# Kiểm soát dữ liệu được sửa khi quay lại bước trước

Trong chương **Liên kết biểu mẫu**, bài này giải thích cách kiểm soát dữ liệu người dùng đã sửa khi điều hướng qua lại giữa các bước của một hành trình Spring Web Flow. Với module **SPRING_WEB_FLOW**, state, event, transition và subflow mô tả thứ tự nghiệp vụ; form binding đưa dữ liệu từ request vào model của flow. Khi người dùng quay lại bước trước, ứng dụng cần xác định thay đổi nào được giữ, thay đổi nào bị loại bỏ và dữ liệu phụ thuộc nào phải được kiểm tra hoặc tính lại.

Một nút “Quay lại” có thể chỉ chuyển màn hình, nhưng request của nút đó vẫn có thể gửi các trường form hiện tại. Nếu transition thực hiện binding trước khi xử lý event, những giá trị người dùng vừa nhập có thể đã được ghi vào model. Vì vậy, điều hướng và chính sách lưu thay đổi phải được thiết kế cùng nhau.

## Vòng đời dữ liệu khi đi qua các bước

Hãy hình dung một flow đặt hàng gồm ba bước: giỏ hàng, địa chỉ giao hàng và xem lại đơn hàng. Người dùng nhập địa chỉ, đi tới bước xem lại, sau đó quay lại sửa địa chỉ. Ứng dụng cần trả lại đúng dữ liệu đang làm dở để người dùng tiếp tục. Nếu người dùng chọn hủy phần sửa, ứng dụng có thể cần khôi phục giá trị trước khi chỉnh sửa.

Trong Spring Web Flow, mỗi request tiếp tục một flow execution. Khi view-state có khai báo model, dữ liệu form được bind vào đối tượng model theo cấu hình binder và transition. Nếu đối tượng đó được giữ trong **flowScope**, nó có thể được dùng xuyên suốt nhiều state trong cùng flow execution.

~~~mermaid
flowchart TD
    A["Giỏ hàng"] -->|"continue"| B["Nhập địa chỉ"]
    B -->|"continue / bind dữ liệu"| C["Xem lại đơn"]
    C -->|"editShipping"| B
    B -->|"save changes"| C
    B -->|"discard edits"| D["Khôi phục bản sao trước sửa"]
    D --> C
    C -->|"confirm"| E["Xác nhận đơn"]
~~~

Điều quan trọng là phân biệt ba thời điểm:

1. **Người dùng sửa dữ liệu trên trình duyệt:** thay đổi mới nằm trong các control của form.
2. **Request được gửi và binding chạy:** các giá trị được chép vào model phía server theo các thuộc tính được phép bind.
3. **Nghiệp vụ được xác nhận:** ứng dụng lưu hoặc thực hiện thay đổi chính thức ở hệ thống nghiệp vụ.

Ba thời điểm này không nhất thiết xảy ra cùng lúc. Một form có thể đã bind dữ liệu vào flow model nhưng đơn hàng chưa được lưu vào cơ sở dữ liệu. Ngược lại, nếu ứng dụng gọi service ghi dữ liệu ở mỗi bước, thao tác quay lại giao diện không tự hoàn tác giao dịch đã thực hiện.

## Chọn chính sách khi quay lại

Trước khi viết transition, hãy quyết định hành vi mong muốn cho từng nút và từng state.

| Chính sách | Hành vi khi quay lại | Khi phù hợp |
|---|---|---|
| Giữ thay đổi | Dữ liệu đã bind vẫn nằm trong flow model và được hiển thị lại | Người dùng quay lại để tiếp tục chỉnh sửa một bản nháp |
| Bỏ thay đổi của request hiện tại | Không bind dữ liệu gửi cùng event quay lại | Nút quay lại chỉ có nhiệm vụ điều hướng, không lưu nội dung vừa nhập |
| Khôi phục bản sao trước khi sửa | Phục hồi các trường của bước đang chỉnh sửa về snapshot đã lưu trước khi vào bước đó | Có nút “Hủy chỉnh sửa” hoặc “Bỏ thay đổi” |
| Giữ một phần, tính lại phần phụ thuộc | Giữ trường được phép sửa, xóa hoặc tính lại dữ liệu phụ thuộc | Thay đổi địa chỉ làm thay đổi phí giao hàng hoặc lựa chọn vận chuyển |

