# Xử lý giá trị thiếu, null và lỗi đánh giá biểu thức

Trong chương **Biểu thức**, bài này giải quyết những tình huống thường gặp khi Spring Web Flow đọc dữ liệu từ form, scope hoặc service: một thuộc tính chưa được tạo, một giá trị có mặt nhưng bằng `null`, một chuỗi rỗng, hoặc một biểu thức không thể đánh giá. Phân biệt đúng các trường hợp này giúp flow rẽ nhánh có chủ đích, hiển thị thông báo phù hợp và tránh để lỗi runtime làm gián đoạn cả hành trình.

Spring Web Flow dùng biểu thức để đọc và ghi dữ liệu scope, gọi bean nghiệp vụ, kiểm tra điều kiện và đưa kết quả vào state tiếp theo. Trong các cấu hình hiện đại, Spring Expression Language (SpEL) thường là ngôn ngữ biểu thức được sử dụng; parser có thể được cấu hình và cú pháp cụ thể cần tương thích với phiên bản Spring Web Flow/Spring Framework của ứng dụng.

## 1. Phân biệt missing, null, empty và invalid

Các trạng thái sau không giống nhau và không nên được xử lý bằng một giá trị mặc định chung:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Missing | Thuộc tính hoặc khóa chưa được cung cấp, chưa khởi tạo hoặc không tồn tại trong dữ liệu đầu vào. | Form không gửi `phone`; map không có khóa `email`. |
| `null` | Có tham chiếu hoặc khóa nhưng giá trị hiện tại là `null`. | `flowScope.booking` đã được đặt thành `null`; `form` có khóa `email` với giá trị null. |
| Empty | Có giá trị nhưng nội dung rỗng hoặc không có phần tử. | `""`, chuỗi chỉ có khoảng trắng, danh sách rỗng. |
| Invalid | Có giá trị nhưng sai định dạng, kiểu hoặc quy tắc nghiệp vụ. | Ngày `31/02`, email sai định dạng, mã đặt lịch không tồn tại. |
| Evaluation error | Bản thân biểu thức không thể phân tích hoặc thực thi. | Sai cú pháp, gọi phương thức không tồn tại, truy cập thuộc tính trên đối tượng null. |

Ví dụ, `email == null` không có nghĩa giống `email == ''`. Một email rỗng có thể được chấp nhận nếu trường là tùy chọn, nhưng email sai định dạng cần báo lỗi. Tương tự, một `bookingId` không được gửi có thể yêu cầu bắt đầu lại flow; một ID được gửi nhưng không tìm thấy bản ghi có thể dẫn đến state thông báo “không tìm thấy”.

Trước khi viết biểu thức, hãy xác định ý nghĩa nghiệp vụ của từng trường: bắt buộc hay tùy chọn, có thể vắng mặt hay không, giá trị rỗng có hợp lệ không, và nếu không hợp lệ thì người dùng có thể sửa hoặc thử lại như thế nào.

## 2. Nhận diện giá trị thiếu trong dữ liệu dạng map

Scope của Spring Web Flow cung cấp dữ liệu theo tên thuộc tính. Với một đối tượng `Map` do ứng dụng lưu trong scope, cần phân biệt khóa chưa có và khóa có giá trị null bằng `containsKey`.

Giả sử `flowScope.form` là một `java.util.Map`:

```xml
<decision-state id="checkEmailInput">
    <if test="flowScope.form != null and flowScope.form.containsKey('email')"
        then="emailWasSubmitted"
        else="emailWasOmitted" />
</decision-state>
```

Điều kiện đầu tiên bảo đảm map tồn tại. Điều kiện thứ hai chỉ kiểm tra khóa `email` có được gửi/lưu hay không. Nếu khóa có mặt nhưng giá trị của nó là null, biểu thức vẫn chọn `emailWasSubmitted`; state đó có thể kiểm tra giá trị riêng.

Có thể đọc giá trị theo khóa:

```xml
<evaluate expression="flowScope.form['email']"
          result="flowScope.emailInput" />
```

Nếu chỉ kiểm tra `flowScope.form['email'] != null`, ta không phân biệt được khóa bị thiếu với khóa có giá trị null. Khi sự khác biệt đó có ý nghĩa, kiểm tra `containsKey` trước. Với object thông thường, truy cập một thuộc tính không tồn tại có thể gây lỗi đánh giá biểu thức; `containsKey` của map không phải cơ chế để che lỗi gõ sai tên thuộc tính trên một JavaBean.

