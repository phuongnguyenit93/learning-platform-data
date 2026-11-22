# @ParameterizedTest với nguồn dữ liệu đơn giản trong JUnit Jupiter

Khi cùng một quy tắc phải được kiểm tra với nhiều giá trị đầu vào, viết từng method `@Test` riêng có thể dẫn đến mã lặp: cách tạo đối tượng, lời gọi và assertion gần như giống nhau, chỉ khác dữ liệu. **`@ParameterizedTest` của JUnit Jupiter** cho phép khai báo **một phương thức kiểm thử** và chạy phương thức đó **nhiều lượt (invocations)**, mỗi lượt với một bộ đối số do nguồn dữ liệu cung cấp.

Bài này tập trung vào những nguồn dữ liệu dễ đọc và thường gặp: **`@ValueSource`, `@NullSource`, `@EmptySource`, `@NullAndEmptySource`, `@CsvSource` và `@EnumSource`**. Mục tiêu là biết chọn nguồn đúng, kiểm tra dữ liệu biên, viết assertion có ý nghĩa, chạy được trong dự án Spring Boot và phân biệt những trường hợp nên chuyển sang nguồn phức tạp hơn.

## 1. Cơ chế của parameterized test

Một test thông thường:

```java
@Test
void acceptsAmy() {
    assertTrue(policy.isValid("amy"));
}
```

Nếu thêm các tên `bob_42` và `abc123456789` mà quy tắc kỳ vọng không đổi, ta có thể viết:

```java
@ParameterizedTest
@ValueSource(strings = {"amy", "bob_42", "abc123456789"})
void acceptsValidUsernames(String username) {
    assertTrue(policy.isValid(username));
}
```

JUnit Jupiter lấy lần lượt từng giá trị từ `@ValueSource` rồi truyền vào tham số `username`. Đây là **3 lần thực thi riêng biệt** của cùng một phương thức; mỗi lượt có kết quả pass/fail riêng trong báo cáo test. Khi một lượt thất bại, dữ liệu gây lỗi cần được thể hiện rõ để sửa đúng trường hợp.

Cấu trúc cơ bản:

```text
@ParameterizedTest + nguồn dữ liệu
              |
              v
     Tạo các bộ đối số
              |
      +-------+-------+
      |       |       |
    case 1  case 2  case 3
      |       |       |
      +--- thực thi ---+
              |
       assertion mỗi lượt
```

Ba thành phần quan trọng:

1. **`@ParameterizedTest`** đánh dấu phương thức được chạy nhiều lượt. Không cần gắn thêm `@Test` lên cùng method.
2. **Argument source (nguồn đối số)** sinh các giá trị: một giá trị mỗi lượt từ `@ValueSource`, nhiều giá trị mỗi lượt từ `@CsvSource`, v.v.
3. **Tham số của method và assertion** nhận dữ liệu, chạy hành vi **thật** cần kiểm tra rồi so sánh kết quả. Test parameterized không có ích nếu chỉ assert lại chính dữ liệu nguồn, không gọi SUT.

**Ví dụ tư duy:** “Mỗi username hợp lệ đều được chấp nhận” là một hành vi có thể được chạy với nhiều tên. “Username hợp lệ được chấp nhận” và “Username không hợp lệ bị từ chối” có kỳ vọng khác nhau; có thể tách hai phương thức test để thông điệp và assertion rõ, hoặc dùng `@CsvSource` nếu cùng một lời gọi và kỳ vọng được cung cấp theo từng dòng.

## 2. Chuẩn bị JUnit Jupiter trong dự án Spring Boot

Trong dự án Spring Boot dùng Gradle, thường sử dụng bộ dependency kiểm thử của Spring Boot. Phần cấu hình liên quan trong `build.gradle` (Groovy DSL) có dạng:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **phần cấu hình bổ sung** cho dự án đã khai báo Spring Boot/Gradle plugins và cơ chế quản lý phiên bản dependency; không phải một file build độc lập. Bộ kiểm thử chuẩn của Spring Boot bao gồm các thư viện JUnit Jupiter cần thiết trong cấu hình thông dụng, trong đó có hỗ trợ parameterized test. Với project Java **không dùng** Spring Boot starter, phải bảo đảm `junit-jupiter-params` cùng JUnit Jupiter engine/API có phiên bản tương thích trên test classpath.

