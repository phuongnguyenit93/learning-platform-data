# Cơ chế phát hiện, chọn lọc và báo cáo kết quả kiểm thử

Trong một dự án Java, build tool không chỉ biên dịch mã nguồn. Nó còn phải xác định những lớp nào là lớp kiểm thử, tìm các test case do framework cung cấp, quyết định test nào cần chạy và ghi lại kết quả để lập trình viên hoặc hệ thống CI có thể đọc được.

Ba cơ chế liên quan chặt chẽ với nhau nhưng giải quyết những việc khác nhau:

- **Phát hiện (discovery):** tìm các lớp và phương thức kiểm thử mà framework có thể thực thi.
- **Chọn lọc (selection/filtering):** giới hạn tập test đã phát hiện theo tên lớp, tên phương thức, tag, group hoặc điều kiện cấu hình.
- **Báo cáo (reporting):** ghi lại test đã chạy, thành công, thất bại, bị bỏ qua và thông tin lỗi.

```text
Mã nguồn kiểm thử
       |
       v
Biên dịch test classes
       |
       v
Phát hiện test bằng framework/engine
       |
       v
Áp dụng bộ lọc và lựa chọn test
       |
       v
Thực thi test
       |
       +--------------------+
       |                    |
       v                    v
Kết quả từng test      Log / exception
       |                    |
       +---------+----------+
                 |
                 v
          Báo cáo test
          HTML / XML / log
```

Nếu một test không xuất hiện trong báo cáo, nguyên nhân có thể nằm ở bước biên dịch, phát hiện, chọn lọc hoặc cấu hình framework. Nếu một test xuất hiện với trạng thái skipped, đó là một tình huống khác với test chưa được phát hiện. Phân biệt đúng các bước giúp tìm nguyên nhân nhanh hơn.

## 1. Một test đi từ mã nguồn đến báo cáo như thế nào?

Giả sử dự án có lớp kiểm thử:

```java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Build tool và test framework phối hợp để xử lý lớp này qua nhiều giai đoạn:

1. Compiler biên dịch `CalculatorTest.java` thành `CalculatorTest.class` trong thư mục output của test source set.
2. Test task hoặc Maven Surefire khởi tạo bộ chạy kiểm thử phù hợp.
3. Framework/engine nhận diện annotation `@Test` và tạo test descriptor tương ứng.
4. Bộ lọc của build tool hoặc framework quyết định test nào được đưa vào lần chạy hiện tại.
5. Test runner thực thi từng test, thu thập kết quả và exception.
6. Build tool ghi báo cáo, log và trạng thái của task/lifecycle.

Một test chỉ có thể chạy nếu những thành phần cần thiết đều có mặt. Chẳng hạn, lớp có thể biên dịch thành công nhưng không được phát hiện nếu test engine không có trên runtime test classpath hoặc build tool chưa được cấu hình để sử dụng engine đó.

### Phân biệt các trạng thái

| Trạng thái | Ý nghĩa |
|---|---|
| Passed | Test đã được thực thi và mọi assertion đều thành công. |
| Failed | Test đã được thực thi nhưng assertion hoặc thao tác trong test gây lỗi. |
| Skipped | Test được framework ghi nhận nhưng không được thực thi, ví dụ do điều kiện hoặc annotation bỏ qua. |
| Aborted | Framework kết thúc test sớm theo cơ chế abort/assumption; cách hiển thị tùy framework và báo cáo. |
| Filtered out | Test không được chọn bởi bộ lọc của lần chạy hiện tại. Nó thường không được tính như một test đã chạy. |
| Not discovered | Framework không nhận diện test đó trong lần quét hiện tại. |
| Not compiled | Không có test class mới tương ứng trong output do lỗi biên dịch hoặc source set không được biên dịch. |

Các báo cáo không phải lúc nào cũng dùng đúng những nhãn trên. Ví dụ, một số framework hiển thị skipped hoặc aborted theo cách riêng. Hãy đọc cả log và báo cáo của test runner.

## 2. Điều kiện để test được phát hiện

Phát hiện test không đơn giản là tìm mọi lớp có tên kết thúc bằng `Test`. Build tool phải biết framework nào được sử dụng và framework đó định nghĩa một test case như thế nào.

Các điều kiện thường gặp gồm:

- Tệp kiểm thử nằm trong source set/thư mục test mà build tool đang xử lý.
- Tệp biên dịch thành công và class output có mặt.
- Test framework API và engine/provider tương ứng nằm trên test runtime classpath.
- Lớp, phương thức và constructor đáp ứng quy tắc của framework.
- Tác vụ kiểm thử không bị tắt hoặc bỏ qua bởi cấu hình build.
- Không có bộ lọc nào loại test ra khỏi lần chạy hiện tại.

### JUnit 5 và JUnit Platform

JUnit 5 sử dụng JUnit Platform làm nền tảng chạy test. Các module chính thường được nhắc đến là:

- **JUnit Jupiter:** API và programming model cho test viết theo JUnit 5.
- **JUnit Platform:** nền tảng test engine và launcher.
- **JUnit Vintage:** engine tương thích để chạy một số test JUnit 3/4 trên JUnit Platform.

Một test JUnit Jupiter thường dùng `org.junit.jupiter.api.Test`. Nếu chỉ có API nhưng thiếu engine phù hợp, test có thể biên dịch được nhưng không được thực thi như mong đợi.

Ví dụ dependency cho Gradle:

```groovy
dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.test {
    useJUnitPlatform()
}
```

JUnit BOM giúp các module JUnit dùng cùng một dòng version. `useJUnitPlatform()` cấu hình Gradle Test để chạy qua JUnit Platform. Với phiên bản Gradle mới, launcher được khai báo tường minh trong test runtime dependencies giúp thiết lập nền tảng chạy test rõ ràng.

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.10.2</version>
    <scope>test</scope>
</dependency>
```

