# Lộ trình từ flow tối giản đến ứng dụng nhiều bước có kiểm thử

Trong chương **Bản đồ Web Flow**, bài này xây dựng một hành trình đặt lịch bằng **Spring Web Flow** từ flow đầu tiên chỉ có một chuyển tiếp đến ứng dụng nhiều bước có binding, validation, subflow và kiểm thử. Đây là phạm vi của module `SPRING_WEB_FLOW`: mô hình hóa hành trình web qua state, event, transition và subflow; tích hợp với Spring MVC; quản lý dữ liệu theo scope; và phục hồi luồng khi có lỗi.

Một flow mô tả người dùng đang ở bước nào và sự kiện nào được phép đưa họ sang bước tiếp theo. Spring MVC tiếp nhận HTTP request và hiển thị view; Spring Web Flow quản lý lần thực thi flow, khóa thực thi và các chuyển tiếp giữa những request. Nhờ vậy, controller không phải tự giữ toàn bộ logic điều hướng của một quy trình dài.

## 1. Hiểu các thành phần trước khi viết flow

Spring Web Flow phân biệt **định nghĩa flow** và **lần thực thi flow**:

- Định nghĩa flow là cấu hình mô tả state, event, transition, biến và hành động của một quy trình.
- Lần thực thi flow là một phiên chạy cụ thể của định nghĩa đó cho một người dùng. Một định nghĩa có thể có nhiều lần thực thi độc lập.
- Event là tín hiệu gửi lên từ giao diện, chẳng hạn `submit`, `edit`, `confirm` hoặc `cancel`.
- Transition xác định state đích khi flow nhận một event phù hợp.

Các state thường gặp:

| State | Vai trò |
| --- | --- |
| `view-state` | Hiển thị một view và nhận dữ liệu do người dùng nhập. |
| `action-state` | Chạy một hoặc nhiều action ở phía máy chủ rồi chọn transition theo kết quả. |
| `decision-state` | Rẽ nhánh theo một điều kiện, chẳng hạn người dùng có đủ điều kiện hay không. |
| `subflow-state` | Gọi một flow con và chờ flow con kết thúc. |
| `end-state` | Kết thúc flow hoặc trả kết quả về flow cha. |

Một flow thường bắt đầu bằng `view-state`, đi qua một số state xử lý, rồi kết thúc ở `end-state`. Không phải flow nào cũng cần tất cả loại state. Hãy dùng state thể hiện rõ một bước nghiệp vụ; tránh chia nhỏ đến mức mỗi thao tác Java đều trở thành một state.

## 2. Tạo flow tối giản

Giả sử ứng dụng có flow `booking` cho quy trình đặt lịch. Với ứng dụng Spring MVC đã có view resolver, tạo file `booking-flow.xml` trong thư mục flow được đăng ký, ví dụ `WEB-INF/flows/booking/booking-flow.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="start" view="booking/start">
        <transition on="continue" to="done" />
    </view-state>

    <end-state id="done" view="booking/done" />
</flow>
```

`start` là state hiển thị view `booking/start`. Khi view gửi event `continue`, flow chuyển sang `done` và hiển thị view kết thúc. Tên trong `on` phải khớp với event mà giao diện gửi lên; tên trong `to` phải là ID của state đã khai báo trong flow.

Một form JSP tối giản có thể gửi event như sau:

```jsp
<form method="post">
    <input type="hidden" name="_flowExecutionKey" value="${flowExecutionKey}" />
    <button type="submit" name="_eventId_continue" value="true">
        Tiếp tục
    </button>
</form>
```

`_flowExecutionKey` xác định lần thực thi flow đang được tiếp tục. Tên control `_eventId_continue` yêu cầu Spring Web Flow phát event `continue`. Trong ứng dụng thực tế, có thể dùng thẻ JSP của Spring Web Flow để render execution key thay vì tự viết input ẩn. Không tự tạo hoặc sửa execution key trong JavaScript.

Ở bước này, hãy xác nhận ba điều: URL khởi chạy được ánh xạ đến flow `booking`, view `booking/start` được view resolver tìm thấy, và khi nhấn **Tiếp tục** thì flow đi đến `done`.

## 3. Đăng ký flow với Spring MVC

