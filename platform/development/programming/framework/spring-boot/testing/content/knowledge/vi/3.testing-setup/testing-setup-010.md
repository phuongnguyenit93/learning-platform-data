# Đọc báo cáo lỗi, stack trace và xác định ca kiểm thử thực sự đã chạy trong Spring Boot

## 1. Vì sao không thể chỉ nhìn dòng BUILD SUCCESSFUL hay BUILD FAILED?

Kiểm thử tự động có giá trị khi chúng ta biết **test nào đã được chọn, test nào thật sự chạy, test nào bị bỏ qua và lỗi xảy ra ở bước nào**. Dòng `BUILD SUCCESSFUL` chỉ cho biết các tác vụ được yêu cầu kết thúc thành công theo cấu hình hiện tại; nó không tự chứng minh mọi ca kiểm thử trong repository đã chạy. Tương tự, `BUILD FAILED` không nhất thiết có nghĩa assertion của ứng dụng sai: build có thể thất bại khi biên dịch test, chuẩn bị database, khởi tạo Spring context hoặc tải dependency.

Với một lần chạy cụ thể, người đọc cần trả lời bốn câu hỏi:

1. **Đã gọi lệnh nào, ở module và môi trường nào?** Ví dụ `./gradlew test`, `./mvnw test`, `./mvnw verify`, hay một lệnh lọc riêng lớp/phương thức.
2. **Có bao nhiêu test được ghi nhận và trạng thái của từng ca là gì?** Tên lớp, tên method/lượt invocation, số pass, failure, error và skipped.
3. **Lỗi xảy ra lúc nào?** Trước khi JUnit khám phá test, trong setup/context, khi chạy assertion, hay trong cleanup?
4. **Bằng chứng dẫn đến nguyên nhân là gì?** Thông báo expected/actual, chuỗi `Caused by`, frame thuộc mã nguồn dự án và dữ liệu tái hiện.

Phân biệt năm mức độ: **có file test** → **task test được yêu cầu** → **test được JUnit khám phá** → **ca test được thực thi** → **ca test đạt**. Năm điều này không tương đương nhau.

## 2. Quy trình đọc kết quả kiểm thử có hệ thống

```text
Lệnh build / CI job
  └─ Biên dịch source, biên dịch test source
      └─ Gradle test task / Maven test goal
          └─ JUnit Platform tìm và chọn test
              ├─ Chạy test: PASS / FAILURE / ERROR
              ├─ Bỏ qua theo điều kiện: SKIPPED / ABORTED
              └─ Không khám phá hoặc bị lọc: không có lượt chạy
          └─ Console và các báo cáo HTML / XML / TXT
```

Đọc theo thứ tự **command → task/goal → report tổng hợp → test case cụ thể → stack trace → nguyên nhân**. Nếu bắt đầu từ một dòng exception ngẫu nhiên trong console, rất dễ kết luận nhầm một lỗi hạ tầng thành bug nghiệp vụ.

| Tín hiệu | Có thể kết luận | Không thể tự kết luận |
|---|---|---|
| Source và test source biên dịch thành công | Biên dịch không lỗi trong phạm vi đó | JUnit đã chạy test |
| Gradle task `:test` có report chứa testcase | Task đó có kết quả test được ghi nhận | Mọi suite của dự án đã chạy |
| Maven Surefire: `Tests run: 4` | Surefire ghi nhận bốn lượt của phạm vi đó | Failsafe integration tests đã chạy |
| `BUILD SUCCESSFUL` | Build đạt theo cấu hình và các task đã yêu cầu | Có test mới được thực thi ngay lần này |
| `BUILD FAILED` | Một tác vụ/goal không đạt | Chắc chắn là lỗi assertion |
| `skipped` | Test được ghi nhận là bỏ qua | Hành vi nghiệp vụ đã đúng |
| Một test không có tên trong report | Chưa có chứng cứ nó chạy ở report đang xem | Test chắc chắn không tồn tại |

## 3. Tìm báo cáo của Gradle

Trong dự án Spring Boot có Gradle wrapper, từ thư mục dự án chạy:

```bash
./gradlew test
```

Trên Windows PowerShell: `.\gradlew.bat test`.

Với test task tên `test` và cấu hình thông thường, đầu ra được tạo tại:

| Nơi xem | Thông tin cần đọc |
|---|---|
| `build/reports/tests/test/index.html` | Báo cáo HTML, danh sách test class/method, thống kê, failure và stack trace |
| `build/test-results/test/TEST-*.xml` | Báo cáo XML với testcase và trạng thái phục vụ CI |
| Console của `:test` | Task đã chạy hay `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`, `NO-SOURCE`; tóm tắt lỗi và link báo cáo |

Trong dự án nhiều module, các đường dẫn nằm trong thư mục của từng module. Nếu cấu hình task `integrationTest` hoặc `functionalTest`, tên report và kết quả thường theo task riêng; **đừng lấy report của `test` để kết luận task khác đã chạy**.

Chạy một lớp cụ thể:

```bash
./gradlew test --tests "com.example.testing.ShippingFeePolicyTest"
```

Chạy một phương thức:

```bash
./gradlew test --tests "com.example.testing.ShippingFeePolicyTest.atThresholdIsFree"
```

Đây là **bộ lọc yêu cầu chạy**, không tự chứng minh test đã được khám phá và thực thi. Trong dự án dùng JUnit Jupiter, Gradle test task cần cấu hình JUnit Platform phù hợp, thường là `useJUnitPlatform()`. Đọc report của đúng task mới có câu trả lời cuối cùng.

### Bằng chứng mới chạy hay kết quả được tái sử dụng?

- `UP-TO-DATE`: Gradle xác định output hiện có còn hợp lệ với input khai báo và không chạy lại task lần đó.
- `FROM-CACHE`: task nhận kết quả từ build cache.
- `SKIPPED` hoặc `NO-SOURCE`: task không thực hiện test vì điều kiện skip hoặc không có nguồn thích hợp.
- `BUILD SUCCESSFUL` sau các trạng thái trên **không có nghĩa test được chạy mới trong lần gọi đó**.

Nếu cần xem test được thực thi lại thay vì dùng output cũ, có thể dùng `./gradlew test --rerun-tasks`, kèm `--tests` nếu muốn lọc. Sau đó xác nhận task outcome và report của lượt chạy mới. Không nên xóa cả thư mục build nếu chỉ cần xác minh một lớp.

## 4. Tìm báo cáo của Maven

Với Maven wrapper:

```bash
./mvnw test
```

Trên Windows PowerShell: `.\mvnw.cmd test`.

Với Maven Surefire chạy unit tests trong pha `test`, các nơi thường dùng:

| Nơi xem | Thông tin cần đọc |
|---|---|
| `target/surefire-reports/TEST-*.xml` | Test suite, testcase, số lượt, failure/error/skipped |
| `target/surefire-reports/*.txt` | Tóm tắt và chi tiết từng lớp |
| Console Surefire | `Tests run`, `Failures`, `Errors`, `Skipped` và file report liên quan |

Chạy một lớp bằng Surefire:

```bash
./mvnw -Dtest=ShippingFeePolicyTest test
```

Nếu module có Maven Failsafe cho integration test, chúng thường thuộc các pha `integration-test` và `verify`, tạo báo cáo trong `target/failsafe-reports/`. Lệnh `./mvnw test` chạy thành công **chưa chứng minh** integration test do Failsafe quản lý đã chạy; muốn xác minh, xem cấu hình thực và chạy đến `verify` khi phù hợp.

Trong dự án Maven nhiều module, mỗi module có thư mục `target/` của riêng mình. Kiểm tra module, commit, CI job và lần chạy trước khi đọc file. `-Dtest=...` lọc phạm vi Surefire; `-DskipTests` thường bỏ qua việc chạy test, còn `-Dmaven.test.skip=true` có thể bỏ qua cả biên dịch test. Cách plugin phản ứng còn phụ thuộc cấu hình dự án, nên lấy log làm bằng chứng.

## 5. Ví dụ Java 17+ có chủ đích tạo một assertion failure

Giả sử phí giao hàng: đơn hàng có tổng tiền **từ 500.000 đồng trở lên** được miễn phí; dưới ngưỡng tính 30.000 đồng; tổng tiền âm bị từ chối.

Mã service sau cố ý có bug `>` thay vì `>=`. Đây là mã Java hoàn chỉnh trong một dự án Spring Boot có Java 17+ và `spring-boot-starter-test`.

Tệp `src/main/java/com/example/testing/ShippingFeePolicy.java`:

```java
package com.example.testing;

public final class ShippingFeePolicy {
    public int fee(int subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be nonnegative");
        }
        return subtotal > 500_000 ? 0 : 30_000; // Bug: không miễn phí tại ngưỡng
    }
}
```

Tệp `src/test/java/com/example/testing/ShippingFeePolicyTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void belowThresholdIsCharged() {
        assertEquals(30_000, policy.fee(499_999));
    }

    @Test
    void atThresholdIsFree() {
        assertEquals(0, policy.fee(500_000));
    }

    @Test
    void aboveThresholdIsFree() {
        assertEquals(0, policy.fee(500_001));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> policy.fee(-1));
    }
}
```

Unit test tạo `ShippingFeePolicy` trực tiếp, không khởi động Spring context. Nếu JUnit Jupiter được cấu hình và chạy đủ bốn ca, **ba ca đạt; ca `atThresholdIsFree` thất bại**. Với đầu vào 500.000, service trả 30.000 còn test mong 0.

Dòng console Surefire minh họa có thể cho thấy:

```text
Tests run: 4, Failures: 1, Errors: 0, Skipped: 0
com.example.testing.ShippingFeePolicyTest.atThresholdIsFree
org.opentest4j.AssertionFailedError: expected: <0> but was: <30000>
```

Stack trace rút gọn **minh họa**, không phải log từ một build thực:

```text
org.opentest4j.AssertionFailedError: expected: <0> but was: <30000>
    at org.junit.jupiter.api.AssertionFailureBuilder.build(...)
    at org.junit.jupiter.api.AssertEquals.assertEquals(...)
    at com.example.testing.ShippingFeePolicyTest.atThresholdIsFree(
        ShippingFeePolicyTest.java:<line>)
```

Các dấu `...` và `<line>` biểu thị phần được rút gọn. Số dòng, thứ tự và lớp JUnit nội bộ thay đổi theo version và tệp thực tế.

Cách đọc:
- **Ca lỗi:** `ShippingFeePolicyTest.atThresholdIsFree`.
- **Expected:** 0; **actual:** 30.000. Đây là sự khác biệt trong assertion, không phải lỗi tạo Spring bean.
- **Frame test:** chỉ về dòng `assertEquals`; đọc giá trị `fee(500_000)` rồi lần theo logic service.
- **Nguyên nhân:** điều kiện `subtotal > 500_000` không bao gồm đúng ngưỡng 500.000.
- **Phạm vi thực thi:** nếu report đúng ghi bốn test, ba pass và một failure; không suy ra các test ở lớp/module khác đã chạy.

Sửa production thành:

```java
return subtotal >= 500_000 ? 0 : 30_000;
```

Với quy tắc đã nêu, bốn assertion sẽ đúng trên implementation mới. Nhưng trong báo cáo dự án thật, chỉ khẳng định `PASS` sau khi chạy test và đọc report mới.

## 6. Đọc XML để xác định ca được ghi nhận

Một file JUnit-style XML minh họa có cấu trúc:

```xml
<testsuite name="com.example.testing.ShippingFeePolicyTest"
           tests="4" failures="1" errors="0" skipped="0">
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="belowThresholdIsCharged"/>
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="atThresholdIsFree">
    <failure type="org.opentest4j.AssertionFailedError"
             message="expected: &lt;0&gt; but was: &lt;30000&gt;"/>
  </testcase>
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="aboveThresholdIsFree"/>
  <testcase classname="com.example.testing.ShippingFeePolicyTest"
            name="negativeSubtotalIsRejected"/>
</testsuite>
```

Đây là **mẫu để tập đọc cấu trúc XML**, không phải nội dung copy từ Maven/Gradle đang chạy.

- `testsuite`: nhóm test mà runner báo cáo, thường tương ứng class.
- `tests`: tổng số lượt test của suite trong report.
- `failures`: số lượt thất bại do assertion hoặc được runner xếp vào nhóm failure.
- `errors`: các lỗi khác nếu runner có phân biệt; phải xem chi tiết từng testcase vì cách phân loại có thể khác nhau.
- `skipped`: số lượt được đánh dấu bỏ qua.
- `testcase classname + name`: định danh lớp và lượt test có trong report.
- Các phần tử con `failure`, `error` hoặc `skipped` cho biết trạng thái; không có chúng trong một `testcase` hoàn chỉnh thường là pass.

