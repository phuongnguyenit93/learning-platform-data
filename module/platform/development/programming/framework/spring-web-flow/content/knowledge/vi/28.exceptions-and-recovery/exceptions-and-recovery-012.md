# Thông báo cho người dùng và giữ dữ liệu cần thiết để xử lý tiếp

Trong Spring Web Flow, một lỗi chỉ được xử lý trọn vẹn khi người dùng hiểu điều gì vừa xảy ra, dữ liệu họ đã nhập vẫn còn và hành động tiếp theo có ý nghĩa. Chuyển sang một trang “Có lỗi xảy ra” thường chưa đủ: người dùng có thể mất bản nháp, gửi lại một giao dịch đã thành công hoặc mắc kẹt trong một flow không thể tiếp tục.

Bài học thuộc chương **Ngoại lệ và phục hồi** của module **SPRING_WEB_FLOW**. Trọng tâm là mô hình hóa đường phục hồi bằng state, event và transition; dùng `MessageContext` để phản hồi; chọn scope để giữ dữ liệu; và phối hợp với Spring MVC ở ranh giới giữa xử lý bên trong flow và xử lý khi không còn truy cập được flow execution.

## 1. Ba quyết định phải tách biệt khi có lỗi

Giả sử người dùng nhập đơn hàng, xem lại rồi xác nhận. Dịch vụ xử lý có thể trả về ba kết quả khác nhau:

| Tình huống | Điều người dùng cần biết | Dữ liệu cần giữ | Hành động phù hợp |
| --- | --- | --- | --- |
| Thiếu trường hoặc sai định dạng | Trường nào cần sửa, sửa như thế nào | Nội dung form và thông báo gắn với trường | Sửa ngay trên form |
| Giá hoặc tồn kho đã thay đổi | Điều kiện nghiệp vụ vừa thay đổi | Bản nháp và thông tin cần cập nhật | Sửa hoặc xem lại dữ liệu mới |
| Timeout sau khi gửi yêu cầu | Chưa xác định được kết quả | Bản nháp và mã đối chiếu ổn định | Kiểm tra trạng thái trước khi quyết định gửi lại |
| Phiên đăng nhập hoặc flow execution không còn | Không thể tiếp tục màn hình hiện tại như cũ | Bản nháp đã lưu bền vững, nếu có | Đăng nhập lại và mở bản nháp qua flow mới |
| Lỗi lập trình hoặc lỗi hạ tầng không dự kiến | Tác vụ bị gián đoạn, kèm mã hỗ trợ | Phần trạng thái còn hợp lệ và dữ liệu phục hồi được cho phép | Dừng an toàn hoặc chuyển đến điểm phục hồi đã thiết kế |

Ba quyết định tương ứng là:

1. **Thông báo:** diễn đạt sự cố theo ngôn ngữ người dùng.
2. **Bảo toàn trạng thái:** giữ đúng dữ liệu cần cho bước tiếp theo.
3. **Điều hướng:** xác định state và event nào được phép xảy ra sau lỗi.

Một thông báo đúng không tự làm cho việc thử lại trở nên an toàn. Ngược lại, giữ được dữ liệu trong bộ nhớ cũng không bảo đảm người dùng quay lại được flow sau khi phiên hết hạn.

## 2. Dùng `MessageContext` cho thông báo bên trong flow

Spring Web Flow cung cấp `MessageContext`, thường được truy cập trong biểu thức flow qua biến `messageContext`. Action có thể thêm thông báo bằng `MessageBuilder`:

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

