# Redirect và báo lỗi trong phản hồi Ajax

Một màn hình đặt phòng dùng Ajax để cập nhật phần tóm tắt mà không tải lại cả trang. Khi người dùng bấm xác nhận, có ba kết quả thường gặp: flow trả về HTML fragment để thay vùng nội dung; flow cần chuyển người dùng sang một view hoặc URL khác; hoặc thao tác thất bại và giao diện cần hiển thị thông báo lỗi. Ba kết quả này cần được biểu diễn khác nhau trong phản hồi HTTP.

Spring Web Flow (SWF) hỗ trợ nhận diện Ajax request và gửi chỉ dẫn redirect phù hợp với thư viện phía client. Với lỗi nghiệp vụ, flow có thể thêm message vào `MessageContext`, phát event kết quả và render lại fragment chứa lỗi. Với exception chưa được xử lý trong flow, `FlowExecutionExceptionHandler`, `FlowHandler` hoặc cơ chế xử lý exception của Spring MVC quyết định phản hồi lỗi.

Bài thuộc chương **Ajax và phân mảnh** của module `SPRING_WEB_FLOW`. Nội dung tập trung vào cách SWF 2.5.x phân biệt HTML fragment, redirect instruction và error response; cách cấu hình `AjaxHandler`; cách xử lý lỗi nghiệp vụ và lỗi hệ thống; cách viết client đọc response; và cách kiểm thử cả flow lẫn HTTP contract.

## 1. Ba loại phản hồi Ajax cần phân biệt

Một Ajax request đi qua Spring MVC và `FlowHandlerAdapter`. Flow xử lý event như request thông thường, sau đó framework quyết định cần render view, render fragment hay yêu cầu trình duyệt điều hướng.

| Kết quả | Nội dung phản hồi | Hành vi phía client |
|---|---|---|
| Cập nhật thành công | HTML fragment hoặc định dạng partial response của JSF | Thay vùng giao diện tương ứng |
| Cần điều hướng | Redirect instruction, thường nằm trong response header | Đọc URL và điều hướng trình duyệt |
| Lỗi nghiệp vụ có thể khắc phục | Fragment chứa validation/message error | Giữ màn hình hiện tại và hiển thị lỗi |
| Lỗi kỹ thuật chưa xử lý | HTTP error status và error body/view do tầng xử lý exception quyết định | Hiển thị thông báo chung, ghi nhận mã lỗi và cho phép thử lại phù hợp |

Không nên đồng nhất lỗi nghiệp vụ với exception kỹ thuật. Ví dụ, phòng vừa được người khác đặt là tình huống nghiệp vụ cần thông báo cho người dùng; database ngừng hoạt động là lỗi kỹ thuật cần được ghi log và trả thông tin an toàn. Cả hai có thể xảy ra trong một Ajax request nhưng không nên có cùng cách xử lý.

~~~mermaid
flowchart TD
    A["Ajax request gửi event tới FlowHandlerAdapter"] --> B["FlowExecutor xử lý event"]
    B --> C{"Kết quả xử lý"}
    C -->|"View cần cập nhật"| D["Render HTML fragment / JSF partial response"]
    C -->|"Flow cần điều hướng"| E["AjaxHandler tạo redirect instruction"]
    C -->|"Lỗi nghiệp vụ"| F["MessageContext + result event"]
    F --> G["Render fragment chứa thông báo"]
    C -->|"Exception chưa xử lý"| H["Flow exception handler / MVC resolver"]
    H --> I["Error view hoặc HTTP error body"]
    D --> J["Client cập nhật vùng giao diện"]
    E --> K["Client điều hướng tới URL"]
    G --> J
    I --> L["Client hiển thị lỗi và mã tham chiếu"]
~~~

## 2. AjaxHandler trong Spring Web Flow

`AjaxHandler` là strategy interface giúp SWF nhận biết request có phải Ajax hay không và gửi chỉ dẫn redirect phù hợp với thư viện client. Trong Spring Web Flow 2.5.x, interface `org.springframework.webflow.context.servlet.AjaxHandler` có hai trách nhiệm chính:

- `isAjaxRequest(request, response)`: xác định request hiện tại có phải Ajax request.
- `sendAjaxRedirect(targetUrl, request, response, popup)`: gửi redirect instruction để client thực hiện request mới tới URL đích.

`AjaxHandler` **không định nghĩa một phương thức `sendAjaxError`** và không phải nơi chuẩn hóa JSON error response. Phần lỗi phải được xử lý bởi flow, exception handler hoặc Spring MVC exception infrastructure.

### 2.1. DefaultAjaxHandler nhận diện request như thế nào?

SWF 2.5.x cung cấp `DefaultAjaxHandler`. Implementation này nhận diện Ajax request bằng một trong hai cách:

- Header `Accept` có giá trị `text/html;type=ajax`.
- Request parameter tên `ajaxSource`.

Khi cần redirect trong Ajax request, handler đặt các response header:

| Header | Ý nghĩa |
|---|---|
| `Spring-Redirect-URL` | URL mà Ajax client cần điều hướng tới |
| `Spring-Modal-View` | Có giá trị khi redirect xuất phát từ view-state được cấu hình `popup="true"` |

Tên header là hợp đồng giữa server và client. Một client dùng `fetch`, jQuery hoặc thư viện riêng phải đọc header tương ứng và thực hiện điều hướng. Trình duyệt không tự động chuyển trang chỉ vì response có `Spring-Redirect-URL`.

### 2.2. Gắn AjaxHandler vào FlowHandlerAdapter

`FlowHandlerAdapter` có thuộc tính `ajaxHandler`. Có thể khai báo rõ `DefaultAjaxHandler` trong XML:

~~~xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
    <property name="ajaxHandler">
        <bean class="org.springframework.webflow.context.servlet.DefaultAjaxHandler" />
    </property>
</bean>
~~~

Nếu ứng dụng đã dùng cấu hình mặc định của SWF 2.5.x, không nhất thiết phải khai báo lại handler. Khai báo tường minh có ích khi cần đọc cấu hình, thay thế bằng handler riêng hoặc kiểm tra wiring của ứng dụng.

Với JSF, SWF cung cấp `JsfAjaxHandler` và `JsfFlowHandlerAdapter`. Handler này tạo redirect instruction theo định dạng partial response của JSF. Client JSF đọc chỉ dẫn đó trong vòng đời Ajax của JSF; không nên tự xử lý response như HTML fragment thông thường.

### 2.3. Tích hợp thư viện Ajax khác

Nếu dùng một thư viện không được handler mặc định nhận diện, hãy cài `AjaxHandler` tương thích với giao thức của client rồi inject vào `FlowHandlerAdapter` hoặc `FlowController`.

Ví dụ một implementation đơn giản có thể kế thừa `AbstractAjaxHandler`:

~~~java
package com.example.webflow;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import org.springframework.webflow.context.servlet.AbstractAjaxHandler;

public class ApplicationAjaxHandler extends AbstractAjaxHandler {

    private static final String AJAX_HEADER = "X-Requested-With";
    private static final String AJAX_VALUE = "XMLHttpRequest";
    private static final String REDIRECT_HEADER = "X-Flow-Redirect";

    @Override
    protected boolean isAjaxRequestInternal(
            HttpServletRequest request,
            HttpServletResponse response) {
        return AJAX_VALUE.equals(request.getHeader(AJAX_HEADER));
    }

    @Override
    protected void sendAjaxRedirectInternal(
            String targetUrl,
            HttpServletRequest request,
            HttpServletResponse response,
            boolean popup) {

        response.setHeader(REDIRECT_HEADER, targetUrl);

        if (popup) {
            response.setHeader("X-Flow-Popup", "true");
        }
    }
}
~~~

Đây là giao thức riêng của ứng dụng, không phải tên header mặc định của SWF. Client phải đọc `X-Flow-Redirect` và `X-Flow-Popup` tương ứng. Nếu cần URL redirect an toàn, chỉ chấp nhận đích do server tạo hoặc kiểm tra origin/allowlist trước khi gửi header.

Đăng ký handler riêng:

~~~xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
    <property name="ajaxHandler">
        <bean class="com.example.webflow.ApplicationAjaxHandler" />
    </property>
