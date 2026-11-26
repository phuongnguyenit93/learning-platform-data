# Giới hạn thuộc tính được binding ở từng màn hình

Spring Web Flow tổ chức một hành trình web thành các view-state, action-state và transition. Ở mỗi view-state, người dùng có thể gửi form để cập nhật một phần dữ liệu của flow. Quá trình **binding** chuyển các tham số request thành giá trị trên model mà view-state đang sử dụng.

Nếu model chứa cả dữ liệu người dùng được phép sửa lẫn dữ liệu do máy chủ quản lý, việc bind quá rộng có thể tạo lỗ hổng mass assignment. Ví dụ, form đặt chỗ chỉ cần nhận tên khách và ngày nhận phòng, nhưng model còn có **ownerId**, **status**, **totalPrice** và **approved**. Nếu request có thể ghi các thuộc tính này, người dùng có thể thử đổi chủ sở hữu, tự xác nhận đơn hoặc sửa giá bằng cách gửi tham số không xuất hiện trên giao diện.

Spring Web Flow cho phép khai báo danh sách thuộc tính được binding bằng phần tử **binder** trong từng view-state. Hãy xem danh sách này như allowlist: mỗi màn hình chỉ nhận những trường mà người dùng được phép cập nhật ở bước đó. Kết hợp allowlist với form model chuyên biệt, validation và kiểm tra quyền ở tầng nghiệp vụ sẽ giúp dữ liệu flow an toàn hơn.

## 1. Binding diễn ra ở đâu trong một flow?

Một view-state thường khai báo model và view. Khi người dùng gửi event từ màn hình, Spring Web Flow xử lý request, bind dữ liệu được phép vào model, chạy validation nếu transition yêu cầu rồi mới quyết định có chuyển state hay không.

~~~text
Browser gửi form + event
          |
          v
      View-state
          |
          v
   Binder allowlist
          |
          v
 Chuyển đổi kiểu dữ liệu
          |
          v
      Validation
          |
     +----+-----+
     |          |
     v          v
   Có lỗi     Hợp lệ
     |          |
     v          v
  Giữ view   Transition
                |
                v
          State tiếp theo
~~~

Thuộc tính **model** xác định đối tượng được dùng làm model cho view-state. Phần tử **binder** xác định các thuộc tính trên model mà request của màn hình được phép bind. Nếu không giới hạn rõ, việc binding mặc định có thể cho phép nhiều thuộc tính của model tham gia quá trình binding hơn mức màn hình cần.

Binding và validation giải quyết hai vấn đề khác nhau:

- **Binding allowlist** xác định request được phép cập nhật thuộc tính nào.
- **Validation** xác định các giá trị đã bind có đáp ứng quy tắc dữ liệu hay không.

Một giá trị hợp lệ về định dạng vẫn có thể là thuộc tính người dùng không được phép sửa. Ngược lại, một thuộc tính được phép bind vẫn cần validation trước khi dùng.

## 2. Khai báo allowlist trong từng view-state

Trong Spring Web Flow, khai báo các thuộc tính được phép bind bên trong phần tử **binder** của view-state. Ví dụ, màn hình nhập thông tin đặt chỗ chỉ cho phép cập nhật tên khách và ngày nhận, ngày trả:

~~~xml
<var name="booking" class="com.example.booking.BookingDraft"/>

<view-state id="enterBookingDetails"
            view="booking/details"
            model="booking">
    <binder>
        <binding property="guestName" required="true"/>
        <binding property="checkInDate" required="true"/>
        <binding property="checkOutDate" required="true"/>
    </binder>

    <transition on="continue" to="enterContact" validate="true"/>
</view-state>
~~~

Trong ví dụ:

- Model của màn hình là biến **booking**.
- Chỉ ba thuộc tính được liệt kê mới thuộc allowlist của màn hình này.
- **required="true"** yêu cầu giá trị của binding đó được gửi trong request; thiếu giá trị sẽ tạo lỗi binding.
- Transition **continue** yêu cầu validation trước khi flow chuyển sang bước tiếp theo.

