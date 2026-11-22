# Phủ định điều kiện và nhánh thoát sớm trong phạm vi biến mẫu Java

## 1. Bài toán: sau một câu lệnh `if`, biến mẫu có còn dùng được?

Khi dùng *pattern matching for `instanceof`*, Java vừa kiểm tra kiểu runtime vừa tạo một **pattern variable** nếu kiểm tra thành công:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Khi biểu thức `value instanceof String text` là `true`, Java biết `value` là một `String` và giới thiệu biến `text` có kiểu `String`. Không cần viết ép kiểu `(String) value`. Tuy nhiên, biến `text` **không tự động có phạm vi trong toàn bộ method**: Java chỉ cho phép dùng tại những điểm mà compiler chứng minh pattern **chắc chắn đã khớp**.

Điều này đặc biệt hữu ích với cách tổ chức code theo **guard clause** (mệnh đề chặn): nếu dữ liệu không hợp lệ, thoát ngay bằng `return`, `throw` hoặc `continue`, sau đó viết luồng chính không cần thêm tầng `else`.

~~~java
static void printText(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    // Nếu thực thi tới đây, instanceof chắc chắn đã thành công.
    System.out.println(text.toUpperCase());
}
~~~

Đoạn trên là **phương thức minh họa đặt trong một class**, không phải chương trình `main` độc lập.

**Phiên bản:** pattern matching for `instanceof` xuất hiện dưới dạng preview ở Java 14/15 nhưng là **tính năng chính thức từ Java 16** (JEP 394), tiếp tục dùng được trên Java 17+ mà không cần `--enable-preview`. Trong bài này, mọi chương trình chạy đầy đủ đều được kiểm thử với **`javac --release 17`**; không dựa vào hành vi preview cũ.

## 2. Nguyên tắc: phạm vi dựa trên luồng điều khiển, không chỉ dấu ngoặc

Phạm vi của pattern variable trong Java được gọi là **flow scoping**. Tư duy đúng là hỏi:

> Tại vị trí chuẩn bị dùng `text`, compiler có chắc mọi đường chạy tới đó đều đã khớp pattern `String text` không?

Một bảng định hướng:

| Điều kiện | Khi nào `text` chắc chắn tồn tại? | Vị trí được dùng |
| --- | --- | --- |
| `value instanceof String text` | Khi điều kiện **true** | Nhánh `if` tương ứng và toán hạng cần điều kiện true |
| `!(value instanceof String text)` | Khi điều kiện **false** | Nhánh `else`; sau `if` nếu nhánh true không thể hoàn thành bình thường |
| `value instanceof String text && text.length() > 2` | Vế trái true mới chạy vế phải | Vế phải `&&` và nhánh true |
| `!(value instanceof String text) || text.isBlank()` | Vế trái false mới chạy vế phải, nghĩa là pattern đã khớp | Vế phải `||`; sau nhánh từ chối thoát hoàn toàn |
| `value instanceof String text || text.isBlank()` | Khi vế trái false, pattern **không khớp** | **Không hợp lệ** ở vế phải |
| `!(value instanceof String text) && text.isBlank()` | Khi vế trái true, pattern **không khớp** | **Không hợp lệ** ở vế phải |

Biến `text` không được tạo theo nghĩa “khai báo rồi có thể là `null`” trong nhánh không khớp. Nếu `value` không phải `String`, compiler **không cho phép tham chiếu** đến `text` tại nơi pattern chưa chắc chắn khớp. Đây là một kiểm tra **thời gian biên dịch**, không phải điều kiện cần xử lý bằng `NullPointerException`.

Với `value == null`, `value instanceof String text` là `false`, nên điều kiện phủ định `!(...)` là `true`; nhánh guard xử lý null giống mọi giá trị không phải `String`.

## 3. Phủ định `!` đảo nhánh nào đảm bảo có biến

So sánh hai cách:

**Cách trực tiếp — dùng biến bên trong nhánh true:**

~~~java
if (value instanceof String text) {
    System.out.println(text.strip());
} else {
    System.out.println("not-a-string");
}
~~~

Trong nhánh `else`, `text` không tồn tại. Nếu không có nhánh thoát sớm, sau toàn bộ `if/else` cũng không thể mặc định dùng `text`, vì vẫn có đường chạy từ trường hợp không khớp.

**Cách phủ định — nhánh true là trường hợp không khớp:**

