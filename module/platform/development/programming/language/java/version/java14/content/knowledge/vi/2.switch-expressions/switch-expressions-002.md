# Biểu thức `switch` trong phép gán và `return` (Java 14+)

## 1. Mục tiêu và ý nghĩa

Từ Java 14, `switch` expression là tính năng chính thức của ngôn ngữ, tiếp tục dùng được trên các phiên bản Java hiện hành và không cần `--enable-preview`. Điểm quan trọng: toàn bộ `switch (...) { ... }` **tính ra một giá trị**. Vì thế, ta có thể gán giá trị đó cho một biến hoặc đưa trực tiếp vào `return` của phương thức, thay vì tạo biến trung gian rồi gán ở nhiều nhánh.

Sau bài này, bạn có thể:
- Viết đúng cú pháp `T value = switch (...) { ... };` và `return switch (...) { ... };`.
- Dùng `case ... -> biểuThức;`, gộp nhiều nhãn bằng dấu phẩy, và dùng `yield` khi một nhánh cần nhiều câu lệnh.
- Bảo đảm tất cả giá trị đầu vào được xử lý (`exhaustive`) và mỗi nhánh thành công sinh ra một giá trị phù hợp với kiểu đích.
- Phân biệt `yield` (trả giá trị cho **biểu thức switch**) với `return` (trả giá trị cho **phương thức**).

## 2. Cấu trúc trong phép gán

~~~java
int level = 2;
String label = switch (level) {
    case 1 -> "Cơ bản";
    case 2, 3 -> "Nâng cao";
    default -> "Không xác định";
};
~~~

Đây là đoạn minh họa đặt **bên trong một phương thức**. Với `level = 2`, biến `label` nhận chuỗi `"Nâng cao"`.

Đọc cấu trúc từ ngoài vào trong:

1. `String label =` quy định biến đích và kiểu giá trị cần nhận.
2. `switch (level)` đánh giá biểu thức chọn nhánh (`selector`); Java thực hiện nhánh `case` phù hợp.
3. `case 2, 3 -> "Nâng cao";` chọn một trong hai giá trị và tạo ra kết quả chuỗi. Dấu `->` **không rơi xuyên** sang nhánh tiếp theo (`fall-through`).
4. `default -> ...;` cung cấp kết quả cho các giá trị khác.
5. Dấu `;` sau dấu `}` là dấu kết thúc **câu lệnh gán**: `};`. Mỗi nhánh dạng `-> biểuThức` cũng kết thúc bằng `;`.

Cách đọc ngắn gọn: **“gán cho `label` kết quả của biểu thức `switch`”**. Khi chỉ cần giá trị, cách viết này giữ biến đích được khởi tạo một lần và tránh phân tán phép gán ở nhiều nhánh.

## 3. Cấu trúc trong `return`

Nếu giá trị chỉ dùng làm kết quả của phương thức, có thể trả về trực tiếp:

~~~java
static String describeLevel(int level) {
    return switch (level) {
        case 1 -> "Cơ bản";
        case 2, 3 -> "Nâng cao";
        default -> "Không xác định";
    };
}
~~~

Đây là **phương thức** minh họa, cần đặt trong một lớp Java để biên dịch. `describeLevel(3)` trả về `"Nâng cao"`.

Trình tự thực hiện là: phương thức gọi `switch` → nhánh khớp tạo giá trị → biểu thức `switch` kết thúc với giá trị đó → câu lệnh `return` trả giá trị cho bên gọi. Kiểu kết quả phải tương thích với kiểu trả về đã khai báo của phương thức, ở đây là `String`.

**Phân biệt quan trọng:**

- `return switch (...) { ... };`: `return` nằm **bên ngoài**, trả kết quả cuối cùng của `switch` cho phương thức gọi.
- `case X -> expression;`: `expression` chính là kết quả nhánh, **không** cần viết `yield`.
- `case X -> { ... yield value; }`: `yield` kết thúc nhánh của biểu thức `switch` bằng `value`.
- Không dùng `return value;` **bên trong** khối của một `switch` expression nhằm thay cho `yield`; đây là lỗi biên dịch vì nhảy ra khỏi biểu thức đang tính giá trị.

