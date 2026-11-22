# Vì sao thư viện dùng chung cần JAR thường thay vì Boot JAR

## 1. Mục tiêu

Trong một dự án Spring Boot đa mô-đun, `shared-core` là thư viện dùng chung, còn `web-app` là chương trình chạy độc lập:

~~~text
multi-module-demo/
├── shared-core/       -> JAR thư viện, project khác import vào classpath
└── web-app/           -> Spring Boot executable JAR, chạy bằng java -jar
    └── depends on shared-core
~~~

Vì hai module có **hợp đồng sử dụng khác nhau**, không nên đóng gói mọi module thành Spring Boot executable JAR. Khi ứng dụng Spring Boot cần chia sẻ classes cho dự án khác, tài liệu Spring Boot khuyên **chuyển code dùng chung sang module độc lập** và để module đó sản xuất ordinary JAR.

Sau bài này, bạn sẽ biết lý do ở mức classpath và cấu trúc archive, cách cấu hình Maven reactor/Gradle multi-project cho hai loại module, cách kiểm tra consumer Java 17 và ứng dụng HTTP, phương án classifier khi chưa thể tách module, quy trình publish và lỗi thường gặp.

Ví dụ dùng Java 17, Spring Boot 4.1.2, Maven 3.6.3+ hoặc Gradle 8.14+ (nhánh 8.x)/9.x theo tài liệu yêu cầu hệ thống của Spring Boot 4.1.2.

## 2. Cơ chế quan trọng nhất: đường dẫn class trong archive

### JAR thường dành cho thư viện

Giả sử class public của `shared-core` có tên `dev.example.core.GreetingFormatter`. Khi build bằng Maven `jar:jar` hoặc Gradle `jar`, file `shared-core-1.0.0.jar` thường có cấu trúc:

~~~text
shared-core-1.0.0.jar
├── META-INF/MANIFEST.MF
└── dev/example/core/GreetingFormatter.class
~~~

Khi một project khác dùng `javac -cp shared-core-1.0.0.jar`, Java compiler tìm class theo tên package, tức entry `dev/example/core/GreetingFormatter.class` **tính từ gốc JAR**. Không cần Boot launcher, không cần Spring runtime nếu API này là Java thuần.

### Spring Boot executable JAR dành cho ứng dụng

Khi Spring Boot Maven Plugin `repackage` hoặc Gradle `bootJar` tạo executable archive, bố cục thường là:

~~~text
web-app-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/dev/example/app/WebApplication.class
    └── lib/
        ├── shared-core-1.0.0.jar
        ├── spring-boot-...jar
        └── ...
~~~

Spring Boot launcher biết cách thêm `BOOT-INF/classes` cùng nested archives dưới `BOOT-INF/lib` vào classpath khi **khởi động `java -jar`**. Nhưng Java compiler/classloader chuẩn không tự xem `BOOT-INF/classes` là package root khi bạn đặt executable archive lên **classpath dependency** của ứng dụng khác; nó cũng không tự tải nested JAR trong `BOOT-INF/lib`.

**Hệ quả:** một Boot JAR có thể chứa đúng class mà consumer vẫn gặp `package ... does not exist` hoặc `ClassNotFoundException`. Đó là sai **loại artifact**, không phải thiếu Java source.

| Tiêu chí | Ordinary library JAR | Boot executable JAR |
| --- | --- | --- |
| Mục tiêu | Import và dùng như dependency | Chạy chương trình |
| Đường dẫn classes | `dev/example/...` ngay tại root | `BOOT-INF/classes/dev/example/...` |
| Dependencies | POM/Gradle metadata quản lý | Nested JAR ở `BOOT-INF/lib` |
| Entry point | Không cần `Main-Class` | Boot loader + `Start-Class` |
| Phép thử đúng | Consumer `javac -cp` | `java -jar` và smoke test |
| Có thể thay thế? | Không | Không |

