# Compile Java trong CI: build nhất quán từ commit tới artifact

**Compile trong CI (Continuous Integration)** là bước tự động biên dịch mã nguồn Java trên runner hoặc build agent sau mỗi lần push, pull request hoặc lần chạy pipeline được yêu cầu. CI lấy đúng commit, chuẩn bị JDK và build tool, khôi phục dependency, biên dịch source, chạy kiểm tra, đóng gói kết quả và lưu log/artifact để nhóm có thể xem lại.

Mục tiêu là phát hiện sớm lỗi compile, sai phiên bản JDK, thiếu dependency, annotation processor không tương thích và khác biệt giữa máy developer với môi trường build. Một pipeline tốt có thể chạy lại từ commit đã biết và tạo ra kết quả có thể giải thích, kiểm tra và tái tạo.

Bài học dùng Maven, Gradle và GitHub Actions làm ví dụ. Cùng nguyên tắc có thể áp dụng cho Jenkins, GitLab CI, Azure Pipelines, Buildkite hoặc runner nội bộ.

## 1. CI compile nằm ở đâu trong quy trình phát triển?

Một vòng CI phổ biến:

1. Developer push commit hoặc mở pull request.
2. CI checkout đúng commit và thiết lập môi trường build.
3. Cài/chọn JDK và build tool đã được dự án quy định.
4. Khôi phục dependency từ repository/cache.
5. Biên dịch source chính và source test.
6. Chạy unit test, static analysis và các kiểm tra chất lượng.
7. Đóng gói JAR/WAR hoặc artifact khác.
8. Lưu artifact, test report và log.
9. Báo trạng thái thành công/thất bại về pull request hoặc commit.

Compile là một phần của build. Một lần **javac** thành công chưa chứng minh ứng dụng đã sẵn sàng: test có thể thất bại, resource có thể thiếu, module có thể không được đóng gói, hoặc integration test có thể phát hiện lỗi khi chạy.

Thông thường CI nên chạy một lifecycle/task đủ rộng để compile, test và verify. Chỉ chạy compile khi mục đích thực sự là kiểm tra biên dịch nhanh.

## 2. Compile, test, package và verify khác nhau thế nào?

| Công việc | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Compile | Source có biên dịch được với JDK/API đã chọn không? | `mvn compile`, `./gradlew compileJava` |
| Test compile | Source test có biên dịch được không? | `mvn test-compile`, `./gradlew compileTestJava` |
| Test | Unit test có chạy và pass không? | `mvn test`, `./gradlew test` |
| Package | Có tạo được JAR/WAR không? | `mvn package`, `./gradlew jar` |
| Verify/check | Các kiểm tra gắn với lifecycle có pass không? | `mvn verify`, `./gradlew check` |
| Build | Tạo các output chính của dự án theo build tool | `./gradlew build` |

Với Maven, `compile` chạy các phase trước đó tới phase compile. `test` còn chạy compile source test và test runner. `package` đóng gói output; `verify` chạy toàn bộ các phase trước đó và những kiểm tra được gắn vào phase verify.

Với Gradle Java Plugin, `compileJava` biên dịch source chính, `compileTestJava` biên dịch test, `test` chạy test, `check` gom các verification task và `build` phụ thuộc cả `check` lẫn `assemble`.

Một CI job thường dùng `mvn verify` hoặc `gradle build`. Lệnh compile đơn lẻ phù hợp cho job compile-only hoặc bước phản hồi nhanh, nhưng không thay thế kiểm tra chất lượng trước khi merge.

## 3. Phân biệt JDK chạy build và phiên bản Java mục tiêu

Có ba khái niệm cần tách biệt:

- **JDK chạy Maven/Gradle:** JVM dùng để khởi động build tool và plugin.
- **JDK compiler/toolchain:** javac thực sự biên dịch source.
- **Java release mục tiêu:** phiên bản ngôn ngữ, bytecode và public Java API mà ứng dụng được phép sử dụng.

Ví dụ: CI có thể chạy Maven bằng JDK 21, compiler toolchain là JDK 21 và tạo bytecode cho Java 17. Khi đó compiler dùng `--release 17`.

`--release 17` kiểm soát cú pháp Java, class-file target và API Java SE có sẵn ở Java 17. Chỉ dùng `-source 17 -target 17` không cung cấp cùng mức kiểm tra API; code vẫn có thể vô tình gọi API mới hơn nếu compiler JDK có API đó.