Ví dụ, cách sau **sai**:

~~~java
// Sai: return nằm bên trong một nhánh của switch expression.
static int incorrect(int code) {
    return switch (code) {
        case 1 -> {
            return 10; // Lỗi biên dịch
        }
        default -> 0;
    };
}
~~~

Cách **đúng**: viết `case 1 -> 10;` nếu chỉ có một biểu thức; hoặc `case 1 -> { yield 10; }` nếu thực sự cần khối lệnh.

## 4. Khi nào dùng `yield`?

Nhánh dạng mũi tên có thể chứa một biểu thức, một câu lệnh `throw` hoặc một khối `{ ... }`. Trong khối có nhiều lệnh, `yield` chỉ định **giá trị của cả switch expression**.

~~~java
int items = 3;
int fee = switch ("EXPRESS") {
    case "STANDARD" -> 20_000;
    case "EXPRESS" -> {
        int extra = items >= 3 ? 10_000 : 0;
        yield 35_000 + extra;
    }
    case "PICKUP" -> 0;
    default -> throw new IllegalArgumentException("Phương thức không hợp lệ");
};
~~~

Ở đây, nhánh `"EXPRESS"` tạo biến cục bộ `extra = 10_000` rồi `yield 45_000;`. Kết quả `fee` là `45000`. Sau dấu `}` đóng **khối nhánh** không cần dấu `;`; dấu `;` nằm ở cuối `yield ...;` và cuối toàn bộ câu lệnh gán `};`.

Một nhánh `throw` hợp lệ dù không sinh giá trị: nó kết thúc bằng ngoại lệ thay vì trả kết quả. Điều này có ích cho trường hợp dữ liệu không hợp lệ. Không bắt buộc phải có `yield` ở nhánh chỉ thực hiện `throw`.

Mẫu dùng cú pháp `case ...:` với `yield` vẫn được Java hỗ trợ, nhưng với bài toán mới nên ưu tiên `->` để rõ ràng và tránh xử lý rơi xuyên giữa các nhánh.

## 5. Ví dụ đầy đủ: phép gán, `return`, `yield` và `throw`

Lưu nguyên chương trình sau thành tệp `SwitchExpressionAssignmentReturnDemo.java`. Ví dụ dùng cú pháp ổn định từ Java 14, không phụ thuộc các tính năng `switch` mới hơn.

~~~java
public class SwitchExpressionAssignmentReturnDemo {
    enum Delivery { STANDARD, EXPRESS, PICKUP }

    static int shippingFee(String method, int numberOfItems) {
        if (numberOfItems < 1) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        return switch (method) {
            case "STANDARD" -> 20_000;
            case "EXPRESS" -> {
                int extra = numberOfItems >= 3 ? 10_000 : 0;
                yield 35_000 + extra;
            }
            case "PICKUP" -> 0;
            default -> throw new IllegalArgumentException("Phương thức không hợp lệ: " + method);
        };
    }

    static String deliveryName(Delivery delivery) {
        return switch (delivery) {
            case STANDARD -> "Giao tiêu chuẩn";
            case EXPRESS -> "Giao nhanh";
            case PICKUP -> "Nhận tại cửa hàng";
        };
    }

    public static void main(String[] args) {
        Delivery selected = Delivery.EXPRESS;
        String description = switch (selected) {
            case STANDARD -> "Đơn thường";
            case EXPRESS -> "Đơn ưu tiên";
            case PICKUP -> "Tự đến nhận";
        };
        System.out.println("Gán: " + description);
        System.out.println("Return: " + shippingFee("EXPRESS", 3));
        System.out.println("Enum: " + deliveryName(Delivery.PICKUP));
    }
}
~~~

Dùng JDK 14 trở lên:

~~~bash
javac -encoding UTF-8 --release 14 SwitchExpressionAssignmentReturnDemo.java
java SwitchExpressionAssignmentReturnDemo
~~~

