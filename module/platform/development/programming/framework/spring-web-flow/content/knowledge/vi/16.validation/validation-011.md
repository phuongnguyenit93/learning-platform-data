# Tác động khác nhau của bind=false và validate=false

Trong chương **Kiểm tra dữ liệu**, một transition của Spring Web Flow có thể vừa nhận dữ liệu từ form, vừa kiểm tra dữ liệu trước khi chuyển sang state tiếp theo. Hai thuộc tính `bind` và `validate` điều khiển hai bước khác nhau trong quá trình đó. Hiểu đúng sự khác nhau giúp ta thiết kế các nút Gửi, Lưu nháp, Quay lại và Hủy mà không vô tình làm mất dữ liệu hoặc chặn người dùng ở một biểu mẫu chưa hoàn chỉnh.

Trong module **SPRING_WEB_FLOW**, form binding và validation là một phần của hành trình nhiều bước được mô hình hóa bằng state, event và transition. Bài học này giải thích tác động của `bind="false"` và `validate="false"`, cách kết hợp hai thuộc tính, cách xử lý lỗi binding và validation, cùng các tình huống nên dùng trong flow thực tế.

## 1. Binding và validation là hai bước riêng biệt

Khi người dùng gửi form từ một `view-state`, Spring Web Flow có thể thực hiện hai công việc trước khi chuyển state:

1. **Binding**: lấy các giá trị trong request, chuyển đổi kiểu dữ liệu nếu cần và gán vào các thuộc tính được phép của model object.
2. **Validation**: kiểm tra model sau khi binding để xác định dữ liệu có thỏa các quy tắc hay không.

Ví dụ, người dùng nhập thông tin đặt chỗ:

- `customerName` là chuỗi tên khách hàng.
- `startDate` là ngày bắt đầu.
- `endDate` là ngày kết thúc.

Binding đưa các giá trị gửi lên vào object `booking`. Quá trình này có thể cần chuyển chuỗi ngày thành kiểu ngày. Sau đó validation kiểm tra tên không được để trống, ngày bắt đầu phải hợp lệ và ngày kết thúc không được trước ngày bắt đầu.

Hai bước có quan hệ thứ tự nhưng có mục đích khác nhau:

| Bước | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Binding | Giá trị request có được chuyển vào đúng thuộc tính model không? | Chuỗi `abc` không chuyển được thành số hoặc ngày |
| Validation | Giá trị model sau binding có thỏa quy tắc dữ liệu không? | Ngày kết thúc trước ngày bắt đầu |

Lỗi chuyển đổi kiểu thường được ghi nhận trong quá trình binding. Lỗi validation phát sinh khi validator kiểm tra các giá trị đã có trong model. Vì vậy, tắt validation không đồng nghĩa với tắt binding hoặc chuyển đổi kiểu.

## 2. Ý nghĩa của bind và validate trên transition

Spring Web Flow cho phép điều khiển riêng hai bước bằng thuộc tính trên transition:

- `bind="false"`: bỏ qua việc binding các tham số request vào model cho transition đó.
- `validate="false"`: bỏ qua bước validation model cho transition đó.

Nếu không khai báo, hành vi mặc định của transition trong view-state là binding và validation được bật. Có thể ghi rõ `bind="true"` và `validate="true"`, nhưng thường không cần vì đó là mặc định.

Ví dụ:

~~~xml
<view-state id="bookingForm" model="booking">
    <transition on="submit" to="reviewBooking" />

    <transition on="saveDraft"
                to="draftSaved"
                validate="false" />

    <transition on="cancel"
                to="cancelled"
                bind="false"
                validate="false" />
</view-state>
~~~

Trong ví dụ:

- `submit` dùng binding và validation mặc định trước khi chuyển đến bước xem lại.
- `saveDraft` vẫn binding dữ liệu người dùng vừa nhập nhưng bỏ qua validation model ở transition này.
- `cancel` bỏ qua cả binding lẫn validation, nên dữ liệu đang nằm trong form không được áp dụng vào model qua request hủy.

Hai thuộc tính này chỉ điều khiển hành vi binding và validation của transition tương ứng. Chúng không thay thế kiểm tra nghiệp vụ trong service, kiểm tra quyền truy cập, ràng buộc cơ sở dữ liệu hoặc các quy tắc an toàn khác.

## 3. Tác động riêng của bind="false"

