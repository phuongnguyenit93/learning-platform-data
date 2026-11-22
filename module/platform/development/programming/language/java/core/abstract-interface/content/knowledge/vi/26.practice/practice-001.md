# Xây dựng hợp đồng thanh toán với nhiều cách triển khai

Một hệ thống checkout có thể cho phép thanh toán bằng tiền mặt, thẻ hoặc ví điện tử. Mỗi cách thanh toán có quy trình riêng, nhưng phần còn lại của ứng dụng vẫn cần một cách thống nhất để yêu cầu thanh toán và nhận kết quả. Trong Java, ta có thể dùng một interface làm **hợp đồng thanh toán**, sau đó viết nhiều lớp triển khai hợp đồng đó.

Bài thực hành này xây dựng một ví dụ Java 17+ chạy được. Các lớp thanh toán chỉ mô phỏng kết quả để minh họa thiết kế; chúng không kết nối ngân hàng, ví điện tử hay thực hiện giao dịch thật.

## 1. Xác định hợp đồng trước khi viết các lớp

Trước tiên, xác định những điều mà mọi phương thức thanh toán phải cung cấp:

- Có tên để giao diện hoặc log có thể hiển thị.
- Nhận một yêu cầu thanh toán hợp lệ.
- Trả về một kết quả có cấu trúc thống nhất, bao gồm mã đơn hàng, số tiền, trạng thái và thông điệp.
- Thể hiện kết quả nghiệp vụ như được chấp nhận, bị từ chối hoặc đang chờ xử lý.
- Có cách báo lỗi kỹ thuật nhất quán khi không thể hoàn tất quy trình thanh toán.

Hợp đồng gồm cả chữ ký phương thức và ý nghĩa của chúng. Chỉ có cùng tên và kiểu tham số là chưa đủ: mọi lớp triển khai cũng phải tuân thủ những quy tắc mà bên gọi dựa vào.

Trong ví dụ này, ta dùng ba kiểu dữ liệu:

- `PaymentRequest`: dữ liệu đầu vào, yêu cầu mã đơn hàng không rỗng và số tiền lớn hơn 0.
- `PaymentResult`: kết quả thống nhất cho mọi cách thanh toán.
- `PaymentMethod`: interface quy định tên và thao tác thanh toán.

## 2. Tạo interface PaymentMethod

~~~java
import java.util.Objects;

enum PaymentStatus {
    APPROVED,
    DECLINED,
    PENDING
}

record PaymentRequest(String orderId, long amountVnd) {
    PaymentRequest {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

record PaymentResult(
        String orderId,
        String method,
        long amountVnd,
        PaymentStatus status,
        String message) {
    PaymentResult {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(method, "method");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(message, "message");
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

final class PaymentException extends Exception {
    PaymentException(String message) {
        super(message);
    }

    PaymentException(String message, Throwable cause) {
        super(message, cause);
    }
}

interface PaymentMethod {
    String name();

    PaymentResult pay(PaymentRequest request) throws PaymentException;
}
~~~

Đây là phần khai báo dữ liệu và hợp đồng. `PaymentStatus` phân biệt kết quả nghiệp vụ; `PaymentException` dành cho lỗi kỹ thuật mà phương thức không thể xử lý tại chỗ. Một giao dịch bị từ chối là kết quả nghiệp vụ bình thường, nên có thể biểu diễn bằng `DECLINED` thay vì coi mọi trường hợp đó là lỗi chương trình.

Hợp đồng `PaymentMethod` đặt ra các quy tắc sau:

1. Bên gọi cung cấp một `PaymentRequest` hợp lệ, không phải `null`.
2. `pay` trả về một `PaymentResult` không phải `null`, gắn với đúng mã đơn hàng và số tiền yêu cầu.
3. `APPROVED`, `DECLINED` và `PENDING` là các trạng thái nghiệp vụ có ý nghĩa riêng; không được xem `PENDING` như đã thanh toán thành công.
4. Lỗi kỹ thuật có thể được báo qua `PaymentException`; mọi implementation cần giữ chính sách lỗi nhất quán.
5. `name()` trả về tên không rỗng, có thể dùng để hiển thị hoặc ghi log.

Các quy tắc ngữ nghĩa này quan trọng ngang chữ ký Java. Chúng giúp lớp sử dụng `PaymentMethod` không cần biết từng implementation làm việc bên trong ra sao.

## 3. Tạo nhiều implementation

Mỗi lớp dưới đây thực hiện cùng một hợp đồng nhưng cung cấp tên và thông điệp riêng. Trong ví dụ, tất cả kết quả đều là mô phỏng.

~~~java
import java.util.Objects;

final class CashPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Cash";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(
            request.orderId(),
            name(),
            request.amountVnd(),
            PaymentStatus.APPROVED,
            "Cash payment simulated"
        );
    }
}

final class CardPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(
            request.orderId(),
            name(),
            request.amountVnd(),
            PaymentStatus.APPROVED,
            "Card payment simulated"
        );
    }
}

