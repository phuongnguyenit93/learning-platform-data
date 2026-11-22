# Giữ thông tin lỗi độc lập với câu chữ của `message` trong ngoại lệ tùy chỉnh Java

Một ngoại lệ Java thường có thông điệp được lấy bằng `getMessage()`, chẳng hạn `"quantity must be positive"`. Chuỗi này hữu ích cho người đọc và chẩn đoán, nhưng **không nên trở thành khóa điều khiển chương trình**: chỉ cần sửa câu chữ, dịch thông điệp sang tiếng Việt hoặc đổi thư viện là các nhánh `if` so sánh message có thể hoạt động sai.

Với **ngoại lệ tùy chỉnh (custom exception)**, cách thiết kế bền vững hơn là tách ba trách nhiệm:

1. **Kiểu ngoại lệ** biểu diễn nhóm thất bại phù hợp với hợp đồng API, ví dụ `ValidationException` hoặc `OrderException`.
2. **Mã lỗi và các thuộc tính có kiểu** biểu diễn sự thật mà chương trình cần dựa vào, ví dụ `ValidationCode.OUT_OF_RANGE`, tên trường `quantity` hoặc một mã thao tác đã được chuẩn hóa.
3. **`message`** biểu diễn một câu giải thích phục vụ người đọc/log, có thể thay đổi mà không làm đổi logic xử lý; **`cause`** giữ đối tượng ngoại lệ gốc khi có chuyển đổi lỗi giữa các tầng.

> Nguyên tắc: **điều khiển bằng kiểu và dữ liệu có cấu trúc; giải thích bằng message; giữ nguyên nhân bằng cause.** Không phân nhánh nghiệp vụ dựa trên việc message chứa một từ hay khớp nguyên văn một câu.

## 1. Vấn đề của việc dùng `getMessage()` làm mã lỗi

Ví dụ thiết kế mong manh:

```java
try {
    placeOrder();
} catch (IllegalArgumentException ex) {
    if ("quantity must be positive".equals(ex.getMessage())) {
        showQuantityError();
    } else {
        showGenericError();
    }
}
```

Đây là **mã minh họa**, giả định các phương thức được khai báo phù hợp. Chỉ cần người viết sửa câu từ `"quantity must be positive"` thành `"quantity must be greater than zero"`, người gọi có thể rơi vào nhánh lỗi chung, dù bản chất lỗi hoàn toàn không đổi.

Các vấn đề khác:

- **Địa phương hóa:** bản tiếng Việt `"Số lượng phải lớn hơn 0"` không khớp chuỗi tiếng Anh.
- **Thông tin ngữ cảnh:** message có thể thêm tên trường, mã yêu cầu hoặc thao tác, làm so sánh toàn chuỗi không còn đúng.
- **Thay thư viện:** một thư viện parse số có thể thay cách tạo `NumberFormatException.getMessage()`.
- **Thiếu message:** `Throwable.getMessage()` có thể trả về `null`; gọi `ex.getMessage().contains(...)` có nguy cơ ném `NullPointerException` ngay trong handler.
- **Độ ổn định:** message là giao diện chẩn đoán cho người đọc, không nhất thiết là giao thức máy móc ổn định.
- **An toàn:** cố đưa toàn bộ giá trị đầu vào hoặc bí mật vào message chỉ để dễ phân nhánh có thể làm lộ thông tin qua log và stack trace.

Cũng đừng sửa cách so sánh thành:

```java
if (ex.getMessage().contains("quantity")) {
    // ...
}
```

Vì một lỗi nội bộ không liên quan có thể tình cờ chứa từ `quantity`. So khớp văn bản bằng `contains` hay regex chỉ làm phụ thuộc vào câu chữ theo một cách khó kiểm soát hơn.

## 2. “Thông tin lỗi độc lập với message” thực chất là gì?

Giả sử quy tắc nhập liệu có ba nguyên nhân:

| Sự thật về lỗi | Mã có cấu trúc | Message có thể hiển thị |
| --- | --- | --- |
| Thiếu số lượng bắt buộc | `REQUIRED_FIELD` | `quantity is required` |
| Số lượng không phải số nguyên hợp lệ | `INVALID_INTEGER` | `quantity must be an integer` |
| Số lượng nằm ngoài phạm vi 1–100 | `OUT_OF_RANGE` | `quantity must be between 1 and 100` |

**Mã lỗi** mang ý nghĩa chương trình cần hiểu và phải được duy trì ổn định theo hợp đồng. **Message** giúp người đọc hiểu điều kiện thất bại, có thể được viết lại cho rõ, được dịch hoặc dùng từ khác trong log.

Khi caller cần biết lỗi ở trường nào, có thể thêm thuộc tính `field`:

```java
String field = ex.getField();
```

Câu trên là **mã minh họa**: `ex` phải là ngoại lệ tùy chỉnh có phương thức `getField()`. Caller dùng thuộc tính thay vì tìm từ `quantity` trong message.

Với lỗi có nhiều thông số, các thuộc tính còn có thể là `minAllowed`, `maxAllowed`, `operation` hoặc `retryable`. Nhưng **không nên thêm mọi dữ liệu thô** vào exception: chỉ giữ những gì cần thiết, có hợp đồng rõ và được phép xuất hiện trong đối tượng có thể bị log.

### Bốn loại dữ liệu cần tách riêng

