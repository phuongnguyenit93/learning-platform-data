# Tích hợp kiểm tra định dạng, phân tích tĩnh và độ bao phủ vào Maven verify hoặc Gradle check

## 1. Mục tiêu: biến chất lượng mã thành điều kiện để bản dựng thành công

Trong một dự án Spring Boot, chạy test thành công chưa chứng minh rằng mã đã được định dạng thống nhất, không có lỗi tiềm ẩn hoặc đã được kiểm thử đủ. Ba nhóm kiểm tra thường được thêm vào **quality gate** của build:

1. **Kiểm tra định dạng (format check)**: xác nhận mã tuân thủ một formatter thống nhất. Ví dụ Spotless kết hợp Google Java Format. Đích là kiểm tra, không tự ý sửa mã trong CI.
2. **Phân tích tĩnh (static analysis)**: phân tích source/bytecode mà không cần chạy những đường logic được xét. Ví dụ PMD phát hiện một số mẫu Java dễ gây lỗi, Checkstyle kiểm tra quy tắc style, SpotBugs kiểm tra pattern trên bytecode. Các công cụ có phạm vi khác nhau.
3. **Độ bao phủ kiểm thử (test coverage)**: đo phần bytecode được thực thi bởi test. Ví dụ JaCoCo thống kê line/branch/instruction coverage và áp ngưỡng tối thiểu.

Mục tiêu cuối là: **một câu lệnh dùng chung ở máy cá nhân và CI sẽ trả mã thoát khác 0 nếu kiểm tra bắt buộc thất bại**.

- Với **Maven**, câu lệnh chuẩn là `./mvnw verify` (Windows: `mvnw.cmd verify`). Các plugin goal phải được **bind vào lifecycle**, thường ở phase `verify`.
- Với **Gradle**, câu lệnh chuẩn là `./gradlew check` (Windows: `gradlew.bat check`). Các task kiểm tra phải nằm trong **dependency graph của task `check`**.

Chạy một lần `spotless:check`, `pmd:check` hay `jacocoTestCoverageVerification` rồi không nối chúng vào lifecycle/task graph **không có nghĩa** `verify` hoặc `check` sẽ chạy chúng.

## 2. Bảng đối chiếu Maven và Gradle

| Chức năng | Maven | Gradle | Điều gì khiến build fail? |
|---|---|---|---|
| Unit test | Maven Surefire Plugin ở phase `test` | Task `test` là dependency của `check` với Java plugin | Test thất bại hoặc lỗi khi chạy test |
| Formatting | Spotless Maven Plugin goal `spotless:check` | Spotless Gradle task `spotlessCheck` | Source khác kết quả formatter mong đợi |
| Sửa định dạng trên máy lập trình | `spotless:apply` | `spotlessApply` | Đây là lệnh **thay đổi file**, không dùng làm gate kiểm tra trong CI |
| Phân tích tĩnh nguồn Java | Maven PMD Plugin goal `pmd:check` | PMD plugin: `pmdMain`, `pmdTest` | Có rule violation vượt giới hạn đã đặt |
| Quy tắc style Java thay thế/bổ sung | Maven Checkstyle Plugin goal `checkstyle:check` | Checkstyle plugin: `checkstyleMain`, `checkstyleTest` | Vi phạm rule set |
| Phân tích bytecode | SpotBugs Maven plugin goal `spotbugs:check` | SpotBugs Gradle plugin và các task liên quan | Vi phạm được cấu hình để fail |
| Thu dữ liệu coverage | JaCoCo `prepare-agent` + test | JaCoCo agent gắn vào `Test` task | Bản thân thu dữ liệu chưa phải gate |
| Sinh coverage report | JaCoCo `report` | `jacocoTestReport` | Lỗi tool/report, nhưng **không mặc nhiên fail vì % thấp** |
| Kiểm tra ngưỡng coverage | JaCoCo `check` | `jacocoTestCoverageVerification` | Tỷ lệ không đạt rule |
| Điểm vào duy nhất | `mvn verify` | `gradle check` | Một hoặc nhiều kiểm tra được nối vào entry point và trả exit code lỗi |

**Điểm khác biệt cốt lõi:** Maven là **phase lifecycle** với các plugin goal được gắn vào phase; Gradle là **task graph** với dependency `dependsOn`. Phân biệt “công cụ đã được khai báo” với “công cụ chắc chắn chạy khi gọi lệnh chính”.

## 3. Maven verify thực sự chạy những gì?

Maven default lifecycle thường đi qua các phase theo thứ tự như:

```text
validate -> compile -> test -> package
           -> integration-test -> verify -> install -> deploy
```

Khi chạy `./mvnw verify`, Maven thực hiện các phase đến `verify`, gồm các plugin goal đã ràng buộc với chúng. **Không nhất thiết** mọi phase sẽ có goal hoặc integration test. Một project Spring Boot dùng `spring-boot-starter-parent` có sẵn nhiều cấu hình plugin, nhưng không tự có Spotless, PMD, JaCoCo coverage gate chỉ vì bạn gọi `verify`.

Ví dụ phân bổ có chủ đích:

```text
initialize       -> JaCoCo prepare-agent
test             -> Surefire thực thi JUnit, tạo target/jacoco.exec
package          -> Đóng gói JAR (cấu hình Spring Boot phù hợp)
verify           -> Spotless check
                 -> PMD check
                 -> JaCoCo report
                 -> JaCoCo check (đối chiếu threshold)
```

JaCoCo `prepare-agent` phải thiết lập JVM agent **trước khi test chạy**. JaCoCo `report` dùng file execution data từ test. JaCoCo `check` cần rule rõ ràng: nếu không cấu hình ngưỡng, việc có report không tự bảo đảm coverage đạt mức tổ chức mong muốn.

