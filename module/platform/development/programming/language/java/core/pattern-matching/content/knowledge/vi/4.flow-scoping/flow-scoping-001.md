# Flow scoping là gì trong Java 21?

**Flow scoping** là quy tắc xác định **phạm vi sử dụng của pattern variable dựa trên luồng điều khiển**. Khi viết một *type pattern* như `value instanceof String text`, Java chỉ cho phép dùng `text` ở những vị trí mà trình biên dịch có thể chứng minh phép so khớp đã thành công. Nhờ vậy, chương trình không thể vô tình đọc một biến pattern chưa được gán vì đối tượng không đúng kiểu.

Chủ đề này đặc biệt quan trọng khi dùng pattern matching với `instanceof`, các toán tử `&&`, `||`, `!`, câu lệnh `if`, và các nhánh `switch`. Java 21 còn hỗ trợ pattern matching trong `switch` và record pattern; flow scoping vẫn kiểm soát nơi pattern variable có hiệu lực.

## 1. Vì sao cần flow scoping?

Với cú pháp truyền thống, người lập trình kiểm tra kiểu trước rồi tự ép kiểu:

```java
static void oldWay(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
```

Type pattern gộp bước kiểm tra và khai báo:

```java
static void newWay(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Hai đoạn là các method minh họa phải đặt trong một class. Ở `newWay`, `text` chỉ tồn tại trong nhánh mà `value instanceof String text` đã trả về `true`. Nếu `value` là `Integer` hoặc `null`, phép kiểm tra thất bại và Java không cho sử dụng `text` trên nhánh đó.

Điểm khác với một biến cục bộ thông thường là phạm vi của pattern variable **không chỉ phụ thuộc vào dấu ngoặc nhọn**. Trình biên dịch xem đường đi nào trong biểu thức và câu lệnh đã khẳng định pattern khớp. Cơ chế này đôi khi được mô tả là một biến được *definitely matched* (chắc chắn đã khớp) tại điểm sử dụng.

## 2. Flow scoping với `if` và `else`

Xét đoạn mã:

```java
static void inspect(Object value) {
    if (value instanceof String text) {
        System.out.println(text.toUpperCase()); // hợp lệ
    } else {
        System.out.println("Not a String");
        // System.out.println(text); // không hợp lệ
    }

    // System.out.println(text); // không hợp lệ
}
```

Ở nhánh `if`, kết quả điều kiện là `true`, nên biến `text` được bảo đảm đã nhận một `String`. Ở nhánh `else`, pattern đã thất bại; sau toàn bộ `if/else`, hai đường đi hợp lại và không phải đường nào cũng tạo ra `text`. Vì thế, biến đó không nằm trong phạm vi tại các vị trí này.

Với phép phủ định, đường đi bảo đảm khớp sẽ **đảo chiều**:

```java
static void inspectNegated(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Not a String");
    } else {
        System.out.println(text.toUpperCase()); // hợp lệ
    }
}
```

Khi `!(value instanceof String text)` là `false`, biểu thức `instanceof` bên trong phải là `true`; do đó `text` có hiệu lực trong nhánh `else`.

## 3. Guard clause: dùng pattern variable sau `if`

Một trường hợp hữu ích là **thoát sớm** nếu pattern không khớp:

```java
static String normalized(Object value) {
    if (!(value instanceof String text)) {
        return "not text";
    }

    return text.trim().toLowerCase(); // hợp lệ
}
```

Nếu điều kiện phủ định đúng, method đã `return`; mọi đường đi còn tiếp tục tới dòng cuối đều bảo đảm `value` là `String`. Trình biên dịch cho phép dùng `text` sau `if` mà không cần đặt toàn bộ logic trong `else`.

Quy tắc tương tự áp dụng nếu nhánh không khớp luôn `throw` exception. Tuy nhiên, nếu nhánh đó vẫn có thể tiếp tục bình thường, không thể kết luận pattern đã khớp:

```java
// Ví dụ KHÔNG BIÊN DỊCH: nhánh if có thể kết thúc bình thường.
static int wrong(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("not text");
    }
    return text.length(); // text chưa chắc đã được tạo
}
```

Vì vậy, tác dụng của guard clause đến từ cả **điều kiện** và việc nhánh thất bại **không đi tiếp**.

## 4. Toán tử `&&`: phía bên phải biết phía bên trái đã khớp

Toán tử `&&` có cơ chế **short-circuit**: Java chỉ đánh giá vế phải khi vế trái là `true`. Nếu vế trái là một type pattern, biến pattern có thể được dùng ngay tại vế phải:

```java
static boolean hasLongName(Object value) {
    return value instanceof String name && name.length() >= 5;
}
```

Khi chạy `name.length()`, phép `instanceof` chắc chắn đã đúng; vì vậy không cần ép kiểu thêm. Có thể nối nhiều điều kiện:

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() <= 100) {
    System.out.println(text.strip());
}
```

