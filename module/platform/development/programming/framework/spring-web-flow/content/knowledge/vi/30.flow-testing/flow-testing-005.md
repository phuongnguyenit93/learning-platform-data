# MockExternalContext cho input, sự kiện và người dùng trong Spring Web Flow

Một flow đặt phòng khách sạn có thể nhận `hotelId` khi khởi chạy, đọc thông tin người dùng hiện tại để tạo bản nháp, nhận event `proceed` khi người dùng hoàn tất form và nhận event `confirm` ở bước cuối. Khi kiểm thử, ta cần mô phỏng đúng **ngữ cảnh bên ngoài** của từng request: dữ liệu khởi chạy, tham số request, event ID, người dùng và đôi khi cả locale hoặc session.

Spring Web Flow (SWF) cung cấp `MockExternalContext` để làm việc đó trong flow execution test. Đây là implementation giả của `ExternalContext`, cho phép bài test thiết lập những thông tin mà flow nhìn thấy khi bắt đầu hoặc tiếp tục một execution. Bài thuộc chương **Kiểm thử flow** của module `SPRING_WEB_FLOW`, tập trung vào ba nhóm dữ liệu quan trọng: **input của flow**, **sự kiện và request parameters**, và **người dùng hiện tại**.

Điểm cần phân biệt ngay từ đầu: input của flow được truyền qua đối số riêng của `startFlow(input, context)`; request parameters được đưa vào `MockExternalContext`; event được mô phỏng bằng `setEventId(...)` khi tiếp tục flow; principal được cung cấp bằng `setCurrentUser(...)`. Bốn thứ này có liên quan nhưng không thay thế nhau.

## 1. MockExternalContext đại diện cho điều gì?

`ExternalContext` là giao diện trừu tượng hóa môi trường bên ngoài đã gọi vào Web Flow. Trong ứng dụng web, môi trường đó thường là request/session của servlet; trong kiểm thử flow, ta không cần dựng servlet container để cung cấp các giá trị cơ bản. `MockExternalContext` cho phép tạo một ngữ cảnh có thể điều khiển được.

~~~java
import org.springframework.webflow.test.MockExternalContext;

MockExternalContext context = new MockExternalContext();
context.setCurrentUser("minh");
context.putRequestParameter("campaign", "summer");
context.setEventId("submit");
~~~

Đoạn trên tạo một context kiểm thử, đặt principal tên `minh`, thêm request parameter `campaign` và chọn event ID `submit`. Nó chưa khởi chạy flow; context chỉ được truyền cho thao tác bắt đầu hoặc tiếp tục execution.

| Thành phần | API của MockExternalContext | Flow có thể đọc qua |
|---|---|---|
| Flow input | Không đặt trực tiếp ở đây; truyền riêng cho `startFlow(input, context)` | Input được khai báo trong flow, được lưu vào flow scope |
| Request parameter | `putRequestParameter(name, value)` | `requestParameters.name` |
| Event ID | `setEventId(id)` | Transition `on="id"` và `currentEvent.id` |
| Người dùng | `setCurrentUser(String/Principal)` | `currentUser` |
| Locale | `setLocale(locale)` | `externalContext.locale` hoặc context phù hợp |
| Context path | `setContextPath(path)` | `externalContext.contextPath` |
| Request/session attributes | `setRequestMap(...)`, `setSessionMap(...)` | `externalContext.requestMap`, `externalContext.sessionMap` |

`MockExternalContext` không thay thế `FlowExecutor` hoặc flow execution. Nó cũng không tự kiểm tra mọi transition; bài test vẫn phải khởi chạy flow, gửi event và assert state/outcome.

## 2. Phân biệt flow input với request parameter

Đây là điểm dễ nhầm nhất khi viết test. **Flow input** là dữ liệu đầu vào theo hợp đồng của flow, được truyền khi bắt đầu execution. **Request parameter** là dữ liệu thuộc một request cụ thể, thường do form hoặc URL gửi lên.

### 2.1. Flow input được truyền qua startFlow

