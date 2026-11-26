# Tham số trả về và kiểm soát đích chuyển hướng

Trong chương **URL và điều hướng**, bài này trình bày cách Spring Web Flow nhận tham số từ URL, giữ dữ liệu cần thiết trong flow, và chuyển người dùng đến đúng đích khi quy trình kết thúc hoặc cần mở một flow khác. Ta cũng sẽ xử lý tham số trả về từ hệ thống bên ngoài, kiểm soát redirect target và kiểm thử để tránh lỗi điều hướng, lộ dữ liệu hoặc open redirect.

Spring Web Flow tổ chức hành trình web qua state, event và transition. Một request có thể khởi chạy flow, tiếp tục một flow execution đang tồn tại hoặc gửi event để chuyển state. URL có thể mang dữ liệu đầu vào, nhưng dữ liệu đó cần được kiểm tra trước khi ảnh hưởng đến nghiệp vụ hoặc quyết định redirect. Flow execution key là định danh cho lần thực thi flow; nó không phải mã nghiệp vụ và không nên được dùng thay cho `bookingId`, `orderId` hay token xác nhận.

## 1. Phân biệt các loại tham số trên URL

Trong một ứng dụng nhiều bước, URL và request có thể chứa nhiều loại thông tin:

| Loại | Ví dụ | Mục đích |
| --- | --- | --- |
| Flow ID | `/flows/booking` | Chọn định nghĩa flow cần khởi chạy. |
| Query parameter nghiệp vụ | `?bookingId=B-1042` | Truyền mã tham chiếu để flow tải dữ liệu nghiệp vụ. |
| Event parameter | `_eventId_submit` | Yêu cầu flow hiện tại xử lý event `submit`. |
| Flow execution key | `_flowExecutionKey` | Xác định lần thực thi flow cần tiếp tục. |
| Redirect parameter | `?result=confirmed` | Chuyển một kết quả hoặc mã tham chiếu đến đích điều hướng tiếp theo. |

Các loại tham số này có vai trò khác nhau. Không tự ghép `_flowExecutionKey` vào URL để tạo flow mới, không dùng query parameter `result=success` làm bằng chứng thanh toán thành công, và không xem giá trị do trình duyệt gửi là dữ liệu đã được xác thực.

Với JSP, form tiếp tục flow thường gửi execution key cùng event:

```jsp
<form method="post">
    <input type="hidden" name="_flowExecutionKey" value="${flowExecutionKey}" />
    <button type="submit" name="_eventId_continue" value="true">
        Tiếp tục
    </button>
</form>
```

`_flowExecutionKey` giúp Web Flow tìm đúng execution đang chạy; `_eventId_continue` phát event `continue`. Trong ứng dụng thực tế, nên dùng thẻ hoặc cơ chế render URL của Spring Web Flow để tạo execution URL, tránh tự duy trì các giá trị nội bộ này bằng JavaScript.

## 2. Đọc tham số khởi chạy flow

Khi người dùng mở một URL khởi chạy flow, các query parameter có thể được đọc qua `requestParameters`. Ví dụ URL chứa `bookingId`:

```text
/booking?bookingId=B-1042
```

Flow có thể dùng tham số đó để tải bản ghi:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <on-start>
        <evaluate expression="bookingService.findAccessible(requestParameters.bookingId)"
                  result="flowScope.booking" />
    </on-start>

    <decision-state id="checkBooking">
        <if test="flowScope.booking != null"
            then="review"
            else="notFound" />
    </decision-state>

    <view-state id="review" view="booking/review" />
    <end-state id="notFound" view="booking/not-found" />
