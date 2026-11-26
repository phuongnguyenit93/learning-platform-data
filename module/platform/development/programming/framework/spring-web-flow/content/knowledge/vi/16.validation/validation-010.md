# Tắt validation cho sự kiện bằng validate=false

> **Chương:** Kiểm tra dữ liệu  
> **Module:** SPRING_WEB_FLOW

Trong module **SPRING_WEB_FLOW**, bạn học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; tổ chức form binding, validation, scope và phiên; tích hợp Spring Web Flow với Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Ở chương **Kiểm tra dữ liệu**, bài này tập trung vào một tình huống thường gặp: người dùng đang nhập form nhưng muốn rời màn hình bằng một thao tác như Hủy hoặc Quay lại, dù các trường hiện tại chưa hợp lệ.

Spring Web Flow cho phép cấu hình **validate="false"** trên một transition của view-state để không chạy bước validation gắn với transition đó. Nhờ vậy, ứng dụng có thể cho phép một event điều hướng như cancel đi qua mà không yêu cầu form phải hợp lệ. Việc tắt validation cần gắn đúng event và đúng mục đích; các thao tác lưu hoặc xác nhận nghiệp vụ vẫn cần kiểm tra dữ liệu ở nơi phù hợp.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích validate của transition trong view-state có tác dụng gì.
- Cấu hình validate="false" cho một event cụ thể như cancel hoặc back.
- Phân biệt event được bỏ qua validation với toàn bộ quá trình binding và kiểm tra nghiệp vụ.
- Thiết kế riêng nhánh lưu dữ liệu và nhánh rời form.
- Kiểm thử cả trường hợp dữ liệu hợp lệ, không hợp lệ và thao tác hủy.
- Tránh dùng validate="false" để che lỗi hoặc bỏ qua các bất biến nghiệp vụ.

## 1. Vì sao cần tắt validation cho một event?

Hãy hình dung người dùng mở màn hình chỉnh sửa đặt chỗ. Họ thay đổi ngày, xóa nội dung một trường bắt buộc rồi nhận ra muốn hủy thao tác. Khi bấm Hủy, ứng dụng cần quay lại màn hình trước hoặc bỏ phần chỉnh sửa đang thực hiện.

Nếu event Hủy cũng kích hoạt validation như event Lưu, người dùng có thể bị giữ lại trên form vì trường bắt buộc đang trống. Đây là trải nghiệm không hợp lý: thao tác hủy không cần dữ liệu mới phải đạt quy tắc để được thực hiện.

Ta cần phân biệt mục đích của từng event:

| Event | Mục đích | Có cần validation của form? |
|---|---|---|
| **save** | Lưu thay đổi | Có, vì dữ liệu cần hợp lệ trước khi lưu. |
| **continue** | Sang bước kế tiếp | Thường có, nếu bước kế tiếp phụ thuộc dữ liệu vừa nhập. |
| **cancel** | Bỏ thay đổi và rời form | Thường không cần validation của form. |
| **back** | Quay về bước trước | Tùy nghiệp vụ; có thể không cần validation nếu chỉ rời màn hình. |
| **preview** | Xem trước dữ liệu | Phụ thuộc việc bản xem trước có chấp nhận dữ liệu chưa hoàn chỉnh hay không. |

Validation là bước kiểm tra dữ liệu theo quy tắc được cấu hình cho view-state hoặc model. Nó phù hợp với event cần dùng dữ liệu đó để tiếp tục nghiệp vụ. Một event chỉ có nhiệm vụ rời màn hình có thể được thiết kế để bỏ qua bước validation này.

## 2. Cấu hình validate="false" trên transition

Thuộc tính **validate** được đặt trực tiếp trên transition của view-state. Ví dụ:

~~~xml
<view-state id="editBooking" model="booking">
    <transition on="save" to="reviewBooking"/>
    <transition on="cancel" to="bookingDetails" validate="false"/>
</view-state>
~~~

Trong ví dụ:

- Khi nhận event **save**, flow đi theo transition mặc định có validation của view-state. Nếu dữ liệu không hợp lệ, flow giữ người dùng ở màn hình chỉnh sửa và hiển thị lỗi.
- Khi nhận event **cancel**, transition có **validate="false"**, nên bước validation gắn với transition này được bỏ qua và flow đi đến **bookingDetails**.

