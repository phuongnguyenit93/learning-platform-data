# Sinh META-INF/build-info.properties bằng Maven spring-boot:build-info

## 1. Build metadata giải quyết vấn đề gì?

Khi một ứng dụng Spring Boot được phát hành lên máy chủ, container hoặc Kubernetes, file thực tế đang chạy có thể khác source code mà người phát triển mở trong IDE. Chẳng hạn, một service trả HTTP 500 nhưng người trực vận hành chưa biết đó là artifact `0.0.1-SNAPSHOT` hay bản release, build từ module nào hoặc thời điểm đóng gói nào. **Build metadata** giúp ghi một số thông tin nhận dạng của Maven project vào chính artifact.

Spring Boot Maven Plugin cung cấp goal:

```bash
./mvnw spring-boot:build-info
```

Goal `build-info` tạo resource có tên chuẩn:

```text
META-INF/build-info.properties
```

Maven đặt resource đó theo mặc định tại:

```text
target/classes/META-INF/build-info.properties
```

Khi ứng dụng Spring Boot được đóng thành executable JAR bằng `spring-boot:repackage`, resource này thường nằm trong:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

Đường dẫn **trên filesystem Maven** và **đường dẫn bên trong Boot JAR** khác nhau vì Boot Loader đặt application classes/resources dưới `BOOT-INF/classes`. Khi ứng dụng chạy, đường dẫn classpath logic vẫn là `META-INF/build-info.properties`.

**Ý chính:** Goal `spring-boot:build-info` *sinh metadata*, còn `spring-boot:repackage` *đóng gói ứng dụng*. Hai goal có vai trò khác nhau, có thể cùng được cấu hình trong một plugin nhưng không thay thế nhau.

### Mục tiêu của bài học

Sau bài này, bạn sẽ:

- Cấu hình `spring-boot-maven-plugin` để gọi goal `build-info` mỗi lần build.
- Hiểu các khóa chuẩn `build.group`, `build.artifact`, `build.name`, `build.version`, `build.time`.
- Bổ sung metadata tùy chỉnh bằng `additionalProperties` mà không nhầm với `application.properties`.
- Biết lúc nào file xuất hiện ở `target/classes` và cách xác nhận trong executable JAR.
- Đọc metadata từ Java/Spring Boot qua `BuildProperties` hoặc `ClassLoader#getResourceAsStream`.
- Hiển thị build info ở Actuator `/actuator/info` **khi có dependency và cho phép expose endpoint**.
- Xử lý `time` để cân bằng độ chính xác thông tin build và yêu cầu reproducible artifacts.
- Phân biệt metadata build, metadata Git và thông tin runtime; tránh nhúng secrets.

## 2. Các khái niệm và file dễ bị nhầm

| Tên | Do đâu tạo hoặc quản lý? | Mục đích |
|---|---|---|
| `pom.xml` | Người phát triển/Maven model | Khai báo project, dependency, plugin, profile, tọa độ `groupId:artifactId:version` |
| `spring-boot-dependencies` BOM | Maven `dependencyManagement` | Quản lý phiên bản dependency, không phải metadata của một bản build cụ thể |
| `META-INF/build-info.properties` | `spring-boot:build-info` | Thông tin build đã được đóng vào artifact |
| `application.properties`/`application.yaml` | Cấu hình Spring Boot | Runtime configuration: HTTP port, profile, datasource, tính năng... |
| `git.properties` | Git Commit Id Plugin hoặc công cụ tương đương | Commit, branch, commit time và metadata SCM nếu cấu hình |
| `META-INF/MANIFEST.MF` | Maven JAR Plugin/Spring Boot Repackage | Main class, launcher, một số thông tin manifest; không đồng nghĩa build-info |
| `BOOT-INF/classpath.idx` | Boot packaging plugin khi phù hợp | Thứ tự nested JAR được dùng bởi Boot Loader, không chứa thông tin release |
| `META-INF/sbom/...` (khi có) | Công cụ tạo SBOM | Thành phần phần mềm/phụ thuộc, không thay `build-info.properties` |

File `build-info.properties` là **Java properties resource**, không phải file JSON và không phải YAML. Spring Boot có API để đọc nó thành `BuildProperties` khi resource nằm trên classpath.

Một artifact có thể mang cả `build-info.properties`, `git.properties` và manifest; mỗi phần trả lời câu hỏi khác nhau:

- **Build info:** app được đóng gói thành artifact nào, phiên bản nào, lúc nào?
- **Git info:** source revision nào được dùng (khi plugin Git đã cấu hình)?
- **Manifest:** Java launcher khởi chạy class nào?
- **Actuator info:** những thông tin build/git/runtime nào được **cho phép xuất qua endpoint**?

**Đừng xem `build-info.properties` như chứng chỉ nguồn gốc đáng tin cậy.** Bất kỳ ai có khả năng sửa artifact đều có thể thay đổi thông tin trong file; độ tin cậy của chuỗi cung ứng còn phụ thuộc signing, checksum, provenance và quy trình CI/CD.

## 3. Cơ chế spring-boot:build-info trong Maven

Spring Boot Maven Plugin đọc **MavenProject** hiệu lực (sau parent inheritance, profile và nội suy properties) rồi tạo metadata theo tọa độ/name/time của module. Goal này có thể gọi **trực tiếp** hoặc được **bind vào lifecycle** qua phần `<executions>`.

### 3.1. Gọi goal thủ công

```bash
# Chạy goal build-info trên module Maven ở thư mục hiện tại.
./mvnw spring-boot:build-info
```

Nếu máy không có Maven Wrapper nhưng có Maven trong `PATH`:

```bash
mvn spring-boot:build-info
```

Lệnh này **không đồng nghĩa `package` hoặc `repackage`**. Nó có thể tạo `target/classes/META-INF/build-info.properties` nhưng **không tự cập nhật JAR đã đóng gói từ một lần build trước**. Muốn resource được đóng vào artifact mới, cần chạy lifecycle có phase package và cấu hình goal tương ứng.

### 3.2. Bind goal vào build lifecycle

Thêm một execution cho goal `build-info`:

```xml
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
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn cấu hình chèn vào `pom.xml`**, chưa phải POM hoàn chỉnh. Goal `build-info` được plugin gắn vào giai đoạn tạo resources của lifecycle; vì vậy khi chạy `mvn package`, nó có cơ hội sinh resource **trước khi JAR được đóng gói**. Maven Spring Boot Starter Parent còn quản lý version/plugin executions cho `repackage` khi bạn khai báo plugin như trong ví dụ đầy đủ bên dưới.

### 3.3. Các khóa chuẩn

Một file điển hình chứa:

```properties
build.artifact=build-info-lab
build.group=com.example
build.name=Build Info Lab
build.version=0.0.1-SNAPSHOT
build.time=2025-01-01T00:00:00Z
```

Đây là **nội dung minh họa có giá trị cố định của ví dụ ở phần 5**, không phải output luôn giống nhau trong mọi dự án. File thực có thể sắp xếp dòng khác, có ký tự escape theo Java properties và có thêm khóa tùy chỉnh.

| Key trong file | Nguồn mặc định | Ý nghĩa |
|---|---|---|
| `build.group` | `project.groupId` | Nhóm tọa độ Maven |
| `build.artifact` | `project.artifactId` | Artifact ID của module |
| `build.name` | `project.name` | Tên hiển thị của project |
| `build.version` | `project.version` | Phiên bản artifact |
| `build.time` | `project.build.outputTimestamp` hoặc thời điểm bắt đầu Maven session khi không đặt timestamp | Thời điểm build ở định dạng parse được bằng `Instant.parse` |
| `build.<custom-key>` | `additionalProperties` của plugin | Metadata do dự án quyết định |

Một số chi tiết quan trọng:

1. `build.version` là **phiên bản project**, không phải phiên bản JDK hoặc Spring Boot.
2. `build.artifact` là **artifactId**, không phải đường dẫn JAR.
3. `build.time` phản ánh chính sách timestamp được cấu hình khi build. Nếu bạn cố ý cố định `project.build.outputTimestamp`, nó **không** có nghĩa thời gian deploy vào production.
4. `build.name` có thể chứa khoảng trắng; Java properties lưu như một chuỗi giá trị.
5. Các keys có tiền tố `build.` trong file; khi đọc qua `BuildProperties`, API chuẩn dùng `getGroup()`, `getVersion()`... và `get("team")` cho custom key **không có tiền tố**.

### 3.4. File là input cho runtime, không phải nơi để sửa cấu hình runtime

Khi plugin đã sinh metadata, ứng dụng sử dụng nó để log “đang chạy bản nào” hoặc hiển thị release identifier. Không đặt password, API token, private key, connection string hoặc thông tin riêng của CI trong `additionalProperties`. Resource được đóng vào artifact và có thể bị đọc bởi người có file JAR, kể cả khi endpoint Actuator không public.

## 4. Các tham số cấu hình chính thức của goal build-info

Trong Spring Boot Maven Plugin 3.5, những tham số hữu ích nhất là:

| Tham số | Kiểu | Tác dụng |
|---|---|---|
| `additionalProperties` | `Map` | Thêm các metadata key tùy chỉnh; plugin tự gắn tiền tố `build.` |
| `excludeInfoProperties` | `List` | Loại một hoặc nhiều key chuẩn hoặc custom khỏi file đầu ra |
| `outputFile` | `File` | Thay đường dẫn file được sinh; mặc định `${project.build.outputDirectory}/META-INF/build-info.properties` |
| `skip` | `boolean` | Bỏ chạy goal; mặc định `false` |
| `time` | `String` | Điều khiển `build.time`; phải parse được bằng Java `Instant.parse`, hoặc dùng `off` để không sinh |

### 4.1. additionalProperties

Ví dụ:

```xml
<additionalProperties>
    <team>platform</team>
    <release.channel>demo</release.channel>
    <java.version>${java.version}</java.version>
</additionalProperties>
```

Nếu POM có `<java.version>17</java.version>`, các khóa thêm sẽ là:

```properties
build.team=platform
build.release.channel=demo
build.java.version=17
```

Đối với key tùy chỉnh, không ghi tiền tố `build.` lần nữa trong `additionalProperties` trừ khi bạn chủ ý muốn key sinh ra có thêm tiền tố; cách thông thường là nhập `<team>` chứ không phải `<build.team>`.

Các giá trị như `${java.version}` là **Maven property interpolation**; Maven nội suy chúng theo model hiện tại. Nếu giá trị cần lấy từ môi trường, phải kiểm tra biến có sẵn và không vô tình rò rỉ secret. Metadata phát hành nên được tạo từ các biến CI được kiểm soát, không lấy ngẫu nhiên từ máy lập trình viên.

### 4.2. excludeInfoProperties

Bạn có thể loại các trường chuẩn `group`, `artifact`, `name`, `version`, `time` hoặc một custom key. Đoạn cấu hình **minh họa để chèn vào execution**:

```xml
<configuration>
    <excludeInfoProperties>
        <excludeInfoProperty>time</excludeInfoProperty>
    </excludeInfoProperties>
</configuration>
```

Kết quả là file không có `build.time`. Khi mục tiêu chỉ là bỏ timestamp, một lựa chọn ngắn hơn là `<time>off</time>`; hãy chọn một cách rõ ràng. Nếu loại `version`, `BuildProperties.getVersion()` có thể trả `null`; đừng viết mã Java giả định mọi trường luôn tồn tại.

### 4.3. outputFile

Mặc định:

```text
${project.build.outputDirectory}/META-INF/build-info.properties
                ↓
target/classes/META-INF/build-info.properties
```

Đổi `outputFile` chỉ nên làm khi bạn **đồng thời hiểu cách đưa resource vào classpath**. Ví dụ:

```xml
<configuration>
    <outputFile>${project.build.directory}/generated/build-info.properties</outputFile>
</configuration>
```

Khi đó goal có thể tạo file tại `target/generated/build-info.properties`, nhưng `spring-boot:repackage`/Spring Boot runtime **không tự nhận** đây là `classpath:META-INF/build-info.properties` nữa. Bạn phải cấu hình resource copying và/hoặc `spring.info.build.location` phù hợp. **Khuyến nghị cho mục đích học:** giữ đường dẫn mặc định, bởi đó là đường mà Spring Boot auto-configuration nhận diện.

### 4.4. time, outputTimestamp và khả năng tái lập

Goal mặc định dùng `project.build.outputTimestamp` nếu có, nếu không dùng thời điểm bắt đầu Maven session. `time` phải là chuỗi phù hợp `Instant.parse`, ví dụ:

```xml
<properties>
    <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Nếu muốn cấu hình tường minh tại goal:

```xml
<configuration>
    <time>2025-01-01T00:00:00Z</time>
</configuration>
```