Giả sử flow khai báo:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="hotelId" type="long" required="true" />

    <on-start>
        <evaluate expression="bookingService.createBooking(hotelId, currentUser.name)"
                  result="flowScope.booking" />
    </on-start>

    <view-state id="enterBookingDetails" view="booking/details">
        <transition on="proceed" to="reviewBooking" />
    </view-state>

    <view-state id="reviewBooking" view="booking/review">
        <transition on="confirm" to="bookingConfirmed" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <end-state id="bookingConfirmed" />
    <end-state id="bookingCancelled" />
</flow>
~~~

`<input name="hotelId" .../>` định nghĩa một input attribute của flow. SWF đưa giá trị input vào flow scope theo tên `hotelId`. Vì vậy biểu thức `bookingService.createBooking(hotelId, currentUser.name)` có thể đọc input này khi flow khởi chạy.

Trong test, tạo input map và truyền riêng:

~~~java
import org.springframework.webflow.core.collection.LocalAttributeMap;
import org.springframework.webflow.core.collection.MutableAttributeMap;
import org.springframework.webflow.test.MockExternalContext;

MutableAttributeMap<Object> input = new LocalAttributeMap<>();
input.put("hotelId", 42L);

MockExternalContext context = new MockExternalContext();
context.setCurrentUser("minh");

startFlow(input, context);
~~~

`startFlow(input, context)` là helper của lớp test flow. Nó chuyển input map vào flow execution và dùng context làm môi trường của request khởi chạy.

### 2.2. Request parameter được đặt trên context

Nếu flow cần đọc tham số của request hiện tại, dùng `putRequestParameter`:

~~~java
MockExternalContext context = new MockExternalContext();
context.putRequestParameter("campaign", "summer");
context.putRequestParameter("page", "2");
~~~

Flow có thể đọc các giá trị đó qua `requestParameters`:

~~~xml
<on-start>
    <evaluate expression="bookingService.createBooking(
                              hotelId,
                              requestParameters.campaign)"
              result="flowScope.booking" />
</on-start>
~~~

Đoạn expression chỉ minh họa cách đọc parameter; cần bảo đảm method service và input contract trong ứng dụng khớp nhau.

### 2.3. Hai loại dữ liệu không tự động thay thế nhau

Bảng sau tóm tắt sự khác biệt:

| Cách thiết lập trong test | Flow nhận ở đâu? | Vòng đời / ý nghĩa |
|---|---|---|
| `input.put("hotelId", 42L)` rồi `startFlow(input, context)` | Input attribute, sau đó có trong flow scope | Dữ liệu khởi chạy theo hợp đồng flow |
| `context.putRequestParameter("campaign", "summer")` | `requestParameters.campaign` | Dữ liệu của request cụ thể |
| `context.setEventId("proceed")` | Event đang được gửi khi resume | Tín hiệu chuyển state |
| `context.setCurrentUser("minh")` | `currentUser` | Principal của request hiện tại |

Đặt `hotelId` vào request parameter không tự động thỏa mãn `<input name="hotelId" required="true"/>` nếu bài test không truyền input map tương ứng hoặc flow không có mapping rõ ràng từ request parameter sang input. Ngược lại, flow input không đại diện cho mọi field của form ở các request tiếp theo.

**Quy tắc thực hành:** input của flow dùng `startFlow(input, context)`; dữ liệu request dùng `putRequestParameter`; event dùng `setEventId`; principal dùng `setCurrentUser`.

## 3. Mô phỏng event và tiếp tục flow

Một `view-state` đợi event từ người dùng. Trong kiểm thử XML flow, `MockExternalContext.setEventId(...)` đặt ID của event sẽ được gửi khi flow tiếp tục. Sau đó gọi `resumeFlow(context)`.

~~~java
MockExternalContext context = new MockExternalContext();
context.setEventId("proceed");

resumeFlow(context);

assertCurrentStateEquals("reviewBooking");
~~~

Trong ví dụ, test giả lập người dùng nhấn nút phát event `proceed` ở state hiện tại. Transition `on="proceed"` được chọn nếu state đó có khai báo transition phù hợp.

### 3.1. Event ID không phải request parameter tùy ý

Có thể nhìn thấy HTML form gửi một field như `_eventId_proceed`. Khi chạy qua Web Flow MVC, hạ tầng view/handler đọc field đó và biến thành event ID. Trong flow test, ta thường bỏ qua việc parse HTML và đặt event trực tiếp bằng `setEventId("proceed")`.