**Giữa các goal cùng phase, thứ tự có thể quan trọng**. Ở ví dụ POM bên dưới, đặt JaCoCo report trước check để tạo báo cáo trước lúc áp ngưỡng. Tuy nhiên, build thường dừng khi một gate thất bại, nên không thể hứa rằng mọi báo cáo khác đều được sinh trong cùng lần chạy thất bại. CI nên lưu các artifact báo cáo đã tạo dù job exit code khác 0.

## 4. Gradle check thực sự chạy những gì?

Với Gradle Java plugin, `check` là lifecycle task cho việc xác minh. Task này mặc định phụ thuộc vào `test`; các plugin khác có thể thêm task phân tích:

- PMD plugin tự nối `pmdMain` và `pmdTest` vào `check`.
- Checkstyle plugin tự nối `checkstyleMain` và `checkstyleTest` vào `check`.
- Spotless Gradle plugin thường thêm `spotlessCheck` vào `check`, nhưng có thể nối tường minh để đảm bảo chính sách dự án.
- JaCoCo plugin tạo `jacocoTestReport` và `jacocoTestCoverageVerification`, nhưng **verification KHÔNG tự là dependency của `check`**. Bạn phải nối nếu yêu cầu kiểm tra coverage khi chạy `check`.

Đồ thị mong muốn cho ví dụ Gradle ở dưới:

```text
./gradlew check
       |
       +-- test --------------------------------+
       |                                        |
       +-- pmdMain / pmdTest (qua PMD plugin)  |
       |                                        v
       +-- spotlessCheck               jacocoTestReport
                                                |
                                                v
                                    jacocoTestCoverageVerification
```

Sơ đồ biểu diễn quan hệ logic, không bảo đảm thứ tự in log hay Gradle luôn thực thi các task theo đúng thứ tự dọc này. `check` thành công chỉ khi các dependency task được yêu cầu đều thành công.

**Phân biệt `check` và `build`:** ở project có Java plugin, `build` thường phụ thuộc `assemble` và `check`. Vì vậy nếu nối gate vào `check`, gọi `build` cũng kích hoạt chúng. Nếu chỉ gọi `bootJar` hoặc `assemble`, bạn **không được giả định** toàn bộ gate sẽ chạy; chính sách CI nên gọi `check` hoặc `build` rõ ràng.

## 5. Chuẩn bị một dự án Spring Boot Java 17 để thực hành

Bài học dùng một ví dụ chung cho Maven và Gradle. Hãy khởi tạo project Spring Boot Java với:

- Java 17+ phù hợp với phiên bản Spring Boot.
- Spring Boot 3.5.x (ví dụ cấu hình `3.5.16` ở dưới).
- Dependency `spring-boot-starter-test` cho JUnit Jupiter.
- Một trong hai build tool Maven **hoặc** Gradle, có wrapper tương ứng.

Cấu trúc source:

```text
quality-demo/
├── pom.xml hoặc build.gradle
├── mvnw, mvnw.cmd  [nếu chọn Maven]
├── gradlew, gradlew.bat [nếu chọn Gradle]
├── src/
│   ├── main/java/com/example/quality/
│   │   ├── QualityApplication.java
│   │   └── DiscountCalculator.java
│   └── test/java/com/example/quality/
│       └── DiscountCalculatorTest.java
└── target/ hoặc build/   [sinh sau khi build]
```

**Không tạo cả hai build file chỉ để trộn quy trình.** Các file Java sau đây được dùng chung cho **hai** cấu hình thay thế ở mục Maven và Gradle.

### 5.1. Ứng dụng Spring Boot

File `src/main/java/com/example/quality/QualityApplication.java`:

```java
package com.example.quality;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QualityApplication {
    public static void main(String[] args) {
        SpringApplication.run(QualityApplication.class, args);
    }
}
```

Lớp này tạo entry point cho executable JAR. Kiểm thử bên dưới **không cần khởi động Spring context** vì phần business logic là Java thuần; đây là một cách giữ unit test nhanh.

### 5.2. Logic Java có nhánh để đo coverage

File `src/main/java/com/example/quality/DiscountCalculator.java`:

```java
package com.example.quality;

public final class DiscountCalculator {
    public int total(int price, boolean member) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        return member ? price * 9 / 10 : price;
    }
}
```

- Nhánh `price < 0` kiểm tra giá trị không hợp lệ.
- Nhánh `member` tính giá sau giảm 10%.
- Nhánh còn lại giữ nguyên giá.

Phép tính sử dụng `int` và **phép chia số nguyên**; ví dụ chỉ phục vụ test/coverage, **không** phải cách xử lý tiền tệ chuẩn trong hệ thống tài chính. Trong sản phẩm thực tế, nên dùng `BigDecimal` hoặc đơn vị tiền nhỏ nhất với chính sách làm tròn cụ thể.

### 5.3. JUnit Jupiter test

File `src/test/java/com/example/quality/DiscountCalculatorTest.java`:

```java
package com.example.quality;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DiscountCalculatorTest {
    private final DiscountCalculator calculator = new DiscountCalculator();

    @Test
    void memberGetsDiscount() {
        assertEquals(90, calculator.total(100, true));
    }

    @Test
    void nonMemberPaysFullPrice() {
        assertEquals(100, calculator.total(100, false));
    }

    @Test
    void negativePriceIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.total(-1, true));
    }
}
```

Các test kiểm tra cả hai đường tính giá và trường hợp ném exception; số học mong đợi là `90`, `100` và `IllegalArgumentException`. Đây là file test chạy trong dự án có **JUnit Jupiter trên test classpath**; không biên dịch được chỉ bằng `javac` trần nếu thiếu dependency JUnit. Không có stdout cố định cho test: Maven/Gradle in báo cáo tùy plugin, còn các assert sẽ fail nếu kết quả khác mong đợi.

**Cẩn trọng với bộ định dạng:** đoạn Java trên dễ hiểu nhưng không nhất thiết đã đúng *từng dấu cách/xuống dòng* theo version Google Java Format đã chọn. Chạy `spotlessApply`/`spotless:apply` một lần trên máy làm việc trước khi mong `spotlessCheck`/`spotless:check` PASS.

