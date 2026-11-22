# Không ghi lại toolchain trong dự án Java

**Không ghi lại toolchain** là anti-pattern xảy ra khi nhóm chỉ lưu source code và lệnh build, nhưng không lưu hoặc không kiểm soát phiên bản các công cụ thực sự tạo ra artifact. Mỗi máy có thể dùng JDK, Gradle/Maven, compiler, plugin và dependency khác nhau. Build vẫn có thể thành công ở cả hai máy nhưng sinh bytecode, metadata, dependency graph hoặc kết quả test khác nhau.

Một bản ghi toolchain tốt phải trả lời được hai câu hỏi: **dự án yêu cầu môi trường nào để build**, và **lần build cụ thể đã thực sự dùng môi trường nào**. Câu thứ nhất là cấu hình có thể review trong repository; câu thứ hai là provenance được ghi lại trong CI hoặc build report. Thiếu một trong hai khiến lỗi khó tái hiện và khó giải thích.

## 1. Toolchain gồm những thành phần nào?

Trong Java, toolchain không chỉ là phiên bản Java được ghi trong `pom.xml` hoặc `build.gradle`.

| Thành phần | Ví dụ | Vì sao cần ghi |
| --- | --- | --- |
| Build tool | Gradle 9.2.1, Maven 3.9.12 | Khác phiên bản có thể thay đổi lifecycle, task, dependency resolution hoặc plugin compatibility |
| JVM chạy build tool | Azul Zulu JDK 24.0.2 | Chạy Gradle daemon/Maven và các plugin không dùng toolchain riêng |
| JDK compiler | Amazon Corretto 17.0.15 | Quyết định compiler thực tế, language features và bytecode |
| Java release target | `--release 17` | Xác định language/API level và class-file target |
| Test/runtime JDK | JDK 17, 21 hoặc 24 | Có thể khác compiler JDK; ảnh hưởng test và runtime behavior |
| Build plugins | Compiler Plugin 3.13.0, Surefire 3.5.2 | Plugin cũng là một phần của build logic |
| Dependencies | Thư viện trực tiếp và bắc cầu | Version được resolve có thể đổi theo thời gian |
| OS và architecture | Windows 11/amd64, Ubuntu Linux/arm64 | Ảnh hưởng native tools, file system, line ending và artifact |
| CI/container image | Runner label hoặc image digest | Image có thể được cập nhật dù workflow không đổi |
| Build environment | Locale, timezone, encoding, JVM flags | Có thể làm thay đổi test, generated file và output |

Cần phân biệt các khái niệm sau:

- **Build JVM** là JVM chạy chính Gradle/Maven.
- **Compiler toolchain** là JDK cung cấp `javac` cho việc compile.
- **Test launcher** là JVM chạy test.
- **Release target** là phiên bản Java mà compiler phải tuân thủ về cú pháp, bytecode và API công khai.
- **Runtime production** là JRE/JDK thực tế chạy ứng dụng sau khi deploy.

Các thành phần này có thể cùng phiên bản, nhưng không bắt buộc phải giống nhau. Ví dụ, Gradle có thể chạy trên JDK 24, dùng compiler/test toolchain JDK 17 và tạo class tương thích Java 17.

## 2. Vì sao không ghi lại toolchain gây lỗi?

### Build xanh nhưng artifact khác nhau

Developer A dùng JDK 17, developer B dùng JDK 24. Cả hai đều đặt source/target hoặc `maven.compiler.release` thành 17. Nếu compiler JDK không được kiểm soát, khác biệt về compiler implementation, plugin, generated metadata và môi trường vẫn có thể xuất hiện.

### Lỗi chỉ tái hiện trên một máy

Một build phụ thuộc trạng thái `JAVA_HOME`, `PATH`, IDE JDK hoặc `~/.m2/toolchains.xml` mà repository không mô tả sẽ khiến người khác không biết compiler hoặc test JVM nào đã được chọn.

