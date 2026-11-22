# `null` có match type pattern hay không?

**Chủ đề:** Java Core Pattern Matching → Null và tương thích kiểu  
**Mốc phiên bản:** Java 17+ cho `instanceof` type pattern; Java 21+ cho pattern matching trong `switch` và record pattern.

## 1. Câu trả lời chính xác

**Khi dùng `instanceof` với type pattern, `null` luôn cho kết quả `false`.** Chẳng hạn, nếu `Object value = null`, biểu thức `value instanceof String text` không khớp, biến `text` không được gắn giá trị và nhánh `if` tương ứng không chạy.

Nhưng không nên mở rộng thành câu “`null` không bao giờ khớp bất kỳ type pattern nào” cho toàn bộ Java 21: **một type pattern lồng trực tiếp trong record pattern có thể là *null-matching*** nếu pattern đó là vô điều kiện (*unconditional*) đối với kiểu của record component. Khi ấy biến pattern lồng có thể nhận giá trị `null`. Đây là trường hợp riêng được quy định trong Java Language Specification §14.30.1–14.30.2.

| Tình huống | `null` có được xem là khớp? | Điều cần nhớ |
| --- | --- | --- |
| `value instanceof String s` với `value == null` | **Không** | Trả `false`, không khởi tạo `s` |
| `value instanceof Object o` về mặt ngữ nghĩa với `value == null` | **Không** | `instanceof` không coi `null` là một instance; một số type pattern dư thừa còn bị từ chối lúc biên dịch |
| `switch (value)` có `case String s`, `value == null` | **Không** | Cần xử lý selector `null` riêng bằng `case null` khi cần |
| `record Box(String value)` được khớp bằng `Box(String s)` với **Box khác null** nhưng component `value == null` | **Có, đối với pattern lồng `String s`** | Biến `s` được gắn `null`; cần kiểm tra trước khi gọi phương thức |

Hai điểm khác nhau phải được tách rõ: **giá trị được kiểm tra ở cấp ngoài** có phải `null` không, và **một component bên trong record** có phải `null` không.

## 2. Vì sao `null instanceof T` là `false`?

`null` biểu thị việc không tham chiếu đến một đối tượng nào; nó không phải một đối tượng `String`, `Integer` hay `Object` có kiểu runtime cụ thể. Phép `instanceof` kiểm tra liệu **giá trị tham chiếu hiện tại** có là một instance của kiểu đích hay không. Vì không có đối tượng nào khi tham chiếu là `null`, kết quả là `false`.

Ví dụ, các câu lệnh sau hợp lệ trên Java 17+:

```java
Object value = null;

System.out.println(value instanceof String);     // false
System.out.println(value instanceof String text); // false
System.out.println(value instanceof Object);     // false
```

Lưu ý: dùng biến có kiểu tĩnh `Object` ở ví dụ để type pattern `String text` là phép kiểm tra có ý nghĩa. Với một biểu thức đã có kiểu tĩnh `String`, cách viết `expr instanceof String s` có thể bị Java từ chối vì kiểm tra pattern là dư thừa theo quy tắc của `instanceof` type pattern; đừng nhầm lỗi biên dịch này với kết quả kiểm tra `null` tại runtime.

**Kiểu khai báo và giá trị thực tế là hai điều khác nhau.** Ví dụ `String name = null;` là một khai báo hợp lệ, nhưng không có đối tượng `String` nào được tham chiếu cho tới khi `name` được gắn một chuỗi thật.

## 3. Ảnh hưởng đến `if`, `else` và flow scoping

Mẫu thực tế thường gặp:

```java
static String explain(Object value) {
    if (value instanceof String text) {
        return "String dài " + text.length();
    }
    if (value == null) {
        return "Không có giá trị";
    }
    return "Không phải String";
}
```

- Với `"Java"`, phép `instanceof` khớp và `text.length()` trả `4`.
- Với `null`, nhánh `String text` bị bỏ qua và nhánh `value == null` chạy.
- Với `42` (được boxing thành `Integer`), không khớp `String`, cũng không phải `null`.

