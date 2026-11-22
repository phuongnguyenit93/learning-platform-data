# Kiểm thử guard đúng và sai

## 1. Vì sao phải kiểm thử cả hai kết quả của guard?

Pattern matching trong Java tách hai quyết định thường đi cùng nhau:

1. **Pattern có khớp không?** Ví dụ, giá trị đang xét có phải record `Dispatch`, với các component phù hợp, hay không?
2. **Guard có đúng không?** Sau khi pattern khớp, điều kiện bổ sung viết bằng `when` có chấp nhận dữ liệu ấy không?

Từ **Java 21**, một nhánh `switch` có thể kết hợp hai phần:

```java
case Dispatch(var destination, int units)
        when destination != null
                && !destination.isBlank()
                && units >= 10 ->
        "EXPRESS";
```

Đoạn này là ví dụ minh họa bên trong `switch` với record `Dispatch` đã khai báo. Nó không đồng nghĩa “mọi `Dispatch` đều là EXPRESS”. Chỉ khi record pattern **khớp** và toàn bộ biểu thức sau `when` **đúng**, nhánh mới được chọn.

Nếu guard sai, Java tiếp tục xét **các case phù hợp ở phía sau**; một case `Dispatch` không guard có thể xử lý giá trị đó. Nếu pattern không khớp, guard của case ấy **không được đánh giá**.

Ba tình huống phải được phân biệt rõ trong test:

| Tình huống | Pattern | Guard | Hành vi |
| --- | --- | --- | --- |
| Đối tượng `Dispatch("HN", 12)` | Khớp | `true` | Nhánh có guard được chọn, nếu không có nhánh trước đã chọn giá trị. |
| Đối tượng `Dispatch("HN", 0)` | Khớp | `false` | Chuyển sang xét các case phía sau. |
| Đối tượng thuộc `Cancel` | Không khớp `Dispatch` | Không đánh giá | Bỏ qua guard và nhánh `Dispatch`. |

Kiểm thử chỉ với một giá trị khiến guard trả về `true` sẽ không phát hiện được sai sót ở đường `false`, thiếu nhánh dự phòng, sai toán tử so sánh hoặc thứ tự case. Do vậy, bài kiểm thử phải kiểm tra **cả kết quả đúng, kết quả sai và mẫu không khớp**.

## 2. Ngữ nghĩa guard trong switch Java 21

Xét các record:

```java
sealed interface Event permits Dispatch, Cancel {}
record Dispatch(String destination, int units) implements Event {}
record Cancel(String reason) implements Event {}
```

Hàm phân loại nghiệp vụ có thể viết:

```java
static String classify(Event event) {
    return switch (event) {
        case Dispatch(var destination, int units)
                when destination != null
                        && !destination.isBlank()
                        && units >= 10 ->
                "EXPRESS";

        case Dispatch(var destination, int units)
                when destination != null
                        && !destination.isBlank()
                        && units > 0 ->
                "STANDARD";

        case Dispatch ignored -> "INVALID_DISPATCH";

        case Cancel(var reason)
                when reason != null && !reason.isBlank() ->
                "CANCELLED";

        case Cancel ignored -> "INVALID_CANCEL";

        case null -> "NO_EVENT";
    };
}
```

Đoạn trên minh họa đầy đủ logic phân loại và được đưa vào chương trình độc lập ở phần sau.

Có một số điểm quan trọng cho thiết kế test:

- `when` chỉ được xét **sau khi** pattern của chính case ấy khớp.
- Nếu `Dispatch("HN", 10)` thỏa guard thứ nhất, `switch` chọn `EXPRESS`; các case phía sau không được xét.
- `Dispatch("HN", 9)` trượt guard thứ nhất, khớp guard thứ hai và chọn `STANDARD`.
- `Dispatch("HN", 0)` trượt cả hai guard và chọn `INVALID_DISPATCH`.
- `Cancel("user")` không phải `Dispatch`, nên các guard của hai case `Dispatch` không chạy; nó đi đến case `Cancel`.
- `null` là **selector null**, được xử lý bởi `case null`; khác với một component bên trong record bằng null.

