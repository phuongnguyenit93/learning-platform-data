# Kiểm thử đủ các biến thể cùng trường hợp `null` khi thiết kế với `sealed` trong Java 17

## 1. Mục tiêu của việc kiểm thử một họ kiểu `sealed`

Khi thiết kế một kiểu `sealed`, bạn đang công khai **tập những kiểu con trực tiếp được phép** của nó. Ví dụ, kết quả xử lý thanh toán có ba trạng thái: thành công, từ chối, đang chờ. Mỗi trạng thái là một kiểu Java riêng thay vì dùng chuỗi trạng thái tùy ý.

~~~java
public sealed interface PaymentResult
        permits Approved, Declined, Pending {
}
~~~

Thiết kế này giúp giới hạn các nhánh kết quả hợp lệ. Tuy nhiên, `sealed` **không tự kiểm thử** các hàm xử lý kết quả. Một hàm có thể:

- Quên xử lý một biến thể mới được bổ sung.
- Xử lý đúng loại đối tượng nhưng trả về thông báo hoặc giá trị sai.
- Vấp lỗi khi tham chiếu `PaymentResult` nhận `null`.
- Bỏ sót các dữ liệu đầu vào bất thường của từng biến thể, ví dụ chuỗi trống hoặc số âm.

Vì vậy, bài học này tập trung vào hai yêu cầu khác nhau nhưng bổ trợ nhau:

1. **Kiểm thử từng biến thể hợp lệ** của họ kiểu `sealed` với dữ liệu và kết quả mong đợi.
2. **Kiểm thử riêng trường hợp `null`** theo chính sách API đã chọn, vì `null` không phải một kiểu con và không thuộc danh sách `permits`.

Ví dụ sử dụng Java 17 ổn định, không cần tính năng preview. Phần kiểm thử minh họa với **JUnit Jupiter** (JUnit 5 API) và Maven; các nguyên tắc vẫn áp dụng khi dùng framework kiểm thử khác.

## 2. Phân biệt "đủ các biến thể" với "đủ mọi đầu vào"

Giả sử:

~~~text
PaymentResult (sealed interface)
├── Approved (record, final)
├── Declined (record, final)
└── Pending  (record, final)
~~~

Có ít nhất ba **nhóm kiểm thử** cần suy nghĩ:

| Nhóm | Mục tiêu | Ví dụ |
|---|---|---|
| Từng biến thể của `sealed` | Bảo đảm mỗi kiểu con có ít nhất một ca kiểm thử về hành vi đặc trưng. | `Approved("TX-17")` cho kết quả `APPROVED: TX-17`. |
| Giá trị biên và bất hợp lệ của dữ liệu | Bảo đảm các kiểu con không lưu trạng thái sai hoặc rơi vào hành vi ngoài dự kiến. | `Approved(null)`, `Approved(" ")`, `Pending(0)`. |
| `null` ở tham số kiểu cha | Bảo đảm API xử lý trường hợp thiếu đối tượng một cách xác định. | `format(null)` ném `NullPointerException` với thông báo rõ ràng. |

Kiểm thử đủ **ba loại** không có nghĩa đã kiểm thử hết **mọi giá trị có thể có** của ba record. Ví dụ, `Approved` có vô số mã giao dịch hợp lệ. Ta cần chọn giá trị đại diện, biên quan trọng và điều kiện lỗi phù hợp với quy tắc nghiệp vụ.

Một điểm khác biệt quan trọng: **`null` không phải biến thể thứ tư** của `PaymentResult`. Giới hạn của `sealed` là giới hạn *kiểu lớp/interface được phép kế thừa*; bản thân một biến tham chiếu Java vẫn có thể chứa `null` trừ khi hợp đồng API chủ động ngăn chặn hoặc xử lý nó.

## 3. Xây dựng họ `sealed` làm đối tượng kiểm thử

Ta xây dựng một hàm `PaymentFormatter.format` chuyển kết quả thanh toán thành văn bản. Các lớp được đặt trong package `example.payment`.