| Thành phần | Mục đích | Có thể thay đổi vì lý do gì? |
| --- | --- | --- |
| `Throwable` subtype | Phân loại nhóm thất bại | Thiết kế API Java |
| Mã lỗi (`enum`/hằng giá trị) | Phân nhánh ổn định, mapping sang phản hồi | Chỉ đổi có kế hoạch tương thích |
| Ngữ cảnh có kiểu | Biết trường/tác vụ/quy tắc liên quan | Theo hợp đồng dữ liệu |
| `message` | Giải thích/log/chẩn đoán | Câu chữ, bản địa hóa, cải thiện trải nghiệm |
| `cause` | Bảo toàn ngoại lệ gốc | Phụ thuộc đường lỗi và thao tác được gọi |

Một exception có thể không có cause nếu lỗi phát sinh trực tiếp từ điều kiện nghiệp vụ; không nên tạo cause giả chỉ để mọi constructor đều có cause.

## 3. Chọn kiểu ngoại lệ phù hợp trước khi thêm thuộc tính

Trong bài toán **không phụ thuộc vào cách viết message**, câu hỏi đầu là caller cần phân biệt bằng **subtype**, **mã lỗi**, hay cả hai:

- Chọn subtype (`InvalidQuantityException`, `PaymentDeclinedException`) khi caller muốn `catch` theo một hành động khác biệt.
- Chọn một exception với `ValidationCode` typed khi nhiều lý do có cùng cách xử lý nhưng UI/API cần mã cụ thể.
- Chọn checked hay unchecked theo hợp đồng caller, không theo việc lỗi có thể “sửa được” hay không.
- Nếu xác thực thất bại là outcome dự kiến của một form, một `ValidationResult` có cấu trúc có thể phù hợp hơn ném exception hàng loạt.

Dù lựa chọn nào, **không so sánh `getMessage()` để điều khiển flow**.

## 4. Thiết kế `enum` mã lỗi

Một mã typed giúp người gọi phân nhánh mà không phụ thuộc ngôn ngữ của message:

~~~java
enum ValidationCode {
    REQUIRED_FIELD, INVALID_INTEGER, OUT_OF_RANGE
}
~~~

`enum` hữu ích trong cùng module; code public qua JSON nên có chuỗi ổn định/versioned cùng chính sách cho **unknown code**. Đừng dùng `ordinal()` làm mã giao thức: đổi thứ tự enum sẽ đổi số. Nếu tên enum có thể đổi theo refactor, giữ một property `publicCode` cố định thay vì dùng `name()` làm hợp đồng public không được kiểm soát.

**Mã phải mô tả ý nghĩa lỗi**, không chỉ là bản viết hoa message. Việc cập nhật bản dịch từ `"must be an integer"` sang `"enter a whole number"` không làm thay đổi `INVALID_INTEGER`.

## 5. Thuộc tính của custom exception nên được thiết kế thế nào?

Để **giữ thông tin lỗi độc lập với message**, custom exception có thể đặt `private final ValidationCode code` và `private final String field`, công bố getter/record accessor rõ nghĩa và kiểm tra `null` ở constructor. Luôn dùng `super(message, cause)` khi chuyển một lỗi kỹ thuật thực sự; không tạo `cause` giả cho lỗi validation tự phát.

Caller đọc `ex.getCode()` và `ex.getField()`; UI tự ánh xạ mã sang thông điệp an toàn theo locale. **Không cần** parse tên field hay dải giá trị từ `ex.getMessage()`. Khi exception vượt qua ranh giới JSON/API, chỉ serialize DTO có schema được cho phép, không công khai cả stack trace hoặc `Throwable`.

Các quy tắc chi tiết về bất biến sâu, tránh hai bản sao ID, snapshot collection và tối thiểu hóa context được áp dụng trong bài thiết kế ngữ cảnh có kiểu; ở đây, trọng tâm là chứng minh **đổi câu chữ không làm đổi kết quả phân loại**.

## 6. Ví dụ Java 17+ hoàn chỉnh: validation có mã, trường và cause

Ví dụ này mô phỏng kiểm tra số lượng đơn hàng, không cần file hoặc dịch vụ ngoài. Lưu tệp **`StructuredValidationDemo.java`**:

```java
import java.util.Objects;

public class StructuredValidationDemo {

    enum ValidationCode {
        REQUIRED_FIELD,
        INVALID_INTEGER,
        OUT_OF_RANGE
    }

    static final class ValidationException
            extends IllegalArgumentException {

        private static final long serialVersionUID = 1L;

        private final ValidationCode code;
        private final String field;

        ValidationException(
                ValidationCode code,
                String field,
                String message) {
            this(code, field, message, null);
        }

        ValidationException(
                ValidationCode code,
                String field,
                String message,
                Throwable cause) {
            super(message, cause);
            this.code = Objects.requireNonNull(code, "code");
            this.field = Objects.requireNonNull(field, "field");
        }

        ValidationCode getCode() {
            return code;
        }

        String getField() {
            return field;
        }
    }

    static int parseQuantity(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new ValidationException(
                    ValidationCode.REQUIRED_FIELD,
                    "quantity",
                    "Quantity is required");
        }

        final int number;
        try {
            number = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new ValidationException(
                    ValidationCode.INVALID_INTEGER,
                    "quantity",
                    "Quantity must be a whole number",
                    cause);
        }

        if (number < 1 || number > 100) {
            throw new ValidationException(
                    ValidationCode.OUT_OF_RANGE,
                    "quantity",
                    "Quantity must be between 1 and 100");
        }

        return number;
    }

    static void runCase(String raw) {
        try {
            System.out.println("OK quantity=" + parseQuantity(raw));
        } catch (ValidationException ex) {
            System.out.println("ERROR code=" + ex.getCode());
            System.out.println("field=" + ex.getField());
            System.out.println("message=" + ex.getMessage());
            System.out.println(
                    "cause="
                    + (ex.getCause() == null
                            ? "none"
                            : ex.getCause().getClass().getSimpleName()));
        }
    }

    public static void main(String[] args) {
        runCase("5");
        runCase(null);
        runCase("abc");
        runCase("0");
        runCase("200");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 StructuredValidationDemo.java
java StructuredValidationDemo
```

