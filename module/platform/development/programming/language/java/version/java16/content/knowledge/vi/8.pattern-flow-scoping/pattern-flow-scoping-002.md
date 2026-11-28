# Phạm vi pattern variable trong nhánh if và else

Từ Java 16, pattern matching cho `instanceof` cho phép khai báo biến ngay trong phép kiểm tra kiểu. Biến đó được gọi là **pattern variable**. Compiler chỉ cho phép sử dụng biến tại những nhánh mà luồng điều khiển chứng minh pattern đã khớp.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn được dùng trong Java hiện đại, bên cạnh `record` và các API Stream. Bài này tập trung vào cách pattern variable xuất hiện trong nhánh `if`, nhánh `else` và phần mã sau câu lệnh điều kiện. Các ví dụ sử dụng cú pháp đã được chuẩn hóa, không cần preview feature.

## 1. Pattern variable trong nhánh `if`

Với điều kiện kiểm tra trực tiếp, pattern variable nằm trong phạm vi của nhánh `if`, vì nhánh này chỉ được thực hiện khi pattern khớp:

```java
static void printValue(Object value) {
    if (value instanceof String text) {
        // Điều kiện đúng nên text đã được gán và có kiểu String.
        System.out.println(text.toUpperCase());
    }
}
```

Compiler biết `text` là một `String` trong thân `if`, nên có thể gọi các phương thức của `String` mà không cần ép kiểu. Pattern `instanceof` cũng chỉ khớp khi giá trị không phải `null`; vì vậy nếu `value` là `null`, thân `if` không chạy.

Phạm vi này áp dụng cho toàn bộ statement làm thân `if`, kể cả khi thân là một câu lệnh đơn không có dấu ngoặc nhọn:

```java
if (value instanceof String text)
    System.out.println(text.length());
```

Trong mã ứng dụng, dùng dấu ngoặc nhọn thường giúp thể hiện rõ ranh giới của nhánh và thuận tiện khi bổ sung thêm câu lệnh.

## 2. Vì sao biến không nằm trong nhánh `else`?

Nhánh `else` chạy khi điều kiện `if` sai. Với điều kiện `value instanceof String text`, kết quả sai có nghĩa là pattern không khớp, nên `text` không được gán và không thể sử dụng trong nhánh `else`:

```java
static void describe(Object value) {
    if (value instanceof String text) {
        System.out.println("Chuỗi có " + text.length() + " ký tự");
    } else {
        System.out.println("Giá trị không phải String");
        // text không nằm trong phạm vi ở đây.
    }
}
```

Nhánh `else` có thể được thực hiện khi `value` là một số, một đối tượng thuộc kiểu khác hoặc `null`. Vì thế, compiler không thể xem giá trị ban đầu là `String` trong nhánh này.

Nếu cần xử lý giá trị ở cả hai nhánh, hãy khai báo biến pattern phù hợp trong từng điều kiện hoặc xử lý riêng trường hợp không khớp. Không dùng biến của nhánh đúng trong nhánh sai.

## 3. Đảo điều kiện để dùng biến trong nhánh `else`

Khi phủ định phép kiểm tra, ý nghĩa của hai nhánh được đảo lại. Với `!(value instanceof String text)`, nhánh `if` chạy khi pattern không khớp; nhánh `else` chạy khi pattern khớp. Do đó, `text` được phép sử dụng trong nhánh `else`:

```java
static void describe(Object value) {
    if (!(value instanceof String text)) {
        System.out.println("Giá trị không phải String");
    } else {
        // Điều kiện phủ định sai, vì vậy pattern instanceof đã đúng.
        System.out.println("Chuỗi viết hoa: " + text.toUpperCase());
    }
}
```

Có thể đọc điều kiện theo từng bước:

1. `value instanceof String text` đúng khi `value` là một `String` khác `null`.
2. Dấu `!` đảo kết quả đó.
3. Thân `if` chạy khi phép kiểm tra kiểu không khớp.
4. Nhánh `else` chạy khi phép kiểm tra kiểu khớp, nên `text` đã được gán.

Đây là một cách viết hữu ích khi muốn xử lý trường hợp sai trước, rồi đặt phần xử lý chính trong nhánh `else`. Với guard clause, có thể viết gọn hơn và cho phép tiếp tục dùng biến sau câu lệnh `if`.

## 4. Pattern variable sau câu lệnh `if`