`--release 14` chọn bộ API/cú pháp tương thích Java 14 khi biên dịch bằng JDK phù hợp; **không** cần cờ preview.

**Kết quả stdout chính xác:**

~~~text
Gán: Đơn ưu tiên
Return: 45000
Enum: Nhận tại cửa hàng
~~~

Giải thích từng đường đi:
- Trong `main`, `selected = EXPRESS`. `switch` tạo chuỗi `"Đơn ưu tiên"` rồi **gán** cho `description`.
- `shippingFee("EXPRESS", 3)` dùng `return switch`. Nhánh `EXPRESS` tính phụ phí `10_000` và `yield 45_000`; phương thức trả số `45000`.
- `deliveryName(PICKUP)` dùng `return switch` trên `enum`. Cả ba hằng `enum` đã có nhánh, nên biểu thức đủ trường hợp dù không viết `default`.

Chương trình trên đã được kiểm tra biên dịch với `javac --release 14` và chạy ra đúng ba dòng kết quả.

## 6. Những quy tắc bắt buộc khi dùng trong gán và `return`

### 6.1. Phải bao phủ mọi trường hợp (`exhaustive`)

Một `switch` **expression** phải xác định được nhánh cho mọi giá trị có thể xảy ra; với `int` hoặc `String` thường cần `default`. Nếu thiếu, trình biên dịch báo lỗi. Với `enum`, có thể bỏ `default` **khi đã liệt kê tất cả hằng enum** đang được khai báo; thêm một hằng mới rồi biên dịch lại sẽ buộc rà soát chỗ `switch` chưa bao phủ.

~~~java
// Hợp lệ khi Delivery chỉ có STANDARD, EXPRESS, PICKUP.
String label = switch (Delivery.STANDARD) {
    case STANDARD -> "Thường";
    case EXPRESS -> "Nhanh";
    case PICKUP -> "Tại quầy";
};
~~~

Không nên thêm `default` một cách máy móc cho `enum`: nếu muốn trình biên dịch nhắc khi tập trạng thái thay đổi, hãy liệt kê đủ hằng và không dùng `default`; nếu nghiệp vụ có quy tắc xử lý giá trị dự phòng rõ ràng, hãy mô tả và dùng `default` phù hợp.

### 6.2. Nhánh phải tạo ra giá trị, hoặc ném ngoại lệ

Mọi đường đi **kết thúc bình thường** của một nhánh phải mang lại giá trị. Nếu khối `-> { ... }` kết thúc mà không có `yield`, trình biên dịch báo lỗi. Một nhánh có thể `throw` ngoại lệ thay vì sinh giá trị, như ví dụ `default` trong `shippingFee`.

~~~java
// Sai: khối case 1 hoàn tất mà không yield.
int result = switch (1) {
    case 1 -> {
        int answer = 10;
    }
    default -> 0;
};
~~~

Sửa bằng `yield answer;` ở trong khối, hoặc bỏ khối và dùng `case 1 -> 10;`.

### 6.3. Kiểu kết quả phải tương thích với kiểu đích

Trong phép gán, các biểu thức ở các nhánh phải tương thích với kiểu của biến nhận; trong `return`, chúng phải tương thích với kiểu trả về của phương thức. Ví dụ `String text = switch (...) { case ... -> "OK"; ... };` là hợp lý, còn nhánh trả `int` vào biến `String` sẽ gây lỗi kiểu. Với `var`, trình biên dịch suy luận kiểu từ kết quả các nhánh; dùng kiểu tường minh khi muốn hợp đồng dữ liệu rõ ràng.

### 6.4. `null` và ranh giới phiên bản Java

Trong cú pháp Java 14 của các ví dụ `switch` trên `String` hoặc `enum`, nếu giá trị chọn nhánh là `null`, việc đánh giá `switch` ném `NullPointerException`; `default` không phải nhánh xử lý `null`. Hãy kiểm tra đầu vào trước khi `switch` nếu `null` là khả năng cần xử lý. Java 21 trở lên có cú pháp `case null` trong những trường hợp phù hợp; **không** dùng cú pháp đó cho mã cần biên dịch với `--release 14`.

