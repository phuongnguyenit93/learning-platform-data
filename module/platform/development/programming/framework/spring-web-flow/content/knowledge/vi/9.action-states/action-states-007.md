# Triển khai Action và trả về Event

> **Chương:** Action-state  
> **Module:** SPRING_WEB_FLOW  
> **Mục tiêu:** Biết cách viết một Action trong Spring Web Flow, gọi Action từ action-state, trả về Event để điều khiển transition, lựa chọn giữa POJO action, Action interface và MultiAction; phân loại kết quả nghiệp vụ, truyền dữ liệu qua scope/event, xử lý exception và kiểm thử hành vi.

## 1. Action làm nhiệm vụ gì trong một flow?

Một flow mô tả hành trình của người dùng bằng state và transition. Tuy nhiên, flow thường phải gọi nghiệp vụ của ứng dụng: tìm dữ liệu, kiểm tra điều kiện, giữ chỗ, lưu đơn hàng hoặc gửi yêu cầu xác minh. **Action** là đơn vị hành vi được flow gọi tại một thời điểm cụ thể.

Ví dụ hành trình đặt lịch:

~~~text
chooseSlot → contact → review → reserve → completed
                              ↘ slotUnavailable → chooseSlot
~~~

Khi người dùng xác nhận ở state review, flow cần gọi dịch vụ đặt lịch. Kết quả có thể là:

- Đặt lịch thành công.
- Khung giờ vừa chọn không còn trống.
- Yêu cầu cần xác minh thêm.
- Lỗi kỹ thuật khiến kết quả chưa thể xác định.

Action nhận ngữ cảnh đang thực thi, gọi service phù hợp, chuyển kết quả thành **Event**. Flow dùng Event đó để chọn transition tiếp theo.

~~~mermaid
flowchart LR
    A["action-state: reserve"] --> B["Action"]
    B --> C["BookingService"]
    C --> D{"Kết quả"}
    D -->|"Booked"| E["Event: booked"]
    D -->|"Unavailable"| F["Event: slotUnavailable"]
    E --> G["Transition → completed"]
    F --> H["Transition → chooseSlot"]
~~~

Action tập trung vào việc thực thi một hành vi. Flow vẫn chịu trách nhiệm điều hướng và quyết định state tiếp theo.

## 2. Phân biệt Action, Event và action-state

Ba khái niệm này liên quan nhưng có vai trò khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Action | Thực hiện hành vi hoặc gọi service | Reserve một khung giờ |
| Event | Biểu diễn kết quả logic của Action | booked, slotUnavailable |
| action-state | Gọi Action và chọn transition theo Event | reserve → completed |

**Action không phải Spring MVC controller.** Action không tự chọn view để hiển thị. Nó trả kết quả để flow quyết định bước tiếp theo.

### 2.1. Một Action không nhất thiết là một class implements Action

Spring Web Flow hỗ trợ nhiều cách triển khai:

- Gọi method trên một POJO/Spring bean bằng biểu thức EL.
- Cài đặt interface `org.springframework.webflow.execution.Action`.
- Kế thừa `MultiAction` để gom nhiều method Action có cùng quy ước.

POJO action thường là cách đơn giản nhất khi chỉ cần gọi service và trả một kết quả. Interface Action hữu ích khi cần làm việc trực tiếp với RequestContext và Event. MultiAction phù hợp khi nhiều hành vi có cấu trúc tương tự thuộc cùng một nhóm.

## 3. Khai báo action-state trong flow definition

Phần tử `action-state` dùng để gọi một hoặc nhiều action rồi chuyển sang state tiếp theo dựa trên outcome.

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="review" view="booking/review">
        <transition on="confirm" to="reserve"/>
    </view-state>

    <action-state id="reserve">
        <evaluate expression="bookingAction.reserve(flowScope.booking, flowRequestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="slotUnavailable" to="chooseSlot"/>
    </action-state>

    <view-state id="chooseSlot" view="booking/choose-slot"/>
    <end-state id="completed" view="booking/completed"/>
</flow>
~~~

Khi flow đi vào `reserve`:

1. Web Flow đánh giá biểu thức trong `evaluate`.
2. Method `bookingAction.reserve(...)` được gọi.
3. Giá trị trả về được ánh xạ thành một Event.
4. action-state so khớp Event với các transition đã khai báo.
5. Flow chuyển sang state đích tương ứng.

