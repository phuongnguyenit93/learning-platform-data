# Kiến thức cần có về Spring IoC, MVC, Servlet và HTTP session

Spring Web Flow (SWF) giúp tổ chức các hành trình web có nhiều bước như đăng ký tài khoản, đặt lịch, thanh toán hay khai báo thông tin. Để hiểu vì sao một `view-state` có thể hiển thị form, một `transition` nhận sự kiện từ trình duyệt và một `flowScope` giữ dữ liệu giữa các bước, cần nắm bốn nền tảng: **Spring IoC**, **Spring MVC**, **Servlet** và **HTTP session**.

Ví dụ xuyên suốt: người dùng mở trang đặt lịch, nhập thông tin, kiểm tra lại rồi xác nhận. Nếu chỉ có một màn hình, một controller MVC thường đã đủ. Khi hành trình gồm nhiều màn hình, nhánh quay lại, xác nhận và hủy, Web Flow có thể quản lý trình tự này bằng các state và event. Dù chọn cách nào, yêu cầu vẫn đi qua hạ tầng HTTP, Servlet và Spring.

## 1. Mục tiêu và mô hình tổng thể

Sau bài này, bạn cần có khả năng:

1. Giải thích được container Spring tạo, lắp ghép và quản lý bean như thế nào; vì sao controller không nên tự giữ dữ liệu của từng người dùng.
2. Theo dõi một HTTP request từ trình duyệt qua servlet container, bộ lọc, `DispatcherServlet`, controller đến view hoặc response.
3. Phân biệt tham số request, model MVC, thuộc tính `HttpSession` và các scope dành riêng cho Web Flow.
4. Hiểu cách cookie phiên, chuyển hướng, binding và validation tác động đến hành trình nhiều bước.
5. Nhận diện các lỗi thường gặp: mất session, trộn dữ liệu giữa người dùng, submit hai lần, flow hết hạn và sai thế hệ thư viện `javax`/`jakarta`.

~~~mermaid
flowchart LR
    A["Trình duyệt"] -->|"HTTP request"| B["Servlet container"]
    B --> C["Filter chain"]
    C --> D["DispatcherServlet"]
    D --> E["HandlerMapping / HandlerAdapter"]
    E --> F["MVC Controller hoặc FlowHandlerAdapter"]
    F --> G["Service bean / FlowExecutor"]
    G --> H["Model, View hoặc response"]
    H -->|"HTTP response"| A
~~~

Sơ đồ là đường đi khái quát, không phải thứ tự gọi cố định của mọi thành phần: chẳng hạn, `ViewResolver` tham gia khi handler trả về tên view; một endpoint REST có thể ghi thẳng JSON mà không render template. Với SWF, `FlowHandlerAdapter` kết nối request MVC với bộ thực thi flow.

## 2. HTTP: nền tảng của mọi lần chuyển bước

HTTP là giao thức **request–response**: trình duyệt gửi yêu cầu, máy chủ xử lý và gửi phản hồi. Giao thức không tự nhớ rằng request hôm nay và request trước thuộc cùng một người; cơ chế phiên và dữ liệu định danh phải được bổ sung ở lớp ứng dụng/hạ tầng.

| Khái niệm | Ý nghĩa | Liên hệ với hành trình nhiều bước |
| --- | --- | --- |
| `GET` | Đọc tài nguyên hoặc hiển thị trang; nên không gây tác dụng phụ nghiệp vụ | Mở trang nhập liệu, trang xem lại |
| `POST` | Gửi biểu mẫu hoặc yêu cầu thực hiện hành động | Chọn “Tiếp tục”, “Xác nhận”, “Hủy” |
| URL và query string | Xác định tài nguyên và tham số điều hướng | Có thể mang định danh phiên thực thi flow, tùy cấu hình |
| Request body | Mang dữ liệu form hoặc JSON | Giá trị các trường người dùng nhập |
| Header `Cookie` | Trình duyệt gửi cookie đã lưu về máy chủ | Thường gửi cookie định danh HTTP session |
| Header `Set-Cookie` | Máy chủ yêu cầu trình duyệt lưu/cập nhật cookie | Có thể thiết lập cookie phiên |
| `302` / `303` và `Location` | Yêu cầu trình duyệt đi đến URL khác | Triển khai chuyển hướng sau POST |
| Status `4xx` / `5xx` | Phân biệt lỗi phía request và lỗi máy chủ | Cần xử lý khi flow không còn hợp lệ hoặc ứng dụng gặp lỗi |

