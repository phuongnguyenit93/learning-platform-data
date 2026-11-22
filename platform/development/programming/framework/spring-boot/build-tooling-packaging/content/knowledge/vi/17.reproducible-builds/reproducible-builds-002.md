# Khóa phiên bản Java, Wrapper, plugin và dependency để có bản dựng tái lập

## 1. Bài toán: vì sao cùng mã nguồn nhưng hai máy build khác nhau?

Một dự án Spring Boot chạy tốt trên máy lập trình viên nhưng CI báo `UnsupportedClassVersionError`; hoặc build hôm qua thành công, hôm nay Maven/Gradle tự chọn phiên bản thư viện mới làm test hỏng. Có trường hợp cả hai máy cùng build thành công nhưng nội dung file JAR lại có timestamp, thứ tự ZIP entries hoặc metadata khác nhau.

Muốn bản dựng ổn định, cần quản lý **bốn nhóm phiên bản** và hiểu thêm các đầu vào ngoài version:

1. **Java/JDK:** compiler, runtime JDK, API mức `--release`, vendor và bản vá nếu cần mức tái lập mạnh.
2. **Build tool qua Wrapper:** Apache Maven hoặc Gradle distribution cụ thể, wrapper scripts/JAR và integrity checksum.
3. **Build plugins:** Spring Boot Maven/Gradle Plugin, compiler/test/package plugins, annotation processors, quality plugins.
4. **Dependencies:** các thư viện trực tiếp, transitive dependencies, BOM/version constraints, test/runtime/annotationProcessor classpaths.

Các yếu tố còn lại gồm repositories, artifact bytes, hệ điều hành, locale/time zone, environment variables, cấu hình build, dữ liệu build-time và công cụ native. **Khóa phiên bản là điều kiện quan trọng nhưng không tự bảo đảm đầu ra giống hệt từng byte**.

### Kết quả mong đợi

Sau bài, bạn có thể:

- Đọc và cấu hình `maven.compiler.release`, Maven Toolchains, Gradle Java Toolchains và `options.release`.
- Tạo Maven Wrapper và Gradle Wrapper, dùng đúng version công cụ ở local/CI.
- Kiểm tra `distributionUrl`, `distributionSha256Sum` và tính toàn vẹn của wrapper.
- Pin phiên bản plugins, Spring Boot parent/BOM, không dùng `LATEST`, `RELEASE`, `1.+` hoặc `-SNAPSHOT` tùy tiện trong release build.
- Tạo một Spring Boot Maven project và một Gradle project độc lập, có Java 17 code, test và executable JAR.
- Bật **Gradle dependency locking** tạo `gradle.lockfile` và biết cách cập nhật một cách có kiểm soát.
- Biết rằng **Maven 3 không có dependency lockfile built-in tương đương Gradle dependency locking**; biết dùng managed versions, dependency tree, Enforcer và repository policy để giảm bất định.
- Kiểm soát phiên bản runtime JVM trong container/CI, so sánh dependency graph và phân biệt các mức độ reproducibility.
- Phân tích lỗi “local OK, CI FAIL” hoặc “cùng source nhưng output khác nhau” trước khi tăng version theo cảm tính.

**Mốc ví dụ được chọn:** Spring Boot **3.5.16**, Java **17**, Maven **3.9.16**, Gradle **8.14.3**. Đây là các bản phát hành cụ thể tương thích cho nội dung minh họa: Spring Boot 3.5.x cần Java 17+ và hỗ trợ Maven 3.6.3+ cùng Gradle 8.4+ thuộc dòng 8.x. Những bản vá/version **không phải lựa chọn bắt buộc cho mọi dự án**; đội ngũ cần duy trì chính sách hỗ trợ và đánh giá security updates.

## 2. “Khóa phiên bản” và “reproducible build” có ba mức khác nhau

### 2.1. Dependency resolution ổn định

Mục tiêu cơ bản là **cùng project state thì build tool giải quyết cùng tập tọa độ dependency**:

~~~text
org.springframework.boot:spring-boot-starter:3.5.16
org.springframework:spring-context:6.2.x
org.junit.jupiter:junit-jupiter:5.x
...
~~~

Các phiên bản `6.2.x`/`5.x` trên là **minh họa pattern**, không phải số version đã được kiểm tra cho build mẫu. Dùng `dependency:tree`/`dependencyInsight` để đọc đúng version được chọn.

Pin direct dependencies **không bảo đảm** transitive graph nếu dùng dynamic ranges, BOM thay đổi, một dependency có POM thay đổi sau khi publish, hoặc repository trả cùng GAV nhưng bytes không nhất quán.

### 2.2. Build behavior nhất quán

Bên cạnh dependencies, cần dùng đúng Maven/Gradle, JDK, plugins và build flags:

~~~text
source + tests + config
         |
         v
JDK 17 + Maven 3.9.16 / Gradle 8.14.3
         |
         v
Spring Boot plugin 3.5.16 + pinned build plugins
         |
         v
dependency graph do BOM / Gradle locks kiểm soát
         |
         v
JAR + reports + test results
~~~

Nếu Jenkins dùng `mvn` từ hệ thống (3.8.x), laptop dùng Maven 3.9.x, hoặc CI chọn JDK 21 còn local chọn JDK 17, thì source code giống nhau chưa đủ để nói công cụ build được khóa.

### 2.3. Bit-for-bit reproducible artifact

Mục tiêu cao hơn: **đối với cùng input được xác định, JAR được tạo ra phải có hash giống nhau**. Điều này đòi hỏi xử lý thêm:

- Timestamp trong ZIP entries và build metadata.
- Thứ tự files trong archive.
- Paths tuyệt đối hoặc hostnames ghi vào generated files.
- Build-time dates, random identifiers, Git metadata và clock-dependent resources.
- Java vendor/patch version khi compiler, annotation processor hoặc tooling tạo output khác nhau.
- Encoding, locale, time zone và filesystem behavior.
- Các dependencies có mutable bytes dù tọa độ version giống nhau.
- Plugins hoặc toolchains native có đầu ra phụ thuộc platform.

**Không tuyên bố “reproducible = chỉ cần pom.xml có version”**. Bài sẽ khóa các công cụ chính trước, rồi đưa checklist kiểm tra hashes/metadata phù hợp ở cuối.

## 3. Phân tầng trách nhiệm: đâu là nguồn khóa chính?

| Thành phần | Maven | Gradle | Điều phải nhớ |
| --- | --- | --- | --- |
| Java language/API level | `maven.compiler.release=17` | `options.release.set(17)` | Giới hạn bytecode/API, **không chọn bản cài JDK tuyệt đối** |
| JDK chạy compiler/tests | Maven Toolchains/JAVA_HOME/CI JDK | Java Toolchains + JDK chạy Gradle | Vendor và patch level có thể vẫn khác |
| Build tool version | `mvnw` + `.mvn/wrapper/maven-wrapper.properties` | `gradlew` + `gradle/wrapper/gradle-wrapper.properties` | Cần commit Wrapper và kiểm checksum |
| Spring Boot build plugin | Parent/pluginManagement/explicit plugin version | `plugins { id(...) version "..." }` | Plugin version khác dependency BOM version |
| Spring libraries | `spring-boot-starter-parent`/import BOM | `platform("...spring-boot-dependencies:...")` | BOM quản lý versions, **không tự thêm dependencies** |
| Other plugins | Pin versions trong `build/plugins`/`pluginManagement` | Pin plugin IDs trong `plugins`/`pluginManagement` | Không để plugin resolution tùy latest |
| Transitive libraries | Maven dependency mediation, management, repository policy | Gradle constraints + `gradle.lockfile` | Gradle có lockfile built-in; Maven 3 không có tương đương mặc định |
| Artifact bytes | Reproducible archive/plugin options | Reproducible archive task options | Cần kiểm hash, không suy ra từ resolved versions |

