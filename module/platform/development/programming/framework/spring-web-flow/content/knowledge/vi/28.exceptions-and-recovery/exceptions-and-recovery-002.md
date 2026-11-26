# Bắt lỗi trong action và trả sự kiện có ý nghĩa

> **Chương:** Ngoại lệ và phục hồi  
> **Mục tiêu:** Thiết kế action trong Spring Web Flow có khả năng nhận diện kết quả nghiệp vụ, bắt đúng những lỗi kỹ thuật có thể xử lý và trả về **event có ý nghĩa** để flow đi theo transition phù hợp. Bài học sử dụng một quy trình đặt lịch làm ví dụ, kết hợp Java, XML, form binding, MessageContext, scope, transaction và kiểm thử.

## 1. Action nằm ở đâu trong hành trình Web Flow?

Giả sử một người đặt lịch tư vấn theo quy trình **chọn khung giờ → nhập thông tin → xem lại → xác nhận**. Khi nhấn **Xác nhận**, người dùng mong đợi một trong các kết quả:

- Lịch được tạo thành công.
- Khung giờ vừa được người khác đặt, cần chọn lại.
- Yêu cầu đã được ghi nhận ở lần gửi trước, nên hiển thị lại kết quả đó.
- Hệ thống chưa xác định được yêu cầu đã ghi thành công hay chưa.
- Một dịch vụ cần thiết tạm thời không sẵn sàng, phải có đường phục hồi.

Trong **Spring Web Flow (SWF)**, các màn hình thường là `view-state`; thao tác gọi service để kiểm tra và lưu thường nằm ở `action-state`. **Action** tạo kết quả cho flow; **event** là tín hiệu kết quả; **transition** biến tín hiệu ấy thành việc đi tới state thích hợp.

~~~mermaid
flowchart TD
    A["view-state: review"] -->|"confirm"| B["action-state: submitBooking"]
    B -->|"booked"| C(("completed"))
    B -->|"slotUnavailable"| D["view-state: chooseSlot"]
    B -->|"statusUnknown"| E["view-state: pendingConfirmation"]
    B -->|"lookupUnavailable"| F["view-state: temporaryProblem"]
~~~

Người dùng chỉ gửi event **confirm**. Các event **booked**, **slotUnavailable**, **statusUnknown** và **lookupUnavailable** phát sinh từ action sau khi gọi service. Vì thế, không nên gắn toàn bộ trường hợp “không thành công” với một event chung `error` không có ngữ nghĩa.

Điều hành trình cần biết là **kết quả nào đã được xác định** và **bước nào giúp người dùng tiếp tục một cách an toàn**.

## 2. Phân biệt kết quả nghiệp vụ và ngoại lệ kỹ thuật

Trước khi viết một khối `try/catch`, hãy phân loại kết quả. Một yêu cầu bị từ chối theo quy tắc nghiệp vụ không nhất thiết là exception; ngược lại, exception kỹ thuật có thể xảy ra khi hệ thống chưa biết kết quả.

| Tình huống | Bản chất | Cách action nên xử lý |
| --- | --- | --- |
| Khung giờ đã có người đặt | Kết quả nghiệp vụ đã biết | Nhận outcome `SLOT_UNAVAILABLE`, phát event `slotUnavailable` |
| Đã đặt thành công với cùng request ID | Kết quả hợp lệ của thao tác lặp | Trả lại mã đặt chỗ cũ, phát event `booked` |
| Form thiếu email | Lỗi binding/validation ở view-state | Giữ form, hiển thị lỗi field, chưa gọi action ghi |
| Tra cứu danh sách giờ tạm timeout **trước khi ghi** | Lỗi kỹ thuật có thể xử lý an toàn | Phát `lookupUnavailable` nếu lớp service phân loại được |
| Timeout sau khi gửi lệnh ghi, chưa biết đã commit chưa | Trạng thái ghi **không xác định** | Phát `statusUnknown`, chuyển sang kiểm tra kết quả |
| NullPointerException do lỗi lập trình | Lỗi kỹ thuật ngoài dự kiến | Để cơ chế xử lý exception ghi nhận, không giả vờ là lỗi người dùng |
| Không có quyền tạo lịch | Lỗi xác thực/phân quyền hoặc kết quả chính sách được bảo vệ | Từ chối theo tầng bảo mật/service, không bỏ qua quyền bằng transition |

Mẫu tư duy cần áp dụng:

~~~text
Action nhận yêu cầu
    |
    +-- Service trả kết quả nghiệp vụ rõ ràng
    |       +-- CONFIRMED         -> event booked
    |       +-- SLOT_UNAVAILABLE -> event slotUnavailable
    |       +-- ALREADY_BOOKED   -> event booked (cùng kết quả cũ)
    |
    +-- Service nhận diện sự cố kỹ thuật có thể xử lý
    |       +-- Chưa có side effect -> event lookupUnavailable
    |       +-- Kết quả ghi chưa rõ -> event statusUnknown
    |
    +-- Exception ngoài dự kiến -> cơ chế exception handling
