# Phủ định pattern và viết guard clause bằng return hoặc throw

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Cú pháp `value instanceof String text` vừa kiểm tra kiểu runtime, vừa tạo biến pattern `text` có kiểu tĩnh là `String`. Compiler cho phép dùng biến ở những vị trí mà luồng điều khiển chứng minh phép kiểm tra đã khớp.

Một cách viết rất hữu ích là phủ định pattern trong điều kiện `if`, sau đó kết thúc sớm nhánh không hợp lệ bằng `return` hoặc `throw`:

```java
if (!(value instanceof String text)) {
    return;
}

System.out.println(text.strip());
```

Khi chương trình đi đến câu lệnh sau `if`, điều kiện phủ định chắc chắn sai. Vì vậy pattern gốc đã khớp và `text` được phép sử dụng. Cách tổ chức này thường được gọi là **guard clause**: kiểm tra điều kiện đầu vào ở đầu phương thức, xử lý trường hợp không đạt yêu cầu ngay, rồi giữ phần xử lý chính thẳng và dễ đọc.

Trong module Java 16, pattern matching cho `instanceof` là một cải tiến ngôn ngữ vẫn hữu ích bên cạnh `record` và các API Stream. Bài này tập trung vào phủ định pattern, phạm vi biến sau guard clause và cách chọn `return` hay `throw`. Các ví dụ dùng cú pháp Java đã chuẩn hóa, không dựa vào tính năng thử nghiệm hoặc đã lỗi thời.

## 1. Hiểu điều kiện phủ định pattern

Xét biểu thức:

```java
!(value instanceof String text)
```

Phép `instanceof` trả về `true` khi `value` là một `String` khác `null`, đồng thời pattern `text` được khớp. Dấu `!` đảo kết quả:

- Điều kiện phủ định đúng: `value` không phải `String` hoặc là `null`; pattern chưa khớp.
- Điều kiện phủ định sai: `value` là `String`; pattern đã khớp và `text` có thể sử dụng ở các vị trí được flow scoping cho phép.

Ví dụ dùng cả hai nhánh:

```java
static void describe(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Giá trị không phải chuỗi");
    } else {
        // Nhánh else chạy khi pattern gốc đã khớp.
        System.out.println("Chuỗi: " + text);
    }
}
```

Biến `text` có mặt trong nhánh `else`, vì nhánh này chỉ chạy khi điều kiện phủ định sai. Nhánh `if` không thể dùng `text`, vì chính nhánh đó biểu thị pattern chưa khớp.

## 2. Dùng `return` để kết thúc sớm trường hợp không phù hợp

Nếu giá trị không phải chuỗi thì phương thức không cần làm gì thêm, có thể dùng `return`:

```java
static void printNormalized(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    // Đến đây, text chắc chắn là String.
    System.out.println(text.strip());
}
```

Compiler phân tích hai đường đi:

1. Nếu pattern không khớp, điều kiện phủ định đúng và `return` kết thúc phương thức.
2. Nếu chương trình đi tiếp sau câu lệnh `if`, điều kiện phủ định phải sai; do đó `value instanceof String text` đã đúng.

Vì mọi đường đi mà pattern chưa khớp đều đã kết thúc, `text` nằm trong phạm vi ở phần còn lại của phương thức.

Có thể trả về một giá trị thay thế nếu đó là hợp đồng rõ ràng của phương thức:

```java
static String displayText(Object value) {
    if (!(value instanceof String text)) {
        return "(không có nội dung dạng chuỗi)";
    }

    return text.strip();
}
```

`return` có thể trả về giá trị hoặc không, tùy kiểu trả về của phương thức. Điều quan trọng với flow scoping là nhánh pattern chưa khớp không thể tiếp tục đến câu lệnh sử dụng `text`.

## 3. Dùng `throw` khi đầu vào vi phạm hợp đồng

Nếu phương thức yêu cầu bắt buộc một giá trị có kiểu `String`, trường hợp không khớp có thể được xem là lỗi đầu vào. Dùng `throw` để ném ngoại lệ:

```java
static String normalizeName(Object value) {
    if (!(value instanceof String name)) {
        throw new IllegalArgumentException("name phải là String");
    }

    String normalized = name.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException("name không được để trống");
    }

    return normalized;
}
```

Khi pattern không khớp, `throw` kết thúc luồng thực thi tại nhánh đó bằng cách ném ngoại lệ. Nếu chương trình đi đến `name.strip()`, phép kiểm tra kiểu đã thành công. Sau guard đầu tiên, `name` tiếp tục nằm trong phạm vi ở các câu lệnh sau, kể cả guard kiểm tra chuỗi rỗng.

`IllegalArgumentException` phù hợp khi đối số không đáp ứng điều kiện mà phương thức yêu cầu. Loại ngoại lệ cụ thể nên phản ánh hợp đồng API và cách ứng dụng xử lý lỗi.