Nhánh `case Dispatch ignored` không guard nằm sau hai case có guard. Nếu đặt nó **trước** hai case, nó bao phủ mọi `Dispatch` không null, khiến các case chuyên biệt phía sau bị *dominated* và có thể bị compiler từ chối.

Vì `Event` là `sealed interface` và các subtype trực tiếp `Dispatch`, `Cancel` là record final, những nhánh không guard tương ứng bao phủ mọi biến thể không null. `case null` biểu diễn chính sách selector null, nên `switch expression` trong ví dụ không cần `default`.

## 3. Các loại ca kiểm thử bắt buộc

### 3.1. Guard đúng ở ranh giới

Điều kiện `units >= 10` phải được thử với **`units = 10`**, không chỉ với giá trị lớn như `100`. Ca này giúp phát hiện lỗi thay `>=` bằng `>`.

```java
classify(new Dispatch("HN", 10))  // "EXPRESS"
```

Dòng trên là minh họa lời gọi và kết quả, không phải một lớp Java riêng.

### 3.2. Guard sai ngay sát ranh giới

`units = 9` phải trượt case `EXPRESS` nhưng vẫn có thể khớp case `STANDARD` do `units > 0`.

```java
classify(new Dispatch("HN", 9))   // "STANDARD"
```

Đây là test của **cả nhánh guard sai lẫn khả năng đi tiếp đến case kế tiếp**. Nếu bài kiểm thử chỉ xác minh kết quả khác `EXPRESS` mà không kiểm tra `STANDARD`, có thể bỏ sót lỗi ở nhánh dự phòng.

### 3.3. Cả hai guard đều sai

`units = 0` hoặc âm phải đi đến `INVALID_DISPATCH`, không rơi vào `STANDARD` hoặc trả về một giá trị chung không rõ nghĩa.

```java
classify(new Dispatch("HN", 0))   // "INVALID_DISPATCH"
```

Điều kiện `units > 0` có ranh giới riêng: `0` là false, `1` là true. Đừng chỉ kiểm tra `9` và `10` mà quên ranh giới `0/1`.

### 3.4. Một vế của && sai

Guard không chỉ có điều kiện số; nó kiểm tra điểm đến không null, không blank:

```java
destination != null && !destination.isBlank() && units >= 10
```

Nên có test riêng cho:

- `destination == null`;
- `destination.equals("")`;
- `destination.equals("   ")`;
- `destination` hợp lệ nhưng `units` nhỏ;
- cả hai điều kiện dữ liệu đều hợp lệ.

Nhờ `&&` đánh giá ngắn mạch, khi `destination == null`, Java không gọi `destination.isBlank()`. Nếu đảo điều kiện hoặc dùng `&` không thích hợp, phương thức có thể ném `NullPointerException` trước khi trả kết quả dự kiến.

### 3.5. Pattern không khớp

Test một `Cancel` để đảm bảo không nhầm logic của `Dispatch` với mọi biến thể thuộc `Event`. Vì pattern `Dispatch` không khớp, guard của case `Dispatch` không được xét.

### 3.6. Guard của một subtype khác

`Cancel(var reason) when reason != null && !reason.isBlank()` có một cặp test tương tự: reason hợp lệ chọn `CANCELLED`; reason rỗng, toàn khoảng trắng hoặc null chọn `INVALID_CANCEL`.

### 3.7. Selector null và component null

Hai ca sau **khác nhau**:

```java
classify(null)                   // "NO_EVENT"
classify(new Dispatch(null, 10)) // "INVALID_DISPATCH"
```

Ở trường hợp đầu, selector bằng null và `case null` được chọn. Ở trường hợp sau, đối tượng `Dispatch` tồn tại, component `destination` bằng null; do dùng **`var destination`**, pattern có thể ràng buộc giá trị null, rồi guard trả `false` an toàn.

Nếu thay thành `Dispatch(String destination, int units)`, type pattern `String destination` **không khớp** khi component đó là null. Đây là lý do cần xác định chính xác pattern và dữ liệu test trước khi kết luận một guard false hay một pattern mismatch.

