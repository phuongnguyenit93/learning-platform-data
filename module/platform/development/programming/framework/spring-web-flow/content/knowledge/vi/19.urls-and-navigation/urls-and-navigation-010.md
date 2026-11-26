# Bookmark và điều kiện cần khởi tạo lại flow

Trong module **SPRING_WEB_FLOW**, URL không chỉ xác định trang cần hiển thị mà còn có thể đại diện cho một flow execution đang tạm dừng tại một state. Điều này giúp người dùng tải lại trang, quay lại một bước hoặc lưu dấu trang để tiếp tục hành trình. Tuy nhiên, một URL flow execution chỉ dùng được khi execution tương ứng vẫn còn trong repository và request còn ngữ cảnh cần thiết, chẳng hạn HTTP session. Vì vậy, cần phân biệt URL khởi tạo một flow mới với URL tiếp tục một flow đang chạy, đồng thời xác định khi nào nên phục hồi execution và khi nào phải khởi tạo lại.

## 1. Hai loại URL trong một hành trình Spring Web Flow

Một ứng dụng thường có hai loại URL với mục đích khác nhau:

| Loại URL | Ví dụ minh họa | Mục đích |
|---|---|---|
| URL khởi tạo flow | `/booking?bookingId=42` | Bắt đầu một flow mới cho booking có định danh 42 |
| URL của flow execution | `/booking?execution=e1s1` | Tiếp tục một execution đã được tạo và tạm dừng ở một điểm cụ thể |

URL khởi tạo thường gắn với một flow ID hoặc một route của ứng dụng. Dữ liệu như `bookingId` là đầu vào để flow tải và kiểm tra đối tượng nghiệp vụ. Khi flow đã bắt đầu và trả về một view, Spring Web Flow tạo URL chứa khóa execution. Tên tham số mặc định thường thấy là `execution`, nhưng cách biểu diễn URL có thể được tùy chỉnh bởi `FlowUrlHandler` và cấu hình của ứng dụng.

Khóa execution là định danh do framework tạo ra. Không tự ghép, tăng, giải mã hoặc đoán giá trị khóa này. Hãy dùng URL được framework render trong form hoặc link của flow để gửi event và tiếp tục execution.

Ví dụ một flow nhận đầu vào là `bookingId` và nạp dữ liệu lúc bắt đầu:

```xml
<flow id="booking">
    <input name="bookingId" type="long" />

    <on-start>
        <evaluate expression="bookingFlowService.loadEditable(bookingId)"
                  result="flowScope.booking" />
    </on-start>

    <view-state id="editBooking" view="booking/edit" model="booking">
        <transition on="submit" to="reviewBooking" bind="true" validate="true" />
    </view-state>

    <view-state id="reviewBooking" view="booking/review" />
</flow>
```

`loadEditable` cần kiểm tra booking có tồn tại, còn ở trạng thái cho phép chỉnh sửa và thuộc phạm vi người dùng hiện tại được truy cập hay không. Đầu vào trên URL chỉ là dữ liệu để tìm đối tượng; nó không phải bằng chứng về quyền truy cập.

## 2. Bookmark một flow execution có ý nghĩa gì?

Khi người dùng lưu bookmark của URL execution, họ đang lưu một địa chỉ tham chiếu tới execution hoặc continuation mà Spring Web Flow quản lý. Nếu repository vẫn giữ execution tương ứng, session và các điều kiện bảo mật vẫn hợp lệ, request sau đó có thể tiếp tục flow ở trạng thái được tham chiếu.

Điều này hữu ích trong một phiên làm việc đang diễn ra: người dùng có thể đánh dấu bước xem lại booking, mở lại trang sau khi tải lại hoặc chia sẻ URL trong cùng một ngữ cảnh được ứng dụng cho phép. Tuy nhiên, bookmark execution không tự chứa toàn bộ trạng thái Java của flow và không bảo đảm là một liên kết lâu dài. URL thường phụ thuộc vào khóa do repository cấp, dữ liệu lưu trong session/repository và thời hạn tồn tại của execution.

