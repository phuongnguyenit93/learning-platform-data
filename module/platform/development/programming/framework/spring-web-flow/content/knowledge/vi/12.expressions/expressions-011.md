# flowExecutionUrl và việc tạo liên kết cho view

Trong Spring Web Flow, một view đang hiển thị thường thuộc về một **flow execution** cụ thể. Khi người dùng nhấn “Tiếp tục”, “Quay lại” hoặc gửi biểu mẫu, request cần quay về đúng execution đang chạy để framework khôi phục trạng thái và phát event tương ứng. Nếu tự ghép URL hoặc tự quản lý execution key, ứng dụng dễ tạo liên kết sai, gửi event tới một execution đã hết hạn hoặc làm mất ngữ cảnh của hành trình.

Spring Web Flow cung cấp biến **flowExecutionUrl** cho view hiện tại. Giá trị này là URL dùng để gửi request trở lại flow execution đang hoạt động. View có thể dùng nó làm đích cho form hoặc gắn event parameter để tạo liên kết điều hướng. Framework chịu trách nhiệm tạo URL gắn với execution hiện tại, nhờ đó view không cần tự tìm và ghép execution key.

Bài học thuộc chương **Biểu thức** của module **Spring Web Flow**. Module này hướng dẫn mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi gặp lỗi.

## 1. flowExecutionUrl là gì?

Khi một flow được khởi chạy, Spring Web Flow tạo một flow execution để theo dõi lần chạy cụ thể đó. Execution chứa trạng thái thực thi, chẳng hạn state hiện tại và dữ liệu trong các scope. Qua mỗi request, framework cần xác định execution nào phải được tiếp tục.

**flowExecutionUrl** là URL mà view hiện tại sử dụng để gửi request về đúng flow execution đó. Web Flow đưa biến này vào ngữ cảnh view khi render view-state. Giá trị URL được tạo dựa trên cấu hình tích hợp web và định danh execution hiện tại.

Ví dụ về cách dùng trong JSP:

~~~jsp
<a href="${flowExecutionUrl}&amp;_eventId=cancel">Hủy</a>
~~~

Liên kết gửi một request tới URL của execution hiện tại và yêu cầu flow xử lý event có tên **cancel**. Tên event phải khớp với transition được khai báo trong flow definition.

Có thể hình dung chu trình như sau:

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant M as Spring MVC
    participant W as FlowExecutor
    participant R as FlowExecutionRepository
    participant F as Flow execution

    U->>M: Request tới URL của flow
    M->>W: Chuyển request cho FlowExecutor
    W->>R: Khôi phục execution hiện tại
    R-->>W: Execution và trạng thái đã lưu
    W->>F: Phát event từ request
    F-->>W: Xử lý state và transition
    W-->>M: Kết quả xử lý / view tiếp theo
    M-->>U: Render view cùng flowExecutionUrl mới
~~~

Sơ đồ mô tả trách nhiệm ở mức khái niệm. Cách định tuyến URL, tham số execution và lưu trữ execution phụ thuộc cấu hình Spring Web Flow của ứng dụng.

flowExecutionUrl là URL tiếp tục một execution đã được tạo. Nó không phải URL khởi chạy một flow hoàn toàn mới, cũng không phải URL tùy ý để điều hướng sang controller khác.

## 2. Phân biệt URL khởi chạy flow và URL của flow execution

Một ứng dụng thường có ít nhất hai loại URL liên quan đến Web Flow:

| Loại URL | Mục đích | Thời điểm sử dụng |
|---|---|---|
| URL khởi chạy flow | Yêu cầu framework bắt đầu một flow mới hoặc xử lý một entry point của flow | Khi người dùng bắt đầu hành trình |
| flowExecutionUrl | Tiếp tục flow execution đang tồn tại và gửi event tới execution đó | Khi view-state đã được render trong một execution |

Ví dụ, một flow đặt lịch có thể được ánh xạ tới URL **/booking**. Khi người dùng chọn “Đặt lịch”, trình duyệt truy cập URL này để khởi chạy flow. Sau khi flow bắt đầu và render view chọn thời gian, view nhận được flowExecutionUrl. Các nút và liên kết trong màn hình đó sử dụng URL được cung cấp để gửi event như **continue** hoặc **cancel**.

Không nên dùng URL khởi chạy flow làm đích cho mọi nút trong các view-state. Làm vậy có thể tạo một execution mới thay vì tiếp tục hành trình hiện tại. Ngược lại, không dùng flowExecutionUrl cũ để bắt đầu một hành trình mới sau khi execution đã kết thúc.

