# Ngày giờ, múi giờ và converter JSR-310

## 1. Chuyển đổi được kiểu chưa có nghĩa là giữ đúng thời gian

Trong chương **Chuyển đổi dữ liệu** của module **SPRING_DATA_COMMONS**, ngày giờ là một ví dụ cho thấy sự khác nhau giữa đổi biểu diễn và giữ nguyên ý nghĩa nghiệp vụ.

Một ứng dụng có thể nhận `2025-01-15T09:00`, chuyển thành `java.util.Date`, lưu xuống database rồi đọc lại mà không gặp ngoại lệ. Tuy vậy, nếu máy ghi và máy đọc dùng múi giờ mặc định khác nhau, giá trị người dùng nhìn thấy có thể bị lệch nhiều giờ.

Để thiết kế đúng, cần trả lời ba câu hỏi:

1. Giá trị biểu diễn một thời điểm trên dòng thời gian, một ngày lịch hay một giờ địa phương?
2. Nếu cần múi giờ, múi giờ đó được lấy từ đâu?
3. Converter, driver và store có giữ được độ chính xác và thông tin cần thiết không?

Bài học tập trung vào `java.time`, các converter JSR-310 trong Spring Data Commons và cách áp dụng chúng khi xây repository, truy vấn, phân trang và auditing. Việc đăng ký converter vào hạ tầng persistence vẫn phụ thuộc module Spring Data và store cụ thể.

## 2. Chọn kiểu theo ý nghĩa nghiệp vụ

JSR-310 là nền tảng của API ngày giờ `java.time` trong Java. Tên “JSR-310 converter” không có nghĩa mọi kiểu trong `java.time` đều tự động được mọi store hỗ trợ.

| Kiểu | Thông tin chính | Ví dụ nghiệp vụ | Điều không nên tự suy ra |
| --- | --- | --- | --- |
| `Instant` | Một thời điểm trên dòng thời gian | Thời điểm tạo đơn, nhận sự kiện | Không chứa múi giờ hiển thị của người dùng |
| `LocalDate` | Ngày theo lịch ISO, không có giờ và múi giờ | Ngày sinh, ngày nghỉ | Không phải nửa đêm UTC |
| `LocalTime` | Giờ trong ngày, không có ngày và múi giờ | Giờ mở cửa | Chưa xác định một thời điểm cụ thể |
| `LocalDateTime` | Ngày và giờ địa phương, không có offset hoặc zone | Giờ hẹn do người dùng nhập | Chưa biết nó tương ứng với `Instant` nào |
| `OffsetDateTime` | Ngày giờ kèm độ lệch UTC | Dữ liệu trao đổi có `+07:00` | Offset không mô tả quy tắc của một vùng |
| `ZonedDateTime` | Ngày giờ kèm zone và offset đã phân giải | Lịch hẹn gắn với một vùng | Store chưa chắc giữ lại toàn bộ thông tin này |
| `ZoneId` | Định danh vùng và tập quy tắc múi giờ | `Asia/Ho_Chi_Minh` | Không phải một thời điểm |
| `Duration` | Một khoảng thời gian theo giây và nano giây | Timeout, thời lượng xử lý | Không đồng nghĩa số ngày lịch |
| `Period` | Khoảng theo năm, tháng, ngày của lịch | Chu kỳ gia hạn theo tháng | Không có độ dài cố định tính bằng giây |

Các kiểu ngày giờ cốt lõi trong `java.time` là immutable. Điều này thuận lợi khi chia sẻ giá trị giữa các luồng và viết converter không có trạng thái thay đổi.

### 2.1. Instant dành cho thời điểm, không dành cho mọi dữ liệu ngày giờ

Một sự kiện “đơn hàng được tạo” cần trả lời: nó xảy ra lúc nào trên dòng thời gian?

~~~java
import java.time.Instant;

Instant createdAt = Instant.parse("2025-01-15T02:00:00Z");
~~~

Cùng thời điểm đó có thể được hiển thị ở nhiều nơi:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime vietnamTime =
        createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime utcTime =
        createdAt.atZone(ZoneId.of("UTC"));
~~~

Việc đổi múi giờ hiển thị không tạo ra một sự kiện mới. Các giá trị trên vẫn có cùng `toInstant()`.

### 2.2. LocalDate giữ nguyên ý nghĩa ngày lịch

Ngày sinh `1995-07-12` không tự mang ý nghĩa “một thời điểm tại đầu ngày ở UTC”:

~~~java
import java.time.LocalDate;

LocalDate birthday = LocalDate.of(1995, 7, 12);
~~~

