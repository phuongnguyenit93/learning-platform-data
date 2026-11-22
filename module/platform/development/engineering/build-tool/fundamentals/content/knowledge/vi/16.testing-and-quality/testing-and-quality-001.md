# Vai trò của kiểm thử tự động trong hợp đồng build

Một lệnh build thành công cần mang lại một mức bảo đảm có thể hiểu và kiểm tra được. Với dự án Java, người dùng build thường mong đợi mã nguồn hợp lệ, dependency được phân giải, các bài kiểm thử quan trọng đều đạt, quy tắc chất lượng được thỏa mãn và artifact được tạo đúng cách. Tập hợp những kỳ vọng đó có thể xem là **hợp đồng build** của dự án.

Kiểm thử tự động là một phần quan trọng của hợp đồng này. Nó biến các yêu cầu về hành vi thành những kiểm tra có thể chạy lặp lại trong mỗi lần build hoặc trên CI. Khi kiểm thử thất bại, build phải phản ánh thất bại đó bằng trạng thái không thành công để người dùng và pipeline biết artifact chưa đạt điều kiện phát hành.

Hợp đồng build không phải một chuẩn riêng của Gradle hay Maven. Đây là cách mô tả thỏa thuận của dự án: lệnh nào được xem là kiểm tra đầy đủ, những điều kiện nào phải đạt, và kết quả nào được phép phát hành. Gradle/Maven cung cấp task, lifecycle và plugin để hiện thực hóa thỏa thuận đó.

## 1. Hợp đồng build gồm những gì?

Một hợp đồng build thường mô tả đầu vào, các bước kiểm tra và đầu ra được chấp nhận.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Đầu vào | Build sử dụng source, dependency và cấu hình nào? | Java source, resource, version dependency, JDK toolchain |
| Biên dịch | Mã nguồn có biên dịch được không? | `compileJava`, `compileTestJava` |
| Kiểm thử | Hành vi cần thiết có được xác minh không? | Unit test, integration test, API contract test |
| Chất lượng | Quy tắc kỹ thuật có được thỏa mãn không? | Static analysis, formatting, dependency verification |
| Đóng gói | Artifact có được tạo đúng không? | JAR, WAR, distribution ZIP |
| Kết quả | Điều kiện nào làm build thành công hoặc thất bại? | Test failure làm task thất bại và CI chặn merge/release |
| Tính tái lập | Cùng đầu vào có thể tạo kết quả nhất quán không? | Dependency lock, toolchain, test data ổn định |

Một hợp đồng build tốt cần rõ ràng với cả lập trình viên lẫn CI. Ví dụ, dự án có thể quy định:

- `./gradlew check` chạy biên dịch và tất cả kiểm tra bắt buộc, bao gồm unit test và integration test.
- `./gradlew build` tạo artifact sau khi các kiểm tra bắt buộc thành công.
- CI không publish artifact release nếu `check` thất bại.
- Các test cần dịch vụ ngoài phải dùng môi trường kiểm thử được quản lý, không phụ thuộc dữ liệu ngẫu nhiên trên máy cá nhân.

Khi mọi người dùng cùng một lệnh và cùng quy tắc, kết quả build trở thành một tín hiệu đáng tin cậy hơn về trạng thái dự án.

## 2. Kiểm thử tự động biến yêu cầu thành hành vi có thể kiểm tra

Kiểm thử tự động là chương trình thực thi một tình huống và xác nhận kết quả thực tế phù hợp với kỳ vọng. Test có thể kiểm tra giá trị trả về, trạng thái dữ liệu, ngoại lệ, tương tác giữa các thành phần hoặc hợp đồng giao tiếp.

