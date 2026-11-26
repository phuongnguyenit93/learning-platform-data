# Phiên hết hạn và trạng thái không còn trong repository

Một flow Spring Web Flow có thể đang hoạt động bình thường rồi đột nhiên không tiếp tục được: người dùng để tab mở quá lâu, quay lại từ bookmark, bấm Back sau khi flow đã kết thúc, hoặc gửi một URL execution cũ sau khi server đã dọn snapshot. Khi đó, **flow definition vẫn có thể tồn tại nhưng flow execution mà URL đang tham chiếu không còn trong repository**.

Bài thuộc chương **Lịch sử trình duyệt** của module `SPRING_WEB_FLOW`. Ta sẽ phân biệt HTTP session hết hạn, flow execution bị loại khỏi repository, snapshot lịch sử không còn, flow đã kết thúc và lỗi khôi phục snapshot. Bạn sẽ học cách nhận diện exception, hiểu cơ chế tự khởi động lại mặc định của Spring MVC integration, tùy chỉnh `FlowHandler` để đưa người dùng tới màn hình phục hồi, và bảo toàn kết quả nghiệp vụ khi request cuối cùng có thể đã commit.

Ví dụ dùng **Java 17, Spring Framework 6.x và Spring Web Flow 3.x**. Repository mặc định và tích hợp servlet có thể được tùy chỉnh; do đó các chi tiết về lưu trữ, session replication và exception cần được đối chiếu với cấu hình triển khai thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt flow definition, flow execution, execution key và history snapshot.
2. Giải thích quan hệ giữa HTTP session và flow execution trong repository mặc định.
3. Nhận biết các nguyên nhân khiến execution key không còn hợp lệ.
4. Phân biệt `NoSuchFlowExecutionException` với lỗi khôi phục snapshot.
5. Hiểu vì sao `FlowHandlerAdapter` có thể tự khởi động execution mới khi nhận key cũ.
6. Tùy chỉnh `FlowHandler.handleException` để xử lý execution hết hạn/kết thúc.
7. Giới hạn dữ liệu đầu vào khi flow được khởi động lại sau lỗi.
8. Tách lỗi của flow đang chạy khỏi lỗi không thể tìm thấy execution.
9. Thiết kế UX để người dùng tra cứu kết quả đã commit hoặc bắt đầu hành trình mới.
10. Kiểm thử session timeout, snapshot eviction, deploy/restart và request replay.

Kết quả cần đạt: khi một tab cũ gửi request, ứng dụng nhận biết trạng thái flow không còn khả dụng, hiển thị hướng xử lý đúng và không tạo giao dịch trùng do tự động chạy lại request.

## 2. Bốn thành phần cần phân biệt

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Flow definition** | Định nghĩa state, transition, action và outcome | `booking-flow.xml` |
| **Flow execution** | Một lần chạy cụ thể của flow definition | Người dùng đang đặt một phòng |
| **Flow execution key** | Khóa opaque dùng để tiếp tục execution/snapshot | URL chứa `execution=...` |
| **History snapshot** | Trạng thái được lưu để hỗ trợ tiếp tục/quay lại | Snapshot tại state review |

Flow definition thường được nạp từ FlowRegistry và có thể vẫn còn sau khi một execution kết thúc. Repository giữ các execution đang hoạt động và những snapshot cần thiết theo chính sách cấu hình. Vì vậy:

- Flow ID tồn tại không có nghĩa execution key cũ còn hợp lệ.
- Một execution có thể kết thúc trong khi flow definition vẫn được dùng cho người dùng khác.
- Một snapshot có thể bị loại bỏ dù session của người dùng vẫn còn.
- Một session có thể chứa nhiều flow execution, và chúng có thể hết hạn/được dọn ở thời điểm khác nhau.

### 2.1. URL start và URL continuation

Ví dụ minh họa:

~~~text
GET /booking
    -> FlowHandlerMapping tìm flow "booking"
    -> FlowExecutor tạo execution mới

POST /booking?execution=K
    -> FlowHandlerAdapter tiếp tục execution/snapshot K
~~~

URL bắt đầu flow không mang execution key. URL continuation do Web Flow sinh ra tham chiếu execution hiện có. Không tự phân tích, sửa hoặc tạo execution key bằng JavaScript.

### 2.2. Execution key không phải dữ liệu nghiệp vụ

Execution key chỉ giúp framework tìm trạng thái flow cần tiếp tục. Nó không phải:

- ID booking đã lưu.
- Bằng chứng người dùng có quyền đọc booking.
- Idempotency key của lệnh thanh toán.
- Mã định danh vĩnh viễn của một quy trình.

Nếu execution mất, dữ liệu nghiệp vụ đã commit vẫn phải tra cứu được qua database và endpoint có authorization riêng.

## 3. HTTP session và repository mặc định