Để Maven chạy JUnit 5, cần phiên bản Maven Surefire có hỗ trợ JUnit Platform. Trong dự án thực tế, nên khai báo phiên bản plugin tường minh thay vì phụ thuộc phiên bản mặc định cũ của Maven.

### JUnit 4

JUnit 4 sử dụng annotation `org.junit.Test`. Ví dụ:

```java
import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class LegacyCalculatorTest {
    @Test
    public void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Nếu dự án dùng JUnit 4, hãy bảo đảm dependency và test runner tương ứng có mặt. Nếu dự án dùng JUnit Platform để chạy test JUnit 4, cần thêm JUnit Vintage Engine. Không nên giả định một cấu hình JUnit 5 tự động chạy được mọi test JUnit 4 cũ.

### TestNG

TestNG có annotation `org.testng.annotations.Test` và cơ chế group riêng. Ví dụ:

```java
import org.testng.annotations.Test;

public class AccountTest {
    @Test(groups = {"fast"})
    public void validatesAccount() {
        // Test logic
    }
}
```

Build tool phải được cấu hình để sử dụng TestNG provider/engine và có dependency TestNG trên test runtime classpath. Các tùy chọn group của TestNG khác với tag của JUnit Jupiter, dù chúng có mục đích chọn lọc tương tự.

## 3. Phát hiện test trong Gradle

Gradle Java plugin tạo source set `test` với thư mục mặc định `src/test/java` và `src/test/resources`. Test source được biên dịch riêng với mã nguồn ứng dụng.

Cấu trúc phổ biến:

```text
src/
├── main/
│   ├── java/
│   └── resources/
└── test/
    ├── java/
    └── resources/
```

Các lớp test đã biên dịch thường nằm trong `build/classes/java/test/`. Tài nguyên test được xử lý vào `build/resources/test/`.

Task `test` thuộc loại `Test` và sử dụng test framework được cấu hình. Với JUnit Platform, cấu hình thường là:

```groovy
tasks.test {
    useJUnitPlatform()
}
```

Nếu không cấu hình đúng framework, test class có thể tồn tại trong thư mục output nhưng runner không hiểu annotation hoặc không tìm thấy engine.

### Source set và task test riêng

Ngoài source set `test`, dự án có thể tạo source set khác như `integrationTest`, `functionalTest` hoặc `acceptanceTest`. Mỗi source set có thể có task biên dịch và task test riêng.

Ví dụ, dự án có thể tạo `integrationTest` task dựa trên một source set tùy chỉnh. Khi đó, báo cáo và kết quả thường nằm trong thư mục có tên task tương ứng, ví dụ `build/reports/tests/integrationTest/` và `build/test-results/integrationTest/`.

Không nên mặc định mọi test đều được chạy bởi task `test`. Hãy xem task graph và source set để biết task nào thực hiện nhóm test nào.

## 4. Chọn lọc test trong Gradle bằng tên lớp và phương thức

Gradle hỗ trợ lọc test bằng option `--tests`. Ví dụ:

Chạy toàn bộ test trong một lớp:

```shell
./gradlew test --tests 'com.example.CalculatorTest'
```

Chạy một phương thức cụ thể:

```shell
./gradlew test --tests 'com.example.CalculatorTest.addsTwoNumbers'
```

Chạy các lớp khớp mẫu:

```shell
./gradlew test --tests '*RepositoryTest'
```

Có thể chỉ định nhiều mẫu:

```shell
./gradlew test \
  --tests 'com.example.service.*Test' \
  --tests 'com.example.repository.UserRepositoryTest'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests 'com.example.CalculatorTest'