`setEventId` không có nghĩa là thêm request parameter tên `eventId`. Nó cấu hình event cho MockExternalContext. Nếu cần kiểm tra một request parameter khác, phải gọi thêm `putRequestParameter`.

~~~java
MockExternalContext context = new MockExternalContext();
context.setEventId("proceed");
context.putRequestParameter("sort", "price");
context.putRequestParameter("direction", "asc");

resumeFlow(context);
~~~

Flow có thể xử lý event `proceed` và đọc `requestParameters.sort`, `requestParameters.direction` trong transition/action phù hợp.

### 3.2. Event phải hợp lệ với state hiện tại

Nếu flow đang ở `enterBookingDetails` và chỉ có transition `proceed`, gửi event `confirm` không tự đưa flow tới `bookingConfirmed`. Event được xử lý trong ngữ cảnh state hiện tại; nếu không có transition phù hợp, flow có thể giữ nguyên state hoặc xử lý theo cấu hình transition toàn cục.

Test nên assert state trước khi gửi event để tránh kiểm tra nhầm:

~~~java
assertCurrentStateEquals("enterBookingDetails");

MockExternalContext context = new MockExternalContext();
context.setEventId("proceed");
resumeFlow(context);

assertCurrentStateEquals("reviewBooking");
~~~

Không dùng một event ID đúng tên nhưng gửi ở sai state rồi kết luận transition đã được kiểm tra.

### 3.3. Vì sao dùng resumeFlow thay vì tạo flow mới?

`startFlow(...)` khởi chạy một flow execution mới. `resumeFlow(...)` tiếp tục execution đã được test harness tạo trước đó. Mỗi lần người dùng gửi event tiếp theo, bài test tạo một external context mới cho request đó rồi gọi `resumeFlow(context)`.

~~~java
MockExternalContext startContext = new MockExternalContext();
startContext.setCurrentUser("minh");
startFlow(input, startContext);

MockExternalContext proceedContext = new MockExternalContext();
proceedContext.setCurrentUser("minh");
proceedContext.setEventId("proceed");
resumeFlow(proceedContext);

MockExternalContext confirmContext = new MockExternalContext();
confirmContext.setCurrentUser("minh");
confirmContext.setEventId("confirm");
resumeFlow(confirmContext);
~~~

Việc tạo context mới cho mỗi request giúp test mô phỏng đúng dữ liệu có thể thay đổi theo từng lần gọi. Nếu một transition cần principal, locale hoặc request parameter ở request tiếp theo, hãy đặt chúng trên context mới đó.

## 4. Thiết lập người dùng hiện tại bằng setCurrentUser

`currentUser` là biến EL đặc biệt đại diện cho authenticated `Principal` trong external context. `MockExternalContext` có hai overload hữu ích:

- `setCurrentUser(String userName)`: cách viết gọn, tạo principal từ tên người dùng.
- `setCurrentUser(Principal principal)`: cung cấp một principal do test tự tạo.

Ví dụ đơn giản:

~~~java
MockExternalContext context = new MockExternalContext();
context.setCurrentUser("minh");
startFlow(input, context);
~~~

Flow có thể đọc:

~~~xml
<on-start>
    <evaluate expression="bookingService.createBooking(hotelId, currentUser.name)"
              result="flowScope.booking" />
</on-start>
~~~

Trong SpEL, `currentUser.name` lấy tên principal. Nếu flow không có người dùng hiện tại, `currentUser` có thể null; biểu thức truy cập `currentUser.name` khi đó không an toàn nếu không có tiền điều kiện hoặc chính sách xử lý tương ứng.

### 4.1. Dùng Principal tùy chỉnh

Nếu logic cần kiểm tra thêm thuộc tính trên principal, test có thể truyền một implementation của `java.security.Principal`:

~~~java
import java.security.Principal;

Principal user = new Principal() {
    @Override
    public String getName() {
        return "minh";
    }
};

MockExternalContext context = new MockExternalContext();
context.setCurrentUser(user);
~~~

