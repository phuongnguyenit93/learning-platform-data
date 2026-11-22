# Không kiểm thử nhánh “không thể xảy ra” trong Java Pattern Matching

## 1. Vì sao đây là lỗi nguy hiểm?

Trong mã dùng `instanceof`, record patterns và pattern matching cho `switch`, một nhánh xử lý lỗi thường được ghi chú là **“trường hợp này không bao giờ xảy ra”**. Lập trình viên có thể bỏ qua việc kiểm thử vì cho rằng hệ thống đã đảm bảo dữ liệu đúng kiểu, record con luôn tồn tại, hoặc mọi subtype của `sealed interface` đều được liệt kê.

Vấn đề là **“không thể xảy ra” có nhiều nghĩa khác nhau**:

1. **Compiler chứng minh một nhánh bị che khuất hoặc biểu thức sai ngữ nghĩa:** ví dụ `case String s` đã bắt toàn bộ `String`, nên `case String s when s.isEmpty()` sau đó bị *dominated*. Java báo lỗi biên dịch; không có mã chạy để kiểm thử nhánh ấy.
2. **Một nhánh hợp lệ nhưng được cho là không bao giờ nhận dữ liệu trong hệ thống hiện tại:** ví dụ `default` trên một selector kiểu `Object`, nhánh xử lý record con bằng `null`, hoặc điều kiện `when` thất bại. Những nhánh này **có thể chạy** nếu giả định về dữ liệu đầu vào sai.
3. **Một trường hợp bị loại trừ nhờ ràng buộc kiểu hoặc invariant:** ví dụ `sealed interface` có các subtype hữu hạn, hoặc constructor kiểm tra dữ liệu. Đây là bảo đảm mạnh hơn quy ước, nhưng vẫn cần test các **ranh giới của hợp đồng** và hiểu ảnh hưởng của thay đổi mã nguồn, dữ liệu ngoài hoặc phiên bản chạy.
4. **Một nhánh bất thường dùng `throw`:** nó không phải đường thành công, nhưng vẫn là hành vi API có thể quan sát. Không kiểm thử ngoại lệ rất dễ khiến dữ liệu không hợp lệ bị im lặng chấp nhận, đổi loại ngoại lệ hoặc trả thông báo sai.

Bài học tập trung vào **lỗi không kiểm thử các nhánh được cho là bất khả thi** trong Java Core Pattern Matching, cách phân biệt các loại “unreachable”, cách lập ma trận test và cách xác nhận nhánh lỗi một cách có chủ đích.

**Phiên bản Java:** Pattern matching cho `instanceof` là tính năng chuẩn từ Java 16 (JEP 394). Record patterns và pattern matching cho `switch` được chuẩn hóa trong **Java 21** (JEP 440, JEP 441). Ví dụ runnable trong bài sử dụng **JDK 21+**, không cần preview.

## 2. Phân biệt unreachable do compiler với nhánh chưa từng gặp ở runtime

### 2.1. Nhánh bị che khuất: compiler từ chối

Ví dụ sau **không biên dịch** trên Java 21:

```java
// Ví dụ cố ý sai: case String có guard bị nhánh String trước đó bao phủ.
static String dominated(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isEmpty() -> "empty";
        default -> "other";
    };
}
```

`case String s` không có guard khớp mọi đối tượng `String` không null, nên nhánh `case String s when s.isEmpty()` nằm sau không thể được chọn. Compiler báo một lỗi tương đương **“this case label is dominated by a preceding case label”**.

Cách sửa:

```java
static String classifyString(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> "empty";
        case String s -> "any string";
        case null -> "null";
        default -> "other";
    };
}
```

Nhánh cụ thể đứng trước, nhánh bao quát đứng sau; hai nhánh đều có thể được chạy. Với loại sai lầm này, giải pháp đầu tiên là **sửa code để biên dịch**. Không thể viết test runtime để “đi vào nhánh bị dominated” của một chương trình không biên dịch.

