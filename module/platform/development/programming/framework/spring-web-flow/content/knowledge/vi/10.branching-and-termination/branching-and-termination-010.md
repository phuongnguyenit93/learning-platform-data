# Dọn tài nguyên và thiết kế hành vi sau khi flow đã kết thúc

Trong chương **Rẽ nhánh và kết thúc**, việc đưa flow đến một end-state mới chỉ là một phần của thiết kế. Một hành trình web nhiều bước có thể đã tạo dữ liệu tạm, giữ chỗ, cấp khóa, mở tài liệu tạm hoặc ghi nhận một giao dịch đang chờ. Khi người dùng xác nhận, hủy hoặc flow không còn tiếp tục, ứng dụng cần quyết định tài nguyên nào được giữ lại, tài nguyên nào phải giải phóng và người dùng sẽ nhìn thấy gì sau đó.

Spring Web Flow cung cấp các state kết thúc, scope theo vòng đời flow và hook xử lý khi flow kết thúc. Kết hợp các cơ chế này với dịch vụ nghiệp vụ, giao dịch và chính sách hết hạn giúp ứng dụng **SPRING_WEB_FLOW** kết thúc hành trình có kiểm soát. Bài học này tập trung vào dọn tài nguyên, trả kết quả từ flow, phân biệt kết thúc subflow với kết thúc flow gốc và xử lý các request đến sau khi execution đã kết thúc.

## 1. Kết thúc flow có ý nghĩa gì?

Một flow được mô hình hóa thành các state và transition. Khi flow đi đến một `end-state`, flow session hiện tại kết thúc. End-state có thể đại diện cho nhiều kết quả nghiệp vụ khác nhau, chẳng hạn:

- Người dùng hoàn tất quy trình và được xác nhận.
- Người dùng chủ động hủy.
- Yêu cầu không thể tiếp tục và được kết thúc theo một nhánh xử lý.
- Một subflow hoàn thành và trả kết quả về flow cha.

Các kết quả này đều có thể là điểm kết thúc của một flow session, nhưng ý nghĩa nghiệp vụ của chúng không giống nhau. Ví dụ, hoàn tất đặt chỗ có thể cần giữ bản ghi đặt chỗ và chốt khoản giữ chỗ; hủy đặt chỗ cần giải phóng khoản giữ chỗ; còn một lỗi dịch vụ có thể cần lưu trạng thái để người dùng thử lại.

Ví dụ flow đặt chỗ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="bookingForm">

    <view-state id="bookingForm" view="bookingForm">
        <transition on="submit" to="review" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <view-state id="review" view="review">
        <transition on="confirm" to="confirmed" />
        <transition on="back" to="bookingForm" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <end-state id="confirmed" view="confirmation" />
    <end-state id="cancelled" view="cancelled" />
</flow>
~~~

Flow có hai kết quả kết thúc:

- `confirmed`: người dùng xác nhận hoàn tất.
- `cancelled`: người dùng hủy hành trình.

Việc định nghĩa hai end-state riêng giúp flow thể hiện rõ kết quả. Các hành động nghiệp vụ như chốt đặt chỗ hoặc giải phóng khoản giữ chỗ cần được thực hiện ở bước thích hợp trước khi flow kết thúc hoặc trong hook kết thúc có kiểm tra trạng thái.

## 2. Phân biệt kết thúc flow session, subflow và flow execution

Spring Web Flow hỗ trợ flow lồng nhau. Vì vậy, cần hiểu phạm vi của một lần kết thúc:

- **Flow session** là một lần chạy của một flow definition. Khi flow đó đi đến end-state, flow session ấy kết thúc.
- **Subflow** là flow được gọi từ một flow khác. Khi subflow kết thúc, kết quả được trả về flow cha để flow cha tiếp tục transition. Flow cha vẫn có thể còn hoạt động.
- **Root flow** là flow ở cấp gốc của execution. Khi root flow kết thúc và không còn flow session nào cần tiếp tục, flow execution hoàn tất.

Ví dụ, quy trình đặt hàng có thể gọi subflow xác minh địa chỉ. Subflow xác minh địa chỉ kết thúc với kết quả `addressVerified`; flow đặt hàng nhận event đó rồi chuyển sang bước tính phí vận chuyển. Việc subflow kết thúc không đồng nghĩa toàn bộ quy trình đặt hàng đã kết thúc.

