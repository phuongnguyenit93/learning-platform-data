# Thuộc tính history của transition và các lựa chọn điều hướng

> **Chương:** Lịch sử trình duyệt  
> **Module:** SPRING_WEB_FLOW

Trong module **SPRING_WEB_FLOW**, bạn học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; tổ chức form binding, validation, scope và phiên; tích hợp Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Khi flow chuyển qua nhiều màn hình, người dùng thường dùng nút Back hoặc Forward của trình duyệt để xem lại bước trước. Spring Web Flow hỗ trợ lưu lịch sử của các view-state và cho phép quy định transition nào giữ, loại bỏ hoặc vô hiệu hóa lịch sử đó.

Thuộc tính **history** giúp chọn chính sách điều hướng cho từng transition. Bài học này giải thích ba lựa chọn **preserve**, **discard** và **invalidate**, cách phân biệt nút Quay lại trong giao diện với nút Back của trình duyệt, và cách kiểm thử hành vi khi người dùng quay lại, tải lại trang hoặc gửi lại một request cũ.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao Spring Web Flow hỗ trợ quay lại các view-state đã đi qua.
- Phân biệt lịch sử trình duyệt với lịch sử snapshot của flow execution.
- Cấu hình history="preserve", history="discard" và history="invalidate" trên transition.
- Chọn chính sách phù hợp cho bước nhập liệu, xác nhận, thanh toán và hoàn tất.
- Phân biệt event back trong flow với thao tác Back của trình duyệt.
- Kiểm tra tác động của Back, Forward, Refresh và submit lặp.
- Thiết kế phục hồi an toàn khi người dùng mở một execution cũ hoặc đã hết hạn.

## 1. Vì sao flow cần quản lý lịch sử?

Một hành trình web nhiều bước thường có dạng:

1. Người dùng nhập thông tin.
2. Người dùng xem lại dữ liệu.
3. Người dùng xác nhận.
4. Ứng dụng xử lý nghiệp vụ và hiển thị kết quả.

Trong quá trình đó, người dùng có thể nhận ra mình cần sửa thông tin ở bước trước. Nếu trình duyệt Back có thể khôi phục view-state và dữ liệu đã nhập, trải nghiệm sẽ thuận tiện hơn. Tuy nhiên, sau khi người dùng xác nhận thanh toán hoặc hoàn tất một giao dịch, việc quay lại màn hình cũ rồi gửi lại dữ liệu có thể gây nhầm lẫn hoặc tạo request không còn hợp lệ.

Spring Web Flow quản lý các lần thực thi flow và có thể lưu snapshot của view-state để hỗ trợ backtracking. Khi người dùng bấm Back, trình duyệt điều hướng đến một mục lịch sử trước đó; request tiếp theo có thể tham chiếu đến trạng thái thực thi flow tương ứng. Chính sách history quyết định snapshot của view-state được giữ hay bị loại bỏ khi transition rời state đó.

Mô hình khái quát:

~~~mermaid
flowchart TD
    A[View-state nhập thông tin] -->|next| B[View-state xem lại]
    B -->|back| A
    B -->|confirm| C[View-state hoàn tất]
    B -.->|Browser Back nếu history được giữ| A
~~~

Các mũi tên nét liền biểu diễn transition được định nghĩa trong flow. Mũi tên nét đứt biểu diễn thao tác quay lại qua lịch sử view-state của trình duyệt. Đây là hai cơ chế khác nhau và cần được kiểm thử riêng.

## 2. Ba lựa chọn của thuộc tính history

Thuộc tính **history** được cấu hình trên transition của một view-state. Spring Web Flow cung cấp ba chính sách:

| Giá trị | Tác dụng khi rời view-state | Khi nào phù hợp |
|---|---|---|
| **preserve** | Giữ lịch sử của view-state để hỗ trợ backtracking. Đây là hành vi mặc định nếu không chỉ định chính sách khác. | Các bước nhập liệu hoặc xem lại mà người dùng có thể cần quay lại. |
| **discard** | Loại bỏ lịch sử của view-state đang rời đi, ngăn quay lại view đó qua lịch sử flow. | Bước tạm thời hoặc bước mà việc quay lại không còn phù hợp. |
| **invalidate** | Vô hiệu hóa lịch sử của view-state đang rời đi cùng tất cả view-state đã hiển thị trước đó. | Điểm không thể quay lại, chẳng hạn sau khi xác nhận một giao dịch. |

