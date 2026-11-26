# Vòng đời thông báo qua render và redirect

Trong một hành trình Spring Web Flow, người dùng có thể gửi biểu mẫu, nhận lỗi kiểm tra, sửa dữ liệu rồi gửi lại. Ứng dụng cũng có thể cần thông báo rằng một thao tác đã hoàn tất sau khi flow chuyển sang màn hình tiếp theo. Những thông báo này phải gắn với đúng flow execution và xuất hiện ở đúng lần render, kể cả khi Spring Web Flow chuyển request theo mô hình POST–Redirect–GET.

Bài này thuộc chương **Thông báo và ngôn ngữ** của module **SPRING_WEB_FLOW**. Trọng tâm là vòng đời của thông báo qua các lần xử lý request, render view và redirect; cách dùng **MessageContext**, **flashScope** và mã thông báo đa ngôn ngữ để thông tin không biến mất quá sớm hoặc xuất hiện lặp lại ở màn hình không liên quan.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Phân biệt render view với redirect sang URL thực thi của flow.
- Giải thích vì sao redirect sau POST không đồng nghĩa với khởi chạy một flow mới.
- Tạo thông báo bằng **MessageContext** và **MessageBuilder** trong action hoặc transition.
- Hiển thị thông báo chung và thông báo gắn với một trường biểu mẫu.
- Chọn giữa **requestScope**, **flashScope**, **flowScope** và **MessageContext** theo vòng đời cần thiết.
- Dùng message code và MessageSource để hiển thị thông báo theo locale.
- Kiểm thử thông báo sau redirect, sau render và khi người dùng tiếp tục sang state khác.

## 1. Render và redirect là hai bước khác nhau

**Render** là lúc ứng dụng tạo nội dung view để trả về trình duyệt. **Redirect** là phản hồi HTTP yêu cầu trình duyệt gửi một request mới đến URL được chỉ định, thường thông qua mã trạng thái 3xx và header **Location**.

Trong một flow, người dùng thường gửi POST để phát ra event. Flow xử lý event, chạy action hoặc transition rồi tạm dừng tại view-state kế tiếp. Với cấu hình phổ biến, **FlowHandlerAdapter** chuyển trình duyệt đến URL thực thi của flow bằng redirect. Trình duyệt gửi GET đến URL đó, mang theo execution key để tiếp tục đúng flow execution đang tồn tại.

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant D as DispatcherServlet
    participant A as FlowHandlerAdapter
    participant F as FlowExecutor
    participant M as MessageContext
    participant V as View

    B->>D: POST URL execution + event
    D->>A: Chuyển request cho flow
    A->>F: Tiếp tục flow execution
    F->>F: Chạy action và transition
    F->>M: Ghi thông báo
    F-->>A: Flow pause tại view-state
    A-->>B: 3xx Location chứa execution key
    B->>D: GET URL execution
    D->>A: Tiếp tục cùng flow execution
    A->>F: Khôi phục trạng thái flow
    F->>V: Render view cùng message context
    V-->>B: HTML có thông báo
~~~

Redirect trong chuỗi này là một phần của flow execution. Nó không khởi chạy lại flow từ đầu. Execution key trong URL giúp Spring Web Flow tìm đúng execution để render view tiếp theo. Đây là cách áp dụng POST–Redirect–GET (PRG), hạn chế việc trình duyệt gửi lại POST khi người dùng tải lại trang sau khi gửi biểu mẫu.

Hành vi redirect có thể được tùy chỉnh trong cấu hình handler adapter. Khi cần chẩn đoán, hãy kiểm tra response thực tế, header **Location**, execution key và cấu hình redirect của ứng dụng thay vì giả định mọi request đều trả về cùng một mã trạng thái.

## 2. Chọn nơi lưu thông báo theo vòng đời

Spring Web Flow có nhiều nơi giữ dữ liệu. Mỗi nơi phục vụ một thời gian sống khác nhau:

| Cơ chế | Vòng đời | Dùng khi |
|---|---|---|
| **requestScope** | Trong request hiện tại. | Dữ liệu chỉ cần khi đang xử lý một request; không dùng để giữ thông báo qua redirect. |
| **flashScope** | Tạm thời cho view kế tiếp được render trong flow. | Một thông tin một lần cần xuất hiện ở màn hình tiếp theo rồi không tiếp tục chiếm chỗ trong flow. |
| **flowScope** | Trong suốt flow execution. | Trạng thái nghiệp vụ hoặc dữ liệu cần dùng qua nhiều bước. |
| **conversationScope** | Trong conversation của flow gốc và các subflow liên quan. | Ngữ cảnh cần chia sẻ giữa các flow execution trong cùng conversation. |
| **MessageContext** | Ngữ cảnh thông báo của flow execution, dùng để thêm, truy vấn và xóa message. | Lỗi validation, cảnh báo và thông tin cần hiển thị trong view của flow. |

