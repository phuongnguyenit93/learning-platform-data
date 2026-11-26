# Tắt binding cho sự kiện bằng bind=false

Trong chương **Liên kết biểu mẫu**, thuộc tính `bind` trên một transition cho phép quyết định dữ liệu của view có được bind vào model khi transition đó được thực thi hay không. Mặc định, transition từ view state thường bind dữ liệu form vào model trước khi tiếp tục. Khi một sự kiện không cần sử dụng dữ liệu người dùng vừa nhập, chẳng hạn `cancel` hoặc một thao tác bỏ qua form, có thể đặt `bind="false"` riêng cho transition đó.

Module `SPRING_WEB_FLOW` dùng state, event, transition và subflow để mô hình hóa hành trình web nhiều bước; đồng thời thực hành form binding, validation, scope, phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng. Vì vậy, kiểm soát binding theo từng sự kiện giúp tránh việc một thao tác điều hướng vô tình ghi dữ liệu chưa hoàn chỉnh vào model. Nó cũng làm rõ hợp đồng của mỗi nút trên form: sự kiện nào cần nhận dữ liệu, sự kiện nào chỉ cần điều hướng.

## 1. Binding xảy ra ở đâu trong view state?

Một `view-state` thường gắn với một view và một model. Ví dụ, view nhập thông tin đặt chỗ có thể bind các trường form vào đối tượng `booking`. Khi người dùng gửi một event như `continue`, Spring Web Flow xử lý transition tương ứng. Với binding được bật, dữ liệu gửi từ view được ánh xạ vào model theo quy tắc binding và sau đó validation có thể được thực hiện trước khi flow chuyển sang state tiếp theo.

Ví dụ đơn giản:

```xml
<view-state id="enterDetails"
            view="booking/details"
            model="booking">
    <transition on="continue" to="review" />
</view-state>
```

Transition `continue` dùng hành vi binding mặc định. Nếu người dùng sửa tên hoặc ngày đặt chỗ rồi gửi form, các giá trị được bind vào model `booking` trước khi flow tiếp tục, theo cấu hình binding và validation của ứng dụng.

Binding hữu ích khi transition cần sử dụng dữ liệu vừa nhập. Tuy nhiên, không phải event nào trên view cũng mang ý nghĩa cập nhật model. Nút hủy, quay lại hoặc bỏ qua có thể chỉ yêu cầu điều hướng. Nếu vẫn bind form ở những event đó, dữ liệu chưa hoàn chỉnh hoặc không hợp lệ có thể làm thay đổi model, gây lỗi validation hoặc tạo ra thay đổi mà người dùng không định xác nhận.

## 2. Dùng `bind="false"` trên đúng transition

Đặt `bind="false"` trực tiếp trên transition cần bỏ qua quá trình bind dữ liệu view vào model. Các transition khác trong cùng view state vẫn có thể giữ binding mặc định.

```xml
<view-state id="enterDetails"
            view="booking/details"
            model="booking">

    <transition on="continue" to="review" />

    <transition on="cancel"
                to="cancelled"
                bind="false"
                validate="false" />
</view-state>
```

Trong ví dụ:

- Khi người dùng gửi `continue`, dữ liệu form được bind vào `booking`; validation theo cấu hình của transition được thực hiện trước khi đi tới `review`.
- Khi người dùng gửi `cancel`, `bind="false"` ngăn dữ liệu form được bind vào model trong transition này. `validate="false"` thể hiện rõ rằng nhánh hủy không cần validation form trước khi điều hướng tới `cancelled`.

`bind` là thuộc tính của transition, không phải một thiết lập tắt binding cho toàn bộ flow hoặc toàn bộ view state. Đây là điểm quan trọng: cùng một form có thể có nút tiếp tục cần binding và nút hủy không cần binding.

## 3. Binding và validation là hai quyết định liên quan nhưng khác nhau