Tuy nhiên, `Principal` chỉ cung cấp danh tính theo hợp đồng Java. Việc thêm role hoặc authority vào một object Principal tùy chỉnh không tự động làm cho Spring Security method security hay filter chain công nhận các quyền đó.

### 4.2. Đặt user trên từng request cần kiểm tra

Một flow execution có thể đi qua nhiều request. Nếu action ở bước xác nhận đọc `currentUser`, context dùng để resume bước xác nhận cũng cần principal:

~~~java
MockExternalContext confirmContext = new MockExternalContext();
confirmContext.setCurrentUser("minh");
confirmContext.setEventId("confirm");
resumeFlow(confirmContext);
~~~

Không nên chỉ đặt user ở context khởi chạy rồi giả định mọi external context được tạo về sau đều tự mang principal đó. Hãy thiết lập principal ở mỗi request test có logic phụ thuộc vào người dùng.

### 4.3. setCurrentUser không thay thế Spring Security

Đây là ranh giới quan trọng:

- `setCurrentUser` cung cấp principal cho `ExternalContext` và biến `currentUser` trong flow expression.
- Nó **không** chạy `SecurityFilterChain`, không tạo một HTTP authentication session thật, không kiểm tra password và không tự kiểm thử `@PreAuthorize`.
- Muốn kiểm tra authorization ở service, hãy test service/method security với security context phù hợp.
- Muốn kiểm tra filter chain, login, CSRF và HTTP status, hãy bổ sung Spring Security Test/MockMvc integration test.

Flow execution test với MockExternalContext trả lời câu hỏi “flow nhận principal nào trong request này?”; nó không tự trả lời câu hỏi “người đó có đăng nhập thành công qua web application hay không?”.

## 5. Ví dụ hoàn chỉnh: booking flow nhận input, request parameter, event và user

Giả sử flow `booking` nhận `hotelId` khi khởi chạy, dùng người dùng hiện tại để tạo bản nháp, đọc `campaign` từ request ở bước đầu, và xử lý event `proceed` rồi `confirm`.

### 5.1. Flow XML

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="hotelId" type="long" required="true" />

    <on-start>
        <evaluate expression="bookingService.createBooking(
                                  hotelId,
                                  currentUser.name)"
                  result="flowScope.booking" />
    </on-start>

    <view-state id="enterBookingDetails"
                view="booking/details">
        <transition on="proceed" to="reviewBooking">
            <set name="flowScope.campaign"
                 value="requestParameters.campaign" />
            <set name="flowScope.lastActor"
                 value="currentUser.name" />
        </transition>
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <view-state id="reviewBooking"
                view="booking/review">
        <transition on="confirm" to="bookingConfirmed">
            <evaluate expression="bookingService.confirm(
                                      flowScope.booking,
                                      currentUser.name)" />
        </transition>
        <transition on="back" to="enterBookingDetails" />
        <transition on="cancel" to="bookingCancelled" />
    </view-state>

    <end-state id="bookingConfirmed" />
    <end-state id="bookingCancelled" />
</flow>
~~~

Flow có bốn nguồn dữ liệu:

1. `hotelId` đến từ input map lúc khởi chạy.
2. `currentUser.name` lấy tên principal từ external context.
3. `requestParameters.campaign` đọc request parameter tại request phát event `proceed`.
4. `currentEvent.id` (nếu cần) cho biết event hiện tại; trong ví dụ, các transition đã khai báo ID trực tiếp qua `on`.

`bookingService` là bean nghiệp vụ do ứng dụng cung cấp. Nó phải kiểm tra quyền đặt phòng và điều kiện dữ liệu theo logic thực tế; flow test sẽ thay bean này bằng fake để không truy cập hệ thống thật.

### 5.2. Fake service ghi nhận dữ liệu nhận được

~~~java
package com.example.booking;

public class FakeBookingService {

    private Long lastHotelId;
    private String lastUserName;
    private String confirmedBy;
    private int createCount;
    private int confirmCount;

    public Booking createBooking(Long hotelId, String userName) {
        this.lastHotelId = hotelId;
        this.lastUserName = userName;
        this.createCount++;
        return new Booking(hotelId, userName);
    }

    public void confirm(Booking booking, String userName) {
        this.confirmedBy = userName;
        this.confirmCount++;
    }

