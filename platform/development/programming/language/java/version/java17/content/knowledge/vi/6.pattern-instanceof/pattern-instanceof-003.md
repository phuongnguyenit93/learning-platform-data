# Phạm vi biến dựa trên luồng điều khiển với pattern `instanceof` trong Java 17

## 1. Vì sao biến của pattern không có phạm vi giống biến cục bộ thông thường?

Java 17 hỗ trợ **pattern matching for `instanceof`** như một tính năng ổn định. Khi kiểm tra đối tượng có thuộc một kiểu cụ thể hay không, bạn có thể đồng thời khai báo một **biến pattern** để dùng đối tượng với kiểu đã được xác nhận.

Trước đây, ta thường viết:

~~~java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

Với Java 17, đoạn trên có thể rút gọn thành:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Biểu thức `value instanceof String text` vừa kiểm tra kiểu vừa giới thiệu biến `text`. Khi phép so khớp thành công, `text` có kiểu tĩnh `String` nên bạn gọi được `length()` mà không ép kiểu thủ công. Nếu `value` không phải `String` hoặc bằng `null`, phép so khớp không thành công và biến `text` không mang một giá trị có thể dùng.

Điều đáng chú ý là **vị trí khai báo không quyết định toàn bộ nơi có thể dùng biến `text`**. Trình biên dịch phân tích những đường đi mà chương trình có thể thực hiện và chỉ cho truy cập biến ở nơi phép so khớp **chắc chắn đã thành công**. Cơ chế đó gọi là **flow scoping** — *phạm vi biến dựa trên luồng điều khiển*.

> Quy tắc nhớ nhanh: chỉ dùng biến pattern trên những đường đi mà trình biên dịch xác định rằng pattern đã khớp. Đường đi chưa chứng minh điều đó thì biến không nằm trong phạm vi sử dụng.

Phạm vi dựa trên luồng điều khiển xuất hiện rõ nhất với `if`, `else`, `!`, `&&`, `||`, biểu thức điều kiện và các vòng lặp. Bài này tập trung vào các quy tắc có hiệu lực trong **Java 17**, không yêu cầu tính năng preview.

## 2. Trường hợp cơ bản: biến có phạm vi ở nhánh thành công

Xét một phương thức nhận `Object`:

~~~java
static void printLength(Object item) {
    if (item instanceof String text) {
        System.out.println("Length: " + text.length());
    } else {
        System.out.println("Not a String");
    }
}
~~~

Diễn biến:

1. Nếu `item` là một `String`, pattern khớp, biến `text` được gán tham chiếu đó và được dùng trong nhánh `if`.
2. Nếu `item` không phải `String`, hoặc là `null`, điều kiện sai và chương trình chạy nhánh `else`. Ở nhánh này, biến `text` **không có phạm vi**.
3. Sau toàn bộ câu lệnh `if/else`, thông thường không thể dùng `text` vì chương trình có thể đã đi qua nhánh không khớp.

Ví dụ **không biên dịch**:

~~~java
static void invalidScope(Object item) {
    if (item instanceof String text) {
        System.out.println(text.length()); // Hợp lệ
    } else {
        // System.out.println(text);     // Lỗi: text không trong phạm vi
    }

    System.out.println(text);             // Lỗi biên dịch
}
~~~

Lý do không phải do dấu ngoặc nhọn `{ }` của `if` đơn thuần: nếu điều kiện thất bại, `text` chưa từng được tạo từ một phép so khớp thành công. Vì thế Java không cho dùng nó ở cuối phương thức.

Sơ đồ đường đi:

~~~text
                    item instanceof String text
                             /       \
                         true         false
                          |             |
                  text dùng được      text không
                       trong if       dùng được
                          \             /
                           \           /
                            sau if/else
                      text không được bảo đảm
~~~

**Đối tượng `null`** luôn làm `instanceof String text` trả về `false`; toán tử `instanceof` không ném `NullPointerException` trong trường hợp này. Tuy nhiên, nếu bạn gọi một phương thức của `item` trước khi kiểm tra `null` thì lời gọi đó vẫn có thể ném ngoại lệ như bình thường.

