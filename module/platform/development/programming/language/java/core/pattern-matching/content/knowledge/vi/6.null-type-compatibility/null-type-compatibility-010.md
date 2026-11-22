# Thiết kế nhánh xử lý null rõ ràng trong Java Pattern Matching

## 1. Vì sao phải thiết kế riêng nhánh null?

Trong ứng dụng Java, một biến kiểu tham chiếu có thể chứa đối tượng hoặc giá trị `null`. Khi dùng pattern matching để phân nhánh, câu hỏi không chỉ là “đối tượng thuộc kiểu nào?” mà còn là **“nếu không có đối tượng thì chương trình phải làm gì?”**. Nếu không thiết kế nhánh `null` ngay từ đầu, cùng một đầu vào có thể bị hiểu nhầm thành “kiểu chưa hỗ trợ”, làm lẫn lộn lỗi dữ liệu và trường hợp không có dữ liệu, hoặc gây `NullPointerException` ngoài dự kiến.

Ví dụ, với yêu cầu hiển thị một thông điệp:

- `null` có thể nghĩa là chưa nhận được thông điệp;
- `""` hoặc `"   "` là thông điệp kiểu chuỗi nhưng rỗng về nội dung;
- một số nguyên là dữ liệu có thật, chỉ thuộc kiểu khác;
- đối tượng thuộc kiểu không hỗ trợ cũng là dữ liệu có thật.

Bốn trạng thái này **không đồng nghĩa**. Việc gom tất cả vào `default` hoặc cùng một `else` có thể khiến nghiệp vụ khó kiểm tra và báo lỗi sai.

**Mục tiêu của bài:** xác định hợp đồng `null` ở ranh giới vào/ra, tạo nhánh riêng cho `null` trong `if/else` và `switch`, sắp xếp nhánh có guard an toàn, xử lý `null` bên trong `record`, và kiểm thử đầy đủ các đường đi.

## 2. Cơ sở Java: pattern có và không khớp null

Hai trường hợp quan trọng có quy tắc khác nhau:

| Tình huống | Hành vi | Hàm ý khi thiết kế |
| --- | --- | --- |
| `value instanceof String text` | Với `value == null`, kết quả là `false`; biến `text` không được ràng buộc | Cần nhánh kiểm tra `null` riêng nếu muốn phân biệt “không có giá trị” với “không phải String” |
| `switch (value)` theo pattern trên Java 21 | Có thể khai báo `case null` để xử lý `null` trực tiếp | Nên tách `case null` khi `null` là đầu vào được phép |
| `switch` thiếu nhánh `case null` | Với đầu vào `null`, thường ném `NullPointerException` trước khi vào nhánh thông thường, kể cả khi có `default` | `default` không phải nhánh dự phòng cho `null` |
| `case String text` | Biến `text` của mẫu kiểu chỉ dùng khi mẫu kiểu khớp; nhánh này không thay thế `case null` | Có thể gọi các phương thức của `text` trong guard với điều kiện mẫu đã khớp |
| Một đối tượng `record` có component `null` | Bản thân đối tượng `record` vẫn có thể khác `null` trong khi một component bên trong là `null` | Cần xem xét **hai tầng thiếu dữ liệu**: đối tượng ngoài và trường bên trong |

Đừng suy luận từ quy tắc `instanceof` rằng mọi `switch` đều tự bỏ qua `null`. Cũng không nên suy luận rằng `case null` làm các component của đối tượng trở thành không-null. Các trường hợp này phải có hợp đồng và kiểm thử riêng.

**Mốc phiên bản:** `instanceof` type pattern chính thức từ Java 16 (dùng ổn định ở Java 17); pattern matching cho `switch`, `case null` cùng các mẫu kiểu/guard trong bài sử dụng cú pháp chính thức Java 21. Với dự án `--release 17`, xử lý `null` trước `switch` và dùng `if`/`instanceof`; không sao chép các `case` của Java 21 vào Java 17.

## 3. Quyết định ý nghĩa của null trước khi viết mã

Một nhánh xử lý `null` rõ ràng trả lời ba câu hỏi:

