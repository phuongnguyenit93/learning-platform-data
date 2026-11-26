# State và Transition trong mô hình điều khiển Spring Web Flow

> **Chương:** Kiến trúc thực thi  
> **Mục tiêu:** Đọc và thiết kế mô hình điều khiển của Spring Web Flow (SWF) dưới dạng đồ thị **state** và **transition**; hiểu cách một **FlowExecution** vận hành đồ thị đó qua các HTTP request, phân biệt vai trò của event, action, điều kiện, scope, validation và các điểm kết thúc.

## 1. Bài toán: một hành trình không chỉ là chuỗi trang

Giả sử một ứng dụng đặt lịch khám cần hỗ trợ:

1. Chọn dịch vụ.
2. Chọn khung giờ.
3. Nhập thông tin người đặt.
4. Xem lại và xác nhận.

Người dùng có thể nhấn **Tiếp tục**, **Quay lại**, **Hủy**. Khi xác nhận, hệ thống phải kiểm tra xem khung giờ còn trống không. Nếu khung giờ đã hết, quay về màn hình chọn giờ, giữ các dữ liệu hợp lệ đã nhập. Nếu đặt thành công, kết thúc flow.

Một sơ đồ điều hướng dạng tuyến tính:

~~~text
service -> slot -> contact -> review -> completed
~~~

không diễn tả đủ các nhánh `back`, `cancel`, lỗi validation hoặc kết quả service. Mô hình điều khiển của Spring Web Flow mô tả toàn bộ quy trình bằng một **đồ thị có hướng**:

- **Đỉnh:** các state có ý nghĩa trong vòng đời flow.
- **Cạnh:** các transition hợp lệ từ state nguồn sang state đích.
- **Tín hiệu chọn cạnh:** event và/hoặc điều kiện do flow đánh giá.
- **Dữ liệu đi cùng execution:** bản nháp, thông tin cần hiển thị, kết quả nghiệp vụ.

~~~mermaid
flowchart TD
    S["chooseService<br/>view-state"] -->|"next"| T["chooseSlot<br/>view-state"]
    T -->|"back"| S
    T -->|"next"| C["contact<br/>view-state"]
    C -->|"back"| T
    C -->|"next"| R["review<br/>view-state"]
    R -->|"edit"| T
    R -->|"confirm"| B["reserve<br/>action-state"]
    B -->|"booked"| E(("completed<br/>end-state"))
    B -->|"slotUnavailable"| T
    S -->|"cancel"| X(("cancelled"))
    T -->|"cancel"| X
    C -->|"cancel"| X
    R -->|"cancel"| X
~~~

**Điểm chính:** Flow không tự động “đi tới trang tiếp theo”. Nó chỉ chuyển state khi có **quy tắc chuyển trạng thái** tương ứng được thực thi.

## 2. Bốn thuật ngữ cần phân biệt trước khi đọc XML

| Khái niệm | Đơn vị mô hình hóa | Câu hỏi trả lời |
| --- | --- | --- |
| **FlowDefinition** | Định nghĩa tĩnh, được đăng ký bằng flow ID | Quy trình có những state và transition nào? |
| **State** | Một vị trí/bước của mô hình điều khiển | Execution đang ở đâu hoặc đang thực hiện gì? |
| **Event** | Một tín hiệu/kết quả được phát ra trong ngữ cảnh hiện tại | Điều gì vừa xảy ra? |
| **Transition** | Quy tắc chuyển từ source sang target | Với event/điều kiện này, flow sẽ đi đâu? |

Khi flow thực sự chạy, framework tạo một **FlowExecution**. Execution sử dụng flow definition nhưng có **trạng thái hiện hành và dữ liệu riêng**, không chia sẻ một biến `currentState` toàn cục cho mọi người dùng.

Ví dụ:

~~~text
FlowDefinition "appointment"
  states: chooseService, chooseSlot, contact, review, reserve, completed...

Execution A -> current state: chooseSlot
Execution B -> current state: review
Execution C -> current state: contact
~~~

Tất cả đều thực thi cùng định nghĩa nhưng đang ở những vị trí khác nhau. Đây là nền tảng giúp Spring Web Flow quản lý hành trình nhiều request mà không trải logic điều hướng khắp các controller.

### 2.1. Tên state không phải URL

`review` là **state ID** trong flow definition. Nó không nhất thiết có endpoint `/review` độc lập. Một endpoint Spring MVC/Web Flow có thể khởi tạo và tiếp tục nhiều state của cùng flow thông qua execution key.

Không nên đồng nhất ba khái niệm:

~~~text
Flow ID        = appointment
State ID       = review
Execution key  = khóa do Web Flow cấp cho một lần tiếp tục execution
~~~

Việc ghép URL, tạo execution key và sử dụng redirect phụ thuộc cấu hình Web Flow/MVC. Không tự xây execution key từ state ID hoặc tin một URL cũ luôn đại diện cho state mới nhất.

## 3. State là vị trí điều khiển, không nhất thiết là màn hình

Trong Spring Web Flow, state có các loại với ngữ nghĩa thực thi khác nhau.

| Loại state | Mục đích | Có thường chờ người dùng? | Ví dụ |
| --- | --- | --- | --- |
| `view-state` | Hiển thị giao diện, bind/validate form | Có | `chooseSlot` |
| `action-state` | Gọi một hoặc nhiều action phía server | Không; thường đi tiếp ngay theo outcome | `reserve` |
| `decision-state` | Rẽ nhánh dựa trên một điều kiện | Không | `checkEligibility` |
| `subflow-state` | Kích hoạt một flow con và nhận outcome | Phụ thuộc flow con | `verifyContact` |
| `end-state` | Kết thúc flow session/execution tương ứng | Không có transition nội bộ tiếp theo | `completed` |

