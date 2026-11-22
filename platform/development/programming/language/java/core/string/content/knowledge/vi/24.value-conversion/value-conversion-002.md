# Phân biệt `String.valueOf(Object)` và `String.valueOf(char[])` khi truyền `null`

Cùng một lời gọi `String.valueOf`, cùng dữ liệu `null`, nhưng **kiểu đối số ở thời điểm biên dịch** quyết định overload nào được gọi. Đây là một bẫy dễ gặp trong Java:

```java
String a = String.valueOf((Object) null); // "null"
String b = String.valueOf((char[]) null); // NullPointerException
String c = String.valueOf(null);          // NullPointerException
```

Trong ba câu lệnh trên, `a` được gán thành công. Hai câu lệnh còn lại biên dịch được nhưng **ném `NullPointerException` ở runtime**. Điều này xuất phát từ *overload resolution* của Java chứ không phải do giá trị `null` thay đổi.

## 1. Hai overload quan trọng của `String.valueOf`

`String` có nhiều phương thức static tên `valueOf` để đổi dữ liệu thành chuỗi. Khi truyền `null`, hai overload nhận kiểu tham chiếu dưới đây là trọng tâm:

```java
public static String valueOf(Object obj);
public static String valueOf(char[] data);
```

Các overload dành cho `boolean`, `char`, `int`, `long`, `float` và `double` nhận **kiểu nguyên thủy**. Giá trị `null` không thể chuyển sang kiểu nguyên thủy để gọi trực tiếp, nên chúng không cạnh tranh khi đối số là literal `null`.

| Overload | Với đối số khác `null` | Với `null` |
| --- | --- | --- |
| `valueOf(Object obj)` | Trả về kết quả `obj.toString()` | Trả về **chuỗi gồm bốn ký tự `"null"`** |
| `valueOf(char[] data)` | Tạo chuỗi gồm nội dung các ký tự của mảng | Ném **`NullPointerException`** |

### `valueOf(Object)` xử lý `null` đặc biệt

Về mặt ý nghĩa, overload `Object` hoạt động tương tự:

```java
static String objectToText(Object obj) {
    return (obj == null) ? "null" : obj.toString();
}
```

Đây là **mã minh họa hành vi**, không phải bản sao mã nguồn JDK. Khi đối số là `null`, kết quả là đối tượng `String` mang nội dung chữ `null`, **không phải tham chiếu `null`**.

```java
String result = String.valueOf((Object) null);
System.out.println(result.equals("null")); // true
System.out.println(result == null);        // false
```

### `valueOf(char[])` cần một mảng thật

Overload nhận `char[]` dùng các phần tử của mảng ký tự để tạo một `String` mới:

```java
char[] letters = {'J', 'a', 'v', 'a'};
String text = String.valueOf(letters);
System.out.println(text); // Java
```

Nếu `data` là `null`, không có mảng để đọc. Phương thức **không tự chuyển `null` thành chữ `"null"`**, mà ném `NullPointerException`. Truyền mảng rỗng `new char[0]` thì hợp lệ và tạo chuỗi rỗng `""`: mảng rỗng khác với tham chiếu mảng `null`.

## 2. Vì sao `String.valueOf(null)` gọi overload `char[]`?

Java quyết định phương thức nào được gọi dựa trên **kiểu của biểu thức đối số tại thời điểm biên dịch**, theo các quy tắc lựa chọn overload của ngôn ngữ Java.

Với lời gọi:

```java
String.valueOf(null)
```

Literal `null` có thể được dùng ở vị trí đối số của phương thức nhận **kiểu tham chiếu**. Trong hai overload có thể áp dụng:

```java
String.valueOf(Object obj);
String.valueOf(char[] data);
```

`char[]` là một **kiểu tham chiếu con của `Object`**: mọi mảng Java đều là đối tượng và có thể được gán cho biến kiểu `Object`. Vì vậy `valueOf(char[])` được xem là **cụ thể hơn (more specific)** so với `valueOf(Object)`.

Java chọn phương thức cụ thể nhất trong các overload áp dụng được. Vì thế:

```text
Đối số: null literal
    |
    +-- valueOf(Object) : áp dụng được
    |
    +-- valueOf(char[]) : áp dụng được, cụ thể hơn Object
                              |
                              +--> được chọn lúc biên dịch
                                    |
                                    +--> thực thi với mảng null
                                              |
                                              +--> NullPointerException
```

**Không có lỗi “ambiguous method call”** ở đây vì Java có một lựa chọn cụ thể hơn. Cũng **không có bước thử `Object` sau khi overload `char[]` ném lỗi**: overload đã được xác định trước khi thực thi.