**Lưu ý:** thư viện dùng Spring Framework vẫn có thể là ordinary JAR. Việc thêm starter hoặc BOM không tự bắt buộc repackage: chính Maven plugin execution hoặc Gradle `bootJar` mới quyết định layout thực thi.

## 3. Kiến trúc đa-mô-đun nên có trách nhiệm rõ ràng

~~~text
                service X      service Y
                    \           /
                     \         /
                 shared-core.jar     [ordinary]
                       ^
                       |
                 web-app module
                       |
                       v
                 web-app.jar         [Boot executable]
                    BOOT-INF/classes
                    BOOT-INF/lib/shared-core.jar
~~~

- `shared-core`: public APIs, DTO, domain rules, helpers và business logic có thể dùng lại. Không cần `@SpringBootApplication` hoặc method `main`.
- `web-app`: application entry point, controllers, runtime configuration, dependency đến `shared-core`.
- Consumer khác: khai báo `shared-core` bằng Maven/Gradle dependency, **không lấy `web-app.jar`** để compile.
- Dependency graph một chiều: `web-app → shared-core`. Tránh core phụ thuộc ngược web-app.

Tách như vậy giúp core có release, Java compatibility, test và API contract riêng. Executable app vẫn dùng được core vì Spring Boot launcher tải ordinary core JAR trong `BOOT-INF/lib`.

## 4. Ví dụ Maven reactor hoàn chỉnh

Cấu trúc source:

~~~text
multi-module-demo/
├── pom.xml
├── shared-core/
│   ├── pom.xml
│   ├── src/main/java/dev/example/core/GreetingFormatter.java
│   └── src/test/java/dev/example/core/GreetingFormatterTest.java
├── web-app/
│   ├── pom.xml
│   └── src/main/java/dev/example/app/WebApplication.java
└── consumer/ConsumerMain.java
~~~

### Root `pom.xml`

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
    <artifactId>multi-jar-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared-core</module>
        <module>web-app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

Root chỉ đóng vai trò aggregator và parent, packaging `pom`. **Không kích hoạt Spring Boot Maven Plugin trong `<build><plugins>` của root**, vì plugin có thể bị kế thừa đến core. Starter parent đã có plugin version và execution `repackage` được cấu hình sẵn; module app kích hoạt khi cần.

### `shared-core/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-jar-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared-core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Chú ý:** không khai báo `spring-boot-maven-plugin` ở core. Maven vẫn chạy Java compilation, Surefire unit tests và `maven-jar-plugin:jar` để sản xuất **ordinary `shared-core-1.0.0.jar`**. Dependency `spring-boot-starter-test` chỉ thuộc test scope, không biến main artifact thành executable.

### `web-app/pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>multi-jar-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>web-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>shared-core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

**Chỉ app kích hoạt Spring Boot Maven Plugin.** Parent Boot đã cấu hình execution `repackage` ở phase `package`; khi plugin được khai báo tại app, Maven tạo executable app JAR. Phần `web-app → shared-core` là dependency thường, giúp reactor xây dựng core trước app.

Nếu không dùng starter parent mà dùng corporate parent/BOM, phải quản lý version Boot plugin và gắn execution goal `repackage` vào `package` **chỉ ở module app**; import `spring-boot-dependencies` BOM không mang theo plugin execution.

## 5. Mã Java 17 cho bài thực hành

### `shared-core/src/main/java/dev/example/core/GreetingFormatter.java`

~~~java
package dev.example.core;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

`shared-core` không cần `main()`. API `greet("Mai")` trả về `Hello, Mai`.

### `shared-core/src/test/java/dev/example/core/GreetingFormatterTest.java`

~~~java
package dev.example.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingFormatterTest {
    @Test
    void greetFormatsName() {
        assertEquals("Hello, Mai", GreetingFormatter.greet("Mai"));
    }
}
~~~

Test chứng minh logic đúng khi chạy bằng test classpath; chưa chứng minh final JAR có layout phù hợp cho compiler.

