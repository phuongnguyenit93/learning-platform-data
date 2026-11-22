# Phân biệt `true`, `false`, `null` với từ khóa trong Java

## 1. Điểm mấu chốt: literal không phải keyword

Trong Java 17, **`true`** và **`false`** là hai *boolean literals* (giá trị hằng trực tiếp kiểu `boolean`); **`null`** là *null literal* (giá trị đặc biệt biểu thị không có tham chiếu tới đối tượng).

Chúng dễ bị nhầm là từ khóa vì có cách viết được ngôn ngữ dành riêng và **không được dùng làm tên định danh**. Nhưng theo phân loại từ vựng Java, cả ba là **literal, không phải keyword**.

| Chuỗi trong source | Phân loại | Kiểu/ý nghĩa | Dùng làm tên biến? |
|---|---|---|---|
| `true` | Boolean literal | Giá trị `boolean` đúng | Không |
| `false` | Boolean literal | Giá trị `boolean` sai | Không |
| `null` | Null literal | Giá trị null, chuyển được sang kiểu tham chiếu phù hợp | Không |
| `boolean` | Keyword | Tên kiểu nguyên thủy boolean | Không |
| `if`, `else` | Keywords | Cấu trúc điều khiển | Không |
| `class`, `return` | Keywords | Khai báo lớp / trả kết quả | Không |
| `Boolean` | Tên lớp trong `java.lang` | Wrapper object cho boolean | Có thể dùng để tham chiếu lớp; **không phải keyword** |

**Ghi nhớ:** Đừng nói “`true` là từ khóa của kiểu `boolean`”. Câu chính xác là “`true` là **boolean literal**; `boolean` là **keyword** dùng để viết tên kiểu nguyên thủy”.

## 2. Boolean literals: `true` và `false`

Khai báo và gán giá trị:

~~~java
boolean loggedIn = true;
boolean suspended = false;

if (loggedIn && !suspended) {
    System.out.println("ALLOW");
} else {
    System.out.println("DENY");
}
~~~

Kết quả là `ALLOW`. Trong đoạn này:

- `boolean` là keyword cho kiểu dữ liệu.
- `true` và `false` là các literal, không phải tên biến.
- `loggedIn` và `suspended` là hai định danh do lập trình viên chọn.
- `if` và `else` là keywords, còn biểu thức `loggedIn && !suspended` tạo ra một giá trị `boolean`.

**Java không tự xem số nguyên là boolean.** Những đoạn sau sai cú pháp/kiểu:

~~~java
// boolean ready = 1;    // Sai: int không tự đổi thành boolean
// if (1) { }            // Sai: if cần điều kiện boolean
// boolean done = "true"; // Sai: String khác boolean
~~~

Nếu bạn nhận chuỗi `"true"` từ đầu vào, đó vẫn là **`String`**, chưa phải boolean literal trong mã nguồn. Có thể chuyển bằng API thích hợp, ví dụ `Boolean.parseBoolean("true")`.

### Phân biệt chữ hoa, chữ thường

Java phân biệt hoa/thường:

- `true` và `false` viết thường chính xác là literal.
- `True`, `False`, `TRUE`, `FALSE` **không tự động là literal**. Chúng có thể là định danh nếu được khai báo hợp lệ, hoặc gây lỗi tên chưa khai báo.
- `Boolean.TRUE` và `Boolean.FALSE` là **các field của lớp `Boolean`**, không phải chính cách viết literal `true` và `false`.

Ví dụ:

~~~java
boolean ready = true;
boolean approved = Boolean.TRUE;  // Unboxing từ Boolean sang boolean
// boolean wrong = True;         // Lỗi nếu không có biến/field tên True
~~~

Trong ứng dụng Java, nên dùng `true`/`false` trực tiếp khi cần giá trị `boolean`; dùng `Boolean` khi cần kiểu đối tượng theo hợp đồng API.

## 3. `null`: không có tham chiếu, không phải chuỗi "null"

`null` có thể được gán cho biến thuộc **kiểu tham chiếu** phù hợp:

~~~java
String name = null;
Integer score = null;
int[] numbers = null;
Object object = null;
~~~

Một biến tham chiếu chứa `null` nghĩa là **không tham chiếu đến object nào** vào thời điểm đó. Điều này không có nghĩa object bị xóa ngay, và cũng không phải một đối tượng `String` đặc biệt.

So sánh:

~~~java
String missing = null;
String text = "null";

System.out.println(missing == null); // true
System.out.println(text == null);    // false
System.out.println("null".equals(text));    // true
System.out.println("null".equals(missing)); // false
~~~

`"null"` là một chuỗi gồm bốn ký tự, hoàn toàn khác **null literal**.

**Không thể gán `null` cho kiểu primitive** như `int` và `boolean`:

~~~java
// int count = null;         // Sai ở compile time
// boolean enabled = null;   // Sai ở compile time
~~~

Một biến `Boolean` có thể nhận `null` vì `Boolean` là lớp wrapper (kiểu tham chiếu); biến `boolean` thì chỉ có hai giá trị `true` hoặc `false`.

### Kiểu của biểu thức `null`

Theo đặc tả Java, null literal có **null type** đặc biệt (không có tên kiểu để khai báo trực tiếp). Giá trị null có thể chuyển sang các kiểu tham chiếu, nhưng không phải mọi biểu thức Java đều có thể suy ra kiểu từ `null` đơn lẻ:

~~~java
String label = null;   // Đúng
Object value = null;   // Đúng
// var unknown = null; // Sai: var không suy ra kiểu thích hợp
~~~

Đừng nhầm **kiểu của null literal** với tên lớp `Null`: Java không có lớp chuẩn tên `Null` tương đương một “đối tượng null”.

## 4. Kiểm tra null và tránh NullPointerException

Một phép kiểm tra null thông dụng là:

~~~java
String userName = null;
boolean hasName = userName != null && !userName.isBlank();
System.out.println(hasName); // false
~~~

`&&` có tính **ngắn mạch**: nếu `userName != null` là `false` thì JVM không đánh giá `!userName.isBlank()`. Nhờ vậy không gọi method qua tham chiếu null.

Ngược lại:

~~~java
// String userName = null;
// System.out.println(userName.length()); // Ném NullPointerException
~~~

Đoạn trên **hợp lệ khi biên dịch** nhưng ném `NullPointerException` khi được thực thi. Đây là lỗi runtime, không phải bằng chứng `null` là keyword.

So sánh nội dung chuỗi an toàn hơn với literal:

~~~java
String state = null;
System.out.println("ACTIVE".equals(state)); // false
~~~

Trong các trường hợp kiểm tra hai đối tượng có thể null, `java.util.Objects.equals(a, b)` có thể phù hợp. Nó trả `true` khi cả hai cùng null, hoặc khi hai giá trị khác null được xem là bằng nhau theo `equals`.

**Bẫy:** `instanceof` với một giá trị null cho ra `false`:

~~~java
String s = null;
System.out.println(s instanceof String); // false
~~~

Một biến được khai báo kiểu `String` vẫn có thể chứa null; `instanceof` không kết luận rằng một giá trị null là instance của `String`.

## 5. Khi Boolean wrapper có null: unboxing cần cẩn thận

Java có hai kiểu dễ nhầm:

| Kiểu | Bản chất | Các giá trị có thể giữ |
|---|---|---|
| `boolean` | Kiểu nguyên thủy | `true`, `false` |
| `Boolean` | Kiểu tham chiếu (wrapper) | Đối tượng `Boolean` hoặc `null` |

Ví dụ:

~~~java
Boolean answer = null;
// if (answer) { } // Hợp lệ về kiểu, nhưng gây NullPointerException khi unboxing
~~~

Điều kiện `if` có thể nhận `Boolean` nhờ **auto-unboxing**, nhưng nếu tham chiếu là `null`, việc chuyển sang `boolean` sẽ gây `NullPointerException`.

Hai cách có ý nghĩa khác nhau:

~~~java
Boolean answer = null;

boolean definitelyTrue = Boolean.TRUE.equals(answer); // false
boolean hasValue = answer != null;                    // false
~~~

Cách đầu chỉ đúng nếu wrapper giữ giá trị true; cách sau chỉ kiểm tra **có giá trị hay không**, không quan tâm giá trị đó là true hay false.

Nếu nghiệp vụ có ba trạng thái “đúng, sai, chưa biết”, `Boolean` cho phép biểu diễn cả ba, nhưng phải quy định rõ cách xử lý null. Không tùy tiện xem null luôn là false: trong nhiều tình huống, “chưa biết” khác hoàn toàn “sai”.

## 6. Demo Java 17 chạy được: quan sát cả ba literal

Tạo tệp **`LiteralDemo.java`**:

~~~java
public final class LiteralDemo {
    private LiteralDemo() {}

    static class Defaults {
        boolean ready; // Mặc định false
        String note;   // Mặc định null
    }

    public static void main(String[] args) {
        boolean enabled = true;
        boolean blocked = false;
        String name = null;
        String word = "null";
        Boolean optional = null;

        System.out.println("enabled = " + enabled);
        System.out.println("blocked = " + blocked);
        System.out.println("name == null: " + (name == null));
        System.out.println("\"null\" == null: " + (word == null));
        System.out.println("word equals null text: " + "null".equals(word));
        System.out.println("name is nonblank: "
                + (name != null && !name.isBlank()));
        System.out.println("Boolean.TRUE.equals(optional): "
                + Boolean.TRUE.equals(optional));
        System.out.println("optional == null: " + (optional == null));
        System.out.println("parseBoolean(TRUE): "
                + Boolean.parseBoolean("TRUE"));
        System.out.println("parseBoolean(yes): "
                + Boolean.parseBoolean("yes"));
        System.out.println("null instanceof String: "
                + (name instanceof String));

        Defaults defaults = new Defaults();
        System.out.println("default ready: " + defaults.ready);
        System.out.println("default note is null: "
                + (defaults.note == null));

        if (enabled && !blocked) {
            System.out.println("decision: ALLOW");
        }
    }
}
~~~

Với **JDK 17 hoặc mới hơn**, mở terminal tại thư mục chứa file.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 LiteralDemo.java
java -cp . LiteralDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\LiteralDemo.java
java -cp . LiteralDemo
~~~

Đầu ra kỳ vọng:

~~~text
enabled = true
blocked = false
name == null: true
"null" == null: false
word equals null text: true
name is nonblank: false
Boolean.TRUE.equals(optional): false
optional == null: true
parseBoolean(TRUE): true
parseBoolean(yes): false
null instanceof String: false
default ready: false
default note is null: true
decision: ALLOW
~~~

Giải thích thêm về `Boolean.parseBoolean(String)`: kết quả chỉ `true` khi chuỗi đầu vào biểu thị `"true"` (không phân biệt hoa/thường). Các chuỗi khác như `"yes"`, `"1"` và cả null cho kết quả `false`, **không ném lỗi nhập liệu**. Vì vậy, nếu nghiệp vụ phải từ chối đầu vào không hợp lệ, bạn cần kiểm tra chuỗi được phép thay vì chỉ gọi `parseBoolean`.

### Giá trị mặc định không áp dụng cho mọi biến

Trong `Defaults`, field `boolean ready` có mặc định `false`, còn field tham chiếu `String note` có mặc định `null`. Đây là quy tắc **khởi tạo field** của Java.

**Biến cục bộ** trong method không được tùy ý đọc khi chưa gán chắc chắn:

~~~java
// Trong method:
// boolean flag;
// System.out.println(flag); // Lỗi compile: biến cục bộ chưa được khởi tạo
~~~

Đừng suy ra vì field boolean mặc định false nên mọi biến boolean cục bộ cũng được cấp sẵn false.

## 7. Những biểu thức sai cần biết cách đọc lỗi