Trong cấu hình mặc định, Web Flow quản lý execution qua flow execution repository gắn với conversation/session của người dùng. Các scope như conversation scope được lưu trong HTTP session; object lưu trong flow/view/conversation scope theo mặc định cần serializable để hỗ trợ lưu trữ/replication.

Điều này tạo ra quan hệ:

~~~mermaid
flowchart TD
    C["Trình duyệt"] -->|Cookie session| S["HTTP session"]
    S --> R["Flow execution repository"]
    R --> E1["Execution A"]
    R --> E2["Execution B"]
    E1 --> A1["Snapshots A"]
    E2 --> B1["Snapshots B"]
~~~

Một cookie session có thể tham chiếu nhiều execution. Duplicate tab, bookmark hoặc browser Back có thể gửi lại một continuation key; repository cần tìm được đúng execution và snapshot tương ứng.

### 3.1. Session hết hạn không giống flow kết thúc

| Tình huống | Điều gì mất? | Điều gì có thể còn? |
| --- | --- | --- |
| HTTP session hết hạn | Session-backed repository và execution trong session | Database, log, flow definition |
| Một execution bị loại khỏi repository | Execution cụ thể | Session và execution khác |
| Snapshot cũ bị dọn | Một điểm lịch sử của execution | Snapshot mới hơn, execution hiện tại |
| Flow chuyển tới end-state | Execution kết thúc theo lifecycle | Outcome và dữ liệu nghiệp vụ đã commit |
| Flow definition không tồn tại | Khả năng tạo execution mới cho flow ID đó | Execution khác không liên quan |

Đừng hiển thị cùng một thông báo cho tất cả trường hợp. Nếu flow definition không tồn tại, đó có thể là lỗi mapping/deploy. Nếu execution hết hạn, người dùng có thể bắt đầu lại. Nếu booking đã được tạo, họ cần xem kết quả đã lưu.

## 4. Các nguyên nhân phổ biến khiến execution không còn

### 4.1. HTTP session timeout

Người dùng mở form, để tab không hoạt động quá thời gian session timeout rồi mới gửi event. Session bị container hoặc session store invalidation; repository gắn với session không còn execution đó.

### 4.2. Giới hạn số execution trên mỗi session

Web Flow cho phép cấu hình `max-executions`. Đây là giới hạn số flow execution được tạo **trên mỗi user session**, áp dụng trên các flow definition. Khi vượt giới hạn, execution cũ nhất bị loại bỏ.

Ví dụ cấu hình XML:

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry">
    <webflow:flow-execution-repository
        max-executions="5"
        max-execution-snapshots="30"/>
</webflow:flow-executor>
~~~

Ở đây `5` và `30` là giá trị minh họa, không phải mặc định bắt buộc. Khi người dùng mở nhiều hành trình trong các tab, execution cũ có thể bị loại trước khi họ quay lại tab đó.

### 4.3. Giới hạn số history snapshot

`max-execution-snapshots` giới hạn số history snapshot được giữ cho **mỗi flow execution**:

- `0`: tắt snapshot history; browser Back không thể tiếp tục bằng snapshot chưa từng được ghi.
- Số dương: giới hạn số snapshot được giữ.
- `-1`: cho phép số snapshot không giới hạn theo cấu hình này.

Giữ snapshot nhiều hơn hỗ trợ backtracking nhưng tăng lượng trạng thái cần lưu. Nếu flowScope giữ object lớn, giới hạn quá cao có thể làm session phình to.

### 4.4. Flow đã kết thúc

Khi flow đi tới end-state, execution kết thúc và key continuation cũ không còn đại diện cho một flow đang chạy. Người dùng bấm Back hoặc gửi lại request từ tab cũ có thể truy cập một key đã kết thúc.

### 4.5. Ứng dụng restart hoặc deploy

Nếu execution repository/session store chỉ nằm trong bộ nhớ của một tiến trình, restart có thể làm mất trạng thái. Nếu dùng Spring Session hoặc session store phân tán, execution có thể còn sau restart, nhưng điều đó phụ thuộc persistence, serialization, TTL và compatibility của class sau deploy.

### 4.6. Snapshot không thể khôi phục

Repository có thể tìm thấy key nhưng không deserialize/restore được trạng thái. Nguyên nhân có thể là class flow variable thay đổi giữa hai bản deploy, object không tương thích serialization, dữ liệu snapshot hỏng hoặc lỗi persistence. Trường hợp này khác với key không tồn tại.

### 4.7. Request tới node không có trạng thái

Trong cluster, request tiếp theo có thể tới node khác. Nếu session/flow repository không được chia sẻ hoặc sticky session cấu hình sai, node mới không tìm được execution. Hãy kiểm tra session affinity, shared session store và cách triển khai repository trước khi tăng timeout.

## 5. Các exception quan trọng

Web Flow có nhóm exception cho việc truy cập repository:

| Exception | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `NoSuchFlowExecutionException` | Không tìm thấy execution theo persistent key được gửi lên | Xem như execution đã bị xóa, kết thúc hoặc không thuộc session hiện tại |
| `FlowExecutionRestorationFailureException` | Không thể khôi phục execution/snapshot | Ghi log root cause, đưa người dùng tới đường phục hồi |
| `FlowExecutionRepositoryException` | Lỗi tổng quát của repository | Kiểm tra persistence/store và exception cause |
| `PermissionDeniedFlowExecutionAccessException` | Repository từ chối truy cập execution | Không coi là timeout; kiểm tra quyền và context |
| `NoSuchFlowDefinitionException` | Không tìm được flow definition | Kiểm tra FlowRegistry, ID và deploy artifact |

### 5.1. NoSuchFlowExecutionException

Exception này được ném khi execution với persistent identifier được cung cấp không tìm thấy trong repository. Một nguyên nhân điển hình là execution đã bị remove nhưng client vẫn giữ URL/key cũ.

### 5.2. FlowExecutionRestorationFailureException

Exception này biểu thị repository không thể restore execution. Hãy xem exception cause để tìm lỗi serialization, class loading, session store hoặc dữ liệu snapshot. Không tự động tạo một execution mới rồi gửi lại event cũ như thể thao tác chưa xảy ra.

### 5.3. Phân biệt với lỗi nghiệp vụ trong flow đang chạy

Nếu flow execution vẫn tồn tại nhưng action `bookingService.confirm()` ném lỗi hết chỗ, đó là lỗi nghiệp vụ của execution đang hoạt động. Hãy bắt lỗi trong action/service, thêm message và trả event để flow chuyển sang state xử lý phù hợp.

Nếu repository không thể tìm hoặc restore execution, state handler bên trong flow có thể không có context hợp lệ để tiếp tục. Đây là lý do cần phân biệt xử lý **trong flow** và xử lý **ở servlet FlowHandler**.

## 6. Hành vi mặc định của FlowHandlerAdapter

Trong Spring MVC integration, `FlowHandlerAdapter` quyết định request sẽ bắt đầu execution mới hay tiếp tục execution hiện có dựa trên thông tin trong HTTP request.

Tài liệu Spring Web Flow 3.0.2 mô tả các hành vi mặc định:

- Request parameter được đưa vào input map khi bắt đầu flow execution mới.
- Nếu execution kết thúc mà chưa gửi response cuối cùng, handler mặc định có thể bắt đầu execution mới trong cùng request.
- Exception chưa được xử lý được chuyển lên `Dispatcher`, ngoại trừ `NoSuchFlowExecutionException`.
- Với `NoSuchFlowExecutionException`, handler mặc định cố gắng phục hồi bằng cách bắt đầu lại flow.
- Exception khác được ném lên Spring MVC `ExceptionResolver` nếu custom `FlowHandler` không xử lý.

### 6.1. Vì sao tự động restart có thể gây bất ngờ?

Giả sử người dùng đang ở bước thanh toán và gửi:

~~~text
POST /checkout?execution=old-key
_eventId_confirm=confirm
paymentMethod=CARD
~~~

Nếu key cũ không còn, adapter mặc định có thể bắt đầu execution mới. Request parameters được dùng làm input cho execution mới theo cơ chế mặc định. Nếu flow nhận input rộng hoặc action khởi tạo có side effect, người dùng có thể thấy hành trình bắt đầu lại ngoài ý muốn.

Vì vậy:

1. Không coi auto-restart là phục hồi dữ liệu đã nhập.
2. Không để `on-start` tạo giao dịch hoặc trừ tiền chỉ vì flow được khởi động lại.
3. Allow-list input của flow mới; không coi event parameter cũ là input hợp lệ.
4. Với thao tác commit, tra cứu kết quả theo idempotency key/business ID trước khi cho người dùng gửi lại.

### 6.2. Khi nào nên giữ hành vi mặc định?

Nếu flow là form tra cứu không có side effect, restart về bước đầu có thể là trải nghiệm phù hợp. Nếu flow tạo đơn hàng, thanh toán, cập nhật hồ sơ hoặc thao tác không thể lặp, nên tùy chỉnh `FlowHandler` để giải thích trạng thái và điều hướng tới trang phục hồi.

## 7. Tùy chỉnh FlowHandler để xử lý execution hết hạn

`FlowHandler` là extension point của Spring MVC integration. Nó có thể:

- Trả flow ID tương ứng với request.
- Tạo input map cho execution mới.
- Xử lý outcome khi flow kết thúc.
- Xử lý exception chưa được Web Flow xử lý.

Trong Spring Web Flow 3.x, có thể kế thừa `AbstractFlowHandler`. Bean handler phải được đăng ký với tên tương ứng flow ID mà nó xử lý.

### 7.1. Handler cho flow booking