**Stdout chính xác:**

```text
OK quantity=5
ERROR code=REQUIRED_FIELD
field=quantity
message=Quantity is required
cause=none
ERROR code=INVALID_INTEGER
field=quantity
message=Quantity must be a whole number
cause=NumberFormatException
ERROR code=OUT_OF_RANGE
field=quantity
message=Quantity must be between 1 and 100
cause=none
ERROR code=OUT_OF_RANGE
field=quantity
message=Quantity must be between 1 and 100
cause=none
```

### Phân tích chương trình

**`runCase("5")`:** chuỗi có số nguyên `5`, nằm trong khoảng 1–100; `parseQuantity` trả `5`, không có ngoại lệ.

**`runCase(null)`:** điều kiện `raw == null || raw.isBlank()` có *short-circuit*, nên không gọi `isBlank()` khi `raw` null. Custom exception được tạo với `REQUIRED_FIELD` và trường `quantity`, không có cause vì lỗi được xác định trực tiếp.

**`runCase("abc")`:** `Integer.parseInt` ném `NumberFormatException`. Code bắt lỗi ở nơi có thể thêm ngữ cảnh; nó tạo `ValidationException` có mã `INVALID_INTEGER`, giữ `NumberFormatException` làm cause. Handler nhìn thấy mã ổn định mà không phải dựa vào văn bản `For input string ...` vốn phụ thuộc JDK.

**`runCase("0")` và `runCase("200")`:** parse thành số thành công nhưng vượt giới hạn nghiệp vụ, nên mã đều là `OUT_OF_RANGE`. Một mã lỗi có thể đại diện cho cùng một quy tắc ngay cả khi giá trị đầu vào khác nhau.

Chương trình cố ý **không in giá trị thô gây lỗi**. Dữ liệu nhập đôi khi nhạy cảm hoặc rất dài, không nên ghép trực tiếp mọi input vào `message`.

### Thay message có làm thay đổi logic không?

Giả sử sửa:

```java
"Quantity must be a whole number"
```

thành:

```java
"Please enter a valid integer for quantity"
```

Đây là ví dụ sửa **duy nhất một chuỗi trong code**. Đầu ra `message=...` sẽ đổi, nhưng mã `INVALID_INTEGER` và field `quantity` vẫn giữ nguyên. Nếu caller dùng `getCode()`, logic phân nhánh **không đổi**. Đây là tiêu chí quan trọng của thiết kế yêu cầu “giữ thông tin lỗi độc lập với câu chữ của message”.

## 7. Cách caller xử lý bằng mã lỗi thay vì bằng message

Với ngoại lệ `ValidationException` ở ví dụ, một handler có thể dùng:

```java
catch (ValidationException ex) {
    switch (ex.getCode()) {
        case REQUIRED_FIELD ->
                markFieldRequired(ex.getField());
        case INVALID_INTEGER ->
                markFieldInvalid(ex.getField());
        case OUT_OF_RANGE ->
                markFieldOutOfRange(ex.getField());
    }
}
```

Đây là **đoạn minh họa**, giả định các hàm `markField...` tồn tại và cấu trúc nằm sau `try` phù hợp. Caller dựa vào giá trị `enum`. Không cần gọi `getMessage()` để quyết định xử lý.

Lợi ích của `switch` theo enum:

1. Chính sách xử lý tách biệt với cách diễn đạt thông điệp.
2. Dễ test nhánh `REQUIRED_FIELD` mà không khóa bài test vào câu tiếng Anh.
3. Có thể địa phương hóa thông báo.
4. IDE có thể phát hiện nơi cần thay đổi nếu mã lỗi mới được thêm.
5. Phạm vi xử lý rõ hơn một chuỗi `if/else` kiểm tra các từ khóa tùy ý.

**Tuy nhiên, handler vẫn cần hiểu ý nghĩa từng mã.** Nếu một tên mã được đổi hoặc ý nghĩa bị tái sử dụng cho một lỗi khác, “có enum” không tự cứu được tính tương thích. Mã lỗi phải có định nghĩa và quy trình quản lý vòng đời.

## 8. Địa phương hóa và ánh xạ ra API độc lập với message kỹ thuật

Một API có thể muốn trả thông điệp tiếng Việt hoặc tiếng Anh tùy locale, trong khi exception nội bộ giữ thông điệp kỹ thuật để hỗ trợ điều tra. Cách làm hợp lý là **chuyển từ mã lỗi sang message công khai ở ranh giới giao tiếp**.

Ví dụ:

```text
ValidationException {
  code = OUT_OF_RANGE,
  field = "quantity",
  message = "Quantity must be between 1 and 100"
}
                  │
                  ▼
         API error mapping
                  │
           ┌──────┴──────┐
           ▼             ▼
     Locale vi-VN   Locale en-US
           │             │
           ▼             ▼
 "Số lượng phải"   "Quantity must"
 "từ 1 đến 100"    "be from 1 to 100"
```

Thông điệp công khai có thể thay đổi theo locale mà **không sửa mã `OUT_OF_RANGE`** và không cần phân tích chuỗi từ `getMessage()`.

### Ví dụ Java 17+ hoàn chỉnh: cùng mã lỗi, hai message công khai

Lưu tệp **`ErrorCodeMappingDemo.java`**:

```java
public class ErrorCodeMappingDemo {

    enum ErrorCode {
        ORDER_NOT_FOUND("ORD_404"),
        ORDER_ALREADY_CLOSED("ORD_409");

        private final String publicCode;

        ErrorCode(String publicCode) {
            this.publicCode = publicCode;
        }

        String publicCode() {
            return publicCode;
        }
    }

    static final class OrderException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        private final ErrorCode code;
        private final String internalOrderId;

        OrderException(
                ErrorCode code,
                String internalOrderId,
                String diagnosticMessage) {
            super(diagnosticMessage);
            this.code = java.util.Objects.requireNonNull(
                    code, "code");
            this.internalOrderId =
                    java.util.Objects.requireNonNull(
                            internalOrderId, "internalOrderId");
        }

        ErrorCode getCode() {
            return code;
        }

        String getInternalOrderId() {
            return internalOrderId;
        }
    }

    record ApiError(String code, String message) {}

    static void process(String mode) {
        switch (mode) {
            case "missing" -> throw new OrderException(
                    ErrorCode.ORDER_NOT_FOUND,
                    "internal-17",
                    "Order lookup returned no record");
            case "closed" -> throw new OrderException(
                    ErrorCode.ORDER_ALREADY_CLOSED,
                    "internal-18",
                    "Cannot update a closed order");
            default -> System.out.println("result=OK");
        }
    }

    static ApiError toPublicError(
            OrderException ex, boolean vietnamese) {

        String message = switch (ex.getCode()) {
            case ORDER_NOT_FOUND -> vietnamese
                    ? "Không tìm thấy đơn hàng"
                    : "Order not found";
            case ORDER_ALREADY_CLOSED -> vietnamese
                    ? "Đơn hàng đã đóng"
                    : "Order is already closed";
        };

        return new ApiError(
                ex.getCode().publicCode(),
                message);
    }

    static void runCase(String mode) {
        try {
            process(mode);
        } catch (OrderException ex) {
            ApiError en = toPublicError(ex, false);
            ApiError vi = toPublicError(ex, true);

            System.out.println("code=" + en.code());
            System.out.println("en=" + en.message());
            System.out.println("vi=" + vi.message());
            System.out.println(
                    "diagnostic=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        runCase("ok");
        runCase("missing");
        runCase("closed");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ErrorCodeMappingDemo.java
java ErrorCodeMappingDemo
```

**Stdout chính xác:**

```text
result=OK
code=ORD_404
en=Order not found
vi=Không tìm thấy đơn hàng
diagnostic=Order lookup returned no record
code=ORD_409
en=Order is already closed
vi=Đơn hàng đã đóng
diagnostic=Cannot update a closed order
```

### Tại sao không trả nguyên `ex.getMessage()` cho client?

Trong ví dụ, `OrderException` giữ `internalOrderId` để tầng nội bộ nhận biết tác vụ, nhưng DTO `ApiError` **không chứa ID nội bộ**. Đây là sự phân tách có chủ đích: client chỉ cần mã công khai và thông điệp phù hợp.

Đối với production:

- Không tự động trả message nội bộ ra HTTP response; có thể chứa đường dẫn, SQL, cấu hình hoặc dữ liệu nhạy cảm.
- Ánh xạ mã lỗi sang **HTTP status** bằng quy tắc rõ ràng nếu ứng dụng là API web (ví dụ lỗi không tìm thấy tài nguyên thường có thể ánh xạ sang 404, lỗi trạng thái tùy ngữ nghĩa có thể là 409). Quyết định tùy hợp đồng thực tế.
- Nếu message đa ngôn ngữ dùng resource bundle hoặc hệ thống localization, khóa tra cứu nên đến từ **mã lỗi ổn định**, không phải chính câu tiếng Anh.
- Khi thay đổi câu chữ, test vẫn kiểm tra code và dữ liệu có cấu trúc; test nội dung bản dịch có thể là một nhóm kiểm tra riêng.
- Bản ghi log nên có mã tương quan không nhạy cảm và đối tượng `Throwable`, nhưng không ghi tràn lan ID cá nhân.

**Đoạn `diagnostic=...` trong stdout là cho mục đích minh họa.** Trong ứng dụng thật, thông điệp này thuộc log nội bộ được kiểm soát, không thuộc phản hồi API.

## 9. Vì sao phải giữ `cause` khi chuyển ngoại lệ thư viện sang ngoại lệ tùy chỉnh?

Một lỗi có cấu trúc không thay thế **dấu vết kỹ thuật** của nguyên nhân gốc.

Ví dụ:

```java
static int parseAge(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException cause) {
        throw new ValidationException(
                ValidationCode.INVALID_INTEGER,
                "age",
                "Age must be an integer",
                cause);
    }
}
```

