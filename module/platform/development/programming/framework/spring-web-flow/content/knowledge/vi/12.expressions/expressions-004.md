# Tham chiếu Spring bean và gọi phương thức trong biểu thức Web Flow

> **Chương:** Biểu thức  
> **Module:** SPRING_WEB_FLOW  
> **Mục tiêu:** Biết cách gọi Spring bean từ flow definition bằng biểu thức, truyền dữ liệu theo scope, nhận kết quả, xử lý event và exception; phân biệt việc đọc dữ liệu với hành động ghi nghiệp vụ; cấu hình, bảo mật và kiểm thử các biểu thức trong hành trình web nhiều bước.

## 1. Bài toán: định nghĩa flow cần gọi code Java

Hãy xét một quy trình **đặt lịch tư vấn**:

1. Người dùng chọn khung giờ tại `chooseSlot`.
2. Web Flow kiểm tra điều kiện cho phép xem lại.
3. Người dùng xác nhận tại `review`.
4. Service tạo booking, hoặc trả về lý do chưa thể đặt.

XML flow rất thích hợp để mô tả **state**, **event** và **transition**, nhưng không nên chứa các phép truy vấn, giao dịch hay quy tắc nghiệp vụ phức tạp. Những phần này thường thuộc các Spring bean đã được quản lý bởi ApplicationContext.

Thay vì nhúng nghiệp vụ vào XML, ta khai báo biểu thức:

~~~xml
<evaluate expression="bookingCatalog.findAvailableSlots()"
          result="viewScope.availableSlots"/>
~~~

Biểu thức yêu cầu Web Flow tìm bean mang tên `bookingCatalog`, gọi method `findAvailableSlots()` và gán giá trị trả về vào `viewScope.availableSlots`. Nó là **điểm nối giữa flow definition và logic ứng dụng**, không phải một đoạn Java được viết trực tiếp vào XML.

Điểm cần ghi nhớ:

- **Spring bean** cung cấp implementation và các dependency.
- **Expression** xác định bean, method, tham số và có thể cả nơi nhận kết quả.
- **FlowExecutor** đánh giá expression tại mốc được khai báo.
- **Event/transition** quyết định bước tiếp theo, không dựa vào tên method đơn thuần.

## 2. Expression tham chiếu bean hoạt động thế nào?

Trong một thiết lập Spring Web Flow điển hình, biểu thức có thể truy cập các bean từ Spring ApplicationContext nhờ cơ chế phân giải biến và bean của Web Flow.

~~~text
Spring ApplicationContext
  ├─ bookingCatalog
  ├─ bookingPolicy
  ├─ bookingService
  └─ bookingAction
           |
           v
Flow definition
  <evaluate expression="bookingAction.submit(requestContext)"/>
           |
           v
Web Flow expression evaluator
  -> phân giải "bookingAction"
  -> chọn method "submit"
  -> phân giải tham số "requestContext"
  -> gọi method
  -> trả kết quả cho action-state/flow
~~~

Các khái niệm quan trọng:

| Phần biểu thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tên bean | Định danh một đối tượng được Spring quản lý | `bookingCatalog` |
| Truy cập thuộc tính | Đọc một property của đối tượng/scope | `flowScope.booking.slotId` |
| Lời gọi method | Thực hiện method có tham số | `bookingPolicy.canReview(flowScope.booking)` |
| Biến ngữ cảnh | Dữ liệu của execution/request | `requestContext`, `flowScope` |
| Kết quả | Giá trị được trả về sau đánh giá | `List<SlotView>`, `boolean`, `Event` |

**Lưu ý về cú pháp:** Spring Web Flow có các phiên bản và cơ chế biểu thức khác nhau trong hệ sinh thái Spring. Những biểu thức như `bookingService.load(...)` trong tài liệu Web Flow được phân giải theo **evaluation context của Web Flow**; không nên tự động thay bằng cú pháp tham chiếu bean `@bookingService` chỉ vì đã gặp cú pháp đó trong một ứng dụng SpEL độc lập. Cấu hình expression parser và phiên bản thư viện quyết định cú pháp thực sự được hỗ trợ.

### 2.1. Bean name và class name là hai thứ khác nhau

Giả sử Spring có:

~~~java
import org.springframework.stereotype.Service;

@Service("bookingCatalog")
public class DefaultBookingCatalog {
    public java.util.List<SlotView> findAvailableSlots() {
        // Ví dụ: trả dữ liệu chỉ đọc để hiển thị.
        return java.util.Collections.emptyList();
    }
}
~~~

Trong XML, tham chiếu là `bookingCatalog`, **không phải** `DefaultBookingCatalog`. Class và method trên chỉ là ví dụ minh họa; `SlotView` là kiểu ứng dụng tự định nghĩa.

Nếu dùng `@Component` không khai báo tên, Spring thường suy tên bean theo quy tắc đặt tên mặc định. Tuy nhiên, đối với flow được duy trì lâu dài, **đặt tên bean rõ ràng và nhất quán** thường dễ đọc hơn khi viết biểu thức.

### 2.2. Bean phải nằm trong ApplicationContext được Web Flow nhìn thấy

Một class Java được tạo bằng `new`, hoặc một bean chỉ tồn tại trong ApplicationContext không nằm trong phạm vi phân giải của Web Flow, sẽ không tự nhiên được tìm thấy từ expression.

Khi debug lỗi “không tìm thấy bean”, hãy xác nhận:

1. Bean đã được đăng ký qua annotation scan hoặc cấu hình Spring chưa?
2. Tên bean có trùng chính xác tên trong expression không?
3. FlowBuilderServices/FlowExecutor/registry đang dùng ApplicationContext nào?
4. Có nhiều application context cha/con khiến bean không nằm trong vùng nhìn thấy không?
5. Có bean hoặc biến khác cùng tên gây hiểu nhầm khi tra cứu không?

