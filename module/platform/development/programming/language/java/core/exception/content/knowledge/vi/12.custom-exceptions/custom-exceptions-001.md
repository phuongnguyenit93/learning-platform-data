# Khi nào cần định nghĩa loại ngoại lệ riêng trong Java?

**Ngoại lệ tùy chỉnh (custom exception)** là một lớp do ứng dụng định nghĩa và kế thừa `Exception`, `RuntimeException` hoặc một lớp ngoại lệ phù hợp khác. Mục tiêu của nó không chỉ là đổi tên một lỗi: một loại ngoại lệ tốt phải biểu đạt **một ý nghĩa thất bại riêng**, giúp caller xử lý đúng, bảo vệ ranh giới abstraction hoặc mang dữ liệu chẩn đoán có cấu trúc.

Ví dụ, hệ thống đặt hàng có thể phân biệt:

- Người gọi truyền `orderId` rỗng: đây là **tham số không hợp lệ**, thường có thể dùng `IllegalArgumentException` có sẵn.
- Đơn hàng chưa ở trạng thái cho phép thanh toán: đây có thể là **lỗi bất biến/trạng thái miền nghiệp vụ** cần một `InvalidOrderStateException` riêng nếu nhiều caller xử lý khác nhau.
- Cổng thanh toán không kết nối được: đây là **lỗi hạ tầng**; tầng nghiệp vụ có thể bọc `IOException` thành `PaymentGatewayUnavailableException` để không làm API công khai phụ thuộc loại lỗi I/O thấp tầng.
- Thẻ bị từ chối theo một quyết định hợp lệ của ngân hàng: nhiều hệ thống nên trả **kết quả nghiệp vụ** như `PaymentDecision.DECLINED` thay vì ném ngoại lệ, vì đây có thể là một kết quả dự kiến của quy trình.

**Không có quy tắc “mỗi thông điệp lỗi cần một class exception”.** Câu hỏi đúng là: *loại lỗi này có cần một hợp đồng xử lý hoặc thông tin riêng mà ngoại lệ hiện có chưa biểu đạt rõ không?*

Bài học thuộc Java Core – Exception, chủ đề **Ngoại lệ tùy chỉnh**, tập trung vào tiêu chí quyết định khi nào nên hoặc không nên tạo loại ngoại lệ riêng; bao gồm checked/unchecked, cấu trúc constructor, cause, dữ liệu lỗi, ranh giới API, thiết kế phân cấp và ví dụ Java 17+ chạy độc lập.

## 1. Ngoại lệ riêng giải quyết vấn đề gì?

Giả sử một phương thức ở tầng thanh toán ném:

~~~java
throw new RuntimeException("Payment gateway unavailable");
~~~

Đây là mảnh mã Java minh họa. Caller nhận được một `RuntimeException` chung chung. Nếu muốn xử lý riêng sự cố cổng thanh toán mà không bắt nhầm các lỗi lập trình khác, caller có thể phải kiểm tra message:

~~~java
catch (RuntimeException e) {
    if (e.getMessage().contains("gateway")) {
        // Thử lại hoặc đưa vào hàng đợi xử lý sau.
    }
}
~~~

Đây là **phản ví dụ về thiết kế**, không phải cách nên áp dụng: `getMessage()` có thể bằng `null` (gây `NullPointerException` khi gọi `contains`), nội dung thông báo có thể thay đổi theo ngôn ngữ hoặc refactor, và việc bắt rộng `RuntimeException` dễ gom cả những lỗi không liên quan.

Nếu lỗi cổng thanh toán có nghĩa riêng và caller cần nhánh xử lý riêng:

~~~java
public final class PaymentGatewayUnavailableException
        extends RuntimeException {
    public PaymentGatewayUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là một **lớp Java độc lập**, có thể lưu trong `PaymentGatewayUnavailableException.java`. Caller có thể bắt theo kiểu cụ thể:

~~~java
catch (PaymentGatewayUnavailableException e) {
    // Chính sách xử lý lỗi cổng thanh toán.
}
~~~

Kiểu lỗi mang ngữ nghĩa ổn định hơn nội dung message. Khi áp dụng kiểu riêng, ứng dụng có thể thêm trường mã lỗi, định danh tác vụ hoặc thuộc tính cần thiết, miễn là không làm lộ thông tin nhạy cảm.

**Lợi ích chính:** chuyển lỗi thành một phần **hợp đồng có kiểu** của API, thay vì bắt người gọi suy luận từ những chuỗi văn bản không ổn định.

## 2. Năm tín hiệu nên cân nhắc tạo custom exception

### 2.1. Caller cần phân biệt lỗi này để xử lý khác

Nếu những tầng gọi cần hành động khác nhau cho các tình huống lỗi, loại exception riêng là một tín hiệu mạnh.

Ví dụ:

| Tình huống | Hành động có thể phù hợp | Có cần kiểu riêng? |
| --- | --- | --- |
| Đơn hàng không ở trạng thái được phép thanh toán | Từ chối thao tác, báo trạng thái hiện tại | Có thể hữu ích nếu là hợp đồng miền |
| Cổng thanh toán tạm thời không sẵn sàng | Retry có giới hạn, cảnh báo hoặc đẩy vào hàng chờ | Có thể hữu ích nếu caller cần nhận diện |
| `age` âm ở hàm đơn giản | Sửa tham số đầu vào | Thường dùng `IllegalArgumentException` |
| Lỗi parser số nguyên | Xử lý `NumberFormatException` trực tiếp khi thích hợp | Không nhất thiết |
| Một thao tác cho ra kết quả `DECLINED` dự kiến | Trả `PaymentDecision` | Thường không cần exception |

Nếu caller **không bao giờ xử lý khác**, loại mới có thể chỉ làm tăng số class mà không đem lại ích lợi.

### 2.2. Có ranh giới abstraction cần bảo vệ

Một module nghiệp vụ không nên bắt mọi caller biết tầng lưu trữ đang dùng tệp, JDBC hay HTTP. Thay vì phơi ra vô số lỗi hạ tầng, module có thể chuyển sang loại lỗi công khai:

~~~java
static Account loadAccount(String accountId)
        throws AccountRepositoryException {
    try {
        return readFromDatabase(accountId);
    } catch (java.sql.SQLException cause) {
        throw new AccountRepositoryException(
                "Không thể tải tài khoản", cause);
    }
}
~~~

Đây là **mã minh họa không độc lập**, giả định `Account`, `AccountRepositoryException` và `readFromDatabase` được khai báo phù hợp.

Ý nghĩa:

- Caller nhận hợp đồng `AccountRepositoryException` ổn định.
- Module có thể thay JDBC bằng API khác mà không buộc caller hiểu toàn bộ chi tiết triển khai.
- `cause` bảo toàn ngoại lệ gốc để điều tra.

Tuy nhiên, không phải tầng nào cũng cần wrapper mới. Nếu một tầng không thêm ngữ cảnh hoặc chính sách xử lý, cứ cho lỗi phù hợp lan truyền có thể rõ ràng hơn.

### 2.3. Lỗi mang dữ liệu cấu trúc có ích cho xử lý

Khi caller cần lấy mã lỗi hoặc thông tin miền một cách **an toàn theo kiểu**, một lớp tùy chỉnh có trường riêng sẽ tốt hơn parsing message.

~~~java
public final class OrderConflictException
        extends IllegalStateException {
    private final String orderId;

    public OrderConflictException(String orderId) {
        super("Order is not in a valid state");
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Đây là lớp Java độc lập nếu lưu trong `OrderConflictException.java`. Caller đọc `getOrderId()` thay vì tách mã đơn hàng từ `getMessage()`.

**Lưu ý riêng tư:** không tự động đưa toàn bộ đơn hàng, thông tin thẻ hoặc dữ liệu người dùng vào exception. Ngoại lệ có thể được ghi vào log hoặc đi qua nhiều tầng. Chỉ giữ các trường thật cần thiết và đã được phép lưu.

### 2.4. Một lỗi thuộc hợp đồng công khai của thư viện

Trong API thư viện hoặc module được nhiều nơi sử dụng, custom exception có thể thể hiện rõ **một tập hợp lỗi mà client được phép dựa vào**.

Ví dụ API:

~~~java
public Receipt issueReceipt(String orderId)
        throws ReceiptGenerationException
~~~

Đây là **chữ ký minh họa**, không phải một chương trình độc lập. Nó cho biết caller cần tính tới một nhóm lỗi phát hành hóa đơn. Nếu điều đó có ý nghĩa với client, `ReceiptGenerationException` có thể là một phần hợp đồng versioning.

Khi đã công khai một kiểu exception, đừng đổi hoặc xóa tùy tiện: mã của bên gọi có thể `catch` kiểu ấy, cấu hình retry dựa theo nó, hoặc gắn trạng thái HTTP dựa trên loại exception.

### 2.5. Muốn phân biệt trạng thái bất thường với lỗi lập trình

Có những lỗi nên được tách rõ khỏi `NullPointerException`, `IndexOutOfBoundsException` hay `IllegalArgumentException` thường gặp trong code vì nguyên nhân và cách khắc phục khác.

Ví dụ `LeaseExpiredException` trong module quản lý quyền truy cập tạm thời có thể có ý nghĩa hơn `IllegalStateException` chung chung, nếu caller được thiết kế để yêu cầu cấp lại lease.

Dù vậy, hãy cẩn thận: **“có tên nghiệp vụ” chưa đủ**. Một hệ thống nhỏ có thể xử lý tốt với ngoại lệ chuẩn cộng message rõ ràng. Chỉ tạo kiểu khi có lợi ích cụ thể về API, phân nhánh hoặc khả năng diễn đạt.

## 3. Trường hợp nên dùng exception chuẩn thay vì tự định nghĩa

JDK đã có một tập hợp ngoại lệ giàu ý nghĩa:

| Ngoại lệ có sẵn | Tình huống thường phù hợp |
| --- | --- |
| `IllegalArgumentException` | Giá trị đối số vi phạm tiền điều kiện |
| `NullPointerException` | Tham chiếu null không được chấp nhận |
| `IllegalStateException` | Trạng thái hiện tại không cho phép thao tác |
| `UnsupportedOperationException` | Thao tác không được triển khai/hỗ trợ |
| `NoSuchElementException` | Không có phần tử theo hợp đồng truy cập |
| `NumberFormatException` | Chuỗi không thể phân tích thành số hợp lệ |
| `IOException` | Thất bại I/O |
| `SQLException` | Lỗi theo API JDBC |

Nếu lỗi là một **vi phạm tiền điều kiện kỹ thuật thông thường**, `IllegalArgumentException` hoặc `IllegalStateException` kèm message rõ nghĩa thường đủ.

Ví dụ:

~~~java
static int positive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "value must be positive");
    }
    return value;
}
~~~

Đây là phương thức Java hợp lệ khi đặt trong một lớp. Không cần `NotPositiveValueException` riêng nếu caller chỉ cần sửa đối số và không phân biệt nhiều lớp lỗi miền.

### Đừng tạo custom exception chỉ để thay chữ trong message

So sánh:

~~~java
throw new IllegalArgumentException("quantity must be > 0");
~~~

và:

~~~java
throw new InvalidQuantityException("quantity must be > 0");
~~~

Đoạn thứ hai giả định một lớp tùy chỉnh tồn tại. Nếu caller vẫn xử lý cả hai bằng đúng một cách và không cần thêm dữ liệu, lớp mới có thể không mang lại giá trị.

Ngoại lệ chuẩn giúp giảm API, giảm code cần duy trì và tận dụng kiến thức chung của lập trình viên Java.

## 4. Exception không phải cách biểu diễn mọi kết quả nghiệp vụ không thuận lợi

Một kết quả **không được chấp nhận** không phải lúc nào cũng là **thất bại bất thường của chương trình**.

Ví dụ dịch vụ thanh toán trả lời thẻ không được chấp nhận. Nếu đó là một kết quả thường thấy của quy trình, kiểu kết quả tường minh có thể dễ dùng hơn:

~~~java
enum PaymentStatus {
    APPROVED, DECLINED
}

record PaymentDecision(PaymentStatus status, String reason) {}
~~~

Đây là hai khai báo Java 17+ có thể nằm trong một lớp. Caller phân nhánh theo `status` mà không cần một cơ chế exception cho kết quả dự kiến.