Phạm vi của pattern variable có thể kéo dài đến các câu lệnh sau `if` nếu compiler chứng minh mọi luồng thực thi có thể đi tiếp đều đã khớp pattern. Điều này thường xảy ra khi nhánh không khớp kết thúc bằng `return` hoặc `throw`.

```java
static void printUpperCase(Object value) {
    if (!(value instanceof String text)) {
        return;
    }

    // Chỉ có thể đến đây khi pattern đã khớp.
    System.out.println(text.toUpperCase());
}
```

Nếu điều kiện phủ định đúng, phương thức kết thúc tại `return`. Nếu chương trình tiếp tục đến câu lệnh cuối, điều kiện phủ định phải sai, nghĩa là `value instanceof String text` đã đúng. Vì vậy compiler cho phép dùng `text` sau câu lệnh `if`.

Một cách viết tương đương là đặt xử lý trường hợp không hợp lệ trong nhánh `else` và kết thúc nhánh đó:

```java
static int stringLength(Object value) {
    if (value instanceof String text) {
        System.out.println("Đã nhận chuỗi");
    } else {
        throw new IllegalArgumentException("Cần truyền String");
    }

    // Nhánh else không thể đi tiếp; luồng còn lại chứng minh pattern đã khớp.
    return text.length();
}
```

Hai cách viết đều thể hiện cùng một nguyên tắc: mọi đường đi có thể đến câu lệnh sử dụng `text` đều phải đi qua kết quả pattern đúng.

## 5. Khi cả hai nhánh đều có thể tiếp tục

Nếu cả nhánh `if` và `else` đều có thể kết thúc bình thường, pattern variable không nằm trong phạm vi sau câu lệnh `if`, bởi chương trình có thể đi tiếp từ nhánh mà pattern không khớp.

```java
static void inspect(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println("Kiểu khác");
    }

    // Không thể dùng text tại đây.
}
```

Nhánh `if` chứng minh `text` hợp lệ, nhưng nhánh `else` vẫn có thể đi đến phần sau trong khi pattern đã thất bại. Compiler phải xét mọi luồng thực thi, không chỉ nhánh mà người viết dự định thường xảy ra.

Ngay cả khi không viết `else`, việc kết thúc nhánh `if` cũng không làm biến pattern khả dụng sau câu lệnh. Ví dụ dưới đây không biên dịch:

```java
static void inspect(Object value) {
    if (value instanceof String text) {
        return;
    }

    // Luồng đi tiếp ở đây là trường hợp pattern không khớp.
    System.out.println(text); // Lỗi biên dịch: text không nằm trong phạm vi.
}
```

Khi thân `if` chạy, phương thức kết thúc. Luồng duy nhất có thể đi đến câu lệnh cuối là điều kiện sai, tức pattern chưa khớp. Đây là điểm khác với guard clause dùng điều kiện phủ định ở phần trước.

So sánh với ví dụ sau:

```java
static void inspect(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    } else {
        System.out.println("Kiểu khác");
        return;
    }

    // Chỉ nhánh if có thể đi tới đây, nên text dùng được.
    System.out.println(text.toUpperCase());
}
```

Khác biệt nằm ở `return` trong nhánh `else`. Nhánh đó không thể đi tới câu lệnh cuối, nên mọi luồng có thể đến vị trí dùng `text` đều bắt nguồn từ nhánh `if` đã khớp pattern.

## 6. Kết hợp điều kiện với phạm vi trong nhánh

Khi điều kiện `if` có nhiều phần, phạm vi được xác định từ kết quả của toàn bộ biểu thức. Với `&&`, vế phải chỉ chạy khi vế trái đúng; vì vậy biến pattern có thể được dùng trong vế phải và trong thân `if` nếu toàn bộ điều kiện đúng:

```java
static void printNonEmpty(Object value) {
    if (value instanceof String text && !text.isEmpty()) {
        System.out.println(text.strip());
    } else {
        System.out.println("Không phải chuỗi không rỗng");
        // text không được đảm bảo đã khớp trong nhánh else.
    }
}
```

Trong ví dụ này, nhánh `else` có thể được chạy vì `value` không phải `String`, hoặc vì nó là chuỗi rỗng. Do đó, không thể dùng `text` trong nhánh `else`.

Tương tự, nếu điều kiện là `value instanceof String text || fallback`, nhánh `if` có thể chạy chỉ vì `fallback` đúng. Compiler không thể kết luận pattern đã khớp trong mọi trường hợp, nên không cho dùng `text` trong thân `if` dựa trên điều kiện đó.