Điểm khác nhau quan trọng giữa **discard** và **invalidate** là phạm vi:

- discard loại bỏ lịch sử của view-state đang rời.
- invalidate loại bỏ lịch sử của view-state đó và tất cả view-state trước đó trong hành trình.

Không nên hiểu invalidate là xóa toàn bộ lịch sử duyệt web của trình duyệt hoặc xóa lịch sử của các tab khác. Đây là chính sách lịch sử backtracking do Spring Web Flow quản lý cho flow execution.

## 3. preserve: giữ khả năng quay lại

Nếu không khai báo thuộc tính history, Spring Web Flow mặc định giữ lịch sử view-state để người dùng có thể quay lại bằng nút Back. Có thể ghi rõ preserve để người đọc flow thấy chủ đích:

~~~xml
<view-state id="enterBooking" model="booking">
    <transition on="next" to="reviewBooking"
                history="preserve"/>
</view-state>

<view-state id="reviewBooking" model="booking">
    <transition on="back" to="enterBooking"
                history="preserve"/>
    <transition on="confirm" to="bookingConfirmed"/>
</view-state>
~~~

Ở đây, người dùng có thể đi từ enterBooking sang reviewBooking. Lịch sử của bước nhập được giữ để hỗ trợ backtracking. Nút Back của trình duyệt có thể đưa người dùng về view-state trước đó theo snapshot mà flow đã lưu.

Chính sách preserve thường phù hợp với:

- Form nhập liệu nhiều bước.
- Màn hình xem lại trước khi gửi.
- Bộ lọc tìm kiếm mà người dùng có thể muốn điều chỉnh.
- Các bước chưa tạo ra tác động nghiệp vụ không thể đảo ngược.

Khi quay lại, hãy xác nhận dữ liệu được khôi phục đúng như mong đợi. Spring Web Flow có cơ chế snapshot cho flow execution; việc dữ liệu cụ thể được khôi phục còn phụ thuộc dữ liệu có nằm trong scope được quản lý và cách ứng dụng binding model.

### Nút Back trong giao diện và nút Back của trình duyệt

Nút Back do ứng dụng tạo ra thường gửi một event như **back**. Event đó phải có transition tương ứng trong view-state:

~~~xml
<view-state id="reviewBooking" model="booking">
    <transition on="back" to="enterBooking"/>
</view-state>
~~~

Trong view, nút có thể phát event back:

~~~html
<button type="submit" name="_eventId_back" value="back">
    Quay lại bước nhập
</button>
~~~

Nút này gửi request đến flow execution hiện tại. Nó là một event nghiệp vụ được flow xử lý và có thể chạy action hoặc validation theo cấu hình transition.

Nút Back của trình duyệt đi qua lịch sử điều hướng của browser và có thể khôi phục snapshot trước đó. Nó không nhất thiết gửi event có id back. Vì thế, hai thao tác có thể cho kết quả khác nhau: event back đi theo transition được khai báo; browser Back đi theo chính sách lịch sử của flow execution.

## 4. discard: loại bỏ lịch sử của một view-state

Dùng **history="discard"** khi người dùng không nên quay lại view-state vừa rời đi, nhưng các bước trước đó vẫn có thể còn giá trị để backtracking.

Ví dụ, sau khi người dùng hủy một bước chọn phương thức giao hàng, ứng dụng muốn bỏ màn hình lựa chọn vừa rời đi:

~~~xml
<view-state id="chooseDelivery" model="deliveryForm">
    <transition on="continue" to="reviewDelivery"/>
</view-state>

<view-state id="reviewDelivery" model="deliveryForm">
    <transition on="cancel" to="deliveryCancelled"
                history="discard"/>
</view-state>
~~~

Khi transition cancel được thực hiện, lịch sử của view-state reviewDelivery bị loại bỏ. Các view-state trước đó không bị xóa toàn bộ như chính sách invalidate.

