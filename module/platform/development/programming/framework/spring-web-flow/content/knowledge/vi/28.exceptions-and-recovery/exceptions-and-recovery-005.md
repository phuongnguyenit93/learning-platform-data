# FlowExecutionException và ngữ cảnh flow, state gây lỗi

> **Chương:** Ngoại lệ và phục hồi  
> **Mục tiêu:** Hiểu vai trò của FlowExecutionException trong Spring Web Flow; đọc ngữ cảnh flow và state gắn với sự cố; lần theo nguyên nhân gốc qua cause chain; thiết kế logging, exception handling và đường phục hồi phù hợp mà không nhầm lỗi kỹ thuật với kết quả nghiệp vụ.

## 1. Vì sao cần biết lỗi xảy ra trong flow và state nào?

Một hành trình đặt lịch có các bước:

~~~text
chooseSlot → contact → review → reserve → completed
~~~

Người dùng báo rằng khi nhấn **Xác nhận**, màn hình chỉ hiển thị lỗi chung. Trong log có một NullPointerException, nhưng nhóm vận hành chưa biết:

- Lỗi xảy ra trong flow đặt lịch hay một subflow xác minh liên hệ?
- Execution đang ở state review, reserve hay một state khác?
- Lỗi xuất hiện khi binding form, đánh giá expression, chạy action hay render view?
- NullPointerException là nguyên nhân gốc hay chỉ là một lớp bọc bên ngoài?
- Có transaction nào đã commit trước khi response lỗi xuất hiện không?

Trong ứng dụng MVC thông thường, stack trace có thể chỉ cho thấy controller/service. Với Spring Web Flow, một request còn tiếp tục **flow execution** đang được lưu hoặc khôi phục qua nhiều HTTP request. Vì vậy, chẩn đoán cần thêm ngữ cảnh của máy trạng thái.

FlowExecutionException là loại exception của Spring Web Flow dùng để biểu diễn lỗi phát sinh trong quá trình thực thi flow và mang theo thông tin nhận diện flow/state liên quan. Nó giúp nhóm phát triển biết **execution nào và vị trí điều khiển nào** có liên quan đến lỗi.

Điều này quan trọng vì cùng một service có thể được gọi từ nhiều flow và nhiều state. Biết flow/state giúp khoanh vùng nhanh hơn, nhưng vẫn cần xem **cause chain** để tìm lỗi thực sự.

## 2. FlowExecutionException là gì?

Trong API Spring Web Flow, lớp exception thường được dùng là:

~~~java
org.springframework.webflow.execution.FlowExecutionException
~~~

Đây là exception ở tầng thực thi flow. Nó có thể mang thông tin như:

| Thông tin | Ý nghĩa |
| --- | --- |
| flowId | ID của flow definition có liên quan |
| stateId | ID state tại ngữ cảnh lỗi được ghi nhận |
| message | Mô tả exception ở tầng flow |
| cause | Exception cấp thấp hơn gây ra hoặc dẫn đến lỗi |

Các accessor thường dùng trong API là getFlowId() và getStateId(). Hãy đối chiếu chữ ký chính xác với phiên bản Spring Web Flow đang dùng khi triển khai code.

**FlowExecutionException không nhất thiết là nguyên nhân gốc.** Nó thường là lớp bọc cung cấp ngữ cảnh Web Flow cho lỗi bên dưới. Ví dụ:

~~~text
FlowExecutionException
  flowId = appointment
  stateId = reserve
  cause:
    ExpressionEvaluationException
      cause:
        DataAccessException
          cause:
            SQLTransientConnectionException
~~~

Trong ví dụ, flow/state cho biết vị trí lỗi được phát hiện; chuỗi cause cho thấy lỗi cuối cùng liên quan đến kết nối database.

### 2.1. Flow ID và state ID giúp khoanh vùng, không giải thích toàn bộ nguyên nhân

Nếu flowId=appointment và stateId=reserve, có thể bắt đầu kiểm tra:

- Action được gọi tại state reserve.
- Expression gọi bean và method tương ứng.
- Dependency được inject vào action/service.
- Transaction hoặc truy vấn chạy ở bước đặt lịch.
- Các transition nhận outcome từ action.

Nhưng không nên kết luận ngay rằng XML state reserve sai. Nguyên nhân có thể là cấu hình database, dữ liệu đầu vào, quyền truy cập hoặc lỗi trong service.

### 2.2. State ID có thể không có trong một số tình huống

Một lỗi có thể xuất hiện khi flow đang được khởi tạo, trước khi state hoạt động ổn định, hoặc trong một tình huống khôi phục execution. Vì vậy, code chẩn đoán cần xử lý trường hợp metadata state không có/không xác định nếu API trả về giá trị rỗng.

Không tự suy ra state từ URL, tên view hoặc event cuối cùng mà trình duyệt gửi. Chỉ ghi nhận ngữ cảnh thực sự được framework cung cấp.

