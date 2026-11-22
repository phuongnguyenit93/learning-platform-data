# Pattern variable được khởi tạo khi nào trong Java?

**Câu trả lời:** Pattern variable (biến mẫu) được **tạo và khởi tạo tại thời điểm một giá trị khớp thành công với pattern trong lúc chạy chương trình**. Với `value instanceof String text`, khi giá trị của `value` khác `null` và là một `String`, Java gắn chính tham chiếu đó cho `text`; ngay từ điểm luồng điều khiển mà compiler chứng minh việc khớp đã xảy ra, ta có thể dùng `text` như một biến kiểu `String`. Nếu pattern không khớp, `text` không được khởi tạo cho lần kiểm tra đó.

Điều cần tách bạch là **thời điểm khởi tạo khi chạy** và **phạm vi có thể truy cập khi biên dịch** (`flow scoping`). Java không cho đọc một pattern variable ở vị trí mà pattern chưa chắc đã khớp, kể cả lập trình viên tin rằng đầu vào thực tế luôn đúng kiểu.

## 1. Từ phép kiểm tra `instanceof` đến biến đã có giá trị

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

Khi thực thi điều kiện:

1. Java đánh giá biểu thức bên trái `instanceof` để lấy giá trị cần kiểm tra.
2. Nếu giá trị là `null` hoặc không tương thích với `String`, type pattern thất bại: `instanceof` trả về `false`, không có `text` khả dụng từ lần match này.
3. Nếu giá trị khớp, pattern variable `text` được khởi tạo bằng giá trị đã kiểm tra (ở ví dụ là tham chiếu tới chuỗi `"Java"`). Phép kiểm tra trả về `true`.
4. Luồng thực thi vào nhánh `if`, nơi `text` đã có giá trị với kiểu tĩnh `String`. Không cần viết `(String) value` hay lệnh gán riêng.

`text` không được khởi tạo sẵn bằng `null` như một trường đối tượng; nó là biến cục bộ do pattern khai báo và được khởi tạo bởi quá trình matching. Nếu giá trị đầu vào là một `String` rỗng `""`, pattern **vẫn khớp**: điều kiện chỉ kiểm tra kiểu, không kiểm tra chuỗi có nội dung hay không.

| Giá trị của `value` | `value instanceof String text` | `text` có được gắn giá trị? |
| --- | --- | --- |
| `"Java"` | `true` | Có, tham chiếu tới `"Java"` |
| `""` | `true` | Có, tham chiếu tới chuỗi rỗng |
| `42` (một `Integer`) | `false` | Không |
| `null` | `false` | Không |

## 2. Khởi tạo ngay sau khi pattern khớp, dù cả điều kiện `if` có thể sai

```java
Object value = "   ";

if (value instanceof String text && !text.isBlank()) {
    System.out.println("Non-blank: " + text);
} else {
    System.out.println("Not a non-blank String");
}
```

`instanceof String text` đã **khớp và khởi tạo `text`**, vì `"   "` là một `String`. Sau đó Java mới đánh giá `!text.isBlank()`, cho kết quả `false`; vì thế toàn bộ biểu thức `&&` là `false` và chạy nhánh `else`. Kết quả:

```text
Not a non-blank String
```

Vì vậy, **“pattern đã khớp” không đồng nghĩa “toàn bộ điều kiện `if` là `true`”**. Trong nhánh `else`, không thể dùng `text`: nhánh này cũng có thể đến từ tình huống `value` là `null` hoặc `Integer`, khi pattern chưa từng khớp.

Toán tử `&&` có đánh giá ngắn mạch: vế phải chỉ được chạy nếu vế trái là `true`. Do đó `text` đã được khởi tạo khi đánh giá `text.isBlank()`. Ngược lại, đoạn sau **không biên dịch**:

```java
// SAI: vế phải của || chạy khi phép instanceof ở vế trái là false.
if (value instanceof String text || text.isEmpty()) {
    // ...
}
```

Ở vế phải `||`, chưa thể bảo đảm `text` đã khớp. Một biểu thức hợp lệ nhưng khác ý nghĩa là `!(value instanceof String text) || text.isBlank()`: vế phải chỉ chạy khi phép `instanceof` ban đầu **đúng**, do đó `text` đã được khởi tạo.

## 3. Phạm vi của biến phụ thuộc đường đi điều khiển

Java sử dụng **flow scoping**: compiler xét những nhánh có thể đi tới từng vị trí và chỉ cho dùng biến khi mọi đường đi hợp lệ đều bảo đảm pattern đã khớp.

**Trong nhánh đúng:**

```java
if (input instanceof String s) {
    System.out.println(s.length()); // Hợp lệ: s đã được khởi tạo
} else {
    // s không nằm trong scope ở đây
}
// Thông thường không thể dùng s ở đây: if có thể thất bại.
```

**Với phủ định `!`:**

```java
if (!(input instanceof String s)) {
    System.out.println("Not a String");
} else {
    System.out.println(s.length()); // Hợp lệ: nhánh else nghĩa là match đúng
}
```

**Sau một nhánh thoát sớm (guard clause):**

```java
static void printLength(Object input) {
    if (!(input instanceof String s)) {
        return;
    }
    System.out.println(s.length()); // Hợp lệ: muốn tới đây phải match thành công
}
```

Đây không phải cách “khởi tạo muộn” bằng một câu lệnh gán mới. `s` đã được khởi tạo **khi pattern khớp trong phép `instanceof`**; compiler suy luận rằng sau `return`, mọi đường đi còn tiếp tục đều có `s` hợp lệ.