Transition `on` phải khớp Event ID. Nếu Action trả `booked` nhưng flow chỉ khai báo `on="success"`, kết quả không khớp transition dự kiến.

### 3.1. Action-state khác decision-state

`decision-state` phù hợp khi chỉ cần đánh giá điều kiện để chọn nhánh:

~~~xml
<decision-state id="hasContact">
    <if test="flowScope.booking.contact != null"
        then="review" else="contact"/>
</decision-state>
~~~

`action-state` phù hợp khi cần gọi hành vi, chẳng hạn truy vấn service hoặc ghi nhận thao tác:

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingAction.reserve(flowScope.booking)"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

Không nên gọi service có side effect trong một biểu thức decision chỉ để tận dụng kết quả boolean. Tách điều kiện định tuyến khỏi hành vi ghi dữ liệu giúp flow dễ hiểu và kiểm thử hơn.

## 4. Gọi POJO action bằng biểu thức EL

Đây là cách triển khai phổ biến. Một Spring bean cung cấp method có thể được gọi trực tiếp từ flow definition.

~~~java
public class BookingAction {

    private final BookingService bookingService;

    public BookingAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public String reserve(
            BookingDraft booking,
            RequestContext context) {

        try {
            BookingConfirmation confirmation =
                    bookingService.reserve(booking);

            context.getFlowScope().put(
                    "confirmation", confirmation);

            return "booked";
        } catch (SlotUnavailableException ex) {
            context.getMessageContext().addMessage(
                    new MessageBuilder()
                            .error()
                            .source("slotId")
                            .code("booking.slot.unavailable")
                            .defaultText("Khung giờ vừa chọn không còn trống.")
                            .build());

            return "slotUnavailable";
        }
    }
}
~~~

Flow gọi method:

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingAction.reserve(flowScope.booking, flowRequestContext)"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

Trong ví dụ:

- `bookingService` giữ nghiệp vụ đặt lịch và transaction.
- `BookingAction` điều phối service, cập nhật dữ liệu flow cần dùng và ánh xạ outcome.
- Chuỗi `booked` hoặc `slotUnavailable` trở thành Event ID.
- Flow chọn transition theo Event ID đó.

POJO action có thể nhận tham số từ biểu thức EL. Nếu cần truy cập RequestContext, truyền `flowRequestContext` như một đối số. Nếu không cần context, giữ method đơn giản với tham số nghiệp vụ.

### 4.1. Spring bean phải được đăng ký

Biểu thức `bookingAction.reserve(...)` chỉ hoạt động nếu bean `bookingAction` được đăng ký trong ApplicationContext mà Web Flow dùng.

Ví dụ cấu hình Java:

~~~java
@Configuration
public class BookingActionConfiguration {

    @Bean
    public BookingAction bookingAction(BookingService bookingService) {
        return new BookingAction(bookingService);
    }
}
~~~

Tên bean mặc định trong ví dụ là `bookingAction`. Nếu bean có tên khác, expression trong flow phải tham chiếu đúng tên đó.

## 5. Cách Web Flow ánh xạ giá trị trả về thành Event

Khi gọi method trên POJO từ action-state hoặc decision-state, giá trị trả về được ánh xạ thành Event ID theo quy tắc:

| Kiểu trả về của method | Event ID |
| --- | --- |
| `String` | Chính chuỗi được trả về |
| `Boolean` | `yes` nếu true, `no` nếu false |
| `Enum` | Tên hằng enum, qua `name()` |
| Kiểu khác | `success` |

Ví dụ method trả `Boolean.TRUE` sẽ tạo outcome `yes`. Method trả enum `ReservationOutcome.BOOKED` tạo Event ID `BOOKED`. Transition phải dùng đúng chữ hoa/thường tương ứng.

### 5.1. Trả String khi có nhiều outcome rõ ràng

~~~java
public String checkEligibility(Customer customer) {
    if (customer.isEligible()) {
        return "eligible";
    }
    return "notEligible";
}
~~~

~~~xml
<action-state id="checkEligibility">
    <evaluate expression="eligibilityAction.checkEligibility(flowScope.customer)"/>
    <transition on="eligible" to="showOffer"/>
    <transition on="notEligible" to="showExplanation"/>
</action-state>
~~~

Tên outcome là một phần hợp đồng giữa Action và flow definition. Hãy dùng tên có ý nghĩa nghiệp vụ và giữ nhất quán giữa Java/XML.