## 3. Phân biệt bean và biến trong flow scope

Một flow execution có nhiều scope. Ví dụ:

~~~text
bookingService           -> bean Spring (logic nghiệp vụ)
bookingCatalog           -> bean Spring (đọc dữ liệu)
flowScope.booking        -> bản nháp của execution hiện tại
viewScope.availableSlots -> dữ liệu riêng cho view hiện tại
requestParameters.slotId -> chuỗi tham số HTTP
requestContext           -> ngữ cảnh thực thi Web Flow
~~~

| Thành phần | Ai quản lý? | Vòng đời | Dùng để làm gì? |
| --- | --- | --- | --- |
| Spring bean | Spring container | Theo scope của bean, thường singleton | Chứa service, policy, action, converter |
| `flowScope` | Web Flow | Trong một flow execution | Giữ DTO/bản nháp qua nhiều state |
| `viewScope` | Web Flow | Trong lúc view-state đang hoạt động | Dữ liệu dành riêng màn hình |
| `requestScope` | Web Flow | Trong lần xử lý request | Dữ liệu ngắn hạn |
| `conversationScope` | Web Flow | Trong conversation, có thể liên quan flow/subflow | Dữ liệu chia sẻ theo thiết kế |
| `requestParameters` | HTTP request | Một request | Nhận dữ liệu thô từ trình duyệt |

Một **bean singleton** có thể được gọi từ nhiều flow execution đồng thời. Vì vậy, không đặt bản nháp của từng người dùng vào field có thể thay đổi của singleton service.

**Sai hướng:**

~~~java
@Service("bookingService")
public class BookingServiceImpl {
    private BookingDraft currentBooking; // Không an toàn khi dùng chung.
}
~~~

**Hướng phù hợp:** giữ `BookingDraft` trong flow execution, truyền nó vào method service khi cần. Service thường không giữ dữ liệu tạm của từng trình duyệt trong instance field.

### 3.1. Vì sao nên tham chiếu scope tường minh?

Trong ví dụ và các flow phức tạp, `flowScope.booking` rõ nghĩa hơn một tên `booking` đơn lẻ khi cần phân biệt với bean hoặc biến cùng tên. Tùy vị trí expression và cơ chế phân giải biến, Web Flow có thể hỗ trợ tên ngắn; nhưng cách viết tường minh làm giảm sự mơ hồ và giúp người đọc thấy vòng đời dữ liệu.

## 4. Các vị trí thường dùng expression gọi bean

Web Flow đánh giá biểu thức khi execution đi tới **điểm móc** được khai báo. Cùng một method có thể chạy số lần khác nhau tùy đặt ở đâu.

| Vị trí | Khi nào thực hiện? | Việc phù hợp |
| --- | --- | --- |
| `on-start` | Khi khởi động flow | Khởi tạo bản nháp, request ID |
| `on-entry` | Khi vào một state | Chuẩn bị dữ liệu cho bước đó |
| `on-render` | Khi view được chuẩn bị render theo cơ chế Web Flow | Nạp thông tin hiển thị có thể thay đổi |
| `transition` | Khi transition được chấp nhận | Chuẩn bị summary hoặc dữ liệu phụ thuộc event |
| `action-state` | Khi flow đi vào state thực thi action | Gọi service và phát outcome |
| `decision-state` | Khi kiểm tra điều kiện rẽ nhánh | Gọi policy đọc dữ liệu, trả boolean |
| `on-end` | Khi kết thúc flow | Dọn tài nguyên tạm phù hợp |

Không nên đặt thao tác **tạo đơn** trong `on-render`, vì view có thể được render nhiều lần do refresh hoặc quay lại. Một action có side effect phải được đặt ở bước nghiệp vụ có thể quản lý kết quả và retry, chẳng hạn `action-state reserve`.

### 4.1. Cùng một expression, mốc thực thi khác nhau

~~~xml
<!-- Gọi khi bắt đầu flow. -->
<on-start>
    <evaluate expression="bookingService.newDraft()"
              result="flowScope.booking"/>
</on-start>
~~~

~~~xml
<!-- Gọi khi chuẩn bị render view-state. -->
<on-render>
    <evaluate expression="bookingCatalog.findAvailableSlots()"
              result="viewScope.availableSlots"/>
</on-render>
~~~

~~~xml
<!-- Gọi khi action-state reserve được kích hoạt. -->
<action-state id="reserve">
    <evaluate expression="bookingAction.submit(requestContext)"/>
    <transition on="booked" to="completed"/>
</action-state>
~~~

**Mốc thực thi là một phần của yêu cầu nghiệp vụ**. Việc viết đúng tên bean và method vẫn chưa đủ nếu đặt expression vào thời điểm không phù hợp.

## 5. Ví dụ hoàn chỉnh: bean + expression + state + event

