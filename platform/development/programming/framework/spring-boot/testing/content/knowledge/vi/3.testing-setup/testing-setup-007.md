# Chạy một lớp, một phương thức hoặc một nhóm tag

## 1. Mục tiêu của bài học

Trong dự án Spring Boot, chạy toàn bộ test sau mỗi chỉnh sửa nhỏ có thể mất thời gian: một số test chỉ kiểm tra logic Java, một số tạo Spring `ApplicationContext`, một số còn cần database hay dịch vụ bên ngoài. Để nhận phản hồi nhanh mà vẫn biết chính xác mình đang kiểm tra điều gì, cần thành thạo ba cách chọn test:

1. **Theo lớp:** chạy toàn bộ test trong một test class, ví dụ `CalculatorTest`.
2. **Theo phương thức:** chạy đúng một test method, ví dụ `CalculatorTest.addsTwoNumbers`.
3. **Theo tag:** chạy một nhóm test thuộc nhiều lớp dựa trên `@Tag("smoke")`, `@Tag("unit")` hoặc biểu thức kết hợp.

Phạm vi chính của bài là **cách cấu hình và chạy test**, không phải cách viết mọi loại unit/integration test. Ví dụ sử dụng JUnit Jupiter (JUnit 5), Java 17+ và Gradle; phần sau đối chiếu Maven Surefire để áp dụng cho dự án Spring Boot dùng Maven.

### Ai thực sự chọn test để chạy?

```text
Lệnh trong terminal
  └── Gradle Test task hoặc Maven Surefire
        ├── Lọc class/method theo tham số dòng lệnh
        └── JUnit Platform + Jupiter TestEngine
              ├── Khám phá các test có thể chạy
              ├── Lọc thêm theo JUnit @Tag nếu được cấu hình
              └── Thực thi test, trả kết quả PASS/FAIL/SKIPPED
```

- `@Test` đánh dấu phương thức kiểm thử.
- `@Tag` **gắn nhãn**, không tự chạy hay tự bỏ qua một test. Chỉ khi cấu hình lọc tag thì nhãn mới quyết định tập test được chọn.
- `--tests` là **tham số của Gradle**, khác với `@Tag` và khác tham số `-Dtest` của Maven Surefire.
- Khi đồng thời lọc class/method và tag, test phải phù hợp **cả hai điều kiện** mới được thực thi.
- Lọc test không vô hiệu hóa `@Disabled` hoặc các điều kiện vô hiệu hóa test khác.

Không cần dùng `@SpringBootTest` để chọn test. Việc chọn một class, method hay tag áp dụng cho JUnit Jupiter thuần, `@WebMvcTest`, `@DataJpaTest`, `@SpringBootTest` và các test dùng Spring Framework.

## 2. Chuẩn bị một bộ test minh họa có thể chạy

Để dễ xác định kết quả lệnh, ta dùng một dự án Gradle Java tối thiểu với **5 test PASS** chia thành hai lớp. Cơ chế chọn test này hoạt động giống hệt khi các test nằm trong một ứng dụng Spring Boot có `spring-boot-starter-test`.

Cấu trúc:

```text
select-tests-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/testing/
│   ├── Calculator.java
│   └── GreetingFormatter.java
└── src/test/java/com/example/testing/
    ├── CalculatorTest.java
    └── GreetingFormatterTest.java
```

### 2.1. Cấu hình Gradle và JUnit Platform

`settings.gradle`:

```groovy
rootProject.name = 'select-tests-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

def includedTagExpression = providers.gradleProperty('includeTags').orNull
def excludedTagExpression = providers.gradleProperty('excludeTags').orNull

tasks.named('test', Test) {
    useJUnitPlatform {
        if (includedTagExpression?.trim()) {
            includeTags includedTagExpression.trim()
        }
        if (excludedTagExpression?.trim()) {
            excludeTags excludedTagExpression.trim()
        }
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
```

