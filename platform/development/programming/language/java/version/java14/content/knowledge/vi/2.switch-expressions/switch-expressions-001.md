# Phân biệt `switch` thực hiện hành động với `switch` tạo ra giá trị (Java 14+)

## 1. Hai cách dùng `switch` giải quyết hai nhu cầu khác nhau

Từ Java 14, `switch expression` đã là tính năng chính thức của ngôn ngữ. Trong Java hiện đại, cùng từ khóa `switch` có thể biểu diễn:

- **`switch statement` (câu lệnh):** chọn nhánh để **thực hiện hành động** như in log, gọi phương thức, cập nhật trạng thái hoặc ném ngoại lệ. Bản thân toàn bộ câu lệnh `switch` **không tạo ra giá trị** để gán hay trả về.
- **`switch expression` (biểu thức):** chọn nhánh và **tính ra một giá trị**. Giá trị đó có thể được gán cho biến, dùng làm giá trị `return` hoặc truyền thẳng vào lời gọi phương thức.

Điểm nhận biết nằm ở **cách sử dụng cả cấu trúc**, không nằm ở dấu `->`: **cả statement lẫn expression đều dùng được `case ... ->`**.

| Tiêu chí | `switch statement` | `switch expression` |
| --- | --- | --- |
| Mục đích chính | Thực thi một nhánh xử lý | Tính và cung cấp một kết quả |
| Kết quả của toàn `switch` | Không có giá trị | Có giá trị và kiểu dữ liệu |
| Vị trí sử dụng điển hình | Một câu lệnh độc lập trong thân phương thức | Bên phải phép gán, trong `return`, đối số phương thức |
| `case ... ->` | Thực thi statement expression, block hoặc `throw` | Cung cấp biểu thức giá trị, block có `yield` hoặc `throw` |
| Bao phủ các trường hợp | Với `switch` thông thường kiểu Java 14, có thể thiếu nhánh | Phải bao phủ mọi giá trị đầu vào hợp lệ, thường qua `default` hoặc đủ hằng số `enum` |
| Cách thoát / trả kết quả | Kiểu `case:` thường dùng `break`; kiểu `->` không cần `break` | Biểu thức sau `->` là kết quả; block dùng `yield`, không dùng `break` để trả kết quả |

**Phân biệt “có thay đổi biến” và “tạo ra giá trị”:** statement vẫn có thể gán vào một biến đã khai báo; đó là *tác dụng của các câu lệnh bên trong*, không phải giá trị của toàn bộ `switch`.

## 2. Ví dụ Java 14+ hoàn chỉnh: cùng đầu vào, hai ý định

Tạo tệp **`SwitchDemo.java`**:

```java
public class SwitchDemo {
    enum OrderStatus { NEW, PAID, CANCELLED }

    // Statement: chọn hành động cần thực hiện.
    static void performAction(OrderStatus status) {
        switch (status) {
            case NEW -> System.out.println("Yêu cầu thanh toán");
            case PAID -> System.out.println("Xử lý giao hàng");
            case CANCELLED -> System.out.println("Không xử lý tiếp");
        }
    }

    // Expression: chọn giá trị để trả về.
    static String toLabel(OrderStatus status) {
        return switch (status) {
            case NEW -> "Chờ thanh toán";
            case PAID -> "Đã thanh toán";
            case CANCELLED -> "Đã hủy";
        };
    }

    public static void main(String[] args) {
        performAction(OrderStatus.PAID);
        System.out.println(toLabel(OrderStatus.CANCELLED));
    }
}
```

Biên dịch và chạy với JDK 14 hoặc mới hơn:

```bash
javac -encoding UTF-8 SwitchDemo.java
java SwitchDemo
```

Kết quả chuẩn:

```text
Xử lý giao hàng
Đã hủy
```

Phân tích:

1. `performAction(...)` là phương thức `void`. `switch (status) { ... }` đứng độc lập như một **câu lệnh**; nhánh `PAID` gọi `println` và tạo tác dụng in ra màn hình. Ta **không thể** viết `String result = switchStatement;` vì statement không phải biểu thức.
2. `toLabel(...)` dùng `return switch (status) { ... };`. Mỗi nhánh `-> "..."` tạo một `String`, nên toàn `switch` là một **biểu thức String**; phương thức trả về chính giá trị đó.
3. Dấu `->` xuất hiện ở **cả hai phương thức**. Với dạng `->`, sau khi chạy nhánh khớp sẽ không tự chạy tiếp vào nhánh kế tiếp (*fall-through*).
4. Vì `OrderStatus` là `enum` và expression đã liệt kê đủ ba hằng số, expression không cần `default`. Nếu đổi đầu vào thành `String` với tập giá trị mở, thông thường phải có `default`.

## 3. So sánh trên cùng một nghiệp vụ tính phí

Giả sử `delivery` nhận `"STANDARD"`, `"EXPRESS"` hoặc `"PICKUP"`.

### Dùng statement khi muốn điều khiển thao tác gán

Đây là **đoạn minh họa đặt trong thân phương thức** (biến `delivery` đã được khai báo):

