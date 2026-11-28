# Flow scoping và điều kiện compiler chứng minh pattern đã khớp

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Cú pháp này cho phép kiểm tra kiểu và khai báo biến pattern trong cùng một biểu thức:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Điểm quan trọng là `text` chỉ được sử dụng ở những vị trí mà trình biên dịch chứng minh được phép kiểm tra `instanceof` đã thành công. Cách xác định phạm vi đó được gọi là **flow scoping**. Phạm vi của biến pattern phụ thuộc vào luồng điều khiển và kết quả đúng hoặc sai của biểu thức, thay vì chỉ phụ thuộc vào cặp dấu ngoặc nhọn gần nhất.

Quy tắc này vẫn được áp dụng trong các phiên bản Java hiện đại. Khi dùng pattern matching cho `instanceof`, không cần bật chế độ preview hay thêm cờ thử nghiệm.

Trong module Java 16, pattern matching cho `instanceof` là một trong những cải tiến ngôn ngữ vẫn hữu ích bên cạnh `record` và các API Stream. Module cũng đề cập đến đóng gói JDK, đóng gói ứng dụng và thay đổi JVM; bài này tập trung vào cách compiler xác định phạm vi của biến pattern. Các ví dụ dưới đây chỉ sử dụng cú pháp đã được chuẩn hóa và tiếp tục dùng được trong Java hiện đại.

## 1. Quy tắc cốt lõi: biến chỉ tồn tại khi pattern đã khớp

Trong biểu thức `value instanceof String text`:

- `value` là giá trị được kiểm tra.
- `String` là kiểu cần khớp.
- `text` là biến pattern, nhận giá trị đã được kiểm tra và có kiểu tĩnh là `String`.
- Nếu biểu thức đúng, compiler biết `value` là một `String` tại nhánh đang xét và cho phép dùng `text`.
- Nếu biểu thức sai, biến `text` không được khởi tạo và không nằm trong phạm vi có thể sử dụng.

Ví dụ:

```java
static void printLength(Object value) {
    if (value instanceof String text) {
        // Nhánh này chỉ chạy khi value là String.
        System.out.println(text.length());
    }

    // Không thể dùng text ở đây: điều kiện có thể đã sai.
}
```

Compiler kiểm tra quy tắc này ngay khi biên dịch. Nếu dùng `text` ở nơi pattern chưa chắc đã khớp, chương trình sẽ không biên dịch. Nhờ vậy, mã không phải tự ép kiểu sau khi kiểm tra và không thể vô tình sử dụng biến pattern khi giá trị ban đầu thuộc kiểu khác.

## 2. Flow scoping với toán tử `&&`

Toán tử `&&` đánh giá vế phải khi và chỉ khi vế trái đúng. Vì thế, nếu vế trái là một pattern `instanceof`, compiler biết pattern đã khớp khi bắt đầu đánh giá vế phải.

```java
static void printLongString(Object value) {
    if (value instanceof String text && text.length() >= 5) {
        System.out.println("Chuỗi đủ dài: " + text);
    }
}
```

Trình tự đánh giá:

1. Java kiểm tra `value instanceof String text`.
2. Nếu kết quả sai, vế phải của `&&` không được đánh giá.
3. Nếu kết quả đúng, biến `text` đã được gán và Java mới đánh giá `text.length() >= 5`.
4. Khi toàn bộ điều kiện đúng, `text` tiếp tục nằm trong phạm vi của thân câu lệnh `if`.

Đây là lý do biến pattern có thể được dùng ngay trong vế phải của `&&`, dù nó được khai báo ở vế trái.

## 3. Vì sao `||` thường không cho phép dùng biến pattern ở vế phải?

Toán tử `||` chỉ đánh giá vế phải khi vế trái sai. Với điều kiện thông thường dưới đây, khi Java đánh giá vế phải thì pattern chưa khớp:

```java
if (value instanceof String text || isFallbackAllowed()) {
    // Không thể dùng text ở đây.
}
```

