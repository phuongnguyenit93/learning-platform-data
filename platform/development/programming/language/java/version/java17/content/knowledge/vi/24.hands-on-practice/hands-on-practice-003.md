# Xử lý biến thể bằng instanceof và switch expression phù hợp Java 17

## 1. Bài toán xử lý nhiều biến thể dữ liệu

Trong ứng dụng, một biến có thể đại diện cho nhiều loại dữ liệu hoặc trạng thái khác nhau: kết quả thanh toán thành công/bị từ chối/đang chờ, thông báo email/SMS/push, hoặc sự kiện tạo mới/cập nhật/xóa. Chương trình cần nhận diện loại thực tế rồi thực hiện hành vi phù hợp.

Java 17 có các tính năng ổn định giúp viết logic này rõ ràng:

- **Pattern matching for `instanceof`**: kiểm tra kiểu và khai báo biến có kiểu ngay trong cùng biểu thức.
- **Switch expression**: chọn và trả về một giá trị dựa trên enum, chuỗi hoặc kiểu số nguyên được hỗ trợ.
- **Sealed types**: giới hạn tập kiểu con trực tiếp của một kiểu cha.
- **Records**: biểu diễn các biến thể dữ liệu ngắn gọn.

Các tính năng này có thể kết hợp để xử lý biến thể mà không cần ép kiểu thủ công ở mọi nhánh. Tuy nhiên, trong Java 17 bản ổn định, `switch` chưa hỗ trợ type pattern như `case Circle c -> ...`. Vì vậy, bài này dùng `instanceof` để phân nhánh theo subtype và dùng switch expression cho enum hoặc trạng thái bên trong từng biến thể.

Sau bài học, người học cần:

1. Dùng pattern matching for `instanceof` để kiểm tra kiểu và lấy biến đã được kiểm tra.
2. Hiểu flow scoping của pattern variable trong điều kiện và nhánh điều khiển.
3. Dùng switch expression để trả về giá trị, xử lý enum và viết nhánh nhiều câu lệnh bằng `yield`.
4. Kết hợp sealed interface, record, `instanceof` và switch expression trong mô hình biến thể.
5. Xử lý `null`, generic type erasure và subtype chưa được hỗ trợ.
6. Phân biệt switch expression ổn định trong Java 17 với pattern matching for switch từng ở trạng thái preview.

## 2. Pattern matching for instanceof

### 2.1. Cách viết truyền thống

Trước khi có pattern matching for `instanceof`, code thường phải kiểm tra kiểu rồi ép kiểu lần nữa:

~~~java
Object value = "Java 17";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
~~~

Có hai thao tác lặp lại: kiểm tra `value` có phải `String` hay không, rồi ép kiểu `value` sang `String` để dùng các method của chuỗi.

### 2.2. Pattern matching for instanceof

Java 16 hoàn thiện pattern matching for `instanceof` (JEP 394). Java 17 có thể dùng trực tiếp:

~~~java
Object value = "Java 17";

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Cú pháp:

~~~java
expression instanceof Type patternVariable
~~~

Nếu biểu thức là một instance tương thích với `Type`, điều kiện đúng và biến `patternVariable` được khởi tạo với giá trị đã kiểm tra. Trong nhánh đúng, có thể sử dụng biến này như một biến có kiểu `Type`.

Lợi ích:

- Không cần viết phép ép kiểu riêng.
- Việc kiểm tra và lấy biến có kiểu nằm trong cùng một biểu thức.
- Biến pattern chỉ có hiệu lực trong phạm vi mà compiler chứng minh nó đã được khởi tạo.
- Giảm nguy cơ ép kiểu sai hoặc dùng nhầm biến.

### 2.3. Ví dụ với nhiều subtype

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Chuỗi có " + text.length() + " ký tự";
    } else if (value instanceof Integer number) {
        return "Số nguyên: " + number;
    } else if (value instanceof Boolean flag) {
        return "Giá trị boolean: " + flag;
    }
    return "Kiểu dữ liệu khác";
}
~~~

