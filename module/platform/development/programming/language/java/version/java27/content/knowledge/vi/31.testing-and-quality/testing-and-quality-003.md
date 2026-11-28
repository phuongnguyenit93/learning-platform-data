# Parameterized test, dữ liệu biên và kiểm thử dựa trên thuộc tính

## 1. Ba cách tăng độ tin cậy cho kiểm thử

Một chương trình có thể vượt qua mọi ví dụ quen thuộc nhưng sai ở **giá trị biên**, **null**, **chuỗi Unicode**, **số nguyên tràn**, **ngày nhuận** hoặc **tổ hợp nhiều điều kiện**. Với Java 27, xây dựng bộ kiểm thử tốt đòi hỏi trả lời hai câu hỏi: hệ thống có thực hiện đúng những ví dụ trong hợp đồng không, và những bất biến nào vẫn đúng với rất nhiều đầu vào khác?

Ba phương pháp bổ sung cho nhau:

- **Parameterized testing**: chạy cùng một test method với nhiều bộ dữ liệu có expected result được xác định.
- **Boundary value analysis**: tập trung vào nơi hành vi có thể đổi, ví dụ min, max, ngay trong/ngoài biên.
- **Property-based testing (PBT)**: sinh nhiều đầu vào trong một miền rồi kiểm tra thuộc tính chung; khi phát hiện phản ví dụ, framework có thể thử thu nhỏ (*shrinking*).

~~~mermaid
flowchart TD
    S["Đặc tả / hợp đồng"] --> P["Các phân lớp đầu vào"]
    P --> B["Ca thử ví dụ + dữ liệu biên"]
    P --> I["Bất biến / property"]
    B --> J["JUnit parameterized tests"]
    I --> G["Generator"]
    G --> T["PBT engine"]
    T --> K["Counterexample + shrinking"]
    K --> R["Regression case cố định"]
    J --> C["CI"]
    R --> C
~~~

**Không thay thế hoàn toàn phương pháp nào bằng phương pháp khác.** Một generator có thể không tạo được trường hợp cực hiếm; một bảng ví dụ có thể không bao phủ hết miền; một property thiếu chặt chẽ có thể được thỏa mãn bởi một implementation sai.

## 2. Framework hiện hành và ranh giới tương thích

**JUnit Jupiter 6.1.3** là phiên bản ổn định được phát hành năm 2026, hỗ trợ Java 17 trở lên và thích hợp để kiểm thử mã nguồn dành cho Java 27. Những API ổn định được dùng ở đây gồm **@ParameterizedTest**, **@ValueSource**, **@CsvSource**, **@MethodSource**, **@CsvFileSource**, **@NullAndEmptySource** và **Assertions**.

**jqwik 1.10.2** là framework PBT hiện hành với **@Property**, **@ForAll**, **@Provide**, **Arbitrary**, shrinking và seed để tái hiện. Phiên bản này theo tài liệu của dự án dùng dòng **JUnit Platform 1.14.x**.

**Cần đặc biệt lưu ý:** JUnit **6.1.3** sử dụng **JUnit Platform 6.x**, trong khi jqwik **1.10.2** được tài liệu hóa với Platform **1.14.x**. Hai ví dụ build trong bài là **hai phương án cấu hình độc lập**. Không ghép chúng vào cùng test runtime khi chưa có xác nhận compatibility và chưa kiểm tra dependency resolution. Các khái niệm kiểm thử vẫn áp dụng ở nhiều phiên bản framework, nhưng các con số version không được phép trộn tùy tiện.

| Mục tiêu | Phương tiện ưu tiên | Lý do |
|---|---|---|
| Danh sách các ví dụ nhỏ | @ValueSource | Một tham số cho mỗi invocation |
| Bảng value/min/max/expected | @CsvSource | Một hàng là một case |
| Tạo object hoặc dữ liệu liên quan | @MethodSource | Dễ biểu đạt bằng Java |
| Bảng được quản lý riêng | @CsvFileSource | Dễ review và tái sử dụng |
| null/empty/blank | @NullAndEmptySource + ValueSource | Rõ ràng về giá trị đặc biệt |
| Nhiều input hợp lệ sinh tự động | jqwik @Property | Generator + shrinking |
| Sinh dữ liệu có seed không dùng PBT engine | JUnit @Test + SplittableRandom | Dễ áp dụng, không tự shrink |

Dự án mới nên ưu tiên Jupiter thay vì **JUnit Vintage** — engine chủ yếu phục vụ di chuyển kiểm thử JUnit cũ và đã bị đánh dấu deprecated trong tài liệu JUnit 6.

## 3. Test oracle: điều gì chứng minh kết quả đúng?

**Test oracle** là cơ sở để xác định một lần chạy thành công hay thất bại. Với các ví dụ, oracle có thể là expected value cụ thể; với PBT, đó là một phát biểu phải đúng cho mọi đầu vào hợp lệ.

Ví dụ quy tắc **clamp(value, min, max)**:

1. **min <= max** là điều kiện để đoạn [min, max] hợp lệ.
2. Kết quả luôn nằm trong [min, max].
3. Nếu value < min, kết quả bằng min.
4. Nếu value > max, kết quả bằng max.
5. Nếu value ở trong đoạn, kết quả bằng value.
6. Nếu min > max, ném **IllegalArgumentException**.
7. Trường hợp min == max là một đoạn chỉ có một phần tử và vẫn hợp lệ.

~~~text
Ví dụ cụ thể:
  clamp(15, 1, 10) = 10

Thuộc tính:
  với mọi value, min, max mà min <= max:
  min <= clamp(value, min, max) <= max
~~~

Cần hạn chế test mà **expected được tính bằng chính thuật toán của implementation**. Nếu hai bản cùng sai, bộ test vẫn có thể xanh. Hãy lấy hợp đồng làm nguồn oracle chính.

## 4. Class Java được kiểm thử xuyên suốt

**Tệp src/main/java/example/RangeLimiter.java:**

~~~java
package example;

public final class RangeLimiter {
    private RangeLimiter() {}

    /** Kẹp giá trị vào đoạn đóng [min, max]. */
    public static int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min must not exceed max");
        }

        return Math.min(max, Math.max(min, value));
    }

    /**
     * Mã kỹ thuật dài từ 1 đến 8 ký tự ASCII.
     * Bắt đầu bằng A-Z; phần sau gồm A-Z, 0-9 hoặc dấu -.
     */
    public static boolean isValidCode(String raw) {
        return raw != null
            && raw.length() <= 8
            && raw.matches("[A-Z][A-Z0-9-]{0,7}");
    }
}
~~~

Đây là hàm thuần Java, không I/O, không state dùng chung. Nó phù hợp để học cơ chế parameterization và property testing mà không cần mock.

**Không áp dụng grammar ASCII này cho tên người hoặc văn bản tiếng Việt.** Mỗi trường đầu vào cần chính sách phù hợp; một mã định danh kỹ thuật có thể hạn chế ký tự, còn display name thường cần hỗ trợ Unicode.

