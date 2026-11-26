# Chuyển chuỗi thành số, enum và giá trị miền nghiệp vụ trong Spring Web Flow

> **Chương:** Chuyển đổi và định dạng  
> **Mục tiêu:** Hiểu cách dữ liệu chuỗi từ HTTP form được chuyển thành các kiểu Java trong Spring Web Flow (SWF); thiết kế quy tắc chuyển đổi số, enum và value object; phân biệt conversion, formatting, validation và kiểm tra nghiệp vụ; xử lý lỗi để flow nhiều bước tiếp tục an toàn.

## 1. Bài toán: HTTP gửi chuỗi, nghiệp vụ cần kiểu dữ liệu

Một flow đặt lịch tư vấn gồm các bước:

1. **chooseService**: chọn gói tư vấn.
2. **chooseSlot**: nhập số người và chọn khung giờ.
3. **review**: xem lại chi phí, lịch hẹn và xác nhận.
4. **reserve**: service lưu đặt lịch rồi kết thúc flow.

Trình duyệt gửi những giá trị như sau:

~~~http
POST /booking?execution=e1s2 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId=next&tier=PRO&attendees=3&deposit=150000.00&slotId=550e8400-e29b-41d4-a716-446655440000
~~~

Mọi giá trị trong phần form URL-encoded bắt đầu là **chuỗi ký tự**. Trong mã Java, ứng dụng lại muốn:

- `attendees` là `Integer`, để so sánh số người tối đa.
- `deposit` là `BigDecimal`, để tránh sai số của số thực nhị phân.
- `tier` là một `enum` chỉ nhận các mã gói hợp lệ.
- `slotId` là một **value object** thể hiện mã khung giờ, thay vì chuỗi tùy ý.

**Conversion** biến dạng biểu diễn từ chuỗi thành kiểu đối tượng. **Formatting** quy định cách một giá trị được đọc từ hoặc hiển thị theo định dạng, thường phụ thuộc ngôn ngữ và vùng. **Validation** kiểm tra giá trị có thỏa ràng buộc hay không. **Business authorization/check** quyết định thao tác có được phép và tài nguyên còn hợp lệ tại thời điểm sử dụng.

~~~mermaid
flowchart LR
    A["HTTP form: các chuỗi"] --> B["Binding các property được phép"]
    B --> C["Conversion / Parsing"]
    C --> D["Validation"]
    D --> E["Flow transition"]
    E --> F["Service: kiểm tra nghiệp vụ"]
    F --> G[("Transaction / Database")]
    C -->|"Lỗi định dạng"| H["Ở lại view-state, báo lỗi field"]
    D -->|"Giá trị không hợp lệ"| H
~~~

Đừng ghép tất cả thành một khối `try/catch` trong action cuối: mỗi loại kiểm tra có trách nhiệm và phản hồi khác nhau.

## 2. Đặt conversion vào vòng đời của Spring Web Flow

Spring Web Flow dùng **flow definition** để mô tả các `view-state`, `event` và `transition`; **flow execution** lưu trạng thái của một lần chạy qua nhiều HTTP request. Khi người dùng submit form ở một `view-state` có `model`, framework có thể thực hiện:

1. Lấy request cùng execution key và event hiện tại.
2. Xác định view-state đang hoạt động trong flow execution.
3. **Bind** các field được cho phép từ request vào model.
4. **Convert** giá trị thành kiểu của property đích.
5. **Validate** dữ liệu đã bind theo cấu hình của state.
6. Nếu dữ liệu hợp lệ, thực hiện transition ứng với event.
7. Nếu binding/conversion/validation thất bại, thường render lại view-state với thông báo lỗi.

Vì flow quản lý nhiều bước, model đã chuyển đổi ở bước trước có thể được giữ trong **flowScope** và sử dụng lại ở bước sau.

Ví dụ, khi người dùng nhập `attendees=3` tại `chooseSlot` rồi sang `review`, view đích có thể đọc số nguyên 3 từ cùng bản nháp mà không phải chuyển đổi lại một chuỗi cũ. Tuy nhiên, nếu người dùng sửa thông tin tại bước trước, binding và validation cần chạy lại.

### 2.1. Conversion không phải transition

Một lỗi chuyển đổi `attendees="ba"` không phải event `slotUnavailable`. Đó là lỗi của dữ liệu gửi từ form. Khi chuyển đổi thất bại, cần phản hồi ở vị trí field, giữ nguyên đường điều hướng hợp lệ và để người dùng sửa.

Ngược lại, nếu `attendees=3` hợp lệ về kiểu nhưng gói tư vấn chỉ cho tối đa hai người, đó là **validation hoặc quy tắc nghiệp vụ**, tùy nơi có đủ dữ liệu để quyết định.

## 3. Bốn tầng cần phân biệt khi thiết kế form

| Tầng | Câu hỏi chính | Ví dụ | Khi thất bại |
| --- | --- | --- | --- |
| **Binding** | Request có được phép ghi property này không? | Chỉ bind `tier`, `attendees`, `slotId` | Bỏ qua hoặc báo field không hợp lệ theo cấu hình |
| **Conversion / Parsing** | Chuỗi có biểu diễn được kiểu Java đích không? | `"3"` → `Integer(3)` | Lỗi chuyển đổi |
| **Formatting** | Chuỗi đọc/hiển thị theo locale nào? | `"1.234,50"` trong tiếng Việt | Lỗi định dạng/locale nếu không nhận diện được |
| **Validation** | Giá trị đã có kiểu có thỏa ràng buộc? | `attendees >= 1` | Lỗi nhập liệu hoặc quy tắc form |
| **Business check** | Dữ liệu có còn được phép áp dụng? | Slot còn trống, người dùng có quyền đặt | Outcome nghiệp vụ từ service |

