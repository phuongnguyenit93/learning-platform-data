# Chuyển dữ liệu kết quả sang flash attributes của MVC

Một flow Spring Web Flow có thể hoàn tất một quy trình nhiều bước rồi chuyển người dùng sang một trang Spring MVC thông thường. Trang đích thường cần biết kết quả vừa xảy ra để hiển thị thông báo như “Đặt chỗ đã được xác nhận” hoặc “Yêu cầu đã được hủy”. Dữ liệu này chỉ cần tồn tại trong lần chuyển hướng kế tiếp, vì vậy MVC flash attributes là một cơ chế phù hợp.

Trong module **SPRING_WEB_FLOW**, flow điều phối state, event, transition và subflow; Spring MVC tiếp nhận các URL và render những trang ứng dụng thông thường. Bài học này trình bày cách xuất dữ liệu từ end-state, đọc kết quả trong FlowHandler, chuyển dữ liệu vào FlashMap của Spring MVC và nhận dữ liệu đó ở request sau redirect. Ta cũng sẽ phân biệt flash attributes của MVC với flash scope của Spring Web Flow, chọn dữ liệu nên truyền và kiểm thử vòng đời một lần chuyển hướng.

## 1. Vì sao cần chuyển kết quả qua MVC flash attributes?

Giả sử người dùng hoàn thành flow đặt chỗ. Flow đã xác nhận đặt chỗ và lưu bản ghi trong cơ sở dữ liệu. Sau đó ứng dụng muốn chuyển người dùng đến trang chi tiết đặt chỗ do một controller MVC xử lý.

Trang đích có thể cần hai loại dữ liệu:

- **Dữ liệu bền vững**, chẳng hạn mã đặt chỗ, để tải thông tin chi tiết từ service hoặc repository.
- **Thông báo tạm thời**, chẳng hạn “Đặt chỗ đã được xác nhận”, chỉ cần hiển thị ngay sau khi chuyển hướng.

Không nên giữ toàn bộ đối tượng đặt chỗ trong URL. URL nên mang định danh hoặc các tham số điều hướng cần thiết. Thông báo tạm thời có thể được gửi qua flash attributes để trang MVC nhận ở request kế tiếp.

Mô hình xử lý:

1. Root flow kết thúc tại một end-state.
2. End-state xuất một số giá trị qua output.
3. Spring Web Flow tạo kết quả kết thúc, chứa ID end-state và các output.
4. FlowHandler đọc kết quả đó và quyết định URL đích.
5. FlowHandler ghi thông báo hoặc dữ liệu ngắn hạn vào output FlashMap của Spring MVC.
6. Trình duyệt được redirect đến URL đích.
7. Spring MVC nhận input FlashMap phù hợp với request mới và đưa các thuộc tính đó vào model của trang.

Flash attributes giúp nối hai request HTTP mà không phải thêm thông báo tạm vào query string hoặc lưu nó lâu dài trong flow scope.

## 2. Phân biệt ba loại dữ liệu và scope

Spring Web Flow và Spring MVC có các cơ chế lưu dữ liệu với vòng đời khác nhau. Tên gọi gần giống nhau nhưng phạm vi và mục đích không giống nhau.

| Cơ chế | Nơi quản lý | Vòng đời | Mục đích |
|---|---|---|---|
| Flow scope | Spring Web Flow | Trong flow session | Dữ liệu cần cho các state trong cùng flow |
| Conversation scope | Spring Web Flow | Trong root flow execution và các flow lồng nhau | Dữ liệu cần chia sẻ giữa flow cha và subflow |
| MVC FlashMap | Spring MVC | Một lần chuyển hướng đến request phù hợp | Thông báo hoặc dữ liệu ngắn hạn cho trang đích |
| HTTP session | Servlet container | Theo vòng đời session | Dữ liệu phiên đăng nhập hoặc dữ liệu ứng dụng có phạm vi phiên |

**Flash scope của Spring Web Flow** là scope của flow execution. **FlashMap của Spring MVC** là cơ chế truyền dữ liệu qua redirect trong Spring MVC. Hai cơ chế này không tự động đồng bộ với nhau.

Nếu dữ liệu chỉ cần dùng trong các state của flow, hãy giữ nó trong flow scope. Khi root flow kết thúc và ứng dụng chuyển sang một controller MVC, hãy xuất dữ liệu cần thiết từ end-state và đưa những thuộc tính tạm thời vào MVC FlashMap.