~~~java
package com.example.booking.web;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.webflow.core.FlowException;
import org.springframework.webflow.execution.repository.NoSuchFlowExecutionException;
import org.springframework.webflow.mvc.servlet.AbstractFlowHandler;

@Component("booking")
public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleException(
            FlowException exception,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (exception instanceof NoSuchFlowExecutionException) {
            return "/booking/expired";
        }

        // Để exception khác đi tới cơ chế xử lý mặc định.
        return null;
    }
}
~~~

`booking` trong tên bean là flow ID; nếu flow ID của ứng dụng là `checkout/booking`, tên bean phải khớp ID đó. Đường dẫn trả về là resource mà Spring MVC có thể điều hướng tới; hãy tạo controller/view tương ứng.

### 7.2. Không xử lý mọi exception như expired

Không nên viết:

~~~java
@Override
public String handleException(
        FlowException exception,
        HttpServletRequest request,
        HttpServletResponse response) {
    return "/booking/expired";
}
~~~

Đoạn này biến lỗi lập trình, lỗi database, lỗi permission hoặc lỗi cấu hình thành thông báo session hết hạn. Chỉ xử lý exception mà handler thực sự hiểu; trả `null` để cơ chế phía sau xử lý các exception còn lại.

### 7.3. Tạo trang phục hồi

Controller/view có thể hiển thị một thông báo ngắn:

~~~java
@Controller
public class BookingRecoveryController {

    @GetMapping("/booking/expired")
    public String expired() {
        return "booking/expired";
    }
}
~~~

~~~html
<h1>Phiên thao tác đã hết hạn</h1>
<p>Hành trình đặt chỗ này không còn khả dụng.</p>
<p>Nếu bạn đã xác nhận, hãy kiểm tra danh sách đặt chỗ trước khi tạo yêu cầu mới.</p>
<a href="/booking">Bắt đầu lượt đặt chỗ mới</a>
~~~

Trang này không nên tự động chạy lại event confirm hoặc dùng lại request body cũ. Người dùng có thể tra cứu kết quả đã commit trước khi quyết định tạo flow mới.

## 8. Giới hạn input khi flow được bắt đầu lại

Theo mặc định, request parameters được đưa vào input map của execution mới. Trong ứng dụng có custom FlowHandler, có thể override `createExecutionInputMap` để chỉ lấy những tham số được cho phép.

Ví dụ chỉ cho phép `campaignCode` là input lúc bắt đầu:

~~~java
import org.springframework.webflow.core.collection.LocalAttributeMap;
import org.springframework.webflow.core.collection.MutableAttributeMap;

// Thêm method này vào BookingFlowHandler ở mục 7.1.
@Override
public MutableAttributeMap<Object> createExecutionInputMap(
        HttpServletRequest request) {
    MutableAttributeMap<Object> input = new LocalAttributeMap<>();

    String campaignCode = request.getParameter("campaignCode");
    if (campaignCode != null && campaignCode.matches("[A-Z0-9]{4,12}")) {
        input.put("campaignCode", campaignCode);
    }
    return input;
}
~~~

Đây là ví dụ allow-list. `campaignCode` vẫn phải được kiểm tra ở service nếu nó ảnh hưởng giá/quyền. Không đưa các tham số sau vào input map chỉ vì chúng có trong request cũ:

- `_eventId_confirm`
- `execution`
- `ownerId`
- `price`
- `approved`
- `paymentStatus`

Event parameter thuộc giao thức tiếp tục flow; nó không phải input nghiệp vụ hợp lệ cho flow mới. `execution` là continuation key; không chuyển nó thành biến flow.

## 9. Xử lý exception trong flow đang hoạt động

Khi execution còn hợp lệ và một action gặp lỗi, nên ưu tiên chuyển lỗi nghiệp vụ thành outcome event:

~~~java
public String confirmBooking(BookingDraft draft, RequestContext context) {
    try {
        BookingReceipt receipt = bookingService.confirm(draft);
        context.getFlowScope().put("receipt", receipt);
        return "success";
    } catch (NoAvailabilityException ex) {
        context.addMessage(new MessageBuilder()
            .error()
            .defaultText("Không còn chỗ trống. Hãy chọn thời gian khác.")
            .build());
        return "unavailable";
    }
}
~~~

Flow XML phản hồi:

~~~xml
<action-state id="confirmBooking">
    <evaluate expression="bookingActions.confirmBooking(draft, flowRequestContext)"/>
    <transition on="success" to="completed"/>
    <transition on="unavailable" to="review"/>
</action-state>
~~~

Đối với lỗi kỹ thuật ngoài dự kiến, để exception đi tới cơ chế xử lý lỗi tập trung và log đầy đủ. Không trả `unavailable` cho mọi lỗi vì điều đó che giấu lỗi database, network hoặc bug.

### 9.1. FlowExecutionExceptionHandler là một extension khác

