# Type pattern và biến được khai báo

## 1. Type pattern là gì?

Trong Java, **type pattern** (mẫu kiểu) kiểm tra xem một giá trị có thuộc một kiểu tham chiếu nhất định hay không; nếu khớp, nó **khai báo và khởi tạo một biến** có kiểu đã kiểm tra. Biến ấy gọi là *pattern variable*. Nhờ vậy, ta dùng trực tiếp các phương thức của kiểu đã khớp mà không cần ép kiểu bằng tay.

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

Cấu trúc `value instanceof String text` có ba thành phần: `value` là biểu thức cần kiểm tra; `instanceof` thực hiện phép thử kiểu khi chạy; `String text` là **type pattern** gồm kiểu `String` và tên biến `text`. Nếu `value` chứa một đối tượng `String`, biểu thức đúng và `text` tham chiếu tới **chính đối tượng đó**, không tạo bản sao. Nếu không khớp, biến `text` không sẵn có ở nhánh thất bại.

Kiểu tĩnh của `text` là `String`; trình biên dịch cho phép gọi `text.length()`, `text.isEmpty()` hoặc `text.toUpperCase()` như với bất kỳ biến `String` nào. Pattern matching cho `instanceof` đã là tính năng chính thức từ **Java 16** và dùng bình thường trong **Java 17+**.

## 2. Khai báo biến pattern so với cách cũ

Trước khi có type pattern, thường phải kiểm tra rồi ép kiểu tường minh:

```java
Object value = "  hello  ";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.trim());
}
```

Dùng type pattern:

```java
Object value = "  hello  ";
if (value instanceof String text) {
    System.out.println(text.trim());
}
```

Cả hai đoạn in `hello`. Cách mới giảm lặp tên kiểu và loại bỏ lệnh cast vốn có thể viết nhầm biến. `String text` trong `instanceof` vừa là phép thử kiểu vừa là khai báo biến được khởi tạo khi phép thử thành công. Đây không phải một khai báo cục bộ được thực thi vô điều kiện.

**Điều kiện khớp:** giá trị phải khác `null` và đối tượng phải tương thích với kiểu `String`. `null instanceof String text` trả về `false`, nên không có giá trị nào để gán cho `text` trong nhánh đúng.

## 3. Phạm vi biến theo luồng điều khiển (flow scoping)

Pattern variable không có phạm vi chỉ dựa vào cặp dấu `{}` gần nhất. Java dùng nguyên tắc **definitely matched**: chỉ cho phép tham chiếu tới biến tại những điểm mà mọi đường chạy đến đó đều bảo đảm phép thử pattern đã thành công.

### 3.1. Nhánh đúng và nhánh sai của `if`

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length()); // Hợp lệ
    } else {
        System.out.println("Không phải chuỗi");
        // text.length(); // LỖI BIÊN DỊCH: text không trong phạm vi
    }
    // text.length(); // LỖI: có thể không khớp khi đi qua if
}
```

Biến `text` dùng được ở nhánh đúng (`then`). Trong `else` và ở sau `if` thông thường, chương trình có thể đã đi theo đường không khớp nên không thể dùng biến ấy.

### 3.2. `&&` cho phép dùng biến trong điều kiện tiếp theo

```java
static boolean hasLongName(Object value) {
    return value instanceof String name && name.length() >= 5;
}
```

`&&` đánh giá vế phải **chỉ khi vế trái đúng**. Vì vậy `name` chắc chắn đã được khởi tạo khi `name.length()` chạy. Nếu `value` là `null` hoặc thuộc kiểu khác, vế trái sai và hàm trả `false` mà không truy cập `name`.

Ngược lại, đây là **mã không biên dịch được**:

```java
// Sai: vế phải có thể được đánh giá khi instanceof thất bại.
if (value instanceof String name || name.isEmpty()) {
    System.out.println("...");
}
```

`||` chỉ đánh giá vế phải khi vế trái sai; khi đó `name` chưa chắc được khởi tạo. Muốn lọc chuỗi rỗng, hãy viết:

```java
if (value instanceof String name && name.isEmpty()) {
    System.out.println("Chuỗi rỗng");
}
```

### 3.3. Phủ định và thoát sớm

Biến pattern có thể dùng **sau `if`** nếu nhánh không khớp kết thúc bằng `return` hoặc `throw`:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length(); // Hợp lệ: tới đây thì instanceof phải đúng
}
```

