# Kiểm thử exhaustive switch, guard và các nhánh nghiệp vụ

Java 21 hoàn thiện Pattern Matching for `switch`, cho phép dùng type pattern, record pattern, sealed hierarchy và guard `when` trong `switch` expression hoặc enhanced `switch` statement. Khi kiểm thử, cần xác nhận từng kiểu con và từng nhánh nghiệp vụ được xử lý đúng, đồng thời kiểm tra các giá trị biên như `null`, guard đúng/sai và component null trong nested record pattern.

Một điểm quan trọng: tính *exhaustive* của switch được compiler kiểm tra ở thời điểm biên dịch. Unit test không thể chạy một switch thiếu nhánh vì source đó không biên dịch được. Unit test xác nhận hành vi của các nhánh hợp lệ; build/compile trong CI xác nhận switch vẫn exhaustive khi domain model thay đổi.

Các ví dụ dùng cú pháp Pattern Matching for `switch` chính thức của Java 21, không cần bật preview feature. Phần test minh họa dùng JUnit Jupiter.

## 1. Phân biệt compile-time exhaustiveness và runtime behavior

Switch expression phải exhaustive: mọi giá trị thuộc miền kiểu mà compiler xét phải được bao phủ bởi các nhãn `case`. Enhanced switch statement cũng phải exhaustive. Compiler có thể chứng minh tính exhaustive từ:

- Tất cả constant của một enum.
- Các permitted subtype của sealed class hoặc sealed interface.
- Pattern unconditional bao phủ kiểu selector.
- Nhãn `default` bao phủ các giá trị còn lại.

Ví dụ sealed hierarchy:

```java
sealed interface PaymentResult
        permits Paid, Declined, Pending {}

record Paid(String transactionId, long amount) implements PaymentResult {}
record Declined(String reason) implements PaymentResult {}
record Pending(String reference) implements PaymentResult {}

final class PaymentRouter {
    static String route(PaymentResult result) {
        return switch (result) {
            case null -> "missing";
            case Paid(var id, var amount) when amount < 0 -> "invalid";
            case Paid(var id, var amount) when amount == 0 -> "free";
            case Paid(var id, var amount) -> "captured:" + id;
            case Declined(var reason)
                    when reason == null || reason.isBlank() -> "declined:unknown";
            case Declined(var reason) -> "declined:" + reason;
            case Pending(var reference) -> "pending:" + reference;
        };
    }

    static String routeWithoutNullLabel(PaymentResult result) {
        return switch (result) {
            case Paid(var id, var amount) -> "paid:" + id;
            case Declined(var reason) -> "declined:" + reason;
            case Pending(var reference) -> "pending:" + reference;
        };
    }
}
```

Compiler biết `PaymentResult` chỉ có ba permitted subtype là `Paid`, `Declined` và `Pending`. Các pattern tương ứng bao phủ toàn bộ ba kiểu này; `case null` xử lý thêm giá trị null của selector.

Nếu sau này thêm `Refunded implements PaymentResult` vào `permits` mà không thêm nhánh tương ứng, switch expression trên sẽ không còn exhaustive và quá trình biên dịch thất bại. Đây là kiểm tra compile-time; không có input runtime nào có thể làm unit test đi vào một nhánh còn thiếu trong source không biên dịch.

## 2. Tạo ma trận test cho mọi subtype và nhánh guard

Đừng chỉ tạo một test cho mỗi kiểu con. Một subtype có thể có nhiều nhánh nghiệp vụ được chia bởi guard. Với `Paid`, ví dụ trên có ba trường hợp: amount âm, amount bằng zero và amount dương. Với `Declined`, reason null/rỗng và reason có nội dung đi vào hai nhánh khác nhau.

Ma trận đầu vào nên ghi rõ subtype, dữ liệu biên, guard được kỳ vọng và kết quả:

| Subtype/đầu vào | Điều kiện | Nhánh mong đợi |
|---|---|---|
| `null` | Selector không có giá trị | `case null` |
| `Paid("tx-1", -1)` | `amount < 0` | `invalid` |
| `Paid("tx-2", 0)` | `amount == 0` | `free` |
| `Paid("tx-3", 100)` | Cả hai guard trên đều false | Nhánh `Paid` không guard |
| `Declined(null)` | `reason == null` | `declined:unknown` |
| `Declined(" ")` | `reason.isBlank()` | `declined:unknown` |
| `Declined("fraud")` | Guard null/blank false | Nhánh `Declined` không guard |
| `Pending("p-1")` | Không có guard | Nhánh `Pending` |

Các test cần có ít nhất một trường hợp cho mỗi permitted subtype và mỗi nhánh guard. Với guard dựa trên ngưỡng, thêm giá trị ngay dưới, đúng bằng và ngay trên ngưỡng để xác nhận điều kiện biên.

## 3. Dùng JUnit Jupiter parameterized test

`@ParameterizedTest` kết hợp `@MethodSource` phù hợp khi mỗi test case cần truyền một record hoặc object domain cùng với kết quả mong đợi:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class PaymentRouterTest {

    @ParameterizedTest(name = "case {index}: expected {1}")
    @MethodSource("routeCases")
    void routesEverySubtypeAndBusinessBranch(
            PaymentResult input, String expected) {
        assertEquals(expected, PaymentRouter.route(input));
    }

    static Stream<Arguments> routeCases() {
        return Stream.of(
                Arguments.of((Object) null, "missing"),
                Arguments.of(new Paid("tx-1", -1), "invalid"),
                Arguments.of(new Paid("tx-2", 0), "free"),
                Arguments.of(new Paid("tx-3", 100), "captured:tx-3"),
                Arguments.of(new Declined(null), "declined:unknown"),
                Arguments.of(new Declined(" "), "declined:unknown"),
                Arguments.of(new Declined("fraud"), "declined:fraud"),
                Arguments.of(new Pending("p-1"), "pending:p-1")
        );
    }
}
```

Mỗi phần tử trong `routeCases()` là một test riêng. Khi một trường hợp thất bại, JUnit hiển thị index và expected value, giúp xác định subtype hoặc nhánh nghiệp vụ cần điều tra.

Có thể dùng `@CsvSource` cho đầu vào đơn giản như chuỗi và số. Với sealed hierarchy, record, collection hoặc giá trị null, `@MethodSource` thường dễ đọc và an toàn kiểu hơn. JUnit Jupiter không thuộc JDK; thêm dependency JUnit Jupiter tương thích với build hiện tại của dự án và chạy test bằng test engine tương ứng.

## 4. Kiểm thử guard true, guard false và thứ tự ưu tiên

Guard `when` chỉ được đánh giá sau khi pattern bên trái khớp. Nếu pattern khớp nhưng guard trả `false`, nhãn đó không được chọn và switch tiếp tục xét các nhãn sau.

Ví dụ có hai guard cho cùng kiểu `String`:

```java
final class TextClassifier {
    static String classify(String value) {
        return switch (value) {
            case null -> "missing";
            case String text when text.contains("!") -> "marked";
            case String text when text.length() >= 3 -> "long";
            case String text -> "short";
        };
    }
}
```

Kiểm thử các trường hợp guard true/false và guard chồng lấn:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class TextClassifierTest {

    @ParameterizedTest
    @CsvSource({
            "'go!', marked",
            "'java', long",
            "'io', short"
    })
    void evaluatesGuardsInLabelOrder(String input, String expected) {
        assertEquals(expected, TextClassifier.classify(input));
    }
}
```

`"go!"` thỏa cả `contains("!")` và `length() >= 3`; kết quả `marked` xác nhận nhãn đầu tiên được chọn. `"java"` làm guard thứ nhất false nhưng guard thứ hai true. `"io"` làm cả hai guard false và đi tới pattern `String text` không guard.

Khi thiết kế test guard, hãy kiểm tra:

- Điều kiện đúng và sai.
- Giá trị biên như độ dài 0, 1, ngưỡng - 1, ngưỡng và ngưỡng + 1.
- Hai guard cùng đúng để xác nhận thứ tự ưu tiên.
- Dữ liệu null ở component mà guard truy cập.
- Guard có gọi code có thể ném exception hay không.

Guard nên thuần, nhanh và không có side effect. Không nên cập nhật database, ghi trạng thái hoặc tiêu thụ dữ liệu bên trong guard, vì compiler/runtime có thể đánh giá điều kiện khi pattern đã khớp và logic side effect sẽ làm thứ tự thực thi khó kiểm soát.

## 5. Kiểm thử null riêng với tính exhaustive

`case null` là nhãn riêng. `default` và type pattern như `case Object value` không tự khớp selector null. Vì thế, tính exhaustive theo miền kiểu không có nghĩa switch đã xử lý null.

Nếu switch có `case null`, kiểm thử nhánh đó trực tiếp như test case đầu tiên trong `routeCases()`. Nếu API cố ý không hỗ trợ null, có thể kiểm thử hợp đồng ném `NullPointerException`:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PaymentRouterNullTest {

    @Test
    void rejectsNullWhenSwitchHasNoNullLabel() {
        assertThrows(NullPointerException.class,
                () -> PaymentRouter.routeWithoutNullLabel(null));
    }
}
```

`routeWithoutNullLabel` cần là một switch exhaustive theo các subtype nhưng không có `case null`. Test này xác nhận hành vi runtime của selector null. Nếu nghiệp vụ định nghĩa null là input hợp lệ, hãy dùng `case null` và kiểm thử kết quả nghiệp vụ thay vì kỳ vọng exception.

Không gộp `default` với xử lý null trong suy nghĩ hoặc trong test. Nếu dùng `case null, default`, hãy có test riêng cho cả null và một giá trị khác không được các nhánh trước nhận.

## 6. Kiểm thử nested record pattern và component null

Khi switch phân rã record nhiều tầng, một record component có thể null dù record bên ngoài hợp lệ. Nested record pattern không khớp component null. Trong một switch expression được compiler xem là exhaustive theo cấu trúc record, trường hợp không khớp ngoài dự kiến có thể dẫn đến `MatchException`.

Ví dụ:

```java
record Coordinates(String city) {}
record Address(Coordinates coordinates) {}

final class AddressView {
    static String city(Address address) {
        return switch (address) {
            case null -> "missing-address";
            case Address(Coordinates(var city)) -> city;
        };
    }
}
```

Kiểm thử riêng record ngoài null, component null và dữ liệu đầy đủ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class AddressViewTest {

    @Test
    void handlesNullOuterSelector() {
        assertEquals("missing-address", AddressView.city(null));
    }

    @Test
    void detectsNullNestedRecordComponent() {
        assertThrows(MatchException.class,
                () -> AddressView.city(new Address(null)));
    }

    @Test
    void extractsCityFromNestedRecord() {
        assertEquals("Da Nang",
                AddressView.city(new Address(new Coordinates("Da Nang"))));
    }
}
```

Nếu component có thể null theo nghiệp vụ, thiết kế switch để bắt component ở tầng ngoài rồi xử lý null rõ ràng trước khi phân rã tiếp:

```java
static String citySafely(Address address) {
    return switch (address) {
        case null -> "missing-address";
        case Address(var coordinates) when coordinates == null -> "missing-coordinates";
        case Address(Coordinates(var city)) -> city;
    };
}
```

Sau khi thêm nhánh xử lý component null, test phải xác nhận kết quả fallback thay vì mong đợi `MatchException`. Đây là ví dụ cho thấy test matrix cần bao phủ cấu trúc dữ liệu, không chỉ subtype bên ngoài.

## 7. Kiểm thử enum và sealed hierarchy khi domain thay đổi

### Enum