Nếu model còn các thuộc tính như **ownerId**, **status**, **totalPrice**, **approved** hoặc **paymentReference**, chúng không được đưa vào allowlist của màn hình này. Một request tự thêm tham số có cùng tên không thể dùng binder để cập nhật các thuộc tính bị loại khỏi danh sách.

Tên property phải khớp với thuộc tính JavaBean trên model và đường dẫn property mà Spring binding hỗ trợ. Hãy kiểm tra spelling, getter/setter và kiểu dữ liệu khi cấu hình flow; một property path không hợp lệ có thể khiến binding thất bại khi flow chạy.

## 3. Allowlist khác nhau theo từng bước

Một hành trình nhiều bước thường có nhiều nhóm dữ liệu. Không nên dùng cùng một danh sách binding rộng cho tất cả màn hình chỉ vì chúng cùng làm việc với một đối tượng draft.

Ví dụ flow đặt chỗ có ba màn hình nhập liệu:

~~~xml
<view-state id="enterBookingDetails"
            view="booking/details"
            model="booking">
    <binder>
        <binding property="guestName" required="true"/>
        <binding property="checkInDate" required="true"/>
        <binding property="checkOutDate" required="true"/>
    </binder>
    <transition on="continue" to="enterGuestCount" validate="true"/>
</view-state>

<view-state id="enterGuestCount"
            view="booking/guests"
            model="booking">
    <binder>
        <binding property="adults" required="true"/>
        <binding property="children"/>
    </binder>
    <transition on="continue" to="enterContact" validate="true"/>
</view-state>

<view-state id="enterContact"
            view="booking/contact"
            model="booking">
    <binder>
        <binding property="email"/>
        <binding property="phone"/>
    </binder>
    <transition on="review" to="reviewBooking" validate="true"/>
</view-state>
~~~

Mỗi màn hình chỉ có thể cập nhật nhóm trường được liệt kê trong binder của chính nó. Ví dụ, request từ màn hình nhập liên hệ không được phép thay đổi số khách hoặc ngày ở chỉ bằng cách gửi thêm tham số **adults** hay **checkInDate**.

Khi người dùng đến màn hình rà soát chỉ đọc, không cần gắn một model có thể bind nếu màn hình chỉ hiển thị dữ liệu hiện có. View có thể đọc dữ liệu flow để trình bày; transition xác nhận gọi action hoặc service lấy dữ liệu đã lưu trong flow. Nếu màn hình rà soát thực sự cho phép sửa một số trường, hãy khai báo model và allowlist chỉ gồm các trường đó.

## 4. Dùng form model chuyên biệt

Allowlist ở view-state là lớp kiểm soát quan trọng, nhưng thiết kế model cũng ảnh hưởng trực tiếp đến mức độ an toàn. Tránh dùng entity persistence làm model form nếu entity có nhiều trường quản trị hoặc thuộc tính nhạy cảm.

Ví dụ, entity đặt chỗ có thể chứa:

~~~java
public class Booking {
    private Long id;
    private Long ownerId;
    private String guestName;
    private LocalDate checkInDate;
    private LocalDate checkOutDate;
    private String status;
    private BigDecimal totalPrice;
    private boolean approved;
    private String paymentReference;

    // Getters and setters
}
~~~

Màn hình nhập thông tin không cần truy cập trực tiếp tất cả các thuộc tính này. Tạo một form model chỉ chứa các giá trị người dùng được phép đề xuất:

~~~java
public class BookingDetailsForm {
    private String guestName;
    private LocalDate checkInDate;
    private LocalDate checkOutDate;

    // Getters and setters
}
~~~

Service sẽ lấy entity từ database, kiểm tra quyền sở hữu và áp dụng các giá trị được phép từ form:

~~~java
public void updateBookingDetails(
        Long bookingId,
        Long currentUserId,
        BookingDetailsForm form) {

    Booking booking = bookingRepository.findById(bookingId)
            .orElseThrow(BookingNotFoundException::new);

    if (!booking.getOwnerId().equals(currentUserId)) {
        throw new AccessDeniedException("Bạn không có quyền sửa đặt chỗ này");
    }

    booking.setGuestName(form.getGuestName());
    booking.setCheckInDate(form.getCheckInDate());
    booking.setCheckOutDate(form.getCheckOutDate());

    bookingValidator.validate(booking);
    bookingRepository.save(booking);
}
~~~