Khi một transition có `bind="false"`, Spring Web Flow không lấy các trường form của request đó để cập nhật model thông qua binder của view-state.

Giả sử model đang có:

~~~java
Booking booking = new Booking();
booking.setCustomerName("An");
booking.setGuests(2);
~~~

Người dùng sửa form thành tên `Binh` và số khách là `4`, sau đó bấm nút Hủy. Nếu transition hủy đặt `bind="false"`, model vẫn giữ các giá trị trước request:

| Thuộc tính | Model trước request | Form người dùng vừa gửi | Model sau transition bind=false |
|---|---|---|---|
| `customerName` | An | Binh | An |
| `guests` | 2 | 4 | 2 |

Điều này hữu ích khi người dùng bấm Hủy hoặc Quay lại và ứng dụng muốn bỏ các chỉnh sửa chưa được chấp nhận.

### Binding bị bỏ qua không có nghĩa là transition bị bỏ qua

Transition vẫn được xử lý bình thường. Flow vẫn phát event, thực hiện transition action nếu có và đi đến state đích. Ví dụ:

~~~xml
<view-state id="bookingForm" model="booking">
    <transition on="cancel" to="cancelled"
                bind="false"
                validate="false">
        <evaluate expression="bookingService.releaseTemporaryHold(flowScope.holdId)" />
    </transition>
</view-state>

<end-state id="cancelled" view="bookingCancelled" />
~~~

Khi người dùng bấm Hủy, request form không được binding vào model. Tuy nhiên, hành động giải phóng khoản giữ chỗ tạm vẫn được gọi khi transition thực thi. Nếu hành động đó cần dữ liệu từ form, hãy truyền dữ liệu cần thiết bằng một cơ chế phù hợp hoặc dùng giá trị đã được lưu ở flow scope.

### bind=false không phải là cơ chế bảo mật

Thuộc tính này không thay thế việc giới hạn các thuộc tính được phép binding. Nếu transition khác có binding mặc định, người dùng vẫn có thể gửi request thay đổi những thuộc tính được binder cho phép. Hãy cấu hình binder theo allowlist và dùng DTO phù hợp để không bind trực tiếp các trường nhạy cảm.

## 4. Tác động riêng của validate="false"

Khi một transition có `validate="false"`, Spring Web Flow bỏ qua bước validation model gắn với transition đó. Nếu binding vẫn bật, các giá trị request vẫn được đưa vào model và các lỗi chuyển đổi kiểu vẫn có thể phát sinh.

Ví dụ, người dùng đang nhập một bản nháp chưa hoàn chỉnh:

- Tên khách hàng đã có.
- Ngày bắt đầu đã có.
- Ngày kết thúc còn để trống.

Nếu validator yêu cầu ngày kết thúc phải có giá trị, transition mặc định có thể không cho phép rời khỏi view-state vì model chưa hợp lệ. Nhưng với một nút Lưu nháp dùng `validate="false"`, người dùng có thể lưu trạng thái đang nhập để tiếp tục sau.

~~~xml
<view-state id="bookingForm" model="booking">
    <transition on="submit" to="reviewBooking" />

    <transition on="saveDraft"
                to="draftSaved"
                validate="false" />
</view-state>
~~~

Ở đây, `saveDraft` vẫn binding các giá trị gửi lên. Sau đó flow bỏ qua validation model ở transition này và đi đến `draftSaved`.

### Validation bị bỏ qua không có nghĩa dữ liệu đã hợp lệ

Khi dùng `validate="false"`, model có thể chứa dữ liệu thiếu hoặc chưa thỏa quy tắc. Điều đó có thể đúng với một bản nháp, nhưng không được xem là dữ liệu đủ điều kiện để tạo giao dịch hoặc thực hiện nghiệp vụ cuối cùng.

Ở bước xác nhận, cần chạy lại validation đầy đủ:

~~~xml
<view-state id="reviewBooking" model="booking">
    <transition on="confirm" to="commitBooking" />
</view-state>

<action-state id="commitBooking">
    <evaluate expression="bookingService.validateAndConfirm(flowScope.booking)" />
    <transition on="success" to="confirmed" />
    <transition on="invalid" to="bookingForm" />
</action-state>
~~~

Service nghiệp vụ phải kiểm tra lại các quy tắc bắt buộc trước khi ghi nhận kết quả. Việc đã đi qua một transition `validate="false"` không tạo ra trạng thái tin cậy cho dữ liệu.

## 5. Bốn tổ hợp bind và validate