Ví dụ, yêu cầu “đơn hàng không được xác nhận nếu không có dòng sản phẩm” có thể được thể hiện bằng test:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderServiceTest {
    @Test
    void rejectsAnOrderWithoutItems() {
        OrderService service = new OrderService();

        assertThrows(
            IllegalArgumentException.class,
            () -> service.confirm(new Order())
        );
    }
}
```

Test này ghi lại một quy tắc nghiệp vụ. Nếu ai đó thay đổi `OrderService` khiến đơn hàng rỗng được chấp nhận, test sẽ thất bại và build báo lỗi.

Kiểm thử tự động đem lại một số lợi ích:

- Phát hiện hồi quy khi thay đổi code.
- Ghi lại hành vi mong đợi bằng ví dụ thực thi được.
- Hỗ trợ refactor vì có thể chạy lại các kiểm tra sau khi thay đổi cấu trúc code.
- Cung cấp bằng chứng cho CI trước khi merge hoặc phát hành.
- Giúp người dùng thư viện hiểu hành vi được hỗ trợ và các trường hợp biên.

Tuy nhiên, test chỉ kiểm tra những tình huống đã được thiết kế. Build xanh không chứng minh chương trình không còn bug; nó cho biết các kiểm tra đã chạy đều đạt trong phạm vi dữ liệu, môi trường và giả định của chúng.

## 3. Các lớp kiểm thử trong một dự án Java

Không phải mọi test đều có cùng phạm vi hoặc chi phí. Dự án thường kết hợp nhiều lớp kiểm thử.

| Loại kiểm thử | Phạm vi | Ví dụ | Đặc điểm |
|---|---|---|---|
| Unit test | Một lớp hoặc đơn vị logic nhỏ | Kiểm tra tính toán giá, validate dữ liệu | Nhanh, thường cô lập dependency |
| Integration test | Nhiều thành phần làm việc cùng nhau | Repository với database, HTTP client với server test | Kiểm tra tích hợp thực tế hơn |
| Component test | Một thành phần lớn với dependency được kiểm soát | Kiểm tra service module qua API công khai | Phạm vi lớn hơn unit test |
| Contract test | Hợp đồng giữa hai hệ thống/thành phần | Consumer-provider API contract | Phát hiện sai lệch schema hoặc giao thức |
| End-to-end test | Luồng từ đầu đến cuối | Tạo đơn hàng qua HTTP rồi xác nhận trong database | Gần hành vi người dùng, thường chậm và nhạy môi trường |
| Smoke test | Một số đường chạy cốt lõi sau đóng gói/triển khai | Khởi động ứng dụng và gọi health endpoint | Xác nhận artifact có thể khởi động và hoạt động cơ bản |

Một mô hình thường dùng là ưu tiên nhiều unit test, ít integration test hơn và một số lượng nhỏ end-to-end test có giá trị cao. Đây là hướng tổ chức phổ biến, không phải tỷ lệ bắt buộc cho mọi hệ thống.

```text
             End-to-end tests
            Ít hơn, chi phí cao
          -----------------------
             Contract tests
          -----------------------
            Integration tests
          -----------------------
                Unit tests
          Nhiều hơn, chạy nhanh
```

Mỗi lớp kiểm thử bổ sung một góc nhìn. Unit test không thay thế kiểm tra database thật nếu dự án phụ thuộc vào SQL behavior; integration test cũng không thay thế kiểm tra logic biên ở các hàm nhỏ.

### 3.1. Unit test

Unit test kiểm tra logic nhỏ trong điều kiện có thể kiểm soát. Test thường tránh mạng, filesystem dùng chung và dịch vụ thật để chạy nhanh, ổn định.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PriceCalculatorTest {
    @Test
    void appliesDiscount() {
        PriceCalculator calculator = new PriceCalculator();

        assertEquals(90, calculator.afterDiscount(100, 10));
    }
}
```

Unit test phù hợp để kiểm tra quy tắc nghiệp vụ, điều kiện biên, xử lý null, chuyển đổi dữ liệu và lỗi đầu vào. Nếu test cần tạo database hoặc gọi dịch vụ ngoài, có thể nó đang kiểm tra phạm vi tích hợp lớn hơn.

### 3.2. Integration test

Integration test xác nhận nhiều thành phần hoạt động cùng nhau. Ví dụ, một repository có thể chạy với database test để xác minh mapping, transaction, index hoặc truy vấn thực tế.

Integration test có thể sử dụng:

- Database/container tạm thời.
- HTTP server hoặc message broker kiểm thử.
- File system trong thư mục tạm.
- Service giả lập (mock server) có hợp đồng rõ ràng.

Điều quan trọng là test phải quản lý vòng đời tài nguyên: khởi tạo, chuẩn bị dữ liệu, thực thi và dọn dẹp. Không nên phụ thuộc vào một database cá nhân có trạng thái từ lần chạy trước.

### 3.3. Contract test

Contract test kiểm tra sự tương thích giữa hai phía giao tiếp. Ví dụ, consumer mong đợi endpoint trả về trường `orderId` kiểu chuỗi; provider phải tiếp tục đáp ứng hợp đồng đó.

Contract test có thể kiểm tra:

- Tên và kiểu trường trong JSON.
- HTTP method, path và status code.
- Quy tắc xác thực request/response.
- Message schema trong hệ thống sự kiện.
- Các lỗi và điều kiện biên đã thỏa thuận.

