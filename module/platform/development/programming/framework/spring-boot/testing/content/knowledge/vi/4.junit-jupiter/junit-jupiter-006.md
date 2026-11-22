# JUnit Jupiter: `@MethodSource`, `@CsvSource` và `@CsvFileSource`

## Mục tiêu

Trong Spring Boot, nhiều quy tắc cần kiểm tra trên **nhiều bộ dữ liệu đầu vào**: giá trị nhỏ nhất/lớn nhất, các nhánh đúng–sai, dữ liệu hợp lệ/không hợp lệ. Thay vì sao chép cùng một thân test, JUnit Jupiter hỗ trợ **parameterized test**: viết một phương thức kiểm thử và cho chạy nhiều lần, mỗi lần nhận một bộ tham số.

Sau bài này, bạn có thể:

- Dùng `@ParameterizedTest` với `@MethodSource`, `@CsvSource` và `@CsvFileSource`.
- Chọn nguồn dữ liệu hợp lý: do Java tạo ra, khai báo ngắn ngay trong annotation, hay quản lý riêng trong tệp CSV.
- Dùng `Stream<Arguments>` cho nhiều tham số và `Stream<T>` cho một tham số; hiểu quy tắc `static` của factory method.
- Xử lý kiểu dữ liệu, dấu phẩy trong chuỗi, ô rỗng, `null`, header và đường dẫn resource.
- Tạo một ví dụ Java 17/JUnit Jupiter có thể chạy bằng Gradle, kiểm tra chính xác số lượt test và xử lý lỗi thường gặp.

Đây là bài về **nguồn tham số của JUnit Jupiter 5**, không phải hướng dẫn kiểm thử toàn bộ hệ thống Spring Boot hay sử dụng CSV trong production.

## 1. Nguyên lý parameterized test

Với `@Test`, mỗi phương thức là một ca kiểm thử độc lập. Với `@ParameterizedTest`, **cùng thân phương thức được gọi nhiều lần**. JUnit lấy bộ dữ liệu từ annotation nguồn, chuyển đổi giá trị sang các tham số của method khi cần, rồi chạy assertion cho từng lượt.

~~~text
@ParameterizedTest
       |
       +-- @MethodSource("cases")       -> dữ liệu từ phương thức Java
       |
       +-- @CsvSource({...})            -> dữ liệu CSV viết trong annotation
       |
       +-- @CsvFileSource(resources=...) -> dữ liệu CSV trong resource file
       |
       v
Mỗi hàng/bộ Arguments -> một invocation -> chạy thân test -> kết quả riêng
~~~

Ví dụ một phép tính có bốn dòng dữ liệu sẽ được JUnit thực thi bốn lần, không phải “một test duy nhất kiểm bốn hàng bên trong một vòng lặp”. Điều này giúp báo cáo xác định **bộ đầu vào nào thất bại**; dùng tên hiển thị chứa giá trị tham số giúp dễ chẩn đoán hơn nữa.

Ba annotation này thuộc `org.junit.jupiter.params.provider`, còn `@ParameterizedTest` thuộc `org.junit.jupiter.params`. Để sử dụng được chúng, classpath kiểm thử cần module **`junit-jupiter-params`**, cùng engine Jupiter để thực thi.

### Bảng so sánh nhanh

| Nguồn | Dữ liệu ở đâu? | Hợp với tình huống nào? | Giới hạn đáng nhớ |
| --- | --- | --- | --- |
| `@MethodSource` | Một factory method Java, có thể trả `Stream`, `Iterable`, mảng… | Object phức tạp, `null`, sinh dữ liệu bằng code, ca kiểm thử có nhiều loại tham số | Phương thức cùng test class thường phải `static`; nhiều tham số nên đóng bằng `Arguments`. |
| `@CsvSource` | Các dòng CSV khai báo trực tiếp trong annotation | Bảng dữ liệu nhỏ, các cột kiểu cơ bản, dễ nhìn cạnh assertion | Dữ liệu dài trở nên khó đọc; cần nhớ quy tắc trích dẫn và `null`. |
| `@CsvFileSource` | File CSV trên classpath hoặc đường dẫn file | Bảng ca kiểm thử dài, do tester/nghiệp vụ cung cấp, muốn xem xét như tài liệu | File phải được đóng gói/đọc đúng, header và định dạng CSV phải khớp chữ ký test. |

