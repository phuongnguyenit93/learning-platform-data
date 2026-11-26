# Đối chiếu tên trường HTML với cấu trúc model

Trong module **SPRING_WEB_FLOW**, form binding đưa dữ liệu người dùng gửi lên vào model của một `view-state`. Để binding đúng, tên trường HTML phải mô tả đúng property path trong đối tượng Java mà view-state đang sử dụng. Một trường có thể bind vào property đơn, property lồng nhau hoặc phần tử trong collection. Nếu tên trường không khớp cấu trúc model, dữ liệu có thể không được cập nhật, lỗi binding xuất hiện hoặc người dùng gửi được những trường mà ứng dụng không định cho phép thay đổi.

Bài này tập trung vào cách đối chiếu `name` của HTML với JavaBean model, cách dùng Spring form tag, cách cấu hình danh sách field được phép bind, xử lý kiểu dữ liệu và validation, cùng các kiểm tra cần có để form nhiều bước hoạt động an toàn.

## 1. Quy tắc cốt lõi: name ánh xạ tới property path

Trình duyệt gửi các cặp tên/giá trị của những control được submit. Với HTML thuần, thuộc tính `name` là khóa của giá trị gửi lên. Thuộc tính `id` chủ yếu phục vụ CSS, JavaScript và liên kết với `<label>`; nó không quyết định property nào được cập nhật trong model.

Ví dụ, model có property `email` thì trường gửi lên cần có `name="email"`:

```html
<label for="email">Email</label>
<input id="email" name="email" type="email">
```

Nếu trường có `id="email"` nhưng `name="contactEmail"`, binder sẽ tìm property `contactEmail`. Việc ID trùng tên property không giúp binding nếu `name` khác. Ngược lại, `id` có thể là `customer-email` trong khi `name` là `customer.email`.

Với Spring Web Flow, `view-state` khai báo model mà view sử dụng. Ví dụ:

```xml
<view-state id="editBooking" view="booking/edit" model="booking">
    <transition on="submit" to="reviewBooking" bind="true" validate="true" />
</view-state>
```

Ở đây `booking` là model attribute được đưa vào view. Khi transition `submit` thực hiện binding, Web Flow dùng các tên trường gửi lên để cập nhật property tương ứng trên model. Vì vậy, cần kiểm tra đồng thời ba phần: model của `view-state`, cấu trúc JavaBean và tên trường HTML.

## 2. Chuẩn bị model JavaBean phù hợp với form

Spring binding dựa trên property path và cơ chế truy cập property của JavaBean. Những property cần bind thường phải có getter và setter tương ứng, với kiểu dữ liệu có thể chuyển đổi từ chuỗi form. Nên tạo một form model/DTO thể hiện đúng dữ liệu người dùng được phép nhập.

