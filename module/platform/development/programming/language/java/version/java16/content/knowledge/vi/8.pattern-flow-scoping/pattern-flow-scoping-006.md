# Dùng pattern variable sau nhánh không thể hoàn tất bình thường

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Khi kiểm tra một giá trị, ta có thể khai báo biến pattern ngay trong biểu thức:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Biến `text` chỉ được sử dụng ở những vị trí mà compiler chứng minh phép kiểm tra kiểu đã khớp. Một trường hợp quan trọng là dùng biến pattern **sau câu lệnh `if`**. Điều này có thể thực hiện khi nhánh mà pattern chưa khớp không thể hoàn tất bình thường, chẳng hạn nhánh đó kết thúc bằng `return` hoặc `throw`.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích bên cạnh `record` và các API Stream. Bài này tập trung vào cách compiler phân tích luồng điều khiển và điều kiện để biến pattern còn nằm trong phạm vi sau `if`. Các ví dụ dùng cú pháp đã được chuẩn hóa, tiếp tục áp dụng trong Java hiện đại và không cần preview feature.

## 1. Normal completion là gì?

Một câu lệnh **hoàn tất bình thường** (*normal completion*) khi việc thực thi đi đến cuối câu lệnh và tiếp tục với câu lệnh kế tiếp. Một câu lệnh **hoàn tất đột ngột** (*abrupt completion*) khi luồng thực thi rời khỏi câu lệnh theo một hướng điều khiển khác, ví dụ:

- `return` kết thúc phương thức hoặc constructor hiện tại.
- `throw` ném ngoại lệ và chuyển luồng điều khiển đến nơi xử lý ngoại lệ phù hợp.
- `break` và `continue` chuyển điều khiển ra khỏi hoặc đến vòng lặp tương ứng.

Trong các guard clause thông thường, `return` và `throw` là hai cách trực tiếp để bảo đảm nhánh không hợp lệ không thể đi tiếp đến phần xử lý chính.

Compiler dùng phân tích luồng điều khiển để xác định biến pattern đã được khớp chắc chắn tại vị trí nào. Nếu một nhánh kết thúc bằng `return` hoặc `throw`, nhánh đó không thể đưa luồng chưa khớp đến câu lệnh phía sau `if`.

## 2. Kết thúc nhánh không khớp bằng `return`

Ví dụ phổ biến nhất là phủ định pattern rồi trả về sớm:

```java
static void printUpperCase(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    // Nếu chạy đến đây, pattern chắc chắn đã khớp.
    System.out.println(text.toUpperCase());
}
```

Compiler phân tích hai khả năng:

1. `value` không phải `String` hoặc là `null`: phép `instanceof` sai, điều kiện phủ định đúng và `return` kết thúc phương thức.
2. `value` là `String`: điều kiện phủ định sai, thân `if` bị bỏ qua và luồng đi đến câu lệnh sau `if`.

Vì đường đi duy nhất có thể đến `text.toUpperCase()` là đường mà pattern đã khớp, `text` nằm trong phạm vi tại đó. Không cần ép kiểu lại `(String) value`.

Có thể trả về một kết quả mặc định nếu hợp đồng phương thức quy định như vậy:

```java
static String normalizeOrDefault(Object value) {
    if (!(value instanceof String text)) {
        return "(không có nội dung)";
    }

    return text.strip();
}
```

Trong trường hợp pattern không khớp, phương thức trả về ngay. Khi thực hiện `text.strip()`, compiler biết `text` đã được tạo.

## 3. Kết thúc nhánh không khớp bằng `throw`

Nếu phương thức yêu cầu đối số phải là `String`, giá trị sai kiểu có thể là lỗi vi phạm hợp đồng. Dùng `throw` để kết thúc nhánh đó:

```java
static String requireName(Object value) {
    if (!(value instanceof String name)) {
        throw new IllegalArgumentException("name phải là String");
    }

    return name.strip();
}
```

Khi pattern không khớp, ngoại lệ được ném ra và phương thức không đi tiếp đến `name.strip()`. Khi câu lệnh `return` được thực hiện, `name` chắc chắn là một `String`.

`return` và `throw` có ý nghĩa nghiệp vụ khác nhau:

- Dùng `return` khi trường hợp không phù hợp được phép bỏ qua hoặc có kết quả thay thế rõ ràng.
- Dùng `throw` khi lời gọi phương thức không đáp ứng hợp đồng và bên gọi cần xử lý lỗi.

Việc chọn câu lệnh kết thúc luồng phải phù hợp với thiết kế API. Về mặt flow scoping, cả hai đều ngăn nhánh chưa khớp đi đến phần mã sử dụng biến pattern.

