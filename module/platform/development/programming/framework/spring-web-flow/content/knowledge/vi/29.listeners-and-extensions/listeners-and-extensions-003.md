# Phân biệt callback của listener với action trong định nghĩa Spring Web Flow

> **Chương:** Listener và mở rộng  
> **Chủ đề:** Khi nào dùng **FlowExecutionListener** để theo dõi vòng đời một flow, khi nào khai báo **action** trong flow definition để xử lý và điều hướng nghiệp vụ. Bài học dùng một quy trình đặt lịch nhiều bước để kết nối state, event, transition, scope, exception, kiểm thử và quan sát hệ thống.

## 1. Một hành trình, hai nhu cầu hoàn toàn khác nhau

Xét chức năng đặt lịch tư vấn gồm các bước:

1. Người dùng chọn khung giờ tại `chooseSlot`.
2. Xem lại thông tin tại `review`.
3. Nhấn **Xác nhận**, hệ thống gọi service để tạo lịch.
4. Nếu còn chỗ, flow kết thúc ở `completed`; nếu đã kín, flow trở lại `chooseSlot`.

Đồng thời, nhóm vận hành muốn biết:

- Một flow được khởi tạo bao nhiêu lần?
- Người dùng thường dừng ở state nào?
- Có bao nhiêu lần flow chuyển từ `review` sang `reserve`?
- Khi xảy ra exception, cần bổ sung ngữ cảnh gì vào log?

Hai nhóm nhu cầu này có thể cùng xuất hiện khi một execution chạy, nhưng không nên trộn lẫn:

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Kiểm tra số chỗ và tạo booking | **Action** gọi domain service | Là một bước nghiệp vụ quyết định outcome và transition |
| Phát event `booked` hoặc `slotUnavailable` | Action trong `action-state` | Flow cần biết kết quả để đi tới state tiếp theo |
| Chuẩn bị dữ liệu cho view | Action `on-entry` hoặc `on-render` | Là một phần đã khai báo của hành vi state |
| Đo thời gian flow tồn tại | **FlowExecutionListener** | Quan sát vòng đời, không tạo transition nghiệp vụ |
| Đếm lượt chuyển state | Callback của listener | Quan sát nhiều state/flow mà không sửa từng định nghĩa |
| Ghi nhận exception kỹ thuật | Listener kết hợp logging/observability | Cung cấp dữ liệu chẩn đoán, không thay thế xử lý lỗi |

**Quy tắc cốt lõi:** **Action** mô tả *flow phải làm gì*; **listener callback** mô tả *hệ thống quan sát hoặc mở rộng gì khi một sự kiện vòng đời xảy ra*. Listener không nên trở thành nơi ẩn logic điều hướng quan trọng khỏi flow definition.

## 2. Bức tranh tổng thể: definition, execution, action và listener

Spring Web Flow mô hình hóa luồng web nhiều bước bằng **flow definition**, trong đó có các **state**, **event** và **transition**. Mỗi lần người dùng khởi động quy trình sẽ có một **flow execution** chứa trạng thái và dữ liệu riêng.

~~~mermaid
flowchart TD
    D["Flow definition: booking"] --> S["State và transition"]
    S --> A["Action: chuẩn bị / kiểm tra / lưu booking"]
    E["FlowExecutor: chạy một execution"] --> S
    E --> L["FlowExecutionListener"]
    L --> O["Log, metrics, trace"]
    A --> B["BookingService"]
    B --> DB[("Database")]
~~~

Trong hình:

- **FlowExecutor** điều phối execution theo flow definition.
- **Action** được flow gọi tại vị trí xác định: khi bắt đầu, khi vào hoặc ra state, khi chuyển state, hoặc khi chạy action-state.
- **Listener** được đăng ký với cơ chế chạy flow để nhận các callback theo vòng đời.
- **Service** thực thi nghiệp vụ và bảo vệ transaction, phân quyền, tính nhất quán.

Điểm quan trọng: callback có thể quan sát state/event giống action nhưng **không có cùng hợp đồng điều khiển flow**. Một method listener trả về `void` không được Web Flow diễn giải như event `booked` để chọn transition.

## 3. Bảng so sánh trực tiếp

| Tiêu chí | Action trong flow definition | Callback của FlowExecutionListener |
| --- | --- | --- |
| Nơi khai báo/gắn kết | Trong XML flow: `on-start`, `on-entry`, `transition`, `action-state`... | Đăng ký listener với FlowExecutor/loader theo cấu hình |
| Ai quyết định lúc gọi? | Vị trí action trong định nghĩa và state đang thực thi | Các mốc vòng đời của execution mà listener đăng ký theo dõi |
| Phạm vi | Thường gắn với một state hoặc một flow cụ thể | Có thể áp dụng cho nhiều flow được chọn |
| Giá trị trả về | Action có thể trả `Event`/kết quả mà flow sử dụng | Callback không trả business event cho transition |
| Tác động mong muốn | Kiểm tra/ghi nghiệp vụ, xây model, quyết định outcome | Metrics, tracing, audit phù hợp, chẩn đoán |
| Độ dễ đọc quy trình | Người đọc XML nhìn thấy bước và đường đi | Logic nằm ngoài flow XML, khó thấy nếu dùng cho nghiệp vụ |
| Kiểm thử | Unit test action + flow test transition + integration test service | Unit test callback + integration test lifecycle/registration |
| Phục hồi khi lỗi | Chọn event/transition phục hồi hoặc exception handler | Quan sát exception, không tự sửa kết quả nghiệp vụ |