## 6. Maven: thêm ba quality gate vào phase verify

### 6.1. POM có thể dùng để xây dựng ứng dụng

Ví dụ `pom.xml` dùng Spring Boot starter parent, Java 17, Spotless, PMD và JaCoCo. Các phiên bản plugin dưới đây là **các bản phát hành cụ thể để ví dụ có thể tái hiện**, không có yêu cầu luôn phải dùng bản mới nhất của mọi plugin. Hãy xác minh compatibility JDK/Maven/plugin tại repository thực tế trước khi nâng cấp.

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
    <artifactId>quality-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- Spring Boot executable JAR -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <!-- 1) Formatting: check (không tự sửa file trong CI) -->
            <plugin>
                <groupId>com.diffplug.spotless</groupId>
                <artifactId>spotless-maven-plugin</artifactId>
                <version>3.10.4</version>
                <configuration>
                    <java>
                        <googleJavaFormat>
                            <version>1.30.0</version>
                        </googleJavaFormat>
                    </java>
                </configuration>
                <executions>
                    <execution>
                        <id>check-formatting</id>
                        <phase>verify</phase>
                        <goals><goal>check</goal></goals>
                    </execution>
                </executions>
            </plugin>

            <!-- 2) Static analysis: PMD -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-pmd-plugin</artifactId>
                <version>3.28.0</version>
                <configuration>
                    <failOnViolation>true</failOnViolation>
                    <printFailingErrors>true</printFailingErrors>
                    <rulesets>
                        <ruleset>/category/java/errorprone.xml</ruleset>
                    </rulesets>
                </configuration>
                <executions>
                    <execution>
                        <id>check-static-analysis</id>
                        <phase>verify</phase>
                        <goals><goal>check</goal></goals>
                    </execution>
                </executions>
            </plugin>

            <!-- 3) Coverage: agent trước test, report + threshold -->
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.16</version>
                <executions>
                    <execution>
                        <id>attach-coverage-agent</id>
                        <goals><goal>prepare-agent</goal></goals>
                    </execution>
                    <execution>
                        <id>coverage-report</id>
                        <phase>verify</phase>
                        <goals><goal>report</goal></goals>
                    </execution>
                    <execution>
                        <id>coverage-threshold</id>
                        <phase>verify</phase>
                        <goals><goal>check</goal></goals>
                        <configuration>
                            <rules>
                                <rule>
                                    <element>BUNDLE</element>
                                    <limits>
                                        <limit>
                                            <counter>LINE</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>0.50</minimum>
                                        </limit>
                                    </limits>
                                </rule>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**Điểm cần QA trước khi áp dụng:**

- Phần `pom.xml` đã đưa **plugin trong `<build><plugins>`** và khai báo `<executions>`, không chỉ để plugin trong `<pluginManagement>`; vì pluginManagement *định nghĩa mặc định* chứ không tự áp dụng mọi goal.
- Spotless goal `check` được bind vào `verify`. PMD goal `check` cũng được bind vào `verify`; theo tài liệu Maven PMD, goal này có thể gọi quá trình phân tích `pmd` trước khi kiểm tra vi phạm.
- JaCoCo `prepare-agent` được đặt ở phase mặc định thích hợp của goal để agent tham gia quá trình test. `report` và `check` chạy ở `verify`; rule đo tỷ lệ **LINE/COVEREDRATIO** của **BUNDLE**.
- Ngưỡng **0.50 = 50%** chỉ là điểm bắt đầu cho ví dụ có một Spring Boot bootstrap class chưa được unit test trực tiếp. Ở dự án thật, chọn ngưỡng mục tiêu cao hơn, phù hợp baseline, loại trừ có lý do và phân loại module; **không gọi 50% là chuẩn chất lượng phổ quát**.
- Dùng `spring-boot-starter-parent` nhận các compiler/test defaults phù hợp. Nếu dùng corporate parent thay thế, cần cấu hình compiler/JUnit Surefire/Spring Boot repackage tương ứng.
- Nếu sửa custom `maven-surefire-plugin` `argLine`, không được vô tình ghi đè thông số agent JaCoCo; xem cơ chế **late property evaluation** khi phải kết hợp JDWP, module options hoặc custom JVM flags.
- Các plugin cần tải về từ repository; build có thể thất bại nếu thiếu internet, proxy/credentials hoặc thiếu Maven/JDK tương thích. Mã nguồn ở mục 5 và POM này tạo một project hợp lệ về mặt cấu trúc, nhưng vẫn cần wrapper/JDK của môi trường thật.

### 6.2. Lệnh Maven để kiểm tra từng loại

```bash
# Sửa định dạng SOURCE trên máy phát triển, sau đó review Git diff
./mvnw spotless:apply

# Chỉ xem có vi phạm format hay không
./mvnw spotless:check

# Kiểm tra static analysis
./mvnw pmd:check

# Chạy đầy đủ lifecycle test/package/quality gates
./mvnw clean verify
```

**Mẹo:** `./mvnw pmd:check` có thể cần source/dependency đã có trạng thái phù hợp; để chẩn đoán từ checkout sạch, chạy `./mvnw verify` theo lifecycle đầy đủ. Không dùng `spotless:apply` trong CI vì nó thay đổi files trong working tree mà không buộc developer review/commit thay đổi.

### 6.3. Phân biệt các loại kết quả Maven