Không nên dùng một hành vi chung cho mọi nút. “Quay lại để sửa” thường muốn giữ dữ liệu hiện tại; “Hủy chỉnh sửa” thường muốn bỏ các thay đổi chưa xác nhận. Tên event và transition nên phản ánh đúng chính sách này để người bảo trì không nhầm hai thao tác.

## Giữ dữ liệu giữa các view-state bằng flowScope

Một biến khai báo bằng flow variable có vòng đời trong flow execution. Đây là nơi phù hợp để giữ DTO hoặc dữ liệu nháp cần dùng qua nhiều bước. Ví dụ, flow tạo một đối tượng **BookingDraft** khi bắt đầu và dùng cùng đối tượng đó làm model cho bước nhập địa chỉ và bước xem lại.

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="bookingDraft"
         class="com.example.booking.BookingDraft" />

    <view-state id="shipping"
                view="booking/shipping"
                model="bookingDraft">
        <binder>
            <binding property="recipient" required="true" />
            <binding property="addressLine" required="true" />
            <binding property="postalCode" required="true" />
        </binder>

        <transition on="continue" to="review">
            <evaluate expression="bookingValidator.validateShipping(bookingDraft, messageContext)" />
        </transition>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="editShipping" to="shipping" />
        <transition on="confirm" to="confirmed">
            <evaluate expression="bookingService.confirm(bookingDraft)" />
        </transition>
    </view-state>

    <end-state id="confirmed" />
</flow>
~~~

Trong ví dụ này, **bookingDraft** là flow variable được dùng làm model của view nhập địa chỉ. Khi người dùng gửi event **continue**, các trường được cho phép bind vào cùng đối tượng rồi flow chuyển tới **review**. Khi người dùng phát event **editShipping**, flow quay lại state **shipping** và view có thể đọc lại dữ liệu hiện có từ **bookingDraft**.

Nếu thay model bằng dữ liệu chỉ nằm trong **viewScope**, dữ liệu đó gắn với vòng đời của view-state. Khi rời state, view scope kết thúc; khi vào lại, không nên giả định dữ liệu cũ vẫn còn. Dữ liệu cần dùng xuyên suốt nhiều bước nên được giữ trong flow scope hoặc scope có vòng đời phù hợp hơn. **conversationScope** chỉ nên dùng khi dữ liệu cần chia sẻ trong conversation gồm flow gốc và các subflow liên quan.

## Kiểm soát field nào được phép bind

Không nên bind mọi thuộc tính của đối tượng nghiệp vụ chỉ vì form có thể gửi chúng. Hãy dùng một form model hoặc DTO dành riêng cho thao tác người dùng và khai báo rõ các thuộc tính được phép bind bằng **binder**.

Ví dụ ở trên chỉ cho phép các thuộc tính **recipient**, **addressLine** và **postalCode** được bind. Những trường như **orderId**, **customerId**, **price**, **status**, **approved**, **ownerId** hoặc **paymentState** không nên được lấy từ request để quyết định nghiệp vụ. Server cần xác định người dùng hiện tại, tải dữ liệu gốc và tính toán các giá trị quan trọng từ nguồn có thẩm quyền.

Một form JSP tương ứng có thể trông như sau:

~~~jsp
<form:form modelAttribute="bookingDraft"
           action="${flowExecutionUrl}"
           method="post">
    <form:label path="recipient">Người nhận</form:label>
    <form:input path="recipient" />

    <form:label path="addressLine">Địa chỉ</form:label>
    <form:input path="addressLine" />

    <form:label path="postalCode">Mã bưu chính</form:label>
    <form:input path="postalCode" />

    <button type="submit" name="_eventId_continue">
        Tiếp tục
    </button>
    <button type="submit" name="_eventId_backToCart">
        Quay lại giỏ hàng
    </button>
</form:form>
~~~

URL **flowExecutionUrl** giữ thông tin để request tiếp tục đúng flow execution. Tham số **_eventId_continue** phát event **continue**; tham số **_eventId_backToCart** phát event **backToCart**. Các thuộc tính được khai báo trong binder là danh sách cho phép của model binding ở view-state này.

Binder giúp giới hạn những trường được bind, nhưng không thay thế kiểm tra quyền và validation nghiệp vụ. Một request có thể bị sửa thủ công; server vẫn phải kiểm tra người dùng có quyền sửa đơn hàng đó hay không, đơn còn ở trạng thái cho phép chỉnh sửa không và các giá trị có hợp lệ với quy tắc hiện tại không.