Đoạn này minh họa bên trong một method có biến `value`. Biến `text` dùng được ở cả hai điều kiện phía sau và phần thân `if` khi **toàn bộ điều kiện đúng**.

Cần phân biệt: nếu cả biểu thức `&&` là `false`, ta chưa biết vế nào thất bại. Có thể `instanceof` sai hoặc phần kiểm tra độ dài sai. Vì vậy, không tự động suy luận `text` có hiệu lực tại mọi nhánh xử lý kết quả `false`.

## 5. Toán tử `||`: không bảo đảm pattern đã khớp

Toán tử `||` đánh giá vế phải khi vế trái là `false`. Nếu vế trái là `value instanceof String text`, một khi đến vế phải thì pattern đã **thất bại**, nên không được dùng `text` ở đó.

```java
// Ví dụ KHÔNG BIÊN DỊCH:
static boolean wrongOr(Object value) {
    return value instanceof String text || text.isBlank();
}
```

Đổi `||` thành `&&` chỉ hợp lý khi mong muốn cả hai điều kiện đúng. Nếu cần chấp nhận một trong hai trường hợp, hãy viết rõ logic độc lập, ví dụ:

```java
static boolean acceptable(Object value) {
    return value == null
            || (value instanceof String text && !text.isBlank());
}
```

Cách viết trên an toàn: trường hợp `null` được xử lý bởi vế đầu; ở nhánh thứ hai, `text` chỉ dùng sau khi `instanceof` thành công.

Một điểm tinh tế: khi phủ định pattern trước `||`, vế phải lại có thể sử dụng pattern variable, vì để đến đó thì phép phủ định phải sai:

```java
static boolean isMissingOrBlank(Object value) {
    return !(value instanceof String text) || text.isBlank();
}
```

Kết quả `true` khi giá trị không phải `String` **hoặc** là chuỗi trống/toàn khoảng trắng. `text.isBlank()` chỉ chạy khi `value` thực sự là `String`. Quy tắc ở đây dựa trên đường đi **true/false** của biểu thức, chứ không phải quy tắc máy móc rằng `||` luôn cấm pattern variable.

## 6. Bảng ghi nhớ các đường đi

| Biểu thức/đường đi | Có thể dùng pattern variable ở đâu? | Lý do |
| --- | --- | --- |
| `x instanceof String s` trả `true` | Nhánh nhận kết quả đúng | Pattern đã khớp |
| `x instanceof String s` trả `false` | Không thể dùng `s` do pattern này | Pattern không khớp |
| `!(x instanceof String s)` trả `false` | Nhánh nhận kết quả sai | `instanceof` bên trong đúng |
| `x instanceof String s && s.length() > 0` | Vế phải `&&`; thân `if` khi tổng điều kiện đúng | Short-circuit bảo đảm `instanceof` đúng |
| `x instanceof String s || ...` | Không dùng `s` ở vế phải chỉ nhờ điều kiện trái | Vế phải chạy khi `instanceof` sai |
| `!(x instanceof String s) || s.isBlank()` | Vế phải `||` | Vế phải chạy khi phép phủ định sai, tức pattern đúng |

