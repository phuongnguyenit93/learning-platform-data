# Type pattern chính thức từ Java 16 và cú pháp `instanceof` có biến

## 1. Bối cảnh: vì sao `instanceof` cần type pattern?

Trong Java, `instanceof` vốn được dùng để kiểm tra một đối tượng có thuộc một kiểu tham chiếu cụ thể hay không. Trước Java 16, sau khi kiểm tra kiểu, lập trình viên thường phải **ép kiểu thủ công** để gọi các phương thức của kiểu đó:

```java
static int lengthOf(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.length();
    }
    return 0;
}
```

Từ **Java 16**, *pattern matching for `instanceof`* trở thành tính năng chính thức (JEP 394). Cú pháp **type pattern** gộp phép kiểm tra kiểu và việc khai báo biến đã được kiểm tra kiểu:

```java
static int lengthOf(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
}
```

Biến `text` có kiểu `String`, nên không cần ép kiểu `(String) value`. Cơ chế này tiếp tục được hỗ trợ trong Java hiện đại và không cần bật chế độ preview. Lợi ích chính là giảm mã lặp, làm rõ điều kiện kiểm tra kiểu và giúp trình biên dịch kiểm soát nơi biến được sử dụng an toàn.

## 2. Cú pháp và ý nghĩa của type pattern

```java
biểuThức instanceof KiểuThamChiếu tênBiến
```

Ví dụ:

```java
Object input = "Java 16";

if (input instanceof String message) {
    System.out.println(message.toUpperCase()); // JAVA 16
}
```

Ở biểu thức `input instanceof String message`:

1. `input` là giá trị được kiểm tra.
2. `String` là kiểu tham chiếu cần khớp; có thể dùng kiểu lớp hoặc giao diện phù hợp.
3. `message` là **pattern variable**: biến chỉ được phép sử dụng ở những vị trí mà trình biên dịch xác định phép khớp đã thành công.

Nếu `input` là một `String` khác `null`, điều kiện đúng và `message` tham chiếu đến chính đối tượng đó, dưới kiểu tĩnh `String`. Nếu không khớp, điều kiện sai và không có giá trị `message` hợp lệ để sử dụng. Pattern variable **không tạo ra đối tượng mới** và không thực hiện chuyển đổi nội dung.

Ví dụ với giao diện:

```java
static int characterCount(Object value) {
    if (value instanceof CharSequence sequence) {
        return sequence.length();
    }
    return 0;
}
```

Ở đây, `sequence` có kiểu tĩnh `CharSequence`, nên chỉ được gọi những thành viên mà kiểu đó cho phép, dù đối tượng thực tế có thể là `String` hoặc một lớp khác triển khai `CharSequence`.

## 3. Phạm vi biến dựa trên luồng điều khiển (*flow scoping*)

Pattern variable không đơn giản tồn tại trong toàn bộ khối lệnh chứa câu `if`. Java phân tích các nhánh điều kiện để xác định nơi biến **chắc chắn đã được khớp**.

### 3.1. Dùng trong nhánh khớp

```java
static void printText(Object value) {
    if (value instanceof String text) {
        System.out.println(text.strip()); // Hợp lệ
    } else {
        System.out.println("Không phải chuỗi");
        // text không khả dụng tại đây.
    }
}
```

Biến `text` dùng được trong nhánh `if` khi điều kiện đúng; không dùng được trong nhánh `else`, vì nhánh đó được thực hiện khi phép kiểm tra không khớp.

### 3.2. Kết hợp với `&&` (đánh giá ngắn mạch)

```java
static boolean hasLongName(Object value) {
    return value instanceof String name && name.length() >= 5;
}
```

Toán tử `&&` chỉ đánh giá vế phải khi vế trái đúng. Vì vậy, tại `name.length()`, trình biên dịch biết `name` đã được gán một giá trị `String` hợp lệ.

Ngược lại, đoạn sau **không biên dịch**:

```java
// SAI: nếu vế trái sai, vế phải vẫn có thể được đánh giá,
// trong khi 'name' chưa khớp.
if (value instanceof String name || name.isBlank()) {
    // ...
}
```

Đừng học thuộc máy móc rằng `||` luôn bị cấm: vấn đề là liệu luồng điều khiển có chứng minh được biến đã khớp tại điểm sử dụng hay không. Ví dụ với điều kiện phủ định bên dưới, biến vẫn có thể dùng hợp lệ.

### 3.3. Phủ định điều kiện và thoát sớm

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "";
    }

    // Đường đi còn lại bảo đảm 'value' đã khớp String.
    return text.strip();
}
```

Vì nhánh không khớp đã `return`, phần tiếp theo của phương thức chỉ chạy khi `text` tồn tại. Cách viết này thường hữu ích khi kiểm tra đầu vào.

Có thể kết hợp phủ định với `||`:

```java
static boolean isNonBlankText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return false;
    }
    return true;
}
```

Ở vế phải của `||`, vế trái phải sai mới được đánh giá; điều đó có nghĩa `value instanceof String text` đã khớp. Trình biên dịch vì vậy cho phép gọi `text.isBlank()`.

## 4. `null` và các giới hạn kiểu cần nhớ

### 4.1. `null` không khớp với type pattern

```java
Object value = null;

