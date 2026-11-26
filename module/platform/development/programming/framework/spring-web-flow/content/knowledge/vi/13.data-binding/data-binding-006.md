# Khai báo output ở flow và end-state phù hợp

Một flow Spring Web Flow thường nhận dữ liệu đầu vào, dẫn người dùng qua nhiều bước rồi kết thúc bằng một kết quả. Ví dụ, flow đặt phòng nhận `hotelId`, thu thập ngày nhận phòng và số khách, sau đó trả về `bookingId` nếu đặt thành công. Nếu người dùng hủy, flow kết thúc với outcome khác và không có mã đặt phòng.

Để bên gọi nhận được kết quả, flow cần một **hợp đồng output**. Trong Spring Web Flow, output attributes được khai báo bên trong từng `<end-state>`. ID của end-state xác định **outcome**, còn các thẻ `<output>` bên trong xác định **dữ liệu được trả về cho outcome đó**. Khi flow là top-level flow, kết quả có thể được xử lý bởi Spring MVC/`FlowHandler`; khi flow là subflow, flow cha nhận outcome như một event và đọc output attributes qua `currentEvent.attributes`.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt flow outcome với output attribute.
2. Khai báo `<output>` trong đúng `<end-state>`.
3. Hiểu cách output mặc định lấy giá trị từ flow scope theo tên attribute.
4. Dùng thuộc tính `value` để ánh xạ một biến nội bộ sang tên output công khai.
5. Thiết kế output khác nhau cho nhánh thành công, hủy và từ chối.
6. Nhận output của subflow qua `currentEvent.attributes`.
7. Xử lý kết quả top-level flow trong `FlowHandler` hoặc MVC flash scope.
8. Kiểm thử cả outcome lẫn dữ liệu output, bao gồm trường hợp không có output.

## 2. Flow có hợp đồng input/output

Một flow có thể được hình dung như một thao tác nhận dữ liệu và trả về kết quả:

```java
FlowOutcome bookingFlow(Map<String, Object> inputAttributes);

// FlowOutcome có hai phần khái niệm:
// - name: outcome, ví dụ "bookingConfirmed" hoặc "bookingCancelled"
// - outputAttributes: dữ liệu đi kèm outcome, ví dụ bookingId
```

Đây là mô hình tư duy để hiểu hợp đồng, không phải chữ ký Java mà ứng dụng cần tự triển khai. Trong XML, input được khai báo ở cấp flow bằng `<input>`; output được khai báo ở end-state bằng `<output>`.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Flow input | Dữ liệu bên gọi cung cấp khi khởi chạy | `hotelId = 42` |
| Flow state | Trạng thái nội bộ khi hành trình chạy | `booking`, `guestForm` |
| End-state ID | Tên kết quả khi flow kết thúc | `bookingConfirmed` |
| Output attribute | Dữ liệu công bố cho bên gọi ở outcome đó | `bookingId = 915` |

Ví dụ:

```text
Outcome: bookingConfirmed
Output:
  bookingId: 915
```

Hai giá trị này có ý nghĩa khác nhau. `bookingConfirmed` là tên nhánh kết thúc; `bookingId` là dữ liệu được xuất kèm nhánh đó. Một flow có thể có nhiều outcome, mỗi outcome có tập output attributes riêng.

## 3. Khai báo output ở end-state

Thẻ `<output>` nằm bên trong `<end-state>` mà nó thuộc về:

```xml
<end-state id="bookingConfirmed">
    <output name="bookingId" />
</end-state>
```

Khi flow đi tới `bookingConfirmed`, Web Flow tìm giá trị `bookingId` trong flow scope và đưa giá trị đó vào output attributes của outcome.

Ví dụ flow đã có:

```xml
<on-start>
    <evaluate expression="bookingService.createBooking(hotelId)"
              result="flowScope.booking" />
    <set name="flowScope.bookingId" value="booking.id" />
</on-start>

<end-state id="bookingConfirmed">
    <output name="bookingId" />
</end-state>
```

Vì output không chỉ rõ `value`, giá trị được lấy từ biến flow scope có cùng tên `bookingId`.

### 3.1. Khi nào cần thuộc tính value?

