# Ánh xạ giá trị trả về thành sự kiện kết quả trong Spring Web Flow

Trong **Spring Web Flow** (`SPRING_WEB_FLOW`), một `action-state` gọi service hoặc action rồi quyết định đi tiếp dựa trên **kết quả thực thi**. Method Java có thể trả về `String`, `Boolean`, `Enum` hoặc một đối tượng nghiệp vụ. Nhưng transition của flow được kích hoạt bởi **event**, vì vậy Spring Web Flow cần ánh xạ giá trị trả về thành một event ID.

Ví dụ, service kiểm tra chỗ trống có thể trả `true` hoặc `false`. Flow có thể hiểu hai kết quả đó thành event `yes` và `no` để chọn bước tiếp theo. Một service tạo đơn hàng trả về `OrderConfirmation` thì thường được ánh xạ thành event `success`. Nếu muốn phân nhánh theo một kết quả nghiệp vụ cụ thể, method có thể trả một chuỗi như `retry` hoặc một enum như `BookingOutcome.REJECTED`.

Bài thuộc chương **Action-state** giải thích quy tắc ánh xạ giá trị trả về thành event, cách khai báo transition tương ứng, cách chủ động tạo event bằng `Action`/`MultiAction`, và cách kiểm thử các nhánh. Nội dung dựa trên cơ chế của Spring Web Flow 2.x/3.x; hãy đối chiếu tài liệu của phiên bản đang triển khai khi dùng API hoặc cấu hình tùy biến.

## 1. Vì sao giá trị trả về cần được ánh xạ thành event?

Một action thường thực hiện công việc rồi trả kết quả. Trong khi đó, flow cần biết **nên chuyển sang state nào**. Hai việc này liên quan nhưng không giống nhau:

- **Giá trị trả về** là kết quả Java của method hoặc action.
- **Event** là tín hiệu có ID để flow chọn transition.
- **State đích** là state mà transition dẫn đến.

Ví dụ kiểm tra tồn kho:

```java
public boolean hasStock(String productCode) {
    return inventoryService.available(productCode);
}
```

Flow không viết transition theo kiểu `on="true"` hay `on="false"`. Spring Web Flow ánh xạ kết quả Boolean thành event `yes` hoặc `no`:

```xml
<action-state id="checkInventory">
    <evaluate expression="inventoryService.hasStock(flowScope.productCode)" />
    <transition on="yes" to="prepareOrder" />
    <transition on="no" to="outOfStock" />
</action-state>
```

Kết quả `true` tạo event `yes` và chuyển đến `prepareOrder`. Kết quả `false` tạo event `no` và chuyển đến `outOfStock`.

`action-state` là nơi gọi action và xử lý outcome. Nó không tự suy ra state đích từ tên method hay tên class; flow phải khai báo transition phù hợp với event ID được tạo ra.

## 2. Quy tắc ánh xạ các kiểu trả về phổ biến

Khi gọi method trên một POJO từ `action-state` hoặc `decision-state`, Spring Web Flow ánh xạ một số kiểu trả về thông dụng như sau:

| Kiểu trả về của method | Event ID được ánh xạ | Ví dụ |
| --- | --- | --- |
| `java.lang.String` | Chính giá trị chuỗi | `"retry"` → `retry` |
| `java.lang.Boolean` | `yes` nếu `true`, `no` nếu `false` | `true` → `yes` |
| `java.lang.Enum` | Tên enum constant | `BookingOutcome.REJECTED` → `REJECTED` |
| Bất kỳ kiểu khác | `success` | `OrderConfirmation`, `Integer`, `BigDecimal` → `success` |

Quy tắc này được Spring Web Flow Reference Guide mô tả cho method return value dùng trong action-state và decision-state. Có thể dựa vào nó để đặt tên transition một cách nhất quán.

Một vài hệ quả quan trọng:

- Chuỗi `"success"` tạo event `success`; chuỗi `"retry"` tạo event `retry`.
- Boolean không tạo event có ID `true` hoặc `false`; nó tạo `yes`/`no`.
- Enum dùng **tên constant**, giữ đúng cách viết đã khai báo, ví dụ `PAYMENT_DECLINED`.
- Trả về một object nghiệp vụ như `OrderConfirmation` vẫn được ánh xạ thành `success`; kiểu class của object không trở thành event ID.

**Đừng đặt transition theo kiểu Java của giá trị trả về.** Transition lắng nghe event ID sau ánh xạ.

## 3. Trả về String để chọn event theo nghiệp vụ

`String` hữu ích khi action có nhiều kết quả nghiệp vụ cần được thể hiện trực tiếp:

```java
package com.example.booking;

public class BookingCheckService {

    public String check(BookingRequest request) {
        if (!request.hasValidGuest()) {
            return "invalidGuest";
        }

        if (!availabilityService.hasRoom(request)) {
            return "noRoom";
        }

        return "available";
    }
}
```

Flow ánh xạ từng chuỗi thành event ID tương ứng:

```xml
<action-state id="checkBooking">
    <evaluate expression="bookingCheckService.check(flowScope.request)" />

    <transition on="available" to="reviewBooking" />
    <transition on="invalidGuest" to="editGuestDetails" />
    <transition on="noRoom" to="chooseAnotherRoom" />
</action-state>
```

Tên chuỗi phải khớp với thuộc tính `on` của transition. Nếu method trả `"noRoom"` nhưng flow chỉ khai báo `on="no-room"`, hai giá trị không khớp. Hãy chọn một quy ước đặt tên event và dùng nhất quán.

Một method trả chuỗi không cần giới hạn ở `success` hoặc `error`. Có thể dùng các ID phản ánh nghiệp vụ như `duplicateEmail`, `quotaExceeded`, `expired` hoặc `requiresApproval`. Tuy nhiên, không nên tạo quá nhiều event nhỏ đến mức flow khó đọc; những điều kiện thuần Boolean đơn giản có thể dùng decision-state.

## 4. Trả về Boolean để tạo event yes/no

Khi action chỉ cần trả lời một câu hỏi đúng/sai, Boolean là cách ngắn gọn:

```java
public boolean needsMoreInformation(RegistrationForm form) {
    return form.getMissingFields().size() > 0;
}
```

```xml
<action-state id="checkRegistration">
    <evaluate expression="registrationService.needsMoreInformation(flowScope.form)" />
    <transition on="yes" to="completeMissingFields" />
    <transition on="no" to="reviewRegistration" />
</action-state>
```

Bảng ánh xạ:

| Method trả về | Event | State đích trong ví dụ |
| --- | --- | --- |
| `Boolean.TRUE` | `yes` | `completeMissingFields` |
| `Boolean.FALSE` | `no` | `reviewRegistration` |

Không viết `on="true"` hay `on="false"` nếu đang dùng quy tắc ánh xạ Boolean mặc định. Nếu muốn tên event mang ý nghĩa riêng, có thể trả String hoặc tự tạo Event.

### Khi nào dùng decision-state?

Nếu method chỉ kiểm tra một biểu thức Boolean để chọn một trong hai state và không cần chuỗi action riêng, `decision-state` có thể rõ ràng hơn:

```xml
<decision-state id="checkRegistration">
    <if test="registrationService.needsMoreInformation(flowScope.form)"
        then="completeMissingFields"
        else="reviewRegistration" />
</decision-state>
```

`decision-state` dùng cú pháp `if/then/else` nên không cần khai báo event `yes`/`no` bằng transition. Chọn action-state khi cần gọi một hoặc nhiều action và xử lý outcome; chọn decision-state cho quyết định điều hướng Boolean gọn.

## 5. Trả về Enum để tránh chuỗi event rải rác

Enum giúp tập hợp các outcome trong một kiểu Java có tên rõ ràng:

```java
package com.example.payment;

public enum PaymentOutcome {
    APPROVED,
    DECLINED,
    REVIEW_REQUIRED
}
```

Service trả về enum:

```java
public PaymentOutcome authorize(PaymentRequest request) {
    if (riskService.requiresManualReview(request)) {
        return PaymentOutcome.REVIEW_REQUIRED;
    }

    if (paymentGateway.authorize(request)) {
        return PaymentOutcome.APPROVED;
    }

    return PaymentOutcome.DECLINED;
}
```

Spring Web Flow ánh xạ enum thành **tên constant**:

```xml
<action-state id="authorizePayment">
    <evaluate expression="paymentService.authorize(flowScope.paymentRequest)" />

    <transition on="APPROVED" to="paymentApproved" />
    <transition on="DECLINED" to="paymentDeclined" />
    <transition on="REVIEW_REQUIRED" to="manualReview" />
</action-state>
```

Lợi ích của enum:

- Compiler giúp phát hiện việc tham chiếu sai constant trong Java.
- Các outcome được tập trung thành một tập giá trị rõ ràng.
- Flow có thể khai báo transition theo tên event tương ứng.

Tuy nhiên, XML vẫn chứa event ID dạng chuỗi. Khi đổi tên enum constant, cần cập nhật các transition liên quan và kiểm thử lại flow. Không đổi tên enum chỉ để làm cho XML đẹp hơn mà không xem xét hợp đồng event.

## 6. Trả về object nghiệp vụ: event success và dữ liệu kết quả là hai việc khác nhau

Một service tạo đặt phòng có thể trả về đối tượng xác nhận:

```java
public BookingConfirmation create(BookingRequest request) {
    return bookingService.createBooking(request);
}
```

Vì `BookingConfirmation` là kiểu khác String, Boolean và Enum, outcome event được ánh xạ mặc định thành `success`. Nếu muốn dùng object ở state tiếp theo, cần **lưu object vào scope**:

```xml
<action-state id="createBooking">
    <evaluate expression="bookingService.create(flowScope.request)"
              result="flowScope.confirmation" />

    <transition on="success" to="bookingConfirmed" />
</action-state>
```

Ở đây có hai kết quả độc lập:

1. `result="flowScope.confirmation"` lưu object do expression trả về vào flow scope.
2. Kiểu object `BookingConfirmation` được ánh xạ thành event `success` để chọn transition.

`result` không phải event ID và `flowScope.confirmation` không phải tên transition. Nếu bỏ `result`, event `success` vẫn có thể được tạo, nhưng object trả về không được lưu tại đích scope đã chỉ định.

Với dữ liệu lớn hoặc chỉ dùng trong một request, hãy cân nhắc scope ngắn hơn. Đối tượng trong `flowScope` có thể được giữ qua nhiều request và có yêu cầu serialization tùy execution repository.

## 7. Khai báo nhiều transition theo outcome

Một action-state thường có một transition cho mỗi outcome có thể xảy ra. Ví dụ đăng ký tài khoản:

```xml
<action-state id="registerAccount">
    <evaluate expression="registrationService.register(flowScope.form)" />

    <transition on="success" to="registrationCompleted" />
    <transition on="duplicateEmail" to="editEmail" />
    <transition on="policyRejected" to="registrationRejected" />
</action-state>
```

Service có thể trả chuỗi:

```java
public String register(RegistrationForm form) {
    if (accountRepository.existsByEmail(form.getEmail())) {
        return "duplicateEmail";
    }

    if (!policyService.isAllowed(form)) {
        return "policyRejected";
    }

    accountService.create(form);
    return "success";
}
```

Flow dùng event ID để điều hướng. Một outcome không được khai báo transition tương ứng có thể khiến flow không tìm được đường đi phù hợp; vì vậy cần liệt kê đầy đủ các kết quả hợp lệ mà action có thể trả.

Đối với lỗi bất ngờ như database unavailable, không nên trả một event nghiệp vụ tùy tiện. Hãy phân biệt lỗi có thể xử lý trong quy trình với lỗi kỹ thuật cần được xử lý qua exception policy.

## 8. Tạo Event trực tiếp bằng Action interface

Khi POJO return mapping không đủ diễn đạt, có thể implement `org.springframework.webflow.execution.Action`. Phương thức `execute(RequestContext)` trả về một đối tượng `Event`:

```java
package com.example.booking;

import org.springframework.webflow.execution.Action;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public class CheckBookingAction implements Action {

    @Override
    public Event execute(RequestContext context) {
        BookingRequest request =
                (BookingRequest) context.getFlowScope().get("request");

        if (request == null) {
            return new Event(this, "invalidRequest");
        }

        if (!availabilityService.hasRoom(request)) {
            return new Event(this, "noRoom");
        }

        return new Event(this, "available");
    }
}
```

Khai báo bean và gọi action:

```xml
<bean id="checkBookingAction"
      class="com.example.booking.CheckBookingAction">
    <property name="availabilityService" ref="availabilityService" />
</bean>

<action-state id="checkBooking">
    <evaluate expression="checkBookingAction" />
    <transition on="available" to="reviewBooking" />
    <transition on="noRoom" to="chooseAnotherRoom" />
    <transition on="invalidRequest" to="restartBooking" />
</action-state>
```

Trong thực tế, ví dụ Java cần khai báo dependency injection tương ứng, chẳng hạn field/setter hoặc constructor. Điểm khác biệt là action **chủ động trả Event** với ID mong muốn, thay vì để Web Flow suy ra event từ kiểu trả về của một POJO method.

Action interface phù hợp khi logic cần đọc/ghi `RequestContext`, truy cập scope, thêm message hoặc tạo event có payload.

## 9. Dùng AbstractAction hoặc MultiAction để tạo outcome rõ ràng

Spring Web Flow cung cấp các lớp tiện ích như `AbstractAction` và `MultiAction`. Chúng có các factory method để tạo event thường gặp:

- `success()` và `error()`.
- `yes()` và `no()`.
- `result("eventId")`.
- Các overload `result(...)` có thể gắn attributes cho event.

Ví dụ `MultiAction`:

```java
package com.example.booking;

import org.springframework.webflow.action.MultiAction;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public class BookingAction extends MultiAction {

    public Event confirm(RequestContext context) {
        BookingRequest request =
                (BookingRequest) context.getFlowScope().get("request");

        try {
            BookingConfirmation confirmation =
                    bookingService.createBooking(request);

            context.getFlowScope().put("confirmation", confirmation);
            return success();
        } catch (RoomNotAvailableException ex) {
            context.getMessageContext().addMessage(
                    new org.springframework.binding.message.MessageBuilder()
                            .error()
                            .defaultText("Không còn phòng phù hợp.")
                            .build());
            return error();
        }
    }
}
```

Gọi method của `MultiAction` trong flow:

```xml
<action-state id="confirmBooking">
    <evaluate expression="bookingAction.confirm" />
    <transition on="success" to="bookingConfirmed" />
    <transition on="error" to="reviewBooking" />
</action-state>
```

`MultiAction` dùng chữ ký action method dạng `Event methodName(RequestContext)`. Nó phù hợp khi một bean chứa một nhóm action có liên quan và cần dùng các factory method của Web Flow.

Đoạn ví dụ bắt `RoomNotAvailableException` như lỗi nghiệp vụ có thể xử lý: ghi message rồi trả `error`. Cần bảo đảm `bookingService` được inject đúng cách; đồng thời không để bean singleton giữ trạng thái riêng của từng flow trong instance field.

## 10. Event ID và event payload

Một `Event` có **event ID** và có thể có thêm attributes (payload). Event ID được dùng để chọn transition; attributes mang dữ liệu bổ sung cho phần xử lý tiếp theo.

Ví dụ, action muốn trả event `success` kèm mã xác nhận:

```java
protected Event doExecute(RequestContext context) {
    String confirmationCode = bookingService.confirm(
            (BookingRequest) context.getFlowScope().get("request"));

    return result("success", "confirmationCode", confirmationCode);
}
```

Ví dụ này giả định class đang kế thừa `AbstractAction` để sử dụng `result(...)`. Flow vẫn chọn transition theo `on="success"`; payload `confirmationCode` là dữ liệu bổ sung của event.