    public Long getLastHotelId() {
        return lastHotelId;
    }

    public String getLastUserName() {
        return lastUserName;
    }

    public String getConfirmedBy() {
        return confirmedBy;
    }

    public int getCreateCount() {
        return createCount;
    }

    public int getConfirmCount() {
        return confirmCount;
    }
}
~~~

`Booking` là DTO minh họa cần được định nghĩa trong test hoặc dùng kiểu model của ứng dụng. Fake chỉ ghi nhận tham số và trả object đơn giản; nó không ghi database, gửi email hay gọi API.

### 5.3. Flow execution test

~~~java
package com.example.booking;

import org.springframework.webflow.core.collection.LocalAttributeMap;
import org.springframework.webflow.core.collection.MutableAttributeMap;
import org.springframework.webflow.engine.builder.FlowDefinitionResource;
import org.springframework.webflow.engine.builder.FlowDefinitionResourceFactory;
import org.springframework.webflow.test.MockExternalContext;
import org.springframework.webflow.test.MockFlowBuilderContext;
import org.springframework.webflow.test.execution.AbstractXmlFlowExecutionTests;

public class BookingFlowExecutionTests
        extends AbstractXmlFlowExecutionTests {

    private final FakeBookingService bookingService =
        new FakeBookingService();

    @Override
    protected FlowDefinitionResource getResource(
            FlowDefinitionResourceFactory resourceFactory) {
        return resourceFactory.createClassPathResource(
            "flows/booking/booking-flow.xml", getClass());
    }

    @Override
    protected void configureFlowBuilderContext(
            MockFlowBuilderContext builderContext) {
        builderContext.registerBean("bookingService", bookingService);
    }

    public void testStartFlowReceivesInputAndCurrentUser() {
        MutableAttributeMap<Object> input = new LocalAttributeMap<>();
        input.put("hotelId", 42L);

        MockExternalContext context = new MockExternalContext();
        context.setCurrentUser("minh");

        startFlow(input, context);

        assertCurrentStateEquals("enterBookingDetails");
        assertEquals(Long.valueOf(42L), bookingService.getLastHotelId());
        assertEquals("minh", bookingService.getLastUserName());
        assertEquals(1, bookingService.getCreateCount());
    }

    public void testProceedReadsRequestParameterAndCurrentUser() {
        MutableAttributeMap<Object> input = new LocalAttributeMap<>();
        input.put("hotelId", 42L);

        MockExternalContext startContext = new MockExternalContext();
        startContext.setCurrentUser("minh");
        startFlow(input, startContext);

        MockExternalContext proceedContext = new MockExternalContext();
        proceedContext.setCurrentUser("minh");
        proceedContext.setEventId("proceed");
        proceedContext.putRequestParameter("campaign", "summer");

        resumeFlow(proceedContext);

        assertCurrentStateEquals("reviewBooking");
        assertEquals("summer", getRequiredFlowAttribute("campaign"));
        assertEquals("minh", getRequiredFlowAttribute("lastActor"));
    }

    public void testConfirmUsesUserFromConfirmationRequest() {
        MutableAttributeMap<Object> input = new LocalAttributeMap<>();
        input.put("hotelId", 42L);

        MockExternalContext startContext = new MockExternalContext();
        startContext.setCurrentUser("minh");
        startFlow(input, startContext);

        MockExternalContext proceedContext = new MockExternalContext();
        proceedContext.setCurrentUser("minh");
        proceedContext.setEventId("proceed");
        resumeFlow(proceedContext);

        MockExternalContext confirmContext = new MockExternalContext();
        confirmContext.setCurrentUser("minh");
        confirmContext.setEventId("confirm");
        resumeFlow(confirmContext);

        assertFlowExecutionEnded();
        assertFlowExecutionOutcomeEquals("bookingConfirmed");
        assertEquals("minh", bookingService.getConfirmedBy());
        assertEquals(1, bookingService.getConfirmCount());
    }
}
~~~

Ví dụ sử dụng test support của Spring Web Flow 2.x, trong đó `AbstractXmlFlowExecutionTests` cung cấp các helper `startFlow(input, context)`, `resumeFlow(context)` và các assertion về state/outcome. Tên resource phải khớp vị trí file XML trong test classpath; các import và test runner phải tương thích với phiên bản SWF mà dự án đang dùng.

