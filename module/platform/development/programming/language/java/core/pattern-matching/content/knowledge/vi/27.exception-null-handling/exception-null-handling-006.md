# Không che giấu lỗi bằng default

## 1. Vấn đề: fallback hợp lệ khác với nuốt lỗi

Trong Java, một nhánh `default` của `switch` thường được hiểu là “các trường hợp còn lại”. Cách hiểu này chưa đủ khi kết hợp **pattern matching**, **exception** và **mô hình domain**: có những trường hợp còn lại là dữ liệu bình thường mà ứng dụng cần hỗ trợ; nhưng cũng có trường hợp còn lại biểu thị **lỗi thiết kế, dữ liệu không hợp lệ hoặc một subtype mới chưa được xử lý**.

Ví dụ dịch vụ trả về ba biến thể kết quả:

- `Ok`: đã hoàn tất thành công;
- `Rejected`: bị từ chối với lý do cụ thể;
- `Retry`: cần thử lại sau một khoảng thời gian.

Nếu một phép phân loại chỉ nhận `Ok` và `Rejected`, rồi đặt `default -> "Không xác định"`, thì mọi `Retry` có thể bị chuyển thành nhãn chung. Code vẫn chạy và hệ thống không biết rằng nó đã **bỏ qua trạng thái cần xử lý nghiệp vụ**.

**Mục tiêu của bài:** nhận diện khi nào `default` thực sự là phương án dự phòng có chủ đích, khi nào nó đang che lỗi; biết cách sử dụng `sealed interface`, pattern matching for `switch`, `case null` và exception để biểu diễn rõ hợp đồng xử lý. Không nên xóa mọi `default`: vấn đề nằm ở **ý nghĩa** của trường hợp còn lại.

## 2. Ví dụ điển hình: default âm thầm bỏ qua một subtype

Giả sử đã khai báo:

```java
sealed interface Result permits Ok, Rejected, Retry {}

record Ok(int receiptId) implements Result {}
record Rejected(String reason) implements Result {}
record Retry(int seconds) implements Result {}
```

Đây là các khai báo minh họa Java 21; phần sau có chương trình hoàn chỉnh để chạy.

Một cách viết dễ gây lỗi:

```java
static String describeUnsafe(Object value) {
    return switch (value) {
        case Ok ok -> "Thành công #" + ok.receiptId();
        case Rejected rejected -> "Từ chối: " + rejected.reason();
        default -> "Không xác định";
    };
}
```

Nếu gọi `describeUnsafe(new Retry(3))`, kết quả là `"Không xác định"`, mặc dù `Retry` là một biến thể **được định nghĩa rõ trong domain**. Trình biên dịch không buộc tác giả bổ sung case `Retry` vì `default` đã bao phủ mọi giá trị không `null` còn lại.

Điều nguy hiểm không nhất thiết nằm ở chuỗi `"Không xác định"`, mà ở hệ quả:

1. **Mất thông tin:** thời gian phải thử lại (3 giây) bị bỏ qua.
2. **Ẩn thay đổi mô hình:** một subtype mới có thể được thêm mà nơi phân loại vẫn biên dịch và trả về fallback cũ.
3. **Khó phát hiện qua giám sát:** một trạng thái nghiệp vụ quan trọng bị gộp với những kiểu thật sự không hỗ trợ.
4. **Test dễ bỏ sót:** chỉ kiểm thử `Ok` và `Rejected` có thể không phát hiện thiếu `Retry`.

Với `switch` trên `Object`, một `default` có thể hợp lý vì dữ liệu không thuộc các kiểu được hỗ trợ có thể xuất hiện. Nhưng ví dụ này lại dùng `default` **thay cho việc xử lý một subtype hợp lệ của chính Result**; đó là sai lầm thiết kế.

## 3. Dùng exhaustiveness để trình biên dịch nhắc thiếu nhánh

Khi domain là một tập biến thể được kiểm soát, `sealed interface` cho phép Java 21 kiểm tra tính **đầy đủ của `switch expression` (exhaustiveness)**.