Đây là **hai phương án khác nhau**: `project.build.outputTimestamp` còn ảnh hưởng các plugin hỗ trợ reproducible archive timestamps; `time` chỉ điều khiển build-info của goal. Không nên hardcode một timestamp bất kỳ trong build production rồi giới thiệu đó là “thời gian build thực”. Với CI, có thể dùng một timestamp **ổn định được xác định từ quy trình release** hoặc loại trường thời gian nếu quy định reproducibility ưu tiên byte-for-byte equality.

Để loại bỏ `build.time` mà không tạo một giá trị giả:

```xml
<configuration>
    <time>off</time>
</configuration>
```

Nếu thật sự cần ghi **thời gian build thực**, có thể giữ default lấy từ Maven session, chấp nhận rằng metadata timestamp làm bytes của artifact thay đổi ở mỗi lần build. Khi đối chiếu hash giữa hai môi trường, phải kiểm soát thêm JDK, archive timestamps, dependency versions, plugin output, file ordering và mọi nguồn không xác định khác; chỉ chỉnh `build.time` không đảm bảo toàn bộ JAR reproducible.

### 4.5. skip

Lệnh CLI sau bỏ qua goal khi nó được gọi trong lifecycle có execution:

```bash
./mvnw clean package -Dspring-boot.build-info.skip=true
```

Dù build thành công, trong **build sạch** file `build-info.properties` sẽ không được tạo từ goal đó. Khi **không clean**, file cũ có thể còn trong `target/classes` và vẫn được đóng gói — đây là một bẫy lớn khi debug. Vì vậy khi xác minh skip thực sự, dùng `clean` và đọc lại archive.

**Không nhầm `spring-boot.build-info.skip` với `-DskipTests` hoặc `-Dmaven.test.skip=true`**: chúng điều khiển những công việc khác nhau. Bỏ goal build-info không chứng minh tests bị bỏ và ngược lại.

## 5. Bài thực hành Java 17 + Spring Boot: Maven POM hoàn chỉnh

Ta sẽ tạo một web application nhỏ tên `build-info-lab`, phát hành một executable JAR và kiểm tra build metadata qua cả Java API lẫn Actuator.

**Môi trường:** JDK 17+, Maven 3.6.3+ hoặc Maven Wrapper cấu hình thích hợp, mạng hoặc Maven cache để tải dependency khi chưa có. Ví dụ dùng Spring Boot **3.5.16**, là phiên bản pin để minh họa, không mặc định luôn mới nhất. Thời gian metadata được **cố định theo chủ đích** để có stdout dễ kiểm chứng.

### 5.1. Cấu trúc thư mục

```text
build-info-lab/
├── pom.xml
├── mvnw                                  (nếu dự án có Maven Wrapper)
├── mvnw.cmd                              (nếu dự án có Maven Wrapper)
├── .mvn/wrapper/...                      (nếu có Maven Wrapper)
└── src/
    ├── main/
    │   ├── java/com/example/buildinfo/
    │   │   ├── BuildInfoLabApplication.java
    │   │   └── BuildVersionController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/buildinfo/BuildInfoLabApplicationTests.java
```

Không cần tạo `mvnw` giả. Nếu đã có Maven cài trên máy, mọi lệnh `./mvnw` có thể đổi thành `mvn`. Còn nếu cần Wrapper, hãy tạo bằng quy trình Maven Wrapper chính thức và commit các file của nó vào repository.

### 5.2. pom.xml hoàn chỉnh

```xml
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
    <artifactId>build-info-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>Build Info Lab</name>
    <description>Build metadata example with Spring Boot Maven Plugin</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <!-- Timestamp cố định để minh họa output; sản phẩm thật cần chính sách CI -->
        <project.build.outputTimestamp>2025-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
                            <additionalProperties>
                                <team>platform</team>
                                <release.channel>demo</release.channel>
                                <java.version>${java.version}</java.version>
                            </additionalProperties>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Với `spring-boot-starter-parent`:

- Spring Boot quản lý phiên bản `starter-web`, `starter-actuator`, `starter-test` và plugin Spring Boot phù hợp.
- `spring-boot-maven-plugin` chỉ được khai báo **một lần** trong `<plugins>`.
- Execution `generate-build-info` gọi goal `build-info`; parent cung cấp cấu hình `repackage` tiêu chuẩn khi plugin được sử dụng. **Không cần đặt `repackage` vào cùng execution này**.
- File `target/classes/META-INF/build-info.properties` được tạo trong build lifecycle, và `repackage` tạo executable JAR có cả file resource.
- `<project.build.outputTimestamp>` đặt cố định cho bài học. Trong dự án thật hãy dùng timestamp phù hợp chính sách release/reproducibility.

### 5.3. Java class chính: đọc BuildProperties sau khi startup

Tạo `src/main/java/com/example/buildinfo/BuildInfoLabApplication.java`:

```java
package com.example.buildinfo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.info.BuildProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BuildInfoLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildInfoLabApplication.class, args);
    }

    @Bean
    CommandLineRunner printBuildInfo(BuildProperties build) {
        return args -> {
            System.out.println("Group: " + build.getGroup());
            System.out.println("Artifact: " + build.getArtifact());
            System.out.println("Name: " + build.getName());
            System.out.println("Version: " + build.getVersion());
            System.out.println("Time: " + build.getTime());
            System.out.println("Team: " + build.get("team"));
            System.out.println("Channel: " + build.get("release.channel"));
            System.out.println("Java target: " + build.get("java.version"));
        };
    }
}
```

Những điểm cần hiểu:

1. `BuildProperties` là bean Spring Boot auto-configure khi có resource `classpath:META-INF/build-info.properties`, không phải object Maven runtime truyền vào.
2. `getGroup()`, `getArtifact()`, `getName()`, `getVersion()` đọc các trường chuẩn.
3. `getTime()` trả `Instant` hoặc `null` nếu thiếu/cấu hình sai; trong ví dụ timestamp cố định hợp lệ nên có `2025-01-01T00:00:00Z`.
4. `get("team")`, `get("release.channel")` và `get("java.version")` đọc các **custom keys không có tiền tố build.**.
5. Bean được inject vào `CommandLineRunner`; nếu resource không được sinh/không nằm trên classpath, ứng dụng này có thể **không startup được** vì thiếu `BuildProperties` bean. Đây là lỗi có dụng ý giúp phát hiện configuration sai.

### 5.4. Controller để kiểm tra version qua HTTP

`src/main/java/com/example/buildinfo/BuildVersionController.java`:

```java
package com.example.buildinfo;

