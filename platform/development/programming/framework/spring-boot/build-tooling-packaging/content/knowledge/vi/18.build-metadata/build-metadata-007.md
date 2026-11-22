# Kiểm tra metadata trong archive và quan hệ với Actuator info của Spring Boot

## 1. Tại sao phải kiểm tra metadata ở cả file đóng gói và ứng dụng đang chạy?

Khi phát hành một ứng dụng Spring Boot, nhóm phát triển thường muốn trả lời bốn câu hỏi:

1. **Đang chạy artifact nào?** Ví dụ `com.example:metadata-demo:0.1.0-SNAPSHOT`.
2. **Artifact được tạo từ Git commit nào?** Để liên hệ tiến trình đang chạy với source code, release và pipeline.
3. **Metadata có thật sự được ghi vào executable JAR/WAR hay không?** Cấu hình plugin build thành công không có nghĩa mọi file metadata đã nằm trong artifact mà máy chủ sử dụng.
4. **Spring Boot Actuator có công bố đúng thông tin đó tại `/actuator/info` không?** Endpoint phải được bật, được phơi bày qua HTTP và có các `InfoContributor` thích hợp.

Trong Spring Boot, các lớp dữ liệu liên quan nhưng **không đồng nhất** gồm:

- `META-INF/MANIFEST.MF`: metadata chuẩn của archive JAR/WAR; Spring Boot executable archive dùng các trường như `Main-Class` và `Start-Class`.
- `META-INF/build-info.properties`: thông tin **build-time** như group, artifact, name, version và thời điểm build; Spring Boot auto-configure `BuildProperties` khi tìm thấy trên classpath.
- `git.properties`: thông tin **Git source revision** như commit ID, branch và commit time; Spring Boot auto-configure `GitProperties` khi tìm thấy ở root classpath.
- **Actuator `info`**: endpoint tổng hợp dữ liệu từ các `InfoContributor`; mặc định `build` và `git` contributors được bật nếu metadata tồn tại, nhưng việc **expose endpoint qua HTTP** phải xét riêng.

Bài thực hành dùng **Spring Boot 3.5.x, Java 17**, Maven hoặc Gradle. Các plugin và cấu trúc được chọn để phù hợp ví dụ; một dự án dùng Spring Boot 4.x hoặc version cũ hơn cần đối chiếu tài liệu của chính version đó.

**Nguyên tắc kiểm tra:** nhìn vào **artifact thật được triển khai**, không chỉ POM/build script hoặc một endpoint từ process chạy ở IDE. Một JAR được tạo hôm qua có thể vẫn chứa commit/version cũ dù source và `pom.xml` hôm nay đã đổi.

## 2. Sơ đồ dữ liệu: build-time → archive → runtime → HTTP

```text
Git repository                       Maven / Gradle project
- HEAD commit                       - group / artifact / version
- branch                             - build time
        |                                      |
        v                                      v
Git metadata generator                Spring Boot build-info task/goal
        |                                      |
        v                                      v
git.properties                       META-INF/build-info.properties
        |                                      |
        +----------------+---------------------+
                         |
                         v
              processResources/classes
                         |
                         v
         Spring Boot executable JAR / WAR
         - BOOT-INF/classes/... (JAR)
         - WEB-INF/classes/...  (WAR)
                         |
             java -jar / deploy
                         |
                         v
            Spring application context
              |                   |
              v                   v
          GitProperties       BuildProperties
              |                   |
              v                   v
          GitInfoContributor  BuildInfoContributor
              +--------+----------+
                       |
                       v
                Actuator InfoEndpoint
                       |
             [HTTP exposure + security]
                       |
                       v
                  GET /actuator/info
```

Cần tách **ba điều kiện**:

**Điều kiện A — tạo metadata:** Gradle/Maven phải chạy task hoặc goal tạo file metadata. Chỉ áp dụng Spring Boot plugin không nhất thiết kích hoạt `build-info` nếu chưa khai báo.

**Điều kiện B — file hiện diện trên runtime classpath:** file phải được chép vào class output rồi được đóng gói vào JAR/WAR chạy thật. Nếu chạy nhầm `plain.jar` hoặc file từ module khác, Runtime không thấy metadata mong muốn.

**Điều kiện C — thông tin được công bố:** có dependency `spring-boot-starter-actuator`, các contributor không bị tắt, endpoint `info` có quyền truy cập và được expose qua kênh đang thử. Một file đúng trong JAR vẫn có thể dẫn tới HTTP 404 hoặc response `{}` nếu không đủ điều kiện runtime.

## 3. So sánh các dạng metadata và nơi lưu

| Nguồn | File/entry | Tác giả tạo | Spring Boot đọc như thế nào? | Thường dùng để |
|---|---|---|---|---|
| Manifest chuẩn | `META-INF/MANIFEST.MF` | Maven JAR/WAR, Gradle archive + Boot repackager | `java -jar` dùng `Main-Class`; Boot Loader dùng `Start-Class` | Kiểm tra launcher, main class, version manifest tùy build |
| Build info | `META-INF/build-info.properties` ở **classpath root** | Spring Boot Maven goal `build-info` hoặc Gradle task `bootBuildInfo` | Bean `BuildProperties` → `BuildInfoContributor` | Release/group/version/build timestamp |
| Git info | `git.properties` ở **classpath root** | Git Commit ID Maven plugin / Gradle Git Properties plugin | Bean `GitProperties` → `GitInfoContributor` | Truy vết source revision |
| `info.*` Spring properties | `application.properties` hoặc config ngoài | Developer/CI/runtime config | `EnvironmentInfoContributor`, **mặc định tắt trong Boot 3.5** | Thông tin vận hành tùy biến |
| Custom InfoContributor | Class Spring bean | Developer | Bean implementing `InfoContributor` | Metadata được lọc/tính toán riêng |
| Build version từ tên archive | `build/libs/app-0.1.0.jar` | Maven/Gradle naming | **Không** phải nguồn mặc định của `BuildProperties` | Nhìn nhanh tên file, không đủ làm bằng chứng runtime |

Đặc biệt, **Maven POM version không tự xuất hiện ở `/actuator/info`** chỉ nhờ có `pom.xml`. Spring Boot cần `META-INF/build-info.properties` hoặc một `InfoContributor` khác cung cấp thông tin tương ứng. Manifest và build-info cũng **không được bảo đảm đồng bộ** nếu pipeline tự chỉnh manifest, dùng archive cũ hoặc tạo metadata bằng một module khác.

## 4. Vị trí trong executable JAR và WAR

### 4.1. Executable JAR

Spring Boot executable JAR dùng Boot Loader, application classes và nested dependencies theo layout quen thuộc:

```text
metadata-demo-0.1.0-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/metadata/MetadataApplication.class
    │   ├── META-INF/build-info.properties
    │   ├── git.properties                 [nếu được sinh]
    │   └── application.properties
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-boot-actuator-*.jar
        └── ... dependencies
```

Đây là cây minh họa; tên JAR con, các file index và số lượng dependency thay đổi theo build. `META-INF/build-info.properties` về mặt **classpath** nằm ở root dưới `META-INF`; về mặt **ZIP entry** của Spring Boot executable JAR, nó thường nằm tại:

```text
BOOT-INF/classes/META-INF/build-info.properties
```

Tương tự, `git.properties` ở classpath root được đóng gói thành:

```text
BOOT-INF/classes/git.properties
```

**Không nhầm** `META-INF/MANIFEST.MF` ở root archive với `BOOT-INF/classes/META-INF/build-info.properties` nằm bên trong application classes. Hai file có mục đích và đường dẫn khác nhau.

### 4.2. Executable WAR

Khi project là Spring Boot executable WAR, class output dùng `WEB-INF/classes`:

```text
metadata-demo-0.1.0-SNAPSHOT.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/launch/WarLauncher.class
└── WEB-INF/
    ├── classes/
    │   ├── com/example/metadata/MetadataApplication.class
    │   ├── META-INF/build-info.properties
    │   └── git.properties                 [nếu được sinh]
    ├── lib/
    └── lib-provided/
```

Archive metadata vẫn được tìm trên **application classpath**: `WEB-INF/classes/META-INF/build-info.properties` và `WEB-INF/classes/git.properties` khi chạy theo layout WAR. `WEB-INF/lib-provided` dành cho provided dependencies khi Boot WAR được chạy bằng `java -jar`; nó không phải thư mục chứa build-info thông thường.

Khi WAR được deploy vào external servlet container, process startup và context path khác executable WAR; nhưng nếu file metadata nằm trên classpath của web application và Actuator được cấu hình hợp lệ, `BuildProperties`/`GitProperties` vẫn có thể được tạo. Hãy kiểm thử riêng đường triển khai thật.

### 4.3. Manifest chứa thông tin gì?

Manifest của executable JAR Boot 3.5 thường có:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.metadata.MetadataApplication
Spring-Boot-Version: 3.5.16
```

`Main-Class` là launcher mà `java -jar` gọi; `Start-Class` là Java main của ứng dụng. `Spring-Boot-Version` là version framework/plugin đóng gói, **không nhất thiết bằng version artifact ứng dụng**. Manifest còn có thể chứa `Implementation-Version` nếu build cấu hình, nhưng **Actuator build info không tự đọc arbitrary manifest attributes như nguồn `build.*`**.

Với Boot 3.2+, launcher package là `org.springframework.boot.loader.launch`. Nếu so sánh với một tài liệu Boot 2.x có package launcher cũ, hãy dùng **manifest của artifact hiện tại** làm bằng chứng, không lấy tên class cũ áp vào build mới.

## 5. Ví dụ chạy được: Spring Boot Java 17 với endpoint /actuator/info

Tạo project tên `metadata-demo` từ Spring Initializr, chọn **Java 17**, Spring Boot 3.5.x và dependency **Spring Web**, **Spring Boot Actuator**, **Spring Boot Starter Test**. Chọn **Maven hoặc Gradle**, không trộn hai build tools vào cùng một module chỉ để chạy bài học.

Cấu trúc source chung:

```text
metadata-demo/
├── pom.xml                   [nếu dùng Maven]
│   hoặc
├── settings.gradle           [nếu dùng Gradle Groovy]
├── build.gradle
├── src/main/java/com/example/metadata/
│   ├── MetadataApplication.java
│   └── VersionController.java
├── src/main/resources/application.properties
└── src/test/java/com/example/metadata/
    └── BuildMetadataTest.java
```

### 5.1. Spring Boot main class

`src/main/java/com/example/metadata/MetadataApplication.java`:

```java
package com.example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetadataApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }
}
```

### 5.2. Controller đọc BuildProperties

`src/main/java/com/example/metadata/VersionController.java`:

```java
package com.example.metadata;

import java.util.Map;
import org.springframework.boot.info.BuildProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {
    private final BuildProperties build;

    public VersionController(BuildProperties build) {
        this.build = build;
    }

    @GetMapping("/version")
    public Map<String, String> version() {
        return Map.of(
                "artifact", build.getArtifact(),
                "version", build.getVersion());
    }
}
```

Điểm cần hiểu: `BuildProperties` chỉ có sẵn khi Spring Boot tìm thấy file `META-INF/build-info.properties` hợp lệ trên runtime classpath. Controller này **cố tình yêu cầu bean**, để build thiếu metadata biểu hiện thành lỗi khởi động thay vì âm thầm trả version suy đoán.

Với project cần chạy ngay cả khi không có build-info (ví dụ chạy file Java riêng trước khi build), có thể tiêm `ObjectProvider<BuildProperties>` hoặc thiết kế fallback rõ ràng. **Không** thêm fallback giả `0.0.0` rồi gọi đó là version được đóng gói chính xác.

### 5.3. Cấu hình HTTP exposure

`src/main/resources/application.properties`:

```properties
spring.application.name=metadata-demo
server.port=8080

# Chỉ phơi bày health và info trong bài thực hành.
management.endpoints.web.exposure.include=health,info
```

Với Spring Boot 3.5, mặc định **chỉ health được expose qua HTTP**, vì vậy việc đặt `management.endpoints.web.exposure.include=health,info` là bước cần thiết để thử `GET /actuator/info`. Không cần đặt `management.info.build.enabled=true` trong ví dụ vì `build` contributor đã bật mặc định nếu có metadata. `management.info.git.enabled` cũng mặc định bật khi phù hợp.

Trong production, cần có chính sách bảo vệ endpoint; bài thực hành này không bật toàn bộ endpoint bằng `*` và không đưa secret vào info.

### 5.4. Kiểm thử BuildProperties

`src/test/java/com/example/metadata/BuildMetadataTest.java`:

```java
package com.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BuildMetadataTest {
    @Autowired
    private BuildProperties buildProperties;

    @Test
    void buildMetadataWasGenerated() {
        assertNotNull(buildProperties);
        assertEquals("metadata-demo", buildProperties.getArtifact());
        assertEquals("0.1.0-SNAPSHOT", buildProperties.getVersion());
    }
}
```

Test này **không kiểm tra** Git info và không cần cổng HTTP để chạy. Nó kiểm chứng rằng build đã cung cấp file metadata trên test runtime classpath và Spring tạo được `BuildProperties`. Nếu dự án thay đổi `group`, `artifactId` hoặc version, cần cập nhật expected values/thiết kế assertions theo yêu cầu release; không commit test với version cứng khi pipeline liên tục override version.

JUnit Jupiter test chạy được khi `spring-boot-starter-test` ở test classpath, goal/task sinh build-info được nối đúng và Maven/Gradle test resource processing đã thực thi.

## 6. Maven: tạo build-info.properties và executable JAR

### 6.1. POM đầy đủ cho ví dụ

`pom.xml` (kế thừa Spring Boot starter parent):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>metadata-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <name>Metadata Demo</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Trong project kế thừa `spring-boot-starter-parent`, Spring Boot Maven Plugin có cấu hình version và goal `repackage` được quản lý theo parent. Execution `build-info` ở trên là **phần bạn thêm** để sinh metadata. Goal này thường gắn vào phase `generate-resources`; output mặc định là:

```text
target/classes/META-INF/build-info.properties
```

**Không cần tạo file `src/main/resources/META-INF/build-info.properties` thủ công** nếu plugin đã sinh. Để pipeline kiểm soát build version, thay `<version>` hoặc build properties theo cơ chế Maven hợp lệ, không chỉnh trực tiếp file generated trong `target/classes` sau packaging.

### 6.2. Build, xem file và chạy

Sau khi có Maven Wrapper hợp lệ từ Spring Initializr:

```bash
./mvnw clean verify
java -jar target/metadata-demo-0.1.0-SNAPSHOT.jar
```

Trên Windows: `mvnw.cmd clean verify` và `java -jar target/metadata-demo-0.1.0-SNAPSHOT.jar`. `verify` chạy lifecycle đến kiểm tra và tạo JAR từ `package`; plugin `build-info` đã chạy trước compile/test theo execution của goal.

Trong terminal thứ hai:

```bash
curl -s http://localhost:8080/version
curl -s http://localhost:8080/actuator/info
```

Với example POM/source, `/version` có JSON object chứa cặp:

```json
{
  "artifact": "metadata-demo",
  "version": "0.1.0-SNAPSHOT"
}
```

Thứ tự các khóa JSON **không được bảo đảm**. `/actuator/info` có `build` section; nó có thể kèm `time` tùy plugin/config, và `git` chỉ xuất hiện khi có Git metadata. Không chép cứng timestamp từ một build khác vào expected output.

### 6.3. Maven goal không tự chạy chỉ vì plugin được khai báo

Phân biệt:

- `spring-boot:repackage`: tạo executable archive.
- `spring-boot:build-info`: tạo `META-INF/build-info.properties`.
- `spring-boot:run`: chạy application từ classes/development classpath.
- `mvn package`/`verify`: thực thi các goal **đã được bind** vào lifecycle.

Nếu chỉ khai báo Spring Boot Maven Plugin mà **không thêm execution `build-info`**, đừng mặc định output build-info sẽ có. Nếu chạy một plugin goal thủ công rồi đóng gói lại bằng pipeline khác, hãy kiểm tra liệu file generated có thực sự đi vào JAR sau cùng không.

### 6.4. Thêm thông tin build tùy chọn

Trong `<execution>` của `spring-boot-maven-plugin`, thêm `<configuration>` khi cần:

```xml
<configuration>
    <additionalProperties>
        <release.channel>training</release.channel>
        <java.version>${java.version}</java.version>
    </additionalProperties>