Formatting và conversion có thể cùng nằm trong hệ thống converter/formatter, nhưng xét về thiết kế bài học cần tách rõ **biểu diễn** và **điều kiện hợp lệ**.

Ví dụ, chuỗi `"0"` chuyển được thành `Integer` thành công, nhưng số người bằng 0 có thể không hợp lệ. Chuỗi `"VIP"` không khớp bất kỳ gói nào là lỗi mã đầu vào; một gói `PRO` tồn tại nhưng đã ngừng bán là kết quả nghiệp vụ không còn khả dụng.

## 4. Khai báo model và field được bind tại view-state

Giả sử ứng dụng có `BookingDraft` làm model qua nhiều state:

~~~java
import java.math.BigDecimal;

public class BookingDraft {
    private Integer attendees;
    private BigDecimal deposit;
    private ServiceTier tier;
    private SlotId slotId;

    public Integer getAttendees() { return attendees; }
    public void setAttendees(Integer attendees) { this.attendees = attendees; }

    public BigDecimal getDeposit() { return deposit; }
    public void setDeposit(BigDecimal deposit) { this.deposit = deposit; }

    public ServiceTier getTier() { return tier; }
    public void setTier(ServiceTier tier) { this.tier = tier; }

    public SlotId getSlotId() { return slotId; }
    public void setSlotId(SlotId slotId) { this.slotId = slotId; }
}
~~~

Đây là DTO minh họa. Một flow định nghĩa bằng XML có thể khai báo model và view-state như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking" class="com.example.booking.BookingDraft"/>

    <view-state id="chooseService"
                view="booking/service"
                model="booking">
        <binder>
            <binding property="tier" required="true"/>
        </binder>
        <transition on="next" to="chooseSlot"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="chooseSlot"
                view="booking/slot"
                model="booking">
        <binder>
            <binding property="attendees" required="true"/>
            <binding property="deposit" required="true"/>
            <binding property="slotId" required="true"/>
        </binder>
        <transition on="back" to="chooseService" bind="false"/>
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="edit" to="chooseSlot" bind="false"/>
        <transition on="confirm" to="reserve" bind="false"/>
    </view-state>

    <action-state id="reserve">
        <evaluate expression="bookingAction.reserve(booking)"/>
        <transition on="booked" to="completed"/>
        <transition on="slotUnavailable" to="chooseSlot"/>
    </action-state>

    <end-state id="completed" view="booking/completed"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

**Quan trọng:** XML minh họa vị trí binding và transition; converter tùy chỉnh cho `ServiceTier` và `SlotId` phải được đăng ký với **cơ chế conversion thực tế của Web Flow**. Chỉ khai báo property có kiểu enum/value object chưa bảo đảm mọi chuỗi tùy ý sẽ tự chuyển đổi đúng.

### 4.1. Vì sao dùng binder tường minh?

Khối `<binder>` xác định những property mà mỗi bước được phép cập nhật. Ví dụ, tại `chooseSlot`, request không nên tự đổi các property nội bộ như `approved`, `price` hoặc `ownerId` nếu chúng tồn tại trên model.

Đây là cách giảm rủi ro **mass assignment**; tuy nhiên service vẫn phải tự kiểm tra quyền và giá trị đáng tin cậy. Mọi dữ liệu từ form có thể bị sửa từ phía client.

## 5. Chuyển chuỗi thành số nguyên

Số lượng người, số lần thử và mã thứ tự thường sử dụng `int`, `Integer` hoặc `long`. Converter cơ bản có thể phân tích các chuỗi như `"3"`. Những giá trị sau cần kiểm tra riêng:

| Giá trị request | Chuyển kiểu | Vấn đề tiếp theo |
| --- | --- | --- |
| `"3"` | Chuyển được thành số 3 | Kiểm tra giới hạn số người |
| `"0"` | Chuyển được thành số 0 | Có thể không hợp lệ theo nghiệp vụ |
| `"-2"` | Chuyển được thành số -2 | Cần ràng buộc tối thiểu |
| `"abc"` | Không chuyển được thành số | Lỗi conversion trên field |
| `"3.5"` | Không phải số nguyên theo quy tắc thông thường | Lỗi conversion |
| Chuỗi trống | Có thể thành null hoặc lỗi theo converter/config | Kiểm tra required và null |
| Số vượt giới hạn `Integer` | Tràn phạm vi kiểu | Lỗi conversion, không được cắt bớt |

Nếu dùng wrapper `Integer` thay cho primitive `int`, có thể phân biệt rõ **chưa nhập/null** và **đã nhập số 0**. Điều này giúp thông báo lỗi chính xác:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.validation.ValidationContext;

public class BookingDraftValidator {
    public void validateChooseSlot(
            BookingDraft booking, ValidationContext context) {

        Integer attendees = booking.getAttendees();
        if (attendees == null || attendees < 1 || attendees > 8) {
            context.getMessageContext().addMessage(
                    new MessageBuilder()
                            .error()
                            .source("attendees")
                            .code("booking.attendees.range")
                            .defaultText("Số người phải từ 1 đến 8.")
                            .build());
        }
    }
}
~~~

Đây là **ví dụ về validation sau conversion**, giả định validator đã được kết nối đúng với Web Flow. Với chuỗi `"abc"`, hệ thống binding đã có lỗi chuyển kiểu; không nên tạo thêm một thông báo “phải từ 1 đến 8” gây hiểu nhầm nếu chưa có giá trị số.

