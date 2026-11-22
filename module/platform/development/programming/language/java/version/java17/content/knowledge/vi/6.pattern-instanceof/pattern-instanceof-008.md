# Gán lại biến pattern và giới hạn phạm vi trong Java 17

**Chủ đề:** Java 17 → Pattern instanceof  
**Trọng tâm:** Biến pattern có thể gán lại hay không; tên biến được nhìn thấy ở đâu sau phép kiểm tra `instanceof`; cách phạm vi thay đổi theo `if`, `else`, `!`, `&&`, `||`, toán tử ba ngôi và những nhánh kết thúc sớm.

**Pattern matching for `instanceof` là tính năng chính thức từ Java 16**, nên dùng được trực tiếp trong Java 17 mà không cần `--enable-preview`. Ở phiên bản chính thức, biến được khai báo bằng type pattern **không còn mặc nhiên là `final`**. Tuy nhiên, nó vẫn tuân theo quy tắc phạm vi đặc biệt theo **luồng điều khiển** (*flow scoping*).

Bài này chỉ bàn về **type pattern với `instanceof` trong Java 17**. Không sử dụng pattern matching cho `switch` vì cú pháp đó còn ở trạng thái *preview* trong Java 17; không dùng các dạng pattern được bổ sung ở phiên bản Java mới hơn.

## 1. Pattern variable là gì?

Trước khi có pattern matching, một thao tác kiểm tra kiểu và ép kiểu thường được viết:

~~~java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

Với Java 17, có thể kết hợp kiểm tra kiểu và khai báo biến:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Trong biểu thức `value instanceof String text`:

- `value` là biểu thức được kiểm tra.
- `String` là kiểu cần so khớp.
- `text` là **biến pattern**, được khởi tạo khi đối tượng khớp kiểu.
- Trong vùng mà biến `text` hợp lệ, mã có thể sử dụng trực tiếp các phương thức của `String` mà không cần ép kiểu thủ công.

Khi `value` là `null`, phép so khớp `instanceof String text` cho kết quả `false`, không tạo ra đường chạy mà `text` đã được gán giá trị.

Biến `text` không trở thành thành viên của `value`, không phải biến toàn cục và cũng không tồn tại trong mọi nhánh của phương thức. Nó là **biến cục bộ được giới thiệu bởi pattern**.

## 2. Biến pattern có được gán lại không?

**Có.** Trong Java 17, biến pattern được khai báo bởi `instanceof` **không mặc nhiên `final`**. Nếu biểu thức bên phải tương thích với kiểu của biến, ta có thể gán giá trị khác cho biến ngay trong phạm vi hợp lệ của nó.

Ví dụ:

~~~java
Object value = "  Hello Java  ";

if (value instanceof String text) {
    System.out.println(text); // Có khoảng trắng đầu/cuối.

    text = text.strip();       // Hợp lệ trên Java 17.

    System.out.println(text); // Hello Java
}
~~~

Biến `text` ban đầu tham chiếu chuỗi được kiểm tra. Sau phép gán `text = text.strip()`, biến này tham chiếu chuỗi đã được chuẩn hóa. **Việc gán lại `text` không tự động gán lại biến `value`.**

### 2.1. Giới hạn khi gán lại

Biến pattern có **kiểu tĩnh** là kiểu được viết trong pattern. Do đó:

~~~java
Object item = "A";

if (item instanceof String text) {
    text = "B";                   // Hợp lệ: String -> String.
    text = text.toLowerCase();    // Hợp lệ: trả về String.

    // text = 123;                // Sai: int không gán được cho String.
    // text = new Object();       // Sai: Object không gán được cho String.
}
~~~

Java vẫn áp dụng những quy tắc gán kiểu thông thường. Không thể dùng phép gán lại để “biến” một pattern `String` thành pattern `Integer`.

**`null` có thể được gán** cho một biến pattern mang kiểu tham chiếu, trừ khi có ràng buộc khác của chương trình hoặc công cụ phân tích tĩnh:

~~~java
Object value = "Hello";

if (value instanceof String text) {
    text = null;  // Về mặt cú pháp và kiểu Java: hợp lệ.

    // text.length();  // Biên dịch được, nhưng ném NullPointerException nếu chạy.
}
~~~