Thông thường object nội bộ có cấu trúc riêng, nhưng bên gọi chỉ cần một tên output ổn định. Khi đó, dùng `value` để chỉ rõ biểu thức nguồn:

```xml
<end-state id="bookingConfirmed">
    <output name="bookingId" value="booking.id" />
    <output name="confirmationNumber"
            value="booking.confirmationNumber" />
</end-state>
```

Trong ví dụ:

- `name="bookingId"` là tên output mà bên gọi nhìn thấy.
- `value="booking.id"` là biểu thức lấy giá trị từ object nội bộ.
- `name="confirmationNumber"` là một output khác, lấy từ thuộc tính `booking.confirmationNumber`.

Nhờ ánh xạ này, bên gọi không cần biết flow đang lưu object `booking` trong scope nào hoặc cấu trúc class nội bộ ra sao. Hợp đồng công khai có thể giữ ổn định trong khi flow thay đổi cách tổ chức dữ liệu bên trong.

### 3.2. Tên output không bắt buộc giống tên biến nội bộ

Ví dụ:

```xml
<end-state id="completed">
    <output name="resultId" value="flowScope.persistedRecord.id" />
</end-state>
```

Flow nội bộ dùng `persistedRecord.id`, nhưng bên gọi chỉ nhận `resultId`. Đây là một cách giảm phụ thuộc giữa caller và implementation.

### 3.3. Output phải được khai báo ở outcome phù hợp

Không khai báo output ở một end-state rồi giả định nó tự xuất hiện ở tất cả end-state khác:

```xml
<end-state id="bookingConfirmed">
    <output name="bookingId" value="booking.id" />
</end-state>

<end-state id="bookingCancelled" />
```

Ở `bookingConfirmed`, caller có thể nhận `bookingId`. Ở `bookingCancelled`, flow không công bố `bookingId`. Bên gọi phải dựa vào outcome để biết output nào được bảo đảm.

## 4. Phân biệt flow root và end-state

Tên bài nói về output của flow và end-state, nhưng cần hiểu chính xác vị trí khai báo: **output attributes được định nghĩa trong end-state đại diện cho từng flow outcome**, không phải một thẻ `<output>` độc lập đặt tùy ý ở cấp root `<flow>`.

Flow root xác định toàn bộ hợp đồng hành trình: input ở cấp flow và những outcome mà các end-state có thể trả về. Mỗi end-state xác định tập output gắn với outcome riêng của nó.

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <!-- Input của flow được khai báo ở cấp flow. -->
    <input name="hotelId" type="long" required="true" />

    <view-state id="reviewBooking">
        <transition on="confirm" to="bookingConfirmed" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <!-- Output chỉ xuất hiện trong outcome thành công. -->
    <end-state id="bookingConfirmed">
        <output name="bookingId" value="booking.id" />
    </end-state>

    <!-- Outcome hủy không hứa hẹn bookingId. -->
    <end-state id="bookingCancelled" />
</flow>
```

Đọc hợp đồng trên như sau:

| Cấp | Khai báo | Ý nghĩa |
| --- | --- | --- |
| Flow root | `<input name="hotelId"/>` | Flow cần hotelId để bắt đầu |
| End-state `bookingConfirmed` | `<output name="bookingId" .../>` | Khi thành công, trả bookingId |
| End-state `bookingCancelled` | Không có output | Khi hủy, chỉ trả outcome |

Không nên thêm một `<output>` ở root để “áp dụng chung” cho mọi outcome. Nếu hai end-state cần trả cùng một loại dữ liệu, hãy khai báo output ở từng end-state phù hợp hoặc thiết kế lại hợp đồng để mỗi nhánh có ý nghĩa rõ ràng.

## 5. Ví dụ đầy đủ: flow đặt phòng

Giả sử người dùng chọn khách sạn, nhập thông tin và xác nhận. Flow cần trả `bookingId` và `confirmationNumber` khi đặt phòng thành công; khi người dùng hủy, flow chỉ trả outcome `bookingCancelled`.

### 5.1. Flow definition

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="hotelId" type="long" required="true" />

    <on-start>
        <evaluate expression="bookingService.createBooking(hotelId, currentUser.name)"
                  result="flowScope.booking" />
    </on-start>

    <view-state id="enterBookingDetails" model="booking">
        <transition on="submit" to="reviewBooking" />
        <transition on="cancel" to="bookingCancelled"
                    bind="false" validate="false" />
    </view-state>

    <view-state id="reviewBooking">
        <transition on="confirm" to="confirmBooking" />
        <transition on="revise" to="enterBookingDetails" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <action-state id="confirmBooking">
        <evaluate expression="bookingService.confirm(booking)"
                  result="flowScope.confirmation" />
        <transition on="success" to="bookingConfirmed" />
    </action-state>

    <end-state id="bookingConfirmed">
        <output name="bookingId" value="confirmation.bookingId" />
        <output name="confirmationNumber"
                value="confirmation.confirmationNumber" />
    </end-state>

    <end-state id="bookingCancelled" />
</flow>
```

