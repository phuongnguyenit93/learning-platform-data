# FlowExecutionExceptionHandler và trạng thái nhất quán sau xử lý

Trong một flow nhiều bước, action có thể gọi service đặt lịch, trừ tồn kho, ghi đơn hàng hoặc gửi yêu cầu thanh toán. Nếu service ném exception, ứng dụng phải trả lời hai câu hỏi cùng lúc: **người dùng sẽ được đưa tới đâu tiếp theo**, và **dữ liệu nghiệp vụ cùng trạng thái flow hiện tại có còn nhất quán không**?

Spring Web Flow (SWF) cung cấp **FlowExecutionExceptionHandler** để xử lý một số exception phát sinh trong lúc flow đang chạy. Handler có thể điều hướng execution sang một state phục hồi phù hợp. Tuy nhiên, handler không tự hoàn tác transaction cơ sở dữ liệu, không sửa một giao dịch bên ngoài đã hoàn tất và cũng không bảo đảm mọi thay đổi trong flow scope tự quay lại trạng thái trước đó. Thiết kế phục hồi phải kết hợp flow transition, transaction service, idempotency và cách lưu trạng thái execution.

Bài học thuộc chương **Ngoại lệ và phục hồi** của module **SPRING_WEB_FLOW**. Module giúp mô hình hóa hành trình web bằng state, event, transition và subflow, đồng thời thực hành form binding, validation, scope/phiên, tích hợp Spring MVC và kiểm thử. Ta sẽ dùng flow đặt lịch để phân biệt lỗi nghiệp vụ với lỗi thực thi flow, cấu hình handler, chọn state đích an toàn và kiểm chứng trạng thái sau khi exception được xử lý.

> Các ví dụ API tập trung vào Spring Web Flow 2.5.x. Tên package, schema và tích hợp servlet cần được đối chiếu với phiên bản cụ thể của dự án. Bài này không giả định mọi ứng dụng Spring Boot đã tự cấu hình FlowExecutor hoặc exception handler.

## 1. Bài toán phục hồi: điều hướng đúng chưa đủ

Giả sử flow đặt lịch có các state:

~~~text
details → review → reserve → confirmation
                         ├→ chooseAnotherSlot
                         └→ technicalError
~~~

Người dùng chọn một khung giờ và bấm xác nhận. Service kiểm tra khả dụng rồi ghi đặt lịch. Trong lúc đó có thể xảy ra:

- Khung giờ vừa được người khác đặt trước.
- Database mất kết nối.
- Transaction bị rollback.
- Giao dịch đã commit nhưng response bị mất.
- Flow execution repository không lưu được snapshot mới.
- View đích không render được.
- Execution key đã hết hạn trước khi request tiếp theo tới server.

Một cách xử lý đơn giản là bắt mọi exception rồi chuyển tới màn hình lỗi. Nhưng nếu exception xảy ra **sau khi database đã commit**, người dùng thấy lỗi và bấm thử lại có thể tạo đặt lịch thứ hai. Ngược lại, nếu flow chuyển sang confirmation dù transaction chưa commit, giao diện sẽ nói thành công trong khi dữ liệu chưa được ghi.

Vì vậy, phục hồi cần bảo đảm ít nhất bốn điều:

1. **Flow control hợp lệ:** execution có state hiện tại rõ ràng hoặc được kết thúc theo một nhánh đã định nghĩa.
2. **Dữ liệu nghiệp vụ đúng:** transaction thành công hoặc rollback theo chính sách.
3. **Không tạo side effect trùng:** request lặp có thể được nhận diện và trả lại kết quả phù hợp.
4. **Thông báo trung thực:** người dùng biết nên sửa dữ liệu, thử lại, kiểm tra kết quả hay liên hệ hỗ trợ.

~~~mermaid
flowchart TD
    A["Action trong flow gọi service"] --> B{"Kết quả"}
    B -->|"Thành công"| C["Outcome success"]
    B -->|"Lỗi nghiệp vụ có thể dự đoán"| D["Outcome event riêng"]
    B -->|"Lỗi flow đã được map"| E["FlowExecutionExceptionHandler"]
    B -->|"Lỗi không được xử lý"| F["FlowHandler / Spring MVC"]
    C --> G["State thành công"]
    D --> H["State sửa dữ liệu hoặc chọn lại"]
    E --> I["State phục hồi đã khai báo"]
    F --> J["HTTP error / trang lỗi chung"]
    G --> K["Đối chiếu DB, execution và side effect"]
    H --> K
    I --> K
~~~

**Flow state và trạng thái nghiệp vụ là hai thứ liên quan nhưng độc lập.** Chuyển được sang state lỗi không chứng minh transaction đã rollback; database rollback cũng không tự đưa flow về state trước đó.

## 2. Phân loại lỗi trước khi chọn handler

Không phải lỗi nào cũng nên được xử lý bằng FlowExecutionExceptionHandler. Hãy phân loại theo nguồn gốc và khả năng phục hồi:

| Loại | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Validation đầu vào | Email sai, ngày không hợp lệ | Giữ ở view-state, hiển thị lỗi field |
| Kết quả nghiệp vụ dự đoán được | Hết chỗ, mã giảm giá hết hạn | Action trả event riêng để đi tới state nghiệp vụ |
| Xung đột đồng thời | Optimistic lock, khung giờ vừa được đặt | Tải lại dữ liệu, cho người dùng xem và quyết định lại |
| Exception trong flow | Action ném lỗi, không khớp transition, lỗi mapping | Handler nếu có nhánh phục hồi an toàn |
| Hạ tầng tạm thời | Timeout, dịch vụ ngoài tạm ngừng | Retry có giới hạn hoặc trang thử lại có kiểm soát |
| Lỗi lập trình/cấu hình | NullPointerException, sai expression, XML lỗi logic | Log, báo lỗi hệ thống; không che giấu bằng retry vô hạn |
| Bảo mật | AccessDeniedException, CSRF failure | Để Spring Security xử lý theo chính sách |
| Execution không còn tồn tại | Key hết hạn, execution đã kết thúc | Xử lý ở tầng HTTP/FlowHandler; phục hồi bản nháp bền vững nếu có |

### 2.1. Validation không phải exception handler