Một state có thể khai báo `exception-handler` tham chiếu bean `FlowExecutionExceptionHandler` để xử lý exception trong **execution đang chạy**. Đây là cơ chế phức tạp: handler phải đưa execution về một state hợp lệ. Nếu xử lý sai, execution có thể trở nên không dùng được.

Tài liệu Web Flow khuyến nghị cân nhắc bắt business exception trong action và trả outcome event; nếu cần exception handler, xem implementation `TransitionExecutingFlowExecutionExceptionHandler` làm mẫu. Exception handler bên trong flow không thay thế `FlowHandler.handleException` khi repository không tìm được execution để khôi phục.

## 10. Bảo toàn kết quả nghiệp vụ khi flow mất

Flow execution là trạng thái điều hướng. Nó không nên là nơi duy nhất lưu bằng chứng rằng booking/thanh toán đã thành công.

Một kịch bản quan trọng:

1. Người dùng bấm Xác nhận.
2. Service commit booking vào database.
3. Server mất kết nối hoặc execution bị lỗi trước khi response đến trình duyệt.
4. Người dùng refresh hoặc mở tab cũ.
5. Flow key không còn hoặc client không biết kết quả commit.

Nếu ứng dụng chỉ dựa vào flowScope, người dùng có thể nghĩ booking chưa tạo và gửi lại. Hãy dùng idempotency:

~~~text
confirm(requestId)
  ├─ requestId đã có reservation -> trả receipt đã lưu
  └─ requestId chưa có
       ├─ kiểm tra quyền và điều kiện
       ├─ tạo reservation trong transaction
       └─ lưu unique(userId, requestId)
~~~

`requestId` được server tạo và gắn với bản nháp/giao dịch. Khi retry, service tra cứu theo user + requestId và trả kết quả cũ nếu đã commit.

### 10.1. Tách draft và committed record

| Dữ liệu | Lưu ở đâu? | Nếu flow hết hạn |
| --- | --- | --- |
| Từ khóa, bộ lọc tạm | Flow scope | Có thể nhập lại |
| Lựa chọn chưa xác nhận | Flow scope hoặc draft store có TTL | Có thể bắt đầu lại hoặc khôi phục theo chính sách |
| Booking đã commit | Database | Vẫn tra cứu được |
| Payment transaction ID | Database/payment provider | Dùng để đối soát |
| Confirmation receipt | Database | Có thể hiển thị lại sau khi flow kết thúc |

Không đặt payment secret hoặc credential trong flowScope. Nếu cần lưu draft bền vững, gắn owner, expiry và authorization rõ ràng; không biến snapshot thành kho lưu trữ vô thời hạn.

## 11. Session replication, serialization và deploy

Nếu chạy nhiều node hoặc dùng session replication, object được lưu trong flow/conversation scope cần tương thích với cơ chế lưu trữ. Với default implementation, Web Flow yêu cầu các object lưu ngoài request scope thường serializable.

### 11.1. Những lỗi thường gặp khi serialize

- Flow variable chứa object không triển khai `Serializable`.
- Object graph giữ reference tới stream, socket, request/response hoặc bean không serializable.
- Thay đổi class giữa hai bản deploy khiến snapshot cũ không thể deserialize.
- Session store có TTL ngắn hơn thời gian người dùng để tab mở.
- Node nhận request không đọc được session của node đã tạo execution.

### 11.2. Không lưu Spring singleton vào flow scope

Flow scope nên chứa dữ liệu của một execution như draft, criteria hoặc DTO. Service Spring là singleton/shared bean; không copy service vào flow scope. Hãy giữ reference service ở application context và chỉ lưu dữ liệu serializable cần cho flow.

### 11.3. Chính sách deploy

Khi deploy phiên bản mới:

1. Quyết định có cho phép session/execution cũ tiếp tục qua deploy không.
2. Nếu repository không hỗ trợ tương thích snapshot, chủ động kết thúc session hoặc hiển thị trang yêu cầu bắt đầu lại.
3. Giữ dữ liệu nghiệp vụ đã commit trong database.
4. Không cố deserialize snapshot cũ bằng cách đổi class tùy tiện.
5. Theo dõi tỷ lệ `NoSuchFlowExecutionException` và restoration failure sau deploy.

## 12. Thời gian sống của session và execution

Thời gian sống có thể chịu ảnh hưởng từ nhiều lớp:

| Lớp | Điều khiển bởi | Tác động |
| --- | --- | --- |
| HTTP session | Servlet container hoặc Spring Session TTL | Có thể làm mất session-backed execution |
| Flow execution count | `max-executions` | Execution cũ nhất bị loại khi vượt giới hạn |
| Snapshot history | `max-execution-snapshots` | History cũ không còn để browser Back |
| Session store | Redis/JDBC/cache TTL và eviction policy | Trạng thái có thể bị xóa trước dự kiến |
| Business draft | TTL riêng trong database/cache | Draft nghiệp vụ hết hạn theo policy |