| Tiêu chí | Trả kết quả tường minh | Ném exception |
| --- | --- | --- |
| Kết quả xảy ra thường xuyên và là một lựa chọn hợp lệ | Thường rõ ràng | Có thể gây cảm giác lỗi bất thường |
| Caller luôn phải xét nhiều nhánh nghiệp vụ | `enum`/`record`/sealed result phù hợp | Dễ khiến nhánh bị bỏ sót nếu unchecked |
| Không thể hoàn tất thao tác do hạ tầng hoặc bất biến sai | Có thể dùng kết quả lỗi theo API | Exception thường phù hợp |
| Cần lan truyền qua nhiều tầng mà không xử lý ngay | Cần trả kết quả qua từng tầng | Exception hỗ trợ lan truyền |
| Muốn truyền nhiều thông tin người dùng phải thấy | Kết quả thường thuận tiện | Cần tránh rò rỉ stack trace nội bộ |

Không có một quy tắc tuyệt đối cho mọi domain. Một API có thể chọn exception cho việc không tìm thấy đối tượng; API khác chọn `Optional.empty()` hoặc một kết quả `NOT_FOUND`. Quan trọng là tính **nhất quán của hợp đồng** và sự phù hợp với hành vi caller.

### Không dùng exception làm đường rẽ thông thường trong vòng lặp

~~~java
try {
    return Integer.parseInt(text);
} catch (NumberFormatException e) {
    return 0;
}
~~~

Đây là mảnh mã minh họa. Nếu yêu cầu chỉ là “thử parse một lần”, cách này có thể hợp lý. Nhưng nếu dữ liệu không hợp lệ xuất hiện liên tục như một trạng thái dự kiến của giao thức, hãy cân nhắc API parse trả trạng thái rõ ràng hoặc kiểm tra định dạng phù hợp thay vì lạm dụng việc tạo exception để điều khiển vòng lặp nóng.

Đừng tối ưu hóa bằng phỏng đoán: quyết định còn phụ thuộc tính đơn giản, độ đúng và phép đo hiệu năng thực tế.

## 5. Chọn checked hay unchecked cho custom exception?

Trước khi tạo một lớp lỗi riêng, cần chọn **hợp đồng mà caller sẽ nhìn thấy**:

| Hướng | Nghĩa vụ lúc biên dịch | Khi cân nhắc |
| --- | --- | --- |
| `extends Exception` (không qua `RuntimeException`) | Caller phải `catch` hoặc khai báo `throws` nếu có thể để checked exception thoát ra | API cố ý yêu cầu người gọi xét một điều kiện thất bại đã công bố |
| `extends RuntimeException` | Caller không bắt buộc `catch` hoặc `throws` | Vi phạm trạng thái/tiền điều kiện, hoặc hợp đồng chủ động dành việc xử lý lỗi cho boundary |

**Có thể phục hồi** không đồng nghĩa **phải checked**: một `NumberFormatException` unchecked vẫn có thể được UI xử lý; một `IOException` checked có thể không phục hồi được. Cần xét tác động lên chữ ký API, việc override và khách hàng sử dụng thư viện. Chọn loại theo trách nhiệm xử lý, không theo cảm giác lỗi “nặng”.

## 6. Định nghĩa constructor: message và cause

Custom exception cần giữ **mô tả dễ hiểu** và **nguyên nhân gốc** khi bọc lỗi từ tầng khác. Tối thiểu, công bố những overload mà caller thực sự cần:

~~~java
public final class RepositoryAccessException extends Exception {
    public RepositoryAccessException(String message) {
        super(message);
    }

    public RepositoryAccessException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là lớp độc lập nếu lưu trong `RepositoryAccessException.java`. Khi bắt `SQLException` rồi chuyển thành `RepositoryAccessException`, hãy dùng constructor `(message, ex)` để `getCause()` giữ đúng **Throwable gốc**. Chỉ nối `ex.getMessage()` vào một câu mới sẽ làm mất chuỗi cause và stack trace của ex.

Java không tự kế thừa constructor từ superclass, vì vậy muốn cho người gọi truyền `cause`, subclass phải cung cấp overload thích hợp. Không cần thêm cả bốn constructor mặc định chỉ để tuân một mẫu máy móc.

## 7. Thêm trường cấu trúc khi có nhu cầu thực tế

Nếu caller cần xử lý theo mã lỗi hoặc truy vấn ID, hãy đưa chúng vào **trường có kiểu**, không yêu cầu caller parse `getMessage()`. Ví dụ:

~~~java
enum OrderFailureCode { ALREADY_PAID, STOCK_INSUFFICIENT }

final class OrderOperationException extends RuntimeException {
    private final OrderFailureCode code;
    private final String orderId;

    OrderOperationException(OrderFailureCode code, String orderId) {
        super("order operation rejected");
        this.code = java.util.Objects.requireNonNull(code);
        this.orderId = java.util.Objects.requireNonNull(orderId);
    }

    OrderFailureCode code() { return code; }
    String orderId() { return orderId; }
}
~~~

Ví dụ khai báo Java 17; các loại có thể đặt ở tệp thích hợp cùng package. Chỉ thêm field nếu nó phục vụ quyết định thực tế của caller hoặc điều tra. Tránh giữ đồng thời ID ở nhiều field, lưu toàn bộ entity mutable hoặc chứa bí mật vào exception. Mã enum và ID có thể được dùng để phân loại/log an toàn theo chính sách; message vẫn là câu chữ diễn giải.

## 8. Ví dụ Java 17+ độc lập: khi nào dùng loại riêng và khi nào không

Chương trình dưới đây cố ý dùng **ba cách biểu diễn thất bại khác nhau**:

1. `IllegalArgumentException` có sẵn cho `orderId` sai.
2. `InvalidOrderStateException` (unchecked, riêng) cho lỗi bất biến trạng thái có ý nghĩa miền và trường `orderId`.
3. `GatewayUnavailableException` (checked, riêng) cho thất bại hạ tầng cần giữ `IOException` làm cause.
4. `PaymentDecision` dưới dạng `record` cho việc thẻ bị từ chối — **một kết quả nghiệp vụ hợp lệ**, không ném exception.

Tạo tệp **`CustomExceptionDecisionDemo.java`**:

~~~java
import java.io.IOException;

public class CustomExceptionDecisionDemo {