Đây là cách cập nhật có chủ đích: service chỉ sao chép những giá trị mà use case cho phép. Các trường **status**, **ownerId**, **approved**, **totalPrice** và **paymentReference** tiếp tục do backend quản lý.

Trong flow, form model có thể được khai báo trong flow scope hoặc một scope phù hợp với vòng đời của hành trình. Khi chuyển bước, service nhận form model và thông tin người dùng hiện tại từ ngữ cảnh xác thực đáng tin cậy, rồi thực hiện cập nhật theo quy tắc nghiệp vụ.

## 5. Binding các thuộc tính lồng nhau

Một form có thể cần cập nhật một phần đối tượng con, ví dụ địa chỉ liên hệ. Có thể khai báo property path cụ thể:

~~~xml
<view-state id="enterAddress"
            view="booking/address"
            model="booking">
    <binder>
        <binding property="address.city" required="true"/>
        <binding property="address.postalCode" required="true"/>
    </binder>
    <transition on="continue" to="reviewBooking" validate="true"/>
</view-state>
~~~

Danh sách này chỉ thể hiện hai thuộc tính con mà màn hình được phép cập nhật. Tránh đưa toàn bộ đối tượng **address** vào allowlist nếu form chỉ cần thành phố và mã bưu chính. Nếu model có các trường như **addressId**, **verified**, **countryPolicy** hoặc thông tin kiểm soát nội bộ, hãy để service quản lý chúng.

Trước khi dùng property path lồng nhau, cần bảo đảm đối tượng cha đã được khởi tạo và có getter/setter phù hợp. Cũng cần kiểm tra quy tắc chuyển đổi kiểu, độ dài, định dạng và miền giá trị cho từng trường.

Với collection hoặc cấu trúc dữ liệu phức tạp, không nên mở binding rộng theo wildcard hoặc cho phép client tùy ý chọn index nếu không có nhu cầu rõ ràng. Hãy giới hạn phần tử và thao tác được phép, kiểm tra kích thước collection, xác minh từng phần tử thuộc đúng aggregate và kiểm soát quyền sửa ở service.

## 6. Required, conversion và validation

Thuộc tính **required** của binding giúp xác định một giá trị phải có trong request của màn hình. Nó không thay thế các quy tắc nghiệp vụ:

| Cơ chế | Kiểm tra | Ví dụ |
|---|---|---|
| Allowlist | Request có được phép bind property này không? | Màn hình liên hệ chỉ bind email và phone. |
| Required binding | Request có gửi giá trị cho binding bắt buộc không? | Màn hình ngày ở phải gửi checkInDate. |
| Conversion | Giá trị request có chuyển được sang kiểu model không? | Chuỗi ngày chuyển thành LocalDate theo converter đã cấu hình. |
| Validation | Giá trị sau binding có hợp lệ không? | Ngày trả phải sau ngày nhận. |
| Authorization | Người dùng hiện tại có quyền thực hiện thay đổi không? | Chỉ chủ đặt chỗ hoặc nhân viên có quyền mới được cập nhật hồ sơ. |

Ví dụ, một chuỗi ngày có thể chuyển đổi thành công sang LocalDate nhưng vẫn nằm trong quá khứ. Binding không kiểm tra quy tắc này; validator cần kiểm tra sau khi dữ liệu đã được bind.

Tương tự, một thuộc tính nằm trong allowlist không có nghĩa người dùng được phép sửa mọi bản ghi có thuộc tính đó. Service vẫn phải xác minh người dùng có quyền trên đối tượng đang cập nhật.

## 7. Không tin các trường ẩn và tham số ngoài form

Ẩn một trường bằng CSS, không hiển thị input hoặc dùng HTML hidden input không phải biện pháp bảo vệ. Người dùng có thể sửa DOM hoặc tự gửi request chứa bất kỳ tên tham số nào.

Ví dụ form hợp lệ:

~~~jsp
<form:form method="post" modelAttribute="booking">
    <label for="guestName">Tên khách</label>
    <form:input id="guestName" path="guestName"/>

    <label for="checkInDate">Ngày nhận phòng</label>
    <form:input id="checkInDate" path="checkInDate"/>

    <label for="checkOutDate">Ngày trả phòng</label>
    <form:input id="checkOutDate" path="checkOutDate"/>

    <button type="submit" name="_eventId_continue">Tiếp tục</button>
