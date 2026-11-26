# Ngày giờ, múi giờ và kiểu dữ liệu tương thích

## Mục tiêu bài học

Trong Spring Web Flow, dữ liệu gửi từ form thường đến dưới dạng chuỗi. Khi người dùng nhập ngày nhận phòng, giờ hẹn hoặc thời điểm bắt đầu sự kiện, Web Flow phải chuyển chuỗi đó thành kiểu Java của model trước khi chạy validation và transition. Khi render lại, ứng dụng cũng cần chuyển giá trị Java thành chuỗi mà giao diện hiển thị được.

Với ngày giờ, chuyển đổi kiểu còn phải trả lời câu hỏi **giá trị đó đại diện cho điều gì**:

- Một ngày trên lịch, không phụ thuộc múi giờ?
- Một giờ trong ngày, chưa gắn với ngày cụ thể?
- Một thời điểm tuyệt đối trên dòng thời gian?
- Một giờ địa phương theo múi giờ của địa điểm tổ chức?

Nếu chọn sai kiểu dữ liệu, hệ thống có thể hiển thị lệch ngày, đặt lịch sai giờ hoặc tạo ra hai cách hiểu khác nhau cho cùng một request.

Sau bài này, bạn có thể:

1. Chọn `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime` hoặc `ZonedDateTime` theo ý nghĩa nghiệp vụ.
2. Phân biệt **formatting**, **type conversion**, **locale** và **time zone**.
3. Cấu hình `ConversionService` dùng trong Spring Web Flow và chia sẻ formatter với Spring MVC.
4. Dùng `@DateTimeFormat`, `Formatter`, `Converter` và `DateTimeFormatterRegistrar`.
5. Bind các giá trị từ HTML date/time controls vào model của `view-state`.
6. Xử lý giờ mùa hè (DST), khoảng trống và giờ bị lặp khi chuyển giờ địa phương thành thời điểm tuyệt đối.
7. Tương thích với `java.util.Date`, `java.sql.Date`, `Timestamp` và dữ liệu cũ.
8. Kiểm thử dữ liệu sai định dạng, múi giờ khác nhau, ngày nhuận và các thời điểm biên.

## 1. Ngày giờ có nhiều ý nghĩa khác nhau

Không nên chọn kiểu Java chỉ vì tên thuộc tính là `date`, `time` hay `createdAt`. Hãy xác định ý nghĩa trước.

| Nhu cầu nghiệp vụ | Kiểu Java nên cân nhắc | Ví dụ |
| --- | --- | --- |
| Một ngày trên lịch | `LocalDate` | Ngày sinh, ngày nghỉ phép, ngày nhận phòng |
| Một giờ trong ngày | `LocalTime` | Giờ mở cửa, giờ bắt đầu ca |
| Ngày và giờ địa phương chưa gắn múi giờ | `LocalDateTime` | Người dùng nhập 09:30 ngày 20/05 |
| Một thời điểm tuyệt đối trên dòng thời gian | `Instant` | Thời điểm tạo bản ghi, thời điểm sự kiện đã xảy ra |
| Ngày giờ kèm độ lệch UTC cụ thể | `OffsetDateTime` | `2026-05-20T09:30:00+07:00` |
| Ngày giờ kèm tên múi giờ và quy tắc vùng | `ZonedDateTime` | 09:30 tại `Asia/Ho_Chi_Minh` |
| Một độ lệch UTC riêng | `ZoneOffset` | `+07:00`, `Z` |
| Một vùng múi giờ theo cơ sở dữ liệu IANA | `ZoneId` | `Asia/Ho_Chi_Minh`, `Europe/Paris` |

### 1.1. `LocalDate` không phải một thời điểm

`LocalDate.of(2026, 5, 20)` biểu diễn ngày 20/05/2026. Nó không chứa giờ, offset hay timezone. Ngày sinh `2000-10-31` không trở thành ngày khác chỉ vì server chạy ở UTC còn người dùng ở một vùng khác.

Vì vậy, không nên biến một `LocalDate` thành `Date` bằng cách tự gắn múi giờ mặc định của máy rồi lưu timestamp nếu nghiệp vụ chỉ cần ngày trên lịch. Khi đọc lại ở múi giờ khác, giá trị có thể bị lệch ngày.

### 1.2. `LocalDateTime` không phải thời điểm tuyệt đối

`LocalDateTime.of(2026, 5, 20, 9, 30)` chỉ nói “09:30 ngày 20/05/2026”. Nó không cho biết 09:30 ở đâu.

Nếu hai người ở hai múi giờ cùng nhập `09:30`, đó có thể là hai thời điểm thực tế khác nhau. Muốn biến giờ địa phương thành một thời điểm tuyệt đối, phải có thêm `ZoneId` hoặc `ZoneOffset`.

### 1.3. `Instant` biểu diễn một điểm trên dòng thời gian

`Instant` được chuẩn hóa theo UTC và phù hợp cho:

- Thời điểm tạo/cập nhật bản ghi.
- Thời điểm nhận request.
- Thời điểm một sự kiện đã xảy ra.
- Thời điểm cần so sánh, sắp xếp hoặc tính khoảng thời gian trên toàn hệ thống.

Ví dụ:

```java
Instant occurredAt = Instant.parse("2026-05-20T02:30:00Z");
```

Giá trị này là một thời điểm duy nhất. Khi hiển thị ở một vùng khác, ứng dụng chuyển `Instant` sang timezone tương ứng; bản thân `Instant` không thay đổi.

### 1.4. `OffsetDateTime` và `ZonedDateTime` khác nhau

`OffsetDateTime` có ngày giờ và offset, ví dụ `+07:00`. Offset cho biết chênh lệch so với UTC tại thời điểm đó, nhưng không mang đầy đủ quy tắc của vùng địa lý.

`ZonedDateTime` còn có `ZoneId`, ví dụ `Europe/Paris`. Nó có thể áp dụng quy tắc đổi giờ theo mùa (DST) của vùng đó.

Một offset `+01:00` không đủ để đại diện cho tất cả quy tắc của Paris trong cả năm. Vào một thời điểm khác, Paris có thể dùng `+02:00`.

## 2. Locale, timezone và định dạng là ba khái niệm riêng

Ba khái niệm thường bị trộn lẫn:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Locale** | Người dùng đọc ngày/tháng/số theo quy ước ngôn ngữ nào? | `vi-VN`, `en-US` |
| **Time zone** | Giờ địa phương thuộc vùng nào trên thế giới? | `Asia/Ho_Chi_Minh`, `Europe/Paris` |
| **Format/pattern** | Chuỗi ngày giờ được viết theo cấu trúc nào? | `dd/MM/uuuu`, `yyyy-MM-dd'T'HH:mm` |

