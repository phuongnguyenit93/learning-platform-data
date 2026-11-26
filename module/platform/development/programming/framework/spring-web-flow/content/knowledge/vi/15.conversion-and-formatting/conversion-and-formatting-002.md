# Tích hợp cơ chế chuyển kiểu và định dạng của Spring

Một hành trình nhiều bước trong **Spring Web Flow (SWF)** thường bắt đầu từ HTTP form: trình duyệt gửi toàn chuỗi như `"2026-12-15"`, `"2"` hoặc `"A12"`, nhưng model Java lại sử dụng `LocalDate`, `Integer` hay kiểu nghiệp vụ `RoomCode`. Khi flow điều hướng từ `view-state` nhập liệu sang `view-state` xem lại, các giá trị ấy cần được chuyển kiểu chính xác và hiển thị lại đúng định dạng. Nếu một controller Spring MVC và một Web Flow dùng **hai bộ quy tắc chuyển đổi khác nhau**, cùng một chuỗi có thể hợp lệ ở endpoint này nhưng lỗi ở endpoint kia.

Bài thuộc chương **Chuyển đổi và định dạng** của module `SPRING_WEB_FLOW`. Trọng tâm là kết nối **Spring Core ConversionService**, **Spring Formatting/FormatterRegistry** và **Spring Binding ConversionService** của Web Flow, dùng được cho form binding, validation, state/transition, tích hợp Spring MVC và việc giữ dữ liệu qua các request. Ví dụ dựa trên Spring MVC và Web Flow 3.x (Java 17/Spring Framework 6); khi dùng SWF 2.x hoặc 4.x cần kiểm tra API, namespace và cấu hình tương ứng với dòng phiên bản.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác nhau giữa **chuyển kiểu** (`Converter`), **định dạng** (`Formatter`), **binding** và **validation**.
2. Nhận diện đường đi của giá trị `String` trong HTTP request tới property Java và chiều ngược từ Java tới HTML.
3. Sử dụng `@DateTimeFormat`, `@NumberFormat`, `Converter`, `Formatter` và `FormatterRegistrar` đúng nhu cầu.
4. Cấu hình **một Spring FormattingConversionService dùng chung** cho Spring MVC và Spring Web Flow qua lớp cầu nối `DefaultConversionService`.
5. Xử lý lỗi `typeMismatch`, parse/print không đối xứng, khác locale hoặc converter không được đăng ký.
6. Viết kiểm thử chuyển đổi và kiểm thử flow để xác nhận người dùng nhập sai sẽ ở lại bước hiện tại, còn dữ liệu đúng được giữ qua các state.

## 2. Chuỗi xử lý thực tế từ form tới flow

Giả sử flow đặt phòng gồm:

~~~mermaid
stateDiagram-v2
    [*] --> details
    details --> review: next
    review --> details: back
    review --> finished: confirm
    finished --> [*]
~~~

Tại `details`, form có ba trường:

| Field trong form | Giá trị HTTP gửi lên | Kiểu Java đích | Ý nghĩa |
| --- | --- | --- | --- |
| `checkInDate` | `2026-12-15` | `LocalDate` | Ngày nhận phòng |
| `guests` | `2` | `Integer` | Số khách |
| `roomCode` | `a12` | `RoomCode` | Mã phòng được chuẩn hóa thành `A12` |

Luồng xử lý tổng quát:

~~~mermaid
flowchart TD
    A["HTTP POST: String parameters"] --> B["Web Flow nhận event next"]
    B --> C["Binder kiểm tra field được phép nhận"]
    C --> D["ConversionService: parse String thành kiểu Java"]
    D --> E{"Có lỗi conversion/binding?"}
    E -->|"Có"| F["Gắn thông báo lỗi; giữ view-state theo cấu hình"]
    E -->|"Không"| G["Validation: constraint + business rule"]
    G --> H{"Dữ liệu hợp lệ?"}
    H -->|"Không"| F
    H -->|"Có"| I["Transition sang review"]
    I --> J["FormattingConversionService: print Java value"]
    J --> K["Render view / form"]
~~~

Sơ đồ thể hiện vai trò từng cơ chế. Thứ tự chi tiết còn phụ thuộc cấu hình `view-state`, các action và chính sách validation. **Không có chuyện tự động chuyển tới state tiếp theo chỉ vì đã parse được chuỗi**: conversion mới kiểm tra cách biểu diễn, validation và quy tắc nghiệp vụ quyết định dữ liệu có thể được chấp nhận hay không.

## 3. Bốn khái niệm cần phân biệt

| Cơ chế | Trả lời câu hỏi | API thường dùng | Ví dụ |
| --- | --- | --- | --- |
| **Binding** | Chuỗi từ request được gán vào property nào? | Binder của Web Flow, Spring `DataBinder` | `checkInDate` → `booking.checkInDate` |
| **Conversion** | Đối tượng kiểu A được đổi sang kiểu B ra sao? | `Converter<S,T>`, `ConverterFactory`, `GenericConverter` | `String` → `RoomCode` |
| **Formatting** | Giá trị được **parse/print** thế nào theo kiểu field và locale? | `Formatter<T>`, `Printer`, `Parser` | `"15/12/2026"` ↔ ngày, tùy locale |
| **Validation** | Giá trị đã có kiểu có hợp lệ không? | Bean Validation, `Validator`, service | Không cho ngày trong quá khứ; số khách từ 1–4 |