~~~

**Lưu ý:** Một message `ERROR` hiển thị cho người dùng và một event `slotUnavailable` có hai vai trò riêng. Message diễn giải vấn đề; event chọn transition. Thêm message vào `MessageContext` không tự động kích hoạt transition `on="error"`.

## 3. Chọn tên event theo ý nghĩa kết quả

Event ID là một phần hợp đồng giữa action và flow definition. Các tên nên giúp người đọc hiểu trạng thái sau khi action chạy.

| Event | Nghĩa được cam kết | State đích đề xuất |
| --- | --- | --- |
| `booked` | Hệ thống biết đã có lịch xác nhận, gồm trường hợp request lặp trả kết quả cũ | `completed` |
| `slotUnavailable` | Hệ thống biết giờ yêu cầu không còn khả dụng | `chooseSlot` |
| `lookupUnavailable` | Tác vụ tra cứu an toàn đã thất bại trước khi ghi | `temporaryProblem` |
| `statusUnknown` | Chưa xác định lệnh ghi đã commit hay chưa | `pendingConfirmation` |
| `pending` | Yêu cầu vẫn đang được đối soát | `pendingConfirmation` |
| `requiresSupport` | Không thể tự xác định kết quả trong chính sách hiện tại | `manualRecovery` |

Tên `error` không phải lúc nào cũng sai, nhưng với nhiều đường phục hồi nó khiến người đọc phải xem code mới biết người dùng cần làm gì. Các tên `slotUnavailable`, `statusUnknown` giúp test và log rõ ràng hơn.

**Không nên đặt event theo tên exception Java** như `SQLTimeoutException`. Flow cần mô tả kết quả ở mức nghiệp vụ/trải nghiệm. Chi tiết hạ tầng nằm trong service và log.

## 4. Thiết kế hợp đồng kết quả của service trước khi viết action

Một hướng dễ hiểu là để service trả về kiểu kết quả biểu diễn **những outcome dự kiến**, thay vì ném exception cho mọi nhánh.

~~~java
// Các kiểu nghiệp vụ minh họa, do ứng dụng tự định nghĩa.
public enum BookingStatus {
    CONFIRMED,
    ALREADY_CONFIRMED,
    SLOT_UNAVAILABLE
}

public final class BookingResult {
    private final BookingStatus status;
    private final String bookingId;

    public BookingResult(BookingStatus status, String bookingId) {
        this.status = status;
        this.bookingId = bookingId;
    }

    public BookingStatus getStatus() {
        return status;
    }

    public String getBookingId() {
        return bookingId;
    }
}

public interface BookingService {
    // Bảo đảm idempotency theo requestId ổn định của một ý định đặt lịch.
    BookingResult submitOnce(BookingDraft draft);

    // Chỉ đọc/đối soát trạng thái theo requestId, không tạo lịch mới.
    BookingLookupResult findByRequestId(String requestId);
}
~~~

`BookingDraft` và `BookingLookupResult` là các kiểu nghiệp vụ ứng dụng cần triển khai. Đối với code minh họa bên dưới, giả sử `BookingDraft` chứa `requestId`, `slotId` và thông tin người đặt. **requestId được tạo một lần cho một ý định đặt lịch và được giữ khi người dùng Back, sửa form hoặc retry.**

Hợp đồng `submitOnce` cần xác định rõ:

1. Khi ghi thành công, trả `CONFIRMED` cùng `bookingId`.
2. Nếu cùng `requestId` đã ghi trước đó, trả `ALREADY_CONFIRMED` và chính `bookingId` cũ.
3. Khi khung giờ không còn, trả `SLOT_UNAVAILABLE`, không tạo bản ghi.
4. Khi không biết thao tác ghi đã commit chưa, báo **trạng thái không xác định** theo hợp đồng kỹ thuật riêng; không khẳng định `SLOT_UNAVAILABLE`.
5. Lỗi lập trình hoặc cấu hình ngoài dự kiến được để lộ cho cơ chế xử lý exception chung, không chuyển thành outcome nghiệp vụ giả.

Service phải giữ bất biến ở tầng database bằng transaction, ràng buộc unique và xử lý đồng thời. **Kiểm tra trước rồi INSERT** mà không có ràng buộc phù hợp vẫn có race condition.

## 5. Action chuyển kết quả thành event trong Java

Spring Web Flow cung cấp `org.springframework.webflow.execution.Event` để biểu diễn event và `RequestContext` để truy cập ngữ cảnh hiện tại. Một action bean thông thường có thể có method trả về `Event`, được gọi bằng biểu thức `evaluate` trong flow XML.

