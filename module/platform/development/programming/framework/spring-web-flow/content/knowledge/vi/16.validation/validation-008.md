# Ghi nhận lỗi qua MessageContext

Trong một flow nhiều bước, validation không chỉ trả lời dữ liệu có hợp lệ hay không. Ứng dụng còn phải chỉ ra trường nào cần sửa, nguyên nhân là gì và thông báo nên xuất hiện ở đâu trên màn hình. Spring Web Flow cung cấp `MessageContext` để validator và các thành phần xử lý flow ghi nhận những thông điệp này theo một giao ước thống nhất.

`MessageContext` là nơi chứa các message phát sinh trong quá trình xử lý một flow request. Một message có thể là lỗi gắn với thuộc tính của model, lỗi chung của cả biểu mẫu, cảnh báo hoặc thông tin. View dùng những message đã ghi nhận để phản hồi cho người dùng; flow dựa vào trạng thái validation để quyết định có tiếp tục sang state kế tiếp hay giữ người dùng ở màn hình hiện tại.

Trong module Spring Web Flow, cơ chế này kết nối trực tiếp với form binding và validation của `view-state`. Nó giúp hành trình nhiều bước có thể phản hồi lỗi ngay tại đúng bước, thay vì để controller tự tổng hợp lỗi và điều hướng bằng những nhánh điều kiện rời rạc.

## 1. Vai trò của MessageContext

`MessageContext` là API của Spring Binding, được Spring Web Flow sử dụng để quản lý message trong ngữ cảnh thực thi. Validator nhận được context này thông qua `ValidationContext`; action hoặc thành phần tích hợp khác có thể làm việc với message context của request khi cần.

Một message thường có các thông tin sau:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Severity | Mức độ của message | `error`, `warning`, `info` |
| Source | Trường hoặc vùng mà message liên quan đến | `email`, `startDate`, hoặc không có source cho lỗi chung |
| Code | Khóa để tra nội dung trong message bundle | `profile.email.invalid` |
| Arguments | Giá trị thay đổi được chèn vào thông báo | Tên trường, giới hạn ký tự hoặc mã đơn |
| Default text | Nội dung dự phòng nếu không tra được code | `Địa chỉ email không hợp lệ.` |

Ví dụ, nếu người dùng nhập email sai định dạng, validator có thể ghi một message với severity `error`, source `email` và code `profile.email.invalid`. View có thể hiển thị thông báo cạnh trường email. Nếu ngày kết thúc sớm hơn ngày bắt đầu, validator có thể ghi lỗi gắn với `endDate` hoặc một lỗi chung cho toàn biểu mẫu, tùy cách thiết kế giao diện.

`MessageContext` không phải nơi lưu dữ liệu nghiệp vụ như hồ sơ, đơn hàng hay tài khoản. Nó lưu phản hồi validation và message phục vụ tương tác. Quy tắc nghiệp vụ và việc lưu dữ liệu vẫn thuộc service/domain layer.

## 2. Ghi message bằng MessageBuilder

Cách phổ biến để thêm message là tạo một `MessageResolver` bằng `MessageBuilder`, sau đó truyền vào `MessageContext.addMessage(...)`. Builder cho phép chỉ định severity, source, code, tham số và nội dung dự phòng.

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;

public class ProfileChecks {

    public void validateEmail(Profile profile, MessageContext messages) {
        if (profile.getEmail() == null
                || !profile.getEmail().contains("@")) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("email")
                    .code("profile.email.invalid")
                    .defaultText("Vui lòng nhập địa chỉ email hợp lệ.")
                    .build());
        }
    }
}
```

Các lời gọi trong builder có ý nghĩa:

- `error()` đánh dấu đây là lỗi validation. Có thể dùng `warning()` hoặc `info()` cho thông báo không làm validation thất bại.
- `source("email")` liên kết message với thuộc tính `email` của model. Source cần khớp với tên property mà view dùng để binding.
- `code(...)` cung cấp khóa để tra nội dung theo locale.
- `defaultText(...)` là nội dung dự phòng khi không tìm được message tương ứng.
- `build()` tạo resolver mà `MessageContext` có thể giải quyết và lưu lại.

Để thêm lỗi không gắn với một trường cụ thể, bỏ qua `source(...)`:

```java
messages.addMessage(new MessageBuilder()
        .error()
        .code("profile.address.incomplete")
        .defaultText("Vui lòng kiểm tra lại thông tin địa chỉ.")
        .build());
