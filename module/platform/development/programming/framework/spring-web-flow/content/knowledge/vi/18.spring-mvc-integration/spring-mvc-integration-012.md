# Xử lý ngoại lệ ở ranh giới MVC–Web Flow

*Chương: Tích hợp Spring MVC · Module: SPRING_WEB_FLOW*

Khi Spring Web Flow chạy bên trong Spring MVC, một request đi qua nhiều lớp: servlet container, DispatcherServlet, handler mapping, FlowHandlerAdapter, FlowExecutor, flow execution và cuối cùng là view. Ngoại lệ có thể phát sinh ở bất kỳ lớp nào. Nếu mọi lỗi đều được xử lý như lỗi của controller, ứng dụng có thể bỏ qua trạng thái của flow, làm mất dữ liệu người dùng đang nhập hoặc hiển thị một trang lỗi không phù hợp với bước hiện tại.

Xử lý ngoại lệ ở ranh giới MVC–Web Flow cần phân biệt lỗi thuộc hành trình của flow với lỗi thuộc tầng web chung. Lỗi nghiệp vụ có thể được chuyển thành một nhánh trong flow; lỗi execution cần được xử lý trong ngữ cảnh flow; lỗi còn thoát ra khỏi adapter mới được xử lý bởi cơ chế exception resolution của Spring MVC. Những lỗi xảy ra trước DispatcherServlet, chẳng hạn một số lỗi xác thực hoặc phân quyền ở filter chain, cần được xử lý ở tầng bảo mật tương ứng.

Module SPRING_WEB_FLOW tập trung mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow, kết hợp form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng. Bài học này giúp bạn đặt đúng nơi xử lý lỗi, bảo toàn dữ liệu cần thiết và đưa người dùng tới một kết quả có thể hiểu được khi flow hoặc tầng MVC gặp sự cố.

Sau bài học, bạn có thể:

- Mô tả đường đi của request flow qua DispatcherServlet và FlowHandlerAdapter.
- Phân biệt lỗi binding, lỗi nghiệp vụ, FlowExecutionException và lỗi MVC.
- Chọn giữa transition theo exception, FlowExecutionExceptionHandler và HandlerExceptionResolver.
- Hiểu vai trò của FlowHandler khi flow kết thúc hoặc phát sinh FlowException.
- Thiết kế phản hồi lỗi an toàn, có log và không làm lộ chi tiết nội bộ.
- Kiểm thử lỗi trong flow execution và lỗi thoát ra ranh giới MVC.

## 1. Đường đi của request và vị trí phát sinh lỗi

Spring Web Flow tích hợp vào Spring MVC thông qua các thành phần mapping và adapter. FlowHandlerMapping nhận diện URL thuộc một flow và chọn handler tương ứng. FlowHandlerAdapter nhận request, gọi FlowExecutor để khởi chạy hoặc tiếp tục execution. Executor làm việc với flow definition, state hiện tại, dữ liệu scope và event được gửi lên.

Sơ đồ rút gọn:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Servlet filters]
    B --> C[DispatcherServlet]
    C --> D[FlowHandlerMapping]
    D --> E[FlowHandlerAdapter]
    E --> F[FlowExecutor]
    F --> G[Flow execution và state]
    G --> H[Action, service, binding]
    G --> I[View]
    H --> J{Có ngoại lệ?}
    J -->|Có| K[Flow-level exception handling]
    J -->|Không| I
    K --> L{Đã xử lý?}
    L -->|Có| I
    L -->|Không| M[FlowHandler hoặc lỗi thoát ra adapter]
    M --> N[Spring MVC HandlerExceptionResolver]
    N --> O[HTTP error response]
~~~

Các lớp không có cùng ngữ cảnh:

| Vị trí | Ngữ cảnh sẵn có | Ví dụ lỗi |
|---|---|---|
| Servlet filter | Request, response, security context | Chưa đăng nhập, không đủ quyền |
| DispatcherServlet và handler mapping | URL, handler và cấu hình MVC | Không tìm thấy handler, mapping không đúng |
| Flow view binding | State hiện tại, model và binding result | Chuỗi không chuyển được thành LocalDate |
| Action hoặc service trong flow | Flow scope, input và nghiệp vụ hiện tại | Hết hàng, dữ liệu không còn hợp lệ, lỗi database |
| Flow execution engine | Flow definition và execution context | State không tồn tại, event không được hỗ trợ, execution lỗi |
| MVC view rendering | Model và view được chọn | Không tìm thấy template, lỗi render |

Điểm quan trọng là ngoại lệ phát sinh trong một action không nhất thiết đi thẳng tới @ControllerAdvice. Flow engine hoặc FlowHandlerAdapter có thể xử lý lỗi trước khi nó thoát ra khỏi handler. Ngược lại, lỗi không được flow xử lý và được ném ra ngoài adapter có thể tiếp tục đi qua chuỗi HandlerExceptionResolver của DispatcherServlet.

## 2. Phân loại lỗi trước khi chọn cơ chế xử lý

Không nên dùng một trang lỗi duy nhất cho mọi ngoại lệ. Hãy phân loại theo ý nghĩa và khả năng phục hồi:

| Loại lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Binding/conversion | Ngày nhập sai định dạng, số tiền không parse được | Giữ người dùng ở view state, hiển thị lỗi theo trường |
| Validation/nghiệp vụ có thể sửa | Thiếu địa chỉ, số lượng vượt giới hạn | Thêm message và yêu cầu sửa dữ liệu |
| Điều kiện nghiệp vụ thay đổi | Hết hàng, báo giá hết hạn | Chuyển tới state thông báo hoặc chọn lại |
| Lỗi hạ tầng tạm thời | Timeout dịch vụ ngoài, database tạm ngừng | Ghi log, bảo toàn dữ liệu cần thiết, cân nhắc retry |
| Lỗi execution | Flow definition lỗi, state/event không hợp lệ | Flow-level handler hoặc cơ chế lỗi phù hợp |
| Execution hết hạn/không còn tồn tại | Người dùng mở tab cũ sau thời gian dài | Khởi tạo hành trình mới hoặc trang phục hồi |
| Lỗi MVC ngoài flow | Controller thông thường lỗi, không tìm thấy view | HandlerExceptionResolver hoặc @ControllerAdvice |
| Lỗi bảo mật | Chưa xác thực hoặc truy cập trái quyền | Security entry point/access-denied handler |

Một lỗi dữ liệu người dùng nhập sai thường không phải lỗi hệ thống. Nó nên được biểu diễn thành binding error hoặc validation message để người dùng sửa ngay tại bước hiện tại. Một lỗi hệ thống nghiêm trọng không nên bị biến thành thông báo “Dữ liệu không hợp lệ”, vì người dùng sẽ không biết thao tác cần thử lại hay liên hệ hỗ trợ.

## 3. Lỗi binding và validation trong flow view

Khi người dùng gửi form, Spring Web Flow bind dữ liệu vào model trước khi flow tiếp tục theo event. Nếu conversion thất bại, binding ghi nhận lỗi cho thuộc tính. Validation có thể bổ sung lỗi nghiệp vụ cho giá trị đã chuyển đổi. Với các lỗi này, hành vi thường là giữ người dùng ở view state hiện tại và hiển thị message phù hợp.

Ví dụ, một view state nhập ngày đặt lịch:

~~~xml
<view-state id="bookingDetails" view="booking/details">
    <binder>
        <binding property="booking.date"/>
        <binding property="booking.guestCount"/>
    </binder>

    <transition on="continue" to="review">
        <evaluate expression="bookingValidator.validate(
            flowRequestContext, messageContext)"/>
    </transition>
</view-state>
~~~

Validator có thể thêm lỗi vào MessageContext. Nếu ngày không parse được, binding đã có lỗi trước khi validation nghiệp vụ được thực hiện. Không nên bắt lỗi parse rồi gán một giá trị mặc định như ngày hiện tại, vì như vậy flow có thể tiếp tục với dữ liệu người dùng chưa hề nhập.

