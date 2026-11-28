# Vì sao || không cho phép dùng biến chưa chắc được khởi tạo

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Khi một phép kiểm tra kiểu khớp, Java tạo một **pattern variable** có kiểu đã kiểm tra. Compiler chỉ cho phép dùng biến này ở những vị trí mà luồng điều khiển chứng minh pattern đã khớp.

Toán tử `||` (OR có đánh giá ngắn mạch) thường gây nhầm lẫn khi kết hợp với pattern variable. Vế phải của `||` chỉ chạy khi vế trái sai. Với một pattern `instanceof` thông thường, vế trái sai chính là trường hợp pattern chưa khớp. Vì vậy, biến pattern không thể được dùng tùy ý ở vế phải hoặc trong thân `if`.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích trong Java hiện đại, bên cạnh `record` và các API Stream. Bài này giải thích mối liên hệ giữa `||`, short-circuit và trạng thái khớp của pattern, đồng thời chỉ ra trường hợp phủ định pattern có thể dùng biến ở vế phải. Các ví dụ sử dụng cú pháp đã được chuẩn hóa, không cần preview feature.

## 1. `||` đánh giá vế phải khi vế trái sai

Toán tử `||` thực hiện phép OR có đánh giá ngắn mạch:

1. Java đánh giá vế trái.
2. Nếu vế trái đúng, toàn biểu thức đã đúng nên Java bỏ qua vế phải.
3. Nếu vế trái sai, Java phải đánh giá vế phải để xác định kết quả.

Ví dụ thông thường:

```java
if (isCached() || loadFromDatabase()) {
    System.out.println("Đã tìm thấy dữ liệu");
}
```

Nếu `isCached()` trả về `true`, `loadFromDatabase()` không được gọi. Nếu vế trái trả về `false`, Java mới gọi phương thức ở vế phải.

Đặc điểm này quan trọng với pattern matching: vị trí được đánh giá sau một vế `instanceof` sai không thể giả định rằng pattern đó đã khớp.

## 2. Vì sao pattern dương không dùng được ở vế phải?

Xét biểu thức sau:

```java
if (value instanceof String text || text.isEmpty()) {
    System.out.println("Đã xử lý");
}
```

Đoạn mã không biên dịch vì `text` không nằm trong phạm vi sử dụng ở vế phải. Để Java đánh giá `text.isEmpty()`, vế trái `value instanceof String text` phải sai. Khi đó, pattern chưa khớp và `text` chưa được gán.

Đọc theo hai trường hợp:

- Nếu `value` là `String`, vế trái đúng. Java bỏ qua vế phải; `text` đã khớp nhưng vế phải không chạy.
- Nếu `value` không phải `String` hoặc là `null`, vế trái sai. Java đánh giá vế phải, nhưng không có biến `text` hợp lệ để gọi `isEmpty()`.

Đây là xung đột giữa điều kiện đánh giá của `||` và điều kiện cần để pattern variable có giá trị. Với `&&`, vế phải chỉ chạy khi vế trái đúng; với `||`, vế phải chỉ chạy khi vế trái sai.

## 3. Vì sao thân `if` cũng không được dùng biến?

Một biến pattern có thể được dùng trong thân `if` khi điều kiện đúng chứng minh pattern đã khớp. Nhưng với biểu thức OR, điều kiện đúng không đồng nghĩa với vế `instanceof` đúng.

```java
static boolean fallbackAllowed(Object value) {
    return value == null;
}

static void handle(Object value) {
    if (value instanceof String text || fallbackAllowed(value)) {
        // Không thể dùng text tại đây.
        System.out.println("Điều kiện đã đúng");
    }
}
```

Thân `if` có thể được thực hiện theo hai đường:

- Pattern khớp và vế trái đúng.
- Pattern không khớp nhưng `fallbackAllowed(value)` trả về `true`.

Compiler phải xét tất cả đường đi có thể đến thân `if`. Vì có một đường đi mà pattern chưa khớp, `text` không được bảo đảm đã có giá trị tại đó.

Nhánh `else` cũng không thể dùng `text` trong mẫu này. Nếu toàn biểu thức OR sai, cả vế trái lẫn vế phải đều phải sai; riêng điều đó xác nhận pattern ở vế trái đã không khớp.

