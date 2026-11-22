# Cấu hình Gradle `useJUnitPlatform()` và thực thi test bằng Gradle Wrapper

## Mục tiêu học tập

Sau bài này, bạn có thể:
- Hiểu `test` task của Gradle, JUnit Platform, JUnit Jupiter và lý do cần gọi `useJUnitPlatform()`.
- Khai báo dependency kiểm thử phù hợp trong dự án Spring Boot dùng **Gradle Groovy DSL** (`build.gradle`).
- Chạy kiểm thử bằng `gradlew`/`gradlew.bat` trên Linux, macOS hoặc Windows, không phụ thuộc việc máy đã cài Gradle toàn cục.
- Chạy một ví dụ JUnit 5 đầy đủ, kiểm tra báo cáo test, chọn lọc test và xử lý lỗi cấu hình thường gặp.
- Phân biệt **Gradle Wrapper** (chọn phiên bản Gradle) với **Java/JDK** và thư viện JUnit (mỗi thứ phải được cấu hình riêng).

Phạm vi bài học là **thiết lập và thực thi test**. Những assertion nghiệp vụ cụ thể của test chỉ đóng vai trò ví dụ để xác nhận cấu hình hoạt động.

## 1. Ba thành phần phối hợp khi chạy JUnit 5

Dự án Java/Spring Boot thường dùng các thành phần sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| **Gradle Java plugin** | Tạo các source set `main`, `test` và task `test` để biên dịch, thực thi kiểm thử. |
| **JUnit Platform** | Cơ chế phát hiện và khởi chạy các test thông qua một hay nhiều test engine. |
| **JUnit Jupiter** | API như `org.junit.jupiter.api.Test`, `Assertions` và Jupiter engine thực thi JUnit 5 test. |
| **Gradle Wrapper** | Các script kèm cấu hình tải/chọn bản Gradle mà dự án quy định. |

Khi áp dụng Java plugin, Gradle thông thường đọc mã sản phẩm ở `src/main/java` và mã kiểm thử ở `src/test/java`. Task `test` nằm trong vòng đời build của Java plugin; `check` phụ thuộc vào `test`, còn `build` phụ thuộc vào `check` thông qua các task Java chuẩn.

**`useJUnitPlatform()` cấu hình một task kiểu `Test` chạy qua JUnit Platform.** Nó không tự thêm JUnit Jupiter API, không tạo bài test, và không tự tải JUnit engine. Nếu thiếu dependency, task có thể không tìm thấy test hoặc báo lỗi runtime. Ngược lại, thêm `@Test` của Jupiter vào mã nhưng không cho Gradle chạy JUnit Platform cũng chưa phải cấu hình hoàn chỉnh.

Một cách nhìn tổng quan:

~~~text
src/test/java/.../*Test.java
           |
           v
   Gradle test task (Test)
           |
           | useJUnitPlatform()
           v
      JUnit Platform
           |
           v
     JUnit Jupiter Engine
           |
           v
    Thực thi @Test và ghi kết quả
           |
           +--> build/test-results/test/   (XML)
           +--> build/reports/tests/test/  (HTML)
~~~

Sơ đồ mô tả pipeline thông thường với Java plugin và task `test`. Khi dự án là multi-project, mỗi subproject tạo báo cáo trong thư mục `build` của **chính subproject đó**.

## 2. Cấu hình trong dự án Spring Boot hiện có

Với dự án Spring Boot sử dụng **Gradle Groovy DSL**, thêm hoặc đối chiếu các đoạn sau trong `build.gradle` của module chứa test:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình để tích hợp vào dự án Spring Boot đã có plugin, repositories và quản lý phiên bản dependency**, không phải file `build.gradle` độc lập hoàn chỉnh.

### Giải thích từng dòng

- `testImplementation 'org.springframework.boot:spring-boot-starter-test'`: thêm bộ thư viện kiểm thử cho mã test, gồm hỗ trợ Spring Test, JUnit Jupiter, assertion/mocking libraries theo phiên bản Spring Boot mà dự án sử dụng.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'`: khai báo JUnit Platform launcher ở runtime của test, theo hướng dẫn cấu hình Gradle hiện đại. Dependency này không thay thế Jupiter engine; engine cần xuất hiện trên test runtime classpath (thường đã được mang vào bởi starter test).
- `tasks.named('test', Test)`: cấu hình đúng task `test` đã được Java plugin tạo. Đây là cú pháp Groovy DSL; Kotlin DSL (`build.gradle.kts`) dùng cú pháp khác.
- `useJUnitPlatform()`: yêu cầu Gradle chạy task đó qua JUnit Platform để nhận diện Jupiter test.

**Quản lý phiên bản:** Đoạn trên không ghi số phiên bản vì giả định dự án đã quản lý dependency bằng Spring Boot dependency management hoặc Spring Boot BOM. Nếu dự án không áp dụng cơ chế quản lý phiên bản, dependency không có version sẽ không phân giải đúng. Trong dự án hiện có, hãy theo hệ thống quản lý phiên bản của chính dự án, tránh tùy tiện ghim một phiên bản JUnit không tương thích với Spring Boot.

Nếu dự án đã có `tasks.named('test') { useJUnitPlatform() }`, không cần tạo một block trùng lặp chỉ để gọi lại cùng một phương thức. Nếu có **nhiều task kiểu `Test`** (ví dụ task integration test riêng), cấu hình mỗi task cần chạy JUnit 5; việc cấu hình riêng `test` **không tự bảo đảm** các task mới tạo cũng dùng JUnit Platform. Một lựa chọn áp dụng cho mọi task kiểu `Test` là:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Chỉ chọn cách áp dụng toàn bộ khi bạn muốn mọi task `Test` chạy qua JUnit Platform; một số task có thể được thiết kế dùng framework khác và cần cấu hình riêng.

### Vai trò của scope dependency

| Scope | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| `implementation` | Mã sản phẩm cần thư viện lúc compile/runtime | Spring Boot starter của ứng dụng |
| `testImplementation` | Mã kiểm thử cần API lúc compile, đồng thời có trên test runtime classpath | `spring-boot-starter-test` hoặc JUnit Jupiter |
| `testRuntimeOnly` | Test cần thành phần ở lúc chạy nhưng không cần import ở mã nguồn test | JUnit Platform launcher |

Không đưa `junit-jupiter` hoặc `spring-boot-starter-test` vào `implementation` của ứng dụng chỉ để test biên dịch. Đặt chúng vào test scopes để giảm việc mang thư viện kiểm thử vào runtime sản phẩm.

## 3. Ví dụ tối thiểu chạy được bằng Gradle + JUnit Jupiter

Để kiểm chứng riêng phần cấu hình, có thể tạo một dự án Java Gradle nhỏ. Ví dụ dưới đây **chạy độc lập** với Java 17+ và Gradle phiên bản tương thích; không cần Spring ApplicationContext. Sau khi hiểu nó, bạn có thể đặt test theo cùng cấu trúc vào dự án Spring Boot.

Cấu trúc thư mục:

~~~text
junit-platform-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/ShippingFeeCalculator.java
    └── test/java/com/example/testing/ShippingFeeCalculatorTest.java
~~~

Các tệp Wrapper được tạo ở bước 4; không cần tự chép mã nhị phân của `gradle-wrapper.jar`.

**`settings.gradle`**

~~~groovy
rootProject.name = 'junit-platform-demo'
~~~

**`build.gradle`** — ví dụ dùng BOM JUnit 5.10.2 để quản lý đồng bộ Jupiter và Platform; đây là một phiên bản minh họa nhất quán, không phải yêu cầu tất cả dự án mới phải dùng đúng phiên bản đó:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Ở đây `platform('org.junit:junit-bom:5.10.2')` là **JUnit BOM** để Gradle chọn phiên bản tương thích của các thành phần JUnit không ghi version. Java toolchain yêu cầu JDK 17 có sẵn hoặc cơ chế provisioning đã được cấu hình; toolchain không tự bảo đảm máy đã cài JDK.

**`src/main/java/com/example/testing/ShippingFeeCalculator.java`**

~~~java
package com.example.testing;

public final class ShippingFeeCalculator {

    public int feeFor(int orderAmount) {
        if (orderAmount < 0) {
            throw new IllegalArgumentException(
                    "orderAmount must not be negative");
        }
        return orderAmount >= 500 ? 0 : 30;
    }
}
~~~

Quy ước bài toán: giá trị đơn hàng từ `500` trở lên được miễn phí vận chuyển (`0`); nhỏ hơn `500` chịu phí `30`; số âm là dữ liệu không hợp lệ. Dùng `int` để giữ ví dụ tập trung vào hạ tầng kiểm thử; ứng dụng tính tiền thật nên có thiết kế kiểu số và đơn vị tiền phù hợp.

**`src/test/java/com/example/testing/ShippingFeeCalculatorTest.java`**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeeCalculatorTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @Test
    void ordersAtThresholdHaveFreeShipping() {
        assertEquals(0, calculator.feeFor(500));
    }

    @Test
    void ordersBelowThresholdPayShipping() {
        assertEquals(30, calculator.feeFor(499));
    }

    @Test
    void negativeOrderAmountIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.feeFor(-1));
    }
}
~~~

Lưu ý import **`org.junit.jupiter.api.Test`** thuộc JUnit Jupiter, khác với `org.junit.Test` thuộc JUnit 4. Ba test trên kiểm tra hai nhánh hợp lệ, một trường hợp không hợp lệ; không gọi Spring và không in ra `stdout`. Với mã và dependency đúng, JUnit Platform phát hiện **3 test** trong class.

Một test không cần `public` ở class hoặc method trong JUnit Jupiter thông thường; `class ShippingFeeCalculatorTest` và các method package-private ở ví dụ là hợp lệ. Gradle nhận diện test dựa trên test engine và annotation, không dựa duy nhất vào việc tên tệp kết thúc bằng `Test`.

### Chạy và kiểm tra bằng Wrapper

Sau khi Wrapper đã có, mở terminal tại thư mục **chứa `gradlew`, `gradlew.bat`, `settings.gradle`**.

Trên Linux/macOS:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Với ví dụ trên, cả ba test phải pass; Gradle kết thúc thành công, thường có dòng `BUILD SUCCESSFUL` (định dạng và số task phụ thuộc phiên bản Gradle/cached tasks). **Các test không viết ra stdout**, nên không có ba dòng kết quả in sẵn trong console. Kết luận số test thực chạy bằng test report, không suy ra chỉ từ dòng `BUILD SUCCESSFUL`.

Kết quả thường xuất hiện tại:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ShippingFeeCalculatorTest.xml
    └── binary/...
~~~

`index.html` là báo cáo HTML cho người đọc; các file XML phục vụ CI và công cụ tổng hợp. Các file con có thể thay đổi theo Gradle; tên XML có thể mang tên class phù hợp. File XML của lớp ví dụ thể hiện 3 lượt test nếu cả ba được thực thi và không bị filter.

## 4. Gradle Wrapper là gì và cách tạo

**Gradle Wrapper** gồm các script chạy Gradle và tệp cấu hình chỉ rõ Gradle distribution. Nó giúp developer, CI cùng dùng **phiên bản Gradle của dự án**, thay vì mỗi máy chạy một phiên bản `gradle` đã cài toàn cục. Wrapper **không tự khóa JDK** hoặc phiên bản thư viện: JDK, dependency và repository vẫn cần cấu hình tương ứng.

Các tệp nên được lưu cùng mã nguồn:

| Tệp | Vai trò |
| --- | --- |
| `gradlew` | Script gọi Gradle trên Linux/macOS |
| `gradlew.bat` | Script gọi Gradle trên Windows |
| `gradle/wrapper/gradle-wrapper.jar` | Mã launcher của Wrapper |
| `gradle/wrapper/gradle-wrapper.properties` | Cấu hình distribution URL, và các thuộc tính Wrapper liên quan |

### Khi chưa có Wrapper

Máy cần có một lệnh **`gradle` chạy được** để tạo Wrapper lần đầu. Ở thư mục dự án Java Gradle, ví dụ tạo Wrapper cho Gradle `8.5`:

~~~bash
gradle wrapper --gradle-version 8.5 --distribution-type bin
~~~

Lệnh này là **bước bootstrap minh họa**. Dự án thực phải chọn phiên bản Gradle tương thích với Java, Spring Boot và plugin đang dùng; không tự ý hạ hoặc nâng phiên bản chỉ vì ví dụ ghi `8.5`. Nếu dự án **đã có Wrapper**, thông thường chỉ cần dùng đúng các script đã có, không cần chạy lại lệnh tạo Wrapper.

Một đoạn của `gradle/wrapper/gradle-wrapper.properties` sau khi tạo có thể giống:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip
~~~

Không tự sửa `distributionUrl` để trỏ đến nguồn không tin cậy. Khi chạy lần đầu, Wrapper có thể cần kết nối mạng để tải Gradle distribution; các lần sau thường sử dụng bản đã cache nếu còn phù hợp. `--distribution-type bin` chọn bản phân phối binary, đủ để build/test; bản `all` thêm tài liệu và sources của Gradle.

### Kiểm tra công cụ đang dùng

Linux/macOS:

~~~bash
java -version
./gradlew --version
./gradlew tasks
~~~

Windows PowerShell:

~~~powershell
java -version
.\gradlew.bat --version
.\gradlew.bat tasks
~~~

`java -version` cho biết JVM đang được tìm qua môi trường shell; `gradlew --version` cho biết Gradle/JVM chạy Gradle; Java **toolchain** của task compile/test có thể là JDK khác với JVM chạy Gradle. Nếu dự án yêu cầu Java 17 hoặc 21, cần xác minh Gradle phiên bản hiện tại hỗ trợ JVM ấy và toolchain tương ứng được tìm thấy.

Trên Linux/macOS, nếu Wrapper script bị từ chối vì thiếu quyền thực thi, có thể cần:

~~~bash
chmod +x gradlew
./gradlew test
~~~

Trên Windows, dùng `.\gradlew.bat` chứ không dùng `./gradlew` của Unix; PowerShell thường cần tiền tố `.\` để chạy script trong thư mục hiện tại. Không cần cài Gradle toàn cục để chạy project **đã có Wrapper và có môi trường Java phù hợp**.

## 5. Các lệnh thường dùng để thực thi test

Bảng dưới sử dụng cú pháp Linux/macOS `./gradlew`. Trên Windows PowerShell thay bằng `.\gradlew.bat`; tham số sau script giữ nguyên.

| Lệnh | Mục đích |
| --- | --- |
| `./gradlew test` | Chạy task `test` theo cấu hình hiện có. |
| `./gradlew clean test` | Xóa output build trước rồi build/test lại. |
| `./gradlew test --tests 'com.example.testing.ShippingFeeCalculatorTest'` | Chỉ chạy các test của một class theo filter. |
| `./gradlew test --tests 'com.example.testing.ShippingFeeCalculatorTest.ordersAtThresholdHaveFreeShipping'` | Chạy một test method đúng tên. |
| `./gradlew test --info` | Hiển thị log chi tiết hơn để chẩn đoán. |
| `./gradlew test --stacktrace` | Hiển thị stack trace khi Gradle gặp lỗi. |
| `./gradlew test --no-daemon` | Chạy không sử dụng daemon lâu dài, thường hữu ích trong một số môi trường CI. |
| `./gradlew :app:test` | Chạy task `test` của subproject có project path thật là `:app`; thay bằng path thực tế của dự án. |

**`test` không phải lúc nào cũng chạy lại tất cả test.** Gradle có thể báo `UP-TO-DATE` hoặc `FROM-CACHE` khi task output được tái sử dụng. `NO-SOURCE` cho biết task không có nguồn test để xử lý trong cấu hình đó. Cả ba trạng thái cần được hiểu đúng; nếu cần chạy lại để chẩn đoán, có thể dùng:

~~~bash
./gradlew test --rerun-tasks
~~~

`--rerun-tasks` có thể buộc nhiều task trong task graph chạy lại, nên không cần dùng mặc định cho mỗi lần test. `clean test` cũng làm lại build output nhưng có chi phí biên dịch lớn hơn.

### Gradle multi-project

Khi một kho có nhiều Gradle project, task path xác định module đang kiểm thử:

~~~bash
./gradlew :orders:test
~~~

Đây là **ví dụ cú pháp**, chỉ hợp lệ nếu `:orders` là project đã được khai báo. Trong repo thực, xem project paths trong `settings.gradle` hoặc chạy `./gradlew projects`. Không suy luận đường dẫn task từ tên thư mục hay tên artifact mà chưa kiểm tra cấu trúc Gradle. Trong composite builds, project và included-build task paths có thể khác nhau.

### Bật log test khi cần

Mặc định console thường hiển thị thông tin task và lỗi; để dễ nhìn sự kiện test, bổ sung vào cấu hình task hiện có:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
~~~

Dùng **một** block `tasks.named('test', Test)` có cấu hình gộp nếu đã tồn tại block đó. Cấu hình này hiển thị sự kiện tương ứng, không tạo test hay đổi kết quả kiểm thử. Với CI, XML/HTML test report vẫn là nguồn phù hợp để xem tổng số và từng lỗi.

## 6. Cách xác nhận cấu hình thực sự đúng

Sau khi chạy thử ví dụ ở mục 3, xác minh theo thứ tự sau:

1. **Wrapper gọi đúng Gradle distribution:** `./gradlew --version` thành công và phiên bản phù hợp với dự án.
2. **JDK đúng:** Gradle khởi động được và Java toolchain của task tìm thấy JDK cần dùng.
3. **Dependency được phân giải:** không có lỗi tải `junit-jupiter`, JUnit Platform launcher hoặc Spring Boot starter test từ repository.
4. **Test được biên dịch:** class ở `src/test/java` import được `org.junit.jupiter.api.Test` và các assertion.
5. **JUnit Platform phát hiện test:** class ví dụ được báo cáo là có 3 test thay vì 0/`NO-SOURCE`; chạy bộ lọc một class cũng tìm thấy đúng class.
6. **Kết quả được ghi:** HTML/XML report xuất hiện, tất cả assertion pass; cố ý đổi kết quả kỳ vọng ở **một bản thử nghiệm cục bộ**, test phải fail, sau đó hoàn nguyên.

Ở ví dụ, thay `assertEquals(0, calculator.feeFor(500))` thành `assertEquals(1, calculator.feeFor(500))` sẽ làm test ngưỡng thất bại nếu runner thực sự chạy test. Điều này xác minh đường đi từ source test tới Jupiter và Gradle test report. **Chỉ hoàn nguyên sửa đổi thử nghiệm sau khi xác minh.**

Nếu muốn xác nhận riêng việc Gradle phát hiện test trong một dự án lớn, dùng `--tests` với tên class chính xác và xem report; điều này có ý nghĩa hơn việc dựa vào dòng thông báo `BUILD SUCCESSFUL` khi task có thể bị cache hoặc không có source.

## 7. Lỗi thường gặp: triệu chứng, nguyên nhân và cách sửa

| Triệu chứng | Khả năng thường gặp | Cách xử lý |
| --- | --- | --- |
| `No tests found for given includes…` khi dùng `--tests` | Filter sai package/class/method, hoặc test không được engine nhận diện | Kiểm tra tên đầy đủ, vị trí `src/test/java`, annotation `@Test` đúng JUnit Jupiter và `useJUnitPlatform()` |
| `test NO-SOURCE` | Không có mã nguồn test được gắn vào source set của task | Kiểm tra đúng module, đường dẫn tệp, extension, `sourceSets` nếu đã tùy chỉnh |
| Task pass nhưng test report có 0 test | Chưa có test thực sự được discovery hoặc task cấu hình sai | Kiểm tra engine, dependency, task path, test filter và XML/HTML report |
| Lỗi kiểu `Cannot create Launcher without at least one TestEngine` | Thiếu test engine trên runtime classpath | Bổ sung `junit-jupiter`/Jupiter engine qua dependency đúng và kiểm tra dependency graph |
| Lỗi thiếu class của JUnit Platform launcher | Launcher dependency không có hoặc phiên bản lệch | Thêm `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` và dùng BOM/quản lý version nhất quán |
| `Could not find method useJUnitPlatform()` | Gọi sai ngữ cảnh hoặc Gradle quá cũ | Đặt trong task kiểu `Test`, dùng Gradle hỗ trợ JUnit Platform |
| Gradle không chạy được vì JVM/class version | Gradle, JDK, plugin yêu cầu phiên bản không tương thích | Xem `java -version` và `gradlew --version`, đối chiếu compatibility matrix của phiên bản thực |
| `.\gradlew.bat` không tìm thấy | Terminal không ở thư mục project root hoặc Wrapper thiếu | Chạy tại thư mục có `gradlew.bat`; xác minh các tệp Wrapper được lưu trong repo |
| `Permission denied` cho `./gradlew` | Wrapper script trên Unix thiếu execute bit | Dùng `chmod +x gradlew` nếu được phép |
| Không thể tải Gradle distribution/dependency | Mạng, proxy, repository hoặc cache không sẵn | Kiểm tra `distributionUrl`, repository, network/proxy và cấu hình môi trường CI |
| Test Spring Boot lỗi khi khởi động context | Thiếu bean/config/profile/database hoặc hạ tầng test | Đọc stack trace của test, tách lỗi application context khỏi cấu hình runner, cung cấp cấu hình test phù hợp |

### JUnit 4 và JUnit Jupiter không phải cùng một `@Test`

Hai import sau trông giống nhau nhưng thuộc các framework/engine khác nhau:

~~~java
// JUnit Jupiter (JUnit 5) — dùng với Jupiter engine
import org.junit.jupiter.api.Test;

// JUnit 4 — cần cơ chế tương thích riêng khi chạy trên JUnit Platform
// import org.junit.Test;
~~~

Khi mới viết test, dùng Jupiter annotation và Jupiter engine. Nếu đang **di trú test JUnit 4 cũ**, có thể cần JUnit Vintage engine trên test runtime classpath để JUnit Platform chạy các test JUnit 4 đó. Không thêm Vintage nếu không có nhu cầu; nó không phải dependency bắt buộc cho test Jupiter. Với Mockito/Spring Test, dùng extension phù hợp với Jupiter như `@ExtendWith`, không giả định `@RunWith` JUnit 4 tự hoạt động trên Jupiter.

### Lỗi trong ứng dụng khác với lỗi cấu hình test runner

Nếu JUnit phát hiện và chạy test `@SpringBootTest` nhưng Spring context không khởi tạo được, đó thường là lỗi **bootstrapping ứng dụng hoặc fixture môi trường**: bean thiếu, cấu hình sai, database không sẵn, v.v. Khi đó `useJUnitPlatform()` có thể đã đúng. Hãy phân biệt:
- **Không chạy/discover được test** → kiểm tra Gradle test task, engine, launcher, source set và dependency.
- **Test đã chạy nhưng assertion hoặc context fail** → kiểm tra behavior ứng dụng, dữ liệu đầu vào, profile test và log lỗi cụ thể.

`@SpringBootTest` chỉ cần khi kiểm thử ngữ cảnh Spring; unit test Java thuần như ví dụ không cần annotation đó. Tránh chạy Spring context cho mọi phép tính thuần vì làm chậm bộ test và tăng phụ thuộc môi trường.

## 8. Chạy trong CI và checklist thực hành

Trong CI, thực hành phổ biến là checkout source (bao gồm Wrapper), cài JDK phù hợp, rồi chạy task test bằng script của **chính repository**:

~~~bash
./gradlew --no-daemon test
~~~

Nếu dự án nhiều module, chọn task path thích hợp; nếu CI cần toàn bộ check, `./gradlew check` chạy chuỗi verification tasks được Java plugin và plugin dự án thiết lập (không đồng nghĩa mọi test tùy chỉnh đều đã được nối vào `check`). Khi pipeline fail, thu thập `build/test-results/test/` và `build/reports/tests/test/` theo từng module làm test artifacts. CI cũng cần quyền truy cập repository/dependency cache, và hạ tầng cần thiết đối với integration test.

Trước khi coi công việc thiết lập test hoàn tất, hãy tự trả lời:

- `build.gradle` chứa đúng test dependency và Gradle task `test` gọi `useJUnitPlatform()` chưa?
- Test import `org.junit.jupiter.api.Test` và có Jupiter engine/launcher phù hợp chưa?
- Wrapper gồm đủ bốn tệp cần thiết và Gradle distribution phù hợp với JDK/plugin của dự án chưa?
- Test ở đúng source set/module; task path và filter đã đúng chưa?
- Báo cáo HTML/XML có phản ánh **số test thực sự chạy**, và thử tạo một assertion sai có làm test fail chưa?
- Ở CI, JDK, repository và cấu hình môi trường của integration test có tái lập được không?

**Ghi nhớ:** `useJUnitPlatform()` là phần **cấu hình cách Gradle chạy test**; `spring-boot-starter-test`/JUnit Jupiter cung cấp **thư viện và engine**, còn Wrapper giúp mọi môi trường gọi **bản Gradle do dự án chọn**. Một setup đáng tin phải có đủ ba phần, rồi được xác nhận bằng test report và một phép kiểm chứng thực sự có thể fail.