Điều này cho thấy phép kiểm tra ban đầu xác nhận đối tượng **tại thời điểm so khớp**, chứ không bảo đảm biến vẫn khác `null` hoặc vẫn tham chiếu đối tượng ban đầu sau mọi phép gán. Không nên gán `null` cho biến pattern chỉ để thử một nhánh logic; ví dụ trên minh họa ranh giới của tính năng.

### 2.2. Gán lại biến pattern khác với thay đổi đối tượng

Hãy phân biệt:

| Thao tác | Thứ thay đổi | Có đổi biến gốc được kiểm tra? |
| --- | --- | --- |
| `text = text.strip()` | Giá trị tham chiếu của biến pattern `text`. | Không tự động. |
| `builder.append("!")` với pattern `StringBuilder builder` | Trạng thái của **đối tượng** đang được tham chiếu. | Biến gốc có thể thấy thay đổi vì cùng trỏ tới đối tượng. |
| `value = anotherObject` | Giá trị tham chiếu của biến `value`. | Có, đây là phép gán trực tiếp cho biến gốc. |

Ví dụ về thay đổi đối tượng:

~~~java
Object value = new StringBuilder("Java");

if (value instanceof StringBuilder builder) {
    builder.append(" 17");
    System.out.println(builder); // Java 17
}

System.out.println(value);       // Java 17
~~~

`append` thay đổi nội dung của `StringBuilder`, chứ không phải gán một tham chiếu mới cho `builder`. Cả `value` và `builder` đều tham chiếu đến cùng đối tượng trong nhánh đó.

### 2.3. Vì sao nhiều tài liệu cũ nói biến pattern là `final`?

Các bản preview trước khi tính năng hoàn tất có những quy định khác nhau. Khi **JEP 394** hoàn thiện pattern matching cho `instanceof` ở Java 16, ràng buộc “biến pattern mặc nhiên `final`” đã được bỏ để nhất quán hơn với biến cục bộ thông thường. Vì vậy, khi học **Java 17**, cách giải thích “không thể gán lại biến pattern” là thông tin đã lỗi thời.

Quy tắc “có thể gán lại” **không đồng nghĩa** “nên gán lại thường xuyên”. Với mã cần dễ đọc hoặc cần đưa biến vào lambda, một biến kết quả riêng thường hữu ích hơn.

## 3. Flow scoping: phạm vi phụ thuộc đường chạy

Biến cục bộ được khai báo bằng `String text = ...` thông thường có phạm vi tính theo cấu trúc khối lệnh. Biến pattern khác ở chỗ **một đường chạy phải chứng minh phép so khớp thành công** trước khi tên biến được sử dụng.

Java Language Specification gọi cơ chế này là **flow scoping**: trình biên dịch xác định những vị trí mà pattern variable đã được *definitely matched* (chắc chắn so khớp thành công).

Ví dụ:

~~~java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ: nhánh true.
} else {
    System.out.println("Không phải String");

    // System.out.println(text); // Sai: text không thuộc phạm vi ở đây.
}

// System.out.println(text);     // Sai: sau if, text không chắc tồn tại.
~~~

**Lý do:** nếu điều kiện `instanceof` là `false`, nhánh `else` chạy nhưng pattern `String text` chưa từng khớp. Sau câu lệnh `if`, chương trình cũng có thể vừa đi qua nhánh `else`. Trình biên dịch không cho phép truy cập `text` ở các vị trí đó.

### Bảng phạm vi cơ bản

| Cấu trúc | Nơi có thể sử dụng biến pattern | Nơi không thể mặc định sử dụng |
| --- | --- | --- |
| `if (o instanceof String s)` | Bên trong nhánh `true`. | Nhánh `else`, phía sau toàn bộ `if` nếu cả hai đường chạy đều tiếp tục. |
| `if (o instanceof String s && điềuKiện(s))` | Phía phải `&&` và nhánh `true`. | Nhánh `else` hoặc sau `if` thông thường. |
| `if (o instanceof String s || điềuKiệnKhác)` | Không thể dùng `s` trong nhánh `true` chỉ vì cả biểu thức đúng. | Phía phải `||` và nhánh `true` của biểu thức này. |
| `if (!(o instanceof String s))` | Nhánh `else` khi điều kiện phủ định là sai. | Nhánh `true` của điều kiện phủ định. |
| `if (!(o instanceof String s)) return/throw;` | Phần mã tiếp tục sau guard clause. | Nhánh guard trước khi thoát. |
| `o instanceof String s ? s.trim() : "N/A"` | Nhánh thứ hai của toán tử ba ngôi (phần sau dấu `?`). | Nhánh sau dấu `:`. |