discard phù hợp khi:

- Một view chỉ có ý nghĩa trong một đoạn ngắn của flow.
- Người dùng đã rời một bước và dữ liệu ở bước đó không còn nên được khôi phục qua browser Back.
- Ứng dụng đã chuyển sang một nhánh thay thế và không muốn người dùng quay lại đúng màn hình vừa rời.

Không dùng discard như cách xóa dữ liệu nghiệp vụ. Nó điều chỉnh lịch sử backtracking, không xóa bản ghi trong cơ sở dữ liệu, không xóa đối tượng khỏi flow scope và không thay thế việc dọn dữ liệu tạm. Nếu dữ liệu không còn cần thiết, hãy xử lý scope hoặc model riêng.

## 5. invalidate: đánh dấu điểm không thể quay lại

Dùng **history="invalidate"** khi flow đã vượt qua một điểm mà các view-state trước đó không còn được phép khôi phục qua cơ chế backtracking của flow.

Ví dụ, sau khi xác nhận đặt chỗ, ứng dụng chuyển sang màn hình hoàn tất:

~~~xml
<view-state id="reviewBooking" model="booking">
    <transition on="confirm" to="bookingConfirmed"
                history="invalidate">
        <evaluate expression="bookingService.confirm(flowScope.booking)"/>
    </transition>
</view-state>

<view-state id="bookingConfirmed">
    <on-entry>
        <evaluate expression="confirmationService.load(flowScope.booking.id)"
                  result="viewScope.confirmation"/>
    </on-entry>
</view-state>
~~~

Khi event confirm được xử lý và transition rời reviewBooking, lịch sử của view-state hiện tại cùng các view-state đã hiển thị trước đó được vô hiệu hóa. Người dùng không thể dùng lịch sử backtracking của flow để quay lại các bước đó như trước.

invalidate thường phù hợp với:

- Xác nhận đơn hàng đã được ghi nhận.
- Hoàn tất thanh toán hoặc gửi yêu cầu không thể hủy bằng cách quay lại form.
- Chuyển qua một ranh giới nghiệp vụ mà dữ liệu trước đó không còn là trạng thái có thể tiếp tục.
- Các bước hoàn tất quy trình mà ứng dụng muốn người dùng bắt đầu một flow mới nếu cần thao tác khác.

Hãy dùng invalidate đúng thời điểm. Nếu đặt quá sớm, người dùng có thể mất khả năng sửa dữ liệu trước khi xác nhận. Nếu đặt quá muộn, người dùng có thể quay lại các màn hình cũ sau khi nghiệp vụ đã hoàn tất.

### invalidate không phải cơ chế chống gian lận

Việc vô hiệu hóa lịch sử flow không thay thế kiểm tra quyền, kiểm tra trạng thái đơn hàng hoặc chống submit trùng. Client vẫn có thể gửi request thủ công hoặc một request cũ; service nghiệp vụ phải xác minh trạng thái hiện tại và đảm bảo thao tác ghi có tính an toàn khi được gọi lại.

## 6. Chọn chính sách theo từng transition

Hãy chọn history dựa trên khả năng quay lại mà nghiệp vụ cho phép:

| Tình huống | Chính sách gợi ý | Lý do |
|---|---|---|
| Nhập thông tin cá nhân | preserve | Người dùng có thể quay lại để sửa. |
| Xem lại đơn trước khi xác nhận | preserve | Chưa phát sinh tác động không thể đảo ngược. |
| Rời màn hình trung gian đã bỏ | discard | Không cần khôi phục view vừa rời, nhưng các bước trước có thể vẫn hữu ích. |
| Xác nhận thanh toán thành công | invalidate | Các bước nhập và xác nhận trước đó không còn là trạng thái có thể tiếp tục. |
| Hiển thị kết quả hoàn tất | Tùy transition tiếp theo | Đây là view mới; chính sách được quyết định ở transition khi rời view này. |
| Hủy flow và về trang danh sách | Tùy mục tiêu | Dùng discard nếu chỉ bỏ view hiện tại; dùng invalidate nếu cần chặn backtracking về toàn bộ hành trình trước. |