## 4. Ma trận test cho các nhánh

| Dữ liệu đầu vào | Nhánh cần được chọn | Ý nghĩa |
| --- | --- | --- |
| `Dispatch("HN", 10)` | `EXPRESS` | Guard express đúng tại ranh giới. |
| `Dispatch("DN", 11)` | `EXPRESS` | Guard express đúng ở phía trên ranh giới. |
| `Dispatch("HN", 9)` | `STANDARD` | Express sai, standard đúng. |
| `Dispatch("HN", 1)` | `STANDARD` | Guard standard đúng ở ranh giới thấp. |
| `Dispatch("HN", 0)` | `INVALID_DISPATCH` | Cả hai guard số lượng sai. |
| `Dispatch("HN", -1)` | `INVALID_DISPATCH` | Giá trị âm không được chấp nhận. |
| `Dispatch("   ", 10)` | `INVALID_DISPATCH` | Đích chỉ chứa khoảng trắng. |
| `Dispatch("", 100)` | `INVALID_DISPATCH` | Đích rỗng dù số lượng đủ lớn. |
| `Dispatch(null, 11)` | `INVALID_DISPATCH` | Component null; guard an toàn nhờ `&&`. |
| `Cancel("user")` | `CANCELLED` | Pattern khác và guard Cancel đúng. |
| `Cancel(" ")` | `INVALID_CANCEL` | Guard Cancel sai. |
| `Cancel(null)` | `INVALID_CANCEL` | Component null trong record Cancel. |
| `null` | `NO_EVENT` | Selector null, không phải một record. |

Bảng này xác định **kết quả chính xác**, không chỉ khẳng định phương thức “không lỗi”. Với những guard chồng lấn như `units >= 10` và `units > 0`, một đầu vào `10` sẽ thỏa cả hai biểu thức nếu xét độc lập, nhưng **case đầu tiên được chọn**, nên test phải kiểm tra `EXPRESS`.

Ngoài test case theo dữ liệu, cần test cả **thứ tự ưu tiên** và **ý nghĩa nhánh dự phòng**, vì guard sai không nhất thiết đồng nghĩa toàn bộ `switch` thất bại.

## 5. Chương trình Java 21 hoàn chỉnh với bộ test tự chạy

Tạo tệp **`GuardTruthTableDemo.java`**. Chương trình bên dưới không phụ thuộc framework test, dùng `AssertionError` để dừng khi kết quả thực tế khác mong đợi, và in thông báo `PASS` cho mỗi trường hợp thành công.

```java
public class GuardTruthTableDemo {
    sealed interface Event permits Dispatch, Cancel {}

    record Dispatch(String destination, int units) implements Event {}

    record Cancel(String reason) implements Event {}

    static boolean validDestination(String destination) {
        return destination != null && !destination.isBlank();
    }

    static boolean validReason(String reason) {
        return reason != null && !reason.isBlank();
    }

    static String classify(Event event) {
        return switch (event) {
            case Dispatch(var destination, int units)
                    when validDestination(destination) && units >= 10 ->
                    "EXPRESS";

            case Dispatch(var destination, int units)
                    when validDestination(destination) && units > 0 ->
                    "STANDARD";

            case Dispatch ignored ->
                    "INVALID_DISPATCH";

            case Cancel(var reason) when validReason(reason) ->
                    "CANCELLED";

            case Cancel ignored ->
                    "INVALID_CANCEL";

            case null ->
                    "NO_EVENT";
        };
    }

    static void check(String name, Event input, String expected) {
        String actual = classify(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println("PASS " + name + " -> " + actual);
    }

    public static void main(String[] args) {
        check("express-at-10", new Dispatch("HN", 10), "EXPRESS");
        check("express-above-10", new Dispatch("DN", 11), "EXPRESS");

        check("standard-at-9", new Dispatch("HN", 9), "STANDARD");
        check("standard-at-1", new Dispatch("HN", 1), "STANDARD");

        check("zero", new Dispatch("HN", 0), "INVALID_DISPATCH");
        check("negative", new Dispatch("HN", -1), "INVALID_DISPATCH");
        check("blank-destination", new Dispatch("   ", 10),
                "INVALID_DISPATCH");
        check("empty-destination", new Dispatch("", 100),
                "INVALID_DISPATCH");
        check("null-destination", new Dispatch(null, 11),
                "INVALID_DISPATCH");

        check("cancel-valid", new Cancel("user"), "CANCELLED");
        check("cancel-blank", new Cancel(" "), "INVALID_CANCEL");
        check("cancel-null", new Cancel(null), "INVALID_CANCEL");

        check("null-selector", null, "NO_EVENT");
    }
}
```