### Nâng cấp công cụ ngoài ý muốn

Lệnh `gradle build` dùng Gradle cài toàn cục. Máy có Gradle 8.5 có thể chạy build khác với máy có Gradle 9.2.1. Tương tự, `mvn package` có thể dùng Maven khác nhau trên từng máy.

### Dependency và plugin tự thay đổi

Version động như `1.+`, `latest.release`, version range hoặc plugin không được pin có thể resolve sang bản mới vào ngày khác. Một build không thay đổi source vẫn có thể nhận dependency graph khác.

### Không đủ bằng chứng để điều tra release

Khi production gặp lỗi, chỉ có JAR và commit ID là chưa đủ. Nhóm cần biết JDK, compiler, build tool, plugin, dependency, OS, command và build parameters đã tạo ra JAR đó.

## 3. Ghi những thông tin nào?

Một toolchain manifest cho mỗi lần build nên có các trường sau:

1. Commit SHA và trạng thái working tree.
2. Lệnh build, task/goal, Maven profile và build flags.
3. Build tool cùng version thực tế; wrapper distribution URL và checksum nếu có.
4. JVM chạy build tool: version đầy đủ, vendor và runtime.
5. Compiler JDK: language version, vendor và version đầy đủ khi có thể.
6. Test JVM và runtime JDK nếu khác compiler.
7. Java release/source/target được cấu hình.
8. Version các build plugin và dependency đã resolve.
9. OS, OS version, CPU architecture và container image digest.
10. Locale, timezone, file encoding và các JVM flags có ảnh hưởng.
11. CI provider, runner image/label, workflow revision và version action.
12. Checksum của artifact đầu ra và dependency verification metadata khi áp dụng.

Không phải mọi thông tin đều cần lưu trong một file. Wrapper và build file lưu các yêu cầu ổn định; report CI lưu thông tin quan sát được; lockfile và verification metadata lưu dependency state. Có thể kết hợp chúng thành một build provenance report.

**Không đưa secret vào report.** Không dump toàn bộ environment variables, Maven `settings.xml`, token, password, private key hoặc nội dung credential. Chỉ ghi các biến đã chọn lọc và loại bỏ giá trị nhạy cảm.

## 4. Kiểm tra toolchain đang được sử dụng

Chạy các lệnh sau từ repository root để biết môi trường hiện tại.

### Java và compiler

```bash
java --version
javac --version
```

Trên Windows PowerShell:

```powershell
Get-Command java, javac
where.exe java
where.exe javac
```

`java --version` cho biết runtime được gọi qua `PATH`; `javac --version` cho biết compiler được gọi qua `PATH`. Các lệnh này chưa chứng minh Gradle hoặc Maven đang dùng cùng JDK, vì build tool có thể chọn daemon JVM hoặc toolchain riêng.

### Gradle

```bash
./gradlew --version
./gradlew javaToolchains
```

Trên Windows:

```powershell
.\gradlew.bat --version
.\gradlew.bat javaToolchains
```

`--version` hiển thị Gradle version và thông tin JVM launcher/daemon. `javaToolchains` liệt kê JDK mà Gradle phát hiện, gồm version, vendor, architecture và installation location. Nếu dự án dùng Java Plugin, hãy chạy task này để xác nhận toolchain thực tế có sẵn.