</configuration>
```

Đây là **fragment**, không phải plugin hoặc POM hoàn chỉnh. Các thuộc tính bổ sung được prefix `build.` khi ghi xuống `build-info.properties`, ví dụ `build.release.channel=training`. Không đặt password, token, internal URL nhạy cảm vào additionalProperties vì file đó có thể được đưa vào artifact và công bố ra info.

**Chú ý cấu hình lồng nhau:** nếu goal `build-info` nằm trong một execution và bạn cần áp riêng cho nó, đặt `<configuration>` trong đúng execution tương ứng; không tạo hai executions phát sinh file cùng vị trí mà không kiểm soát.

## 7. Gradle: sinh metadata bằng bootBuildInfo

### 7.1. Groovy DSL — dự án hoàn chỉnh

`settings.gradle`:

```groovy
rootProject.name = 'metadata-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'
description = 'Metadata Demo'

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    buildInfo()
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`springBoot { buildInfo() }` cấu hình task **`bootBuildInfo`**. Theo tài liệu Spring Boot 3.5, task tạo `META-INF/build-info.properties` cho **main source set** và được nối để resource hiện diện trên classpath. Thông tin mặc định gồm `build.artifact`, `build.group`, `build.name`, `build.version` và `build.time`.

Lệnh:

```bash
./gradlew clean test bootJar
java -jar build/libs/metadata-demo-0.1.0-SNAPSHOT.jar
```

Với `bootJar`, output executable archive nằm trong `build/libs` (trừ khi đổi `archiveFileName`). File generated có thể xem tại output của `bootBuildInfo`/main resources, nhưng **phải kiểm tra archive thật** vì task output location có thể được plugin thay đổi qua các version.

**Đừng tự tạo task `processResources.dependsOn bootBuildInfo` bằng cách đoán** nếu `springBoot.buildInfo()` của plugin đã tích hợp đúng. Trùng dependency đôi khi không gây lỗi nhưng làm build script khó hiểu và dễ tạo cycle khi người phát triển thay cấu hình.

### 7.2. Kotlin DSL tương đương

`settings.gradle.kts`:

```kotlin
rootProject.name = "metadata-demo"
```

`build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"
description = "Metadata Demo"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

springBoot {
    buildInfo()
}

tasks.test {
    useJUnitPlatform()
}
```

Các file Java/test giống mục 5; đừng copy cú pháp Groovy `implementation '...'` vào `build.gradle.kts`. Với project multi-module, chỉ cần task `bootBuildInfo` tại các module ứng dụng cần metadata; không mặc định mọi library phải công bố `/actuator/info`.

### 7.3. Tùy chỉnh hoặc bỏ build.time để hỗ trợ repeatable build

**Vấn đề:** Theo tài liệu Gradle plugin của Spring Boot 3.5, giá trị `build.time` mặc định là thời điểm build, khiến output của task thay đổi ở những lần chạy khác nhau và có thể làm task `bootBuildInfo` **không up-to-date**. Điều này làm tăng công việc downstream, giảm tính tái lập artifact.

Nếu nhóm coi tính tái lập và tốc độ quan trọng hơn việc mỗi artifact có timestamp runtime do task đặt, có thể **loại bỏ field time**:

```groovy
// Phần thay thế cho springBoot { buildInfo() } trong build.gradle.
springBoot {
    buildInfo {
        excludes = ['time']
        properties {
            additional = [
                'release.channel': 'training'
            ]
        }
    }
}
```

Kotlin DSL:

```kotlin
// Phần thay thế cho springBoot { buildInfo() } trong build.gradle.kts.
springBoot {
    buildInfo {
        excludes.set(setOf("time"))
        properties {
            additional.set(mapOf("release.channel" to "training"))
        }
    }
}
```

Đây là những **biến thể lựa chọn**; không đặt đồng thời nhiều `springBoot.buildInfo` block mâu thuẫn với nhau trong project thật. Khi bỏ time, `/actuator/info` không còn hiển thị `build.time`; CI vẫn có thể ghi release time ở hệ thống deployment/release riêng.

Với Maven, goal `build-info` có tùy chọn `time` và `excludeInfoProperties`. Theo tài liệu Boot 3.5, đặt `<time>off</time>` trong configuration của goal hoặc loại field `time` là cách chủ động không ghi `build.time`. Không tự dùng một timestamp giả để đánh lừa khả năng truy vết.

## 8. Git revision: sinh git.properties khác với build-info

### 8.1. Git metadata trả lời câu hỏi khác

`build-info.properties` mô tả **project artifact**: group, artifact, name, version, time. `git.properties` mô tả **trạng thái Git khi build**: commit, branch, commit time, và có thể có thêm các trường do plugin cung cấp.

Ví dụ file `git.properties` ở root classpath:

```properties
git.branch=main
git.commit.id=0123456789abcdef0123456789abcdef01234567
git.commit.time=2026-10-01T07:30:00+0000
```