Ở trong nhánh `if` phủ định, `text` không sẵn có. Nhưng vì nhánh này `return`, mọi đường chạy tới `return text.length()` đều phải đi qua kết quả khớp. Nếu bỏ `return` và để nhánh thất bại đi tiếp, biến `text` không còn được dùng an toàn bên dưới.

| Vị trí | Có thể dùng biến `s`? | Lý do |
| --- | --- | --- |
| Trong `if (x instanceof String s) { ... }` | Có | Đã khớp |
| Trong `else` của phép thử trên | Không | Phép thử thất bại |
| Vế phải của `x instanceof String s && s.length() > 0` | Có | `&&` chỉ đi tiếp khi khớp |
| Vế phải của `x instanceof String s || s.isEmpty()` | Không | `||` đi tiếp khi không khớp |
| Sau `if (!(x instanceof String s)) return;` | Có | Đường không khớp đã kết thúc |

Cách tự kiểm tra: **Có đường chạy nào đến chỗ dùng `s` mà phép thử chưa thành công không?** Nếu có, trình biên dịch sẽ không cho dùng biến pattern đó.

## 4. Chương trình hoàn chỉnh Java 17+

Lưu đúng tên tệp `TypePatternDemo.java`:

```java
public class TypePatternDemo {
    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "String: " + text.toUpperCase()
                    + " (" + text.length() + ")";
        }
        if (value instanceof Integer number) {
            return "Integer doubled: " + (number * 2);
        }
        if (value == null) {
            return "null";
        }
        return "Other or blank string";
    }

    static String firstLetter(Object value) {
        if (!(value instanceof String text)) {
            return "Not a string";
        }
        if (text.isEmpty()) {
            return "Empty string";
        }
        return "First character: " + text.charAt(0);
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(21));
        System.out.println(describe(null));
        System.out.println(describe(""));
        System.out.println(firstLetter("abc"));
        System.out.println(firstLetter(42));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac TypePatternDemo.java
java TypePatternDemo
```

Kết quả:

```text
String: JAVA (4)
Integer doubled: 42
null
Other or blank string
First character: a
Not a string
```

Diễn giải:

1. `"java"` khớp `String text`; `!text.isBlank()` là `true`; `toUpperCase()` trả `JAVA` và độ dài là 4.
2. `21` được truyền với kiểu `Object` nhưng thực tế là `Integer`, nên `Integer number` khớp. `number * 2` dùng unboxing và cho kết quả 42.
3. `null` không khớp hai type pattern và được xử lý riêng.
4. `""` là `String` nhưng `isBlank()` bằng `true`, nên nhánh đầu không trả về và chương trình dùng thông báo dự phòng.
5. Trong `firstLetter`, nhánh `!(value instanceof String text)` trả về ngay nếu thất bại; vì vậy `text` dùng được sau `if`.

Đây là chương trình độc lập có `main`, không yêu cầu thư viện bên ngoài. Hai phương thức sử dụng cùng tên biến pattern `text` vì mỗi khai báo nằm trong phạm vi phương thức riêng.

## 5. Những giới hạn kiểu cần nắm

### Kiểu tĩnh có thể khiến phép thử dư thừa

Java 17 từ chối `instanceof` type pattern khi biểu thức có kiểu tĩnh đã là kiểu con của kiểu được kiểm tra, vì phép thử kiểu ấy dư thừa:

```java
String text = "Java";
// if (text instanceof String s) { } // LỖI BIÊN DỊCH
Object value = text;
if (value instanceof String s) {      // Hợp lệ
    System.out.println(s.length());   // 4
}
```

### Kiểu tham chiếu và generic

Type pattern `String s`, `Number n`, `CharSequence cs`, `Integer i` và `List<?> items` dùng được khi kiểu biểu thức phù hợp. Ở Java 17, `int n` không phải type pattern dùng được trong `instanceof`; với số nguyên được boxing trong `Object`, hãy kiểm tra `Integer n`.

Không thể kiểm tra `List<String>` trong `instanceof` vì thông tin đối số generic không được lưu đầy đủ ở thời điểm chạy (*type erasure*). Dùng kiểu có thể kiểm tra được:

```java
Object value = java.util.List.of("A", "B");
if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
```

Từ `List<?>` chỉ biết đó là một danh sách; **không được mặc nhiên coi tất cả phần tử là `String`**. Hãy kiểm tra từng phần tử nếu ứng dụng cần biết kiểu cụ thể.