### 5.4. Những điều test đang chứng minh

| Test | Dữ liệu đặt trên context | Điều được xác minh |
|---|---|---|
| `testStartFlowReceivesInputAndCurrentUser` | Input map `hotelId=42` và principal `minh` | Flow nhận đúng input, service được gọi với user hiện tại |
| `testProceedReadsRequestParameterAndCurrentUser` | Event `proceed`, parameter `campaign=summer`, principal `minh` | Event chuyển state; transition đọc được request parameter và principal |
| `testConfirmUsesUserFromConfirmationRequest` | Event `confirm` và principal của request xác nhận | Flow kết thúc đúng outcome; service nhận user ở request cuối |

Test không chứng minh rằng `hotelId=42` tồn tại trong database, `minh` đã đăng nhập qua form login, hoặc một booking thật được commit. Những việc đó nằm ngoài phạm vi fake service và MockExternalContext.

## 6. Truyền nhiều giá trị request parameter

`MockExternalContext` hỗ trợ parameter đơn và parameter nhiều giá trị:

~~~java
MockExternalContext context = new MockExternalContext();

context.putRequestParameter("keyword", "spring");
context.putRequestParameter(
    "status",
    new String[] { "OPEN", "PENDING" }
);
~~~

Trong flow, `requestParameters.status` đại diện parameter nhiều giá trị theo kiểu mà `ParameterMap` cung cấp. Nếu logic phụ thuộc kiểu dữ liệu cụ thể, hãy kiểm tra API `ParameterMap` của phiên bản SWF đang dùng thay vì giả định nó luôn là một chuỗi duy nhất.

Một constructor khác cũng cho phép truyền sẵn `ParameterMap`:

~~~java
MockExternalContext context =
    new MockExternalContext(existingParameterMap);
~~~

Cách này hữu ích khi test cần chuẩn bị cả một tập request parameters. Với đa số flow test, `putRequestParameter` dễ đọc và đủ dùng.

### 6.1. Request parameters chỉ thuộc request hiện tại

Mỗi lần `resumeFlow(context)` mô phỏng một request mới. Nếu event `proceed` có parameter `campaign`, nhưng event `confirm` không gửi lại parameter đó, không nên mặc định `requestParameters.campaign` vẫn tồn tại ở request xác nhận.

Nếu cần giữ giá trị qua nhiều state, flow phải chủ động lưu vào scope, ví dụ `flowScope.campaign`. Đó là lý do ví dụ XML sao chép parameter từ request ở transition `proceed` sang flow scope.

## 7. Kiểm thử input không hợp lệ và context thiếu dữ liệu

Một test tốt cần bao phủ cả trường hợp có dữ liệu và trường hợp thiếu dữ liệu. Với flow khai báo `required="true"` cho input, cần có test không truyền input bắt buộc:

~~~java
public void testMissingRequiredInputIsRejected() {
    MutableAttributeMap<Object> input = new LocalAttributeMap<>();

    MockExternalContext context = new MockExternalContext();
    context.setCurrentUser("minh");

    try {
        startFlow(input, context);
        fail("Flow should reject a missing required input");
    } catch (org.springframework.webflow.execution.FlowExecutionException expected) {
        // Flow input mapping/startup rejected the incomplete input.
    }
}
~~~

Exception cụ thể có thể được bọc bởi kiểu `FlowExecutionException` hoặc subtype tùy phiên bản/cấu hình; test integration nên xác minh loại exception thực tế của dự án nếu cần assertion chính xác hơn.

Với principal, nếu flow bắt buộc phải có người dùng hiện tại, có thể viết test context không gọi `setCurrentUser` để kiểm tra đường lỗi đã thiết kế. Không để một test tình cờ phụ thuộc vào principal được giữ từ fixture dùng chung.

### 7.1. Không biến thiếu user thành dữ liệu mặc định