Nếu ép ngày này thành timestamp rồi hiển thị ở múi giờ khác, ngày trên màn hình có thể đổi. Với dữ liệu chỉ có ngày, nên dùng khả năng lưu ngày lịch của store hoặc một biểu diễn được quy định rõ, thay vì mặc định biến mọi thứ thành `Instant`.

### 2.3. LocalDateTime cần thêm ngữ cảnh

Hai giá trị sau chưa cung cấp cùng lượng thông tin:

~~~text
2025-01-15T09:00
2025-01-15T09:00+07:00
~~~

Dòng đầu là giờ địa phương. Dòng sau có offset, nên có thể suy ra thời điểm tương ứng.

Tên field như `appointmentTime` không thay thế được hợp đồng dữ liệu. Cần biết nó là giờ người dùng nhập ở vùng nào, có cần giữ vùng đó cho tương lai hay không và cách xử lý khi giờ địa phương nhập vào bị nhập nhằng.

## 3. ZoneId và ZoneOffset giải quyết hai vấn đề khác nhau

`ZoneOffset` là một độ lệch cố định so với UTC, chẳng hạn `+07:00`.

`ZoneId` như `Europe/Berlin` trỏ đến các quy tắc múi giờ, bao gồm thay đổi offset theo ngày và giờ, khi vùng đó có áp dụng.

~~~java
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneOffset fixedOffset = ZoneOffset.ofHours(7);
~~~

Hai đối tượng có thể cho cùng offset tại một thời điểm nhưng không phải cùng một khái niệm.

Đối với lịch hẹn tương lai hoặc lịch lặp, “09:00 tại vùng X” có thể cần giữ cả ngày giờ địa phương lẫn `ZoneId`. Chỉ lưu offset đang có tại thời điểm tạo lịch có thể làm mất ý định nghiệp vụ.

Đối với một sự kiện đã xảy ra, `Instant` thường là giá trị chính để so sánh và sắp thứ tự. Nếu cần tái hiện múi giờ gốc hoặc phục vụ nghiệp vụ, có thể lưu thêm zone hoặc offset như dữ liệu riêng.

Quy tắc của các vùng đến từ cơ sở dữ liệu múi giờ của runtime. Với lịch tương lai, việc runtime cập nhật quy tắc là một yếu tố cần đưa vào thiết kế, không phải thứ một converter đơn lẻ có thể quyết định thay ứng dụng.

## 4. java.util.Date là cầu nối, không phải múi giờ

Tên `Date` dễ gây hiểu nhầm. `java.util.Date` biểu diễn một thời điểm với độ chính xác mili giây; nó không chứa một `ZoneId` nghiệp vụ.

~~~java
import java.time.Instant;
import java.util.Date;

Instant original = Instant.parse("2025-01-15T02:00:00Z");

Date legacy = Date.from(original);
Instant restored = legacy.toInstant();
~~~

Trong ví dụ này, `restored.equals(original)` là `true` vì giá trị ban đầu không có phần nhỏ hơn mili giây.

Ngược lại, `Date.toString()` định dạng giá trị theo múi giờ mặc định của môi trường. Hai máy có thể in chuỗi khác nhau cho cùng một giá trị epoch.

Khi chẩn đoán, nên quan sát đồng thời:

~~~java
System.out.println(legacy.getTime());
System.out.println(legacy.toInstant());
System.out.println(java.time.ZoneId.systemDefault());
~~~

Ba dòng lần lượt cho biết epoch mili giây, biểu diễn thời điểm và múi giờ mặc định. Chúng giúp phân biệt thay đổi cách hiển thị với thay đổi thời điểm thực sự.

Ví dụ ở đây dùng `java.util.Date`. Không nên áp dụng mọi giả định này một cách máy móc cho các kiểu `java.sql.Date`, `java.sql.Time` hoặc `java.sql.Timestamp`; các kiểu JDBC có hợp đồng và cách tương tác với driver riêng.

## 5. Vai trò của Jsr310Converters trong Spring Data Commons

`org.springframework.data.convert.Jsr310Converters` cung cấp các converter dùng chung liên quan đến API ngày giờ Java.

Một nhóm quan trọng là cầu nối giữa `java.util.Date` và một số kiểu `java.time`. Hai trường hợp cần phân biệt:

| Cặp chuyển đổi | Có cần chọn múi giờ? | Ý nghĩa chính |
| --- | --- | --- |
| `Instant` ↔ `Date` | Không | Hai biểu diễn của thời điểm, có khác biệt độ chính xác |
| `LocalDateTime` ↔ `Date` | Có | Cần gắn hoặc tách ngữ cảnh giờ địa phương |
| `LocalDate` ↔ `Date` | Có | Phải quy ước một thời điểm đại diện cho ngày, chiều đọc lấy ngày theo zone |
| `LocalTime` ↔ `Date` | Cần thêm ngữ cảnh ngày và zone | Không thể coi là phép chuyển đổi khôi phục đầy đủ thời điểm |

