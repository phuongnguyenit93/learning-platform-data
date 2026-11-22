# Độ bao phủ mã nguồn, độ mạnh của assertion và giới hạn của các con số

Trong chiến lược kiểm thử Spring Boot, **code coverage** cho biết phần mã nào đã được chạy khi test thực thi; **assertion** cho biết test đã kiểm tra điều gì về kết quả quan sát được; và **độ tin cậy của bộ test** còn phụ thuộc vào việc những tình huống, quy tắc nghiệp vụ và lỗi quan trọng có được kiểm chứng hay không. Ba khía cạnh liên quan nhưng không thể quy đổi trực tiếp cho nhau.

Một dự án có 90% line coverage vẫn có thể tính sai tiền. Một test có 100% branch coverage vẫn có thể không phát hiện phản hồi HTTP sai. Ngược lại, một bộ test nhỏ nhưng kiểm tra chính xác điều kiện biên và hợp đồng nghiệp vụ quan trọng có thể giúp phát hiện lỗi hiệu quả hơn một bộ test chạy nhiều dòng nhưng ít assertion có ý nghĩa.

## 1. Ba câu hỏi phải tách riêng

| Câu hỏi | Loại bằng chứng | Ví dụ | Không được suy ra |
| --- | --- | --- | --- |
| **Mã nào đã được thực thi?** | Coverage: line, instruction, branch, method… | JaCoCo ghi nhận 40/50 dòng có lệnh được chạy | 40 dòng đó tính toán đúng |
| **Kết quả nào đã được xác minh?** | Assertion: giá trị, exception, trạng thái, hiệu ứng phụ, hợp đồng HTTP | `assertEquals(0, fee(200_000))` | Tất cả tổ hợp đầu vào khác đều đúng |
| **Test có bắt được các lỗi thực tế quan trọng không?** | Chất lượng tình huống, độ mạnh oracle, mutation testing, integration test, kiểm thử biên | Đổi phí miễn phí thành 5.000 và test báo đỏ | Mọi lỗi trong tương lai đều sẽ bị phát hiện |

**Test oracle** là cơ sở để xác định đúng/sai: yêu cầu nghiệp vụ, hợp đồng API, invariant hoặc kết quả được tính độc lập. Một assertion chỉ mạnh khi **kỳ vọng của nó đúng** và liên quan đến điều cần bảo vệ. Viết `assertEquals(actual, actual)` luôn xanh nhưng không xác minh gì; chép nguyên công thức của production code vào phần expected cũng có thể sao chép chính lỗi đó.

## 2. Coverage đo điều gì?

Coverage được thu thập bằng cách ghi nhận mã thực thi trong lúc chạy một hoặc nhiều test. Với dự án Java/Spring Boot dùng Gradle, **JaCoCo** là công cụ phổ biến để đo bytecode đã được thực thi và dựng báo cáo theo class, package và source line.

| Chỉ số | Ý nghĩa thực tế | Giới hạn |
| --- | --- | --- |
| **Instruction coverage** | Tỷ lệ instruction bytecode được chạy | Dễ tăng nhờ nhiều lệnh khởi tạo, chưa nói gì về expected result |
| **Line coverage** | Tỷ lệ dòng nguồn chứa lệnh đã được chạm tới theo dữ liệu bytecode | Một dòng có nhiều biểu thức/nhánh có thể chỉ được thực hiện một phần |
| **Branch coverage** | Tỷ lệ nhánh quyết định do công cụ nhận diện được thực thi (như `if`, `switch`) | Không tương đương mọi đường chạy, mọi tổ hợp điều kiện hoặc mọi trạng thái dữ liệu |
| **Method/class coverage** | Method/class nào có instruction được thực thi | “Đã gọi” chưa nói hành vi đúng hay đầu ra được kiểm tra |
| **Complexity / missed complexity** | Gợi ý những quyết định logic còn thiếu đường kiểm thử | Không phải điểm số chất lượng nghiệp vụ |