```

`--tests` lọc các test theo tên lớp hoặc tên test mà Gradle nhận diện. Wildcard có thể hữu ích khi muốn chạy một nhóm lớp. Tên phương thức có thể khác cách viết trong báo cáo nếu framework hiển thị tên test đã tham số hóa hoặc tên được tùy chỉnh.

### Lọc trong build script

Bạn có thể đặt bộ lọc cố định trong cấu hình task:

```groovy
tasks.test {
    filter {
        includeTestsMatching 'com.example.unit.*'
        excludeTestsMatching 'com.example.unit.slow.*'
    }
}
```

Các pattern ở đây được áp dụng cho test task. Nếu có nhiều test task, cấu hình một task không tự động áp dụng cho mọi task khác. Hãy đặt cấu hình ở convention plugin hoặc cấu hình dùng chung nếu nhiều task cần cùng chính sách.

Khi cần chạy toàn bộ test, hãy xem lại filter trong build script và các tham số được truyền từ CI. Một filter cũ có thể khiến test mới không được chọn dù nó đã biên dịch và được phát hiện.

## 5. Chọn lọc test theo tag trong JUnit 5

JUnit Jupiter cho phép gắn tag vào test hoặc lớp kiểm thử:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

class PaymentServiceTest {
    @Test
    @Tag("fast")
    void calculatesFee() {
        // Test logic
    }

    @Test
    @Tag("integration")
    void savesPaymentToDatabase() {
        // Test logic
    }
}
```

Tag mô tả nhóm test theo mục đích, ví dụ `fast`, `integration`, `slow`, `database` hoặc `smoke`. Một test có thể mang nhiều tag.

Gradle cấu hình tag qua JUnit Platform:

```groovy
tasks.test {
    useJUnitPlatform {
        includeTags 'fast'
        excludeTags 'slow'
    }
}
```

Với cấu hình trên, task chỉ chọn test có tag được include và không bị loại bởi tag exclude. Nếu include và exclude không được khai báo, JUnit Platform chạy theo mặc định của engine và các filter khác.

Không nhầm tag filter với `--tests`: `--tests` lọc theo tên test/class mà Gradle nhận diện; `includeTags` và `excludeTags` lọc theo metadata của JUnit Platform.

### Chọn test theo tag ở các môi trường khác nhau

Một dự án có thể tổ chức các task riêng:

```groovy
tasks.register('fastTest', Test) {
    group = 'verification'
    description = 'Chạy test mang tag fast.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'fast'
    }
}

tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Chạy test mang tag integration.'
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'integration'
    }
}
```

Đây là ví dụ dùng chung source set để minh họa lựa chọn tag. Với dự án lớn, integration test thường có source set, runtime classpath và dependency riêng để tránh đưa thư viện test tích hợp vào unit test.

Chạy riêng:

```shell
./gradlew fastTest
./gradlew integrationTest
```

Task riêng giúp CI chạy nhanh unit test ở mỗi thay đổi và chỉ chạy integration test ở giai đoạn phù hợp. Cần bảo đảm các task không ghi đè cùng thư mục kết quả và report.

## 6. Chọn lọc test trong Maven Surefire

Maven Surefire Plugin chạy unit test trong phase `test` của lifecycle mặc định. Plugin có các quy tắc include/exclude để xác định lớp test.

Các tên lớp phổ biến được Surefire nhận diện theo mặc định gồm:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

Ví dụ các lớp sau thường khớp quy ước:

```text
TestCalculator.java
CalculatorTest.java
CalculatorTests.java
CalculatorTestCase.java
```

Một lớp tên `CalculatorCheck.java` có thể không được chọn theo các pattern mặc định, dù bên trong có method gắn annotation test. Nếu muốn dùng quy ước tên khác, cần cấu hình include phù hợp.

### Chạy một lớp cụ thể

```shell
mvn -Dtest=CalculatorTest test
```