Các giá trị trong ví dụ là **dữ liệu minh họa**, không phải commit thực tế của project. Nhiều plugin còn ghi commit abbreviated ID, tags, build user, build host hoặc remote URL; phải kiểm soát trường nào được đưa vào artifact.

Spring Boot 3.5 `GitProperties` được auto-configure nếu file `git.properties` có trên classpath. `GitInfoContributor` chỉ hiển thị một tập nhỏ trường như branch, commit ID và commit time theo mặc định (nếu có).

### 8.2. Maven Git Commit ID plugin

Nếu project kế thừa `spring-boot-starter-parent`, tài liệu Spring Boot 3.5 cho biết parent đã quản lý cấu hình của Git Commit ID Maven Plugin. Để bật tạo Git metadata, **thêm plugin vào `<build><plugins>` trong POM ví dụ**:

```xml
<plugin>
    <groupId>io.github.git-commit-id</groupId>
    <artifactId>git-commit-id-maven-plugin</artifactId>
</plugin>
```

Đây là **plugin bổ sung**, không phải dependency trong `<dependencies>` và không phải nguyên POM. Parent Boot cung cấp version/config mặc định; nếu dùng corporate parent khác, cần khai báo version và execution tạo `git.properties` phù hợp tài liệu plugin. Kết quả thường nằm ở:

```text
target/classes/git.properties
```

**Không có `.git` hoặc không có thông tin commit?** Nhiều CI checkout từ source archive, shallow clone/detached HEAD hoặc snapshot không có Git metadata đầy đủ; cần cấu hình plugin phù hợp hoặc cấp thông tin revision từ CI, không tự suy diễn commit. Sau khi thêm plugin, chạy **build mới** rồi kiểm tra file thay vì chỉ đọc Git history ở workspace.

### 8.3. Gradle Git Properties plugin

Trong phần `plugins { ... }` của `build.gradle` ở mục 7, thêm:

```groovy
id 'com.gorylenko.gradle-git-properties' version '2.4.1'
```

Nếu dùng Kotlin DSL:

```kotlin
id("com.gorylenko.gradle-git-properties") version "2.4.1"
```

Đây là version **được tài liệu Spring Boot 3.5 dùng làm ví dụ**, không phải tuyên bố phiên bản mới nhất tại mọi thời điểm. Plugin cung cấp task sinh `git.properties` khi build, thường là `generateGitProperties`; kiểm tra `./gradlew tasks --all` và log task của version đang dùng. Spring Boot sẽ đọc file nếu output được nối đúng vào runtime classpath.

Trong repository nhiều module, chỉ module có plugin/config cần thiết mới sinh file. Nếu root và submodule trỏ các Git directories khác nhau hoặc build từ source archive, cần xem plugin config thay vì giả định `git.properties` xuất hiện ở mọi module.

## 9. Actuator /info: contributor, endpoint và exposure là ba quyết định riêng

### 9.1. Các contributor có sẵn trong Spring Boot 3.5

| Contributor | Điều kiện tạo | Mặc định trong 3.5 |
|---|---|---|
| `BuildInfoContributor` | `META-INF/build-info.properties` → `BuildProperties` | **Enabled** khi có metadata |
| `GitInfoContributor` | `git.properties` → `GitProperties` | **Enabled** khi có metadata |
| `EnvironmentInfoContributor` | Spring `info.*` properties | **Disabled** mặc định |
| `JavaInfoContributor` | JVM đang chạy | **Disabled** mặc định |
| `OsInfoContributor` | Operating system | **Disabled** mặc định |
| `ProcessInfoContributor` | Process runtime | **Disabled** mặc định |

Ví dụ chỉ muốn build và Git metadata:

```properties
management.endpoints.web.exposure.include=health,info

# Không bắt buộc, do hai contributor đã bật mặc định:
management.info.build.enabled=true
management.info.git.enabled=true
```

Đây là **minh họa cơ chế**. Trong bản nguồn ở mục 5 đã có dòng exposure; không cần thêm cả hai dòng true chỉ để ép file sinh ra, vì contributor **không tự tạo metadata file**.

Muốn thêm thông tin thủ công qua Spring Environment:

```properties
management.info.env.enabled=true
info.app.owner=training
info.app.runtime=java17
```

Khi bật `env` contributor, nhóm `info.*` properties được công bố ở endpoint; **đừng đặt secret** dưới key `info.*`. Nếu chỉ thêm `info.app.owner` mà không bật `management.info.env.enabled=true`, theo mặc định Boot 3.5, response có thể **không** có phần tương ứng.

### 9.2. JSON ví dụ hợp lệ

Sau Maven/Gradle build đúng và chạy executable JAR:

```bash
curl -s http://localhost:8080/actuator/info
```

Một response **minh họa khi chỉ có build-info và không có git.properties**:

```json
{
  "build": {
    "artifact": "metadata-demo",
    "name": "Metadata Demo",
    "group": "com.example",
    "version": "0.1.0-SNAPSHOT",
    "time": "2026-10-01T07:30:00Z"
  }
}
```

Timestamp chỉ minh họa; có thể khác hoặc vắng nếu cấu hình `time=off`/`excludes=['time']`. JSON field order cũng không bảo đảm. Trường `name` của Gradle có thể dựa trên project name thay vì `description` theo cấu hình mặc định; đừng buộc output Maven và Gradle phải có cùng `build.name` nếu chưa cấu hình tương đương.

Nếu thêm Git plugin và file hợp lệ, response có thể có thêm:

```json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": "0123456",
      "time": "2026-10-01T07:30:00Z"
    }
  }
}
```

Đây là **phần `git` minh họa**, không phải response JSON thứ hai bắt buộc. `git.commit.id` có thể được rút gọn trong mode mặc định; nhánh có thể thay đổi theo môi trường CI. Kiểm tra bằng `git rev-parse HEAD` trong build workspace rồi so với file trong JAR; đừng kết luận sai chỉ vì endpoint hiển thị ID ngắn.

### 9.3. Vì sao mặc định GET /actuator/info có thể trả 404?

Trong Spring Boot 3.5, **chỉ `health` được expose qua HTTP mặc định**. Kể cả khi có bean `BuildProperties` và `BuildInfoContributor`, nếu chưa thêm `info` vào `management.endpoints.web.exposure.include`, endpoint chưa được expose qua HTTP.

Với Spring Security (nếu được thêm vào project), có thể nhận `401 Unauthorized` hoặc `403 Forbidden` tùy authentication/authorization. Hai status này khác hoàn toàn `404` do không expose hoặc không tạo endpoint. Nếu nhóm định expose info cho hệ thống nội bộ, hãy cấu hình security riêng (ví dụ role phù hợp), firewall hoặc API gateway, và không đưa thông tin nhạy cảm vào response.

**Không đặt `management.endpoints.web.exposure.include=*` trong production chỉ để giải quyết một lỗi 404**; hãy expose đúng endpoint cần và kiểm soát quyền truy cập.

## 10. Kiểm tra metadata trực tiếp trong archive bằng JDK và công cụ ZIP

### 10.1. Liệt kê entry archive

Maven:

```bash
./mvnw clean package
jar tf target/metadata-demo-0.1.0-SNAPSHOT.jar
```