Contract test có giá trị khi các service được phát triển hoặc triển khai độc lập. Nó giúp phát hiện thay đổi API có thể phá vỡ consumer trước khi triển khai lên môi trường thật.

### 3.4. Smoke test sau đóng gói

Unit/integration test có thể chạy trên classpath của source set. Nhưng artifact được phát hành còn có thể gặp lỗi do thiếu resource, manifest sai, dependency không được đóng gói hoặc cấu hình runtime không đúng.

Smoke test có thể chạy artifact đã đóng gói, khởi động ứng dụng trong môi trường thử nghiệm rồi gọi một số endpoint cốt lõi. Đây là cách kiểm tra gần hơn với sản phẩm mà người dùng sẽ nhận.

## 4. Test là một phần của task graph, không phải bước tùy chọn ngoài quy trình

Build tool cần kết nối các task kiểm thử vào lifecycle chuẩn. Nếu test chỉ được gọi thủ công, một người có thể chạy `build` và tạo artifact mà không thực hiện bất kỳ test nào.

Với Gradle Java plugin, các task thường liên quan:

```text
compileJava -----------+
                      |
processResources -----+----> classes
                            |
compileTestJava ------------+
                            |
                            v
                           test
                            |
                            v
                           check
                            |
                            v
                           build
```

Đây là sơ đồ khái quát. Gradle Java plugin có các dependency mặc định và plugin khác có thể bổ sung task vào graph.

Các task quan trọng:

| Task | Vai trò |
|---|---|
| `test` | Chạy test của source set chính mặc định là `test` |
| `check` | Task lifecycle tổng hợp cho các kiểm tra |
| `assemble` | Tạo artifact của project |
| `build` | Tổng hợp verification và assembly |

Nếu dự án thêm task `integrationTest`, task đó nên được nối vào `check` nếu integration test là điều kiện bắt buộc của build.

### 4.1. Cấu hình JUnit 5 trong Gradle

Ví dụ với Groovy DSL:

```groovy
plugins {
    id 'java'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`testImplementation` đưa JUnit vào compile/runtime classpath của test. `useJUnitPlatform()` cấu hình Gradle Test task sử dụng JUnit Platform, cần thiết khi chạy JUnit Jupiter theo cấu hình phổ biến.

Chạy:

```bash
./gradlew test
```

Hoặc chạy toàn bộ verification:

```bash
./gradlew check
```

Khi chạy `check`, Gradle sẽ thực hiện `test` và các task verification khác được gắn vào lifecycle.

### 4.2. Thêm integration test vào `check`

Một dự án có thể định nghĩa source set và task integration test riêng. Ví dụ dưới đây minh họa cấu hình cơ bản trong Groovy DSL:

```groovy
plugins {
    id 'java'
}

sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output + configurations.testRuntimeClasspath
        runtimeClasspath += output + compileClasspath
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
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

Trong ví dụ, source set `integrationTest` có thư mục mặc định `src/integrationTest/java` và resource tương ứng. Task `integrationTest` chạy các test đã biên dịch từ source set này. `shouldRunAfter` đề xuất chạy sau unit test nếu cả hai cùng được chọn; `dependsOn` trong `check` bảo đảm integration test được kéo vào graph khi chạy `check`.

Với dự án lớn, có thể dùng plugin convention hoặc cấu hình source set dùng chung để tránh lặp lại cấu hình này ở nhiều module. Cũng cần bảo đảm test framework được khai báo đúng trong configuration của integration test.

## 5. Maven lifecycle và vị trí chạy test

Maven tổ chức build theo lifecycle và phase. Các plugin gắn goal vào phase phù hợp.

Các phase quan trọng trong default lifecycle:

| Phase | Vai trò liên quan đến test |
|---|---|
| `test-compile` | Biên dịch mã nguồn kiểm thử |
| `test` | Chạy unit test |
| `package` | Đóng gói artifact sau test |
| `pre-integration-test` | Chuẩn bị môi trường cho integration test |
| `integration-test` | Chạy integration test |
| `post-integration-test` | Dọn dẹp hoặc thu hồi môi trường test |
| `verify` | Xác minh kết quả và các điều kiện sau tích hợp |
| `install` | Cài artifact vào local repository sau các phase trước |

### 5.1. Unit test với Maven Surefire

Maven Surefire Plugin thường chạy unit test ở phase `test`.

Ví dụ cấu hình:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.2.5</version>
    </plugin>
  </plugins>
