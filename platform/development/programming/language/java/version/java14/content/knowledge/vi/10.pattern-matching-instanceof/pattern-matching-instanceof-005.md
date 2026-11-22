# Kiểu tĩnh của biến mẫu sau khi khớp với instanceof

## 1. Biến mẫu có kiểu tĩnh ngay từ lúc biên dịch

Pattern matching cho toán tử `instanceof` cho phép **kiểm tra kiểu và khai báo biến đã được kiểm tra kiểu trong cùng một biểu thức**:

~~~java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

Trong mã này có **ba thông tin khác nhau**, cần phân biệt:

- **Kiểu tĩnh của biểu thức nguồn `input`:** `Object`, vì khai báo `Object input`. Việc biến đang tham chiếu đến một chuỗi không tự đổi khai báo đó.
- **Kiểu được nêu trong type pattern:** `String` tại `instanceof String text`. Phép thử kiểm tra ở runtime xem đối tượng có tương thích với `String` không.
- **Kiểu tĩnh của biến mẫu `text` sau khi match:** **`String`**, đúng theo kiểu được ghi trong pattern. Compiler cho gọi các phương thức hợp lệ của `String` như `toUpperCase()` hoặc `strip()` mà không cần cast.

**Quy tắc cốt lõi: trong type pattern `T name`, biến mẫu `name` có kiểu tĩnh T.** Kiểu này được xác định khi biên dịch, **không được suy từ lớp runtime cụ thể của đối tượng**.

Tính năng này là chính thức từ **Java 16 (JEP 394)** và được dùng trực tiếp trên **Java 17+**. Dù chủ đề nằm trong lộ trình Java 14, không cần dựa vào phiên bản preview cũ; tất cả ví dụ chạy trong Java 17 trở lên mà không bật `--enable-preview`.

## 2. Vì sao phải phân biệt kiểu tĩnh và kiểu runtime?

Ví dụ:

~~~java
Object value = new StringBuilder("hello");

if (value instanceof CharSequence chars) {
    System.out.println(chars.length()); // 5
}
~~~

Ở thời điểm chạy, object thực tế có lớp `StringBuilder`. Tuy nhiên, `chars` có **kiểu tĩnh `CharSequence`**, vì pattern được viết là `CharSequence chars`. Compiler biết `CharSequence` công bố `length()`, `charAt()` và `subSequence()`, nên cho phép gọi các phương thức đó.

Nhưng:

~~~java
Object value = new StringBuilder("hello");

if (value instanceof CharSequence chars) {
    System.out.println(chars.length()); // Hợp lệ.
    // chars.append("!");               // Lỗi biên dịch.
}
~~~

`append()` là API của `StringBuilder`, không phải API của `CharSequence`. Java không cấp quyền gọi phương thức của subtype chỉ vì dữ liệu chạy thử hiện tại đang là subtype đó.

Nếu nghiệp vụ thực sự cần thao tác cụ thể của `StringBuilder`, kiểm tra hẹp hơn:

~~~java
if (value instanceof CharSequence chars) {
    if (chars instanceof StringBuilder builder) {
        builder.append("!");
        System.out.println(builder.toString());
    }
}
~~~

Biến `chars` vẫn có kiểu tĩnh `CharSequence`; biến mới `builder` có kiểu tĩnh `StringBuilder`. Phép thử không clone hay chuyển đổi object: cả hai biến có thể tham chiếu tới cùng một object runtime.

### So sánh trực quan

| Đối tượng/biến | Kiểu tĩnh | Kiểu runtime trong ví dụ | API compiler cho phép |
| --- | --- | --- | --- |
| `value` | `Object` | `StringBuilder` | Các thành viên hợp lệ của `Object` |
| `chars` | `CharSequence` | `StringBuilder` | Các thành viên hợp lệ của `CharSequence` |
| `builder` | `StringBuilder` | `StringBuilder` | Các thành viên hợp lệ của `StringBuilder` |

Một biến mang kiểu interface hoặc superclass vẫn có thể giữ đối tượng subtype; điều đó **không** khiến compiler âm thầm đổi kiểu đã khai báo của biến.

## 3. Ngay cả overload cũng được chọn theo kiểu tĩnh

Sự khác biệt không chỉ nằm ở việc gọi phương thức của đối tượng. Java chọn phương thức **overload** bằng các kiểu biểu thức khi biên dịch:

~~~java
static String choose(Object value) {
    return "Object";
}

static String choose(CharSequence value) {
    return "CharSequence";
}

static String choose(String value) {
    return "String";
}
~~~