Locale `vi-VN` không tự động có nghĩa timezone là `Asia/Ho_Chi_Minh`. Một người nói tiếng Việt có thể sống ở Paris; một ứng dụng có thể hiển thị tiếng Anh nhưng đặt lịch theo timezone của khách sạn.

`Formatter<T>` của Spring nhận `Locale` trong `parse` và `print`, còn timezone cần được xử lý rõ ràng bằng kiểu dữ liệu và quy tắc nghiệp vụ. Không nên kỳ vọng thay locale là tự chuyển thời điểm từ UTC sang giờ địa phương.

### Ví dụ cùng một thời điểm, hai cách hiển thị

```java
Instant instant = Instant.parse("2026-05-20T02:30:00Z");

ZonedDateTime vietnam =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime paris =
        instant.atZone(ZoneId.of("Europe/Paris"));
```

Hai giá trị `vietnam` và `paris` biểu diễn cùng một `Instant`, nhưng phần giờ địa phương khác nhau. Việc định dạng chuỗi có thể dùng locale khác nhau mà không làm thay đổi thời điểm gốc.

## 3. HTML form gửi ngày giờ theo quy ước nào?

Các control ngày giờ của HTML có định dạng giá trị riêng. Giao diện trình duyệt có thể hiển thị theo ngôn ngữ máy, nhưng **giá trị được submit** theo dạng chuẩn của HTML.

| HTML control | Ví dụ giá trị submit | Kiểu Java phù hợp |
| --- | --- | --- |
| `<input type="date">` | `2026-05-20` | `LocalDate` |
| `<input type="time">` | `09:30` hoặc `09:30:15` | `LocalTime` |
| `<input type="datetime-local">` | `2026-05-20T09:30` | `LocalDateTime` |
| Text input tự do | `20/05/2026` | Kiểu phù hợp với formatter được cấu hình |

**`datetime-local` không gửi timezone hoặc offset.** Nó chỉ gửi ngày giờ địa phương mà người dùng chọn. Nếu đó là lịch hẹn tại một địa điểm cụ thể, form cần truyền thêm `ZoneId` hoặc ứng dụng phải biết timezone của địa điểm từ nguồn tin cậy.

Ví dụ giao diện:

```html
<label for="arrivalDate">Ngày nhận phòng</label>
<input id="arrivalDate"
       name="arrivalDate"
       type="date"
       value="2026-05-20">

<label for="arrivalTime">Giờ nhận phòng</label>
<input id="arrivalTime"
       name="arrivalTime"
       type="time"
       value="09:30">

<label for="meetingAt">Thời điểm địa phương</label>
<input id="meetingAt"
       name="meetingAt"
       type="datetime-local"
       value="2026-05-20T09:30">
```

Các giá trị HTML trên không phải định dạng hiển thị duy nhất. Trình duyệt có thể trình bày theo locale, nhưng request vẫn dùng chuỗi máy có quy ước xác định. Vì vậy, với control chuẩn, nên dùng ISO-compatible format thay vì cố ép server parse theo cách viết `dd/MM/yyyy`.

## 4. Spring Web Flow chuyển đổi dữ liệu form như thế nào?

Khi `view-state` bind một model, request parameter thường là chuỗi. Web Flow cần chuyển chuỗi thành kiểu của thuộc tính trước khi gán:

```xml
<view-state id="enterBookingDetails"
            view="booking/details"
            model="booking">
    <binder>
        <binding property="arrivalDate" required="true" />
        <binding property="arrivalTime" required="true" />
    </binder>
    <transition on="review" to="reviewBooking" />
</view-state>
```

Nếu model khai báo:

```java
private LocalDate arrivalDate;
private LocalTime arrivalTime;
```

Web Flow cần một conversion/formatting service có thể xử lý các kiểu tương ứng. Khi bind thành công, validation model mới tiếp tục được thực hiện. Nếu chuỗi không parse được, Web Flow tạo lỗi binding/conversion và render lại view để người dùng sửa.

### Converter và Formatter

Spring cung cấp hai abstraction chính:

| Abstraction | Mục đích | Khi nên dùng |
| --- | --- | --- |
| `Converter<S, T>` | Chuyển một kiểu object sang kiểu object khác | `String` → enum, ID → value object, `Date` → `Instant` |
| `Formatter<T>` | Parse/print giữa `String` và một kiểu object, có hỗ trợ `Locale` | Ngày/giờ người dùng nhập và hiển thị trong form |

`Formatter<T>` kế thừa `Printer<T>` và `Parser<T>`. Đây thường là lựa chọn phù hợp cho field web vì phải xử lý cả hai chiều:

```text
Request string → parse → LocalDate
View model     → print → Request/display string
```

Không viết một converter chỉ parse từ `String` nếu view cũng cần in giá trị Java ra form; formatter giải quyết cả hai chiều.

## 5. Chọn `java.time` cho model

Với ứng dụng Java hiện đại, nên ưu tiên API `java.time` thay cho các lớp mutable/khó hiểu về timezone của API ngày giờ cũ.

Ví dụ model:

```java
import java.io.Serializable;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.LocalDateTime;

import org.springframework.format.annotation.DateTimeFormat;

public class BookingDraft implements Serializable {
    private static final long serialVersionUID = 1L;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate arrivalDate;

    @DateTimeFormat(iso = DateTimeFormat.ISO.TIME)
    private LocalTime arrivalTime;

    @DateTimeFormat(pattern = "uuuu-MM-dd'T'HH:mm")
    private LocalDateTime localArrival;

    private String zoneId;

    // Getter/setter
}
```

Giải thích:

- `arrivalDate` nhận chuỗi ISO date `2026-05-20`.
- `arrivalTime` nhận giờ như `09:30`.
- `localArrival` nhận ngày giờ địa phương của `datetime-local`, không có offset.
- `zoneId` giữ tên vùng múi giờ riêng, ví dụ `Asia/Ho_Chi_Minh`.

Trong ứng dụng thật, hãy kiểm tra `zoneId` có hợp lệ bằng `ZoneId.of(...)` và người dùng có được phép chọn vùng đó hay không. Nếu timezone được xác định bởi địa điểm, hãy lấy từ cấu hình địa điểm thay vì tin một giá trị form có thể bị sửa.

### Không gán timezone cho `LocalDate` hoặc `LocalTime` một cách tùy tiện

`LocalDate` không cần timezone. `LocalTime` cũng không cần timezone nếu chỉ biểu diễn giờ mở cửa hoặc giờ hẹn trong một lịch địa phương chưa xác định ngày. Nếu chuyển chúng thành `Instant`, phải có đủ thông tin ngày và vùng giờ.

## 6. Định dạng ngày giờ bằng `@DateTimeFormat`