## 3. Toán tử `&&`: vế phải có thể sử dụng biến từ vế trái

Trong Java, `&&` là phép AND có **đánh giá ngắn mạch** (*short-circuit*). Vế phải chỉ được đánh giá khi vế trái đúng. Vì thế, nếu vế trái là một pattern `instanceof`, vế phải được phép dùng biến pattern.

~~~java
static boolean isLongText(Object item) {
    return item instanceof String text && text.length() > 10;
}
~~~

Chương trình đánh giá theo thứ tự:

~~~text
item instanceof String text ?
    ├── false -> trả về false, KHÔNG gọi text.length()
    └── true  -> text đã khớp; đánh giá text.length() > 10
                  ├── false -> trả về false
                  └── true  -> trả về true
~~~

Đoạn sau cũng hợp lệ:

~~~java
if (item instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

Ở đây, có hai bảo đảm khi vào thân `if`: `item` khớp với `String` và `text` không chứa toàn khoảng trắng. Vế phải của `&&` dùng được `text` vì **để tới được vế phải, phép so khớp ở vế trái đã phải thành công**.

Điểm quan trọng là `&&` cho phép dùng biến ở **vế phải của biểu thức**, không có nghĩa biến đó luôn tồn tại sau cả câu lệnh:

~~~java
static void printNonBlank(Object item) {
    if (item instanceof String text && !text.isBlank()) {
        System.out.println(text);
    }

    // System.out.println(text); // Lỗi: chưa chắc pattern đã khớp
}
~~~

### So sánh với phép AND không ngắn mạch

Java cũng có toán tử `&` dùng với boolean. Toán tử này đánh giá **cả hai vế**, không chỉ khi vế trái đúng. Vì vậy, đừng thay `&&` bằng `&` trong tình huống cần vế phải dựa vào một biến pattern từ vế trái:

~~~java
// Không hợp lệ: vế phải có thể chạy ngay cả khi item không phải String
if (item instanceof String text & text.length() > 3) {
    System.out.println("Long text");
}
~~~

Giữ `&&` khi điều kiện sau phụ thuộc vào sự thành công của kiểm tra trước.

## 4. Toán tử `||`: vì sao cách viết tương tự lại lỗi?

Phép OR `||` cũng đánh giá ngắn mạch, nhưng **vế phải chỉ chạy khi vế trái sai**. Nếu vế trái là `item instanceof String text` thì vế phải chạy chính khi pattern **không khớp**; `text` không tồn tại trên đường đi này.

Ví dụ **lỗi biên dịch**:

~~~java
// Sai: text không nằm trong phạm vi ở vế phải của ||
if (item instanceof String text || text.isEmpty()) {
    System.out.println("Something matched");
}
~~~

Hãy so sánh trực tiếp:

| Biểu thức | Vế phải được chạy khi nào? | Vế phải có dùng được biến pattern? |
|---|---|---|
| `item instanceof String text && text.length() > 3` | Khi `instanceof` **đúng** | **Có** |
| `item instanceof String text || text.isEmpty()` | Khi `instanceof` **sai** | **Không** |

Điều này xuất phát từ **luồng đánh giá**, không phải quy tắc "biến pattern dùng được bên trong mọi biểu thức điều kiện".

Tuy nhiên, `||` **có thể** dùng với biến pattern nếu ta đảo điều kiện bằng `!` để trường hợp đi tới vế phải lại tương ứng với pattern khớp:

~~~java
static boolean isMissingOrBlank(Object item) {
    return !(item instanceof String text) || text.isBlank();
}
~~~

Giải thích:

- Nếu `item` không phải `String`, `!(item instanceof String text)` là `true`. Toán tử `||` trả về `true` ngay, không đánh giá `text.isBlank()`.
- Nếu `item` là `String`, phần phủ định là `false`. Lúc này vế phải được đánh giá, và `text` **đã được tạo bởi phép so khớp thành công**.

Đoạn mã này vừa hợp lệ, vừa là một ví dụ điển hình cho việc phạm vi của biến pattern **được suy ra qua các phép toán logic**.

## 5. Toán tử `!` làm đổi đường đi mà biến được bảo đảm

Hãy chú ý đến dấu phủ định:

~~~java
if (!(item instanceof String text)) {
    System.out.println("Not a String");
} else {
    System.out.println("String length: " + text.length());
}
~~~

Khi nhánh `if` chạy, biểu thức `instanceof` nằm trong dấu `!` đã trả về `false`. Vì vậy `text` không có phạm vi trong nhánh `if`. Khi nhánh `else` chạy, phép phủ định trả về `false`, tương ứng `instanceof` trả về `true`. Biến `text` **có phạm vi** trong nhánh `else`.

Có thể hình dung:

~~~text
if (!(item instanceof String text))
                |
                v
         Kết quả phủ định?
          /            \
       true            false
        |                |
  pattern không      pattern đã
  khớp              khớp
        |                |
   nhánh if          nhánh else
   không dùng        dùng text
   được text         được
~~~

Điều này khác với một biến khai báo ở đầu phương thức vốn luôn tồn tại từ vị trí khai báo đến cuối phạm vi từ vựng thích hợp. Biến pattern được đưa vào phạm vi **đúng tại những đường đi tương thích với kết quả so khớp**.

## 6. Guard clause: dùng biến pattern ở các câu lệnh phía sau

*Guard clause* là một nhánh kiểm tra điều kiện không hợp lệ rồi thoát sớm khỏi phương thức bằng `return` hoặc `throw`. Kết hợp với phủ định `!`, nó cho phép dùng biến pattern ở phần mã **sau câu lệnh `if`**.

~~~java
static int requireLength(Object item) {
    if (!(item instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }

    // Đến đây chắc chắn item instanceof String đã khớp.
    return text.length(); // Hợp lệ trong Java 17
}
~~~

Lập luận của trình biên dịch:

1. Nếu pattern không khớp, điều kiện `if` đúng và chương trình ném ngoại lệ. Đường đi này **không thể tiếp tục** tới `return text.length()`.
2. Nếu chương trình đi được tới câu lệnh `return`, nhánh ném ngoại lệ đã không chạy; điều đó đồng nghĩa pattern phải khớp.
3. Vì vậy biến `text` nằm trong phạm vi ở phần tiếp theo của phương thức.

Tương tự, có thể sử dụng `return`:

~~~java
static String requireText(Object item) {
    if (!(item instanceof String text)) {
        return "Input is not text";
    }

    return "Input: " + text.strip();
}
~~~

Nhánh `return` đầu tiên kết thúc lời gọi. Dòng cuối chỉ được thực thi nếu `text` đã khớp, nên đoạn mã hợp lệ.

### Tại sao không thể bỏ `return`/`throw`?

Ví dụ **không hợp lệ**:

~~~java
static void badGuard(Object item) {
    if (!(item instanceof String text)) {
        System.out.println("Not text");
    }

    System.out.println(text.length()); // Lỗi biên dịch
}
~~~

Nhánh `if` trong ví dụ này chỉ in thông báo rồi **tiếp tục chạy**. Do đó dòng cuối vẫn có thể nhận `item` không phải `String`. Trình biên dịch không cho phép dùng `text` ở đó.

Yếu tố quyết định không phải tên "guard", mà là **việc mọi đường đi còn tiếp tục đều bảo đảm phép so khớp thành công**.

### Guard kết hợp `||`

Một mẫu thường gặp trong code xử lý đầu vào:

~~~java
static String requireNonBlankText(Object item) {
    if (!(item instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(
                "Expected a non-blank String");
    }

    return text.strip();
}
~~~

Khi rời khỏi `if` mà không ném ngoại lệ, cả hai điều kiện từ chối đều sai. Nghĩa là `item` đã khớp `String text` và `text` không blank. `text` vừa được dùng hợp lệ ở vế phải `||`, vừa còn trong phạm vi sau guard.

Ngược lại, **không được dùng `text` bên trong thân `if` này** nếu không có một kiểm tra bổ sung: thân `if` có thể chạy chỉ vì `item` không phải `String`, lúc đó pattern chưa hề khớp.

## 7. Phạm vi biến trong biểu thức điều kiện `? :`

Toán tử điều kiện dạng `condition ? valueIfTrue : valueIfFalse` chọn một trong hai nhánh dựa trên giá trị boolean. Vì thế biến pattern có thể được dùng ở nhánh mà kết quả kiểm tra kiểu bảo đảm thành công.

~~~java
static String display(Object item) {
    return item instanceof String text
            ? "Text: " + text.strip()
            : "Other value";
}
~~~

Ở nhánh sau dấu `?`, phép `instanceof` đã đúng, nên có thể dùng `text`. Ở nhánh sau dấu `:`, phép kiểm tra thất bại, vì vậy không thể dùng `text`:

~~~java
// Không hợp lệ: nhánh thứ ba chạy khi instanceof là false
String label = item instanceof String text
        ? "Text: " + text
        : text.toString();
~~~

Biểu thức có phủ định thì hướng đảm bảo sẽ thay đổi:

~~~java
String label = !(item instanceof String text)
        ? "Not a String"
        : text.toUpperCase();
~~~

Tại nhánh thứ ba của biểu thức cuối, phần phủ định là `false`, nghĩa là `item instanceof String text` thực sự đã khớp.

Biến pattern không trở thành biến bên ngoài toàn bộ biểu thức chỉ vì nó xuất hiện trong một nhánh `? :`.

## 8. Phạm vi trong vòng lặp `while`

Điều kiện của `while` được đánh giá trước mỗi lượt lặp. Nếu điều kiện là một pattern `instanceof`, **mỗi lần vào thân vòng lặp** đều tương ứng với một phép so khớp thành công.

~~~java
static int countStringStages(Object current) {
    int stages = 0;

    while (current instanceof String text) {
        stages++;
        System.out.println("Text stage: " + text);
        current = text.length();
    }

    return stages;
}
~~~

Nếu gọi `countStringStages("Java")`:

1. Lần kiểm tra đầu, `current` là `String`, `text` nhận giá trị `"Java"`; thân vòng lặp chạy một lần.
2. Trong thân vòng lặp, `current` được gán thành số nguyên `4` (autobox thành `Integer` vì biến có kiểu `Object`).
3. Lần kiểm tra tiếp, `current` là `Integer` nên pattern `String` không khớp và vòng lặp kết thúc.

Kết quả trả về là `1`. Biến `text` **có phạm vi bên trong thân `while`**, nhưng **không có phạm vi sau vòng lặp**, vì vòng lặp có thể chấm dứt khi pattern thất bại hoặc không chạy lần nào.

~~~java
while (current instanceof String text) {
    System.out.println(text.length()); // Hợp lệ
    current = text.length();
}

// System.out.println(text); // Lỗi: ngoài phạm vi
~~~

Quy tắc tương tự xuất hiện khi điều kiện vòng lặp kết hợp `instanceof` và `&&`:

~~~java
while (current instanceof String text && !text.isEmpty()) {
    System.out.println(text);
    current = text.substring(1);
}
~~~

Ở đây, mỗi lần vào thân vòng lặp đều bảo đảm `current` là chuỗi **không rỗng**. Lệnh `substring(1)` làm chuỗi ngắn dần nên với đầu vào là một chuỗi hữu hạn, vòng lặp sẽ kết thúc.

## 9. Tên biến và những phạm vi không chồng lấn

Java tránh tình trạng một biến pattern bị "đầu độc" (*poisoning*) chỉ vì tên của nó đã xuất hiện trong một phép `instanceof`. Khi hai pattern có những miền phạm vi **không chồng lấn**, bạn có thể tái sử dụng cùng tên biến.

~~~java
static void inspect(Object value) {
    if (value instanceof String data) {
        System.out.println("String: " + data.length());
    }

    if (value instanceof Integer data) {
        System.out.println("Integer: " + data.intValue());
    }
}
~~~

Ở hai câu lệnh `if` độc lập này, các miền sử dụng `data` không chồng lấn; `data` ở nhánh thứ nhất có kiểu `String`, còn `data` ở nhánh thứ hai có kiểu `Integer`.

Ngược lại, không thể khai báo hai biến trùng tên **đang cùng nằm trong phạm vi sử dụng**:

~~~java
static void collision(Object value) {
    if (value instanceof String text) {
        // String text = "another"; // Lỗi: trùng tên với biến pattern
        System.out.println(text);
    }
}
~~~

Điều này cho thấy flow scoping xác định **nơi biến pattern có hiệu lực**; tại nơi đó, quy tắc tên biến và xung đột khai báo vẫn áp dụng.

Nên ưu tiên tên có nghĩa, ví dụ `customer`, `message` hoặc `list`, thay vì luôn đặt `s` hoặc `x`. Dù tái sử dụng tên trong hai vùng độc lập là hợp lệ, nếu làm mã khó đọc thì dùng hai tên khác nhau thường tốt hơn.

## 10. Ví dụ hoàn chỉnh có thể biên dịch bằng Java 17

Tạo thư mục `src/demo` và tệp `src/demo/FlowScopeDemo.java`, nội dung:

~~~java
package demo;

public final class FlowScopeDemo {
    private FlowScopeDemo() {
    }

    public static void main(String[] args) {
        Object[] inputs = {"  Java 17  ", "", 42, null};

        for (Object input : inputs) {
            System.out.println(describe(input));
        }

        System.out.println(
                "Validated: " + requireNonBlankText("  hello  "));

        System.out.println(
                "String stages: " + countStringStages("abc"));
    }

    private static String describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "Text: " + text.strip();
        }

        if (input instanceof String blankText) {
            return "Blank text";
        }

        if (input instanceof Integer number) {
            return "Integer: " + number;
        }

        return input == null ? "null" : "Other object";
    }

    private static String requireNonBlankText(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected a non-blank String");
        }

        return text.strip();
    }

    private static int countStringStages(Object current) {
        int stages = 0;

        while (current instanceof String text) {
            stages++;
            current = text.length();
        }

        return stages;
    }
}
~~~