Tương tự, một `switch expression` trên `sealed interface` nhưng không có đủ nhánh có thể bị compiler từ chối vì **không exhaustive**. Trường hợp này cũng là vấn đề kiểm tra tĩnh, không nên nhầm với “nhánh đã biên dịch được nhưng test không bao giờ chạy”.

### 2.2. Nhánh fallback hợp lệ vẫn có thể xảy ra

Giả sử một đầu vào bên ngoài được nhận dưới kiểu `Object`:

```java
static String display(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "number";
        case null -> "missing";
        default -> "unexpected";
    };
}
```

Ngay cả khi ứng dụng hiện chỉ gửi `String` và `Integer`, `default` vẫn **có thể chạy**, chẳng hạn khi caller truyền `new Object()`, `Boolean.TRUE` hoặc một kiểu DTO mới. Bỏ qua test cho `default` vì “bên tích hợp không bao giờ gửi kiểu khác” là một giả định về **runtime data**, không phải chứng minh của compiler.

Nếu `default` trả chuỗi mặc định, test cần xác nhận chuỗi đó. Nếu `default` ném ngoại lệ để báo vi phạm hợp đồng, test cần xác nhận **đúng loại ngoại lệ và thông báo**, tránh biến một lỗi dữ liệu thành hành vi khó theo dõi.

### 2.3. Nhánh có `when` không bao phủ toàn bộ một kiểu

```java
record Created(String id, int count) {}

// Đây là snippet minh họa trong phương thức nhận Object value.
return switch (value) {
    case Created(var id, var count) when count > 0 -> "created:" + id;
    case Created(var id, var count) -> "invalid count";
    case null -> "no event";
    default -> "other";
};
```

Một `Created` có `count == 0` hoặc âm **không vào nhánh `when count > 0`**. Nó đi vào nhánh `Created` không guard. Nếu chỉ test `new Created("A", 2)` và tin rằng `count` “luôn dương”, bạn chưa kiểm chứng trường hợp mà guard thất bại.

**Bài học:** phải test cả nhánh guard **đúng và sai**, đặc biệt quanh mốc biên. Với điều kiện `count > 0`, dữ liệu `0` và `-1` thường có giá trị kiểm thử hơn việc lặp nhiều ca dương giống nhau.

## 3. Record patterns lồng nhau: cái tưởng bất khả thi rất dễ có trong thực tế

Xét:

```java
record Envelope(Object payload) {}
record Message(String text) {}
```

Một lập trình viên có thể tin rằng mọi `Envelope` đều chứa `Message` và text không bao giờ null. Nhưng chữ ký `Envelope(Object payload)` không hề cấm:

```java
new Envelope(new Message("hello"));
new Envelope(new Message(null));
new Envelope(null);
new Envelope(42);
```

Nếu không có validation riêng trong constructor hoặc ở ranh giới nhận dữ liệu, **tất cả đều là cách xây dựng record hợp lệ ở mức ngôn ngữ**.

Xét biểu thức:

```java
static String extract(Object input) {
    return switch (input) {
        case Envelope(Message(var text)) when text != null && !text.isBlank()
                -> "text:" + text.trim();
        case Envelope(Message(var text)) -> "empty-text";
        case Envelope(var payload) -> "unexpected-payload";
        case null -> "null-envelope";
        default -> "unsupported";
    };
}
```

Mỗi nhánh có ý nghĩa khác nhau:

| Đầu vào | Nhánh thực sự được chọn | Kết quả |
| --- | --- | --- |
| `new Envelope(new Message(" hello "))` | Nested record pattern + `when` đúng | `text:hello` |
| `new Envelope(new Message(null))` | `Envelope(Message(...))` thứ hai | `empty-text` |
| `new Envelope(new Message("   "))` | Nhánh nested record thứ hai vì `isBlank()` | `empty-text` |
| `new Envelope(null)` | `Envelope(var payload)` | `unexpected-payload` |
| `new Envelope(42)` | `Envelope(var payload)` | `unexpected-payload` |
| `null` | `case null` | `null-envelope` |
| `"not-envelope"` | `default` | `unsupported` |

