# Sự kiện quay lại, tiếp tục, xác nhận và hủy

Trong chương **Event và transition**, bài này xây dựng các thao tác điều hướng thường gặp của một hành trình nhiều bước: người dùng tiếp tục từ biểu mẫu sang màn hình rà soát, quay lại để sửa dữ liệu, xác nhận để hoàn tất hoặc hủy quy trình. Spring Web Flow biểu diễn các thao tác đó bằng event và transition gắn với từng state. Nhờ vậy, luồng xử lý của module **SPRING_WEB_FLOW** được mô hình hóa rõ ràng qua state, event, transition và subflow, thay vì để controller tự quyết định bước kế tiếp bằng nhiều nhánh điều kiện.

Một nút bấm chỉ gửi đi một event. Chính định nghĩa flow mới quyết định event đó có ý nghĩa gì ở state hiện tại và sẽ chuyển đến đâu. Phân biệt hai phần này giúp bạn thiết kế hành trình dễ đọc, kiểm thử được và giữ dữ liệu xuyên suốt phiên làm việc.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa event do view gửi lên và transition trong flow definition.
- Khai báo các event tiếp tục, quay lại, xác nhận và hủy.
- Gửi event từ biểu mẫu JSP bằng tên tham số theo quy ước của Spring Web Flow.
- Giữ dữ liệu biểu mẫu khi người dùng quay lại state trước.
- Đặt thao tác nghiệp vụ tại thời điểm xác nhận và xử lý hủy theo đúng vòng đời của quy trình.
- Chẩn đoán các lỗi thường gặp khi event không khớp transition hoặc request không tiếp tục đúng flow execution.

## 1. Event và transition phối hợp như thế nào?

**Event** là tín hiệu mô tả điều người dùng vừa yêu cầu, chẳng hạn **continue**, **return**, **confirm** hoặc **cancel**. **Transition** là quy tắc trong flow definition nhận event đó và chỉ định state đích. Một event không tự điều hướng đến state nào; nó cần có transition phù hợp tại state đang hoạt động.

Ví dụ, khi người dùng đang ở state **edit**:

- Event **continue** chuyển đến state **review**.
- Event **cancel** chuyển đến trạng thái kết thúc **cancelled**.

Khi người dùng đang ở state **review**:

- Event **return** chuyển ngược về **edit**.
- Event **confirm** thực hiện thao tác xác nhận và chuyển đến **completed**.
- Event **cancel** kết thúc quy trình đang thực hiện.

Các event này là tên do ứng dụng quy ước. Spring Web Flow không tự gán sẵn ý nghĩa nghiệp vụ cho từ **continue**, **return**, **confirm** hay **cancel**. Ý nghĩa được xác định bởi transition của từng state. Vì thế, cùng một event **cancel** có thể được khai báo ở nhiều state và cùng dẫn đến một state kết thúc.

Quá trình xử lý một thao tác có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Người dùng thao tác trên view] --> B[Form gửi event cùng flow execution]
    B --> C[Spring Web Flow tiếp tục execution hiện tại]
    C --> D{Event có transition tại state hiện tại?}
    D -->|Có| E[Chạy action của transition nếu có]
    E --> F[Chuyển sang state đích]
    F --> G{State đích}
    G -->|View-state| H[Hiển thị view tiếp theo]
    G -->|End-state| I[Kết thúc flow]
    D -->|Không| J[Kiểm tra event name và transition]
~~~

Một request tiếp tục flow cần gắn với đúng flow execution. View của Spring Web Flow cung cấp URL thực thi hiện tại; form phải gửi request về URL đó để hệ thống biết cần tiếp tục phiên luồng nào. Nếu tự thay action bằng một URL khởi chạy mới, ứng dụng có thể tạo flow execution khác thay vì xử lý event trên luồng đang mở.

## 2. Khai báo flow có bốn thao tác

Giả sử ứng dụng có quy trình tạo đơn hàng. Người dùng nhập thông tin người nhận ở màn hình đầu, xem lại thông tin ở màn hình xác nhận, sau đó xác nhận hoặc hủy.

Tạo flow XML, ví dụ **order-flow.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="order" class="com.example.order.OrderForm"/>

    <view-state id="edit" view="order/edit" model="order">
        <transition on="continue" to="review"/>
        <transition on="cancel" to="cancelled"/>
    </view-state>

    <view-state id="review" view="order/review" model="order">
        <transition on="return" to="edit"/>

        <transition on="confirm" to="completed">
            <evaluate expression="orderService.confirm(order)"/>
        </transition>

        <transition on="cancel" to="cancelled"/>
    </view-state>

    <end-state id="completed" view="order/completed"/>
    <end-state id="cancelled" view="order/cancelled"/>