Không nên xem MVC flash attributes là kho lưu trữ lâu dài. Chúng phục vụ request đích tiếp theo; sau khi được request phù hợp nhận, dữ liệu sẽ được tiêu thụ và không còn sẵn cho các lần tải trang sau.

## 3. Xuất dữ liệu từ end-state

Để FlowHandler nhận được kết quả nghiệp vụ, root flow cần khai báo output ở end-state. Ví dụ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      start-state="bookingForm">

    <var name="booking" class="com.example.Booking" />

    <view-state id="bookingForm" view="bookingForm">
        <transition on="submit" to="confirmBooking" />
    </view-state>

    <action-state id="confirmBooking">
        <evaluate expression="bookingService.confirm(flowScope.booking)" />
        <transition on="success" to="bookingConfirmed" />
        <transition on="invalid" to="bookingForm" />
    </action-state>

    <end-state id="bookingConfirmed">
        <output name="bookingId" value="flowScope.booking.id" />
        <output name="resultCode" value="'BOOKING_CONFIRMED'" />
    </end-state>
</flow>
~~~

Khi root flow kết thúc ở end-state bookingConfirmed, kết quả kết thúc có:

- ID của end-state: bookingConfirmed.
- Output bookingId: định danh của bản ghi đã được xác nhận.
- Output resultCode: mã kết quả nghiệp vụ đã chọn.

Output được khai báo rõ ràng giúp FlowHandler chỉ nhận những giá trị cần thiết. Không nên xuất toàn bộ flow scope hoặc toàn bộ entity graph chỉ để hiển thị một thông báo.

Nếu có nhánh hủy, có thể khai báo end-state riêng:

~~~xml
<end-state id="bookingCancelled">
    <output name="resultCode" value="'BOOKING_CANCELLED'" />
</end-state>
~~~

Nhờ có end-state riêng, FlowHandler có thể phân biệt hoàn tất với hủy và chọn thông báo, URL đích phù hợp.

## 4. FlowExecutionOutcome là kết quả mà FlowHandler nhận

Khi root flow kết thúc, Spring Web Flow tạo một đối tượng FlowExecutionOutcome. Đối tượng này cung cấp thông tin về flow đã kết thúc, ID kết quả và các output được khai báo tại end-state.

FlowHandler là điểm tích hợp cho ứng dụng muốn tùy chỉnh cách xử lý khi một flow hoàn tất. Trong Spring Web Flow MVC, có thể mở rộng AbstractFlowHandler và ghi đè phương thức handleExecutionOutcome.

Ví dụ:

~~~java
import org.springframework.webflow.execution.FlowExecutionOutcome;
import org.springframework.webflow.mvc.servlet.AbstractFlowHandler;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleExecutionOutcome(
            FlowExecutionOutcome outcome,
            HttpServletRequest request,
            HttpServletResponse response) {

        if ("bookingConfirmed".equals(outcome.getId())) {
            Object bookingId = outcome.getOutput().get("bookingId");

            String target = "/bookings/" + bookingId;

            // Ghi flash attributes và lưu FlashMap trước redirect.
            // Phần xử lý FlashMap được minh họa ở mục tiếp theo.

            return "redirect:" + target;
        }

        if ("bookingCancelled".equals(outcome.getId())) {
            return "redirect:/bookings";
        }

        return "redirect:/";
    }
}
~~~

Ví dụ dùng namespace jakarta.servlet của Spring Framework 6 trở lên. Với ứng dụng Spring cũ dùng Servlet API trước Jakarta, hãy thay bằng namespace javax.servlet tương ứng.

FlowHandler nhận FlowExecutionOutcome sau khi root flow kết thúc. Nếu flow cha gọi subflow, việc subflow kết thúc chỉ trả event và output về flow cha; nó không làm FlowHandler của root execution xử lý kết quả cuối cùng ngay tại thời điểm đó.

Phương thức handleExecutionOutcome trả về một đích điều hướng. Chuỗi có tiền tố redirect: yêu cầu tích hợp MVC thực hiện redirect đến URL tương ứng. Ứng dụng có thể chọn đích khác nhau theo ID end-state và output.

## 5. Ghi output FlashMap trước khi redirect