Đây là một **dự án Gradle Java độc lập** để chạy ví dụ ngay cả khi chưa có ứng dụng Boot. BOM đồng bộ phiên bản thư viện JUnit 5; `useJUnitPlatform` yêu cầu task `test` chạy bằng JUnit Platform. Hai project property `includeTags` và `excludeTags` chỉ có tác dụng khi được truyền vào lệnh; nếu không truyền, không có bộ lọc tag mặc định. Vì thế bài vẫn có thể chạy **toàn bộ 5 test**.

Đối với **dự án Spring Boot đã được cấu hình**, thường chỉ cần bảo đảm dependency kiểm thử:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot quản lý phiên bản JUnit theo BOM của phiên bản Boot. Giữ phần cấu hình `tasks.named('test', Test) { useJUnitPlatform { ... } }` để hỗ trợ chọn tag động; không cần ép một JUnit BOM khác vào Boot chỉ để dùng `@Tag`. Đây là **điều chỉnh cho dự án Boot**, không phải yêu cầu thêm cả hai cấu hình dependency vào cùng một dự án.

Nếu có **Gradle Wrapper**, dùng `./gradlew` trên Linux/macOS hoặc `gradlew.bat` trên Windows. Nếu không có Wrapper, các lệnh ví dụ `./gradlew` có thể đổi thành `gradle` khi máy đã cài Gradle tương thích. Nên chạy trong thư mục chứa `settings.gradle`.

### 2.2. Mã ứng dụng Java 17+

`src/main/java/com/example/testing/Calculator.java`:

```java
package com.example.testing;

public final class Calculator {
    public int add(int left, int right) {
        return left + right;
    }

    public int divide(int left, int right) {
        return left / right;
    }
}
```

`src/main/java/com/example/testing/GreetingFormatter.java`:

```java
package com.example.testing;

public final class GreetingFormatter {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return "Xin chào, " + name.strip() + "!";
    }
}
```

Hai lớp này không dùng Spring nên giúp quan sát rõ việc chọn test mà không chịu ảnh hưởng từ thời gian khởi tạo context.

### 2.3. Hai test class và tag của từng phương thức

`src/test/java/com/example/testing/CalculatorTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
class CalculatorTest {
    private final Calculator calculator = new Calculator();

    @Test
    @Tag("smoke")
    void addsTwoNumbers() {
        assertEquals(5, calculator.add(2, 3));
    }

    @Test
    void dividesEvenly() {
        assertEquals(3, calculator.divide(12, 4));
    }

    @Test
    void rejectsDivisionByZero() {
        assertThrows(
                ArithmeticException.class,
                () -> calculator.divide(1, 0)
        );
    }
}
```

`src/test/java/com/example/testing/GreetingFormatterTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingFormatterTest {
    private final GreetingFormatter formatter = new GreetingFormatter();

    @Test
    @Tag("smoke")
    void formatsGreeting() {
        assertEquals("Xin chào, An!", formatter.greet(" An "));
    }

    @Test
    @Tag("contract")
    void rejectsBlankName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> formatter.greet("   ")
        );
    }
}
```

**Tập test thật trong ví dụ:**

| Lớp | Phương thức | Tag hiệu lực | Kết quả |
| --- | --- | --- | --- |
| `CalculatorTest` | `addsTwoNumbers` | `unit`, `smoke` | PASS |
| `CalculatorTest` | `dividesEvenly` | `unit` | PASS |
| `CalculatorTest` | `rejectsDivisionByZero` | `unit` | PASS |
| `GreetingFormatterTest` | `formatsGreeting` | `smoke` | PASS |
| `GreetingFormatterTest` | `rejectsBlankName` | `contract` | PASS |

`@Tag("unit")` đặt ở **class** áp dụng cho mọi test method bên trong `CalculatorTest`. Riêng `addsTwoNumbers` còn mang thêm tag `smoke` từ annotation ở method. Một test có thể thuộc nhiều nhóm; tag trên method được kết hợp với tag cấp lớp, không thay thế nhau.

