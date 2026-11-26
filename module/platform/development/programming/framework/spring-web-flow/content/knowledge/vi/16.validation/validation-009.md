# Điều kiện chéo giữa các trường và giữa nhiều bước

Spring Web Flow mô hình hóa hành trình web nhiều bước bằng flow, state, event và transition. Trong một quy trình như đặt chỗ, người dùng có thể nhập ngày nhận và ngày trả ở bước đầu, số khách ở bước tiếp theo rồi kiểm tra thông tin liên hệ trước khi xác nhận. Mỗi trường riêng lẻ có thể hợp lệ nhưng tổ hợp dữ liệu vẫn có thể sai. Ví dụ, ngày trả phải sau ngày nhận; số trẻ em không được vượt quá tổng số khách; hoặc thông tin giao hàng ở bước sau phải phù hợp với quốc gia đã chọn ở bước trước.

Những quy tắc phụ thuộc nhiều trường được gọi là **điều kiện chéo**. Khi dữ liệu được thu thập qua nhiều view-state, ứng dụng còn phải kiểm tra các điều kiện phụ thuộc vào dữ liệu của nhiều bước. Để xử lý đúng, cần giữ một mô hình dữ liệu chung trong flow, kiểm tra dữ liệu sau binding ở từng bước, kiểm tra lại các bất biến tổng thể trước khi xác nhận và kiểm tra các điều kiện nghiệp vụ có thể thay đổi tại thời điểm ghi dữ liệu.

## 1. Phân biệt các loại điều kiện kiểm tra

Không phải mọi quy tắc đều thuộc cùng một nơi. Hãy phân loại trước khi thiết kế validator:

| Loại điều kiện | Ví dụ | Thời điểm phù hợp |
|---|---|---|
| Điều kiện một trường | Email đúng định dạng, tên không rỗng, số lượng lớn hơn 0. | Ngay sau khi bind dữ liệu của bước nhập trường đó. |
| Điều kiện chéo trong một bước | Ngày trả sau ngày nhận; mật khẩu xác nhận trùng mật khẩu; phải nhập ít nhất email hoặc số điện thoại. | Sau khi bind toàn bộ form của view-state. |
| Điều kiện chéo giữa nhiều bước | Tổng số khách khớp số lượng giường đã chọn; quốc gia giao hàng phù hợp với mã vùng thuế đã nhập ở bước khác. | Khi đã thu thập đủ dữ liệu liên quan, thường ở bước rà soát trước xác nhận. |
| Điều kiện nghiệp vụ phụ thuộc hệ thống | Phòng còn trống, mã khuyến mại còn hiệu lực, hạn mức tài khoản chưa bị vượt. | Khi xác nhận hoặc trong service thực hiện giao dịch, và cần kiểm tra lại ngay trước khi commit. |

Điều kiện một trường thường dễ kiểm tra và trả lỗi trực tiếp cho trường đó. Điều kiện chéo cần nhìn thấy tất cả giá trị liên quan. Điều kiện nghiệp vụ phụ thuộc dữ liệu bên ngoài có thể thay đổi giữa lúc người dùng nhập form và lúc họ xác nhận, vì vậy kiểm tra ở giao diện chưa đủ để bảo đảm giao dịch thành công.

## 2. Giữ dữ liệu của nhiều bước trong cùng flow

Để kiểm tra giữa các bước, các view-state cần làm việc với cùng một đối tượng dữ liệu có vòng đời đủ dài. Một cách phổ biến là khai báo biến ở flow scope rồi đặt biến đó làm model của các view-state.

Ví dụ, flow đặt phòng dùng một đối tượng BookingDraft để giữ ngày ở, số khách và thông tin liên hệ:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking" class="com.example.booking.BookingDraft"/>

    <view-state id="enterDates"
                view="booking/dates"
                model="booking">
        <transition on="next" to="enterGuests" validate="true"/>
    </view-state>

    <view-state id="enterGuests"
                view="booking/guests"
                model="booking">
        <transition on="next" to="enterContact" validate="true"/>
    </view-state>

    <view-state id="enterContact"
                view="booking/contact"
                model="booking">
        <transition on="next" to="reviewBooking" validate="true"/>
    </view-state>

    <view-state id="reviewBooking"
                view="booking/review"
                model="booking">
        <transition on="confirm" to="confirmBooking" validate="true"/>
        <transition on="editDates" to="enterDates" validate="false"/>
        <transition on="editGuests" to="enterGuests" validate="false"/>
        <transition on="editContact" to="enterContact" validate="false"/>
    </view-state>

    <action-state id="confirmBooking">
        <evaluate expression="bookingService.confirm(booking)"/>
        <transition on="success" to="bookingConfirmed"/>
    </action-state>

    <end-state id="bookingConfirmed"/>
