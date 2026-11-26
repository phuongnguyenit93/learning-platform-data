# Thiết kế trang khôi phục hoặc bắt đầu lại có kiểm soát

Trong chương **Lịch sử trình duyệt**, ta cần xử lý một tình huống thường gặp: người dùng bấm Back, Forward, Refresh hoặc mở lại bookmark của một flow đã hết hạn. Trình duyệt có thể còn giữ URL và HTML của một bước cũ, trong khi flow execution trên máy chủ đã kết thúc, session đã hết hạn hoặc snapshot không còn khả dụng. Nếu không thiết kế trước, người dùng dễ gặp lỗi khó hiểu, gửi lại thao tác đã hoàn tất hoặc mất dữ liệu đang nhập.

Với **SPRING_WEB_FLOW**, state, event và transition mô tả hành trình nghiệp vụ; execution key giúp framework tìm lại một lần chạy cụ thể giữa các request. Bài học này trình bày cách phân loại request lịch sử, xây dựng trang khôi phục độc lập, tạo execution mới có chủ đích và tiếp tục từ dữ liệu nghiệp vụ đã lưu. Mục tiêu là để người dùng hiểu tình trạng hiện tại và chọn bước tiếp theo an toàn.

## 1. Lịch sử trình duyệt không phải nguồn sự thật của flow

Trình duyệt lưu URL và có thể lưu nội dung trang để phục vụ Back/Forward. Spring Web Flow quản lý trạng thái của flow execution ở phía máy chủ thông qua flow executor và execution repository. Hai bên có vòng đời khác nhau.

Một URL flow thường chứa Flow ID và thông tin tham chiếu đến execution đang chạy. Ví dụ minh họa:

~~~text
/booking?execution=e1s3
~~~

- `booking` xác định flow definition cần xử lý.
- `execution` là khóa tham chiếu do framework cấp cho một execution snapshot.
- Giá trị khóa thực tế phụ thuộc framework và repository; ứng dụng không được tự tạo, chỉnh sửa hoặc suy luận cấu trúc khóa.

Khi người dùng quay lại một trang cũ, trình duyệt có thể hiển thị nội dung đã cache hoặc gửi request chứa execution key cũ. Nếu snapshot tương ứng vẫn còn và session hợp lệ, framework có thể khôi phục trạng thái theo cơ chế snapshot. Nếu execution đã kết thúc, snapshot bị loại bỏ, session hết hạn hoặc khóa không còn hợp lệ, request có thể không được tiếp tục.

Vì vậy, cần phân biệt:

- **Lịch sử giao diện**: những trang mà trình duyệt đã hiển thị.
- **Flow execution**: trạng thái hành trình mà Spring Web Flow đang quản lý.
- **Trạng thái nghiệp vụ**: dữ liệu bền vững như đơn hàng, đặt chỗ hoặc hồ sơ được lưu trong hệ thống.

Trạng thái nghiệp vụ mới là nguồn sự thật để quyết định một thao tác đã hoàn tất, còn hiệu lực hay có thể tiếp tục. Việc một trang cũ vẫn xuất hiện trong lịch sử trình duyệt không chứng minh flow còn hoạt động.

## 2. Những tình huống cần xử lý

Một trang khôi phục tốt bắt đầu từ việc phân loại nguyên nhân. Không phải mọi request cũ đều có cùng cách xử lý.

| Tình huống | Điều có thể xảy ra | Hướng xử lý |
|---|---|---|
| Back về một snapshot còn hợp lệ | Framework có thể khôi phục state trước đó | Cho phép tiếp tục theo snapshot và transition hợp lệ |
| Back về trang đã cache nhưng execution đã hết hạn | HTML cũ còn hiện nhưng request tiếp theo không khôi phục được flow | Hiển thị trang khôi phục khi máy chủ phát hiện execution không còn khả dụng |
| Refresh sau một POST | Trình duyệt có thể hỏi gửi lại form hoặc gửi lại request tùy luồng điều hướng | Dùng Post/Redirect/Get cho thao tác phù hợp và bảo vệ nghiệp vụ khỏi gửi trùng |
| Forward đến execution đã kết thúc | URL cũ vẫn chứa khóa của lần chạy trước | Thông báo hành trình đã kết thúc và cung cấp lựa chọn bắt đầu lại hoặc xem kết quả |
| Mở bookmark có execution key cũ | Execution có thể đã hết hạn hoặc thuộc session khác | Đưa đến trang khôi phục có hướng dẫn rõ ràng |
| Session đăng nhập hết hạn | Execution có thể không còn gắn với session hiện tại | Yêu cầu đăng nhập lại nếu cần rồi kiểm tra quyền và trạng thái nghiệp vụ |
| Dữ liệu nghiệp vụ đã thay đổi | Snapshot cũ không còn phản ánh trạng thái hiện hành | Tải lại dữ liệu và kiểm tra điều kiện trước khi tiếp tục |
| Người dùng mở nhiều tab | Mỗi tab có thể giữ execution key hoặc snapshot khác nhau | Giữ execution riêng và kiểm tra xung đột ở tầng nghiệp vụ |