if (value instanceof String text) {
    System.out.println(text.length()); // Không chạy
} else {
    System.out.println("Không khớp");   // Chạy
}
```

`null instanceof String text` cho kết quả `false`, giống phép `instanceof` truyền thống. Bản thân phép kiểm tra không ném `NullPointerException`. Tuy nhiên, khi dùng `value` ở những thao tác khác (như `value.getClass()`), vẫn cần tự xử lý `null`.

### 4.2. Không kiểm tra trực tiếp kiểu generic bị xóa thông tin

Do cơ chế *type erasure*, không thể dùng một kiểu tham số hóa không reifiable như `List<String>` làm đích kiểm tra `instanceof` cho một giá trị kiểu `Object`:

```java
Object raw = java.util.List.of("Java", "16");

// SAI: không thể kiểm tra đầy đủ List<String> lúc chạy.
// if (raw instanceof java.util.List<String> items) { ... }

// ĐÚNG: kiểm tra List<?> rồi kiểm tra từng phần tử nếu cần.
if (raw instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text);
        }
    }
}
```

Pattern `List<?> items` xác nhận đối tượng là một `List`, **không bảo đảm** mọi phần tử là `String`. Luôn kiểm tra phần tử trước khi sử dụng theo kiểu cụ thể.

### 4.3. Tránh kiểm tra kiểu đã biết chắc từ kiểu tĩnh

Trình biên dịch không chấp nhận type pattern `instanceof` khi kiểu tĩnh của biểu thức đã là kiểu con của kiểu pattern, vì phép khớp không còn cung cấp kiểm tra kiểu có ý nghĩa:

```java
String greeting = "Xin chào";

// SAI ở thời điểm biên dịch:
// if (greeting instanceof String text) { ... }

// ĐÚNG: sử dụng trực tiếp biến đã có kiểu String.
System.out.println(greeting.length());
```

Trong Java 16 trở đi, pattern variable không còn mặc định là `final`; có thể gán lại trong phạm vi hợp lệ. Dù vậy, giữ nguyên ý nghĩa của biến sau phép khớp thường giúp mã dễ đọc hơn:

```java
if (value instanceof String text) {
    String trimmed = text.strip(); // Biến mới diễn đạt bước xử lý rõ ràng.
    System.out.println(trimmed);
}
```

## 5. Ví dụ hoàn chỉnh: chuẩn hóa cách mô tả dữ liệu đầu vào

Khi nhận dữ liệu ở biên của hệ thống dưới dạng `Object`, type pattern giúp xử lý từng kiểu mà không cần ép kiểu bằng tay:

```java
import java.util.List;

public class InstanceofPatternDemo {
    static String describe(Object value) {
        if (value == null) {
            return "Không có dữ liệu";
        }
        if (value instanceof String text) {
            return "Chuỗi: " + text.strip();
        }
        if (value instanceof Integer number) {
            return "Số nguyên: " + number;
        }
        if (value instanceof List<?> items) {
            return "Danh sách gồm " + items.size() + " phần tử";
        }
        return "Kiểu khác: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        System.out.println(describe("  Java 16  "));
        System.out.println(describe(42));
        System.out.println(describe(List.of("record", "instanceof")));
        System.out.println(describe(null));
    }
}
```

Kết quả:

```text
Chuỗi: Java 16
Số nguyên: 42
Danh sách gồm 2 phần tử
Không có dữ liệu
```

Ví dụ chỉ sử dụng API và cú pháp đã ổn định ở Java 16: `String.strip()` có từ Java 11, `List.of()` có từ Java 9, còn `instanceof` với type pattern là tính năng chính thức từ Java 16.

## 6. Khi nào nên dùng?

| Tình huống | Cách áp dụng |
| --- | --- |
| Xử lý giá trị `Object` từ API, adapter hoặc dữ liệu đầu vào | Kiểm tra kiểu và lấy biến ngay bằng `instanceof T name`. |
| Kiểm tra kiểu kèm điều kiện về nội dung | Dùng `&&` để điều kiện phụ chỉ chạy sau khi khớp kiểu. |
| Kiểm tra đầu vào ở đầu phương thức | Dùng phủ định và `return`/`throw` sớm, sau đó dùng pattern variable trên đường đi hợp lệ. |
| Xử lý danh sách không biết kiểu phần tử | Khớp `List<?>` rồi tiếp tục kiểm tra từng phần tử. |
| Phân nhánh liên tục theo nhiều kiểu trong một hệ phân cấp do mình thiết kế | Cân nhắc gọi phương thức đa hình trên interface/lớp cơ sở để giữ thiết kế dễ mở rộng. |

**Ghi nhớ:** `value instanceof String text` vừa kiểm tra kiểu vừa cung cấp biến `text`; biến chỉ dùng được ở nơi trình biên dịch chứng minh phép khớp đã xảy ra. Chính quy tắc *flow scoping* tạo nên khác biệt cốt lõi so với `instanceof` kèm ép kiểu thủ công.