### Sơ đồ vòng đời

~~~mermaid
flowchart TD
    A["Root flow bắt đầu"] --> B["Gọi subflow xác minh địa chỉ"]
    B --> C["Subflow chạy các bước xác minh"]
    C --> D["Subflow đến end-state"]
    D --> E["Trả event/kết quả cho root flow"]
    E --> F["Root flow tiếp tục xử lý đơn hàng"]
    F --> G["Root flow đến end-state"]
    G --> H["Root flow execution hoàn tất"]
~~~

Khi thiết kế dọn dẹp, hãy gắn trách nhiệm với đúng flow session sở hữu tài nguyên. Subflow tạo một tài nguyên tạm riêng thì nên giải phóng tài nguyên đó khi subflow kết thúc hoặc chuyển quyền sở hữu rõ ràng cho flow cha. Nếu flow cha tiếp tục sử dụng tài nguyên, không được giải phóng nó chỉ vì subflow đã kết thúc.

## 3. Vòng đời của scope và dữ liệu sau khi flow kết thúc

Spring Web Flow cung cấp các scope để lưu dữ liệu theo thời gian sống khác nhau. Chọn đúng scope giúp ứng dụng tránh giữ dữ liệu quá lâu hoặc làm mất dữ liệu trước khi cần.

| Scope | Thời gian tồn tại | Ví dụ sử dụng |
|---|---|---|
| Request scope | Trong một request hiện tại | Dữ liệu trung gian chỉ dùng khi xử lý request |
| Flash scope | Tạm thời qua một lần chuyển tiếp/render theo cơ chế flash | Thông báo ngắn sau thao tác |
| View scope | Trong vòng đời của một view-state | Dữ liệu phục vụ một màn hình và các lần postback của màn hình đó |
| Flow scope | Trong vòng đời flow session | Dữ liệu đặt chỗ trong một flow |
| Conversation scope | Trong vòng đời root flow execution, có thể dùng chung giữa flow cha và subflow | Mã tương quan hoặc dữ liệu cần chia sẻ giữa các flow lồng nhau |
| Session scope | Trong vòng đời HTTP session | Tùy chọn người dùng hoặc dữ liệu phiên ứng dụng phù hợp |

Khi flow session kết thúc, dữ liệu trong flow scope của session đó không còn là dữ liệu sống để dùng cho request tiếp theo. Khi root flow execution hoàn tất, conversation scope của execution cũng kết thúc. Dữ liệu trong HTTP session có vòng đời rộng hơn và không tự mất chỉ vì một flow kết thúc.

Không nên đặt mọi dữ liệu vào session scope để “giữ cho chắc”. Nếu lưu trạng thái tạm của một flow trong session scope, người dùng mở nhiều tab có thể vô tình chia sẻ hoặc ghi đè dữ liệu của nhau. Hãy dùng flow scope cho dữ liệu riêng của hành trình; chỉ dùng conversation scope khi flow cha và subflow thực sự cần chia sẻ; dùng session scope cho dữ liệu có ý nghĩa ở cấp phiên đăng nhập.

Sau khi flow kết thúc, nếu một màn hình khác cần dữ liệu nghiệp vụ, hãy lấy dữ liệu đó từ kho lưu trữ bền vững bằng một mã định danh phù hợp. Đừng dựa vào flow scope đã kết thúc để hiển thị trang xác nhận hoặc xử lý thao tác tiếp theo.

## 4. Dùng hook on-end để thực hiện công việc kết thúc

Flow definition có thể khai báo `on-end` để thực hiện hành động khi flow session kết thúc. Hook này phù hợp với công việc dọn dẹp gắn với vòng đời flow, ví dụ giải phóng một khoản giữ chỗ tạm hoặc ghi nhận trạng thái kết thúc.

Ví dụ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      start-state="bookingForm">

    <var name="booking" class="com.example.Booking" />

    <on-end>
        <evaluate
            expression="bookingLifecycle.cleanupAfterFlow(flowScope.booking)" />
    </on-end>

    <!-- Các state và transition của flow -->