Nếu dữ liệu cần dùng ở nhiều state, thường dễ hiểu hơn khi ghi rõ vào `flowScope`:

```java
context.getFlowScope().put("confirmationCode", confirmationCode);
return success();
```

Chọn event payload khi dữ liệu chỉ gắn với outcome của action; chọn scope khi dữ liệu là một phần context cần tồn tại qua các state. Không dùng event ID để nhét toàn bộ object hoặc dữ liệu nhạy cảm vào tên sự kiện.

## 11. Nhiều action trong một action-state: thứ tự và outcome

Một `action-state` có thể khai báo nhiều action. Chúng được thực hiện theo thứ tự. Web Flow kiểm tra outcome sau mỗi action; nếu outcome khớp một transition đi ra khỏi action-state, flow chuyển theo transition đó và các action còn lại không được chạy. Nếu không có transition khớp, chuỗi action có thể tiếp tục với action tiếp theo.

Ví dụ:

```xml
<action-state id="prepareCheckout">
    <evaluate expression="cartValidationAction" />
    <evaluate expression="inventoryReservationAction" />
    <evaluate expression="pricingAction" />

    <transition on="invalidCart" to="editCart" />
    <transition on="outOfStock" to="changeItems" />
    <transition on="success" to="reviewCheckout" />
</action-state>
```

Hãy bảo đảm mỗi action trả đúng outcome và thứ tự được thiết kế rõ. Nếu action đầu trả `invalidCart`, flow đi tới `editCart`; các action giữ chỗ và tính giá không được chạy ở lần thực thi đó.

Đây là một dạng **Chain of Responsibility**: action-state thử từng action theo thứ tự và dừng khi có outcome khớp transition. Không nên dùng thứ tự ngầm này thay cho transaction orchestration phức tạp; với thao tác ghi nhiều bước, cần thiết kế rollback/compensation phù hợp.

## 12. Exception không tự động trở thành event error

Một lỗi thường gặp là nghĩ rằng method ném exception thì Spring Web Flow tự tạo event `error`. **Không nên dựa vào giả định đó.**

Tài liệu Web Flow khuyến nghị bắt các exception nghiệp vụ có thể phục hồi trong action, thêm message nếu cần và trả event kết quả phù hợp. Ví dụ:

```java
public String makeBooking(BookingRequest request,
                          RequestContext context) {
    try {
        bookingService.createBooking(request);
        return "success";
    } catch (RoomNotAvailableException ex) {
        context.getMessageContext().addMessage(
                new MessageBuilder()
                        .error()
                        .defaultText("Phòng vừa được đặt bởi khách khác.")
                        .build());
        return "roomUnavailable";
    }
}
```

Flow xử lý event được trả về:

```xml
<action-state id="makeBooking">
    <evaluate expression="bookingAction.makeBooking(flowScope.request, flowRequestContext)" />
    <transition on="success" to="bookingConfirmed" />
    <transition on="roomUnavailable" to="reviewBooking" />
</action-state>
```

Các exception không thể phục hồi hoặc lỗi hạ tầng cần được xử lý bằng exception handler/chính sách lỗi của flow execution. Không nên biến mọi lỗi kỹ thuật thành `success` hoặc một event nghiệp vụ giả. Khi dùng `FlowExecutionExceptionHandler`, hãy cấu hình theo hướng dẫn phiên bản; handler sai có thể để flow execution ở trạng thái không hợp lệ.

## 13. Kết hợp result event với dữ liệu trong scope

Một action thường vừa tạo outcome, vừa chuẩn bị dữ liệu cho state tiếp theo. Ví dụ:

```xml
<action-state id="loadOrder">
    <evaluate expression="orderService.find(orderId)"
              result="flowScope.order" />
    <transition on="success" to="reviewOrder" />
</action-state>
```

Nếu `find(orderId)` trả về `Order`, event được ánh xạ thành `success` theo quy tắc “kiểu khác” và object được lưu vào `flowScope.order` nhờ thuộc tính `result`.