Không chỉ tăng HTTP session timeout để giải quyết mọi lỗi. Nếu người dùng mở hàng chục tab, `max-executions` có thể loại execution dù session chưa hết hạn. Nếu snapshot limit quá thấp, browser Back có thể thất bại dù execution hiện tại còn.

### 12.1. Cấu hình XML

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry">
    <webflow:flow-execution-repository
        max-executions="8"
        max-execution-snapshots="40"/>
</webflow:flow-executor>
~~~

### 12.2. Cấu hình Java

~~~java
@Bean
public FlowExecutor flowExecutor() {
    return getFlowExecutorBuilder(flowRegistry())
        .setMaxFlowExecutions(8)
        .setMaxFlowExecutionSnapshots(40)
        .build();
}
~~~

Giá trị phải được chọn dựa trên số tab/hành trình trung bình, kích thước object trong scope, session store và yêu cầu browser history. Đo kích thước session và số execution thực tế trước khi tăng giới hạn lớn.

## 13. Logging và giám sát

Khi người dùng báo “form tự quay về đầu”, cần xác định đó là session timeout, execution eviction hay lỗi restore. Nên ghi log có cấu trúc gồm:

- Flow ID.
- Kết quả xử lý: started, resumed, ended, missing, restoration-failed.
- Node/instance ID.
- Session correlation ID đã mask hoặc hash theo policy.
- Loại exception và root cause.
- Thời gian từ lúc execution được tạo nếu có metric.
- Business request ID đã mask nếu cần đối soát.

Không log nguyên session cookie, CSRF token, access token, thông tin thanh toán hoặc dữ liệu cá nhân không cần thiết. Execution key có thể xuất hiện trong URL và log; hãy quyết định rõ cách mask/ghi nhận nó.

### 13.1. Metric hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| `flow.execution.started` | Số execution mới |
| `flow.execution.ended` | Số execution kết thúc bình thường |
| `flow.execution.missing` | Request dùng key không còn trong repository |
| `flow.execution.restore.failed` | Snapshot tồn tại nhưng không khôi phục được |
| `flow.execution.evicted` | Execution bị loại do giới hạn |
| `flow.session.expired` | Session hết hạn |
| `flow.recovery.redirected` | Người dùng được đưa tới trang phục hồi |

Đếm riêng các nhóm này giúp phát hiện tăng đột biến sau deploy, thay đổi timeout hoặc lỗi session store.

Các tên metric trong bảng là **gợi ý instrumentation do ứng dụng định nghĩa**, không phải cam kết rằng Spring Web Flow tự phát hành sẵn các metric có tên đó. Có thể ghi chúng bằng Micrometer hoặc hệ thống telemetry hiện có.

## 14. Ma trận chẩn đoán

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Tab mở lâu rồi submit bị reset | Session TTL và exception type | Trang hết hạn, tra cứu kết quả trước khi tạo mới |
| Mở nhiều tab rồi tab cũ không dùng được | `max-executions` | Điều chỉnh giới hạn hoặc UX nhiều hành trình |
| Browser Back không hoạt động | `max-execution-snapshots` | Kiểm tra snapshot policy |
| Sau deploy tab cũ báo lỗi | Serialization/class compatibility | Quy trình deploy và session policy |
| Chỉ một node báo missing execution | Sticky session/shared store | Sửa cluster/session routing |
| Booking đã tạo nhưng flow báo lỗi | Transaction và idempotency key | Tra cứu receipt đã commit |
| Flow ID không tìm thấy | FlowRegistry và mapping | Sửa flow deployment/mapping; không báo session timeout |
| Access denied khi mở key cũ | Session/principal/permission | Kiểm tra authorization, không restart tự động |
| Restoration failure | Root cause serialization/store | Ghi log, phục hồi bằng start URL hoặc business resource |
| User quay lại end-state cũ | Execution đã kết thúc | Redirect tới trang kết quả hoặc bắt đầu flow mới |

### 14.1. Quy trình xử lý một báo cáo lỗi

1. Lấy timestamp, flow ID và correlation ID của request.
2. Xác định request là start URL hay continuation URL.
3. Đọc exception class và root cause.
4. Kiểm tra session còn tồn tại không.
5. Kiểm tra execution count và snapshot limit.
6. Kiểm tra node xử lý request và session store.
7. Kiểm tra booking/payment đã commit chưa.
8. Chỉ sau đó quyết định restart, tra cứu receipt hoặc hiển thị lỗi kỹ thuật.

## 15. Kiểm thử session hết hạn và repository missing

Không chỉ test bằng cách xóa cookie. Cần tách test session timeout, execution eviction, snapshot eviction, flow ended và restore failure.

### 15.1. Các kịch bản thủ công