Các ví dụ **cố tình sai** dưới đây không nên đặt vào file chạy chính:

~~~java
// boolean a = True;       // Tên True chưa khai báo (nếu không có định danh đó)
// int x = null;           // null không chuyển sang int
// boolean ok = null;      // null không chuyển sang boolean primitive
// var item = null;        // Không suy ra được kiểu chỉ từ null
// int true = 1;           // true là boolean literal, không phải tên biến
// String null = "x";      // null literal không phải tên biến
// int class = 1;          // class là keyword
~~~

| Lỗi | Giai đoạn | Bản chất |
|---|---|---|
| Dùng `true` làm tên biến | Compile | Literal không được làm định danh |
| Dùng `class` làm tên biến | Compile | Keyword không được làm định danh |
| Gán `null` cho `int` | Compile | Null không chuyển sang primitive |
| `var x = null` | Compile | Không suy ra kiểu phù hợp |
| Gọi `name.length()` khi name null | Runtime | `NullPointerException` |
| Auto-unbox `Boolean` null | Runtime | `NullPointerException` |
| Nhận `"yes"` từ `parseBoolean` | Chạy đúng theo API | Trả false; cần validation nếu muốn báo dữ liệu sai |

Compiler không tự xác định ý nghĩa nghiệp vụ của `null`. Với API thật, hãy hỏi liệu null có nghĩa là “không có dữ liệu”, “chưa nhập”, hay “lỗi”, rồi chọn mô hình dữ liệu và validation phù hợp.

## 8. Không nhầm boolean với điều kiện và giá trị ba trạng thái

`true`/`false` là **giá trị**; `if`/`while` là **keywords điều khiển luồng**, còn phần trong ngoặc phải tạo ra một biểu thức boolean hợp lệ.

~~~java
boolean paid = true;
if (paid) {
    System.out.println("Da thanh toan");
}
~~~

Ở đây:

- `paid` là định danh, `true` là literal gán cho biến.
- `if` là keyword; `paid` là điều kiện boolean.
- `"Da thanh toan"` là string literal dùng để in, không phải giá trị boolean.

Java không có **primitive boolean thứ ba** biểu thị null. Khi cần trạng thái “chưa biết” cùng đúng/sai, bạn có thể dùng một mô hình minh bạch như enum:

~~~java
enum ApprovalState {
    APPROVED, REJECTED, UNKNOWN
}
~~~

Enum tránh phải đoán ý nghĩa `null`; tuy vậy nó chỉ đáng dùng khi nghiệp vụ thật sự có ba trạng thái và các luồng xử lý cần phân biệt.

## 9. Một số edge cases đáng nhớ

**1. `null == null` là true.** Cả hai vế là null literal nên phép so sánh tham chiếu phù hợp, kết quả là `true`. Nhưng nó không khiến null trở thành object có thể gọi method.

**2. `"false"` khác `false`.** Chuỗi `"false"` là `String`, còn `false` là `boolean`. Không thể viết `boolean valid = "false";` rồi trông đợi Java tự ép kiểu.

**3. `Boolean.FALSE` không phải null.** `Boolean.FALSE` là đối tượng wrapper biểu thị false; nếu field `Boolean` null, cần kiểm tra riêng trạng thái thiếu giá trị.

**4. `== null` thích hợp để kiểm tra có tham chiếu hay không.** Nhưng đừng dùng `==` để mặc định so sánh **nội dung** hai `String` không null; thường dùng `equals`.

**5. `null` có thể gây mơ hồ overload.** Nếu có hai overload không có quan hệ kiểu đủ rõ, như `work(String)` và `work(Integer)`, gọi `work(null)` có thể lỗi compile vì cả hai đều nhận null nhưng không có overload rõ ràng tốt hơn. Có thể ép kiểu `work((String) null)` nếu đó là chủ đích.

**6. Lưu ý `switch` với null trên Java 17.** Một switch expression/statement truyền thống nhận selector tham chiếu null thường có thể ném `NullPointerException` khi đánh giá. Không tự coi null là nhánh `default`; cần kiểm tra null trước hoặc dùng kỹ thuật phù hợp với phiên bản Java và yêu cầu.

