# Thiết kế hệ phân cấp Exception theo cách bên gọi cần xử lý

> **Java Core – Exception** · Nhóm: **Ngoại lệ tùy chỉnh (custom exceptions)** · Mục tiêu: thiết kế cây ngoại lệ theo **quyết định xử lý của caller**, không theo tên class nội bộ của hệ thống. Ví dụ chính tương thích **Java 17+**.

## 1. Tư tưởng thiết kế cốt lõi

Một exception có ích không chỉ nói “đã có lỗi gì” mà còn giúp **bên gọi biết nên làm gì tiếp theo**.

Ví dụ trong chức năng thanh toán/đặt hàng, khi giao dịch thất bại, caller có thể cần một trong các hành động khác biệt:

- **Yêu cầu khách hàng sửa đầu vào:** địa chỉ giao hàng thiếu thông tin, dữ liệu không hợp lệ.
- **Thử lại sau theo chính sách an toàn:** dịch vụ thanh toán tạm thời không phản hồi, quá tải.
- **Chuyển kiểm tra thủ công:** giao dịch cần người quản trị xác minh.
- **Báo lỗi kỹ thuật:** ứng dụng vi phạm invariant hoặc có bug, không được coi là lỗi thông thường cần khách sửa.

Những hành động trên là cơ sở để chọn các **nhánh exception**. Một cây ngoại lệ nên thể hiện sự khác nhau có giá trị đối với người xử lý lỗi, thay vì phản ánh mọi lớp công nghệ bên trong.

**Nguyên tắc:** *Nếu hai lỗi bắt buộc caller xử lý giống nhau, chưa chắc chúng cần hai lớp exception khác nhau. Nếu hai lỗi đòi hỏi hai hành động khác nhau và caller phải phân biệt ổn định, đó là tín hiệu mạnh để có hai kiểu riêng hoặc một mã lỗi có cấu trúc rõ ràng.*

### 1.1. Hệ phân cấp đề xuất cho một API Checkout

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── CheckoutException                  ← hợp đồng checked của API
        ├── CorrectionNeededException      ← khách hàng cần sửa dữ liệu
        ├── RetryableCheckoutException     ← lỗi tạm thời, xử lý retry có điều kiện
        └── ManualReviewException          ← chuyển kiểm tra thủ công

java.lang.RuntimeException
└── IllegalStateException                  ← lỗi kỹ thuật, không phải lỗi Checkout dự kiến
~~~

Cây này là **ví dụ mô hình hóa**, không phải bộ exception chuẩn có sẵn trong JDK. Các kiểu Checkout sẽ được định nghĩa đầy đủ trong chương trình runnable ở phần 5.

Caller có thể tổ chức handler dựa trên hành động:

~~~java
try {
    checkout(request);
} catch (CorrectionNeededException ex) {
    askCustomerToFix(ex);
} catch (RetryableCheckoutException ex) {
    scheduleSafeRetry(ex);
} catch (ManualReviewException ex) {
    sendToReviewQueue(ex);
} catch (CheckoutException ex) {
    reportGenericCheckoutFailure(ex);
}
~~~

Đây là **đoạn mã phác họa**, chưa thể chạy độc lập vì các biến, kiểu và phương thức handler là tên tượng trưng. Nó minh họa đúng chủ ý: caller chọn nhánh bằng **khả năng xử lý**, không cần biết tên package chứa gateway hay loại driver mạng.

## 2. Đừng phân cấp chỉ theo nguồn lỗi kỹ thuật

Cách phân loại thuần kỹ thuật thường giống:

~~~text
ServiceException
├── DatabaseException
├── HttpException
├── SocketException
├── JsonException
└── QueueException
~~~

Nếu caller của chức năng đặt hàng không có khả năng xử lý riêng một lỗi database so với một lỗi socket, việc phải catch từng loại chỉ buộc tầng nghiệp vụ biết cấu trúc hạ tầng. Đổi từ JDBC sang HTTP hoặc thay thư viện JSON có thể làm **hợp đồng exception bị thay đổi** dù cách caller phục hồi không đổi.

Ví dụ:

| Nguyên nhân hạ tầng | Ý nghĩa đối với caller | Nhánh lỗi nghiệp vụ khả dĩ |
| --- | --- | --- |
| Gateway trả tín hiệu tạm quá tải | Có thể lên lịch thử lại **nếu an toàn** | `RetryableCheckoutException` |
| Timeout trước khi biết giao dịch đã hoàn tất chưa | Cần đối soát/idempotency trước khi retry | Không tự động suy mọi timeout là retryable |
| Người dùng gửi địa chỉ thiếu trường | Yêu cầu sửa đầu vào | `CorrectionNeededException` |
| Quy tắc gian lận yêu cầu phê duyệt | Đưa vào hàng đợi kiểm tra | `ManualReviewException` |
| Một thao tác trên đối tượng null ngoài hợp đồng | Báo bug/hạ tầng, không giả vờ đã xử lý nghiệp vụ | `NullPointerException` hoặc lỗi kỹ thuật thích hợp |

