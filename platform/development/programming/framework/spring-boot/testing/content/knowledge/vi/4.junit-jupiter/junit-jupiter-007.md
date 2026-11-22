# Kiểm thử giá trị null, rỗng, biên và tổ hợp đầu vào bằng JUnit Jupiter

## 1. Mục tiêu: kiểm thử đúng miền đầu vào, không chỉ đường đi thông thường

Một phương thức Spring Boot có thể hoạt động tốt với dữ liệu mẫu nhưng vẫn lỗi khi tham số không được gửi, chuỗi chỉ chứa khoảng trắng, số đúng tại giới hạn hoặc nhiều điều kiện xuất hiện đồng thời. Thay vì viết hàng trăm test ngẫu nhiên, ta chia miền đầu vào thành các nhóm có ý nghĩa, chọn điểm đại diện và kiểm tra các tương tác giữa nhiều tham số.

Sau bài này, bạn có thể:
- Phân biệt **null**, **rỗng (empty)**, **chỉ chứa khoảng trắng (blank)**, giá trị không hợp lệ và giá trị hợp lệ; không đánh đồng chúng.
- Chọn giá trị **ngay dưới, đúng tại và ngay trên** các ranh giới min/max bằng phân tích giá trị biên (boundary value analysis).
- Dùng **@NullSource, @EmptySource, @NullAndEmptySource, @ValueSource, @CsvSource, @MethodSource** của JUnit Jupiter để tổ chức dữ liệu kiểm thử.
- Lập ma trận tổ hợp đầu vào, hiểu khi nào dùng đầy đủ tổ hợp và khi nào nên giảm số trường hợp theo rủi ro.
- Kiểm chứng cùng yêu cầu ở mức hàm Java và ở ranh giới HTTP của Spring Boot bằng MockMvc, vì giá trị nhận được sau binding có thể khác chuỗi trong URL.

**Nguyên tắc:** Mỗi test phải chứng minh một yêu cầu. Test pass không có nghĩa đã bao phủ mọi đầu vào; phạm vi kiểm thử chỉ rõ khi xác định được các lớp tương đương, biên và tương tác quan trọng.

## 2. Phân biệt null, empty, blank và các trường hợp liên quan

Đầu vào thuộc các trạng thái sau có thể đòi hỏi phản ứng khác nhau:

| Đầu vào Java | Ý nghĩa | Cách kiểm tra phù hợp |
|---|---|---|
| null | Không có đối tượng/giá trị tham chiếu | value == null; không gọi method trên value |
| "" | String tồn tại, có độ dài bằng 0 | value.isEmpty() hoặc length() == 0 |
| " " | Có một dấu cách, không rỗng nhưng blank | value.isBlank() trả true |
| "\t\n" | Có tab và xuống dòng; không rỗng nhưng blank | value.isBlank() trả true |
| "ab" | Hai ký tự, có dữ liệu nhưng có thể chưa đạt độ dài tối thiểu | Kiểm tra length theo yêu cầu |
| "abc" | Ba ký tự, có thể đúng tại ranh giới tối thiểu | Kiểm tra quy tắc min/max |
| List.of() | Collection tồn tại, số phần tử bằng 0 | collection.isEmpty() |
| new String[0] | Array tồn tại nhưng không có phần tử | array.length == 0 |
| Integer age = null | Không có số tuổi | Kiểm tra null trước khi so sánh |
| Integer age = 0 | Có giá trị số 0; không phải null | So với miền giá trị hợp lệ |

Trong Java 17:
- **String.isEmpty()** kiểm tra độ dài đúng bằng 0. Chuỗi " " không empty.
- **String.isBlank()** nhận diện chuỗi rỗng hoặc chỉ chứa code point được Java xem là whitespace; nó không được định nghĩa là nhận mọi ký tự trông giống khoảng trắng trên màn hình.
- **String.length()** đếm đơn vị mã UTF-16, không nhất thiết đếm ký tự người dùng nhìn thấy. Với tên người dùng Unicode/emoji, cần xác định quy tắc đo độ dài (code unit, code point hay grapheme cluster) trước khi đặt biên.
- **String.trim(), strip()** thay đổi dữ liệu trước khi kiểm tra; quyết định chuẩn hóa hay từ chối chuỗi có khoảng trắng phải xuất phát từ yêu cầu nghiệp vụ. Đừng tự ý trim trong test nếu production không trim.
- **Collection rỗng** khác **Collection null**, và Collection chứa một phần tử null cũng khác cả hai; List.of(null) không được Java chấp nhận.

Ví dụ một kiểm tra dễ gây NullPointerException:

~~~java
// Sai nếu username == null:
if (username.isEmpty()) {
    // ...
}

