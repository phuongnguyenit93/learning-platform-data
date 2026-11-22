# Xác định mục tiêu build cho dự án Java

## 1. Mục tiêu build là gì?

Mục tiêu build (build goal) mô tả kết quả mà dự án cần tạo ra từ source code và các đầu vào đã xác định. Nó trả lời những câu hỏi:

- Cần tạo sản phẩm gì: library JAR, executable JAR, WAR, application distribution hay container image?
- Artifact phải chạy trên phiên bản Java, hệ điều hành và kiến trúc nào?
- Những bước nào phải hoàn tất trước khi coi build là thành công?
- Chất lượng nào cần được chứng minh: compile, test, static analysis, dependency checks, packaging hay signature?
- Artifact được lưu ở đâu, đặt tên ra sao và ai sẽ sử dụng?
- Làm thế nào để developer khác hoặc CI có thể lặp lại build và xác nhận kết quả?

Một build goal tốt mô tả kết quả có thể kiểm chứng. “Build ứng dụng Java” còn mơ hồ. Mục tiêu cụ thể hơn là: “Tạo executable JAR orders-cli-1.0.0.jar, biên dịch bằng Java 17 API, chạy được trên Java 17 trở lên, có Main-Class, vượt qua unit test và có checksum SHA-256 trong CI”.

Mục tiêu build định hướng cấu hình toolchain, build tool, task, dependency, kiểm thử và artifact. Chọn Maven hay Gradle trước khi hiểu đầu ra cần tạo thường dẫn tới cấu hình thừa hoặc thiếu.

## 2. Phân biệt build goal, build task và release goal

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Build goal | Cần đạt kết quả nào? | Tạo library JAR tương thích Java 17 và chạy test. |
| Build task/phase | Công cụ phải thực hiện việc gì? | compileJava, test, jar, Maven package. |
| Release goal | Cần chuẩn bị artifact để phân phối ra sao? | Ký JAR, tạo checksum, SBOM và publish repository. |

Một goal có thể cần nhiều task. Mục tiêu tạo executable JAR cần compile class, xử lý resource, tạo manifest, đóng gói và kiểm tra lệnh chạy.

Build cũng khác deploy ứng dụng. Maven phase deploy thường chuyển artifact lên remote repository; nó không đồng nghĩa triển khai service lên production. Deploy ứng dụng là hoạt động vận hành riêng, có thể dùng container platform, application server hoặc hệ thống release.

## 3. Bắt đầu từ người dùng và sản phẩm cần tạo

Hãy xác định ai sẽ dùng đầu ra của build:

| Người nhận | Artifact thường cần | Tiêu chí quan trọng |
|---|---|---|
| Developer dùng trong project khác | Library JAR, POM/module metadata | API, dependency metadata, version. |
| Người dùng chạy command line | Executable JAR hoặc application distribution | Entry point, runtime dependency, arguments. |
| Người dùng cài desktop app | Installer hoặc OS-specific package | Native launcher, runtime, icon, permissions. |
| CI/CD pipeline | JAR, ZIP, image, reports | Đầu ra xác định, kiểm thử, checksum, provenance. |
| Release repository | Versioned artifacts | Coordinates, signature, SBOM, immutable version. |

Không phải mọi JAR đều cần Main-Class. Library JAR thường được nạp bởi ứng dụng khác. Ngược lại, executable JAR có Main-Class vẫn có thể không chạy được nếu thiếu dependency runtime.

Xác định sản phẩm trước sẽ giúp quyết định có cần manifest, fat JAR, application distribution, module path hay installer.

## 4. Viết build contract trước khi cấu hình