1. Mở flow bằng start URL và đi tới màn hình review.
2. Lưu URL continuation hiện tại trong test environment.
3. Invalidate HTTP session rồi gửi request cũ.
4. Tạo nhiều execution để vượt `max-executions`, sau đó gửi lại key của execution cũ.
5. Giới hạn snapshot thấp, đi qua nhiều state và thử browser Back.
6. Kết thúc flow rồi gửi lại URL cũ.
7. Mô phỏng repository restore failure bằng test double hoặc snapshot không tương thích trong môi trường kiểm thử.
8. Deploy/restart trong môi trường staging có session store giống production.
9. Kiểm tra custom FlowHandler đưa request missing execution tới trang phục hồi.
10. Xác nhận booking đã commit vẫn tra cứu được và retry không tạo booking thứ hai.

### 15.2. Ma trận test

| ID | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| EX01 | Mở start URL | Execution mới được tạo |
| EX02 | Tiếp tục key còn hiệu lực | Execution resume đúng state |
| EX03 | Invalidate session | Key cũ không còn được tìm thấy |
| EX04 | Vượt `max-executions` | Execution cũ nhất bị loại theo policy |
| EX05 | Vượt snapshot limit | Snapshot lịch sử không còn; state hiện tại vẫn được kiểm tra riêng |
| EX06 | `max-execution-snapshots=0` | Browser Back không dựa vào snapshot |
| EX07 | Gửi key sau end-state | Flow không tiếp tục như execution đang chạy |
| EX08 | Repository không có key | `NoSuchFlowExecutionException` được xử lý |
| EX09 | Snapshot không restore được | Restoration failure được phân loại riêng |
| EX10 | Flow definition không tồn tại | Báo lỗi registry/mapping, không báo session timeout |
| EX11 | Custom FlowHandler nhận missing key | Redirect tới trang recovery |
| EX12 | Exception không phải missing execution | Được chuyển tiếp tới exception resolver |
| EX13 | Request cũ có `_eventId_confirm` | Không bị dùng làm input của execution mới |
| EX14 | Booking commit trước khi response mất | Tra cứu receipt theo request ID |
| EX15 | Retry cùng idempotency key | Không tạo booking thứ hai |
| EX16 | Session store shared trong cluster | Node khác resume được execution |
| EX17 | Session store không shared | Missing execution được ghi nhận và xử lý |
| EX18 | FlowScope chứa object không serializable | Test phát hiện lỗi persistence/replication |
| EX19 | Deploy thay đổi class flow variable | Chính sách snapshot cũ được thực thi |
| EX20 | Anonymous/đổi tài khoản gửi key cũ | Authorization theo principal hiện tại |

### 15.3. Kiểm tra kết quả ở database

Với flow có side effect, test không chỉ assert HTTP status hoặc trang hiển thị. Hãy xác minh:

- Có tối đa một booking cho một idempotency key.
- Retry trả lại cùng receipt/business ID.
- Không tạo booking khi flow chỉ được restart để phục hồi giao diện.
- Request từ user khác không đọc được booking.
- Một transaction thất bại không để lại trạng thái ghi dở.

## 16. Bài tập thực hành

### Bài A — tái hiện session timeout

Tạo flow booking hai bước, mở màn hình review rồi invalidate session trong test. Gửi continuation URL cũ và ghi lại exception. Thêm custom FlowHandler để đưa người dùng tới trang hết hạn.

**Đạt khi:** phân biệt được missing execution với flow definition không tồn tại.

### Bài B — giới hạn execution

Đặt `max-executions` nhỏ trong môi trường test. Mở nhiều flow execution trong cùng session, sau đó gửi key của execution cũ nhất.

**Đạt khi:** giải thích được vì sao session còn nhưng một execution đã bị loại.

### Bài C — giới hạn snapshot

Đặt `max-execution-snapshots` bằng một giá trị nhỏ, thực hiện nhiều transition rồi thử browser Back. Thử thêm giá trị 0 và quan sát hành vi.

**Đạt khi:** phân biệt snapshot history bị dọn với execution hiện tại bị mất.

### Bài D — custom recovery handler

Override `handleException` chỉ cho `NoSuchFlowExecutionException`, trả về trang `/booking/expired`, và để các exception khác trả `null`.

**Đạt khi:** lỗi missing key có UX rõ, còn lỗi kỹ thuật không bị che thành timeout.

### Bài E — allow-list flow input

Override `createExecutionInputMap`, chỉ nhận `campaignCode`. Gửi request cũ có `_eventId_confirm`, `price` và `ownerId`; xác minh chúng không trở thành input của flow mới.

**Đạt khi:** flow mới chỉ nhận dữ liệu được cho phép và service vẫn kiểm tra lại.

### Bài F — bảo vệ commit khỏi retry

Tạo request ID phía server, unique constraint theo user/request ID, và service trả receipt cũ khi request được gửi lại. Mô phỏng response bị mất sau commit rồi gửi lại request.

