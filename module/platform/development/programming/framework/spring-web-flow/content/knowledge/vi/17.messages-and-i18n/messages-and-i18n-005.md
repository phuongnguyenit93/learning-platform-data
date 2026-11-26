# Resource bundle dùng riêng cho một flow

> **Chương:** Thông báo và ngôn ngữ  
> **Mục tiêu:** Tổ chức các chuỗi giao diện, thông báo validation và phản hồi nghiệp vụ trong resource bundle riêng của một Spring Web Flow; hiểu cách đặt tên, phân giải locale, phối hợp với message source dùng chung, truyền tham số, kiểm thử và triển khai bản dịch mà không làm lẫn nội dung giữa các flow.

## 1. Vì sao một flow cần resource bundle riêng?

Một ứng dụng có thể có nhiều hành trình:

- `booking`: đặt lịch tư vấn.
- `checkout`: thanh toán đơn hàng.
- `profile`: cập nhật thông tin cá nhân.
- `support`: nhân viên hỗ trợ tra cứu và xử lý yêu cầu.

Mỗi flow có những thuật ngữ và thông báo đặc thù. Ví dụ, từ “slot” trong booking là khung giờ, còn từ “delivery slot” trong checkout có thể là khung giờ giao hàng. Nếu tất cả chuỗi đều đặt trong một file toàn ứng dụng, các nhóm phát triển dễ vô tình dùng chung key sai ngữ cảnh hoặc sửa một bản dịch làm ảnh hưởng nhiều màn hình.

**Resource bundle riêng cho một flow** gom những message chỉ có ý nghĩa trong một hành trình vào một bộ tài nguyên gắn với flow đó. Spring Web Flow có cơ chế hỗ trợ message resource theo flow; trong cấu hình thông dụng, bundle được đặt cùng khu vực tài nguyên của flow definition và được đặt tên theo **flow ID**.

Ví dụ:

~~~text
flows/
  booking/
    booking-flow.xml
    booking.properties
    booking_vi.properties
    booking_en.properties
    views/
      choose-slot.html
      review.html
  checkout/
    checkout-flow.xml
    checkout.properties
    checkout_vi.properties
    checkout_en.properties
~~~

Ở ví dụ này, `booking.properties` thuộc flow `booking`; `checkout.properties` thuộc flow `checkout`. Các file bản địa hóa theo locale cung cấp nội dung tương ứng.

**Lợi ích chính:** phạm vi message rõ ràng, key có ngữ cảnh, bản dịch được quản lý cùng flow và ít va chạm với message của quy trình khác.

## 2. Resource bundle là gì?

Resource bundle là tập tài nguyên dạng key/value để tách nội dung hiển thị khỏi code và flow definition. Trong Java/Spring, dạng thường gặp là file `.properties`:

~~~properties
booking.title=Đặt lịch tư vấn
booking.slot.required=Vui lòng chọn khung giờ.
booking.slot.unavailable=Khung giờ vừa chọn không còn trống.
booking.review.heading=Kiểm tra thông tin đặt lịch
booking.confirm=Xác nhận đặt lịch
~~~

Code và XML tham chiếu **key**:

~~~java
new MessageBuilder()
        .error()
        .source("slotId")
        .code("booking.slot.unavailable")
        .defaultText("Khung giờ không còn trống.")
        .build();
~~~

View có thể dùng key cho tiêu đề, nhãn, nút hoặc hướng dẫn. Khi locale thay đổi, message source tìm giá trị tương ứng mà không cần sửa logic điều hướng.

### 2.1. Tách ý nghĩa khỏi câu chữ

Không nên viết:

~~~java
messages.addMessage(new MessageBuilder()
        .error()
        .defaultText("Khung giờ vừa chọn không còn trống.")
        .build());
~~~

nếu ứng dụng cần hỗ trợ nhiều ngôn ngữ và quản lý bản dịch tập trung. Nên gắn code ổn định:

~~~java
messages.addMessage(new MessageBuilder()
        .error()
        .source("slotId")
        .code("booking.slot.unavailable")
        .defaultText("Khung giờ vừa chọn không còn trống.")
        .build());
~~~

`code` là định danh nội dung; `defaultText` là dự phòng khi không phân giải được code theo cơ chế được cấu hình. Không nên dùng câu tiếng Việt làm key vì khi sửa câu chữ sẽ buộc sửa cả code Java, XML hoặc template.

## 3. Cách đặt tên bundle theo flow ID

Trong cách tổ chức flow resource thông dụng của Spring Web Flow, **flow-specific message bundle được đặt tên theo flow ID** và nằm cạnh flow definition/resource của flow.

Ví dụ flow ID là `booking`:

~~~text
booking/
  booking-flow.xml
  booking.properties
  booking_vi.properties
  booking_en.properties
~~~

Flow ID là tên logic được đăng ký trong `FlowRegistry`, còn tên file XML là một phần cấu trúc resource. Trong ví dụ trên, cả hai cùng gợi tên `booking` để dễ nhận diện.

### 3.1. Đường dẫn phải khớp vị trí flow resource

Một cấu trúc khác:

~~~text
src/main/resources/
  flows/
    appointment/
      appointment-flow.xml
      appointment.properties
      appointment_vi.properties
    account/
      account-flow.xml
      account.properties
      account_vi.properties
~~~

Nếu `appointment` và `account` là hai flow ID riêng, mỗi flow có bộ message độc lập. Không đặt tất cả file vào một thư mục không liên quan rồi giả định Web Flow tự tìm được.