Không nên hiểu bảng này thành “listener tuyệt đối không được tác động gì tới ngữ cảnh”. Một số callback có thể truy cập RequestContext và exception từ callback có thể ảnh hưởng việc chạy flow. **Đó chính là lý do nên giới hạn listener vào trách nhiệm quan sát rõ ràng**, tránh biến nó thành bộ điều phối ngầm.

## 4. Action có những hình thức nào trong flow definition?

Ngoài `action-state`, Spring Web Flow cho phép đặt action ở các vị trí thể hiện mốc của quy trình. Những nhóm thường gặp:

| Vị trí | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| `on-start` của flow | Thực hiện khi bắt đầu flow session | Tạo một bản nháp có request ID |
| `on-entry` của state | Thực hiện khi đi vào state | Chuẩn bị danh sách khung giờ |
| `on-render` ở view-state | Thực hiện khi view được chuẩn bị/render theo cấu hình | Nạp dữ liệu hiển thị mới |
| `transition` action | Thực hiện trên đường chuyển state | Chuẩn bị summary khi nhấn Next |
| `on-exit` của state | Thực hiện khi rời state | Dọn dữ liệu view tạm thời nếu cần |
| `action-state` | Thực hiện action và chọn nhánh bằng outcome/event | Đặt lịch thành công hay hết chỗ |
| `on-end` của flow | Hành động khi flow kết thúc theo cấu hình | Dọn tài nguyên ngắn hạn do flow sở hữu |

Các action lifecycle vẫn là **action thuộc định nghĩa flow**. Chúng không phải callback của `FlowExecutionListener`, dù có những tên mốc gần giống nhau như `on-start` và `sessionStarted`.

### 4.1. Ví dụ XML: hành vi nghiệp vụ được khai báo rõ

Đoạn dưới đây là một flow rút gọn; lớp model, service, action bean, validator, view và cấu hình tích hợp Spring MVC do ứng dụng cung cấp:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="chooseSlot">

    <var name="booking" class="com.example.booking.BookingDraft"/>

    <on-start>
        <!-- Khởi tạo một lần cho flow mới. -->
        <evaluate expression="bookingDraftFactory.initialize(booking)"/>
    </on-start>

    <view-state id="chooseSlot"
                view="booking/choose-slot"
                model="booking">
        <on-entry>
            <evaluate expression="bookingPresenter.prepareSlots(requestContext)"/>
        </on-entry>
        <binder>
            <binding property="slotId" required="true"/>
        </binder>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="chooseSlot" bind="false"/>
        <transition on="confirm" to="reserve" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="reserve">
        <evaluate expression="bookingAction.reserve(requestContext)"/>
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

Nhìn vào XML, người học biết **confirm dẫn tới reserve**, và reserve có ba outcome được định nghĩa. Đây là thông tin mang ý nghĩa nghiệp vụ, vì vậy cần hiển thị ở bản đồ flow thay vì ẩn trong listener.

### 4.2. Dùng `on-entry` có làm callback listener trở nên thừa không?

Không. Cả hai đều có thể xảy ra quanh thời điểm vào state nhưng mục tiêu khác:

- `on-entry` chuẩn bị dữ liệu hoặc thực hiện hành động mà **state cần** để hoạt động đúng.
- `stateEntering` / `stateEntered` của listener dùng để quan sát chuyển động của execution, đo thời gian hoặc ghi dấu vết.

Nếu bỏ listener metrics, flow vẫn cần chuẩn bị danh sách slot để người dùng chọn. Nếu bỏ action chuẩn bị dữ liệu, listener logging không tự cung cấp danh sách slot.

## 5. Action có thể trả event để điều hướng

Trong SWF, một method action thường nhận `RequestContext` và trả `Event`, hoặc trả kết quả được framework chuyển thành outcome theo cơ chế action được dùng.

~~~java
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;

public final class BookingAction {

    private final BookingService bookingService;

    public BookingAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public Event reserve(RequestContext context) {
        BookingDraft draft =
                (BookingDraft) context.getFlowScope().get("booking");

        BookingResult result = bookingService.reserveOnce(draft);

        switch (result.getStatus()) {
            case CONFIRMED:
            case ALREADY_CONFIRMED:
                context.getFlowScope().put(
                        "bookingId", result.getBookingId());
                return new Event(this, "booked");
            case SLOT_UNAVAILABLE:
                return new Event(this, "slotUnavailable");
            case OUTCOME_UNKNOWN:
                return new Event(this, "statusUnknown");
            default:
                throw new IllegalStateException(
                        "Unhandled booking status");
        }
    }
}
~~~

`BookingDraft`, `BookingService`, `BookingResult` và các status là **kiểu nghiệp vụ minh họa**, không phải API sẵn có của Web Flow. Service phải bảo đảm phân quyền, transaction và idempotency. `OUTCOME_UNKNOWN` chỉ được dùng khi chưa xác định lệnh ghi đã commit hay chưa; không được tự phát ra để che lỗi lập trình.