## 3. Phân biệt exception ở tầng flow với exception gốc

Một request có thể đi qua nhiều lớp:

~~~mermaid
flowchart TD
    A["HTTP request + execution key"] --> B["FlowExecutor"]
    B --> C["FlowExecution: current state"]
    C --> D["Expression / action / binding / transition"]
    D --> E["Spring bean"]
    E --> F["Domain service"]
    F --> G[("Database / remote service")]
    G -->|"Exception"| H["Cause chain"]
    H --> I["FlowExecutionException<br/>flowId + stateId + cause"]
    I --> J["Exception handling / logging"]
    J --> K["HTTP response an toàn"]
~~~

Các lớp có trách nhiệm khác nhau:

- **Domain/service exception:** mô tả lỗi ở tầng nghiệp vụ hoặc hạ tầng.
- **Expression/binding exception:** cho biết lỗi khi Web Flow đánh giá expression hoặc bind dữ liệu.
- **FlowExecutionException:** thêm ngữ cảnh flow/state cho lỗi trong execution.
- **HTTP exception handling:** quyết định phản hồi phù hợp cho trình duyệt/API.

Không nên xóa thông tin ở các tầng này bằng cách bắt mọi exception rồi ném một RuntimeException("Flow failed") không có cause.

### 3.1. Ví dụ cause chain khi gọi Spring bean

Flow có action:

~~~xml
<action-state id="reserve">
    <evaluate expression="appointmentAction.reserve(requestContext)"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

Trong method reserve, service gọi repository. Nếu database mất kết nối, lỗi có thể được bọc qua proxy transaction, repository, expression evaluator và execution boundary.

Khi đọc log, hãy xem cả:

1. flowId và stateId của FlowExecutionException.
2. Loại exception của lớp bọc trực tiếp.
3. Các cause lồng bên trong.
4. Stack frame đầu tiên thuộc code ứng dụng.
5. Transaction/side effect đã xảy ra đến đâu trước khi lỗi được phát hiện.

Một DataAccessException có thể bọc lỗi JDBC; một ExpressionEvaluationException có thể bọc lỗi gọi method. **Không phải cứ thấy exception ngoài cùng là biết cách phục hồi.**

## 4. Những vị trí trong flow có thể gây lỗi

Exception không chỉ phát sinh trong action-state. Một flow có thể lỗi ở nhiều giai đoạn:

| Vị trí | Ví dụ | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| Khởi tạo flow | Bean tạo bản nháp ném lỗi | on-start, bean factory, dependency |
| Vào state | Action on-entry lỗi | Expression, dữ liệu scope, service |
| Render view | Lỗi template hoặc message resolution | View resolver, model, resource bundle |
| Binding/conversion | Chuỗi không chuyển thành kiểu đích | Binder, converter, request parameter |
| Validation | Validator hoặc dependency của validator lỗi | Validator registration, quy tắc, message context |
| Transition | Action trên transition lỗi | Event, expression, source/target state |
| Action-state | Service ném exception | Outcome, transaction, repository |
| Decision-state | Điều kiện expression lỗi | Bean policy, null, kiểu trả về |
| Subflow | Flow con không khởi tạo hoặc lỗi khi chạy | Flow ID, input/output, state của flow con |
| Resume execution | Execution key/snapshot không thể khôi phục | Repository, session, key và cấu hình lưu trữ |
| Kết thúc flow | Action dọn dẹp hoặc kết thúc gặp lỗi | on-end, tài nguyên và side effect |

Ngữ cảnh stateId giúp tìm điểm cần xem, nhưng cần phân biệt **state đang hoạt động** với **view cuối cùng người dùng nhìn thấy**. Người dùng có thể vẫn đang nhìn trang review trong browser trong khi request tiếp theo đã đi vào action-state reserve và lỗi ở đó.

## 5. Đọc FlowExecutionException trong logging

Một cách ghi log hữu ích là ghi flow/state và giữ exception đầy đủ để hệ thống log có stack trace:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.webflow.execution.FlowExecutionException;

public final class FlowExceptionLogger {

    private static final Logger log =
            LoggerFactory.getLogger(FlowExceptionLogger.class);

    public void record(FlowExecutionException exception) {
        log.error(
                "Web Flow execution failed: flowId={}, stateId={}",
                exception.getFlowId(),
                exception.getStateId(),
                exception);
    }
}
~~~

Đây là ví dụ minh họa cho một thành phần logging được gọi từ exception-handling boundary phù hợp. Nó **không có nghĩa** phải tự bắt exception trong mọi action hoặc mọi controller. Việc tích hợp handler phải theo API và cấu hình Web Flow/MVC của phiên bản ứng dụng.

### 5.1. Giữ cause chain khi bọc exception

Nếu lớp ứng dụng cần thêm thông tin nhưng vẫn phải bọc lỗi:

~~~java
try {
    repository.reserve(slotId);
} catch (DataAccessException ex) {
    throw new ReservationPersistenceException(
            "Unable to persist reservation", ex);
}
~~~

Constructor nhận cause giúp giữ nguyên nguyên nhân bên dưới. Tuy nhiên, chỉ bọc khi có lý do ở ranh giới abstraction; không bọc lặp lại nhiều lớp với cùng thông tin.

**Không làm như sau:**

~~~java
catch (Exception ex) {
    throw new RuntimeException("Something went wrong");
}
~~~

Vì code này làm mất cause chain và phân loại lỗi. Nếu phải chuyển loại exception, hãy giữ cause và cung cấp ngữ nghĩa rõ ràng.

### 5.2. Không log rồi nuốt exception

~~~java
try {
    appointmentService.reserve(draft);
} catch (Exception ex) {
    log.error("Reserve failed", ex);
    return null; // Sai: execution không nhận được outcome hợp lệ.
}
~~~

Trả null có thể khiến lỗi tiếp theo khó hiểu hơn. Action nên:

- Trả outcome/event nếu service xác định được kết quả nghiệp vụ.
- Ném exception chuyên biệt nếu caller cần xử lý một lỗi có phân loại.
- Để exception ngoài dự kiến đi tới exception handler phù hợp.

Không che một lỗi kỹ thuật thành một kết quả thành công hoặc một event nghiệp vụ không liên quan.

## 6. FlowExecutionException và cause chain trong thực tế

Hãy xem bốn tình huống:

### 6.1. Lỗi expression do bean không tồn tại

Flow XML:

~~~xml
<action-state id="reserve">
    <evaluate expression="appointmentAction.reserve(requestContext)"/>
    <transition on="booked" to="completed"/>
</action-state>
~~~

Nếu bean appointmentAction không được đăng ký hoặc không nhìn thấy trong context mà Web Flow dùng, expression có thể thất bại khi state được thực thi.

**Cách chẩn đoán:**

1. Đọc flowId và stateId.
2. Kiểm tra tên bean và ApplicationContext.
3. Xem exception về expression resolution trong cause chain.
4. Kiểm tra wiring/flow executor thực tế.

Đây là lỗi cấu hình/triển khai, không phải lỗi người dùng cần thử lại.

### 6.2. Lỗi null trong model

Ví dụ expression:

~~~xml
<evaluate expression="appointmentPolicy.canReview(flowScope.draft.contact.email)"/>
~~~

Nếu draft hoặc contact là null, expression có thể lỗi khi truy cập property.

**Cách xử lý:**

- Khởi tạo model ở mốc thích hợp.
- Kiểm tra binding và validation trước khi đọc property sâu.
- Dùng method policy có thể xử lý trạng thái thiếu dữ liệu rõ ràng nếu đó là một điều kiện hợp lệ.
- Không chỉ thêm try/catch để biến mọi null thành false mà không hiểu nguyên nhân.

### 6.3. Lỗi database trong action-state

Nếu appointmentService.reserveOnce(...) gặp lỗi kết nối database, FlowExecutionException có thể cung cấp flowId=appointment và stateId=reserve, trong khi cause chain cho biết lỗi truy cập dữ liệu.

Trước khi hiển thị nút **Thử lại**, cần xác định:

- Lỗi xảy ra trước khi gửi lệnh ghi hay sau khi gửi?
- Transaction đã commit chưa?
- Kết quả có thể đã được ghi nhưng response bị mất không?
- Có request ID/idempotency key để tra cứu không?

Timeout không chứng minh thao tác ghi thất bại. Không nên tự động retry một lệnh ghi chưa biết kết quả.

### 6.4. Lỗi ở subflow

Flow cha:

~~~xml
<subflow-state id="verifyContact" subflow="verifyContact">
    <input name="email" value="flowScope.draft.email"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="contact"/>
</subflow-state>
~~~

Nếu flow con verifyContact lỗi, ngữ cảnh flow/state liên quan có thể thuộc **flow con** chứ không phải state view cuối cùng của flow cha. Hãy dùng ID thực tế trong exception và trace; đừng tự thay nó bằng tên flow cha khi log.

Nếu cần hiển thị thông báo thân thiện ở flow cha, hãy xử lý outcome/exception qua ranh giới subflow có chủ đích. Không giả định lỗi bên trong flow con sẽ tự chuyển thành event cancelled.

## 7. Phân loại lỗi trước khi chọn cách phục hồi

Không phải mọi FlowExecutionException đều cần hiển thị cùng một trang lỗi. Hãy phân loại theo nguyên nhân và mức độ chắc chắn của trạng thái nghiệp vụ.