Bản thiết kế xử lý các biến thể rõ ràng:

```java
static String describe(Result result) {
    return switch (result) {
        case Ok(int receiptId) ->
                "Thành công #" + receiptId;
        case Rejected rejected ->
                "Từ chối: " + rejected.reason();
        case Retry(int seconds) ->
                "Thử lại sau " + seconds + " giây";
        case null ->
                throw new IllegalArgumentException("Kết quả không được null");
    };
}
```

Các ý quan trọng:

- `Result` là `sealed interface` chỉ cho phép trực tiếp `Ok`, `Rejected` và `Retry`. Đây đều là record, mà record là `final`.
- `Ok(int receiptId)` và `Retry(int seconds)` là **record patterns**: khi khớp, component `int` được lấy ra làm biến.
- `case Rejected rejected` là **type pattern**: nó khớp mọi đối tượng `Rejected` không `null`, kể cả khi component `reason` bên trong bằng `null`. Muốn chặn `reason == null` cần kiểm tra riêng.
- Với các case trên, trình biên dịch biết mọi biến thể không `null` của `Result` đều đã có nhánh. Không cần `default`.
- `case null` xử lý selector `null` một cách tường minh bằng exception đúng chính sách đầu vào.

**Lợi ích khi thêm subtype:** Nếu người sở hữu domain thêm một subtype trực tiếp mới vào `permits`, các `switch expression` không có `default` mà trước đó đủ nhánh có thể bị compiler báo chưa exhaustive khi biên dịch lại. Đây là tín hiệu đáng giá: lập trình viên phải quyết định cách xử lý subtype mới, thay vì âm thầm chuyển nó sang một giá trị chung.

Giới hạn cần hiểu: kiểm tra exhaustiveness phản ánh **thông tin kiểu và các pattern** mà compiler có thể xác định. Nó không thay thế test nghiệp vụ, kiểm tra dữ liệu hoặc xử lý lỗi chạy thực tế. Trong môi trường nâng cấp module/binary không đồng bộ, một `switch` cũ từng được biên dịch đầy đủ vẫn có thể gặp loại mới lúc chạy và dẫn đến `MatchException`. Vì vậy, khi thay đổi hierarchy, cần kiểm thử và phát hành các module phụ thuộc đồng bộ.

## 4. Một lỗi khác: default che dữ liệu không hợp lệ bên trong subtype hợp lệ

Ngay cả khi đã xử lý đủ ba subtype, vẫn có thể có **dữ liệu sai trong component**.

Ví dụ `Retry(int seconds)` cho phép tạo `new Retry(0)` hoặc `new Retry(-5)` nếu record không có validation. Việc xử lý bằng một nhánh chung như:

```java
// Dễ làm mất ý nghĩa của seconds không hợp lệ:
case Retry retry -> "Trạng thái khác";
```

sẽ khiến dữ liệu lỗi đi qua như một tình huống bình thường.

Nếu nghiệp vụ yêu cầu `seconds > 0`, hãy diễn đạt điều kiện đó rõ:

```java
case Retry(int seconds) when seconds > 0 ->
        "Thử lại sau " + seconds + " giây";
case Retry retry ->
        throw new IllegalArgumentException(
                "Thời gian thử lại không hợp lệ: " + retry.seconds());
```

Ở đây:

1. Java chỉ đánh giá `when seconds > 0` sau khi record pattern `Retry(int seconds)` đã khớp.
2. Nhánh `Retry retry` không guard phải đứng **sau** nhánh cụ thể, để không bao phủ nhánh trước.
3. `Retry(0)` vẫn thuộc kiểu `Retry` nhưng bị từ chối bằng exception có nội dung rõ ràng.
4. Hai case cùng nhau xử lý mọi giá trị `Retry` không `null`, nên không cần một `default` mơ hồ.

**Không nhầm kiểm tra subtype với validation:** `sealed` kiểm soát loại đối tượng nào được phép tham gia hệ kiểu; `record pattern` kiểm tra cấu trúc và trích xuất component; còn `when` hoặc constructor mới kiểm tra những ràng buộc giá trị như `seconds > 0`. Nếu mọi `Retry` phải hợp lệ trong toàn bộ hệ thống, tốt hơn nên kiểm tra invariant ngay tại constructor/boundary để dữ liệu sai không được tạo ra.