Action trả event `slotUnavailable` rồi FlowExecutor chọn transition `on="slotUnavailable"` để về `chooseSlot`. Callback listener có thể nhìn thấy event/chuyển state tương ứng, nhưng **không thay thế vai trò trả event của action**.

### 5.1. Vì sao xử lý nghiệp vụ qua listener là sai hướng?

Ví dụ thiết kế kém:

~~~java
// ANTI-PATTERN: không làm như thế này.
// Trong callback stateEntered(review):
//   tự gọi bookingService.reserveOnce(...)
//   tự sửa biến flow để ép đến completed
~~~

Khi người dùng chỉ tới trang review, listener có thể chạy dù họ chưa xác nhận. Như vậy việc **xem lại trang** có nguy cơ tạo booking. Hơn nữa, người đọc XML không thấy điểm ghi dữ liệu và khó biết cách kiểm thử. Nên chỉ gọi `reserveOnce` ở action-state `reserve` được kích hoạt bởi event `confirm`.

## 6. FlowExecutionListener quan sát những mốc nào?

Web Flow có giao diện `org.springframework.webflow.execution.FlowExecutionListener` và adapter `FlowExecutionListenerAdapter` cho việc xử lý một số callback cụ thể. Những nhóm mốc thường gặp:

| Nhóm lifecycle | Callback điển hình | Khi nào quan sát? |
| --- | --- | --- |
| Tạo và bắt đầu flow session | `sessionCreating`, `sessionStarting`, `sessionStarted` | Khi chuẩn bị/khởi động một session của flow |
| Phát sự kiện | `eventSignaled` | Khi execution xử lý một event |
| Chuyển trạng thái | `transitionExecuting`, `transitionExecuted` | Quanh việc thực thi transition |
| Vào state | `stateEntering`, `stateEntered` | Quanh việc vào một state |
| Render view | `viewRendering`, `viewRendered` | Quanh việc render view theo cơ chế Web Flow |
| Dừng và tiếp tục | `paused`, `resumed` | Khi execution chờ request kế tiếp hoặc được tiếp tục |
| Kết thúc flow session | `sessionEnding`, `sessionEnded` | Khi một session của flow kết thúc |
| Phát hiện exception trong execution | `exceptionThrown` | Khi execution thông báo một exception đến listener |

Danh sách là sơ đồ khái niệm của API SWF thường dùng; **chữ ký method và điều kiện gọi phải được đối chiếu đúng phiên bản thư viện dự án**. Ví dụ, một flow có subflow sẽ có vòng đời session lồng nhau, và không phải callback nào cũng tương ứng một HTTP request riêng.

### 6.1. Không lẫn tên callback với tên action

`sessionStarted` là callback quan sát **flow session đã bắt đầu**. `<on-start>` là vị trí action khai báo trong flow definition. Hai sự kiện có liên quan về thời gian, nhưng không có nghĩa có thể thay thế cho nhau:

- Tạo request ID nghiệp vụ cần thiết cho flow: dùng action khởi tạo đã khai báo.
- Đếm lượt khởi động flow: dùng listener, metrics.
- Áp dụng chính sách quyền trước thao tác nhạy cảm: dùng security và service; listener bảo mật chuyên dụng có thể hỗ trợ nhưng không thay được kiểm tra tại tầng nghiệp vụ.

### 6.2. Không đoán chắc thứ tự callback

Một request chuyển từ `review` sang `reserve` thường bao gồm **tiếp tục execution → nhận event confirm → xử lý transition → thực hiện action-state → chuyển sang end/view-state → phản hồi**. Listener có thể nhận nhiều callback xen kẽ.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser
    participant Executor as FlowExecutor
    participant Listener as FlowExecutionListener
    participant Action as BookingAction
    participant Service as BookingService
    User->>Browser: Nhấn Confirm
    Browser->>Executor: POST execution key, event confirm
    Executor-->>Listener: Callback vòng đời / event / transition
    Executor->>Action: reserve(requestContext)
    Action->>Service: reserveOnce(draft)
    Service-->>Action: BookingResult CONFIRMED
    Action-->>Executor: Event booked
    Executor-->>Listener: Callback thay đổi state / kết thúc
    Executor-->>Browser: Trang kết quả
~~~

**Sơ đồ chỉ minh họa thứ tự logic**, không cam kết thứ tự từng callback before/after. Để kiểm tra chính xác khi listener gọi quanh action/transition và khi exception xuất hiện, phải viết integration test với phiên bản Web Flow thực tế.

## 7. Viết listener quan sát mà không thay đổi nghiệp vụ

Một implementation dùng `FlowExecutionListenerAdapter` chỉ override những callback cần thiết. Ví dụ theo dõi event, state và exception:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.webflow.definition.State;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.FlowExecutionException;
import org.springframework.webflow.execution.FlowExecutionListenerAdapter;
import org.springframework.webflow.execution.RequestContext;