</bean>
~~~

Handler ví dụ chỉ mô tả cách nhận diện request và gửi redirect instruction. Nó không thay thế xử lý exception và không tự tạo error body.

## 3. Khi flow cần redirect trong một Ajax request

Thông thường SWF dùng POST-REDIRECT-GET khi đi vào view-state. Với Ajax request, `AjaxHandler` có thể gửi redirect instruction để client điều hướng mà không nhận một HTML document rồi nhét nhầm vào fragment.

Ví dụ flow hoàn tất xác nhận và chuyển sang trang hóa đơn:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="reviewBooking" view="booking/review">
        <transition on="confirm" to="bookingConfirmed" />
    </view-state>

    <end-state id="bookingConfirmed"
               view="externalRedirect:contextRelative:/booking/receipt" />
</flow>
~~~

Nếu event `confirm` được gửi bằng Ajax và kết quả yêu cầu redirect, handler mặc định có thể trả `Spring-Redirect-URL` thay vì để client hiểu nhầm response là fragment cần cập nhật.

### 3.1. Client đọc redirect header

Ví dụ client dùng Fetch API và giao thức mặc định của `DefaultAjaxHandler`:

~~~javascript
async function submitFlowEvent(form) {
    const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: {
            "Accept": "text/html;type=ajax"
        }
    });

    const redirectUrl = response.headers.get("Spring-Redirect-URL");

    if (redirectUrl) {
        navigateToApprovedUrl(redirectUrl);
        return;
    }

    if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        showRequestError(
            errorBody && errorBody.message
                ? errorBody.message
                : "Không thể xử lý yêu cầu lúc này."
        );
        return;
    }

    const fragmentHtml = await response.text();
    replaceBookingPanel(fragmentHtml);
}
~~~

Ví dụ giả định view trả về HTML fragment khi thành công và response body JSON khi có lỗi HTTP. `navigateToApprovedUrl` cần kiểm tra URL theo chính sách origin/allowlist của ứng dụng; `replaceBookingPanel` thay đúng vùng giao diện. Nếu ứng dụng dùng Tiles, JSF hoặc một định dạng partial response khác, phần đọc body cần tuân theo giao thức tương ứng.

Không điều hướng tới URL tùy ý lấy từ request parameter. Redirect header phải được tạo bởi server đáng tin cậy; nếu có khả năng điều hướng ra domain khác, kiểm tra origin hoặc allowlist theo chính sách ứng dụng.

### 3.2. Embedded mode và redirect

Nếu flow được nhúng vào một vùng của trang và mọi Ajax event chỉ nên cập nhật vùng đó, khởi chạy flow với input `mode=embedded`:

~~~text
/booking?mode=embedded
~~~

Trong embedded mode, SWF không phát flow execution redirect cho Ajax request theo hành vi mặc định của flow top-level. Điều này cho phép flow đi qua nhiều view-state mà không tải lại toàn bộ trang bao quanh.

Embedded mode không tự tạo partial response. View vẫn cần cấu hình render fragment, ví dụ:

~~~xml
<view-state id="reviewBooking" view="booking/review">
    <transition on="refreshSummary">
        <evaluate expression="bookingService.loadSummary(booking)"
                  result="viewScope.summary" />
        <render fragments="bookingForm:summaryPanel" />
    </transition>
</view-state>
~~~

`<render fragments="..."/>` chọn vùng view cần render. Client phải biết cách thay vùng đó theo view technology đang dùng. Với JSF, dùng cơ chế partial processing/rendering của JSF; với Spring JS/Tiles, cấu hình fragment tương ứng.

## 4. Trả lỗi nghiệp vụ trong fragment thay vì ném exception

Một lỗi nghiệp vụ có thể dự đoán được nên trở thành kết quả của action. Ví dụ, phòng vừa hết chỗ hoặc mã khuyến mại không còn hiệu lực. Flow có thể giữ thông báo trong `MessageContext`, trả event `error` và quay lại view để hiển thị fragment lỗi.

### 4.1. Action bắt lỗi nghiệp vụ và tạo message

~~~java
package com.example.booking;