### 5.1. Chuỗi trống, null và giá trị mặc định

Không nên dùng `0` làm giá trị mặc định để che việc người dùng chưa nhập. Nếu trường bắt buộc, cấu hình `required="true"` và/hoặc validation phù hợp, đồng thời giữ nguyên thông tin để user biết mình cần điền gì.

Tránh âm thầm đổi `"-1"` thành 1, `"3.9"` thành 3 hoặc chuỗi không parse được thành 0. Cách đó biến dữ liệu sai thành dữ liệu hợp lệ giả.

## 6. Chuyển chuỗi thành số thập phân với BigDecimal

Tiền đặt cọc, giá hoặc tỷ lệ cần độ chính xác thập phân nên dùng `BigDecimal`. Không nên xử lý tiền bằng cách chuyển chuỗi sang `double` rồi truyền vào `new BigDecimal(double)`, vì số thực nhị phân có thể biểu diễn không chính xác.

~~~java
import java.math.BigDecimal;

BigDecimal good = new BigDecimal("150000.00");
// Tránh: new BigDecimal(0.1d) nếu cần chính xác tiền tệ.
~~~

Nhưng việc chọn kiểu `BigDecimal` chưa giải quyết hết vấn đề: chuỗi `"1,500.50"` hay `"1.500,50"` có thể mang nghĩa khác nhau theo locale.

### 6.1. Dạng chuẩn để trao đổi và dạng hiển thị

Hai chiến lược phổ biến:

1. **Dạng chuẩn của giao thức**: form gửi `150000.50`, phân cách thập phân bằng dấu chấm, không có phân cách hàng nghìn; service nhận `BigDecimal`.
2. **Dạng theo locale**: người dùng nhập `150.000,50` trong giao diện tiếng Việt; formatter/parser hiểu locale và trả `BigDecimal("150000.50")`.

Không trộn hai chiến lược mà không khai báo rõ. Nếu giao diện hiển thị `1.234,50` nhưng server luôn parse theo kiểu tiếng Anh, giá trị rất dễ bị hiểu sai.

### 6.2. Parser chặt chẽ cho chuỗi thập phân dạng chuẩn

Một ví dụ thuần Java, độc lập với việc đăng ký converter của framework:

~~~java
import java.math.BigDecimal;

public final class DecimalInput {
    private DecimalInput() {}

    // Chấp nhận 1..n chữ số, tùy chọn dấu chấm và tối đa 2 chữ số lẻ.
    public static BigDecimal parseCanonicalMoney(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Required amount");
        }
        String value = raw.trim();
        if (!value.matches("[0-9]+(\\.[0-9]{1,2})?")) {
            throw new IllegalArgumentException("Invalid amount");
        }
        return new BigDecimal(value);
    }
}
~~~

Ví dụ này chấp nhận `"150000"` và `"150000.50"`, từ chối `"150.000,50"`, `"1e3"` và dữ liệu âm. Đó là một **hợp đồng đầu vào cụ thể**, không phải định dạng chuẩn duy nhất cho mọi ứng dụng.

Khi tích hợp vào binding, ngoại lệ parse phải được đưa thành **lỗi chuyển đổi cho field deposit**; không ném thông tin lỗi kỹ thuật thô ra trình duyệt. Validation vẫn cần kiểm tra số tiền tối thiểu, tối đa, đơn vị tiền tệ và quy tắc nghiệp vụ.

### 6.3. Locale và định dạng hiển thị

Với đầu vào do người dùng nhập theo ngôn ngữ:

~~~text
vi-VN: 1.234,50  (dấu chấm có thể là phân nhóm, dấu phẩy là thập phân)
en-US: 1,234.50  (dấu phẩy phân nhóm, dấu chấm là thập phân)
canonical: 1234.50
~~~

Các quy ước cần đối chiếu theo locale và formatter cụ thể; đừng tự suy ra locale chỉ bằng ký tự có mặt trong chuỗi. Nếu sử dụng `NumberFormat` hoặc `DecimalFormat`:

- Cố định locale từ cấu hình request/ứng dụng đã được xác định.
- Đặt chế độ parse thành `BigDecimal` khi dùng `DecimalFormat` và cần giữ độ chính xác.
- Yêu cầu parser tiêu thụ **toàn bộ** chuỗi; tránh chấp nhận tiền tố hợp lệ rồi bỏ qua phần dư.
- Quy định rõ số chữ số lẻ, nhóm hàng nghìn và đơn vị tiền.
- Kiểm thử các trường hợp nhập sai dấu phân cách, ký tự trắng và số rất lớn.

**Formatting khi hiển thị** là hướng ngược lại: lấy `BigDecimal("1234.50")` và tạo văn bản phù hợp locale, nhưng không làm thay đổi giá trị lưu trữ.

## 7. Chuyển chuỗi thành enum

Một mã gói `"PRO"` có thể được chuyển thành enum thay vì giữ một chuỗi không kiểm soát. Tuy nhiên, phải phân biệt **tên hằng Java** và **mã truyền qua HTTP**.

~~~java
public enum ServiceTier {
    BASIC("BSC"),
    PRO("PRO"),
    ENTERPRISE("ENT");

    private final String code;

    ServiceTier(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static ServiceTier fromCode(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Tier is required");
        }
        String code = raw.trim();
        for (ServiceTier tier : values()) {
            if (tier.code.equals(code)) {
                return tier;
            }
        }
        throw new IllegalArgumentException("Unknown tier code");
    }
}
~~~