### 5.2. Trả Boolean khi chỉ có hai nhánh

~~~java
public boolean hasMoreQuestions(Interview interview) {
    return interview.hasUnansweredQuestions();
}
~~~

~~~xml
<action-state id="checkQuestions">
    <evaluate expression="interviewAction.hasMoreQuestions(flowScope.interview)"/>
    <transition on="yes" to="answerQuestions"/>
    <transition on="no" to="finish"/>
</action-state>
~~~

Boolean phù hợp với điều kiện nhị phân. Nếu có ba hoặc nhiều outcome, dùng String, enum hoặc Action trả Event rõ ràng.

### 5.3. Trả Enum để giới hạn tập outcome

~~~java
public enum ReservationOutcome {
    BOOKED,
    SLOT_UNAVAILABLE,
    REQUIRES_VERIFICATION
}
~~~

~~~java
public ReservationOutcome reserve(BookingDraft booking) {
    return bookingService.reserve(booking);
}
~~~

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingAction.reserve(flowScope.booking)"/>
    <transition on="BOOKED" to="completed"/>
    <transition on="SLOT_UNAVAILABLE" to="chooseSlot"/>
    <transition on="REQUIRES_VERIFICATION" to="verifyContact"/>
</action-state>
~~~

Event ID được tạo từ tên enum, do đó transition phải khớp chính xác. Nếu muốn tên event theo quy ước camelCase, có thể ánh xạ enum sang String ở Action thay vì dùng trực tiếp enum.

### 5.4. Trả object thường tạo Event success

Một method trả về domain object thường được ánh xạ thành Event `success`:

~~~java
public BookingConfirmation reserve(BookingDraft booking) {
    return bookingService.reserve(booking);
}
~~~

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingAction.reserve(flowScope.booking)"
              result="flowScope.confirmation"/>
    <transition on="success" to="completed"/>
</action-state>
~~~

Ở đây có hai việc độc lập:

- `result="flowScope.confirmation"` lưu giá trị trả về vào scope.
- Kiểu object trả về được ánh xạ thành Event ID `success`.

Thuộc tính `result` không đổi Event ID thành tên thuộc tính. Nếu muốn transition theo outcome cụ thể, method phải trả String/Boolean/Enum phù hợp hoặc trả Event trực tiếp qua Action interface.

## 6. Cài đặt interface Action

Khi cần thao tác trực tiếp với Web Flow API, có thể cài đặt:

`org.springframework.webflow.execution.Action`

Hợp đồng chính:

~~~java
Event execute(RequestContext context) throws Exception;
~~~

Ví dụ:

~~~java
public class ReserveBookingAction implements Action {

    private final BookingService bookingService;

    public ReserveBookingAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    @Override
    public Event execute(RequestContext context) {
        BookingDraft booking =
                (BookingDraft) context.getFlowScope().get("booking");

        try {
            BookingConfirmation confirmation =
                    bookingService.reserve(booking);

            context.getFlowScope().put(
                    "confirmation", confirmation);

            return new Event(this, "booked");
        } catch (SlotUnavailableException ex) {
            context.getMessageContext().addMessage(
                    new MessageBuilder()
                            .error()
                            .source("slotId")
                            .code("booking.slot.unavailable")
                            .defaultText("Khung giờ vừa chọn không còn trống.")
                            .build());

            return new Event(this, "slotUnavailable");
        }
    }
}
~~~

Flow gọi bean Action:

~~~xml
<action-state id="reserve">
    <evaluate expression="reserveBookingAction"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

Khác với POJO method return mapping, Action interface trả Event trực tiếp. Vì vậy code chủ động chọn Event ID và có thể gắn payload attributes nếu flow cần dữ liệu bổ sung.

### 6.1. Event gồm source và id

Một Event có:

- **Source:** đối tượng phát ra event, thường là Action.
- **ID:** tên logic mô tả outcome, ví dụ `booked`.
- **Attributes (tùy chọn):** payload bổ sung đi kèm event.

Event ID là khóa để flow so khớp transition:

~~~xml
<transition on="booked" to="completed"/>
~~~

Không đưa toàn bộ domain object hoặc dữ liệu nhạy cảm vào tên Event ID. Nếu cần truyền dữ liệu, lưu object cần thiết trong scope hoặc dùng event attributes có chủ đích.

### 6.2. Event payload và flow scope có mục đích khác nhau