</flow>
~~~

Biến được khai báo bằng var có vòng đời gắn với flow scope. Mỗi view-state dùng cùng model booking nên các bước sau có thể đọc dữ liệu người dùng đã nhập ở bước trước. Nhờ vậy, validator ở màn hình rà soát có thể kiểm tra ngày ở, số khách và thông tin liên hệ cùng lúc.

Trong ứng dụng thực tế, hãy dùng một đối tượng form hoặc draft có các trường được phép bind. Không nên bind trực tiếp một entity có nhiều thuộc tính quản trị, trạng thái nội bộ hoặc trường nhạy cảm. Một binder có danh sách thuộc tính cho phép giúp giới hạn dữ liệu người dùng có thể gửi:

~~~xml
<view-state id="enterDates"
            view="booking/dates"
            model="booking">
    <binder>
        <binding property="checkInDate"/>
        <binding property="checkOutDate"/>
    </binder>
    <transition on="next" to="enterGuests" validate="true"/>
</view-state>
~~~

Chỉ khai báo các thuộc tính cần thiết cho form của bước đó. Các trường không có trong binder không nên được xem là dữ liệu do người dùng được phép cập nhật thông qua request này.

## 3. Kiểm tra điều kiện chéo trong một view-state

Spring Web Flow hỗ trợ phương thức validation trên model theo quy ước tên gắn với view-state. Khi validation được bật cho transition, phương thức có dạng validateTênViewState nhận một ValidationContext có thể được gọi để kiểm tra model. Ví dụ với view-state có id là enterDates, model có thể cung cấp phương thức validateEnterDates(ValidationContext context).

ValidationContext cho phép truy cập MessageContext. Validator thêm lỗi vào message context; nếu có lỗi validation, transition không tiếp tục và view-state hiện tại được hiển thị lại để người dùng sửa dữ liệu.

Ví dụ kiểm tra ngày trả phải sau ngày nhận:

~~~java
import java.time.LocalDate;

import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.webflow.execution.ValidationContext;

public class BookingDraft {

    private LocalDate checkInDate;
    private LocalDate checkOutDate;

    public void validateEnterDates(ValidationContext context) {
        MessageContext messages = context.getMessageContext();

        if (checkInDate == null) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("checkInDate")
                    .code("booking.checkIn.required")
                    .defaultText("Vui lòng chọn ngày nhận phòng.")
                    .build());
        }

        if (checkOutDate == null) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("checkOutDate")
                    .code("booking.checkOut.required")
                    .defaultText("Vui lòng chọn ngày trả phòng.")
                    .build());
        }

        if (checkInDate != null && checkOutDate != null
                && !checkOutDate.isAfter(checkInDate)) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("checkOutDate")
                    .code("booking.date.range")
                    .defaultText("Ngày trả phòng phải sau ngày nhận phòng.")
                    .build());
        }
    }

    // Getters and setters
}
~~~

Thuộc tính source xác định trường mà lỗi liên quan để view có thể hiển thị thông báo cạnh input tương ứng. Code giúp tra cứu thông báo trong message bundle; defaultText cung cấp nội dung dự phòng. Có thể thêm lỗi không gắn với một trường cụ thể nếu đó là lỗi của toàn bộ form.

Trong ví dụ, hai lỗi thiếu ngày được báo riêng. Quy tắc so sánh chỉ chạy khi cả hai ngày có giá trị, tránh lỗi null khi validator đánh giá dữ liệu chưa đầy đủ. Phương thức validation không nên tự lưu đặt phòng hoặc gọi dịch vụ thanh toán; nhiệm vụ của nó là phát hiện và mô tả dữ liệu không hợp lệ.

## 4. Kiểm tra điều kiện giữa nhiều bước