Nếu switch expression liệt kê đầy đủ enum constant mà không có `default`, compiler sẽ báo lỗi khi một constant mới được thêm và source được biên dịch lại nhưng chưa có nhánh tương ứng.

```java
enum DeliveryState {
    QUEUED, SENT, FAILED
}

static String label(DeliveryState state) {
    return switch (state) {
        case QUEUED -> "Đang chờ";
        case SENT -> "Đã gửi";
        case FAILED -> "Thất bại";
    };
}
```

Có thể dùng `@EnumSource(DeliveryState.class)` để chạy test trên toàn bộ constant hiện tại. Nếu mỗi constant có kết quả riêng, dùng `@MethodSource` để ánh xạ constant sang expected value. Vẫn cần kiểm thử null riêng nếu selector có thể null.

### Sealed hierarchy

Với sealed type, ưu tiên switch expression không có `default` nếu muốn compiler buộc cập nhật khi thêm permitted subtype. Unit test nên tạo ít nhất một instance đại diện cho mỗi subtype và mỗi nhánh guard.

Nếu thêm subtype mới:

1. Cập nhật `permits` và khai báo subtype.
2. Thêm nhánh switch cho subtype mới.
3. Thêm test case tương ứng.
4. Chạy compile và toàn bộ test suite.

Một switch có `default` vẫn exhaustive sau khi subtype mới được thêm, nhưng compiler không buộc người viết cập nhật logic riêng cho subtype đó. Điều này có thể làm một loại nghiệp vụ mới vô tình đi vào fallback chung. Với domain đóng và cần xử lý tường minh, không dùng `default` chỉ để tránh lỗi biên dịch.

## 8. Kiểm thử dominance và lỗi biên dịch

Dominance là quy tắc compile-time: một pattern label không được đặt sau nhãn không guard đã bao phủ mọi giá trị mà pattern sau có thể khớp.

Ví dụ sau không biên dịch vì mọi `String` đều là `CharSequence`, nên nhánh đầu đã dominate nhánh sau:

```java
// Ví dụ lỗi biên dịch — không đưa vào source test đang chạy.
static String invalidOrder(Object value) {
    return switch (value) {
        case CharSequence chars -> "text";
        case String text -> "string"; // Bị dominate
        default -> "other";
    };
}
```

Unit test thông thường không thể gọi phương thức này để kiểm tra exception vì compiler từ chối toàn bộ source trước khi test chạy. Hãy xử lý dominance bằng code review và compile trong CI. Nếu dự án đang phát triển compiler, static analyzer hoặc công cụ kiểm tra source, khi đó mới cần negative compilation test dùng Java Compiler API hoặc framework chuyên dụng để xác nhận diagnostic.

Với code ứng dụng, điều cần test là thứ tự các nhánh hợp lệ và kết quả khi guard true/false; không cố biến lỗi biên dịch thành một test runtime.

## 9. Kiểm thử behavior khi hierarchy thay đổi sau separate compilation

Compiler kiểm tra exhaustiveness dựa trên hierarchy mà nó nhìn thấy khi biên dịch. Nếu sealed hierarchy hoặc enum trong một thư viện được thay đổi rồi triển khai riêng mà consumer không được biên dịch lại, một switch đã biên dịch trước đó có thể gặp giá trị runtime không được các nhánh cũ bao phủ. Java 21 có thể ném `MatchException` trong tình huống này.

Trong quy trình build bình thường, compile lại toàn bộ module phụ thuộc là biện pháp chính. Unit test không thay thế compile-time exhaustiveness. Với hệ thống plugin hoặc thư viện được triển khai độc lập, cần có kiểm thử tương thích phiên bản và kiểm soát việc nâng cấp dependency; chỉ thêm `default` để che lỗi có thể làm mất tín hiệu khi domain thay đổi.

## 10. Đo branch coverage có mục tiêu

Coverage tool cho biết nhánh code nào đã được thực thi, nhưng không tự chứng minh test matrix đầy đủ về mặt nghiệp vụ. Một test có thể chạy qua một dòng switch nhưng không bao phủ cả hai kết quả của guard.