Đây là **phương thức minh họa** cần đặt trong phạm vi nhìn thấy `ValidationException` và `ValidationCode` ở ví dụ trước. Caller dựa vào `INVALID_INTEGER` và `age` để quyết định phản hồi, trong khi `getCause()` còn trỏ tới `NumberFormatException` gốc để điều tra.

### Cách làm mất dấu vết

```java
catch (NumberFormatException ex) {
    throw new ValidationException(
            ValidationCode.INVALID_INTEGER,
            "age",
            "Age is invalid");
}
```

Nếu chỉ tạo wrapper không có `cause`, handler ở tầng ngoài khó biết lỗi thật do định dạng, số vượt giới hạn `int` hay một chi tiết parse khác. Có những tình huống cố tình bỏ cause vì chính sách bảo mật hoặc tầng trừu tượng, nhưng đó phải là quyết định có chủ đích, không phải do quên constructor.

**`cause` không phải message.** Việc tạo chuỗi `"invalid: " + ex.getMessage()` không tương đương giữ nguyên đối tượng `ex`. Mất kiểu, stack trace và các suppressed exceptions của nguyên nhân.

### Ném lại cùng đối tượng

Nếu tầng trung gian không cần đổi hợp đồng lỗi, `throw ex;` ném lại cùng ngoại lệ. Điều này giữ nguyên mã lỗi, field, cause và stack trace đang được ghi trên đối tượng. Không cần tạo wrapper mới ở mọi tầng.

### Tránh biến `cause` thành mã lỗi công khai

Caller không nên dò tên lớp `NumberFormatException` trong `getCause()` rồi mặc định coi nó là lỗi field `quantity`; tầng parse mới biết tên field, nên tầng đó nên cung cấp **mã validation và tên trường có cấu trúc**. Cause phục vụ chẩn đoán, không thay cho hợp đồng nghiệp vụ.

## 10. Ngoại lệ tùy chỉnh với nhiều thông số ngữ cảnh

Nếu lỗi có những thuộc tính giúp caller hành động chính xác, bạn có thể thêm field có kiểu:

```java
final class RangeViolationException
        extends IllegalArgumentException {

    private static final long serialVersionUID = 1L;

    private final String field;
    private final int minimum;
    private final int maximum;

    RangeViolationException(
            String field, int minimum, int maximum) {
        super("Field is outside the allowed range");
        this.field = java.util.Objects.requireNonNull(
                field, "field");
        this.minimum = minimum;
        this.maximum = maximum;
    }

    String getField() {
        return field;
    }

    int getMinimum() {
        return minimum;
    }

    int getMaximum() {
        return maximum;
    }
}
```

Đây là **một lớp minh họa** có thể đặt trong cùng package thích hợp. Handler có thể tạo thông báo theo ngôn ngữ và hệ thống UI dựa trên `field`, `minimum` và `maximum`, không cần parse ngược các con số từ message.

### Dữ liệu nào không nên cho vào field của exception?

Không nên tự động lưu:

- Mật khẩu, token, cookie, khóa API.
- Toàn bộ request body hoặc dữ liệu nhạy cảm của khách hàng.
- Payload cực lớn hoặc object mutable có vòng đời phức tạp.
- Các tham chiếu tới kết nối/stream chỉ để “đọc lại ngữ cảnh” sau khi chúng đã đóng.
- Đối tượng nội bộ có ràng buộc đa luồng mà caller không thể quản lý.

Các field nằm trong đối tượng ngoại lệ có thể bị log, serialize, quan sát bởi debugger hoặc telemetry. Chỉ giữ ngữ cảnh **cần thiết, nhỏ gọn và theo chính sách bảo mật**.

### Đừng quên bất biến thực sự

`private final List<String> details` chỉ làm **tham chiếu danh sách** không đổi; nếu danh sách mutable thì nội dung vẫn có thể đổi. Nếu custom exception cần giữ collection ổn định, cân nhắc snapshot:

```java
this.details = java.util.List.copyOf(details);
```

Đây là đoạn minh họa, áp dụng nếu `details` là một danh sách không null có phần tử phù hợp. Tùy yêu cầu, cần defensive copy cho các đối tượng mutable sâu hơn nữa.

## 11. Cấu trúc DTO cho phản hồi lỗi và hợp đồng công khai

Một **đối tượng ngoại lệ** và một **phản hồi API** phục vụ hai mục tiêu khác nhau:

| Ngoại lệ nội bộ | DTO phản hồi công khai |
| --- | --- |
| Mang kiểu Java/stack trace/cause | Mang schema ổn định cho client |
| Có message chẩn đoán nội bộ | Có message được phép công khai và bản địa hóa |
| Có thể giữ ngữ cảnh kỹ thuật | Chỉ chứa trường được quy định trong hợp đồng |
| Caller Java có thể bắt theo subtype | Client nhận mã string/status/trường đã định nghĩa |
| Có thể thay đổi khi refactor nội bộ | Cần quản lý tương thích phiên bản |

Ví dụ schema minh họa:

```json
{
  "code": "VAL_003",
  "field": "quantity",
  "message": "Số lượng phải nằm trong khoảng cho phép"
}
```

Mã lỗi là trường được cam kết theo phiên bản API; message là chuỗi hiển thị có thể thay đổi. Trong hệ thống thật cần quy định rõ những field nào ổn định, trạng thái HTTP, cách sử dụng request/correlation ID và điều kiện lộ thông tin.

