# Kết hợp `instanceof` với block lệnh

**Chủ đề:** Java Core Pattern Matching → instanceof cơ bản  
**Phiên bản áp dụng:** Java 17 trở lên; cách viết `instanceof` có *pattern variable* đã chính thức từ Java 16.

## 1. Vì sao cần kết hợp `instanceof` với block lệnh?

Một biến có kiểu khai báo rộng như `Object` có thể tham chiếu đến đối tượng thuộc nhiều kiểu thực tế. `instanceof` trả về `true` khi giá trị khác `null` và đối tượng tương thích với kiểu tham chiếu được kiểm tra; ngược lại trả về `false`. Ta thường đặt phép kiểm tra trong điều kiện `if`, rồi dùng **block lệnh** `{ ... }` để gom các thao tác chỉ được thực hiện sau khi kiểm tra thành công.

Block giúp tạo ranh giới rõ ràng: trong nhánh đúng, ta xử lý dữ liệu theo kiểu đã được xác nhận; trong `else` hoặc `else if`, ta xử lý tình huống không khớp. Cách tổ chức này vừa hạn chế việc ép kiểu sai vừa làm mã dễ theo dõi khi có nhiều thao tác nối tiếp.

## 2. Cách truyền thống: kiểm tra rồi ép kiểu trong block

Ví dụ minh họa (đoạn mã đặt trong một phương thức có biến `value` kiểu `Object`):

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println("Độ dài: " + text.length());
    System.out.println("Chữ hoa: " + text.toUpperCase());
} else {
    System.out.println("Không phải chuỗi");
}
```

Trong nhánh `if`, `instanceof String` cho biết phép ép kiểu `(String) value` có thể thực hiện an toàn đối với **giá trị vừa được kiểm tra**, nếu không có thay đổi liên quan giữa bước kiểm tra và ép kiểu. Biến `text` khai báo trong `{ ... }` có phạm vi từ vị trí khai báo đến hết block. Nhánh `else` chạy khi `value` là kiểu khác hoặc `null`.

Đừng đưa phép ép kiểu ra trước điều kiện:

```java
// Sai về logic: có thể ném ClassCastException trước khi kiểm tra.
String text = (String) value;
if (value instanceof String) {
    System.out.println(text.length());
}
```

Mã trên chỉ là ví dụ **không an toàn**, không phải mẫu cần sử dụng. Nếu `value` là `Integer`, việc ép kiểu thất bại trước khi chương trình tới `if`. Việc ép `null` sang `String` riêng nó không ném `ClassCastException`, nhưng thao tác `text.length()` sẽ lỗi nếu không kiểm tra thêm.

## 3. Cách hiện đại: type pattern ngay trong điều kiện `if`

Java cho phép đưa việc kiểm tra kiểu và khai báo biến đã được gắn kiểu vào một biểu thức:

```java
if (value instanceof String text) {
    System.out.println("Độ dài: " + text.length());
    System.out.println("Chữ hoa: " + text.toUpperCase());
} else {
    System.out.println("Không phải chuỗi");
}
```

Ở đây:

- `String` là kiểu được kiểm tra.
- `text` là *pattern variable*; nó được gắn với đối tượng đã khớp, có kiểu tĩnh `String`.
- Block `if` chỉ chạy khi pattern khớp. Không cần viết thêm `(String) value` trong block.
- `text` không khả dụng trong nhánh `else` của ví dụ trên vì nhánh đó chỉ chạy khi pattern không khớp.

Hai cách trên có cùng mục đích trong tình huống đơn giản. Pattern variable giảm một bước ép kiểu và tránh việc vô tình ép lại một biến đã thay đổi. Khi làm việc với dự án Java 17+, nên ưu tiên cách viết này nếu nó giúp mã rõ ràng.

## 4. Block lồng nhau và chuỗi `if / else if / else`

Sau khi nhận diện đúng kiểu, block có thể chứa nhiều câu lệnh và điều kiện lồng nhau:

```java
if (value instanceof String text) {
    if (text.isBlank()) {
        System.out.println("Chuỗi rỗng hoặc chỉ có khoảng trắng");
    } else {
        System.out.println("Số ký tự: " + text.length());
    }
} else if (value instanceof Integer number) {
    System.out.println("Số nguyên: " + number);
} else {
    System.out.println("Kiểu khác hoặc null");
}
```

Trình tự thực hiện:

1. Kiểm tra `String`; nếu đúng, block đầu chạy và chương trình không xét `else if` phía sau.
2. Nếu không phải `String`, thử `Integer`; trong block tương ứng, `number` có kiểu `Integer`.
3. Nếu cả hai đều không khớp, chạy block `else`.

Lệnh bên trong các block có thể gọi phương thức, khai báo biến cục bộ hoặc trả kết quả. Nên dùng `{ ... }` dù một nhánh chỉ có một câu lệnh để việc bổ sung dòng xử lý sau này không vô tình làm thay đổi luồng điều khiển. Khi bỏ dấu ngoặc nhọn, `if` chỉ điều khiển **một statement** ngay sau điều kiện.

## 5. Phạm vi biến: block thông thường và flow scoping

Với biến cục bộ thông thường, phạm vi được quyết định phần lớn bởi vị trí khai báo và dấu ngoặc nhọn:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
// Không thể dùng biến cục bộ text ở đây.
```