Thuộc tính này thuộc về transition. Không đặt nó trên nút HTML, không đặt trên action-state và cũng không phải một cờ toàn cục để tắt validation cho toàn bộ flow.

Nếu không khai báo validate, transition sử dụng hành vi validation mặc định của view-state và cấu hình liên quan. Trong ví dụ trên, ta chỉ ghi rõ ngoại lệ cho event cancel; event save tiếp tục theo quy tắc validation thông thường.

### Form gửi event tương ứng

View cần gửi đúng event id đã khai báo trong flow:

~~~html
<form method="post">
    <label for="date">Ngày đặt</label>
    <input id="date" name="date" type="date"/>

    <label for="guestCount">Số khách</label>
    <input id="guestCount" name="guestCount" type="number"/>

    <button type="submit" name="_eventId_save" value="save">
        Lưu
    </button>

    <button type="submit" name="_eventId_cancel" value="cancel">
        Hủy
    </button>
</form>
~~~

Ví dụ HTML được rút gọn để minh họa hai event. Trong ứng dụng thật, form phải gửi đến URL của flow execution hiện tại và các trường phải được binding theo cấu hình view-state. Điều quan trọng là event id được gửi từ nút phải khớp với giá trị **on** trong flow definition.

Nếu nút Hủy vô tình gửi event save, transition có validation vẫn được chọn. Khi điều tra, hãy kiểm tra payload của request trong Developer Tools để xác nhận event thực tế.

## 3. validate="false" ảnh hưởng đến điều gì?

Cần hiểu đúng phạm vi của thuộc tính này để tránh kỳ vọng sai.

**validate="false" yêu cầu Spring Web Flow bỏ qua bước validation gắn với transition đó.** Nó không có nghĩa mọi xử lý dữ liệu trong request đều bị vô hiệu hóa.

| Cơ chế | validate="false" có tự động tắt không? | Giải thích |
|---|---|---|
| Validation của view-state/transition | Có, đối với transition được đánh dấu | Đây là tác dụng chính của thuộc tính. |
| Gửi form và xử lý request | Không | Trình duyệt vẫn gửi request để phát event. |
| Form binding / chuyển đổi kiểu | Không nên giả định là bị tắt | Việc binding phụ thuộc binder và vòng đời xử lý view; cần kiểm tra riêng nếu dữ liệu có lỗi chuyển kiểu. |
| Validation trong service nghiệp vụ | Không | Service vẫn thực hiện các kiểm tra mà code gọi đến. |
| Kiểm tra quyền truy cập | Không | Authorization vẫn phải được thực hiện ở phía máy chủ. |
| Ràng buộc cơ sở dữ liệu | Không | Constraint và transaction vẫn hoạt động theo cấu hình lưu dữ liệu. |

Ví dụ, người dùng nhập chữ vào trường số rồi bấm Hủy. validate="false" bỏ qua validation của transition Hủy, nhưng không nên dựa vào đó để kết luận mọi lỗi chuyển đổi dữ liệu trong quá trình binding đều biến mất. Hành vi binding cụ thể còn phụ thuộc cách view-state và binder xử lý request.

Tương tự, nếu action của transition Hủy gọi service xóa dữ liệu, các kiểm tra quyền và quy tắc nghiệp vụ trong service vẫn cần được thực hiện. validate="false" không phải cơ chế bảo mật hoặc cơ chế cho phép bỏ qua các bất biến dữ liệu.

## 4. Tách nhánh Lưu và Hủy trong cùng một view-state

Một thiết kế tốt thường phân biệt rõ hai ý định:

- Lưu: dữ liệu cần hợp lệ, sau đó mới gọi logic ghi dữ liệu.
- Hủy: rời form hoặc khôi phục trạng thái trước đó, không yêu cầu dữ liệu đang nhập phải hợp lệ.

Ví dụ flow:

~~~xml
<view-state id="editProfile" model="profile">
    <transition on="save" to="saveProfile"/>
    <transition on="cancel" to="profileDetails" validate="false"/>
</view-state>