~~~text
sealed-tests/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── example/
    │           └── payment/
    │               ├── PaymentResult.java
    │               ├── Approved.java
    │               ├── Declined.java
    │               ├── Pending.java
    │               └── PaymentFormatter.java
    └── test/
        └── java/
            └── example/
                └── payment/
                    └── PaymentFormatterTest.java
~~~

### 3.1. Kiểu cha `PaymentResult`

Tệp `src/main/java/example/payment/PaymentResult.java`:

~~~java
package example.payment;

public sealed interface PaymentResult
        permits Approved, Declined, Pending {
}
~~~

Danh sách `permits` được viết **tường minh** vì mỗi kiểu con nằm ở một tệp `.java` khác nhau. Ba record bên dưới đều trực tiếp `implements PaymentResult`. Record là kiểu ngầm định `final`, đáp ứng yêu cầu về kiểu con trực tiếp của `sealed`.

### 3.2. Ba biến thể với quy tắc dữ liệu

Tệp `src/main/java/example/payment/Approved.java`:

~~~java
package example.payment;

import java.util.Objects;

public record Approved(String reference) implements PaymentResult {
    public Approved {
        Objects.requireNonNull(reference, "reference");
        if (reference.isBlank()) {
            throw new IllegalArgumentException(
                    "reference must not be blank");
        }
        reference = reference.strip();
    }
}
~~~

Tệp `src/main/java/example/payment/Declined.java`:

~~~java
package example.payment;

import java.util.Objects;

public record Declined(String reason) implements PaymentResult {
    public Declined {
        Objects.requireNonNull(reason, "reason");
        if (reason.isBlank()) {
            throw new IllegalArgumentException(
                    "reason must not be blank");
        }
        reason = reason.strip();
    }
}
~~~

Tệp `src/main/java/example/payment/Pending.java`:

~~~java
package example.payment;

public record Pending(int queuePosition) implements PaymentResult {
    public Pending {
        if (queuePosition <= 0) {
            throw new IllegalArgumentException(
                    "queuePosition must be positive");
        }
    }
}
~~~

Các compact constructor của record xác nhận bất biến:

- Mã tham chiếu của `Approved` và lý do của `Declined` không được `null` hoặc chỉ toàn khoảng trắng.
- `Pending` cần vị trí trong hàng đợi lớn hơn 0.
- `strip()` loại bỏ khoảng trắng ở đầu/cuối dữ liệu được chấp nhận.

Kiểu dữ liệu cụ thể giúp làm rõ ý nghĩa: một đối tượng `Declined` không thể bị nhầm với `Approved` vì chỉ cùng chứa chuỗi; chúng là hai loại đối tượng khác nhau.

### 3.3. Hàm xử lý đủ ba nhánh

Tệp `src/main/java/example/payment/PaymentFormatter.java`:

~~~java
package example.payment;

import java.util.Objects;

public final class PaymentFormatter {
    private PaymentFormatter() {
    }

    public static String format(PaymentResult result) {
        Objects.requireNonNull(result, "result");

        if (result instanceof Approved approved) {
            return "APPROVED: " + approved.reference();
        }
        if (result instanceof Declined declined) {
            return "DECLINED: " + declined.reason();
        }
        if (result instanceof Pending pending) {
            return "PENDING: " + pending.queuePosition();
        }

        throw new IllegalStateException(
                "Unhandled PaymentResult variant: "
                        + result.getClass().getName());
    }
}
~~~

Ở đây, `Objects.requireNonNull(result, "result")` định nghĩa rõ chính sách: **không chấp nhận `null`**; nếu nhận `null`, hàm ném `NullPointerException` có thông báo `result`. Đây là một quyết định của API ví dụ, không phải hành vi mặc định do `sealed` tạo ra.

`instanceof` với biến mẫu, chẳng hạn `result instanceof Approved approved`, là tính năng Java 17 ổn định. Với `null`, mọi phép kiểm tra `instanceof` đều cho `false`, nên việc đặt `requireNonNull` ở đầu giúp lỗi rõ ràng hơn và tránh vô tình rơi vào nhánh xử lý thiếu biến thể.

