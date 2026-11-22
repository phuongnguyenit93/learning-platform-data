# Test trong CI cho dự án Java

**Test trong Continuous Integration (CI)** là bước tự động biên dịch và chạy bộ kiểm thử mỗi khi code được push hoặc mở pull request. CI cung cấp phản hồi sớm về lỗi logic, lỗi tích hợp, khác biệt giữa các JDK và regression trước khi thay đổi được merge hoặc phát hành.

Một pipeline test tốt phải trả lời được ba câu hỏi: bộ test có thực sự chạy không, kết quả có được lưu để điều tra không và lỗi có làm pipeline thất bại đúng cách không. Build xanh khi không phát hiện test nào, test bị skip ngoài ý muốn hoặc report bị mất sau khi job thất bại đều có thể tạo cảm giác an toàn giả.

Bài này dùng Java 17 làm mức tương thích ví dụ, JUnit 5 cho unit test, Gradle và Maven cho build, cùng GitHub Actions và GitLab CI để minh họa cách vận hành.

## 1. CI test nằm ở đâu trong pipeline?

Một pipeline Java thường có các bước:

1. Checkout đúng commit.
2. Cài JDK và build tool theo phiên bản đã chọn.
3. Khôi phục dependency cache.
4. Compile production source và test source.
5. Chạy unit/component tests.
6. Khởi động dịch vụ phụ trợ nếu cần và chạy integration tests.
7. Tạo test reports và coverage reports.
8. Upload reports để developer xem kể cả khi test thất bại.
9. Đánh dấu job thành công hoặc thất bại theo exit code của build.
10. Chỉ cho phép merge/release khi các quality gate bắt buộc đã qua.

CI thường được kích hoạt bởi push, pull_request hoặc merge_request. Có thể chạy thêm lịch hằng đêm để kiểm tra các luồng chậm, test tương thích hoặc test cần nhiều tài nguyên.

**Test job là quality gate.** Nếu một test bắt buộc thất bại, lệnh build phải trả exit code khác 0 để CI đánh dấu job thất bại. Bước upload report có thể chạy bằng điều kiện always(), nhưng không được dùng continue-on-error để biến test thất bại thành pipeline xanh.

## 2. Các loại test thường chạy trong CI

| Loại test | Mục tiêu | Đặc điểm | Thời điểm phù hợp |
| --- | --- | --- | --- |
| Unit test | Kiểm tra một method/class với dependency được cô lập | Nhanh, ít phụ thuộc môi trường | Mỗi push và pull request |
| Component test | Kiểm tra một nhóm class hoặc một module | Có thể dùng database/service giả lập | Mỗi pull request |
| Integration test | Kiểm tra tương tác giữa các thành phần thật | Có thể cần database, queue, HTTP service hoặc container | Pull request hoặc pipeline chính |
| Contract test | Kiểm tra hợp đồng giữa producer/consumer | Cần dữ liệu contract được quản lý | Pull request và lịch định kỳ |
| End-to-end test | Kiểm tra luồng từ đầu tới cuối qua nhiều service | Chậm, dễ phụ thuộc môi trường | Sau deploy lên môi trường test hoặc nightly |

Không nên đưa mọi test vào một nhóm duy nhất. Unit test cần nhanh và ổn định để developer nhận phản hồi sớm. Integration/E2E test thường cần khởi động dịch vụ, dữ liệu và cấu hình riêng; có thể chạy ở stage sau nhưng vẫn phải là quality gate nếu thay đổi phụ thuộc vào chúng.

Ví dụ, một service đặt hàng có thể có:

- Unit test cho phép tính tổng tiền và kiểm tra discount.
- Integration test cho thao tác lưu đơn hàng vào database.
- Contract test xác nhận JSON API không phá vỡ consumer.
- E2E test kiểm tra luồng đặt hàng, thanh toán giả lập và gửi xác nhận.

## 3. Viết test độc lập với môi trường CI