Khi cần dùng biến sau một điều kiện kết hợp, hãy đảm bảo nhánh chứa mọi trường hợp pattern chưa khớp kết thúc luồng:

```java
static void printNonEmpty(Object value) {
    if (!(value instanceof String text) || text.isEmpty()) {
        return;
    }

    // Điều kiện sai chỉ khi text là String và không rỗng.
    System.out.println(text.strip());
}
```

Ở đây, `text` có thể được dùng trong vế phải của `||` vì vế phải chỉ được đánh giá khi phủ định ở vế trái sai. Sau `if`, nó tiếp tục dùng được vì mọi trường hợp làm điều kiện đúng đều đã kết thúc bằng `return`.

## 7. Phạm vi trong các nhánh `else if` và điều kiện lồng nhau

Mỗi nhánh `else if` có điều kiện riêng. Biến pattern của một điều kiện chỉ có mặt ở các vị trí mà kết quả của điều kiện đó chứng minh pattern đã khớp:

```java
static void classify(Object value) {
    if (value instanceof String text) {
        System.out.println("Chuỗi: " + text.strip());
    } else if (value instanceof Integer number) {
        System.out.println("Số nguyên: " + number);
    } else {
        System.out.println("Kiểu khác hoặc null");
    }
}
```

Trong nhánh đầu, `text` được dùng vì điều kiện đầu đúng. Nếu nhánh đầu không chạy, chương trình mới xét điều kiện tiếp theo; trong thân `else if`, `number` được dùng khi pattern `Integer` khớp. Nhánh cuối không có biến nào trong hai pattern trên được bảo đảm đã khớp.

Điều kiện lồng nhau cũng tuân theo nguyên tắc này:

```java
if (value instanceof String text) {
    if (text.length() > 10) {
        System.out.println("Chuỗi dài: " + text);
    } else {
        System.out.println("Chuỗi ngắn: " + text);
    }
}
```

Cả hai nhánh bên trong đều có thể dùng `text`, vì câu lệnh `if` bên trong chỉ được thực hiện sau khi nhánh ngoài đã xác nhận `value` là `String`.

## 8. Bảng tra cứu nhanh

| Cách viết điều kiện | Nhánh `if` | Nhánh `else` | Sau `if` |
|---|---|---|---|
| `value instanceof String text` không có `else` | Dùng được | Không có nhánh `else` | Không dùng được |
| `!(value instanceof String text)` | Không dùng được | Dùng được | Có thể dùng nếu nhánh `if` kết thúc luồng |
| `value instanceof String text && test(text)` | Dùng được | Không được bảo đảm | Có thể dùng nếu nhánh `else` kết thúc luồng |
| `value instanceof String text` với `else { return; }` | Dùng được | Không dùng được | Dùng được |
| `value instanceof String text` với hai nhánh đều tiếp tục | Dùng được | Không dùng được | Không dùng được |

## 9. Cách đọc lỗi compiler và áp dụng

Khi compiler báo pattern variable không thể được tìm thấy tại một dòng lệnh, hãy kiểm tra ba điều:

1. Vị trí đó nằm trong nhánh nào: nhánh điều kiện đúng, nhánh `else`, hay phần sau câu lệnh `if`?
2. Kết quả điều kiện có thật sự chứng minh pattern đã khớp trên mọi đường đi đến vị trí đó không?
3. Nếu muốn dùng biến sau `if`, nhánh cho phép pattern thất bại đã kết thúc bằng `return`, `throw` hoặc một luồng điều khiển không thể đi tiếp chưa?

Ưu tiên đặt phép kiểm tra kiểu gần nơi sử dụng, dùng nhánh `else` để xử lý trường hợp không khớp, và dùng guard clause khi cần bảo đảm phần còn lại của phương thức chỉ nhận giá trị đúng kiểu. Những cách viết này giúp compiler kiểm tra phạm vi rõ ràng và tránh ép kiểu thủ công.

Pattern variable trong Java 16 được quản lý theo luồng điều khiển. Biến xuất hiện trong nhánh `if` khi điều kiện chứng minh pattern đúng, xuất hiện trong nhánh `else` khi điều kiện phủ định làm pattern đúng, và có thể tiếp tục tồn tại sau `if` khi mọi đường đi còn lại đều đã xác nhận pattern khớp. Quy tắc này vẫn hữu ích và được giữ trong Java hiện đại.