**Lưu ý theo phiên bản/cấu hình:** cách Web Flow phát hiện resource bundle phụ thuộc cơ chế resource loader, flow location và cấu hình message source của ứng dụng. Khi flow definition không nằm cạnh bundle theo quy ước thông dụng, cần đối chiếu tài liệu phiên bản đang dùng hoặc cấu hình message source tường minh. Đừng chỉ đổi tên file rồi cho rằng mọi classpath layout đều được tự động quét.

### 3.2. Không nhầm flow ID với tên view-state

Giả sử:

~~~xml
<flow id="booking">
    <view-state id="chooseSlot" view="booking/choose-slot"/>
    <view-state id="review" view="booking/review"/>
</flow>
~~~

`booking` là phạm vi flow; `chooseSlot` và `review` là state ID. Bundle theo flow thường là `booking.properties`, không phải bắt buộc tạo `chooseSlot.properties` và `review.properties`.

Nếu một state có rất nhiều thuật ngữ đặc thù, có thể tổ chức key theo prefix:

~~~properties
booking.chooseSlot.title=Chọn khung giờ
booking.chooseSlot.help=Chọn thời gian phù hợp với bạn.
booking.review.title=Kiểm tra lịch hẹn
booking.review.confirm=Đặt lịch
~~~

Prefix giúp nhóm message theo state mà vẫn giữ **một bundle riêng cho flow**.

## 4. Bundle riêng và message source dùng chung

Không phải mọi message đều nên nhân bản vào từng flow. Một ứng dụng thường có hai nhóm:

| Phạm vi | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| Dùng chung toàn ứng dụng | “Lưu”, “Hủy”, “Trường bắt buộc”, lỗi hệ thống chung | Application-wide MessageSource |
| Chỉ thuộc một flow | “Khung giờ đặt lịch đã hết”, “Mã xác nhận booking không hợp lệ” | Flow-specific resource bundle |

Ví dụ global:

~~~properties
# messages.properties
common.save=Lưu
common.cancel=Hủy
common.back=Quay lại
common.next=Tiếp tục
common.required=Trường này là bắt buộc.
common.unexpected=Đã xảy ra lỗi. Vui lòng thử lại sau.
~~~

Ví dụ riêng cho booking:

~~~properties
# booking.properties
booking.title=Đặt lịch tư vấn
booking.slot.required=Vui lòng chọn khung giờ.
booking.slot.unavailable=Khung giờ vừa chọn không còn trống.
booking.confirmation.pending=Đang kiểm tra kết quả đặt lịch.
~~~

### 4.1. Tìm message theo phạm vi

Trong một cấu hình điển hình, Web Flow có thể phân giải message trong tài nguyên gắn với flow và phối hợp với message source cha/toàn ứng dụng. Mục đích là:

1. Flow tìm được nội dung đặc thù của chính nó.
2. Nội dung dùng chung có thể được tái sử dụng từ application message source.
3. Nếu không tìm thấy key, ứng dụng có fallback có chủ đích thay vì hiện chuỗi rỗng.

**Thứ tự ưu tiên và fallback chính xác phụ thuộc phiên bản và cấu hình message source.** Không nên khẳng định flow bundle luôn ghi đè global bundle trong mọi setup, hoặc ngược lại. Nếu cùng một key tồn tại ở cả hai nơi, hãy viết integration test để xác nhận nguồn nào được chọn trong cấu hình thực tế.

### 4.2. Quy tắc chọn nơi đặt key

- Nếu message chỉ có ý nghĩa trong booking, dùng prefix `booking.` và bundle booking.
- Nếu nhiều flow thực sự dùng cùng ý nghĩa/cùng nội dung, dùng global key `common.`.
- Nếu hai flow dùng câu giống nhau nhưng ý nghĩa nghiệp vụ khác nhau, giữ key riêng để dịch độc lập.
- Tránh copy toàn bộ global bundle vào từng flow; điều đó tạo bản dịch trùng lặp và dễ lệch.

## 5. Bản địa hóa theo locale

Java resource bundle hỗ trợ tên file theo quy tắc locale. Ví dụ:

~~~text
booking.properties       # Bản mặc định
booking_vi.properties    # Tiếng Việt
booking_en.properties    # Tiếng Anh
booking_vi_VN.properties # Tiếng Việt, Việt Nam
booking_en_US.properties # Tiếng Anh, Hoa Kỳ
~~~

Locale thực tế có thể đến từ:

- Locale của request do Spring MVC xác định.
- Cookie/session hoặc profile người dùng theo chính sách ứng dụng.
- Header `Accept-Language` của trình duyệt.
- Một lựa chọn ngôn ngữ rõ ràng trên giao diện.

Resource bundle chỉ cung cấp bản dịch. **Nó không tự quyết định người dùng đang dùng locale nào**; ứng dụng phải có cơ chế xác định và truyền locale vào message resolution.

### 5.1. Ví dụ hai ngôn ngữ

**booking_vi.properties**

~~~properties
booking.title=Đặt lịch tư vấn
booking.chooseSlot.title=Chọn khung giờ
booking.chooseSlot.required=Vui lòng chọn khung giờ.
booking.slot.unavailable=Khung giờ vừa chọn không còn trống.
booking.review.title=Kiểm tra thông tin đặt lịch
booking.review.confirm=Đặt lịch
booking.success=Bạn đã đặt lịch thành công.
booking.pending=Chúng tôi đang xác nhận lịch hẹn của bạn.
~~~

