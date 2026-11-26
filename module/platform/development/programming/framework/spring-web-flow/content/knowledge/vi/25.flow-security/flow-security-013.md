# Kiểm soát redirect, biểu thức và dữ liệu hiển thị

Trong chương **Bảo vệ flow**, bài này tập trung vào ba ranh giới dễ tạo lỗ hổng trong ứng dụng Spring Web Flow: URL chuyển hướng do request điều khiển, biểu thức được đánh giá trong flow và dữ liệu được render ra view. Một flow nhiều bước có thể giữ trạng thái qua nhiều request, nhận dữ liệu từ trình duyệt hoặc hệ thống ngoài, rồi dùng dữ liệu đó để gọi service và tạo trang HTML. Mỗi bước cần xác định dữ liệu nào đáng tin, ai được phép thực hiện hành động và dữ liệu nào phải được mã hóa trước khi hiển thị.

Spring Web Flow mô hình hóa hành trình bằng state, event, transition và subflow; Spring MVC tiếp nhận request và render view. Cấu hình flow XML và biểu thức SpEL là mã cấu hình phía máy chủ, còn query parameter, form field, callback và dữ liệu người dùng là đầu vào không đáng tin cậy. Không để đầu vào đó tự quyết định nơi redirect, nội dung biểu thức cần chạy hoặc HTML được đưa thẳng vào trang.

## 1. Xác định ranh giới tin cậy của một flow

Một quy trình đặt lịch có thể nhận `bookingId` từ URL, nhận tên và ghi chú từ form, gọi service kiểm tra quyền, rồi hiển thị thông tin đặt lịch. Có thể phân loại dữ liệu theo nguồn:

| Dữ liệu | Nguồn | Cách xử lý |
| --- | --- | --- |
| Flow definition và SpEL trong XML | Mã ứng dụng được triển khai | Review như mã nguồn; giới hạn bean và quyền mà biểu thức có thể gọi. |
| Query parameter và form field | Trình duyệt | Xem là dữ liệu không đáng tin; kiểm tra kiểu, kích thước, định dạng và quy tắc nghiệp vụ. |
| Callback từ hệ thống ngoài | Nhà cung cấp hoặc client bên ngoài | Xác minh chữ ký/trạng thái qua service; không tin riêng tham số `status`. |
| Dữ liệu trong flow scope | Được giữ qua nhiều state của execution | Kiểm soát vòng đời, quyền truy cập và nội dung được lưu; dữ liệu đã lưu không mặc nhiên an toàn. |
| Nội dung hiển thị trong view | Model, request hoặc service | Encode theo ngữ cảnh HTML/attribute/URL/JavaScript trước khi render. |
| Redirect target | Cấu hình hoặc lựa chọn từ request | Chỉ dùng đích được server cho phép; không redirect trực tiếp đến URL tùy ý. |

Một nguyên tắc xuyên suốt là **kiểm tra tại nơi dữ liệu được sử dụng**. Việc một giá trị đã được lưu trong `flowScope` không chứng minh nó hợp lệ; nó có thể bắt nguồn từ request trước đó. Tương tự, việc người dùng đã đi qua một view state không chứng minh họ có quyền thực hiện hành động ở state kế tiếp.

## 2. Kiểm soát redirect target bằng allowlist

Lỗ hổng open redirect xuất hiện khi ứng dụng nhận một URL từ request rồi chuyển trình duyệt đến URL đó mà không xác thực. Ví dụ:

```text
/booking/complete?returnUrl=https://fake-login.example.invalid
```

Nếu flow dùng trực tiếp `requestParameters.returnUrl`, kẻ tấn công có thể tạo một liên kết mang domain đáng tin của ứng dụng nhưng đưa người dùng đến trang giả mạo sau khi họ nhấn vào.

Hãy ánh xạ một khóa lựa chọn thành các đích do server quản lý:

```java
public class RedirectTargetService {

    private static final Map<String, String> TARGETS = Map.of(
            "summary", "/booking/summary",
            "home", "/home"
    );

    public String resolve(String destination) {
        return TARGETS.getOrDefault(destination, "/booking/complete");
    }
}
```

Flow chỉ nhận một khóa như `summary` hoặc `home`, sau đó dùng đích đã được ánh xạ:

```xml
<action-state id="resolveReturnTarget">
    <evaluate expression="redirectTargetService.resolve(requestParameters.destination)"
              result="flowScope.returnPath" />
    <transition to="leaveFlow" />
</action-state>

<end-state id="leaveFlow"
           view="externalRedirect:#{flowScope.returnPath}" />
```