**Đừng đếm số method Java để suy ra số lượt chạy.** `@ParameterizedTest` và `@RepeatedTest` tạo nhiều lượt cho một phương thức; `@Nested` có tên class lồng nhau; `@DisplayName` có thể khác tên method. Khi dùng `@TestFactory` với dynamic tests, các lượt cũng được runner báo cáo theo cách riêng. Hãy xem từng testcase/invocation trong report của đúng lượt chạy.

Nếu một test **không xuất hiện** trong report, nó có thể bị bộ lọc loại bỏ, không được JUnit khám phá, nằm trong task khác hoặc report đã chọn sai. Nếu test xuất hiện với `skipped`, nó **không được coi là đã thực thi thành công**.

## 7. Đọc stack trace: từ lỗi trên cùng đến nguyên nhân trong source

Stack trace Java có thể gồm:
- **Tên exception và message**: `AssertionFailedError`, `NullPointerException`, `IllegalStateException`, `BeanCreationException`.
- Các dòng **`at ...`**: thứ tự gọi hàm, nhiều khi kèm `SomeFile.java:42`.
- **`Caused by:`**: exception nguyên nhân bị bọc qua các tầng.
- **`Suppressed:`**: exception bổ sung (ví dụ lỗi lúc đóng tài nguyên), chưa chắc là nguyên nhân chính.

Thực hiện theo trình tự:

1. Từ report, tìm đúng class/method báo failure; đừng chọn exception bất kỳ từ log của test khác.
2. Đọc exception đầu tiên và thông điệp. `expected/actual` thường là assertion mismatch, còn `Failed to load ApplicationContext` chỉ ra setup Spring.
3. Tìm `Caused by` khi có: đi sâu tới nguyên nhân có thông tin hành động được. Nguyên nhân quan trọng thường gần cuối chuỗi nhưng không nhất thiết là dòng cuối cùng.
4. Xác định frame thuộc mã dự án (`com.example....`) thay vì chỉ nhìn hàng chục frame của JUnit, Spring, Gradle hoặc Surefire.
5. Mở đúng version của file được nhắc ở frame và xem dữ liệu/fixture. Frame ở test thường là **chỗ phát hiện sai lệch**; frame trong service hoặc repository có thể là nơi exception được ném.
6. Kiểm tra pha thất bại: compile, context initialization, setup, test body, teardown hay hạ tầng. Nếu lỗi trước test body, chưa thể khẳng định phương thức nghiệp vụ đã được kiểm tra.
7. Sửa nguyên nhân, chạy lại cùng ca và sau đó các test liên quan; dùng kết quả mới để xác nhận.

### 7.1. Assertion failure

```text
org.opentest4j.AssertionFailedError:
expected: <0> but was: <30000>
```

Tập trung vào **đầu vào tại assertion**, hợp đồng mong đợi, đường đi production và giá trị thực tế. Không đổi `expected` theo output sai chỉ để test xanh.

### 7.2. Spring context không khởi tạo

Một trace minh họa:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext
    ...
Caused by: org.springframework.beans.factory.UnsatisfiedDependencyException:
    Error creating bean with name 'orderService'
    ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
    No qualifying bean of type 'com.example.payment.PaymentClient' available
```

Lỗi gốc gợi ý thiếu bean `PaymentClient` cần thiết để tạo `orderService`. Một test `@SpringBootTest` hay slice test có thể fail **trước khi vào phương thức `@Test`**. Cần kiểm tra component scan, profile, bean configuration, mock/test bean phù hợp với loại test và phiên bản Spring Boot. Không coi trace này là bằng chứng logic `orderService` trả kết quả sai.

Nếu nhiều test cùng báo lỗi nạp context, tìm **trace đầu tiên với `Caused by` có ích**; những lần sau có thể bị ảnh hưởng bởi cơ chế cache/context failure handling.

### 7.3. Exception ném từ mã ứng dụng

```text
java.lang.NullPointerException: ...
    at com.example.orders.OrderService.total(OrderService.java:42)
    at com.example.orders.OrderServiceTest.calculatesTotal(OrderServiceTest.java:27)