### `web-app/src/main/java/dev/example/app/WebApplication.java`

~~~java
package dev.example.app;

import dev.example.core.GreetingFormatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }

    @GetMapping("/greeting")
    public String greeting(
            @RequestParam(name = "name", defaultValue = "world") String name) {
        return GreetingFormatter.greet(name);
    }
}
~~~

App có HTTP endpoint. Java class này biên dịch được vì Maven `web-app` khai báo dependency `shared-core`; không cần sao chép mã core sang module app.

### `consumer/ConsumerMain.java`

~~~java
package dev.consumer;

import dev.example.core.GreetingFormatter;

public class ConsumerMain {
    public static void main(String[] args) {
        System.out.println("CONSUMER=" + GreetingFormatter.greet("Mai"));
    }
}
~~~

Consumer là chương trình Java độc lập, đặt ngoài hai module. Chúng ta sẽ cố tình chỉ đưa **ordinary core JAR** vào compiler classpath để chứng minh artifact hoạt động như thư viện.

## 6. Build Maven, kiểm chứng thư viện và chạy ứng dụng

Tại root:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Kết quả dự kiến:

~~~text
shared-core/target/shared-core-1.0.0.jar
web-app/target/web-app-1.0.0.jar
web-app/target/web-app-1.0.0.jar.original   # thường có bản gốc trước repackage
~~~

- `shared-core-1.0.0.jar`: ordinary library JAR.
- `web-app-1.0.0.jar`: Boot executable JAR.
- `.jar.original` của app nếu xuất hiện không phải file để deploy.

### 6.1. Kiểm tra archive

~~~bash
jar tf shared-core/target/shared-core-1.0.0.jar
jar tf web-app/target/web-app-1.0.0.jar
~~~

Trong core cần có:

~~~text
dev/example/core/GreetingFormatter.class
~~~

Trong app cần có:

~~~text
BOOT-INF/classes/dev/example/app/WebApplication.class
BOOT-INF/lib/shared-core-1.0.0.jar
BOOT-INF/lib/...
org/springframework/boot/loader/...
~~~

Core JAR **không** được chứa `BOOT-INF/classes`. Nếu thấy layout Boot ở core, cần kiểm tra plugin inheritance và execution đã chạy nhầm.

### 6.2. Test consumer Java 17 trên Linux/macOS

~~~bash
mkdir -p target/consumer-classes
javac -cp shared-core/target/shared-core-1.0.0.jar -d target/consumer-classes consumer/ConsumerMain.java
java -cp target/consumer-classes:shared-core/target/shared-core-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Stdout chính xác:**

~~~text
CONSUMER=Hello, Mai
~~~

Trên Windows PowerShell, classpath separator là dấu `;`. Có thể chạy hai lệnh một dòng mỗi lệnh:

~~~powershell
New-Item -ItemType Directory -Force target\consumer-classes | Out-Null
javac -cp shared-core\target\shared-core-1.0.0.jar -d target\consumer-classes consumer\ConsumerMain.java
java -cp "target\consumer-classes;shared-core\target\shared-core-1.0.0.jar" dev.consumer.ConsumerMain
~~~

Không đưa `shared-core/target/classes` vào `-cp`; làm vậy sẽ che lỗi nếu JAR đóng gói sai.

### 6.3. Chạy app qua Boot executable

Terminal thứ nhất:

~~~bash
java -jar web-app/target/web-app-1.0.0.jar --server.port=18080
~~~

Sau khi server khởi động, terminal thứ hai:

~~~bash
curl -fsS 'http://127.0.0.1:18080/greeting?name=Mai'
~~~

**HTTP response body chính xác:**

~~~text
Hello, Mai
~~~

Đây là HTTP response body, không phải stdout đầy đủ của process `java -jar` vì Spring Boot có thể in log khác. Sau khi kiểm tra, dừng server bằng `Ctrl+C`.

