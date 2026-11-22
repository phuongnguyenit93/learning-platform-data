# Tái sử dụng tên biến ở các nhánh độc lập trong Java Pattern Matching

## 1. Quy tắc nền tảng: tên được tái sử dụng khi phạm vi không chồng lấn

Trong Java, **pattern variable** là biến được khai báo ngay trong một pattern, chẳng hạn `String item` trong biểu thức `value instanceof String item`. Khi pattern khớp, trình biên dịch cho phép dùng `item` ở những vị trí mà luồng điều khiển bảo đảm phép khớp đã thành công. Cơ chế này gọi là **flow scoping**.

Một điểm hữu ích là: **hai pattern nằm ở các nhánh độc lập có thể dùng cùng một tên biến**, nếu phạm vi của các khai báo đó không chồng lấn. Không có quy tắc bắt buộc rằng mọi pattern variable trong cùng phương thức phải mang tên khác nhau.

Ví dụ Java 17:

```java
if (value instanceof String item) {
    System.out.println(item.toUpperCase());
} else if (value instanceof Integer item) {
    System.out.println(item + 1);
}
```

Đây là **đoạn mã minh họa trong phương thức có biến `Object value`**, không phải chương trình độc lập. Cả hai nhánh đều dùng tên `item` nhưng vẫn hợp lệ:

- Nhánh đầu: `item` có kiểu `String`, chỉ dùng khi pattern `String item` đã khớp.
- Nhánh sau: `item` có kiểu `Integer`, chỉ dùng khi pattern `Integer item` đã khớp.
- Hai nhánh `if/else if` loại trừ nhau trong một lần thực thi; mỗi tên được khai báo trong vùng phạm vi riêng, vì thế không có xung đột.
- Nếu giá trị không khớp cả hai kiểu, không có nhánh nào dùng được `item`.

**Cùng một cách viết tên không có nghĩa là cùng một biến.** Hai khai báo nói trên tạo ra hai pattern variable khác nhau, có kiểu tĩnh khác nhau và chỉ có thể tham chiếu ở các vị trí tương ứng.

## 2. Phân biệt tên biến, phạm vi và đường đi của chương trình

Để quyết định có được tái sử dụng tên hay không, cần phân biệt ba khái niệm:

1. **Tên (identifier):** chuỗi ký tự người lập trình chọn, như `item`, `text`, `number`.
2. **Khai báo (declaration):** nơi Java tạo ra một biến có tên và kiểu cụ thể, ví dụ `String item` hay `Integer item`.
3. **Phạm vi (scope):** những vị trí trong mã nguồn mà tên đó trỏ tới khai báo ấy. Với pattern variable, phạm vi phụ thuộc đường đi mà phép khớp chắc chắn đúng.

Trong `if (value instanceof String item) { ... }`, `item` dùng được trong thân nhánh đúng. Nó **không mặc nhiên** dùng được trong `else` hoặc sau toàn bộ `if`, vì có thể đã đi qua một đường không khớp.

Vì vậy, Java không chỉ nhìn xem hai khai báo xuất hiện trong **cùng một phương thức**. Trình biên dịch xét xem phạm vi hiệu lực của chúng có giao nhau hay không. Nếu không giao nhau, việc dùng lại cùng tên có thể hoàn toàn hợp lệ.

Tính độc lập ở đây có nghĩa là **độc lập về phạm vi khai báo**. Không nhất thiết hai nhánh phải loại trừ nhau về thời gian chạy: hai câu lệnh `if` liên tiếp có thể đều chạy, nhưng vẫn dùng lại tên vì mỗi pattern variable có phạm vi riêng.

## 3. Trường hợp 1: Các nhánh `if/else if` dùng chung một tên

```java
static String format(Object value) {
    if (value instanceof String data) {
        return "Text: " + data.strip();
    } else if (value instanceof Integer data) {
        return "Count: " + (data + 1);
    } else if (value instanceof Long data) {
        return "Long: " + data;
    }
    return "Unsupported";
}
```

Đây là **phương thức minh họa đặt trong một lớp Java 17+**.

Tại mỗi nhánh, `data` có kiểu khác nhau:

| Nhánh đã khớp | Pattern variable | Kiểu tĩnh của `data` | Hành động hợp lệ |
| --- | --- | --- | --- |
| `value instanceof String data` | `data` của nhánh thứ nhất | `String` | `data.strip()` |
| `value instanceof Integer data` | `data` của nhánh thứ hai | `Integer` | `data + 1` (tự mở hộp) |
| `value instanceof Long data` | `data` của nhánh thứ ba | `Long` | Nối giá trị vào chuỗi |

