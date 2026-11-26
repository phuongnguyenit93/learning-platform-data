# Điều hướng bằng kết quả action và sự kiện của thành phần

Khi dùng JSF làm view technology cho Spring Web Flow, người dùng tương tác với các thành phần như `h:commandButton`, `h:commandLink`, input và Ajax behavior. JSF phát sinh sự kiện trong vòng đời xử lý request; một action method có thể trả về một chuỗi outcome. Trong một view-state của Spring Web Flow, outcome đó được dùng làm event để flow chọn transition tiếp theo.

Để điều hướng đúng, cần phân biệt ba khái niệm: sự kiện của thành phần JSF, kết quả trả về từ action method và event mà flow dùng để tìm transition. Chúng liên quan với nhau nhưng không đồng nhất. Component phát sự kiện khi người dùng tương tác; action method trả outcome; tích hợp JSF của Spring Web Flow chuyển outcome thành flow event. Flow definition quyết định state tiếp theo.

## 1. Vai trò của action outcome trong flow

Trong JSF, thuộc tính `action` của command component trỏ đến một action method hoặc một outcome tĩnh. Action method thường trả về `String`. Khi trang đang được hiển thị bởi một view-state của Spring Web Flow, outcome này trở thành event để flow xử lý.

Ví dụ, người dùng nhấn nút tiếp tục và action method trả về `continue`:

```java
public class BookingActions {

    public String continueBooking() {
        return "continue";
    }

    public String cancelBooking() {
        return "cancel";
    }
}
```

Flow khai báo transition có event tương ứng:

```xml
<view-state id="enterDetails" view="enterDetails.xhtml">
    <transition on="continue" to="prepareReview" />
    <transition on="cancel" to="cancelled" />
</view-state>
```

Khi action method trả `continue`, flow tìm transition `on="continue"` và chuyển sang state `prepareReview`. Khi action trả `cancel`, flow đi đến state `cancelled`. Chuỗi outcome chính là giao ước giữa trang JSF và flow definition.

Tên component như `continueButton` hoặc ID của `h:commandButton` không tự động trở thành event của flow. Giá trị được dùng để điều hướng là outcome của action. Vì vậy, nếu method trả `continue` nhưng flow chỉ khai báo transition `on="submit"`, hai bên không khớp và hành trình sẽ không đi theo transition mong muốn.

## 2. Kết nối command component với action method

Một trang Facelets có thể bind dữ liệu vào flow scope và gắn command component với action method:

```xml
<h:form id="bookingForm">
    <h:panelGrid columns="2">
        <h:outputLabel for="email" value="Email" />
        <h:inputText id="email"
                     value="#{flowScope.booking.email}"
                     required="true" />

        <h:outputLabel for="phone" value="Điện thoại" />
        <h:inputText id="phone"
                     value="#{flowScope.booking.phone}" />
    </h:panelGrid>

    <h:message for="email" />
    <h:messages globalOnly="true" />

    <h:commandButton id="continueButton"
                     value="Tiếp tục"
                     action="#{bookingActions.continueBooking}" />

    <h:commandButton id="cancelButton"
                     value="Hủy"
                     immediate="true"
                     action="#{bookingActions.cancelBooking}" />
</h:form>
```

Trong ví dụ, `bookingActions` là bean được JSF/Spring quản lý và có thể được inject service nếu cần. `flowScope.booking` là dữ liệu của flow đang chạy, được hiển thị và cập nhật qua EL trong view. Nút tiếp tục trả outcome `continue`; nút hủy trả outcome `cancel`.

Flow definition cần khai báo view-state có view tương ứng. Các tên bean, scope và cách đăng ký bean phụ thuộc cấu hình JSF/Spring của ứng dụng; điều quan trọng là action method có thể được JSF gọi và outcome của nó khớp với transition của flow.