Chạy mặc định:

```bash
./gradlew test
```

**Kỳ vọng:** 5 test được thực thi và PASS. Các test không in ra `stdout` cố định; Gradle hiển thị sự kiện test tùy cấu hình logging và báo cáo. Có thể mở `build/reports/tests/test/index.html` để xem từng test, hoặc đọc XML trong `build/test-results/test/`.

## 3. Chạy đúng một lớp test bằng Gradle

Khi đang sửa logic `Calculator`, ta thường chỉ muốn chạy lớp kiểm thử tương ứng:

```bash
./gradlew test --tests "com.example.testing.CalculatorTest"
```

Trong dự án mẫu, lệnh chạy **3 phương thức** của `CalculatorTest` và không chạy hai test trong `GreetingFormatterTest`.

Gradle còn nhận **tên lớp ngắn** nếu không có nhầm lẫn:

```bash
./gradlew test --tests "CalculatorTest"
```

Hoặc dùng ký tự đại diện `*`:

```bash
./gradlew test --tests "*CalculatorTest"
```

Những cách này đều chọn lớp Calculator trong bộ test hiện tại. **Tên đầy đủ kèm package** là lựa chọn rõ nhất khi repository có nhiều class trùng tên.

Một vài pattern hữu ích:

| Tham số Gradle | Ý nghĩa |
| --- | --- |
| `--tests "com.example.testing.CalculatorTest"` | Chọn đúng lớp theo fully qualified class name |
| `--tests "CalculatorTest"` | Chọn theo simple class name |
| `--tests "*CalculatorTest"` | Chọn mọi lớp có tên khớp wildcard |
| `--tests "com.example.testing.*"` | Chọn test trong package tương ứng và lớp có tên phù hợp pattern |
| `--tests "*Test"` | Chọn các lớp có tên kết thúc bằng `Test`; phù hợp ví dụ này nhưng có thể quá rộng trong dự án thật |

`--tests` lọc trên **test discovery của task `test`**, không đồng nghĩa với chọn file Java source hoặc chạy class bằng lệnh `java`. Gradle vẫn có thể biên dịch source/test trước khi thực thi test được lọc.

### Chạy nhiều lớp trong cùng một lệnh

Có thể lặp lại `--tests`:

```bash
./gradlew test --tests "CalculatorTest" --tests "GreetingFormatterTest"
```

Hai pattern chọn theo phép **hợp (OR)**; ví dụ chạy đủ 5 test. Dùng nhiều tham số `--tests` khi cần kiểm tra vài lớp cụ thể mà không sửa `build.gradle`.

## 4. Chạy đúng một phương thức test bằng Gradle

Khi đang xử lý một lỗi hẹp, chạy một method cho vòng phản hồi ngắn:

```bash
./gradlew test --tests "com.example.testing.CalculatorTest.addsTwoNumbers"
```

Hoặc tên lớp ngắn:

```bash
./gradlew test --tests "CalculatorTest.addsTwoNumbers"
```

**Kỳ vọng:** chỉ **1 test** `addsTwoNumbers` chạy; hai method còn lại trong cùng class không chạy.

Để chạy phương thức khác:

```bash
./gradlew test --tests "CalculatorTest.rejectsDivisionByZero"
```

Test này PASS vì `assertThrows` mong đợi `ArithmeticException` khi chia cho 0. Exception mong đợi không có nghĩa là bài test bị lỗi.

### Chọn nhiều method hoặc dùng wildcard

```bash
./gradlew test \
  --tests "CalculatorTest.addsTwoNumbers" \
  --tests "CalculatorTest.rejectsDivisionByZero"
```