Nếu `currentUser` là null, không nên tự động thay bằng một tài khoản dùng chung trong flow chỉ để test chạy qua. Hãy quyết định chính sách: flow có cho khách ẩn danh hay yêu cầu xác thực? Nếu bắt buộc đăng nhập, nên chặn ở lớp bảo mật thích hợp và kiểm tra thêm hành vi flow khi context không có principal.

## 8. Locale, context path và session map

Ngoài input, event và principal, `MockExternalContext` còn có thể mô phỏng một số thuộc tính môi trường:

~~~java
import java.util.Locale;

MockExternalContext context = new MockExternalContext();
context.setLocale(Locale.forLanguageTag("vi-VN"));
context.setContextPath("/shop");
context.setCurrentUser("minh");
context.setEventId("search");
context.putRequestParameter("keyword", "đặt phòng");
~~~

`setLocale` hữu ích khi flow hoặc view cần chọn nội dung theo ngôn ngữ. `setContextPath` có ích khi kiểm tra cách flow tạo URL tương đối theo context. Các giá trị này không thay thế kiểm thử HTTP thật với servlet container; chúng chỉ cung cấp dữ liệu cho external context.

Nếu cần thiết lập session attributes, có thể làm việc với `getSessionMap()` hoặc truyền một `SharedAttributeMap` phù hợp qua `setSessionMap(...)`. Phân biệt:

- `requestMap`: attribute của request hiện tại.
- `sessionMap`: attribute trong phiên người dùng.
- `requestParameterMap`: parameter được gửi từ client.
- `flowScope`: dữ liệu của flow session.

Không dùng session map thay cho flow input khi test cần xác minh hợp đồng đầu vào của flow. Cũng không dùng request map thay cho request parameters: một bên là attribute của request, bên kia là dữ liệu parameter gửi lên.

## 9. Những giới hạn cần biết

`MockExternalContext` làm cho flow execution test có thể mô phỏng dữ liệu môi trường, nhưng không tự chạy toàn bộ stack web.

| Điều cần xác minh | MockExternalContext có đủ không? | Kiểm thử bổ sung |
|---|---|---|
| Flow nhận input map lúc start | Có, qua `startFlow(input, context)` | Flow execution test |
| Flow đọc request parameter | Có, qua `putRequestParameter` | Flow execution test |
| Flow xử lý event ID | Có, qua `setEventId` + `resumeFlow` | Flow execution test |
| Flow đọc Principal | Có, qua `setCurrentUser` | Flow execution test |
| Bean/action/service nhận đúng tham số | Có, nếu đăng ký fake/mock | Flow test + unit test |
| Servlet filter và Spring Security login | Không | MockMvc/Spring Security Test |
| CSRF token trong HTTP request thật | Không đầy đủ | MockMvc + `with(csrf())` |
| URL routing và FlowHandlerMapping | Không | Spring MVC integration test |
| Binding/conversion với request thực | Chỉ trong phạm vi flow test đã dựng | MVC/flow integration test |
| JSP/Thymeleaf render HTML | Không | View integration test |
| Database transaction và persistence | Không nếu service đã fake | Repository/service integration test |

Đặc biệt, `setCurrentUser("minh")` chỉ đặt principal cho external context. Nếu code của ứng dụng lấy user từ `SecurityContextHolder` hoặc dùng method security qua proxy, test với MockExternalContext có thể chưa thiết lập những thành phần đó. Hãy dùng công cụ Spring Security Test hoặc application context thích hợp cho kiểm thử bảo mật.

## 10. Lỗi thường gặp khi thiết lập context

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Flow báo thiếu input dù đã put request parameter | Request parameter không phải flow input | Truyền input map cho `startFlow(input, context)` |
| Service nhận user null | Chưa gọi `setCurrentUser` trên context của request hiện tại | Đặt principal trên từng context cần dùng |
| Event không chuyển state | Chưa gọi `setEventId` hoặc gọi `startFlow` thay vì `resumeFlow` | Thiết lập event ID rồi resume execution |
| Event đúng tên nhưng không có transition | Event được gửi ở sai state | Assert state hiện tại trước khi resume |
| Request parameter không thấy trong expression | Parameter đặt trên context khác hoặc tên không khớp | Dùng `putRequestParameter` trên context truyền vào thao tác hiện tại |
| Event ID bị bỏ qua | Custom test factory/view factory không parse event ID | Kiểm tra MockViewFactory và test support |
| Test user pass nhưng authorization thật fail | Principal mock không tạo SecurityContext/filter chain | Bổ sung Spring Security integration test |
| Test phụ thuộc thứ tự chạy | Fake/context map hoặc test fixture dùng chung trạng thái | Tạo fixture mới, reset dữ liệu và cô lập test |
| Request parameter cũ vẫn xuất hiện trong test | Tái sử dụng cùng context giữa nhiều request | Tạo context mới cho từng lần resume |
| Input sai kiểu | Chưa khai báo type hoặc test truyền kiểu không phù hợp | Kiểm tra `type` và conversion service |