## 4. Quy tắc cần nhớ: điều kiện đúng của OR không chứng minh từng vế đúng

Với biểu thức `A || B`, kết quả đúng chỉ cho biết ít nhất một trong hai vế đúng. Nó không cho biết vế `A` chắc chắn đúng. Vì vậy, nếu pattern variable chỉ được gán khi `A` đúng, thân `if` không thể mặc định sử dụng biến đó.

| Vị trí | Điều Java biết với `A || B` |
|---|---|
| Vế phải `B` | `A` sai, vì vậy không thể dựa vào pattern dương được khai báo trong `A`. |
| Thân `if` | `A` đúng hoặc `B` đúng; không bảo đảm `A` đúng. |
| Nhánh `else` | Cả `A` và `B` đều sai; pattern dương trong `A` chắc chắn không khớp. |

Đây là lý do không nên hiểu đơn giản rằng “điều kiện `if` đúng thì mọi biến pattern trong điều kiện đều dùng được”. Compiler cần chứng minh pattern cụ thể đã khớp trên mọi đường đi đến vị trí sử dụng.

## 5. Trường hợp đặc biệt: phủ định pattern ở vế trái

`||` không cấm mọi cách sử dụng pattern variable. Nếu vế trái là phép phủ định của pattern, khi vế trái sai thì pattern bên trong phải đúng.

```java
static void printNonBlank(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return;
    }

    // text đã khớp và chuỗi không rỗng theo isBlank().
    System.out.println(text.strip());
}
```

Trong biểu thức này, `text` dùng được ở vế phải `text.isBlank()`. Java chỉ đánh giá vế phải khi vế trái sai. Mà vế trái là `!(value instanceof String text)`, nên khi nó sai, phép `instanceof` bên trong đã đúng và `text` đã được gán.

Có thể phân tích kết quả:

- Nếu `value` không phải `String` hoặc là `null`, biểu thức phủ định bên trái đúng. Java bỏ qua vế phải và đi vào thân `if`, nơi `return` kết thúc phương thức.
- Nếu `value` là chuỗi rỗng hoặc chỉ có khoảng trắng, vế trái sai, Java kiểm tra `text.isBlank()`, kết quả đúng và thân `if` kết thúc phương thức.
- Nếu `value` là chuỗi có nội dung, cả vế trái và vế phải đều sai. Toàn điều kiện sai nên chương trình đi tiếp sau `if`.

Khi chương trình đi tiếp, compiler chứng minh `text` chắc chắn đã khớp. Đây là mẫu **guard clause**: loại bỏ sớm trường hợp không hợp lệ rồi xử lý dữ liệu đã được xác nhận ở phần còn lại của phương thức.

## 6. Vì sao biến vẫn không dùng được trong thân `if` của ví dụ phủ định?

Trong ví dụ trước, dù `text` dùng được ở vế phải, không thể dùng nó tùy ý trong thân `if`:

```java
if (!(value instanceof String text) || text.isBlank()) {
    // Không thể dùng text ở đây.
    return;
}
```

Thân `if` chạy khi toàn biểu thức đúng. Điều đó có thể xảy ra ngay vì vế trái đúng, tức pattern chưa khớp. Nó cũng có thể xảy ra vì vế trái sai nhưng `text.isBlank()` đúng. Compiler không thể đảm bảo pattern đã khớp trên tất cả đường đi vào thân `if`.

Ngược lại, nhánh `else` của chính điều kiện này chỉ chạy khi toàn biểu thức sai. Khi OR sai, vế trái phải sai; vì vế trái là phủ định, pattern bên trong chắc chắn đúng. Do đó, có thể dùng `text` trong nhánh `else`:

```java
if (!(value instanceof String text) || text.isBlank()) {
    System.out.println("Không có chuỗi hợp lệ");
} else {
    // Điều kiện OR sai chứng minh text là String và không blank.
    System.out.println(text.strip());
}
```

## 7. Dùng `&&` khi tất cả điều kiện phải cùng đúng

Nếu mục tiêu là xác nhận giá trị thuộc kiểu mong muốn rồi kiểm tra thêm đặc điểm của nó, `&&` thường diễn đạt đúng ý định:

```java
static void printLongText(Object value) {
    if (value instanceof String text && !text.isBlank() && text.length() > 20) {
        System.out.println(text);
    }
}
```

