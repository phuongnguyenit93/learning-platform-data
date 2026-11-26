# Xử lý Ajax và cập nhật thành phần trong cùng view-state

Trong chương **Tích hợp JSF**, bài này hướng dẫn dùng Ajax của JavaServer Faces (JSF) để xử lý một phần form và cập nhật các thành phần giao diện mà không rời view-state hiện tại của Spring Web Flow. Với module **SPRING_WEB_FLOW**, state, event, transition và subflow mô hình hóa hành trình nhiều bước; JSF cung cấp component tree, binding, validation và cơ chế render giao diện. Ajax giúp phản hồi nhanh trong một bước, còn flow chỉ chuyển state khi người dùng thực hiện hành động điều hướng đã được định nghĩa.

Ví dụ, người dùng đang nhập địa chỉ giao hàng. Khi rời trường mã bưu chính, ứng dụng có thể kiểm tra định dạng và cập nhật thông báo lỗi cùng phần xem trước phí vận chuyển. Người dùng vẫn ở màn hình địa chỉ; flow chưa chuyển sang bước xem lại đơn hàng. Chỉ khi họ chọn “Tiếp tục” và event tương ứng được xử lý, transition mới đưa flow sang view-state khác.

## Phân biệt Ajax request với flow transition

Một flow execution có thể xử lý nhiều request trong cùng một view-state. Không phải request nào cũng cần làm flow chuyển sang state mới.

- **Ajax request trong cùng view-state:** JSF xử lý một phần component tree, cập nhật model nếu validation thành công và render lại các vùng được chỉ định. Flow vẫn ở state hiện tại.
- **Flow event:** một hành động như continue, cancel hoặc confirm được gửi để flow xử lý transition. Flow có thể chuyển sang state khác hoặc kết thúc.
- **Full postback:** trình duyệt gửi form và JSF xử lý request theo vòng đời đầy đủ; kết quả có thể render toàn bộ view hoặc được Spring Web Flow điều phối theo event.

~~~mermaid
flowchart TD
    A["Người dùng đang ở view-state shipping"] --> B{"Loại thao tác"}
    B -->|"Nhập / sửa trường"| C["JSF Ajax request"]
    C --> D["Execute component được chọn"]
    D --> E["Convert và validate"]
    E --> F{"Dữ liệu hợp lệ?"}
    F -->|"Có"| G["Update model và gọi listener"]
    F -->|"Không"| H["Giữ lỗi trong JSF component state"]
    G --> I["Render các component được chọn"]
    H --> I
    I --> J["Vẫn ở view-state shipping"]
    B -->|"Tiếp tục"| K["Gửi flow event continue"]
    K --> L["Spring Web Flow xử lý transition"]
    L --> M["Chuyển sang view-state review"]
~~~

Điểm mấu chốt: Ajax partial render là một phần của vòng đời JSF. Nó không tự tạo transition trong flow. Một listener có thể kiểm tra hoặc tính lại dữ liệu, nhưng nếu không phát event điều hướng thì flow vẫn ở view-state hiện tại.

## Vòng đời Ajax trong JSF

Một Ajax request của JSF vẫn đi qua các pha của JSF lifecycle, nhưng chỉ xử lý những component được chỉ định trong thuộc tính execute. Sau đó, JSF chỉ render các component được liệt kê trong render.

| Pha | Việc xảy ra trong Ajax request |
|---|---|
| Restore View | Khôi phục cây component của view hiện tại |
| Apply Request Values | Đọc giá trị gửi lên cho các component nằm trong execute |
| Process Validations | Chuyển kiểu và chạy validation cho các component được xử lý |
| Update Model Values | Ghi giá trị hợp lệ vào model được bind |
| Invoke Application | Gọi listener hoặc action tương ứng nếu lifecycle đi tới pha này |
| Render Response | Tạo partial response cho các component trong render |

Nếu validation thất bại, JSF không cập nhật model bằng giá trị không hợp lệ và thường chuyển tới render response để hiển thị lỗi. Giá trị người dùng vừa nhập có thể vẫn được giữ trong trạng thái của component để hiển thị lại, ngay cả khi model phía server chưa nhận giá trị đó.

Hai thuộc tính quan trọng:

- **execute** xác định component nào tham gia xử lý request.
- **render** xác định component nào được gửi lại trong partial response.

