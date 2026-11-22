# Giữ điều kiện dễ đọc khi kết hợp nhiều phép kiểm tra với biến mẫu instanceof

Khi xử lý dữ liệu có kiểu chưa biết chắc ở thời điểm biên dịch, Java cho phép dùng **pattern matching for `instanceof`** để vừa kiểm tra kiểu vừa gắn một biến mẫu: `if (value instanceof String text)`. Khi phối hợp thêm điều kiện về độ dài, nội dung, trạng thái hoặc quyền truy cập, rất dễ viết một biểu thức Boolean dài và khó nhìn ra **khi nào biến `text` thực sự tồn tại, kiểm tra nào được chạy và kiểm tra nào bị bỏ qua**.

Điểm học tập chính của bài này thuộc **phạm vi biến mẫu (flow scoping)**: phạm vi của một *pattern variable* phụ thuộc vào việc chương trình đã xác định mẫu khớp hay chưa, không đơn thuần là dấu ngoặc nhọn. Để điều kiện dễ đọc và an toàn, cần hiểu ngữ nghĩa của `&&`, `||`, `!`, thứ tự đánh giá từ trái sang phải và cách tách một điều kiện phức tạp thành nhiều bước có tên rõ ràng.

**Phiên bản:** Pattern matching for `instanceof` đã trở thành tính năng chính thức từ **Java 16** (JEP 394). Dù nằm trong module Java 14, các ví dụ sử dụng **Java 17+ ổn định**, không dựa vào cú pháp preview cũ.

## 1. Biến mẫu là gì và khi nào được dùng?

Ví dụ cổ điển thường tách kiểm tra và ép kiểu:

~~~java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

Cách viết Java hiện đại:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Hai đoạn trên là **minh họa bên trong phương thức có biến `Object value`**. Ở phiên bản mới:

- `value instanceof String text` là **type pattern test**.
- Nếu `value` không-null và là `String`, mẫu **khớp**, biến `text` được khởi tạo bằng chính tham chiếu có kiểu `String`.
- Trong nhánh `if` mà Java biết mẫu đã khớp, `text.length()` hợp lệ; không cần ép kiểu viết tay.
- Nếu không khớp, không thể tự ý truy cập `text` như thể nó đã được khởi tạo.

Pattern variable chỉ được dùng ở những vị trí nơi việc mẫu đã khớp được bảo đảm theo **luồng điều khiển**. Java phân tích điều này tại thời điểm biên dịch, giúp tránh truy cập biến chưa khởi tạo.

### Khác biệt với biến khai báo thông thường

Một biến địa phương như `String text = "hi";` có phạm vi từ vị trí khai báo theo quy tắc block. Biến mẫu `text` của `instanceof` lại có phạm vi phụ thuộc vào điều kiện nào thực sự đúng/sai. Vì thế, hai dòng có dấu ngoặc rất giống nhau vẫn có thể khác về tính hợp lệ của `text`.

## 2. Kết hợp nhiều điều kiện bằng `&&`: kiểm tra kiểu trước, dùng biến sau

Toán tử **conditional AND `&&`** đánh giá vế trái trước; chỉ đánh giá vế phải nếu vế trái `true`. Chính cơ chế ngắn mạch (*short-circuit*) này làm cho biểu thức sau hợp lệ:

~~~java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 3) {
    System.out.println("Accepted: " + text);
}
~~~

Đoạn này nằm trong phương thức có `Object value`.

Thứ tự thực thi là:

1. Kiểm tra `value instanceof String text`.
2. Nếu `false`, toàn bộ chuỗi `&&` trả `false`; **không** đánh giá `text.isBlank()` hay `text.length()`.
3. Nếu `true`, biến `text` đã được gắn kiểu `String`, nên `!text.isBlank()` được đánh giá an toàn.
4. Chỉ khi điều kiện thứ hai `true`, Java mới đánh giá `text.length() >= 3`.
5. Nếu tất cả đúng, chương trình vào nhánh `if` và `text` vẫn khả dụng.