Những điểm áp dụng trực tiếp:

- `describe` sử dụng `&&` để bảo đảm `text` đã khớp trước khi gọi `isBlank()`, rồi tiếp tục phân loại chuỗi trống và số nguyên.
- `requireNonBlankText` sử dụng `!`, `||` và guard ném ngoại lệ để biến `text` có phạm vi tại lệnh `return`.
- `countStringStages` dùng biến `text` trong thân `while`, nơi mỗi lần lặp đều đã thỏa `instanceof String`.
- Khi đầu vào là `null`, tất cả các phép `instanceof` tương ứng đều sai và `describe` chọn chuỗi `"null"`.

### Biên dịch và chạy

Trong thư mục gốc chứa `src`, chạy:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/FlowScopeDemo.java
java -cp out demo.FlowScopeDemo
~~~

Lệnh `javac` cần JDK 17 hoặc JDK mới hơn có hỗ trợ `--release 17`. Tùy chọn `-d out` đặt bytecode vào thư mục `out`, còn `java -cp out` chạy lớp theo tên package đầy đủ.

Đầu ra dự kiến:

~~~text
Text: Java 17
Blank text
Integer: 42
null
Validated: hello
String stages: 1
~~~

Để tự quan sát lỗi phạm vi, thử thêm `System.out.println(text);` ở cuối `describe`, bên ngoài mọi nhánh. Trình biên dịch sẽ từ chối vì tại vị trí đó không có một biến pattern tên `text` được bảo đảm khớp.

