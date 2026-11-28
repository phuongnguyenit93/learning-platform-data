# Kiểm thử biên dịch các biểu thức boolean sau khi refactor pattern

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Cú pháp này vừa kiểm tra kiểu runtime vừa khai báo biến pattern, và compiler xác định phạm vi biến dựa trên kết quả đúng/sai của biểu thức boolean. Vì vậy, khi refactor điều kiện, thay đổi vị trí của `&&`, `||`, `!` hoặc tách điều kiện thành biến boolean có thể làm thay đổi nơi biến pattern được phép sử dụng.

Một biểu thức boolean vẫn có thể trả về cùng kết quả sau khi refactor nhưng không còn giữ được thông tin luồng điều khiển mà compiler cần để xác nhận pattern đã khớp. Do đó, sau khi thay đổi điều kiện có pattern, cần biên dịch lại để kiểm tra flow scoping, rồi kiểm thử hành vi ở runtime.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích trong Java hiện đại, bên cạnh `record` và các API Stream. Bài này hướng dẫn kiểm tra các biểu thức `&&`, `||`, `!`, toán tử ba ngôi và guard clause sau refactor; phân biệt lỗi phạm vi với lỗi hành vi; và sử dụng `javac --release 16` để xác nhận mã tương thích Java 16. Các ví dụ dùng cú pháp đã được chuẩn hóa, không cần preview feature.

## 1. Vì sao phải biên dịch lại sau khi refactor điều kiện?

Compiler không chỉ kiểm tra biểu thức có kiểu `boolean`. Với pattern matching, compiler còn theo dõi những đường đi mà tại đó pattern chắc chắn đã khớp. Ví dụ:

```java
static void printText(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        System.out.println(text.strip());
    }
}
```

Vế phải của `&&` chỉ được đánh giá khi vế trái đúng. Vì vậy, khi Java gọi `text.isBlank()`, pattern `value instanceof String text` đã khớp. Thân `if` cũng chỉ chạy khi toàn điều kiện đúng, nên `text` có mặt trong thân.

Nếu refactor điều kiện làm mất quan hệ đó, compiler sẽ từ chối các vị trí dùng biến không còn được bảo đảm. Biên dịch lại giúp phát hiện vấn đề ngay sau thay đổi, thay vì chờ một nhánh runtime ít gặp mới bộc lộ lỗi.

## 2. Kiểm tra trường hợp `&&`

Với `&&`, vế phải chỉ chạy khi vế trái đúng. Đây là cấu trúc thường dùng để kiểm tra kiểu trước rồi kiểm tra tiếp dữ liệu:

```java
static void validateText(Object value) {
    if (value instanceof String text
            && !text.isBlank()
            && text.length() <= 40) {
        System.out.println("Hợp lệ: " + text.strip());
    }
}
```

Khi refactor, giữ phép kiểm tra pattern ở vế trái của chuỗi `&&` nếu các vế sau cần dùng biến:

```java
static boolean isAcceptable(String text) {
    return !text.isBlank() && text.length() <= 40;
}

static void validateText(Object value) {
    if (value instanceof String text && isAcceptable(text)) {
        System.out.println(text.strip());
    }
}
```

Ở phiên bản này, phương thức trợ giúp nhận tham số có kiểu `String`. Pattern được xác nhận trước khi gọi `isAcceptable(text)`, nên cả lời gọi helper và thân `if` đều sử dụng được `text`.

Không tách phép kiểm tra kiểu khỏi biểu thức theo cách khiến compiler mất liên hệ với biến pattern. Phần tiếp theo trình bày trường hợp đó.

## 3. Refactor sang biến boolean không mang theo pattern binding

Đoạn mã sau không biên dịch:

```java
static void printText(Object value) {
    boolean isText = value instanceof String text;

    if (isText) {
        System.out.println(text); // Lỗi biên dịch: text không nằm trong phạm vi.
    }
}
```

Biến `isText` chỉ lưu kết quả `true` hoặc `false`. Nó không lưu đối tượng `String` và cũng không giữ mối liên hệ luồng điều khiển giữa kết quả boolean với pattern variable `text`. Khi bước vào thân `if (isText)`, compiler không thể chứng minh `text` đã khớp.

Giữ pattern ngay trong điều kiện sử dụng biến là cách sửa đơn giản:

```java
static void printText(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }
}
```

Nếu cần tái sử dụng kết quả kiểm tra qua nhiều vị trí, lưu giá trị nguồn vào biến có kiểu phù hợp rồi thực hiện pattern matching tại nơi cần biến đã kiểm tra:

```java
static void process(Object input) {
    Object candidate = input;

    if (candidate instanceof String text) {
        System.out.println(text.strip());
    }

    if (candidate instanceof Integer number) {
        System.out.println(number + 1);
    }
}
```

Hai điều kiện kiểm tra cùng một `candidate`, nhưng mỗi pattern variable chỉ được dùng trong phạm vi mà compiler xác định cho điều kiện tương ứng.

## 4. Refactor điều kiện `||` và kiểm tra cả hai nhánh

Với `||`, vế phải chỉ được đánh giá khi vế trái sai. Do đó, pattern dương ở vế trái không thể được dùng ở vế phải:

```java
static void check(Object value) {
    if (value instanceof String text || text.isBlank()) {
        // Lỗi biên dịch: vế phải chỉ chạy khi pattern chưa khớp.
        System.out.println(text);
    }
}
```

Thân `if` cũng không được dùng `text`, vì điều kiện có thể đúng do vế phải dù pattern không khớp.

Một trường hợp hợp lệ là phủ định pattern ở vế trái:

```java
static void printNonBlank(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return;
    }

    System.out.println(text.strip());
}
```

Khi vế phải `text.isBlank()` được đánh giá, vế trái phủ định đã sai; do đó pattern gốc đã khớp. Sau `if`, điều kiện OR sai chỉ khi cả hai vế đều sai, nên `text` chắc chắn là `String` không blank. Nhánh không hợp lệ kết thúc bằng `return`, vì vậy compiler cho phép dùng `text` ở phần sau.

Khi refactor biểu thức này, hãy kiểm tra riêng ba vị trí: vế phải của OR, thân `if` và câu lệnh sau `if`. Một biến có thể dùng được ở vế phải nhưng không dùng được trong thân `if`.

## 5. Dấu ngoặc làm thay đổi phạm vi có thể suy ra

Không chỉ đổi toán tử, di chuyển dấu ngoặc cũng có thể thay đổi ý nghĩa boolean và phạm vi pattern:

```java
static void process(Object value, boolean fallback) {
    if (value instanceof String text
            && (text.length() > 3 || fallback)) {
        System.out.println(text.strip());
    }
}
```

Điều kiện ngoài cùng là `A && B`, trong đó `A` là phép kiểm tra pattern. Nếu toàn điều kiện đúng, `A` bắt buộc phải đúng, vì vậy `text` được dùng trong biểu thức con và thân `if`.

Nếu chuyển `|| fallback` ra ngoài:

```java
if (value instanceof String text && text.length() > 3 || fallback) {
    // Không thể dựa vào text ở đây.
}
```

Điều kiện có thể đúng chỉ vì `fallback` đúng, kể cả khi `value` không phải `String`. Vì vậy, compiler không thể đảm bảo pattern đã khớp trong thân `if`.

Khi refactor, hãy viết rõ cấu trúc bằng dấu ngoặc và kiểm tra cả ý nghĩa boolean lẫn vị trí sử dụng biến. Dấu ngoặc có thể không làm thay đổi thứ tự ưu tiên như người viết dự định nếu đặt sai vị trí.

## 6. Kiểm tra toán tử phủ định `!` và guard clause

Mẫu guard clause sau đây cho phép dùng biến pattern sau câu lệnh `if`:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("value phải là String");
    }

    return text.strip();
}
```

Nếu pattern không khớp, `throw` kết thúc luồng. Nếu chương trình đi đến `return text.strip()`, pattern chắc chắn đã khớp.

Khi đổi `throw` thành một lời gọi helper chỉ ghi log, luồng có thể tiếp tục và biến không còn được bảo đảm:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        logInvalid(value); // Phương thức này có thể trả về bình thường.
    }

    return text.strip(); // Lỗi biên dịch: nhánh không khớp có thể đi tiếp.
}
```

Sửa bằng cách giữ câu lệnh kết thúc luồng trong nhánh không hợp lệ:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        logInvalid(value);
        throw new IllegalArgumentException("value phải là String");
    }

    return text.strip();
}
```

Sau refactor, hãy xác minh rằng mọi đường đi mà pattern chưa khớp đều thực sự kết thúc bằng `return`, `throw` hoặc một cấu trúc điều khiển không thể đi tiếp đến vị trí sử dụng biến.

## 7. Refactor điều kiện thành helper method

Một helper trả về `boolean` chỉ trả về kết quả kiểm tra; nó không chuyển biến pattern ra caller:

```java
static boolean isNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}

