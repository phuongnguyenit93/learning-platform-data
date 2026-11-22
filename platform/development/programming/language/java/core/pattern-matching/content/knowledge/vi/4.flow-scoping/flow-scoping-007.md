# Phạm vi biến trong `while` với Java pattern matching

## 1. Vấn đề: biến pattern tồn tại ở đâu trong vòng lặp?

Từ Java 16 (và trong Java 17+), `instanceof` có thể dùng **type pattern** để vừa kiểm tra kiểu đối tượng, vừa khai báo một biến có kiểu đã được kiểm tra:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Khi đưa phép thử ấy vào `while`, cần trả lời hai câu hỏi khác nhau:

1. **Trong thân vòng lặp**, khi điều kiện đúng, biến pattern có dùng được không?
2. **Sau vòng lặp**, khi điều kiện sai khiến vòng lặp dừng, biến pattern có dùng được không?

Câu trả lời phụ thuộc vào *flow scoping*: Java phân tích luồng điều khiển để xác định một pattern variable đã **chắc chắn khớp (definitely matched)** tại vị trí dùng hay chưa. Phạm vi không đơn thuần là “từ chỗ khai báo đến hết cặp dấu ngoặc nhọn”. Trong `while`, kết quả đúng hoặc sai của điều kiện cùng các đường thoát khỏi vòng lặp quyết định phạm vi này.

Bài học dùng `instanceof` type pattern chuẩn Java 17+. Quy tắc chính được đặc tả trong **Java Language Specification (JLS) 17, §6.3.2.3 — `while` Statements**.

## 2. Điều kiện `while` khớp: biến dùng được trong thân vòng lặp

Ví dụ:

```java
Object value = "hello";
while (value instanceof String text) {
    System.out.println(text.toUpperCase());
    value = 10;
}
// System.out.println(text); // LỖI biên dịch: text không trong phạm vi
```

Diễn biến:

1. Đánh giá `value instanceof String text`. Đối tượng ban đầu là `"hello"`, nên kết quả `true` và biến `text` được gán tham chiếu tới chuỗi ấy.
2. Thân `while` chỉ chạy khi điều kiện `true`, vì vậy **`text` đã khớp chắc chắn** và được dùng hợp lệ trong thân vòng lặp. Chương trình in `HELLO`.
3. Phép gán `value = 10` làm `value` tham chiếu tới `Integer` do autoboxing. Biến `text` của **lượt hiện tại** vẫn tham chiếu tới `"hello"`; đổi biến nguồn không thay đổi giá trị đã được gán cho pattern variable ở lượt ấy.
4. Đầu lượt kế tiếp, `value instanceof String text` trả `false`, vòng lặp kết thúc.
5. **Sau `while` này không dùng được `text`**: điều kiện kết thúc là phép thử **không khớp**. Biến chỉ được đưa vào phạm vi trong thân vòng lặp khi điều kiện đúng.

Trong ngữ cảnh này, `while (value instanceof String text)` có thể hiểu là: “Chừng nào giá trị hiện tại còn là `String`, hãy chạy thân vòng lặp với một biến `text` có kiểu `String`”. Mỗi lần điều kiện được đánh giá là đúng, giá trị từ phép khớp của lượt đó dùng trong phần thân tương ứng.

Lưu ý: nếu không thay đổi `value`, ví dụ trên sẽ lặp vô hạn vì điều kiện vẫn đúng. Luôn bảo đảm điều kiện có khả năng trở thành `false`, hoặc có một cơ chế kết thúc thích hợp.

## 3. `&&` trong điều kiện: dùng biến ở vế phải và trong thân

Toán tử `&&` đánh giá từ trái sang phải và **không đánh giá vế phải khi vế trái sai** (*short-circuit*). Điều đó cho phép kiểm tra kiểu rồi ngay lập tức áp dụng điều kiện bổ sung lên pattern variable.

```java
Object value = "Java";
while (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.length()); // text hợp lệ
    value = "";
}
```

Lượt đầu: `value` là `"Java"`, type pattern `String text` khớp, rồi mới gọi `text.isEmpty()`. Lượt hai: `value` là `""`, vẫn khớp `String` nhưng `!text.isEmpty()` là `false`, nên vòng lặp dừng. Kết quả chỉ in `4`.

Có thể đặt các điều kiện bảo vệ **trước** phép thử để tránh truy cập ngoài giới hạn:

```java
Object[] values = {"Hi", "Java", 7};
int index = 0;

while (index < values.length
        && values[index] instanceof String text
        && !text.isBlank()) {
    System.out.println(text + ": " + text.length());
    index++;
}
// text không dùng được ở đây.
```

Mỗi lần kiểm tra:

- Trước hết `index < values.length` phải đúng, vì vậy phép truy cập `values[index]` an toàn.
- Tiếp theo, phần tử phải khớp `String text`.
- Cuối cùng, `text.isBlank()` mới được gọi; lúc này `text` có kiểu `String` và đã được khởi tạo.
- Thân vòng lặp chạy khi **toàn bộ biểu thức đúng**, nên dùng được `text`.

Đoạn mã in:

```text
Hi: 2
Java: 4
```

Nó dừng ở chỉ số 2 vì phần tử `7` là `Integer`, không phải `String`. Chuỗi `"Java"` có độ dài 4.

**Lỗi thường gặp với `||`:**

```java
// KHÔNG biên dịch:
while (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
```

Vế phải của `||` được đánh giá khi vế trái **sai**, tức là khi `text` không được bảo đảm đã khớp. Vì thế, Java không cho gọi `text.isEmpty()` ở vị trí đó. Với mẫu kiểm tra dương `value instanceof String text`, hãy dùng `&&` nếu điều kiện sau cần truy cập `text`.

## 4. Điều kiện phủ định `!`: biến có thể dùng **sau** `while`

Đây là trường hợp dễ nhầm nhất. Xét:

```java
static String ensureString(Object value) {
    while (!(value instanceof String text)) {
        value = "ready";
    }
    return text.toUpperCase(); // HỢP LỆ trong Java 17+
}
```

Phân tích theo luồng chạy:

- Nếu `value` ban đầu đã là `String`, biểu thức `value instanceof String text` đúng, phủ định `!` khiến điều kiện `while` sai. Thân không chạy; **`text` đã khớp** và được sử dụng sau `while`.
- Nếu `value` ban đầu không phải `String` hoặc là `null`, phép kiểm tra ban đầu sai nên `while` chạy. Lúc này **không dùng được `text` bên trong thân**, vì chính phép thử `String` đã thất bại.
- Trong thân, `value` được gán `"ready"`. Khi đánh giá điều kiện lại, phép thử `String text` đúng, phủ định khiến `while` kết thúc. Sau vòng lặp, `text` tham chiếu tới `"ready"`.

**Vì sao biên dịch được?** Theo JLS 17, một `while` có thể đưa pattern variable vào phạm vi **sau chính câu lệnh `while`** nếu:

1. Biến pattern được giới thiệu bởi biểu thức điều kiện **khi biểu thức đó sai** (*introduced when false*).
2. Thân vòng lặp **không chứa `break` có thể thực thi mà thoát khỏi vòng lặp này** (nói chính xác theo JLS: không có *reachable break* với đích thoát bao chứa thân vòng lặp).

Ở ví dụ `while (!(value instanceof String text))`, biểu thức điều kiện chỉ có thể sai khi phép thử `instanceof String text` đúng. Vì không có đường thoát sớm bằng `break`, mọi đường đi bình thường tới câu `return text.toUpperCase()` đều bảo đảm `text` đã khớp.

Điều này **không áp dụng** cho `while (value instanceof String text)`: khi vòng lặp ấy kết thúc vì điều kiện sai, phép thử kiểu không thành công.

### 4.1. `break` có thể khiến biến mất phạm vi sau `while`

Ví dụ sau **chỉ để minh họa lỗi biên dịch**, không phải chương trình độc lập:

```java
static void maybeBreak(Object value, boolean stopEarly) {
    while (!(value instanceof String text)) {
        if (stopEarly) {
            break;
        }
        value = "ready";
    }

    // System.out.println(text.length()); // LỖI biên dịch nếu bỏ //
}
```

Khi `stopEarly` là `true`, `break` có thể thoát `while` ngay lúc phép thử `String text` còn sai. Java vì vậy **không đưa `text` vào phạm vi sau vòng lặp**. Không thể dựa vào việc “trong một lần chạy cụ thể, `stopEarly` thường là `false`” để quyết định phạm vi ở thời điểm biên dịch.

Ngược lại, `continue` chuyển sang lần đánh giá điều kiện tiếp theo, nên bản thân `continue` **không phải** một đường thoát bỏ qua phép kiểm tra. Dẫu vậy, vẫn phải bảo đảm vòng lặp có khả năng kết thúc.

### 4.2. Phủ định kết hợp `||` có thể hợp lệ

Không phải mọi phép `||` đi cùng pattern variable đều sai. Ví dụ sau hợp lệ trong Java 17:

```java
static String requireNonBlankString(Object value) {
    while (!(value instanceof String text) || text.isBlank()) {
        value = "fallback";
    }
    return text;
}
```

Nếu vế trái `!(value instanceof String text)` là `true`, vế phải không được đánh giá. Nếu vế trái là `false`, đối tượng **đã khớp** với `String text`, nên vế phải `text.isBlank()` dùng `text` hợp lệ. Khi toàn bộ điều kiện `while` là `false`, điều đó bảo đảm giá trị đã là một chuỗi không trắng. Không có `break` nên `text` cũng dùng được sau vòng lặp.