Nếu người dùng nhập số lượng âm hoặc bỏ trống email, đó là lỗi dữ liệu có thể dự đoán. Dùng binder và validation để giữ người dùng ở đúng view-state, gắn message vào field và cho phép sửa. Không nên ném một FlowExecutionException chỉ để điều hướng các lỗi nhập liệu bình thường.

### 2.2. Business exception có thể trở thành event

Nếu “không còn khung giờ trống” là một kết quả nghiệp vụ dự kiến, action có thể bắt exception cụ thể và trả event như **slotUnavailable**. Flow định nghĩa transition tới state chọn lại. Đây thường là cách rõ ràng hơn một exception handler tổng quát.

### 2.3. FlowExecutionException là lỗi lúc flow đang thực thi

**FlowExecutionException** là lớp cơ sở cho exception xảy ra trong runtime của flow. Một số lớp con trong SWF 2.5.x gồm:

- **ActionExecutionException:** lỗi khi thực thi action.
- **EnterStateVetoException:** việc vào state bị ngăn.
- **FlowAttributeMappingException:** lỗi mapping input/output của flow.
- **NoMatchingTransitionException:** event không tìm được transition phù hợp.
- **ViewRenderingException:** lỗi khi render view.

Đây là những lỗi ở các giai đoạn khác nhau. Không nên map tất cả về cùng một state “thử lại” mà không kiểm tra nguyên nhân. Ví dụ, lỗi mapping hoặc lỗi cấu hình thường cần sửa phần mềm; retry request không làm nó biến mất.

## 3. FlowExecutionExceptionHandler làm nhiệm vụ gì?

**FlowExecutionExceptionHandler** là một strategy xử lý exception xảy ra trong một **flow execution đang hoạt động**. Interface nằm trong package:

~~~java
org.springframework.webflow.engine.FlowExecutionExceptionHandler
~~~

Hợp đồng chính gồm hai phương thức:

~~~java
public interface FlowExecutionExceptionHandler {

    boolean canHandle(FlowExecutionException exception);

    void handle(
        FlowExecutionException exception,
        RequestControlContext context
    );
}
~~~

Ý nghĩa:

- **canHandle(exception):** handler xác định nó có nhận xử lý exception này hay không.
- **handle(exception, context):** xử lý exception trong request hiện tại, sử dụng execution control context.
- Khi xử lý, handler được kỳ vọng **thực hiện một transition** qua RequestControlContext; chỉ trả về mà không đưa flow tới state hợp lệ có thể làm execution không dùng được ở request sau.

Handler giống một transition đặc biệt được kích hoạt bởi exception. Nó có quyền điều khiển flow, vì vậy phức tạp hơn một action chỉ trả outcome.

### 3.1. Handler không phải nơi thay thế transaction

FlowExecutionExceptionHandler không có nhiệm vụ tự động:

- Gọi rollback cho transaction service.
- Xóa một bản ghi database đã commit.
- Hủy email hoặc thông điệp đã gửi tới hệ thống khác.
- Khôi phục mọi field đã thay đổi trong flowScope.
- Biến một execution đã hết hạn thành execution cũ còn dùng được.

Handler chỉ quyết định cách **flow execution đang hoạt động** tiếp tục hoặc chuyển sang nhánh phục hồi. Transaction và side effect phải được quản lý ở service/integration layer.

### 3.2. Handler không phải nơi bắt mọi Throwable

Chỉ nhận các loại exception mà ứng dụng có thể xử lý an toàn. Nếu handler nhận quá rộng, lỗi lập trình như NullPointerException có thể bị chuyển thành trang “thử lại” và che mất nguyên nhân thật.

Một nguyên tắc hữu ích:

- Lỗi nghiệp vụ có thể dự đoán: ưu tiên outcome event từ action.
- Exception runtime đã biết và có state phục hồi: dùng handler map theo loại cụ thể.
- Lỗi không biết nguyên nhân hoặc lỗi hạ tầng nghiêm trọng: để lan tới tầng xử lý lỗi chung sau khi đã ghi log phù hợp.
- Lỗi authorization/CSRF: giữ nguyên cơ chế bảo mật, không chuyển thành outcome thành công.

## 4. Ưu tiên action trả event cho nhánh nghiệp vụ bình thường

Tài liệu Spring Web Flow khuyến nghị trong nhiều trường hợp nên bắt exception tại action và trả **result event** để flow thực hiện transition chuẩn. Ví dụ, đặt lịch không thành công vì khung giờ vừa hết là kết quả nghiệp vụ mà flow có thể dự đoán.

Một action dạng POJO:

~~~java
public class BookingAction {

    private BookingService bookingService;

    public String reserve(
            BookingDraft draft,
            RequestContext context) {

        try {
            BookingReceipt receipt =
                    bookingService.reserve(draft);

            context.getFlowScope().put("receipt", receipt);
            return "success";

        } catch (SlotUnavailableException ex) {
            context.getMessageContext().addMessage(
                new MessageBuilder()
                    .error()
                    .defaultText(
                        "Khung giờ vừa được đặt. Hãy chọn thời gian khác."
                    )
                    .build()
            );
            return "slotUnavailable";
        }
    }
}
~~~

Flow XML:

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingAction.reserve(draft, flowRequestContext)"/>

    <transition on="success" to="confirmation"/>
    <transition on="slotUnavailable" to="chooseAnotherSlot"/>
</action-state>
~~~

Ví dụ cần bean **bookingAction**, **bookingService**, **BookingDraft** và **BookingReceipt** được cấu hình theo dự án. Chữ ký phương thức phải khớp expression và cách gọi action của phiên bản SWF đang dùng.

Cách làm này phù hợp vì:

- Flow thể hiện rõ kết quả nghiệp vụ bằng event.
- State đích nằm trong flow definition, dễ hiểu và review.
- Validation/message có thể được hiển thị ở view-state tiếp theo.
- Không cần tạo exception handler cho mọi nhánh bình thường.
- Các exception không dự kiến vẫn có thể lan tới cơ chế xử lý lỗi chuyên biệt.

**Không bắt mọi Exception rồi trả về success hoặc một event chung.** Nếu lỗi database hoặc lỗi lập trình bị coi là “không còn khung giờ”, người dùng sẽ nhận thông báo sai và log khó chẩn đoán.

## 5. Cấu hình TransitionExecutingFlowExecutionExceptionHandler