```

Lỗi toàn cục phù hợp với điều kiện liên quan nhiều trường hoặc không thể gắn chính xác với một input. Nếu có thể xác định trường chịu trách nhiệm, nên gắn source để người dùng biết cần sửa ở đâu.

## 3. Lấy MessageContext từ ValidationContext

Khi một `view-state` khai báo model, Spring Web Flow có thể gọi validator theo quy ước đặt tên. Phương thức validator nhận model và `ValidationContext`; từ context này, ta lấy `MessageContext` để ghi lỗi.

Ví dụ một biểu mẫu tạo hồ sơ có email và tuổi:

```java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.message.MessageContext;
import org.springframework.stereotype.Component;
import org.springframework.webflow.execution.ValidationContext;

@Component
public class ProfileValidator {

    public void validateEnterProfile(
            Profile profile, ValidationContext context) {

        MessageContext messages = context.getMessageContext();

        if (profile.getEmail() == null
                || !profile.getEmail().matches("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("email")
                    .code("profile.email.invalid")
                    .defaultText("Địa chỉ email không đúng định dạng.")
                    .build());
        }

        if (profile.getAge() < 18) {
            messages.addMessage(new MessageBuilder()
                    .error()
                    .source("age")
                    .code("profile.age.minimum")
                    .arg(18)
                    .defaultText("Tuổi phải từ {0} trở lên.")
                    .build());
        }
    }
}
```

Trong ví dụ, `validateEnterProfile` gắn với state có id `enterProfile`. `ValidationContext.getMessageContext()` trả về nơi ghi nhận message cho lần validation đó. Mỗi lỗi có source trùng với property của model để view có thể hiển thị ở đúng vị trí.

Biểu thức kiểm tra email ở đây chỉ minh họa một kiểm tra định dạng đơn giản. Trong ứng dụng thực tế, nên dùng validation phù hợp với quy tắc sản phẩm và không xem regex là cách chứng minh một địa chỉ có thể nhận thư. Nếu email phải duy nhất, validator có thể gọi service để kiểm tra sớm, nhưng service vẫn phải bảo đảm tính duy nhất khi lưu vì hai request có thể kiểm tra đồng thời.

## 4. Validator theo state và validation mặc định

Spring Web Flow tìm validator cho model theo quy ước bean name dựa trên model expression. Với model `profile`, bean thường có tên `profileValidator`. Validator có thể cung cấp phương thức chung `validate(...)` và các phương thức riêng theo state, ví dụ `validateEnterProfile(...)`.

- Phương thức `validateEnterProfile(Profile, ValidationContext)` chứa quy tắc riêng cho state `enterProfile`.
- Phương thức `validate(Profile, ValidationContext)` chứa các quy tắc cần áp dụng mặc định cho model ở những state có validation.
- Khi có cả phương thức theo state và phương thức mặc định, Web Flow áp dụng kiểm tra theo state và kiểm tra mặc định theo quy ước validator.

Việc chia validation theo state hữu ích khi cùng một model đi qua nhiều màn hình. Ví dụ, state `enterContact` chỉ kiểm tra email và số điện thoại; state `reviewProfile` có thể kiểm tra thêm các điều kiện cần thiết trước khi xác nhận. Tránh đặt mọi kiểm tra vào một phương thức khổng lồ khiến state nào cũng chạy các quy tắc không liên quan.

Khai báo validator thành Spring bean bằng component scanning hoặc cấu hình bean XML. Tên bean, tên model expression và tên state phải khớp quy ước. Nếu Web Flow không tìm thấy validator, hãy kiểm tra model expression, tên bean và phạm vi Spring application context được dùng bởi flow.

## 5. Kết hợp MessageContext với view-state

`view-state` xác định model được binding và các event có thể phát ra. Khi người dùng gửi event trên transition cần validation, Web Flow bind dữ liệu request vào model rồi chạy validation. Nếu có error message, flow giữ người dùng ở view state để sửa dữ liệu; khi validation thành công, flow mới tiếp tục transition.

```xml
<view-state id="enterProfile" model="profile">
    <binder>
        <binding property="email" required="true" />
        <binding property="age" required="true" />
    </binder>
    <transition on="continue" to="reviewProfile" />
    <transition on="cancel" to="profileCancelled" validate="false" />
</view-state>