Gradle:

```bash
./gradlew clean bootJar
jar tf build/libs/metadata-demo-0.1.0-SNAPSHOT.jar
```

Tìm các đường dẫn:

```text
META-INF/MANIFEST.MF
BOOT-INF/classes/META-INF/build-info.properties
BOOT-INF/classes/git.properties                    (nếu có plugin Git)
BOOT-INF/classes/com/example/metadata/MetadataApplication.class
```

**Đừng nhầm plain JAR với bootJar**. Với Gradle một số build có thể tạo cả `metadata-demo-...-plain.jar` và executable JAR; chỉ executable JAR có layout `BOOT-INF` như trên. Với Maven, goal `repackage` có thể thay thế artifact chính và giữ original file với hậu tố khác nếu cấu hình plugin. Luôn chọn đúng artifact mà CI publish/deploy.

### 10.2. Đọc nội dung bằng unzip

Trên Linux/macOS hoặc môi trường có `unzip`:

```bash
# Dùng đúng file do Maven sinh.
unzip -p target/metadata-demo-0.1.0-SNAPSHOT.jar META-INF/MANIFEST.MF
unzip -p target/metadata-demo-0.1.0-SNAPSHOT.jar \
    BOOT-INF/classes/META-INF/build-info.properties

# Nếu có git.properties:
unzip -p target/metadata-demo-0.1.0-SNAPSHOT.jar \
    BOOT-INF/classes/git.properties
```

Với Gradle, thay đường dẫn file thành `build/libs/metadata-demo-0.1.0-SNAPSHOT.jar`. Các lệnh `unzip -p` đọc **nội dung** entry mà không giải nén nguyên archive. Trên Windows, có thể dùng công cụ ZIP hoặc chương trình Java `JarFile` ở mục 11 để tránh phụ thuộc `unzip`.

Ví dụ build-info (file content mẫu):

```properties
build.artifact=metadata-demo
build.group=com.example
build.name=Metadata Demo
build.version=0.1.0-SNAPSHOT
build.time=2026-10-01T07:30:00Z
```

Không mong cả Maven lẫn Gradle sinh đúng thứ tự key hoặc cùng timestamp. Nếu bản Maven/Gradle đã loại `build.time`, việc thiếu field đó là **có chủ đích**, không phải lỗi.

### 10.3. Kiểm tra trước khi khởi động ứng dụng

Bạn có thể kiểm tra metadata **mà không chạy** Spring Boot bằng `jar tf`/`unzip -p`. Điều này đặc biệt hữu ích trong CI để xác minh artifact trước khi publish. Nhưng kiểm tra file hiện diện vẫn chưa chứng minh endpoint `/actuator/info` được expose hoặc đúng security config; phần runtime cần smoke test riêng.

## 11. Công cụ Java 17 độc lập để đọc manifest và metadata của JAR/WAR

