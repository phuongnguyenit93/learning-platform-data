# Refactor `switch` trên type tag bằng pattern matching (Java 21+)

## 1. Vấn đề: type tag cộng với ép kiểu thủ công

**Type tag** là một giá trị biểu thị loại dữ liệu, ví dụ `"EMAIL"`, `"SMS"`, `"PUSH"`. Trong mã Java cũ, kiểu xử lý thường là **`switch` trên chuỗi/enum tag**, sau đó **ép kiểu** phần payload về class tương ứng:

```java
// Minh họa ý tưởng, đặt trong phương thức có biến tag và payload.
switch (tag) {
    case "EMAIL":
        Email email = (Email) payload;
        System.out.println(email.to());
        break;
    case "SMS":
        Sms sms = (Sms) payload;
        System.out.println(sms.phone());
        break;
    default:
        System.out.println("unsupported");
}
```

Nhược điểm cốt lõi: **`tag` và kiểu thực tế của `payload` là hai nguồn thông tin riêng biệt**. Java không thể tự chứng minh `"EMAIL"` luôn đi kèm một `Email`. Nếu tag là `"EMAIL"` nhưng payload thực tế là `Sms`, lệnh `(Email) payload` ném `ClassCastException`. Nếu payload là `null`, ép kiểu về class tham chiếu có thể cho `null`, nhưng việc gọi accessor trên nó sẽ gây `NullPointerException`.

Phần code trên còn cần nhiều nhánh ép kiểu lặp lại. Khi thêm một loại mới, lập trình viên phải tự cập nhật enum/tag, class dữ liệu, nhánh `switch` và kiểm thử tương thích giữa chúng.

**Mục tiêu refactor:** để **kiểu runtime của đối tượng** làm cơ sở phân nhánh khi xử lý dữ liệu nội bộ, thay vì tin hoàn toàn vào một type tag song song. Với Java 21+, có thể dùng `switch` trên đối tượng với **type patterns** hoặc **record patterns**, và thường dùng một **sealed hierarchy** để compiler kiểm tra các biến thể đã xử lý.

> Phân biệt: `switch(tag)` có thể vẫn cần ở ranh giới nhận dữ liệu JSON, message queue hoặc giao thức truyền thông. Việc thay `switch` trên tag bằng pattern matching **không có nghĩa xóa tag khỏi mọi giao thức**. Nên xác thực tag và chuyển sang kiểu nội bộ tại ranh giới, rồi tránh phụ thuộc vào tag trong phần xử lý nghiệp vụ.

## 2. Điều kiện ngôn ngữ và lựa chọn hướng refactor

- **Java 16:** Type pattern trong `instanceof` là tính năng chính thức (JEP 394); có thể dùng để bỏ cast thủ công dù chưa có pattern matching for `switch` chính thức.
- **Java 21:** Pattern matching for `switch` và record patterns chính thức (JEP 441, JEP 440). Ví dụ ở bài này dùng `case Email(var to, var text) -> ...` và **JDK 21+**, không cần `--enable-preview`.
- **Sealed types:** được chuẩn hóa từ Java 17 (JEP 409); dùng `sealed interface` và `permits` để biểu diễn một tập biến thể có chủ đích.

Hai cấp refactor phổ biến:

1. **Refactor cục bộ:** vẫn nhận `Object`, chuyển `switch(tag) + (TargetType) payload` thành các kiểm tra `instanceof TargetType t`. Cách này bỏ cast nguy hiểm nhưng thường vẫn cần `else`/`default` vì hệ kiểu chưa đóng.
2. **Refactor mô hình dữ liệu:** định nghĩa một kiểu chung `Notice` với các subtype cụ thể như `Email`, `Sms` và `Push`; dùng `switch(notice)` với pattern. Cách này bỏ tag khỏi **mô hình nội bộ**, làm rõ các biến thể hợp lệ và giúp compiler kiểm tra tính bao phủ của `switch expression`.