Đối với biểu thức phức tạp, phải xét đầy đủ các nhánh mà chương trình có thể đi qua, không chỉ nhìn vào dấu ngoặc nhọn.

## 4. Kết hợp với `&&`: phạm vi được mở sang vế phải

Toán tử `&&` trong Java có **short-circuit**: chỉ đánh giá vế phải nếu vế trái là `true`. Vì vậy:

~~~java
Object input = "Java 17";

if (input instanceof String text && text.length() >= 5) {
    System.out.println(text.toUpperCase());
}
~~~

Vế phải `text.length() >= 5` chỉ chạy khi `input instanceof String text` là `true`. Tại đó `text` đã được gán và có kiểu `String`, nên Java cho phép sử dụng biến.

Điều kiện có thể mở rộng:

~~~java
if (input instanceof String text
        && !text.isBlank()
        && text.length() <= 100) {
    System.out.println(text.strip());
}
~~~

Trong **nhánh `true`**, cả ba điều kiện đều đúng. Tuy nhiên nếu một điều kiện là `false`, không thể suy ra rằng phép so khớp đầu tiên đã thành công, nên không được mặc định dùng `text` trong `else`.

### Lỗi thường gặp: đảo thứ tự điều kiện

~~~java
Object input = "Java 17";

// Sai: text chưa được khai báo/khớp ở vế trái.
// if (text.length() > 0 && input instanceof String text) {
//     System.out.println(text);
// }
~~~

**Thứ tự có ý nghĩa:** kiểm tra kiểu phải đứng trước biểu thức dùng biến pattern.

## 5. Kết hợp với `||`: khi nào biến chưa chắc được gán?

Toán tử `||` cũng short-circuit, nhưng vế phải chỉ chạy khi vế trái là **`false`**. Vì thế mẫu sau không hợp lệ:

~~~java
Object input = "Java 17";
boolean allowOtherTypes = true;

// Sai: khi vế trái false, vế phải vẫn có thể chạy
// dù input không phải String.
// if (input instanceof String text || allowOtherTypes) {
//     System.out.println(text.length());
// }
~~~

Ngay cả khi **toàn bộ điều kiện đúng**, đó có thể là do `allowOtherTypes`, không phải do `input instanceof String text`. Biến `text` không bảo đảm đã được gán trong nhánh `if`.

**Mẹo nhớ:**

- Với `A && B`, để đến được `B`, `A` **phải đúng**.
- Với `A || B`, để đến được `B`, `A` **phải sai**.

Vì vậy, pattern được giới thiệu khi `true` bởi `instanceof` phù hợp với vế phải của `&&`; mẫu `o instanceof T t || ...` không cho phép dùng `t` ở vế phải như thể phép so khớp chắc chắn đã thành công.

### Dùng phủ định cùng `||` theo cách hợp lệ

Ta có thể viết một *guard clause* kiểm tra giá trị **không phải chuỗi hoặc là chuỗi trống**:

~~~java
static String requireText(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException("Cần chuỗi không trống");
    }

    // Ở đây điều kiện if đã sai: input là String và không blank.
    return text.strip();
}
~~~

Vì sao `text.isBlank()` ở vế phải `||` hợp lệ? Để đánh giá vế phải, biểu thức `!(input instanceof String text)` phải là `false`. Từ đó suy ra phép so khớp `String text` **thành công**.

Đây là một trường hợp quan trọng: **không phải mọi cách viết có `||` đều sai**. Phạm vi phụ thuộc giá trị logic nào làm cho phép so khớp chắc chắn thành công.

## 6. Phủ định `!` và nhánh kết thúc sớm

Xét biểu thức:

~~~java
if (!(value instanceof String text)) {
    // value KHÔNG khớp String; text không được sử dụng ở đây.
} else {
    // Phủ định sai => value khớp String.
    System.out.println(text.length());
}
~~~

Phép phủ định `!` đảo ý nghĩa `true` và `false` của điều kiện. Nhánh `else` ở đây là nơi biến `text` có thể được sử dụng.

