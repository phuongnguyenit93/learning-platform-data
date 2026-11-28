# Ngày giờ, định dạng và múi giờ cần công bố

Khi người dùng nhập ngày hoặc thời điểm vào command, Spring Shell nhận đầu vào dưới dạng văn bản rồi chuyển nó sang kiểu Java mà phương thức command khai báo. Với dữ liệu ngày giờ, chỉ khai báo LocalDate, LocalDateTime hay ZonedDateTime là chưa đủ để tạo ra một giao diện CLI rõ ràng: ứng dụng cần công bố chuỗi đầu vào có định dạng nào, có yêu cầu offset hoặc múi giờ hay không, và kết quả được hiển thị theo múi giờ nào.

Trong module SPRING_SHELL, nội dung này liên quan trực tiếp đến chuyển đổi kiểu, validation, trợ giúp và khả năng gọi command từ script. Một quy ước ngày giờ ổn định giúp người vận hành nhập đúng dữ liệu và giúp các hệ thống tự động gọi CLI mà không phụ thuộc vào thiết lập vùng của máy đang chạy.

## 1. Chọn đúng kiểu thời gian trước khi chọn định dạng

Java cung cấp API java.time để mô hình hóa các khái niệm thời gian khác nhau. Hãy chọn kiểu theo ý nghĩa dữ liệu thay vì chọn kiểu chỉ vì nó dễ parse.

| Kiểu Java | Biểu diễn | Có offset/múi giờ? | Trường hợp sử dụng |
| --- | --- | --- | --- |
| `LocalDate` | Ngày lịch, ví dụ `2026-11-26` | Không | Ngày sinh, ngày báo cáo, ngày hiệu lực |
| `LocalTime` | Giờ trong ngày, ví dụ `09:30:00` | Không | Giờ mở cửa, giờ chạy tác vụ hằng ngày |
| `LocalDateTime` | Ngày và giờ, ví dụ `2026-11-26T09:30:00` | Không | Thời điểm trên đồng hồ địa phương khi múi giờ được quản lý riêng |
| `Instant` | Một điểm trên dòng thời gian UTC | Có ý nghĩa UTC, không giữ múi giờ vùng | Thời điểm sự kiện, timestamp lưu trữ và trao đổi |
| `OffsetDateTime` | Ngày giờ cùng độ lệch UTC, ví dụ `2026-11-26T09:30:00+07:00` | Có offset, không giữ quy tắc vùng | Giao tiếp qua giao thức hoặc dữ liệu chỉ cần offset |
| `ZonedDateTime` | Ngày giờ, offset đã xác định và mã vùng, ví dụ `2026-11-26T09:30:00+07:00[Asia/Ho_Chi_Minh]` | Có múi giờ vùng | Lịch hẹn, lịch chạy theo địa điểm và quy tắc giờ địa phương |

Một số lựa chọn thường gặp:

- Dùng `LocalDate` cho ngày không gắn với thời điểm cụ thể. Sinh nhật không cần chuyển sang UTC.
- Dùng `Instant` cho thời điểm sự kiện đã xảy ra. Khi hiển thị cho người dùng, chuyển `Instant` sang múi giờ mà giao diện công bố.
- Dùng `LocalDateTime` khi giá trị là giờ trên đồng hồ địa phương và ứng dụng nhận múi giờ riêng, ví dụ `--at 2026-11-26T09:30:00 --zone Asia/Ho_Chi_Minh`.
- Dùng `OffsetDateTime` khi chuỗi đầu vào đã có độ lệch UTC và không cần lưu mã vùng.
- Dùng `ZonedDateTime` khi cần giữ cả mã vùng như `Asia/Ho_Chi_Minh` để áp dụng quy tắc thời gian của vùng đó.

`LocalDateTime` không đại diện cho một thời điểm duy nhất trên toàn cầu. Hai người ở hai múi giờ khác nhau có thể cùng nhập `2026-11-26T09:30:00` nhưng đang nói đến hai thời điểm UTC khác nhau. Vì vậy, không nên lưu hoặc truyền một `LocalDateTime` như timestamp toàn cục khi chưa xác định múi giờ.