### Quy tắc về mã ổn định

Nếu một hệ thống đã phát hành mã `ORD_404` cho lỗi “không tìm thấy đơn hàng”, hãy tránh dùng lại mã đó cho lỗi “đơn hàng đóng” ở phiên bản sau. Việc tái sử dụng ý nghĩa khiến client dùng mã cũ hiểu sai.

Một bộ mã ổn định thường có:

- Tên hoặc giá trị công khai **duy nhất**.
- Định nghĩa chính xác về điều kiện lỗi.
- Phạm vi áp dụng ở module/domain.
- Hướng dẫn client có thể xử lý thế nào.
- Chính sách thêm mã mới, thay thế và ngừng hỗ trợ mã cũ.
- Kiểm thử bảo đảm không đổi ý nghĩa khi sửa message.

Không nhất thiết mọi ứng dụng nhỏ đều cần registry phức tạp, nhưng ngay từ đầu nên xem mã lỗi là **dữ liệu có hợp đồng**, khác với câu chữ tự do.

## 12. Dùng `switch` theo enum: lợi ích và giới hạn

Java 17 hỗ trợ `switch expression`, thuận tiện để ánh xạ mã lỗi sang giá trị:

```java
String publicMessage = switch (code) {
    case REQUIRED_FIELD -> "Required field";
    case INVALID_INTEGER -> "Invalid integer";
    case OUT_OF_RANGE -> "Outside allowed range";
};
```

Đây là đoạn minh họa với `code` có kiểu `ValidationCode` từ ví dụ trước. Không có `default` nên nếu thêm enum constant mà chưa xử lý, trình biên dịch có thể phát hiện switch expression chưa bao phủ đủ các giá trị.

Đây là lợi ích quan trọng của **mã có kiểu** so với `if (message.contains(...))`. Tuy nhiên:

- Caller phải quản lý trường hợp mở rộng enum theo kế hoạch tương thích.
- Nếu mã là string nhận từ hệ thống ngoài, cần kiểm tra input không xác định thay vì gọi `Enum.valueOf` vô điều kiện.
- Enum là lựa chọn tốt khi tập mã được biết khi biên dịch; hệ thống plugin/extensible có thể cần registry hoặc value object thay vì một enum duy nhất.
- Không nên tạo enum tên giống tiếng Anh message rồi coi nó là sự phân tách; enum cần biểu diễn **ý nghĩa ổn định**, không chỉ gắn số thứ tự cho câu chữ.

### Nếu cần xác định lỗi có thể thử lại?

Một số hệ thống thêm thuộc tính `retryable`, nhưng cần thận trọng. “Có thể retry” thường phụ thuộc cả **tình huống xử lý, số lần thử, idempotency, trạng thái giao dịch** và chính sách tầng gọi, không chỉ là tên exception. Không nên mặc định mọi lỗi `IOException` đều retry hoặc mọi lỗi `ValidationException` đều không bao giờ xử lý tiếp; quy tắc phụ thuộc hợp đồng.

Dữ liệu có cấu trúc giúp quyết định chính xác hơn, nhưng **không thay thế việc hiểu ngữ nghĩa tác vụ**.

## 13. Kiểm thử đúng hợp đồng thay vì kiểm tra toàn bộ message

Một bài test dễ vỡ:

```java
// Minh họa: kiểm thử phụ thuộc câu chữ.
assertEquals(
        "Quantity must be a whole number",
        exception.getMessage());
```

Mỗi lần sửa câu chữ hợp lý có thể khiến test thất bại dù hành vi không thay đổi.

Với exception có code và field, bài test nên ưu tiên:

```java
// Minh họa: cần framework assert và biến exception thích hợp.
assertEquals(
        ValidationCode.INVALID_INTEGER,
        exception.getCode());
assertEquals("quantity", exception.getField());
assertInstanceOf(
        NumberFormatException.class,
        exception.getCause());
```

Đây là **các câu lệnh minh họa dạng JUnit**, không phải chương trình độc lập; `assertInstanceOf` là một API trong các phiên bản JUnit phù hợp. Test giúp xác nhận:

- **Phân loại ổn định:** mã `INVALID_INTEGER`.
- **Ngữ cảnh:** trường `quantity`.
- **Nguyên nhân:** `NumberFormatException` được giữ lại.

Có thể kiểm tra message riêng khi message thật sự là phần của hợp đồng công khai hoặc khi kiểm thử tài nguyên bản địa hóa. Khi ấy cần xác định trước rằng thay đổi câu chữ là thay đổi có chủ đích, không coi nó là giao thức xử lý lỗi.

### Kiểm thử không phụ thuộc framework

Ngay cả khi không dùng JUnit, có thể viết các phép kiểm tra thuần Java:

```java
if (ex.getCode() != ValidationCode.INVALID_INTEGER) {
    throw new AssertionError("Unexpected validation code");
}
if (!"quantity".equals(ex.getField())) {
    throw new AssertionError("Unexpected field");
}
if (!(ex.getCause() instanceof NumberFormatException)) {
    throw new AssertionError("Original cause not preserved");
}
```

Đây là đoạn minh họa đặt bên trong handler có `ex` đúng kiểu. Các kiểm tra dựa trên **dữ liệu**, không dựa vào câu chữ của `getMessage()`.

## 14. Tương thích phiên bản khi mã lỗi trở thành hợp đồng