Chạy một phương thức cụ thể với các phiên bản Surefire hỗ trợ cú pháp này:

```shell
mvn -Dtest=CalculatorTest#addsTwoNumbers test
```

Chạy nhiều lớp bằng pattern:

```shell
mvn -Dtest='*RepositoryTest,CalculatorTest' test
```

Trên Windows PowerShell, cũng có thể truyền pattern trong dấu nháy đơn:

```powershell
mvn '-Dtest=*RepositoryTest,CalculatorTest' test
```

Pattern và khả năng chọn method phụ thuộc phiên bản Surefire và test provider. Nếu một lệnh chọn method không hoạt động, kiểm tra phiên bản plugin và cú pháp mà provider đang dùng hỗ trợ.

### Cấu hình include/exclude trong `pom.xml`

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.2.5</version>
            <configuration>
                <includes>
                    <include>**/*Test.java</include>
                    <include>**/*Spec.java</include>
                </includes>
                <excludes>
                    <exclude>**/*SlowTest.java</exclude>
                </excludes>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Ví dụ trên bổ sung quy ước chọn lớp có hậu tố `Spec` và loại các lớp có hậu tố `SlowTest`. Hãy điều chỉnh pattern theo cách tổ chức test của project. Khi thay đổi includes, nhớ rằng cấu hình include có thể thay thế hoặc mở rộng cách chọn mặc định tùy cách khai báo; hãy chạy thử và đọc báo cáo để xác nhận số test được chọn.

### Chọn test theo JUnit 5 tags hoặc TestNG groups

Surefire hỗ trợ lọc theo nhóm/tag thông qua các thuộc tính như `groups` và `excludedGroups` với provider tương ứng. Ví dụ chọn tag JUnit 5:

```shell
mvn -Dgroups=fast test
```

Loại tag:

```shell
mvn -Dgroups=fast -DexcludedGroups=slow test
```

Với TestNG, `groups` và `excludedGroups` là group được khai báo trong annotation/configuration TestNG. Với JUnit 5, chúng được ánh xạ vào tag filter thông qua JUnit Platform provider. Cần xác nhận Surefire provider và phiên bản đang dùng hỗ trợ cấu hình này.

## 7. Phân biệt unit test và integration test trong Maven

Maven thường dùng hai plugin khác nhau cho hai nhóm test:

- **Surefire:** chạy unit test trong phase `test`.
- **Failsafe:** chạy integration test trong các phase `integration-test` và `verify`.

Failsafe thường sử dụng quy ước tên như:

```text
**/IT*.java
**/*IT.java
**/*ITCase.java
```

Ví dụ:

```text
UserServiceIT.java
ITDatabaseMigration.java
PaymentGatewayITCase.java
```

Một cấu hình Failsafe cơ bản:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.2.5</version>
            <executions>
                <execution>
                    <goals>
                        <goal>integration-test</goal>
                        <goal>verify</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Chạy integration test theo lifecycle:

```shell
mvn verify
```

Failsafe tách việc thực thi integration test khỏi bước xác minh kết quả để các phase sau có cơ hội dọn dẹp tài nguyên trước khi build được đánh dấu thất bại ở `verify`. Điều này hữu ích khi test đã khởi động server hoặc container cần được dừng sau khi test kết thúc.

Nếu chỉ chạy `mvn test`, các goal Failsafe gắn với `integration-test` và `verify` chưa được thực hiện. Vì vậy, đừng kết luận integration test đã chạy chỉ dựa trên việc unit test thành công.

## 8. Báo cáo kết quả trong Gradle

Gradle Test task thu thập kết quả và thường tạo báo cáo HTML cùng dữ liệu XML.

Với task `test` mặc định:

```text
build/
├── reports/
│   └── tests/
│       └── test/
│           └── index.html
└── test-results/
    └── test/
        ├── TEST-com.example.CalculatorTest.xml
        └── binary/