Một state chính là một nút trong **mô hình điều khiển**. Với `action-state` hoặc `decision-state`, người dùng có thể không nhìn thấy màn hình riêng dù flow đã đi qua các state đó.

### 3.1. View-state: điểm tạm dừng để chờ tương tác

Khi execution vào `chooseSlot`, framework có thể render form và tạm dừng để chờ event từ request sau. Form có thể gửi `next`, `back` hoặc `cancel`; các event này chỉ có ý nghĩa vì state hiện tại khai báo transition tương ứng.

~~~xml
<view-state id="chooseSlot"
            view="appointment/choose-slot"
            model="draft">
    <transition on="next" to="contact"/>
    <transition on="back" to="chooseService" bind="false"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

Lưu ý: đây là đoạn XML tập trung vào điều hướng; việc binding các field có thể được khai báo thêm qua `<binder>`.

### 3.2. Action-state: state chạy logic phía server

~~~xml
<action-state id="reserve">
    <evaluate expression="appointmentAction.reserve(requestContext)"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

`reserve` gọi code Java để xử lý nghiệp vụ và phát event phản ánh outcome. Nếu kết quả là `booked`, execution đi vào `completed`; nếu khung giờ hết, quay về `chooseSlot`.

**Action-state không tự động là một HTTP request mới.** Nó có thể được thực thi ngay sau transition `confirm` trong request hiện tại rồi tiếp tục tới một view-state hoặc end-state.

### 3.3. Decision-state: state rẽ nhánh theo điều kiện

~~~xml
<decision-state id="checkEligibility">
    <if test="appointmentPolicy.isEligible(flowScope.draft)"
        then="review"
        else="notEligible"/>
</decision-state>
~~~

Đây là nhánh điều khiển dựa trên phép kiểm tra boolean, khác với việc người dùng nhấn nút phát event. Điều kiện nên không có side effect, vì flow có thể đi qua decision-state nhiều lần trong các hành trình sửa/bắt đầu lại.

### 3.4. Subflow-state: một state đại diện cho hành trình con

~~~xml
<subflow-state id="verifyContact" subflow="verifyContact">
    <input name="email" value="flowScope.draft.email"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="contact"/>
</subflow-state>
~~~

`verifyContact` là **một state của flow cha** nhưng khi được kích hoạt, nó mở một flow con có state, event và transition riêng. Outcome của flow con khi kết thúc được dùng để chọn transition trong subflow-state của flow cha.

### 3.5. End-state: dừng điều khiển flow

~~~xml
<end-state id="completed" view="appointment/completed"/>
<end-state id="cancelled" view="appointment/cancelled"/>
~~~

`end-state` biểu thị kết thúc theo định nghĩa. Nó **không đồng nghĩa** rollback database, tự hủy booking đã commit hoặc dọn sạch mọi dữ liệu bền vững ở hệ thống bên ngoài.

## 4. Transition là quy tắc của state nguồn

Một transition có thể xem là:

~~~text
source state + trigger/condition + action tùy chọn -> target state
~~~

Ví dụ:

~~~xml
<view-state id="contact" view="appointment/contact" model="draft">
    <transition on="back" to="chooseSlot" bind="false"/>
    <transition on="next" to="review"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

Ở đây, **source** được hiểu từ state chứa `<transition>`, và thuộc tính `to` xác định **target**.

| Source | Event | Target |
| --- | --- | --- |
| contact | back | chooseSlot |
| contact | next | review |
| contact | cancel | cancelled |

Nếu event `next` được gửi ở `chooseSlot`, transition của `contact` **không được áp dụng**. Mỗi state khai báo tập event và đường đi phù hợp riêng.

### 4.1. Cùng event, nhiều target tùy state

~~~xml
<view-state id="chooseService" view="appointment/service">
    <transition on="next" to="chooseSlot"/>
</view-state>

<view-state id="chooseSlot" view="appointment/slot">
    <transition on="next" to="contact"/>
</view-state>

<view-state id="contact" view="appointment/contact">
    <transition on="next" to="review"/>
</view-state>
~~~

Event `next` không có đích cố định toàn flow. Khi chạy, flow cần biết **state hiện tại** trước khi chọn transition.

### 4.2. Một state có thể có nhiều transition

`review` có thể hỗ trợ:

~~~xml
<view-state id="review" view="appointment/review">
    <transition on="edit" to="chooseSlot" bind="false"/>
    <transition on="confirm" to="reserve" bind="false"/>
    <transition on="cancel" to="cancelled" bind="false"/>
</view-state>
~~~

Điều này biến `review` thành một **điểm phân nhánh hợp lệ** trong đồ thị. Không có transition `next` ở state này thì gửi `next` không được ngầm diễn giải thành `confirm`.

## 5. Event là tín hiệu kích hoạt, không phải lệnh tùy ý

Trong Spring Web Flow, **Event** có event ID, có thể kèm attributes theo API. Event có thể xuất phát từ:

1. **HTTP form của người dùng:** `next`, `back`, `cancel`, `confirm`.
2. **Kết quả action phía server:** `booked`, `slotUnavailable`, `statusUnknown`.
3. **Outcome của flow con:** `verified` hoặc `cancelled`.