Khi dữ liệu đã được thu thập qua nhiều view-state, hãy thực hiện kiểm tra tổng thể ở bước rà soát trước khi xác nhận. Ví dụ, một booking chỉ hợp lệ nếu:

- Ngày nhận và ngày trả tạo thành một khoảng thời gian hợp lệ.
- Số người lớn ít nhất là một và tổng số khách không vượt quá giới hạn của loại phòng.
- Có ít nhất một phương thức liên hệ.
- Nếu người dùng chọn xuất hóa đơn, thông tin mã số thuế và quốc gia phải phù hợp.

Phương thức validateReview trên cùng model có thể kiểm tra các trường đã nhập ở những bước trước:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.webflow.execution.ValidationContext;

public class BookingDraft {

    private Integer adults;
    private Integer children;
    private Integer roomCapacity;
    private String email;
    private String phone;
    private boolean invoiceRequested;
    private String taxNumber;
    private String billingCountry;

    public void validateReview(ValidationContext context) {
        MessageContext messages = context.getMessageContext();

        int adultCount = adults == null ? 0 : adults;
        int childCount = children == null ? 0 : children;
        int totalGuests = adultCount + childCount;

        if (adultCount < 1) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("adults")
                    .code("booking.adults.minimum")
                    .defaultText("Đặt phòng cần ít nhất một người lớn.")
                    .build());
        }

        if (roomCapacity != null && totalGuests > roomCapacity) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("roomCapacity")
                    .code("booking.guests.capacity")
                    .defaultText("Số khách vượt quá sức chứa của phòng đã chọn.")
                    .build());
        }

        boolean hasEmail = email != null && !email.isBlank();
        boolean hasPhone = phone != null && !phone.isBlank();
        if (!hasEmail && !hasPhone) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("contact")
                    .code("booking.contact.required")
                    .defaultText("Vui lòng cung cấp email hoặc số điện thoại.")
                    .build());
        }

        if (invoiceRequested
                && (taxNumber == null || taxNumber.isBlank()
                    || billingCountry == null || billingCountry.isBlank())) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("taxNumber")
                    .code("booking.invoice.details.required")
                    .defaultText("Cần có mã số thuế và quốc gia xuất hóa đơn.")
                    .build());
        }
    }

    // Getters and setters
}
~~~

Đây là ví dụ minh họa các quy tắc trên một draft đã được thu thập qua nhiều bước. Trong dự án thực tế, có thể tách validator khỏi DTO để tránh model form chứa quá nhiều logic. Dù đặt validator ở đâu, nó cần nhận đủ dữ liệu của draft và đưa lỗi vào message context của flow.

View-state rà soát có thể bật validation khi người dùng xác nhận:

~~~xml
<view-state id="reviewBooking"
            view="booking/review"
            model="booking">
    <transition on="confirm" to="confirmBooking" validate="true"/>
</view-state>
~~~

Khi người dùng gửi event confirm, Spring Web Flow bind dữ liệu được phép, gọi validation cho view-state và chỉ tiếp tục transition nếu không có lỗi. Nếu điều kiện chéo giữa các bước không đạt, người dùng vẫn ở màn hình rà soát và có thể quay lại bước liên quan để sửa.

## 5. Phân biệt validation của view-state với kiểm tra nghiệp vụ cuối cùng

Validation ở view-state phù hợp với các quy tắc xác định từ dữ liệu người dùng đã nhập. Tuy nhiên, có những điều kiện phụ thuộc dữ liệu thay đổi theo thời gian hoặc cần truy cập hệ thống khác:

- Phòng có thể đã được người khác đặt sau khi người dùng mở form.
- Mã khuyến mại có thể hết hạn trước lúc xác nhận.
- Hạn mức hoặc số dư có thể thay đổi bởi giao dịch khác.
- Một tài khoản có thể bị khóa giữa hai request.

Các điều kiện này phải được kiểm tra lại ở service nghiệp vụ ngay trước thao tác ghi. Không dựa vào kết quả validation ở bước trước như một bảo đảm rằng dữ liệu bên ngoài vẫn còn đúng.