import org.springframework.boot.info.BuildProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BuildVersionController {
    private final BuildProperties build;

    public BuildVersionController(BuildProperties build) {
        this.build = build;
    }

    @GetMapping("/build-version")
    public String version() {
        return build.getArtifact() + ":" + build.getVersion();
    }
}
```

Controller chỉ trả **tên artifact và version**, không trả bí mật hoặc toàn bộ Environment. Endpoint custom `/build-version` là ứng dụng tự tạo, **không phải** endpoint Actuator. Trong ứng dụng thật, cần chính sách xác thực/visibility phù hợp ngay cả với metadata tưởng như vô hại.

### 5.5. application.properties: bật Actuator info một cách có chủ đích

Tạo `src/main/resources/application.properties`:

```properties
spring.application.name=build-info-lab
spring.main.banner-mode=off
server.port=8080

# Mặc định web chỉ expose health; cho phép thêm info cho bài thực hành.
management.endpoints.web.exposure.include=health,info
```

Với dependency `spring-boot-starter-actuator`, Spring Boot có `BuildInfoContributor` khi `BuildProperties` bean tồn tại. Do `/actuator/info` **không được expose qua HTTP mặc định**, dòng `management.endpoints.web.exposure.include=health,info` là cần thiết để gọi từ trình duyệt/curl trong bài học.

Nếu Spring Security hoặc các policy khác được thêm vào ứng dụng, `/actuator/info` có thể yêu cầu xác thực hoặc bị chặn theo cấu hình. Không tự mở `management.endpoints.web.exposure.include=*` trong production.

### 5.6. Unit/integration test nhỏ xác nhận BuildProperties

`src/test/java/com/example/buildinfo/BuildInfoLabApplicationTests.java`:

```java
package com.example.buildinfo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BuildInfoLabApplicationTests {

    @Autowired
    BuildProperties build;

    @Test
    void buildInfoIsAvailableInApplicationContext() {
        assertEquals("com.example", build.getGroup());
        assertEquals("build-info-lab", build.getArtifact());
        assertEquals("0.0.1-SNAPSHOT", build.getVersion());
        assertEquals("platform", build.get("team"));
        assertNotNull(build.getTime());
    }
}
```

Ở đây test chỉ xác nhận bean và metadata của module. `webEnvironment = NONE` giúp kiểm tra nhanh mà không khởi chạy HTTP server. Test vẫn khởi tạo Spring ApplicationContext nên cần resource đã được generate **trước phase test** khi chạy `mvn test` hoặc `mvn package` theo lifecycle có execution.

**Cạm bẫy IDE:** Nếu IDE chạy riêng test Java bằng JUnit launcher mà không kích hoạt Maven lifecycle và folder generated output chưa có, bean `BuildProperties` có thể vắng. Cách điều tra: chạy `./mvnw clean test` và kiểm tra `target/classes/META-INF/build-info.properties`, rồi cấu hình IDE nhận generated resources hoặc chạy qua Maven task thích hợp.

## 6. Chạy build, kiểm tra file và xác minh stdout

Tại thư mục root chứa `pom.xml`, trên Linux/macOS:

```bash
# Có Maven Wrapper:
./mvnw clean package

# Nếu không có wrapper, dùng Maven đã cài:
mvn clean package
```

Chọn **một** cách build, không cần chạy cả hai. Windows PowerShell với Wrapper dùng `.\mvnw.cmd clean package`.

Với đúng POM/source ở mục 5, khi Maven chạy thành công, file được sinh ở:

```text
target/classes/META-INF/build-info.properties
```

và executable JAR ở:

```text
target/build-info-lab-0.0.1-SNAPSHOT.jar
```

### 6.1. Xem file trong thư mục output

Linux/macOS:

```bash
cat target/classes/META-INF/build-info.properties
```

Windows PowerShell:

```powershell
Get-Content target/classes/META-INF/build-info.properties
```

Nội dung sẽ có các **khóa và giá trị**:

```properties
build.artifact=build-info-lab
build.group=com.example
build.name=Build Info Lab
build.version=0.0.1-SNAPSHOT
build.time=2025-01-01T00:00:00Z
build.team=platform
build.release.channel=demo
build.java.version=17
```

**Không cần thứ tự các dòng trùng ví dụ**: Java properties không tạo một hợp đồng về thứ tự cho ứng dụng. Một số ký tự đặc biệt có thể được escape/format lại khi ghi file. Điều cần kiểm tra là **khóa và giá trị**, không phải byte-order của đoạn minh họa.

### 6.2. Xác nhận resource được đóng vào executable JAR

```bash
# Liệt kê archive; nhìn đúng tên JAR do Maven tạo:
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar

# Linux/macOS có grep:
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar |
    grep 'BOOT-INF/classes/META-INF/build-info.properties'
```

Trên PowerShell:

```powershell
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/classes/META-INF/build-info.properties'
```

Với Spring Boot executable JAR, **đường dẫn trong archive** là:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

Đừng nhầm với `META-INF/build-info.properties` nằm ở root của một plain JAR. Spring Boot Loader đưa `BOOT-INF/classes` vào application classpath nên ResourceLoader/ClassLoader vẫn có thể tìm resource bằng `classpath:META-INF/build-info.properties`.

Muốn trích đúng file từ JAR mà không thay đổi archive:

```bash
mkdir -p inspect
cd inspect
jar xf ../target/build-info-lab-0.0.1-SNAPSHOT.jar \
  BOOT-INF/classes/META-INF/build-info.properties