public final class FlowDiagnosticsListener
        extends FlowExecutionListenerAdapter {

    private static final Logger log =
            LoggerFactory.getLogger(FlowDiagnosticsListener.class);

    @Override
    public void eventSignaled(RequestContext context, Event event) {
        log.debug("flow={} event={}",
                context.getActiveFlow().getId(),
                event.getId());
    }

    @Override
    public void stateEntered(
            RequestContext context, State previousState, State state) {
        log.debug("flow={} state={}",
                context.getActiveFlow().getId(),
                state.getId());
    }

    @Override
    public void exceptionThrown(
            RequestContext context, FlowExecutionException exception) {
        log.warn("flow={} exceptionType={}",
                context.getActiveFlow().getId(),
                exception.getClass().getSimpleName());
    }
}
~~~

Ví dụ không in thông tin liên hệ, nội dung form, thông số thanh toán hoặc toàn bộ execution key. Trong hệ thống thật cần bổ sung quy tắc bảo mật log và trace theo chính sách.

### 7.1. Vì sao không cất thông tin từng người dùng trong field của listener?

Listener được đăng ký bằng một Spring bean có thể dùng chung cho nhiều execution, nhiều request và nhiều thread. Không được giả định nó được tạo mới cho mỗi người dùng.

Sai:

~~~java
// ANTI-PATTERN, không thread-safe và lẫn dữ liệu giữa execution:
private String currentBookingId;

public void eventSignaled(RequestContext context, Event event) {
    currentBookingId = "...";
}
~~~

Thay vào đó:

- Dùng `RequestContext` để truy cập ngữ cảnh hiện hành nếu cần.
- Lưu dữ liệu nghiệp vụ thuộc execution vào scope tương ứng, không để trong field của listener singleton.
- Dùng công cụ metrics thread-safe như counter/timer, chỉ ghi nhãn có cardinality thấp.
- Dùng trace/correlation context có vòng đời và cơ chế dọn dẹp rõ, tránh lẫn giữa các request.

### 7.2. Callback có thể gây lỗi ngược trở lại flow

Một listener thực hiện I/O đồng bộ đến dịch vụ quan sát có thể làm chậm flow; nếu nó ném exception, execution có thể bị ảnh hưởng tùy vị trí callback và xử lý framework.

Với metrics và log **không trọng yếu**, nên ưu tiên cơ chế quan sát có khả năng chịu lỗi và không làm người dùng mất khả năng đặt lịch chỉ vì hệ thống metrics ngừng hoạt động. Nếu mục tiêu thật sự là một audit bắt buộc, xem phần ranh giới transaction để thiết kế cơ chế bền vững đúng chỗ.

## 8. Đăng ký listener khác với khai báo action trong XML

Action thuộc **flow definition**; listener được gắn vào **cơ chế thực thi flow**. Trong cấu hình Spring XML kiểu Web Flow 2.x, mô hình đăng ký listener có thể tương tự:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         http://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/webflow-config
         http://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd">

    <bean id="flowDiagnosticsListener"
          class="com.example.webflow.FlowDiagnosticsListener"/>

    <webflow:flow-executor id="flowExecutor"
                           flow-registry="flowRegistry">
        <webflow:flow-execution-listeners>
            <webflow:listener ref="flowDiagnosticsListener"/>
        </webflow:flow-execution-listeners>
    </webflow:flow-executor>
</beans>
~~~

Đây là **mẫu cấu hình minh họa**, chưa bao gồm việc định nghĩa `flowRegistry` và tích hợp Spring MVC. Một số phiên bản cho phép giới hạn listener theo flow ID/criteria hoặc cấu hình programmatic bằng các thành phần liên quan listener loader. **Cần dùng đúng schema và API của phiên bản Web Flow mà dự án triển khai**.

Nếu muốn theo dõi tất cả flow, listener có thể được đăng ký ở mức executor với phạm vi phù hợp. Nếu chỉ muốn một flow, nên dùng cơ chế chọn flow được hỗ trợ thay vì viết hàng loạt câu `if` tự suy đoán state/ID trong mọi callback.

### 8.1. Không có nghĩa annotation `@Component` tự biến bean thành listener

Đăng ký một lớp làm Spring bean chỉ tạo đối tượng có thể được dependency injection. Để Web Flow gửi lifecycle callbacks đến nó, bean phải được **nối vào executor/listener loader theo cơ chế cấu hình**. Đây là vấn đề wiring khác với việc flow XML gọi `bookingAction.reserve(...)`.

## 9. Callback nào tương ứng với action nào?

Một cách học hiệu quả là đặt các mốc cùng tên cạnh nhau:

| Vị trí action | Callback gần thời điểm đó | Khác biệt cần nhớ |
| --- | --- | --- |
| `<on-start>` | `sessionStarting` / `sessionStarted` | Action khởi tạo dữ liệu; callback quan sát vòng đời session |
| `<on-entry>` | `stateEntering` / `stateEntered` | Action của state; callback quan sát việc vào state |
| `<on-render>` | `viewRendering` / `viewRendered` | Action chuẩn bị view; callback có thể theo dõi quá trình render |
| Action trên `<transition>` | `transitionExecuting` / `transitionExecuted` | Action thuộc đường chuyển; callback theo dõi đường chuyển |
| `<action-state>` | Các callback event/transition/state có liên quan | Action trả outcome; listener không trả event |
| `<on-end>` | `sessionEnding` / `sessionEnded` | Action dọn dẹp theo flow; callback thông báo kết thúc |