Ví dụ giả định `bookingService.createBooking` tạo một bản nháp trong flow scope và `bookingService.confirm` trả về object `confirmation` sau khi lưu thành công. Trong dự án thực tế, các bean, view và kiểu dữ liệu phải được ứng dụng cung cấp.

### 5.2. Hợp đồng của hai outcome

```text
bookingConfirmed:
  bookingId: Long
  confirmationNumber: String

bookingCancelled:
  (không có output attributes)
```

Bên gọi có thể xử lý thành công mà không cần đọc toàn bộ object `booking`. Khi hủy, caller không được giả định `bookingId` tồn tại trong output.

### 5.3. Vì sao output lấy từ confirmation thay vì booking?

`booking` là object bản nháp trong flow. `confirmation` là kết quả do service trả sau khi xác nhận thành công. Lấy output từ `confirmation` làm rõ rằng ID và số xác nhận đã được tạo sau thao tác lưu. Nếu dùng `booking.id` trước khi chắc chắn transaction hoàn tất, flow có thể công bố dữ liệu chưa phản ánh kết quả nghiệp vụ cuối cùng.

## 6. Kết quả của top-level flow

Khi flow được gọi trực tiếp qua Spring MVC, flow kết thúc bằng một `FlowExecutionOutcome`. Kết quả này bao gồm tên outcome và output attributes.

Một `FlowHandler` tùy chỉnh có thể đọc kết quả để điều hướng người dùng:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.webflow.execution.FlowExecutionOutcome;
import org.springframework.webflow.mvc.servlet.AbstractFlowHandler;

public class BookingFlowHandler extends AbstractFlowHandler {

    @Override
    public String handleExecutionOutcome(
            FlowExecutionOutcome outcome,
            HttpServletRequest request,
            HttpServletResponse response) {

        if ("bookingConfirmed".equals(outcome.getId())) {
            Object bookingId = outcome.getOutput().get("bookingId");
            return "contextRelative:/bookings/" + bookingId;
        }

        return "contextRelative:/hotels";
    }
}
```

Đây là ví dụ cho ứng dụng dùng Jakarta Servlet API; với ứng dụng cũ dùng `javax.servlet`, import sẽ khác. Bean `FlowHandler` phải được đăng ký với tên khớp flow ID mà nó xử lý.

### 6.1. Không nhầm outcome ID với output attribute

Trong handler:

- `outcome.getId()` trả về end-state ID, ví dụ `bookingConfirmed`.
- `outcome.getOutput().get("bookingId")` lấy output attribute tên `bookingId`.

Không viết:

```java
// Sai ý nghĩa: bookingId không phải outcome ID.
if ("bookingId".equals(outcome.getId())) {
    // ...
}
```

Nếu cần điều hướng theo kết quả nghiệp vụ, kiểm tra outcome trước, sau đó đọc những output mà end-state đó cam kết cung cấp.

### 6.2. Khi không có FlowHandler tùy chỉnh

Ứng dụng vẫn có thể để `FlowHandlerAdapter` xử lý outcome theo cấu hình mặc định hoặc redirect được khai báo trong flow. Tuy nhiên, nếu controller cần biết ID vừa tạo, phải có cách truyền output phù hợp; đừng cố đọc trực tiếp flow scope sau khi flow đã kết thúc vì scope đã được giải phóng cùng flow.

## 7. Chuyển output sang MVC flash scope

Khi end-state thực hiện internal redirect, Spring Web Flow có tùy chọn lưu output attributes vào **Spring MVC flash scope**. Tính năng này hữu ích khi flow kết thúc và chuyển sang một controller hiển thị trang tổng kết.

Ví dụ end-state:

```xml
<end-state id="finish" view="externalRedirect:summary">
    <output name="confirmationNumber"
            value="booking.confirmationNumber" />