<view-state id="reviewProfile">
    <!-- Hiển thị dữ liệu đã được kiểm tra -->
</view-state>
```

Transition `continue` sử dụng validation mặc định. Nếu validator thêm lỗi vào `MessageContext`, người dùng ở lại `enterProfile` và view có thể render các message. Transition `cancel` đặt `validate="false"` để người dùng rời màn hình mà không phải hoàn tất form. Bỏ qua validation ở transition hủy không được bỏ qua kiểm tra quyền hoặc quy tắc nghiệp vụ ở những thao tác khác.

Có thể chủ động cấu hình `validate="true"` để làm rõ ý định. Khi transition cần bỏ qua validation, dùng `validate="false"` một cách có chủ đích và kiểm tra rằng hành vi đó phù hợp với trải nghiệm người dùng.

## 6. Source và cách gắn lỗi với trường

Source là tên thuộc tính mà message muốn chỉ đến. Ví dụ model có `email`, `phoneNumber` và `address.postalCode`, thì source cần được chọn theo cách binding/view truy cập các thuộc tính đó. Với lỗi ở một trường, source cụ thể giúp giao diện đặt thông báo cạnh input và có thể đánh dấu trường cần sửa.

| Loại lỗi | Source gợi ý | Lý do |
|---|---|---|
| Email thiếu hoặc sai định dạng | `email` | Lỗi thuộc riêng trường email |
| Mã bưu chính sai định dạng | `address.postalCode` | Lỗi thuộc một thuộc tính lồng nhau |
| Ngày kết thúc trước ngày bắt đầu | `endDate` hoặc source chung | Có thể hướng người dùng đến trường cần điều chỉnh |
| Điều kiện áp dụng cho toàn biểu mẫu | Không đặt source | Không có một trường đơn lẻ chịu trách nhiệm |

Không dùng tên hiển thị như `Email address` làm source nếu property thực tế là `email`. Source là định danh thuộc tính trong model, còn nhãn thân thiện là trách nhiệm của view/message bundle.

Với một quy tắc liên trường, hãy chọn source theo cách giúp người dùng sửa dễ nhất. Ví dụ, nếu `endDate` phải sau `startDate`, có thể gắn lỗi với `endDate` và viết thông báo giải thích mối quan hệ giữa hai giá trị. Nếu cả hai giá trị cùng thiếu hoặc không thể đánh giá, một message toàn cục có thể rõ ràng hơn.

## 7. Tham số hóa message và bản địa hóa

Message nên dùng code ổn định thay vì nhúng câu chữ vào validator. `MessageBuilder.arg(...)` hoặc `args(...)` truyền giá trị thay đổi để message bundle tạo câu hoàn chỉnh theo locale.

```java
messages.addMessage(new MessageBuilder()
        .error()
        .source("password")
        .code("profile.password.minimumLength")
        .arg(12)
        .defaultText("Mật khẩu phải có ít nhất {0} ký tự.")
        .build());