**Không thể** chỉ giữ `switch(tag)` với selector là `String` rồi viết `case Email(var to, var text)` trên chuỗi ấy. Muốn match theo subtype, **selector phải là đối tượng có thể mang subtype đó**, ví dụ `Notice notice`.

## 3. Mô hình ví dụ: nhận envelope legacy và chuyển sang kiểu nội bộ

Ta có nguồn cũ:

```java
record LegacyEnvelope(String tag, Object payload) {}
```

`LegacyEnvelope.tag` là tên loại do bên gửi cung cấp; `payload` có kiểu tĩnh `Object`. Dữ liệu nội bộ sau refactor:

```java
sealed interface Notice permits Email, Sms, Push {}

record Email(String to, String text) implements Notice {}
record Sms(String phone, String text) implements Notice {}
record Push(String device, String text) implements Notice {}
```

Mỗi bản ghi là một biến thể rõ ràng: `Email` có `to`; `Sms` có `phone`; `Push` có `device`. Một `Notice` hợp lệ trong mô hình này phải là một trong ba subtype được phép. Sealed interface giúp compiler biết những biến thể cần xét, còn record giúp tạo, giữ và đọc các component.

Quan trọng: **type tag từ nguồn ngoài không tự chuyển thành một `Notice`**. Cần một hàm adapter kiểm tra cặp `tag/payload` trước khi đi vào phần code nghiệp vụ.

## 4. Cách cũ: switch tag và cast

```java
static String legacy(LegacyEnvelope input) {
    if (input == null || input.tag() == null) return "invalid";

    return switch (input.tag()) {
        case "EMAIL" -> {
            Email e = (Email) input.payload();
            yield "email:" + e.to() + ":" + e.text();
        }
        case "SMS" -> {
            Sms s = (Sms) input.payload();
            yield "sms:" + s.phone() + ":" + s.text();
        }
        case "PUSH" -> {
            Push p = (Push) input.payload();
            yield "push:" + p.device() + ":" + p.text();
        }
        default -> "invalid";
    };
}
```

Đây vẫn là **thiết kế legacy** vì phân nhánh dựa vào tag, rồi cast payload. Để hai bản chạy trong **cùng chương trình Java 21**, phương thức trên được viết bằng cú pháp `switch expression` hiện đại (có `yield` trong block); ý tưởng `switch tag + cast` cũng tồn tại trong code Java cũ dùng `case: ... break;`.

Điểm yếu không nằm ở dấu `->` hay `yield`, mà ở **ép kiểu dựa trên lời khẳng định chưa được kiểm tra của tag**. Ví dụ `new LegacyEnvelope("EMAIL", new Sms("0900", "Code"))` vượt qua nhánh tag rồi thất bại tại cast sang `Email`.

## 5. Bước chuyển tiếp: xác thực tag và payload ở ranh giới

```java
static Notice adapt(LegacyEnvelope input) {
    if (input == null || input.tag() == null) return null;

    return switch (input.tag()) {
        case "EMAIL" -> input.payload() instanceof Email e ? e : null;
        case "SMS" -> input.payload() instanceof Sms s ? s : null;
        case "PUSH" -> input.payload() instanceof Push p ? p : null;
        default -> null;
    };
}
```

Adapter chỉ tạo một `Notice` khi **cả tag và kiểu thực tế đều nhất quán**:

- `"EMAIL"` phải đi kèm một `Email`; `"SMS"` đi cùng `Sms`; `"PUSH"` đi cùng `Push`.
- `instanceof Email e` vừa kiểm tra kiểu runtime vừa ràng buộc biến `e`; không cần cast `(Email) ...`.
- `payload == null` hoặc tag và payload không khớp → `instanceof` trả `false` và adapter trả `null`.
- Tag lạ cũng được đưa về `null`, theo chính sách đơn giản của ví dụ.