SWF cung cấp sẵn **TransitionExecutingFlowExecutionExceptionHandler**, một implementation của FlowExecutionExceptionHandler. Handler này ánh xạ loại exception cụ thể tới **state ID** đích.

API có phương thức:

~~~java
add(
    Class<? extends Throwable> exceptionClass,
    String targetStateId
)
~~~

Ví dụ cấu hình Java:

~~~java
@Bean
public FlowExecutionExceptionHandler bookingExceptionHandler() {
    return new TransitionExecutingFlowExecutionExceptionHandler()
        .add(SlotUnavailableException.class, "chooseAnotherSlot")
        .add(BookingConflictException.class, "reviewCurrentBooking");
}
~~~

Trong đó:

- **SlotUnavailableException** được ánh xạ tới state **chooseAnotherSlot**.
- **BookingConflictException** được ánh xạ tới state **reviewCurrentBooking**.
- Các state đích phải tồn tại trong flow tương ứng và có thể xử lý dữ liệu còn lại sau exception.

Handler built-in tìm loại exception phù hợp trong **cause chain**, nên có thể nhận ra exception nghiệp vụ nằm bên trong một FlowExecutionException hoặc exception bọc khác. Tuy vậy, chỉ nên map những exception có ý nghĩa phục hồi rõ ràng.

### 5.1. Đăng ký handler trong state

Phần tử **exception-handler** có thể được khai báo như phần tử con của state type và tham chiếu bean handler bằng thuộc tính **bean**:

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingService.reserve(draft)"/>
    <transition on="success" to="confirmation"/>

    <exception-handler bean="bookingExceptionHandler"/>
</action-state>

<view-state id="chooseAnotherSlot"
            view="booking/choose-another-slot"
            model="draft">
    <transition on="retry" to="review"/>
    <transition on="cancel" to="cancelled"
                bind="false"
                validate="false"/>
</view-state>

<view-state id="reviewCurrentBooking"
            view="booking/review-current"
            model="draft">
    <transition on="refresh" to="review"/>
    <transition on="cancel" to="cancelled"
                bind="false"
                validate="false"/>
</view-state>
~~~

Ví dụ cho thấy handler gắn với state **reserve**. Khi exception thuộc loại đã map xảy ra trong state này, handler chuyển flow tới state tương ứng. Cần kiểm tra schema của phiên bản SWF đang sử dụng và bảo đảm bean có mặt trong application context mà flow builder nhìn thấy.

### 5.2. Handler có thể xử lý exception chưa được map không?

**canHandle** của implementation built-in trả lời dựa trên các exception mapping đã đăng ký. Nếu không có mapping phù hợp, exception không được handler nhận; nó tiếp tục đi qua các handler khác hoặc lan ra tầng xử lý bên ngoài.

Đừng thêm mapping cho **Exception.class** chỉ để mọi lỗi đều được bắt. Mapping quá rộng dễ biến lỗi hệ thống thành trạng thái phục hồi giả tạo, trong khi flow hoặc database có thể đang ở trạng thái không xác định.

## 6. Dữ liệu exception được đưa vào flash scope

Khi **TransitionExecutingFlowExecutionExceptionHandler** xử lý exception, nó đưa flow exception và root cause vào flash scope để view đích có thể sử dụng:

| Thuộc tính | Tên trong flash scope | Ý nghĩa |
|---|---|---|
| Exception của flow | **flowExecutionException** | FlowExecutionException đã được handler xử lý |
| Root cause | **rootCauseException** | Exception gốc được tìm trong cause chain |

Các tên tương ứng với hằng số trong API:

~~~java
TransitionExecutingFlowExecutionExceptionHandler
    .FLOW_EXECUTION_EXCEPTION_ATTRIBUTE

TransitionExecutingFlowExecutionExceptionHandler
    .ROOT_CAUSE_EXCEPTION_ATTRIBUTE
~~~

Flash scope phù hợp với dữ liệu tạm thời phục vụ lần render sau. Nó không phải nơi lưu một trạng thái lỗi bền vững hoặc bản ghi audit lâu dài.

### 6.1. Không hiển thị raw exception cho người dùng

View không nên in trực tiếp giá trị của **flashScope.rootCauseException**. Thông tin này có thể chứa tên lớp nội bộ, SQL, endpoint, tên bảng hoặc dữ liệu nhạy cảm. Thay vào đó:

- Ghi exception vào log server với correlation ID.
- Chuyển mã lỗi an toàn hoặc message code vào view.
- Hiển thị hướng dẫn có thể hành động: thử lại, chọn thời gian khác, kiểm tra trạng thái hoặc liên hệ hỗ trợ.
- Không đưa stack trace vào HTML.
- Không lưu cookie, execution key hoặc token trong message.

Nếu cần hiển thị loại lỗi, dùng mapping sang mã lỗi do ứng dụng định nghĩa, không dùng nguyên văn exception message.

### 6.2. Flash scope không thay thế audit record

Nếu cần biết một lần đặt lịch thất bại vì lý do nào, hãy ghi audit/diagnostic event theo chính sách ứng dụng. Flash scope có vòng đời ngắn và có thể mất khi redirect hoặc execution kết thúc; nó không đủ để phục vụ đối soát.

## 7. Custom FlowExecutionExceptionHandler và rủi ro trạng thái không hợp lệ

Có thể tự viết class implements FlowExecutionExceptionHandler khi built-in mapping không đủ. Nhưng đây là extension point cần cẩn trọng.

Hợp đồng:

~~~java
public boolean canHandle(FlowExecutionException exception) {
    // Chỉ nhận các exception có thể phục hồi an toàn.
}

public void handle(
        FlowExecutionException exception,
        RequestControlContext context) {
    // Thực hiện transition hợp lệ trong execution context.
}
~~~

Trong **handle**, implementation được kỳ vọng gọi cơ chế thực thi transition trên **RequestControlContext**. Không chỉ ghi log, set một biến rồi trả về. Nếu handler kết thúc mà flow không có current state hợp lệ, execution có thể không sử dụng được ở request sau.

### 7.1. Trường hợp exception xảy ra lúc flow khởi động

Đây là trường hợp đặc biệt. Nếu exception phát sinh khi khởi tạo flow session và được chuyển tới exception handler, handler phải bảo đảm flow trở về trạng thái nhất quán. Tài liệu API nêu rõ: trong tình huống này, handler cần transition flow tới **start state**. Chỉ return mà không thiết lập current state có thể làm execution không dùng được.