Ví dụ dưới đây minh họa **đường xử lý chính**. Hai exception `AvailabilityLookupUnavailableException` và `BookingOutcomeUnknownException` là **kiểu do ứng dụng tự định nghĩa**, chỉ được service ném khi đã xác định đúng tính chất sự cố.

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public final class BookingAction {

    private final BookingService bookingService;

    public BookingAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public Event submit(RequestContext context) {
        BookingDraft draft =
                (BookingDraft) context.getFlowScope().get("draft");

        if (draft == null || draft.getRequestId() == null) {
            // Bất biến lập trình bị vi phạm; không giả vờ lỗi form.
            throw new IllegalStateException(
                    "Missing booking draft or requestId");
        }

        try {
            BookingResult result = bookingService.submitOnce(draft);

            if (result.getStatus() == BookingStatus.CONFIRMED
                    || result.getStatus() == BookingStatus.ALREADY_CONFIRMED) {
                context.getFlowScope().put(
                        "bookingId", result.getBookingId());
                return new Event(this, "booked");
            }

            if (result.getStatus() == BookingStatus.SLOT_UNAVAILABLE) {
                context.getMessageContext().addMessage(
                        new MessageBuilder()
                                .error()
                                .source("slotId")
                                .code("booking.slot.unavailable")
                                .defaultText(
                                        "Khung giờ đã hết. Vui lòng chọn lại.")
                                .build());
                return new Event(this, "slotUnavailable");
            }

            // Outcome chưa được định nghĩa: lỗi hợp đồng service.
            throw new IllegalStateException(
                    "Unsupported booking status: " + result.getStatus());

        } catch (AvailabilityLookupUnavailableException ex) {
            // Chỉ bắt khi service bảo đảm chưa phát sinh tác vụ ghi.
            context.getMessageContext().addMessage(
                    new MessageBuilder()
                            .warning()
                            .code("booking.lookup.unavailable")
                            .defaultText(
                                    "Chưa kiểm tra được lịch trống.")
                            .build());
            return new Event(this, "lookupUnavailable");

        } catch (BookingOutcomeUnknownException ex) {
            // Có thể đã commit: giữ requestId để đối soát, không tạo ID mới.
            context.getFlowScope().put(
                    "pendingRequestId", draft.getRequestId());
            return new Event(this, "statusUnknown");
        }
    }
}
~~~

Đây là khung dạy học: các kiểu `BookingDraft`, exception và service phải được ứng dụng triển khai, bean phải được đăng ký và hành vi lưu/tra cứu cần được kiểm thử. **Không được ném `AvailabilityLookupUnavailableException` cho một timeout có thể xảy ra sau khi ghi**, vì nhánh đó gợi ý người dùng thử lại.

### 5.1. Vì sao không bắt `Exception` hoặc `Throwable`?

Mẫu nguy hiểm:

~~~java
try {
    bookingService.submitOnce(draft);
    return new Event(this, "booked");
} catch (Exception ex) {
    return new Event(this, "slotUnavailable"); // SAI
}
~~~

Một exception có thể là lỗi database, sai cấu hình, thiếu quyền, bug hoặc trạng thái ghi chưa xác định. Chuyển tất cả thành `slotUnavailable` làm người dùng hiểu sai sự thật và gây khó chẩn đoán vận hành.

Ngay cả:

~~~java
catch (Exception ex) {
    return new Event(this, "retry");
}
~~~

cũng nguy hiểm nếu action vừa thực hiện thao tác ghi. Retry có thể tạo side effect lặp lại nếu tầng nghiệp vụ không thực sự idempotent.

**Chỉ bắt loại lỗi mà action biết cách xử lý đúng.** Các exception ngoài dự kiến phải đi theo chiến lược exception handling của Web Flow/Spring MVC và được ghi nhận ở tầng quan sát phù hợp.

### 5.2. Bắt exception tại ranh giới phù hợp

Không phải exception nào cũng cần bắt trong action:

- **Validation đầu vào:** xử lý ở form binding/validator của `view-state`.
- **Kết quả nghiệp vụ dự kiến:** service trả enum/result type rõ ràng.
- **Lỗi kỹ thuật có nhánh phục hồi được kiểm chứng:** action có thể bắt exception chuyên biệt và trả event.
- **Lỗi ngoài dự kiến:** để exception handler của ứng dụng ghi log và trả phản hồi an toàn.

Nếu service của thư viện bên ngoài ném exception cho tình trạng hết chỗ, có thể **chuyển exception chuyên biệt thành kết quả nghiệp vụ ở lớp adapter/service**. Điều này giữ action độc lập với tên exception của nhà cung cấp.

## 6. Định nghĩa transition tương ứng trong XML