Công thức diễn giải ở phạm vi một chỉ số là:

```text
coverage (%) = covered units / total measurable units × 100
```

Ví dụ, có 18 nhánh được công cụ tính, test chạy qua 15 nhánh: branch coverage = 15 / 18 × 100% ≈ 83,33%. Khi đọc tỷ lệ phải ghi rõ **đơn vị đo, phạm vi mã và bộ test** đã tạo ra dữ liệu. Không được so sánh 80% branch coverage với 80% line coverage như hai thước đo cùng ý nghĩa.

**Chi tiết quan trọng về JaCoCo:** line coverage được suy ra từ instruction bytecode ánh xạ về dòng nguồn; một dòng có thể được đánh dấu “partially covered”. Branch counter chủ yếu phản ánh các lệnh điều kiện và `switch` do compiler sinh ra; **exception handling không được JaCoCo tính như branch**. Các lời gọi bị lỗi, tình huống `catch`, transaction rollback hay đường xử lý ở môi trường khác vẫn cần test có chủ đích.

### Vì sao 100% line hoặc branch coverage vẫn chưa đủ?

Hãy xét:

```java
if (premiumUser && cartTotal >= 500_000) {
    return 0;
}
return 30_000;
```

Ngay cả khi báo cáo cho thấy các nhánh đã được chạy, bạn vẫn phải xét các tổ hợp như `premiumUser=false`, `cartTotal=500_000`; `premiumUser=true`, `cartTotal=499_999`; và `premiumUser=true`, `cartTotal=500_000`. Do short-circuit, những tổ hợp và ranh giới có thể cho kết quả khác nhau dù cùng đi đến một nhánh cuối. Branch coverage không cam kết đã kiểm tra mọi tổ hợp boolean, mọi path qua nhiều quyết định, mọi giá trị biên hay điều kiện bên ngoài.

Coverage càng không đo **assertion quality**: mã chạy một lần không buộc test phải so sánh kết quả của lần chạy đó.

## 3. Ví dụ phản chứng: chạy hết nhánh nhưng assertion yếu

Quy tắc nghiệp vụ giả định cho phí giao hàng:

- Đơn có giá trị âm phải bị từ chối bằng `IllegalArgumentException`.
- Đơn có giá trị **từ 200.000 trở lên** được miễn phí giao hàng (`0`).
- Đơn hợp lệ **dưới 200.000** có phí cố định `30.000`.
- Đơn vị là đồng nguyên; không có thuế, tỷ giá, voucher hoặc chương trình ưu đãi khác trong ví dụ.

Triển khai đúng:

```java
public int fee(int orderValue) {
    if (orderValue < 0) {
        throw new IllegalArgumentException("orderValue must be non-negative");
    }
    if (orderValue >= 200_000) {
        return 0;
    }
    return 30_000;
}
```

Một test yếu có thể gọi cả ba đường đi nhưng chỉ hỏi “phí không âm”:

```java
assertTrue(service.fee(199_999) >= 0);
assertTrue(service.fee(200_000) >= 0);
assertThrows(IllegalArgumentException.class, () -> service.fee(-1));
```

Đối với riêng method này, các lệnh và cả hai hướng của mỗi `if` đều có cơ hội được thực thi. Một báo cáo JaCoCo có thể hiển thị **100% line và branch coverage** cho lớp chứa method. Tuy nhiên nếu lập trình viên vô tình sửa nhánh miễn phí từ `return 0;` thành `return 5_000;`, tất cả assertion ở trên **vẫn xanh**: phí 5.000 cũng là số không âm.

Test có coverage mạnh về “đã chạy” nhưng oracle quá yếu về “đã đúng”. Để chặn lỗi, hãy assert kết quả từ quy tắc độc lập:

```java
assertEquals(30_000, service.fee(199_999));
assertEquals(0, service.fee(200_000));
```

Cặp giá trị **sát ranh giới** còn phát hiện lỗi sửa `>= 200_000` thành `> 200_000` — thứ có thể thoát khỏi test chỉ dùng 100.000 và 300.000.

