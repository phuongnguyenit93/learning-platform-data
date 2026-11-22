# Phạm vi biến sau toán tử phủ định trong Java Flow Scoping

**Chủ đề:** Java Core Pattern Matching → Flow scoping  
**Phiên bản:** Java 17 trở lên. Pattern matching cho `instanceof` đã là tính năng chính thức từ Java 16.

## 1. Vấn đề cốt lõi

Với biểu thức `value instanceof String text`, biến pattern `text` chỉ có ý nghĩa tại những điểm mà trình biên dịch có thể chứng minh đối tượng đã khớp kiểu `String`. Khi thêm toán tử phủ định `!`, kết quả boolean bị đảo chiều:

```java
value instanceof String text       // true  => đã khớp String
!(value instanceof String text)    // false => đã khớp String
```

Vì vậy, **sau biểu thức phủ định**, phạm vi hợp lệ của `text` phụ thuộc vào nhánh điều khiển nào chắc chắn chứng minh được điều kiện `instanceof` ban đầu là `true`. Đây là quy tắc *flow scoping* (phạm vi theo luồng điều khiển), không chỉ là phạm vi tính bằng cặp ngoặc nhọn.

Điểm cần ghi nhớ: `!` chỉ đảo **giá trị boolean** của phép kiểm tra; nó không biến một giá trị không phải `String` thành `String` và không làm biến pattern khả dụng ở mọi nhánh.

## 2. Phân tích hai nhánh của `if` có phủ định

Xét đoạn mã với `value` là `Object`:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải String");
    // Không thể dùng text ở đây.
} else {
    System.out.println(text.length()); // Hợp lệ.
}
```

Bảng suy luận:

| Kết quả `value instanceof String text` | Kết quả phủ định | Nhánh chạy | Có thể dùng `text`? |
| --- | --- | --- | --- |
| `true` | `false` | `else` | Có: pattern đã khớp |
| `false` | `true` | `if` | Không: pattern không khớp |

Nếu `value == null`, phép `instanceof String text` là `false`, nên điều kiện phủ định là `true`. Với ví dụ trên, `null` đi vào nhánh `if`; trong nhánh đó, `text` không có giá trị để sử dụng.

Cú pháp ngoặc `!(value instanceof String text)` rất quan trọng. Nó phủ định toàn bộ phép `instanceof`. Viết `!value instanceof String text` không biểu diễn ý định trên và không hợp lệ khi `value` có kiểu `Object`.

## 3. Vì sao có thể dùng biến pattern **sau** `if`?

Đây là trường hợp quan trọng nhất:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length(); // Hợp lệ trong Java 17+.
}
```

Nếu `value` không phải `String` (kể cả `null`), chương trình thực hiện `return -1`; không có đường đi nào từ nhánh này tới dòng `return text.length()`. Muốn tới dòng sau `if`, điều kiện phủ định phải là `false`, đồng nghĩa với `instanceof` đã khớp. Trình biên dịch vì vậy cho phép dùng `text`.

Đây không phải một ngoại lệ tùy ý. Java có quy tắc: với dạng `if (condition) statement`, một biến pattern được giới thiệu khi `condition` là `false` có thể được đưa vào phạm vi của các lệnh theo sau nếu **nhánh `statement` không thể hoàn tất bình thường** (*cannot complete normally*). Lệnh `return` hoặc `throw` vô điều kiện là các ví dụ điển hình.

Biến thể dùng `throw`:

```java
static String requireString(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Cần String");
    }
    return text.trim(); // Hợp lệ.
}
```

Với `throw`, đường đi không khớp kết thúc bằng ngoại lệ, nên đường đi tiếp tục cũng đã chứng minh pattern khớp.

Kỹ thuật này thường gọi là **guard clause**: kiểm tra đầu vào không hợp lệ ở đầu phương thức, kết thúc sớm, rồi viết phần xử lý chính với độ lồng nhau thấp.

## 4. Khi nào biến vẫn **không** hợp lệ sau `if`?

Nếu nhánh điều kiện phủ định có thể kết thúc bình thường, luồng điều khiển vẫn có thể đi tiếp mà pattern chưa khớp:

```java
// Ví dụ KHÔNG BIÊN DỊCH:
static int invalid(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Không phải chuỗi");
    }
    return text.length(); // Lỗi: chưa chắc text đã được gắn giá trị.
}
```

Nhánh `if` trên chỉ in một dòng rồi tiếp tục. Với `value = 42` hoặc `null`, chương trình sẽ tới `return text.length()` mặc dù `text` chưa hề khớp. Java loại bỏ mã này ở thời điểm biên dịch.