Đoạn XML sau mô tả một flow đặt lịch rút gọn. `BookingDraft`, các bean Java, view, validator và cấu hình Spring MVC/Web Flow cần được ứng dụng cung cấp.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="chooseSlot">

    <!-- Mỗi execution có bản nháp riêng. -->
    <on-start>
        <evaluate expression="bookingService.newDraft()"
                  result="flowScope.booking"/>
    </on-start>

    <view-state id="chooseSlot"
                view="booking/choose-slot"
                model="booking">
        <on-render>
            <evaluate expression="bookingCatalog.findAvailableSlots()"
                      result="viewScope.availableSlots"/>
        </on-render>
        <binder>
            <binding property="slotId" required="true"/>
            <binding property="attendees" required="true"/>
        </binder>
        <transition on="next" to="checkReviewEligibility"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <decision-state id="checkReviewEligibility">
        <if test="bookingPolicy.canReview(flowScope.booking)"
            then="review"
            else="chooseSlot"/>
    </decision-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="chooseSlot" bind="false"/>
        <transition on="confirm" to="reserve" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="reserve">
        <evaluate expression="bookingAction.submit(requestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="slotUnavailable" to="chooseSlot"/>
        <transition on="statusUnknown" to="pending"/>
    </action-state>

    <view-state id="pending" view="booking/pending">
        <transition on="checkStatus" to="checkStatus" bind="false"/>
    </view-state>

    <action-state id="checkStatus">
        <evaluate expression="bookingAction.checkStatus(requestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="pending" to="pending"/>
    </action-state>

    <end-state id="completed" view="booking/completed"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

Flow cho thấy ba cách dùng method:

1. **Tạo dữ liệu:** `bookingService.newDraft()` trả một object, được gán vào `flowScope.booking`.
2. **Đọc/kiểm tra dữ liệu:** `bookingCatalog.findAvailableSlots()` trả danh sách, còn `bookingPolicy.canReview(...)` trả boolean để quyết định nhánh.
3. **Thực hiện nghiệp vụ:** `bookingAction.submit(requestContext)` trả một `Event` có ID tương ứng với transition trong `action-state`.

Các outcome `booked`, `slotUnavailable`, `statusUnknown` chỉ là các event do ứng dụng định nghĩa, **không phải loại exception được Web Flow tự tạo**.

### 5.1. Hành trình request dưới góc nhìn expression

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant F as FlowExecutor
    participant C as bookingCatalog
    participant P as bookingPolicy
    participant A as bookingAction
    participant S as bookingService

    U->>B: Mở /booking
    B->>F: GET khởi tạo flow
    F->>S: newDraft()
    S-->>F: BookingDraft
    F->>C: findAvailableSlots()
    C-->>F: Danh sách slot
    F-->>B: Trang chooseSlot

    U->>B: Nhập dữ liệu và Next
    B->>F: POST event=next
    F->>F: Bind/validate model
    F->>P: canReview(booking)
    P-->>F: true
    F-->>B: Trang review

    U->>B: Nhấn Confirm
    B->>F: POST event=confirm
    F->>A: submit(requestContext)
    A->>S: reserveOnce(booking)
    S-->>A: BookingOutcome
    A-->>F: Event booked/slotUnavailable/statusUnknown
    F-->>B: View hoặc redirect theo transition
~~~

Sơ đồ mô tả **thứ tự logic** chứ không xác định mọi chi tiết HTTP redirect, số lần render hay thứ tự callback. Cấu hình view rendering, repository và phiên bản Web Flow có thể làm phát sinh request bổ sung.

## 6. Ví dụ Java: khai báo Spring bean được gọi từ flow

Để XML ở trên có thể phân giải, ứng dụng cần đăng ký các bean với tên mà expression sử dụng.

~~~java
import org.springframework.stereotype.Service;

@Service("bookingService")
public class BookingServiceImpl implements BookingService {

    @Override
    public BookingDraft newDraft() {
        BookingDraft draft = new BookingDraft();
        draft.setRequestId(java.util.UUID.randomUUID().toString());
        return draft;
    }

    @Override
    public BookingOutcome reserveOnce(BookingDraft draft) {
        // Thực tế: xác thực quyền, validate cuối,
        // transaction và idempotency bằng requestId.
        throw new UnsupportedOperationException(
                "Ví dụ phải được ứng dụng triển khai");
    }
}
~~~

~~~java
import org.springframework.stereotype.Component;

@Component("bookingPolicy")
public class BookingPolicy {

    public boolean canReview(BookingDraft draft) {
        return draft != null
                && draft.getSlotId() != null
                && draft.getAttendees() != null
                && draft.getAttendees() > 0;
    }
}
~~~

~~~java
import org.springframework.stereotype.Component;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

@Component("bookingAction")
public class BookingAction {

    private final BookingService bookingService;

    public BookingAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public Event submit(RequestContext context) {
        BookingDraft draft =
                (BookingDraft) context.getFlowScope().get("booking");
        BookingOutcome outcome = bookingService.reserveOnce(draft);

        switch (outcome.getStatus()) {
            case CONFIRMED:
            case ALREADY_CONFIRMED:
                context.getFlowScope().put(
                        "bookingId", outcome.getBookingId());
                return new Event(this, "booked");
            case SLOT_UNAVAILABLE:
                return new Event(this, "slotUnavailable");
            case OUTCOME_UNKNOWN:
                return new Event(this, "statusUnknown");
            default:
                throw new IllegalStateException(
                        "Unhandled booking outcome");
        }
    }

    public Event checkStatus(RequestContext context) {
        // Ví dụ cần tự triển khai: chỉ đọc/đối soát bằng requestId.
        return new Event(this, "pending");
    }
}
~~~

`BookingDraft`, `BookingOutcome`, `BookingService`, `SlotView` và `bookingCatalog` là thành phần minh họa do ứng dụng tự định nghĩa. Để có ứng dụng chạy được, phải triển khai chúng và nối Spring/Web Flow theo phiên bản đang sử dụng.

### 6.1. Spring dependency injection vẫn hoạt động

Mặc dù XML gọi `bookingAction.submit(...)`, bản thân `BookingAction` vẫn là một Spring bean, có dependency `BookingService` được truyền qua constructor. Web Flow không phải tự tạo object mới hoặc tự quản lý connection database.

Điều này cho phép:

- Thay implementation service trong test.
- Dùng transaction và security interceptor ở ranh giới service phù hợp.
- Chia sẻ service cho MVC controller/API và flow mà không sao chép nghiệp vụ.
- Giữ flow XML chủ yếu là **bản đồ điều hướng**.