Chọn nguồn dựa trên **bản chất của bộ dữ liệu**, không chỉ dựa trên số dòng. Dữ liệu bên ngoài cần được kiểm soát phiên bản cùng code; phép tính expected phải độc lập với thuật toán đang được thử.

## 2. Chuẩn bị project Java 17 có JUnit Jupiter

Có thể thử độc lập không cần khởi động Spring Boot. Trong dự án Gradle Groovy DSL tối thiểu, cấu trúc như sau (các script Wrapper được tạo hoặc có sẵn tại root):

~~~text
junit-params-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/com/example/testing/RewardPointsCalculator.java
    └── test/
        ├── java/com/example/testing/RewardPointsCalculatorTest.java
        └── resources/cases/reward-points.csv
~~~

**`settings.gradle`**

~~~groovy
rootProject.name = 'junit-params-demo'
~~~

**`build.gradle`** — ví dụ dùng JUnit 5.10.2/BOM tương thích để mã chạy độc lập. Trong dự án Spring Boot thực, ưu tiên phiên bản dependency do Spring Boot/BOM của dự án quản lý.

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

`org.junit.jupiter:junit-jupiter` là artifact tổng hợp bao gồm Jupiter API, params và engine trong bộ JUnit 5.10.2. `useJUnitPlatform()` bảo Gradle chạy test qua JUnit Platform; launcher cung cấp thành phần runtime thích hợp. Java toolchain cần JDK 17 sẵn có hoặc cơ chế provisioning đã cấu hình.