Kỳ vọng chạy **2 test**. Dấu `\` cuối dòng là cú pháp tiếp dòng trong shell Bash; trên Windows hoặc PowerShell đơn giản đặt tất cả tham số trên **một dòng**:

```bash
./gradlew test --tests "CalculatorTest.addsTwoNumbers" --tests "CalculatorTest.rejectsDivisionByZero"
```

Nếu dự án có phương thức cùng tiền tố, dùng `--tests "CalculatorTest.*"` để chọn các test method của lớp. Không nhầm tên method Java với `@DisplayName`: khi chạy test thông thường theo method, dùng **tên phương thức trong mã nguồn** để pattern dễ ổn định.

**Trường hợp đặc biệt:** chọn một phương thức `@ParameterizedTest` có thể chạy **tất cả lần gọi với các tham số** của phương thức đó; chọn `@RepeatedTest` có thể chạy tất cả lần lặp. Nó không mặc nhiên chạy đúng một invocation. Với `@Nested` hoặc test động, tên hiển thị và định danh do engine cung cấp có thể khiến pattern chi tiết phức tạp hơn; bắt đầu từ lớp chứa test rồi xem báo cáo thực tế.

## 5. Gắn và hiểu JUnit tag

JUnit Jupiter hỗ trợ `@Tag("ten-nhom")` trên lớp hoặc phương thức. Tag phù hợp để quản lý các nhóm chạy xuyên qua nhiều package:

- `unit`: test logic cô lập, chạy thường xuyên;
- `smoke`: nhóm rất nhỏ xác nhận các hành vi quan trọng;
- `integration`: test tích hợp với Spring context, database hoặc service thật;
- `contract`: xác nhận một hợp đồng đầu vào/đầu ra.

Đây là **quy ước tên nhóm của dự án**; JUnit không tự suy ra một test thực sự là unit hay integration chỉ từ tên tag. Không nên gán `integration` cho test không hề kiểm tra ranh giới tích hợp.

Một tag phải là chuỗi không rỗng; sau khi trim, không được chứa khoảng trắng, ký tự điều khiển hoặc các ký tự dành riêng như dấu phẩy, `(`, `)`, `&`, `|`, `!`. Tên như `integration-db` hợp lệ và dễ đọc.

### Biểu thức tag

JUnit Platform hỗ trợ **tag expression** với các toán tử:

| Biểu thức | Tập test được chọn |
| --- | --- |
| `smoke` | Có tag `smoke` |
| `unit | contract` | Có `unit` **hoặc** `contract` |
| `unit & smoke` | Có cả `unit` **và** `smoke` |
| `unit & !smoke` | Có `unit` nhưng **không** có `smoke` |
| `(smoke | contract) & !integration` | Có `smoke` hoặc `contract` nhưng không có `integration` |
| `any()` | Có ít nhất một tag |
| `none()` | Không có tag nào |

Thứ tự ưu tiên là `!` trước `&` trước `|`; dùng ngoặc khi cần diễn đạt rõ ràng. **Không được** dùng dấu phẩy để nối nhiều tag trong một `@Tag`; dấu phẩy không nằm trong tên tag hợp lệ.

## 6. Chạy một nhóm tag bằng Gradle

Gradle chạy JUnit Platform thông qua `useJUnitPlatform { ... }`. Trong `build.gradle` ở mục 2, ta đã ánh xạ hai project property `includeTags`, `excludeTags` sang bộ lọc của Platform. Vì vậy có thể chọn nhóm **trên dòng lệnh** mà không phải sửa file cấu hình mỗi lần.

### Chạy toàn bộ nhóm smoke

```bash
./gradlew test -PincludeTags=smoke
```

**Kỳ vọng: 2 test** — `CalculatorTest.addsTwoNumbers` và `GreetingFormatterTest.formatsGreeting`. Hai lớp đều được xem xét, nhưng các phương thức khác không có tag `smoke` nên không được chọn.

### Chạy toàn bộ nhóm unit

```bash
./gradlew test -PincludeTags=unit
```

**Kỳ vọng: 3 test** — toàn bộ test trong `CalculatorTest`, nhờ tag `unit` ở cấp lớp.

### Lọc bằng biểu thức logic

Trong Bash/zsh, dùng nháy đơn quanh toàn bộ tham số khi biểu thức chứa khoảng trắng hoặc `!`:

```bash
./gradlew test '-PincludeTags=unit & !smoke'
```

**Kỳ vọng: 2 test** — `dividesEvenly` và `rejectsDivisionByZero`. Method `addsTwoNumbers` có cả `unit` lẫn `smoke` nên bị loại khỏi biểu thức này.

Chạy nhóm `smoke` hoặc `contract`:

```bash
./gradlew test '-PincludeTags=smoke | contract'
```

**Kỳ vọng: 3 test** — `addsTwoNumbers`, `formatsGreeting`, `rejectsBlankName`.

Trên **Windows PowerShell/cmd**, dùng nháy kép cho tham số có ký tự đặc biệt:

```powershell
.\gradlew.bat test "-PincludeTags=unit & !smoke"
.\gradlew.bat test "-PincludeTags=smoke | contract"
```

Cú pháp nháy kép ở đây giúp shell truyền biểu thức nguyên vẹn vào một đối số. Đừng tách `unit`, `&` và `!smoke` thành ba tham số riêng.

### Chỉ loại một nhóm test

```bash
./gradlew test -PexcludeTags=smoke
```

**Kỳ vọng: 3 test** còn lại của bộ mẫu. Nếu cùng khai báo include và exclude, phép lọc cuối cùng tương ứng với “thuộc nhóm cho phép **và** không thuộc nhóm loại trừ”:

```bash
./gradlew test -PincludeTags=unit -PexcludeTags=smoke
```

Lệnh này cũng chạy **2 test** trong `CalculatorTest` không mang tag `smoke`.

### Lọc tag cố định trong build script

Nếu mọi lệnh `test` của một task luôn phải chạy cùng nhóm, có thể cấu hình tĩnh:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'unit'
        excludeTags 'integration'
    }
}
```