</end-state>
```

Trong cấu hình `FlowHandlerAdapter`:

```xml
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor" />
    <property name="saveOutputToFlashScopeOnRedirect" value="true" />
</bean>
```

Khi bật `saveOutputToFlashScopeOnRedirect`, output có thể được dùng ở request tiếp theo theo cơ chế flash attribute của Spring MVC. Theo tài liệu Spring Web Flow, tùy chọn này **tắt mặc định để tương thích ngược**. Hãy kiểm tra phiên bản framework đang dùng và cấu hình rõ nếu ứng dụng cần hành vi này.

Không nhầm MVC flash scope với Web Flow `flashScope`:

| Cơ chế | Nơi thuộc về | Vòng đời |
| --- | --- | --- |
| Web Flow `flashScope` | Flow execution context | Được dọn sau mỗi lần render view |
| Spring MVC flash attributes | MVC redirect/request kế tiếp | Dành cho dữ liệu chuyển qua redirect |
| Flow output attributes | Kết quả của end-state | Được trả khi flow kết thúc |

Output attributes là dữ liệu kết quả của flow. Việc chuyển chúng vào MVC flash scope là một tích hợp bổ sung, không làm thay đổi hợp đồng end-state.

## 8. Output của subflow

Khi một flow được gọi như subflow, flow cha chờ flow con kết thúc. **End-state ID của flow con trở thành event** mà flow cha dùng để chọn transition tiếp theo. Nếu end-state con khai báo output, flow cha có thể đọc các giá trị đó trong transition thông qua `currentEvent.attributes`.

### 8.1. Flow con trả output

Ví dụ `create-guest-flow.xml`:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="bookingId" type="long" required="true" />

    <on-start>
        <evaluate expression="guestService.createForm(bookingId)"
                  result="flowScope.guestForm" />
    </on-start>

    <view-state id="enterGuest" model="guestForm">
        <transition on="save" to="saveGuest" />
        <transition on="cancel" to="guestCreationCancelled"
                    bind="false" validate="false" />
    </view-state>

    <action-state id="saveGuest">
        <evaluate expression="guestService.addGuest(bookingId, guestForm)"
                  result="flowScope.guest" />
        <transition on="success" to="guestCreated" />
    </action-state>

    <end-state id="guestCreated">
        <output name="guest" value="flowScope.guest" />
    </end-state>

    <end-state id="guestCreationCancelled" />
</flow>
```

Ở outcome `guestCreated`, flow con trả object `guest`. Ở outcome `guestCreationCancelled`, không có output `guest`.

### 8.2. Flow cha nhận output

Trong flow cha `booking`:

```xml
<subflow-state id="addGuest" subflow="create-guest">
    <input name="bookingId" value="flowScope.booking.id" />

    <transition on="guestCreated" to="reviewBooking">
        <evaluate expression="booking.guests.add(currentEvent.attributes.guest)" />
    </transition>

    <transition on="guestCreationCancelled" to="reviewBooking" />
</subflow-state>
```

Khi flow con kết thúc:

- Event ID là `guestCreated` hoặc `guestCreationCancelled`.
- Nếu event là `guestCreated`, output `guest` có thể đọc qua `currentEvent.attributes.guest`.
- Nếu event là `guestCreationCancelled`, không được đọc `currentEvent.attributes.guest` vì end-state hủy không khai báo output đó.

### 8.3. Outcome và output ở subflow không phải một thứ

| Flow con kết thúc | Event ở flow cha | Output attributes |
| --- | --- | --- |
| `guestCreated` | `guestCreated` | `guest` |
| `guestCreationCancelled` | `guestCreationCancelled` | Không có |

Flow cha điều hướng dựa trên **event ID**, rồi mới đọc **output attributes** nếu outcome đó cung cấp. Không dùng tên output làm giá trị `on` trừ khi end-state thực sự có cùng ID.