</flow>
~~~

Bean `bookingLifecycle` có thể kiểm tra trạng thái của đặt chỗ để quyết định cần làm gì:

~~~java
public void cleanupAfterFlow(Booking booking) {
    if (booking == null) {
        return;
    }

    if (booking.isConfirmed()) {
        // Đặt chỗ đã được chốt; giữ dữ liệu nghiệp vụ cần thiết.
        return;
    }

    if (booking.hasPendingHold()) {
        reservationService.releaseIfPending(booking.getHoldId());
    }
}
~~~

Ví dụ minh họa một phương thức cleanup có thể gọi nhiều lần mà không làm sai trạng thái. Trong ứng dụng thật, trạng thái xác nhận phải được lưu bền vững ở tầng nghiệp vụ và việc giải phóng khoản giữ chỗ phải kiểm tra trạng thái hiện tại trong giao dịch phù hợp.

Không nên viết hook `on-end` như một lệnh xóa vô điều kiện. Hook chạy khi flow session kết thúc, bất kể đó là end-state hoàn tất hay end-state hủy. Nếu xóa dữ liệu hoặc giải phóng tài nguyên mà không xét kết quả nghiệp vụ, ứng dụng có thể vô tình hủy một đặt chỗ vừa được xác nhận.

Có thể đặt hành động nghiệp vụ rõ ràng ở từng nhánh:

~~~xml
<action-state id="commitBooking">
    <evaluate expression="bookingService.confirm(flowScope.booking)" />
    <transition on="success" to="confirmed" />
    <transition on="failure" to="confirmationProblem" />
</action-state>

<action-state id="releaseBooking">
    <evaluate expression="bookingService.cancelAndRelease(flowScope.booking)" />
    <transition on="success" to="cancelled" />
    <transition on="failure" to="cancellationProblem" />
</action-state>

<end-state id="confirmed" view="confirmation" />
<end-state id="cancelled" view="cancelled" />
~~~

Trong thiết kế này, việc xác nhận và hủy được thực hiện như các bước nghiệp vụ có kết quả rõ ràng. Hook `on-end` vẫn có thể đảm nhiệm việc dọn dữ liệu tạm còn sót lại, nhưng không thay thế các thao tác xác nhận hoặc hủy cần được kiểm soát và báo kết quả cho người dùng.

## 5. Không phụ thuộc duy nhất vào on-end để giải phóng tài nguyên

Hook kết thúc hữu ích khi flow session đi qua vòng đời kết thúc bình thường. Tuy nhiên, một hành trình web có thể bị bỏ dở: người dùng đóng trình duyệt, mất kết nối, session hết hạn, ứng dụng bị dừng hoặc tiến trình máy chủ gặp sự cố. Không phải mọi tình huống bỏ dở đều có thể được xử lý ngay bằng một lệnh cleanup trong flow.

Vì vậy, tài nguyên bên ngoài flow cần có cơ chế an toàn ở tầng sở hữu tài nguyên:

- **Khoản giữ chỗ** nên có thời hạn hết hiệu lực. Một tác vụ nền có thể tìm và giải phóng các khoản giữ chỗ quá hạn chưa được xác nhận.
- **Khóa nghiệp vụ** nên có thời gian thuê (lease) hoặc cơ chế timeout để tránh bị giữ vô thời hạn.
- **File tạm** nên được tạo trong vùng lưu trữ có quy tắc dọn file quá hạn.
- **Giao dịch cơ sở dữ liệu** nên ngắn và kết thúc trong một request nghiệp vụ. Không giữ transaction mở trong suốt thời gian người dùng đi qua nhiều màn hình.
- **Tài nguyên kết nối** như connection, stream hoặc session của thư viện bên ngoài nên được mở và đóng trong phạm vi thao tác ngắn bằng cơ chế như try-with-resources.

Một flow kéo dài vài phút không nên giữ một connection cơ sở dữ liệu hoặc transaction mở trong toàn bộ thời gian đó. Thay vào đó, mỗi action gọi service trong một giao dịch ngắn, lưu trạng thái nghiệp vụ cần thiết, rồi trả quyền điều khiển về flow.