Ví dụ form booking có thông tin khách hàng, danh sách dòng hàng, ngày nhận và lựa chọn gói quà:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class BookingForm {
    private CustomerForm customer = new CustomerForm();
    private List<BookingItemForm> items = new ArrayList<>();
    private LocalDate arrivalDate;
    private boolean giftWrap;
    private String note;

    public CustomerForm getCustomer() {
        return customer;
    }

    public void setCustomer(CustomerForm customer) {
        this.customer = customer;
    }

    public List<BookingItemForm> getItems() {
        return items;
    }

    public void setItems(List<BookingItemForm> items) {
        this.items = items;
    }

    public LocalDate getArrivalDate() {
        return arrivalDate;
    }

    public void setArrivalDate(LocalDate arrivalDate) {
        this.arrivalDate = arrivalDate;
    }

    public boolean isGiftWrap() {
        return giftWrap;
    }

    public void setGiftWrap(boolean giftWrap) {
        this.giftWrap = giftWrap;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}

public class CustomerForm {
    private String name;
    private String email;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}

public class BookingItemForm {
    private String productCode;
    private Integer quantity;

    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
}
```

Trong dự án thực tế, mỗi lớp `public` thường nằm trong file Java riêng. Các property lồng nhau như `customer` cần được khởi tạo trước khi binding hoặc được binder cấu hình để tự tạo nested path. Với collection, hãy khởi tạo danh sách và chỉ cho phép những chỉ số mà form thực sự hiển thị; không phụ thuộc vào việc binder tự mở rộng danh sách trong mọi tình huống.

Tạo model trước khi vào view-state, ví dụ từ một action/service:

```xml
<action-state id="prepareBookingForm">
    <evaluate expression="bookingFormService.createForm(flowScope.bookingId)"
              result="flowScope.booking" />
    <transition on="success" to="editBooking" />
</action-state>

<view-state id="editBooking" view="booking/edit" model="booking">
    <transition on="submit" to="reviewBooking" bind="true" validate="true" />
</view-state>
```

Model có thể được nạp từ dữ liệu hiện có hoặc tạo mới. Hãy bảo đảm nó có cấu trúc phù hợp với các field mà view hiển thị trước khi người dùng gửi form.

## 3. Đối chiếu tên trường với property đơn và property lồng nhau

Với property đơn, tên trường là tên property. Với property lồng nhau, dùng dấu chấm để đi qua từng cấp object.

| Cấu trúc model Java | Tên trường HTML (`name`) | Ý nghĩa |
|---|---|---|
| `BookingForm.note` | `note` | Ghi chú booking |
| `BookingForm.arrivalDate` | `arrivalDate` | Ngày nhận |
| `BookingForm.customer.name` | `customer.name` | Tên khách hàng |
| `BookingForm.customer.email` | `customer.email` | Email khách hàng |
| `BookingForm.items[0].quantity` | `items[0].quantity` | Số lượng ở dòng hàng đầu tiên |

HTML thuần có thể viết:

```html
<label for="customer-name">Tên khách hàng</label>
<input id="customer-name" name="customer.name" type="text">

<label for="customer-email">Email</label>
<input id="customer-email" name="customer.email" type="email">

<label for="arrival-date">Ngày nhận</label>
<input id="arrival-date" name="arrivalDate" type="date">

<label for="booking-note">Ghi chú</label>
<textarea id="booking-note" name="note"></textarea>
```

Với nested path `customer.email`, binder đi từ `BookingForm.getCustomer()` rồi cập nhật `CustomerForm.setEmail(...)`. Nếu property `customer` là `null`, binder không thể đi tiếp trừ khi cơ chế auto-grow nested path được bật và kiểu property có thể được khởi tạo. Khởi tạo object con trong form model thường dễ dự đoán hơn.

## 4. Dùng Spring form tag để tránh lệch tên

Trong JSP, Spring form tag có thể sinh thuộc tính `name` từ `path`. Điều này giảm việc phải viết cùng một property path ở nhiều nơi:

```jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>

<form:form method="post" modelAttribute="booking">
    <label for="customer-name">Tên khách hàng</label>
    <form:input id="customer-name" path="customer.name" />
    <form:errors path="customer.name" cssClass="field-error" />

    <label for="customer-email">Email</label>
    <form:input id="customer-email" path="customer.email" type="email" />
    <form:errors path="customer.email" cssClass="field-error" />

    <label for="arrival-date">Ngày nhận</label>
    <form:input id="arrival-date" path="arrivalDate" type="date" />
    <form:errors path="arrivalDate" cssClass="field-error" />

    <button type="submit" name="_eventId_submit" value="true">Tiếp tục</button>
</form:form>
```

`modelAttribute="booking"` liên kết form tag với model attribute của view. `path="customer.email"` là property path; Spring form tag sinh `name` tương ứng. `id` vẫn là giá trị riêng cho HTML. Khi dùng HTML thuần hoặc một template engine khác, cần tự bảo đảm `name` khớp property path.

Trong ví dụ, nút gửi phát event `submit` theo quy ước event ID của Spring Web Flow. Tên event phải khớp `on="submit"` trong transition. Có thể kiểm tra HTML được render trong trình duyệt để chắc chắn `name` của input và tên event thực tế được gửi đúng.

## 5. Đối chiếu collection và phần tử có chỉ số

Với `List` hoặc array, property path dùng chỉ số trong ngoặc vuông. Ví dụ model có `List<BookingItemForm> items`, trường số lượng của dòng đầu tiên có tên `items[0].quantity`:

```html
<label for="item-0-code">Mã sản phẩm</label>
<input id="item-0-code" name="items[0].productCode" type="text">

<label for="item-0-quantity">Số lượng</label>
<input id="item-0-quantity" name="items[0].quantity" type="number" min="1">

<label for="item-1-code">Mã sản phẩm dòng 2</label>
<input id="item-1-code" name="items[1].productCode" type="text">
```

Chỉ số trong tên trường phải tương ứng với vị trí phần tử trong collection tại thời điểm binding. Nếu view hiển thị dòng `items[1]` nhưng model chỉ có một phần tử, binding có thể thất bại hoặc phụ thuộc cấu hình auto-grow và giới hạn collection của binder. Với danh sách có thể thêm/xóa động, hãy thiết kế rõ cách tạo dòng, giới hạn số lượng phần tử và kiểm tra chỉ số trước khi xử lý.

Đối với map, property path có thể dùng key trong ngoặc vuông, nhưng key có ký tự đặc biệt cần được escape/quote theo cú pháp property accessor mà binder sử dụng. Nếu map key do người dùng kiểm soát, hãy xác thực key và giới hạn các key được phép. Với form nghiệp vụ thông thường, DTO có property tường minh thường dễ bảo trì và kiểm soát hơn map tùy ý.

## 6. Chọn chính xác các property được phép bind

Nếu không giới hạn field, một request có thể gửi thêm tên property mà giao diện không hiển thị. Không nên coi việc ẩn field hoặc bỏ field khỏi HTML là biện pháp bảo vệ model. Có thể dùng `<binder>` trong `view-state` để liệt kê các property được phép binding:

```xml
<view-state id="editBooking" view="booking/edit" model="booking">
    <binder>
        <binding property="customer.name" />
        <binding property="customer.email" />
        <binding property="arrivalDate" />
        <binding property="giftWrap" />
        <binding property="note" />
        <binding property="items[0].productCode" />
        <binding property="items[0].quantity" />
    </binder>
    <transition on="submit" to="reviewBooking" bind="true" validate="true" />
</view-state>
```

Khi khai báo binder allowlist, chỉ những property được liệt kê mới được nhận binding theo cấu hình đó. Hãy thêm property path cho từng field thực sự cần cập nhật và kiểm tra binder có xử lý đúng các index collection mà view render. Nếu dùng danh sách có số dòng thay đổi, cần cấu hình giới hạn và kiểm thử đường dẫn được phép tương ứng.

Không bind trực tiếp các trường nhạy cảm hoặc do server quyết định như `totalPrice`, `discountApproved`, `ownerId`, `paymentStatus`, `role` hay `approved`. Tính lại giá và kiểm tra quyền ở service từ dữ liệu tin cậy. Một input `type="hidden"` vẫn do trình duyệt gửi lên và người dùng có thể sửa giá trị của nó.

## 7. Kiểu dữ liệu và chuyển đổi giá trị

Giá trị form thường được gửi dưới dạng chuỗi. Binder cần chuyển chuỗi đó sang kiểu Java của property. Những trường hợp phổ biến:

| Kiểu Java | Ví dụ `name` | Ví dụ giá trị gửi | Lưu ý |
|---|---|---|---|
| `String` | `customer.name` | `Nguyen An` | Kiểm tra độ dài và chuẩn hóa nếu cần |
| `Integer` | `items[0].quantity` | `2` | Từ chối chuỗi không phải số và kiểm tra giới hạn |
| `BigDecimal` | `deposit` | `1250000.00` | Dùng định dạng số nhất quán, không dùng `double` cho tiền |
| `LocalDate` | `arrivalDate` | `2026-12-05` | Cấu hình formatter/converter theo định dạng form |
| `Enum` | `paymentMethod` | `BANK_TRANSFER` | Chỉ chấp nhận enum value được cho phép |
| `Boolean` | `giftWrap` | `true` | Chú ý checkbox không được chọn thường không gửi field |

Ví dụ, `<input type="date">` thường gửi ngày theo định dạng ISO `yyyy-MM-dd`. Nếu model dùng `LocalDate`, hãy cấu hình `ConversionService` hoặc formatter phù hợp với phiên bản Spring và cách Web Flow được cấu hình. Với số tiền, dùng `BigDecimal` và định dạng được xác định rõ theo locale; không tự phân tích chuỗi tiền tệ bằng phép thay dấu phẩy/dấu chấm rải rác trong controller.

Khi chuyển đổi thất bại, binder tạo binding error thay vì cập nhật property với một giá trị hợp lệ. View nên hiển thị lỗi ngay tại field tương ứng để người dùng biết cần sửa gì.

## 8. Checkbox, select và field có thể không được gửi

Checkbox HTML không được chọn thường bị trình duyệt bỏ khỏi request. Điều đó có nghĩa model có thể không nhận được giá trị `false` nếu trước đó property đang là `true`. Với JSP, dùng `<form:checkbox path="giftWrap" />` để Spring form tag tạo cấu trúc hỗ trợ marker cho checkbox. Nếu dùng HTML thuần, hãy xử lý marker/giá trị mặc định theo cơ chế binder của ứng dụng và kiểm thử trường hợp bỏ chọn.

Với select, giá trị `value` phải chuyển đổi được sang kiểu property:

```jsp
<form:select path="paymentMethod">
    <form:option value="">-- Chọn phương thức --</form:option>
    <form:option value="CARD">Thẻ</form:option>
    <form:option value="BANK_TRANSFER">Chuyển khoản</form:option>
</form:select>
<form:errors path="paymentMethod" cssClass="field-error" />
```

Nếu property là enum `PaymentMethod`, các giá trị `CARD` và `BANK_TRANSFER` cần được chuyển đổi hợp lệ. Không dựa vào nhãn hiển thị như “Thẻ” để chuyển đổi nếu enum dùng tên khác. Hãy dùng converter/formatter có quy tắc rõ ràng và kiểm tra giá trị không hợp lệ.

## 9. Binding và validation là hai bước liên quan nhưng khác nhau

Binding chuyển dữ liệu request vào model; validation kiểm tra dữ liệu đã bind có đáp ứng quy tắc hay không. Trong Spring Web Flow, transition có thể bật cả hai:

```xml
<transition on="submit" to="reviewBooking" bind="true" validate="true" />
```

Khi binding hoặc validation có lỗi, flow giữ người dùng ở view-state để hiển thị lỗi và sửa dữ liệu. Ví dụ, `items[0].quantity` có thể bind thành công chuỗi `0` vào `Integer`, nhưng validation nghiệp vụ vẫn phải từ chối số lượng nhỏ hơn 1. Ngược lại, chuỗi `abc` không thể chuyển thành `Integer`, nên đây là lỗi binding/type conversion trước khi quy tắc số lượng được đánh giá.

Ví dụ validator ở tầng Java:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class BookingFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        if (form.getCustomer() == null ||
                form.getCustomer().getName() == null ||
                form.getCustomer().getName().isBlank()) {
            errors.rejectValue("customer.name", "customer.name.required",
                    "Vui lòng nhập tên khách hàng.");
        }

        if (form.getItems() == null || form.getItems().isEmpty()) {
            errors.reject("booking.items.required", "Booking cần ít nhất một dòng hàng.");
        }
    }
}
```

Đăng ký validator theo cấu hình validation của flow/application. Trên view, hiển thị lỗi theo đúng property path, ví dụ `customer.name`, `items[0].quantity` hoặc lỗi toàn form. Thông báo validation không thay thế kiểm tra quyền và quy tắc ở service trước khi ghi dữ liệu.

## 10. Lỗi đối chiếu thường gặp

| Lỗi | Triệu chứng | Cách kiểm tra và sửa |
|---|---|---|
| Dùng `id` đúng nhưng `name` sai | Property trong model không thay đổi | Kiểm tra request payload và sửa `name` theo property path |
| Dùng tên label thay cho property | Binder không tìm thấy property | Dùng tên JavaBean property, ví dụ `customer.email` |
| Thiếu getter/setter hoặc sai kiểu | Binding error hoặc không cập nhật được | Kiểm tra JavaBean accessors và converter |
| Object con đang `null` | Không bind được `customer.name` | Khởi tạo nested object hoặc cấu hình auto-grow phù hợp |
| Index collection vượt phạm vi | Lỗi binding hoặc dòng bị bỏ qua | Đồng bộ chỉ số với model, giới hạn kích thước và kiểm tra input |
| Checkbox bỏ chọn không gửi giá trị | Giá trị cũ vẫn còn trong model | Dùng Spring form checkbox hoặc xử lý marker rõ ràng |
| Field nhạy cảm không có trên giao diện nhưng vẫn bind được | Request giả mạo có thể thay đổi property | Dùng binder allowlist và form DTO chỉ chứa field được phép |
| Validation chỉ chạy ở JavaScript | Request trực tiếp có thể bỏ qua kiểm tra | Bật server-side validation trên transition và kiểm tra lại ở service |

Khi một field không được cập nhật, hãy lần theo đường đi: HTML đã render `name` nào, trình duyệt có gửi cặp tên/giá trị đó không, model attribute của view-state có đúng không, binder có cho phép property path đó không, và property Java có thể nhận kiểu dữ liệu đã gửi không. Cách kiểm tra tuần tự này giúp khoanh vùng nguyên nhân mà không phải đoán.

## 11. Kiểm thử mapping giữa HTML và model

Kiểm thử nên xác nhận cả cấu trúc request lẫn kết quả trên model. Một số trường hợp quan trọng:

1. **Property đơn:** gửi `note` và xác nhận `BookingForm.note` được cập nhật.
2. **Property lồng nhau:** gửi `customer.name` và `customer.email`, xác nhận đúng object `CustomerForm` nhận dữ liệu.
3. **Collection:** gửi `items[0].quantity`, kiểm tra đúng phần tử được cập nhật; thử index không hợp lệ và giới hạn số dòng.
4. **Chuyển đổi kiểu:** gửi ngày ISO, số nguyên, số tiền và enum hợp lệ; sau đó gửi chuỗi sai định dạng để kiểm tra binding error.
5. **Checkbox:** kiểm tra cả trạng thái chọn và bỏ chọn để property boolean được cập nhật như mong đợi.
6. **Allowlist:** gửi thêm `totalPrice`, `ownerId` hoặc property không được khai báo và xác nhận chúng không thể thay đổi model.
7. **Validation:** gửi dữ liệu bind được nhưng vi phạm quy tắc; xác nhận flow ở lại view-state và lỗi gắn đúng field.
8. **Event:** xác nhận form gửi đúng event ID và transition chỉ đi tiếp khi binding/validation thành công.

Với flow test, khởi chạy flow, gửi event bằng `MockExternalContext` hoặc request mô phỏng, rồi kiểm tra state và object trong scope. Với kiểm thử giao diện tích hợp Spring MVC, kiểm tra HTML render thực tế để bảo đảm `path` của Spring form tag sinh đúng `name`. Một unit test cho validator không thể phát hiện lỗi đánh máy trong thuộc tính `name` của HTML, nên cần ít nhất một kiểm tra ở cấp view hoặc flow.

## 12. Quy trình đối chiếu trước khi hoàn tất form

Trước khi nối một form với model trong Spring Web Flow, hãy thực hiện lần lượt:

1. Xác định model attribute mà `view-state` cung cấp, ví dụ `booking`.
2. Liệt kê các field người dùng thực sự được phép sửa và property path Java tương ứng.
3. Kiểm tra object lồng nhau và collection đã được khởi tạo với cấu trúc phù hợp.
4. Đặt `name` HTML bằng property path; với Spring form tag, dùng `path` để sinh tên đó.
5. Cấu hình `<binder>` allowlist cho các property được phép cập nhật, đặc biệt với form chứa dữ liệu nghiệp vụ nhạy cảm.
6. Cấu hình chuyển đổi kiểu và định dạng cho ngày, số, enum và các kiểu không phải chuỗi.
7. Bật binding/validation trên transition gửi form và hiển thị lỗi theo đúng property path.
8. Kiểm thử request hợp lệ, request sai kiểu, field bị giả mạo, collection index và checkbox bỏ chọn.

Khi tên trường HTML phản ánh đúng cấu trúc model, binder được giới hạn đúng phạm vi và validation chạy ở phía server, form binding trở thành một phần rõ ràng của flow. Người phát triển có thể lần từ input tới property Java, hiểu dữ liệu được giữ qua state nào và xác định nhanh lỗi khi một giá trị không được bind như mong đợi.