cat BOOT-INF/classes/META-INF/build-info.properties
cd ..
```

PowerShell thay `cat` bằng `Get-Content` và dùng `Push-Location`/`Pop-Location` nếu cần. Lệnh `jar xf` trích file vào thư mục kiểm tra; nó **không sửa executable JAR gốc**.

### 6.3. Chạy executable JAR và đọc BuildProperties

```bash
java -jar target/build-info-lab-0.0.1-SNAPSHOT.jar
```

Khi startup thành công, console **có chứa các dòng do CommandLineRunner in** chính xác như sau:

```text
Group: com.example
Artifact: build-info-lab
Name: Build Info Lab
Version: 0.0.1-SNAPSHOT
Time: 2025-01-01T00:00:00Z
Team: platform
Channel: demo
Java target: 17
```

Do app có `spring-boot-starter-web`, embedded server sẽ tiếp tục chạy và chờ HTTP requests; log Spring Boot khác có thể xuất hiện. Không khẳng định toàn bộ stdout chỉ có 8 dòng trên.

### 6.4. Kiểm tra endpoint HTTP và Actuator

Ở terminal khác, sau khi server sẵn sàng:

```bash
curl -fsS http://localhost:8080/build-version
curl -fsS http://localhost:8080/actuator/info
```

Đối với custom endpoint, HTTP body dự kiến (không có newline được controller tự thêm):

```text
build-info-lab:0.0.1-SNAPSHOT
```

Còn Actuator `/actuator/info` sẽ chứa **nhóm `build`** với artifact/name/version/group/time và các custom keys theo mức hiển thị mặc định/phần cấu hình phù hợp. Dạng JSON có thể trông như dưới đây (rút gọn; thứ tự keys không bảo đảm):

```json
{
  "build": {
    "artifact": "build-info-lab",
    "name": "Build Info Lab",
    "version": "0.0.1-SNAPSHOT",
    "group": "com.example",
    "time": "2025-01-01T00:00:00Z",
    "team": "platform"
  }
}
```

JSON trên là **ví dụ cấu trúc**, không phải cam kết toàn bộ response: nội dung và custom property formatting tùy phiên bản/contributors, có thể có các trường bổ sung. Muốn kiểm chứng **đúng từng giá trị**, đọc file hoặc `BuildProperties` bean là nguồn trực tiếp.

### 6.5. Trường hợp không muốn chạy web server

Nếu chỉ dùng thư viện `spring-boot-starter` (không có `starter-web`) và không có web stack, app vẫn có thể đọc `BuildProperties` từ Java và in console khi resource tồn tại. Nhưng `curl localhost:8080/actuator/info` **sẽ không hoạt động** nếu không có HTTP server; việc có file metadata không tự tạo HTTP endpoint.

## 7. Đọc file bằng Java 17 thuần: không cần Spring

Để hiểu tại sao resource là một file Java properties thật, thử một chương trình Java 17 độc lập tên `ReadBuildInfo.java`. Chạy chương trình từ thư mục root ví dụ, để `target/classes` hiện diện.

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ReadBuildInfo {
    public static void main(String[] args) throws IOException {
        String path = "META-INF/build-info.properties";

        try (InputStream input = ReadBuildInfo.class
                .getClassLoader().getResourceAsStream(path)) {
            if (input == null) {
                throw new IOException("Missing resource: " + path);
            }

            Properties properties = new Properties();
            properties.load(input);
            System.out.println("Artifact = "
                    + properties.getProperty("build.artifact"));
            System.out.println("Version = "
                    + properties.getProperty("build.version"));
            System.out.println("Team = "
                    + properties.getProperty("build.team"));
        }
    }
}
```

Biên dịch và chạy với classpath chỉ gồm **Java class và thư mục Maven output**:

```bash
javac ReadBuildInfo.java
java -cp ".:target/classes" ReadBuildInfo
```

Trên Windows, dấu phân cách classpath là **dấu chấm phẩy**:

```powershell
javac ReadBuildInfo.java
java -cp ".;target/classes" ReadBuildInfo
```

Với `build-info.properties` được tạo đúng từ POM ví dụ, stdout của chương trình Java này **chính xác**:

```text
Artifact = build-info-lab
Version = 0.0.1-SNAPSHOT
Team = platform
```

Chương trình không dùng `BuildProperties` bean, không nạp Spring và không cần Maven plugin trong runtime Java classpath; nó chỉ đọc **file resource đã có**. Cách này hữu ích để tách lỗi “Maven không sinh file” khỏi lỗi “Spring không tìm được bean”:

- Nếu `ReadBuildInfo` báo `Missing resource`, kiểm tra `target/classes` có file chưa và lệnh `-cp` có đúng không.
- Nếu Java thuần đọc được nhưng Spring không có bean, kiểm tra classpath thật của process Spring, autoconfiguration và vị trí resource.
- Nếu `java -jar` chạy nhưng dùng file build cũ, kiểm tra JAR được build lần cuối và đường dẫn artifact thật.

## 8. Hiểu BuildProperties bean và ProjectInfoAutoConfiguration

Spring Boot tạo `BuildProperties` từ resource `META-INF/build-info.properties` khi resource có trong application classpath và không có bean thay thế. Điều này thuộc `ProjectInfoAutoConfiguration`, không phụ thuộc việc app có Actuator HTTP endpoint.

### 8.1. API BuildProperties

| API | Trả gì? | Lưu ý |
|---|---|---|
| `getGroup()` | `com.example` | Có thể `null` nếu key bị loại |
| `getArtifact()` | `build-info-lab` | Artifact ID, không phải full JAR path |
| `getName()` | `Build Info Lab` | `<name>` trong effective POM |
| `getVersion()` | `0.0.1-SNAPSHOT` | Maven version của module |
| `getTime()` | `Instant` | Có thể `null` nếu không có/không parse được `build.time` |
| `get("team")` | `platform` | Key custom **không có** prefix `build.` |
| `get("release.channel")` | `demo` | Có thể là chuỗi không phải nested object |
| `toPropertySource()` | Spring PropertySource | Dùng nếu cần đưa metadata vào cơ chế PropertySource |

**Phân biệt:** `BuildProperties.getVersion()` là phiên bản **artifact đã build**, còn `SpringBootVersion.getVersion()` hoặc Spring environment có thể cho biết phiên bản **framework**. Chúng không nhất thiết bằng nhau.

### 8.2. Đổi vị trí resource khi chủ động tùy biến

Spring Boot mặc định tìm `classpath:META-INF/build-info.properties`. Nếu ứng dụng **có lý do thật** phải đọc vị trí khác, có thể dùng Spring property:

```properties
spring.info.build.location=classpath:custom/build-info.properties
```

Nhưng khi đó bạn cũng phải chắc file `custom/build-info.properties` thực sự có trên runtime classpath. Không thay `outputFile` trong Maven rồi kỳ vọng auto-configuration tự đoán đường dẫn mới.

### 8.3. Nếu muốn startup ngay cả khi thiếu file

Ví dụ chính cố ý inject bắt buộc để phát hiện build lỗi. Trong sản phẩm thật, một số môi trường IDE có thể chạy app trước khi Maven tạo resource. Khi chấp nhận thiếu metadata, có thể dùng một bean tùy chọn, ví dụ **đoạn minh họa thay thế constructor**:

```java
private final org.springframework.beans.factory.ObjectProvider<BuildProperties>
        buildPropertiesProvider;

public BuildVersionController(
        org.springframework.beans.factory.ObjectProvider<BuildProperties> provider) {
    this.buildPropertiesProvider = provider;
}
```

Đây là **đoạn class fragment**, chưa hoàn chỉnh để chạy độc lập. `ObjectProvider#getIfAvailable()` cho phép xử lý trường hợp metadata chưa được sinh. Tuy nhiên fallback như `"unknown"` nên được log/giám sát; nếu production yêu cầu release metadata, tốt hơn là kiểm tra file trong CI và fail build thay vì im lặng.

## 9. Reproducible build và policy chọn build.time

Một lỗi hay gặp là hai người build cùng commit/dependency/POM nhưng file JAR có hash khác nhau. `build.time` là một nguồn khác biệt nếu nó thay đổi theo Maven session. Maven 3.5+ và Spring Boot plugins cung cấp cách điều khiển timestamp để hỗ trợ reproducible builds.

### 9.1. Ba chính sách thường gặp

| Chính sách | Ví dụ | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Ghi thời điểm Maven session | Không đặt fixed timestamp | Dễ biết build xảy ra lúc nào | Build lại có thể thay đổi bytes |
| Pin thời điểm build từ CI/release | `project.build.outputTimestamp` do pipeline cấp | Giúp tái lập nếu mọi input khác ổn định | Cần quy trình xác định timestamp đáng tin |
| Không đưa build time vào file | `<time>off</time>` hoặc exclude `time` | Loại một nguồn không xác định | Không còn timestamp build trong metadata |

**Không dùng một timestamp cố định giả để thay cho giám sát release time.** Ví dụ `2025-01-01T00:00:00Z` trong bài chỉ để stdout có giá trị đoán được. Khi deploy, có thể đo **deployment time** bằng CD system, khác với **build time** và **commit time**.

### 9.2. SOURCE_DATE_EPOCH và timestamps

Một số pipeline dùng `SOURCE_DATE_EPOCH` làm nguồn timestamp tái lập. Đây là một quy ước công nghiệp, nhưng **đừng tự khẳng định mọi phiên bản Maven/Boot plugin đều tự sử dụng biến đó**. Nếu build cần timestamp từ biến môi trường, hãy cấu hình nó vào `project.build.outputTimestamp` hoặc tham số `time` theo chính sách thực tế và xác minh trong file sinh ra.

### 9.3. Kiểm tra tính nhất quán

Với cùng source, dependencies và tool versions:

```bash
./mvnw clean package
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar
```

Sau đó trích file `build-info.properties` ra để xem `build.time`. Để kiểm chứng byte-for-byte reproducibility, cần so SHA-256 của artifact từ hai build sạch tương đương; chỉ thấy version/time trùng nhau chưa đủ.

Nếu `build.time` có dạng không parse được bằng `Instant.parse`, Java `BuildProperties.getTime()` có thể là `null` dù raw key vẫn còn. Dùng ISO-8601 có timezone rõ ràng như `2025-01-01T00:00:00Z` để tránh mơ hồ.

## 10. Mối quan hệ với Actuator info và bảo mật

`spring-boot-starter-actuator` cung cấp `info` endpoint, nhưng **build-info file không phụ thuộc Actuator để tồn tại**. Có hai trường hợp:

- **Có file, không có Actuator:** Spring Boot vẫn có thể tạo `BuildProperties` bean và ứng dụng dùng nó trong code.
- **Có file và Actuator:** `BuildInfoContributor` có thể thêm nhóm `build` vào `/actuator/info`, khi endpoint được kích hoạt và được expose theo cấu hình.
- **Có Actuator nhưng không có file:** thường không có nhóm build từ `BuildInfoContributor`; endpoint có thể trả `{}` nếu không có contributor khác.
- **Có file nhưng info không xuất qua HTTP:** có thể chưa expose `info`, endpoint bị security/policy chặn, hoặc `management.info.build.enabled=false`.

### 10.1. Không mặc định info được public

Mặc định Spring Boot chỉ expose HTTP health, không phải mọi endpoint. Để thử nghiệm local:

```properties
management.endpoints.web.exposure.include=health,info
```

Với production, cần xác định người dùng và mạng nào được truy cập. Nếu dùng Spring Security, cấu hình `SecurityFilterChain`/Actuator authorization phù hợp. Không bật toàn bộ `*` chỉ để đọc build version.

### 10.2. Không đặt dữ liệu nhạy cảm trong additionalProperties

Ví dụ **không an toàn**:

```xml
<additionalProperties>
    <database.password>super-secret-value</database.password>
    <ci.token>some-private-token</ci.token>
</additionalProperties>
```

Đoạn trên **chỉ minh họa điều cần tránh**, không phải cấu hình nên sử dụng. Secrets có thể nằm trong JAR được phát hành, log và response của Actuator info. Đừng dựa vào việc `/actuator/info` chưa expose làm biện pháp bảo vệ secrets; artifact vẫn có thể bị đọc bởi người có quyền tải file.

Thông tin tương đối an toàn: `team`, `release.channel`, `source.encoding`, `artifact`/`version` hoặc mã release không nhạy cảm. Tuy nhiên với môi trường bảo mật cao, cả tên nội bộ/branch/build server có thể là thông tin không nên public.

### 10.3. BuildInfoContributor vs GitInfoContributor

| Nguồn | Điều kiện | Nội dung |
|---|---|---|
| `BuildInfoContributor` | `META-INF/build-info.properties` hiện diện, bean/feature enabled | Build coordinates/time/custom metadata |
| `GitInfoContributor` | `git.properties` hiện diện và cấu hình phù hợp | Commit ID, branch, commit time |
| `EnvironmentInfoContributor` | Bật tương ứng | Các property `info.*` trong Spring Environment |
| Custom `InfoContributor` | Bean do ứng dụng định nghĩa | Thông tin bổ sung do code xây dựng |

Goal `build-info` **không tự tạo Git commit hash**. Muốn Git metadata, cấu hình plugin chuyên dụng và test output `git.properties` riêng. **Không nhầm `build.time` với `git.commit.time`**: thời gian đóng gói và thời gian commit có thể cách nhau rất xa.

## 11. Maven đa mô-đun: sinh build info ở đúng module

Giả sử Maven reactor có:

```text
multi-service/
├── pom.xml               (parent/aggregator)
├── shared-lib/pom.xml     (JAR thư viện)
└── service-app/pom.xml    (Spring Boot executable app)
```

Mỗi MavenProject có `groupId`/`artifactId`/`version` và `build.outputDirectory` riêng. Nếu đặt goal `build-info` trong `<build><plugins>` của parent rồi để tất cả module kế thừa, bạn có thể sinh file `META-INF/build-info.properties` cho **mọi module**, kể cả root `pom` packaging hoặc thư viện không cần metadata trong artifact phát hành.

### 11.1. Cấu hình khuyến nghị

- Root parent giữ **plugin version** trong `<build><pluginManagement>` để module con dùng nhất quán.
- Chỉ `service-app` khai báo `spring-boot-maven-plugin` và execution `build-info` (cùng chính sách `repackage` phù hợp).
- `shared-lib` dùng `maven-jar-plugin` hoặc lifecycle JAR thường, không cần Boot executable plugin chỉ để dùng dependency management.
- Nếu nhiều app có chung chính sách metadata, có thể tạo parent/convention cấu hình kế thừa có kiểm soát; bảo đảm mỗi app ghi **thư mục target của chính mình**.

Ví dụ **đoạn parent POM** quản lý plugin version nhưng chưa thực thi:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.5.16</version>
        </plugin>
    </plugins>
</pluginManagement>
```

Nếu parent là `spring-boot-starter-parent`, plugin version đã được quản lý; không cần thêm khai báo trên. Đoạn trên chỉ dành cho parent tự xây dựng.

### 11.2. Kiểm tra từng module

```bash
# Build app và các project phụ thuộc trong reactor:
./mvnw -pl :service-app -am clean package

# Chỉ xem effective POM của app:
./mvnw -pl :service-app help:effective-pom

# Xem resource và archive đúng module:
jar tf service-app/target/service-app-1.0.0.jar
```

Các tên module/version trên là **giả định**; chúng chỉ chạy nguyên văn nếu Maven reactor của bạn đúng tên `service-app`, phiên bản `1.0.0` và có wrapper. Mục đích là kiểm tra **metadata của artifact app**, không nhầm file ở root hay metadata của một library module.

**Lưu ý:** khi chạy `-pl :service-app -am`, các project cần thiết trong reactor cũng được build. Nếu chúng được cấu hình sinh build-info, metadata của chúng không tự trở thành metadata “chính” của app; hãy đọc đúng resource trong artifact được triển khai. Khi có nhiều dependency JAR mang `META-INF/build-info.properties`, classloader resource lookup có thể thấy nhiều bản; tránh cấu hình trùng/không rõ chủ sở hữu metadata.

## 12. So với Gradle: tương đương về mục đích, khác cú pháp

Trong Gradle Spring Boot Plugin cũng có chức năng tạo build information, ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

springBoot {
    buildInfo()
}
```

Gradle plugin tạo task `bootBuildInfo`, còn Maven dùng goal `spring-boot:build-info`. **Không dùng lệnh Gradle `bootBuildInfo` trong Maven**, và không dùng `-Dspring-boot.build-info.skip` như một cách điều khiển task Gradle.

Bài này tập trung vào Maven: goal đọc `MavenProject`, cấu hình XML trong POM, file ở `target/classes`. Nếu một monorepo chứa Maven và Gradle project, hãy xác định build tool **của artifact cuối** trước khi tìm file trong `target` hay `build`.

## 13. Sự cố phổ biến và cách điều tra

| Triệu chứng | Giả thuyết thường gặp | Kiểm tra/cách xử lý |
|---|---|---|
| Không thấy `target/classes/META-INF/build-info.properties` | Chưa chạy goal hoặc execution chưa bind vào lifecycle | Xem `pom.xml`, `help:effective-pom`, gọi `mvn spring-boot:build-info` |
| Có plugin nhưng file không sinh trong `mvn package` | Chỉ khai báo `spring-boot-maven-plugin`, chưa có execution `build-info` | Thêm `<executions><execution><goals><goal>build-info</goal>...` |
| File được tạo nhưng executable JAR không có | Chạy goal sau khi package, custom `outputFile` hoặc artifact cũ | Dùng `mvn clean package`, kiểm tra `target/classes` và `jar tf` |
| Java báo thiếu `BuildProperties` bean | Resource không nằm trên application classpath hoặc auto-config bị thay | Kiểm tra `BOOT-INF/classes/META-INF/build-info.properties`, `spring.info.build.location` và bean config |
| `BuildProperties.getVersion()` trả `null` | `version` bị loại hoặc file thiếu key | Xem `build.version`, `excludeInfoProperties` |
| `getTime()` trả `null` | Không có `build.time` hoặc time không parse được | Kiểm tra `<time>off</time>` và ISO-8601 UTC |
| `/actuator/info` trả 404 | Thiếu Actuator, không expose info, endpoint bị disabled hoặc wrong URL | Thêm starter-actuator và `management.endpoints.web.exposure.include=health,info`, kiểm tra security |
| `/actuator/info` trả `{}` | Không có contributor/build file hoặc contributors disabled | Kiểm tra `BuildInfoContributor` và resource |
| `/actuator/info` trả 401/403 | Spring Security/authorization | Dùng credential/role hợp lệ; không mở public bừa bãi |
| File có giá trị cũ sau skip goal | `target/classes` chứa output từ lần build trước | `mvn clean package` rồi kiểm tra |
| Build time thay đổi ở mỗi build | Timestamp lấy từ Maven session | Pin `project.build.outputTimestamp` hoặc tắt `build.time` theo policy |
| Build time cố định sai ngày release | Hardcode timestamp minh họa được copy vào production | Để CI cấp timestamp hoặc ghi release time ở hệ CD |
| `additionalProperties` tạo key sai | Ghi sẵn `build.` trong tên key hoặc Maven interpolation sai | Kiểm tra generated properties và gọi `build.get("key")` đúng |
| Metadata app lấy từ module thư viện | Nhiều JAR cùng có file `META-INF/build-info.properties` | Giới hạn sinh ở app; kiểm tra classpath/resource resolution |
| Maven chạy trực tiếp goal nhưng POM plugin version không rõ | Chưa pin plugin, effective POM/parent khác dự tính | Pin plugin version; dùng `mvn help:effective-pom` |
| Spring app không có HTTP server nên curl fail | Chỉ dùng non-web starter | Thêm web starter hoặc kiểm tra bằng Java `BuildProperties` |
| Test trong IDE fail nhưng Maven test pass | IDE không sinh resource `build-info.properties` | Chạy Maven lifecycle trước và kiểm tra generated resource folder |
| Resource có secret từ build pipeline | `additionalProperties` lấy password/token | Gỡ khỏi cấu hình, rotate secret nếu đã phát hành, bảo vệ artifact |