## 5. Null không phải là “loại khác”

Trong pattern matching for `switch` của Java 21, **selector `null` là một trường hợp riêng**. Không nên mong `default` luôn hoạt động như `case null`.

Ví dụ:

```java
static String label(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        default -> "Khác";
    };
}
```

Với `label(null)`, chương trình có thể ném `NullPointerException` do không có nhánh `case null`, **không** trả về `"Khác"`. Một nhánh `default` không phải là chính sách xử lý null.

Nếu `null` được coi là lỗi đầu vào:

```java
case null -> throw new IllegalArgumentException("Thiếu dữ liệu");
```

Nếu `null` là trạng thái nghiệp vụ hợp lệ, chẳng hạn giao diện chưa chọn bộ lọc:

```java
case null -> "Chưa chọn";
```

Hai cách đều có thể đúng trong ngữ cảnh phù hợp. Sai lầm là để `null` bị xử lý ngẫu nhiên, sau đó dùng `default` hoặc `catch (Exception ...)` để biến mọi lỗi thành cùng một chuỗi.

**Với component bên trong record** cũng cần lưu ý:

```java
record Rejected(String reason) implements Result {}
```

Type pattern `case Rejected rejected` nhận mọi `Rejected` không-null, nhưng `rejected.reason()` vẫn có thể là `null`. Một thông báo `"Từ chối: " + rejected.reason()` có thể in `"Từ chối: null"`, từ đó gây hiểu nhầm rằng thông tin từ chối hợp lệ.

Cách chặt chẽ hơn là kiểm tra rõ yêu cầu:

```java
case Rejected rejected -> {
    String reason = rejected.reason();
    if (reason == null || reason.isBlank()) {
        throw new IllegalArgumentException(
                "Lý do từ chối không hợp lệ");
    }
    yield "Từ chối: " + reason;
}
```

Trong `switch expression`, khi một case dùng block và cần tạo giá trị, hãy dùng `yield`. Nếu dữ liệu không hợp lệ, `throw` là một lựa chọn tường minh. Không “làm sạch” mọi lỗi bằng một `default` rồi coi chúng là thành công.

## 6. Khi nào default là lựa chọn đúng?

Không phải `default` nào cũng che giấu lỗi.

### 6.1. Dữ liệu đầu vào thuộc tập mở

Nếu nhận `Object` từ một điểm tích hợp có thể gặp nhiều kiểu khác nhau, một fallback rõ chính sách có thể hợp lý:

```java
static String friendlyLabel(Object value) {
    return switch (value) {
        case String text -> "Chuỗi: " + text;
        case Integer number -> "Số: " + number;
        case null -> "Không có giá trị";
        default -> "Định dạng chưa được hỗ trợ";
    };
}
```

Ở đây, người viết **cố ý** cho phép mọi kiểu còn lại trở thành kết quả có nghĩa: “định dạng chưa được hỗ trợ”. Nếu chức năng chỉ hiển thị nhãn và không có tác vụ quan trọng nào bị bỏ qua, `default` có thể thích hợp.

Nhưng ở boundary yêu cầu dữ liệu phải là một trong vài kiểu được hỗ trợ để tiếp tục nghiệp vụ, tốt hơn nên từ chối rõ:

```java
static String requireSupported(Object value) {
    return switch (value) {
        case String text -> text;
        case Integer number -> number.toString();
        case null -> throw new IllegalArgumentException("Thiếu đầu vào");
        default -> throw new IllegalArgumentException(
                "Kiểu không hỗ trợ: " + value.getClass().getName());
    };
}
```

Nhánh `default` vẫn có mặt, nhưng **không nuốt lỗi**: nó tạo exception với dữ liệu chẩn đoán rõ ràng. Ở đây `value.getClass()` an toàn vì `null` đã có case riêng; các type pattern xử lý những trường hợp nhận diện được.