// Thứ tự an toàn:
if (username == null) {
    // Xử lý thiếu giá trị.
} else if (username.isEmpty()) {
    // Xử lý chuỗi có độ dài 0.
} else if (username.isBlank()) {
    // Xử lý chuỗi chỉ có whitespace.
}
~~~

Đoạn trên minh họa cấu trúc điều kiện, chưa phải một chương trình độc lập. Khi thiết kế API, hãy phân biệt yêu cầu “tham số phải hiện diện” với “tham số phải có nội dung” và “nội dung phải hợp lệ”; đây là ba điều kiện có thể cần ba nhóm test.

## 3. Phân vùng tương đương trước khi chọn dữ liệu

**Phân vùng tương đương (equivalence partitioning)** là chia miền đầu vào thành những nhóm mà hệ thống dự kiến xử lý giống nhau. Ta chọn vài điểm đại diện của mỗi nhóm để giảm test lặp mà vẫn kiểm tra ý nghĩa nghiệp vụ.

Giả sử chức năng kiểm tra tên đăng ký có quy tắc minh họa:

1. null → **MISSING**.
2. String độ dài 0 → **EMPTY**.
3. String chỉ gồm khoảng trắng → **BLANK**.
4. Tên có độ dài nhỏ hơn 3 → **TOO_SHORT**.
5. Tên có độ dài lớn hơn 12 → **TOO_LONG**.
6. Còn lại → **VALID**.

**Lưu ý về đặc tả:** Chức năng mẫu đo độ dài bằng String.length(), không tự strip/trim và không giới hạn bảng chữ cái. Do đó " abc " có độ dài 5 và được xem là VALID. Nếu sản phẩm yêu cầu loại bỏ whitespace ở đầu/cuối, cần sửa cả đặc tả lẫn implementation/test.

Bảng phân vùng:

| Nhóm | Dữ liệu đại diện | Kết quả |
|---|---|---|
| Thiếu tham chiếu | null | MISSING |
| Chuỗi rỗng | "" | EMPTY |
| Chuỗi chỉ gồm whitespace | " ", "\t" | BLANK |
| Dài dưới 3 | "a", "ab" | TOO_SHORT |
| Trong khoảng 3–12 | "abc", "abcd", "abcdefghijkl" | VALID |
| Dài trên 12 | "abcdefghijklm" | TOO_LONG |

Chỉ phân vùng là chưa đủ: nếu lập trình viên viết nhầm so sánh độ dài <= 3 thành < 3, dữ liệu dài 6 vẫn có thể pass. Đó là lý do phải kết hợp kiểm thử giá trị biên.

## 4. Kiểm thử giá trị biên (BVA) — m − 1, m, m + 1

Lỗi thường nằm ở toán tử so sánh (<, <=, >, >=), index, giới hạn số lượng và phép chuyển kiểu. Với khoảng hợp lệ **[min, max]** tính cả hai đầu mút, bộ dữ liệu tối thiểu giàu ý nghĩa gồm:

- min − 1: ngay dưới giới hạn dưới, phải từ chối.
- min: đúng giới hạn dưới, phải chấp nhận.
- min + 1: ngay trên giới hạn dưới, phải chấp nhận.
- max − 1: ngay dưới giới hạn trên, phải chấp nhận.
- max: đúng giới hạn trên, phải chấp nhận.
- max + 1: ngay trên giới hạn trên, phải từ chối.

Ví dụ tên hợp lệ 3–12 đơn vị mã UTF-16:

| Độ dài | Chuỗi | Kết quả mong đợi |
|---|---|---|
| 2 | "ab" | TOO_SHORT |
| 3 | "abc" | VALID |
| 4 | "abcd" | VALID |
| 11 | "abcdefghijk" | VALID |
| 12 | "abcdefghijkl" | VALID |
| 13 | "abcdefghijklm" | TOO_LONG |

Với tuổi hợp lệ từ 18 đến 120 (bao gồm hai biên), chọn **17, 18, 19, 119, 120, 121** và thêm null nếu dữ liệu không được gửi. Không thể dùng cùng một ca số 0 để thay cho cả hai biên; các lỗi off-by-one cần điểm ở sát từng giới hạn.

Phạm vi số cần kiểm tra rộng hơn khi dùng kiểu nguyên thủy: ví dụ Integer.MIN_VALUE, Integer.MAX_VALUE, tràn số khi cộng và cách parse dữ liệu không phải số. Các trường hợp ấy chỉ nên bổ sung nếu phương thức/API có thể nhận giá trị đó và rủi ro thực tế cần kiểm tra. Nếu điều kiện là “dài dưới hoặc bằng 12” thay vì “dưới 12”, phải cập nhật bảng kỳ vọng theo đặc tả.

## 5. Các annotation nguồn dữ liệu trong JUnit Jupiter