Trong project Spring Boot **đã có plugin và BOM/dependency management**, cấu hình phổ biến tương ứng là:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` thường mang theo JUnit Jupiter, trong đó có params; không cần khai báo trùng nhiều phiên bản JUnit khác nhau. Nếu dùng một Spring Boot release khác, hãy để cơ chế quản lý phiên bản của nó quyết định các dependency tương thích. **Không copy cả hai block `dependencies` vào cùng project**: chọn một hướng theo bản chất dự án.

## 3. Quy tắc nghiệp vụ để thử

Giả sử hệ thống ghi điểm tích lũy theo số tiền mua:

- Mỗi **100 đơn vị tiền** mang lại **1 điểm cơ bản**, lấy phần nguyên. Ví dụ mua 299 được 2 điểm.
- Khách `premium` nhận **gấp đôi** điểm cơ bản.
- Mua dưới 100 được 0 điểm.
- Giá trị âm bị từ chối bằng `IllegalArgumentException`.

Viết code thực thi quy tắc ở **`src/main/java/com/example/testing/RewardPointsCalculator.java`**:

~~~java
package com.example.testing;

public final class RewardPointsCalculator {

    public int pointsFor(int purchaseAmount, boolean premium) {
        if (purchaseAmount < 0) {
            throw new IllegalArgumentException(
                    "purchaseAmount must be non-negative");
        }

        int basePoints = purchaseAmount / 100;
        return premium ? basePoints * 2 : basePoints;
    }
}
~~~

Do bài tập dùng `int` theo đơn vị giả định để tập trung vào kỹ thuật kiểm thử, không nên suy ra thiết kế xử lý tiền tệ sản xuất từ ví dụ. Các con số expected được xác định từ quy tắc trên bằng tay, không gọi lại chính method `pointsFor` để tính expected.

## 4. Ví dụ hoàn chỉnh sử dụng cả ba nguồn

Tạo file **`src/test/java/com/example/testing/RewardPointsCalculatorTest.java`**:

~~~java
package com.example.testing;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.CsvFileSource;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.MethodSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.params.provider.Arguments.arguments;

class RewardPointsCalculatorTest {

    private final RewardPointsCalculator calculator =
            new RewardPointsCalculator();

    record Purchase(int amount, boolean premium) {}

    // 1) @MethodSource: đối tượng Java kết hợp expected.
    @ParameterizedTest(name = "method {index}: {0} -> {1} points")
    @MethodSource("structuredCases")
    void calculatesFromMethodSource(Purchase purchase, int expected) {
        int actual = calculator.pointsFor(
                purchase.amount(), purchase.premium());

        assertEquals(expected, actual);
    }

    static Stream<Arguments> structuredCases() {
        return Stream.of(
                arguments(new Purchase(0, false), 0),
                arguments(new Purchase(99, true), 0),
                arguments(new Purchase(100, false), 1),
                arguments(new Purchase(100, true), 2),
                arguments(new Purchase(250, true), 4)
        );
    }

    // Một tham số thì có thể trả Stream<Integer>.
    @ParameterizedTest(name = "invalid purchase {0} is rejected")
    @MethodSource("invalidAmounts")
    void rejectsNegativeAmounts(int amount) {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.pointsFor(amount, false));
    }

    static Stream<Integer> invalidAmounts() {
        return Stream.of(-1, -100);
    }

    // 2) @CsvSource: bảng nhỏ ngay bên cạnh mã test.
    @ParameterizedTest(
            name = "inline CSV {index}: amount={0}, premium={1}, points={2}")
    @CsvSource({
        "199, false, 1",
        "199, true, 2",
        "500, false, 5",
        "500, true, 10",
        "550, true, 10"
    })
    void calculatesFromInlineCsv(int amount, boolean premium, int expected) {
        int actual = calculator.pointsFor(amount, premium);

        assertEquals(expected, actual);
    }

    // 3) @CsvFileSource: dữ liệu ở file resources.
    @ParameterizedTest(
            name = "file CSV {index}: amount={0}, premium={1}, points={2}")
    @CsvFileSource(
            resources = "/cases/reward-points.csv",
            numLinesToSkip = 1)
    void calculatesFromCsvFile(int amount, boolean premium, int expected) {
        int actual = calculator.pointsFor(amount, premium);

        assertEquals(expected, actual);
    }
}
~~~

Các method đều không cần `@Test`: **`@ParameterizedTest` tự đánh dấu chúng là parameterized test**. Trong cùng class, `structuredCases` và `invalidAmounts` là **factory methods** cung cấp dữ liệu; chúng không phải test và không mang `@Test`. Java `record Purchase` (có từ Java 16, dùng ổn ở Java 17) giữ hai thuộc tính đầu vào gọn và có `toString()` thuận tiện cho tên hiển thị.

### Tệp CSV cần đặt đúng vị trí

Tạo file **`src/test/resources/cases/reward-points.csv`** với đúng nội dung:

~~~csv
amount,premium,expected
1,false,0
99,false,0
100,false,1
101,true,2
299,true,4
300,false,3
999,true,18
1000,false,10
~~~

Vì `resources = "/cases/reward-points.csv"` tham chiếu **đường dẫn trên test classpath**, Gradle mặc định chép file từ `src/test/resources` vào test runtime classpath. Dấu `/` đầu đường dẫn biểu thị gốc classpath, không phải gốc ổ đĩa Windows/Linux. Nếu lưu file ở thư mục khác, cần sửa đường dẫn cho khớp. `numLinesToSkip = 1` bỏ qua dòng tiêu đề để JUnit không cố chuyển chuỗi `amount` thành `int`.

**Đối chiếu một số hàng trong CSV:**

| Đầu vào | Kỳ vọng | Vì sao |
| --- | --- | --- |
| `1,false` | `0` | 1 chia nguyên cho 100 bằng 0. |
| `101,true` | `2` | Cơ bản 1 điểm, premium nhân 2. |
| `299,true` | `4` | 299 chia nguyên cho 100 bằng 2, nhân 2 bằng 4. |
| `999,true` | `18` | Cơ bản 9 điểm, nhân 2 bằng 18. |
| `1000,false` | `10` | Cơ bản 10 điểm, khách thường không nhân đôi. |

Tất cả code minh họa trong mục 2–4 tạo thành **một project chạy được**. Chạy tại root đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu project chưa có Wrapper, có thể tạo từ một Gradle đã cài hợp lệ bằng `gradle wrapper --gradle-version <version-phù-hợp>` rồi commit các tệp Wrapper; cần chọn phiên bản tương thích với Java và plugin thực tế. Trong project Spring Boot hiện có, dùng Wrapper đã được repository cung cấp.

Với **chính bộ dữ liệu đã liệt kê**, các lượt thực thi là:

| Test method | Số bộ dữ liệu | Số invocation |
| --- | ---: | ---: |
| `calculatesFromMethodSource` | 5 | 5 |
| `rejectsNegativeAmounts` | 2 | 2 |
| `calculatesFromInlineCsv` | 5 | 5 |
| `calculatesFromCsvFile` | 8 hàng sau header | 8 |
| **Tổng** | **20** | **20** |

Tất cả phải pass với code mẫu. Không có `System.out.println`, nên các test **không sinh stdout nghiệp vụ**. Gradle thường báo `BUILD SUCCESSFUL` khi task thành công; xem số test chính xác trong `build/reports/tests/test/index.html` hoặc XML ở `build/test-results/test/`. Nếu task được đánh dấu `UP-TO-DATE`/`FROM-CACHE`, kết quả có thể được dùng lại; cần thực thi lại để chẩn đoán thì chạy `./gradlew test --rerun-tasks`.

## 5. `@MethodSource`: factory method Java

`@MethodSource` đọc dữ liệu từ **factory method** có thể được nêu tên trực tiếp:

~~~java
@ParameterizedTest
@MethodSource("caseProvider")
void testSomething(int value, String label) {
    // ...assertions...
}

static Stream<Arguments> caseProvider() {
    return Stream.of(
            arguments(1, "one"),
            arguments(2, "two")
    );
}
~~~

Đoạn này **chỉ minh họa cú pháp**, không phải chương trình độc lập. Các bộ `Arguments` chứa **hai đối số theo đúng thứ tự** mà test nhận: `int`, rồi `String`. Nếu factory trả một `Stream<Integer>`, test tương ứng chỉ có một tham số (như `invalidAmounts` trong ví dụ chạy được).

### Quy tắc quan trọng

1. **Tên:** `@MethodSource("structuredCases")` tìm factory `structuredCases`. Nếu bỏ tên trong annotation, JUnit dùng tên phương thức kiểm thử làm tên factory và có thể phải khai báo một factory cùng tên (thường là overload không nhận tham số). Nêu tên tường minh giúp dễ đọc.
2. **`static`:** factory nằm trong test class phải `static` mặc định. Ngoại lệ là test class có vòng đời `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, khi đó có thể khai báo factory instance. Factory ở class khác phải `static`.
3. **Giá trị trả về:** Jupiter chấp nhận một số dạng dữ liệu nguồn như `Stream`, `Iterable`, `Iterator`, mảng hoặc các kiểu stream nguyên thủy; `Stream<Arguments>` là lựa chọn thường dùng cho nhiều tham số. Mỗi phần tử phải khớp số lượng/kiểu tham số test.
4. **Đối tượng phức tạp:** `Arguments.of(...)` có thể chứa object, record, enum, collection, `null`; những ca cần setup đối tượng phức tạp thường phù hợp hơn CSV thuần chữ.
5. **Dữ liệu độc lập:** factory nên tạo dữ liệu xác định được, không phụ thuộc thứ tự test, đồng hồ, network hay cơ sở dữ liệu chia sẻ. JUnit có thể gọi factory để discovery và execution; tránh side effect trong provider.