Build contract là mô tả ngắn gọn về đầu vào, đầu ra và điều kiện chấp nhận của build. Có thể ghi thành bảng trong README dự án:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Source | Source revision nào được build? | Git commit đang checkout. |
| Build JDK | JDK nào chạy build tool/compiler? | Temurin JDK 21. |
| Runtime baseline | Ứng dụng cần chạy từ Java nào? | Java 17+. |
| Platform | Hệ điều hành/CPU nào được hỗ trợ? | Windows/Linux/macOS, x64. |
| Dependency | Dependency được quản lý thế nào? | Phiên bản được pin, không dùng snapshot trong release. |
| Output | Artifact nào phải được tạo? | orders-cli-1.0.0.jar. |
| Quality gates | Điều kiện nào phải pass? | Compile, unit tests, integration tests. |
| Reproducibility | Build có cần tái lập byte-for-byte? | Có đối với release JAR. |
| Security | Kiểm tra nào bắt buộc? | Dependency scan, license policy, signing. |
| Delivery | Artifact được lưu ở đâu? | CI artifact hoặc Maven repository. |

Build contract cần đủ cụ thể để người khác có thể chạy đúng lệnh và xác nhận đúng kết quả.

## 5. Các nhóm mục tiêu build thường gặp

Một dự án có thể chọn một hoặc nhiều nhóm:

1. **Compile goal:** xác nhận source biên dịch được bằng JDK và API mục tiêu.
2. **Test goal:** chạy unit, integration hoặc contract test cần thiết.
3. **Package goal:** tạo JAR, WAR, ZIP hoặc distribution.
4. **Verification goal:** kiểm tra cấu trúc archive, manifest, metadata, static analysis và quality rules.
5. **Compatibility goal:** xác nhận bytecode/API và runtime tương thích với phiên bản Java được hỗ trợ.
6. **Reproducibility goal:** cùng source và đầu vào đã pin tạo artifact có thể tái lập.
7. **Security goal:** kiểm tra dependency, vulnerability, license, secret và chữ ký theo policy.
8. **Performance goal:** giới hạn thời gian build và tài nguyên CI.
9. **Publication goal:** xuất artifact có version, checksum, SBOM và metadata phù hợp.
10. **Developer feedback goal:** giữ vòng lặp compile/test local nhanh và dễ chẩn đoán.

Không nhất thiết bật tất cả gate trong mọi lần chạy. Ví dụ, dependency vulnerability scan có thể chạy ở pull request và nightly; ký release chỉ chạy trong pipeline phát hành.

## 6. Đặt tiêu chí chấp nhận có thể đo được

Một goal chỉ hữu ích khi có thể trả lời rõ build đã đạt hay chưa. Tránh các mô tả như “build nhanh”, “chạy ổn định” hoặc “tương thích tốt” nếu không có tiêu chí đo.

Ví dụ tiêu chí chấp nhận:

- javac --release 17 compile thành công.
- Tất cả unit test bắt buộc pass; không có test bị bỏ qua ngoài danh sách được phê duyệt.
- mvn clean verify hoặc gradle clean build kết thúc với exit code 0.
- JAR có tên và version đúng.
- Executable JAR có manifest Main-Class đúng.
- JAR chạy được trên JDK 17 và JDK 21 nếu hai runtime này nằm trong phạm vi hỗ trợ.
- Dependency scan không có vulnerability vượt ngưỡng policy.
- Release artifact có SHA-256 và chữ ký hợp lệ nếu quy trình yêu cầu.
- Build release dùng dependency/tool version đã pin.
- Thời gian build nằm trong ngân sách đã thống nhất, ví dụ dưới 5 phút cho pull request trên runner chuẩn.

Tiêu chí phải phù hợp với sản phẩm. Library JAR không cần tiêu chí chạy java -jar; ứng dụng GUI có thể cần smoke test cài đặt và khởi chạy.

## 7. Chọn JDK chạy build và phiên bản Java mục tiêu

Cần phân biệt:

- **Build JDK:** JDK chạy Maven/Gradle và compiler.
- **Target release:** Java API và class file version mà source được biên dịch hướng tới.
- **Runtime JDK:** JDK mà người dùng hoặc môi trường triển khai dùng để chạy artifact.

Ví dụ dự án có thể chạy Gradle bằng JDK 21 nhưng tạo bytecode Java 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

toolchain chọn JDK dùng cho compile task. options.release giới hạn API Java mục tiêu và class file version. Chỉ đặt source/target mà không đặt release có thể cho phép code gọi API mới hơn runtime mục tiêu.