Một converter có thể đổi `"2"` thành số nguyên `2`. Điều đó không đảm bảo khách được phép đặt cho 2 người, hay phòng còn chỗ trống. Validation và nghiệp vụ phải thực hiện các kiểm tra ấy.

### 3.1. `Converter<S,T>` dùng cho chuyển đổi tổng quát

Interface `org.springframework.core.convert.converter.Converter<S,T>` có một phương thức cốt lõi:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Nó phù hợp khi quy tắc chuyển đổi giữa hai kiểu **không phụ thuộc locale**, ví dụ `String` → giá trị mã nghiệp vụ, `Long` → mã định danh nội bộ, hoặc `String` → enum theo tập giá trị đã định nghĩa.

### 3.2. `Formatter<T>` dành cho giao diện người dùng

`org.springframework.format.Formatter<T>` kết hợp hai chiều:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    // print(T value, Locale locale) -> String
    // parse(String text, Locale locale) -> T
}
~~~

Nó phù hợp cho biểu diễn của người dùng: ngày, số, tiền tệ, phần trăm hoặc kiểu miền cần hiển thị lại trong form. Điểm quan trọng là **hai chiều parse/print** và khả năng dùng `Locale`.

### 3.3. `ConversionService` và `FormatterRegistry`

`org.springframework.core.convert.ConversionService` cung cấp API tra cứu và thực hiện conversion, như `canConvert` và `convert`. `FormattingConversionService` vừa là `ConversionService` vừa triển khai `FormatterRegistry` để đăng ký formatter, converter và các quy tắc annotation. Cấu hình ở một nơi giúp MVC và Web Flow dùng cùng quy tắc.

`FormatterRegistrar` là điểm gom đăng ký nhiều converter/formatter; `AnnotationFormatterFactory` dùng khi cần annotation định dạng riêng, ví dụ một annotation chỉ định cách diễn giải mã bưu chính cho từng field.

## 4. Kiến trúc tích hợp: có hai ConversionService mang tên tương tự

Một điểm dễ sai khi đọc API:

| Thành phần | Package | Vai trò |
| --- | --- | --- |
| Spring ConversionService | `org.springframework.core.convert.ConversionService` | API chuyển kiểu chung của Spring |
| FormattingConversionService | `org.springframework.format.support.FormattingConversionService` | Spring conversion + formatter, phục vụ binding/formatting |
| Web Flow ConversionService | `org.springframework.binding.convert.service.ConversionService` | Hợp đồng chuyển kiểu mà FlowBuilderServices/Web Flow sử dụng |
| DefaultConversionService của Web Flow | `org.springframework.binding.convert.service.DefaultConversionService` | Lớp Web Flow có thể **delegate** sang Spring ConversionService |

Các tên gần giống nhau nhưng **không được xem là cùng một interface**. Theo reference của Spring Web Flow, kể từ SWF 2.1, phần lớn conversion dựa vào cơ chế Spring. Mặc định Web Flow tạo `DefaultConversionService` của Spring Binding, chuyển việc chuyển kiểu thông dụng sang một Spring `FormattingConversionService` bên dưới; Spring MVC cũng có conversion service riêng. **Khi thêm formatter tùy chỉnh, phải cấu hình rõ để hai bên dùng chung quy tắc**.

~~~mermaid
flowchart TD
    R["HTTP form + Web Flow view-state"] --> W["Web Flow Binder"]
    M["Spring MVC Controller / DataBinder"] --> MC["MVC ConversionService"]
    W --> WF["Web Flow DefaultConversionService"]
    WF --> C["applicationConversionService"]
    MC --> C
    C --> F["Custom Formatter / Converter"]
    C --> D["Default formatters: date, number, enum..."]
~~~

Mô hình mong muốn là **cùng một `applicationConversionService`** hoặc một registry có đúng cùng converter/formatter, để cả hai lối đi thống nhất với nhau. Chỉ đặt `WebMvcConfigurer.addFormatters` trong ứng dụng Spring Boot **không chứng minh** Web Flow đang dùng cùng instance; phải kiểm tra dây nối ở FlowBuilderServices.

## 5. Ví dụ model nhiều bước với kiểu Java rõ ràng

Giả sử có kiểu bất biến đại diện cho mã phòng; mã chỉ gồm một chữ cái và hai chữ số:

~~~java
package com.example.booking;

import java.util.Locale;

public record RoomCode(String value) {
    public RoomCode {
        if (value == null || !value.matches("[A-Z][0-9]{2}")) {
            throw new IllegalArgumentException("Mã phòng phải có dạng A12");
        }
    }
}
~~~

Ví dụ dùng Java `record`, phù hợp nền Java 17+ của Spring Framework 6/SWF 3. Với ứng dụng SWF 2.5 đang dùng Java 8, thay `record` bằng class immutable thông thường.