Đây là **ánh xạ mục đích**, không phải một lịch gọi từng method chính xác. Với view rendering/redirect, các callback có thể được kích hoạt trong những request khác nhau theo cấu hình. Một flow có thể đi qua nhiều action-state/decision-state trong cùng một request.

### 9.1. Thứ tự before/after có quan trọng không?

Có, đặc biệt khi đo thời gian hoặc ghi log:

- `stateEntering` khác `stateEntered`: một bên quanh thời điểm bắt đầu nhập state, bên kia sau khi state được nhập theo callback contract.
- `transitionExecuting` khác `transitionExecuted`: chúng quan sát hai mốc quanh quá trình chuyển.
- `sessionEnding` khác `sessionEnded`: đặc biệt quan trọng nếu đọc dữ liệu còn tồn tại và muốn đo trạng thái hoàn tất.

Không nên thiết kế một invariant nghiệp vụ dựa vào thứ tự callback mà chưa xác minh hợp đồng API. Nếu cần tạo booking **trước khi** end-state, hãy khai báo action tương ứng trước transition đến `completed`; đừng dựa vào `sessionEnded`.

## 10. Event từ action và callback eventSignaled không giống nhau

Khi người dùng gửi:

~~~http
POST /booking?execution=e1s3 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId=confirm
~~~

Flow đang ở `review` có transition `on="confirm" to="reserve"`. Khi `BookingAction.reserve(...)` trả `Event("booked")`, action-state có thể chọn transition sang `completed`.

Listener `eventSignaled` có thể quan sát các event liên quan tới execution theo hợp đồng framework. Tuy nhiên:

1. Callback không sinh ra một **event điều hướng mới** chỉ vì nó nhận event `confirm`.
2. Callback không có trách nhiệm gọi `bookingService.reserveOnce(...)`.
3. Callback không nên suy ra mọi event tên `booked` đều tương đương transaction đã commit nếu service có bug; xác nhận nghiệp vụ phải ở service.
4. Nếu muốn ghi metrics `booking_completed`, cần tránh đếm lặp do replay/snapshot/retry và chọn đúng mốc phản ánh sự hoàn tất thực sự.

Tổng quát:

~~~text
Event + state hiện tại -> chọn transition
Action -> có thể tạo event nghiệp vụ cho transition
Listener callback -> quan sát những mốc đó, không tự tạo nhánh nghiệp vụ
~~~

## 11. Đừng đặt tác dụng phụ quan trọng trong listener

Một listener nhìn thấy mốc `stateEntered(completed)` hoặc `sessionEnded` rất thuận tiện để gửi email, cập nhật database, phát hóa đơn, trừ tiền. Nhưng đó là thiết kế dễ gây sai lệch khi có retry, exception, failover hay execution được khôi phục từ snapshot.

| Tác vụ | Có nên đặt trong listener? | Giải pháp phù hợp hơn |
| --- | --- | --- |
| Ghi metric lượt vào state | Có, nếu thread-safe và chịu lỗi | Listener + metrics |
| Log event kỹ thuật đã được chọn lọc | Có | Listener + structured logs |
| Phân tích thời gian một flow | Có, với timer và ranh giới được test | Listener + tracing |
| Tạo booking mới | Không nên | Action-state gọi service transactional |
| Trừ tiền | Không nên | Service thanh toán với idempotency và transaction thích hợp |
| Gửi email xác nhận bắt buộc | Không nên dựa duy nhất vào callback | Domain event/outbox hoặc worker tiêu thụ sự kiện đã commit |
| Kiểm tra quyền trước mỗi lần ghi | Không nên chỉ dựa vào listener | Spring Security + domain service |
| Hủy booking đã commit | Không nên coi `cancelled` callback là rollback | Nghiệp vụ hủy riêng, có quyền và transaction |

### 11.1. Ví dụ nguy hiểm: gửi email tại sessionEnded

~~~java
// ANTI-PATTERN: callback có thể không mang hợp đồng exactly-once.
// @Override
// public void sessionEnded(RequestContext ctx, FlowSession session,
//                          String outcome) {
//     if ("completed".equals(outcome)) {
//         emailService.sendConfirmation(...);
//     }
// }
~~~

Nếu gửi email thành công rồi response thất lạc, hoặc callback bị gọi lại ở một bối cảnh phục hồi, người dùng có thể nhận email trùng. Nếu email là một yêu cầu nghiệp vụ gắn với booking đã commit, nên lưu **ý định gửi** trong transaction phù hợp (chẳng hạn outbox) và xử lý idempotent. Listener có thể ghi metrics thông tin việc flow kết thúc, không bảo đảm phát thông báo exactly-once.

### 11.2. Không giữ transaction qua view-state

Flow có thể chờ người dùng vài phút giữa các trang. Không giữ một database transaction hoặc connection mở trong suốt thời gian đó. Action gọi service thực hiện transaction ngắn tại thời điểm cần ghi; listener chỉ quan sát execution và không chiếm giữ tài nguyên hạ tầng lâu dài.

