# Liên kết cũ sau khi flow đã hoàn thành

> **Chương:** Lịch sử trình duyệt  
> **Module:** SPRING_WEB_FLOW  
> **Mục tiêu:** Hiểu vì sao URL/execution key cũ có thể còn trong browser history, bookmark hoặc email sau khi một Spring Web Flow đã kết thúc; biết cách xử lý request tiếp tục execution đã đóng/hết hạn, thiết kế trang đích ổn định, ngăn submit lặp và kiểm thử Back, Forward, Refresh.

## 1. Vấn đề: flow kết thúc nhưng liên kết vẫn còn

Một khách hàng hoàn tất quy trình đặt lịch:

~~~text
chooseSlot → contact → review → reserve → completed
~~~

Trong quá trình sử dụng, trình duyệt có thể lưu lại nhiều URL:

- URL khởi tạo flow.
- URL chứa execution key để tiếp tục một lần chạy cụ thể.
- URL của trang review trước khi xác nhận.
- URL hiển thị kết quả hoàn tất.

Sau khi flow kết thúc, người dùng có thể:

1. Nhấn **Back** để quay lại trang review.
2. Nhấn **Forward** để trở lại trang hoàn tất.
3. Refresh trang cũ.
4. Mở bookmark đã lưu từ lần trước.
5. Nhấp liên kết trong email được gửi từ một phiên flow cũ.
6. Mở cùng URL trong tab khác hoặc gửi lại request từ lịch sử.

Những liên kết này có thể vẫn hiển thị trong thanh địa chỉ hoặc browser history, nhưng **không có nghĩa flow execution còn hoạt động**.

Điều cần phân biệt:

- **URL:** địa chỉ mà trình duyệt đang yêu cầu.
- **Flow ID:** tên quy trình được đăng ký trong FlowRegistry.
- **Execution key:** khóa dùng để tiếp tục một flow execution theo cơ chế Web Flow.
- **FlowExecution:** một lần chạy có state và dữ liệu riêng.
- **Kết quả nghiệp vụ:** booking/order đã được ghi bền vững trong hệ thống.

Một flow đã kết thúc không thể được “mở lại” chỉ bằng cách quay lại URL cũ. Ứng dụng phải xác định request đó có thể tiếp tục execution, phải bắt đầu flow mới hay cần hiển thị trang kết quả đã lưu.

## 2. Flow execution và liên kết trình duyệt khác nhau thế nào?

Spring Web Flow cho phép một hành trình tồn tại qua nhiều HTTP request. Framework lưu và khôi phục execution thông qua cơ chế repository và execution key theo cấu hình.

~~~mermaid
flowchart TD
    A["GET /booking"] --> B["FlowExecutor khởi tạo execution"]
    B --> C["chooseSlot"]
    C --> D["review"]
    D --> E["reserve"]
    E --> F["completed / end-state"]
    C -.-> H["Browser history giữ URL cũ"]
    D -.-> H
    F --> G["Flow execution kết thúc"]
    H --> I["Người dùng mở lại URL cũ"]
    I --> J{"Execution key còn hợp lệ?"}
    J -->|"Có theo repository/config"| K["Tiếp tục theo execution đã lưu"]
    J -->|"Không"| L["Xử lý stale/expired execution"]
    G --> M["Kết quả nghiệp vụ được lưu riêng"]
    L --> N["Trang thông báo hoặc trang kết quả ổn định"]
    M --> N
~~~

Sơ đồ mô tả hai vòng đời độc lập:

- Browser có thể giữ URL trong history lâu hơn thời gian sống của flow execution.
- Booking/order có thể tồn tại lâu dài trong database sau khi execution đã kết thúc.

**Không dùng browser history làm kho lưu trạng thái nghiệp vụ.** Một trang cũ chỉ là một bản điều hướng phía client; dữ liệu bền vững phải được tra cứu từ hệ thống.

### 2.1. Execution key không phải mã kết quả

Một URL minh họa:

~~~text
/booking?execution=e1s4
~~~

Giá trị **e1s4** chỉ là minh họa. Trong thực tế, tên tham số và định dạng key phụ thuộc URL generation, repository và cấu hình của Web Flow.

Execution key giúp framework xác định execution/snapshot cần tiếp tục. Nó không nên được dùng như:

- Booking ID để tra cứu nghiệp vụ.
- Bằng chứng người dùng sở hữu booking.
- Token xác thực.
- Idempotency key của thao tác đặt lịch.
- Liên kết công khai có thể chia sẻ để người khác truy cập dữ liệu.