Không nên dùng một outcome tùy ý do trình duyệt gửi lên. Outcome nên được quyết định bởi action method phía server hoặc một giá trị tĩnh đã được khai báo trong view. Người dùng có thể thay đổi request, nhưng không nên có khả năng chọn một flow state bất kỳ bằng cách sửa tham số.

## 3. Phân biệt action và actionListener

JSF có hai thuộc tính thường gặp trên command component:

| Thuộc tính | Chữ ký thường dùng | Mục đích |
|---|---|---|
| `action` | Method trả `String` hoặc outcome tĩnh | Trả navigation outcome; trong view-state của Spring Web Flow, outcome được dùng làm flow event |
| `actionListener` | Method nhận `ActionEvent` và trả `void` | Phản hồi sự kiện component, đọc thông tin component hoặc cập nhật trạng thái phục vụ xử lý |

Ví dụ:

```java
import jakarta.faces.event.ActionEvent;

public class BookingActions {

    public void recordContinueClick(ActionEvent event) {
        // Ghi nhận thao tác hoặc cập nhật trạng thái giao diện cần thiết.
    }

    public String continueBooking() {
        return "continue";
    }
}
```

```xml
<h:commandButton value="Tiếp tục"
                 actionListener="#{bookingActions.recordContinueClick}"
                 action="#{bookingActions.continueBooking}" />
```

`actionListener` được dùng cho xử lý sự kiện của component; nó không trả về navigation outcome. `action` là nơi trả chuỗi event mà flow dùng để chọn transition. Nếu listener thay đổi một thuộc tính, action method có thể đọc thuộc tính đó và quyết định outcome, nhưng không nên nhầm giá trị trả về của listener với flow event.

Ví dụ trên dùng package `jakarta.faces` của Jakarta Faces hiện đại. Ứng dụng JSF cũ dùng Java EE có thể cần import `javax.faces.event.ActionEvent`; hãy dùng namespace phù hợp với phiên bản JSF đang chạy.

## 4. Các loại sự kiện component thường gặp

JSF phát sinh nhiều loại sự kiện tùy component và thao tác của người dùng:

| Sự kiện | Nguồn phát | Công dụng điển hình | Có tự chọn transition của flow không? |
|---|---|---|---|
| `ActionEvent` | Command button hoặc command link | Xử lý thao tác gửi form hoặc kích hoạt lệnh | Outcome của action method gắn với lệnh có thể trở thành flow event |
| `ValueChangeEvent` | Input có giá trị thay đổi | Phản hồi khi lựa chọn hoặc giá trị input đổi | Không tự động trở thành flow event chỉ vì giá trị thay đổi |
| `AjaxBehaviorEvent` | Thành phần có `f:ajax` | Xử lý tương tác Ajax hoặc cập nhật một phần view | Listener Ajax là sự kiện component; điều hướng flow cần action outcome hoặc cơ chế tích hợp tương ứng |
| `PhaseEvent` | JSF lifecycle | Theo dõi một giai đoạn của vòng đời request | Không phải event điều hướng do người dùng chọn |

Ví dụ, khi người dùng chọn quốc gia, `ValueChangeListener` có thể cập nhật danh sách tỉnh/thành. Đó là hành vi trong màn hình hiện tại. Khi người dùng nhấn nút “Tiếp tục”, action method trả `continue` để flow chuyển sang state tiếp theo.

Không nên dùng listener của mọi input để điều hướng flow. Làm vậy khiến một thay đổi nhỏ trong form có thể làm người dùng rời view trước khi hoàn tất dữ liệu. Chỉ dùng action outcome làm flow event khi thao tác thực sự đại diện cho một bước điều hướng trong hành trình.

## 5. Vòng đời JSF ảnh hưởng đến việc phát flow event

Khi command component được submit, JSF xử lý request theo các giai đoạn chính:

1. **Restore View:** khôi phục cây component của view.
2. **Apply Request Values:** đọc các giá trị gửi lên và phát hiện component được kích hoạt.
3. **Process Validations:** chuyển đổi và kiểm tra dữ liệu theo converter, validator và ràng buộc của component.
4. **Update Model Values:** ghi giá trị hợp lệ vào model được bind.
5. **Invoke Application:** gọi action listener và action method theo vòng đời JSF.
6. **Render Response:** render view hoặc response tương ứng.