**Quan trọng:** cùng một loại exception kỹ thuật có thể dẫn tới nhiều quyết định nghiệp vụ, tùy ngữ cảnh. Ví dụ một `IOException` có thể là timeout có khả năng phục hồi, tệp cấu hình bị hỏng cần vận hành can thiệp hoặc lỗi quyền truy cập không nên retry. Vì thế đừng ánh xạ *mọi* `IOException` thành `RetryableCheckoutException` theo thói quen. Phải xác định **ý nghĩa và trạng thái thao tác**.

Ngược lại, hai công nghệ khác nhau có thể gây lỗi cần xử lý giống nhau. Nếu trong cả hai trường hợp caller chỉ có thể đề nghị khách nhập lại thông tin, có thể gom thành cùng nhánh lỗi nghiệp vụ kèm chi tiết có cấu trúc.

## 3. Bắt đầu từ quyết định của caller, không bắt đầu từ extends

Thiết kế tốt bắt đầu bằng **bảng hành động**:

| Câu hỏi caller cần trả lời | Hành động sau khi bắt | Khác biệt type có ích? |
| --- | --- | --- |
| Khách có thể sửa đầu vào không? | Hiển thị lỗi cụ thể, cho nhập lại | Có nếu khác retry/escalate |
| Hệ thống có thể retry an toàn không? | Lên lịch retry có giới hạn và idempotency | Có nếu cần nhánh retry riêng |
| Cần con người kiểm tra không? | Chuyển quy trình xử lý thủ công | Có nếu cách xử lý khác hẳn |
| Đây có phải lỗi lập trình không? | Ghi log, báo động, dừng đúng ranh giới | Nên tách khỏi nhóm lỗi dự kiến |
| Tất cả lỗi chỉ cần trả cùng thông báo? | Dùng handler chung ở boundary | Có thể chỉ cần một lớp + mã lỗi |
| Caller không thể khắc phục được? | Cho lỗi lan hoặc bọc để thêm ngữ cảnh | Không cần tạo subtype vô nghĩa |

Quy trình thực hiện:

1. Viết ra **những phản ứng hợp lệ** mà caller thực sự có thể thực hiện.
2. Gom các tình huống có cùng phản ứng thành một nhóm.
3. Xác định các nhánh cần phân biệt **ở thời điểm biên dịch** (kiểu exception) và các chi tiết chỉ là **dữ liệu** (mã, ID, message).
4. Chọn base exception có ý nghĩa làm hợp đồng chung của API.
5. Chọn chính sách checked/unchecked phù hợp cho từng tầng.
6. Xác định nơi chuyển exception hạ tầng thành exception hợp đồng, giữ nguyên cause.
7. Viết caller demo hoặc test trước để kiểm tra cây exception có thực sự giúp điều khiển logic hay không.

Nếu caller phải viết nhiều câu `instanceof`, đọc chuỗi `getMessage()` hoặc ép kiểu liên tục để xác định nên làm gì, hệ phân cấp hiện tại có thể chưa phản ánh đúng phân loại hành động.

## 4. Checked hay unchecked trong hệ phân cấp custom?

Java có hai nhóm cơ bản:

- **Checked exception**: kế thừa `Exception` nhưng **không** thuộc nhánh `RuntimeException`. Compiler yêu cầu xử lý hoặc khai báo `throws` phù hợp.
- **Unchecked exception**: kế thừa `RuntimeException` hoặc `Error`. Compiler không bắt buộc khai báo trong chữ ký.

Ví dụ dưới đây thiết kế `CheckoutException extends Exception`, vì ba tình huống nghiệp vụ được xem là **kết quả thất bại dự kiến** mà caller của API nên có chính sách. Chữ ký:

~~~java
static String checkout(String scenario) throws CheckoutException
~~~

buộc bên gọi của method phải xử lý hoặc khai báo exception checked theo quy tắc Java.

Điều đó **không có nghĩa mọi lỗi nghiệp vụ luôn phải checked**. Một thư viện có thể chọn unchecked theo chính sách API, đặc biệt nếu tầng gọi không thể phục hồi trực tiếp hoặc framework mong cơ chế propagation tự do. Khi quyết định, xét:

- Caller **có thể và thường phải** phản ứng một cách hữu ích không?
- Có hợp lý khi buộc mọi caller khai báo/bắt nhóm này không?
- Thay đổi API trong tương lai có làm người dùng mã nguồn phải sửa hàng loạt không?
- Hệ thống có tầng boundary dùng thông tin lỗi để chuyển thành HTTP response, job retry hoặc trạng thái giao dịch không?

**Không dùng `Error` làm base cho lỗi nghiệp vụ.** `Error` thuộc nhánh dành cho các tình huống nghiêm trọng mà ứng dụng thường không kỳ vọng khôi phục. Cũng không nên custom exception trực tiếp từ `Throwable` nếu không có lý do cực kỳ đặc biệt: như vậy dễ tạo nhóm không được các handler `catch (Exception)` thông thường bao phủ.

## 5. Chương trình Java 17 hoàn chỉnh: caller chọn cách xử lý

Lưu mã thành tệp **`CallerOrientedExceptionsDemo.java`**. Để chương trình chạy trong một file, các exception được khai báo là **public static nested classes**. Trong thư viện thực tế, các exception public thường được đặt trong những file riêng để tạo API rõ ràng.

~~~java
import java.io.IOException;