**booking_en.properties**

~~~properties
booking.title=Book a consultation
booking.chooseSlot.title=Choose a time slot
booking.chooseSlot.required=Please choose a time slot.
booking.slot.unavailable=The selected time slot is no longer available.
booking.review.title=Review your booking
booking.review.confirm=Confirm booking
booking.success=Your booking has been confirmed.
booking.pending=We are checking the status of your booking.
~~~

Cùng một key biểu thị cùng một ý nghĩa. Khi locale là `vi`, nội dung tiếng Việt được chọn; khi locale là `en`, nội dung tiếng Anh được chọn theo quy tắc phân giải locale.

### 5.2. Fallback khi thiếu bản dịch

Giả sử bundle `booking_vi.properties` không có `booking.pending`. Java/Spring có thể tiếp tục tìm resource ít cụ thể hơn như `booking.properties` hoặc message source cha, tùy cách cấu hình.

Một chiến lược an toàn:

1. Duy trì bundle mặc định có đủ các key bắt buộc.
2. Bổ sung bản dịch cho từng locale được hỗ trợ.
3. Cho phép fallback có chủ đích khi thiếu bản dịch.
4. Có test phát hiện key thiếu trước khi phát hành.
5. Không để người dùng nhìn thấy key nội bộ như `booking.pending`.

Không dùng default text ở ngôn ngữ sai làm cách che việc thiếu bản dịch. Một fallback kỹ thuật có thể giúp tránh trang trống, nhưng chất lượng ngôn ngữ vẫn cần được kiểm soát.

## 6. Locale có thể thay đổi giữa các request của một flow

Flow nhiều bước thường tồn tại qua nhiều request HTTP. Người dùng có thể đổi ngôn ngữ khi đang ở `review` rồi quay lại `chooseSlot`.

Một cách tổ chức hợp lý:

~~~text
FlowExecution:
  flowScope.booking = dữ liệu nghiệp vụ đã bind
  current state = review

Request 1:
  locale = vi
  render booking_vi.properties

Người dùng đổi locale

Request 2:
  locale = en
  render booking_en.properties
  flowScope.booking vẫn giữ giá trị nghiệp vụ
~~~

**Không lưu câu đã dịch làm dữ liệu nghiệp vụ trong flowScope.** Hãy lưu mã dịch vụ, số lượng, ngày giờ hoặc ID; view resolve lại message theo locale hiện tại.

### 6.1. Locale của message và format dữ liệu là hai việc liên quan

Một trang tiếng Việt có thể hiển thị `1.234,50`, trong khi tiếng Anh hiển thị `1,234.50`. Message bundle dịch nhãn và câu chữ; formatter/converter chịu trách nhiệm định dạng số, ngày và tiền theo locale.

Không đặt sẵn mọi chuỗi định dạng số trong resource bundle nếu có thể dùng formatter phù hợp. Cũng không lấy locale của một message rồi tự suy ra rằng mọi dữ liệu form đã được parse theo cùng locale; conversion/binding phải được cấu hình riêng.

## 7. Resource bundle dùng cho validation

Spring Web Flow hỗ trợ validation thông qua cơ chế binding/message. Validator có thể thêm message theo code:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.validation.ValidationContext;

public class BookingValidator {

    public void validateChooseSlot(
            BookingDraft draft, ValidationContext context) {

        if (draft.getSlotId() == null) {
            context.getMessageContext().addMessage(
                    new MessageBuilder()
                            .error()
                            .source("slotId")
                            .code("booking.chooseSlot.required")
                            .defaultText("Vui lòng chọn khung giờ.")
                            .build());
        }
    }
}
~~~

Bundle:

~~~properties
# booking_vi.properties
booking.chooseSlot.required=Vui lòng chọn khung giờ.
booking.attendees.range=Số người phải từ {0} đến {1}.
~~~

~~~properties
# booking_en.properties
booking.chooseSlot.required=Please choose a time slot.
booking.attendees.range=Attendees must be between {0} and {1}.
~~~

Trong ví dụ, `source("slotId")` xác định field liên quan; `code(...)` là key để tìm bản dịch. View phải hiển thị message gắn field đúng vị trí. Việc tạo code và resolve code thực tế còn phụ thuộc validator, binding và message source đã được cấu hình.

### 7.1. Lỗi conversion có thể có code khác

Nếu request gửi `attendees=abc` trong khi property đích là `Integer`, lỗi xảy ra ở conversion/binding trước khi validator có một số nguyên hợp lệ để kiểm tra range.

Đừng giả định code tự sinh của lỗi conversion luôn là `booking.attendees.range`. Hãy kiểm tra code được Web Flow/Spring Binding tạo ra trong phiên bản đang dùng và cung cấp mapping tương ứng nếu muốn bản địa hóa chính xác.

### 7.2. Tránh phát hai message cho một lỗi

Nếu binder đã báo lỗi chuyển đổi, validator không nên thêm thêm một lỗi “số người phải từ 1 đến 8” khi giá trị hiện tại chưa có kiểu số. Hãy phân biệt:

- **Conversion error:** không thể tạo giá trị Java.
- **Validation error:** đã có giá trị Java nhưng vi phạm ràng buộc.
- **Business outcome:** giá trị hợp lệ nhưng tài nguyên không còn khả dụng.