## 4. Vì sao phải kết thúc nhánh bằng `return` hoặc `throw`?

Compiler chỉ cho phép dùng pattern variable sau `if` nếu mọi đường đi có thể đến vị trí đó đều chứng minh pattern đã khớp. Chỉ ghi log hoặc gọi một phương thức thông báo lỗi không tạo ra bảo đảm này:

```java
static void reject(Object value) {
    System.err.println("Giá trị không hợp lệ: " + value);
}

static void process(Object value) {
    if (!(value instanceof String text)) {
        reject(value);
        // reject có thể kết thúc bình thường, nên luồng vẫn có thể đi tiếp.
    }

    // Lỗi biên dịch: compiler không thể chứng minh text đã khớp.
    System.out.println(text.toUpperCase());
}
```

Dù người viết biết mục đích của `reject`, compiler không suy luận rằng một phương thức tùy ý luôn ném ngoại lệ hoặc luôn kết thúc chương trình. Chữ ký `void` cho phép phương thức trả về bình thường. Hãy viết hành động kết thúc luồng trực tiếp tại nhánh cần loại bỏ:

```java
static void process(Object value) {
    if (!(value instanceof String text)) {
        reject(value);
        return;
    }

    System.out.println(text.toUpperCase());
}
```

Ở ví dụ này, `reject` chỉ ghi nhận lỗi; `return` mới là câu lệnh đảm bảo phương thức không tiếp tục khi pattern chưa khớp.

## 5. Phủ định pattern với nhiều điều kiện

Guard clause có thể kiểm tra thêm các điều kiện nghiệp vụ. Khi dùng `||`, nếu vế trái là phủ định pattern thì vế phải chỉ được đánh giá khi pattern gốc đã khớp:

```java
static void printCommand(Object value) {
    if (!(value instanceof String command)
            || command.isBlank()
            || !command.startsWith("run:")) {
        return;
    }

    // command là chuỗi không blank và có tiền tố run:.
    System.out.println(command.strip());
}
```

Thứ tự đánh giá:

1. Nếu `value` không phải `String` hoặc là `null`, biểu thức phủ định đúng. Java bỏ qua các vế còn lại và thực hiện `return`.
2. Nếu `value` là `String`, vế phủ định sai. Java mới đánh giá `command.isBlank()`.
3. Nếu chuỗi blank, vế thứ hai đúng; các vế còn lại bị bỏ qua và phương thức kết thúc.
4. Nếu chuỗi không blank, Java kiểm tra tiền tố `run:`. Nếu tiền tố không đúng, phương thức cũng kết thúc.
5. Chỉ khi toàn bộ biểu thức OR sai, chương trình mới đi tiếp sau `if`. Khi đó `command` chắc chắn là một chuỗi hợp lệ theo các điều kiện đã kiểm tra.

Trong biểu thức này, `command` dùng được ở các vế phải sau pattern và sau câu lệnh `if`. Nó không được bảo đảm trong thân `if`, bởi thân đó cũng chạy khi pattern chưa khớp.

## 6. Xử lý `null` bằng guard clause

`instanceof` trả về `false` khi toán hạng là `null`. Do đó, guard clause kiểm tra pattern cũng loại được `null`:

```java
static int lengthOfText(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }

    return text.length();
}
```

Nếu `value` là `null`, phương thức trả về `0` trước khi gọi bất kỳ phương thức nào trên `text`. Nếu ứng dụng cần phân biệt `null` với một đối tượng sai kiểu, có thể kiểm tra `null` riêng và đưa ra thông báo phù hợp:

```java
static String requireText(Object value) {
    if (value == null) {
        throw new IllegalArgumentException("text không được null");
    }

    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("text phải là String");
    }

    return text.strip();
}
```

Sau guard `null`, pattern vẫn cần thiết để chứng minh kiểu của đối tượng. Khi guard thứ hai ném ngoại lệ nếu pattern không khớp, `text` có thể được dùng ở câu lệnh `return`.

## 7. Guard clause so với xử lý trong `else`

Hai cách viết dưới đây có thể thể hiện cùng một quy tắc nghiệp vụ:

**Dùng `else`:**

```java
static void printText(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Bỏ qua giá trị không phải chuỗi");
    } else {
        System.out.println(text.strip());
    }
}
```

**Dùng guard clause:**

```java
static void printText(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Bỏ qua giá trị không phải chuỗi");
        return;
    }

    System.out.println(text.strip());
}
```

Guard clause hữu ích khi phần xử lý chính dài hoặc có nhiều bước: trường hợp không hợp lệ được giải quyết ngay đầu phương thức, giảm mức lồng nhau và làm luồng thành công dễ theo dõi. Nếu nhánh sai chỉ có một hành động ngắn và phần còn lại gọn, `else` cũng là lựa chọn dễ đọc.