### 6.2. Cẩn thận với @Transactional

Nếu `reserveOnce` ghi database, transaction nên được thiết kế tại **service** và được gọi qua bean/proxy được Spring quản lý. Gọi cùng method nội bộ trên `this` có thể bỏ qua proxy của Spring trong một số cấu hình.

Không mở transaction trong `on-start` để giữ liên tục đến `review`; người dùng có thể dừng nhập form lâu và flow được tạm dừng giữa nhiều request HTTP.

## 7. Truyền tham số vào method

Biểu thức có thể truyền literal, dữ liệu từ scope hoặc ngữ cảnh request:

~~~xml
<!-- Truyền dữ liệu đã bind vào model. -->
<evaluate expression="bookingPolicy.canReview(flowScope.booking)"/>

<!-- Truyền chuỗi cố định, chỉ để minh họa method không ghi dữ liệu. -->
<evaluate expression="bookingCatalog.findByCategory('CONSULTING')"
          result="viewScope.categories"/>

<!-- Truyền chính RequestContext khi action cần điều phối message/scope. -->
<evaluate expression="bookingAction.submit(requestContext)"/>
~~~

Không phải method nào cũng cần cả `RequestContext`. Nếu chỉ cần `BookingDraft`, dùng method có tham số đúng kiểu và viết logic thuần Java sẽ dễ unit test hơn.

### 7.1. Truyền giá trị đã chuyển kiểu thay vì chuỗi thô

Giả sử form gửi:

~~~text
attendees=3&slotId=550e8400-e29b-41d4-a716-446655440000
~~~

Việc binding từ HTTP sang `BookingDraft` nên diễn ra ở `view-state`, với converter/validator rõ ràng. Sau đó service nhận DTO typed:

~~~java
public boolean canReview(BookingDraft draft) {
    return draft != null && draft.getAttendees() != null
            && draft.getAttendees() >= 1;
}
~~~

Tránh gọi trực tiếp một service nhạy cảm bằng chuỗi `requestParameters.attendees` rồi tự coi đó là số đã được xác thực. `requestParameters` chứa dữ liệu không đáng tin và chỉ thuộc request hiện tại.

### 7.2. Quá tải phương thức và null

Nếu bean có nhiều overload:

~~~java
public Quote estimate(Integer attendees) { /* ... */ }
public Quote estimate(String attendees)  { /* ... */ }
~~~

Expression evaluator phải chọn method từ kiểu tham số thực tế; khi giá trị `null` hoặc dạng chuỗi chưa convert, việc phân giải có thể không như mong đợi. Đối với API gọi từ flow, nên ưu tiên **method rõ tên, ít overload và tham số typed**.

Một property như `flowScope.booking.slotId` có thể là `null` nếu chưa được khởi tạo. Không để expression truy cập sâu vào null rồi hiển thị stack trace ra giao diện. Kiểm tra ràng buộc tại binder/validator và tạo nhánh từ chối phù hợp.

## 8. Nhận kết quả trả về: result và scope

Method có thể trả dữ liệu thay vì event. Với `<evaluate>`, thuộc tính `result` biểu thị nơi lưu kết quả theo cú pháp framework:

~~~xml
<on-start>
    <evaluate expression="bookingService.newDraft()"
              result="flowScope.booking"/>
</on-start>
~~~

~~~xml
<on-render>
    <evaluate expression="bookingCatalog.findAvailableSlots()"
              result="viewScope.availableSlots"/>
</on-render>
~~~

| Loại kết quả | Vị trí điển hình | Vì sao |
| --- | --- | --- |
| Bản nháp của flow | `flowScope.booking` | Cần qua nhiều state |
| Danh sách slot hiển thị | `viewScope.availableSlots` | Chỉ cần khi ở view hiện tại |
| Thông điệp/tính toán ngắn hạn | `requestScope` hoặc cơ chế message | Không cần giữ lâu |
| Mã booking đã được commit | Database; flowScope chỉ giữ ID để hiển thị | Kết quả nghiệp vụ bền vững độc lập execution |

**Không phải mọi kết quả đều nên đưa vào flowScope**. Danh sách dữ liệu lớn, connection, entity JPA còn attached hoặc tài nguyên mạng không phù hợp lưu trong snapshot execution. Giữ DTO nhỏ hoặc ID và truy vấn lại khi cần.

### 8.1. Phân biệt result dữ liệu và Event điều hướng

Hai ví dụ:

~~~xml
<!-- Lấy dữ liệu: lưu List vào viewScope. -->
<evaluate expression="bookingCatalog.findAvailableSlots()"
          result="viewScope.availableSlots"/>
~~~

~~~xml
<!-- Lấy outcome: action-state dùng Event chọn transition. -->
<action-state id="reserve">
    <evaluate expression="bookingAction.submit(requestContext)"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

Nếu method trả một `Event`, `action-state` có thể dùng event ID để chọn transition. Nếu method trả dữ liệu danh sách, **dữ liệu đó không tự tạo một state đích có ý nghĩa nghiệp vụ**. Hãy đặt method ở đúng vị trí và hiểu hợp đồng giá trị trả về.

## 9. Method trong decision-state nên là phép kiểm tra

`decision-state` thích hợp khi hướng đi có thể được xác định bằng một điều kiện rõ ràng:

~~~xml
<decision-state id="checkReviewEligibility">
    <if test="bookingPolicy.canReview(flowScope.booking)"
        then="review"
        else="chooseSlot"/>
</decision-state>
~~~

Method `canReview` nên **không tạo booking, không gửi email, không thay đổi balance**. Nó cần phản ánh một điều kiện có thể kiểm tra lại mà không tạo side effect.