Với biến pattern, Java còn phân tích **luồng điều khiển** (*flow scoping*): biến chỉ nằm trong phạm vi mà trình biên dịch có thể chứng minh pattern đã khớp. Những ví dụ sau minh họa quy tắc:

```java
if (value instanceof String text) {
    System.out.println(text.length()); // Hợp lệ: pattern đã khớp.
} else {
    System.out.println("Không phải String");
    // text.length();                 // Không hợp lệ: text ngoài phạm vi.
}
```

Trong điều kiện có toán tử `&&`, toán hạng bên phải chỉ được đánh giá nếu toán hạng trái là `true`. Do đó phép kiểm tra thứ hai có thể dùng biến pattern:

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println("Chuỗi có ít nhất 4 ký tự");
}
```

Ngược lại, trong điều kiện `||`, nhánh phải có thể làm cả biểu thức đúng khi pattern **không** khớp, nên không thể dùng biến pattern như đã chắc chắn tồn tại:

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof String text || text.isEmpty()) { }
// Vì khi value không phải String, text chưa được gắn giá trị.
```

Trường hợp phủ định cần quan sát cả đường đi của chương trình. Khi nhánh không khớp kết thúc phương thức bằng `return`, biến pattern có thể tiếp tục dùng sau block:

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length(); // Hợp lệ: để đi tới đây, value phải khớp String.
}
```

Đây là ưu điểm đáng học của flow scoping: trình biên dịch xác định các vị trí an toàn theo đường đi thực tế, thay vì đơn giản cho rằng biến pattern chỉ dùng được trong dấu ngoặc nhọn của `if`.

## 6. Ví dụ hoàn chỉnh chạy trên Java 17+

Tạo tệp **`InstanceofBlocksDemo.java`**:

```java
public class InstanceofBlocksDemo {
    static void describe(Object value) {
        if (value instanceof String text) {
            if (text.isBlank()) {
                System.out.println("Blank");
            } else {
                System.out.println("Text(" + text + ") length=" + text.length());
            }
        } else if (value instanceof Integer number) {
            System.out.println("Integer=" + number);
        } else {
            System.out.println("Other");
        }
    }

    static boolean hasAtLeastFourChars(Object value) {
        return value instanceof String text && text.length() >= 4;
    }

