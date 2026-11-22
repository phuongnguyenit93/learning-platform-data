# String.isEmpty và phân biệt chuỗi rỗng với giá trị null

## 1. Hai câu hỏi khác nhau: có chuỗi không, và chuỗi có nội dung không?

Biến kiểu `String` giữ một **tham chiếu** tới đối tượng chuỗi hoặc giữ `null`. Chuỗi rỗng `""` là một giá trị chuỗi hợp lệ, chỉ có độ dài bằng không.

```java
String missing = null;
String empty = "";
String text = "Java";
```

Đoạn khai báo trên minh họa ba trạng thái, không phải một chương trình độc lập:

- `missing`: không tham chiếu tới đối tượng `String`.
- `empty`: có chuỗi nhưng không có phần tử nội dung.
- `text`: có chuỗi với nội dung `Java`.

Phân biệt này quan trọng khi xử lý dữ liệu: người dùng chưa cung cấp tên khác với chủ động xóa tên; một cấu hình không có giá trị khác với một cấu hình được đặt thành chuỗi rỗng.

`String.isEmpty()` trả lời câu hỏi **chuỗi này có độ dài bằng không không?** Nó không trả lời câu hỏi **tham chiếu này có tồn tại không?**

## 2. Hợp đồng của isEmpty

Chữ ký:

```java
public boolean isEmpty()
```

Phương thức trả `true` khi và chỉ khi `length() == 0`. Nó có từ Java 6 và vẫn phù hợp trên Java hiện đại.

```java
"".isEmpty();       // true
"Java".isEmpty();   // false
" ".isEmpty();      // false
"null".isEmpty();   // false
```

Đây là các biểu thức minh họa. `" "` có một dấu cách nên không rỗng. `"null"` có bốn chữ cái; nó không phải giá trị `null`.

Với tham chiếu bằng `null`:

```java
String value = null;
value.isEmpty();    // ném NullPointerException
```

JVM không có đối tượng để gọi phương thức instance. Nó không tự trả `true`, không tự thay `null` bằng `""` và không chạy thân `String.isEmpty()` như với đối tượng hợp lệ.

