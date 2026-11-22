# instanceof pattern với target null trong Java

## 1. Khái niệm và quy tắc quan trọng nhất

Trong biểu thức `target instanceof String text`, `target` là **toán hạng bên trái** — giá trị được kiểm tra; `String text` là **type pattern** — mẫu thử kiểu và đặt tên biến mẫu nếu thành công.

“Target null” ở đây nghĩa là **biểu thức bên trái cho ra tham chiếu `null` khi chạy**. Đây không phải một đối tượng “có kiểu null”: `null` không tham chiếu tới một instance nào.

**Quy tắc của Java 17 và Java 21:** nếu giá trị của toán hạng bên trái là `null`, biểu thức `instanceof` trả về **`false`**. Quy tắc này áp dụng cho cả `instanceof` kiểm tra kiểu truyền thống lẫn `instanceof` với pattern. Không có biến mẫu nào được khởi tạo.

~~~java
Object target = null;

System.out.println(target instanceof String text); // false
System.out.println(target instanceof Object obj);   // false
~~~

Ngay cả mẫu `Object obj` cũng không khớp, vì khai báo biến `target` kiểu `Object` chỉ cho biết **kiểu tĩnh của biến**, không chứng minh biến đang trỏ đến một đối tượng tồn tại.

## 2. Hai dạng instanceof và hai giai đoạn kiểm tra

Hai dạng cú pháp:

~~~java
target instanceof String          // Type comparison truyền thống
target instanceof String text     // Pattern match, có biến mẫu text
~~~

Với target `null`, cả hai đều trả `false`. Với target trỏ tới một `String` thật sự, cả hai đều trả `true`; dạng pattern còn khởi tạo biến `text` để dùng tại vị trí có phạm vi hợp lệ.

| Giá trị thực của target | `instanceof String` | `instanceof String text` |
| --- | --- | --- |
| `null` | false | false, không khởi tạo `text` |
| `"Java"` | true | true, `text` là `"Java"` |
| `Integer.valueOf(7)` | false | false, không khởi tạo `text` |

Cần phân biệt:

1. **Lúc biên dịch:** kiểu tĩnh của biểu thức bên trái phải tương thích với việc kiểm tra pattern bên phải (*pattern applicability*). Đầu vào có thể bằng null không làm cho pattern vốn không tương thích trở thành hợp lệ.
2. **Lúc chạy:** Java đánh giá biểu thức bên trái. Nếu kết quả là tham chiếu null, `instanceof` trả false ngay. Nếu khác null, Java thử khớp giá trị với kiểu/pattern; khi khớp mới gán biến mẫu.

Ví dụ `Object value = null; value instanceof String s` hợp lệ khi biên dịch và trả false lúc chạy. Ngược lại, `String value = null; value instanceof Integer n` vẫn không hợp lệ vì hai kiểu lớp không tương thích; giá trị null không “bỏ qua” kiểm tra kiểu tĩnh.

Với literal null, biểu thức sau cũng trả false trong Java 17/21:

~~~java
System.out.println(null instanceof String s); // false
~~~

Nhưng `value instanceof null` là cú pháp sai: `null` không phải một type pattern hay reference type để đặt sau toán tử.

## 3. Chương trình độc lập: null luôn không khớp type pattern

Lưu thành tệp **`NullInstanceofDemo.java`**, chạy với JDK 17 trở lên:

~~~java
import java.util.List;

public class NullInstanceofDemo {

    static String describe(Object value) {
        if (value instanceof String s) {
            return "String length=" + s.length();
        }
        if (value instanceof Integer n) {
            return "Integer x2=" + (n * 2);
        }
        return value == null ? "NULL" : "OTHER";
    }