Với submit thông thường, action method được gọi sau khi validation và cập nhật model hoàn tất. Nếu một input không hợp lệ, JSF thường bỏ qua bước gọi action và render lại view cùng thông báo lỗi. Vì action method không được gọi, outcome không được trả về và flow không nhận event điều hướng tương ứng.

Đây là lý do một form có lỗi vẫn ở lại view-state hiện tại. Người dùng có thể sửa dữ liệu, gửi lại form và chỉ khi validation thành công thì action method mới trả outcome để flow chuyển bước.

## 6. Sử dụng immediate cho hành động bỏ qua validation

Thuộc tính `immediate="true"` làm sự kiện của component được xử lý sớm hơn trong JSF lifecycle. Một trường hợp thường gặp là nút hủy hoặc quay lại: người dùng có thể rời form dù các trường bắt buộc chưa được nhập đầy đủ.

```xml
<h:commandButton value="Quay lại"
                 immediate="true"
                 action="#{bookingActions.back}" />
```

Action `back` có thể trả outcome `back`, được flow ánh xạ sang transition tương ứng. Cách này phù hợp khi thao tác không cần dữ liệu vừa nhập và không nên bị chặn bởi validation của form.

Không bật `immediate` cho nút submit chính chỉ để tránh lỗi validation. Khi action được xử lý sớm, model có thể chưa nhận các giá trị mới và các kiểm tra thông thường có thể bị bỏ qua. Nếu action cần đọc dữ liệu form vừa nhập, hãy để lifecycle chạy đúng thứ tự hoặc thiết kế riêng quy trình xử lý phù hợp.

`immediate` cũng không phải cơ chế phân quyền. Dù người dùng bấm hủy hay quay lại, service vẫn phải kiểm tra quyền và điều kiện nghiệp vụ trước mọi thao tác có side effect.

## 7. Dùng action outcome để điều phối các bước nghiệp vụ

Action method có thể chỉ trả event, còn service nghiệp vụ được gọi ở action-state hoặc action gắn với flow. Cách này giữ cho bean của view mỏng và làm cho quy tắc nghiệp vụ không phụ thuộc JSF.

Ví dụ flow chuyển từ form sang state chuẩn bị màn hình review:

```xml
<view-state id="enterDetails" view="enterDetails.xhtml">
    <transition on="continue" to="prepareReview" />
    <transition on="cancel" to="cancelled" />
</view-state>

<action-state id="prepareReview">
    <evaluate expression="bookingService.prepareReview(flowScope.booking)"
              result="flowScope.review" />
    <transition to="reviewBooking" />
</action-state>

<view-state id="reviewBooking" view="reviewBooking.xhtml">
    <transition on="confirm" to="confirmBooking" />
    <transition on="back" to="enterDetails" />
</view-state>
```

Action method `continueBooking()` trả `continue`; flow thực hiện transition rồi gọi `bookingService.prepareReview(...)`. Service có thể kiểm tra dữ liệu nghiệp vụ, tải thông tin cần thiết và trả DTO cho màn hình review. Nếu kết quả nghiệp vụ không cho phép tiếp tục, flow có thể dùng một event hoặc cơ chế exception handling được thiết kế rõ ràng để quay lại view và hiển thị thông báo.

Không nên để JSF backing bean tự quyết định tên view vật lý hoặc tự điều khiển toàn bộ state machine. Bean phục vụ tương tác component; flow định nghĩa thứ tự bước; service thực hiện quy tắc nghiệp vụ.

## 8. Event outcome phải khớp transition

Outcome là một phần của hợp đồng giữa view và flow. Nên dùng tên ngắn, ổn định và thể hiện ý định người dùng hoặc kết quả của action.