Test chạy trên máy developer nhưng thất bại trên CI thường do test phụ thuộc trạng thái bên ngoài.

Các nguyên tắc quan trọng:

- Mỗi test tự chuẩn bị dữ liệu và dọn dẹp sau khi chạy.
- Không phụ thuộc thứ tự test hoặc dữ liệu do test trước tạo ra.
- Không dùng port cố định nếu nhiều job có thể chạy đồng thời.
- Không dựa vào giờ hệ thống, timezone, locale hoặc random seed mặc định.
- Dùng clock/seed cố định khi kiểm tra logic phụ thuộc thời gian hoặc ngẫu nhiên.
- Không gọi production database, production API hoặc tài khoản người dùng thật.
- Đặt timeout hợp lý cho network, database và process.
- Ghi log đủ để tìm lỗi nhưng không in password, token hoặc dữ liệu cá nhân.
- Tách test cần network/service thật khỏi unit test thuần.

Với integration test cần database hoặc message broker, có thể dùng service container của CI hoặc Testcontainers để tạo dependency tạm thời cho mỗi lần chạy. Test cần đợi service healthy trước khi gửi request, dùng database/schema riêng và xóa tài nguyên sau khi hoàn tất.

Nếu một test chỉ chạy được khi có một service đang chạy sẵn trên máy cá nhân, hãy biến service đó thành dependency được khai báo trong pipeline. Không dựa vào trạng thái ngầm của runner.

## 4. Ví dụ Java 17 và JUnit 5

Tạo một class nhỏ để minh họa test được phát hiện và chạy trong cả Gradle lẫn Maven.

Tệp `src/main/java/com/example/Calculator.java`:

```java
package com.example;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }

    public static int divide(int numerator, int denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException("denominator must not be zero");
        }
        return numerator / denominator;
    }
}
```

Tệp `src/test/java/com/example/CalculatorTest.java`:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(12, Calculator.add(7, 5));
    }

    @Test
    void rejectsDivisionByZero() {
        IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> Calculator.divide(10, 0)
        );

        assertEquals("denominator must not be zero", error.getMessage());
    }
}
```

Hai test kiểm tra kết quả bình thường và điều kiện lỗi. Test không cần file, network hoặc database, vì vậy phù hợp để chạy trên mọi CI runner.

## 5. Chạy unit test bằng Gradle

Với Gradle Java Plugin, test source mặc định nằm trong src/test/java, còn production source nằm trong src/main/java.

Ví dụ build.gradle dùng JUnit 5 và cho phép chọn JDK chạy test qua project property:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

def testJdk = providers.gradleProperty('testJdk')
    .orElse('17')
    .get()
    .toInteger()

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(testJdk)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
```

JUnit BOM đồng bộ version của JUnit artifacts. useJUnitPlatform() yêu cầu Gradle chạy JUnit Platform. junit-platform-launcher cung cấp launcher ở runtime; nên khai báo rõ dependency này khi dùng các phiên bản Gradle hiện đại. options.release = 17 giữ source/API compatibility ở Java 17 trong khi test có thể chạy bằng JDK 17, 21 hoặc 25.

Chạy test trên JDK 17:

```bash
./gradlew -PtestJdk=17 test
```

Chạy toàn bộ verification lifecycle:

```bash
./gradlew -PtestJdk=17 clean check
```

test chạy unit tests. check là lifecycle verification task và có thể phụ thuộc thêm vào integration test, static analysis hoặc các task kiểm tra do project đăng ký.

Gradle tạo report mặc định:

| Report | Đường dẫn |
| --- | --- |
| HTML | build/reports/tests/test/index.html |
| JUnit XML | build/test-results/test/TEST-*.xml |

XML report tương thích với nhiều CI server. HTML report hữu ích khi developer muốn xem từng test, assertion failure và stack trace.