Với `value = " abc "`, Java vào nhánh `String` và dùng `data.strip()`. Với `value = Integer.valueOf(7)`, Java vào nhánh `Integer` và thực hiện phép cộng. Cùng một tên `data` giúp người đọc hiểu rằng mỗi nhánh đang xử lý *giá trị đã được xác nhận kiểu* của chính nhánh đó.

**Không được suy ra rằng `data` có thể sử dụng sau toàn bộ chuỗi `if/else if`.** Trường hợp `value = null` hoặc `value` là một `Double` sẽ không khớp pattern nào; không tồn tại một biến `data` được gắn trên mọi đường đi.

## 4. Trường hợp 2: Hai câu lệnh `if` độc lập cũng có thể dùng cùng tên

Đây là trường hợp dễ gây bất ngờ hơn:

```java
static void inspect(Object first, Object second) {
    if (first instanceof String part) {
        System.out.println("String length: " + part.length());
    }

    if (second instanceof Integer part) {
        System.out.println("Integer plus one: " + (part + 1));
    }
}
```

**Đây là hai câu lệnh `if` liên tiếp**, không phải `if/else if`. Nếu `first` là `String` và `second` là `Integer`, **cả hai thân `if` đều chạy**. Việc tái sử dụng `part` vẫn hợp lệ vì:

- `part` thứ nhất có phạm vi trong đường đi match `first instanceof String part`.
- Sau câu lệnh `if` thứ nhất, `part` thứ nhất không còn thuộc phạm vi có thể dùng trong trường hợp thông thường này.
- `part` thứ hai là một khai báo mới, thuộc điều kiện `second instanceof Integer part` và nhánh đúng của câu lệnh thứ hai.

Điểm cần nhớ là **phạm vi không chồng lấn**, chứ không phải “chỉ một nhánh được thực thi”. Không có sự chia sẻ hay ghi đè biến `part` giữa hai câu lệnh `if`.

Nếu muốn sử dụng đồng thời hai giá trị ở ngoài các nhánh, hãy khai báo những biến có tên và kiểu rõ ràng trong phạm vi chung, hoặc chuyển logic vào phương thức có kiểu tham số phù hợp. Không nên trông chờ pattern variable của một nhánh tự động trở thành biến dùng chung của cả phương thức.

## 5. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`PatternVariableNameReuse.java`**:

```java
public class PatternVariableNameReuse {

    static String classify(Object value) {
        if (value instanceof String item) {
            return "String: " + item.toUpperCase();
        } else if (value instanceof Integer item) {
            return "Integer: " + (item + 1);
        } else if (value instanceof Long item) {
            return "Long: " + (item * 2);
        }
        return "Other";
    }

    static String evaluateBoth(Object left, Object right) {
        String result = "";

        if (left instanceof String item) {
            result = "S=" + item.length();
        }

        if (right instanceof Integer item) {
            result += (result.isEmpty() ? "" : " / ")
                    + "I=" + (item + 10);
        }

        return result.isEmpty() ? "None" : result;
    }

    public static void main(String[] args) {
        System.out.println(classify("java"));
        System.out.println(classify(7));
        System.out.println(classify(6L));
        System.out.println(classify(null));
        System.out.println(evaluateBoth("hi", 3));
        System.out.println(evaluateBoth(8, "no"));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac PatternVariableNameReuse.java
java PatternVariableNameReuse
```

Stdout dự kiến chính xác:

```text
String: JAVA
Integer: 8
Long: 12
Other
S=2 / I=13
None
```

Giải thích:

- `classify("java")` khớp `String item`; nhánh đầu sử dụng `String.toUpperCase()`.
- `classify(7)` truyền đối số `int` và được autoboxing thành `Integer` khi nhận ở tham số `Object`; nhánh thứ hai cộng 1.
- `classify(6L)` truyền giá trị `long` được autoboxing thành `Long`; nhánh thứ ba nhân 2.
- `classify(null)` không khớp bất kỳ type pattern `instanceof` nào, nên trả `Other`.
- `evaluateBoth("hi", 3)` cho thấy hai câu lệnh `if` đều chạy: biến `item` thứ nhất có kiểu `String` và biến `item` thứ hai có kiểu `Integer`. Giá trị xuất ra được tích lũy vào `result`, nhưng **hai pattern variable không phải một biến duy nhất**.
- `evaluateBoth(8, "no")` không khớp nhánh nào và trả `None`.

Điều có thể tái sử dụng là **tên khai báo**, không phải trạng thái hay giá trị của pattern variable trước đó.

## 6. Khi nào cùng tên gây lỗi biên dịch?