static void process(Object value) {
    if (isNonBlankText(value)) {
        // Không có biến pattern text trong phạm vi này.
    }
}
```

Nếu caller cần biến `String`, có thể giữ pattern ở caller và đưa phần kiểm tra bổ sung vào helper nhận `String`:

```java
static boolean isNonBlankText(String text) {
    return !text.isBlank();
}

static void process(Object value) {
    if (value instanceof String text && isNonBlankText(text)) {
        System.out.println(text.strip());
    }
}
```

Nếu mục tiêu là đóng gói cả thao tác chuyển đổi kiểu và trả kết quả đã định kiểu, hãy thiết kế helper trả về kiểu dữ liệu phù hợp, chẳng hạn `Optional<String>`:

```java
import java.util.Optional;

static Optional<String> asString(Object value) {
    if (value instanceof String text) {
        return Optional.of(text);
    }
    return Optional.empty();
}

static void process(Object value) {
    asString(value).ifPresent(text -> System.out.println(text.strip()));
}
```

Không dùng helper `boolean` với kỳ vọng compiler sẽ liên kết kết quả trả về với một pattern variable bên trong helper. Ranh giới phương thức không truyền flow scope sang caller.

## 8. Kiểm tra biểu thức điều kiện ba ngôi `?:`

Với toán tử ba ngôi, nhánh sau `?` được đánh giá khi điều kiện đúng; nhánh sau `:` được đánh giá khi điều kiện sai. Pattern variable phải nằm trong nhánh mà kết quả điều kiện chứng minh pattern đã khớp:

```java
static String display(Object value) {
    return value instanceof String text
            ? text.strip()
            : "(not a string)";
}
```

Nếu phủ định điều kiện, biến có thể dùng ở nhánh sau `:`:

```java
static String display(Object value) {
    return !(value instanceof String text)
            ? "(not a string)"
            : text.strip();
}
```

Sau refactor, không chuyển `text` ra ngoài biểu thức ba ngôi nếu không có một phép kiểm tra khác xác nhận kiểu. Ví dụ, lưu kết quả vào `String label` không làm biến pattern `text` tự động tồn tại trong các câu lệnh tiếp theo.

## 9. Quy trình kiểm tra bằng compiler

Khi refactor điều kiện có pattern matching, có thể dùng quy trình sau:

1. **Giữ phiên bản nhỏ nhất:** tách riêng biểu thức vừa thay đổi, tránh sửa đồng thời nhiều điều kiện không liên quan.
2. **Kiểm tra toán tử:** xác định vế nào chạy khi điều kiện trước đúng hoặc sai; chú ý short-circuit của `&&` và `||`.
3. **Kiểm tra từng vị trí dùng biến:** vế phải, thân `if`, nhánh `else`, nhánh `?`, nhánh `:` và câu lệnh sau guard có thể có phạm vi khác nhau.
4. **Biên dịch theo Java 16:** dùng `javac --release 16` để xác nhận cú pháp và API mục tiêu.
5. **Đọc lỗi đầu tiên:** lỗi không tìm thấy biến hoặc biến không nằm trong phạm vi thường chỉ ra pattern không được chứng minh tại vị trí sử dụng. Sửa điều kiện trước khi thay bằng ép kiểu thủ công.
6. **Chạy kiểm thử hành vi:** compiler không xác nhận logic nghiệp vụ, tác dụng phụ hoặc mọi nhánh runtime. Kiểm tra cả giá trị `null`, kiểu đúng, kiểu sai, chuỗi rỗng và các điều kiện fallback liên quan.

Ví dụ lệnh biên dịch một lớp có khai báo `package example;`, chạy từ thư mục gốc của dự án và dùng thư mục hiện tại làm đích đầu ra:

```bash
javac --release 16 -Xlint:all -d . src/main/java/example/PatternBooleanCheck.java
```

Với dự án nhiều lớp, truyền đầy đủ các file nguồn cần thiết hoặc dùng cấu hình build của dự án với mức phát hành Java 16. `--release 16` kiểm tra ngôn ngữ và API theo Java 16; không cần bật preview cho pattern matching `instanceof` đã hoàn thiện trong phiên bản này.

## 10. Ví dụ hoàn chỉnh để kiểm tra sau refactor

```java
package example;

import java.util.Optional;

public class PatternBooleanCheck {