final class EWalletPayment implements PaymentMethod {
    @Override
    public String name() {
        return "E-wallet";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(
            request.orderId(),
            name(),
            request.amountVnd(),
            PaymentStatus.APPROVED,
            "E-wallet payment simulated"
        );
    }
}
~~~

Cả ba lớp đều dùng `implements PaymentMethod` và cung cấp các phương thức bắt buộc. Mã gọi có thể làm việc với kiểu `PaymentMethod` mà không cần phụ thuộc vào tên lớp cụ thể.

Ví dụ mô phỏng này không kiểm tra hạn mức thẻ, số dư ví hay xác nhận của ngân hàng. Trong hệ thống thật, mỗi implementation sẽ gọi một nhà cung cấp hoặc xử lý một quy trình riêng, đồng thời phải tuân thủ cùng hợp đồng đầu vào, đầu ra và lỗi.

## 4. Để dịch vụ checkout phụ thuộc vào interface

Lớp checkout không cần biết đang dùng tiền mặt, thẻ hay ví điện tử. Nó chỉ cần một `PaymentMethod`.

~~~java
import java.util.Objects;

final class CheckoutService {
    private final PaymentMethod paymentMethod;

    CheckoutService(PaymentMethod paymentMethod) {
        this.paymentMethod =
            Objects.requireNonNull(paymentMethod, "paymentMethod");
    }

    PaymentResult checkout(PaymentRequest request)
            throws PaymentException {
        Objects.requireNonNull(request, "request");
        return paymentMethod.pay(request);
    }
}
~~~

Việc truyền implementation qua constructor được gọi là **dependency injection**. `CheckoutService` không tự tạo `new CardPayment()` bên trong, vì vậy bên gọi có thể chọn cách thanh toán phù hợp khi khởi tạo dịch vụ.

Thiết kế này cũng áp dụng nguyên tắc phụ thuộc vào abstraction: checkout dựa trên hợp đồng ổn định, còn chi tiết thanh toán nằm trong những lớp riêng. Khi cần thêm chuyển khoản ngân hàng, có thể tạo `BankTransferPayment implements PaymentMethod` mà không cần sửa logic checkout, miễn là lớp mới tuân thủ hợp đồng.

## 5. Chương trình hoàn chỉnh có thể chạy

Lưu toàn bộ các khai báo trên cùng với đoạn `main` dưới đây vào một tệp tên **PaymentContractDemo.java**. Để tránh trùng khai báo, khi ghép thành tệp hoàn chỉnh, giữ các import ở đầu tệp một lần và đặt tất cả các kiểu phụ trợ cùng với lớp public trong cùng tệp.

~~~java
import java.util.List;
import java.util.Objects;

enum PaymentStatus {
    APPROVED,
    DECLINED,
    PENDING
}

record PaymentRequest(String orderId, long amountVnd) {
    PaymentRequest {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

record PaymentResult(
        String orderId,
        String method,
        long amountVnd,
        PaymentStatus status,
        String message) {
    PaymentResult {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(method, "method");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(message, "message");
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd must be positive");
        }
    }
}

final class PaymentException extends Exception {
    PaymentException(String message) {
        super(message);
    }

    PaymentException(String message, Throwable cause) {
        super(message, cause);
    }
}

interface PaymentMethod {
    String name();

    PaymentResult pay(PaymentRequest request) throws PaymentException;
}

final class CashPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Cash";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(request.orderId(), name(),
            request.amountVnd(), PaymentStatus.APPROVED,
            "Cash payment simulated");
    }
}

final class CardPayment implements PaymentMethod {
    @Override
    public String name() {
        return "Card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(request.orderId(), name(),
            request.amountVnd(), PaymentStatus.APPROVED,
            "Card payment simulated");
    }
}

