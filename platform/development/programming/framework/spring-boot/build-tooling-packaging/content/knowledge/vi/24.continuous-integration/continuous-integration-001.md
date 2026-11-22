# Thiết kế chuỗi checkout, thiết lập JDK, kiểm tra, đóng gói và lưu artifact cho Spring Boot CI

## 1. Mục tiêu: từ commit đến artifact đã được kiểm chứng

Trong nhóm chủ đề cha **Tự động hóa CI**, bài học này thiết kế một pipeline tự động cho ứng dụng Spring Boot theo chuỗi **checkout source → thiết lập JDK → kiểm tra → đóng gói → xác minh → lưu artifact**. Mục tiêu là mỗi file được lưu có thể truy ngược về commit, môi trường build, kết quả test và checksum cụ thể.

Một lệnh build chạy thành công trên máy cá nhân chưa đủ để tạo ra một quy trình phát hành đáng tin cậy. CI phải trả lời được:

- Workflow đã checkout đúng commit của push hoặc pull request chưa?
- Runner sử dụng JDK và Maven/Gradle version nào?
- Wrapper có được commit và dùng đúng phiên bản đã pin không?
- Unit test và integration test nào thực sự chạy?
- File nào là executable Spring Boot JAR, file nào chỉ là plain JAR?
- Artifact có tồn tại, có cấu trúc đúng và chạy được trong smoke test không?
- SHA-256 của file là gì?
- Artifact được upload ở đâu, tên gì, lưu bao lâu và job sau tải đúng file nào?
- Pull request từ fork có được giữ ở quyền read-only và không tiếp cận secrets release không?

Bài cung cấp hai workflow GitHub Actions thay thế nhau: **Maven** và **Gradle**. Các ví dụ sử dụng **Java 17, Spring Boot 3.3.5, Maven Wrapper 3.9.x hoặc Gradle Wrapper 8.5**. Đây là bộ version cố định cho bài thực hành; dự án thật phải chọn version phù hợp với repository và cập nhật theo lịch bảo trì.