public final class DraftChecks {
    public String check(OrderDraft draft, MessageContext messages) {
        if (draft.getQuantity() <= 0) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("quantity")
                    .code("order.quantity.positive")
                    .defaultText("Số lượng phải lớn hơn 0.")
                    .build());
            return "invalid";
        }
        return "valid";
    }
}
```

Trong ví dụ này:

- `error()` xác định mức độ thông báo.
- `source("quantity")` liên kết thông báo với thuộc tính `quantity` của model.
- `code(...)` cho phép tra nội dung theo locale qua message source đã cấu hình.
- `defaultText(...)` là nội dung dự phòng khi không phân giải được mã.
- Giá trị trả về `invalid` là kết quả điều khiển luồng, độc lập với nội dung thông báo.

Thông báo gắn với một thuộc tính giúp người dùng sửa đúng chỗ. Khi lỗi liên quan toàn bộ tác vụ, chẳng hạn không xác định được kết quả gửi đơn, hãy dùng thông báo tổng quát bằng cách không đặt `source`.

### Binding và validation không cùng một tầng

Lỗi binding có thể xuất hiện trước khi action chạy, ví dụ người dùng nhập `abc` vào trường số lượng kiểu số nguyên. Lỗi validation xuất hiện khi đã có giá trị nhưng giá trị không hợp lệ theo ràng buộc. Lỗi nghiệp vụ có thể xuất hiện muộn hơn, khi dịch vụ phát hiện tồn kho không còn đủ.

Với `view-state` có `model` và tích hợp Spring MVC phù hợp, hãy dùng cơ chế binding/validation của Web Flow cho form. Đừng bắt tất cả thành ngoại lệ hệ thống rồi chuyển sang trang lỗi chung.

Cũng cần phân biệt hai loại dữ liệu:

- Giá trị đã chuyển đổi thành công được giữ trong model, chẳng hạn `flowScope.draft`.
- Giá trị nhập thô bị từ chối, chẳng hạn chuỗi `abc`, được cơ chế binding giữ để hiển thị lại trên lượt lỗi phù hợp; nó không trở thành giá trị hợp lệ trong thuộc tính số nguyên của DTO.

Vì vậy, giữ DTO là cần thiết nhưng chưa đủ để tự tái dựng mọi thông tin về một lần binding thất bại. Hãy tận dụng tích hợp form thay vì chỉ đọc trực tiếp thuộc tính DTO để dựng lại trường nhập.

### Hiển thị thông báo ở view

Một JSP dùng Spring form tags có thể trình bày như sau:

```jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>

<form:form modelAttribute="draft" action="${flowExecutionUrl}" method="post">
    <div role="alert" aria-live="polite">
        <form:errors path="*" element="div" htmlEscape="true" />
    </div>

    <form:label path="quantity">Số lượng</form:label>
    <form:input path="quantity" />
    <form:errors path="quantity" htmlEscape="true" />

    <button type="submit" name="_eventId_confirm">Xác nhận đơn</button>