Resource bundle có thể chứa key cho cả ba, nhưng tầng phát message phải đúng trách nhiệm.

## 8. Resource bundle cho nhãn, hướng dẫn và nút trong view

Ngoài lỗi, flow bundle có thể chứa các chuỗi phục vụ giao diện:

~~~properties
booking.chooseSlot.title=Chọn khung giờ
booking.chooseSlot.description=Chọn thời gian phù hợp với lịch của bạn.
booking.chooseSlot.slotLabel=Khung giờ
booking.chooseSlot.attendeesLabel=Số người tham gia
booking.actions.back=Quay lại
booking.actions.next=Tiếp tục
booking.actions.cancel=Hủy
booking.review.title=Kiểm tra thông tin đặt lịch
booking.review.confirm=Đặt lịch
~~~

Nhóm key theo state và vai trò giúp translator hiểu ngữ cảnh. Một key `booking.actions.back` có thể được dùng ở nhiều state trong cùng flow, trong khi `booking.chooseSlot.slotLabel` chỉ dành cho màn hình chọn giờ.

### 8.1. View template chỉ tham chiếu key

Ví dụ pseudocode template:

~~~html
<h1>#{booking.chooseSlot.title}</h1>
<p>#{booking.chooseSlot.description}</p>
<label for="slotId">#{booking.chooseSlot.slotLabel}</label>
<button type="submit" name="_eventId_next">
  #{booking.actions.next}
</button>
~~~

Đây là **minh họa ý tưởng**, cú pháp thực tế khác nhau giữa JSP, Thymeleaf hoặc view technology mà ứng dụng dùng. Không mặc định `#{...}` là cú pháp dùng được ở mọi template engine.

Nếu view được render bởi một engine tích hợp Spring MessageSource, hãy cấu hình view resolver/message expression theo engine đó và kiểm thử locale thực tế.

## 9. Message trong action: kết quả nghiệp vụ theo ngôn ngữ

Giả sử người dùng đã chọn `slotId` hợp lệ về kiểu nhưng người khác vừa đặt khung giờ đó. Service trả outcome `SLOT_UNAVAILABLE`; action phát message:

~~~java
context.getMessageContext().addMessage(
        new MessageBuilder()
                .error()
                .source("slotId")
                .code("booking.slot.unavailable")
                .defaultText("Khung giờ vừa chọn không còn trống.")
                .build());

return new Event(this, "slotUnavailable");
~~~

Flow:

~~~xml
<action-state id="reserve">
    <evaluate expression="bookingAction.reserve(requestContext)"/>
    <transition on="booked" to="completed"/>
    <transition on="slotUnavailable" to="chooseSlot"/>
</action-state>
~~~

Bundle:

~~~properties
# booking_vi.properties
booking.slot.unavailable=Khung giờ vừa chọn không còn trống. Vui lòng chọn lại.
~~~

~~~properties
# booking_en.properties
booking.slot.unavailable=The selected time slot is no longer available. Please choose another.
~~~

**Message và event có vai trò khác nhau:** message giải thích cho người dùng; event `slotUnavailable` chọn transition. Resource bundle không điều khiển flow.

### 9.1. Vòng đời message khi chuyển state

Message được thêm ở action-state có thể cần hiển thị tại view-state kế tiếp. Cần kiểm tra cơ chế lưu/hiển thị message của Web Flow và view engine đang dùng, nhất là khi có redirect hoặc flow execution tạm dừng.

Nếu thông báo phải tồn tại lâu hơn vòng đời MessageContext, có thể giữ **mã outcome** trong scope phù hợp rồi resolve lại ở view đích. Tránh lưu câu đã dịch vào session chung vì:

- Người dùng có thể đổi locale.
- Nhiều tab có thể hiển thị nhầm thông báo.
- Message cũ có thể tồn tại sau khi người dùng đã sửa xong.

## 10. Message có tham số và định dạng

Một key có thể chứa tham số:

~~~properties
# booking_vi.properties
booking.attendees.range=Số người phải từ {0} đến {1}.
booking.slot.remaining=Khung giờ này còn {0} chỗ.
booking.fee=Phí tư vấn: {0}
~~~

~~~properties
# booking_en.properties
booking.attendees.range=Attendees must be between {0} and {1}.
booking.slot.remaining=This time slot has {0} places remaining.
booking.fee=Consultation fee: {0}
~~~

Code có thể truyền arguments cho MessageBuilder:

~~~java
context.getMessageContext().addMessage(
        new MessageBuilder()
                .warning()
                .code("booking.slot.remaining")
                .args(2)
                .defaultText("Khung giờ này còn ít chỗ.")
                .build());
~~~

Việc định dạng argument phụ thuộc message source/MessageFormat và locale. Với tiền tệ, ngày giờ hoặc số nhiều, nên dùng kiểu dữ liệu có ý nghĩa và formatter phù hợp thay vì nối chuỗi thủ công.

### 10.1. Dấu nháy và dấu ngoặc nhọn trong properties

Resource bundle kiểu Java dùng quy tắc escape và định dạng của `MessageFormat` khi message có tham số. Dấu nháy đơn, dấu ngoặc nhọn hoặc dấu gạch chéo ngược có thể cần escape tùy nội dung.

Ví dụ:

~~~properties
booking.welcome=Chào {0}, bạn đã chọn gói {1}.
~~~