**7. Null không tự đồng nghĩa “dữ liệu không tồn tại vĩnh viễn”.** Một biến đang null có thể được gán tham chiếu khác sau đó nếu cho phép gán lại. Trạng thái null là trạng thái của **giá trị tham chiếu**, không phải nhãn riêng bất biến của object.

## 10. Bài tập ngắn kèm đáp án

### Bài A — phân loại từ vựng

Phân loại các token `boolean`, `true`, `false`, `null`, `if`, `Boolean`.

**Đáp án:** `boolean` và `if` là keywords; `true`/`false` là boolean literals; `null` là null literal; `Boolean` là tên lớp wrapper trong `java.lang` (không phải keyword).

### Bài B — đúng hay lỗi?

~~~java
boolean x = false;
Boolean y = null;
String z = "null";
~~~

**Đáp án:** cả ba khai báo hợp lệ. `x` là primitive false, `y` là tham chiếu null, `z` là một chuỗi không null có nội dung `null`.

### Bài C — dự đoán đầu ra

~~~java
String s = null;
System.out.println(s == null);
System.out.println("abc".equals(s));
System.out.println(s instanceof String);
~~~

**Đáp án:**

~~~text
true
false
false
~~~

Không có lời gọi method thông qua `s`, nên không xảy ra `NullPointerException`.

### Bài D — chọn cách tránh lỗi unboxing

~~~java
Boolean flag = null;
// if (flag) System.out.println("ON");
~~~

**Đáp án:** `if (flag)` sẽ gây `NullPointerException` khi Java tự unbox giá trị null. Nếu mong muốn chỉ cho phép true, viết `if (Boolean.TRUE.equals(flag)) { ... }`. Nếu null mang ý nghĩa “chưa xác nhận”, xử lý riêng thay vì âm thầm quy thành false.

### Bài E — API nhận chuỗi từ người dùng

Ứng dụng chỉ chấp nhận `true` hoặc `false` (bất kể hoa/thường). Người dùng nhập `yes`. Có nên dùng `Boolean.parseBoolean("yes")` và coi đó là dữ liệu hợp lệ không?

**Đáp án:** Không. `parseBoolean("yes")` trả false theo API; nếu hệ thống yêu cầu **chỉ nhận hai chuỗi**, phải validation trước và từ chối `yes` bằng thông báo thích hợp.

## 11. Checklist tự kiểm tra

- [ ] Nêu đúng `true`/`false` là **boolean literals**, `null` là **null literal**; không gọi chúng là Java keywords.
- [ ] Phân biệt keyword `boolean` với literal `true` và `false`.
- [ ] Hiểu `Boolean` là class wrapper, khác primitive `boolean`.
- [ ] Biết `null` không phải string `"null"` và không gán được cho `int`/`boolean`.
- [ ] Không dùng ba literal `true`, `false`, `null` làm tên biến.
- [ ] Dùng `== null`, `!= null && ...` và `"literal".equals(value)` đúng mục đích.
- [ ] Phân biệt lỗi compile (kiểu không hợp lệ) với runtime `NullPointerException`.
- [ ] Biết field primitive boolean mặc định false, field tham chiếu mặc định null, nhưng biến cục bộ cần gán trước khi đọc.
- [ ] Chạy thành công `LiteralDemo.java` bằng `javac`/`java` và đối chiếu output.
- [ ] Không coi test chạy được là bằng chứng null có cùng ý nghĩa trong mọi nghiệp vụ.

**Kết luận:** **`true` và `false` là literal kiểu `boolean`; `null` là null literal; cả ba không phải từ khóa Java**, dù được dành riêng và không được dùng làm định danh. Từ khóa như `boolean`, `if`, `class` tạo cấu trúc ngôn ngữ; literal biểu diễn giá trị. Hiểu đúng phân loại này giúp đọc mã chính xác, tránh lỗi kiểu và xử lý null có chủ đích.