Không nên coi Back luôn là lỗi. Nếu snapshot còn hợp lệ, việc quay lại có thể là một phần trải nghiệm được hỗ trợ. Vấn đề xuất hiện khi giao diện cũ và trạng thái thực tế của execution hoặc dữ liệu nghiệp vụ không còn đồng nhất.

## 3. Phân biệt lỗi execution với kết quả nghiệp vụ

Một request cũ có thể thất bại vì execution không còn khả dụng, nhưng nghiệp vụ trước đó có thể đã hoàn tất. Ví dụ, người dùng bấm Xác nhận, máy chủ đã tạo đặt chỗ, nhưng response bị mất. Khi người dùng refresh hoặc gửi lại form, hệ thống không được suy luận rằng đặt chỗ chưa được tạo chỉ vì execution key cũ không còn hợp lệ.

Cần phân biệt ít nhất ba nhóm:

1. **Execution không còn khả dụng**: khóa không hợp lệ, snapshot đã hết hạn, session đã mất hoặc root flow đã kết thúc.
2. **Kết quả nghiệp vụ đã tồn tại**: đặt chỗ đã được xác nhận, đơn hàng đã tạo hoặc yêu cầu đã bị hủy.
3. **Nghiệp vụ còn có thể tiếp tục**: bản nháp vẫn ở trạng thái đang xử lý, chưa hết hạn và người dùng hiện tại vẫn có quyền thao tác.

Trang khôi phục nên dựa vào trạng thái nghiệp vụ để quyết định hành động. Nếu đặt chỗ đã xác nhận, hãy dẫn người dùng đến trang kết quả. Nếu bản nháp vẫn còn hiệu lực, có thể tạo execution mới để tiếp tục bản nháp. Nếu bản nháp đã hết hạn, giải thích tình trạng và cho phép bắt đầu quy trình mới khi phù hợp.

Không dùng execution key như mã đặt chỗ, mã đơn hàng hoặc bằng chứng quyền truy cập. Execution key chỉ tham chiếu đến trạng thái điều phối của một lần chạy flow.

## 4. Trang khôi phục nên hoạt động độc lập với flow cũ

Trang khôi phục cần có URL MVC ổn định, không phụ thuộc execution key đang gặp lỗi. Ví dụ:

~~~text
/flow/recovery
~~~

Đây là route thông thường do Spring MVC controller xử lý. Nó vẫn có thể hiển thị khi flow execution không còn khả dụng.

Trang nên cung cấp thông tin vừa đủ:

- Nêu rõ hành trình trước đó không còn tiếp tục được bằng liên kết cũ.
- Không tiết lộ stack trace, tên lớp nội bộ, session ID hoặc execution key.
- Nếu hệ thống xác định được kết quả nghiệp vụ, hiển thị kết quả đó.
- Nếu có bản nháp còn hiệu lực, cung cấp lựa chọn tiếp tục từ bản nháp.
- Nếu không có bản nháp, cung cấp lựa chọn bắt đầu quy trình mới.
- Cho phép người dùng quay về trang chức năng hoặc danh sách hồ sơ.

Ví dụ controller MVC:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class FlowRecoveryController {

    @GetMapping("/flow/recovery")
    public String showRecovery(Model model) {
        model.addAttribute(
            "message",
            "Phiên làm việc trước không còn khả dụng."
        );
        model.addAttribute(
            "canStartAgain",
            true
        );

        return "flow/recovery";
    }
}
~~~

View `flow/recovery` có thể hiển thị hai liên kết:

~~~html
<section>
    <h1>Phiên làm việc đã kết thúc</h1>
    <p>
        Bạn có thể bắt đầu một quy trình mới hoặc quay lại danh sách đặt chỗ.
    </p>

    <a href="/booking">Bắt đầu đặt chỗ mới</a>
    <a href="/bookings">Xem danh sách đặt chỗ</a>
</section>
~~~

Đây là ví dụ giao diện đơn giản. Trong ứng dụng thực tế, nội dung trang cần được bản địa hóa và các URL phải được tạo theo context path hoặc cơ chế URL của ứng dụng.

Trang khôi phục không nên tự động khởi chạy một flow mới ngay khi được mở. Người dùng có thể chỉ muốn xem thông báo hoặc quay về trang trước. Hãy để người dùng chủ động chọn hành động tiếp theo.

## 5. Chuyển lỗi execution đến trang khôi phục

Trong tích hợp Spring MVC, FlowHandler là điểm tùy chỉnh hành vi của một flow. Tùy phiên bản Spring Web Flow, có thể triển khai xử lý exception của FlowHandler hoặc dùng cơ chế xử lý lỗi MVC phù hợp để nhận diện lỗi execution không còn khả dụng.

Nguyên tắc là chỉ chuyển những lỗi đã xác định được là execution hết hạn hoặc không thể khôi phục sang trang khôi phục. Lỗi lập trình, lỗi cấu hình flow hoặc lỗi hệ thống không dự kiến cần tiếp tục đi qua cơ chế xử lý lỗi và logging bình thường.

Một FlowHandler có thể tổ chức logic theo hướng sau:

~~~java
public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleException(
            FlowException exception,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (isUnavailableExecution(exception)) {
            return "redirect:/flow/recovery";
        }

        // Để lỗi không dự kiến được xử lý bởi cơ chế lỗi phù hợp.
        return null;
    }

    private boolean isUnavailableExecution(FlowException exception) {
        // Phân loại theo exception hierarchy và phiên bản SWF đang dùng.
        // Không coi mọi FlowException là lỗi hết hạn.
        return false;
    }
}
~~~

Đoạn mã mô tả cấu trúc xử lý. Cần đối chiếu kiểu exception và quy ước giá trị trả về của FlowHandler với phiên bản Spring Web Flow đang triển khai. Hàm phân loại phải nhận diện đúng các trường hợp repository không tìm thấy hoặc không thể khôi phục execution. Không nên viết hàm luôn trả về true hoặc chuyển tất cả exception thành thông báo hết hạn.

Nếu cần gửi thông báo một lần sau redirect, handler có thể ghi một thuộc tính vào MVC output FlashMap:

~~~java
FlashMap flashMap =
    RequestContextUtils.getOutputFlashMap(request);

flashMap.put(
    "recoveryMessage",
    "Phiên làm việc trước không còn khả dụng. Hãy chọn cách tiếp tục."
);

RequestContextUtils.saveOutputFlashMap(
    "/flow/recovery",
    request,
    response
);

return "redirect:/flow/recovery";
~~~

FlashMap thuộc Spring MVC và phục vụ request redirect tiếp theo. Nó không phải flow scope và không thể khôi phục execution cũ. Nếu ứng dụng không dùng redirect hoặc đã có cơ chế thông báo khác, có thể truyền một mã lý do an toàn theo cách phù hợp.

Không đưa exception message, stack trace, session identifier hoặc execution key vào URL hay nội dung flash. Trang khôi phục chỉ cần mã lý do đã được ứng dụng kiểm soát và thông báo dễ hiểu.

## 6. Bắt đầu lại bằng URL khởi chạy flow sạch

Để tạo một hành trình mới, người dùng cần truy cập URL khởi chạy flow mà không mang execution key của lần chạy cũ.

Ví dụ:

~~~text
/booking
~~~

Đây là URL được FlowHandlerMapping ánh xạ đến Flow ID `booking`. Khi request hợp lệ đến URL khởi chạy mà không tham chiếu execution đang hoạt động, Spring Web Flow có thể tạo một flow execution mới theo cấu hình.

Không nên tạo URL bằng cách xóa hoặc thay ký tự trong execution key cũ. Không tự gán một giá trị như `execution=e1s1`, không dùng lại URL postback cũ và không gửi event của state trước đó đến execution mới.

Nếu muốn cung cấp nút bắt đầu lại, hãy liên kết đến URL khởi chạy đã biết:

~~~html
<a href="/booking">Bắt đầu quy trình mới</a>
~~~

Nếu ứng dụng cần một request POST để tạo tài nguyên nghiệp vụ mới trước khi khởi chạy flow, hãy dùng endpoint phù hợp, bảo vệ CSRF và chuyển hướng theo kết quả. URL bắt đầu flow nên có ý nghĩa rõ ràng và không vô tình tạo giao dịch chỉ vì trình duyệt tải lại trang.

### Bắt đầu lại không đồng nghĩa xóa dữ liệu cũ

Trước khi tạo execution mới, ứng dụng cần xác định dữ liệu cũ đang ở trạng thái nào:

- Bản nháp chưa lưu có thể đã mất cùng execution.
- Bản nháp đã lưu có thể còn tiếp tục được.
- Giao dịch đã xác nhận phải được hiển thị như kết quả hiện có.
- Một khoản giữ chỗ hoặc tài nguyên tạm cần được giải phóng theo chính sách nghiệp vụ.
- Một thao tác đang ở trạng thái không xác định cần được tra cứu trước khi cho phép gửi lại.

Không xóa dữ liệu nghiệp vụ chỉ vì flow execution không còn tồn tại. Việc cleanup phải dựa trên trạng thái nghiệp vụ và cơ chế quản lý tài nguyên ở tầng service.

## 7. Tiếp tục bản nháp bằng một execution mới

Nếu người dùng cần tiếp tục một bản nháp đã lưu, cách an toàn là tạo flow execution mới rồi tải bản nháp bằng một định danh nghiệp vụ. Không cố khôi phục flow execution đã hết hạn bằng cách đoán execution key.

Ví dụ, flow nhận input `draftId`:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      start-state="loadDraft">

    <input name="draftId" type="java.lang.Long" />

    <action-state id="loadDraft">
        <evaluate
            expression="bookingService.loadEditableDraft(draftId)"
            result="flowScope.booking" />

        <transition on="success" to="bookingForm" />
        <transition on="notFound" to="draftUnavailable" />
        <transition on="forbidden" to="draftUnavailable" />
        <transition on="expired" to="draftUnavailable" />
    </action-state>

    <view-state id="bookingForm" view="bookingForm">
        <transition on="submit" to="reviewBooking" />
    </view-state>

    <end-state id="draftUnavailable" />
</flow>
~~~

Đây là cấu trúc minh họa; action tải bản nháp cần trả event tương ứng và đặt đối tượng vào flow scope khi tải thành công. Cách cung cấp input cho flow cần được cấu hình trong FlowHandler hoặc cơ chế khởi chạy tương ứng.

Service `loadEditableDraft` phải kiểm tra:

- Bản nháp có tồn tại không.
- Bản nháp còn ở trạng thái có thể chỉnh sửa không.
- Bản nháp đã hết hạn hay đã được xác nhận chưa.
- Người dùng hiện tại có quyền tiếp tục bản nháp không.
- Dữ liệu có cần được tải lại hoặc chuyển đổi theo phiên bản hiện tại không.

ID bản nháp không phải bằng chứng quyền truy cập. Người dùng có thể thay đổi tham số `draftId`, vì vậy service phải kiểm tra principal và quyền sở hữu hoặc quyền thao tác trước khi trả dữ liệu.

Một FlowHandler có thể tạo execution input từ request theo hợp đồng đã định nghĩa. Ví dụ, request khởi chạy có thể mang `draftId`:

~~~text
/booking?draftId=4821
~~~

FlowHandler hoặc cơ chế input mapping chuyển giá trị đó thành flow input. Chỉ chấp nhận tham số được dự kiến, kiểm tra định dạng và để service xác thực quyền. Không chuyển nguyên toàn bộ query string vào flow scope.

## 8. Phân biệt ba lựa chọn trên trang khôi phục

Một trang khôi phục thường nên đưa ra các hành động khác nhau tùy theo kết quả tra cứu nghiệp vụ.