Điểm dễ sai nhất: **record con bằng null làm nested record pattern không khớp, nhưng component `var text` của một record `Message` đã tồn tại vẫn có thể nhận null**.

Do đó `Envelope(Message(var text))` không có nghĩa là `text != null`. Guard `text != null && !text.isBlank()` cần được giữ, và case `Message(null)` phải có test riêng nếu input có thể tới từ dữ liệu ngoài.

Với guard `text != null && !text.isBlank()`, toán tử `&&` ngắn mạch nên không gọi `isBlank()` trên null. Nếu đổi thành `text == null || text.isBlank()` để diễn đạt tình trạng lỗi thì logic vẫn có thể an toàn; nhưng đổi thứ tự hoặc toán tử sai có thể gây `NullPointerException`. Test null giúp phát hiện thay đổi vô ý này.

## 4. `sealed interface` và exhaustiveness không thay thế kiểm thử hành vi

Giả sử:

```java
sealed interface Event permits Created, Deleted {}
record Created(String id, int count) implements Event {}
record Deleted(String id) implements Event {}
```

Một `switch expression` có thể bao phủ mọi subtype hiện được cho phép:

```java
static String handle(Event event) {
    return switch (event) {
        case null -> "no-event";
        case Created(var id, var count) when count > 0 -> "created:" + id;
        case Created(var id, var count) -> "bad-count:" + id;
        case Deleted(var id) -> "deleted:" + id;
    };
}
```

Không có `default` vì compiler biết `Event` chỉ có các implementation trực tiếp được cho phép trong hệ kiểu này, và các nhánh đã bao phủ `Created`/`Deleted`. Nhánh `Created` không guard sau `when` bảo đảm mọi giá trị `Created` được xử lý.

Ưu điểm của việc **không viết `default` vô điều kiện** trên một hierarchy sealed đã được bao phủ: nếu sau này sửa định nghĩa để cho phép subtype mới và biên dịch lại code phụ thuộc, compiler có thể yêu cầu cập nhật `switch`. Một nhánh `default -> "unknown"` có thể che mất lời nhắc này.

Nhưng exhaustive checking **không chứng minh logic từng nhánh đúng**. Nó không bảo đảm `count > 0`, không bảo đảm `id != null` và không tự kiểm tra chất lượng chuỗi trả về. Vì vậy vẫn phải test:

- `Created` với `count > 0`.
- `Created` với `count == 0` hoặc âm, để kiểm tra nhánh có `when` false.
- `Deleted`.
- `null` nếu API cho phép, vì kiểm tra null của selector là vấn đề riêng.
- Các ràng buộc dữ liệu như `id == null` nếu chúng ảnh hưởng đến nghiệp vụ.

Nếu một hierarchy sealed thay đổi **không đồng bộ giữa lúc biên dịch và lúc chạy** (ví dụ binary của các module khác phiên bản), giả định exhaustiveness cũ có thể không còn đúng tại runtime và có thể dẫn tới `java.lang.MatchException` theo ngữ nghĩa pattern switch. Đây là tình huống triển khai/binary compatibility đặc biệt: ưu tiên kiểm thử khả năng tương thích phiên bản khi hệ thống thực sự triển khai kiểu module tách rời, thay vì cố mô phỏng một subtype Java mà compiler không cho khai báo.

**Kết luận phần này:** compiler giúp kiểm tra **độ bao phủ cấu trúc**, còn test giúp xác nhận **kết quả nghiệp vụ, đường đi lỗi và ranh giới dữ liệu**. Hai lớp bảo vệ bổ sung chứ không thay thế nhau.