Nếu không có `unzip`, dùng Java Standard Library và JDK 17. Tạo file **`InspectBootArchive.java`** ở thư mục độc lập ngoài source app:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Properties;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class InspectBootArchive {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java InspectBootArchive <archive.jar-or-war>");
            System.exit(2);
        }

        try (JarFile archive = new JarFile(args[0])) {
            Manifest manifest = archive.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("Missing manifest");
            }

            System.out.println("Main-Class="
                    + manifest.getMainAttributes().getValue("Main-Class"));
            System.out.println("Start-Class="
                    + manifest.getMainAttributes().getValue("Start-Class"));

            // Kiểm tra hai layout executable JAR và executable WAR.
            show(archive, "BOOT-INF/classes/META-INF/build-info.properties");
            show(archive, "BOOT-INF/classes/git.properties");
            show(archive, "WEB-INF/classes/META-INF/build-info.properties");
            show(archive, "WEB-INF/classes/git.properties");
        }
    }

    private static void show(JarFile archive, String name)
            throws IOException {
        JarEntry entry = archive.getJarEntry(name);
        if (entry == null) {
            System.out.println(name + " -> absent");
            return;
        }

        System.out.println(name + " -> present");
        Properties properties = new Properties();
        try (InputStream stream = archive.getInputStream(entry)) {
            properties.load(stream);
        }
        List<String> keys = new ArrayList<>(properties.stringPropertyNames());
        Collections.sort(keys);
        for (String key : keys) {
            System.out.println("  " + key + "=" + properties.getProperty(key));
        }
    }
}
```

Biên dịch/chạy (ví dụ với Maven artifact):

```bash
javac --release 17 -encoding UTF-8 InspectBootArchive.java
java InspectBootArchive target/metadata-demo-0.1.0-SNAPSHOT.jar
```

Chương trình này **không cần Spring dependency**, chỉ dùng `java.util.jar` và `java.util.Properties`. Nếu artifact Maven của mục 6 đã có build-info và **chưa thêm Git plugin**, những dòng trạng thái chính kỳ vọng là:

```text
Main-Class=org.springframework.boot.loader.launch.JarLauncher
Start-Class=com.example.metadata.MetadataApplication
BOOT-INF/classes/META-INF/build-info.properties -> present
BOOT-INF/classes/git.properties -> absent
WEB-INF/classes/META-INF/build-info.properties -> absent
WEB-INF/classes/git.properties -> absent
```

**Chú ý:** giữa các dòng trạng thái còn có những dòng `build.artifact=...`, `build.group=...` và các property khác do chương trình in sau `present`; đoạn trên chỉ là **các dòng được chọn** để tập trung vào vị trí, không phải stdout nguyên xi liên tiếp. Nếu chọn executable WAR, vị trí `WEB-INF/classes` đổi thành `present` và vị trí `BOOT-INF/classes` thường `absent`.

API `Properties.load(InputStream)` theo quy ước Java properties sử dụng ISO-8859-1 và Unicode escapes; nếu metadata có Unicode được ghi theo một quy ước khác, việc đọc Java properties cần dùng encoding phù hợp. Với các key/giá trị ASCII trong ví dụ, chương trình cho ra dữ liệu chính xác.

## 12. Test runtime: đối chiếu artifact với /actuator/info

### 12.1. Quy trình đối chiếu từng tầng

**Tầng 1 — build output**: xác nhận task/goal chạy và file xuất hiện dưới output classes/resources của module ứng dụng.

**Tầng 2 — executable artifact**: xem `BOOT-INF/classes/META-INF/build-info.properties` và `git.properties` (nếu có) trong JAR; với WAR xem `WEB-INF/classes`.

**Tầng 3 — startup**: chạy `java -jar` trên **đúng file đã kiểm tra**; tránh để IDE hoặc `bootRun` khởi động bản classes khác. Nếu controller `VersionController` tiêm `BuildProperties` thành công và trả artifact/version, bean đã có.

**Tầng 4 — Actuator endpoint**: gửi `GET /actuator/info` theo đúng cổng/management base path và quyền truy cập; so sánh `build.artifact` và `build.version` với file đã đóng gói.

**Tầng 5 — provenance**: nếu có Git metadata, so sánh commit ID với CI build revision/source tag. Nếu CI dùng detached HEAD, branch có thể không giống branch nguồn được merge nhưng commit ID mới là tín hiệu mạnh hơn cho provenance.

**Không nên** lấy `git rev-parse HEAD` trên laptop hôm nay để xác minh JAR được build hôm qua từ CI khác; hãy dùng revision mà CI đã checkout **tại thời điểm build artifact**.

### 12.2. HTTP status và nội dung cần phân biệt

| Kết quả khi gọi /actuator/info | Giải thích khả dĩ | Kiểm tra tiếp |
|---|---|---|
| `200`, JSON có `build` | Endpoint expose, build contributor có metadata | So khớp fields với JAR đúng version |
| `200`, JSON có `build` nhưng không có `git` | Chưa có `git.properties`, Git contributor tắt hoặc metadata không hợp lệ | Inspect `git.properties`, plugin Git và `management.info.git.enabled` |
| `200`, JSON `{}` | Endpoint hoạt động nhưng không contributor nào đóng góp thông tin | Xem classpath metadata, `management.info.*.enabled` và Spring context |
| `404` | Endpoint chưa expose/tạo hoặc sai URL/path/port | Kiểm tra `management.endpoints.web.exposure.include` và endpoint enablement |
| `401`/`403` | Spring Security hoặc gateway không cho phép truy cập | Dùng authentication/authorization hợp lệ, không mở toàn bộ actuator |
| Kết nối bị từ chối | Process chưa chạy, sai port/container routing | Kiểm tra app logs, `server.port`, `management.server.port` |
| `200` nhưng version cũ | Chạy artifact cũ, container image cũ, CI không rebuild hoặc cache/deploy nhầm | So manifest/JAR checksum, image digest và build-info bên trong |
| `build.time` khác kỳ vọng | Time plugin theo build instant hoặc outputTimestamp; time đã loại | Kiểm tra task/goal config, không quy ngay thành deploy time |

### 12.3. Build metadata không phải runtime metadata

- `build.version`: version tại **lúc build**, không tự đổi khi JVM chạy lâu.
- `build.time`: thời điểm build/giá trị do plugin tạo, **không phải** thời điểm deploy hoặc khởi động JVM.
- `git.commit.time`: thời điểm của commit theo metadata Git, **không phải** timestamp của image/container đang chạy.
- `java.version` hoặc `os.name` từ **runtime contributors**: thông tin JVM/OS mà ứng dụng **đang chạy**, nếu bật contributors tương ứng.

Khi điều tra incident, nên ghi đồng thời **application version, Git commit, artifact checksum/image digest, deployment ID và runtime environment**. Chỉ một `build.version` có thể bị trùng khi nhiều bản `SNAPSHOT` cùng tên được build khác nhau.

## 13. Tính tái lập build: build.time, Git và checksum artifact

### 13.1. Timestamp có thể làm build khác nhau

Nếu `build.time` được tạo mới mỗi lần, hai build từ cùng source/dependencies có thể tạo bytes khác nhau. Với Gradle, tài liệu Spring Boot 3.5 chỉ rõ task `bootBuildInfo` dùng current build time mặc định, khiến task không up-to-date và artifact kém tái lập. Nếu tổ chức ưu tiên reproducible builds, hãy cân nhắc bỏ `time` hoặc đặt timestamp ổn định từ hệ thống build.

Với Maven, goal `build-info` có tham số `time` và liên quan `project.build.outputTimestamp`; có thể đặt `<time>off</time>` để bỏ field time. Nếu plugin khác cũng tạo timestamps, archive entries, file generated hoặc resource filtering có nội dung không ổn định, chỉ bỏ `build.time` **chưa đủ** để bảo đảm byte-for-byte reproducibility.

### 13.2. Git properties và tính tái lập

Nếu plugin Git sinh build user, host, branch hoặc build time thay đổi, metadata có thể khác dù commit giống nhau. Cân nhắc giới hạn output vào **commit ID và commit time**/những trường thật sự cần. CI với shallow clone có thể không truy xuất được tags hoặc thông tin branch đầy đủ.

Giữ Git commit ID trong metadata thường tăng tính truy vết nhưng **không phải bằng chứng ký số**. Để có provenance mạnh, có thể kết hợp artifact checksum, SBOM, chữ ký và attestation của pipeline; đây là những cơ chế tách biệt với Actuator info.

### 13.3. Đừng nhầm hash của source và hash của artifact

`git.commit.id` là hash của Git commit/tree metadata, không phải SHA-256 của executable JAR. Một commit có thể tạo nhiều artifact khác nhau nếu dependency/plugin/JDK/input môi trường thay đổi. Nếu tổ chức cần đối chiếu “đúng file đã được phê duyệt”, pipeline nên lưu checksum hoặc image digest của artifact sau build.

Không tính checksum của JAR rồi ghi lại vào **chính JAR đó** mà không thiết kế quy trình ổn định: nội dung file thay đổi làm checksum thay đổi, tạo vòng lặp. Lưu artifact digest ở artifact repository hoặc metadata phát hành bên ngoài.

## 14. Security: /actuator/info không nên trở thành kho tiết lộ hệ thống

Ngay cả khi `/actuator/info` chỉ có vài field, dữ liệu vẫn giúp người xem xác định phiên bản sản phẩm, commit, branch và thời gian phát hành. Với production, hãy quyết định **ai được phép truy cập** theo chính sách tổ chức.

- Chỉ expose những endpoint cần: `management.endpoints.web.exposure.include=health,info` hoặc thậm chí chỉ `health` nếu không dùng info.
- Với Spring Security, bảo vệ info bằng authentication/authorization phù hợp; nếu khai báo `SecurityFilterChain` riêng, phải đánh giá lại toàn bộ actuator rules vì auto-configuration mặc định có thể back off.
- Đặt Actuator sau network policy, firewall, service mesh hoặc internal gateway khi thích hợp; không tin rằng ẩn URL là biện pháp bảo vệ.
- Không cấu hình `management.info.git.mode=full` cho môi trường công khai nếu Git metadata có remote URL, build user hoặc nhánh nội bộ.
- Không đưa token, secret, internal endpoint URL, credentials, customer data vào `build-info.properties`, `git.properties`, `info.*` hoặc custom `InfoContributor`.
- Dùng allowlist fields để kiểm soát dữ liệu công bố. Không chỉ dựa vào việc Actuator có sanitization ở **những endpoint khác** như env/configprops.

**Cần phân biệt:** một thông tin đã bị tắt trong `GitInfoContributor` vẫn có thể **nằm nguyên trong file git.properties ở JAR** nếu plugin đã tạo. Quyền xem archive và quyền gọi endpoint là hai bề mặt rủi ro khác nhau. Giảm dữ liệu sinh ra từ build mới bảo vệ cả hai.

## 15. Trong multi-module: metadata thuộc đúng module ứng dụng

Giả sử Maven reactor hoặc Gradle multi-project:

```text
platform/
├── shared-domain/          (library JAR)
├── orders-api/             (Spring Boot executable JAR)
└── reporting-worker/       (Spring Boot executable JAR)
```

Mỗi module có thể có tọa độ/version và nhiệm vụ riêng. Nếu root aggregator cấu hình `build-info` plugin execution được kế thừa **ở mọi module**, cả thư viện dùng chung có thể tạo `META-INF/build-info.properties` và đóng gói cùng app. Điều này làm classpath chứa **nhiều build-info.properties trùng đường dẫn**, khiến Spring chọn một file không phải metadata của executable app trong tình huống nhất định.

Nguyên tắc:

1. Sinh build-info **ở module tạo executable artifact**, thường là `orders-api`/`reporting-worker`.
2. Với Maven parent, quản lý plugin version trong `pluginManagement` nếu cần nhưng áp dụng goal ở module app; kiểm tra `inherited` của execution.
3. Với Gradle, dùng `springBoot { buildInfo() }` tại module app, không bật ồ ạt trong library nếu không cần.
4. Kiểm tra dependency JAR mà app đưa vào `BOOT-INF/lib` không chứa một resource metadata trùng tên có thể gây ambiguity.
5. CI build module mục tiêu rồi inspect **đúng archive**; với Maven `-pl :orders-api -am package`, với Gradle `:orders-api:bootJar`.
6. Nếu có nhiều app cùng chung parent và version, đừng đánh đồng `build.name` của root với `build.artifact` của app; xác minh field từ từng archive.

**Giới hạn:** đây là rủi ro thiết kế classpath, không phải khẳng định mọi project có hai metadata resources chắc chắn sai. Nhưng metadata để truy vết production phải **không mơ hồ**, nên tốt nhất tránh tài nguyên build-info trùng lặp giữa application và library.

## 16. Thử nghiệm có kiểm soát: thiếu, đúng và bị tắt metadata

Dùng project mục 5 và **một build tool**.

### Lượt A — Có build-info, không Git plugin

1. Giữ goal Maven `build-info` hoặc Gradle `springBoot.buildInfo()`.
2. Build package/bootJar mới và kiểm tra `META-INF/build-info.properties` trong archive.
3. Chạy executable JAR và gọi `/actuator/info`.
4. Kỳ vọng có `build.artifact` và `build.version`; `git` vắng mặt vì chưa tạo `git.properties`.
5. Controller `/version` cũng trả artifact/version từ `BuildProperties`.

### Lượt B — Thêm Git plugin

1. Thêm Git Commit ID Maven Plugin hoặc Gradle Git Properties Plugin như mục 8.
2. Build lại trong checkout có `.git` hợp lệ.
3. Kiểm tra `git.properties` nằm tại root classpath của executable archive.
4. Khởi động lại **JAR mới**, gọi `/actuator/info`. Kỳ vọng thêm `git` section nếu plugin tạo dữ liệu và Git contributor enabled.
5. Đối chiếu commit ID với revision CI đã checkout.

### Lượt C — Có metadata nhưng không expose info

1. Giữ metadata file nguyên vẹn.
2. Bỏ `info` khỏi `management.endpoints.web.exposure.include`, hoặc đặt `management.endpoints.web.exposure.include=health`.
3. Khởi động lại app rồi gọi `/actuator/info`; theo cấu hình mặc định, endpoint không được expose qua HTTP.
4. Khôi phục `health,info` sau thí nghiệm. Kết luận: file và contributor không đủ nếu HTTP exposure chưa được bật.

### Lượt D — Tắt contributor build nhưng vẫn giữ file

Trong `application.properties` thêm:

```properties
management.info.build.enabled=false
```

Khởi động lại app. `BuildProperties` có thể vẫn tồn tại vì file build-info hợp lệ; nhưng `BuildInfoContributor` bị tắt, nên response `/actuator/info` không còn `build` section do contributor này cung cấp. Controller `/version` vẫn có thể lấy version từ `BuildProperties`. **Kết luận:** metadata bean và HTTP info presentation là hai lớp khác nhau.

Sau thử nghiệm, xóa dòng `management.info.build.enabled=false` nếu muốn công bố build info. Đừng để cấu hình thí nghiệm thành behavior production ngoài ý muốn.

### Lượt E — Bỏ sinh build-info

Ở **bản sao hoặc nhánh thử nghiệm**, bỏ execution Maven build-info hoặc `springBoot { buildInfo() }`, clean rồi build mới. File `build-info.properties` sẽ không được tạo bởi các task này. Với source `VersionController` đang inject `BuildProperties` bắt buộc, app có thể **không khởi động được**, hoặc test `BuildMetadataTest` fail vì thiếu bean. Đây là fail có chủ đích minh họa dependency của ứng dụng vào build metadata.

Khôi phục cấu hình build-info rồi build lại. Không kết luận plugin hỏng nếu file cũ từ một lần build trước vô tình còn trong class output vì không clean; đó là lý do thí nghiệm dùng clean build.

## 17. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `jar tf` không thấy `BOOT-INF/classes/META-INF/build-info.properties` | Chưa chạy goal/task sinh file, đóng gói nhầm JAR | Kiểm tra Maven `build-info` execution/Gradle `bootBuildInfo` và artifact thực tế |
| Có build-info ở `target/classes` nhưng không có trong JAR | Repackage/resource layout sai, archive cũ hoặc file bị exclude | Build sạch, inspect `BOOT-INF/classes`, kiểm tra packaging |
| `/actuator/info` trả 404 | Chưa expose `info` qua HTTP hoặc sai base path/port | Đặt `management.endpoints.web.exposure.include=health,info` và kiểm tra management port/path |
| `/actuator/info` trả 401/403 | Spring Security/gateway hạn chế | Cấp quyền phù hợp, đừng disable bảo mật |
| HTTP 200 nhưng `{}` | Không có contributor đóng góp hoặc bị tắt | Xem file classpath và `management.info.*.enabled` |
| Có `build` nhưng thiếu `git` | Chưa tạo `git.properties` hoặc contributor Git tắt | Bật Git plugin, xác minh file/`management.info.git.enabled` |
| `build.version` là version của parent/library | Metadata của sai module hoặc artifact đang chạy sai | Đặt task sinh ở app module và inspect đúng artifact |
| `build.time` thay đổi mỗi lần build | Plugin dùng timestamp build | Cân nhắc bỏ `time` nếu cần repeatability |
| Không có `build.time` | Đã đặt Maven `time=off` hoặc Gradle `excludes=['time']` | Xác nhận chính sách, không coi mọi trường hợp là lỗi |
| `git.branch` là `HEAD` hoặc vắng | CI detached HEAD/shallow checkout | Dựa commit ID và thông tin CI revision phù hợp |
| Git commit ở endpoint khác local HEAD | Build từ một commit khác hoặc artifact cũ | So với source revision của build pipeline, không so bừa với workspace hiện tại |
| `BuildProperties` không được inject | File build-info không trên classpath hoặc auto-config bị thay đổi | Kiểm tra entry/execution/test runtime classpath |
| `info.app.*` không hiển thị | EnvironmentInfoContributor mặc định tắt | Đặt `management.info.env.enabled=true` nếu dữ liệu an toàn |
| Artifact có Git metadata chứa secret | Git plugin xuất nhiều trường quá mức | Cấu hình allowlist, rebuild, thu hồi credential nếu đã lộ |
| `jar tf` xem plain JAR thay bootJar | Có nhiều file output hoặc classifier | Chọn executable archive đúng trong `build/libs` hoặc `target` |
| Gradle mỗi lần test phải rebuild resources | `build.time` luôn đổi làm `bootBuildInfo` không up-to-date | Cân nhắc excludes time theo tài liệu plugin |
| Deploy container chạy version cũ dù pipeline có build mới | Image digest/tag/rollout sai | Kiểm tra registry digest, deployment revision và archive metadata |

Lệnh hỗ trợ (chỉ dùng công cụ thực tế của project):

```bash
# Maven
./mvnw help:effective-pom
./mvnw clean verify