**Yêu cầu:** JDK 21 trở lên. Biên dịch và chạy, không cần `--enable-preview`:

```bash
javac -encoding UTF-8 GuardTruthTableDemo.java
java GuardTruthTableDemo
```

Đầu ra chính xác khi mọi test đều thành công:

```text
PASS express-at-10 -> EXPRESS
PASS express-above-10 -> EXPRESS
PASS standard-at-9 -> STANDARD
PASS standard-at-1 -> STANDARD
PASS zero -> INVALID_DISPATCH
PASS negative -> INVALID_DISPATCH
PASS blank-destination -> INVALID_DISPATCH
PASS empty-destination -> INVALID_DISPATCH
PASS null-destination -> INVALID_DISPATCH
PASS cancel-valid -> CANCELLED
PASS cancel-blank -> INVALID_CANCEL
PASS cancel-null -> INVALID_CANCEL
PASS null-selector -> NO_EVENT
```

### Vì sao chương trình này kiểm tra được guard đúng và sai?

- Hai dòng đầu xác minh **guard của nhánh EXPRESS đúng** tại và trên ngưỡng. Đây là bằng chứng nhánh đúng được chọn, không chỉ là biểu thức boolean trả true.
- Hai dòng tiếp cho thấy **guard EXPRESS sai**, nhưng **guard STANDARD đúng**; kết quả không bị trả sai thành `INVALID_DISPATCH`.
- Năm dòng `zero`, `negative`, `blank-destination`, `empty-destination`, `null-destination` xác nhận **cả hai case Dispatch có guard đều không được chọn**, và nhánh dự phòng rõ nghĩa được kích hoạt.
- Ba dòng về `Cancel` xác nhận pattern khác được xử lý độc lập; guard của `Cancel` có cả kết quả đúng và sai.
- Dòng cuối xác nhận selector null đi vào `case null`, chứ không bị nhầm với một component null.

Phương thức `check` so sánh trực tiếp giá trị mong đợi với giá trị thực tế. Nếu một case sai, nó ném `AssertionError` và tiến trình dừng; vì vậy chương trình không in “PASS” cho phép kiểm tra sai.

Khác với việc dựa vào từ khóa `assert` của Java, kiểm tra thủ công bằng `if (!expected.equals(actual)) throw new AssertionError(...)` **luôn chạy**. Từ khóa `assert` thông thường có thể bị vô hiệu khi không bật `-ea`, vì vậy nếu chọn dùng `assert`, cần biết chính sách chạy test của dự án.

## 6. Test điều kiện độc lập với test nhánh switch

Giả sử guard là:

```java
when validDestination(destination) && units >= 10
```

Ta có hai loại kiểm thử bổ sung cho nhau:

**A. Unit test cho predicate.** Ví dụ `validDestination(null)` trả `false`, `validDestination("   ")` trả `false`, `validDestination("HN")` trả `true`. Các test này xác nhận hàm điều kiện hoạt động đúng.

**B. Test cho lựa chọn case.** Ví dụ `Dispatch("HN", 9)` phải trả `STANDARD` chứ không chỉ “không phải EXPRESS”. Kết quả còn phụ thuộc vào **thứ tự case** và guard tiếp theo, điều mà unit test predicate riêng không thể kiểm chứng.