## 3. Dùng guard để tránh dereference null

Một lỗi phổ biến là truy cập thuộc tính lồng nhau khi đối tượng cha chưa được tạo:

```text
flowScope.booking.customer.email
```

Nếu `booking` hoặc `customer` bằng null, biểu thức có thể ném lỗi khi truy cập thuộc tính tiếp theo. Trước hết, hãy kiểm tra từng đối tượng cần thiết bằng điều kiện có short-circuit:

```xml
<decision-state id="checkBooking">
    <if test="flowScope.booking != null and flowScope.booking.customer != null"
        then="showCustomer"
        else="collectBooking" />
</decision-state>
```

Toán tử `and` chỉ cần đánh giá vế phải khi vế trái đúng. Vì vậy, khi `booking` là null, phần truy cập `booking.customer` không được thực hiện. Guard thể hiện rõ điều kiện để state tiếp theo sử dụng dữ liệu.

SpEL cũng hỗ trợ toán tử điều hướng an toàn `?.` trong các phiên bản tương thích:

```xml
<evaluate expression="flowScope.booking?.customer?.email"
          result="flowScope.customerEmail" />
```

Nếu `booking` hoặc `customer` là null, chuỗi truy cập an toàn trả về null thay vì dereference đối tượng null. Hãy dùng `?.` ở từng đoạn có thể null. Ví dụ `booking?.customer.email` vẫn có thể lỗi nếu `customer` là null, bởi phần `.email` sau đó không được bảo vệ. Safe navigation chỉ xử lý receiver null; nó không sửa lỗi chính tả tên thuộc tính, phương thức không tồn tại hoặc ngoại lệ phát sinh bên trong phương thức được gọi.

Với điều kiện rẽ nhánh, guard thường dễ đọc hơn việc gộp một biểu thức dài. Khi có nhiều cấp dữ liệu tùy chọn, tách thành các decision state nhỏ hoặc gọi một bean kiểm tra chuyên biệt để giữ logic dễ kiểm thử.

## 4. Cung cấp giá trị mặc định có chủ đích

Khi một giá trị thực sự tùy chọn, có thể dùng Elvis operator `?:` của SpEL để cung cấp mặc định nếu biểu thức bên trái là null:

```xml
<evaluate expression="flowScope.booking?.customer?.email ?: 'Chưa cung cấp email'"
          result="flowScope.emailLabel" />
```

Trong ví dụ này, email được dùng nếu có giá trị; nếu chuỗi truy cập trả về null, nhãn mặc định được gán. Giá trị mặc định phù hợp cho nội dung hiển thị, bộ lọc tùy chọn hoặc tham số có quy tắc fallback rõ ràng.

Elvis không thay thế validation. Một chuỗi rỗng vẫn là một giá trị khác null; nếu muốn coi chuỗi rỗng hoặc chỉ có khoảng trắng là chưa nhập, cần kiểm tra riêng:

```xml
<decision-state id="checkEmailValue">
    <if test="flowScope.emailInput != null and !flowScope.emailInput.trim().isEmpty()"
        then="validateEmail"
        else="emailOptionalOrMissing" />
</decision-state>
```

Điều kiện này giả định `emailInput` là chuỗi. Nếu kiểu dữ liệu không chắc chắn, hãy chuyển đổi và kiểm tra kiểu ở tầng binding/service trước khi gọi `trim()`. Không dùng mặc định như `0`, `false` hoặc chuỗi rỗng để che một dữ liệu bắt buộc bị thiếu; việc đó có thể khiến flow tiếp tục với dữ liệu sai nhưng trông có vẻ hợp lệ.

Có thể dùng toán tử ba ngôi khi cần chọn một trong hai giá trị:

```xml
<evaluate expression="flowScope.booking != null ? flowScope.booking.id : null"
          result="flowScope.bookingId" />
```

Nếu điều kiện hoặc biểu thức phức tạp, tách ra thành một biến kết quả hoặc bean chuyên trách. Biểu thức trong flow nên mô tả quyết định điều hướng và việc chuyển dữ liệu, không chứa toàn bộ quy tắc nghiệp vụ.

## 5. Phân biệt lỗi binding, validation và lỗi biểu thức