Ví dụ, service xác nhận đặt chỗ cần kiểm tra sức chứa và tình trạng phòng trong transaction phù hợp, sau đó mới ghi nhận đặt chỗ. Nếu nhiều người cùng đặt một phòng, database cần có ràng buộc hoặc cơ chế khóa để ngăn hai giao dịch cùng chiếm một tài nguyên.

Quy trình tổng thể:

~~~text
Nhập dữ liệu bước 1
       |
       v
Validate trường và điều kiện chéo bước 1
       |
       v
Nhập dữ liệu bước 2
       |
       v
Validate trường và điều kiện chéo bước 2
       |
       v
Rà soát toàn bộ draft
       |
       v
Validate điều kiện giữa các bước
       |
       v
Service xác nhận nghiệp vụ
       |
       +---- hợp lệ, ghi transaction ----> Hoàn tất
       |
       +---- dữ liệu đã thay đổi --------> Báo lỗi / chọn lại
~~~

Tách hai lớp kiểm tra giúp thông báo cho người dùng sớm, đồng thời giữ tính đúng đắn ở backend. Validation trong flow hỗ trợ trải nghiệm và điều hướng; service cùng database bảo vệ quy tắc nghiệp vụ khi có request đồng thời hoặc dữ liệu thay đổi.

## 6. Trả lỗi đúng trường và đúng bước

Khi điều kiện chéo không đạt, thông báo cần chỉ ra dữ liệu nào cần sửa. Nếu lỗi liên quan hai trường, có thể gắn lỗi vào trường cần thay đổi hoặc dùng một lỗi chung ở đầu form.

Ví dụ:

| Quy tắc | Nơi hiển thị lỗi gợi ý |
|---|---|
| Ngày trả không sau ngày nhận | Trường ngày trả |
| Mật khẩu xác nhận không trùng | Trường xác nhận mật khẩu |
| Không có email hoặc số điện thoại | Khu vực thông tin liên hệ hoặc cả hai trường |
| Tổng số khách vượt sức chứa | Khu vực số khách và lựa chọn phòng |
| Mã số thuế không phù hợp quốc gia | Khu vực thông tin hóa đơn |

Trong message context, source là tên thuộc tính mà view dùng để hiển thị lỗi. Với lỗi toàn cục, chọn một source dành riêng cho thông báo chung hoặc cách hiển thị global message mà view đã hỗ trợ. Không gắn lỗi vào một trường không liên quan chỉ để thông báo xuất hiện.

Nếu lỗi phát hiện ở màn hình rà soát nhưng cần sửa dữ liệu ở bước trước, hãy cho người dùng biết bước nào có vấn đề và cung cấp hành động quay lại bước đó. Không xóa toàn bộ draft khi validation thất bại. Sau khi người dùng sửa dữ liệu, cần chạy lại các quy tắc liên quan vì thay đổi một trường có thể làm cho kết quả kiểm tra trước đó không còn đúng.

## 7. Validation group và quy tắc theo từng bước

Một draft có thể chứa nhiều trường nhưng mỗi view-state chỉ cho phép sửa một phần. Validator cần phân biệt quy tắc của từng bước với quy tắc tổng thể:

- Bước ngày ở kiểm tra sự tồn tại và thứ tự ngày.
- Bước khách kiểm tra số lượng và sức chứa đã chọn.
- Bước liên hệ kiểm tra ít nhất một kênh liên hệ và định dạng của kênh đã nhập.
- Bước rà soát kiểm tra các bất biến kết hợp từ toàn bộ draft.

Nếu dùng Spring Validator hoặc Bean Validation, có thể tổ chức các nhóm validation theo bước hoặc gọi các validator chuyên biệt. Cần bảo đảm cấu hình của ứng dụng thực sự gọi đúng nhóm tại transition tương ứng; không giả định mọi annotation sẽ tự động chạy chỉ vì model được gắn vào view-state.

Một cách tổ chức dễ kiểm soát là tách các validator:

~~~java
public interface BookingStepValidator {
    void validate(BookingDraft draft, MessageContext messages);
}

public class DateStepValidator implements BookingStepValidator {
    @Override
    public void validate(BookingDraft draft, MessageContext messages) {
        // Kiểm tra ngày nhận, ngày trả và thứ tự ngày
    }
}