Một request mang dữ liệu của flow có thể trông như sau. Đây là ví dụ minh họa: tên tham số và định dạng execution key phụ thuộc cách tích hợp Web Flow.

~~~http
POST /booking?execution=e1s1 HTTP/1.1
Host: example.test
Cookie: JSESSIONID=opaque-session-id
Content-Type: application/x-www-form-urlencoded

_eventId=next&customerName=Lan
~~~

Ba thông tin trong ví dụ có vai trò **khác nhau**:

- `JSESSIONID` (tên mặc định thường gặp) là cookie giúp máy chủ tìm HTTP session. Giá trị cookie **không** chứa toàn bộ thông tin đặt lịch.
- `execution` là thông tin để Web Flow tìm và tiếp tục một flow execution, tùy cấu hình URL và repository.
- `_eventId=next` biểu thị sự kiện mà người dùng phát ra; Web Flow xem state hiện tại có transition tương ứng hay không. Không được xem tên event do client gửi là quyền thực hiện hành động: phân quyền phải kiểm tra ở server.

**POST không mặc nhiên an toàn khi gửi lặp.** Nếu thao tác xác nhận tạo đơn hàng hoặc trừ tiền, việc người dùng bấm đúp hay refresh có thể gây trùng thao tác. Đặt kiểm soát tại tầng nghiệp vụ bằng khóa idempotency, ràng buộc dữ liệu hoặc cơ chế phù hợp; chỉ chuyển hướng sau POST chưa đủ để bảo đảm không trùng.

## 3. Servlet và vòng đời một HTTP request

**Servlet** là hợp đồng Java để xử lý yêu cầu HTTP trong servlet container, chẳng hạn Tomcat hoặc Jetty. Container nhận kết nối, phân tích request, thực thi filter chain, chọn servlet và quản lý các đối tượng `HttpServletRequest`, `HttpServletResponse`, `HttpSession`.

Trong ứng dụng Spring MVC phổ biến, servlet trung tâm là **`DispatcherServlet`**. Phần lớn controller viết bằng `@Controller` không tự kế thừa `HttpServlet`; chúng được `DispatcherServlet` tìm và gọi thông qua các thành phần MVC.

Một request trang web đi qua các lớp theo trình tự khái quát:

1. **Container** nhận HTTP request và ánh xạ tới servlet phù hợp.
2. **Servlet Filter** có thể xử lý bảo mật, logging, encoding hoặc CORS trước/sau servlet. Spring Security thường hoạt động qua filter chain.
3. **`DispatcherServlet`** nhờ `HandlerMapping` tìm handler, rồi nhờ `HandlerAdapter` thực thi handler đó.
4. **Handler** gọi bean nghiệp vụ, đọc/ghi model hoặc xử lý Web Flow.
5. Nếu trả về view name, **view resolution/rendering** tạo HTML; nếu REST, message converter có thể tạo JSON.
6. Container trả HTTP response. Bản thân request và các thuộc tính `requestScope` không còn sống sau chu kỳ request đó.

### 3.1. Servlet request khác HTTP session

`HttpServletRequest` sống trong phạm vi một lần xử lý request. `HttpSession` có thể sống qua nhiều request của cùng một phiên, miễn chưa hết hạn hoặc bị hủy.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionProbeController {
    @GetMapping("/debug/session-present")
    public String sessionPresent(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        return session == null ? "Chưa có HTTP session" : "Đã có HTTP session";
    }
}
~~~

`getSession(false)` **không tạo session mới**. Ngược lại, `getSession()` hoặc `getSession(true)` có thể tạo session nếu chưa có. Ví dụ dùng API `jakarta.servlet`, phù hợp với thế hệ Spring Framework 6; ở hệ sinh thái Spring Framework 5 thường gặp namespace `javax.servlet`. Không trộn các kiểu import này trong cùng một cấu hình thư viện.