## 5. Cấu hình JUnit Jupiter bằng Gradle

Ví dụ cấu hình **build.gradle (Groovy DSL)** để chạy các ví dụ JUnit:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform('org.junit:junit-bom:6.1.3'))
    testImplementation('org.junit.jupiter:junit-jupiter')
    testRuntimeOnly('org.junit.platform:junit-platform-launcher')
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Dependency tổng hợp **junit-jupiter** kéo theo Jupiter API, engine và **junit-jupiter-params**; không cần thêm params nếu đã dùng aggregator đúng phiên bản.

Cách chạy khi dự án đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Những lệnh chỉ minh họa cách chạy khi setup đã tồn tại; bước viết kiến thức này không chạy Gradle và không sửa build files của dự án khác.

## 6. @ParameterizedTest tạo nhiều test invocations

Một parameterized test có cùng test body, nhưng được gọi nhiều lần với những argument khác nhau.

~~~java
package example;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RangeLimiterBasicTest {
    @ParameterizedTest(name = "[{index}] input={0}")
    @ValueSource(ints = {-10, -1, 0, 1, 10})
    void valuesWithinBoundsRemainUnchanged(int value) {
        assertEquals(
            value,
            RangeLimiter.clamp(value, -10, 10)
        );
    }
}
~~~

JUnit thực hiện năm invocations. Tên có **{index}** và **{0}** cho biết lần chạy và giá trị đối số đầu, giúp đọc báo cáo kiểm thử.

**Lợi ích:** không phải sao chép năm phương thức test giống nhau. **Giới hạn:** nếu các giá trị đều từ cùng một phân lớp, nhiều invocation chưa chắc làm tăng khả năng phát hiện lỗi.

## 7. @ValueSource: một cột dữ liệu đơn giản

**@ValueSource** cung cấp các literal của một kiểu cho **một tham số**, ví dụ int, long, String, char hoặc Class trong những loại được hỗ trợ.

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ValidCodeTest {
    @ParameterizedTest(name = "valid code: {0}")
    @ValueSource(strings = {
        "A", "A-7", "AB123456", "A-------"
    })
    void acceptsKnownValidCodes(String code) {
        assertTrue(RangeLimiter.isValidCode(code));
    }
}
~~~

Bảng trên có trường hợp dài tối thiểu, có dấu gạch, dài tối đa và chuỗi vẫn hợp lệ dù gồm nhiều dấu gạch. Nếu cần thay đổi **nhiều tham số cùng lúc**, không lạm dụng ValueSource; dùng CsvSource hoặc MethodSource.

## 8. @CsvSource: test nhiều cột tương ứng

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClampCsvTest {
    @ParameterizedTest(
        name = "[{index}] clamp({0}, {1}, {2}) = {3}"
    )
    @CsvSource({
        "-2147483648, -10, 10, -10",
        "-11, -10, 10, -10",
        "-10, -10, 10, -10",
        "-9, -10, 10, -9",
        "0, -10, 10, 0",
        "9, -10, 10, 9",
        "10, -10, 10, 10",
        "11, -10, 10, 10",
        "2147483647, -10, 10, 10",
        "5, 5, 5, 5"
    })
    void clampsAccordingToContract(
            int value, int min, int max, int expected) {

        assertEquals(expected, RangeLimiter.clamp(value, min, max));
    }
}
~~~

Mỗi dòng CSV tương ứng một bộ **value/min/max/expected**. JUnit chuyển các giá trị dạng text thành int theo bộ converter đã hỗ trợ.

Bảng bao phủ: cực trị kiểu int, ngay ngoài biên, tại biên, ngay trong biên, trường hợp giữa đoạn và đoạn một điểm. Các expected được viết tường minh, không dựa vào việc gọi lại thuật toán kẹp của code đang test.

## 9. Bẫy null và chuỗi rỗng trong CSV

Ở **@CsvSource**, theo quy tắc mặc định:

- Một cột **để trống và không quote** được diễn giải thành **null**.
- Một cột **rỗng nhưng được quote bằng cặp dấu nháy đơn** là chuỗi **""**.
- Các cột text không quote có thể được trim theo quy tắc whitespace của source.
- Dấu phân cách mặc định là dấu phẩy.

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CsvNullVsEmptyTest {
    @ParameterizedTest
    @CsvSource({
        ", NULL",
        "'', EMPTY",
        "abc, TEXT"
    })
    void tellsNullFromEmpty(String input, String category) {
        String actual = input == null ? "NULL"
            : input.isEmpty() ? "EMPTY" : "TEXT";

        assertEquals(category, actual);
    }
}
~~~

**Không truyền null cho tham số primitive như int:** JUnit sẽ thất bại ở bước chuyển arguments. Nếu cần kiểm tra null, hãy dùng wrapper như Integer hoặc String tùy contract.

Với **@CsvFileSource**, dấu quote mặc định thường là **dấu nháy kép**, khác @CsvSource. Đừng mặc định hai source có cùng quy tắc CSV dù dữ liệu trông giống nhau.

## 10. @NullAndEmptySource và blank strings

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertFalse;

class InvalidCodeTest {
    @ParameterizedTest(name = "invalid code: {0}")
    @NullAndEmptySource
    @ValueSource(strings = {
        " ", "\t", "a", "1ABC", "ABCDEFGHI", "A/B", "A😀"
    })
    void rejectsInvalidCodes(String code) {
        assertFalse(RangeLimiter.isValidCode(code));
    }
}
~~~

Ba nhóm cần phân biệt:

- **null:** thiếu reference.
- **empty:** chuỗi length = 0.
- **blank:** có ký tự nhưng chỉ gồm whitespace theo quy tắc được chọn.

**@NullSource** và **@EmptySource** có thể dùng riêng hoặc kết hợp qua **@NullAndEmptySource**. EmptySource chỉ hỗ trợ một tập kiểu xác định như String, array và các collection tương thích; không có nghĩa mọi loại object đều được tự động tạo một giá trị rỗng.

## 11. @MethodSource cho object và dữ liệu có quan hệ

~~~java
package example;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClampMethodSourceTest {
    static Stream<Arguments> clampCases() {
        return Stream.of(
            Arguments.of(-100, -10, 10, -10),
            Arguments.of(0, -10, 10, 0),
            Arguments.of(100, -10, 10, 10),
            Arguments.of(7, 7, 7, 7)
        );
    }

    @ParameterizedTest
    @MethodSource("clampCases")
    void followsCases(
            int value, int min, int max, int expected) {

        assertEquals(expected, RangeLimiter.clamp(value, min, max));
    }
}
~~~

Với test instance lifecycle mặc định của Jupiter, source method trong cùng test class thường cần **static**. Có những quy tắc khác khi dùng **PER_CLASS**; chỉ đổi lifecycle nếu có lý do rõ ràng.