Các converter Commons tiêu chuẩn nối `Date` với `LocalDateTime` hoặc `LocalDate` sử dụng múi giờ mặc định hệ thống khi cần diễn giải giờ địa phương. Điều này khác với việc ứng dụng đã có một múi giờ nghiệp vụ được cấu hình rõ ràng.

Các converter cho kiểu local không biến dữ liệu thiếu zone thành dữ liệu tự có zone. Chúng thực hiện phép chuyển đổi theo một quy ước cụ thể.

Không nên xem bảng trên là danh mục toàn bộ converter hoặc cam kết hỗ trợ kiểu cho mọi store. Bộ converter khả dụng và cách hạ tầng store chọn sử dụng chúng phải được đối chiếu với phiên bản và cấu hình thực tế của dự án.

### 5.1. Quan sát bộ chuyển đổi trong một ConversionService độc lập

Ví dụ sau chỉ minh họa cơ chế chuyển đổi trong bộ nhớ:

~~~java
import java.time.Instant;
import java.util.Date;

import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.GenericConversionService;
import org.springframework.data.convert.Jsr310Converters;

public final class Jsr310ConversionDemo {

    public static void main(String[] args) {
        GenericConversionService service =
                new GenericConversionService();

        for (Converter<?, ?> converter
                : Jsr310Converters.getConvertersToRegister()) {
            service.addConverter(converter);
        }

        Instant source =
                Instant.parse("2025-01-15T02:00:00.123456789Z");

        Date stored = service.convert(source, Date.class);
        Instant restored = service.convert(stored, Instant.class);

        System.out.println(source);
        System.out.println(restored);
    }
}
~~~

Với phép chuyển đổi qua `Date` trong ví dụ, phần nhỏ hơn mili giây không còn:

~~~text
2025-01-15T02:00:00.123456789Z
2025-01-15T02:00:00.123Z
~~~

Đây là khác biệt về độ chính xác, không phải lỗi múi giờ.

Việc tạo `GenericConversionService` và đăng ký converter như trên không tự cấu hình MongoDB, JDBC, JPA hay bất kỳ repository nào. Muốn tác động đến persistence, converter phải được hạ tầng tương ứng sử dụng.

## 6. Vì sao múi giờ mặc định có thể làm dữ liệu bị lệch?

Xét giá trị:

~~~java
import java.time.LocalDateTime;

LocalDateTime value =
        LocalDateTime.of(2025, 1, 15, 9, 0);
~~~

Khi gắn zone để tạo thời điểm, hai lựa chọn cho hai kết quả:

| Cách diễn giải | Thời điểm tương ứng |
| --- | --- |
| 09:00 tại `UTC` | `2025-01-15T09:00:00Z` |
| 09:00 tại `Asia/Ho_Chi_Minh` | `2025-01-15T02:00:00Z` |

Nếu converter lấy `ZoneId.systemDefault()`, môi trường chạy trở thành một phần ngầm của hợp đồng dữ liệu.

Một tình huống điển hình:

1. Máy A dùng múi giờ Việt Nam, ghi `LocalDateTime` 09:00 thành thời điểm 02:00Z.
2. Máy B dùng UTC, đọc thời điểm đó thành `LocalDateTime` 02:00.
3. Ứng dụng nhận được giá trị local khác với giá trị đã nhập.

Có hai mức bảo toàn khác nhau:

- **Bảo toàn thời điểm:** `Instant` trước và sau giống nhau trong giới hạn độ chính xác đã thỏa thuận.
- **Bảo toàn ý nghĩa local:** ngày giờ địa phương trước và sau vẫn mang đúng ý nghĩa trong zone nghiệp vụ.

Một round trip thành công trên cùng máy chưa chứng minh hoạt động đúng khi đổi môi trường.

Cấu hình mọi JVM chạy UTC có thể làm môi trường nhất quán hơn. Tuy nhiên, ứng dụng vẫn phải gắn đúng zone khi tiếp nhận một giờ địa phương. Nếu đầu vào nghĩa là “09:00 ở Việt Nam”, diễn giải nó thành “09:00 UTC” ngay từ đầu vẫn cho sai thời điểm.

Không nên dùng `TimeZone.setDefault(...)` trong converter để giải quyết từng yêu cầu. Đây là trạng thái toàn cục của JVM, có thể ảnh hưởng các luồng và thành phần khác.

## 7. Mất thông tin khi biến kiểu local thành thời điểm

### 7.1. LocalDate không có thời điểm duy nhất

Một cách chuyển đổi thường gặp:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