Spring Web Flow cần ba thành phần chính: registry để tìm định nghĩa flow, executor để quản lý lần thực thi, và các adapter để kết nối flow với cơ chế dispatch của Spring MVC.

Một cấu hình XML tham khảo trong Spring MVC context:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/webflow-config https://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd">

    <webflow:flow-registry id="flowRegistry" base-path="/WEB-INF/flows">
        <webflow:flow-location-pattern value="/**/*-flow.xml" />
    </webflow:flow-registry>

    <webflow:flow-executor id="flowExecutor" flow-registry="flowRegistry" />

    <bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
        <property name="flowRegistry" ref="flowRegistry" />
        <property name="order" value="-1" />
    </bean>

    <bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
        <property name="flowExecutor" ref="flowExecutor" />
    </bean>
</beans>
```

Registry tìm các file có hậu tố `-flow.xml` dưới `WEB-INF/flows`. ID flow được xác định từ cách đăng ký và vị trí flow; vì vậy cần kiểm tra URL thực tế mà `FlowHandlerMapping` ánh xạ, thay vì mặc định rằng mọi cấu trúc thư mục đều tạo cùng một URL. `FlowHandlerAdapter` chuyển request đã được ánh xạ cho executor. Thứ tự của `FlowHandlerMapping` cần cho phép nó nhận URL flow trước các handler tổng quát có thể bắt cùng URL.

Ứng dụng cũng cần cấu hình view resolver tương thích với Spring MVC và các bean dịch vụ mà flow gọi đến. Dependency `spring-webflow` phải được chọn ở phiên bản tương thích với phiên bản Spring Framework và Java của ứng dụng; nếu dự án quản lý phiên bản bằng BOM hoặc dependency management, hãy dùng cùng quy tắc đó thay vì ghép các phiên bản tùy ý.

Nếu dự án dùng Java configuration, có thể cấu hình tương đương bằng `AbstractFlowConfiguration`, `FlowDefinitionRegistry`, `FlowExecutor`, `FlowHandlerMapping` và `FlowHandlerAdapter`. Giữ một registry và executor nhất quán trong MVC context; nếu cần tùy chỉnh view factory hoặc flow builder services, khai báo rõ chúng khi tạo registry.

## 4. Mở rộng thành flow đặt lịch nhiều bước

Flow tiếp theo thu thập thông tin, cho người dùng rà soát rồi xác nhận. Dữ liệu đặt lịch được giữ trong `flowScope` trong suốt lần thực thi flow.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking" class="com.example.booking.Booking" />

    <on-start>
        <evaluate expression="bookingService.createDraft()" result="flowScope.booking" />
    </on-start>

    <view-state id="enterDetails" view="booking/details" model="booking">
        <binder>
            <binding property="customerName" />
            <binding property="email" />
            <binding property="date" />
        </binder>
        <transition on="submit" to="validateDetails" />
    </view-state>

    <action-state id="validateDetails">
        <evaluate expression="bookingValidator.isValid(flowScope.booking, messageContext)" />
        <transition on="yes" to="review" />
        <transition on="no" to="enterDetails" />
    </action-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="enterDetails" />
        <transition on="confirm" to="complete">
            <evaluate expression="bookingService.confirm(flowScope.booking)"
                      result="flowScope.confirmation" />
        </transition>
    </view-state>

    <end-state id="complete" view="booking/complete" />
</flow>
```

Trong ví dụ:

1. `on-start` tạo bản nháp khi flow bắt đầu.
2. `enterDetails` hiển thị form và chỉ cho phép binding ba thuộc tính được liệt kê trong `binder`.
3. Event `submit` đưa flow đến `validateDetails`. Validator trả về `true` hoặc `false`, tương ứng với event `yes` hoặc `no` của action state.
4. Nếu dữ liệu hợp lệ, người dùng đến `review`. Event `edit` quay lại form; event `confirm` gọi dịch vụ xác nhận và lưu kết quả vào flow scope.
5. `complete` kết thúc flow và hiển thị trang xác nhận.

`Booking`, `bookingService` và `bookingValidator` là các lớp/bean của ứng dụng, cần được đăng ký trong Spring context. Ví dụ giả định `createDraft()` trả về một đối tượng `Booking`, còn `confirm(...)` thực hiện nghiệp vụ xác nhận và trả về kết quả. Nếu thao tác xác nhận có thể thất bại, hãy bổ sung nhánh xử lý lỗi như phần phục hồi bên dưới.