Hai thuộc tính có thể kết hợp thành bốn cách xử lý. Bảng dưới đây giúp chọn đúng hành vi theo mục đích transition.

| bind | validate | Tác động | Tình huống phù hợp |
|---|---|---|---|
| `true` | `true` | Binding request vào model, sau đó validation | Gửi form, tiếp tục đến bước cần dữ liệu hợp lệ |
| `true` | `false` | Binding vẫn diễn ra, validation model bị bỏ qua | Lưu nháp hoặc chuyển bước khi dữ liệu còn chưa hoàn chỉnh |
| `false` | `true` | Không binding request; nếu validation được thực thi thì kiểm tra trạng thái model hiện có | Kiểm tra trạng thái đã có trong model mà không nhận chỉnh sửa từ request |
| `false` | `false` | Bỏ qua cả binding và validation | Hủy hoặc rời màn hình mà không nhận các giá trị đang nhập |

Ở tổ hợp `bind="false" validate="true"`, validator làm việc với model hiện có, không phải những giá trị người dùng vừa gửi trong request. Do đó, nếu mục tiêu là kiểm tra nội dung form vừa gửi, không được tắt binding rồi kỳ vọng validator kiểm tra được những giá trị chưa được đưa vào model.

Tổ hợp này chỉ có ích khi model đã có dữ liệu cần kiểm tra từ trước và transition muốn tránh nhận các thay đổi đang gửi lên. Nếu không có nhu cầu như vậy, hãy dùng cấu hình rõ ràng và đơn giản hơn.

## 6. Ví dụ đầy đủ: gửi form, lưu nháp và hủy

Flow dưới đây minh họa ba hành vi khác nhau trong một view-state:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      start-state="bookingForm">

    <var name="booking" class="com.example.BookingDraft" />

    <view-state id="bookingForm"
                view="bookingForm"
                model="booking">

        <transition on="submit" to="reviewBooking" />

        <transition on="saveDraft"
                    to="draftSaved"
                    validate="false" />

        <transition on="cancel"
                    to="cancelled"
                    bind="false"
                    validate="false" />
    </view-state>

    <view-state id="draftSaved" view="draftSaved">
        <transition on="continue" to="bookingForm"
                    bind="false"
                    validate="false" />
    </view-state>

    <view-state id="reviewBooking" view="reviewBooking">
        <transition on="confirm" to="confirmed" />
        <transition on="edit" to="bookingForm"
                    bind="false"
                    validate="false" />
    </view-state>

    <end-state id="confirmed" view="confirmation" />
    <end-state id="cancelled" view="bookingCancelled" />
</flow>
~~~

Các nút trong view có thể phát event tương ứng:

~~~html
<form method="post">
    <input name="customerName" />
    <input name="startDate" />
    <input name="endDate" />

    <button type="submit" name="_eventId_submit">
        Gửi để kiểm tra
    </button>

    <button type="submit" name="_eventId_saveDraft">
        Lưu nháp
    </button>

    <button type="submit" name="_eventId_cancel">
        Hủy
    </button>
</form>
~~~

Kết quả mong đợi:

- **Gửi để kiểm tra**: binding và validation được thực hiện theo mặc định. Nếu model không hợp lệ, flow giữ người dùng ở form và hiển thị lỗi.
- **Lưu nháp**: binding được thực hiện để giữ nội dung vừa nhập; validation model bị bỏ qua để chấp nhận bản nháp chưa hoàn chỉnh.
- **Hủy**: binding và validation đều bị bỏ qua; flow rời form mà không đưa những chỉnh sửa đang gửi vào model.
- **Quay lại chỉnh sửa**: ví dụ dùng cả hai thuộc tính false để không lấy dữ liệu ngoài ý muốn từ request quay lại.

Ví dụ là khung flow minh họa. Ứng dụng cần bổ sung service lưu bản nháp, xử lý hủy, validator và view tương ứng. Nếu muốn Lưu nháp ghi dữ liệu xuống cơ sở dữ liệu, service vẫn cần xác thực quyền, kiểm tra định dạng tối thiểu và lưu một trạng thái draft rõ ràng.

## 7. Binding lỗi và validation lỗi khác nhau thế nào?

Hai loại lỗi này thường bị nhầm lẫn vì đều có thể khiến người dùng không rời được form.

### Lỗi binding hoặc chuyển đổi kiểu