**Hai kiểm chứng độc lập:** consumer compile chứng minh library JAR dùng được; app `java -jar` và HTTP chứng minh executable JAR đã mang được nested core dependency. Unit test của core không thay được một trong hai phép kiểm chứng này.

## 7. Gradle multi-project: không apply Boot plugin cho shared-core

Dùng cùng source Java ở mục 5, thay cấu hình build bằng bốn file Gradle.

### `settings.gradle`

~~~groovy
rootProject.name = 'multi-module-demo'
include 'shared-core', 'web-app'
~~~

### Root `build.gradle`

~~~groovy
allprojects {
    group = 'dev.example'
    version = '1.0.0'

    repositories {
        mavenCentral()
    }
}
~~~

### `shared-core/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.1.2'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Library chỉ áp dụng `java-library`**, không áp dụng Boot plugin. Task `jar` tạo ordinary JAR với class ở root package path; JUnit test dependencies chỉ nằm trong test classpath.

### `web-app/build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.1.2'
    )
    implementation project(':shared-core')
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
}

tasks.named('bootJar') {
    mainClass = 'dev.example.app.WebApplication'
}
~~~

App mới áp dụng Boot plugin. Dependency `implementation project(':shared-core')` kết nối đúng project, khiến core JAR được tạo và đóng vào `BOOT-INF/lib` của app khi `bootJar` chạy.

### Build và kiểm chứng Gradle

~~~bash
./gradlew clean build
jar tf shared-core/build/libs/shared-core-1.0.0.jar
jar tf web-app/build/libs/web-app-1.0.0.jar
~~~

Kết quả:

~~~text
shared-core/build/libs/shared-core-1.0.0.jar   # ordinary JAR
web-app/build/libs/web-app-1.0.0.jar           # executable Boot JAR
web-app/build/libs/web-app-1.0.0-plain.jar     # có thể có ordinary JAR của app
~~~

Boot Gradle plugin thường đặt classifier `plain` cho task `jar` của app nhằm tránh trùng output với `bootJar`. **Đừng nhầm app plain JAR với library module**; consumer cần shared-core JAR.

Để test consumer với Gradle output:

~~~bash
mkdir -p build/consumer-classes
javac -cp shared-core/build/libs/shared-core-1.0.0.jar -d build/consumer-classes consumer/ConsumerMain.java
java -cp build/consumer-classes:shared-core/build/libs/shared-core-1.0.0.jar dev.consumer.ConsumerMain
~~~

**Stdout chính xác:** `CONSUMER=Hello, Mai`.

Chạy app và thử HTTP:

~~~bash
java -jar web-app/build/libs/web-app-1.0.0.jar --server.port=18080
~~~

Ở terminal khác:

~~~bash
curl -fsS 'http://127.0.0.1:18080/greeting?name=Mai'
~~~

Response body là `Hello, Mai`.

**Task khác nhau:** `:shared-core:jar` chỉ đóng gói library; `:web-app:bootJar` đóng gói app, không tự bảo đảm toàn bộ test chạy. Dùng `./gradlew clean build` để chạy các verification tasks đã được cấu hình.

## 8. Khi publish, module khác phải lấy artifact nào?

Maven consumer dùng:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>shared-core</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Gradle consumer dùng:

~~~groovy
dependencies {
    implementation 'dev.example:shared-core:1.0.0'
}
~~~

**Không** sử dụng executable `web-app` làm dependency chỉ vì nó có nested core JAR.

Để cài core vào Maven repository local:

~~~bash
mvn -pl shared-core -am install
~~~

Đây là local `install`, chưa phải remote `deploy`. Nếu build app module riêng mà core chưa có trong local repository, dùng reactor `mvn -pl web-app -am verify` hoặc cài/resolve core phù hợp.

Với Gradle, publish ordinary library bằng `maven-publish` và Java component trong **module shared-core**, ví dụ fragment:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