Trong ví dụ này, `returnPath` chỉ nhận đường dẫn nội bộ từ map cố định. Nếu nghiệp vụ cần redirect đến domain ngoài, hãy parse URI và kiểm tra scheme, host, port theo allowlist chính xác. Cần từ chối URL dạng `//host`, scheme như `javascript:` hoặc `data:`, user-info, hostname giả mạo và các dạng mã hóa có thể làm sai kết quả kiểm tra. Không dùng phép kiểm tra chuỗi đơn giản như `startsWith("https://trusted.example")` để xác thực hostname.

Với đường dẫn nội bộ, chuẩn hóa path và bảo đảm đích nằm trong phạm vi được phép. Nếu tham số thiếu hoặc sai, dùng đích fallback an toàn. Không đưa trực tiếp `returnUrl` của người dùng vào `externalRedirect:` hay `flowRedirect:`.

## 3. Tách dữ liệu khỏi biểu thức SpEL

Spring Web Flow sử dụng biểu thức để đọc scope, gọi bean và quyết định transition. Ví dụ hợp lệ là biểu thức được viết sẵn trong flow definition:

```xml
<decision-state id="checkBooking">
    <if test="bookingAccessService.canView(flowScope.bookingId, currentUser.id)"
        then="showBooking"
        else="accessDenied" />
</decision-state>
```

`bookingAccessService` là bean do ứng dụng kiểm soát; biểu thức gọi một phương thức hẹp để kiểm tra quyền. Request chỉ cung cấp `bookingId` như một giá trị đầu vào. Không biến request thành một phần của mã biểu thức.

**Không bao giờ đánh giá chuỗi do người dùng gửi như một biểu thức SpEL.** Tránh các cách làm như:

```java
// Không an toàn: dữ liệu người dùng bị coi như mã biểu thức.
Expression expression = parser.parseExpression(request.getParameter("rule"));
Object result = expression.getValue(evaluationContext);
```

Khi người dùng có thể kiểm soát chuỗi biểu thức, họ có thể truy cập thuộc tính hoặc gọi phương thức ngoài dự kiến tùy cấu hình evaluation context. Thay vào đó, nhận một mã lựa chọn có tập giá trị cố định rồi ánh xạ sang hành vi được phép:

```java
public enum BookingAction {
    REVIEW, CANCEL, RESTART
}

public BookingAction parseAction(String value) {
    try {
        return BookingAction.valueOf(value);
    } catch (IllegalArgumentException | NullPointerException ex) {
        return BookingAction.REVIEW;
    }
}
```

Nếu ứng dụng có chức năng cho quản trị viên cấu hình điều kiện, hãy định nghĩa một DSL giới hạn hoặc một bộ điều kiện kiểu dữ liệu cụ thể; không cho phép người dùng cuối gửi SpEL tùy ý. Cấu hình biểu thức được lưu trong database cũng cần được xem là đầu vào có rủi ro nếu người có quyền sửa dữ liệu không đồng thời được phép thực thi mã.

## 4. Giới hạn bean và phương thức mà flow có thể gọi

Biểu thức flow thường gọi bean bằng tên, chẳng hạn `bookingService.confirm(...)`. Chỉ đưa vào context các bean cần thiết và cung cấp phương thức có trách nhiệm hẹp. Không tạo một bean tiện ích có quyền truy cập toàn bộ application context, filesystem, shell hoặc các chức năng quản trị rồi cho flow gọi tùy ý.

Ví dụ service nên kiểm tra quyền ở phía máy chủ:

```java
public class BookingService {

    public Booking confirm(Long bookingId, UserPrincipal actor) {
        Booking booking = repository.findById(bookingId)
                .orElseThrow(BookingNotFoundException::new);

        if (!authorizationService.canConfirm(actor, booking)) {
            throw new AccessDeniedException("Không có quyền xác nhận lịch đặt.");
        }

        return confirmationService.confirm(booking);
    }
}
```

Flow có thể gọi phương thức này ở action state, nhưng service vẫn phải xác thực quyền và trạng thái nghiệp vụ. Không nhận `actorId` do request gửi để thay thế principal đã xác thực. Không dựa vào việc nút **Xác nhận** bị ẩn trong view để bảo vệ hành động; người dùng có thể gửi request trực tiếp.

Các phương thức được gọi từ SpEL nên có kiểu tham số rõ ràng, kiểm tra đầu vào, trả kết quả miền nghiệp vụ và không tạo side effect ngoài dự kiến khi chỉ dùng để kiểm tra điều kiện. Tránh gọi một phương thức thay đổi dữ liệu bên trong `decision-state` hoặc biểu thức dùng cho render, vì biểu thức có thể được đánh giá ở thời điểm khó dự đoán và làm hành vi thay đổi theo cách khó kiểm thử.

## 5. Bảo vệ dữ liệu trong scope và flow execution