Tại sao? Flow có thể được tiếp tục từ snapshot, thử lại hoặc đi qua decision-state thêm lần nữa. Nếu `canReview` ngầm ghi dữ liệu, request replay có thể tạo kết quả không mong muốn.

### 9.1. Kiểm tra ở decision-state không thay thế kiểm tra cuối

Giả sử `canReview` đã trả `true` vì khung giờ còn trống. Đến lúc người dùng nhấn Confirm vài phút sau, khung giờ có thể đã bị người khác đặt.

Vì vậy:

- Decision giúp điều hướng và trải nghiệm.
- Service `reserveOnce` vẫn kiểm tra **điều kiện hiện tại** trong transaction thích hợp.
- Khi không còn chỗ, action phát `slotUnavailable` để flow trở lại `chooseSlot`.

**Một biểu thức đúng không đồng nghĩa giao dịch đã an toàn.**

### 9.2. Khi nào method nên trả boolean, khi nào trả Event?

| Nhu cầu | Đầu ra nên cân nhắc | Cơ chế |
| --- | --- | --- |
| “Đủ dữ liệu để xem lại chưa?” | Boolean | `decision-state` |
| “Tạo booking được hay không?” | Outcome rõ nghĩa rồi chuyển thành `Event` | `action-state` |
| “Lấy danh sách slot để render” | Collection/DTO | `evaluate result=...` |
| “Chuẩn bị bản nháp” | DTO mới | `on-start` với `result` |

Tránh dùng boolean “true/false” cho một nghiệp vụ có ba hoặc bốn outcome khác nhau, vì sẽ mất thông tin phục hồi quan trọng.

## 10. Hành động có side effect chỉ chạy ở nơi phù hợp

Một method Java được gọi từ expression là **một lời gọi method thực sự**, không phải phép mô tả trừu tượng. Nó có thể ghi database, gọi API bên ngoài, gửi email hoặc ném exception.

| Vị trí | Có nên thực hiện tác vụ ghi quan trọng? | Lý do |
| --- | --- | --- |
| `on-render` | Không nên | View có thể render lại |
| `decision-state` | Không nên | Điều kiện có thể được đánh giá nhiều lần |
| `on-entry` của form | Thường không nên | Quay lại form có thể chạy lại |
| Action trên transition Next | Chỉ nếu có chủ đích và bảo vệ replay | Next thường là điều hướng |
| `action-state reserve` | Phù hợp nếu bảo vệ idempotency | Có outcome và nhánh phục hồi rõ ràng |
| `on-end` | Không nên là nguồn duy nhất của side effect sống còn | Kết thúc flow không phải transaction/outbox |

Ví dụ thao tác ghi dễ gặp lỗi:

~~~xml
<!-- KHÔNG NÊN: chỉ render review cũng tạo booking. -->
<view-state id="review" view="booking/review">
    <on-render>
        <evaluate expression="bookingService.reserveOnce(flowScope.booking)"/>
    </on-render>
</view-state>
~~~

Thay vào đó, để event `confirm` dẫn tới action-state và gọi service **chống trùng**.

### 10.1. Idempotency độc lập với execution key

Nếu response sau commit bị mất, người dùng có thể submit lại từ trang cũ. Execution key của Web Flow dùng cho việc tiếp tục flow/snapshot; **không nên dùng nó làm khóa idempotency nghiệp vụ**.

Một `requestId` bền vững của thao tác đặt lịch nên được tạo **một lần** trong bản nháp, được truyền đến `reserveOnce` và được bảo vệ bằng unique constraint thích hợp trong database.

Khi service biết request đã thành công trước đó, nên trả lại **booking ID cũ**. Khi chưa thể xác định commit, action cần trả `statusUnknown` và cho tra cứu/đối soát thay vì khẳng định thất bại.

## 11. Xử lý exception khi expression không chạy được

Lời gọi method qua expression có thể thất bại ở nhiều tầng:

1. **Không tìm thấy bean:** `bookingAction` không có trong ApplicationContext.
2. **Sai method hoặc chữ ký:** typo, số tham số sai, overload không phù hợp.
3. **Không chuyển được kiểu tham số:** method cần ID typed nhưng nhận chuỗi sai dạng.
4. **Null ở đường dẫn property:** `flowScope.booking` chưa có.
5. **Exception từ method:** service timeout, lỗi cấu hình, vi phạm ràng buộc.
6. **Không khớp Event/transition:** action trả outcome không có đường đi trong XML.

Không nên coi tất cả là “người dùng nhập sai”.

### 11.1. Phân loại lỗi để phục hồi đúng

| Lỗi | Tầng chịu trách nhiệm | Hướng xử lý |
| --- | --- | --- |
| Field form sai kiểu | Binder/converter/validator | Giữ view-state, báo lỗi field |
| Khung giờ vừa bị chiếm | Domain service | Outcome `SLOT_UNAVAILABLE`, action trả `slotUnavailable` |
| Bean không tồn tại | Wiring/config | Lỗi kỹ thuật; sửa cấu hình, không retry mù |
| Method không có chữ ký phù hợp | Code/definition | Lỗi triển khai; kiểm thử và sửa expression |
| Timeout trước thao tác ghi, chắc chắn không có side effect | Service/adapter | Có thể đưa tới nhánh thử lại có kiểm soát |
| Timeout sau lệnh ghi, kết quả chưa biết | Service/adapter | `statusUnknown`, tra cứu theo requestId |
| Lỗi lập trình bất ngờ | Exception handler | Log/trace an toàn, không giả mạo business event |