## 4. Đảo cách viết: nhánh `else` không thể hoàn tất bình thường

Không nhất thiết phải đặt dấu `!` trong điều kiện. Có thể giữ pattern dương trong `if`, rồi kết thúc nhánh `else`:

```java
static String uppercase(Object value) {
    if (value instanceof String text) {
        System.out.println("Đã nhận chuỗi");
    } else {
        throw new IllegalArgumentException("Cần truyền String");
    }

    // Nhánh else đã ném ngoại lệ; chỉ nhánh if có thể đi tiếp.
    return text.toUpperCase();
}
```

Trong nhánh `if`, pattern đã khớp nên `text` được sử dụng bình thường. Nếu pattern không khớp, nhánh `else` ném ngoại lệ và không thể đi đến `return` cuối phương thức. Do đó, mọi đường đi có thể đến `text.toUpperCase()` đều đã xác nhận kiểu `String`.

Cách này hữu ích khi phần xử lý trường hợp hợp lệ nằm trong nhánh `if`, còn trường hợp không hợp lệ cần bị từ chối rõ ràng.

## 5. Khi nhánh không thể hoàn tất bình thường thì biến được dùng ở đâu?

Biến pattern có thể nằm trong phạm vi sau câu lệnh `if` khi mọi đường đi có thể tiếp tục sau `if` đều đã khớp pattern. Không phải cứ một nhánh bất kỳ kết thúc bằng `return` hoặc `throw` là đủ; cần xem nhánh nào kết thúc và nhánh nào còn có thể đi tiếp.

| Cấu trúc | Đường đi có thể đến sau `if` | Có thể dùng biến pattern sau `if`? |
|---|---|---|
| `if (!(v instanceof String s)) { return; }` | Chỉ khi pattern khớp | Có |
| `if (!(v instanceof String s)) { throw ex; }` | Chỉ khi pattern khớp | Có |
| `if (v instanceof String s) { ... } else { throw ex; }` | Chỉ từ nhánh pattern khớp | Có |
| `if (v instanceof String s) { ... }` | Khi pattern không khớp | Không |
| `if (!(v instanceof String s)) { log(v); }` | Có thể từ nhánh pattern không khớp | Không |

Ví dụ cuối cho thấy gọi một phương thức ghi log không kết thúc luồng. Sau khi ghi log, chương trình vẫn có thể đi đến câu lệnh tiếp theo trong khi `s` chưa được khởi tạo.

## 6. Vì sao chỉ gọi phương thức báo lỗi là chưa đủ?

Compiler không phân tích nội dung tùy ý của một phương thức để kết luận lời gọi đó luôn kết thúc luồng. Ví dụ:

```java
static void reportInvalid(Object value) {
    System.err.println("Giá trị không hợp lệ: " + value);
}

static void process(Object value) {
    if (!(value instanceof String text)) {
        reportInvalid(value);
        // reportInvalid có thể trả về bình thường.
    }

    // Lỗi biên dịch: text không được bảo đảm đã khớp.
    System.out.println(text.strip());
}
```

Tên phương thức `reportInvalid` không tạo ra bảo đảm cho compiler. Chữ ký `void` cho phép lời gọi kết thúc bình thường. Ngay cả khi phần cài đặt hiện tại luôn ném ngoại lệ, compiler không xem một lời gọi phương thức tùy ý là câu lệnh `throw` tại vị trí gọi.

Hãy đặt hành động kết thúc luồng ngay trong nhánh:

```java
static void process(Object value) {
    if (!(value instanceof String text)) {
        reportInvalid(value);
        return;
    }

    System.out.println(text.strip());
}
```

Ở đây, `reportInvalid` cung cấp thông tin chẩn đoán, còn `return` đảm bảo phương thức không tiếp tục khi pattern chưa khớp.

## 7. Điều kiện kết hợp vẫn cần xét mọi đường đi

Guard clause có thể kiểm tra thêm điều kiện nghiệp vụ sau khi xác nhận kiểu:

```java
static String requireCommand(Object value) {
    if (!(value instanceof String command)
            || command.isBlank()
            || !command.startsWith("run:")) {
        throw new IllegalArgumentException("Lệnh không hợp lệ");
    }

    return command.strip();
}
```

Vế phải đầu tiên chỉ được đánh giá khi phép phủ định sai, tức pattern `String command` đã khớp. Các vế tiếp theo cũng chỉ được đánh giá nếu các vế trước sai. Nếu bất kỳ điều kiện không hợp lệ nào đúng, `throw` kết thúc phương thức. Khi đi đến `return command.strip()`, compiler biết pattern đã khớp và các điều kiện kiểm tra đều đạt.