Các import phổ biến:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.EmptySource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;
```

Lưu ý: các source annotations nằm trong `org.junit.jupiter.params.provider`, còn `@Test` nằm trong `org.junit.jupiter.api`. Chúng hoạt động trên **JUnit Platform/Jupiter**, không yêu cầu khởi động Spring application context nếu kiểm thử logic Java thuần.

Vị trí file tiêu chuẩn:

```text
src/
├── main/java/example/testing/UsernamePolicy.java
└── test/java/example/testing/UsernamePolicyTest.java
```

JUnit và Gradle sẽ cần cấu hình đúng đường dẫn source/test như project Java hoặc Spring Boot thông dụng.

## 3. Bảng chọn nguồn dữ liệu đơn giản

| Annotation | Sinh đối số | Phù hợp khi | Điểm cần nhớ |
| --- | --- | --- | --- |
| `@ValueSource` | Mỗi lượt **một** giá trị literal | Danh sách chuỗi, số, boolean, ký tự... cùng một kỳ vọng | Một tham số test; không trực tiếp tạo `null` |
| `@NullSource` | Một lượt chứa `null` | Bắt lỗi xử lý đầu vào thiếu | Không truyền `null` vào tham số primitive như `int` |
| `@EmptySource` | Một lượt là giá trị rỗng tương thích loại tham số | Kiểm tra `""` hoặc collection/array rỗng | Rỗng khác `null` và khác chuỗi chỉ chứa khoảng trắng |
| `@NullAndEmptySource` | Kết hợp trường hợp null và empty | Các API nhận String/collection có kiểm tra thiếu/rỗng | Có thể dùng chung với `@ValueSource` cho khoảng trắng |
| `@CsvSource` | Mỗi hàng là **nhiều cột/đối số** | Bảng đầu vào → kết quả mong đợi hoặc nhiều tham số | Cần hiểu dấu phân cách, dấu quote, chuyển kiểu và ô trống |
| `@EnumSource` | Các hằng enum đã chọn | Trạng thái, loại lệnh, chế độ hoạt động | Có thể chọn tên cụ thể hoặc loại trừ các tên |

Nguyên tắc chọn nhanh: **một đối số → `@ValueSource`; null/empty → nguồn tương ứng; nhiều đối số theo hàng → `@CsvSource`; các trạng thái enum → `@EnumSource`**. Khi dữ liệu phải được tạo động, là đối tượng phức tạp, cần tái sử dụng nhiều nơi hoặc quá dài để viết trực tiếp trong annotation, cân nhắc `@MethodSource` hoặc nguồn chuyên biệt. Không cần áp dụng những công cụ phức tạp đó cho các trường hợp đơn giản của bài này.

## 4. Ví dụ runnable: kiểm tra username và trạng thái chỉnh sửa

Ta thống nhất hợp đồng nghiệp vụ trước khi viết test:

- Username hợp lệ có **3–12 ký tự**, ký tự đầu là chữ thường ASCII `a–z`; các ký tự còn lại chỉ gồm chữ thường ASCII, chữ số hoặc dấu gạch dưới `_`.
- `null`, chuỗi rỗng, chuỗi chỉ chứa whitespace, ký tự sai định dạng hoặc độ dài sai đều không hợp lệ.
- Hàm loại bỏ whitespace ở **hai đầu** chuỗi trả về phần còn lại; nó **không đổi chữ hoa thành chữ thường**.
- Một bản ghi chỉ được chỉnh sửa khi ở trạng thái `DRAFT`.

Chính sách và các phép test được giữ nhỏ để quan sát tập trung vào JUnit parameterization.

### 4.1. Lớp production

Tạo file `src/main/java/example/testing/UsernamePolicy.java`:

```java
package example.testing;

public final class UsernamePolicy {

    public boolean isValid(String username) {
        return username != null
                && username.matches("[a-z][a-z0-9_]{2,11}");
    }

    public String stripOuterWhitespace(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        return input.strip();
    }

    public boolean canEdit(Status status) {
        return status == Status.DRAFT;
    }