Event attributes phù hợp với dữ liệu gắn trực tiếp vào một outcome, chẳng hạn mã tham chiếu hoặc thông tin kết quả cần flow cha nhận từ subflow. Flow scope phù hợp với dữ liệu cần tồn tại trong phần còn lại của flow execution.

Không dùng event payload như kho lưu trữ lâu dài. Event là kết quả của một lần thực thi Action; dữ liệu cần hiển thị ở state sau nên được đưa vào scope thích hợp hoặc tải lại từ service.

## 7. Dùng MultiAction khi có nhiều hành vi liên quan

`MultiAction` là lớp cơ sở cho phép gom nhiều method Action vào một class. Các method được gọi theo quy ước:

~~~java
public Event methodName(RequestContext context) throws Exception;
~~~

Ví dụ:

~~~java
public class BookingMultiAction extends MultiAction {

    private final BookingService bookingService;

    public BookingMultiAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public Event loadSummary(RequestContext context) {
        BookingDraft booking =
                (BookingDraft) context.getFlowScope().get("booking");

        BookingSummary summary =
                bookingService.loadSummary(booking.getId());

        context.getFlowScope().put("summary", summary);
        return new Event(this, "success");
    }

    public Event reserve(RequestContext context) {
        BookingDraft booking =
                (BookingDraft) context.getFlowScope().get("booking");

        try {
            BookingConfirmation confirmation =
                    bookingService.reserve(booking);
            context.getFlowScope().put("confirmation", confirmation);
            return new Event(this, "booked");
        } catch (SlotUnavailableException ex) {
            context.getMessageContext().addMessage(
                    new MessageBuilder()
                            .error()
                            .code("booking.slot.unavailable")
                            .defaultText("Khung giờ vừa chọn không còn trống.")
                            .build());
            return new Event(this, "slotUnavailable");
        }
    }
}
~~~

Gọi method cụ thể:

~~~xml
<action-state id="loadSummary">
    <evaluate expression="bookingMultiAction.loadSummary"/>
    <transition on="success" to="review"/>
</action-state>

<action-state id="reserve">
    <evaluate expression="bookingMultiAction.reserve"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

MultiAction giúp gom các command cùng ngữ cảnh flow. Không nên gom mọi nghiệp vụ của toàn ứng dụng vào một MultiAction khổng lồ; chia theo flow hoặc nhóm hành vi để class vẫn dễ hiểu.

## 8. Tên action và event khi có chuỗi nhiều action

Một action-state có thể khai báo nhiều phần tử `evaluate`. Chúng được chạy theo thứ tự. Sau mỗi action, Web Flow kiểm tra outcome có khớp transition đã khai báo hay không. Khi một action tạo outcome phù hợp, flow có thể chuyển state và các action còn lại trong chuỗi không được thực hiện.

Ví dụ:

~~~xml
<action-state id="prepareReview">
    <evaluate expression="bookingService.validateDraft(flowScope.booking)">
        <attribute name="name" value="validate"/>
    </evaluate>
    <evaluate expression="bookingService.loadPricing(flowScope.booking)"
              result="flowScope.pricing">
        <attribute name="name" value="pricing"/>
    </evaluate>
    <transition on="pricing.success" to="review"/>
</action-state>
~~~

Thuộc tính `name` giúp định danh outcome của từng action trong chuỗi. Trong ví dụ, event thành công của action thứ hai được định danh `pricing.success`.

Giả sử action `validateDraft` trả về một object nên outcome là `validate.success`. Vì action-state chưa khai báo transition cho outcome này, chuỗi tiếp tục tới `loadPricing`. Nếu action thứ hai trả về object, outcome của nó là `pricing.success` và transition đã khai báo sẽ được chọn.

### 8.1. Dùng chain có chủ đích

Một chain phù hợp khi các bước nhỏ được thực thi tuần tự và outcome có thể dừng chuỗi. Ví dụ:

1. Kiểm tra draft.
2. Tải báo giá.
3. Chuẩn bị dữ liệu review.

Nếu cần điều kiện rẽ nhánh phức tạp giữa các bước, nhiều action-state riêng thường dễ đọc hơn một chuỗi dài.

### 8.2. Không giả định mọi action sau đều chạy

Nếu action đầu trả Event đã khớp transition, flow không cần chạy các action tiếp theo. Đừng đặt side effect bắt buộc ở action sau một action có thể kết thúc chuỗi.