Cần thêm `id 'maven-publish'` vào `plugins` hiện có của core rồi dùng `./gradlew :shared-core:publishToMavenLocal`. Fragment trên không tự hoạt động nếu plugin `maven-publish` chưa được kích hoạt. Remote publish cần cấu hình repository và credentials riêng.

Sau publish, QA nên tải lại core từ repository trong một consumer và biên dịch thật. Đừng chỉ kiểm tra file trong `target` hoặc `build/libs`.

## 9. Khi chưa thể tách module: classifier là phương án tạm

Với một module vừa có public API vừa có executable application, có thể tạo **hai artifact riêng** thay vì để Boot archive thay ordinary library JAR.

**Maven** dùng starter parent: tùy biến execution `repackage` bằng classifier `exec`:

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

Đây là fragment trong `build/plugins`. Khi không có source artifact mang classifier `exec`, Maven giữ ordinary `artifact-1.0.0.jar` và tạo thêm executable `artifact-1.0.0-exec.jar`. Nếu không dùng starter parent, cần khai báo plugin version và goal execution `repackage` ở `package` tường minh.

**Gradle:** giữ `jar` không classifier, đặt `bootJar` classifier `exec`:

~~~groovy
tasks.named('jar') {
    archiveClassifier = ''
}
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}
~~~

Classifier giải quyết việc **hai archive có layout khác nhau**. Tuy nhiên cùng module vẫn thường có cùng metadata dependencies; consumer chỉ cần API có thể vô tình kéo dependencies của web stack. Khi thư viện có nhiều consumers, tách `shared-core`/`web-app` vẫn là thiết kế sạch hơn.

## 10. Lỗi thường gặp và chẩn đoán

| Lỗi | Nguyên nhân cần kiểm tra | Cách khắc phục |
| --- | --- | --- |
| Core build báo thiếu main class | Boot plugin chạy nhầm ở library | Chỉ activate Boot Maven Plugin/Gradle Boot Plugin ở app |
| Core JAR có `BOOT-INF/classes` | Repackage đã thay ordinary artifact | Kiểm tra POM effective / task graph; sửa packaging core |
| Consumer không import `GreetingFormatter` | Dùng Boot JAR hoặc sai version | `jar tf` và compile classpath của consumer |
| App `NoClassDefFoundError` với core | App thiếu dependency hoặc nested JAR | Xem `BOOT-INF/lib/shared-core-...jar` |
| Maven app không resolve shared-core | Build app riêng khi core chưa có trong repo | Dùng `-pl web-app -am` hoặc install/publish core |
| Maven root `pom` bị cố repackage | Plugin Boot bật ở root và inherited | Chỉ bật ở app, dùng pluginManagement nếu cần |
| Gradle core tạo `bootJar` | Apply Boot plugin trong mọi subprojects | Dùng `java-library` tại core |
| Gradle app có thêm `-plain.jar` | `jar` và `bootJar` là hai tasks | Deploy đúng output `bootJar` |
| Test xanh nhưng published core hỏng | Test chạy trên classes, không kiểm tra JAR | Thêm `javac -cp core.jar` consumer gate |
| App chạy mà HTTP sai | Port/config/route hoặc dependency runtime | HTTP smoke test status và body |
| Core compiler target cao hơn runtime | Toolchain/release không thống nhất | Dùng Java target tương thích giữa modules |
| Library kéo web dependencies không cần | Core/app chưa tách hoặc metadata sai | Tách module, quản lý API/implementation deps |

**Trình tự điều tra:** xác định module → artifact identity → archive layout → dependency graph → consumer compile → executable runtime → repository metadata. Không chữa lỗi classpath layout bằng cách đổi Java version tùy tiện.

## 11. QA gate cho dự án đa mô-đun