Ví dụ một request phát event:

~~~http
POST /appointment?execution=e1s2 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId=next&slotId=42
~~~

`execution=e1s2` là **giá trị minh họa**; khóa thật do Web Flow cấp, và cách framework dùng khóa phụ thuộc repository. `_eventId=next` báo ý định chuyển bước. `slotId=42` là dữ liệu request để binding/validation.

**Event không được xem là bằng chứng phân quyền.** Client có thể tự sửa `_eventId` hoặc gửi form cũ; framework và service phải bảo vệ việc điều hướng, dữ liệu và quyền độc lập.

### 5.1. Java action trả Event

Một action bean của ứng dụng có thể trả `org.springframework.webflow.execution.Event`:

~~~java
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public final class AppointmentAction {

    private final AppointmentService service;

    public AppointmentAction(AppointmentService service) {
        this.service = service;
    }

    public Event reserve(RequestContext context) {
        AppointmentDraft draft =
                (AppointmentDraft) context.getFlowScope().get("draft");

        ReservationOutcome result = service.reserveOnce(draft);

        if (result.isBooked()) {
            context.getFlowScope().put(
                    "reservationId", result.getReservationId());
            return new Event(this, "booked");
        }
        if (result.isSlotUnavailable()) {
            return new Event(this, "slotUnavailable");
        }
        if (result.isOutcomeUnknown()) {
            return new Event(this, "statusUnknown");
        }
        throw new IllegalStateException("Unhandled reservation outcome");
    }
}
~~~

`AppointmentService`, `AppointmentDraft` và `ReservationOutcome` là các kiểu minh họa do ứng dụng định nghĩa. Tên outcome là một phần **hợp đồng Java–flow XML**: action trả `statusUnknown` thì action-state phải có transition hoặc cơ chế xử lý phù hợp cho outcome đó.

## 6. Transition selection: engine chọn đường đi thế nào?

Với một view-state chờ tương tác, luồng xử lý logic thường là:

~~~mermaid
flowchart TD
    A["Nhận request với execution key"] --> B["Khôi phục FlowExecution"]
    B --> C["Xác định state hiện tại"]
    C --> D["Nhận event và dữ liệu request"]
    D --> E["Binding / validation nếu có"]
    E --> F{"Điều kiện hợp lệ?"}
    F -->|"Không"| G["Giữ view-state, báo lỗi"]
    F -->|"Có"| H["Tìm transition phù hợp"]
    H --> I{"Có transition?"}
    I -->|"Không"| J["Xử lý event chưa được khai báo theo chính sách framework"]
    I -->|"Có"| K["Thực thi transition/action liên quan"]
    K --> L["Đi vào target state"]
    L --> M{"Target có tạm dừng?"}
    M -->|"Có"| N["Render view, lưu/tạm dừng execution"]
    M -->|"Không"| O["Tiếp tục action/decision/end-state"]
~~~

Đây là sơ đồ **khái niệm**, không mô tả chính xác thứ tự mọi callback, transition criteria, binding và validation của tất cả loại state trong mọi phiên bản. Với `action-state`, event có thể được phát từ action thay vì HTTP.

### 6.1. Event chưa được khai báo không được tự suy diễn

Giả sử `review` có `edit`, `confirm` và `cancel`, nhưng client gửi `next`. Không có đường đi tương ứng thì engine phải xử lý sự kiện chưa được xử lý theo cơ chế Web Flow/cấu hình liên quan, có thể gây lỗi thực thi hoặc phản hồi phù hợp.

Không nên “tự động” đưa event lạ đến end-state success. Cần test các request bất thường, đặc biệt với thao tác ghi.

### 6.2. Guard và điều kiện không giống validation

Một transition/decision có thể phụ thuộc điều kiện:

~~~xml
<decision-state id="checkEligibility">
    <if test="appointmentPolicy.canContinue(flowScope.draft)"
        then="review"
        else="chooseSlot"/>
</decision-state>
~~~

Policy `canContinue(...)` kiểm tra điều kiện điều hướng, còn **validation** xử lý dữ liệu form đã bind. Ví dụ:

- `slotId` không phải số hợp lệ: lỗi conversion.
- `slotId` rỗng: lỗi required/validation.
- `slotId` hợp dạng nhưng đã được đặt: kết quả nghiệp vụ từ service.
- Người dùng thiếu quyền: từ chối theo bảo mật/service.

Đừng gom mọi tình huống thành một transition `on="error"` không rõ nguồn gốc.

## 7. Một HTTP request có thể đi qua nhiều state

Một hiểu lầm thường gặp là “mỗi state tương ứng một HTTP request”. Với Spring Web Flow, các state như `action-state` và `decision-state` có thể thực thi liên tiếp trên server trước khi framework trả response.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as FlowExecutor
    participant A as AppointmentAction
    participant S as AppointmentService
    U->>B: Nhấn Confirm tại review
    B->>F: POST event=confirm, execution key
    F->>F: review --confirm--> reserve
    F->>A: reserve(requestContext)
    A->>S: reserveOnce(draft)
    S-->>A: ReservationOutcome BOOKED
    A-->>F: Event booked
    F->>F: reserve --booked--> completed
    F-->>B: HTTP response/redirect theo cấu hình
    B-->>U: Hiển thị kết quả
~~~

Trong một request, execution có thể chuyển qua nhiều đỉnh của đồ thị cho tới khi gặp view-state cần tạm dừng hoặc end-state.