### 2.2. Flow ID không xác định một lần chạy cụ thể

**booking** có thể là Flow ID dùng chung cho hàng nghìn khách hàng. Mỗi người dùng/lần mở flow có execution riêng. Vì vậy, URL bắt đầu flow và URL tiếp tục một execution có mục đích khác nhau.

Nếu người dùng mở lại URL bắt đầu flow, ứng dụng có thể khởi tạo một execution mới theo cấu hình handler. Nếu họ mở URL mang execution key cũ, framework cố gắng tiếp tục execution tương ứng; hai hành vi không được coi là giống nhau.

## 3. Điều gì xảy ra khi flow đi vào end-state?

Một flow có thể khai báo:

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingAction.reserve(requestContext)"/>
    <transition on="booked" to="completed"/>
</action-state>

<end-state id="completed" view="booking/completed"/>
~~~

Khi action phát event **booked**, execution đi đến **completed**. End-state biểu thị flow session kết thúc theo mô hình điều khiển. Framework hoàn tất execution theo lifecycle và repository đang cấu hình.

Các chi tiết như snapshot nào còn được giữ, key cũ được chấp nhận trong bao lâu, request tiếp tục sau end-state trả lỗi hay được handler chuyển hướng phụ thuộc implementation/repository/version và cách ứng dụng tích hợp.

**Không nên viết logic sản phẩm dựa trên giả định rằng mọi URL sau end-state đều trả đúng một HTTP status cố định.** Hãy thiết kế một hành vi stale-link rõ ràng ở ranh giới web và kiểm thử với repository thực tế.

### 3.1. End-state không phải trang có thể mở mãi bằng execution key

Thuộc tính **view="booking/completed"** chỉ định view dùng để trình bày kết quả ở điểm kết thúc theo flow definition. Nó không tự tạo một URL vĩnh viễn để xem booking.

Nếu người dùng cần xem lại kết quả ngày mai, tuần sau hoặc từ email, hãy cung cấp một **trang kết quả ổn định** dựa trên booking ID và kiểm tra quyền truy cập.

### 3.2. Kết thúc flow không xóa kết quả nghiệp vụ

Giả sử **bookingService.reserveOnce()** đã commit booking với ID **B-1042**. Sau đó flow kết thúc. Dù execution key cũ không còn sử dụng được, booking **B-1042** vẫn tồn tại trong database.

Không xóa booking khi flow execution bị dọn khỏi repository. Ngược lại, không giữ flow execution vô hạn chỉ để người dùng xem lại booking.

## 4. Browser Back và Forward sau khi hoàn tất

Browser history lưu các mục điều hướng ở phía trình duyệt. Hành vi khi Back/Forward phụ thuộc browser, cache policy, redirect và loại response.

### 4.1. Back có thể hiển thị nội dung cũ mà chưa gửi request

Người dùng nhấn Back và thấy form review. Điều đó không chứng minh:

- Server đã khôi phục execution.
- Execution key còn hợp lệ.
- State hiện tại vẫn là **review**.
- Booking chưa được tạo.
- Người dùng còn quyền xác nhận.

Browser có thể hiển thị trang đã cache. Chỉ khi người dùng gửi request tiếp theo, server mới xử lý request với session, CSRF, execution key và quyền hiện hành.

### 4.2. Forward cũng không khôi phục trạng thái server

Forward có thể đưa người dùng trở lại một trang hoàn tất đã lưu trong browser. Nội dung đó có thể cũ so với trạng thái booking hiện tại.

Nếu booking đã bị hủy hoặc cập nhật sau khi trang được render, browser vẫn có thể hiển thị bản cũ. Khi cần dữ liệu mới, trang kết quả nên tải từ endpoint đọc dữ liệu hiện hành và kiểm tra quyền.

### 4.3. Refresh có thể gửi lại request

Nếu trang hiện tại được tạo từ POST, refresh có thể khiến browser hỏi người dùng có muốn gửi lại form hay không. Nếu request cũ là **confirm**, gửi lại có thể lặp thao tác ghi nếu service không được bảo vệ.

Không dựa vào nút Back, cảnh báo browser hay tên end-state để ngăn duplicate booking. **Idempotency phải được bảo vệ ở tầng nghiệp vụ/database.**

## 5. Liên kết cũ có thể xuất hiện ở đâu?