import org.springframework.binding.message.MessageBuilder;
import org.springframework.webflow.execution.RequestContext;

public class BookingAction {

    private final BookingService bookingService;

    public BookingAction(BookingService bookingService) {
        this.bookingService = bookingService;
    }

    public String confirm(Booking booking, RequestContext context) {
        try {
            bookingService.confirm(booking);
            return "success";
        } catch (RoomUnavailableException ex) {
            context.getMessageContext().addMessage(
                new MessageBuilder()
                    .error()
                    .source("booking")
                    .code("booking.room.unavailable")
                    .defaultText("Phòng vừa hết chỗ. Hãy chọn phòng khác.")
                    .build()
            );
            return "error";
        }
    }
}
~~~

Action chỉ chuyển exception nghiệp vụ đã biết thành message dành cho người dùng. Không đưa stack trace hoặc nội dung exception nội bộ vào message. Các lỗi không dự kiến như database unavailable nên tiếp tục đi tới logging và exception handling của hệ thống.

### 4.2. Flow chuyển về view có thông báo lỗi

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="reviewBooking" view="booking/review">
        <on-entry>
            <render fragments="bookingForm:messages" />
        </on-entry>
        <transition on="confirm" to="confirmBooking" />
    </view-state>

    <action-state id="confirmBooking">
        <evaluate expression="bookingAction.confirm(booking, flowRequestContext)" />
        <transition on="success" to="bookingConfirmed" />
        <transition on="error" to="reviewBooking" />
    </action-state>

    <end-state id="bookingConfirmed"
               view="externalRedirect:contextRelative:/booking/receipt" />
</flow>
~~~

Khi service xác nhận thành công, action trả `success` và flow đi tới end-state. Khi gặp `RoomUnavailableException`, action thêm message và trả `error`; flow quay lại `reviewBooking`, nơi `on-entry` yêu cầu render fragment chứa thông báo.

Nếu request được gửi bằng Ajax trong embedded mode, flow có thể render vùng lỗi mà không chuyển toàn bộ trang. Nếu không ở embedded mode và flow cần redirect tới view-state khác, Ajax handler sẽ gửi redirect instruction theo giao thức đã cấu hình.

### 4.3. Phân biệt message lỗi và HTTP error status

Với lỗi nghiệp vụ có thể sửa, response thường vẫn là một phản hồi render bình thường: HTTP status thành công và body chứa fragment có message. Client thay fragment và giữ người dùng ở màn hình hiện tại.

Không nên trả HTTP 500 cho mọi validation error. Ngược lại, không nên biến lỗi hệ thống nghiêm trọng thành HTTP 200 chỉ để client dễ xử lý. Hãy chọn status theo bản chất lỗi và giữ một contract rõ ràng cho client.

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Thiếu trường bắt buộc hoặc dữ liệu không hợp lệ | Message/validation fragment, người dùng sửa và gửi lại |
| Phòng đã được đặt bởi người khác | Business error event, hiển thị lựa chọn thay thế |
| Người dùng không có quyền | Chặn bằng security/service, trả lỗi truy cập phù hợp |
| Execution key hết hạn hoặc không khôi phục được | Khởi động lại flow hoặc trả lỗi trạng thái phiên |
| Database/service không khả dụng | Log exception, trả HTTP 5xx và thông báo chung |
| Request sai cấu trúc hoặc thiếu tham số bắt buộc | HTTP 400 hoặc flow error theo hợp đồng endpoint |

## 5. Xử lý exception phát sinh trong flow execution

Một exception không được action bắt có thể được xử lý bởi `FlowExecutionExceptionHandler`. SWF cung cấp `TransitionExecutingFlowExecutionExceptionHandler`, cho phép ánh xạ một loại exception sang state đích.

Handler này đưa exception đã xử lý và root cause vào flash scope với hai key:

- `flowExecutionException`
- `rootCauseException`

Ví dụ Java Config đăng ký handler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.webflow.engine.FlowExecutionExceptionHandler;
import org.springframework.webflow.engine.support.TransitionExecutingFlowExecutionExceptionHandler;

@Configuration
public class FlowErrorConfig {