## 12. Exception trong action và exceptionThrown của listener

Phân biệt các tình huống:

| Tình huống | Action/flow làm gì? | Listener có vai trò gì? |
| --- | --- | --- |
| Email sai định dạng | View-state validation báo field error | Có thể thu thập metrics lỗi input nếu thiết kế |
| Slot đã kín | Service trả business outcome; action phát `slotUnavailable` | Quan sát event/chuyển state |
| Timeout ghi nhưng kết quả chưa rõ | Action/service trả trạng thái phục hồi có ý nghĩa hoặc handler xử lý | Ghi nhận thông tin kỹ thuật, không khẳng định thất bại |
| Bug ném NullPointerException | Exception handler phù hợp tiếp quản | `exceptionThrown` có thể ghi thông tin chẩn đoán |

**Không có quy tắc “mọi exception tự biến thành event error”**. FlowExecutionListener nhận callback lỗi theo API tương ứng, nhưng nó không tự cung cấp transition `on="error"` và cũng không bảo đảm mọi exception đã được action bắt sẽ tới `exceptionThrown`.

### 12.1. Một listener exception không phải exception handler nghiệp vụ

Ví dụ việc quan sát:

~~~java
@Override
public void exceptionThrown(
        RequestContext context, FlowExecutionException exception) {
    log.warn("Flow execution failure: type={}",
            exception.getClass().getSimpleName());
}
~~~

Đoạn này ghi log. Nó **không chọn state phục hồi**. Nếu muốn cho người dùng thử lại khi dịch vụ tra cứu lỗi, action/service cần phân loại đúng lỗi và trả event phục hồi có chủ đích. Nếu kết quả ghi chưa xác định, phải tra cứu bằng request ID và bảo vệ idempotency.

Trường hợp exception ngoài dự kiến cần được xử lý an toàn ở tầng Web Flow/MVC phù hợp phiên bản; không nên chỉ viết listener logging rồi cho rằng UX phục hồi đã hoàn thiện.

## 13. Listener và subflow: dễ đếm sai số lượng sự kiện

Một flow đặt lịch có thể gọi flow con `verifyPhone`:

~~~mermaid
flowchart TD
    A["booking: review"] --> B["subflow-state verifyPhone"]
    B --> C["verifyPhone: enterCode"]
    C -->|"verified"| D["verifyPhone: end verified"]
    D --> E["booking: reserve"]
    E --> F["booking: completed"]
~~~

Ở mức **flow execution**, có thể tồn tại một conversation với flow session cha và flow session con. Listener đã đăng ký có thể quan sát mốc bắt đầu/kết thúc của từng session tùy phạm vi.

Do đó:

- Đếm `sessionStarted` **không nhất thiết** tương đương số người bắt đầu một booking.
- Đếm `sessionEnded` **không nhất thiết** tương đương số booking thành công.
- Kết thúc subflow `verified` là outcome của tác vụ xác minh, **không phải** booking đã hoàn tất.
- Một event `cancelled` ở flow con có thể chỉ dẫn flow cha quay lại màn hình khác; chưa chắc conversation chính kết thúc.

Để đo **booking thành công**, nên dựa trên kết quả bền vững từ service hoặc một event miền nghiệp vụ đã commit. Listener hữu ích cho **hành vi điều hướng** và có thể gắn nhãn flow ID/state ID rõ ràng.

## 14. Concurrency, snapshot và trình duyệt Back/Forward

Khi người dùng nhấn **Browser Back**, trình duyệt có thể hiển thị trang từ lịch sử/cache mà **không phát request tới server**. Khi không có request vào Web Flow, listener cũng không có callback mới để quan sát lần hiển thị đó.

Khi người dùng submit form cũ có execution key/snapshot còn hợp lệ, framework có thể khôi phục một trạng thái cũ theo repository. Những callback sau đó phản ánh **execution thực sự xử lý**, không phải “người dùng chắc chắn đang trên trang mới nhất”.

Những hệ quả khi đo metrics:

1. Một người có thể vào cùng state nhiều lần khi Back/Edit.
2. Hai tab có thể chạy hai execution riêng hoặc cùng một execution key.
3. Retry HTTP có thể khiến một callback mốc xử lý xuất hiện thêm lượt.
4. Snapshot cũ có thể không còn được repository chấp nhận.

Không dùng số callback để khẳng định **đúng một** transaction thành công. Dữ liệu nghiệp vụ cần idempotency key, unique constraint và giao dịch phù hợp ở service/database.

## 15. Bảo mật và tính riêng tư trong listener

`RequestContext` có thể dẫn tới dữ liệu scope, form và thông tin execution. Những dữ liệu này thường nhạy cảm hơn tên state/event. Một listener logging áp dụng nhiều flow cần hạn chế những gì được ghi.

**Nên:**

- Chỉ ghi flow ID, state ID, event ID thuộc danh sách cho phép và thời gian xử lý.
- Che giấu hoặc không ghi session ID, execution key, request ID nghiệp vụ, token, email và nội dung form.
- Tách lỗi nghiệp vụ dự kiến khỏi lỗi kỹ thuật; tránh log một validation error như sự cố hạ tầng nghiêm trọng.
- Giới hạn nhãn metrics ở những giá trị có cardinality thấp.
- Áp dụng chính sách retention, truy cập log và trace phù hợp.