| Nguồn liên kết | Vì sao cũ? | Cách xử lý nên cân nhắc |
| --- | --- | --- |
| Browser Back/Forward | History giữ trang từ trước khi flow kết thúc | Render lại dữ liệu hiện hành khi có request; xử lý stale execution |
| Bookmark | Người dùng lưu URL mang execution key | Hướng dẫn mở trang bắt đầu flow hoặc trang kết quả ổn định |
| Email | Email chứa URL của execution cũ | Gửi liên kết tới trang tra cứu/kết quả có token nghiệp vụ an toàn hoặc yêu cầu đăng nhập |
| Chat/tài liệu nội bộ | URL được copy từ thanh địa chỉ | Không xem execution key là liên kết chia sẻ lâu dài |
| Tab thứ hai | Tab khác giữ snapshot cũ | Xử lý execution hết hạn và submit trùng |
| Lịch sử form POST | Browser có thể gửi lại request | PRG khi phù hợp và idempotency ở service |
| Trang cache | Nội dung cũ còn ở client | Chính sách cache phù hợp; xác minh quyền và dữ liệu trên server |

Một liên kết có thể **cũ về execution** nhưng vẫn có ích nếu nó dẫn tới trang đích ổn định. Vì vậy, nên tách URL điều khiển flow khỏi URL tra cứu kết quả.

## 6. Thiết kế URL cho trang hoàn tất ổn định

Thay vì gửi email chứa URL tiếp tục execution:

~~~text
/booking?execution=e1s4
~~~

hãy dẫn người dùng tới một route kết quả có định danh nghiệp vụ:

~~~text
/bookings/B-1042
~~~

URL này chỉ là ví dụ. Endpoint thực tế phải:

1. Xác thực người dùng nếu nội dung yêu cầu đăng nhập.
2. Kiểm tra principal có quyền xem booking ID đó.
3. Tải trạng thái booking mới nhất từ service/database.
4. Không phụ thuộc flow execution cũ.
5. Trả thông báo phù hợp nếu booking không tồn tại, đã bị hủy hoặc không thuộc người dùng.

### 6.1. Booking ID không tự động là bí mật hoặc quyền truy cập

ID có thể được đoán, copy hoặc lộ trong log. Không coi ID dạng **B-1042** là authorization token.

Nếu nghiệp vụ cần liên kết trong email cho người dùng chưa đăng nhập, thiết kế một **token truy cập có chủ đích** với:

- Entropy đủ lớn và khó đoán.
- Scope chỉ cho đúng thao tác cần thiết.
- Hạn dùng rõ ràng.
- Cơ chế thu hồi/đổi token khi cần.
- Không đưa thông tin nhạy cảm trực tiếp vào URL.
- Không dùng lại execution key của Web Flow làm token email.

Khi có thể, yêu cầu đăng nhập và kiểm tra ownership vẫn là phương án dễ quản lý hơn.

### 6.2. Trang kết quả nên là read-only

Trang **/bookings/B-1042** thường chỉ hiển thị trạng thái đã lưu. Nếu người dùng muốn đổi giờ hoặc hủy, hãy yêu cầu một thao tác nghiệp vụ riêng, có quyền và xác nhận thích hợp.

Không dùng GET để tạo booking, hủy booking hoặc thay đổi trạng thái. GET phải giữ tính chất đọc để browser prefetch, crawler hoặc refresh không tạo side effect.

## 7. Post/Redirect/Get sau khi flow hoàn tất

Một nguyên tắc web hữu ích là **Post/Redirect/Get (PRG)**:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as FlowExecutor
    participant S as BookingService
    participant R as ResultController
    U->>B: Submit confirm
    B->>F: POST event=confirm
    F->>S: reserveOnce(requestId)
    S-->>F: Booking B-1042 confirmed
    F-->>B: Redirect tới URL kết quả ổn định
    B->>R: GET /bookings/B-1042
    R->>S: findAuthorizedBooking(B-1042, principal)
    S-->>R: Booking result
    R-->>B: Trang kết quả
~~~

Sơ đồ minh họa kiến trúc mong muốn. Cách redirect cụ thể phụ thuộc cách kết thúc flow, end-state view, MVC handler và cấu hình Web Flow.

Lợi ích:

- Refresh trang kết quả gửi lại GET, không lặp POST xác nhận.
- Bookmark trỏ đến trang kết quả ổn định.
- Email có thể trỏ tới trang tra cứu đã bảo vệ.
- Kết quả được tải từ dữ liệu hiện hành.

### 7.1. End-state view và redirect là hai lựa chọn cần thiết kế

Một end-state có thể được cấu hình để render view kết thúc. Trong một số ứng dụng, việc render view này là đủ cho response cuối cùng. Nếu cần URL kết quả ổn định, hãy thiết kế redirect/landing route phù hợp với integration đang dùng.