API `ServiceTier.valueOf("PRO")` chỉ dùng tên hằng; `ServiceTier.fromCode("BSC")` dùng **mã công khai** đã định nghĩa. Hai cách có hợp đồng khác nhau. Nếu gói BASIC đổi tên hằng Java, mã HTTP `BSC` vẫn có thể được duy trì ổn định.

### 7.1. Tránh parse enum theo cách quá dễ dãi

Không nên:

~~~java
// Không nên mặc định chọn PRO khi request gửi mã lạ.
ServiceTier tier;
try {
    tier = ServiceTier.valueOf(raw.toUpperCase());
} catch (Exception ignored) {
    tier = ServiceTier.PRO;
}
~~~

Cách làm đó có thể khiến một mã gói không xác định bị hiểu thành dịch vụ đắt hơn hoặc có quyền cao hơn.

Nên quyết định rõ:

- Mã có phân biệt hoa thường hay không?
- Có chấp nhận khoảng trắng bao quanh không?
- Mã nào là deprecated và cần migration?
- Mã lạ có phải lỗi nhập liệu hay một kết quả cần ngừng flow?

Ví dụ `"pro"`, `"PRO "` và `"PLUS"` cần có hành vi được tài liệu hóa. Không nên tự động chấp nhận mọi biến thể nếu điều đó làm mất ý nghĩa định danh.

### 7.2. Enum tồn tại không có nghĩa luôn còn được phép chọn

`ServiceTier.PRO` có thể chuyển đổi thành công nhưng hiện đã ngừng bán hoặc người dùng không đủ điều kiện. **Converter chỉ kiểm tra mã biểu diễn**; service phải đánh giá chính sách kinh doanh và quyền truy cập khi thực hiện đặt lịch.

## 8. Chuyển chuỗi thành value object của miền nghiệp vụ

Không phải mọi khái niệm đều nên dùng `String` hoặc enum. Một **value object** có thể biểu diễn mã khung giờ với bất biến rõ ràng và làm cho chữ ký service chính xác hơn.

~~~java
import java.util.Objects;
import java.util.UUID;

public final class SlotId {
    private final UUID value;

    private SlotId(UUID value) {
        this.value = Objects.requireNonNull(value);
    }

    public static SlotId parse(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            throw new IllegalArgumentException("Slot ID is required");
        }
        try {
            return new SlotId(UUID.fromString(raw.trim()));
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid slot ID", ex);
        }
    }

    public UUID getValue() { return value; }

    @Override
    public String toString() { return value.toString(); }

    @Override
    public boolean equals(Object other) {
        return other instanceof SlotId
                && value.equals(((SlotId) other).value);
    }

    @Override
    public int hashCode() { return value.hashCode(); }
}
~~~

Ví dụ sử dụng `UUID.fromString` để diễn giải mã. Nếu hệ thống yêu cầu đúng dạng UUID canonical theo quy tắc chặt chẽ, hãy bổ sung kiểm tra chuỗi đầu vào và kiểm thử đối với các dạng UUID rút gọn/không chuẩn tùy JDK.

Value object này bảo đảm rằng code phía service làm việc với một **mã hợp dạng**; nó **không chứng minh** khung giờ đó tồn tại, chưa bị người khác đặt, hoặc thuộc quyền người dùng.

### 8.1. Vì sao converter không nên truy vấn database?

Hãy tách hai việc:

~~~text
Chuỗi "550e8400-e29b-41d4-a716-446655440000"
  -> SlotId.parse(...)               : chuyển đổi biểu diễn
  -> BookingService.loadSlot(slotId)  : kiểm tra tồn tại/quyền/hiệu lực
~~~

Nếu converter tự query database, conversion của từng field có thể gây chi phí cao, side effect không rõ, exception tầng mạng và khó kiểm thử. Trong đa số trường hợp, converter nên **nhẹ, xác định, không phụ thuộc I/O**; để service xử lý lookup và policy.

### 8.2. Các ví dụ value object khác

| Value object | Chuỗi HTTP | Validation miền thường cần |
| --- | --- | --- |
| `SlotId` | UUID | Slot còn tồn tại và có thể đặt |
| `OrderNumber` | Mã đơn | Đơn thuộc người dùng, còn được xử lý |
| `Percentage` | `"12.5"` | Giá trị nằm trong phạm vi hợp lệ |
| `Quantity` | `"3"` | Số lượng dương, không vượt giới hạn |
| `CurrencyCode` | `"VND"` | Tiền tệ được hệ thống hỗ trợ |

Các kiểu trên nên có quy tắc tạo rõ ràng, so sánh giá trị nhất quán và định dạng xuất ngược về chuỗi theo hợp đồng.

## 9. Converter của Spring và tích hợp vào Spring Web Flow

Trong hệ sinh thái Spring có nhiều cơ chế conversion/formatting. Một converter theo **Spring Core** có thể triển khai giao diện `org.springframework.core.convert.converter.Converter<S, T>`:

~~~java
import org.springframework.core.convert.converter.Converter;

public final class StringToSlotIdConverter
        implements Converter<String, SlotId> {

    @Override
    public SlotId convert(String source) {
        return SlotId.parse(source);
    }
}
~~~

Có thể thử converter độc lập bằng `DefaultConversionService` của Spring Core:

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToSlotIdConverter());

SlotId slot = service.convert(
        "550e8400-e29b-41d4-a716-446655440000",
        SlotId.class);
~~~

**Cảnh báo về tích hợp:** Spring Web Flow có hệ thống conversion/binding và điểm cấu hình riêng (bao gồm các thành phần liên quan `FlowBuilderServices`); một converter đăng ký cho **Spring MVC** hoặc một `ConversionService` Spring Core độc lập **không mặc nhiên được Web Flow sử dụng**.

