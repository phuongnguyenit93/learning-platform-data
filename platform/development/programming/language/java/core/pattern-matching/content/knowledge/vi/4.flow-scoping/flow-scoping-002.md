# Phạm vi biến trong nhánh `if`: flow scoping của Java pattern matching

## 1. Biến pattern được dùng ở đâu?

Trong Java, **flow scoping** là cơ chế trình biên dịch xác định **biến được khai báo bởi pattern có thể được tham chiếu ở những vị trí nào**, dựa trên luồng điều khiển và kết quả chắc chắn của phép kiểm tra pattern.

Ví dụ với type pattern của `instanceof`:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Đoạn trên là **mã minh họa bên trong một phương thức có biến `value`**. Khi `value` là một đối tượng `String`, phép kiểm tra `instanceof String text` trả về `true` và biến pattern `text` được gắn tham chiếu đến chính đối tượng đó. Trong **nhánh `if` mà điều kiện chắc chắn đúng**, trình biên dịch cho phép gọi `text.length()` mà không cần ép kiểu thủ công.

Khi `value` không khớp `String`, bao gồm trường hợp `null`, điều kiện cho `false`; biến `text` không được gắn cho đường đi ấy. Do đó, đoạn mã không thể dùng `text` tại một vị trí mà việc khớp mẫu chưa được bảo đảm.

Quy tắc cốt lõi là:

> Biến pattern chỉ nằm trong phạm vi sử dụng ở những đường đi mà trình biên dịch có thể suy ra chắc chắn pattern đã khớp.

Đây là **phạm vi theo luồng điều khiển**; nó không hoàn toàn giống quy tắc “khai báo trong cặp ngoặc nhọn thì dùng được trong cả cặp ngoặc nhọn” của biến cục bộ thông thường.

## 2. Phạm vi trong `if`, `else` và sau `if`

Giả sử `value` có kiểu khai báo là `Object`.

### Nhánh `if` khi kiểm tra dương

```java
if (value instanceof String text) {
    // Hợp lệ: vào đây nghĩa là pattern String text đã khớp.
    System.out.println(text.toUpperCase());
} else {
    // Không hợp lệ nếu tham chiếu text tại đây:
    // System.out.println(text);
}
// Cũng không hợp lệ nếu dùng text ở đây:
// System.out.println(text.length());
```

Với cấu trúc cơ bản này:

- **Trong thân `if`:** `text` được phép sử dụng vì điều kiện kiểm tra pattern đã đúng.
- **Trong thân `else`:** `text` không được phép sử dụng vì nhánh này xảy ra khi điều kiện sai và pattern chưa chắc đã khớp.
- **Sau toàn bộ `if/else`:** không thể mặc nhiên sử dụng `text` vì luồng điều khiển có thể đi qua nhánh không khớp.

Từ “không hợp lệ” ở đây nghĩa là **lỗi biên dịch**, không phải một `NullPointerException` chỉ xuất hiện khi chạy. Trình biên dịch không cho phép tham chiếu đến biến pattern ngoài phạm vi hợp lệ.

### So với biến được khai báo trong thân khối

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
// text cũng không còn trong scope ở đây.
```

Đây là cách kiểm tra kiểu rồi ép kiểu thủ công. Biến `text` là biến cục bộ được khai báo trong thân khối `if`. Với pattern matching, biến `text` được khai báo **ngay trong biểu thức điều kiện**, nên còn có thể được dùng ở các phần khác của biểu thức Boolean nếu luồng điều khiển chứng minh nó đã khớp. Đây là khác biệt quan trọng.

**Không nên hiểu “được gắn” là chuyển đổi đối tượng:** `String text` không tạo ra chuỗi mới. Biến pattern chỉ có kiểu tĩnh `String` và tham chiếu đến đối tượng `String` phù hợp đã có.

## 3. `&&`: biến pattern dùng được ở vế phải

Toán tử `&&` trong Java đánh giá **từ trái sang phải** và có tính **ngắn mạch**: nếu vế trái sai, vế phải không được đánh giá.

```java
if (value instanceof String text && text.length() > 3) {
    System.out.println("Chuỗi dài: " + text);
}
```

Khi Java cần đánh giá `text.length() > 3`, biểu thức `value instanceof String text` bên trái chắc chắn đã trả về `true`. Do đó:

1. `text` đã được gắn một `String` khác `null`.
2. `text` **nằm trong scope của vế phải `&&`**.
3. Nếu cả hai vế đều đúng, `text` cũng dùng được trong thân nhánh `if`.

**Chú ý:** pattern có thể khớp nhưng cả điều kiện `if` vẫn sai. Với `value = "hi"`, `String text` khớp, nhưng `text.length() > 3` là `false`. Khi ấy Java không thực thi thân `if`. Nếu có `else`, nhánh `else` có thể chạy nhưng `text` không được dùng trong nhánh đó vì điều kiện tổng sai có thể đến từ nhiều nguyên nhân.

Có thể nối nhiều điều kiện khi từng bước giữ bảo đảm:

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 5) {
    System.out.println(text.substring(0, 5));
}
```