Với repository mặc định dựa trên HTTP session, bookmark thường chỉ có thể tiếp tục khi trình duyệt còn gửi đúng session cookie và session vẫn tồn tại. Nếu người dùng mở bookmark trong một trình duyệt khác, cửa sổ riêng tư hoặc sau khi session hết hạn, repository có thể không tìm thấy execution. Nếu ứng dụng dùng repository lưu trữ hoặc cơ chế continuation khác, khả năng phục hồi phụ thuộc vào cấu hình và chính sách lưu trữ của cơ chế đó.

Vì vậy, cần xác định rõ mục đích của bookmark:

- **Tiếp tục phiên đang chạy:** dùng URL execution do Spring Web Flow tạo, với điều kiện execution còn hiệu lực.
- **Quay lại một nghiệp vụ về lâu dài:** dùng URL ổn định của ứng dụng chứa định danh nghiệp vụ, rồi khởi tạo flow mới và tải lại dữ liệu hiện tại.
- **Chia sẻ cho người khác:** dùng route nghiệp vụ có kiểm tra quyền ở mỗi lần truy cập; không chia sẻ khóa execution như một quyền truy cập.

## 3. Cấu hình Spring MVC để định tuyến tới flow

Trong tích hợp Servlet với Spring MVC, `FlowHandlerMapping` ánh xạ URL tới flow trong registry và `FlowHandlerAdapter` chuyển request tới `FlowExecutor`. Ví dụ cấu hình XML phổ biến:

```xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry" />
    <property name="order" value="0" />
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
</bean>
```

Với cách ánh xạ theo flow ID mặc định, route `/booking` được liên kết với flow có ID `booking`. Một URL mới có thể mang tham số đầu vào:

```text
/booking?bookingId=42
```

Sau khi flow bắt đầu, URL tiếp tục execution sẽ do Web Flow tạo và render. Trong ứng dụng thực tế, cần kiểm tra cấu hình `FlowHandlerMapping`, `FlowHandlerAdapter`, `FlowExecutor`, flow registry và `FlowUrlHandler` đang dùng để hiểu chính xác đường dẫn cùng tên tham số. Không viết cứng một khóa execution mẫu như `e1s1` vào link của ứng dụng.

## 4. Bookmark URL execution và bookmark URL nghiệp vụ

Hai loại bookmark giải quyết hai nhu cầu khác nhau. URL execution tham chiếu tới một lần chạy cụ thể; URL nghiệp vụ tham chiếu tới đối tượng hoặc công việc mà người dùng muốn mở lại.

Ví dụ link nghiệp vụ ổn định:

```html
<a href="/booking?bookingId=42">Mở booking</a>
```

Khi người dùng mở link này vào ngày khác, ứng dụng bắt đầu một flow mới. Flow tải dữ liệu mới nhất theo ID, xác minh quyền và xác định trạng thái hiện tại của booking. Nếu booking đã được duyệt hoặc bị hủy, service có thể trả kết quả phù hợp để flow chuyển tới màn hình chỉ đọc hoặc thông báo trạng thái.

Ngược lại, URL execution như `/booking?execution=...` đại diện cho một execution đã tồn tại. Nó có thể chứa tham chiếu tới snapshot/continuation của flow, không phải một truy vấn mới tới booking. Khi cần một bookmark dùng lâu dài, nên tạo route nghiệp vụ ổn định thay vì lưu execution key làm liên kết vĩnh viễn.

Không đưa toàn bộ model, thông tin thanh toán, dữ liệu cá nhân hoặc trạng thái bảo mật vào query string. URL có thể xuất hiện trong lịch sử trình duyệt, log máy chủ, hệ thống phân tích, ảnh chụp màn hình và header referrer. Chỉ truyền định danh hoặc tham số không nhạy cảm cần thiết để bắt đầu flow; tải phần dữ liệu còn lại từ service sau khi xác thực và kiểm tra quyền.

## 5. Khi nào cần khởi tạo lại flow?

Một execution có thể không còn phù hợp để tiếp tục. Các trường hợp thường gặp:

| Tình huống | Vì sao execution cũ không dùng được hoặc không nên tiếp tục | Hướng xử lý |
|---|---|---|
| Người dùng chủ động bắt đầu một tác vụ mới | Đây là một hành trình mới, có đầu vào và vòng đời riêng | Khởi tạo flow mới từ URL launch |
| HTTP session đã hết hạn | Repository dựa trên session không còn execution được tham chiếu | Yêu cầu đăng nhập nếu cần, sau đó mở route khởi tạo mới |
| Execution key không tồn tại hoặc không hợp lệ | Repository không thể khôi phục execution tương ứng | Hiển thị thông báo liên kết hết hạn và cung cấp cách bắt đầu lại |
| Flow đã đi tới `end-state` | Execution đã hoàn tất, không còn là một phiên chỉnh sửa đang hoạt động | Chuyển tới trang kết quả hoặc mở flow mới khi người dùng chọn thao tác khác |
| Dữ liệu nghiệp vụ đã thay đổi đáng kể | Model trong execution có thể cũ hoặc không còn thỏa điều kiện hiện tại | Tải lại dữ liệu, kiểm tra trạng thái và khởi tạo lại nếu cần |
| Người dùng hoặc quyền truy cập thay đổi | Execution cũ có thể được tạo dưới một principal hoặc quyền khác | Xác thực lại và kiểm tra quyền trước khi tiếp tục; từ chối hoặc bắt đầu mới theo chính sách |
| Phiên bản flow hoặc dữ liệu lưu trữ không còn tương thích | Execution cũ có thể không phục hồi được sau triển khai hoặc thay đổi cấu trúc | Xử lý lỗi phục hồi và đưa người dùng về route khởi tạo tương thích |

Không phải mọi lần refresh đều cần khởi tạo flow mới. Nếu URL execution còn hợp lệ và người dùng đang ở đúng session, tiếp tục execution là hành vi mong muốn. Khởi tạo mới chỉ nên diễn ra khi flow thực sự đã mất, đã kết thúc, không còn an toàn hoặc người dùng yêu cầu một hành trình mới.

## 6. Xử lý execution hết hạn hoặc không thể phục hồi

Khi request chứa execution key mà repository không thể khôi phục, Web Flow có thể phát sinh lỗi liên quan tới việc không tìm thấy hoặc không phục hồi được flow execution. Ứng dụng nên xử lý lỗi này tại tầng tích hợp phù hợp, thường là exception handler hoặc cơ chế xử lý lỗi của Spring MVC, để hiển thị trang có hướng dẫn rõ ràng.

Một luồng xử lý nên có các bước:

1. Xác định request đang cố tiếp tục một execution cũ hay đang yêu cầu khởi tạo flow mới.
2. Nếu execution key không hợp lệ/hết hạn, ghi nhận lỗi ở mức phù hợp mà không đưa dữ liệu nhạy cảm vào log.
3. Kiểm tra trạng thái xác thực. Nếu session hết hạn, yêu cầu đăng nhập lại theo cơ chế bảo mật của ứng dụng.
4. Hiển thị thông báo rằng phiên làm việc đã kết thúc hoặc liên kết không còn hiệu lực.
5. Cung cấp link tới route nghiệp vụ ổn định để người dùng tải dữ liệu mới và bắt đầu flow mới.

Ví dụ nội dung trang lỗi:

```html
<h1>Phiên làm việc đã kết thúc</h1>
<p>Liên kết này không còn trỏ tới một phiên chỉnh sửa đang hoạt động.</p>
<a href="/booking?bookingId=42">Mở lại booking</a>
```

Trong ứng dụng thật, ID trong link phải lấy từ ngữ cảnh đã được xác minh hoặc một route an toàn. Nếu không thể xác định đối tượng ban đầu, đưa người dùng về danh sách booking để họ chọn lại. Không tự động chuyển mọi lỗi execution thành một flow mới với dữ liệu mặc định; hành vi đó có thể khiến người dùng thao tác nhầm đối tượng hoặc lặp một nghiệp vụ đã hoàn tất.

## 7. Back, refresh và nhiều tab trình duyệt

Nút Back, Forward và Refresh có thể gửi lại URL của một snapshot/continuation hoặc một event đã được gửi trước đó. Kết quả cụ thể phụ thuộc vào repository, chiến lược lưu continuation, URL handler và cấu hình flow. Cần thiết kế hành vi có thể dự đoán:

- **Refresh sau khi render:** thường gửi lại URL execution hiện tại. Không đặt side effect không idempotent trong logic render chỉ vì người dùng có thể refresh.
- **Back về state trước:** có thể khôi phục một continuation trước đó nếu repository còn giữ snapshot phù hợp. Dữ liệu hiển thị có thể cũ so với trạng thái nghiệp vụ trong database.
- **Forward:** có thể tiếp tục một continuation sau đó nếu nó còn được lưu và hợp lệ.
- **Mở cùng execution ở nhiều tab:** hai tab có thể thao tác trên cùng một conversation hoặc các continuation liên quan. Một tab có thể làm thay đổi trạng thái khiến tab kia trở nên cũ.
- **Gửi form lặp:** người dùng có thể submit lại do double-click, refresh hoặc retry mạng. Các thao tác tạo đơn, thanh toán, giữ chỗ và gửi thông báo cần cơ chế idempotency ở tầng nghiệp vụ.

Không dùng browser history như nguồn dữ liệu chuẩn cho trạng thái booking. Khi người dùng quay lại một bước chỉnh sửa, service vẫn cần kiểm tra phiên bản dữ liệu và quyền hiện tại trước khi lưu. Với dữ liệu có thể thay đổi đồng thời, dùng optimistic locking/version field hoặc cơ chế đồng bộ phù hợp để phát hiện xung đột.

## 8. Điều kiện an toàn trước khi tiếp tục một execution

Ngay cả khi repository khôi phục được execution, ứng dụng vẫn cần xác minh ngữ cảnh nghiệp vụ. Một execution còn tồn tại không có nghĩa mọi thao tác trong đó vẫn được phép.

Trước các bước ghi dữ liệu hoặc thực hiện side effect, cần kiểm tra:

- Người dùng hiện tại đã xác thực và vẫn có quyền truy cập booking.
- Booking còn tồn tại và trạng thái hiện tại cho phép thao tác được yêu cầu.
- Dữ liệu trong flow không cũ tới mức có thể ghi đè thay đổi mới hơn.
- Các điều kiện nghiệp vụ như tồn kho, hạn mức, thời hạn hoặc trạng thái phê duyệt vẫn còn đúng.
- Thao tác chưa được thực hiện trước đó, hoặc service có idempotency key để nhận diện lần gửi lặp.

Ví dụ, người dùng mở lại flow chỉnh sửa booking sau khi một nhân viên khác đã duyệt booking. Service `loadEditable` nên từ chối chế độ chỉnh sửa hoặc trả kết quả chỉ đọc dựa trên trạng thái mới nhất. Flow có thể chuyển tới `bookingAlreadyApproved` để thông báo. Không chỉ dựa vào `flowScope.booking.status` được nạp từ lần truy cập trước.

## 9. Quản lý vòng đời flow và dọn dẹp

Một flow có thể kết thúc qua `end-state`, và conversation/repository có chính sách lưu trữ riêng. Khi nghiệp vụ hoàn tất, nên điều hướng người dùng tới trang kết quả hoặc route nghiệp vụ phù hợp, đồng thời để framework quản lý vòng đời execution theo cấu hình. Không giữ flow sống lâu chỉ để biến URL execution thành bookmark vĩnh viễn.

Các thao tác dọn dẹp như giải phóng khóa chỉnh sửa, đóng tài nguyên tạm hoặc xóa dữ liệu nháp cần được thiết kế theo vòng đời nghiệp vụ. Nếu cleanup được đặt trong `on-end` hoặc action kết thúc, cần bảo đảm nó an toàn khi flow kết thúc bình thường và khi có đường thoát được hỗ trợ. Không dùng cleanup của flow làm cơ chế duy nhất để bảo vệ tài nguyên có TTL; session có thể mất đột ngột mà không chạy đầy đủ logic kết thúc. Với khóa hoặc reservation, nên có thời hạn ở tầng lưu trữ và tiến trình thu hồi độc lập.