**Exception Java không tự biến thành event `error`** chỉ vì XML khai báo `<transition on="error">`. Action phải phát event có chủ đích sau khi phân loại được outcome, hoặc để cơ chế exception handler của Web Flow/MVC xử lý lỗi kỹ thuật.

### 11.2. Thông báo qua MessageContext

Khi service đã kết luận một outcome nghiệp vụ, action có thể tạo message:

~~~java
context.getMessageContext().addMessage(
    new org.springframework.binding.message.MessageBuilder()
        .error()
        .source("slotId")
        .code("booking.slot.unavailable")
        .defaultText("Khung giờ đã hết. Vui lòng chọn lại.")
        .build()
);
return new Event(this, "slotUnavailable");
~~~

`MessageContext` dùng để giải thích cho người dùng, còn `Event` dùng để điều hướng. Cần kiểm tra vòng đời message khi action-state chuyển sang view-state khác, đặc biệt nếu có redirect, để thông báo thực sự đến đúng màn hình.

## 12. Bean, expression và bảo mật

Expression có khả năng gọi method nên cần được xem như **một phần code ứng dụng đáng tin**, không phải mẫu chuỗi do người dùng kiểm soát.

### 12.1. Không ghép input HTTP thành expression

**Không an toàn:**

~~~text
expression = "bookingService." + requestParameters.methodName + "(...)"
~~~

Hệ thống không được cho client chọn tên bean hoặc method được thực thi. **Expression text phải cố định trong flow definition do dự án kiểm soát**, còn dữ liệu người dùng chỉ được truyền như **giá trị** qua binder và model đã validate.

Ví dụ tốt:

~~~xml
<evaluate expression="bookingPolicy.canReview(flowScope.booking)"/>
~~~

Tên method `canReview` cố định. Người dùng có thể thay đổi dữ liệu `booking` thông qua field được phép, nhưng không thể quyết định framework sẽ gọi method nào chỉ bằng request parameter.

### 12.2. Bean được tìm thấy không có nghĩa người dùng được phép gọi

Một service có thể được dùng cả từ MVC API lẫn Web Flow. Quyền thực hiện nghiệp vụ cần được kiểm tra ở **service/security boundary**, không chỉ dựa trên việc người dùng đã đi qua đúng state.

Trước khi tạo booking:

- Kiểm tra người dùng đã xác thực và có quyền đối với tài nguyên.
- Kiểm tra lại giá, số chỗ, điều kiện hiện hành, dữ liệu typed.
- Thực hiện transaction và cơ chế chống trùng.
- Không tin `slotId` hay `attendees` chỉ vì chúng đã được conversion.

Một client có thể tự sửa `_eventId` hoặc gửi request từ snapshot cũ. **Transition có cấu trúc tốt không thay thế phân quyền nghiệp vụ**.

### 12.3. Đừng ghi log tham số nhạy cảm

Khi debug expression, nên log **flow ID, state ID, tên bean/method và mã lỗi có kiểm soát**, không log toàn bộ `flowScope`, tham số request hay credential. Nếu ghi nguyên expression có chứa literal nhạy cảm, cũng phải che giấu phù hợp.

## 13. Hiệu năng: method có thể được gọi nhiều lần

Một expression có thể chạy trong cùng một execution nhiều lần:

- Người dùng quay về state cũ.
- View được render lại sau validation error.
- Trình duyệt refresh/retry request.
- Nhiều tab dùng chung execution hoặc snapshot hợp lệ.
- Flow chạy subflow rồi quay về state cha.

Vì vậy, cần phân biệt:

| Loại method | Thiết kế nên có |
| --- | --- |
| `findAvailableSlots()` | Đọc dữ liệu, có giới hạn truy vấn; có thể cache phù hợp |
| `canReview(draft)` | Nhẹ, không side effect, xác định trong cùng ngữ cảnh |
| `newDraft()` | Khởi tạo ở mốc rõ ràng, không chạy lại khi render |
| `reserveOnce(draft)` | Idempotent, transaction ngắn, trả outcome rõ |

### 13.1. Cân nhắc on-entry và on-render

`on-entry` phù hợp nếu dữ liệu chỉ cần nạp khi **đi vào state**. `on-render` phù hợp nếu cần tính lại mỗi lần render. Nhưng nếu danh sách khung giờ được truy vấn từ API chậm, gọi trong on-render có thể khiến validation error hoặc refresh làm tăng số lần truy vấn.

Lựa chọn mốc theo trải nghiệm mong muốn, cache/timeout và độ mới của dữ liệu. Dù UI hiển thị slot còn trống, service vẫn cần kiểm tra lại khi commit.

### 13.2. Không giữ kết nối hoặc entity sống lâu trong scope

Nếu `bookingCatalog.findAvailableSlots()` trả một tập entity JPA đang attached, lưu nó dài hạn trong `flowScope` có thể gây lỗi serialization/snapshot và dữ liệu lỗi thời. Nên trả DTO nhỏ gọn và chỉ giữ ID cần thiết.

## 14. Biểu thức ở flow cha và subflow

Một flow chính có thể gọi `verifyContact` để xác minh liên hệ:

~~~mermaid
flowchart TD
    P["Flow cha: review"] --> S["subflow-state verifyContact"]
    S --> V["Flow con: enterCode"]
    V -->|"verified"| R["Flow cha: reserve"]
    V -->|"cancelled"| C["Flow cha: review"]
~~~

Bean Spring như `verificationService` có thể được dùng trong flow con, nhưng **scope của flow cha và flow con không đồng nhất**. Không nên giả định `flowScope.booking` ở flow con là cùng biến trực tiếp với flow cha.

Hãy thiết kế **input/output** của subflow rõ ràng:

~~~xml
<subflow-state id="verifyContact" subflow="verifyContact">
    <input name="email" value="flowScope.booking.email"/>
    <transition on="verified" to="reserve"/>
    <transition on="cancelled" to="review"/>
</subflow-state>
~~~

Flow con cần khai báo input tương ứng và tự gọi bean xác minh bằng expression. Khi cần trả token/kết quả, dùng output hợp đồng được khai báo và kiểm tra ở flow cha. Đừng để bean singleton giữ “email hiện tại” của mọi user.

## 15. Kiểm thử bean resolution và method invocation

**Unit test của service** không đủ để chứng minh XML flow gọi đúng bean/method. Một bộ kiểm thử nên xác minh cả wiring, event và transition.

| Cấp kiểm thử | Kịch bản | Kết quả cần đạt |
| --- | --- | --- |
| Bean context test | Có `bookingAction`, `bookingPolicy`, `bookingCatalog` | Bean được resolve đúng tên |
| Unit policy | `canReview(validDraft)` | Trả true, không ghi database |
| Unit action | Service trả `SLOT_UNAVAILABLE` | Action trả Event `slotUnavailable` |
| Flow test | Bắt đầu flow | `newDraft()` được gọi, `flowScope.booking` có dữ liệu |
| Flow test | Enter/render `chooseSlot` | `findAvailableSlots()` được gọi tại mốc dự kiến |
| Flow test | `next` với form hợp lệ | `canReview(...)` chọn state review |
| Flow test | `next` với dữ liệu không hợp lệ | Binding/validation giữ view-state |
| Flow test | `confirm` khi còn chỗ | `booked` dẫn tới completed |
| Flow test | `confirm` khi hết chỗ | `slotUnavailable` dẫn tới chooseSlot |
| Flow test | Action trả event không khai báo | Test phát hiện lỗi contract XML/action |
| Integration | Gọi method qua proxy service | Transaction/security hoạt động |
| Integration | Submit cùng request ID hai lần | Không tạo booking trùng |
| Security | Client sửa event và field ngoài whitelist | Không vượt quyền hoặc mass assignment |

### 15.1. Unit test expression nghiệp vụ khác với flow test

Pseudocode:

~~~text
given bookingService.reserveOnce(draft)
    returns BookingOutcome(SLOT_UNAVAILABLE)

event = bookingAction.submit(requestContextWith(draft))
assert event.id == "slotUnavailable"
~~~

Test này chỉ xác minh action tạo event đúng. Cần test tiếp:

~~~text
flow = start("booking")
assert state(flow) == "chooseSlot"
assert flowScope.booking != null

submit(flow, event="next", validSlotAndAttendees)
assert state(flow) == "review"

submit(flow, event="confirm", serviceOutcome=SLOT_UNAVAILABLE)
assert state(flow) == "chooseSlot"
~~~

Đây là **pseudocode**, không phải API Java chạy nguyên văn. Test thực tế cần dùng cơ sở kiểm thử tương thích phiên bản Web Flow và context bean được cấu hình thật.

### 15.2. Test đối với method bị rename

Một lỗi thường xảy ra khi refactor Java từ `findAvailableSlots()` thành `listAvailableSlots()` mà không cập nhật XML. Do biểu thức có thể chỉ được giải quyết khi flow chạy đến một state cụ thể, ứng dụng có thể khởi động bình thường nhưng lỗi khi người dùng mở trang đó.

Nên có integration test đi qua **mọi state quan trọng**, bao gồm nhánh lỗi và subflow, để phát hiện:

- Sai tên bean.
- Sai tên method hoặc chữ ký tham số.
- Sai return type/outcome.
- Null path trong scope.
- Event Java trả về nhưng XML thiếu transition.

## 16. Cách chẩn đoán khi expression không hoạt động

Khi thấy lỗi “expression evaluation failed” hoặc flow không chuyển state, hãy kiểm tra theo thứ tự:

1. **Đã vào đúng state chưa?** Validation có thể chặn việc chuyển tiếp trước khi method dự kiến được gọi.
2. **Expression nằm ở mốc nào?** `on-start`, `on-entry`, `on-render`, transition hay action-state?
3. **Bean có tồn tại trong context mà Web Flow dùng không?** Tên trong XML có đúng chính tả?
4. **Method có public và chữ ký phù hợp không?** Tham số typed, overload hoặc `null` có gây sai resolution không?
5. **Dữ liệu scope có được tạo chưa?** `flowScope.booking` có còn tồn tại khi resume execution?
6. **Converter/validator có chạy đúng không?** Input từ HTTP đã thành `BookingDraft` hợp lệ?
7. **Method trả gì?** Collection, boolean, Event hay exception?
8. **Action-state có transition cho event đó không?** Event `statusUnknown` có đường đi tương ứng?
9. **Service có transaction và phân quyền phù hợp không?** Exception do Spring proxy/security có thể xảy ra khi gọi.
10. **Session/execution có hết hạn không?** Nếu key cũ không khôi phục được, method có thể chưa hề được gọi.

Một trace hữu ích (đã ẩn dữ liệu riêng tư):

~~~text
flow=booking
state=review
event=confirm
expressionBean=bookingAction
expressionMethod=submit
outcome=slotUnavailable
nextState=chooseSlot
~~~

Đây là **định dạng log minh họa**, không phải output mặc định do Spring Web Flow phát ra.

## 17. Những lỗi thiết kế thường gặp

**Gọi method ghi ở on-render.** Một lượt refresh có thể tạo side effect thêm lần nữa. Đặt thao tác ghi trong action-state với idempotency.

**Dùng bean singleton làm bộ nhớ của form.** Các flow execution khác nhau có thể ghi đè dữ liệu của nhau. Giữ draft ở scope của execution.