## 2. Công bố định dạng đầu vào cho command

CLI nên có một định dạng dễ đọc, ổn định và không phụ thuộc locale của hệ điều hành. Với các lệnh dùng trong script, ISO-8601 thường là lựa chọn phù hợp:

| Dữ liệu cần nhập | Định dạng nên công bố | Ví dụ |
| --- | --- | --- |
| Ngày | `uuuu-MM-dd` | `2026-11-26` |
| Giờ | `HH:mm:ss` | `09:30:00` |
| Ngày và giờ địa phương | `uuuu-MM-dd'T'HH:mm:ss` | `2026-11-26T09:30:00` |
| Ngày giờ có offset | ISO offset date-time | `2026-11-26T09:30:00+07:00` |
| Ngày giờ có mã vùng | ISO zoned date-time | `2026-11-26T09:30:00+07:00[Asia/Ho_Chi_Minh]` |
| Thời điểm UTC | ISO instant | `2026-11-26T02:30:00Z` |

Tránh để người dùng phải đoán giữa `03/04/2026` là ngày 3 tháng 4 hay ngày 4 tháng 3. Nếu nghiệp vụ bắt buộc dùng dạng `dd/MM/uuuu`, hãy ghi rõ trong mô tả option và dùng formatter đúng mẫu đó. Đối với CLI tự động hóa, không nên tự thay đổi định dạng theo ngôn ngữ hoặc vùng của máy.

### Dùng formatter ISO có sẵn

`DateTimeFormatter` cung cấp formatter cho những kiểu thời gian phổ biến. Các formatter ISO giúp thống nhất cách parse và in dữ liệu:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

LocalDate date = LocalDate.parse(
        "2026-11-26",
        DateTimeFormatter.ISO_LOCAL_DATE
);

LocalDateTime localDateTime = LocalDateTime.parse(
        "2026-11-26T09:30:00",
        DateTimeFormatter.ISO_LOCAL_DATE_TIME
);

OffsetDateTime offsetDateTime = OffsetDateTime.parse(
        "2026-11-26T09:30:00+07:00",
        DateTimeFormatter.ISO_OFFSET_DATE_TIME
);

ZonedDateTime zonedDateTime = ZonedDateTime.parse(
        "2026-11-26T09:30:00+07:00[Asia/Ho_Chi_Minh]",
        DateTimeFormatter.ISO_ZONED_DATE_TIME
);

Instant instant = Instant.parse(
        "2026-11-26T02:30:00Z"
);
```

Các chuỗi trên biểu diễn cùng một thời điểm ở hai dạng có offset/vùng: `09:30` tại `Asia/Ho_Chi_Minh` tương ứng `02:30Z`. `LocalDateTime` không mang offset nên không thể tự suy ra phép quy đổi đó.

## 3. Chuyển chuỗi thành kiểu ngày giờ trong Spring Shell

Spring Shell chuyển giá trị option từ chuỗi sang kiểu tham số của phương thức command. Tài liệu phần Types của Spring Shell 3.4 liệt kê các kiểu phổ biến như `String`, boolean, số, enum và mảng; tài liệu không công bố một hợp đồng định dạng ngày giờ riêng cho mọi kiểu `java.time`. Vì vậy, nếu CLI cần một cú pháp ngày giờ ổn định, hãy khai báo rõ formatter bằng converter hoặc parse chuỗi ngay trong command.

### Cách 1: đăng ký converter cho LocalDate

Spring sử dụng `Converter<S, T>` để chuyển một kiểu nguồn thành kiểu đích. Có thể tạo converter `String` sang `LocalDate`, sau đó đăng ký nó như một Spring bean:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class IsoLocalDateConverter implements Converter<String, LocalDate> {

    @Override
    public LocalDate convert(String source) {
        try {
            return LocalDate.parse(
                    source,
                    DateTimeFormatter.ISO_LOCAL_DATE
            );
        }
        catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Ngày phải theo định dạng uuuu-MM-dd, ví dụ 2026-11-26",
                    ex
            );
        }
    }
}
```