```

Frame `OrderService.java:42` trỏ nơi exception được ném; frame của test cho biết tình huống gọi. Xem object nào null: input, mock, mapper hay dependency thiếu. Không suy ra chỉ từ tên exception. Ngược lại, nếu test dùng `assertThrows` và bắt **đúng ngoại lệ được yêu cầu**, thì exception đó là bằng chứng của một test pass, không phải test fail.

### 7.4. Lỗi biên dịch, classpath và môi trường

`compileTestJava` thất bại, `NoClassDefFoundError`, `ClassNotFoundException`, timeout database, `Connection refused`, port trùng, thiếu cấu hình hoặc dependency không tải được đều cần phân tích riêng. Nếu lỗi xảy ra trước lúc JUnit khám phá, chưa có bằng chứng ca kiểm thử chạy. Một test fail vì database không sẵn sàng cũng không tự chứng minh quy tắc nghiệp vụ sai.

## 8. Cách chứng minh ca test thực sự đã chạy

Dùng bộ đối chiếu sau trong mỗi lần phân tích:

1. **Lệnh và phạm vi:** `./gradlew :orders:test --tests "com.example.testing.ShippingFeePolicyTest"` chỉ nhắm task test của module orders và bộ lọc đó; `./gradlew test` ở root có thể có phạm vi khác.
2. **Outcome thực tế của task/goal:** task đã chạy test, dùng cache, skip, không có source hay thất bại trước runner?
3. **Report thuộc đúng lần chạy:** thời gian/report artifact, module, job, branch/commit, tên task và môi trường.
4. **Danh sách testcase:** có lớp/method/invocation cần kiểm tra trong report không, trạng thái chính xác là gì?
5. **Bộ lọc và điều kiện:** `--tests`, `-Dtest`, `@Tag`, `@Disabled`, JUnit conditions, include/exclude patterns, name convention, engine.
6. **Số liệu khớp phạm vi:** có bao nhiêu lượt pass, failure/error, skipped và test không được chọn?
7. **Yêu cầu thực thi mới:** nếu đang xem output được cache, chạy lại có kiểm soát và xác nhận task + report mới trước khi phát biểu “đã chạy lại”.

Ví dụ: `BUILD SUCCESSFUL` kèm `:test UP-TO-DATE` có thể là build thành công nhờ kết quả trước đó; không nên báo “tất cả test vừa được chạy mới”. Ngược lại, `Tests run: 0` hay `No tests to run` không phải bằng chứng hành vi ứng dụng đã được test thành công.

Với Maven, nên kiểm tra Surefire/Failsafe và các thông báo skip. Với Gradle, cấu hình JUnit Platform và các test task khác nhau phải được đọc từ project hiện tại. **Tên file `*Test.java` hiện diện trong source không chứng minh JUnit đã phát hiện nó.**

## 9. Bảng phân biệt nhanh các tình huống thường gặp

| Tình huống | Có thể đã xảy ra | Bước kiểm tra tiếp theo |
|---|---|---|
| Console báo `BUILD SUCCESSFUL`, không thấy test | Không có test được chọn, task bị skip hoặc dùng cache | Xem task outcome và report/testcase |
| Gradle `UP-TO-DATE` hoặc `FROM-CACHE` | Dùng lại kết quả | Dùng `--rerun-tasks` nếu cần bằng chứng thực thi mới |
| Maven `Tests run: 0` | Không khám phá/không chọn được test | Kiểm tra filter, plugin, naming, JUnit engine, module |
| Có `@Disabled` hoặc assumption | Test có thể được ghi là skipped/aborted | Đọc lý do và không tính như pass thực thi |
| Lọc `-Dtest` hoặc `--tests` | Chỉ một phần lớp/phương thức được chọn | Đối chiếu từng testcase của bộ lọc |
| Test biên dịch lỗi | JUnit chưa bắt đầu chạy ca đó | Sửa compile/classpath trước |
| `Failed to load ApplicationContext` | Bean/profile/test config lỗi | Tìm `Caused by` thực tế và kiểm tra setup |
| `AssertionFailedError` | Expected khác actual | Kiểm tra input, hợp đồng, code path |
| Test unit xanh, API vẫn sai | Test không đi qua MVC/Security/JSON | Thêm test tại đúng ranh giới xảy ra lỗi |
| `mvn test` xanh, integration test thiếu | Failsafe/suite khác chưa chạy | Kiểm tra cấu hình, `verify`, report riêng |
| Số lượt test khác số method | Parameterized/repeated/dynamic/nested | Xem từng invocation/testcase trong report |
| Nhiều test fail cùng exception | Setup/context chung hoặc phụ thuộc ngoài | Nhóm lỗi theo root cause, đọc lần đầu gây fail |

### Lưu ý đặc thù Spring Boot

- `@SpringBootTest` thường nạp application context, nhưng mặc định **không tự chạy HTTP server thật**. Muốn test HTTP server ở cổng ngẫu nhiên, cần cấu hình `webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT`.
- `@WebMvcTest` là MVC slice; thiếu bean collaborator có thể gây lỗi nạp context trong test slice, không có nghĩa production controller chắc chắn sai.
- `@DataJpaTest` và test database có thể dùng môi trường dữ liệu khác production. Với bug liên quan SQL/transaction, kiểm tra hệ DB thực sự được dùng trong test.
- Test Spring context có thể fail vì profile/test property/bean khác môi trường triển khai. Nên phân biệt lỗi cấu hình test với bug ứng dụng trước khi chỉnh production.

## 10. Đọc CI report và viết báo cáo lỗi có bằng chứng

Khi CI chạy nhiều job hoặc nhiều Java version, gắn kết quả với **commit, job, module, lệnh chạy, JDK, profile và artifact**. Một report của job unit tests không chứng minh job integration tests đã chạy. Report cũ còn trong workspace có thể gây nhầm; ưu tiên report được xuất từ đúng CI run và đối chiếu timestamp khi cần.

Nếu nhiều test fail:
1. Nhóm theo assertion nghiệp vụ, context startup, database/network, timeout, classpath hoặc cấu hình.
2. Tìm root cause chung, đặc biệt khi nhiều test cùng không tạo được ApplicationContext.
3. Phân biệt test fail trực tiếp với lỗi thứ cấp do setup.
4. Sửa nguyên nhân và chạy lại ca/lớp rồi toàn bộ suite chịu ảnh hưởng.
5. Tránh “chữa” CI đỏ bằng việc xóa test, bỏ assertion, vô hiệu hóa test hoặc retry không giới hạn.

Một mẫu báo cáo **minh họa**:

> CI job `unit-tests` chạy `./gradlew :orders:test --tests "com.example.testing.ShippingFeePolicyTest"` cho commit được nêu trong job. Report `:orders:test` ghi 4 test: 3 pass, 1 failure, 0 skipped. Test `atThresholdIsFree` mong 0 nhưng thực tế là 30000. Dòng `ShippingFeePolicy.fee(500_000)` dùng `>` thay vì `>=`. Đề xuất sửa điều kiện, chạy lại đúng test và suite liên quan; chưa tuyên bố fix đạt cho đến khi có kết quả chạy mới.

Khi viết báo cáo thật, chỉ nêu thông tin đã thấy trong log, XML và code của đúng phiên bản. Đừng sao chép số liệu minh họa hoặc khẳng định test pass nếu chưa có lần chạy thực tế.

## 11. Checklist trước khi kết luận kết quả kiểm thử

- [ ] Đã xác định đúng lệnh, module, commit, môi trường, JDK và CI job của lần chạy.
- [ ] Đã phân biệt compile/test discovery/setup với thực thi test body.
- [ ] Đã mở report HTML/XML/TXT đúng task, đúng module và đúng lần chạy.
- [ ] Đã đọc số tests, failures, errors, skipped; không chỉ nhìn `BUILD FAILED`/`BUILD SUCCESSFUL`.
- [ ] Đã xác định `classname` + `testcase` + invocation và trạng thái ca mục tiêu.
- [ ] Đã kiểm tra filter, tag, disabled, cache, skip và task riêng để biết test nào thực sự chạy.
- [ ] Đã đọc exception message, `Caused by`, frame trong source và dòng assertion.
- [ ] Đã so sánh expected/actual hoặc trạng thái/side effect với hợp đồng cần kiểm tra.
- [ ] Sau fix, đã chạy lại ca lỗi và suite liên quan; phân biệt kết quả thật với dự đoán.
- [ ] Báo cáo nêu rõ ranh giới đã được xác minh và những suite chưa chạy hoặc test đang skipped.

**Kết luận:** Phân tích test Spring Boot đúng cách là nối **lệnh chạy → task/goal → test case + trạng thái → stack trace → nguyên nhân trong source**. Đừng nhầm assertion failure với Spring ApplicationContext failure, hoặc build xanh với việc tất cả test vừa được thực thi. Bằng chứng đáng tin luôn có **tên ca, kết quả, phạm vi và lần chạy cụ thể**.