## 3. Tạo liên kết gửi event bằng flowExecutionUrl

Một liên kết điều hướng có thể gửi event bằng cách nối tham số **_eventId** vào URL của execution:

~~~jsp
<nav>
    <a href="${flowExecutionUrl}&amp;_eventId=back">Quay lại</a>
    <a href="${flowExecutionUrl}&amp;_eventId=cancel">Hủy hành trình</a>
</nav>
~~~

Trong flow definition, các event này cần có transition tương ứng:

~~~xml
<view-state id="chooseSlot" view="booking/choose-slot">
    <transition on="back" to="chooseService" />
    <transition on="cancel" to="cancelled" />
    <transition on="continue" to="enterGuest" />
</view-state>
~~~

Khi người dùng nhấn liên kết **back**, request mang event **back** được gửi tới execution hiện tại. Flow engine tìm transition có event phù hợp và chuyển sang state **chooseService**.

Một số điểm cần nhớ:

- Tên event trong _eventId phải trùng với giá trị on của transition.
- Liên kết phải dùng flowExecutionUrl được cung cấp cho view hiện tại.
- Trong HTML, dấu phân cách query parameter nên được viết thành &amp; để markup hợp lệ. Trình duyệt sẽ gửi ký tự & trong request.
- Không tự thêm một execution key giả định hoặc sao chép URL từ một view-state khác.
- Nếu event không có transition phù hợp, flow có thể không xử lý được request theo cách mong muốn; cần kiểm tra event và flow definition.

Tên event nên mô tả ý định điều hướng hoặc hành động của người dùng, chẳng hạn **back**, **cancel**, **continue** hoặc **showDetails**. Tránh dùng tên chung chung như **action1**, vì khó đọc và khó bảo trì khi flow có nhiều state.

## 4. Dùng flowExecutionUrl cho form

Với dữ liệu nhập từ người dùng, form thường là lựa chọn phù hợp. Form gửi dữ liệu và event tới execution hiện tại trong cùng request.

Ví dụ JSP dùng Spring form tag:

~~~jsp
<form:form modelAttribute="bookingForm"
           action="${flowExecutionUrl}"
           method="post">

    <label for="guestName">Họ tên</label>
    <form:input path="guestName" id="guestName" />

    <label for="guestEmail">Email</label>
    <form:input path="guestEmail" id="guestEmail" />

    <button type="submit" name="_eventId_continue">
        Tiếp tục
    </button>

    <button type="submit" name="_eventId_cancel">
        Hủy
    </button>
</form:form>
~~~

Flow definition có thể xử lý các event tương ứng:

~~~xml
<view-state id="enterGuest" view="booking/enter-guest"
            model="bookingForm">
    <transition on="continue" to="review">
        <evaluate expression="bookingService.validateGuest(bookingForm, messageContext)" />
    </transition>
    <transition on="cancel" to="cancelled" />
</view-state>
~~~

Trong ví dụ:

- Thuộc tính action trỏ tới flowExecutionUrl, vì vậy form gửi request về execution đang hoạt động.
- method="post" dùng cho thao tác gửi dữ liệu.
- Tên nút name="_eventId_continue" yêu cầu Web Flow phát event **continue**.
- Nút hủy gửi event **cancel** trong cùng execution.
- Model form được binding theo cấu hình view-state; service kiểm tra dữ liệu trước khi flow đi tiếp.

Cách đặt tên _eventId_<eventName> là quy ước submit event trong form của Web Flow. Với liên kết thông thường, dùng tham số _eventId=<eventName>. Hai cách này phục vụ cùng mục đích nhưng nằm trong ngữ cảnh HTML khác nhau.

Nếu form có nhiều nút submit, mỗi nút có thể đại diện một event khác nhau. Hãy đặt tên nút rõ ràng và bảo đảm flow definition có transition tương ứng. Với dữ liệu quan trọng, cần kiểm tra validation và quyền ở server trước khi thực hiện nghiệp vụ.

## 5. flowExecutionUrl trong các view technology

Biến flowExecutionUrl được Web Flow cung cấp trong ngữ cảnh view. Cú pháp thể hiện giá trị biến phụ thuộc công nghệ render:

| Công nghệ view | Ví dụ sử dụng | Lưu ý |
|---|---|---|
| JSP với EL | ${flowExecutionUrl} | Phổ biến trong các ứng dụng Spring MVC dùng JSP |
| Thymeleaf | Dùng biểu thức view để lấy giá trị biến flowExecutionUrl | Cần giữ quy tắc URL expression và escaping của Thymeleaf |
| View technology khác | Đọc biến từ model/request context mà Web Flow cung cấp | Xác nhận cách truy cập biến trong integration tương ứng |

Với JSP, có thể dùng biến trực tiếp trong thuộc tính href hoặc action. Nếu cần in URL trong nội dung HTML, hãy dùng cơ chế escape phù hợp của view technology. Đừng ghép chuỗi HTML thủ công từ dữ liệu người dùng.

Ví dụ JSP:

~~~jsp
<c:out value="${flowExecutionUrl}" />
~~~

Đoạn trên chỉ hiển thị URL đã escape trong nội dung trang. Để tạo liên kết có event, đặt URL trong thuộc tính href và thêm event parameter đúng cách như các ví dụ trước.

Cú pháp cụ thể trong Thymeleaf hoặc một view engine khác phụ thuộc cách integration đưa biến vào context. Nguyên tắc vẫn giống nhau: lấy URL execution hiện tại từ context do Web Flow cung cấp, sau đó để view engine xử lý URL và HTML escaping.

## 6. URL encoding và tham số bổ sung

URL của execution thường đã chứa thông tin cần thiết để framework định vị execution. Vì vậy, khi tạo liên kết, chỉ thêm event hoặc tham số thực sự cần thiết. Không tự phân tích chuỗi URL để đoán tên tham số nội bộ hoặc tự thay execution key.

Nếu cần truyền một tham số bổ sung, hãy bảo đảm giá trị được URL-encode. Ví dụ, một tham số **tab** có giá trị do ứng dụng kiểm soát có thể được nối vào query string theo đúng quy tắc URL:

~~~jsp
<a href="${flowExecutionUrl}&amp;_eventId=showDetails&amp;tab=summary">
    Xem tóm tắt
</a>
~~~

Nếu giá trị tham số được tạo động từ dữ liệu người dùng, cần dùng API hoặc cơ chế URL builder của view framework để encode giá trị. Không nối trực tiếp chuỗi tùy ý vào URL, vì ký tự &, =, #, khoảng trắng hoặc ký tự Unicode có thể làm sai cấu trúc query string.

Đối với dữ liệu nghiệp vụ như email, địa chỉ, lựa chọn thanh toán hoặc thông tin hồ sơ, ưu tiên form binding và model của flow. Không nên biến query string thành nơi chứa toàn bộ dữ liệu form. URL thường xuất hiện trong lịch sử trình duyệt, log truy cập và hệ thống giám sát; tránh đưa dữ liệu nhạy cảm vào đó.

Ngoài URL encoding, cần chú ý HTML escaping. Trong thuộc tính HTML, dấu & được biểu diễn bằng &amp;. Đây là quy tắc của markup; nó không thay đổi ý nghĩa tham số mà trình duyệt gửi tới server.

## 7. Liên kết điều hướng và thao tác thay đổi dữ liệu

Liên kết GET thường phù hợp với điều hướng nhẹ như quay lại, mở một vùng thông tin hoặc chuyển tới state hiển thị. Với thao tác tạo, cập nhật, xác nhận hoặc xóa dữ liệu nghiệp vụ, nên dùng form POST và áp dụng bảo vệ CSRF theo cấu hình Spring Security của ứng dụng.

Ví dụ:

| Tương tác | Cách gửi phù hợp | Lý do |
|---|---|---|
| Mở phần chi tiết trên cùng flow | Liên kết event GET nếu event chỉ điều hướng | Không gửi payload form |
| Quay lại bước trước | Liên kết event GET hoặc nút form tùy thiết kế | Điều hướng tới state khác |
| Gửi thông tin người tham gia | Form POST | Có dữ liệu cần binding và validation |
| Xác nhận đặt lịch hoặc tạo đơn | Form POST | Có tác động nghiệp vụ cần bảo vệ và kiểm tra |
| Hủy một bản ghi đã tồn tại | Form POST với xác thực và xác nhận | Tránh thay đổi dữ liệu qua một liên kết GET dễ bị kích hoạt ngoài ý muốn |

Một event GET vẫn có thể làm flow thay đổi state. Tuy nhiên, không nên dùng liên kết GET để thực hiện tác động nghiệp vụ không an toàn. Các hành động như thanh toán, tạo đơn hoặc xóa dữ liệu cần được bảo vệ ở tầng HTTP và nghiệp vụ.