Trong một ứng dụng chỉ có một module, enum có thể thay đổi đồng bộ với caller. Nhưng với thư viện Java public, API ngoài hoặc hệ thống microservices, mã lỗi có thể được nhiều client sử dụng.

Những thay đổi cần cân nhắc:

| Thay đổi | Mức ảnh hưởng điển hình |
| --- | --- |
| Sửa dấu câu, cách diễn đạt message nội bộ | Không nên ảnh hưởng logic dựa trên code |
| Dịch message công khai | Không nên đổi mã lỗi hay field có cấu trúc |
| Thêm enum constant | Caller có `switch` không đầy đủ có thể cần cập nhật |
| Đổi tên enum constant được client Java sử dụng | Có thể phá vỡ tương thích nguồn/binary |
| Đổi giá trị `publicCode` đã phát hành | Có thể phá vỡ client hoặc dữ liệu lưu trữ |
| Dùng lại code cũ cho lỗi mới | Dễ gây hiểu sai âm thầm, nên tránh |
| Đổi subtype exception checked/unchecked | Thay đổi hợp đồng xử lý của caller |
| Xóa field/context đang được client dùng | Có thể phá vỡ API và test |
| Ngừng truyền `cause` từng có trước đó | Làm giảm khả năng chẩn đoán |

Một mã có cấu trúc chỉ hữu ích lâu dài nếu **được định nghĩa và quản trị nhất quán**. Đừng giả định việc dùng `enum` tự động làm mọi thay đổi tương thích.

## 15. Những sai lầm thường gặp

| Sai lầm | Tại sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| `getMessage().equals("...")` để phân nhánh | Đổi chữ hoặc null làm hỏng logic | Dùng mã lỗi/thuộc tính có kiểu |
| `getMessage().contains("...")` | Trùng từ, phụ thuộc thư viện/ngôn ngữ | Phân loại theo hợp đồng |
| Gộp mọi lỗi trong `RuntimeException("failed")` | Không phân biệt nhóm lỗi và nguyên nhân | Chọn subtype/code phù hợp |
| Tạo một class cho mỗi biến thể message | Dễ bùng nổ kiểu mà logic giống nhau | Dùng một loại exception có enum khi phù hợp |
| Chỉ lưu code trong message, không có getter | Caller vẫn phải parse chuỗi | Lưu field `private final` và getter |
| Đổi message thành tiếng Việt rồi làm thay đổi logic | Phá vỡ phân tách trình bày/xử lý | Locale mapping dựa trên code |
| Bọc ngoại lệ nhưng bỏ cause | Mất stack trace, loại lỗi gốc, suppressed | Constructor nhận `Throwable cause` |
| Đưa secret hoặc payload thô vào field/message | Dễ rò rỉ log/telemetry | Chỉ lưu ngữ cảnh an toàn |
| Dùng `enum.name()` làm mã public rồi đổi tên hằng | Gãy hợp đồng public code | Dùng giá trị mã riêng ổn định nếu cần |
| Đặt toàn bộ dữ liệu business vào một string `detail` | Trở lại phụ thuộc câu chữ | Tạo field có kiểu cho dữ liệu cần thiết |
| Nghĩ `private final List` là immutable | Phần tử/danh sách vẫn có thể mutable | Defensive copy đúng mức |
| Trả toàn bộ `Throwable` từ API | Lộ implementation và dữ liệu nội bộ | Chuyển thành DTO công khai |
| Gắn thông điệp người dùng vào ngoại lệ tầng thấp | Trộn i18n vào thư viện/logic | Translate tại boundary giao tiếp |
| Test toàn bộ message dù chưa phải hợp đồng | Test giòn, cản sửa câu chữ | Test code, field, cause và mapping riêng |

## 16. Bài tập luyện tập

**Bài A — phát hiện hợp đồng mong manh**

Một controller có:

```java
if (ex.getMessage().startsWith("quantity")) {
    return "INVALID_QUANTITY";
}
```

Điều gì xảy ra nếu thư viện thay message thành `"Invalid value for field quantity"`?

**Đáp án:** nhánh xử lý có thể sai dù bản chất lỗi không đổi. Cần dùng `ex.getCode()`/`ex.getField()` hoặc một loại ngoại lệ chuyên biệt, không dựa vào prefix văn bản.

**Bài B — cause có phải mã nghiệp vụ không?**

Tầng parse bắt `NumberFormatException` rồi tạo `ValidationException(ValidationCode.INVALID_INTEGER, "quantity", ..., cause)`. Caller có nên nhìn `cause.getMessage()` để quyết định field bị lỗi?

**Không.** Caller dùng field và code có cấu trúc. Cause phục vụ chẩn đoán nguồn thất bại, không cần chứa tên field nghiệp vụ.

**Bài C — sửa message có phá hợp đồng không?**

Thay `"Quantity must be between 1 and 100"` bằng `"Enter a quantity from 1 to 100"`. Nếu code vẫn là `OUT_OF_RANGE`, field là `quantity` và các điều kiện validation không đổi thì các client dựa trên code có bị đổi nhánh không?

**Không.** Đây là mục tiêu của việc tách dữ liệu lỗi khỏi câu chữ.

**Bài D — enum hay string?**

Ứng dụng có năm lỗi validation đã biết lúc biên dịch. Nên bắt đầu từ `enum` hay các string tự do rải khắp mã nguồn?