| Nhóm | Ví dụ | Phản hồi phù hợp |
| --- | --- | --- |
| Binding/validation | Email sai, số lượng không hợp lệ | Giữ view-state và báo lỗi field |
| Kết quả nghiệp vụ dự kiến | Slot đã được đặt | Action trả event slotUnavailable |
| Authentication/authorization | Session hết hạn, thiếu quyền | Luồng login/access denied theo Spring Security |
| Lỗi cấu hình/lập trình | Bean không tồn tại, NullPointerException | Error handling chung, log/trace |
| Lỗi hạ tầng trước side effect | Không tải được danh sách slot | Có thể cho thử lại có giới hạn |
| Kết quả ghi chưa xác định | Timeout sau khi gửi lệnh đặt lịch | Tra cứu trạng thái, không retry mù |
| Execution không thể khôi phục | Snapshot/key không còn hợp lệ | Hướng dẫn bắt đầu lại hoặc hỗ trợ |

**FlowExecutionException là ngữ cảnh thực thi, không phải taxonomy nghiệp vụ.** Không dùng tên lớp này để quyết định rằng mọi lỗi đều là lỗi máy chủ giống nhau.

### 7.1. Lỗi dự kiến nên được mô hình hóa thành outcome

Nếu slot hết chỗ là tình huống bình thường trong quy trình, service có thể trả kết quả có kiểu:

~~~java
public enum ReservationStatus {
    BOOKED,
    SLOT_UNAVAILABLE,
    OUTCOME_UNKNOWN
}
~~~

Action chuyển outcome thành event:

~~~java
switch (result.getStatus()) {
    case BOOKED:
        return new Event(this, "booked");
    case SLOT_UNAVAILABLE:
        return new Event(this, "slotUnavailable");
    case OUTCOME_UNKNOWN:
        return new Event(this, "statusUnknown");
    default:
        throw new IllegalStateException("Unknown status");
}
~~~

Các kiểu trên là ví dụ do ứng dụng định nghĩa. **Không cần ném exception cho mọi nhánh từ chối nghiệp vụ**; event rõ nghĩa làm flow definition dễ đọc và kiểm thử.

## 8. Exception handling: xử lý ở đúng ranh giới

Có nhiều nơi có thể xử lý lỗi, nhưng không nên xử lý cùng một lỗi nhiều lần ở nhiều tầng.

| Vị trí | Trách nhiệm |
| --- | --- |
| Converter/binder | Báo lỗi chuyển kiểu và gắn với field |
| Validator | Kiểm tra ràng buộc dữ liệu form |
| Domain service | Trả outcome nghiệp vụ và bảo vệ invariant |
| Action | Ánh xạ outcome/exception đã phân loại thành event phù hợp |
| Flow exception handling | Xử lý exception không thể giải quyết bằng transition thông thường theo cấu hình Web Flow |
| Spring MVC/Security exception handling | Tạo phản hồi HTTP, login/access denied hoặc trang lỗi an toàn |
| Logging/observability | Ghi nhận ngữ cảnh, cause và correlation để điều tra |

### 8.1. Không coi transition on="error" là exception handler tổng quát

Ví dụ:

~~~xml
<action-state id="reserve">
    <evaluate expression="appointmentAction.reserve(requestContext)"/>
    <transition on="booked" to="completed"/>
    <transition on="error" to="problem"/>
</action-state>
~~~

Transition on="error" chỉ có thể xử lý **event có ID error mà action trả ra** theo flow contract. Nó không tự bắt tất cả Java exception hoặc mọi FlowExecutionException.

Nếu muốn xử lý exception của execution, cần dùng cơ chế exception handling được hỗ trợ trong phiên bản Web Flow, hoặc tầng web tương ứng. Không giả định một transition event thông thường sẽ tự nhận mọi throwable.

### 8.2. Handler không nên tự tạo lại nghiệp vụ

Exception handler nên tập trung:

- Phân loại lỗi đã biết.
- Ghi log/trace và correlation.
- Chọn phản hồi an toàn hoặc cơ chế kết thúc/phục hồi được hỗ trợ.
- Giữ thông tin đủ để người dùng tra cứu hoặc bắt đầu lại khi phù hợp.

Handler không nên gọi lại reserveOnce() chỉ vì gặp lỗi, không tự cấp booking ID và không biến lỗi quyền thành thành công.

**API đăng ký exception handler khác nhau theo phiên bản/cấu hình.** Hãy xác minh điểm nối của FlowExecutor/FlowExecution và tầng MVC trong dự án thay vì sao chép một đoạn XML không chắc tương thích.

## 9. Ghi log ngữ cảnh mà không làm lộ dữ liệu

Một log chẩn đoán có thể chứa:

~~~text
timestamp=2026-11-25T09:30:00Z
flowId=appointment
stateId=reserve
errorType=FlowExecutionException
causeType=DataAccessResourceFailureException
correlationId=7f...
outcome=unknown
~~~

Đây là định dạng minh họa, không phải output mặc định của Spring Web Flow.

Nên ghi:

- Flow ID và state ID.
- Loại exception ở tầng flow và loại cause phù hợp.
- Correlation/trace ID được sinh phía server.
- Event/state trước đó nếu có và đã được xác minh.
- Request ID nghiệp vụ đã được che giấu hoặc quản lý theo chính sách.
- Kết quả transaction nếu service có thể xác định.

Không nên ghi:

- Password, access token, refresh token, CSRF token.
- Toàn bộ HTTP session hoặc flowScope.
- Toàn bộ nội dung form có email, số điện thoại, địa chỉ, dữ liệu thanh toán.
- Execution key thô vào log có thời hạn lưu dài nếu không cần thiết.
- Stack trace vào message trả về browser.

### 9.1. Correlation ID giúp nối các lớp log

Một flow có thể tồn tại qua nhiều request HTTP. Mỗi request có trace riêng nhưng cùng một booking request ID có thể liên quan tới nhiều bước. Có thể dùng:

- **Trace ID:** liên kết các span của một request/chuỗi gọi đồng bộ.
- **Correlation ID:** liên kết log theo một hành trình hoặc thao tác nghiệp vụ.
- **Request ID/idempotency key:** định danh một ý định ghi để chống tạo trùng.

Ba giá trị này có mục đích khác nhau. Không dùng một execution key của Web Flow thay cho tất cả.

### 9.2. Tránh cardinality quá cao trong metrics

Không tạo metric label cho từng flow execution key, booking ID hoặc email. Những giá trị đó tạo cardinality rất lớn và có thể chứa dữ liệu nhạy cảm. Dùng nhãn giới hạn như flowId, stateId, exceptionCategory và outcome đã được kiểm soát.

## 10. Trả phản hồi an toàn cho người dùng

Người dùng thường không cần biết class exception, tên database hoặc stack trace. Họ cần biết:

- Hành động vừa thực hiện đã thành công, thất bại hay chưa xác định?
- Có thể tiếp tục, sửa dữ liệu hay phải đăng nhập lại?
- Có cần giữ mã yêu cầu để tra cứu không?

| Tình huống | Nội dung gợi ý |
| --- | --- |
| Lỗi nhập liệu | “Vui lòng kiểm tra thông tin được đánh dấu.” |
| Slot đã hết | “Khung giờ này không còn trống. Vui lòng chọn khung giờ khác.” |
| Dịch vụ tra cứu tạm gián đoạn | “Chưa tải được dữ liệu. Vui lòng thử lại sau.” |
| Kết quả ghi chưa xác định | “Chúng tôi chưa xác nhận được kết quả. Hãy kiểm tra trạng thái yêu cầu trước khi gửi lại.” |
| Session hết hạn | “Phiên làm việc đã hết hạn. Vui lòng đăng nhập và bắt đầu lại.” |
| Lỗi ngoài dự kiến | “Đã xảy ra lỗi. Mã tham chiếu: …” |

Nội dung trên nên được đặt trong resource bundle để hỗ trợ i18n. Mã tham chiếu là correlation ID công khai đã được thiết kế an toàn, không phải execution key hoặc stack trace.

### 10.1. Không đưa thông tin nguyên nhân nội bộ ra giao diện

Không hiển thị:

~~~text
org.springframework.dao.DataAccessResourceFailureException:
Connection refused to jdbc:...
~~~

hoặc tên class, SQL, đường dẫn file, host nội bộ, stack frame. Những chi tiết này thuộc log/trace có kiểm soát, không thuộc message cho người dùng.

### 10.2. Không tuyên bố thất bại khi kết quả chưa rõ

Nếu database đã commit nhưng response bị mất, thông báo “Đặt lịch thất bại” là sai. Nên dùng thông báo trạng thái chưa xác định và cung cấp chức năng kiểm tra theo request ID.

## 11. Phục hồi sau lỗi: quay lại state hay bắt đầu flow mới?

Quyết định phục hồi phụ thuộc **execution còn hợp lệ không** và **side effect đã xảy ra chưa**.

~~~mermaid
flowchart TD
    A["FlowExecutionException"] --> B{"Nguyên nhân đã phân loại?"}
    B -->|"Không"| C["Ghi log/trace, phản hồi lỗi an toàn"]
    B -->|"Có"| D{"Có thể tiếp tục execution an toàn?"}
    D -->|"Không"| E["Kết thúc/khởi động lại theo chính sách"]
    D -->|"Có"| F{"Đã có side effect ghi?"}
    F -->|"Chưa"| G["Cho thử lại có giới hạn nếu lỗi tạm thời"]
    F -->|"Có, kết quả rõ"| H["Hiển thị outcome đã xác nhận"]
    F -->|"Có thể đã commit, chưa rõ"| I["Tra cứu bằng requestId / đối soát"]
    I --> J{"Đã xác định kết quả?"}
    J -->|"Đã thành công"| H
    J -->|"Chưa rõ"| K["Giữ trạng thái pending / hỗ trợ"]
    J -->|"Chắc chắn chưa ghi"| G
~~~

### 11.1. Khi nên giữ execution và quay lại view-state