JUnit Jupiter hỗ trợ **@ParameterizedTest** để chạy cùng một phương thức test nhiều lần với bộ tham số khác nhau. Từng lượt chạy là một invocation riêng, có assertion và kết quả riêng trong báo cáo.

| Annotation | Khi sử dụng | Hạn chế cần biết |
|---|---|---|
| @NullSource | Cần một lượt chạy truyền null | Không dùng cho tham số kiểu nguyên thủy int/boolean; dùng Integer/Boolean |
| @EmptySource | Cần giá trị empty được hỗ trợ, thường là String "" hoặc một số kiểu collection/array | Không sinh whitespace; kiểu tham số phải thuộc nhóm được hỗ trợ |
| @NullAndEmptySource | Gộp null + empty cho một tham số | Không tự sinh " " hay các tình huống nhiều tham số |
| @ValueSource | Danh sách một tham số đơn giản: strings, ints, longs… | Không nhận nhiều cột; không truyền null trực tiếp |
| @CsvSource | Bảng nhiều cột ngắn, thuận tiện cho expected value | Cần hiểu cách viết giá trị null/empty, dấu quote, phép chuyển kiểu |
| @MethodSource | Sinh bộ tham số phức tạp, đối tượng, null, Stream<Arguments>, tổ hợp | Factory trong cùng class thường phải static, trừ lifecycle PER_CLASS |

Ví dụ ngắn với null và chuỗi rỗng:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

@ParameterizedTest
@NullAndEmptySource
void missingOrEmptyNeverValid(String name) {
    assertNotEquals(RegistrationRules.UsernameStatus.VALID,
            RegistrationRules.classifyUsername(name));
}
~~~

Đây là **phương thức mẫu** đặt bên trong class test, không phải file Java độc lập. Nó tạo hai lượt chạy, một với null và một với "". **Không** bao gồm trường hợp " ". Muốn thêm dữ liệu chỉ chứa whitespace, dùng @ValueSource(strings = {" ", "\t", "\n"}) hoặc @MethodSource.

**Điểm dễ sai với @CsvSource:** Một trường không có ký tự giữa hai dấu phẩy thường được diễn giải thành null. Một trường được quote rỗng bằng dấu quote phù hợp (mặc định dấu nháy đơn) cho ra chuỗi rỗng; hai giá trị này không tương đương. Có thể dùng nullValues và emptyValue khi muốn quy định rõ cách diễn giải. Nên dùng @MethodSource nếu dữ liệu nhiều cột có dấu phẩy, xuống dòng hoặc cần phân biệt null/empty thật rõ.

## 6. Ví dụ hoàn chỉnh chạy được với Spring Boot 3.3.5, Java 17 và Gradle

Ví dụ dùng một quy tắc đăng ký nhỏ để thấy cả **null**, **empty**, **blank**, **biên** và **tổ hợp**. Có hai phần:

- **Kiểm thử thuần Java bằng JUnit Jupiter:** Kiểm tra quy tắc chính xác, chạy nhanh, không cần Spring ApplicationContext.
- **Kiểm thử ranh giới HTTP bằng MockMvc:** Kiểm tra request parameter được Spring MVC chuyển thành Java argument ra sao trước khi đi vào quy tắc.

Đặc tả bổ sung cho ví dụ: yêu cầu tên VALID, tuổi từ 18 đến 120 (bao gồm hai đầu), và đã đồng ý điều khoản. Không có xử lý lưu tài khoản hoặc nghiệp vụ bảo mật; endpoint GET chỉ trả kết quả kiểm tra, không đăng ký tài khoản thật.

Cấu trúc dự án:

~~~text
settings.gradle
build.gradle
src/main/java/demo/testing/TestingApplication.java
src/main/java/demo/testing/RegistrationRules.java
src/main/java/demo/testing/RegistrationController.java
src/test/java/demo/testing/RegistrationRulesTest.java
src/test/java/demo/testing/RegistrationHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'jupiter-input-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Spring Boot starter-test cung cấp Jupiter và những tiện ích như AssertJ, Mockito, Spring Test; ví dụ này dùng Jupiter trực tiếp và MockMvc. Lệnh useJUnitPlatform() yêu cầu Gradle chạy test theo JUnit Platform. Ví dụ dùng cấu hình Spring Boot/Gradle cố định để minh họa; khi áp dụng vào dự án có sẵn nên dùng bộ phiên bản đang được dự án quản lý.

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/testing/RegistrationRules.java**

~~~java
package demo.testing;

public final class RegistrationRules {
    private RegistrationRules() {
    }

    public enum UsernameStatus {
        MISSING, EMPTY, BLANK, TOO_SHORT, TOO_LONG, VALID
    }