Không giả định chỉ cần thêm thuộc tính view vào end-state là browser sẽ tự nhận URL mới có thể bookmark lâu dài.

### 7.2. Tránh redirect quay lại execution đã đóng

Một redirect tới URL vẫn mang execution key cũ có thể tạo vòng lặp hoặc lỗi stale execution. URL đích phải độc lập với execution đã kết thúc, hoặc phải bắt đầu một flow mới theo ý định rõ ràng.

## 8. Xử lý request mang execution key cũ

Khi nhận request tiếp tục flow, framework cần tìm execution tương ứng trong repository. Nếu key không còn hợp lệ, repository không thể khôi phục execution theo yêu cầu.

Nguyên nhân thường gặp:

- Flow đã kết thúc.
- Snapshot cũ đã bị loại bỏ theo chính sách repository.
- Execution hết hạn.
- Session đã hết hạn hoặc bị hủy.
- Key sai, bị sửa hoặc không thuộc context hiện tại.
- Ứng dụng đã restart và repository lưu execution trong memory không còn dữ liệu.
- Flow definition/version thay đổi làm execution cũ không thể tiếp tục.

### 8.1. Không đồng nhất mọi trường hợp với “flow đã hoàn tất”

Một execution key không hợp lệ có thể do:

| Tình huống | Ý nghĩa |
| --- | --- |
| Execution đã kết thúc | Quy trình đã đi đến end-state |
| Snapshot hết hạn | Execution có thể từng hợp lệ nhưng repository đã dọn |
| Session hết hạn | Ngữ cảnh người dùng không còn |
| Key sai/giả mạo | Request không trỏ tới execution hợp lệ |
| Repository mất dữ liệu | Hạ tầng không còn snapshot cần khôi phục |
| Version incompatibility | Snapshot cũ không tương thích code/definition mới |

Phản hồi nên đủ an toàn để không tiết lộ execution nào tồn tại, đồng thời giúp người dùng biết bước tiếp theo.

### 8.2. HTTP status và thông báo phụ thuộc integration

Không có một HTTP status duy nhất phù hợp cho mọi lỗi stale execution. Ứng dụng có thể trả trang thông báo, redirect đến trang bắt đầu, hoặc để handler MVC xử lý exception theo chính sách.

Điều quan trọng là:

- Không tự động chạy lại action ghi.
- Không lộ stack trace hoặc execution key.
- Không tuyên bố booking thất bại nếu kết quả chưa được đối soát.
- Có đường tra cứu kết quả nghiệp vụ khi thao tác trước đó có thể đã commit.

## 9. Tách stale-link handler khỏi logic nghiệp vụ

Một handler ở tầng web có thể nhận biết request không thể tiếp tục execution và đưa người dùng đến trang hướng dẫn.

~~~java
// Minh họa ý tưởng; API exception/handler phải khớp phiên bản SWF/MVC.
public ModelAndView handleExpiredFlowLink(Exception exception) {
    return new ModelAndView("flow/expired-link");
}
~~~

Trang **flow/expired-link** có thể giải thích:

- Liên kết đã hết hiệu lực.
- Nếu người dùng vừa hoàn tất, hãy mở trang kết quả hoặc mục lịch sử.
- Nếu chưa hoàn tất, hãy bắt đầu một flow mới.
- Nếu trạng thái thanh toán/đặt lịch chưa rõ, hãy tra cứu bằng mã yêu cầu.

**Không gọi bookingService.reserveOnce() trong stale-link handler.** Handler giải quyết điều hướng và trải nghiệm lỗi; service mới là nơi kiểm soát giao dịch.

### 9.1. Handler phải tránh redirect loop

Nếu trang expired-link lại nằm trong cùng flow và yêu cầu execution key cũ, request có thể tiếp tục thất bại. Hãy dùng route MVC độc lập hoặc trang tĩnh không phụ thuộc execution cũ.

### 9.2. Không tự động khởi tạo flow mới khi nhận mọi key cũ

Tự động chuyển mọi request stale sang flow mới có thể:

- Tạo nhiều execution không cần thiết.
- Làm người dùng tưởng một thao tác cũ chưa hoàn thành.
- Mất dữ liệu draft hoặc tạo lại hành động ghi.
- Tạo đường bypass nếu flow mới có logic khởi tạo side effect.

Chỉ bắt đầu flow mới khi đó là hành vi người dùng chủ động chọn, ví dụ nút **Bắt đầu đặt lịch mới**.

## 10. Chống submit lặp khi người dùng quay lại trang review

