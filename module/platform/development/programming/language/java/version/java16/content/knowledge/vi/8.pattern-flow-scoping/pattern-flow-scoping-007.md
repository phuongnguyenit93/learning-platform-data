# Phạm vi biến trong biểu thức điều kiện ba ngôi

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Cú pháp này cho phép kiểm tra kiểu và khai báo biến pattern ngay trong biểu thức. Khi kết hợp với toán tử điều kiện ba ngôi `?:`, biến pattern chỉ khả dụng trong nhánh mà kết quả của điều kiện chứng minh pattern đã khớp.

Điểm cần nhớ là toán tử ba ngôi có hai nhánh: biểu thức sau `?` được đánh giá khi điều kiện đúng; biểu thức sau `:` được đánh giá khi điều kiện sai. Vì thế, pattern variable có thể xuất hiện trong một trong hai nhánh tùy theo cách viết điều kiện, kể cả khi điều kiện có phủ định.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích bên cạnh `record` và các API Stream. Bài này tập trung vào phạm vi pattern variable trong hai nhánh của `?:`, điều kiện kết hợp và biểu thức lồng nhau. Các ví dụ dùng cú pháp đã được chuẩn hóa, tiếp tục áp dụng trong Java hiện đại và không cần preview feature.

## 1. Cấu trúc của toán tử điều kiện ba ngôi

Toán tử điều kiện ba ngôi có dạng:

```java
condition ? expressionWhenTrue : expressionWhenFalse
```

Java đánh giá `condition` trước, sau đó chỉ đánh giá một trong hai biểu thức:

- Nếu điều kiện đúng, Java đánh giá biểu thức sau `?`.
- Nếu điều kiện sai, Java đánh giá biểu thức sau `:`.

Ví dụ đơn giản:

```java
int score = 85;
String result = score >= 50 ? "Đạt" : "Chưa đạt";
```

Khi `score >= 50` đúng, `result` nhận giá trị từ nhánh sau `?`. Nhánh sau `:` không được đánh giá. Đây là một biểu thức trả về giá trị, nên thường được dùng để gán biến, truyền đối số hoặc trả về trực tiếp từ phương thức.

## 2. Pattern variable trong nhánh đúng sau `?`

Trường hợp thường gặp là kiểm tra kiểu ở điều kiện rồi dùng biến pattern trong nhánh đúng:

```java
static String display(Object value) {
    return value instanceof String text
            ? text.strip()
            : "(không phải chuỗi)";
}
```

Trong biểu thức này:

1. Java đánh giá `value instanceof String text`.
2. Nếu kết quả đúng, pattern đã khớp và `text` được gán.
3. Java đánh giá `text.strip()` ở nhánh sau `?`.
4. Nếu kết quả sai, Java đánh giá chuỗi mặc định ở nhánh sau `:`; nhánh đó không cần và không thể dựa vào `text`.

Compiler cho phép dùng `text` trong nhánh đúng vì nhánh đó chỉ được đánh giá khi điều kiện `instanceof` đúng. Không cần ép kiểu tường minh `(String) value`.

## 3. Pattern variable trong nhánh sai sau `:` khi dùng phủ định

Biến pattern cũng có thể dùng trong nhánh sau `:` nếu điều kiện được phủ định:

```java
static String display(Object value) {
    return !(value instanceof String text)
            ? "(không phải chuỗi)"
            : text.strip();
}
```

Ở đây, nhánh sau `:` được đánh giá khi điều kiện phủ định sai. Điều đó có nghĩa biểu thức gốc `value instanceof String text` đúng, nên pattern đã khớp và `text` có thể sử dụng.

Có thể đọc theo hai trường hợp:

- Nếu `value` không phải `String` hoặc là `null`, biểu thức `instanceof` sai, phủ định thành đúng; Java chọn nhánh sau `?`.
- Nếu `value` là `String`, biểu thức `instanceof` đúng, phủ định thành sai; Java chọn nhánh sau `:` và `text` đã được gán.

Do đó, không phải nhánh sau `:` luôn không có biến pattern. Phạm vi phụ thuộc vào việc điều kiện đúng hay sai có chứng minh pattern đã khớp hay không.

## 4. Bảng ghi nhớ phạm vi trong hai nhánh

| Điều kiện | Nhánh sau `?` (điều kiện đúng) | Nhánh sau `:` (điều kiện sai) |
|---|---|---|
| `value instanceof String text` | Dùng được `text` | Không dùng được `text` |
| `!(value instanceof String text)` | Không dùng được `text` | Dùng được `text` |