</build>
```

Khi chạy:

```bash
mvn test
```

Maven thực hiện các phase trước `test`, biên dịch source/test source và chạy unit test theo cấu hình Surefire.

### 5.2. Integration test với Maven Failsafe

Failsafe Plugin được thiết kế cho integration test và thường gắn hai goal:

- `integration-test`: thực hiện integration test.
- `verify`: kiểm tra kết quả test và làm build thất bại nếu có lỗi.

Ví dụ:

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

Failsafe tách việc chạy test khỏi việc báo lỗi cuối cùng để các phase `post-integration-test` và `verify` có cơ hội thực hiện dọn dẹp và tổng kết. Vì vậy, khi dùng Failsafe, nên chạy:

```bash
mvn verify
```

Không nên chỉ gọi `mvn integration-test` rồi xem đó là kết quả cuối cùng của toàn bộ quy trình integration test.

### 5.3. `mvn package` và `mvn verify` khác nhau

Nếu Failsafe được cấu hình cho integration test, `mvn package` đi đến phase package nhưng chưa đi hết các phase `pre-integration-test`, `integration-test`, `post-integration-test`, `verify` vốn nằm sau package trong default lifecycle. Vì vậy, `mvn package` không thay thế `mvn verify` khi hợp đồng build yêu cầu integration test.

Trong CI, `mvn clean verify` thường là lựa chọn phù hợp để chạy unit test, integration test và các bước verification đã cấu hình trước khi artifact được xem là đạt điều kiện.

## 6. Test failure phải làm build thất bại

Một test thất bại có ý nghĩa khi nó làm cho kết quả build phản ánh đúng trạng thái đó. Nếu task test in ra lỗi nhưng build vẫn exit code `0`, pipeline có thể tiếp tục publish artifact không đạt điều kiện.

Thông thường:

- Test pass: task test thành công.
- Assertion thất bại hoặc test ném lỗi không được xử lý: task test thất bại.
- Task kiểm thử thất bại: lifecycle task phụ thuộc vào nó không thể hoàn thành thành công.
- CI nhận exit code khác `0` và đánh dấu job thất bại.

Không nên vô hiệu hóa failure chỉ để pipeline màu xanh. Nếu một test không phù hợp hoặc đang được thay thế, cần xử lý rõ ràng bằng cách sửa test, phân loại test, hoặc thay đổi hợp đồng có review.

### 6.1. Gradle: không bỏ qua test trong build chuẩn

Lệnh sau loại task `test` khỏi graph:

```bash
./gradlew build -x test
```

Nó hữu ích cho một số tình huống chẩn đoán hoặc build tạm, nhưng không nên dùng làm lệnh CI xác nhận chất lượng nếu test là một phần hợp đồng build.

Gradle cũng có tùy chọn `ignoreFailures` trên Test task. Nếu bật, task có thể ghi nhận test failure nhưng không làm task thất bại theo cách thông thường. Chỉ dùng khi có quy trình riêng để xử lý kết quả và không để artifact release vượt qua quality gate chỉ vì failure bị bỏ qua.

### 6.2. Maven: phân biệt skip test và skip test compilation

Surefire hỗ trợ:

```bash
mvn test -DskipTests
```

Tùy chọn này bỏ qua thực thi test nhưng vẫn biên dịch test source theo quy trình thông thường.

Tùy chọn:

```bash
mvn package -Dmaven.test.skip=true
```

có thể bỏ qua cả biên dịch test source và chạy test thông qua các plugin hỗ trợ property này. Đây là hai hành vi khác nhau.

Các tùy chọn skip có thể hữu ích khi điều tra build hoặc tạo artifact tạm trong một workflow được kiểm soát. Nhưng chúng không nên thay thế lệnh verify chuẩn của CI/release.

## 7. Test report là bằng chứng của build

Khi test chạy, build tool và test framework tạo báo cáo để người phát triển biết test nào thành công, thất bại, bị bỏ qua hoặc gặp lỗi khởi tạo.

Gradle Java plugin thường tạo báo cáo HTML tại:

```text
build/reports/tests/test/index.html
```

và dữ liệu kết quả nhị phân/XML trong các thư mục output của task test, tùy phiên bản và cấu hình.

Maven Surefire thường ghi báo cáo tại:

```text
target/surefire-reports/
```

Maven Failsafe thường ghi báo cáo tại:

```text
target/failsafe-reports/
```

Các báo cáo có thể chứa:

- Tổng số test được chạy.
- Số test thành công, thất bại và bị bỏ qua.
- Stack trace và assertion message.
- Thời gian chạy từng test.
- Thông tin test suite và môi trường.

CI nên lưu test report như artifact của job, kể cả khi build thất bại. Nhờ đó, nhóm có thể xem nguyên nhân mà không phải chạy lại ngay trên máy cá nhân.

## 8. Kiểm thử tự động và quality gate

Test là một phần của quality gate, nhưng không phải phần duy nhất. Một dự án có thể kết hợp:

- Compile với compiler warnings được kiểm soát.
- Unit/integration/contract tests.
- Static analysis và lint.
- Kiểm tra format.
- Kiểm tra dependency/license/security.
- Kiểm tra coverage theo ngưỡng có ý nghĩa.
- Kiểm tra artifact sau đóng gói.

Trong Gradle, các task kiểm tra thường được nối vào `check`. Ví dụ:

```groovy
tasks.named('check') {
    dependsOn tasks.named('integrationTest')
    dependsOn tasks.named('verifyApiCompatibility')
}
```

Task `check` trở thành điểm gọi thống nhất cho các kiểm tra của dự án. CI có thể chạy:

```bash
./gradlew clean check
```

Với Maven, các plugin kiểm tra có thể được gắn vào phase `verify`. CI chạy:

```bash
mvn clean verify
```

Không nên để mỗi lập trình viên phải nhớ một danh sách dài các lệnh test, lint và check riêng. Đưa các kiểm tra bắt buộc vào một entry point chuẩn giúp hợp đồng build dễ hiểu và nhất quán.

### 8.1. Coverage không phải thước đo duy nhất của chất lượng

Code coverage đo phần code được thực thi trong test theo một tiêu chí như line, branch hoặc instruction coverage. Coverage cao không đảm bảo assertion có ý nghĩa; test có thể chạy qua một dòng mà không kiểm tra kết quả đúng.

Nên dùng coverage để tìm vùng code chưa được kiểm thử và theo dõi xu hướng, không dùng một con số duy nhất để kết luận chất lượng. Nếu đặt ngưỡng, cần chọn phạm vi và ngưỡng phù hợp, đồng thời bảo đảm report được tạo từ đúng source/test set.

### 8.2. Static analysis bổ sung cho test

Test kiểm tra hành vi khi code chạy. Static analysis có thể phát hiện một số lỗi hoặc rủi ro mà test chưa kích hoạt, như nullability, code smell, API nguy hiểm, lỗi format hoặc vi phạm quy tắc nội bộ.

Hai loại kiểm tra bổ sung cho nhau. Static analysis không thay thế test runtime; test runtime cũng không thay thế kiểm tra source và dependency.

## 9. Tính ổn định và khả năng lặp lại của test

Một hợp đồng build chỉ đáng tin nếu cùng một thay đổi không lúc pass, lúc fail vì trạng thái ngẫu nhiên không liên quan đến code.

Test ổn định nên:

- Tạo dữ liệu riêng cho mỗi lần chạy.
- Dọn dẹp tài nguyên sau khi hoàn thành.
- Không phụ thuộc thứ tự test khác.
- Không dùng thời gian, timezone hoặc locale mặc định nếu kết quả phụ thuộc chúng.
- Kiểm soát random seed khi dùng dữ liệu ngẫu nhiên.
- Tránh gọi dịch vụ production hoặc tài nguyên dùng chung không được kiểm soát.
- Có timeout hợp lý cho thao tác mạng và chờ đợi.
- Chạy được trên môi trường CI sạch.

Ví dụ, thay vì giả định timezone của máy luôn là UTC, test nên đặt timezone hoặc truyền `Clock` cụ thể cho logic cần tính thời gian. Thay vì dùng một database cá nhân, integration test nên tạo database/container tạm hoặc schema riêng.

## 10. Flaky test và ảnh hưởng đến hợp đồng build

Flaky test là test có thể pass hoặc fail không ổn định dù code và đầu vào được cho là không thay đổi. Nguyên nhân thường gặp:

- Test phụ thuộc thời gian hoặc timezone.
- Race condition trong test đa luồng.
- Dùng port cố định hoặc tài nguyên chia sẻ.
- Gọi API bên ngoài không ổn định.
- Không dọn dữ liệu sau lần chạy trước.
- Giả định thứ tự test.
- Timeout quá ngắn hoặc phụ thuộc tải máy.

Flaky test làm giảm niềm tin vào CI. Nếu mọi người quen với việc rerun job cho đến khi pass, tín hiệu test failure sẽ mất giá trị.

Khi phát hiện flaky test:

1. Lưu log, seed, thời gian và môi trường của lần fail.
2. Xác định phụ thuộc không ổn định.
3. Tạo điều kiện tái hiện cục bộ hoặc trong CI.
4. Sửa nguyên nhân gốc như race, shared state, timeout hoặc external dependency.
5. Theo dõi test sau sửa để bảo đảm không còn dao động.

Có thể dùng retry có giới hạn như biện pháp tạm thời trong một số pipeline, nhưng retry không sửa nguyên nhân và có thể che lỗi thật. Nếu phải quarantine test, cần ghi nhận owner, lý do, phạm vi ảnh hưởng và điều kiện đưa test trở lại quality gate.

## 11. Test isolation và chạy song song

Build tool có thể chạy nhiều test hoặc test suite song song để rút ngắn thời gian. Điều này chỉ an toàn nếu test độc lập hoặc tài nguyên được cô lập.

Trong Gradle:

```groovy
tasks.named('test') {
    maxParallelForks = 2
}
```

`maxParallelForks` cho phép Gradle chạy nhiều test worker process cho một Test task. Số lượng phù hợp phụ thuộc CPU, RAM và khả năng cô lập dữ liệu. Tăng song song có thể làm lộ race condition hoặc tranh chấp port/file nếu test dùng chung tài nguyên.

Với Maven Surefire, có các tùy chọn fork và parallel execution. Cần chọn chế độ dựa trên test framework, mức cô lập và khả năng thread safety của code.

Một test không nên dựa vào test khác chạy trước để chuẩn bị dữ liệu. Mỗi test hoặc test fixture phải tạo trạng thái cần thiết và dọn dẹp sau khi chạy.

## 12. Test trước và sau đóng gói

Phần lớn unit test chạy trên classpath của source set, trước khi artifact được publish. Nhưng một số lỗi chỉ xuất hiện sau đóng gói:

- Thiếu resource trong JAR.
- Manifest không có `Main-Class` hoặc `Class-Path` phù hợp.
- Service descriptor `META-INF/services` bị ghi đè khi tạo fat JAR.
- Dependency runtime không được đóng gói hoặc phân giải đúng.
- Cấu hình module path/JPMS không đúng.
- Script khởi động trỏ sai classpath.

Vì vậy, một build contract đầy đủ có thể có bước smoke test hoặc kiểm tra artifact sau `jar`/`assemble`.

Ví dụ task kiểm tra JAR có tồn tại:

```groovy
tasks.register('verifyApplicationJar') {
    dependsOn tasks.named('jar')
    inputs.file(tasks.named('jar').flatMap { it.archiveFile })

    doLast {
        def archive = tasks.named('jar').get().archiveFile.get().asFile
        if (!archive.isFile() || archive.length() == 0) {
            throw new GradleException("Application JAR is missing or empty: ${archive}")
        }
    }
}

