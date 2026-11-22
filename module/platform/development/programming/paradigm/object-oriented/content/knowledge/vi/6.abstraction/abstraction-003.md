# Hợp đồng sử dụng và chi tiết thực hiện trong Java OOP

Một đối tượng có thể thay đổi thuật toán, cách lưu dữ liệu hay nhà cung cấp bên ngoài mà người sử dụng **không phải đổi cách gọi**. Điều này chỉ an toàn khi ta phân biệt rõ hai thứ:

- **Hợp đồng sử dụng (*contract*):** người gọi được yêu cầu hành vi gì, đầu vào nào hợp lệ, nhận loại kết quả nào, lỗi và tác dụng phụ nào có thể xảy ra.
- **Chi tiết thực hiện (*implementation*):** đối tượng dùng thuật toán, cấu trúc dữ liệu, thư viện hay kết nối bên ngoài nào để thực hiện các cam kết ấy.

Trong Java, `interface`, `abstract class` và public API đều có thể thể hiện một phần hợp đồng. Nhưng **chữ ký phương thức không phải toàn bộ hợp đồng hành vi**. Một implementation vẫn có thể biên dịch mà trả kết quả sai ý nghĩa.

Bài này dùng **chính sách đánh giá đơn xin nghỉ phép** để đi từ việc định nghĩa hợp đồng, triển khai hai quy tắc khác nhau, thay thế provider, kiểm thử và quản lý thay đổi. Đây là ví dụ độc lập, không cần Spring Boot.

## 1. Nhìn từ phía người gọi: họ thực sự cần biết gì?

Một dịch vụ nhân sự cần đánh giá sơ bộ đơn xin nghỉ. Dữ liệu cần cho chính sách minh họa là mã nhân viên, số ngày xin nghỉ và số ngày phép còn lại tại thời điểm kiểm tra. Có hai loại chính sách:

- **Chính sách thông thường:** cho kết quả đủ điều kiện nếu số ngày xin nghỉ không vượt số ngày phép còn lại.
- **Chính sách thử việc:** ngoài điều kiện số dư, mỗi đơn chỉ được xin tối đa hai ngày.

Hai cách thực hiện có thể cho **kết quả khác nhau với cùng đầu vào** mà vẫn tuân thủ cùng một hợp đồng. Người gọi chỉ cần yêu cầu `evaluate(request)` và nhận quyết định có lý do, không cần biết việc xét thử việc đặt trong `if`, bảng quy tắc hay hệ thống HR.

| Hợp đồng cần công bố | Ví dụ |
| --- | --- |
| Khả năng | Đánh giá khả năng chấp nhận một yêu cầu nghỉ |
| Dữ liệu đầu vào | `LeaveRequest` có mã nhân viên, `requestedDays`, `remainingDays` |
| Miền giá trị | Mã không trắng, số ngày xin > 0, số dư ngày phép >= 0 |
| Kết quả | `LeaveDecision` với mã quyết định và giải thích |
| Quy tắc chung | Không được phê duyệt nếu ngày xin vượt số dư |
| Lỗi | `null` bị từ chối; dữ liệu không hợp lệ bị từ chối lúc tạo request |
| Tác dụng phụ | Chỉ **đánh giá**, không trừ ngày phép, không ghi cơ sở dữ liệu |
| Giới hạn | Quyết định dựa trên snapshot; chưa có nghĩa là đơn đã được duyệt/lưu |

**Hợp đồng càng rõ thì càng ít chỗ để mỗi implementation tự hiểu một kiểu.** Ví dụ, nếu một lớp trả `null` cho đơn bị từ chối, lớp khác trả đối tượng có mã từ chối, caller buộc phải có nhánh riêng cho từng nhà cung cấp.

## 2. Ví dụ Java chạy độc lập: hai implementation, một hợp đồng

Lưu thành `LeaveContractDemo.java`, biên dịch bằng **JDK 17 trở lên**. `record` là các kiểu giá trị gọn và có constructor kiểm tra dữ liệu. Trong ví dụ này, record chỉ chứa `String`, số nguyên và enum nên không lộ tham chiếu mutable.