MethodSource tiện khi có **records**, **lists**, **dates**, **complex objects** hoặc việc xây expected có nhiều trường. Không nên gọi production database hoặc mạng để tạo input cho một unit test vốn cần chạy nhanh và độc lập.

## 12. @CsvFileSource khi bảng dữ liệu dài

Có thể đặt dữ liệu vào **src/test/resources/clamp-cases.csv**:

~~~csv
input,min,max,expected
-11,-10,10,-10
-10,-10,10,-10
0,-10,10,0
10,-10,10,10
11,-10,10,10
~~~

Sau đó dùng:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvFileSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ClampFileTest {
    @ParameterizedTest
    @CsvFileSource(
        resources = "/clamp-cases.csv",
        numLinesToSkip = 1
    )
    void validatesTable(
            int value, int min, int max, int expected) {

        assertEquals(expected, RangeLimiter.clamp(value, min, max));
    }
}
~~~

Ưu điểm của file dữ liệu riêng: dễ review bảng case khi nhiều người cùng viết đặc tả. Nhưng phải lưu file vào version control, kiểm tra delimiter/quote/charset và gắn những case quan trọng với lý do nghiệp vụ để dễ bảo trì.

## 13. @EnumSource cho trạng thái

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class DeliveryModeTests {
    enum Mode { STANDARD, EXPRESS, PICKUP }

    @ParameterizedTest
    @EnumSource(Mode.class)
    void eachModeIsRecognized(Mode mode) {
        assertNotNull(mode.name());
    }
}
~~~

Đây là ví dụ cơ chế source, **chưa phải assertion nghiệp vụ tốt**. Trong thực tế nên kiểm tra mỗi mode có chính sách giá, thời gian giao hàng hoặc quyền hợp lệ theo hợp đồng. Chỉ kiểm tra **enum.name() != null** sẽ không phát hiện được những sai lệch ấy.

## 14. Phân lớp tương đương (equivalence partitioning)

**Phân lớp tương đương** gom những input mà hệ thống được kỳ vọng xử lý theo cùng quy tắc. Với một trường **quantity** là số nguyên trong đoạn [1, 100]:

| Phân lớp | Đại diện | Kết quả cần kiểm tra |
|---|---|---|
| Không cung cấp | null | Từ chối theo API contract |
| Rỗng/blank | "", " " | Từ chối hoặc xử lý theo chính sách |
| Giá trị âm | -5 | Từ chối |
| Bằng 0 | 0 | Từ chối |
| Hợp lệ thấp | 1 | Chấp nhận |
| Hợp lệ giữa | 50 | Chấp nhận |
| Hợp lệ cao | 100 | Chấp nhận |
| Trên giới hạn | 101 | Từ chối |
| Rất lớn | Integer.MAX_VALUE | Từ chối |
| Sai kiểu | "one", 1.5 | Lỗi parse/schema |

Một đại diện của phân lớp chỉ là điểm xuất phát. Nếu code có quy tắc cho số chẵn, ngày nhuận hoặc ký tự Unicode, cần chia nhỏ miền theo những quy tắc đó.

## 15. Phân tích giá trị biên

Với đoạn nguyên đóng **[L, U]**, chọn tối thiểu các điểm sau khi có thể biểu diễn:

~~~text
L-1  |  L  |  L+1  |  giữa miền  |  U-1  |  U  |  U+1
     ngoài    trong                  trong      ngoài
~~~

Ví dụ [1,100]:

| Giá trị | Vị trí | Kỳ vọng |
|---:|---|---|
| 0 | Ngay dưới min | Sai |
| 1 | Chính min | Đúng |
| 2 | Ngay trên min | Đúng |
| 50 | Đại diện nội miền | Đúng |
| 99 | Ngay dưới max | Đúng |
| 100 | Chính max | Đúng |
| 101 | Ngay trên max | Sai |

Không tùy tiện tính **L - 1** nếu L là **Integer.MIN_VALUE**, hoặc **U + 1** nếu U là **Integer.MAX_VALUE**: chính biểu thức tạo test data có thể bị overflow.

Với số thực, một đơn vị cộng thêm có thể quá lớn; dùng các giá trị sát biên theo độ chính xác hợp đồng hoặc **Math.nextUp/Math.nextDown** khi phù hợp.

## 16. Biên không chỉ là số nguyên

Những ranh giới đáng test:

- **Kích thước:** list 0/1/n phần tử, chuỗi đúng max và vượt một đơn vị, payload đúng giới hạn byte và vượt một byte.
- **Thời gian:** 23:59:59, cuối tháng, 29/02, DST gap/overlap, deadline vừa tới, timeout.
- **Kiểu số:** MIN_VALUE, MAX_VALUE, số âm/zero, giá trị gây overflow, precision/scale.
- **Text:** null/empty/blank, Unicode composed/decomposed, emoji nhiều code points, malformed UTF-8.
- **Trạng thái:** chuyển trạng thái hợp lệ, chuyển sai, thao tác lặp và hủy giữa chừng.
- **Concurrency:** 0/1/n threads, hàng đợi vừa đầy, task đã hủy hoặc bị interrupt.
- **Quyền:** principal không có quyền, tài nguyên thuộc tenant khác, token vừa hết hạn.

Dữ liệu biên phải suy ra từ hợp đồng của API, không chọn một bộ giá trị -1/0/1 duy nhất cho mọi chức năng.

## 17. Điều kiện nhiều chiều và tổ hợp rủi ro

Nếu một chức năng có năm tham số, mỗi tham số ba giá trị, toàn bộ tổ hợp có **3^5 = 243** trường hợp. Với số chiều lớn hơn, số lượng tăng rất nhanh.

Có thể dùng **pairwise testing** để phủ các cặp điều kiện với ít case hơn. Nhưng lỗi chỉ phát sinh khi **ba hoặc nhiều điều kiện tương tác** có thể không được pairwise bao phủ.

Ví dụ các kết hợp nên ưu tiên:

- Coupon tối đa và quantity tối đa.
- Không có quyền nhưng ID đối tượng hợp lệ.
- Deadline đúng lúc thay đổi timezone.
- File đúng giới hạn bytes nhưng giải nén vượt quota.
- Một khoản tiền vừa chạm giới hạn đồng thời có phí bổ sung.

**Tư duy dựa trên rủi ro** là trọng tâm: số lượng invocation lớn không tự bảo đảm phát hiện đúng lỗi có tác động lớn.

## 18. Negative tests kiểm tra chính xác cách từ chối

Với **min > max**, hợp đồng yêu cầu **IllegalArgumentException**:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertThrowsExactly;

class InvalidRangeTest {
    @ParameterizedTest
    @CsvSource({
        "10, 9",
        "1, 0",
        "-5, -6"
    })
    void rejectsInvalidBounds(int min, int max) {
        assertThrowsExactly(
            IllegalArgumentException.class,
            () -> RangeLimiter.clamp(0, min, max)
        );
    }
}
~~~