~~~java
if (!(value instanceof String text)) {
    System.out.println("not-a-string");
    return;
}
System.out.println(text.strip());
~~~

Nhánh guard `if` thực thi khi **không khớp**, nên không được dùng `text` ở bên trong nhánh này. Nhưng lệnh `return` bảo đảm mọi đường đi không khớp đều đã thoát phương thức. Do vậy, phần code phía sau `if` chỉ có thể được thực thi trên đường **đã khớp pattern**, và `text` trở thành biến hợp lệ tại đó.

Phân tích luồng:

~~~text
        value instanceof String text ?
                    |
          +---------+----------+
          |                    |
        false                 true
          |                    |
  !(...) = true        !(...) = false
          |                    |
   nhánh if (guard)     bỏ qua nhánh if
   in thông báo                |
   return                 text đã khớp
          |                    |
     kết thúc             dùng text.strip()
~~~

Chính **khả năng hoàn thành bình thường của nhánh guard** quyết định biến có được giới thiệu sau `if` hay không. Đặc tả Java mô tả rằng câu lệnh `if (e) S` có thể giới thiệu biến mẫu được khớp khi `e` false ra phần code phía sau **nếu `S` không thể hoàn thành bình thường**.

Ví dụ có `System.out.println(...)` rồi **không `return`** là khác hoàn toàn:

~~~java
// Sai: nhánh không khớp vẫn chạy tiếp.
if (!(value instanceof String text)) {
    System.out.println("not-a-string");
}
System.out.println(text); // compile error: text không chắc đã được khớp
~~~

Lỗi nằm ở việc luồng không khớp vẫn có thể đến dòng cuối, chứ không phải vì `text` đang có giá trị `null`.

## 4. Nhánh thoát sớm: `return` và `throw`

### 4.1. `return` trong phương thức `void`

~~~java
static void check(Object value) {
    if (!(value instanceof String text)) {
        return;
    }
    System.out.println(text.length());
}
~~~

Đây là phương thức minh họa. `return` chặn đường đi không khớp và cho phép phần thân phía sau được đọc như một luồng xử lý `String` đã hợp lệ.

### 4.2. `return` một giá trị khi phương thức có kiểu trả về

~~~java
static int lengthOrDefault(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
~~~

Cú pháp `return -1;` phù hợp với kiểu trả về `int`; không thể dùng `return;` trống ở phương thức phải trả `int`. Logic phạm vi biến mẫu vẫn như nhau.

### 4.3. `throw` cũng ngăn nhánh hoàn thành bình thường

~~~java
static int requireTextLength(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected String");
    }
    return text.length();
}
~~~

Không chỉ `return`, một câu lệnh `throw` vô điều kiện trên đường không khớp cũng đảm bảo phần sau chỉ chạy nếu pattern đã khớp. Đây là cách thích hợp khi **đầu vào sai kiểu phải được báo lỗi** chứ không phải bỏ qua.

Lưu ý: nếu viết `if (!matched) { log(); if (flag) return; }` thì nhánh guard **có thể** hoàn thành bình thường khi `flag == false`. Do đó compiler không thể cho dùng biến mẫu phía sau. Điều kiện “nhánh không thể hoàn thành bình thường” áp dụng với **toàn bộ nhánh**, không phải chỉ có một lệnh `return` nằm đâu đó bên trong.

## 5. Chương trình Java 17+: kiểm chứng `return`, `throw` và `else`

Tạo file **`PatternGuardDemo.java`**:

~~~java
public class PatternGuardDemo {
    static void printText(Object value) {
        if (!(value instanceof String text)) {
            System.out.println("not-a-string");
            return;
        }
        System.out.println("text=" + text.strip());
    }