Mã này hợp lệ: chỉ khi hai điều kiện trước đã đúng mới chạy điều kiện tiếp theo. Vì đã có `text.length() >= 5`, `substring(0, 5)` trong nhánh được chọn không vượt chỉ số hợp lệ.

## 4. `||`: không được tùy tiện dùng biến pattern

Toán tử `||` cũng ngắn mạch: **vế phải được đánh giá khi vế trái sai**. Do đó, mã sau **không biên dịch**:

```java
if (value instanceof String text || text.isEmpty()) {
    System.out.println("Không hợp lệ");
}
```

Khi vế trái `value instanceof String text` sai, Java mới thử `text.isEmpty()`. Nhưng trường hợp ấy `text` không được gắn. Trình biên dịch phát hiện điều này và báo lỗi tham chiếu biến ngoài scope.

Ngay cả nếu vế phải là điều kiện độc lập hợp lệ:

```java
if (value instanceof String text || value == null) {
    // Không được mặc định dùng text ở đây:
    // System.out.println(text.length());
}
```

Cả điều kiện có thể đúng **chỉ vì `value == null`**, trong khi pattern `String text` không khớp. Vì thế trong thân `if`, việc gắn `text` chưa được bảo đảm.

So sánh để ghi nhớ:

| Biểu thức điều kiện | Có thể dùng `text` ở vế phải? | Có thể dùng `text` trong nhánh `if` nếu điều kiện đúng? |
| --- | --- | --- |
| `value instanceof String text` | Không có vế phải | Có |
| `value instanceof String text && !text.isBlank()` | Có | Có |
| `value instanceof String text || value == null` | Không có tham chiếu `text` ở vế phải; nếu thêm sẽ không được bảo đảm | Không |
| `!(value instanceof String text)` | Không có vế phải | Không, vì nhánh `if` là đường không khớp |

Bảng này xét các biểu thức cụ thể, không phải tuyên bố rằng **mọi** sự kết hợp `||` với pattern đều bất hợp lệ. Phải xét logic luồng điều khiển và vị trí biến được sử dụng.

## 5. Phủ định `!` đảo chiều nhánh có thể sử dụng biến