Khi nối converter vào flow, cần:

1. Xác định **phiên bản Web Flow** và API conversion thực tế của phiên bản đó.
2. Xem flow dùng conversion service nào để bind view-state.
3. Đăng ký converter/adapter tương thích với hệ thống Spring Binding của Web Flow, hoặc cấu hình converter được flow tham chiếu theo khả năng phiên bản.
4. Bảo đảm converter được dùng ở cả chiều cần thiết: **String → Domain** khi submit và **Domain → String** khi hiển thị/chọn lại.
5. Viết integration test từ form thật, vì unit test converter Spring Core chưa chứng minh Web Flow đã nhận converter đó.

Không nên sao chép cấu hình converter của Spring MVC sang Web Flow rồi kết luận mọi luồng đã sử dụng cùng cơ chế. Tài liệu và API chính xác phụ thuộc tổ hợp phiên bản Spring Web Flow, Spring MVC và Spring Boot.

### 9.1. Cần một quy tắc chuyển đổi hai chiều

Một form chọn slot phải có thể:

- Đọc `slotId` từ HTTP và tạo `SlotId`.
- Render `SlotId` hiện có thành thuộc tính `value` của `<option>`.

Nếu chiều xuất chỉ dùng `toString()`, cần bảo đảm định dạng đó ổn định, không chứa thông tin nhạy cảm và khớp đúng với parser chiều vào.

**Round-trip invariant**:

~~~text
parse(format(value)) == value
~~~

Áp dụng cho mã định danh, enum code và giá trị tiền theo một locale/hợp đồng xác định. Với giá trị hiển thị làm tròn (như 1,234.5 thay cho 1,234.567), không thể đòi hỏi round-trip chính xác tuyệt đối nếu đã cố ý giảm độ chính xác.

## 10. Trình tự khi một field chuyển đổi thất bại

Tại `view-state chooseSlot`, người dùng nhập:

~~~text
attendees = "ba"
deposit = "1.500,00"
slotId = "không-phải-uuid"
~~~

Nếu converter số nguyên, tiền và SlotId yêu cầu dạng chuẩn, việc binding thất bại trước khi có đủ model hợp lệ để chuyển sang review. Ứng dụng nên:

- Giữ người dùng tại `chooseSlot`.
- Hiển thị thông báo gần đúng field: “Số người phải là số nguyên”.
- Không âm thầm biến giá trị lỗi thành 0/null rồi cho đi tiếp.
- Bảo toàn dữ liệu hợp lệ người dùng đã nhập theo cơ chế binding/view.
- Không gọi service đặt lịch chỉ vì sự kiện `next` đã được gửi.

~~~mermaid
flowchart TD
    A["POST next tại chooseSlot"] --> B["Bind property được phép"]
    B --> C{"Chuyển kiểu thành công?"}
    C -->|"Không"| D["Binding error / message cho field"]
    D --> E["Render lại chooseSlot"]
    C -->|"Có"| F["Validation: range, required, format policy"]
    F -->|"Không đạt"| E
    F -->|"Đạt"| G["Transition next → review"]
~~~

### 10.1. Phân biệt lỗi chuyển kiểu và lỗi validator

| Request | Conversion | Validation | Phản hồi |
| --- | --- | --- | --- |
| `attendees=abc` | Thất bại | Chưa có số để validate | “Nhập số nguyên hợp lệ” |
| `attendees=0` | Thành công | Không đạt tối thiểu 1 | “Số người phải từ 1 đến 8” |
| `tier=NOPE` | Không nhận diện code | Không có enum hợp lệ | “Gói dịch vụ không hợp lệ” |
| `tier=PRO` | Thành công | Có thể không đạt chính sách sản phẩm | “Gói này chưa áp dụng cho tài khoản” |
| `slotId=bad` | Không phân tích được mã | Chưa đủ ID để lookup | “Mã khung giờ không hợp lệ” |
| UUID hợp dạng nhưng không tồn tại | Thành công | Service lookup thất bại theo nghiệp vụ | “Khung giờ không còn khả dụng” |

Khi converter đã báo lỗi, validator nên tránh phát thêm lỗi ràng buộc giả cho cùng field nếu chưa có dữ liệu chuyển đổi thành công.

## 11. MessageContext và mã lỗi có thể dịch

Spring Web Flow tích hợp thông báo với `MessageContext`. Validator hoặc action có thể tạo message gắn field:

~~~java
import org.springframework.binding.message.MessageBuilder;
import org.springframework.binding.validation.ValidationContext;

public void validateChooseSlot(
        BookingDraft draft, ValidationContext context) {
    Integer count = draft.getAttendees();
    if (count != null && (count < 1 || count > 8)) {
        context.getMessageContext().addMessage(
                new MessageBuilder()
                        .error()
                        .source("attendees")
                        .code("booking.attendees.range")
                        .defaultText("Số người phải từ 1 đến 8.")
                        .build());
    }
}
~~~

Method này minh họa **validation sau khi conversion thành công**; nó không thay thế lỗi binding khi chuỗi không parse được. Validator class/điểm đăng ký theo convention của Web Flow cần được cấu hình phù hợp.

Trong resource bundle:

~~~properties
# messages_vi.properties
booking.attendees.range=Số người phải từ 1 đến 8.
booking.attendees.type=Số người phải là số nguyên.
booking.deposit.type=Số tiền không đúng định dạng.
booking.tier.invalid=Gói dịch vụ không hợp lệ.
booking.slot.invalid=Mã khung giờ không hợp lệ.
booking.slot.unavailable=Khung giờ vừa chọn không còn trống.
~~~