Một lần chạy kiểm thử trên Gradle 9.2.1 với JDK 24.0.2 đã thực thi hai test ở ví dụ trên: addsTwoNumbers và rejectsDivisionByZero đều PASS; cả HTML và XML report được tạo. JDK chạy test có thể khác phiên bản JDK mục tiêu của source.

## 6. Tách integration test bằng Gradle

Integration test thường cần dependency hoặc môi trường riêng. Có thể tạo source set integrationTest để quản lý classpath và report độc lập.

Thêm vào build.gradle:

```groovy
sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    shouldRunAfter tasks.named('test')
    useJUnitPlatform()
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Đặt integration test trong src/integrationTest/java. Ví dụ tên class là CalculatorIT. Khi chạy check, Gradle sẽ chạy test và integrationTest; task integration được sắp xếp sau unit test.

Chạy riêng integration test:

```bash
./gradlew integrationTest
```

Chạy cả hai nhóm:

```bash
./gradlew clean check
```

Report được tách theo task:

- build/test-results/test/
- build/test-results/integrationTest/
- build/reports/tests/test/
- build/reports/tests/integrationTest/

Khi integration test cần database, hãy thêm dependency/service startup và teardown vào pipeline. Không đặt logic kết nối tới service dùng chung trong static initializer vì nó làm test khó cô lập và khó chẩn đoán.

## 7. Chạy unit test bằng Maven Surefire

Maven dùng Surefire Plugin để chạy unit test ở lifecycle phase test. Với JUnit 5, thêm dependency junit-jupiter trong scope test và cố định version plugin.

Ví dụ pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>calculator</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
        <configuration>
          <failIfNoTests>true</failIfNoTests>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Chạy unit test:

```bash
mvn --batch-mode test
```

--batch-mode phù hợp với CI vì không yêu cầu tương tác. Surefire mặc định nhận các tên test phổ biến như TestCalculator, CalculatorTest, CalculatorTests và CalculatorTestCase. Có thể cấu hình include/exclude khi naming convention của project khác.

Report mặc định:

- Text: target/surefire-reports/*.txt
- XML: target/surefire-reports/TEST-*.xml

Có thể mở report XML trong CI để xem số test, failures, errors và skipped. Nếu project bắt buộc có test, bật failIfNoTests ở module đó để một lần chạy không tìm thấy test không bị hiểu nhầm là thành công.

Một lần chạy kiểm thử trên Maven 3.9.12, Surefire 3.5.2 và JDK 24.0.2 đã chạy hai test JUnit 5 thành công: 2 tests, 0 failures, 0 errors, 0 skipped.

## 8. Tách integration test bằng Maven Failsafe

Surefire dành cho unit test. **Failsafe Plugin** dành cho integration test và tham gia hai lifecycle phase integration-test và verify.

Thêm plugin vào pom.xml:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <version>3.5.2</version>
  <executions>
    <execution>
      <goals>
        <goal>integration-test</goal>
        <goal>verify</goal>
      </goals>
    </execution>
  </executions>
</plugin>
```

Maven Failsafe mặc định tìm các tên như ITCalculator, CalculatorIT hoặc CalculatorITCase. Theo cấu hình mặc định, các class này đặt trong src/test/java; Surefire không chọn tên *IT theo pattern unit test mặc định, còn Failsafe sẽ chọn chúng.