tasks.named('check') {
    dependsOn tasks.named('verifyApplicationJar')
}
```

Ví dụ trên chỉ kiểm tra sự tồn tại/kích thước artifact, chưa phải smoke test thực thi ứng dụng. Một smoke test thực sự cần khởi chạy artifact trong môi trường thử nghiệm và kiểm tra hành vi cần thiết.

## 13. CI dùng hợp đồng build để quyết định merge và release

CI chạy cùng các bước build đã định nghĩa trong repository. Khi pull request được tạo, pipeline có thể:

1. Checkout source.
2. Chọn JDK/toolchain và build tool version.
3. Phân giải dependency.
4. Compile source và test source.
5. Chạy unit test, integration test và contract test.
6. Chạy static analysis và quality checks.
7. Đóng gói artifact.
8. Lưu báo cáo và artifact để review.

Luồng:

```text
Pull request / commit
         |
         v
    CI build job
         |
         v
       Compile
         |
         v
     Automated tests
         |
         v
   Quality checks
         |
         v
      Package
         |
         v
   Build successful?
      /       \
    Yes        No
     |          |
     v          v
 Artifact    Fail job
 eligible    Save reports
 for next    Block merge/release
 stage
```

Ví dụ lệnh CI cho Gradle:

```bash
./gradlew clean check build
```

Với Maven:

```bash
mvn clean verify
```

Trong Gradle, `build` vốn phụ thuộc vào các task tổng hợp verification và assembly; gọi cả `check build` có thể dư thừa về mặt task graph nhưng có thể làm ý định pipeline rõ hơn. Nên chọn một lệnh chuẩn nhất quán với cấu hình dự án.

Chỉ khi job đạt điều kiện, pipeline mới chuyển artifact sang bước publish/deploy. Không nên để test failure bị bỏ qua nhưng vẫn cho release chạy như bình thường.

## 14. Build contract cho thư viện và ứng dụng

Hợp đồng build có thể khác nhau theo loại sản phẩm.

**Thư viện dùng chung** thường cần:

- Unit test cho API và logic.
- Compatibility test cho public API nếu có yêu cầu hỗ trợ version.
- Test publication để xác nhận POM/module metadata và artifact đúng.
- Consumer test hoặc sample project để xác nhận thư viện có thể được sử dụng từ bên ngoài.
- Kiểm tra sources/Javadoc artifact nếu dự án phát hành chúng.

**Ứng dụng** thường cần:

- Unit test và integration test cho business logic, database, messaging và HTTP.
- Contract test cho API với consumer/provider.
- Smoke test cho JAR/WAR hoặc container image đã đóng gói.
- Kiểm tra cấu hình và migration cần thiết.
- Kiểm tra startup/shutdown và health endpoint trong môi trường thử nghiệm.

Không phải dự án nào cũng cần mọi loại test. Hợp đồng build nên chọn kiểm tra theo rủi ro và hành vi quan trọng của sản phẩm.

## 15. Kiểm thử dependency và môi trường build

Một số lỗi không nằm trong business logic mà nằm ở dependency graph hoặc toolchain:

- Version dependency được chọn khác dự kiến.
- Runtime classpath thiếu thư viện.
- Một API chỉ có ở JDK mới hơn.
- Artifact publish thiếu classifier hoặc metadata.
- Generated source không được biên dịch.

Build contract có thể bao gồm các kiểm tra dependency/toolchain:

- Khai báo Java toolchain và version compiler/runtime được hỗ trợ.
- Dùng dependency locking để kiểm soát version được chọn.
- Dùng dependency verification khi cần kiểm tra checksum/signature.
- Chạy consumer test trên artifact đã publish vào repository tạm.
- Kiểm tra dependency tree trong CI khi cập nhật thư viện quan trọng.

Các kiểm tra này bổ sung cho test chức năng. Một test pass trên classpath của project chưa chắc chứng minh artifact được publish có metadata và dependency đúng.

## 16. Không biến hợp đồng build thành quy trình quá nặng

Nếu mọi test end-to-end, kiểm tra bảo mật sâu và benchmark dài đều chạy trên mỗi lần compile, vòng phản hồi của lập trình viên sẽ chậm. Ngược lại, nếu build chuẩn chỉ compile mà không chạy test nào, CI có thể bỏ lọt hồi quy quan trọng.

Có thể chia mức kiểm tra:

| Mức | Khi chạy | Nội dung điển hình |
|---|---|---|
| Fast feedback | Trong quá trình phát triển | Compile, unit test nhanh, format cơ bản |
| Pull request gate | Trước merge | Unit test đầy đủ, integration test thiết yếu, static analysis |
| Release verification | Trước publish/deploy | Full test suite, contract/smoke test, security/license checks, artifact verification |
| Scheduled checks | Theo lịch | Test dài, compatibility matrix, benchmark, kiểm tra dependency định kỳ |

Các mức này cần được gọi từ task/lifecycle hoặc CI job có tên rõ ràng. Điều quan trọng là người dùng biết lệnh nào là kiểm tra nhanh và lệnh nào là hợp đồng đầy đủ trước khi phát hành.

## 17. Những lỗi thường gặp khi đưa test vào build

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `build` thành công dù test không chạy | Test task chưa được nối vào lifecycle hoặc bị loại khỏi graph | Kiểm tra `check`, task dependencies và lệnh CI |
| Test chạy trên máy cá nhân nhưng không chạy trên CI | Test source/configuration không được phát hiện hoặc framework engine thiếu | Kiểm tra test runtime classpath và báo cáo test |
| Maven `package` không chạy integration test | Failsafe được gắn ở phase sau `package` | Dùng `mvn verify` cho hợp đồng có integration test |
| Test failure nhưng pipeline vẫn publish | Có tùy chọn skip/ignore hoặc pipeline không kiểm tra exit code | Bỏ qua cờ skip và yêu cầu quality gate thành công |
| Test lúc pass lúc fail | Flaky test, shared state, race hoặc external service | Cô lập dữ liệu, kiểm soát thời gian/seed và sửa nguyên nhân |
| Test report không được lưu khi job thất bại | CI chỉ upload artifact khi job thành công | Cấu hình lưu report trong cả trường hợp failure |
| Unit test quá chậm | Test làm nhiều I/O hoặc gọi dịch vụ thật | Tách integration test và giảm phạm vi unit test |
| Integration test ảnh hưởng dữ liệu dùng chung | Không tạo schema/database riêng hoặc cleanup thiếu | Dùng tài nguyên tạm và quản lý lifecycle |
| Test chạy song song gây lỗi | Test chia sẻ file, port, database hoặc static state | Cô lập tài nguyên hoặc giới hạn parallelism |
| Coverage cao nhưng vẫn có bug | Assertion không kiểm tra hành vi quan trọng hoặc thiếu tình huống biên | Thiết kế test theo rủi ro và yêu cầu, không chỉ theo coverage |
| Test pass nhưng JAR chạy lỗi | Test không kiểm tra artifact đóng gói/runtime classpath | Thêm smoke test hoặc consumer test sau packaging |

## 18. Quy trình thiết kế hợp đồng build cho dự án

Khi thiết lập build contract, có thể thực hiện theo trình tự:

1. **Xác định hành vi quan trọng:** liệt kê quy tắc nghiệp vụ, API và tích hợp cần bảo vệ.
2. **Chọn lớp test phù hợp:** unit cho logic nhỏ, integration cho tương tác, contract cho giao tiếp và smoke cho artifact.
3. **Chọn entry point chuẩn:** Gradle `check`/`build` hoặc Maven `verify` theo yêu cầu.
4. **Nối task đúng lifecycle:** test và kiểm tra bắt buộc phải được kéo vào graph/lifecycle tương ứng.
5. **Quy định failure behavior:** test fail phải làm job không thành công; skip phải là ngoại lệ được kiểm soát.
6. **Quản lý môi trường test:** dữ liệu, service, port, timezone và credential phải có cách cung cấp rõ ràng.
7. **Lưu báo cáo:** bảo đảm test report có thể xem lại khi CI thất bại.
8. **Đặt quality gate:** xác định điều kiện merge, publish và deploy.
9. **Theo dõi flaky test:** xử lý nguyên nhân và không để retry che lỗi kéo dài.
10. **Kiểm tra artifact:** bổ sung smoke/consumer test khi rủi ro đóng gói hoặc publication đáng kể.

## 19. Ví dụ một hợp đồng build được tài liệu hóa

Một thư viện Java có thể công bố hợp đồng như sau:

```text
Local development:
  ./gradlew test
  Chạy unit test nhanh.