## 5. Nhánh “đáng lẽ phải throw”: hãy kiểm tra ngoại lệ thật sự

Một số hệ thống muốn fail fast thay vì trả giá trị mặc định cho cấu trúc sai. Ví dụ:

```java
static String mustBeMessage(Object input) {
    if (!(input instanceof Message(var text))) {
        throw new IllegalArgumentException("expected Message");
    }
    if (text == null) {
        throw new IllegalArgumentException("missing text");
    }
    return text;
}
```

Đừng chỉ test `mustBeMessage(new Message("ok"))`. Cần test riêng:

1. `mustBeMessage(null)` ném `IllegalArgumentException` với thông báo `expected Message`.
2. `mustBeMessage(42)` ném cùng loại ngoại lệ và thông báo, vì sai kiểu.
3. `mustBeMessage(new Message(null))` ném `IllegalArgumentException` với thông báo `missing text`.
4. `mustBeMessage(new Message(""))` **không bị từ chối bởi hợp đồng hiện tại**, vì code chỉ chặn null. Nếu muốn cấm chuỗi rỗng, phải bổ sung điều kiện và test khác.

Nếu test chỉ có happy path, một refactor sai có thể đổi exception thành `NullPointerException`, đổi thông báo, trả null hoặc bỏ hoàn toàn việc từ chối. Tất cả đều có thể là thay đổi có hại đối với caller.

Với JUnit 5, ý tưởng là dùng `assertThrows(IllegalArgumentException.class, () -> ...)` rồi kiểm tra message nếu message thuộc hợp đồng cần giữ. Để bài có thể chạy độc lập **không cần thư viện test bên ngoài**, ví dụ hoàn chỉnh dưới đây dùng helper `expectReject` với `Runnable` và `AssertionError`.

## 6. Ví dụ Java 21 chạy được: kiểm thử 15 tình huống, kể cả nhánh bị gọi là “impossible”

Tạo tệp **`ImpossibleBranchTestDemo.java`**:

```java
public class ImpossibleBranchTestDemo {
    sealed interface Event permits Created, Deleted {}
    record Created(String id, int count) implements Event {}
    record Deleted(String id) implements Event {}
    record Envelope(Object payload) {}
    record Message(String text) {}

    static String handle(Event event) {
        return switch (event) {
            case null -> "no-event";
            case Created(var id, var count) when count > 0 -> "created:" + id;
            case Created(var id, var count) -> "bad-count:" + id;
            case Deleted(var id) -> "deleted:" + id;
        };
    }

    static String extract(Object input) {
        return switch (input) {
            case Envelope(Message(var text)) when text != null && !text.isBlank()
                    -> "text:" + text.trim();
            case Envelope(Message(var text)) -> "empty-text";
            case Envelope(var payload) -> "unexpected-payload";
            case null -> "null-envelope";
            default -> "unsupported";
        };
    }

    static String mustBeMessage(Object input) {
        if (!(input instanceof Message(var text))) {
            throw new IllegalArgumentException("expected Message");
        }
        if (text == null) throw new IllegalArgumentException("missing text");
        return text;
    }

    static int checked;

    static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " expected " + expected + " but got " + actual);
        }
        checked++;
        System.out.println("PASS " + label + " => " + actual);
    }

    static void expectReject(String label, Runnable action, String message) {
        try {
            action.run();
            throw new AssertionError(label + " should reject input");
        } catch (IllegalArgumentException ex) {
            if (!message.equals(ex.getMessage())) {
                throw new AssertionError(label + " wrong error: " + ex.getMessage());
            }
            checked++;
            System.out.println("PASS " + label + " => rejected: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        expect("created", "created:A", handle(new Created("A", 2)));
        expect("bad-created", "bad-count:B", handle(new Created("B", 0)));
        expect("deleted", "deleted:C", handle(new Deleted("C")));
        expect("null-event", "no-event", handle(null));
        expect("nested-valid", "text:hello", extract(new Envelope(new Message(" hello "))));
        expect("null-text", "empty-text", extract(new Envelope(new Message(null))));
        expect("blank-text", "empty-text", extract(new Envelope(new Message("   "))));
        expect("null-payload", "unexpected-payload", extract(new Envelope(null)));
        expect("wrong-payload", "unexpected-payload", extract(new Envelope(42)));
        expect("null-input", "null-envelope", extract(null));
        expect("wrong-outer", "unsupported", extract("not-envelope"));
        expect("strict-success", "ok", mustBeMessage(new Message("ok")));
        expectReject("strict-null", () -> mustBeMessage(null), "expected Message");
        expectReject("strict-wrong", () -> mustBeMessage(42), "expected Message");
        expectReject("strict-missing", () -> mustBeMessage(new Message(null)), "missing text");
        System.out.println("checks=" + checked);
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 ImpossibleBranchTestDemo.java
java ImpossibleBranchTestDemo
```