**assertThrowsExactly** yêu cầu loại exception chính xác; **assertThrows** cho phép subtype. Chọn theo hợp đồng, không chỉ theo việc test viết dễ hay khó.

Ở tầng HTTP, còn phải kiểm tra status code, error code công khai, không tiết lộ dữ liệu nhạy cảm và không gây side effects khi yêu cầu bị từ chối.

## 19. Property và invariant có ý nghĩa gì?

Thay vì liệt kê expected cho từng input, một property kiểm tra quy tắc đúng cho nhiều giá trị trong miền:

~~~text
Với min <= max:

1. min <= clamp(x, min, max) <= max

2. clamp(clamp(x, min, max), min, max)
   == clamp(x, min, max)

3. Nếu a <= b thì
   clamp(a, min, max) <= clamp(b, min, max)

4. Nếu min <= x <= max thì
   clamp(x, min, max) == x
~~~

Các loại thuộc tính khác:

| Loại property | Mô tả |
|---|---|
| **Idempotence** | f(f(x)) = f(x) |
| **Monotonicity** | Input có thứ tự thì output có quan hệ thứ tự tương ứng |
| **Round-trip** | deserialize(serialize(x)) giữ thông tin quan trọng |
| **Commutativity** | f(a,b) = f(b,a), chỉ với phép có giao hoán |
| **Associativity** | f(f(a,b),c) = f(a,f(b,c)), nếu phép có kết hợp |
| **Metamorphic** | Biến đổi input tạo quan hệ dự kiến giữa output |
| **State invariant** | Sau mỗi thao tác hợp lệ, trạng thái vẫn thỏa điều kiện |

**Một implementation luôn trả min vẫn có thể vượt qua property kết quả trong đoạn.** Vì vậy, phải có thêm property giữ nguyên giá trị trong đoạn và những directed tests đã biết.

## 20. Quy trình property-based testing

**Property-based testing** biến một quy tắc tổng quát thành phép thử thực tế:

1. Xác định **miền dữ liệu hợp lệ**.
2. Định nghĩa **Arbitrary/generator** tạo ra những input nằm trong miền đó.
3. Viết **property/oracle** từ hợp đồng.
4. Thực thi property nhiều lần với dữ liệu sinh tự động.
5. Khi thất bại, ghi lại **counterexample**.
6. Dùng **shrinking** để tìm tình huống đơn giản hơn, nếu framework hỗ trợ.
7. Đưa phản ví dụ thành **deterministic regression test**.
8. Tiếp tục chạy property sau khi sửa lỗi.

~~~mermaid
flowchart TD
    A["Property + miền dữ liệu"] --> B["Generator"]
    B --> C["Giá trị được sinh"]
    C --> D["Gọi code cần test"]
    D --> E{"Bất biến đúng?"}
    E -->|"Đúng"| F["Sinh dữ liệu tiếp"]
    E -->|"Sai"| G["Counterexample"]
    G --> H["Shrink / tối giản"]
    H --> I["Giữ seed + ca regression"]
~~~

PBT là **kiểm thử dựa trên dữ liệu**, **không phải chứng minh toán học**. Dù một property đã qua một nghìn lần thử, không có nghĩa nó được chứng minh đúng với mọi giá trị trong miền.

## 21. Cấu hình jqwik độc lập với JUnit 6

Đây là **cấu hình build.gradle riêng** cho jqwik **1.10.2**, dựa trên dòng JUnit Platform 1.14.x mà tài liệu jqwik nêu ra:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation('net.jqwik:jqwik:1.10.2')
    testRuntimeOnly('org.junit.platform:junit-platform-launcher:1.14.4')
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Không dán trực tiếp cấu hình này vào cùng cấu hình JUnit Jupiter 6.1.3 ở mục 5.** Nếu dự án cần đồng thời parameterized và property tests, hãy chọn một tập phiên bản engine/Platform tương thích được nhà phát hành hỗ trợ, sau đó kiểm tra dependency graph và chạy kiểm thử. Một lựa chọn phù hợp với tài liệu jqwik 1.10.2 là nhánh Jupiter 5.14.x trên dòng Platform 1.x, nếu dự án cần Jupiter trong cùng runtime; cũng có thể chờ một phiên bản PBT engine xác nhận hỗ trợ JUnit Platform 6.

Phần code property bên dưới dùng **boolean property** của jqwik, nên không cần nhập Assertions từ Jupiter và không ngầm tạo dependency xuyên dòng Platform.

## 22. @Property và @ForAll

Test jqwik đơn giản nhất:

~~~java
package example;

import net.jqwik.api.ForAll;
import net.jqwik.api.Property;

class ClampSimpleProperties {
    @Property(tries = 300)
    boolean alwaysWithinZeroAndTen(@ForAll int value) {
        int result = RangeLimiter.clamp(value, 0, 10);

        return result >= 0 && result <= 10;
    }
}
~~~

- **@Property** khai báo property mà engine của jqwik sẽ thực thi.
- **@ForAll int value** yêu cầu sinh đầu vào cho parameter.
- **boolean true** nghĩa property thỏa; **false** là một trường hợp bác bỏ.
- **tries = 300** đặt ngân sách số lần thử theo quy tắc generator hiện hành.

jqwik thường dùng **1.000 tries mặc định** nếu không cấu hình khác, nhưng số checks thực tế có thể chịu tác động từ assumptions, cách sinh dữ liệu hoặc việc framework chọn exhaustive generation cho miền nhỏ.

**Một property chỉ đúng khi input sinh ra nằm trong miền mà property được phát biểu.** Ví dụ nếu hàm yêu cầu min <= max, đừng cho generator tạo min > max rồi bắt hàm phải trả một giá trị thay vì ném exception.

## 23. @Provide và Arbitrary tạo dữ liệu có ràng buộc

Với property cần hai đầu mốc **min <= max**, cách tốt là sinh hai endpoint rồi sắp xếp chúng ngay trong generator:

~~~java
package example;

import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;

class RangeLimiterProperties {
    record Range(int min, int max) {}

    @Provide
    Arbitrary<Range> ranges() {
        Arbitrary<Integer> endpoints =
            Arbitraries.integers().between(-1000, 1000);

        return Combinators.combine(endpoints, endpoints)
            .as((a, b) -> new Range(
                Math.min(a, b),
                Math.max(a, b)
            ));
    }

    @Property(tries = 500)
    boolean outputAlwaysInRange(
            @ForAll int value,
            @ForAll("ranges") Range range) {

        int actual = RangeLimiter.clamp(
            value, range.min(), range.max()
        );

        return range.min() <= actual && actual <= range.max();
    }

    @Property(tries = 500)
    boolean clampingTwiceChangesNothing(
            @ForAll int value,
            @ForAll("ranges") Range range) {

        int once = RangeLimiter.clamp(
            value, range.min(), range.max()
        );

        int twice = RangeLimiter.clamp(
            once, range.min(), range.max()
        );

        return once == twice;
    }