Ba nhóm lỗi có nguồn gốc và cách xử lý khác nhau:

| Nhóm | Xảy ra khi | Cách xử lý |
| --- | --- | --- |
| Binding/conversion error | Request có dữ liệu nhưng không chuyển được sang kiểu thuộc tính của model. | Hiển thị lỗi tại field, giữ view state để người dùng sửa. |
| Validation error | Dữ liệu đã bind được nhưng không đáp ứng quy tắc nhập liệu hoặc nghiệp vụ. | Ghi thông báo vào message context, quay lại form hoặc chuyển đến state giải thích. |
| Expression evaluation error | Biểu thức không phân tích được hoặc không thể thực thi tại runtime. | Sửa cấu hình/biểu thức; với lỗi runtime dự kiến, xử lý ở ranh giới phù hợp và có nhánh an toàn. |

Ví dụ, người dùng nhập `abc` vào trường ngày có kiểu `LocalDate` có thể gây lỗi chuyển đổi trước khi flow gọi validator. Ngày `2026-02-31` có thể không chuyển đổi được hoặc được parser xử lý thành lỗi binding tùy converter. Ngày hợp lệ về định dạng nhưng nằm ngoài thời hạn đặt là lỗi validation nghiệp vụ. Còn biểu thức gọi `flowScope.booking.customer.emial` với tên thuộc tính sai là lỗi đánh giá biểu thức, không phải lỗi người dùng nhập form.

Không nên bắt mọi lỗi rồi hiển thị như “Dữ liệu không hợp lệ”. Người dùng chỉ có thể sửa lỗi nhập liệu; lỗi cấu hình hoặc lỗi lập trình cần được ghi nhận và xử lý như lỗi hệ thống.

## 6. Nhận diện lỗi phân tích và lỗi thực thi

Biểu thức có thể thất bại ở hai thời điểm:

**Lỗi phân tích (parse error)** xuất hiện khi parser không hiểu cú pháp. Ví dụ thiếu dấu nháy, ngoặc không cân bằng hoặc dùng toán tử không được phiên bản parser hỗ trợ. Lỗi thường xuất hiện khi flow được nạp hoặc khi biểu thức được phân tích lần đầu. Hãy kiểm tra flow XML, dấu nháy trong thuộc tính XML và phiên bản Spring EL.

**Lỗi thực thi (evaluation error)** xuất hiện khi cú pháp hợp lệ nhưng dữ liệu hoặc đối tượng lúc chạy không đáp ứng biểu thức. Các nguyên nhân thường gặp gồm:

- Receiver null ở một đoạn truy cập thuộc tính hoặc gọi phương thức.
- Thuộc tính hoặc phương thức không tồn tại trên kiểu đối tượng thực tế.
- Bean được tham chiếu chưa được đăng ký hoặc tên bean sai.
- Phương thức được gọi ném exception.
- Giá trị trả về không chuyển đổi được sang kiểu đích của `result` hoặc thuộc tính model.
- Dữ liệu scope không còn ở thời điểm biểu thức được đánh giá.

Ví dụ một action gọi service:

```xml
<action-state id="loadBooking">
    <evaluate expression="bookingService.findById(flowScope.bookingId)"
              result="flowScope.booking" />
    <transition to="checkBookingResult" />
</action-state>
```

Biểu thức có thể đúng cú pháp, nhưng vẫn lỗi nếu `bookingService` không có trong Spring context, `bookingId` sai kiểu hoặc phương thức ném exception. Nếu service trả về null khi không tìm thấy bản ghi, đó là một kết quả dữ liệu cần được phân nhánh; nó không tự động là lỗi đánh giá biểu thức.

## 7. Chuyển kết quả nghiệp vụ thành nhánh rõ ràng

Các kết quả dự kiến như “không tìm thấy”, “đã hết hạn” hoặc “không đủ điều kiện” nên được biểu diễn thành trạng thái nghiệp vụ. Không nên dùng exception cho mọi kết quả không thành công.

Một service facade có thể trả về kết quả rõ ràng:

```java
public class BookingLookupService {

    public BookingLookupResult find(String bookingId) {
        if (bookingId == null || bookingId.trim().isEmpty()) {
            return BookingLookupResult.missingId();
        }

        return repository.findById(bookingId)
                .map(BookingLookupResult::found)
                .orElseGet(BookingLookupResult::notFound);
    }
}
```