Điều này cũng là lý do nên ưu tiên built-in **TransitionExecutingFlowExecutionExceptionHandler** nếu chỉ cần map exception sang state. Custom handler cần test cả exception lúc startup, exception khi vào state và exception khi xử lý event.

### 7.2. Đừng sửa state bằng cách thay đổi nội bộ không có transition

Một handler không nên:

- Gán current state bằng reflection.
- Xóa flow session khỏi repository rồi giả vờ request đã phục hồi.
- Đưa execution tới một state không tồn tại.
- Để execution ở trạng thái không có current state.
- Đánh dấu flow completed trong khi nghiệp vụ chưa hoàn tất.

Hãy dùng cơ chế transition được SWF hỗ trợ và bảo đảm state đích được định nghĩa trong flow.

## 8. Khi nào nên để exception đi ra ngoài flow?

Không phải mọi exception đều có state phục hồi bên trong flow. Ví dụ:

- XML flow definition sai hoặc expression không thể được tạo.
- View template bị thiếu hoặc lỗi renderer nghiêm trọng.
- Flow ID không tồn tại.
- Execution key hết hạn hoặc repository không khôi phục được execution.
- Request không còn session hoặc không đủ dữ liệu để resume.
- Lỗi lập trình không thể xử lý an toàn trong flow.

Các trường hợp này có thể cần **FlowHandler.handleException** hoặc cơ chế **Spring MVC HandlerExceptionResolver**.

Phân biệt hai tầng:

| Thành phần | Phạm vi | Dùng khi |
|---|---|---|
| FlowExecutionExceptionHandler | Bên trong một flow execution đang hoạt động | Có exception và flow còn đủ ngữ cảnh để chuyển state |
| FlowHandler.handleException | Tích hợp HTTP/Spring MVC cho FlowException chưa được xử lý trong flow | Cần chọn response hoặc trang lỗi khi flow handler nhận exception |
| Spring MVC HandlerExceptionResolver | Tầng MVC | Xử lý exception được ném ra khỏi flow adapter/handler |
| Servlet container error handling | Tầng web server | Lỗi không được xử lý ở các tầng trên |

### 8.1. FlowHandler.handleException

Interface **FlowHandler** có phương thức:

~~~java
String handleException(
    FlowException exception,
    HttpServletRequest request,
    HttpServletResponse response
);
~~~

Phương thức này xử lý FlowException chưa được Web Flow xử lý trong execution. Một custom handler có thể trả về location của trang lỗi hoặc trả null để tầng gọi tiếp tục xử lý theo cơ chế mặc định.

**AbstractFlowHandler** là base class tiện dụng nếu ứng dụng muốn tùy biến hành vi cho một flow cụ thể. Ví dụ, ứng dụng có thể chuyển tới trang giải thích execution đã hết hạn hoặc hiển thị mã hỗ trợ.

### 8.2. Execution hết hạn không phải exception trong một flow còn hoạt động

Khi execution key đã hết hạn hoặc execution đã kết thúc, SWF có thể không khôi phục được flow execution. Khi không có active execution context, **FlowExecutionExceptionHandler không thể chuyển state của execution đã mất**.

Trong Spring Web Flow 2.5.x, hành vi mặc định của **FlowHandlerAdapter** có thể cố gắng khởi động execution mới khi gặp **NoSuchFlowExecutionException** cho một execution đã kết thúc/hết hạn; các exception khác thường được ném lại cho Spring MVC ExceptionResolver nếu FlowHandler không xử lý. Hành vi này không khôi phục tự động dữ liệu flow scope cũ. Nếu ứng dụng cần tiếp tục bản nháp, phải lưu bản nháp bền vững và khởi tạo execution mới từ một draft ID được kiểm tra quyền.

## 9. Trạng thái flow và transaction database phải nhất quán

Đây là phần quan trọng nhất khi xử lý exception trong một action có side effect.

Giả sử action gọi service:

~~~java
BookingReceipt receipt = bookingService.reserve(draft);
context.getFlowScope().put("receipt", receipt);
~~~

Service có thể ghi database trong transaction, còn SWF lưu execution/snapshot qua **FlowExecutionRepository**. Hai cơ chế này không mặc nhiên nằm trong cùng một transaction.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as FlowExecutor
    participant S as BookingService
    participant DB as Database
    participant R as FlowExecutionRepository

    B->>F: POST event confirm
    F->>S: reserve(draft)
    S->>DB: INSERT booking
    DB-->>S: COMMIT
    S-->>F: receipt
    F->>R: Lưu execution snapshot mới
    R--xF: Lỗi lưu snapshot
    F-->>B: Request thất bại / response không hoàn tất
    Note over B,R: Database có booking, browser có thể vẫn giữ URL cũ
~~~

Nếu database commit thành công nhưng execution snapshot không được lưu, người dùng có thể gửi lại request theo key cũ. Nếu service không nhận diện yêu cầu lặp, hệ thống có thể tạo booking thứ hai.

Tình huống ngược lại cũng cần tránh: flow đã đi tới state confirmation nhưng transaction nghiệp vụ chưa commit hoặc đã rollback. Khi đó giao diện hiển thị thành công sai sự thật.

### 9.1. Flow scope không phải transaction

**flowScope** giữ dữ liệu trong một flow execution. Nó giúp chia sẻ draft giữa các state, nhưng không tự:

- Commit/rollback database.
- Khóa bản ghi nghiệp vụ.
- Chống request lặp.
- Đồng bộ với message broker.
- Bảo đảm snapshot execution được lưu cùng transaction service.

Không nên xem việc xóa một biến trong flowScope là rollback của nghiệp vụ.

### 9.2. Transaction nên nằm ở service nghiệp vụ

Một thao tác ghi database nên được bao quanh bởi transaction ở service:

~~~java
@Service
public class BookingService {

    @Transactional
    public BookingReceipt reserve(BookingDraft draft) {
        // Kiểm tra slot, ghi booking và trả receipt.
        // Tất cả thao tác database thuộc một transaction.
        return persistReservation(draft);
    }
}
~~~

