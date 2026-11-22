# Tên biến và phạm vi hợp lệ của pattern variable trong Java

## 1. Pattern variable là gì và tên biến có ý nghĩa gì?

Khi dùng **pattern matching**, Java có thể vừa kiểm tra giá trị có khớp với một pattern hay không, vừa ràng buộc (bind) một biến có kiểu phù hợp để dùng ở những vị trí an toàn. Biến được khai báo bởi pattern gọi là **pattern variable** (biến mẫu).

Trong Java 17, tình huống cơ bản là *type pattern* của `instanceof`:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

Ở đây:

- `value` là biểu thức được kiểm tra, có kiểu tĩnh `Object`.
- `String` là kiểu cần khớp.
- `text` là **tên pattern variable**. Nó có kiểu `String` và được khởi tạo từ giá trị `value` khi type pattern khớp.
- Nhánh `if` chỉ chạy khi `value` thực sự khớp pattern, vì vậy `text` sử dụng được trong nhánh đó mà không cần ép kiểu tường minh.

Tên `text` có thể thay bằng `s`, `message`, `candidate` hoặc một định danh hợp lệ khác; **tên biến không ảnh hưởng điều kiện khớp**. Tuy nhiên, tên ảnh hưởng trực tiếp đến cách đọc chương trình, khả năng trùng tên và phạm vi tham chiếu. Hai câu hỏi phải phân biệt rõ:

1. **Tên có hợp lệ khi khai báo hay không?** Java kiểm tra quy tắc định danh và việc trùng tên với những khai báo đã ở trong phạm vi.
2. **Biến có nằm trong phạm vi hợp lệ tại vị trí sử dụng hay không?** Java phân tích luồng điều khiển để biết chắc pattern đã khớp trước khi cho tham chiếu biến.

Điểm thứ hai được gọi là **flow scoping**. Nó khác với phạm vi thuần túy dựa trên cặp dấu ngoặc nhọn của nhiều biến cục bộ thông thường.

## 2. Quy tắc đặt tên pattern variable

Pattern variable sử dụng quy tắc định danh của Java cho biến cục bộ. Vì vậy, nên đặt tên theo cùng quy ước với các biến Java bình thường:

- Phải là **Java identifier** hợp lệ; không được dùng từ khóa như `class`, `if`, `return`. Dấu gạch dưới đơn lẻ `_` không phải tên biến thông thường hợp lệ trong Java 17.
- Tên **phân biệt chữ hoa và chữ thường**: `text`, `Text` là hai định danh khác nhau.
- Có thể dùng chữ cái, chữ số ở vị trí phù hợp, `_` hoặc `$` theo quy tắc Java; tên không được bắt đầu bằng chữ số. Nên ưu tiên `camelCase` dễ đọc.
- Đặt tên diễn tả vai trò sau khi kiểm tra, ví dụ `customer`, `exception`, `response`. Các tên quá ngắn như `s` chấp nhận được trong phép kiểm tra nhỏ, nhưng không nên áp dụng máy móc cho đoạn xử lý phức tạp.
- Cần tránh trùng với biến cục bộ hoặc tham số đang còn trong phạm vi. Tên trùng với **field** có thể được phép do shadowing, nhưng dễ gây nhầm lẫn.

Ví dụ hợp lệ:

```java
if (value instanceof String userName) {
    System.out.println(userName);
}

if (value instanceof CharSequence charSequence) {
    System.out.println(charSequence.length());
}
```

Hai kiểm tra trên độc lập. Nếu `value` là `String`, cả hai pattern đều có thể khớp vì `String` hiện thực `CharSequence`. Kiểu được khai báo trong pattern quyết định phương thức có thể gọi qua pattern variable.

Ví dụ đặt tên không hợp lệ:

```java
// Sai: bắt đầu bằng chữ số
// if (value instanceof String 1name) { }

// Sai: từ khóa Java
// if (value instanceof String class) { }

// Trong Java 17, _ đơn lẻ không được dùng làm tên biến thông thường
// if (value instanceof String _) { }
```

Với các Java đời mới có tính năng *unnamed patterns*, dấu `_` có mục đích riêng và không tạo ra một biến tên `_` để tham chiếu; không đánh đồng nó với một pattern variable có tên trong Java 17.

## 3. Flow scoping: “chắc chắn đã match” thì mới được dùng biến