Đoạn trên là **một phương án thay thế** phần cấu hình tag động ở mục 2, không phải đoạn cần thêm vào sau nó. Nếu đặt lọc tĩnh rồi tiếp tục truyền project property, tập test có thể thu hẹp khó đoán. Với bộ test dành cho developer và CI, cách dùng `-PincludeTags` động ở mục 2 giúp nhìn thấy rõ nhóm nào đang được chạy.

**Điểm dễ nhầm:** Gradle không mặc định hỗ trợ lệnh `./gradlew test --tag smoke`. Lệnh `-PincludeTags=smoke` ở đây hoạt động **nhờ** mã nối project property với `useJUnitPlatform` trong `build.gradle`; nó không phải option tích hợp sẵn để lọc tag của Gradle.

## 7. Kết hợp chọn class/method và tag

Đôi khi cần chạy chỉ những smoke test của một class:

```bash
./gradlew test --tests "CalculatorTest" -PincludeTags=smoke
```

**Kỳ vọng: 1 test** — `CalculatorTest.addsTwoNumbers`.

Một lệnh tưởng đúng nhưng không khớp:

```bash
./gradlew test --tests "GreetingFormatterTest.rejectsBlankName" -PincludeTags=smoke
```

`rejectsBlankName` chỉ có tag `contract`, nên **không có test nào đáp ứng cả hai bộ lọc**. Với cách lọc của Gradle, điều này có thể khiến task thất bại vì không tìm thấy test phù hợp, tùy cấu hình `failOnNoMatchingTests`. Không nên diễn giải trạng thái “0 tests” như đã xác nhận chức năng đúng.

Trong Gradle, các pattern `--tests` được kết hợp theo OR với nhau, còn bộ lọc tag do JUnit Platform áp dụng sẽ tiếp tục giới hạn tập test. Có thể hiểu:

```text
Test được chạy
= khớp ít nhất một bộ lọc --tests (nếu có)
  VÀ thỏa biểu thức includeTags (nếu có)
  VÀ không thỏa biểu thức excludeTags (nếu có)
  VÀ không bị disabled/điều kiện thực thi loại bỏ
```