### Hai lớp bảo vệ cho tài nguyên tạm

~~~mermaid
flowchart TD
    A["Flow tạo khoản giữ chỗ"] --> B["Lưu holdId và thời điểm hết hạn"]
    B --> C{"Flow kết thúc bình thường?"}
    C -->|"Hủy / chưa xác nhận"| D["on-end hoặc nhánh hủy giải phóng"]
    C -->|"Xác nhận"| E["Chốt đặt chỗ"]
    D --> F["Service kiểm tra trạng thái và giải phóng"]
    E --> G["Lưu trạng thái đã xác nhận"]
    H["Tác vụ nền định kỳ"] --> I["Tìm khoản giữ chỗ quá hạn còn pending"]
    I --> J["Giải phóng khoản giữ chỗ hết hạn"]
~~~

Cleanup phải có tính **idempotent**: nếu cùng một yêu cầu giải phóng được gọi nhiều lần, lần sau không được làm hỏng kết quả đã hoàn tất. Ví dụ, `releaseIfPending(holdId)` chỉ giải phóng khi khoản giữ chỗ còn ở trạng thái pending; nếu đã xác nhận hoặc đã giải phóng thì trả về kết quả phù hợp mà không lặp tác động.

## 6. Trả kết quả có ý nghĩa từ end-state

Một flow kết thúc thường cần cung cấp kết quả cho bên gọi hoặc cho màn hình kết thúc. Có thể phân biệt kết quả bằng ID của end-state, ví dụ `confirmed`, `cancelled` hoặc `rejected`. Với flow được gọi như subflow, kết quả kết thúc được trả về flow cha dưới dạng event để flow cha chọn transition tiếp theo.

Flow cũng có thể khai báo dữ liệu đầu ra tại end-state. Ví dụ:

~~~xml
<end-state id="bookingConfirmed" view="confirmation">
    <output name="bookingId" value="flowScope.booking.id" />
</end-state>
~~~

Ở đây, `bookingConfirmed` thể hiện kết quả của flow, còn `bookingId` là dữ liệu đầu ra được chọn để trả cho bên gọi. Chỉ xuất những giá trị cần thiết; không trả toàn bộ đối tượng flow hoặc dữ liệu nội bộ không cần thiết.

Khi dùng subflow, flow cha có thể dựa vào event kết thúc để phân biệt các kết quả:

~~~xml
<subflow-state id="booking" subflow="booking">
    <input name="customerId" value="flowScope.customerId" />

    <transition on="bookingConfirmed" to="showConfirmation" />
    <transition on="bookingCancelled" to="showCancellation" />
</subflow-state>
~~~

Các end-state tương ứng trong subflow cần có ID phù hợp với event mà flow cha xử lý. Nếu cần dùng dữ liệu đầu ra, hãy khai báo output rõ ràng và ánh xạ dữ liệu theo hợp đồng giữa flow cha và subflow. Điều này giúp flow cha không phải truy cập trực tiếp vào trạng thái nội bộ của subflow đã kết thúc.

Một hợp đồng đầu ra tốt nên có các đặc điểm:

- Tên output thể hiện rõ ý nghĩa nghiệp vụ, chẳng hạn `bookingId`.
- Giá trị output là dữ liệu tối thiểu cần cho bước tiếp theo.
- Mỗi kết quả kết thúc có ý nghĩa rõ ràng và được flow cha xử lý.
- Dữ liệu quan trọng đã được lưu bền vững trước khi flow trả kết quả thành công.

## 7. Thiết kế trang sau khi flow kết thúc

Sau khi người dùng hoàn tất hoặc hủy flow, giao diện cần trả lời rõ điều gì đã xảy ra và người dùng có thể làm gì tiếp theo.

| Kết quả flow | Hành vi giao diện phù hợp |
|---|---|
| Đã xác nhận | Hiển thị mã xác nhận, thông tin tóm tắt và liên kết xem chi tiết |
| Đã hủy | Thông báo hủy thành công và cung cấp đường dẫn quay lại chức năng |
| Không đủ điều kiện | Giải thích lý do ở mức phù hợp và hướng dẫn bước tiếp theo |
| Lỗi tạm thời | Thông báo hệ thống chưa hoàn tất thao tác và hướng dẫn thử lại |
| Hết hạn | Giải thích hành trình cũ không còn hiệu lực và cho phép bắt đầu flow mới |