Flow XML dưới đây minh họa cách outcome của `BookingAction.submit` dẫn tới các state. Các view, bean, lớp model và cấu hình Spring MVC là phần ứng dụng phải cung cấp.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="chooseSlot">

    <var name="draft" class="com.example.booking.BookingDraft"/>

    <!-- Tạo requestId một lần; hàm này cần thiết lập draft. -->
    <on-start>
        <evaluate expression="bookingService.initializeDraft(draft)"/>
    </on-start>

    <view-state id="chooseSlot" view="booking/choose-slot" model="draft">
        <binder>
            <binding property="slotId" required="true"/>
        </binder>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="chooseSlot" bind="false"/>
        <transition on="confirm" to="submitBooking" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="submitBooking">
        <evaluate expression="bookingAction.submit(requestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="slotUnavailable" to="chooseSlot"/>
        <transition on="lookupUnavailable" to="temporaryProblem"/>
        <transition on="statusUnknown" to="pendingConfirmation"/>
    </action-state>

    <view-state id="temporaryProblem" view="booking/temporary-problem">
        <transition on="edit" to="chooseSlot" bind="false"/>
        <transition on="retry" to="submitBooking" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="pendingConfirmation" view="booking/pending">
        <transition on="checkStatus" to="checkBookingStatus" bind="false"/>
    </view-state>

    <action-state id="checkBookingStatus">
        <evaluate expression="bookingAction.checkStatus(requestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="pending" to="pendingConfirmation"/>
        <transition on="requiresSupport" to="manualRecovery"/>
    </action-state>

    <view-state id="manualRecovery" view="booking/manual-recovery"/>
    <end-state id="completed" view="booking/completed"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

Trong ví dụ, **`checkStatus` phải là thao tác tra cứu trạng thái**, không gọi lại lệnh tạo lịch. Method `bookingAction.checkStatus(requestContext)` là hợp đồng cần được triển khai riêng, với các event `booked`, `pending` và `requiresSupport`. `initializeDraft` cũng là method ứng dụng tự cung cấp; nó tạo một request ID ổn định khi bắt đầu flow.

### 6.1. Vì sao `temporaryProblem` và `pendingConfirmation` khác nhau?

- **temporaryProblem:** service đã phân loại được việc tra cứu thất bại **trước khi thao tác ghi**. Retry có thể được phép nếu thỏa chính sách về số lần thử, khoảng chờ và quyền.
- **pendingConfirmation:** lệnh ghi **có thể đã được thực hiện**. Người dùng được xem trạng thái hoặc yêu cầu hỗ trợ, không tự động tạo một yêu cầu mới.

Nếu dùng cùng một state `error` với nút `Retry` cho cả hai, người dùng có thể vô tình tạo đặt lịch trùng. Sự khác biệt trong event giúp diễn đạt chính sách phục hồi ngay trên sơ đồ flow.

### 6.2. Một event không có transition phù hợp

Nếu action trả `statusUnknown` nhưng XML chỉ khai báo `booked` và `slotUnavailable`, flow sẽ không tự biết phải đi đâu. Hành vi với event không được xử lý phụ thuộc cấu hình/framework, có thể dẫn đến lỗi thực thi.

Để tránh điều này, cần **kiểm tra tập event action có thể phát ra khớp với các transition của state** và có test cho từng nhánh. Khi thêm outcome nghiệp vụ mới vào service, phải cập nhật hợp đồng event/transition và view phục hồi tương ứng.

## 7. AbstractAction và event kết quả

Ngoài method bean thông thường, Spring Web Flow có cơ sở hạ tầng `org.springframework.webflow.action.AbstractAction` để triển khai action. Một implementation có thể override `doExecute(RequestContext)` và trả về `Event`:

~~~java
import org.springframework.webflow.action.AbstractAction;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public final class CheckPolicyAction extends AbstractAction {

    private final EligibilityService eligibilityService;

    public CheckPolicyAction(EligibilityService eligibilityService) {
        this.eligibilityService = eligibilityService;
    }

    @Override
    protected Event doExecute(RequestContext context) {
        boolean eligible = eligibilityService.isEligible(
                context.getFlowScope().get("draft"));
        return new Event(this, eligible ? "eligible" : "notEligible");
    }
}
~~~

`EligibilityService` là service minh họa do ứng dụng viết. Cách đăng ký action bean và gọi trong flow definition tùy mô hình cấu hình. Chọn method bean hay `AbstractAction` dựa trên khả năng tái sử dụng, kiểm thử và convention của dự án; **nguyên tắc phân loại outcome và exception không thay đổi**.

**Khi kết quả là boolean đơn giản**, event `eligible`/`notEligible` dễ hiểu. Với nghiệp vụ nhiều kết quả, kiểu enum/result rõ nghĩa ở service tránh việc nhét hàng loạt nhánh exception vào action.

## 8. MessageContext: báo lỗi cho người dùng mà vẫn giữ event rõ nghĩa

Một action thường cần trả **hai loại thông tin khác nhau**:

1. **Event ID** để flow chọn transition.
2. **Message** để giao diện giải thích tình huống.

Spring Web Flow cung cấp `RequestContext.getMessageContext()` và `MessageBuilder` để thêm message:

~~~java
context.getMessageContext().addMessage(
        new MessageBuilder()
                .error()
                .source("slotId")
                .code("booking.slot.unavailable")
                .defaultText("Khung giờ này đã có người đặt.")
                .build());

return new Event(this, "slotUnavailable");
~~~

Trong đoạn này:

- `error()` là mức độ thông báo.
- `source("slotId")` gắn thông báo với field chọn giờ.
- `code(...)` là khóa i18n để tra cứu tiếng Việt/tiếng Anh.
- `defaultText(...)` là nội dung dự phòng.
- Event `slotUnavailable` mới là thứ flow dùng để chuyển sang `chooseSlot`.

Một file tài nguyên có thể định nghĩa:

~~~properties
# messages_vi.properties
booking.slot.unavailable=Khung giờ này đã được đặt. Vui lòng chọn lại.
booking.lookup.unavailable=Chưa tải được danh sách giờ trống. Vui lòng thử lại.
booking.status.unknown=Chưa xác nhận được kết quả. Hãy kiểm tra trạng thái.
~~~

### 8.1. Cảnh báo về vòng đời thông báo

Message được thêm ở action-state **không mặc nhiên tồn tại qua mọi redirect và thay đổi state**. Cần kiểm tra cách Web Flow truyền/hiển thị `MessageContext` với view engine và phiên bản đang dùng.

Nếu `slotUnavailable` phải tồn tại qua nhiều bước, có thể giữ **mã lý do nghiệp vụ** trong scope phù hợp rồi tạo message khi render view đích, hoặc dùng cơ chế thông báo có vòng đời ngắn được cấu hình rõ ràng. Tránh để banner lỗi tồn tại mãi trong HTTP session chung.

## 9. Không retry khi chưa biết thao tác ghi đã commit hay chưa

Đây là tình huống phục hồi quan trọng nhất. Giả sử service đã gửi lệnh tạo booking đến database hoặc hệ thống ngoài, nhưng **response bị mất**. Action nhận timeout; người dùng chưa biết có booking hay không.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant F as Flow action
    participant S as BookingService
    participant D as Database
    U->>F: Confirm
    F->>S: submitOnce(requestId=R123)
    S->>D: Ghi booking R123
    D-->>S: Commit thành công
    Note over S,F: Response thất lạc/timeout
    S--xF: Kết quả chưa xác định
    F-->>U: statusUnknown, kiểm tra trạng thái
~~~

**Timeout không chứng minh thất bại**. Nếu action bắt `Exception` và trả event `failed`, người dùng có thể nghĩ chưa có đặt chỗ và bấm tạo mới. Cách an toàn hơn:

1. Giữ nguyên **requestId** của ý định đặt lịch.
2. Đưa flow đến `pendingConfirmation`, hiển thị trạng thái chưa chắc chắn.
3. Tra cứu bằng `findByRequestId(requestId)` hoặc cơ chế reconciliation của hệ thống.
4. Nếu đã xác nhận, hiển thị lại booking cũ.
5. Nếu vẫn chưa xác định được, giữ đường kiểm tra lại hoặc hỗ trợ; không tự khẳng định đã thất bại.

**Idempotency key** phải gắn với một thao tác logic, không dùng execution key của Web Flow làm khóa. Execution key có thể thay đổi khi flow tiến qua các snapshot; một thao tác nghiệp vụ vẫn cần cùng requestId qua retry.

### 9.1. Chống trùng ở service và database

Pseudocode cho `submitOnce`:

~~~text
submitOnce(draft):
    xác thực người dùng và kiểm tra quyền
    bắt đầu transaction
    tìm booking theo (userId, requestId)
    nếu đã có:
        trả ALREADY_CONFIRMED + bookingId cũ
    kiểm tra khung giờ và điều kiện hiện hành
    nếu không hợp lệ:
        trả SLOT_UNAVAILABLE
    tạo booking với unique(userId, requestId)
    commit
    trả CONFIRMED + bookingId mới
~~~

Đây là nguyên tắc, chưa phải thuật toán đồng thời hoàn chỉnh. Ràng buộc unique trong database, xử lý race condition, lock/version tài nguyên và quy tắc transaction phải được thiết kế tương ứng. Nếu service trả kết quả trước khi transaction commit bền vững, thông báo `booked` có thể là sai.

### 9.2. Retry an toàn có điều kiện

Retry **có thể** phù hợp khi:

- Chỉ gọi một thao tác đọc hoặc kiểm tra không có side effect.
- Hệ thống có idempotency theo cùng requestId và xác định rõ kết quả của lần trước.
- Có giới hạn số lần, khoảng đợi, timeout và cơ chế chống tải tăng đột biến.

Không nên tự retry vô hạn trong một `action-state`: một request HTTP sẽ bị giữ quá lâu, khó phản hồi kịp thời. Nhiều trường hợp cần quay lại view-state để người dùng được biết sự cố và quyết định hành động.

## 10. Lỗi validation và exception trong action

Một flow thực tế xử lý form binding và validation **trước khi đi đến action ghi**:

~~~mermaid
flowchart TD
    A["view-state: chooseSlot"] -->|"next"| B["Binding/Validation"]
    B -->|"sai dữ liệu"| A
    B -->|"hợp lệ"| C["view-state: review"]
    C -->|"confirm"| D["action-state: submitBooking"]
    D -->|"booked"| E["completed"]
    D -->|"slotUnavailable"| A
    D -->|"statusUnknown"| F["pendingConfirmation"]