Thử suy luận:

| Giá trị đầu vào | Diễn biến | Giá trị trả về |
| --- | --- | --- |
| `"abc"` | Đã là chuỗi không trắng, không vào thân | `"abc"` |
| `""` | Khớp `String` nhưng trống; gán `"fallback"`, kiểm tra lại | `"fallback"` |
| `7` | Không phải `String`; gán `"fallback"`, kiểm tra lại | `"fallback"` |
| `null` | Không khớp `String`; gán `"fallback"`, kiểm tra lại | `"fallback"` |

Hãy chú ý **kết quả nào khiến vế phải được đánh giá**: `instanceof String text && ...` dùng `text` ở vế phải khi phép thử dương đúng; còn `!(instanceof String text) || ...` cũng dùng `text` khi phép thử gốc đúng, vì lúc ấy vế phủ định sai.

## 5. Chương trình Java 17+ chạy đầy đủ

Tạo file `WhilePatternScopeDemo.java`:

```java
public class WhilePatternScopeDemo {
    static void printLeadingStrings(Object[] values) {
        int index = 0;

        while (index < values.length
                && values[index] instanceof String text
                && !text.isBlank()) {
            System.out.println("String " + index + ": "
                    + text + " (" + text.length() + ")");
            index++;
        }
        System.out.println("Stopped at index " + index);
        // System.out.println(text); // Không trong phạm vi sau while này.
    }

    static String ensureString(Object value) {
        while (!(value instanceof String text)) {
            System.out.println("Replacing non-string");
            value = "ready";
        }
        return text.toUpperCase(); // Trong phạm vi sau while phủ định.
    }

    static void showSnapshot() {
        Object value = "first";
        while (value instanceof String text) {
            value = 100;
            System.out.println("Old match: " + text);
        }
    }

    public static void main(String[] args) {
        printLeadingStrings(new Object[] {"Hi", "Java", 123, "later"});
        System.out.println("Converted: " + ensureString(42));
        System.out.println("Already: " + ensureString("ok"));
        showSnapshot();
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac WhilePatternScopeDemo.java
java WhilePatternScopeDemo
```

Đầu ra chính xác:

```text
String 0: Hi (2)
String 1: Java (4)
Stopped at index 2
Replacing non-string
Converted: READY
Already: OK
Old match: first
```

**Giải thích:**

1. `printLeadingStrings` chỉ xử lý tiền tố chuỗi không trắng. Phần tử thứ ba là `123` (`Integer`), nên biểu thức điều kiện sai và dừng với `index = 2`.
2. `ensureString(42)` đi vào thân vòng lặp một lần, in `Replacing non-string` và đổi giá trị thành `"ready"`. Lần kiểm tra sau, `String text` khớp, vòng lặp dừng và trả `"READY"`.
3. `ensureString("ok")` không chạy thân vòng lặp; biến `text` vẫn được khớp khi kiểm tra điều kiện ban đầu và kết quả là `"OK"`.
4. `showSnapshot` khớp `"first"`, sau đó gán `value = 100`. Biến `text` trong lượt đang chạy vẫn chỉ tới chuỗi `"first"` nên in `Old match: first`; lần kiểm tra tiếp theo thất bại và vòng lặp kết thúc.

Chương trình này minh họa **hai hướng của flow scoping**: điều kiện dương cho phép dùng biến trong thân vòng lặp, còn điều kiện phủ định với đường thoát bình thường duy nhất qua phép kiểm tra thất bại cho phép dùng biến sau vòng lặp.

## 6. So sánh các cấu trúc `while`

| Điều kiện / thân vòng lặp | Trong thân dùng `s`? | Sau vòng lặp dùng `s`? | Giải thích |
| --- | --- | --- | --- |
| `while (x instanceof String s) { ... }` | **Có** | **Không** | Thân chạy khi đã khớp; kết thúc tự nhiên khi không khớp |
| `while (x instanceof String s && !s.isBlank()) { ... }` | **Có** | **Không** | `s` dùng được trong vế phải `&&` và thân khi điều kiện đúng |
| `while (!(x instanceof String s)) { x = "ok"; }` | **Không** | **Có** | Thân chạy khi chưa khớp; kết thúc tự nhiên khi đã khớp |
| `while (!(x instanceof String s)) { if (flag) break; x = "ok"; }` | **Không** | **Không** | `break` có thể thoát trước khi pattern khớp |
| `while (!(x instanceof String s) || s.isBlank()) { x = "ok"; }` | **Không** | **Có** | Vế phải của `||` chỉ chạy khi `s` đã khớp; không có `break` |

Các dòng bảng có `x`, `flag` là biến giả định đã được khai báo với kiểu phù hợp, còn `{ ... }` đại diện cho thân lặp. Bảng chỉ so sánh **khả năng sử dụng biến pattern `s`**, không bảo đảm từng vòng lặp kết thúc với mọi giá trị đầu vào.