~~~properties
# messages_en.properties
booking.attendees.range=Attendees must be between 1 and 8.
booking.attendees.type=Enter a whole number of attendees.
booking.deposit.type=Enter a valid amount.
booking.tier.invalid=The selected service tier is invalid.
booking.slot.invalid=The time slot identifier is invalid.
booking.slot.unavailable=The selected time slot is no longer available.
~~~

**Lưu ý:** Mã lỗi do framework sinh ra cho binding/conversion có thể khác mã ứng dụng tự đặt. Để hiển thị bản dịch chính xác, cần kiểm tra cơ chế resolve message code của phiên bản Web Flow và cách view truy cập binding errors. Không giả định mọi lỗi tự chuyển thành `booking.attendees.type`.

## 12. Xử lý theo locale ở giao diện nhiều ngôn ngữ

Một ứng dụng có giao diện tiếng Việt và tiếng Anh thường cần phân biệt:

| Vấn đề | Nội dung cần kiểm tra |
| --- | --- |
| Định dạng input | Người dùng nhập số theo `vi-VN` hay `en-US`? |
| Định dạng output | Render giá tiền với dấu nhóm và dấu thập phân nào? |
| Validation text | Có bản dịch lỗi conversion và validation cho cả hai locale không? |
| Chuyển locale giữa flow | Giá trị đã bind có giữ nguyên ý nghĩa không? |
| Sao chép dữ liệu sang form | Giá trị cũ có được format đúng trước khi gửi lại không? |

Ví dụ, nếu người dùng nhập số tiền `1.234,50` tại locale tiếng Việt, server phải parse theo quy tắc đã công bố. Khi chuyển giao diện sang tiếng Anh, giá trị **BigDecimal** phải giữ nguyên về mặt số học và có thể hiển thị là `1,234.50`.

Nên lưu **giá trị đã chuẩn hóa** trong model/flowScope, không lưu chuỗi hiển thị rồi liên tục parse lại theo locale mới. Nếu sản phẩm cần giữ chính xác văn bản người dùng gõ khi có lỗi, view/binding layer có thể giữ **raw input** riêng cho lần render thông báo.

## 13. Hành trình nhiều bước: lỗi ở đâu thì quay về đâu?

Giả sử người dùng đã qua `chooseSlot` và đang tại `review`. Khi nhấn `confirm`, service phát hiện slot vừa bị đặt:

~~~mermaid
flowchart LR
    A["chooseSlot"] -->|"next + bind hợp lệ"| B["review"]
    B -->|"confirm"| C["reserve action"]
    C -->|"booked"| D(("completed"))
    C -->|"slotUnavailable"| A
~~~

Trường hợp này **không phải lỗi conversion**: `SlotId` vẫn hợp dạng, nhưng tài nguyên đã thay đổi. Action có thể đưa flow quay lại `chooseSlot` với message nghiệp vụ.

~~~java
public Event reserve(RequestContext context) {
    BookingDraft draft =
            (BookingDraft) context.getFlowScope().get("booking");
    BookingResult result = bookingService.reserveOnce(draft);
    if (result.isBooked()) {
        return new Event(this, "booked");
    }
    if (result.isSlotUnavailable()) {
        context.getMessageContext().addMessage(
                new MessageBuilder()
                        .error()
                        .source("slotId")
                        .code("booking.slot.unavailable")
                        .defaultText("Khung giờ không còn trống.")
                        .build());
        return new Event(this, "slotUnavailable");
    }
    throw new IllegalStateException("Unknown booking result");
}
~~~

Đoạn Java mô tả ý tưởng; `BookingResult` và `bookingService` là các kiểu ứng dụng tự định nghĩa, và code cần import `Event`, `RequestContext`, `MessageBuilder` phù hợp khi triển khai. **Exception ngoài dự kiến không tự biến thành event `slotUnavailable`**.

### 13.1. Không nhầm event với dữ liệu form

`_eventId=next` hoặc `_eventId=confirm` báo **ý định chuyển bước**. Giá trị `attendees=3`, `tier=PRO` là **dữ liệu**. Converter không quyết định flow đến state nào; nó tạo kiểu dữ liệu để validation và transition xử lý.

### 13.2. Back với bind=false

Ở view-state nhập số, event `back` có thể dùng `bind="false"` để quay về mà không bị validation chặn. Tuy nhiên giá trị mới người dùng đang gõ có thể bị bỏ qua nếu chưa bind. Cần kiểm thử và quyết định rõ cách giữ bản nháp khi quay lại.

## 14. Những rủi ro khi đưa entity nghiệp vụ vào flowScope

Sau khi chuỗi slot ID được chuyển thành `SlotId`, có thể có cám dỗ chuyển tiếp thành entity JPA rồi cất cả entity trong `flowScope`. Cách này tạo rủi ro:

- Entity có thể gắn với persistence context đã đóng.
- Serialization/snapshot của flow execution có thể không phù hợp.
- Dữ liệu có thể trở nên lỗi thời qua thời gian người dùng nhập form.
- Nhiều tab có thể cập nhật cùng một bản ghi và tạo race condition.
- Kích thước flow execution/snapshot lớn không cần thiết.

Thường nên lưu **ID và DTO nhỏ gọn**, rồi service lookup mới trong transaction cần thiết. Đặc biệt với đặt chỗ, giá, tồn kho, quyền truy cập và trạng thái thanh toán phải được kiểm tra lại khi commit.