## 8. Chọn `return` hay `throw`?

| Tình huống | Cách kết thúc phù hợp | Ví dụ |
|---|---|---|
| Giá trị sai kiểu là trường hợp có thể bỏ qua | `return;` | Bỏ qua một sự kiện không phải chuỗi trong bộ xử lý tùy chọn. |
| Phương thức có giá trị mặc định được quy định | `return value;` | Trả về chuỗi thông báo hoặc kết quả mặc định theo hợp đồng. |
| Đối số sai kiểu vi phạm điều kiện gọi phương thức | `throw` | Ném `IllegalArgumentException` khi API yêu cầu `String`. |
| Trạng thái không thể tiếp tục theo quy tắc nghiệp vụ | `throw` loại phù hợp | Báo lỗi xác thực hoặc trạng thái không hợp lệ. |

Không nên dùng giá trị trả về giả định nếu nó khiến bên gọi không phân biệt được dữ liệu hợp lệ và dữ liệu bị từ chối. Ngược lại, cũng không nên ném ngoại lệ cho một trường hợp bình thường mà hợp đồng phương thức cho phép bỏ qua.

## 9. Các lỗi thường gặp

**Quên dấu phủ định:**

```java
if (value instanceof String text) {
    return;
}

// Không thể dùng text ở đây: luồng tiếp tục là trường hợp pattern sai.
```

Để dùng biến sau `if` theo guard clause, nhánh kết thúc sớm phải là nhánh pattern không khớp:

```java
if (!(value instanceof String text)) {
    return;
}
System.out.println(text);
```

**Chỉ gọi phương thức báo lỗi mà không kết thúc luồng:** compiler không thể biết phương thức đó luôn ném ngoại lệ. Thêm `return` hoặc `throw` trực tiếp trong nhánh.

**Dùng biến trong thân guard:** với `if (!(value instanceof String text))`, thân `if` chính là nhánh pattern không khớp nên không được dùng `text` ở đó. Biến dùng được ở nhánh `else` hoặc sau câu lệnh `if` khi nhánh không khớp đã kết thúc.

**Cho rằng `instanceof` cần kiểm tra `null` riêng:** pattern không khớp với `null`, vì vậy guard pattern đã xử lý trường hợp này. Chỉ tách kiểm tra `null` khi nghiệp vụ cần thông báo hoặc hành vi khác nhau.

## 10. Ví dụ hoàn chỉnh

```java
public class PatternGuardDemo {

    static String normalizeOrDefault(Object value) {
        if (!(value instanceof String text)) {
            return "(empty)";
        }

        if (text.isBlank()) {
            return "(empty)";
        }

        return text.strip();
    }

    static String requireIdentifier(Object value) {
        if (!(value instanceof String identifier)) {
            throw new IllegalArgumentException("identifier phải là String");
        }

        String normalized = identifier.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("identifier không được để trống");
        }

        return normalized;
    }

    public static void main(String[] args) {
        System.out.println(normalizeOrDefault("  Java 16  "));
        System.out.println(normalizeOrDefault("   "));
        System.out.println(normalizeOrDefault(42));
        System.out.println(normalizeOrDefault(null));

        System.out.println(requireIdentifier("  customer-01  "));
    }
}
```

Có thể biên dịch bằng JDK 16 trở lên. Khi dùng JDK mới và muốn kiểm tra mã theo mức ngôn ngữ Java 16:

```bash
javac --release 16 PatternGuardDemo.java
java PatternGuardDemo
```

## 11. Cách áp dụng trong mã Java hiện đại

- Đặt điều kiện phủ định `!(value instanceof Type variable)` ở đầu phương thức khi cần từ chối sớm giá trị sai kiểu.
- Kết thúc nhánh không khớp bằng `return` nếu có thể bỏ qua hoặc trả kết quả mặc định; dùng `throw` nếu đầu vào vi phạm hợp đồng.
- Sau guard clause, sử dụng trực tiếp biến pattern đã được compiler xác nhận, không ép kiểu lại.
- Với nhiều điều kiện, đặt pattern ở đầu chuỗi kiểm tra và tận dụng short-circuit để chỉ đánh giá các điều kiện phụ khi biến đã được khởi tạo.
- Giữ thông báo lỗi, kiểu ngoại lệ và giá trị mặc định nhất quán với hợp đồng của phương thức.

Phủ định pattern kết hợp với `return` hoặc `throw` giúp thể hiện rõ trường hợp không hợp lệ và tạo một luồng xử lý chính ít lồng nhau. Cơ chế flow scoping bảo đảm biến pattern chỉ được dùng sau khi mọi đường đi chưa khớp đã kết thúc. Đây là cách viết ổn định, tiếp tục áp dụng trong Java hiện đại.