Không nên để trang kết thúc phụ thuộc vào dữ liệu trong flow scope sau khi flow đã kết thúc. Thay vào đó, trang xác nhận có thể dùng output đã chọn hoặc truy vấn lại dữ liệu nghiệp vụ bằng mã định danh bền vững.

Đối với request POST kết thúc flow, hãy cân nhắc mô hình **Post/Redirect/Get**. Sau khi xử lý thành công, ứng dụng chuyển trình duyệt đến URL kết quả an toàn để refresh không gửi lại thao tác POST. Trang kết quả nên lấy dữ liệu từ mã nghiệp vụ đã lưu, đồng thời kiểm tra người dùng hiện tại có quyền xem kết quả đó.

Nếu ứng dụng dùng end-state với view được render trực tiếp, cần hiểu cách tích hợp Spring MVC đang xử lý request tiếp theo và hành vi refresh của trình duyệt. Có thể chọn một trang kết quả riêng hoặc redirect phù hợp với cấu hình view và handler của ứng dụng.

## 8. Xử lý request đến execution đã kết thúc

Sau khi root flow kết thúc, execution key của hành trình đó không còn là cách hợp lệ để tiếp tục một flow đang hoạt động. Người dùng vẫn có thể bấm Back, refresh hoặc mở bookmark cũ. Các request đó có thể mang execution key đã hết hiệu lực hoặc tham chiếu đến execution mà repository không còn phục vụ.

Ứng dụng cần thiết kế hành vi rõ ràng cho các tình huống này:

1. **Refresh trang kết quả**: hiển thị lại kết quả từ dữ liệu nghiệp vụ đã lưu hoặc URL kết quả, không chạy lại thao tác xác nhận.
2. **Bấm Back về màn hình cũ**: nếu execution đã kết thúc, thông báo hành trình cũ không còn hiệu lực và cung cấp đường dẫn bắt đầu lại.
3. **Gửi lại form cũ**: kiểm tra trạng thái nghiệp vụ và mã yêu cầu để ngăn tạo thao tác trùng.
4. **Mở bookmark chứa execution key cũ**: hướng người dùng đến điểm bắt đầu hợp lệ hoặc trang thông báo hết hạn.
5. **Session hết hạn**: yêu cầu đăng nhập lại nếu cần, sau đó kiểm tra trạng thái nghiệp vụ trước khi cho phép tiếp tục.

Không nên tự tạo execution key mới bằng cách sửa key cũ hoặc tiếp tục một execution đã kết thúc. Khi cần bắt đầu lại, hãy mở URL khởi chạy flow để framework tạo execution mới. Nếu hành trình có thể tiếp tục từ dữ liệu đã lưu, hãy thiết kế một flow mới có bước tải lại trạng thái nghiệp vụ và kiểm tra quyền.

### Phân biệt lỗi hết hạn và lỗi nghiệp vụ

| Tình huống | Ý nghĩa | Cách phản hồi |
|---|---|---|
| Execution key không còn hợp lệ | Flow execution không còn khả dụng | Hướng đến điểm bắt đầu hoặc trang kết quả |
| Đặt chỗ đã được xác nhận | Nghiệp vụ đã hoàn tất | Hiển thị kết quả hiện có, tránh xác nhận lần nữa |
| Đặt chỗ đã bị hủy | Nghiệp vụ đã kết thúc theo nhánh hủy | Hiển thị trạng thái đã hủy |
| Dịch vụ chưa phản hồi | Chưa biết thao tác đã thành công hay chưa | Tra cứu bằng mã yêu cầu trước khi cho phép thử lại |

Điểm cuối rất quan trọng: khi request bị timeout, không thể kết luận chắc chắn thao tác nghiệp vụ thất bại. Máy chủ có thể đã lưu kết quả nhưng response không đến được trình duyệt. Hãy tra cứu trạng thái theo mã yêu cầu hoặc mã giao dịch trước khi cho phép người dùng gửi lại.

## 9. Xử lý lỗi và quan sát thời điểm kết thúc