Binding trả lời câu hỏi: dữ liệu gửi từ view có được ánh xạ vào model ở transition này không? Validation trả lời câu hỏi: các ràng buộc trên model có được kiểm tra ở thời điểm này không?

Spring Web Flow cho phép cấu hình cả `bind` và `validate` trên transition. Với hành vi mặc định thông thường, binding và validation được bật cho transition từ view state. Khi thiết kế nhánh đặc biệt, hãy quyết định cả hai thuộc tính theo mục đích nghiệp vụ.

| Nhu cầu của event | `bind` | `validate` | Ý nghĩa |
|---|---:|---:|---|
| Tiếp tục với dữ liệu form vừa nhập | `true` | `true` | Bind dữ liệu và kiểm tra hợp lệ trước khi chuyển bước |
| Quay lại nhưng muốn giữ dữ liệu người dùng vừa nhập | `true` | `false` | Cập nhật model nhưng bỏ qua validation ở bước quay lại |
| Hủy form, bỏ qua mọi thay đổi đang nhập | `false` | `false` | Không bind dữ liệu form và không yêu cầu validation form cho event này |
| Chuyển bước không nhận dữ liệu form nhưng vẫn cần kiểm tra model đã có | `false` | `true` | Không bind dữ liệu gửi lên; validation được yêu cầu theo cấu hình transition |

Tổ hợp cuối cần được dùng có chủ đích: model có thể chứa dữ liệu đã có từ trước, và validation có thể kiểm tra dữ liệu đó dù không bind request hiện tại. Cách validation được gọi và các ràng buộc áp dụng phụ thuộc cấu hình/version, vì vậy cần xác minh bằng kiểm thử với phiên bản Spring Web Flow đang sử dụng.

Không nên xem `bind="false"` là cách tắt validation cho mọi tình huống. Nếu event không cần kiểm tra dữ liệu form, đặt `validate="false"` tường minh để hợp đồng dễ đọc. Ngược lại, nếu vẫn cần kiểm tra model hiện tại, hãy giữ validation theo chủ đích và xác nhận hành vi bằng test.

## 4. Trường hợp điển hình: nút Cancel

Giả sử form đặt chỗ có các trường bắt buộc như tên người đặt, ngày nhận phòng và số khách. Người dùng nhập dở rồi quyết định hủy. Nếu transition `cancel` vẫn bind và validate như transition `continue`, flow có thể giữ lại dữ liệu dở dang hoặc từ chối cho hủy vì form không hợp lệ.

```xml
<view-state id="editBooking"
            view="booking/edit"
            model="booking">

    <transition on="continue" to="reviewBooking"
                bind="true" validate="true" />

    <transition on="cancel" to="cancelBooking"
                bind="false" validate="false" />
</view-state>

<action-state id="cancelBooking">
    <evaluate expression="bookingService.cancelDraft(booking)" />
    <transition on="success" to="bookingCancelled" />
    <transition on="error" to="cancelError" />
</action-state>
```

Ở đây, thao tác hủy không cần các trường người dùng đang nhập. Flow bỏ qua binding và validation của form cho event `cancel`, sau đó xử lý hủy bản nháp ở action-state. Service vẫn phải kiểm tra bản nháp thuộc người dùng hiện tại, trạng thái có thể hủy và các điều kiện nghiệp vụ khác. `bind="false"` không thay thế authorization hoặc validation nghiệp vụ.

Nếu thao tác hủy chỉ cần kết thúc flow mà không phải gọi service, transition có thể đi thẳng tới end state. Nếu hủy cần ghi dữ liệu, thu hồi tài nguyên hoặc gọi hệ thống ngoài, hãy xử lý qua service có transaction và cơ chế chống lặp phù hợp.

## 5. Trường hợp Back: giữ hay bỏ dữ liệu vừa nhập?

Nút `back` có hai cách hiểu khác nhau tùy trải nghiệm người dùng.