LocalDate date = LocalDate.of(2025, 1, 15);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = date.atStartOfDay(zone).toInstant();
~~~

Kết quả là `2025-01-14T17:00:00Z`.

Ngày UTC của thời điểm này là ngày 14, dù ngày nghiệp vụ ban đầu là ngày 15. Điều đó không mâu thuẫn: hai giá trị đang được nhìn trong hai ngữ cảnh khác nhau.

`atStartOfDay(zone)` lấy thời điểm bắt đầu ngày hợp lệ theo quy tắc của zone; không nên giả định mọi ngày tại mọi vùng đều bắt đầu bằng một giờ 00:00 tồn tại bình thường.

### 7.2. LocalTime thiếu cả ngày

Giờ mở cửa `08:30` không xác định được epoch. Muốn biến thành `Date` hoặc `Instant` phải bổ sung ngày và zone.

Nếu ngày được lấy ngầm từ “hôm nay”, kết quả có thể khác giữa các lần chạy. Nếu ngày được cố định tùy ý, đó là một quy ước mã hóa cần được ghi nhận và xử lý nhất quán.

Với dữ liệu chỉ có giờ, nên dùng cách lưu được thiết kế cho giờ trong ngày, hoặc biểu diễn riêng có hợp đồng rõ ràng. Không dùng một timestamp giả làm thời điểm thực tế trong truy vấn hay auditing.

### 7.3. Offset và zone có thể bị mất khi lưu thành Date

Hai giá trị `ZonedDateTime` ở hai vùng khác nhau có thể cùng `Instant`. Khi chỉ lưu phần thời điểm, thông tin vùng gốc không còn.

Đọc lại `Instant` rồi gắn một `ZoneId` tùy chọn chỉ tạo cách nhìn mới về thời điểm đó. Nó không khôi phục được zone mà người dùng đã chọn nếu zone chưa từng được lưu.

## 8. DST: một giờ địa phương có thể không tồn tại hoặc có hai cách hiểu

Khi có thay đổi giờ theo mùa, ánh xạ từ `LocalDateTime` sang `Instant` không phải lúc nào cũng một-một.

- **Khoảng trống:** đồng hồ nhảy tới trước, một số giờ địa phương không tồn tại.
- **Khoảng chồng:** đồng hồ lùi lại, cùng một giờ địa phương xảy ra hai lần.

Ví dụ lịch sử với `Europe/Berlin`:

| Giá trị local | Trạng thái |
| --- | --- |
| `2025-03-30T02:30` | Nằm trong khoảng trống |
| `2025-10-26T02:30` | Có hai offset hợp lệ |

`local.atZone(zone)` có cơ chế mặc định để phân giải các trường hợp này; nó không mặc nhiên từ chối mọi giá trị nhập nhằng hoặc không tồn tại. Vì vậy, cần chọn chính sách nghiệp vụ thay vì trông chờ một ngoại lệ luôn xuất hiện.

### 8.1. Ví dụ phân giải nghiêm ngặt

Utility dưới đây từ chối giờ không tồn tại và yêu cầu cung cấp offset khi giờ bị nhập nhằng:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Objects;

public final class StrictLocalTimeResolver {

    private StrictLocalTimeResolver() {
    }

    public static Instant resolve(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset requestedOffset) {

        Objects.requireNonNull(local, "local");
        Objects.requireNonNull(zone, "zone");

        List<ZoneOffset> validOffsets =
                zone.getRules().getValidOffsets(local);

        if (validOffsets.isEmpty()) {
            throw new DateTimeException(
                    "Local time does not exist in zone " + zone);
        }

        if (requestedOffset != null
                && !validOffsets.contains(requestedOffset)) {
            throw new DateTimeException(
                    "Offset is not valid for this local time and zone");
        }

        if (requestedOffset == null && validOffsets.size() > 1) {
            throw new DateTimeException(
                    "Local time is ambiguous; an offset is required");
        }

        ZoneOffset selectedOffset = requestedOffset != null
                ? requestedOffset
                : validOffsets.get(0);

        return ZonedDateTime.ofStrict(
                local, selectedOffset, zone).toInstant();
    }
}
~~~

Cách dùng:

~~~java
Instant selected = StrictLocalTimeResolver.resolve(
        LocalDateTime.of(2025, 10, 26, 2, 30),
        ZoneId.of("Europe/Berlin"),
        ZoneOffset.ofHours(1));
~~~

Với bộ quy tắc tương ứng, kết quả là `2025-10-26T01:30:00Z`.

Đây là một chính sách minh họa. Ứng dụng cũng có thể cho phép dịch giờ, chọn lần xuất hiện đầu hoặc yêu cầu người dùng chọn. Điều quan trọng là chính sách phải được quyết định rõ và được giữ nhất quán giữa lúc ghi, đọc và truy vấn.