## 4. Ví dụ chạy được với Java 17+, Spring Boot, JUnit và JaCoCo

Đây là **dự án ví dụ độc lập**, dùng Spring Boot 3.3.x, Gradle Groovy DSL và Java 17+. Có thể đặt các tệp dưới đây vào một dự án Gradle có Wrapper tương thích với Java 17. Các class cùng package `com.example.coverage`; test unit tạo service trực tiếp nên không khởi động Spring context.

Cấu trúc:

```text
settings.gradle
build.gradle
src/main/java/com/example/coverage/CoverageApplication.java
src/main/java/com/example/coverage/ShippingFeeService.java
src/test/java/com/example/coverage/ShippingFeeWeakTest.java
src/test/java/com/example/coverage/ShippingFeeStrongTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'coverage-evidence'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'jacoco'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

tasks.named('jacocoTestReport') {
    dependsOn(tasks.named('test'))
    reports {
        html.required = true
        xml.required = true
    }
}
```

Plugin `jacoco` gắn thu thập coverage cho task `test`. `jacocoTestReport` tạo báo cáo từ dữ liệu thực thi của test, còn khai báo `dependsOn(test)` đảm bảo test được thực hiện trước khi sinh report. Cấu hình không thiết lập ngưỡng chất lượng: **báo cáo phần trăm chỉ là quan sát**, không phải một phép kiểm chứng business rule.

**`src/main/java/com/example/coverage/CoverageApplication.java`**

```java
package com.example.coverage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CoverageApplication {
    public static void main(String[] args) {
        SpringApplication.run(CoverageApplication.class, args);
    }
}
```

**`src/main/java/com/example/coverage/ShippingFeeService.java`**

```java
package com.example.coverage;

import org.springframework.stereotype.Service;

@Service
public class ShippingFeeService {
    public int fee(int orderValue) {
        if (orderValue < 0) {
            throw new IllegalArgumentException(
                    "orderValue must be non-negative");
        }
        if (orderValue >= 200_000) {
            return 0;
        }
        return 30_000;
    }
}
```

**`src/test/java/com/example/coverage/ShippingFeeWeakTest.java`**

```java
package com.example.coverage;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShippingFeeWeakTest {
    private final ShippingFeeService service = new ShippingFeeService();

    @Test
    void visitsAllOutcomesButChecksLittle() {
        assertTrue(service.fee(199_999) >= 0);
        assertTrue(service.fee(200_000) >= 0);
        assertThrows(IllegalArgumentException.class,
                () -> service.fee(-1));
    }
}
```

**`src/test/java/com/example/coverage/ShippingFeeStrongTest.java`**

```java
package com.example.coverage;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeeStrongTest {
    private final ShippingFeeService service = new ShippingFeeService();

    @Test
    void paysTheFixedFeeBelowTheBoundary() {
        assertEquals(30_000, service.fee(0));
        assertEquals(30_000, service.fee(199_999));
    }

    @Test
    void isFreeAtAndAboveTheBoundary() {
        assertEquals(0, service.fee(200_000));
        assertEquals(0, service.fee(200_001));
    }

    @Test
    void rejectsNegativeOrderValues() {
        assertThrows(IllegalArgumentException.class,
                () -> service.fee(-1));
    }
}
```

Các expected value được suy ra từ hợp đồng nêu trước code. Test mạnh không chỉ quan tâm “có exception” hay “trả số không âm” mà bảo vệ các kết quả cụ thể và ngưỡng `200_000`.

### 4.1. Chạy test và đọc kết quả coverage

Trong thư mục dự án có Gradle Wrapper:

```bash
./gradlew clean test --tests com.example.coverage.ShippingFeeWeakTest jacocoTestReport
```

Trên Windows, thay `./gradlew` bằng `gradlew.bat`. Mở báo cáo HTML:

```text
build/reports/jacoco/test/html/index.html
```