public class CallerOrientedExceptionsDemo {
    public static abstract class CheckoutException extends Exception {
        private static final long serialVersionUID = 1L;

        protected CheckoutException(String message) {
            super(message);
        }

        protected CheckoutException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class CorrectionNeededException
            extends CheckoutException {
        private static final long serialVersionUID = 1L;

        public CorrectionNeededException(String message) {
            super(message);
        }
    }

    public static final class RetryableCheckoutException
            extends CheckoutException {
        private static final long serialVersionUID = 1L;

        public RetryableCheckoutException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static final class ManualReviewException
            extends CheckoutException {
        private static final long serialVersionUID = 1L;

        public ManualReviewException(String message) {
            super(message);
        }
    }

    private static String checkout(String scenario)
            throws CheckoutException {
        switch (scenario) {
            case "invalid":
                throw new CorrectionNeededException(
                        "shipping address missing");
            case "temporary":
                IOException technical =
                        new IOException("gateway timeout");
                throw new RetryableCheckoutException(
                        "payment service temporarily unavailable",
                        technical);
            case "review":
                throw new ManualReviewException(
                        "risk review needed");
            case "unexpected":
                throw new IllegalStateException(
                        "internal invariant broken");
            case "ok":
                return "ORDER-100";
            default:
                throw new CorrectionNeededException(
                        "unknown request");
        }
    }

    private static void caller(String scenario) {
        System.out.println("== " + scenario + " ==");

        try {
            System.out.println("receipt=" + checkout(scenario));
        } catch (CorrectionNeededException ex) {
            System.out.println(
                    "action=ask-customer; reason=" + ex.getMessage());
        } catch (RetryableCheckoutException ex) {
            System.out.println(
                    "action=retry-later; reason=" + ex.getMessage());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        } catch (ManualReviewException ex) {
            System.out.println(
                    "action=manual-review; reason=" + ex.getMessage());
        } catch (CheckoutException ex) {
            System.out.println(
                    "action=generic-checkout-failure; type="
                    + ex.getClass().getSimpleName());
        } catch (RuntimeException ex) {
            System.out.println(
                    "action=technical-alert; type="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        caller("invalid");
        caller("temporary");
        caller("review");
        caller("ok");
        caller("unexpected");
    }
}
~~~

Chạy từ thư mục chứa file, với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 CallerOrientedExceptionsDemo.java
java CallerOrientedExceptionsDemo
~~~

**Stdout chính xác, đã được kiểm chứng khi biên dịch và chạy chương trình:**

~~~text
== invalid ==
action=ask-customer; reason=shipping address missing
== temporary ==
action=retry-later; reason=payment service temporarily unavailable
cause=IOException
== review ==
action=manual-review; reason=risk review needed
== ok ==
receipt=ORDER-100
== unexpected ==
action=technical-alert; type=IllegalStateException
~~~

Chương trình dùng mã mô phỏng ổn định, không gọi mạng thật hoặc xử lý thanh toán thật. Việc in `action=retry-later` **chỉ minh họa quyết định của caller**, không thực hiện retry tự động.

## 6. Vì sao cây exception trong ví dụ hợp lý?

### 6.1. Một base checked mô tả hợp đồng của API

~~~java
public static abstract class CheckoutException extends Exception {
    private static final long serialVersionUID = 1L;

    protected CheckoutException(String message) {
        super(message);
    }

    protected CheckoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Class gốc `CheckoutException` nói rằng có một **thất bại dự kiến thuộc quá trình checkout**. Nó không nêu hành động cụ thể, nhưng cho phép code cấp cao khai báo một hợp đồng chung: `throws CheckoutException`.

Chọn `abstract` khiến tác giả dịch vụ phải sử dụng subtype (hoặc tạo thêm subtype khi thật sự cần) thay vì ném một lỗi base mơ hồ trong những tình huống cần phân biệt. Các constructor `protected` hỗ trợ lớp con truyền message/cause và tránh bị gọi tùy tiện từ code ngoài khi muốn duy trì chính sách phân loại.

**Lưu ý:** Không phải mọi project đều cần base abstract. Nếu hệ thống chủ yếu có một loại lỗi nghiệp vụ, một exception cụ thể duy nhất có thể rõ ràng hơn cây phân cấp. Chỉ tạo base khi có lợi ích thật đối với phương thức caller và quản lý hợp đồng.

### 6.2. CorrectionNeededException: người dùng cần sửa dữ liệu

Trong nhánh `invalid`, dịch vụ ném:

~~~java
throw new CorrectionNeededException(
        "shipping address missing");
~~~

Caller thấy kiểu `CorrectionNeededException` và thực hiện hành động cụ thể: hiển thị lỗi cho người dùng/cho nhập lại. Không cần bắt `IllegalArgumentException` cho mọi sự cố rồi đoán xem đó là lỗi dữ liệu khách nhập hay bug trong hệ thống.

**Đừng trả trực tiếp message nội bộ cho khách hàng** nếu nó chứa thông tin riêng tư hoặc cấu trúc hệ thống. Trong API thật, handler nên ánh xạ sang mã lỗi ổn định, nội dung UI đã được chọn lọc và có thể quốc tế hóa.

### 6.3. RetryableCheckoutException: có khả năng thử lại theo chính sách

Trong nhánh `temporary`, một `IOException("gateway timeout")` được bọc:

~~~java
throw new RetryableCheckoutException(
        "payment service temporarily unavailable",
        technical);
~~~

Caller bắt nhánh retry và thấy `getCause()` là `IOException`. Điều này giữ được dấu vết kỹ thuật mà không bắt caller phụ thuộc trực tiếp vào loại exception của thư viện mạng.

**Đặc biệt quan trọng trong thanh toán:** “lỗi có thể thử lại” không đồng nghĩa “gọi lại ngay là an toàn”. Một timeout có thể xảy ra **sau khi bên nhận đã ghi giao dịch thành công**. Retry cần đi kèm kiểm tra trạng thái, **idempotency key**, giới hạn số lần, backoff, timeout và tránh nhân đôi khoản thu. Nếu không thể xác minh an toàn, phân loại sang trạng thái cần đối soát/thủ công thay vì gắn nhãn retryable theo cảm tính.

Ví dụ chỉ **chỉ thị caller dự kiến hành động**, không đưa ra một thuật toán retry giao dịch tài chính thật.

### 6.4. ManualReviewException: cần người xử lý

Nhánh `review` biểu thị giao dịch chưa thể được tự động hoàn tất. Caller có thể tạo ticket hoặc trạng thái chờ phê duyệt, thay vì coi đây là lỗi tạm thời để retry vô hạn hoặc lỗi nhập liệu buộc người dùng sửa.

Một API thật có thể cần trạng thái `PENDING_REVIEW` dưới dạng **kết quả nghiệp vụ** thay vì exception, nhất là nếu chờ kiểm tra là một phần của luồng hoạt động bình thường. Hãy dùng exception khi đó thực sự là **đường kết thúc bất thường** theo hợp đồng, không vì muốn lưu mọi trạng thái trong một class Throwable.

### 6.5. IllegalStateException: lỗi không thuộc nhóm nghiệp vụ dự kiến

Trong nhánh `unexpected`, code chủ động tạo `IllegalStateException` để biểu diễn bất biến nội bộ bị phá vỡ. Nó không kế thừa `CheckoutException`, và caller mẫu bắt tại boundary bằng `catch (RuntimeException)` để in một **cảnh báo kỹ thuật**.

Đây là cấu trúc mô phỏng cho mục đích quan sát. **Không nên bắt mọi RuntimeException rồi mặc nhiên tiếp tục nghiệp vụ** như thể đã phục hồi. Trong ứng dụng thật, boundary có thể log, trả lỗi máy chủ, dừng job hoặc chuyển sự cố đến bộ phận vận hành. Những lỗi logic như `NullPointerException`, `IndexOutOfBoundsException` không nên được đóng gói thành lỗi “khách nhập sai” chỉ để đạt một handler chung.

## 7. Thứ tự catch và hợp đồng subtype

Khi có cả subtype và base trong một cấu trúc:

~~~java
try {
    checkout("temporary");
} catch (CorrectionNeededException ex) {
    handleCorrection(ex);
} catch (RetryableCheckoutException ex) {
    handleRetryable(ex);
} catch (ManualReviewException ex) {
    handleReview(ex);
} catch (CheckoutException ex) {
    handleOtherCheckout(ex);
}
~~~

Đây là **đoạn minh họa**, các phương thức handler cần định nghĩa. Thứ tự **các subtype trước base** là bắt buộc để tránh catch base che các catch cụ thể. Nếu đặt `catch (CheckoutException)` lên trước, các nhánh con ở phía sau sẽ **không thể tới được** và compiler từ chối.

Ba subtype ngang hàng trong ví dụ không kế thừa lẫn nhau, vì vậy thứ tự **giữa chính ba subtype** không bị ràng buộc bởi quan hệ superclass/subclass. Có thể xếp theo cách người đọc hiểu rõ luồng xử lý nhất.

### Vì sao vẫn có catch base ở cuối?

Trong chương trình chính, `catch (CheckoutException ex)` là **nhánh dự phòng** để xử lý một subtype khác có thể được bổ sung sau này, hoặc một đường phát sinh từ phương thức có chữ ký chung.

Nếu thư viện phát hành thêm một subtype mới, caller cũ đang bắt base ở cuối vẫn có chính sách fallback. Nhưng fallback cũng phải **an toàn**: không nên im lặng coi subtype chưa biết là “có thể retry”. Ví dụ in `generic-checkout-failure` thể hiện thái độ bảo thủ: báo lỗi chung hoặc chuyển xử lý, không tự suy hành động đặc thù.

**Cảnh báo:** catch base quá sớm làm mất ý nghĩa của hệ phân cấp. Có base để tiến hóa API khác với việc mọi tầng đều bắt base rồi bỏ qua phân loại.

## 8. Cần bao nhiêu cấp trong cây exception?

Một cây sâu có thể trông “kiến trúc” nhưng gây khó đọc:

~~~text
ApplicationException
  └─ DomainException
      └─ CommerceException
          └─ CheckoutException
              └─ PaymentException
                  └─ GatewayException
                      └─ TimeoutException
~~~

Nếu caller không có chính sách ở từng cấp, phần lớn các tầng là chi phí nhận thức và bảo trì. Những catch lồng nhau nhiều kiểu chung đôi khi khiến mã khó theo dõi và tên lớp không truyền được hành động.

Một cây **nông, hành động rõ ràng** thường dễ dùng hơn. Có thể áp dụng câu hỏi phản biện:

- Caller có **thực sự catch** kiểu trung gian này không?
- Nếu bỏ cấp trung gian, có mất một chính sách xử lý có ý nghĩa không?
- Hai subtype hiện tại khác nhau về **hành vi** hay chỉ về message/cause?
- Nếu một thay đổi thư viện kỹ thuật xảy ra, tên và phân cấp custom có buộc caller sửa không?
- Nếu phát hành subtype mới, caller cũ có fallback an toàn không?

Không phải mọi tình huống mới đều cần một subtype. Nếu hai sự cố đều yêu cầu người dùng sửa đầu vào, có thể dùng cùng `CorrectionNeededException` và thêm mã lý do có cấu trúc.

## 9. Dùng mã lỗi có cấu trúc thay vì tạo class cho mọi chi tiết

Giả sử một nhóm lỗi yêu cầu sửa dữ liệu có nhiều lý do: thiếu địa chỉ, thiếu số điện thoại, mã bưu chính không hợp lệ. Nếu mọi lý do đều dẫn đến một hành động chung, tạo ba class exception mới có thể không cần thiết.

Một cách mô hình hóa:

~~~java
enum CorrectionCode {
    ADDRESS_MISSING,
    PHONE_MISSING,
    POSTAL_CODE_INVALID
}

final class CorrectionNeededException extends Exception {
    private final CorrectionCode code;

    CorrectionNeededException(CorrectionCode code, String message) {
        super(message);
        this.code = code;
    }

    CorrectionCode code() {
        return code;
    }
}
~~~

Đoạn trên là **các khai báo kiểu Java hợp lệ để minh họa thiết kế**, chưa bao gồm chương trình `main`. Caller có thể bắt một kiểu `CorrectionNeededException`, xử lý chung việc cho sửa dữ liệu rồi ánh xạ `code()` đến trường UI thích hợp.

Tuy nhiên, **nếu mã lỗi bắt đầu quyết định những luồng xử lý hoàn toàn khác nhau**, một enum quá rộng chỉ chuyển gánh nặng từ các catch thành một `switch` phức tạp. Khi đó hãy cân nhắc dùng subtype hoặc một mô hình kết quả nghiệp vụ khác.

**Không phân loại lỗi bằng cách so sánh `getMessage()`**: message dành cho người đọc/log, có thể đổi do bản dịch hoặc chỉnh câu chữ. Class type, enum code và hợp đồng API rõ ràng đáng tin hơn.

## 10. Giữ cause khi chuyển lỗi hạ tầng thành lỗi nghiệp vụ

Ngoại lệ tùy chỉnh thường nằm tại **ranh giới tầng**. Tầng kỹ thuật có thể ném `IOException`, `SQLException` hoặc exception của HTTP client; tầng dịch vụ chuyển sang exception mang ý nghĩa hợp đồng.

Mẫu:

~~~java
try {
    gatewayCall();
} catch (IOException ex) {
    if (knownTransientCondition(ex)) {
        throw new RetryableCheckoutException(
                "Gateway temporarily unavailable", ex);
    }
    throw new IllegalStateException(
            "Gateway failure needs investigation", ex);
}
~~~

Đây là **mã minh họa**, `gatewayCall()` và `knownTransientCondition()` chưa được định nghĩa. Điều quan trọng không phải luôn chọn đúng hai loại nêu trên, mà là **chỉ gắn nhãn retry sau khi phân loại hợp lệ** và **giữ nguyên cause** bằng constructor nhận `Throwable`.

Các lỗi thường gặp:

- Bắt mọi `Exception` rồi ném `new CheckoutException("failed")`, làm mất loại lỗi gốc và khả năng khôi phục.
- Bắt `IOException` rồi đánh dấu retryable mà không biết yêu cầu có thể đã được hệ thống ngoài thực hiện.
- Chỉ chuyển message sang exception mới, bỏ mất `cause` và stack trace nguồn gốc.
- Dùng exception hạ tầng làm public API dù caller không nên phụ thuộc vào thư viện đó.

Nếu cần log, một logger tốt sẽ ghi **exception object**, gồm cause và suppressed exceptions, không chỉ message. Cẩn trọng với thông tin riêng tư trong message.

## 11. Thiết kế constructor và thông tin lỗi

Custom exception nên cân nhắc cung cấp constructor phù hợp để lưu message và cause. Ví dụ base ở chương trình chính:

~~~java
protected CheckoutException(String message) {
    super(message);
}

protected CheckoutException(String message, Throwable cause) {
    super(message, cause);
}
~~~

Các constructor thực tế nằm bên trong lớp `CheckoutException`. Một lớp con có thể chỉ công khai những kiểu khởi tạo phù hợp với ngữ nghĩa của nó; không bắt buộc phải copy cả bốn overload constructor từ `Exception` chỉ để “đầy đủ”.

Một số thông tin bổ sung có thể hữu ích:

| Dữ liệu | Nên lưu bằng gì? | Lưu ý |
| --- | --- | --- |
| Loại hành động cần thực hiện | Subtype hoặc cấu trúc kết quả | Phải ổn định và có ý nghĩa caller |
| Mã lý do có cấu trúc | Enum/string code có hợp đồng | Không dùng message làm mã |
| Thông điệp chẩn đoán | `getMessage()` | Không lộ token, mật khẩu, dữ liệu nhạy cảm |
| Lỗi nguồn gốc | `cause` | Giữ chain để debug |
| Định danh giao dịch/operation | Trường typed hoặc context bên ngoài | Không công khai vô điều kiện |
| Thời gian retry dự kiến | Chính sách retry hoặc trường được chuẩn hóa | Không bảo đảm mọi lỗi transient đều retry an toàn |
| Lỗi cleanup thứ cấp | `getSuppressed()` | Không đồng nhất với cause |

Nếu một class exception là API công khai có khả năng được serialize, cần cân nhắc tương thích giữa phiên bản. Các exception trong chương trình chính khai báo `serialVersionUID` vì `Throwable` hỗ trợ `Serializable`; trường này không làm ngoại lệ an toàn hơn, cũng không thay thế chính sách versioning/serialization.

## 12. Checked exception không thể tự động bắt RuntimeException

Trong chương trình chính, `checkout(String)` khai báo:

~~~java
private static String checkout(String scenario)
        throws CheckoutException
~~~

Method vẫn có thể ném `IllegalStateException` vì đó là unchecked exception. Caller bắt từng subtype `CheckoutException`, sau đó có một handler `RuntimeException` ở tầng boundary để ghi cảnh báo.

**Không suy rằng một phương thức khai báo `throws CheckoutException` thì mọi thất bại runtime đều phải là subtype của CheckoutException.** Compiler chỉ áp dụng quy tắc `throws` bắt buộc cho checked exceptions; unchecked exceptions có thể phát sinh từ code nội bộ bất kể chữ ký.

Cũng không nên viết mọi nghiệp vụ như sau:

~~~java
try {
    doSomething();
} catch (Exception ex) {
    System.out.println("Handled");
}
~~~

Đây là đoạn minh họa thiếu định nghĩa `doSomething()`. Nó bắt rất nhiều exception thuộc nhánh `Exception`, bao gồm cả `RuntimeException` do bug, và biến tất cả thành một thông báo chung. Trong nhiều hệ thống, cách này làm lỗi bị “nuốt” và chương trình tiếp tục ở trạng thái không nhất quán. Một handler rộng chỉ nên tồn tại tại boundary có chính sách phản hồi, logging và dừng/khôi phục rõ.

## 13. Hợp đồng tiến hóa của một thư viện public

Một hệ phân cấp exception có thể là **public API**. Khi đã có caller thực tế, thay đổi cây không còn chỉ là việc đổi tên class.

### 13.1. Thêm subtype mới

Ví dụ một bản phát hành thêm `VerificationPendingException extends CheckoutException`. Một caller cũ chỉ có ba catch cụ thể **và** catch base cuối vẫn xử lý theo fallback chung. Một caller cố liệt kê toàn bộ subtype mà không có fallback có thể cần điều chỉnh tùy chữ ký và cấu trúc code.

Đừng để subtype mới âm thầm mặc định được retry nếu nó chưa có chính sách rõ. Chọn fallback bảo thủ ở boundary, đồng thời đánh dấu metric/log để đội phát triển bổ sung xử lý khi cần.

### 13.2. Đổi checked thành unchecked hoặc ngược lại

Đổi `extends Exception` thành `extends RuntimeException` có thể thay đổi cả cách compiler yêu cầu `throws`/catch và ý nghĩa hợp đồng đối với caller. Đổi ngược lại có thể khiến nhiều nơi gọi không biên dịch. Cần coi đây là **thay đổi API quan trọng**, không chỉ sửa inheritance cho đẹp.

### 13.3. Thay đổi cha/con của một exception

Nếu một subtype đang được xử lý bởi `catch (RetryableCheckoutException)` mà sau này chuyển sang nhóm khác, behavior của caller sẽ đổi dù exception class vẫn giữ tên. Các handler theo kiểu runtime phụ thuộc cây kế thừa.

Vì vậy tổ chức class theo **hành động caller ổn định** có giá trị lâu dài hơn gắn chặt vào hạ tầng vốn thay đổi thường xuyên.

### 13.4. Không nên hứa cây class là tập đóng khi không bảo đảm

Các subtype được đánh dấu `final` trong chương trình mẫu để không tạo thêm những nhánh con tùy ý bên dưới từng hành động. Nhưng base `CheckoutException` vẫn cho phép thêm subtype trong tương lai. Do đó **không** được hiểu cây hiện tại chỉ có ba trường hợp mãi mãi.

Java 17 có sealed classes để hạn chế tập subtype khi cần một phân loại đóng và được kiểm soát, nhưng đó là quyết định riêng: sealed hierarchy có thể thích hợp khi API muốn exhaustive modeling, trong khi hệ thống cần mở rộng plugin/exceptions có thể không muốn đóng cây. Đừng chọn sealed chỉ vì Java 17 có hỗ trợ.

## 14. Kiểm thử hệ phân cấp theo hành vi của caller

Một bài kiểm thử tốt không chỉ kiểm tra “đã ném exception”, mà còn kiểm tra **caller chọn đúng phản ứng**.

Với ví dụ chính:

| Scenario | Exception hoặc giá trị trả về | Hành động caller |
| --- | --- | --- |
| `invalid` | `CorrectionNeededException` | Yêu cầu sửa dữ liệu |
| `temporary` | `RetryableCheckoutException` với cause `IOException` | Đánh dấu xử lý retry sau, không retry mù |
| `review` | `ManualReviewException` | Chuyển kiểm tra thủ công |
| `ok` | `ORDER-100` | Xử lý thành công |
| `unexpected` | `IllegalStateException` | Cảnh báo kỹ thuật tại boundary |

Các kiểm thử thực tế nên xét:

1. **Đúng kiểu exception** khi một tình huống đã được phân loại.
2. **Cause có được giữ không** khi dịch từ hạ tầng sang hợp đồng nghiệp vụ.
3. **Hành động caller** có đúng hay không, tránh bug biến lỗi cần sửa thành retry.
4. **Fallback có an toàn không** khi gặp subtype chưa biết.
5. **Không nuốt RuntimeException** và không trả về kết quả thành công giả.
6. **Không dựa vào message** để chọn nhánh; message có thể thay đổi.
7. **Chính sách retry có idempotency/bounded retry** và không nhân đôi tác vụ có side effect.
8. **Lỗi kỹ thuật có log/metric thích hợp** mà không rò rỉ dữ liệu nhạy cảm.

Trong chương trình console, việc kiểm chứng stdout theo từng scenario đã chứng minh cơ chế catch và ý nghĩa của cây. Khi chuyển vào project, có thể dùng JUnit 5 (nếu đã có) để viết test riêng cho service và caller; không cần thêm framework chỉ để giải thích quy tắc Java.

## 15. So sánh các phương án thiết kế

| Phương án | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| Một class `CheckoutException` duy nhất | Mọi caller đều xử lý chung | Không có phân biệt hành động trực tiếp bằng kiểu |
| Base + subtype theo hành động | Caller cần sửa, retry, review theo nhánh khác nhau | Có thể nhiều class nếu lạm dụng |
| Một exception + enum reason | Cùng hành động nhưng nhiều nguyên nhân chi tiết | Enum có thể biến thành một switch phức tạp |
| Exception theo công nghệ (DB/HTTP/JSON) | Caller thực sự là tầng hạ tầng và biết cách khắc phục riêng | Rò rỉ implementation detail lên tầng nghiệp vụ |
| Unchecked exception tùy chỉnh | Chính sách API không buộc caller bắt từng lỗi | Caller có thể bỏ qua lỗi dự kiến |
| Kiểu kết quả như `Result/Status` thay vì exception | Thất bại/đang chờ là trạng thái bình thường thường gặp | Cần thiết kế result type và xử lý tường minh |
| Wrapper exception + cause | Chuyển tầng để thêm ngữ cảnh nhưng giữ lỗi gốc | Có thể lạm dụng việc bọc nhiều tầng và làm log dài |

**Điểm chọn lựa:** Một mô hình hợp lý không phải mô hình có nhiều subtype nhất, mà là mô hình khiến caller viết được **luồng xử lý đúng, dễ hiểu, ít phụ thuộc và an toàn**.

## 16. Những lỗi thiết kế thường gặp

1. **Tạo class cho từng thông báo lỗi.** Nếu cách khắc phục không đổi, sử dụng cùng class với mã lý do có cấu trúc.
2. **Tạo class theo từng tên driver/protocol.** Dễ làm hỏng hợp đồng khi đổi thư viện kỹ thuật.
3. **Mọi exception đều extends một base rất rộng rồi catch base ở mọi tầng.** Làm mất phân loại hành động.
4. **Dùng checked exception cho mọi bug.** Bắt lập trình viên xử lý cả những vấn đề không thể phục hồi hợp lý.
5. **Dùng unchecked exception để che những thất bại dự kiến nhưng không có chính sách.** Caller có thể bất ngờ mất cơ hội xử lý.
6. **Gắn nhãn retryable cho mọi timeout.** Rất nguy hiểm với thao tác có side effect nếu không có idempotency và đối soát.
7. **Đổi hệ phân cấp liên tục theo implementation.** Khiến caller cũ bị ảnh hưởng dù chức năng không đổi.
8. **Không giữ cause.** Khó truy dấu lỗi gốc trong log.
9. **So sánh message bằng chuỗi.** Ngôn ngữ hiển thị và wording không nên quyết định luồng xử lý.
10. **Cho người dùng thấy trực tiếp message hạ tầng.** Dễ rò rỉ cấu trúc hệ thống hoặc dữ liệu nhạy cảm.
11. **Tạo cây kế thừa quá sâu.** Gây chi phí bảo trì khi không có handler nào dùng tầng trung gian.
12. **Dùng exception cho một trạng thái nghiệp vụ bình thường.** Ví dụ pending approval thường là trạng thái hợp lệ, có thể mô hình hóa bằng result.
13. **Bọc tất cả RuntimeException thành lỗi người dùng nhập sai.** Che giấu lỗi lập trình.
14. **Không kiểm thử handler fallback.** Type mới xuất hiện có thể bị xử lý bằng hành động không an toàn.
15. **Giả định có cause thì caller nên catch kiểu cause.** Caller nên sử dụng contract exception của tầng hiện tại; cause chủ yếu phục vụ chẩn đoán hoặc một chiến lược xử lý được thiết kế rõ.
16. **Gọi là retryable nhưng không đưa chính sách retry vào hệ thống.** Phân loại exception chỉ là một phần của workflow; retry phải có giới hạn và kiểm soát.

## 17. Các câu hỏi tự kiểm tra

**Câu 1.** Tại sao `PaymentHttpException` và `PaymentDatabaseException` không nhất thiết là hai nhánh tốt trong API Checkout?

*Đáp án:* Nếu caller xử lý hai lỗi giống nhau và không cần biết công nghệ bên trong, sự phân chia này làm lộ hạ tầng. Nên gom theo chính sách xử lý thực tế khi phù hợp.

**Câu 2.** Ba quyết định “sửa dữ liệu”, “retry có điều kiện”, “kiểm tra thủ công” có thể được thể hiện thế nào?

*Đáp án:* Có thể tạo các subtype có ý nghĩa riêng dưới một base CheckoutException, hoặc mô hình hóa theo mã/trạng thái có cấu trúc khi phù hợp. Quan trọng là caller phân biệt được đúng hành động.

**Câu 3.** Nếu `CorrectionNeededException extends CheckoutException` thì catch nào phải đứng trước khi có cả hai?

*Đáp án:* `catch (CorrectionNeededException)` phải đứng trước `catch (CheckoutException)`. Đặt base trước che subtype và gây lỗi biên dịch.

**Câu 4.** Một `IOException` khi gọi payment gateway có luôn là lỗi nên retry không?

*Đáp án:* Không. Cần phân loại trạng thái thực tế, đánh giá idempotency và khả năng giao dịch đã được thực hiện trước timeout.

**Câu 5.** Vì sao constructor `RetryableCheckoutException(String, Throwable)` hữu ích?

*Đáp án:* Cho phép giữ cause hạ tầng khi đưa ra một exception nghiệp vụ ổn định, giúp caller xử lý theo contract và vẫn có dấu vết kỹ thuật để debug.

**Câu 6.** Một method khai báo `throws CheckoutException` có thể ném `NullPointerException` không?

*Đáp án:* Có. NullPointerException là unchecked và không buộc phải được liệt kê trong throws.

**Câu 7.** Nếu hai trường dữ liệu lỗi đều khiến khách nhập lại, có bắt buộc tạo hai subclass exception không?

*Đáp án:* Không. Có thể dùng cùng một lớp lỗi hành động “cần sửa” và một enum/code chi tiết, nếu đó là hợp đồng ổn định, dễ dùng.

**Câu 8.** Thêm subtype `VerificationPendingException` có nên mặc định được retry trong catch base không?

*Đáp án:* Không. Fallback cần bảo thủ: ghi nhận lỗi chưa được phân loại rõ, trả trạng thái tổng quát hoặc chuyển kiểm tra theo chính sách an toàn.

**Câu 9.** Nếu thao tác “pending review” là trạng thái thường xuyên, không phải lỗi bất thường, nên cân nhắc gì?

*Đáp án:* Dùng status/result object hoặc một kiểu kết quả có nhánh rõ, thay vì mặc nhiên ném exception để biểu diễn trạng thái bình thường.

**Câu 10.** Làm sao biết cây exception đang trở nên quá sâu?

*Đáp án:* Xem từng cấp có được caller catch để quyết định hành động thật không. Nếu nhiều cấp không có chính sách xử lý riêng, có thể đơn giản hóa.

## 18. Tài liệu đối chiếu

- [Java SE 17 JLS – Exceptions, chương 11](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): phân biệt checked và unchecked, phân tích exception và yêu cầu khai báo.
- [Java SE 17 JLS – try/catch, mục 14.20](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20): quy tắc lựa chọn catch phù hợp và thứ tự các handler.
- [Java SE 17 JLS – throw, mục 14.18](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): điều kiện biểu thức và ngữ nghĩa ném Throwable.
- [Java SE 17 API – Exception](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Exception.html): class gốc checked phổ biến.
- [Java SE 17 API – RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html): nhánh unchecked dành cho nhiều lỗi không buộc khai báo.
- [Java SE 17 API – Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): cause, message, stack trace và suppressed exceptions.
- [Java SE 17 API – IllegalStateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): một ví dụ unchecked exception thể hiện trạng thái ứng dụng không hợp lệ.

**Tóm lại:** Hãy thiết kế hệ phân cấp **từ phía caller**: họ cần sửa dữ liệu, thử lại có kiểm soát, chuyển người xử lý hay báo lỗi kỹ thuật? Cho mỗi nhánh một **hợp đồng hành động ổn định**, không tạo class theo mọi chi tiết hạ tầng. Giữ cause, đặt catch cụ thể trước catch base, chọn checked/unchecked có chủ đích và để fallback an toàn khi API tiến hóa.