Spring có annotation `@DateTimeFormat` để kiểm soát cách parse và print giá trị trong quá trình data binding.

### 6.1. Dùng ISO khi có thể

```java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate date;

@DateTimeFormat(iso = DateTimeFormat.ISO.TIME)
private LocalTime time;

@DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
private OffsetDateTime occurredAt;
```

ISO giúp format nhất quán giữa trình duyệt, server và API. Với `LocalDateTime` được bind từ HTML `datetime-local`, có thể dùng pattern chính xác:

```java
@DateTimeFormat(pattern = "uuuu-MM-dd'T'HH:mm")
private LocalDateTime localMeetingTime;
```

Không gắn offset vào field `LocalDateTime` nếu client không gửi offset. Nếu form gửi `2026-05-20T09:30+07:00`, kiểu phù hợp hơn là `OffsetDateTime`.

### 6.2. Dùng pattern khi nghiệp vụ yêu cầu

Ví dụ text input hiển thị `20/05/2026`:

```java
@DateTimeFormat(pattern = "dd/MM/uuuu")
private LocalDate arrivalDate;
```

Các ký hiệu thường gặp:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `dd` | Ngày trong tháng | `20` |
| `MM` | Tháng | `05` |
| `uuuu` | Năm theo lịch ISO | `2026` |
| `HH` | Giờ 24 giờ | `09`, `17` |
| `hh` | Giờ 12 giờ | `09` |
| `mm` | Phút | `30` |
| `ss` | Giây | `45` |
| `XXX` | Offset dạng `+07:00` | `+07:00` |
| `VV` | Tên vùng timezone | `Asia/Ho_Chi_Minh` |
| `a` | AM/PM | `AM` |

Những lỗi pattern rất thường gặp:

- `MM` là tháng; `mm` là phút.
- `HH` là giờ 24h; `hh` là giờ 12h.
- `yyyy` là year-of-era; `YYYY` là week-based year, có thể cho kết quả khác quanh đầu/cuối năm.
- Với định dạng nghiêm ngặt theo lịch, `uuuu` thường là lựa chọn rõ ràng cho proleptic year.

Nếu format cần hiển thị theo locale, cân nhắc `style` hoặc một formatter nhận `Locale`. Với dữ liệu máy/API, ISO hoặc pattern cố định thường dễ tương thích hơn format phụ thuộc locale.

### 6.3. Tương thích JDK mới

Các style format phụ thuộc locale và môi trường Java có thể thay đổi theo JDK. Từ JDK 20 trở lên, một số hành vi locale-based date/time/number formatting có thể khác các runtime cũ. Với dữ liệu được lưu, trao đổi giữa service hoặc gửi từ HTML control, ưu tiên **ISO hoặc pattern cố định do ứng dụng kiểm soát**; không dựa vào `SHORT` style nếu cần chuỗi ổn định qua nhiều môi trường.

## 7. Cấu hình `ConversionService` dùng trong Spring Web Flow

Spring Web Flow dùng hệ thống type conversion và formatting của Spring cho phần lớn nhu cầu data binding. Tuy nhiên, `ConversionService` được tạo mặc định cho Web Flow **không nhất thiết là cùng một instance** với conversion service của Spring MVC.

Khi bắt đầu đăng ký formatter riêng, hãy nối rõ hai nơi để tránh trường hợp:

```text
Spring MVC controller parse được LocalDate
nhưng view-state của Spring Web Flow lại báo typeMismatch
```

### 7.1. Tạo `FormattingConversionService` dùng chung

Ví dụ cấu hình XML:

```xml
<bean id="applicationConversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="formatters">
        <set>
            <bean class="com.example.format.LocalDateDmyFormatter" />
        </set>
    </property>
</bean>

<bean id="webFlowConversionService"
      class="org.springframework.binding.convert.service.DefaultConversionService">
    <constructor-arg ref="applicationConversionService" />
</bean>

<mvc:annotation-driven
        conversion-service="applicationConversionService" />

<webflow:flow-builder-services
        id="flowBuilderServices"
        conversion-service="webFlowConversionService" />

<webflow:flow-registry
        id="flowRegistry"
        flow-builder-services="flowBuilderServices">
    <webflow:flow-location
            path="/WEB-INF/flows/booking/booking.xml" />
</webflow:flow-registry>
```

Đoạn XML minh họa cách nối conversion service:

- `applicationConversionService` là Spring `FormattingConversionService` chứa formatter.
- Spring MVC dùng nó qua `mvc:annotation-driven`.
- Web Flow Binding `DefaultConversionService` delegate tới cùng service đó.
- `flow-builder-services` truyền conversion service cho flow registry khi build flow.

Đảm bảo ứng dụng đã khai báo các XML namespace `beans`, `mvc`, `webflow` và schema tương ứng. Nếu đã có `flow-builder-services` ở nơi khác, hãy cấu hình trên registry thực sự sử dụng nó; đừng tạo hai registry rồi vô tình dùng registry mặc định.

Một số flow cũ có thể khai báo converter theo tên ngay trên binding, ví dụ `<binding property="arrivalDate" converter="shortDate" />`. Cơ chế named converter của Spring Binding được giữ lại vì tương thích ngược nhưng đã deprecated; với ứng dụng mới, nên đăng ký `Converter`/`Formatter` trong Spring `ConversionService` để MVC và Web Flow dùng chung quy tắc.

### 7.2. Đăng ký JSR-310 formatter cho `java.time`

Có thể dùng `DateTimeFormatterRegistrar` để đăng ký formatter cho các kiểu `java.time`:

```java
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.format.support.FormattingConversionServiceFactoryBean;

public class ApplicationConversionServiceFactoryBean
        extends FormattingConversionServiceFactoryBean {

    @Override
    protected void installFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
```

`setUseIsoFormat(true)` yêu cầu các formatter JSR-310 dùng chuẩn ISO thay vì style phụ thuộc locale. Nếu muốn pattern toàn cục riêng cho `LocalDate`, `LocalTime` hoặc `LocalDateTime`, có thể dùng `setDateFormatter(...)`, `setTimeFormatter(...)`, `setDateTimeFormatter(...)` tương ứng trước khi gọi `registerFormatters(...)`.

Ví dụ:

```java
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import org.springframework.format.FormatterRegistry;

void registerDateTimeFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar =
            new DateTimeFormatterRegistrar();

    registrar.setDateFormatter(
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT));
    registrar.setTimeFormatter(
        DateTimeFormatter.ofPattern("HH:mm")
                .withResolverStyle(ResolverStyle.STRICT));
    registrar.setDateTimeFormatter(
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm")
                .withResolverStyle(ResolverStyle.STRICT));

    registrar.registerFormatters(registry);
}
```