`flowScope` giữ dữ liệu qua nhiều state trong một flow execution; `conversationScope` có thể chia sẻ dữ liệu giữa flow cha và subflow. Dữ liệu nằm trong scope thường được lưu theo cơ chế execution/session của ứng dụng. Điều đó không có nghĩa dữ liệu đã được mã hóa, có quyền truy cập đúng hoặc được phép giữ vô thời hạn.

Một số nguyên tắc:

- Chỉ lưu những trường cần cho các bước tiếp theo; ưu tiên ID hoặc DTO nhỏ thay vì entity lớn chứa nhiều thuộc tính.
- Không lưu mật khẩu, mã OTP, access token, refresh token hoặc dữ liệu thanh toán nhạy cảm trong flow scope lâu hơn nhu cầu.
- Không đưa dữ liệu bí mật vào query string, hidden field hoặc output hiển thị cho trình duyệt.
- Kiểm tra quyền sở hữu và quyền thực hiện lại ở service tại mỗi thao tác nhạy cảm; không giả định execution key là quyền truy cập.
- Xác định hành vi khi session hết hạn, flow execution cũ được gửi lại hoặc người dùng mở nhiều tab.
- Không ghi toàn bộ flow scope hoặc request parameter vào log để debug.

Flow execution key dùng để tiếp tục một lần thực thi cụ thể. Nó không phải CSRF token, không phải access token và không thay thế xác thực/ủy quyền. Bảo vệ cookie session bằng cấu hình phù hợp như `HttpOnly`, `Secure` khi dùng HTTPS và `SameSite` theo nhu cầu ứng dụng; dùng session management của Spring Security để xử lý session fixation và đăng xuất.

## 6. Bảo vệ request thay đổi trạng thái bằng CSRF

Các event như `confirm`, `cancel`, `delete` hoặc `pay` làm thay đổi trạng thái nghiệp vụ. Chúng nên được gửi bằng POST và được bảo vệ bằng CSRF token khi ứng dụng dùng Spring Security. Không dùng GET để thực hiện thao tác thay đổi dữ liệu.

Ví dụ form JSP với Spring Security taglib:

```jsp
<%@ taglib prefix="sec" uri="http://www.springframework.org/security/tags" %>

<form method="post">
    <input type="hidden" name="_flowExecutionKey" value="${flowExecutionKey}" />
    <sec:csrfInput />
    <button type="submit" name="_eventId_confirm" value="true">
        Xác nhận
    </button>
</form>
```

Thẻ `csrfInput` render token theo cấu hình Spring Security. Nếu ứng dụng dùng cơ chế render form khác, bảo đảm token được gửi cùng request theo tên parameter/header mà CSRF filter đang cấu hình. Kiểm tra request thực tế qua Spring MVC và Spring Web Flow để chắc chắn filter chain không bỏ qua endpoint flow ngoài dự kiến.

Không tắt CSRF chỉ để làm cho event của flow chạy được. Hãy xác định đúng phương thức HTTP, token, matcher và thứ tự filter. Với callback từ cổng thanh toán hoặc webhook server-to-server, xác thực chữ ký và giao thức callback theo nhà cung cấp; không áp dụng ngoại lệ CSRF rộng cho toàn bộ endpoint.

## 7. Encode dữ liệu trước khi hiển thị

Cross-site scripting (XSS) xảy ra khi dữ liệu không đáng tin được render như HTML hoặc JavaScript có thể thực thi. Ví dụ người dùng nhập ghi chú:

```text
<img src=x onerror=alert(1)>
```

Nếu view in chuỗi đó như HTML thô, trình duyệt có thể thực thi event handler. Hãy encode theo đúng ngữ cảnh:

```jsp
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>

<p class="booking-note">
    <c:out value="${booking.note}" />
</p>
```

`c:out` mặc định escape các ký tự XML/HTML cơ bản khi xuất nội dung. Với giá trị nằm trong HTML attribute, URL hoặc JavaScript, cần encoding dành riêng cho ngữ cảnh đó; không dùng HTML escaping như giải pháp chung cho mọi ngữ cảnh. Ưu tiên đặt dữ liệu vào text node, tránh tạo inline JavaScript từ dữ liệu động và dùng thư viện encoder phù hợp như OWASP Java Encoder khi cần.

Không render dữ liệu người dùng bằng cơ chế xuất HTML thô, chẳng hạn `escapeXml="false"`, `innerHTML` hoặc template mode không escape, trừ khi nội dung đã được sanitize bằng một bộ lọc HTML allowlist chuyên dụng. Nếu ứng dụng cho phép rich text, xác định rõ các thẻ/attribute được phép, loại bỏ script, event handler, URL scheme nguy hiểm và kiểm thử payload thực tế.

## 8. Bảo vệ URL và dữ liệu hiển thị khỏi rò rỉ