Giả sử thuộc tính `guests` có kiểu `Integer`, nhưng request gửi chuỗi `many`. Binder không thể chuyển chuỗi đó thành số. Đây là lỗi binding/conversion, không phải lỗi do validator kết luận số khách không hợp lệ.

Nếu transition có `bind="true"`, lỗi chuyển đổi có thể được ghi nhận trong binding result. `validate="false"` không làm cho chuỗi không hợp lệ tự chuyển thành số và cũng không đảm bảo loại bỏ lỗi binding.

Nếu transition có `bind="false"`, binder không xử lý các trường form của request đó, vì vậy giá trị `many` không được áp dụng vào model qua binding của view-state.

### Lỗi validation

Nếu `guests` đã được chuyển thành số `0`, binding có thể thành công. Sau đó validator kiểm tra quy tắc số khách phải lớn hơn hoặc bằng 1 và tạo lỗi validation.

Nếu transition dùng `validate="false"`, bước kiểm tra model này bị bỏ qua tại transition đó. Model vẫn có thể chứa số `0` và cần được kiểm tra lại ở bước nghiệp vụ phù hợp.

| Input | Binding | Validation | Kết quả |
|---|---|---|---|
| `guests=2` | Thành công | Hợp lệ | Có thể chuyển state |
| `guests=0` | Thành công | Không hợp lệ nếu yêu cầu ít nhất 1 | Transition có validation có thể giữ ở form |
| `guests=many` | Lỗi chuyển đổi | Không thể xem là giá trị số hợp lệ | Binding error cần xử lý |
| Không gửi trường `guests` | Phụ thuộc giá trị model và binder | Validator kiểm tra trạng thái model hiện có nếu được gọi | Không thể kết luận chỉ từ request |

## 8. Phối hợp với binder và validator

Trong view-state, thuộc tính `model` chỉ ra object được dùng cho form binding và validation. Binder có thể giới hạn các trường được phép nhận từ request:

~~~xml
<view-state id="bookingForm"
            view="bookingForm"
            model="booking">

    <binder>
        <binding property="customerName" />
        <binding property="startDate" />
        <binding property="endDate" />
        <binding property="guests" />
    </binder>

    <transition on="submit" to="reviewBooking" />
    <transition on="saveDraft"
                to="draftSaved"
                validate="false" />
</view-state>
~~~

Cấu hình binder xác định những thuộc tính có thể được binding. Thuộc tính `bind` trên transition quyết định có thực hiện binding ở transition đó hay không. Hai lớp cấu hình này bổ sung cho nhau:

- Binder giới hạn **trường nào** được binding.
- `bind` quyết định **có binding hay không** trong lần chuyển state này.
- `validate` quyết định **có chạy validation model hay không** trong lần chuyển state này.

Validator có thể kiểm tra các quy tắc của object:

~~~java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class BookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingDraft.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingDraft booking = (BookingDraft) target;

        if (booking.getCustomerName() == null
                || booking.getCustomerName().trim().isEmpty()) {
            errors.rejectValue(
                "customerName",
                "booking.customerName.required"
            );
        }

        if (booking.getStartDate() != null
                && booking.getEndDate() != null
                && booking.getEndDate().isBefore(booking.getStartDate())) {
            errors.rejectValue(
                "endDate",
                "booking.endDate.beforeStart"
            );
        }
    }
}
~~~

Ví dụ dùng Spring Validator để minh họa quy tắc model. Validator cần được đăng ký với flow/view theo cấu hình của ứng dụng. Trong dự án dùng Jakarta Bean Validation, các annotation như `@NotBlank`, `@NotNull` hoặc constraint tùy chỉnh có thể đảm nhiệm một phần quy tắc tương tự.

Dù dùng validator nào, `validate="false"` chỉ bỏ qua lần validation được điều khiển bởi transition. Nó không vô hiệu hóa validator ở mọi nơi trong ứng dụng và không ngăn service tự thực hiện kiểm tra nghiệp vụ.

## 9. Chọn thuộc tính theo ý nghĩa nút bấm

Tên nút và mục đích nghiệp vụ nên quyết định cấu hình transition:

| Nút hoặc event | bind | validate | Lý do |
|---|---|---|---|
| Gửi form để tiếp tục | Mặc định bật | Mặc định bật | Cần nhận và kiểm tra dữ liệu mới |
| Lưu nháp | Bật | Tắt | Giữ dữ liệu người dùng nhập dù còn thiếu |
| Hủy | Tắt | Tắt | Không nhận thay đổi chưa xác nhận |
| Quay lại bỏ thay đổi hiện tại | Tắt | Tắt | Trở về state trước mà không áp dụng request hiện tại |
| Quay lại nhưng muốn giữ dữ liệu đã nhập | Bật | Thường tắt | Binding để giữ nội dung, validation không chặn việc quay lại |
| Xác nhận nghiệp vụ cuối cùng | Bật | Bật | Cần dữ liệu hiện tại và kiểm tra đầy đủ |

Không phải mọi nút Quay lại đều cần cùng một cấu hình. Nếu người dùng mong muốn giữ những gì vừa nhập khi quay lại, binding cần được bật. Nếu hành vi là bỏ thay đổi và trở về dữ liệu đã lưu trước đó, có thể dùng `bind="false"`.

Tương tự, Lưu nháp thường cần binding để giữ dữ liệu nhưng có thể bỏ qua validation đầy đủ. Nếu nút Lưu nháp chỉ lưu một dấu mốc mà không nhận các giá trị vừa nhập, hãy cân nhắc có cần binding hay không.

## 10. Những điều bind=false và validate=false không làm

Để tránh hiểu sai, cần phân biệt rõ giới hạn của hai thuộc tính:

- `bind="false"` không ngăn transition action chạy.
- `bind="false"` không xóa model hiện tại; nó chỉ bỏ qua việc cập nhật model từ request qua binder.
- `validate="false"` không xóa lỗi cũ đã tồn tại trong model hoặc message context.
- `validate="false"` không tắt chuyển đổi kiểu khi binding vẫn bật.
- Cả hai không thay thế xác thực, phân quyền, kiểm tra nghiệp vụ hoặc constraint ở cơ sở dữ liệu.
- Cả hai không tự rollback một thay đổi đã được service ghi vào cơ sở dữ liệu.
- Cả hai không bảo đảm dữ liệu tạm sẽ được lưu hoặc bị hủy; điều đó phụ thuộc action và service của ứng dụng.

Đặc biệt, nếu một transition gọi service ghi dữ liệu, cấu hình `bind="false"` không hoàn tác thao tác đó. Nếu service được gọi trước khi người dùng bấm Hủy, ứng dụng cần có quy trình nghiệp vụ riêng để xử lý hủy hoặc bù trừ.

## 11. Kiểm thử các tổ hợp bind/validate

Kiểm thử nên quan sát cả giá trị model trước và sau transition, lỗi binding/validation và state đích.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Submit với dữ liệu hợp lệ | Gửi form hợp lệ | Model nhận dữ liệu và flow đến state tiếp theo |
| Submit với dữ liệu không hợp lệ | Gửi ngày kết thúc trước ngày bắt đầu | Validation lỗi và người dùng ở lại form |
| Save draft thiếu trường bắt buộc | Gửi form thiếu ngày kết thúc qua transition validate=false | Model nhận giá trị gửi lên và flow đến state lưu nháp |
| Save draft có chuỗi sai kiểu | Gửi `guests=many` khi binder cần Integer | Binding error vẫn được phát hiện dù validate=false |
| Cancel sau khi sửa form | Gửi các giá trị khác model qua bind=false | Model không nhận các giá trị đang gửi; transition vẫn chạy |
| bind=false, validate=true | Gửi giá trị khác nhưng model cũ hợp lệ | Request không cập nhật model; validation (nếu được thực thi) đánh giá model hiện có |
| Transition action khi bind=false | Gửi event cancel có action giải phóng tài nguyên | Action vẫn được gọi theo cấu hình transition |

Ở mức unit test, kiểm thử validator độc lập với binder. Ở mức flow test, kiểm tra từng transition với giá trị model ban đầu, request parameters, binding result và state sau transition. Ở mức tích hợp, dùng trình duyệt hoặc MockMvc phù hợp với cấu hình ứng dụng để xác nhận tên event và request thực tế.