Model form:

~~~java
package com.example.booking;

import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;

public class BookingForm {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate checkInDate;

    @NumberFormat(pattern = "#,##0")
    private Integer guests;

    private RoomCode roomCode;

    public LocalDate getCheckInDate() { return checkInDate; }
    public void setCheckInDate(LocalDate value) { this.checkInDate = value; }

    public Integer getGuests() { return guests; }
    public void setGuests(Integer value) { this.guests = value; }

    public RoomCode getRoomCode() { return roomCode; }
    public void setRoomCode(RoomCode value) { this.roomCode = value; }
}
~~~

Các annotation thể hiện **định dạng**, chưa thiết lập tính hợp lệ về nghiệp vụ. `@DateTimeFormat(iso = ISO.DATE)` dùng biểu diễn ISO như `2026-12-15`. `@NumberFormat(pattern = "#,##0")` cho phép formatter số có dấu phân nhóm theo locale; người dùng ở những locale khác nhau có thể thấy ký hiệu phân nhóm khác nhau. Chỉ dùng pattern được kiểm soát và thử với các locale thực tế.

Hãy lưu ý:

- `LocalDate` biểu diễn **ngày lịch** không kèm múi giờ; đặt phòng theo ngày có thể phù hợp, còn thời điểm check-in cụ thể liên quan múi giờ cần thiết kế khác.
- `Integer` có thể nhận `null` khi field không nhập; cần validation cho bắt buộc và phạm vi.
- `RoomCode` là kiểu miền đơn giản. Việc phòng có tồn tại, còn trống hay thuộc quyền truy cập của người dùng là quyết định **service**, không nên tự kiểm tra database trong formatter.

## 6. Tạo một Formatter tùy chỉnh có đủ hai chiều

Formatter cho `RoomCode` nhận `a12` hoặc ` A12 `, chuẩn hóa chữ hoa và in ra `A12`:

~~~java
package com.example.booking;

import java.text.ParseException;
import java.util.Locale;
import org.springframework.format.Formatter;

public final class RoomCodeFormatter implements Formatter<RoomCode> {
    @Override
    public RoomCode parse(String text, Locale locale) throws ParseException {
        String normalized = text.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z][0-9]{2}")) {
            throw new ParseException("Mã phòng phải có dạng A12", 0);
        }
        return new RoomCode(normalized);
    }

    @Override
    public String print(RoomCode value, Locale locale) {
        return value.value();
    }
}
~~~

Formatter **không chia sẻ trạng thái mutable** và dùng `Locale.ROOT` khi chuẩn hóa mã kỹ thuật để tránh hiện tượng chữ hoa/thường phụ thuộc ngôn ngữ như tiếng Thổ Nhĩ Kỳ. Không dùng `Locale.ROOT` cho mọi nội dung: với số tiền hoặc ngày tháng hiển thị cho con người, `locale` của request có thể cần được tôn trọng.

Vì formatter triển khai cả `parse` và `print`, dữ liệu nhận ở form và biểu diễn trả về trang review dùng cùng quy tắc:

| Đầu vào | `parse` | `print` | Kỳ vọng |
| --- | --- | --- | --- |
| `a12` | `RoomCode("A12")` | `A12` | Hợp lệ |
| ` A12 ` | `RoomCode("A12")` | `A12` | Hợp lệ, chuẩn hóa |
| `B07` | `RoomCode("B07")` | `B07` | Hợp lệ |
| `12A` | `ParseException` | — | Ghi lỗi binding/formatting |
| `B999` | `ParseException` | — | Ghi lỗi vì sai dạng |

Một nguyên tắc kiểm thử quan trọng là **round-trip**: với các giá trị hợp lệ, `parse(print(value, locale), locale)` phải giữ nguyên ý nghĩa của `value`. Tính đối xứng này đặc biệt quan trọng với form nhiều bước, nơi dữ liệu được render rồi submit lại.

## 7. Đăng ký formatter vào Spring FormattingConversionService

Có hai lựa chọn:

- **Quy tắc dùng chung theo kiểu:** đăng ký `RoomCodeFormatter` cho mọi field `RoomCode`.
- **Quy tắc theo annotation:** dùng `@DateTimeFormat` hoặc `@NumberFormat` cho các field cụ thể; tạo `AnnotationFormatterFactory` nếu dự án cần định dạng riêng.

Một ví dụ **XML dùng chung cho MVC và SWF** minh họa chính xác điểm nối:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:mvc="http://www.springframework.org/schema/mvc"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/mvc
         https://www.springframework.org/schema/mvc/spring-mvc.xsd
         http://www.springframework.org/schema/webflow-config
         https://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd">

    <!-- Spring conversion + formatter dùng chung -->
    <bean id="applicationConversionService"
          class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
        <property name="formatters">
            <set>
                <bean class="com.example.booking.RoomCodeFormatter"/>
            </set>
        </property>
    </bean>

    <!-- Spring MVC binding và formatter -->
    <mvc:annotation-driven conversion-service="applicationConversionService"/>

    <!-- Web Flow registry dùng FlowBuilderServices được cấu hình riêng -->
    <webflow:flow-registry id="flowRegistry"
                           flow-builder-services="flowBuilderServices">
        <webflow:flow-location path="/WEB-INF/flows/booking/booking.xml"/>
    </webflow:flow-registry>

    <webflow:flow-builder-services id="flowBuilderServices"
         conversion-service="webFlowConversionService"/>

    <!-- Adapter từ Web Flow conversion API sang Spring ConversionService -->
    <bean id="webFlowConversionService"
          class="org.springframework.binding.convert.service.DefaultConversionService">
        <constructor-arg ref="applicationConversionService"/>
    </bean>