- **Source sai format:** `spotless:check` fail ở phase `verify`, log chỉ ra file và yêu cầu chạy apply.
- **PMD phát hiện mẫu bị cấm:** `pmd:check` fail nếu vi phạm vượt cấu hình. `maven-pmd-plugin` có thể tạo report tại `target/`; đường dẫn chính xác phụ thuộc plugin config.
- **Test đỏ:** Maven thường dừng ở phase `test` trước khi vào `verify`. Vì vậy một lần `verify` fail không đảm bảo bạn đã chạy được các quality gates ở cuối.
- **Coverage dưới 50%:** JaCoCo `check` fail ở `verify` khi có dữ liệu đo và rule tính được. Báo cáo HTML mặc định của goal `report` thường ở `target/site/jacoco/index.html`; XML tại `target/site/jacoco/jacoco.xml` khi định dạng XML được bật.
- **Không có dữ liệu coverage:** JaCoCo có thể log “Skipping JaCoCo execution due to missing execution data file”; **đây không tự động đồng nghĩa 0% và fail ngưỡng**. Để gate đáng tin, CI phải thực sự chạy test, thu execution data và kiểm tra đầu ra không bị mất.
- **Chạy `mvn package` thay vì `mvn verify`:** không mặc nhiên kích hoạt các goal đang bind ở `verify`. Vì thế CI phải gọi **verify**.

## 7. Gradle: nối Spotless, PMD, JaCoCo vào check

### 7.1. Một build.gradle Groovy DSL có thể dùng

Giả sử project Spring Boot Gradle được tạo từ Spring Initializr, có `settings.gradle` và Gradle Wrapper. `settings.gradle` tối giản:

```groovy
rootProject.name = 'quality-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'

    // Formatting
    id 'com.diffplug.spotless' version '8.11.0'

    // Static analysis và coverage là Gradle core plugins
    id 'pmd'
    id 'jacoco'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

// 1) Định dạng Java thống nhất, bao gồm source và test source
spotless {
    java {
        googleJavaFormat('1.30.0')
    }
}

// 2) PMD: một tập rule Java ví dụ, không bỏ qua lỗi
pmd {
    toolVersion = '7.16.0'
    ruleSets = ['category/java/errorprone.xml']
    ignoreFailures = false
    consoleOutput = true
}

// 3) JaCoCo thu coverage khi test chạy
jacoco {
    toolVersion = '0.8.16'
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        xml.required = true
        html.required = true
    }
}

tasks.named('jacocoTestCoverageVerification') {
    // Xây dependency để report và test chạy trước khi áp ngưỡng.
    dependsOn tasks.named('jacocoTestReport')
    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.50
            }
        }
    }
}

tasks.named('check') {
    // PMD plugin tự nối pmdMain/pmdTest vào check.
    // Nối Spotless và coverage tường minh cho dễ audit.
    dependsOn tasks.named('spotlessCheck'),
              tasks.named('jacocoTestCoverageVerification')
}
```

**Đọc kỹ những dây nối task:**

1. `id 'java'` tạo task `test`, `check` và quy ước `src/main/java`/`src/test/java`.
2. Spring Boot plugin hỗ trợ đóng gói ứng dụng, không tự thay thế static analysis hay coverage gate.
3. `id 'com.diffplug.spotless'` cung cấp `spotlessCheck` và `spotlessApply`. Ở nhiều version, Spotless đã tự nối vào `check`; `dependsOn` tường minh ở trên giúp thấy rõ điều kiện dự án muốn.
4. `id 'pmd'` cung cấp `pmdMain`/`pmdTest`, đồng thời tự nối các task này vào `check`; không cần gọi PMD bằng tay khi chạy check.
5. `id 'jacoco'` thêm công cụ đo vào Java `Test` task và cung cấp report/verification task.
6. `jacocoTestReport.dependsOn test` đảm bảo test chạy trước khi tạo report. `jacocoTestCoverageVerification.dependsOn jacocoTestReport` đảm bảo report và dữ liệu đã được tạo trước khi áp ngưỡng.
7. `check.dependsOn spotlessCheck, jacocoTestCoverageVerification` là bước **bắt buộc có chủ đích** của ví dụ. Không chỉ gọi `jacoco { ... }` rồi tưởng check đã biết phải xét phần trăm.
8. `ignoreFailures = false` cho PMD là chính sách fail khi vi phạm; nếu chuyển thành `true`, report có thể vẫn sinh nhưng `check` có thể không fail vì PMD violation.
9. `toolVersion` chỉ định phiên bản engine PMD/JaCoCo, không đồng nhất với version Gradle plugin/Wrapper. Chọn version engine phù hợp JDK và build tool.

Các plugin/version trên là ví dụ **cần wrapper và JVM phù hợp**; đặc biệt khi nâng phiên bản Spotless/Gradle/Boot trong hệ thống đã vận hành, xác minh compatibility và thử `./gradlew help` trước. Với project dùng Gradle Kotlin DSL, **cú pháp khác** — không copy trực tiếp Groovy code vào `build.gradle.kts`.

### 7.2. Lệnh Gradle để thực hành

```bash
# Áp định dạng trên máy phát triển rồi xem git diff
./gradlew spotlessApply

# Kiểm tra định dạng mà không sửa source
./gradlew spotlessCheck

# Chạy phân tích tĩnh riêng
./gradlew pmdMain pmdTest

# Chạy unit test và sinh coverage report
./gradlew test jacocoTestReport

# Chỉ kiểm tra ngưỡng coverage (đã cấu hình dependsOn report/test)
./gradlew jacocoTestCoverageVerification

# Chạy toàn bộ quality gates
./gradlew clean check

# Compile/package + tất cả check trong Java lifecycle
./gradlew build
```

`./gradlew clean check` trước tiên xóa output trong `build/`. Không nhất thiết phải clean ở mỗi lần phát triển: dùng `./gradlew check` để tận dụng incremental compilation và up-to-date tasks, sau đó clean khi cần loại bỏ output cũ.

### 7.3. Gradle Kotlin DSL: những đoạn chuyển cú pháp cần biết

Nếu project dùng `build.gradle.kts`, khối plugin tương đương:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
    id("com.diffplug.spotless") version "8.11.0"
    pmd
    jacoco
}
```

Và các thiết lập quality gate chính (đoạn này được thêm vào `build.gradle.kts` đã có `repositories`, `dependencies` và Java toolchain):

```kotlin
spotless {
    java {
        googleJavaFormat("1.30.0")
    }
}