Toàn bộ điều kiện có thể đúng vì `isFallbackAllowed()` trả về `true`, ngay cả khi `value` không phải `String`. Do đó, compiler không thể chứng minh `text` đã được gán trong thân `if`.

Tuy nhiên, kết hợp `||` với phủ định có thể tạo ra một điều kiện mà compiler chứng minh được pattern đã khớp:

```java
static void printNonBlank(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return;
    }

    // Đến đây, text chắc chắn là String và không rỗng theo isBlank().
    System.out.println(text.strip());
}
```

Có hai điểm cần hiểu:

- Khi vế phải `text.isBlank()` được đánh giá, vế trái `!(value instanceof String text)` đã sai. Điều đó chứng minh phép `instanceof` bên trong đã đúng, nên `text` dùng được ở vế phải.
- Nếu chương trình đi qua câu lệnh `if`, toàn bộ điều kiện phải sai. Với biểu thức `A || B`, điều đó chỉ xảy ra khi cả `A` và `B` đều sai. Vì `A` là phủ định của pattern, `A` sai chứng minh pattern đã khớp. Compiler do đó cho phép dùng `text` sau câu lệnh `if`.

Đây là mẫu kiểm tra đầu vào thường dùng: loại bỏ sớm giá trị không đúng kiểu hoặc không đạt điều kiện, sau đó xử lý biến đã được kiểm tra ở phần còn lại của phương thức.

## 4. Phủ định `!` và các nhánh `if` / `else`

Phủ định đảo ngược kết quả mà compiler có thể suy ra từ biểu thức pattern. Khi điều kiện là `!(value instanceof String text)`, nhánh điều kiện đúng có nghĩa là pattern chưa khớp; nhánh `else` có nghĩa là pattern đã khớp.

```java
if (!(value instanceof String text)) {
    System.out.println("Giá trị không phải chuỗi");
} else {
    // Pattern đã khớp trong nhánh else.
    System.out.println(text.toUpperCase());
}
```

Một cách viết khác là dùng guard clause để kết thúc sớm nhánh không hợp lệ:

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("Giá trị phải là chuỗi");
    }

    // Nhánh không khớp đã ném exception, nên tại đây text chắc chắn hợp lệ.
    return text.strip();
}
```

Sau câu lệnh `if`, compiler biết luồng thực thi chỉ có thể tiếp tục khi điều kiện sai. Điều kiện sai đồng nghĩa với `value instanceof String text` đúng, vì vậy `text` nằm trong phạm vi ở phần còn lại của khối chứa câu lệnh.

Ngược lại, với `if (value instanceof String text)`, biến `text` nằm trong thân `if`, nơi điều kiện đúng. Nó không tự động có mặt trong nhánh `else`, bởi nhánh đó được chạy khi pattern không khớp.

## 5. Flow scoping trong biểu thức điều kiện ba ngôi

Biến pattern cũng có thể được dùng trong nhánh đúng của toán tử điều kiện `?:`:

```java
static int lengthOrZero(Object value) {
    return value instanceof String text ? text.length() : 0;
}
```

Biểu thức sau dấu `?` chỉ được đánh giá khi điều kiện đúng, nên `text` chắc chắn đã được gán. Nhánh sau dấu `:` được đánh giá khi điều kiện sai và không thể sử dụng `text`.

## 6. Phạm vi của biến pattern không lan theo suy luận tùy ý

Flow scoping dựa trên các quy tắc luồng điều khiển mà Java định nghĩa. Compiler không suy luận mối liên hệ giữa một biến boolean được lưu riêng và kết quả của phép kiểm tra kiểu.

```java
boolean isText = value instanceof String text;

if (isText) {
    // Không thể dùng text ở đây.
}
```

Mặc dù người viết biết `isText` được tạo từ phép kiểm tra trên, biến `text` không nằm trong phạm vi của thân `if`. Khi chỉ giữ lại kết quả boolean, mối liên hệ luồng điều khiển cần thiết để chứng minh pattern đã khớp không còn được biểu diễn trong điều kiện.

Tương tự, một phương thức trợ giúp trả về `boolean` không thể đưa biến pattern ra phạm vi của nơi gọi:

```java
static boolean isString(Object value) {
    return value instanceof String text;
}