### 6.2. Trường hợp “không biết” thật sự là domain state

Nếu mô hình domain quy định sẵn trạng thái `Unknown` là một biến thể hợp lệ, nên biểu diễn nó bằng một subtype hoặc một kết quả tường minh, thay vì âm thầm đẩy mọi lỗi vào `default`. Ví dụ `sealed interface Status permits Active, Inactive, Unknown` giúp caller phân biệt **trạng thái được thiết kế là Unknown** với **lỗi dữ liệu hoặc subtype chưa được xử lý**.

### 6.3. Compatibility hoặc telemetry có chủ đích

Khi ứng dụng phải chấp nhận định dạng từ hệ thống cũ, việc phân loại input lạ vào một nhánh dự phòng có thể là một quyết định tương thích có chủ ý. Nhưng nên:

- Ghi nhận hoặc đo lường đúng sự kiện không hỗ trợ nếu cần giám sát.
- Tránh trả thành công giả cho thao tác mang tính giao dịch quan trọng.
- Ghi rõ chính sách trong API, log và test, nhất là trường hợp dễ bị nhầm giữa “chưa hỗ trợ” và “lỗi dữ liệu”.

## 7. Chương trình Java 21 chạy hoàn chỉnh

Tạo tệp **`DefaultMustNotHideErrorsDemo.java`**:

```java
public class DefaultMustNotHideErrorsDemo {
    sealed interface Result permits Ok, Rejected, Retry {}

    record Ok(int receiptId) implements Result {}
    record Rejected(String reason) implements Result {}
    record Retry(int seconds) implements Result {}

    // Anti-pattern minh họa: missing Retry bị nuốt bởi default.
    static String describeUnsafe(Object value) {
        return switch (value) {
            case Ok ok -> "Thành công #" + ok.receiptId();
            case Rejected rejected ->
                    "Từ chối: " + rejected.reason();
            default -> "Không xác định";
        };
    }

    // Xử lý đủ domain type và xác thực dữ liệu nội bộ.
    static String describeStrict(Result result) {
        return switch (result) {
            case Ok(int id) -> "Thành công #" + id;

            case Rejected rejected -> {
                String reason = rejected.reason();
                if (reason == null || reason.isBlank()) {
                    throw new IllegalArgumentException(
                            "Lý do từ chối không hợp lệ");
                }
                yield "Từ chối: " + reason;
            }

            case Retry(int seconds) when seconds > 0 ->
                    "Thử lại sau " + seconds + " giây";

            case Retry retry ->
                    throw new IllegalArgumentException(
                            "Thời gian thử lại không hợp lệ: "
                                    + retry.seconds());

            case null ->
                    throw new IllegalArgumentException(
                            "Kết quả không được null");
        };
    }

    // Boundary mở: từ chối giá trị ngoài Result rõ ràng.
    static String describeExternal(Object input) {
        if (input == null) {
            throw new IllegalArgumentException(
                    "Kết quả không được null");
        }
        if (!(input instanceof Result result)) {
            throw new IllegalArgumentException(
                    "Không phải Result: " + input.getClass().getName());
        }
        return describeStrict(result);
    }

    static void showFailure(
            String label,
            java.util.function.Supplier<String> action) {
        try {
            System.out.println(label + " -> " + action.get());
        } catch (IllegalArgumentException ex) {
            System.out.println(label
                    + " -> IllegalArgumentException: "
                    + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println(describeStrict(new Ok(12)));
        System.out.println(describeStrict(
                new Rejected("Thiếu chữ ký")));
        System.out.println(describeStrict(new Retry(3)));

        System.out.println("default âm thầm: "
                + describeUnsafe(new Retry(3)));

        showFailure("retry 0",
                () -> describeStrict(new Retry(0)));

        showFailure("lý do null",
                () -> describeStrict(new Rejected(null)));

        showFailure("selector null",
                () -> describeStrict(null));

        showFailure("kiểu không hỗ trợ",
                () -> describeExternal("lạ"));
    }
}
```

Biên dịch và chạy với **JDK 21 trở lên**, không cần bật preview:

```bash
javac -encoding UTF-8 DefaultMustNotHideErrorsDemo.java
java DefaultMustNotHideErrorsDemo
```

Kết quả:

```text
Thành công #12
Từ chối: Thiếu chữ ký
Thử lại sau 3 giây
default âm thầm: Không xác định
retry 0 -> IllegalArgumentException: Thời gian thử lại không hợp lệ: 0
lý do null -> IllegalArgumentException: Lý do từ chối không hợp lệ
selector null -> IllegalArgumentException: Kết quả không được null
kiểu không hỗ trợ -> IllegalArgumentException: Không phải Result: java.lang.String
```

Giải thích từng dòng:

1. `Ok(12)` khớp `Ok(int id)` và trả biên nhận thành công.
2. `Rejected("Thiếu chữ ký")` khớp `Rejected`, vượt qua validation và có thông báo cụ thể.
3. `Retry(3)` khớp record pattern có guard `seconds > 0`.
4. Cùng `Retry(3)` nhưng qua `describeUnsafe` sẽ lọt vào `default` và bị đổi thành `Không xác định`. Đây là minh họa trực tiếp việc che giấu một trạng thái domain.
5. `Retry(0)` có subtype hợp lệ nhưng giá trị không đạt quy tắc; nhánh `Retry retry` không guard ném `IllegalArgumentException`.
6. `Rejected(null)` vẫn khớp type pattern `Rejected rejected`; validation phát hiện reason null và ném exception.
7. `describeStrict(null)` chọn `case null` và ném exception có thông báo riêng.
8. Chuỗi `"lạ"` không thuộc `Result`. `describeExternal` từ chối bằng `IllegalArgumentException` kèm tên lớp runtime `java.lang.String`.

`showFailure` chỉ dùng để minh họa **các lỗi dự kiến** và in kết quả xác định. Trong sản phẩm thật, không nên bắt `IllegalArgumentException` trên mọi đường đi chỉ để đổi nó thành một chuỗi rồi coi giao dịch thành công. Tầng giao diện hoặc boundary có thể bắt lỗi để trả thông báo thích hợp, nhưng tầng nghiệp vụ vẫn cần giữ trạng thái lỗi rõ ràng.

## 8. Đừng che giấu exception bằng catch và fallback trống

Một anti-pattern liên quan:

```java
// KHÔNG NÊN: nuốt mọi RuntimeException và tiếp tục như thành công.
static String unsafeOperation() {
    try {
        return performImportantOperation();
    } catch (RuntimeException ex) {
        return "OK";
    }
}
```

Ví dụ chỉ minh họa, giả định phương thức `performImportantOperation()` được định nghĩa ở nơi khác. Nó có thể che cả lỗi logic lập trình, lỗi lưu dữ liệu hoặc ngoại lệ do môi trường.

Một phiên bản có chính sách rõ hơn sẽ phân biệt lỗi có thể phục hồi và lỗi phải báo:

```java
// Minh họa; giả định recoverableAction() và notifyFailure(...) có sẵn.
static String performWithPolicy() {
    try {
        return recoverableAction();
    } catch (TransientServiceException ex) {
        notifyFailure(ex);
        throw ex;
    }
}
```

Đây là **pseudocode minh họa**: `TransientServiceException`, `recoverableAction()` và `notifyFailure()` không phải API Java dựng sẵn. Mục đích là chỉ ra rằng việc bắt một loại lỗi dự kiến phải có chính sách tường minh — phục hồi có kiểm soát, trả kết quả lỗi có kiểu hoặc ném tiếp — thay vì `return "OK"` bất kể nguyên nhân.

Trong thực tế, không phải ứng dụng nào cũng phải ném exception cho mọi dữ liệu lạ. Có thể trả một `Result` có kiểu riêng như `UnsupportedInput`. Quan trọng là **lỗi được biểu diễn, không bị giả làm thành công**.

## 9. Quy tắc viết switch dễ phát hiện lỗi

### 9.1. Tách nhánh nghiệp vụ khỏi fallback kỹ thuật