    @Bean
    public FlowExecutionExceptionHandler flowExceptionHandler() {
        return new TransitionExecutingFlowExecutionExceptionHandler()
            .add(InventoryServiceException.class, "systemError");
    }
}
~~~

Gắn handler vào flow definition:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <exception-handler bean="flowExceptionHandler" />

    <view-state id="reviewBooking" view="booking/review" />

    <view-state id="systemError" view="booking/system-error">
        <on-entry>
            <render fragments="bookingForm:errorPanel" />
        </on-entry>
    </view-state>
</flow>
~~~

Handler chuyển flow tới `systemError` khi exception phù hợp xảy ra. View lỗi nên hiển thị thông báo chung và hướng dẫn người dùng thử lại hoặc quay về bước an toàn. Không render trực tiếp stack trace, SQL, hostname, đường dẫn file hay dữ liệu nhạy cảm từ `rootCauseException`.

`FlowExecutionExceptionHandler` là extension point cấp flow runtime. Nó phức tạp hơn action trả event vì handler phải đưa execution về một state hợp lệ. Với lỗi nghiệp vụ thông thường, cách bắt exception trong action và trả event vẫn dễ hiểu, dễ kiểm thử hơn.

## 6. Lỗi chưa được xử lý trong flow: FlowHandler và Spring MVC

Có những exception xảy ra ngoài phạm vi mà flow exception handler xử lý được, ví dụ execution đã hết hạn hoặc không thể khôi phục từ repository. Ở tầng Servlet/MVC, `FlowHandler` cung cấp `handleException(...)` để tùy chỉnh cách xử lý `FlowException` chưa được xử lý.

~~~java
package com.example.booking.web;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import org.springframework.webflow.core.FlowException;
import org.springframework.webflow.execution.repository.NoSuchFlowExecutionException;
import org.springframework.webflow.mvc.servlet.AbstractFlowHandler;

public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleException(
            FlowException exception,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (exception instanceof NoSuchFlowExecutionException) {
            return "contextRelative:/booking/restart";
        }

        return null;
    }
}
~~~

Nếu trả về một resource location, `FlowHandlerAdapter` xử lý như một redirect tới tài nguyên lỗi/khôi phục. Nếu trả `null`, exception được chuyển cho xử lý mặc định của adapter. Theo mặc định, `NoSuchFlowExecutionException` có thể được khôi phục bằng cách khởi chạy execution mới; các `FlowException` khác được ném tiếp lên Spring MVC `ExceptionResolver`.

Để cài handler riêng cho flow `booking`, đăng ký bean có tên trùng flow ID trong application context:

~~~xml
<bean name="booking"
      class="com.example.booking.web.BookingFlowHandler" />
~~~

`FlowHandler.handleException(...)` trả về **đường dẫn để redirect**, không phải JSON error body. Nếu Ajax client cần một body JSON có status code, hãy để exception đi tới một `HandlerExceptionResolver` hoặc `@RestControllerAdvice` phù hợp với endpoint Ajax.

### 6.1. Trả JSON error body qua Spring MVC

Ví dụ dưới đây minh họa một error contract dành cho các endpoint Ajax trả JSON. Cấu hình này cần được giới hạn cho nhóm endpoint phù hợp và có Jackson message converter:

~~~java
package com.example.web;

import java.util.Collections;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.webflow.core.FlowException;

@RestControllerAdvice
public class FlowAjaxExceptionAdvice {

    @ExceptionHandler(FlowException.class)
    public ResponseEntity<Map<String, String>> handleFlowException(
            FlowException exception) {

        Map<String, String> body = Collections.singletonMap(
            "message",
            "Quy trình đã gián đoạn. Hãy tải lại và thử lại."
        );

        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(body);
    }
}
~~~

Đây là ví dụ cho endpoint có hợp đồng JSON. Trong ứng dụng dùng chung endpoint cho cả request HTML và Ajax, hãy phân biệt loại request bằng route hoặc content negotiation và chọn error view/JSON response tương ứng. Không trả `exception.getMessage()` hoặc stack trace cho client.