</beans>
~~~

Ví dụ giả định ứng dụng đã có hạ tầng `FlowExecutor`, `FlowHandlerMapping`, `FlowHandlerAdapter`, ViewResolver, Spring Security nếu cần và các view thực tế. Nó trình bày **đoạn cấu hình conversion liên quan**, chưa đủ để một ứng dụng Web Flow khởi động độc lập. Nếu dự án dùng Java Config/`AbstractFlowConfiguration` hoặc Spring Boot, hãy cấu hình các bean tương đương bằng API của đúng version và tránh đăng ký trùng cấu hình MVC.

### 7.1. Vì sao không đưa thẳng Spring ConversionService vào Web Flow?

Trong XML, thuộc tính `conversion-service` của `webflow:flow-builder-services` nhận hợp đồng **Spring Binding ConversionService** của Web Flow. `applicationConversionService` lại là Spring Core `ConversionService`. Lớp `org.springframework.binding.convert.service.DefaultConversionService` có constructor nhận Spring Core `ConversionService` để **delegate**. Điều đó giải thích vì sao cần bean `webFlowConversionService` làm cầu nối trong ví dụ.

Nếu cố truyền sai interface, ứng dụng có thể lỗi khi nạp context, bean type mismatch hoặc chuyển kiểu dùng rule mặc định khác. Tên bean không quyết định loại API: cần kiểm tra **kiểu Java mà FlowBuilderServices thực sự đòi hỏi**.

### 7.2. Nếu dự án dùng Spring Boot và `WebMvcConfigurer`

Trong Spring MVC thuần, có thể đăng ký formatter bằng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcFormattingConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new RoomCodeFormatter());
    }
}
~~~

Đoạn này hữu ích để tùy chỉnh **MVC ConversionService**. Tuy nhiên **không nên coi đây là toàn bộ cấu hình SWF**: nếu Web Flow tạo conversion service riêng, formatter vừa đăng ký ở MVC chưa chắc hiện diện ở flow. Khi cần một logic thống nhất, cấu hình rõ Spring `FormattingConversionService` được dùng chung và bridge nó trong `FlowBuilderServices` như ví dụ XML, hoặc bảo đảm cả hai registry được đăng ký qua cùng một `FormatterRegistrar` rồi kiểm thử.

### 7.3. Gom nhiều quy tắc bằng FormatterRegistrar

~~~java
import org.springframework.format.FormatterRegistrar;
import org.springframework.format.FormatterRegistry;

public final class BookingFormatters implements FormatterRegistrar {
    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addFormatter(new RoomCodeFormatter());
        // Có thể đăng ký thêm formatter/converter khác cho module booking.
    }
}
~~~

Một `FormatterRegistrar` cho phép lắp đặt bộ chuyển kiểu nhất quán ở nhiều cấu hình, giảm sai sót khi duy trì ứng dụng có controller MVC và các flow. Nếu dùng đồng thời nhiều cách đăng ký, cần kiểm tra rule nào được ưu tiên khi chúng cùng áp dụng cho một cặp kiểu.

## 8. Kết nối vào view-state và binding

Trong flow định nghĩa model kiểu `BookingForm`:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.booking.BookingForm"/>

    <view-state id="details" view="booking/details" model="booking">
        <binder>
            <binding property="checkInDate" required="true"/>
            <binding property="guests" required="true"/>
            <binding property="roomCode" required="true"/>
        </binder>

        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="back" to="details"/>
        <transition on="confirm" to="finished">
            <evaluate expression="bookingService.confirm(booking)"/>
        </transition>
    </view-state>

    <end-state id="finished" view="booking/done"/>
    <end-state id="cancelled" view="booking/cancelled"/>
</flow>
~~~

Đây là **định nghĩa flow minh họa**; class, bean `bookingService`, các view và cấu hình registry/executor phải được cung cấp. Service cần kiểm tra lại quyền, trạng thái phòng, transaction và submit lặp trước khi ghi.

Trong ví dụ:

1. Khi form gửi `roomCode=a12`, binder tìm property `booking.roomCode` kiểu `RoomCode`.
2. Web Flow gọi conversion service đã cấu hình; `RoomCodeFormatter.parse` tạo `RoomCode("A12")`.
3. `checkInDate=2026-12-15` được định dạng theo `@DateTimeFormat(iso = ISO.DATE)`; `guests` được parse theo cấu hình số.
4. Nếu có lỗi parse hoặc field bắt buộc bị thiếu, Web Flow thu thập lỗi binding; theo cấu hình view-state, người dùng ở lại màn hình để sửa.
5. Nếu validation thành công, event `next` dẫn tới `review`. Khi render, formatter in `RoomCode("A12")` thành `A12`.
6. `back` quay lại `details` mà không cần biến chuỗi `A12` thành `RoomCode` lần nữa nếu model đã giữ object trong flow. Nhưng mỗi lần client gửi lại field thì binder vẫn cần conversion.

