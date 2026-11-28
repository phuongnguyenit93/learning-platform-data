# Hành vi khi đối tượng nguồn là `null`

## 1. `null` không khớp với type pattern

Trong Java, một biến tham chiếu có thể không trỏ đến đối tượng nào mà mang giá trị `null`. Khi dùng pattern matching for `instanceof` được chuẩn hóa từ Java 16, giá trị `null` **không khớp với bất kỳ type pattern nào**:

~~~java
Object value = null;

if (value instanceof String text) {
    System.out.println(text.length()); // Không được thực thi
} else {
    System.out.println("Không khớp");
}
~~~

Biểu thức `value instanceof String text` cho kết quả `false`. Nhánh `else` được thực thi và biến `text` không được ràng buộc. Phép kiểm tra tự nó không ném `NullPointerException`.

Quy tắc này cũng giống phép kiểm tra `instanceof` truyền thống:

~~~java
Object value = null;

System.out.println(value instanceof String); // false
~~~

Điều quan trọng là không nhầm việc kiểm tra kiểu với việc gọi phương thức trên biến nguồn. `instanceof` xử lý được `null`, nhưng biểu thức như `value.toString()` hoặc `value.getClass()` vẫn ném `NullPointerException` nếu `value` là `null`.

## 2. Pattern variable chỉ tồn tại khi phép khớp thành công

Trong biểu thức:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Java chỉ cho phép dùng `text` ở nơi luồng điều khiển bảo đảm pattern đã khớp. Điều đó đồng thời bảo đảm:

- `value` không phải `null`.
- Đối tượng được tham chiếu khớp với kiểu `String`.
- `text` có kiểu tĩnh `String` và tham chiếu đến đối tượng đã khớp.

Vì thế, trong nhánh `if`, không cần kiểm tra `text != null` thêm lần nữa. Nếu nguồn là `null`, điều kiện đã sai và phần thân không chạy.

Ví dụ sau là không hợp lệ vì `text` không nằm trong phạm vi sử dụng sau câu lệnh `if`:

~~~java
Object value = null;

if (value instanceof String text) {
    System.out.println(text.length());
}

// Không hợp lệ: text không được khai báo trên đường đi này.
// System.out.println(text);
~~~

Không có một biến `text` mang giá trị `null` được tạo ra khi pattern thất bại. Biến pattern chỉ có ý nghĩa trên những đường đi mà phép khớp đã được xác nhận.

## 3. Phân biệt `null` với một đối tượng sai kiểu

Nếu chỉ cần kiểm tra đầu vào có phải chuỗi hay không, một pattern đã đủ:

~~~java
static void printText(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    } else {
        System.out.println("Không phải String");
    }
}
~~~

Ở ví dụ này, nhánh `else` có thể xảy ra vì hai nguyên nhân: nguồn là `null`, hoặc nguồn là một đối tượng thuộc kiểu khác. Nếu nghiệp vụ cần phân biệt hai trường hợp, hãy kiểm tra `null` riêng:

~~~java
static String describe(Object value) {
    if (value == null) {
        return "Không có giá trị";
    }

    if (value instanceof String text) {
        return "Chuỗi: " + text;
    }

    return "Kiểu khác: " + value.getClass().getSimpleName();
}
~~~

Kết quả minh họa:

~~~java
System.out.println(describe(null));       // Không có giá trị
System.out.println(describe("Java"));     // Chuỗi: Java
System.out.println(describe(16));         // Kiểu khác: Integer
~~~

Thứ tự này giúp mã thể hiện rõ ba trường hợp: không có dữ liệu, dữ liệu đúng kiểu và dữ liệu có kiểu khác. Sau nhánh kiểm tra `null`, lời gọi `value.getClass()` an toàn trên đường đi còn lại.

Có thể viết theo thứ tự pattern trước rồi mới xét `null`:

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Chuỗi: " + text;
    }
    if (value == null) {
        return "Không có giá trị";
    }
    return "Kiểu khác: " + value.getClass().getSimpleName();
}
~~~

Thứ tự nào dễ đọc hơn phụ thuộc vào mục tiêu xử lý. Cả hai đều an toàn vì phép `instanceof` không ném ngoại lệ với nguồn `null`.

## 4. Dùng pattern để từ chối cả `null` lẫn sai kiểu

Khi một phương thức chỉ chấp nhận một kiểu đầu vào, có thể dùng phủ định pattern để thoát sớm:

~~~java
static int countCharacters(Object value) {
    if (!(value instanceof CharSequence text)) {
        return 0;
    }

    return text.length();
}
~~~

Điều kiện phủ định đúng khi:

- `value` là `null`, vì `null instanceof CharSequence text` là `false`.
- `value` là một đối tượng không triển khai `CharSequence`.

Trong cả hai trường hợp, phương thức trả về trước. Nếu chương trình đi tiếp đến `text.length()`, pattern chắc chắn đã khớp. Đây là cách viết gọn khi hai trường hợp `null` và sai kiểu có cùng cách xử lý.

Nếu hai trường hợp cần thông báo khác nhau, hãy tách nhánh:

~~~java
static int countCharacters(Object value) {
    if (value == null) {
        throw new IllegalArgumentException("Giá trị không được null");
    }

    if (!(value instanceof CharSequence text)) {
        throw new IllegalArgumentException("Giá trị phải là văn bản");
    }

    return text.length();
}
~~~