Nếu dùng `DefaultAjaxHandler` nhưng request cần thương lượng JSON, có thể gửi request parameter `ajaxSource` để handler vẫn nhận diện đây là Ajax request; header `Accept: application/json` khi đó dành cho JSON response. Đây là contract khác với request tải HTML fragment dùng `Accept: text/html;type=ajax`. Không dùng cùng một `Accept` value cho hai kiểu body rồi kỳ vọng Spring tự chọn đúng định dạng.

Một response JSON có thể mang cấu trúc ổn định như sau:

~~~json
{
  "code": "FLOW_EXECUTION_FAILED",
  "message": "Quy trình đã gián đoạn. Hãy tải lại và thử lại.",
  "correlationId": "req-7f31"
}
~~~

`correlationId` là mã tra cứu log do ứng dụng tạo. Nó giúp đội vận hành tìm exception chi tiết mà không phơi bày thông tin nội bộ trong response.

## 7. Client xử lý fragment, redirect và lỗi HTTP

Client nên kiểm tra kết quả theo thứ tự: redirect instruction, HTTP status, rồi mới đọc body fragment. Nếu cố parse mọi response thành HTML, một JSON error body hoặc một redirect instruction sẽ bị đưa nhầm vào vùng giao diện.

~~~javascript
async function sendAjaxEvent(url, formData) {
    const response = await fetch(url, {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: {
            "Accept": "text/html;type=ajax"
        }
    });

    const redirectUrl = response.headers.get("Spring-Redirect-URL");

    if (redirectUrl) {
        navigateToApprovedUrl(redirectUrl);
        return;
    }

    if (!response.ok) {
        let errorMessage = "Không thể xử lý yêu cầu lúc này.";

        const contentType = response.headers.get("Content-Type") || "";
        if (contentType.indexOf("application/json") >= 0) {
            try {
                const errorBody = await response.json();
                if (errorBody.message) {
                    errorMessage = errorBody.message;
                }
            } catch (ignored) {
                // JSON body không hợp lệ hoặc rỗng.
            }
        }

        showRequestError(errorMessage);
        return;
    }

    const html = await response.text();
    replaceBookingPanel(html);
}
~~~

Trong đoạn code:

- `Spring-Redirect-URL` có ưu tiên trước body vì response đang yêu cầu client điều hướng.
- `response.ok` kiểm tra status HTTP trong nhóm 2xx.
- Error body được parse có kiểm soát; nếu server trả HTML error page hoặc body rỗng, client dùng thông báo dự phòng.
- HTML fragment chỉ được chèn vào vùng đã định trước. Nội dung do server render vẫn cần được escape đúng theo view technology.

Nếu dùng custom `AjaxHandler`, thay tên header và điều kiện nhận diện bằng giao thức ứng dụng đã cấu hình. Nếu dùng JSF, để JSF JavaScript xử lý partial response và redirect instruction của `JsfAjaxHandler`.

Đoạn Fetch ở trên là contract HTML fragment dùng `Accept: text/html;type=ajax`. Với request có JSON error contract, gửi `Accept: application/json` và đánh dấu Ajax bằng request parameter `ajaxSource` (hoặc custom handler); khi đó server có thể trả JSON từ exception resolver. Hai kiểu response cần được client phân nhánh theo content type, không cố chèn JSON vào vùng HTML.

## 8. Kiểm thử redirect và error response

Nên kiểm thử ở hai mức:

1. **Flow execution test**: xác minh event, state, message và nhánh xử lý exception.
2. **HTTP/MVC integration test**: xác minh Ajax detection, redirect header, status code, content type và error body.

### 8.1. Flow test cho lỗi nghiệp vụ

Dùng fake service ném `RoomUnavailableException`, sau đó gửi event `confirm`. Kết quả mong đợi là flow quay lại `reviewBooking` và message error có mặt trong message context.

~~~java
public void testUnavailableRoomReturnsToReviewState() {
    MockExternalContext context = new MockExternalContext();
    startFlow(context);

    MockExternalContext confirmContext = new MockExternalContext();
    confirmContext.setAjaxRequest(true);
    confirmContext.setEventId("confirm");
    resumeFlow(confirmContext);

    assertCurrentStateEquals("reviewBooking");
    assertTrue(fakeBookingService.wasConfirmationAttempted());
    assertTrue(getFlowExecutionContext().isActive());
}
~~~