## 9. Thiết kế output khác nhau cho từng end-state

Một flow có thể kết thúc theo nhiều kết quả nghiệp vụ:

```xml
<end-state id="approved">
    <output name="requestId" value="flowScope.request.id" />
    <output name="approvedBy" value="currentUser.name" />
</end-state>

<end-state id="rejected">
    <output name="requestId" value="flowScope.request.id" />
    <output name="reasonCode" value="flowScope.rejection.reasonCode" />
</end-state>

<end-state id="cancelled" />
```

Hợp đồng kết quả:

| Outcome | Output được cam kết |
| --- | --- |
| `approved` | `requestId`, `approvedBy` |
| `rejected` | `requestId`, `reasonCode` |
| `cancelled` | Không có output |

Thiết kế này cho phép caller xử lý rõ ràng:

- `approved`: ghi nhận người phê duyệt và chuyển đến màn hình kết quả.
- `rejected`: hiển thị lý do từ chối.
- `cancelled`: quay lại màn hình trước đó mà không xử lý dữ liệu kết quả.

### 9.1. Có nên trả cùng một output ở mọi outcome?

Chỉ nên trả một output ở nhiều end-state nếu giá trị đó có ý nghĩa và tồn tại trong mọi nhánh. Ví dụ `requestId` có thể xuất hiện ở cả `approved` và `rejected` vì hai nhánh đều thao tác trên cùng yêu cầu. Nhưng `approvedBy` không nên xuất hiện ở nhánh `cancelled` nếu chưa có ai phê duyệt.

Nếu caller cần một dữ liệu chung, hãy khai báo output ở từng end-state có bảo đảm cung cấp nó. Không dựa vào giả định rằng flow scope còn tồn tại sau khi kết thúc.

### 9.2. Output null và output không tồn tại

Có khác biệt giữa:

- Output attribute được khai báo nhưng biểu thức nguồn cho kết quả `null`.
- Output attribute không được khai báo trong end-state.

Ở trường hợp đầu, caller có tên attribute trong hợp đồng nhưng giá trị có thể null. Ở trường hợp sau, caller không được giả định attribute có mặt. Thiết kế tốt nên tránh xuất null nếu caller không cần, hoặc quy định rõ ý nghĩa của null.

## 10. Quy tắc đặt tên output

Output name là một phần API của flow. Nếu nhiều flow khác nhau gọi cùng một subflow, tên output ổn định giúp các caller không phải biết cách triển khai nội bộ.

Nên:

1. Đặt tên theo ý nghĩa nghiệp vụ, ví dụ `bookingId`, `guest`, `verifiedContactId`.
2. Giữ kiểu dữ liệu ổn định giữa các phiên bản của flow.
3. Dùng tên output nhất quán giữa những outcome có cùng ngữ nghĩa.
4. Chỉ xuất dữ liệu caller thực sự cần.
5. Không xuất toàn bộ flow scope hoặc object chứa dữ liệu nhạy cảm.
6. Tài liệu hóa output nào có mặt ở từng end-state.

Tránh tên chung chung như `result`, `data` hoặc `value` nếu caller cần phân biệt nhiều loại dữ liệu. Cũng tránh để output name phụ thuộc vào tên field nội bộ nếu field đó có thể đổi trong tương lai.

## 11. Output và scope: dữ liệu nguồn cần tồn tại khi flow kết thúc

Khi Web Flow đi tới end-state, nó đánh giá biểu thức `value` để tạo output attributes. Vì vậy, nguồn dữ liệu phải tồn tại và có thể truy cập tại thời điểm kết thúc.

Ví dụ:

```xml
<end-state id="completed">
    <output name="orderId" value="flowScope.order.id" />
</end-state>
```

Để biểu thức hoạt động:

- `flowScope.order` phải được khởi tạo trước khi vào end-state.
- `order.id` phải có giá trị theo hợp đồng nghiệp vụ.
- Service lưu đơn hàng phải hoàn tất thành công trước khi flow kết thúc `completed`.

Nếu biến nguồn nằm trong `viewScope` của một state đã rời, không nên dựa vào nó khi end-state ở state khác. Dữ liệu cần xuất thường nên được giữ ở flow scope hoặc được đọc từ một service đáng tin cậy tại thời điểm thích hợp.