Nếu thao tác ghi thất bại bằng unchecked exception, transaction mặc định của Spring rollback. Với checked exception, mặc định không rollback; cần khai báo rollback rule phù hợp, ví dụ **rollbackFor** trên @Transactional hoặc cấu hình tương đương.

### 9.3. Cẩn thận khi catch exception bên trong transaction

Xem ví dụ:

~~~java
@Transactional
public BookingResult reserve(BookingDraft draft) {
    try {
        writeReservation(draft);
        return BookingResult.success();
    } catch (InventoryConflictException ex) {
        return BookingResult.conflict();
    }
}
~~~

Nếu exception bị bắt bên trong phương thức transactional và phương thức trả về bình thường, transaction interceptor có thể không nhận được exception để đánh dấu rollback. Nếu trước đó đã có thay đổi dữ liệu, transaction có thể commit ngoài ý muốn.

Các lựa chọn an toàn:

1. Để exception thoát khỏi phương thức transactional và bắt ở action bên ngoài proxy.
2. Khai báo rollback rule cho loại exception phù hợp.
3. Nếu đó là một kết quả nghiệp vụ bình thường, kiểm tra điều kiện trước khi ghi và trả result type rõ ràng.
4. Chỉ dùng setRollbackOnly khi thật sự cần đánh dấu rollback trong transaction hiện tại và hiểu rõ hệ quả.

Không catch mọi exception rồi trả một object “failure” nếu chưa xác định transaction cần commit hay rollback.

### 9.4. Checked và unchecked exception

Theo mặc định của Spring transaction management:

- RuntimeException và Error làm transaction rollback.
- Checked Exception không tự động rollback nếu không có rollback rule.
- Có thể dùng rollbackFor/noRollbackFor để tùy biến.

Ví dụ:

~~~java
@Transactional(rollbackFor = ExternalReservationException.class)
public BookingReceipt reserve(BookingDraft draft)
        throws ExternalReservationException {
    // ...
}
~~~

Chọn rule dựa trên ý nghĩa nghiệp vụ và trạng thái dữ liệu. Đừng đổi mọi exception thành RuntimeException chỉ để ép rollback mà không xác định loại lỗi và cách flow phục hồi.

## 10. Thiết kế state phục hồi an toàn

State đích cần phản ánh **điều người dùng có thể làm tiếp theo** và **mức độ chắc chắn của kết quả nghiệp vụ**.

| State phục hồi | Dùng khi | Hành động phù hợp |
|---|---|---|
| chooseAnotherSlot | Slot không còn khả dụng và transaction không tạo booking | Chọn thời gian khác |
| reviewCurrentBooking | Dữ liệu xung đột hoặc bị thay đổi | Tải lại dữ liệu server và xác nhận lại |
| retryOperation | Lỗi tạm thời, kết quả thao tác đã được xác định là chưa commit | Thử lại có giới hạn |
| checkOperationStatus | Không biết request trước đã commit hay chưa | Tra cứu bằng idempotency key |
| technicalError | Lỗi không thể phục hồi trong flow | Hiển thị thông báo và mã hỗ trợ |
| cancelled | Người dùng chủ động hủy | Kết thúc flow, giải phóng tài nguyên cần thiết |

### 10.1. Retry không phải lúc nào cũng an toàn

Chỉ cho retry tự động hoặc thủ công khi service có thể xác định request trước **chưa tạo side effect**, hoặc thao tác được bảo vệ bằng idempotency.

Không tự động retry:

- Gửi email mà không có cơ chế chống gửi trùng.
- Charge thẻ thanh toán khi chưa biết request trước đã thành công hay chưa.
- Tạo booking mới nếu request cũ có thể đã commit.
- Gọi API bên ngoài có side effect nhưng không có idempotency key.

Nếu không xác định được kết quả, state phù hợp thường là **checkOperationStatus** để tra cứu trạng thái trước khi gửi lại lệnh.

### 10.2. State lỗi phải có thể render ổn định

Nếu exception xuất hiện khi render view, không map về một view cũng đang dùng template hoặc bean bị lỗi. State phục hồi nên tối giản, ít dependency, có thể hiển thị một thông báo chung và mã hỗ trợ.

Không để error state gọi lại ngay service đã ném exception trong on-entry; điều đó có thể tạo vòng lặp exception-handler.

### 10.3. Chỉ giữ dữ liệu cần thiết

Nếu exception handler đưa exception vào flash scope, view đích nên lấy message code hoặc thông tin đã được làm sạch. Draft vẫn nằm trong scope theo thiết kế, nhưng không đưa toàn bộ stack trace, entity nhạy cảm hoặc object service vào flow scope.

## 11. Idempotency bảo vệ khi request được gửi lại

**Idempotency** giúp cùng một yêu cầu nghiệp vụ được gửi lại mà không tạo thêm side effect. Với flow đặt lịch, có thể sinh một request ID duy nhất ở server khi người dùng bắt đầu thao tác xác nhận.

~~~java
public class BookingDraft {
    private UUID draftId;
    private UUID idempotencyKey;
    // Các trường đặt lịch khác.
}
~~~

Service có thể lưu idempotency key cùng kết quả:

~~~java
@Transactional
public BookingReceipt reserve(BookingDraft draft) {
    return repository.findByIdempotencyKey(draft.getIdempotencyKey())
        .orElseGet(() -> createAndStoreReservation(draft));
}
~~~

Đây là pseudocode minh họa. Triển khai thật phải bảo đảm **atomicity** bằng unique constraint hoặc cơ chế khóa thích hợp; nếu hai request đồng thời cùng không tìm thấy key, cả hai không được tạo hai booking.

Các quy tắc:

- Key được tạo và quản lý ở server; không dùng execution key của SWF thay thế.
- Key phải gắn với user/tenant và nghiệp vụ phù hợp.
- Cùng key và cùng payload hợp lệ trả về cùng kết quả đã ghi.
- Cùng key nhưng payload khác phải bị từ chối hoặc xử lý theo chính sách rõ ràng.
- Có thời hạn lưu idempotency record phù hợp với thời gian retry và đối soát.

### 11.1. Kiểm tra trạng thái trước khi retry