Phù hợp khi:

- Lỗi thuộc validation/binding và execution vẫn hoạt động.
- Service trả outcome nghiệp vụ đã biết, ví dụ SLOT_UNAVAILABLE.
- Một tác vụ đọc thất bại trước side effect và có thể thử lại an toàn.
- Flow có state phục hồi đã định nghĩa.

Ví dụ action trả slotUnavailable và transition về chooseSlot với message phù hợp.

### 11.2. Khi nên kết thúc hoặc bắt đầu execution mới

Có thể cần khi:

- Flow definition/version không còn tương thích với execution đã lưu.
- Execution key/snapshot không thể khôi phục.
- Session hoặc authentication hết hạn và chính sách yêu cầu bắt đầu lại.
- State không còn hợp lệ hoặc dữ liệu flow bị hỏng.

Không tự động tạo execution mới rồi sao chép toàn bộ dữ liệu cũ sang mà không kiểm tra quyền, tính toàn vẹn và tính hợp lệ.

### 11.3. Khi cần đối soát thay vì retry

Nếu lỗi xảy ra sau khi gửi lệnh ghi, kết quả có thể không chắc chắn. Hãy:

1. Giữ request ID ổn định của thao tác.
2. Tra cứu trạng thái booking bằng request ID.
3. Nếu đã commit, trả kết quả booking cũ.
4. Nếu chắc chắn chưa ghi, cho phép retry có kiểm soát.
5. Nếu chưa thể xác định, giữ trạng thái pending hoặc chuyển hỗ trợ.

Không tạo request ID mới chỉ vì một FlowExecutionException xuất hiện.

## 12. FlowExecutionException và browser Back/snapshot cũ

Spring Web Flow có thể lưu/khôi phục execution qua nhiều request. Trình duyệt có thể giữ trang cũ trong history hoặc gửi lại form từ một snapshot cũ.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as FlowExecutor
    participant S as BookingService
    participant DB as Database
    U->>B: Confirm booking
    B->>F: POST confirm + execution key
    F->>S: reserveOnce(requestId=R123)
    S->>DB: INSERT booking
    DB-->>S: Commit
    Note over S,F: Response bị mất
    S--xF: Timeout / kết quả không rõ ở caller
    F-->>B: Phản hồi lỗi
    U->>B: Back rồi submit lại
    B->>F: POST snapshot/key cũ
    F->>S: Tra cứu hoặc submitOnce(R123)
    S->>DB: Kiểm tra requestId
    DB-->>S: Booking cũ nếu đã tồn tại
    S-->>F: Kết quả đã xác nhận
~~~

Snapshot cũ không rollback database. Vì vậy:

- Execution key là định danh để tiếp tục flow theo cơ chế Web Flow.
- Request ID là định danh thao tác nghiệp vụ.
- Transaction và unique constraint bảo vệ dữ liệu bền vững.
- Flow cần xử lý execution hết hạn hoặc snapshot không hợp lệ.

Một FlowExecutionException trong quá trình resume có thể phản ánh lỗi repository, execution key hoặc trạng thái flow; không tự động có nghĩa service nghiệp vụ đã thất bại.

## 13. Subflow và ngữ cảnh exception

Giả sử flow appointment gọi subflow verifyContact. Nếu lỗi xảy ra trong state sendCode của flow con, log có thể phản ánh **flow con và state con**. Điều này giúp tìm đúng XML, action và dependency gây lỗi.

~~~mermaid
flowchart TD
    A["appointment: review"] --> B["appointment: verifyContact"]
    B --> C["verifyContact: sendCode"]
    C --> D["verifyContact: enterCode"]
    D -->|"verified"| E["appointment: reserve"]
    C -->|"exception"| F["FlowExecutionException context"]
    F --> G["flowId=verifyContact<br/>stateId=sendCode"]
~~~

Các ID trong sơ đồ là ví dụ minh họa. Khi chẩn đoán:

- Ghi flow/state thực tế từ exception.
- Kiểm tra input mapping từ flow cha sang flow con.
- Kiểm tra dependency và expression trong state con.
- Xem cause chain để phân biệt lỗi dịch vụ, lỗi dữ liệu và lỗi cấu hình.
- Quyết định flow cha cần nhận outcome, hiển thị lỗi hay để exception handler tiếp quản.

Không giả định một lỗi ở flow con tự động trở thành outcome cancelled. Muốn flow cha xử lý một kết quả dự kiến, hãy thiết kế outcome của subflow rõ ràng.

## 14. Những lỗi không nên bắt rồi chuyển thành event nghiệp vụ

Một action có thể viết sai:

~~~java
public Event reserve(RequestContext context) {
    try {
        service.reserveOnce(getDraft(context));
        return new Event(this, "booked");
    } catch (Exception ex) {
        return new Event(this, "slotUnavailable");
    }
}
~~~

Đây là anti-pattern vì:

- Database timeout bị hiểu thành hết slot.
- Access denied bị hiểu thành hết slot.
- Bug lập trình bị hiểu thành kết quả nghiệp vụ.
- Timeout sau commit có thể làm người dùng thử lại và tạo trùng.

Thay vào đó, service trả outcome có kiểu cho kết quả dự kiến và ném exception chuyên biệt cho lỗi kỹ thuật đã phân loại. Action chỉ bắt những exception mà nó biết cách xử lý đúng.

### 14.1. Không bắt Throwable

Throwable còn bao gồm các lỗi nghiêm trọng của JVM như OutOfMemoryError. Không nên bắt nó trong action để cố render một trang lỗi như thể ứng dụng vẫn hoạt động bình thường.

Chỉ bắt exception cụ thể có chính sách phục hồi. Các lỗi ngoài dự kiến nên đi theo cơ chế xử lý ở tầng phù hợp.

## 15. Bảo mật khi ghi nhận exception

FlowExecutionException và cause có thể chứa thông tin về request, dữ liệu đầu vào hoặc cấu hình hạ tầng. Log đầy đủ stack trace hữu ích cho vận hành, nhưng phải được bảo vệ:

- Chỉ người có quyền vận hành mới được xem log/trace chi tiết.
- Không ghi password, token, CSRF token, cookie hoặc toàn bộ session.
- Hạn chế ghi raw form values, email, số điện thoại, thông tin thanh toán.
- Không trả exception.getMessage() trực tiếp ra browser.
- Che giấu ID nghiệp vụ hoặc chỉ log correlation ID theo chính sách.
- Thiết lập retention và quyền truy cập log phù hợp.

Nếu cần mã tham chiếu cho người dùng, tạo một ID ngẫu nhiên phía server và liên kết nó với log; không dùng stack trace hoặc execution key làm mã công khai.

## 16. Kiểm thử FlowExecutionException và ngữ cảnh state

Một bộ test tốt không chỉ xác minh “có lỗi”. Nó cần xác minh **flow/state context, cause chain, phản hồi người dùng và side effect**.

| Tình huống | Ngữ cảnh mong đợi | Điều cần kiểm tra |
| --- | --- | --- |
| Bean expression không tìm thấy | Flow/state chứa expression | Cause phản ánh lỗi resolve bean |
| Null trong policy expression | State đang đánh giá policy | Cause cho thấy lỗi property/null |
| Database lỗi khi reserve | State reserve | Cause chain chứa lỗi persistence |
| Lỗi trong subflow | Flow/state của subflow | Không ghi nhầm thành state cuối của flow cha |
| Execution key không hợp lệ | Ngữ cảnh resume | Phản hồi an toàn, không gọi action ghi |
| Validation thất bại | View-state có form | Giữ state, báo lỗi field; không biến thành lỗi hệ thống |
| Slot hết chỗ | Action-state reserve | Event slotUnavailable, không cần exception hệ thống |
| Timeout sau commit | State reserve, kết quả ghi chưa rõ | Đối soát request ID, không tạo booking trùng |
| Lỗi lập trình bất ngờ | Flow/state được framework ghi nhận | Handler ghi log, người dùng nhận trang lỗi an toàn |

### 16.1. Unit test cho logging/diagnostic

Pseudocode:

~~~text
exception = FlowExecutionException(
    flowId="appointment",
    stateId="reserve",
    cause=DataAccessException(...)
)

logger.record(exception)

assert log contains flowId="appointment"
assert log contains stateId="reserve"
assert log preserves cause type
assert log does not contain raw email or session token
~~~

Đây là **pseudocode**, không phải constructor Java để chạy nguyên văn. Khi viết test thực tế, sử dụng constructor và API đúng phiên bản Web Flow; hoặc tạo exception qua một flow test thực sự để xác minh framework đóng gói ngữ cảnh thế nào.

### 16.2. Flow integration test

~~~text
start appointment flow
move to review
configure reserve action to throw a known test exception
send confirm

assert:
  exception reaches configured handling boundary
  FlowExecutionException identifies relevant flow/state
  cause chain retains original test exception
  no success event is emitted
  no duplicate reservation is created
~~~

Không nên assert một stateId cố định nếu phiên bản/cấu hình thực tế ghi nhận state ở mốc khác với giả định. Hãy dựa vào contract API và kết quả integration test.

### 16.3. Test riêng transaction và idempotency

Một test action không chứng minh dữ liệu đã commit đúng. Cần integration test với service/database:

1. Gửi reserveOnce(R123), mô phỏng commit rồi làm mất response.
2. Gọi lại cùng R123.
3. Xác minh service trả booking cũ.
4. Xác minh database chỉ có một booking cho request ID đó.
5. Xác minh trạng thái flow được phục hồi/đối soát mà không phát thông báo thất bại giả.

## 17. Quy trình chẩn đoán từng bước

Khi nhận một lỗi production:

1. Lấy correlation ID và thời điểm request.
2. Tìm log FlowExecutionException tương ứng.
3. Ghi nhận flowId và stateId từ exception.
4. Mở đúng flow definition và xem action/transition/entry/exit tại state đó.
5. Lần theo cause chain tới exception cụ thể.
6. Xác định lỗi do binding, expression, service, database, security hay repository execution.
7. Kiểm tra transaction và side effect đã xảy ra chưa.
8. Xác định execution còn tiếp tục được không.
9. Chọn phục hồi: sửa input, quay lại state, retry an toàn, đối soát hoặc kết thúc execution.
10. Kiểm tra người dùng nhận thông báo đúng ngôn ngữ, không lộ thông tin nội bộ.
11. Bổ sung regression test cho flow/state và service.

~~~text
Flow ID + State ID
        |
        v
Tìm action / expression / view
        |
        v
Đọc cause chain
        |
        v
Phân loại lỗi + kiểm tra side effect
        |
        v
Chọn event phục hồi hoặc exception handling
        |
        v
Test lại transition + transaction + UX
~~~

## 18. Bài thực hành: điều tra lỗi trong flow đặt lịch

Một ứng dụng có flow:

~~~text
chooseSlot → contact → review → reserve → completed
~~~

Log ghi:

~~~text
FlowExecutionException
  flowId = appointment
  stateId = reserve
  cause = ExpressionEvaluationException
    cause = ReservationPersistenceException
      cause = SQLTransientConnectionException
~~~

**Yêu cầu:**

1. Giải thích vì sao flowId và stateId giúp khoanh vùng nhưng không thay thế cause chain.
2. Xác định expression/action cần kiểm tra trong state reserve.
3. Nêu cách giữ cause khi service chuyển exception JDBC thành exception của ứng dụng.
4. Phân tích hai khả năng: lỗi trước khi gửi lệnh ghi và timeout sau khi database commit.
5. Thiết kế phản hồi riêng cho slotUnavailable, lookupUnavailable và statusUnknown.
6. Viết pseudocode logging có flow ID, state ID, cause type và correlation ID; không ghi PII.
7. Thiết kế exception handling phù hợp phiên bản Web Flow, không dùng transition on="error" để bắt mọi Java exception.
8. Viết test chứng minh lỗi trong subflow được ghi đúng flow/state.
9. Viết integration test commit rồi mất response, sau đó retry cùng request ID mà không tạo booking thứ hai.
10. Viết test browser/session hết hạn và xác minh người dùng được hướng dẫn bắt đầu lại an toàn.

**Tiêu chí đạt:** người đọc xác định được flow/state liên quan, truy ra nguyên nhân gốc, biết side effect đã xảy ra chưa và chọn được phản hồi phù hợp. Log đủ phục vụ điều tra nhưng không tiết lộ dữ liệu nhạy cảm; retry không làm phát sinh giao dịch trùng.

## 19. Tổng kết và câu hỏi tự kiểm tra

FlowExecutionException bổ sung ngữ cảnh Web Flow cho lỗi trong execution, đặc biệt là **flow ID** và **state ID** liên quan. Nó giúp khoanh vùng nơi lỗi được phát hiện; cause chain mới cho biết nguyên nhân bên dưới. Một lỗi có thể phát sinh trong binding, expression, action, transition, render, subflow hoặc khi resume execution.

Hãy xử lý theo đúng tầng: binding/validation cho dữ liệu form, outcome/event cho kết quả nghiệp vụ dự kiến, exception handler cho lỗi không thể xử lý bằng transition thông thường, và logging/observability để điều tra. Khi thao tác ghi có thể đã commit nhưng response bị mất, **đối soát bằng request ID và idempotency**, không kết luận thất bại hoặc retry mù. Phản hồi người dùng phải an toàn, rõ trạng thái và không lộ stack trace.

**Câu hỏi tự kiểm tra:**

1. FlowExecutionException khác exception gốc ở điểm nào?
2. flowId và stateId giúp chẩn đoán ra sao, và khi nào stateId có thể không xác định?
3. Vì sao không thể dựa vào tên state cuối cùng người dùng nhìn thấy trong browser để kết luận nơi lỗi xảy ra?
4. Khi action-state gọi bean và database ném lỗi, cần xem những phần nào trong cause chain?
5. Transition on="error" có tự bắt mọi FlowExecutionException không?
6. Vì sao lỗi slot hết chỗ nên là outcome nghiệp vụ thay vì exception kỹ thuật chung?
7. Nếu timeout xảy ra sau khi transaction commit, vì sao cần đối soát thay vì retry bằng request ID mới?
8. Khi lỗi xảy ra trong subflow, vì sao phải giữ flow/state ID thực tế trong log?
9. Những dữ liệu nào không nên ghi vào log hoặc đưa vào message trả cho browser?
10. Cần những loại test nào để xác minh flow context, cause chain, transaction và idempotency?