</flow>
~~~

Trong ví dụ:

| Thành phần | Ý nghĩa |
|---|---|
| **order** | Đối tượng dữ liệu của quy trình, được khai báo ở cấp flow để có thể dùng qua nhiều state. |
| **edit** | View-state nhập hoặc chỉnh sửa thông tin. |
| **review** | View-state hiển thị dữ liệu để người dùng rà soát. |
| **continue** | Đi từ **edit** sang **review**. |
| **return** | Đi từ **review** về **edit**. |
| **confirm** | Gọi dịch vụ nghiệp vụ để xác nhận, sau đó đi đến **completed** nếu thao tác thành công. |
| **cancel** | Đi đến **cancelled** và kết thúc flow. |

Phần tử **var** khai báo đối tượng dữ liệu ở phạm vi flow. Do đó, khi transition **return** đưa người dùng từ **review** về **edit**, đối tượng **order** vẫn thuộc cùng flow execution. Người dùng có thể chỉnh sửa dữ liệu đã nhập thay vì phải bắt đầu một quy trình mới.

**end-state** biểu thị điểm kết thúc của flow. Trong ví dụ, **completed** và **cancelled** có view riêng để thông báo kết quả cho người dùng. Việc chuyển đến end-state kết thúc flow execution hiện tại sau khi xử lý kết quả của quy trình.

Lệnh **orderService.confirm(order)** là điểm gọi nghiệp vụ minh họa. Bean **orderService** phải được Spring cấu hình và có phương thức tương ứng. Nếu việc xác nhận có thể thất bại do dữ liệu thay đổi, hết hàng hoặc vi phạm quy tắc nghiệp vụ, dịch vụ cần báo lỗi theo cách ứng dụng xử lý được; chỉ chuyển sang màn hình thành công sau khi thao tác nghiệp vụ thực sự hoàn tất.

## 3. Gửi event từ biểu mẫu

Trong view của Spring Web Flow, tên nút submit có thể dùng quy ước **_eventId_<tên-event>**. Phần tên sau **_eventId_** chính là event ID mà transition sẽ nhận.

### Màn hình nhập dữ liệu

Ví dụ JSP **order/edit.jsp**:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<h1>Thông tin đơn hàng</h1>

<form:form modelAttribute="order"
           action="${flowExecutionUrl}"
           method="post">

    <label for="recipientName">Tên người nhận</label>
    <form:input id="recipientName" path="recipientName"/>

    <label for="deliveryAddress">Địa chỉ giao hàng</label>
    <form:input id="deliveryAddress" path="deliveryAddress"/>

    <button type="submit"
            name="_eventId_continue"
            value="continue">Tiếp tục</button>

    <button type="submit"
            name="_eventId_cancel"
            value="cancel">Hủy</button>
</form:form>
~~~

Nút **Tiếp tục** gửi event **continue**. Spring Web Flow tìm transition có **on="continue"** trong state **edit** và chuyển đến **review**. Nút **Hủy** gửi event **cancel**, làm flow đi đến end-state **cancelled**.

Thuộc tính **action="${flowExecutionUrl}"** hướng biểu mẫu về URL của flow execution hiện tại. Khi hiển thị view, Spring Web Flow cung cấp URL này cùng thông tin nhận diện execution. Giữ URL thực thi là điều cần thiết để request POST tiếp tục đúng flow đang chạy.

Thuộc tính **modelAttribute="order"** liên kết biểu mẫu với đối tượng **order** đã khai báo trong flow. Các trường **recipientName** và **deliveryAddress** cần có thuộc tính tương ứng cùng getter/setter trong lớp **OrderForm**. Nếu ứng dụng bật bảo vệ CSRF của Spring Security, biểu mẫu cũng phải gửi CSRF token theo cấu hình bảo mật của ứng dụng.

### Màn hình rà soát và xác nhận

Ví dụ JSP **order/review.jsp**:

~~~jsp
<h1>Kiểm tra thông tin đơn hàng</h1>

<p>Người nhận: ${order.recipientName}</p>
<p>Địa chỉ: ${order.deliveryAddress}</p>

<form action="${flowExecutionUrl}" method="post">
    <button type="submit"
            name="_eventId_return"
            value="return">Quay lại chỉnh sửa</button>

    <button type="submit"
            name="_eventId_confirm"
            value="confirm">Xác nhận đơn hàng</button>

    <button type="submit"
            name="_eventId_cancel"
            value="cancel">Hủy quy trình</button>
</form>
~~~

Mỗi nút gửi một event riêng. Người dùng chọn **Quay lại chỉnh sửa** thì flow quay về **edit**; chọn **Xác nhận đơn hàng** thì transition **confirm** chạy lời gọi dịch vụ; chọn **Hủy quy trình** thì flow kết thúc tại **cancelled**.