Đi vào package `com.example.coverage` và chọn `ShippingFeeService`. Với code không sửa, test yếu chạm đủ các đường đi của service, nên lớp này có thể đạt coverage rất cao, kể cả 100% line và branch. **Đừng lấy số phần trăm tổng dự án thay cho số của service:** `CoverageApplication.main` có thể chưa chạy, nên tỷ lệ toàn dự án khác tỷ lệ của service.

Sau đó chạy đầy đủ:

```bash
./gradlew clean test jacocoTestReport
```

Bộ test chuẩn dự kiến xanh với code gốc. File XML thường nằm tại:

```text
build/reports/jacoco/test/jacocoTestReport.xml
```

Để tự kiểm chứng độ yếu của assertion, **trong bản thử nghiệm**, đổi duy nhất `return 0;` của nhánh miễn phí thành `return 5_000;`, rồi chạy riêng test yếu và test mạnh:

```bash
./gradlew test --tests com.example.coverage.ShippingFeeWeakTest
./gradlew test --tests com.example.coverage.ShippingFeeStrongTest
```

Kỳ vọng logic: test yếu vẫn PASS vì `5_000 >= 0`; test mạnh FAIL ở `assertEquals(0, service.fee(200_000))`. Hãy hoàn nguyên `return 0;` sau thí nghiệm. Đây là **dự đoán từ mã mẫu**, không phải log chạy thực tế được trích dẫn. Muốn đo chính xác, cần tự chạy test bằng toolchain và dependencies tương ứng.

## 5. Đọc báo cáo coverage đúng cách trong ứng dụng Spring Boot

Báo cáo JaCoCo hiển thị số instruction/line/branch đã cover hoặc miss, thường phân theo package/class/method; màu xanh biểu thị đã cover, đỏ là chưa cover, vàng thường là một phần. Dùng bản HTML để tìm khu vực rủi ro cao còn bỏ sót, chẳng hạn:

- Nhánh `if` kiểm tra quyền truy cập, eligibility, tồn kho, định giá hoặc giới hạn giao dịch.
- Đường trả lỗi, retry, timeout, fallback, rollback, xử lý duplicate và các tình huống dữ liệu không hợp lệ.
- Điều kiện biên `<`, `<=`, `>=`, `>` và tổ hợp nhiều trạng thái.
- Khu vực quyết định tính đúng của dữ liệu lưu trữ hoặc phản hồi API.

**Màu xanh không có nghĩa assertion đạt yêu cầu**. Một dòng được thực thi trong lúc Spring dựng bean, thực hiện constructor hoặc gọi vào code bởi một test không có assertion vẫn góp vào số đo. Trên Spring Boot, `@SpringBootTest` có thể khởi tạo nhiều bean và làm tăng coverage trong quá trình startup; từ đó **không thể suy ra** các API/transaction đã được xác minh.

Coverage cũng phụ thuộc vào phạm vi quan sát:

1. **Test task nào chạy?** Unit test, integration test ở task riêng, test theo profile hoặc test bị exclude có thể sinh dữ liệu khác nhau. Báo cáo của chỉ `test` không tự bao gồm một task `integrationTest` riêng chưa được hợp nhất execution data.
2. **Mã nào được tính?** Các class bị exclude, code được sinh tự động, Lombok, adapter hoặc cấu hình instrumentation khác nhau có thể thay đổi mẫu số. So sánh hai lần đo cần giữ nguyên quy tắc tính.
3. **Chạy ở đâu và với cấu hình nào?** Test dùng H2 hay Testcontainers, mock hay dependency thật, profile `test` hay `prod` quyết định đường code nào được thực thi.
4. **Cơ chế chạy nào được kiểm tra?** Unit test có thể phủ logic service nhưng bỏ qua JSON serialization, Spring Security filter chain, transaction, SQL và message broker.
5. **Test fail thì sao?** Coverage từ những lệnh đã chạy không thay thế trạng thái PASS của test. Một build có báo cáo đẹp nhưng assertion fail vẫn là build thất bại về correctness.