Trong Java, `value instanceof String text` cũng trả `false` với `value == null`; không phát sinh `NullPointerException` ở việc thử mẫu này.

### Quy tắc viết dễ đọc

Đặt các điều kiện theo trình tự logic:

- **Xác định kiểu:** `value instanceof String text`.
- **Kiểm tra giả định để dùng an toàn:** ví dụ `!text.isBlank()` trước khi dùng dữ liệu chuỗi.
- **Ràng buộc đơn giản:** `text.length() >= 3`.
- **Quy tắc nghiệp vụ có tên rõ ràng:** `allowedPrefix(text)` hoặc `isValidCode(text)`.

Ví dụ:

~~~java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 3
        && allowedPrefix(text)) {
    use(text);
}
~~~

Đây là đoạn minh họa; `allowedPrefix(String)` và `use(String)` phải được định nghĩa ở ngữ cảnh sử dụng. Việc tách helper giúp người đọc hiểu **ý nghĩa** kiểm tra thay vì phải giải mã một biểu thức Boolean dài.

**Quan trọng:** `&&` không đồng nghĩa với `&`. Với toán hạng Boolean, `&` đánh giá cả hai vế, không short-circuit. Khi vế phải chỉ an toàn sau một type pattern test, dùng `&&`.

## 3. `||` và phạm vi biến: vì sao không thể dùng mẫu chưa khớp?

Toán tử **conditional OR `||`** cũng đánh giá từ trái sang phải nhưng **chỉ đánh giá vế phải khi vế trái `false`**. Vì thế, đoạn sau **không biên dịch**:

~~~java
// CỐ Ý SAI: text chưa chắc đã được gắn.
if (value instanceof String text || text.isBlank()) {
    System.out.println("checked");
}
~~~

Nếu vế trái `false`, `value` không khớp mẫu `String text`. Chính lúc đó `||` mới đánh giá `text.isBlank()`, nhưng biến `text` chưa được gắn. Đây là vấn đề **flow scoping**.

Cũng không thể lấy kiểu logic “một trong hai điều kiện được chấp nhận” rồi tự giả định biến mẫu luôn có trong body:

~~~java
// CỐ Ý SAI: nhánh if có thể vào nhờ allowFallback
// dù value không phải String, nên text không chắc đã gắn.
if ((value instanceof String text && text.length() >= 3)
        || allowFallback) {
    System.out.println(text);
}
~~~

Đoạn trên là minh họa với `Object value` và `boolean allowFallback`. Thậm chí nếu phần có `&&` được viết đúng, body phía sau `||` vẫn **không được bảo đảm** `text` đã khớp: `allowFallback` có thể làm cả điều kiện `true` khi mẫu không khớp.

**Cách sửa khi cả hai trường hợp phải xử lý khác nhau:** tách nhánh:

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println("text=" + text);
} else if (allowFallback) {
    System.out.println("fallback");
}
~~~

Bằng cách này, `text` chỉ xuất hiện ở nhánh nơi mẫu đã được kiểm tra thành công.

### `||` vẫn hữu ích trong kiểm tra dữ liệu sau khi đã biết kiểu

Đây là ví dụ **hợp lệ**:

~~~java
if (value instanceof String text
        && (text.startsWith("A") || text.startsWith("B"))) {
    System.out.println(text);
}
~~~

`text` được gắn từ mẫu bên trái của `&&`, nên có thể dùng ở cả hai vế bên trong nhóm `(...)`. Dấu ngoặc thể hiện ý đồ: sau khi đúng kiểu, chỉ cần **một** trong hai tiền tố được chấp nhận.

Đừng rải những dấu ngoặc không cần thiết, nhưng hãy **chủ động nhóm logic `OR`** bên trong điều kiện `AND` để cả người đọc lẫn reviewer thấy rõ ranh giới.

## 4. Phủ định `!` và guard clause giúp giảm lồng nhau

Khi kiểm tra đầu vào rồi có nhiều quy tắc bổ sung, **guard clause** giúp tách các tình huống không hợp lệ ra sớm:

~~~java
static String describe(Object value) {
    if (!(value instanceof String text)) {
        return "not-text";
    }

    if (text.isBlank()) {
        return "blank";
    }

    return "length=" + text.length();
}
~~~

Đây là một phương thức Java độc lập có thể đặt trong class. Đường đi sau `if` đầu tiên chỉ được thực hiện khi mẫu `String text` **khớp** vì nhánh không khớp đã `return`. Do đó `text` có phạm vi hợp lệ ở các câu lệnh sau guard.

Mẫu này đặc biệt rõ ràng khi bạn có nhiều bước:

1. **Từ chối sai kiểu**.
2. **Chuẩn hóa dữ liệu** nếu cần.
3. **Từ chối giá trị rỗng**.
4. **Kiểm tra các ràng buộc nghiệp vụ khác**.
5. **Thực hiện nghiệp vụ chính**.

### Một biểu thức OR với mẫu phủ định cũng có thể hợp lệ

~~~java
if (!(value instanceof String text) || text.isBlank()) {
    return "invalid";
}
return "valid:" + text;
~~~

Đoạn này minh họa trong phương thức trả `String` có tham số `Object value`. Vì vế phải của `||` **chỉ chạy khi** `!(value instanceof String text)` là `false`, trường hợp ấy đồng nghĩa mẫu `String text` đã khớp. Vậy `text.isBlank()` là hợp lệ. Khi vượt qua guard, `text` vẫn được biết là đã gắn.

Cách viết gộp này có ích với hai điều kiện đơn giản. Nhưng với nhiều phép kiểm tra, tách thành các guard clause thường dễ hiểu hơn, nhất là với người đang học cách phạm vi biến mẫu hoạt động.

**Phân biệt hai trường hợp:**

| Biểu thức | Hợp lệ? | Lý do |
|---|---|---|
| `value instanceof String s && !s.isBlank()` | Có | Vế phải chạy khi mẫu khớp |
| `value instanceof String s || s.isBlank()` | Không | Vế phải chạy khi mẫu không khớp |
| `!(value instanceof String s) || s.isBlank()` | Có | Vế phải chạy khi phủ định sai, tức mẫu đã khớp |
| `value instanceof String s && (s.startsWith("A") || s.startsWith("B"))` | Có | `s` đã gắn trước khi xét nhóm OR |
| `(value instanceof String s && s.length() > 2) || fallback` và dùng `s` trong body | Không | Body có thể chạy chỉ nhờ `fallback` |

## 5. Tránh điều kiện dài bằng cách đặt tên cho phép kiểm tra

Không phải mọi logic đều nên nằm trong một biểu thức `if`. Xét cách viết khó review:

~~~java
if (value instanceof String s
        && !s.isBlank()
        && s.strip().length() >= 3
        && s.strip().length() <= 8
        && (s.strip().startsWith("A")
            || s.strip().startsWith("B"))) {
    // Xử lý chuỗi hợp lệ.
}
~~~

Đây là một đoạn minh họa trong phương thức có `Object value`. Các lời gọi `strip()` được lặp lại nhiều lần; dù `String.strip()` không thay đổi đối tượng gốc, biểu thức trở nên dài và che khuất mục đích kiểm tra.

**Cách rõ ràng hơn:** dùng guard clause và tên biến diễn đạt chính sách:

~~~java
static String classify(Object value) {
    if (!(value instanceof String text)) {
        return "not-text";
    }

    String code = text.strip();
    if (code.isEmpty()) {
        return "blank";
    }

    if (!hasAllowedLength(code)) {
        return "bad-length";
    }

    if (!hasAllowedPrefix(code)) {
        return "bad-prefix";
    }

    return "ok:" + code;
}

static boolean hasAllowedLength(String code) {
    return code.length() >= 3 && code.length() <= 8;
}

static boolean hasAllowedPrefix(String code) {
    return code.startsWith("A") || code.startsWith("B");
}
~~~

Các phương thức trên **có thể được đặt cùng một class** và biên dịch trên Java 17. Lợi ích:

- `text` chỉ được dùng sau khi mẫu `String` chắc chắn khớp.
- `strip()` được gọi một lần và kết quả được đặt tên `code`.
- `hasAllowedLength` và `hasAllowedPrefix` trình bày **quy tắc** rõ hơn dãy toán tử.
- Từng lý do từ chối được biểu diễn bằng một kết quả riêng, thuận tiện cho kiểm thử.
- Thứ tự kiểm tra được đọc từ trên xuống như chuỗi quyết định, không cần suy luận quá sâu về dấu ngoặc và phạm vi biến mẫu.

Không nhất thiết tách mọi phép so sánh nhỏ thành helper. Hãy tách khi tên helper giúp diễn đạt nghiệp vụ, khi điều kiện được tái sử dụng hoặc khi việc tách giảm rủi ro hiểu sai.

## 6. Kết hợp nhiều type patterns và điều kiện an toàn

### 6.1. Kiểm tra collection và phần tử đầu tiên

Một ứng dụng có thể cần kiểm tra đầu vào là `List`, list không rỗng và phần tử đầu là chuỗi có nội dung. Dạng điều kiện ngắn gọn:

~~~java
static String firstText(Object value) {
    if (value instanceof java.util.List<?> items
            && !items.isEmpty()
            && items.get(0) instanceof String first
            && !first.isBlank()) {
        return "first:" + first.strip();
    }

    return "first:missing";
}
~~~

Đây là **phương thức độc lập**, dùng tên lớp `java.util.List<?>` đã được viết đầy đủ nên không cần import.

Thứ tự các điều kiện **có ý nghĩa an toàn**:

1. `value instanceof List<?> items` xác nhận kiểu, đồng thời tạo biến `items`.
2. `!items.isEmpty()` đảm bảo thao tác lấy chỉ số `0` hợp lệ đối với một list bình thường.
3. `items.get(0) instanceof String first` kiểm tra kiểu phần tử đầu và gắn biến `first`.
4. `!first.isBlank()` chỉ chạy nếu mẫu `String first` đã khớp.

Việc đảo `items.get(0)` lên trước `!items.isEmpty()` có thể gây `IndexOutOfBoundsException` với list rỗng. Việc dùng `||` thay cho chuỗi `&&` có thể làm các biến mẫu không còn được bảo đảm. Đây là một ví dụ tốt cho việc **thứ tự an toàn quan trọng hơn độ ngắn**.

Với list do luồng khác sửa đổi đồng thời, việc kiểm tra `isEmpty()` trước `get(0)` không tự đảm bảo dữ liệu không bị thay đổi giữa hai phép gọi. Cần đồng bộ, snapshot hoặc cơ chế collection phù hợp nếu đó là yêu cầu thực tế.

### 6.2. Phân nhánh theo kiểu khác nhau

Nếu nghiệp vụ xử lý String và Integer theo hai cách độc lập, **`if / else if`** thường dễ đọc hơn phép OR dài:

~~~java
static String describeType(Object value) {
    if (value instanceof String text) {
        return "text:" + text;
    } else if (value instanceof Integer number) {
        return "number:" + number;
    }

    return "unsupported";
}
~~~

Mỗi biến mẫu chỉ cần hiện diện ở nhánh của mình. Không có lý do phải gom mọi kiểu và điều kiện vào một mệnh đề Boolean rồi cố sử dụng `text` hoặc `number` ở vùng chưa được đảm bảo.

### 6.3. Với cùng một kiểu nhưng nhiều điều kiện thay thế

Nếu một `String` được chấp nhận khi bắt đầu bằng `"A"` **hoặc** kết thúc bằng `"Z"`, hãy nhóm OR bên trong AND:

~~~java
if (value instanceof String text
        && !text.isBlank()
        && (text.startsWith("A") || text.endsWith("Z"))) {
    use(text);
}
~~~

Đây là đoạn minh họa có `Object value` và phương thức `use(String)`. Cấu trúc phản ánh đúng ngữ nghĩa: **kiểu đúng** AND **không rỗng** AND (**cách A** OR **cách B**).