## Điều khiển binding trên transition quay lại

Với view-state có model, Spring Web Flow có thể bind dữ liệu request trước khi xử lý transition. Điều này có nghĩa nút quay lại đặt trong cùng form có thể gửi những giá trị người dùng vừa sửa. Nếu chính sách yêu cầu bỏ dữ liệu của lần submit đó, transition có thể tắt binding và validation bằng các thuộc tính **bind="false"** và **validate="false"**.

Ví dụ, người dùng đang ở bước nhập địa chỉ nhưng muốn quay về giỏ hàng mà không lưu các thay đổi vừa nhập:

~~~xml
<view-state id="shipping"
            view="booking/shipping"
            model="bookingDraft">
    <binder>
        <binding property="recipient" required="true" />
        <binding property="addressLine" required="true" />
        <binding property="postalCode" required="true" />
    </binder>

    <transition on="continue" to="review">
        <evaluate expression="bookingValidator.validateShipping(bookingDraft, messageContext)" />
    </transition>

    <transition on="backToCart"
                to="cart"
                bind="false"
                validate="false" />
</view-state>
~~~

Ở transition **backToCart**, request vẫn phát event điều hướng nhưng model binding và validation của transition này bị tắt. Các giá trị mới chỉ có trong request không được chép vào **bookingDraft** qua transition đó. Transition **continue** vẫn bind dữ liệu và chạy validation như bình thường.

Cách này hữu ích cho thao tác hủy hoặc rời khỏi form. Tuy nhiên, nếu người dùng muốn quay lại bước trước và giữ các giá trị vừa nhập để tiếp tục sau đó, không nên tắt binding cho event đó. Hãy để transition bind theo chính sách đã chọn và kiểm tra validation phù hợp.

Cũng cần kiểm tra phiên bản Spring Web Flow đang dùng và schema cấu hình của dự án khi áp dụng thuộc tính transition. Hành vi binding và validation cần được kiểm thử qua request thực tế, đặc biệt khi form có nhiều nút submit.

## Phân biệt quay lại để sửa và hủy chỉnh sửa

Một tình huống thường gặp là người dùng đã nhập địa chỉ, đi tới màn hình xem lại, rồi chọn sửa địa chỉ. Họ thay đổi địa chỉ nhưng sau đó quyết định hủy lần sửa và quay lại màn hình xem lại với địa chỉ trước đó.

Nếu dùng cùng một đối tượng **bookingDraft**, dữ liệu sẽ bị thay đổi ngay khi form được bind. Muốn có thể hủy lần sửa, ứng dụng cần lưu một bản sao trước khi người dùng bắt đầu chỉnh sửa. Bản sao này chỉ cần chứa các trường thuộc bước đang sửa.

Một lớp DTO có thể hỗ trợ sao chép và phục hồi như sau:

~~~java
public class BookingDraft {
    private String recipient;
    private String addressLine;
    private String postalCode;
    private String deliveryMethod;
    private String shippingQuoteId;

    public ShippingDetails copyShippingDetails() {
        return new ShippingDetails(
                recipient,
                addressLine,
                postalCode,
                deliveryMethod,
                shippingQuoteId);
    }

    public void restoreShippingDetails(ShippingDetails saved) {
        this.recipient = saved.getRecipient();
        this.addressLine = saved.getAddressLine();
        this.postalCode = saved.getPostalCode();
        this.deliveryMethod = saved.getDeliveryMethod();
        this.shippingQuoteId = saved.getShippingQuoteId();
    }

    // Các getter và setter phục vụ form binding được lược bỏ.
}
~~~

**ShippingDetails** ở đây là một DTO bất biến hoặc bản sao độc lập của các trường giao hàng. Nếu DTO có collection hoặc đối tượng lồng nhau có thể thay đổi, cần sao chép sâu các phần tử có thể bị sửa. Sao chép tham chiếu nông không tạo ra bản sao độc lập: thay đổi đối tượng con vẫn có thể làm thay đổi cả bản sao dự phòng.

Có thể dùng action-state để tạo bản sao trước khi vào màn hình chỉnh sửa và phục hồi khi người dùng chọn bỏ thay đổi:

~~~xml
<view-state id="review" view="booking/review">
    <transition on="editShipping" to="prepareShippingEdit" />
    <transition on="confirm" to="confirmed">
        <evaluate expression="bookingService.confirm(bookingDraft)" />
    </transition>
</view-state>

<action-state id="prepareShippingEdit">
    <evaluate expression="bookingDraft.copyShippingDetails()"
              result="flowScope.shippingBackup" />
    <transition to="shipping" />
</action-state>

<view-state id="shipping"
            view="booking/shipping"
            model="bookingDraft">
    <binder>
        <binding property="recipient" />
        <binding property="addressLine" />
        <binding property="postalCode" />
        <binding property="deliveryMethod" />
    </binder>

    <transition on="saveShipping" to="review">
        <evaluate expression="shippingService.refreshQuote(bookingDraft)" />
    </transition>

    <transition on="discardShippingEdits"
                to="restoreShipping"
                bind="false"
                validate="false" />
</view-state>

<action-state id="restoreShipping">
    <evaluate expression="bookingDraft.restoreShippingDetails(flowScope.shippingBackup)" />
    <transition to="review" />
</action-state>
~~~

Khi người dùng chọn **editShipping**, flow chụp lại các trường giao hàng trước khi mở form chỉnh sửa. Nếu chọn **saveShipping**, flow giữ dữ liệu đã bind và cập nhật báo giá vận chuyển. Nếu chọn **discardShippingEdits**, transition bỏ qua binding của request hiện tại, sau đó action-state phục hồi các trường từ bản sao. Đây là hai ý định khác nhau và nên có event riêng.

Trong triển khai thực tế, cần xóa hoặc thay thế **shippingBackup** sau khi hoàn tất chỉnh sửa để tránh dùng lại bản sao cũ ở lần sửa tiếp theo. Có thể tạo backup mới mỗi lần bắt đầu chỉnh sửa. Nếu flow cho phép nhiều vùng dữ liệu được sửa độc lập, hãy lưu backup theo từng vùng thay vì sao chép toàn bộ đối tượng không cần thiết.

## Làm mới dữ liệu phụ thuộc khi một trường thay đổi

Một thay đổi ở bước trước có thể làm cho dữ liệu của bước sau không còn đúng. Ví dụ, địa chỉ giao hàng quyết định phí vận chuyển, phương thức giao hàng ảnh hưởng ngày dự kiến, còn tổng tiền phụ thuộc giá và khuyến mãi hiện tại.

Khi người dùng thay đổi địa chỉ, không nên giữ nguyên một báo giá vận chuyển đã tính cho địa chỉ cũ. Cần xóa hoặc đánh dấu dữ liệu dẫn xuất là cũ, sau đó tính lại trước khi xác nhận đơn.

| Trường được sửa | Dữ liệu phụ thuộc | Hành động cần thực hiện |
|---|---|---|
| Địa chỉ giao hàng | Báo giá, vùng giao hàng, thời gian dự kiến | Vô hiệu hóa báo giá cũ và yêu cầu tính lại |
| Phương thức vận chuyển | Phí vận chuyển, ngày giao dự kiến | Tính lại phí và ngày giao |
| Danh sách sản phẩm | Tổng tiền, thuế, khuyến mãi, tồn kho | Tính lại từ dữ liệu sản phẩm hiện tại |
| Mã khuyến mãi | Mức giảm, điều kiện áp dụng, tổng tiền | Kiểm tra lại hiệu lực và phạm vi áp dụng |
| Thông tin thanh toán | Payment intent hoặc lần thử thanh toán | Kiểm tra trạng thái hiện tại; tạo lần thử mới theo quy tắc dịch vụ nếu cần |

Một service có thể làm mới dữ liệu phụ thuộc sau khi địa chỉ được lưu:

~~~java
public void refreshQuote(BookingDraft draft) {
    draft.setShippingQuoteId(null);

    ShippingQuote quote = shippingService.quote(
            draft.getAddressLine(),
            draft.getPostalCode(),
            draft.getDeliveryMethod());

    draft.setShippingQuoteId(quote.getId());
    draft.setEstimatedShippingFee(quote.getAmount());
}
~~~