**Converter không được biến một ID hợp dạng thành bằng chứng người dùng sở hữu hoặc có quyền sử dụng đối tượng đó.**

## 15. Chuyển đổi có thể đảo ngược và kiểm thử round-trip

Một converter chỉ được test theo chiều `String → Type` là chưa đủ cho form có nút Back/Edit. Giao diện có thể cần hiển thị lại giá trị typed trong model.

| Loại | Input từ form | Model | Output trở lại form |
| --- | --- | --- | --- |
| Số nguyên | `"3"` | `Integer(3)` | `"3"` |
| Tiền chuẩn | `"1234.50"` | `BigDecimal("1234.50")` | `"1234.50"` hoặc chuỗi locale tương ứng |
| Enum code | `"BSC"` | `ServiceTier.BASIC` | `"BSC"` |
| Slot ID | UUID string | `SlotId` | UUID string canonical |

Khi thiết kế các converter/formatter, cần kiểm tra:

~~~text
parse(format(value)) = value
~~~

Đây là bất biến hữu ích khi format không làm mất thông tin. Với giá trị hiển thị làm tròn, cần quy định rõ cách làm tròn và độ chính xác.

### 15.1. Test parser/formatter thuần Java

~~~text
parseCanonicalMoney("1234.50") -> BigDecimal 1234.50
parseCanonicalMoney("1,234.50") -> ERROR
parseCanonicalMoney("1.234,50") -> ERROR
parseCanonicalMoney("-50") -> ERROR

ServiceTier.fromCode("BSC") -> BASIC
ServiceTier.fromCode("NOPE") -> ERROR

SlotId.parse(validUuid) -> SlotId
SlotId.parse("abc") -> ERROR
~~~

Đừng chỉ test happy path. Đầu vào null, rỗng, dấu âm, ký tự lạ, số vượt biên, Unicode whitespace, mã enum sai kiểu chữ và locale không khớp rất dễ bộc lộ lỗi.

## 16. Kiểm thử binding thực trong Web Flow

Unit test converter thuần Java xác minh thuật toán chuyển kiểu; nó **không chứng minh** Web Flow đã sử dụng converter trong view-state.

Một bộ kiểm thử nên gồm:

| Cấp kiểm thử | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Unit | `attendees="abc"` | Converter báo lỗi, không tạo số giả |
| Unit | `attendees="0"` | Chuyển kiểu thành công, validator từ chối |
| Unit | `tier="BSC"` | Map đúng enum BASIC |
| Unit | `tier="UNKNOWN"` | Không chọn gói mặc định |
| Unit | `slotId` sai định dạng | Không tạo SlotId |
| Flow | Submit `next` với số hợp lệ | State chuyển sang review |
| Flow | Submit `next` với lỗi conversion | Giữ chooseSlot, có lỗi field |
| Flow | Back/Edit giữa các bước | Giá trị typed được render lại đúng |
| MVC integration | Input theo locale VI/EN | Parse/format khớp quy tắc |
| Business integration | Slot ID hợp dạng nhưng đã bị chiếm | Service từ chối, không ghi trùng |
| Security | Client tự gửi property nội bộ | Không được bind/không vượt kiểm tra quyền |
| Session/history | Gửi form từ snapshot cũ | Xử lý dựa trên execution hợp lệ và xác minh lại nghiệp vụ |

### 16.1. Pseudocode kiểm thử flow

~~~text
flow = startFlow("booking")
assertState(flow, "chooseService")

submit(flow, event="next", tier="BSC")
assertState(flow, "chooseSlot")

submit(flow, event="next",
       attendees="abc",
       deposit="150000.00",
       slotId=validUuid)
assertState(flow, "chooseSlot")
assertFieldError("attendees")

submit(flow, event="next",
       attendees="3",
       deposit="150000.00",
       slotId=validUuid)
assertState(flow, "review")
assertModelType("booking.attendees", Integer)
assertModelType("booking.slotId", SlotId)
~~~

Đoạn trên là **mã giả mô tả kịch bản**, không phải test API Java chạy nguyên văn. Test thực tế cần sử dụng cơ sở hạ tầng của phiên bản Web Flow và converter/formatter đã đăng ký.

### 16.2. Kiểm thử thay đổi locale giữa chừng

Một kịch bản quan trọng:

1. Người dùng ở locale `vi-VN` nhập số tiền theo định dạng được hỗ trợ.
2. Web Flow bind thành `BigDecimal` và đi tới review.
3. Người dùng chuyển sang `en-US` hoặc mở lại form.
4. View format cùng giá trị theo locale mới.
5. Submit lại mà không thay đổi giá trị số học.

Nếu bước 4 tạo chuỗi mà bước 5 không thể parse, cần kiểm tra **sự không tương thích giữa formatter chiều hiển thị và parser chiều vào**.

## 17. Lỗi thiết kế thường gặp và cách tránh

**Gộp converter và validator.** Converter chỉ nên chuyển biểu diễn một cách nhất quán. Ràng buộc “số người không vượt 8” nên nằm ở validation hoặc service theo yêu cầu.

**Bắt mọi exception rồi chọn default.** Mã enum lạ hoặc số lỗi không nên biến thành gói mặc định. Người dùng có thể vô tình đặt dịch vụ khác mong muốn.

**Dùng double cho tiền.** Chuyển chuỗi tiền trực tiếp sang số thực nhị phân có thể tạo sai số; sử dụng `BigDecimal` với quy tắc scale/rounding rõ ràng.

**Không cố định locale.** `1,234` có thể được hiểu khác nhau ở các vùng. Chỉ parse khi biết hợp đồng định dạng.