```

Mở `build/reports/tests/test/index.html` trong trình duyệt để xem tổng quan, test thành công/thất bại/bị bỏ qua, thời gian chạy và stack trace. Các tệp XML phù hợp để hệ thống CI thu thập và chuyển thành test report.

Với task tên khác, thư mục report và result thường dùng tên task tương ứng, ví dụ `build/reports/tests/integrationTest/`.

### Cấu hình test logging

Gradle cho phép chọn các sự kiện xuất hiện trong log:

```groovy
tasks.test {
    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showCauses true
        showExceptions true
        showStackTraces true
    }
}
```

Các sự kiện `passed`, `skipped` và `failed` giúp biết test đang tạo ra kết quả gì trong Terminal. `exceptionFormat 'full'` hiển thị chi tiết exception hơn khi test thất bại. Có thể điều chỉnh mức chi tiết để log CI không quá dài.

Nếu cần xem `System.out` và `System.err` của test trong log:

```groovy
tasks.test {
    testLogging {
        showStandardStreams = true
    }
}
```

Chỉ nên bật stream khi cần điều tra vì nhiều test in log có thể làm báo cáo CI khó đọc. Thông thường, dùng assertion message và log có chủ đích sẽ hữu ích hơn.

### Kết quả test và trạng thái build

Mặc định, test thất bại khiến task `test` thất bại và có thể làm build dừng ở trạng thái failure. Báo cáo thường vẫn được tạo để bạn xem nguyên nhân.

Có thể cấu hình `ignoreFailures = true` để task tiếp tục build dù test thất bại:

```groovy
tasks.test {
    ignoreFailures = true
}
```

Thiết lập này hữu ích trong một số tình huống thu thập nhiều báo cáo, nhưng cần cẩn trọng trong CI: pipeline có thể hoàn tất thành công ở cấp build dù báo cáo chứa test failed. Nếu sử dụng, cần có bước riêng đọc kết quả và quyết định trạng thái pipeline.

## 9. Báo cáo kết quả trong Maven

Maven Surefire thường ghi báo cáo tại:

```text
target/surefire-reports/
├── TEST-com.example.CalculatorTest.xml
└── com.example.CalculatorTest.txt
```

Tệp XML chứa dữ liệu có cấu trúc như số test, failure, error, skipped, thời gian và thông tin lỗi. Tệp TXT thường chứa phần log hoặc stack trace thuận tiện để đọc nhanh.

Maven Failsafe thường ghi kết quả tại:

```text
target/failsafe-reports/
```

CI có thể thu thập các tệp XML này để hiển thị test report hợp nhất. Nếu thư mục báo cáo không tồn tại, hãy xác nhận đúng phase/plugin đã chạy và test có được phát hiện hay không.

### Cấu hình báo cáo và mức độ chi tiết

Surefire có thể cấu hình trong `pom.xml` để điều chỉnh output, ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <printSummary>true</printSummary>
        <trimStackTrace>false</trimStackTrace>
        <redirectTestOutputToFile>true</redirectTestOutputToFile>
    </configuration>
</plugin>
```

`printSummary` yêu cầu hiển thị tổng kết trong log. `trimStackTrace` điều chỉnh việc rút gọn stack trace. `redirectTestOutputToFile` chuyển output của test vào tệp báo cáo riêng thay vì trộn toàn bộ vào console. Các tùy chọn và giá trị mặc định có thể thay đổi theo phiên bản Surefire.

## 10. Chọn test và bỏ qua test không giống nhau

Một trong những nguyên nhân khó hiểu trong CI là build vẫn xanh nhưng một số test không chạy. Có nhiều cơ chế làm điều đó và chúng có ý nghĩa khác nhau.

### Gradle

Chạy một test cụ thể:

```shell
./gradlew test --tests 'com.example.CalculatorTest'
```

Loại toàn bộ task `test` khỏi lần chạy:

```shell
./gradlew build -x test
```

`-x test` loại task `test` khỏi task graph được thực thi. Đây không phải bộ lọc test method; toàn bộ task bị loại.

Trong test code, JUnit 5 có thể bỏ qua một test bằng `@Disabled` hoặc assumption. Test vẫn được framework nhận diện, nhưng kết quả có trạng thái skipped/aborted tùy cơ chế.

### Maven

Chạy một lớp:

```shell
mvn -Dtest=CalculatorTest test
```

Bỏ qua việc chạy test nhưng vẫn biên dịch test source:

```shell
mvn -DskipTests package
```

Bỏ qua cả biên dịch và chạy test:

```shell
mvn -Dmaven.test.skip=true package
```

Hai tùy chọn Maven này khác nhau:

- `skipTests` thường yêu cầu Surefire/Failsafe không thực thi test; test source vẫn có thể được biên dịch.
- `maven.test.skip` yêu cầu bỏ qua cả bước biên dịch test và thực thi test ở các plugin hỗ trợ thuộc tính này.

Trong test code, annotation như JUnit `@Disabled` hoặc TestNG `enabled = false` làm test được framework bỏ qua theo cơ chế của framework. Điều này khác với việc Maven không chọn lớp test ngay từ đầu.