Điều kiện có `&&` tận dụng cơ chế *short-circuit*: chỉ đọc `text` sau khi pattern đã khớp.

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

Nếu `value == null`, vế trái là `false`, nên `text.isBlank()` không được gọi và cũng không có `NullPointerException` từ thao tác này.

Với phép phủ định, kết quả `instanceof` bị đảo nhưng **không tạo ra một đối tượng mới**:

```java
if (!(value instanceof String text)) {
    // Tới đây khi value là null hoặc không phải String.
    return "Không phải String";
}
// Sau guard return, text đã được bảo đảm khớp:
return text.toUpperCase();
```

Đoạn cuối là mã minh họa thuộc một phương thức trả về `String`; để chạy độc lập, xem chương trình đầy đủ ở mục 6. Không được gọi `text.toUpperCase()` trong chính nhánh phủ định: đó là đường đi không khớp pattern.

## 4. Xử lý `null` với pattern matching trong `switch` (Java 21+)

Pattern matching cho `switch` đã chính thức từ Java 21. Với selector `null`, một type pattern cấp ngoài như `case String s` **không nhận `null`**. Thay vào đó, `case null` xử lý giá trị này:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Khác";
    };
}
```

`case null` là **nhãn case cho giá trị null**, không phải một type pattern. Nó giúp mô tả nhánh xử lý `null` tường minh.

**Cẩn thận với `default`:** trong `switch` Java 21, nếu selector là `null` mà không có `case null` (hoặc nhãn kết hợp `case null, default`), `switch` thường ném `NullPointerException` trước khi vào các nhánh thông thường. Việc chỉ thêm `default` không có nghĩa `null` sẽ được xử lý ở đó. Ví dụ `switch (value) { case String s -> ...; default -> ...; }` không tự nhận `null` ở `default`.

Nếu không muốn dùng `case null`, hãy kiểm tra `value == null` trước `switch`. Tránh dùng `case Object obj` như một cách ngầm bao phủ `null`: một selector `null` vẫn cần quy tắc xử lý `null` của `switch`.

## 5. Ngoại lệ quan trọng của Java 21: type pattern lồng trong record

Đặc tả Java 21 định nghĩa một **null-matching type pattern** khi type pattern đứng **trực tiếp** trong danh sách component của record pattern, và type pattern đó là *unconditional* cho kiểu khai báo của component tương ứng. Khi điều kiện này đúng, component `null` **khớp với type pattern lồng** và biến pattern được khởi tạo thành `null`.

Xét hai record:

```java
record TextBox(String value) {}
record WideBox(Object value) {}
```

Với `TextBox`, component có kiểu khai báo `String`. Pattern `String text` là unconditional đối với `String`, vì thế:

```java
new TextBox(null) instanceof TextBox(String text) // true trên Java 21+
```

Ở đây đối tượng **`TextBox` không null**. Chỉ thành phần `value` của nó bằng `null`. Khi record pattern khớp, `text == null` là `true`. Nếu gọi `text.length()` mà không kiểm tra, sẽ phát sinh `NullPointerException`.

Với `WideBox`, component có kiểu khai báo `Object`. Pattern `String text` **không** unconditional cho `Object`, nên:

```java
new WideBox(null) instanceof WideBox(String text) // false trên Java 21+
```

Sự khác nhau nằm ở **kiểu khai báo của record component**. Đặc tả dùng tính chất unconditional của type pattern để xác định có được nhận `null` trong record pattern hay không; không phải cứ thấy cú pháp `String text` là có cùng hành vi ở mọi vị trí.

Đừng nhầm với một record pattern nhận selector `null`:

```java
Object value = null;
boolean result = value instanceof TextBox(String text); // false
```

**Record pattern cấp ngoài không khớp một tham chiếu `null`.** Trường hợp đặc biệt chỉ nói về *type pattern của component bên trong một record thực sự tồn tại*.

## 6. Ví dụ chạy độc lập, đối chiếu cả ba tình huống

Tạo tệp **`NullTypePatternDemo.java`**, dùng JDK 21 hoặc mới hơn:

```java
public class NullTypePatternDemo {
    record TextBox(String value) {}
    record WideBox(Object value) {}