Spring MVC cung cấp FlashMap để lưu các thuộc tính sẽ được chuyển sang request đích. Trong FlowHandler, có thể lấy output FlashMap từ request bằng RequestContextUtils, thêm thuộc tính rồi lưu nó gắn với URL đích.

Ví dụ hoàn chỉnh:

~~~java
import org.springframework.webflow.execution.FlowExecutionOutcome;
import org.springframework.webflow.mvc.servlet.AbstractFlowHandler;
import org.springframework.web.servlet.FlashMap;
import org.springframework.web.servlet.support.RequestContextUtils;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleExecutionOutcome(
            FlowExecutionOutcome outcome,
            HttpServletRequest request,
            HttpServletResponse response) {

        if ("bookingConfirmed".equals(outcome.getId())) {
            Object bookingId = outcome.getOutput().get("bookingId");

            if (bookingId == null) {
                return "redirect:/bookings";
            }

            String target = "/bookings/" + bookingId;

            FlashMap flashMap =
                RequestContextUtils.getOutputFlashMap(request);

            flashMap.put(
                "notice",
                "Đặt chỗ đã được xác nhận thành công."
            );
            flashMap.put("resultCode", "BOOKING_CONFIRMED");

            RequestContextUtils.saveOutputFlashMap(
                target,
                request,
                response
            );

            return "redirect:" + target;
        }

        if ("bookingCancelled".equals(outcome.getId())) {
            String target = "/bookings";

            FlashMap flashMap =
                RequestContextUtils.getOutputFlashMap(request);

            flashMap.put("notice", "Đặt chỗ đã được hủy.");

            RequestContextUtils.saveOutputFlashMap(
                target,
                request,
                response
            );

            return "redirect:" + target;
        }

        return "redirect:/";
    }
}
~~~

Có ba thao tác quan trọng:

1. Gọi getOutputFlashMap(request) để lấy FlashMap dành cho response redirect hiện tại.
2. Gọi put để thêm các thuộc tính cần chuyển.
3. Gọi saveOutputFlashMap(target, request, response) để lưu FlashMap và gắn nó với URL đích trước khi trả kết quả redirect.

Đích truyền vào saveOutputFlashMap phải tương ứng với URL redirect thực tế. Việc gắn đường dẫn và tham số đích giúp Spring MVC tìm đúng FlashMap cho request tiếp theo. Hãy dùng cùng một giá trị target cho thao tác lưu và redirect để tránh sai lệch.

RequestContextUtils làm việc với FlashMapManager đã được tích hợp trong DispatcherServlet. Với cấu hình MVC thông thường, Spring MVC quản lý việc lưu và lấy FlashMap. Nếu ứng dụng tùy chỉnh FlashMapManager hoặc DispatcherServlet, cần bảo đảm FlowHandler và controller đích dùng cùng cơ chế quản lý.

## 6. Nhận flash attributes ở controller MVC

Sau redirect, request đến URL đích được xử lý như một request MVC thông thường. Spring MVC đưa input FlashMap phù hợp vào model của request đích.

Ví dụ controller:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
public class BookingController {

    private final BookingService bookingService;