Không dùng tùy chọn bỏ qua test trong pipeline phát hành chỉ để làm build xanh khi có lỗi. Nếu cần build không chạy test cho một mục đích cụ thể, hãy ghi rõ lý do và bảo đảm bước xác minh được thực hiện ở giai đoạn khác.

## 11. Báo cáo không có test: phân biệt nguyên nhân

Nếu build thành công nhưng báo cáo có 0 test hoặc không có báo cáo, hãy lần theo quy trình:

1. **Kiểm tra source path:** tệp có nằm trong `src/test/java` hoặc thư mục test được cấu hình không?
2. **Kiểm tra compile:** test class có được tạo trong output directory không?
3. **Kiểm tra dependency:** test API, engine/provider có trên test runtime classpath không?
4. **Kiểm tra framework:** Gradle đã gọi `useJUnitPlatform()` khi cần chưa? Maven Surefire có phiên bản/provider tương thích chưa?
5. **Kiểm tra quy tắc tên:** lớp có khớp pattern include mặc định hoặc pattern tùy chỉnh không?
6. **Kiểm tra filter:** `--tests`, include/exclude, tag/group hoặc profile có loại test không?
7. **Kiểm tra task/phase:** đúng task `test`, `integrationTest` hoặc Maven phase đã được chạy chưa?
8. **Kiểm tra skip flags:** có `-x test`, `-DskipTests`, `-Dmaven.test.skip` hoặc cấu hình `enabled = false` không?

Một số ví dụ:

| Biểu hiện | Nơi cần kiểm tra trước |
|---|---|
| `CalculatorTest` không được biên dịch | Thư mục source, source set, lỗi compile và task `compileTestJava`. |
| Test class có `.class` nhưng không có test case | Annotation, framework engine/provider và runtime classpath. |
| Chỉ một vài lớp được chạy | `--tests`, include/exclude hoặc quy ước tên Surefire. |
| Test hiện là skipped | `@Disabled`, assumption, điều kiện chạy hoặc cấu hình framework. |
| Unit test chạy nhưng integration test không chạy | Đúng task/phase, source set, Failsafe và quy ước `IT`. |
| Build xanh dù có test failed | Cấu hình bỏ qua lỗi, `ignoreFailures` hoặc pipeline không đọc kết quả XML. |
| Không thấy báo cáo sau build | Task chưa chạy, report bị tắt, task name khác hoặc output directory được tùy chỉnh. |

## 12. Test report trong CI

Hệ thống CI thường cần hai loại thông tin:

- **Trạng thái build:** tiến trình build có thành công hay thất bại.
- **Chi tiết test:** tổng số test, passed, failed, skipped, thời gian và lỗi.

Log console hữu ích khi chạy trực tiếp nhưng khó tổng hợp khi có hàng nghìn test. Báo cáo XML theo định dạng JUnit phổ biến giúp CI đọc kết quả từ nhiều framework và hiển thị trong giao diện pipeline.

Ví dụ các thư mục cần thu thập:

| Build tool | Kết quả XML | Báo cáo HTML |
|---|---|---|
| Gradle `test` | `build/test-results/test/` | `build/reports/tests/test/` |
| Maven Surefire | `target/surefire-reports/` | Có thể được tạo bởi plugin báo cáo riêng; Surefire mặc định tập trung vào report files. |
| Maven Failsafe | `target/failsafe-reports/` | Có thể được tạo bởi plugin báo cáo riêng. |

Trong CI, hãy cấu hình artifact/report collection để lấy đúng thư mục và lưu cả khi test thất bại. Nếu pipeline chỉ tải artifact khi build thành công, nhóm có thể mất báo cáo quan trọng nhất khi có lỗi.

### Vì sao cần lưu báo cáo khi build thất bại?

Một test failed thường là lý do khiến task hoặc pipeline thất bại. Nếu CI chỉ giữ log ngắn mà bỏ XML/HTML, người điều tra phải chạy lại toàn bộ test mới xem được chi tiết. Giữ report giúp:

- Xác định test thất bại và assertion message.
- So sánh số lượng test qua các lần build.
- Nhận diện test chậm hoặc có xu hướng flaky.
- Phân biệt test không được chọn với test đã chạy nhưng bị skip.
- Tạo lịch sử chất lượng theo commit/branch.