### Maven

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree
```

Có thể liệt kê JDK toolchains mà Maven phát hiện:

```bash
./mvnw toolchains:display-discovered-jdk-toolchains
```

Goal khám phá JDK có trong Maven Toolchains Plugin từ version 3.2.0. `mvn -version` cho biết JVM chạy Maven; nếu Maven Toolchains chọn một JDK khác cho compiler hoặc Surefire, log chọn toolchain mới cho biết JDK được dùng ở các plugin tương ứng.

## 5. Pin build tool bằng Wrapper

Wrapper lưu phiên bản build tool trong repository và giúp mọi developer/CI gọi cùng một distribution.

### Gradle Wrapper

Commit các file wrapper vào Git:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

Ví dụ `gradle/wrapper/gradle-wrapper.properties`:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.2.1-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

`distributionUrl` phải trỏ tới một phiên bản cụ thể. Có thể thêm `distributionSha256Sum` với SHA-256 chính thức của distribution để Wrapper xác minh file tải xuống. Lấy checksum từ trang release checksums độc lập với file ZIP; không tự lấy checksum của một file chưa được xác minh rồi xem đó là bằng chứng tin cậy.

Dùng Wrapper:

```bash
./gradlew clean check
```

Windows:

```powershell
.\gradlew.bat clean check
```

Không dùng `gradle build` trong tài liệu dự án hoặc CI khi repository đã có Wrapper. Lệnh đó phụ thuộc Gradle cài toàn cục.

### Maven Wrapper

Commit các file Maven Wrapper, gồm `mvnw`, `mvnw.cmd`, wrapper JAR và `.mvn/wrapper/maven-wrapper.properties`. Trong file properties, đặt `distributionUrl` tới một Maven distribution version cụ thể, ví dụ Maven 3.9.12.

Chạy:

```bash
./mvnw --batch-mode clean verify
```

Windows:

```powershell
.\mvnw.cmd --batch-mode clean verify
```

Maven Wrapper pin Maven distribution. JDK chạy Maven vẫn phải được thiết lập và kiểm tra riêng bằng `JAVA_HOME`, CI setup hoặc Maven Enforcer. Nếu compiler cần một JDK khác, cấu hình Maven Toolchains.

## 6. Phân biệt Gradle daemon JVM, compiler JDK và release target

Gradle có thể dùng JVM khác nhau cho client, daemon, compiler và test. JVM khởi chạy Wrapper/Gradle client thường được xác định qua `JAVA_HOME`, `PATH` hoặc IDE. Daemon có thể dùng JVM được chỉ định bởi `org.gradle.java.home`, Tooling API hoặc daemon JVM criteria. Java toolchain của project điều khiển compiler, test và Javadoc tasks.

Ví dụ `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
```

Ở đây, Gradle chọn JDK 17 cho các task Java của project; `options.release = 17` bảo đảm compiler tuân thủ Java 17 API/language level. Nếu muốn yêu cầu vendor cụ thể, có thể thêm `vendor = JvmVendorSpec.ADOPTIUM` hoặc vendor phù hợp với chính sách dự án.

Không nhầm `options.release` với toolchain. `--release 17` không cài JDK 17, không chọn `javac` 17 và không điều khiển JVM chạy Gradle. Nó điều khiển cách compiler biên dịch source.

### Ghi build JVM và toolchain vào report

Gradle cung cấp `JavaToolchainService` để truy vấn compiler và launcher đã chọn. Có thể tạo task ghi report vào `build/reports/toolchain/toolchain.txt`:

```groovy
def toolchains = extensions.getByType(
    org.gradle.jvm.toolchain.JavaToolchainService
)

tasks.register('toolchainReport') {
    doLast {
        def compiler = toolchains.compilerFor(java.toolchain).get()
        def launcher = toolchains.launcherFor(java.toolchain).get()

        def compilerMetadata = compiler.metadata
        def launcherMetadata = launcher.metadata

        def lines = [
            "gradle.version=" + gradle.gradleVersion,
            "build.jvm.version=" + System.getProperty('java.version'),
            "build.jvm.vendor=" + System.getProperty('java.vendor'),
            "compiler.language.version=" + compilerMetadata.languageVersion,
            "compiler.vendor=" + compilerMetadata.vendor,
            "launcher.language.version=" + launcherMetadata.languageVersion,
            "launcher.vendor=" + launcherMetadata.vendor,
            "java.release=17",
            "os.name=" + System.getProperty('os.name'),
            "os.arch=" + System.getProperty('os.arch')
        ]

        def output = layout.buildDirectory
            .file('reports/toolchain/toolchain.txt')
            .get()
            .asFile

        output.parentFile.mkdirs()
        output.setText(
            lines.join(System.lineSeparator()) + System.lineSeparator(),
            'UTF-8'
        )

        println(lines.join(System.lineSeparator()))
    }
}
```

Có thể thêm một chương trình Java nhỏ để ghi full runtime version của test launcher. Tệp `src/main/java/com/example/ToolchainProbe.java`:

```java
package com.example;