Mỗi vế sau chỉ được đánh giá khi các vế trước đúng. Do đó:

- `text` đã được tạo trước khi gọi `isBlank()`.
- `length()` chỉ được gọi khi giá trị là `String` và không blank.
- Thân `if` chỉ chạy khi cả ba điều kiện đúng.

Nếu thay `&&` bằng `||`, ý nghĩa thay đổi thành “chỉ cần một điều kiện đúng”. Ngoài việc có thể làm chương trình chấp nhận dữ liệu không mong muốn, cách viết đó cũng không bảo đảm biến pattern đã khớp trong thân `if`.

## 8. Khi cần chấp nhận nhiều kiểu dữ liệu

Đôi khi OR được dùng để chấp nhận một trong nhiều kiểu. Khi đó, không nên mong đợi một biến pattern cụ thể đại diện cho mọi trường hợp:

```java
static void handleValue(Object value) {
    if (value instanceof String text) {
        System.out.println("Chuỗi: " + text.toUpperCase());
    } else if (value instanceof Integer number) {
        System.out.println("Số nguyên: " + number.intValue());
    } else {
        System.out.println("Kiểu chưa hỗ trợ");
    }
}
```

Mỗi nhánh xác nhận một kiểu riêng và sử dụng biến pattern tương ứng. Cách này rõ ràng hơn một điều kiện OR gộp các kiểu khác nhau rồi cố gọi phương thức riêng của một trong các kiểu đó.

Nếu các kiểu được chấp nhận có chung một kiểu cha hoặc interface phù hợp, có thể kiểm tra kiểu chung đó:

```java
static void printSequence(Object value) {
    if (value instanceof CharSequence sequence && sequence.length() > 0) {
        System.out.println(sequence);
    }
}
```

`String` và `StringBuilder` đều triển khai `CharSequence`, vì vậy kiểm tra kiểu chung cho phép xử lý cả hai qua cùng biến `sequence`.

## 9. Bảng so sánh nhanh `&&` và `||`

| Biểu thức | Vế phải được đánh giá khi | Pattern variable dùng được ở vế phải? |
|---|---|---|
| `value instanceof String text && text.isEmpty()` | Pattern khớp | Có |
| `value instanceof String text || fallback()` | Pattern không khớp | Không |
| `!(value instanceof String text) || text.isBlank()` | Pattern khớp | Có |
| `!(value instanceof String text) && text.isBlank()` | Pattern chưa khớp | Không |

Hãy chú ý rằng trường hợp thứ ba không phải ngoại lệ tùy tiện. Nó tuân theo cùng quy tắc flow scoping: vế phải của `||` chỉ chạy khi vế trái sai; phủ định sai có nghĩa pattern gốc đúng.

## 10. Cách xử lý khi compiler báo lỗi phạm vi

Khi compiler báo pattern variable không thể được tìm thấy hoặc chưa được khớp, hãy lần lượt kiểm tra:

1. Biến pattern được khai báo trong vế nào của biểu thức?
2. Toán tử `&&` hay `||` quyết định điều kiện nào để vế tiếp theo được đánh giá?
3. Tại vị trí dùng biến, kết quả của các vế trước có chứng minh pattern đã khớp hay có thể đã sai?
4. Nếu cần xử lý nhiều kiểu, có thể tách thành `if` / `else if` để mỗi nhánh có pattern riêng hay dùng một interface chung không?

Không sửa lỗi bằng cách ép kiểu cưỡng bức khi chưa xác nhận kiểu runtime. Hãy tổ chức lại điều kiện để compiler có thể chứng minh pattern đã khớp trước khi truy cập biến.

`||` phù hợp khi chỉ cần một trong các điều kiện đúng. Nó không bảo đảm pattern ở vế trái đã khớp khi vế phải hoặc thân `if` được thực hiện. `&&` phù hợp khi cần xác nhận kiểu trước rồi kiểm tra tiếp dữ liệu. Với `||` kết hợp phủ định pattern, hãy đọc kỹ chiều đúng/sai: vế phải có thể dùng biến khi phủ định sai, còn thân `if` vẫn có thể chứa đường đi mà pattern chưa khớp. Các quy tắc này vẫn áp dụng trong Java hiện đại.