Điều cần phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| Giá trị trả về của expression | Object `Order` |
| `result` | Đích lưu object vào `flowScope.order` |
| Event ID | `success` |
| `transition on="success"` | Điều hướng tới `reviewOrder` |

Nếu `orderService.find` trả `null` hoặc lỗi nghiệp vụ khi không tìm thấy đơn, hãy xác định hợp đồng rõ ràng. Có thể để service/action trả event `notFound` hoặc dùng một action chuyên biệt kiểm tra điều kiện; không để flow phụ thuộc vào một giá trị null mơ hồ.

`result-type` (nếu được dùng cho conversion) nói về **kiểu của dữ liệu được gán**, không phải cách đặt tên event. Đây là hai hợp đồng khác nhau.

## 14. Kiểm thử event mapping theo từng kiểu trả về

Nên kiểm thử chính xác event ID được tạo ra, sau đó xác nhận state đích:

| Kịch bản | Giá trị method trả về | Event mong đợi | Transition cần xác nhận |
| --- | --- | --- | --- |
| Có tồn kho | `Boolean.TRUE` | `yes` | `prepareOrder` |
| Hết tồn kho | `Boolean.FALSE` | `no` | `outOfStock` |
| Email trùng | `"duplicateEmail"` | `duplicateEmail` | `editEmail` |
| Đặt phòng được duyệt | `BookingOutcome.APPROVED` | `APPROVED` | `bookingConfirmed` |
| Service trả object xác nhận | `BookingConfirmation` | `success` | `showConfirmation` |
| Action chủ động trả Event | `new Event(this, "retry")` | `retry` | `retryPayment` |
| Exception nghiệp vụ được bắt | Action trả `"roomUnavailable"` | `roomUnavailable` | `reviewBooking` |

Với test flow, kiểm tra cả:

1. Action có được gọi đúng số lần không?
2. Method trả về đúng kiểu và giá trị như hợp đồng không?
3. Event ID có khớp transition không?
4. Flow chuyển tới state dự kiến không?
5. Các action sau có bị bỏ qua khi một outcome đã chọn transition không?
6. Dữ liệu cần thiết có được lưu vào scope/payload không?
7. Exception có được chuyển thành outcome rõ ràng hoặc đi vào exception handler đúng cách không?

Test unit cho method chỉ xác nhận logic Java. Cần thêm test Web Flow execution để xác nhận **quy tắc ánh xạ và transition** của framework.

## 15. Chẩn đoán khi action không đi đúng nhánh

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Boolean true nhưng không đi nhánh success | Transition đang nghe `on="true"` thay vì `on="yes"` | Kiểm tra mapping Boolean và event ID |
| String trả về đúng nhưng không có transition | Sai chính tả/khác chữ hoa thường giữa String và `on` | Log giá trị trả về, so sánh event ID |
| Enum không khớp transition | XML dùng tên khác enum constant | Kiểm tra `Enum.name()` và transition |
| Object trả về nhưng transition không chạy | Thiếu transition `on="success"` hoặc expression/action thất bại | Xác nhận kiểu object thuộc nhóm ánh xạ mặc định |
| Có outcome success nhưng view sau không thấy object | Chưa gán `result` hoặc chưa ghi vào scope | Kiểm tra `result="flowScope..."` và tên biến |
| Action thứ hai không được gọi | Action thứ nhất đã trả event khớp transition | Kiểm tra thứ tự action và transition |
| Exception bị đẩy ra ngoài flow | Chưa bắt exception phục hồi hoặc chưa có handler phù hợp | Đọc `Caused by`, xác định chính sách lỗi |
| Event custom không được nhận | Action trả sai ID hoặc tạo Event từ nhầm nguồn | Kiểm tra Event ID và cách đăng ký action |

Khi cần, bật log Web Flow:

```properties
logging.level.org.springframework.webflow=DEBUG
```

Tên logger và lượng log cụ thể thay đổi theo phiên bản. Khi điều tra, hãy ghi nhận flow ID, state ID, action/method, kiểu trả về, event ID và transition được chọn. Không ghi payload chứa thông tin nhạy cảm vào log dùng chung.