Command có thể khai báo tham số là `LocalDate`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    @Command(command = "report daily", description = "Tạo báo cáo theo ngày.")
    public String daily(
            @Option(
                longNames = "date",
                description = "Ngày theo ISO uuuu-MM-dd, ví dụ 2026-11-26"
            ) LocalDate date) {

        return "Đang tạo báo cáo ngày " +
                date.format(DateTimeFormatter.ISO_LOCAL_DATE);
    }
}
```

Khi gọi command, người dùng truyền chuỗi theo hợp đồng đã công bố:

```text
shell:> report daily --date 2026-11-26
Đang tạo báo cáo ngày 2026-11-26
```

Converter chịu trách nhiệm chuyển đổi và báo lỗi định dạng. Command nhận kiểu `LocalDate` đã được chuyển đổi, nên logic nghiệp vụ không phải tự parse chuỗi mỗi lần.

Với mô hình annotation mới trong Spring Shell 3.x, lớp command phải là Spring bean và được đưa vào quá trình phát hiện bằng `@CommandScan` hoặc `@EnableCommand`. Trong ứng dụng Spring Boot 3.x, thường đặt `@CommandScan` trên lớp ứng dụng. Spring Boot 4 tự động bật command scanning nên không cần annotation này.

Với mô hình annotation legacy của Spring Shell 3.x, phương thức có thể dùng `@ShellComponent`, `@ShellMethod` và `@ShellOption` với tham số `LocalDate`. Với mô hình annotation mới 3.x, dùng `@Command(command = ...)` và `@Option(longNames = ...)` như ví dụ. Spring Shell 4.x dùng `@Component`, `@Command(name = ...)` và `@Option(longName = ...)`; converter vẫn triển khai Spring `Converter<String, LocalDate>`. Nếu dùng custom converter với mô hình `@Command` của Spring Shell 4, cần dùng ít nhất bản 4.0.3, nơi lỗi custom converter với annotation command đã được sửa.

### Cách 2: parse chuỗi trực tiếp trong command

Nếu định dạng chỉ được dùng bởi một command, hoặc muốn thông báo lỗi gắn sát với nghiệp vụ, có thể nhận `String` rồi parse bằng `DateTimeFormatter`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

@ShellMethod(key = "report daily", value = "Tạo báo cáo theo ngày.")
public String daily(@ShellOption(value = "--date") String dateText) {
    try {
        LocalDate date = LocalDate.parse(
                dateText,
                DateTimeFormatter.ISO_LOCAL_DATE
        );
        return "Đang tạo báo cáo ngày " + date;
    }
    catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Giá trị --date phải theo định dạng uuuu-MM-dd, ví dụ 2026-11-26",
                ex
        );
    }
}
```

Ưu điểm của cách này là command kiểm soát hoàn toàn thông báo lỗi và định dạng. Đổi lại, kiểu tham số vẫn là `String`, nên command phải parse trước khi gọi service. Không nên lặp lại cùng đoạn parse ở nhiều command; khi nhiều lệnh cùng nhận một kiểu ngày giờ, converter dùng chung sẽ dễ bảo trì hơn.

## 4. Dùng định dạng tùy chỉnh và kiểm tra nghiêm ngặt

Nếu yêu cầu nghiệp vụ bắt buộc ngày theo `dd/MM/uuuu`, hãy tạo formatter riêng thay vì dựa vào locale mặc định:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