### 3.2. Filter và interceptor không giống nhau

| Thành phần | Vị trí hoạt động | Dùng khi nào |
| --- | --- | --- |
| Servlet `Filter` | Trong chuỗi xử lý Servlet, trước khi MVC chọn handler | Bảo mật mức HTTP, log request, header, encoding |
| Spring MVC `HandlerInterceptor` | Quanh quá trình gọi handler đã được MVC ánh xạ | Kiểm tra/nghiệp vụ phụ thuộc handler, ghi nhận thời gian xử lý |
| `@Controller` / `@RestController` | Handler xử lý endpoint | Điều phối request, binding, validation, gọi service |
| Web Flow `FlowHandlerAdapter` | Một loại MVC handler adapter | Chuyển request được ánh xạ tới flow thành thao tác trên `FlowExecutor` |

Nếu cần bảo vệ endpoint, ưu tiên dùng cơ chế bảo mật ở server (ví dụ Spring Security), không chỉ kiểm tra sự kiện hoặc ẩn nút ở giao diện.

## 4. Spring IoC: nơi tạo và nối các thành phần

**IoC (Inversion of Control)** nghĩa là quyền tạo và phối hợp đối tượng được chuyển cho Spring container thay vì mỗi đối tượng tự `new` mọi dependency. **Dependency Injection (DI)** là cách phổ biến để container cấp dependency cho một bean.

Ví dụ kiến trúc đặt lịch:

~~~java
import org.springframework.stereotype.Service;

@Service
public class BookingService {
    public void submit(String customerName) {
        // Ở ứng dụng thật: kiểm tra điều kiện và lưu qua repository.
    }
}
~~~

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/booking")
public class BookingController {
    private final BookingService bookingService;

    public BookingController(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    // Các phương thức xử lý GET/POST được bổ sung ở phần MVC.
}
~~~

Spring phát hiện các class thông qua component scanning hoặc cấu hình bean, tạo instance `BookingService` rồi truyền vào constructor của `BookingController`. Cơ chế này hỗ trợ thay thế implementation, kiểm thử bằng dependency giả lập và giảm phụ thuộc giữa các lớp.

Những annotation nên nhận biết:

| Annotation/khái niệm | Công dụng |
| --- | --- |
| `@Component` | Đánh dấu thành phần do Spring quản lý |
| `@Service` | Chỉ rõ bean phụ trách logic nghiệp vụ |
| `@Repository` | Đánh dấu thành phần truy cập dữ liệu; có thể tham gia chuyển đổi ngoại lệ |
| `@Controller` / `@RestController` | Thành phần xử lý yêu cầu web |
| `@Configuration` và `@Bean` | Định nghĩa bean bằng cấu hình Java |
| Constructor injection | Nhận dependency khi tạo đối tượng; phù hợp cho dependency bắt buộc |
| Bean scope `singleton` | Mặc định một bean instance cho mỗi Spring container, có thể phục vụ nhiều request/người dùng |

### 4.1. Bẫy đặc biệt nguy hiểm: dữ liệu người dùng trong singleton

Ví dụ **sai**:

~~~java
@Controller
class UnsafeBookingController {
    private String currentCustomer; // SAI: trạng thái dùng chung giữa nhiều request
}
~~~

Nếu hai người đồng thời đặt lịch, họ có thể ghi đè dữ liệu của nhau. Spring controller và service thường là singleton nên **không lưu dữ liệu form riêng của người dùng trong field mutable của bean**. Hãy dùng biến cục bộ của request, kho dữ liệu nghiệp vụ hoặc scope phù hợp của Web Flow. Nếu cần bean có scope ngắn hơn như `request` hay `session`, phải hiểu rõ cách inject/proxy và vòng đời của chúng.

Đây là mối nối đầu tiên tới Web Flow: `FlowExecutor`, controller tích hợp và các service có thể là bean Spring dùng chung, còn **dữ liệu từng hành trình** được quản lý qua flow execution và scope tương ứng.

## 5. Spring MVC: từ URL tới form, model và view

Spring MVC đặt `DispatcherServlet` ở trung tâm:

- **Controller**: nhận request, chọn nghiệp vụ và xác định response.
- **Model**: dữ liệu để render view trong lượt xử lý hiện tại; không tự động trở thành dữ liệu phiên.
- **View**: template HTML (ví dụ Thymeleaf/JSP) hoặc cách render tương ứng. REST endpoint có thể trả body trực tiếp.

Ví dụ form đặt lịch một màn hình. Lớp dữ liệu có constructor rỗng và getter/setter để MVC bind giá trị từ form:

~~~java
import jakarta.validation.constraints.NotBlank;

public class BookingForm {
    @NotBlank
    private String customerName;

