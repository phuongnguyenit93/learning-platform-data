# Dữ liệu kết quả trong FlowExecutionOutcome

Spring Web Flow điều khiển hành trình web nhiều bước bằng flow, state, event và transition. Trong quá trình đó, dữ liệu có thể được giữ trong request scope, view scope, flow scope hoặc conversation scope để phục vụ các bước đang chạy. Khi một flow kết thúc, ứng dụng thường cần chuyển một phần kết quả ra ngoài flow, chẳng hạn mã đặt chỗ vừa tạo, trạng thái hoàn tất hoặc mã tham chiếu của giao dịch.

**FlowExecutionOutcome** là đối tượng thể hiện kết quả khi một flow execution kết thúc. Nó cung cấp thông tin về flow và các giá trị output được khai báo ở end-state. Trong tích hợp Spring MVC, một **FlowHandler** có thể nhận outcome này để quyết định phản hồi tiếp theo, ví dụ chuyển hướng người dùng đến trang chi tiết dựa trên mã đặt chỗ.

Điểm quan trọng là phân biệt dữ liệu nội bộ của flow với dữ liệu kết quả được xuất ra. Không phải mọi biến trong flow scope đều tự động trở thành output. Flow cần khai báo rõ giá trị nào được xuất tại end-state để lớp tích hợp bên ngoài nhận được một hợp đồng dữ liệu nhỏ, có chủ đích.

## 1. FlowExecutionOutcome xuất hiện khi nào?

Một flow execution có thể tạm dừng tại view-state hoặc action-state để chờ request tiếp theo. Khi flow đi đến end-state, execution kết thúc và Spring Web Flow tạo kết quả hoàn tất. **FlowExecutionOutcome** mang output được khai báo cho end-state đó.

Luồng xử lý tổng quát:

~~~text
Browser / Spring MVC
        |
        v
FlowHandlerAdapter
        |
        v
FlowExecutor
        |
        v
Flow execution
  View-state / Action-state
        |
        | event + transition
        v
     End-state
        |
        | evaluate output expressions
        v
FlowExecutionOutcome
        |
        v
FlowHandler.handleExecutionOutcome(...)
        |
        v
Spring MVC response / redirect
~~~

**FlowExecutionOutcome** chỉ xuất hiện khi execution kết thúc. Khi flow đang ở một view-state và chờ người dùng nhập dữ liệu, ứng dụng vẫn đang làm việc với flow execution đang hoạt động; chưa có outcome cuối cùng để xử lý.

Trong Spring MVC, **FlowHandlerAdapter** làm việc với **FlowExecutor**. Khi execution kết thúc, adapter có thể gọi callback **handleExecutionOutcome(...)** của flow handler tương ứng. Flow handler sử dụng output để chọn view hoặc URL tiếp theo. Nếu ứng dụng không cần xử lý kết quả tùy chỉnh, có thể dùng cách xử lý mặc định của cấu hình handler.

## 2. Khai báo output tại end-state

Output được khai báo trong định nghĩa flow, bên trong end-state. Mỗi phần tử **output** có:

- **name**: tên thuộc tính mà bên nhận sẽ dùng để đọc kết quả.
- **value**: biểu thức được đánh giá trong context của flow khi flow kết thúc.

Ví dụ, flow đặt chỗ giữ đối tượng **booking** trong flow scope. Sau khi xác nhận thành công, flow xuất mã đặt chỗ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking" class="com.example.booking.Booking"/>

    <view-state id="reviewBooking" view="booking/review">
        <transition on="confirm" to="saveBooking"/>
    </view-state>

    <action-state id="saveBooking">
        <evaluate expression="bookingService.save(booking)"/>
        <transition on="success" to="bookingConfirmed"/>
    </action-state>

    <end-state id="bookingConfirmed">
        <output name="bookingId" value="booking.id"/>
    </end-state>
</flow>
~~~