Ví dụ src/test/java/com/example/CalculatorIT.java:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorIT {
    @Test
    void integrationFlowUsesCalculator() {
        assertEquals(12, Calculator.add(7, 5));
    }
}
```

Chạy cả unit test và integration test:

```bash
mvn --batch-mode clean verify
```

Điểm quan trọng: hãy gọi verify, không chỉ gọi integration-test. Failsafe hoãn việc đánh dấu build thất bại cho tới phase verify, nhờ vậy phase post-integration-test có thể chạy để dọn môi trường ngay cả khi integration test thất bại.

Report được tách:

- Unit test: target/surefire-reports/
- Integration test: target/failsafe-reports/

Một lần kiểm thử trên Maven 3.9.12 và Failsafe 3.5.2 đã chạy CalculatorTest và CalculatorIT thành công; hai thư mục report đều có XML tương ứng.

## 9. GitHub Actions: test Gradle trên nhiều JDK

Ma trận JDK giúp phát hiện lỗi tương thích giữa các runtime mà dự án hỗ trợ. Ví dụ dưới đây kiểm tra Java 17, 21 và 25. Hãy thay danh sách này theo chính sách tương thích của project.

Tệp .github/workflows/gradle-ci.yml:

```yaml
name: Java Gradle CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: gradle

      - name: Show Java version
        run: java --version

      - name: Run verification
        run: ./gradlew --no-daemon -PtestJdk=${{ matrix.java }} clean check

      - name: Upload test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: gradle-test-reports-jdk-${{ matrix.java }}
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
          if-no-files-found: ignore