Nếu browser gửi lại POST sau timeout, action không nên mù quáng gọi create mới. Service tra cứu theo idempotency key:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu reserve"] --> B{"Có idempotency record?"}
    B -->|"Có, đã thành công"| C["Trả receipt đã lưu"]
    B -->|"Có, đang xử lý"| D["Trả trạng thái pending"]
    B -->|"Có, thất bại cuối cùng"| E["Trả kết quả thất bại"]
    B -->|"Chưa có"| F["Thực hiện transaction"]
    F --> G{"Commit thành công?"}
    G -->|"Có"| H["Lưu/đọc receipt"]
    G -->|"Không"| I["Rollback và ghi nhận kết quả phù hợp"]
~~~

Khi FlowExecutionRepository gặp lỗi sau khi service commit, lần request tiếp theo có thể dùng cùng key để lấy lại receipt. Flow có thể tiếp tục tới confirmation mà không tạo bản ghi mới.

## 12. External side effect và mô hình outbox

Database transaction không thể tự rollback một email đã gửi hoặc một message đã được broker nhận. Nếu action làm cả hai:

1. Ghi booking vào database.
2. Gửi email xác nhận.
3. Sau đó flow execution lưu snapshot thất bại.

Một lần retry có thể gửi email thứ hai.

Mô hình **transactional outbox** giúp giảm khoảng trống giữa ghi dữ liệu và phát thông điệp:

- Trong cùng transaction, ghi booking và một outbox record.
- Worker riêng đọc outbox và gửi message.
- Sau khi gửi, worker đánh dấu record đã xử lý.
- Consumer hoặc worker cần idempotency để chịu được gửi lại.
- Flow chỉ hiển thị confirmation dựa trên booking đã được ghi nhận.

Đây là kiến trúc xử lý side effect bền vững, không phải tính năng tự động của FlowExecutionExceptionHandler. Flow handler chỉ điều hướng execution; outbox/worker chịu trách nhiệm phân phối sự kiện nghiệp vụ.

### 12.1. Compensation khi không thể rollback

Với hệ thống bên ngoài, đôi khi cần **compensating action** thay vì rollback thật. Ví dụ đã giữ chỗ ở hệ thống đối tác nhưng bước ghi nội bộ thất bại, ứng dụng có thể gọi API giải phóng chỗ.

Compensation cũng có thể thất bại hoặc được gửi lặp, nên cần:

- Ghi trạng thái từng bước.
- Có operation ID ổn định.
- Retry có giới hạn và backoff.
- Audit rõ ràng.
- State phục hồi cho nhân viên xử lý thủ công nếu cần.

Không đặt toàn bộ compensation trong một exception handler rồi giả định nó luôn chạy thành công.

## 13. Ví dụ hoàn chỉnh: xử lý exception khi giữ chỗ

Tình huống:

- User chọn ngày và khung giờ.
- Flow gọi service giữ chỗ.
- Slot conflict là lỗi nghiệp vụ có thể phục hồi.
- Database timeout là lỗi hạ tầng cần được log và chuyển nhánh an toàn.
- Request lặp phải dùng idempotency key.

Flow XML minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="draft"
         class="com.example.booking.BookingDraft"/>

    <view-state id="details"
                view="booking/details"
                model="draft">
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled"
                    bind="false"
                    validate="false"/>
    </view-state>

    <view-state id="review"
                view="booking/review"
                model="draft">
        <transition on="back" to="details"
                    bind="false"
                    validate="false"/>
        <transition on="confirm" to="reserve"/>
    </view-state>

    <action-state id="reserve">
        <evaluate expression="bookingAction.reserve(draft, flowRequestContext)"/>

        <transition on="success" to="confirmation"/>
        <transition on="slotUnavailable" to="chooseAnotherSlot"/>

        <exception-handler bean="bookingExceptionHandler"/>
    </action-state>

    <view-state id="chooseAnotherSlot"
                view="booking/choose-another-slot"
                model="draft">
        <transition on="retry" to="review"/>
        <transition on="cancel" to="cancelled"
                    bind="false"
                    validate="false"/>
    </view-state>

    <view-state id="checkOperationStatus"
                view="booking/check-operation-status"
                model="draft">
        <transition on="refresh" to="reserve"/>
        <transition on="cancel" to="cancelled"
                    bind="false"
                    validate="false"/>
    </view-state>

    <view-state id="technicalError"
                view="booking/technical-error">
        <transition on="finish" to="cancelled"
                    bind="false"
                    validate="false"/>
    </view-state>

    <view-state id="confirmation"
                view="booking/confirmation">
        <transition on="finish" to="completed"
                    bind="false"
                    validate="false"/>
    </view-state>

    <end-state id="completed"/>
    <end-state id="cancelled"/>
</flow>
~~~

Java config cho handler:

~~~java
@Bean
public FlowExecutionExceptionHandler bookingExceptionHandler() {
    return new TransitionExecutingFlowExecutionExceptionHandler()
        .add(BookingConflictException.class, "chooseAnotherSlot")
        .add(UnknownBookingOutcomeException.class, "checkOperationStatus");
}
~~~

Trong ví dụ, **BookingConflictException** được ánh xạ tới state chọn khung giờ khác. **UnknownBookingOutcomeException** được ánh xạ tới state tra cứu trạng thái operation. Không map tất cả **DataAccessException** hoặc **Exception** sang retry; cần xác định loại lỗi nào thực sự có thể phục hồi.

Nếu action bắt **SlotUnavailableException** và trả event **slotUnavailable**, transition trong action-state sẽ đưa flow tới chooseAnotherSlot mà không cần handler. Handler dành cho những exception đã được định nghĩa mapping cụ thể.

**Lưu ý về consistency:** service phải commit booking trước khi action đặt receipt vào flow scope và trả success. Nếu service commit nhưng execution repository không lưu được, idempotency key cho phép lần request sau đọc lại receipt. Nếu transaction rollback, flow không được hiển thị confirmation.

## 14. Kiểm thử handler và trạng thái sau xử lý

Một test chỉ xác nhận view lỗi xuất hiện là chưa đủ. Cần kiểm tra cả **state flow**, **transaction database** và **side effect**.

### 14.1. Test action trả business event

Khi slot không khả dụng:

1. Mock service ném SlotUnavailableException.
2. Gọi action.
3. Xác nhận action trả event **slotUnavailable**.
4. Xác nhận message được thêm vào MessageContext.
5. Phát event trong flow execution test.
6. Kiểm tra flow ở state chooseAnotherSlot.
7. Xác nhận không có booking được ghi.