Các từ khóa thường dùng gồm **@this** (component phát request), **@form** (form chứa component), **@all** và **@none**. Có thể chỉ rõ ID component. Chọn phạm vi execute nhỏ giúp tránh chạy validation không liên quan; chọn render vừa đủ giúp giảm lượng HTML cần cập nhật.

## Ví dụ: kiểm tra mã bưu chính và cập nhật phần xem trước

Giả sử flow có view-state shipping, trong đó model được giữ trong flow scope. Người dùng nhập mã bưu chính; khi rời trường, Ajax xử lý riêng input này và render lại thông báo cùng phần xem trước.

Flow definition rút gọn:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="shippingDraft"
         class="com.example.checkout.ShippingDraft" />

    <view-state id="shipping"
                view="shipping.xhtml"
                model="shippingDraft">
        <transition on="continue" to="review">
            <evaluate expression="shippingService.validateAndPrepare(
                flowScope.shippingDraft, messageContext)" />
        </transition>
        <transition on="cancel" to="cancelled" />
    </view-state>

    <view-state id="review" view="review.xhtml">
        <transition on="editShipping" to="shipping" />
        <transition on="confirm" to="completed" />
    </view-state>

    <end-state id="completed" />
    <end-state id="cancelled" />
</flow>
~~~

Định nghĩa trên thể hiện ranh giới giữa hai bước. Event continue được dùng cho transition sang review; các request Ajax trong shipping chỉ xử lý component của view. Chi tiết validator và điều kiện ngăn transition khi có lỗi cần được cấu hình theo phiên bản Web Flow/JSF và cách tích hợp của ứng dụng.

Một trang Facelets có thể khai báo như sau:

~~~xhtml
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:h="http://xmlns.jcp.org/jsf/html"
      xmlns:f="http://xmlns.jcp.org/jsf/core">
<h:head>
    <title>Địa chỉ giao hàng</title>
</h:head>
<h:body>
    <h:form id="shippingForm">
        <h:messages id="globalMessages" />

        <h:outputLabel for="postalCode" value="Mã bưu chính" />
        <h:inputText id="postalCode"
                     value="#{flowScope.shippingDraft.postalCode}"
                     required="true">
            <f:ajax event="blur"
                    execute="@this"
                    render="postalCodeMessage globalMessages shippingPreview" />
        </h:inputText>

        <h:message id="postalCodeMessage" for="postalCode" />

        <h:panelGroup id="shippingPreview" layout="block">
            <h:outputText value="Phí giao hàng dự kiến: " />
            <h:outputText
                value="#{flowScope.shippingDraft.estimatedShippingFee}" />
        </h:panelGroup>

        <h:commandButton id="continue"
                         value="Tiếp tục"
                         action="continue" />

        <h:commandButton id="cancel"
                         value="Hủy"
                         action="cancel" />
    </h:form>
</h:body>
</html>
~~~

Khi input mất focus, f:ajax gửi request với execute là @this. JSF xử lý input postalCode, chạy conversion/validation của component và cập nhật model nếu hợp lệ. Các vùng postalCodeMessage, globalMessages và shippingPreview được render lại. Vì request không phát event continue hay cancel, người dùng vẫn ở view-state shipping.

Khi nhấn nút Tiếp tục, action outcome continue được ánh xạ tới transition on="continue" của flow. Đây là hành động điều hướng, khác với Ajax blur. Cú pháp và cách ánh xạ outcome cần phù hợp với phiên bản JSF và bộ tích hợp Spring Web Flow đang dùng.

## Dùng listener để tính lại dữ liệu phụ thuộc

Một số giao diện cần tính lại dữ liệu sau khi người dùng thay đổi trường. Ví dụ, mã bưu chính và phương thức giao hàng có thể ảnh hưởng phí vận chuyển. Có thể gắn Ajax listener vào component phát request:

~~~xhtml
<h:selectOneMenu id="deliveryMethod"
                 value="#{flowScope.shippingDraft.deliveryMethod}">
    <f:selectItems value="#{shippingView.deliveryMethods}" />
    <f:ajax event="change"
            execute="@this"
            listener="#{shippingView.refreshQuote}"
            render="shippingPreview globalMessages" />
</h:selectOneMenu>
~~~

Một listener JSF có thể nhận AjaxBehaviorEvent:

~~~java
import jakarta.faces.event.AjaxBehaviorEvent;

public void refreshQuote(AjaxBehaviorEvent event) {
    shippingDraft.setEstimatedShippingFee(
            shippingService.calculateEstimate(shippingDraft));
}
~~~