```java
int fee;
switch (delivery) {
    case "STANDARD" -> fee = 15;
    case "EXPRESS" -> fee = 35;
    case "PICKUP" -> fee = 0;
    default -> throw new IllegalArgumentException(
            "Loại giao hàng không hợp lệ: " + delivery);
}
System.out.println(fee);
```

`switch` ở đây là statement: từng nhánh thực thi **phép gán** `fee = ...`. Kết quả cuối cùng được lấy từ biến `fee` ở ngoài, chứ không phải từ bản thân `switch`.

### Dùng expression khi mục tiêu là lấy một giá trị

```java
int fee = switch (delivery) {
    case "STANDARD" -> 15;
    case "EXPRESS" -> 35;
    case "PICKUP" -> 0;
    default -> throw new IllegalArgumentException(
            "Loại giao hàng không hợp lệ: " + delivery);
};
System.out.println(fee);
```

Ở đây, toàn `switch (...) { ... }` là biểu thức ở **bên phải dấu `=`**. Mỗi nhánh hợp lệ cung cấp một `int` trực tiếp. Cách này bỏ biến trung gian được gán ở nhiều chỗ và giúp người đọc nhận ra mục đích là **chuyển một đầu vào thành kết quả**.

Với các giá trị đầu vào đã định nghĩa, hai đoạn tính cùng mức phí. Tuy nhiên, statement có thể phù hợp hơn khi mỗi nhánh cần gọi tác vụ khác nhau và không có kết quả duy nhất cần trả ra.

## 4. Phân biệt chính xác `->`, `yield`, `break` và `return`

### `->` không tự biến statement thành expression

`case PAID -> System.out.println("...");` có thể nằm trong statement vì một lời gọi phương thức là *statement expression* hợp lệ. Trong expression, `case PAID -> "Đã thanh toán";` cung cấp giá trị `String`.

Ngược lại, đoạn sau **không hợp lệ** nếu viết như một `switch statement` độc lập:

```java
// Sai khi đây là switch statement: chuỗi đơn lẻ không phải câu lệnh hợp lệ.
switch (status) {
    case NEW -> "Mới";
    default -> "Khác";
}
```

Muốn lấy chuỗi, hãy đặt `switch` trong ngữ cảnh biểu thức, chẳng hạn `String label = switch (status) { ... };`.

### Khi một nhánh expression cần nhiều câu lệnh, dùng `yield`

Ví dụ phương thức minh họa sau tính phí dựa trên loại giao hàng và cuối tuần:

```java
static int calculateFee(String delivery, boolean weekend) {
    return switch (delivery) {
        case "STANDARD" -> 15;
        case "EXPRESS" -> {
            int surcharge = weekend ? 10 : 0;
            yield 35 + surcharge;
        }
        case "PICKUP" -> 0;
        default -> throw new IllegalArgumentException(
                "Loại giao hàng không hợp lệ: " + delivery);
    };
}
```

- Với `case "STANDARD" -> 15;`, biểu thức `15` đã là kết quả; **không** cần `yield`.
- Với `case "EXPRESS" -> { ... }`, dấu ngoặc nhọn tạo **block** chứa nhiều câu lệnh. `yield 35 + surcharge;` trao giá trị cho **switch expression đang bao quanh**, không trả về trực tiếp từ phương thức `calculateFee`.
- `throw` là nhánh kết thúc bằng ngoại lệ, nên không cần `yield` hay giá trị thông thường.

Cú pháp `case:` vẫn được Java hỗ trợ trong **switch expression**; ở dạng đó, `yield` đưa ra giá trị:

```java
// Đoạn minh họa trong ngữ cảnh đã có biến status kiểu OrderStatus.
String label = switch (status) {
    case NEW:
        yield "Chờ thanh toán";
    case PAID:
        yield "Đã thanh toán";
    case CANCELLED:
        yield "Đã hủy";
};
```

`break;` có vai trò thoát khỏi switch statement kiểu `case:`; **`break;` không thay cho `yield value;`** trong switch expression. Với block của switch expression, mọi đường đi hợp lệ phải tạo giá trị hoặc ném ngoại lệ; block chỉ in log rồi kết thúc sẽ không biên dịch.

`return` trả kết quả từ **phương thức**. Khi viết `return switch (...) { ... };`, thứ tự là: `switch expression` tính ra giá trị, rồi `return` trả giá trị đó khỏi phương thức.

## 5. Tính đầy đủ nhánh, kiểu kết quả và các giới hạn quan trọng

**Exhaustiveness (bao phủ mọi trường hợp):** switch expression phải có nhánh cho mọi giá trị khả dĩ của biểu thức đầu vào. Với `int` hay `String` theo cú pháp Java 14, thường cần `default`. Với `enum`, có thể bỏ `default` nếu đã liệt kê đủ các hằng số. Nếu thiếu nhánh trong một expression, trình biên dịch báo lỗi thay vì cho phép expression kết thúc mà không có giá trị.