Trong ví dụ, biểu thức **booking.id** được đánh giá khi flow đi đến end-state **bookingConfirmed**. Giá trị được đưa vào output với tên **bookingId**. Flow handler có thể đọc giá trị này mà không cần truy cập trực tiếp toàn bộ flow scope.

Tên output là một phần của hợp đồng giữa flow và thành phần nhận kết quả. Hãy chọn tên có ý nghĩa nghiệp vụ, ổn định và thống nhất giữa flow definition với code Java. Tránh phụ thuộc vào tên biến nội bộ hoặc xuất cả đối tượng lớn khi bên nhận chỉ cần một mã định danh.

Nếu flow có nhiều end-state, mỗi end-state có thể xuất tập output phù hợp với kết quả tương ứng. Ví dụ, trạng thái hoàn tất có thể xuất **bookingId**, còn trạng thái hủy có thể xuất **cancellationReason**. Bên nhận cần xử lý theo end-state và kiểm tra output có thực sự tồn tại trước khi sử dụng.

## 3. Đọc output trong FlowHandler

Trong tích hợp Spring MVC, có thể tùy chỉnh hành vi sau khi flow kết thúc bằng cách triển khai **AbstractFlowHandler** và ghi đè **handleExecutionOutcome(...)**.

Ví dụ:

~~~java
import org.springframework.webflow.execution.FlowExecutionOutcome;
import org.springframework.webflow.mvc.servlet.AbstractFlowHandler;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleExecutionOutcome(
            FlowExecutionOutcome outcome,
            HttpServletRequest request,
            HttpServletResponse response) {

        Object rawBookingId = outcome.getOutput().get("bookingId");
        if (!(rawBookingId instanceof Number)) {
            return "redirect:/booking";
        }

        long bookingId = ((Number) rawBookingId).longValue();
        return "redirect:/booking/confirmation/" + bookingId;
    }
}
~~~

Flow handler đọc thuộc tính **bookingId** từ output map. Nếu dữ liệu thiếu hoặc sai kiểu, handler chuyển đến trang an toàn; nếu hợp lệ, handler tạo redirect đến trang xác nhận.

Ví dụ dùng **javax.servlet** cho các dòng Spring Framework và Servlet API tương ứng. Với ứng dụng đã chuyển sang Jakarta EE, hãy thay bằng package **jakarta.servlet** theo phiên bản Spring đang sử dụng. Tên class và callback của Spring Web Flow cũng cần tương thích với phiên bản thư viện trong dự án.

**handleExecutionOutcome(...)** trả về tên view hoặc redirect view theo cơ chế xử lý view của Spring MVC. Chuỗi **redirect:/...** yêu cầu Spring MVC thực hiện redirect. Giá trị output không tự động được thêm vào URL; chính flow handler quyết định cách dùng nó.

Flow handler cần được Spring đăng ký và được cơ chế mapping của Spring Web Flow chọn cho flow tương ứng. Cách khai báo mapping cụ thể phụ thuộc cấu hình **FlowHandlerMapping** của ứng dụng. Phần quan trọng trong ví dụ là callback nhận **FlowExecutionOutcome**, không phải việc controller thông thường tự đọc flow scope.

## 4. Phân biệt output với các scope của flow

Các scope quản lý dữ liệu theo vòng đời khác nhau. Output có mục đích riêng: xuất một tập giá trị tại thời điểm flow kết thúc.

| Nơi lưu dữ liệu | Vòng đời | Mục đích |
|---|---|---|
| Request scope | Một HTTP request | Dữ liệu tạm thời trong lần xử lý hiện tại. |
| View scope | Trong thời gian flow ở view-state tương ứng | Dữ liệu phục vụ màn hình hiện tại. |
| Flow scope | Trong suốt flow execution | Dữ liệu nghiệp vụ cần dùng qua nhiều state. |
| Conversation scope | Trong conversation, có thể chia sẻ giữa flow cha và subflow | Dữ liệu được các flow liên quan sử dụng chung. |
| Output của end-state | Được tạo khi flow kết thúc | Công bố rõ các giá trị cần chuyển cho flow handler hoặc bên gọi. |