Ví dụ kết hợp cả ba chính sách:

~~~xml
<view-state id="enterDetails" model="booking">
    <transition on="next" to="review"
                history="preserve"/>
</view-state>

<view-state id="review" model="booking">
    <transition on="back" to="enterDetails"
                history="preserve"/>
    <transition on="cancel" to="cancelled"
                history="discard"/>
    <transition on="confirm" to="confirmed"
                history="invalidate"/>
</view-state>
~~~

Trong flow này:

- next giữ lịch sử bước nhập để người dùng có thể quay lại.
- back là event do giao diện phát ra và chuyển về bước nhập.
- cancel loại bỏ lịch sử của view review khi rời nó.
- confirm vô hiệu hóa lịch sử của review và các view trước đó.

Hãy nhớ rằng history là thuộc tính của transition trên view-state. Không đặt history trên nút HTML hoặc coi đây là thuộc tính chung của action-state. Nếu cần thay đổi lịch sử từ logic nằm trong action-state, hãy xem xét lại cấu trúc flow để đặt chính sách trên transition rời view-state phù hợp; không giả định action-state hỗ trợ cùng thuộc tính này.

## 7. Ảnh hưởng đến dữ liệu, scope và trạng thái nghiệp vụ

Lịch sử điều hướng và dữ liệu trong flow có liên quan nhưng không đồng nhất.

| Thành phần | Vai trò | Khi dùng discard/invalidate |
|---|---|---|
| Browser history | Các mục điều hướng mà trình duyệt ghi nhận | Trình duyệt vẫn có thể giữ mục URL cũ; flow có thể không còn cho phép khôi phục view-state tương ứng. |
| Flow execution history | Snapshot của các view-state trong execution | Snapshot được giữ, loại bỏ hoặc vô hiệu hóa theo history policy. |
| flowScope | Dữ liệu tồn tại trong vòng đời flow | Không tự động bị xóa chỉ vì history bị discard hoặc invalidate. |
| viewScope | Dữ liệu gắn với view-state | Vòng đời phụ thuộc view-state và việc flow chuyển trạng thái; không nên dùng history policy như lệnh xóa dữ liệu. |
| Database/service | Trạng thái nghiệp vụ bền vững | Không bị thay đổi chỉ bởi history policy; service phải kiểm tra và ghi dữ liệu theo transaction. |

Ví dụ, flow có thể đã lưu booking vào flowScope. Nếu transition dùng history="invalidate", điều đó không tự động xóa booking khỏi flowScope hay hủy bản ghi trong database. Nếu muốn xóa dữ liệu tạm sau khi hoàn tất, hãy thực hiện rõ ràng bằng action hoặc lifecycle phù hợp.

Ngược lại, nếu người dùng quay lại một snapshot được giữ bằng preserve, ứng dụng cần biết dữ liệu nào được khôi phục và dữ liệu nào cần tải lại. Thông tin có thể đã thay đổi ở hệ thống bên ngoài; đừng dùng snapshot cũ như bằng chứng rằng giá, tồn kho, quyền hoặc trạng thái nghiệp vụ vẫn còn hiệu lực.

## 8. Browser Back, Forward và Refresh

### Browser Back

Khi người dùng bấm Back, trình duyệt quay về mục điều hướng trước. Nếu mục đó tương ứng với một view-state history còn được giữ, Spring Web Flow có thể khôi phục trạng thái flow tương ứng. Nếu history đã discard hoặc invalidate, request quay lại có thể không khôi phục được state đó; hành vi cụ thể còn phụ thuộc phiên bản framework, execution repository và trạng thái phiên.

Không nên khẳng định rằng trình duyệt sẽ không thể hiển thị trang cũ. Browser cache có thể hiển thị nội dung đã lưu. Điều cần kiểm tra là request tiếp theo có được flow chấp nhận và có thực hiện được thao tác nghiệp vụ hay không.

### Browser Forward