Nếu viết `if (!(value instanceof String text))`, nhánh `if` chỉ chạy khi **pattern không khớp**:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải chuỗi");
    // Không được dùng text tại đây.
} else {
    // Hợp lệ: rơi vào else nghĩa là pattern đã khớp.
    System.out.println("Độ dài: " + text.length());
}
```

Ở đây `text` dùng được trong `else` của phép kiểm tra phủ định, bởi `!(...)` là `false` chỉ khi pattern bên trong đã khớp.

### Guard clause với `return`

Mẫu viết thường gặp nhất là kết thúc sớm đường không khớp:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Phần `return text.length();` xuất hiện **sau** khối `if` nhưng vẫn hợp lệ. Vì đường không khớp đã `return`, chỉ đường đã khớp mới có thể tiếp tục đến dòng này.

Vì vậy, câu “biến pattern không bao giờ dùng được sau `if`” là **quá tuyệt đối**. Phạm vi phụ thuộc đường đi được chứng minh, và dạng guard clause ở trên là ví dụ quan trọng.

### Guard clause với `throw`

```java
static String requireText(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Expected a String");
    }
    return text.trim();
}
```

Dòng `return text.trim();` cũng hợp lệ vì nếu không khớp, nhánh đầu ném ngoại lệ và không thể hoàn thành bình thường. Mẫu này phù hợp khi API muốn từ chối đầu vào sai kiểu thay vì trả giá trị mặc định.

**Lưu ý:** không phải cứ có `return` ở đâu đó trong `if` là biến pattern sẽ tự động hợp lệ ở mọi chỗ. Trình biên dịch dựa trên các đường đi **có thể tiếp tục thực thi** đến vị trí tham chiếu cụ thể.

## 6. Ví dụ chạy độc lập bằng Java 17

Tạo tệp `IfPatternScopeDemo.java`:

```java
public class IfPatternScopeDemo {

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Text(" + text.length() + "): " + text;
        } else if (value instanceof Integer number) {
            return "Number: " + (number + 1);
        }
        return "Other";
    }

    static int lengthOrMinusOne(Object value) {
        if (!(value instanceof String text)) {
            return -1;
        }
        return text.length();
    }

    public static void main(String[] args) {
        Object[] values = {"java", "", 41, null};

        for (Object value : values) {
            System.out.println(
                    describe(value) + " | length=" + lengthOrMinusOne(value));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac IfPatternScopeDemo.java
java IfPatternScopeDemo
```

Stdout:

```text
Text(4): java | length=4
Other | length=0
Number: 42 | length=-1
Other | length=-1
```

Phân tích từng đầu vào:

- `"java"`: pattern `String text` khớp, điều kiện `!text.isBlank()` đúng, nên `describe` dùng `text` trong thân nhánh đầu; `lengthOrMinusOne` dùng `text` sau guard clause. Kết quả độ dài là `4`.
- `""`: vẫn là `String` nên **pattern khớp**. Nhưng `isBlank()` trả về `true`, điều kiện tổng của nhánh đầu sai; `describe` trả `Other`. Trong `lengthOrMinusOne`, kiểm tra phủ định sai nên bỏ qua `return -1`; `text.length()` trả về `0`.
- `41`: phần tử là `Integer` được autoboxing khi đưa vào `Object[]`; nhánh thứ hai của `describe` dùng được biến `number` và trả `Number: 42`. `lengthOrMinusOne` trả `-1`.
- `null`: `null instanceof String` và `null instanceof Integer` đều sai; cả hai hàm đi theo đường không khớp nên không gọi phương thức trên một biến `String` chưa được gắn.

Mã này **chạy trực tiếp trên Java 17**, không cần `--enable-preview`. Pattern matching cho `instanceof` đã được chuẩn hóa từ Java 16; bài không phụ thuộc cú pháp `switch` pattern được chuẩn hóa về sau ở Java 21.

## 7. Những lỗi biên dịch và nhầm lẫn thường gặp

### Lỗi 1: Sử dụng biến trong nhánh `else` của kiểm tra dương

```java
if (value instanceof String text) {
    System.out.println(text);
} else {
    // Sai nếu bỏ chú thích:
    // System.out.println(text.length());
}
```

Nhánh `else` chính là nơi điều kiện `instanceof` sai, nên việc có biến `text` kiểu `String` không được bảo đảm.

### Lỗi 2: Sử dụng biến bên phải `||`

```java
// Không biên dịch nếu bỏ chú thích:
// if (value instanceof String text || text.isEmpty()) {
//     System.out.println(text);
// }
```

Đường chạy đến `text.isEmpty()` xảy ra khi phép kiểm tra bên trái không khớp. Đây là lỗi **phạm vi theo luồng điều khiển**.

### Lỗi 3: Coi biến pattern là biến của toàn bộ phương thức

```java
static void print(Object value) {
    if (value instanceof String text) {
        System.out.println(text);
    }

    // Không hợp lệ nếu bỏ chú thích:
    // System.out.println(text.length());
}
```

Không nên mang `text` ra ngoài như thể nó được khai báo và khởi tạo cho mọi đường đi. Nếu cần xử lý cả hai trường hợp, dùng `if/else` rõ ràng, guard clause hoặc thiết kế lại kiểu tham số.

### Lỗi 4: Khai báo trùng tên trong phạm vi đang tồn tại

```java
static void nameCollision(Object value) {
    String text = "existing";

    // Không hợp lệ: tên text đã tồn tại trong phạm vi:
    // if (value instanceof String text) {
    //     System.out.println(text);
    // }

    if (value instanceof String matchedText) {
        System.out.println(matchedText);
    }
}
```

Đặt tên biến pattern không được xung đột với biến cục bộ hiện có trong phạm vi mà Java cấm khai báo trùng. Chọn tên mô tả vai trò như `matchedText` có thể giúp tránh lỗi và làm mã rõ hơn.

### Lỗi 5: Nhầm “pattern khớp” với “điều kiện tổng đúng”

```java
Object value = "hi";
if (value instanceof String text && text.length() >= 5) {
    System.out.println("Long");
} else {
    System.out.println("Short or not a string");
}
```

Stdout của đoạn mã trên (khi đặt trong một phương thức chạy được) là:

```text
Short or not a string
```

Pattern `String text` **đã khớp** với `"hi"`, nhưng điều kiện chiều dài sai. Nhánh `else` không được dùng `text` vì về mặt logic điều kiện tổng có thể sai cả khi đối tượng không phải chuỗi.

### Lỗi 6: Nhầm phạm vi biên dịch với thời gian tồn tại dữ liệu

Flow scoping quyết định **tại đâu tên biến pattern có thể được trình biên dịch chấp nhận**. Nó không mang nghĩa Java tạo, hủy hay sao chép đối tượng `String` mỗi lần đi vào hoặc ra khỏi nhánh. Đối tượng vẫn tuân theo các quy tắc tham chiếu và bộ gom rác bình thường của JVM; scope của tên biến là một vấn đề khác.

## 8. So sánh nhanh các dạng `if`

| Dạng mã | Đường đi chắc chắn đã khớp | Vị trí dùng biến pattern |
| --- | --- | --- |
| `if (v instanceof String s) { ... }` | Nhánh `if` | Trong thân `if` |
| `if (v instanceof String s && s.length() > 0) { ... }` | Vế phải `&&` khi được đánh giá; thân `if` khi toàn bộ điều kiện đúng | Ở vế phải `&&` và thân `if` |
| `if (v instanceof String s) { ... } else { ... }` | Nhánh `if` | Không dùng `s` trong `else` thông thường |
| `if (!(v instanceof String s)) { ... } else { ... }` | Nhánh `else` | Dùng được `s` trong nhánh `else` |
| `if (!(v instanceof String s)) return;` rồi dùng `s` | Đường tiếp tục sau `if` | Dùng được `s` sau guard clause |
| `if (v instanceof String s || v == null) { ... }` | Không có bảo đảm khi toàn bộ điều kiện đúng | Không mặc định dùng `s` trong thân `if` |

Tất cả ví dụ ở bảng giả định `v` là biến thuộc kiểu tham chiếu rộng phù hợp, chẳng hạn `Object`, và không có khai báo cùng tên gây xung đột.

## 9. Cách áp dụng và tự kiểm tra

Khi cần kiểm tra kiểu để xử lý ngắn gọn ngay trong một nhánh, dùng trực tiếp:

```java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.charAt(0));
}
```

Khi muốn loại sớm đầu vào không đúng kiểu và tiếp tục xử lý ở phía dưới, ưu tiên guard clause:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length());
```

Đoạn thứ hai là **minh họa đặt trong một phương thức trả về `void`**. Quy tắc flow scoping giúp biến `text` hợp lệ sau câu lệnh `if` vì đường sai kiểu đã kết thúc.

**Tự kiểm tra:** với `Object v = "abc";`, ở biểu thức `v instanceof String s && s.length() == 3`, vế phải `&&` có được phép dùng `s` không? **Có**, vì chỉ được đánh giá sau khi pattern đã khớp. Nếu thay `&&` bằng `||` rồi tham chiếu `s` ở vế phải, có hợp lệ không? **Không**, vì vế phải chạy khi pattern có thể chưa khớp.

**Ghi nhớ:** phạm vi của biến pattern được quyết định bởi **đường đi chắc chắn khớp pattern**, chứ không đơn thuần bởi số lượng dấu ngoặc nhọn quanh một nhánh `if`. Hiểu nguyên tắc này giúp đọc mã Java 17+ chính xác, loại bỏ phép cast thủ công lặp lại và tránh các lỗi biên dịch khi viết điều kiện kết hợp.