Một kịch bản:

1. Người dùng mở review.
2. Nhấn confirm.
3. Service tạo booking và commit.
4. Response bị mất hoặc browser chưa nhận redirect.
5. Người dùng nhấn Back và gửi lại form cũ.

Nếu service tạo booking mới mỗi lần gọi, một ý định đặt lịch có thể tạo nhiều bản ghi.

### 10.1. Idempotency ở service

Tạo request ID một lần cho ý định đặt lịch và lưu trong draft:

~~~java
public ReservationResult reserveOnce(
        AppointmentDraft draft,
        String currentUserId) {

    String requestId = draft.getRequestId();

    return reservationRepository.findByRequestId(requestId)
            .map(ReservationResult::alreadyCreated)
            .orElseGet(() -> createUnderUniqueConstraint(
                    requestId, draft, currentUserId));
}
~~~

Đây là pseudocode minh họa. Trong implementation thực tế, cần xử lý race condition bằng transaction và unique constraint/idempotency record trong database; mẫu find rồi insert đơn giản không tự chống được hai request đồng thời.

### 10.2. Execution key không phải idempotency key

Execution key dùng để tiếp tục flow. Nếu người dùng bắt đầu flow mới, execution key có thể khác dù đó là cùng một ý định nghiệp vụ.

Idempotency key phải đại diện cho **thao tác nghiệp vụ** và được giữ ổn định qua retry. Không dùng execution key làm idempotency key vì hai vòng đời và mục đích khác nhau.

### 10.3. Bảo vệ cả trường hợp request đồng thời

Hai tab có thể gửi confirm gần như cùng lúc. Cả hai request đều có thể vượt qua kiểm tra “chưa tồn tại” nếu chỉ dùng truy vấn trước khi insert.

Cần một trong các cơ chế phù hợp:

- Unique constraint trên request ID.
- Idempotency table có khóa duy nhất.
- Optimistic/pessimistic locking theo tài nguyên.
- Transaction bảo vệ thao tác kiểm tra và ghi.

Service phải trả lại kết quả đã tạo trước đó khi request ID được dùng lại, thay vì tạo booking thứ hai.

## 11. Session, security và liên kết cũ

Execution key cũ không được xem là bằng chứng người dùng đã đăng nhập. Khi nhận request:

1. Spring Security filter chain xác thực session/token hiện hành.
2. CSRF protection kiểm tra request thay đổi trạng thái.
3. Web Flow kiểm tra execution key/repository theo cơ chế của nó.
4. Service kiểm tra quyền trên booking/order ID.

Một người có URL cũ không mặc nhiên có quyền xem dữ liệu.

### 11.1. Không đặt execution key vào email công khai

Execution URL có thể chứa thông tin dùng để tiếp tục một execution trong thời hạn nhất định. Việc gửi URL đó qua email/chat có thể khiến người khác có được một đường truy cập không mong muốn, tùy security/session configuration.

Email nên trỏ tới:

- Trang đăng nhập rồi điều hướng tới lịch sử của người dùng.
- Trang kết quả có authorization kiểm tra ở server.
- Liên kết xác minh có token giới hạn quyền, thời hạn và có thể thu hồi.

Không gửi URL chứa session ID, token xác thực hoặc execution key nếu không có thiết kế bảo mật rõ ràng.

### 11.2. CSRF và GET

Một stale GET không nên tạo side effect. Các hành động như xác nhận, hủy hoặc đổi lịch phải dùng HTTP method thay đổi trạng thái và được bảo vệ CSRF theo cấu hình.

Không dùng một liên kết GET trong email để trực tiếp hủy booking. Nếu email có nút thao tác, hãy đưa người dùng đến trang xác nhận an toàn rồi gửi POST.

## 12. Cache và dữ liệu cũ trên browser

Ngay cả khi server xử lý stale execution đúng, browser vẫn có thể hiển thị trang đã cache. Với những view nhạy cảm như review hoặc kết quả chứa dữ liệu cá nhân, cân nhắc cache policy phù hợp.

Ví dụ header minh họa:

~~~http
Cache-Control: no-store
~~~

**no-store** có thể phù hợp với trang chứa thông tin nhạy cảm hoặc form có thao tác quan trọng. Tuy nhiên, không áp dụng máy móc cho mọi tài nguyên; ảnh, CSS và nội dung tĩnh có thể có chính sách cache khác.

### 12.1. Cache không thay thế authorization

Header cache giúp giảm khả năng lưu nội dung ở cache theo chính sách HTTP. Nó không thay thế kiểm tra quyền trên mỗi request đọc dữ liệu.