Điểm quan trọng là `command` dùng được trong các vế phải nhờ thứ tự đánh giá và dùng được sau `if` nhờ nhánh không hợp lệ kết thúc bằng `throw`. Không được dùng `command` trong thân `if` của guard này, vì thân đó có thể chạy ngay khi pattern chưa khớp.

## 8. Nhánh chỉ kết thúc trong một số trường hợp thì sao?

Một nhánh chỉ được xem là không thể hoàn tất bình thường nếu mọi đường đi qua nhánh đó đều kết thúc đột ngột. Nếu một điều kiện con cho phép đi tiếp, compiler vẫn phải tính đến đường đó.

Ví dụ, đoạn sau không bảo đảm pattern đã khớp sau `if`:

```java
static void process(Object value, boolean strict) {
    if (!(value instanceof String text)) {
        if (strict) {
            throw new IllegalArgumentException("Cần String");
        }
        System.out.println("Bỏ qua kiểm tra nghiêm ngặt");
    }

    // Lỗi biên dịch: khi strict là false, nhánh ngoài vẫn kết thúc bình thường.
    System.out.println(text.strip());
}
```

Khi `strict` là `true`, nhánh trong ném ngoại lệ. Nhưng khi `strict` là `false`, chương trình ghi thông báo rồi tiếp tục ra ngoài `if`, trong khi pattern chưa khớp. Vì vẫn có một đường đi như vậy, `text` không được bảo đảm.

Sửa bằng cách kết thúc mọi trường hợp không hợp lệ:

```java
static void process(Object value, boolean strict) {
    if (!(value instanceof String text)) {
        if (strict) {
            throw new IllegalArgumentException("Cần String");
        }
        return;
    }

    System.out.println(text.strip());
}
```

Bây giờ mọi đường đi vào nhánh pattern không khớp đều kết thúc bằng `throw` hoặc `return`. Vì vậy, câu lệnh cuối chỉ được thực hiện khi pattern đã khớp.

## 9. Xử lý `null`

`instanceof` trả về `false` khi giá trị bên trái là `null`. Vì thế, guard clause với pattern tự xử lý cả `null`:

```java
static int textLength(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }

    return text.length();
}
```

Nếu nghiệp vụ cần phân biệt `null` và sai kiểu, có thể thêm guard riêng:

```java
static String requireText(Object value) {
    if (value == null) {
        throw new IllegalArgumentException("Không được truyền null");
    }

    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Giá trị phải là String");
    }

    return text.strip();
}
```

Sau guard đầu tiên, compiler vẫn cần phép kiểm tra `instanceof` để xác nhận kiểu. Guard thứ hai ném ngoại lệ khi kiểu không đúng, nên `text` dùng được ở câu lệnh `return`.

## 10. Ví dụ hoàn chỉnh

```java
public class PatternAfterAbruptBranchDemo {

    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("value phải là String");
        }

        if (text.isBlank()) {
            return "(empty)";
        }

        return text.strip();
    }

    static String describe(Object value) {
        if (value instanceof String text) {
            System.out.println("Đã nhận chuỗi");
        } else {
            throw new IllegalArgumentException("Kiểu không được hỗ trợ");
        }

        return text.toUpperCase();
    }

    public static void main(String[] args) {
        System.out.println(normalize("  Java 16  "));
        System.out.println(normalize("   "));
        System.out.println(describe("pattern flow"));
    }
}
```

Có thể biên dịch bằng JDK 16 trở lên. Khi dùng JDK mới và muốn kiểm tra cú pháp theo mức ngôn ngữ Java 16:

```bash
javac --release 16 PatternAfterAbruptBranchDemo.java
java PatternAfterAbruptBranchDemo
```

## 11. Cách áp dụng trong mã Java hiện đại

- Đặt kiểm tra `instanceof` ở đầu phương thức khi muốn xác nhận kiểu trước khi xử lý dữ liệu.
- Dùng `return` nếu trường hợp không khớp có thể được bỏ qua hoặc có kết quả thay thế.
- Dùng `throw` nếu đối số sai kiểu vi phạm hợp đồng của phương thức.
- Đảm bảo mọi đường đi trong nhánh không khớp đều kết thúc; ghi log hoặc gọi helper có thể trả về là chưa đủ.
- Khi kết hợp nhiều điều kiện, phân tích thứ tự short-circuit và xác nhận biến pattern đã khớp ở từng vị trí sử dụng.

Pattern variable có thể được sử dụng sau `if` khi compiler chứng minh không có đường đi nào từ trường hợp pattern chưa khớp tiếp tục đến vị trí đó. `return` và `throw` là cách rõ ràng để kết thúc nhánh không hợp lệ, giúp luồng xử lý chính dễ đọc và giữ an toàn kiểu trong Java 16 cũng như Java hiện đại.