**Giới hạn quan trọng:** dùng `null` làm “không hợp lệ” là **quy ước minh họa**, làm mất thông tin lý do (tag lạ, sai payload, thiếu tag, v.v.). Trong ứng dụng thật nên chọn kết quả có thông tin lỗi (`Result`, một sealed outcome type, ngoại lệ có mã, v.v.) để có thể log, kiểm toán hoặc trả HTTP status chính xác. Adapter vẫn cần validation dữ liệu ngoài, kể cả khi đã kiểm tra subtype.

Ngoài ra, nếu dữ liệu đầu vào là JSON/map chưa được biến thành đối tượng `Email`, `Sms`, `Push`, adapter sẽ phải **parse và xây dựng** đối tượng tương ứng. `instanceof` không thể kiểm tra “đây là Email” khi payload vẫn chỉ là chuỗi JSON thô.

## 6. Cách mới: switch trên subtype thực tế bằng record patterns

Sau adapter, nghiệp vụ làm việc với `Notice`:

```java
static String modern(Notice notice) {
    return switch (notice) {
        case null -> "invalid";
        case Email(var to, var text) -> "email:" + to + ":" + text;
        case Sms(var phone, var text) -> "sms:" + phone + ":" + text;
        case Push(var device, var text) -> "push:" + device + ":" + text;
    };
}
```

Cách đọc `case Email(var to, var text)`:

1. Kiểm tra selector có phải đối tượng `Email` khác `null` hay không.
2. Tách hai component record **theo đúng thứ tự khai báo**, gán cho `to` và `text`.
3. Thực thi biểu thức sau `->`, lấy kết quả làm giá trị của `switch expression`.

Ba nhánh `Email`/`Sms`/`Push` bao phủ các subtype được phép của sealed interface `Notice`. Có `case null` để xử lý giá trị không có đối tượng. **Không cần `default`** trong mô hình này; khi thêm một subtype permitted mới mà quên bổ sung case, compiler có cơ hội báo `switch expression` không còn exhaustive. Nếu viết `default` cho mọi thứ, lợi ích cảnh báo thiếu nhánh có thể bị che mất.

**Không nhầm deconstruction với mapping:** Record pattern giúp lấy component và kiểm tra cấu trúc; phép nối chuỗi tạo kết quả là logic nghiệp vụ. Deconstruction không tự chuyển đổi sang DTO mới, không validate địa chỉ email/số điện thoại, và cũng không làm sâu bản sao (*deep copy*) của các tham chiếu mutable bên trong record.

**`null` cần phân biệt hai tầng:** `case null` xử lý **selector `notice` bằng `null`**. Nếu một record `Email` có `to == null`, `case Email(var to, var text)` vẫn có thể khớp và biến `to` là `null`. Phải thêm guard hoặc validation riêng nếu trường đó bắt buộc không được null.

## 7. Ví dụ hoàn chỉnh có thể biên dịch và chạy

Tạo file **`TypeTagRefactorDemo.java`**:

```java
public class TypeTagRefactorDemo {
    record LegacyEnvelope(String tag, Object payload) {}

    sealed interface Notice permits Email, Sms, Push {}
    record Email(String to, String text) implements Notice {}
    record Sms(String phone, String text) implements Notice {}
    record Push(String device, String text) implements Notice {}

    // Cách cũ: tin vào tag rồi ép kiểu payload.
    static String legacy(LegacyEnvelope input) {
        if (input == null || input.tag() == null) return "invalid";
        return switch (input.tag()) {
            case "EMAIL" -> {
                Email e = (Email) input.payload();
                yield "email:" + e.to() + ":" + e.text();
            }
            case "SMS" -> {
                Sms s = (Sms) input.payload();
                yield "sms:" + s.phone() + ":" + s.text();
            }
            case "PUSH" -> {
                Push p = (Push) input.payload();
                yield "push:" + p.device() + ":" + p.text();
            }
            default -> "invalid";
        };
    }

    // Ranh giới chuyển đổi: kiểm tra cả tag lẫn kiểu payload.
    static Notice adapt(LegacyEnvelope input) {
        if (input == null || input.tag() == null) return null;
        return switch (input.tag()) {
            case "EMAIL" -> input.payload() instanceof Email e ? e : null;
            case "SMS" -> input.payload() instanceof Sms s ? s : null;
            case "PUSH" -> input.payload() instanceof Push p ? p : null;
            default -> null;
        };
    }

    // Cách mới: switch trực tiếp trên subtype thực tế.
    static String modern(Notice notice) {
        return switch (notice) {
            case null -> "invalid";
            case Email(var to, var text) -> "email:" + to + ":" + text;
            case Sms(var phone, var text) -> "sms:" + phone + ":" + text;
            case Push(var device, var text) -> "push:" + device + ":" + text;
        };
    }

    static void verify(String label, LegacyEnvelope input) {
        String oldValue = legacy(input);
        String newValue = modern(adapt(input));
        if (!oldValue.equals(newValue)) {
            throw new AssertionError(
                    label + ": " + oldValue + " != " + newValue);
        }
        System.out.println(label + " -> " + newValue);
    }

    public static void main(String[] args) {
        verify("email", new LegacyEnvelope("EMAIL",
                new Email("a@example.com", "Hello")));
        verify("sms", new LegacyEnvelope("SMS",
                new Sms("0900", "Code")));
        verify("push", new LegacyEnvelope("PUSH",
                new Push("device-1", "Alert")));

        System.out.println("null -> " + modern(adapt(null)));
        System.out.println("unknown-tag -> " + modern(adapt(
                new LegacyEnvelope("FAX", new Email("a@example.com", "Hi")))));

        LegacyEnvelope mismatch = new LegacyEnvelope("EMAIL",
                new Sms("0900", "Code"));
        System.out.println("tag-mismatch -> " + modern(adapt(mismatch)));

        try {
            legacy(mismatch);
        } catch (ClassCastException ex) {
            System.out.println("legacy mismatch -> ClassCastException");
        }
    }
}
```

Lệnh chạy với JDK 21 trở lên:

```bash
javac --release 21 TypeTagRefactorDemo.java
java TypeTagRefactorDemo
```

**Stdout chính xác:**

```text
email -> email:a@example.com:Hello
sms -> sms:0900:Code
push -> push:device-1:Alert
null -> invalid
unknown-tag -> invalid
tag-mismatch -> invalid
legacy mismatch -> ClassCastException
```

Chương trình đã được chạy và đối chiếu đầu ra bằng JDK 24 với các cú pháp có từ Java 21. `verify` kiểm tra **ba trường hợp hợp lệ** có kết quả cũ/mới giống nhau; nếu khác, chương trình ném `AssertionError`. Các dòng sau cố tình kiểm thử tình huống bất thường.

### Phân tích các ca kiểm thử

| Đầu vào | `legacy` | `adapt` + `modern` | Kết luận |
| --- | --- | --- | --- |
| `"EMAIL"` + `Email` | Trả chuỗi email | Trả cùng chuỗi email | Giữ nguyên hành vi |
| `"SMS"` + `Sms` | Trả chuỗi SMS | Trả cùng chuỗi SMS | Giữ nguyên hành vi |
| `"PUSH"` + `Push` | Trả chuỗi push | Trả cùng chuỗi push | Giữ nguyên hành vi |
| `null` envelope | `"invalid"` nhờ guard | `adapt` trả null, `case null` trả `"invalid"` | Giữ nguyên hành vi trong ví dụ |
| `"FAX"` (tag không biết) | `default` trả `"invalid"` | Adapter trả null rồi `"invalid"` | Giữ nguyên hành vi trong ví dụ |
| `"EMAIL"` + `Sms` (sai cặp) | Ném `ClassCastException` | Adapter từ chối, trả `"invalid"` | **Thay đổi có chủ đích**; cần được duyệt trong migration |