## 11. Bảng tra nhanh các tình huống flow scoping

Các ví dụ dưới đây giả sử `value` là một biểu thức kiểu `Object`.

| Tình huống | Nơi biến `s` dùng được | Giải thích |
|---|---|---|
| `if (value instanceof String s) { ... }` | Thân `if` | Thân chạy khi match đúng. |
| `if (value instanceof String s) { ... } else { ... }` | Thân `if`; không ở `else` | `else` ứng với match sai. |
| `if (!(value instanceof String s)) { ... } else { ... }` | Nhánh `else` | Phủ định đảo điều kiện. |
| `value instanceof String s && s.length() > 0` | Vế phải của `&&` | Vế phải chỉ chạy sau match đúng. |
| `value instanceof String s \|\| s.isEmpty()` | Không dùng được ở vế phải; lỗi | Vế phải chạy khi match sai. |
| `!(value instanceof String s) \|\| s.isEmpty()` | Vế phải của `\|\|` | Vế phải chạy khi phép phủ định sai, tức match đúng. |
| `if (!(value instanceof String s)) return;` | Những lệnh sau guard trong cùng phạm vi | Chỉ đường đi match đúng mới tiếp tục. |
| `while (value instanceof String s) { ... }` | Thân `while` | Mỗi lượt vào vòng lặp đều match đúng. |
| `value instanceof String s ? s.length() : 0` | Nhánh thứ hai của `? :` | Nhánh được chọn khi match đúng. |