**Kết quả chuẩn:**

```text
PASS created => created:A
PASS bad-created => bad-count:B
PASS deleted => deleted:C
PASS null-event => no-event
PASS nested-valid => text:hello
PASS null-text => empty-text
PASS blank-text => empty-text
PASS null-payload => unexpected-payload
PASS wrong-payload => unexpected-payload
PASS null-input => null-envelope
PASS wrong-outer => unsupported
PASS strict-success => ok
PASS strict-null => rejected: expected Message
PASS strict-wrong => rejected: expected Message
PASS strict-missing => rejected: missing text
checks=15
```

Trong ví dụ:

- `handle` kiểm chứng cả `Created` hợp lệ, `Created` có count bằng 0, `Deleted` và null. `case Created ... when count > 0` không được coi là trường hợp duy nhất cần kiểm thử.
- `extract` chứng minh nhánh `Envelope(var payload)` và `default` **có thể chạy** dù nhiều ứng dụng tin rằng payload luôn là `Message`.
- `mustBeMessage` kiểm tra ba đường từ chối: đầu vào null, sai kiểu và component text null.
- Helper `expect` so sánh kết quả với kỳ vọng và ném `AssertionError` ngay khi sai. Helper `expectReject` bảo đảm thao tác thực sự ném **IllegalArgumentException** với thông báo dự kiến; nếu thao tác kết thúc bình thường, test cũng thất bại.

Lệnh `checks=15` chứng tỏ **15 phép kiểm tra trong chương trình** đã vượt qua. Nó **không phải bằng chứng mọi đường chạy và dữ liệu đều đã được bao phủ**. Test suite thực tế cần thêm giá trị biên khác, dữ liệu sai định dạng, tương tác bên ngoài và các trường hợp mới theo hợp đồng ứng dụng.

## 7. Thiết kế ma trận kiểm thử thay vì chỉ test happy path

Khi đọc một `switch` pattern, hãy liệt kê các **nhánh được chọn** và các điều kiện làm nhánh đó không được chọn. Sau đó dùng giá trị cụ thể để kích hoạt từng nhóm:

| Loại đường đi | Đầu vào gợi ý | Điều cần khẳng định |
| --- | --- | --- |
| Type/record pattern khớp | Đối tượng hợp lệ | Nhánh thành công sinh đúng giá trị. |
| `when` đúng | Giá trị vượt ngưỡng | Nhánh có guard được chọn. |
| `when` sai, cùng record | Giá trị bằng ngưỡng hoặc thấp hơn | Nhánh dự phòng cùng type được chọn. |
| Selector null | `null` | `case null` hoặc ngoại lệ theo hợp đồng. |
| Nested record con null | `Envelope(null)` | Nested pattern không khớp; nhánh ngoài phù hợp được xử lý. |
| Component con null | `new Message(null)` bên trong record hợp lệ | `var text` có thể ràng buộc null; guard không dereference null. |
| Kiểu không phù hợp | `Envelope(42)` hoặc raw `String` | Nhánh fallback xử lý đúng. |
| Dữ liệu biên | `count == 0`, `count == -1`, chuỗi trắng | Quy tắc nghiệp vụ đúng tại ranh giới. |
| Nhánh `throw` | Sai kiểu, thiếu dữ liệu bắt buộc | Kiểm tra loại ngoại lệ, thông báo và việc không có kết quả thành công. |
| Hierarchy thay đổi | Thêm subtype hợp lệ khi biên dịch lại | Build/test buộc cập nhật nhánh xử lý nếu switch không có `default` và trước đó dựa vào exhaustive matching. |