## 9. Đặt Action ở đâu trong lifecycle?

Action không chỉ xuất hiện trong action-state. Web Flow có các điểm thực thi hành vi khác:

| Điểm thực thi | Khi nào chạy? | Ví dụ |
| --- | --- | --- |
| on-start | Khi flow bắt đầu | Tạo booking draft |
| on-entry | Khi đi vào state | Chuẩn bị model cho state |
| on-render | Trước khi render view | Tải danh sách lựa chọn |
| transition action | Khi xử lý một event chuyển state | Ghi nhận câu trả lời |
| on-exit | Khi rời state | Giải phóng tài nguyên đã giữ |
| on-end | Khi flow kết thúc | Dọn tài nguyên theo chính sách |

Ví dụ action trong transition:

~~~xml
<view-state id="review" view="booking/review">
    <transition on="confirm" to="reserve">
        <evaluate expression="auditAction.recordConfirmation(flowScope.booking)"/>
    </transition>
</view-state>
~~~

Action ở transition chạy khi event tương ứng được xử lý. Nó khác action-state độc lập vì mục đích là thực hiện hành vi gắn với transition đó.

### 9.1. Chọn điểm thực thi theo ý nghĩa

- Dữ liệu khởi tạo cho cả flow: on-start.
- Chuẩn bị dữ liệu khi state được mở: on-entry.
- Dữ liệu cần tải lại trước mỗi lần render: on-render.
- Ghi nhận hành động người dùng: transition action.
- Dọn tài nguyên khi rời state: on-exit.
- Dọn tài nguyên khi flow kết thúc: on-end.
- Thực hiện hành vi có nhiều outcome và cần định tuyến: action-state.

Không chuyển tất cả logic vào action-state. Chọn điểm lifecycle phù hợp làm flow definition dễ đọc và tránh gọi service lặp không cần thiết.

## 10. Trả dữ liệu qua scope và result

Action thường cần chuyển dữ liệu cho state kế tiếp. Có một số cách:

### 10.1. Gán kết quả evaluate vào scope

~~~xml
<action-state id="loadBooking">
    <evaluate expression="bookingService.find(flowScope.bookingId)"
              result="flowScope.booking"/>
    <transition on="success" to="review"/>
</action-state>
~~~

Giá trị trả về được lưu trong flow scope; do kết quả là object nên Event ID theo mapping thông thường là `success`.

### 10.2. Action ghi trực tiếp vào scope

~~~java
context.getFlowScope().put("confirmation", confirmation);
~~~

Cách này phù hợp khi Action interface cần cập nhật nhiều giá trị hoặc cần kiểm soát chính xác tên thuộc tính.

### 10.3. Chọn scope đúng vòng đời

| Scope | Vòng đời điển hình | Dữ liệu phù hợp |
| --- | --- | --- |
| requestScope | Request đang xử lý | Dữ liệu tạm trong một lần gọi |
| flashScope | Đến khi view render hoàn tất | Message hoặc dữ liệu qua redirect/render |
| viewScope | Trong một view-state | Model riêng của màn hình |
| flowScope | Trong flow execution | Booking draft, kết quả cần qua nhiều state |
| conversationScope | Chia sẻ trong conversation theo thiết kế | Dữ liệu dùng chung giữa các flow liên quan |

Không lưu object chỉ phục vụ một lần render vào flowScope nếu viewScope đã đủ. Không lưu dữ liệu lớn hoặc nhạy cảm không cần thiết vào execution snapshot.

## 11. Phân loại outcome nghiệp vụ và exception kỹ thuật

Một Action nên chuyển **kết quả nghiệp vụ dự kiến** thành Event có ý nghĩa:

| Kết quả service | Event | Hành vi flow |
| --- | --- | --- |
| Đặt lịch thành công | booked | completed |
| Slot không còn trống | slotUnavailable | chooseSlot |
| Cần xác minh liên hệ | requiresVerification | verifyContact |
| Draft không hợp lệ | invalidDraft | review hoặc sửa form |

Ví dụ slot hết chỗ là tình huống bình thường có thể xảy ra trong hệ thống đặt lịch. Service có thể ném exception nghiệp vụ chuyên biệt; Action bắt exception đó, thêm message và trả Event `slotUnavailable`.

Ngược lại, lỗi kết nối database, lỗi cấu hình hoặc bug lập trình không nên bị chuyển thành `slotUnavailable`. Nếu Action không thể xác định outcome nghiệp vụ, để exception đi tới cơ chế xử lý exception của Web Flow.