Đoạn Java dùng namespace Jakarta Faces. Nếu dự án chạy JSF 2.x trên Java EE, import tương ứng có thể thuộc package javax.faces thay vì jakarta.faces. Hãy dùng namespace đúng với phiên bản nền tảng đang triển khai. Bean shippingView phải được JSF EL phân giải và có quyền truy cập draft hiện tại; service nghiệp vụ nên được inject từ Spring container theo cấu hình tích hợp của ứng dụng.

Listener chỉ nên thực hiện thao tác ngắn, có thể lặp lại an toàn và không commit nghiệp vụ cuối cùng. Nếu cần gọi dịch vụ báo giá bên ngoài, cần xử lý timeout/lỗi và không để một lần blur làm phát sinh giao dịch không thể đảo ngược. Giá trị ước tính được render lại vẫn cần được xác minh ở server khi người dùng xác nhận đơn.

## Chọn execute đúng phạm vi

Nếu một form có nhiều trường required, dùng execute="@form" cho mọi thao tác blur có thể khiến các trường chưa nhập cũng bị validation. Điều này làm người dùng khó tương tác với từng trường.

| Nhu cầu | Execute gợi ý | Lưu ý |
|---|---|---|
| Kiểm tra riêng một input | @this | Chỉ xử lý component phát Ajax |
| Tính lại dựa trên một vài input | ID các input liên quan | Đảm bảo tất cả giá trị phụ thuộc được đưa vào request |
| Kiểm tra toàn bộ form trước xem lại | @form | Phù hợp khi người dùng chủ động gửi form |
| Chỉ render lại vùng giao diện | execute="@none" trong trường hợp phù hợp | Không có input nào được xử lý; listener phải không phụ thuộc giá trị form mới |

Ví dụ nếu phí giao hàng phụ thuộc cả postalCode và deliveryMethod, nhưng chỉ execute postalCode, model deliveryMethod được dùng trong listener có thể vẫn là giá trị cũ nếu người dùng vừa thay đổi nó mà chưa có request cập nhật. Khi đó, execute cần bao gồm cả hai component hoặc dùng @form ở hành động chủ động tính lại.

## Chọn render đúng component

Render xác định phần nào của cây component được JSF chuyển thành markup trong partial response. Thường nên render thông báo lỗi, kết quả tính toán và vùng phụ thuộc trực tiếp vào thao tác vừa thực hiện.

Một số lưu ý:

- Component đích cần tồn tại trong cây component ở thời điểm render. Với vùng chỉ xuất hiện có điều kiện, hãy đặt nội dung bên trong một panelGroup luôn được tạo để có ID ổn định.
- ID tương đối được phân giải trong naming container gần nhất. Nếu không tìm thấy component, dùng client ID tuyệt đối bắt đầu bằng dấu hai chấm và kiểm tra cấu trúc form/table thực tế.
- Khi render cả vùng cha, các component con trong vùng đó được cập nhật cùng markup của vùng cha; tránh liệt kê quá nhiều vùng trùng lặp.
- Nếu cần hiển thị lỗi của một input, render component h:message tương ứng và vùng tổng hợp h:messages nếu có.
- Không thao tác DOM bằng JavaScript để thay nội dung mà không đồng bộ component tree của JSF. Request sau có thể khôi phục trạng thái server và ghi đè thay đổi DOM tự thực hiện.

Ví dụ với component nằm trong một form:

~~~xhtml
<h:panelGroup id="quotePanel" layout="block">
    <h:outputText value="#{flowScope.shippingDraft.estimatedShippingFee}" />
</h:panelGroup>

<h:commandButton value="Tính lại">
    <f:ajax execute="@form"
            listener="#{shippingView.refreshQuote}"
            render="quotePanel globalMessages" />
</h:commandButton>
~~~

Nếu component đích nằm trong naming container khác, ID tương đối có thể không phân giải đúng. Hãy kiểm tra client ID được render trong HTML và cấu trúc naming container thay vì đoán ID.

## Validation và thông báo trong Ajax request

Ajax không bỏ qua validation. Khi input nằm trong execute, JSF vẫn chuyển đổi và kiểm tra giá trị theo converter, validator và thuộc tính required. Nếu có lỗi, model không được cập nhật cho giá trị đó; các component message cần được render để người dùng biết cách sửa.

Ví dụ có thể dùng validator chuẩn hoặc validator tùy chỉnh:

~~~xhtml
<h:inputText id="postalCode"
             value="#{flowScope.shippingDraft.postalCode}"
             required="true"
             requiredMessage="Vui lòng nhập mã bưu chính">
    <f:validateRegex pattern="[0-9]{5,6}" />
    <f:ajax event="blur"
            execute="@this"
            render="postalCodeMessage globalMessages" />
</h:inputText>
<h:message id="postalCodeMessage" for="postalCode" />
~~~

Trong ứng dụng đa ngôn ngữ, message của validator nên được phân giải từ resource bundle theo locale hiện tại. Việc render một phần không làm thay đổi nguyên tắc quản lý message code và bản dịch. Kiểm thử nên xác nhận mã lỗi, source và hành vi giữ state; nội dung dịch có thể được kiểm thử riêng theo locale.

Nếu một Ajax request bị validation lỗi, listener ở pha Invoke Application thường không được gọi vì lifecycle kết thúc sớm để render lỗi. Đừng giả định listener luôn chạy dù dữ liệu không hợp lệ. Nếu cần xử lý trong mọi trường hợp, hãy thiết kế listener và phase phù hợp với API JSF, đồng thời cân nhắc kỹ thuộc tính immediate vì nó thay đổi thời điểm xử lý sự kiện và có thể bỏ qua các pha validation/model update mong muốn.

## Không để Ajax vô tình kích hoạt transition

Một lỗi thiết kế phổ biến là dùng cùng một nút hoặc cùng một action cho cả việc cập nhật vùng giao diện và chuyển state. Khi người dùng chỉ muốn xem lại phí vận chuyển, request không nên phát event khiến flow chuyển sang review.

Hãy tách ý định:

- Ajax blur/change: cập nhật hoặc kiểm tra một phần dữ liệu trong view-state.
- Nút tính lại: gọi listener, render vùng kết quả, không trả outcome điều hướng.
- Nút tiếp tục: gửi event continue để flow kiểm tra toàn bộ bước và chuyển state.
- Nút hủy: gửi event cancel để flow xử lý nhánh hủy.

Nếu một thao tác Ajax thật sự cần điều hướng, hãy xem đó là một flow event có chủ đích và kiểm thử riêng. Partial response của JSF và response điều hướng của Web Flow cần được xử lý đúng bởi tích hợp đang dùng; không nên tự tạo redirect hoặc thay URL trong listener để mô phỏng transition.

## Liên hệ với state và dữ liệu trong flow

Dữ liệu bind qua JSF thường được lưu trong model mà view-state đang sử dụng. Nếu model được đặt trong flowScope, giá trị hợp lệ có thể tồn tại khi người dùng rời view-state và quay lại trong cùng execution. Tuy nhiên, một Ajax request chỉ cập nhật các component được execute; field ngoài phạm vi đó có thể chưa được bind trong request hiện tại.

Đừng dùng Ajax để thay đổi trực tiếp state machine. Nếu người dùng thay đổi lựa chọn khiến flow phải chuyển nhánh, hãy phát event rõ ràng và để transition hoặc decision-state xử lý. Nếu chỉ cần cập nhật một vùng hiển thị, hãy giữ thao tác trong view-state và render lại component.

Cần phân biệt trạng thái component JSF với dữ liệu trong flow scope. Khi validation thất bại, component có thể giữ submitted/local value để hiển thị lại; flow model có thể vẫn giữ giá trị trước request. Khi điều hướng hoặc reset form, hãy kiểm tra hành vi reset component state và model để tránh hiển thị một giá trị cũ hoặc lỗi đã hết hiệu lực.

## Kiểm thử Ajax trong cùng view-state

Kiểm thử cần xác nhận cả ba điều: JSF xử lý đúng component, partial response cập nhật đúng vùng và flow không chuyển state ngoài ý muốn.

Một kịch bản tích hợp:

1. Khởi chạy flow và mở view-state shipping.
2. Gửi Ajax blur với mã bưu chính sai định dạng.
3. Xác nhận response là partial response của JSF, thông báo lỗi được render và flow vẫn ở shipping.
4. Nhập mã hợp lệ rồi gửi Ajax lần nữa.
5. Xác nhận model được cập nhật và vùng xem trước được render lại.
6. Thay phương thức giao hàng, xác nhận listener tính lại phí và chỉ vùng liên quan được cập nhật.
7. Nhấn Tiếp tục; xác nhận flow phát event continue và chuyển sang review.
8. Quay lại shipping; xác nhận dữ liệu trong flow scope được hiển thị theo chính sách dữ liệu của ứng dụng.