    @Property(tries = 500)
    boolean lowerBoundSaturates(
            @ForAll("ranges") Range range) {

        // min >= -1000 nên phép trừ 1 an toàn.
        int below = range.min() - 1;

        return RangeLimiter.clamp(
            below, range.min(), range.max()
        ) == range.min();
    }

    @Property(tries = 500)
    boolean interiorValueIsPreserved(
            @ForAll("ranges") Range range) {

        int middle = range.min()
            + (range.max() - range.min()) / 2;

        return RangeLimiter.clamp(
            middle, range.min(), range.max()
        ) == middle;
    }
}
~~~

Giải thích:

- **Arbitraries.integers().between(-1000, 1000)** giới hạn miền số.
- **Combinators.combine** tạo hai giá trị có thể kết hợp thành một đối tượng domain.
- **@Provide** là nguồn được **@ForAll("ranges")** tham chiếu.
- **Range** là record biểu diễn một đoạn hợp lệ.
- Các phép cộng/trừ trong ví dụ đều không tràn vì generator bị giới hạn ở [-1000,1000].

Không cần mở database, network hoặc dựa vào đồng hồ thật. Generator nên càng thuần túy càng tốt để việc tái hiện và shrinking ổn định.

## 24. Metamorphic test và tính đơn điệu

Một cách kiểm tra mà không cần biết output chính xác là xét quan hệ giữa kết quả của hai input có liên hệ với nhau.

Với clamp, nếu **a <= b** thì:

~~~text
clamp(a, min, max) <= clamp(b, min, max)
~~~

Thêm phương thức sau vào **RangeLimiterProperties** ở mục 23:

~~~java
@Property(tries = 500)
boolean clampingIsMonotonic(
        @ForAll int first,
        @ForAll int second,
        @ForAll("ranges") Range range) {

    int lower = Math.min(first, second);
    int higher = Math.max(first, second);

    int left = RangeLimiter.clamp(
        lower, range.min(), range.max()
    );

    int right = RangeLimiter.clamp(
        higher, range.min(), range.max()
    );

    return left <= right;
}
~~~

Đây là một **metamorphic relation**: biến đổi input theo một quan hệ có kiểm soát và so sánh hai kết quả.

Những ví dụ khác:

| Tính năng | Quan hệ có thể kiểm tra |
|---|---|
| Chuẩn hóa text | normalize(normalize(s)) = normalize(s) |
| Sắp xếp | Sort lần thứ hai không đổi kết quả |
| Serialize/deserialize | Giá trị round-trip tương đương theo hợp đồng |
| Tập hợp | Thêm phần tử đã có không đổi tập hợp |
| Pagination trên snapshot cố định | Kết hợp các trang không bỏ/trùng dữ liệu |
| Permission filtering | Giảm quyền không làm tập quyền truy cập lớn hơn |

Không tự coi mọi quan hệ trên là đúng khi nghiệp vụ không có invariant đó. Ví dụ phép chia, tiền tệ có làm tròn hoặc phân trang trên dữ liệu liên tục thay đổi có những điều kiện riêng.

## 25. Shrinking: từ lỗi khó hiểu đến phản ví dụ nhỏ

Khi một property thất bại, jqwik có thể cố giảm kích thước/độ phức tạp input:

~~~text
Input ban đầu:
  list = [45, -1002, 8, 0, 11, 6, 9, ...]

Sau shrinking (minh họa):
  list = [-1]

Giả thuyết: code xử lý sai phần tử âm.
~~~

Shrinking có thể thu gọn list, giảm số nguyên về gần 0, rút ngắn chuỗi hoặc thay cấu trúc theo các luật của Arbitrary.

**Shrinking không bảo đảm tìm được input nhỏ nhất tuyệt đối.** Kết quả chịu ảnh hưởng của miền generator, cấu trúc dữ liệu, cách kết hợp arbitrary, tính ổn định của lỗi và ngân sách shrinking. Một test bị race hoặc phụ thuộc network có thể khiến shrinking không tái hiện nhất quán.

Không viết một Arbitrary tùy biến bằng generator không hỗ trợ shrink mà vẫn kỳ vọng kết quả tự tối giản như generator có cấu trúc do framework hỗ trợ.

## 26. Ghi seed, replay và giữ regression case

Khi jqwik báo một counterexample, cần lưu:

- Property name và input tối giản.
- Seed đã được báo.
- Phiên bản jqwik, JUnit Platform và JDK.
- Generator/configuration tương ứng.
- Điều kiện môi trường ảnh hưởng tới lỗi.

Trình tự hữu ích:

1. Chạy lại theo **seed** và cấu hình của framework để tái hiện.
2. Xem phản ví dụ sau shrinking có làm lộ điều kiện sai thật không.
3. Viết một **test dữ liệu cố định** với phản ví dụ đó.
4. Xác nhận test cố định thất bại trước khi sửa code.
5. Sửa lỗi, xác minh directed test và property đều xanh.
6. Giữ regression test lâu dài ngay cả khi thay generator.

Một seed không bảo đảm tái hiện nếu generator/framework/data bên ngoài thay đổi. **Ca lỗi cố định** là biện pháp giữ tri thức bền hơn một dòng seed duy nhất.

Không dùng random seed không ghi lại rồi báo “CI thỉnh thoảng đỏ”; test không tái hiện được làm chậm việc điều tra.

## 27. Tránh generator bỏ quá nhiều mẫu

Một cách chưa tốt:

~~~java
// Minh họa anti-pattern trong jqwik.
@Property
boolean validRanges(
        @ForAll int min,
        @ForAll int max) {

    Assume.that(min >= 0 && max <= 100 && min <= max);

    return RangeLimiter.clamp(50, min, max) <= max;
}
~~~

Đoạn này cần import **net.jqwik.api.Assume** và các annotations; không phải ví dụ tích hợp hoàn chỉnh.

Vì **@ForAll int** sinh trong miền rất rộng, hầu hết cặp số bị bỏ bởi Assume. Framework có thể **discard** quá nhiều mẫu và không chạy đủ trường hợp hợp lệ.

Tốt hơn: xây trực tiếp **Arbitrary<Range>** như mục 23. Filtering có thể hợp lý khi điều kiện loại bỏ hiếm, nhưng generator có cấu trúc thường giúp diễn đạt miền rõ hơn và shrinking hoạt động hiệu quả hơn.

## 28. Property không thay thế test biên cố định

Một nghìn lượt thử chưa chắc chứa:

- **Integer.MIN_VALUE** hoặc **Integer.MAX_VALUE**.
- Một chuỗi đúng 1.024 byte UTF-8.
- Ngày **29/02** của năm nhuận.
- Ngày có chuyển DST vào đúng giờ gap/overlap.
- Một số đầu vào min == max trong cấu hình cụ thể.
- File nén ngắn nhưng giải nén vượt hàng trăm MB.
- Trạng thái hủy đúng lúc một tác vụ vừa hoàn tất.