Đối với flow có thể bị bỏ dở, hãy xác định thời hạn giữ execution, dữ liệu nháp và tài nguyên đã giữ. Thời hạn nghiệp vụ nên được kiểm tra ở service mỗi khi tiếp tục; sự tồn tại của execution trong repository không gia hạn quyền sử dụng tài nguyên đã hết hạn.

## 10. Kiểm thử bookmark và khởi tạo lại

Kiểm thử cần bao phủ cả trường hợp tiếp tục thành công và trường hợp execution không còn dùng được:

1. **Tiếp tục execution hợp lệ:** khởi tạo flow, lấy URL execution do framework tạo, gửi request tiếp theo trong cùng session và xác nhận flow tiếp tục ở state mong đợi.
2. **Bookmark trong cùng session:** lưu URL execution, mở lại khi repository còn giữ execution và xác nhận hành vi theo cấu hình continuation.
3. **Mất session:** gửi lại URL execution sau khi session hết hạn; xác nhận ứng dụng hiển thị hướng dẫn mở lại thay vì lỗi kỹ thuật thô.
4. **Execution key không tồn tại:** sửa hoặc dùng một key đã bị xóa; xác nhận handler xử lý lỗi rõ ràng và không khởi tạo flow ngoài ý muốn.
5. **Flow đã kết thúc:** truy cập lại URL execution sau `end-state`; xác nhận người dùng được đưa tới kết quả hoặc route bắt đầu mới phù hợp.
6. **Dữ liệu đã đổi:** mở lại flow sau khi booking bị duyệt/hủy ở nơi khác; xác nhận service kiểm tra trạng thái mới và ngăn thao tác cũ.
7. **Khác người dùng:** thử mở link nghiệp vụ dưới một principal khác; xác nhận quyền được kiểm tra lại.
8. **Nhiều tab và gửi lặp:** thực hiện thao tác ở hai tab hoặc gửi hai request gần nhau; xác nhận optimistic locking/idempotency bảo vệ dữ liệu.
9. **URL không chứa dữ liệu nhạy cảm:** kiểm tra query string, log và link được render để bảo đảm chỉ có tham số cần thiết.

Flow test có thể dùng `MockExternalContext` và test support của Spring Web Flow để gửi event, kiểm tra state cùng scope. Các tình huống phụ thuộc HTTP session, cookie, redirect và URL thật cần thêm kiểm thử tích hợp với Spring MVC/Servlet container. Đặc biệt, kiểm thử phải xác nhận cả mã phản hồi và nội dung hướng dẫn người dùng khi execution hết hạn.

## 11. Quy trình quyết định tiếp tục hay khởi tạo lại

Khi nhận một URL liên quan tới flow, hãy xử lý theo thứ tự:

1. **Không có execution key:** xem đây là yêu cầu khởi tạo flow theo route và đầu vào nghiệp vụ đã định nghĩa.
2. **Có execution key:** yêu cầu `FlowExecutor`/repository khôi phục execution tương ứng; không tự phân tích key.
3. **Khôi phục thành công:** xác thực người dùng và kiểm tra quyền, trạng thái nghiệp vụ trước khi cho phép thao tác tiếp theo.
4. **Khôi phục thất bại:** phân loại session hết hạn, key không hợp lệ, execution đã kết thúc hoặc lỗi tương thích; hiển thị thông báo phù hợp.
5. **Người dùng chọn mở lại:** điều hướng tới URL nghiệp vụ ổn định, tải dữ liệu mới và khởi tạo flow mới.
6. **Nghiệp vụ đã hoàn tất:** hiển thị trang kết quả hoặc trạng thái hiện tại thay vì tạo lại thao tác đã thực hiện.

Bookmark hữu ích khi nó trỏ tới một execution còn hiệu lực, nhưng không thay thế một địa chỉ nghiệp vụ bền vững. Hãy để Spring Web Flow quản lý execution key, dùng route nghiệp vụ để mở lại tác vụ trong tương lai, và kiểm tra lại session, quyền cùng dữ liệu mỗi khi người dùng tiếp tục. Cách tổ chức này giúp điều hướng dễ hiểu, tránh xử lý lặp và cho phép flow phục hồi an toàn khi phiên làm việc đã hết hạn.