    static boolean isAllowed(String text) {
        return !text.isBlank() && text.length() <= 40;
    }

    static Optional<String> asString(Object value) {
        if (value instanceof String text) {
            return Optional.of(text);
        }
        return Optional.empty();
    }

    static String inlineCheck(Object value) {
        if (value instanceof String text && isAllowed(text)) {
            return text.strip();
        }
        return "(invalid)";
    }

    static String guardCheck(Object value) {
        if (!(value instanceof String text) || !isAllowed(text)) {
            return "(invalid)";
        }
        return text.strip();
    }

    static String helperCheck(Object value) {
        return asString(value)
                .filter(PatternBooleanCheck::isAllowed)
                .map(String::strip)
                .orElse("(invalid)");
    }

    public static void main(String[] args) {
        Object[] samples = {" Java 16 ", "   ", 42, null};

        for (Object sample : samples) {
            System.out.println(inlineCheck(sample));
            System.out.println(guardCheck(sample));
            System.out.println(helperCheck(sample));
        }
    }
}
```

Ví dụ này cho ba cách tổ chức khác nhau:

- `inlineCheck` giữ pattern và điều kiện kiểm tra trong cùng biểu thức `&&`.
- `guardCheck` loại bỏ sớm kiểu sai hoặc nội dung không đạt điều kiện; sau `if`, pattern đã được xác nhận.
- `helperCheck` dùng `Optional<String>` để truyền giá trị đã định kiểu qua ranh giới phương thức, không trông chờ một biến pattern bên trong helper xuất hiện ở caller.

Có thể biên dịch bằng JDK 16 trở lên:

```bash
javac --release 16 -Xlint:all -d . src/main/java/example/PatternBooleanCheck.java
java -cp . example.PatternBooleanCheck
```

## 11. Phân biệt kiểm tra biên dịch và kiểm thử runtime

| Loại kiểm tra | Có thể xác nhận | Không tự xác nhận |
|---|---|---|
| Biên dịch với `javac --release 16` | Cú pháp Java 16, kiểu dữ liệu, phạm vi pattern và điều kiện capture | Kết quả nghiệp vụ đúng với mọi đầu vào. |
| Unit test | Hành vi của các nhánh được chạy với dữ liệu kiểm thử | Các nhánh chưa được kiểm thử hoặc lỗi flow scoping vốn đã bị compiler chặn. |
| Integration test | Tương tác giữa các thành phần và nguồn dữ liệu thực tế | Tính đúng đắn của mọi biểu thức boolean chưa được thực thi. |
| Static analysis/IDE inspection | Một số vấn đề về kiểu, nullability và chất lượng mã | Thay thế hoàn toàn compiler và kiểm thử runtime. |

Compiler là bước bắt buộc để xác nhận pattern variable còn nằm trong phạm vi hợp lệ sau refactor. Unit test và integration test bổ sung bằng chứng về hành vi thực tế. Hai loại kiểm tra phục vụ mục đích khác nhau và nên được dùng cùng nhau.

## 12. Checklist khi refactor biểu thức boolean có pattern

- Phép kiểm tra `instanceof` còn nằm trước các vế cần sử dụng biến trong chuỗi `&&` không?
- Có chuyển `&&` thành `||` hoặc di chuyển dấu ngoặc khiến thân `if` có thể chạy khi pattern chưa khớp không?
- Có tách điều kiện thành biến boolean rồi mong đợi pattern variable vẫn khả dụng ở nhánh sau không?
- Có chuyển logic vào helper trả về `boolean` và kỳ vọng binding được truyền ra caller không?
- Với guard clause, mọi đường đi pattern chưa khớp có kết thúc bằng `return` hoặc `throw` không?
- Với `?:`, biến có chỉ được dùng trong nhánh mà điều kiện chứng minh pattern đã khớp không?
- Đã biên dịch theo `--release 16` và chạy kiểm thử cho cả đầu vào đúng, sai, `null` và trường hợp fallback chưa?

Khi refactor biểu thức boolean có pattern matching, hãy bảo toàn quan hệ luồng điều khiển mà compiler dùng để chứng minh pattern đã khớp. Tách một kết quả boolean hoặc chuyển logic qua helper trả về `boolean` không mang biến pattern theo cùng. Biên dịch với `javac --release 16`, sau đó kiểm thử runtime các nhánh quan trọng, giúp phát hiện sớm lỗi phạm vi và xác nhận hành vi của mã Java hiện đại.