Nếu nội dung chứa literal `'` hoặc `{`, hãy test message sau khi resolve thay vì chỉ đọc file. Một file properties hợp cú pháp không đảm bảo chuỗi định dạng sẽ render đúng với mọi argument.

### 10.2. Số nhiều và khác biệt ngôn ngữ

Không phải ngôn ngữ nào cũng dùng quy tắc số nhiều như tiếng Anh. Một mẫu đơn giản:

~~~properties
booking.slot.count=You have {0} slots.
~~~

có thể không đủ cho ngôn ngữ cần nhiều dạng số nhiều. Khi nội dung yêu cầu quy tắc phức tạp, sử dụng cơ chế pluralization/i18n phù hợp của ứng dụng hoặc tách message theo outcome rõ ràng; không ghép hậu tố `s` trong Java.

## 11. Resource bundle cho flow con (subflow)

Một flow cha `booking` có thể gọi subflow `verifyContact`. Flow con có nội dung riêng:

~~~text
flows/
  booking/
    booking-flow.xml
    booking.properties
    verifyContact/
      verifyContact-flow.xml
      verifyContact.properties
      verifyContact_vi.properties
~~~

Ví dụ:

**booking.properties**

~~~properties
booking.title=Đặt lịch tư vấn
booking.confirm=Đặt lịch
booking.contact.verified=Thông tin liên hệ đã được xác minh.
~~~

**verifyContact.properties**

~~~properties
verifyContact.title=Xác minh thông tin liên hệ
verifyContact.code.required=Vui lòng nhập mã xác minh.
verifyContact.code.invalid=Mã xác minh không đúng.
verifyContact.code.expired=Mã xác minh đã hết hạn.
~~~

Flow con sở hữu các màn hình và message riêng của quá trình xác minh. Flow cha sở hữu message của quy trình đặt lịch.

### 11.1. Flow cha không nên phụ thuộc key nội bộ của flow con

Nếu flow cha muốn hiển thị kết quả xác minh, hãy nhận **outcome hoặc dữ liệu có cấu trúc** từ subflow và tạo message thuộc flow cha khi cần.

~~~xml
<subflow-state id="verifyContact" subflow="verifyContact">
    <input name="email" value="flowScope.booking.email"/>
    <transition on="verified" to="review"/>
    <transition on="cancelled" to="contact"/>
</subflow-state>
~~~

Flow con có thể kết thúc bằng `verified`; flow cha quyết định message `booking.contact.verified` nếu người dùng cần được thông báo ở màn hình review.

Không giả định MessageContext của subflow sẽ luôn được render trong flow cha hoặc bundle của flow con sẽ tự động được dùng để phân giải mọi key ở view cha.

## 12. Dùng lại key và tránh xung đột

Hai flow có thể vô tình cùng đặt key `title` nhưng ý nghĩa khác nhau. Khi tài nguyên được phân giải qua nhiều message source, key chung chung làm khó truy vết.

Nên dùng key có namespace:

~~~properties
booking.title=Đặt lịch tư vấn
checkout.title=Thanh toán đơn hàng
profile.title=Thông tin cá nhân
support.title=Hỗ trợ khách hàng
~~~

Trong flow-specific bundle, prefix flow ID vẫn có ích dù bundle đã có phạm vi riêng:

- Dễ chuyển key sang global bundle nếu sau này cần.
- Dễ grep, review và tìm nơi sử dụng.
- Giảm xung đột nếu có nhiều message source được kết hợp.
- Giúp translator hiểu ngữ cảnh khi key được export ra công cụ dịch.

### 12.1. Khi nào đưa key từ flow lên global?

Chỉ chuyển khi các flow thực sự chia sẻ **cùng ý nghĩa và cùng yêu cầu bản dịch**. Ví dụ `common.cancel` có thể dùng chung. Còn “Hủy đặt lịch” và “Hủy giao dịch thanh toán” có thể có chính sách khác nhau, nên giữ key riêng.

Đừng chuyển key lên global chỉ để giảm số file; phạm vi sở hữu nội dung quan trọng hơn số lượng file.

## 13. Cấu hình message source và tích hợp Spring

Spring Framework cung cấp abstraction `MessageSource` để phân giải message theo code, arguments và locale. Một ứng dụng có thể cấu hình application-wide source bằng `ResourceBundleMessageSource` hoặc `ReloadableResourceBundleMessageSource` tùy môi trường.

Ví dụ cấu hình Spring XML cho bundle dùng chung:

~~~xml
<bean id="messageSource"
      class="org.springframework.context.support.ResourceBundleMessageSource">
    <property name="basenames">
        <list>
            <value>messages</value>
            <value>validation</value>
        </list>
    </property>
    <property name="defaultEncoding" value="UTF-8"/>
</bean>
~~~

Đây là cấu hình **application-wide** minh họa. Nó không tự chứng minh Web Flow đã phát hiện tất cả flow-specific bundles. Cơ chế flow resource bundle và message source cha cần được cấu hình/tích hợp đúng phiên bản.

### 13.1. Flow-specific resource không phải lúc nào cũng là basename global

Một lựa chọn là cấu hình mọi flow bundle vào global basename list:

~~~xml
<property name="basenames">
    <list>
        <value>messages</value>
        <value>flows.booking.booking</value>
        <value>flows.checkout.checkout</value>
    </list>
</property>
~~~

Cách này **biến các bundle flow thành tài nguyên của message source toàn ứng dụng** và có thể gây xung đột key hoặc không giữ đúng phạm vi riêng. Chỉ dùng nếu kiến trúc chủ động muốn một message source chung và hiểu rõ thứ tự basename/precedence.