Đây là ví dụ rút gọn; service thực tế cần kiểm tra dữ liệu địa chỉ, quyền truy cập, vùng giao hàng và lỗi từ hệ thống báo giá. Không tin phí vận chuyển hoặc tổng tiền được gửi từ trình duyệt. Khi xác nhận, server nên tải lại hoặc kiểm tra báo giá còn hiệu lực và tính tổng tiền theo nguồn dữ liệu có thẩm quyền.

## Giữ bản nháp tách biệt với dữ liệu đã xác nhận

Một thiết kế an toàn là giữ dữ liệu người dùng đang chỉnh sửa trong một **draft DTO** thuộc flow scope. Khi người dùng xác nhận ở bước cuối, service mới kiểm tra lại và ghi thay đổi vào hệ thống nghiệp vụ trong transaction thích hợp.

Mô hình này giúp phân biệt:

- **Draft:** dữ liệu đang nhập hoặc chỉnh sửa, có thể được giữ, sửa tiếp hoặc bỏ.
- **Validated data:** dữ liệu đã qua kiểm tra ở bước hiện tại nhưng vẫn có thể cần xác minh lại trước khi xác nhận cuối.
- **Committed data:** dữ liệu đã được ghi nhận chính thức theo quy tắc nghiệp vụ.

Nếu ứng dụng phải lưu dữ liệu tạm vào cơ sở dữ liệu ở từng bước, hãy dùng trạng thái nháp rõ ràng, quyền sở hữu theo người dùng và quy tắc hết hạn. Thao tác xác nhận cần idempotent hoặc có cơ chế chống gửi lặp, vì người dùng có thể nhấn nút nhiều lần hoặc trình duyệt gửi lại request. Việc quay lại một view-state không tự rollback các ghi nhận đã commit trước đó.

## Validation khi người dùng quay lại

Khi quay lại một bước đã nhập trước đó, dữ liệu có thể đã cũ hoặc các điều kiện nghiệp vụ có thể đã thay đổi. Do đó, validation nên được thực hiện ở các thời điểm phù hợp:

- Khi người dùng rời bước nhập bằng event tiếp tục, kiểm tra các trường bắt buộc và định dạng của bước đó.
- Khi người dùng quay lại và sửa dữ liệu, kiểm tra lại những trường bị ảnh hưởng trước khi chuyển tiếp.
- Khi xác nhận cuối, kiểm tra lại các điều kiện có thể thay đổi theo thời gian như tồn kho, giá, quyền sở hữu và trạng thái thanh toán.
- Khi bỏ thay đổi, không chạy validation trên dữ liệu form chưa được bind; thay vào đó khôi phục bản sao hợp lệ trước đó.

Validation của form và kiểm tra nghiệp vụ ở service có mục đích khác nhau. Form validation giúp phản hồi nhanh cho người dùng. Service vẫn phải kiểm tra điều kiện quan trọng trước khi ghi dữ liệu chính thức, vì request có thể bị gửi ngoài giao diện hoặc trạng thái hệ thống đã thay đổi.

## Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Quay lại nhưng dữ liệu vừa nhập biến mất | Dữ liệu chỉ nằm trong view scope hoặc transition không bind | Dùng model có vòng đời flow scope khi cần giữ dữ liệu; kiểm tra thuộc tính bind của transition |
| Nhấn quay lại nhưng dữ liệu chưa xác nhận vẫn bị lưu vào draft | Transition quay lại vẫn bind request | Tắt binding cho transition điều hướng nếu chính sách là bỏ dữ liệu request đó |
| Hủy chỉnh sửa nhưng dữ liệu cũ không trở lại | Không lưu bản sao trước khi vào màn hình sửa | Tạo backup độc lập và phục hồi các trường thuộc bước chỉnh sửa |
| Đổi địa chỉ nhưng phí giao hàng không đổi | Dữ liệu dẫn xuất chưa được làm mới | Vô hiệu hóa báo giá cũ và tính lại ở server |
| Người dùng sửa được trạng thái hoặc giá | Binder cho phép bind trường nhạy cảm hoặc dùng entity trực tiếp | Dùng DTO, allow-list thuộc tính và tính lại trường nhạy cảm ở server |
| Validation ngăn người dùng rời form bằng nút hủy | Transition hủy vẫn chạy validation | Tắt validation trên transition điều hướng/hủy khi phù hợp |
| Dữ liệu đã ghi vào DB vẫn còn sau khi quay lại | Ghi nghiệp vụ đã commit trước đó | Dùng draft hoặc thiết kế hành động bù/hoàn tác rõ ràng |