</form:form>
```

Đây là đoạn view minh họa trong ứng dụng đã cấu hình Spring MVC, Web Flow và thư viện JSP tương ứng. URI taglib cần phù hợp với thế hệ thư viện của dự án. `flowExecutionUrl` trỏ đến execution hiện tại; event `confirm` sẽ được transition tương ứng xử lý.

`form:errors` sử dụng tích hợp lỗi của model với Spring MVC. Việc hiển thị thông báo tổng quát cũng cần nằm trong đúng binding context; với một view không dùng model form, hãy chủ động expose danh sách message đã phân giải để render và escape nội dung. Không giả định mọi view đều tự hiện tất cả message.

Ví dụ trên vừa có vùng tổng hợp vừa có lỗi tại trường nên một lỗi có thể xuất hiện ở cả hai vị trí. Có thể giới hạn vùng tổng hợp vào lỗi toàn cục nếu thiết kế giao diện muốn tránh lặp.

## 3. Chọn scope theo vòng đời phục hồi

Một dữ liệu chỉ hữu ích cho phục hồi nếu nó còn tồn tại ở thời điểm người dùng thực hiện bước tiếp theo.

| Scope hoặc nơi lưu | Vòng đời và phạm vi | Dữ liệu phù hợp |
| --- | --- | --- |
| `requestScope` | Một lần xử lý request trong flow | Giá trị tính tạm thời để dựng response |
| `flashScope` | Dữ liệu tạm, được dọn sau khi view được render | Thông tin chỉ phục vụ lần hiển thị kế tiếp |
| `viewScope` | Trong thời gian còn ở cùng một `view-state` | Trạng thái giao diện và dữ liệu tạm của màn hình |
| `flowScope` | Suốt vòng đời một flow session | DTO bản nháp dùng qua nhiều state |
| `conversationScope` | Phạm vi flow cấp cao nhất và các subflow liên quan | Dữ liệu cần chia sẻ xuyên ranh giới flow/subflow |
| Kho lưu bền vững | Theo chính sách lưu trữ của ứng dụng | Bản nháp cần mở lại sau khi phiên hoặc execution hết hiệu lực |

`MessageContext` là cơ chế thông báo của Web Flow; không cần tự sao chép message vào từng scope. Thời gian giữ và khôi phục message gắn với chu kỳ xử lý, render và tích hợp view của framework. Không dùng message như một kho dữ liệu nghiệp vụ lâu dài.

### Những lựa chọn dễ làm mất dữ liệu

**Đặt bản nháp trong `requestScope`.** Người dùng quay lại sau một request khác và model đã biến mất. Với hành trình nhập, xem lại, sửa và xác nhận, bản nháp thường thuộc `flowScope`.

**Đặt mọi dữ liệu vào `viewScope`.** Khi rời `view-state` sang action-state hoặc một màn hình khác, không thể coi dữ liệu của view cũ là còn tồn tại. Dữ liệu cần đi qua nhiều state phải được đưa vào scope thích hợp trước khi rời view.

**Khởi tạo lại model mỗi lần vào form.** Một `on-entry` luôn gán `new OrderDraft()` sẽ xóa dữ liệu khi transition phục hồi quay lại màn hình. Hãy tạo model một lần bằng flow variable hoặc khởi tạo có điều kiện.

**Đẩy bản nháp lên HTTP session để “chắc chắn còn”.** Cách này kéo dài vòng đời ngoài nhu cầu của flow và dễ gây lẫn dữ liệu giữa nhiều tab. Nếu cần mở lại dài hạn, dùng bản nháp có định danh và kiểm soát truy cập trong kho lưu trữ.

Các đối tượng được giữ trong trạng thái flow cần tương thích với cơ chế snapshot, serialization hoặc repository mà ứng dụng dùng. DTO nhỏ, có thể serialize khi cần, thường dễ quản lý hơn entity đang gắn persistence context, stream, request, response hay stack trace ngoại lệ.

## 4. Mô hình hóa đường phục hồi thành state và event

Ví dụ sau tập trung vào việc gửi đơn khi kết quả có thể chưa xác định. Giả định ứng dụng đã có:

- `OrderDraft`: JavaBean có `quantity`, các thuộc tính form khác và `requestKey`.
- Bean `submissionActions`: gọi dịch vụ, thêm message và trả về tên kết quả.
- Các view `orderForm`, `orderRecovery`, `orderSubmitted`.

`requestKey` được tạo một lần cho một ý định gửi đơn. Nó được giữ ổn định khi kiểm tra lại hoặc gửi lại chính yêu cầu đó. Dịch vụ phía sau phải thực thi tính idempotent cho khóa này; việc lưu một UUID ở giao diện không tự ngăn được đơn hàng trùng.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="draft" class="com.example.order.OrderDraft" />

    <view-state id="edit" view="orderForm" model="draft">
        <transition on="confirm" to="submit" />
        <transition on="cancel" to="cancelled" bind="false" />
    </view-state>

    <action-state id="submit">
        <evaluate expression="submissionActions.submit(flowScope.draft, messageContext)" />
        <transition on="accepted" to="completed" />
        <transition on="rejected" to="edit" />
        <transition on="unknown" to="recover" />
    </action-state>

    <view-state id="recover" view="orderRecovery" model="draft">
        <transition on="checkStatus" to="checkStatus" bind="false" />
    </view-state>

    <action-state id="checkStatus">
        <evaluate expression="submissionActions.checkStatus(flowScope.draft, messageContext)" />
        <transition on="accepted" to="completed" />
        <transition on="rejected" to="edit" />
        <transition on="unknown" to="recover" />
    </action-state>

    <end-state id="completed" view="orderSubmitted" />
    <end-state id="cancelled" />
</flow>
```

Luồng phục hồi có các đặc điểm quan trọng:

1. `draft` được tạo ở cấp flow, nên transition từ `submit` về `edit` không tự tạo một bản nháp mới.
2. Khi kết quả là `unknown`, giao diện chuyển đến `recover`, nơi chỉ có hành động kiểm tra trạng thái trong ví dụ này.
3. `checkStatus` dùng `bind="false"` vì thao tác kiểm tra không cần ghi đè model từ các trường trong request.
4. `completed` chỉ được đi tới sau kết quả `accepted` đã được dịch vụ xác nhận.
5. Màn hình phục hồi không có nút gửi lại ngay. Nếu sản phẩm cần hành động đó, phải bổ sung điều kiện nghiệp vụ và bảo đảm idempotency trước.