Lưu ý: `char[]` không phải kiểu con của `String`. Java không có overload `String.valueOf(String)`; việc ép kiểu `(String) null` sẽ đi qua `Object`. Nếu một API tự định nghĩa có hai overload nhận các kiểu tham chiếu không liên quan và đều áp dụng được, literal `null` có thể khiến lời gọi trở nên mơ hồ; đây là câu chuyện khác với cặp `Object` và `char[]`.

## 3. So sánh mọi cách truyền `null` thường gặp

| Biểu thức Java | Overload được chọn khi biên dịch | Kết quả |
| --- | --- | --- |
| `String.valueOf(null)` | `char[]` | `NullPointerException` |
| `String.valueOf((Object) null)` | `Object` | `"null"` |
| `String.valueOf((char[]) null)` | `char[]` | `NullPointerException` |
| `String.valueOf((String) null)` | `Object` | `"null"` |
| `String.valueOf((int[]) null)` | `Object` | `"null"` |
| `Object o = null; String.valueOf(o)` | `Object` | `"null"` |
| `char[] chars = null; String.valueOf(chars)` | `char[]` | `NullPointerException` |
| `String s = null; String.valueOf(s)` | `Object` | `"null"` |

`(Object) null` là **ép kiểu tường minh**: ta nói với trình biên dịch rằng biểu thức truyền vào mang kiểu `Object`, nên overload `char[]` không còn áp dụng được.

`(char[]) null` ép kiểu theo chiều ngược lại: bắt trình biên dịch coi đối số là `char[]`, vì vậy chọn overload `char[]` và gặp lỗi khi dùng mảng null.

`(String) null` có kiểu tĩnh là `String`, vốn là con của `Object` nhưng **không** phải con của `char[]`. Do đó nó được xử lý như đối số `Object`.

Tương tự, `int[]` là một loại mảng nhưng **không thể** chuyển sang `char[]`; vì thế `String.valueOf((int[]) null)` cũng gọi overload `Object`.

**Quan trọng:** Java không dò kiểu của một đối tượng ở runtime để đổi từ overload `Object` sang `char[]`. Chọn overload khác với cơ chế *override* (đa hình phương thức instance).

## 4. Ví dụ Java 17+ chạy độc lập

Tạo file `ValueOfNullOverloadsDemo.java`:

```java
import java.util.function.Supplier;

public class ValueOfNullOverloadsDemo {

    private static void check(String label, Supplier<String> action) {
        try {
            System.out.println(label + " -> " + action.get());
        } catch (NullPointerException ex) {
            System.out.println(label + " -> NullPointerException");
        }
    }

    public static void main(String[] args) {
        check("literal", () -> String.valueOf(null));
        check("(Object)null", () -> String.valueOf((Object) null));
        check("(char[])null", () -> String.valueOf((char[]) null));
        check("(String)null", () -> String.valueOf((String) null));

        Object obj = null;
        char[] chars = null;
        String string = null;

        check("Object variable", () -> String.valueOf(obj));
        check("char[] variable", () -> String.valueOf(chars));
        check("String variable", () -> String.valueOf(string));

        char[] data = {'J', 'a', 'v', 'a'};
        System.out.println("char[] content -> " + String.valueOf(data));

        // Không in mã băm đối tượng vì nó có thể đổi giữa các lần chạy.
        String objectText = String.valueOf((Object) data);
        System.out.println("Object-char[] uses array identity -> "
                + objectText.startsWith("[C@"));
    }
}
```

Dùng JDK 17 hoặc mới hơn để chạy:

```bash
javac ValueOfNullOverloadsDemo.java
java ValueOfNullOverloadsDemo
```

Kết quả stdout:

```text
literal -> NullPointerException
(Object)null -> null
(char[])null -> NullPointerException
(String)null -> null
Object variable -> null
char[] variable -> NullPointerException
String variable -> null
char[] content -> Java
Object-char[] uses array identity -> true
```

Hàm `check` chủ động bắt `NullPointerException` **chỉ để minh họa và cho phép chương trình tiếp tục chạy** qua mọi trường hợp. Trong chương trình thực tế, hãy kiểm tra dữ liệu trước khi gọi nếu `null` có thể xuất hiện; không cần dùng exception như một nhánh xử lý thông thường.

Không đưa nội dung `ex.getMessage()` hay stack trace vào stdout vì thông báo lỗi cụ thể có thể thay đổi tùy phiên bản JDK. Ví dụ giữ kết quả rõ ràng và ổn định bằng cách in tên loại exception.

## 5. Điều gì xảy ra với mảng `char[]` không phải `null`?

Sự khác biệt giữa hai overload tồn tại **ngay cả khi mảng có nội dung**:

```java
char[] data = {'O', 'K'};

String byChars = String.valueOf(data);          // overload char[]
String byObject = String.valueOf((Object) data); // overload Object

System.out.println(byChars);                    // OK
System.out.println(byObject.startsWith("[C@")); // true
```