### Quy trình chẩn đoán năm bước

1. **Xác định module và POM:** có đúng `artifactId` của ứng dụng không? Plugin version và execution `build-info` có nằm trong effective POM không?
2. **Sinh lại sạch:** `./mvnw clean package`; đọc log goal `spring-boot:build-info` có chạy hay bị skip.
3. **Đọc file đầu ra:** `target/classes/META-INF/build-info.properties`, kiểm tra keys và giá trị sau nội suy.
4. **Đọc artifact cuối:** `jar tf ...jar`, trích `BOOT-INF/classes/META-INF/build-info.properties`, đối chiếu với file target/classes.
5. **Đọc runtime:** kiểm tra `BuildProperties` bean, log startup và `/actuator/info` theo quy định bảo mật; so version với artifact thật đang chạy.

Không sửa file trong `target/classes` thủ công rồi coi đây là giải pháp bền vững. Hãy sửa source POM, CI variables hoặc resource generation và rebuild.

## 14. Cách kiểm tra chất lượng và đưa vào CI/CD

Một quy trình build release có thể yêu cầu:

- Goal `build-info` được thực thi trong lifecycle mà không bị bỏ qua.
- Các keys chuẩn `group`, `artifact`, `version` có giá trị đúng.
- Additional properties thuộc allowlist đã duyệt; không chứa password/token.
- `build.time` tuân chính sách timestamp, không khiến reproducibility bị hỏng ngoài dự kiến.
- Resource có trong **JAR được upload/deploy**, không chỉ thư mục `target/classes`.
- Khi chạy artifact, `BuildProperties` báo đúng tọa độ/version.
- Actuator `info` được expose **chỉ theo chính sách truy cập**, không mở rộng ngẫu nhiên.
- Multi-module CI xác minh đúng app artifact; library modules không phải tự có cùng metadata.

### Ví dụ kiểm tra artifact trong CI (Linux/macOS)

Giả sử dùng đúng POM và artifact ở mục 5:

```bash
set -e

./mvnw clean verify

# Đảm bảo file Maven-generated tồn tại.
test -f target/classes/META-INF/build-info.properties

# Đảm bảo executable JAR chứa resource trong BOOT-INF/classes.
jar tf target/build-info-lab-0.0.1-SNAPSHOT.jar |
    grep -Fx 'BOOT-INF/classes/META-INF/build-info.properties'

# Đảm bảo không build nhầm version.
grep -F 'build.version=0.0.1-SNAPSHOT' \
    target/classes/META-INF/build-info.properties
```

Đây là **một script kiểm tra theo đúng file/tên của ví dụ**, không phải workflow CI có sẵn trên mọi hệ thống. Với POM multi-module, đổi đường dẫn, artifactId và expected version theo biến chính sách của pipeline. Trên Windows PowerShell dùng `Test-Path`/`Select-String` cùng cách kiểm tra exit status thích hợp.

### Cần phân biệt build time và release provenance

Một file build-info giúp debug “đang chạy phiên bản nào” nhưng không chứng minh:

- JAR được build từ **commit nào** nếu không có metadata Git hoặc attestation.
- Artifact không bị sửa sau build.
- Người ký/release có quyền hợp lệ.
- Thư viện phụ thuộc không có lỗ hổng.
- Deploy thành công vào đúng môi trường và thời điểm.

Đối với yêu cầu audit mạnh, dùng build-info cùng Git metadata, checksums/signatures, SBOM, CI provenance và deployment records — **không dùng một file properties làm nguồn tin duy nhất**.

## 15. Checklist cuối bài

- [ ] Hiểu goal `spring-boot:build-info` khác `spring-boot:repackage`.
- [ ] Có execution `build-info` trong POM tại **module ứng dụng**.
- [ ] Biết file mặc định `target/classes/META-INF/build-info.properties`.
- [ ] Biết file trong executable JAR ở `BOOT-INF/classes/META-INF/build-info.properties`.
- [ ] Hiểu `build.group`, `build.artifact`, `build.name`, `build.version`, `build.time`.
- [ ] Biết `additionalProperties` tự thêm prefix `build.`.
- [ ] Biết `excludeInfoProperties`, `time=off` và `skip` có tác dụng gì.
- [ ] Phân biệt `build.time`, Git commit time và deployment time.
- [ ] Đọc metadata từ Java bằng `BuildProperties` hoặc Java `Properties`.
- [ ] Biết khi nào `BuildProperties` bean được auto-configure.
- [ ] Biết `/actuator/info` cần Actuator và HTTP exposure/authorization thích hợp.
- [ ] Không nhúng secrets vào file resources/public endpoints.
- [ ] Biết chỉnh `project.build.outputTimestamp` để kiểm soát timestamp.
- [ ] Đã xác nhận file được **đóng vào artifact triển khai thật**.
- [ ] Đã kiểm tra multi-module scope và không nhầm build metadata của library.
- [ ] Đã chạy test và xác minh stdout/HTTP của ví dụ Java 17.
- [ ] Có CI check cho build-info và release version của bản phát hành.

**Kết luận:** Maven goal `spring-boot:build-info` tạo **metadata có cấu trúc trong `META-INF/build-info.properties`** từ `MavenProject`. File được thêm vào ứng dụng khi Maven packaging/repackage chạy đúng lifecycle, và Spring Boot có thể đọc nó qua `BuildProperties` hoặc xuất qua Actuator info. Giá trị thực tế của tính năng này nằm ở việc **biết chính xác artifact đang chạy**; muốn đáng tin trong production, phải đi kèm chính sách timestamp, CI verification và bảo vệ thông tin nhạy cảm.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Maven Plugin: Integrating with Actuator / build-info Goal](https://docs.spring.io/spring-boot/3.5/maven-plugin/build-info.html)
- [Spring Boot 3.5 — How-to: Generate Build Information](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Spring Boot 3.5 — Actuator Endpoints and Application Information](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — BuildProperties Java API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/info/BuildProperties.html)
- [Spring Boot 3.5 — ProjectInfoAutoConfiguration Java API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/info/ProjectInfoAutoConfiguration.html)
- [Spring Boot 3.5 — Maven Plugin Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