Không thêm transition từ `recover` quay thẳng về sửa đơn khi yêu cầu cũ vẫn có thể được chấp nhận ở phía dịch vụ. Nếu cho sửa trong lúc chưa biết kết quả, cần tách rõ bản yêu cầu đã gửi với một bản nháp mới để tránh đổi nội dung dưới cùng một khóa.

### Action chuyển kết quả nghiệp vụ thành event

Đoạn Java dưới đây minh họa cách viết action cho XML trên. `SubmissionGateway` là cổng dịch vụ của ứng dụng; nó phải phân loại kết quả theo hợp đồng thật của hệ thống.

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

public final class SubmissionActions {
    private final SubmissionGateway gateway;

    public SubmissionActions(SubmissionGateway gateway) {
        this.gateway = gateway;
    }

    public String submit(OrderDraft draft, MessageContext messages) {
        try {
            SubmissionOutcome outcome = gateway.submit(draft);
            return toEvent(outcome, messages);
        } catch (SubmissionOutcomeUnknownException ex) {
            // Lỗi đã được phân loại: yêu cầu có thể đã được tiếp nhận.
            // Ghi log kỹ thuật qua cơ chế logging của ứng dụng.
            return unknown(messages);
        }
    }

    public String checkStatus(OrderDraft draft, MessageContext messages) {
        try {
            SubmissionOutcome outcome = gateway.findByRequestKey(
                    draft.getRequestKey());
            return toEvent(outcome, messages);
        } catch (StatusLookupUnavailableException ex) {
            return unknown(messages);
        }
    }

    private String toEvent(SubmissionOutcome outcome,
                           MessageContext messages) {
        switch (outcome) {
            case ACCEPTED:
                return "accepted";
            case REJECTED:
                messages.addMessage(new MessageBuilder()
                        .error()
                        .code("order.submit.rejected")
                        .defaultText("Đơn chưa được chấp nhận. "
                                + "Hãy kiểm tra dữ liệu trước khi gửi lại.")
                        .build());
                return "rejected";
            case UNKNOWN:
                return unknown(messages);
            default:
                throw new IllegalStateException("Unsupported submission outcome");
        }
    }