Khi gọi `valueOf(char[])`, Java chuyển **các phần tử ký tự** thành chuỗi. Khi gọi `valueOf(Object)` với một mảng ký tự, Java gọi `toString()` của chính **đối tượng mảng**. Mảng Java mặc định không ghi đè `Object.toString()` để liệt kê các phần tử, nên thường được biểu diễn bằng tên kiểu và mã nhận dạng, ví dụ `[C@...`, trong đó `[C` là tên kiểu JVM cho `char[]` và phần sau có thể thay đổi.

Vì vậy, ép kiểu `(Object) data` là cách **chọn overload `Object`** chứ không phải cách chuyển nội dung `char[]` thành chuỗi. Nó chỉ hữu ích trong ngữ cảnh cần dùng quy tắc chuyển đổi kiểu `Object`, đặc biệt khi muốn `null` được biểu diễn thành chữ `"null"`.

Ngoài ra, `valueOf(char[])` tạo nội dung chuỗi độc lập với mảng ban đầu:

```java
char[] data = {'O', 'K'};
String text = String.valueOf(data);
data[0] = 'N';
System.out.println(text); // OK
```

Mảng có thể thay đổi, còn `String` là immutable; sửa mảng sau khi tạo chuỗi không thay đổi `text`.

## 6. Vì sao biến kiểu `Object` không tự gọi `char[]`?

Xét:

```java
char[] source = {'H', 'i'};
Object asObject = source;

String s1 = String.valueOf(source);   // char[] overload
String s2 = String.valueOf(asObject); // Object overload
```

`source` và `asObject` trỏ tới **cùng một đối tượng mảng**, nhưng trình biên dịch thấy kiểu của chúng lần lượt là `char[]` và `Object`. Vì vậy, `s1` chứa `"Hi"`; `s2` chứa biểu diễn mặc định của đối tượng mảng như `[C@...`.

Với `null` cũng vậy:

```java
char[] chars = null;
Object obj = chars;

String a = String.valueOf(obj);   // "null"
String b = String.valueOf(chars); // NullPointerException
```

Sự khác biệt xuất hiện **do kiểu tĩnh của biểu thức**. Không nên đoán overload theo kiểu mà biến có thể trỏ tới khi chạy.

Một hàm nhận đối số kiểu `Object` sẽ luôn gọi phiên bản `valueOf(Object)` cho lời gọi bên trong:

```java
static String convert(Object value) {
    return String.valueOf(value);
}
```

Đây là **đoạn minh họa cần đặt trong một class**, không phải chương trình độc lập. Gọi `convert(null)` trả về `"null"`. Gọi `convert(new char[] {'A', 'B'})` lại không tạo `"AB"`, bởi overload `Object` xử lý mảng như một đối tượng.

## 7. Cách xử lý an toàn trong code thực tế

### Mục tiêu A: mọi `null` đều thành chuỗi `"null"`

Nếu đối số có thể mang nhiều kiểu và muốn quy ước `null` thành văn bản `"null"`, gọi overload `Object` rõ ràng:

```java
String result = String.valueOf((Object) null);
```

Với biến tĩnh `Object value`, chỉ cần `String.valueOf(value)`. Tuy nhiên nếu giá trị **không phải null** và lại là mảng, `Object.toString()` không nhất thiết trả về nội dung các phần tử. Hãy chọn theo đúng mục đích.

### Mục tiêu B: cần nội dung `char[]` và có thể gặp `null`

Kiểm tra mảng trước khi gọi overload `char[]`:

```java
static String safeChars(char[] chars) {
    return chars == null ? "null" : String.valueOf(chars);
}
```

Hàm trên cần được khai báo bên trong một class. Nó trả về chuỗi `"null"` khi mảng không tồn tại, và trả về **nội dung ký tự** khi mảng có dữ liệu. Nếu `null` cần có nghĩa “không có giá trị” thay vì chữ `"null"`, hãy dùng quy ước phù hợp, ví dụ:

```java
static String displayChars(char[] chars) {
    return chars == null ? "<missing>" : String.valueOf(chars);
}
```

`"<missing>"` chỉ là placeholder do chương trình định nghĩa; không phải giá trị được Java tự động tạo.

### Mục tiêu C: cần chuỗi mặc định cho đối tượng bất kỳ

`java.util.Objects.toString(obj, nullDefault)` cho phép chỉ định văn bản thay `null`:

```java
import java.util.Objects;

// Đoạn minh họa bên trong một phương thức.
Object obj = null;
String result = Objects.toString(obj, "<none>");
System.out.println(result); // <none>
```

Nếu `obj` thực tế trỏ tới `char[]` không null, `Objects.toString` vẫn gọi `toString()` của đối tượng mảng, **không** tự chuyển từng ký tự thành một `String`. Phương thức này giúp xử lý `null` theo kiểu `Object`, không thay thế cho `String.valueOf(char[])`.