    public static UsernameStatus classifyUsername(String username) {
        if (username == null) {
            return UsernameStatus.MISSING;
        }
        if (username.isEmpty()) {
            return UsernameStatus.EMPTY;
        }
        if (username.isBlank()) {
            return UsernameStatus.BLANK;
        }
        if (username.length() < 3) {
            return UsernameStatus.TOO_SHORT;
        }
        if (username.length() > 12) {
            return UsernameStatus.TOO_LONG;
        }
        return UsernameStatus.VALID;
    }

    public static boolean eligible(
            String username, Integer age, boolean acceptedTerms) {
        return classifyUsername(username) == UsernameStatus.VALID
                && age != null
                && age >= 18
                && age <= 120
                && acceptedTerms;
    }
}
~~~

Hàm phân loại có thứ tự kiểm tra chủ ý: tránh gọi isEmpty()/isBlank() trên null, đồng thời phân biệt empty với blank. Integer cho age vì muốn kiểm tra cả giá trị null; age >= 18 an toàn do toán tử && đánh giá ngắn mạch sau age != null. Một tên có khoảng trắng ở hai bên vẫn được tính theo chiều dài ban đầu; đây là quy tắc minh họa đã công bố.

**src/main/java/demo/testing/RegistrationController.java**

~~~java
package demo.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registration")
class RegistrationController {

    record EligibilityResult(String usernameStatus, boolean eligible) {
    }

    @GetMapping("/check")
    EligibilityResult check(
            @RequestParam(required = false) String username,
            @RequestParam(required = false) Integer age,
            @RequestParam(defaultValue = "false") boolean acceptedTerms) {
        return new EligibilityResult(
                RegistrationRules.classifyUsername(username).name(),
                RegistrationRules.eligible(username, age, acceptedTerms));
    }
}
~~~

Một request hợp lệ kiểu:

~~~text
GET /api/registration/check?username=abc&age=18&acceptedTerms=true
~~~

trả JSON có usernameStatus bằng VALID và eligible bằng true. Khi username hoàn toàn không xuất hiện, tham số String không bắt buộc nhận null; khi gửi username=, nó nhận chuỗi rỗng. Những quy tắc binding này là lý do nên có test HTTP bên cạnh unit test. Đối với acceptedTerms, defaultValue = "false" được áp dụng nếu thiếu hoặc để trống tham số; đó là quyết định của ví dụ, không phải kết luận chung cho mọi API.

### 6.1. Test các lớp tương đương và ranh giới bằng @MethodSource

**src/test/java/demo/testing/RegistrationRulesTest.java**

~~~java
package demo.testing;

import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.params.provider.Arguments;

import static demo.testing.RegistrationRules.UsernameStatus;
import static org.junit.jupiter.api.Assertions.*;

class RegistrationRulesTest {

    @ParameterizedTest(name = "{index}: username={0} => {1}")
    @MethodSource("usernameCases")
    void classifiesUsername(
            String username, UsernameStatus expected) {
        assertEquals(
                expected, RegistrationRules.classifyUsername(username));
    }