Pull request:
  ./gradlew clean check
  Compile, unit test, integration test và static analysis.

Release candidate:
  ./gradlew clean build
  Tạo JAR, sources/Javadoc nếu cấu hình, chạy verification.

Publication:
  Chỉ publish khi CI verification thành công.
  Kiểm tra POM/module metadata và artifact trong repository thử nghiệm.
```

Một dự án Maven tương ứng có thể quy định:

```text
Local development:
  mvn test

Pull request / release verification:
  mvn clean verify

Publication:
  Chỉ deploy artifact sau khi verify thành công.
```

Các lệnh cụ thể phụ thuộc plugin và task mà dự án cấu hình. Điều quan trọng là hợp đồng được viết rõ trong tài liệu đóng góp hoặc README và CI thực thi cùng quy tắc đó.

## 20. Tổng kết

Kiểm thử tự động biến yêu cầu về hành vi thành các kiểm tra thực thi được và giúp phát hiện hồi quy trong mỗi lần build. Unit, integration, contract, end-to-end và smoke test kiểm tra những phạm vi khác nhau; chúng bổ sung cho nhau và cần được chọn theo rủi ro của sản phẩm.

Trong Gradle, test và các kiểm tra bắt buộc nên được nối vào `check`; `build` tổng hợp verification và assembly. Trong Maven, Surefire thường chạy unit test ở phase `test`, còn Failsafe chạy integration test ở `integration-test` và xác nhận kết quả ở `verify`. Vì vậy, lệnh CI phải đi đến phase/task bao phủ đủ những kiểm tra mà dự án cam kết.

Một build contract đáng tin cần bảo đảm test failure làm build thất bại, báo cáo được lưu, môi trường test có thể tái lập và artifact chỉ được phát hành sau khi quality gate đạt. Test xanh không chứng minh không còn lỗi, nhưng nó cung cấp bằng chứng tự động, lặp lại được rằng những hành vi quan trọng đã được kiểm tra trong phạm vi đã định.