Đoạn này đặt pattern mặc định cho các kiểu JSR-310 tương ứng. Nếu cùng ứng dụng có HTML `date` control và text field dùng `dd/MM/uuuu`, hãy tránh cấu hình global khiến chuỗi ISO mà browser submit không parse được. Có thể dùng `@DateTimeFormat` riêng trên field hoặc tách formatter theo mục đích.

Lưu ý: `setDateTimeFormatter(...)` được dùng cho `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime`. Pattern `dd/MM/uuuu HH:mm` ở ví dụ chỉ phù hợp với dữ liệu giờ địa phương không mang offset/zone. Nếu model có `OffsetDateTime` hoặc `ZonedDateTime`, hãy dùng format có phần offset/zone tương ứng hoặc khai báo formatter riêng cho field đó.

Các pattern global ở ví dụ dùng `ResolverStyle.STRICT` để từ chối ngày không tồn tại thay vì tự điều chỉnh. Khi tự viết `Formatter`, hãy quyết định rõ mức strictness; với lịch đặt chỗ hoặc ngày nghiệp vụ quan trọng, không nên âm thầm chuẩn hóa một ngày sai.

### 7.3. Dùng Java configuration

Trong Spring MVC, có thể đăng ký formatter qua `WebMvcConfigurer`:

```java
@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
        registry.addFormatter(new LocalDateDmyFormatter());
    }
}
```

Đối với Web Flow, `FlowBuilderServices` cũng phải nhận conversion service tương ứng. Tùy cấu hình Java/XML của ứng dụng, có thể tạo `DefaultConversionService` của Spring Binding delegate tới cùng `FormattingConversionService` rồi gọi `setConversionService(...)` trên builder. Không nên chỉ cấu hình MVC và mặc định cho rằng Web Flow sẽ tự dùng đúng instance đó.

## 8. Viết custom `Formatter<LocalDate>`

Khi cần nhận chuỗi `20/05/2026` cho một field text, formatter riêng giúp kiểm soát cả parse và print.

```java
package com.example.format;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.format.Formatter;

public class LocalDateDmyFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter formatter(Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale)
            throws ParseException {
        try {
            return LocalDate.parse(text, formatter(locale));
        } catch (DateTimeParseException ex) {
            ParseException parseException = new ParseException(
                    "Ngày phải có dạng dd/MM/yyyy",
                    Math.max(0, ex.getErrorIndex()));
            parseException.initCause(ex);
            throw parseException;
        }
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return value == null ? "" : formatter(locale).format(value);
    }
}
```

Formatter có hai chiều:

- `parse`: chuyển chuỗi từ client thành `LocalDate`.
- `print`: chuyển `LocalDate` thành chuỗi hiển thị.

`DateTimeFormatter` là immutable và thread-safe, phù hợp để tạo theo locale như ví dụ. Nếu dùng pattern cố định và không phụ thuộc locale, có thể giữ một formatter dùng chung làm `static final`.

Trong message lỗi, pattern ghi `dd/MM/yyyy` để người dùng dễ hiểu, trong khi pattern kỹ thuật dùng `uuuu`. Hai cách viết không mâu thuẫn: `uuuu` phù hợp với việc parse/format năm lịch theo `DateTimeFormatter`.

### Formatter không thay thế validation nghiệp vụ

Formatter chỉ xác nhận chuỗi có thể chuyển thành kiểu ngày. Ví dụ `31/02/2026` không phải ngày hợp lệ nên parse thất bại. Nhưng `20/05/2026` có thể parse đúng mà vẫn không hợp lệ với nghiệp vụ nếu ngày đó đã qua hoặc khách sạn không nhận phòng.

Tách thành:

```text
String request
  → Formatter: parse thành LocalDate
  → Validator: kiểm tra ngày hợp lệ theo nghiệp vụ
  → Transition: chỉ đi tiếp khi không có lỗi
```

## 9. `Converter` cho kiểu ngày giờ hoặc value object riêng

`Converter<S, T>` phù hợp khi chuyển đổi giữa hai kiểu object, không cần locale. Ví dụ ứng dụng có value object `BusinessDate`:

```java
import java.time.LocalDate;
import java.util.Objects;

public record BusinessDate(LocalDate value) {
    public BusinessDate {
        Objects.requireNonNull(value);
    }
}
```

Converter:

```java
import java.time.LocalDate;
import org.springframework.core.convert.converter.Converter;

public class StringToBusinessDateConverter
        implements Converter<String, BusinessDate> {

    @Override
    public BusinessDate convert(String source) {
        return new BusinessDate(LocalDate.parse(source));
    }
}
```

Đăng ký trong formatter/conversion service:

```java
import org.springframework.format.FormatterRegistry;

void registerConverters(FormatterRegistry registry) {
    registry.addConverter(new StringToBusinessDateConverter());
}
```

Đây là ví dụ cho chuỗi ISO `yyyy-MM-dd`. Nếu đầu vào cần phụ thuộc locale hoặc cần in ngược ra giao diện, hãy dùng `Formatter<BusinessDate>` thay vì chỉ có converter một chiều.

### Hạn chế converter theo ngữ cảnh

Không nên viết một converter chung chung kiểu:

```text
String → Date
```

rồi đoán chuỗi đó là `dd/MM/yyyy`, `MM/dd/yyyy` hay ISO theo dữ liệu đầu vào. Chuỗi `03/04/2026` có thể được hiểu là ngày 3 tháng 4 hoặc ngày 4 tháng 3. Hãy xác định format ở field hoặc API contract; không suy đoán.

## 10. Múi giờ: chuyển giờ địa phương thành thời điểm

Giả sử người dùng đặt lịch họp:

```text
Ngày: 20/05/2026
Giờ: 09:30
Địa điểm: Paris
```

Model form có thể giữ:

```java
LocalDate date;
LocalTime time;
String zoneId;
```

Khi cần một thời điểm thực tế:

```java
LocalDateTime localDateTime =
        LocalDateTime.of(date, time);

ZoneId zone = ZoneId.of(zoneId);
ZonedDateTime zonedDateTime =
        localDateTime.atZone(zone);

Instant scheduledInstant =
        zonedDateTime.toInstant();
```

`scheduledInstant` là điểm trên dòng thời gian. `zoneId` nên được lưu riêng nếu ứng dụng còn cần hiển thị lại theo vùng ban đầu hoặc giải thích giờ địa phương của cuộc hẹn.

### Không dùng `ZoneId.systemDefault()` làm quy tắc nghiệp vụ

Server có thể chạy trong container UTC, máy developer ở timezone khác, còn khách hàng chọn lịch tại một địa điểm thứ ba. `ZoneId.systemDefault()` phản ánh cấu hình máy đang chạy; nó không nhất thiết là timezone của người dùng hoặc địa điểm tổ chức.

Hãy lấy zone từ:

- Cấu hình địa điểm/chi nhánh đã lưu.
- Lựa chọn timezone hợp lệ của người dùng.
- Quy tắc nghiệp vụ của sự kiện hoặc lịch làm việc.

Không tin một chuỗi timezone tùy ý mà không xác thực:

```java
ZoneId zone;
try {
    zone = ZoneId.of(requestedZoneId);
} catch (DateTimeException ex) {
    throw new InvalidTimeZoneException(requestedZoneId);
}
```

`InvalidTimeZoneException` là exception minh họa do ứng dụng định nghĩa. Có thể giới hạn danh sách vùng được phép thay vì chấp nhận mọi ID có trong tz database.

## 11. DST: giờ địa phương có thể không tồn tại hoặc bị lặp

Một số vùng đổi đồng hồ theo mùa. Khi chuyển giờ mùa xuân, một khoảng giờ địa phương có thể bị bỏ qua. Khi chuyển giờ mùa thu, một khoảng giờ có thể xuất hiện hai lần.

Ví dụ tại `Europe/Paris`:

- Một giờ địa phương nằm trong khoảng nhảy đồng hồ có thể **không tồn tại**.
- Một giờ địa phương trong khoảng đồng hồ quay lùi có thể tương ứng với **hai offset** khác nhau.

Đây là lý do `LocalDateTime` cộng với `ZoneId` đôi khi chưa đủ để chọn một `Instant` duy nhất nếu không có chính sách xử lý DST.

### 11.1. Kiểm tra giờ hợp lệ

```java
LocalDateTime local =
        LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Paris");

List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(local);
```

Kết quả:

- `offsets.isEmpty()`: giờ địa phương nằm trong khoảng không tồn tại (DST gap).
- `offsets.size() == 1`: chỉ có một offset hợp lệ.
- `offsets.size() == 2`: giờ địa phương bị lặp (DST overlap), có hai cách hiểu.

Với overlap, ứng dụng có thể yêu cầu người dùng chọn lần xuất hiện đầu hay lần thứ hai, hoặc áp dụng chính sách nghiệp vụ được công bố rõ. Không nên âm thầm chọn một offset nếu thời điểm đó quan trọng như chuyến bay, khám bệnh hoặc giao dịch tài chính.

### 11.2. `atZone()` có thể tự điều chỉnh

`localDateTime.atZone(zoneId)` áp dụng quy tắc của `ZoneRules`. Với giờ nằm trong gap, Java có thể điều chỉnh về phía trước theo độ dài khoảng trống; với overlap, nó có chính sách chọn offset mặc định. Nếu nghiệp vụ yêu cầu từ chối giờ không tồn tại hoặc bắt người dùng chọn offset, hãy kiểm tra `getValidOffsets(...)` trước khi gọi `atZone(...)`.

### 11.3. Một hàm chuyển đổi có chính sách rõ ràng

```java
public Instant toInstantStrict(LocalDateTime local, ZoneId zone) {
    List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);

    if (offsets.isEmpty()) {
        throw new IllegalArgumentException(
                "Giờ địa phương không tồn tại do chuyển giờ mùa");
    }

    if (offsets.size() > 1) {
        throw new IllegalArgumentException(
                "Giờ địa phương bị lặp, cần chọn offset");
    }

    return local.toInstant(offsets.get(0));
}
```

Hàm trên chọn chính sách **từ chối overlap** để yêu cầu caller xử lý rõ. Nếu ứng dụng muốn cho phép overlap, hãy nhận thêm `ZoneOffset` do người dùng chọn và xác nhận offset đó thuộc danh sách hợp lệ của `ZoneRules`.

## 12. Tương thích kiểu dữ liệu cũ

Nhiều ứng dụng Spring cũ dùng `java.util.Date`, `Calendar`, `java.sql.Date` hoặc `java.sql.Timestamp`. Cần biết ý nghĩa từng loại trước khi chuyển sang `java.time`.

| Kiểu cũ | Ý nghĩa gần đúng | Kiểu mới nên cân nhắc |
| --- | --- | --- |
| `java.util.Date` | Một thời điểm theo epoch milliseconds | `Instant` |
| `java.sql.Date` | Ngày SQL, không phải timestamp thông thường | `LocalDate` |
| `java.sql.Time` | Giờ SQL | `LocalTime` |
| `java.sql.Timestamp` | Timestamp SQL, có độ chính xác nano trong API | `LocalDateTime` hoặc `Instant`, tùy schema/ngữ nghĩa |
| `Calendar` | Ngày giờ cùng timezone/calendar state | `ZonedDateTime`, hoặc tách instant và zone |

### 12.1. Chuyển đổi `java.util.Date` và `Instant`

```java
Date legacyDate = new Date();
Instant instant = legacyDate.toInstant();

Date backToDate = Date.from(instant);
```

`Date` về bản chất là một timestamp, không chứa timezone. Việc in `Date` bằng `toString()` sử dụng timezone mặc định của môi trường, nên cùng một object có thể hiện chuỗi khác trên hai máy.

### 12.2. Chuyển đổi SQL date/time

```java
java.sql.Date sqlDate = java.sql.Date.valueOf(
        LocalDate.of(2026, 5, 20));
LocalDate localDate = sqlDate.toLocalDate();

java.sql.Time sqlTime = java.sql.Time.valueOf(
        LocalTime.of(9, 30));
LocalTime localTime = sqlTime.toLocalTime();
```

Với `java.sql.Timestamp`, có thể dùng `toInstant()` khi cột và driver đang biểu diễn một thời điểm tuyệt đối. Nếu schema cũ dùng timestamp không timezone để lưu giờ địa phương, hãy xác định timezone quy ước trước khi chuyển; không tự giả định nó là UTC.

### 12.3. Không chuyển mọi `Date` thành `LocalDate`

Nếu `Date` cũ đại diện cho thời điểm tạo đơn, chuyển sang `LocalDate` sẽ làm mất giờ/phút/giây và ý nghĩa thời điểm. Ngược lại, nếu cột SQL `DATE` đại diện cho ngày sinh, chuyển nó thành `Instant` có thể tạo thêm một timezone không tồn tại trong nghiệp vụ.

Hãy phân loại dữ liệu theo ý nghĩa, không chỉ theo kiểu Java hiện tại.

## 13. Lưu ngày giờ trong database

Kiểu Java, kiểu cột database và timezone phải thống nhất.