Một `BOM` hoặc version catalog chỉ là **một phần** của chiến lược. Wrapper và JDK phải được quản lý từ cả repository lẫn CI; không thể thay bằng một BOM.

## 4. Khóa Java: Java 17 không luôn đồng nghĩa cùng một JDK

### 4.1. JDK đang chạy Maven/Gradle

Trên Linux/macOS:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
mvn -version
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
mvn -version
~~~

`java -version` cho biết Java trong PATH; `mvn -version` cho biết Java runtime Maven đang sử dụng. Chúng có thể không giống nhau nếu launcher hoặc environment được cấu hình khác. Với Gradle xem:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

`javaToolchains` hiển thị các JDK Gradle phát hiện; `--version` cho biết Gradle distribution và JVM chạy build. Toolchain được chọn cho compilation có thể **khác JVM chạy Gradle daemon**.

### 4.2. Maven compiler release

Trong `pom.xml`, khai báo:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Khi compiler plugin hỗ trợ `--release`, biên dịch với `--release 17` giới hạn Java API và class-file target phù hợp Java 17. Nó **không** cài JDK 17 và không buộc Maven JVM chỉ chạy Java 17.

Ví dụ compiler đang chạy bằng JDK 21 vẫn có thể compile target Java 17 nhờ `--release 17`. Kết quả có thể chạy trên Java 17 nếu **mọi runtime dependencies** cũng tương thích Java 17. `--release` không tự hạ target của dependency JAR đã có.

### 4.3. Maven Toolchains chọn một JDK khác với Maven launcher

Maven Toolchains Plugin cho phép compiler và những plugin hỗ trợ toolchain sử dụng JDK riêng. Một cách khai báo cho Maven có:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>select-jdk-toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

Đây là **đoạn plugin nằm trong `<build><plugins>`**, không phải file POM hoàn chỉnh; ví dụ project Maven đầy đủ ở mục 6 sẽ dùng hướng đơn giản hơn: yêu cầu Maven JVM chạy Java 17 ngay từ CI và kiểm tra bằng Enforcer.

Tùy cách dùng, JDK toolchains được mô tả trong `~/.m2/toolchains.xml` hoặc auto-discovery của Maven Toolchains 3.2+. File `toolchains.xml` có đường dẫn JDK **theo từng máy**, do vậy không nên commit đường dẫn absolute của một developer làm chuẩn toàn công ty. Công cụ build phải được cấu hình để **fail rõ ràng nếu không tìm được JDK phù hợp**, thay vì im lặng chọn JDK mới hơn ngoài hợp đồng.

**Điểm cần phân biệt:** `requireJavaVersion` của Maven Enforcer kiểm tra Java dùng để chạy Maven. Nó không thay thế việc chọn/kiểm tra JDK của toolchain khác nếu compiler/tests dùng JDK riêng.

### 4.4. Gradle Java Toolchain và options.release

Trong `build.gradle.kts`:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
~~~

Đoạn này cần plugin `java` hoặc plugin có Java extension. Toolchain chọn **JDK có ngôn ngữ phiên bản 17** cho compilation và các tasks Java plugin hỗ trợ; `--release 17` cấm compiler dùng JDK APIs mới hơn mục tiêu. Gradle có thể auto-provision toolchain **khi đã cấu hình toolchain download repositories**; nếu không có JDK phù hợp và không có provisioning, build có thể fail.

**Khóa tới Java 17 major ≠ pin toàn bộ JDK binary**: Adoptium 17.0.x và một vendor 17.0.y đều là Java 17 nhưng bytecode/tool behavior có thể có khác biệt. Nếu cần bit-for-bit reproducibility, pin thêm vendor, patch và artifact digest trong CI/container/toolchain provisioning theo chính sách của nhóm.

### 4.5. Java chạy ứng dụng sau khi package

Dự án build bằng JDK 17 nhưng production runtime có thể là Java 21. Điều đó đôi khi là hợp lệ, nhưng cần test tương thích. Nếu mục tiêu là **chạy đúng Java 17 ở production**, phải cấu hình runtime image/JAVA_HOME/container tag **cụ thể**, không suy ra từ Java release của compiler. Dùng container image digest thay cho tag mutable trong yêu cầu tái lập chặt.

## 5. Maven Wrapper: khóa Maven distribution trong repository

### 5.1. Wrapper giải quyết vấn đề gì?

Không nên yêu cầu “mọi developer tự cài đúng Maven version” rồi chỉ dựa vào hướng dẫn README. Apache Maven Wrapper thêm các scripts `mvnw`/`mvnw.cmd` và file cấu hình trong `.mvn/wrapper/`. Khi chạy wrapper, nó tải hoặc tái dùng **Maven distribution đã chọn**.

Cấu trúc thường gặp:

~~~text
version-lock-maven/
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── pom.xml
└── src/...
~~~

Một số distribution types của Maven Wrapper dùng `maven-wrapper.jar`, `MavenWrapperDownloader.java` hoặc chỉ scripts; **không mặc định mọi phiên bản có đủ cả ba file**.

### 5.2. Sinh Maven Wrapper với Maven 3.9.16

Nếu máy đầu tiên có Maven cài sẵn:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper \
  -Dmaven=3.9.16 -Dtype=only-script
~~~

Trên Windows PowerShell, đặt trong một dòng:

~~~powershell
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper "-Dmaven=3.9.16" "-Dtype=only-script"
~~~

`-N` là non-recursive (hữu ích ở root multi-module). `-Dmaven=3.9.16` chọn Maven distribution; `only-script` là Maven Wrapper type không yêu cầu commit wrapper JAR. **Chạy goal này là bước thiết lập/upgrade ban đầu**, không phải lệnh phải chạy mỗi lần build.

Sau khi sinh, dùng:

~~~bash
./mvnw -version
./mvnw clean verify
~~~

Windows:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
~~~

Cần commit đúng các wrapper scripts/config được tạo. Nếu wrapper không tồn tại trong project, `./mvnw` không phải lệnh hợp lệ — dùng `mvn` để **tạo** wrapper trước.

### 5.3. File maven-wrapper.properties

Một cấu hình có thể chứa:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.16/apache-maven-3.9.16-bin.zip
~~~

**Không tự gõ checksum ngẫu nhiên** vào `distributionSha256Sum`. Maven Wrapper hỗ trợ `distributionSha256Sum` để xác minh Maven distribution và (với wrapper JAR type phù hợp) `wrapperSha256Sum` để xác minh wrapper JAR. Lấy **hash SHA-256 chính thức của đúng file** từ nơi phát hành tin cậy rồi thêm vào properties hoặc truyền tham số được Maven Wrapper Plugin hỗ trợ. Chỉ đặt checksum khi bạn có giá trị đã được xác minh; một chuỗi giả làm wrapper fail và còn tạo cảm giác an toàn sai.

**Khóa version không thay việc xác minh nguồn tải**. Nên review wrapper scripts/JAR và distribution URL mỗi lần update; CI chỉ sử dụng wrapper đã commit, không tải những scripts thay thế qua lệnh mạng không được kiểm soát.

### 5.4. Maven version được khóa khác Maven plugins