**Ghi nhớ:** bảng diễn tả các vị trí thông dụng; toàn bộ quy tắc chính xác của Java được định nghĩa bằng việc một biểu thức **giới thiệu biến pattern khi đúng** hay **khi sai**, kết hợp luồng điều khiển của câu lệnh bao quanh. Không nên suy luận chỉ từ việc có cùng dấu ngoặc nhọn.

## 12. Các lỗi thường gặp và cách đọc nguyên nhân

### 12.1. Dùng biến sau `if` dù nhánh sai vẫn có thể tiếp tục

~~~java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
// System.out.println(text); // Lỗi
~~~

**Cách sửa:** đặt đoạn xử lý cần `text` vào nhánh khớp, hoặc đổi thành guard phủ định có `return`/`throw` khi nhánh không khớp.

### 12.2. Dùng biến ở vế phải `||` mà không phủ định

~~~java
// if (value instanceof String text || text.isBlank()) { ... }
~~~

**Cách sửa:** nếu mục tiêu là "không phải String **hoặc** chuỗi rỗng", viết `!(value instanceof String text) || text.isBlank()`. Nếu muốn kiểm tra "là String **và** chuỗi không rỗng", viết `value instanceof String text && !text.isBlank()`.

### 12.3. Cho rằng `instanceof` luôn cho phép tiếp tục sau kiểm tra