`<binder>` tạo **danh sách field được phép bind**; ngoài conversion, đây còn là biện pháp chống mass assignment. Không để client tự bind các property như `ownerId`, `price`, `approved` hoặc `role`. Conversion chỉ chuyển kiểu; nó không xác nhận người dùng được phép chỉnh thuộc tính.

## 9. Chuyển đổi trong action, expression và input/output

Type conversion không chỉ xuất hiện khi submit form. Trong một flow còn có:

| Vị trí | Ví dụ | Điểm cần nhớ |
| --- | --- | --- |
| Binding request | `String` từ form → `LocalDate` | Dựa trên kiểu property, annotation và formatter |
| Flow input | Tham số vào một flow hoặc subflow | Kiểm tra kiểu khai báo và giá trị thực tế |
| `<evaluate>` result | Giá trị trả từ service được đưa vào model/scope | Có thể cần `result-type` hoặc conversion khi loại khác nhau |
| Hiển thị view | `RoomCode` → chuỗi `A12` | Cần formatter/print theo locale |
| Gọi service qua expression | Expression cần coercion tham số theo kiểu Java | Phải hiểu conversion service và lỗi expression |

Ví dụ khai báo flow input có type:

~~~xml
<input name="guestCount" type="java.lang.Integer" required="true"/>
~~~

Hoặc chỉ định kiểu cho kết quả evaluate khi cần:

~~~xml
<evaluate expression="bookingService.findAvailableRooms(booking)"
          result="flowScope.rooms"/>
~~~

Phần tử `evaluate` hỗ trợ các thuộc tính kết quả và kiểu kết quả theo schema của phiên bản SWF. Không cố đưa mọi conversion vào biểu thức EL bằng cách gọi static parser thủ công; tốt hơn là đăng ký converter/formatter ở tầng framework để dễ dùng lại và kiểm thử.

**Phân biệt với flow scope:** `flowScope` giữ object đã chuyển kiểu xuyên qua các state theo vòng đời execution, còn conversion service là thành phần ứng dụng dùng chung. Không lưu formatter, locale resolver mutable hoặc service instance tùy biến vào `flowScope` của mỗi người dùng.

## 10. Ngày, số và Locale: điểm phát sinh bug phổ biến

### 10.1. Ngày theo chuẩn ISO và ngày hiển thị địa phương

Ví dụ `<input type="date">` trong HTML thường gửi ngày theo ISO `yyyy-MM-dd` (giá trị form mà trình duyệt gửi), dù giao diện người dùng có thể hiển thị theo ngôn ngữ hệ điều hành. `@DateTimeFormat(iso = ISO.DATE)` cho model `LocalDate` là lựa chọn rõ ràng cho giá trị HTML này.

Nếu ứng dụng dùng text input định dạng `dd/MM/uuuu`, phải dùng formatter hay annotation với pattern được định nghĩa rõ. **Đừng trộn** một control gửi ISO với formatter kỳ vọng ngày kiểu địa phương mà không có quy tắc nhất quán.

Khi xử lý **thời điểm** có múi giờ, `LocalDateTime` không tự mang timezone. Chọn `OffsetDateTime`/`ZonedDateTime` hoặc chuẩn UTC khi nghiệp vụ cần thời điểm tuyệt đối và quy tắc múi giờ cụ thể. Conversion không tự giải quyết múi giờ doanh nghiệp.

### 10.2. Số và ký hiệu phân nhóm/thập phân

| Locale ví dụ | Chuỗi thường thấy | Nguy cơ |
| --- | --- | --- |
| `en_US` | `1,234.50` | Dùng dấu phẩy phân nhóm và dấu chấm thập phân |
| `de_DE` | `1.234,50` | Vai trò của dấu chấm và dấu phẩy bị đảo |
| `vi_VN` | Có thể dùng `1.234,50` tùy formatter/CLDR/JDK | Cần kiểm thử trên JDK và locale production |

Không được dùng `String.replace(",", ".")` đơn giản cho mọi loại tiền/số: chuỗi có dấu phân nhóm có thể bị diễn giải sai nghiêm trọng. Với dữ liệu trao đổi **giữa các hệ thống**, hãy dùng biểu diễn chuẩn, ví dụ JSON number hoặc decimal string nhất quán; với form **dành cho người dùng**, sử dụng formatter có locale được xác định.

Các pattern định dạng dựa trên locale có thể thay đổi khi cập nhật JDK/CLDR; với dữ liệu cần ổn định giữa các môi trường, dùng **ISO hoặc pattern tường minh** và kiểm thử hồi quy sau nâng JDK.

### 10.3. Locale được chọn ở đâu?