PBT frameworks có thể trộn edge cases vào generation, nhưng không được phụ thuộc xác suất để đảm bảo từng trường hợp hiếm sẽ xuất hiện trong mọi lần chạy.

Nên kết hợp:

- **Directed boundary tests** chạy chắc chắn.
- **PBT** khám phá nhiều input trong miền.
- **Regression tests** lưu những ca lỗi trước.
- **Integration tests** kiểm chứng ranh giới I/O và framework.
- **Stress/concurrency tests** cho rủi ro lịch thực thi.

## 29. Overflow có thể bác bỏ một property tưởng đúng

Phát biểu:

~~~text
Với mọi số nguyên int x: Math.abs(x) >= 0.
~~~

Nghe có vẻ đúng trong toán học nhưng sai với **int**:

~~~java
int value = Integer.MIN_VALUE;

System.out.println(value);           // -2147483648
System.out.println(Math.abs(value)); // -2147483648
~~~

Giá trị tuyệt đối của **Integer.MIN_VALUE** không biểu diễn được dưới dạng int không âm. Hành vi tràn số ở đây khiến kết quả vẫn âm.

Bài học: trước khi viết property, phải xác định **loại số, chính sách overflow và miền đầu vào**. Một property có thể đúng trên **BigInteger** nhưng sai với int/long khi giới hạn biểu diễn được vượt quá.

Một PBT generator có thể không chạm đúng MIN_VALUE trong ngân sách nhỏ. Hãy giữ thêm directed test để bắt chắc chắn trường hợp này.

## 30. Khi chưa dùng PBT engine: test ngẫu nhiên có seed

**SplittableRandom** trong JDK có thể tạo input có seed tái hiện được. JUnit @Test dùng vòng lặp cho nhiều mẫu vẫn có ích:

~~~java
package example;

import java.util.SplittableRandom;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SeededExplorationTest {
    @Test
    void generatedValuesRemainWithinBounds() {
        long seed = 20261127L;
        SplittableRandom random = new SplittableRandom(seed);

        for (int caseIndex = 0; caseIndex < 10_000; caseIndex++) {
            int a = random.nextInt(-1000, 1001);
            int b = random.nextInt(-1000, 1001);
            int min = Math.min(a, b);
            int max = Math.max(a, b);
            int value = random.nextInt();

            int result = RangeLimiter.clamp(value, min, max);

            assertTrue(
                min <= result && result <= max,
                "seed=" + seed + ", case=" + caseIndex
                    + ", input=" + value + ", min=" + min
                    + ", max=" + max + ", result=" + result
            );
        }
    }
}
~~~

**Giới hạn:** test này không có engine shrinking tự động; việc phân phối và chọn trường hợp đặc biệt hoàn toàn do bạn tự lập trình. Nếu có lỗi, thông báo chứa seed và input giúp tạo lại một test cụ thể.

**Không dựa vào Java keyword assert** khi không chắc JVM đã bật **-ea**; ưu tiên JUnit Assertions hoặc trả boolean trong @Property.

## 31. Biên với số thực và BigDecimal

Với **double**, cần cân nhắc:

- **NaN**: so sánh thông thường có hành vi khác số hữu hạn.
- **Positive/negative infinity**.
- **-0.0 và +0.0**.
- Các giá trị sát biên theo biểu diễn floating-point.
- Sai số tích lũy và quy tắc làm tròn.

Không so sánh phép tính floating-point phức tạp bằng một equality tuyệt đối nếu hợp đồng chỉ yêu cầu sai số trong ngưỡng cho phép. Nhưng cũng **không chọn epsilon ngẫu nhiên** để che lỗi.

Với tiền tệ, dùng **BigDecimal** và quy tắc scale/rounding cụ thể:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("10.005");

BigDecimal rounded = amount.setScale(
    2,
    RoundingMode.HALF_UP
);

System.out.println(rounded); // 10.01
~~~

Test ở gần ranh giới làm tròn như 10.004, 10.005, 10.006, số âm và nhiều scale. Đừng dùng **new BigDecimal(0.1)** như cách biểu diễn chữ số thập phân chính xác được người dùng nhập.

## 32. Biên thời gian, locale và Unicode

**Thời gian:** cuối tháng, năm nhuận, DST, Instant deadline. Dùng **Clock.fixed** cho test phụ thuộc thời điểm hiện tại:

~~~java
import java.time.*;

Clock fixed = Clock.fixed(
    Instant.parse("2026-11-27T10:00:00Z"),
    ZoneOffset.UTC
);

Instant deadline = Instant.parse("2026-11-27T10:00:00Z");

boolean expired = !Instant.now(fixed).isBefore(deadline);
// true nếu thời điểm bằng deadline đã được coi là hết hạn
~~~

**Locale:** kết quả định dạng số và thời gian có thể khác với **Locale.US**, **vi-VN** và môi trường mặc định CI. Truyền Locale/ZoneId rõ ràng nếu đó là một phần của test.

**Unicode:** String.length tính UTF-16 code units; **codePointCount** đếm codepoints; UTF-8 byte length là khái niệm khác. Một emoji hoặc chữ tiếng Việt có dấu có thể khiến các con số khác nhau.

PBT cho string/date/time cần generator **phù hợp dữ liệu thật**, không chỉ chuỗi ASCII hoặc timestamp ngẫu nhiên không gắn timezone.

## 33. Stateful testing: kiểm tra chuỗi hành động

Nhiều hệ thống có trạng thái, nên test một lời gọi đơn lẻ không đủ.

Ví dụ tài khoản:

~~~text
Số dư đầu: 100
deposit(50) → 150
withdraw(20) → 130
withdraw(130) → 0
withdraw(1) → rejected, số dư giữ nguyên
~~~

Properties có thể là:

- Số dư không âm sau thao tác được chấp nhận.
- Thao tác bị từ chối không đổi trạng thái.
- Chuyển tiền giữa hai tài khoản giữ nguyên tổng nếu không có phí.
- Cùng chuỗi lệnh trên cùng trạng thái ban đầu dẫn đến kết quả nhất quán.
- Một command có idempotency key không được thực thi ghi lặp theo hợp đồng.

Stateful PBT dùng **model** tham chiếu và generator cho **sequence of actions**. Không coi việc sinh các actions độc lập là đủ, vì nhiều action chỉ hợp lệ sau một số trạng thái nhất định.

Với hệ thống có database, tách model-level tests ra khỏi integration tests dùng transaction và hạ tầng thật.

## 34. Property tests và concurrency

Một property trên nhiều input không tự phát hiện mọi race condition vì lỗi concurrency phụ thuộc **thread interleavings**, không chỉ giá trị tham số.

Ví dụ nhiều thread cùng thực hiện **counter++** trên state không được đồng bộ có thể mất cập nhật.