    public enum Status {
        DRAFT,
        SUBMITTED,
        APPROVED,
        REJECTED
    }
}
```

Giải thích:

- Biểu thức `[a-z][a-z0-9_]{2,11}` yêu cầu **một** chữ thường đầu tiên, tiếp theo **2–11** ký tự được phép: tổng cộng 3–12. `String.matches(...)` so khớp toàn bộ chuỗi.
- Kiểm tra `username != null` ở trước biểu thức regular expression nên không phát sinh `NullPointerException` khi truyền null.
- `String.strip()` (Java 11+) xóa khoảng trắng theo định nghĩa Unicode của Java ở hai đầu, không thay đổi phần giữa.
- `canEdit` minh họa cùng một kỳ vọng `false` trên nhiều trạng thái enum.

Đây là Java thuần, không cần `@Service` hoặc `@SpringBootTest`. Trong ứng dụng Spring Boot thật, logic dạng này có thể được gọi từ service/controller mà không làm thay đổi cách kiểm tra quy tắc của nó.

### 4.2. Bộ test hoàn chỉnh với các nguồn dữ liệu

Tạo file `src/test/java/example/testing/UsernamePolicyTest.java`:

```java
package example.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UsernamePolicyTest {

    private final UsernamePolicy policy = new UsernamePolicy();

    @ParameterizedTest(name = "[{index}] valid username: {0}")
    @ValueSource(strings = {"amy", "bob_42", "abc123456789"})
    void acceptsValidUsernames(String username) {
        assertTrue(policy.isValid(username));
    }

    @ParameterizedTest(name = "[{index}] invalid format: {0}")
    @ValueSource(strings = {
            "ab", "Tom", "9tom", "tom-adam", "abc1234567890"
    })
    void rejectsInvalidFormats(String username) {
        assertFalse(policy.isValid(username));
    }

    @ParameterizedTest(name = "[{index}] missing or blank: {0}")
    @NullAndEmptySource
    @ValueSource(strings = {" ", "\t"})
    void rejectsMissingOrBlankUsernames(String username) {
        assertFalse(policy.isValid(username));
    }

    @ParameterizedTest(name = "[{index}] strip [{0}] -> [{1}]")
    @CsvSource({
            "'  amy  ',amy",
            "' bob_42 ',bob_42",
            "'  TOM ',TOM"
    })
    void stripsOuterWhitespace(String input, String expected) {
        assertEquals(expected, policy.stripOuterWhitespace(input));
    }

    @ParameterizedTest(name = "[{index}] cannot edit: {0}")
    @EnumSource(
            value = UsernamePolicy.Status.class,
            names = {"SUBMITTED", "APPROVED", "REJECTED"}
    )
    void cannotEditNonDraftStatus(UsernamePolicy.Status status) {
        assertFalse(policy.canEdit(status));
    }

    @Test
    void canEditDraft() {
        assertTrue(policy.canEdit(UsernamePolicy.Status.DRAFT));
    }
}
```

**Tổng số lần thực thi dự kiến** của file trên là **19** (nếu test được runner phát hiện và cấu hình đúng), tính từ các nguồn:

| Test method | Nguồn | Số lượt |
| --- | --- | ---: |
| `acceptsValidUsernames` | Ba string trong `@ValueSource` | 3 |
| `rejectsInvalidFormats` | Năm string trong `@ValueSource` | 5 |
| `rejectsMissingOrBlankUsernames` | Null + empty + hai string whitespace | 4 |
| `stripsOuterWhitespace` | Ba dòng trong `@CsvSource` | 3 |
| `cannotEditNonDraftStatus` | Ba giá trị enum | 3 |
| `canEditDraft` | Một `@Test` bình thường | 1 |
| **Tổng** | | **19** |

Đây là **19 invocations**, không phải 19 method được khai báo. Các ca có đầu vào riêng, lỗi của một invocation có thể được JUnit hiển thị gắn với giá trị cụ thể; cách báo cáo và việc có tiếp tục chạy sau lỗi phụ thuộc runner/cấu hình.

Chạy từ thư mục dự án Gradle:

```bash
./gradlew test --tests example.testing.UsernamePolicyTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.UsernamePolicyTest"
```

**Kỳ vọng:** tất cả các ca trên pass với Java 17+ và project đã có JUnit Jupiter Params phù hợp. Không có chuỗi stdout cố định cho lệnh test vì Gradle/JUnit và thiết lập log có thể hiển thị khác nhau. Nếu test đỏ, báo cáo sẽ cho biết invocation và assertion thất bại, giúp đối chiếu dữ liệu nguồn.

### 4.3. Chạy riêng logic Java không cần JUnit

Để xem kết quả thực thi của lớp production độc lập, tạo file `src/main/java/example/testing/UsernamePolicyDemo.java`:

```java
package example.testing;