Chạy Maven 3.9.16 **không** buộc Maven Compiler Plugin hay Spring Boot Maven Plugin cùng cố định version. Plugin version là một artifact khác, có lifecycle/config riêng. Không nhập nhằng version Maven distribution với version của `maven-compiler-plugin`.

## 6. Project Maven hoàn chỉnh: Java 17 + parent/BOM + pinned plugins

### 6.1. Cây thư mục

Bài thực hành Maven độc lập dùng:

~~~text
version-lock-maven/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/maven-wrapper.properties
└── src/
    ├── main/java/com/example/lockdemo/
    │   └── VersionLockApplication.java
    └── test/java/com/example/lockdemo/
        └── VersionLockApplicationTest.java
~~~

Wrapper files được tạo bằng lệnh mục 5; nếu bạn tạo project thủ công trước đó chỉ có `pom.xml` và `src/`, dùng Maven đã cài để tạo wrapper.

### 6.2. File pom.xml hoàn chỉnh

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
    <artifactId>version-lock-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>verify-build-runtime</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,18)</version>
                                </requireJavaVersion>
                            </rules>
                            <fail>true</fail>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao cấu hình này có tính kiểm soát hơn POM mặc định?**

- `spring-boot-starter-parent:3.5.16` cố định Spring Boot parent và quản lý một tập phiên bản phụ thuộc/plugin. Parent cũng cấu hình `spring-boot-maven-plugin:repackage` trong lifecycle khi plugin được khai báo.
- `maven.compiler.release=17` và `java.version=17` xác định target Java của project theo convention Boot.
- Compiler/Surefire/Enforcer/Boot build plugins có **versions cụ thể**, không trôi theo việc Maven chọn một plugin release khác.
- `requireMavenVersion [3.9,4.0)` từ chối Maven cũ hơn 3.9 hoặc từ Maven 4 trở lên; **Wrapper 3.9.16** còn pin đến bản Maven cụ thể.
- `requireJavaVersion [17,18)` yêu cầu **JDK/JRE dùng chạy Maven** ở dòng Java 17. Đây là chính sách chặt của ví dụ, không phải yêu cầu của Spring Boot rằng mọi build phải dùng Java 17.
- `project.build.outputTimestamp` cung cấp timestamp được khai báo cho các archive plugins hỗ trợ reproducible archives. Nó không tự chữa mọi nguồn không xác định khác như generated source chứa current time.

**Lưu ý quan trọng về Enforcer:** với JDK toolchains, plugin có thể kiểm Java launcher mà không xác minh mọi toolchain. Nếu chủ động chạy Maven bằng JDK 21 để compile source target 17, quy tắc `[17,18)` sẽ fail, dù compile bằng `--release 17` về mặt kỹ thuật có thể hợp lệ. Điều này là lựa chọn policy cho ví dụ, không phải bug.

### 6.3. Java source hoàn chỉnh

Tạo `src/main/java/com/example/lockdemo/VersionLockApplication.java`:

~~~java
package com.example.lockdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class VersionLockApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionLockApplication.class, args);
    }

    public static String message() {
        return "LOCKED_OK: hello";
    }

    @Bean
    ApplicationRunner showMessage() {
        return args -> System.out.println(message());
    }
}
~~~

Đây là file Java hoàn chỉnh, chạy được với `spring-boot-starter` và Java 17. `ApplicationRunner` in một dòng sau khi Spring context khởi tạo. Dòng **do code này in** có nội dung chính xác:

~~~text
LOCKED_OK: hello
~~~

Spring Boot thường in thêm startup logs tùy môi trường; không coi toàn bộ stdout là chỉ một dòng.

### 6.4. Unit test độc lập với external services

Tạo `src/test/java/com/example/lockdemo/VersionLockApplicationTest.java`:

~~~java
package com.example.lockdemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class VersionLockApplicationTest {

    @Test
    void messageIsStable() {
        assertEquals("LOCKED_OK: hello",
                     VersionLockApplication.message());
    }
}
~~~

`spring-boot-starter-test` cung cấp JUnit Jupiter. Test không khởi tạo database, HTTP server hoặc container, giúp khóa version và kiểm compiler/test plugin mà không để nguồn bất định bên ngoài làm nhiễu. Maven Surefire từ POM mẫu chạy test khi `mvn test`/`mvn verify`.

### 6.5. Chạy Maven qua Wrapper

~~~bash
./mvnw -version
./mvnw clean verify
java -jar target/version-lock-maven-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
java -jar .\target\version-lock-maven-1.0.0.jar
~~~

Nếu không có Wrapper vì bạn chưa làm bước 5, dùng `mvn clean verify` **sau khi xác minh Maven/JDK tương thích** để tạo artifact, rồi sinh wrapper trước khi commit dự án.

Những điều cần kiểm:

1. `./mvnw -version` hiển thị Maven **3.9.16** và JVM của Maven nằm trong Java **17.x**.
2. Enforcer chạy ở phase `validate` và fail sớm nếu Maven/Java version vi phạm policy.
3. Unit test `messageIsStable` pass.
4. `target/version-lock-maven-1.0.0.jar` là executable Spring Boot JAR, không phải plain thin JAR.
5. `java -jar` chạy được và có dòng `LOCKED_OK: hello`.

### 6.6. Parent riêng và Spring Boot BOM

Nếu công ty đã có Maven corporate parent, **không khai báo hai parent**. Một POM chỉ có một parent trực tiếp. Có thể import BOM Boot:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Và phải quản lý các Maven plugins/executions ở parent hay app module. **Import BOM chỉ quản lý dependency versions; nó không tự import plugin management hoặc execution `repackage`** của `spring-boot-starter-parent`.

## 7. Maven dependencyManagement/BOM không phải lockfile đầy đủ

### 7.1. Những gì BOM thực sự giải quyết

Một BOM là POM có tập managed dependency coordinates/versions. Khi child khai báo Spring Boot starter không ghi version, Maven chọn version do parent/imported BOM quản lý. Điều này giúp giữ các Spring libraries trong một release train được kiểm thử tương thích.