Đọc report bằng các câu hỏi cụ thể: dòng/nhánh nào chưa thực thi, lỗi có thể ẩn ở đó là gì, tình huống test nào sẽ kích hoạt, và sau khi chạy có assertion kiểm tra hành vi mong đợi chưa?

## 6. Độ mạnh của assertion: kiểm tra điều hệ thống phải bảo đảm

Một assertion có giá trị cần bốn thành phần:

1. **Kịch bản xác định:** đầu vào, trạng thái ban đầu, điều kiện và dependency quan trọng.
2. **Kết quả kỳ vọng độc lập:** lấy từ yêu cầu, bảng quyết định, hợp đồng API hoặc invariant đã được duyệt.
3. **Quan sát phù hợp:** giá trị trả về, HTTP status/body, thay đổi DB, event phát ra, exception được mô tả hoặc tác động quan trọng khác.
4. **Khả năng phân biệt sai/đúng:** nếu cài đặt bị lỗi hợp lý, test phải có cơ hội báo đỏ.

So sánh các kiểu assertion:

| Assertion | Độ mạnh trong kịch bản tính phí | Vấn đề / điều được bảo vệ |
| --- | --- | --- |
| `assertNotNull(service)` | Thấp | Chỉ chứng minh reference có đối tượng; không gọi nghiệp vụ |
| `assertDoesNotThrow(() -> service.fee(200_000))` | Thấp | Code có thể trả 5.000 hay 30.000 mà vẫn qua |
| `assertTrue(service.fee(200_000) >= 0)` | Thấp | Không phân biệt miễn phí và tính phí sai |
| `assertEquals(0, service.fee(200_000))` | Mạnh cho quy tắc cụ thể | Bảo vệ phí bằng 0 tại đúng ranh giới |
| `assertThrows(IllegalArgumentException.class, () -> service.fee(-1))` | Mạnh cho loại lỗi được yêu cầu | Chưa kiểm tra message hay ánh xạ thành HTTP 400 nếu API quy định chúng |
| `assertEquals(expectedSavedState, repository.findById(id))` | Mạnh cho persistence nếu setup đúng | Phải so sánh với expected state độc lập, không chỉ `isPresent()` |

Với HTTP API, assertion nên kiểm tra thứ client phụ thuộc vào: status code, schema/body, header quan trọng và side effect. Với Spring MVC có thể dùng `MockMvc`; với web server thật có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng HTTP client. `MockMvc` thường kiểm tra lớp MVC mà không khởi chạy một HTTP server thực; test với random port xác nhận thêm lớp vận chuyển HTTP trong môi trường test đó.

Với repository và transaction, hãy assert **state trước/sau** hoặc sự bất biến khi lỗi; kiểm tra mỗi `verify(repository).save(...)` chỉ chứng minh một lời gọi tương tác trong phạm vi mock, chưa chứng minh dữ liệu thực được commit. Trong code bất đồng bộ, cần chờ một điều kiện có giới hạn và assertion sau khi điều kiện đạt, tránh `Thread.sleep` tùy tiện hoặc assertion trước khi sự kiện hoàn tất.

**Chú ý:** Assertion “mạnh” nhưng expected **sai yêu cầu** sẽ biến bug thành test xanh. Review test cần đọc cả **đầu vào và expected**, không chỉ đếm số assertion.

## 7. Mutation testing: đo khả năng bộ test phát hiện thay đổi sai

**Mutation testing** chủ động tạo ra những thay đổi nhỏ (mutant) trong production code — ví dụ đổi `>=` thành `>`, đổi số 0 thành số khác, đảo điều kiện, đổi phép toán — rồi chạy test để xem test có phát hiện sự sai khác hay không.

Một mutant thường được phân loại:

- **Killed:** các test liên quan báo lỗi khi mutant được áp dụng; đây là dấu hiệu bộ test có khả năng phân biệt thay đổi đó.
- **Survived:** test vẫn xanh; cần xem thiếu tình huống, assertion yếu hay mutant thực ra tương đương về hành vi quan sát.
- **No coverage:** mutant nằm tại mã chưa được test chạy tới.
- **Timeout/không thể thực thi/lỗi khác:** phải đọc quy tắc phân loại của công cụ; không gộp bừa vào kết luận “test mạnh”.

Trong Java có thể tìm hiểu **PIT (PITest)** để tự động hóa mutation testing. Với ví dụ `ShippingFeeService`, mutant đổi `return 0;` thành `return 5_000;` sống sót trước `ShippingFeeWeakTest` nhưng bị `ShippingFeeStrongTest` bắt. Đây là lý do hai bộ test có thể có coverage gần như giống nhau nhưng khả năng phát hiện lỗi khác hẳn.

Mutation score thường được trình bày theo tỷ lệ mutant bị kill trên tập mutant được tính trong score; **hãy đọc rõ mẫu số của report công cụ** (survived, no-coverage, timed-out hoặc mutant bị loại có thể được xử lý khác nhau). Đừng so mutation score của hai lần chạy có tập mutant, cấu hình, filter hoặc phạm vi khác nhau như một phép so trực tiếp.

Mutation testing có chi phí thực thi cao hơn test thường và có **equivalent mutant**: thay đổi cú pháp nhưng không tạo ra khác biệt quan sát được theo hợp đồng. Vì vậy mục tiêu không phải “100% mọi giá”. Nên ưu tiên domain rules quan trọng, tập trung phân tích các mutant survived có giá trị thực tế, và bổ sung assertion/tình huống khi phát hiện lỗ hổng.

## 8. Khi con số che giấu rủi ro: các ngộ nhận cần tránh

| Ngộ nhận | Thực tế | Việc nên làm |
| --- | --- | --- |
| “Coverage đạt 90% nên nghiệp vụ đã đúng 90%” | Coverage đo mã chạy, không đo tỷ lệ quy tắc đúng | Lập danh sách quy tắc, trường hợp biên và hậu quả nếu sai |
| “100% line coverage tức là mọi `if` đã được thử” | Một dòng có thể có nhiều nhánh hoặc điều kiện phức tạp | Xem branch report và dựng test cho ranh giới/tổ hợp |
| “Có assertion là test tốt” | Assertion có thể tầm thường hoặc dùng expected sai | Thử thay đổi hành vi sai hợp lý: test có báo đỏ không? |
| “Test mock xanh nghĩa là DB/broker đúng” | Mock không đại diện cho protocol, transaction và lỗi môi trường thật | Thêm integration test có phụ thuộc thật khi cần |
| “`@SpringBootTest` xanh nghĩa là toàn API đúng” | Context startup không tự gọi hoặc kiểm tra response của từng API | Kiểm tra endpoint và hợp đồng HTTP có ý nghĩa |
| “Có mutation score cao tức không còn bug” | Công cụ chỉ thử một tập biến đổi hạn chế | Kết hợp yêu cầu, boundary, integration, exploratory và review |
| “Cứ tăng threshold là chất lượng tăng” | Có thể kích thích viết test chỉ để chạm dòng hoặc exclude khó | Dùng threshold làm tín hiệu, review các rủi ro cụ thể |

Đặc biệt cẩn thận với các kiểu “làm đẹp” số liệu: exclude class khó test nhưng quan trọng, tạo test chỉ khởi tạo bean, gọi getter/setter, hoặc assert thứ luôn đúng. Chúng có thể tăng tỷ lệ mà không tăng khả năng tìm bug.

## 9. Sử dụng coverage gate một cách hợp lý trong Gradle/CI

Nếu nhóm muốn CI báo lỗi khi branch coverage xuống dưới ngưỡng tham khảo, có thể **bổ sung** vào `build.gradle` ví dụ sau:

```groovy
tasks.named('jacocoTestCoverageVerification') {
    dependsOn(tasks.named('test'))
    violationRules {
        rule {
            limit {
                counter = 'BRANCH'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}

tasks.named('check') {
    dependsOn(tasks.named('jacocoTestCoverageVerification'))
}
```