**View-state** thường là điểm chia ranh giới giữa các request, vì người dùng cần thời gian nhập form. Không giữ thread HTTP hoặc transaction database mở trong suốt khoảng chờ đó.

### 7.1. FlowExecution là máy trạng thái đang chạy

Nếu FlowDefinition là một **sơ đồ giao thông**, FlowExecution là một **chuyến đi cụ thể** đang ở một vị trí, có hành lý (scope data) và lịch sử tiếp tục riêng.

| Thành phần | Tính chất |
| --- | --- |
| FlowDefinition | Thường tái sử dụng; không lưu current state cho từng user |
| FlowExecution | Một lần chạy có current state và dữ liệu |
| FlowSession | Ngữ cảnh thực thi của flow đang hoạt động trong execution, có thể lồng nhau với subflow |
| FlowExecutionRepository | Lưu/khôi phục execution qua các request theo cấu hình |
| FlowExecutor | Điều phối start/resume và thực thi state/transition |

Các thành phần này phối hợp với nhau, nhưng không nên hoán đổi tên. Đặc biệt, **repository không định nghĩa đường đi**; nó lưu execution có thể được khôi phục để engine tiếp tục đi theo đường đã định nghĩa.

## 8. Bắt đầu, tạm dừng, tiếp tục và kết thúc

Một execution có vòng đời điển hình:

~~~text
START
  -> chọn start state
  -> thực thi state/action cần thiết
  -> đến view-state, render và PAUSE
  -> nhận request tiếp theo, RESUME bằng execution key
  -> event + transition -> state khác
  -> ... lặp lại ...
  -> end-state -> END
~~~

Điều này giải thích vì sao framework cần lưu trạng thái execution giữa các request, dù HTTP mang tính stateless ở mức giao thức.

### 8.1. State hiện tại không nằm trong một biến controller singleton

Nếu ứng dụng tự dùng biến `currentStep` trên singleton controller, nhiều người dùng sẽ ghi đè nhau. Web Flow quản lý state riêng theo execution và scope, nhờ đó cùng flow definition có thể phục vụ nhiều request/hành trình độc lập.

### 8.2. Start-state và end-state có ý nghĩa kiến trúc

Một flow bắt đầu từ **start-state** đã định nghĩa hoặc được chọn theo quy tắc framework. Các transition từ đó phải dẫn đến một điểm chờ hoặc kết thúc hợp lệ.

Một flow không nên có vòng lặp vô hạn giữa các action-state không bao giờ đến view/end-state, vì có thể giữ request HTTP chạy mãi. Khi xây đồ thị, cần xem lại các chu trình giữa state đồng bộ.

## 9. XML mẫu: mô hình điều khiển đầy đủ

Ví dụ sau tập trung mô tả các loại state và transition của flow `appointment`. Các lớp model, bean Java, validator, view và Spring MVC integration cần được ứng dụng cung cấp.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="chooseService">

    <var name="draft" class="com.example.appointment.AppointmentDraft"/>

    <on-start>
        <evaluate expression="appointmentDraftFactory.initialize(draft)"/>
    </on-start>

    <view-state id="chooseService"
                view="appointment/service"
                model="draft">
        <binder>
            <binding property="serviceCode" required="true"/>
        </binder>
        <transition on="next" to="chooseSlot"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="chooseSlot"
                view="appointment/slot"
                model="draft">
        <on-render>
            <evaluate expression="appointmentCatalog.listSlots(draft.serviceCode)"
                      result="viewScope.slots"/>
        </on-render>
        <binder>
            <binding property="slotId" required="true"/>
        </binder>
        <transition on="back" to="chooseService" bind="false"/>
        <transition on="next" to="contact"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="contact"
                view="appointment/contact"
                model="draft">
        <binder>
            <binding property="name" required="true"/>
            <binding property="email" required="true"/>
        </binder>
        <transition on="back" to="chooseSlot" bind="false"/>
        <transition on="next" to="checkEligibility"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <decision-state id="checkEligibility">
        <if test="appointmentPolicy.canReview(draft)"
            then="review"
            else="contact"/>
    </decision-state>

    <view-state id="review" view="appointment/review">
        <transition on="edit" to="chooseSlot" bind="false"/>
        <transition on="confirm" to="reserve" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="reserve">
        <evaluate expression="appointmentAction.reserve(requestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="slotUnavailable" to="chooseSlot"/>
        <transition on="statusUnknown" to="pending"/>
    </action-state>

    <view-state id="pending" view="appointment/pending">
        <transition on="check" to="checkReservation" bind="false"/>
    </view-state>

    <action-state id="checkReservation">
        <evaluate expression="appointmentAction.checkStatus(requestContext)"/>
        <transition on="booked" to="completed"/>
        <transition on="pending" to="pending"/>
    </action-state>

    <end-state id="completed" view="appointment/completed"/>
    <end-state id="cancelled" view="appointment/cancelled"/>
</flow>
~~~

### 9.1. Cách đọc XML như một đồ thị

1. `<flow>` mô tả quy trình và điểm bắt đầu.
2. `<view-state>` biểu thị điểm dừng/chờ người dùng.
3. `<action-state>` biểu thị bước thực thi phía server.
4. `<decision-state>` chọn một nhánh dựa trên điều kiện.
5. `<transition on="..." to="...">` mô tả cạnh từ state chứa nó tới target.
6. `<end-state>` là các nút kết thúc.
7. `<var>`, `model`, `<binder>` và `<evaluate>` phối hợp dữ liệu với điều khiển.