**Quay lại và giữ dữ liệu vừa nhập:** người dùng muốn sửa một lựa chọn trước đó nhưng vẫn giữ thông tin đã điền ở bước hiện tại. Có thể bind dữ liệu nhưng bỏ qua validation để họ quay lại ngay cả khi form hiện tại chưa hoàn chỉnh:

```xml
<transition on="back"
            to="chooseOptions"
            bind="true"
            validate="false" />
```

**Quay lại và bỏ các thay đổi của bước hiện tại:** người dùng muốn trở về trạng thái model trước khi sửa form. Có thể tắt binding:

```xml
<transition on="back"
            to="chooseOptions"
            bind="false"
            validate="false" />
```

Hai hành vi này khác nhau về dữ liệu được giữ lại. Cần chọn theo yêu cầu sản phẩm và giải thích nhất quán qua nhãn nút, thông báo hoặc xác nhận nếu việc bỏ thay đổi có thể gây bất ngờ.

Lưu ý rằng `bind="false"` chỉ ngăn dữ liệu của view được bind vào model trong transition đó. Nó không tự khôi phục model về snapshot trước khi hiển thị form. Nếu model đã bị thay đổi bởi action khác hoặc dữ liệu đã được lưu ở service, cần cơ chế rollback/khôi phục riêng.

## 6. Những gì `bind="false"` không làm

Thuộc tính này có phạm vi hẹp: kiểm soát binding dữ liệu view cho một transition. Nó không phải cơ chế bảo mật tổng quát hoặc thao tác hoàn tác.

- Không ngăn event được gửi tới flow và không tự hủy transition.
- Không xóa các giá trị đã có trong model hoặc `flowScope`.
- Không khôi phục bản sao model trước đó.
- Không ngăn action trong transition hoặc state tiếp theo đọc dữ liệu hiện có.
- Không ngăn action tự đọc request parameters qua `externalContext`.
- Không thay thế kiểm tra quyền, CSRF protection, kiểm tra dữ liệu trong service hoặc quy tắc domain.
- Không thay đổi binding của những transition khác trong cùng view state.

Nếu action sau transition tự đọc tham số HTTP, dữ liệu đó vẫn có thể được truy cập dù binding form đã tắt. Do đó, không dùng `bind="false"` để bảo vệ một trường nhạy cảm hoặc để ngăn client gửi dữ liệu giả mạo. Mọi dữ liệu do client cung cấp phải được kiểm tra nguồn gốc, định dạng và quyền sử dụng ở ranh giới nghiệp vụ.

## 7. Kết hợp với model, allowed fields và validation

`bind="false"` điều khiển việc binding cho toàn bộ view model của transition. Với transition cần binding, vẫn phải giới hạn thuộc tính được phép cập nhật. Không nên cho phép một form gửi trực tiếp mọi thuộc tính của entity, đặc biệt các trường như `ownerId`, `approved`, `totalPrice`, `role` hoặc trạng thái thanh toán.

Một thiết kế an toàn thường dùng DTO hoặc form object riêng:

```java
public class BookingForm {
    private String guestName;
    private LocalDate checkIn;
    private int guestCount;

    // getters and setters
}
```

Sau khi form được bind và validate, service tải dữ liệu đáng tin cậy, kiểm tra quyền và áp dụng các trường được phép lên domain object. Cách này tránh mass assignment và giữ model trong flow ở mức dữ liệu cần thiết cho hành trình.

Ví dụ định nghĩa flow có thể dùng form object làm model:

```xml
<var name="bookingForm" class="com.example.web.BookingForm" />

<view-state id="editBooking"
            view="booking/edit"
            model="bookingForm">
    <transition on="continue" to="reviewBooking"
                bind="true" validate="true" />
    <transition on="cancel" to="cancelled"
                bind="false" validate="false" />
</view-state>
```

Validation ở view state giúp phản hồi sớm cho người dùng, nhưng không thay thế kiểm tra ở service/domain layer. Dữ liệu có thể thay đổi giữa lúc hiển thị form và lúc lưu; service vẫn cần xác minh lại các điều kiện quan trọng tại thời điểm ghi.