~~~

Một email sai định dạng, `slotId` rỗng hoặc ngày không hợp lệ thường nên trả **field error** ngay tại form bằng validation. Không cần biến mọi lỗi nhập liệu thành exception trong `submitBooking`.

Tuy nhiên, service vẫn phải **kiểm tra lại** dữ liệu và bất biến trước khi ghi: giữa lúc người dùng thấy trang review và nhấn confirm, khung giờ có thể bị người khác đặt. Đường từ chối nghiệp vụ `slotUnavailable` chính là nơi điều kiện đó được phản ánh lên flow.

### 10.1. `bind="false"` trên các event chỉ điều hướng

Ở màn hình review:

~~~xml
<transition on="edit" to="chooseSlot" bind="false"/>
<transition on="confirm" to="submitBooking" bind="false"/>
~~~

Vì review không phải form nhập, hai event trên có thể bỏ qua binding. Với một view có dữ liệu đang sửa, `bind="false"` sẽ bỏ qua những giá trị chưa được cập nhật vào model; cần chọn theo yêu cầu trải nghiệm.

## 11. Exception handler và lỗi ngoài dự kiến

**Action chỉ nên bắt những lỗi mà nó có chính sách xử lý cụ thể.** Những lỗi như sai cấu hình expression, bean không tồn tại, bug null reference hay lỗi hạ tầng không phân loại được cần được chuyển đến cơ chế xử lý exception phù hợp của Web Flow và ứng dụng web.

Một chiến lược tốt thường có các lớp trách nhiệm:

| Vị trí | Trách nhiệm |
| --- | --- |
| Validator / Binder | Báo sai đầu vào và giữ form |
| Domain service | Trả business outcome đã biết, bảo vệ bất biến và transaction |
| Adapter hạ tầng | Chuyển lỗi thư viện thành lỗi kỹ thuật chuyên biệt khi có đủ bằng chứng |
| Action | Ánh xạ outcome/exception chuyên biệt thành event được định nghĩa |
| Exception handler của flow / tầng web | Ghi log, bảo vệ thông tin, trả trang lỗi an toàn cho lỗi chưa xử lý |

Web Flow có cơ chế xử lý exception trong vòng đời flow execution; cách đăng ký handler và các loại exception cụ thể phụ thuộc phiên bản/cấu hình. **Không nên coi `<transition on="error">` là cách bắt Java exception chung.** Transition nhận event đã phát ra; exception chưa được xử lý đi theo cơ chế khác.

### 11.1. Logging đủ thông tin nhưng không lộ dữ liệu

Khi xử lý một exception kỹ thuật đã phân loại, hệ thống có thể log:

- Flow ID và state đang xử lý.
- Mã tương quan/tracing.
- Loại lỗi kỹ thuật, dependency thất bại và thời điểm.
- Request ID nghiệp vụ đã được che giấu hoặc quản lý theo chính sách log.

Không ghi mật khẩu, token, thông tin cá nhân nhạy cảm hay toàn bộ model form vào log. Không trả stack trace hoặc SQL chi tiết trong `MessageContext` cho trình duyệt.

## 12. Scope và phiên khi flow cần phục hồi

Sau event `slotUnavailable`, người dùng thường muốn chọn lại giờ nhưng giữ tên, email. Vì vậy, một `BookingDraft` nhỏ gọn trong **flowScope** phù hợp hơn việc đặt toàn bộ bản nháp vào biến static hoặc session chung.

| Dữ liệu | Phạm vi gợi ý | Vì sao |
| --- | --- | --- |
| Thông tin liên hệ và slot đang chọn | `flowScope` | Cần qua nhiều state của một execution |
| `requestId` của thao tác đặt lịch | `flowScope` và cơ chế bền vững phù hợp khi cần đối soát | Giữ ổn định qua retry và timeout |
| Danh sách giờ gợi ý riêng màn hình | `viewScope` hoặc nạp lại theo request | Không cần giữ quá lâu |
| Thông báo lỗi field | `MessageContext`/validation | Hiển thị đúng bước và chu kỳ xử lý |
| Booking đã commit | Database | Dữ liệu bền vững, không phụ thuộc flow execution |

Nếu **session/flow execution hết hạn** trước lúc người dùng kiểm tra kết quả, không nên tạo một requestId mới rồi đoán rằng booking chưa được tạo. Đường phục hồi dài hạn phải dùng nguồn dữ liệu bền vững và xác minh quyền người dùng.

Một flow execution có thể có snapshot cũ. Việc Back/Forward của trình duyệt hoặc khôi phục snapshot cũ cũng **không rollback** những transaction đã commit. Bảo vệ chống submit lặp phải nằm ở service/database.

## 13. Subflow và exception: nên trả điều gì cho flow cha?

Một flow đăng ký có thể gọi subflow **verifyPhone**. Khi flow con kết thúc, flow cha cần nhận một kết quả có ý nghĩa như `verified` hoặc `cancelled`. Nếu vượt số lần thử, kết quả `locked` có thể đưa flow cha tới màn hình giải thích.