| Action outcome | Transition trong view-state | Ý nghĩa |
|---|---|---|
| `continue` | `<transition on="continue" to="prepareReview" />` | Người dùng muốn sang bước xem lại |
| `back` | `<transition on="back" to="enterDetails" />` | Quay lại bước nhập thông tin |
| `cancel` | `<transition on="cancel" to="cancelled" />` | Hủy hành trình |
| `confirm` | `<transition on="confirm" to="confirmBooking" />` | Xác nhận thao tác |

Không nên dùng tên ID component như `form:continueButton` làm giao ước điều hướng nếu không có lý do cụ thể. Component ID có thể thay đổi khi đổi cấu trúc form hoặc naming container; outcome của action là giao ước rõ ràng hơn.

Nếu nhiều nút cùng gọi một method, method có thể cần xác định hành động dựa trên ngữ cảnh component hoặc tham số hợp lệ. Tuy nhiên, các nút điều hướng khác nhau thường dễ bảo trì hơn khi có action method riêng và outcome rõ ràng. Không nhận trực tiếp tên transition từ request để chuyển state tùy ý.

Khi một outcome không có transition tương ứng, flow không thể thực hiện nhánh điều hướng mong muốn. Hãy kiểm tra outcome thực tế mà action trả về, phân biệt chữ hoa/thường và xác minh transition nằm trong đúng view-state đang hoạt động. Đừng giả định một JSF navigation rule dành cho toàn ứng dụng sẽ thay thế transition của flow.

## 9. Kết hợp Ajax và sự kiện của component

`f:ajax` cho phép xử lý một phần form mà không render lại toàn bộ trang. Ví dụ khi chọn loại khách hàng, giao diện có thể hiển thị thêm trường mã số doanh nghiệp:

```xml
<h:selectOneMenu id="customerType"
                 value="#{flowScope.booking.customerType}">
    <f:selectItem itemValue="PERSON" itemLabel="Cá nhân" />
    <f:selectItem itemValue="BUSINESS" itemLabel="Doanh nghiệp" />
    <f:ajax event="change"
            execute="@this"
            render="businessFields" />
</h:selectOneMenu>

<h:panelGroup id="businessFields" layout="block">
    <!-- Các trường chỉ hiển thị khi khách hàng là doanh nghiệp -->
</h:panelGroup>
```

Ajax behavior phục vụ tương tác trong view. Event `change` và listener của nó không mặc nhiên có nghĩa flow phải chuyển state. Khi người dùng hoàn tất bước, command component vẫn có thể phát action outcome `continue` để flow thực hiện transition.

Với Ajax submit có liên quan đến flow navigation, cần kiểm thử cách JSF integration xử lý response partial và state mới. Bảo đảm các component cần thiết nằm trong vùng `execute`, các vùng cần cập nhật nằm trong `render`, và request vẫn mang thông tin execution cần thiết. Không nên để một partial request vô tình kích hoạt transition khi người dùng chỉ đang thay đổi một trường.

## 10. Validation và message trên JSF view

JSF có cơ chế converter, validator và message riêng. Khi một component không hợp lệ, message có thể được hiển thị bằng `h:message` cho một trường hoặc `h:messages` cho toàn view. Spring Web Flow điều phối transition sau khi JSF lifecycle xử lý action outcome.

```xml
<h:inputText id="email"
             value="#{flowScope.booking.email}"
             required="true"
             validatorMessage="Email không hợp lệ." />
<h:message for="email" />
<h:messages globalOnly="true" />
```

Khi validation thất bại, action method thông thường không được gọi; do đó flow không nhận outcome `continue`. Người dùng ở lại view-state và nhìn thấy lỗi. Khi validation thành công, action trả outcome, flow chọn transition và có thể tiếp tục kiểm tra nghiệp vụ ở service.

Validation ở giao diện không thay thế kiểm tra nghiệp vụ phía server. Service phải kiểm tra lại quyền, trạng thái và các bất biến trước khi ghi dữ liệu, vì request có thể được gửi trực tiếp hoặc dữ liệu đã thay đổi kể từ lần render trước.