public class ReviewValidator implements BookingStepValidator {
    @Override
    public void validate(BookingDraft draft, MessageContext messages) {
        // Kiểm tra điều kiện cần dữ liệu từ nhiều bước
    }
}
~~~

Đây là cấu trúc minh họa để tổ chức mã. Có thể gọi các validator từ phương thức validation theo view-state hoặc từ một action validation chuyên biệt. Điều quan trọng là mỗi bước chỉ chạy các quy tắc phù hợp, còn các bất biến tổng thể phải được kiểm tra khi đã có đủ dữ liệu.

## 8. Xử lý dữ liệu thay đổi sau khi validation

Validation không phải chứng nhận vĩnh viễn cho một draft. Khi người dùng quay lại sửa số khách, đổi loại phòng hoặc thay ngày, các giá trị phụ thuộc có thể trở nên không hợp lệ:

- Tổng giá có thể thay đổi khi số khách hoặc ngày ở thay đổi.
- Sức chứa có thể không còn phù hợp với loại phòng mới.
- Mã khuyến mại có thể không còn áp dụng cho khoảng ngày mới.
- Thông tin hóa đơn có thể cần kiểm tra lại khi đổi quốc gia.

Không nên giữ một cờ boolean như validated=true rồi bỏ qua kiểm tra sau khi dữ liệu thay đổi. Nếu có lưu kết quả kiểm tra tốn kém, hãy gắn kết quả với phiên bản hoặc fingerprint của dữ liệu đã kiểm tra và vô hiệu hóa khi các trường liên quan thay đổi.

Các giá trị dẫn xuất như tổng tiền, thuế, chiết khấu và quyền được áp dụng ưu đãi nên được tính lại ở backend. Không tin giá trị tổng tiền do trình duyệt gửi lên. Trước khi xác nhận, service cần tính lại từ dữ liệu chuẩn và kiểm tra các quy tắc liên quan.

## 9. Các lỗi thiết kế thường gặp

### Kiểm tra từng trường nhưng bỏ qua tổ hợp

Ngày nhận hợp lệ và ngày trả hợp lệ riêng lẻ vẫn có thể tạo thành khoảng thời gian sai. Hãy đặt quy tắc so sánh ở validator có thể nhìn thấy cả hai giá trị.

### Mỗi bước dùng một object độc lập rồi làm mất dữ liệu

Nếu dữ liệu cần cho bước cuối không được lưu trong flow scope hoặc một kho lưu trữ phù hợp, validator tổng thể sẽ thiếu thông tin. Dùng một draft chung hoặc ánh xạ rõ dữ liệu từ từng bước vào đối tượng tổng hợp.

### Chỉ kiểm tra ở bước đầu

Người dùng có thể quay lại sửa dữ liệu, request có thể bị gửi lặp và trạng thái hệ thống có thể thay đổi. Hãy kiểm tra lại các điều kiện phụ thuộc dữ liệu đã thay đổi và kiểm tra nghiệp vụ tại thời điểm commit.

### Dựa hoàn toàn vào JavaScript phía trình duyệt

Client-side validation hữu ích để phản hồi nhanh nhưng có thể bị bỏ qua. Mọi quy tắc quan trọng phải được kiểm tra lại ở server.

### Gắn lỗi vào sai trường

Thông báo chung không rõ nguyên nhân khiến người dùng khó sửa. Dùng source phù hợp cho lỗi field-level và một khu vực global cho lỗi toàn form.

### Ghi dữ liệu trước khi kiểm tra toàn bộ

Nếu lưu hoặc phát sinh tác dụng phụ ở giữa quy trình, validation thất bại ở bước sau có thể để lại dữ liệu dở dang. Hãy giữ draft trong flow và chỉ thực hiện thao tác ghi cuối cùng sau khi các điều kiện cần thiết đạt; nếu nghiệp vụ cần giữ tài nguyên tạm thời, phải có cơ chế hết hạn và giải phóng.

### Giữ kết quả validation cũ sau khi người dùng sửa form

Một thay đổi ở trường có thể làm mất hiệu lực kết quả kiểm tra trước đó. Hãy chạy lại validator liên quan và tính lại giá trị phụ thuộc.

## 10. Kiểm thử điều kiện chéo và nhiều bước