Một ca biên khác đáng kiểm tra trong dự án: tag `"EMAIL"` nhưng `payload == null`. Cast tham chiếu từ null không tự ném lỗi, nhưng `e.to()` sẽ ném `NullPointerException` ở code legacy; adapter mới trả null và xử lý theo chính sách `"invalid"`. Khi cần tương thích ngược tuyệt đối, phải **quyết định rõ** có giữ hành vi ném lỗi, đổi sang lỗi nghiệp vụ hay trả kết quả, và bổ sung kiểm thử tương ứng.

## 8. So sánh hai thiết kế và trade-off

| Tiêu chí | Switch trên type tag + cast | Switch trên subtype/pattern |
| --- | --- | --- |
| Selector | Chuỗi/enum tag | Đối tượng có kiểu thực tế, như `Notice` |
| Kiểu dữ liệu | Tag và payload có thể bất nhất | Subtype xác định biến thể nội bộ |
| Cast | Thường phải cast trong mỗi case | Type/record pattern kiểm tra trước khi ràng buộc biến |
| Sai tag/payload | Có thể ném `ClassCastException`, `NullPointerException` | Adapter có thể phát hiện sớm; `switch` nghiệp vụ xử lý dữ liệu đã chuẩn hóa |
| Compiler kiểm tra thiếu case | Với `String tag` không biết trước mọi giá trị | Với sealed hierarchy và switch expression, có thể kiểm tra exhaustiveness |
| Thêm subtype mới | Tự đồng bộ tag, cast, case và chỗ tạo payload | Sửa hierarchy và case; compiler hỗ trợ tìm nơi thiếu bao phủ |
| Input từ JSON/protocol | Thuận tiện để đọc tag thô | Vẫn cần parser/adapter nhận dạng subtype |
| Guard nghiệp vụ | Thường đặt `if` trong case | Có `when` cho guarded pattern hoặc kiểm tra trong block |
| Record component | Gọi accessor sau cast | Record pattern tách component trực tiếp |
| Hiệu năng | Phụ thuộc switch/cast/logic thực tế | Không có bảo đảm luôn nhanh hơn; đo benchmark nếu quan trọng |
| Tương thích phiên bản | Có thể viết trên Java cũ | Pattern switch/record patterns trong ví dụ cần Java 21+ |

### Khi nào không nên chuyển ngay?

- Input vẫn là dữ liệu thô của giao thức; chưa có model nội bộ ổn định.
- Các hệ thống khác tiêu thụ type tag như một phần của schema công khai; đổi schema có thể phá tương thích.
- Dự án còn phải biên dịch với Java 8/11/17 và không thể chuyển toolchain sang 21.
- Domain có các loại mở rộng bởi plugin bên ngoài, không phù hợp với một `sealed` hierarchy đóng. Vẫn có thể dùng `instanceof` và nhánh `default` trên hierarchy mở, hoặc polymorphism, tùy nhu cầu.
- Logic phụ thuộc vào quy tắc riêng của mỗi loại và nên nằm trong phương thức đa hình của subtype, thay vì một `switch` tập trung quá lớn.

Mục đích là làm rõ trách nhiệm và tăng kiểm tra kiểu, **không phải ép mọi `switch` đều trở thành pattern matching**.

## 9. Cách refactor an toàn theo từng bước