```

Giải thích:

- actions/setup-java cài JDK, thiết lập JAVA_HOME và có thể cache dependency của Gradle.
- matrix.java tạo một job riêng cho mỗi JDK.
- fail-fast: false cho phép các job JDK còn lại tiếp tục để thấy toàn bộ kết quả ma trận; một job thất bại vẫn làm workflow thất bại.
- clean check chạy unit test và các verification task đã đăng ký.
- if: always() chỉ áp dụng cho upload report, nên report vẫn được lưu khi test job thất bại.
- permissions: contents: read giới hạn quyền token cho một pipeline chỉ cần đọc source.

Nếu dùng self-hosted runner, cần phiên bản runner tương thích với runtime Node.js 24 của các action hiện đại. Nên kiểm tra yêu cầu phiên bản runner trong tài liệu action trước khi nâng cấp.

## 10. GitHub Actions: test Maven và lưu Surefire/Failsafe reports

Tệp .github/workflows/maven-ci.yml:

```yaml
name: Java Maven CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      matrix:
        java: ['17', '21', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven

      - name: Show Java version
        run: java --version

      - name: Run verification
        run: mvn --batch-mode --no-transfer-progress clean verify

      - name: Upload test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: maven-test-reports-jdk-${{ matrix.java }}
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
          if-no-files-found: ignore
```

Nếu project chỉ có unit test và chưa cấu hình Failsafe, có thể dùng mvn clean test. Khi đã đăng ký Failsafe, mvn clean verify là lệnh phù hợp để chạy cả unit và integration tests cùng các bước teardown.

Artifact chứa XML report giúp developer tải về và phân tích lỗi sau khi job kết thúc. Không cần giữ toàn bộ thư mục build trong cache chỉ để xem report; report nên được upload dưới dạng artifact riêng.

Các action version trong ví dụ là major version hiện hành tại thời điểm viết. Với pipeline yêu cầu supply-chain control chặt chẽ, có thể pin action bằng commit SHA đã xác minh và cập nhật có kiểm soát.

## 11. GitLab CI: đưa JUnit XML vào pipeline

GitLab có thể hiển thị JUnit XML trong pipeline và merge request. Ví dụ với Maven:

Tệp .gitlab-ci.yml:

```yaml
image: maven:3.9.12-eclipse-temurin-17

stages:
  - test

variables:
  MAVEN_OPTS: "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"

cache:
  key:
    files:
      - pom.xml
  paths:
    - .m2/repository/

test:
  stage: test
  script:
    - mvn --batch-mode --no-transfer-progress clean verify
  artifacts:
    when: always
    reports:
      junit:
        - target/surefire-reports/TEST-*.xml
        - target/failsafe-reports/TEST-*.xml
    paths:
      - target/surefire-reports/
      - target/failsafe-reports/
    expire_in: 1 week
```

artifacts:reports:junit cho GitLab biết file nào chứa kết quả test. artifacts:paths giữ thêm các file để tải và kiểm tra trực tiếp. when: always bảo đảm artifacts thông thường được thu thập kể cả khi script test thất bại.

Với Gradle, đổi command thành ./gradlew clean check và report paths thành build/test-results/** cùng build/reports/tests/**. Image runner cần chứa JDK/Gradle phù hợp hoặc cài JDK trong job.

## 12. Chọn JDK matrix và target release

Test trên nhiều JDK không có nghĩa mỗi lần build đều phải thay đổi target API.

Ví dụ một thư viện hỗ trợ Java 17 trở lên:

- JDK 17: baseline runtime.
- JDK 21: kiểm tra runtime LTS mới hơn.
- JDK 25: kiểm tra runtime LTS hiện hành.
- Compiler vẫn dùng --release 17 để ngăn việc vô tình sử dụng API mới hơn Java 17.

Với Gradle, chọn toolchain qua property và đặt options.release = 17. Với Maven, đặt maven.compiler.release là 17, còn CI thay JDK qua actions/setup-java.

Ma trận không nhất thiết phải gồm mọi OS và mọi JDK. Một ma trận quá lớn làm pipeline chậm và tốn tài nguyên. Hãy chọn những tổ hợp đại diện cho support matrix của sản phẩm; thêm Windows/macOS khi code có hành vi phụ thuộc OS, filesystem hoặc native library.

## 13. Cache, artifact và wrapper

Ba khái niệm này có vai trò khác nhau:

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| Dependency cache | Giảm thời gian tải dependency | .gradle/caches, .m2/repository |
| Build artifact | Đầu ra cần dùng ở job sau hoặc phát hành | JAR, Docker image, generated package |
| Test report artifact | Bằng chứng để phân tích kết quả test | JUnit XML, HTML report, log |

Cache không thay thế report và không nên dùng để che lỗi test. Cache nên có key dựa trên file quản lý dependency như build.gradle, version catalog, gradle-wrapper.properties hoặc pom.xml. Khi dependency thay đổi, key mới giúp runner tải đúng dependency.

Commit Gradle Wrapper và Maven Wrapper vào repository:

- Gradle: ./gradlew
- Maven: ./mvnw

Wrapper giúp local và CI sử dụng cùng phiên bản build tool. Không nên dựa vào phiên bản Gradle/Maven ngẫu nhiên được cài sẵn trên runner.

Nếu build dùng JDK toolchain, bảo đảm JDK tương ứng được cài hoặc được Gradle provision theo cấu hình rõ ràng. Không để CI âm thầm chọn một compiler khác với local.

## 14. Test thất bại, skip và report

CI cần phân biệt các trạng thái:

| Trạng thái | Ý nghĩa | Xử lý |
| --- | --- | --- |
| Passed | Test thực thi và assertion thành công | Job có thể tiếp tục |
| Failed | Assertion hoặc test logic thất bại | Job phải thất bại |
| Error | Test gặp exception ngoài kết quả mong đợi | Job phải thất bại |
| Skipped | Test không được thực thi do điều kiện hoặc annotation | Kiểm tra lý do skip |
| No tests found | Không phát hiện test phù hợp | Xác minh discovery/naming và fail nếu project yêu cầu có test |

Các lệnh bỏ qua test cần được kiểm soát:

- Maven -DskipTests bỏ qua chạy test nhưng vẫn có thể compile test source.
- Maven -Dmaven.test.skip=true bỏ qua cả compile và chạy test.
- Gradle -x test loại task test khỏi execution graph.

Những tùy chọn này hữu ích trong một số tác vụ đóng gói riêng, nhưng không nên xuất hiện trong job CI được dùng làm required test check. Không dùng continue-on-error hoặc || true quanh lệnh test để che exit code khác 0.

Upload report trong always() là cách giữ bằng chứng thất bại. Điều kiện này không được đặt cho chính bước test. Job test vẫn phải giữ nguyên trạng thái failure nếu test thất bại.

## 15. Tính ổn định và tốc độ của test suite

Khi bộ test lớn dần, cần tối ưu mà vẫn giữ độ tin cậy.

**Chạy song song có kiểm soát**

Gradle hỗ trợ maxParallelForks; Maven Surefire có forkCount và reuseForks. Tăng parallelism có thể rút ngắn thời gian, nhưng nếu test dùng chung database, port, file hoặc static state thì dễ tạo race condition. Bắt đầu với mức thấp rồi đo CPU, RAM và thời gian.

**Chia nhóm test**

Có thể chia unit, integration và E2E thành các job/stage riêng. Unit test chạy nhanh trên mỗi pull request; E2E test có thể chạy sau khi deploy lên môi trường kiểm thử hoặc theo lịch. Test bắt buộc vẫn cần chặn merge/release ở stage tương ứng.

**Quản lý flaky test**

Một test lúc pass lúc fail thường báo hiệu phụ thuộc thời gian, race condition, shared state hoặc service không ổn định. Có thể chạy lại để thu thập bằng chứng, nhưng retry không nên biến lỗi ban đầu thành trạng thái xanh không được ghi nhận. Theo dõi flaky test như một vấn đề kỹ thuật cần sửa.

**Coverage**

Coverage đo phần code được thực thi, không chứng minh test kiểm tra đúng hành vi. Nếu dùng JaCoCo hoặc công cụ tương đương, có thể đặt threshold cho line/branch coverage ở module quan trọng. Không tăng coverage bằng test chỉ gọi getter hoặc chạy qua code mà không có assertion có ý nghĩa.

## 16. Bảo mật và độ tin cậy của CI test

CI thường chạy code do contributor gửi lên, vì vậy quyền runner và secret phải được giới hạn.

- Chỉ cấp GITHUB_TOKEN quyền cần thiết; job chỉ checkout và test thường chỉ cần contents: read.
- Không đưa production secret vào test của pull request từ fork.
- Không dùng workflow pull_request_target để checkout và thực thi code không tin cậy nếu chưa thiết kế ranh giới bảo mật phù hợp.
- Dùng service account và database tạm cho integration test.
- Không in credential hoặc token vào test output.
- Tách test job khỏi deploy job; deploy chỉ chạy sau khi test gate thành công và có điều kiện branch/environment phù hợp.
- Với self-hosted runner, giới hạn repository/job được phép sử dụng và dọn workspace sau khi chạy.
- Pin dependency và CI actions theo chính sách supply-chain của tổ chức.

Test trong CI không nên truy cập dữ liệu production. Nếu cần dữ liệu gần thực tế, dùng fixture đã ẩn danh hoặc dataset tổng hợp.

## 17. Troubleshooting lỗi test trong CI

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Build xanh nhưng không có test report | Test discovery không tìm thấy class hoặc task bị skip | Kiểm tra tên class, source set và report directory |
| Gradle không load JUnit Platform | Thiếu engine/launcher hoặc chưa bật useJUnitPlatform() | Thêm JUnit Jupiter, launcher runtime và cấu hình platform |
| Maven không phát hiện JUnit 5 | Thiếu Jupiter engine hoặc Surefire quá cũ | Kiểm tra dependency và pin Surefire version |
| Test pass local nhưng fail trên CI | Khác JDK, timezone, locale, OS hoặc environment variable | In version, cố định môi trường và tạo test độc lập |
| Integration test timeout | Service chưa healthy, port sai hoặc readiness chưa hoàn tất | Dùng health check và retry kết nối có giới hạn |
| Test chạy riêng pass nhưng chạy cùng suite fail | Shared state, thứ tự test hoặc resource contention | Cô lập fixture, schema, file và port |
| Test report không có sau failure | Upload artifact chỉ chạy khi job thành công | Dùng always() cho bước upload |
| Ma trận JDK thất bại chỉ ở một version | API/runtime behavior hoặc compiler target khác nhau | Xem log job riêng và kiểm tra source compatibility |
| Maven verify không chạy integration test | Chưa đăng ký Failsafe execution hoặc class name sai | Kiểm tra plugin goals và pattern *IT |
| Gradle check chỉ chạy unit test | Chưa gắn integrationTest vào check | Thêm dependency task |
| Build mất nhiều thời gian tải dependency | Chưa cache hoặc cache key thay đổi liên tục | Cache theo wrapper/build files |
| Test thất bại nhưng pipeline vẫn xanh | continue-on-error, || true hoặc skip flag | Giữ exit code và bỏ tùy chọn che lỗi |

## 18. Quy trình thiết lập CI test từ đầu

1. Xác định JDK tối thiểu và các JDK runtime cần hỗ trợ.
2. Commit Gradle/Maven Wrapper và pin version plugin.
3. Chuẩn hóa source layout và naming convention cho unit/integration tests.
4. Chọn JUnit 5 hoặc test framework phù hợp.
5. Cấu hình Gradle test hoặc Maven Surefire.
6. Tạo integration test task/phase riêng nếu cần service phụ trợ.
7. Đảm bảo check hoặc verify thực thi mọi test bắt buộc.
8. Chạy lệnh test trên máy local để xác nhận report và exit code.
9. Tạo workflow cho push/pull request và JDK matrix.
10. Cache dependency, upload report bằng điều kiện luôn chạy.
11. Đặt CI check thành required status check cho branch protection.
12. Theo dõi test duration, flaky rate và report failure để cải thiện suite.

Với Gradle, command thường dùng là:

```bash
./gradlew --no-daemon clean check
```

Với Maven, command thường dùng là:

```bash
mvn --batch-mode --no-transfer-progress clean verify
```

Dùng check khi Gradle đã đăng ký unit/integration verification task; dùng verify khi Maven đã cấu hình Surefire/Failsafe và các bước kiểm tra sau test.

## 19. Ghi nhớ

- CI test tự động chạy bộ test trên mỗi thay đổi và cung cấp quality gate trước merge/release.
- Unit test nên nhanh, độc lập và chạy ở mọi pull request; integration/E2E test cần môi trường và lịch chạy rõ ràng.
- JUnit 5 cần được cấu hình đúng trong Gradle/Maven; với Gradle hiện đại, khai báo launcher runtime rõ ràng.
- Gradle test chạy unit test; gắn integrationTest vào check để chạy cả hai nhóm.
- Maven Surefire chạy unit test ở phase test; Failsafe chạy integration test và kiểm tra kết quả ở verify.
- Dùng mvn verify để Failsafe có cơ hội chạy bước teardown trước khi đánh dấu build thất bại.
- JUnit XML và HTML report cần được lưu dưới dạng artifact, kể cả khi test job thất bại.
- JDK matrix phải theo support policy; giữ compiler release riêng nếu cần tương thích API với phiên bản thấp hơn.
- Cache dependency để tăng tốc; không nhầm cache với test report hoặc build artifact.
- Test thất bại phải làm job trả exit code khác 0; không che lỗi bằng skip hoặc continue-on-error.
- Tách biệt dữ liệu, service và secret; không chạy test với production credentials/data.
- Theo dõi flaky test, thời gian chạy và coverage như các chỉ số để cải thiện chất lượng suite.

Một pipeline Java đáng tin cậy không chỉ chạy được lệnh test. Nó phải bảo đảm đúng test được phát hiện, đúng JDK được kiểm tra, report luôn có thể xem lại và mọi lỗi bắt buộc đều chặn được quá trình merge hoặc phát hành.

## Tài liệu tham khảo

- [Gradle: Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
- [GitHub Actions: actions/checkout](https://github.com/actions/checkout)
- [GitHub Actions: actions/upload-artifact](https://github.com/actions/upload-artifact)
- [GitHub Actions: Using jobs and matrix strategies](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs)
- [GitLab CI/CD YAML syntax](https://docs.gitlab.com/ci/yaml/)
- [GitLab CI/CD JUnit test reports](https://docs.gitlab.com/ci/yaml/artifacts_reports/)