Ba nhánh cuối xử lý đúng toàn bộ các record được `permits` cho phép hiện tại. Lệnh `throw` cuối cùng là biện pháp phòng thủ nếu mã nguồn phát triển thêm biến thể nhưng người viết chưa cập nhật formatter.

**Giới hạn của Java 17:** chuỗi `if/else` hoặc `if` với `instanceof` **không được trình biên dịch chứng minh là đầy đủ các nhánh**. Pattern matching for `switch` trên kiểu `sealed` vẫn là tính năng *preview* trong Java 17; tài liệu này không yêu cầu bật `--enable-preview`. Vì thế, kiểm thử và việc rà soát thay đổi khi thêm biến thể là đặc biệt quan trọng.

## 4. Lập ma trận kiểm thử trước khi viết test

Một ma trận rõ ràng giúp tránh chỉ kiểm thử "đường đi thành công" mà bỏ quên các trường hợp quan trọng:

| Mã ca | Đầu vào | Kết quả mong đợi | Loại kiểm thử |
|---|---|---|---|
| V1 | `new Approved("TX-17")` | `"APPROVED: TX-17"` | Biến thể `Approved` |
| V2 | `new Declined("Invalid card")` | `"DECLINED: Invalid card"` | Biến thể `Declined` |
| V3 | `new Pending(3)` | `"PENDING: 3"` | Biến thể `Pending` |
| N1 | `PaymentFormatter.format(null)` | Ném `NullPointerException`, message `"result"` | `null` tại tham số kiểu cha |
| N2 | `new Approved(null)` | Ném `NullPointerException` | `null` trong dữ liệu record |
| N3 | `new Declined(null)` | Ném `NullPointerException` | `null` trong dữ liệu record |
| B1 | `new Approved("   ")` | Ném `IllegalArgumentException` | Chuỗi chỉ có khoảng trắng |
| B2 | `new Declined(" ")` | Ném `IllegalArgumentException` | Chuỗi chỉ có khoảng trắng |
| B3 | `new Pending(0)` hoặc `new Pending(-1)` | Ném `IllegalArgumentException` | Biên số không hợp lệ |
| E1 | Kiểm tra danh sách `permits` bằng reflection | Mọi kiểu con trực tiếp có fixture kiểm thử | Phát hiện biến thể mới chưa được đưa vào test |

Một số ca có thể gộp bằng **parameterized tests** vì dùng chung quy tắc kiểm tra. Ca `N1` cần tách riêng để làm rõ hợp đồng của API khi tham chiếu kiểu cha bằng `null`.

## 5. Viết kiểm thử với JUnit Jupiter

JUnit Jupiter hỗ trợ `@Test` và `@ParameterizedTest`. `@MethodSource` giúp khai báo từng biến thể cùng kết quả mong đợi ở một chỗ, giảm việc viết ba phương thức thử có cấu trúc lặp lại.

Tệp `src/test/java/example/payment/PaymentFormatterTest.java`:

~~~java
package example.payment;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class PaymentFormatterTest {

    private static Stream<Arguments> validVariants() {
        return Stream.of(
                Arguments.of(
                        new Approved("TX-17"), "APPROVED: TX-17"),
                Arguments.of(
                        new Declined("Invalid card"), "DECLINED: Invalid card"),
                Arguments.of(
                        new Pending(3), "PENDING: 3")
        );
    }

    @ParameterizedTest(name = "variant {index}: {0}")
    @MethodSource("validVariants")
    void formatsEachPermittedVariant(
            PaymentResult result, String expected) {
        assertEquals(expected, PaymentFormatter.format(result));
    }

    @Test
    void rejectsNullResultExplicitly() {
        NullPointerException exception = assertThrows(
                NullPointerException.class,
                () -> PaymentFormatter.format(null));

        assertEquals("result", exception.getMessage());
    }

    @Test
    void rejectsNullFieldsInsideRecords() {
        assertAll(
                () -> assertThrows(
                        NullPointerException.class,
                        () -> new Approved(null)),
                () -> assertThrows(
                        NullPointerException.class,
                        () -> new Declined(null))
        );
    }

    @Test
    void rejectsInvalidRecordValues() {
        assertAll(
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Approved("   ")),
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Declined(" ")),
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Pending(0)),
                () -> assertThrows(
                        IllegalArgumentException.class,
                        () -> new Pending(-1))
        );
    }

    @Test
    void normalizesAllowedWhitespace() {
        assertEquals("TX-17", new Approved("  TX-17  ").reference());
        assertEquals(
                "Invalid card",
                new Declined(" Invalid card ").reason());
    }

    @Test
    void fixturesCoverAllDirectPermittedTypes() {
        assertTrue(PaymentResult.class.isSealed());

        Set<Class<?>> permittedTypes = Arrays.stream(
                PaymentResult.class.getPermittedSubclasses())
                .collect(Collectors.toSet());

        Set<Class<?>> testedTypes = validVariants()
                .map(arguments -> arguments.get()[0].getClass())
                .collect(Collectors.toSet());

        assertEquals(permittedTypes, testedTypes);
    }
}
~~~