Không nên chỉ dựa vào số lượng test để đánh giá chất lượng. Một test có thể được phát hiện nhưng assertion không kiểm tra đúng hành vi; báo cáo là bằng chứng về quá trình thực thi, không chứng minh toàn bộ yêu cầu sản phẩm đã được kiểm thử.

## 13. Chẩn đoán một test failed từ báo cáo

Khi báo cáo hiển thị test thất bại, hãy đọc theo thứ tự:

1. Tên lớp và tên method/test case.
2. Trạng thái và thời gian thực thi.
3. Assertion message hoặc exception đầu tiên.
4. Dòng code trong stack trace thuộc test hoặc code sản phẩm.
5. Input, fixture, mock, tài nguyên hoặc môi trường mà test sử dụng.
6. Log của test nếu có bật output capture.

Ví dụ báo cáo:

```text
CalculatorTest.addsTwoNumbers
Status: FAILED
Expected: 5
Actual:   4
AssertionError at CalculatorTest.java:18
```

Đây là lỗi assertion: test đã được phát hiện và thực thi, nhưng kết quả không khớp mong đợi. Nếu báo cáo ghi `Skipped`, test có thể đã bị bỏ qua do annotation hoặc điều kiện. Nếu test không có trong report, hãy kiểm tra discovery và selection trước khi sửa logic test.

### Phân biệt lỗi test với lỗi khởi tạo test runtime

Một số lỗi xảy ra trước khi method test chạy, ví dụ:

- Không tìm thấy class trên runtime classpath.
- Thiếu test engine hoặc provider.
- Lỗi khởi tạo extension, test listener hoặc test fixture.
- Không khởi động được database/container mà integration test cần.
- Lỗi cấu hình test JVM hoặc biến môi trường.

Các lỗi này có thể được báo cáo dưới dạng test error, suite failure hoặc task failure tùy framework. Hãy kiểm tra log đầy đủ và stack trace để phân biệt lỗi assertion với lỗi môi trường thực thi.

## 14. Test parameterized, nested và dynamic

Không phải mỗi method `@Test` luôn tương ứng với đúng một dòng kết quả. JUnit 5 hỗ trợ parameterized test, nested test và dynamic test.