**`enum`** thường giúp kiểm tra kiểu và refactor dễ hơn. Nếu phải phát hành mã qua network, thêm giá trị public ổn định và chính sách versioning.

**Bài E — dữ liệu nhạy cảm**

Có nên lưu raw API token trong field `private final String token` của `AuthenticationException` để tiện log không?

**Không mặc định.** Field trong exception có thể lộ qua log/debugger/telemetry. Chỉ lưu mã lỗi và ngữ cảnh được cho phép; không tạo thông điệp chứa secret.

**Bài F — test theo message**

Test đang so sánh toàn bộ message ở `ValidationException`. Nếu QA muốn cải thiện thông điệp tiếng Việt, có phải sửa tất cả test nghiệp vụ không?

**Không nên.** Tách test phân loại (code/field/cause) khỏi test bản dịch/câu chữ. Chỉ test toàn bộ message tại nơi message được định nghĩa là hợp đồng.

**Bài G — một lỗi, hai ngôn ngữ**

`OrderException` mang `ORDER_NOT_FOUND`. API muốn tiếng Việt hoặc tiếng Anh. Có nên sửa `ex.getMessage()` của từng exception cho phù hợp locale?

**Không cần.** Tầng API có thể ánh xạ `ORDER_NOT_FOUND` thành thông báo phù hợp ngôn ngữ; mã lỗi giữ nguyên.

**Bài H — final field có đủ không?**

Custom exception có `private final Map<String, Object> metadata` và getter trả trực tiếp map. Có thể khẳng định ngữ cảnh không bị đổi không?

**Không.** `final` chỉ khóa tham chiếu; map có thể bị sửa qua getter hoặc tham chiếu khác. Dùng defensive copy và kiểu dữ liệu có cấu trúc phù hợp, cẩn thận với object mutable bên trong.

**Bài I — đổi ý nghĩa mã lỗi**

Hôm nay `ORD_404` nghĩa là “không tìm thấy đơn hàng”; ngày mai hệ thống dùng lại `ORD_404` nghĩa là “không thể thanh toán”. Có tốt không?

**Không.** Client đang xử lý mã cũ có thể hiểu sai âm thầm. Cần mã mới cho ý nghĩa mới và chính sách tương thích.

## 17. Checklist thiết kế custom exception ổn định

Khi tạo hoặc xem xét một lớp ngoại lệ tùy chỉnh, hãy tự kiểm tra:

1. **Loại lỗi có cần một subtype riêng không?** Nếu caller không xử lý khác, có thể dùng subtype chuẩn hoặc một custom exception theo nhóm domain.
2. **Checked hay unchecked?** Chọn theo hợp đồng phục hồi thực sự của caller, không chọn ngẫu nhiên.
3. **Có mã lỗi ổn định không?** Dùng `enum`, code string có hằng hoặc một value object thay vì ghép từ message.
4. **Những thuộc tính nào caller thực sự cần?** Ví dụ `field`, `operation`, `resourceType`, giá trị giới hạn; tránh phình to và tránh bí mật.
5. **Các field quan trọng có `private final` và getter không?** Có cần defensive copy đối với dữ liệu mutable không?
6. **Constructor có giữ cause không?** Khi wrapper được tạo từ lỗi thư viện, bảo toàn đối tượng gốc khi phù hợp.
7. **Message có chỉ là phần giải thích không?** Thử đổi câu chữ xem nhánh code có bị thay đổi không.
8. **API công khai có dùng mã riêng không?** Nếu có, mã phải ổn định qua phiên bản và khác thông điệp địa phương hóa.
9. **Có mapping rõ ở ranh giới giao tiếp không?** Không tự trả `Throwable` hoặc stack trace nguyên văn cho client.
10. **Có chính sách đổi mã/thêm mã mới không?** Định nghĩa ý nghĩa và tránh tái sử dụng mã cũ.
11. **Kiểm thử tập trung vào code, field, cause chưa?** Đừng khóa các bài test nghiệp vụ vào dấu câu của message.
12. **Log có đủ dấu vết nhưng không lộ dữ liệu không?** Thông tin lỗi có cấu trúc và cause phải đi kèm kiểm soát truy cập.
13. **Các hành vi xử lý có dựa trên ngữ nghĩa, không dựa trên message không?** Chẳng hạn logic retry, HTTP mapping và i18n phải theo hợp đồng.
14. **Đã kiểm tra các trường hợp lỗi trực tiếp và lỗi wrapper chưa?** Lỗi trực tiếp có thể không có cause; lỗi wrapper có thể mang cause/suppressed.

## Kết luận

**`message` dành cho người đọc; mã lỗi và dữ liệu có kiểu dành cho chương trình.** Khi thiết kế ngoại lệ tùy chỉnh Java, hãy chọn subtype phản ánh nhóm thất bại, lưu mã lỗi ổn định cùng thuộc tính cần thiết, giữ `cause` khi chuyển lỗi, và xây dựng thông điệp tự nhiên, dễ hiểu nhưng **không biến câu chữ thành điều kiện điều khiển**.

Cách tách này giúp hệ thống sửa thông điệp, địa phương hóa, chuyển từ console sang API, refactor nội bộ và nâng cấp thư viện mà **không vô tình đổi cách caller nhận diện và xử lý lỗi**. Mã lỗi vẫn cần hợp đồng tương thích, còn dữ liệu được lưu trong exception phải nhỏ gọn, có ý nghĩa và an toàn khi được ghi log.