**Không tạo test một cách máy móc cho nhánh compiler đã xác định không thể tồn tại.** Nếu compiler báo dominated case hoặc non-exhaustive switch, cần sửa mã nguồn trước. Ma trận kiểm thử dành cho **các đường chạy hợp lệ mà chương trình đã biên dịch có thể gặp**, kể cả những đường ít thấy trong production.

## 8. Lợi ích và giới hạn của branch coverage

**Branch coverage** giúp phát hiện có nhánh `case`/`if` nào chưa được thực thi trong test suite hay không. Nhưng một phần trăm coverage cao chưa chứng minh đã kiểm tra toàn bộ ràng buộc:

- Cùng một `case Created(...)` có thể tạo giá trị sai khi `count == 0` dù nhánh ấy đã được chạy với `count == 5`.
- Một `when` có nhiều toán hạng như `text != null && !text.isBlank()` có ít nhất các tình huống quan trọng: text null, text trắng, text hợp lệ. Chỉ đo branch coverage có thể chưa đủ để phát hiện lỗi ở từng điều kiện con.
- Các trường hợp dữ liệu bên ngoài đổi schema, version không tương thích, side effect hoặc exception có thể đòi hỏi integration tests, contract tests hay regression tests.
- Đường được coi là unreachable có thể do invariant được kiểm chứng ở nơi khác. Khi đó hãy kiểm thử **nơi thiết lập invariant** và hành vi từ chối dữ liệu vi phạm, thay vì tìm mọi cách xuyên qua lớp bảo vệ chỉ để tăng coverage.

Một quy trình tốt là kết hợp **bảng ca kiểm thử theo phân vùng dữ liệu**, **giá trị biên**, assertions về ngoại lệ và phép đo coverage. Nếu test chạy vào nhánh fallback, phải xác nhận hành vi trong nhánh ấy phù hợp hợp đồng chứ không chỉ ghi nhận rằng nó đã được thực thi.

Tránh “chữa” coverage bằng cách thêm `default -> null` ở mọi `switch`: điều đó có thể che một trạng thái dữ liệu lạ và làm caller tiếp tục với kết quả không hợp lệ. Fallback nên trả lỗi rõ ràng hoặc `throw` khi yêu cầu nghiệp vụ là fail fast.

## 9. Làm mạnh invariant để nhánh thực sự khó xuất hiện hơn

Nếu ứng dụng yêu cầu text luôn có giá trị không rỗng, nên diễn đạt ràng buộc ngay tại chỗ khởi tạo dữ liệu:

```java
record NonBlankMessage(String text) {
    NonBlankMessage {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }
    }
}
```

Compact constructor của record kiểm tra điều kiện trước khi instance hợp lệ được tạo qua constructor ấy. Nhờ đó, dữ liệu thông thường đi qua kiểu `NonBlankMessage` có invariant mạnh hơn một `record Message(String text)` không có validation. Tuy nhiên vẫn cần test:

- `new NonBlankMessage("hello")` thành công.
- `new NonBlankMessage(null)` bị từ chối.
- `new NonBlankMessage(" ")` bị từ chối.
- Một đường nhận dữ liệu ngoài dùng đúng validation trước khi chuyển thành đối tượng tin cậy.