    static void printNonBlank(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            System.out.println("invalid");
            return;
        }
        System.out.println("accepted=" + text.strip());
        System.out.println("length=" + text.length());
    }

    static int lengthOrThrow(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Expected String");
        }
        return text.length();
    }

    static void printElse(Object value) {
        if (value instanceof String text) {
            System.out.println("matched=" + text);
        } else {
            System.out.println("no-match");
            return;
        }
        System.out.println("after-else=" + text.length());
    }

    public static void main(String[] args) {
        printText("  Java  ");
        printText(42);
        printNonBlank("  ");
        printNonBlank("Text");
        printNonBlank(null);
        System.out.println("checked-length=" + lengthOrThrow("Hello"));
        printElse("ABC");
        printElse(100);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc bản mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 PatternGuardDemo.java
java PatternGuardDemo
~~~

Stdout đã được kiểm tra:

~~~text
text=Java
not-a-string
invalid
accepted=Text
length=4
invalid
checked-length=5
matched=ABC
after-else=3
no-match
~~~

Giải thích các điểm quan trọng:

1. `printText("  Java  ")` khớp `String text`, bỏ qua nhánh guard, sau đó `strip()` bỏ khoảng trắng hai đầu và in `text=Java`.
2. `printText(42)` không khớp `String`, đi vào nhánh phủ định và `return`. Lệnh sử dụng `text` phía sau không chạy.
3. `printNonBlank("  ")` là một `String`, nhưng `text.isBlank()` đúng, nên guard từ chối; `printNonBlank("Text")` vượt qua guard và dùng `text` bên ngoài `if`.
4. `printNonBlank(null)` cũng bị từ chối. Do `instanceof` false cho `null` và `||` ngắn mạch, Java **không gọi** `text.isBlank()` trên đường không khớp.
5. `lengthOrThrow("Hello")` chứng minh `throw` đặt ở nhánh sai kiểu cũng cho phép dùng `text` phía sau.
6. `printElse("ABC")` minh họa biến `text` có thể dùng **sau toàn bộ `if/else`**: nhánh `if` đúng thì thực thi bình thường, nhánh `else` sai kiểu thì `return`. Với `100`, nhánh `else` in `no-match` và thoát.

Mặc dù ví dụ `printElse` dùng điều kiện **không phủ định**, nó dựa trên cùng quy tắc flow scoping: chỉ những đường đi đã khớp mới được đi đến điểm dùng biến.

## 6. Toán tử `&&` và `||` khi điều kiện có phủ định

Java sử dụng **short-circuit evaluation**: với `a && b`, chỉ xét `b` nếu `a` true; với `a || b`, chỉ xét `b` nếu `a` false. Flow scoping kết hợp với quy tắc này để bảo đảm biến mẫu luôn được sử dụng trên đường đã khớp.

### 6.1. Pattern khẳng định kết hợp `&&`

~~~java
if (value instanceof String text && text.length() >= 4) {
    System.out.println("long-text=" + text);
}
~~~

`text.length()` hợp lệ vì vế phải chỉ chạy khi `value instanceof String text` đã **true**. Nếu vế trái false thì vế phải không được đánh giá.

### 6.2. Pattern phủ định kết hợp `||`

~~~java
if (!(value instanceof String text) || text.isBlank()) {
    return;
}
System.out.println(text.strip());
~~~

Đây là một trong những cấu trúc guard có ích nhất:

- Khi **không phải String**, `!(...)` true → `||` short-circuit → không đánh giá `text.isBlank()` → thoát.
- Khi **là String**, `!(...)` false → phần phải của `||` được chạy và biến `text` chắc chắn đã khớp.
- Nếu String rỗng/trắng, `isBlank()` true → thoát.
- Nếu String không trắng, toàn bộ điều kiện false → không vào nhánh `if` → dòng sau có thể dùng `text`.

Ở đây việc dùng `text` bên trong vế phải **và** phía sau `if` đều hợp lệ, nhưng bởi **hai lý do flow scoping liên quan**: vế phải được chạy trên đường đã khớp; phần sau được chạy chỉ khi nhánh guard đã bị bỏ qua.

### 6.3. Hai cách kết hợp dễ gây lỗi

~~~java
// Sai: khi vế trái false, pattern KHÔNG khớp nhưng vế phải chạy.
if (value instanceof String text || text.isBlank()) {
    System.out.println("invalid");
}

// Sai: khi vế phủ định true, pattern KHÔNG khớp nhưng vế phải chạy.
if (!(value instanceof String text) && text.isBlank()) {
    System.out.println("invalid");
}
~~~

Cả hai là **mã cố ý lỗi biên dịch**, không đưa vào chương trình runnable. Compiler báo không tìm thấy biến `text` ở toán hạng phải.

Nhớ quy tắc gọn:

| Pattern ban đầu | Toán tử đúng để dùng biến ở vế phải |
| --- | --- |
| `value instanceof String text` | `&&` vì vế phải chỉ chạy khi pattern khớp |
| `!(value instanceof String text)` | `||` vì vế phải chỉ chạy khi phủ định false, tức pattern khớp |

Đổi `&&` thành `||` hoặc bỏ dấu `!` mà không xét lại luồng có thể khiến mã không biên dịch.

## 7. Guard trong vòng lặp: bỏ phần tử sai bằng `continue`

Với các phần tử cần lọc trong vòng lặp, thường không muốn kết thúc cả phương thức chỉ vì một phần tử không hợp lệ. Ta có thể dùng `continue` để bỏ qua vòng lặp hiện tại:

~~~java
for (Object value : values) {
    if (!(value instanceof String text) || text.isBlank()) {
        continue;
    }
    System.out.println(text.strip());
}
~~~

Khi nhánh guard kích hoạt, `continue` chuyển sang vòng lặp tiếp theo, không đi đến dòng sử dụng `text`. Do đó phần code còn lại trong **lần lặp hiện tại** biết `text` là `String` hợp lệ.

Không suy ra rằng `text` tiếp tục tồn tại sau khi vòng lặp đã kết thúc: đây là biến gắn với điều kiện kiểm tra trong vòng lặp, không phải biến được khai báo ở scope bao ngoài.

### Chương trình thứ hai: `continue` và kiểm tra `&&`

Tạo file **`PatternContinueDemo.java`**:

~~~java
import java.util.List;

public class PatternContinueDemo {
    static void printNonBlankStrings(List<Object> values) {
        for (Object value : values) {
            if (!(value instanceof String text) || text.isBlank()) {
                continue;
            }
            System.out.println("keep=" + text.strip());
        }
    }

    static String categorize(Object value) {
        if (value instanceof String text && text.length() >= 4) {
            return "long:" + text.length();
        }
        if (value instanceof String text) {
            return "short:" + text.length();
        }
        return "not-string";
    }

    public static void main(String[] args) {
        printNonBlankStrings(
                java.util.Arrays.asList("  Java  ", 17, " ", null, "OK"));
        System.out.println(categorize("Java"));
        System.out.println(categorize("Hi"));
        System.out.println(categorize(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 PatternContinueDemo.java
java PatternContinueDemo
~~~

Stdout đã kiểm tra:

~~~text
keep=Java
keep=OK
long:4
short:2
not-string
~~~

Trong `printNonBlankStrings`, các giá trị `17` và `null` không phải `String` nên bị bỏ qua mà không gọi `isBlank()`, còn `" "` khớp `String` nhưng bị bỏ qua vì trắng. Chỉ `"  Java  "` và `"OK"` được xử lý bằng `text.strip()`.

Trong `categorize`, biểu thức `text.length() >= 4` chỉ thực thi khi `instanceof` true. Có thể dùng lại tên `text` ở một `if` sau khi biến mẫu ở `if` trước không còn trong scope của đường đi đó; compiler dựa vào phạm vi thực tế chứ không cấm mọi tên pattern trùng nhau trong một phương thức.

## 8. Lỗi biên dịch: vùng nào không được dùng biến mẫu

Để nhìn thấy lỗi thật, tạo file **`PatternInvalidScope.java`** dưới đây. Đây là **bài thử cố ý không biên dịch**, phải tách khỏi hai file chạy thành công:

~~~java
class PatternInvalidScope {
    void incorrectNegatedBranch(Object input) {
        if (!(input instanceof String text)) {
            System.out.println(text); // ERROR: pattern không khớp
        }
    }

    void incorrectFallthrough(Object input) {
        if (!(input instanceof String text)) {
            System.out.println("reject"); // không thoát
        }
        System.out.println(text); // ERROR: có đường đi không khớp
    }

    void incorrectOr(Object input) {
        if (input instanceof String text || text.isBlank()) {
            System.out.println("invalid");
        }
    }

    void incorrectAnd(Object input) {
        if (!(input instanceof String text) && text.isBlank()) {
            System.out.println("invalid");
        }
    }
}
~~~

Chạy kiểm tra bằng compiler (kỳ vọng thoát mã lỗi):

~~~bash
javac --release 17 -encoding UTF-8 PatternInvalidScope.java
~~~

Kết quả kiểm thử: `javac` từ chối **bốn vị trí** dùng biến `text`, đều có chẩn đoán chính là `cannot find symbol` / `variable text`, lần lượt tại:

1. `incorrectNegatedBranch` — dùng `text` bên trong nhánh `!(instanceof)` đang true.
2. `incorrectFallthrough` — nhánh guard không có `return`/`throw` và có thể chạy tiếp tới `println(text)`.
3. `incorrectOr` — toán hạng phải của `||` chạy khi pattern khẳng định false.
4. `incorrectAnd` — toán hạng phải của `&&` chạy khi pattern phủ định true.

Thông báo chính xác có thể thay đổi nhẹ giữa các bản `javac`, nhưng lỗi phạm vi là **lỗi biên dịch** và không phụ thuộc giá trị mà ta định truyền ở thời gian chạy.

### Cách sửa bốn lỗi

- **Lỗi 1:** trong nhánh phủ định, dùng `input` để log thông tin đầu vào, không dùng `text`; hoặc chuyển logic dùng `text` sang nhánh `else`.
- **Lỗi 2:** nếu muốn phần code sau guard luôn xử lý `String`, thêm lệnh thoát **không điều kiện** ở nhánh sai kiểu; nếu không muốn thoát, đặt logic dùng `text` trong nhánh `else` tương ứng.
- **Lỗi 3:** nếu muốn kiểm tra `text` khi pattern khớp, thay `||` bằng `&&`; nếu muốn từ chối kiểu sai hoặc chuỗi trắng, phủ định pattern rồi dùng `||`.
- **Lỗi 4:** với phủ định pattern và kiểm tra phụ `text.isBlank()`, thay `&&` bằng `||`.

Đừng cố “sửa” lỗi bằng ép kiểu `(String) input` ở mọi chỗ: nếu input sai kiểu, cast có thể ném `ClassCastException`. Flow scoping được thiết kế chính để bảo đảm dùng đúng kiểu trên đường chạy hợp lệ.

## 9. Việc dùng `!` không có nghĩa là `text` bị phủ định thành `null`

Một vài phân biệt quan trọng:

**Pattern variable khác biến local thông thường.** Tên `text` được khai báo trong pattern `String text`, nhưng chỉ được phép dùng tại những vị trí compiler chứng minh pattern đã khớp. Biến này **không** được khởi tạo thành `null` trong nhánh thất bại.

**`null` không khớp type pattern của `instanceof`.** Với `value == null`, biểu thức `value instanceof String text` trả false; vì vậy guard phủ định sẽ chặn null tự nhiên. Nếu code vẫn cần chấp nhận null như một giá trị nghiệp vụ riêng, hãy xử lý nó bằng một nhánh rõ ràng.

**`!` đổi kết quả boolean, không đổi cách pattern được định nghĩa.** Viết `!(value instanceof String text)` nghĩa là "không phải String", nhưng `text` chỉ hợp lệ khi **biểu thức gốc `instanceof` đã khớp**. Do đó `text` xuất hiện trong nhánh false của biểu thức phủ định, hoặc phần sau một nhánh true thoát sớm.

**Một nhánh được xem là “không thể hoàn thành bình thường” theo quy tắc ngôn ngữ.** Lệnh `return` hoặc `throw` vô điều kiện là những trường hợp rõ nhất. Một lời gọi method có thể ném exception tùy runtime **không** đồng nghĩa với một `throw` rõ ràng ở compile time; không nên dựa vào việc “method kia lúc nào cũng ném” để giới thiệu biến mẫu phía sau.

**Pattern variable không phải `final` ngầm định.** Kể từ khi tính năng ổn định trong Java 16, pattern variable không còn bị bắt buộc ngầm `final`. Tuy nhiên, việc gán lại biến mẫu sau khi khớp thường không cần thiết để giải thích guard clause; có thể dùng biến mới với tên rõ nghĩa cho kết quả biến đổi để dễ đọc hơn. Không dùng quy tắc preview cũ rằng mọi pattern variable đều phải `final`.

## 10. Thiết kế guard clause có thể đọc được và dễ bảo trì

Khi phương thức yêu cầu đầu vào có kiểu cụ thể để xử lý phần chính, có hai lựa chọn:

**Lồng code vào nhánh true:**

~~~java
static void printLabel(Object value) {
    if (value instanceof String label) {
        if (!label.isBlank()) {
            System.out.println(label.strip());
        }
    }
}
~~~

**Phủ định + thoát sớm:**

~~~java
static void printLabel(Object value) {
    if (!(value instanceof String label) || label.isBlank()) {
        return;
    }
    System.out.println(label.strip());
}
~~~

Hai đoạn trên là **định nghĩa phương thức thay thế nhau**, không đặt đồng thời cùng chữ ký trong một class. Với luồng chủ yếu cần xử lý `String` hợp lệ, phiên bản thứ hai tránh thêm tầng lồng và giữ `label` ở phần xử lý chính.

Lựa chọn `return`, `throw` hay `continue` dựa trên **ý nghĩa nghiệp vụ**: dữ liệu sai có thể cần im lặng bỏ qua, trả kết quả mặc định, báo lỗi rõ ràng, hoặc chỉ bỏ qua một phần tử trong tập dữ liệu. Flow scoping hỗ trợ cả các cách đó; bản thân cú pháp không quyết định chính sách xử lý lỗi.

Khi có nhiều điều kiện, nên đặt kiểm tra kiểu trước và thêm điều kiện phụ sau bằng `||` trong guard phủ định, ví dụ `!(input instanceof String s) || s.isBlank()`. Tránh nhồi quá nhiều điều kiện phụ vào một biểu thức nếu nó trở nên khó đọc hoặc có side effect.

## 11. Checklist và bài tự kiểm tra

Trước khi dùng biến mẫu bên ngoài `if`:

1. Xác định **pattern gốc** `value instanceof Type name` khớp ở nhánh true hay false của điều kiện hiện tại.
2. Nếu có `!`, nhớ rằng **điều kiện phủ định false** mới chứng minh pattern gốc khớp.
3. Nếu dùng `&&` hoặc `||`, hỏi vế phải được chạy khi vế trái true hay false.
4. Nếu dùng `text` sau `if`, chứng minh **mọi đường đi không khớp đều đã rời khỏi vị trí đó** bằng `return`/`throw` (hoặc một cấu trúc điều khiển tương đương hợp lệ).
5. Kiểm tra `null`: với type pattern `instanceof`, null không khớp; short-circuit phải ngăn sử dụng biến khi không khớp.
6. Chạy `javac --release 17` khi kiểm tra mã Java 17+: các lỗi scope thường được phát hiện ngay ở compile time.

Câu hỏi ngắn:

| Câu hỏi | Đáp án |
| --- | --- |
| Sau `if (!(x instanceof String s)) return;` có dùng `s` được không? | **Có**, nếu các câu lệnh nằm trong khối mà `if` giới thiệu `s` sau nhánh không hoàn thành bình thường |
| Trong thân `if (!(x instanceof String s)) { ... }` có được gọi `s.length()` không? | **Không**, vì nhánh true là đường không khớp |
| Sau `if (!(x instanceof String s)) log();` có dùng `s` được không? | **Không**, nhánh không khớp có thể đi tiếp |
| Trong `x instanceof String s && s.isBlank()` có dùng `s` ở vế phải không? | **Có**, vì vế phải chỉ chạy khi pattern khớp |
| Trong `!(x instanceof String s) || s.isBlank()` có dùng `s` ở vế phải không? | **Có**, vì vế phải chỉ chạy khi phủ định false |
| Trong `x instanceof String s || s.isBlank()` có dùng `s` ở vế phải không? | **Không**, vì vế phải chạy khi pattern không khớp |
| `throw` trong nhánh phủ định có giúp `s` có phạm vi sau `if` không? | **Có**, nếu nhánh không thể hoàn thành bình thường |

## Tài liệu chính thức (quy tắc còn áp dụng)

- **Java Language Specification 26, §6.3.1** — phạm vi pattern variable trong `!`, `&&`, `||` và các biểu thức: https://docs.oracle.com/javase/specs/jls/se26/html/jls-6.html#jls-6.3.1
- **Java Language Specification 26, §6.3.2** — flow scoping của pattern variable qua câu lệnh `if` và các nhánh không hoàn thành bình thường: https://docs.oracle.com/javase/specs/jls/se26/html/jls-6.html#jls-6.3.2
- **Java Language Specification 17, §6.3.2.2** — quy tắc `if` cho Java 17: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.2.2
- **OpenJDK JEP 394 — Pattern Matching for instanceof**, ổn định từ Java 16: https://openjdk.org/jeps/394
- **Oracle Java SE 16 Language Changes**, xác nhận tính năng không cần preview và pattern variables không còn ngầm `final`: https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html