1. **Đầu vào có được phép `null` không?** Nếu có, hành vi dự kiến là gì? Nếu không, kiểm tra tại ranh giới và báo lỗi nhất quán.
2. **Giá trị `null` đại diện cho trạng thái nào?** Ví dụ chưa cung cấp, không tìm thấy, bỏ chọn, hoặc lỗi lập trình. Đừng mặc định tất cả cùng nghĩa.
3. **Kết quả cần phân biệt với điều gì?** Có cần tách `null` với chuỗi rỗng, đối tượng kiểu khác, trạng thái dữ liệu không hợp lệ và lỗi trong hệ thống không?

Một bảng thiết kế nhỏ giúp tránh bỏ sót:

| Đầu vào ví dụ | Trạng thái | Cách xử lý gợi ý |
| --- | --- | --- |
| `null` | Không có đối tượng đầu vào | Trả kết quả `MISSING` hoặc từ chối ở ranh giới, tùy hợp đồng |
| `""` / `"   "` | Có chuỗi nhưng thiếu nội dung | Trả `EMPTY_TEXT` hoặc lỗi dữ liệu rỗng |
| `"Java"` | Chuỗi hợp lệ | Xử lý nội dung |
| `42` | Số nguyên hợp lệ | Xử lý như số nguyên nếu được hỗ trợ |
| `2.5` trong API chỉ hỗ trợ `String`/`Integer` | Kiểu chưa hỗ trợ | Trả `UNSUPPORTED` hoặc lỗi kiểu dữ liệu |

Trong một API thực, nên chọn cách biểu diễn kết quả gắn với miền nghiệp vụ (enum, kiểu kết quả hoặc exception có chủ đích), không nhất thiết dùng chuỗi như trong ví dụ học tập. Điều quyết định là **mỗi nhánh có ý nghĩa duy nhất**.

## 4. Mẫu đơn giản nhất trên Java 17: kiểm tra null trước instanceof

Khi cần phân loại `Object` theo kiểu, hãy đặt nhánh `null` rõ nghĩa **trước** các nhánh type pattern.

```java
public class ExplicitNullIf17 {

    static String route(Object input) {
        if (input == null) {
            return "MISSING";
        }

        if (input instanceof String text) {
            if (text.isBlank()) {
                return "EMPTY_TEXT";
            }
            return "TEXT: " + text.strip();
        }

        if (input instanceof Integer number) {
            return "INT: " + number;
        }

        return "UNSUPPORTED";
    }

    public static void main(String[] args) {
        System.out.println(route(null));
        System.out.println(route(" "));
        System.out.println(route(" Java "));
        System.out.println(route(42));
        System.out.println(route(2.5));
    }
}
```