~~~java
import java.util.Objects;

public class LeaveContractDemo {

    record LeaveRequest(
            String employeeId, int requestedDays, int remainingDays) {
        LeaveRequest {
            if (employeeId == null || employeeId.isBlank()) {
                throw new IllegalArgumentException("Employee ID is required");
            }
            if (requestedDays <= 0 || remainingDays < 0) {
                throw new IllegalArgumentException("Invalid day count");
            }
        }
    }

    enum DecisionCode {
        APPROVED, INSUFFICIENT_BALANCE,
        EXCEEDS_TRIAL_LIMIT, REJECTED_BY_POLICY
    }

    record LeaveDecision(DecisionCode code, String explanation) {
        LeaveDecision {
            Objects.requireNonNull(code, "code");
            if (explanation == null || explanation.isBlank()) {
                throw new IllegalArgumentException("Explanation is required");
            }
        }

        boolean approved() {
            return code == DecisionCode.APPROVED;
        }
    }

    /**
     * Đánh giá một request hợp lệ, khác null.
     * Trả LeaveDecision khác null.
     * Không APPROVED khi requestedDays > remainingDays.
     * Không sửa request hay số dư; không lưu/phê duyệt đơn thật.
     * Null input -> NullPointerException.
     */
    interface LeavePolicy {
        LeaveDecision evaluate(LeaveRequest request);
    }

    static final class StandardLeavePolicy implements LeavePolicy {
        @Override
        public LeaveDecision evaluate(LeaveRequest request) {
            Objects.requireNonNull(request, "request");
            if (request.requestedDays() > request.remainingDays()) {
                return new LeaveDecision(
                        DecisionCode.INSUFFICIENT_BALANCE,
                        "Số ngày phép còn lại không đủ");
            }
            return new LeaveDecision(
                    DecisionCode.APPROVED, "Đủ ngày phép");
        }
    }

    static final class TrialLeavePolicy implements LeavePolicy {
        @Override
        public LeaveDecision evaluate(LeaveRequest request) {
            Objects.requireNonNull(request, "request");
            if (request.requestedDays() > request.remainingDays()) {
                return new LeaveDecision(
                        DecisionCode.INSUFFICIENT_BALANCE,
                        "Số ngày phép còn lại không đủ");
            }
            if (request.requestedDays() > 2) {
                return new LeaveDecision(
                        DecisionCode.EXCEEDS_TRIAL_LIMIT,
                        "Giới hạn thử việc là 2 ngày");
            }
            return new LeaveDecision(
                    DecisionCode.APPROVED, "Đạt quy tắc thử việc");
        }
    }

    static final class LeaveReviewService {
        private final LeavePolicy policy;

        LeaveReviewService(LeavePolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        LeaveDecision review(LeaveRequest request) {
            return policy.evaluate(request);
        }
    }

    static void print(
            String name, LeavePolicy policy, LeaveRequest request) {
        LeaveDecision result =
                new LeaveReviewService(policy).review(request);
        System.out.println(name + ": " + result.code()
                + " - " + result.explanation());
    }