public class UsernamePolicyDemo {
    public static void main(String[] args) {
        UsernamePolicy policy = new UsernamePolicy();

        System.out.println(policy.isValid("amy"));
        System.out.println(policy.isValid("Tom"));
        System.out.println(
                policy.stripOuterWhitespace("  bob_42  "));
        System.out.println(
                policy.canEdit(UsernamePolicy.Status.DRAFT));
    }
}
```

Lệnh biên dịch/chạy từ thư mục gốc project:

```bash
javac -d out src/main/java/example/testing/UsernamePolicy.java src/main/java/example/testing/UsernamePolicyDemo.java
java -cp out example.testing.UsernamePolicyDemo
```

Stdout chính xác của `main`:

```text
true
false
bob_42
true
```

Lệnh `javac` ở đây chứng minh hai file Java thuần hoạt động với JDK mà không cần Spring hay JUnit; bản thân nó **không chạy các test parameterized**. Để chạy test cần JUnit engine và test dependencies thông qua Gradle hoặc một test runner tương đương.

## 5. Hiểu kỹ từng nguồn dữ liệu

### 5.1. `@ValueSource`: danh sách một giá trị mỗi lượt

`@ValueSource` phù hợp nhất khi test nhận **một tham số** và dùng cùng logic kiểm chứng. Ngoài `strings`, các dạng phổ biến gồm `ints`, `longs`, `doubles`, `booleans`, `chars` và `classes`; JUnit còn hỗ trợ các kiểu primitive khác theo danh sách trong API. Khai báo một thuộc tính nguồn phù hợp với trường hợp kiểm thử.

Ví dụ kiểm tra một hàm xử lý số nguyên (đây là **đoạn method test minh họa**, giả định đã có hàm `isEven(int)` trong SUT):

```java
@ParameterizedTest
@ValueSource(ints = {0, 2, 4, 100})
void acceptsEvenNumbers(int value) {
    assertTrue(numberPolicy.isEven(value));
}
```

JUnit truyền lần lượt từng số vào `value`. Tránh viết bốn test với cùng assertion chỉ để thay số.

**Giới hạn:** `@ValueSource` không phải bảng nhiều cột. Không dùng `@ValueSource(strings = {"amy", "false"})` và mong JUnit tự tạo cặp `(String, boolean)`. Trường hợp muốn test method có hai tham số `username` và `expected`, hãy chọn `@CsvSource` hoặc một nguồn tạo `Arguments` phù hợp.

`@ValueSource` cũng không diễn đạt `null`; sử dụng `@NullSource`, `@NullAndEmptySource`, hoặc nguồn khác nếu cần trường hợp null.

### 5.2. `@NullSource`, `@EmptySource` và `@NullAndEmptySource`

Ba trường hợp cần phân biệt trên một tham số `String`:

| Input | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `null` | Không có đối tượng String | Không phải chuỗi độ dài 0 |
| `""` | String có `length() == 0` | Chuỗi rỗng |
| `" "` hoặc `"\t"` | String **có ký tự whitespace** | Không rỗng; có thể bị coi là blank theo quy tắc nghiệp vụ |

`@NullSource` tạo **một** invocation với `null`. `@EmptySource` tạo một invocation với giá trị rỗng tương thích kiểu tham số, như `String` rỗng; nó cũng có khả năng dùng với một số kiểu collection/array thích hợp. `@NullAndEmptySource` kết hợp cả hai cho các kiểu được hỗ trợ.

Ví dụ đơn giản:

```java
@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", "\t"})
void rejectsBlankInput(String input) {
    assertFalse(policy.isValid(input));
}
```

Ở đây JUnit tạo **4 lượt**: `null`, `""`, một dấu cách, một ký tự tab. Nếu policy chỉ kiểm tra `isEmpty()` mà bỏ qua blank, test với khoảng trắng sẽ phơi bày lỗ hổng.

**Không truyền `null` vào tham số primitive** như `int`, `long` hoặc `boolean`. Java primitive không chứa được null; test sẽ lỗi chuyển đối số trước khi kiểm tra nghiệp vụ. Nếu thực sự cần biểu diễn null, dùng wrapper `Integer`/`Long`/`Boolean` hoặc reference type thích hợp.

Lưu ý khi method được khai báo nhiều annotation nguồn: mỗi annotation bổ sung các invocations của mình theo cơ chế JUnit, **không tự ghép các nguồn thành tích Descartes**. `@NullAndEmptySource` cộng với `@ValueSource(strings = {" "})` tạo ba lượt độc lập, không phải các cặp dữ liệu.

### 5.3. `@CsvSource`: nhiều đối số trên mỗi dòng

Một dòng CSV đại diện một case; mỗi cột tương ứng với tham số trong test method. Đây là lựa chọn tự nhiên cho bảng **input → expected**:

```java
@ParameterizedTest(name = "[{index}] {0} => {1}")
@CsvSource({
        "amy,true",
        "Tom,false",
        "abc123456789,true",
        "abc1234567890,false"
})
void validatesExpectedResult(String username, boolean expected) {
    assertEquals(expected, policy.isValid(username));
}
```

Đây là **đoạn bổ sung bên trong class `UsernamePolicyTest`** và dùng các import đã có; nó sẽ chạy thêm 4 lượt nếu thêm vào file hoàn chỉnh ở mục 4.2. JUnit có cơ chế chuyển các giá trị CSV đơn giản như chuỗi `"true"` và `"false"` sang tham số `boolean`; các chuỗi số thích hợp có thể chuyển sang `int`, `long` và các kiểu tích hợp khác. Khi dữ liệu không chuyển được sang kiểu tham số, lỗi phát sinh ở argument conversion, không phải ở quy tắc đang test.

**Dấu phân cách và quote** rất quan trọng:

- `@CsvSource` mặc định phân cách bởi dấu phẩy; mặc định dấu nháy dùng để bao một giá trị CSV là **nháy đơn** `'`.
- Giá trị `"'  amy  ',amy"` đặt chuỗi đầu trong nháy đơn để giữ nguyên các khoảng trắng ở hai đầu. Nếu viết `"  amy  ,amy"` không quote, mặc định JUnit có thể loại whitespace thừa xung quanh token.
- Một trường không có ký tự và không quote (ví dụ `"alice,"`) được hiểu là **`null`** ở vị trí cột đó theo cấu hình mặc định. Trường chứa nháy đơn rỗng (ví dụ giá trị CSV `''`) biểu diễn **chuỗi rỗng** `""`. Đừng nhầm null với empty khi test validation.
- Chuỗi literal `"null"` trong CSV **không tự động** là Java null. Nếu cần một nhãn đặc biệt được chuyển thành null, dùng thiết lập `nullValues` của `@CsvSource` hoặc một nguồn khác, và diễn đạt quy tắc rõ ràng.
- Nếu một giá trị chứa dấu phẩy, quote toàn bộ trường đó theo quy tắc CSV; nếu cần dấu phân cách khác, các thuộc tính như `delimiter`/`delimiterString` có thể thích hợp.