    static Stream<Arguments> usernameCases() {
        return Stream.of(
                Arguments.of(null, UsernameStatus.MISSING),
                Arguments.of("", UsernameStatus.EMPTY),
                Arguments.of(" ", UsernameStatus.BLANK),
                Arguments.of("\t\n", UsernameStatus.BLANK),
                Arguments.of("ab", UsernameStatus.TOO_SHORT),
                Arguments.of("abc", UsernameStatus.VALID),
                Arguments.of("abcd", UsernameStatus.VALID),
                Arguments.of("abcdefghijk", UsernameStatus.VALID),
                Arguments.of("abcdefghijkl", UsernameStatus.VALID),
                Arguments.of("abcdefghijklm", UsernameStatus.TOO_LONG),
                Arguments.of(" abc ", UsernameStatus.VALID)
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    void nullAndEmptyAreDifferentFromValidName(String username) {
        assertNotEquals(
                UsernameStatus.VALID,
                RegistrationRules.classifyUsername(username));
    }

    @ParameterizedTest
    @ValueSource(strings = {" ", "\t", "\n"})
    void whitespaceOnlyIsBlank(String username) {
        assertEquals(
                UsernameStatus.BLANK,
                RegistrationRules.classifyUsername(username));
    }

    @ParameterizedTest(name = "{index}: age={0}, valid={1}")
    @CsvSource({
            "17, false",
            "18, true",
            "19, true",
            "119, true",
            "120, true",
            "121, false"
    })
    void checksAgeBoundaries(int age, boolean expected) {
        assertEquals(
                expected,
                RegistrationRules.eligible("alice", age, true));
    }

    @ParameterizedTest
    @NullSource
    void nullAgeIsRejected(Integer age) {
        assertFalse(RegistrationRules.eligible("alice", age, true));
    }

    @Test
    void falseConsentIsRejected() {
        assertFalse(
                RegistrationRules.eligible("alice", 18, false));
    }

    private record NameSample(String value, boolean valid) {
    }

    private record AgeSample(Integer value, boolean valid) {
    }

    @ParameterizedTest(
            name = "{index}: username={0}, age={1}, terms={2} => {3}")
    @MethodSource("registrationCombinations")
    void testsInputCombinations(
            String username, Integer age,
            boolean acceptedTerms, boolean expected) {
        assertEquals(
                expected,
                RegistrationRules.eligible(
                        username, age, acceptedTerms));
    }

    static Stream<Arguments> registrationCombinations() {
        List<NameSample> names = List.of(
                new NameSample(null, false),
                new NameSample("", false),
                new NameSample("ab", false),
                new NameSample("abc", true),
                new NameSample("abcdefghijkl", true),
                new NameSample("abcdefghijklm", false)
        );

        List<AgeSample> ages = List.of(
                new AgeSample(null, false),
                new AgeSample(17, false),
                new AgeSample(18, true),
                new AgeSample(120, true),
                new AgeSample(121, false)
        );

        return names.stream().flatMap(name ->
                ages.stream().flatMap(age ->
                        Stream.of(false, true).map(terms ->
                                Arguments.of(
                                        name.value(), age.value(), terms,
                                        name.valid() && age.valid() && terms)
                        )
                )
        );
    }
}
~~~

**Điểm cần quan sát trong mã test:**

1. usernameCases() trả Stream<Arguments>, vì một lượt cần hai giá trị: input và expected. Với @MethodSource cùng class, factory là static khi chưa cấu hình @TestInstance(PER_CLASS).
2. @NullAndEmptySource tạo các trường hợp null và "", không tạo " ". @ValueSource cho " ", "\t", "\n" là các lượt kiểm tra khác.
3. @CsvSource chuyển chuỗi đầu vào thành int và boolean theo kiểu tham số của phương thức. Tên tuổi là int vì các lượt trong bảng đều có số; thử null phải dùng Integer trong một test riêng.
4. usernameCases() kiểm tra rõ ngưỡng độ dài 2/3/4 và 11/12/13. Việc so sánh **kết quả enum chính xác** tốt hơn chỉ assertNotNull.
5. Mẫu tên và tuổi của ma trận có **cờ expected độc lập** (valid hay không theo yêu cầu) trước khi gọi hàm production. Giá trị expected cuối cùng dựa trên bảng nghiệp vụ “tên hợp lệ AND tuổi hợp lệ AND đồng ý điều khoản”, không gọi lại method đang được kiểm tra để tạo expected.
6. List.of() chứa các bản ghi NameSample/AgeSample đều không null; trường value bên trong bản ghi có thể null. Điều này khác với List.of(null), sẽ gây NullPointerException.
7. Phương thức testsInputCombinations có nhiều lượt kiểm tra, nhưng báo cáo vẫn chỉ gồm một phương thức Java tham số hóa với các invocation riêng. Chọn thông báo name hiển thị dữ liệu sẽ giúp tìm lại đầu vào gây fail.

### 6.2. Test sau khi Spring MVC binding dữ liệu HTTP

**src/test/java/demo/testing/RegistrationHttpTest.java**

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationHttpTest {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
            "abc, VALID, true",
            "ab, TOO_SHORT, false",
            "abcdefghijklm, TOO_LONG, false"
    })
    void checksHttpInputAndExpectedResult(
            String username, String expectedStatus, boolean eligible)
            throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", username)
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value(expectedStatus))
                .andExpect(jsonPath("$.eligible").value(eligible));
    }

    @Test
    void missingQueryParameterBecomesNull() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value("MISSING"))
                .andExpect(jsonPath("$.eligible").value(false));
    }

    @Test
    void emptyQueryParameterIsNotNull() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", "")
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value("EMPTY"))
                .andExpect(jsonPath("$.eligible").value(false));
    }

    @Test
    void whitespaceQueryParameterIsBlank() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", " ")
                        .param("age", "18")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.usernameStatus").value("BLANK"))
                .andExpect(jsonPath("$.eligible").value(false));
    }

    @Test
    void invalidNumericQueryParameterReturns400() throws Exception {
        mvc.perform(get("/api/registration/check")
                        .param("username", "abc")
                        .param("age", "not-a-number")
                        .param("acceptedTerms", "true"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Ở đây MockMvc chạy qua cấu hình MVC của Spring Boot mà không cần mở cổng mạng thực. Test chỉ rõ ba tình huống **vắng tham số**, **gửi tham số rỗng** và **gửi whitespace**, mặc dù cả ba đều khiến eligible = false. Nếu chỉ assert eligible = false, lỗi binding làm mất khác biệt giữa MISSING/EMPTY/BLANK có thể bị bỏ sót.

Trường age phải chuyển thành Integer. Khi chuỗi "not-a-number" không thể bind thành Integer, Spring MVC thông thường trả HTTP 400 do lỗi chuyển kiểu; đây là bài test **tầng HTTP**, không phải kết quả của RegistrationRules. Nếu dự án có @ControllerAdvice hoặc quy tắc lỗi riêng, hãy xác nhận contract thực tế thay vì mặc định mọi ứng dụng đều trả cùng một body.

### 6.3. Chạy và đọc kết quả

Trong thư mục dự án, nếu đã có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Với PowerShell trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Nếu chưa có Wrapper, dùng Gradle tương thích đã cài để tạo Wrapper hoặc chạy gradle test. Các file trên là ví dụ đầy đủ cho phần source và build; lệnh ./gradlew chỉ hoạt động khi các tệp Wrapper cũng tồn tại.

Khi tất cả assertion đúng, Gradle test task hoàn thành thành công; xem báo cáo HTML tại **build/reports/tests/test/index.html**. Log và tổng số test hiển thị có thể thay đổi theo cấu hình Gradle, nhưng các trường hợp dự kiến gồm:

- 11 invocation ở usernameCases().
- 2 invocation của @NullAndEmptySource.
- 3 invocation của @ValueSource với whitespace.
- 6 invocation về tuổi qua @CsvSource.
- 1 invocation tuổi null và 1 invocation từ chối consent.
- **60 invocation** từ 6 trạng thái tên × 5 trạng thái tuổi × 2 giá trị đồng ý.
- 3 invocation HTTP với @CsvSource và 4 phương thức HTTP đơn lẻ.

Do đó tổng trường hợp trong bộ ví dụ này là **91 lượt** (84 lượt unit và 7 lượt HTTP), nếu không có test khác được thêm vào dự án. Một vòng test thất bại hiển thị input tương ứng trong tên invocation để xác định nguyên nhân. Nếu thay đổi dữ liệu hoặc filter test, số lượt sẽ thay đổi; hãy kiểm tra báo cáo thật thay vì chỉ tin vào build xanh.

## 7. Tổ hợp đầu vào: tránh chỉ kiểm tra từng điều kiện riêng lẻ

Giả sử eligibility phụ thuộc ba trục:

| Trục | Giá trị đại diện | Số lựa chọn |
|---|---|---|
| Tên | null, "", "ab", "abc", dài 12, dài 13 | 6 |
| Tuổi | null, 17, 18, 120, 121 | 5 |
| Đồng ý điều khoản | false, true | 2 |

**Tích Descartes (full Cartesian product)** tạo 6 × 5 × 2 = 60 ca. Trong quy tắc hiện tại, chỉ 2 lựa chọn tên hợp lệ × 2 lựa chọn tuổi hợp lệ × 1 giá trị consent true = 4 ca được chấp nhận; 56 ca còn lại phải bị từ chối. Cách kết hợp này bắt được các lỗi tương tác như “khi age = null nhưng acceptedTerms = true thì hệ thống ném NullPointerException” hoặc “tên dài 13 được cho qua nếu tuổi hợp lệ”.

**Không phải lúc nào cũng nên chạy mọi tổ hợp.** Nếu có 10 tham số, mỗi tham số 5 giá trị, số ca full Cartesian là 5^10 = 9.765.625. Chiến lược thực tế:

1. Xác định các partition và biên quan trọng cho **từng** tham số trước.
2. Nếu ma trận nhỏ, dùng full combination, nhất là các rule cho phép/từ chối phối hợp.
3. Nếu ma trận quá lớn, ưu tiên các tổ hợp có rủi ro cao, ca hợp lệ, mỗi kiểu đầu vào không hợp lệ, biên cùng xảy ra, và các điều kiện phụ thuộc nhau.
4. Cân nhắc **pairwise** để mỗi cặp giá trị của hai trục xuất hiện trong ít nhất một ca; pairwise **không bảo đảm** phát hiện lỗi chỉ xuất hiện khi ba hoặc nhiều điều kiện cùng xảy ra.
5. Khi có các tổ hợp không thể xảy ra trong sản phẩm, mô tả ràng buộc thật và loại chúng một cách có chủ đích, không xóa ngẫu nhiên các ca test.
6. Ghi rõ lý do lựa chọn bộ dữ liệu và bổ sung ca mới mỗi khi production gặp lỗi ở một tổ hợp cụ thể.

JUnit Jupiter **không yêu cầu một annotation tích Descartes đặc biệt**: @MethodSource có thể tự tạo Stream<Arguments> với vòng lặp hoặc flatMap như ví dụ. Các thư viện bổ sung có thể cung cấp tiện ích kết hợp tham số, nhưng không cần để hiểu cơ chế cốt lõi.

## 8. Chọn dữ liệu kiểm thử theo từng kiểu đầu vào

### 8.1. String

Nên phân biệt: null, "", chỉ whitespace, rất ngắn, đúng min, vừa trên min, bình thường, vừa dưới max, đúng max, vượt max, Unicode/emoji, dấu câu và khoảng trắng đầu/cuối nếu đặc tả liên quan.

Nếu có chuẩn hóa (ví dụ strip, đổi chữ hoa/thường, Unicode normalization), hãy kiểm tra **trước và sau chuẩn hóa**. Quy tắc như “tối đa 12 ký tự hiển thị” phải định nghĩa chính xác cách đếm; String.length() không tự đáp ứng yêu cầu đó.

### 8.2. Số nguyên, số thập phân, số tiền

Kiểm tra null cho wrapper, 0, âm, dương, min−1/min/min+1, max−1/max/max+1, giá trị tối đa của kiểu dữ liệu nếu có khả năng nhận, và phép toán có thể tràn. Với BigDecimal, cân nhắc scale/rounding, so sánh bằng compareTo khi chỉ quan tâm giá trị số và kiểm tra rõ quy tắc làm tròn.

Phân biệt **kiểm thử rule Java** với **kiểm thử chuyển kiểu từ chuỗi HTTP**: “age=abc”, “age=” và age không được gửi có thể đi qua các đường binding khác nhau.

### 8.3. Collection, array và dữ liệu phân trang

Kiểm tra null collection, empty collection, một phần tử, số phần tử đúng giới hạn, vượt giới hạn, phần tử trùng, phần tử null (nếu container hỗ trợ), thứ tự, và index đầu/cuối. Một List có một phần tử null không phải List rỗng. Nếu API cấm null phần tử, test phải chứng minh nó bị từ chối.

Với page và size, các biên thường gồm page = 0 nếu đánh số từ 0, page = −1, size = 0, size = 1, size = max và size = max+1; không giả định mọi API dùng cùng quy tắc phân trang.

### 8.4. Enum, boolean và cặp tham số phụ thuộc

Enum có tập giá trị hữu hạn; kiểm tra các giá trị có ý nghĩa, trạng thái chưa hỗ trợ, cách xử lý token không hợp lệ ở tầng HTTP và null nếu đầu vào optional. Boolean không có ranh giới số nhưng có hai trạng thái false/true và có thể có trạng thái “không được gửi” nếu dùng Boolean wrapper. Khi tham số phụ thuộc nhau, luôn kiểm tra ít nhất một tình huống hợp lệ và một số tình huống mâu thuẫn.

## 9. Assertion và test design để không tạo cảm giác an toàn giả

### Kiểm tra kết quả cụ thể

Một assertion như assertNotNull(result) rất yếu nếu yêu cầu mong đợi enum TOO_LONG. Tốt hơn là assertEquals(TOO_LONG, result). Với lỗi exception, có thể dùng assertThrows để kiểm tra đúng loại exception và thông điệp quan trọng khi nó là một phần của contract; nhưng **không nên tự biến trường hợp null thành exception** nếu đặc tả muốn trả trạng thái MISSING.

### Tránh tính expected bằng chính hàm production

Sai ví dụ:

~~~java
// Test gần như vô nghĩa: gọi lại cùng method để tạo expected.
boolean expected = RegistrationRules.eligible("abc", 18, true);
assertEquals(expected, RegistrationRules.eligible("abc", 18, true));
~~~

Đúng hơn: đưa expected từ bảng quy tắc độc lập, ví dụ tên abc + tuổi 18 + consent true → true; tuổi 17 → false; tên null → false. Trong ma trận tổ hợp, cờ hợp lệ ở NameSample/AgeSample được **khai báo độc lập** và kết hợp theo đặc tả.

### Tránh các test trùng nhau vô ích

Có thể dùng một vài ca lặp giữa @NullAndEmptySource và bảng đầy đủ để minh họa tính năng Jupiter, nhưng dự án thực tế nên tổ chức dữ liệu tránh hàng chục assertion giống hệt mà không tăng khả năng phát hiện lỗi. Trái lại, **không được tối giản** đến mức bỏ mất biên hoặc một trạng thái có ý nghĩa.

### Chọn mức test thích hợp

- **Unit/Jupiter:** Nhanh, kiểm tra phân nhánh, ranh giới, tổ hợp với dữ liệu rõ ràng.
- **Spring MVC slice hoặc MockMvc:** Xác minh parse, binding, validation, status, JSON; không thay bằng việc gọi thẳng method.
- **Integration test với database/hệ thống thật:** Cần khi rule dựa trên constraint DB, uniqueness, transaction hoặc dịch vụ khác. Dùng dữ liệu độc lập, có cleanup/transaction phù hợp.
- **Contract test:** Cần nếu các mã lỗi, trường JSON, kiểu dữ liệu phải tương thích với consumer khác.

Một trường hợp có thể xuất hiện ở nhiều mức vì nó chứng minh rủi ro khác nhau; chẳng hạn null trong unit test chứng minh quy tắc Java, còn thiếu query parameter trong MockMvc chứng minh binding và mapping.

## 10. Lỗi phổ biến với JUnit Jupiter khi kiểm thử đầu vào

| Lỗi | Tại sao sai | Cách sửa |
|---|---|---|
| Chỉ thử input hợp lệ | Bỏ sót thiếu dữ liệu, rỗng, sai định dạng, biên | Lập partition và BVA trước khi code test |
| Gộp null, "" và " " vào một nhóm | Có thể dẫn đến kết quả hoặc đường xử lý khác nhau | Test riêng null/empty/blank theo contract |
| @NullSource áp dụng cho int | Kiểu nguyên thủy không nhận null | Dùng Integer hoặc test sai định dạng ở HTTP |
| Nghĩ @EmptySource tự cấp whitespace | Empty string khác whitespace | Thêm @ValueSource hoặc @MethodSource |
| Dùng @ValueSource cho nhiều cột/đối tượng phức tạp | Không đúng mục đích nguồn dữ liệu đơn | Dùng @CsvSource hay @MethodSource |
| @MethodSource không static khi dùng lifecycle mặc định | Jupiter không gọi được method factory như dự kiến | Đặt factory static, hoặc cấu hình lifecycle PER_CLASS có chủ đích |
| Nhầm CSV trống với chuỗi rỗng | Giá trị không quote có thể thành null, quote rỗng thành "" | Dùng cú pháp CSV/emptyValue/nullValues rõ ràng |
| Chỉ thử min và max, không thử hai phía | Khó bắt lỗi < so với <= | Thêm min−1/min+1/max−1/max+1 |
| Chỉ thử từng tham số riêng biệt | Không bắt lỗi tương tác giữa điều kiện | Tạo ma trận tổ hợp hoặc pairwise theo rủi ro |
| Dùng String.length() cho mọi khái niệm “ký tự” | UTF-16 code unit không bằng code point/grapheme | Xác định cách đếm đúng theo sản phẩm |
| Kỳ vọng HTTP giống với input truyền trực tiếp cho hàm | Framework có binding/default/validation riêng | Thêm MockMvc hoặc integration test tại boundary |
| Kết luận “build xanh = bao phủ đầy đủ” | Test có thể bị lọc, thiếu case hoặc assertion yếu | Xem report và đối chiếu coverage với bảng đặc tả |

## 11. Quy trình áp dụng cho endpoint thực tế

Khi nhận yêu cầu “đăng ký tên từ 3 đến 12 ký tự, tuổi 18–120, bắt buộc đồng ý điều khoản”, đi theo thứ tự:

1. **Viết bảng quyết định:** Nêu rõ cách xử lý null, empty, blank, Unicode, trim, dữ liệu không phải số, dấu biên và precedence giữa các lỗi. Nếu chưa rõ, xác nhận đặc tả trước khi quyết định expected.
2. **Lập partition:** Chọn một hoặc vài giá trị đại diện cho từng trạng thái của mỗi tham số.
3. **Lập BVA:** Ghi min−1, min, min+1, max−1, max, max+1; thêm null/empty nếu có nghĩa.
4. **Lập ma trận tổ hợp:** Tính tổng số case và chọn full combination hoặc một bộ giảm theo rủi ro, giữ những tổ hợp nguy hiểm.
5. **Viết JUnit Jupiter:** Dùng @ValueSource/@CsvSource cho bảng ngắn, @NullAndEmptySource cho tình huống đúng loại, @MethodSource khi cần nhiều tham số hoặc data generator.
6. **Kiểm tra HTTP:** Với Spring Boot, dùng MockMvc để kiểm tra sự khác biệt giữa query parameter thiếu, rỗng, whitespace, sai kiểu và response.
7. **Rà soát báo cáo:** Đếm invocation thực sự chạy, xem tên input khi fail, kiểm tra assertions có mô tả nghiệp vụ, bổ sung regression case cho lỗi mới tìm được.

Bộ test có ích nhất không phải bộ có nhiều dữ liệu ngẫu nhiên nhất, mà là bộ chứng minh được **những nhóm giá trị, ranh giới và tương tác đầu vào** mà yêu cầu nghiệp vụ quan tâm.