    public BookingForm() {}

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }
}
~~~

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/booking")
public class BookingController {
    private final BookingService bookingService;

    public BookingController(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    @GetMapping("/new")
    public String newForm(Model model) {
        model.addAttribute("booking", new BookingForm());
        return "booking/new";
    }

    @PostMapping("/new")
    public String submit(
            @Valid @ModelAttribute("booking") BookingForm booking,
            BindingResult errors,
            RedirectAttributes redirectAttributes) {
        if (errors.hasErrors()) {
            return "booking/new";
        }

        bookingService.submit(booking.getCustomerName());
        redirectAttributes.addFlashAttribute("notice", "Đã nhận yêu cầu đặt lịch");
        return "redirect:/booking/done";
    }
}
~~~

Đây là các đoạn mã minh họa ở những tệp Java tương ứng, giả định đã có template `booking/new`, route `/booking/done`, các dependency MVC/validation cần thiết và cơ chế lưu thật ở service. Chúng cho thấy luồng API, chưa phải một ứng dụng hoàn chỉnh.

Điểm cần quan sát:

1. `@GetMapping` và `@PostMapping` ánh xạ URL + HTTP method tới phương thức.
2. `@ModelAttribute("booking")` nhận dữ liệu form vào `BookingForm`; chỉ nên bind các trường được phép sửa.
3. `@Valid` yêu cầu chạy Bean Validation. Cần có implementation validation được cấu hình, chẳng hạn dependency validation starter trong ứng dụng Spring Boot.
4. `BindingResult` đặt **ngay sau** tham số được validate để handler đọc lỗi binding/validation. Khi lỗi, render lại view để hiển thị thông báo.
5. `redirect:` thực hiện chuyển hướng sau POST (mẫu **Post/Redirect/Get**), tránh trình duyệt gửi lại form chỉ vì refresh trang kết quả.
6. `RedirectAttributes.addFlashAttribute` truyền thông báo sang request sau khi redirect; đây là **MVC flash attributes**, không đồng nhất với `flashScope` của Web Flow.

**Binding không phải validation, validation không phải phân quyền.** Binding chuyển giá trị request vào object; validation kiểm tra tính hợp lệ; còn service phải thực thi quy tắc nghiệp vụ và kiểm tra quyền truy cập.

### 5.1. MVC một request so với hành trình nhiều request

Với một form, controller thường có cặp GET/POST. Khi có các bước “nhập thông tin → xem lại → xác nhận”, controller thuần phải tự quản lý màn hình hiện tại, các nhánh hợp lệ, dữ liệu tạm và hành vi quay lại. Web Flow đưa những mối quan hệ đó vào mô hình state/transition, nhưng vẫn dựa trên cơ chế request, binding, validation, view và service của Spring.

## 6. HTTP session: nhớ người dùng giữa các request

Một **HTTP session** là vùng trạng thái phía server được liên hệ với các request của một phiên client. Thông thường:

1. Server tạo session khi cần và cấp một session ID khó đoán.
2. Trình duyệt giữ session ID trong cookie, thường có tên `JSESSIONID`.
3. Ở request sau, trình duyệt gửi cookie phù hợp; server tra session tương ứng.
4. Session có thể hết hạn, bị `invalidate()`, mất do thay đổi hạ tầng lưu trữ hoặc không truy cập được ở một node khác.

Ví dụ API thấp của Servlet:

~~~java
import jakarta.servlet.http.HttpSession;

// Ví dụ bên trong một handler đã nhận HttpSession từ Spring MVC:
session.setAttribute("draftId", "draft-123");
String draftId = (String) session.getAttribute("draftId");
session.removeAttribute("draftId");
// Khi chủ động kết thúc toàn bộ phiên:
// session.invalidate();
~~~

`HttpSession` phù hợp với dữ liệu thật sự thuộc cả phiên, nhưng không nên coi đó là cơ sở dữ liệu bền vững. Cân nhắc bộ nhớ, kích thước object, serialization, số người dùng đồng thời, timeout và cách triển khai nhiều instance. Nếu chạy nhiều node, cần chiến lược session nhất quán, chẳng hạn sticky session hoặc kho session dùng chung; Spring Session là một lựa chọn tùy kiến trúc.

### 6.1. Tách bạch sáu loại trạng thái thường bị nhầm

| Nơi giữ trạng thái | Vòng đời chủ yếu | Phù hợp cho |
| --- | --- | --- |
| Tham số request / `requestScope` | Một request | Input gửi lên, dữ liệu tính tạm |
| MVC `Model` | Dữ liệu để handler render view ở request hiện tại | Hiển thị lỗi form, kết quả truy vấn |
| MVC flash attributes | Qua một lần redirect, dùng ở request đích | Thông báo sau khi lưu |
| Servlet `HttpSession` | Nhiều request cho tới timeout/hủy phiên | Thông tin mức phiên được kiểm soát |
| Database | Bền theo chính sách lưu trữ | Đơn hàng, lịch hẹn đã xác nhận |
| Web Flow scope | Theo request/view/flow/conversation do Web Flow quản lý | Dữ liệu và ngữ cảnh của riêng hành trình |

`@SessionAttributes` của Spring MVC cho phép một controller lưu **một số model attributes** giữa các request; gọi `SessionStatus.setComplete()` để kết thúc việc lưu các thuộc tính controller đó. Annotation này không tương đương với toàn bộ `HttpSession`, cũng không thay thế `flowScope`.

### 6.2. Các lưu ý khi dùng session

- **Không phụ thuộc vào session luôn tồn tại.** Tab cũ hoặc request sau timeout có thể thiếu dữ liệu; hiển thị thông báo và cho người dùng bắt đầu lại an toàn.
- **Không lưu object tùy ý không giới hạn.** Bản nháp lớn, tệp upload hoặc dữ liệu nhạy cảm cần chiến lược lưu trữ riêng và vòng đời rõ ràng.
- **Không coi session là khóa đồng bộ.** Hai tab hoặc hai request song song có thể sửa cùng dữ liệu; thao tác đọc–sửa–ghi không tự động atomic.
- **Không coi session ID hay execution key là quyền truy cập.** Kiểm tra xác thực, ủy quyền và quyền sở hữu dữ liệu tại server.
- **Bảo vệ cookie và biểu mẫu.** Dùng HTTPS, thuộc tính cookie phù hợp (`HttpOnly`, `Secure`, `SameSite`), chống CSRF đối với thao tác thay đổi trạng thái, và đổi session ID khi xác thực theo cấu hình bảo mật phù hợp.

## 7. Các scope của Spring Web Flow liên hệ thế nào với HTTP session?

Spring Web Flow định nghĩa các scope gắn với vòng đời của **flow execution**. Nắm rõ chúng giúp tránh lưu mọi thứ vào `HttpSession` rồi phải tự dọn dẹp.

| Web Flow scope | Ý nghĩa thực hành | Ví dụ |
| --- | --- | --- |
| `requestScope` | Dữ liệu của lần request đang xử lý | Tham số/tính toán tạm |
| `flashScope` | Dữ liệu ngắn hạn phục vụ lần chuyển và lần hiển thị kế tiếp theo vòng đời Web Flow | Thông báo vừa hoàn tất thao tác |
| `viewScope` | Dữ liệu gắn với view-state đang hoạt động | Trạng thái hiển thị của một bước |
| `flowScope` | Dữ liệu của một flow execution, qua nhiều state trong flow đó | Bản nháp đặt lịch |
| `conversationScope` | Dữ liệu ở conversation của flow gốc, có thể chia sẻ với subflow thuộc conversation đó | Ngữ cảnh chung của hành trình và các nhánh con |
| `sessionScope` | Thuộc HTTP session, có thể được truy cập qua nhiều flow của phiên | Thông tin dùng chung ở mức phiên khi thực sự cần |

Lưu ý: phạm vi chính xác của việc duy trì, phục hồi hoặc snapshot dữ liệu còn chịu ảnh hưởng bởi cấu hình execution repository và vòng đời state. **`flowScope` không đồng nghĩa với `HttpSession`**: một phiên trình duyệt có thể có nhiều flow execution, mỗi execution mang dữ liệu riêng. Dữ liệu flow có thể được lưu qua cơ chế repository tùy cấu hình, nên cũng không mặc định toàn bộ flow được lưu trực tiếp vào session.

Một thiết kế đặt lịch hợp lý là để `bookingDraft` ở `flowScope` trong lúc người dùng đi qua các bước, lưu bản ghi nghiệp vụ vào database khi xác nhận thành công, rồi kết thúc flow. Chỉ đưa dữ liệu lên `conversationScope` hoặc `sessionScope` khi thực sự cần chia sẻ ở phạm vi rộng hơn.

## 8. Ghép bốn nền tảng vào một Spring Web Flow

Giả sử hành trình gồm ba màn hình/hành động:

~~~mermaid
stateDiagram-v2
    [*] --> details
    details --> review: next
    review --> details: back
    review --> finished: confirm / lưu
    finished --> [*]
~~~

Một định nghĩa XML minh họa:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.booking.BookingDraft"/>