    public static void main(String[] args) {
        describe("Java");
        describe("   ");
        describe(7);
        describe(null);

        System.out.println("Long Java=" + hasAtLeastFourChars("Java"));
        System.out.println("Long Hi=" + hasAtLeastFourChars("Hi"));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac --release 17 InstanceofBlocksDemo.java
java InstanceofBlocksDemo
```

Kết quả chính xác:

```text
Text(Java) length=4
Blank
Integer=7
Other
Long Java=true
Long Hi=false
```

**Diễn giải:**

- `"Java"` khớp `String text`, đi vào nhánh `!text.isBlank()` và in độ dài `4`.
- `"   "` vẫn là `String`; `isBlank()` trả về `true` nên in `Blank`.
- `7` được autobox thành `Integer` khi truyền vào tham số `Object`, nên vào nhánh `Integer number`.
- `null` không khớp các type pattern trên, nên vào `else`.
- Phương thức `hasAtLeastFourChars` cho thấy `&&` vừa bảo vệ việc truy cập `text.length()`, vừa trả về `false` cho chuỗi ngắn hoặc đối tượng không phải `String`.

Nếu muốn dùng cách viết truyền thống, thay nhánh `if (value instanceof String text)` bằng `if (value instanceof String)`, rồi khai báo `String text = (String) value;` ở đầu block; các nhánh sau giữ nguyên ý nghĩa.

## 7. Những lỗi thường gặp khi phối hợp với block

| Vấn đề | Vì sao sai hoặc rủi ro | Cách sửa |
| --- | --- | --- |
| Ép kiểu trước `instanceof` | Có thể ném `ClassCastException` trước khi kiểm tra | Ép trong nhánh đã khớp hoặc dùng type pattern |
| Dùng `text` ở `else` của `if (value instanceof String text)` | Nhánh `else` không bảo đảm pattern đã khớp | Chỉ dùng `text` tại vị trí được flow scoping cho phép |
| Dùng `text` ở vế phải `||` trong cùng điều kiện | Nhánh phải có thể chạy khi pattern không khớp | Dùng `&&`, hoặc tách thành các nhánh rõ ràng |
| Quên xử lý `null` | `instanceof` trả `false` với `null` | Xử lý ở `else` hoặc kiểm tra `null` riêng |
| Kiểm tra một biến nhưng ép kiểu biến khác | Kiểm tra không bảo đảm biến khác có cùng kiểu | Dùng đúng giá trị được kiểm tra hoặc trực tiếp dùng pattern variable |
| Thay đổi biến `value` rồi ép lại sau khi kiểm tra | Giá trị mới có thể không còn là kiểu vừa xác nhận | Không dựa vào kết quả kiểm tra cũ cho giá trị đã thay đổi |
| Bỏ dấu `{ ... }` khi có nhiều thao tác | Chỉ statement đầu tiên thuộc `if` | Dùng block đầy đủ cho các nhánh |
| Viết `value instanceof java.util.List<String>` | Type argument thường bị xóa ở runtime, không phải kiểm tra reifiable hợp lệ | Dùng `List<?>` rồi kiểm tra phần tử theo nhu cầu |

Một block dài chứa nhiều kiểm tra kiểu thường là dấu hiệu nên cân nhắc tách phương thức. Nếu hành vi thuộc về từng lớp trong cùng một hệ phân cấp, cơ chế đa hình (`override`) có thể phù hợp hơn việc liên tục thêm `else if`.

## 8. Bài tập tự kiểm tra

1. Viết phương thức `printShape(Object value)` dùng `if / else if / else` để phân biệt `String`, `Integer`, và giá trị khác, mỗi nhánh có block `{ ... }`.
2. Trong block xử lý `String`, thêm một `if` lồng nhau để phân biệt chuỗi `isEmpty()` và chuỗi có nội dung. Giải thích vì sao chuỗi `"   "` có `isEmpty() == false` nhưng `isBlank() == true`.
3. Chuyển mã có `instanceof` + ép kiểu thủ công sang cú pháp `instanceof String text`, bảo đảm không dùng `text` ngoài phạm vi.
4. Viết phương thức trả về `-1` nếu tham số không phải `String`, còn lại trả về độ dài chuỗi; thử cả dạng block `if` thông thường và dạng phủ định rồi `return` sớm.
5. Thử biên dịch ví dụ có `||` không hợp lệ ở mục 5, đọc lỗi trình biên dịch, sau đó sửa bằng `&&` hoặc tách nhánh.

**Tiêu chí hoàn thành:** đọc được luồng thực thi của các block, xác định chính xác thời điểm phép ép kiểu là an toàn, sử dụng đúng phạm vi biến pattern và dự đoán được kết quả với `String`, `Integer`, đối tượng không khớp và `null`.

**Tham khảo:** [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394); [Java Language Specification, `instanceof` operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2).