~~~java
if (!(value instanceof String text)) {
    System.out.println("Invalid value");
}
// System.out.println(text.length()); // Lỗi
~~~

**Cách sửa:** khi giá trị không hợp lệ, chấm dứt đường đi bằng `return` hoặc `throw`, nếu contract cho phép. In log rồi tiếp tục không đủ để chứng minh `text` đã khớp.

### 12.4. Nhầm `null` với một giá trị khớp

~~~java
Object value = null;

if (value instanceof String text) {
    // Không chạy; text không nhận null ở nhánh này.
    System.out.println(text.length());
}
~~~

**Cách sửa:** nếu `null` là một trường hợp cần xử lý, kiểm tra hoặc phản hồi nó theo hợp đồng riêng. Trong Java 17, pattern `instanceof` trên `null` không khớp.

### 12.5. Nhầm pattern `instanceof` với pattern `switch` của Java mới hơn

Java 17 đã ổn định pattern matching cho `instanceof`. Nhưng các dạng pattern matching cho `switch` trong Java 17 thuộc **preview feature**, có yêu cầu bật preview khi dùng. Bài này cố ý sử dụng `instanceof`, `if` và các toán tử logic hiện hành của Java 17; không cần cú pháp `switch` preview để thực hành flow scoping.

### 12.6. Dùng kiểu kiểm tra khi biểu thức đã có kiểu tĩnh chính xác

Khi đối tượng đã có kiểu tĩnh `String`, bạn thường không cần kiểm tra `instanceof String text` nữa. Ví dụ, nếu tham số là `String input`, hãy dùng trực tiếp `input` hoặc kiểm tra `null` phù hợp. Pattern `instanceof` hữu ích nhất tại ranh giới làm việc với `Object`, kiểu cha hoặc interface mà có thể gặp nhiều kiểu hiện thực.

## 13. Bài tập thực hành

### Bài tập 1 — Đoán vị trí hợp lệ

Giả sử `Object input`:

~~~java
if (input instanceof String s && s.length() > 3) {
    System.out.println(s);
} else {
    // Có được dùng s ở đây không?
}
// Có được dùng s ở đây không?
~~~