Các lỗi có thể xảy ra trước khi flow đến end-state. Ví dụ, service xác nhận đặt chỗ phát sinh lỗi, hoặc thao tác giải phóng tài nguyên thất bại. Flow nên có nhánh xử lý lỗi phù hợp để người dùng hiểu trạng thái và hệ thống có thể ghi nhận việc cần xử lý tiếp.

Với lỗi có thể phục hồi, có thể chuyển sang một state hiển thị thông báo và cho phép thử lại. Với lỗi không thể phục hồi, có thể kết thúc flow theo một end-state lỗi sau khi lưu trạng thái nghiệp vụ phù hợp. Không nên nuốt exception rồi hiển thị thành công nếu thao tác chưa được xác nhận.

FlowExecutionListener có thể giúp quan sát vòng đời flow execution và flow session, ví dụ các sự kiện bắt đầu, xử lý event, chuyển state, kết thúc session hoặc phát sinh exception. Listener thích hợp để ghi log, đo thời gian và gắn mã tương quan. Không nên dùng listener như cơ chế duy nhất để giải phóng tài nguyên nghiệp vụ quan trọng, vì cleanup cần được bảo vệ bằng giao dịch, idempotency và chính sách hết hạn ở tầng sở hữu tài nguyên.

Log nên ghi các thông tin có ích như flow ID, state ID, event ID, mã yêu cầu nghiệp vụ và kết quả kết thúc. Tránh ghi dữ liệu biểu mẫu nhạy cảm, token, thông tin xác thực hoặc toàn bộ execution context. Nếu execution key được ghi để chẩn đoán, hãy tuân theo chính sách bảo mật và thời hạn lưu log của ứng dụng.

## 10. Kiểm thử cleanup và hành vi sau kết thúc

Một flow có thể chạy đúng đến end-state nhưng vẫn để lại tài nguyên tạm hoặc cho phép thao tác lặp. Vì vậy, kiểm thử cần bao gồm cả vòng đời tài nguyên và request sau khi kết thúc.

| Kịch bản | Điều cần xác minh |
|---|---|
| Người dùng xác nhận thành công | Dữ liệu nghiệp vụ đã commit; tài nguyên cần giữ lại không bị cleanup |
| Người dùng hủy | Khoản giữ chỗ hoặc tài nguyên tạm được giải phóng |
| Subflow kết thúc | Flow cha nhận đúng event và output; tài nguyên riêng của subflow được xử lý |
| Root flow kết thúc | Flow scope và conversation scope không còn được dùng như trạng thái sống |
| Cleanup được gọi hai lần | Không giải phóng nhầm tài nguyên đã chốt và không tạo lỗi do gọi lặp |
| Người dùng đóng trình duyệt | Tài nguyên tạm được giải phóng theo TTL hoặc tác vụ nền |
| Execution key cũ được gửi lại | Không tiếp tục flow đã kết thúc và không lặp thao tác nghiệp vụ |
| Response bị timeout sau khi commit | Request thử lại tra cứu trạng thái hiện có thay vì tạo giao dịch thứ hai |

Ở mức unit test, kiểm thử service cleanup với các trạng thái pending, confirmed, cancelled và expired. Ở mức flow test, chạy các event xác nhận và hủy, sau đó kiểm tra state kết thúc, output và lời gọi service. Ở mức tích hợp, gửi request tiếp theo bằng execution key cũ và xác minh ứng dụng trả về hành vi đã thiết kế.