Ví dụ, **booking** có thể tồn tại trong flow scope suốt quá trình nhập và xác nhận. Khi kết thúc, flow chỉ xuất **booking.id**. Flow handler nhận mã này để tạo URL. Các trường như tên khách hàng, địa chỉ hoặc thông tin thanh toán không cần được xuất nếu bên nhận không sử dụng chúng.

Output không phải là một scope mới để giữ dữ liệu trong suốt flow. Nó là kết quả được tạo từ các biểu thức output ở end-state. Do đó, không thể đọc output cuối cùng từ một view-state khi flow chưa kết thúc.

Output cũng không tự động được ghi vào HTTP session, query string hoặc response body. Nếu cần lưu kết quả để người dùng mở lại sau này, hãy ghi dữ liệu nghiệp vụ vào nơi lưu trữ thích hợp và chỉ xuất khóa tham chiếu cần thiết.

## 5. Dùng output để trả kết quả từ subflow

Subflow là một flow được gọi từ flow cha để đóng gói một phần hành trình, chẳng hạn thu thập thông tin địa chỉ hoặc xác thực danh tính. Khi subflow kết thúc, output của end-state là dữ liệu kết quả mà flow cha có thể nhận theo cấu hình liên kết output của subflow-state.

Ví dụ khái niệm:

~~~text
Parent flow
    |
    v
Subflow-state: collectAddress
    |
    v
Child flow: address-flow
    |
    | Người dùng nhập và xác nhận địa chỉ
    v
Child end-state
    |
    | output: addressId
    v
Subflow outcome
    |
    v
Parent flow nhận kết quả
    |
    v
State tiếp theo
~~~

Trong flow con, khai báo output tại end-state:

~~~xml
<end-state id="addressConfirmed">
    <output name="addressId" value="address.id"/>
</end-state>
~~~

Flow cha khai báo subflow-state để gọi flow con và transition theo end-state mà flow con trả về:

~~~xml
<subflow-state id="collectAddress" subflow="address">
    <transition on="addressConfirmed" to="reviewOrder"/>
</subflow-state>
~~~

Output của flow con được chuyển qua cơ chế output mapping của subflow-state để flow cha sử dụng sau khi subflow kết thúc. Với mapping mặc định, thuộc tính được công bố như **addressId** có thể được đọc trong context của flow cha theo cùng tên. Nếu ứng dụng cần đổi tên hoặc chọn lọc dữ liệu, hãy cấu hình output mapper tương ứng theo schema và API của phiên bản Spring Web Flow đang dùng.

Khi thiết kế hợp đồng giữa flow cha và flow con, hãy thống nhất tên, kiểu và ý nghĩa output. Flow con nên xuất dữ liệu tối thiểu cần thiết cho flow cha, thay vì chia sẻ trực tiếp toàn bộ object graph nội bộ.

## 6. Chọn kiểu dữ liệu output phù hợp

Output được chuyển từ flow sang flow handler trong cùng ứng dụng. Dù không tự động gửi cho trình duyệt, dữ liệu vẫn đi qua ranh giới giữa hai thành phần và cần có hợp đồng rõ ràng.

Nên ưu tiên:

- String, số hoặc UUID cho mã định danh và mã tham chiếu.
- Enum hoặc giá trị trạng thái ổn định nếu bên nhận cần phân biệt kết quả.
- DTO nhỏ, có cấu trúc rõ nếu cần truyền nhiều trường liên quan.

Hạn chế xuất:

- Entity ORM có quan hệ lazy loading hoặc vòng tham chiếu.
- Đối tượng lớn chứa nhiều dữ liệu không cần thiết.
- Dữ liệu nhạy cảm như mật khẩu, token, thông tin thanh toán hoặc dữ liệu cá nhân không cần cho bước tiếp theo.
- Đối tượng phụ thuộc vào session, request hoặc tài nguyên đã đóng.