    public BookingController(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    @GetMapping("/bookings/{bookingId}")
    public String show(
            @PathVariable Long bookingId,
            Model model) {

        Booking booking =
            bookingService.findVisibleToCurrentUser(bookingId);

        model.addAttribute("booking", booking);

        return "booking/detail";
    }
}
~~~

Các flash attributes như notice và resultCode được Spring MVC đưa vào model khi request đích khớp với FlashMap đã lưu. View có thể đọc thuộc tính notice để hiển thị thông báo.

Controller vẫn cần tải dữ liệu nghiệp vụ từ service bằng bookingId và kiểm tra quyền của người dùng hiện tại. Flash attribute bookingId hoặc resultCode không phải bằng chứng rằng người dùng được phép xem bản ghi.

Nếu cần đọc flash attributes trực tiếp trong controller hoặc thành phần xử lý request, có thể dùng RequestContextUtils:

~~~java
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.servlet.support.RequestContextUtils;

public void inspectFlashAttributes(HttpServletRequest request) {
Map<String, ?> inputFlashMap =
    RequestContextUtils.getInputFlashMap(request);

if (inputFlashMap != null) {
    Object notice = inputFlashMap.get("notice");
}
}
~~~

Ví dụ dùng namespace jakarta.servlet của Spring Framework 6 trở lên; với phiên bản cũ, thay bằng javax.servlet tương ứng. Thông thường không cần truy cập thủ công vì Spring MVC đã đưa input flash attributes vào model.

## 7. Đăng ký FlowHandler với FlowHandlerMapping

Custom FlowHandler cần được ánh xạ với Flow ID mà nó xử lý. Trong cấu hình Spring Web Flow MVC, FlowHandlerMapping chịu trách nhiệm ánh xạ URL flow và handler; FlowHandlerAdapter thực thi flow và xử lý kết quả.

Một cấu hình XML thường có dạng:

~~~xml
<bean id="bookingFlowHandler"
      class="com.example.web.BookingFlowHandler" />

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry" />
    <property name="order" value="0" />
    <property name="flowHandlers">
        <map>
            <entry key="booking" value-ref="bookingFlowHandler" />
        </map>
    </property>
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
~~~

Trong ví dụ, Flow ID booking được ánh xạ đến BookingFlowHandler. Cần bảo đảm flow registry có định nghĩa booking và FlowHandlerMapping/FlowHandlerAdapter được đăng ký trong cùng cấu hình MVC phục vụ ứng dụng.

Tên thuộc tính cấu hình và cách đăng ký handler cần được đối chiếu với phiên bản Spring Web Flow mà dự án sử dụng. Nếu dùng Java configuration, hãy cấu hình mapping tương đương và bảo đảm handler được chọn cho đúng Flow ID.

Không cần tạo một FlowHandler riêng cho mọi flow nếu các flow có cùng chính sách điều hướng. Có thể dùng handler mặc định hoặc một handler chung có phân nhánh theo outcome ID. Khi nhiều flow có quy tắc khác nhau về URL và flash attributes, handler riêng giúp hợp đồng rõ ràng hơn.

## 8. Chọn dữ liệu nào để đưa vào FlashMap?

FlashMap nên chứa dữ liệu nhỏ, có vòng đời ngắn và phục vụ trực tiếp cho request đích.

| Dữ liệu | Có nên đưa vào FlashMap? | Cách xử lý |
|---|---|---|
| Thông báo thành công hoặc hủy | Có | Dùng một thuộc tính như notice |
| Mã kết quả ngắn | Có thể | Dùng khi trang đích cần chọn cách hiển thị |
| ID bản ghi vừa tạo | Có thể, nếu URL chưa có ID | Thường đặt ID trong URL hoặc output điều hướng |
| Toàn bộ entity | Không nên | Trang đích tải lại qua service |
| Danh sách lớn | Không nên | Truy vấn tại controller đích |
| Password, token, dữ liệu xác thực | Không | Không đưa bí mật vào flash attributes |
| Dữ liệu cần giữ nhiều ngày | Không | Lưu trong cơ sở dữ liệu hoặc kho bền vững |

Nếu URL đã có bookingId trong path, controller có thể dùng path variable để tải dữ liệu. Không cần lặp lại cùng ID trong FlashMap trừ khi có lý do cụ thể.

Một thông báo đơn giản thường đủ:

~~~java
flashMap.put("notice", "Đặt chỗ đã được xác nhận.");
~~~

Nếu view cần phân biệt nhiều loại kết quả, có thể thêm mã kết quả:

~~~java
flashMap.put("resultCode", "BOOKING_CONFIRMED");
~~~

Không nên dùng flash attributes để chuyển cả đối tượng flow hoặc dữ liệu nội bộ của execution. Điều đó làm tăng kích thước session, tạo phụ thuộc giữa flow và MVC, và khiến trang đích khó kiểm soát dữ liệu cần hiển thị.

## 9. FlashMap được tiêu thụ khi nào?

FlashMap là dữ liệu tạm cho một request tiếp theo phù hợp. Khi lưu output FlashMap, Spring MVC có thể gắn thông tin target path và query parameters để xác định request đích. Khi request khớp đến, FlashMap được lấy làm input và sau đó được loại khỏi kho lưu trữ flash.

Vòng đời minh họa:

~~~mermaid
sequenceDiagram
    participant F as Root Flow
    participant H as FlowHandler
    participant M as MVC FlashMapManager
    participant B as Browser
    participant C as MVC Controller