    record PaymentDecision(boolean approved, String reason) {}

    static final class InvalidOrderStateException
            extends IllegalStateException {
        private final String orderId;

        InvalidOrderStateException(
                String orderId, String message) {
            super(message);
            this.orderId = orderId;
        }

        String orderId() {
            return orderId;
        }
    }

    static final class GatewayUnavailableException
            extends Exception {
        private final String code;

        GatewayUnavailableException(
                String code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        show("O-1", true, true, true);
        show("O-2", true, false, true);
        show("O-3", false, true, true);
        show("O-4", true, true, false);

        try {
            charge("", true, true, true);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "invalid argument: " + e.getMessage());
        } catch (GatewayUnavailableException e) {
            System.out.println("unexpected gateway error");
        }
    }

    static void show(
            String orderId,
            boolean ready,
            boolean approved,
            boolean gatewayOnline) {
        try {
            PaymentDecision decision =
                    charge(orderId, ready, approved, gatewayOnline);

            String status = decision.approved()
                    ? "APPROVED"
                    : "DECLINED";
            System.out.println(
                    orderId + " decision=" + status
                            + " reason=" + decision.reason());
        } catch (InvalidOrderStateException e) {
            System.out.println(
                    orderId + " state-error=" + e.getMessage()
                            + " order=" + e.orderId());
        } catch (GatewayUnavailableException e) {
            System.out.println(
                    orderId + " gateway-error=" + e.code());
            System.out.println(
                    "cause=" + e.getCause().getClass().getSimpleName()
                            + ": " + e.getCause().getMessage());
        }
    }

    static PaymentDecision charge(
            String orderId,
            boolean ready,
            boolean approved,
            boolean gatewayOnline)
            throws GatewayUnavailableException {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        if (!ready) {
            throw new InvalidOrderStateException(
                    orderId, "order is not ready");
        }

        try {
            callGateway(gatewayOnline);
        } catch (IOException cause) {
            throw new GatewayUnavailableException(
                    "GATEWAY_OFFLINE",
                    "payment gateway unavailable",
                    cause);
        }

        if (!approved) {
            return new PaymentDecision(false, "card declined");
        }

        return new PaymentDecision(true, "accepted");
    }