</form:form>
~~~

Một request bị sửa có thể gửi thêm các tham số:

~~~text
guestName=Nguyen Van A
checkInDate=2026-12-10
checkOutDate=2026-12-12
status=APPROVED
ownerId=999
totalPrice=1
approved=true
~~~

Nếu binder chỉ cho phép ba thuộc tính đầu, các tham số thêm không được bind vào model qua view-state đó. Tuy nhiên, vẫn phải bảo vệ các đường cập nhật khác và không được dùng trực tiếp tham số request chưa kiểm soát trong action hoặc service.

## 8. Binding allowlist không thay thế các lớp bảo mật khác

Giới hạn property binding bảo vệ model khỏi việc cập nhật những trường ngoài ý muốn. Nó không tự xác thực danh tính, không kiểm tra quyền truy cập bản ghi và không bảo vệ mọi loại request.

Các lớp bảo vệ cần phối hợp:

- **Authentication:** xác định người dùng hiện tại từ cơ chế đăng nhập đáng tin cậy.
- **Authorization:** kiểm tra người dùng có quyền xem, sửa hoặc xác nhận đối tượng nghiệp vụ hay không.
- **Binding allowlist:** giới hạn thuộc tính mà form của từng view-state được phép cập nhật.
- **Validation:** kiểm tra giá trị, quan hệ giữa các trường và bất biến nghiệp vụ.
- **CSRF protection:** bảo vệ request thay đổi trạng thái theo cấu hình Spring Security và cơ chế form token của ứng dụng.
- **Transaction và kiểm soát đồng thời:** bảo vệ dữ liệu khi nhiều request cùng cập nhật một đối tượng.

Không lấy **ownerId**, **role**, **userId** hoặc quyền quản trị từ form để quyết định quyền của request. Những thông tin này phải lấy từ principal hoặc nguồn dữ liệu server đã xác thực.

Event cũng là dữ liệu request. Người dùng có thể thử gửi một event khác với nút được hiển thị. Flow cần chỉ khai báo các transition hợp lệ; action và service đích vẫn phải kiểm tra điều kiện nghiệp vụ và quyền trước khi thực hiện tác dụng phụ.

## 9. Những lỗi cấu hình thường gặp

### Không khai báo binder ở màn hình có model nhạy cảm

Nếu view-state dùng một model lớn và không có allowlist, nhiều property có thể đủ điều kiện binding theo cấu hình mặc định. Hãy khai báo binder rõ ràng cho các màn hình nhận dữ liệu từ người dùng.

### Dùng cùng allowlist rộng cho mọi bước

Một form liên hệ không cần quyền cập nhật ngày đặt chỗ hoặc trạng thái thanh toán. Tạo binder riêng theo view-state và chỉ liệt kê trường của bước đó.

### Dùng entity làm form model

Entity thường có id, owner, trạng thái, giá trị tính toán và thông tin audit. Dùng DTO/form model có tập trường nhỏ để giảm nguy cơ mass assignment và tách giao diện khỏi cấu trúc persistence.

### Coi required là kiểm tra hợp lệ hoàn chỉnh

Required chỉ kiểm soát sự hiện diện của giá trị binding. Vẫn cần kiểm tra định dạng, miền giá trị, điều kiện chéo và quy tắc nghiệp vụ.

### Coi hidden input là dữ liệu đáng tin

Hidden input có thể bị thay đổi. Không dùng giá trị hidden làm căn cứ phân quyền, giá, trạng thái duyệt hoặc chủ sở hữu.

### Chỉ bảo vệ flow mà bỏ quên service

Một service có thể được gọi từ controller, job hoặc API khác. Quy tắc cho phép cập nhật trường nào và ai được cập nhật phải được bảo vệ ở tầng nghiệp vụ, không chỉ trong XML của flow.

### Property path lồng nhau quá rộng

Cho phép bind cả object con hoặc collection có thể mở ra các trường ngoài phạm vi màn hình. Liệt kê từng property cần thiết và kiểm tra cấu trúc dữ liệu trước khi bind.