Với biến cục bộ truyền thống, dấu `{...}` thường quyết định phạm vi từ vựng. Với pattern variable, compiler còn xét **đường đi logic của biểu thức và luồng điều khiển**. Một pattern variable chỉ được phép sử dụng ở vị trí mà Java chứng minh được pattern tương ứng đã khớp và biến được khởi tạo.

```java
Object input = "Hello";

if (input instanceof String text) {
    System.out.println(text.length()); // Hợp lệ, text đã match
} else {
    // Không thể dùng text ở đây: pattern có thể thất bại
}

// Không thể dùng text ở đây: nhánh if có thể đã không chạy.
```

Tại thời điểm chạy, nếu `input` là `null` hoặc một `Integer`, pattern `String text` không khớp, nên không có giá trị `text` an toàn cho các nhánh đó.

**Bảng định hướng phạm vi cho Java 17:**

| Vị trí | Có dùng được biến mẫu `s`? | Lý do |
| --- | --- | --- |
| Trong nhánh đúng của `if (x instanceof String s)` | Có | Pattern khớp khi vào nhánh |
| Trong nhánh `else` của điều kiện trên | Không | Pattern có thể thất bại |
| Sau một `if` thông thường như trên | Không | Chương trình có thể đi qua nhánh không khớp |
| Vế phải của `x instanceof String s && s.length() > 0` | Có | `&&` chỉ đánh giá vế phải khi vế trái đúng |
| Vế phải của `x instanceof String s || s.length() > 0` | Không | `||` chỉ đánh giá vế phải khi vế trái sai |
| Sau `if (!(x instanceof String s)) return;` | Có | Đường đi không khớp đã kết thúc |
| Nhánh `true` của `x instanceof String s ? s.length() : 0` | Có | Nhánh đó chỉ chạy khi pattern khớp |
| Trong thân `while (x instanceof String s)` | Có | Mỗi lần vào thân vòng lặp phải khớp điều kiện |

Bảng mô tả những tình huống trực tiếp. Với biểu thức phức tạp hơn, cần xét chính xác luồng điều khiển, chứ không ghi nhớ đơn giản rằng biến “chỉ sống trong dấu ngoặc của `if`”.

## 4. `&&` và `||` quyết định phạm vi ở vế phải

### Phép `&&` hợp lệ

```java
Object value = "Java";

if (value instanceof String s && s.length() >= 3) {
    System.out.println(s.toUpperCase()); // JAVA
}
```

Java đánh giá vế trái trước. Chỉ khi `value instanceof String s` là `true` thì vế phải `s.length() >= 3` mới được đánh giá. Vì vậy `s` đã được khởi tạo khi dùng ở vế phải. Điều kiện bổ sung có thể sai, nhưng điều đó không phủ nhận việc pattern đã khớp trước đó.

Điều này tạo ra cách viết an toàn, ngắn gọn để kết hợp kiểm tra kiểu và kiểm tra nội dung:

```java
if (value instanceof String name && !name.isBlank()) {
    System.out.println("Valid: " + name.trim());
}
```

### Phép `||` có thể không hợp lệ

```java
// SAI: vế phải chạy khi instanceof ở vế trái trả về false.
// if (value instanceof String s || s.isEmpty()) {
//     System.out.println("...");
// }
```

Nếu `value` không phải `String`, phép kiểm tra vế trái sai, Java mới phải chạy `s.isEmpty()`. Nhưng pattern đã **không khớp**, nên `s` không ở trong phạm vi hợp lệ. Đây là **lỗi biên dịch**, không phải `NullPointerException` lúc chạy.

Phủ định có thể đổi luồng hợp lệ:

```java
if (!(value instanceof String s) || s.isEmpty()) {
    System.out.println("Not a non-empty String");
}
```

Trong biểu thức này, vế phải `s.isEmpty()` chỉ chạy khi `!(value instanceof String s)` là `false`, tức pattern bên trong đã khớp. Vì vậy dùng `s` ở vế phải là hợp lệ. Tuy nhiên, nhánh `if` cũng có thể chạy khi `value` không phải `String`, nên **không** suy ra rằng `s` có thể dùng tùy ý trong thân nhánh đó.

## 5. Toán tử phủ định `!`, nhánh `else` và guard clause

Phủ định đổi hướng nhánh chắc chắn thành công:

```java
static void printLength(Object input) {
    if (!(input instanceof String text)) {
        System.out.println("Not a String");
    } else {
        System.out.println(text.length()); // Hợp lệ
    }
}
```

Khi chạy vào `else`, điều kiện phủ định đã sai; do đó `input instanceof String text` đúng, và `text` đã được gán giá trị.