Output thường được xử lý ngay khi flow kết thúc, nhưng không nên giả định mọi object đều an toàn để serialize hoặc giữ lâu. Nếu flow execution được lưu trữ hoặc phục hồi theo cấu hình ứng dụng, hãy kiểm tra yêu cầu serialization của các dữ liệu liên quan.

## 7. Kiểm tra output trước khi sử dụng

Flow handler nên xem output là dữ liệu đầu vào cần kiểm tra. Dù flow do chính ứng dụng định nghĩa, lỗi cấu hình, nhánh kết thúc khác hoặc dữ liệu nghiệp vụ thiếu vẫn có thể khiến một thuộc tính không tồn tại.

Khi đọc output:

1. Dùng đúng tên thuộc tính đã khai báo trong **name** của phần tử **output**.
2. Kiểm tra giá trị có null hay không.
3. Kiểm tra kiểu dữ liệu trước khi ép kiểu.
4. Kiểm tra miền giá trị nếu dùng để tạo URL, truy vấn dữ liệu hoặc chọn quyền truy cập.
5. Không coi một ID nhận được là bằng chứng người dùng có quyền xem bản ghi tương ứng; endpoint đích vẫn phải kiểm tra quyền.
6. Xử lý rõ trường hợp flow kết thúc ở end-state khác và không xuất thuộc tính đang mong đợi.

Ví dụ, nếu **bookingId** được dùng để mở trang chi tiết, controller xử lý trang đó vẫn phải xác minh người dùng hiện tại có quyền xem booking. Không được chỉ dựa vào việc flow handler đã nhận được ID.

Không đưa trực tiếp một chuỗi output chưa kiểm tra vào redirect URL. Với ID số, xác nhận giá trị là **Number** và chuyển thành kiểu số phù hợp. Với mã dạng chuỗi, giới hạn định dạng hoặc encode theo ngữ cảnh URL trước khi sử dụng.

## 8. Các lỗi thường gặp

### Không khai báo output ở end-state

Flow scope có thể chứa **booking**, nhưng nếu end-state không khai báo output, flow handler không có thuộc tính **bookingId** để đọc. Hãy thêm phần tử **output** vào end-state và kiểm tra biểu thức được đánh giá đúng.

### Nhầm tên biến với tên output

Tên biến flow là **booking**, còn tên output có thể là **bookingId**. Bên nhận phải đọc theo thuộc tính **name** của output, không tự suy đoán tên từ biến flow.

### Đọc output khi flow chưa kết thúc

Output được tạo khi flow đi đến end-state. Nếu cần dữ liệu trong lúc flow vẫn chạy, hãy dùng flow scope, view scope hoặc một cơ chế trao đổi dữ liệu phù hợp.

### Một nhánh kết thúc không cung cấp đủ output

Nếu flow có nhiều end-state, không phải nhánh nào cũng có **bookingId**. Flow handler cần kiểm tra trạng thái và giá trị output, hoặc thiết kế một hợp đồng kết quả nhất quán cho các nhánh.

### Xuất toàn bộ entity

Đưa entity lớn vào output làm tăng liên kết giữa flow và bên nhận, có thể gây lỗi lazy loading hoặc vô tình mang theo dữ liệu nhạy cảm. Chỉ xuất ID hoặc DTO tối thiểu.

### Coi output là dữ liệu đã được phân quyền

Output chỉ là dữ liệu kết quả của flow. Nó không thay thế kiểm tra quyền truy cập ở controller, service hoặc endpoint nhận redirect.

### Nhầm output với HTTP response

**FlowExecutionOutcome** không tự gửi JSON, HTML hoặc query parameter cho trình duyệt. Flow handler hoặc thành phần tích hợp tiếp theo phải quyết định cách biểu diễn kết quả thành phản hồi HTTP.

## 9. Kiểm thử FlowExecutionOutcome