**GitHub Actions versions được dùng trong ví dụ:** `actions/checkout@v7`, `actions/setup-java@v6`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`. Các tag major giúp nhận bản vá trong cùng major; pipeline bảo mật cao có thể pin full commit SHA đã kiểm chứng.

## 2. Pipeline tổng thể

~~~text
Push / Pull Request / Manual trigger
              |
              v
       Checkout đúng commit
              |
              v
       Setup JDK + dependency cache
              |
              v
    Verify Java + Maven/Gradle Wrapper
              |
              v
       Compile + tests + verification
              |
              v
   Package executable Spring Boot JAR
              |
              v
   Validate archive + runtime smoke test
              |
              v
      Tính SHA-256 + staging output
              |
              v
       Upload workflow artifact
              |
              v
    Download + verify ở job tiếp theo
              |
              v
          Approval / deploy
~~~

Các bước có thứ tự vì bước sau phụ thuộc vào kết quả bước trước. Nếu test fail, job không nên tiếp tục upload một executable artifact như thể build đã được chấp nhận. Báo cáo test vẫn có thể được upload bằng một step riêng chạy với `if: always()` để hỗ trợ điều tra.

## 3. Phân biệt bốn loại dữ liệu trong CI

| Loại dữ liệu | Nội dung | Mục đích | Vòng đời |
| --- | --- | --- | --- |
| **Dependency cache** | Maven local repository hoặc Gradle dependency cache/wrapper distributions | Giảm thời gian tải dependencies/build | Có thể được tái sử dụng giữa các workflow run |
| **Build output** | File trong target/ hoặc build/ | Kết quả cục bộ của build job | Thường bị xóa cùng runner |
| **Workflow artifact** | JAR, checksum, reports được upload từ workflow run | Tải về, chia sẻ giữa jobs, review/test/deploy | Có retention theo repository policy |
| **Release package** | JAR/WAR publish lên Maven repository, GitHub Packages hoặc registry | Consumer tải theo version/GAV hoặc image tag/digest | Theo chính sách lưu trữ của registry |

**Upload workflow artifact không phải Maven deploy/Gradle publish.** Upload chỉ lưu output gắn với workflow run. Nếu muốn module khác khai báo `com.example:catalog-core:1.0.0`, cần publication với POM/Gradle Module Metadata, repository và quyền truy cập thích hợp.

Không upload nguyên thư mục `~/.m2`, `~/.gradle` hoặc toàn bộ workspace làm artifact sản phẩm. Cache là đầu vào tăng tốc; JAR là đầu ra cần phân phối.

## 4. Chuẩn bị repository và build wrapper

Cấu trúc project đơn module:

~~~text
catalog-app/
├── .github/
│   └── workflows/
│       ├── ci-maven.yml
│       └── ci-gradle.yml
├── .mvn/wrapper/
│   └── maven-wrapper.properties
├── gradle/wrapper/
│   └── gradle-wrapper.properties
├── mvnw
├── mvnw.cmd
├── gradlew
├── gradlew.bat
├── pom.xml
├── build.gradle
├── settings.gradle
└── src/
    ├── main/java/com/example/catalog/CatalogApplication.java
    └── test/java/com/example/catalog/CatalogApplicationTests.java
~~~

Đây là cây minh họa liệt kê cả Maven và Gradle. Một repository thực tế thường chỉ dùng một build system. Nếu project nằm trong subdirectory của monorepo, workflow phải đặt `working-directory` và artifact path theo đúng module.

### 4.1. Vì sao cần Wrapper?

**Maven Wrapper** gồm `mvnw`, `mvnw.cmd` và cấu hình trong `.mvn/wrapper`. **Gradle Wrapper** gồm `gradlew`, `gradlew.bat` và cấu hình trong `gradle/wrapper`.

Wrapper giúp local developer và CI sử dụng cùng phiên bản build tool đã khai báo. Không dựa vào Maven/Gradle cài sẵn trên GitHub runner vì image runner có thể được cập nhật độc lập với project.

Ví dụ Gradle Wrapper pin 8.5 trong `gradle/wrapper/gradle-wrapper.properties`:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip
~~~

Maven Wrapper giữ distribution URL của Maven 3.9.x trong `.mvn/wrapper/maven-wrapper.properties`. Chọn một bản Maven đã kiểm thử với plugin và project; không tải bản mới nhất tùy ý trong mỗi workflow run.

### 4.2. Quyền thực thi wrapper trên Linux

Nếu script wrapper bị mất executable bit khi commit, runner Linux có thể báo `Permission denied`. Kiểm tra Git mode và commit quyền thực thi:

~~~bash
git update-index --chmod=+x mvnw
git update-index --chmod=+x gradlew
git commit -m "Make build wrappers executable"
~~~

Chỉ chạy lệnh cho wrapper mà repository thực sự sử dụng. Trên Windows có thể gọi `mvnw.cmd` hoặc `gradlew.bat`.

### 4.3. Pin JDK target trong build

Maven với Spring Boot parent:

~~~xml
<properties>
    <java.version>17</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

JDK cài trên runner và Java toolchain của project là hai lớp cấu hình liên quan nhưng khác nhau. `setup-java` cài JDK và thiết lập `JAVA_HOME`; Maven compiler hoặc Gradle toolchain quyết định compiler/target mà project sử dụng. Kiểm tra mọi module trong monorepo, tránh một module vô tình compile Java 21 trong khi ứng dụng phải chạy trên Java 17.

## 5. Ví dụ Java 17: application và test

### 5.1. Spring Boot application

File **src/main/java/com/example/catalog/CatalogApplication.java**:

~~~java
package com.example.catalog;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner ciProof() {
        return args -> System.out.println("CI_PACKAGE_OK");
    }
}
~~~

Đây là class Java 17 hoàn chỉnh. Ví dụ dùng Spring Boot starter cơ bản, không mở HTTP server. Khi context khởi động thành công, dòng stdout do ứng dụng in là:

~~~text
CI_PACKAGE_OK
~~~

Spring Boot vẫn có thể in banner/log. Dòng trên là output nghiệp vụ xác định, không phải toàn bộ terminal output.

### 5.2. Test class theo JUnit 5

File **src/test/java/com/example/catalog/CatalogApplicationTests.java**:

~~~java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public class CatalogApplicationTests {

    @Test
    void contextLoads() {
    }
}
~~~

Đây là test class đầy đủ cho JUnit Jupiter và Spring Boot Test. Modifier `public` được khai báo tường minh theo quy ước QA của module. Test xác nhận application context khởi tạo được; dự án thực tế cần thêm unit/integration tests cho business logic, persistence, API, security và service dependencies.

## 6. Maven: cấu hình executable Boot JAR

File **pom.xml** cho project đơn module:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-app</artifactId>
    <version>1.0.0</version>
    <name>catalog-app</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

POM này dùng Spring Boot starter parent:

- Parent quản lý version dependency và cấu hình plugin thông dụng.
- `java.version` đặt Java target theo cấu hình parent.
- `spring-boot-starter-test` chỉ dùng trong test scope.
- Spring Boot Maven Plugin tạo executable archive qua goal `repackage`.
- Khi dùng starter parent, execution repackage được quản lý sẵn; khai báo plugin như trên là đủ cho trường hợp chuẩn.

### 6.1. Build Maven bằng lifecycle verification

~~~bash
./mvnw -B -ntp clean verify
~~~

- `-B`: batch mode, phù hợp CI.
- `-ntp`: tắt transfer progress để log dễ đọc.
- `clean`: xóa output build cũ.
- `verify`: chạy các phase trước đó, gồm compile, test, package và verify.
- Goal repackage của Spring Boot được chạy trong package lifecycle theo cấu hình parent.

Artifact mặc định:

~~~text
target/catalog-app-1.0.0.jar
~~~

Nếu không dùng Spring Boot parent, cần cấu hình execution `repackage` rõ ràng. Nếu đặt classifier, finalName hoặc output directory khác, phải điều chỉnh đường dẫn workflow theo artifact thật.

### 6.2. Kiểm tra thủ công Maven

~~~bash
./mvnw -B -ntp clean verify
jar tf target/catalog-app-1.0.0.jar
java -jar target/catalog-app-1.0.0.jar --spring.main.banner-mode=off
~~~

Ứng dụng command-line ở mục 5 kết thúc sau khi `CommandLineRunner` hoàn tất và in `CI_PACKAGE_OK`. Một service web thực tế sẽ tiếp tục chạy; khi đó cần kiểm tra health endpoint hoặc readiness probe thay vì chờ process tự kết thúc.

Một executable Boot JAR thông thường có:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/catalog/CatalogApplication.class
BOOT-INF/lib/...
~~~

### 6.3. Maven workflow cho multi-module

Nếu app nằm trong reactor:

~~~text
repository/
├── pom.xml
├── core/pom.xml
└── app/pom.xml
~~~

Build app cùng những module phụ thuộc:

~~~bash
./mvnw -B -ntp -pl app -am clean verify
~~~

`-pl app` chọn module app; `-am` yêu cầu Maven build các module reactor cần thiết, ví dụ core. Artifact có thể nằm tại:

~~~text
app/target/app-1.0.0.jar
~~~

Workflow phải dùng path này thay cho `target/catalog-app-1.0.0.jar`. Nếu project có nhiều POM, cache key cần phản ánh POM của các module liên quan.

## 7. GitHub Actions workflow hoàn chỉnh cho Maven

Tạo **.github/workflows/ci-maven.yml**:

~~~yaml
name: Spring Boot CI - Maven

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    name: Test and package with Maven
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17 and Maven cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "17"
          cache: maven
          cache-dependency-path: |
            **/pom.xml
            **/.mvn/wrapper/maven-wrapper.properties
            **/.mvn/extensions.xml

      - name: Verify Java and Maven
        run: |
          java -version
          ./mvnw --version

      - name: Run tests and package executable JAR
        run: ./mvnw -B -ntp clean verify

      - name: Verify executable Boot JAR
        run: |
          test -s target/catalog-app-1.0.0.jar
          jar tf target/catalog-app-1.0.0.jar > target/jar-entries.txt
          grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' target/jar-entries.txt
          grep -q '^BOOT-INF/lib/' target/jar-entries.txt

      - name: Smoke test executable JAR
        run: |
          java -jar target/catalog-app-1.0.0.jar --spring.main.banner-mode=off > target/smoke.log
          grep -q '^CI_PACKAGE_OK$' target/smoke.log

      - name: Prepare artifact and SHA-256
        run: |
          mkdir -p dist
          cp target/catalog-app-1.0.0.jar dist/
          (
            cd dist
            sha256sum catalog-app-1.0.0.jar > catalog-app-1.0.0.jar.sha256
          )

      - name: Upload executable JAR
        uses: actions/upload-artifact@v7
        with:
          name: spring-boot-maven-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: dist/
          if-no-files-found: error
          retention-days: 14

      - name: Upload Maven test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-test-reports-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/target/surefire-reports/
            **/target/failsafe-reports/
          if-no-files-found: ignore
          retention-days: 7
~~~

Workflow này thực hiện:

1. Chạy trên push main, pull request vào main, tag release dạng `v*` hoặc manual dispatch.
2. Checkout commit thuộc event hiện tại.
3. Cài Temurin JDK 17 và cache Maven dependencies.
4. In version Java/Maven để truy vết.
5. Chạy `clean verify`; test fail làm job dừng trước bước upload JAR.
6. Kiểm tra file tồn tại và có cấu trúc Boot executable.
7. Smoke test JAR command-line để chứng minh nó khởi động và chạy code.
8. Tạo thư mục staging `dist/`, copy đúng artifact và tạo checksum.
9. Upload JAR + checksum với tên duy nhất, fail nếu không tìm thấy file.
10. Upload Surefire/Failsafe reports ngay cả khi bước trước thất bại.

**Cache path:** `**/pom.xml` bao gồm POM module con trong monorepo. Nếu build dùng Maven extensions hoặc wrapper properties, chúng cũng tham gia cache key. Khi dependency graph thay đổi, cache key mới giúp tránh dùng cache không phản ánh cấu hình hiện tại.

**Smoke test:** ví dụ app không mở server nên process kết thúc. Với REST service, thay bằng bước khởi động ứng dụng nền, chờ health endpoint và dừng process đúng cách; không dùng pattern grep output làm kiểm tra duy nhất cho server lâu dài.

## 8. Gradle: cấu hình Java toolchain và Boot JAR

File **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

- Java plugin cung cấp compile, test và plain JAR tasks.
- Spring Boot Gradle Plugin cung cấp `bootJar` để tạo executable archive.
- Dependency Management Plugin tích hợp Spring Boot dependency management.
- Java toolchain yêu cầu compiler/test launcher phù hợp Java 17.
- `useJUnitPlatform()` kích hoạt JUnit Jupiter.

Gradle Wrapper phải được commit, ví dụ `gradle-wrapper.properties` trỏ tới Gradle 8.5. Không dựa vào Gradle global cài sẵn trên runner.

### 8.1. Build và kiểm tra Gradle

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

- `--no-daemon`: không giữ Gradle daemon sau build trên runner ngắn hạn.
- `clean`: xóa output cũ.
- `check`: chạy tests và các verification tasks đã gắn.
- `bootJar`: tạo executable Spring Boot JAR.

Artifact mặc định:

~~~text
build/libs/catalog-app-1.0.0.jar
~~~

Nếu build đồng thời tạo plain JAR, tên thường có hậu tố `-plain.jar`. Workflow phải upload đúng file do `bootJar` tạo.

### 8.2. Gradle multi-project

Với cấu trúc:

~~~text
repository/
├── settings.gradle
├── build.gradle
├── core/build.gradle
└── app/build.gradle
~~~

Chạy:

~~~bash
./gradlew --no-daemon clean :app:check :app:bootJar
~~~

Artifact:

~~~text
app/build/libs/app-1.0.0.jar
~~~

Cập nhật workflow từ `build/libs/catalog-app-1.0.0.jar` sang `app/build/libs/app-1.0.0.jar`. Chỉ module app cần Spring Boot plugin; core library thường dùng Java Library plugin và tạo plain JAR.

## 9. GitHub Actions workflow hoàn chỉnh cho Gradle

Tạo **.github/workflows/ci-gradle.yml**:

~~~yaml
name: Spring Boot CI - Gradle

on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    name: Test and package with Gradle
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Set up JDK 17 and Gradle cache
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "17"
          cache: gradle
          cache-dependency-path: |
            **/*.gradle*
            **/gradle.properties
            **/gradle/wrapper/gradle-wrapper.properties
            **/gradle/libs.versions.toml

      - name: Verify Java and Gradle
        run: |
          java -version
          ./gradlew --version

      - name: Run checks and package executable JAR
        run: ./gradlew --no-daemon clean check bootJar

      - name: Verify executable Boot JAR
        run: |
          test -s build/libs/catalog-app-1.0.0.jar
          jar tf build/libs/catalog-app-1.0.0.jar > build/jar-entries.txt
          grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' build/jar-entries.txt
          grep -q '^BOOT-INF/lib/' build/jar-entries.txt

      - name: Smoke test executable JAR
        run: |
          java -jar build/libs/catalog-app-1.0.0.jar --spring.main.banner-mode=off > build/smoke.log
          grep -q '^CI_PACKAGE_OK$' build/smoke.log

      - name: Prepare artifact and SHA-256
        run: |
          mkdir -p dist
          cp build/libs/catalog-app-1.0.0.jar dist/
          (
            cd dist
            sha256sum catalog-app-1.0.0.jar > catalog-app-1.0.0.jar.sha256
          )

      - name: Upload executable JAR
        uses: actions/upload-artifact@v7
        with:
          name: spring-boot-gradle-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: dist/
          if-no-files-found: error
          retention-days: 14

      - name: Upload Gradle test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: gradle-test-reports-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/build/reports/tests/
          if-no-files-found: ignore
          retention-days: 7
~~~

Hai workflow Maven và Gradle là **hai phương án thay thế**. Không cần đặt cả hai vào một repository nếu dự án chỉ sử dụng một build system.

## 10. Checkout: đảm bảo build đúng commit

### 10.1. Push, pull_request và manual trigger

- **push:** chạy khi commit được đẩy lên branch/tag được khai báo.
- **pull_request:** kiểm tra thay đổi trước khi merge.
- **workflow_dispatch:** cho phép chạy thủ công từ GitHub Actions UI/API.
- **tags:** có thể dùng để kích hoạt release workflow theo version tag.

Checkout action lấy commit gắn với event. Không tự clone branch HEAD mới nhất giữa workflow, vì commit đó có thể khác source revision đang được kiểm thử.

### 10.2. Shallow checkout và fetch-depth

Checkout mặc định lấy lịch sử nông phù hợp phần lớn compile/test/package. Nếu versioning plugin hoặc release script cần Git tags/lịch sử, cấu hình:

~~~yaml
- name: Checkout full history
  uses: actions/checkout@v7
  with:
    fetch-depth: 0
~~~

Chỉ dùng `fetch-depth: 0` khi thật sự cần. Tải toàn bộ history có thể làm checkout chậm hơn.

### 10.3. Submodules và Git LFS

Nếu source phụ thuộc submodules:

~~~yaml
- uses: actions/checkout@v7
  with:
    submodules: recursive
~~~

Nếu dùng Git LFS:

~~~yaml
- uses: actions/checkout@v7
  with:
    lfs: true
~~~

Chỉ bật các tùy chọn này khi repository thực sự sử dụng chúng và token có quyền tải dữ liệu tương ứng.

### 10.4. Monorepo và working-directory

Nếu POM/Gradle project nằm dưới `services/catalog`, các lệnh cần chạy tại thư mục đó:

~~~yaml
- name: Build catalog service
  working-directory: services/catalog
  run: ./mvnw -B -ntp clean verify
~~~

Artifact path cũng cần phản ánh working directory. Một lỗi phổ biến là build trong subdirectory nhưng upload path lại được viết tương đối theo repository root.

## 11. Thiết lập JDK: version, distribution và toolchain

### 11.1. actions/setup-java

Ví dụ:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: "17"
~~~

Action cài JDK distribution được chọn, thiết lập `JAVA_HOME`/PATH và có thể cache dependencies Maven/Gradle. Java 17 là feature version mà project ví dụ yêu cầu.

**Major version và patch version:**

- `java-version: "17"` chọn dòng Java 17; patch build có thể được cập nhật.
- Version cụ thể có thể giúp tái lập nghiêm ngặt hơn, nhưng nhóm phải có chính sách cập nhật bảo mật.
- Không dùng `latest` cho release cần kiểm soát target Java 17, vì alias latest có thể chuyển sang feature release mới.

### 11.2. JDK distribution

Các distribution có thể khác nhau về vendor, build, certificate và cách cung cấp package. Ví dụ dùng Temurin để có lựa chọn rõ ràng. Nếu tổ chức chuẩn hóa Microsoft Build of OpenJDK, Oracle JDK hoặc distribution khác, đổi `distribution` theo tên được action hỗ trợ và kiểm tra version thực tế.

### 11.3. Kiểm tra version

~~~bash
java -version
./mvnw --version
./gradlew --version
~~~

Chỉ chạy lệnh wrapper tương ứng build system. Với Gradle, có thể kiểm tra toolchains:

~~~bash
./gradlew -q javaToolchains
~~~

Nếu có nhiều JDK trên runner, output giúp xác nhận toolchain mà Gradle phát hiện. Maven có thể cần kiểm tra compiler plugin/toolchains khi project sử dụng JDK riêng.

### 11.4. Self-hosted runners

Các action major mới sử dụng runtime Node mới. Self-hosted runner cần phiên bản runner tương thích với runtime mà action yêu cầu. Khi action báo lỗi Node/runner, cập nhật runner theo tài liệu GitHub Actions và release notes của action; không hạ version action một cách tùy tiện để che vấn đề runtime.

## 12. Dependency cache: cấu hình đúng theo build system

### 12.1. Maven cache

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: "17"
    cache: maven
    cache-dependency-path: |
      **/pom.xml
      **/.mvn/wrapper/maven-wrapper.properties
      **/.mvn/extensions.xml
~~~

Maven dependencies thường được tải về local repository `~/.m2/repository`. Cache giúp giảm download ở lần build sau. `cache-dependency-path` cho biết file nào tham gia hash cache key.

Với multi-module, cần đưa POM con vào cache path. Nếu dùng Maven profiles hoặc extensions làm thay dependency graph, kiểm tra chúng có được phản ánh trong key.

### 12.2. Gradle cache

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: "17"
    cache: gradle
    cache-dependency-path: |
      **/*.gradle*
      **/gradle.properties
      **/gradle/wrapper/gradle-wrapper.properties
      **/gradle/libs.versions.toml
~~~

Gradle cache lưu downloaded dependencies, metadata và wrapper distribution. Với project có `buildSrc`, included build hoặc file quản lý version riêng, cần kiểm tra cache key có bao phủ những input ảnh hưởng dependency resolution không.

### 12.3. Cache không phải bảo đảm reproducibility

Cache chỉ giúp lấy lại dữ liệu nhanh. Nó không tự bảo đảm:

- Dependency SNAPSHOT/dynamic version không thay đổi.
- Repository không ghi đè cùng tọa độ artifact.
- JDK patch version luôn giống nhau.
- Build script không dùng timestamp/random value.
- Artifact bytes tái lập.

Release pipeline có thể dùng dependency locking/verification, checksum và immutable repositories để kiểm soát input.

### 12.4. Khi nào không nên cache?

Nếu đang điều tra cache corruption, muốn benchmark cold build hoặc kiểm tra độc lập một lần, có thể tắt cache theo cơ chế action/build tool. Không tắt cache vĩnh viễn chỉ vì một lần build fail; trước tiên xác định lỗi nằm ở dependency resolution, task output hay source.

## 13. Test và verification: đặt quality gate trước upload

### 13.1. Maven lifecycle

Lệnh:

~~~bash
./mvnw -B -ntp clean verify
~~~

chạy các phase trước verify, bao gồm compile, test, package và verify. Spring Boot repackage được gắn trong package lifecycle khi dùng starter parent. Nếu test hoặc verification plugin fail, Maven trả exit code khác 0 và các bước sau trong job mặc định bị bỏ qua.

### 13.2. Gradle task graph

Lệnh:

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

- `check` phụ thuộc các verification tasks, bao gồm test.
- `bootJar` tạo executable archive.
- Gradle xây task graph và thực hiện dependency tasks trước.
- Một task không chạy lặp lại nhiều lần trong cùng invocation chỉ vì nhiều task khác phụ thuộc nó.

### 13.3. Unit test và integration test

Maven thường dùng Surefire cho unit tests và Failsafe cho integration tests khi được cấu hình. Gradle dùng Test tasks và source sets tương ứng. Hãy xác định rõ test nào thuộc quality gate của pull request và test nào cần service ngoài.

Nếu integration test cần PostgreSQL, Redis, Kafka hoặc HTTP service, CI phải cung cấp service container/Testcontainers/endpoint test phù hợp. Không để test bị skip âm thầm chỉ vì runner không có service.

### 13.4. Upload test reports kể cả khi test fail

Dùng:

~~~yaml
- name: Upload test reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v7
  with:
    name: test-reports-${{ github.run_id }}-${{ github.run_attempt }}
    path: |
      **/target/surefire-reports/
      **/target/failsafe-reports/
    if-no-files-found: ignore
    retention-days: 7
~~~

Ví dụ này dành cho Maven. Với Gradle, đổi path thành `**/build/reports/tests/`. Vì step chạy với `always()`, report vẫn có thể được lưu sau khi test fail. `if-no-files-found: ignore` tránh làm job thêm lỗi nếu project chưa tạo report ở giai đoạn đó.

## 14. Package: xác định đúng executable Boot JAR

### 14.1. Maven

Với Spring Boot parent và không dùng classifier, executable JAR thường là:

~~~text
target/catalog-app-1.0.0.jar
~~~

Nếu cấu hình classifier `exec`, file có thể là:

~~~text
target/catalog-app-1.0.0-exec.jar
~~~

Nếu repackage thay artifact chính, bản JAR gốc có thể được giữ dưới tên `.jar.original`. Workflow phải upload executable file đúng theo cấu hình plugin.

### 14.2. Gradle

Task:

~~~bash
./gradlew bootJar
~~~

tạo executable archive thường ở:

~~~text
build/libs/catalog-app-1.0.0.jar
~~~

Plain JAR nếu tạo song song có thể là:

~~~text
build/libs/catalog-app-1.0.0-plain.jar
~~~

Không dùng wildcard `build/libs/*.jar` để chọn artifact khi folder có nhiều loại JAR. Chỉ định đúng file do `bootJar` tạo.

### 14.3. Kiểm tra cấu trúc archive

Maven:

~~~bash
test -s target/catalog-app-1.0.0.jar
jar tf target/catalog-app-1.0.0.jar > target/jar-entries.txt
grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' target/jar-entries.txt
grep -q '^BOOT-INF/lib/' target/jar-entries.txt
~~~

Gradle:

~~~bash
test -s build/libs/catalog-app-1.0.0.jar
jar tf build/libs/catalog-app-1.0.0.jar > build/jar-entries.txt
grep -q '^BOOT-INF/classes/com/example/catalog/CatalogApplication.class$' build/jar-entries.txt
grep -q '^BOOT-INF/lib/' build/jar-entries.txt
~~~

Các bước này xác nhận file tồn tại, có application class và nested libraries. Chúng chưa chứng minh mọi API/database/config production hoạt động; smoke test và integration tests vẫn cần thiết.

### 14.4. Smoke test cho ứng dụng command-line

~~~bash
java -jar target/catalog-app-1.0.0.jar --spring.main.banner-mode=off > target/smoke.log
grep -q '^CI_PACKAGE_OK$' target/smoke.log
~~~

Lệnh trên dành cho ví dụ CommandLineRunner kết thúc sau khi chạy. Với web service, khởi động process ở background, chờ health endpoint, xác minh response rồi dừng process; không dùng cách đợi app tự exit.

## 15. SHA-256: ghi nhận checksum của artifact

### 15.1. Tạo checksum

Trên Ubuntu runner:

~~~bash
mkdir -p dist
cp target/catalog-app-1.0.0.jar dist/
(
  cd dist
  sha256sum catalog-app-1.0.0.jar > catalog-app-1.0.0.jar.sha256
)
~~~

Thư mục staging:

~~~text
dist/
├── catalog-app-1.0.0.jar
└── catalog-app-1.0.0.jar.sha256
~~~

File checksum chứa digest và tên file tương ứng. Nó giúp phát hiện file bị thay đổi hoặc tải không đầy đủ sau upload/download.

### 15.2. Verify sau download

~~~bash
cd downloaded
sha256sum -c catalog-app-1.0.0.jar.sha256
~~~

Nếu khớp, stdout:

~~~text
catalog-app-1.0.0.jar: OK
~~~

Nếu file sai hoặc thiếu, sha256sum trả exit code khác 0. Không tự tạo lại checksum từ file mismatch rồi đánh dấu pass; phải điều tra nguồn thay đổi.

### 15.3. Windows PowerShell

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "catalog-app-1.0.0.jar"
~~~

PowerShell in algorithm, hash và path. Khi so sánh hai file, chỉ so giá trị hash sau khi đã xác định chúng là cùng artifact/version.

**Checksum không phải chữ ký số.** Nó xác minh tính nhất quán của bytes khi có checksum tin cậy; không chứng minh source an toàn hay người phát hành đáng tin. Release security có thể cần signature, provenance, SBOM và trusted build policy.

## 16. Upload workflow artifact

Ví dụ upload JAR và checksum:

~~~yaml
- name: Upload executable JAR
  uses: actions/upload-artifact@v7
  with:
    name: spring-boot-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
    path: dist/
    if-no-files-found: error
    retention-days: 14
~~~

Giải thích:

- **name:** có commit SHA, run ID và run attempt để truy vết, giảm khả năng trùng tên khi rerun.
- **path:** chỉ upload thư mục staging chứa artifact được phép phân phối.
- **if-no-files-found: error:** thiếu file là lỗi pipeline.
- **retention-days:** ví dụ 14 ngày cho artifact CI ngắn hạn; repository/organization có thể đặt giới hạn thấp hơn.

Các phiên bản upload-artifact hiện hành dùng artifact immutable. Không thiết kế nhiều job để append file vào cùng artifact name; gom các file cần upload trong một step hoặc đặt tên riêng cho từng job/matrix.

### 16.1. Upload artifact theo matrix

Nếu chạy nhiều OS/JDK, tên artifact phải bao gồm matrix values:

~~~yaml
name: spring-boot-${{ matrix.os }}-java-${{ matrix.java }}-${{ github.run_id }}
~~~

Nếu không, các job có thể upload trùng artifact name và gây conflict. Nếu chỉ một JDK được phép tạo release artifact, tách job release canonical khỏi các job compatibility matrix.

### 16.2. Retention không phải lưu trữ vĩnh viễn

Workflow artifact gắn với run và retention policy. Khi hết hạn hoặc bị xóa, đường dẫn tải không còn dùng được. Artifact phục vụ QA/UAT có thể cần retention dài hơn; package release lâu dài nên đưa vào Maven repository, GitHub Packages hoặc container registry theo chính sách tổ chức.

## 17. Download artifact trong job downstream

Ví dụ job thứ hai tải artifact của cùng workflow run:

~~~yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      # Checkout, setup JDK, test, package và upload ở job này.

  verify-artifact:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Download executable JAR
        uses: actions/download-artifact@v8
        with:
          name: spring-boot-maven-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: downloaded

      - name: Verify downloaded artifact
        run: |
          cd downloaded
          sha256sum -c catalog-app-1.0.0.jar.sha256
          test -s catalog-app-1.0.0.jar
~~~

`needs: build` đảm bảo job downstream chỉ chạy sau khi build thành công. Nó không cần checkout hoặc build lại nếu mục tiêu chỉ là kiểm tra file đã được build job upload.

Nếu download artifact từ workflow run/repository khác, action cần thêm run identifier và token có quyền phù hợp. Ví dụ trên chỉ dành cho artifact trong cùng workflow run.

### 17.1. Deploy đúng artifact đã test

Luồng release tốt:

~~~text
Build + test + package
          |
          v
      Upload artifact
          |
          v
   Approval / release gate
          |
          v
    Download same artifact
          |
          v
     Verify checksum
          |
          v
         Deploy
~~~

Không build lại từ branch mới nhất trong deploy job nếu yêu cầu là triển khai chính file đã qua test. Build lại có thể tạo một artifact khác dù commit branch đã thay đổi.

## 18. Checkout an toàn và quyền workflow

### 18.1. Least privilege

Ví dụ:

~~~yaml
permissions:
  contents: read
~~~

Chỉ cấp quyền tối thiểu. Build/test thường không cần packages: write, deployments: write hay id-token: write. Chỉ job release mới nhận quyền cần thiết và phải giới hạn theo trigger/environment.

### 18.2. Pull request từ fork

Pull request có thể chứa code do contributor bên ngoài cung cấp. Không truyền production secrets, signing key hoặc credentials deploy vào job chạy source không đáng tin.

- Giữ PR CI ở quyền read-only.
- Không dùng `pull_request_target` để checkout và thực thi code PR không an toàn.
- Tách release/deploy sang job sau merge/tag.
- Dùng protected environment và reviewer approval khi deploy production.
- Không in secret ra log hoặc upload file cấu hình chứa credentials.

### 18.3. Pin action versions

Ví dụ dùng major tags `@v7`, `@v6`, `@v7`, `@v8` giúp cập nhật patch trong cùng major. Với pipeline nhạy cảm, pin full commit SHA đã xác minh và cập nhật qua pull request có review. Không copy SHA cũ từ blog hoặc workflow không rõ nguồn.

### 18.4. Self-hosted runner

Action có thể yêu cầu runner support Node runtime mới. Kiểm tra runner version theo release notes của action. Ngoài ra, runner phải có network access tới JDK distribution, Maven/Gradle distribution và dependency repositories theo policy.

## 19. Tối ưu workflow có kiểm soát

### 19.1. Concurrency

~~~yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
~~~

Khi có commit mới liên tiếp trên cùng branch/PR, workflow cũ có thể bị hủy để tiết kiệm runner. Không áp dụng cancel-in-progress một cách máy móc cho release/deploy job không thể bị ngắt giữa chừng.

### 19.2. Timeout

~~~yaml
timeout-minutes: 20
~~~

Chọn timeout dựa trên thời gian build thực tế. Timeout giúp phát hiện test treo hoặc download vô hạn, nhưng đặt quá thấp có thể gây fail ngẫu nhiên cho integration tests.

### 19.3. JDK matrix

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ["17", "21"]
~~~

Sau đó:

~~~yaml
with:
  distribution: temurin
  java-version: ${{ matrix.java }}
~~~

Artifact name phải chứa matrix.java. Nếu sản phẩm chính thức chỉ build bằng Java 17, hãy tách artifact release canonical khỏi compatibility jobs chạy Java 21.

### 19.4. Tách PR CI, main CI và release

- **PR CI:** checkout, setup JDK, test, package, upload artifact để review.
- **Main CI:** kiểm tra commit sau merge, tạo artifact canonical.
- **Release:** chạy theo tag hoặc approval, tạo/publish package theo version.
- **Deploy:** nhận đúng artifact immutable đã được kiểm chứng và triển khai.

Không để một pull request tùy ý kích hoạt deploy production chỉ vì workflow có quyền write.

## 20. Xử lý lỗi thường gặp

**1. Không tìm thấy mvnw/gradlew.** Checkout sai thư mục hoặc wrapper chưa được commit. Kiểm tra repository root, working-directory và file wrapper.

**2. Permission denied khi chạy wrapper.** Git không lưu executable bit trên Linux. Commit quyền +x hoặc gọi wrapper qua shell thích hợp.

**3. Wrapper tải sai build tool version.** Kiểm tra distributionUrl trong wrapper properties; không dùng global Maven/Gradle để thay thế wrapper.

**4. Runner dùng nhầm Java.** Kiểm tra setup-java, JAVA_HOME, java -version và toolchain/compiler configuration.

**5. Local build được nhưng CI fail.** Local machine có cache, generated file hoặc environment variable mà runner không có. Khai báo đầy đủ inputs và dùng wrapper.

**6. Cache key không đổi khi dependency thay đổi.** Bổ sung POM/build scripts/version catalog/wrapper properties vào cache-dependency-path.

**7. Maven test không chạy.** Kiểm tra Surefire/Failsafe, naming conventions, profile và flags skipTests/maven.test.skip.

**8. Gradle check bỏ qua test mong muốn.** Kiểm tra task graph, source set, useJUnitPlatform và test filters.

**9. Build thành công nhưng không có Boot JAR.** Kiểm tra Spring Boot plugin, repackage/bootJar, packaging và classifier.

**10. Upload báo không tìm thấy file.** Xác minh filename, target/build path, module working directory và classifier.

**11. Upload nhầm plain JAR.** Gradle có thể tạo -plain.jar. Upload đúng file do bootJar tạo.

**12. Maven giữ JAR gốc thành .original.** Repackage có thể thay artifact chính. Kiểm tra plugin classifier/attach và chọn đúng executable output.

**13. Job downstream không tải được artifact.** Kiểm tra needs, tên artifact, workflow run, repository/token và retention.

**14. Matrix jobs upload trùng tên.** Thêm OS/JDK/architecture vào artifact name.

**15. Rerun workflow bị conflict.** Dùng run_attempt trong tên; artifact immutable nên không thiết kế append vào cùng tên.

**16. Checksum không khớp.** Xác minh file tải, staging path, tên file và thao tác thay đổi sau upload. Không cập nhật checksum theo file mới mà bỏ qua nguyên nhân.

**17. Test report mất khi test fail.** Dùng if: always() cho step upload report và if-no-files-found: ignore.

**18. Artifact quá lớn.** Chỉ upload file cần dùng; bỏ cache, source tree và temporary files khỏi staging directory.

**19. Pull request từ fork cần production secret.** Tách test khỏi publish/deploy; không cấp secret cho code PR không đáng tin.

**20. Workflow chạy chồng lấn.** Dùng concurrency có chủ đích cho CI branch/PR; giữ release job có kiểm soát.

**21. Job timeout.** Điều tra service container, test treo, download và runner resource trước khi tăng timeout.

**22. JAR không chạy được.** Kiểm tra Java runtime version, manifest, nested dependencies, profile, external configuration và smoke test.

**23. Chỉ chạy Maven package.** Plugin verify hoặc integration test có thể gắn ở phase sau package. Dùng clean verify khi policy yêu cầu lifecycle verification.

**24. Chỉ chạy Gradle bootJar.** Tests có thể chưa chạy. Dùng clean check bootJar.

**25. Action version không còn tương thích runner.** Đọc release notes và cập nhật self-hosted runner/runtime theo yêu cầu action.

**26. Dùng workflow artifact làm kho release lâu dài.** Artifact có retention. Dùng Maven repository/package registry/container registry cho release.

**27. Upload cả workspace.** Có thể làm lộ .env, source, cache hoặc file nội bộ. Dùng staging directory chứa đúng artifact.

**28. Checkout thiếu tags.** Nếu versioning cần Git history/tags, đặt fetch-depth: 0; nếu không, giữ shallow checkout.

**29. Java target lệch runtime production.** Đồng bộ setup-java và compiler/toolchain target, kiểm tra runtime version.

**30. Không truy vết được artifact thuộc commit nào.** Đặt commit SHA/run ID trong artifact name hoặc metadata; lưu checksum và toolchain logs.

## 21. Checklist nghiệm thu pipeline

- [ ] Workflow nằm trong `.github/workflows/`.
- [ ] Trigger push, pull_request và manual dispatch đúng branch/tag.
- [ ] Checkout đúng commit event.
- [ ] Submodules/LFS được cấu hình nếu project cần.
- [ ] Maven/Gradle Wrapper đã commit và chạy được trên runner.
- [ ] JDK distribution và version được khai báo rõ.
- [ ] Maven java.version hoặc Gradle toolchain khớp target.
- [ ] Dependency cache dùng đúng package manager.
- [ ] Cache dependency path chứa đủ file ảnh hưởng dependency graph.
- [ ] Build log có Java và Maven/Gradle versions.
- [ ] Unit tests chạy và fail làm job fail.
- [ ] Integration tests được kích hoạt theo policy.
- [ ] Build task tạo đúng executable Boot JAR.
- [ ] Archive check xác nhận BOOT-INF/classes và BOOT-INF/lib.
- [ ] Smoke test chạy đúng ứng dụng.
- [ ] Artifact path chỉ rõ file cần upload.
- [ ] SHA-256 được tạo cạnh artifact nếu cần.
- [ ] Upload action có tên duy nhất, if-no-files-found: error và retention.
- [ ] Test reports được lưu khi cần điều tra lỗi.
- [ ] Downstream job dùng download-artifact và xác minh checksum.
- [ ] Permissions ở mức tối thiểu.
- [ ] Pull request không nhận production secrets.
- [ ] Release/deploy tách khỏi PR CI và có approval phù hợp.
- [ ] Action versions được theo dõi/pin theo policy.
- [ ] Branch protection yêu cầu status check của job build.
- [ ] Đã thử cả đường success lẫn test/package failure.

## 22. Tài liệu chính thức

- GitHub Actions — checkout: https://github.com/actions/checkout
- GitHub Actions — setup-java: https://github.com/actions/setup-java
- GitHub Actions — upload-artifact: https://github.com/actions/upload-artifact
- GitHub Actions — download-artifact: https://github.com/actions/download-artifact
- GitHub Docs — Store and share data with workflow artifacts: https://docs.github.com/en/actions/tutorials/store-and-share-data
- GitHub Docs — Workflow syntax: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- Spring Boot 3.3 — Maven executable archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle executable archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Maven — Build lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Wrapper: https://maven.apache.org/wrapper/
- Gradle 8.5 — Wrapper: https://docs.gradle.org/8.5/userguide/gradle_wrapper.html
- Gradle — Java toolchains: https://docs.gradle.org/current/userguide/toolchains.html

**Kết luận:** Pipeline CI đáng tin cậy phải truy vết được **commit, JDK, build tool, kết quả kiểm thử và artifact cuối**. Checkout đúng source, cài JDK 17, dùng Wrapper, chạy lifecycle verification, tạo executable Boot JAR, kiểm tra archive và runtime, tính SHA-256 rồi upload đúng file với tên/retention rõ ràng. Job sau nên tải và xác minh chính artifact đã qua test thay vì tự build lại. Cuối cùng, tách workflow artifact ngắn hạn khỏi package release và giữ quyền workflow/secrets ở mức tối thiểu.