**Không nên:**

- Dùng listener như điểm duy nhất để kiểm tra phân quyền thao tác ghi.
- Tin rằng client gửi event `confirm` có nghĩa họ được phép đặt lịch.
- Log toàn bộ `flowScope` hoặc `requestParameters` để “debug cho nhanh”.
- Tin rằng có callback `sessionStarted` mới bảo đảm người dùng vẫn có quyền ở request tiếp theo.

Nếu ứng dụng dùng `SecurityFlowExecutionListener` hoặc một extension bảo mật, vẫn cần kiểm tra quyền ở domain service tại thời điểm ghi, đặc biệt khi người dùng có thể quay lại snapshot cũ hoặc bị thay đổi quyền giữa các bước.

## 16. Chọn đúng công cụ mở rộng

Không phải mọi nhu cầu tùy biến Web Flow đều cần listener. Bảng quyết định:

| Muốn làm gì? | Ưu tiên |
| --- | --- |
| Chạy nghiệp vụ khi người dùng nhấn nút | Action trong transition/action-state |
| Kiểm tra dữ liệu form và báo lỗi field | Binding/validation tại view-state |
| Chuẩn bị dữ liệu mỗi khi vào view | `on-entry`/`on-render` action |
| Đo lifecycle của nhiều flow | FlowExecutionListener |
| Tạo trace/span hoặc metrics | Listener và công cụ observability |
| Chia sẻ một bước xác minh nhiều màn hình | Subflow với input/output rõ ràng |
| Quyết định cho phép tạo/đổi tài nguyên | Domain service + Spring Security |
| Xử lý exception không có outcome dự kiến | Exception handling phù hợp của flow/tầng web |
| Gửi sự kiện nghiệp vụ sau commit | Service/domain event/outbox |

### 16.1. Khi nào nên tạo listener tùy chỉnh?

Chỉ tạo listener riêng nếu có **một quan tâm cắt ngang nhiều flow** và lifecycle callback thật sự là điểm móc phù hợp. Nếu code chỉ áp dụng cho state `review` của một flow, action trong flow definition thường rõ ràng hơn và dễ review hơn.

Trước khi tạo listener, tự hỏi:

1. Nếu listener bị gỡ, nghiệp vụ có còn đúng không?
2. Listener có cần quyết định transition hoặc gọi service ghi không?
3. Callback có thể chạy nhiều lần hoặc không chạy sau một lỗi, liệu có vấn đề không?
4. Có thể test bằng listener stub/spy và integration test executor không?

Nếu câu 1 là **không**, hoặc câu 2 là **có**, logic đó có khả năng đang đặt sai lớp.

## 17. Kiểm thử tách bạch action và listener

Một bộ kiểm thử tốt chia làm ba lớp: **unit test action**, **flow test**, **integration test listener**.

### 17.1. Unit test action

~~~text
Given BookingService.reserveOnce(draft)
      returns SLOT_UNAVAILABLE
When BookingAction.reserve(context) executes
Then Event.id == "slotUnavailable"
And no completed booking is assumed
~~~

Test này chứng minh action chuyển kết quả service thành event đúng. Nó không cần một listener.

### 17.2. Flow test

~~~text
start booking -> chooseSlot
send next with valid slotId -> review
send confirm, mocked result SLOT_UNAVAILABLE -> chooseSlot
send next then confirm, mocked result CONFIRMED -> completed
~~~

Test này chứng minh **định nghĩa flow có transition** khớp với outcome của action. Nó cũng cần kiểm tra form binding/validation và event không hợp lệ.

### 17.3. Unit test listener

~~~text
Given FlowDiagnosticsListener
When eventSignaled(context, event("confirm"))
Then diagnostic event is recorded with flowId and eventId
And no BookingService.reserveOnce call occurs
And no flow state is manually changed
~~~

Đây là **pseudocode**, không phải API test Java có thể chạy nguyên văn. Với listener metrics, nên kiểm tra nhãn cardinality thấp, không ghi PII, thread safety và xử lý khi backend metrics lỗi.

### 17.4. Integration test gắn listener vào FlowExecutor

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Khởi động flow mới | Listener được đăng ký thực sự nhận callback start/session thích hợp |
| Chuyển `chooseSlot → review` | Callback về event/state/transition xuất hiện theo API |
| Gọi action trả `slotUnavailable` | Transition đúng, listener không thay đổi outcome |
| Dừng ở view-state rồi POST tiếp | Callback pause/resume phản ánh vòng đời thực tế |
| Action ném exception ngoài dự kiến | Lỗi được xử lý ở tầng phù hợp; listener không giả vờ thành công |
| Subflow `verifyPhone` | Không nhầm số session con với booking thành công |
| Submit hai lần hoặc từ snapshot cũ | Metrics có thể nhiều lần; database vẫn không có booking trùng |
| Lỗi hệ thống metrics | Flow vẫn phục vụ người dùng theo chính sách chịu lỗi |

### 17.5. Ghi lại thứ tự callback thay vì đoán

Trong integration test, có thể dùng một listener thử nghiệm ghi nhận tên callback vào collection thread-safe; sau đó xác minh:

- Những callback nào thực sự xảy ra khi start, resume, render và end.
- Action `reserve` chạy giữa các mốc tương ứng.
- Khi exception bị action bắt và chuyển thành event, callback lỗi có xuất hiện hay không.
- Khi subflow bắt đầu/kết thúc, callback session được phát bao nhiêu lần.

Tránh assert một thứ tự không được API bảo đảm; khi cần đảm bảo chính xác, dựa vào contract của phiên bản và các test tích hợp.

## 18. Chẩn đoán khi callback không được gọi

Nếu bạn thấy action chạy nhưng listener không nhận callback, hãy kiểm tra:

1. Bean listener có thực sự được tạo và nối vào FlowExecutor đang chạy không?
2. Có nhiều FlowExecutor khác nhau và request đi vào executor khác không?
3. Bộ lọc chọn flow của listener có loại flow hiện tại không?
4. Callback được override có đúng chữ ký của phiên bản Web Flow không?
5. Request có thực sự đến server hay Browser Back chỉ hiển thị cache?
6. Flow đã thực sự đến state/mốc đó chưa, hay validation chặn transition?
7. Exception có bị action bắt và biến thành event trước khi callback lỗi được kích hoạt không?
8. Với ứng dụng nhiều node, log/metrics có đang được đọc từ đúng node và có correlation hợp lệ không?

Nếu listener nhận callback nhưng flow vẫn không chuyển state, nên kiểm tra **event action trả về, transition trong XML, validation và exception**. Thêm log listener không tự sửa một flow definition sai.

## 19. Bài thực hành: tách nghiệp vụ ra khỏi listener

Một dự án đang triển khai flow `checkout`. Lập trình viên viết listener làm ba việc:

- Khi `stateEntered(review)`, gọi service tạo đơn.
- Khi `sessionEnded`, gửi email xác nhận.
- Khi `exceptionThrown`, tăng counter lỗi.

Kết quả là người dùng chỉ vào trang xem lại cũng có thể tạo đơn; đôi khi email bị gửi hai lần.

**Yêu cầu thiết kế lại:**

1. Vẽ flow `cart → review → submitOrder → completed`, với nhánh `outOfStock` quay về giỏ hàng và nhánh `statusUnknown` để đối soát.
2. Đưa thao tác tạo đơn sang **action-state** được kích hoạt bởi event `confirm`.
3. Thiết kế `OrderService.submitOnce(requestId, draft)` có idempotency key và unique constraint.
4. Dùng domain event/outbox phù hợp để gửi email sau khi transaction được xác nhận, không dựa vào callback `sessionEnded` làm nguồn duy nhất.
5. Giữ listener chỉ theo dõi state, event, thời gian và exception với nhãn an toàn.
6. Viết XML action/transition và đoạn Java listener tối thiểu.
7. Viết unit test action, flow test nhánh `outOfStock` và integration test gửi confirm lặp; kiểm tra cả số đơn hàng và số email thực tế.
8. Mô tả hành vi khi người dùng đóng tab trước khi flow kết thúc hoặc submit lại form từ snapshot cũ.

**Tiêu chí đánh giá:** Chỉ action/service nghiệp vụ được quyền ghi đơn; listener có thể được tắt mà booking/order vẫn đúng; mọi outcome có transition hợp lệ và khả năng phục hồi được kiểm thử.

## 20. Tổng kết và câu hỏi ôn tập

Trong Spring Web Flow, **action nằm trong flow definition** và được thực thi như một phần của hành trình, thường tạo kết quả hoặc event để engine chọn transition. **FlowExecutionListener** là điểm mở rộng theo dõi vòng đời execution/session, event, transition, state, render và exception. Hai cơ chế có thể cùng xuất hiện ở một thời điểm nhưng không đồng nghĩa.

Ưu tiên action cho **dữ liệu, quyết định và side effect nghiệp vụ**. Ưu tiên listener cho **quan sát cắt ngang** như tracing và metrics. Không biến callback thành transaction ngầm hoặc cơ chế retry bí mật. Những công việc ghi dữ liệu quan trọng vẫn cần service với kiểm tra quyền, idempotency và transaction; exception phục hồi cần được phân loại và xử lý theo đường đi rõ ràng.

**Câu hỏi tự kiểm tra:**

1. Vì sao `<on-entry>` và callback `stateEntered` có thể xảy ra gần nhau nhưng không thể dùng thay thế tùy tiện?
2. Callback `eventSignaled` có trả event `booked` để FlowExecutor tự đi tới `completed` được không?
3. Khi nào việc dùng listener cho metrics là thích hợp hơn việc thêm action vào tất cả view-state?
4. Vì sao không nên tạo đơn ở `stateEntered(review)`?
5. `sessionEnded` có bảo đảm email xác nhận được gửi đúng một lần không? Thiết kế nào đáng tin hơn?
6. Khi có subflow, vì sao đếm `sessionStarted` không nhất thiết bằng số booking?
7. Nếu trình duyệt hiển thị trang cũ từ bfcache, listener có chắc nhận callback mới không?
8. Cần những loại test nào để xác minh riêng action, transition, listener registration và idempotency?