Lưu tệp thành `ExplicitNullIf17.java`, chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 ExplicitNullIf17.java
java ExplicitNullIf17
```

Kết quả chính xác:

```text
MISSING
EMPTY_TEXT
TEXT: Java
INT: 42
UNSUPPORTED
```

**Vì sao cách này an toàn và dễ hiểu?**

- Nhánh `input == null` có ý nghĩa riêng; không bị hòa vào “không khớp kiểu”.
- Sau nhánh thoát sớm, mọi đường đi tiếp theo đều có đầu vào khác `null`.
- Trong `input instanceof String text`, biến `text` chỉ tồn tại ở đường đi đã khớp kiểu. `text.isBlank()` an toàn vì `text` không thể là `null` trong mẫu kiểu này.
- `text.isBlank()` được kiểm tra trước khi xử lý chuỗi bình thường; chuỗi chứa khoảng trắng không bị hiển thị như chuỗi có nội dung.
- `return "UNSUPPORTED"` được dành cho đối tượng không thuộc kiểu hỗ trợ; nó không chứa ý nghĩa “thiếu đối tượng”.

Nếu bỏ nhánh đầu:

```java
static String routeWithoutNullBranch(Object input) {
    if (input instanceof String text) {
        return text;
    }
    return "UNSUPPORTED";
}
```

Hàm sẽ trả `UNSUPPORTED` với `null` vì `instanceof` không khớp. Điều này **không tự gây ngoại lệ**, nhưng chỉ hợp lý nếu hợp đồng chủ đích coi `null` và kiểu không hỗ trợ là cùng một trạng thái. Đa số tình huống cần chẩn đoán đầu vào sẽ rõ ràng hơn nếu tách.

### Có nên gọi phương thức trên đầu vào trước khi kiểm tra?

Không nên viết:

```java
// SAI về an toàn null khi input có thể null:
if (input.toString().isBlank()) {
    return "EMPTY_TEXT";
}
```

Khi `input` là `null`, lời gọi `toString()` ném `NullPointerException` trước khi bạn có cơ hội phân loại. Với kiểm tra loại chuỗi, dùng `instanceof String text` rồi mới gọi `text.isBlank()`; nếu hợp đồng nhận `null`, cân nhắc nhánh riêng đầu tiên.

## 5. Java 21: case null trong switch cần hiện rõ

Với cùng bài toán phân loại, Java 21 có thể dùng `switch` expression:

```java
static String route(Object input) {
    return switch (input) {
        case null -> "MISSING";
        case String text when text.isBlank() -> "EMPTY_TEXT";
        case String text -> "TEXT: " + text.strip();
        case Integer number -> "INT: " + number;
        default -> "UNSUPPORTED";
    };
}
```

Đây là **phương thức minh họa** đặt trong lớp, yêu cầu Java 21 trở lên.

**Cách đọc thứ tự nhánh:**

1. `case null` tách trường hợp không có đối tượng đầu vào.
2. `case String text when text.isBlank()` khớp chuỗi và chỉ chọn nhánh nếu chuỗi rỗng hoặc toàn khoảng trắng.
3. `case String text` xử lý những chuỗi còn lại. Nhánh tổng quát của `String` phải đặt sau nhánh có guard.
4. `case Integer number` xử lý số nguyên đóng gói.
5. `default` là những giá trị còn lại không khớp các loại trên.

`when` chỉ được đánh giá sau khi **type pattern đã khớp**. Vì vậy `text.isBlank()` ở đây không nhận một `String` null. Nếu dữ liệu có thể có null ở **bên trong** một đối tượng được pattern giữ lại, cần kiểm tra component riêng, như phần 7.

### Vì sao default không phải case null?

Xét mã sau:

```java
static String unsafe(Object value) {
    return switch (value) {
        case String s -> "TEXT";
        default -> "OTHER";
    };
}
```

Nếu gọi `unsafe(null)`, Java 21 ném `NullPointerException`; nó **không** trả `"OTHER"`. `default` phục vụ các giá trị không-null còn lại, không phải phương án thay thế cho `case null`. Muốn xử lý `null` thành giá trị kết quả, hãy đưa `case null` vào `switch` một cách có chủ đích.

Trong Java 17, nếu dùng `switch` truyền thống với selector kiểu tham chiếu có thể `null`, cũng cần tiền kiểm `null` ở ngoài; cú pháp pattern `case String s` và `case null` chính thức nêu ở đây thuộc Java 21.

## 6. Đặt default, null và guard theo đúng ý nghĩa

Một lỗi phổ biến là nghĩ việc có `default` nghĩa là đã “bao hết mọi thứ”. Hãy kiểm tra riêng ba vấn đề sau:

**Thứ nhất, null và kiểu khác nhau là hai trạng thái khác nhau.** Nếu dữ liệu thiếu phải được báo rõ, luôn viết nhánh `null` hoặc tiền kiểm tương đương.

**Thứ hai, guard không được dùng để che giấu dữ liệu không hợp lệ.** Ví dụ:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "MISSING";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT";
        default -> "UNSUPPORTED";
    };
}
```

Đoạn trên là phương thức minh họa Java 21. Hai nhánh `String` diễn tả hai tình huống khác nhau; `default` dành cho các kiểu chưa được hỗ trợ. Nếu nhánh tổng quát `case String s` được đưa lên trước guard, case guard ở sau bị che khuất (dominance) và trình biên dịch sẽ từ chối.

**Thứ ba, guard cần an toàn với trường dữ liệu nullable.** Một guard kiểu `obj.field().isBlank()` có thể gây lỗi khi `field()` trả `null`, dù bản thân `obj` khác `null`. Hãy kiểm tra trường nullable trước rồi mới gọi phương thức lên nó.

Không cần ép mọi `switch` có `default` bằng mọi giá. Với một hệ kiểu đóng dùng `sealed`, đôi khi lựa chọn tốt hơn là liệt kê đủ các biến thể để trình biên dịch kiểm tra tính đầy đủ. Nhánh `null` vẫn độc lập với việc đó.

## 7. Hai tầng null: đối tượng ngoài và dữ liệu bên trong record

Giả sử một yêu cầu có các biến thể:

- `Text(String value)` chứa nội dung văn bản; component `value` có thể `null` nếu đối tượng được tạo như vậy.
- `Count(int amount)` chứa số lượng.
- `Ping()` biểu thị một tín hiệu không mang dữ liệu.
- Bản thân giá trị `Request` cũng có thể `null`.

Cả `null` của `Request` và `null` bên trong `Text` đều phải được xử lý; chúng mô tả **hai trạng thái khác nhau**.

Ví dụ hoàn chỉnh Java 21:

```java
public class ExplicitNullSwitch21 {

    sealed interface Request permits Text, Count, Ping {}

    record Text(String value) implements Request {}
    record Count(int amount) implements Request {}
    record Ping() implements Request {}

    static String handle(Request request) {
        return switch (request) {
            case null -> "MISSING_REQUEST";

            case Text t when t.value() == null ->
                    "MISSING_TEXT";

            case Text t when t.value().isBlank() ->
                    "EMPTY_TEXT";

            case Text t ->
                    "TEXT: " + t.value().strip();

            case Count c ->
                    "COUNT: " + c.amount();

            case Ping p ->
                    "PING";
        };
    }

    public static void main(String[] args) {
        System.out.println(handle(null));
        System.out.println(handle(new Text(null)));
        System.out.println(handle(new Text(" ")));
        System.out.println(handle(new Text(" Java ")));
        System.out.println(handle(new Count(7)));
        System.out.println(handle(new Ping()));
    }
}
```

Lưu tệp thành `ExplicitNullSwitch21.java` và chạy:

```bash
javac -encoding UTF-8 --release 21 ExplicitNullSwitch21.java
java ExplicitNullSwitch21
```

Kết quả chính xác:

```text
MISSING_REQUEST
MISSING_TEXT
EMPTY_TEXT
TEXT: Java
COUNT: 7
PING
```

**Phân tích quan trọng:**

- `case null` nhận tình huống biến `request` không trỏ tới đối tượng.
- `case Text t` chỉ khớp một đối tượng `Text`; nhưng **không tự đảm bảo** `t.value()` khác `null`.
- Guard đầu `t.value() == null` xử lý component thiếu. Nhờ đó, nhánh tiếp theo mới gọi `t.value().isBlank()` khi giá trị đã khác `null`; nếu guard đầu không được chọn, `t.value()` của cùng đối tượng `Text` trong ví dụ này khác `null`.
- `case Text t` không kèm guard ở cuối xử lý phần còn lại của biến thể `Text`.
- Mọi kiểu con được phép của `Request` (`Text`, `Count`, `Ping`) đều có nhánh bao quát; với `sealed`, trình biên dịch có thể kiểm tra tính đầy đủ mà không cần `default`. Nhánh `case null` cung cấp xử lý riêng cho tham chiếu ngoài bằng `null`.

Mô hình ví dụ dùng `record` để cho phép nhìn rõ các trường hợp. Trong hệ thống thực tế, nếu `Text.value` không được phép `null`, nên từ chối việc tạo `Text(null)` ngay trong constructor thay vì đưa nhánh `MISSING_TEXT` xuống mọi nơi sử dụng.

### Khi nào cần kiểm tra null bên trong pattern lồng?

Java 21 hỗ trợ record pattern để lấy trực tiếp component, ví dụ `Text(String value)`. Tuy nhiên, để diễn đạt **hợp đồng nullable** rõ ràng và tránh hiểu nhầm các quy tắc khớp pattern lồng nhau, ví dụ trên giữ `Text t` rồi kiểm tra `t.value()`. Điều này giúp người đọc phân biệt rõ null ở lớp ngoài với null ở dữ liệu bên trong.

Với record pattern lồng nhiều tầng, cần xét thêm khả năng một component tham chiếu là `null` và lựa chọn nhánh phù hợp theo quy tắc khớp của từng component type pattern. Không nên thay thế việc thiết kế null bằng giả định “pattern lồng tự kiểm tra hết mọi null”.

## 8. Khi nào chấp nhận null, khi nào từ chối?

Không phải mọi phương thức đều cần `case null`. Điều đúng tùy thuộc **hợp đồng đầu vào**.

### Lựa chọn A — Null là trạng thái hợp lệ

Ví dụ: người dùng chưa chọn mục nào. Phương thức nên có kết quả xác định:

```java
static String display(Object value) {
    if (value == null) {
        return "Chưa chọn";
    }
    if (value instanceof String text) {
        return text;
    }
    return "Không hỗ trợ";
}
```