Query string có thể xuất hiện trong browser history, access log, proxy log, analytics và header `Referer`. Không truyền mật khẩu, OTP, token, số thẻ hoặc thông tin cá nhân nhạy cảm qua URL. Với redirect sau khi hoàn tất, chỉ truyền mã tham chiếu không nhạy cảm và tải dữ liệu qua service có kiểm tra quyền.

Khi hiển thị dữ liệu lỗi hoặc trạng thái flow:

- Không đưa stack trace, tên lớp nội bộ, SQL, đường dẫn filesystem hoặc thông tin cấu hình vào view.
- Không hiển thị token hoặc giá trị của hidden field trong thông báo lỗi.
- Dùng message code và thông báo thân thiện; ghi chi tiết kỹ thuật vào log có kiểm soát.
- Đặt `Cache-Control: no-store` cho trang chứa dữ liệu nhạy cảm nếu phù hợp với chính sách ứng dụng.
- Dùng HTTPS cho toàn bộ session và redirect liên quan đến thông tin xác thực.

Thông báo lỗi nên giúp người dùng biết cần làm gì tiếp theo mà không tiết lộ liệu một tài khoản, đơn hàng hoặc tài nguyên riêng tư có tồn tại hay không nếu điều đó tạo rủi ro dò quét.

## 9. Kiểm thử bảo mật cho flow

Kiểm thử cần bao phủ cả đường đi bình thường lẫn request được tạo thủ công:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| `returnUrl` là domain ngoài allowlist | Flow dùng đích fallback an toàn; không redirect đến domain do người dùng chọn. |
| `returnUrl` dạng `//attacker.example` hoặc `javascript:` | Bị từ chối. |
| Request gửi chuỗi SpEL tùy ý | Chuỗi được coi là dữ liệu; không được parse/evaluate. |
| Request sửa `bookingId` sang tài nguyên người khác | Service từ chối truy cập; không lộ dữ liệu. |
| Gửi event thay đổi trạng thái mà thiếu CSRF token | Spring Security từ chối request theo cấu hình. |
| Gửi GET đến endpoint thực hiện xác nhận | Không thực hiện side effect. |
| Ghi chú chứa thẻ HTML/script | Nội dung được encode hoặc sanitize theo chính sách; không thực thi trong trình duyệt. |
| Session hết hạn hoặc execution key cũ | Người dùng nhận hành vi hết hạn an toàn; không truy cập dữ liệu cũ. |
| Callback thanh toán giả mạo `success` | Không xác nhận thanh toán nếu chữ ký/trạng thái không hợp lệ. |
| Lỗi service hoặc exception | View không hiển thị stack trace, token hoặc dữ liệu nhạy cảm. |

Với redirect, kiểm tra cả status code và `Location` header bằng MVC integration test. Với CSRF, kiểm thử request thiếu, sai và đúng token. Với authorization, thử thay ID trong request bằng ID thuộc người dùng khác. Với XSS, dùng payload trong field hiển thị và xác nhận trình duyệt coi nó là text, không tạo phần tử hoặc chạy script.

Kiểm thử thêm trường hợp người dùng mở hai tab hoặc gửi lại event `confirm`. Service cần bảo đảm trạng thái nghiệp vụ hợp lệ và idempotency cho thao tác có side effect; việc một flow execution hợp lệ không đảm bảo request không bị lặp.

## 10. Checklist trước khi đưa flow vào môi trường thật

- Redirect target đến từ allowlist phía máy chủ và có fallback an toàn.
- Request parameter không được ghép thành SpEL hoặc mã thực thi.
- Bean được gọi từ expression context có phạm vi nhỏ và phương thức kiểm tra đầu vào rõ ràng.
- Service kiểm tra quyền trên mỗi thao tác nhạy cảm; không dựa vào trạng thái giao diện.
- Flow scope chỉ giữ dữ liệu cần thiết và không giữ bí mật quá lâu.
- Execution key không được xem là CSRF token hoặc bằng chứng ủy quyền.
- Event thay đổi dữ liệu dùng POST và được bảo vệ bằng CSRF theo cấu hình Spring Security.
- Dữ liệu hiển thị được encode theo ngữ cảnh; rich text được sanitize bằng allowlist.
- URL và log không chứa token hoặc dữ liệu cá nhân nhạy cảm.
- Kiểm thử open redirect, expression injection, IDOR, CSRF, XSS, session expiry và request lặp.

Khi các ranh giới này được bảo vệ, Spring Web Flow có thể điều phối hành trình nhiều bước mà không để dữ liệu đầu vào tự quyết định mã biểu thức, đích redirect hoặc nội dung HTML thực thi. Flow chịu trách nhiệm state và transition; service xác thực quyền và nghiệp vụ; view hiển thị dữ liệu đã được kiểm soát và encode đúng ngữ cảnh.