Có thể kiểm tra các tham số partial request như javax.faces.partial.ajax, javax.faces.source, javax.faces.partial.execute và javax.faces.partial.render trong request. Ở response, kiểm tra partial-response XML có update cho đúng client ID. Các tên tham số này là chi tiết giao thức JSF; không nên để test nghiệp vụ phụ thuộc vào thứ tự hoặc chuỗi HTML đầy đủ.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Input blur với giá trị hợp lệ | Model được cập nhật; view-state không đổi |
| Input blur với giá trị không hợp lệ | Model không nhận giá trị lỗi; message được render; state không đổi |
| Listener tính lại phí | Vùng xem trước được cập nhật; không commit đơn hàng |
| Render ID sai | Test phát hiện component không được cập nhật hoặc lỗi component lookup |
| Nhấn Continue | Flow xử lý event và chuyển sang state review nếu validation thành công |
| Nhấn Cancel | Flow xử lý nhánh hủy đã khai báo |
| Hai Ajax request liên tiếp | Không ghi đè dữ liệu mới bằng kết quả cũ ngoài ý muốn |

## Chẩn đoán sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Ajax request trả lỗi component không tìm thấy | Render ID sai hoặc naming container khác | Kiểm tra client ID và cấu trúc form/table |
| Input đổi nhưng model không đổi | Input không nằm trong execute hoặc validation thất bại | Kiểm tra partial.execute, conversion và message |
| Message không xuất hiện | Message component không nằm trong render | Thêm ID message vào render và xác nhận source |
| Phí xem trước không cập nhật | Listener không chạy, execute thiếu input phụ thuộc hoặc render sai vùng | Kiểm tra request payload, lifecycle và render target |
| Blur làm lỗi các trường chưa nhập | Execute quá rộng như @form | Thu hẹp execute về @this hoặc nhóm input cần thiết |
| Ajax vô tình chuyển sang state khác | Component phát flow outcome/action | Tách listener Ajax khỏi action transition |
| Giá trị cũ xuất hiện sau render | Component local/submitted value và model không đồng bộ | Kiểm tra validation, reset state và thứ tự xử lý |
| Listener không được gọi khi form lỗi | Lifecycle dừng ở validation/render response | Xác định pha listener và thiết kế xử lý lỗi phù hợp |

Khi debug, bắt đầu từ request trong Network: xác nhận đây có phải Ajax request, component source nào phát, execute và render có giá trị gì. Tiếp theo xem server log, conversion/validation messages và listener. Cuối cùng xác nhận flow execution vẫn ở view-state mong muốn hay đã nhận một event điều hướng.

## Checklist triển khai

Trước khi đưa Ajax vào một view-state JSF, hãy rà soát:

- [ ] Ajax chỉ xử lý ý định cập nhật cục bộ, còn flow event dùng cho điều hướng.
- [ ] Execute bao gồm đủ input cần thiết và không chạy validation ngoài phạm vi.
- [ ] Render bao gồm message và các vùng phụ thuộc cần cập nhật.
- [ ] Các render target có ID ổn định và đúng naming container.
- [ ] Listener ngắn, không commit nghiệp vụ chỉ vì người dùng blur/change.
- [ ] Validation lỗi được hiển thị; không giả định model đã nhận giá trị không hợp lệ.
- [ ] Message được phân giải theo locale đang hoạt động.
- [ ] Model và component state được đồng bộ khi người dùng sửa hoặc quay lại.
- [ ] Phiên bản JSF và namespace javax/jakarta khớp với nền tảng.
- [ ] Kiểm thử partial request, partial response và state của flow sau mỗi thao tác.

## Ghi nhớ

- Ajax trong JSF có thể xử lý và render một phần component tree mà vẫn giữ nguyên view-state của Spring Web Flow.
- **execute** xác định component được xử lý; **render** xác định component được cập nhật trong partial response.
- Validation vẫn chạy cho component nằm trong execute; lỗi có thể ngăn model update và listener ở pha sau.
- Dùng listener cho tính toán cục bộ; dùng flow event và transition cho điều hướng giữa các state.
- Chọn ID render đúng naming container, giữ vùng cập nhật ổn định và kiểm thử bằng request/response thực tế.