## 8. Xử lý trường hợp binding lỗi

Khi binding được bật, dữ liệu gửi lên có thể không chuyển đổi được sang kiểu của model. Ví dụ, người dùng gửi chuỗi không phải ngày hợp lệ cho trường `checkIn`, hoặc gửi giá trị không phải số cho `guestCount`. Spring Web Flow kết hợp cơ chế binding/conversion và validation để đưa lỗi vào message context, cho phép view hiển thị thông báo phù hợp.

Nếu event `continue` cần dữ liệu đó, lỗi binding phải ngăn flow chuyển sang bước review. Người dùng có thể sửa form rồi gửi lại. Nếu event `cancel` không cần dữ liệu form, `bind="false"` cho phép flow đi theo nhánh hủy mà không phụ thuộc vào việc các trường đang nhập có chuyển đổi được hay không.

Hãy phân biệt:

- **Lỗi chuyển đổi/binding:** dữ liệu không thể ánh xạ sang kiểu thuộc tính model.
- **Lỗi validation:** dữ liệu đã bind nhưng vi phạm ràng buộc, ví dụ ngày nhận phòng ở quá khứ.
- **Lỗi nghiệp vụ:** dữ liệu hợp lệ về mặt hình thức nhưng không đáp ứng quy tắc như hết phòng hoặc người dùng không có quyền sửa booking.

Binding và validation thuộc giai đoạn xử lý view transition; lỗi nghiệp vụ và quyền truy cập vẫn cần được xử lý trong service/domain layer. Nếu nhánh hủy có tác dụng phụ, service hủy phải độc lập với dữ liệu form đang lỗi.

## 9. Kiểm thử hành vi `bind=false`

Kiểm thử nên xác minh dữ liệu model trước và sau từng event, không chỉ kiểm tra state cuối cùng. Một test cho `cancel` cần chứng minh dữ liệu người dùng gửi lên không được bind vào model; một test cho `continue` cần chứng minh binding vẫn diễn ra bình thường.

| Kịch bản | Điều cần xác minh |
|---|---|
| `continue` với dữ liệu hợp lệ | Dữ liệu form được bind, validation thành công và flow tới state review |
| `continue` với dữ liệu không hợp lệ | Flow ở lại view state; lỗi binding/validation được hiển thị |
| `cancel` với dữ liệu form hợp lệ | Flow rời view state mà không cập nhật model từ dữ liệu submit |
| `cancel` với dữ liệu sai định dạng | Nhánh hủy vẫn hoạt động vì không cần binding form; xác minh validation được cấu hình đúng |
| `back` với bind=true, validate=false | Dữ liệu đã nhập được giữ theo model và không bị chặn bởi validation form |
| `back` với bind=false | Dữ liệu submit không ghi vào model; lưu ý đây không phải rollback snapshot |
| Action sau transition đọc request parameter | Kiểm tra riêng dữ liệu đọc trực tiếp từ request vì `bind=false` không chặn đường này |
| Hai execution hoặc nhiều tab | Model và dữ liệu flow không bị trộn giữa các lần thực thi |

Ví dụ các khẳng định cần có trong test (mã giả):

```java
// Model ban đầu có guestName = "An".
// Người dùng gửi cancel cùng guestName = "Binh".
assertThat(flow.currentState()).isEqualTo("cancelled");
assertThat(flow.flowScope().get("bookingForm").getGuestName())
        .isEqualTo("An");

// Với continue, dữ liệu gửi lên được bind trước khi tới review.
assertThat(continueFlow.currentState()).isEqualTo("reviewBooking");
assertThat(continueFlow.flowScope().get("bookingForm").getGuestName())
        .isEqualTo("Binh");
```