# Gradle
./gradlew tasks --all
./gradlew clean bootJar --info

# Kiểm tra manifest và classpath entries của artifact
jar tf target/metadata-demo-0.1.0-SNAPSHOT.jar

# Khi app đang chạy
curl -i http://localhost:8080/actuator/info
```

Lệnh `jar tf` phía trên dành cho Maven artifact; nếu build Gradle, dùng `build/libs/...jar`. Đừng dùng một file path không tồn tại rồi kết luận thiếu metadata.

## 18. Quy trình CI/CD xác minh metadata trước phát hành

Pipeline có thể xây một **quality gate** cho metadata tương tự test/coverage:

1. **Checkout source revision** rõ ràng và dùng JDK + Maven/Gradle Wrapper được pin.
2. **Build artifact từ source**: Maven `clean verify` hoặc Gradle `clean test bootJar`/`build` phù hợp.
3. **Kiểm tra archive** bằng `jar tf`/`JarFile`: có `META-INF/MANIFEST.MF`, build-info đúng vị trí, và Git info nếu đó là yêu cầu.
4. **So sánh build coordinates** với artifact repository/release metadata; không chỉ kiểm tra file tồn tại.
5. **So sánh Git commit** từ archive với revision mà CI checkout, nếu plugin Git được bật. Chú ý abbreviated SHA/metadata full-vs-short.
6. **Khởi chạy đúng artifact** trong test environment, gọi `/actuator/info` qua kênh được phép và kiểm tra response.
7. **Lưu checksum/image digest** cùng release record; không nhầm Git commit ID với artifact digest.
8. **Publish/deploy chính file đã kiểm tra**, tránh build lại vô tình sinh timestamp/dependency khác rồi không chạy kiểm thử.
9. **Kiểm tra security policy**: chỉ công bố những field được phép và không expose credentials.
10. **Nghiệm thu sau deploy**: endpoint và artifact bytes trên môi trường nhận phải phù hợp release record.

Ví dụ hai nhiệm vụ nối tiếp (Maven):

```bash
./mvnw -B clean verify
java InspectBootArchive target/metadata-demo-0.1.0-SNAPSHOT.jar
```

Bước thứ hai giả sử đã compile helper `InspectBootArchive.java` ở mục 11, và cần **kiểm tra kết quả** chứ không chỉ chạy rồi bỏ qua stdout. Ở CI thật, biến nhiệm vụ này thành script assert các key và giá trị; exit code phải khác 0 khi thiếu metadata bắt buộc. Khi dùng shell/PowerShell khác nhau, chọn cách parse phù hợp và **không gửi log có secret** lên hệ thống công khai.

**Quan trọng:** endpoint `/actuator/info` không phải bằng chứng tự đủ cho supply-chain security. Nó là một nguồn thông tin vận hành thuận tiện; artifact checksum/signing, SBOM và attestation cần được quản lý theo quy trình riêng nếu tổ chức yêu cầu.

## 19. Tổng kết: tránh ba ngộ nhận thường thấy

**Ngộ nhận 1: “Có version trong tên file JAR là Actuator sẽ biết.”** Không đúng. Tên archive chỉ là filename. Spring Boot build contributor đọc metadata file `META-INF/build-info.properties` hoặc custom contributor; không tự lấy version từ đuôi tên file.

**Ngộ nhận 2: “Chỉ thêm Actuator là Git commit xuất hiện.”** Không đúng. Actuator cần `git.properties` trên classpath, do plugin Git hoặc quy trình build tạo. Nếu file không có, `GitProperties`/`GitInfoContributor` sẽ không có dữ liệu để công bố.

**Ngộ nhận 3: “Metadata đã ở trong archive thì /actuator/info chắc chắn truy cập được.”** Không đúng. Phải có dependency Actuator, endpoint/contributors thích hợp, HTTP exposure và security policy. Có thể tồn tại `BuildProperties` bean dù `/actuator/info` đang bị 404 hoặc contributor `build` bị tắt.

### Checklist nghiệm thu

- [ ] Đúng Maven/Gradle project, đúng Java/Spring Boot versions.
- [ ] Goal Maven `build-info` hoặc Gradle `bootBuildInfo` thực sự chạy.
- [ ] Có `META-INF/build-info.properties` trong runtime classpath của app module.
- [ ] Có `BOOT-INF/classes/META-INF/build-info.properties` hoặc `WEB-INF/classes/META-INF/build-info.properties` trong artifact deploy.
- [ ] Manifest `Main-Class`/`Start-Class` khớp executable layout.
- [ ] `build.artifact`, `build.group`, `build.version` phản ánh module ứng dụng, không phải parent/library.
- [ ] `git.properties` chỉ được yêu cầu khi tổ chức cần Git provenance; nếu yêu cầu thì file có revision đúng.
- [ ] BuildProperties/GitProperties được Spring auto-configure và không bị thay đổi ngoài ý muốn.
- [ ] Actuator `info` được expose qua HTTP có chủ đích; response status phù hợp security.
- [ ] `build`/`git` contributors bật khi cần, `env` chỉ bật khi kiểm soát dữ liệu.
- [ ] `build.time` được giữ hoặc loại bỏ theo chính sách reproducibility.
- [ ] Không có secrets/private URLs trong metadata archive hoặc JSON info.
- [ ] CI so khớp archive, Git source revision và release record trước khi deploy.
- [ ] Smoke test sử dụng **đúng file artifact** đã được build/publish.

### Tài liệu chính thức

- [Spring Boot 3.5 — Actuator Endpoints và Application Information](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — How-to Build: Generate Build and Git Information](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Spring Boot 3.5 — Maven Plugin: Integrating with Actuator / build-info](https://docs.spring.io/spring-boot/3.5/maven-plugin/build-info.html)
- [Spring Boot 3.5 — Gradle Plugin: Integrating with Actuator / bootBuildInfo](https://docs.spring.io/spring-boot/3.5/gradle-plugin/integrating-with-actuator.html)
- [Spring Boot 3.5 — Executable Jar Structure](https://docs.spring.io/spring-boot/3.5/specification/executable-jar/nested-jars.html)
- [Spring Boot — Actuator info REST API](https://docs.spring.io/spring-boot/api/rest/actuator/info.html)
- [Git Commit ID Maven Plugin — Repository/Documentation](https://github.com/git-commit-id/git-commit-id-maven-plugin)

**Ghi nhớ:** hãy kiểm tra theo chuỗi **build-info/git-info được tạo → file có thật trong executable archive → Spring tạo BuildProperties/GitProperties → Actuator contributor công bố → endpoint được expose và được phép truy cập**. Nếu một mắt xích thiếu, kết quả `/actuator/info` có thể không phản ánh bản build mà bạn tưởng đang chạy.