Có những bảo đảm do **type system** cung cấp (như hierarchy sealed), có những bảo đảm do **constructor validation** cung cấp, và có những giả định chỉ nằm trong **comment hoặc suy nghĩ của lập trình viên**. Mức độ test phụ thuộc vào lớp bảo vệ: đừng coi một comment “never null” mạnh tương đương với mã kiểm tra được thực thi.

Nếu nhánh thật sự chỉ dùng để báo vi phạm invariant mà không có đường hợp lệ để vào, nên đặt thông báo rõ như `throw new IllegalStateException("Unexpected state")` hoặc bảo đảm kiểu thay vì lặng lẽ trả một giá trị giả. Hãy có tests tại điểm nhận dữ liệu hoặc xây dựng state để xác nhận invariant, cùng logging/monitoring phù hợp với hệ thống.

## 10. Những ngộ nhận và lỗi hay gặp

| Lỗi | Vì sao không ổn | Cách kiểm tra/sửa |
| --- | --- | --- |
| “`default` không bao giờ chạy” vì backend hiện chỉ gửi hai kiểu | Selector `Object` còn có nhiều kiểu runtime khác. | Test một kiểu ngoài tập hợp dự kiến; dùng fallback hoặc lỗi rõ. |
| “Tất cả `Created` đều có count dương” | `record Created(String id, int count)` tự nó không chặn 0/âm. | Test `0` và `-1`, bổ sung validation nếu cần. |
| “Nested record pattern khớp thì mọi component đều non-null” | Record con cần khác null để deconstruct, nhưng component `var text` vẫn có thể null. | Test record con null và component null riêng rẽ. |
| Chỉ test `when` true | Guard false có thể chọn nhánh khác, kể cả nhánh lỗi. | Dùng giá trị ở hai phía của ranh giới và đúng tại ranh giới. |
| Không test `case null` | Selector null có xử lý khác với record component null. | Test null như một đầu vào độc lập. |
| Thêm `default` để switch sealed luôn biên dịch | Dễ bỏ sót subtype mới ở lần biên dịch sau. | Khi muốn compiler buộc cập nhật subtype, liệt kê case exhaustive không default. |
| Cố gọi nhánh bị dominated để tăng coverage | Compiler Java từ chối nhánh bị che khuất. | Sửa thứ tự case; không tìm cách tạo runtime test cho mã không biên dịch. |
| Xem `throw` là “không quan trọng vì là lỗi” | Loại ngoại lệ và message ảnh hưởng hợp đồng caller. | Test bằng `assertThrows` hoặc helper kiểm tra ngoại lệ. |
| Chỉ chạy happy path rồi kết luận refactor tương đương | Không biết lỗi sai kiểu, null, giá trị biên có bị thay đổi. | Test hồi quy cả thành công và thất bại. |
| Tin rằng 100% coverage đồng nghĩa đúng mọi đầu vào | Coverage đo sự thực thi, không kiểm chứng mọi giá trị và kỳ vọng. | Kết hợp data partitions, boundary, negative và contract tests. |
| Gọi mọi fallback là “impossible” rồi trả null | Làm lỗi bị che và phát sinh NPE muộn hơn. | Ghi rõ lý do, fail fast hoặc trả lỗi có kiểu. |
| Không xem lại assumptions khi thêm subtype/đổi schema | Những đường trước đây hiếm có thể trở thành bình thường. | Cập nhật test matrix khi thay hợp đồng dữ liệu và hệ kiểu. |

## 11. Bài tập tự kiểm tra: tìm nhánh bị bỏ quên

Cho hai record:

```java
record Coordinates(int x, int y) {}
record Wrapper(Object payload) {}
```

Mã xử lý:

```java
static String inspect(Object value) {
    return switch (value) {
        case Wrapper(Coordinates(var x, var y)) when x >= 0 && y >= 0
                -> "valid:" + x + "," + y;
        case Wrapper(Coordinates(var x, var y)) -> "negative";
        case Wrapper(var payload) -> "unknown payload";
        case null -> "null input";
        default -> "other";
    };
}
```

Một nhóm test mới viết đúng một ca:

```java
// Test còn thiếu rất nhiều đường đi.
inspect(new Wrapper(new Coordinates(2, 3))); // "valid:2,3"
```

**Câu hỏi:** Các nhánh “không thể xảy ra” nào cần kiểm tra thêm? Hãy chọn dữ liệu làm thay đổi kết quả.

Gợi ý đáp án:

1. `new Wrapper(new Coordinates(-1, 3))` → `negative`.
2. `new Wrapper(new Coordinates(2, -1))` → `negative`.
3. `new Wrapper(new Coordinates(0, 0))` → `valid:0,0`, kiểm tra ranh giới `>= 0`.
4. `new Wrapper(null)` → `unknown payload`, vì nested `Coordinates(...)` không khớp null.
5. `new Wrapper("text")` → `unknown payload` vì sai kiểu component.
6. `null` → `null input`.
7. `new Object()` → `other`.

Các đoạn bài tập là snippet minh họa sử dụng hai record đã khai báo. Tệp đầy đủ có `main`, lệnh chạy và 15 checks ở mục 6 có thể dùng làm mẫu để viết tests tương tự.

Nếu có thêm invariant “x, y luôn không âm” từ lớp xác thực dữ liệu, hãy viết tests cho **lớp xác thực** ấy; không chỉ bỏ nhánh `negative` khỏi test vì một câu nhận định không được mã hóa. Nếu `Wrapper.payload` được đổi từ `Object` sang một kiểu cụ thể, hãy cập nhật ma trận dựa trên kiểu mới, không sao chép máy móc những test không còn ý nghĩa.

## 12. Checklist phòng tránh lỗi khi review code

Trước khi chấp nhận một đoạn pattern matching có nhánh bị gọi là “unreachable”, trả lời những câu hỏi sau:

1. Nhánh đó **không thể biên dịch vì bị dominated**, hay **vẫn có thể chạy với dữ liệu runtime khác kỳ vọng**?
2. Selector có thể bằng null không? **`case null`** có được xử lý theo hợp đồng?
3. Có `record` con nullable không? Component `var` có thể null không?
4. `when` có test ở **hai chiều true/false** và các giá trị biên không?
5. Có nhánh `default`/fallback hợp lệ không, và đã test đầu vào kích hoạt nó chưa?
6. Với `sealed`, switch có đầy đủ subtype không, và có vô tình thêm `default` che sự thiếu sót khi thêm subtype không?
7. Đường `throw` có test **đúng loại ngoại lệ** và thông báo cần thiết không?
8. Invariant “không thể xảy ra” được bảo đảm bởi type system, constructor/validation hay chỉ bởi giả định?
9. Khi nguồn dữ liệu hoặc phiên bản triển khai thay đổi, test nào phát hiện phá vỡ hợp đồng?
10. Có kết hợp **branch coverage + giá trị biên + negative tests**, thay vì chỉ dựa vào số phần trăm coverage không?

**Ghi nhớ:** Không thể và không cần ép runtime test chạy vào một nhánh mà compiler đã loại bỏ. Nhưng mọi nhánh **có thể biên dịch và có thể nhận dữ liệu hợp lệ về mặt kiểu**, dù bị gọi là “không bao giờ xảy ra”, đều cần được đánh giá theo hợp đồng nghiệp vụ. Test các nhánh null, kiểu không khớp, `when` false, nested record thiếu dữ liệu và ngoại lệ chính là cách phát hiện giả định sai trước khi chúng trở thành lỗi production.

**Tài liệu tham khảo:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Java SE 21 JLS — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30), [Java SE 21 JLS — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28).