| Trạng thái hiện tại | Hành động chính | Hành động thay thế |
|---|---|---|
| Đã hoàn tất | Xem kết quả đã lưu | Quay về danh sách |
| Bản nháp còn hiệu lực | Tiếp tục bản nháp | Bắt đầu mới nếu người dùng muốn |
| Bản nháp hết hạn | Bắt đầu quy trình mới | Quay về danh sách |
| Đã hủy | Xem thông tin hủy | Tạo yêu cầu mới |
| Không xác định kết quả sau timeout | Tra cứu trạng thái giao dịch | Liên hệ hỗ trợ nếu chưa xác định được |
| Không có quyền | Quay về trang an toàn | Đăng nhập bằng tài khoản phù hợp nếu cần |

Không nên hiển thị cùng một nút “Thử lại” cho mọi trường hợp. Nếu giao dịch đã hoàn tất, thử lại có thể tạo bản ghi trùng. Nếu người dùng không có quyền, việc thử lại không giải quyết được vấn đề. Nếu kết quả chưa xác định, hệ thống cần tra cứu trước khi cho phép thao tác mới.

## 9. Chống gửi lặp khi Back, Refresh hoặc gửi lại form

Browser history có thể khiến một request POST được gửi lại. Post/Redirect/Get giúp giảm việc trình duyệt hỏi gửi lại form khi refresh trang kết quả, nhưng không thay thế bảo vệ ở tầng nghiệp vụ.

Với thao tác tạo đơn hàng, xác nhận đặt chỗ hoặc thanh toán, cần thiết kế idempotency:

- Tạo một mã yêu cầu duy nhất cho thao tác nghiệp vụ.
- Lưu mã đó cùng kết quả trong transaction.
- Khi request lặp lại, trả về kết quả đã có thay vì tạo giao dịch mới.
- Kiểm tra trạng thái hiện tại trước khi thực hiện lại tác động phụ.
- Dùng transaction và ràng buộc duy nhất ở cơ sở dữ liệu khi phù hợp.

Ví dụ service:

~~~java
@Transactional
public BookingResult confirm(
        Long draftId,
        String requestKey,
        UserPrincipal principal) {

    BookingResult existing =
        bookingRepository.findResultByRequestKey(requestKey);

    if (existing != null) {
        authorizationService.checkCanView(existing, principal);
        return existing;
    }

    BookingDraft draft =
        bookingRepository.loadEditableDraft(draftId, principal);

    BookingResult result = bookingRepository.confirm(draft, requestKey);

    return result;
}
~~~

Đây là ví dụ khái niệm. Trong ứng dụng thật, việc kiểm tra request key, tạo kết quả và lưu khóa cần được thực hiện nguyên tử trong transaction; đồng thời phải xử lý hai request đồng thời dùng cùng khóa. Không dựa vào một biến trong flow scope để chống gửi trùng vì flow có thể hết hạn hoặc nhiều execution có thể cùng thao tác trên một bản nháp.

Với form có thay đổi dữ liệu, tiếp tục bảo vệ CSRF và kiểm tra quyền ở mỗi request thay đổi. Không cho phép một URL GET đơn thuần thực hiện xác nhận, thanh toán hoặc hủy giao dịch.

## 10. Xử lý nhiều tab và dữ liệu xung đột

Người dùng có thể mở cùng một flow trong hai tab. Mỗi tab có thể giữ URL và execution key riêng. Nếu cả hai cùng chỉnh sửa một bản ghi, việc khôi phục snapshot cũ không đảm bảo dữ liệu vẫn mới nhất.

Cần phối hợp flow với kiểm soát đồng thời ở tầng nghiệp vụ:

- Dùng version hoặc optimistic locking để phát hiện dữ liệu đã thay đổi.
- Khi lưu bị xung đột, tải dữ liệu mới và yêu cầu người dùng xem lại.
- Kiểm tra trạng thái bản ghi ngay trước khi xác nhận.
- Không dùng session attribute chung để lưu một execution key duy nhất cho mọi tab.
- Giữ dữ liệu riêng của từng hành trình trong flow scope hoặc một draft có định danh riêng.

Nếu hai tab đại diện cho hai bản nháp độc lập, hãy cấp ID riêng cho mỗi bản nháp. Nếu cả hai tab chỉnh sửa cùng một bản ghi, service cần phát hiện xung đột và không ghi đè âm thầm.

## 11. Bảo vệ dữ liệu khi trình duyệt quay lại

Trang có dữ liệu nhạy cảm hoặc biểu mẫu quan trọng cần được bảo vệ khỏi việc hiển thị ngoài ý muốn từ cache. Có thể cấu hình các header cache phù hợp, ví dụ `Cache-Control: no-store` cho response chứa dữ liệu nhạy cảm.