### 14.2. Test built-in exception handler

Dùng flow execution test hoặc integration test để kiểm tra:

- Exception class đã map chuyển tới đúng target state.
- Exception không được map không bị handler nhận.
- Exception lồng trong cause chain được nhận theo mapping.
- State đích tồn tại và có thể render.
- Flash scope chứa exception/root-cause attribute theo API.
- UI chỉ hiển thị message đã làm sạch.
- Không có action side effect nào chạy sau khi exception bị từ chối.

### 14.3. Test transaction rollback

Dùng database test thật hoặc transaction test phù hợp:

1. Service bắt đầu transaction.
2. Ghi một thay đổi.
3. Ném unchecked exception.
4. Xác nhận thay đổi không tồn tại sau rollback.
5. Lặp lại với checked exception và rollback rule được cấu hình.
6. Thử trường hợp exception bị catch bên trong service và xác nhận hành vi commit/rollback đúng thiết kế.

Không chỉ mock service rồi assert exception; cần một test persistence để chứng minh trạng thái database.

### 14.4. Test request lặp sau lỗi snapshot

Mô phỏng:

1. Request confirm gọi service và commit booking.
2. Flow execution persistence gặp lỗi hoặc response bị mất.
3. Client gửi lại cùng operation/idempotency key.
4. Service trả receipt đã tồn tại.
5. Không có booking thứ hai.
6. Flow tiếp tục tới confirmation với receipt đúng.

Đây là test quan trọng cho tình huống database commit và execution snapshot không cùng transaction.

### 14.5. Test custom handler khi startup lỗi

Nếu có custom FlowExecutionExceptionHandler, hãy tạo tình huống exception lúc flow session startup và xác nhận handler đưa execution về start state hợp lệ. Nếu handler không làm được điều đó, không nên phát hành implementation này.

## 15. Ma trận kiểm thử lỗi và phục hồi

| ID | Tình huống | Handler/nhánh | Trạng thái cần xác minh |
|---|---|---|---|
| E01 | Validation form thất bại | Message + giữ view-state | Draft giữ dữ liệu hợp lệ, không transition sai |
| E02 | Slot không còn khả dụng | Action trả slotUnavailable | State chọn slot khác, không tạo booking |
| E03 | Booking conflict | Exception handler map | State review lại dữ liệu mới |
| E04 | DB timeout trước commit | Handler/outer error theo policy | Transaction rollback hoặc trạng thái chưa commit được xác nhận |
| E05 | DB commit nhưng response mất | Check operation status/idempotency | Chỉ một booking, receipt được khôi phục |
| E06 | Exception không có mapping | Lan tới tầng ngoài | Không giả vờ thành công, log có correlation ID |
| E07 | Handler target state sai | Test cấu hình thất bại | Không phát hành flow có target không tồn tại |
| E08 | Exception lúc flow startup | Handler về start state | Execution có current state hợp lệ |
| E09 | View lỗi khi render | Fallback view hoặc MVC error | Không lặp exception trong cùng view |
| E10 | Execution key hết hạn | FlowHandler/MVC layer | Không gọi in-flow handler trên execution đã mất |
| E11 | Request confirm gửi lặp | Idempotency | Không tạo booking hoặc email trùng |
| E12 | Service ném checked exception | rollbackFor phù hợp | DB không giữ thay đổi dở dang |
| E13 | External API đã thực hiện side effect | Compensation/outbox | Operation có trạng thái đối soát rõ |
| E14 | Exception bị catch bên trong transaction | Kiểm tra transaction rule | Không commit dữ liệu dở dang ngoài ý muốn |
| E15 | AccessDeniedException | Security handling | Không chuyển thành state success hoặc lộ dữ liệu |

## 16. Chẩn đoán khi flow không phục hồi như dự kiến

### 16.1. Handler không được gọi

Kiểm tra:

- Exception có phải FlowExecutionException hoặc được bọc thành loại phù hợp không?
- Exception có phát sinh trong active flow execution không?
- Handler có được khai báo trong đúng state không?
- Bean reference có tồn tại trong context mà flow builder sử dụng không?
- canHandle có trả true cho exception thực tế/cause chain không?
- Exception có bị action bắt và trả event trước khi tới handler không?

### 16.2. Flow chuyển state nhưng vẫn báo lỗi ở request sau

Có thể handler đã transition nhưng:

- State đích không có view/bean cần thiết.
- Execution repository không lưu snapshot.
- Dữ liệu trong flowScope đã bị thay đổi một phần trước exception.
- State đích tiếp tục gọi lại service lỗi.
- Request sau dùng execution key cũ hoặc session đã hết hạn.

Kiểm tra state đích và execution URL được phát hành sau response; đừng chỉ xem log của handler.

### 16.3. Database đã có bản ghi nhưng flow báo lỗi

Đây là dấu hiệu hai transaction boundary không cùng hoàn tất. Tra cứu theo idempotency key hoặc operation ID, sau đó trả kết quả đã lưu. Không xóa booking chỉ vì browser không nhận được response; có thể người dùng đã nhận được dịch vụ hoặc hệ thống ngoài đã phát thông báo.

### 16.4. Flow báo thành công nhưng database không có dữ liệu

Kiểm tra:

- Action có trả event success quá sớm không?
- Service có thực sự commit không?
- Checked exception có rollback rule phù hợp không?
- Exception có bị catch và biến thành success không?
- Receipt trong flow scope có phải object giả được tạo trước khi ghi dữ liệu không?

Confirmation nên dựa trên kết quả đã commit hoặc operation record có trạng thái rõ ràng.

### 16.5. Exception handler tạo vòng lặp

Nếu state đích có action lại ném đúng exception đã map, flow có thể lặp qua handler nhiều lần. Chọn state phục hồi không gọi lại cùng hành động trong on-entry, hoặc thêm điều kiện giới hạn retry và yêu cầu người dùng chủ động tiếp tục.

## 17. Bài tập thực hành: phục hồi quy trình đặt lịch

Tạo flow:

~~~text
details → review → reserve → confirmation
                    ├→ chooseAnotherSlot
                    ├→ checkOperationStatus
                    └→ technicalError
~~~

**Yêu cầu:**