Giả sử những phương thức trên nằm trong một class, ta gọi:

~~~java
Object input = "java";

if (input instanceof CharSequence chars) {
    System.out.println(choose(chars)); // CharSequence
    System.out.println(choose(input)); // Object

    if (chars instanceof String text) {
        System.out.println(choose(text)); // String
    }
}
~~~

Cả `input`, `chars` và `text` đều có thể chỉ tới **cùng một đối tượng String**. Nhưng compiler nhìn thấy các kiểu **`Object`, `CharSequence` và `String`** tương ứng, nên chọn overload khác nhau. Đây là ví dụ rất rõ về việc “biến mẫu có kiểu tĩnh của pattern”, chứ không phải kiểu chạy được suy động ở mỗi dòng.

Đừng nhầm **overloading** (chọn signature bằng kiểu tĩnh) với **overriding** (gọi cài đặt polymorphic dựa trên đối tượng runtime đối với phương thức instance được override). Pattern matching không thay đổi các quy tắc nền tảng này.

## 4. So với kiểm tra instanceof rồi ép kiểu thủ công

Cách truyền thống:

~~~java
Object input = "Java";

if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.length());
}
~~~

Cách dùng type pattern:

~~~java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

Cả hai cách đều cho biến `text` có kiểu tĩnh `String` ở nhánh tương ứng. Cách mới ngắn gọn hơn và tránh lặp thông tin kiểu giữa phép kiểm tra và cast. Nó cũng tránh lỗi vô tình kiểm tra một kiểu rồi ép sang kiểu khác.

**Không phải smart-cast cho biến nguồn:** trong ví dụ trên, `input` tiếp tục có kiểu `Object`. Chỉ `text` có kiểu tĩnh `String`:

~~~java
if (input instanceof String text) {
    System.out.println(text.length());  // Hợp lệ.
    // System.out.println(input.length()); // Không hợp lệ.
}
~~~

Thói quen tốt là **dùng chính biến mẫu vừa match** thay vì ép lại biến nguồn.

## 5. Phạm vi biến mẫu theo luồng điều khiển (flow scoping)

Một biến mẫu chỉ được dùng ở vị trí compiler biết rằng pattern **đã khớp và biến đã có giá trị**. Vì vậy phạm vi của nó không chỉ phụ thuộc dấu ngoặc nhọn mà còn phụ thuộc luồng boolean và các nhánh có thể đi tới.

### 5.1. Nhánh if thành công

~~~java
static void showLength(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // Hợp lệ.
    } else {
        // Không sử dụng được text ở nhánh else.
    }

    // Không sử dụng được text ở đây khi cả hai nhánh tiếp tục.
}
~~~

`text` có kiểu tĩnh `String` **ở những nơi nó nằm trong scope**. Tính đúng đắn về kiểu và việc được phép dùng ở một vị trí là **hai câu hỏi độc lập**.

### 5.2. Toán tử &&

~~~java
static boolean isLongEnough(Object input) {
    return input instanceof String text && text.length() >= 4;
}
~~~

`&&` short-circuit: vế phải chỉ được đánh giá khi vế trái true. Do đó `text` đã được khởi tạo, có kiểu `String`, và được sử dụng hợp lệ ở vế phải.

### 5.3. Toán tử || — ví dụ cố ý sai

~~~java
static boolean incorrect(Object input) {
    return input instanceof String text || text.isBlank();
    // Lỗi compile: vế phải có thể chạy khi instanceof false.
}
~~~

Vế phải của `||` có thể được chạy khi vế trái **false** — chính là lúc `text` chưa khớp. Không thể dùng biến này ở đây. Nếu muốn “đúng là chuỗi và không rỗng”, dùng `input instanceof String text && !text.isBlank()`.

### 5.4. Phủ định và early return

~~~java
static String upperOrNA(Object input) {
    if (!(input instanceof String text)) {
        return "N/A";
    }
    return text.strip().toUpperCase();
}
~~~

Nếu chạy đến `return` cuối, đường không khớp đã thoát khỏi phương thức. Java biết `text` đã khớp, nên vẫn cho phép dùng nó **sau** câu `if`. Biến có kiểu tĩnh `String` như lúc khai báo.

Nếu nhánh phủ định chỉ in thông báo rồi tiếp tục, kết luận đó không còn đúng; compiler sẽ không cho dùng biến mẫu ở điểm có thể đi tới khi phép thử thất bại.

### 5.5. Trong toán tử ba ngôi

~~~java
static int lengthOrMinusOne(Object input) {
    return input instanceof String text ? text.length() : -1;
}
~~~