### 5.1. Điều gì diễn ra trong bài test tham số hóa?

`validVariants()` cung cấp ba cặp **đầu vào / đầu ra mong đợi**. JUnit chạy phương thức `formatsEachPermittedVariant` riêng cho từng cặp. Như vậy, khi một nhánh xử lý sai, kết quả test cho biết cụ thể biến thể nào không đáp ứng kỳ vọng.

Sử dụng `assertEquals` để kiểm tra **kết quả thực sự**, thay vì chỉ xác nhận chương trình không ném lỗi. Ví dụ, nếu vô tình đổi nội dung nhánh `Declined` thành `"APPROVED: " + declined.reason()`, test dành cho `Declined` sẽ thất bại.

### 5.2. Vì sao phải có test riêng cho `null`?

`rejectsNullResultExplicitly()` xác minh cả **loại ngoại lệ** và **thông báo** để thể hiện hợp đồng đã chọn. Việc dùng `assertThrows` giúp test thành công khi hành vi *từ chối null* xảy ra đúng như thiết kế.

Ngược lại, `rejectsNullFieldsInsideRecords()` kiểm tra **dữ liệu bên trong biến thể**. Đây là hai cấp độ khác nhau:

~~~text
null                      -> không có đối tượng PaymentResult
new Approved(null)        -> cố tạo đối tượng Approved với field null
new Approved("TX-17")     -> đối tượng Approved hợp lệ
~~~

Không nên nghĩ rằng có `sealed` hoặc record thì field tham chiếu tự động khác `null`. Kiểu tham chiếu `String` trong record vẫn có thể nhận `null` nếu constructor không kiểm soát.

### 5.3. Reflection giúp nhận biết khi tập biến thể thay đổi

Java 17 cung cấp hai API reflection phù hợp:

- `Class.isSealed()` kiểm tra một lớp/interface có được khai báo `sealed` không.
- `Class.getPermittedSubclasses()` trả về mảng các kiểu con **trực tiếp** được phép của kiểu `sealed`.

Test `fixturesCoverAllDirectPermittedTypes()` lấy tập kiểu đã được phép bằng reflection, rồi so sánh với tập kiểu thực tế của các fixture trong `validVariants()`.

Ví dụ, nếu sau này lập trình viên thêm:

~~~java
// PaymentResult.java sau khi mở rộng
public sealed interface PaymentResult
        permits Approved, Declined, Pending, Cancelled {
}
~~~

và tạo `record Cancelled(String reason) implements PaymentResult`, nhưng quên bổ sung test cho `Cancelled`, thì tập `permittedTypes` có bốn kiểu, còn `testedTypes` vẫn có ba kiểu. Test guard sẽ **thất bại**, nhắc nhóm phát triển kiểm tra nhánh mới và đưa nó vào dữ liệu kiểm thử.

Test này có ý nghĩa hơn việc ghi cứng một danh sách ba kiểu vào cả mã nguồn và test rồi chỉ so sánh hai danh sách cứng. Tuy nhiên, cần hiểu giới hạn: reflection guard chứng minh **mỗi kiểu con trực tiếp có fixture**, chứ không chứng minh logic của từng nhánh đúng. Vì vậy nó phải đi cùng test `formatsEachPermittedVariant`.