Một switch statement thông thường trong Java 14 có thể bỏ sót trường hợp và khi đó không chạy nhánh nào. Đây là lý do nên chủ động xử lý `default` hoặc bảo đảm trường hợp của nghiệp vụ đã được bao phủ, ngay cả khi trình biên dịch không bắt buộc. **Lưu ý về Java mới hơn:** statement dùng pattern matching hoặc `case null` có thể phải đáp ứng quy tắc exhaustiveness bổ sung; đừng hiểu rằng *mọi* switch statement ở *mọi* phiên bản đều được phép thiếu nhánh.

**Kiểu kết quả:** các nhánh expression phải tạo ra những kết quả tương thích với kiểu mà ngữ cảnh yêu cầu. Ví dụ, `int fee = switch (...) { ... };` không thể có một nhánh trả `"miễn phí"` kiểu `String` trong khi những nhánh khác trả số nguyên mà không chuyển đổi phù hợp.

**`null`:** trong Java 14, nếu selector là kiểu tham chiếu như `String` hay `enum` và nhận `null`, `switch` sẽ ném `NullPointerException`; `default` không tự xử lý trường hợp `null`. Hãy kiểm tra đầu vào trước khi dùng `switch` nếu `null` có thể xuất hiện. Java 21 trở lên có hỗ trợ cú pháp `case null` phù hợp, nhưng sự khác biệt giữa statement và expression vẫn giữ nguyên.

**Side effect:** switch expression **vẫn có thể** gọi phương thức hoặc ghi log bên trong block. Tên “expression” chỉ khẳng định toàn `switch` tạo giá trị, không khẳng định các nhánh là hàm thuần không có tác dụng phụ.

## 6. Các lỗi thường gặp và cách tránh

| Lỗi | Vì sao sai / nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Nhìn thấy `->` và kết luận đó là switch expression | `->` được dùng cho cả statement và expression | Xem toàn `switch` đang đứng độc lập hay đang được gán, trả về hoặc truyền làm đối số |
| Dùng `break;` để “trả kết quả” trong expression | `break` không mang giá trị của switch expression | Dùng biểu thức sau `->` hoặc `yield value;` trong block |
| Nhánh expression có block nhưng chỉ thực hiện hành động | Block có thể hoàn tất mà không cung cấp kết quả | Thêm `yield` cho đường đi cần trả giá trị hoặc `throw` cho nhánh lỗi |
| Thiếu `default` với expression xử lý `String` | Không bảo đảm tất cả giá trị đều được xét | Thêm `default` có ý nghĩa nghiệp vụ hoặc ném ngoại lệ |
| Trộn kết quả không tương thích kiểu | Không thể suy ra/ép về kiểu biểu thức cần thiết | Chọn một kiểu trả kết quả nhất quán hoặc chuyển đổi rõ ràng |
| Cho rằng `default` bắt được `null` ở Java 14 | `null` có quy tắc riêng và gây `NullPointerException` | Kiểm tra `null` trước, hoặc dùng cú pháp được hỗ trợ ở phiên bản Java mới |
| Quên `break` trong statement kiểu `case:` | Có thể xảy ra *fall-through* ngoài ý muốn | Ưu tiên `case ... ->` khi không cố ý cần fall-through |

Các nhánh kiểu `case:` là cú pháp Java vẫn hỗ trợ và có thể gặp trong mã đang được bảo trì. Để tránh lỗi rơi xuống nhánh khác khi viết mã mới, thường nên dùng `case ... ->`, rồi chọn **statement hay expression** theo mục đích thực sự.

## 7. Quy tắc chọn nhanh khi thiết kế mã

- **Câu hỏi là “Cần làm gì khi trạng thái này xảy ra?”** → Ưu tiên **switch statement**. Ví dụ: gửi thông báo, ghi log, gọi tác vụ tương ứng.
- **Câu hỏi là “Với đầu vào này, kết quả là gì?”** → Ưu tiên **switch expression**. Ví dụ: ánh xạ trạng thái sang nhãn, tính phí, xác định chiến lược hoặc trả mã phân loại.
- **Cần xử lý nhiều câu lệnh trước khi sinh kết quả?** → Vẫn có thể dùng **switch expression** với block và `yield`.
- **Không có giá trị kết quả thống nhất?** → Statement thường rõ hơn; đừng ép các nhánh tạo ra giá trị giả chỉ để dùng expression.

**Tự kiểm tra:** (1) `switch` trong `performAction` ở ví dụ chính là statement dù có `->`; (2) `switch` trong `toLabel` là expression vì toàn cấu trúc trở thành giá trị được `return`; (3) nếu một nhánh expression phải tính phụ phí trước khi trả số, dùng block và `yield`. Nắm đúng ba điểm này sẽ giúp lựa chọn cú pháp theo ý định của đoạn mã, thay vì đoán từ hình dạng các `case`.

### Tham khảo chính thức

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): tính năng được chuẩn hóa từ Java 14.
- [Oracle Java Language Updates — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/25/language/switch-expressions-statements.html): cú pháp statement/expression, `yield`, exhaustiveness và các quy tắc tiếp tục áp dụng trong Java hiện đại.