private static final DateTimeFormatter VIETNAMESE_DATE =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse("26/11/2026", VIETNAMESE_DATE);
```

`ResolverStyle.STRICT` yêu cầu ngày hợp lệ theo lịch. Ví dụ `31/02/2026` bị từ chối thay vì được tự điều chỉnh. Khi dùng mẫu tùy chỉnh, hãy ghi chính xác mẫu vào `description` của option và tài liệu sử dụng:

```text
--date 26/11/2026
```

Không nên vừa chấp nhận `yyyy-MM-dd`, vừa chấp nhận `dd/MM/yyyy`, vừa thử đoán định dạng dựa trên chuỗi. Nhiều định dạng có thể gây nhập nhằng, làm cho script khó dự đoán và khiến lỗi dữ liệu bị phát hiện muộn.

## 5. Phân biệt offset và múi giờ vùng

Offset là độ lệch cụ thể so với UTC tại một thời điểm, ví dụ `+07:00`. Múi giờ vùng là một mã như `Asia/Ho_Chi_Minh`, đi kèm quy tắc thời gian được duy trì cho địa điểm đó. Hai khái niệm không thể thay thế hoàn toàn cho nhau.

| Giá trị | Có ý nghĩa gì? | Ví dụ |
| --- | --- | --- |
| UTC offset | Độ lệch so với UTC tại thời điểm đó | `+07:00` |
| Zone ID | Mã vùng có quy tắc thời gian | `Asia/Ho_Chi_Minh` |
| `ZoneId` | Kiểu Java biểu diễn mã vùng hoặc offset | `ZoneId.of("Asia/Ho_Chi_Minh")` |
| `ZoneOffset` | Kiểu Java biểu diễn độ lệch cố định | `ZoneOffset.of("+07:00")` |

Nếu chỉ lưu `+07:00`, ứng dụng biết độ lệch tại thời điểm đó nhưng không biết quy tắc của địa điểm trong các thời điểm khác. Nếu nghiệp vụ liên quan đến lịch theo địa điểm, hãy lưu hoặc nhận Zone ID dạng vùng. Tránh dùng viết tắt như `CST`, `IST` hoặc `ICT` vì chúng có thể mang nhiều nghĩa hoặc không xác định đầy đủ quy tắc vùng.

Ví dụ tạo một `ZoneId` từ đầu vào:

```java
import java.time.ZoneId;
import java.time.DateTimeException;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
```

Nếu tên vùng không hợp lệ, `ZoneId.of` ném `DateTimeException`. CLI nên chuyển lỗi đó thành thông báo có ví dụ hợp lệ, chẳng hạn `--zone Asia/Ho_Chi_Minh`.

## 6. Khi command nhận giờ địa phương và múi giờ riêng

Một cách thiết kế rõ ràng cho lịch hẹn là nhận hai option riêng:

- `--at`: ngày giờ địa phương theo ISO local date-time.
- `--zone`: mã múi giờ vùng, ví dụ `Asia/Ho_Chi_Minh`.

Command có thể chuyển chúng thành `ZonedDateTime`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

@ShellMethod(key = "meeting schedule", value = "Lên lịch họp theo múi giờ.")
public String schedule(
        @ShellOption(value = "--at") LocalDateTime localDateTime,
        @ShellOption(value = "--zone") String zoneText) {

    ZoneId zone = ZoneId.of(zoneText);
    List<ZoneOffset> validOffsets =
            zone.getRules().getValidOffsets(localDateTime);

    if (validOffsets.isEmpty()) {
        throw new IllegalArgumentException(
                "Giờ địa phương không tồn tại trong múi giờ " + zone
        );
    }

    if (validOffsets.size() > 1) {
        throw new IllegalArgumentException(
                "Giờ địa phương bị lặp trong múi giờ " + zone
                        + "; hãy truyền thêm offset để xác định thời điểm"
        );
    }

    ZonedDateTime scheduledAt = ZonedDateTime.ofStrict(
            localDateTime,
            validOffsets.get(0),
            zone
    );

    return "Đã lên lịch tại " +
            scheduledAt.format(DateTimeFormatter.ISO_ZONED_DATE_TIME);
}
```

Lời gọi ví dụ:

```text
shell:> meeting schedule --at 2026-11-26T09:30:00 --zone Asia/Ho_Chi_Minh
Đã lên lịch tại 2026-11-26T09:30:00+07:00[Asia/Ho_Chi_Minh]
```