## 6. Chạy kiểm thử bằng Maven với Java 17

Để ví dụ có thể chạy riêng, tạo `pom.xml` ở thư mục `sealed-tests`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>sealed-tests</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **một cấu hình minh họa hợp lệ** với Java 17 và JUnit Jupiter 5; không bắt buộc dùng đúng các phiên bản dependency này trong mọi dự án. Khi đưa vào ứng dụng thực tế, hãy quản lý phiên bản thư viện theo chính sách cập nhật của dự án.

Kiểm tra `java -version` và `mvn -version` để biết Maven đang dùng JDK nào. Tại thư mục chứa `pom.xml`, chạy:

~~~bash
mvn test
~~~

Maven sẽ biên dịch mã chính trong `src/main/java`, biên dịch mã test trong `src/test/java`, rồi chạy các ca kiểm thử. Lần đầu cần tải dependency từ kho Maven, nên phải có kết nối mạng hoặc cache đã chứa chúng.

Ví dụ này không cần `--enable-preview`. Nếu dùng IDE, cấu hình project SDK và target release là Java 17, đồng thời nhập dự án Maven để nhận đúng JUnit dependency.

## 7. Khi chính sách API cho phép `null`

Không có quy tắc duy nhất buộc mọi API đều ném ngoại lệ khi gặp `null`. Bạn có thể chọn một chính sách khác nếu ngữ nghĩa nghiệp vụ thực sự cần:

~~~java
public static String formatNullable(PaymentResult result) {
    if (result == null) {
        return "NO_RESULT";
    }
    return PaymentFormatter.format(result);
}
~~~

Test tương ứng:

~~~java
@Test
void nullableApiReturnsMarkerForNull() {
    assertEquals("NO_RESULT", formatNullable(null));
}
~~~

Ở ví dụ rời này, `formatNullable` là một phương thức của lớp tiện ích do bạn tự khai báo; nếu đưa vào `PaymentFormatter` thì có thể gọi `PaymentFormatter.formatNullable(null)`. Hãy nhất quán giữa quy ước được công bố và test: **hoặc từ chối null, hoặc xử lý nó thành kết quả có nghĩa**; tránh để `null` tình cờ đi qua các phép `instanceof` rồi nhận một ngoại lệ mơ hồ.

Một lựa chọn thiết kế khác là biểu diễn sự vắng mặt bằng **biến thể được đặt tên**:

~~~java
public sealed interface PaymentResult
        permits Approved, Declined, Pending, NotStarted {
}

public record NotStarted() implements PaymentResult {
}
~~~

Đây là **minh họa thay đổi cấu trúc**, không phải hai đoạn có thể chép nối trực tiếp với `PaymentResult.java` cũ mà không điều chỉnh file. Khi thêm `NotStarted`, bạn cần:

1. Tạo tệp `NotStarted.java`, bổ sung record vào `permits`.
2. Xác định định dạng cho `NotStarted` trong formatter.
3. Thêm fixture và expected output vào `validVariants()`; thêm test biên nếu record có dữ liệu.
4. Tiếp tục quyết định riêng xem **`format(null)`** có được phép hay không.

`NotStarted` là một **đối tượng thuộc kiểu con được phép**, còn `null` vẫn là sự vắng mặt của tham chiếu. Hai khái niệm không đồng nhất.

## 8. Những giới hạn cần biết khi dùng kiểm thử để đánh giá tính đầy đủ

### 8.1. Chỉ suy luận được mức trực tiếp của `permits`

`getPermittedSubclasses()` liệt kê **kiểu con trực tiếp**. Giả sử:

~~~java
sealed interface Event permits Completed, Retryable {
}

record Completed() implements Event {
}

non-sealed class Retryable implements Event {
}

final class NetworkRetry extends Retryable {
}
~~~

Reflection trên `Event` trả về `Completed` và `Retryable`, **không** liệt kê `NetworkRetry`. Hơn nữa, nhánh `Retryable` là `non-sealed`, nên về nguyên tắc có thể tiếp tục có nhiều lớp con khác. Một bài test "mỗi kiểu trong `getPermittedSubclasses()` có một fixture" không đảm bảo kiểm thử hết mọi lớp cụ thể trong nhánh mở này.