1. **Liệt kê type tag và nơi dùng:** xác định giá trị tag hợp lệ, mọi kiểu payload tương ứng, nhánh default, cách xử lý null, hành vi khi tag/payload sai và các side effect.
2. **Đóng băng hành vi cũ bằng test:** tối thiểu mỗi tag hợp lệ, tag không biết, thiếu tag, null envelope, null payload và tag/payload không nhất quán. Ghi rõ case nào cần **giữ nguyên** và case nào được **cố ý thay đổi**.
3. **Định nghĩa model nội bộ có kiểu:** tạo interface/class đại diện biến thể; cân nhắc `sealed interface` và `record` khi không cần khả năng mở rộng tùy ý. Không xóa type tag tại boundary khi contract bên ngoài vẫn yêu cầu.
4. **Viết adapter ở boundary:** kiểm tra `tag` và dữ liệu; parser hoặc deserializer chuyển giá trị đầu vào sang subtype nội bộ. Chỗ này giữ trách nhiệm báo lỗi rõ ràng, log, bảo vệ dữ liệu không tin cậy.
5. **Chuyển xử lý nghiệp vụ:** thay `switch(tag)` trong core bằng `switch(typedValue)` với type/record patterns; loại bỏ cast trong các nhánh đã có kiểu bảo đảm.
6. **Kiểm tra tính bao phủ và thứ tự pattern:** với sealed hierarchy, ưu tiên switch expression exhaustive và tránh `default` thừa. Nếu có guarded case, đặt case cụ thể trước case rộng để tránh case bị *dominated*.
7. **Chạy test đối chiếu và rollout:** xác minh kết quả hợp lệ giữ nguyên, các tình huống lỗi đổi theo chính sách đã thống nhất, không thay đổi định dạng/wire schema ngoài dự kiến. Khi có sự kiện thực tế, theo dõi lỗi parse/mismatch ở adapter.

**Mẹo migration:** Nếu không thể đổi model ngay, bước trung gian đơn giản là:

```java
// Đoạn minh họa đặt trong phương thức nhận Object payload.
if (payload instanceof Email email) {
    System.out.println(email.to());
} else if (payload instanceof Sms sms) {
    System.out.println(sms.phone());
} else if (payload instanceof Push push) {
    System.out.println(push.device());
} else {
    System.out.println("unsupported");
}
```

Cách này đã loại được cast dựa trên tag, và có thể dùng trên Java 16+. Tuy nhiên, nó phân loại theo **kiểu runtime thực tế**, nên sẽ thay đổi cách xử lý trường hợp tag sai. Hãy kiểm thử và chỉ dùng khi đó là hợp đồng mong muốn. Đây là đoạn minh họa không độc lập; các type phải được định nghĩa ở nơi sử dụng.

## 10. Guarded patterns và phạm vi biến

Nếu muốn kiểm tra thêm điều kiện nghiệp vụ, Java 21 hỗ trợ `when` trong nhánh pattern. Ví dụ bên trong một `switch expression` trên `Notice notice` đã khai báo:

```java
String result = switch (notice) {
    case null -> "invalid";
    case Email(var to, var text) when to == null || to.isBlank() ->
            "invalid-email";
    case Email(var to, var text) -> "email:" + to + ":" + text;
    case Sms(var phone, var text) -> "sms:" + phone + ":" + text;
    case Push(var device, var text) -> "push:" + device + ":" + text;
};
```

Phần `when` chỉ được đánh giá **sau khi record pattern đã khớp**. Biến `to` và `text` có phạm vi theo luồng (*flow scoping*) trong guard và trong nhánh của case tương ứng. Đặt nhánh `Email` có guard **trước** nhánh `Email` không guard; nếu đặt nhánh tổng quát trước, nhánh đặc biệt bị che và compiler có thể báo lỗi dominance.

Biểu thức `to == null || to.isBlank()` an toàn vì `||` đánh giá ngắn mạch; khi `to == null` đúng, Java **không gọi** `to.isBlank()`. Điều này cần làm rõ bởi record pattern không tự xác nhận component tham chiếu khác null.

Với kiểu con không phải record, dùng **type pattern**: `case SomeClass s -> ...`. Không thể viết `SomeClass(var x)` chỉ để deconstruct một class thường; dạng `Type(...)` dành cho record.

## 11. Những lỗi dễ xảy ra trong quá trình chuyển đổi