Spring MVC thường xác định locale qua `LocaleResolver` hoặc `LocaleContextResolver`. Khi Spring Formatter được gọi, request locale có thể ảnh hưởng `parse`/`print`. Trong Web Flow, cần xác minh cơ chế truyền locale của view integration; đừng giả định mọi request trong cùng một execution luôn dùng cùng locale.

Nếu người dùng đổi ngôn ngữ trong lúc flow đang chạy, những field đã lưu là object Java vẫn giữ giá trị; chỉ **cách in lại** có thể thay đổi. Test quan trọng: giá trị format ở locale A không được tự động phân tích như locale B nếu form cũ được submit sau khi đổi locale.

## 11. Conversion, validation và thông báo lỗi

Khi `checkInDate=không-phải-ngày`, conversion không tạo được `LocalDate`. Khi `checkInDate=2026-12-15` nhưng lịch hẹn thuộc ngày đã bị khóa, conversion vẫn thành công nhưng **validation hoặc business rule** phải từ chối.

| Tình huống | Tầng phát hiện | Kết quả mong muốn |
| --- | --- | --- |
| `guests=abc` | Conversion (`String` → `Integer`) | Lỗi type mismatch, form không chuyển bước |
| `roomCode=C123` | `RoomCodeFormatter.parse` | Lỗi parse, trả về màn hình nhập |
| `guests=0` | Bean/business validation | Không hợp lệ dù chuyển được sang số 0 |
| `checkInDate` trước ngày được phép | Validation | Thông báo rõ quy tắc ngày |
| Phòng không còn trống | Service/database | Không xác nhận dù mã phòng đúng định dạng |
| Client gửi `ownerId=someoneElse` | Binder whitelist / authorization | Không bind trường nhạy cảm; service kiểm tra quyền |

Để hiển thị lỗi tốt:

1. Cấu hình message bundle của ứng dụng, gồm thông báo cho field bắt buộc, type mismatch và lỗi nghiệp vụ.
2. Giữ **giá trị nhập gốc và thông báo tương ứng** khi conversion thất bại; tránh buộc người dùng nhập lại toàn bộ form.
3. Khi binding lỗi, không gọi action xác nhận nghiệp vụ.
4. Không ghi stack trace hoặc nội dung nhạy cảm trong lỗi người dùng thấy.
5. Kiểm tra trường nào được bind/validate trên event `next`; các event như `cancel` có thể dùng `bind="false"` để tránh yêu cầu chuyển kiểu dữ liệu không liên quan.

**Lưu ý:** `@DateTimeFormat` và `@NumberFormat` là annotation về định dạng, **không thay thế** `@NotNull`, `@Min`, `@Max` hay validator riêng. Trong SWF 3+/Spring 6, Bean Validation thuộc namespace `jakarta.validation.*`; trên ứng dụng SWF 2.5/Spring 5 thường gặp `javax.validation.*`.

## 12. Hướng dẫn kiểm thử độc lập conversion service

Trước khi gắn Web Flow, thử quy tắc parse và print trực tiếp:

~~~java
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.format.support.DefaultFormattingConversionService;

import static org.junit.jupiter.api.Assertions.*;

class RoomCodeFormattingTest {
    @Test
    void parsesAndPrintsTheSameRoomCode() {
        var conversion = new DefaultFormattingConversionService();
        conversion.addFormatter(new RoomCodeFormatter());

        RoomCode code = conversion.convert(" a12 ", RoomCode.class);

        assertNotNull(code);
        assertEquals("A12", code.value());
        assertEquals("A12", conversion.convert(code, String.class));
    }

    @Test
    void rejectsAnInvalidRoomCode() {
        var conversion = new DefaultFormattingConversionService();
        conversion.addFormatter(new RoomCodeFormatter());

        assertThrows(RuntimeException.class,
            () -> conversion.convert("room 1234", RoomCode.class));
    }
}
~~~

Ví dụ dành cho **JUnit Jupiter** và Java 17. Kiểu exception được assert theo nhóm `RuntimeException` để không phụ thuộc vào cách Spring bọc `ParseException`; trong dự án thực, nên kiểm tra exception cụ thể, message và mã lỗi binding mà phiên bản Spring đang sử dụng trả về.

Kiểm thử riêng `Formatter` với locale:

~~~java
import java.util.Locale;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RoomCodeFormatterTest {
    @Test
    void roundTrip() throws Exception {
        var formatter = new RoomCodeFormatter();
        RoomCode original = formatter.parse(" b07 ", Locale.forLanguageTag("vi-VN"));
        String text = formatter.print(original, Locale.forLanguageTag("vi-VN"));
        RoomCode restored = formatter.parse(text, Locale.forLanguageTag("vi-VN"));

        assertEquals(original, restored);
        assertEquals("B07", text);
    }
}
~~~

Sau đó bổ sung test `@DateTimeFormat(ISO.DATE)` và `@NumberFormat` với các locale trong ứng dụng. Với ngày, bao gồm **năm nhuận, ngày không tồn tại, giá trị trống và định dạng không đúng**.

## 13. Kiểm thử tích hợp với Spring MVC và Web Flow