Việc kiểm tra `getValidOffsets` xử lý hai tình huống có thể xảy ra ở vùng có thay đổi giờ mùa hè:

- Không có offset hợp lệ: giờ địa phương rơi vào khoảng bị bỏ qua khi đồng hồ nhảy tới, ví dụ từ 01:59 lên 03:00.
- Có hai offset hợp lệ: giờ địa phương xuất hiện hai lần khi đồng hồ lùi lại.

`LocalDateTime.atZone(zone)` tự giải quyết các trường hợp này theo quy tắc của Java: thời điểm trong khoảng trống có thể được đẩy về phía sau, còn thời điểm bị lặp thường chọn offset sớm hơn. Nếu lịch nghiệp vụ cần hành vi xác định, hãy công bố chính sách và xử lý rõ ràng như ví dụ trên, hoặc yêu cầu người dùng nhập offset cùng thời điểm.

## 7. Chọn cách biểu diễn cho dữ liệu lưu trữ và output

Một quy ước thực tế là lưu thời điểm sự kiện dưới dạng `Instant`, còn lưu múi giờ vùng riêng nếu nghiệp vụ cần biết địa điểm hoặc tái hiện giờ địa phương.

Ví dụ chuyển thời điểm nhận từ người dùng sang UTC:

```java
ZonedDateTime scheduledAt = ZonedDateTime.parse(
        "2026-11-26T09:30:00+07:00[Asia/Ho_Chi_Minh]",
        DateTimeFormatter.ISO_ZONED_DATE_TIME
);

Instant storedAt = scheduledAt.toInstant();
String utcText = DateTimeFormatter.ISO_INSTANT.format(storedAt);
String localText = scheduledAt.format(DateTimeFormatter.ISO_ZONED_DATE_TIME);
```

Kết quả:

```text
UTC:   2026-11-26T02:30:00Z
Local: 2026-11-26T09:30:00+07:00[Asia/Ho_Chi_Minh]
```

Hai chuỗi thể hiện cùng một thời điểm. Chuỗi UTC phù hợp để trao đổi và lưu timestamp; chuỗi có Zone ID hữu ích khi hiển thị lịch địa phương hoặc kiểm tra cấu hình vùng.

Để hiển thị một `Instant` theo múi giờ được công bố, hãy chuyển đổi rõ ràng:

```java
ZoneId displayZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime displayed = storedAt.atZone(displayZone);

String output = displayed.format(DateTimeFormatter.ISO_ZONED_DATE_TIME);
```

Không nên dùng `ZoneId.systemDefault()` làm quy ước ngầm cho CLI. Máy chủ chạy ở container, máy của người vận hành và máy trong CI có thể đặt các múi giờ khác nhau. Nếu múi giờ mặc định là một phần của nghiệp vụ, hãy cấu hình nó thành giá trị rõ ràng và hiển thị trong trợ giúp hoặc output.

## 8. Công bố định dạng và múi giờ trong trợ giúp

Người dùng cần biết định dạng ngay tại nơi họ nhập option. Mô tả command nên trả lời được các câu hỏi:

- Ngày giờ dùng ISO-8601 hay một mẫu tùy chỉnh?
- Có bắt buộc truyền offset hoặc Zone ID không?
- Nếu thiếu múi giờ, ứng dụng dùng vùng nào?
- Output được in theo UTC hay theo múi giờ địa phương?
- Với lịch theo vùng có thay đổi giờ mùa hè, ứng dụng xử lý giờ bị lặp hoặc không tồn tại ra sao?

Ví dụ mô tả option:

```java
@Command(
    command = "meeting schedule",
    description = "Lên lịch theo thời điểm và múi giờ được chỉ định."
)
public String schedule(
        @Option(
            longNames = "at",
            description = "ISO local date-time, ví dụ 2026-11-26T09:30:00"
        ) LocalDateTime at,
        @Option(
            longNames = "zone",
            description = "Zone ID, ví dụ Asia/Ho_Chi_Minh"
        ) String zone) {
    // ...
}
```