Mỗi nhánh vừa kiểm tra kiểu vừa khai báo biến tương ứng. Không cần viết `(String) value`, `(Integer) value` hoặc `(Boolean) value`.

Lưu ý: `instanceof` trả về `false` nếu biểu thức bên trái là `null`. Nếu method không chấp nhận null, nên xác định chính sách rõ ràng thay vì để null rơi xuống nhánh “kiểu khác”.

## 3. Flow scoping của pattern variable

Pattern variable không có phạm vi giống một biến được khai báo trước block. Compiler xác định biến có thể được sử dụng ở đâu dựa trên luồng điều khiển.

### 3.1. Trong nhánh if đúng

~~~java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
// text không còn trong phạm vi ở đây.
~~~

Biến `text` chỉ được sử dụng trong vùng mà điều kiện `instanceof` đã được chứng minh là đúng.

### 3.2. Với toán tử &&

Trong biểu thức `&&`, vế phải chỉ được đánh giá khi vế trái đúng. Vì vậy pattern variable có thể dùng ở vế phải:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim());
}
~~~

Ở đây `text` chỉ được sử dụng khi `value` đã được xác nhận là `String`.

### 3.3. Với toán tử ||

Không thể dùng pattern variable trong vế phải của `||` theo cách tương tự:

~~~java
// Không hợp lệ:
// if (!(value instanceof String text) || text.isBlank()) { ... }
~~~

Nếu vế trái của `||` là đúng, vế phải không được đánh giá. Khi đó `text` có thể chưa được khởi tạo, nên compiler không cho phép dùng nó trong vế phải.

Hãy đổi cách viết để điều kiện rõ ràng:

~~~java
if (!(value instanceof String text)) {
    return;
}

if (text.isBlank()) {
    return;
}

System.out.println(text.trim());
~~~

### 3.4. Với phép phủ định và early return

~~~java
if (!(value instanceof String text)) {
    throw new IllegalArgumentException("Expected a String");
}

// Nếu đi tới đây, điều kiện sai nghĩa là value là String.
System.out.println(text.length());
~~~

Compiler biết nhánh `if` không thể đi tiếp sau khi ném exception. Do đó `text` có hiệu lực ở phần sau.

Tương tự, `return`, `throw`, `break` hoặc cấu trúc điều khiển khác có thể ảnh hưởng flow scope. Nên viết nhánh kiểm tra ngắn và dễ đọc để compiler cũng như người review hiểu được điều kiện.

### 3.5. Pattern variable không thể gán lại

Pattern variable được xem là biến local có tính chất final trong ngữ cảnh pattern matching; không thể gán giá trị mới cho nó:

~~~java
if (value instanceof String text) {
    // text = "khác"; // Không hợp lệ.
    System.out.println(text);
}
~~~

Nếu cần biến mutable, hãy tạo một biến local khác sau khi đã kiểm tra kiểu.

## 4. Switch expression trong Java 17

### 4.1. Switch expression trả về giá trị

Switch expression được chuẩn hóa từ Java 14 (JEP 361), vì vậy dùng ổn định trong Java 17.

Khác với switch statement chủ yếu thực hiện hành động, switch expression tính ra một giá trị:

~~~java
int days = switch (month) {
    case 1, 3, 5, 7, 8, 10, 12 -> 31;
    case 4, 6, 9, 11 -> 30;
    case 2 -> 28;
    default -> throw new IllegalArgumentException("Invalid month");
};
~~~

Giá trị của biểu thức switch được gán trực tiếp cho `days`. Các nhánh dùng `->` không tự động rơi xuống nhánh tiếp theo như dạng switch statement cổ điển.