Nên kiểm thử cả trường hợp cleanup thất bại. Ví dụ, service giải phóng khoản giữ chỗ không truy cập được. Ứng dụng cần ghi nhận việc cần thử lại hoặc để TTL xử lý sau, thay vì âm thầm bỏ qua và xem như tài nguyên đã được giải phóng.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ có một end-state cho mọi kết quả | Khó phân biệt xác nhận, hủy và lỗi | Đặt end-state theo kết quả nghiệp vụ |
| Dùng `on-end` để xóa mọi dữ liệu | Có thể xóa dữ liệu vừa được xác nhận | Cleanup có điều kiện dựa trên trạng thái nghiệp vụ |
| Chỉ cleanup khi flow kết thúc bình thường | Tài nguyên tồn tại khi người dùng bỏ dở hoặc server gặp sự cố | Dùng TTL, lease và tác vụ nền |
| Giữ transaction mở trong suốt flow | Khóa lâu, tốn connection và dễ gây nghẽn | Dùng giao dịch ngắn theo từng thao tác |
| Đưa dữ liệu tạm của flow vào session scope | Các tab có thể ghi đè trạng thái của nhau | Dùng flow scope hoặc conversation scope đúng phạm vi |
| Flow cha giả định subflow đã kết thúc thì root flow cũng kết thúc | Hành trình cha bị dừng hoặc mất kết quả | Xử lý event/output từ subflow rồi tiếp tục flow cha |
| Trang kết quả đọc flow scope đã hết vòng đời | Mất dữ liệu hoặc phát sinh lỗi khi refresh | Lưu dữ liệu bền vững và dùng mã định danh kết quả |
| Gửi lại POST sau timeout mà không tra cứu trạng thái | Có thể tạo giao dịch trùng | Dùng idempotency key và tra cứu kết quả trước khi thử lại |

## 12. Thực hành: kết thúc flow đặt chỗ an toàn

Hãy mở rộng flow đặt chỗ ở phần đầu bài học để xử lý cả xác nhận, hủy và tài nguyên tạm.

1. Khi khởi chạy flow, tạo một khoản giữ chỗ có thời hạn ở tầng nghiệp vụ và lưu `holdId` trong flow scope.
2. Tạo nhánh `confirmed` để gọi service chốt đặt chỗ và lưu mã `bookingId`.
3. Tạo nhánh `cancelled` để gọi service giải phóng khoản giữ chỗ còn pending.
4. Khai báo `on-end` gọi phương thức cleanup an toàn, có kiểm tra trạng thái và có thể được gọi nhiều lần.
5. Khai báo output `bookingId` tại end-state thành công để flow cha hoặc trang kết quả nhận được mã định danh cần thiết.
6. Tạo trang kết quả đọc dữ liệu đặt chỗ từ kho lưu trữ bằng `bookingId`, không phụ thuộc flow scope đã kết thúc.
7. Thử refresh trang kết quả và xác nhận thao tác xác nhận không chạy lại.
8. Gửi lại request với execution key cũ và xác nhận ứng dụng hướng người dùng đến hành vi hết hạn phù hợp.
9. Giả lập người dùng bỏ dở flow; xác nhận tác vụ nền giải phóng khoản giữ chỗ sau khi hết TTL.
10. Gọi cleanup hai lần và xác nhận trạng thái tài nguyên vẫn đúng.

Sau khi thực hành, hãy tự trả lời:

- Khi subflow đến end-state, điều gì xảy ra với flow cha?
- Dữ liệu trong flow scope và conversation scope tồn tại đến khi nào?
- Vì sao không thể chỉ dựa vào `on-end` để dọn mọi tài nguyên?
- Khi người dùng refresh sau khi flow đã kết thúc, trang kết quả nên lấy dữ liệu từ đâu?
- Làm thế nào để tránh xác nhận đặt chỗ hai lần khi request đầu tiên timeout?

## 13. Ghi nhớ

End-state kết thúc flow session hiện tại; nếu đó là subflow, flow cha có thể nhận event và output rồi tiếp tục. Khi root flow kết thúc, execution hoàn tất và các scope gắn với execution không còn là nơi lưu trạng thái cho hành trình mới. Hãy chọn end-state theo kết quả nghiệp vụ, dùng output để trả dữ liệu tối thiểu và dùng `on-end` cho cleanup có điều kiện.

Tài nguyên quan trọng phải được quản lý ở tầng nghiệp vụ với giao dịch ngắn, thao tác idempotent và thời hạn hết hiệu lực khi cần. Trang sau flow nên đọc dữ liệu đã lưu bằng mã định danh bền vững; request mang execution key cũ cần được xử lý như một hành trình đã kết thúc. Cách thiết kế này giúp **SPRING_WEB_FLOW** kết thúc rõ ràng, bảo vệ tài nguyên và duy trì hành vi nhất quán khi người dùng quay lại, refresh hoặc bỏ dở quy trình.