Có thể tham chiếu provider ở class khác bằng chuỗi tên đầy đủ có dấu `#`, ví dụ `@MethodSource("com.example.testing.CommonCases#validInputs")`, với method `static` và khả năng truy cập phù hợp. Điều này hữu ích khi nhiều test dùng chung một bộ cases, nhưng nên tránh tạo “kho tổng hợp case” khó truy dấu.

**Khi nào ưu tiên?** Khi dữ liệu là object giàu cấu trúc, expected exception, scenario có nhiều nhánh, object không thể mô tả trực quan bằng CSV, hoặc cần code sinh những giá trị biên một cách xác định. Đừng viết provider vòng lặp trả expected bằng chính thuật toán của SUT: nếu cả hai cùng sai, test có thể vẫn pass.

## 6. `@CsvSource`: bảng nhỏ khai báo tại chỗ

`@CsvSource` cho mỗi chuỗi trong `value = {...}` một dòng CSV. JUnit chuyển cột sang tham số test theo thứ tự. Khi khai báo:

~~~java
@CsvSource({
    "500, false, 5",
    "500, true, 10"
})
~~~

dòng `"500, true, 10"` là **một chuỗi Java** chứa ba cột CSV, lần lượt được chuyển thành `int=500`, `boolean=true`, `int=10` của method ví dụ. Đây không phải ba phần tử của mảng Java riêng lẻ.