Đây là cấu trúc minh họa cho test fixture SWF 2.x. Test cụ thể cần cấu hình fake để phát sinh lỗi nghiệp vụ và xác minh message theo API `MessageContext` của test harness đang dùng. `MockExternalContext.setAjaxRequest(true)` giúp mô phỏng cờ Ajax ở mức flow execution; nó không kiểm tra response header Servlet thực tế.

### 8.2. HTTP test cho redirect header

Với Spring MVC integration test, gửi request có Accept header mà `DefaultAjaxHandler` nhận diện. Khi flow yêu cầu redirect, xác minh header:

~~~java
mockMvc.perform(post("/booking")
        .param("execution", executionKey)
        .param("_eventId_confirm", "")
        .accept("text/html;type=ajax"))
    .andExpect(status().isOk())
    .andExpect(header().exists("Spring-Redirect-URL"));
~~~

Đoạn test minh họa tên URL và execution parameter; điều chỉnh theo `FlowUrlHandler` và cách view gửi event trong ứng dụng. Nếu flow đang chạy embedded mode và event chỉ render fragment trong cùng state, response có thể không có redirect header. Hãy chọn một transition thực sự cần điều hướng để kiểm thử redirect.

### 8.3. HTTP test cho error body

Nếu exception được chuyển tới `@RestControllerAdvice`, kiểm tra status và nội dung JSON:

~~~java
mockMvc.perform(post("/booking/ajax")
        .header("Accept", "application/json")
        .param("execution", executionKey)
        .param("_eventId_confirm", ""))
    .andExpect(status().is5xxServerError())
    .andExpect(content().contentTypeCompatibleWith("application/json"))
    .andExpect(jsonPath("$.message").exists());
~~~

Đường dẫn `/booking/ajax` ở đây là endpoint minh họa dành cho JSON contract. Nếu ứng dụng chỉ có một flow endpoint, hãy cấu hình exception resolver hoặc controller advice phù hợp để phân biệt request JSON với request fragment HTML.

### 8.4. Ma trận kiểm thử tối thiểu

| Ca kiểm thử | Điều cần xác minh |
|---|---|
| Ajax event thành công, cùng view-state | Response chứa fragment, không điều hướng toàn trang |
| Ajax event chuyển sang view-state mới trong embedded mode | Không phát flow execution redirect mặc định |
| Ajax event yêu cầu redirect ở top-level flow | Có `Spring-Redirect-URL` |
| View-state popup redirect | Có `Spring-Modal-View` theo cấu hình popup |
| Business exception đã biết | Message được thêm và fragment lỗi được render |
| Exception được ánh xạ bởi `FlowExecutionExceptionHandler` | Flow chuyển tới error state hợp lệ |
| Execution key hết hạn | Có đường khởi động lại hoặc error route đã định nghĩa |
| Exception không được flow xử lý | Được chuyển tới FlowHandler/MVC exception resolver |
| HTTP 5xx JSON response | Client hiển thị message an toàn và mã tương quan |
| Redirect URL ngoài origin | Client từ chối điều hướng nếu chính sách chỉ cho phép same-origin |
| Request không phải Ajax | Hành vi HTML/full-page vẫn hoạt động đúng |

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ajax nhận HTML của cả trang thay vì fragment | Flow/view chưa chọn fragment hoặc view resolver không hỗ trợ partial rendering | Kiểm tra `<render fragments="..."/>` và Tiles/view technology |
| Response có redirect header nhưng trang không đổi | Client không đọc `Spring-Redirect-URL` | Bổ sung logic điều hướng ở client |
| Ajax request không được nhận diện | Header `Accept` hoặc parameter không khớp handler | Kiểm tra `DefaultAjaxHandler` hoặc custom handler |
| Bấm nút trong embedded flow làm tải lại trang | Flow không được khởi chạy với `mode=embedded` hoặc request không được nhận diện là Ajax | Kiểm tra input khi launch và Ajax request header |
| Message lỗi không xuất hiện | Action không thêm message hoặc fragment lỗi không được render | Kiểm tra `MessageContext`, state đích và fragment ID |
| Lỗi nghiệp vụ trả HTTP 500 | Exception bị ném khỏi action thay vì chuyển thành result event | Bắt lỗi nghiệp vụ đã biết, thêm message và trả event |
| Lỗi database bị hiển thị như lỗi validation | Catch quá rộng và biến mọi exception thành message | Chỉ catch exception nghiệp vụ dự kiến |
| Client cố parse redirect response thành JSON | Không kiểm tra redirect header trước body | Xử lý redirect trước status/body |
| Client chèn JSON error vào vùng HTML | Không kiểm tra `response.ok` và content type | Phân nhánh theo status và định dạng response |
| Ajax client nhận trang trắng sau exception | Exception chưa được xử lý hoặc error response không đúng contract | Kiểm tra FlowExecutionExceptionHandler và MVC resolver |
| Stack trace xuất hiện trong response | Trả exception message hoặc root cause trực tiếp | Trả thông báo chung và correlation ID |