**Biểu thức ba ngôi:** Với `input instanceof String s ? s.length() : 0`, `s` đã khởi tạo trong nhánh `?` khi điều kiện đúng, nhưng không thể tham chiếu ở nhánh `:` khi pattern sai.

**Vòng lặp:** `while (input instanceof String s)` kiểm tra pattern mỗi lần đánh giá điều kiện. Mỗi lần match thành công, `s` được gắn với giá trị của lần kiểm tra đó; trong thân vòng lặp có thể sử dụng `s`. Không nên suy ra từ quy tắc ngôn ngữ rằng JVM bắt buộc phải cấp phát một đối tượng mới cho biến ở mỗi vòng lặp.

## 4. Chương trình Java 17+ chạy độc lập

Lưu đoạn sau vào đúng file `PatternVariableLifecycle.java`:

```java
public class PatternVariableLifecycle {
    static void describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            System.out.println("String: " + text + " (" + text.length() + ")");
        } else {
            System.out.println("Khong phai chuoi khac rong");
        }
    }

    static void printAfterGuard(Object input) {
        if (!(input instanceof String text)) {
            System.out.println("Bo qua: khong phai String");
            return;
        }
        System.out.println("Sau guard: " + text.toUpperCase());
    }

    public static void main(String[] args) {
        describe("Java");
        describe("   ");
        describe(12);
        describe(null);
        printAfterGuard("pattern");
        printAfterGuard(99);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 PatternVariableLifecycle.java
java PatternVariableLifecycle
```

Kết quả chuẩn:

```text
String: Java (4)
Khong phai chuoi khac rong
Khong phai chuoi khac rong
Khong phai chuoi khac rong
Sau guard: PATTERN
Bo qua: khong phai String
```

Giải thích: với `"Java"`, pattern khớp, `text` được khởi tạo, rồi `isBlank()` trả về `false` nên vào nhánh đúng. Với `"   "`, `text` **vẫn được khởi tạo** nhưng điều kiện bổ sung không thỏa. Với `12` và `null`, pattern không khớp. Ở `printAfterGuard`, `return` loại bỏ các đường đi không khớp, nên `text` dùng được sau `if`.

## 5. `switch` và record pattern: Java 21+

Trong `switch` sử dụng pattern (tính năng chính thức từ Java 21), biến của một `case` được khởi tạo khi giá trị selector khớp với pattern của `case` đó, **trước khi** đánh giá điều kiện bảo vệ `when` và trước khi chạy thân nhánh:

```java
static String classify(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "Text: " + s;
        case String s -> "Blank String";
        case Integer n -> "Integer: " + n;
        case null -> "Null";
        default -> "Other";
    };
}
```

Ở `case String s when !s.isBlank()`, `s` đã có giá trị khi `when` gọi `s.isBlank()`. Nếu điều kiện `when` sai, `switch` xét tiếp nhánh phù hợp kế tiếp. Các biến cùng tên `s` trong hai nhãn `case` trên thuộc các vùng scope riêng. `case null` xử lý giá trị `null` mà không khai báo một pattern variable.

**Record pattern** (chính thức từ Java 21) vừa kiểm tra record vừa phân rã các component bằng những pattern lồng nhau:

```java
record Pair(Object left, Object right) {}

static void inspectPair(Object value) {
    if (value instanceof Pair(String left, Integer right)) {
        System.out.println(left + ": " + right);
    }
}
```

Chỉ khi record và **cả hai component pattern** đều khớp, nhánh `if` mới chạy với `left` và `right` đã được khởi tạo từ các component. Nếu một component không khớp (chẳng hạn `right` là `null`), toàn bộ record pattern thất bại và không thể sử dụng các biến đó ở nhánh thành công.

Hai ví dụ trong mục này cần `javac --release 21` (hoặc biên dịch trên JDK 21+ với mức ngôn ngữ tương ứng); ví dụ ở mục 4 tương thích Java 17.

## 6. Những hiểu nhầm cần tránh

- **Nhầm khai báo với khởi tạo:** cú pháp `instanceof String s` khai báo pattern variable; `s` chỉ nhận giá trị khi pattern match thành công lúc chạy. Không cần và không được thêm cú pháp `s = ...` vào chính type pattern.
- **Nhầm kết quả pattern với kết quả toàn điều kiện:** `instanceof` có thể đúng và khởi tạo `s`, trong khi phần kiểm tra sau `&&` làm `if` đi vào `else`.
- **Nhầm scope với vòng đời đối tượng:** pattern variable giữ một tham chiếu tới đối tượng đã match; nó không sao chép đối tượng `String`. Thay đổi biến nguồn về sau không tự cập nhật giá trị đã gắn cho pattern variable.
- **Cho rằng pattern variable luôn `final`:** từ phiên bản Java 16 của `instanceof` pattern matching, biến mẫu không mặc nhiên là `final`; có thể gán lại trong scope hợp lệ (nếu không khai báo `final`). Việc gán lại `s` không đổi giá trị biến nguồn.
- **Giả định match với `null`:** type pattern `String s` không khớp `null`, khác với ép kiểu `(String) null` vốn cho ra `null`.
- **Dùng biến ngoài nơi compiler chứng minh đã match:** ở vế phải của `||` với điều kiện `instanceof` không phủ định, nhánh `else` hoặc sau `if` có thể thiếu bảo đảm khởi tạo và sẽ bị từ chối khi biên dịch.

**Quy tắc nhớ:** *Pattern matching thành công thì biến được khởi tạo; Java chỉ cho sử dụng biến trên các đường đi mà kết quả thành công đó được bảo đảm.* Phân biệt hai ý này sẽ giúp đọc đúng các biểu thức logic, guard clause, `switch` và record pattern.

### Tài liệu chính thức

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