Kiểm thử cần đi qua cả model validator, flow transition và service nghiệp vụ. Các trường hợp nên có:

1. **Điều kiện chéo hợp lệ.** Ngày trả sau ngày nhận; flow chuyển sang bước tiếp theo.
2. **Điều kiện chéo không hợp lệ.** Ngày trả bằng hoặc trước ngày nhận; flow ở lại view-state và thông báo gắn đúng trường.
3. **Dữ liệu qua nhiều bước.** Nhập ngày ở bước một, số khách ở bước hai; validator ở bước rà soát đọc được cả hai.
4. **Sửa dữ liệu ở bước trước.** Quay lại đổi loại phòng hoặc ngày ở; các quy tắc phụ thuộc được chạy lại.
5. **Thiếu một phần dữ liệu.** Validator không ném NullPointerException và trả lỗi dễ hiểu.
6. **Lỗi toàn cục.** Điều kiện liên quan nhiều trường hiển thị ở khu vực thông báo chung hoặc trường phù hợp.
7. **Giả mạo request.** Bỏ qua client-side validation hoặc gửi trực tiếp dữ liệu không hợp lệ; server vẫn từ chối.
8. **Dữ liệu hệ thống thay đổi.** Phòng hết chỗ sau bước rà soát; service xác nhận từ chối an toàn và flow hiển thị hướng xử lý.
9. **Request đồng thời.** Hai flow cùng xác nhận một tài nguyên; chỉ một giao dịch được commit theo quy tắc nghiệp vụ.
10. **Không phát sinh tác dụng phụ khi validation lỗi.** Không có đơn hàng, thanh toán hoặc thông báo thành công nào được tạo trước khi điều kiện cần thiết đạt.

Ở cấp flow integration test, kiểm tra state hiện tại, event được phát ra, message context và dữ liệu draft sau mỗi transition. Ở cấp service, kiểm tra transaction và ràng buộc dữ liệu để bảo đảm các quy tắc vẫn đúng khi nhiều request cùng chạy.

## 11. Quy trình thiết kế validator cho flow nhiều bước

Khi xây dựng một flow có nhiều form, hãy làm theo trình tự:

1. Liệt kê các trường và xác định bước nào thu thập từng trường.
2. Viết rõ điều kiện đơn trường, điều kiện chéo trong một bước và điều kiện chéo giữa nhiều bước.
3. Tạo một draft có vòng đời flow để lưu dữ liệu cần dùng xuyên suốt quy trình.
4. Giới hạn binding theo từng view-state để người dùng chỉ cập nhật các thuộc tính được phép.
5. Viết validator theo view-state, dùng message context để gắn lỗi vào trường hoặc thông báo chung.
6. Thêm bước rà soát và kiểm tra các bất biến tổng thể sau khi đã thu thập đủ dữ liệu.
7. Đặt kiểm tra nghiệp vụ có thể thay đổi trong service ngay trước thao tác ghi.
8. Chỉ thực hiện commit và tác dụng phụ sau khi validation phù hợp đã đạt; dùng transaction và cơ chế phục hồi cho thao tác nhiều hệ thống.
9. Kiểm thử đường đi hợp lệ, không hợp lệ, quay lại sửa, request giả mạo và request đồng thời.

## 12. Ghi nhớ

Điều kiện chéo cần nhìn thấy tất cả trường liên quan. Điều kiện giữa nhiều bước cần một draft có vòng đời đủ dài để giữ dữ liệu đã nhập, thường là flow scope. Trong Spring Web Flow, phương thức validation theo tên view-state có thể dùng ValidationContext và MessageContext để tạo lỗi có nguồn rõ ràng; khi có lỗi, transition được giữ lại để người dùng sửa.

Hãy kiểm tra quy tắc tại bước nhập để phản hồi sớm, kiểm tra tổng thể ở màn hình rà soát và kiểm tra lại các điều kiện nghiệp vụ có thể thay đổi ngay trong service trước khi commit. Kết hợp giới hạn binding, thông báo đúng trường, tính lại dữ liệu dẫn xuất và kiểm thử nhiều nhánh sẽ giúp flow nhiều bước giữ được tính nhất quán ngay cả khi người dùng quay lại sửa dữ liệu hoặc hệ thống thay đổi trong lúc họ thao tác.