**Cho converter query database.** Điều này làm binding tốn tài nguyên, gây lỗi mạng và làm sai ranh giới trách nhiệm. Chỉ chuyển từ chuỗi thành ID/value object; service chịu trách nhiệm tra cứu.

**Tin rằng enum hợp lệ là được phép mua.** Giá, quyền, hạn mức và trạng thái gói phải được service kiểm tra lại tại thời điểm ghi.

**Đăng ký converter ở MVC rồi không test Web Flow.** Hai hệ thống có thể dùng conversion service khác nhau; phải xác minh cấu hình binding của Web Flow bằng integration test.

**Không hỗ trợ format ngược.** Sau Back/Edit, model typed không thể hiển thị đúng trong form hoặc tạo mã khác so với lúc submit.

**Lưu nguyên chuỗi giao diện trong flowScope.** Chuỗi có dấu phân cách theo locale dễ thành dữ liệu lỗi thời khi locale thay đổi. Nên lưu giá trị typed/chuẩn hóa.

**Dùng bản nháp đã convert như nguồn dữ liệu bền vững.** Snapshot cũ không chứng minh slot còn trống. Service phải xác minh điều kiện hiện hành, transaction và idempotency.

## 18. Bài thực hành: thiết kế converter cho flow đặt vé

Xây dựng flow `ticketBooking` gồm các bước `chooseType → chooseQuantity → review → pay → completed`, có nút Back/Edit và đường lỗi khi hết vé.

**Yêu cầu nghiệp vụ:**

- Form chọn loại vé có mã `STD`, `VIP` và `STU`.
- Số lượng vé là số nguyên từ 1 đến 6.
- Tiền đặt cọc nhập theo hợp đồng định dạng được công bố cho locale hiện tại.
- Mã suất chiếu là UUID, nhưng suất chiếu có thể đã hết vé vào lúc thanh toán.
- Người dùng có thể sửa form từ trang review.

**Nhiệm vụ:**

1. Định nghĩa `TicketType` enum có mã công khai không phụ thuộc vào tên hằng Java.
2. Tạo `ShowId` value object parse từ chuỗi UUID.
3. Chọn `BigDecimal` cho tiền và công bố rõ cách nhập ở `vi-VN` và `en-US`.
4. Thiết kế `TicketDraft` với các property typed; khai báo `<binder>` cho từng view-state.
5. Viết converter, formatter và validation theo đúng trách nhiệm; không truy cập database trong converter.
6. Vẽ sơ đồ Web Flow cho lỗi conversion, lỗi range và kết quả nghiệp vụ `soldOut`.
7. Viết test parse/format round-trip và test binding trong flow.
8. Đảm bảo service kiểm tra lại giá, quyền, số vé và idempotency trước khi commit.

**Các test case bắt buộc:**

| Đầu vào | Kết quả cần có |
| --- | --- |
| `quantity=3` | Được convert và qua validation |
| `quantity=3.5` | Lỗi chuyển đổi, vẫn ở form |
| `quantity=0` | Chuyển được thành số nhưng validation từ chối |
| `ticketType=NOPE` | Lỗi mã enum, không chọn loại mặc định |
| `deposit=1.500,25` ở locale VI | Chỉ chấp nhận nếu formatter VI đã được cấu hình đúng |
| `showId` sai UUID | Lỗi conversion, không gọi service đặt vé |
| `showId` hợp dạng nhưng hết vé | Service trả outcome `soldOut`, flow đưa người dùng chọn lại |

Một thiết kế đạt yêu cầu cho phép xem lại và sửa giá trị đã nhập mà không mất ý nghĩa dữ liệu, giữ lỗi chuyển đổi tại field, và chỉ xác nhận thành công khi service đã kiểm tra/ghi nghiệp vụ an toàn.

## 19. Tổng kết và câu hỏi ôn tập

Trong Spring Web Flow, **binding** gắn tham số form vào model, **conversion** biến chuỗi thành kiểu Java, **formatting** quản lý dạng nhập/hiển thị, **validation** kiểm tra giá trị đã chuyển đổi và **service** kiểm tra điều kiện nghiệp vụ tại thời điểm thực hiện. Số nguyên, `BigDecimal`, enum có mã công khai và value object đều có vai trò riêng khi xử lý dữ liệu nhiều bước.

Flow sử dụng `view-state`, `event` và `transition` để giữ người dùng ở màn hình có lỗi hoặc đi tiếp khi hợp lệ. Hệ thống conversion của Web Flow phải được cấu hình thực tế và kiểm thử qua HTTP form; đăng ký một converter trong Spring Core/MVC chưa chứng minh nó đang được sử dụng ở Web Flow.

**Câu hỏi tự kiểm tra:**

1. Vì sao `"0"` có thể chuyển thành Integer thành công nhưng vẫn bị từ chối?
2. Nếu chuỗi `"1.234,50"` được nhập ở tiếng Việt, cần những thông tin nào để parse an toàn?
3. Khác biệt giữa `ServiceTier.valueOf(...)` và `ServiceTier.fromCode(...)` là gì?
4. Vì sao `SlotId` hợp dạng chưa đủ để xác nhận quyền đặt một khung giờ?
5. Converter Spring Core đã chạy unit test thành công thì có thể khẳng định form Web Flow bind đúng chưa?
6. Lỗi `attendees=abc` và kết quả slot hết chỗ khác nhau ở tầng xử lý và event như thế nào?
7. Vì sao form nhiều bước phải kiểm thử cả chiều parse lẫn chiều format sau Back/Edit?