Ví dụ trên chưa xét năm nhuận; nó chỉ minh họa cú pháp switch expression. Nếu cần xử lý lịch thực tế, dùng `YearMonth.lengthOfMonth()` hoặc API `java.time` phù hợp.

### 4.2. Switch expression với enum

Enum là lựa chọn phù hợp khi tập trạng thái đã được xác định:

~~~java
enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}

static String label(OrderStatus status) {
    return switch (status) {
        case NEW -> "Mới tạo";
        case PAID -> "Đã thanh toán";
        case SHIPPED -> "Đã giao";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Vì switch expression phải tạo ra giá trị cho mọi trường hợp có thể xảy ra, compiler yêu cầu biểu thức phải exhaustive. Với enum, liệt kê đủ các hằng là cách rõ ràng. Nếu thêm một hằng mới rồi biên dịch lại, compiler sẽ yêu cầu xử lý trường hợp đó.

Không thêm `default` một cách máy móc nếu muốn compiler giúp phát hiện enum được mở rộng. `default` có thể hữu ích khi cần fallback, nhưng nó cũng có thể che việc chưa cập nhật logic cho hằng mới.

### 4.3. Switch expression với String

~~~java
static String normalizeCommand(String command) {
    return switch (command) {
        case "start" -> "START";
        case "stop" -> "STOP";
        case "reload" -> "RELOAD";
        default -> throw new IllegalArgumentException(
                "Unsupported command: " + command);
    };
}
~~~

Switch với `String` phân biệt chữ hoa/chữ thường. Nếu giao thức không phân biệt hoa thường, chuẩn hóa chuỗi trước khi switch, ví dụ `command.toLowerCase(Locale.ROOT)`. Không dùng locale mặc định cho việc chuẩn hóa token kỹ thuật.

### 4.4. Switch expression với nhiều nhãn

Có thể gộp nhiều hằng vào một nhánh:

~~~java
static String category(int code) {
    return switch (code) {
        case 200, 201, 202 -> "Thành công";
        case 400, 401, 403, 404 -> "Lỗi phía request";
        case 500, 502, 503 -> "Lỗi phía server";
        default -> "Mã khác";
    };
}
~~~

Đây là cú pháp hữu ích khi nhiều giá trị có cùng kết quả. Không đặt những giá trị có ý nghĩa khác nhau vào chung một nhánh chỉ để rút ngắn code.

## 5. Dùng block và yield trong switch expression

Một nhánh switch expression có thể chứa nhiều câu lệnh. Khi đó dùng `yield` để trả về giá trị của nhánh:

~~~java
static String describeStatus(int code) {
    return switch (code) {
        case 200 -> {
            String message = "Request";
            message += " thành công";
            yield message;
        }
        case 404 -> {
            String message = "Không tìm thấy tài nguyên";
            yield message;
        }
        default -> {
            String message = "HTTP status: " + code;
            yield message;
        }
    };
}
~~~

`yield` trả về giá trị từ nhánh switch expression. Nó khác `return`, vì `return` thoát khỏi method hiện tại.

Không dùng `break` để trả về giá trị từ switch expression. Nếu một nhánh dùng block `{ ... }`, phải có đường đi tạo ra giá trị bằng `yield` hoặc kết thúc bằng hành vi không thể hoàn tất bình thường như `throw`.

## 6. Kết hợp instanceof với switch expression

Trong Java 17 ổn định, hai công cụ này giải quyết hai tầng phân loại khác nhau:

1. `instanceof` xác định biến thể object đang có.
2. `switch` expression xử lý một giá trị phân loại đã biết, thường là enum hoặc mã trạng thái.

Ví dụ một kết quả thanh toán có thể là thành công, bị từ chối hoặc đang chờ. Mỗi biến thể chứa thêm một enum mô tả chi tiết.

~~~java
enum PaymentMethod {
    CARD,
    BANK_TRANSFER,
    CASH
}

enum DeclineReason {
    INSUFFICIENT_FUNDS,
    INVALID_ACCOUNT,
    RISK_CHECK
}

enum PendingStage {
    CREATED,
    WAITING_FOR_BANK,
    VERIFYING
}

sealed interface PaymentResult
        permits Paid, Declined, Pending {
}

record Paid(String transactionId, PaymentMethod method)
        implements PaymentResult {
}

record Declined(String transactionId, DeclineReason reason)
        implements PaymentResult {
}

record Pending(String transactionId, PendingStage stage)
        implements PaymentResult {
}

static String describe(PaymentResult result) {
    Objects.requireNonNull(result, "result");

    if (result instanceof Paid paid) {
        String methodName = switch (paid.method()) {
            case CARD -> "thẻ";
            case BANK_TRANSFER -> "chuyển khoản";
            case CASH -> "tiền mặt";
        };

        return "Giao dịch " + paid.transactionId()
                + " đã thanh toán qua " + methodName;
    } else if (result instanceof Declined declined) {
        String reasonText = switch (declined.reason()) {
            case INSUFFICIENT_FUNDS -> "không đủ số dư";
            case INVALID_ACCOUNT -> "tài khoản không hợp lệ";
            case RISK_CHECK -> "không vượt qua kiểm tra rủi ro";
        };

        return "Giao dịch " + declined.transactionId()
                + " bị từ chối: " + reasonText;
    } else if (result instanceof Pending pending) {
        String stageText = switch (pending.stage()) {
            case CREATED -> "đã được tạo";
            case WAITING_FOR_BANK -> "đang chờ ngân hàng";
            case VERIFYING -> "đang xác minh";
        };

        return "Giao dịch " + pending.transactionId()
                + " đang xử lý: " + stageText;
    }

    throw new IllegalArgumentException(
            "Unsupported result type: " + result.getClass().getName());
}
~~~

Trong ví dụ:

- `PaymentResult` là sealed interface giới hạn các biến thể được phép.
- `Paid`, `Declined` và `Pending` là record, mỗi record mang dữ liệu riêng.
- `instanceof` pattern matching chọn đúng nhánh và tạo biến `paid`, `declined` hoặc `pending`.
- Switch expression xử lý enum của từng biến thể và trả về chuỗi mô tả.
- `Objects.requireNonNull` xác định rõ rằng method không chấp nhận `null`.

Phần `throw` cuối cùng là nhánh phòng vệ. Java 17 chưa suy luận tính exhaustive của chuỗi `instanceof` đối với sealed hierarchy như pattern switch ở các bản Java sau. Khi thêm một subtype mới vào `permits`, cần cập nhật logic và test tương ứng.

## 7. Sealed types và records trong mô hình biến thể

### 7.1. Sealed interface giới hạn subtype

Sealed classes/interfaces được chuẩn hóa trong Java 17 (JEP 409). Một sealed type khai báo rõ các kiểu được phép mở rộng hoặc triển khai:

~~~java
sealed interface PaymentResult
        permits Paid, Declined, Pending {
}
~~~

Mỗi subtype trực tiếp phải tuân theo một trong các dạng được phép:

- `final`: không cho phép mở rộng tiếp.
- `sealed`: tiếp tục giới hạn subtype của chính nó.
- `non-sealed`: mở lại khả năng kế thừa.

Trong ví dụ, record là final một cách ngầm định, vì vậy có thể là permitted subtype.

### 7.2. Record phù hợp cho biến thể mang dữ liệu

~~~java
record Paid(String transactionId, PaymentMethod method)
        implements PaymentResult {
}
~~~

Record tự cung cấp component accessor, constructor canonical, `equals`, `hashCode` và `toString`. Đây là cách gọn để biểu diễn một biến thể dữ liệu bất biến ở mức field reference.

Record không tự xác thực mọi quy tắc nghiệp vụ. Nếu cần ràng buộc dữ liệu, dùng compact constructor hoặc validator:

~~~java
record Paid(String transactionId, PaymentMethod method)
        implements PaymentResult {
    Paid {
        Objects.requireNonNull(transactionId, "transactionId");
        Objects.requireNonNull(method, "method");
        if (transactionId.isBlank()) {
            throw new IllegalArgumentException(
                    "transactionId must not be blank");
        }
    }
}
~~~

### 7.3. Vì sao vẫn cần nhánh cuối?

Sealed hierarchy giúp người đọc biết tập subtype trực tiếp được cho phép, nhưng một chuỗi `if/else instanceof` trong Java 17 không có kiểm tra exhaustive ở compile time.

Nếu một subtype được thêm mới:

- Compiler không tự yêu cầu sửa mọi chuỗi `instanceof`.
- Nhánh cuối có thể nhận subtype mới.
- Test phải bao phủ từng permitted subtype.
- Có thể dùng visitor pattern nếu muốn gom hành vi theo kiểu và làm rõ nơi cần cập nhật khi hierarchy thay đổi.

Không viết nhánh cuối trả về một chuỗi thành công mặc định nếu subtype chưa biết cần được xử lý rõ ràng. Thường nên ném exception hoặc chuyển sang xử lý lỗi có chủ đích.

## 8. Giới hạn của switch expression ổn định trong Java 17

### 8.1. Những kiểu selector được hỗ trợ

Trong Java 17, switch statement/expression ổn định hỗ trợ các selector thuộc nhóm:

- `byte`, `short`, `char`, `int` và các wrapper tương ứng.
- `String`.
- Enum.

Không thể dùng `long`, `float`, `double` hoặc `boolean` trực tiếp làm selector của switch.

Ví dụ hợp lệ:

~~~java
String label = switch (statusCode) {
    case 0 -> "OK";
    case 1 -> "WARNING";
    default -> "UNKNOWN";
};
~~~

Ví dụ không hợp lệ:

~~~java
// Không hợp lệ trong Java 17:
// switch (longValue) { ... }
// switch (booleanValue) { ... }
~~~

Nếu cần phân loại giá trị `long`, có thể kiểm tra bằng `if/else` hoặc chuyển đổi có kiểm soát sang một kiểu selector được hỗ trợ. Không ép kiểu tùy tiện nếu có nguy cơ mất dữ liệu.

### 8.2. Java 17 không có type pattern trong switch ổn định

Trong Java 17, cú pháp sau không thuộc tính năng switch ổn định:

~~~java
// Không biên dịch như Java 17 stable:
// return switch (shape) {
//     case Circle circle -> circle.radius() * circle.radius() * Math.PI;
//     case Rectangle rectangle -> rectangle.width() * rectangle.height();
// };
~~~

Pattern matching for switch từng được cung cấp dưới dạng preview trong JDK 17 (JEP 406). Preview feature yêu cầu bật riêng và có thể thay đổi qua các phiên bản preview; không nên dùng cú pháp preview đó làm nền tảng cho source Java 17 ổn định.

Pattern matching for switch chỉ được chuẩn hóa ở Java 21 (JEP 441). Nếu yêu cầu runtime là Java 17, hãy dùng `instanceof` pattern matching kết hợp switch expression trên enum hoặc giá trị được hỗ trợ như các ví dụ trong bài.

### 8.3. Switch expression không tự xử lý null

Nếu selector của switch expression là `null`, Java 17 ném `NullPointerException`:

~~~java
OrderStatus status = null;

// Ném NullPointerException:
// String label = switch (status) { ... };
~~~

Nếu `null` là trạng thái hợp lệ của dữ liệu, xử lý trước:

~~~java
static String label(OrderStatus status) {
    if (status == null) {
        return "Chưa xác định";
    }

    return switch (status) {
        case NEW -> "Mới tạo";
        case PAID -> "Đã thanh toán";
        case SHIPPED -> "Đã giao";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Java 17 stable không có `case null` trong switch expression. Không dựa vào cú pháp preview để xử lý null nếu source cần tương thích ổn định với JDK 17.

## 9. Generic type và instanceof

### 9.1. Không kiểm tra trực tiếp parameterized type

Do type erasure, không thể viết:

~~~java
// Không hợp lệ:
// if (value instanceof List<String> strings) { ... }
~~~

`List<String>` không phải reifiable type tại runtime. Có thể kiểm tra loại raw generic:

~~~java
if (value instanceof List<?> values) {
    System.out.println(values.size());
}
~~~

Sau đó từng phần tử vẫn có kiểu `Object` cho tới khi được kiểm tra riêng:

~~~java
if (value instanceof List<?> values) {
    for (Object item : values) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
~~~

Không cast toàn bộ list thành `List<String>` chỉ vì một vài phần tử đầu tiên là chuỗi. Nếu cần một danh sách chuỗi, hãy xác thực tất cả phần tử rồi mới tạo hoặc trả về kiểu dữ liệu phù hợp.

### 9.2. Array có thể kiểm tra component type

Array giữ thông tin component type tại runtime, nên có thể kiểm tra:

~~~java
if (value instanceof String[] texts) {
    System.out.println(texts.length);
}
~~~

Điều này khác với generic collection bị type erasure. Dù vậy, nếu array có thể là `null`, `instanceof` vẫn trả về `false`.

## 10. So sánh if/else instanceof với switch expression

Hai cấu trúc không thay thế hoàn toàn nhau. Chọn theo loại dữ liệu đang phân loại:

| Nhu cầu | Cấu trúc phù hợp trong Java 17 |
|---|---|
| Phân nhánh theo subtype của object | `if/else` với pattern matching `instanceof` |
| Phân nhánh theo enum | Switch expression |
| Phân nhánh theo String command | Switch expression |
| Phân nhánh theo mã số nguyên | Switch expression |
| Xử lý một sealed hierarchy theo subtype trong switch | Chưa có trong Java 17 stable; dùng `instanceof` hoặc visitor |
| Kiểm tra một giá trị có thuộc kiểu nào không | `instanceof` |
| Cần nhiều câu lệnh để tính một kết quả trong switch | Switch expression với block và `yield` |

Không chuyển một chuỗi `if/else` theo kiểu object thành switch enum bằng cách thêm field `type` nếu field đó có thể không khớp với subtype thực tế. Hai nguồn thông tin phân loại trùng nhau dễ tạo trạng thái mâu thuẫn.

## 11. Ví dụ tổng hợp: xử lý sự kiện ứng dụng

Ví dụ sau minh họa sealed event hierarchy, pattern matching for `instanceof` và switch expression để phân loại mức độ:

~~~java
import java.util.Objects;

public class EventDemo {
    enum Severity {
        INFO,
        WARNING,
        ERROR
    }

    enum RetryPolicy {
        NEVER,
        ONCE,
        EXPONENTIAL
    }

    sealed interface AppEvent permits UserCreated, PaymentFailed, ServiceUnavailable {
    }

    record UserCreated(String userId) implements AppEvent {
    }

    record PaymentFailed(String paymentId, Severity severity)
            implements AppEvent {
    }

    record ServiceUnavailable(String serviceName, RetryPolicy retryPolicy)
            implements AppEvent {
    }

    static String describe(AppEvent event) {
        Objects.requireNonNull(event, "event");

        if (event instanceof UserCreated created) {
            return "Tạo người dùng " + created.userId();
        } else if (event instanceof PaymentFailed failed) {
            String action = switch (failed.severity()) {
                case INFO -> "ghi nhận";
                case WARNING -> "cảnh báo";
                case ERROR -> "điều tra ngay";
            };
            return "Thanh toán " + failed.paymentId()
                    + " thất bại; cần " + action;
        } else if (event instanceof ServiceUnavailable unavailable) {
            String retry = switch (unavailable.retryPolicy()) {
                case NEVER -> "không thử lại";
                case ONCE -> "thử lại một lần";
                case EXPONENTIAL -> "thử lại với exponential backoff";
            };
            return "Dịch vụ " + unavailable.serviceName()
                    + " không khả dụng; " + retry;
        }

        throw new IllegalArgumentException(
                "Unsupported event type: " + event.getClass().getName());
    }

    public static void main(String[] args) {
        AppEvent event = new PaymentFailed("PAY-1024", Severity.ERROR);
        System.out.println(describe(event));
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~bash
javac --release 17 EventDemo.java
java EventDemo
~~~

Kết quả:

~~~text
Thanh toán PAY-1024 thất bại; cần điều tra ngay
~~~

Ở đây `instanceof` xác định loại sự kiện. Switch expression xử lý enum để quyết định hành động. Không dùng pattern switch preview nên source chạy bằng Java 17 ổn định mà không cần `--enable-preview`.

## 12. Những lỗi thường gặp

### 12.1. Kiểm tra instanceof rồi ép kiểu lại

Code sau không cần thiết:

~~~java
if (value instanceof String) {
    String text = (String) value;
}
~~~

Dùng pattern:

~~~java
if (value instanceof String text) {
    // Dùng text trực tiếp.
}
~~~

### 12.2. Dùng pattern variable ngoài flow scope

Pattern variable chỉ tồn tại ở nơi compiler chứng minh nó đã được khởi tạo. Không khai báo trong một điều kiện rồi mặc định dùng được sau mọi nhánh.

**Cách xử lý:** dùng block `if` hoặc early return để làm rõ luồng điều khiển.

### 12.3. Dùng switch statement khi cần một giá trị

Nếu mục tiêu là tạo kết quả để gán hoặc return, switch expression thường gọn và ít lỗi fall-through hơn:

~~~java
String label = switch (status) {
    case NEW -> "Mới";
    case PAID -> "Đã thanh toán";
    case CANCELLED -> "Đã hủy";
};
~~~

### 12.4. Quên yield trong nhánh block

Một nhánh switch expression dùng block `{ ... }` phải tạo ra kết quả bằng `yield` nếu hoàn tất bình thường.

**Cách xử lý:** thêm `yield result;` hoặc dùng arrow expression đơn giản nếu chỉ có một biểu thức.

### 12.5. Thêm default vào enum switch mà không cần

`default` có thể khiến compiler không cảnh báo khi enum thêm hằng mới.

**Cách xử lý:** khi muốn xử lý tường minh mọi enum constant, liệt kê tất cả và để compiler phát hiện khi source cần cập nhật.

### 12.6. Quên null

`instanceof` với null cho kết quả false; switch với null ném `NullPointerException` trong Java 17 stable.

**Cách xử lý:** xác định null có hợp lệ không, rồi xử lý trước khi phân nhánh.

### 12.7. Dùng instanceof với generic parameterized type

`instanceof List<String>` không hợp lệ do type erasure.

**Cách xử lý:** kiểm tra `List<?>`, sau đó xác thực từng phần tử.

### 12.8. Dùng pattern switch preview như tính năng stable Java 17

Type pattern trong switch không thuộc Java 17 stable.

**Cách xử lý:** với target Java 17, dùng `instanceof` pattern matching. Chỉ dùng pattern switch khi nâng runtime/compiler lên phiên bản đã chuẩn hóa tính năng đó và codebase chủ đích theo phiên bản mới.

## 13. Bài tập thực hành

### Bài 1 — Viết lại instanceof truyền thống

Cho biến `Object value`. Viết lại chuỗi kiểm tra `instanceof` và ép kiểu cho `String`, `Integer`, `Boolean` bằng pattern matching for `instanceof`. Mỗi nhánh trả về một mô tả.

### Bài 2 — Flow scoping

Viết method chỉ chấp nhận chuỗi không rỗng. Dùng pattern variable trong `&&` và negated pattern với early return/throw. Giải thích vì sao không thể dùng pattern variable ở vế phải của một biểu thức `||` trong trường hợp điều kiện có thể bỏ qua việc khởi tạo biến.

### Bài 3 — Switch expression với enum

Tạo enum `DeliveryStatus` gồm `CREATED`, `IN_TRANSIT`, `DELIVERED`, `FAILED`. Viết switch expression trả về thông báo. Thêm một enum constant mới và quan sát compiler yêu cầu cập nhật ở đâu.

### Bài 4 — Kết hợp subtype và enum

Tạo sealed interface `Notification` với ba record `Email`, `Sms`, `Push`. Dùng `instanceof` để phân nhánh theo loại notification và switch expression để xử lý enum `Priority` trong mỗi biến thể.

### Bài 5 — Sealed hierarchy

Tạo sealed interface `Shape` với `Circle`, `Rectangle`, `Triangle`. Viết method tính diện tích bằng chuỗi `instanceof` pattern matching. Thêm subtype mới và giải thích vì sao Java 17 không tự báo thiếu nhánh trong chuỗi if/else.

### Bài 6 — Generic type erasure

Nhận một `Object` có thể là `List<?>`. Dùng pattern matching để kiểm tra list, sau đó chỉ xử lý các phần tử `String`. Giải thích vì sao không thể kiểm tra trực tiếp `List<String>`.

### Bài 7 — Nhận diện preview feature

Đọc ví dụ pattern matching for switch của JDK 17 và so sánh với cú pháp stable của Java 17. Giải thích vì sao source cần chạy trên Java 17 không nên phụ thuộc vào preview switch pattern.

## 14. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Viết `value instanceof String text` và sử dụng biến pattern trong đúng phạm vi.
2. Giải thích flow scoping với `if`, `&&`, `||`, phủ định và early return.
3. Dùng switch expression trả về giá trị với enum, String hoặc kiểu số nguyên được hỗ trợ.
4. Viết nhánh switch expression nhiều câu lệnh bằng `yield`.
5. Kết hợp `instanceof`, sealed interface, record và switch expression để xử lý biến thể.
6. Xử lý `null` rõ ràng trước khi switch.
7. Hiểu giới hạn type erasure khi dùng `instanceof` với generic.
8. Phân biệt switch expression stable của Java 17 với pattern matching for switch ở trạng thái preview trong JDK 17.
9. Chọn `instanceof`, switch expression hoặc visitor theo loại dữ liệu và yêu cầu bảo trì.
10. Biên dịch ví dụ bằng `javac --release 17` mà không bật preview.

## 15. Tài liệu chính thức

- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): pattern matching for `instanceof` được chuẩn hóa trong Java 16.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): switch expression được chuẩn hóa trong Java 14.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): sealed classes/interfaces được chuẩn hóa trong Java 17.
- [Java SE 17 Language Specification — Pattern Matching for instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): cú pháp và quy tắc kiểm tra kiểu.
- [Java SE 17 Language Specification — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): switch expression, exhaustiveness và kết quả biểu thức.
- [Java SE 17 Language Specification — Scope of Pattern Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html): phạm vi và flow scoping của pattern variable.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): trạng thái preview của pattern switch trong Java 17; không phải cú pháp stable của release này.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): trạng thái chuẩn hóa ở Java 21 để đối chiếu khi nâng phiên bản.

**Ghi nhớ:** Với Java 17 ổn định, dùng `instanceof` pattern matching để nhận diện subtype, switch expression để xử lý enum/String/mã số và sealed types để giới hạn biến thể. Pattern matching for switch chưa phải tính năng stable của Java 17; đừng đưa cú pháp preview vào code cần chạy ổn định trên JDK 17.