### 11.1. Không dùng output thay cho lưu trữ bền vững

Output chỉ là dữ liệu kết quả được trả cho caller. Nó không tự lưu dữ liệu vào database, không thay thế transaction và cũng không phải cơ chế giữ trạng thái qua nhiều ngày. Nếu caller cần truy vấn lại đơn hàng sau khi flow kết thúc, output nên trả ID; dữ liệu đầy đủ được đọc từ service/database.

### 11.2. Chỉ xuất DTO/ID cần thiết

Ví dụ:

```xml
<end-state id="completed">
    <output name="orderId" value="flowScope.order.id" />
    <output name="status" value="flowScope.order.status" />
</end-state>
```

Không nên trả trực tiếp entity có quan hệ lazy, persistence context hoặc dữ liệu nhạy cảm sang flow cha/MVC nếu caller chỉ cần ID. Một DTO nhỏ giúp giảm phụ thuộc và rủi ro serialization.

## 12. Những lỗi thường gặp khi khai báo output

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Caller không nhận được `bookingId` | End-state chưa khai báo output | Thêm `<output>` trong end-state thành công |
| Output null | Biến nguồn chưa được gán hoặc biểu thức `value` sai | Kiểm tra service result và expression |
| Output lấy nhầm biến | Bỏ `value` trong khi biến cùng tên không chứa dữ liệu mong muốn | Khai báo `value` tường minh |
| Hủy flow nhưng caller vẫn đọc `bookingId` | Caller giả định output của success có ở mọi outcome | Rẽ nhánh theo outcome trước khi đọc output |
| Flow cha không thấy `guest` | End-state con không khai báo output `guest` | Thêm output ở đúng end-state con |
| Transition cha không chạy | `on` không khớp ID end-state con | Kiểm tra outcome name của flow con |
| FlowHandler redirect sai | Dùng output name thay cho outcome ID hoặc ngược lại | So sánh `outcome.getId()`, sau đó đọc output map |
| MVC controller không thấy flash attribute | Chưa bật `saveOutputToFlashScopeOnRedirect` hoặc redirect không thuộc trường hợp hỗ trợ | Kiểm tra FlowHandlerAdapter và kiểu redirect |
| Output chứa object quá lớn | Trả toàn bộ entity/flow model | Chỉ xuất ID hoặc DTO nhỏ |
| Thay đổi tên output làm caller lỗi | Đã phá hợp đồng công khai | Cập nhật caller/test đồng bộ hoặc giữ alias ổn định |

### 12.1. Sai vị trí khai báo

Không đặt `<output>` trực tiếp dưới root flow:

```xml
<!-- Sai cấu trúc ý nghĩa: output thuộc một end-state cụ thể. -->
<flow xmlns="http://www.springframework.org/schema/webflow">
    <output name="bookingId" value="booking.id" />
</flow>
```

Đặt vào end-state:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <end-state id="bookingConfirmed">
        <output name="bookingId" value="booking.id" />
    </end-state>
</flow>
```

### 12.2. Nhầm end-state ID với output name

Sai:

```xml
<end-state id="bookingConfirmed">
    <output name="bookingConfirmed" value="booking.id" />
</end-state>
```

Đoạn này hợp lệ về mặt ý tưởng nếu thật sự muốn một output attribute trùng tên outcome, nhưng thường gây nhầm lẫn. Rõ ràng hơn:

```xml
<end-state id="bookingConfirmed">
    <output name="bookingId" value="booking.id" />
</end-state>
```

Caller dùng `bookingConfirmed` để nhận diện outcome và `bookingId` để lấy ID.

## 13. Thay đổi hợp đồng output an toàn

Flow có thể được nhiều caller sử dụng: controller, flow cha hoặc một integration test. Đổi output name vì vậy là thay đổi API.

Ví dụ phiên bản đầu:

```xml
<end-state id="confirmed">
    <output name="bookingId" value="booking.id" />
</end-state>
```

Phiên bản sau muốn đổi thành `reservationId`. Nếu caller cũ vẫn đọc `bookingId`, dữ liệu sẽ không còn được tìm thấy.

Một cách chuyển tiếp có thể xuất cả hai tên trong một giai đoạn:

```xml
<end-state id="confirmed">
    <output name="bookingId" value="booking.id" />
    <output name="reservationId" value="booking.id" />