`text` được sử dụng ở nhánh `?` khi match true; không tự có mặt trong nhánh `:` khi match false.

## 6. Chương trình độc lập chạy trên Java 17+

Tệp: **`PatternStaticTypeDemo.java`**. Ví dụ minh họa cùng lúc kiểu tĩnh, lớp runtime, overload và flow scoping.

~~~java
import java.util.Locale;

public class PatternStaticTypeDemo {

    static String choose(Object value) {
        return "Object";
    }

    static String choose(CharSequence value) {
        return "CharSequence";
    }

    static String choose(String value) {
        return "String";
    }

    static void inspect(Object value) {
        if (value instanceof CharSequence text) {
            System.out.println(
                    "runtime=" + text.getClass().getSimpleName()
            );
            System.out.println("length=" + text.length());
            System.out.println("overload=" + choose(text));
            System.out.println("original=" + choose(value));

            if (text instanceof String string) {
                System.out.println(
                        "upper=" + string.toUpperCase(Locale.ROOT)
                );
                System.out.println("narrow=" + choose(string));
            }
            return;
        }

        if (value instanceof Number number) {
            System.out.println("number=" + number.doubleValue());
            return;
        }

        System.out.println("unmatched");
    }

    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "N/A";
        }
        return text.strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        inspect("java");
        inspect(new StringBuilder("abc"));
        inspect(Integer.valueOf(42));
        inspect(null);

        System.out.println("normalized=" + normalize("  sdk  "));
        System.out.println("normalized-null=" + normalize(null));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 PatternStaticTypeDemo.java
java PatternStaticTypeDemo
~~~

Kết quả dự kiến:

~~~text
runtime=String
length=4
overload=CharSequence
original=Object
upper=JAVA
narrow=String
runtime=StringBuilder
length=3
overload=CharSequence
original=Object
number=42.0
unmatched
normalized=SDK
normalized-null=N/A
~~~

**Giải thích:**

1. `inspect("java")`: `value` có kiểu `Object`, `text` có kiểu `CharSequence`; object runtime là `String`. `choose(text)` chọn overload `CharSequence`, còn `choose(value)` chọn overload `Object`. Sau khi match subtype, `string` có kiểu `String` và `choose(string)` chọn overload `String`.
2. `inspect(new StringBuilder("abc"))`: kiểu tĩnh của biến mẫu vẫn là `CharSequence`, nhưng runtime class in là `StringBuilder`. `StringBuilder` không phải `String` nên không có dòng `upper` và `narrow`.
3. `inspect(Integer.valueOf(42))`: không match `CharSequence` nhưng match `Number`. Biến `number` có kiểu tĩnh `Number` và cho gọi `doubleValue()`, kết quả in `42.0`.
4. `inspect(null)`: `null` không match type pattern, vì vậy in `unmatched`.
5. `normalize` dùng phủ định và `return` sớm. Khi đến dòng xử lý cuối, `text` chắc chắn là `String` và có thể gọi `strip()`, `toUpperCase(Locale.ROOT)`.

Chương trình này **biên dịch độc lập** nếu lưu đúng tệp và có JDK 17 trở lên; không dùng thư viện ngoài.

## 7. Trường hợp lỗi do kiểu tĩnh của biểu thức đã quá cụ thể

Pattern matching `instanceof` được chuẩn hóa với kiểm tra compile-time: nếu kiểu tĩnh của biểu thức được kiểm tra đã là subtype của kiểu `T` trong type pattern, phép kiểm tra pattern bị xem là thừa và **không hợp lệ**.

~~~java
String name = "Java";

// Mã cố ý sai:
// if (name instanceof String text) {
//     System.out.println(text.length());
// }
~~~

`name` đã có kiểu tĩnh `String`; không cần một biến mẫu `String` thứ hai. Nếu cần bảo vệ null, dùng kiểm tra `name != null` rồi gọi `name.length()`.

Đặc biệt lưu ý với `var`:

~~~java
var first = "java";     // Compiler suy ra kiểu tĩnh String.
Object second = first;  // Kiểu tĩnh Object.

// if (first instanceof String s) { } // Lỗi: phép thử thừa.
if (second instanceof String s) {     // Hợp lệ.
    System.out.println(s.length());
}
~~~

`var` không có nghĩa là kiểu biến thay đổi tùy đối tượng chạy thực tế. Nó chỉ yêu cầu compiler **suy ra một kiểu tĩnh** từ initializer.

Tương tự, compiler có thể từ chối một type pattern vốn không thể thành công vì kiểu tĩnh của biểu thức và kiểu pattern là các class không tương thích:

~~~java
Integer number = 42;
// if (number instanceof String text) {} // Lỗi compile.
~~~

Nếu chương trình thực sự nhận dữ liệu nhiều loại, dùng một supertype/interface đầu vào phù hợp và kiểm tra cụ thể ở nơi cần thiết, không ép một phép thử không thể đúng.

## 8. Generic type pattern: phân biệt kiểu tĩnh và type erasure

Khi nguồn là `Object`, không thể trực tiếp xác nhận giá trị là `List<String>` bằng type pattern thông thường vì generic type arguments không được giữ đủ trong runtime:

~~~java
Object input = java.util.List.of("a", "b");

if (input instanceof java.util.List<?> items) {
    Object first = items.get(0);
    System.out.println(first); // a
}

// Cố ý không biên dịch với đầu vào Object:
// if (input instanceof java.util.List<String> names) {}
~~~

Trong nhánh đã khớp, `items` có kiểu tĩnh **`List<?>`**. Kiểu giá trị có thể đọc an toàn qua `get(0)` là `Object`; compiler không tự suy rằng tất cả phần tử là String chỉ vì dữ liệu trong ví dụ chứa chuỗi.

Nếu cần sử dụng API của String, có thể kiểm tra thêm từng phần tử:

~~~java
Object first = items.get(0);