<action-state id="saveProfile">
    <evaluate expression="profileService.save(flowScope.profile)"/>
    <transition on="success" to="profileDetails"/>
    <transition on="error" to="editProfile"/>
</action-state>
~~~

Luồng xử lý:

1. Người dùng mở view-state **editProfile**.
2. Người dùng chỉnh sửa các trường.
3. Nếu bấm **save**, view-state thực hiện validation theo cấu hình. Khi hợp lệ, flow đi đến action-state **saveProfile**.
4. Action gọi service lưu dữ liệu và trả về kết quả.
5. Nếu bấm **cancel**, transition được đánh dấu validate="false" cho phép flow rời form mà không chạy validation của transition này.

Ví dụ trên mô tả cấu trúc điều khiển. Cách quản lý đối tượng profile, transaction và phục hồi dữ liệu khi hủy cần được triển khai theo ứng dụng. Đặc biệt, nếu form đang sửa trực tiếp một đối tượng dùng chung trong flow scope, thao tác Hủy có thể không tự khôi phục giá trị cũ. Muốn hủy thật sự, hãy dùng bản sao form/model hoặc cơ chế lưu trạng thái ban đầu để bỏ các thay đổi chưa lưu.

### Hủy không đồng nghĩa với xóa dữ liệu đã lưu

Một event cancel thường có nghĩa là bỏ phần thay đổi chưa lưu trong lần chỉnh sửa. Nó không nên gọi cùng action ghi dữ liệu như event save. Nếu nghiệp vụ cần xóa một bản ghi đã tồn tại, hãy mô hình hóa một event và một thao tác xóa riêng, có xác nhận và kiểm tra quyền thích hợp.

## 5. Dùng validate="false" cho back hoặc close

Một số flow nhiều bước cho phép người dùng quay lại bước trước ngay cả khi form hiện tại chưa hoàn chỉnh. Ví dụ, người dùng đang nhập địa chỉ giao hàng nhưng muốn quay lại chọn phương thức vận chuyển.

~~~xml
<view-state id="enterAddress" model="addressForm">
    <transition on="continue" to="reviewAddress"/>
    <transition on="back" to="chooseDelivery" validate="false"/>
</view-state>
~~~

Event back được miễn validation của transition vì mục đích là điều hướng. Tuy nhiên, quyết định có giữ lại dữ liệu người dùng đã nhập hay không phải được thiết kế riêng.

Có hai hành vi thường gặp:

- **Giữ bản nháp:** lưu dữ liệu tạm để người dùng quay lại form và tiếp tục.
- **Bỏ thay đổi:** phục hồi dữ liệu từ bản gốc hoặc tạo form mới khi người dùng quay lại.

Không để việc chọn validate="false" quyết định ngầm hành vi dữ liệu. Hãy xác định rõ vòng đời model, scope và điểm ghi dữ liệu.

## 6. Tránh tắt validation cho event cần dữ liệu hợp lệ

Không nên đặt validate="false" cho mọi transition chỉ để người dùng ít gặp thông báo lỗi. Ví dụ sau có thể nguy hiểm:

~~~xml
<view-state id="editPayment" model="paymentForm">
    <transition on="submit" to="chargePayment" validate="false"/>
</view-state>
~~~

Nếu action chargePayment dựa vào các trường đã nhập mà không tự xác thực lại, dữ liệu thiếu hoặc sai định dạng có thể đi vào quy trình thanh toán. Validation của view-state là một lớp bảo vệ hữu ích; bỏ qua nó đòi hỏi một thiết kế kiểm tra thay thế rõ ràng.

Với event thực hiện nghiệp vụ, hãy giữ validation hoặc chủ động gọi validator tương ứng trước khi thực hiện hành động. Các quy tắc quan trọng cần được bảo vệ ở tầng service, vì client có thể gửi request không theo đúng đường đi giao diện dự kiến.

Một cách phân loại hữu ích:

| Nhóm event | Ví dụ | Cách thiết kế |
|---|---|---|
| Điều hướng rời form | cancel, close, back | Có thể dùng validate="false" nếu không cần dữ liệu form. |
| Gửi dữ liệu để xử lý | save, submit, confirm | Giữ validation và kiểm tra nghiệp vụ. |
| Quyết định dựa trên dữ liệu chưa hoàn chỉnh | preview, calculateDraft | Xác định rõ trường nào bắt buộc; có thể dùng validator riêng hoặc nhánh xử lý bản nháp. |
| Hành động nhạy cảm | pay, approve, delete | Kiểm tra dữ liệu, quyền và điều kiện nghiệp vụ ở phía máy chủ. |

## 7. Xử lý dữ liệu và phục hồi khi người dùng hủy

Một tình huống khó thường gặp là dữ liệu form đã được binding vào model trước khi flow thực hiện transition. Nếu người dùng bấm Hủy, dữ liệu chưa lưu có thể vẫn nằm trong đối tượng mà flow đang giữ.

Giả sử flow scope chứa đối tượng Booking:

~~~java
Booking booking =
    (Booking) context.getFlowScope().get("booking");
~~~

Nếu view binding trực tiếp vào booking, các giá trị người dùng nhập có thể thay đổi đối tượng này trong quá trình xử lý form. Khi cancel, chỉ chuyển về state trước không đảm bảo các giá trị cũ tự khôi phục.

Một thiết kế an toàn hơn là dùng một đối tượng form riêng:

~~~java
Booking original =
    bookingService.findById(bookingId);

BookingForm form = BookingForm.from(original);

context.getFlowScope().put("originalBooking", original);
context.getFlowScope().put("bookingForm", form);
~~~

Khi lưu, service nhận form, xác thực lại dữ liệu và cập nhật bản ghi theo transaction. Khi hủy, flow có thể bỏ bookingForm hoặc tạo lại form từ originalBooking. Không ghi đè bản ghi nghiệp vụ chỉ vì người dùng đã thay đổi trường trên giao diện.

Ví dụ xử lý hủy trong action:

~~~java
public Event cancelEdit(RequestContext context) throws Exception {
    context.getFlowScope().remove("bookingForm");
    return success();
}
~~~

Đây là minh họa cho việc loại bỏ bản nháp khỏi scope. API cụ thể và nơi đặt action phụ thuộc flow definition của ứng dụng. Nếu form nằm trong view scope hoặc conversation scope, hãy xử lý đúng scope chứa dữ liệu.

## 8. Kiểm thử transition có validate="false"

Cần kiểm thử hành vi của từng event, không chỉ kiểm tra XML có thuộc tính validate="false".

| Kịch bản | Thao tác | Kết quả mong đợi |
|---|---|---|
| Lưu với dữ liệu hợp lệ | Nhập đủ trường rồi bấm Lưu | Validation đạt; flow đến action lưu dữ liệu. |
| Lưu với dữ liệu không hợp lệ | Bỏ trống trường bắt buộc rồi bấm Lưu | Flow ở lại form và hiển thị lỗi. |
| Hủy với dữ liệu không hợp lệ | Bỏ trống trường bắt buộc rồi bấm Hủy | Transition cancel được thực hiện mà không chạy validation của transition đó. |
| Quay lại với dữ liệu chưa hoàn chỉnh | Bấm Back | Flow quay về state trước theo thiết kế. |
| Hủy sau khi đã thay đổi form | Thay đổi dữ liệu rồi bấm Hủy | Bản ghi đã lưu không bị cập nhật ngoài ý muốn; bản nháp được giữ hoặc bỏ đúng yêu cầu. |
| Request gửi event sai | Form gửi event không khớp transition | Flow không đi theo nhánh cancel dự kiến; cần kiểm tra tên event và request payload. |
| Người dùng không có quyền | Gửi event cancel hoặc save bằng tài khoản không có quyền | Kiểm tra quyền vẫn được thực hiện ở phía máy chủ. |

### Kiểm tra trên trình duyệt

Mở Developer Tools và chọn tab Network. Với mỗi thao tác, xác minh:

1. Request gửi đến URL flow execution hiện tại.
2. Payload có event id đúng, ví dụ **_eventId_cancel** hoặc **_eventId_save**.
3. Response và trang sau thao tác phù hợp với transition mong đợi.
4. Khi Hủy, không có action lưu dữ liệu được gọi ngoài ý muốn.
5. Khi Lưu, lỗi validation được hiển thị nếu dữ liệu không hợp lệ.