    public static void main(String[] args) {
        LeaveRequest request = new LeaveRequest("NV-01", 3, 5);
        print("Thông thường", new StandardLeavePolicy(), request);
        print("Thử việc", new TrialLeavePolicy(), request);

        LeaveRequest insufficient = new LeaveRequest("NV-02", 6, 5);
        print("Thiếu phép", new StandardLeavePolicy(), insufficient);
    }
}
~~~

Chạy:

~~~bash
javac LeaveContractDemo.java
java LeaveContractDemo
~~~

Kết quả:

~~~text
Thông thường: APPROVED - Đủ ngày phép
Thử việc: EXCEEDS_TRIAL_LIMIT - Giới hạn thử việc là 2 ngày
Thiếu phép: INSUFFICIENT_BALANCE - Số ngày phép còn lại không đủ
~~~

**Giải thích theo trình tự:**

1. Request đầu có 3 ngày xin, 5 ngày còn lại; đây là đầu vào hợp lệ.
2. `StandardLeavePolicy` kiểm tra ngày xin không vượt số dư, trả `APPROVED`.
3. `TrialLeavePolicy` cùng được gọi qua `LeavePolicy.evaluate`, nhưng bổ sung giới hạn 2 ngày, nên trả `EXCEEDS_TRIAL_LIMIT`.
4. Request thứ hai xin 6 ngày khi còn 5, nên chính sách thường trả `INSUFFICIENT_BALANCE`.
5. Không có dòng nào trừ số dư. `remainingDays` là **snapshot đầu vào** và `APPROVED` ở đây chỉ có nghĩa “vượt qua bước đánh giá theo chính sách”, chưa phải phê duyệt giao dịch nghỉ phép cuối cùng.

Khác biệt kết quả không đồng nghĩa vi phạm hợp đồng. Chính sách đã được chủ đích cho phép các tiêu chí bổ sung, nhưng mọi implementation đều phải giữ **quy tắc chung: không phê duyệt khi thiếu số dư**.

## 3. Bản đồ phụ thuộc và phân vai

~~~mermaid
classDiagram
    class LeavePolicy {
        <<interface>>
        +evaluate(LeaveRequest) LeaveDecision
    }
    class StandardLeavePolicy {
        +evaluate(LeaveRequest) LeaveDecision
    }
    class TrialLeavePolicy {
        +evaluate(LeaveRequest) LeaveDecision
    }
    class LeaveReviewService {
        -LeavePolicy policy
        +review(LeaveRequest) LeaveDecision
    }
    LeavePolicy <|.. StandardLeavePolicy
    LeavePolicy <|.. TrialLeavePolicy
    LeaveReviewService --> LeavePolicy
~~~

**`LeaveReviewService` là client:** nó chỉ biết kiểu `LeavePolicy` và kết quả `LeaveDecision`. Phần tạo đối tượng hay nơi cấu hình quyết định chính sách nào được truyền vào constructor. Interface **không tự chọn** chính sách đúng theo nhân viên.

**`LeavePolicy` là hợp đồng:** công bố khả năng đánh giá, kiểu đầu vào/đầu ra và lời hứa về hành vi. Nó không nêu chi tiết thuật toán.

**`StandardLeavePolicy` và `TrialLeavePolicy` là implementation:** mỗi lớp tự chịu trách nhiệm thực hiện đúng phần việc của mình, kể cả từ chối `null` và không phê duyệt khi ngày xin vượt số dư.

Constructor injection trong ví dụ là cách truyền phụ thuộc từ ngoài vào. Không cần DI container để thực hiện điều này. Nếu thay bằng một implementation mới hợp lệ, `LeaveReviewService.review` vẫn không cần biết tên lớp mới.

## 4. Phân biệt chữ ký phương thức với hợp đồng hành vi

Chữ ký Java:

~~~java
LeaveDecision evaluate(LeaveRequest request);
~~~

giúp trình biên dịch biết tên method, kiểu tham số và kiểu trả về. Nó **không tự cưỡng chế** mọi cam kết như “không trả null”, “không ghi database” hay “không phê duyệt vượt phép”.

| Nội dung | Java compiler kiểm tra được? | Điều còn phải xác minh |
| --- | --- | --- |
| Có method `evaluate(LeaveRequest)` | Có | Ý nghĩa nghiệp vụ |
| Trả kiểu `LeaveDecision` | Có | Có trả `null` khi không được phép không |
| Request tạo qua constructor hợp lệ | Constructor runtime kiểm tra | Các đường tạo khác và quy tắc nguồn dữ liệu |
| Không duyệt khi thiếu phép | Không bằng chữ ký | Kiểm thử với ngày xin > ngày còn |
| Không gây side effect | Không bằng chữ ký | Review mã/test/tài liệu |
| Mã quyết định đúng ngữ nghĩa | Không bằng chữ ký | Test tình huống và quy ước chung |

Ví dụ một implementation sai dù vẫn biên dịch:

~~~java
static final class BrokenLeavePolicy implements LeavePolicy {
    @Override
    public LeaveDecision evaluate(LeaveRequest request) {
        return null; // Vi phạm cam kết kết quả khác null.
    }
}
~~~

Đoạn này có thể đặt làm lớp lồng trong `LeaveContractDemo` để quan sát. `@Override` chỉ giúp compiler xác minh đang triển khai đúng chữ ký; nó không chứng minh hành vi đã đúng.

### Những điều caller cần biết, không được “giấu” nhầm

Một hợp đồng thực tế có thể phải nói rõ thời điểm lấy số dư ngày phép, cách xử lý dữ liệu quá hạn, phân quyền người duyệt, trạng thái lưu trữ, lỗi mạng và điều kiện đồng thời. Nếu một implementation từ chỗ tính trong bộ nhớ chuyển sang gọi API HR, timeout và khả năng dữ liệu không còn mới **có thể quan sát được**. Không nên hứa “hành vi hoàn toàn y hệt” chỉ vì tên method không đổi.

Trong ví dụ hiện tại, `evaluate` cố ý chỉ đánh giá theo dữ liệu đưa vào. Việc cập nhật ngày phép cần thuộc **một use case/giao dịch khác** có kiểm soát cạnh tranh dữ liệu. Nếu hai nhân viên hoặc hai request sử dụng cùng snapshot số dư, hai kết quả `APPROVED` chưa bảo đảm hệ thống có đủ phép để thực hiện cả hai yêu cầu cùng lúc.

## 5. Khả năng thay thế dựa trên hợp đồng, không chỉ interface

Nguyên tắc thay thế Liskov (LSP) ở đây là: một implementation có thể thay thế implementation khác mà không làm hỏng những **lời hứa chung** client được quyền dựa vào.

Đừng hiểu sai rằng hai chính sách phải trả cùng quyết định. Bài toán đã quy định chính sách thử việc có thể nghiêm hơn về ngày nghỉ; nhưng không chính sách nào được trả `APPROVED` khi `requestedDays > remainingDays`.

| Hành vi implementation | Phù hợp với hợp đồng ví dụ? | Vì sao |
| --- | --- | --- |
| Chính sách thường duyệt 3/5 ngày | Có | Quy tắc thông thường cho phép |
| Chính sách thử việc từ chối 3/5 ngày | Có | Giới hạn 2 ngày của chính sách này |
| Một implementation trả `APPROVED` cho 6/5 ngày | Không | Phá cam kết chung về số dư |
| Một implementation trả `null` khi đơn không hợp lệ | Không | Hợp đồng yêu cầu kết quả khác null với request hợp lệ |
| Một implementation trừ ngày phép ngay khi chỉ đánh giá | Không | Vi phạm cam kết không có side effect |
| Dùng cấu trúc dữ liệu/thuật toán khác | Có | Chi tiết thực hiện có quyền thay đổi |
| Thay đổi thông báo giải thích nhưng giữ đúng mã | Thường có | Trừ khi văn bản giải thích chính xác là một phần API đã cam kết |

Một quy tắc thực hành khác: implementation không được **siết tiền điều kiện chung** theo cách khiến những lời gọi hợp lệ của contract trở thành lỗi bất ngờ; cũng không được **làm yếu hậu điều kiện chung**. Trong ví dụ, các chính sách được phép *trả kết quả từ chối hợp lệ*, khác với *ném lỗi mới mà contract không mô tả*.

LSP không bắt buộc mọi chính sách phải chấp nhận đơn giống nhau; chính **ý nghĩa của các kết quả khác nhau** phải nhất quán.

## 6. Kiểm thử hợp đồng và kiểm thử client là hai việc khác nhau

### A. Test chung cho các implementation

Có thể thêm method sau vào `LeaveContractDemo`:

~~~java
static void verifyContract(LeavePolicy policy) {
    LeaveRequest insufficient = new LeaveRequest("NV-X", 6, 5);
    LeaveDecision rejected = policy.evaluate(insufficient);

    if (rejected == null || rejected.approved()) {
        throw new AssertionError("Policy approved excessive leave");
    }
    if (policy.evaluate(new LeaveRequest("NV-Y", 1, 3)) == null) {
        throw new AssertionError("Policy returned null");
    }

    try {
        policy.evaluate(null);
        throw new AssertionError("Null must be rejected");
    } catch (NullPointerException expected) {
        // Đúng hợp đồng về null.
    }
}
~~~

Gọi `verifyContract(new StandardLeavePolicy())` và `verifyContract(new TrialLeavePolicy())` để kiểm tra **cam kết chung**. Không nên viết test chung kiểu “mọi policy luôn duyệt 3 ngày” vì giới hạn thử việc đã quy định ngoại lệ hợp lệ.

Đây chỉ là test mẫu, không chứng minh đúng với mọi đầu vào. Trong ứng dụng thực, bổ sung các ca biên về số dư bằng 0, thời điểm cập nhật, lỗi provider và kiểm thử tích hợp.

### B. Test client bằng implementation giả

Nếu chỉ muốn kiểm tra `LeaveReviewService` **chuyển đúng request và nhận đúng kết quả**, ta không cần áp dụng chính sách thật:

~~~java
static final class FixedRejectPolicy implements LeavePolicy {
    @Override
    public LeaveDecision evaluate(LeaveRequest request) {
        Objects.requireNonNull(request, "request");
        return new LeaveDecision(
                DecisionCode.REJECTED_BY_POLICY, "Kết quả giả lập");
    }
}
~~~

Đây là một *test double* tuân thủ hợp đồng: từ chối là một kết quả hợp lệ, input vẫn được kiểm tra và không có side effect. Nó giúp kiểm tra client mà không phụ thuộc thuật toán chính sách thật.

**Test double không thay thế contract test của provider.** Một client chạy đúng khi dùng fake chưa chứng minh implementation dùng database hay HTTP giữ đúng ngữ nghĩa.

## 7. Interface, abstract class và public method: mức nào là đủ?

Trừu tượng hóa là một quyết định thiết kế, không đồng nghĩa bắt buộc viết `interface`. Một lớp cụ thể công bố `evaluate` rõ ràng, giấu cách tính bên trong cũng có thể cung cấp API tốt.

| Khi cần | Gợi ý |
| --- | --- |
| Một chính sách duy nhất, đơn giản và ổn định | Lớp cụ thể với public method có hợp đồng rõ |
| Nhiều chính sách cùng một tập hành vi; client cần thay chúng độc lập | Interface nhỏ như `LeavePolicy` |
| Một họ lớp thật sự chia sẻ trạng thái instance, constructor và phần lớn quy trình | Cân nhắc `abstract class` |
| Chỉ muốn tái sử dụng một phép kiểm tra/thuật toán | Hàm hỗ trợ hoặc composition, chưa chắc cần kế thừa |
| Nhiều interface chỉ chuyển tiếp y nguyên một lời gọi | Xem xét bỏ tầng không có trách nhiệm |

`interface` không có constructor hay instance field; `abstract class` có thể giữ trạng thái và phần triển khai chung nhưng Java chỉ cho phép một superclass trực tiếp. Nội dung chi tiết về cú pháp `abstract` được học trong bài dành riêng cho lớp/phương thức trừu tượng; ở đây tiêu chí chính là **client cần phụ thuộc vào hợp đồng nào**.

Nguyên tắc đảo ngược phụ thuộc (DIP) gợi ý để module điều phối dựa vào hợp đồng ổn định thay vì tạo cứng nhiều provider cụ thể. Nó **không** đòi mọi lớp nhỏ đều phải tạo một interface tương ứng.

## 8. Khi implementation nằm sau hệ thống bên ngoài

Một chính sách thực tế có thể hỏi dịch vụ nhân sự qua REST API hoặc SDK. Không nhất thiết để `LeaveReviewService` phải biết URL, JSON field, HTTP header hay mã lỗi của provider.

Có thể tổ chức theo ranh giới:

~~~mermaid
flowchart LR
    A["LeaveReviewService"] --> C["LeavePolicy<br/>Hợp đồng ứng dụng"]
    P["RemoteHrPolicyAdapter"] -. "implements" .-> C
    P --> H["SDK / HTTP HR"]
    H --> P
    P --> R["LeaveDecision"]
~~~

Một adapter có nhiệm vụ chuyển `LeaveRequest` sang dữ liệu provider, gọi dịch vụ, ánh xạ phản hồi về `LeaveDecision`, và biểu diễn lỗi theo hợp đồng của ứng dụng. Cần phân biệt **bị từ chối theo chính sách** với **không thể kiểm tra do hệ thống gặp lỗi**.

Ví dụ về ranh giới lỗi (mã minh họa, không phải một file đầy đủ):

~~~java
try {
    // Gọi provider và chuyển phản hồi thành LeaveDecision.
} catch (java.io.IOException ex) {
    throw new HrPolicyUnavailableException(
            "Không thể đánh giá lúc này", ex);
}
~~~

`HrPolicyUnavailableException` là kiểu exception ứng dụng phải tự khai báo và quyết định cách xử lý. Đây chỉ là mẫu mô tả; không phải mọi lỗi đều hợp lý để chuyển thành cùng một exception. Trong thực tế cần quy định timeout, retry, idempotency, khả năng trả dữ liệu cũ và những lỗi nào ảnh hưởng đến caller.

**Đặc biệt, không được biến lỗi mạng thành `APPROVED` hoặc `INSUFFICIENT_BALANCE`** chỉ để luôn có một kết quả. Như vậy vừa làm sai ngữ nghĩa, vừa tạo cảm giác quy tắc đã được kiểm tra thành công.

## 9. Hợp đồng có thể thay đổi mà vẫn ảnh hưởng client

Giữ nguyên tên `evaluate` không có nghĩa không thể phá vỡ hợp đồng.

| Thay đổi | Đánh giá |
| --- | --- |
| Tối ưu private helper nhưng giữ ngữ nghĩa | Thường không ảnh hưởng caller |
| Đổi thuật toán của một chính sách trong phạm vi đã công bố | Caller không cần sửa cách gọi, nhưng cần kiểm thử nghiệp vụ |
| Đổi tên `evaluate` hoặc kiểu trả về | Thường gây lỗi biên dịch ở caller/implementation |
| Thêm abstract method vào `LeavePolicy` | Các implementation cũ phải triển khai |
| Thêm default method | Có thể tương thích hơn, nhưng phải xét xung đột và ý nghĩa |
| Đổi `remainingDays` sang giờ nhưng giữ tên trường | Phá ngữ nghĩa/đơn vị dù kiểu vẫn là `int` |
| Tự động trừ ngày phép trong `evaluate` | Phá cam kết không có side effect |
| Trả `null` thay cho quyết định từ chối | Phá lời hứa kết quả non-null |
| Ném exception mới khi input hợp lệ mà trước đây trả từ chối | Có thể phá logic caller |
| Chuyển từ tính nội bộ sang gọi mạng | Cần xét timeout, lỗi tạm thời và hiệu lực snapshot |

Nếu bắt buộc đổi hợp đồng, cần phân tích tương thích nguồn, nhị phân và hành vi theo phạm vi ứng dụng, version API nếu cần, nâng cấp caller/implementation và duy trì contract test.

**Điểm khác biệt với refactor nội bộ:** sửa một công thức private có thể giữ nguyên API; đổi ý nghĩa một tham số, thời điểm cam kết hoặc loại lỗi có thể là **breaking change** dù chữ ký Java trông giống hệt.

## 10. Khi nào hợp đồng trở nên quá rộng hoặc rò rỉ triển khai?

Hai thiết kế đều có thể làm người dùng khó hiểu:

~~~java
// Quá mơ hồ: caller phải đoán ngữ nghĩa và ép kiểu.
interface GenericOperation {
    Object execute(Object input);
}

// Rò rỉ hạ tầng: nghiệp vụ bị ép hiểu cách truy xuất cụ thể.
interface RawHrConnector {
    java.sql.ResultSet queryVacationBalance(String employeeId)
            throws java.sql.SQLException;
}
~~~

Hợp đồng `LeavePolicy.evaluate(LeaveRequest)` rõ hơn vì công bố đúng hành vi và kiểu dữ liệu cần thiết. Tuy nhiên, nếu ứng dụng cố ý cung cấp thư viện truy vấn JDBC cấp thấp, `ResultSet` có thể chính là hợp đồng phù hợp. “Rò rỉ” phụ thuộc **ai là người sử dụng và họ cần biết gì**.

Khi API phình thành hàng chục phương thức không liên quan, một số implementation phải ném `UnsupportedOperationException` cho các thao tác không hỗ trợ. Đây là dấu hiệu hợp đồng cần được tách theo khả năng có ý nghĩa, thay vì bắt mọi provider giả vờ có cùng mọi chức năng.

Một API tốt không giấu đi **những thuộc tính quan sát được mà caller phải biết**. Đầu vào, kết quả, lỗi, độ mới dữ liệu, thời điểm cam kết, side effect đều có thể là phần thiết yếu. Chi tiết đáng che là quyết định triển khai *không cần thiết cho việc dùng đúng hợp đồng*.

## 11. Luyện tập: tự kiểm tra khả năng đọc hợp đồng

**Câu 1.** `LeaveReviewService` khai báo field `LeavePolicy` thay vì `TrialLeavePolicy`. Lợi ích là gì?

**Gợi ý:** Client chỉ phụ thuộc khả năng đánh giá, thay policy tại nơi cấu hình mà không phải sửa method `review`.

**Câu 2.** Một `LeavePolicy` trả `null` khi đơn thiếu phép. Code vẫn biên dịch. Đã đúng hợp đồng chưa?

**Gợi ý:** Chưa. Với request hợp lệ, phải trả `LeaveDecision` không null; thiếu phép là một quyết định từ chối, không phải “không có kết quả”.

**Câu 3.** Tại sao `StandardLeavePolicy` và `TrialLeavePolicy` được phép trả quyết định khác nhau cho cùng một request?

**Gợi ý:** Hợp đồng cho phép chính sách cụ thể áp dụng quy tắc riêng. Chúng vẫn phải giữ quy tắc chung, nhất là không phê duyệt vượt số dư và không sửa input.

**Câu 4.** Provider đổi sang HTTP nhưng vẫn trả `LeaveDecision`. Có cần xét lại hợp đồng?

**Gợi ý:** Có thể có, vì timeout, lỗi tạm thời, độ mới dữ liệu và tính xác định theo thời điểm đều ảnh hưởng người gọi. Chữ ký không tự cam kết những thuộc tính này.

**Câu 5.** `@Override` chứng minh được số dư phép đã được kiểm tra đúng không?

**Gợi ý:** Không. Nó chỉ xác nhận quan hệ override ở mức compiler; phải kiểm thử hậu điều kiện và các ngữ nghĩa đã hứa.

**Câu 6.** Có nên thêm `ILeaveReviewService` cho mỗi class để “đạt chuẩn OOP”?

**Gợi ý:** Không có quy tắc như vậy. Chỉ thêm một tầng hợp đồng khi có ranh giới phụ thuộc, nhu cầu thay thế hoặc nhóm hành vi thực sự độc lập.

**Câu 7.** Cùng một `LeavePolicy` có được vừa đánh giá vừa trừ quota không?

**Gợi ý:** Không theo hợp đồng đang nêu. Muốn thực hiện cấp phép và ghi sổ ngày phép phải thiết kế use case riêng, transaction và kiểm tra đồng thời. Không được âm thầm thay đổi trách nhiệm của `evaluate`.

## Checklist thiết kế hợp đồng dùng được lâu dài

Trước khi chốt một API, hãy hỏi: **Ai gọi?**; **input/output và đơn vị có rõ không?**; **điều kiện trước/sau nào caller được dựa vào?**; **lỗi, side effect, thời điểm và đồng thời được hứa đến đâu?**; **hai implementation có thay thế hợp lệ không?**; **có contract test chung không?**; **lộ chi tiết hạ tầng nào không cần thiết không?**

Hợp đồng là **đường biên tin cậy** giữa code sử dụng và cách thực hiện. Trừu tượng tốt cho phép bên trong được thay đổi có kiểm soát mà không bắt bên ngoài đoán ý nghĩa của mỗi implementation.