Khi command yêu cầu một thời điểm toàn cục, mô tả nên nói rõ phải có offset hoặc zone. Ví dụ: `ISO-8601 date-time có offset, ví dụ 2026-11-26T09:30:00+07:00`. Nếu command nhận `ZonedDateTime`, có thể công bố mẫu có cả offset và Zone ID.

Đối với command dùng trong script, hãy giữ định dạng output ổn định và có thể parse lại. Tránh chỉ in `26/11/2026 09:30` mà không kèm múi giờ nếu đây là timestamp cần trao đổi giữa các hệ thống.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `26/11/2026` không parse được | Converter đang chờ ISO `uuuu-MM-dd` | Nhập đúng định dạng được công bố hoặc thay formatter theo yêu cầu |
| `31/02/2026` được chấp nhận ngoài ý muốn | Formatter không dùng chế độ strict | Dùng `ResolverStyle.STRICT` cho mẫu tùy chỉnh |
| Cùng một giờ tạo ra hai timestamp khác nhau | `LocalDateTime` được diễn giải trong hai múi giờ khác nhau | Nhận offset/Zone ID hoặc quy định múi giờ rõ ràng |
| Giờ hẹn bị thay đổi khi chuyển máy | Ứng dụng dựa vào múi giờ mặc định của hệ điều hành | Dùng `ZoneId` tường minh và công bố nó |
| Zone ID không hợp lệ | Tên vùng sai hoặc viết tắt không được hỗ trợ | Dùng mã vùng IANA như `Asia/Ho_Chi_Minh` |
| Giờ lịch rơi vào khoảng DST bị bỏ qua hoặc bị lặp | Quy tắc vùng làm một giờ địa phương không tồn tại hoặc xuất hiện hai lần | Kiểm tra `ZoneRules.getValidOffsets` và công bố chính sách xử lý |
| Spring Shell báo không chuyển đổi được kiểu | Chưa đăng ký converter, converter không được Spring phát hiện hoặc phiên bản có lỗi | Đăng ký converter bean, kiểm tra import/API và xác nhận phiên bản Spring Shell |
| Output hiển thị giờ khác với người nhập | Đã chuyển `Instant` sang múi giờ khác khi render | Ghi rõ múi giờ hiển thị và in kèm offset/Zone ID |

## 10. Checklist thiết kế command ngày giờ

- Chọn kiểu Java theo ý nghĩa: `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime` hoặc `ZonedDateTime`.
- Công bố định dạng đầu vào bằng ví dụ cụ thể trong `description` hoặc tài liệu trợ giúp.
- Dùng ISO-8601 cho CLI và script khi không có yêu cầu nghiệp vụ khác.
- Nếu dùng mẫu tùy chỉnh, chọn `Locale` cố định và `ResolverStyle.STRICT`.
- Đăng ký converter cho những kiểu ngày giờ cần dùng chung; báo lỗi có ví dụ định dạng hợp lệ.
- Không suy đoán múi giờ từ máy chạy hoặc từ viết tắt không rõ nghĩa.
- Yêu cầu offset hoặc Zone ID khi cần xác định một thời điểm toàn cục.
- Xác định chính sách khi giờ địa phương bị lặp hoặc không tồn tại do quy tắc múi giờ.
- Lưu timestamp theo UTC khi phù hợp; giữ Zone ID riêng nếu cần tái hiện lịch địa phương.
- Công bố múi giờ dùng cho output và kiểm thử cùng một command trên máy có cấu hình vùng khác nhau.

## Tài liệu tham khảo

- [Spring Shell 3.4 — Types](https://docs.spring.io/spring-shell/reference/3.4/options/types.html)
- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell Releases — Custom converters fixed in 4.0.3](https://github.com/spring-projects/spring-shell/releases)
- [Spring Framework — Type Conversion and ConversionService](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Java SE — java.time Package](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html)
- [Java SE — DateTimeFormatter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE — ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