Đừng dùng **flowScope** làm nơi lưu mọi thông báo. Nếu một thông báo chỉ có ý nghĩa ở màn hình kế tiếp, lưu nó như dữ liệu tạm trong **flashScope** hoặc tạo message cho view cần hiển thị. Nếu lưu một chuỗi thông báo lâu dài trong flow scope mà không quản lý thời điểm xóa, thông báo cũ có thể xuất hiện lại khi người dùng quay về state hoặc mở một màn hình khác.

**MessageContext** được thiết kế cho thông báo và có thể gắn message với một source, ví dụ tên trường **email**. **flashScope** phù hợp cho dữ liệu tạm thời cần được view kế tiếp đọc, chẳng hạn một cờ hoặc nội dung hiển thị một lần. Hai cơ chế có mục đích liên quan nhưng không thay thế hoàn toàn cho nhau.

## 3. Tạo thông báo bằng MessageContext

Trong action của Spring Web Flow, có thể lấy **MessageContext** từ **RequestContext**. **MessageBuilder** tạo message với severity, source và mã thông báo:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.webflow.execution.Event;
import org.springframework.webflow.execution.RequestContext;
import org.springframework.webflow.action.AbstractAction;
import com.example.booking.Booking;

public class SubmitBookingAction extends AbstractAction {

    @Override
    protected Event doExecute(RequestContext context) {
        MessageContext messages = context.getMessageContext();

        Booking booking = (Booking) context.getFlowScope().get("booking");

        if (booking == null || booking.getEmail() == null
                || booking.getEmail().isBlank()) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("email")
                    .code("booking.email.required")
                    .defaultText("Vui lòng nhập địa chỉ email.")
                    .build());

            return new Event(this, "error");
        }

        messages.addMessage(new MessageBuilder()
                .info()
                .code("booking.details.accepted")
                .defaultText("Thông tin đã được tiếp nhận.")
                .build());

        return new Event(this, "success");
    }
}
~~~

Các phần quan trọng:

- **getMessageContext()** lấy ngữ cảnh thông báo của request/flow hiện tại.
- **error()** đánh dấu thông báo lỗi; **info()** tạo thông báo thông tin.
- **source("email")** liên kết lỗi với trường email để view có thể hiển thị gần trường đó.
- **code(...)** cung cấp mã tra cứu trong MessageSource.
- **defaultText(...)** là nội dung dự phòng nếu không tìm thấy mã trong message bundle.
- **addMessage(...)** thêm thông báo vào MessageContext.

Ví dụ dùng **AbstractAction** để trả event **error** hoặc **success** cho flow quyết định state tiếp theo. Trong ứng dụng thực tế, hãy thay điều kiện minh họa bằng kiểm tra hợp lệ của đối tượng biểu mẫu và gọi dịch vụ nghiệp vụ ở thời điểm phù hợp.

Một thông báo thành công chỉ nên được thêm sau khi thao tác nghiệp vụ hoàn tất. Nếu dịch vụ ghi dữ liệu thất bại, hãy tạo thông báo lỗi phù hợp và đưa người dùng về state có thể xử lý tiếp, thay vì phát thông báo thành công trước khi biết kết quả.

## 4. Nối action với state và transition

Flow có thể định tuyến event submit đến action-state để kiểm tra dữ liệu. Nếu action trả về **error**, flow quay lại màn hình nhập; nếu trả về **success**, flow chuyển đến màn hình rà soát:

~~~xml
<var name="booking" class="com.example.booking.Booking"/>

<view-state id="edit" view="booking/edit" model="booking">
    <transition on="submit" to="validate"/>
</view-state>

<action-state id="validate">
    <evaluate expression="submitBookingAction"/>
    <transition on="success" to="review"/>
    <transition on="error" to="edit"/>
</action-state>

<view-state id="review" view="booking/review">
    <transition on="confirm" to="completed"/>
</view-state>

<end-state id="completed" view="booking/completed"/>
~~~

Khi action trả về **error**, flow quay lại view **edit**. Thông báo lỗi đã được thêm vào MessageContext và view có thể hiển thị khi được render lại. Khi action trả về **success**, thông báo thông tin có thể được hiển thị ở view **review**.

Trong ví dụ trên, bean **submitBookingAction** phải được đăng ký trong Spring context và có thể được biểu thức của flow truy cập. Nếu dùng tên bean khác, hãy cập nhật expression tương ứng. Việc chuyển đến action-state không tự làm mất flow execution; request tiếp theo vẫn tiếp tục cùng execution nếu flow pause và handler adapter thực hiện redirect.

## 5. Hiển thị thông báo trong view

Với JSP, view có thể đọc message context từ **flowRequestContext**. Ví dụ minh họa:

~~~jsp
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>