## 10. Kiểm thử allowlist cho từng màn hình

Kiểm thử cần xác nhận cả trường hợp hợp lệ lẫn request cố tình gửi thêm thuộc tính. Một số trường hợp nên có:

1. **Bind trường được phép.** Gửi tên khách và ngày ở; xác nhận model nhận đúng giá trị.
2. **Gửi thêm trường bị cấm.** Thêm status, ownerId, approved và totalPrice; xác nhận các giá trị server quản lý không thay đổi.
3. **Thử ở màn hình khác.** Gửi thuộc tính chỉ được phép ở bước ngày từ màn hình liên hệ; xác nhận binder của màn hình liên hệ không cập nhật thuộc tính đó.
4. **Thiếu trường required.** Bỏ một tham số bắt buộc; xác nhận lỗi binding được hiển thị và transition không tiếp tục.
5. **Sai định dạng.** Gửi ngày không thể chuyển đổi; xác nhận lỗi conversion được xử lý rõ ràng.
6. **Giá trị đúng kiểu nhưng sai nghiệp vụ.** Gửi ngày trả trước ngày nhận; xác nhận validator từ chối.
7. **Property lồng nhau.** Gửi thành phố và mã bưu chính hợp lệ, đồng thời thử thêm trường verified; chỉ các property được liệt kê được cập nhật.
8. **Giả mạo định danh.** Thay ownerId hoặc bookingId trong request; service vẫn kiểm tra quyền theo principal và bản ghi thực tế.
9. **Gửi event không mong đợi.** Thử event không có transition tương ứng; flow không thực hiện action trái phép.
10. **Kiểm tra các đường gọi khác.** Gọi service từ đường dẫn ngoài flow; các quy tắc nghiệp vụ vẫn được áp dụng.

Ở cấp tích hợp, nên khởi chạy flow thật, gửi request có tham số hợp lệ và tham số giả mạo, sau đó kiểm tra model, message context, state hiện tại và dữ liệu trong database. Không chỉ kiểm tra HTML có ẩn trường hay không.

## 11. Quy trình thiết kế binding an toàn

Khi thêm một view-state nhận dữ liệu, hãy thực hiện theo thứ tự:

1. Xác định chính xác trường nào người dùng cần sửa ở màn hình đó.
2. Dùng form model hoặc DTO chứa tập trường phù hợp với use case.
3. Khai báo **model** trên view-state và tạo binder chỉ gồm các property được phép.
4. Đánh dấu binding bắt buộc bằng **required** khi request phải gửi giá trị đó.
5. Cấu hình converter và validator để kiểm tra kiểu, định dạng và điều kiện chéo.
6. Giữ các trường do server quản lý như id chủ sở hữu, role, trạng thái, giá và kết quả thanh toán ngoài allowlist.
7. Kiểm tra quyền trên bản ghi và áp dụng thay đổi bằng service nghiệp vụ.
8. Kiểm thử request giả mạo, binding ở từng màn hình và các đường gọi service khác.

Khi yêu cầu màn hình thay đổi, cập nhật allowlist cùng form model và kiểm thử. Không mở rộng binder chỉ để làm cho một lỗi binding biến mất trước khi xác định trường đó có thực sự thuộc quyền chỉnh sửa của người dùng hay không.

## 12. Ghi nhớ

Phần tử **binder** trong view-state giúp giới hạn các thuộc tính được binding ở từng màn hình. Hãy khai báo allowlist riêng cho mỗi bước, chỉ bind những trường người dùng được phép cập nhật và ưu tiên form model chuyên biệt thay vì entity đầy đủ. Thuộc tính **required** hỗ trợ kiểm tra sự hiện diện của dữ liệu; converter và validator xử lý kiểu, định dạng và quy tắc nghiệp vụ.

Allowlist không thay thế authentication, authorization, CSRF protection hay kiểm soát transaction. Service vẫn phải xác minh quyền trên bản ghi và chỉ áp dụng những thay đổi được nghiệp vụ cho phép. Kiểm thử bằng request tự thêm các trường bị cấm là cách xác nhận binder thực sự bảo vệ model, thay vì chỉ dựa vào giao diện người dùng.
