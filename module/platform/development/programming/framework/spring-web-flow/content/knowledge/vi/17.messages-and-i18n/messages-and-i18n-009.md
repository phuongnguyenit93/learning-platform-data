# Thông báo thành công khi flow trả kết quả

Trong chương **Thông báo và ngôn ngữ**, thông báo thành công giúp người dùng hiểu kết quả của một hành trình nhiều bước. Với **SPRING_WEB_FLOW**, flow có thể hoàn tất một thao tác, trả outcome từ subflow hoặc chuyển đến view kết quả. Ta cần gắn thông báo với kết quả nghiệp vụ đã được xác nhận, chọn scope phù hợp để giữ thông báo đến đúng màn hình và dùng message code để hiển thị theo ngôn ngữ hiện tại.

Bài học dùng quy trình đặt chỗ làm ví dụ: sau khi service xác nhận đặt chỗ thành công, flow hiển thị mã xác nhận và thông báo tương ứng. Nếu người dùng hủy hoặc thao tác thất bại, flow không được phát thông báo thành công.

## 1. Thông báo phải phản ánh kết quả nghiệp vụ

Một thông báo như “Đặt chỗ thành công” chỉ nên xuất hiện sau khi thao tác nghiệp vụ đã hoàn tất. Việc người dùng nhấn nút Xác nhận mới chỉ tạo ra một event; nó chưa chứng minh dữ liệu đã được lưu hoặc dịch vụ bên ngoài đã xử lý thành công.

Trình tự hợp lý là:

1. Flow nhận event `confirm`.
2. Action gọi service để xác nhận đặt chỗ.
3. Service trả kết quả thành công và mã tham chiếu.
4. Flow lưu mã kết quả cùng message code.
5. Flow chuyển đến view xác nhận hoặc trả outcome cho flow cha.

Nếu service từ chối thao tác, phát sinh lỗi nghiệp vụ hoặc không thể hoàn tất giao dịch, flow phải đi theo nhánh lỗi phù hợp. Không đặt message thành công trước khi service hoàn thành vì người dùng có thể nhìn thấy thông báo sai khi giao dịch thất bại.

## 2. Lưu message code trong flow scope

Khi view kết quả là một phần của cùng flow, có thể lưu message code trong `flowScope`. Cách này giữ thông tin kết quả qua các state và cho phép view cuối đọc được mã thông báo.

```xml
<view-state id="reviewBooking">
    <transition on="confirm" to="confirmBooking" />
    <transition on="cancel" to="cancelled" />
</view-state>

<action-state id="confirmBooking">
    <evaluate expression="bookingService.confirm(booking)"
              result="flowScope.bookingResult" />
    <transition to="completed">
        <set name="flowScope.successMessageCode"
             value="'booking.confirmed'" />
    </transition>
</action-state>

<end-state id="completed" view="booking/confirmation" />
<end-state id="cancelled" view="booking/cancelled" />
```

Ở ví dụ này, `bookingService.confirm(booking)` phải trả về sau khi thao tác xác nhận đã thành công; nếu thất bại, action cần đưa lỗi vào cơ chế xử lý lỗi hoặc nhánh phù hợp thay vì đi tiếp như thành công. Transition không có `on` là transition không điều kiện sau khi action state hoàn tất bình thường.

`successMessageCode` là mã ổn định, chẳng hạn `booking.confirmed`, không phải câu tiếng Việt được hard-code trong flow. `bookingResult` có thể chứa mã tham chiếu do service trả về. View cuối có thể hiển thị cả thông báo và dữ liệu kết quả:

```jsp
<%@ taglib prefix="spring" uri="http://www.springframework.org/tags" %>

<section class="booking-result" role="status">
    <h1><spring:message code="${flowScope.successMessageCode}" /></h1>
    <p>Mã xác nhận: ${flowScope.bookingResult.reference}</p>
</section>
```

View `booking/confirmation` được render như view kết thúc của flow. Trong trường hợp này, dữ liệu flow scope còn có thể được dùng trong lúc render view cuối. Không nên giả định dữ liệu đó sẽ tự xuất hiện trong một request mới sau khi trình duyệt được redirect ra khỏi flow.

## 3. Thông báo một lần khi chuyển sang view kế tiếp

Nếu flow vẫn tiếp tục sau thao tác thành công, thông báo thường chỉ cần hiển thị ở màn hình kế tiếp. Có thể dùng `flashScope` để giữ message code cho lần flow resume tiếp theo:

```xml
<action-state id="saveDraft">
    <evaluate expression="bookingService.saveDraft(booking)" />
    <transition to="editBooking">
        <set name="flashScope.noticeCode" value="'booking.draftSaved'" />
    </transition>
</action-state>
```

View `editBooking` đọc thông báo trong flash scope:

```jsp
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<%@ taglib prefix="spring" uri="http://www.springframework.org/tags" %>

<c:if test="${not empty flashScope.noticeCode}">
    <p class="notice" role="status">
        <spring:message code="${flashScope.noticeCode}" />
    </p>
</c:if>
```

`flashScope` phù hợp với thông báo ngắn hạn cần đi qua lần chuyển tiếp kế tiếp. Sau khi flow được resume, dữ liệu flash được tiêu thụ theo vòng đời của nó. Không dùng flash scope để lưu mã xác nhận hoặc dữ liệu nghiệp vụ cần truy cập lâu dài.

Nếu view kết quả được render trực tiếp bởi `end-state`, hãy lưu thông tin cần hiển thị trong flow scope trước khi kết thúc. Flash scope chủ yếu phù hợp khi flow tiếp tục và có request resume để nhận dữ liệu flash.

## 4. Trả kết quả từ subflow và tạo thông báo ở flow cha

Trong một hành trình lớn, subflow thường chỉ nên trả outcome và dữ liệu kết quả; flow cha quyết định thông báo cuối cùng. Ví dụ, subflow thanh toán trả mã giao dịch khi thanh toán thành công:

```xml
<!-- Flow payment -->
<end-state id="paid">
    <output name="paymentReference" value="payment.reference" />
</end-state>

<end-state id="paymentFailed" />
```

Flow đặt chỗ nhận outcome `paid`, lưu mã giao dịch và thiết lập thông báo cho màn hình kết quả:

```xml
<subflow-state id="payment" subflow="payment">
    <transition on="paid" to="bookingCompleted">
        <set name="flowScope.paymentReference"
             value="currentEvent.attributes.paymentReference" />
        <set name="flowScope.successMessageCode"
             value="'booking.paymentReceived'" />
    </transition>
    <transition on="paymentFailed" to="paymentProblem" />
</subflow-state>

<end-state id="bookingCompleted" view="booking/confirmation" />
<view-state id="paymentProblem" />
```

Các output của subflow được cung cấp cho flow cha qua event attributes; tên và cách ánh xạ cần khớp với output đã khai báo. Nhánh `paymentFailed` không đặt message code thành công. Flow cha có thể ghép thông tin thanh toán với mã đặt chỗ để tạo một thông báo hoàn chỉnh.

Giữ message code ở flow cha giúp thông điệp nhất quán với kết quả của toàn bộ hành trình. Subflow thanh toán có thể được dùng ở nhiều quy trình khác nhau, vì vậy nó không nên tự quyết định câu thông báo tổng kết cho từng nghiệp vụ cha.

## 5. Tổ chức message code theo ngôn ngữ

Không nên đặt nguyên câu hiển thị trực tiếp trong flow definition hoặc Java action. Hãy lưu message code trong message bundle để cùng một kết quả có thể được hiển thị bằng nhiều ngôn ngữ.

Ví dụ, file `messages_vi.properties`:

```properties
booking.confirmed=Đặt chỗ của bạn đã được xác nhận.
booking.draftSaved=Bản nháp đặt chỗ đã được lưu.
booking.paymentReceived=Đặt chỗ đã được xác nhận và thanh toán thành công.
booking.cancelled=Đặt chỗ đã được hủy.
```

File `messages_en.properties`:

```properties
booking.confirmed=Your booking has been confirmed.
booking.draftSaved=Your booking draft has been saved.
booking.paymentReceived=Your booking has been confirmed and paid.
booking.cancelled=Your booking has been cancelled.
```

Đăng ký `MessageSource` để Spring có thể phân giải mã thông báo:

```xml
<bean id="messageSource"
      class="org.springframework.context.support.ResourceBundleMessageSource">
    <property name="basename" value="messages" />
    <property name="defaultEncoding" value="UTF-8" />
</bean>
```