```

Trong bundle tiếng Việt:

```properties
profile.password.minimumLength=Mật khẩu phải có ít nhất {0} ký tự.
profile.email.invalid=Địa chỉ email không đúng định dạng.
profile.age.minimum=Tuổi phải từ {0} trở lên.
profile.address.incomplete=Vui lòng kiểm tra lại thông tin địa chỉ.
```

Bundle tiếng Anh có thể giữ nguyên code nhưng thay câu chữ:

```properties
profile.password.minimumLength=Password must contain at least {0} characters.
profile.email.invalid=Enter a valid email address.
profile.age.minimum=Age must be at least {0}.
profile.address.incomplete=Check the address information.
```

Không ghép các mảnh câu đã dịch trong Java. Một số ngôn ngữ có trật tự từ và cách biến đổi ngữ pháp khác nhau; để cả câu trong bundle và chỉ truyền giá trị động qua tham số sẽ dễ bản địa hóa hơn. Luôn cung cấp nội dung dự phòng phù hợp khi tạo message từ code và duy trì bundle mặc định để tránh thiếu thông báo.

## 8. Đọc và phân loại message

`MessageContext` có các thao tác để thêm và truy xuất message. Những phương thức thường gặp gồm:

| Phương thức | Công dụng |
|---|---|
| `addMessage(...)` | Thêm một `MessageResolver` vào context |
| `getAllMessages()` | Lấy các message đã ghi nhận |
| `getMessagesBySource(source)` | Lấy message gắn với một source |
| `getMessagesByCriteria(criteria)` | Lọc message theo tiêu chí |
| `hasErrorMessages()` | Kiểm tra context có lỗi hay không |
| `clearMessages()` | Xóa message trong context khi có lý do phù hợp |

Ví dụ, một thành phần có thể kiểm tra context trước khi thực hiện một bước xử lý tiếp theo:

```java
if (messages.hasErrorMessages()) {
    // Giữ nguyên kết quả validation để view hiển thị và yêu cầu người dùng sửa.
    return;
}
```

Đây là minh họa cách đọc trạng thái message; trong luồng validation chuẩn của `view-state`, Spring Web Flow tự điều phối việc ở lại view khi validation có lỗi. Không cần tự viết action để thay thế cơ chế mặc định chỉ nhằm kiểm tra lỗi form.

Không nên gọi `clearMessages()` một cách tùy tiện sau khi validator vừa thêm lỗi, vì view sẽ mất phản hồi cần thiết. Chỉ xóa khi bắt đầu một chu kỳ xử lý mới hoặc khi nghiệp vụ thực sự yêu cầu loại bỏ message cũ. Việc giữ hay xóa message cần nhất quán với vòng đời view và cách ứng dụng hiển thị lỗi.

## 9. Phân biệt lỗi binding và lỗi validation

Khi người dùng gửi form, lỗi có thể xuất hiện ở nhiều giai đoạn:

1. **Binding/conversion:** dữ liệu request không chuyển được sang kiểu của model. Ví dụ nhập `abc` vào trường `age` kiểu số.
2. **Validation:** dữ liệu đã chuyển thành công nhưng vi phạm điều kiện. Ví dụ `age` là số `15` trong khi quy tắc yêu cầu ít nhất `18`.
3. **Nghiệp vụ:** dữ liệu hình thức hợp lệ nhưng thao tác không còn được phép. Ví dụ email đã tồn tại hoặc mã giảm giá đã hết hạn.

Binding và validation thường được phản ánh qua message của quá trình xử lý form. Với lỗi nghiệp vụ, service trả về kết quả có ý nghĩa hoặc exception phù hợp; action có thể chuyển kết quả đó thành message cho người dùng nếu cần. Dù validator kiểm tra sớm một quy tắc, service vẫn phải kiểm tra lại các điều kiện quan trọng tại thời điểm ghi dữ liệu vì dữ liệu có thể thay đổi giữa hai request.

Ví dụ nhập tuổi:

| Dữ liệu gửi lên | Giai đoạn | Phản hồi |
|---|---|---|
| `abc` | Chuyển đổi kiểu thất bại | Message về giá trị không phải số |
| `15` | Binding thành công, validation thất bại | Message `profile.age.minimum` |
| `25`, nhưng tài khoản không đủ điều kiện tạo hồ sơ | Nghiệp vụ thất bại | Service trả kết quả từ chối; flow hiển thị message phù hợp |

Không dùng validator của view làm lớp bảo vệ duy nhất. Client có thể bỏ qua form hoặc gọi service từ một entry point khác. Các bất biến quan trọng cần được bảo vệ ở service/domain và database.

## 10. Lỗi nghiệp vụ phát sinh sau validation

Một số lỗi chỉ xuất hiện khi service thực hiện thao tác. Ví dụ, validator kiểm tra email chưa tồn tại, nhưng một request khác tạo tài khoản cùng email ngay sau đó. Database có thể từ chối insert do unique constraint. Service cần chuyển tình huống này thành kết quả nghiệp vụ có thể xử lý; action có thể thêm message phù hợp vào context hoặc đưa người dùng đến state xử lý tương ứng.

Khi tạo message từ kết quả service, cần phân biệt lỗi có thể giải thích cho người dùng với sự cố kỹ thuật. Email đã được sử dụng là lỗi nghiệp vụ dự kiến; database mất kết nối là lỗi hạ tầng cần ghi nhận và xử lý theo cơ chế exception. Không nên bắt mọi exception rồi hiển thị chung là dữ liệu không hợp lệ.

Thông báo không nên tiết lộ thông tin nhạy cảm. Ví dụ, tùy yêu cầu bảo mật, hệ thống có thể không xác nhận công khai một email có tài khoản hay chưa. Message nên giúp người dùng biết bước tiếp theo mà không làm lộ dữ liệu của người khác.

## 11. Kiểm thử MessageContext

Kiểm thử validator cần xác minh cả nội dung lẫn cấu trúc message. Không chỉ kiểm tra rằng validator trả về hoặc không ném exception.

Các trường hợp nên có:

1. Dữ liệu hợp lệ không tạo error message.
2. Email sai định dạng tạo message có source `email`, severity `error` và code đúng.
3. Tuổi dưới giới hạn tạo message gắn với `age` và truyền tham số giới hạn chính xác.
4. Lỗi liên trường được gắn với source phù hợp hoặc message toàn cục theo thiết kế.
5. Nhiều lỗi cùng xuất hiện thì tất cả message cần thiết đều được ghi nhận.
6. Message không có bản dịch riêng vẫn có default text hoặc bundle fallback.
7. Transition có `validate="false"` cho phép rời view theo yêu cầu mà không chạy validation của model.
8. Lỗi nghiệp vụ từ service được ánh xạ thành phản hồi phù hợp, còn lỗi kỹ thuật đi theo exception handling.

Ví dụ kiểm thử ở mức validator có thể tạo một `MessageContext` giả lập hoặc dùng implementation phù hợp từ thư viện Spring Binding, gọi phương thức validator rồi kiểm tra message theo source và severity. Với kiểm thử tích hợp, khởi chạy flow, gửi event từ view-state và xác minh người dùng ở lại màn hình khi có lỗi; sau khi sửa dữ liệu, xác minh flow chuyển tiếp.

Nên kiểm thử riêng cả binding/conversion và validation. Một input không chuyển được sang kiểu model có thể khiến validator không nhận được giá trị như mong đợi; do đó không nên chỉ dùng unit test validator để kết luận form binding hoạt động đúng.

## 12. Lỗi thiết kế thường gặp

- **Không đặt source cho lỗi trường:** view không biết message thuộc input nào. Dùng tên property đúng với model binding.
- **Dùng câu chữ làm code:** message code thay đổi theo ngôn ngữ sẽ khiến validator và view khó phối hợp. Dùng khóa ổn định, câu chữ nằm trong bundle.
- **Dùng warning thay cho error khi cần chặn transition:** message không mang severity phù hợp có thể không làm validation thất bại như mong muốn. Chọn `error()` cho lỗi phải sửa trước khi tiếp tục.
- **Đưa quy tắc nghiệp vụ quan trọng chỉ vào validator:** request khác có thể bỏ qua validation. Bảo vệ bất biến ở service/domain và database.
- **Xóa message trước khi render:** người dùng không nhìn thấy lý do form bị giữ lại. Chỉ xóa khi chu kỳ message cũ thực sự kết thúc.
- **Dùng source không khớp property:** view không liên kết được lỗi với trường. Đồng bộ source với tên thuộc tính trong model.
- **Bắt mọi exception thành message validation:** lỗi kỹ thuật bị che khuất và khó vận hành. Phân loại kết quả nghiệp vụ với exception.
- **Tạo một validator khổng lồ cho mọi state:** các quy tắc không liên quan chạy ở sai màn hình. Chia phương thức theo state và dùng validation mặc định cho quy tắc thực sự chung.

## 13. Nguyên tắc áp dụng

1. Lấy `MessageContext` từ `ValidationContext` trong validator của `view-state`.
2. Tạo message bằng `MessageBuilder` với severity, source, code, tham số và default text phù hợp.
3. Gắn lỗi trường với đúng tên property; dùng message toàn cục cho lỗi không thuộc một input cụ thể.
4. Chia validation theo state để mỗi màn hình chỉ kiểm tra những điều kiện liên quan.
5. Để Spring Web Flow điều phối validation của transition; chỉ bỏ qua bằng `validate="false"` khi hành trình yêu cầu.
6. Phân biệt lỗi binding, validation và lỗi nghiệp vụ; bảo vệ quy tắc quan trọng ở service/domain.
7. Kiểm thử message theo source, severity, code, tham số, locale và hành vi transition.

`MessageContext` giúp validation trở thành phản hồi có cấu trúc trong hành trình Spring Web Flow. Khi validator ghi đúng source và severity, message dùng code ổn định, còn view-state điều phối việc ở lại hay chuyển bước, người dùng sẽ biết cần sửa điều gì và ứng dụng giữ được ranh giới rõ ràng giữa tương tác, validation và nghiệp vụ.