### Quy tắc delimiter, quote và khoảng trắng

Mặc định, `@CsvSource` dùng **dấu phẩy** làm delimiter và **dấu nháy đơn `'`** làm quote character. Nếu giá trị chuỗi có dấu phẩy, phải quote đúng kiểu CSV được `@CsvSource` sử dụng:

~~~java
@ParameterizedTest
@CsvSource({
    "'Miền Bắc, Việt Nam', 1",
    "'', 0"
})
void exampleCsvStrings(String region, int expectedFlag) {
    // Ví dụ riêng: nhận "Miền Bắc, Việt Nam" rồi nhận chuỗi rỗng "".
}
~~~

Đoạn trên chỉ minh họa cách truyền giá trị, không chứa assertion nên **chưa phải test hoàn chỉnh**. Có thể đổi dấu phân tách, ví dụ `@CsvSource(value = {"100; true; 2"}, delimiter = ';')`; lúc đó dấu `;` là separator. Không cấu hình đồng thời `delimiter` và `delimiterString`.

| Viết trong `@CsvSource` | Giá trị nhận được nếu tham số là `String` |
| --- | --- |
| `"red, blue"` (hai cột, không quote) | `"red"` và `"blue"` |
| `"'red, blue', 1"` | Cột đầu là `"red, blue"`; cột sau là `"1"` trước khi convert sang `int` |
| `"name, ''"` | Cột thứ hai là chuỗi rỗng `""` |
| `"name, "` | Cột thứ hai là `null` (không có giá trị) |
| `"name, NIL"` kèm `nullValues = "NIL"` | Cột thứ hai là `null` |

**`''` khác ô rỗng không quote:** chuỗi rỗng `""` và `null` có thể dẫn đến assertion/validation khác nhau. Một cột `null` không chuyển được sang tham số kiểu nguyên thủy `int`, `boolean`; hãy dùng kiểu wrapper như `Integer` nếu chủ ý kiểm tra `null`. Với `@CsvSource`, khoảng trắng đầu/cuối ở các cột không quote thường được trim; dữ liệu có khoảng trắng mang ý nghĩa nghiệp vụ cần được quote hoặc điều chỉnh cấu hình. Nếu cần xuống nhiều dòng trong Java 17, `@CsvSource(textBlock = """...""")` là một lựa chọn, nhưng dùng đúng Java text block và đặc tính xử lý dòng/comment theo tài liệu JUnit hiện hành.

**Khi nào ưu tiên?** Khi có vài hàng con số hoặc chuỗi ngắn, ví dụ kiểm tra số biên, từng loại tài khoản và expected tương ứng. Đặt test cạnh bộ dữ liệu giúp reviewer thấy toàn bộ ví dụ mà không phải mở file khác.