Bảng mô tả quy tắc điển hình khi `s` được khai báo bởi pattern ngay trong biểu thức. Với điều kiện phức tạp, phải xem xét cả các nhánh thoát sớm, phép phủ định và đường đi cụ thể; đừng đoán phạm vi theo vị trí chữ `s` trong mã nguồn.

## 7. Flow scoping trong vòng lặp

Biểu thức điều kiện của vòng lặp cũng có thể chứa pattern. Trong ví dụ sau, phần thân `while` chỉ chạy khi pattern khớp:

```java
static void printOnce(Object value) {
    while (value instanceof String text && !text.isEmpty()) {
        System.out.println(text);
        break;
    }

    // System.out.println(text); // không hợp lệ ngoài vòng lặp
}
```

Biến `text` dùng được trong thân vòng lặp; sau vòng lặp, chương trình có thể đã không chạy vào thân lần nào nên không thể dựa vào nó. Đừng nhầm với `do ... while`: thân `do` thực thi **trước** khi điều kiện cuối vòng được kiểm tra, nên không thể dùng pattern variable từ điều kiện đó để giả định biến đã tồn tại ở thân vòng.

Khi một điều kiện có nhiều pattern hoặc nhiều nhánh, tách phần kiểm tra thành câu lệnh riêng thường giúp scope dễ đọc hơn.

## 8. Flow scoping trong `switch` pattern matching của Java 21

Pattern variable trong nhãn `case` có hiệu lực ở **guard `when`** và phần thân tương ứng khi pattern khớp; nó không tự lan sang các nhánh `case` khác.

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when !text.isBlank() -> "text: " + text.strip();
        case String ignored -> "blank text";
        case Integer number -> "number: " + number;
        default -> "other";
    };
}
```

- Ở nhánh đầu tiên có `String text`, `text` đã là `String`, nên được dùng trực tiếp trong `when` và biểu thức kết quả.
- Nếu guard `when` không đạt, `switch` tiếp tục xét nhánh phù hợp phía sau; `ignored` của nhánh `String` tiếp theo là **một pattern variable khác**.
- Ở nhánh `Integer number`, không có biến `text`. Tên và phạm vi của mỗi pattern gắn với nhánh tương ứng.
- `case null` xử lý riêng selector bằng `null`; nếu bỏ nhánh này, pattern switch trên giá trị tham chiếu thường ném `NullPointerException` khi selector là `null`, ngay cả khi có `default`.

Với **record pattern**, ví dụ `case Point(var x, var y)`, các biến `x`, `y` cũng được đưa vào scope của nhánh đó khi record pattern khớp. Flow scoping quyết định **nơi** có thể dùng biến; bản thân record pattern quyết định **dữ liệu nào** được tách ra.

## 9. Những lỗi hay gặp

**Dùng biến pattern ngoài đường đi chắc chắn khớp.** Nếu dùng `text` trong `else` sau `if (value instanceof String text)`, hoặc sau `if` có thể đi tiếp từ cả hai phía, trình biên dịch sẽ từ chối.

**Nhầm `&&` với `||`.** Đối với `value instanceof String text && text.length() > 0`, vế phải được bảo vệ bởi phép khớp. Đối với `value instanceof String text || text.length() > 0`, vế phải chạy khi phép khớp thất bại.

**Bỏ qua ảnh hưởng của `!`.** Điều kiện `!(value instanceof String text)` đúng nghĩa là mẫu *không* khớp. Sau một guard clause phủ định có `return` hoặc `throw`, những câu lệnh còn chạy tiếp mới chắc chắn có `text`.

**Nghĩ rằng flow scoping tự kiểm tra dữ liệu nghiệp vụ.** `value instanceof String text` xác nhận kiểu chuỗi, không xác nhận chuỗi khác rỗng, đúng định dạng email hay thỏa quy tắc nghiệp vụ. Những việc này vẫn cần điều kiện bổ sung hoặc validation.

**Cố dùng biến từ một nhánh `switch` ở nhánh khác.** Mỗi nhánh có phạm vi pattern riêng; tách logic dùng chung ra method sẽ rõ hơn.

**Cho rằng Java 21 cần bật preview.** Type pattern cho `instanceof` là tính năng ổn định từ Java 16; pattern matching cho `switch` và record pattern đã ổn định trong Java 21. Những ví dụ tương ứng bên dưới không cần `--enable-preview`.

## 10. Chương trình hoàn chỉnh chạy được trên JDK 21

Tạo file **`FlowScopingDemo.java`**:

```java
public class FlowScopingDemo {
    static String normalize(Object value) {
        if (!(value instanceof String text)) {
            return "not a string";
        }
        if (text.isBlank()) {
            return "blank";
        }
        return text.trim().toUpperCase();
    }

    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String text when !text.isBlank() -> "text:" + text.trim();
            case String ignored -> "blank string";
            case Integer number -> "int:" + number;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object value = "  Java  ";
        if (value instanceof String text && !text.isBlank()) {
            System.out.println("if=" + text.trim());
        }