## 8. flowExecutionUrl và vòng đời execution

flowExecutionUrl chỉ có ý nghĩa trong ngữ cảnh execution hiện tại. Trong quá trình xử lý request, Web Flow có thể lưu trạng thái mới và cung cấp URL tiếp tục tương ứng khi render view tiếp theo. Vì vậy, mỗi view nên dùng biến flowExecutionUrl mà nó nhận được tại lần render đó.

Một số tình huống có thể làm URL cũ không còn dùng được:

- Flow execution đã kết thúc.
- Session chứa execution đã hết hạn.
- Người dùng gửi lại một URL cũ sau khi execution đã tiến tới trạng thái khác.
- Người dùng mở nhiều tab và gửi request từ một trang có trạng thái execution đã lỗi thời.
- Execution không còn được repository lưu giữ hoặc không thể khôi phục.

Không nên lưu URL của execution vào database để dùng như định danh nghiệp vụ lâu dài. URL này phục vụ việc tiếp tục một tương tác Web Flow cụ thể. Nếu cần khôi phục một hồ sơ sau khi phiên kết thúc, hãy lưu dữ liệu nghiệp vụ bằng ID bền vững và khởi chạy flow mới sau khi xác thực người dùng.

Khi execution không còn tồn tại, ứng dụng cần xử lý lỗi hết hạn bằng một trang hoặc thông báo dễ hiểu, có hướng dẫn bắt đầu lại hoặc tải lại bản nháp đã lưu. Không hiển thị stack trace hay chi tiết nội bộ của execution cho người dùng.

## 9. Những lỗi thường gặp khi tạo liên kết

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng URL khởi chạy flow cho nút trong một execution đang chạy | Có thể tạo execution mới và mất ngữ cảnh hiện tại | Dùng flowExecutionUrl trong view |
| Tự ghép execution key | URL sai hoặc trỏ tới execution khác | Dùng URL do Web Flow cung cấp |
| Nối ? vào URL đã có query string | Query string bị sai cấu trúc | Dùng &amp; trong HTML khi thêm tham số |
| Event name không khớp transition | Flow không tìm được transition mong muốn | Đối chiếu _eventId với thuộc tính on |
| Dùng GET để xác nhận thanh toán hoặc xóa dữ liệu | Hành động có thể bị kích hoạt ngoài ý muốn | Dùng POST và bảo vệ CSRF |
| Nối dữ liệu người dùng trực tiếp vào URL | Sai encoding hoặc lộ dữ liệu qua URL/log | Dùng URL builder và form binding |
| Tái sử dụng URL từ tab cũ | Request có thể trỏ tới execution key đã lỗi thời | Render và dùng URL mới nhất của view hiện tại |
| Coi execution URL là ID hồ sơ | Khó phục hồi sau khi session hết hạn | Dùng định danh nghiệp vụ bền vững |

## 10. Quy trình tạo và kiểm tra liên kết

Khi xây dựng view-state, hãy thực hiện theo trình tự:

1. Xác định flow execution hiện tại và bảo đảm view được render bởi Web Flow.
2. Dùng flowExecutionUrl được cung cấp trong context làm đích cho form hoặc liên kết event.
3. Với liên kết, thêm _eventId tương ứng; với form, dùng name="_eventId_<eventName>" trên nút submit.
4. Đối chiếu event name với transition trong flow definition.
5. Dùng POST cho thao tác gửi dữ liệu hoặc thay đổi trạng thái nghiệp vụ; kiểm tra CSRF và quyền truy cập.
6. Escape HTML và encode các giá trị URL động.
7. Kiểm thử cả trường hợp URL cũ, session hết hạn, nhiều tab và flow đã kết thúc.
8. Với nhu cầu bắt đầu lại hoặc phục hồi hồ sơ, dùng URL khởi chạy flow cùng ID nghiệp vụ đã được xác thực, không tái sử dụng URL execution đã hết hạn.

flowExecutionUrl kết nối view với flow execution đang hoạt động. Khi dùng URL do Web Flow cung cấp, gửi đúng event parameter và chọn GET/POST theo bản chất thao tác, các liên kết trong view có thể tiếp tục hành trình một cách nhất quán, đồng thời giảm lỗi do ghép URL thủ công hoặc sử dụng execution key đã cũ.