**Đạt khi:** chỉ một booking được tạo và người dùng có thể xem lại kết quả.

## 17. Checklist triển khai

- [ ] Đã phân biệt flow definition, execution, key và snapshot.
- [ ] Đã xác định repository thực tế và nơi lưu session/execution.
- [ ] Đã cấu hình `max-executions` theo số tab và kích thước session.
- [ ] Đã cấu hình `max-execution-snapshots` theo yêu cầu browser history.
- [ ] Đã hiểu tác động của session timeout và store TTL.
- [ ] Đã kiểm thử execution bị evict và flow đã kết thúc.
- [ ] Đã phân biệt `NoSuchFlowExecutionException` với restoration failure.
- [ ] Đã xác minh hành vi restart mặc định của FlowHandlerAdapter.
- [ ] Custom FlowHandler chỉ xử lý exception mà nó hiểu.
- [ ] Request input khi restart được allow-list.
- [ ] Event parameter cũ không trở thành input nghiệp vụ.
- [ ] Flow/action không tạo side effect trong on-start khi restart ngoài ý muốn.
- [ ] Booking/payment đã commit có thể tra cứu độc lập với flow.
- [ ] Service có idempotency cho thao tác có thể retry.
- [ ] Object trong flow/conversation scope phù hợp serialization.
- [ ] Session replication/sticky session được kiểm thử trên cluster.
- [ ] Có log/metric cho missing, restore failure, eviction và session expiry.
- [ ] Có test trên đúng repository và session store của môi trường triển khai.

## 18. Câu hỏi tự kiểm tra

**1. Flow definition còn tồn tại có nghĩa execution key cũ còn dùng được không?** Không. Definition và execution là hai tài nguyên khác nhau.

**2. Session hết hạn khác execution bị evict thế nào?** Session hết hạn có thể làm mất nhiều execution trong session; eviction chỉ loại một execution khi vượt giới hạn.

**3. `max-executions` áp dụng theo phạm vi nào?** Theo user session, trên các flow definition.

**4. `max-execution-snapshots=0` có ý nghĩa gì?** Tắt snapshot history; browser Back không thể khôi phục snapshot chưa được ghi.

**5. `NoSuchFlowExecutionException` nói lên điều gì?** Repository không tìm thấy execution theo key được gửi lên.

**6. Restoration failure khác missing execution ra sao?** Key có thể được nhận diện nhưng repository không thể khôi phục trạng thái snapshot.

**7. FlowHandlerAdapter mặc định làm gì với NoSuchFlowExecutionException?** Cố gắng khởi động lại flow; custom FlowHandler có thể thay đổi hành vi.

**8. Vì sao phải allow-list input khi restart?** Request parameters của request bắt đầu flow mới có thể được đưa vào input map theo mặc định.

**9. Có nên xử lý session timeout bằng FlowExecutionExceptionHandler trong state không?** Không phù hợp khi repository không thể restore execution; dùng FlowHandler ở servlet boundary.

**10. Nếu booking có thể đã commit nhưng flow mất thì sao?** Tra cứu theo business ID/idempotency key trước khi cho phép gửi lệnh mới.

## 19. Tài liệu tham khảo

1. [Spring Web Flow 3.0.2 Reference — Tuning Flow Execution Persistence](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — `max-executions`, `max-execution-snapshots` và browser history.
2. [Spring Web Flow 3.0.2 Reference — Flow-handling Workflow](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — cách FlowHandlerAdapter bắt đầu/tiếp tục execution và xử lý `NoSuchFlowExecutionException`.
3. [Spring Web Flow 3.0.2 Reference — Implementing Custom Flow Handlers](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — `FlowHandler.handleException`, outcome và input map.
4. [NoSuchFlowExecutionException Javadoc 3.0.1](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/execution/repository/NoSuchFlowExecutionException.html) — execution không tìm thấy trong repository.
5. [FlowExecutionAccessException Javadoc 3.0.1](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/execution/repository/FlowExecutionAccessException.html) — nhóm exception khi execution không thể truy cập.
6. [FlowExecutionExceptionHandler Javadoc](https://docs.spring.io/spring-webflow/docs/3.0.0/api/org/springframework/webflow/engine/FlowExecutionExceptionHandler.html) — handler cho exception trong execution đang hoạt động và các lưu ý về trạng thái nhất quán.

**Điểm cần nhớ:** URL continuation chỉ dùng được khi repository còn execution/snapshot tương ứng. Session timeout, giới hạn execution, giới hạn snapshot, flow đã kết thúc hoặc lỗi restore đều có thể làm tab cũ mất khả năng tiếp tục. Spring MVC mặc định có thể khởi động flow mới khi gặp `NoSuchFlowExecutionException`; hãy tùy chỉnh `FlowHandler` khi cần UX phục hồi rõ ràng, allow-list input và bảo vệ nghiệp vụ bằng idempotency để không chạy lại giao dịch đã commit.