Nếu cần thực sự quản lý toàn bộ tập biến thể, hãy cân nhắc thiết kế cây kiểu **đóng hoàn toàn bằng `final` hoặc các nhánh `sealed` tiếp tục có giới hạn**, rồi xác định các lá cần test. Nếu chủ động chọn `non-sealed` để mở rộng, hãy kiểm thử theo **hợp đồng và nhóm hành vi** của nhánh mở, cùng các hiện thực cụ thể quan trọng, thay vì khẳng định tập biến thể có số lượng hữu hạn.

### 8.2. Một fixture chưa đủ cho mọi điều kiện biên

Ví dụ, kiểm thử `Pending(3)` chứng minh nhánh định dạng dùng dữ liệu dương thông thường. Nó không chứng minh constructor từ chối `0` hoặc `-1`. Vì vậy ví dụ có cả test kiểm tra mọi biến thể và test điều kiện bất hợp lệ của từng record.

Tương tự, test `Approved("TX-17")` và `Approved(" TX-17 ")` phục vụ hai mục tiêu khác nhau: đầu ra formatter và chuẩn hóa giá trị trong record.

### 8.3. Thêm biến thể cần cập nhật xử lý, không chỉ thêm fixture

Trong Java 17, `if` kết hợp `instanceof` không được kiểm tra exhaustiveness ở compile time. Nếu thêm `Cancelled` vào `permits` và chỉ thêm fixture test mà không sửa formatter, test xử lý `Cancelled` sẽ đi đến `IllegalStateException`.

Đây là hành vi mong muốn từ bộ test: thay đổi model khiến phần xử lý và các trường hợp kiểm thử phải được xem lại cùng nhau. Không nên gắn `default` "bỏ qua" hay dùng `return null` như một cách che giấu việc thiếu nhánh.

### 8.4. Không dùng `null` như một giá trị đại diện cho mọi lỗi

`null` ở **đầu vào** và một phương thức **trả về null** là hai hợp đồng khác nhau. Chẳng hạn, nếu một nhánh formatter trả về `null` khi thất bại, test cần phát hiện rằng nó không đáp ứng yêu cầu trả về thông điệp. Với API công bố kết quả có nhiều trạng thái, nhiều khi biến thể `Declined` hoặc `NotStarted` giúp truyền đạt ý nghĩa rõ hơn một `null` không giải thích gì.

### 8.5. Phân biệt dữ liệu test và dữ liệu production

Không cần cố tạo một lớp tùy ý `implements PaymentResult` để thử "kiểu lạ": cơ chế `sealed` đã chặn lớp ngoài `permits` ngay ở biên dịch hoặc khi kiểm tra ràng buộc kiểu lúc liên kết. Với kiểu đóng hoàn toàn như ba record ban đầu, không có một lớp con trực tiếp thứ tư hợp lệ nếu chưa sửa khai báo `permits`.

Muốn kiểm tra cách formatter phản ứng khi **mô hình thay đổi**, hãy thêm biến thể trong mã nguồn ở một nhánh làm việc riêng, rồi quan sát test guard và test định dạng thất bại cho đến khi được cập nhật. Đó là kiểm thử sự tiến hóa của API, khác với tạo đối tượng vi phạm quy tắc Java.

## 9. Quy trình thực tế khi thêm một biến thể vào `sealed`

Giả sử nhóm phát triển cần trạng thái `Cancelled`. Một quy trình có thể lặp lại:

1. Xác định quy tắc dữ liệu của `Cancelled` và viết record hoặc lớp phù hợp.
2. Bổ sung `Cancelled` vào `permits` của `PaymentResult`.
3. Chạy test để thấy guard phản ánh biến thể mới chưa được phủ.
4. Thêm một hoặc nhiều fixture `Cancelled` với kết quả định dạng mong đợi.
5. Cập nhật `PaymentFormatter.format` để xử lý đúng biến thể mới.
6. Viết test cho `null` hoặc dữ liệu biên bên trong `Cancelled` nếu có.
7. Chạy lại toàn bộ test hiện có, gồm test `null` tại tham số kiểu cha.