### 6.1. Guard clause cho phép dùng biến sau `if`

Một mẫu thực tế, rõ ràng trong Java 17:

~~~java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }

    // Mọi đường chạy tới đây đều đã khớp String.
    text = text.strip();
    return text;
}
~~~

Nhánh `if` **không thể hoàn thành bình thường** vì luôn ném ngoại lệ khi đi vào. Nếu luồng chạy tới `text = text.strip()`, phép so khớp chắc chắn đã thành công. Do đó `text` thuộc phạm vi của phần còn lại trong khối.

Có thể dùng `return` thay cho `throw`:

~~~java
static int textLengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
~~~

So sánh với trường hợp **không kết thúc sớm**:

~~~java
static void printIfText(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Không phải chuỗi");
    }

    // Sai nếu bỏ comment: nhánh if có thể chạy xong rồi đi tiếp.
    // System.out.println(text.length());
}
~~~

Chỉ đảo điều kiện thành `!`, nhưng **không có `throw`/`return` hoặc một cấu trúc đảm bảo thoát**, chưa đủ để mở phạm vi biến sang phần phía sau.

### 6.2. Sơ đồ luồng điều khiển

~~~text
                    input instanceof String text?
                             /          \
                         true            false
                          |                |
                 text được gán        text chưa được gán
                          |                |
                 dùng text hợp lệ    không dùng được text

  if (!(...)) throw ...;           // Nhánh thất bại bị chặn.
  dùng text ở đây                 // Chỉ còn đường đã khớp.
~~~

Java suy luận phạm vi **từ các đường chạy có thể đi đến một dòng lệnh**, không dựa vào việc ta hy vọng giá trị đầu vào thường là chuỗi.

## 7. Toán tử ba ngôi `?:` và phạm vi của biến

Pattern variable có thể dùng ở nhánh tương ứng trong một biểu thức điều kiện:

~~~java
static String label(Object value) {
    return value instanceof String text
            ? text.strip()
            : "Không phải chuỗi";
}
~~~

Nhánh sau dấu `?` chỉ được đánh giá khi điều kiện so khớp là `true`, nên `text` có thể sử dụng. Nhánh sau dấu `:` không được bảo đảm như vậy:

~~~java
// Sai: tại nhánh false, pattern chưa khớp.
// String label = value instanceof String text
//         ? "Chuỗi"
//         : text.toUpperCase();
~~~

Với điều kiện phủ định, phạm vi tương ứng có thể nằm ở nhánh sau dấu `:`:

~~~java
static String normalizedOrDefault(Object value) {
    return !(value instanceof String text)
            ? "N/A"
            : text.strip();
}
~~~

**Lưu ý:** toán tử ba ngôi không mặc định “đưa” biến pattern ra phạm vi của các câu lệnh tiếp theo, bởi bản thân biểu thức có thể hoàn thành qua những nhánh khác nhau.

## 8. Với `while` và `for`: phạm vi trong điều kiện và thân vòng lặp

Phạm vi của biến pattern cũng có thể bao gồm thân vòng lặp nếu điều kiện chứng minh phép so khớp thành công.

Ví dụ vòng lặp `while`:

~~~java
Object current = "Java";

while (current instanceof String text && !text.isEmpty()) {
    System.out.println(text);
    current = null; // Lần kiểm tra sau không còn khớp String.
}

// Không thể mặc định dùng text ở đây.
// System.out.println(text);
~~~

Trong mỗi lần thân vòng lặp chạy, `current` phải khớp kiểu `String`, nên `text` hợp lệ. Sau vòng lặp, không thể suy ra lần kiểm tra cuối cùng đã khớp; vì vậy, không mặc định dùng được `text`.

Đối với vòng `for` cơ bản cũng có nguyên tắc tương tự:

~~~java
Object current = "data";

for (; current instanceof String text && !text.isBlank(); current = null) {
    System.out.println(text.toUpperCase());
}
~~~

Nhờ điều kiện `instanceof` ở phần giữa, `text` có thể được sử dụng ở phần cập nhật và thân vòng lặp ở những vị trí được Java xác nhận chắc chắn đã khớp. Ví dụ chỉ dùng `current` ở phần cập nhật để kết thúc đơn giản. Không nên giả định `text` có phạm vi ở **mọi** phần của câu lệnh `for`, đặc biệt là phần khởi tạo đứng trước điều kiện.