    private String unknown(MessageContext messages) {
        messages.addMessage(new MessageBuilder()
                .warning()
                .code("order.submit.unknown")
                .defaultText("Chưa xác định được kết quả gửi đơn. "
                        + "Dữ liệu của bạn vẫn được giữ trong phiên hiện tại. "
                        + "Hãy kiểm tra trạng thái trước khi gửi lại.")
                .build());
        return "unknown";
    }
}
```

Các kiểu `SubmissionGateway`, `SubmissionOutcome` và hai ngoại lệ trong ví dụ là kiểu do ứng dụng định nghĩa, không phải API sẵn có của Spring Web Flow. `SubmissionOutcome` có ba giá trị `ACCEPTED`, `REJECTED`, `UNKNOWN`.

Hợp đồng của `REJECTED` phải đủ mạnh: yêu cầu hiện tại đã bị từ chối một cách xác định và không còn tiếp tục xử lý để tạo đơn ở phía sau. Nếu hệ thống chỉ báo “không tìm thấy” trong một kho đọc có độ trễ, kết quả đó chưa đủ để coi là `REJECTED`; nên giữ `UNKNOWN` cho đến khi xác định được kết quả.

Ví dụ chỉ chuyển những lỗi đã được phân loại thành kết quả phục hồi. Các lỗi không dự kiến vẫn cần cơ chế xử lý ngoại lệ và logging thích hợp ở cấp flow hoặc ứng dụng. Không dùng `catch (Exception)` rồi trả về `unknown` cho mọi lỗi vì điều đó có thể che lỗi lập trình và làm sai ý nghĩa trạng thái.

## 5. Viết thông báo đủ để hành động

Một thông báo tốt trả lời được: điều gì đã xảy ra, dữ liệu còn ở đâu và người dùng nên làm gì tiếp theo.

| Thông báo yếu | Thông báo có thể hành động |
| --- | --- |
| “Lỗi hệ thống.” | “Chưa tải được trạng thái đơn. Hãy chọn Kiểm tra trạng thái sau ít phút.” |
| “Không hợp lệ.” | “Số lượng phải lớn hơn 0.” |
| “Giao dịch thất bại.” khi chỉ có timeout | “Chưa xác định được kết quả. Hãy kiểm tra trạng thái trước khi gửi lại.” |
| “Dữ liệu đã được lưu.” khi chỉ có `flowScope` | “Dữ liệu vẫn được giữ trong phiên hiện tại.” |

Không hiện `ex.getMessage()` trực tiếp cho người dùng. Nội dung ngoại lệ có thể chứa tên bảng, câu SQL, URL nội bộ hoặc dữ liệu nhạy cảm. Thay vào đó, ánh xạ sang mã thông báo ổn định và ghi chi tiết kỹ thuật vào log theo chính sách của ứng dụng.

Có thể cung cấp mã hỗ trợ hoặc mã đối chiếu để nhân viên hỗ trợ tìm request liên quan. Mã này phải gắn được với log hoặc bản ghi nghiệp vụ, được render có escape và không chứa bí mật. Không nhầm mã đối chiếu giao diện với một cơ chế phân quyền: biết mã không có nghĩa là được phép xem đơn.

Không cam kết “không bị trừ tiền” hoặc “đơn chưa được tạo” nếu hệ thống chưa xác nhận điều đó. Sự trung thực về trạng thái là một phần của thiết kế phục hồi.

## 6. Giữ dữ liệu vừa đủ và đúng ranh giới giao dịch

Một recovery view thường cần các dữ liệu sau:

- Bản nháp hoặc bản chụp dữ liệu đã gửi, tùy trạng thái xử lý.
- Khóa yêu cầu hoặc định danh nghiệp vụ để tra trạng thái.
- Trạng thái đã được xác nhận, cùng thời điểm kiểm tra nếu cần cho giao diện.
- Định danh bản nháp lưu bền vững nếu sản phẩm hỗ trợ mở lại sau này.

Không giữ nguyên đối tượng exception trong `flowScope` chỉ để render lỗi. Ngoài nguy cơ lộ thông tin, một đồ thị exception lớn làm tăng kích thước trạng thái và có thể không phù hợp với cơ chế lưu flow.

### Rollback dữ liệu và khôi phục flow là hai cơ chế khác nhau

Rollback một transaction cơ sở dữ liệu không tự khôi phục mọi thay đổi đã thực hiện trên Java object trong `flowScope`. Tương tự, quay về một snapshot flow không đảo ngược được email đã gửi, giao dịch ở hệ thống ngoài hoặc đơn hàng đã được commit.

Ví dụ, nếu action đặt `draft.status = "SUBMITTED"` trước khi gọi dịch vụ rồi dịch vụ gặp timeout, DTO có thể thể hiện một kết luận chưa được chứng minh. Cách dễ kiểm soát hơn là:

1. Giữ riêng trạng thái yêu cầu đã gửi và kết quả đã được xác nhận.
2. Chỉ cập nhật trạng thái thành công sau khi có bằng chứng chấp nhận.
3. Khi chưa biết kết quả, lưu định danh đối chiếu rồi chuyển đến recovery state.
4. Trước thao tác tiếp theo, xác minh lại điều kiện nghiệp vụ ở phía server.

Nút bị vô hiệu hóa sau click chỉ là hỗ trợ giao diện. Khả năng chống gửi trùng cần được thực thi ở tầng dịch vụ hoặc kho dữ liệu với khóa và ràng buộc phù hợp.

## 7. Khi không còn flow execution để quay lại

Các transition phục hồi trong XML chỉ có tác dụng khi execution còn truy cập được và hệ thống vẫn có thể tiếp tục xử lý nó. Nếu người dùng mở URL execution cũ sau khi phiên hết hạn hoặc trạng thái đã bị loại khỏi repository, không thể giả định `flowScope.draft` vẫn còn để render lại.

Ở ranh giới tích hợp Spring MVC và Web Flow, ứng dụng cần một đường xử lý bên ngoài execution cho trường hợp này. Tùy cấu hình, đó có thể là cơ chế xử lý ngoại lệ của adapter/resolver và một trang phục hồi độc lập. Không coi `@ControllerAdvice` là giải pháp tự động bao phủ mọi lỗi từ Web Flow; cần kiểm tra đường dispatch và resolver thực tế.

Trang phục hồi nên cung cấp hành động rõ ràng:

- Đăng nhập lại nếu phiên xác thực hết hạn.
- Mở flow mới từ bản nháp đã lưu, nếu ứng dụng có tính năng đó.
- Bắt đầu lại và giải thích rằng dữ liệu chỉ nằm trong phiên cũ không thể khôi phục.

Nếu dùng bản nháp bền vững, hãy kiểm tra quyền sở hữu trước khi nạp lại; không dựa vào draft ID gửi từ trình duyệt. Sau khi nạp, vẫn phải kiểm tra lại giá, tồn kho và điều kiện nghiệp vụ vì dữ liệu ngoài flow có thể đã thay đổi.

### Phục hồi qua subflow

Nếu một bước nhập địa chỉ nằm trong subflow, `flowScope` của subflow là trạng thái của flow session đó. Khi subflow kết thúc, dữ liệu cần dùng tiếp phải được truyền qua output đã khai báo hoặc qua một hợp đồng chia sẻ có chủ đích.

Đừng dựa vào việc một message của subflow tình cờ còn hiển thị ở flow cha. Flow cha nên nhận kết quả có cấu trúc, cập nhật bản nháp thuộc quyền quản lý của nó và tạo thông báo phù hợp với màn hình tiếp theo.

## 8. Các tình huống cần kiểm chứng khi triển khai

Các tình huống sau là tiêu chí cho phần triển khai và kiểm thử tiếp theo; chúng không thay thế việc chạy kiểm thử trong ứng dụng thực tế.

| Thao tác hoặc sự cố | Kết quả mong đợi |
| --- | --- |
| Nhập chuỗi vào trường số | Hiện lỗi binding, giữ giá trị nhập để sửa, chưa gọi gửi đơn |
| Dịch vụ từ chối theo nghiệp vụ | Về form với dữ liệu hợp lệ đã nhập và thông báo dễ hiểu |
| Timeout sau khi gửi | Vào recovery state, giữ khóa yêu cầu, không tự gửi lại |
| Kiểm tra thấy yêu cầu đã được chấp nhận | Đi tới trạng thái hoàn tất mà không tạo yêu cầu mới |
| Tra cứu chưa có kết luận | Ở lại đường phục hồi và tiếp tục dùng cùng định danh đối chiếu |
| Người dùng refresh hoặc gửi lặp | Không tạo tác dụng phụ trùng nhờ cơ chế idempotency ở server |
| Quay lại form sau lỗi | Không chạy khởi tạo ghi đè bản nháp |
| Mở hai flow ở hai tab | Dữ liệu được phân biệt theo execution; dữ liệu chia sẻ được kiểm soát |
| Execution hết hiệu lực | Trang phục hồi độc lập hoạt động, không hứa khôi phục dữ liệu chỉ có trong phiên |
| Kết thúc subflow | Flow cha nhận đúng output cần thiết và có thông báo của màn hình cha |

Một điểm cần kiểm chứng riêng là thông báo có hiển thị đúng sau redirect theo cấu hình thực tế hay không. Thử cả lỗi theo trường, lỗi tổng quát và quay lại cùng view-state; tránh kết luận chỉ từ việc action đã gọi `addMessage()`.

## 9. Nguyên tắc ghi nhớ

Trong Spring Web Flow, phục hồi là một phần của mô hình hành trình. `MessageContext` giải thích tình huống; scope giữ dữ liệu theo đúng vòng đời; state và transition giới hạn hành động tiếp theo; tầng dịch vụ xác nhận kết quả và ngăn tác dụng phụ trùng.

Khi thiết kế một nhánh lỗi, hãy xác định đồng thời: **người dùng sẽ đọc gì, dữ liệu nào còn tồn tại, sự thật nghiệp vụ nào đã biết và event nào được phép tiếp tục**. Bốn câu trả lời này giúp một màn hình báo lỗi trở thành một bước phục hồi có thể sử dụng được.