| Gate | Bằng chứng PASS |
| --- | --- |
| Library layout | `shared-core.jar` có `dev/example/core/GreetingFormatter.class` tại root, không có `BOOT-INF/classes` |
| Library API | `javac -cp shared-core.jar` thành công; `ConsumerMain` in `CONSUMER=Hello, Mai` |
| Core tests | `GreetingFormatterTest` thực sự được chạy, 0 failures/errors |
| App archive | `web-app.jar` có `BOOT-INF/classes`, `BOOT-INF/lib/shared-core-1.0.0.jar` và launcher |
| App runtime | `java -jar web-app.jar` khởi động trên JDK mục tiêu |
| App smoke | HTTP `/greeting?name=Mai` trả 200 và body `Hello, Mai` |
| Publish | Consumer tải `dev.example:shared-core:1.0.0` từ repository và compile được |
| Build lineage | Hai module cùng commit/version, không repackage nhầm core |

**Quan trọng:** `BUILD SUCCESS` không tự chứng minh library artifact đúng layout; app chạy được cũng không chứng minh consumers import được core qua repository. Cần kiểm tra cả **library contract** và **executable contract**.

## 12. Câu hỏi luyện tập

**1. Vì sao Boot executable JAR không thích hợp làm dependency?** Vì class ở `BOOT-INF/classes` và nested dependencies ở `BOOT-INF/lib`, trong khi compiler/classloader thông thường tìm class theo root của classpath entry.

**2. Core dùng Spring Framework có bắt buộc Boot JAR không?** Không. Ordinary JAR có thể chứa Spring classes, miễn dependencies và config được quản lý đúng.

**3. Maven root kế thừa Boot starter parent có làm core tự repackage không?** Không nếu root không activate plugin và core không khai báo plugin. Chỉ module app nên kích hoạt Boot Maven Plugin.

**4. Gradle core nên apply plugin nào?** `java-library` (hoặc `java`), không cần `org.springframework.boot`.

**5. Vì sao core JAR cần consumer compile test?** Unit test có thể chạy trên compiled classes chưa đóng gói; consumer test chứng minh JAR cuối có package layout đúng.

**6. Nếu app đã chứa core nested JAR, tại sao app vẫn chạy?** Spring Boot launcher cấu hình runtime classpath từ `BOOT-INF/lib` khi `java -jar`.

**7. Khi chưa thể tách module, classifier giải quyết được gì?** Tách plain JAR và exec JAR; chưa tự tách dependency graph và API coupling.

**8. `mvn install` có nghĩa đã publish remote library không?** Không. Install là local repository; deploy mới là bước publish remote theo cấu hình.

## 13. Checklist cuối

- [ ] Xác định module thư viện và module chạy độc lập.
- [ ] Core chỉ tạo ordinary JAR; app mới dùng Boot repackage/bootJar.
- [ ] Class core nằm tại Java package path ở root của ordinary JAR.
- [ ] Boot JAR app có loader, `BOOT-INF/classes` và nested core JAR.
- [ ] Root Maven/Gradle không apply Boot plugin đại trà.
- [ ] App phụ thuộc core một chiều.
- [ ] Unit test core và consumer `javac -cp` cùng PASS.
- [ ] App `java -jar` và HTTP smoke test cùng PASS.
- [ ] Java toolchain/release phù hợp giữa modules.
- [ ] Downstream dùng tọa độ core, không dùng executable web-app.
- [ ] Publication metadata đúng ordinary artifact.
- [ ] Kiểm tra output và báo cáo thực tế, không chỉ build exit code.

**Ghi nhớ:** `shared-core.jar` là **đầu vào classpath cho consumers**; `web-app.jar` là **đầu vào của `java -jar`**. Tách library và app thành hai module giúp giữ đúng cả hai hợp đồng và ngăn Boot packaging làm hỏng khả năng tái sử dụng của code dùng chung.

## 14. Tài liệu chính thức

1. [Spring Boot — Use a Spring Boot Application as a Dependency](https://docs.spring.io/spring-boot/how-to/build.html)
2. [Spring Boot — Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
3. [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
4. [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
5. [Spring Boot Gradle Plugin — Packaging Executable and Plain Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
6. [Apache Maven — Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
7. [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
8. [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
9. [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