### Tên biến không tự tồn tại ở mọi vị trí

Nếu biến pattern không trong phạm vi sau `while`, một biến cục bộ cùng tên có thể được khai báo tại vị trí phù hợp theo quy tắc đặt tên của Java. Ngược lại, khi `while` phủ định đưa `s` vào phạm vi sau vòng lặp, không thể khai báo biến cục bộ khác cũng tên `s` trong cùng phạm vi ấy:

```java
static void example(Object value) {
    while (!(value instanceof String text)) {
        value = "ok";
    }
    System.out.println(text); // Hợp lệ.
    // String text = "another"; // LỖI: tên text đã trong phạm vi.
}
```

Khi đọc code, hãy xác định **điểm chương trình chắc chắn khớp pattern**, không chỉ dò dấu `{` và `}`.

## 7. Lỗi thường gặp và cách khắc phục

1. **Dùng biến pattern trong thân `while` phủ định.** Trong `while (!(obj instanceof String s))`, thân chạy khi đối tượng **không phải** `String`; không thể dùng `s` ở đó. Chỉ dùng `s` sau vòng lặp nếu JLS cho phép.
2. **Dùng biến sau `while` dương.** `while (obj instanceof String s) { ... }` kết thúc bình thường khi phép thử sai; khi đó `s` không trong phạm vi.
3. **Thêm `break` vào `while` phủ định rồi vẫn dùng `s` bên dưới.** Đường thoát sớm có thể bỏ qua việc khớp; trình biên dịch từ chối. Nếu cần dừng sớm, xử lý riêng kết quả thay vì giả định có `s`.
4. **Nhầm `&&` và `||`.** Vế phải của `&&` chạy khi vế trái đúng; vế phải của `||` chạy khi vế trái sai. Việc dùng `s` ở vế phải hợp lệ hay không phụ thuộc dạng điều kiện và phép phủ định.
5. **Quên điều kiện tiến triển.** Type pattern không tự thay đổi `obj`; nếu `obj` cứ là `String` với điều kiện dương, `while` có thể chạy mãi. Nếu `obj` không bao giờ thành `String` trong điều kiện phủ định, vòng lặp cũng có thể không dừng.
6. **Quên trường hợp `null`.** Với Java 17, `null instanceof String s` là `false`. Vòng lặp dương bỏ qua thân; vòng lặp phủ định đi vào thân. Việc gọi phương thức trên `s` chỉ an toàn khi `s` đã khớp.
7. **Nhầm thay đổi biến nguồn với thay đổi biến pattern trong lượt hiện tại.** Sau khi điều kiện khớp, biến pattern giữ tham chiếu đã được gán của lượt đó; việc gán lại `obj` không đổi tham chiếu đã có trong `s`.
8. **Dùng cú pháp với JDK không hỗ trợ.** Pattern matching cho `instanceof` là tính năng chính thức từ Java 16; dùng JDK 17+ để biên dịch các ví dụ trong bài.

## 8. Bài tập vận dụng

1. Dự đoán kết quả và giải thích phạm vi biến `s`:

   ```java
   Object x = "abc";
   while (x instanceof String s && s.length() > 1) {
       System.out.println(s);
       x = 0;
   }
   ```

2. Viết `static String normalize(Object x)` dùng `while (!(x instanceof String text))` để đổi các giá trị không phải chuỗi thành `"unknown"`, rồi trả `text.trim()`. Thử với `null`, `123`, `" hi "`.
3. Thêm một `if (stopEarly) break;` vào thân `while` ở câu 2. Giải thích vì sao sau đó `text.trim()` không còn hợp lệ ở bên ngoài vòng lặp.
4. Viết vòng lặp qua `Object[]` gồm các chuỗi và số, dừng ở phần tử đầu tiên không phải `String`, đồng thời in độ dài từng chuỗi. Bảo đảm không truy cập mảng quá giới hạn.
5. Giải thích vì sao `while (!(x instanceof String s) || s.isBlank()) { x = "ok"; }` hợp lệ, trong khi `while (x instanceof String s || s.isBlank()) { ... }` không hợp lệ.

**Tự đánh giá:** Bạn đã hiểu nội dung khi trả lời được cả hai câu: “Khi nào thân `while` chắc chắn có biến pattern?” và “Khi nào mọi đường chạy ra khỏi `while` chắc chắn đã khớp pattern?”. Câu thứ hai giải thích vai trò đặc biệt của điều kiện phủ định và `break`.

## Tài liệu tham khảo

- [Java Language Specification SE 17, §6.3.2.3 — Scope in `while` statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.2.3).
- [Java Language Specification SE 17, §6.3.1 — Pattern variables in expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3.1).
- [Oracle Java 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