Một cách viết thường được dùng khi cần xử lý tiếp phía dưới là **guard clause**:

```java
static void process(Object input) {
    if (!(input instanceof String text)) {
        return;
    }

    // Tới đây, mọi đường đi còn lại đều đã match String.
    System.out.println(text.toUpperCase());
}
```

Ở đây, `text` có thể dùng **sau khối `if`**. Vì nhánh không khớp đã `return`, không tồn tại đường đi nào tiếp tục đến `System.out.println` mà pattern chưa khớp.

Đổi `return` thành `throw new IllegalArgumentException("Expected String");` cũng tạo một nhánh thoát. Nhưng nếu bỏ lệnh kết thúc và cho chương trình tiếp tục, compiler sẽ không còn bảo đảm biến đã match tại vị trí sau `if`.

**Lưu ý:** Việc biến có thể dùng sau guard không có nghĩa nó được khai báo và gán mặc định từ đầu phương thức. Pattern variable được khởi tạo ngay khi pattern khớp trong quá trình đánh giá `instanceof`; Java chỉ cho phép dùng nó ở các điểm an toàn theo luồng điều khiển.

## 6. Trùng tên: khi nào lỗi, khi nào được dùng lại?

### Không được trùng với biến cục bộ đang có scope

Ví dụ dưới đây không hợp lệ trong Java 17:

```java
static void invalid(Object input) {
    String text = "Existing";

    // SAI: đã có một local variable tên text trong phạm vi bên ngoài.
    // if (input instanceof String text) {
    //     System.out.println(text);
    // }
}
```

Tương tự, không thể khai báo một pattern variable có cùng tên với tham số phương thức đang ở trong cùng phạm vi:

```java
// SAI (minh họa, không biên dịch nếu bỏ comment):
// static void invalid(Object input, String text) {
//     if (input instanceof String text) {
//         System.out.println(text);
//     }
// }
```

Đổi tên pattern variable cho rõ vai trò:

```java
static void valid(Object input, String text) {
    if (input instanceof String candidate) {
        System.out.println(text + ": " + candidate);
    }
}
```

Cần kiểm tra cả khai báo trong những nhánh có **scope giao nhau**. Cặp dấu ngoặc nhọn ở thân `if` không làm cho mọi tên biến mẫu khai báo trong điều kiện trở nên độc lập với các biến cục bộ bên ngoài.

### Có thể tái sử dụng tên khi các phạm vi không chồng lấn

```java
static void printBoth(Object first, Object second) {
    if (first instanceof String s) {
        System.out.println("first=" + s);
    }

    if (second instanceof String s) {
        System.out.println("second=" + s);
    }
}
```

Hai pattern variable đều tên `s`, nhưng thuộc **hai phép kiểm tra độc lập**, phạm vi của `s` trong `if` đầu không kéo dài tới `if` thứ hai. Vì thế đoạn này hợp lệ và in lần lượt giá trị của hai đối tượng nếu chúng là `String`.

Tái sử dụng tên không có nghĩa hai biến là cùng một biến hoặc chia sẻ giá trị. Trong mã dài, nên cân nhắc đặt `firstText` và `secondText` để dễ theo dõi.

### Shadowing một field có thể hợp lệ

Khác với local variable, pattern variable có thể che khuất (*shadow*) field cùng tên:

```java
class Example {
    static String label = "FIELD";

    static void print(Object input) {
        if (input instanceof String label) {
            System.out.println(label.toUpperCase());
        }

        System.out.println(Example.label);
    }
}
```

Trong nhánh `if`, tên đơn `label` dùng pattern variable kiểu `String`. Để truy cập field bị che, dùng `Example.label`. Sau nhánh, nơi biến mẫu không còn trong phạm vi, `label` có thể lại tham chiếu field.

Mặc dù hợp lệ, shadowing dễ gây nhầm; thường nên chọn tên khác như `matchedLabel`.

## 7. Biến mẫu trong biểu thức ba ngôi và vòng lặp

### Biểu thức điều kiện `? :`

```java
static int lengthOrZero(Object value) {
    return value instanceof String s ? s.length() : 0;
}
```

Nhánh bên phải dấu `?` chỉ được đánh giá nếu pattern khớp, nên `s.length()` hợp lệ. Nhánh sau dấu `:` chạy khi pattern không khớp và **không được dùng `s`**.

### Vòng `while`