Nếu browser hiển thị một trang cũ, khi người dùng thực hiện hành động mới, server vẫn phải kiểm tra session, CSRF, ownership và trạng thái tài nguyên.

## 13. Browser history với flow lồng nhau và nhiều tab

### 13.1. Subflow đã kết thúc

Flow cha có thể gọi subflow xác minh liên hệ:

~~~xml
<subflow-state id="verifyContact" subflow="verifyContact">
    <input name="email" value="flowScope.booking.email"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="contact"/>
</subflow-state>
~~~

Khi subflow kết thúc, flow cha tiếp tục theo outcome. Một URL cũ của flow con không nên được coi là cách mở lại subflow đã kết thúc. Nếu người dùng muốn xác minh lại, flow cha cần có transition/action khởi tạo một lần xác minh mới theo chính sách.

### 13.2. Nhiều tab

Hai tab có thể:

- Cùng tham chiếu một execution.
- Giữ snapshot khác nhau của cùng execution.
- Tạo hai execution riêng biệt.

Hành vi cụ thể phụ thuộc cách người dùng mở URL và repository. Không giả định tab A hoàn tất thì nội dung đang mở ở tab B tự cập nhật.

Khi tab B submit form cũ, server phải kiểm tra execution và service phải bảo vệ idempotency. Nếu execution đã đóng, hiển thị stale-link message hoặc kết quả đã lưu.

### 13.3. Không giữ trạng thái UI bằng URL cũ

Nếu sản phẩm cần cho người dùng mở lại một bước chưa hoàn tất sau vài ngày, hãy thiết kế **draft bền vững** có ID, quyền sở hữu, hạn dùng và trạng thái rõ ràng. Không giữ flow execution vô hạn chỉ để URL cũ tiếp tục hoạt động.

## 14. Thiết kế trạng thái draft và trang kết quả

~~~text
Flow execution:
  phục vụ điều hướng trong một phiên tương tác
  có thể hết hạn hoặc kết thúc

Booking draft:
  dữ liệu tạm của nghiệp vụ
  có thể được lưu riêng nếu cần tiếp tục lâu dài

Booking:
  kết quả nghiệp vụ đã commit
  có ID và trạng thái bền vững

Result page:
  route đọc booking theo ID
  kiểm tra authentication/authorization
~~~

### 14.1. Draft dài hạn cần vòng đời riêng

Nếu người dùng có thể lưu và tiếp tục booking sau nhiều ngày:

- Lưu draft vào database.
- Gắn owner/principal.
- Có trạng thái DRAFT, SUBMITTED, EXPIRED hoặc tương đương.
- Có thời hạn và chính sách dọn dữ liệu.
- Khi mở lại, khởi tạo flow execution mới từ draft đã kiểm tra quyền.

Đây là một hành trình mới dựa trên dữ liệu nghiệp vụ đã lưu, không phải khôi phục vô hạn một execution key cũ.

### 14.2. Không tái sử dụng flow execution sau end-state

Một execution đã kết thúc không phải đối tượng tái sử dụng cho lần đặt lịch mới. Hãy khởi tạo execution mới hoặc draft mới theo thao tác người dùng. Việc tái sử dụng ID/key cũ làm mờ ranh giới giữa hai ý định nghiệp vụ.

## 15. Kiểm thử liên kết cũ sau khi flow hoàn thành

Kiểm thử cần đi qua browser/repository/service thay vì chỉ kiểm tra XML end-state.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Hoàn tất flow rồi nhấn Back | Trang cũ có thể hiện; request tiếp theo không thực thi ghi trái phép |
| Mở lại URL mang execution key cũ | Hành vi stale execution theo repository được xử lý an toàn |
| Refresh trang kết quả sau redirect | GET tải lại kết quả, không gửi lại lệnh confirm |
| Bookmark URL execution cũ | Có thông báo/link bắt đầu lại hoặc trang kết quả phù hợp |
| Mở URL từ email sau nhiều ngày | Trang đích ổn định và kiểm tra quyền |
| Session hết hạn | Người dùng được yêu cầu xác thực lại; không ghi nghiệp vụ |
| Hai tab submit cùng request ID | Chỉ một booking được tạo |
| Browser gửi lại POST confirm | Idempotency trả kết quả cũ, không tạo trùng |
| Booking bị hủy sau khi trang cache | GET trang kết quả hiển thị trạng thái mới |
| Execution repository restart/cleanup | Key cũ được xử lý theo chính sách, không crash không kiểm soát |
| URL cũ của subflow | Không mở lại subflow đã kết thúc trái quy tắc |
| Người khác mở result URL | Không xem được booking không thuộc quyền |