Đây là phương thức minh họa Java 17. Trả một giá trị rành mạch khi `null` được chấp nhận là trường hợp nghiệp vụ.

### Lựa chọn B — Null vi phạm hợp đồng

Ví dụ: một phương thức xử lý đơn hàng yêu cầu tham số bắt buộc. Thay vì trả kết quả mơ hồ hoặc cố phân nhánh trong nhiều lớp, kiểm tra ngay khi nhận:

```java
import java.util.Objects;

public class RequiredInput {
    static String normalize(String text) {
        Objects.requireNonNull(text, "text is required");
        return text.strip();
    }
}
```

Đoạn trên biên dịch với Java 17. `Objects.requireNonNull` ném `NullPointerException` với thông điệp đã chọn khi nhận `null`. Đây là hành vi **có chủ đích ở ranh giới hợp đồng**, khác với việc vô tình gọi `text.strip()` trên `null`.

Nếu muốn dùng `IllegalArgumentException` hoặc đối tượng lỗi nghiệp vụ thay thế, hãy xác định quy ước nhất quán của ứng dụng; đừng trộn lẫn các loại lỗi theo từng nhánh mà không có lý do.

### Lựa chọn C — Null có thể xuất hiện nhưng trả về kiểu biểu diễn khác

Ví dụ phương thức tra cứu có thể không tìm thấy bản ghi. API có thể cân nhắc `Optional<T>` cho kết quả có/không ở nơi thích hợp. `Optional` không làm dữ liệu từ hệ thống bên ngoài tự nhiên hết `null`; bạn vẫn phải chuyển đổi tại ranh giới và xem xét các trường hợp dữ liệu rỗng/hỏng riêng.

Việc thay mọi tham chiếu bằng `Optional` cũng không phải mục tiêu. Điều cần nhất quán là người gọi **biết trước** khi nào kết quả có thể thiếu và phải xử lý ra sao.

## 9. Những mẫu điều kiện dễ gây lỗi

### Lỗi 1 — Kiểm tra null sau khi dereference

```java
// SAI: đã gọi phương thức trước khi kiểm tra.
if (name.isBlank() || name == null) {
    System.out.println("missing");
}
```

Với `name == null`, lời gọi `isBlank()` ném `NullPointerException` trước khi vế phải chạy. Đổi thứ tự:

```java
if (name == null || name.isBlank()) {
    System.out.println("missing");
}
```

Đây là cách **an toàn về null** nhờ `||` chỉ tính vế phải khi cần, nhưng nó **gộp** null và chuỗi rỗng vào một trạng thái. Chỉ dùng kiểu gộp này nếu nghiệp vụ thực sự coi hai trường hợp tương đương.

### Lỗi 2 — Coi instanceof không khớp nghĩa là null

```java
if (value instanceof String s) {
    return "STRING";
}
return "MISSING"; // Sai ý nghĩa nếu value là Integer hay đối tượng khác.
```

Đây là đoạn phương thức minh họa. Mẫu `String` có thể không khớp vì `null` **hoặc** vì loại khác. Cần kiểm tra `value == null` riêng nếu `MISSING` chỉ được dành cho null.

### Lỗi 3 — Giả định default trong switch nhận null

```java
// Java 21: nếu value == null, switch vẫn ném NPE.
return switch (value) {
    case String s -> "STRING";
    default -> "OTHER";
};
```

Đây là biểu thức minh họa bên trong phương thức. Thêm `case null -> "MISSING";` nếu `null` được phép và cần xử lý.

### Lỗi 4 — Truy cập component nullable trong guard

```java
// Nguy hiểm nếu t.value() có thể null:
case Text t when t.value().isBlank() -> "EMPTY"
```

Đây là **một case minh họa** (không phải chương trình độc lập). Giải pháp là kiểm tra `t.value() == null` trước, hoặc thiết kế `Text` không chấp nhận component null.

### Lỗi 5 — Gộp null, chuỗi trắng và kiểu chưa hỗ trợ

Dùng cùng một nhánh `"UNKNOWN"` khiến việc truy vết khó khăn: không biết đầu vào thiếu, dữ liệu hợp lệ nhưng không đủ nội dung, hay nhà phát triển chưa bổ sung trường hợp mới. Chỉ gộp nếu hợp đồng nghiệp vụ thực sự có một kết quả chung; nếu không, dùng kết quả hoặc loại lỗi riêng.