public final class ToolchainProbe {
    private ToolchainProbe() {
    }

    public static void main(String[] args) {
        System.out.println("runtime.version=" + Runtime.version());
        System.out.println("runtime.vendor=" + System.getProperty("java.vendor"));
        System.out.println("runtime.vm=" + System.getProperty("java.vm.name"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
    }
}
```

Đăng ký task chạy chương trình bằng toolchain đã chọn:

```groovy
tasks.register('toolchainProbe', JavaExec) {
    dependsOn tasks.named('classes')
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.ToolchainProbe'
    javaLauncher = toolchains.launcherFor(java.toolchain)
}
```

Chạy và lưu report:

```bash
./gradlew toolchainReport toolchainProbe javaToolchains
```

Ví dụ đã kiểm tra trên Windows 11: Gradle 9.2.1 chạy bằng Azul Zulu JDK 24.0.2, nhưng project chọn Amazon Corretto JDK 17.0.15 cho compiler và launcher. `options.release` cũng là 17.

```text
gradle.version=9.2.1
build.jvm.version=24.0.2
build.jvm.vendor=Azul Systems, Inc.
compiler.language.version=17
compiler.vendor=Amazon Corretto
launcher.language.version=17
launcher.vendor=Amazon Corretto
java.release=17
os.name=Windows 11
os.arch=amd64

runtime.version=17.0.15+6-LTS
runtime.vendor=Amazon.com Inc.
os.name=Windows 11
os.arch=amd64
```

Đây là ví dụ cụ thể cho thấy build JVM, compiler/test JDK và release target là ba thông tin riêng biệt. Nếu cần pin patch version hoặc vendor tuyệt đối, CI cần provision đúng distribution/version và report version đầy đủ; `languageVersion = 17` chỉ chỉ định Java major version.

### Ghi lại Gradle daemon JVM

Trong Gradle, `gradlew --version` giúp xem JVM launcher và daemon. Với Gradle hỗ trợ daemon JVM criteria, task `updateDaemonJvm` có thể tạo file `gradle/gradle-daemon-jvm.properties` để khai báo yêu cầu JVM của daemon:

```bash
./gradlew updateDaemonJvm --jvm-version=17
```

Commit file criteria nếu dự án dùng cơ chế này và kiểm tra tương thích với Gradle Wrapper version. Khi dùng `org.gradle.java.home`, tránh commit đường dẫn tuyệt đối trên máy developer; đường dẫn đó thường khác trên CI và máy của người khác.

## 7. Ghi Maven runtime và JDK toolchain riêng biệt

`mvn -version` cho biết Maven version và Java runtime đang chạy Maven. Nếu Maven Toolchains được cấu hình, compiler, Surefire, Javadoc hoặc JAR Plugin có thể sử dụng một JDK khác.

### Khóa Maven và JDK chạy Maven bằng Enforcer

Ví dụ POM yêu cầu Maven 3.9.x và Maven runtime JDK 24:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.6.3</version>
  <executions>
    <execution>
      <id>enforce-build-runtime</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <requireMavenVersion>
            <version>[3.9,4)</version>
          </requireMavenVersion>
          <requireJavaVersion>
            <version>[24,25)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
```

Điều chỉnh range theo support policy. `requireJavaVersion` kiểm tra JVM chạy Maven; nó không tự chọn compiler JDK nếu Maven Toolchains được cấu hình riêng.

### Chọn JDK compiler bằng Maven Toolchains

Trong `pom.xml`, khai báo JDK mà các plugin toolchain-aware phải sử dụng:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.3.0</version>
  <executions>
    <execution>
      <goals>
        <goal>toolchain</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <toolchains>
      <jdk>
        <version>17</version>
        <vendor>Amazon Corretto</vendor>
      </jdk>
    </toolchains>
  </configuration>
</plugin>
```

Mỗi developer/runner khai báo đường dẫn JDK trên máy của mình trong `~/.m2/toolchains.xml`. Ví dụ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>Amazon Corretto</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/corretto-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
```

`jdkHome` là đường dẫn cài JDK trên máy hiện tại. Đường dẫn này thuộc cấu hình local/runner; repository chỉ khai báo tiêu chí version/vendor để tránh buộc mọi máy dùng cùng một absolute path.

Maven Toolchains Plugin tìm cấu hình phù hợp rồi cung cấp JDK cho các plugin có hỗ trợ toolchain. Khi chạy, log cho biết JDK được chọn:

```bash
./mvnw --batch-mode verify
```

Nếu không tìm thấy toolchain phù hợp, build nên thất bại sớm ở phase `validate` với thông báo rõ ràng. Không tiếp tục compile bằng JDK ngẫu nhiên trong `PATH`.

### Release vẫn là một cấu hình riêng

Trong Maven Compiler Plugin:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
    <encoding>UTF-8</encoding>
  </configuration>
</plugin>
```

`release` kiểm soát source/API/bytecode target; Maven Toolchains chọn JDK thực tế cho compiler. Nếu Maven chạy bằng JDK 24 và toolchain chọn JDK 17, log có thể thể hiện cả hai version. Đây là cấu hình hợp lệ khi project đã xác định rõ lý do và compatibility policy.

### Ví dụ Maven đã kiểm tra

Môi trường thử nghiệm dùng Maven 3.9.12 chạy trên Azul Zulu JDK 24.0.2. Maven Enforcer xác nhận đúng Maven/JDK runtime; Maven Toolchains Plugin 3.3.0 chọn Amazon Corretto JDK 17.0.15; Compiler Plugin 3.13.0 compile với `release 17`; Surefire 3.5.2 và JAR Plugin 3.4.2 cũng nhận toolchain JDK 17. Build `package` thành công.

## 8. Pin plugin và dependency versions

Wrapper pin build tool, nhưng không tự pin mọi plugin hoặc dependency. Cần ghi rõ version trong build configuration.

### Gradle

Dùng version catalog để tập trung version:

```toml
[versions]
junit = "5.11.4"
spotbugs = "6.0.26"

[libraries]
junit-bom = { module = "org.junit:junit-bom", version.ref = "junit" }
```

Khai báo plugin version rõ ràng trong `plugins` block hoặc plugin management. Tránh version động như `1.+`, `latest.release` hoặc snapshot không có kiểm soát.

Bật dependency locking cho các configuration:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sinh/cập nhật lock state khi chủ động thay đổi dependency:

```bash
./gradlew dependencies --write-locks
```

Commit `gradle.lockfile` và review diff khi lockfile thay đổi. Locking lưu resolved dependency versions, gồm dependency bắc cầu. Với buildscript/plugin classpath, cần cấu hình locking tương ứng nếu muốn khóa cả build logic.

Có thể bật dependency verification để kiểm tra checksum/chữ ký của artifact được tải về:

```bash
./gradlew --write-verification-metadata sha256
```

Lệnh này tạo `gradle/verification-metadata.xml`. Hãy tạo metadata từ dependency đã được xác minh, review checksum/signature và commit file. Không chấp nhận mù toàn bộ checksum vừa bootstrap từ repository có thể đã bị xâm phạm.

### Maven

Maven project nên:

- Khai báo version dependency tập trung trong `dependencyManagement` hoặc BOM.
- Pin version của build plugin trong `pluginManagement` hoặc `plugins`.
- Tránh `LATEST`, `RELEASE`, version range rộng và dependency `SNAPSHOT` trong release build.
- Dùng Enforcer để kiểm tra Maven/JDK requirements và các quy tắc dự án.
- Lưu `help:effective-pom` và `dependency:tree` khi cần điều tra build cụ thể.

Maven không có dependency lockfile tích hợp theo cùng cách Gradle. Vì vậy, cần khai báo version rõ ràng, quản lý transitive dependencies qua BOM/`dependencyManagement`, cố định plugin versions và lưu dependency tree của release khi cần truy vết.

## 9. Ghi nhận toolchain trong CI

CI nên chạy Wrapper, cài đúng JDK distribution/version và lưu report cùng build artifacts. Ví dụ GitHub Actions cho Gradle:

```yaml
name: Java Build Provenance

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle

      - name: Record build JVM and compiler discovery
        run: |
          java --version
          javac --version
          ./gradlew --version
          ./gradlew javaToolchains

      - name: Build and write toolchain report
        run: ./gradlew --no-daemon clean toolchainReport toolchainProbe check

      - name: Record source revision
        run: |
          git rev-parse HEAD
          git status --short

      - name: Upload provenance report
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: java-toolchain-report
          path: build/reports/toolchain/toolchain.txt
          if-no-files-found: ignore
```

Ví dụ Maven dùng cùng nguyên tắc:

```yaml
- name: Set up JDK
  uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: maven

- name: Record Maven runtime
  run: |
    java --version
    javac --version
    ./mvnw --version

- name: Show discovered Maven JDK toolchains
  run: ./mvnw toolchains:display-discovered-jdk-toolchains

- name: Build
  run: ./mvnw --batch-mode --no-transfer-progress clean verify
```

`actions/setup-java` có thể cài JDK distribution/version, thiết lập `JAVA_HOME`, cập nhật `PATH`, cache Maven/Gradle dependencies và tạo Maven Toolchains entries. Nếu dự án yêu cầu vendor cụ thể, cấu hình vendor trong action và toolchain requirement cho khớp.

Với release quan trọng, có thể dùng matrix OS/JDK. Ghi lại runner OS/architecture thực tế và container image digest nếu build chạy trong container. Runner label như `ubuntu-latest` có thể trỏ tới image được cập nhật theo thời gian; provenance cần ghi image version/digest để điều tra chính xác.

Nếu supply-chain policy yêu cầu kiểm soát mạnh hơn, pin GitHub Actions bằng commit SHA đã xác minh, kiểm tra Wrapper JAR, xác minh Gradle distribution checksum và dùng JDK archive có checksum/chữ ký được xác thực.

## 10. Reproducible build và toolchain report

Ghi lại toolchain giúp tái hiện môi trường, nhưng bản ghi không tự làm build reproducible. Muốn tạo lại artifact byte-for-byte, còn cần kiểm soát:

- Source revision và trạng thái working tree.
- Build tool, JDK, compiler, plugin và dependency versions.
- OS/architecture, locale, timezone và line ending.
- Timestamp và file order trong archive.
- Generated metadata không phụ thuộc username, absolute path hoặc thời gian hiện tại.
- Repository/mirror và dependency checksums.

Với Gradle, kết hợp Wrapper, toolchains, dependency locking và dependency verification. Với Maven, kết hợp Wrapper, Enforcer, Maven Toolchains, plugin/dependency version pinning và `project.build.outputTimestamp` cho plugin hỗ trợ reproducible archive.

Ví dụ Maven:

```xml
<properties>
  <project.build.outputTimestamp>2026-11-10T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Build hai lần trong môi trường tương đương rồi so sánh SHA-256. Nếu hash khác, kiểm tra timestamp, manifest, generated files, tool versions, resolved dependency graph và OS newline. Maven reproducible-build guide cũng lưu ý build trên Windows và Unix có thể khác nhau do CRLF/LF nếu nội dung chưa được chuẩn hóa.

Toolchain manifest là bằng chứng về môi trường; lockfile và verification metadata kiểm soát dependency; reproducible-build checks xác nhận artifact có thể được tạo lại. Ba phần hỗ trợ lẫn nhau nhưng giải quyết các vấn đề khác nhau.

## 11. Ví dụ một build provenance report

Một report ngắn gọn có thể trông như sau:

```text
build.tool=Gradle 9.2.1
build.jvm=Azul Zulu 24.0.2
compiler.toolchain=Amazon Corretto 17.0.15
test.launcher=Amazon Corretto 17.0.15
java.release=17
os=Windows 11
architecture=amd64
source.revision=<commit-sha>
build.command=./gradlew clean toolchainReport toolchainProbe check
dependency.lock=gradle.lockfile
dependency.verification=gradle/verification-metadata.xml
```

Giá trị commit, command và đường dẫn metadata phải được sinh từ build thực tế. Không copy một report cũ rồi sửa version bằng tay. Nếu report được upload lên CI, giữ nó cùng artifact, test reports và checksum để người điều tra có thể ghép đúng lần build.

Với Maven, report nên ghi riêng `mvnw --version` và toolchain selection log, vì Maven runtime và compiler JDK có thể khác nhau.

## 12. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ ghi `Java 17` trong README | Không biết vendor, patch version, compiler hay runtime đã dùng | Ghi đầy đủ build JVM, compiler/test toolchain và release target |
| Chỉ dùng `--release 17` | Có thể compile bằng JDK khác nhau | Cấu hình toolchain riêng |
| Chạy `gradle build` hoặc `mvn package` toàn cục | Build tool version phụ thuộc máy | Commit và dùng Wrapper |
| Dựa vào IDE JDK | Local và CI có thể chọn JDK khác | Đặt toolchain trong build file và CI |
| Không ghi Gradle daemon JVM | Không biết JVM nào thực thi build logic | Chạy `gradlew --version` và kiểm tra daemon criteria |
| Nghĩ `mvn -version` cho biết compiler JDK | Bỏ sót Maven Toolchains đã chọn JDK khác | Ghi toolchain selection từ Maven log/plugin |
| Không pin plugin version | Build thay đổi khi plugin metadata thay đổi | Khai báo version tường minh |
| Dùng dependency version động trong release | Dependency graph thay đổi theo thời gian | Gradle lockfile hoặc Maven dependencyManagement/BOM |
| Chỉ lưu log `BUILD SUCCESS` | Không đủ dữ liệu để tái hiện | Lưu toolchain report, commit SHA và dependency state |
| Ghi toàn bộ environment variables | Có thể làm lộ secret/token | Chỉ ghi whitelist an toàn và redact giá trị nhạy cảm |
| Commit absolute JDK path của máy cá nhân | Máy khác không có cùng đường dẫn | Dùng toolchain requirement và local mapping |
| Dùng `latest` trong CI | Cùng workflow nhưng runner cài version khác | Pin distribution/version hoặc image digest |

## 13. Troubleshooting khi toolchain không khớp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Unsupported class file major version` | Build tool/plugin không hỗ trợ JDK chạy build hoặc bytecode đầu vào quá mới | Kiểm tra Gradle/Maven runtime và plugin versions |
| Compiler báo API không tồn tại | JDK compiler hoặc `--release` không đúng | Kiểm tra toolchain compiler và release target |
| Local pass, CI fail | CI cài JDK/build tool khác hoặc OS khác | So sánh provenance report, runner image và command |
| Gradle dùng JDK khác `JAVA_HOME` | Daemon JVM criteria, IDE hoặc toolchain chọn runtime khác | Chạy `./gradlew --version`, `javaToolchains`, kiểm tra IDE |
| Maven dùng JDK khác terminal | Maven Wrapper/`JAVA_HOME` hoặc Maven Toolchains | Chạy `./mvnw --version`, xem log `toolchains:toolchain` |
| Toolchain không tìm thấy | Chưa cài JDK phù hợp hoặc version/vendor không khớp | Chạy `javaToolchains` hoặc `toolchains:display-discovered-jdk-toolchains` |
| Dependency đổi dù source không đổi | Dynamic version, SNAPSHOT hoặc thiếu lock | Kiểm tra Gradle lockfile hoặc Maven dependency tree |
| JAR hash khác giữa hai build | Timestamp, OS newline, generated metadata hoặc plugin khác | So sánh report và kiểm tra archive entries |
| Build chạy đúng local nhưng IDE khác | IDE Gradle JVM/Maven runner JDK khác terminal | Kiểm tra IDE build delegation và JDK settings |

Khi gặp lỗi, so sánh hai provenance report trước. Chỉ thay đổi một lớp tại một thời điểm: build tool, build JVM, compiler toolchain, dependency hoặc OS. Sau khi build thành công, lưu report mới cùng artifact để lần điều tra tiếp theo có bằng chứng.

## 14. Checklist thiết lập toolchain cho dự án Java

1. Chọn JDK baseline và runtime support matrix.
2. Xác định vendor/patch version có cần cố định hay chỉ cần Java major version.
3. Commit Gradle/Maven Wrapper và pin distribution version.
4. Xác minh checksum distribution/Wrapper theo chính sách bảo mật.
5. Cấu hình Gradle Java toolchain hoặc Maven Toolchains.
6. Đặt `options.release` hoặc `maven.compiler.release` rõ ràng.
7. Ghi riêng build JVM, compiler JDK và test/runtime JDK.
8. Pin plugin versions và dependency versions.
9. Bật Gradle dependency locking/verification nếu phù hợp.
10. Dùng Maven Enforcer để kiểm tra Maven/JDK runtime requirements.
11. Thiết lập CI để cài đúng JDK distribution/version và dùng Wrapper.
12. Tạo toolchain report chứa commit, build command, versions, OS và architecture.
13. Upload report cùng test reports và build artifacts.
14. Kiểm tra reproducibility bằng build lặp lại và so sánh checksum.
15. Review report để bảo đảm không chứa credential, token hoặc dữ liệu nhạy cảm.

## 15. Ghi nhớ

- Toolchain gồm build tool, build JVM, compiler JDK, test/runtime JDK, plugins, dependencies và môi trường OS/CI.
- `--release 17` xác định API/language/bytecode target; nó không chọn compiler JDK.
- Gradle client, daemon, compiler và test launcher có thể chạy bằng các JVM khác nhau.
- Maven `-version` ghi JVM chạy Maven; Maven Toolchains có thể chọn JDK khác cho compiler/Surefire/Javadoc.
- Wrapper pin Gradle/Maven distribution; Enforcer kiểm tra yêu cầu Maven/JDK; toolchains chọn JDK thực tế.
- Pin plugin/dependency versions và lưu lock state để tránh dependency graph thay đổi âm thầm.
- Gradle dependency verification kiểm tra checksum/chữ ký artifact; chỉ tin metadata đã được review.
- CI cần lưu OS/architecture, JDK distribution/version, build tool, commit SHA, command và toolchain report.
- Không ghi secret hoặc toàn bộ environment vào build report.
- Reproducible build cần kiểm soát cả toolchain, dependency, timestamp, file order và generated metadata.

Khi toolchain được khai báo, kiểm tra và ghi lại cùng mỗi lần build, nhóm có thể giải thích vì sao hai môi trường cho kết quả khác nhau, tái tạo artifact của release và nâng cấp công cụ theo cách có kiểm soát.

## Tài liệu tham khảo

- [Gradle: Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle: Daemon JVM Toolchains and criteria](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle: Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle: Securing the Build Tool and distribution checksum](https://docs.gradle.org/current/userguide/securing_build_tool.html)
- [Gradle: Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle: Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Maven: Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Maven: Toolchains Plugin Usage](https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html)
- [Maven: JDK Toolchain configuration](https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk.html)
- [Maven: Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Maven Compiler Plugin: Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)
- [Maven: Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