Đặt các bundle trong classpath, ví dụ `src/main/resources/messages_vi.properties` và `src/main/resources/messages_en.properties`. Locale được chọn theo cấu hình locale của ứng dụng, chẳng hạn locale resolver của Spring MVC hoặc locale được xác định từ request. Cần bảo đảm cấu hình Web Flow và Spring MVC cùng sử dụng cơ chế phân giải message phù hợp để view nhận đúng ngôn ngữ.

Trong JSP, thẻ `<spring:message>` nhận message code và phân giải nội dung theo locale hiện tại. Có thể truyền tham số cho thông báo, chẳng hạn tên người nhận hoặc mã tham chiếu, bằng thuộc tính `arguments` của thẻ hoặc bằng message format trong bundle. Chỉ đưa dữ liệu không nhạy cảm vào nội dung thông báo.

## 6. Thông báo khi flow redirect sang Spring MVC

Khi `end-state` dùng `externalRedirect:`, trình duyệt tạo request mới đến URL đích. Flow scope của flow đã kết thúc không tự động trở thành model của controller đích. Vì vậy, không nên dựa vào `${flowScope.successMessageCode}` trong trang MVC sau redirect.

Một cách bền vững là lưu kết quả nghiệp vụ trước khi kết thúc flow, sau đó chuyển một mã tham chiếu không nhạy cảm đến trang MVC:

```xml
<end-state id="completed"
           view="externalRedirect:/booking/confirmation?reference=#{flowScope.bookingResult.reference}" />
```

Controller đích tra cứu kết quả từ service và render message code tương ứng:

```java
@Controller
public class BookingConfirmationController {

    private final BookingQueryService bookingQueryService;

    public BookingConfirmationController(BookingQueryService bookingQueryService) {
        this.bookingQueryService = bookingQueryService;
    }

    @GetMapping("/booking/confirmation")
    public String show(@RequestParam String reference, Model model) {
        BookingResult result = bookingQueryService.findVisibleResult(reference);
        model.addAttribute("bookingResult", result);
        model.addAttribute("successMessageCode", "booking.confirmed");
        return "booking/confirmation";
    }
}
```

`findVisibleResult` cần kiểm tra người dùng hiện tại có quyền xem kết quả đó. Mã tham chiếu trên URL không được xem là bằng chứng xác thực hoặc quyền truy cập. Nếu ứng dụng muốn thông báo chỉ xuất hiện một lần sau redirect, có thể dùng cơ chế one-time notice phía máy chủ hoặc Spring MVC flash attribute do một controller tạo ra trong chính request redirect của nó. Không có cơ chế tự động chuyển `flashScope` của Web Flow thành `RedirectAttributes` của Spring MVC.

## 7. Phân biệt success message với validation message

Thông báo thành công và thông báo validation có mục đích khác nhau:

| Loại thông báo | Thời điểm | Ví dụ | Vòng đời phù hợp |
|---|---|---|---|
| Validation error | Trước khi transition được thực hiện, khi dữ liệu không hợp lệ. | “Email không đúng định dạng.” | Message context của lần xử lý view hiện tại để hiển thị lại form. |
| Business error | Service từ chối thao tác hoặc quy tắc nghiệp vụ không thỏa mãn. | “Phòng vừa được người khác đặt.” | Nhánh lỗi và message context hoặc message code của view lỗi. |
| Success notice | Sau khi thao tác nghiệp vụ hoàn tất. | “Đặt chỗ của bạn đã được xác nhận.” | `flowScope` cho view kết thúc; `flashScope` cho view kế tiếp; dữ liệu bền vững cho request sau redirect. |

Không dùng success notice để thay thế trạng thái thực tế của giao dịch. Nếu thao tác được xử lý bất đồng bộ, chỉ thông báo “đã tiếp nhận yêu cầu” khi mới tạo yêu cầu; chỉ thông báo “đã hoàn tất” sau khi nhận được kết quả cuối cùng từ hệ thống xử lý.

## 8. Kiểm thử thông báo và kết quả flow

Kiểm thử nên xác nhận thông báo được tạo đúng thời điểm và đúng nhánh:

- Khi service xác nhận thành công, flow lưu message code `booking.confirmed` và đi đến state kết quả.
- Khi service trả lỗi nghiệp vụ, flow đi đến nhánh lỗi và không có success code.
- Khi subflow trả outcome `paid`, flow cha nhận đúng mã giao dịch và đặt message code tương ứng.
- Khi dùng `flashScope`, thông báo có ở request resume kế tiếp và không được dùng như dữ liệu lâu dài.
- Khi redirect ra Spring MVC, controller tải lại kết quả từ nguồn bền vững thay vì đọc flow scope đã kết thúc.
- Khi locale là tiếng Việt hoặc tiếng Anh, cùng message code được phân giải thành nội dung tương ứng.

Ví dụ ma trận kiểm thử:

| Kịch bản | Kết quả nghiệp vụ | Message code mong đợi | State hoặc trang đích |
|---|---|---|---|
| Xác nhận đặt chỗ | Thành công, có reference | `booking.confirmed` | `completed` |
| Lưu bản nháp | Thành công | `booking.draftSaved` | View chỉnh sửa kế tiếp |
| Thanh toán qua subflow | Outcome `paid` | `booking.paymentReceived` | `bookingCompleted` |
| Hủy đặt chỗ | Hủy thành công | `booking.cancelled` | `cancelled` |
| Thanh toán thất bại | Outcome `paymentFailed` | Không có success code | `paymentProblem` |

Với flow test, dùng `MockExternalContext` để gửi event và kiểm tra state/outcome. Có thể đăng ký một bean probe trong test để ghi lại message code hoặc dữ liệu kết quả được chuyển qua transition. Test message bundle riêng bằng `MessageSource` với các locale khác nhau; test flow và test phân giải ngôn ngữ nên kiểm tra hai phần độc lập.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Hiện thông báo thành công dù lưu thất bại | Message code được đặt trước khi service xác nhận thành công hoặc exception bị nuốt và flow vẫn đi tiếp. |
| View kết quả không có thông báo | Message code không được lưu trong scope còn tồn tại khi render; kiểm tra tên thuộc tính và state đích. |
| Thông báo xuất hiện lặp lại | Dùng `flowScope` hoặc `conversationScope` cho thông báo chỉ cần một lần; cân nhắc `flashScope` hoặc xóa sau khi hiển thị. |
| Sau redirect không tìm thấy message code | Flow scope đã kết thúc và không được chia sẻ với request MVC mới. Hãy tải kết quả từ nguồn bền vững hoặc dùng cơ chế one-time notice phía máy chủ. |
| Luôn hiển thị tiếng Việt dù người dùng chọn tiếng Anh | Locale resolver, `MessageSource` hoặc tên file bundle chưa được cấu hình đúng. |
| Subflow báo thành công nhưng flow cha không có mã giao dịch | Output name, event outcome hoặc mapping của `subflow-state` không khớp. |

Khi debug, hãy kiểm tra thứ tự: service đã hoàn tất chưa, flow đang đi qua outcome nào, message code được đặt ở scope nào, view có đọc đúng key không và locale hiện tại là gì. Cách này giúp phân biệt lỗi nghiệp vụ với lỗi hiển thị hoặc lỗi phân giải ngôn ngữ.

## 10. Thực hành

Hoàn thiện flow đặt chỗ có hai nhánh xác nhận và hủy.

1. Tạo action state gọi `bookingService.confirm(booking)` và chỉ đặt `booking.confirmed` sau khi service trả thành công.
2. Hiển thị message code trong view cuối bằng `<spring:message>`.
3. Thêm message bundle tiếng Việt và tiếng Anh cho `booking.confirmed`, `booking.cancelled` và `booking.draftSaved`.
4. Thêm một transition lưu bản nháp, đặt `booking.draftSaved` vào `flashScope` và xác nhận thông báo chỉ xuất hiện ở view kế tiếp.
5. Nếu có subflow thanh toán, trả outcome cùng `paymentReference`; để flow cha chọn message code cho kết quả toàn bộ đặt chỗ.
6. Thử nhánh thanh toán thất bại và xác nhận không có success message.
7. Thử redirect đến Spring MVC; lưu kết quả trước khi kết thúc flow và để controller tra cứu theo reference cùng kiểm tra quyền truy cập.
8. Chạy test với locale Việt và Anh để xác nhận cùng message code cho ra nội dung đúng ngôn ngữ.

Bạn hoàn thành bài khi giải thích được vì sao success message chỉ được tạo sau kết quả nghiệp vụ, chọn đúng scope cho view cuối hoặc thông báo một lần, và phân giải message code theo locale mà không phụ thuộc vào câu chữ hard-code trong flow.