if (first instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Đoạn mã sau dùng `items` được khai báo ở nhánh trước, nên chỉ là **minh họa nối tiếp trong cùng phạm vi**, không phải một chương trình độc lập.

Điểm cần ghi nhớ: việc một biến mẫu có kiểu tĩnh `List<?>` hoàn toàn **không chứng minh kiểu phần tử** là `String`. Khi viết mã sản phẩm, cần xác thực cấu trúc dữ liệu, schema hoặc nội dung phần tử theo yêu cầu. Một số ngữ cảnh generics có quy tắc chuyển đổi cụ thể khác; không nên phát biểu rằng mọi type pattern có tham số đều sai, nhưng kiểm tra `Object instanceof List<String>` như trên không hợp lệ.

## 9. Biến mẫu có final không?

Trong Java 16+ và Java 17+, pattern variable **không mặc định là `final`**. Trong phạm vi hợp lệ, có thể gán lại cho nó một giá trị tương thích với **kiểu tĩnh đã khai báo**:

~~~java
Object input = " Java ";

if (input instanceof String text) {
    text = text.strip();
    System.out.println(text); // Java
}
~~~

Kiểu tĩnh của `text` vẫn là `String`; không thể gán một `StringBuilder` cho `text`. Việc gán lại không biến biến nguồn `input` thành `String` và không sửa nội dung đối tượng String cũ.

Để code dễ bảo trì, thường nên dùng biến mẫu làm **giá trị đã kiểm tra**, rồi tạo biến `normalized` nếu cần diễn tả một bước chuyển đổi mới:

~~~java
if (input instanceof String text) {
    String normalized = text.strip();
    System.out.println(normalized);
}
~~~

Không dựa vào những hạn chế của bản preview cũ; hành vi không bắt buộc final đã là một phần của thiết kế chính thức.

## 10. Null, phạm vi tên và lỗi thường gặp

- **Null không match type pattern:** `input instanceof String text` là `false` khi `input == null`. Không có biến `text` được khởi tạo khi phép thử thất bại.
- **Không suy ra runtime subtype:** nếu pattern là `Number n`, biến `n` có kiểu tĩnh `Number`, dù object có thể là `Integer`, `Long` hoặc `Double`. Chỉ gọi API phù hợp với `Number`, hoặc match thêm subtype nếu cần.
- **Không dùng biến mẫu ở nhánh thất bại:** `else` của phép thử dương không có biến mẫu; vế phải của `||` cũng không mặc nhiên có nó.
- **Không lạm dụng cast:** `if (input instanceof String text) { ((String) input).length(); }` có thể chạy nhưng lặp cast không cần thiết và dễ làm code thiếu nhất quán.
- **Không đặt tên trùng biến đang cùng phạm vi:** một pattern variable mới có thể xung đột tên với biến cục bộ đang ở scope. Dùng tên ngắn, có nghĩa.
- **Không xem scope như chỉ có dấu ngoặc nhọn:** sau guard clause kết thúc đường thất bại bằng `return`, biến có thể sử dụng ngoài khối `if`.
- **Không xem `instanceof` là cơ chế tạo object:** nếu match, biến mẫu nhận tham chiếu tới object được kiểm tra, không tạo bản sao.

Bảng ôn tập:

| Cú pháp | Kiểu tĩnh của biến mẫu | Có sử dụng ở nơi nêu không? |
| --- | --- | --- |
| `input instanceof String s`, trong nhánh true | `String` | Có |
| `input instanceof CharSequence cs`, trong nhánh true | `CharSequence` | Có |
| `input instanceof String s && s.length() > 1` | `String` | Có, ở vế phải `&&` |
| `input instanceof String s || s.isBlank()` | `String` về khai báo nhưng chưa chắc match | Không, lỗi compile |
| `if (!(input instanceof String s)) return;` rồi dùng `s` | `String` | Có, ở đường đi tiếp sau guard |
| `input instanceof List<?> list` | `List<?>` | Có khi khớp; phần tử đọc ra không tự thành String |

## 11. Checklist khi review

1. Xác định **kiểu tĩnh của biểu thức nguồn**: `Object`, superclass, interface hay kiểu suy ra từ `var`?
2. Nhìn vào **kiểu T trong type pattern**: đó mới là kiểu tĩnh của biến mẫu, không phải lớp runtime luôn luôn xuất hiện.
3. Phương thức muốn gọi có thực sự được khai báo trong T hoặc supertypes không? Nếu không, phải đổi thiết kế hoặc kiểm tra pattern subtype phù hợp.
4. Biến mẫu có được sử dụng ở nơi **chắc chắn đã match**? Xem `if`, `&&`, `||`, phủ định và early return.
5. Pattern có bị thừa vì biểu thức nguồn đã có kiểu tĩnh subtype của T không?
6. Có giới hạn `null` và type erasure nào cần xử lý không?
7. Có thể dùng biến mẫu thay cho cast lại biến nguồn không?
8. Nếu có overload, bạn đã hiểu rằng Java chọn signature theo **kiểu tĩnh** của biến được truyền vào chưa?

## 12. Bài tập tự luyện

**Bài 1 — Kiểu tĩnh khác runtime.** Cho `Object x = new StringBuilder("abc");` và `if (x instanceof CharSequence s)`. Hãy ghi kiểu tĩnh của `x`, `s`, lớp runtime và lý do `s.append("!")` không biên dịch. Đáp án: `Object`, `CharSequence`, `StringBuilder`; `append` không phải API của `CharSequence`.

**Bài 2 — Chọn overload.** Với ba hàm `choose(Object)`, `choose(CharSequence)`, `choose(String)` ở mục 6, dự đoán output của `choose(x)`, `choose(s)` và `choose(text)` khi `x` có kiểu `Object`, `s` là biến mẫu `CharSequence`, `text` là biến mẫu `String`. Đáp án lần lượt: Object, CharSequence, String.

**Bài 3 — Scope với boolean.** Tìm lỗi ở `x instanceof String s || s.length() == 0`. Viết lại thành kiểm tra “x là chuỗi không rỗng” bằng `&&`. Đáp án gợi ý: `x instanceof String s && !s.isEmpty()`.

**Bài 4 — Guard clause.** Viết `static String sanitize(Object x)` trả `"unknown"` nếu không phải String; với String thì `strip()` và viết hoa. Dùng `if (!(x instanceof String s)) return "unknown";` rồi dùng `s` phía sau.

**Bài 5 — var và type test.** So sánh `var a = "hello";` với `Object b = "hello";`: vì sao pattern `a instanceof String s` bị từ chối nhưng `b instanceof String s` hợp lệ? Đáp án: kiểu tĩnh được suy ra của `a` là `String`; của `b` là `Object`.

**Bài 6 — List<?>.** Với `Object value = List.of("x");`, dùng `instanceof List<?> list` và kiểm tra `list.get(0) instanceof String s` để gọi `s.toUpperCase()`. Giải thích tại sao `List<?>` không tự xác nhận kiểu phần tử.

## 13. Tài liệu chính thức

- [Oracle: Pattern Matching for instanceof (Java 17)](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html) — type pattern và scope theo đường điều khiển.
- [OpenJDK JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394) — chuẩn hóa từ Java 16, quy tắc kiểm tra type pattern và pattern variable.
- [Java Language Specification §14.30: Patterns (Java 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.30) — quy định type pattern và kiểu của biến mẫu.
- [Java Language Specification §6.3: Scope of a Declaration (Java 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3) — flow scoping của pattern variables.
- [Java Language Specification §15.20.2: Type Comparison Operator instanceof (Java 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2) — kiểm tra kiểu và tính hợp lệ của instanceof.