Lưu ý: ở action-state `checkReservation`, method `checkStatus` cần được triển khai **chỉ tra cứu/đối soát**, không tạo booking mới. `statusUnknown` biểu thị thao tác ghi trước đó có thể đã commit nhưng kết quả chưa xác định; không nên tự động retry bằng request mới.

### 9.2. Vì sao không dùng controller if/else cho mọi bước?

Một controller có thể tự điều hướng bằng `if (step == 2) ...` nhưng khi có nhiều nhánh back/cancel/retry, logic khó thấy và khó kiểm thử. Với Web Flow, mỗi transition được biểu diễn cạnh ngay trong định nghĩa; người đọc có thể lập bảng đường đi và xác nhận trạng thái đích.

## 10. Transition action và callback lifecycle của state

Transition không nhất thiết chỉ là một cạnh trống. Nó có thể chứa action được thực thi lúc chuyển:

~~~xml
<transition on="next" to="review">
    <evaluate expression="appointmentSummary.prepare(draft)"/>
</transition>
~~~

Khi state nguồn xử lý event `next` và transition đó được chọn, action `prepare` chạy trong đường chuyển. Tuy nhiên, những tác vụ ghi nghiệp vụ quan trọng có nhiều outcome thường phù hợp với `action-state` riêng để diễn đạt nhánh phục hồi rõ ràng.

State cũng có thể có action gắn với vòng đời:

~~~xml
<view-state id="chooseSlot" view="appointment/slot">
    <on-entry>
        <evaluate expression="appointmentPresenter.onChooseSlotEntered()"/>
    </on-entry>
    <transition on="next" to="contact"/>
    <on-exit>
        <evaluate expression="appointmentPresenter.onChooseSlotExited()"/>
    </on-exit>
</view-state>
~~~

Đoạn này minh họa ý tưởng **entry/exit action**; các method là do ứng dụng cung cấp. Khi triển khai, cần đối chiếu vị trí phần tử với XSD phiên bản Web Flow cụ thể. Không đặt logic trả tiền/tạo booking trong action chỉ để chuẩn bị hiển thị, bởi state có thể được vào lại khi người dùng quay về.

### 10.1. Action trong definition khác callback của FlowExecutionListener

`on-entry` và `on-exit` là hành vi **được định nghĩa trong flow**. `FlowExecutionListener` là điểm quan sát/mở rộng của executor, có các callback vòng đời riêng.

Nếu một action cần tạo event điều khiển transition, hãy dùng cơ chế action/event. Listener quan sát không nên tự ý sửa graph hoặc tạo booking khi một state được vào.

## 11. Binding và validation ảnh hưởng transition thế nào?

View-state có thể bind các field từ request trước khi cho event `next` đi qua transition. Mẫu:

~~~xml
<view-state id="contact"
            view="appointment/contact"
            model="draft">
    <binder>
        <binding property="name" required="true"/>
        <binding property="email" required="true"/>
    </binder>
    <transition on="next" to="review"/>
    <transition on="back" to="chooseSlot" bind="false"/>
</view-state>
~~~

Nếu email rỗng hoặc sai định dạng theo validator đã đăng ký, người dùng thường **ở lại `contact`** để sửa. Có transition `next` trong XML không có nghĩa mọi request chứa `_eventId=next` đều có quyền đi tiếp bất chấp lỗi binding/validation.

### 11.1. Lỗi form không phải event nghiệp vụ

| Input/tình huống | Tầng phát hiện | Phản hồi hợp lý |
| --- | --- | --- |
| `email` thiếu | Binder/validator | Giữ contact, báo lỗi field |
| `slotId` không đúng kiểu | Converter/binding | Giữ chooseSlot, báo lỗi field |
| `slotId` hợp dạng nhưng đã hết chỗ | Service ở bước xác nhận | Event `slotUnavailable`, quay lại chooseSlot |
| Quyền tạo lịch bị thu hồi | Security/service | Từ chối thao tác, không giả mạo outcome thành công |
| Timeout ghi chưa xác định kết quả | Service/action | Event `statusUnknown`, cho đối soát |

Điểm phân biệt là **event điều khiển** phản ánh một kết quả đã biết hoặc ý định từ form; **validation** bảo vệ việc chấp nhận dữ liệu trước khi transition thành công.

### 11.2. Back với `bind="false"`

Nút Back/Cancel có thể cần hoạt động dù form đang không hợp lệ. `bind="false"` cho phép bỏ qua binding đối với transition phù hợp.

Tác dụng phụ cần lưu ý: những thay đổi người dùng vừa gõ nhưng chưa được bind **có thể bị bỏ** khi quay lại. Nếu sản phẩm cần giữ dữ liệu đó, thiết kế binding/validation trên Back phải được xác định riêng.

## 12. Scope là dữ liệu; state là điều khiển

Mô hình state/transition không tự giải quyết câu hỏi **dữ liệu nằm ở đâu**. Thông thường:

| Scope | Ví dụ | Vòng đời khái quát |
| --- | --- | --- |
| `requestScope` | Kết quả tra cứu tạm của một request | Ngắn trong lần xử lý |
| `flashScope` | Thông báo ngắn hạn qua một chu kỳ điều hướng | Tùy vòng đời flash/render |
| `viewScope` | Danh sách slot hiển thị ở chooseSlot | Gắn với view-state |
| `flowScope` | AppointmentDraft, requestId nghiệp vụ | Qua nhiều state của execution |
| `conversationScope` | Dữ liệu cần chia sẻ qua các flow session liên quan | Qua conversation theo cấu hình |