Khi kiểm thử concurrency:

1. Định nghĩa rõ invariants như không mất cập nhật/không duplicate.
2. Dùng **CountDownLatch**, **Future.get(timeout)**, barrier hoặc công cụ đồng bộ phù hợp.
3. Không dùng **Thread.sleep** để giả định chắc thread khác đã chạy.
4. Kiểm tra cancellation, interruption, timeout và resource cleanup.
5. Thử trên nhiều tải khi cần, không coi một lần xanh là đã chứng minh thread safety.
6. Với Memory Model phức tạp, cân nhắc công cụ kiểm thử concurrency chuyên biệt.

PBT input generation có thể hỗ trợ chọn chuỗi thao tác, nhưng không thay thế việc kiểm soát và quan sát lịch thực thi.

## 35. Test phải độc lập và failure report phải hữu ích

Một parameterized invocation tốt cần hiển thị đủ:

- Trường hợp nào thất bại.
- Input và expected/actual.
- Bất biến/hợp đồng bị vi phạm.
- Cách tái hiện, nếu là dữ liệu sinh.
- Dữ liệu nào có thể log mà không lộ thông tin nhạy cảm.

~~~java
@ParameterizedTest(name = "case {index}: value={0}")
@CsvSource({
    "-11, -10, 10, -10",
    "11, -10, 10, 10"
})
void reportsUsefulFailure(
        int input, int min, int max, int expected) {

    assertEquals(
        expected,
        RangeLimiter.clamp(input, min, max),
        "Incorrect clamp result for input=" + input
    );
}
~~~

Đoạn này cần các imports JUnit tương ứng như những lớp test đầy đủ đã minh họa.

**Ngăn flaky tests:** không chia sẻ mutable static state giữa các case, không phụ thuộc thứ tự, không gọi live API trong unit test, không dựa giờ thực hoặc timezone mặc định, đóng executor/file/socket và reset fixture đúng cách.

Parameterized tests **không tự bảo đảm** cô lập toàn bộ resources bên ngoài. Nếu bật parallel execution, kiểm tra thread-safety của dữ liệu và cấu hình.

## 36. Coverage và mutation testing

**Line coverage** cho biết code đã được thực thi, không bảo đảm code đã được xác minh đúng bằng assertions.

~~~java
@Test
void lowValueTest() {
    RangeLimiter.clamp(100, 0, 10);
    // Không assertion: dù kết quả sai, test có thể vẫn xanh.
}
~~~

**Mutation testing** tạo các thay đổi nhỏ trong production code (đảo toán tử, bỏ nhánh, thay điều kiện...) rồi xem test có phát hiện sai lệch không. Trong Java, **PIT** là một công cụ mutation testing hiện hành cần kiểm tra phiên bản tương thích với JDK/build cụ thể.

Một bộ test có coverage cao nhưng yếu có thể không phát hiện việc đổi **<=** thành **<** hoặc bỏ kiểm tra invalid range. **Boundary tests + properties + mutation signals** giúp đánh giá chất lượng tốt hơn việc chỉ theo đuổi tỷ lệ dòng đã chạy.

## 37. Ví dụ tổng hợp: suite JUnit cho RangeLimiter

Cấu trúc tối thiểu:

~~~text
project/
├── build.gradle
└── src/
    ├── main/java/example/
    │   └── RangeLimiter.java
    └── test/java/example/
        ├── RangeLimiterTest.java
        └── SeededExplorationTest.java
~~~

**Tệp src/test/java/example/RangeLimiterTest.java:**

~~~java
package example;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.*;

class RangeLimiterTest {
    @ParameterizedTest(name = "clamp case {index}: {0}")
    @CsvSource({
        "-2147483648, -10, 10, -10",
        "-11, -10, 10, -10",
        "-10, -10, 10, -10",
        "0, -10, 10, 0",
        "10, -10, 10, 10",
        "11, -10, 10, 10",
        "2147483647, -10, 10, 10",
        "5, 5, 5, 5"
    })
    void clampMatchesCases(
            int value, int min, int max, int expected) {
        assertEquals(
            expected,
            RangeLimiter.clamp(value, min, max)
        );
    }

    @ParameterizedTest
    @CsvSource({"10, 9", "1, 0", "-5, -6"})
    void invalidRangeFails(int min, int max) {
        assertThrowsExactly(
            IllegalArgumentException.class,
            () -> RangeLimiter.clamp(0, min, max)
        );
    }

    @ParameterizedTest
    @ValueSource(strings = {"A", "A-7", "AB123456", "A-------"})
    void validCodes(String value) {
        assertTrue(RangeLimiter.isValidCode(value));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "\t", "a", "1ABC", "ABCDEFGHI", "A/B"})
    void invalidCodes(String value) {
        assertFalse(RangeLimiter.isValidCode(value));
    }
}
~~~

Dùng class **RangeLimiter.java** ở mục 4 và **build.gradle** ở mục 5 để thực thi bộ test trên một dự án đã được tạo sẵn.

**jqwik RangeLimiterProperties** ở mục 23 dùng **cấu hình riêng của mục 21**. Chỉ đưa các class của hai công nghệ vào cùng một test runtime sau khi chọn phiên bản JUnit Platform và engines tương thích.

## 38. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Chỉ test một giá trị bình thường | Bỏ lỡ điều kiện biên | Dùng phân lớp và bảng biên |
| Có hàng trăm case cùng một phân lớp | Chi phí cao, ít thêm ý nghĩa | Chọn dữ liệu có rủi ro khác nhau |
| Dùng ValueSource cho nhiều biến phụ thuộc | Khó diễn đạt expected | CsvSource/MethodSource |
| Nhầm null với empty trong CSV | Test input khác dự định | Kiểm tra quy tắc quote |
| Truyền NullSource cho int | Lỗi argument conversion | Dùng wrapper hoặc nguồn phù hợp |
| Expected dùng đúng thuật toán SUT | Có thể cùng sai | Oracle từ hợp đồng, properties độc lập |
| PBT không ghi seed | Không tái hiện được | Lưu seed và counterexample |
| Generator bỏ quá nhiều mẫu | Ít kiểm thử hợp lệ | Sinh miền hợp lệ trực tiếp |
| Property quá yếu | Test xanh dù code sai | Thêm nhiều invariant độc lập |
| Chỉ PBT mà không có biên cố định | Trường hợp hiếm có thể không xuất hiện | Directed boundary tests |
| Coi shrinking luôn tối ưu toàn cục | Có thể bỏ qua lỗi phức tạp | Hiểu shrink strategy và miền |
| Ghép JUnit 6 và jqwik Platform 1.x tùy tiện | Runtime/dependency conflict | Chọn tập phiên bản tương thích |
| Shared mutable fixture | Flaky, phụ thuộc thứ tự | Khởi tạo/reset độc lập |
| Dùng clock hệ thống khi test expiry | Thất bại tùy thời điểm CI | Inject Clock |
| Dùng live network trong unit tests | Không ổn định và chậm | Fake/stub; integration tests riêng |
| Chạy random vô hạn trong CI | Không kiểm soát chi phí | Tries/time budget xác định |
| Chỉ coi coverage là chất lượng | Assertion có thể không kiểm tra gì | Mutation và property/boundary tests |
| Không giữ phản ví dụ PBT | Lỗi có thể tái xuất hiện | Thêm regression test |