<c:forEach
    items="${flowRequestContext.messageContext.allMessages}"
    var="message">

    <div class="message">
        <c:out value="${message.text}"/>
    </div>
</c:forEach>
~~~

Đây là vùng hiển thị thông báo chung. Nếu cần phân biệt severity, view có thể đọc thuộc tính severity của message để gắn class CSS phù hợp. Hãy kiểm tra kiểu severity và cách expose message của phiên bản Spring Web Flow đang dùng khi xây dựng view cụ thể.

Thông báo gắn với trường có thể được trình bày gần input tương ứng. Ví dụ, message có source **email** được dùng để giải thích vì sao trường email chưa hợp lệ. Nếu ứng dụng dùng Spring form tag và BindingResult cho lỗi binding/validation của form, có thể dùng **form:errors** cho những lỗi đó; message do MessageContext tạo ra cần được render từ message context theo cách riêng.

Không nên đưa nguyên văn nội dung do người dùng nhập vào HTML như markup. Hãy escape đầu ra, ví dụ dùng **c:out**, để tránh diễn giải nội dung không tin cậy thành HTML hoặc script.

## 6. Thông báo qua redirect và flashScope

Khi action thêm message rồi flow pause tại view-state, redirect có thể đưa trình duyệt đến URL execution mới. Vì request GET tiếp tục cùng flow execution, view kế tiếp có thể đọc thông báo đã được tạo trong quá trình xử lý event.

**requestScope** không thích hợp cho thông báo cần qua redirect: request sau là một request mới, nên dữ liệu gắn với request trước không còn là nơi lưu trữ đáng tin cậy. Với một thông tin một lần khác ngoài MessageContext, có thể đặt giá trị vào **flashScope**:

~~~xml
<set name="flashScope.notice"
     value="'Hồ sơ đã được lưu thành công.'"/>
~~~

View kế tiếp có thể đọc **flashScope.notice** để hiển thị. Flash scope dành cho dữ liệu tạm thời đến lần render kế tiếp; đừng dựa vào nó để lưu trạng thái nghiệp vụ qua nhiều state. Nếu thông tin cần tồn tại qua nhiều bước, hãy lưu trạng thái nghiệp vụ trong flow scope và tạo thông báo phù hợp ở từng màn hình.

Nếu flow redirect ra một URL MVC bên ngoài flow, MessageContext của flow không tự trở thành flash attribute của controller đích. Khi cần chuyển một thông báo qua redirect MVC, hãy dùng cơ chế flash attribute của Spring MVC, chẳng hạn **RedirectAttributes.addFlashAttribute(...)**, hoặc một cơ chế chuyển giao thông báo được ứng dụng thiết kế rõ ràng.

## 7. Quản lý thông báo để không xuất hiện lặp lại

Thông báo nên gắn với một kết quả cụ thể và một thời điểm hiển thị. Lỗi validation có thể cần tồn tại cho đến khi người dùng thấy và sửa trường bị lỗi. Thông báo thành công thường chỉ có ý nghĩa ở màn hình ngay sau thao tác lưu. Cảnh báo có thể cần ở nhiều màn hình nếu điều kiện nghiệp vụ vẫn còn hiệu lực, nhưng khi đó nên mô hình hóa cảnh báo như trạng thái có chủ đích thay vì để message cũ tồn tại vô thời hạn.

MessageContext cung cấp các thao tác truy vấn và xóa message. Ví dụ, có thể kiểm tra có lỗi hay không bằng **hasErrorMessages()**, lấy toàn bộ message bằng **getAllMessages()**, lọc theo source bằng **getMessagesBySource(...)**, hoặc xóa message bằng **clearMessages()** và **clearMessagesBySource(...)** khi ứng dụng cần chủ động dọn thông báo.

Không nên xóa message quá sớm, trước khi view có cơ hội hiển thị. Ngược lại, nếu một action tái sử dụng execution và thêm lại cùng một thông báo ở mỗi request, người dùng có thể thấy thông báo trùng. Hãy xác định rõ nơi tạo message, view nào tiêu thụ message và điểm nào cần xóa hoặc thay thế.

Một số quy tắc thực hành:

- Thêm lỗi validation khi kiểm tra dữ liệu thất bại và giữ người dùng ở view có thể sửa dữ liệu.
- Chỉ thêm thông báo thành công sau khi dịch vụ nghiệp vụ xác nhận thao tác hoàn tất.
- Dùng flashScope cho dữ liệu một lần cần xuất hiện ở view kế tiếp.
- Dùng flowScope cho trạng thái nghiệp vụ, không dùng nó làm hộp thư thông báo.
- Xóa thông báo theo source khi người dùng đã sửa trường tương ứng nếu quy trình cần loại bỏ lỗi cũ.
- Khi rời flow, không dựa vào message của execution cũ để hiển thị ở một flow mới.