</flow>
```

`requestParameters.bookingId` đọc giá trị từ request hiện tại. Service `findAccessible` trong ví dụ cần kiểm tra cả việc bản ghi tồn tại lẫn người dùng hiện tại có quyền truy cập. Biết một ID không đồng nghĩa có quyền xem hoặc sửa bản ghi đó.

Không nên đưa toàn bộ object hoặc dữ liệu nhạy cảm lên query string. URL có thể được lưu trong browser history, access log, analytics, proxy log và đôi khi được gửi trong header `Referer`. Chỉ truyền mã tham chiếu tối thiểu; tải dữ liệu thật qua service có kiểm tra quyền.

Nếu tham số bắt buộc bị thiếu hoặc sai định dạng, hãy chuyển đến state thông báo hoặc kết thúc flow theo quy tắc rõ ràng. Không gọi service với `null` rồi để lỗi runtime quyết định hành vi.

## 3. Phân biệt tham số request với dữ liệu sống trong flow

`requestParameters` phản ánh request hiện tại. Khi người dùng gửi request tiếp theo, request parameters trước đó không tự động trở thành dữ liệu lâu dài của flow. Nếu cần dùng tham số ở nhiều state, hãy kiểm tra rồi lưu vào scope có vòng đời phù hợp.

```xml
<on-start>
    <evaluate expression="requestParameters.bookingId"
              result="flowScope.bookingId" />
    <evaluate expression="bookingService.findAccessible(flowScope.bookingId)"
              result="flowScope.booking" />
</on-start>
```

Trong ví dụ này, `bookingId` được sao chép vào `flowScope` để các state sau có thể dùng. Có thể kiểm tra giá trị trước khi gọi service bằng decision state hoặc một service facade nhận và xác thực tham số. Nếu tham số chỉ cần trong request hiện tại, không cần lưu vào `flowScope`.

Chọn scope theo vòng đời:

- `requestScope`: chỉ dùng trong request hiện tại.
- `flashScope`: thông tin ngắn hạn cần hiển thị qua ranh giới request tiếp theo.
- `viewScope`: dữ liệu chỉ phục vụ view state hiện tại.
- `flowScope`: dữ liệu cần tồn tại qua nhiều state của một flow execution.
- `conversationScope`: dữ liệu cần chia sẻ giữa flow cha và subflow trong cùng conversation.

Nếu cần trả dữ liệu sau khi flow kết thúc, khai báo output ở end state hoặc lưu dữ liệu bền vững qua service trước khi kết thúc. Không trông chờ `requestParameters` còn tồn tại sau nhiều lần chuyển state.

## 4. Chuyển hướng đến URL bên ngoài bằng externalRedirect

Khi flow hoàn tất một nghiệp vụ và cần đưa trình duyệt đến một URL khác, có thể dùng view đặc biệt `externalRedirect:`. Ví dụ kết thúc flow sau khi xác nhận:

```xml
<end-state id="completed"
           view="externalRedirect:/booking/confirmation?bookingId=#{flowScope.booking.id}" />
```

Đích redirect là trang xác nhận của ứng dụng. Biểu thức `#{...}` lấy mã booking từ flow context khi tạo đích chuyển hướng. Nếu cần nhiều query parameter trong XML, ký tự `&` phải được escape thành `&amp;`:

```xml
<end-state id="completed"
           view="externalRedirect:/booking/confirmation?bookingId=#{flowScope.booking.id}&amp;source=webflow" />
```

Chỉ đưa dữ liệu cần thiết vào query string. Nếu giá trị có thể chứa khoảng trắng, dấu `&`, `?`, `#`, dấu tiếng Việt hoặc ký tự đặc biệt, phải mã hóa từng giá trị theo quy tắc URL. Với URL phức tạp, hãy tạo URI bằng một thành phần chuyên trách ở tầng Java thay vì nối chuỗi thủ công. Đảm bảo cú pháp expression template và cách xử lý URL tương thích với phiên bản Spring Web Flow đang dùng.

`externalRedirect:` phù hợp khi cần chuyển trình duyệt đến một URL ngoài flow hiện tại, chẳng hạn trang xác nhận, trang đăng nhập tập trung hoặc hệ thống thanh toán. Với điều hướng giữa các state của cùng flow, dùng transition. Không tạo redirect HTTP chỉ để đi từ một state nội bộ sang state kế tiếp.

## 5. Chuyển sang một flow khác bằng flowRedirect

Khi một quy trình hoàn tất và cần bắt đầu một flow độc lập, có thể dùng view đặc biệt `flowRedirect:` để khởi chạy flow đích:

```xml
<end-state id="bookingCompleted"
           view="flowRedirect:bookingSummary?bookingId=#{flowScope.booking.id}" />
```

Ở ví dụ này, flow `bookingSummary` được khởi chạy với mã đặt lịch làm tham số đầu vào trên URL. Flow đích đọc `requestParameters.bookingId`, tải bản ghi và kiểm tra quyền truy cập như khi nhận một request khởi chạy bình thường.

Flow redirect tạo một lần khởi chạy flow đích; nó không tiếp tục execution cũ. Nếu mục đích là trả kết quả từ subflow về flow cha, hãy dùng `subflow-state` và output mapping. Nếu chỉ muốn chuyển sang state khác trong cùng execution, dùng transition. Phân biệt ba trường hợp này giúp tránh tạo nhiều execution không cần thiết hoặc làm mất dữ liệu đang nằm trong scope.

Tên flow và URL được đăng ký trong registry phải khớp cấu hình. Nếu flow đích không tồn tại hoặc không được registry tìm thấy, redirect sẽ thất bại. Hãy kiểm thử URL thực tế được `FlowHandlerMapping` ánh xạ, nhất là khi flow nằm trong thư mục con hoặc ứng dụng có context path.

## 6. Kiểm soát redirect target bằng allowlist

Một rủi ro bảo mật phổ biến là lấy trực tiếp URL do trình duyệt gửi rồi chuyển hướng đến đó:

```text
/booking/finish?returnUrl=https://example-attacker.invalid
```

Nếu flow sử dụng `returnUrl` mà không kiểm tra, kẻ tấn công có thể tạo liên kết khiến người dùng bị chuyển đến trang giả mạo. Đây là lỗi open redirect. Người dùng thường tin tưởng domain của ứng dụng trước khi bị đưa đến một trang không đáng tin.

Hãy quyết định đích chuyển hướng từ dữ liệu phía máy chủ hoặc ánh xạ một khóa lựa chọn sang danh sách đích cố định. Ví dụ, service chỉ cho phép các đích nội bộ:

```java
public class RedirectTargetService {

    public String resolve(String destination) {
        if ("summary".equals(destination)) {
            return "/booking/summary";
        }
        if ("home".equals(destination)) {
            return "/home";
        }
        return "/booking/complete";
    }
}
```

Flow nhận một khóa ngắn, gọi service để ánh xạ thành đích được phép:

```xml
<action-state id="resolveReturnTarget">
    <evaluate expression="redirectTargetService.resolve(requestParameters.destination)"
              result="flowScope.returnPath" />
    <transition to="leaveFlow" />
</action-state>

<end-state id="leaveFlow"
           view="externalRedirect:#{flowScope.returnPath}" />
```

Ví dụ này giả định `returnPath` chỉ có thể nhận các đường dẫn cố định do service trả về. Nếu cần chuyển hướng đến domain bên ngoài, hãy dùng allowlist gồm scheme, host và port được phép; kiểm tra URL sau khi parse, chuẩn hóa và xử lý cả trường hợp URL dạng `//host`, user-info, ký tự mã hóa hoặc redirect lồng. Không chỉ kiểm tra bằng `startsWith("https://trusted.example")`, vì cách đó có thể chấp nhận hostname giả mạo như `trusted.example.attacker.invalid`.

Không cho phép redirect đến `javascript:`, `data:` hoặc scheme không cần thiết. Với đường dẫn nội bộ, chuẩn hóa path và ngăn path traversal hoặc các dạng URL có thể thoát khỏi context của ứng dụng. Đích mặc định phải an toàn khi tham số thiếu hoặc không hợp lệ.

## 7. Nhận tham số trả về từ hệ thống bên ngoài

Một quy trình thanh toán thường rời ứng dụng để đến cổng thanh toán rồi quay lại bằng một callback URL. Cổng thanh toán có thể gửi `orderId`, `transactionId`, `status` hoặc chữ ký trong query string/request. Những giá trị này là dữ liệu đầu vào chưa được tin cậy.