## 7. Chương trình hoàn chỉnh Java 17+: dễ đọc, đúng phạm vi biến mẫu

Tạo tệp **`ReadablePatternConditionsDemo.java`**:

~~~java
import java.util.List;

public class ReadablePatternConditionsDemo {

    private static boolean hasAllowedLength(String code) {
        return code.length() >= 3 && code.length() <= 8;
    }

    private static boolean hasAllowedPrefix(String code) {
        return code.startsWith("A") || code.startsWith("B");
    }

    private static String classify(Object value) {
        if (!(value instanceof String text)) {
            return "not-text";
        }

        String code = text.strip();
        if (code.isEmpty()) {
            return "blank";
        }
        if (!hasAllowedLength(code)) {
            return "bad-length:" + code;
        }
        if (!hasAllowedPrefix(code)) {
            return "bad-prefix:" + code;
        }
        return "ok:" + code;
    }

    private static String firstText(Object value) {
        if (value instanceof List<?> items
                && !items.isEmpty()
                && items.get(0) instanceof String first
                && !first.isBlank()) {
            return "first:" + first.strip();
        }
        return "first:missing";
    }

    private static String smallInteger(Object value) {
        if (value instanceof Integer number
                && number >= 1
                && number <= 3) {
            return "small-int:" + number;
        }
        return "other";
    }