### Lỗi 6 — Đưa trường hợp null ra ngoài rồi quên đường đi lỗi

Một nhánh như `if (value == null) return "";` có thể ngăn NPE nhưng để người gọi hiểu `""` là dữ liệu rỗng hợp lệ. Hãy thiết kế giá trị trả về thể hiện đúng trạng thái, thêm kiểm thử và tài liệu API.

## 10. Quy trình thiết kế nhánh null trong một phương thức

Một cách làm thực dụng trước khi viết `if` hoặc `switch`:

1. **Liệt kê những trạng thái đầu vào.** Bắt đầu bằng `null` của giá trị ngoài, sau đó các loại đối tượng hỗ trợ, cuối cùng các kiểu chưa hỗ trợ.
2. **Xác định null có hợp lệ không.** Nếu không hợp lệ, từ chối ở đầu hàm/boundary. Nếu hợp lệ, đặt nhánh xử lý riêng với kết quả rõ nghĩa.
3. **Tách điều kiện kiểu và điều kiện dữ liệu.** `instanceof String s` giải quyết kiểu; `s.isBlank()` giải quyết trạng thái nội dung. Với dữ liệu lồng, kiểm tra tính nullable của component trước khi dùng phương thức của nó.
4. **Sắp xếp nhánh cụ thể trước nhánh tổng quát.** Trong `switch`, case có guard phải trước case tổng quát cùng kiểu nếu cả hai cùng áp dụng.
5. **Xem xét tính đầy đủ.** Với kiểu mở như `Object`, cần chính sách cho kiểu chưa hỗ trợ; với `sealed`, có thể tận dụng kiểm tra exhaustiveness của trình biên dịch.
6. **Kiểm thử từng trạng thái riêng.** Tối thiểu có null ngoài, null component nếu được phép, giá trị rỗng, giá trị hợp lệ và kiểu khác/hay biến thể khác.

Sau khi viết, thử đọc mã từ trên xuống như một bảng quyết định: với từng đầu vào, có đúng một đường đi dự kiến hay không? Có chỗ nào dereference trước khi bảo đảm khác null không? Có nhánh `default` hoặc `else` đang nhận hai ý nghĩa không liên quan không?

## 11. Bộ ca kiểm thử tối thiểu

Với `ExplicitNullIf17` và `ExplicitNullSwitch21` ở trên, có thể dùng bảng sau làm hợp đồng kiểm thử:

| Ca | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Java 17 — thiếu đầu vào | `route(null)` | `MISSING` |
| Java 17 — chuỗi chỉ có khoảng trắng | `route(" ")` | `EMPTY_TEXT` |
| Java 17 — chuỗi hợp lệ có khoảng trắng đầu/cuối | `route(" Java ")` | `TEXT: Java` |
| Java 17 — số nguyên | `route(42)` | `INT: 42` |
| Java 17 — số thực không được hỗ trợ | `route(2.5)` | `UNSUPPORTED` |
| Java 21 — null của cả request | `handle(null)` | `MISSING_REQUEST` |
| Java 21 — request có component null | `handle(new Text(null))` | `MISSING_TEXT` |
| Java 21 — component chỉ có khoảng trắng | `handle(new Text(" "))` | `EMPTY_TEXT` |
| Java 21 — component văn bản hợp lệ | `handle(new Text(" Java "))` | `TEXT: Java` |
| Java 21 — biến thể Count | `handle(new Count(7))` | `COUNT: 7` |
| Java 21 — biến thể Ping | `handle(new Ping())` | `PING` |

Ngoài ca chạy thành công, kiểm tra thay đổi thiết kế:

- Nếu thêm kiểu con mới vào `permits` mà chưa bổ sung nhánh bao quát trong `switch` không có `default`, trình biên dịch có thể báo `switch` expression chưa exhaustive. Đây là tín hiệu tốt để cập nhật logic.
- Nếu bỏ `case Text t when t.value() == null`, ca `new Text(null)` có thể gây NPE ở nhánh kiểm tra `isBlank()`. Điều đó cho thấy **null của component** cần được xử lý rõ.
- Nếu bỏ `case null` khỏi `switch` của `Request` mà vẫn gọi `handle(null)`, chương trình không còn hành vi `MISSING_REQUEST` như mong đợi.