1. Service reserve dùng transaction để kiểm tra slot và ghi booking.
2. Nếu slot hết chỗ, action trả event **slotUnavailable** và thêm message cho người dùng.
3. Nếu booking conflict, built-in TransitionExecutingFlowExecutionExceptionHandler map tới state chooseAnotherSlot.
4. Nếu không xác định được kết quả request, handler map tới checkOperationStatus.
5. Dùng idempotency key cho mỗi thao tác confirm.
6. Nếu transaction rollback, không được đưa flow tới confirmation.
7. Nếu database commit nhưng response mất, lần retry trả receipt cũ, không tạo booking mới.
8. Nếu exception không được map, để nó đi tới tầng xử lý lỗi chung và ghi log.
9. Kiểm thử exception lúc startup nếu có custom handler.
10. Kiểm thử request confirm hai lần và đối chiếu số booking/email thực tế.
11. Kiểm tra view error không render raw exception hoặc dữ liệu nhạy cảm.
12. Viết test cho execution key hết hạn ở tầng HTTP/FlowHandler thay vì in-flow handler.

### Câu hỏi tự kiểm tra

**1. FlowExecutionExceptionHandler xử lý lỗi ở phạm vi nào?** Trong một flow execution đang hoạt động; nó quyết định cách flow chuyển tiếp sau exception.

**2. Vì sao action trả event thường phù hợp với lỗi nghiệp vụ dự đoán được?** Vì flow có transition tường minh cho kết quả đó, dễ hiểu và không cần exception handler tổng quát.

**3. handle() của custom handler phải làm gì?** Thực hiện transition hợp lệ qua RequestControlContext; không được chỉ return và để execution thiếu current state.

**4. Vì sao built-in TransitionExecutingFlowExecutionExceptionHandler hữu ích?** Nó map exception class tới state ID, tìm trong cause chain và đưa exception/root cause vào flash scope.

**5. Handler có tự rollback database không?** Không. Transaction rollback thuộc transaction manager/service và rollback rules.

**6. Vì sao checked exception có thể không rollback theo mặc định?** Vì Spring declarative transaction mặc định rollback RuntimeException và Error, còn checked exception cần rollbackFor hoặc rule tương ứng.

**7. Nếu DB đã commit nhưng flow snapshot không lưu được thì sao?** Request lặp có thể tạo side effect trùng; dùng idempotency key và tra cứu kết quả đã commit.

**8. Execution key hết hạn có thể được FlowExecutionExceptionHandler chuyển về state retry không?** Không nếu execution đã không thể khôi phục; xử lý ở FlowHandler/MVC layer và khởi tạo execution mới từ dữ liệu bền vững nếu có.

**9. Có nên map mọi Exception sang technicalError không?** Không. Lỗi lập trình, lỗi cấu hình, authorization và lỗi nghiệp vụ cần cách xử lý khác nhau; mapping quá rộng che giấu nguyên nhân.

## 18. Checklist trước khi phát hành

- [ ] Đã phân biệt validation, business result, flow exception và lỗi HTTP/execution repository.
- [ ] Action trả event cho nhánh nghiệp vụ có thể dự đoán.
- [ ] Handler chỉ nhận exception class đã biết và có nhánh phục hồi an toàn.
- [ ] Built-in TransitionExecutingFlowExecutionExceptionHandler được ưu tiên khi chỉ cần map exception tới state.
- [ ] Bean handler được đăng ký đúng context và exception-handler đặt trong state phù hợp.
- [ ] Target state tồn tại, có thể render và không tự lặp lại lỗi.
- [ ] Custom handler thực hiện transition hợp lệ và xử lý trường hợp startup exception.
- [ ] Exception không được map có thể lan tới tầng xử lý lỗi chung.
- [ ] AccessDeniedException và lỗi CSRF không bị biến thành business success.
- [ ] Flow scope không bị coi là transaction hoặc kho dữ liệu bền vững.
- [ ] Service transaction có rollback rules đúng với checked/unchecked exception.
- [ ] Không catch exception trong transaction rồi commit dữ liệu dở dang ngoài ý muốn.
- [ ] Side effect dùng idempotency hoặc cơ chế chống lặp phù hợp.
- [ ] Database commit và FlowExecutionRepository được xem là hai boundary riêng nếu không có transaction coordination rõ ràng.
- [ ] External side effect có outbox, idempotency hoặc compensation phù hợp.
- [ ] Flash scope chỉ giữ thông tin tạm thời và view không lộ raw exception.
- [ ] Execution hết hạn được xử lý ở tầng HTTP/FlowHandler.
- [ ] Test bao phủ state, transaction, duplicate request, snapshot failure và exception không được map.
- [ ] Log có correlation ID và không chứa cookie, token, execution key hoặc dữ liệu cá nhân không cần thiết.

**Ghi nhớ:** FlowExecutionExceptionHandler giúp flow chuyển sang một state phục hồi khi exception xảy ra trong execution đang hoạt động. Handler phải đưa execution tới state hợp lệ; nó không thay thế transaction, idempotency hoặc cơ chế đối soát side effect. Hãy dùng action event cho lỗi nghiệp vụ dự đoán được, handler map cho exception đã biết, và tầng FlowHandler/MVC cho execution không còn khôi phục được. Chỉ khi flow state, database và side effect cùng có trạng thái xác định thì người dùng mới có thể tiếp tục an toàn.

### Tài liệu tham khảo

- [Spring Web Flow 2.5.x Reference — Action Exceptions and exception-handler element](https://docs.spring.io/spring-webflow/docs/2.5.x-SNAPSHOT/reference/)
- [Spring Web Flow 2.5.x API — FlowExecutionExceptionHandler](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/engine/FlowExecutionExceptionHandler.html)
- [Spring Web Flow 2.5.x API — TransitionExecutingFlowExecutionExceptionHandler](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/engine/support/TransitionExecutingFlowExecutionExceptionHandler.html)
- [Spring Web Flow 2.5.x API — FlowExecutionException](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/api/org/springframework/webflow/execution/FlowExecutionException.html)
- [Spring Web Flow 2.5.x API — AbstractFlowHandler](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/mvc/servlet/AbstractFlowHandler.html)
- [Spring Framework Reference — Rolling Back a Declarative Transaction](https://docs.spring.io/spring/reference/7.0/data-access/transaction/declarative/rolling-back.html)