Nếu muốn dùng cơ chế flow-specific của Web Flow, hãy giữ cấu trúc resource theo flow và cấu hình FlowBuilderServices/message source đúng với phiên bản. Đừng đồng thời cấu hình cùng bundle ở nhiều nơi mà không có test về ưu tiên.

### 13.2. Đừng tự đoán API cấu hình từ phiên bản khác

Các dự án có thể dùng:

- Spring Web Flow 2.x với XML namespace.
- Spring Web Flow được cấu hình qua Java configuration.
- Spring MVC và MessageSource riêng.
- View engine JSP/Thymeleaf hoặc một giải pháp khác.

Tên class, điểm nối, cách tạo flow-specific message source và cú pháp cấu hình có thể khác theo phiên bản. Trước khi áp dụng, kiểm tra dependency thực tế và API tương ứng. Bài này tập trung vào **mô hình tổ chức resource và nguyên tắc phân giải**, không cam kết một đoạn XML duy nhất chạy nguyên văn trên mọi tổ hợp phiên bản.

## 14. Encoding và quy tắc file properties

Các file resource bundle chứa tiếng Việt cần được lưu đúng encoding. Với Spring MessageSource, cấu hình encoding UTF-8 phù hợp giúp tránh lỗi hiển thị dấu.

Ví dụ nội dung:

~~~properties
booking.title=Đặt lịch tư vấn
booking.error=Không thể hoàn tất yêu cầu.
~~~

### 14.1. Kiểm tra encoding trong build và runtime

- Lưu file bằng UTF-8 theo convention của dự án.
- Cấu hình message source với encoding tương ứng nếu API hỗ trợ.
- Kiểm tra cách runtime Java đọc resource bundle theo JDK/version đang dùng.
- Không giả định file hiển thị đúng trong editor thì runtime cũng đọc đúng.
- Có integration test lấy message tiếng Việt và so sánh đúng dấu.

Các phiên bản JDK khác nhau có lịch sử khác nhau về encoding mặc định của resource bundle. Vì vậy, **khai báo encoding rõ ràng và kiểm thử runtime** là cách ít phụ thuộc môi trường hơn.

### 14.2. Ký tự đặc biệt

Trong file properties, dấu `=`, `:`, khoảng trắng đầu dòng, dấu gạch chéo ngược và ký tự xuống dòng có quy tắc escape riêng. Nếu câu dịch có ký tự đặc biệt, hãy kiểm tra parser properties và kết quả message sau khi tải.

Không tự chèn newline vào câu thông báo chỉ để định dạng file. Nếu cần xuống dòng trên UI, view nên điều khiển layout hoặc dùng key riêng cho từng đoạn.

## 15. Kiểm thử flow-specific bundle

Kiểm thử cần chứng minh **đúng bundle được chọn**, đúng locale và đúng fallback. Chỉ kiểm tra file tồn tại là chưa đủ.

| Cấp kiểm thử | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| Resource test | Flow booking với locale vi | Resolve key booking tiếng Việt |
| Resource test | Flow booking với locale en | Resolve cùng key bằng tiếng Anh |
| Isolation test | Flow checkout resolve key riêng | Không lấy nhầm nội dung booking |
| Fallback test | Thiếu key trong bundle locale cụ thể | Dùng fallback được cấu hình |
| Validation test | slotId rỗng | Message code booking.chooseSlot.required |
| Action test | Slot đã bị đặt | Message booking.slot.unavailable và event slotUnavailable |
| View integration | Render chooseSlot tiếng Việt | Tiêu đề, label, nút và lỗi đúng ngôn ngữ |
| View integration | Render chooseSlot tiếng Anh | Nội dung tiếng Anh, không hiện key |
| Subflow test | Flow con verifyContact | Message xác minh thuộc bundle flow con |
| Parent flow test | Nhận outcome verified | Flow cha hiển thị message riêng nếu cần |
| Encoding test | Đọc chuỗi có dấu tiếng Việt | Không lỗi mojibake |
| Missing-key test | Dùng key chưa được dịch | Test phát hiện thiếu key theo locale |

### 15.1. Test isolation giữa hai flow

Giả sử cả hai bundle có key `title`:

~~~properties
# booking.properties
title=Đặt lịch tư vấn
~~~

~~~properties
# checkout.properties
title=Thanh toán đơn hàng
~~~

Hãy test trong đúng ngữ cảnh từng flow:

~~~text
resolve(flow="booking", key="title")  -> "Đặt lịch tư vấn"
resolve(flow="checkout", key="title") -> "Thanh toán đơn hàng"
~~~

Đây là pseudocode. Nếu hệ thống chỉ dùng global MessageSource và không có flow-specific resolution, test sẽ cho thấy hai key trùng tên không còn được cách ly. Khi đó cần đổi key thành namespace rõ ràng hoặc cấu hình lại nguồn message.

### 15.2. Test thứ tự ưu tiên và fallback

Tạo một key có mặt ở cả flow bundle và global bundle:

~~~properties
# booking.properties
common.cancel=Hủy đặt lịch
~~~

~~~properties
# messages.properties
common.cancel=Hủy
~~~

Trong cấu hình thực tế, kiểm tra nguồn nào được ưu tiên. Sau đó xóa key khỏi flow bundle và kiểm tra fallback. **Đừng biến giả định về precedence thành hợp đồng nếu chưa có test theo phiên bản.**