Tương tự, trong **chính nhánh `if` có phủ định**, không được truy cập `text`:

```java
// Ví dụ KHÔNG BIÊN DỊCH:
if (!(value instanceof String text)) {
    // System.out.println(text.length()); // text ngoài phạm vi.
}
```

Việc có dấu ngoặc nhọn `{ ... }` không tự làm biến pattern xuất hiện. Phạm vi biến phụ thuộc vào nhánh nào bảo đảm kiểm tra kiểu đã thành công.

## 5. Tác động của `!` khi kết hợp `||` và `&&`

Các toán tử logic ngắn mạch cần được đọc theo **điều kiện mà toán hạng bên phải được đánh giá**.

### 5.1. Phủ định kết hợp `||`: hợp lệ

```java
static boolean isNonBlankText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return false;
    }
    return true;
}
```

Vế phải của `||` chỉ được đánh giá khi vế trái là `false`. Với vế trái `!(value instanceof String text)`, điều đó có nghĩa `value` **đã khớp** `String text`. Do vậy `text.isBlank()` là hợp lệ và không bị gọi trên một giá trị khác kiểu. Nếu `value` là `null`, vế trái là `true` và Java không đánh giá vế phải.

Có thể tận dụng phép suy luận này sau một guard:

```java
static String normalizeNonBlank(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "INVALID";
    }
    return text.strip(); // Hợp lệ: điều kiện || ở trên phải false.
}
```

Muốn chạy tới `return text.strip()`, cả hai vế của `||` phải `false`. Điều đó chứng minh `text` là một `String` không blank.

### 5.2. Phủ định kết hợp `&&`: khác hẳn

```java
// Ví dụ KHÔNG BIÊN DỊCH:
// if (!(value instanceof String text) && text.isBlank()) {
//     System.out.println("Không hợp lệ");
// }
```

Vế phải của `&&` chỉ chạy khi vế trái là `true`: tức là `instanceof` **không khớp**, nên biến `text` không thể dùng ở đó.