| Ý nghĩa | Kiểu Java | Kiểu SQL thường cân nhắc | Lưu ý |
| --- | --- | --- | --- |
| Ngày lịch | `LocalDate` | `DATE` | Không đổi theo timezone |
| Giờ trong ngày | `LocalTime` | `TIME` | Không phải thời điểm tuyệt đối |
| Ngày giờ địa phương | `LocalDateTime` | `TIMESTAMP` không timezone | Cần biết zone quy ước khi diễn giải |
| Thời điểm tuyệt đối | `Instant` | Timestamp theo UTC hoặc kiểu hỗ trợ instant của DB | Kiểm tra mapping driver/dialect |
| Ngày giờ có offset | `OffsetDateTime` | Kiểu timestamp có timezone tùy DB | Nhiều DB chuẩn hóa instant và không giữ nguyên tên vùng |
| Ngày giờ theo vùng | `ZonedDateTime` | Lưu instant + zone ID hoặc schema riêng | Đừng giả định DB giữ nguyên đầy đủ `ZoneId` |

Với PostgreSQL, chẳng hạn `timestamp with time zone` lưu một instant được chuẩn hóa, không giữ tên vùng gốc như `Europe/Paris`. Nếu ứng dụng cần biết người dùng chọn vùng nào để hiển thị lại hoặc áp dụng lịch tương lai, lưu `ZoneId` riêng.

### Quy tắc thực hành

- Lưu `Instant`/UTC cho thời điểm hệ thống đã xảy ra.
- Lưu `LocalDate` cho ngày trên lịch.
- Lưu `LocalTime` cho giờ mở cửa/giờ cố định trong ngày.
- Với lịch hẹn tương lai tại địa điểm cụ thể, lưu thông tin giờ địa phương và `ZoneId`, đồng thời xác định thời điểm cụ thể theo chính sách DST.
- Không dùng timestamp để giả lập ngày lịch nếu không có lý do.
- Kiểm tra mapping thực tế của JPA provider, JDBC driver và database dialect; không suy luận chỉ từ tên kiểu SQL.

### Lịch tương lai và thay đổi quy tắc timezone

Quy tắc timezone có thể được cập nhật bởi cơ quan quản lý. Nếu ứng dụng lưu một lịch định kỳ “09:00 giờ địa phương mỗi thứ Hai”, lưu mỗi `Instant` có thể không đủ để tái hiện ý định ban đầu sau khi quy tắc vùng thay đổi.

Trong trường hợp đó, cần giữ:

```text
localDateTime / recurring local rule
zoneId
quy tắc chọn offset khi DST overlap
```

Nếu lịch đã được xác nhận cho một lần cụ thể, có thể lưu thêm `Instant` đã tính để biết chính xác thời điểm mà hệ thống đã cam kết.

## 14. Tích hợp vào `view-state`: ví dụ đặt lịch

Ví dụ flow có màn hình nhập ngày giờ, xem lại rồi xác nhận:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <on-start>
        <evaluate expression="appointmentFactory.newDraft()"
                  result="flowScope.appointment" />
    </on-start>

    <view-state id="enterAppointment"
                view="appointment/edit"
                model="appointment">
        <binder>
            <binding property="date" required="true" />
            <binding property="time" required="true" />
            <binding property="zoneId" required="true" />
        </binder>
        <transition on="review" to="reviewAppointment" />
        <transition on="cancel" to="cancelled" bind="false" />
    </view-state>

    <view-state id="reviewAppointment"
                view="appointment/review">
        <transition on="edit" to="enterAppointment" bind="false" />
        <transition on="confirm" to="saveAppointment" bind="false" />
    </view-state>

    <action-state id="saveAppointment">
        <evaluate expression="appointmentFlowAction.schedule(appointment)" />
        <transition on="saved" to="completed" />
        <transition on="invalidTime" to="enterAppointment" />
        <transition on="slotUnavailable" to="slotUnavailable" />
    </action-state>

    <view-state id="slotUnavailable"
                view="appointment/unavailable">
        <transition on="chooseAgain" to="enterAppointment" bind="false" />
    </view-state>

    <end-state id="completed" />
    <end-state id="cancelled" />
</flow>
```

Đây là flow minh họa. `appointmentFactory`, `appointmentService`, model, view và validator là thành phần ứng dụng cần triển khai. Nếu cần chọn timezone, view phải hiển thị danh sách zone hợp lệ và model phải xác nhận ID đó. Nếu giờ bị lặp do DST, bước xác nhận hoặc service phải yêu cầu offset cụ thể theo chính sách.

### Model minh họa

```java
import java.io.Serializable;
import java.time.LocalDate;
import java.time.LocalTime;

import org.springframework.format.annotation.DateTimeFormat;

public class AppointmentDraft implements Serializable {
    private static final long serialVersionUID = 1L;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate date;

    @DateTimeFormat(iso = DateTimeFormat.ISO.TIME)
    private LocalTime time;

    private String zoneId;