Hãy giải thích từng vị trí dựa trên đường đi làm điều kiện `instanceof` đúng hoặc sai.

### Bài tập 2 — Sửa lỗi `||`

Đoạn sau không hợp lệ:

~~~java
if (input instanceof String s || s.isBlank()) {
    System.out.println("Invalid");
}
~~~

Hãy sửa để điều kiện có nghĩa: **giá trị đầu vào không phải `String` hoặc là một chuỗi trống/blank**. Sau đó giải thích vì sao vế phải của `||` được dùng biến `s` trong cách viết mới.

### Bài tập 3 — Tái cấu trúc guard

Từ đoạn mã:

~~~java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.strip());
    } else {
        throw new IllegalArgumentException("Not a String");
    }
}
~~~

Hãy viết lại với `if (!(input instanceof String text))` và một guard ném ngoại lệ để câu lệnh in ra được đưa **ra sau** `if`. Giải thích tại sao biến `text` vẫn có phạm vi.

### Bài tập 4 — Vòng lặp và dừng

Thêm vào phương thức:

~~~java
Object current = "abcd";
int count = 0;
while (current instanceof String s && !s.isEmpty()) {
    count++;
    current = s.substring(1);
}
System.out.println(count);
~~~

Dự đoán giá trị được in ra và giải thích điều gì xảy ra khi `current` trở thành chuỗi rỗng. Biến `s` có dùng được ở câu lệnh `println` sau vòng lặp không?

### Bài tập 5 — Đường đi của biểu thức điều kiện

Viết biểu thức `? :` trả về độ dài của chuỗi nếu `input` là `String`, ngược lại trả về `-1`. Sau đó thử sửa để dùng biến pattern ở nhánh `false` và giải thích vì sao phiên bản đó không hợp lệ.

### Đáp án gợi ý

1. `s` dùng được trong thân `if` và vế phải `&&`; không được bảo đảm ở `else` hoặc sau toàn bộ `if`.
2. Viết `if (!(input instanceof String s) || s.isBlank())`. Khi chạy vế phải, phủ định đã sai nên pattern đã khớp.
3. Viết guard `if (!(input instanceof String text)) { throw ...; }` rồi `System.out.println(text.strip());`. Nhánh không khớp không đi tới câu lệnh in.
4. Giá trị `count` là `4`. Khi chuỗi rỗng, điều kiện `!s.isEmpty()` sai và vòng lặp dừng. `s` không có phạm vi sau vòng lặp.
5. `input instanceof String s ? s.length() : -1`. Nhánh thứ ba chỉ chạy khi pattern không khớp, nên không thể dùng `s` ở nhánh đó.

## 14. Tư duy áp dụng trong mã nguồn thực tế

Flow scoping khuyến khích mã nguồn làm rõ quan hệ giữa **điều kiện** và **dữ liệu đã được xác nhận**. Khi đọc một nhánh:

- Với `&&`, hãy hỏi: **điều gì phải đúng để đánh giá vế phải?**
- Với `||`, hãy hỏi: **điều gì phải sai để đánh giá vế phải?**
- Với `!`, hãy nhớ kết quả đúng/sai của biểu thức ngoài bị đảo so với phép kiểm tra bên trong.
- Với guard `throw` hoặc `return`, hãy hỏi: **các đường đi không khớp còn có thể tới lệnh phía sau không?**
- Với vòng lặp, hãy hỏi: **điều kiện nào luôn đúng mỗi lần vào thân?** và **tại sao điều đó không còn chắc chắn sau vòng lặp?**

Nhờ phân tích theo cách đó, bạn có thể viết điều kiện ngắn gọn mà vẫn kiểm soát chính xác phạm vi của biến pattern. Đây là nền tảng quan trọng khi Java 17 xử lý dữ liệu thuộc nhiều kiểu, từ tham số `Object` đến các interface và hệ phân cấp đối tượng.

### Tài liệu tham khảo

- [Java Language Specification, Java SE 17 — Section 6.3, Scope of a Declaration (Pattern Variables)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3).
- [Java Language Specification, Java SE 17 — Section 15.20.2, Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