Quy trình này tạo mối liên hệ rõ giữa **hợp đồng kiểu dữ liệu**, **hành vi xử lý** và **bộ test**. Khi thêm nhánh, việc sửa test phản ánh thay đổi nghiệp vụ chứ không chỉ nhằm làm số lượng test tăng lên.

## 10. Bài tập vận dụng

### Bài tập 1 — Tìm ca chưa được phủ

Xét khai báo:

~~~java
sealed interface LoadResult permits Loaded, Failed, Loading {
}

record Loaded(String value) implements LoadResult {
}

record Failed(String message) implements LoadResult {
}

record Loading(int percent) implements LoadResult {
}
~~~

Một bộ test hiện chỉ có `new Loaded("data")` và `new Failed("timeout")`. Hãy liệt kê những ca bắt buộc phải thêm để bao phủ đủ biến thể của `sealed`, và thêm một ca cho `format(null)` theo chính sách từ chối `null`.

**Gợi ý:** Còn thiếu `Loading`. Riêng `null` cần một ca độc lập với danh sách `permits`; không được cộng nó vào `getPermittedSubclasses()`.

### Bài tập 2 — Phân biệt hai loại `null`

Tự thiết kế constructor kiểm tra dữ liệu cho `record Loaded(String value)`. Viết hai test riêng: một cho `format(null)` và một cho `new Loaded(null)`. Giải thích tại sao hai test có thể cùng mong đợi `NullPointerException` nhưng vẫn kiểm chứng **hai tầng hợp đồng khác nhau**.

### Bài tập 3 — Phát hiện biến thể mới

Thêm `record Cancelled(String reason) implements PaymentResult` vào dự án ví dụ, cập nhật `permits` nhưng chưa sửa formatter và fixture. Dự đoán test nào thất bại; sau đó bổ sung fixture và nhánh định dạng tương ứng, để test mới thành công.

### Bài tập 4 — Họ kiểu có nhánh mở

Với `sealed interface Event permits Completed, Retryable` ở phần 8, hãy giải thích vì sao test so sánh `getPermittedSubclasses()` với hai fixture không chứng minh rằng mọi lớp con của `Retryable` đã được kiểm thử. Khi nào nên để `Retryable` là `non-sealed`, và khi nào nên thay bằng một thiết kế có tập lá hữu hạn?

## 11. Các ý cần ghi nhớ

- `sealed` giới hạn tập **kiểu con trực tiếp được phép**, nhưng **không loại bỏ `null`** khỏi mọi tham chiếu.
- Muốn kiểm thử các biến thể, hãy tạo **fixture cụ thể cho từng loại**, kết hợp expected output và điều kiện biên.
- Java 17 hỗ trợ `record`, `sealed`, pattern matching for `instanceof` và reflection `getPermittedSubclasses()` mà không cần preview.
- Kết hợp **parameterized test** với **reflection guard** để dễ nhận ra khi ai đó thêm biến thể nhưng chưa bổ sung test.
- `getPermittedSubclasses()` chỉ trả về **kiểu con trực tiếp**; tập con gián tiếp dưới `non-sealed` không thể coi là một danh sách đóng.
- Chính sách `null` phải được định nghĩa rõ và kiểm thử riêng: ném ngoại lệ, xử lý như một trường hợp đặc biệt, hoặc đưa sự vắng mặt có ý nghĩa vào một biến thể có tên.
- Với Java 17, không nên dựa vào cú pháp pattern matching for `switch` ở dạng preview để dạy quy trình kiểm thử cơ bản; `instanceof` và test rõ ràng là đủ cho ví dụ này.

### Tài liệu tham khảo

- [Java SE 17 — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html).
- [Java SE 17 API — `Class.getPermittedSubclasses()` và `Class.isSealed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 API — `Objects.requireNonNull()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html).
- [JUnit Jupiter — User Guide](https://junit.org/junit5/docs/current/user-guide/).