Ví dụ mô tả ý nghĩa ba dòng dữ liệu:

```java
@CsvSource({
        "alice,ACTIVE",
        "bob,PENDING",
        "'last,first',DISPLAY_NAME"
})
```

Đây **chỉ là annotation dữ liệu**, muốn chạy phải đặt trên một `@ParameterizedTest` có hai tham số với kiểu tương ứng. Dòng cuối truyền `"last,first"` thành **một** cột, không phải hai cột; dấu nháy đơn không nằm trong giá trị truyền cho test method.

Những lỗi phổ biến với CSV là số lượng cột không khớp chữ ký method, nhầm cú pháp quote của Java với quote của CSV, hoặc vô tình mất khoảng trắng đầu/cuối khi muốn kiểm tra trimming. Khi phân vân, tạo 1–2 dòng đầu, chạy test và đọc tên/giá trị invocation trước khi mở rộng bảng.

### 5.4. `@EnumSource`: lấy dữ liệu từ enum

Một enum có tập trạng thái hữu hạn, nên `@EnumSource` giúp kiểm tra nhiều trạng thái mà không phải gõ chuỗi rồi chuyển đổi thủ công.

Nếu muốn tất cả hằng enum:

```java
@ParameterizedTest
@EnumSource(UsernamePolicy.Status.class)
void statusIsDefined(UsernamePolicy.Status status) {
    assertTrue(status.name().length() > 0);
}
```

Đoạn này minh họa cách cung cấp **tất cả enum values**. Trong test thực tế, hãy thay assertion minh họa bằng hành vi có ý nghĩa của SUT; chỉ kiểm tra `status.name()` có độ dài dương không tạo nhiều giá trị bảo vệ nghiệp vụ.

Ví dụ nghiệp vụ ở bộ test runnable đã chọn một số trạng thái:

```java
@EnumSource(
        value = UsernamePolicy.Status.class,
        names = {"SUBMITTED", "APPROVED", "REJECTED"}
)
```

Ta có thể biểu diễn cùng tập dữ liệu bằng cách **loại trừ** `DRAFT`:

```java
@EnumSource(
        value = UsernamePolicy.Status.class,
        mode = EnumSource.Mode.EXCLUDE,
        names = "DRAFT"
)
```

Hai annotation trên là **hai phương án thay thế cho cùng một test**, không đặt cùng lúc. Khi enum được bổ sung trạng thái mới, chọn theo danh sách tên cố định hay “tất cả trừ DRAFT” cho kết quả khác nhau:

- **Chỉ định danh sách `names`:** trạng thái mới không tự được kiểm tra; phù hợp khi chỉ những case liệt kê mới thuộc tập cần xác minh.
- **Loại trừ `DRAFT`:** trạng thái mới tự được đưa vào nhóm “không cho sửa”; phù hợp khi quy tắc là “chỉ DRAFT được sửa”. Test có thể phát hiện implementation quên khóa trạng thái mới.

Đó là lựa chọn thiết kế test, không chỉ cú pháp annotation. Tên enum trong `names` phải khớp hằng thực tế. Nếu dữ liệu là string từ HTTP (chẳng hạn `"submitted"`), kiểm tra enum chưa chứng minh Spring tự chuyển input HTTP, xử lý lowercase hay status lỗi đúng; những điều ấy cần test ở ranh giới HTTP.