Nếu Hủy vẫn bị chặn, kiểm tra transition có đúng event id và thuộc đúng view-state hay không. Nếu Hủy đi được nhưng dữ liệu vẫn thay đổi, kiểm tra binding, model và scope. Nếu Lưu đi qua dù dữ liệu sai, kiểm tra validate mặc định, validator được cấu hình và việc action/service có thực hiện kiểm tra nghiệp vụ hay không.

### Kiểm thử tích hợp flow

Dùng test fixture của phiên bản Spring Web Flow trong dự án để khởi chạy flow, gửi event và kiểm tra state kết quả. Một test hữu ích nên xác nhận cả việc validator có được gọi hay không và state đích sau event.

Không chỉ assert rằng cancel đi đến state kế tiếp. Hãy đặt dữ liệu không hợp lệ có thể kích hoạt validator, gửi cancel và xác nhận flow vẫn rời view-state. Sau đó gửi save với cùng dữ liệu để xác nhận validation vẫn ngăn việc chuyển tiếp.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hủy vẫn hiển thị lỗi validation | Event gửi lên không phải event có validate="false" | Kiểm tra tên event trong form và thuộc tính on của transition. |
| Đã thêm validate="false" nhưng không có tác dụng | Thuộc tính đặt sai transition hoặc sai view-state | Đặt thuộc tính trên đúng transition nhận event cần bỏ validation. |
| Lưu không còn kiểm tra dữ liệu | validate="false" bị áp dụng nhầm vào transition save | Bật validation lại cho event lưu và kiểm tra validator. |
| Hủy xong dữ liệu vẫn bị thay đổi | Form binding đã cập nhật model dùng chung | Dùng form object riêng hoặc khôi phục snapshot khi hủy. |
| Hủy vẫn gặp lỗi chuyển kiểu | Binding/conversion có thể xảy ra độc lập với validation | Kiểm tra binder, kiểu dữ liệu và cách xử lý request của view-state. |
| Service vẫn lưu dữ liệu khi hủy | Hai event cùng gọi logic ghi hoặc action bị gọi nhầm | Tách nhánh cancel khỏi action save và kiểm tra log. |
| Người dùng có thể bỏ qua quy tắc nghiệp vụ | Chỉ dựa vào validation của view | Kiểm tra bất biến và quyền trong service phía máy chủ. |

Khi điều tra, lần theo thứ tự: event thực tế, transition được chọn, validation của view-state, binding của model và action/service được gọi. Cách này giúp xác định chính xác phần xử lý gây ra hành vi sai.

## 10. Checklist thiết kế

- [ ] Chỉ đặt validate="false" trên transition thực sự cần bỏ validation.
- [ ] Event id trong view khớp với thuộc tính on của transition.
- [ ] Event save/submit/confirm vẫn được validation phù hợp.
- [ ] Event cancel/back chỉ điều hướng và không gọi nhầm action ghi dữ liệu.
- [ ] Đã phân biệt validation với form binding và chuyển đổi kiểu.
- [ ] Đã xác định dữ liệu bản nháp được giữ hay bỏ khi rời form.
- [ ] Service vẫn kiểm tra dữ liệu, quyền và bất biến nghiệp vụ.
- [ ] Đã kiểm thử cancel với dữ liệu không hợp lệ.
- [ ] Đã kiểm thử save với dữ liệu không hợp lệ để xác nhận validation vẫn hoạt động.
- [ ] Đã kiểm tra request, response, state và tác động dữ liệu trên trình duyệt hoặc test tích hợp.

## Kết luận

**validate="false"** cho phép một transition của view-state bỏ qua bước validation gắn với transition đó. Đây là lựa chọn phù hợp cho event điều hướng như cancel hoặc back khi dữ liệu form chưa hoàn chỉnh. Hãy giới hạn nó ở đúng event, giữ validation cho thao tác cần dữ liệu hợp lệ, xử lý riêng bản nháp khi hủy và luôn thực hiện kiểm tra nghiệp vụ cùng phân quyền ở phía máy chủ.