```java
static void loop(Object value) {
    while (value instanceof String s) {
        System.out.println(s);
        value = null; // Lần kiểm tra tiếp theo sẽ không match.
    }
}
```

Biến `s` được sử dụng hợp lệ trong thân vòng lặp, vì để vào thân vòng lặp phải match tại lần đánh giá điều kiện tương ứng. Sau vòng lặp, không được mặc định sử dụng `s`: vòng lặp có thể không chạy, hoặc kết thúc khi pattern thất bại.

**Không suy diễn về bộ nhớ:** quy tắc khởi tạo pattern variable không cam kết JVM tạo một đối tượng mới cho mỗi lần lặp; biến tham chiếu tới đối tượng đã match. JVM có thể tối ưu nội bộ tùy ngữ cảnh.

### Khi nào hai tên giống nhau gây xung đột?

Hãy xét **vị trí khai báo cùng những điểm dùng biến có thể đạt tới theo luồng điều khiển**, không chỉ đếm cặp ngoặc. Việc khai báo `s` trong hai nhánh ngắn, tách biệt thường hợp lệ; việc khai báo thêm `s` ngay trong nơi `s` đang được dùng sẽ bị lỗi trùng tên. Khi không chắc chắn, chọn tên khác và biên dịch bằng đúng phiên bản Java dự kiến.

## 8. Chương trình Java 17 chạy được: đặt tên, phạm vi, tái sử dụng tên

Lưu đoạn mã đầy đủ dưới đây thành file **`PatternScopeDemo.java`**:

```java
public class PatternScopeDemo {
    static String label = "FIELD";

    static void inspect(Object input) {
        if (input instanceof String label && !label.isBlank()) {
            System.out.println("if: " + label.toUpperCase());
        } else {
            System.out.println("not nonblank text");
        }

        if (input instanceof Integer number) {
            System.out.println("integer=" + number);
        }
    }

    static void afterGuard(Object input) {
        if (!(input instanceof String text)) {
            System.out.println("skip");
            return;
        }

        System.out.println("length=" + text.length());
    }

    static void reuse(Object left, Object right) {
        if (left instanceof String s) {
            System.out.println("first=" + s);
        }

        if (right instanceof String s) {
            System.out.println("second=" + s);
        }
    }

    public static void main(String[] args) {
        inspect("Java");
        inspect("   ");
        inspect(42);
        afterGuard("abc");
        afterGuard(null);
        reuse("left", "right");
        System.out.println("field=" + label);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 PatternScopeDemo.java
java PatternScopeDemo
```

Kết quả tiêu chuẩn:

```text
if: JAVA
not nonblank text
not nonblank text
integer=42
length=3
skip
first=left
second=right
field=FIELD
```

Phân tích kết quả:

1. `inspect("Java")`: `input` khớp `String label`, và chuỗi không rỗng trắng. Bên trong nhánh, `label` là **pattern variable**, nên in `JAVA`.
2. `inspect("   ")`: pattern vẫn khớp `String`, nhưng `isBlank()` trả về `true`, khiến toàn biểu thức `&&` sai và chạy `else`. Không dùng `label` trong nhánh đó.
3. `inspect(42)`: pattern `String` sai, sau đó pattern `Integer number` đúng, nên in `integer=42`.
4. `afterGuard("abc")`: điều kiện phủ định sai, vượt qua guard và dùng được `text` để in độ dài `3`.
5. `afterGuard(null)`: pattern `String` không khớp; nhánh guard in `skip` rồi `return`.
6. `reuse(...)`: cả hai `if` có thể sử dụng tên `s` riêng mà không xung đột; in `first=left` và `second=right`.
7. `field=FIELD`: field tĩnh `label` vẫn nguyên vẹn; pattern variable cùng tên bên trong `inspect` không gán đè field.

Ví dụ này dùng **type pattern của `instanceof`**, chính thức từ Java 16 và được hỗ trợ đầy đủ trong Java 17. Không cần bật `--enable-preview`.

## 9. Phạm vi tên biến trong `switch` pattern matching (Java 21+)

Từ Java 21, `switch` hỗ trợ pattern matching chính thức. Mỗi nhánh `case` dạng pattern có thể khai báo biến; biến đó có thể dùng trong **guard `when`** và **phần xử lý của nhánh tương ứng** khi pattern match:

```java
static String classify(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "text:" + s;
        case String s -> "blank";
        case null -> "null";
        default -> "other";
    };
}
```

Ý nghĩa:

- Với `"Java"`, pattern `String s` khớp; `s` có giá trị khi `when` kiểm tra `!s.isBlank()`. Kết quả `"text:Java"`.
- Với `"   "`, type pattern đầu khớp nhưng guard sai; `switch` tiếp tục tìm nhánh phù hợp và chọn nhánh `case String s ->`, cho `"blank"`.
- Với `null`, nhánh `case null` xử lý giá trị; nó không khai báo biến mẫu.
- Với `42`, các nhánh `String` không khớp; đi tới `default` và cho `"other"`.

Hai nhánh `case String s` ở đây hợp lệ vì biến `s` của mỗi nhánh được dùng trong phạm vi tương ứng. Phạm vi của một pattern variable trong `switch` phải tuân theo quy tắc cụ thể của cấu trúc `switch`; nhất là với dấu `:` và khả năng fall-through, không được suy luận rằng mọi nhánh có phạm vi giống `if`. Dùng nhánh dạng `->` như trên giúp phạm vi rõ hơn.

Chương trình chạy độc lập cho Java 21+ (file **`SwitchScopeDemo.java`**):

```java
public class SwitchScopeDemo {
    static String classify(Object value) {
        return switch (value) {
            case String s when !s.isBlank() -> "text:" + s;
            case String s -> "blank";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("Java"));
        System.out.println(classify("   "));
        System.out.println(classify(null));
        System.out.println(classify(42));
    }
}
```

Biên dịch/chạy bằng JDK 21 trở lên:

```bash
javac --release 21 SwitchScopeDemo.java
java SwitchScopeDemo
```

Kết quả:

```text
text:Java
blank
null
other
```

Sự khác biệt phiên bản đáng nhớ: ví dụ đầy đủ ở mục 8 chạy với `--release 17`, còn ví dụ `switch` có `case String s when ...` cần Java 21+.

## 10. Những lỗi thường gặp và cách sửa

### Lỗi 1: Tham chiếu biến ở nhánh `else` không bảo đảm match

```java
if (input instanceof String text) {
    System.out.println(text);
} else {
    // Sai nếu bỏ comment: text có thể chưa được khởi tạo.
    // System.out.println(text.length());
}
```

**Sửa:** dùng logic trên giá trị `input` ở nhánh thất bại, hoặc đảo điều kiện và đặt đoạn cần dùng `text` vào nhánh đã chắc chắn match.

### Lỗi 2: Dùng biến trên vế phải `||` sai chiều

```java
// if (input instanceof String text || text.isBlank()) { ... } // Sai
if (input instanceof String text && text.isBlank()) {
    System.out.println("Blank string");
}
```

**Sửa:** chọn toán tử mà đường đánh giá vế phải bảo đảm kết quả pattern đã đúng; nếu mục tiêu là “không phải String hoặc String rỗng trắng”, dùng `!(input instanceof String text) || text.isBlank()`.

### Lỗi 3: Gọi pattern variable sau `if` mà vẫn còn đường đi thất bại

```java
if (!(input instanceof String text)) {
    System.out.println("Not String");
}

// Không hợp lệ nếu bỏ comment: nhánh không match vẫn có thể tới đây.
// System.out.println(text.length());
```

**Sửa:** thêm `return` hoặc `throw` vào nhánh thất bại khi thực sự muốn xử lý tiếp chỉ với `String`, hoặc chuyển xử lý vào nhánh đã match.

### Lỗi 4: Trùng tên với biến cục bộ hoặc tham số

```java
String text = "A";
// if (input instanceof String text) { ... } // Sai: xung đột tên

if (input instanceof String candidate) {
    System.out.println(candidate);
}
```

**Sửa:** chọn tên không trùng, ưu tiên thể hiện vai trò như `candidate` hoặc `parsedText`.

### Lỗi 5: Nghĩ rằng pattern variable luôn có giá trị mặc định

Không có quy tắc tự khởi tạo biến mẫu thành `null` khi pattern thất bại. Pattern variable **không dùng được** ở đường đi mà compiler không chứng minh đã match; vấn đề thường xuất hiện thành lỗi biên dịch trước khi chạy.

### Lỗi 6: Nhầm tên biến mẫu với việc đổi tên đối tượng

```java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text); // Java
}
```

`text` là một tham chiếu kiểu `String` tới giá trị đã khớp; nó không tạo đối tượng `String` mới và không đổi kiểu khai báo của `input` từ `Object` thành `String`.

### Lỗi 7: Cho rằng pattern variable mặc định `final`