    // Getter/setter
}
```

Service xác thực và chuyển đổi:

```java
@Transactional
public AppointmentReceipt schedule(AppointmentDraft draft) {
    ZoneId zone = ZoneId.of(draft.getZoneId());
    LocalDateTime local = LocalDateTime.of(
            draft.getDate(), draft.getTime());

    List<ZoneOffset> offsets =
            zone.getRules().getValidOffsets(local);

    if (offsets.isEmpty()) {
        throw new InvalidAppointmentTimeException();
    }
    if (offsets.size() > 1) {
        throw new AmbiguousAppointmentTimeException();
    }

    Instant instant = local.toInstant(offsets.get(0));
    // Kiểm tra quyền, slot, trạng thái lịch và ghi trong transaction.
    return repository.createAppointment(local, zone, instant);
}
```

`AppointmentReceipt`, repository và các exception là thành phần minh họa. Ví dụ cố ý từ chối giờ overlap để tránh tự chọn một thời điểm mà người dùng không mong muốn. Nếu cho phép người dùng chọn offset, cần bind thêm giá trị lựa chọn và xác nhận nó nằm trong `offsets`.

`appointmentFlowAction` là adapter phía flow gọi service và trả outcome dạng chuỗi cho Web Flow:

```java
public String schedule(AppointmentDraft draft) {
    try {
        appointmentService.schedule(draft);
        return "saved";
    } catch (InvalidAppointmentTimeException ex) {
        return "invalidTime";
    } catch (AmbiguousAppointmentTimeException ex) {
        return "invalidTime";
    } catch (SlotUnavailableException ex) {
        return "slotUnavailable";
    }
}
```

Adapter bắt các lỗi nghiệp vụ đã dự kiến sau khi lời gọi service transactional kết thúc bằng rollback. Lỗi hạ tầng hoặc exception không mong đợi cần tiếp tục đi theo cơ chế exception handling; không biến chúng thành `saved`.

**Validation format không thay thế kiểm tra lịch:** một chuỗi có thể parse thành `LocalDate` và `LocalTime` nhưng slot đã kín hoặc giờ địa phương không tồn tại theo timezone. Service phải kiểm tra các điều kiện đó ngay trước khi ghi.

## 15. Thông báo lỗi chuyển đổi trong Spring Web Flow

Khi conversion thất bại, Web Flow tạo lỗi binding như `typeMismatch` và có thể lấy nội dung từ message bundle theo property.

Ví dụ model `Booking` có field `checkinDate`. Nếu người dùng nhập `abc`, key thông báo có thể là:

```properties
booking.checkinDate.typeMismatch=Ngày nhận phòng không đúng định dạng
```

Có thể bổ sung các key khác:

```properties
booking.arrivalTime.typeMismatch=Giờ nhận phòng phải theo dạng HH:mm
booking.localArrival.typeMismatch=Thời điểm phải theo dạng yyyy-MM-dd'T'HH:mm
booking.zoneId.typeMismatch=Múi giờ không hợp lệ
```

Phân biệt hai nhóm lỗi:

| Nhóm | Ví dụ | Nguồn |
| --- | --- | --- |
| Binding/conversion error | `20/99/2026`, `abc`, chuỗi có offset trong field `LocalDateTime` không phù hợp | Converter/Formatter hoặc conversion service |
| Validation/business error | Ngày nhận phòng đã qua, ngày trả trước ngày nhận, giờ rơi vào DST gap | Validator hoặc service nghiệp vụ |

Khi lỗi conversion xảy ra, model có thể chưa nhận được giá trị mới ở field đó. Không nên giả định model validation có thể xử lý một giá trị chưa parse được; hãy để binding error hiển thị đúng.

## 16. Kiểm thử ngày giờ và timezone

Một formatter có thể chạy tốt trên máy developer nhưng sai khi triển khai do locale, timezone mặc định hoặc phiên bản JDK khác. Hãy kiểm thử bằng dữ liệu cố định và timezone được chỉ định rõ.

| Kịch bản | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| ISO date hợp lệ | `2026-05-20` | Parse thành `LocalDate` đúng |
| Ngày nhuận hợp lệ | `2024-02-29` | Parse thành ngày nhuận |
| Ngày không tồn tại | `2026-02-29` | Conversion error |
| Text pattern hợp lệ | `20/05/2026` với `dd/MM/uuuu` | Parse đúng ngày 20 tháng 5 |
| Nhầm tháng/phút | Pattern dùng `mm` cho tháng | Test phát hiện chuỗi không đúng |
| HTML time | `09:30` | Parse thành `LocalTime` |
| HTML datetime-local | `2026-05-20T09:30` | Parse thành `LocalDateTime`, không tự thêm zone |
| ISO offset | `2026-05-20T09:30:00+07:00` | Parse thành `OffsetDateTime` |
| UTC instant | `2026-05-20T02:30:00Z` | Parse thành `Instant` |
| Zone không tồn tại | `Mars/Olympus` | `ZoneId.of` thất bại |
| DST gap | Local time không tồn tại tại vùng chọn | Từ chối hoặc áp dụng chính sách đã định |
| DST overlap | Local time có hai offset hợp lệ | Yêu cầu chọn hoặc áp dụng chính sách rõ |
| Locale khác nhau | `vi-VN`, `en-US` | Text formatter phản ánh quy tắc đã thiết kế |
| Timezone server khác user | Server UTC, zone form là Paris | Kết quả vẫn theo zone nghiệp vụ |
| JDK khác phiên bản | Cùng ISO input | Parse/print giữ định dạng ổn định |
| Legacy timestamp | `java.util.Date` | Chuyển sang `Instant` không mất thời điểm |
| SQL date | `java.sql.Date` | Chuyển sang `LocalDate` không tạo timezone giả |

### 16.1. Unit test formatter

```java
class LocalDateDmyFormatterTest {

    private final LocalDateDmyFormatter formatter =
            new LocalDateDmyFormatter();

    @Test
    void parsesAndPrintsVietnameseDate() throws ParseException {
        Locale locale = Locale.forLanguageTag("vi-VN");

        LocalDate value = formatter.parse("20/05/2026", locale);

        assertEquals(LocalDate.of(2026, 5, 20), value);
        assertEquals("20/05/2026", formatter.print(value, locale));
    }
}
```

Ví dụ dùng JUnit 5. Bổ sung test cho chuỗi rỗng, ngày không tồn tại, locale khác và pattern thực tế của ứng dụng.

### 16.2. Kiểm thử conversion service

Sau khi đăng ký formatter, kiểm tra cả hai chiều:

```java
assertTrue(conversionService.canConvert(String.class, LocalDate.class));

LocalDate date = conversionService.convert(
        "20/05/2026", LocalDate.class);