Một `switch` nên làm rõ các biến thể nghiệp vụ hợp lệ trước. Nếu miền kiểu đóng, hãy để compiler cảnh báo thiếu nhánh. Nếu miền kiểu mở, mới quyết định một chính sách fallback rõ ràng.

Đừng viết `default -> null`, `default -> false` hoặc `default -> "OK"` chỉ để xóa lỗi “switch expression does not cover all possible input values”, trừ khi các kết quả ấy **thực sự** là hợp đồng của mọi trường hợp còn lại.

### 9.2. Cụ thể trước, tổng quát sau

Đặt pattern chi tiết hoặc có guard trước pattern bao quát:

```java
case Retry(int seconds) when seconds > 0 -> "Đang chờ";
case Retry retry -> throw new IllegalArgumentException("Sai seconds");
```

Nếu đảo thứ tự, `case Retry retry` có thể bao phủ toàn bộ `Retry`, làm nhánh cụ thể phía sau bị *dominated* và không biên dịch được. Compiler giúp phát hiện những trường hợp dominance theo quy tắc của Java.

### 9.3. Không để generic default che việc thay đổi sealed hierarchy

Mẫu cần tránh ở domain đóng:

```java
// Bất lợi: khi thêm subtype mới, có thể không nhận được cảnh báo
// thiếu case trong biểu thức này vì đã có default.
return switch (result) {
    case Ok ok -> "OK";
    case Rejected rejected -> "NO";
    default -> "OTHER";
};
```

Đoạn code là minh họa trong phương thức trả về `String`, biến `result` đã có. Nếu `Retry` cần một kết quả rõ ràng, hãy thay `default` bằng case `Retry` và chỉ dùng nhánh bao quát khi hợp đồng thật sự yêu cầu.

### 9.4. Chọn đúng loại lỗi

- **`IllegalArgumentException`** phù hợp khi đầu vào vi phạm hợp đồng phương thức, như số giây âm hoặc subtype không được hỗ trợ.
- **`IllegalStateException`** phù hợp khi trạng thái nội bộ không phù hợp với thao tác đang yêu cầu.
- **Domain exception có tên hoặc result type** phù hợp khi lỗi nghiệp vụ cần được xử lý ở các tầng khác, ví dụ `PaymentDeclined` hay `ValidationError`.
- **`NullPointerException`** có thể là hệ quả của việc dùng selector null mà không có case, nhưng nếu null là lỗi đầu vào cần báo có chủ đích, dùng kiểm tra/`case null` rõ ràng sẽ dễ hiểu hơn.

Không có một exception phù hợp cho mọi tình huống. Điều quan trọng là **định nghĩa được ai phát hiện lỗi, ai xử lý và hành vi nào được xem là thành công**.

## 10. Bảng quyết định: dùng default, case null hay throw?

| Tình huống | Cách xử lý nên cân nhắc | Lý do |
| --- | --- | --- |
| `switch expression` trên sealed domain với tất cả subtype được biết | Liệt kê case cụ thể, thường không thêm `default` | Compiler kiểm tra exhaustiveness và cảnh báo khi mở rộng subtype. |
| Một subtype hợp lệ nhưng component không đạt invariant | Case cùng subtype + validation, `throw` hoặc kết quả lỗi có kiểu | Không biến dữ liệu sai thành trạng thái thành công chung. |
| Selector có thể bằng `null` | `case null` hoặc kiểm tra trước `switch` | Phân biệt chính sách null với fallback kiểu khác. |
| API nhận `Object`/interface mở và chấp nhận kiểu chưa biết | `default` có nhãn fallback được tài liệu hóa | Đây có thể là hành vi bình thường, không phải lỗi. |
| API nhận kiểu không biết nhưng nghiệp vụ không thể tiếp tục | `default -> throw ...` hoặc validation tại boundary | Lỗi được thể hiện rõ và có thể quan sát. |
| Mở rộng `sealed permits` trong lần phát hành mới | Biên dịch lại các `switch`, thêm case và test | Tránh thiếu xử lý trạng thái hợp lệ mới. |
| Hệ thống cố ý có `Unknown` là một trạng thái hợp lệ | Tạo subtype/result riêng khi phù hợp | Không đánh đồng unknown có chủ đích với lỗi chương trình. |