## 9. Viết converter có zone tường minh

Khi store thực sự dùng `Date` làm kiểu trung gian, ứng dụng có thể cần một cặp converter theo zone nghiệp vụ.

Các ví dụ sau sử dụng `Converter` của Spring và annotation định hướng của Spring Data Commons. Mỗi public type được đặt trong một file Java riêng khi áp dụng vào dự án.

### 9.1. Chiều ghi: LocalDateTime sang Date

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;
import java.util.Objects;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class BusinessLocalDateTimeWriteConverter
        implements Converter<LocalDateTime, Date> {

    private final ZoneId zone;

    public BusinessLocalDateTimeWriteConverter(ZoneId zone) {
        this.zone = Objects.requireNonNull(zone, "zone");
    }

    @Override
    public Date convert(LocalDateTime source) {
        return Date.from(
                StrictLocalTimeResolver.resolve(source, zone, null));
    }
}
~~~

Converter này dùng chính sách nghiêm ngặt ở phần trước. Khi gặp giờ nhập nhằng, nó từ chối vì `LocalDateTime` không mang offset để chọn một trong hai thời điểm.

Nếu nghiệp vụ cần chấp nhận cả hai khả năng, nên tiếp nhận thêm offset hoặc đổi kiểu đầu vào. Không nên để converter đoán bằng múi giờ máy chủ.

### 9.2. Chiều đọc: Date sang LocalDateTime

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;
import java.util.Objects;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class BusinessLocalDateTimeReadConverter
        implements Converter<Date, LocalDateTime> {

    private final ZoneId zone;

    public BusinessLocalDateTimeReadConverter(ZoneId zone) {
        this.zone = Objects.requireNonNull(zone, "zone");
    }

    @Override
    public LocalDateTime convert(Date source) {
        return LocalDateTime.ofInstant(source.toInstant(), zone);
    }
}
~~~

Hai chiều cần dùng cùng zone và cùng hợp đồng độ chính xác:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

BusinessLocalDateTimeWriteConverter writer =
        new BusinessLocalDateTimeWriteConverter(businessZone);

BusinessLocalDateTimeReadConverter reader =
        new BusinessLocalDateTimeReadConverter(businessZone);

LocalDateTime source =
        LocalDateTime.of(2025, 1, 15, 9, 0);

Date stored = writer.convert(source);
LocalDateTime restored = reader.convert(stored);

System.out.println(stored.toInstant());
// 2025-01-15T02:00:00Z

System.out.println(restored);
// 2025-01-15T09:00
~~~

Đoạn mã mô tả việc gọi converter trực tiếp, chưa đăng ký chúng với store.

### 9.3. Những giới hạn cần giữ rõ

Cặp converter trên có các giới hạn có chủ đích:

- Không giữ nano giây nhỏ hơn một mili giây khi ghi qua `Date`.
- Không lưu `ZoneId` trong giá trị `Date`; zone nằm trong cấu hình converter.
- Chiều đọc chỉ giữ ngày giờ local, không giữ offset.
- Một thời điểm đọc vào khoảng chồng DST có thể trở thành local nhập nhằng; ghi lại local đó bằng writer nghiêm ngặt sẽ bị từ chối.
- Nếu đăng ký cho toàn bộ cặp `LocalDateTime` ↔ `Date`, ảnh hưởng có thể rộng hơn một thuộc tính.

Vì thế, cặp này phù hợp khi toàn bộ phạm vi áp dụng cùng có một hợp đồng zone và chính sách thời gian tương ứng. Nó không phải một phép chuyển đổi hai chiều không mất thông tin cho mọi giá trị.

Nếu các field có ý nghĩa khác nhau, có thể cân nhắc dùng `Instant` cho thời điểm, kiểu miền riêng cho dữ liệu nghiệp vụ, hoặc cơ chế chuyển đổi theo thuộc tính nếu store hỗ trợ.

Converter nên tập trung vào chuyển đổi giá trị, không truy vấn repository hoặc thực hiện I/O để tìm zone của từng bản ghi. Nếu zone phụ thuộc người dùng hoặc bản ghi, cần đưa ngữ cảnh đó vào mô hình và xử lý ở tầng thích hợp.

## 10. Đăng ký converter đúng với hạ tầng persistence

`@ReadingConverter` và `@WritingConverter` giúp Spring Data nhận diện hướng sử dụng converter. Chúng không tự đăng ký đối tượng với tất cả store.

Khi tích hợp, cần thực hiện theo cơ chế của module đang dùng:

1. Xác định store coi kiểu nào là kiểu lưu trữ hoặc kiểu đơn giản.
2. Tạo converter và đưa vào cấu hình custom conversions của store đó.
3. Kiểm tra converter có được mapping converter hoặc pipeline persistence thực sự sử dụng.
4. Kiểm tra cả lưu entity, đọc entity và chuyển đổi tham số truy vấn cần thiết.

Không nên suy ra thứ tự ưu tiên chỉ từ việc converter được tạo thành Spring bean. Quan hệ giữa converter mặc định, converter tùy chỉnh và codec của driver phụ thuộc hạ tầng đang dùng.

| Hạ tầng | Ranh giới cần chú ý |
| --- | --- |
| Spring Data Commons | Cung cấp abstraction và converter dùng chung; không quyết định một định dạng lưu trữ chung cho mọi store |
| Spring Data MongoDB | Mapping converter, custom conversions và codec của driver có thể tham gia những đường chuyển đổi khác nhau |
| Spring Data JDBC | Cần xét kiểu cột, driver, dialect và cơ chế chuyển đổi của module |
| Spring Data JPA | Mapping ngày giờ thường đi qua JPA provider và JDBC; Spring `Converter` không thay thế `AttributeConverter` của JPA |
| HTTP/JSON | Serializer và deserializer có cấu hình riêng; định dạng JSON không tự quyết định định dạng database |

Đặc biệt, không nên mặc định rằng các codec ngày giờ native của driver sử dụng cùng quy tắc zone với converter Commons nối `Date` và kiểu local.

Nếu chuyển từ cơ chế này sang cơ chế khác, cần kiểm tra dữ liệu đã lưu và ý nghĩa của các field trước khi đổi cấu hình. Một thay đổi converter có thể thay đổi cách đọc bản ghi cũ dù schema không đổi.

## 11. Độ chính xác là một phần của hợp đồng

`Instant` và `LocalDateTime` có thể giữ phần nano giây. Điều này không có nghĩa store cũng lưu được toàn bộ phần đó.

Ví dụ:

~~~text
Giá trị vào:         2025-01-15T02:00:00.123456789Z
Sau Date.from(...):  2025-01-15T02:00:00.123Z
~~~

Ngoài converter, kiểu cột và driver có thể cắt hoặc làm tròn phần lẻ theo quy tắc riêng.

Cần quyết định:

- Độ chính xác mà API chấp nhận.
- Độ chính xác mà persistence bảo toàn.
- Cách chuẩn hóa trước khi so sánh và truy vấn.
- Có chấp nhận mất độ chính xác trong round trip hay không.

Nếu hợp đồng lưu bằng mili giây, ví dụ sau thể hiện phép so sánh tương ứng cho giá trị `Instant`:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;

Instant source =
        Instant.parse("2025-01-15T02:00:00.123456789Z");

Instant restored = Date.from(source).toInstant();

boolean preservedAtMillis =
        restored.equals(source.truncatedTo(ChronoUnit.MILLIS));
~~~

Không nên dùng cách chuẩn hóa này để che lỗi nếu nghiệp vụ thực sự yêu cầu độ chính xác cao hơn.

Độ chính xác cũng ảnh hưởng thứ tự. Khi nhiều sự kiện có cùng timestamp sau khi lưu, phân trang cần thêm khóa phân biệt ổn định, chẳng hạn ID phù hợp với hợp đồng sắp xếp của ứng dụng.

## 12. Truy vấn theo ngày phải chuyển cả khoảng thời gian

Giả sử người dùng muốn xem các đơn trong ngày `2025-01-15` theo giờ Việt Nam, còn hệ thống lưu thời điểm bằng `Instant`.

Cần tính khoảng nửa kín:

~~~text
[startInclusive, endExclusive)
~~~

Ví dụ:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate requestedDate = LocalDate.of(2025, 1, 15);
ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        requestedDate.atStartOfDay(userZone).toInstant();

Instant endExclusive =
        requestedDate.plusDays(1).atStartOfDay(userZone).toInstant();
~~~

Hai mốc tương ứng:

~~~text
startInclusive = 2025-01-14T17:00:00Z
endExclusive   = 2025-01-15T17:00:00Z
~~~

Điều kiện truy vấn mong muốn:

~~~text
createdAt >= startInclusive
AND createdAt < endExclusive
~~~

Không nên tạo mốc cuối ngày bằng `23:59:59.999`. Cách đó gắn logic truy vấn với một độ chính xác cụ thể và dễ bỏ sót dữ liệu khi độ chính xác thay đổi.

Cũng không nên luôn tính `endExclusive` bằng `startInclusive` cộng 24 giờ. Một ngày lịch ở vùng có thay đổi offset có thể không dài đúng 24 giờ. Tính đầu ngày kế tiếp theo cùng zone thể hiện đúng câu hỏi “thuộc ngày địa phương nào”.