`BookingLookupResult` là kiểu kết quả do ứng dụng định nghĩa, có thể chứa `status` và bản ghi khi tìm thấy. Ví dụ flow lưu kết quả rồi rẽ nhánh:

```xml
<action-state id="lookupBooking">
    <evaluate expression="bookingLookupService.find(flowScope.bookingId)"
              result="flowScope.lookupResult" />
    <transition to="decideLookup" />
</action-state>

<decision-state id="decideLookup">
    <if test="flowScope.lookupResult.status == 'FOUND'"
        then="reviewBooking"
        else="bookingNotFound" />
</decision-state>
```

Đoạn Java giả định `repository` đã được inject và `BookingLookupResult` cung cấp các factory method tương ứng. Nếu hệ thống có thêm trạng thái như `EXPIRED` hoặc `FORBIDDEN`, hãy biểu diễn thành nhánh riêng khi người dùng cần hành vi khác nhau. Với lỗi hạ tầng như database không truy cập được, service nên ném exception phù hợp hoặc trả kết quả lỗi kỹ thuật theo quy ước của ứng dụng; không biến lỗi hạ tầng thành `NOT_FOUND`.

## 8. Xử lý exception tại đúng ranh giới

Một nguyên tắc hữu ích là phân loại exception theo khả năng dự kiến:

- Lỗi nghiệp vụ dự kiến nên trở thành kết quả hoặc event có tên rõ ràng để flow chuyển state.
- Lỗi nhập liệu nên trở thành thông báo validation/binding gắn với form.
- Lỗi kỹ thuật tạm thời có thể được xử lý tại service/action boundary để cho phép retry hoặc chuyển đến state thông báo.
- Lỗi lập trình hoặc cấu hình không dự kiến cần được ghi log và đưa đến cơ chế xử lý lỗi chung.

Nếu một thao tác bên ngoài có thể thất bại tạm thời, tạo một facade chuyên trách để phân loại lỗi. Ví dụ facade có thể trả `SUCCESS`, `RETRYABLE_FAILURE` hoặc `REJECTED`; flow dùng `decision-state` để chuyển đến state hoàn tất, thử lại hoặc giải thích từ chối. Không để một biểu thức SpEL dài tự bắt và diễn giải nhiều loại exception.

Spring Web Flow có cơ chế xử lý exception ở tầng flow execution thông qua `FlowExecutionExceptionHandler` và cấu hình exception handler phù hợp với ứng dụng. Handler nên ghi nhận flow ID, state hiện tại, execution/correlation ID và nguyên nhân kỹ thuật; sau đó chọn cách kết thúc hoặc hiển thị lỗi an toàn. Tránh ghi dữ liệu cá nhân, token hoặc toàn bộ nội dung form vào log. Không bắt `Throwable` hoặc nuốt exception rồi giả vờ thao tác thành công.

Với lỗi runtime có thể phục hồi ngay tại action, có thể bắt đúng loại exception trong service facade và trả về kết quả miền nghiệp vụ. Cách này giúp flow xử lý các tình huống dự kiến bằng transition thông thường. Exception handler chung phù hợp với lỗi không xử lý được ở một state cụ thể hoặc cần chính sách toàn flow.

## 9. Giữ biểu thức ngắn và dễ chẩn đoán

Biểu thức trong XML thường nằm trong thuộc tính, vì vậy cần chú ý cả cú pháp SpEL lẫn quy tắc escape của XML. Dùng `and`, `or` trong biểu thức để tránh phải viết `&&` hoặc `||` rồi escape thành `&amp;&amp;` hay `||` trong XML.

Ví dụ biểu thức dài khó đọc:

```xml
<evaluate expression="flowScope.booking != null and flowScope.booking.customer != null and flowScope.booking.customer.email != null and !flowScope.booking.customer.email.trim().isEmpty() ? flowScope.booking.customer.email.trim() : 'Chưa cung cấp'"
          result="flowScope.emailLabel" />
```

Có thể tách điều kiện và giá trị:

```xml
<decision-state id="checkCustomerEmail">
    <if test="flowScope.booking != null and flowScope.booking.customer != null"
        then="checkEmailValue"
        else="emailUnavailable" />
</decision-state>

<decision-state id="checkEmailValue">
    <if test="flowScope.booking.customer.email != null and !flowScope.booking.customer.email.trim().isEmpty()"
        then="emailAvailable"
        else="emailUnavailable" />
</decision-state>
```