### 15.3. Test locale thay đổi qua request

Một kịch bản browser/MockMvc:

1. Mở flow booking ở locale `vi`.
2. Chọn slot, đi đến review.
3. Thay locale sang `en` theo cơ chế ứng dụng.
4. Tiếp tục render view-state kế tiếp.
5. Xác minh dữ liệu draft không thay đổi nhưng câu chữ được resolve theo locale mới.

Nếu ứng dụng cố định locale cho cả conversation, kết quả có thể khác. Điều quan trọng là **chính sách locale phải rõ ràng và có test**.

## 16. Quản lý bản dịch khi flow phát triển

Khi đổi flow definition hoặc validator, key có thể được thêm, đổi tên hoặc xóa. Cần quản lý resource bundle như một phần của hợp đồng giao diện:

- Mọi key được dùng trong flow/view/validator phải có bản mặc định.
- Các locale được hỗ trợ cần được cập nhật đồng bộ.
- Key đã bỏ phải được tìm và dọn theo quy trình review.
- Không đổi nghĩa một key đang dùng ở nhiều nơi mà không rà soát.
- Translator cần ngữ cảnh và placeholder, không chỉ danh sách chuỗi.

### 16.1. Bảng theo dõi key

| Key | Vị trí sử dụng | VI | EN | Trạng thái |
| --- | --- | --- | --- | --- |
| booking.chooseSlot.title | View chooseSlot | Có | Có | Đủ |
| booking.chooseSlot.required | Validator | Có | Có | Đủ |
| booking.slot.unavailable | Action reserve | Có | Có | Đủ |
| booking.status.unknown | View pending | Có | Thiếu | Cần dịch |

Đây là bảng minh họa cho quá trình review, không phải file metadata mà Web Flow tự sinh.

### 16.2. Tránh đổi key tùy tiện

Một key có thể được tham chiếu từ:

- Java `MessageBuilder.code(...)`.
- Validator.
- JSP/Thymeleaf template.
- XML expression hoặc action.
- Test tự động.

Khi đổi `booking.slot.unavailable` thành `booking.slot.taken`, cần cập nhật tất cả điểm sử dụng và bản dịch. Tìm kiếm key trong repository và chạy test missing-key giúp tránh message bị rơi về default text ngoài ý muốn.

## 17. Thông báo không được biến thành dữ liệu nghiệp vụ

Resource bundle chỉ chứa **nội dung hiển thị**, không phải trạng thái thật của booking.

Ví dụ `booking.success=Bạn đã đặt lịch thành công` chỉ được hiển thị khi service xác nhận transaction đã commit. Nếu service timeout sau khi gửi lệnh ghi và chưa biết kết quả, phải dùng message như `booking.pending` và cho đối soát bằng request ID.

~~~mermaid
flowchart TD
    A["BookingService.reserveOnce(requestId)"] --> B{"Kết quả đã biết?"}
    B -->|"Confirmed"| C["Event booked"]
    C --> D["Resolve booking.success theo locale"]
    B -->|"Slot unavailable"| E["Event slotUnavailable"]
    E --> F["Resolve booking.slot.unavailable"]
    B -->|"Commit chưa rõ"| G["Event statusUnknown"]
    G --> H["Resolve booking.pending"]
    H --> I["Tra cứu theo requestId"]
~~~

### 17.1. Không dùng nội dung bản dịch để quyết định flow

Sai:

~~~java
if (messageText.equals("Đặt lịch thành công")) {
    // ...
}
~~~

Đúng: dùng enum/outcome/event typed từ service, còn message code chỉ dùng để hiển thị:

~~~java
if (outcome.isBooked()) {
    return new Event(this, "booked");
}
~~~

Nội dung bản dịch có thể thay đổi theo locale, cách diễn đạt hoặc yêu cầu sản phẩm; logic điều khiển phải độc lập với câu chữ.

### 17.2. Không đưa dữ liệu nhạy cảm vào properties

Bundle là tài nguyên tĩnh, có thể được đóng gói trong artifact và đọc bởi nhiều người có quyền truy cập repository. Không đặt token, mật khẩu, dữ liệu khách hàng hoặc thông tin cấu hình bí mật trong resource bundle.

Arguments truyền vào message cũng cần escape an toàn khi render HTML. Một bản dịch không mặc nhiên là HTML đáng tin.

## 18. Những lỗi thường gặp

**Đặt bundle sai vị trí.** Flow không tìm thấy message riêng vì file không nằm trong resource layout mà loader mong đợi. Xác minh flow ID, location và resource resolver.

**Dùng tên file theo state thay vì flow ID.** Không theo quy ước flow-specific thông dụng, dẫn đến bundle không được phát hiện. Xác định rõ flow ID và basename.

**Đưa mọi key vào global bundle.** Các flow dễ dùng nhầm thuật ngữ, key trùng và sửa bản dịch gây ảnh hưởng ngoài ý muốn. Tách key đặc thù về bundle riêng.

**Copy toàn bộ global bundle sang mỗi flow.** Tạo bản dịch trùng lặp, khó đồng bộ. Chỉ giữ key riêng của flow.

**Giả định thứ tự ưu tiên.** Cùng key có ở flow và global nhưng chưa test nguồn được chọn. Kiểm thử precedence/fallback theo cấu hình thực tế.