**Cho client chọn tên bean/method.** Ghép request parameter thành expression tạo rủi ro thực thi ngoài ý định. Expression phải được tin cậy và cố định.

**Coi quyết định ở decision-state là bất biến mãi mãi.** Điều kiện nghiệp vụ thay đổi theo thời gian; service phải kiểm tra lại tại commit.

**Dùng một method trả boolean cho tất cả outcome.** Không phân biệt được thành công, hết chỗ và kết quả ghi chưa xác định. Cần outcome/Event có ý nghĩa.

**Đăng ký bean ở MVC context nhưng quên context của Web Flow.** Mã compile thành công nhưng expression không tìm thấy bean lúc chạy. Test wiring thật.

**Chỉ xem xét chuỗi URL mà bỏ validation.** RequestParameters không phải dữ liệu typed/đáng tin. Bind và validate form trước khi gọi service.

**Nhầm message với event.** Message dùng hiển thị cho người dùng; Event dùng chọn transition.

**Bắt mọi exception rồi trả event retry.** Timeout có thể xảy ra sau khi ghi. Phải phân loại và bảo vệ transaction/idempotency.

**Lưu collection hoặc entity quá lớn trong flowScope.** Tăng kích thước snapshot và nguy cơ lỗi thời. Giữ dữ liệu nhỏ gọn.

## 18. Bài thực hành: gọi bean đúng lúc trong flow checkout

Thiết kế flow `checkout` gồm `cart → delivery → review → submit → completed`. Spring có các bean `checkoutDraftFactory`, `shippingCatalog`, `checkoutPolicy`, `checkoutAction` và `checkoutService`.

Yêu cầu:

1. Khi flow bắt đầu, gọi `checkoutDraftFactory.create()` và lưu kết quả vào `flowScope.checkout`.
2. Tại bước delivery, gọi `shippingCatalog.availableMethods(...)` để lấy danh sách vận chuyển, lưu vào viewScope.
3. Tại review, dùng một policy method trả boolean để kiểm tra điều kiện đi tới bước xác nhận; không tạo đơn khi chỉ render view.
4. Khi submit, gọi `checkoutAction.submit(requestContext)`; trả các event `placed`, `outOfStock` và `statusUnknown`.
5. Khi `outOfStock`, chuyển về cart để sửa số lượng. Khi `statusUnknown`, cho người dùng tra cứu theo request ID, không tạo đơn mới mù quáng.
6. Đăng ký bean bằng Spring và đảm bảo XML tham chiếu đúng bean name.
7. Viết integration test cố tình rename một method để phát hiện lỗi expression.
8. Viết test hai request `confirm` đồng thời để chứng minh database không tạo đơn trùng.

**Gợi ý khung XML:**

~~~xml
<on-start>
    <evaluate expression="checkoutDraftFactory.create()"
              result="flowScope.checkout"/>
</on-start>

<!-- Đặt trong view-state delivery -->
<on-render>
    <evaluate expression="shippingCatalog.availableMethods(flowScope.checkout)"
              result="viewScope.shippingMethods"/>
</on-render>

<action-state id="submit">
    <evaluate expression="checkoutAction.submit(requestContext)"/>
    <transition on="placed" to="completed"/>
    <transition on="outOfStock" to="cart"/>
    <transition on="statusUnknown" to="pending"/>
</action-state>
~~~

Đoạn trên là **các mảnh XML minh họa**, chưa phải flow hoàn chỉnh; cần đặt ở đúng vị trí trong flow definition và khai báo đầy đủ state, bean, converter, validation, security và đường phục hồi.

**Tiêu chí đánh giá:** chỉ những method đúng trách nhiệm được gọi tại đúng mốc; một flow có thể resume qua nhiều request mà không mất bản nháp; các event đều có transition; quyền và transaction nằm ở service; expression không lấy tên method từ dữ liệu do người dùng gửi.

## 19. Tổng kết và câu hỏi tự kiểm tra

Trong Spring Web Flow, expression giúp **tham chiếu Spring bean và gọi method** tại những mốc xác định của flow. Kết quả trả về có thể là **dữ liệu** lưu vào scope, **boolean** cho decision-state hoặc **Event** giúp action-state chọn transition. Bean do Spring quản lý; dữ liệu người dùng thuộc flow execution; HTTP request mang chuỗi chưa đáng tin cần binding/validation trước khi vào service.

Hãy dùng biểu thức **cố định và dễ đọc**, đặt method ở đúng lifecycle, giữ logic nghiệp vụ và transaction trong service, đồng thời kiểm thử khả năng tìm bean, kiểu tham số, outcome và phục hồi. Tránh xem expression như đường tắt để bỏ qua phân quyền, idempotency hoặc các bước form validation.

**Câu hỏi tự kiểm tra:**

1. Trong `bookingCatalog.findAvailableSlots()`, phần nào là tên Spring bean, phần nào là tên method?
2. Vì sao tham chiếu `flowScope.booking` khác với tham chiếu `bookingService`?
3. Lời gọi trong `on-render` có thể xảy ra lại khi nào, và tác vụ nào không nên đặt ở đó?
4. `result="viewScope.availableSlots"` có tác dụng gì? Khi nào nên dùng `flowScope` thay vì `viewScope`?
5. Vì sao `bookingPolicy.canReview(...)` phù hợp với decision-state hơn method tạo booking?
6. Khi action trả Event `statusUnknown` nhưng XML không khai báo transition đó, cần sửa phần nào?
7. Vì sao expression dùng dữ liệu người dùng làm **tham số** khác về bảo mật với việc ghép dữ liệu người dùng vào **tên method**?
8. Những test nào chứng minh bean resolution đúng, và những test nào mới chứng minh thao tác ghi không bị lặp?