Đây là mã giả mô tả điều cần kiểm tra; cách khởi chạy execution, gửi event và truy cập flow scope phải dùng test support/API của phiên bản Spring Web Flow trong dự án. Có thể dùng một form object khởi tạo sẵn và kiểm tra giá trị trước/sau transition, kết hợp kiểm thử tích hợp để xác nhận cấu hình XML thực sự được áp dụng.

## 10. Lỗi thiết kế thường gặp

### Tắt binding cho cả view state

Một form có nút `continue` cần dữ liệu nhưng developer tắt binding ở mọi transition hoặc xử lý binding thủ công ở nhiều nơi. Kết quả là model không nhận giá trị như mong đợi. Hãy đặt `bind="false"` chỉ trên event không cần dữ liệu.

### Cho rằng `bind=false` tự hoàn tác thay đổi

Nếu model đã được cập nhật trước đó hoặc service đã lưu dữ liệu, tắt binding ở event hiện tại không hoàn tác những thay đổi đó. Dùng bản nháp, transaction hoặc thao tác khôi phục rõ ràng nếu nghiệp vụ yêu cầu.

### Dùng `bind=false` như một biện pháp bảo mật

Client vẫn có thể gửi request parameters, headers hoặc event khác. Action có thể đọc trực tiếp các giá trị này. Phân quyền và kiểm tra dữ liệu phải được thực hiện ở service/domain layer; bảo vệ request bằng cơ chế CSRF và security phù hợp.

### Nhầm lẫn giữa Back và Cancel

Back có thể cần giữ dữ liệu người dùng đã nhập để quay lại sửa bước trước; Cancel thường có ý nghĩa bỏ thay đổi. Hai event không nhất thiết dùng cùng cấu hình `bind` và `validate`. Hãy mô tả hành vi mong đợi và kiểm thử riêng.

### Để validation chặn thao tác điều hướng không cần dữ liệu form

Một nút hủy không nên bị chặn bởi trường bắt buộc đang trống nếu nghiệp vụ cho phép hủy. Cấu hình `bind` và `validate` phù hợp cho event đó, đồng thời bảo đảm service hủy vẫn kiểm tra quyền và trạng thái nghiệp vụ.

## 11. Checklist trước khi dùng `bind=false`

Với mỗi transition từ view state, hãy trả lời:

1. Event có cần dữ liệu form mới nhất không?
2. Nếu không bind, model hiện tại có đủ dữ liệu cho action và state tiếp theo không?
3. Event có cần validation form không, hay chỉ cần điều hướng?
4. Nếu quay lại, người dùng mong muốn giữ hay bỏ dữ liệu vừa nhập?
5. Có action nào đọc request parameters trực tiếp và cần kiểm tra chúng riêng không?
6. Service có kiểm tra quyền, trạng thái nghiệp vụ và dữ liệu tại thời điểm ghi không?
7. Test đã xác minh model không bị cập nhật ở nhánh `bind=false` và vẫn bind ở nhánh cần thiết chưa?

`bind="false"` có ích nhất khi được dùng như một quyết định theo event: chỉ bỏ binding ở nơi dữ liệu form không thuộc trách nhiệm của sự kiện đó. Cấu hình rõ cả `bind` và `validate` làm flow dễ đọc hơn, đặc biệt với các nút Continue, Back và Cancel có hành vi khác nhau.

## Kết luận

`bind="false"` trên transition của view state tắt việc bind dữ liệu view vào model cho chính event đó. Nó hữu ích với thao tác hủy hoặc điều hướng không cần dữ liệu form, giúp người dùng rời form ngay cả khi các trường đang nhập chưa hoàn chỉnh. Những transition khác vẫn có thể bind và validate bình thường.

Hãy quyết định riêng binding và validation cho từng event, phân biệt hành vi Back với Cancel, và nhớ rằng tắt binding không xóa dữ liệu cũ, không rollback model và không thay thế bảo mật hay kiểm tra nghiệp vụ. Kiểm thử giá trị model trước/sau từng transition sẽ xác nhận `bind=false` đang bảo vệ đúng ranh giới dữ liệu mà flow cần.