## 7. `@CsvFileSource`: bảng dữ liệu nằm trong tệp

Với `@CsvFileSource(resources = "/cases/reward-points.csv", numLinesToSkip = 1)`, mỗi **record** trong tệp sau header được xử lý thành một bộ tham số. Điều này phù hợp khi hàng dữ liệu nhiều hoặc được rà soát bởi QA/người hiểu nghiệp vụ.

### Cơ chế nạp resource

- `resources = "/cases/reward-points.csv"` đọc resource trên **classpath của test**, và đường dẫn bắt đầu bằng `/` để tính từ root của classpath.
- Khi dùng Java/Gradle thông thường, đặt tệp vào `src/test/resources/cases/reward-points.csv`. Nếu dùng custom source sets, bảo đảm resource được đưa vào runtime classpath của task test.
- `numLinesToSkip = 1` bỏ qua header đầu tiên. Nếu không skip mà dòng đầu là `amount,premium,expected`, JUnit sẽ cố chuyển `amount` sang `int` và fail ở argument conversion.
- Có thể khai báo nhiều resource qua `resources = {"/cases/a.csv", "/cases/b.csv"}`; nên bảo đảm các file có cùng schema.
- `@CsvFileSource` cũng hỗ trợ đường dẫn file thông qua thuộc tính `files`, nhưng tài nguyên dưới `src/test/resources` thường dễ đóng gói, chia sẻ và chạy ổn định trên CI hơn đường dẫn phụ thuộc thư mục làm việc.

### CSV file mặc định dùng nháy kép

Khác `@CsvSource`, `@CsvFileSource` **mặc định dùng dấu nháy kép `"`** để quote chuỗi có dấu phẩy:

~~~csv
region,level
"Miền Bắc, Việt Nam",1
"Miền Nam, Việt Nam",2
~~~

Nếu người viết dùng quote đơn `'Miền Bắc, Việt Nam'` trong tệp mà không đổi `quoteCharacter`, dấu phẩy bên trong có thể bị hiểu thành dấu phân cột, làm sai số lượng tham số.

Quy tắc **dữ liệu rỗng** tương tự về ý nghĩa nhưng khác ký tự quote:

| Trong file CSV | Ý nghĩa mặc định |
| --- | --- |
| `""` (được quote bằng nháy kép) | Chuỗi rỗng `""` |
| Một cột trống giữa hai dấu phẩy | `null` |
| `NIL` với `nullValues = "NIL"` | `null` |
| `"Miền Bắc, Việt Nam"` | Một cột chứa cả dấu phẩy |

Một file CSV có thể chứa dòng chú thích bắt đầu bằng `#` được JUnit bỏ qua. Không lạm dụng comment để thay đổi ý nghĩa số cột. Khi dữ liệu chứa ký tự đặc biệt, hãy lưu tệp theo UTF-8 và giữ cùng quy tắc quote/delimiter với annotation.

### Quản lý dữ liệu file có trách nhiệm

File CSV không nên trở thành “đống dữ liệu vàng” khó hiểu. Người viết test cần biết mỗi hàng bảo vệ quy tắc nào; tên cột, commit diff và giải thích biên được giữ rõ ràng. Dùng dữ liệu giả lập, không đưa thông tin cá nhân hay credential thật vào repository. File được review cùng code vì thay đổi **expected** cũng có thể che lỗi. Nếu phải dùng nhiều kịch bản khác cấu trúc, cân nhắc tách file theo hợp đồng hoặc chọn `@MethodSource` với case object.

## 8. Chọn nguồn dựa trên tình huống thực tế