    static void callGateway(boolean online) throws IOException {
        if (!online) {
            throw new IOException("connection refused");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac CustomExceptionDecisionDemo.java
java CustomExceptionDecisionDemo
~~~

**Stdout chính xác:**

~~~text
O-1 decision=APPROVED reason=accepted
O-2 decision=DECLINED reason=card declined
O-3 state-error=order is not ready order=O-3
O-4 gateway-error=GATEWAY_OFFLINE
cause=IOException: connection refused
invalid argument: orderId must not be blank
~~~

### Lần theo luồng thành công

`show("O-1", true, true, true)` gọi `charge` với tham số hợp lệ, đơn hàng sẵn sàng và gateway trực tuyến. `callGateway` không ném lỗi; `charge` trả `PaymentDecision(true, "accepted")`. Caller in `APPROVED`.

### Từ chối thẻ: không tạo exception tùy chỉnh

`show("O-2", true, false, true)` vẫn gọi gateway thành công. Quyết định nghiệp vụ là `DECLINED`, nên `charge` trả `PaymentDecision(false, "card declined")`. Đây là ví dụ quan trọng rằng **không phải mọi kết quả không thành công đều cần ngoại lệ**.

Nếu hệ thống có quy định khác, từ chối thanh toán có thể được biểu diễn bằng một kiểu kết quả đa dạng hơn; mục tiêu là người gọi thấy rõ đây là một trạng thái **được dự liệu**.

### Vi phạm bất biến: custom unchecked exception

`show("O-3", false, true, true)` gặp trạng thái đơn hàng chưa sẵn sàng. `charge` ném `InvalidOrderStateException` chứa mã đơn hàng riêng. `show` bắt đúng loại lỗi này và đọc `orderId()` mà không phân tích message.

`InvalidOrderStateException extends IllegalStateException` là một lựa chọn hợp lý nếu lỗi này **thực sự là tình huống trạng thái không cho phép thao tác** và nhiều tầng xử lý cần nhận diện nó. Trong ứng dụng quá nhỏ, `IllegalStateException` có sẵn cũng có thể đủ.

### Lỗi hạ tầng: custom checked exception và cause

`show("O-4", true, true, false)` khiến `callGateway` ném `IOException("connection refused")`. `charge` bắt lỗi rồi bọc thành `GatewayUnavailableException` chứa:

- `code = "GATEWAY_OFFLINE"` làm mã phân loại ổn định cho caller;
- `message = "payment gateway unavailable"` mô tả hoạt động tầng thanh toán;
- `cause` là chính `IOException` gốc.

Vì `GatewayUnavailableException extends Exception`, `charge` khai báo `throws GatewayUnavailableException`. Caller buộc xử lý hoặc chuyển tiếp loại checked exception đó theo hợp đồng.

### Tham số trống: ngoại lệ chuẩn là đủ

`charge("", ...)` ném `IllegalArgumentException` vì `orderId` vi phạm tiền điều kiện; ví dụ không tạo `BlankOrderIdException` riêng. Đây là lựa chọn đơn giản, rõ ràng và phù hợp khi caller chỉ cần sửa dữ liệu đầu vào.

**Lưu ý:** Chương trình mô phỏng logic; `boolean approved` và `boolean gatewayOnline` là các đầu vào giả lập, không phải giao thức thanh toán thật. Không dùng ví dụ này để suy ra cách triển khai bảo mật, chống trùng giao dịch hoặc chính sách retry của một hệ thống thanh toán thực tế.

## 9. Thiết kế phân cấp exception riêng: đơn giản trước

Một base class như `BillingException extends Exception` có ích nếu caller thực sự muốn `catch (BillingException)` cho cả một nhóm lỗi. Khi caller cần hai hành động khác nhau, có thể tạo subtype như `PaymentDeclinedException` và `PaymentProviderUnavailableException`, nếu chúng phù hợp với cùng họ.

Nhưng **không tạo cây sâu chỉ để mô phỏng sơ đồ hệ thống**. Nếu mọi lỗi đều được xử lý giống nhau, một exception có mã lý do typed có thể phù hợp hơn hàng chục subtype. Caller nên phân nhánh theo **hành động có thể thực hiện**, không theo tên driver, HTTP client hay database nội bộ. Chi tiết hạ tầng nên giữ qua `cause` khi chuyển abstraction.

## 10. Thiết kế checked exception và khả năng tương thích API

Một custom checked exception trở thành phần có ảnh hưởng đáng kể tới mã gọi:

~~~java
public Receipt generate(String orderId)
        throws ReceiptGenerationException
~~~

Đây là một chữ ký API minh họa. Bên gọi phải chọn `try/catch` hoặc khai báo `throws`. Nếu thêm một checked exception mới vào chữ ký công khai, source code của client có thể cần thay đổi.

Những cân nhắc:

- Checked exception có giúp caller **thật sự** xử lý hoặc phục hồi không?
- Nó mô tả một loại lỗi có thể dự kiến từ tác vụ hay chỉ lỗi lập trình?
- Có khả năng đổi hạ tầng bên dưới nhưng giữ hợp đồng không?
- Việc bắt/khai báo lặp qua nhiều tầng có làm API phức tạp không?
- Một kết quả kiểu `Result`/`Optional` có rõ nghĩa hơn cho trạng thái thiếu dữ liệu dự kiến không?

Khi đã tạo API công khai, tài liệu hóa **khi nào ném ngoại lệ, caller có thể làm gì và ngoại lệ có giữ cause hay không**. Không đơn thuần công bố tên kiểu rồi để người dùng đoán.

### `throws` không có nghĩa lần nào cũng thất bại

Phương thức:

~~~java
static String readConfig(boolean available)
        throws java.io.IOException {
    if (!available) {
        throw new java.io.IOException("unavailable");
    }
    return "ready";
}
~~~

Đây là phương thức Java hợp lệ trong lớp. `throws IOException` là khai báo khả năng ném checked exception theo hợp đồng. Với `readConfig(true)`, kết quả bình thường là `"ready"`.

Điều tương tự áp dụng khi custom checked exception xuất hiện ở `throws`: khai báo không tự làm ngoại lệ xảy ra; chỉ những đường thực thi thực sự ném nó mới kết thúc bất thường.

## 11. Khi dùng unchecked exception riêng, caller có thể bỏ qua không?

Với custom unchecked exception, compiler không bắt buộc caller viết `catch` hoặc `throws`. Nhưng điều đó không biến lỗi thành sự kiện vô hại.

~~~java
static void verifyState(boolean ready) {
    if (!ready) {
        throw new InvalidOrderStateException(
                "O-7", "order is not ready");
    }
}
~~~

Đây là phương thức minh họa sử dụng lớp lồng trong ví dụ chạy được; nếu viết ở ngoài cần truy cập đúng lớp. Khi `ready = false`, ngoại lệ vẫn ném ra và có thể làm request hoặc tác vụ thất bại nếu không có handler.

Cần có một tầng biên phù hợp để xử lý, chẳng hạn chuyển lỗi miền thành HTTP 409 theo chính sách API, báo lỗi lệnh CLI, rollback transaction, hoặc ghi log có kiểm soát.

**Không bắt `RuntimeException` hoặc `Exception` rộng khắp chỉ để ứng dụng “không chết”.** Làm thế có thể che lỗi lập trình và tiếp tục xử lý ở trạng thái không còn đáng tin cậy. Chỉ bắt ở những ranh giới có trách nhiệm cụ thể.

## 12. Đừng phân loại retry chỉ từ tên ngoại lệ

Một loại lỗi riêng có thể hỗ trợ phân loại retry, nhưng “lỗi mạng” không tự động đồng nghĩa **được retry an toàn**.

Ví dụ một request thanh toán có thể đã được phía nhà cung cấp xử lý, sau đó kết nối đứt trước khi nhận phản hồi. Thử lại bừa bãi có thể tạo giao dịch trùng.

Khi thiết kế ngoại lệ liên quan đến hạ tầng, cần phân biệt:

- Có thể xác định thao tác **chưa** được thực thi ở phía dịch vụ hay không?
- Tác vụ có **idempotent** không?
- Có idempotency key hoặc cơ chế deduplication không?
- Có giới hạn số lần thử, backoff và timeout hợp lý không?
- Có mã lỗi cấu trúc hoặc metadata nào chỉ ra retryable theo hợp đồng không?

Một tên `GatewayUnavailableException` chỉ nói **loại thất bại**, không đủ để xác nhận một thao tác viết dữ liệu có thể gọi lại an toàn. Nếu chính sách retry là quan trọng, hãy thiết kế nó độc lập hoặc thông qua dữ liệu được hợp đồng xác nhận.

## 13. Khi nào không nên phân cấp theo từng mã lỗi?

Một hệ thống có hàng chục mã thất bại không nhất thiết cần hàng chục class `Exception`. Có thể dùng một kiểu exception cho một nhóm ngữ nghĩa, kèm enum mã lỗi:

~~~java
enum ImportFailureCode {
    INVALID_FORMAT,
    UNSUPPORTED_VERSION,
    SOURCE_UNAVAILABLE
}

final class ImportException extends Exception {
    private final ImportFailureCode code;

    ImportException(
            ImportFailureCode code,
            String message,
            Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    ImportFailureCode code() {
        return code;
    }
}
~~~

Đây là các khai báo Java 17+ hợp lệ trong cùng package hoặc lớp bao thích hợp.

Giải pháp này có thể phù hợp nếu caller xử lý chung nhóm lỗi nhập dữ liệu, nhưng cần mã lỗi chi tiết để hiển thị hoặc ghi nhận. Ngược lại, nếu một vài mã có cách khôi phục rất khác biệt và được bắt trực tiếp ở nhiều nơi, subtype riêng có thể rõ hơn.

### Trade-off: kiểu riêng hay enum mã lỗi?

| Cách tiếp cận | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Một subtype riêng mỗi tình huống | `catch` theo kiểu, rõ ngữ nghĩa, IDE dễ khám phá | Nhiều class, tăng API surface |
| Một nhóm exception + mã lỗi enum | Ít class, dữ liệu mã lỗi ổn định | Caller có thể cần `switch` theo mã |
| Exception chuẩn + message | Đơn giản, ít boilerplate | Ít ngữ nghĩa miền cho machine |
| Kết quả nghiệp vụ có trạng thái | Rõ nhánh dự kiến và có kiểu dữ liệu | Phải truyền kết quả qua các tầng gọi |

Không có lựa chọn tối ưu chung cho mọi dự án. Bắt đầu bằng cấu trúc đơn giản, tăng số kiểu khi hợp đồng và nhu cầu thật xuất hiện.

## 14. Cause và suppressed exceptions trong custom exception

Một custom exception không nên làm mất nguyên nhân gốc khi bọc lỗi:

~~~java
catch (java.io.IOException cause) {
    throw new GatewayUnavailableException(
            "GATEWAY_OFFLINE",
            "gateway unavailable",
            cause);
}
~~~

Đây là đoạn minh họa trong lớp có thể truy cập `GatewayUnavailableException`. Constructor của lớp riêng gọi `super(message, cause)`, nhờ đó `getCause()` trả `IOException` gốc.

### Cause khác suppressed

- `getCause()`: một ngoại lệ làm **nguyên nhân trực tiếp** của lỗi ngoài.
- `getSuppressed()`: các ngoại lệ phụ không nên thay thế lỗi chính, thường gặp khi đóng tài nguyên trong try-with-resources.

Ví dụ:

~~~java
Exception main = new Exception(
        "work failed",
        new java.io.IOException("read failed"));

main.addSuppressed(new java.io.IOException("close failed"));
~~~

Đây là mảnh mã minh họa. Cause là `"read failed"`, suppressed exception là `"close failed"`. Không phải cả hai đều là những mắt xích `getCause()` liên tiếp.

### Chú ý constructor và lớp kế thừa

Nếu custom exception không định nghĩa overload có cause, bạn có thể cân nhắc `initCause(...)` khi lớp cho phép và cause chưa được khởi tạo. Nhưng với mã mới, thường nên **tạo constructor nhận cause ngay từ đầu**. Constructor không được kế thừa tự động.

## 15. Message, mã lỗi và dữ liệu nhạy cảm

Exception thường xuất hiện trong log, tracing và báo lỗi vận hành. Vì vậy, các trường dữ liệu của custom exception phải có chính sách rõ.

Nên:

- Đặt message mô tả **thao tác và điều kiện thất bại**, không chỉ `"error occurred"`.
- Dùng mã lỗi ổn định cho nhánh xử lý; tránh parse message.
- Giữ cause khi chuyển abstraction để phục vụ điều tra.
- Chỉ giữ metadata cần thiết (ví dụ mã tác vụ nội bộ không nhạy cảm).
- Phân biệt message kỹ thuật trong log với thông điệp cho người dùng.

Tránh:

- Lưu mật khẩu, access token, chuỗi kết nối nguyên vẹn hoặc dữ liệu thẻ.
- Gắn cả request/body chứa dữ liệu nhạy cảm vào exception.
- Dùng `getMessage()` như giao thức máy-máy ổn định.
- Trả thẳng `printStackTrace()` hoặc toàn bộ chain ra API công khai.

Một kiểu ngoại lệ tốt còn phải phù hợp với chiến lược observability và bảo mật của ứng dụng.

## 16. Lớp ngoại lệ có cần `serialVersionUID`?

`Throwable` triển khai `Serializable`, vì vậy một custom exception có thể nhận cảnh báo IDE liên quan tới `serialVersionUID`. **Không phải mọi exception đều cần cam kết định dạng serialization.** Nếu hệ thống thực sự lưu hoặc trao đổi Java-serialized Throwable giữa các phiên bản, hãy xác định UID, tương thích class/field và kiểm thử dữ liệu cũ đọc bằng phiên bản mới; chỉ thêm `serialVersionUID = 1L` không bảo đảm tương thích.

Với HTTP/message queue/public API, thường nên công bố **DTO lỗi có schema, mã lỗi và context được kiểm soát** thay vì serialize nguyên đồ thị Throwable, vốn có thể mang cause, suppressed và thông tin nhạy cảm.

## 17. Có nên đưa mọi lỗi dưới một `BaseApplicationException`?

Một lớp cha chung có thể hữu ích khi framework hoặc ứng dụng cần handler biên:

~~~java
public class ApplicationException extends RuntimeException {
    public ApplicationException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Nhưng nếu mọi lỗi đều kế thừa nó, caller bắt `ApplicationException` sẽ nhận một tập hợp lỗi rất rộng, không chắc có một cách phục hồi chung. Một phân cấp lớn cũng dễ trở thành nơi chứa mọi mã lỗi không liên quan.

**Một base exception chỉ có ích nếu nó thực sự biểu diễn một hợp đồng chung.** Ví dụ một module billing có nhóm lỗi có cùng cơ chế ghi nhận hoặc ánh xạ lỗi ở tầng biên. Không cần tạo base exception cho từng dự án mới chỉ để tuân theo một khuôn OOP.

Nếu các loại ngoại lệ ở các module hoàn toàn khác nhau, dùng các loại JDK có sẵn hoặc các nhóm nhỏ độc lập có thể dễ bảo trì hơn.

## 18. Kiểm thử custom exception

Một custom exception nên được kiểm thử ở **hai mức**.

### Mức lớp: constructor và metadata

Kiểm tra:

- `getMessage()` nhận đúng thông điệp.
- `getCause()` giữ **chính đối tượng cause** (dùng `==` hoặc `assertSame` trong framework test).
- Getter metadata như `code()` hoặc `orderId()` trả đúng giá trị.
- Kiểu checked/unchecked phù hợp quan hệ kế thừa.
- Có hay không khả năng làm lộ dữ liệu không mong muốn qua message.

Đoạn kiểm tra đơn giản không cần framework:

~~~java
java.io.IOException root =
        new java.io.IOException("unavailable");

GatewayUnavailableException e =
        new GatewayUnavailableException(
                "GATEWAY_OFFLINE", "gateway down", root);

if (e.getCause() != root) {
    throw new AssertionError("cause was lost");
}
if (!"GATEWAY_OFFLINE".equals(e.code())) {
    throw new AssertionError("wrong code");
}
~~~

Đây là mảnh mã kiểm tra có thể đặt trong lớp chứa `GatewayUnavailableException` của ví dụ đầy đủ.

### Mức hành vi: đúng tình huống thì ném đúng loại

Ví dụ:

- `charge` với `orderId` rỗng phải ném `IllegalArgumentException`.
- `charge` với trạng thái không sẵn sàng phải ném `InvalidOrderStateException`.
- `charge` với gateway offline phải ném `GatewayUnavailableException` và giữ `IOException` làm cause.
- `charge` với thẻ bị từ chối hợp lệ phải **trả kết quả `DECLINED`**, không ném exception.

Kiểm thử theo kiểu và dữ liệu cấu trúc tốt hơn kiểm thử phụ thuộc toàn bộ stack trace, số dòng mã nguồn hoặc format `printStackTrace()`.

## 19. Những sai lầm phổ biến

### Sai lầm 1 — Một loại exception cho mỗi câu message

Tạo nhiều class chỉ khác lời thông báo khiến API phình to mà không có lợi ích xử lý thực tế.

### Sai lầm 2 — Bắt `RuntimeException` rồi so sánh `getMessage()`

Message không ổn định và có thể null. Dùng kiểu lỗi cụ thể hoặc mã lỗi có cấu trúc nếu caller thật sự cần phân nhánh.

### Sai lầm 3 — Tạo custom exception cho mọi đầu vào sai

Các lỗi tiền điều kiện đơn giản thường đã có `IllegalArgumentException` hoặc `IllegalStateException`. Chỉ tạo loại riêng khi có hợp đồng miền rõ ràng.

### Sai lầm 4 — Dùng exception cho mọi kết quả từ chối

Nếu từ chối là một kết quả nghiệp vụ dự kiến, kiểu kết quả tường minh có thể phù hợp hơn.

### Sai lầm 5 — Chọn checked vì lỗi “nghiêm trọng” và unchecked vì lỗi “nhẹ”

Phân loại checked/unchecked liên quan hợp đồng compile-time, không phải thang đo độ nghiêm trọng.

### Sai lầm 6 — Quên truyền cause trong constructor

`super(message)` không tự bảo toàn cause. Dùng `super(message, cause)` khi bọc ngoại lệ tầng thấp.

### Sai lầm 7 — Quên khai báo `throws` cho custom checked

Lớp kế thừa `Exception` (không phải `RuntimeException`) thường là checked. Phương thức ném nó phải bắt hoặc khai báo; caller cũng vậy theo quy tắc Java.

### Sai lầm 8 — Tạo cây kế thừa sâu không có người dùng

Phân cấp quá chi tiết tăng phụ thuộc và tạo gánh nặng bảo trì. Chọn số lớp đúng nhu cầu phân nhánh thực sự.

### Sai lầm 9 — Làm lộ hạ tầng trong hợp đồng nghiệp vụ

Trả trực tiếp `SQLException` hoặc `IOException` ở mọi API cấp cao có thể khiến caller phụ thuộc vào công nghệ hiện tại; cân nhắc bọc ở ranh giới module khi có ích.

### Sai lầm 10 — Bọc mọi lỗi ở mọi tầng

Ngoại lệ có chuỗi wrapper dài nhưng không thêm thông tin khiến log khó đọc. Chỉ bọc khi cần đổi abstraction hoặc bổ sung ngữ cảnh.

### Sai lầm 11 — Giả định tên exception quyết định retry an toàn

Lỗi gateway có thể xuất hiện sau khi một yêu cầu ghi đã được thực thi. Retry còn cần idempotency, timeout, backoff và hợp đồng nhà cung cấp.

### Sai lầm 12 — Lạm dụng `catch (Exception)` hoặc `catch (Throwable)`

Bắt quá rộng có thể che lỗi lập trình hoặc các `Error` nghiêm trọng. Chỉ bắt ở tầng có trách nhiệm và chiến lược xử lý thích hợp.

### Sai lầm 13 — Dùng message như mã lỗi ổn định

Đổi cách diễn đạt message có thể làm sai logic. Tách code hoặc subtype khỏi message khi cần xử lý tự động.

### Sai lầm 14 — Thêm trường dữ liệu nhạy cảm vào exception

Lỗi có thể được ghi log, in stack trace hoặc chuyển qua hệ thống giám sát; tránh để lộ thông tin bí mật.

### Sai lầm 15 — Tự bật/tắt stack trace để “tối ưu” mà không đo đạc

Một số constructor nâng cao có thể hạn chế thu thập stack trace hoặc suppressed exceptions, nhưng đó là đánh đổi khả năng chẩn đoán. Đừng biến nó thành mặc định cho custom exception thông thường.

### Sai lầm 16 — Nghĩ mọi constructor của `Exception` tự truyền xuống lớp con

Constructor **không được kế thừa**. Muốn public overload nào thì custom exception phải tự định nghĩa overload đó.

## 20. Checklist trước khi tạo một loại ngoại lệ riêng

Hãy tự trả lời những câu hỏi sau:

1. **Đây thực sự là trạng thái bất thường hay chỉ kết quả dự kiến?** Có nên trả enum/record/result thay vì ném?
2. **JDK đã có loại ngoại lệ diễn đạt đúng chưa?** `IllegalArgumentException`, `IllegalStateException`, `IOException`... có đủ không?
3. **Caller cần bắt loại này riêng không?** Nếu có, họ sẽ hành động khác thế nào?
4. **Có ranh giới abstraction cần bảo vệ không?** Loại riêng có giúp module không phụ thuộc hạ tầng không?
5. **Checked hay unchecked?** Quy tắc biên dịch có phù hợp cách client cần phục hồi?
6. **Có cần metadata có cấu trúc không?** Mã lỗi/trạng thái/ID an toàn có thật sự được dùng không?
7. **Cause được giữ lại chưa?** Khi bọc lỗi, constructor có `super(message, cause)` không?
8. **Có đơn giản hơn không?** Một class kèm enum code, loại chuẩn hoặc kết quả tường minh có rõ hơn nhiều subclass không?
9. **Có chính sách log/API bảo vệ thông tin không?** Message và cause có thể chứa dữ liệu nhạy cảm.
10. **Có test theo loại, message cần thiết, cause và metadata không?** Thay vì kiểm tra chuỗi stack trace dễ thay đổi.

Nếu các câu trả lời cho thấy loại lỗi mới sẽ **thay đổi cách caller hiểu và xử lý thất bại**, custom exception có thể là một lựa chọn tốt. Nếu không, thường nên bắt đầu với loại chuẩn hoặc dữ liệu kết quả.

## 21. Bài tập tự kiểm tra

1. Khi nào một `IllegalArgumentException` có sẵn đủ tốt hơn tạo `InvalidAgeException`?
2. Exception riêng có lợi ích gì hơn so sánh chuỗi `getMessage()`?
3. Lỗi “thẻ bị từ chối” có bắt buộc ném exception không?
4. Vì sao lỗi trạng thái đơn hàng có thể cần một subtype của `IllegalStateException`?
5. Khi nào nên bọc `IOException` bằng exception ở tầng nghiệp vụ?
6. `getCause()` giúp gì khi tạo wrapper?
7. Nếu chỉ dùng `super(message)`, thông tin cause có tự được giữ không?
8. Nếu custom exception kế thừa `Exception` nhưng không phải `RuntimeException` thì nghĩa vụ checked thế nào?
9. Một exception kế thừa `RuntimeException` có phải vì thế mà không thể làm request thất bại không?
10. Custom exception có bắt buộc phải có constructor không tham số không?
11. Nếu caller xử lý 12 mã lỗi giống nhau, có nhất thiết tạo 12 class không?
12. Khi nào một enum mã lỗi trong exception hữu ích?
13. Mã lỗi và message khác nhau ra sao về độ ổn định?
14. Có nên kế thừa `Throwable` trực tiếp cho ngoại lệ nghiệp vụ thông thường không?
15. Vì sao không nên dùng `Error` làm lớp cha của lỗi nghiệp vụ thông thường?
16. Custom exception có thể giữ trường `orderId` không? Nên giới hạn dữ liệu đó thế nào?
17. Vì sao tên `GatewayUnavailableException` chưa đủ để quyết định retry một lệnh thanh toán?
18. Tạo subtype riêng cho từng tầng ứng dụng có luôn làm chain dễ hiểu hơn không?
19. Khi thêm custom checked exception mới vào public API, client có thể phải thay đổi gì?
20. `serialVersionUID` có bắt buộc để `throw/catch` hoạt động không?
21. Cách kiểm thử constructor có bảo toàn cause chính xác là gì?
22. Khi nào caller nên xử lý kết quả `DECLINED` như một giá trị thay vì `catch`?
23. `catch (Throwable)` có phải lựa chọn mặc định để xử lý mọi custom exception không?
24. Exception riêng có thể giúp che chi tiết JDBC khi module chuyển sang hạ tầng khác như thế nào?
25. Nêu ba câu hỏi quan trọng nhất trước khi tạo một lớp exception mới.

### Đáp án gợi ý

1. Khi chỉ là vi phạm đối số thông thường, không có nhánh xử lý miền riêng.
2. Caller phân nhánh theo kiểu ổn định, dễ đọc và an toàn hơn message.
3. Không; có thể biểu diễn bằng kết quả nghiệp vụ tường minh.
4. Khi đó là một bất biến miền cần nhận diện và xử lý riêng.
5. Khi ranh giới API cần đổi abstraction hoặc bổ sung ngữ cảnh có ích.
6. Giữ đối tượng nguyên nhân gốc và thông tin chẩn đoán của nó.
7. Không; nên gọi `super(message, cause)` nếu muốn giữ cause.
8. Phương thức/caller phải bắt hoặc khai báo theo quy tắc checked exceptions.
9. Không; unchecked vẫn được ném và có thể lan truyền làm thao tác thất bại.
10. Không; chỉ tạo overload cần cho hợp đồng.
11. Không; một nhóm exception kèm enum code có thể rõ hơn.
12. Khi máy phải phân loại lỗi mà không parsing message.
13. Code dành cho hợp đồng xử lý; message dành cho người đọc và có thể thay đổi.
14. Thường không; ưu tiên `Exception`/`RuntimeException` hoặc subtype có nghĩa.
15. `Error` dành cho các lỗi nghiêm trọng của môi trường/VM, không phải hợp đồng thất bại nghiệp vụ thường ngày.
16. Có, nếu cần và an toàn; tránh dữ liệu cá nhân/bí mật quá chi tiết.
17. Vì một lần gọi có thể đã có side effect; retry còn cần idempotency.
18. Không; chain dài không thêm ngữ cảnh có thể khó điều tra hơn.
19. Có thể cần thêm `catch` hoặc `throws` và chính sách xử lý tương ứng.
20. Không; chỉ cân nhắc serialization nếu dự án có yêu cầu.
21. Kiểm tra `getCause() == originalCause` và metadata/message đúng.
22. Khi từ chối là trạng thái dự kiến của giao thức và caller cần xử lý như một nhánh thông thường.
23. Không; bắt quá rộng có thể nuốt `Error` và lỗi không liên quan.
24. Caller chỉ biết exception công khai của module; cause còn giữ thông tin kỹ thuật cho logging.
25. Lỗi có khác biệt ngữ nghĩa/cách xử lý không? Loại chuẩn hoặc result đã đủ chưa? Caller/ranh giới API được lợi gì?

## 22. Ghi nhớ

**Hãy định nghĩa custom exception khi cần một ngữ nghĩa thất bại riêng, một hợp đồng xử lý có kiểu, dữ liệu lỗi cấu trúc hoặc một ranh giới abstraction rõ ràng.** Đừng tạo lớp mới chỉ để thay chuỗi message hay cho mọi trạng thái không thuận lợi. Ưu tiên ngoại lệ chuẩn cho tiền điều kiện đơn giản, kết quả tường minh cho nhánh nghiệp vụ dự kiến, và custom exception khi caller thực sự cần phân biệt. Chọn **checked hoặc unchecked** theo hợp đồng API, giữ **cause** khi bọc lỗi, tránh phân cấp sâu không cần thiết, và kiểm thử cả dữ liệu lẫn hành vi ném/bắt.