**Locale không được truyền đúng.** File `booking_vi.properties` tồn tại nhưng request vẫn resolve locale mặc định. Kiểm tra LocaleResolver/LocaleContext và cách flow tiếp tục request.

**Dùng câu dịch làm key.** Sửa câu chữ làm hỏng code reference. Dùng key ổn định theo ý nghĩa.

**Thiếu bản dịch nhưng không phát hiện.** Một số màn hình hiện key thô hoặc default text sai ngôn ngữ. Thêm test missing-key cho từng locale.

**Dùng MessageContext như kho thông báo dài hạn.** Message có vòng đời theo quá trình xử lý; nếu cần mang qua state, hãy truyền mã outcome hoặc dữ liệu phù hợp.

**Định dạng số/ngày trong properties.** Message bundle không thay thế converter/formatter. Dùng formatter theo locale cho dữ liệu động.

**Hiển thị thông báo thành công quá sớm.** Message không xác nhận transaction. Chỉ hiển thị success sau khi service biết kết quả bền vững.

## 19. Bài thực hành: tách message cho booking và checkout

Một ứng dụng hiện có một file `messages.properties` chứa toàn bộ nội dung của flow đặt lịch và thanh toán. Một số key:

~~~properties
title=Đặt lịch
confirm=Xác nhận
unavailable=Không còn chỗ
pending=Đang xử lý
~~~

Nhóm phát triển muốn tách nội dung theo flow và hỗ trợ tiếng Việt/tiếng Anh.

**Yêu cầu:**

1. Tạo cấu trúc tài nguyên cho flow `booking` và `checkout`; đặt bundle theo flow ID và đặt các locale cần hỗ trợ.
2. Di chuyển các key đặc thù như `booking.slot.unavailable` và `checkout.stock.unavailable` về bundle tương ứng.
3. Giữ key chung như `common.cancel` ở application-wide bundle nếu hai flow thật sự cùng nghĩa.
4. Viết các bản dịch VI/EN có cùng key và cùng ý nghĩa.
5. Cập nhật validator booking để dùng `booking.chooseSlot.required`.
6. Cập nhật action booking để phát message `booking.slot.unavailable` khi service trả outcome hết chỗ.
7. Đảm bảo view booking chỉ tham chiếu key, không hardcode câu tiếng Việt.
8. Tạo test chứng minh cùng key `title` được phân giải đúng trong từng flow nếu cơ chế flow-specific hỗ trợ.
9. Tạo test precedence khi key cùng tồn tại ở flow bundle và global bundle.
10. Thay locale giữa hai request của flow và xác minh draft không đổi nhưng câu chữ đổi.
11. Tạo test thiếu key để phát hiện bản dịch EN còn thiếu.
12. Xác minh message “đã đặt thành công” chỉ được hiển thị sau khi service xác nhận commit.

**Cấu trúc gợi ý:**

~~~text
flows/
  booking/
    booking-flow.xml
    booking.properties
    booking_vi.properties
    booking_en.properties
  checkout/
    checkout-flow.xml
    checkout.properties
    checkout_vi.properties
    checkout_en.properties
messages.properties
messages_vi.properties
messages_en.properties
~~~

Đây là cấu trúc minh họa. Điều chỉnh theo flow location và resource loader thực tế của dự án.

**Tiêu chí đạt:** message đặc thù không lẫn giữa các flow; message dùng chung không bị nhân bản; locale được xác định nhất quán; mọi key có fallback rõ; view, validator và action dùng cùng hợp đồng key; trạng thái nghiệp vụ không phụ thuộc câu dịch.

## 20. Tổng kết và câu hỏi tự kiểm tra

Resource bundle riêng cho flow giúp quản lý **ngôn ngữ và nội dung giao diện theo ranh giới của một hành trình**. Trong cấu trúc thông dụng của Spring Web Flow, bundle mang tên flow ID và được đặt cùng khu vực resource của flow definition; các file locale cung cấp bản dịch tương ứng. Message source dùng chung vẫn phù hợp cho nội dung thực sự dùng chung.

Flow-specific bundle có thể cung cấp nội dung cho tiêu đề, label, hướng dẫn, lỗi validation và phản hồi nghiệp vụ. **Message code** phải ổn định, còn locale và message source quyết định câu chữ được phân giải. Thứ tự ưu tiên giữa flow bundle và global source, cách phát hiện resource, encoding và cú pháp view cần được xác minh theo phiên bản/cấu hình thực tế.

**Câu hỏi tự kiểm tra:**

1. Vì sao flow `booking` có thể cần `booking.properties` riêng thay vì đưa mọi key vào `messages.properties`?
2. Flow ID khác state ID như thế nào khi đặt tên bundle?
3. Khi cùng key xuất hiện ở flow-specific bundle và global bundle, vì sao cần test precedence?
4. Resource bundle có tự chọn locale cho request không?
5. Nếu locale thay đổi giữa hai request, vì sao nên giữ dữ liệu typed trong flowScope thay vì câu đã dịch?
6. `MessageBuilder.code(...)` khác `defaultText(...)` ở vai trò nào?
7. Lỗi conversion và lỗi validation có nhất thiết dùng cùng message code không?
8. Vì sao message của subflow không nên được flow cha xem như tài nguyên nội bộ có thể truy cập mặc định?
9. Resource bundle có thay thế formatter cho tiền và ngày tháng không?
10. Vì sao thông báo success phải phụ thuộc kết quả service/transaction chứ không phụ thuộc việc flow đã tới một view có tên completed?