Ví dụ phép chọn “mọi test `smoke` trên toàn repository” là cách lọc bằng **tag**; phép chọn “mọi test trong `CalculatorTest`” là cách lọc bằng **class**; phép chọn “`addsTwoNumbers`” là cách lọc theo **method**. Chọn kiểu lọc theo mục đích thay vì ghép nhiều điều kiện nếu không cần thiết.

## 8. Đối chiếu với Maven Surefire trong dự án Spring Boot

Nếu dự án dùng Maven, phần chọn test thường do **Maven Surefire Plugin** thực hiện. Các lệnh sau giả định `pom.xml` đã cấu hình JUnit Jupiter qua `spring-boot-starter-test` hoặc dependency JUnit thích hợp, và dùng phiên bản Surefire hỗ trợ JUnit Platform (ví dụ Surefire 3.x).

| Mục tiêu | Lệnh Maven tương ứng |
| --- | --- |
| Chạy toàn bộ test | `./mvnw test` |
| Chạy một lớp | `./mvnw -Dtest=CalculatorTest test` |
| Chạy một lớp theo tên đầy đủ | `./mvnw -Dtest=com.example.testing.CalculatorTest test` |
| Chạy một method | `./mvnw "-Dtest=CalculatorTest#addsTwoNumbers" test` |
| Chạy tag smoke | `./mvnw -Dgroups=smoke test` |
| Chạy biểu thức tag | `./mvnw '-Dgroups=unit & !smoke' test` |
| Loại tag smoke | `./mvnw -DexcludedGroups=smoke test` |

`-Dtest` là tham số lọc test class/method của **Surefire**, trong đó dấu `#` phân cách lớp với phương thức. Nó **khác** ký hiệu dấu chấm ở Gradle `--tests "Class.method"`.

`groups` và `excludedGroups` của Surefire tương thích JUnit Platform dùng để lọc tag/tag expression; chúng **không phải** Spring `@Profile`. Với Windows PowerShell/cmd, dùng nháy kép cho biểu thức:

```powershell
.\mvnw.cmd "-Dgroups=unit & !smoke" test
```

Maven Surefire mặc định nhận diện tên class theo các mẫu như `*Test`, `*Tests`, `Test*`, `*TestCase`. Các lớp ví dụ `CalculatorTest`, `GreetingFormatterTest` phù hợp. Nếu dự án có cấu hình include/exclude khác, cần tuân theo cấu hình thực tế.

Khi dự án phân tách integration test sang **Maven Failsafe** (`integration-test`/`verify`), `mvn test` không thay thế việc chạy vòng đời Failsafe; lúc đó cần dùng mục tiêu và bộ lọc của task/plugin tương ứng. Tương tự với Gradle, một task `integrationTest` tự tạo không nhất thiết là một phần của task `test`.

## 9. Khi ứng dụng thật dùng Spring Boot Test