| Bạn có gì? | Ưu tiên | Lý do |
| --- | --- | --- |
| 3–10 cặp số và expected | `@CsvSource` | Ngắn, đọc nhanh cạnh test |
| 50 hàng input/expected đã được QA rà soát | `@CsvFileSource` | Tách dữ liệu, dễ review hàng CSV và dùng với CI |
| Input gồm record, enum, object, exception type | `@MethodSource` | Factory tạo object có kiểu rõ ràng |
| Chỉ một tham số `String` có `null`, empty, blank | `@NullSource`/`@EmptySource`/`@ValueSource` hoặc `@MethodSource` | Đơn giản hơn là ép vào CSV |
| Bộ test gồm dữ liệu sinh có quy luật rõ và ổn định | `@MethodSource` | Có thể xây bộ cases bằng Java mà vẫn dễ kiểm chứng |
| Dữ liệu có dấu phẩy, newline hoặc dấu quote phức tạp | `@MethodSource` hoặc CSV được escape chính xác | Giảm rủi ro parser làm thay đổi giá trị |

Không phải vì có nhiều hàng mà bắt buộc phải chuyển sang CSV file. Nếu expected kết hợp logic nghiệp vụ phức tạp, một `record` với tên trường rõ nghĩa có thể giúp tránh đọc nhầm cột hơn là file có 12 cột kiểu nguyên thủy.

## 9. Tên invocation và cách chạy đúng test

Những tên hiển thị trong ví dụ dùng `name = "...{index}...{0}..."`:

- `{index}` là số thứ tự lượt chạy do Jupiter cung cấp.
- `{0}`, `{1}`, … là chuỗi hiển thị của từng đối số.
- Tên có đầu vào và expected giúp tìm nhanh dòng lỗi trong IDE, HTML report và CI.

Ví dụ, ca `199, true, 2` sẽ có tên dạng **`inline CSV 2: amount=199, premium=true, points=2`** nếu đây là dòng thứ hai của `@CsvSource`. Các nhãn có thể được formatter/IDE trình bày khác đi; chính **kết quả assertion và số invocation** mới là thứ xác minh.

Chạy toàn bộ class trong Gradle project:

~~~bash
./gradlew test --tests 'com.example.testing.RewardPointsCalculatorTest'
~~~

Chạy riêng một method parameterized:

~~~bash
./gradlew test --tests 'com.example.testing.RewardPointsCalculatorTest.calculatesFromInlineCsv'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests 'com.example.testing.RewardPointsCalculatorTest'
~~~

`--tests` chọn method theo tên, còn một method parameterized vẫn có thể tạo **nhiều invocation**. Không nên kỳ vọng `--tests <method>` chỉ chạy một dòng CSV. Với một số bản Gradle/JUnit, lọc tới một invocation riêng bằng display name có giới hạn và khác nhau; để chẩn đoán thường dễ hơn nếu chọn method rồi xem index/argument trong report.

Khi cần xem thêm log cấu hình/discovery, dùng `./gradlew test --info` hoặc `--stacktrace`. Các file báo cáo chuẩn xuất hiện dưới `build/reports/tests/test/` và `build/test-results/test/` của Gradle module đang chạy. Với multi-project, có thể phải dùng task path ví dụ `:orders:test` nếu đó là project path thực.