`State` mô tả **đang ở bước nào**, còn scope dữ liệu trả lời **đã nhập gì, phải giữ bao lâu**.

Nếu ở `contact` nhấn Back về `chooseSlot`, transition cập nhật control state; bản nháp ở `flowScope` có thể giữ email đã nhập, nhưng phần dữ liệu chưa bind không tự được lưu.

### 12.1. Một flow có thể có nhiều execution đồng thời

Hai tab khác nhau có thể tạo hai execution độc lập, hoặc cùng mang một execution key nếu người dùng nhân bản tab. Không lưu bản nháp vào một field static hoặc HTTP session chung chỉ mang tên `draft`, vì có thể gây lẫn dữ liệu giữa hành trình.

### 12.2. Không cất entity đang attached trong flowScope

Flow execution có thể được snapshot/serialize theo repository. Nên giữ DTO nhỏ gọn, ID và dữ liệu cần thiết cho tương tác. Entity JPA đang attached, connection, stream hoặc kết quả query lớn không phù hợp làm state dài hạn của flow.

## 13. Transition của subflow: kết quả từ một đồ thị khác

Một flow cha có thể cần xác minh số điện thoại trước khi review:

~~~mermaid
flowchart TD
    A["Flow cha: contact"] --> B["Flow cha: subflow-state verifyPhone"]
    B --> C["Flow con: sendCode"]
    C --> D["Flow con: enterCode"]
    D -->|"đúng mã"| E(("Flow con: verified"))
    D -->|"hủy"| F(("Flow con: cancelled"))
    E -->|"outcome verified"| G["Flow cha: review"]
    F -->|"outcome cancelled"| A
~~~

Flow con có đồ thị state/transition độc lập. Khi nó kết thúc, **outcome end-state** được dùng như event kết quả tại `subflow-state` của flow cha.

Ví dụ:

~~~xml
<subflow-state id="verifyPhone" subflow="verifyPhone">
    <input name="phone" value="flowScope.draft.phone"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="contact"/>
</subflow-state>
~~~

Nếu flow con cần trả thêm dữ liệu, khai báo output/input mapping theo hợp đồng rõ ràng. Không giả định `flowScope` của flow con là cùng scope với flow cha hoặc dùng singleton bean để giữ dữ liệu người dùng.

**Một end-state của flow con không tự kết thúc flow cha**; flow cha tiếp tục theo transition được khai báo tại subflow-state.

## 14. Browser Back và snapshot: đừng nhầm với transition Back

Nút **Back của trình duyệt** điều khiển lịch sử điều hướng HTTP. Nút **Back của flow** gửi event `back` để lựa chọn transition:

~~~xml
<transition on="back" to="chooseSlot" bind="false"/>
~~~

Hai hành vi không đồng nghĩa:

- Browser Back có thể hiện trang cũ từ cache mà chưa gửi request lên server.
- Trang cũ có thể mang execution key/snapshot cũ.
- Repository có thể còn snapshot đó hoặc đã loại bỏ.
- Nếu snapshot được khôi phục, execution có thể tiếp tục từ state cũ tùy cấu hình.
- Nếu snapshot không còn, request không thể tiếp tục như dự kiến và cần đường phục hồi.

**Snapshot của flow không phải transaction rollback.** Một booking đã commit không bị hủy vì người dùng quay lại một trang HTML cũ.

### 14.1. Cần bảo vệ transition sau khi hoàn tất

Nếu người dùng gửi lại `confirm` từ một snapshot cũ, không được chỉ dựa vào việc flow đã tới `completed` để bảo đảm không tạo booking thứ hai. Service cần **idempotency** theo request ID nghiệp vụ, unique constraint và kiểm tra transaction phù hợp.

## 15. Thiết kế đồ thị dễ đọc và không tạo vòng lặp vô hạn

Một flow có thể chứa vòng lặp hợp lệ:

~~~text
chooseSlot --next--> review --edit--> chooseSlot
~~~

Người dùng chủ động sửa, nên vòng lặp qua view-state là hợp lý. Nhưng chuỗi action-state/decision-state như sau có thể nguy hiểm:

~~~text
actionA --success--> actionB --success--> actionA
~~~

Nếu không có điểm tạm dừng hay điều kiện thoát, engine có thể tiếp tục trong cùng một request cho tới khi gặp vấn đề thời gian/tài nguyên.

### 15.1. Quy tắc thiết kế đồ thị

1. Mỗi state có **tên diễn đạt mục đích**: `review`, `reserve`, `checkEligibility`.
2. Mỗi event có **ý nghĩa nhất quán trong ngữ cảnh state**: `confirm`, `cancel`, `slotUnavailable`.
3. Các action ghi được đặt ở state có outcome và đường phục hồi rõ ràng.
4. Mọi state quan trọng đều có đường xử lý lỗi, Back hoặc Cancel khi nghiệp vụ cho phép.
5. Các nhánh điều kiện phải có fallback phù hợp khi không thỏa.
6. Các chu trình đồng bộ không được vô hạn.
7. Không che logic quan trọng trong controller/listener ngoài đồ thị.
8. Sau end-state, mọi tác vụ bền vững đã thành công phải được xác nhận bằng service/database, không phải chỉ bằng màn hình.

### 15.2. Một event có thể được đặt tên sai về mặt nghiệp vụ