    static String nonBlank(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "TEXT=" + s.strip();
        }
        return "NO_TEXT";
    }

    static String requireText(Object value) {
        if (!(value instanceof String s)) {
            return value == null ? "MISSING" : "WRONG_TYPE";
        }
        return "VALID=" + s;
    }

    public static void main(String[] args) {
        Object value = null;

        System.out.println("string=" + (value instanceof String s));
        System.out.println("object=" + (value instanceof Object any));
        System.out.println("list=" + (value instanceof List<?> items));

        System.out.println(describe(null));
        System.out.println(describe("Java"));
        System.out.println(describe(7));
        System.out.println(describe(new Object()));

        System.out.println(nonBlank(null));
        System.out.println(nonBlank("  Java  "));
        System.out.println(nonBlank("   "));

        System.out.println(requireText(null));
        System.out.println(requireText("OK"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac NullInstanceofDemo.java
java NullInstanceofDemo
~~~

Đầu ra:

~~~text
string=false
object=false
list=false
NULL
String length=4
Integer x2=14
OTHER
NO_TEXT
TEXT=Java
NO_TEXT
MISSING
VALID=OK
~~~

**Vì sao?**

- `value` ở đầu chương trình chứa null, nên các phép thử `String`, `Object` và `List<?>` đều false. Generic wildcard không biến null thành danh sách.
- `describe(null)` đi qua cả hai nhánh `instanceof` và chỉ đến cuối mới phân biệt null bằng `== null`.
- `describe("Java")` khớp `String s` và truy cập `s.length()` an toàn.
- `nonBlank(null)` trả `NO_TEXT`; vế phải của `&&` không chạy khi pattern thất bại.
- `requireText(null)` trả `MISSING` nhờ kiểm tra null riêng trong nhánh không khớp; `requireText("OK")` dùng biến `s` ở đường đi đã khớp.

Đây là ví dụ về **hành vi được quy định bởi ngôn ngữ**, không phải phụ thuộc HotSpot, thư viện hay phiên bản JVM cụ thể.

## 4. Kết quả false không cho biết nguyên nhân

Một phép thử `instanceof` false có ít nhất hai nguyên nhân thường gặp:

~~~java
Object first = null;
Object second = Integer.valueOf(100);

boolean a = first instanceof String s1;  // false vì null
boolean b = second instanceof String s2; // false vì khác kiểu
~~~

Không thể nhìn vào giá trị false mà suy ra target là null. Nếu nghiệp vụ cần phân biệt “chưa có dữ liệu” với “có dữ liệu nhưng sai kiểu”, hãy kiểm tra rõ:

~~~java
static String classify(Object value) {
    if (value == null) {
        return "Thiếu dữ liệu";
    }
    if (value instanceof String text) {
        return "Chuỗi: " + text;
    }
    return "Không phải chuỗi";
}
~~~

Đây là **phương thức minh họa** để đặt trong một class Java 17+. Khi gọi `classify(null)` kết quả là `"Thiếu dữ liệu"`; khi gọi `classify(7)` kết quả là `"Không phải chuỗi"`.

Nếu hai trường hợp có chung cách xử lý, có thể chỉ cần:

~~~java
static int lengthIfString(Object value) {
    return value instanceof String text ? text.length() : 0;
}
~~~

Hàm này trả `0` cho cả null và sai kiểu. Hãy chọn theo **contract của API**, không nhất thiết lúc nào cũng tách null thành một nhánh riêng.

## 5. Biến mẫu không được gán giá trị null khi instanceof false

Mẫu `String text` khai báo một **pattern variable**. Biến này được khởi tạo **chỉ khi phép thử trả true**. Khi target null, Java không tạo ra một `text` mang giá trị mặc định null để dùng trong nhánh khác.

Mã cố ý sai:

~~~java
static void invalid(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println(text.length()); // COMPILE ERROR
    }
}
~~~

Đây là **mảnh mã minh họa lỗi**, không phải chương trình chạy độc lập. Dù nhánh `else` có thể chạy với null, biến `text` không ở trong phạm vi (*scope*) của nhánh đó. Java dùng cơ chế **flow scoping** để xác định vị trí nào chắc chắn đã khớp pattern.

Đảo điều kiện thì biến mẫu chuyển sang nhánh `else`:

~~~java
static String render(Object value) {
    if (!(value instanceof String text)) {
        return "null hoặc không phải String";
    } else {
        return "Chuỗi: " + text;
    }
}
~~~

Ở nhánh `else`, biểu thức phủ định false đồng nghĩa `value instanceof String text` true; do đó `text` đã được gán và không thể là null do chính phép khớp này. Nếu `value == null`, nhánh `if` chạy.

Một *guard clause* cũng giữ được phạm vi:

~~~java
static int safeLength(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // Hợp lệ: đường đi tiếp tục đã khớp
}
~~~

Khi target null, hàm trả 0 trước khi dùng `text`.

## 6. Đặt điều kiện bổ sung bằng && và ||

Với `&&` ngắn mạch, biến mẫu ở vế phải chỉ được sử dụng sau khi phép `instanceof` đã true:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Nếu `value == null`, vế trái false và Java **không gọi `text.isBlank()`**. Nếu điều kiện tổng thể true, biến `text` chắc chắn tồn tại và chứa String thực sự.

Cũng có thể viết điều kiện phủ định bằng `||`:

~~~java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("Không có chuỗi hợp lệ");
} else {
    System.out.println(text.strip());
}
~~~

Ở đây vế phải của `||` chỉ chạy khi vế trái false, tức là khi mẫu String đã khớp. Khi vào `else`, cả hai vế đều false; `text` chắc chắn đã khớp và không blank.

Ngược lại, đoạn sau **không biên dịch**:

~~~java
// CỐ Ý SAI: text chưa chắc tồn tại ở vế phải của ||
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
~~~

Vì vế phải `||` có thể cần chạy khi `value instanceof String text` false, biến `text` không ở scope tại đó. Việc target có thể null khiến tình huống không khớp càng rõ ràng, nhưng đây trước hết là quy tắc về luồng điều khiển của Java.

Không cần viết `value != null && value instanceof String text` chỉ để bảo vệ `text` khỏi null. Nếu không cần phân biệt null, riêng `value instanceof String text` đã an toàn.

## 7. Vì sao instanceof an toàn nhưng biểu thức chứa nó vẫn có thể ném NPE?

Câu khẳng định chính xác là:

> **Nếu việc đánh giá toán hạng trái đã kết thúc và cho ra tham chiếu null, `instanceof` trả false.**

Java vẫn phải **tính toán toán hạng trái trước**. Nếu quá trình đó ném ngoại lệ, toán tử `instanceof` chưa được thực hiện.

Mã an toàn:

~~~java
Object value = null;
boolean matched = value instanceof String text; // false
~~~

Mã có thể ném NPE:

~~~java
Object[] values = null;
boolean matched = values[0] instanceof String text;
~~~

Trong trường hợp thứ hai, phép truy cập `values[0]` gây `NullPointerException` do `values` bằng null; lỗi phát sinh **trước** phép kiểm tra kiểu. Tương tự, gọi một phương thức trên receiver null để tạo giá trị bên trái có thể ném NPE trước khi tới `instanceof`.

Đừng vì thấy một đoạn mã có `instanceof` mà kết luận mọi biểu thức trong đoạn đó đều null-safe. `instanceof` chỉ xử lý **giá trị nó nhận được**, không tự bảo vệ toàn bộ phép tính tạo ra giá trị ấy.

## 8. Null, ép kiểu tường minh và gọi phương thức

So sánh các thao tác khi `Object value = null`:

| Thao tác | Hành vi |
| --- | --- |
| `value instanceof String s` | false; không khởi tạo `s` |
| `value instanceof String` | false |
| `value instanceof Object obj` | false |
| `value == null` | true |
| `String s = (String) value` | Cast hợp lệ, `s` vẫn null |
| `((String) value).length()` | Ném `NullPointerException` |
| `Objects.requireNonNull(value)` | Chủ động ném `NullPointerException` |

Một phép cast thành công không có nghĩa target là một đối tượng. Cast null sang một kiểu tham chiếu hợp lệ vẫn trả về null:

~~~java
Object value = null;
String casted = (String) value; // casted == null
boolean matched = value instanceof String text; // false
~~~

`instanceof` cần một **đối tượng thực tế khớp pattern**, còn cast tham chiếu null chỉ giữ nguyên null.

Nếu bạn muốn *bắt buộc* không có null, dùng `Objects.requireNonNull` hoặc điều kiện `if (value == null) throw ...` như một quyết định rõ ràng trong thiết kế API; `instanceof` không tự coi null là lỗi.

## 9. Null với generic, interface, mảng và Object

Không có ngoại lệ dành riêng cho các nhóm kiểu tham chiếu:

~~~java
Object target = null;

boolean a = target instanceof CharSequence cs;
boolean b = target instanceof java.util.List<?> list;
boolean c = target instanceof int[] numbers;
boolean d = target instanceof Runnable task;
boolean e = target instanceof Object obj;
~~~

Đặt các khai báo này trong một phương thức hoặc block Java 17+. Cả năm kết quả đều false.

- **Generic:** `List<?>` có thể dùng để thử một đối tượng có phải List hay không, nhưng không làm null khớp. `List<String>` với nguồn có kiểu tĩnh `Object` thường còn không phải pattern hợp lệ vì cast generic cần kiểm tra *unchecked*.
- **Mảng:** mảng rỗng `new int[0]` là **một đối tượng**, nên khớp `int[]`; tham chiếu `int[] array = null` không trỏ tới mảng, nên không khớp.
- **Interface:** một đối tượng không null có thể triển khai `Runnable`, nhưng null thì không.
- **Object:** kiểu khai báo của biến là `Object` không đồng nghĩa với có một đối tượng. `null instanceof Object` vẫn false.

## 10. Java 21: target null khác với record chứa component null

Khi dùng **record patterns**, cần phân biệt:

- **Target ngoài cùng null:** không có đối tượng record để khớp. `target instanceof Box(var value)` luôn false.
- **Đối tượng record tồn tại nhưng component bên trong null:** record pattern ngoài cùng có thể khớp, và một số component patterns có thể khớp null theo quy tắc riêng.

Ví dụ độc lập dùng **Java 21**, lưu thành `NullRecordDemo.java`:

~~~java
public class NullRecordDemo {
    record Box(Object payload) {}

    static String inspect(Object target) {
        if (target instanceof Box(String text)) {
            return "TEXT:" + text;
        }
        if (target instanceof Box(var payload)) {
            return payload == null
                    ? "BOX_NULL_CONTENT"
                    : "BOX_OTHER_CONTENT";
        }
        return target == null ? "TARGET_NULL" : "NOT_A_BOX";
    }

    static String fromSwitch(Object value) {
        return switch (value) {
            case null -> "SWITCH_NULL";
            case String s -> "SWITCH_STRING=" + s;
            default -> "SWITCH_OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(null));
        System.out.println(inspect(new Box(null)));
        System.out.println(inspect(new Box("Java")));
        System.out.println(inspect(new Box(42)));
        System.out.println(inspect("Java"));

        System.out.println(fromSwitch(null));
        System.out.println(fromSwitch("Java"));
        System.out.println(fromSwitch(42));
    }
}
~~~

Lệnh:

~~~bash
javac NullRecordDemo.java
java NullRecordDemo
~~~

Kết quả:

~~~text
TARGET_NULL
BOX_NULL_CONTENT
TEXT:Java
BOX_OTHER_CONTENT
NOT_A_BOX
SWITCH_NULL
SWITCH_STRING=Java
SWITCH_OTHER
~~~

Giải thích:

1. `inspect(null)`: cả hai `instanceof Box(...)` đều false vì bản thân target null.
2. `inspect(new Box(null))`: Box **tồn tại**. `Box(String text)` không khớp vì component kiểu `Object` đang null không khớp pattern String ở đó. `Box(var payload)` khớp và `payload` có thể là null.
3. `inspect(new Box("Java"))`: component String khớp nhánh đầu.
4. `inspect(new Box(42))`: record Box khớp, nhưng component không phải String, nên sang nhánh `Box(var payload)`.

JLS 21 có quy tắc *null-matching component patterns* đối với quá trình giải cấu trúc record. Một type pattern **unconditional tại kiểu component** có thể nhận null trong trường hợp này. Điều đó **không làm thay đổi quy tắc**: nếu toàn bộ toán hạng trái của `instanceof` là null thì kết quả vẫn false.

**Ranh giới phiên bản:** ví dụ `NullInstanceofDemo` dùng tính năng đã chính thức trong Java 17; `NullRecordDemo` cần Java 21 vì record patterns là tính năng chính thức từ Java 21.

## 11. Java 21 switch có case null: khác instanceof

Hàm `fromSwitch` ở ví dụ trên dùng:

~~~java
return switch (value) {
    case null -> "SWITCH_NULL";
    case String s -> "SWITCH_STRING=" + s;
    default -> "SWITCH_OTHER";
};
~~~

`case null` là nhãn đặc biệt của `switch`, **không phải type pattern của `instanceof`**. Trong Java 21:

| Cấu trúc | Với đầu vào null |
| --- | --- |
| `value instanceof String s` | Trả false |
| `if (value == null)` | Điều kiện true |
| `switch (value)` có `case null` | Thực thi nhánh `case null` |
| `switch (value)` không có `case null` | Ném `NullPointerException`, ngay cả khi có `default` |

Không nên suy luận rằng `default` của `switch` nhận null giống `else` sau chuỗi điều kiện `instanceof`. Nếu muốn xử lý null bằng switch Java 21, cần `case null`; cũng có thể kiểm tra null trước khi switch.

Trong Java 21, `case null, String s -> ...` không hợp lệ vì không thể gộp nhãn null với type pattern như vậy. Có thể dùng `case null, default -> ...` nếu muốn hai trường hợp có chung xử lý.

## 12. Lựa chọn hành vi theo contract của API

**Cách A — Null là dữ liệu thiếu, có fallback:**

~~~java
static String displayName(Object value) {
    if (value == null) {
        return "(chưa có)";
    }
    if (value instanceof String name && !name.isBlank()) {
        return name;
    }
    return "(không hợp lệ)";
}
~~~

**Cách B — Null là lỗi cần phát hiện:**

~~~java
static int requiredStringLength(Object value) {
    java.util.Objects.requireNonNull(value, "value");
    if (value instanceof String text) {
        return text.length();
    }
    throw new IllegalArgumentException("value phải là String");
}
~~~

**Cách C — Chỉ quan tâm tới String:**

~~~java
static int lengthIfString(Object value) {
    return value instanceof String text ? text.length() : 0;
}
~~~

Đây là các **phương thức minh họa**, đặt trong class Java 17+ khi chạy. Cách A phân biệt null với sai kiểu; cách B chủ động báo lỗi; cách C gộp null và sai kiểu thành cùng fallback. Chọn cách phù hợp contract và thông điệp cần truyền cho người gọi.

## 13. Những lỗi và ngộ nhận thường gặp

| Ngộ nhận / lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `null instanceof Object obj` là true | Null không phải instance nào | Kiểm tra null bằng `== null` |
| Biến mẫu `s` có giá trị null nếu pattern false | Pattern variable chỉ được khởi tạo khi khớp | Dùng `s` ở nhánh chắc chắn khớp |
| Dùng `s` trong `else` của `if (v instanceof String s)` | Else có thể ứng với null hoặc khác kiểu | Xử lý `v` hoặc đổi cấu trúc điều kiện |
| `instanceof` bảo vệ mọi phép dereference ở toán hạng trái | Lỗi có thể xảy ra trước lúc thử pattern | Kiểm tra receiver hoặc mảng khi cần |
| `instanceof` false ⇒ target null | Đối tượng khác kiểu cũng false | Tách `== null` nếu cần phân biệt |
| Viết `v instanceof null` | Null không phải type pattern | Dùng `v == null` |
| Trong switch Java 21, `default` sẽ bắt null | Không có `case null` thì selector null gây NPE | Thêm `case null` |
| `new Box(null)` tương đương `null` | Box có thật, chỉ component null | Xét null ngoài cùng và null component riêng |
| `(String) null` thành công ⇒ `null instanceof String s` true | Cast null giữ nguyên null, không tạo instance | Phân biệt cast và so khớp pattern |

## 14. Tự kiểm tra

**Câu 1.** Với `Object o = null;`, ba phép `o instanceof String s`, `o instanceof Number n`, `o instanceof Object x` cho kết quả nào?

**Đáp án:** Cả ba đều false; không có biến mẫu nào được khởi tạo.

**Câu 2.** Vì sao `if (o instanceof String s && s.length() > 3)` không ném NPE khi `o == null`?

**Đáp án:** Phép `instanceof` trả false và `&&` bỏ qua vế phải. `s.length()` chỉ được đánh giá sau khi mẫu khớp.

**Câu 3.** `String s = (String) null;` có hợp lệ không? Có khiến `null instanceof String t` thành true không?

**Đáp án:** Cast hợp lệ nhưng `s` vẫn null; `instanceof` vẫn false.

**Câu 4.** `target = null` và `target = new Box(null)` có cho cùng kết quả với `target instanceof Box(var p)` trong Java 21 không?

**Đáp án:** Không. Target ngoài cùng null làm `instanceof` false; một Box thực sự chứa component null có thể khớp pattern và gán `p = null`.

**Câu 5.** `switch` Java 21 có `default` nhưng không có `case null` sẽ xử lý selector null ra sao?

**Đáp án:** Ném `NullPointerException`; `default` không bắt null.

## 15. Tài liệu chuẩn

- [Java Language Specification 21, mục 15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): điều kiện biên dịch, hành vi khi toán hạng trái null, khi nào khởi tạo pattern variables.
- [JLS 21, mục 14.30.2 — Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2): matching của type/record patterns và quy tắc null-matching component patterns.
- [JLS 21, mục 6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): flow scoping của biến mẫu.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): `case null` và hành vi của selector null.

**Kết luận:** `instanceof` với **target ngoài cùng là null luôn trả false**; không có biến mẫu nào được khởi tạo. Muốn phân biệt null với sai kiểu thì kiểm tra `== null`; muốn xử lý null trong `switch` Java 21 thì dùng `case null`. Chỉ khi một record thật sự tồn tại mới cần xét thêm các quy tắc null của component patterns.