pmd {
    toolVersion = "7.16.0"
    ruleSets = listOf("category/java/errorprone.xml")
    isIgnoreFailures = false
}

jacoco {
    toolVersion = "0.8.16"
}

tasks.test {
    useJUnitPlatform()
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

tasks.jacocoTestCoverageVerification {
    dependsOn(tasks.jacocoTestReport)
    violationRules {
        rule {
            element = "BUNDLE"
            limit {
                counter = "LINE"
                value = "COVEREDRATIO"
                minimum = "0.50".toBigDecimal()
            }
        }
    }
}

tasks.check {
    dependsOn("spotlessCheck", "jacocoTestCoverageVerification")
}
```

Các đoạn Kotlin DSL chỉ minh họa phần **khác biệt cú pháp**; để có build hoàn chỉnh cần ghép với `group`, `version`, `java.toolchain`, repositories và dependency như ví dụ Groovy. Không áp dụng đồng thời hai ngôn ngữ DSL vào cùng một project.

## 8. Cấu hình rule và ngưỡng: đừng chỉ cài plugin

### 8.1. Format rule

Formatter nên được **khóa version** và chạy theo cùng quy tắc ở IDE, CLI và CI. Nếu nhóm dùng Google Java Format, kiểm tra plugin version và Google Java Format version được khai báo. Khi thay formatter version, một loạt file có thể phải đổi định dạng; nên tạo commit format riêng để tránh che mất thay đổi logic.

- `check`: chỉ phát hiện sai định dạng, fail build khi cần.
- `apply`: thay đổi file thực tế; chạy tại máy phát triển rồi review `git diff` và commit.
- Đừng biến CI thành nơi âm thầm sửa code rồi báo thành công; như vậy Git history không khớp source đã kiểm.

### 8.2. PMD, Checkstyle và SpotBugs khác nhau

**PMD** phân tích mã nguồn theo rule set; có thể phát hiện dấu hiệu lỗi logic, vấn đề maintainability hoặc coding practice. Ví dụ rule category `java/errorprone` chỉ là điểm bắt đầu; tùy PMD version, quy tắc cụ thể có thể thay đổi. Một phân tích tĩnh hữu ích cần chọn bộ rule phù hợp Java release và kiến trúc team, tránh bật hàng trăm rule gây false positive mà không có kế hoạch.

**Checkstyle** mạnh trong việc enforce quy tắc Java style, import, naming, kích thước method… Nó không thay thế tất cả semantic analysis của PMD. Có thể dùng Checkstyle **thay hoặc bổ sung** PMD khi style rule là yêu cầu bắt buộc.

**SpotBugs** phân tích bytecode và tìm một số bug pattern sau compile (ví dụ misuse API, nullness patterns); đây là loại phân tích khác PMD. Có thể thêm vào bản build nâng cao nhưng phải bảo đảm đúng plugin version, task/goal và chính sách severity.

**Ví dụ thay PMD bằng Checkstyle trong Gradle:**

```groovy
plugins {
    id 'java'
    id 'checkstyle'
}

checkstyle {
    toolVersion = '10.23.0'
    configFile = file('config/checkstyle/checkstyle.xml')
    ignoreFailures = false
}
```

Đây là **snippet thay thế, không phải toàn bộ build**. Bạn phải cung cấp file `config/checkstyle/checkstyle.xml` hợp lệ; nếu thiếu, plugin có thể fail do thiếu cấu hình chứ không phải vì vi phạm mã. Gradle Java + Checkstyle plugin tự gắn task `checkstyleMain`/`checkstyleTest` vào `check`.

Ví dụ cấu hình tối thiểu hợp lệ cho Checkstyle (file `config/checkstyle/checkstyle.xml`):

```xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>
    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
    </module>
</module>
```

Ví dụ trên chỉ kiểm tra wildcard import (không phải toàn bộ rule chuẩn của công ty), giúp hiểu cơ chế cấu hình. Khi dùng PMD và Spotless cùng lúc, nên tránh các rule có ý nghĩa trùng lặp nhưng khác tiêu chuẩn gây mâu thuẫn.

**Maven Checkstyle** có goal `checkstyle:check` để fail trên violation; goal `checkstyle:checkstyle` chủ yếu sinh báo cáo cho Maven site và không được nhầm với quality gate. Một cấu hình bind thay thế có dạng:

```xml
<!-- Đoạn trong <build><plugins> của pom.xml, thay/đệm PMD theo chính sách -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.6.0</version>
    <configuration>
        <configLocation>config/checkstyle/checkstyle.xml</configLocation>
        <failOnViolation>true</failOnViolation>
    </configuration>
    <executions>
        <execution>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>
```

Nếu dùng Checkstyle/PMD cho multi-module, phải xác định config/ruleset ở parent/root ra sao để các module có file rule ổn định. Một module không có Java source có thể cần skip task phù hợp; không tắt toàn bộ quality gate chỉ để xử lý ngoại lệ nhỏ.

### 8.3. Coverage ratio nên hiểu thế nào?

JaCoCo có nhiều **counter** và **value**. Các nhóm thường dùng:

| Counter | Diễn giải |
|---|---|
| `INSTRUCTION` | Bytecode instructions được thực thi |
| `LINE` | Dòng có bytecode có thực thi hay không |
| `BRANCH` | Các nhánh điều khiển như điều kiện `if`/`switch` (không đồng nhất số test case) |
| `METHOD` | Method được gọi |
| `CLASS` | Class có code được thực thi |

Các value như `COVEREDRATIO`, `MISSEDRATIO`, `COVEREDCOUNT`, `MISSEDCOUNT` có ngữ nghĩa khác nhau. Ví dụ:

\`LINE COVEREDRATIO = 0.80\` nghĩa là độ bao phủ dòng **80%** theo cách JaCoCo đếm dòng có bytecode trong phạm vi rule. Không có nghĩa 80% các luồng nghiệp vụ được kiểm thử. Một test chỉ thực thi code mà không assert điều gì vẫn có thể tăng coverage mà không đảm bảo chất lượng.

Ngưỡng là **chính sách**, không phải tính năng đo tự có. Ví dụ rule `minimum = 0.50` cần được chọn có chủ đích cho từng loại module; có thể nâng dần 60% → 75% → 85% khi test suite phát triển, nhưng tránh đặt ngưỡng tùy tiện khiến team viết test vô nghĩa chỉ để đạt số.

**Ví dụ về số học**: nếu JaCoCo tính 80 dòng có bytecode và test bao phủ 64 dòng thì ratio là `64 / 80 = 0.80`. Nếu gate yêu cầu `0.85`, build phải fail; nếu gate `0.75`, build pass. Đây là ví dụ số học, không phải output đo từ các file `DiscountCalculator` ở trên.

### 8.4. Exclusion có trách nhiệm

Đôi khi cần loại khỏi coverage các class được generate, DTO, bootstrap class hoặc code do framework tạo. Đừng loại chỉ để “nâng điểm”. Mỗi exclusion cần được giải thích, review và giữ ổn định giữa report và check.

**Cảnh báo:** cấu hình exclude cho **report** nhưng không exclude cho **verification** (hoặc ngược lại) có thể làm số hiển thị và số áp ngưỡng khác nhau. Trong multi-module, JaCoCo mặc định tính theo module/source set; nếu muốn ngưỡng toàn repo, cần hợp nhất dữ liệu và định nghĩa aggregation rõ.

## 9. Thực nghiệm: chứng minh ba gate thực sự chặn build

Sau khi tạo file Java/test và chọn một build tool:

### 9.1. Bước chuẩn hóa định dạng

Maven:

```bash
./mvnw spotless:apply
./mvnw clean verify
```

Gradle:

```bash
./gradlew spotlessApply
./gradlew clean check
```

**Mong đợi:** nếu code được format đúng, các rule phân tích phù hợp và coverage đạt ngưỡng, lệnh verify/check kết thúc thành công. Sẽ không có stdout cố định vì Maven/Gradle/plugin versions tạo log khác nhau.

### 9.2. Gây lỗi format an toàn

Đổi cách căn dòng/space trong file `DiscountCalculator.java` sao cho formatter sẽ sửa nó, nhưng vẫn là source Java hợp lệ. Sau đó **không** chạy apply; gọi lại `./mvnw verify` hoặc `./gradlew check`. Khi plugin format check đã nối đúng, build phải fail. Sau đó chạy apply và kiểm tra diff.

Nếu sửa file sao cho parser không đọc được Java, nhiều task có thể fail ngay tại compiler trước khi format check; muốn test **riêng gate format**, có thể chạy `spotless:check` hoặc `spotlessCheck`.

### 9.3. Gây lỗi phân tích tĩnh

Tạo một vi phạm rule đã bật (ví dụ một wildcard import khi dùng Checkstyle rule `AvoidStarImport` ở trên) và chạy goal/task static analysis riêng. Xác nhận báo cáo chỉ ra file, dòng và rule. Sau đó sửa mã và chạy lại.

**Không hứa** mọi mẫu code “xấu” sẽ bị PMD bắt: chỉ có quy tắc đã bật, ở version đang dùng, mới quyết định có violation hay không. Để test PMD một cách có kiểm soát, chọn một rule cụ thể trong `category/java/errorprone.xml` và xây input vi phạm đúng rule đó.

### 9.4. Chứng minh ngưỡng coverage

Tạm thời tăng `minimum` lên một mức cao hơn coverage thực đo (ví dụ từ 0.50 lên 0.99 cho build có class bootstrap chưa được test) rồi chạy lệnh verify/check.

- Maven: JaCoCo `check` trả lỗi vì không đạt ngưỡng.
- Gradle: `jacocoTestCoverageVerification` trả lỗi, kéo `check` fail vì `dependsOn` đã khai báo.

Đây là **thử nghiệm có chủ đích**; sau thử nghiệm, khôi phục ngưỡng chính sách phù hợp, không commit số 0.99 chỉ để chứng minh gate. Nếu không thấy lỗi, xem file execution data, rule scope, skip flag và việc task có thật sự được chạy hay không.

## 10. Báo cáo, exit code và tích hợp CI

### 10.1. Báo cáo tạo ở đâu?

| Công cụ | Vị trí thường gặp | Nội dung |
|---|---|---|
| Maven Surefire | `target/surefire-reports/` | XML/text về unit test |
| Gradle Test | `build/test-results/test/`, `build/reports/tests/test/` | XML/HTML kết quả test |
| Maven JaCoCo | `target/site/jacoco/index.html`, `jacoco.xml` | HTML/XML coverage |
| Gradle JaCoCo | `build/reports/jacoco/test/html/index.html`, `build/reports/jacoco/test/jacocoTestReport.xml` | HTML/XML coverage |
| Maven PMD | `target/pmd.xml` / các report trong `target/site/` (tùy goal/config) | Vi phạm PMD |
| Gradle PMD | `build/reports/pmd/` | Report theo source set |
| Gradle Checkstyle | `build/reports/checkstyle/` | Report Checkstyle |
| Spotless | Log/diff do plugin cung cấp | File nào không theo formatter |

Đường dẫn có thể khác nếu plugin hoặc multi-module thay đổi output directory. XML coverage phục vụ công cụ tổng hợp/CI; HTML giúp developer xem những dòng đã được test chạm tới. **XML report không thay thế rule fail build.**

### 10.2. Một CI job phải làm gì?

Một pipeline đúng nên:

1. Checkout đúng source commit.
2. Thiết lập JDK và Maven/Gradle Wrapper phù hợp.
3. Dùng cache dependency có kiểm soát để cải thiện thời gian, nhưng không dùng cache để thay thế bước test/quality gate.
4. Chạy **`./mvnw -B verify`** hoặc **`./gradlew --no-daemon check`** (và build/package nếu pipeline cần artifact).
5. Xem **exit code** của lệnh. Nếu khác 0, job thất bại và PR không qua gate theo branch protection.
6. Lưu test/PMD/Checkstyle/JaCoCo reports như artifacts, kể cả khi job fail nếu nền tảng CI cho phép.
7. Không chạy formatter apply tự động rồi báo source đã đúng; thay đổi format phải được commit và review.

Ví dụ shell cho Maven:

```bash
./mvnw -B clean verify
```

Ví dụ shell cho Gradle:

```bash
./gradlew --no-daemon clean check
```

`--no-daemon` có thể phù hợp với CI ephemeral nhưng không phải yêu cầu kỹ thuật bắt buộc cho mọi Gradle runner. Với Spring Boot packaging trong CI dùng Gradle, `./gradlew build` thường bao gồm `check` thông qua Java lifecycle; nhưng cần xác nhận task graph của project và task/branch protection thực tế.

**Quan trọng về report khi fail:** Nếu formatting check fail trước khi test chạy, JaCoCo không thể có report mới. Nếu test fail, coverage data/report có thể tồn tại nhưng lifecycle có thể không đến bước JaCoCo check. Để thu thập tất cả lỗi trong một lượt, tổ chức có thể chạy kiểm tra độc lập thành các CI jobs riêng hoặc dùng cơ chế finalizer của Gradle khi phù hợp, thay vì mặc định một lệnh sẽ tạo mọi báo cáo bất chấp lỗi.

## 11. Multi-module: gate ở đâu và tính coverage thế nào?

### 11.1. Maven reactor

Ở multi-module Maven:

- Parent POM có thể khai báo plugin version/config trong `<pluginManagement>` để các module dùng thống nhất.
- Nhưng `pluginManagement` **không tự làm plugin goal thực thi ở mọi module**; cần plugin được áp dụng trong `<build><plugins>` ở parent/module phù hợp, chú ý `<inherited>` và packaging.
- Các module `pom` không có mã Java có thể cần skip lint/coverage hoặc chỉ chạy các gate liên quan.
- JaCoCo `report` đơn module không mặc nhiên tạo **một ngưỡng chung toàn reactor**. Với báo cáo hợp nhất có `report-aggregate` và thiết lập dependency/aggregation riêng.

Nếu chỉ chạy `./mvnw -pl :orders-api verify`, các module phụ thuộc có thể cần `-am` và phù hợp reactor setup:

```bash
./mvnw -pl :orders-api -am verify
```

Đừng đặt ngưỡng ứng dụng giống hệt module generated-code hoặc test fixtures mà không xem bản chất module. Xác định rõ gate tối thiểu và ngoại lệ module có lý do.

### 11.2. Gradle multi-project

Trong Gradle, `check` là task **theo project**:

```bash
./gradlew :orders-api:check
./gradlew :shared-domain:check
```

Một build nhiều module có thể gọi `./gradlew check` để chọn task tên `check` trong cấu trúc project, nhưng không nên giả định mọi custom verification task ở tất cả module đã được nối. Dùng `./gradlew tasks --all` và `./gradlew :module:check --dry-run` để kiểm tra những task sẽ được thực thi.

- Áp dụng `pmd`, `jacoco`, `spotless` cho đúng module/source set.
- Gói quy ước chung trong **convention plugin** để tránh module nào quên `dependsOn`.
- Mỗi module thường có báo cáo JaCoCo riêng. Nếu muốn coverage toàn bộ ứng dụng từ test xuyên module, cần JaCoCo report aggregation/thiết lập execution data phù hợp; việc cộng phần trăm trung bình đơn giản giữa module không đúng khi số dòng khác nhau.
- Không bật plugin Spring Boot executable cho mọi module thư viện chỉ để có quality gate. Các plugin quality có thể đi cùng `java-library` ở module không phải Boot app.

## 12. Các lỗi phổ biến và hướng chẩn đoán

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
|---|---|---|
| `./mvnw verify` PASS dù file sai format | Chỉ cài Spotless mà chưa bind `check`, hoặc skip flag đang bật | Kiểm tra `<executions>`, `<phase>verify</phase>` và log goal |
| `./gradlew check` PASS dù coverage 0% | `jacocoTestCoverageVerification` chưa là dependency của `check` | Thêm `check.dependsOn` verification, kiểm tra `--dry-run` |
| Có HTML coverage nhưng gate không fail | Chỉ chạy `report` mà không cấu hình `check`/`violationRules` | Thêm rule và nối vào verify/check |
| JaCoCo báo missing execution data | Agent chưa gắn vào test JVM, test bị skip, test task không chạy hoặc output khác | Xem `prepare-agent`/`Test` instrumentation, report paths và skip flags |
| JaCoCo coverage sai khi dùng nhiều module/test suite | Chỉ đo `test` của một module thay vì tất cả test | Tạo report aggregation và rule scope đúng |
| PMD/checkstyle chỉ sinh cảnh báo | `ignoreFailures`/`failOnViolation`/violation policy bỏ qua lỗi | Đặt chính sách fail rõ, thử vi phạm mẫu |
| CI tự sửa format rồi vẫn PASS | Dùng `spotlessApply`/`spotless:apply` thay check | CI chỉ chạy check; developer tự apply + review |
| Maven JaCoCo thiếu agent sau khi thêm VM options | `argLine` của Surefire bị ghi đè | Kết hợp tham số agent với custom VM options đúng theo plugin docs |
| Build fail do thiếu Checkstyle config | File `checkstyle.xml` chưa commit hoặc đường dẫn sai | Commit file rule và tham chiếu đường dẫn đúng |
| Spotless formatter khác giữa IDE và CI | Chưa cố định formatter/plugin version hoặc line endings | Pin version, cấu hình Git attributes và đồng bộ IDE |
| `./gradlew bootJar` thành công nhưng kiểm tra tĩnh chưa chạy | `bootJar` không bắt buộc phụ thuộc vào `check` | Gọi `check`/`build` trong CI |
| PMD false positive trên mã sinh tự động | Rule set quét generated sources hoặc cấu hình exclude chưa đúng | Giới hạn input hợp lý; review exclusion |
| Test PASS nhưng chất lượng logic chưa bảo đảm | Coverage chỉ đo execution, không đo chất lượng assertion | Review test case, thêm branch/behavior testing, có thể mutation test |

Chạy lệnh chẩn đoán **chỉ trên công cụ mà project đang dùng**:

```bash
# Maven: xem cấu hình hiệu lực và các goal khi chạy
./mvnw help:effective-pom
./mvnw -X verify

# Gradle: xem task graph và lý do task chạy/bỏ qua
./gradlew check --dry-run
./gradlew check --info
```

Log debug có thể chứa biến môi trường hoặc chi tiết hệ thống; chỉ chia sẻ sau khi xem xét dữ liệu nhạy cảm.

## 13. Gợi ý chính sách quality gate thực tế

**Định dạng** nên là điều kiện nhị phân: đã format đúng hay chưa. Rule phải có command apply rõ ràng để developer sửa nhanh. Nếu team chọn Spotless, thống nhất formatter/version, không trộn nhiều formatter Java cho cùng file.

**Phân tích tĩnh** nên có mức lỗi ưu tiên, danh sách rule được review và cơ chế suppress có lý do, thay vì bật `ignoreFailures` hàng loạt. Một số rule có thể chạy trong PR, một số phân tích bytecode nặng hơn có thể chạy theo lịch — nhưng điều kiện bắt buộc cho merge phải được ghi cụ thể.

**Coverage** cần ít nhất một ngưỡng thực tế và report được lưu. Bắt đầu với baseline hiện có, xây mục tiêu tăng dần, chú trọng code rủi ro cao, branch coverage và test behavior. Các lớp bootstrap, DTO, generated code chỉ nên loại ra khi có chính sách rõ; đừng đánh đồng “đạt 90%” với “không còn bug”.

**Hiệu năng**: có thể dùng Gradle incremental/up-to-date, Maven plugin caching, chia task theo module/CI job. Nhưng không hy sinh tính chính xác của gate để tiết kiệm vài giây; build cache được phép tái sử dụng kết quả hợp lệ, không được khiến việc check bị bỏ qua vô điều kiện.

**Bảo trì**: định kỳ cập nhật plugin/JDK/ruleset một cách có kiểm soát, review report false positives, kiểm tra lại CI branch protection và chạy thí nghiệm gây lỗi để chứng minh gate vẫn hoạt động.

## 14. Checklist trước khi triển khai vào CI

1. **Format**: `spotlessCheck` hoặc `spotless:check` chạy tự động trong `check`/`verify`; `apply` chỉ chạy thủ công.
2. **Static analysis**: PMD/Checkstyle/SpotBugs được chọn có version, rule set, phạm vi source và chế độ fail rõ ràng.
3. **Coverage agent**: test được instrument đúng; file execution data được tạo trong lần CI build.
4. **Coverage report**: HTML/XML được tạo và lưu khi có dữ liệu; đường dẫn báo cáo đúng theo module.
5. **Coverage gate**: JaCoCo `check`/`jacocoTestCoverageVerification` áp ngưỡng thật sự, không chỉ sinh báo cáo.
6. **Lifecycle/task graph**: Maven goal bind đúng `verify`; Gradle dependency `check` chứa các task cần thiết; xác nhận bằng log hoặc dry-run.
7. **JUnit**: Maven Surefire/Gradle `test` tìm được và chạy đúng test framework; không bật skip flags trong job bắt buộc.
8. **Packaging**: nếu cần phát hành JAR, chạy `package`/`build` phù hợp **sau hoặc cùng với** gate; không nhầm `bootJar` với toàn bộ kiểm tra.
9. **Multi-module**: mỗi module có gate đúng vai trò; coverage aggregate nếu yêu cầu đã được cấu hình rõ.
10. **Bảo mật CI**: token/repository credentials đặt trong secrets, không commit vào build config và không đưa vào log.
11. **Thử nghiệm lỗi**: chủ động tạo một vi phạm format, một violation static analysis, một coverage threshold vượt mức rồi xác nhận lệnh chính trả mã lỗi.
12. **Báo cáo**: CI lưu report giúp người sửa xác định file/line/rule cần khắc phục; restore threshold và source sau thí nghiệm.

### Tài liệu chính thức

- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Spotless Maven Plugin — check và lifecycle binding](https://github.com/diffplug/spotless/blob/main/plugin-maven/README.md)
- [Spotless Gradle Plugin — task spotlessCheck/spotlessApply](https://github.com/diffplug/spotless/blob/main/plugin-gradle/README.md)
- [Maven PMD Plugin — tích hợp vào verify](https://pmd.github.io/pmd/pmd_userdocs_tools_maven.html)
- [Gradle PMD Plugin](https://docs.gradle.org/current/userguide/pmd_plugin.html)
- [Gradle Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html)
- [Gradle JaCoCo Plugin — verification không tự phụ thuộc check](https://docs.gradle.org/current/userguide/jacoco_plugin.html)
- [JaCoCo Maven — check goal](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [JaCoCo Maven — report goal](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)

**Ghi nhớ:** Chất lượng chỉ trở thành **quality gate** khi format check, static analysis và coverage verification được gắn vào **`mvn verify` hoặc `gradle check`**, có rule rõ ràng và thực sự làm lệnh trả lỗi khi vi phạm. Báo cáo đẹp nhưng không fail build **không phải** cổng kiểm soát chất lượng.