| Lỗi | Hậu quả / hướng xử lý |
| --- | --- |
| Giữ nguyên `switch(tag)` nhưng thay nhãn bằng `case Email(...)` | Selector vẫn là String nên không match được record. Chuyển selector sang object subtype hoặc dùng adapter. |
| Chỉ bỏ cast nhưng vẫn dùng tag không kiểm tra | Tag và payload có thể bất nhất; logic vẫn sai. Kiểm tra cặp tag-payload tại boundary. |
| Viết `default -> "unknown"` tùy tiện trong sealed switch | Có thể che cảnh báo thiếu subtype mới. Chỉ thêm default khi thật sự là một phần contract. |
| Tin rằng `case null` cũng kiểm tra các component null | `case null` chỉ xử lý selector; validate trường bắt bằng `var` riêng. |
| Viết `Email(var text, var to)` mà hai component đều là String | Có thể biên dịch nhưng đảo ý nghĩa theo thứ tự component. Luôn đối chiếu khai báo record. |
| Đặt `case Notice n` trước `case Email(...)` | Case rộng có thể làm case cụ thể bị dominated. Đặt case cụ thể trước. |
| Đổi lỗi `ClassCastException` thành `"invalid"` mà không thông báo | Thay đổi hành vi; cần test, logging, thống nhất contract API. |
| Giả định `record` có deep immutability | Record có component final, nhưng component có thể tham chiếu dữ liệu mutable; không tự deep-copy. |
| Coi type tag từ nguồn ngoài như dữ liệu đáng tin | Phải parse, validate, kiểm soát null và lỗi cấu trúc ở ranh giới dữ liệu. |

## 12. Bài tập tự luyện

Cho mô hình cũ:

```java
record OldCommand(String type, Object payload) {}
record Create(long id) {}
record Delete(long id) {}
```

Một hàm cũ dùng `switch(command.type())`; nhánh `"CREATE"` cast payload về `Create`, nhánh `"DELETE"` cast về `Delete`. Yêu cầu:

1. Định nghĩa `sealed interface Command permits CreateCommand, DeleteCommand` và hai record tương ứng; không dùng tag bên trong model mới.
2. Viết adapter từ `OldCommand` sang `Command`, dùng `instanceof` kiểm tra payload thực tế (hoặc chuyển đổi từ DTO ngoài sang các record mới).
3. Dùng `switch (command)` với record patterns để trả về `"create:<id>"` hoặc `"delete:<id>"`.
4. Viết test cho tag `"CREATE"` + payload `Delete`, null input và tag không hỗ trợ. Quyết định rõ nên trả về kết quả lỗi hay ném exception ở adapter.
5. Thử thêm một subtype `UpdateCommand` vào `permits` mà chưa bổ sung case; quan sát phản hồi biên dịch của `switch expression` exhaustive.

**Hướng giải:** dùng các kiểu nội bộ như `record CreateCommand(long id) implements Command {}`; nhánh `case CreateCommand(var id) -> "create:" + id;`. Giữ việc đọc type tag và kiểm tra payload trong adapter. Đừng chuyển đối tượng `OldCommand` trực tiếp thành subtype chỉ dựa vào chuỗi `"CREATE"` mà không xác thực dữ liệu.

## 13. Tổng kết và tài liệu

**Nguyên tắc:** Đừng dùng một chuỗi `type` để biện minh cho cast không kiểm tra trong phần xử lý nghiệp vụ. Giữ tag tại ranh giới khi cần, kiểm tra và chuẩn hóa dữ liệu, rồi sử dụng type/record patterns trên kiểu nội bộ. Sealed hierarchy + switch exhaustive làm mô hình rõ ràng hơn và có thể giúp phát hiện thiếu nhánh khi phát triển hệ thống. Hãy đánh giá tính tương đương bằng test, đặc biệt ở các trường hợp legacy vốn gây exception.

Tài liệu chính thức:
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