Đừng chỉ test `validDestination` rồi cho rằng nhánh `switch` chắc chắn đúng. Cũng đừng chỉ test một đầu vào `Dispatch("HN", 100)` rồi kết luận tất cả vế trong guard đều đã được kiểm tra.

Việc chia predicate thành các hàm **thuần túy (pure)** giúp cả hai lớp test đơn giản hơn: đầu vào giống nhau cho kết quả giống nhau, không cần đoán trạng thái nội bộ thay đổi sau mỗi lần thử.

## 7. Chuyển ca kiểm thử thành JUnit 5

Trong dự án dùng **JUnit Jupiter (JUnit 5)**, có thể chuyển các giá trị biên thành parameterized test. Ví dụ sau là **một tệp test minh họa** tên `GuardTruthTableTest.java`, cùng package với `GuardTruthTableDemo.java`; cần cấu hình dependency JUnit Jupiter và JUnit Platform trong công cụ build của dự án. Nó **không** nằm trong chương trình độc lập ở phần 5 và không thể biên dịch bằng `javac` thuần khi thiếu JUnit.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GuardTruthTableTest {
    @ParameterizedTest
    @CsvSource({
        "0, INVALID_DISPATCH",
        "1, STANDARD",
        "9, STANDARD",
        "10, EXPRESS",
        "11, EXPRESS"
    })
    void unitsBoundaries(int units, String expected) {
        var event = new GuardTruthTableDemo.Dispatch("HN", units);
        assertEquals(expected, GuardTruthTableDemo.classify(event));
    }

    @Test
    void nullDestinationFallsBack() {
        var event = new GuardTruthTableDemo.Dispatch(null, 11);
        assertEquals("INVALID_DISPATCH",
                GuardTruthTableDemo.classify(event));
    }

    @Test
    void cancelWithoutReasonIsInvalid() {
        var event = new GuardTruthTableDemo.Cancel("   ");
        assertEquals("INVALID_CANCEL",
                GuardTruthTableDemo.classify(event));
    }

    @Test
    void nullSelectorUsesItsOwnCase() {
        assertEquals("NO_EVENT", GuardTruthTableDemo.classify(null));
    }
}
```

Đoạn test có hai lợi ích: từng giá trị biên được khai báo trực quan, và khi xảy ra sai lệch, JUnit báo **expected/actual** của ca tương ứng. Ngoài các test trên, nên bổ sung test về dữ liệu âm, reason null và các kết hợp điều kiện khác trong bộ test chính thức.

Nếu dự án cần kiểm tra nhánh ném exception, dùng `assertThrows` phù hợp khi có lỗi hợp đồng. Nhưng **guard false không mặc nhiên là exception**. Trong ví dụ bài này, guard false chọn case dự phòng với kết quả rõ nghĩa; vì vậy `assertEquals` kiểm tra nhánh là thích hợp hơn.

## 8. Test giá trị biên: quan trọng hơn “một ca true, một ca false”

Các toán tử so sánh tạo ranh giới có thể lỗi khi refactor:

| Điều kiện | Giá trị ngay dưới | Giá trị tại ranh giới | Giá trị ngay trên |
| --- | --- | --- | --- |
| `units >= 10` | 9: false | 10: true | 11: true |
| `units > 0` | -1: false | 0: false | 1: true |
| `units <= 5` | 4: true | 5: true | 6: false |
| `units == 10` | 9: false | 10: true | 11: false |

Với điều kiện tổng hợp `validDestination(destination) && units >= 10`, nên kiểm tra mỗi vế có thể làm thay đổi quyết định:

- Destination hợp lệ, units thiếu: `("HN", 9)` ⇒ guard false.
- Destination không hợp lệ, units đủ: `("", 10)` ⇒ guard false.
- Cả hai hợp lệ: `("HN", 10)` ⇒ guard true.
- Destination null: `(null, 10)` ⇒ guard false **mà không ném exception**.

Việc này gần với tư duy *condition coverage*: kiểm tra các điều kiện con tạo ra kết quả đúng và sai. Nó không phải bằng chứng rằng mọi đường thực thi vô hạn đã được bao phủ; các phép kiểm thử được chọn theo hợp đồng domain và những ranh giới có nguy cơ sai.

## 9. Những sai lầm mà test guard phải phát hiện

### 9.1. Sai toán tử so sánh

`units > 10` thay vì `units >= 10` chỉ khác nhau ở ranh giới `10`. Một ca test `units = 100` không bắt được lỗi ấy; ca `10` bắt được.

### 9.2. Sai thứ tự case

Nếu hai guard đều có thể đúng, Java chọn **case phù hợp đầu tiên**. Trong bài, số lượng `10` thỏa cả `>= 10` và `> 0`. Do đó, case `EXPRESS` phải đứng trước `STANDARD`. Nếu đảo thứ tự, `10` có thể bị phân loại thành `STANDARD` dù các guard riêng lẻ đều viết đúng.

Một case không guard như `case Dispatch ignored` nếu đặt trước case có guard sẽ che các nhánh phía sau và có thể gây lỗi *dominated case* khi biên dịch. Kiểm thử runtime không thay thế bước biên dịch với đúng phiên bản Java.

### 9.3. Không xử lý null trong guard

`destination.isBlank()` được gọi khi `destination == null` sẽ ném `NullPointerException`. Một guard **ném exception** không có nghĩa là guard trả false rồi Java tự động sang case tiếp theo; ngoại lệ làm gián đoạn đánh giá theo luồng exception bình thường. Vì vậy, test component null là ca rất quan trọng.

Cách viết an toàn trong bài là `destination != null && !destination.isBlank()`. Khi component được ràng buộc bằng `var`, việc kiểm tra null là trách nhiệm của biểu thức guard nếu API cho phép giá trị ấy.

### 9.4. Chỉ kiểm tra rằng phương thức không ném exception

Giả sử một refactor khiến `Dispatch("HN", 9)` trả `INVALID_DISPATCH` thay vì `STANDARD`. Cả hai kết quả đều là chuỗi hợp lệ và chương trình không ném exception. Test kiểu “does not throw” vẫn có thể PASS; **test expected outcome** mới phát hiện sai nhánh.

### 9.5. Lạm dụng default che thiếu case

Một `default -> "UNKNOWN"` dễ làm test bỏ qua subtype mới trong sealed hierarchy. Nếu domain đóng, nên liệt kê các case không guard bao phủ từng subtype, để compiler kiểm tra exhaustiveness khi cấu trúc mô hình thay đổi. Nếu interface mở, `default` hoặc case tổng quát có thể hợp lý, nhưng phải có chính sách/test rõ ràng cho các implementation chưa biết trước.

### 9.6. Giả định guard chỉ chạy một lần

Khi case đầu có pattern khớp nhưng guard sai, Java có thể tiếp tục thử case sau và đánh giá guard khác. Trong ví dụ này, `validDestination(destination)` có thể được gọi ở hai case `Dispatch` cho một đối tượng có units nhỏ. Các predicate được thiết kế thuần túy nên sự lặp đánh giá không làm đổi kết quả.

Không nên đặt thao tác ghi dữ liệu, gửi sự kiện hay cập nhật trạng thái vào `when` rồi kỳ vọng nó chỉ được gọi một lần trên mỗi `switch`. Nếu có yêu cầu giám sát số lần gọi, nên thêm test có kiểm soát riêng, nhưng **tránh đưa tác dụng phụ vào guard nghiệp vụ** chỉ để thuận tiện test.

## 10. Kiểm thử predicate ném lỗi khác với guard false

Trong Java, **guard false** và **guard gây exception** có hậu quả khác nhau:

- Guard trả `false`: case không được chọn và việc kiểm tra chuyển sang case tiếp theo có thể áp dụng.
- Guard ném exception: phép đánh giá `switch` bị gián đoạn bởi exception, trừ khi có luồng xử lý exception bao quanh phù hợp.

Để kiểm thử một guard có thể ném lỗi do domain (ví dụ truy cập dịch vụ hoặc thực hiện validation), phải xác định chính sách rõ: exception nên được lan truyền, chuyển thành result lỗi hay bắt ở boundary. Đừng vô tình viết `catch (Exception ex) { return "STANDARD"; }` để biến mọi lỗi thành một kết quả nghiệp vụ bình thường.

Trong bộ test, hãy tách:

1. **Ca false hợp lệ** — ví dụ `units = 9` dẫn tới `STANDARD`;
2. **Ca dữ liệu không hợp lệ** — ví dụ `units = 0` dẫn tới `INVALID_DISPATCH`;
3. **Ca lỗi bất thường** — nếu phương thức guard thực sự có thể ném exception, dùng `assertThrows` hoặc cách tương đương để kiểm tra chính xác loại và lý do, theo hợp đồng.

Cách phân loại này giúp test không đồng nhất “không khớp”, “không đủ điều kiện” và “lỗi thực thi”.

## 11. Tự kiểm tra

Giả sử có:

```java
record Score(String subject, int points) {}
```

Viết `switch` sao cho:

- `Score("Java", 80)` trả `PASS`;
- `Score("Java", 79)` trả `RETRY`;
- `Score("SQL", 90)` trả `OTHER_SUBJECT`;
- `null` trả `NO_SCORE`.

Một lời giải Java 21:

```java
static String scoreStatus(Score score) {
    return switch (score) {
        case Score(var subject, int points)
                when "Java".equals(subject) && points >= 80 ->
                "PASS";
        case Score(var subject, int points)
                when "Java".equals(subject) ->
                "RETRY";
        case Score ignored ->
                "OTHER_SUBJECT";
        case null ->
                "NO_SCORE";
    };
}
```

Đoạn này là phương thức minh họa, giả định record `Score` đã được khai báo ở cùng phạm vi.

Bốn ca trên kiểm tra lần lượt: guard đầu đúng; guard đầu sai nhưng guard thứ hai đúng; cả hai guard sai; selector null. Bổ sung `Score(null, 90)` để xác minh cách xử lý subject null: vì dùng `var subject`, `"Java".equals(subject)` trả false an toàn và kết quả là `OTHER_SUBJECT`.

Khi kiểm thử thực tế, cần tránh kết luận chỉ từ “code chạy được”: phải so sánh kết quả chính xác với thiết kế và đặt giá trị ở ngay ranh giới điều kiện.

## 12. Checklist trước khi kết luận guard được kiểm thử đầy đủ

1. Đã có ít nhất một test **pattern khớp + guard true** cho mỗi case có `when`?
2. Đã có test **pattern khớp + guard false** và xác minh **case tiếp theo cụ thể**?
3. Đã có test **pattern không khớp** để bảo đảm guard không được áp dụng sai đối tượng?
4. Đã thử giá trị **ngay dưới, tại và ngay trên** mỗi ngưỡng quan trọng?
5. Đã thử các thành phần **null, chuỗi rỗng, chuỗi toàn khoảng trắng, số 0, số âm** khi domain cho phép chúng xuất hiện?
6. Đã kiểm tra **thứ tự case** khi các guard chồng lấn?
7. Có test riêng cho **selector null** nếu hợp đồng hỗ trợ hoặc từ chối null?
8. Có tách **guard false**, **kết quả dữ liệu không hợp lệ** và **exception thực sự**?
9. Đã so sánh **expected/actual**, không chỉ “không ném exception”?
10. Đã biên dịch bằng đúng JDK, bảo đảm pattern, `when` và `switch` tuân theo phiên bản Java đang sử dụng?

**Ghi nhớ:** Kiểm thử guard không chỉ là truyền một dữ liệu làm `when` đúng và một dữ liệu làm `when` sai. Cần xác minh cả **mẫu khớp hay không**, **case kế tiếp sau khi guard false**, **giá trị biên và null**, **thứ tự ưu tiên của các case**, và **kết quả hoặc exception theo hợp đồng**. Nhờ đó, pattern matching for `switch` trong Java 21 vừa gọn vừa đáng tin cậy khi quy tắc nghiệp vụ thay đổi.