Thông báo nên gắn với mã trường và message code có thể dịch. Không hiển thị stack trace hoặc tên class exception cho người dùng. Khi có lỗi, view cần render lại dữ liệu đã nhập hợp lệ và chỉ rõ trường nào cần sửa.

## 4. Xử lý ngoại lệ nghiệp vụ bằng transition

Một số ngoại lệ là kết quả nghiệp vụ có thể dự đoán. Ví dụ, service kiểm tra tồn kho có thể ném InventoryUnavailableException khi sản phẩm vừa hết hàng. Trong trường hợp này, flow có thể định nghĩa một nhánh lỗi ngay tại action state thay vì để lỗi đi tới trang lỗi chung.

Ví dụ:

~~~xml
<action-state id="reserveInventory">
    <evaluate expression="inventoryService.reserve(
        flowScope.order)"/>
    <transition to="review"/>
    <transition
        on-exception="com.acme.checkout.InventoryUnavailableException"
        to="inventoryUnavailable"/>
</action-state>

<view-state id="inventoryUnavailable"
            view="checkout/inventory-unavailable">
    <transition on="changeItems" to="cart"/>
    <transition on="cancel" to="cancelled"/>
</view-state>
~~~

Transition có thuộc tính on-exception dùng để chọn nhánh khi action phát sinh loại exception được chỉ định. Cách này phù hợp với một ngoại lệ cụ thể có ý nghĩa nghiệp vụ và có state đích rõ ràng. Cần xác nhận cú pháp và hành vi theo phiên bản Spring Web Flow đang dùng, đặc biệt khi action được gọi từ một loại state khác.

Không nên khai báo một transition bắt mọi Exception rồi chuyển tới state thành công. Làm vậy có thể che lỗi lập trình, lỗi cấu hình hoặc lỗi dữ liệu nghiêm trọng. Chỉ bắt loại lỗi mà flow thực sự có thể xử lý và tiếp tục một cách an toàn.

Nếu action thực hiện ghi dữ liệu, hãy xác định ranh giới transaction. Khi exception xảy ra, transaction cần rollback theo chính sách phù hợp trước khi flow chuyển tới state thông báo. Đừng để state tiếp theo hiển thị “đã hủy” trong khi một phần thao tác ghi dữ liệu vẫn được commit.

## 5. FlowExecutionExceptionHandler cho lỗi của execution

Khi một lỗi cần được xử lý trong ngữ cảnh của flow execution, Spring Web Flow cung cấp abstraction FlowExecutionExceptionHandler. Handler có thể xác định exception nào nó xử lý và thực hiện hành động phục hồi trong RequestControlContext.

Một flow có thể đăng ký handler trong định nghĩa:

~~~xml
<flow>
    <exception-handler bean="checkoutFlowExceptionHandler"/>

    <!-- Các state và transition của checkout -->
</flow>
~~~

Tên phần tử và cách đăng ký cần khớp schema cùng phiên bản Spring Web Flow của ứng dụng. Bean handler phải nằm trong Spring application context được flow sử dụng.

Ví dụ cấu trúc handler:

~~~java
public class CheckoutFlowExceptionHandler
        implements FlowExecutionExceptionHandler {

    @Override
    public boolean canHandle(FlowExecutionException exception) {
        return hasCause(
                exception,
                InventoryUnavailableException.class);
    }

    @Override
    public void handle(
            FlowExecutionException exception,
            RequestControlContext context) {

        context.getFlashScope().put(
                "flowError",
                "Không thể giữ hàng ở thời điểm hiện tại.");

        // Chuyển tới phản hồi phục hồi phù hợp với ứng dụng.
        context.getExternalContext()
                .requestExternalRedirect("/checkout/problem");
    }

    private boolean hasCause(
            Throwable exception,
            Class<? extends Throwable> expectedType) {
        Throwable current = exception;
        while (current != null) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            if (current.getCause() == current) {
                break;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

Đây là cấu trúc minh họa; cách điều hướng cuối cùng phải phù hợp với URL mapping, FlowHandler và phiên bản API đang dùng. Handler nên chỉ nhận các lỗi mà nó hiểu. Nếu không thể xử lý, cần để lỗi tiếp tục tới cơ chế xử lý cấp cao hơn thay vì đánh dấu đã xử lý một cách giả tạo.

Một số nguyên tắc khi viết handler:

- Kiểm tra cause chain vì flow engine có thể bọc exception gốc trong FlowExecutionException.
- Chỉ đưa thông báo an toàn vào flash hoặc model; giữ chi tiết kỹ thuật trong log.
- Không lưu Throwable, request hoặc đối tượng tài nguyên vào flowScope.
- Bảo toàn dữ liệu nháp cần thiết nếu người dùng có thể tiếp tục.
- Không tự động retry một thao tác có side effect nếu chưa bảo đảm tính idempotent.
- Nếu handler thực hiện redirect, bảo đảm URL đích không tạo vòng lặp quay lại flow đang lỗi.

FlowExecutionExceptionHandler xử lý lỗi trong ngữ cảnh execution. Nó không phải là cơ chế thay thế toàn bộ exception resolver của Spring MVC.

## 6. FlowHandler và FlowHandlerAdapter ở ranh giới web

FlowHandlerAdapter là adapter của Spring MVC dành cho flow. Nó nhận request đã được FlowHandlerMapping ánh xạ và gọi FlowExecutor để khởi chạy hoặc tiếp tục flow. Khi flow kết thúc, adapter phối hợp với FlowHandler để xác định phản hồi HTTP hoặc view tiếp theo. Khi phát sinh FlowException ở ranh giới này, FlowHandler có thể cung cấp cách xử lý riêng.

FlowHandler hữu ích khi một flow cần hành vi web đặc thù:

- Xác định flow ID cho URL.
- Tạo input map từ request khi khởi chạy flow.
- Chọn URL hoặc view sau khi flow kết thúc.
- Tùy biến phản hồi khi flow phát sinh FlowException.

Ví dụ, một flow đặt lịch có thể chuyển tới trang chi tiết lịch hẹn khi kết thúc thành công. Nếu execution hết hạn, handler có thể điều hướng người dùng về trang bắt đầu đặt lịch với thông báo phù hợp. Không nên cố tiếp tục một execution đã không còn trong repository bằng cách tự tạo lại execution key cũ.

Không phải ứng dụng nào cũng cần custom FlowHandler. Cấu hình mặc định có thể đủ nếu các flow có hành vi outcome thống nhất. Chỉ tạo handler riêng khi có nhu cầu định tuyến hoặc phản hồi thực sự khác nhau.

## 7. Spring MVC HandlerExceptionResolver và @ControllerAdvice

Spring MVC dùng chuỗi HandlerExceptionResolver để xử lý ngoại lệ thoát ra từ handler. @ExceptionHandler trong @ControllerAdvice là cách phổ biến để định nghĩa phản hồi tập trung cho controller. Các cơ chế này vẫn hữu ích trong ứng dụng có Spring Web Flow, đặc biệt với controller thông thường, lỗi render view hoặc exception không được flow/FlowHandler xử lý và thực sự thoát ra DispatcherServlet.

Ví dụ:

~~~java
@ControllerAdvice
public class WebExceptionAdvice {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ModelAndView handleCustomerNotFound(
            CustomerNotFoundException exception) {

        ModelAndView model = new ModelAndView("errors/not-found");
        model.addObject(
                "message",
                "Không tìm thấy thông tin khách hàng.");
        return model;
    }

    @ExceptionHandler(Exception.class)
    public ModelAndView handleUnexpected(Exception exception) {
        String referenceId = UUID.randomUUID().toString();
        // Ghi exception cùng referenceId vào logger tại đây.

        ModelAndView model = new ModelAndView("errors/unexpected");
        model.addObject("referenceId", referenceId);
        return model;
    }
}
~~~

Ví dụ minh họa một handler cho controller thông thường và một fallback cho lỗi ngoài dự kiến. Trong ứng dụng thực tế, logger cần ghi stack trace, correlation ID, request path và thông tin chẩn đoán cần thiết theo chính sách bảo mật. Không đưa exception.getMessage() trực tiếp vào view vì thông điệp có thể chứa SQL, đường dẫn nội bộ hoặc dữ liệu nhạy cảm.

Một lưu ý quan trọng: @ControllerAdvice không bảo đảm sẽ nhận mọi exception phát sinh bên trong flow. FlowExecutionExceptionHandler hoặc FlowHandler có thể đã xử lý lỗi trước đó. MVC resolver chỉ xử lý exception mà DispatcherServlet nhận được sau khi handler adapter trả lỗi ra ngoài. Vì vậy, hãy kiểm thử đường đi thực tế của từng nhóm lỗi thay vì giả định annotation sẽ bắt tất cả.

Nếu cần cấu hình resolver tùy chỉnh, hãy kiểm tra thứ tự trong chuỗi HandlerExceptionResolver. Resolver trả về null thường có nghĩa là nó không xử lý exception và cho phép resolver tiếp theo thử. Resolver trả về một ModelAndView hoặc một phản hồi đã xử lý sẽ kết thúc quá trình resolution tương ứng.

## 8. Lỗi bảo mật và lỗi xảy ra trước DispatcherServlet

Một số request bị từ chối ngay trong servlet filter chain trước khi tới DispatcherServlet. Ví dụ, Spring Security có thể yêu cầu đăng nhập hoặc từ chối quyền truy cập. Những lỗi này cần được xử lý bằng AuthenticationEntryPoint hoặc AccessDeniedHandler theo loại lỗi, thay vì trông đợi flow exception handler hoặc @ControllerAdvice.

Với request flow:

- Chưa xác thực: chuyển tới trang đăng nhập hoặc cơ chế xác thực được cấu hình.
- Đã xác thực nhưng không đủ quyền: trả 403 hoặc trang từ chối truy cập phù hợp.
- Execution key thuộc flow khác hoặc không hợp lệ: không tiết lộ dữ liệu của execution đó.
- Người dùng quay lại URL cũ sau khi phiên hết hạn: cung cấp đường bắt đầu lại rõ ràng.

Không hiển thị flow ID, execution key, token bảo mật hoặc stack trace trong trang lỗi. Không dùng exception handler để bỏ qua kiểm tra authorization hoặc tự động khởi tạo một flow mới với dữ liệu nhạy cảm lấy từ request cũ.

## 9. Phục hồi khi execution hết hạn hoặc không còn tồn tại

Flow execution có vòng đời và được lưu/khôi phục thông qua FlowExecutionRepository. Khi người dùng mở lại một tab cũ, gửi lại request hoặc tiếp tục sau khi session hết hạn, execution key có thể không còn hợp lệ. Đây là tình huống phục hồi phiên, không phải lỗi validation và cũng không nhất thiết là lỗi nghiệp vụ.

Ứng dụng nên:

1. Nhận diện trường hợp execution không còn tồn tại hoặc đã hết hạn.
2. Ghi log thông tin chẩn đoán cần thiết mà không ghi token nhạy cảm ở dạng có thể bị lạm dụng.
3. Hiển thị thông báo rằng quy trình cũ không còn hoạt động.
4. Cung cấp đường bắt đầu lại hoặc tải lại dữ liệu nháp nếu nghiệp vụ cho phép.
5. Kiểm tra quyền truy cập và trạng thái dữ liệu khi người dùng bắt đầu execution mới.

Nếu dữ liệu nháp phải tồn tại lâu hơn session, hãy lưu draft vào kho dữ liệu riêng với TTL và chỉ giữ draft ID trong flow. Khi bắt đầu lại, service tải draft theo ID, kiểm tra chủ sở hữu và trạng thái trước khi cho phép tiếp tục.

Không nên cố tái sử dụng execution key cũ hoặc tạo một flow execution mới mà không kiểm tra dữ liệu. Làm vậy có thể tạo đơn hàng trùng, giữ chỗ trùng hoặc cho phép truy cập một draft không thuộc người dùng hiện tại.

## 10. Ghi log và phản hồi lỗi an toàn

Người dùng cần một thông báo ngắn gọn và bước tiếp theo có thể thực hiện. Nhóm vận hành cần đủ thông tin để tìm nguyên nhân. Hai mục tiêu này nên được đáp ứng bằng hai kênh riêng:

| Đối tượng | Nội dung nên nhận |
|---|---|
| Người dùng | Mô tả dễ hiểu, mã tham chiếu, cách thử lại hoặc liên hệ hỗ trợ |
| Log ứng dụng | Exception gốc, stack trace, flow ID, state ID, correlation ID và thời điểm |
| Monitoring | Tỷ lệ lỗi theo flow, loại exception, thời gian xử lý và số execution bị ảnh hưởng |

Không ghi password, access token, session ID, dữ liệu thanh toán hoặc toàn bộ nội dung form vào log. Nếu cần ghi định danh execution để điều tra, hãy tuân theo chính sách bảo mật và che hoặc băm các giá trị có thể dùng để tiếp tục phiên.

Một lỗi nên có correlation ID để nối log từ MVC, FlowHandlerAdapter, flow service và hệ thống bên ngoài. Nếu request được gửi qua nhiều service, truyền trace context theo cơ chế tracing của ứng dụng.

## 11. Retry, transaction và tính idempotent

Không phải ngoại lệ nào cũng nên cho người dùng bấm “Thử lại”. Retry có thể an toàn với thao tác đọc, nhưng thao tác ghi hoặc gọi hệ thống thanh toán có thể đã thành công ở phía ngoài dù response bị timeout.

Trước khi thiết kế retry, hãy xác định:

- Thao tác có side effect hay không.
- Transaction đã commit hay rollback.
- Hệ thống ngoài có hỗ trợ idempotency key hay không.
- Có thể truy vấn trạng thái thao tác trước khi gửi lại không.
- Dữ liệu trong flow còn mới và còn quyền sử dụng không.

Ví dụ, khi xác nhận đơn hàng, service nên dùng mã yêu cầu duy nhất hoặc khóa idempotency để tránh tạo hai đơn khi request được gửi lại. Flow chỉ chuyển tới state hoàn tất sau khi service xác nhận kết quả cuối cùng. Nếu timeout khiến trạng thái chưa rõ, đưa người dùng tới màn hình kiểm tra trạng thái thay vì lập tức gửi lại lệnh tạo đơn.

## 12. Kiểm thử exception ở từng ranh giới

Một bộ test tốt cần xác minh không chỉ trang lỗi mà cả nơi đã xử lý exception và trạng thái flow sau đó.

| Kịch bản | Cấp kiểm thử | Điều cần xác minh |
|---|---|---|
| Chuỗi ngày sai định dạng | Flow view binding | Người dùng ở lại view, lỗi gắn đúng trường |
| Validation nghiệp vụ thất bại | Flow test | Không chuyển tới state tiếp theo |
| InventoryUnavailableException trong action | Flow test | Chọn đúng transition hoặc flow exception handler |
| FlowExecutionException được handler nhận | Flow integration test | Handler nhận đúng loại lỗi, thông báo an toàn được đặt |
| Handler không nhận exception | Integration test | Lỗi tiếp tục tới lớp xử lý phù hợp |
| Exception thoát khỏi FlowHandlerAdapter | MVC integration test | HandlerExceptionResolver hoặc @ControllerAdvice tạo phản hồi |
| Flow execution hết hạn | Web integration test | Người dùng được hướng dẫn bắt đầu lại |
| Chưa đăng nhập hoặc không đủ quyền | Security integration test | Entry point/access-denied handler hoạt động |
| Timeout sau thao tác ghi | Service và flow test | Retry không tạo side effect trùng |
| Lỗi render view | MVC integration test | Có phản hồi lỗi phù hợp và log chứa correlation ID |

Ở cấp flow, kiểm tra state hiện tại trước và sau khi gửi event hoặc kích hoạt action lỗi. Ở cấp MVC, gửi request thật qua DispatcherServlet để xác minh adapter và exception resolver được gọi theo đúng thứ tự. Test trực tiếp phương thức @ExceptionHandler không đủ để chứng minh toàn bộ chuỗi MVC hoạt động.

## 13. Lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách điều chỉnh |
|---|---|---|
| Dùng @ControllerAdvice để xử lý mọi lỗi flow | Flow có thể đã xử lý exception trước khi MVC resolver nhận được | Đặt handler theo đúng tầng và kiểm thử đường exception thực tế |
| Bắt mọi Exception trong flow | Che lỗi lập trình và làm flow tiếp tục với trạng thái không an toàn | Chỉ bắt loại exception có ý nghĩa và nhánh phục hồi rõ ràng |
| Hiển thị exception.getMessage() | Rò rỉ SQL, đường dẫn, tên class hoặc dữ liệu nhạy cảm | Dùng message an toàn và mã tham chiếu |
| Retry mọi timeout | Có thể tạo thao tác ghi trùng | Kiểm tra trạng thái và dùng idempotency |
| Coi execution hết hạn là lỗi validation | Người dùng không thể tiếp tục và không hiểu phải làm gì | Cung cấp đường bắt đầu lại hoặc khôi phục draft |
| Bỏ qua rollback khi chuyển state lỗi | Dữ liệu có thể được ghi một phần | Thiết kế transaction và kiểm tra kết quả commit/rollback |
| Ghi toàn bộ request vào log | Lộ dữ liệu cá nhân hoặc token | Chỉ ghi metadata cần thiết và che dữ liệu nhạy cảm |

## 14. Quy trình thiết kế xử lý ngoại lệ

Khi thêm một thao tác có thể phát sinh lỗi vào flow, hãy thực hiện theo thứ tự:

1. Liệt kê các lỗi dự kiến từ binding, validation, nghiệp vụ, hệ thống ngoài và execution.
2. Phân loại lỗi nào người dùng có thể sửa, lỗi nào cần nhánh nghiệp vụ, lỗi nào phải thoát khỏi flow.
3. Với lỗi nghiệp vụ dự kiến, định nghĩa transition hoặc state phục hồi cụ thể.
4. Với lỗi execution, cân nhắc FlowExecutionExceptionHandler và chỉ nhận các loại lỗi mà handler hiểu.
5. Với lỗi thoát ra adapter, dùng FlowHandler hoặc Spring MVC exception resolution theo trách nhiệm của ứng dụng.
6. Với lỗi filter/security, cấu hình entry point và access-denied handler tương ứng.
7. Xác định transaction, rollback, retry và idempotency cho mọi thao tác có side effect.
8. Viết test ở đúng tầng để chứng minh exception được xử lý một lần và người dùng nhận được phản hồi phù hợp.

Khi review, cần trả lời được ba câu hỏi: lỗi phát sinh ở lớp nào, lớp nào chịu trách nhiệm xử lý cuối cùng, và flow/session còn ở trạng thái nào sau khi xử lý. Nếu không trả lời được, ranh giới exception handling chưa đủ rõ.

## Kết luận

Ở ranh giới MVC–Web Flow, xử lý ngoại lệ cần tôn trọng ngữ cảnh của từng lớp. Binding và validation lỗi nên quay về view state; lỗi nghiệp vụ dự kiến có thể đi qua transition; lỗi execution có thể cần FlowExecutionExceptionHandler; lỗi FlowException ở tích hợp web có thể cần FlowHandler; exception thực sự thoát khỏi adapter mới đi qua HandlerExceptionResolver hoặc @ControllerAdvice. Lỗi bảo mật xảy ra ở filter chain cần được xử lý bằng cơ chế bảo mật tương ứng.

Khi phân loại lỗi rõ ràng, bảo toàn dữ liệu cần thiết, quản lý transaction và retry đúng cách, đồng thời tách thông báo người dùng khỏi chi tiết log, ứng dụng có thể phục hồi flow một cách dễ hiểu mà vẫn giữ được tính an toàn và khả năng chẩn đoán.