### 15.1. Flow integration test

~~~text
execution = startFlow("booking")
execution = submit(execution, "next", validDraft)
execution = submit(execution, "confirm")

assert bookingService.createdCount(requestId) == 1
assert flow reached end-state

oldExecutionUrl = capturePreviousExecutionUrl()
response = request(oldExecutionUrl)

assert response does not create another booking
assert response follows stale-link policy
~~~

Đây là pseudocode mô tả ý tưởng, không phải API Java chạy nguyên văn. Test thực tế cần dùng repository, FlowExecutor và servlet/MVC integration đúng phiên bản.

### 15.2. Browser-level test

Một test trình duyệt nên:

1. Mở flow.
2. Đi đến review.
3. Xác nhận booking.
4. Kiểm tra redirect đến URL kết quả.
5. Refresh trang kết quả.
6. Nhấn Back/Forward.
7. Mở URL execution cũ trong tab mới.
8. Gửi lại form cũ nếu browser cho phép.
9. Kiểm tra booking chỉ được tạo một lần và thông tin được bảo vệ.

### 15.3. Test race condition ở service/database

Gửi hai request đồng thời với cùng idempotency key và xác minh:

- Database chỉ có một bản ghi nghiệp vụ.
- Hai request nhận cùng booking ID/kết quả.
- Unique constraint không để lộ lỗi 500 không kiểm soát.
- Flow không phát thông báo thành công trước khi kết quả được xác định.

## 16. Chẩn đoán sự cố stale URL

Khi người dùng báo URL cũ bị lỗi:

1. Xác định URL là URL bắt đầu flow, URL execution hay URL kết quả nghiệp vụ.
2. Không yêu cầu người dùng gửi token/session/execution key qua kênh công khai.
3. Kiểm tra Flow ID và handler mapping.
4. Xác định execution repository đang dùng và chính sách snapshot/expiration.
5. Kiểm tra flow đã vào end-state hay session đã hết hạn.
6. Kiểm tra có booking/order đã được commit không bằng request ID/booking ID.
7. Kiểm tra log có flow/state context và correlation ID.
8. Kiểm tra response/redirect có quay lại URL execution cũ không.
9. Xác minh quyền người dùng trên trang kết quả.
10. Kiểm tra retry có tạo side effect trùng không.

### 16.1. Phân biệt lỗi execution và lỗi tra cứu kết quả

Nếu URL execution cũ không thể khôi phục nhưng booking đã tồn tại, người dùng vẫn có thể xem kết quả qua route nghiệp vụ ổn định. Hai lỗi cần xử lý riêng:

- **Không tiếp tục được flow:** lỗi điều hướng/execution.
- **Không tra cứu được booking:** lỗi nghiệp vụ, quyền hoặc dữ liệu.

Không biến cả hai thành một trang “Booking thất bại”.

### 16.2. Log hữu ích

~~~text
flowId=booking
requestType=resume
executionState=expired_or_ended
resultLookup=found
correlationId=...
action=redirect_to_result
~~~

Đây là định dạng minh họa. Không log nguyên URL có query chứa execution key hoặc token nếu không cần thiết.

## 17. Những thiết kế dễ gây lỗi

**Gửi email chứa execution URL.** Execution key có vòng đời của flow, không phải liên kết kết quả lâu dài. Gửi route tra cứu đã bảo vệ hoặc token có scope/hạn dùng riêng.

**Cho rằng end-state view là bookmark vĩnh viễn.** End-state kết thúc flow session; view không thay thế trang đọc dữ liệu nghiệp vụ ổn định.

**Bắt mọi stale execution rồi tạo flow mới.** Có thể tạo nhiều execution hoặc khiến người dùng vô tình lặp thao tác. Yêu cầu người dùng chủ động bắt đầu lại.

**Dùng execution key làm booking ID.** Hai giá trị có mục đích và vòng đời khác nhau. Dùng ID nghiệp vụ riêng.

**Cho GET thực hiện thao tác ghi.** Refresh, crawler hoặc prefetch có thể kích hoạt side effect. Dùng POST và CSRF.

**Chỉ dựa vào browser warning để chống submit lặp.** Warning không bảo vệ request đồng thời hoặc client khác. Dùng idempotency/unique constraint.

**Giữ flow execution vô hạn để hỗ trợ bookmark.** Tăng tài nguyên và làm mờ vòng đời. Lưu draft/result riêng nếu nghiệp vụ yêu cầu.