Khi đánh giá coverage, xem xét:

- Mỗi permitted subtype có ít nhất một test.
- Mỗi guard có test true và false.
- Các guard chồng lấn có test xác nhận thứ tự ưu tiên.
- Các biên số học và chuỗi rỗng/null được kiểm tra.
- Nhánh `default` có test với một kiểu thực sự chưa được xử lý.
- `case null` có test riêng.
- Nested record component nullable có test riêng nếu domain cho phép null.
- Các ngoại lệ từ nghiệp vụ/guard được kiểm tra nếu chúng là một phần của hợp đồng API.

Đối với switch dựa trên sealed hierarchy, việc không có `default` giúp compiler hỗ trợ completeness. Coverage vẫn cần để chứng minh kết quả nghiệp vụ của từng nhánh là đúng.

## 11. Chạy kiểm thử trên Java 21 trong CI

Pattern Matching for `switch` đã là tính năng chính thức trong Java 21. Với compiler và runtime Java 21, không cần `--enable-preview` cho các ví dụ switch pattern/guard trong bài.

Nếu dùng `javac` trực tiếp:

```bash
javac --release 21 -d out src/main/java/*.java
```

Sau đó compile và chạy test với JUnit Jupiter theo build tool của dự án. Với Maven hoặc Gradle, cấu hình toolchain/release ở mức Java 21 và chạy task test tương ứng. Điều quan trọng là CI phải compile source chính sau khi domain sealed/enum thay đổi; chỉ chạy test trên bytecode cũ không xác nhận source switch còn exhaustive.

Nên tách rõ ba loại kiểm tra:

| Loại kiểm tra | Điều cần xác nhận | Công cụ |
|---|---|---|
| Compile-time | Switch exhaustive, pattern applicable, không dominance | `javac`/compiler trong build |
| Unit test | Kết quả từng subtype, guard, null và business branch | JUnit Jupiter |
| Integration/contract test | Dữ liệu thật từ API, serialization, versioning và dependency | Test tích hợp theo hệ thống |

## 12. Checklist kiểm thử exhaustive switch

- [ ] Source được compile bằng Java 21, không bật preview cho pattern switch.
- [ ] Switch expression hoặc enhanced switch statement đã exhaustive ở compile time.
- [ ] Với sealed hierarchy, có test cho mọi permitted subtype.
- [ ] Với enum, có test cho mọi constant hiện tại.
- [ ] Không thêm `default` vào domain đóng nếu cần compiler cảnh báo subtype mới.
- [ ] Mỗi guard có test true và false.
- [ ] Guard chồng lấn có test xác nhận thứ tự ưu tiên.
- [ ] Có test cho giá trị biên, null, chuỗi rỗng và component null phù hợp domain.
- [ ] Phân biệt NPE của selector null với MatchException do nested pattern không khớp.
- [ ] Không dùng unit test runtime để kiểm tra source không biên dịch vì dominance/exhaustiveness.
- [ ] CI compile lại tất cả consumer khi sealed hierarchy hoặc enum thay đổi.
- [ ] Coverage được xem cùng test matrix nghiệp vụ, không dùng một con số coverage làm bằng chứng duy nhất.

## Tài liệu tham khảo

- [Pattern Matching for switch Expressions and Statements — Java SE 21](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): pattern label, record pattern, guard `when`, dominance, exhaustiveness và null label.
- [Java Language Specification, Java SE 21 — §14.11 Switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch expression/statement, type coverage và exhaustive switch block.
- [Java Language Specification, Java SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): pattern applicability, total pattern, record pattern và dominance.
- [MatchException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html): lỗi runtime khi switch được xem là exhaustive nhưng không tìm thấy nhãn khớp.
- [JUnit 5 User Guide — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests): `@ParameterizedTest`, `@MethodSource`, `@CsvSource` và `@EnumSource`.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng switch pattern hoàn thiện trong Java 21 và quy tắc thiết kế liên quan.