Ví dụ trên cố ý dùng test Java thuần. Trong Spring Boot, cùng thao tác lọc vẫn áp dụng:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@Tag("integration")
class ApplicationStartupTest {
    @Test
    void contextLoads() {
        // PASS khi Spring Boot ApplicationContext khởi tạo thành công.
    }
}
```

Đây là **đoạn ví dụ để thêm vào dự án Spring Boot có `@SpringBootApplication`**, không chạy độc lập trong project Java tối thiểu ở mục 2. Khi đã có class này trong ứng dụng Boot, có thể chọn:

```bash
./gradlew test --tests "ApplicationStartupTest"
./gradlew test -PincludeTags=integration
```

Các lệnh chọn **test cần thực thi**, không tự thay đổi quy mô của Spring context. Chạy đúng một method trong lớp `@SpringBootTest` vẫn có thể phải khởi tạo ApplicationContext và các dependency mà test sử dụng. Đừng mặc định chạy một method luôn nhanh tức thời; điểm khác biệt chủ yếu là **số test được chọn**.

Khi dùng `@WebMvcTest` hoặc `@DataJpaTest`, tag chỉ lọc test được thực thi; nó không biến slice test thành full integration test. Khi dùng Testcontainers, test được chọn có thể vẫn khởi tạo container và cần Docker/container runtime phù hợp. Nếu test không được chọn bởi tag, chi phí thiết lập của test đó thường cũng không cần xảy ra trong lần chạy này, nhưng các hook/context được chia sẻ cho test khác có thể vẫn khởi tạo.

**Tổ chức tag thực tế:** đặt `@Tag("integration")` ở class nếu **mọi method** đều là integration test; đặt ở method nếu chỉ một số method thuộc nhóm. Tag ở class không phải chỉ là nhãn hiển thị — nó có tác động tới tất cả test method trong lớp khi lọc.

## 10. Cách xác nhận bộ lọc thật sự chạy đúng

Sau khi chạy lệnh, cần kiểm tra ba điều:

1. **Task phù hợp:** có chạy đúng `test`, `integrationTest` hoặc task tương ứng của module không?
2. **Số lượng và tên test thực thi:** có khớp mục tiêu, hay vô tình chạy quá nhiều/không chạy test nào?
3. **Kết quả:** các test được chạy PASS hay FAIL? Test bị SKIPPED có nguyên nhân gì?

Trong Gradle, file báo cáo thông dụng:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-*.xml
```

Với Maven Surefire:

```text
target/surefire-reports/
```

Đây là các đường dẫn mặc định trong module đang chạy; dự án nhiều module, cấu hình custom hoặc test task khác có thể dùng đường dẫn khác. Báo cáo HTML/XML hữu ích để xác nhận chính xác method nào đã chạy; không nên chỉ nhìn dòng `BUILD SUCCESSFUL` hoặc `BUILD SUCCESS` rồi suy ra toàn bộ test suite đã được kiểm tra.

### Bảng kết quả kỳ vọng của ví dụ mục 2

| Lệnh Gradle (rút gọn sau `./gradlew`) | Số test dự kiến |
| --- | ---: |
| `test` | 5 |
| `test --tests "CalculatorTest"` | 3 |
| `test --tests "CalculatorTest.addsTwoNumbers"` | 1 |
| `test -PincludeTags=smoke` | 2 |
| `test -PincludeTags=unit` | 3 |
| `test '-PincludeTags=unit & !smoke'` | 2 |
| `test '-PincludeTags=smoke | contract'` | 3 |
| `test -PexcludeTags=smoke` | 3 |
| `test --tests "CalculatorTest" -PincludeTags=smoke` | 1 |

Các số lượng này dựa trên **chính năm method đã trình bày**, với giả định test code biên dịch, JUnit Platform được bật và không có cấu hình lọc khác. Khi thêm hoặc đổi tag/test method, cập nhật kỳ vọng theo tập test thực tế.

### Lỗi thường gặp và cách xử lý

**`No tests found for given includes` / “0 tests”**

- Kiểm tra tên class có đúng package không; sử dụng fully qualified name để loại trừ nhầm lẫn.
- Kiểm tra test nằm trong `src/test/java`, JUnit Jupiter có trên classpath và task dùng `useJUnitPlatform`.
- Kiểm tra `@Test` và tên method thật; `@DisplayName` có thể khác tên phương thức.
- Nếu đang ghép `--tests` và `includeTags`, kiểm tra chúng có giao nhau không.
- Kiểm tra class bị cấu hình exclude, test bị `@Disabled` hoặc test thuộc task/source set khác.

**Thêm `@Tag("smoke")` nhưng lệnh `./gradlew test` vẫn chạy cả suite**

Đây là hành vi bình thường: `@Tag` chỉ là nhãn. Cần `useJUnitPlatform { includeTags 'smoke' }` hoặc cấu hình động `-PincludeTags=smoke` như ví dụ.

**Gõ `./gradlew test -PincludeTags=smoke` nhưng vẫn chạy cả suite**