Sau khi Back, người dùng có thể bấm Forward để quay lại mục lịch sử tiếp theo. Nếu flow execution đã thay đổi hoặc history không còn hợp lệ, request Forward có thể không tiếp tục được theo trạng thái cũ. Ứng dụng cần có cách xử lý rõ ràng cho execution hết hạn hoặc không hợp lệ.

### Refresh

Spring Web Flow thường sử dụng redirect phía client khi vào view-state. Khi một request vẫn ở cùng view-state, cơ chế redirect sau xử lý cũng giúp hạn chế cảnh báo gửi lại POST khi người dùng refresh. Hành vi chính xác phụ thuộc loại request, Ajax/embedded mode và cấu hình flow.

Khi kiểm thử Refresh, xác nhận thao tác lưu hoặc thanh toán không bị thực hiện lặp. Redirect không thay thế idempotency của service. Với thao tác ghi quan trọng, hãy dùng transaction, khóa hoặc mã yêu cầu duy nhất phù hợp để chống xử lý trùng.

### Back sau khi submit

Một request gửi form có thể thay đổi dữ liệu hoặc gọi service. Khi người dùng quay lại một snapshot cũ, dữ liệu hiển thị có thể là dữ liệu tại thời điểm snapshot được tạo. Service cần kiểm tra trạng thái hiện hành trước khi cho phép submit lần nữa.

## 9. Xử lý execution cũ và trạng thái không hợp lệ

Một URL flow execution có thể được giữ trong lịch sử trình duyệt, bookmark hoặc một tab khác. Sau khi flow kết thúc, hết hạn hoặc bị loại bỏ khỏi repository, request đến URL đó có thể không còn hợp lệ.

Ứng dụng nên xác định hành vi phục hồi:

- Hiển thị thông báo rằng hành trình đã kết thúc hoặc hết hạn.
- Đưa người dùng về trang bắt đầu phù hợp.
- Hướng dẫn khởi chạy flow mới khi họ cần thao tác lại.
- Tra cứu trạng thái nghiệp vụ hiện tại trước khi cho phép tạo một yêu cầu mới.
- Tránh tiết lộ dữ liệu của execution cũ cho người dùng không còn quyền truy cập.

Không tự ghép hoặc sửa flow execution key để ép flow quay lại state mong muốn. Execution key là thông tin điều phối, không phải bằng chứng phân quyền. Các thao tác nhạy cảm vẫn phải xác thực người dùng và kiểm tra quyền trên tài nguyên.

## 10. Kiểm thử chính sách history

Hãy kiểm thử theo cả đường đi bình thường và các thao tác trình duyệt. Có thể dùng bảng kịch bản:

| Kịch bản | Cách thực hiện | Kết quả cần xác nhận |
|---|---|---|
| Preserve | Đi từ view A sang B rồi bấm Back | Flow khôi phục view A theo snapshot đã giữ. |
| Discard | Rời view B bằng transition history="discard", sau đó bấm Back | View B không còn được khôi phục qua lịch sử flow; các view trước đó có thể vẫn còn tùy history. |
| Invalidate | Rời view B bằng transition history="invalidate", sau đó bấm Back | View B và các view trước đó không còn được khôi phục qua lịch sử flow. |
| Event back | Bấm nút Quay lại trong giao diện | Flow xử lý event back theo transition được khai báo. |
| Forward sau Back | Bấm Back rồi Forward | Xác nhận execution và view hiện tại vẫn hợp lệ theo chính sách. |
| Refresh | Refresh sau khi vào view-state | Không thực hiện lại thao tác ghi ngoài ý muốn. |
| Submit lặp | Double-click nút xác nhận hoặc gửi lại request | Service không tạo giao dịch trùng. |
| Execution hết hạn | Mở URL flow cũ trong tab khác | Ứng dụng hiển thị phục hồi phù hợp, không làm lộ dữ liệu. |

Trong test tích hợp Spring Web Flow, khởi chạy flow, gửi event theo từng transition và xác nhận state. Đối với browser Back/Forward thực tế, cần kiểm thử trình duyệt đầu cuối vì test ở tầng flow execution không mô phỏng đầy đủ lịch sử của browser.

Khi dùng trình duyệt, mở Developer Tools và quan sát Network:

1. Ghi lại URL và request của từng view-state.
2. Xác định redirect được trả về sau mỗi transition.
3. Quan sát request khi bấm Back hoặc Forward.
4. Kiểm tra request có tiếp tục đúng flow execution hay bị từ chối.
5. Xác nhận action/service không bị gọi lại ngoài ý muốn.
6. Kiểm tra dữ liệu hiển thị sau khi khôi phục snapshot.

Không ghi flow execution key, cookie session hoặc thông tin cá nhân đầy đủ vào báo cáo kiểm thử.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Browser Back quay lại form đã xác nhận | Transition chưa dùng invalidate hoặc policy đặt sai transition | Đặt history="invalidate" trên transition rời view-state tại điểm xác nhận. |
| Back không quay lại được bước cần sửa | Dùng discard hoặc invalidate quá sớm | Đổi sang preserve ở các bước còn cho phép sửa. |
| Chỉ mất một view nhưng vẫn quay lại được các bước trước | Dùng discard | Đây là phạm vi dự kiến; dùng invalidate nếu cần loại bỏ toàn bộ history trước đó. |
| Dữ liệu vẫn còn sau invalidate | History policy không xóa flowScope hoặc database | Dọn dữ liệu tạm riêng; quản lý bản ghi qua service. |
| Bấm nút Quay lại nhưng không chuyển state | Event id không khớp transition | Kiểm tra tên event trong form và thuộc tính on. |
| Back hiển thị trang cũ nhưng submit bị lỗi | Browser cache còn nội dung, execution đã bị discard/invalidate hoặc hết hạn | Kiểm tra request mới và hiển thị thông báo phục hồi phù hợp. |
| Refresh làm action ghi chạy nhiều lần | Thiết kế service không chống xử lý lặp | Dùng cơ chế idempotency và kiểm tra trạng thái trước khi ghi. |
| Chính sách không có tác dụng | Đặt history trên phần tử không hỗ trợ hoặc sai transition | Đặt history trên transition của view-state thực sự được thực hiện. |

Khi điều tra, hãy xác định chính xác transition nào đã được chọn, history policy trên transition đó, flow execution còn tồn tại không và service đã thực hiện tác động gì. Không kết luận chỉ dựa trên việc trình duyệt có hiển thị lại một trang cũ hay không.

## 12. Checklist thiết kế điều hướng

- [ ] Đã xác định bước nào người dùng được phép quay lại.
- [ ] Các bước nhập liệu và xem lại cần backtracking dùng preserve hoặc mặc định preserve.
- [ ] Dùng discard khi chỉ muốn loại bỏ lịch sử của view-state vừa rời.
- [ ] Dùng invalidate tại điểm không thể quay lại và cần vô hiệu hóa các view trước đó.
- [ ] History policy được đặt trên đúng transition của view-state.
- [ ] Nút Back trong giao diện có event id và transition riêng.
- [ ] Không nhầm browser Back với event back của flow.
- [ ] Không coi history policy là cơ chế xóa flowScope hoặc dữ liệu database.
- [ ] Service xác minh trạng thái nghiệp vụ và quyền trước thao tác nhạy cảm.
- [ ] Refresh, Forward, submit lặp và execution hết hạn đã được kiểm thử.
- [ ] Người dùng nhận được hướng dẫn rõ ràng khi flow execution cũ không còn hợp lệ.

## Kết luận

Thuộc tính **history** cho phép Spring Web Flow điều khiển backtracking theo từng transition của view-state. **preserve** giữ lịch sử để hỗ trợ quay lại, **discard** loại bỏ lịch sử của view-state đang rời, còn **invalidate** vô hiệu hóa view-state đó cùng các view trước đó. Hãy chọn chính sách theo ranh giới nghiệp vụ, phân biệt event back với nút Back của trình duyệt và kiểm thử cả snapshot, session lẫn tác động của service để hành trình nhiều bước có thể điều hướng và phục hồi đúng cách.

**Tài liệu tham khảo:** [Spring Web Flow Reference Guide – View backtracking](https://docs.spring.io/spring-webflow/docs/2.4.x/reference/htmlsingle/), mục 5.15.