## 16. Checklist thiết kế outcome event dễ bảo trì

- [ ] Mỗi action có hợp đồng kết quả rõ: String, Boolean, Enum, object hoặc Event.
- [ ] Với Boolean, transition dùng `yes` và `no`.
- [ ] Với String, mọi event ID được khai báo đúng trong flow.
- [ ] Với Enum, transition dùng đúng tên constant.
- [ ] Với object nghiệp vụ, có transition `success` và gán `result` nếu state sau cần object.
- [ ] Với custom Action/MultiAction, event được tạo tường minh.
- [ ] Event ID được đặt theo ngôn ngữ nghiệp vụ và nhất quán chữ hoa/thường.
- [ ] Exception nghiệp vụ có thể phục hồi được bắt và ánh xạ thành outcome phù hợp.
- [ ] Lỗi không thể phục hồi được xử lý qua exception policy.
- [ ] Các action trong action-state có thứ tự và điều kiện dừng rõ.
- [ ] Test xác nhận event ID, state đích và dữ liệu scope.

## 17. Bài thực hành: vì sao flow không đi tới nhánh còn hàng?

Service:

```java
public Boolean isAvailable(String sku) {
    return inventoryRepository.available(sku);
}
```

Flow hiện tại:

```xml
<action-state id="checkStock">
    <evaluate expression="inventoryService.isAvailable(flowScope.sku)" />
    <transition on="true" to="prepareOrder" />
    <transition on="false" to="outOfStock" />
</action-state>
```

Khi service trả `Boolean.TRUE`, flow không đi tới `prepareOrder`.

**Câu hỏi:**

1. Spring Web Flow ánh xạ `Boolean.TRUE` thành event ID nào?
2. Hai thuộc tính `on` trong XML cần sửa ra sao?
3. Nếu service đổi sang trả `String` với các giá trị `"available"` và `"outOfStock"`, transition phải viết thế nào?
4. Nếu service trả `InventoryCheckResult`, event mặc định là gì?
5. Nếu action cần tạo event `retry` kèm mã lỗi, nên dùng POJO return mapping hay custom `Action`?

**Gợi ý lời giải:**

Với Boolean, event là `yes` hoặc `no`. Sửa flow:

```xml
<action-state id="checkStock">
    <evaluate expression="inventoryService.isAvailable(flowScope.sku)" />
    <transition on="yes" to="prepareOrder" />
    <transition on="no" to="outOfStock" />
</action-state>
```

Nếu trả String, dùng đúng chuỗi làm event ID. Nếu trả object `InventoryCheckResult`, outcome mặc định là `success`; muốn dùng object ở state sau thì gán vào `flowScope` bằng `result`. Nếu cần event custom có payload, triển khai `Action`/`MultiAction` và trả Event có ID `retry` cùng attributes phù hợp.

**Điểm cần nhớ:** Spring Web Flow ánh xạ giá trị trả về thành event theo kiểu: **String → chính chuỗi, Boolean → yes/no, Enum → tên constant, kiểu khác → success**. Flow dùng event ID đó để chọn transition. Khi cần outcome đặc biệt hoặc payload, hãy tạo Event trực tiếp; khi cần giữ dữ liệu cho state sau, hãy lưu riêng vào scope. Tách rõ **giá trị Java, event ID và state đích** giúp action-state điều hướng minh bạch và dễ kiểm thử.

## Tài liệu tham khảo chính thức

- [Spring Web Flow 2.5.x Reference Guide — Executing Actions](https://docs.spring.io/spring-webflow/docs/2.5.x/reference/html/actions.html)
- [Spring Web Flow 3.0.x Reference Guide](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/)
- [Action API — Spring Web Flow 2.5.1](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/execution/Action.html)
- [AbstractAction API — Spring Web Flow 2.5.1](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/action/AbstractAction.html)

Đối chiếu tài liệu đúng dòng phiên bản đang dùng, nhất là khi custom action, event factory hoặc exception handler đã được tùy chỉnh.