~~~mermaid
flowchart TD
    A["Flow cha: review"] --> B["subflow-state: verifyPhone"]
    B --> C["Flow con: enterCode"]
    C -->|"verified"| D["Flow con: end verified"]
    C -->|"locked"| E["Flow con: end locked"]
    D -->|"outcome verified"| F["Flow cha: submitBooking"]
    E -->|"outcome locked"| G["Flow cha: recovery"]
~~~

Nếu trong subflow có lỗi cấu hình hoặc dịch vụ xác minh bị lỗi kỹ thuật, **không nên tự động phát `verified` hoặc `locked`**. Nó cần một đường phục hồi kỹ thuật thích hợp hoặc handler ngoại lệ.

Flow con nên trả **outcome và dữ liệu kết quả có hợp đồng rõ ràng** qua input/output; flow cha tự quyết định thông báo/transition tương ứng. Không dựa vào việc message của view con sẽ tự tồn tại ở mọi view của flow cha.

## 14. Kiểm thử action có bắt lỗi và trả đúng event không?

Một bộ test hữu ích phải ép từng outcome cụ thể và kiểm tra **event, transition, side effect, message**.

| Trường hợp | Service trả về hoặc ném gì | Event mong đợi | Kết quả cần xác minh |
| --- | --- | --- | --- |
| Tạo booking thành công | `CONFIRMED` | `booked` | Có bookingId, đi `completed` |
| Request đã xử lý trước đó | `ALREADY_CONFIRMED` | `booked` | Dùng ID cũ, không tạo booking mới |
| Khung giờ hết | `SLOT_UNAVAILABLE` | `slotUnavailable` | Đến `chooseSlot`, có message thích hợp |
| Tra cứu tạm lỗi trước write | `AvailabilityLookupUnavailableException` | `lookupUnavailable` | Đến `temporaryProblem`, chưa ghi DB |
| Kết quả ghi chưa xác định | `BookingOutcomeUnknownException` | `statusUnknown` | Giữ requestId, đến `pendingConfirmation` |
| Ngoại lệ lập trình | `NullPointerException` ngoài dự kiến | Không có event nghiệp vụ giả | Exception handler nhận được |
| Service trả trạng thái lạ | Outcome không có trong contract | Exception lỗi hợp đồng | Không âm thầm coi là thành công |
| Xác nhận hai lần cùng request ID | Hai request đồng thời | Kết quả đúng theo idempotency | Tối đa một booking cho ý định đó |

### 14.1. Unit test của action (pseudocode)

~~~text
given draft.requestId = "R123"
and bookingService.submitOnce(draft)
    returns BookingResult(SLOT_UNAVAILABLE)

event = bookingAction.submit(requestContext)

assert event.id == "slotUnavailable"
assert messageContext contains:
    severity = ERROR
    source = "slotId"
    code = "booking.slot.unavailable"
assert bookingId has not been created
~~~

Đây là **pseudocode**, không phải một API Java để chạy nguyên văn. Khi triển khai, dùng mock/stub cho service và RequestContext phù hợp phiên bản Web Flow.

### 14.2. Flow test: action event có dẫn tới đúng state không?

Ngoài unit test, cần test flow XML:

~~~text
start flow booking
submit next with slotId valid       -> state review
submit confirm, service SOLD_OUT    -> state chooseSlot
submit confirm, service CONFIRMED   -> state completed
submit confirm, result UNKNOWN      -> state pendingConfirmation
submit checkStatus, result PENDING  -> state pendingConfirmation
submit checkStatus, result BOOKED   -> state completed
~~~

Các lời gọi là mô tả kịch bản, không phải cú pháp test cố định. Test phải xác nhận người dùng **không thể phát event `confirm` từ state không có transition đó** và lỗi validation giữ họ ở form.

### 14.3. Integration test của transaction

Unit test action không chứng minh idempotency. Cần integration test với repository/database hoặc fake đủ sát thực tế để xác minh:

- Hai request có cùng `requestId` không tạo hai bản ghi.
- Timeout sau khi commit được đối soát lại thành booking cũ.
- Slot bị chiếm giữa bước review và confirm không cho ghi trùng.
- Request từ tab cũ, snapshot cũ hoặc phiên hết hạn không vượt qua phân quyền.
- Việc retry có giới hạn và không quay vòng vô hạn tại action-state.

## 15. Những lỗi thường gặp khi xử lý exception trong action

### Bắt mọi exception rồi trả `error`

Code trở nên ngắn nhưng mất khả năng phân biệt dữ liệu sai, lỗi quyền, bug và trạng thái ghi chưa xác định. Nên dùng outcome có kiểu và các exception chuyên biệt.

### Đặt tên event trùng tên exception Java

Tên `SQLTimeoutException` làm flow phụ thuộc vào hạ tầng. Hãy dùng `lookupUnavailable` hoặc `statusUnknown` khi trạng thái đã được phân loại đúng.