    F->>H: Root flow kết thúc + FlowExecutionOutcome
    H->>H: Đọc outcome ID và output
    H->>M: Ghi notice vào output FlashMap
    H->>M: Lưu FlashMap với URL đích
    H-->>B: Redirect đến /bookings/42
    B->>C: GET /bookings/42
    C->>M: MVC lấy input FlashMap phù hợp
    M-->>C: notice và resultCode
    C->>C: Tải booking bằng ID và kiểm tra quyền
    C-->>B: Render trang chi tiết với thông báo
~~~

FlashMap được thiết kế cho mô hình Post/Redirect/Get. Người dùng refresh trang GET đích thường không nhận lại cùng thông báo flash vì FlashMap đã được tiêu thụ ở request phù hợp đầu tiên.

Nếu người dùng mở một URL khác trước khi request đích xảy ra, FlashMap có thể vẫn chờ một request khớp hoặc hết hạn theo cơ chế quản lý. Vì vậy, không nên dựa vào flash attributes cho dữ liệu mà người dùng cần truy cập lại bằng bookmark hoặc mở ở tab khác.

## 10. Phân biệt flash attributes với query parameters và session attributes

Có ba cách thường được cân nhắc khi chuyển thông tin sang trang MVC:

| Cách truyền | Dữ liệu xuất hiện ở đâu? | Vòng đời | Phù hợp với |
|---|---|---|---|
| Query parameter | URL và lịch sử trình duyệt | Có thể tồn tại trong bookmark/chia sẻ URL | Bộ lọc, phân trang, ID điều hướng không nhạy cảm |
| Flash attribute | Kho flash của MVC, request đích nhận trong model | Một lần chuyển hướng phù hợp | Thông báo, mã kết quả tạm |
| Session attribute | HTTP session | Nhiều request cho đến khi xóa hoặc hết session | Trạng thái cần tồn tại qua nhiều màn hình |

Ví dụ, bookingId thường phù hợp với path variable:

~~~text
/bookings/42
~~~

Thông báo kết quả phù hợp với flash attribute:

~~~text
notice = "Đặt chỗ đã được xác nhận."
~~~

Nếu cần lưu bộ lọc tìm kiếm để người dùng bookmark, hãy dùng query parameters. Nếu cần giữ tùy chọn trong suốt phiên đăng nhập, cân nhắc session hoặc kho lưu trữ phù hợp. Không nên dùng FlashMap như một session attribute dài hạn.

## 11. Xử lý outcome thành công, hủy và lỗi

Flow có thể kết thúc theo nhiều kết quả. FlowHandler nên xử lý từng outcome theo ý nghĩa nghiệp vụ.

~~~java
@Override
public String handleExecutionOutcome(
        FlowExecutionOutcome outcome,
        HttpServletRequest request,
        HttpServletResponse response) {

    if ("bookingConfirmed".equals(outcome.getId())) {
        return redirectWithNotice(
            "/bookings",
            "Đặt chỗ đã được xác nhận.",
            request,
            response
        );
    }

    if ("bookingCancelled".equals(outcome.getId())) {
        return redirectWithNotice(
            "/bookings",
            "Đặt chỗ đã được hủy.",
            request,
            response
        );
    }

    if ("bookingRejected".equals(outcome.getId())) {
        return redirectWithNotice(
            "/bookings",
            "Yêu cầu không đáp ứng điều kiện.",
            request,
            response
        );
    }

    return "redirect:/";
}
~~~

Phương thức trợ giúp:

~~~java
private String redirectWithNotice(
        String target,
        String message,
        HttpServletRequest request,
        HttpServletResponse response) {

    FlashMap flashMap =
        RequestContextUtils.getOutputFlashMap(request);

    flashMap.put("notice", message);

    RequestContextUtils.saveOutputFlashMap(
        target,
        request,
        response
    );

    return "redirect:" + target;
}
~~~

Trong ứng dụng thực tế, có thể đưa mã kết quả hoặc ID bản ghi vào FlashMap nếu trang đích cần. Không nên hiển thị một thông báo thành công khi outcome là lỗi hoặc khi service chưa xác nhận giao dịch đã hoàn tất.

Nếu root flow kết thúc do exception, việc xử lý đi qua cơ chế handleException của FlowHandler hoặc cơ chế xử lý lỗi chung. Không nên giả định mọi lỗi đều tạo FlowExecutionOutcome bình thường. Hãy phân biệt lỗi kỹ thuật, từ chối nghiệp vụ và hủy do người dùng để trang đích đưa ra thông báo chính xác.

## 12. Các lưu ý về URL đích và request đồng thời

FlashMap có thể được gắn với target path và query parameters. Hãy lưu nó cho đúng URL mà trình duyệt sẽ truy cập.

Nếu hai hành trình khác nhau cùng redirect đến một URL chung, chẳng hạn /bookings, trong cùng session và gần cùng thời điểm, việc gắn target path đơn thuần có thể chưa đủ để phân biệt ý định hiển thị. Có thể thêm query parameter không nhạy cảm như tab hoặc resultCode vào URL đích để FlashMap được gắn với request cụ thể hơn.

Ví dụ:

~~~java
String target = "/bookings?result=created";

FlashMap flashMap =
    RequestContextUtils.getOutputFlashMap(request);

flashMap.put("notice", "Đã tạo đặt chỗ.");

RequestContextUtils.saveOutputFlashMap(
    target,
    request,
    response
);

return "redirect:" + target;
~~~

Nếu URL có query parameters, saveOutputFlashMap sử dụng chúng để xác định request đích. Hãy bảo đảm URL trong thao tác lưu và URL redirect là cùng một đích.

Không đưa thông tin bí mật vào query string chỉ để phân biệt FlashMap. Query string có thể xuất hiện trong lịch sử trình duyệt, log máy chủ, analytics và referrer. Chỉ dùng các giá trị điều hướng không nhạy cảm.

## 13. Những giới hạn cần nhớ

MVC flash attributes có ích nhưng có phạm vi rõ ràng:

- Chúng không phải kho dữ liệu bền vững và không thay thế database.
- Chúng chỉ dành cho request đích phù hợp sau redirect.
- Chúng phụ thuộc vào FlashMapManager và cơ chế lưu trữ flash của Spring MVC.
- Chúng thường gắn với HTTP session, vì vậy redirect sang host hoặc ứng dụng khác không tự chuyển được dữ liệu.
- Chúng không thay thế kiểm tra quyền truy cập ở controller hoặc service đích.
- Chúng không bảo đảm một thông báo luôn được hiển thị nếu người dùng không thực hiện request redirect đích.
- Chúng không thay thế output của flow; output vẫn là hợp đồng để FlowHandler nhận kết quả từ root flow.

Nếu cần chuyển dữ liệu sang một ứng dụng khác, dùng hợp đồng API hoặc cơ chế truyền dữ liệu phù hợp giữa các hệ thống. Nếu cần dữ liệu tồn tại sau lần redirect, hãy lưu dữ liệu bền vững và dùng ID để truy xuất.

## 14. Kiểm thử luồng chuyển dữ liệu

Kiểm thử cần chứng minh cả kết quả của flow, dữ liệu flash được lưu và hành vi của request đích.

| Kịch bản | Điều cần xác minh |
|---|---|
| Flow kết thúc thành công | Outcome ID và output có đúng giá trị |
| Flow bị hủy | Handler chọn đúng URL và thông báo hủy |
| Output thiếu bookingId | Handler xử lý an toàn, không tạo URL sai |
| FlashMap được lưu | Có notice và target URL phù hợp |
| Request GET đích đến | Controller nhận flash attribute trong model |
| Refresh trang đích | Thông báo không bị hiển thị lại như dữ liệu bền vững |
| Hai flow cùng redirect | FlashMap được gắn với request đích thích hợp |
| Người dùng không có quyền xem ID | Controller/service từ chối dù flash có thông tin kết quả |
| Exception khi flow chạy | Cơ chế lỗi xử lý riêng, không tạo thông báo thành công giả |

Có thể kiểm thử FlowHandler riêng bằng một FlowExecutionOutcome giả lập để xác nhận logic chọn URL và phân nhánh outcome. Kiểm thử tích hợp nên chạy qua DispatcherServlet, FlowHandlerAdapter và FlowHandlerMapping để kiểm tra FlashMapManager thực sự lưu và tiêu thụ dữ liệu.

Một bài kiểm thử end-to-end nên:

1. Gửi request khởi chạy flow.
2. Thực hiện các event cần thiết để flow đi đến end-state thành công.
3. Kiểm tra response redirect đến URL MVC mong đợi.
4. Gửi request GET đến URL đích.
5. Xác nhận controller nhận notice và tải dữ liệu nghiệp vụ bằng ID.
6. Gửi lại GET hoặc refresh để xác nhận thông báo flash đã được tiêu thụ.
7. Chạy lại với outcome hủy và xác nhận nội dung thông báo khác.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Nghĩ output của end-state tự động trở thành MVC flash attributes | Controller không nhận dữ liệu như mong đợi | Đọc FlowExecutionOutcome và ghi output FlashMap trong FlowHandler |
| Dùng flash scope của Web Flow thay cho MVC FlashMap | Dữ liệu không tự xuất hiện ở controller sau redirect | Chuyển dữ liệu qua RequestContextUtils |
| Quên gọi saveOutputFlashMap | Flash attributes không được lưu cho request đích | Lưu FlashMap trước khi trả redirect |
| Lưu FlashMap cho URL khác URL redirect | Request đích không nhận được dữ liệu | Dùng cùng target URL cho cả hai thao tác |
| Chuyển cả entity qua FlashMap | Session nặng và tăng phụ thuộc | Chỉ truyền message, resultCode hoặc ID cần thiết |
| Dùng flash để giữ dữ liệu dài hạn | Dữ liệu mất sau request phù hợp hoặc hết hạn | Dùng database hoặc session theo đúng vòng đời |
| Tin bookingId trong flash là quyền truy cập | Có thể lộ dữ liệu nếu controller không kiểm tra quyền | Kiểm tra quyền ở tầng service/controller |
| Dùng thông báo thành công cho mọi outcome | Người dùng nhận kết quả sai | Phân nhánh theo outcome ID và trạng thái nghiệp vụ |

## 16. Thực hành: đưa kết quả đặt chỗ sang trang MVC

Hãy mở rộng flow đặt chỗ để sau khi xác nhận, người dùng được chuyển đến trang MVC hiển thị chi tiết.

1. Trong root flow, khai báo end-state bookingConfirmed và output bookingId.
2. Tạo BookingFlowHandler mở rộng AbstractFlowHandler.
3. Trong handleExecutionOutcome, kiểm tra outcome ID và lấy bookingId từ output.
4. Lấy output FlashMap bằng RequestContextUtils.getOutputFlashMap.
5. Thêm thuộc tính notice và resultCode vào FlashMap.
6. Gọi RequestContextUtils.saveOutputFlashMap với URL đích.
7. Trả về redirect đến cùng URL đó.
8. Đăng ký handler với FlowHandlerMapping cho Flow ID booking.
9. Tạo BookingController xử lý GET /bookings/{bookingId}, tải bản ghi và kiểm tra quyền.
10. Hiển thị thông báo flash ở view MVC.
11. Refresh trang đích và xác nhận thông báo không được dùng như dữ liệu lâu dài.
12. Thêm end-state bookingCancelled và kiểm thử thông báo hủy.

Sau khi thực hành, hãy tự trả lời:

- FlowExecutionOutcome cung cấp những thông tin gì cho FlowHandler?
- Vì sao output của end-state không tự động trở thành MVC flash attributes?
- FlashMap khác flow scope của Spring Web Flow ở vòng đời nào?
- Vì sao cần gọi saveOutputFlashMap trước khi redirect?
- Khi nào nên truyền ID trong URL thay vì FlashMap?
- Vì sao controller đích vẫn phải kiểm tra quyền truy cập?
- Điều gì xảy ra khi người dùng refresh request đích sau khi flash attribute đã được tiêu thụ?

## 17. Ghi nhớ

Để chuyển dữ liệu kết quả từ Spring Web Flow sang Spring MVC, hãy xuất dữ liệu cần thiết tại end-state, đọc FlowExecutionOutcome trong custom FlowHandler, ghi các thuộc tính tạm vào output FlashMap bằng RequestContextUtils và lưu FlashMap gắn với URL redirect. Request MVC đích sẽ nhận các thuộc tính đó trong model ở lần truy cập phù hợp.

Flow scope và MVC FlashMap có vòng đời khác nhau. Flow scope phục vụ các state trong flow execution; FlashMap phục vụ một lần redirect đến controller MVC. Chỉ chuyển thông báo, mã kết quả hoặc dữ liệu ngắn hạn; dùng URL và kho dữ liệu bền vững cho định danh và dữ liệu chi tiết. Cách tích hợp này giúp **SPRING_WEB_FLOW** phối hợp với Spring MVC rõ ràng, giữ URL gọn và hiển thị kết quả nhất quán sau khi người dùng hoàn tất hành trình.