Một kiểm thử quan trọng là sửa form rồi bấm Hủy: sau transition, xác minh dữ liệu model vẫn là dữ liệu cũ. Tiếp theo, sửa form rồi bấm Lưu nháp: xác minh model nhận giá trị mới dù validation đầy đủ không chạy. Hai tình huống này thể hiện rõ sự khác nhau giữa binding và validation.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đặt `validate="false"` cho nút Submit chính | Dữ liệu không hợp lệ có thể đi đến bước nghiệp vụ | Chỉ tắt validation ở transition có mục đích rõ như lưu nháp |
| Đặt `bind="false"` cho Lưu nháp | Nội dung người dùng vừa nhập không được đưa vào model | Bật binding và chỉ bỏ qua validation nếu phù hợp |
| Nghĩ validate=false bỏ qua lỗi chuyển đổi | Binding error vẫn xuất hiện | Phân biệt conversion/binding với model validation |
| Dùng bind=false để bảo vệ trường nhạy cảm | Transition khác vẫn có thể bind trường đó | Cấu hình binder allowlist và dùng DTO |
| Cho rằng bind=false hủy action | Action vẫn chạy, có thể vẫn ghi dữ liệu | Thiết kế rõ tác động nghiệp vụ và cơ chế rollback/compensation |
| Dùng validate=false cho mọi transition | Dữ liệu thiếu hoặc sai có thể đến bước cuối | Bật validation ở điểm kiểm tra bắt buộc |
| Quay lại với bind=false dù muốn giữ nội dung | Người dùng mất các chỉnh sửa vừa nhập | Chọn binding theo hành vi mong muốn |
| Chỉ kiểm tra validation ở giao diện | Request khác có thể gọi service bỏ qua flow | Kiểm tra nghiệp vụ ở tầng service |

## 13. Thực hành: thiết kế form đặt chỗ có ba hành vi

Tạo một view-state `bookingForm` với model `booking`, gồm các trường tên khách, ngày bắt đầu, ngày kết thúc và số khách.

1. Cấu hình binder chỉ cho phép binding bốn thuộc tính được liệt kê.
2. Tạo validator yêu cầu tên khách và ngày bắt đầu; nếu có ngày kết thúc thì ngày kết thúc phải sau hoặc bằng ngày bắt đầu.
3. Tạo transition `submit` với binding và validation mặc định để đi đến màn hình xem lại.
4. Tạo transition `saveDraft` với `validate="false"` để lưu bản nháp chưa hoàn chỉnh.
5. Tạo transition `cancel` với `bind="false" validate="false"` để hủy mà không nhận chỉnh sửa từ request.
6. Nhập ngày kết thúc trước ngày bắt đầu và bấm Submit; xác nhận flow ở lại form và hiển thị lỗi.
7. Xóa ngày kết thúc rồi bấm Lưu nháp; xác nhận model nhận dữ liệu vừa nhập và flow đi đến màn hình bản nháp.
8. Thay đổi tên khách rồi bấm Hủy; xác nhận model không nhận tên mới qua request hủy.
9. Gửi một giá trị sai kiểu cho số khách và bấm Lưu nháp; quan sát lỗi binding dù validation bị tắt.
10. Kiểm thử service xác nhận cuối cùng để bảo đảm dữ liệu không hợp lệ không thể được ghi nhận thành đặt chỗ chính thức.

Sau khi thực hành, hãy tự trả lời:

- `bind="false"` thay đổi bước nào trong quá trình xử lý request?
- Vì sao `validate="false"` không loại bỏ lỗi chuyển đổi kiểu?
- Khi nào một transition nên binding nhưng không validation?
- Khi nào nên bỏ qua cả binding và validation?
- Nếu binding bị tắt nhưng validation bật, validator nhìn thấy dữ liệu nào?
- Vì sao service vẫn phải kiểm tra nghiệp vụ khi flow đã bật validation?

## 14. Ghi nhớ

`bind="false"` bỏ qua việc cập nhật model từ các tham số request qua binder. `validate="false"` bỏ qua validation model trên transition. Binding và validation là hai bước riêng biệt: binding có thể tạo lỗi chuyển đổi kiểu, còn validation kiểm tra quy tắc của dữ liệu đã có trong model.

Dùng binding và validation mặc định cho bước gửi form cần dữ liệu hợp lệ. Dùng binding bật, validation tắt cho các hành động như lưu nháp khi dữ liệu còn thiếu. Dùng cả hai tắt cho Hủy hoặc Quay lại khi muốn bỏ các chỉnh sửa chưa xác nhận. Cuối cùng, luôn kiểm tra lại quy tắc nghiệp vụ ở service trước khi thực hiện thao tác quan trọng. Cách sử dụng đúng giúp hành trình **SPRING_WEB_FLOW** xử lý form nhất quán và cho người dùng những lựa chọn điều hướng phù hợp.