assertEquals(LocalDate.of(2026, 5, 20), date);
```

Nếu có formatter gắn theo annotation, cần kiểm thử qua binder/model binding để xác nhận annotation được áp dụng. Một test gọi `LocalDate.parse(...)` trực tiếp không chứng minh Web Flow đang dùng đúng `ConversionService`.

### 16.3. Kiểm thử tích hợp flow

Với flow test hoặc Spring MVC integration test:

1. Khởi chạy flow và vào `enterAppointment`.
2. Submit `date=2026-05-20`, `time=09:30`, `zoneId=Asia/Ho_Chi_Minh`.
3. Xác nhận model nhận đúng kiểu `LocalDate`, `LocalTime` và chuỗi zone.
4. Submit ngày sai định dạng; xác nhận view ở lại và có message `typeMismatch`.
5. Submit ngày đúng format nhưng vi phạm nghiệp vụ; xác nhận validator trả lỗi khác với conversion error.
6. Xác nhận service tạo đúng `Instant` theo timezone đã chọn.
7. Chạy test DST gap/overlap với một zone có quy tắc DST.

Không chỉ assert trang có status HTTP 200; hãy kiểm tra giá trị model sau binding và kết quả thời điểm ở tầng service.

## 17. Các lỗi thường gặp và cách khắc phục

### 17.1. MVC parse được nhưng Web Flow báo `typeMismatch`

**Nguyên nhân:** hai nơi dùng `ConversionService` khác nhau; formatter chỉ được đăng ký trong MVC.

**Khắc phục:** nối formatter vào service được truyền cho `flow-builder-services`, tốt nhất chia sẻ cùng `FormattingConversionService` như ví dụ cấu hình.

### 17.2. Ngày bị đảo tháng và ngày

**Nguyên nhân:** client gửi `MM/dd/yyyy` nhưng formatter parse `dd/MM/yyyy`, hoặc ngược lại.

**Khắc phục:** dùng ISO cho control/API; nếu dùng text input, quy định pattern rõ và không đoán từ chuỗi.

### 17.3. Ngày lệch một ngày khi lưu/đọc

**Nguyên nhân:** dùng timestamp/`Date` cho dữ liệu chỉ có ý nghĩa `LocalDate`, rồi chuyển timezone khi render.

**Khắc phục:** dùng `LocalDate` và cột `DATE` cho ngày lịch; chỉ chuyển thành instant khi nghiệp vụ có thời điểm cụ thể.

### 17.4. Giờ bị lệch khi server chạy UTC

**Nguyên nhân:** coi `LocalDateTime` là UTC hoặc dùng `ZoneId.systemDefault()` dù lịch thuộc timezone địa điểm khác.

**Khắc phục:** truyền/lưu `ZoneId` theo nghiệp vụ; chuyển sang `Instant` có chủ đích.

### 17.5. `datetime-local` không parse vào `OffsetDateTime`

**Nguyên nhân:** browser gửi `2026-05-20T09:30` không có offset, trong khi field đòi hỏi offset.

**Khắc phục:** bind vào `LocalDateTime`, rồi kết hợp zone đã xác định; hoặc đổi contract form để gửi offset rõ ràng nếu thật sự cần `OffsetDateTime`.

### 17.6. DST làm lịch nhảy giờ hoặc chọn sai lần xuất hiện

**Nguyên nhân:** chuyển `LocalDateTime` sang `ZonedDateTime` mà không kiểm tra gap/overlap.

**Khắc phục:** kiểm tra `ZoneRules.getValidOffsets(...)`, xác định chính sách cho gap và overlap, yêu cầu người dùng chọn khi cần.

### 17.7. Dùng `YYYY` khiến ngày đầu/cuối năm sai

**Nguyên nhân:** `YYYY` là week-based year, không phải năm lịch thông thường.

**Khắc phục:** dùng `uuuu` hoặc `yyyy` theo mục đích, và test các ngày quanh giao năm.

### 17.8. Formatter không thread-safe

**Nguyên nhân:** dùng `SimpleDateFormat` mutable làm field singleton mà không đồng bộ.

**Khắc phục:** ưu tiên `DateTimeFormatter` immutable; nếu buộc dùng API cũ, tạo formatter theo request hoặc bảo đảm an toàn luồng.

### 17.9. Chuyển đổi thành công nhưng dữ liệu nghiệp vụ sai

**Nguyên nhân:** parse đúng format nhưng không kiểm tra ngày quá khứ, slot đã kín hoặc giờ nằm ngoài giờ làm việc.

**Khắc phục:** tách conversion khỏi validation; kiểm tra chính sách và dữ liệu mới nhất ở service trước khi commit.

## 18. Bài tập thực hành

Bạn xây dựng flow đặt lịch tư vấn:

```text
enterAppointment → reviewAppointment → saveAppointment → completed
```

Form gồm:

- `appointmentDate`: ngày tư vấn.
- `appointmentTime`: giờ tư vấn.
- `zoneId`: múi giờ của cơ sở.
- `customerName`: tên khách hàng.

**Yêu cầu:**

1. Dùng `LocalDate` cho ngày, `LocalTime` cho giờ và `ZoneId` cho cơ sở.
2. Dùng HTML `date` và `time` control với chuỗi ISO.
3. Cấu hình `ConversionService` để Web Flow và Spring MVC dùng chung formatter.
4. Thêm validator kiểm tra ngày không ở quá khứ và giờ nằm trong khung hoạt động.
5. Trong service xác nhận, kết hợp ngày/giờ với timezone và kiểm tra DST gap/overlap.
6. Ghi một `Instant` cho lịch đã xác nhận và giữ `zoneId` để hiển thị theo cơ sở.
7. Kiểm thử ngày nhuận, format sai, timezone không hợp lệ, DST gap/overlap và server chạy UTC.

**Câu hỏi tự kiểm tra:**

- Vì sao `LocalDateTime` không đủ để xác định một thời điểm tuyệt đối?
- Vì sao `datetime-local` không tự cung cấp timezone?
- Khi nào nên dùng `Instant` thay vì `LocalDateTime`?
- Tại sao formatter đã đăng ký cho Spring MVC vẫn có thể chưa được Web Flow sử dụng?
- Vì sao kiểm tra format không thay thế kiểm tra slot trong transaction?

## 19. Ghi nhớ

- Chọn kiểu dữ liệu theo **ý nghĩa nghiệp vụ**: `LocalDate` cho ngày lịch, `LocalTime` cho giờ trong ngày, `LocalDateTime` cho giờ địa phương chưa gắn zone, `Instant` cho thời điểm tuyệt đối, `OffsetDateTime` cho offset và `ZonedDateTime` cho vùng giờ có quy tắc.
- Locale, pattern và timezone là ba khái niệm riêng.
- HTML `date`, `time`, `datetime-local` gửi chuỗi chuẩn; `datetime-local` không chứa timezone.
- Spring Web Flow dùng Spring type conversion/formatting cho data binding; hãy cấu hình rõ `ConversionService` của Web Flow thay vì mặc định nó trùng với MVC.
- Dùng `@DateTimeFormat` hoặc `Formatter` cho chuỗi ngày giờ; dùng `Converter` cho chuyển đổi object-to-object.
- ISO hoặc pattern cố định giúp ổn định dữ liệu qua nhiều locale và JDK.
- `LocalDateTime` cộng `ZoneId` có thể gặp DST gap/overlap; hãy xác định chính sách trước khi tạo `Instant`.
- Với dữ liệu cũ, chuyển đổi theo ý nghĩa thực của cột: `java.util.Date` gần với `Instant`, `java.sql.Date` gần với `LocalDate`.
- Kiểm tra binding, validation, timezone, transaction và database mapping ở nhiều tầng; parse thành công chưa có nghĩa lịch hợp lệ.

### Tài liệu tham khảo

- [Spring Web Flow 3.0.2 Reference Guide — Performing Type Conversion](https://docs.spring.io/spring-webflow/docs/3.0.2-SNAPSHOT/reference/#performing-type-conversion): conversion service, formatter, converter và cấu hình `flow-builder-services`.
- [Spring Web Flow 3.0.2 Reference Guide — Binding to a Model](https://docs.spring.io/spring-webflow/docs/3.0.2-SNAPSHOT/reference/#binding-to-a-model): data binding và chuyển đổi request parameter vào model.
- [Spring Framework Reference — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Converter`, `Formatter`, `@DateTimeFormat` và hỗ trợ `java.time`.
- [Spring Framework Reference — Configuring a Global Date and Time Format](https://docs.spring.io/spring/reference/6.2/core/validation/format-configuring-formatting-globaldatetimeformat.html): `DateTimeFormatterRegistrar` và đăng ký formatter JSR-310.
- [Java API — `java.time.ZoneRules`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): kiểm tra offset hợp lệ và quy tắc DST.
- [Java API — `java.time.format.DateTimeFormatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern, ISO formatter và parse/print.