    <view-state id="details" view="booking/details" model="booking">
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="finished">
            <evaluate expression="bookingService.save(booking)"/>
        </transition>
    </view-state>

    <end-state id="finished" view="booking/finished"/>
</flow>
~~~

Đây là **trích đoạn định nghĩa flow**, không phải cấu hình ứng dụng đầy đủ. Ví dụ giả định class `BookingDraft` có thể khởi tạo, `bookingService` là bean Spring truy cập được từ flow, có view tương ứng, có Web Flow registry/executor/MVC integration đã cấu hình và có quy tắc validation cần thiết. Logic lưu thật cần kiểm tra dữ liệu, phân quyền và giao dịch tại service.

Đọc flow này bằng kiến thức vừa học:

- **Spring IoC:** cung cấp `bookingService` và hạ tầng chạy flow.
- **Spring MVC:** tiếp nhận request tới flow và phối hợp render view; adapter của Web Flow tích hợp với `DispatcherServlet`.
- **Servlet/HTTP:** nhận form POST với event, cookie và thông tin tiếp tục execution.
- **Web Flow state/event/transition:** tại `details`, event `next` dẫn đến `review`; tại `review`, `back` quay lại, `confirm` chạy action lưu và kết thúc.
- **Scope:** biến `booking` của flow giữ bản nháp trong hành trình, tránh đặt bản nháp vào field của singleton controller.

### 8.1. Từ một click đến transition

1. Trình duyệt hiển thị view của state `details` và gửi form với event `next`.
2. Servlet container và filter chain xử lý request; `DispatcherServlet` chọn handler cho flow.
3. Web Flow tìm flow execution dựa trên thông tin request/repository, đọc state hiện tại.
4. Web Flow bind và có thể validate dữ liệu từ form vào model của view-state theo cấu hình.
5. Nếu xử lý hợp lệ, transition `next` đưa execution sang `review`; view mới được render.
6. Khi event `confirm` xảy ra, service thực thi quy tắc lưu và flow kết thúc.

Nếu binding/validation thất bại, hành vi giữ lại view và thông báo lỗi phụ thuộc cấu hình state/validation; không nên viết logic điều hướng chỉ dựa trên việc client luôn gửi event đúng.

### 8.2. Điều gì thuộc controller, điều gì thuộc service?

| Thành phần | Trách nhiệm chính |
| --- | --- |
| MVC Controller / flow handler | Điểm nhận request, điều phối tích hợp web |
| Flow definition | Mô tả state, event, transition, nhánh và vòng đời hành trình |
| Form/model | Giữ giá trị đầu vào và lỗi validation cho màn hình |
| Service bean | Thực thi nghiệp vụ, kiểm tra quyền, phối hợp giao dịch |
| Repository/database | Lưu trạng thái nghiệp vụ cần bền vững |
| Session/flow repository | Duy trì ngữ cảnh thực thi tạm thời theo chính sách |

**Không đặt nghiệp vụ lưu đơn hàng chỉ trong controller, XML chuyển trạng thái hoặc session.** Flow giúp mô tả trình tự; service phải đảm bảo giao dịch và các bất biến nghiệp vụ ngay cả khi nhận request lặp hoặc có nhiều tab.

## 9. Phiên bản và khả năng tương thích: `javax`, `jakarta`, Spring MVC và SWF

Khi học từ ví dụ trên mạng, cần xác định ví dụ thuộc thế hệ thư viện nào. Dấu hiệu dễ thấy:

| Thế hệ thường gặp | API Servlet | API validation | Hệ quả |
| --- | --- | --- | --- |
| Spring Framework 5.x | `javax.servlet.*` | `javax.validation.*` | Ví dụ legacy sử dụng namespace Java EE |
| Spring Framework 6.x | `jakarta.servlet.*` | `jakarta.validation.*` | Ví dụ thế hệ Jakarta EE; yêu cầu dependency/container tương thích |

Đừng chỉ thay import rồi kỳ vọng cả ứng dụng chạy: namespace Servlet, validation, phiên bản Spring MVC, Web Flow, Java runtime và servlet container phải thuộc tổ hợp tương thích. **Không suy phiên bản SWF hỗ trợ chỉ từ phiên bản Spring Boot.** Khi nâng cấp một dự án thực tế, đối chiếu release notes và ma trận tương thích của chính những artifact đang sử dụng.

Một số điểm kiểm tra khi nhận dự án cũ:

1. Xác định phiên bản Java, Spring Framework/MVC, SWF và servlet container được quản lý bởi BOM hoặc dependency management.
2. Soát import `javax.*`/`jakarta.*` của Servlet, Validation và các thư viện tích hợp.
3. Kiểm tra cơ chế cấu hình `DispatcherServlet`, flow registry, flow executor và Web Flow handler mapping/adapter.
4. Kiểm tra cách lưu execution, quản lý session, timeout, security filter chain và đường dẫn đến template.
5. Chạy kiểm thử điều hướng, validation, back/refresh, timeout và submit trùng sau mỗi thay đổi lớn.

## 10. Các lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Việc cần kiểm tra |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` hoặc không inject được service | Bean chưa được đăng ký, component scan sai hoặc có xung đột cấu hình | Component scan, `@Bean`, kiểu dependency và package |
| URL trả `404` dù flow/controller đã viết | Sai mapping, chưa đăng ký handler/flow, sai flow id | URL thực tế, `HandlerMapping`, flow registry, log mapping |
| Form không nhận dữ liệu hoặc không báo lỗi | Tên field không khớp, thiếu binding/validator hoặc đọc sai `BindingResult` | `@ModelAttribute`, tên field, validator, thứ tự tham số |
| Người A thấy thông tin của người B | Đặt trạng thái cá nhân trong field mutable singleton hoặc cache sai key | Bean scope, nơi lưu bản nháp và kiểm soát truy cập |
| Mỗi request như một phiên mới | Cookie không được lưu/gửi, khác hostname/path, session store thiếu nhất quán | Cookie, HTTPS/proxy, node xử lý, session configuration |
| Quay lại tab cũ báo không tìm thấy execution | Flow đã kết thúc, timeout hoặc execution key cũ/đã bị loại khỏi repository | Vòng đời execution, session timeout, chính sách snapshot |
| Nút xác nhận gây lưu hai lần | Request bị submit lặp, thiếu idempotency hoặc ràng buộc dữ liệu | Service và database, không chỉ UI/redirect |
| Lỗi kiểu `javax.servlet` / `jakarta.servlet` | Trộn dependency thuộc hai thế hệ API | Dependency tree, BOM, Java/container và phiên bản SWF |

Khi debug, hãy đặt breakpoint/log tại lớp **đang sở hữu vấn đề**: filter nếu cookie/security có vấn đề; MVC nếu mapping/binding sai; Web Flow nếu event/transition sai; service nếu nghiệp vụ sai. Không ghi session ID, execution key hay thông tin nhạy cảm nguyên dạng vào log production.

## 11. Bài thực hành có kiểm chứng

**Bài A — theo dõi HTTP/MVC**

1. Tạo một ứng dụng Spring MVC tối giản với form đặt lịch như phần 5 và một route hiển thị kết quả.
2. Mở Developer Tools → Network: quan sát GET form, POST submit, status redirect và GET trang đích.
3. Cố ý gửi tên rỗng; xác minh validation trả lại màn hình form và hiển thị lỗi, không gọi service lưu.
4. Đặt breakpoint tại controller và service để phân biệt điều phối web với nghiệp vụ.

**Bài B — xác định scope**

Vẽ hành trình `details → review → confirm` và quyết định nơi giữ mỗi dữ liệu:

| Dữ liệu | Phạm vi nên cân nhắc | Lý do |
| --- | --- | --- |
| Giá trị tên khách đang nhập | `flowScope` / model của flow | Cần qua nhiều state nhưng chỉ thuộc một execution |
| Lỗi của một lần submit | Binding/validation và phạm vi hiển thị phù hợp | Không cần tồn tại lâu dài |
| Thông báo sau khi chuyển bước | Flash/view tùy luồng | Chỉ cần hiển thị ngắn hạn |
| Lịch hẹn đã xác nhận | Database | Phải bền, có kiểm soát giao dịch |
| Cấu hình nghiệp vụ dùng chung | Spring service/configuration bean | Dùng cho nhiều request, không mang trạng thái người dùng |

**Bài C — thử các tình huống phiên**

Mở hai cửa sổ trình duyệt độc lập (hoặc hai profile), nhập hai bản nháp khác nhau và xác nhận không bị trộn. Sau đó thử refresh, back, submit trùng, mở hai tab cùng phiên và quay lại sau timeout. Ghi rõ kết quả mong muốn cho từng trường hợp; những hành vi chưa được bảo đảm phải có xử lý ở service hoặc ở flow.

## 12. Câu hỏi tự kiểm tra

1. **Vì sao không đặt `currentBooking` trong field của `@Controller`?** Vì controller thường là singleton và phục vụ đồng thời nhiều người dùng; dữ liệu bản nháp sẽ bị chia sẻ hoặc ghi đè.
2. **`Model` trong MVC có tự lưu sang request kế tiếp không?** Không. Model thông thường phục vụ việc render của request hiện tại; muốn qua request khác cần cơ chế thích hợp như flash, session hoặc Web Flow scope.
3. **`HttpSession` và `flowScope` có cùng vòng đời không?** Không. Một HTTP session có thể chứa/được liên kết với nhiều flow execution; `flowScope` gắn với một execution cụ thể.
4. **`@Valid` đã đủ để cho phép người dùng xác nhận đơn hàng chưa?** Chưa. Bean Validation kiểm tra dữ liệu; server vẫn phải xác thực, phân quyền, áp dụng quy tắc nghiệp vụ và bảo vệ thao tác khỏi xử lý lặp.
5. **Vì sao sau POST thường nên redirect?** Để dùng mẫu Post/Redirect/Get và giảm tình trạng refresh khiến trình duyệt gửi lại POST; vẫn cần idempotency tại service cho nghiệp vụ quan trọng.
6. **Điều gì xảy ra khi gửi event không có transition hợp lệ?** Flow không nên tự điều hướng theo ý client; engine xử lý theo state, transition và chính sách lỗi được cấu hình. Cần thiết kế thông báo/khôi phục phù hợp.

**Điểm cần nhớ:** IoC quản lý **bean và dependency**; Servlet/HTTP quản lý **request, response và phiên**; Spring MVC quản lý **ánh xạ web, binding và view**; Spring Web Flow tổ chức **state, event, transition và dữ liệu của từng hành trình** trên các nền tảng đó. Phân biệt đúng trách nhiệm và vòng đời của từng lớp là tiền đề để xây dựng, kiểm thử và phục hồi các luồng web nhiều bước.