Trong pattern matching cho `instanceof` từ Java 16, pattern variable **không mặc nhiên là `final`**. Có thể gán lại biến ở phạm vi hợp lệ khi không bị hạn chế bởi quy tắc khác; việc gán lại biến mẫu không tự thay đổi biến nguồn. Dù được phép, nên tránh dùng lại cùng tên cho nhiều ý nghĩa khiến luồng dữ liệu khó đọc.

### Lỗi 8: Tái sử dụng tên trong cùng phạm vi đang hoạt động

Có thể dùng cùng `s` ở hai phép `if` độc lập nếu scope không chồng lấn; nhưng không thể khai báo một biến mẫu thứ hai cùng tên ngay tại vị trí mà biến cục bộ hoặc pattern variable trước vẫn đang trong scope. Khi nghi ngờ, đổi tên hoặc thu hẹp khối xử lý, rồi kiểm tra với `javac` của phiên bản mục tiêu.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Với `Object x = "abc";`, vì sao `if (x instanceof String s && s.length() > 2)` hợp lệ nhưng thay `&&` bằng `||` lại lỗi?

**Đáp án:** `&&` chỉ cho vế phải chạy sau khi pattern khớp; `||` chỉ chạy vế phải khi vế trái sai, nên `s` không được bảo đảm đã khởi tạo.

**Câu 2.** Đoạn sau có biên dịch không?

```java
static void verify(Object x) {
    if (!(x instanceof String s)) {
        return;
    }
    System.out.println(s.length());
}
```

**Đáp án:** Có (Java 17+). Mọi đường tới `println` đều đã loại trừ trường hợp không match.

**Câu 3.** Tên `s` dùng hai lần trong hai `if` nối tiếp, không lồng nhau, có chắc chắn là lỗi khai báo trùng?

**Đáp án:** Không. Nếu scope của pattern variable đầu đã kết thúc trước khi biến thứ hai được khai báo, có thể sử dụng lại tên. Ví dụ ở mục 8 minh họa trường hợp hợp lệ.

**Câu 4.** Một class có field `String label`, bên trong `if (obj instanceof String label)` có được gọi `label.toUpperCase()` không?

**Đáp án:** Có nếu kiểu tĩnh của `obj` cho phép type pattern và pattern match. Pattern variable có thể shadow field; dùng `ClassName.label` để truy cập field khi cần. Tuy nhiên nên tránh dùng cùng tên vì dễ nhầm.

**Câu 5.** `switch` có `case String s when s.length() > 2 ->` có dùng `s` trong `when` được không?

**Đáp án:** Có trong Java 21+, vì guard chỉ được đánh giá sau khi pattern của nhánh đó khớp. Trong Java 17, cú pháp pattern `switch` này chưa là tính năng chính thức.

## 12. Checklist khi viết pattern variable

Trước khi dùng tên biến mẫu, hãy lần lượt tự hỏi:

1. **Tên có hợp lệ và rõ nghĩa không?** Tránh keyword, tên trùng local/parameter đang có scope và tên che field không cần thiết.
2. **Kiểu pattern có phù hợp với kiểu tĩnh của biểu thức được kiểm tra không?** Không phải mọi phép `instanceof` đều có thể viết dưới dạng pattern hợp lệ nếu kiểm tra thừa hoặc kiểu không tương thích trong phiên bản Java mục tiêu.
3. **Tại dòng đang dùng, có chắc pattern đã match không?** Xét `&&`, `||`, `!`, `if/else`, `return`, vòng lặp hoặc `switch`.
4. **Biến có thể bị dùng ở nhánh thất bại hoặc sau khi scope kết thúc không?** Nếu có, sửa cấu trúc luồng điều khiển hoặc dùng biến khác.
5. **Đã biên dịch với đúng phiên bản Java chưa?** Ví dụ `instanceof` type pattern dùng Java 17; `case String s when ...` trong `switch` yêu cầu Java 21+.

**Quy tắc cốt lõi:** *Đặt tên pattern variable như biến cục bộ Java, nhưng xác định phạm vi sử dụng của nó theo các đường đi mà Java có thể chứng minh việc matching đã thành công.* Đó là lý do cùng một tên có thể hợp lệ trong hai khối độc lập, còn một biến khai báo ngay trong điều kiện vẫn có thể dùng sau `if` nếu guard loại bỏ mọi đường đi không khớp.

### Tài liệu chính thức

- [JLS Java SE 17, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3)
- [JLS Java SE 17, §6.3.1 — Scope for Pattern Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1)
- [JLS Java SE 17, §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