Nên có kiểm thử cho cả định nghĩa flow và flow handler. Mục tiêu là xác nhận end-state công bố đúng dữ liệu, outcome chứa đúng giá trị và bên nhận xử lý được những trường hợp thiếu hoặc sai kiểu.

Các trường hợp cần kiểm tra:

1. **Kết thúc thành công.** Flow đi đến end-state thành công và output chứa **bookingId** đúng với booking đã lưu.
2. **Kết thúc ở nhánh khác.** Flow hủy hoặc từ chối không bị giả định có **bookingId** nếu nhánh đó không xuất giá trị này.
3. **Biểu thức output sai.** Cấu hình tham chiếu thuộc tính không tồn tại phải được phát hiện trong kiểm thử hoặc khi khởi chạy flow.
4. **Output thiếu hoặc null.** Flow handler trả phản hồi dự phòng phù hợp và không phát sinh lỗi ép kiểu.
5. **Output sai kiểu.** Handler từ chối dữ liệu không hợp lệ thay vì dùng trực tiếp để tạo URL.
6. **Redirect sau outcome.** Xác nhận Spring MVC tạo redirect đúng và endpoint đích thực hiện kiểm tra quyền.
7. **Subflow output.** Flow cha nhận đúng giá trị được flow con công bố và ánh xạ.
8. **Tách biệt dữ liệu.** Chỉ các giá trị được khai báo mới xuất hiện trong output; các biến nội bộ khác vẫn thuộc scope của flow.

Ở cấp tích hợp, hãy kiểm tra cả URL hoặc view cuối cùng và trạng thái nghiệp vụ trong database. Một redirect đúng không chứng minh giao dịch đã được lưu đúng; tương tự, dữ liệu đã lưu đúng không chứng minh flow handler đọc đúng output.

## 10. Quy trình thiết kế hợp đồng output

Khi cần chuyển dữ liệu từ flow sang Spring MVC hoặc flow cha, thực hiện theo trình tự:

1. Xác định bên nhận cần giá trị nào và dùng nó vào việc gì.
2. Chọn end-state tương ứng với kết quả nghiệp vụ và khai báo **output** với tên có ý nghĩa.
3. Dùng biểu thức lấy dữ liệu từ flow context hoặc kết quả action tại thời điểm kết thúc.
4. Trong flow handler hoặc subflow-state, đọc đúng tên output và kiểm tra null, kiểu dữ liệu.
5. Chỉ xuất dữ liệu tối thiểu, ưu tiên mã tham chiếu thay vì entity đầy đủ.
6. Kiểm tra quyền truy cập ở endpoint đích nếu output được dùng để tạo URL hoặc tải tài nguyên.
7. Viết kiểm thử cho mọi nhánh kết thúc, gồm cả nhánh thành công, hủy và lỗi nghiệp vụ.

Hợp đồng output nên ổn định theo thời gian. Nếu đổi tên thuộc tính hoặc thay kiểu dữ liệu, cần cập nhật đồng thời định nghĩa flow, flow handler, ánh xạ subflow và kiểm thử liên quan.

## 11. Ghi nhớ

**FlowExecutionOutcome** biểu diễn kết quả khi một flow execution kết thúc và mang các giá trị output được khai báo tại end-state. Phần tử **output** xác định tên và biểu thức của từng giá trị; flow handler có thể đọc output trong **handleExecutionOutcome(...)** để chọn view hoặc redirect. Flow cha cũng có thể nhận output từ subflow thông qua cấu hình ánh xạ tương ứng.

Hãy xem output là hợp đồng dữ liệu tường minh giữa flow và bên nhận. Chỉ xuất giá trị cần thiết, kiểm tra kiểu và giá trị trước khi dùng, đồng thời giữ kiểm tra quyền ở endpoint đích. Cách tổ chức này giúp dữ liệu kết quả rời flow có kiểm soát, giảm phụ thuộc vào scope nội bộ và làm cho tích hợp Spring Web Flow với Spring MVC dễ kiểm thử hơn.