## 8. Kết hợp MessageSource và locale

Mã thông báo giúp tách nội dung hiển thị khỏi logic xử lý. Ví dụ, action dùng mã **booking.email.required**; nội dung cụ thể được tra trong message bundle theo locale hiện tại.

Tệp **messages.properties**:

~~~properties
booking.email.required=Please enter an email address.
booking.details.accepted=Your details have been received.
~~~

Tệp **messages_vi.properties**:

~~~properties
booking.email.required=Vui lòng nhập địa chỉ email.
booking.details.accepted=Thông tin của bạn đã được tiếp nhận.
~~~

Cấu hình ứng dụng cần cung cấp **MessageSource** để Spring có thể phân giải mã thông báo. Locale được chọn theo chiến lược của ứng dụng, chẳng hạn locale của request hoặc lựa chọn ngôn ngữ đã lưu trong phiên. Nếu người dùng đổi ngôn ngữ giữa các bước, hãy xác định thông báo đang giữ là mã chưa phân giải hay văn bản đã phân giải để biết nó có được hiển thị theo locale mới hay không.

Với **MessageBuilder**, dùng **code(...)** cùng **defaultText(...)** để có nội dung dự phòng. Cách này giúp ứng dụng vẫn có thể đưa ra thông báo có nghĩa khi message bundle thiếu một mã, đồng thời cho phép nội dung được dịch mà không phải sửa action.

Thông báo nên ngắn gọn, chỉ rõ điều gì đã xảy ra và người dùng có thể làm gì tiếp theo. Tránh đưa dữ liệu cá nhân, token, mã bí mật hoặc thông tin nội bộ vào thông báo gửi đến trình duyệt.

## 9. Kiểm thử vòng đời thông báo

Kiểm thử không nên dừng ở việc action đã gọi **addMessage**. Cần xác nhận thông báo có xuất hiện đúng view sau redirect và không bị lặp lại ở màn hình không liên quan.

| Tình huống | Kết quả cần xác nhận |
|---|---|
| POST submit có lỗi validation | Flow quay về view nhập; message lỗi xuất hiện đúng trường hoặc vùng thông báo. |
| POST submit hợp lệ | Flow chuyển đến view tiếp theo; thông báo thông tin xuất hiện ở đúng nơi. |
| Redirect sau transition | GET dùng execution key tiếp tục cùng flow và view đọc được message dự kiến. |
| Tải lại view sau khi đã hiển thị | Thông báo một lần không xuất hiện lại ngoài chủ đích của ứng dụng. |
| Chuyển sang state khác | Message cũ không gây nhầm lẫn với kết quả của state mới. |
| Dùng flashScope | Giá trị tạm được đọc ở lần render kế tiếp và không bị dùng như dữ liệu lâu dài. |
| Đổi locale | Message code được phân giải theo locale mà ứng dụng đang áp dụng. |
| Redirect ra controller MVC | Thông báo được chuyển bằng flash attribute hoặc cơ chế được thiết kế riêng; không giả định MessageContext tự đi theo. |

Với **MockMvc**, có thể gửi POST đến URL execution, kiểm tra response redirect và tiếp tục GET đến URL trong **Location**. Giữ cùng session/cookie trong toàn bộ chuỗi request. Assertion nên kiểm tra nội dung thông báo, source nếu cần, locale và việc message không xuất hiện ở state tiếp theo ngoài dự kiến.

Cũng nên kiểm thử trường hợp action thêm nhiều message, lỗi binding đồng thời với lỗi nghiệp vụ, người dùng nhấn submit lặp và request bị gửi lại. Những tình huống này giúp phát hiện thông báo trùng, message cũ hoặc thông báo thành công được tạo sai thời điểm.

## 10. Nguyên tắc thiết kế lâu dài

Hãy tạo thông báo tại nơi biết rõ kết quả nghiệp vụ, gắn lỗi với source khi có thể, và để view chịu trách nhiệm trình bày thông báo theo locale hiện tại. Dùng MessageContext cho lỗi và thông tin gắn với quá trình thực thi flow; dùng flashScope cho dữ liệu một lần ở view kế tiếp; dùng flowScope cho trạng thái nghiệp vụ cần qua nhiều bước.

Khi flow pause và redirect, hãy nhớ rằng trình duyệt gửi một request mới nhưng execution key vẫn trỏ về flow execution đang tiếp tục. Kiểm thử cả response redirect lẫn lần render kế tiếp để chắc chắn thông báo đến đúng nơi. Khi redirect ra ngoài flow, chủ động chuyển thông báo bằng cơ chế flash của Spring MVC. Cách phân chia rõ ràng này giúp thông báo không biến mất giữa các bước, không bị lưu quá lâu và có thể hiển thị đúng ngôn ngữ người dùng chọn.