Khi điều tra, hãy kiểm tra model được khai báo trên view-state, scope của đối tượng, các field trong binder, event mà nút gửi và chính sách bind/validate của transition. Sau đó kiểm tra service có ghi dữ liệu chính thức ở bước trước hay không. Việc chỉ sửa nút Back thường không giải quyết được nguyên nhân nếu dữ liệu đã được ghi vào hệ thống nghiệp vụ.

## Kiểm thử các nhánh quay lại

Một flow nhiều bước cần kiểm thử cả trường hợp giữ và bỏ thay đổi. Kịch bản tối thiểu cho flow đặt hàng có thể gồm:

1. Khởi chạy flow và nhập địa chỉ hợp lệ.
2. Tiếp tục tới màn hình xem lại; xác nhận địa chỉ và báo giá được hiển thị.
3. Quay lại bằng event **editShipping**; xác nhận dữ liệu đã lưu trong draft vẫn được điền vào form.
4. Sửa địa chỉ rồi chọn lưu; xác nhận dữ liệu mới được giữ và báo giá cũ được tính lại.
5. Bắt đầu một lần chỉnh sửa khác rồi chọn **discardShippingEdits**; xác nhận dữ liệu trước lần sửa được phục hồi.
6. Từ form có dữ liệu chưa hợp lệ, chọn event quay lại có binding và validation tắt; xác nhận người dùng vẫn điều hướng được theo chính sách.
7. Thử gửi thêm các trường không nằm trong binder; xác nhận chúng không làm thay đổi thuộc tính nhạy cảm của model.
8. Thay đổi tồn kho hoặc giá ở hệ thống nghiệp vụ trước khi xác nhận; xác nhận service kiểm tra lại trạng thái hiện tại.

Với mỗi kịch bản, nên kiểm tra cả giá trị hiển thị trong view và giá trị ở phía server. Nếu chỉ kiểm tra giao diện, có thể bỏ sót việc một trường nhạy cảm đã bị bind hoặc dữ liệu cũ vẫn còn trong flow scope.

## Checklist thiết kế

Trước khi hoàn thiện flow nhiều bước, hãy rà soát:

- [ ] Đã xác định trường nào được giữ khi quay lại, trường nào bị bỏ.
- [ ] Dữ liệu cần đi qua nhiều state được giữ trong scope có vòng đời phù hợp.
- [ ] Model form là DTO phù hợp, không bind trực tiếp toàn bộ entity nghiệp vụ.
- [ ] Binder chỉ cho phép các thuộc tính người dùng được sửa.
- [ ] Event quay lại, lưu, hủy chỉnh sửa có ý nghĩa và chính sách rõ ràng.
- [ ] Transition điều hướng đã chọn đúng hành vi bind và validate.
- [ ] Có backup độc lập nếu cần khôi phục dữ liệu trước khi sửa.
- [ ] Dữ liệu phụ thuộc được vô hiệu hóa hoặc tính lại khi đầu vào thay đổi.
- [ ] Service xác minh lại quyền và trạng thái trước khi ghi dữ liệu chính thức.
- [ ] Có kiểm thử cho cả giữ, bỏ, validation lỗi và dữ liệu nghiệp vụ thay đổi.

## Ghi nhớ

- Binding có thể cập nhật flow model trước khi transition điều hướng được xử lý; nút quay lại trong form cần có chính sách dữ liệu rõ ràng.
- Dùng flow scope cho dữ liệu nháp cần tồn tại qua nhiều view-state; view scope gắn với vòng đời của một view-state.
- Dùng binder để giới hạn thuộc tính được phép bind. Không nhận giá, trạng thái, quyền hoặc định danh có thẩm quyền từ request.
- Có thể dùng **bind="false"** và **validate="false"** cho transition điều hướng cần bỏ dữ liệu request hiện tại, sau khi xác nhận cấu hình phù hợp với phiên bản dự án.
- Phân biệt quay lại để tiếp tục sửa với hủy chỉnh sửa; dùng bản sao độc lập nếu cần phục hồi dữ liệu trước lần sửa.
- Khi dữ liệu đầu vào thay đổi, làm mới dữ liệu phụ thuộc và xác minh lại nghiệp vụ ở phía server trước khi xác nhận.