Với Maven, khai báo:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Và pin Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
~~~

Nếu cần compiler JDK khác JVM đang chạy Maven, cấu hình Maven Toolchains phù hợp. Đừng chỉ nhìn JAVA_HOME; kiểm tra JDK thực tế mà build tool và compiler sử dụng.

## 8. Xác định phạm vi nền tảng

Build goal nên ghi rõ nền tảng được hỗ trợ:

- Chỉ Java bytecode portable hay có JNI/JNA/native library?
- Có hỗ trợ Windows, Linux và macOS không?
- Hỗ trợ x64, ARM64 hay cả hai?
- Có phụ thuộc file permission, symbolic link, shell hoặc OS service không?
- Có yêu cầu installer riêng theo hệ điều hành không?

Nếu ứng dụng chỉ dùng API Java chuẩn, một JAR có thể chạy trên nhiều OS tương thích. Nếu có native library, artifact hoặc distribution có thể phải build riêng theo OS/architecture.

Đừng ghi “cross-platform” nếu chỉ compile trên một runner. Với sản phẩm cam kết đa nền tảng, đưa các OS quan trọng vào CI matrix và kiểm tra runtime thực tế.

## 9. Chọn các bước build theo mục tiêu

Một pipeline Java phổ biến gồm:

~~~text
Source + configuration
        |
        v
Validate inputs and toolchain
        |
        v
Compile source
        |
        v
Process resources
        |
        v
Run unit tests
        |
        v
Package artifact
        |
        v
Verify artifact and quality gates
        |
        v
Publish or archive output
~~~

Không phải dự án nào cũng cần mọi bước ở mọi lần build. Nhưng phải xác định bước nào bắt buộc trước khi đánh dấu build thành công.

Ví dụ:

- Compile-only check có thể dùng cho vòng lặp nhanh.
- test chạy unit test.
- package tạo artifact.
- verify chạy các verification goal đã được cấu hình trong lifecycle.
- publish chuyển artifact tới repository hoặc registry nếu có cấu hình phù hợp.

Một build chỉ compile thành công chưa chứng minh test pass, JAR có thể chạy hoặc dependency runtime đã đầy đủ.

## 10. Chọn Maven hay Gradle theo nhu cầu

Maven phù hợp khi dự án cần convention rõ, lifecycle chuẩn và cấu hình XML quen thuộc. Gradle phù hợp khi cần task graph linh hoạt, build logic tùy biến hoặc cấu hình Kotlin/Groovy DSL.

| Nhu cầu | Maven | Gradle |
|---|---|---|
| Compile/package Java chuẩn | Compiler/JAR plugins và lifecycle | Java Plugin tasks |
| Chạy unit test | Surefire/Failsafe | Test task và JUnit Platform |
| Chọn JDK compiler | Maven Toolchains/Compiler Plugin | Java Toolchains |
| Tạo executable JAR | Maven JAR Plugin manifest | JAR task manifest |
| Tùy biến task graph | Plugin/phase configuration | Task graph và plugins |
| Dependency management | POM coordinates/scopes | Configurations/dependencies |
| Wrapper | Maven Wrapper | Gradle Wrapper |

Build goal quyết định cấu hình cần có. Đừng thêm plugin hoặc task chỉ vì dự án khác đang dùng nó. Mỗi thành phần cần phục vụ một đầu ra hoặc quality gate cụ thể.

## 11. Ví dụ build contract cho ứng dụng CLI

Giả sử cần build một công cụ command line:

| Yêu cầu | Tiêu chí |
|---|---|
| Sản phẩm | Executable JAR |
| Java tối thiểu | Java 17 |
| Build JDK | JDK 21 |
| Entry point | com.example.BuildGoalDemo |
| Input | Arguments từ command line |
| Output | build-goal-demo-1.0.0.jar |
| Test | Unit test cho logic nghiệp vụ |
| Runtime dependencies | Được khai báo và phân phối đầy đủ |
| Kiểm tra | JAR list được và chạy bằng java -jar |
| Release | Version cố định, checksum và metadata |