### 6.5. Đặt đúng dấu câu và không nhầm với `switch` statement

- Trong `T value = switch (...) { ... };` và `return switch (...) { ... };`, cần dấu chấm phẩy sau dấu ngoặc đóng của toàn bộ biểu thức.
- Nhánh `case X -> expr;` có dấu chấm phẩy sau `expr`.
- Nhánh `case X -> { ... yield value; }` có dấu chấm phẩy sau `yield value`, không có dấu chấm phẩy bắt buộc ngay sau dấu `}` của riêng nhánh.
- `switch` **statement** dùng để thực thi lệnh, còn `switch` **expression** dùng ở vị trí cần giá trị. Việc cùng sử dụng từ khóa `switch` không làm hai dạng trở thành một.

## 7. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Thiếu giá trị ở một nhánh | Khối `-> { }` kết thúc mà chưa `yield` | Thêm `yield kếtQuả;` cho mọi đường đi kết thúc bình thường |
| Báo `switch expression does not cover all possible input values` | Thiếu `default` hoặc chưa liệt kê đủ trường hợp | Thêm quy tắc mặc định hoặc bao phủ đủ hằng `enum` |
| Dùng `return` ở bên trong khối nhánh | Nhầm trả về phương thức với trả về giá trị `switch` | Đổi sang `yield`, để `return` bao ngoài `switch` |
| Lỗi cú pháp sau `}` | Quên `;` của lệnh gán/`return` | Viết `};` ở cuối toàn bộ biểu thức |
| Lỗi kiểu dữ liệu | Một nhánh sinh giá trị không tương thích với kiểu đích | Thống nhất hợp đồng kiểu của các kết quả |
| Đầu vào `null` gây `NullPointerException` | Nhầm `default` xử lý cả `null` trong mã Java 14 | Kiểm tra `null` trước `switch` |
| Nhánh mong đợi chạy tiếp nhánh khác | Nhầm `case ... ->` với `case ...:` | Với `->`, chỉ nhánh khớp được thực thi; không có fall-through |

## 8. Bài tập áp dụng

Tạo phương thức `static int priorityScore(String status)` nhận một trong `"NEW"`, `"IN_PROGRESS"`, `"DONE"` và **trả trực tiếp** số `1`, `2`, `3` tương ứng. Với giá trị khác, ném `IllegalArgumentException`. Viết bằng đúng một `return switch`.

**Đáp án tham khảo (đặt trong lớp Java):**

~~~java
static int priorityScore(String status) {
    return switch (status) {
        case "NEW" -> 1;
        case "IN_PROGRESS" -> 2;
        case "DONE" -> 3;
        default -> throw new IllegalArgumentException("Status không hợp lệ: " + status);
    };
}
~~~

Có thể tự kiểm tra: `priorityScore("IN_PROGRESS")` trả `2`; `priorityScore("UNKNOWN")` ném `IllegalArgumentException`. Nếu API cho phép `null`, hãy bổ sung chính sách kiểm tra `null` trước biểu thức trên.

## 9. Ghi nhớ khi dùng trong mã thực tế

Dùng `variable = switch (...) { ... };` khi giá trị cần lưu để dùng tiếp; dùng `return switch (...) { ... };` khi kết quả là giá trị cuối cùng của phương thức. Ưu tiên `case ... ->` cho nhánh đơn giản, `yield` trong khối nhiều lệnh và `throw` cho trạng thái sai; bảo đảm đủ trường hợp, đúng kiểu và xử lý `null` theo hợp đồng đầu vào. Các quy tắc này là cú pháp Java 14 **chính thức**, vẫn còn được áp dụng trên các Java hiện hành.

**Nguồn chính thức để tra cứu thêm:**
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [Oracle Java SE 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions-and-statements.html)
- [Oracle Java SE 26 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html)