## 9. Phạm vi biến và trùng tên

Một lợi ích của *flow scoping* là tên pattern variable có thể được dùng lại trong các nhánh độc lập, miễn là **không có hai khai báo trùng tên cùng thuộc phạm vi xung đột**.

### 9.1. Được dùng lại tên sau khi phạm vi cũ đã kết thúc

~~~java
static void printTwo(Object first, Object second) {
    if (first instanceof String text) {
        System.out.println("A: " + text);
    }

    if (second instanceof String text) {
        System.out.println("B: " + text);
    }
}
~~~

Hai lần khai báo `text` ở hai biểu thức `instanceof` riêng biệt là hợp lệ trong cấu trúc này, vì biến pattern của nhánh `if` đầu **không thuộc phạm vi** biểu thức `if` thứ hai.

### 9.2. Không được che khuất một biến cục bộ đang có phạm vi

~~~java
static void conflict(Object value) {
    String text = "đã có";

    // Sai: biến local text đã nằm trong phạm vi này.
    // if (value instanceof String text) {
    //     System.out.println(text);
    // }
}
~~~

Để sửa, hãy đổi tên pattern variable:

~~~java
static void noConflict(Object value) {
    String text = "đã có";
    if (value instanceof String parsedText) {
        System.out.println(parsedText);
    }
    System.out.println(text);
}
~~~

### 9.3. Không khai báo cùng một tên pattern ở hai vế kết hợp

Ví dụ sau **không hợp lệ**:

~~~java
Object a = "A";
Object b = "B";

// Sai: hai pattern cùng khai báo tên s trong biểu thức kết hợp.
// if ((a instanceof String s) && (b instanceof String s)) {
//     System.out.println(s);
// }
~~~

Sử dụng tên khác nhau nếu cần hai đối tượng:

~~~java
if (a instanceof String first && b instanceof String second) {
    System.out.println(first + " - " + second);
}
~~~

Ví dụ đúng vì `first` và `second` là hai biến pattern khác tên, được xác nhận phù hợp trên đường chạy tới thân `if`.

## 10. Gán lại biến pattern và lambda: `effectively final`

Một biến pattern **có thể gán lại** không có nghĩa nó luôn được bắt (*capture*) vào lambda. Java yêu cầu biến cục bộ được dùng từ lambda phải là `final` hoặc **effectively final**, tức là không bị gán lại sau lần khởi tạo theo quy tắc của ngôn ngữ.

Trường hợp hợp lệ:

~~~java
static Runnable printer(Object value) {
    if (value instanceof String text) {
        return () -> System.out.println(text);
    }
    return () -> System.out.println("Không phải chuỗi");
}
~~~

Biến `text` không bị gán lại, nên đáp ứng điều kiện effectively final.

Ngược lại:

~~~java
static Runnable invalidPrinter(Object value) {
    if (value instanceof String text) {
        text = text.strip();

        // Sai: text đã bị gán lại, không còn effectively final.
        // return () -> System.out.println(text);
    }
    return () -> {};
}
~~~

Mặc dù việc `text = text.strip()` tự nó **hợp lệ**, phép gán đó khiến `text` không còn phù hợp để được lambda capture.

Cách làm rõ ràng hơn:

~~~java
static Runnable normalizedPrinter(Object value) {
    if (value instanceof String text) {
        String normalized = text.strip();
        return () -> System.out.println(normalized);
    }
    return () -> System.out.println("Không phải chuỗi");
}
~~~

Biến `normalized` chỉ nhận một giá trị và không bị gán lại, nên lambda có thể sử dụng nó. Cách này cũng tách bạch **đối tượng được kiểm tra ban đầu** và **giá trị đã biến đổi**.

## 11. Ví dụ hoàn chỉnh: scope, guard clause và gán lại

Tạo tệp **`PatternScopeDemo.java`** với nội dung dưới đây. Chương trình chỉ dùng API Java SE 17 ổn định, không dùng preview:

~~~java
public class PatternScopeDemo {
    static String describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            // Biến pattern có thể gán lại trong Java 17.
            text = text.strip();
            return "Chuỗi: " + text;
        }

        if (input instanceof Integer number) {
            return "Số nguyên: " + number;
        }

        return "Không hỗ trợ hoặc chuỗi trống";
    }

    static String requireText(Object input) {
        if (!(input instanceof String text)) {
            throw new IllegalArgumentException("Cần giá trị String");
        }

        // Hợp lệ ngoài if vì đường không khớp đã thoát.
        String normalized = text.strip();
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("Chuỗi không được trống");
        }

        return normalized;
    }

    static String compactLabel(Object input) {
        return input instanceof String text
                ? text.toUpperCase()
                : "OTHER";
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java 17  "));
        System.out.println(describe(42));
        System.out.println(describe("  "));
        System.out.println(requireText("  ready  "));
        System.out.println(compactLabel("pattern"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~shell
javac --release 17 PatternScopeDemo.java
java PatternScopeDemo
~~~

Kết quả dự kiến:

~~~text
Chuỗi: Java 17
Số nguyên: 42
Không hỗ trợ hoặc chuỗi trống
ready
PATTERN
~~~

Những điểm cần đọc trong chương trình:

1. Trong `describe`, `text` chỉ được dùng sau khi kiểm tra `input instanceof String text` thành công; dấu `&&` giúp dùng `text.isBlank()` ngay ở điều kiện.
2. Phép gán `text = text.strip()` là hợp lệ, và chỉ ảnh hưởng biến pattern trong phạm vi đó.
3. Nhánh `Integer number` dùng một pattern variable độc lập; không liên quan tới `text` ở nhánh trên.
4. Trong `requireText`, nếu phép so khớp thất bại, `throw` chấm dứt đường chạy. Sau `if`, `text` chắc chắn được gán và được phép sử dụng.
5. Trong `compactLabel`, biến pattern chỉ xuất hiện ở nhánh tương ứng của toán tử `?:`.

## 12. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `s` trong `else` của `if (o instanceof String s)`. | `else` chạy khi phép so khớp thất bại. | Đọc biến gốc, xử lý trường hợp khác hoặc viết nhánh phủ định phù hợp. |
| Dùng `s` sau một `if` có nhánh không khớp vẫn tiếp tục. | Tại dòng sau, `s` chưa chắc đã được gán. | Dùng `s` trong nhánh khớp hoặc viết guard clause thoát sớm. |
| `o instanceof String s || s.isEmpty()`. | Vế phải `||` được đánh giá khi vế trái false. | Dùng `&&`, hoặc phủ định có chủ đích như `!(o instanceof String s) || s.isEmpty()`. |
| Gán `s = 123` khi `s` là `String`. | Gán không tương thích kiểu. | Gán giá trị thuộc kiểu hợp lệ hoặc tạo biến khác. |
| Gán lại `s` rồi capture `s` trong lambda. | Không còn effectively final. | Tạo biến mới không gán lại để lambda capture. |
| Khai báo pattern `s` trùng tên biến cục bộ còn phạm vi. | Xung đột tên; pattern không được che khuất local variable ấy. | Đổi tên pattern hoặc tổ chức lại khối mã. |
| Nghĩ rằng `value instanceof String s` làm `value` trở thành biến kiểu `String`. | Pattern tạo biến **mới** `s` chứ không thay đổi kiểu khai báo của `value`. | Dùng `s` khi cần phương thức của `String`. |
| Nghĩ rằng pattern `s` luôn khác `null` sau bất kỳ câu lệnh nào. | `s` có thể bị gán lại, kể cả gán `null`. | Hạn chế gán lại tùy tiện, dùng biến chuẩn hóa rõ ràng. |

### Trường hợp cần tránh thêm: kiểm tra kiểu đã chắc chắn ở compile time

Java 17 không cho một phép kiểm tra pattern `instanceof` vô điều kiện khi kiểu biểu thức nguồn đã là subtype của kiểu pattern đích:

~~~java
String value = "Java";

// Sai trên Java 17: value đã có kiểu String.
// if (value instanceof String text) {
//     System.out.println(text);
// }

// Dùng trực tiếp value:
System.out.println(value.length());
~~~

Trong ví dụ cần kiểm tra kiểu động, hãy dùng giá trị có kiểu tĩnh rộng hơn, chẳng hạn `Object`, interface chung hoặc lớp cha thích hợp. Đây là quy tắc hiện hành của bản Java 17 chính thức, không nên sao chép ví dụ preview cũ.

## 13. Cách lựa chọn: gán lại hay tạo biến mới?

Giả sử pattern đã khớp và cần chuẩn hóa chuỗi:

**Cách 1 — gán lại trực tiếp:**

~~~java
if (input instanceof String text) {
    text = text.strip();
    process(text);
}
~~~

Phù hợp nếu phạm vi ngắn, không cần giá trị ban đầu và không cần dùng `text` trong lambda.

**Cách 2 — tạo biến kết quả mới:**

~~~java
if (input instanceof String text) {
    String normalized = text.strip();
    process(normalized);
}
~~~

Phù hợp nếu muốn giữ nguyên giá trị tham chiếu ban đầu, cần phân biệt dữ liệu thô với dữ liệu đã chuẩn hóa, hoặc chuẩn bị dùng biến trong lambda. Cách thứ hai thường giúp người đọc dễ theo dõi hơn khi logic xử lý dài.

> Hai mẫu trên giả định có phương thức `process(String)` trong ngữ cảnh ứng dụng. Chúng là đoạn minh họa, không phải các chương trình độc lập.

Không nên kéo dài chuỗi điều kiện chỉ để sử dụng được biến pattern ở một vị trí xa. Đối với logic phức tạp, hãy tách phương thức và đặt tên rõ ràng, vừa thể hiện điều kiện đã kiểm tra vừa tránh xung đột phạm vi.

## 14. Tự luyện về phạm vi

Cho biến `Object input` chứa một giá trị bất kỳ, hãy dự đoán chỗ nào sử dụng được tên `text`:

**Tình huống A:**

~~~java
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
~~~

**Đáp án:** `text` hợp lệ ở vế phải `&&` và trong nhánh `if` khi toàn bộ điều kiện đúng.

**Tình huống B:**

~~~java
if (input instanceof String text || input == null) {
    // System.out.println(text); // Không hợp lệ.
}
~~~

**Đáp án:** `if` có thể chạy vì `input == null`, nên `text` không chắc đã được gán.

**Tình huống C:**

~~~java
if (!(input instanceof String text)) {
    return;
}
System.out.println(text);
~~~

**Đáp án:** `text` hợp lệ ở dòng cuối khi đoạn mã nằm trong một phương thức `void`; nhánh không khớp đã `return`, mọi đường chạy còn lại đều khớp.

**Tình huống D:**

~~~java
if (input instanceof String text) {
    text = text.toUpperCase();
    // Runnable action = () -> System.out.println(text);
}
~~~

**Đáp án:** phép gán lại hợp lệ; dòng tạo lambda bị chú thích là không hợp lệ vì `text` không còn effectively final.

**Tình huống E:**

~~~java
if (input instanceof String text) {
    System.out.println(text);
}
if (input instanceof Integer number) {
    System.out.println(number);
}
~~~

**Đáp án:** cả hai nhánh đều hợp lệ. `text` và `number` thuộc các phạm vi riêng phụ thuộc phép so khớp. Không biến nào tự động trở thành tên biến sử dụng được ở mọi vị trí sau hai `if`.

## 15. Tài liệu chính thức để tra cứu

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): mô tả tính năng chính thức và thay đổi loại bỏ `implicitly final` đối với pattern variables.
- [Java SE 17 Language Changes — Oracle](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html): mốc hoàn thiện pattern matching for `instanceof` ở Java 16 và phạm vi áp dụng khi dùng Java 17.
- [Java Language Specification 17 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): cơ sở của quy tắc phạm vi biến.
- [Java Language Specification 17 §6.3.1 — Scope for Pattern Variables in Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1): các quy tắc `&&`, `||`, `!`, toán tử ba ngôi và `instanceof`.
- [Java Language Specification 17 §6.3.2 — Scope for Pattern Variables in Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.2): quy tắc phạm vi với `if`, vòng lặp và các loại câu lệnh.
- [Java Language Specification 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): các quy tắc `final` và `effectively final`, liên quan việc lambda capture biến cục bộ.

**Nguyên tắc cốt lõi:** Trong Java 17, biến pattern **có thể gán lại nếu đúng kiểu**, nhưng chỉ **có phạm vi ở nơi luồng điều khiển chứng minh phép so khớp đã thành công**. Khi đọc code, hãy theo từng nhánh `true`/`false`, đặc biệt trước và sau `&&`, `||` và câu lệnh thoát sớm.