## 39. Bài tập thực hành

**Bài 1 — Các biên số nguyên:** Viết hàm chấp nhận pageSize từ 1 đến 100; tạo ít nhất bảy dữ liệu quanh hai biên, và dùng @CsvSource với expected rõ ràng.

**Bài 2 — Null, empty, blank:** Dùng @NullAndEmptySource và ValueSource để kiểm tra tên kỹ thuật. Giải thích sự khác nhau giữa ba loại input.

**Bài 3 — MethodSource:** Kiểm tra giá giao hàng theo trọng lượng, vùng và loại dịch vụ. Dùng nhiều Arguments.of có expected cùng lời mô tả case.

**Bài 4 — CSV resource:** Chuyển bảng test sang resources, thêm trường hợp chứa dấu phẩy và chuỗi rỗng; quan sát quote semantics của CsvFileSource.

**Bài 5 — Property clamp:** Tạo Arbitrary<Range>, kiểm tra within-bounds, idempotence, monotonicity và giữ nguyên điểm bên trong đoạn.

**Bài 6 — Phản ví dụ overflow:** Kiểm tra Math.abs(Integer.MIN_VALUE); phân biệt thuộc tính toán học với hành vi kiểu int.

**Bài 7 — Unicode:** Với display name tối đa 30 codepoints và 120 UTF-8 bytes, viết test cho chữ tiếng Việt, emoji và combining marks.

**Bài 8 — Thời gian:** Dùng Clock.fixed kiểm thử expiry đúng bằng deadline, trước và sau deadline; bổ sung lịch cuối tháng và DST khi liên quan nghiệp vụ.

**Bài 9 — Stateful:** Sinh chuỗi add/remove sản phẩm vào giỏ hàng; xác minh số lượng không âm và thao tác lỗi không đổi trạng thái.

**Bài 10 — Đánh giá suite:** Tìm một method đã có coverage nhưng ít assertions; thêm directed boundaries và một property độc lập, sau đó thử mutation testing trên môi trường được phép.

## 40. Checklist chất lượng trước khi merge

- [ ] Test dựa trên **hợp đồng**, không sao chép implementation vào expected.
- [ ] Có phân lớp valid/invalid/missing/special.
- [ ] Có min, max, ngay bên trong và ngay bên ngoài biên khi có thể.
- [ ] Có null/empty/blank và Unicode nếu miền cho phép.
- [ ] Chọn đúng Value/Csv/Method/CsvFile source.
- [ ] Hiểu quoting/null conventions của CsvSource và CsvFileSource.
- [ ] Không truyền null tới tham số primitive.
- [ ] Negative tests kiểm tra đúng exception/error contract.
- [ ] Property có miền xác định và invariant thực sự có ý nghĩa.
- [ ] Generator sinh dữ liệu hợp lệ, không discard quá nhiều.
- [ ] Giới hạn tries/time budget cho CI.
- [ ] Lưu seed, input tối giản và môi trường khi property thất bại.
- [ ] Chuyển counterexample thành regression test cố định.
- [ ] Không xem PBT như thay thế kiểm thử biên.
- [ ] Dùng fixed clock và locale/ZoneId khi test ngày giờ.
- [ ] Không có shared mutable state hoặc thứ tự test ẩn.
- [ ] Không phụ thuộc live production services trong unit tests.
- [ ] Có kiểm thử integration/concurrency riêng theo rủi ro.
- [ ] Các phiên bản JUnit Platform, engines và PBT framework đã được align.
- [ ] Báo cáo lỗi chứa case, input và expected/actual nhưng không lộ secrets.
- [ ] Coverage và mutation score chỉ là tín hiệu bổ sung.
- [ ] Chạy CI trên JDK và build tool được dự án hỗ trợ.

**Kết luận:** Parameterized tests diễn đạt những **ví dụ có chủ đích và giá trị biên**, còn PBT cho phép kiểm tra **bất biến trên nhiều dữ liệu được sinh** và tìm phản ví dụ dễ phân tích hơn nhờ shrinking. Sự kết hợp hiệu quả cho mã Java 27 là dùng oracle độc lập, generator đúng miền, regression tests cho lỗi đã phát hiện, và quản lý phiên bản test engines một cách nhất quán. Một bộ test tốt không chỉ chạy xanh mà còn có khả năng bắt lỗi khi hợp đồng bị phá vỡ.

## Tài liệu tham khảo

- [JUnit 6.1.3 — Parameterized Classes and Tests](https://docs.junit.org/6.1.3/writing-tests/parameterized-classes-and-tests.html): @ParameterizedTest, @ValueSource, @CsvSource, @MethodSource, @NullAndEmptySource và chuyển kiểu tham số.
- [JUnit 6.1.3 — Build Support](https://docs.junit.org/6.1.3/running-tests/build-support.html): cấu hình Gradle, BOM, Jupiter aggregator, Platform launcher.
- [JUnit 6.1.3 — Overview](https://docs.junit.org/6.1.3/overview.html): JUnit Platform/Jupiter/Vintage và runtime Java hỗ trợ.
- [JUnit 6.1.3 — Release Notes](https://docs.junit.org/6.1.3/release-notes): phiên bản ổn định, các thay đổi và ghi chú phát hành.
- [JUnit 6.1.3 — CsvSource API](https://docs.junit.org/6.1.3/api/org.junit.jupiter.params/org/junit/jupiter/params/provider/CsvSource.html): quoting, null, empty, delimiter.
- [JUnit 6.1.3 — CsvFileSource API](https://docs.junit.org/6.1.3/api/org.junit.jupiter.params/org/junit/jupiter/params/provider/CsvFileSource.html): nguồn CSV file và thiết lập quote.
- [jqwik 1.10.2 — User Guide](https://jqwik.net/docs/1.10.2/user-guide.html): @Property, Arbitrary, @ForAll, @Provide, shrinking, seed, stateful properties.
- [jqwik — Release Notes](https://jqwik.net/release-notes.html): phiên bản và tương thích runtime.
- [Java SE 27 — SplittableRandom](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SplittableRandom.html): dữ liệu ngẫu nhiên có seed.
- [Java SE 27 — Math](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html): Math.min, Math.max, Math.abs và xử lý giới hạn.
- [Java SE 27 — Clock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html): đồng hồ xác định cho unit tests.
- [PIT — Mutation Testing for Java](https://pitest.org/): đánh giá khả năng phát hiện sai lệch của test suite.