Đối với derived queries, cần chọn các toán tử thể hiện đúng điều kiện `>=` và `<` mà store hỗ trợ. Không mặc định một phương thức chứa `Between` có cùng hợp đồng biên với khoảng nửa kín đang cần.

Sau khi dựng được khoảng, vẫn phải xác minh pipeline của store chuyển đổi tham số theo cùng quy tắc với dữ liệu đã lưu.

## 13. Liên hệ với repository, sort, projection và auditing

### 13.1. Repository và sort

Nếu cần sắp thứ tự theo thời điểm thực tế, trường sort nên có ý nghĩa thời điểm nhất quán.

So sánh chuỗi ngày giờ không đồng nhất định dạng hoặc trộn nhiều offset có thể không cho cùng thứ tự với so sánh `Instant`.

`Pageable` và `Sort` chỉ mô tả yêu cầu. Chúng không sửa được dữ liệu đã bị diễn giải sai zone trước khi lưu.

Khi timestamp có thể trùng, cần quy định thứ tự bổ sung ổn định để việc phân trang không phụ thuộc vào thứ tự ngẫu nhiên giữa các bản ghi có cùng giá trị thời gian.

### 13.2. Projection

DTO có `LocalDateTime` trong khi entity có `Instant` cần có quy ước zone rõ ràng cho bước chuyển đổi.

Không nên cho rằng converter persistence sẽ tự áp dụng vào mọi constructor projection hoặc mọi bước ánh xạ DTO. Tùy loại projection và store, đường xử lý có thể khác.

Có thể giữ `Instant` trong DTO dữ liệu và chuyển sang zone ở biên hiển thị, hoặc xây DTO theo zone người dùng bằng một mapper được cấu hình tường minh.

### 13.3. Auditing

Các field như `createdAt` và `updatedAt` thường biểu diễn thời điểm. `Instant` là lựa chọn rõ nghĩa khi store hỗ trợ cách lưu tương ứng.

Ví dụ khai báo:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

public class AuditedRecord {

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
~~~

Annotation không tự bật toàn bộ auditing. Cần cấu hình hạ tầng auditing của store, nguồn thời gian và các callback hoặc listener liên quan.

Nguồn thời gian nên có thể kiểm soát khi kiểm thử:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2025-01-15T02:00:00Z"),
        ZoneOffset.UTC);

Instant now = fixedClock.instant();
~~~

Nếu dùng `DateTimeProvider` của Spring Data, có thể xây nguồn thời gian từ `Clock` rồi cấu hình provider đó theo cơ chế auditing của module.

Một `Clock` cố định giúp kiểm soát “bây giờ”. Nó không tự thay đổi `ZoneId.systemDefault()` bên trong một converter khác. Nguồn thời gian và cách diễn giải zone vẫn là hai quyết định riêng.

### 13.4. Query by Example

Query by Example không tự diễn giải “trong ngày của người dùng” thành một khoảng thời gian.

Probe chứa một timestamp hoặc ngày giờ cụ thể vẫn phải tuân theo matcher và khả năng query của store. Với yêu cầu khoảng ngày, cần chọn API truy vấn hỗ trợ điều kiện biên rõ ràng thay vì kỳ vọng converter suy ra ý định nghiệp vụ.

## 14. Kiểm chứng theo hợp đồng dữ liệu

Việc kiểm chứng cần bao gồm ý nghĩa, độ chính xác và đường persistence thực tế.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| `Instant` đi qua `Date` | Giữ thời điểm theo độ chính xác mili giây đã quy định |
| Ghi và đọc trên hai môi trường có zone mặc định khác nhau | Không xuất hiện thay đổi ý nghĩa ngoài hợp đồng |
| `LocalDate` như ngày sinh | Không đổi ngày khi đổi zone hiển thị |
| Giờ local trong khoảng trống DST | Được từ chối hoặc điều chỉnh đúng chính sách |
| Giờ local trong khoảng chồng DST | Chọn offset rõ ràng hoặc báo nhập nhằng |
| Ghi entity rồi đọc lại qua repository | Hạ tầng store thực sự sử dụng cấu hình mong muốn |
| Truy vấn theo ngày | Đúng zone và đúng biên `>=`, `<` |
| Hai timestamp trùng sau khi giảm độ chính xác | Thứ tự và phân trang vẫn ổn định theo hợp đồng |
| Bản ghi cũ sau khi đổi converter | Cách đọc vẫn đúng hoặc có kế hoạch chuyển đổi dữ liệu |
| JSON và database | Phân biệt lỗi định dạng hiển thị với lỗi lưu trữ |

Một kiểm tra chỉ gọi `converter.convert(...)` không chứng minh driver, mapping converter và repository đều chạy đúng.