Ví dụ trong `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

Version của starter được managed bởi parent. Nhưng BOM **không tự thêm** starter vào classpath; child phải khai báo dependency.

### 7.2. Vì sao Maven không “lock tất cả” chỉ với BOM?

Một ứng dụng có thư viện ngoài Boot BOM hoặc dependencies mới xuất hiện qua graph transitive. Maven dependency mediation, `dependencyManagement`, scopes và version ranges quyết định kết quả. Khi BOM thay version hoặc dependency graph thay đổi, transitive versions có thể đổi. **Maven 3 không phát sinh file khóa transitives theo mặc định** tương đương `gradle.lockfile`.

Để kiểm soát:

- Pin direct dependencies không nằm trong BOM và pin BOM/parent version.
- Tránh version ranges/dynamic/latest và `SNAPSHOT` trong production release graph.
- Pin build plugins và versions của plugin dependencies khi cần.
- Lưu dependency graph, artifact checksums/SBOM cho release.
- Có repository mirror/immutable release artifact policy.
- Dùng Maven Enforcer như `dependencyConvergence`/`requireUpperBoundDeps` **khi phù hợp** để phát hiện một số conflict; những rules này **không tự tạo một dependency lockfile**.
- Cân nhắc các công cụ lock/dependency verification bên thứ ba sau khi đánh giá mức độ bảo trì, nhưng không mặc định Maven có cùng `--write-locks` như Gradle.

### 7.3. Dùng dependency tree kiểm tra phiên bản thực

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
./mvnw clean verify
~~~

`dependency:tree` thể hiện graph Maven đã resolve, gồm transitive version và scope. `help:effective-pom` cho biết parent inheritance, BOM/management và plugins sau merge. Lệnh gọi goal từ CLI có thể dùng plugin version theo plugin management của parent hoặc Maven plugin resolution; trong quy trình tái lập nghiêm ngặt, cũng nên pin versions của **các plugins báo cáo** thường dùng.

**Đừng lấy output của `dependency:tree` làm file input mà Maven tự xác minh ở lần chạy sau.** Nó là báo cáo, không phải built-in lock. Muốn CI phát hiện drift, so sánh báo cáo/SBOM được chuẩn hóa bằng quy trình riêng hoặc plugin phục vụ enforcement.

## 8. Gradle Wrapper: khóa distribution và xác minh checksum

### 8.1. Vì sao commit wrapper?

Gradle Wrapper gồm scripts và cấu hình cho version Gradle đã chọn:

~~~text
version-lock-gradle/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle.kts
├── build.gradle.kts
└── src/...
~~~

**Commit cả scripts, properties và wrapper JAR** được sinh bởi Gradle chính thức. Gradle wrapper JAR là một executable binary ở mức build bootstrap: phải verify nguồn/chữ ký hoặc checksum theo hướng dẫn Gradle, không chỉ review text file.

### 8.2. Tạo wrapper với Gradle 8.14.3

Nếu môi trường đầu tiên đã cài Gradle phù hợp:

~~~bash
gradle wrapper --gradle-version=8.14.3 --distribution-type=bin
~~~

Sau khi wrapper có mặt:

~~~bash
./gradlew wrapper --gradle-version=8.14.3 --distribution-type=bin
./gradlew --version
~~~

Tài liệu Gradle khuyến nghị chạy wrapper task thêm lần nữa sau khi nâng version để cập nhật wrapper JAR/scripts theo release mới, nếu các file hiện có chưa được nâng. Trong repository thực tế, review diff của `gradle/wrapper`, không chạy nhiệm vụ này một cách ngẫu nhiên trong pipeline release.

### 8.3. File gradle-wrapper.properties

Một file được tạo có thể chứa các dòng kiểu:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Các thuộc tính có thể khác chút ít theo Gradle Wrapper release. Phần **khóa version** là `gradle-8.14.3-bin.zip`. Về integrity, thêm `distributionSha256Sum` bằng **giá trị SHA-256 thật, đầy đủ của distribution ZIP này**, lấy từ Gradle release checksums:

https://gradle.org/release-checksums/

Có thể xem file checksum chính thức:

~~~bash
curl -fsSL https://services.gradle.org/distributions/gradle-8.14.3-bin.zip.sha256
~~~

**Không tự điền hash mẫu/hard-code hash chưa xác minh**. Gradle Wrapper kiểm `distributionSha256Sum` khi tải distribution mới; nếu ZIP đã cache thì verification behavior khác và không nên coi wrapper checksum như kiểm tất cả dependencies của build. Tài liệu Gradle nhấn mạnh cần xác minh riêng **`gradle-wrapper.jar`** vì binary đó chạy trước khi Gradle download/verification được thực hiện.

### 8.4. Chạy thống nhất trên các môi trường

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean build
~~~

**Không thay `./gradlew` bằng `gradle` hệ thống trong CI** nếu mục đích là dùng distribution đã được khóa. Wrapper không pin JDK chạy Gradle; Java cần được quản lý riêng.

## 9. Project Gradle hoàn chỉnh: plugin, BOM, toolchain và dependency locking

### 9.1. Cấu trúc

Đây là **project độc lập với ví dụ Maven**, nhưng sử dụng cùng Java application/test files ở mục 6.3 và 6.4:

~~~text
version-lock-gradle/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/gradle-wrapper.jar
├── gradle/wrapper/gradle-wrapper.properties
├── gradle.lockfile            # Sinh sau khi tạo locks
└── src/
    ├── main/java/com/example/lockdemo/
    │   └── VersionLockApplication.java
    └── test/java/com/example/lockdemo/
        └── VersionLockApplicationTest.java
~~~

Các file source Java **cần được đặt đúng package path** như mục 6; không đặt Maven POM và Gradle build scripts vào một directory rồi giả định cùng một artifact sẽ được publish.

### 9.2. File settings.gradle.kts

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "version-lock-gradle"
~~~

Đây là file Kotlin DSL hoàn chỉnh. Gradle plugin resolution và dependency resolution có thể dùng repositories khác nhau; khai báo cả hai để dễ audit. Trong doanh nghiệp, thay/bao ngoài bằng artifact repository proxy đáng tin cậy, quản lý repositories centrally và fail khi dự án cố ý dùng repository ngoài chính sách.

### 9.3. File build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )

    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

**Đọc kỹ từng khóa:**

- Plugin `org.springframework.boot` được pin **3.5.16**; không để version trôi qua dynamic plugin version.
- `java` core plugin cung cấp `compileJava`, `test` và `jar`. Boot plugin nhận diện Java project và tạo `bootJar`.
- Java toolchain chọn Java **17**; `options.release=17` giới hạn API/bytecode và UTF-8 encoding.
- `platform(...)` nhập Spring Boot BOM vào Gradle dependency resolution; **không tự thêm starter**.
- `spring-boot-starter`/`spring-boot-starter-test` không có version vì BOM quản lý versions. Nếu một dependency không được BOM quản lý, cần khai báo version/constraint rõ.
- `junit-platform-launcher` được đưa vào test runtime theo hướng dẫn Gradle/JUnit, phiên bản do BOM quản lý.
- `dependencyLocking.lockAllConfigurations()` bật Gradle locking cho những configurations được resolve. Lockfile sẽ xuất hiện **sau khi chạy lệnh sinh lock**, không tự sinh chỉ vì có block này.
- `AbstractArchiveTask` bỏ per-file timestamps và chuẩn hóa file order cho các archive tasks Gradle hỗ trợ. Nó giúp reproducible archive nhưng **không chắc đảm bảo bit-for-bit** nếu nội dung generated files phụ thuộc môi trường.

**Không thêm `io.spring.dependency-management` vào project này chỉ để có BOM**: ví dụ đã dùng Gradle native `platform`. Boot plugin version và Spring Boot BOM đang trùng `3.5.16` là **quy ước minh họa dễ audit**; muốn nâng phải xét cả hai cùng lúc.

### 9.4. Java source và kết quả chạy

Sao chép đúng hai Java files ở mục 6.3/6.4 vào project Gradle này. `VersionLockApplication.message()` trả `LOCKED_OK: hello`; test assert chính giá trị đó, không phụ thuộc thời điểm build hoặc mạng.

Sau khi Gradle đã resolve dependencies, chạy:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/version-lock-gradle-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\version-lock-gradle-1.0.0.jar
~~~

Nếu archive name/classifier được thay đổi theo project, dùng đúng file thực tế dưới `build/libs/`. Dòng do application tự in:

~~~text
LOCKED_OK: hello
~~~

Boot startup logs có thể xuất hiện thêm; output trên không phải toàn bộ stdout.

## 10. Gradle dependency locking — tạo và duy trì gradle.lockfile

### 10.1. Tại sao BOM chưa đủ?

Giả sử dependencies khai báo:

~~~kotlin
implementation(
    platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
)
implementation("org.springframework.boot:spring-boot-starter")
~~~

BOM chọn một tập versions, nhưng Gradle vẫn thực hiện dependency graph resolution qua constraints/conflicts giữa các module. Với `lockAllConfigurations`, Gradle có thể lưu **phiên bản cuối cùng đã resolve** của direct và transitive dependencies cho các configurations. Lần sau, nếu graph muốn chọn version khác mà không cập nhật lock hợp lệ, Gradle báo lỗi thay vì âm thầm trôi.

### 10.2. Khởi tạo file khóa

Ở project **đã bật `dependencyLocking`**, chạy:

~~~bash
./gradlew dependencies --write-locks
./gradlew clean test bootJar
~~~

`dependencies --write-locks` tạo/cập nhật lock state cho **các configurations có locking đã được resolve**. Trên project đơn module cơ bản, lệnh này phù hợp để sinh lần đầu; có thể chạy thêm:

~~~bash
./gradlew test bootJar --write-locks
~~~

để đảm bảo các configurations phục vụ các tasks thật sự được resolve trong quá trình ghi lock. Các lệnh `--write-locks` **được phép sửa lockfile**; không dùng chúng trong CI verify thông thường.

Sau khi tạo, commit `gradle.lockfile` cùng build scripts. Lockfile thường nằm ở root của từng project/subproject; một multi-project build có thể có nhiều `gradle.lockfile` riêng. **Lưu ý:** trong multi-project build, `./gradlew dependencies` từ root thường chỉ chạy report cho root, không bảo đảm mọi subproject configurations đã được resolve. Có thể gọi `:service:dependencies`, `:shared:dependencies` hoặc tạo task resolve-all riêng, rồi kiểm các lockfiles đã sinh.

### 10.3. gradle.lockfile có dạng gì?

Đây là **ví dụ mô hình cấu trúc**, không phải kết quả byte-for-byte của project ở mục 9; version chính xác phải do Gradle sinh từ dependency resolution thực tế:

~~~text
# This is a Gradle generated file for dependency locking.
com.example:library-a:1.2.3=compileClasspath,runtimeClasspath
com.example:library-b:2.4.6=runtimeClasspath
empty=annotationProcessor
~~~

Mỗi dòng chứa `group:name:version` đã lock và danh sách configurations tham gia; dòng `empty` biểu diễn configurations đã resolve nhưng không có dependencies. **Không copy file ví dụ này** thành lockfile của project thật. Hãy chạy Gradle `--write-locks` để sinh file có dependencies thực, sau đó review diff và commit.

### 10.4. Build sau khi có lockfile

Trong CI chạy bình thường:

~~~bash
./gradlew --no-daemon clean test bootJar
~~~

Không thêm `--write-locks`: nếu dependency resolution không tương thích với trạng thái khóa, build cần **fail** và báo thay đổi phải được review. Cần lưu ý Gradle lock state chỉ áp dụng cho những configurations được resolve và có locking enabled.

### 10.5. Cập nhật dependencies có chủ đích

Khi nâng Boot từ một release lên một release khác, cần chỉnh:

1. Plugin `id("org.springframework.boot") version "..."`.
2. BOM `spring-boot-dependencies:...`.
3. Các dependencies/constraints được pin ngoài BOM khi có.
4. Regenerate locks trên **những configurations bị ảnh hưởng**, sau đó xem toàn bộ diff và chạy tests.

Ví dụ selective lock update:

~~~bash
./gradlew dependencies \
  --update-locks org.apache.commons:commons-lang3
~~~

`--update-locks` yêu cầu Gradle cập nhật một module cụ thể (có thể kéo thay đổi transitive liên quan); không đảm bảo mọi module liên quan đều ở phiên bản cũ nếu resolver bắt buộc thay. **Không dùng lệnh này để tự nâng Spring Boot BOM plugin**; nó chỉ áp dụng dependency locks, không update plugin version đã pin trong `plugins`.

### 10.6. Những điều lockfile không khóa

Gradle dependency locking **không đồng nghĩa**:

- Pin Gradle Wrapper/JDK distribution.
- Pin tất cả versions của plugins resolve trong `plugins` block.
- Kiểm SHA của mọi artifact tải xuống.
- Lock source dependencies, local file dependencies hoặc mọi external tool.
- Bảo đảm artifact JAR không thay đổi khi build scripts tạo nội dung từ ngày/giờ.
- Ngăn mọi drift nếu project dùng changing modules (`-SNAPSHOT`, mutable coordinates) mà bytes tại cùng version đã thay đổi.

Tài liệu Gradle cảnh báo **không dùng dependency locking với changing versions** để mong tái lập nội dung. Lock GAV không thể kiểm soát artifact bytes bị publish lại dưới cùng tọa độ.

## 11. Plugin versions: tách khỏi library dependency versions

### 11.1. Maven: version của plugin và plugin dependencies

Một Maven build dùng compiler/Surefire/JAR plugin do lifecycle gọi và các plugins được cấu hình thêm. Version của `spring-boot-maven-plugin` **không bằng** “version tất cả dependencies của ứng dụng”; một số plugin có dependencies riêng.

Các hướng kiểm soát:

- Dùng `spring-boot-starter-parent` hoặc corporate parent có `pluginManagement` được duy trì.
- Pin plugins dùng trực tiếp tại `<build><plugins>` hoặc quản lý tại `pluginManagement`.
- Kiểm `mvn help:effective-pom` và quan sát plugin goal/version trong build log.
- Tránh plugin CLI gọi theo “latest” vô tình dùng phiên bản mới ở máy CI.
- Với build yêu cầu kiểm rất chặt, xem quy tắc Maven Enforcer `requirePluginVersions` và chính sách plugin dependencies; không bật Enforcer rule đó mù quáng khi lifecycle/super-POM chưa được quản lý đầy đủ.

Maven `dependencyManagement` của project **không tự quản lý mọi dependency bên trong plugin realm**. Khi plugin tự kéo dependencies, cần nhìn plugin metadata/config nếu có yêu cầu audit hoặc conflict.

### 11.2. Gradle: version của plugin marker và classpath

Trong Gradle Kotlin DSL:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.5.16"
}
~~~

Version pin trong block `plugins` là **plugin version**. Với project multi-module, có thể quản lý version ở root settings `pluginManagement`, version catalog hoặc convention plugin classpath, rồi áp dụng theo module. **Gradle dependency lockfile của application configurations không tự khóa mọi plugin implementation artifacts hoặc wrapper distribution**.

Không dùng:

~~~kotlin
plugins {
    id("org.springframework.boot") version "+"
}
~~~

Cấu hình này là **anti-pattern minh họa**, không nên copy. Cố định version và kiểm plugin repository/provenance.

### 11.3. Annotation processors và test tools

Nếu project dùng Lombok, MapStruct hoặc `spring-boot-configuration-processor`, dependencies của `annotationProcessor` path **cũng ảnh hưởng output compile**. Trong Maven, đặt compiler annotation processor paths với versions rõ ràng/managed; trong Gradle, khai báo `annotationProcessor(...)` và bật lock cho configuration được resolve.

Một lớp Java không đổi có thể sinh khác khi Lombok/MapStruct processor version thay đổi. Tương tự, phiên bản test engine/Surefire/Gradle Test worker có thể làm thay đổi tập tests chạy và báo cáo.

## 12. Không dùng dynamic, SNAPSHOT hay mutable repositories cho release build

### 12.1. Các cách khai báo dễ gây drift

| Cấu hình | Vấn đề | Thay bằng |
| --- | --- | --- |
| Maven `<version>[1.0,2.0)</version>` | Version range có thể chọn bản mới khi repository thay đổi | Version được chọn/phê duyệt cụ thể |
| Maven `LATEST` hoặc `RELEASE` | Phụ thuộc metadata hiện tại, không phù hợp build cố định | Version literal/BOM có version cụ thể |
| Maven `1.0-SNAPSHOT` | Bytes có thể đổi sau cùng một tọa độ | Release immutable version hoặc digest/provenance |
| Gradle `implementation("x:y:1.+")` | Chọn bản mới theo metadata/cache | Version cụ thể + Gradle locking |
| Gradle `latest.release` | Phụ thuộc repository state | Explicit version |
| Gradle `changing = true` | Cho phép artifact thay bytes cùng coordinates | Immutable release repositories |
| Container image tag `jdk:17` | Tag có thể đổi underlying image digest | Image digest khi cần cấp tái lập cao |
| Plugin version `+` | Build tasks có thể đổi mà source không đổi | Pinned plugin release |

Trong giai đoạn phát triển, SNAPSHOT/dynamic versions có thể hữu ích để tích hợp nhanh. Nhưng **khi chuẩn bị release**, nên tạo release artifacts immutable và kiểm tra versions/graph, không coi local cache là nguồn chân lý.

### 12.2. Version được pin vẫn chưa đủ nếu artifact bytes thay

Ví dụ một repository nội bộ cho phép upload lại `com.example:lib:1.0.0` với nội dung khác. Maven/Gradle hôm nay và hôm qua có thể cùng báo **version 1.0.0** nhưng dùng hai JAR không giống nhau. Giải pháp là **repository không cho overwrite release**, artifact checksums/signatures, trusted mirrors, provenance và dependency verification ở mức byte.

Dùng `--offline` không chứng minh build tái lập: nó chỉ dùng thứ đã cache, có thể che metadata cũ hoặc thiếu dependency. **Build tái lập phải có khả năng giải thích đầy đủ nguồn và danh tính của mọi artifact được resolve**, kể cả trên một runner sạch có thể truy cập repository tin cậy.

### 12.3. Repository order và cache

Hai Maven settings files có mirrors khác nhau, hoặc Gradle có repositories cùng chứa một GAV nhưng bytes khác nhau, đều tạo nguồn bất định. Với doanh nghiệp, xác định repository proxy/mirror thống nhất và kiểm rules cho release vs snapshot.

Không dùng `mvn -U` hay `./gradlew --refresh-dependencies` như cách “khóa version”. Chúng tác động cache/revalidation, không thay dependency management/lock policy. Sau khi refresh vẫn cần đọc graph và bảo đảm bytes khớp nguồn đáng tin cậy.

## 13. So sánh dependency graph và artifact thực tế

### 13.1. Maven diagnostics

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
jar tf target/version-lock-maven-1.0.0.jar
~~~

`effective-pom` cho biết parent, plugins và management sau Maven model merge. `dependency:tree` cho biết version selection và scopes. `jar tf` kiểm tra **những files đã đóng vào archive**, không chỉ graph metadata.

Một executable Boot JAR thường có:

~~~text
BOOT-INF/classes/com/example/lockdemo/VersionLockApplication.class
BOOT-INF/lib/spring-boot-*.jar
org/springframework/boot/loader/launch/JarLauncher.class
~~~

Dấu `*` ở dòng file Spring Boot chỉ là ký hiệu “nhiều version filenames” trong ví dụ. Kiểm các tên thật với `jar tf`, không coi `spring-boot-*.jar` là tên một entry literal.

### 13.2. Gradle diagnostics

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-boot
./gradlew clean test bootJar
jar tf build/libs/version-lock-gradle-1.0.0.jar
~~~

Nếu lệnh dùng Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency spring-boot
.\gradlew.bat clean test bootJar
~~~

`dependencyInsight` cho biết vì sao resolver chọn một version. `gradle.lockfile` mô tả trạng thái khóa; nó không thay báo cáo dependency graph hay test runtime verification.

### 13.3. Kiểm hash của hai lần build

Linux/macOS:

~~~bash
sha256sum target/version-lock-maven-1.0.0.jar
sha256sum build/libs/version-lock-gradle-1.0.0.jar
~~~

Trên macOS không có `sha256sum` mặc định, có thể dùng:

~~~bash
shasum -a 256 target/version-lock-maven-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\version-lock-maven-1.0.0.jar -Algorithm SHA256
Get-FileHash .\build\libs\version-lock-gradle-1.0.0.jar -Algorithm SHA256
~~~

**Không so trực tiếp hash Maven JAR với Gradle JAR của hai build recipes khác nhau rồi kết luận có lỗi**: tên/layout/metadata/plugin packaging có thể khác. Hãy so **cùng một recipe** trên hai môi trường, cùng source, cùng tools/input, rồi điều tra khi checksum khác.

## 14. Muốn bit-for-bit reproducible: xử lý timestamp và generated contents

### 14.1. Maven reproducible archive timestamp

Ví dụ POM có:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Một số Maven plugins hiện đại, gồm các archive plugins và Spring Boot repackager, dùng property này để chuẩn hóa timestamps trong output. Ngày `2026-01-01T00:00:00Z` là một **giá trị cố định minh họa**; nhóm có thể dùng commit time/SOURCE_DATE_EPOCH chuẩn hóa theo quy trình của mình.

**Không hứa tính reproducible tuyệt đối chỉ với property này**: một resource generated ghi `System.currentTimeMillis()`, Git dirty state, file order hoặc metadata riêng vẫn làm JAR đổi.

### 14.2. Gradle archive tasks

Ví dụ ở mục 9:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Cấu hình này khiến các archive tasks Gradle hỗ trợ có file timestamps được chuẩn hóa và file order ổn định, giảm khác biệt ZIP/JAR giữa các máy. Nhưng nội dung `.class` hoặc generated files vẫn có thể khác do compiler/JDK/annotation processor hoặc build script logic.

### 14.3. Kiểm output thực, không chỉ log SUCCESS

Quy trình thử:

1. Checkout cùng commit ở hai môi trường sạch.
2. Dùng Wrapper, đúng JDK/toolchain/CI image và repositories.
3. Chạy tests/build bằng command giống nhau.
4. Kiểm dependency graphs và plugin versions.
5. Lấy SHA-256 của artifact output và so sánh.
6. Nếu khác, inspect ZIP entries, timestamps, generated resources, build-info, manifest và bytecode; không chỉ so file size.

Khi artifact khác nhưng business tests vẫn pass, đó vẫn có thể là lỗi reproducibility **nếu** hợp đồng phát hành yêu cầu identical digest. Ngược lại, một số build cố ý nhúng commit timestamp hoặc release signing data nên đầu ra có thể khác theo thiết kế; hãy ghi rõ **input nào được phép thay đổi**.

## 15. Bảo vệ nguồn cung và integrity khi khóa phiên bản

### 15.1. Wrapper là code chạy trước build

`mvnw`, `gradlew` và wrapper JAR/scripts có quyền thực thi lệnh trên máy local/CI. Vì vậy:

- Commit các Wrapper files vào source control.
- Xem diff khi nâng Maven/Gradle release.
- Kiểm `distributionUrl` không trỏ đến mirror lạ không được phê duyệt.
- Lấy checksum SHA-256 từ nguồn chính thức cho distribution; kiểm riêng wrapper JAR khi có.
- Không download/execute wrapper scripts trực tiếp từ một địa chỉ lạ trên mỗi CI job.
- Quản lý repository credentials bằng secret store, không commit tokens vào properties.

### 15.2. Dependency verification là một tầng khác

Gradle có cơ chế **dependency verification** (`gradle/verification-metadata.xml`) để kiểm metadata về checksums/signatures của resolved artifacts. Nó **bổ sung** cho `gradle.lockfile`: lockfile khóa coordinates/versions, còn verification metadata giúp phát hiện khi bytes/signatures không khớp kỳ vọng.

Maven build thông thường kiểm tính nhất quán checksum theo repository/download policy và có thể bổ sung cơ chế artifact verification/signing trong supply-chain workflow. Đừng nói rằng BOM hoặc `dependency:tree` cung cấp kiểm SHA toàn diện mặc định.

### 15.3. Một bản dựng có thể “quá cũ”

Pin mãi version không đồng nghĩa an toàn. Nếu một dependency có CVE nghiêm trọng, **phải cập nhật có kế hoạch**. Chính sách tốt cần kết hợp:

- Stable, reviewable dependency upgrades.
- Vulnerability scanning/SBOM và kiểm license.
- CI regression/security tests.
- Đánh dấu release artifacts immutable.
- Ghi nhận nguyên nhân đổi version và rollback strategy.
- Một source of truth cho Java, wrapper, plugins, BOM/lockfile theo từng repo.

Khóa phiên bản giúp **dễ kiểm soát thay đổi**, không phải lý do trì hoãn security fixes.

## 16. CI/CD: xác minh phiên bản thay vì chỉ tin README

### 16.1. Quy trình Maven

Một pipeline trung lập với CI provider có thể có các bước shell:

~~~bash
java -version
./mvnw -version
./mvnw -B -ntp clean verify
jar tf target/version-lock-maven-1.0.0.jar
sha256sum target/version-lock-maven-1.0.0.jar
~~~

CI nên cấp JDK 17 theo chính sách (nếu Enforcer ràng buộc `[17,18)`) **trước khi** gọi wrapper. Maven Wrapper chỉ chọn Maven version; không tự cài hoặc chọn Java runtime của Maven.

### 16.2. Quy trình Gradle

~~~bash
java -version
./gradlew --version
./gradlew -q javaToolchains
./gradlew --no-daemon clean test bootJar
jar tf build/libs/version-lock-gradle-1.0.0.jar
sha256sum build/libs/version-lock-gradle-1.0.0.jar
~~~

CI phải có Java toolchain phù hợp hoặc configured toolchain download repositories. Không thêm `--write-locks` vì job verify **không được cập nhật trạng thái dependency đã review**. Nếu lock sai, cần build fail và người phụ trách tạo PR cập nhật lock.

### 16.3. Khi dùng container image

Một ví dụ policy:

~~~text
Source commit:
    fixed Git revision

Build command:
    ./mvnw -B -ntp clean verify
    hoặc ./gradlew --no-daemon clean build

Build image:
    pinned by immutable digest

JDK:
    Java 17 vendor + patch stated in image manifest

Artifacts:
    published with SHA-256 and build provenance
~~~

Đây là **mô tả policy**, không phải Dockerfile/cấu hình CI có thể chạy độc lập. Không đưa một container digest giả vào tài liệu; digest phải lấy từ image thật sau khi doanh nghiệp chọn và kiểm nguồn.

## 17. Troubleshooting: tại sao đã khóa mà vẫn khác?

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra / xử lý |
| --- | --- | --- |
| Local Maven 3.9.x, CI Maven 3.8.x | CI gọi `mvn` thay vì `./mvnw` | Chạy `./mvnw -version` ở cả hai; sửa pipeline |
| Maven wrapper tải bản Maven ngoài dự kiến | `distributionUrl` sai hoặc wrapper properties chưa commit | Review `.mvn/wrapper`, verify version/SHA |
| Gradle wrapper reports 8.14.3 nhưng CI dùng Gradle 9 | CI gọi `gradle` hệ thống | Chuyển sang `./gradlew`, in `--version` |
| Plugin tự nâng dù dependency BOM không đổi | Plugin version dynamic/unmanaged | Pin plugin trong `plugins`/`pluginManagement`, đọc effective config |
| Java compile pass local, fail CI `invalid target release: 17` | JDK dùng compile thiếu release 17 | In Java/Javac versions; dùng JDK 17+ hoặc toolchain đúng |
| Artifact báo `UnsupportedClassVersionError` | Runtime Java cũ hơn classfile hoặc dependency được compile bằng Java mới | Kiểm runtime JDK, `--release` và dependency requirements |
| Maven Enforcer Java rule fail dưới JDK 21 | Policy yêu cầu `[17,18)` | Cấp JDK 17 để build hoặc chỉnh policy có review |
| Maven Spring Boot BOM đã khóa nhưng transitive thay | Dependency ngoài BOM, range, repository mutable, graph đổi | `dependency:tree`, effective POM, pin offending deps |
| Gradle báo dependency lock out of date | POM/BOM/dependency thay nhưng lockfile chưa cập nhật | Review change; chạy `--write-locks` trong PR, không cập nhật lén ở CI |
| Gradle lockfile vắng mặt | Chưa chạy `--write-locks` hoặc configuration chưa resolve | Chạy `dependencies --write-locks` và test/bootJar; kiểm file sinh |
| Multi-project có lockfile root nhưng app không được khóa | Root `dependencies` không resolve các subproject | Resolve `:app:dependencies`/tasks liên quan, commit lockfile per module |
| Boot Gradle plugin pin nhưng starter thiếu version | Không nhập Boot BOM qua platform/dependency management | Thêm `platform(...)`/plugin phù hợp và kiểm `dependencyInsight` |
| Build dùng `-SNAPSHOT` khác bytes dù GAV giống | Snapshot/changing dependency bị publish lại | Dùng immutable releases, verification và versioned artifacts |
| Wrapper SHA fail | Checksum/version/URL không khớp hoặc bytes bị can thiệp | So source chính thức, không vô hiệu hóa integrity check |
| JAR hash khác nhưng dependency graph giống | ZIP timestamp, file ordering, generated build-info, JDK patch | Dùng reproducible archive options, kiểm generated files |
| Repo offline vẫn pass, CI clean fail | Local cache che dependency/repository thiếu hoặc metadata cũ | Kiểm repository access/credentials, dùng runner sạch với nguồn tin cậy |
| Maven root và child dùng khác Boot versions | Parent/BOM/plugin version lệch hoặc child override | `help:effective-pom`, centralized management, tests |
| Gradle `--refresh-dependencies` làm khác build | Repository metadata thay, dynamic/changing modules | Cố định versions, khóa và verify artifacts, không phụ thuộc cache |
| Cùng artifact filename nhưng nội dung khác | Build output bị ghi đè mà không tăng version | Immutable artifact repositories, SHA/provenance, fail overwrite |
| Sau khi update Java major, tests khác behavior | JDK runtime/locale/time zone/crypto providers khác | Chạy tests trên runtime target, khóa environment và ghi release notes |

### 17.1. Sáu câu hỏi chẩn đoán theo thứ tự

**1. Source có thật sự cùng commit không?** Kiểm Git commit và working tree, submodules, generated source inputs.

**2. Build tool có đúng wrapper không?** Chạy `./mvnw -version`/`./gradlew --version` chứ không chỉ `mvn -version` hoặc đọc README.

**3. Java compiler/runtime có đúng không?** Đối chiếu `java -version`, `javac -version`, Maven Enforcer/Toolchains và Gradle Toolchains.

**4. Plugin versions có cố định không?** Đọc effective POM, Gradle plugins/settings/build-logic; xem annotation processors và test plugins.

**5. Dependency graph/bytes có khớp không?** Maven tree/Gradle lockfile, resolved versions, repositories và artifact verification.

**6. Đầu ra khác tại đâu?** Nếu build vẫn pass nhưng hash khác, mở archive và phân tích timestamp, file order và generated content; không tự kết luận lỗi từ version management.

## 18. Bài tập thực hành kèm đáp án định hướng

**Bài 1 — Wrapper vs Maven hệ thống.** Máy local có Maven 3.9.16, CI có Maven hệ thống phiên bản khác. Lệnh nào bảo đảm dự án dùng Maven Wrapper version?  
**Đáp án:** `./mvnw clean verify` hoặc `.\mvnw.cmd clean verify`; phải commit Wrapper và cấu hình distribution đã chọn, rồi kiểm `./mvnw -version`.

**Bài 2 — Java --release.** Maven chạy JDK 21, `maven.compiler.release=17`. Có nghĩa ứng dụng được chạy dưới JDK 17 trong production không?  
**Đáp án:** Không. Compiler target 17, nhưng Java runtime production là cấu hình deploy riêng. Enforcer của ví dụ còn yêu cầu Maven chạy Java 17 nên Maven dưới Java 21 sẽ bị từ chối vì policy.

**Bài 3 — BOM vs dependency.** Parent import `spring-boot-dependencies:3.5.16`, nhưng child không khai báo `spring-boot-starter`. Starter có tự có trong runtime không?  
**Đáp án:** Không. BOM cung cấp managed versions, child vẫn phải khai báo dependencies sử dụng.

**Bài 4 — Maven có gradle.lockfile?** Project Maven 3 chỉ import BOM nhưng muốn lock tất cả transitive GAV. Có một lệnh native `mvn --write-locks` tương đương Gradle không?  
**Đáp án:** Không. Maven 3 không có cơ chế lockfile dependency built-in giống Gradle. Dùng pinned versions/BOM/Enforcer, lưu tree/SBOM và giải pháp phụ trợ khi cần.

**Bài 5 — Gradle khóa versions.** Thêm `dependencyLocking { lockAllConfigurations() }` nhưng chưa thấy `gradle.lockfile`. Bước còn thiếu?  
**Đáp án:** Resolve các configurations bằng task phù hợp với `--write-locks`, kiểm lockfiles sinh và commit; không chỉ bật block DSL.

**Bài 6 — Plugin chưa khóa.** `gradle.lockfile` có đầy đủ Spring library versions, nhưng Spring Boot Gradle Plugin dùng dynamic version. Có an toàn chưa?  
**Đáp án:** Chưa. Plugin resolution/implementation classpath cần version rõ; dependency locking application không tự pin Boot plugin.

**Bài 7 — SNAPSHOT.** Hai builds có cùng `com.example:client:1.0-SNAPSHOT` nhưng bytes khác nhau. Lockfile có đủ để kết luận reproducible không?  
**Đáp án:** Không. Coordinate không bảo đảm artifact immutable; cần release version/digest verification/repository policy.

**Bài 8 — Hash khác.** Maven/Gradle dependencies cùng versions nhưng JAR hash khác. Kiểm gì trước?  
**Đáp án:** Cùng source/recipe/toolchains, timestamps/ZIP file ordering, generated resources, Git metadata, environment; sau đó so artifact entries. Không thể đổ hết cho dependencies.

**Bài 9 — Security update.** Một library được pin có CVE. Có nên giữ mãi chỉ vì lockfile?  
**Đáp án:** Không. Nâng version có kiểm soát, cập nhật lock/BOM, chạy security scan/regression tests và review diff.

**Bài 10 — Multi-module Gradle.** Root có `gradle.lockfile`, subproject `:service` resolve dependencies riêng. Có chắc mọi subproject đã khóa không?  
**Đáp án:** Không. Locking là theo project/configuration; kiểm state cho từng subproject và resolve những configurations thực sự dùng.

## 19. Checklist chốt bản dựng

- [ ] Source revision, build scripts và generated inputs có kiểm soát trong Git.
- [ ] JDK compiler/runtime được chọn rõ ràng; Java language/API target đặt bằng `--release` khi phù hợp.
- [ ] Maven/Gradle Wrapper được commit đầy đủ và CI **thực sự chạy qua wrapper**.
- [ ] Wrapper distribution URL/version được pin và SHA-256 được xác minh theo nguồn phát hành.
- [ ] Spring Boot build plugin và những plugins khác có versions cụ thể, không dùng dynamic release.
- [ ] Spring Boot parent/BOM version cụ thể; các dependencies ngoài BOM được quản lý tường minh.
- [ ] Gradle dependency locking đã bật, tạo `gradle.lockfile` cho đúng configurations/projects và commit.
- [ ] Với Maven, hiểu BOM/dependencyManagement không tương đương dependency lockfile tự sinh.
- [ ] Không có version ranges/dynamic/SNAPSHOT ngoài chính sách release đã phê duyệt.
- [ ] Dependency repositories không cho overwrite immutable releases; kiểm checksum/signature/provenance khi cần.
- [ ] Build reproducible archive options đã được cân nhắc, generated files không nhúng dữ liệu thay đổi ngoài kiểm soát.
- [ ] CI in tool versions, kiểm dependency graph, chạy tests và lưu SHA-256 artifact/release metadata.
- [ ] Có quy trình nâng Java/Wrapper/plugins/BOM/dependency lock bằng PR review và rollback.
- [ ] Không lưu secrets vào `pom.xml`, `gradle.properties`, wrapper properties hoặc logs.

## 20. Tài liệu chính thức

- Spring Boot 3.5 — System Requirements (Java/Maven/Gradle): https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Apache Maven — Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven — Maven Wrapper Plugin Usage: https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html
- Apache Maven — Compiler Plugin / --release: https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- Apache Maven — Toolchains Plugin: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Apache Maven — Enforcer RequireJavaVersion: https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html
- Apache Maven — Enforcer RequireMavenVersion: https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html
- Apache Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Gradle — Wrapper and Checksum Verification: https://docs.gradle.org/8.14.3/userguide/gradle_wrapper.html
- Gradle — Java Toolchains: https://docs.gradle.org/8.14.3/userguide/toolchains.html
- Gradle — Dependency Locking: https://docs.gradle.org/8.14.3/userguide/dependency_locking.html
- Gradle — Managing Dependencies/Platforms: https://docs.gradle.org/8.14.3/userguide/platforms.html
- Gradle — Dependency Verification: https://docs.gradle.org/8.14.3/userguide/dependency_verification.html
- Gradle — Reproducible Archives: https://docs.gradle.org/8.14.3/userguide/working_with_files.html#sec:reproducible_archives

**Tóm tắt:** Khóa **Java**, **Wrapper**, **plugin** và **dependency** là một hệ thống, không phải một con số. Maven dùng parent/BOM, plugin versions, Wrapper và kiểm tra policy; Gradle bổ sung `gradle.lockfile` cho resolved dependencies. Muốn build thực sự tái lập, phải khóa và xác minh cả nguồn artifact, toolchain, môi trường và archive contents; sau mỗi cập nhật được review, chạy lại tests và kiểm đầu ra thay vì dựa vào cảm giác “hôm qua đã build được”.