Kiểm thử converter độc lập **không chứng minh nó đã được đăng ký** ở cả hai integration. Cần kiểm thử thêm:

| Lớp kiểm thử | Hành động | Bằng chứng cần có |
| --- | --- | --- |
| Unit formatter | Parse/print `a12` và `B07` | Không có lỗi, kết quả nhất quán |
| Unit conversion service | `convert(" a12 ", RoomCode.class)` | Registry đã nhận formatter |
| Spring MVC integration | Gửi `roomCode=a12` vào controller/form | MVC bind thành `RoomCode("A12")` |
| Web Flow integration | POST `_eventId=next` tại `details` | Web Flow bind vào `BookingForm` cùng kết quả |
| Validation | Gửi `guests=0` | Không qua `review` nếu rule cấm |
| Conversion error | Gửi `roomCode=123` hoặc ngày sai | Vẫn ở form, có thông báo |
| Round-trip view | Từ `details` → `review` → `back` | Mã phòng và ngày không biến dạng |
| Locale | Thử `vi-VN` và `en-US` | Ngày/số được xử lý theo format chủ đích |
| Session/flow | Tạm dừng và quay lại flow trong cùng execution | Object đã chuyển kiểu vẫn đúng, không trộn tab |

Một bộ test Web Flow nên tạo context có đúng `flowRegistry`, `flowBuilderServices` và `webFlowConversionService`; một bộ test MVC có `applicationConversionService`. Nếu Spring Boot auto-config tạo MVC conversion service riêng, integration test phải chỉ rõ **bean nào được dùng**.

Ví dụ kịch bản thủ công ở trình duyệt:

1. Mở `/booking` và chọn `15/12/2026` ở UI nếu hiển thị địa phương; kiểm tra request body thực sự gửi định dạng nào.
2. Gửi `roomCode=a12`; trang review phải hiển thị `A12`.
3. Bấm `back`; form vẫn hiển thị đúng ngày, số khách, mã phòng.
4. Gửi ngày sai hoặc mã phòng sai; flow không xác nhận nghiệp vụ và hiện lỗi có thể hiểu.
5. Thử hai tab/flow executions; dữ liệu bản nháp của hai hành trình không bị trộn.

## 14. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| MVC nhận `roomCode` nhưng flow báo type mismatch | Formatter chỉ đăng ký ở MVC | Kiểm tra `flow-builder-services` và bridge `DefaultConversionService` |
| Application context không khởi tạo được | Nhầm Spring Core `ConversionService` với Spring Binding `ConversionService` | Xem bean type, constructor, namespace và stack trace |
| `ClassNotFoundException` với `jakarta`/`javax` | Trộn version Java EE/Jakarta | Soát Spring/SWF/Servlet/Validation dependency tree |
| Không parse được `LocalDate` | Thiếu formatter, sai pattern, trình duyệt gửi ISO khác dự kiến | Đọc HTTP payload và annotation `@DateTimeFormat` |
| Ngày bị đảo tháng/ngày | Locale thay đổi hoặc pattern nhập không khớp | Test các locale, dùng ISO/pattern rõ |
| Số `1,234` có nghĩa khác giữa hai môi trường | Locale, DecimalFormat hoặc JDK/CLDR khác | Ghi locale/JDK, test round-trip |
| `parse` thành công nhưng view in sai | Chỉ đăng ký converter một chiều | Dùng formatter hai chiều hoặc bổ sung chiều reverse |
| Event `cancel` cũng báo lỗi parse field không liên quan | Binder/validation vẫn chạy trên transition | Kiểm tra `bind="false"`/`validate="false"` theo semantics |
| Model lưu được nhưng xem lại mất giá trị | Scope/flow execution hoặc view rendering sai | Kiểm tra `flowScope`, view-state, model binding |
| Chuỗi bất kỳ đổi thành entity nhạy cảm | Converter gọi repository và bỏ qua quyền | Chuyển kiểm tra quyền và tải entity về service |
| Lỗi sau khi nâng JDK | Localized date/number behavior thay đổi | Test formatter theo locale; ưu tiên ISO/pattern tường minh |

### 14.1. Tránh ba cách xử lý “chữa cháy”

**Một là:** không parse thủ công cùng một field ở nhiều controller/flow bằng `LocalDate.parse(...)` với pattern khác nhau. Đăng ký quy tắc chung và test.

**Hai là:** không “sửa” lỗi bằng cách ép tất cả property form thành `String` rồi chuyển kiểu sâu trong service không kiểm soát. Điều này làm khó hiển thị lỗi field và khiến business service phải xử lý cả cú pháp giao diện.

**Ba là:** không để converter quyết định **quyền truy cập, giá phòng, trạng thái thanh toán hoặc tính hợp lệ nghiệp vụ** chỉ từ input của client. Formatter có thể xác định `RoomCode("A12")` đúng cú pháp; service mới quyết định tài khoản có được đặt phòng `A12` hay không.

## 15. Bài tập tự thực hành

### Bài A — phân loại trách nhiệm

Với một form có `checkInDate`, `guests`, `roomCode`, `ownerId`, hãy gán mỗi việc vào đúng lớp:

1. Phân tích ngày `2026-12-15` thành `LocalDate`.
2. Giới hạn không nhận `ownerId` do client gửi.
3. Kiểm tra `guests >= 1`.
4. Xác định người đăng nhập có quyền đặt phòng không.
5. In mã `RoomCode("B07")` thành `B07` khi render form.

**Đáp án:** (1) conversion/formatting; (2) binding whitelist; (3) validation; (4) authorization ở service; (5) formatter `print`.

### Bài B — tự cấu hình hai conversion service

Viết cấu hình sao cho Spring MVC và Web Flow dùng chung `applicationConversionService` có `RoomCodeFormatter`. Chứng minh bằng hai integration tests gửi `roomCode=a12` qua:

- controller MVC dùng `@ModelAttribute`;
- Web Flow `details` khi nhận event `next`.

**Điều kiện đạt:** cả hai đều tạo `RoomCode("A12")`; nhập `roomCode=xx` đều trả lỗi đúng field mà không chuyển state/khởi động nghiệp vụ.

### Bài C — thử khác locale

Thêm một field tiền gửi `BigDecimal` và đánh giá `@NumberFormat` với `en-US` và `vi-VN`. So sánh giá trị hiển thị, chuỗi submit, kết quả parse và kiểm tra có giữ chính xác giá trị số ban đầu không. Không dùng formatter thay cho quy tắc tính tiền hoặc cho phép client tự quyết định giá.

### Bài D — phát hiện lỗi khi nâng framework

Ứng dụng Spring 5/SWF 2.5 đang dùng `javax.validation` và custom `PropertyEditor`. Sau nâng Spring 6/SWF 3, MVC form vẫn chạy nhưng Web Flow chuyển kiểu sai.

Hãy kiểm tra theo thứ tự: version JDK/Spring/SWF/Jakarta; bean MVC conversion service; bean Web Flow `DefaultConversionService`; formatter/converter registration; binding whitelist; validation provider; integration tests. Tránh suy rằng chỉ đổi namespace `javax` sang `jakarta` là đã di chuyển xong toàn bộ quy tắc chuyển đổi.

## 16. Checklist khi đưa conversion vào flow thật

- [ ] Đã xác định kiểu Java đích của từng form field.
- [ ] Đã phân biệt rõ binding, conversion, formatting, validation và authorization.
- [ ] Đã chọn `Converter` cho chuyển đổi tổng quát, `Formatter` cho parse/print dạng người dùng.
- [ ] `@DateTimeFormat`/`@NumberFormat` được khai báo đúng kiểu field và dữ liệu HTTP thực tế.
- [ ] Có chính sách locale nhất quán, kiểm thử các locale và JDK được hỗ trợ.
- [ ] MVC và Web Flow cùng dùng quy tắc chuyển kiểu, được kết nối qua bridge phù hợp.
- [ ] Không nhầm `org.springframework.core.convert.ConversionService` với interface conversion service của Spring Binding.
- [ ] `view-state` binder chỉ nhận các field được phép và xử lý lỗi parse đúng cách.
- [ ] Các transition nhạy cảm kiểm tra validation và service/business rule trước commit.
- [ ] `flowScope` chỉ giữ dữ liệu hành trình cần thiết; không trộn dữ liệu giữa phiên/tab.
- [ ] Có unit test parse/print/round-trip và integration test ở cả MVC/Web Flow.
- [ ] Lỗi chuyển kiểu không gây commit nghiệp vụ, không làm lộ dữ liệu nhạy cảm.

## 17. Tài liệu tham khảo

1. [Spring Web Flow 3.0.2 — Performing Type Conversion](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/) — mục **13.6**, đặc biệt cấu hình `DefaultConversionService` delegate tới Spring `FormattingConversionService`, named converter legacy và annotation formatting.
2. [Spring Web Flow 3.0.2 — System Setup](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/) — mục **18.3.7** về `FlowBuilderServices` và conversion service tùy chỉnh.
3. [Spring Framework — Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html) — `ConversionService`, `Converter`, `ConverterFactory`, `GenericConverter`.
4. [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html) — `Formatter`, `FormatterRegistry`, annotation, quy tắc locale và `FormatterRegistrar`.
5. [Spring Boot — Servlet Web Applications / Spring MVC Conversion Service](https://docs.spring.io/spring-boot/reference/web/servlet.html) — `WebMvcConfigurer.addFormatters`, MVC conversion service và cấu hình format.
6. [Spring Web Flow 2.5.1 — Reference Guide](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/) — đối chiếu integration cũ khi cần migrate.

**Điểm cần nhớ:** Dữ liệu form chỉ là `String` tại ranh giới HTTP; Spring `FormattingConversionService` cung cấp quy tắc chuyển kiểu/định dạng dùng lại được. Spring Web Flow có **lớp conversion service riêng** để tích hợp, vì vậy phải nối rõ ràng với service của Spring MVC khi muốn form trong controller và trong flow hành xử nhất quán. Conversion làm dữ liệu có đúng **kiểu**, validation và service mới quyết định dữ liệu có được **chấp nhận và ghi lại**.