`String` bất biến; gọi `isEmpty()` không sửa chuỗi hoặc biến tham chiếu. Hợp đồng xem [String.isEmpty](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#isEmpty()).

## 3. Bảng phân biệt các trạng thái thường gặp

| Giá trị của biến | Là null? | Gọi isEmpty trực tiếp | Ý nghĩa |
| --- | --- | --- | --- |
| `null` | Có | Ném `NullPointerException` | Không có đối tượng chuỗi |
| `""` | Không | `true` | Chuỗi có độ dài 0 |
| `" "` | Không | `false` | Chuỗi có một dấu cách |
| `"\t\n"` | Không | `false` | Chuỗi có tab và xuống dòng |
| `"null"` | Không | `false` | Văn bản gồm bốn chữ cái |
| `"Java"` | Không | `false` | Văn bản thông thường |

Không nên gọi mọi hàng ngoài `"Java"` là “rỗng”. Chúng có thể cần chính sách xử lý khác nhau.

Việc một biến được khai báo kiểu `String` không bảo đảm nó khác `null`. Điều đó phụ thuộc hợp đồng phương thức, dữ liệu đầu vào và cách chương trình quản lý trạng thái.

## 4. Kiểm tra an toàn bằng đánh giá ngắn mạch

Nếu nghiệp vụ muốn coi cả `null` và `""` là thiếu dữ liệu:

```java
boolean missing = value == null || value.isEmpty();
```

Đây là đoạn mã đặt ở nơi đã có biến `String value`.

Toán tử `||` đánh giá từ trái sang phải. Nếu vế trái là `true`, nó bỏ qua vế phải:

```text
value == null?
  có    -> kết quả true, không gọi isEmpty
  không -> gọi isEmpty trên đối tượng chuỗi
```

Tương tự, để yêu cầu có tham chiếu và chuỗi không rỗng:

```java
boolean present = value != null && !value.isEmpty();
```

Với `&&`, nếu vế trái là `false`, vế phải không được đánh giá.

Hai lỗi dễ gặp:

```java
// Sai khi value == null: gọi phương thức trước khi kiểm tra.
boolean wrongOrder = value.isEmpty() || value == null;

// Sai khi value == null: | đánh giá cả hai vế boolean.
boolean wrongOperator = value == null | value.isEmpty();
```

Không thay `||` bằng `|`, hay `&&` bằng `&`, khi dựa vào việc bỏ qua lời gọi nguy hiểm. Quy tắc đánh giá ngắn mạch theo [JLS về && và ||](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.23).

Có thể đóng gói chính sách thành một phương thức nhỏ:

```java
static boolean isNullOrEmpty(String value) {
    return value == null || value.isEmpty();
}
```

Tên phương thức nói rõ hai trạng thái được gộp. Đây là phương thức để đặt trong một lớp; không phải mọi nơi trong chương trình đều nên gộp hai trạng thái.

## 5. Rỗng khác chỉ gồm khoảng trắng

Trên Java 11 trở lên, `String.isBlank()` trả `true` nếu chuỗi rỗng hoặc mọi code point đều thuộc nhóm khoảng trắng theo `Character.isWhitespace`.

```java
"".isBlank();        // true
" ".isBlank();       // true
"\t\n".isBlank();   // true
" Java ".isBlank();  // false
```

`isBlank()` không tự xử lý `null`; gọi nó trên `null` vẫn ném `NullPointerException`.

Nếu nghiệp vụ coi null, rỗng và chỉ khoảng trắng là không có nội dung:

```java
boolean missingText = value == null || value.isBlank();
```

Đây là lựa chọn trên Java hiện đại, không phải thay đổi ý nghĩa của `isEmpty()`. Không cần cắt chuỗi bằng `trim()` chỉ để kiểm tra độ dài bằng không.

Cũng không coi mọi ký tự nhìn như khoảng trắng hoặc vô hình là blank:

- `"\u2003"` — EM SPACE — được `isBlank()` coi là khoảng trắng.
- `"\u00A0"` — NO-BREAK SPACE — không thuộc tập mà `Character.isWhitespace` dùng cho phép kiểm tra này.
- `"\u200B"` — ZERO WIDTH SPACE — cũng không được `isBlank()` coi là blank.

Vì thế, một chuỗi hiển thị gần như không có gì vẫn có thể không rỗng và không blank. Nếu ứng dụng cần chuẩn hóa các ký tự đặc biệt, hãy định nghĩa chính sách riêng theo dữ liệu thực tế; không tự xóa mọi ký tự vô hình ở mọi trường.

`trim()`, `strip()`, `isEmpty()` và `isBlank()` phục vụ các hợp đồng khác nhau. Việc cắt ký tự còn có thể làm thay đổi dữ liệu; kiểm tra một điều kiện không mặc nhiên cho phép sửa nội dung. Xem [String.isBlank](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#isBlank()) và [Character.isWhitespace](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isWhitespace(int)).

## 6. Ví dụ Java 17+: quan sát từng trạng thái

Tệp `StringStateDemo.java`:

```java
public final class StringStateDemo {
    public static void main(String[] args) {
        String[] labels = {
                "null-reference", "empty", "space", "tab-newline",
                "literal-null", "em-space", "no-break-space",
                "zero-width-space", "text"
        };
        String[] values = {
                null, "", " ", "\t\n", "null",
                "\u2003", "\u00A0", "\u200B", "Java"
        };

        for (int i = 0; i < values.length; i++) {
            String value = values[i];
            System.out.println(labels[i]
                    + ": state=" + classify(value)
                    + ", nullOrEmpty=" + isNullOrEmpty(value));
        }

        try {
            String missing = null;
            missing.isEmpty();
        } catch (NullPointerException expected) {
            System.out.println("null.isEmpty -> NullPointerException");
        }
    }

    private static boolean isNullOrEmpty(String value) {
        return value == null || value.isEmpty();
    }

    private static String classify(String value) {
        if (value == null) {
            return "MISSING";
        }
        if (value.isEmpty()) {
            return "EMPTY";
        }
        if (value.isBlank()) {
            return "BLANK";
        }
        return "TEXT";
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 StringStateDemo.java
java StringStateDemo
```

Stdout:

```text
null-reference: state=MISSING, nullOrEmpty=true
empty: state=EMPTY, nullOrEmpty=true
space: state=BLANK, nullOrEmpty=false
tab-newline: state=BLANK, nullOrEmpty=false
literal-null: state=TEXT, nullOrEmpty=false
em-space: state=BLANK, nullOrEmpty=false
no-break-space: state=TEXT, nullOrEmpty=false
zero-width-space: state=TEXT, nullOrEmpty=false
text: state=TEXT, nullOrEmpty=false
null.isEmpty -> NullPointerException
```

Hàm `classify` kiểm tra theo thứ tự `null` → rỗng → blank → các chuỗi còn lại. Thứ tự có ý nghĩa: chuỗi rỗng cũng là blank, nên nếu kiểm tra `isBlank()` trước thì nhãn `EMPTY` sẽ không được dùng cho nó.

Nhãn `TEXT` trong ví dụ chỉ có nghĩa “không thuộc ba nhóm trước”, không khẳng định người dùng nhìn thấy chữ hoặc nội dung đã hợp lệ về nghiệp vụ. Hai dòng NO-BREAK SPACE và ZERO WIDTH SPACE minh họa giới hạn đó.

Khối `try/catch` cuối chỉ cố ý tạo lỗi để học hành vi. Trong mã xử lý bình thường, nên kiểm tra hoặc xác định hợp đồng null trước; không dùng bắt `NullPointerException` như cách thường xuyên kiểm tra chuỗi có rỗng không.

## 7. Chọn chính sách null theo ý nghĩa dữ liệu

### Trường bắt buộc

Nếu null là lỗi của bên gọi, có thể yêu cầu hợp đồng rõ ràng rồi mới kiểm tra nội dung:

```java
static String requireDisplayName(String value) {
    java.util.Objects.requireNonNull(value, "displayName must not be null");
    if (value.isBlank()) {
        throw new IllegalArgumentException("displayName must contain text");
    }
    return value;
}
```

Đây là phương thức minh họa để đặt trong một lớp. Nó phân biệt lỗi null với giá trị có đối tượng nhưng không đáp ứng điều kiện blank. Nó trả nguyên nội dung, không tự bỏ khoảng trắng hai đầu. Quy tắc này vẫn chưa phải bộ kiểm tra hoàn chỉnh cho mọi tên hiển thị; ví dụ các ký tự Unicode đặc biệt cần quyết định riêng nếu phạm vi sản phẩm yêu cầu.

### Trường tùy chọn

Nếu null nghĩa là chưa cung cấp còn chuỗi rỗng nghĩa là chủ động xóa, đừng gộp chúng ngay ở đầu:

```text
null -> giữ giá trị hiện có
""   -> xóa nội dung hiện có
khác -> cập nhật nội dung
```

Đây là một chính sách minh họa cho cập nhật dữ liệu. Một API cụ thể có thể phân biệt thêm trường không được gửi với trường được gửi bằng null; cần giữ đúng hợp đồng dữ liệu của API đó.

### Dùng giá trị mặc định

Chuyển null thành chuỗi rỗng có thể hợp lý ở biên hiển thị nếu sản phẩm muốn thế. Nhưng nếu làm quá sớm ở tầng dữ liệu, bạn có thể mất thông tin về sự vắng mặt.

Tương tự, `String.valueOf(value)` khi `value` là null tạo văn bản `"null"`, không phải `""`. Đây không phải phép kiểm tra hoặc chuẩn hóa “thiếu chuỗi”.

## 8. Những cách viết dễ gây hiểu nhầm

| Cách viết/suy luận | Vấn đề |
| --- | --- |
| `value == ""` để kiểm tra rỗng | `==` so tham chiếu, không diễn đạt kiểm tra nội dung chuỗi |
| `value.length() == 0` mà chưa xử lý null | Vẫn gọi phương thức instance trên null |
| `"".equals(value)` rồi coi false là đã có nội dung | Với null cũng trả false; không tách riêng trạng thái thiếu |
| `value != null || !value.isEmpty()` | Khi null vẫn đánh giá vế phải; khi không null lại trả true dù rỗng |
| Dùng `isEmpty()` để cấm toàn bộ khoảng trắng | Chuỗi có khoảng trắng vẫn có độ dài lớn hơn 0 |
| Dùng `isBlank()` để khẳng định có/không có ký tự nhìn thấy | Nó dựa vào định nghĩa khoảng trắng cụ thể, không phân tích hiển thị |

`value.length() == 0` và `value.isEmpty()` tương đương về điều kiện khi `value` là một `String` khác null. Chọn `isEmpty()` thường làm ý định đọc rõ hơn; không cần tuyên bố một cách nhanh hơn cách còn lại khi chưa có câu hỏi hiệu năng cụ thể.

## 9. Tự thực hành

1. Đổi `||` trong `isNullOrEmpty` thành `|`; chạy ca null và giải thích vì sao lỗi xuất hiện.
2. Đưa kiểm tra `isBlank()` lên trước `isEmpty()` trong `classify`; dự đoán nhãn của `""`.
3. Thêm `" Java "` vào ví dụ; phân biệt “có khoảng trắng” với “chỉ có khoảng trắng”.
4. Với một trường dữ liệu thật, ghi rõ null, rỗng và blank có cùng ý nghĩa không.
5. Nêu vì sao đổi toàn bộ null thành `""` có thể làm mất thông tin khi cập nhật một trường tùy chọn.