## 6. Đặt tên invocation để đọc lỗi nhanh

Mặc định báo cáo test parameterized thường hiển thị index và arguments; có thể chủ động đặt tên:

```java
@ParameterizedTest(name = "[{index}] username={0}")
@ValueSource(strings = {"amy", "bob_42"})
void acceptsValidUsernames(String username) {
    assertTrue(policy.isValid(username));
}
```

Trong mẫu:

- `{index}` là số thứ tự invocation (bắt đầu từ 1).
- `{0}` là đối số thứ nhất, `{1}` là đối số thứ hai nếu có.
- `{arguments}` có thể hiển thị danh sách đối số được format bởi JUnit.

Nếu case lỗi có tên hiển thị như `[2] username=bob_42`, ta truy ra chính xác hàng dữ liệu để tái hiện. Với input dài, nhạy cảm hoặc định dạng phức tạp, chọn tên ngắn gọn và tránh in bí mật trong báo cáo. Test nên chứa dữ liệu tổng hợp, không cần giá trị thật của người dùng.

Đặt tên method theo hành vi, chẳng hạn `rejectsMissingOrBlankUsernames`. `@DisplayName` (nếu dùng) và `name` của `@ParameterizedTest` có thể giúp báo cáo dễ đọc, nhưng không thay thế assertion.

## 7. Phối hợp dữ liệu nguồn với thiết kế test tốt

Parameterized test phù hợp khi **cùng một quy tắc** được kiểm tra với nhiều đầu vào và cách assert ổn định. Có thể dùng bảng quyết định:

| Tình huống | Cách chọn | Lý do |
| --- | --- | --- |
| 3–10 giá trị String phải cùng được chấp nhận | `@ValueSource(strings = {...})` | Một tham số, một kỳ vọng, dễ đọc |
| API cần phân biệt null, empty, whitespace | `@NullAndEmptySource` + `@ValueSource` | Phân biệt các loại dữ liệu thiếu/rỗng |
| Mỗi input có output khác nhau | `@CsvSource` | Mỗi hàng trình bày cặp input–expected |
| Test cùng rule qua mọi trạng thái enum | `@EnumSource` | Tránh tên enum sai và bao phủ nhóm giá trị |
| Mỗi case đòi setup/mocking hoàn toàn khác | Những method `@Test` riêng | Hành vi và fixture khác nhau, ép chung sẽ khó hiểu |
| Dữ liệu là record/DTO/stream cấu trúc nhiều tầng | `@MethodSource` hoặc nguồn thích hợp | Annotation literal không còn dễ bảo trì |
| Hàng trăm case nằm trong file dữ liệu kiểm thử | `@CsvFileSource` hoặc fixture có kiểm soát | Giảm file Java dài và thuận tiện cập nhật dữ liệu |

**Không tự động gộp mọi test vào một bảng.** Ví dụ “username hợp lệ trả true”, “input null ném exception” và “hệ thống lưu event khi đăng ký” khác nhau về hành vi và loại assertion. Nếu cố đặt cả ba vào một test với chuỗi `if/else` để chọn cách assert, lỗi khó đọc và test có thể che logic quan trọng. Dùng parameterized cho những biến thể *thật sự cùng hợp đồng*.

Chọn tập giá trị có ý nghĩa: ở phép kiểm tra độ dài 3–12, nên có 2, 3, 12, 13; ở ký tự đầu, nên có chữ thường, chữ hoa, chữ số; với dữ liệu rỗng, cần null, empty, whitespace. Kiểm thử mọi số ngẫu nhiên mà không có lý do không thay thế được kiểm thử ranh giới.

Dữ liệu có tính **quyết định** giúp kết quả tái hiện được. Tránh giá trị dựa vào đồng hồ hiện tại, API bên ngoài hoặc random không seed. Một danh sách enum có thể phát triển theo code; lựa chọn INCLUDE/EXCLUDE phải phản ánh quy tắc thực sự để việc mở rộng enum không vô tình làm test pass vô nghĩa.

## 8. Trong Spring Boot, parameterized test nằm ở lớp nào?

`@ParameterizedTest` là khả năng của **JUnit Jupiter**, không phải một Spring annotation. Nó áp dụng ở nhiều mức test:

1. **Unit test Java thuần:** kiểm tra validation, tính toán, mapping, policy; tốc độ nhanh nhất, không cần ApplicationContext. Ví dụ `UsernamePolicyTest` ở trên thuộc loại này.
2. **Service test có mock:** mỗi case có thể stub response của repository/client theo input rồi assert kết quả và tương tác có ý nghĩa. Chỉ parameterize nếu setup và mục tiêu các case tương đồng.
3. **Spring MVC slice:** dùng `@WebMvcTest` và `MockMvc` để thử nhiều request parameters/status/JSON với cùng form assertion. Method phải được Spring Test chuẩn bị controller và các collaborator cần thiết.
4. **Repository hoặc integration test:** `@DataJpaTest`/`@SpringBootTest` có thể kết hợp với parameterized test, nhưng mỗi invocation có thể làm việc với DB/context và cần kiểm soát dữ liệu, transaction, cleanup.
5. **Security/role matrix:** `@EnumSource` hoặc `@CsvSource` mô tả quyền theo role và status; cần chạy chính security infrastructure nếu muốn chứng minh filter/authorization của Spring hoạt động.

**Ví dụ MVC chỉ minh họa bên trong class test đã có `MockMvc` và cấu hình `@WebMvcTest`:**

```java
@ParameterizedTest
@ValueSource(strings = {"", "a", "9tom"})
void invalidUsernameReturnsBadRequest(String username)
        throws Exception {
    mockMvc.perform(post("/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":\"" + username + "\"}"))
            .andExpect(status().isBadRequest());
}
```

Đoạn trên **không phải test class độc lập**: cần controller `POST /users`, validation/exception mapping đúng, bean `MockMvc`, cấu hình security phù hợp và static imports từ Spring Test. Các giá trị minh họa là những chuỗi có thể đưa trực tiếp vào JSON; **không tự ghép JSON bằng string concatenation cho dữ liệu tùy ý** trong ứng dụng thật vì cần escaping. Với dữ liệu phức tạp, dùng JSON serializer hoặc request builder phù hợp.

Một lần chạy xanh ở test MVC chứng minh phần hợp đồng HTTP đang được kiểm tra, **không tự động chứng minh persistence hoạt động** nếu repository đã được thay bằng mock. Tương tự, test service dùng mock repository không chứng minh SQL; lựa chọn ranh giới dựa vào yêu cầu, còn `@ParameterizedTest` chỉ giúp lặp lại cùng test với bộ dữ liệu khác.

## 9. Vòng đời của mỗi invocation và vấn đề state

Một parameterized test tạo nhiều lần thực thi logic, nhưng không có nghĩa những lần thực thi nên phụ thuộc nhau. Mặc định JUnit Jupiter sử dụng lifecycle test instance theo **PER_METHOD**: mỗi invocation có thể có đối tượng test mới, và các callback như `@BeforeEach` được chạy cho từng invocation. Điều này giúp các case được cô lập khi fixture chuẩn bị hợp lý.

Dù vậy, có thể còn trạng thái chung trong biến `static`, singleton của Spring, database, file, cache hoặc test container. Không giả định rằng các invocation tự động reset mọi tài nguyên bên ngoài. Nếu một case sửa danh sách dữ liệu chung, invocation sau có thể đỏ do thứ tự chạy mà không liên quan nghiệp vụ. Hãy setup/cleanup có kiểm soát, dùng transaction/rollback nơi phù hợp, và tránh dựa vào thứ tự nguồn hoặc thứ tự test khi không được bảo đảm.

Trong test có Mockito, điều khiển stub cho mỗi invocation theo input, không dùng một mock được cấu hình lẫn lộn để test qua nhờ số lần gọi từ case trước. Với `@SpringBootTest` có context cache, Spring có thể tái sử dụng ApplicationContext giữa các lần chạy; việc cache context giúp tốc độ nhưng **không cô lập dữ liệu ứng dụng** theo từng invocation.

Một số nguyên tắc hữu ích:

- Ưu tiên assertion trên output và side effect có nghĩa, không khóa cứng thứ tự gọi các helper nội bộ.
- Đặt tên dữ liệu dễ hiểu để khi một dòng fail biết được chính xác quy tắc/biên.
- Tránh tạo dependency truy cập mạng hoặc giờ hệ thống chỉ để parameterize đầu vào đơn giản.
- Nếu nhiều case yêu cầu fixture khác hẳn nhau, tách method test theo hành vi thay vì dùng logic phân nhánh lớn trong test.

## 10. Lỗi thường gặp và cách khắc phục

**Lỗi 1 — Quên nguồn dữ liệu.** Gắn `@ParameterizedTest` nhưng không có argument source làm JUnit không biết tạo những lượt chạy có tham số ra sao; kiểm tra báo cáo và thêm nguồn phù hợp. Đừng nhầm test không chạy với test đã pass.