### 11.1. Bắt exception cụ thể

~~~java
try {
    BookingConfirmation confirmation = bookingService.reserve(booking);
    context.getFlowScope().put("confirmation", confirmation);
    return new Event(this, "booked");
} catch (SlotUnavailableException ex) {
    context.getMessageContext().addMessage(
            new MessageBuilder()
                    .error()
                    .code("booking.slot.unavailable")
                    .defaultText("Khung giờ vừa chọn không còn trống.")
                    .build());
    return new Event(this, "slotUnavailable");
}
~~~

Chỉ bắt exception mà Action biết cách chuyển thành outcome đúng. Không bắt chung `Exception` rồi trả Event thành công hoặc lỗi nghiệp vụ bất kỳ.

### 11.2. Exception handler là lựa chọn nâng cao

Web Flow cho phép cấu hình `exception-handler` trên state với bean triển khai `FlowExecutionExceptionHandler`. Đây là cơ chế nâng cao. Nếu handler chuyển state không đúng, execution có thể rơi vào trạng thái không hợp lệ.

Với lỗi nghiệp vụ đã biết, cách dễ kiểm soát thường là bắt trong Action, ghi message và trả Event để flow xử lý qua transition thông thường. Với lỗi không mong đợi, dùng exception handling ở tầng phù hợp và giữ nguyên cause để điều tra.

## 12. Action phải an toàn khi được gọi nhiều lần

Action được gọi trong một request đang thực thi flow. Một action có thể được gọi lại do:

- Người dùng submit lại.
- Browser Back/Refresh.
- Request retry sau timeout.
- Một flow mới được khởi tạo từ cùng dữ liệu.
- Hệ thống phục hồi một execution hoặc xử lý lại yêu cầu.

Với hành vi chỉ đọc, gọi lại thường không gây side effect lớn. Với hành vi ghi, cần thiết kế idempotency.

### 12.1. Dùng request ID cho thao tác ghi

~~~java
public Event reserve(RequestContext context) {
    BookingDraft booking =
            (BookingDraft) context.getFlowScope().get("booking");

    ReservationResult result =
            bookingService.reserveOnce(
                    booking.getRequestId(), booking);

    if (result.isBooked()) {
        context.getFlowScope().put(
                "confirmation", result.getConfirmation());
        return new Event(this, "booked");
    }

    return new Event(this, "slotUnavailable");
}
~~~

Đây là ví dụ minh họa. Service/database cần bảo vệ request ID bằng unique constraint hoặc cơ chế idempotency nguyên tử; chỉ kiểm tra trước rồi insert không đủ khi hai request đồng thời.

### 12.2. Không lưu dữ liệu request vào field của Action singleton

Spring bean thường được dùng chung giữa nhiều flow execution và request. Không viết:

~~~java
public class BookingAction {
    private BookingDraft currentBooking; // Không an toàn
}
~~~

Hai người dùng có thể ghi đè dữ liệu của nhau. Hãy dùng biến local, RequestContext và service thread-safe. Action bean nên stateless; dữ liệu riêng của người dùng nằm trong scope của execution hoặc storage nghiệp vụ.

## 13. Quy tắc đặt tên Event và transition

Event ID là hợp đồng giữa code và flow definition. Nên đặt tên theo outcome:

~~~text
booked
slotUnavailable
requiresVerification
invalidDraft
success
error
~~~

`success` phù hợp cho một hành động thành công tổng quát, nhưng với nghiệp vụ quan trọng, tên cụ thể như `booked` giúp flow dễ đọc hơn.

### 13.1. Dùng cùng quy ước chữ hoa/thường

Nếu POJO trả enum `SLOT_UNAVAILABLE` thì event ID có thể là `SLOT_UNAVAILABLE`. Nếu XML viết `on="slotUnavailable"` thì sẽ không khớp.

Nên chọn một quy ước:

- camelCase cho String Event ID.
- Enum uppercase nếu dùng trực tiếp enum mapping.
- Chuyển enum sang String trong Action nếu flow cần tên camelCase.

### 13.2. Khai báo transition cho mọi outcome có thể xảy ra

Nếu Action có thể trả `booked`, `slotUnavailable` và `requiresVerification`, action-state cần định nghĩa các transition tương ứng hoặc có chính sách xử lý rõ ràng cho outcome còn lại.