Nếu mục tiêu là kiểm tra String có nội dung, dạng không phủ định cũng rất rõ ràng:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
```

Ở ví dụ này, `&&` chỉ đánh giá `!text.isBlank()` sau khi `value instanceof String text` thành công.

### 5.3. Quy tắc dễ ghi nhớ

| Biểu thức đứng bên trái | Toán tử | Khi nào vế phải chạy? | Biến `text` hợp lệ ở vế phải? |
| --- | --- | --- | --- |
| `value instanceof String text` | `&&` | Khi khớp `String` | Có |
| `value instanceof String text` | `\|\|` | Khi không khớp `String` | Không |
| `!(value instanceof String text)` | `\|\|` | Khi khớp `String` | Có |
| `!(value instanceof String text)` | `&&` | Khi không khớp `String` | Không |

Phép phân tích này dành cho `&&` và `||` có cơ chế short-circuit; không nên mặc nhiên áp dụng tương tự cho `&` hoặc `|` vốn đánh giá cả hai vế.

## 6. Ví dụ chương trình hoàn chỉnh Java 17+

Tạo tệp **`NegatedInstanceofScopeDemo.java`**:

```java
public class NegatedInstanceofScopeDemo {
    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "NOT_STRING";
        }
        return "TEXT:" + text.trim().toUpperCase(java.util.Locale.ROOT);
    }

    static int lengthOrMinusOne(Object value) {
        if (!(value instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    static boolean isNonBlankText(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return false;
        }
        return true;
    }

    static void showElse(Object value) {
        if (!(value instanceof String text)) {
            System.out.println("OTHER");
        } else {
            System.out.println("MATCH=" + text.length());
        }
    }

    public static void main(String[] args) {
        System.out.println(normalize("  java  "));
        System.out.println(normalize(42));

        System.out.println("len=" + lengthOrMinusOne("abc"));
        System.out.println("len=" + lengthOrMinusOne(null));

        System.out.println("nonBlank=" + isNonBlankText("   "));
        System.out.println("nonBlank=" + isNonBlankText("Java"));

        showElse("abc");
        showElse(null);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 NegatedInstanceofScopeDemo.java
java NegatedInstanceofScopeDemo
```

Kết quả chính xác:

```text
TEXT:JAVA
NOT_STRING
len=3
len=-1
nonBlank=false
nonBlank=true
MATCH=3
OTHER
```

**Đối chiếu từng nhóm kết quả:**

1. `normalize("  java  ")` vượt qua guard, được phép dùng `text` sau `if`, cắt khoảng trắng hai đầu và chuyển thành `JAVA`. `42` không khớp `String` nên trả về `NOT_STRING`.
2. `lengthOrMinusOne("abc")` trả `3`, còn `lengthOrMinusOne(null)` trả `-1` do `instanceof` với `null` là `false`.
3. `isNonBlankText("   ")` trả `false` vì `isBlank()` là `true`; `"Java"` cho `true`.
4. Trong `showElse`, chỉ nhánh `else` được dùng biến `text`; `"abc"` in `MATCH=3`, còn `null` in `OTHER`.

Chương trình sử dụng type pattern cho `instanceof` và các phương thức chuẩn có sẵn trên JDK 17; không cần bật preview feature.

## 7. `continue`, `break` và phạm vi bên trong vòng lặp

Lý do guard clause hoạt động là đường đi không khớp **không thể tới lệnh phía sau trong cùng luồng đó**. Trong vòng lặp, `continue` cũng hữu ích: nó chuyển sang lần lặp tiếp theo.

Ví dụ minh họa đặt trong một phương thức:

```java
for (Object item : items) {
    if (!(item instanceof String text)) {
        continue;
    }
    System.out.println(text.length()); // Hợp lệ trong lần lặp này.
}
```

Ở mỗi lần lặp, nếu `item` không phải `String`, `continue` bỏ qua câu lệnh in. Nếu vẫn tới được câu lệnh in, `text` đã khớp. Dấu ngoặc nhọn của vòng lặp xác định điểm kết thúc phạm vi sử dụng này; không mang `text` sang lần lặp khác.

Với `break`, cần xem chính xác đích thoát: `break` có thể chấm dứt vòng lặp, nhưng không bảo đảm biến tồn tại ngoài cấu trúc chứa nó. Hãy suy luận theo đường thực thi thực tế, đừng suy đoán chỉ từ sự xuất hiện của từ khóa `break` hay `continue`.

## 8. Các lỗi điển hình

- **Nhầm nhánh:** cho rằng `text` tồn tại trong `if (!(value instanceof String text))`. Thực tế nhánh này biểu thị pattern **không khớp**.
- **Bỏ điều kiện thoát:** đổi `return` thành `println` trong guard nhưng vẫn sử dụng `text` sau `if`. Khi nhánh không khớp có thể đi tiếp, trình biên dịch không cho phép biến đó.
- **Nhầm `&&` với `||`:** sau phủ định, `||` mới cho phép vế phải dùng biến pattern đã khớp; `&&` thì không.
- **Không xét `null`:** `null` luôn không khớp type pattern `instanceof String text`, vì vậy điều kiện phủ định nhận `true`.
- **Dùng biến trong nhiều block tùy ý:** flow scoping gắn với chứng minh kiểu theo từng đường đi; không thể kéo dài phạm vi biến chỉ bằng việc mở rộng cặp ngoặc nhọn.
- **Nhầm với phép kiểm tra kiểu truyền thống:** `value instanceof String` không tự khai báo `text`; chỉ cú pháp `value instanceof String text` mới có pattern variable.
- **Dựa vào giá trị runtime để chữa lỗi biên dịch:** dù người viết biết một tham số “luôn là String”, trình biên dịch vẫn phải kiểm chứng từ cấu trúc điều khiển và kiểu tĩnh.

## 9. Tự thực hành

1. Dự đoán nhánh chạy khi truyền `"hello"`, `10` và `null` vào điều kiện `if (!(value instanceof String s))`. Ở nhánh nào có thể gọi `s.length()`?
2. Đổi `return -1` trong `lengthOrMinusOne` thành `System.out.println("invalid")`; thử biên dịch và giải thích vì sao dòng `return text.length()` không hợp lệ.
3. Viết guard dùng `throw new IllegalArgumentException(...)` khi đối tượng không phải `String`, rồi trả chuỗi đã `trim()` ở cuối phương thức.
4. So sánh `!(value instanceof String s) || s.isBlank()` với `!(value instanceof String s) && s.isBlank()`; xác định biểu thức nào có thể biên dịch và lý do.
5. Viết vòng lặp `for (Object item : items)`, dùng `continue` để bỏ qua những giá trị không phải `String`, rồi in độ dài mỗi chuỗi hợp lệ.

**Tiêu chí đạt:** giải thích được vì sao `!` chuyển điều kiện *pattern đã khớp* sang nhánh `false`, chứng minh được khi nào biến tồn tại sau guard và nhận diện được lỗi scoping trong điều kiện ghép `&&`/`||`.

**Tài liệu chuẩn:** [Java Language Specification, §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3) và [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