Parameterized test chạy một test method với nhiều bộ dữ liệu:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class NumberTest {
    @ParameterizedTest
    @ValueSource(ints = {2, 4, 6})
    void numberIsEven(int value) {
        assert value % 2 == 0;
    }
}
```

Một method có thể tạo nhiều test invocation trong báo cáo. Khi chọn theo tên method, hãy nhớ rằng báo cáo có thể hiển thị tên invocation kèm tham số.

Nested test tổ chức test theo lớp lồng nhau:

```java
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class AccountTest {
    @Nested
    class WhenAccountIsActive {
        @Test
        void allowsTransfer() {
            // Test logic
        }
    }
}
```

Dynamic test được tạo trong runtime thông qua `@TestFactory`. Một số filter theo tên có thể cần xem cách framework đặt display name thay vì chỉ nhìn tên method Java. Khi một test parameterized/dynamic không được chọn như dự kiến, hãy xem test descriptor hoặc tên trong report.

## 15. Tổ chức test để chọn lọc rõ ràng

Một quy ước đặt tên và tag nhất quán giúp nhóm chọn test theo mục đích mà không cần viết filter phức tạp.

Ví dụ quy ước:

| Nhóm | Tên/tag gợi ý | Mục đích |
|---|---|---|
| Unit test nhanh | `*Test`, tag `fast` | Chạy thường xuyên ở mỗi commit. |
| Integration test | `*IT`, tag `integration` | Kiểm tra tương tác với DB, HTTP, queue hoặc hệ thống thật. |
| Smoke test | tag `smoke` | Xác nhận đường đi quan trọng sau deploy. |
| Slow test | tag `slow` | Nhóm test chạy lâu, có thể chạy theo lịch hoặc pipeline riêng. |
| Platform-specific test | tag `windows`, `linux` | Chỉ chạy trên môi trường phù hợp. |

Tag cần được sử dụng thống nhất. Nếu một test vừa là integration vừa chạy lâu, có thể gắn cả hai tag. Chính sách CI quyết định pipeline nào include hoặc exclude các tag đó.

Không nên dùng tên lớp như cơ chế phân loại duy nhất khi dự án có nhiều loại test. Kết hợp source set, task riêng và tag/group sẽ giúp build script diễn đạt rõ hơn.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Test class biên dịch thành công nghĩa là test chắc chắn được chạy | Còn cần framework/engine, discovery, selection và task phù hợp. |
| Test không có trong report nghĩa là test đã pass | Có thể test chưa được phát hiện, bị filter hoặc task chưa chạy. |
| Skipped giống filtered out | Skipped thường là test đã được framework nhận diện nhưng không thực thi; filtered out bị loại trước khi chạy. |
| Gradle `--tests` là cách chọn JUnit tag | `--tests` lọc tên; tag filter cấu hình qua JUnit Platform. |
| Maven `mvn test` chạy cả integration test | Failsafe thường gắn với `integration-test` và `verify`; cần chạy lifecycle đến `verify`. |
| `-DskipTests` và `-Dmaven.test.skip=true` giống nhau | Tùy chọn thứ hai còn bỏ qua biên dịch test source ở plugin hỗ trợ. |
| Build xanh chứng minh không có test failed | Cấu hình có thể bỏ qua failure; phải đọc report và trạng thái pipeline. |
| Chỉ cần xem log console để điều tra | XML/HTML report thường có danh sách test, trạng thái, thời gian và stack trace đầy đủ hơn. |
| Một method parameterized chỉ tạo một test result | Framework có thể tạo nhiều invocation từ một method. |
| Có test engine trong compile classpath là đủ | Engine cần có trên runtime test classpath để thực thi. |

## 17. Quy trình tìm nguyên nhân khi test không chạy như mong đợi

Khi một test không xuất hiện hoặc kết quả khác dự kiến, hãy đi theo quy trình:

1. Xác định build tool và task/phase đã chạy.
2. Xác định test thuộc source set hoặc thư mục test nào.
3. Kiểm tra test class đã được biên dịch chưa.
4. Kiểm tra framework API và engine/provider trong test runtime classpath.
5. Kiểm tra annotation và quy tắc phát hiện của framework.
6. Kiểm tra include/exclude, tag/group và filter theo tên.
7. Kiểm tra tùy chọn bỏ qua task hoặc bỏ qua test.
8. Mở report HTML/XML và phân biệt passed, failed, skipped, error.
9. Đọc stack trace và log của test để tìm nguyên nhân thực thi.
10. Sau khi sửa, chạy test cụ thể để tái hiện, rồi chạy toàn bộ nhóm test có liên quan.

Ví dụ: `CalculatorTest` đã có trong `build/classes/java/test` nhưng report không có test nào. Kiểm tra `useJUnitPlatform()`, dependency `junit-jupiter` và runtime engine/launcher. Nếu lớp được phát hiện nhưng không chạy khi gọi `--tests`, kiểm tra pattern tên lớp và phương thức. Nếu report có trạng thái skipped, đọc annotation hoặc assumption trong test. Mỗi tình huống nằm ở một giai đoạn khác nhau.

## 18. Bài thực hành

Thực hành trên một dự án Java có Gradle hoặc Maven:

1. Tạo một lớp `CalculatorTest` với hai test method và chạy toàn bộ test.
2. Xác nhận lớp test được biên dịch và tìm file `.class` trong thư mục output.
3. Chạy riêng một method bằng Gradle `--tests` hoặc Maven `-Dtest=Class#method`.
4. Tạo một test có tag `fast` và một test có tag `integration`; cấu hình task chỉ chạy tag `fast`.
5. Tạo một test bị bỏ qua bằng annotation của framework và quan sát trạng thái trong report.
6. Cố ý dùng một tên lớp không khớp pattern mặc định của Surefire, sau đó cấu hình include để phát hiện lớp đó.
7. Chạy `mvn test` và `mvn verify` trên dự án có Surefire/Failsafe; so sánh nhóm test được chạy và thư mục báo cáo.
8. Tạo một test thất bại có assertion message rõ ràng. Mở HTML/XML report và tìm stack trace.
9. Thử bỏ qua task hoặc test bằng tùy chọn của build tool, rồi giải thích khác biệt giữa task không chạy, test bị filter và test bị skipped.
10. Lưu báo cáo XML và xác định cách CI có thể thu thập báo cáo ngay cả khi build thất bại.

Sau bài thực hành, bạn cần giải thích được test được phát hiện nhờ đâu, cách chọn một lớp/method/tag/group, cách phân biệt test chưa được tìm thấy với test bị bỏ qua, nơi tìm báo cáo HTML/XML và cách dùng báo cáo để truy nguyên lỗi. Đây là nền tảng để xây dựng pipeline kiểm thử có kết quả rõ ràng và đáng tin cậy.