Cần phân biệt **kiểm thử kết quả nghiệp vụ** với **kiểm thử lỗi lập trình**: nếu hợp đồng cấm `null`, bài kiểm thử nên xác nhận phương thức từ chối đầu vào theo lỗi đã quy định; không nên bắt lỗi rồi im lặng trả dữ liệu giả.

## 12. Bài tập tự luyện

**Bài 1 — Phân loại đầu vào Java 17.** Viết hàm `summarize(Object input)`, hỗ trợ `String` và `Integer`. Yêu cầu: null trả `"NO_INPUT"`, chuỗi trắng trả `"BLANK"`, chuỗi thường trả nội dung đã `strip()`, số nguyên trả dạng `"NUMBER: n"`, các kiểu khác trả `"UNSUPPORTED_TYPE"`. Dùng `instanceof` pattern, không ép kiểu thủ công.

**Bài 2 — Chuyển sang switch Java 21.** Chuyển cùng hàm thành `switch` expression với `case null`, hai case `String` (một case có guard), `Integer` và `default`. Thử đổi thứ tự hai case `String` rồi quan sát lỗi dominance.

**Bài 3 — Null bên ngoài và null bên trong record.** Tạo `sealed interface Command permits Write, Read`; `record Write(String text) implements Command` và `record Read(int id) implements Command`. Quy định riêng cho `null` của `Command`, `Write(null)`, `Write("")`, `Read(1)`. Viết `switch` expression và kiểm thử đủ bốn đường đi; chỉ gọi `isBlank()` khi biết component khác null.

**Bài 4 — Thiết kế lại hợp đồng.** Ở bài 3, đổi quy tắc để `Write.text` **không bao giờ được null**. Thực hiện kiểm tra trong compact constructor bằng `Objects.requireNonNull(text, "text")`. Suy nghĩ nhánh `MISSING_TEXT` còn cần thiết không; phân biệt lỗi tạo đối tượng với trường hợp “không có command”.

**Bài 5 — Đánh giá chất lượng mã.** Chọn một đoạn mã thực tế có `default` trả `"Unknown"`. Liệt kê các trạng thái đang bị gom chung, thiết kế tên kết quả rõ nghĩa và viết các trường hợp kiểm thử tương ứng. Giải thích khi nào giữ một nhánh chung là quyết định hợp lý.

## 13. Tự kiểm tra kiến thức

1. Vì sao `input instanceof String text` là `false` khi đầu vào `null`, và vì sao điều đó không có nghĩa `else` chỉ nhận `null`?
2. Trong `switch` expression Java 21, `default` có nhận một selector `null` khi không có `case null` không?
3. Tại sao `case String s when s.isBlank()` an toàn với null ở cấp đầu vào, trong khi `case Text t when t.value().isBlank()` có thể không an toàn?
4. `null` của cả `Text` khác `null` của `Text.value` như thế nào về ý nghĩa?
5. Khi nào nên trả giá trị `MISSING`, và khi nào nên từ chối ngay bằng `Objects.requireNonNull`?
6. Vì sao một `switch` exhaustive trên tập kiểu `sealed` vẫn cần quyết định xử lý selector `null`?
7. Bộ kiểm thử của bạn có tách được dữ liệu thiếu, rỗng, hợp lệ và kiểu không được hỗ trợ không?

Nếu trả lời được các câu này và giải thích chính xác từng dòng kết quả của hai chương trình, bạn đã có nền tảng để thiết kế nhánh xử lý `null` rõ ràng trong mã Java dùng pattern matching.

## 14. Tài liệu chính thức để đọc thêm

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): điều kiện khớp type pattern và phạm vi biến trong `instanceof`.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): `case null`, guard, dominance, tính đầy đủ và cách xử lý selector null.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record pattern, component và các quy tắc khớp.
- [Java Language Specification, Java SE 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): quy tắc `switch` statement và các trường hợp liên quan.
- [Java Language Specification, Java SE 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): `switch` expression và yêu cầu tính đầy đủ.
- [Java SE 21 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): kiểm tra tham số bắt buộc.

Áp dụng theo **phiên bản Java mà mã nguồn thực sự được biên dịch**. Với Java 17, bắt đầu từ tiền kiểm `null` và `instanceof`; với Java 21, tận dụng `case null` trong `switch` khi hợp đồng cho phép đầu vào thiếu.