Sau câu lệnh kiểm tra thứ hai, mọi đường đi tiếp tục đều có một biến `text` hợp lệ. Cách này hữu ích khi API cần nêu rõ lý do đầu vào không được chấp nhận.

## 5. Kết hợp với toán tử logic và đánh giá ngắn mạch

### 5.1. Dùng `&&`

Vế phải của `&&` chỉ được đánh giá khi vế trái đúng. Vì vậy, pattern variable có thể được sử dụng an toàn trong điều kiện tiếp theo:

~~~java
static boolean isUsefulText(Object value) {
    return value instanceof String text
            && !text.isBlank()
            && text.length() <= 100;
}
~~~

Nếu `value` là `null`, vế đầu tiên trả về `false`; các vế còn lại không được đánh giá. Không có lời gọi `isBlank()` trên một tham chiếu null.

### 5.2. Dùng `||` với phủ định

Có thể từ chối nguồn null, sai kiểu hoặc chuỗi rỗng trong một điều kiện:

~~~java
static boolean isAcceptedText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return false;
    }
    return true;
}
~~~

Khi `value` là `null`, pattern thất bại, biểu thức phủ định thành `true`, và vế phải của `||` không được đánh giá. Khi pattern khớp, vế trái thành `false`, nên Java mới đánh giá `text.isBlank()`. Ở điểm đó, `text` chắc chắn không null.

Không viết điều kiện sau:

~~~java
// Không hợp lệ: nếu phép kiểm tra bên trái thất bại,
// vế phải vẫn có thể được đánh giá khi pattern chưa khớp.
if (value instanceof String text || text.isBlank()) {
    // ...
}
~~~

Khi dùng `||`, phải xem xét đường đi mà vế trái sai. Chỉ được dùng pattern variable ở vế phải nếu chính điều kiện đó chứng minh pattern đã khớp.

## 6. So sánh type pattern với ép kiểu truyền thống khi nguồn là `null`

Ép kiểu một giá trị `null` sang kiểu tham chiếu tương thích không tự ném ngoại lệ:

~~~java
Object value = null;
String text = (String) value;

System.out.println(text == null); // true
// text.length();                // Ném NullPointerException
~~~

Điều này khác với type pattern:

~~~java
Object value = null;

if (value instanceof String text) {
    // Không chạy; pattern không tạo biến text có giá trị null.
    System.out.println(text.length());
}
~~~

Hai cách có mục đích khác nhau:

| Cách viết | Hành vi khi nguồn là `null` |
| --- | --- |
| `value instanceof String` | Trả về `false` |
| `value instanceof String text` | Trả về `false`; pattern variable không được ràng buộc |
| `String text = (String) value` | Ép kiểu thành công và gán `null` cho `text` |
| `text.length()` khi `text == null` | Ném `NullPointerException` |

Type pattern thuận tiện khi chỉ muốn xử lý giá trị sau khi đã xác nhận vừa đúng kiểu vừa khác null. Nếu cần giữ nguyên một giá trị có thể null để xử lý sau, ép kiểu tham chiếu có thể vẫn hợp lệ, nhưng phải kiểm tra null trước khi gọi thành viên.

## 7. Tránh gọi lại biểu thức nguồn có thể trả về `null`

Pattern chỉ đánh giá biểu thức nguồn tại vị trí xuất hiện của nó. Nếu nguồn là lời gọi phương thức, hãy lưu kết quả khi cần sử dụng lại:

~~~java
static Object loadValue() {
    return Math.random() > 0.5 ? "Java" : null;
}

static void printLoadedValue() {
    Object value = loadValue();

    if (value instanceof String text) {
        System.out.println(text.toUpperCase());
    } else {
        System.out.println("Không có chuỗi để xử lý");
    }
}
~~~

Biến `value` giữ đúng kết quả đã nhận được. Nếu viết `loadValue() instanceof String text` rồi gọi lại `loadValue()` ở nơi khác, lần gọi sau có thể trả về một kết quả khác, đặc biệt khi phương thức đọc dữ liệu thay đổi hoặc có tác dụng phụ. Lưu kết quả giúp điều kiện kiểm tra và dữ liệu được xử lý thuộc cùng một lần lấy giá trị.

## 8. Những điểm cần nhớ khi xử lý null

- `null instanceof T variable` luôn cho kết quả `false`; phép kiểm tra không ném `NullPointerException`.
- Pattern variable chỉ được sử dụng trên đường đi mà phép khớp thành công, vì vậy biến đó không thể là `null` trong phạm vi được bảo đảm.
- Nếu `null` và sai kiểu có cùng cách xử lý, một pattern hoặc guard clause có thể xử lý cả hai.
- Nếu cần thông báo hay hành vi riêng cho `null`, hãy kiểm tra `value == null` tường minh.
- `instanceof` an toàn với nguồn null, nhưng gọi phương thức hoặc truy cập thành viên trên chính nguồn null vẫn có thể ném `NullPointerException`.

Hiểu đúng hành vi này giúp dùng pattern matching cho `instanceof` an toàn ở ranh giới nhận dữ liệu, nơi giá trị có thể null hoặc có kiểu không như mong đợi. Các quy tắc trên thuộc cú pháp ổn định từ Java 16 và tiếp tục áp dụng trong Java hiện đại.