Ví dụ URL quay về:

```text
/payment/return?orderId=O-1042&transactionId=T-9081&status=success
```

Flow không nên kết thúc thanh toán chỉ vì `status=success`. Thay vào đó, gọi service phía máy chủ để xác minh chữ ký, đối chiếu transaction với order, kiểm tra số tiền và trạng thái giao dịch qua API đáng tin cậy của nhà cung cấp:

```xml
<on-start>
    <evaluate expression="paymentReturnService.verify(requestParameters)"
              result="flowScope.paymentResult" />
</on-start>

<decision-state id="checkPaymentResult">
    <if test="flowScope.paymentResult.verified and flowScope.paymentResult.paid"
        then="paymentConfirmed"
        else="paymentNotConfirmed" />
</decision-state>
```

`paymentReturnService.verify` là service do ứng dụng định nghĩa. Service cần xác minh chữ ký theo giao thức của nhà cung cấp, kiểm tra transaction chưa được xử lý trước đó và bảo đảm order thuộc người dùng/phiên nghiệp vụ hiện tại. Chỉ khi xác minh thành công mới cập nhật trạng thái đơn hàng. Query parameter `status` có thể dùng để hiển thị hoặc hỗ trợ tra cứu, nhưng không phải bằng chứng xác nhận.

Nếu nhà cung cấp yêu cầu một `returnUrl`, hãy đăng ký URL callback cố định ở phía máy chủ hoặc tạo URL có chữ ký và thời hạn. Không nhận một callback URL tùy ý từ form rồi gửi cho cổng thanh toán. Với luồng thanh toán, cần thêm idempotency để request callback gửi lặp không tạo nhiều lần ghi nhận giao dịch.

## 8. Phân biệt redirect với forward và transition

Các cơ chế điều hướng khác nhau về việc trình duyệt có gửi request mới hay không:

| Cơ chế | Hành vi | Khi nên dùng |
| --- | --- | --- |
| Transition | Web Flow chuyển state trong cùng flow execution theo event. | Điều hướng giữa các bước của cùng quy trình. |
| Subflow transition | Flow cha gọi flow con, rồi nhận event/output khi flow con kết thúc. | Quy trình con có vòng đời riêng nhưng cần trả kết quả cho cha. |
| External redirect | Máy chủ trả redirect để trình duyệt mở URL khác. | Chuyển sang URL ngoài flow hoặc domain khác đã được cho phép. |
| Flow redirect | Khởi chạy một flow khác qua URL của flow registry. | Bắt đầu quy trình độc lập mới. |
| Forward nội bộ | Máy chủ chuyển xử lý trong cùng request theo cơ chế servlet/view. | Trường hợp tích hợp web truyền thống khi thực sự cần giữ nguyên request. |

Redirect thường làm trình duyệt phát request mới; do đó query parameter có thể xuất hiện trong URL đích và được lưu trong history. Forward không đổi URL trên trình duyệt. Transition nội bộ do Web Flow điều khiển state và execution. Không dùng thuật ngữ “redirect” chung cho mọi hình thức chuyển state, vì cách xử lý dữ liệu và vòng đời khác nhau.

## 9. Tránh lặp request và redirect loop

Điều hướng sai có thể tạo vòng lặp: trang A redirect sang B, B lại redirect về A. Một số nguyên nhân thường gặp:

- URL callback trỏ về chính endpoint đang redirect.
- Flow đích yêu cầu tham số bắt buộc nhưng URL redirect không truyền tham số đó.
- Đích redirect yêu cầu đăng nhập, còn logic đăng nhập lại redirect về đích cũ không hợp lệ.
- Flow kết thúc nhưng view hoặc handler tiếp tục khởi chạy lại flow ban đầu.
- Request callback được gửi lặp và logic nghiệp vụ lại tạo redirect như thể giao dịch chưa xử lý.

Để tránh lặp:

1. Vẽ rõ nguồn và đích của từng redirect, bao gồm trường hợp thành công, hủy và lỗi.
2. Đảm bảo URL đích không kích hoạt lại cùng điều kiện redirect.
3. Dùng trạng thái nghiệp vụ/idempotency key để xử lý callback gửi nhiều lần.
4. Có đích fallback an toàn khi tham số trả về thiếu hoặc không hợp lệ.
5. Ghi log flow ID, state, redirect target đã chuẩn hóa và correlation ID để chẩn đoán; không ghi token hoặc dữ liệu nhạy cảm.

Với form POST, cân nhắc hành vi POST/Redirect/GET để tránh trình duyệt gửi lại thao tác khi người dùng refresh. Tuy nhiên, redirect không thay thế idempotency: client, proxy hoặc nhà cung cấp vẫn có thể gửi request lặp.

## 10. Kiểm thử tham số và redirect target

Kiểm thử URL/navigation nên bao phủ cả dữ liệu đầu vào, đích được tạo và hành vi trình duyệt:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Flow khởi chạy với `bookingId` hợp lệ | Service tải đúng bản ghi và kiểm tra quyền truy cập. |
| Thiếu `bookingId` | Flow đi đến state thông báo hoặc fallback đã định nghĩa. |
| `bookingId` sai định dạng | Không phát sinh lỗi runtime; dữ liệu được từ chối có chủ đích. |
| Redirect đến trang xác nhận | URL đích đúng path và query parameter cần thiết. |
| Tham số `destination` nằm ngoài allowlist | Service trả đích fallback an toàn. |
| Redirect URL chứa ký tự đặc biệt | Query parameter được encode đúng, không bị tách thành tham số ngoài ý muốn. |
| Callback thanh toán giả mạo `status=success` | Service xác minh thất bại; đơn hàng không được đánh dấu đã thanh toán. |
| Callback hợp lệ gửi lặp | Giao dịch chỉ được ghi nhận một lần. |
| Flow redirect sang flow không tồn tại | Test phát hiện registry/URL mapping sai. |
| Redirect loop | Test hoặc kiểm thử tích hợp xác nhận chuỗi điều hướng kết thúc. |

Trong flow execution test, có thể đặt request parameter vào `MockExternalContext`, khởi chạy flow rồi kiểm tra state và scope. Với redirect, dùng MVC integration test để kiểm tra status code, `Location` header và URL đã encode. Không chỉ assert chuỗi redirect trong unit test của service; cần kiểm tra handler thực sự tạo response như dự kiến.

Với allowlist, thử các giá trị như `https://trusted.example.attacker.invalid`, `//attacker.invalid`, `javascript:alert(1)`, URL có user-info và path chứa ký tự mã hóa. Tất cả phải bị từ chối hoặc ánh xạ về đích an toàn. Với callback, kiểm thử chữ ký sai, transaction không khớp order, amount không khớp và request trùng.

## 11. Checklist trước khi phát hành flow

- Đã phân biệt flow ID, query parameter nghiệp vụ, event parameter và execution key chưa?
- Tham số URL đã được kiểm tra định dạng, quyền truy cập và trạng thái nghiệp vụ chưa?
- Dữ liệu cần qua nhiều state đã được lưu vào scope phù hợp chưa?
- Đã chọn transition, subflow, `flowRedirect:` hay `externalRedirect:` theo đúng mục đích chưa?
- Redirect target có đến từ server-side allowlist hoặc nguồn tin cậy không?
- Query parameter đã được encode và không chứa secret hoặc dữ liệu nhạy cảm chưa?
- Callback từ hệ thống bên ngoài đã được xác minh chữ ký và idempotency chưa?
- Có đích fallback cho tham số thiếu, sai hoặc flow đích không khả dụng không?
- Đã kiểm thử `Location` header, URL mapping, redirect loop và request lặp chưa?

Khi những điều kiện này được đáp ứng, URL trở thành giao diện điều hướng có kiểm soát giữa trình duyệt, flow execution và các hệ thống liên quan. Spring Web Flow tiếp tục quản lý state và event của quy trình; service xác thực dữ liệu và quyền truy cập; còn redirect chỉ đưa người dùng đến đích đã được ứng dụng cho phép.