Tuy nhiên, không nên xem header cache là cách bảo đảm execution còn hiệu lực hoặc đã bị hủy. Trình duyệt có thể có cơ chế Back/Forward cache riêng và có thể hiển thị nội dung đã lưu trước khi gửi request mới. Mọi thao tác tiếp theo vẫn phải được máy chủ xác thực và kiểm tra trạng thái.

Một số nguyên tắc:

- Không đưa thông tin nhạy cảm vào query string hoặc execution key.
- Không hiển thị stack trace hoặc dữ liệu session trên trang khôi phục.
- Kiểm tra quyền ở controller và service đích, kể cả khi người dùng đến từ một flow hợp lệ trước đó.
- Với thao tác thay đổi dữ liệu, dùng POST/PUT/DELETE phù hợp và bảo vệ CSRF.
- Khi session hết hạn, xử lý đăng nhập lại rồi kiểm tra lại quyền và trạng thái bản nháp.
- Ghi log mã tương quan và mã nghiệp vụ cần thiết; hạn chế ghi execution key và dữ liệu form nhạy cảm.

## 12. Kiểm thử Back, Forward, Refresh và restart

Kiểm thử cần bao gồm cả hành vi của trình duyệt lẫn trạng thái mà máy chủ quản lý. Chỉ kiểm tra trang hiển thị đúng không đủ để chứng minh một request cũ được xử lý an toàn.

| Kịch bản | Điều cần xác minh |
|---|---|
| Back đến snapshot còn hợp lệ | Flow khôi phục đúng state theo cấu hình và không làm sai dữ liệu |
| Back đến execution đã hết hạn | Người dùng được đưa đến trang khôi phục dễ hiểu |
| Forward đến URL cũ sau khi flow kết thúc | Không tiếp tục một execution đã kết thúc |
| Refresh sau redirect | Không gửi lại thao tác POST đã hoàn tất |
| Gửi lại request xác nhận | Idempotency trả về kết quả cũ, không tạo bản ghi thứ hai |
| Session hết hạn | Người dùng được hướng dẫn đăng nhập lại và kiểm tra quyền |
| Bắt đầu lại | URL mới không chứa execution key cũ và tạo execution mới |
| Tiếp tục draft | Flow mới tải đúng draft theo ID và kiểm tra quyền |
| Draft đã hết hạn | Flow không cho tiếp tục chỉnh sửa |
| Hai tab cùng chỉnh sửa | Xung đột version được phát hiện |
| Kết quả nghiệp vụ đã hoàn tất | Trang khôi phục dẫn đến kết quả đã lưu |
| Lỗi kỹ thuật không dự kiến | Không bị che thành thông báo “phiên hết hạn” chung chung |

Một bài kiểm thử end-to-end có thể thực hiện:

1. Khởi chạy flow đặt chỗ và đi đến màn hình nhập thông tin.
2. Lưu bản nháp với một ID nghiệp vụ.
3. Mở một tab khác hoặc ghi lại URL của bước hiện tại.
4. Kết thúc hoặc làm hết hạn execution theo cấu hình kiểm thử.
5. Quay lại URL cũ và xác nhận trang khôi phục xuất hiện khi server không thể tiếp tục execution.
6. Chọn Tiếp tục bản nháp và xác nhận flow execution mới được tạo.
7. Xác nhận service tải đúng draft và kiểm tra quyền.
8. Gửi thao tác xác nhận hai lần với cùng request key và xác nhận chỉ có một kết quả nghiệp vụ.
9. Thử draft đã hết hạn và xác nhận người dùng được hướng dẫn bắt đầu mới.
10. Kiểm tra log không chứa thông tin xác thực hoặc dữ liệu nhạy cảm.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi URL cũ là bằng chứng flow còn chạy | Request không thể khôi phục hoặc dùng snapshot cũ | Để repository xác thực execution và xử lý lỗi phù hợp |
| Tự sửa execution key để bắt đầu lại | Tạo URL không hợp lệ và khó chẩn đoán | Dùng URL khởi chạy flow sạch |
| Tự động mở flow mới khi gặp mọi exception | Che giấu lỗi hệ thống và có thể làm mất ngữ cảnh | Chỉ phân loại lỗi execution đã biết; để lỗi khác đi qua error handling |
| Chỉ lưu tiến độ trong flow scope | Mất khả năng tiếp tục khi execution hết hạn | Lưu draft nghiệp vụ bền vững nếu cần phục hồi |
| Cho phép tiếp tục draft chỉ bằng ID | Có thể lộ hoặc sửa dữ liệu của người khác | Kiểm tra principal, quyền và trạng thái trong service |
| Hiển thị thông báo “thử lại” cho mọi trường hợp | Có thể tạo giao dịch trùng hoặc làm sai trạng thái | Phân biệt đã hoàn tất, còn tiếp tục và chưa xác định |
| Chỉ dựa vào Post/Redirect/Get để chống trùng | Request lặp từ tab khác hoặc client khác vẫn có thể xảy ra | Dùng idempotency ở tầng nghiệp vụ |
| Lưu một execution key chung trong session | Các tab có thể ghi đè hành trình của nhau | Để framework quản lý execution riêng |
| Dựa vào cache header để bảo vệ flow | Nội dung cũ vẫn có thể xuất hiện từ browser history | Kiểm tra trạng thái và quyền trên mọi request |