Tên event phải khớp với thuộc tính **on** trong flow XML. Ví dụ, nút có tên **_eventId_return** sẽ gửi event **return**, không phải **back**. Nếu đổi tên event trong view, phải cập nhật transition tương ứng.

## 4. Giữ dữ liệu khi quay lại

Quay lại là một transition bình thường trong flow. Nó không có nghĩa là trình duyệt tự tải lại trang trước đó. Khi người dùng gửi event **return**, Spring Web Flow chuyển flow execution từ state **review** về state **edit**.

Trong ví dụ, đối tượng **order** được khai báo ở cấp flow nên dữ liệu được giữ trong suốt flow execution. Người dùng có thể sửa một trường rồi tiếp tục sang màn hình rà soát lần nữa.

Cần phân biệt phạm vi dữ liệu:

| Phạm vi | Vòng đời và cách dùng |
|---|---|
| **viewScope** | Dữ liệu gắn với một view-state; phù hợp cho trạng thái tạm thời của riêng màn hình đó. |
| **flowScope** | Dữ liệu tồn tại trong flow execution; phù hợp với biểu mẫu cần được giữ qua nhiều state. |
| **conversationScope** | Dữ liệu dùng chung trong phạm vi conversation có chứa flow; phù hợp khi các flow liên quan cần chia sẻ thông tin. |

Đối tượng được khai báo bằng **var** ở cấp flow như ví dụ thuộc phạm vi flow. Nếu đặt dữ liệu chỉ trong **viewScope**, khi rời state và quay lại, bạn không nên mặc định rằng dữ liệu đó vẫn còn nguyên. Hãy chọn scope theo đúng thời gian sống cần thiết của dữ liệu.

Không nên dùng event quay lại để tạo một flow execution mới. Cách đó có thể làm mất dữ liệu đang giữ trong execution cũ và tạo ra hai hành trình độc lập. Hãy gửi event về URL của execution hiện tại.

Ngoài ra, nút quay lại của ứng dụng nên được kiểm thử riêng với nút Back của trình duyệt. Lịch sử trình duyệt có thể hiển thị lại nội dung cũ hoặc gửi lại request trước đó; nó không thay thế transition **return** trong state machine.

## 5. Xác nhận và hủy phải có ý nghĩa nghiệp vụ rõ ràng

Event **confirm** thường là điểm chuyển từ dữ liệu tạm sang một hành động nghiệp vụ có hiệu lực, chẳng hạn tạo đơn hàng, đặt chỗ hoặc ghi nhận giao dịch. Vì vậy, không nên xem việc người dùng bấm nút là bằng chứng rằng nghiệp vụ đã được xác nhận. Dịch vụ phía máy chủ vẫn phải kiểm tra dữ liệu, quyền thực hiện và các điều kiện hiện tại trước khi ghi nhận kết quả.

Trong flow mẫu, thao tác xác nhận được gọi ngay trong transition:

~~~xml
<transition on="confirm" to="completed">
    <evaluate expression="orderService.confirm(order)"/>
</transition>
~~~

Lệnh **evaluate** chạy khi transition được kích hoạt. Nếu dịch vụ xác nhận thành công, flow đi đến **completed**. Nếu dịch vụ ném exception hoặc phát hiện điều kiện không hợp lệ, ứng dụng cần có chiến lược xử lý lỗi phù hợp để người dùng nhận được thông báo và có thể tiếp tục hoặc sửa dữ liệu. Không nên hiển thị màn hình thành công trước khi thao tác xác nhận hoàn tất.

Với thao tác có thể bị gửi lặp do người dùng nhấn đúp, tải lại trang hoặc mạng chập chờn, dịch vụ nghiệp vụ nên bảo vệ tính lặp an toàn (idempotency). Ví dụ, một mã đơn hàng hoặc mã yêu cầu duy nhất có thể được dùng để tránh tạo hai đơn hàng từ cùng một ý định xác nhận. Việc bảo vệ này thuộc tầng nghiệp vụ và lưu trữ; chỉ ẩn nút sau lần bấm đầu không đủ để bảo đảm không có thao tác trùng.

Event **cancel** cũng cần được định nghĩa theo ngữ cảnh:

- Nếu người dùng chỉ rời một biểu mẫu chưa lưu, hủy có thể kết thúc flow và bỏ dữ liệu tạm.
- Nếu flow đang giữ tài nguyên tạm như chỗ đặt trước hoặc một bản nháp đã lưu, hủy có thể cần gọi dịch vụ giải phóng hoặc đánh dấu bản nháp đã hủy.
- Nếu đơn hàng đã được xác nhận, việc hủy đơn hàng là một nghiệp vụ khác, có thể cần kiểm tra trạng thái, quyền, phí hoặc quy tắc hoàn tác. Không nên dùng transition kết thúc flow chưa xác nhận để giả lập việc hủy một giao dịch đã có hiệu lực.

Trong flow mẫu, **cancelled** chỉ có nghĩa là quy trình đang mở đã kết thúc theo lựa chọn hủy. Nó không tự động hoàn tác một giao dịch đã ghi vào hệ thống.

## 6. Kiểm thử bốn event

Hãy kiểm tra từng event trong đúng state phát sinh, sau đó kiểm tra dữ liệu và trạng thái đích. Bảng dưới đây là ma trận kiểm thử tối thiểu cho flow **order**:

| State hiện tại | Event gửi lên | Kết quả mong đợi |
|---|---|---|
| **edit** | **continue** | Sang **review**, dữ liệu đã nhập được hiển thị để rà soát. |
| **edit** | **cancel** | Kết thúc flow tại **cancelled**. |
| **review** | **return** | Trở lại **edit**, dữ liệu trong flow vẫn được giữ. |
| **review** | **confirm** | Dịch vụ xác nhận được gọi; nếu thành công, flow đến **completed**. |
| **review** | **cancel** | Kết thúc flow tại **cancelled** theo chính sách hủy của quy trình. |

Khi kiểm thử bằng trình duyệt, hãy quan sát URL thực thi và giữ cookie phiên giữa các request. Khi kiểm thử tự động, nên mô phỏng chuỗi POST trên cùng flow execution thay vì chỉ kiểm tra từng URL độc lập. Các assertion nên xác nhận cả state hoặc view kết quả, dữ liệu được giữ sau khi quay lại và lời gọi nghiệp vụ xác nhận chỉ xảy ra khi event **confirm** được gửi.

Một số tình huống lỗi cần kiểm tra:

| Biểu hiện | Nguyên nhân cần xem xét |
|---|---|
| Bấm nút nhưng không chuyển state | Tên tham số không đúng quy ước, event ID không khớp transition hoặc form không gửi POST. |
| Request mở một flow mới | Form gửi đến URL khởi chạy thay vì **flowExecutionUrl** của execution hiện tại. |
| Quay lại nhưng mất dữ liệu | Dữ liệu được đặt trong scope có vòng đời ngắn hơn flow, hoặc form binding không cập nhật đúng đối tượng. |
| Xác nhận hai lần tạo hai kết quả | Dịch vụ nghiệp vụ chưa xử lý request lặp an toàn. |
| Hủy nhưng tài nguyên tạm vẫn còn | Quy trình hủy chưa gọi thao tác giải phóng hoặc dọn dẹp cần thiết. |
| Người dùng quay lại sau khi flow đã kết thúc | Execution cũ không còn là quy trình đang hoạt động; cần khởi chạy quy trình mới hoặc hiển thị trạng thái kết quả phù hợp. |

## 7. Nguyên tắc thiết kế transition dễ bảo trì

Hãy đặt tên event theo hành động người dùng hiểu được, giữ cách đặt tên nhất quán giữa view và flow XML. Một event nên biểu đạt ý định, còn transition xác định ý định đó hợp lệ ở state nào và dẫn đến đâu.

Đặt thao tác nghiệp vụ có tác động dữ liệu tại transition phù hợp hoặc trong action-state riêng khi quy trình cần nhiều nhánh thành công, thất bại. Các kiểm tra quan trọng như quyền xác nhận, tính hợp lệ của dữ liệu và trạng thái đơn hàng phải được thực hiện phía máy chủ. View chỉ gửi tín hiệu; nó không quyết định kết quả nghiệp vụ.

Giữ dữ liệu cần dùng qua nhiều màn hình trong **flowScope** hoặc scope phù hợp, và chỉ đưa dữ liệu vào **conversationScope** khi thật sự cần chia sẻ giữa các flow liên quan. Tách riêng ý nghĩa của **cancel** trong flow chưa hoàn tất với nghiệp vụ hủy một giao dịch đã xác nhận. Điều này giúp transition thể hiện đúng vòng đời của quy trình.

Khi cần mở rộng hành trình, bạn có thể đưa một nhóm bước dùng chung vào subflow, chẳng hạn quy trình xác thực địa chỉ hoặc chọn phương thức thanh toán. Flow cha vẫn chịu trách nhiệm cho các event điều hướng cấp cao như tiếp tục, quay lại, xác nhận và hủy; subflow xử lý phần công việc chuyên biệt rồi trả kết quả cho flow cha.