Java cho phép tái sử dụng tên ở các phạm vi **không chồng lấn**. Nếu một biến tên đó vẫn đang nằm trong scope tại nơi khai báo pattern variable mới, Java sẽ ngăn khai báo trùng.

### Lỗi A: Tên đã thuộc biến cục bộ bao quanh

```java
static void conflict(Object input) {
    String item = "original";

    // Lỗi biên dịch nếu bỏ phần chú thích:
    // if (input instanceof String item) {
    //     System.out.println(item);
    // }
}
```

Ở đây `item` cục bộ đã được khai báo trong phạm vi phương thức; phép thử pattern với tên `item` mới sẽ xung đột. Cách sửa là chọn một tên khác:

```java
static void valid(Object input) {
    String item = "original";

    if (input instanceof String matchedText) {
        System.out.println(item + ": " + matchedText);
    }
}
```

### Lỗi B: Pattern mới nằm trong phạm vi pattern cũ đã khớp

```java
static void nestedConflict(Object first, Object second) {
    if (first instanceof String item) {
        // Lỗi biên dịch nếu bỏ chú thích:
        // if (second instanceof Integer item) {
        //     System.out.println(item);
        // }
    }
}
```

Trong thân `if` ngoài, `item` kiểu `String` đã nằm trong scope. Khai báo thêm `Integer item` bên trong sẽ chồng lấn. Sửa bằng cách đặt tên khác:

```java
static void nestedValid(Object first, Object second) {
    if (first instanceof String text) {
        if (second instanceof Integer number) {
            System.out.println(text + ": " + number);
        }
    }
}
```

### Lỗi C: Hai khai báo chồng nhau qua toán tử `&&`

```java
static void andConflict(Object first, Object second) {
    // Không hợp lệ nếu bỏ chú thích:
    // if (first instanceof String part
    //         && second instanceof Integer part) {
    //     System.out.println(part);
    // }
}
```

Vế phải của `&&` chỉ được đánh giá khi vế trái đúng; lúc ấy `part` của vế trái đã nằm trong scope. Khai báo tiếp `part` ở vế phải sẽ xung đột. Dùng hai tên riêng:

```java
static void andValid(Object first, Object second) {
    if (first instanceof String text
            && second instanceof Integer count) {
        System.out.println(text.repeat(count));
    }
}
```

Đây là ví dụ hợp lệ về scope. Trong mã ứng dụng thực tế, cần kiểm soát `count` để tránh giá trị âm và lượng lặp quá lớn; `String.repeat(int)` có thể ném ngoại lệ với đối số âm.

### Lỗi D: Tưởng rằng biến đã ra khỏi scope sau mọi `if`

Flow scoping có một trường hợp quan trọng: **biến pattern có thể còn trong scope sau `if` khi đường không khớp đã kết thúc**.

```java
static void requireString(Object input, Object second) {
    if (!(input instanceof String item)) {
        return;
    }

    System.out.println(item.length()); // Hợp lệ.

    // Không được khai báo thêm pattern variable tên item:
    // if (second instanceof Integer item) {
    //     System.out.println(item);
    // }
}
```

Sau câu lệnh `if (!(input instanceof String item)) return;`, đường đi tiếp tục được trình biên dịch chứng minh là đã khớp `String item`; do đó `item` **vẫn trong scope**. Dùng lại tên `item` trong một pattern mới ở phần dưới sẽ xung đột. Đây là lý do không thể áp dụng mẹo “hễ đóng dấu `}` thì tên biến pattern đã hết phạm vi”.

Nếu cần dùng pattern thứ hai, hãy đổi tên thành `secondNumber` hoặc tổ chức lại luồng điều khiển cho rõ.

## 7. Kiểm tra điều kiện và phạm vi hợp lệ

Một số trường hợp có thể gây nhầm lẫn khi tái sử dụng tên:

| Cấu trúc | Tái sử dụng cùng tên? | Lý do |
| --- | --- | --- |
| `if (x instanceof String p) {...} else if (x instanceof Integer p) {...}` | Có | Hai nhánh có phạm vi pattern riêng, không chồng lấn |
| `if (x instanceof String p) {...}` rồi `if (y instanceof Integer p) {...}` | Có, với cấu trúc cơ bản này | Scope của `p` từ `if` thứ nhất không kéo dài sang `if` thứ hai |
| `String p = "..."; if (x instanceof String p) {...}` | Không | Tên `p` cục bộ đã tồn tại trong phạm vi bao quanh |
| `if (x instanceof String p) { if (y instanceof Integer p) {...} }` | Không | Scope của `p` thứ nhất bao trùm `if` lồng trong |
| `if (x instanceof String p && y instanceof Integer p) {...}` | Không | `p` thứ nhất đã ở trong scope của vế phải `&&` |
| `if (!(x instanceof String p)) return;` rồi khai báo `p` mới | Không trong đường tiếp tục này | `p` đầu vẫn trong scope sau guard clause |