static void process(Object value) {
    if (isString(value)) {
        // Không có biến pattern text tại đây.
    }
}
```

Nếu cần dùng giá trị dưới kiểu `String`, hãy thực hiện pattern matching tại vị trí xử lý hoặc thiết kế phương thức trợ giúp trả về một giá trị có kiểu phù hợp. Không nên kỳ vọng compiler suy luận qua lời gọi phương thức tùy ý.

## 7. Bảng ghi nhớ quy tắc thường gặp

| Cấu trúc | Vị trí có thể dùng biến pattern | Lý do |
|---|---|---|
| `if (value instanceof String text)` | Thân `if` | Thân `if` chỉ chạy khi pattern khớp. |
| `value instanceof String text && text.isBlank()` | Vế phải của `&&` | Vế phải chỉ chạy khi vế trái đúng. |
| `value instanceof String text || ...` | Không dùng được ở vế phải hoặc thân `if` chỉ dựa trên điều kiện này | Điều kiện có thể đúng dù pattern không khớp. |
| `!(value instanceof String text) || text.isBlank()` | Vế phải của `||`; sau `if` nếu nhánh `if` kết thúc luồng | Vế phải chỉ chạy khi phủ định sai; đi tiếp sau guard cũng chứng minh pattern đã khớp. |
| `if (!(value instanceof String text)) ... else ...` | Nhánh `else` | Nhánh `else` chạy khi pattern khớp. |
| `value instanceof String text ? text.length() : 0` | Nhánh sau `?` | Nhánh này chỉ được đánh giá khi điều kiện đúng. |

## 8. Ví dụ hoàn chỉnh

Ví dụ sau kết hợp điều kiện `&&`, guard clause với `||` và biểu thức ba ngôi:

```java
public class FlowScopingDemo {

    static void printLongString(Object value) {
        if (value instanceof String text && text.length() >= 5) {
            System.out.println("Chuỗi dài: " + text);
        }
    }

    static void printNonBlank(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            System.out.println("Không có chuỗi hợp lệ");
            return;
        }

        System.out.println("Nội dung: " + text.strip());
    }

    static int lengthOrZero(Object value) {
        return value instanceof String text ? text.length() : 0;
    }

    public static void main(String[] args) {
        printLongString("Java pattern matching");
        printLongString(42);

        printNonBlank("  Flow scoping  ");
        printNonBlank("   ");
        printNonBlank(null);

        System.out.println(lengthOrZero("Java"));
        System.out.println(lengthOrZero(100));
    }
}
```

Có thể biên dịch với JDK 16 trở lên. Khi dùng JDK mới và muốn kiểm tra cú pháp theo mức Java 16, có thể chạy:

```bash
javac --release 16 FlowScopingDemo.java
java FlowScopingDemo
```

## 9. Cách áp dụng khi viết mã

- Đặt phép kiểm tra `instanceof` ngay tại nơi cần sử dụng giá trị đã kiểm tra để compiler theo dõi được luồng điều khiển.
- Dùng `&&` khi các điều kiện tiếp theo cần truy cập biến pattern.
- Dùng phủ định kết hợp guard clause khi muốn loại bỏ sớm giá trị sai kiểu hoặc không đạt yêu cầu.
- Đọc điều kiện theo thứ tự đánh giá thực tế của `&&` và `||`; không giả định biến pattern luôn tồn tại trong toàn bộ câu lệnh `if`.
- Khi compiler báo biến pattern không nằm trong phạm vi, hãy kiểm tra xem mọi đường đi đến vị trí sử dụng có thật sự chứng minh được pattern đã khớp hay không.

Flow scoping giúp mã Java ngắn gọn hơn nhưng vẫn giữ được kiểm tra kiểu tĩnh. Nắm vững quan hệ giữa kết quả đúng/sai của biểu thức, toán tử short-circuit và các nhánh điều khiển sẽ giúp sử dụng pattern matching cho `instanceof` an toàn trong Java 16 và các phiên bản Java hiện đại.