### Tên và khả năng gán lại

Biến pattern là biến cục bộ có phạm vi do luồng điều khiển quyết định. Đặt tên có nghĩa như `text`, `number`, `items`; không khai báo tên trùng với biến đang hiện hữu trong cùng phạm vi. Từ Java 16, pattern variable **không mặc định `final`**, nên Java 17 có thể gán lại khi luật khai báo biến cho phép; dù vậy, tránh đổi ý nghĩa của biến ngay sau khi khớp để code dễ hiểu.

Không thể viết `value instanceof var x` ở Java 17: `var` không thay thế một kiểu cụ thể trong type pattern. Một khai báo cục bộ `var x = ...` thông thường cũng không tự kiểm tra kiểu runtime.

## 6. Type pattern trong `switch` (Java 21 trở lên)

Java 21 chính thức hỗ trợ pattern matching cho `switch`. Mỗi nhãn `case String s` hoặc `case Integer n` khởi tạo một biến cho nhánh khớp. Biến còn có thể dùng trong điều kiện `when` cùng nhãn, nhưng không có phạm vi ở các nhãn `case` khác.

Ví dụ sau dành cho **JDK 21+**; lưu thành `SwitchPatternDemo.java`:

```java
public class SwitchPatternDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "Chuỗi trống";
            case String s -> "Chuỗi dài " + s.length();
            case Integer n -> "Số " + n;
            default -> "Loại khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(""));
        System.out.println(describe("Java"));
        System.out.println(describe(8));
        System.out.println(describe(null));
    }
}
```

Chạy:

```bash
javac SwitchPatternDemo.java
java SwitchPatternDemo
```

Đầu ra:

```text
Chuỗi trống
Chuỗi dài 4
Số 8
null
```

`when s.isBlank()` chạy sau khi `String s` khớp; nhánh `case String s` kế tiếp xử lý các chuỗi còn lại. Hai nhãn có thể khai báo cùng tên `s` nhờ phạm vi tách biệt. `case null` xử lý giá trị `null` một cách tường minh. **Không chạy nguyên ví dụ `switch` này trên Java 17 ở chế độ biên dịch thông thường:** `switch` pattern khi đó chưa phải tính năng chính thức.

## 7. Lỗi thường gặp

- Dùng `s` ở `else` hoặc sau `if` khi luồng không khớp vẫn có thể tiếp tục → lỗi phạm vi.
- Viết `instanceof String s || s.isEmpty()` → sai do `||` kiểm tra vế phải khi pattern thất bại; thay bằng `&&` hoặc tái cấu trúc điều kiện.
- Cho rằng `null instanceof String s` khớp → sai, `instanceof` trả `false`.
- Ép kiểu `(String) value` lần nữa trong nhánh đã có `String s` → thừa và làm code kém rõ.
- Dùng `List<String>` trong `instanceof` → không thể kiểm tra đối số generic đó lúc chạy; cân nhắc `List<?>`.
- Nhầm biến pattern với khai báo `var` hay cho rằng nó luôn trong phạm vi đến cuối khối → hiểu sai nguyên tắc **definitely matched**.
- Sao chép cú pháp `switch` type pattern của Java 21 vào dự án biên dịch bằng Java 17 → sai phiên bản.

## 8. Bài tập áp dụng

1. Viết `static int size(Object value)` trả `cs.length()` nếu `value instanceof CharSequence cs`; ngược lại trả `-1`. Thử với `"abc"`, `new StringBuilder("xy")`, `12` và `null`.
2. Giải thích từng đường chạy của `x instanceof String s && s.length() >= 3`; vì sao chuyển `&&` thành `||` lại khiến việc dùng `s` sai?
3. Tạo một guard clause `if (!(obj instanceof Number n)) return;` trong phương thức `void`, rồi gọi `n.doubleValue()` sau `if`. Giải thích vì sao biến chắc chắn đã được khởi tạo.
4. Nếu có JDK 21+, thêm nhánh `case Long n` vào ví dụ `switch` và so sánh phạm vi biến `n` giữa hai nhánh `case` khác nhau.

**Ghi nhớ:** Type pattern là cặp **kiểu + tên biến**; biến pattern chỉ dùng được nơi Java chứng minh giá trị đã khớp. Trong `instanceof`, `&&` và các nhánh thoát sớm là hai cách thực tế nhất để khai thác flow scoping an toàn.

## Tài liệu tham khảo

- [Oracle Java 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