## 14. Thực hành: tạo trang khôi phục và bắt đầu lại

Hãy xây dựng một quy trình đặt chỗ có thể phục hồi sau khi execution hết hạn.

1. Tạo root flow `booking` và một flow scope chứa dữ liệu đang chỉnh sửa.
2. Thêm service lưu bản nháp bền vững và trả về `draftId`.
3. Cấu hình flow nhận `draftId` làm input khi cần tiếp tục bản nháp.
4. Tạo controller MVC cho route `/flow/recovery`, không phụ thuộc execution key.
5. Tạo view khôi phục với các lựa chọn xem kết quả, tiếp tục bản nháp, bắt đầu mới hoặc quay về danh sách.
6. Cấu hình FlowHandler hoặc cơ chế exception phù hợp để chỉ chuyển lỗi execution không còn khả dụng sang trang khôi phục.
7. Khi bắt đầu mới, liên kết đến URL khởi chạy `/booking` không có execution key cũ.
8. Khi tiếp tục bản nháp, khởi chạy execution mới với `draftId`; service phải kiểm tra quyền và thời hạn.
9. Thêm request key cho thao tác xác nhận và bảo đảm service xử lý idempotent.
10. Kiểm thử Back, Forward, Refresh, session hết hạn và hai tab cùng thao tác.
11. Xác nhận các lỗi lập trình hoặc lỗi cấu hình vẫn được ghi nhận qua cơ chế xử lý lỗi bình thường.
12. Kiểm tra trang khôi phục không tiết lộ execution key, session ID hoặc dữ liệu nhạy cảm.

Sau khi thực hành, hãy tự trả lời:

- Vì sao browser history không phải nguồn sự thật của flow execution?
- Khi nào một snapshot cũ có thể được khôi phục?
- Vì sao không nên dùng execution key cũ để bắt đầu một flow mới?
- Dữ liệu nào cần lưu bền vững nếu muốn tiếp tục sau khi execution hết hạn?
- Vì sao service phải kiểm tra quyền khi nhận draftId?
- Post/Redirect/Get giải quyết vấn đề gì và vì sao vẫn cần idempotency?
- Làm thế nào phân biệt execution đã hết hạn với nghiệp vụ đã hoàn tất?

## 15. Ghi nhớ

Back, Forward và Refresh có thể đưa người dùng đến URL hoặc nội dung trang cũ, nhưng không bảo đảm flow execution còn khả dụng. Hãy để Spring Web Flow repository xác định execution có thể khôi phục hay không. Khi execution không còn khả dụng, đưa người dùng đến một trang MVC độc lập để giải thích tình trạng và cung cấp các lựa chọn rõ ràng.

Bắt đầu lại bằng URL khởi chạy flow sạch để framework tạo execution mới. Nếu cần tiếp tục công việc đã lưu, hãy truyền ID bản nháp vào flow mới và tải dữ liệu qua service có kiểm tra quyền, trạng thái và thời hạn. Kết hợp Post/Redirect/Get, idempotency, kiểm soát đồng thời và kiểm thử browser history để hành trình **SPRING_WEB_FLOW** có thể phục hồi an toàn mà không tạo giao dịch trùng hoặc làm người dùng mất phương hướng.