**Lỗi 2 — Dùng `@ValueSource` cho hai tham số.** `@ValueSource` tạo một đối số mỗi lượt. Nếu method nhận `String input, boolean expected` thì `@CsvSource` thích hợp hơn; đảm bảo số cột, chữ ký và kiểu dữ liệu khớp.

**Lỗi 3 — Đưa `@NullSource` vào tham số primitive.** `null` không gán được cho `int` hoặc `boolean`. Dùng reference/wrapper khi null là input hợp lệ về mặt kiểu, hoặc thay test nguồn khác.

**Lỗi 4 — Nhầm `""`, `null` và whitespace.** `@EmptySource` không đồng nghĩa với một dấu cách. Thêm `@ValueSource(strings = {" ", "\t"})` nếu nghiệp vụ cần bác bỏ blank.

**Lỗi 5 — Nhầm cú pháp `@CsvSource`.** Dữ liệu có dấu phẩy hoặc khoảng trắng ở mép không được quote có thể tách sai hoặc mất whitespace. Trong CSV mặc định của JUnit, quote bằng nháy đơn `'`; một ô không quote và không có dữ liệu khác với `''`.

**Lỗi 6 — Kỳ vọng conversion tùy ý.** CSV string có thể tự chuyển thành kiểu tích hợp, nhưng không thể mặc định chuyển mọi JSON/DTO tùy ý thành object domain. Dùng converter, `@MethodSource` hoặc fixture nếu case phức tạp.

**Lỗi 7 — `@EnumSource` phủ sai tập.** Liệt kê tên thiếu một trạng thái mới khiến test không bao phủ case đó; dùng `Mode.EXCLUDE` khi quy tắc có nghĩa “mọi enum trừ X”, hoặc chọn danh sách cố định khi đó mới là hợp đồng.

**Lỗi 8 — Test method chỉ kiểm tra dữ liệu nguồn.** `assertEquals(expected, expected)` luôn pass mà không chạy code cần test. Hãy gọi SUT thật và assert kết quả/exception/side effect từ SUT.

**Lỗi 9 — Gộp hành vi khác nhau bằng hàng loạt `if` trong test.** Nếu mỗi case cần mock khác, exception khác và chuẩn bị khác, chia thành test có tên riêng; parameterize chỉ những trường hợp cùng hành vi.

**Lỗi 10 — Dùng `@SpringBootTest` cho phép tính thuần.** Context không cần thiết làm feedback chậm và lỗi khó định vị. Một class Java thuần có thể được kiểm tra với JUnit mà không khởi động Spring. Chỉ dùng context khi wiring, transaction, security hoặc adapter thực sự là điều cần chứng minh.

**Lỗi 11 — Case trước ảnh hưởng case sau.** Dữ liệu tĩnh, DB hoặc cache dùng chung làm kết quả phụ thuộc thứ tự. Cô lập state từng invocation và kiểm tra cleanup phù hợp.

**Lỗi 12 — Dùng quá nhiều giá trị nhưng thiếu ca biên.** Mười giá trị giữa khoảng không thay được input nằm ngay dưới/trên ngưỡng. Ưu tiên đại diện equivalence classes, boundary values và trường hợp lỗi nghiệp vụ.

## 11. Checklist thực hành

Trước khi dùng `@ParameterizedTest`:

- Các case có thật sự cùng **hành vi và cấu trúc assertion** không?
- Mỗi invocation nhận bao nhiêu tham số? Một giá trị nên dùng `@ValueSource`; một hàng nhiều cột nên dùng `@CsvSource`.
- Đã có null, empty, whitespace, cực trị và giá trị sai định dạng nếu liên quan chưa?
- Với enum, danh sách cố định hay “tất cả trừ...” mới phản ánh quy tắc?
- Dữ liệu CSV có dấu phẩy, nháy hoặc khoảng trắng hai đầu cần quote đúng không?
- Có đặt tên invocation giúp truy ra dữ liệu khi test fail không?
- Có chạy SUT thật ở đúng ranh giới thay vì chỉ kiểm tra stub/mock không?
- Từng invocation có độc lập với state của invocation khác không?
- Test được JUnit engine phát hiện và chạy trên Java/test dependencies đúng chưa?

**Ghi nhớ:** `@ParameterizedTest` giúp kiểm chứng **một hành vi với nhiều bộ dữ liệu** bằng một method test. Chọn nguồn đơn giản nhất phù hợp: `@ValueSource` cho một tham số, nhóm null/empty cho dữ liệu thiếu, `@CsvSource` cho bảng input–expected, và `@EnumSource` cho trạng thái enum. Chất lượng kiểm thử nằm ở **đầu vào đại diện, assertion quan sát hành vi thật và sự độc lập của từng invocation**, không ở việc gộp được nhiều method `@Test` vào một annotation.