    public static void main(String[] args) {
        Object[] samples = {
                " A12 ", "B2", "ZZZ", "  ", 42, "ALPHABET9"
        };

        for (Object value : samples) {
            System.out.println(classify(value));
        }

        System.out.println(firstText(List.of(" java ", 1)));
        System.out.println(firstText(List.of(1, "java")));
        System.out.println(firstText(List.of("   ", 1)));
        System.out.println(smallInteger(2));
        System.out.println(smallInteger(5));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ReadablePatternConditionsDemo.java
java ReadablePatternConditionsDemo
~~~

**Standard output chính xác:**

~~~text
ok:A12
bad-length:B2
bad-prefix:ZZZ
blank
not-text
bad-length:ALPHABET9
first:java
first:missing
first:missing
small-int:2
other
~~~

### Giải thích kết quả

- `" A12 "` được `strip()` thành `"A12"`; độ dài `3` nằm trong khoảng `3..8` và tiền tố `A` được chấp nhận.
- `"B2"` có độ dài `2`, không đi tiếp tới kiểm tra tiền tố mà bị từ chối bằng `bad-length`.
- `"ZZZ"` đạt độ dài nhưng không bắt đầu bằng `A` hoặc `B`.
- `"  "` trở thành chuỗi rỗng sau `strip()`, bị từ chối với `blank`.
- `42` không phải `String` nên guard clause trả `not-text`; những kiểm tra trên `String` không chạy.
- `"ALPHABET9"` có `9` ký tự nên bị từ chối trước khi xét tiền tố.
- List đầu tiên có phần tử đầu là `" java "`, khớp `String first`, không blank và được `strip()` để in `first:java`.
- List thứ hai có phần tử đầu là `Integer`, không khớp `String first`.
- List thứ ba có phần tử đầu là chuỗi chỉ gồm khoảng trắng; mẫu kiểu khớp nhưng `first.isBlank()` trả `true`, nên bị từ chối.
- `smallInteger(2)` khớp mẫu `Integer number` và khoảng `1..3`; `smallInteger(5)` khớp kiểu nhưng ngoài khoảng nên trả `other`.

Ở ví dụ này, điều kiện được tổ chức theo đúng **thứ tự an toàn** và mỗi biến mẫu chỉ xuất hiện khi trình biên dịch biết nó đã khớp.

## 8. Thứ tự đánh giá, short-circuit và tác dụng phụ

**Đừng chỉ nhìn kết quả Boolean.** Với các phương thức có tác dụng phụ, đổi chỗ điều kiện có thể thay đổi log, số lần gọi hoặc thời điểm phát sinh lỗi.

Ví dụ dưới đây là đoạn minh họa trong một class có định nghĩa `audit(String)`:

~~~java
if (value instanceof String text
        && audit(text)
        && text.length() >= 3) {
    // ...
}
~~~

Ở đây giả sử `audit(String)` là phương thức trả `boolean`. Nó chỉ chạy khi `value` khớp `String`. Nếu đổi thành gọi `audit(String.valueOf(value))` trước `instanceof`, phương thức có thể chạy với cả dữ liệu sai kiểu; nếu chuyển xuống sau kiểm tra độ dài, thứ tự log thay đổi. Với kiểm tra thuần, việc sắp xếp lại có thể không ảnh hưởng kết quả; với I/O, cập nhật trạng thái hoặc exception, không được giả định điều đó.

**Nguyên tắc:**

- Đặt kiểm tra điều kiện tiên quyết trước phép xử lý phụ thuộc vào nó.
- Ưu tiên các predicate **không có tác dụng phụ** cho việc kiểm tra thuần.
- Không tính một lời gọi tốn kém nhiều lần khi kết quả có thể được lưu vào một biến phù hợp.
- Khi refactor `&&` hoặc `||`, giữ đúng hành vi short-circuit nếu các vế có thể ném ngoại lệ hoặc gây tác dụng phụ.
- Nếu một phép gọi vừa kiểm tra vừa thay đổi trạng thái, nên tách logic để tên và thứ tự thực thi minh bạch.

### Phân biệt `&&` và `&`, `||` và `|`

Với toán hạng kiểu `boolean`:

| Toán tử | Đánh giá vế phải | Nên dùng khi |
|---|---|---|
| `&&` | Chỉ khi vế trái `true` | Kiểm tra nối tiếp, vế sau phụ thuộc vào vế trước |
| `||` | Chỉ khi vế trái `false` | Chấp nhận một trong các điều kiện, có thể bỏ qua điều kiện sau |
| `&` | Luôn đánh giá cả hai vế | Chỉ khi thực sự cần tính cả hai; không phải mặc định cho pattern conditions |
| `\|` | Luôn đánh giá cả hai vế | Chỉ khi thực sự cần tính cả hai; không có cơ chế short-circuit như `||` |

Biến mẫu trong điều kiện dài dựa vào **luồng đã kiểm chứng việc khớp**; không thể đơn giản thay `&&` bằng `&` hay `||` bằng `|` rồi mong phạm vi và hành vi giữ nguyên.

## 9. Độ ưu tiên toán tử và cách đặt dấu ngoặc

Trong các biểu thức Boolean Java, `!` có độ ưu tiên cao hơn `&&` và `&&` cao hơn `||`. Thay vì bắt người đọc ghi nhớ thứ tự đó ở mọi chỗ, hãy làm nổi bật nhóm logic.

Ví dụ dễ nhầm:

~~~java
if (isAdmin || isOwner && isActive) {
    // ...
}
~~~

Đoạn trên tương đương `isAdmin || (isOwner && isActive)`, **không phải** `(isAdmin || isOwner) && isActive`. Nếu chính sách yêu cầu mọi người phải active, cần viết rõ:

~~~java
if ((isAdmin || isOwner) && isActive) {
    // ...
}
~~~

Các đoạn này là minh họa trong phương thức có ba biến boolean `isAdmin`, `isOwner` và `isActive`. Sai khác về dấu ngoặc có thể là **lỗi nghiệp vụ**, không chỉ là lỗi phong cách.

Với pattern variable, trình tự luôn phải có điều kiện thiết lập biến trước khi dùng nó:

~~~java
if (value instanceof String text
        && (text.startsWith("A") || text.startsWith("B"))
        && text.length() >= 3) {
    System.out.println(text);
}
~~~

Nếu OR quá dài, chuyển logic đó vào helper `hasAllowedPrefix(text)` và giữ chuỗi `&&` dễ đọc.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Tác động | Cách xử lý |
|---|---|---|
| `value instanceof String s \|\| s.isBlank()` | Vế phải chạy khi mẫu chưa khớp; code không biên dịch | Dùng `&&` nếu vế sau phụ thuộc vào mẫu, hoặc `!(pattern) \|\| ...` cho điều kiện từ chối |
| Dùng biến mẫu sau một OR có nhánh fallback | Nhánh fallback có thể đúng dù mẫu chưa khớp | Tách `if/else if`, chỉ dùng biến mẫu trong nhánh đã xác nhận |
| Kiểm tra `list.get(0)` trước `!list.isEmpty()` | Có nguy cơ `IndexOutOfBoundsException` | Kiểm tra cấu trúc và kích thước trước khi truy cập |
| Đổi `&&` sang `&` để “viết ngắn” | Mất short-circuit; có thể thay đổi lỗi/tác dụng phụ | Giữ `&&` khi các phép kiểm tra có quan hệ điều kiện tiên quyết |
| Quên dấu ngoặc khi trộn `&&` và `||` | Điều kiện nghiệp vụ bị hiểu sai | Nhóm các vế OR bằng `(...)` và viết rõ thứ tự |
| Lặp lại `strip()`, `parse()` hoặc lời gọi tốn kém | Khó đọc, có thể tính nhiều lần hoặc đổi tác dụng phụ | Lưu kết quả trung gian vào biến có tên |
| Dùng helper có tác dụng phụ mà không nêu rõ | Refactor điều kiện có thể làm đổi thứ tự hoặc số lần gọi | Ưu tiên helper thuần; bảo toàn thứ tự với thao tác có trạng thái |
| Một `if` dài có quá nhiều điều kiện | Khó xem lý do thất bại, khó kiểm thử | Dùng guard clauses, đặt tên predicate theo nghiệp vụ |
| Dùng type pattern generic không kiểm tra được từ `Object` | Không thể xác minh trực tiếp type argument tại runtime | Dùng `List<?>` rồi kiểm tra phần tử nếu cần |
| Dùng preview syntax của giai đoạn Java 14 | Phụ thuộc phiên bản và không cần thiết trong mã Java 17+ | Dùng pattern matching for `instanceof` đã chính thức từ Java 16 |

### Lưu ý về generic

Khi `value` có kiểu tĩnh `Object` và cần kiểm tra nó là một list, hãy viết:

~~~java
if (value instanceof java.util.List<?> items
        && !items.isEmpty()) {
    System.out.println(items.size());
}
~~~

Không nên dùng `value instanceof List<String> items` từ một `Object` như thể JVM có thể xác nhận type argument `String`. `List<?>` chỉ kiểm tra đây là một list; muốn bảo đảm mỗi phần tử là `String` phải kiểm tra riêng từng phần tử. Đây là giới hạn của type erasure, không phải vấn đề cú pháp dấu ngoặc.

## 11. Checklist viết và review điều kiện

Trước khi kết luận một mệnh đề Boolean có biến mẫu là dễ đọc và đúng, hãy kiểm tra:

1. **Mục đích:** điều kiện này đang xác thực kiểu, loại bỏ dữ liệu sai hay quyết định nghiệp vụ?
2. **Mẫu nào gắn biến?** Biến mẫu chỉ được dùng trên đường đi đã biết chắc mẫu khớp chưa?
3. **Kiểu và null:** có cần chặn null trước phép gọi phương thức không? `instanceof` với `null` đã trả false.
4. **Ngắn mạch:** vế phải của `&&` hoặc `||` chạy trong trường hợp nào? Có phụ thuộc vào biến mẫu được gắn ở vế trái không?
5. **Thứ tự điều kiện:** mọi phép lấy phần tử, ép kiểu hoặc truy cập trạng thái đã có tiền đề an toàn chưa?
6. **Dấu ngoặc:** các nhóm điều kiện thay thế đã được biểu diễn rõ bằng `(...)` chưa?
7. **Độ dài:** người đọc có thể giải thích từng điều kiện mà không phải đọc lại từ đầu nhiều lần không?
8. **Helper:** có quy tắc nghiệp vụ nào cần tên rõ, hoặc phép tính nào được lặp lại?
9. **Tác dụng phụ:** việc tách/gom điều kiện có thay đổi lời gọi, log, ngoại lệ hay số lần thực thi không?
10. **Kiểm thử:** có test cho sai kiểu, null, rỗng, giá trị biên, điều kiện OR và nhánh từ chối chưa?

## 12. Tự kiểm tra

**Câu 1.** Với `Object value = "Java";`, đoạn sau có hợp lệ không, và in gì?

~~~java
if (value instanceof String text && text.length() > 3) {
    System.out.println(text.toUpperCase());
}
~~~

**Đáp án:** Hợp lệ; in `JAVA`. Mẫu `String text` khớp, `text.length()` là `4` nên vế phải cũng đúng.

**Câu 2.** Tại sao `value instanceof String text || text.isEmpty()` không biên dịch?

**Đáp án:** `||` chỉ đánh giá vế phải khi mẫu `String text` không khớp. Tại đó `text` chưa được gắn, nên không thể gọi `isEmpty()`.

**Câu 3.** Vì sao `if (!(value instanceof String text)) return;` cho phép dùng `text` sau `if`?

**Đáp án:** Đường đi còn lại chỉ có thể đạt được khi `value` đã khớp `String`; đường không khớp đã kết thúc bằng `return`.

**Câu 4.** Trong điều kiện `value instanceof List<?> list && !list.isEmpty() && list.get(0) instanceof String first`, nếu list rỗng thì có gọi `get(0)` không?

**Đáp án:** Không. `!list.isEmpty()` là `false` nên `&&` short-circuit, bỏ qua việc lấy phần tử.

**Câu 5.** Điều kiện `isAdmin || isOwner && isActive` có yêu cầu admin phải active không?

**Đáp án:** Không. Nó là `isAdmin || (isOwner && isActive)`. Nếu muốn yêu cầu tất cả phải active, viết `(isAdmin || isOwner) && isActive`.

**Câu 6.** Khi refactor `if (input instanceof String s && check(s) && save(s))` thành nhiều lệnh, có thể chuyển `save(s)` chạy trước `check(s)` không?

**Đáp án:** Không nếu cần bảo toàn hành vi. `save(s)` có thể gây tác dụng phụ và ban đầu chỉ chạy sau khi `check(s)` trả true. Refactor phải giữ đúng điều kiện và thứ tự thực thi hoặc xác định rõ yêu cầu nghiệp vụ mới.

**Câu 7.** Khi một `if` có tám phép kiểm tra và nhiều nhóm OR, nên ưu tiên thêm dấu ngoặc hay chia nhỏ?

**Đáp án:** Dấu ngoặc có thể làm rõ cú pháp, nhưng nếu ý đồ vẫn khó hiểu, hãy chia thành guard clauses hoặc helper có tên rõ để thể hiện nghiệp vụ. Không đổi thứ tự các phép kiểm tra có tác dụng phụ hoặc phụ thuộc trạng thái mà không xác nhận tính tương đương.

## Tài liệu tham khảo

- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): tính năng chính thức từ Java 16 và quy tắc flow scoping.
- [Java Language Specification 17, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi biến mẫu và phân tích điều kiện.
- [Java Language Specification 17, `15.23 — Conditional-And Operator &&](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.23): short-circuit và thứ tự đánh giá.
- [Java Language Specification 17, `15.24 — Conditional-Or Operator ||](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.24): điều kiện đánh giá vế phải.
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): ví dụ pattern variables với `&&`, phủ định và flow scoping.

**Ghi nhớ:** **Kiểm tra để gắn biến mẫu trước; chỉ dùng biến khi luồng điều khiển bảo đảm đã khớp.** `&&` giúp xâu chuỗi các điều kiện phụ thuộc, `||` dùng cho lựa chọn thay thế, `!` giúp tạo guard clause, còn helper có tên tốt giúp một chuỗi kiểm tra dài trở nên có ý nghĩa và dễ bảo trì.