## 10. Lỗi phổ biến và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| JUnit không nhận `@ParameterizedTest` | Thiếu `junit-jupiter-params`, engine hoặc `useJUnitPlatform()` | Kiểm tra test dependencies, Gradle task và import |
| Báo không tìm thấy method source | Sai tên trong `@MethodSource` hoặc package/class tham chiếu | Đối chiếu tên factory; dùng tên tường minh |
| Factory method phải static | Factory instance trong lifecycle mặc định | Đặt `static`, hoặc cấu hình `@TestInstance(PER_CLASS)` khi thật sự cần |
| Số tham số không khớp | `Arguments`/CSV thiếu hoặc thừa cột | Kiểm tra từng hàng và chữ ký method |
| `ArgumentConversionException` | Chuỗi không đổi được sang `int`/`boolean`/enum, hoặc giá trị `null` đưa vào primitive | Sửa dữ liệu, kiểu tham số hay dùng converter có chủ đích |
| Nội dung có dấu phẩy bị tách sai | CSV quote sai theo từng annotation | `@CsvSource` mặc định `'`; `@CsvFileSource` mặc định `"` |
| Header `amount` bị ép thành `int` | Chưa bỏ dòng tiêu đề trong file CSV | Dùng `numLinesToSkip = 1` hoặc cấu hình header thích hợp |
| `Cannot find resource` | Sai đường dẫn, sai nguồn `src/test/resources` hoặc chưa đóng gói | Kiểm tra classpath và resource path bắt đầu bằng `/` |
| CSV file chạy trên máy cá nhân nhưng lỗi CI | Dùng đường dẫn máy, encoding hoặc dữ liệu không commit | Dùng resource thuộc repo, encoding thống nhất |
| Test luôn pass dù logic hỏng | Expected được sinh bằng chính SUT, assertion quá yếu | Viết expected độc lập từ yêu cầu, thử tạo lỗi có chủ đích |
| Test không ổn định | Provider dùng random/time/network/shared state | Cố định seed/dữ liệu, kiểm soát dependency và tạo case độc lập |
| Bảng rất lớn gây báo cáo khó hiểu | Nhiều dòng lặp, case không có ý nghĩa | Gom theo yêu cầu, đặt tên invocation rõ, bỏ hàng trùng không cần thiết |

### Bốn điểm dễ nhầm cần nhớ

**(1) `@Test` khác `@ParameterizedTest`:** Phương thức nhận arguments từ source phải mang `@ParameterizedTest`. Nếu chỉ dùng `@Test`, JUnit không tự gắn dữ liệu từ `@CsvSource` vào tham số test.

**(2) Một method không phải một invocation:** Với năm rows, test chạy năm lần. Nếu muốn biết pass/fail của từng case, xem báo cáo theo invocation hoặc tên hiển thị.

**(3) `null` không giống `""`:** CSV trống không quote thường tương ứng `null`; chuỗi rỗng có quote vẫn là giá trị không `null`. Với primitive, JUnit không thể truyền `null`.

**(4) Provider không phải oracle:** Factory tạo input và expected, nhưng expected phải suy ra **từ đặc tả nghiệp vụ**; không lặp lại logic SUT để tự xác nhận chính mình.

## 11. Bài tập tự luyện

**Bài A — `@CsvSource`:** Thêm các ca với `purchaseAmount = 99, 100, 199, 200` cho `premium=false`. Viết expected độc lập trước khi chạy. Với mỗi dòng, kiểm tra đúng bước nhảy tại bội số của 100.

**Bài B — `@MethodSource`:** Mở rộng `Stream<Arguments>` để nhận một `Purchase` object và một `expected` trong các trường hợp `premium=true` ở ngưỡng 100, 200, 300. Thêm `Stream<Integer>` cho giá trị âm lớn; dùng `assertThrows`.

**Bài C — `@CsvFileSource`:** Thêm hai hàng vào `reward-points.csv` cho `purchaseAmount = 1099, premium=true` và `purchaseAmount = 1999, premium=false`. Expected tương ứng là `20` và `19`. Kiểm tra rằng tổng số invocation tăng từ **20 lên 22**, không đổi thân test.

**Bài D — phát hiện lỗi:** Tạm thay `purchaseAmount / 100` thành `purchaseAmount / 200` trong một bản local; những ca có expected khác 0 phải fail. Hoàn nguyên thay đổi rồi chạy lại. Đây là cách xác nhận test đang kiểm quy tắc thật, không chỉ xác nhận JUnit đã tải file CSV.

**Ghi nhớ:** `@MethodSource` linh hoạt nhất với object/dữ liệu Java, `@CsvSource` giúp trình bày bảng nhỏ ngay bên test, và `@CsvFileSource` phù hợp với bảng dữ liệu quản lý riêng. Dù chọn nguồn nào, phải ghép đúng số cột/kiểu, làm rõ `null`/quote, và giữ expected độc lập để mỗi invocation có ý nghĩa kiểm thử.