**Không kiểm tra quyền trên result URL.** Booking ID có thể bị đoán hoặc chia sẻ. Kiểm tra ownership ở service.

**Redirect tới URL cũ sau khi flow kết thúc.** Có thể gây redirect loop/stale key. Chuyển đến route độc lập với execution.

**Hiển thị dữ liệu cache như trạng thái hiện hành.** Tải lại dữ liệu từ service khi cần và đặt cache policy phù hợp.

## 18. Bài thực hành: xử lý URL cũ của flow đặt lịch

Một flow đặt lịch có hành trình:

~~~text
chooseSlot → contact → review → reserve → completed
~~~

Ứng dụng gửi email xác nhận sau khi booking được tạo. Hiện tại email chứa URL của flow execution đã hoàn tất. Người dùng nhấp lại sau vài ngày và gặp lỗi.

**Yêu cầu:**

1. Phân biệt URL khởi tạo flow, URL tiếp tục execution và URL kết quả booking.
2. Thiết kế route kết quả ổn định, ví dụ **/bookings/{bookingId}**.
3. Kiểm tra authentication và ownership khi tải booking.
4. Thay liên kết email bằng route kết quả hoặc token có scope/hạn dùng rõ ràng.
5. Thiết kế stale-link page độc lập với flow execution.
6. Sau confirm, đưa người dùng tới GET result page theo PRG nếu phù hợp với MVC/Web Flow integration.
7. Tạo request ID ổn định cho thao tác booking và bảo vệ bằng unique constraint/idempotency.
8. Kiểm thử browser Back, Forward, Refresh và mở bookmark cũ.
9. Kiểm thử hai tab submit cùng request ID.
10. Mô phỏng execution repository hết hạn trong khi booking đã commit.
11. Đảm bảo stale URL không tạo booking mới và không lộ thông tin của người khác.
12. Ghi log flow/state/correlation phù hợp mà không ghi raw execution key.

**Bảng thiết kế đầu ra:**

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Booking vừa hoàn tất | Redirect/đi tới trang kết quả |
| Refresh trang kết quả | GET đọc booking hiện hành |
| Mở execution URL cũ | Stale-link handling an toàn |
| Mở result URL hợp lệ | Kiểm tra quyền rồi hiển thị |
| Booking không thuộc user | Từ chối theo chính sách, không lộ dữ liệu |
| Submit confirm lặp | Trả cùng kết quả, không tạo booking thứ hai |
| Kết quả commit chưa rõ | Đối soát theo request ID |

**Tiêu chí đạt:** người dùng có liên kết lâu dài để xem kết quả; flow execution được phép kết thúc và hết hạn; URL cũ không tạo side effect; browser history không được coi là nguồn sự thật; service bảo vệ quyền và tính duy nhất của giao dịch.

## 19. Tổng kết và câu hỏi tự kiểm tra

Sau khi Spring Web Flow đi vào end-state, URL chứa execution key có thể vẫn còn trong browser history, bookmark hoặc email. **Liên kết còn tồn tại không có nghĩa execution còn sống.** Repository và lifecycle quyết định execution có thể tiếp tục hay không; hành vi HTTP cụ thể phụ thuộc cấu hình và phiên bản.

Hãy tách vòng đời flow execution khỏi vòng đời kết quả nghiệp vụ. Dùng route kết quả ổn định theo booking/order ID với kiểm tra quyền; dùng PRG để refresh không lặp POST; dùng request ID/idempotency và ràng buộc database để chống ghi trùng; xử lý stale link bằng trang độc lập với execution cũ. Không gửi execution key như liên kết lâu dài hoặc token xác thực.

**Câu hỏi tự kiểm tra:**

1. Vì sao URL vẫn nằm trong browser history sau khi flow đã hoàn tất?
2. Flow ID, execution key và booking ID khác nhau thế nào?
3. End-state view có tự tạo một URL kết quả lâu dài không?
4. Vì sao browser Back có thể hiển thị trang review cũ mà server không còn execution tương ứng?
5. Khi execution key hết hạn nhưng booking đã commit, người dùng nên xem kết quả qua đâu?
6. PRG giúp giảm vấn đề nào khi refresh trang sau submit?
7. Vì sao execution key không nên dùng làm idempotency key?
8. Một result URL chứa booking ID vẫn cần kiểm tra quyền vì sao?
9. Khi nào nên lưu draft bền vững thay vì giữ flow execution lâu dài?
10. Cần những test nào để chứng minh Back/Forward, stale link và submit đồng thời không gây giao dịch trùng?