    static String byInstanceof(Object value) {
        if (value instanceof String text) {
            return "STRING:" + text.length();
        }
        return value == null ? "NULL" : "OTHER";
    }

    static String bySwitch(Object value) {
        return switch (value) {
            case null -> "SWITCH_NULL";
            case String text -> "SWITCH_STRING:" + text;
            default -> "SWITCH_OTHER";
        };
    }

    static String byRecord(Object value) {
        return switch (value) {
            case null -> "RECORD_INPUT_NULL";
            case TextBox(String text) ->
                    text == null ? "TEXTBOX_NULL" : "TEXTBOX:" + text;
            case WideBox(String text) -> "WIDEBOX_STRING:" + text;
            case WideBox(var other) -> "WIDEBOX_OTHER:" + other;
            default -> "RECORD_OTHER";
        };
    }

    public static void main(String[] args) {
        Object missing = null;
        System.out.println(missing instanceof String);
        System.out.println(missing instanceof String text);
        System.out.println(missing instanceof Object);

        System.out.println(byInstanceof(null));
        System.out.println(byInstanceof("Java"));
        System.out.println(byInstanceof(42));

        System.out.println(bySwitch(null));
        System.out.println(bySwitch("ok"));
        System.out.println(bySwitch(42));

        System.out.println(byRecord(new TextBox(null)));
        System.out.println(byRecord(new TextBox("ok")));
        System.out.println(byRecord(new WideBox(null)));
        System.out.println(byRecord(new WideBox("ok")));
        System.out.println(byRecord(null));

        System.out.println(new TextBox(null) instanceof TextBox(String s));
        System.out.println(new WideBox(null) instanceof WideBox(String s));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 NullTypePatternDemo.java
java NullTypePatternDemo
```

Kết quả dự kiến:

```text
false
false
false
NULL
STRING:4
OTHER
SWITCH_NULL
SWITCH_STRING:ok
SWITCH_OTHER
TEXTBOX_NULL
TEXTBOX:ok
WIDEBOX_OTHER:null
WIDEBOX_STRING:ok
RECORD_INPUT_NULL
true
false
```

**Phân tích các dòng dễ nhầm:**

1. Ba dòng `false` đầu tiên chứng minh `missing == null` không phải instance của `String` hay `Object`; dùng type pattern trong `instanceof` cũng không làm `null` khớp.
2. `byInstanceof(null)` trả `NULL` do điều kiện `instanceof` thất bại; `"Java"` trả `STRING:4`.
3. `bySwitch(null)` vào `case null` nên trả `SWITCH_NULL`, không vào `case String text` hoặc `default`.
4. `byRecord(new TextBox(null))` khớp `TextBox(String text)`; biến `text` thực sự bằng `null`, nên trả `TEXTBOX_NULL`.
5. `byRecord(new WideBox(null))` **không** khớp `WideBox(String text)` nhưng khớp `WideBox(var other)`, nơi `other` nhận `null`; phép nối chuỗi in thành `WIDEBOX_OTHER:null`.
6. `byRecord(null)` xử lý selector `null` bằng `case null`; nó không thể khớp `TextBox(...)` hay `WideBox(...)`.
7. Hai dòng cuối (`true`, `false`) kiểm tra trực tiếp ngoại lệ null-matching của type pattern lồng trong record: kiểu component là `String` so với `Object`.

Chương trình sử dụng các tính năng đã chính thức trong Java 21, **không cần `--enable-preview`**.

## 7. Bảng quyết định khi xử lý dữ liệu có thể là `null`

| Đầu vào | Dạng kiểm tra | Kết quả hoặc nhánh |
| --- | --- | --- |
| `Object x = null` | `x instanceof String s` | `false` |
| `Object x = "Hi"` | `x instanceof String s` | `true`, `s = "Hi"` |
| `Object x = 5` | `x instanceof String s` | `false` |
| `Object x = null` | `x == null` | `true` |
| `Object x = null` | `switch (x)` có `case null` | Vào `case null` |
| `Object x = null` | `switch (x)` chỉ có `case String s` và `default` | Ném `NullPointerException` |
| `new TextBox(null)` | `instanceof TextBox(String s)` | `true`; `s == null` |
| `new WideBox(null)` | `instanceof WideBox(String s)` | `false` |

**Gợi ý khi thiết kế:** nếu `null` là đầu vào hợp lệ theo nghiệp vụ, mô tả nó thành một nhánh riêng và viết test. Với record pattern lồng, xem xét tính nullable của từng component, kể cả khi record bên ngoài không null.

## 8. Các hiểu lầm và lỗi phổ biến

- **“Kiểu biến là `String` nên `null` phải khớp `String`.”** Sai: kiểu tĩnh của biến không thay đổi việc giá trị runtime là `null`. `instanceof` kiểm tra đối tượng thực tế.
- **“`instanceof` sẽ ném `NullPointerException` khi biến null.”** Sai: bản thân phép `instanceof` trên một tham chiếu `null` trả `false`. Ngoại lệ có thể đến từ việc gọi phương thức trên `null` ở bước khác.
- **“Vào nhánh `else` nghĩa là giá trị null.”** Sai: có thể là kiểu không khớp, ví dụ `Integer` thay vì `String`; nếu cần phân biệt, kiểm tra `value == null`.
- **“Pattern variable có thể dùng ngay cả khi không match.”** Sai: với `instanceof`, biến pattern chỉ có phạm vi khi luồng điều khiển chứng minh đã khớp; không thể dùng ở nhánh thất bại.
- **“`default` của `switch` tự bắt `null`.”** Sai trong tình huống mô tả ở Java 21; dùng `case null` hoặc tiền kiểm tra `null`.
- **“Mọi `String s` pattern đều không nhận `null`.”** Không chính xác khi nói về type pattern lồng trực tiếp trong record pattern và unconditional cho record component tương ứng.
- **“Record chứa null thì cả record cũng null.”** Sai: `new TextBox(null)` là một record object hợp lệ có component null; chỉ `null` đứng ở cấp ngoài mới khiến record pattern không khớp.
- **“Nếu match record pattern thì mọi component chắc chắn khác null.”** Sai: một type pattern lồng null-matching có thể ràng buộc biến bằng `null`, nên phải áp dụng kiểm tra phù hợp trước khi gọi phương thức.

## 9. Bài tập tự luyện

1. Với `Object x = null;`, dự đoán kết quả của `x instanceof String`, `x instanceof Integer i`, `x instanceof Object` và `x == null`, rồi kiểm chứng.
2. Viết hàm nhận `Object` và trả ba kết quả riêng cho `null`, `String` và các kiểu còn lại; dùng `instanceof String s` trong `if` để in độ dài an toàn.
3. Tạo `switch` Java 21 với `case null`, `case String s`, `default`. Thử bỏ `case null` khi truyền `null` và quan sát ngoại lệ; sau đó khôi phục nhánh an toàn.
4. Định nghĩa `record TextBox(String value)` và `record WideBox(Object value)`. Cho component bằng `null`, giải thích tại sao `TextBox(String s)` có thể match còn `WideBox(String s)` không match.
5. Với `new TextBox(null)`, hãy viết nhánh record pattern xử lý an toàn biến `s` trước khi gọi `s.length()`; bổ sung test để không gây `NullPointerException`.

**Tiêu chí đạt:** phân biệt được tham chiếu null cấp ngoài với component null bên trong record, dự đoán đúng kết quả `instanceof`, hiểu vai trò `case null` và giải thích được điều kiện *null-matching* của type pattern lồng theo Java 21.

**Tài liệu chuẩn để tra cứu:**

- [JLS Java SE 21 — `instanceof` operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2).
- [JLS Java SE 21 — kinds of patterns và null-matching (§14.30.1)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.1).
- [JLS Java SE 21 — pattern matching (§14.30.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2).
- [JLS Java SE 21 — chọn nhãn trong `switch` (§14.11.1.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2).