final class EWalletPayment implements PaymentMethod {
    @Override
    public String name() {
        return "E-wallet";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        Objects.requireNonNull(request, "request");
        return new PaymentResult(request.orderId(), name(),
            request.amountVnd(), PaymentStatus.APPROVED,
            "E-wallet payment simulated");
    }
}

final class CheckoutService {
    private final PaymentMethod paymentMethod;

    CheckoutService(PaymentMethod paymentMethod) {
        this.paymentMethod =
            Objects.requireNonNull(paymentMethod, "paymentMethod");
    }

    PaymentResult checkout(PaymentRequest request)
            throws PaymentException {
        Objects.requireNonNull(request, "request");
        return paymentMethod.pay(request);
    }
}

public class PaymentContractDemo {
    public static void main(String[] args) throws PaymentException {
        List<PaymentMethod> methods = List.of(
            new CashPayment(),
            new CardPayment(),
            new EWalletPayment()
        );

        for (int i = 0; i < methods.size(); i++) {
            PaymentMethod method = methods.get(i);
            PaymentRequest request =
                new PaymentRequest("DEMO-" + (i + 1), 150_000L);
            CheckoutService checkout = new CheckoutService(method);
            PaymentResult result = checkout.checkout(request);

            System.out.printf(
                "%s | %s | %d | %s | %s%n",
                result.orderId(),
                result.method(),
                result.amountVnd(),
                result.status(),
                result.message()
            );
        }
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
javac PaymentContractDemo.java
java PaymentContractDemo
~~~

Kết quả:

~~~text
DEMO-1 | Cash | 150000 | APPROVED | Cash payment simulated
DEMO-2 | Card | 150000 | APPROVED | Card payment simulated
DEMO-3 | E-wallet | 150000 | APPROVED | E-wallet payment simulated
~~~

Ba đơn hàng demo được tạo riêng để so sánh ba implementation. Đây chỉ là mô phỏng; một ứng dụng thực tế không được thử lần lượt nhiều phương thức trên cùng một đơn hàng theo cách có thể phát sinh nhiều lần thu tiền.

**Lưu ý khi ghép ví dụ:** các mục 2–4 minh họa từng phần để giải thích thiết kế; mục 5 là tệp độc lập hoàn chỉnh. Chỉ biên dịch một phiên bản `PaymentContractDemo.java` có mỗi kiểu được khai báo đúng một lần.

## 6. Vì sao hợp đồng tốt hơn các nhánh if/else rải rác?

Một cách triển khai ban đầu có thể kiểm tra loại thanh toán ở nhiều nơi:

~~~java
if (methodType.equals("CASH")) {
    // Handle cash
} else if (methodType.equals("CARD")) {
    // Handle card
} else if (methodType.equals("WALLET")) {
    // Handle wallet
}
~~~

Khi thêm phương thức mới, các nhánh này có thể phải được cập nhật ở nhiều vị trí. Nếu từng nhánh có quy tắc kết quả hoặc lỗi khác nhau, việc bảo trì sẽ khó hơn.

Với `PaymentMethod`, logic gọi thanh toán chỉ cần gọi `paymentMethod.pay(request)`. Chọn implementation là trách nhiệm của nơi cấu hình ứng dụng, factory hoặc tầng điều phối. Đừng xóa mọi điều kiện nghiệp vụ: điều kiện xác thực, giới hạn rủi ro và quyền sử dụng phương thức vẫn có thể cần thiết. Mục tiêu là tập trung hành vi riêng của mỗi phương thức trong implementation tương ứng.

## 7. Cách kiểm tra một implementation có tuân thủ hợp đồng

Khi viết lớp mới như `BankTransferPayment`, kiểm tra các điều sau:

- Tên phương thức không rỗng và có ý nghĩa.
- Đầu vào hợp lệ được xử lý theo đúng quy tắc đã công bố.
- Kết quả không phải `null`, có đúng mã đơn hàng và số tiền được yêu cầu.
- `APPROVED`, `DECLINED` và `PENDING` được dùng đúng nghĩa; không báo thành công khi chưa có xác nhận.
- Lỗi kỹ thuật tuân thủ chính sách ngoại lệ đã định nghĩa.
- Không làm thay đổi hợp đồng chung bằng một hành vi bất ngờ, chẳng hạn trả số tiền khác mà không ghi rõ quy tắc phí.
- Mã gọi không cần ép kiểu về lớp cụ thể để sử dụng hành vi đã cam kết.

Một bài kiểm tra hữu ích là chạy cùng một bộ kiểm tra hợp đồng cho mọi implementation. Có thể dùng JUnit để kiểm tra các trường hợp đầu vào hợp lệ, đầu vào không hợp lệ, kết quả bị từ chối và lỗi nhà cung cấp. Khi kiểm tra lỗi, phân biệt lỗi đầu vào do người gọi và lỗi kỹ thuật phát sinh trong quá trình xử lý.

## 8. Mở rộng sang thanh toán thực tế

Ví dụ demo giữ kết quả đơn giản để tập trung vào interface. Một tích hợp thanh toán thực tế thường cần thêm các khái niệm sau:

- **Mã giao dịch của nhà cung cấp:** để đối chiếu và hỗ trợ tra soát.
- **Idempotency key:** để việc gửi lại yêu cầu sau timeout không tạo giao dịch trùng. Mã đơn hàng đơn thuần chỉ đủ khi nhà cung cấp và thiết kế của bạn bảo đảm tính duy nhất cho mỗi lần thanh toán.
- **Trạng thái chờ:** có thể nhà cung cấp đã nhận yêu cầu nhưng chưa có kết quả cuối cùng. Khi đó cần truy vấn hoặc nhận webhook; không nên tự chuyển `PENDING` thành `APPROVED`.
- **Timeout và lỗi mạng:** timeout không chứng minh rằng giao dịch thất bại; hệ thống cần xác minh trạng thái trước khi quyết định thử lại.
- **Bảo mật:** không ghi log dữ liệu thẻ nhạy cảm, bảo vệ thông tin xác thực và tuân thủ yêu cầu bảo mật của nhà cung cấp.
- **Phí và tiền tệ:** nếu mỗi phương thức tính phí khác nhau, hợp đồng cần định nghĩa rõ số tiền yêu cầu, phí, tổng tiền bị thu và đơn vị tiền tệ.

Khi các yêu cầu này xuất hiện, hãy mở rộng `PaymentRequest` và `PaymentResult` có chủ đích, rồi cập nhật hợp đồng cùng tất cả implementation. Không nên để mỗi lớp tự hiểu trường dữ liệu theo một nghĩa khác nhau.

## 9. Lỗi thiết kế thường gặp

- **Đặt logic của từng phương thức trong CheckoutService:** làm dịch vụ phụ thuộc vào chi tiết và buộc phải sửa khi thêm cách thanh toán. Hãy để implementation thực hiện hành vi riêng qua interface.
- **Tạo interface chỉ có tên nhưng không có hợp đồng rõ ràng:** chữ ký phương thức cần đi kèm ý nghĩa đầu vào, đầu ra và lỗi.
- **Cho các implementation trả kết quả không nhất quán:** ví dụ lớp này trả `null`, lớp khác trả một kết quả thiếu mã đơn hàng. Bên gọi sẽ phải viết nhiều nhánh phòng vệ và không còn tin được hợp đồng.
- **Dùng exception cho mọi trường hợp bị từ chối:** từ chối thanh toán có thể là kết quả nghiệp vụ bình thường; phân biệt nó với lỗi kỹ thuật.
- **Xem PENDING như thành công:** kết quả chưa xác định không đồng nghĩa tiền đã được thu.
- **Dùng cùng một đơn hàng để chạy thử tất cả phương thức thanh toán thật:** có thể dẫn tới nhiều lần thu tiền. Dùng đơn hàng thử riêng hoặc môi trường sandbox.
- **Cho rằng interface tự bảo đảm tính đúng đắn:** trình biên dịch kiểm tra chữ ký, còn quy tắc nghiệp vụ vẫn cần được thể hiện bằng tài liệu, kiểm thử và cách triển khai.

Điểm cốt lõi của bài thực hành là định nghĩa một hợp đồng ổn định cho thao tác thanh toán, triển khai hợp đồng bằng nhiều lớp độc lập và để dịch vụ checkout làm việc qua kiểu interface. Khi thêm một phương thức mới, ta có thể bổ sung implementation mà vẫn giữ cách gọi chung và những cam kết mà toàn bộ hệ thống dựa vào.