### Form binding và validation

`model="booking"` cho Spring Web Flow biết đối tượng làm model của view state. Binder giới hạn những thuộc tính được phép nhận từ request, giúp tránh bind nhầm các trường nội bộ như `status`, `ownerId` hoặc giá trị tính toán phía máy chủ.

Ví dụ view JSP dùng Spring Form tag:

```jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form method="post" modelAttribute="booking">
    <label for="customerName">Tên người đặt</label>
    <form:input path="customerName" id="customerName" />
    <form:errors path="customerName" />

    <label for="email">Email</label>
    <form:input path="email" id="email" />
    <form:errors path="email" />

    <label for="date">Ngày đặt</label>
    <form:input path="date" id="date" />
    <form:errors path="date" />

    <input type="hidden" name="_flowExecutionKey" value="${flowExecutionKey}" />
    <button type="submit" name="_eventId_submit" value="true">Rà soát</button>
</form:form>
```

Một validator có thể ghi thông báo vào `MessageContext` để view hiển thị lỗi theo field:

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

public class BookingValidator {

    public boolean isValid(Booking booking, MessageContext messages) {
        boolean valid = true;

        if (booking.getCustomerName() == null || booking.getCustomerName().trim().isEmpty()) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("customerName")
                    .defaultText("Vui lòng nhập tên người đặt.")
                    .build());
            valid = false;
        }

        if (booking.getEmail() == null || !booking.getEmail().contains("@")) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("email")
                    .defaultText("Email chưa hợp lệ.")
                    .build());
            valid = false;
        }

        return valid;
    }
}
```

Đây là validation minh họa ở mức nhập liệu. Quy tắc nghiệp vụ như ngày còn chỗ, thời hạn đặt hoặc quyền đặt lịch vẫn phải được kiểm tra trong service khi xác nhận, vì dữ liệu có thể thay đổi giữa lúc người dùng mở form và lúc họ gửi xác nhận. Validation phía giao diện chỉ cải thiện trải nghiệm; nó không thay thế kiểm tra phía máy chủ.

## 5. Chọn scope và quản lý dữ liệu phiên

Spring Web Flow cung cấp các scope có vòng đời khác nhau. Chọn scope theo thời gian dữ liệu cần tồn tại:

| Scope | Vòng đời và cách dùng |
| --- | --- |
| `requestScope` | Chỉ tồn tại trong request hiện tại; phù hợp dữ liệu tạm dùng khi xử lý request. |
| `flashScope` | Dùng để chuyển dữ liệu ngắn hạn qua ranh giới request, thường để hiển thị thông báo sau redirect. |
| `viewScope` | Gắn với view state hiện tại; phù hợp dữ liệu chỉ phục vụ một màn hình. |
| `flowScope` | Tồn tại trong một lần thực thi flow; phù hợp model của quy trình đặt lịch. |
| `conversationScope` | Chia sẻ trong conversation của flow gốc và các subflow; phù hợp dữ liệu cần dùng chung giữa các flow liên quan. |

Biến khai báo bằng `<var>` được tạo cho flow và thường được truy cập qua `flowScope`. Có thể đặt giá trị trực tiếp bằng EL, ví dụ `flowScope.booking`. Không đưa mọi dữ liệu vào `conversationScope` chỉ vì muốn giữ chúng lâu hơn một view. Scope rộng hơn làm tăng thời gian giữ dữ liệu và khiến việc hiểu nơi cập nhật dữ liệu khó hơn.

`conversationScope` không phải kho lưu trữ lâu dài và không đồng nghĩa với một bảng dữ liệu nghiệp vụ. Dữ liệu flow được quản lý qua cơ chế lưu trữ execution của Spring Web Flow, thường gắn với session theo cấu hình ứng dụng. Khi cần dữ liệu tồn tại sau khi flow kết thúc, sau khi session hết hạn hoặc để nhiều thiết bị cùng truy cập, hãy lưu vào database qua service và chỉ giữ ID cần thiết trong flow. Tránh giữ thông tin nhạy cảm hoặc object lớn trong scope lâu hơn nhu cầu.

## 6. Tách quy trình con bằng subflow

Khi bước thanh toán hoặc xác minh có vòng đời riêng, có thể tách thành flow con. Flow cha gọi flow con bằng `subflow-state`:

```xml
<subflow-state id="payment" subflow="payment">
    <input name="bookingId" value="flowScope.booking.id" />
    <transition on="paid" to="complete" />
    <transition on="cancelled" to="review" />