Trong đó `0.80` là **ví dụ ngưỡng quản trị**, không phải chuẩn phổ quát. Rule mặc định ở đây kiểm tra theo phạm vi bundle báo cáo mà task thu thập, chưa diễn tả riêng mức độ rủi ro của từng service. Nếu đặt ngưỡng theo package/class hoặc gộp unit/integration coverage, phải cấu hình và kiểm chứng rõ phạm vi của task/violation rule.

Với dự án mới hoặc có nhiều mã cũ, nên lấy baseline hiện tại trước, ưu tiên module nghiệp vụ quan trọng và chống giảm coverage do thay đổi không chủ ý. Dù CI đạt ngưỡng, PR review vẫn cần hỏi: test mới bảo vệ hợp đồng nào, ranh giới gì, assertion có phát hiện cài đặt sai điển hình không? Threshold **không thay thế** review về tính đúng.

Một luồng CI cân đối:

1. Chạy compiler, unit tests và các assertion nghiệp vụ quan trọng; test fail phải chặn thay đổi.
2. Chạy integration/API tests phù hợp, cung cấp DB/broker/test configuration đáng tin khi kiến trúc yêu cầu.
3. Xuất báo cáo coverage và xác định những đường code có rủi ro nhưng chưa được thử.
4. Dùng coverage threshold cho tín hiệu xu hướng và tập trung review các phần mã mới/sửa quan trọng.
5. Chạy mutation testing chọn lọc, đặc biệt ở tính phí, ủy quyền, giao dịch hoặc xử lý trạng thái phức tạp; đánh giá survived mutants thay vì chỉ nhìn điểm.
6. Với bản phát hành, kiểm thử smoke trên artifact triển khai cùng cấu hình cần thiết; coverage của unit test không xác minh khả năng vận hành ở production.

## 10. Bài tập tự kiểm tra trước khi kết luận “test đủ tốt”

Xét thay đổi sau đối với quy tắc phí giao hàng ở phần 4:

- **Lỗi A:** `return 0;` thành `return 5_000;`.
- **Lỗi B:** `orderValue >= 200_000` thành `orderValue > 200_000`.
- **Lỗi C:** `return 30_000;` thành `return 3_000;`.
- **Lỗi D:** bỏ xử lý giá trị đơn âm.

Với từng lỗi, tự trả lời: test nào phải báo đỏ, assertion nào kích hoạt, và test yếu có phát hiện được không? Theo code ví dụ: test yếu bỏ lọt A, B, C nếu phí vẫn không âm; test mạnh bắt A/B/C nhờ các `assertEquals` giá trị cụ thể. Cả hai có thể bắt D nếu loại bỏ điều kiện dẫn đến không còn `IllegalArgumentException` cho `-1`. Câu trả lời phụ thuộc *mutant thực tế* và *test đang chạy*, không phụ thuộc duy nhất vào phần trăm coverage trước đó.

**Checklist trước khi tin vào số liệu:** Đã ghi rõ định nghĩa line/branch coverage và phạm vi đo chưa? Có test cho happy path, biên, dữ liệu sai và tác động phụ quan trọng không? Expected value dựa trên yêu cầu độc lập không? Có test tích hợp cho những hành vi phụ thuộc Spring wiring, HTTP, persistence hoặc security không? Test có báo đỏ khi cố ý tạo một lỗi nghiệp vụ điển hình không? Có ai đã review những vùng rủi ro cao dù report hiển thị màu xanh không?

Kết luận cần nhớ: **coverage giúp tìm chỗ chưa chạy; assertion có ý nghĩa giúp phát hiện kết quả sai; lựa chọn tình huống và chất lượng oracle quyết định mức độ các lỗi quan trọng được phát hiện.** Hãy dùng số liệu để dẫn đường cho kiểm thử và review, không biến số liệu thành định nghĩa duy nhất của chất lượng phần mềm.