### 10.1. setEventId phụ thuộc MockViewFactory

Trong API SWF 2.x, `setEventId` được thiết kế để đặt event sẽ phát khi flow được resume. Việc đọc event ID trên resume phụ thuộc `MockViewFactory` được cấu hình để xử lý event ID. `AbstractXmlFlowExecutionTests` cung cấp test infrastructure mặc định cho trường hợp phổ biến; nếu dự án ghi đè factory hoặc dùng custom view factory, cần kiểm tra lại hành vi này.

### 10.2. Không tái sử dụng một context như thể đó là toàn bộ session

Một external context đại diện cho môi trường của **một lần gọi vào flow**. Tạo context mới cho request kế tiếp giúp phát hiện việc quên thiết lập principal, locale hoặc parameter. Nếu cần chia sẻ session map giữa nhiều context, hãy cấu hình map dùng chung một cách có chủ đích thay vì mặc định mọi context mới đều chia sẻ cùng trạng thái.

## 11. Bài tập thực hành

Xây dựng flow `profileSearch` để tìm hồ sơ khách hàng:

- Flow nhận input `tenantId` bắt buộc khi khởi chạy.
- Người dùng hiện tại được đọc qua `currentUser.name`.
- View `searchCriteria` nhận event `search` và request parameters `keyword`, `status`.
- View `searchResults` nhận event `open` để mở một hồ sơ.
- View `profileDetails` cho phép `back` hoặc `finish`.

Yêu cầu viết flow execution test:

1. Truyền `tenantId` bằng `LocalAttributeMap` và `startFlow(input, context)`.
2. Dùng `setCurrentUser("tester")` và xác minh service nhận đúng tên principal.
3. Đặt `keyword` bằng `putRequestParameter`, gửi event `search` bằng `setEventId` rồi `resumeFlow(context)`.
4. Gửi parameter nhiều giá trị `status` và xác minh flow/service nhận đúng tập giá trị.
5. Gửi event `open` ở đúng state và xác minh hồ sơ được chọn.
6. Gửi event không có transition ở một state để kiểm tra flow không đi sang nhánh không hợp lệ.
7. Không truyền `tenantId` để kiểm tra input bắt buộc.
8. Tạo context tiếp tục flow nhưng không đặt user để kiểm tra chính sách khi principal thiếu.
9. Viết integration test riêng nếu muốn xác minh Spring Security authentication và HTTP filter chain.

**Tiêu chí hoàn thành:** người học có thể giải thích chính xác input được truyền qua đâu, request parameter được đặt ở đâu, event được gửi bằng API nào, user được mô phỏng ra sao, và vì sao các context đại diện cho từng request. Khi tách đúng bốn loại dữ liệu này, flow test sẽ kiểm tra được hợp đồng khởi chạy, đường đi của event và những quyết định phụ thuộc người dùng một cách rõ ràng.

## Tài liệu tham khảo

- Spring Web Flow 2.5.1 Reference Guide, *Testing flows*: https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/testing.html
- Spring Web Flow 2.5.x API, `MockExternalContext`: https://docs.spring.io/spring-webflow/docs/2.5.x/api/org/springframework/webflow/test/MockExternalContext.html
- Spring Web Flow 2.5.1 Reference Guide, *Input/Output Mapping* và *Special EL variables*: https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/

*Ghi chú tương thích:* Các ví dụ API dựa trên Spring Web Flow 2.5.x và test support XML. Kiểm tra package, chữ ký phương thức, JUnit/test runner và view factory khi dùng phiên bản khác.