Một acceptance test có thể chạy:

~~~bash
java -jar build-goal-demo-1.0.0.jar ci
~~~

Và kiểm tra stdout:

~~~text
Build goal: package a Java 17 application
Target: ci
~~~

Đây là một tiêu chí quan sát được. Nếu command kết thúc với exit code 0 và output đúng, smoke test đã xác nhận entry point hoạt động trong môi trường kiểm tra đó.

## 12. Ví dụ Java 17 có thể chạy độc lập

Tạo src/main/java/com/example/BuildGoalDemo.java:

~~~java
package com.example;

public final class BuildGoalDemo {
    private BuildGoalDemo() {
    }

    public static void main(String[] args) {
        String target = args.length == 0 ? "local" : args[0];
        System.out.println("Build goal: package a Java 17 application");
        System.out.println("Target: " + target);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d build/classes \
  src/main/java/com/example/BuildGoalDemo.java
~~~

Tạo executable JAR:

~~~bash
jar --create \
  --file build-goal-demo.jar \
  --main-class com.example.BuildGoalDemo \
  -C build/classes .
~~~

Chạy:

~~~bash
java -jar build-goal-demo.jar ci
~~~

Stdout chính xác:

~~~text
Build goal: package a Java 17 application
Target: ci
~~~

Ví dụ này có thể chạy độc lập, không cần thư viện ngoài. Nó chứng minh mục tiêu compile + package + executable entry point. Nó chưa thay thế unit test, dependency scan hay integration test của một ứng dụng thực tế.

## 13. Cấu hình Maven theo build goal

Ví dụ pom.xml cho CLI Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>build-goal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.BuildGoalDemo</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Build artifact:

~~~bash
mvn -B clean package
~~~

Chạy:

~~~bash
java -jar target/build-goal-demo-1.0.0.jar ci
~~~

Nếu goal yêu cầu test, thêm JUnit Jupiter và Maven Surefire Plugin. Nếu goal yêu cầu static analysis, dependency checks hoặc signing, cấu hình các plugin tương ứng và định nghĩa rõ ngưỡng pass/fail.

package tạo artifact. verify chạy thêm các verification goal đã cấu hình trong lifecycle; nếu dự án chưa cấu hình quality plugin, không nên giả định verify tự động chạy mọi loại scan.

## 14. Cấu hình Gradle theo build goal

Ví dụ build.gradle:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.named('jar', Jar).configure {
    manifest {
        attributes 'Main-Class': 'com.example.BuildGoalDemo'
    }
}
~~~

Build:

~~~bash
./gradlew clean jar
~~~

Trên Windows:

~~~powershell
.\gradlew.bat clean jar
~~~

Chạy:

~~~bash
java -jar build/libs/build-goal-demo-1.0.0.jar ci
~~~

Nếu goal yêu cầu test, cấu hình JUnit và useJUnitPlatform(). Gradle task check có thể gom các verification task, còn build thường phụ thuộc vào check và assemble.

Không nhầm assemble với check: một task tạo artifact, task còn lại kiểm tra chất lượng theo các task đã cấu hình.

## 15. Xác định test goal

Chọn loại test dựa vào rủi ro cần kiểm tra:

| Test type | Mục tiêu | Ví dụ |
|---|---|---|
| Unit test | Logic class/method | Validate input, tính toán, mapping. |
| Integration test | Kết nối thành phần | JDBC, filesystem, HTTP client. |
| Contract test | Tuân thủ interface/protocol | JSON schema, API contract. |
| Smoke test | Artifact khởi chạy được | java -jar app.jar --help. |
| End-to-end test | Luồng người dùng hoàn chỉnh | Gọi CLI hoặc REST workflow từ đầu tới cuối. |

Không phải mọi test cần chạy trong mọi lần build. Một cấu hình thường gặp:

- Pull request: compile, unit test, static checks.
- Main branch: unit + integration test, package và smoke test.
- Nightly: OS/JDK matrix rộng, end-to-end, performance test.
- Release: full verification, dependency/security scan, signing và checksum.

Ghi rõ test nào bắt buộc. Test skip phải có lý do, tránh để số lượng test bị bỏ qua tăng dần mà không ai nhận ra.

## 16. Xác định dependency và đầu vào build

Build chỉ có thể tái lập nếu đầu vào được kiểm soát.

Hãy xác định dependency trực tiếp và bắc cầu, phiên bản plugin, JDK vendor/version, toolchain, build properties, environment variables, resource được generate, repository dependency và native binary nếu có.

Tránh dependency version thay đổi không kiểm soát, snapshot không ổn định trong release và tải tool từ URL không được xác thực.

Với release, nên pin phiên bản plugin/dependency, dùng dependency locking khi phù hợp và ghi lại source revision cùng toolchain version.

Không đóng gói secret hoặc credential vào JAR. Secret nên được cấp ở runtime hoặc qua secret manager của môi trường triển khai.

## 17. Xác định mục tiêu artifact và naming

Artifact cần có danh tính rõ ràng:

- groupId: nhóm tổ chức hoặc namespace.
- artifactId: tên module.
- version: phiên bản sản phẩm.
- classifier: biến thể nếu có.
- packaging: JAR, WAR hoặc loại artifact khác.

Ví dụ Maven coordinates:

~~~text
com.example:orders-cli:1.4.0
~~~

Tên file thường là:

~~~text
orders-cli-1.4.0.jar
~~~

Đừng dùng tên chung như final.jar cho artifact phát hành. Tên và version giúp CI, người dùng và repository phân biệt bản build.

Nếu tạo nhiều biến thể, ghi rõ classifier hoặc quy ước phân phối, ví dụ linux-x64, windows-x64 hoặc sources. Chỉ tạo biến thể khi sản phẩm thực sự cần khác nhau.

## 18. Quality gates và security goals

Build thành công không đồng nghĩa artifact đã an toàn hoặc sẵn sàng phát hành. Hãy chọn gate theo mức rủi ro và policy của tổ chức.

Ví dụ:

- Compiler warnings hoặc lint rules.
- Unit/integration tests.
- Static analysis và code coverage threshold.
- Dependency vulnerability scan.
- License policy.
- Secret scanning.
- SBOM generation.
- Artifact signing và checksum.
- Container image scan nếu build container.

Định nghĩa ngưỡng rõ ràng, ví dụ không có critical vulnerability chưa được chấp nhận hoặc coverage không thấp hơn mức dự án đã thống nhất. Không chọn một ngưỡng tùy tiện rồi coi đó là chuẩn chung cho mọi dự án.

Các scan có thể cần mạng hoặc service ngoài. Ghi lại phiên bản database scan và thời điểm chạy để kết quả có thể giải thích. Không đưa API token hoặc signing key vào source code hoặc build log.

## 19. Reproducibility và traceability

Hai build từ cùng source có thể khác artifact nếu dependency, timestamp, file order hoặc generated metadata thay đổi.

Nếu mục tiêu yêu cầu reproducible build, hãy:

- Pin JDK, build tool, plugin và dependency.
- Chuẩn hóa archive timestamps và file order.
- Loại bỏ build time động khỏi manifest/resource.
- Kiểm soát locale, timezone và encoding.
- Tránh ghi absolute path hoặc username vào artifact.
- Build lại từ cùng source revision và so sánh SHA-256.

Traceability bổ sung thông tin để trả lời artifact được tạo từ đâu: Git commit/source revision, build JDK, build tool version, dependency lock, build run ID, checksum và chữ ký nếu áp dụng.

Reproducibility trả lời “có thể tạo lại cùng artifact không?”. Traceability trả lời “artifact này đến từ source và quy trình nào?”. Hai mục tiêu hỗ trợ nhau nhưng không giống nhau.

## 20. Cân bằng tốc độ build và độ tin cậy

Build nhanh giúp developer nhận feedback sớm; build release cần kiểm tra đầy đủ hơn.

| Mức chạy | Nội dung | Thời điểm |
|---|---|---|
| Fast feedback | Compile và unit test trọng yếu | Khi developer làm việc. |
| Pull request | Clean build, unit test, static checks | Trước merge. |
| Main branch | Integration test, package, smoke test | Sau merge. |
| Nightly | Matrix OS/JDK, E2E, performance, dependency scan | Theo lịch. |
| Release | Full verification, signing, SBOM, checksum | Trước phát hành. |

Dùng incremental build để tăng tốc vòng lặp local. Dùng clean build trong CI/release để kiểm tra artifact không phụ thuộc output cũ.

Không đánh đổi quality gate bắt buộc chỉ để giảm vài giây. Nếu build chậm, đo task nào tốn thời gian rồi tối ưu cache, parallelism hoặc test selection mà vẫn giữ mục tiêu chất lượng.

## 21. CI: chuyển build goal thành pipeline

CI phải thực hiện cùng contract đã mô tả trong dự án. Một workflow cơ bản:

~~~yaml
name: Java build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify
        run: ./mvnw -B clean verify

      - name: Upload JAR
        uses: actions/upload-artifact@v4
        with:
          name: build-output
          path: target/*.jar
~~~

Workflow này giả định repository có Maven Wrapper, project có thể build trên Ubuntu và Maven verify đã được cấu hình với các gate mong muốn.

Nếu hỗ trợ nhiều OS/JDK, dùng matrix. Nếu goal chỉ cần Java 17 runtime, hãy có job chạy thực sự bằng JDK 17; compile release 17 bằng JDK 21 không thay thế runtime test trên Java 17.

Không publish release artifact từ mọi pull request. Tách build verification và release publication bằng branch/tag, permission và approval policy phù hợp.

## 22. Kiểm tra artifact sau khi build

Sau khi build, kiểm tra đầu ra thực tế thay vì chỉ dựa vào thông báo BUILD SUCCESSFUL.

Liệt kê JAR:

~~~bash
jar --list --file target/build-goal-demo-1.0.0.jar
~~~

Kiểm tra manifest:

~~~bash
jar --extract --file target/build-goal-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Chạy executable JAR:

~~~bash
java -jar target/build-goal-demo-1.0.0.jar ci
~~~

Tính checksum trên PowerShell:

~~~powershell
Get-FileHash .\target\build-goal-demo-1.0.0.jar -Algorithm SHA256
~~~

Linux:

~~~bash
sha256sum target/build-goal-demo-1.0.0.jar
~~~

Nếu goal là library, kiểm tra coordinates, POM/module metadata và việc artifact được consumer project resolve. Nếu goal là application distribution, kiểm tra script launcher, dependency directory, config và permissions.

## 23. Lab: xác nhận cùng build goal bằng javac, Maven và Gradle

Ví dụ BuildGoalDemo.java ở phần 12 được dùng làm source chung. Mục tiêu lab là tạo executable JAR Java 17, chạy với argument ci và kiểm tra stdout.

**Cách 1 — JDK trực tiếp**

~~~bash
javac --release 17 -encoding UTF-8 -d build/classes src/main/java/com/example/BuildGoalDemo.java
jar --create --file build-goal-demo.jar --main-class com.example.BuildGoalDemo -C build/classes .
java -jar build-goal-demo.jar ci
~~~

**Cách 2 — Maven**

Dùng POM ở phần 13:

~~~bash
mvn -B clean package
java -jar target/build-goal-demo-1.0.0.jar ci
~~~

**Cách 3 — Gradle**

Dùng build file ở phần 14:

~~~bash
./gradlew clean jar
java -jar build/libs/build-goal-demo-1.0.0.jar ci
~~~

Cả ba cách cần đáp ứng cùng contract: compile target Java 17, JAR có main class và chương trình in đúng hai dòng output. Cách tổ chức output folder và metadata có thể khác nhau theo build tool.

## 24. Kết quả lab đã kiểm chứng

Fixture Java 17 đã được chạy trên Windows với JDK 24.0.2, Maven 3.9.12 và Gradle 9.2.1.

| Cách build | Kết quả | Kiểm tra |
|---|---|---|
| javac + jar | PASS | JAR chạy được bằng java -jar. |
| Maven Compiler 3.13.0 + JAR Plugin 3.4.2 | BUILD SUCCESS | Executable JAR chạy được. |
| Gradle 9.2.1 Java Plugin | BUILD SUCCESSFUL | Executable JAR chạy được. |

Stdout của cả ba artifact khi truyền argument ci:

~~~text
Build goal: package a Java 17 application
Target: ci
~~~

Các build dùng cùng source, --release 17 và manifest main class. Hash của JAR giữa ba build không được kỳ vọng giống nhau vì Maven và Gradle có thể thêm metadata khác nhau. Lab xác nhận cùng hành vi chạy và contract đầu ra, không tuyên bố byte-for-byte reproducibility.

## 25. Những sai lầm thường gặp khi xác định mục tiêu build

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ ghi “build project” | Không biết artifact và điều kiện pass. | Mô tả sản phẩm, đầu ra và acceptance criteria. |
| Nhầm Build JDK với target Java | Artifact có thể yêu cầu runtime mới hơn dự kiến. | Chọn toolchain và --release riêng. |
| Cho rằng mọi JAR đều executable | Library JAR bị coi nhầm là hỏng. | Phân biệt application JAR và library JAR. |
| Chỉ kiểm tra compile | Lỗi test/dependency/manifest lọt qua. | Thêm test, package và smoke verification. |
| Coi package là release | Artifact thiếu checksum, signature hoặc metadata. | Định nghĩa release goal riêng. |
| Không pin plugin/dependency | Build có thể thay đổi theo thời gian. | Pin version và quản lý dependency. |
| Chỉ chạy trên máy developer | Lỗi môi trường xuất hiện muộn trong CI. | Chạy CI trên môi trường được hỗ trợ. |
| Chạy clean ở mọi thao tác nhỏ | Vòng lặp local chậm. | Incremental local, clean CI/release. |
| Dùng exit code build làm tiêu chí duy nhất | Artifact có thể thiếu entry point hoặc dependency. | Kiểm tra artifact và chạy smoke test. |
| Không định nghĩa ai nhận artifact | Đầu ra không phù hợp nhu cầu sử dụng. | Bắt đầu từ consumer và cách phân phối. |

## 26. Mẫu build contract có thể áp dụng cho dự án

Có thể dùng mẫu sau trong tài liệu dự án hoặc pull request:

~~~text
Build purpose:
Primary consumer:
Artifact type:
Artifact name and version:
Build JDK and vendor:
Minimum runtime Java:
Target release:
Supported OS/architecture:
Dependency and plugin policy:
Required compile/test/verification tasks:
Runtime dependency strategy:
Reproducibility requirement:
Security and signing requirements:
Output location:
CI command:
Acceptance criteria:
Release/publish destination:
~~~

Điền từng mục bằng giá trị cụ thể. Nếu một mục không áp dụng, ghi rõ “không áp dụng” và lý do thay vì để người triển khai tự đoán.

Ví dụ acceptance criteria cho executable CLI:

1. Maven clean verify kết thúc exit code 0.
2. Artifact có tên orders-cli-1.0.0.jar.
3. Manifest có Main-Class đúng.
4. java -jar orders-cli-1.0.0.jar --help in usage và exit code 0.
5. Unit/integration tests bắt buộc pass.
6. Runtime dependency được đóng gói hoặc phân phối đầy đủ.
7. Release artifact có checksum và signature theo policy.

## 27. Tài liệu tham khảo

- [The javac Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [The jar Command — JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [Maven Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [GitHub Actions Matrix Builds](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)

Xác định mục tiêu build bằng cách bắt đầu từ sản phẩm và người dùng đầu ra, sau đó viết build contract với JDK, runtime baseline, artifact, quality gates và acceptance criteria. Khi kết quả cần đạt đã rõ, Maven hoặc Gradle mới được cấu hình để thực hiện và chứng minh những yêu cầu đó.