Kiểm tra `build.gradle` đã thật sự đọc `includeTags` và truyền vào `useJUnitPlatform`. Project property tự nó không có cơ chế điều khiển JUnit nếu không được kết nối bằng cấu hình build script.

**Viết `--tests "Class#method"` theo thói quen Maven**

Gradle dùng `Class.method`; Maven Surefire dùng `-Dtest=Class#method`. Hai bộ lọc có cú pháp khác nhau.

**Biểu thức tag có `&`, `|` hoặc `!` bị shell phân tách**

Đặt toàn bộ tham số `-PincludeTags=...` trong dấu nháy phù hợp với shell. Trong Maven, cũng cần quote `-Dgroups=...` nếu có khoảng trắng/toán tử.

**Chạy một test nhưng vẫn tốn nhiều thời gian**

Kiểm tra test có `@SpringBootTest` hoặc dùng container/db ngoài không; chọn một method không triệt tiêu chi phí cần thiết để khởi tạo context, container, Gradle build và fixture.

**Test PASS nhưng CI đã bỏ lỡ nhóm quan trọng**

Bộ lọc class/method thích hợp cho vòng debug cục bộ; job CI kiểm tra đầy đủ phải có đường chạy toàn suite hoặc các nhóm bổ sung nhau. Đảm bảo không vô tình để cấu hình `includeTags 'smoke'` vĩnh viễn trên toàn bộ task `test`.

**Thấy test bỏ qua nhưng không biết vì sao**

Phân biệt ba trạng thái: **không được chọn** (lọc discovery), **bị disabled/skipped** (`@Disabled`, assumption, điều kiện) và **đã chạy nhưng FAIL** (assertion/exception). Báo cáo cùng log test là nguồn xác nhận.

## 11. Bài thực hành tự kiểm tra

Với bộ test 5 method, thực hiện lần lượt:

1. Chạy cả `CalculatorTest` và dự đoán 3 tên method sẽ xuất hiện.
2. Chạy duy nhất `GreetingFormatterTest.formatsGreeting`; xác nhận chỉ 1 test.
3. Chạy nhóm `smoke`; xác nhận hai test nằm **ở hai class khác nhau**.
4. Chạy `unit & !smoke`; giải thích vì sao `addsTwoNumbers` không được chọn dù class có tag `unit`.
5. Chạy `--tests "CalculatorTest"` kết hợp `-PincludeTags=smoke`; dự đoán đúng 1 test.
6. Thêm `@Tag("smoke")` vào `rejectsBlankName`, chạy lại nhóm `smoke` và dự đoán số test tăng từ 2 lên **3**.

Các bài thực hành này chỉ yêu cầu thay annotation và chạy lại test; không cần Spring context hay database để hiểu cơ chế lọc.

## 12. Ghi nhớ khi áp dụng vào dự án

- **Một lớp:** `./gradlew test --tests "package.ClassTest"`.
- **Một phương thức:** `./gradlew test --tests "package.ClassTest.methodName"`.
- **Một nhóm tag:** gắn `@Tag` và dùng `useJUnitPlatform { includeTags ... }`; muốn điều chỉnh qua CLI thì ánh xạ một project property như `-PincludeTags=smoke`.
- **Maven:** `-Dtest=ClassTest`, `-Dtest=ClassTest#methodName` và `-Dgroups=smoke` với Surefire/JUnit Platform.
- **Kết hợp bộ lọc:** test phải thỏa cả pattern class/method và biểu thức tag, nên phải kiểm tra báo cáo số lượng test.
- **Spring Boot:** lựa chọn test vẫn do Gradle/Maven và JUnit Platform quyết định; `@SpringBootTest`/slice annotation quyết định môi trường Spring khi test tương ứng thực sự chạy.

Tài liệu chính thức để đối chiếu cách dùng và những thay đổi theo phiên bản:

- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html) (Test filtering; Test grouping).
- [JUnit 5 User Guide — Tagging and Filtering / Tags](https://docs.junit.org/5.10.2/user-guide/index.html).
- [Maven Surefire — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html).