### Mục tiêu D: muốn ký tự `"null"` được in nhưng không cần chọn overload

Nếu chỉ cần in thông tin chẩn đoán, có thể viết:

```java
System.out.println("value=" + null);
// value=null
```

Đây là quy tắc **nối chuỗi (`String` concatenation)** của Java, không phải lời gọi `String.valueOf(null)` trực tiếp ở mã nguồn. Không nên suy luận từ biểu thức nối chuỗi rằng `String.valueOf(null)` cũng sẽ trả về `"null"`.

## 8. Những hiểu nhầm thường gặp

1. **“`String.valueOf(null)` luôn trả về `"null"`.”** Sai: lời gọi với null literal chọn `valueOf(char[])` rồi ném `NullPointerException`.
2. **“Java chọn overload theo dữ liệu runtime.”** Sai trong trường hợp này: lựa chọn overload dựa vào **kiểu tĩnh** tại thời điểm biên dịch. Vì thế biến `Object` và biến `char[]` có thể tạo kết quả khác nhau dù cùng trỏ tới một mảng.
3. **“Đó là lỗi mơ hồ giữa `Object` và `char[]`.”** Sai: `char[]` là con của `Object`, nên overload `char[]` cụ thể hơn và được chọn.
4. **“Ép kiểu `(Object)` rồi vẫn nhận nội dung mảng.”** Không đúng với mảng `char[]` không null: chuyển sang overload `Object` khiến `toString()` mặc định của mảng được dùng.
5. **“`char[]` rỗng tương đương `null`.”** Sai: `new char[0]` là mảng hợp lệ và cho chuỗi rỗng; `(char[]) null` không phải mảng và gây `NullPointerException`.
6. **“Kết quả `"null"` là Java null.”** Sai: đây là một `String` có bốn ký tự `n`, `u`, `l`, `l`; đối tượng chuỗi tồn tại bình thường.
7. **“Nên bắt `NullPointerException` để sửa dữ liệu.”** Thường không cần. Nếu `null` được phép xuất hiện, kiểm tra bằng `if` hoặc toán tử ba ngôi và quyết định ý nghĩa thích hợp cho ứng dụng.
8. **“Dùng `Objects.toString` sẽ đổi mọi mảng ra nội dung.”** Không đúng: với đối tượng mảng không null, nó dùng `toString()` của đối tượng đó.

## 9. Bài luyện tập

**Câu 1.** Ba biểu thức dưới đây trả về gì?

```java
String.valueOf((Object) null);
String.valueOf((char[]) null);
String.valueOf(null);
```

Đáp án lần lượt: `"null"`; `NullPointerException`; `NullPointerException`.

**Câu 2.** Với:

```java
Object a = null;
char[] b = null;
```

Lời gọi `String.valueOf(a)` và `String.valueOf(b)` khác nhau thế nào?

Đáp án: `a` có kiểu tĩnh `Object` nên nhận chuỗi `"null"`. `b` có kiểu tĩnh `char[]` nên ném `NullPointerException`.

**Câu 3.** Vì sao `String.valueOf((String) null)` trả về `"null"`?

Đáp án: `String` là con của `Object` nhưng không tương thích với `char[]`; chỉ overload `Object` có thể nhận đối số này.

**Câu 4.** Đổi một biến `char[] chars` có thể null thành văn bản và bảo toàn nội dung ký tự khi mảng không null.

Đáp án:

```java
String result = chars == null ? "<empty>" : String.valueOf(chars);
```

Ở đây `"<empty>"` là giá trị thay thế theo quy tắc của ứng dụng, không có liên quan trực tiếp tới lựa chọn overload.

**Câu 5.** Với `Object data = new char[] {'A', 'B'};`, `String.valueOf(data)` có trả về `"AB"` không?

Đáp án: không. Overload nhận `Object` được chọn theo kiểu tĩnh `Object` của `data`. Nó dùng `toString()` của đối tượng mảng nên cho biểu diễn kiểu `[C@...`, không phải các ký tự nối lại.

**Ghi nhớ:** `String.valueOf(null)` nguy hiểm vì `char[]` là overload cụ thể hơn `Object`. Muốn chọn xử lý `null` theo `Object`, ép kiểu `(Object) null` hoặc truyền biến mang kiểu `Object`. Muốn lấy nội dung của mảng ký tự, dùng `valueOf(char[])` với mảng **khác null** và kiểm tra null rõ ràng.

## Tài liệu chính thức

- [`String.valueOf(Object)` và `String.valueOf(char[])` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [JLS §15.12.2 — Compile-Time Step 2: Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2)
- [JLS §15.12.2.5 — Choosing the Most Specific Method](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2.5)