Trong state `checkEmailValue`, flow đã xác nhận `booking` và `customer` tồn tại ở nhánh trước. Nếu cấu trúc dữ liệu có thể thay đổi giữa các state hoặc có nhiều điểm cập nhật, hãy kiểm tra lại điều kiện hoặc gom việc đọc dữ liệu vào bean chuyên trách. Tên state như `checkCustomerEmail`, `emailAvailable` và `emailUnavailable` giúp log và test dễ hiểu hơn.

Đặt biểu thức quan trọng vào một bean Java khi nó cần nhiều bước xử lý, truy cập nhiều service, có logic phân loại lỗi hoặc cần unit test độc lập. Flow XML nên cho người đọc thấy luồng điều hướng; bean giữ quy tắc xử lý dữ liệu.

## 10. Kiểm thử các trường hợp thiếu, null và lỗi

Hãy lập bộ dữ liệu kiểm thử theo từng trạng thái thay vì chỉ thử một trường hợp hợp lệ:

| Dữ liệu | Kết quả mong đợi |
| --- | --- |
| Không có khóa `email` trong map | Flow nhận diện input bị bỏ qua và đi đến nhánh phù hợp với trường tùy chọn/bắt buộc. |
| Có khóa `email` với giá trị null | Flow nhận diện khóa đã có nhưng giá trị null nếu nghiệp vụ cần phân biệt. |
| `email = ""` hoặc chỉ có khoảng trắng | Flow xử lý như chưa nhập hoặc theo quy tắc chuẩn hóa đã định nghĩa. |
| Email sai định dạng | Validator báo lỗi field; người dùng được quay lại form. |
| `booking` null | Guard hoặc safe navigation ngăn dereference; flow đi đến nhánh khởi tạo/tìm lại dữ liệu. |
| Tên thuộc tính sai | Test phát hiện lỗi cấu hình/biểu thức, không biến nó thành dữ liệu mặc định. |
| Bean service ném exception | Exception được phân loại và xử lý theo chính sách lỗi. |
| Service trả về không tìm thấy | Flow đi đến state nghiệp vụ `notFound`, không coi là lỗi parser. |

Trong flow execution test, khởi chạy flow bằng dữ liệu giả, gửi event qua `MockExternalContext`, rồi kiểm tra state hiện tại và dữ liệu scope sau transition. Test riêng các nhánh null, missing và empty để bảo đảm chúng không vô tình đi cùng một nhánh nếu nghiệp vụ phân biệt chúng.

Với binding, gửi giá trị không chuyển đổi được sang kiểu model và xác nhận view vẫn hiển thị lỗi field. Với expression runtime, có thể dùng service mock để tạo kết quả null hoặc ném exception, sau đó kiểm tra flow handler hoặc state lỗi. Một test cho biểu thức sai tên thuộc tính giúp phát hiện lỗi cấu hình sớm; không nên chỉ kiểm tra nhánh thành công.

## 11. Checklist trước khi đưa biểu thức vào flow

- Đã xác định thuộc tính có thể missing, null, empty hay không hợp lệ chưa?
- Nếu dùng map, có cần phân biệt khóa không tồn tại và khóa có giá trị null bằng `containsKey` không?
- Đã guard receiver có thể null trước khi truy cập thuộc tính lồng nhau chưa?
- Cú pháp `?.` và `?:` có được parser/phiên bản Spring EL đang dùng hỗ trợ không?
- Giá trị mặc định có phù hợp nghiệp vụ hay đang che một dữ liệu bắt buộc bị thiếu?
- Lỗi binding, validation và expression evaluation có được phân loại riêng không?
- Các kết quả nghiệp vụ dự kiến đã được chuyển thành trạng thái/event rõ ràng chưa?
- Exception kỹ thuật có log đủ ngữ cảnh và được hiển thị an toàn không?
- Test đã bao phủ missing, null, empty, invalid, service exception và sai biểu thức chưa?

Khi hoàn thành các bước này, biểu thức của Spring Web Flow sẽ mô tả rõ cách dữ liệu được đọc và quyết định được đưa ra. Giá trị thiếu được xử lý theo quy tắc nghiệp vụ, null không gây truy cập ngoài ý muốn, còn lỗi thực thi được chẩn đoán và chuyển đến cơ chế phục hồi phù hợp.