Quy tắc tổng quát: biến pattern dùng được trong nhánh được chọn khi kết quả của điều kiện tại nhánh đó chứng minh pattern đã khớp. Dấu `!` đảo kết quả điều kiện, nên cũng đảo nhánh mà biến pattern có thể dùng.

## 5. Kết hợp điều kiện bằng `&&`

Điều kiện của toán tử ba ngôi có thể chứa nhiều phần. Với `&&`, vế phải chỉ được đánh giá khi vế trái đúng. Vì thế, pattern variable được dùng trong vế phải và trong nhánh đúng của toán tử ba ngôi:

```java
static String normalize(Object value) {
    return value instanceof String text && !text.isBlank()
            ? text.strip()
            : "(không có chuỗi hợp lệ)";
}
```

Nếu điều kiện tổng thể đúng, cả phép kiểm tra kiểu và điều kiện `!text.isBlank()` đều đúng. Do đó `text` chắc chắn đã khớp trong nhánh sau `?`.

Nhánh sau `:` không được dùng `text` trong ví dụ này. Điều kiện tổng thể có thể sai vì `value` không phải `String`, hoặc vì chuỗi là blank. Compiler không thể đảm bảo pattern đã khớp trên mọi trường hợp đi đến nhánh sai.

## 6. Kết hợp phủ định với nhiều điều kiện

Có thể viết điều kiện theo hướng xác định trường hợp không hợp lệ rồi dùng nhánh sau `:` cho trường hợp hợp lệ:

```java
static String commandLabel(Object value) {
    return !(value instanceof String command)
            || command.isBlank()
            || !command.startsWith("run:")
            ? "Lệnh không hợp lệ"
            : command.strip();
}
```

Nhánh sau `:` chỉ được chọn khi toàn bộ biểu thức OR sai. Khi `A || B || C` sai, cả `A`, `B` và `C` đều sai:

1. `!(value instanceof String command)` sai, nên pattern `String command` đã khớp.
2. `command.isBlank()` sai, nên chuỗi không blank.
3. `!command.startsWith("run:")` sai, nên chuỗi có tiền tố `run:`.

Vì vậy, `command` dùng được trong nhánh sau `:`. Trong nhánh sau `?`, không thể dùng `command`, bởi nhánh này cũng được chọn khi pattern chưa khớp.

## 7. Biểu thức ba ngôi lồng nhau

Biểu thức điều kiện có thể lồng nhau. Khi pattern đã khớp ở điều kiện ngoài, biến pattern tiếp tục nằm trong phạm vi của toàn bộ biểu thức nhánh đúng, bao gồm các nhánh con bên trong:

```java
static String describe(Object value) {
    return value instanceof String text
            ? text.isBlank()
                ? "Chuỗi rỗng hoặc chỉ có khoảng trắng"
                : text.strip()
            : "Giá trị không phải String";
}
```

Điều kiện ngoài xác nhận `value` là `String`, nên cả hai nhánh của biểu thức ba ngôi bên trong đều có thể dùng `text`. Nếu điều kiện ngoài sai, Java chọn nhánh cuối cùng và không có biến pattern `text`.

Biểu thức lồng nhau có thể ngắn nhưng dễ khó đọc khi có nhiều tầng. Nếu phải xử lý nhiều trường hợp, nên cân nhắc dùng `if` / `else if` để làm rõ từng nhánh:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        if (text.isBlank()) {
            return "Chuỗi rỗng hoặc chỉ có khoảng trắng";
        }
        return text.strip();
    }

    return "Giá trị không phải String";
}
```

## 8. Phạm vi không kéo dài ra ngoài biểu thức

Pattern variable chỉ khả dụng trong các vị trí được flow scoping xác định. Nó không trở thành biến cục bộ có thể dùng sau khi biểu thức ba ngôi kết thúc:

```java
static void printValue(Object value) {
    String result = value instanceof String text
            ? text.strip()
            : "(không phải chuỗi)";

    System.out.println(result);

    // Không thể dùng text ở đây: phạm vi của pattern kết thúc trong biểu thức.
}
```

Sau biểu thức, chỉ biến `result` đã được khai báo riêng còn khả dụng. Nếu cần dùng giá trị chuỗi ở nhiều câu lệnh tiếp theo, hãy gán kết quả của biểu thức vào một biến có kiểu phù hợp như `String result`, hoặc dùng cấu trúc `if` để thực hiện nhiều thao tác trong nhánh pattern.

## 9. Xử lý `null`

`instanceof` trả về `false` khi toán hạng là `null`. Do đó, với biểu thức:

```java
String label = value instanceof String text
        ? text.strip()
        : "(null hoặc không phải chuỗi)";