## 11. Kiểm thử nhánh lỗi, không chỉ nhánh thành công

Một bộ test nên kiểm tra cả những trường hợp mà `default` dễ che giấu:

1. **Mỗi subtype được phép:** với `Ok`, `Rejected`, `Retry`, xác minh kết quả cụ thể; không chỉ kiểm tra phương thức không ném exception.
2. **Giá trị biên của guard:** `Retry(1)`, `Retry(0)`, `Retry(-1)`; kiểm tra chính xác điều kiện `seconds > 0`.
3. **Component nullable:** `Rejected(null)` hoặc `Rejected("")` nếu mô hình có thể tạo ra; xác định exception hoặc result lỗi.
4. **Selector null:** test riêng, không giả định `default` xử lý.
5. **Kiểu ngoài miền:** với API nhận `Object`, truyền `String` hoặc một loại khác để kiểm tra fallback hoặc exception đúng hợp đồng.
6. **Thay đổi sealed hierarchy:** mỗi khi thêm subtype, biên dịch lại, xử lý warning/error và bổ sung test cho biến thể mới.
7. **Quan sát lỗi:** khi một lỗi phải được ghi nhận, đảm bảo chương trình không chuyển nó thành `"OK"` hoặc `false` mà người gọi hiểu là thành công.

Có thể dùng JUnit để viết unit test như `assertThrows(IllegalArgumentException.class, ...)`, nhưng không cần thư viện ngoài để nắm ý tưởng cốt lõi: mỗi nhánh thất bại phải có **kết quả mong đợi rõ ràng**.

## 12. Tự kiểm tra

Giả sử:

```java
sealed interface JobState permits Done, Failed, Waiting {}
record Done(int id) implements JobState {}
record Failed(String reason) implements JobState {}
record Waiting(int seconds) implements JobState {}
```

**Câu 1.** Vì sao đoạn sau không nên dùng khi `Waiting` là trạng thái nghiệp vụ quan trọng?

```java
// Minh họa trong phương thức nhận JobState state.
return switch (state) {
    case Done done -> "Xong";
    case Failed failed -> "Lỗi";
    default -> "Khác";
};
```

**Đáp án:** `Waiting` bị đẩy vào `default` và mất thông tin rằng tác vụ đang chờ. Với sealed hierarchy, nên thêm case `Waiting` rõ ràng và để compiler kiểm tra tính đầy đủ của `switch`.

**Câu 2.** Nếu `Waiting(0)` không hợp lệ, chỉ thêm `case Waiting waiting -> "Chờ"` đã đủ chưa?

**Đáp án:** Chưa. Việc khớp subtype không kiểm tra quy tắc `seconds > 0`. Cần validation ở constructor hoặc phân nhánh guard và báo lỗi khi giá trị không đạt.

**Câu 3.** Nếu `state == null` nhưng `switch` chỉ có `default` thì có thể chắc chắn nhận `"Khác"` không?

**Đáp án:** Không. Với pattern matching for `switch` Java 21, `null` có cách xử lý riêng. Có thể nhận `NullPointerException` nếu không có chính sách null; dùng `case null` hoặc kiểm tra trước `switch` khi cần.

**Ghi nhớ:** `default` **không sai tự thân**. Nó nguy hiểm khi biến một trường hợp **đáng lẽ phải được xử lý hoặc báo lỗi rõ ràng** thành kết quả chung, khiến người gọi tưởng chương trình đã xử lý thành công. Với domain đóng, ưu tiên các `case` cụ thể để compiler kiểm tra exhaustiveness; với đầu vào mở, định nghĩa fallback hoặc exception đúng hợp đồng; với `null` và dữ liệu vi phạm invariant, kiểm tra tường minh. Làm vậy giúp lỗi hiện ra đúng nơi, thay vì bị che trong một nhánh `default` tưởng như tiện lợi.