### Thêm message nhưng quên trả event

Message giúp hiển thị lỗi, **không tự chọn transition**. Action cần trả event phù hợp hoặc để exception handler tiếp quản.

### Trả event phục hồi nhưng XML không có transition

Nếu Java có `statusUnknown` mà XML không có `on="statusUnknown"`, flow có thể mắc lỗi xử lý. Kiểm tra hợp đồng Java/XML và viết test từng outcome.

### Gộp mọi lỗi kỹ thuật thành `retry`

Retry sau một commit không rõ ràng có thể tạo side effect trùng. Đối soát bằng request ID ổn định; chỉ retry khi an toàn hoặc service thật sự idempotent.

### Thử lại bằng requestId mới

Một ý định nghiệp vụ có thể bị ghi thành nhiều giao dịch. Request ID phải được giữ xuyên các lần thử hợp lệ và được bảo vệ bởi database.

### Gửi message “đã thất bại” khi chưa biết kết quả

Mất response sau commit không chứng minh giao dịch thất bại. Cần trình bày **“chưa xác nhận được”** và cho kiểm tra trạng thái.

### Dùng message lỗi kỹ thuật để bỏ qua kiểm tra quyền

Mọi lần gọi service ghi/đối soát vẫn cần xác thực và phân quyền. Không vì thao tác trước timeout mà cho phép client gửi một event bí mật để bỏ qua policy.

## 16. Bài thực hành: refactor action xử lý lỗi sai cách

Cho action ban đầu sau:

~~~java
public Event confirm(RequestContext context) {
    try {
        checkoutService.submit(
                context.getFlowScope().get("draft"));
        return new Event(this, "success");
    } catch (Exception ex) {
        context.getMessageContext().addMessage(
                new MessageBuilder()
                        .error()
                        .defaultText("Đăng ký thất bại. Nhấn thử lại.")
                        .build());
        return new Event(this, "error");
    }
}
~~~

**Yêu cầu sửa:**

1. Định nghĩa ít nhất ba outcome nghiệp vụ có tên và ý nghĩa rõ ràng: thành công, yêu cầu đã xử lý, và không đủ điều kiện.
2. Tạo một exception chuyên biệt cho lỗi tra cứu có thể retry **khi chắc chắn chưa ghi**; tạo một trạng thái riêng cho việc không biết transaction đã commit chưa.
3. Trả các event như `confirmed`, `notEligible`, `lookupUnavailable`, `statusUnknown` và viết XML transition tương ứng.
4. Giữ một request ID cố định qua Back, sửa form, retry và đối soát.
5. Thêm `MessageContext` với code, source và severity phù hợp cho lỗi có thể hiển thị; không đưa stack trace ra view.
6. Thiết kế state `pendingConfirmation` chỉ cho phép **tra cứu kết quả** và các bước phục hồi an toàn.
7. Viết unit test từng event, flow test từng transition và integration test submit lặp khi mất response.

**Tiêu chí đạt:** Người dùng nhận thông tin phù hợp với điều hệ thống thực sự biết; service không tạo bản ghi trùng; lỗi lập trình không bị ngụy trang thành từ chối nghiệp vụ; mọi event action trả về đều có đường đi được định nghĩa và kiểm thử.

## 17. Tổng kết và câu hỏi ôn tập

Trong Spring Web Flow, action nên **dịch kết quả service thành event có ý nghĩa** để `action-state` chọn transition. **Kết quả nghiệp vụ dự kiến** nên được mô hình hóa bằng kiểu kết quả rõ ràng. **Exception kỹ thuật** chỉ nên được bắt khi action biết cách phục hồi đúng; lỗi chưa xử lý đi theo cơ chế exception handling của hệ thống. **MessageContext** giải thích cho người dùng, còn **event/transition** điều phối flow.

Khi thao tác ghi có thể đã commit nhưng response bị mất, hãy phát một kết quả kiểu **`statusUnknown`**, giữ request ID và đối soát thay vì kết luận thất bại hay gửi lại vô điều kiện. Scope, session, browser history và subflow ảnh hưởng cách người dùng quay lại một bước; chúng không thay thế transaction, quyền truy cập hoặc idempotency ở service/database.

**Câu hỏi ôn tập:**

1. Vì sao `SLOT_UNAVAILABLE` thường nên là outcome nghiệp vụ thay vì một exception kỹ thuật chung?
2. Message `ERROR` khác event `slotUnavailable` ở vai trò nào?
3. Có nên bắt `RuntimeException` rồi trả `retry` cho mọi lỗi không? Vì sao?
4. Nếu timeout xuất hiện sau khi lệnh INSERT đã commit, event nào phù hợp và tại sao?
5. Nếu action trả `statusUnknown` nhưng XML không có transition tương ứng, cần kiểm tra điều gì?
6. Vì sao request ID nghiệp vụ phải độc lập với execution key của Web Flow?
7. Làm sao kiểm thử riêng tính đúng của event/transition và tính idempotent của database?