Thiếu transition phù hợp có thể dẫn đến lỗi không tìm thấy transition. Đừng để outcome phát sinh trong runtime mà chưa được mô hình hóa trong flow.

## 14. Kiểm thử Action độc lập

Action có thể được kiểm thử ở mức unit test bằng cách mock RequestContext/service:

~~~java
import org.springframework.webflow.core.collection.LocalAttributeMap;
import org.springframework.webflow.core.collection.MutableAttributeMap;

@Test
void returnsBookedWhenReservationSucceeds() {
    BookingService service = mock(BookingService.class);
    RequestContext context = mock(RequestContext.class);
    MutableAttributeMap<Object> flowScope = new LocalAttributeMap<>();
    BookingDraft draft = mock(BookingDraft.class);
    BookingConfirmation confirmation = mock(BookingConfirmation.class);

    when(context.getFlowScope()).thenReturn(flowScope);
    flowScope.put("booking", draft);
    when(service.reserve(draft)).thenReturn(confirmation);

    ReserveBookingAction action = new ReserveBookingAction(service);
    Event event = action.execute(context);

    assertEquals("booked", event.getId());
    assertSame(confirmation, flowScope.get("confirmation"));
}
~~~

Đây là ví dụ theo API Web Flow 2.x; tên package/import và cách tạo fixture cần khớp version/test stack thực tế. Có thể dùng MockRequestContext do Web Flow cung cấp thay vì tự mock toàn bộ RequestContext.

Các trường hợp cần kiểm thử:

- Service thành công trả Event `booked`.
- Slot không còn trống trả Event `slotUnavailable`.
- MessageContext nhận đúng message code và field source.
- Exception kỹ thuật không bị biến thành outcome nghiệp vụ.
- Scope chỉ nhận dữ liệu cần thiết.
- Không giữ dữ liệu request trong field của Action.

## 15. Kiểm thử flow integration

Unit test chứng minh Action trả Event đúng. Integration test chứng minh flow definition nhận Event và chuyển state đúng.

~~~text
Start booking flow
Move to review
Submit event confirm
Configure BookingService to return booked

Assert:
  reserve action is invoked once
  event id is booked
  flow reaches completed
  confirmation is available in flowScope
~~~

Kịch bản slot hết:

~~~text
Start booking flow
Move to review
Submit event confirm
Configure BookingService to throw SlotUnavailableException

Assert:
  action adds booking.slot.unavailable message
  event id is slotUnavailable
  flow returns to chooseSlot
  no success confirmation is stored
~~~

### 15.1. Test outcome không có transition

Cho Action trả một Event ID chưa được khai báo. Xác minh flow báo lỗi theo exception handling đã cấu hình. Test này giúp phát hiện khi code thêm outcome mới nhưng XML chưa cập nhật.

### 15.2. Test nhiều Action trong cùng action-state

Nếu action-state dùng chain:

- Xác minh thứ tự thực thi.
- Xác minh action trả event khớp transition làm dừng chuỗi.
- Xác minh action sau không chạy khi chuỗi đã chuyển state.
- Xác minh qualifier `name` tạo event ID đúng như flow đang chờ.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Bean không tìm thấy | Bean chưa đăng ký hoặc sai tên | ApplicationContext và expression |
| Method không được gọi | Expression EL sai hoặc method không truy cập được | Kiểm tra tham số, tên method, scope |
| Flow không đi đúng nhánh | Event ID không khớp transition | Log Event ID và XML `on` |
| Luôn đi vào success | Method trả object nên mapping thành success | Kiểm tra kiểu trả về và result |
| Enum không khớp transition | Khác chữ hoa/thường | Dùng enum name chính xác hoặc ánh xạ String |
| Dữ liệu không có ở state sau | Gán sai scope/result | Kiểm tra result expression và scope |
| Message không hiển thị | MessageContext/source/locale/view sai | Kiểm tra message code và render |
| Booking bị tạo trùng | Action/service không idempotent | Request ID và unique constraint |
| Dữ liệu người dùng bị lẫn | Action singleton giữ state mutable | Bỏ field dữ liệu request, dùng scope |
| Exception làm flow dừng | Lỗi kỹ thuật chưa được xử lý | Đọc cause và exception handler |

### 16.1. Kiểm tra kiểu trả về trước khi sửa XML