```

Nếu `value` là `null`, Java chọn nhánh sau `:`. Nhánh sau `?` không được đánh giá nên `text.strip()` không được gọi trên giá trị null.

Nếu cần phân biệt `null` với một kiểu không phù hợp, có thể dùng điều kiện riêng:

```java
String label = value == null
        ? "Giá trị null"
        : value instanceof String text
            ? text.strip()
            : "Không phải chuỗi";
```

Trong biểu thức lồng này, `text` chỉ được dùng trong nhánh đúng của phép kiểm tra `instanceof`. Nhánh `value == null` được xử lý trước; nếu giá trị không null nhưng sai kiểu, nhánh cuối cùng được chọn.

## 10. Những lỗi thường gặp

**Dùng biến pattern trong nhánh không chứng minh pattern đã khớp:**

```java
String result = value instanceof String text
        ? "Không sử dụng text ở đây"
        : text.strip(); // Lỗi biên dịch
```

Nhánh sau `:` chỉ chạy khi phép kiểm tra `instanceof` sai, nên `text` không được gán.

**Phủ định điều kiện nhưng dùng biến ở nhánh sai:**

```java
String result = !(value instanceof String text)
        ? text.strip() // Lỗi biên dịch
        : "Không phải chuỗi";
```

Khi điều kiện phủ định đúng, pattern gốc sai. Biến `text` chỉ dùng được ở nhánh sau `:` của biểu thức này.

**Dùng biến sau biểu thức:** biến pattern không được khai báo như một biến độc lập bên ngoài biểu thức điều kiện. Hãy dùng biến kết quả hoặc chuyển sang `if` nếu cần xử lý nhiều câu lệnh.

**Lồng quá nhiều toán tử ba ngôi:** cú pháp có thể hợp lệ nhưng khó đọc. Dùng `if` / `else` khi mỗi trường hợp cần nhiều xử lý hoặc điều kiện có nhiều tầng.

## 11. Ví dụ hoàn chỉnh

```java
public class PatternConditionalDemo {

    static String display(Object value) {
        return value instanceof String text
                ? text.isBlank()
                    ? "(blank)"
                    : text.strip()
                : "(not a string)";
    }

    static String requireCommandLabel(Object value) {
        return !(value instanceof String command)
                || command.isBlank()
                || !command.startsWith("run:")
                ? "Invalid command"
                : command.strip();
    }

    static String displayWithNegation(Object value) {
        return !(value instanceof String text)
                ? "(not a string)"
                : text.toUpperCase();
    }

    public static void main(String[] args) {
        System.out.println(display("  Java 16  "));
        System.out.println(display("   "));
        System.out.println(display(16));
        System.out.println(display(null));

        System.out.println(requireCommandLabel("run:service-a"));
        System.out.println(requireCommandLabel("stop:service-a"));
        System.out.println(displayWithNegation("pattern matching"));
    }
}
```

Có thể biên dịch bằng JDK 16 trở lên. Khi dùng JDK mới và muốn kiểm tra cú pháp theo mức ngôn ngữ Java 16:

```bash
javac --release 16 PatternConditionalDemo.java
java PatternConditionalDemo
```

## 12. Cách áp dụng trong mã Java hiện đại

- Đặt pattern `instanceof` trong điều kiện của toán tử ba ngôi khi kết quả cần biểu diễn thành một giá trị.
- Dùng biến pattern ở nhánh sau `?` khi điều kiện đúng chứng minh pattern khớp.
- Có thể dùng biến pattern ở nhánh sau `:` khi điều kiện sai chứng minh pattern khớp, ví dụ điều kiện phủ định `!(value instanceof Type variable)`.
- Với `&&` và `||`, xét kết quả của toàn bộ điều kiện, không chỉ một vế riêng lẻ.
- Không dùng biến pattern sau khi biểu thức kết thúc; gán kết quả vào biến riêng nếu cần sử dụng tiếp.
- Chuyển sang `if` / `else` khi biểu thức lồng nhau làm giảm khả năng đọc hiểu.

Trong toán tử điều kiện ba ngôi, flow scoping gắn biến pattern với nhánh được chọn bởi kết quả đúng hoặc sai của điều kiện. Hiểu rõ quan hệ này giúp viết biểu thức ngắn gọn, tránh ép kiểu thủ công và giữ an toàn kiểu trong Java 16 cũng như các phiên bản Java hiện đại.