        System.out.println("guard=" + normalize(value));
        System.out.println("mismatch=" + normalize(42));
        System.out.println("blank=" + normalize(" "));
        System.out.println("switch=" + classify("  scope  "));
        System.out.println("switchBlank=" + classify(""));
        System.out.println("switchNull=" + classify(null));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 FlowScopingDemo.java
java FlowScopingDemo
```

Stdout chính xác:

```text
if=Java
guard=JAVA
mismatch=not a string
blank=blank
switch=text:scope
switchBlank=blank string
switchNull=null
```

Giải thích luồng chạy:

1. `value instanceof String text` đúng; `&& !text.isBlank()` được đánh giá và cho phép in `text.trim()`.
2. Trong `normalize`, điều kiện phủ định không đúng nên nhánh `return "not a string"` bị bỏ qua; từ đó `text` nằm trong phạm vi của phần code còn lại.
3. `normalize(42)` không khớp `String`, nên thoát sớm. `normalize(" ")` khớp kiểu nhưng không vượt qua kiểm tra `isBlank()`.
4. Ở `classify`, biến `text` chỉ có hiệu lực trong case `String` có guard; nhánh dự phòng `String ignored` xử lý chuỗi rỗng. `case null` trả kết quả `null` một cách tường minh.

## 11. Cách suy luận nhanh về scope

Khi không chắc một pattern variable có dùng được ở dòng nào, trả lời theo thứ tự:

1. **Biến được giới thiệu ở biểu thức nào?** Ví dụ `value instanceof String text` hoặc `case String text`.
2. **Muốn tới dòng hiện tại, điều gì bắt buộc phải đúng?** Nếu tồn tại một đường đi mà pattern chưa khớp, không thể dùng biến đó.
3. **Có short-circuit, phủ định hoặc thoát sớm không?** `&&`, `||`, `!`, `return`, `throw` có thể thay đổi đường đi được chứng minh an toàn.
4. **Đang ở nhánh nào?** Pattern variable của một nhánh `switch` hoặc một thân `if` không đương nhiên được chia sẻ với nhánh khác.

Flow scoping giúp Java giữ tính an toàn kiểu ngay trong những điều kiện phân nhánh phức tạp: **pattern variable chỉ xuất hiện ở nơi compiler biết pattern đã thành công**. Hiểu đúng quy tắc này giúp tận dụng pattern matching để giảm ép kiểu, viết guard clause gọn và tránh lỗi biên dịch khi kết hợp nhiều điều kiện.