Không nên suy luận phiên bản target chỉ từ `java -version`. Hãy kiểm tra cấu hình build và compiler thực tế.

## 4. Chọn JDK ổn định cho CI

JDK được chọn phải phù hợp với:

- Phiên bản Java mà ứng dụng hỗ trợ.
- Phiên bản Maven/Gradle và plugin.
- Annotation processor, compiler plugin và test framework.
- Hệ điều hành và kiến trúc runner.
- Chính sách hỗ trợ của nhóm.

Ví dụ, dự án target Java 17 có thể chạy CI chính bằng JDK 17. Nếu muốn kiểm tra tương thích trên runtime mới hơn, thêm matrix JDK 21 và 25. Giữ `--release 17` để compiler không dùng API mới hơn trong source.

Không dùng alias `latest` cho build phát hành cần tái lập. Pin Java major version, vendor/distribution và khi yêu cầu kiểm soát chặt hơn thì pin cả JDK build cụ thể hoặc image digest.

Có thể in môi trường ngay đầu job:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
~~~

`mvn -version` và `gradle --version` cho biết JVM mà build tool đang dùng. Nếu version khác dự kiến, kiểm tra `JAVA_HOME`, PATH, runner image và toolchain configuration.

## 5. Dùng Maven Wrapper hoặc Gradle Wrapper

Wrapper lưu cấu hình phiên bản build tool trong repository để developer và CI chạy cùng một bản Maven/Gradle mà không phụ thuộc phiên bản cài sẵn trên runner.

Maven Wrapper thường gồm:

~~~text
.mvn/
  wrapper/
    maven-wrapper.properties
mvnw
mvnw.cmd
~~~

Chạy trên Linux/macOS:

~~~bash
./mvnw --version
./mvnw --batch-mode --no-transfer-progress clean verify
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd --batch-mode --no-transfer-progress clean verify
~~~

`maven-wrapper.properties` cần chỉ rõ distribution URL. Với build nhạy cảm về integrity, cấu hình thêm checksum chính thức `distributionSha256Sum` lấy từ trang phát hành Maven. Commit wrapper scripts, wrapper JAR và properties theo hướng dẫn của Maven Wrapper.

Gradle Wrapper gồm `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties`.

~~~bash
./gradlew --version
./gradlew --no-daemon clean build
~~~

Pin `distributionUrl` vào phiên bản Gradle cụ thể và đặt `distributionSha256Sum` theo checksum phát hành. Commit đầy đủ wrapper files. Không để CI tự chọn một Gradle version bất kỳ từ runner.

Wrapper làm build tool nhất quán hơn, nhưng không tự pin JDK, dependency hoặc plugin. Các phần đó vẫn cần được cấu hình riêng.

## 6. Cấu hình Maven Compiler Plugin

Trong Maven, `maven-compiler-plugin` gọi javac để biên dịch source chính và source test. Khai báo rõ release, encoding và plugin version trong POM:

~~~xml
<properties>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <maven.compiler.release>17</maven.compiler.release>
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
  </plugins>
</build>
~~~

`release` là cấu hình quan trọng để không vô tình compile bằng API của JDK cao hơn. Pin plugin version để kết quả không phụ thuộc default plugin version mà Maven chọn.

Nếu dự án có nhiều module, đặt compiler plugin và Java release ở parent POM hoặc `pluginManagement` để các module dùng chung cấu hình. Kiểm tra effective POM nếu một module kế thừa cấu hình khác mong đợi.

## 7. Maven lifecycle trong CI

Các lệnh thường dùng:

~~~bash
# Chỉ biên dịch source chính
./mvnw --batch-mode compile

# Biên dịch cả source test
./mvnw --batch-mode test-compile

# Compile và chạy unit test
./mvnw --batch-mode test

# Tạo artifact sau khi chạy test
./mvnw --batch-mode package

# Chạy đầy đủ lifecycle tới verify
./mvnw --batch-mode clean verify
~~~

`clean` xóa output build cũ để lần chạy bắt đầu từ trạng thái sạch. `verify` chạy các phase trước đó, gồm compile, test compile, test và package, cùng những verification goal được cấu hình trong dự án.

Hai tùy chọn skip test thường bị nhầm:

- `-DskipTests`: bỏ thực thi test, nhưng test source vẫn được compile.
- `-Dmaven.test.skip=true`: bỏ cả test compile lẫn test execution.

Không dùng skip option trong CI merge gate nếu mục tiêu là xác nhận chất lượng. Chỉ dùng khi có một job chuyên biệt và lý do rõ ràng.

`--batch-mode` tắt tương tác, phù hợp với runner. `--no-transfer-progress` giảm log download dài. `--errors` hiển thị stack trace lỗi Maven khi cần.

## 8. Cấu hình JavaCompile trong Gradle

Gradle Java Plugin tạo các task compile theo source set. Với Kotlin DSL, cấu hình Java release và encoding:

~~~kotlin
plugins {
    java
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}
~~~

Toolchain chọn JDK compiler phù hợp; `options.release` giới hạn API và bytecode mục tiêu. Nếu cấu hình toolchain 17, runner phải có JDK 17 hoặc Gradle phải được cấu hình một resolver đáng tin cậy để tải toolchain.

Các task chính:

~~~bash
./gradlew compileJava
./gradlew compileTestJava
./gradlew test
./gradlew check
./gradlew jar
./gradlew clean build
~~~

Với Groovy DSL, cấu hình tương đương:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Không trộn nhiều nguồn cấu hình Java version mà không hiểu ưu tiên của chúng. Hãy kiểm tra toolchain và compiler task khi build trên máy có nhiều JDK.

## 9. Maven Toolchains khi compiler JDK khác JDK chạy Maven

Có trường hợp Maven cần chạy bằng một JDK mới để đáp ứng yêu cầu của plugin, nhưng dự án phải compile bằng một JDK khác. Maven Toolchains cho phép plugin chọn toolchain được khai báo trong `toolchains.xml`.

Một cấu hình toolchain có thể khai báo JDK 17:

~~~xml
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

Trên CI, đường dẫn thực tế phụ thuộc runner. Không commit đường dẫn tuyệt đối của máy developer vào repository. Dùng biến môi trường, JDK installation path hoặc cấu hình toolchain được tạo bởi setup action.

`maven.compiler.release` vẫn cần được cấu hình để xác định API và bytecode target. Toolchain chọn compiler JDK; release xác định hợp đồng tương thích Java của output.

## 10. Ví dụ project Maven hoàn chỉnh

Cấu trúc:

~~~text
ci-compile-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/CiCompileDemo.java
    └── test/java/com/example/CiCompileDemoTest.java
~~~

Tệp `src/main/java/com/example/CiCompileDemo.java`:

~~~java
package com.example;

public final class CiCompileDemo {
    private CiCompileDemo() {}

    public static String status() {
        return "CI_COMPILE_OK version=17";
    }

    public static void main(String[] args) {
        System.out.println(status());
    }
}
~~~

Tệp `src/test/java/com/example/CiCompileDemoTest.java`:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CiCompileDemoTest {
    @Test
    void returnsExpectedBuildStatus() {
        assertEquals("CI_COMPILE_OK version=17", CiCompileDemo.status());
    }
}
~~~

POM đầy đủ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>ci-compile-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.12.2</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

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
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.CiCompileDemo</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Biên dịch, test và đóng gói:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean verify
java -jar target/ci-compile-demo-1.0.0.jar
~~~

Stdout của JAR:

~~~text
CI_COMPILE_OK version=17
~~~

JUnit report nằm trong `target/surefire-reports/`. JAR được tạo trong `target/`. Trong CI, có thể upload cả JAR và report để reviewer tải xuống hoặc kiểm tra khi job thất bại.

## 11. GitHub Actions workflow cho Maven

Tạo `.github/workflows/java-ci.yml`:

~~~yaml
name: Java CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Check Java and Maven
        run: |
          java -version
          ./mvnw --version

      - name: Compile, test and verify
        run: ./mvnw --batch-mode --no-transfer-progress --errors clean verify

      - name: Upload JAR and test reports
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: java-build-${{ github.run_id }}
          path: |
            target/*.jar
            target/surefire-reports/**
          if-no-files-found: warn
          retention-days: 7
~~~

Các điểm quan trọng:

- `checkout` lấy đúng source commit của event.
- `setup-java` cài JDK và thiết lập `JAVA_HOME`.
- `cache: maven` cache dependency đã tải và wrapper distribution.
- `./mvnw` bảo đảm CI dùng Maven version được dự án pin.
- `clean verify` chạy compile, test và lifecycle verification.
- `if: always()` giúp upload test report/log ngay cả khi bước build thất bại; nếu chưa có JAR thì upload action có thể cảnh báo không tìm thấy file.
- `permissions: contents: read` giới hạn quyền token ở mức cần cho checkout.

`actions/setup-java` có thể cache Maven dependency theo các file như `pom.xml` và wrapper properties. Với monorepo, dùng `cache-dependency-path` để chỉ rõ các POM/wrapper cần tham gia cache key.

## 12. GitHub Actions workflow cho Gradle

Nếu dự án dùng Gradle Wrapper, có thể dùng `gradle/actions/setup-gradle` để cấu hình Gradle User Home cache và kiểm tra wrapper:

~~~yaml
name: Gradle CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Check toolchain
        run: |
          java -version
          ./gradlew --version

      - name: Build and test
        run: ./gradlew --no-daemon clean build

      - name: Upload JAR and test reports
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: gradle-build-${{ github.run_id }}
          path: |
            build/libs/*.jar
            build/reports/tests/test/**
          if-no-files-found: warn
          retention-days: 7
~~~

Cấu hình Gradle Kotlin DSL tối thiểu cho Java 17:

~~~kotlin
plugins {
    application
}

group = "com.example"
version = "1.0.0"

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

application {
    mainClass = "com.example.CiCompileDemo"
}
~~~

`gradle/actions/setup-gradle@v6` quản lý cache Gradle User Home và kiểm tra Gradle Wrapper. Một lựa chọn đơn giản khác là `actions/setup-java` với `cache: gradle`. Chọn một chiến lược cache chính, tránh cấu hình hai cơ chế chồng chéo nếu không có lý do cụ thể.

## 13. Matrix build với nhiều JDK

Matrix giúp chạy cùng một build trên nhiều phiên bản JDK hoặc hệ điều hành. Ví dụ dự án target Java 17 nhưng hỗ trợ chạy trên Java 17, 21 và 25:

~~~yaml
jobs:
  test-jdk-matrix:
    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']
    runs-on: ubuntu-latest
    name: Test on Java ${{ matrix.java }}
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

Giữ `maven.compiler.release` là 17 trong POM. Mỗi matrix job dùng JDK khác để kiểm tra runtime và compiler behavior. Nếu chỉ muốn kiểm tra compile bằng một compiler cố định nhưng test trên nhiều runtime, cấu hình Maven Toolchains hoặc Gradle toolchain cho compile, rồi chọn Java launcher riêng cho test.

Matrix làm tăng thời gian và chi phí runner. Chọn các phiên bản đại diện cho phạm vi hỗ trợ thực tế, không thêm mọi JDK chỉ vì có thể.

Có thể mở rộng matrix sang `ubuntu-latest`, `windows-latest`, `macos-latest` khi dự án có mã phụ thuộc nền tảng, script đa hệ điều hành hoặc native library.

## 14. Caching dependency và build output

Cache giúp giảm thời gian tải dependency giữa các lần CI chạy. Nó không được là điều kiện để build đúng.

Nên cache:

- Maven local repository (`~/.m2/repository`).
- Gradle dependency cache và wrapper distribution.
- Các dependency tool đã được xác định qua lock/configuration files.

Không nên tự cache `target/` hoặc `build/` như cache dependency mặc định. Build output có thể chứa class cũ, generated source, file phụ thuộc môi trường hoặc trạng thái incremental không hợp lệ. Dùng build cache chuyên dụng của Gradle khi đã hiểu key, task input/output và trust boundary.

Cache key nên thay đổi khi dependency hoặc build configuration thay đổi. Maven setup action mặc định hash POM và Maven wrapper metadata; Gradle cache dựa vào build scripts, wrapper properties và version catalog liên quan.

Nếu cache bị miss, CI vẫn phải có khả năng tải dependency và build. Thỉnh thoảng chạy clean build để phát hiện pipeline đang vô tình dựa vào output cũ.

## 15. Pin dependency, plugin và build tool

Một build có thể thay đổi dù source code không đổi nếu dependency hoặc plugin version bị thay thế.

Thực hành tốt:

- Pin version cho Maven plugin và dependency trực tiếp.
- Dùng BOM hoặc dependency management để đồng bộ version trong nhiều module.
- Tránh version range và dependency SNAPSHOT trong release build.
- Với Gradle, dùng version catalog và dependency locking khi dự án cần khóa graph.
- Bật dependency verification/checksum verification theo khả năng build tool.
- Pin Maven/Gradle Wrapper version.
- Quản lý JDK distribution/version rõ ràng.
- Review thay đổi lockfile, POM và wrapper properties trong pull request.

Không dùng version plugin mặc định không được kiểm soát. Maven plugin có thể thay đổi hành vi khi Maven core hoặc parent POM được nâng cấp; khai báo version rõ ràng giúp reviewer nhìn thấy thay đổi đó.

## 16. Reproducible build và artifact có thể kiểm chứng

**Reproducible build** nghĩa là cùng source, dependency, build instructions và môi trường đã xác định có thể tạo lại artifact giống nhau ở mức bit-for-bit.

Các yếu tố làm artifact khác nhau:

- JDK vendor hoặc major version khác.
- Plugin hoặc dependency version thay đổi.
- Timestamp trong JAR manifest/resource.
- Locale, timezone, line endings hoặc environment variable.
- Generated source chứa thời gian, đường dẫn hoặc thông tin máy build.
- Dependency lấy từ repository thay đổi nội dung hoặc không được xác minh.

Maven hỗ trợ `project.build.outputTimestamp` và các plugin có hỗ trợ reproducible archives. Gradle cũng có các thiết lập archive timestamp/order để tạo output ổn định.

Ví dụ trong POM:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Để so sánh hai lần build, build lại từ clean workspace và so SHA-256 của artifact. Nếu cần chứng minh tính tái lập, build độc lập trên môi trường khác rồi so sánh hash; chỉ chạy hai lần trên cùng runner chưa chứng minh mọi nguồn biến thiên đã được loại bỏ.

## 17. Compile warnings và static analysis trong CI

Compiler warning thường báo API deprecated, unchecked conversion, raw type, serialization issue hoặc code có khả năng gây lỗi.

Có thể bật lint:

~~~bash
javac --release 17 -Xlint:all -encoding UTF-8 -d out src/main/java/com/example/*.java
~~~

Với Maven, truyền compiler arguments qua `maven-compiler-plugin`. Với Gradle, cấu hình `options.compilerArgs`.

Chỉ bật `-Werror` sau khi codebase đã xử lý warning ổn định. Khi thêm một JDK mới, compiler có thể xuất hiện warning mới; nếu CI biến mọi warning thành lỗi ngay lập tức, một nâng cấp JDK có thể làm build thất bại hàng loạt.

Static analysis như Checkstyle, SpotBugs, PMD, Error Prone hoặc Sonar có thể chạy như verification task riêng. Gắn kết quả vào `verify` hoặc `check` để pull request có một trạng thái rõ ràng.

## 18. Annotation processor và generated sources

Một số thư viện tạo source hoặc bytecode trong lúc compile, ví dụ annotation processor, code generator, MapStruct, AutoValue hoặc Lombok.

CI cần bảo đảm:

- Processor dependency có version được pin.
- Processor chạy trên JDK được hỗ trợ.
- Processor path được khai báo rõ nếu build tool yêu cầu.
- Generated source được đưa vào compile task đúng cách.
- Không phụ thuộc file generated còn sót lại từ lần build trước.
- Processor không đọc secret hoặc ghi nội dung ngoài workspace ngoài dự kiến.

Nếu local build pass nhưng CI báo không tìm thấy generated class, xem log của annotation processing, cấu hình processor path và task order. Không sửa lỗi bằng cách commit generated output nếu dự án không quản lý generated source theo cách đó.

## 19. Multi-module project và monorepo

Với Maven multi-module, chạy từ root POM:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean verify
~~~

Muốn build một module cùng các dependency module cần thiết:

~~~bash
./mvnw -pl service-api -am verify
~~~

`-pl` chọn project; `-am` thêm các module cần thiết để build module đã chọn.

Với Gradle, có thể chạy task theo project path:

~~~bash
./gradlew :service-api:build
~~~

Trong monorepo, cache key cần bao gồm các POM/build files/wrapper properties ảnh hưởng đến dependency của module. Artifact name nên có module và matrix dimension để không ghi đè output của job khác.

Đặt working directory rõ ràng nếu workflow chạy trong thư mục con. Không assume root repository chính là thư mục chứa `pom.xml` hoặc `settings.gradle.kts`.

## 20. Lưu artifact, test report và log

Sau khi build thành công, artifact có thể được lưu để QA, staging hoặc release pipeline dùng lại. Với Maven thường là `target/*.jar`; Gradle thường là `build/libs/*.jar`.

Nên lưu cùng artifact:

- Surefire/Failsafe XML và HTML reports.
- Gradle test reports.
- Compiler/static-analysis report.
- Build log khi thất bại.
- Commit SHA, JDK version, Maven/Gradle version và build metadata.

Không upload `~/.m2`, toàn bộ `~/.gradle`, credentials, `.env`, signing key hoặc thư mục chứa secret. Artifact cần có retention period phù hợp; artifact CI không nhất thiết là release artifact đã được phê duyệt.

Nếu release pipeline dùng lại artifact từ CI, xác minh artifact ID/hash và nguồn commit. Không build lại bằng cấu hình khác ở bước deploy rồi giả định output giống artifact đã được test.

## 21. Bảo mật workflow compile

Build script, Maven plugin, Gradle plugin và annotation processor đều có thể thực thi code trên runner. Hãy xem build từ pull request như code chưa được tin cậy.

Thực hành cơ bản:

- Dùng `permissions: contents: read` cho job chỉ checkout và build.
- Không truyền deploy token, signing key hoặc cloud credential vào pull request từ fork.
- Không dùng `pull_request_target` để checkout và thực thi source không tin cậy với quyền của repository.
- Không in secret vào log hoặc đưa secret vào artifact.
- Chỉ cấp quyền publish ở job release riêng, sau khi CI gate thành công.
- Giữ runner sạch, đặc biệt với self-hosted runner; ưu tiên ephemeral runner cho workload không tin cậy.
- Pin action theo commit SHA nếu chính sách supply-chain yêu cầu bất biến; major tag tiện nâng cấp nhưng có thể trỏ tới bản mới.
- Dùng checksum/signature verification cho JDK, wrapper và dependency khi nền tảng hỗ trợ.

Compile job chỉ nên có quyền tối thiểu cần thiết. Không chạy deployment hoặc publish từ cùng job pull request chỉ vì compile pass.

## 22. Chẩn đoán compile failure trong CI

| Lỗi | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `invalid source release` | Compiler JDK không hỗ trợ release đã cấu hình. | `java -version`, toolchain và compiler log. |
| `Unsupported class file major version` | Build plugin hoặc runtime đọc bytecode mới hơn khả năng hỗ trợ. | Kiểm tra JDK chạy build tool và version plugin. |
| `package ... does not exist` | Dependency thiếu, scope sai hoặc cache/repository lỗi. | `mvn dependency:tree`, Gradle dependency insight. |
| `cannot find symbol` | Source/generated source/module/classpath không đầy đủ. | Kiểm tra source set, processor và module path. |
| Test compile pass nhưng test fail | Runtime behavior, environment hoặc test data khác. | Xem Surefire/Gradle test report và environment. |
| Wrapper không chạy trên Linux | Script không có executable bit hoặc wrapper file thiếu. | Kiểm tra quyền `mvnw`/`gradlew` và wrapper files. |
| `toolchain not found` | Runner không có JDK phù hợp hoặc resolver chưa cấu hình. | Kiểm tra toolchain installation và auto-download repository. |
| Build pass local nhưng fail CI | Khác JDK, OS, encoding, case sensitivity, environment hoặc dependency. | In tool versions và chạy clean build trong container tương đương. |
| Cache hit nhưng build sai | Cache key không bao phủ input hoặc build dựa vào output cũ. | Clean workspace và tắt cache để so sánh. |

Maven diagnostics:

~~~bash
./mvnw --version
./mvnw --errors --debug -DskipTests compile
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

Gradle diagnostics:

~~~bash
./gradlew --version
./gradlew compileJava --info --stacktrace
./gradlew dependencies
./gradlew dependencyInsight --dependency junit --configuration testRuntimeClasspath
~~~

Chỉ bật `--debug` khi cần vì log có thể rất dài và một số plugin có thể in thông tin nhạy cảm. Trước khi chia sẻ log ra ngoài, kiểm tra và loại bỏ token, URL nội bộ có credential hoặc dữ liệu bí mật.

## 23. Xác minh bytecode và JAR đầu ra

Sau compile, kiểm tra class file version:

~~~bash
javap -verbose -classpath target/classes com.example.CiCompileDemo
~~~

Java 17 có class-file major version 61. Một số mốc phổ biến:

| Java | Class-file major version |
|---|---:|
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Kiểm tra nội dung JAR:

~~~bash
jar tf target/ci-compile-demo-1.0.0.jar
~~~

Chạy JAR:

~~~bash
java -jar target/ci-compile-demo-1.0.0.jar
~~~

Những bước này xác nhận bytecode và artifact có đúng cấu trúc dự kiến. Chúng không thay thế test hoặc kiểm tra runtime trên các JDK mà dự án hỗ trợ.

## 24. Pipeline compile trong GitLab CI và Jenkins

Build tool command không phụ thuộc GitHub Actions. GitLab CI có thể chạy Maven Wrapper trong image đã pin JDK/Maven:

~~~yaml
stages:
  - verify

compile_and_test:
  stage: verify
  image: maven:3.9.12-eclipse-temurin-17
  script:
    - java -version
    - ./mvnw --batch-mode --no-transfer-progress clean verify
  artifacts:
    when: always
    paths:
      - target/*.jar
      - target/surefire-reports/
    expire_in: 7 days
~~~

Nếu dự án dùng wrapper, image vẫn cần JDK phù hợp; Maven cài sẵn trong image không bắt buộc phải là Maven version được dùng vì wrapper sẽ chọn distribution đã pin.

Trong Jenkins Pipeline, cùng lệnh có thể chạy ở stage:

~~~groovy
pipeline {
    agent any
    stages {
        stage('Compile and verify') {
            steps {
                sh './mvnw --batch-mode --no-transfer-progress clean verify'
            }
        }
    }
    post {
        always {
            junit 'target/surefire-reports/*.xml'
            archiveArtifacts artifacts: 'target/*.jar', allowEmptyArchive: true
        }
    }
}
~~~

Trên Windows agent, dùng `bat '.\\mvnw.cmd --batch-mode --no-transfer-progress clean verify'` thay cho `sh`. Cần cấu hình tool installation hoặc container image để JDK và build tool version nhất quán.

## 25. Quy trình triển khai CI compile cho dự án mới

1. Chọn Java version mà dự án hỗ trợ và xác định JDK chạy build.
2. Chọn Maven hoặc Gradle; tạo và commit wrapper.
3. Khai báo compiler release, encoding và plugin versions.
4. Thêm unit test tối thiểu để xác nhận behavior quan trọng.
5. Chạy wrapper trên máy local bằng clean build.
6. Tạo CI workflow cho push và pull request.
7. Dùng JDK distribution/version đã pin và cache dependency theo build files.
8. Chạy `verify` hoặc `build`, không bỏ qua test trong merge gate.
9. Lưu JAR, test reports và log với retention hợp lý.
10. Thử build từ clean runner và kiểm tra artifact/class-file version.
11. Thêm JDK/OS matrix khi cần xác nhận phạm vi hỗ trợ.
12. Tách quyền publish/deploy khỏi job build pull request.

Một compile job đáng tin cậy phải trả lời được ba câu hỏi: commit nào được build, compiler/JDK nào đã tạo bytecode, và artifact nào tương ứng với kết quả test. Khi các thông tin đó được ghi nhận cùng wrapper, dependency và workflow đã pin, nhóm có thể tái hiện lỗi compile và truy vết thay đổi mà không phụ thuộc vào máy của một developer.

## Tài liệu tham khảo

- GitHub Docs — [Building and testing Java with Maven](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-maven).
- GitHub Docs — [Building and testing Java with Gradle](https://docs.github.com/en/actions/tutorials/build-and-test-code/java-with-gradle).
- GitHub — [actions/setup-java](https://github.com/actions/setup-java).
- GitHub — [actions/checkout](https://github.com/actions/checkout).
- GitHub — [actions/upload-artifact](https://github.com/actions/upload-artifact).
- Gradle — [Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html).
- Gradle — [Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).
- Apache Maven — [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/).
- Apache Maven — [Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html).
- Apache Maven — [Configuring for Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html).
- Apache Maven — [Maven in Five Minutes: Build Lifecycle](https://maven.apache.org/guides/getting-started/maven-in-five-minutes).