Bảng giả định `x` và `y` có kiểu tham chiếu rộng như `Object` và không có khai báo khác trùng tên. Khả năng sử dụng `p` ở một biểu thức còn chịu quy tắc flow scoping của chính biểu thức đó; ví dụ, `p` từ `x instanceof String p` không tự có mặt trong vế phải của `||` khi vế trái sai.

## 8. Mở rộng: các nhánh `switch` pattern trong Java 21

Từ **Java 21**, pattern matching cho `switch` là tính năng chính thức. Tên biến pattern cũng có thể được dùng lại ở các **switch rule** độc lập có cú pháp mũi tên `->`.

Ví dụ sau là **phương thức minh họa dành cho Java 21+**, đặt bên trong một lớp:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Null";
        case String item -> "Text length: " + item.length();
        case Integer item -> "Integer: " + item;
        default -> "Other";
    };
}
```

Hai biến `item` trong `case String item` và `case Integer item` thuộc hai nhánh rule riêng biệt. Ở nhánh thứ nhất, `item` có kiểu `String`; ở nhánh thứ hai, `item` có kiểu `Integer`. Đây là cùng nguyên tắc **không chồng lấn phạm vi**, nhưng trong ngữ cảnh `switch`.

Không nên suy rộng ví dụ trên cho mọi dạng `switch` dùng nhãn `case:` truyền thống, nơi quy tắc phạm vi và khả năng chuyển tiếp giữa các nhóm statement có thể khác. Mẫu `switch` arrow-rule giúp mỗi nhánh xử lý tập trung và dễ đọc.

**Phân biệt phiên bản:** Java đã chuẩn hóa pattern matching cho `instanceof` từ Java 16 nên các ví dụ `if` chạy trên Java 17. Ví dụ `switch` có pattern ở đây yêu cầu Java 21 hoặc mới hơn.

## 9. Khi nào nên dùng lại tên và khi nào nên đặt tên riêng?

Tái sử dụng một tên ngắn như `item` hoặc `value` hợp lý khi:

- Các nhánh độc lập cùng diễn đạt “giá trị đã khớp kiểu của nhánh hiện tại”.
- Mỗi nhánh ngắn, chỉ dùng biến ngay tại đó, và kiểu của biến thể hiện rõ từ pattern.
- Tên chung giúp người đọc so sánh các nhánh mà không cần ghi nhớ nhiều tên mới.

Nên đặt tên riêng như `text`, `number`, `user`, `order` khi:

- Hai hoặc nhiều pattern variable cần được dùng **cùng lúc** trong một điều kiện hoặc khối lệnh.
- Nhánh lồng nhau hoặc guard clause khiến scope kéo dài và có thể xung đột.
- Các biến mang ý nghĩa nghiệp vụ khác nhau; tên rõ nghĩa giúp tránh nhầm dữ liệu, dù Java cho phép dùng chung tên.

Đừng đổi cấu trúc điều khiển chỉ để tái sử dụng một tên. **Tính rõ ràng và không chồng lấn scope** quan trọng hơn việc làm số lượng tên biến ít đi.

## 10. Bài tập tự kiểm tra

Xét hai đoạn sau, đều đặt trong phương thức có `Object first` và `Object second`.

**Đoạn A:**

```java
if (first instanceof String data) {
    System.out.println(data.length());
}
if (second instanceof Integer data) {
    System.out.println(data + 1);
}
```

**Đoạn B:**

```java
if (first instanceof String data) {
    if (second instanceof Integer data) {
        System.out.println(data);
    }
}
```

**Câu hỏi:** Đoạn nào biên dịch được trong Java 17? Tại sao?

**Đáp án:** **A hợp lệ** vì hai pattern variable `data` ở những nhánh có scope riêng, dù hai nhánh đều có thể được thực thi trong cùng một lần gọi phương thức. **B không hợp lệ** vì khi vào thân nhánh ngoài, `data` kiểu `String` vẫn trong scope; `data` kiểu `Integer` được khai báo trong nhánh lồng vào làm chồng lấn tên. Đổi biến bên trong thành `number` sẽ giải quyết xung đột.

**Ghi nhớ:** Java cho phép tái sử dụng tên pattern variable khi **phạm vi của các khai báo độc lập và không chồng lấn**. Muốn đánh giá đúng phải theo dõi đường đi của pattern matching, đặc biệt trong `if/else if`, `&&`, khối lồng nhau và guard clause có `return` hoặc `throw`.