Ví dụ `on="success"` từ `reserve` dễ hiểu nhưng thiếu ngữ nghĩa nếu service có nhiều kết quả. Event `booked` nói rõ thao tác đã đạt điều gì; `slotUnavailable` nói rõ vì sao quay lại.

Tuy nhiên, tên event chỉ hữu ích khi implementation thực sự **bảo đảm outcome** tương ứng. Không phát `booked` trước khi giao dịch được xác nhận bền vững.

## 16. Bảo mật và transaction nằm ngoài đồ thị điều khiển

Flow state graph tổ chức hành trình nhưng không tự bảo đảm an toàn. Một client có thể:

- Gửi event khác với nút hiển thị.
- Sửa field ẩn của form.
- Gửi lại POST từ snapshot cũ.
- Cố gọi một execution đã hết hạn hoặc không thuộc mình.

Do đó, ngoài transition, ứng dụng cần:

- Spring Security bảo vệ HTTP request, session và CSRF.
- Kiểm tra quyền tại flow/state nếu dùng cơ chế Web Flow security phù hợp.
- Service kiểm tra ownership, trạng thái tài nguyên và quyền của principal.
- Transaction và idempotency để tránh tạo bản ghi trùng.
- Phản hồi an toàn khi exception, timeout hoặc kết quả commit chưa chắc chắn.

**Đường đi hợp lệ trong đồ thị không phải bằng chứng người dùng được phép thực hiện nghiệp vụ.**

### 16.1. Không coi `cancelled` là rollback

Khi user chọn Cancel, flow có thể đến `end-state cancelled`, nhưng không có bảo đảm các side effect đã xảy ra bị hoàn tác. Nếu đã tạo booking trước đó, cần một thao tác hủy riêng với quyền và policy rõ ràng.

## 17. Từ sơ đồ trạng thái đến bảng kiểm thử

Việc kiểm thử flow nên xuất phát từ **bảng chuyển trạng thái**. Với flow `appointment`:

| State trước | Event/kết quả | State sau hoặc phản hồi mong đợi |
| --- | --- | --- |
| Chưa chạy | Start | chooseService |
| chooseService | next hợp lệ | chooseSlot |
| chooseService | cancel | cancelled |
| chooseSlot | back | chooseService |
| chooseSlot | next, slotId hợp lệ | contact |
| chooseSlot | next, slotId sai định dạng | Giữ chooseSlot và báo lỗi |
| contact | next, email sai | Giữ contact và báo lỗi field |
| contact | next, dữ liệu hợp lệ, policy true | checkEligibility → review |
| contact | next, policy false | checkEligibility → contact |
| review | edit | chooseSlot |
| review | confirm | reserve |
| reserve | booked | completed |
| reserve | slotUnavailable | chooseSlot |
| reserve | statusUnknown | pending |
| pending | check | checkReservation |
| checkReservation | booked | completed |
| checkReservation | pending | pending |

Một test chỉ kiểm tra rằng giao diện review hiển thị **không chứng minh** action save chỉ chạy một lần, hoặc chỉ người có quyền được tạo booking.

### 17.1. Flow-level test (pseudocode)

~~~text
execution = startFlow("appointment")
assertCurrentState(execution, "chooseService")

execution = sendEvent(execution, "next", {
    serviceCode: "GENERAL"
})
assertCurrentState(execution, "chooseSlot")

execution = sendEvent(execution, "next", {
    slotId: "SLOT-42"
})
assertCurrentState(execution, "contact")

execution = sendEvent(execution, "next", {
    name: "Nguyen An",
    email: "an@example.com"
})
assertCurrentState(execution, "review")
~~~

Đây là **mã giả**, không phải API Java chạy nguyên văn. Khi triển khai phải sử dụng công cụ kiểm thử phù hợp với phiên bản SWF, khai báo mock/stub cho các bean service và bảo đảm validation thực sự được đăng ký.

### 17.2. Kiểm thử từng loại state

| Loại | Nội dung cần kiểm thử |
| --- | --- |
| View-state | Nhận đúng event, binder cho đúng field, validation giữ state khi lỗi |
| Action-state | Kết quả service được chuyển thành Event đúng, không che exception |
| Decision-state | Nhánh true/false dẫn đến đúng state, policy không có side effect |
| Subflow-state | Input/output và outcome của flow con được map đúng |
| End-state | Flow kết thúc với kết quả đã định nghĩa; không tự suy luận rollback |

### 17.3. Integration test cho những điều đồ thị không tự bảo đảm

Kiểm tra riêng:

- Hai POST `confirm` với cùng request ID không tạo booking trùng.
- Người dùng thiếu quyền không thể tạo booking dù gửi event hợp lệ.
- Browser Back/Forward với execution key cũ được xử lý đúng theo repository.
- Session hết hạn cho phản hồi phục hồi phù hợp.
- Service trả kết quả chưa xác định dẫn tới bước tra cứu, không tự ghi lại.
- Các flow khác nhau có bản nháp không lẫn dữ liệu.

## 18. Chẩn đoán khi flow đến sai state

Khi người dùng báo “nhấn Next nhưng không tới màn hình mong đợi”, hãy kiểm tra theo thứ tự:

1. **Định nghĩa flow nào đang chạy?** Flow ID có đúng không?
2. **Execution nào được tiếp tục?** Execution key có hợp lệ và được repository khôi phục không?
3. **State hiện tại là gì?** Có đúng với view mà browser đang hiển thị không?
4. **Event nào thật sự được gửi?** `_eventId` hay nút `_eventId_next` có đúng tên?
5. **Binding có thành công?** Field được phép bind có đúng kiểu và converter hợp lệ không?
6. **Validation có chặn transition?** Có message nào gắn source field không?
7. **State đó có transition cho event không?** Target ID có tồn tại không?
8. **Có action/decision trước target không?** Chúng trả outcome hoặc nhánh gì?
9. **Có exception chưa xử lý không?** Lỗi kỹ thuật khác với outcome nghiệp vụ.
10. **Sau transition, có subflow hoặc redirect không?** Đừng đoán current state chỉ từ URL.

Với dữ liệu nhạy cảm, log chỉ nên chứa **flow ID, state ID, event ID, outcome đã phân loại và correlation ID an toàn**, không log toàn bộ form/session hoặc token.

### 18.1. Test cả event không hợp lệ

Nếu client ở `chooseSlot` cố gửi `confirm`, không được bỏ qua review và thực hiện `reserve`. Bản đồ chuyển trạng thái phải định nghĩa rõ những event được hỗ trợ ở từng state, và test phải xác minh thao tác ghi không chạy từ request sai.

### 18.2. Khi action trả event không có transition

Giả sử Java đã thêm `statusUnknown` nhưng XML `reserve` vẫn chỉ khai báo `booked` và `slotUnavailable`. Flow không có đường đi tương ứng cho outcome mới. Đó là lỗi hợp đồng giữa code và definition; cần bổ sung transition và test.

## 19. Bài thực hành: vẽ máy trạng thái cho checkout

Thiết kế flow `checkout` gồm:

~~~text
cart → shipping → paymentReview → submitOrder → completed
  ^                                 |
  +----------- outOfStock ----------+
~~~

**Yêu cầu:**

1. Xác định flow ID, start-state, các view-state, một action-state và hai end-state (`completed`, `cancelled`).
2. Thêm event `next`, `back`, `cancel` và `confirm` tại đúng state.
3. Thêm một decision-state kiểm tra địa chỉ giao hàng có hợp lệ trước `paymentReview`.
4. Viết `<binder>` cho field địa chỉ và phương thức giao hàng; dữ liệu không hợp lệ phải giữ người dùng ở form.
5. Dùng action-state `submitOrder` với outcome `placed`, `outOfStock`, `statusUnknown` và transition phù hợp.
6. Tách subflow `verifyPhone` có outcome `verified` và `cancelled`; nêu rõ nhánh flow cha.
7. Chỉ rõ dữ liệu nào giữ ở `flowScope`, dữ liệu nào dùng riêng `viewScope`.
8. Phân tích browser Back sau khi đơn hàng đã được ghi: vì sao cần idempotency ở service?
9. Lập bảng state–event–target cho ít nhất 12 trường hợp, gồm nhánh hợp lệ và lỗi.
10. Viết pseudocode test với event `confirm` gửi sai state, validation thất bại và submit trùng.

**Gợi ý đồ thị:**

~~~mermaid
flowchart TD
    C["cart"] -->|"next"| S["shipping"]
    S -->|"next"| V{"validateDelivery"}
    V -->|"true"| R["paymentReview"]
    V -->|"false"| S
    R -->|"confirm"| A["submitOrder"]
    A -->|"placed"| E(("completed"))
    A -->|"outOfStock"| C
    A -->|"statusUnknown"| P["pendingStatus"]
    P -->|"check"| Q["checkOrderStatus"]
    Q -->|"placed"| E
    Q -->|"pending"| P
~~~

**Tiêu chí đạt:** sơ đồ mô tả rõ trách nhiệm của state và transition; action ghi chỉ chạy sau event đúng; điều kiện và validation không bị nhầm với exception; mọi outcome đều có đường phục hồi; service vẫn bảo vệ transaction và quyền truy cập độc lập với flow.

## 20. Tổng kết và câu hỏi ôn tập

Trong kiến trúc Spring Web Flow, **state** biểu diễn những vị trí/bước của một hành trình, còn **transition** là quy tắc chuyển từ state nguồn tới state đích khi event hoặc điều kiện tương ứng được xử lý. **FlowDefinition** là sơ đồ điều khiển dùng chung, **FlowExecution** là một lần chạy với current state và dữ liệu riêng. **FlowExecutor** thực thi sơ đồ đó, còn **repository** hỗ trợ lưu/khôi phục execution qua nhiều HTTP request.

Các loại state có vai trò khác nhau: `view-state` chờ người dùng, `action-state` gọi logic phía server, `decision-state` rẽ nhánh, `subflow-state` gọi flow con và `end-state` kết thúc. Binding/validation, scope, security và transaction phối hợp với đồ thị nhưng không đồng nghĩa với điều hướng.

**Câu hỏi tự kiểm tra:**

1. Vì sao gọi `view-state` là “một trang” chưa đủ chính xác để mô tả toàn bộ state trong Web Flow?
2. Cùng event `next` ở `chooseService` và `chooseSlot` có thể đi tới hai target khác nhau vì sao?
3. Một HTTP request có thể đi qua `review → reserve → completed` mà không cần ba request không?
4. `FlowDefinition` và `FlowExecution` khác nhau như thế nào khi có hai người dùng?
5. Vì sao dữ liệu form sai định dạng không nên được xem như event `slotUnavailable`?
6. Outcome của subflow được flow cha xử lý tại loại state nào?
7. Vì sao Browser Back không mặc định tương đương transition `on="back"`?
8. Nếu đồ thị đi đúng đường nhưng service tạo hai booking khi retry, vấn đề nằm ở trách nhiệm nào?