## 10. Bài tập thực hành

Xây dựng flow đặt phòng khách sạn với màn hình `reviewBooking` được cập nhật bằng Ajax.

Yêu cầu:

1. Khi người dùng cập nhật số khách, chỉ render fragment `guestSummary`.
2. Khi xác nhận đặt phòng thành công, flow chuyển tới trang hóa đơn.
3. Khi phòng hết chỗ, action bắt `RoomUnavailableException`, thêm message vào `MessageContext`, trả event `error` và render fragment `messages`.
4. Khởi chạy một biến thể của flow bằng `mode=embedded` và so sánh với flow top-level mặc định.
5. Cấu hình `DefaultAjaxHandler` và xác minh header `Spring-Redirect-URL` khi redirect xảy ra.
6. Cấu hình `FlowExecutionExceptionHandler` cho một exception kỹ thuật có thể ánh xạ an toàn tới `systemError`.
7. Viết MVC exception handler trả JSON error body với HTTP 5xx cho exception không được xử lý trong flow.
8. Viết client đọc redirect header, kiểm tra status và cập nhật fragment theo đúng định dạng response.
9. Kiểm thử redirect, lỗi nghiệp vụ, lỗi kỹ thuật, execution hết hạn và request không phải Ajax.
10. Xác minh response không chứa stack trace, thông tin database hoặc dữ liệu nhạy cảm.

**Tiêu chí hoàn thành:** người học phân biệt được redirect instruction với HTML fragment và error body; giải thích được `AjaxHandler` làm nhiệm vụ gì; biết khi nào chuyển lỗi thành result event, khi nào dùng `FlowExecutionExceptionHandler`, và khi nào để Spring MVC xử lý exception. Client phải thực hiện đúng một trong ba hành vi: cập nhật fragment, điều hướng hoặc hiển thị lỗi có kiểm soát.

## Tài liệu tham khảo

- Spring Web Flow 2.5.1 Reference Guide — [Handling Ajax Requests](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/): `AjaxHandler`, partial rendering và tích hợp Spring MVC/Web Flow.
- Spring Web Flow 2.5.1 Reference Guide — [Action Exceptions](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/): chuyển business exception thành message và result event; dùng `exception-handler`.
- Spring Web Flow API — [DefaultAjaxHandler](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/context/servlet/DefaultAjaxHandler.html): nhận diện Ajax request và các response header redirect.
- Spring Web Flow API — [FlowHandlerAdapter](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/mvc/servlet/FlowHandlerAdapter.html): cấu hình AjaxHandler và hành vi xử lý FlowException.
- Spring Web Flow API — [FlowExecutionExceptionHandler](https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/engine/FlowExecutionExceptionHandler.html): xử lý exception trong flow execution.

*Ghi chú tương thích:* Các ví dụ dựa trên Spring Web Flow 2.5.x, Spring Framework 5 và Servlet API `javax.servlet`. SWF 2.5 yêu cầu JSF 2.2 trở lên khi dùng Spring Faces. Kiểm tra package, handler mặc định, view technology và giao thức Ajax theo phiên bản thực tế của ứng dụng.