Nếu method trả về một object, Event ID mặc định thường là `success`. Việc thêm transition `on="booked"` không làm method tự phát event booked.

Hãy chọn một trong các cách:

- Đổi method trả String `booked`.
- Trả enum có tên tương ứng.
- Cài đặt Action và trả `new Event(this, "booked")`.

### 16.2. Không dùng null như outcome ngầm

Không dựa vào `null` để biểu thị thất bại hoặc kết thúc. Hãy trả Event ID rõ ràng hoặc để exception được xử lý theo chính sách. Mọi outcome cần có ý nghĩa và transition tương ứng.

## 17. Bài thực hành: xây Action đặt lịch

Tạo một flow:

~~~text
review → reserve → completed
             ↘ slotUnavailable → chooseSlot
             ↘ requiresVerification → verifyContact
~~~

**Yêu cầu:**

1. Tạo service `BookingService` với thao tác đặt lịch.
2. Tạo POJO action `BookingAction` nhận service qua constructor.
3. Viết method `reserve` trả String outcome.
4. Xử lý `SlotUnavailableException` bằng message code và Event ID `slotUnavailable`.
5. Viết một phiên bản khác triển khai interface `Action` và trả Event trực tiếp.
6. Lưu `BookingConfirmation` vào flowScope sau khi thành công.
7. Khai báo action-state và transition cho mọi outcome.
8. Thử trả object, Boolean và Enum để quan sát cách ánh xạ Event ID.
9. Viết test cho booked và slotUnavailable.
10. Viết integration test chứng minh state đích đúng.
11. Gửi cùng request ID hai lần và xác minh chỉ có một booking.
12. Xác minh Action bean không giữ dữ liệu request trong field.

**Tiêu chí đạt:** Action gọi service đúng, trả Event có tên ổn định, flow transition đúng theo outcome, message được hiển thị ở state phù hợp, exception kỹ thuật được giữ nguyên ngữ nghĩa và thao tác ghi không tạo dữ liệu trùng.

## 18. Tóm tắt và câu hỏi tự kiểm tra

Action là đơn vị hành vi được flow gọi; action-state thực thi Action và chọn transition dựa trên Event. Với POJO action, Web Flow ánh xạ giá trị trả về thành Event ID: String dùng chính chuỗi, Boolean thành yes/no, Enum thành tên enum và object thông thường thành success. Với interface Action, method `execute(RequestContext)` trả Event trực tiếp; MultiAction gom nhiều method có chữ ký `Event method(RequestContext)`.

Hãy để service sở hữu nghiệp vụ và transaction, còn Action điều phối, cập nhật scope cần thiết, chuyển outcome thành Event và tạo message phù hợp. Bắt exception nghiệp vụ cụ thể khi có thể chuyển thành nhánh flow dự kiến; để lỗi kỹ thuật đi qua exception handling. Mỗi outcome phải khớp transition đã khai báo, Action bean phải stateless và thao tác ghi cần idempotency.

**Câu hỏi tự kiểm tra:**

1. Action khác controller Spring MVC ở vai trò nào?
2. action-state thực hiện gì sau khi Action trả Event?
3. POJO method trả Boolean true tạo Event ID nào?
4. Vì sao method trả một domain object thường dẫn đến Event `success`?
5. Khi nào nên cài đặt interface Action thay vì gọi POJO method?
6. Event gồm những thông tin nào và Event ID được dùng ra sao?
7. MultiAction yêu cầu chữ ký method như thế nào?
8. Vì sao một action-state có nhiều evaluate có thể dừng trước khi chạy hết chuỗi?
9. Vì sao không nên bắt mọi Exception rồi trả Event `slotUnavailable`?
10. Flow scope, view scope và event attributes phù hợp với những loại dữ liệu nào?
11. Vì sao Action bean singleton không nên lưu BookingDraft vào field?
12. Cần kiểm thử những gì để chứng minh Event và transition hoạt động đúng?

## Tài liệu tham khảo

- [Spring Web Flow 2.5.x Reference Guide — Executing Actions](https://docs.spring.io/spring-webflow/docs/2.5.x/reference/html/actions.html)
- [Spring Web Flow 2.5.x API — Action](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/execution/Action.html)
- [Spring Web Flow 2.5.1 API — Event](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/api/org/springframework/webflow/execution/Event.html)
- [Spring Web Flow 2.5.1 API — MultiAction](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/api/org/springframework/webflow/action/MultiAction.html)