Ngược lại, nếu kết quả chỉ khác chuỗi hiển thị nhưng epoch và `Instant` giống nhau, cần xem lại lớp trình bày trước khi sửa dữ liệu.

Các đoạn mã trong bài là ví dụ minh họa để đưa vào dự án. Chúng không phải báo cáo đã chạy kiểm thử hoặc xác nhận một cấu hình database cụ thể.

## 15. Chẩn đoán các lỗi thường gặp

| Biểu hiện | Khả năng cần xem xét | Hướng xử lý |
| --- | --- | --- |
| Lệch đúng một số giờ giữa máy local và server | Dùng zone mặc định khi chuyển kiểu local | Xác định zone nghiệp vụ và đường converter thực sự được dùng |
| Ngày sinh lùi hoặc tiến một ngày | Ngày lịch bị mã hóa thành timestamp rồi nhìn ở zone khác | Khôi phục hợp đồng ngày lịch và kiểm tra mapping của store |
| Mất phần nano giây | Đi qua `Date` hoặc kiểu lưu có độ chính xác thấp hơn | Quy định độ chính xác và kiểm tra giá trị lưu thực |
| Một số giờ hẹn bị dịch sang giờ khác | Chính sách phân giải khoảng trống DST | Kiểm tra quy tắc zone và chính sách nhận đầu vào |
| Hai lần hẹn có cùng giờ local | Khoảng chồng DST hoặc thiếu offset | Lưu đủ thông tin để phân biệt thời điểm |
| Custom converter không được gọi | Chưa đăng ký đúng store hoặc đang dùng đường codec khác | Kiểm tra cấu hình custom conversions và đường mapping |
| JSON đúng nhưng truy vấn sai | Lớp JSON và persistence dùng quy tắc khác nhau | Kiểm tra riêng chuyển đổi tham số và dữ liệu trong store |
| Bản ghi cũ đổi cách hiển thị sau triển khai | Thay zone, converter hoặc quy tắc đọc | Phân tích biểu diễn cũ trước khi sửa hoặc di trú dữ liệu |

Không nên sửa dữ liệu hàng loạt chỉ dựa trên quan sát “lệch bảy giờ”. Trước hết cần xác định dữ liệu hiện lưu một thời điểm đúng nhưng hiển thị khác, hay đã bị gắn sai zone từ lúc ghi.

Nếu ý nghĩa zone chưa từng được lưu và không còn nguồn thông tin đáng tin cậy, converter mới không thể tự khôi phục thông tin đã mất.

## 16. Tự kiểm tra kiến thức

**Vì sao LocalDateTime không thể tự xác định một Instant?**

Vì nó thiếu zone hoặc offset. Ở vùng có thay đổi giờ, ngay cả khi thêm zone vẫn cần chính sách cho giờ không tồn tại hoặc có nhiều offset hợp lệ.

**Date có lưu múi giờ của người dùng không?**

Không. `java.util.Date` giữ thời điểm ở độ chính xác mili giây. Cách in giá trị có thể sử dụng zone mặc định mà không biến zone đó thành dữ liệu nằm trong `Date`.

**Đăng ký converter vào một ConversionService có tự thay đổi repository không?**

Không. Hạ tầng persistence phải thực sự sử dụng converter đó qua cơ chế của module và store.

**Vì sao cần kiểm tra cả chiều đọc lẫn chiều ghi?**

Vì hai chiều có thể dùng zone khác nhau, mất độ chính xác hoặc làm mất thông tin offset và zone. Có hai converter không có nghĩa mọi giá trị đều khôi phục nguyên vẹn.

**Có nên lưu mọi giá trị ngày giờ bằng UTC không?**

Cần chọn theo ý nghĩa. Thời điểm có thể được biểu diễn nhất quán bằng `Instant`. Ngày sinh, giờ mở cửa và lịch hẹn theo vùng có thông tin nghiệp vụ khác, cần kiểu và cách lưu tương ứng.

**Tại sao truy vấn ngày nên dùng đầu ngày kế tiếp thay cho cộng 24 giờ?**

Vì câu hỏi dựa trên ngày lịch trong một zone. Độ dài ngày theo dòng thời gian có thể thay đổi khi offset thay đổi.

**Bài học áp dụng cho Spring Data Commons như thế nào?**

Dùng converter chung để hiểu và kiểm soát phép chuyển đổi giá trị; dùng cấu hình của store để nối phép chuyển đổi đó vào persistence. Trước khi dựa vào repository, sort, projection hay auditing, cần xác định rõ ý nghĩa thời gian, nguồn zone và độ chính xác mà toàn bộ đường đi dữ liệu bảo toàn.