</subflow-state>
```

Flow `payment` nhận input `bookingId`, tự quản lý các state của quá trình thanh toán, rồi kết thúc bằng một trong các end state `paid` hoặc `cancelled`. Flow cha xử lý kết quả theo ID end state tương ứng. Nếu flow con cần trả thêm dữ liệu, khai báo output trên end state và ánh xạ output đó theo cấu hình subflow của dự án.

Subflow hữu ích khi một quy trình có thể tái sử dụng, có nhiều bước nội bộ hoặc cần kiểm thử độc lập. Không cần tạo subflow cho một lời gọi service đơn giản; một action trong flow hiện tại thường dễ hiểu hơn.

## 7. Phục hồi khi flow gặp lỗi

Một ứng dụng nhiều bước cần xác định lỗi nào cho phép người dùng tiếp tục và lỗi nào buộc quy trình dừng lại.

| Tình huống | Cách xử lý phù hợp |
| --- | --- |
| Thiếu hoặc sai dữ liệu form | Ghi lỗi theo field vào message context, quay lại view nhập liệu và giữ dữ liệu hợp lệ đã nhập. |
| Quy tắc nghiệp vụ không còn đúng | Hiển thị state giải thích kết quả, cho phép sửa dữ liệu hoặc bắt đầu lại. Ví dụ: khung giờ vừa hết chỗ. |
| Người dùng hủy quy trình | Chuyển đến end state hủy; thực hiện dọn dẹp dữ liệu tạm nếu cần. |
| Service hoặc hệ thống ngoài tạm thời lỗi | Bắt lỗi ở ranh giới service/action, ghi log có correlation ID và đưa người dùng đến state có thể thử lại. |
| Session hoặc flow execution hết hạn | Hiển thị thông báo dễ hiểu và hướng dẫn khởi chạy flow mới. Không yêu cầu người dùng tự sửa execution key. |

Với lỗi nghiệp vụ dự kiến, nên trả về kết quả rõ ràng để flow chọn nhánh phù hợp. Với lỗi kỹ thuật không dự kiến, cấu hình exception handler ở tầng flow execution hoặc xử lý tại action/service phù hợp với chính sách lỗi của ứng dụng. Không hiển thị stack trace hay thông tin nội bộ cho người dùng.

Các thao tác có tác động bên ngoài như giữ chỗ, thu tiền hoặc gửi yêu cầu đến hệ thống khác cần có cơ chế chống thực hiện lặp. Người dùng có thể gửi lại request, tải lại trang hoặc mở lại một execution cũ. Dùng mã yêu cầu duy nhất, kiểm tra trạng thái nghiệp vụ và thiết kế service theo hướng idempotent để một lần xác nhận không tạo nhiều giao dịch.

## 8. Kiểm thử flow theo từng lớp

Kiểm thử nên bao phủ cả logic nghiệp vụ và cách flow di chuyển giữa các state:

1. **Unit test cho model và service:** kiểm tra quy tắc ngày đặt, tình trạng còn chỗ, xác nhận và hủy.
2. **Unit test cho validator:** kiểm tra dữ liệu hợp lệ, dữ liệu thiếu và thông báo gắn đúng field.
3. **Flow execution test:** khởi chạy flow, gửi event, truyền request parameter và xác nhận state hiện tại sau mỗi bước.
4. **MVC integration test:** kiểm tra URL flow, view resolver, binding, session và execution key qua request HTTP.
5. **Kiểm thử lỗi:** kiểm tra nhánh validation thất bại, service lỗi, hủy flow và execution hết hạn.

Spring Web Flow có test support cho flow XML. Một test execution có thể kế thừa `AbstractXmlFlowExecutionTests`, cung cấp resource của flow và dùng `MockExternalContext` để mô phỏng request/event. Ví dụ dưới đây minh họa cấu trúc; package và helper cụ thể cần khớp phiên bản Spring Web Flow mà dự án đang sử dụng:

```java
public class BookingFlowTests extends AbstractXmlFlowExecutionTests {

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createResource(
                "classpath:flows/booking/booking-flow.xml");
    }

    public void testStartsAtDetails() {
        MockExternalContext context = new MockExternalContext();

        startFlow(context);

        assertCurrentStateEquals("enterDetails");
    }

    public void testValidSubmissionMovesToReview() {
        MockExternalContext context = new MockExternalContext();
        startFlow(context);

        context.setEventId("submit");
        context.setRequestParameter("customerName", "An");
        context.setRequestParameter("email", "an@example.com");
        context.setRequestParameter("date", "2026-12-10");
        resumeFlow(context);

        assertCurrentStateEquals("review");
    }
}
```

Tên parameter phải khớp với tên field được binder cho phép. Test hợp lệ cần cung cấp dữ liệu đủ cho model và mock các service mà flow gọi. Bổ sung test gửi dữ liệu không hợp lệ để xác nhận flow quay về `enterDetails` và message context có lỗi; test `edit` để xác nhận dữ liệu vẫn còn; test `confirm` để xác nhận service chỉ được gọi theo đúng kịch bản. Với MVC integration test, kiểm tra cả request tiếp theo có execution key hợp lệ, không chỉ kiểm tra trực tiếp state trong test harness.

## 9. Lộ trình triển khai và lỗi thường gặp

Nên phát triển theo từng nấc để dễ xác định lỗi nằm ở cấu hình, view hay logic nghiệp vụ:

1. Tạo flow có một `view-state`, một transition và một `end-state`.
2. Đăng ký flow với MVC, xác nhận URL, view resolver và execution key.
3. Thêm model vào flow scope, binding một vài field và hiển thị lại dữ liệu đã nhập.
4. Thêm validation, kiểm tra cả nhánh hợp lệ lẫn không hợp lệ.
5. Thêm bước review và xác nhận; bảo đảm service kiểm tra lại quy tắc nghiệp vụ.
6. Tách subflow khi một quy trình con có ý nghĩa độc lập.
7. Thêm nhánh lỗi, hủy, hết hạn và kiểm thử các đường đi quan trọng.

Một số lỗi dễ gặp:

- Event trong HTML không khớp với giá trị `on` của transition, khiến người dùng nhấn nút nhưng flow không đi theo nhánh mong muốn.
- Flow ID hoặc vị trí file không khớp registry, khiến URL không tìm được định nghĩa.
- View name không khớp cấu hình view resolver, dẫn đến lỗi render dù state đã được kích hoạt.
- Binder thiếu thuộc tính cần thiết hoặc cho phép bind các field không nên nhận từ client.
- Dữ liệu đặt trong `viewScope` nhưng lại cần dùng ở state kế tiếp, hoặc đặt trong scope quá rộng mà không có lý do.
- Chỉ kiểm tra dữ liệu lúc mở form mà không kiểm tra lại trước thao tác xác nhận.
- Service thực hiện side effect trước khi flow biết thao tác thất bại, gây trạng thái nghiệp vụ không nhất quán khi người dùng thử lại.
- Chỉ kiểm thử state cuối cùng mà bỏ qua các nhánh lỗi, hủy, quay lại và subflow.

## 10. Tiêu chí hoàn thành

Một flow nhiều bước có thể xem là sẵn sàng cho vòng kiểm thử tích hợp khi:

- Registry tìm đúng flow và Spring MVC ánh xạ đúng URL.
- Mỗi event của giao diện có transition tương ứng và state đích tồn tại.
- Model được bind qua danh sách thuộc tính cho phép; validation hiển thị lỗi đúng field.
- Dữ liệu nằm trong scope có vòng đời phù hợp và được lưu bền vững khi nghiệp vụ yêu cầu.
- Subflow nhận input, kết thúc bằng kết quả rõ ràng và flow cha xử lý được từng kết quả.
- Lỗi nghiệp vụ, lỗi kỹ thuật, hủy flow và execution hết hạn đều có hành vi có thể giải thích cho người dùng.
- Unit test, flow execution test và MVC integration test bao phủ các đường đi quan trọng.

Khi các tiêu chí này được đáp ứng, Spring Web Flow đã đảm nhiệm rõ ràng vai trò điều phối hành trình nhiều bước; controller và service có thể tập trung vào HTTP integration và nghiệp vụ tương ứng của chúng.