## 11. Kiểm thử action outcome và component event

Nên kiểm thử cả action bean, JSF lifecycle và flow transition:

1. Gọi action method `continueBooking()` và xác minh outcome là `continue`.
2. Submit command button trên view-state và xác minh flow đi đến state có transition `on="continue"`.
3. Gửi form có lỗi validation và xác minh action không được gọi, flow ở lại view-state và message được render.
4. Nhấn nút hủy có `immediate="true"` và xác minh flow đi theo outcome `cancel` dù các trường bắt buộc còn trống.
5. Phát `ValueChangeEvent` hoặc `AjaxBehaviorEvent` và xác minh chỉ cập nhật phần view mong muốn, không chuyển flow ngoài ý muốn.
6. Trả một outcome không có transition và xác minh lỗi được phát hiện trong kiểm thử cấu hình hoặc tích hợp.
7. Xác minh action listener chạy cho mục đích component event nhưng không bị nhầm là nguồn trả flow outcome.
8. Kiểm tra nhiều command component trong cùng form để chắc chắn mỗi nút phát đúng outcome.

Unit test cho action bean có thể xác minh giá trị String trả về. Kiểm thử tích hợp Spring Web Flow/JSF cần xác minh sự kiện component thực sự đi qua JSF lifecycle, được chuyển thành flow event và chọn đúng transition. Chỉ kiểm thử method Java không đủ chứng minh cấu hình view và flow khớp nhau.

## 12. Lỗi thường gặp và cách xử lý

- **Outcome không khớp transition:** kiểm tra chuỗi trả về từ action method và thuộc tính `on` của transition.
- **Dùng component ID làm flow event:** phân biệt ID của component với outcome mà action trả về.
- **Mong `actionListener` trả outcome:** listener thường trả `void`; dùng `action` để trả navigation outcome.
- **Validation thất bại nhưng mong action vẫn chạy:** kiểm tra JSF lifecycle, converter, validator và message của input.
- **Bật `immediate` cho submit chính:** action có thể chạy trước khi model được cập nhật. Chỉ dùng cho hành động như cancel/back khi phù hợp.
- **Value change tự điều hướng flow:** dùng value change cho cập nhật component; dùng action outcome cho bước điều hướng có chủ đích.
- **Ajax request kích hoạt transition ngoài ý muốn:** kiểm tra component phát request, vùng `execute` và action được gọi.
- **Backing bean chứa toàn bộ nghiệp vụ:** chuyển quy tắc và transaction vào service, để action bean trả outcome cho flow.
- **Dựa vào JSF navigation rule thay cho flow transition:** trong một view-state, khai báo event và transition rõ ràng trong flow definition.

## 13. Nguyên tắc áp dụng

1. Dùng `action` để trả outcome biểu thị flow event; khai báo transition có cùng tên trong view-state.
2. Dùng `actionListener`, `ValueChangeListener` và Ajax listener cho xử lý sự kiện component, không mặc định xem chúng là flow navigation.
3. Nhớ rằng JSF validation và model update diễn ra trước action trong submit thông thường.
4. Chỉ dùng `immediate="true"` cho hành động cần bỏ qua validation của form, thường là cancel hoặc back.
5. Để flow điều phối state và service thực hiện quy tắc nghiệp vụ.
6. Giữ outcome ổn định, rõ nghĩa và do server quyết định.
7. Kiểm thử outcome, transition, validation failure, component event và Ajax behavior trong cấu hình tích hợp thực tế.

Trong tích hợp JSF, action outcome là cầu nối trực tiếp giữa thao tác của người dùng và transition của Spring Web Flow. Khi phân biệt outcome với component event, hiểu đúng JSF lifecycle và khai báo transition tương ứng, các màn hình JSF có thể tham gia hành trình nhiều bước một cách rõ ràng, trong khi flow vẫn giữ quyền điều phối và service giữ trách nhiệm nghiệp vụ.