</end-state>
```

Sau khi các caller đã chuyển sang `reservationId`, có thể bỏ alias cũ ở một thay đổi có kiểm soát. Chỉ làm vậy khi tất cả caller đã được xác nhận và test.

## 14. Kiểm thử output theo từng outcome

Một test chỉ kiểm tra flow đã kết thúc chưa là chưa đủ. Cần kiểm tra cả:

- End-state ID thực tế.
- Tên output attributes.
- Giá trị và kiểu của từng output.
- Những output không được xuất ở nhánh hủy/từ chối.

### 14.1. Ma trận kiểm thử

| Ca kiểm thử | Outcome | Output kỳ vọng |
| --- | --- | --- |
| Xác nhận đặt phòng thành công | `bookingConfirmed` | `bookingId` và `confirmationNumber` |
| Người dùng hủy trước khi xác nhận | `bookingCancelled` | Không có output bắt buộc |
| Tạo guest thành công trong subflow | `guestCreated` | `guest` |
| Hủy tạo guest | `guestCreationCancelled` | Không có `guest` |
| Phê duyệt yêu cầu | `approved` | `requestId`, `approvedBy` |
| Từ chối yêu cầu | `rejected` | `requestId`, `reasonCode` |
| Biểu thức output sai | Outcome thành công | Test phát hiện output thiếu/null hoặc flow lỗi |
| FlowHandler nhận kết quả | `bookingConfirmed` | Redirect dùng đúng `bookingId` |

### 14.2. Khung kiểm thử flow

Spring Web Flow cung cấp `AbstractXmlFlowExecutionTests` và các assertion để bắt đầu flow, phát event và kiểm tra outcome. Đoạn dưới đây minh họa ý tưởng; test cần nạp flow XML, mock service và chuẩn bị dữ liệu:

```java
public class BookingFlowTests extends AbstractXmlFlowExecutionTests {

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createFileResource(
                "src/main/webapp/WEB-INF/flows/booking/booking-flow.xml");
    }

    @Override
    protected void configureFlowBuilderContext(
            MockFlowBuilderContext builderContext) {
        builderContext.registerBean("bookingService", new StubBookingService());
    }

    public void testBookingConfirmedReturnsBookingId() {
        MutableAttributeMap input = new LocalAttributeMap();
        input.put("hotelId", 42L);

        MockExternalContext context = new MockExternalContext();
        context.setCurrentUser("booking-user");
        startFlow(input, context);
        assertCurrentStateEquals("enterBookingDetails");

        context = new MockExternalContext();
        context.setEventId("submit");
        resumeFlow(context);
        assertCurrentStateEquals("reviewBooking");

        context = new MockExternalContext();
        context.setEventId("confirm");
        resumeFlow(context);
        assertFlowExecutionEnded();
        assertFlowExecutionOutcomeEquals("bookingConfirmed");

        FlowExecutionOutcome outcome = getFlowExecutionOutcome();
        assertEquals(Long.valueOf(915L),
                outcome.getOutput().get("bookingId"));
    }
}
```

Với bộ test XML của Spring Web Flow 3.0.1, `getFlowExecutionOutcome()` trả kết quả đã kết thúc; `getOutput()` trả map output attributes. Assertion cần kiểm tra đúng giá trị, ví dụ `bookingId == 915L`, chứ không chỉ kiểm tra `bookingConfirmed`.

### 14.3. Test caller của subflow

Kiểm thử flow cha gọi subflow nên có ít nhất hai trường hợp:

1. Subflow trả `guestCreated` với output `guest`; flow cha đọc `currentEvent.attributes.guest` và thêm guest vào booking.
2. Subflow trả `guestCreationCancelled` không có output; flow cha quay lại màn hình review và không cố đọc `guest`.

Test thứ hai giúp phát hiện lỗi giả định output luôn tồn tại dù outcome là hủy.

## 15. Bài tập thực hành

Thiết kế flow `document-submission` có các bước:

1. Nhận `applicationId` khi bắt đầu.
2. Người dùng kiểm tra tài liệu và xác nhận gửi.
3. Service lưu hồ sơ và trả `submissionReceipt` gồm `receiptId`, `submittedAt` và `status`.
4. Flow có ba outcome: `submitted`, `returnedForCorrection` và `cancelled`.

Yêu cầu:

- `submitted` xuất `receiptId` và `submittedAt`.
- `returnedForCorrection` xuất `applicationId` và `reasonCode`.
- `cancelled` không xuất output.
- Viết một `FlowHandler` điều hướng `submitted` tới trang chi tiết biên nhận.
- Viết một flow cha gọi `document-submission` như subflow; flow cha đọc `receiptId` qua `currentEvent.attributes`.
- Kiểm thử ba outcome và bảo đảm nhánh hủy không đọc `receiptId`.

**Câu hỏi tự kiểm tra:**

- Vì sao `<output>` được đặt bên trong end-state thay vì khai báo chung dưới root flow?
- Nếu `name="receiptId"` không có `value`, Web Flow tìm giá trị ở đâu?
- Khi flow con kết thúc `submitted`, event ở flow cha là `submitted` hay `receiptId`?
- Nếu top-level flow kết thúc, vì sao không nên cố đọc lại `flowScope` từ request sau?
- Khi đổi tên output, những caller nào cần được cập nhật?

## 16. Checklist trước khi công bố flow output

- [ ] Mỗi end-state có outcome ID có ý nghĩa nghiệp vụ.
- [ ] Output chỉ được khai báo ở end-state cần trả dữ liệu.
- [ ] `name` ổn định và phản ánh hợp đồng công khai.
- [ ] `value` trỏ tới dữ liệu đã tồn tại và có giá trị tại thời điểm kết thúc.
- [ ] Nếu bỏ `value`, biến flow scope cùng tên đã được gán đúng.
- [ ] Nhánh hủy/từ chối không xuất dữ liệu thành công nếu không có ý nghĩa.
- [ ] Caller kiểm tra outcome trước khi đọc output attributes.
- [ ] Subflow caller dùng `currentEvent.attributes` đúng tên output.
- [ ] FlowHandler/MVC redirect đọc đúng output của top-level flow.
- [ ] Không trả entity lớn, secret hoặc dữ liệu nhạy cảm.
- [ ] Test kiểm tra cả outcome và giá trị output của từng nhánh.

## 17. Ghi nhớ

- Flow có hợp đồng input/output; input được khai báo ở flow, output attributes được khai báo trong từng `<end-state>`.
- End-state ID là **outcome name**; `<output name="...">` là **tên dữ liệu được trả về**.
- Nếu `<output>` không có `value`, Web Flow lấy giá trị từ flow scope theo tên output; nếu có `value`, biểu thức chỉ rõ nguồn dữ liệu.
- Output của từng end-state khác nhau. Caller phải kiểm tra outcome trước khi giả định một output tồn tại.
- Khi flow là subflow, end-state ID trở thành event ở flow cha; output được đọc qua `currentEvent.attributes.<outputName>`.
- Với top-level flow, `FlowHandler` có thể đọc outcome và output để redirect; MVC flash scope có thể nhận output khi bật `saveOutputToFlashScopeOnRedirect` cho trường hợp redirect phù hợp.
- Output là kết quả giao tiếp, không phải nơi lưu trữ bền vững hay transaction. Thường chỉ xuất ID/DTO nhỏ để caller đọc lại dữ liệu qua service.
- Đổi output name là thay đổi hợp đồng; cập nhật caller và test đồng bộ.

### Tài liệu tham khảo

- [Spring Web Flow 3.0.x Reference Guide — Input/Output Mapping](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#_inputoutput_mapping)
- [Spring Web Flow 3.0.x Reference Guide — Mapping Sub-flow Output](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#_mapping_sub_flow_output)
- [Spring Web Flow 3.0.1 Reference Guide — Saving Flow Output to MVC Flash Scope](https://docs.spring.io/spring-webflow/docs/3.0.1/reference/#_saving_flow_output_to_mvc_flash_scope)
- [FlowExecutionOutcome Javadoc — Spring Web Flow 3.0.1](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/execution/FlowExecutionOutcome.html)
- [FlowHandler Javadoc — Spring Web Flow 3.0.1](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/mvc/servlet/FlowHandler.html)
