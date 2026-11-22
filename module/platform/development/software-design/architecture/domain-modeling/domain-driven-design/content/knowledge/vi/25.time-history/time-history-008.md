# Múi giờ và lịch nghiệp vụ trong phạm vi quy tắc của miền

Một thời điểm trong hệ thống có thể được lưu chính xác nhưng vẫn được diễn giải sai trong nghiệp vụ. Ví dụ, một lệnh chuyển tiền có thể được ghi nhận lúc 23:30 UTC nhưng thuộc ngày làm việc tiếp theo ở múi giờ của ngân hàng; một hợp đồng có hiệu lực từ ngày 1/4 tại địa phương; một lệnh đặt chỗ lúc 02:30 vào ngày đồng hồ chuyển sang giờ mùa hè có thể không tồn tại trong múi giờ đó.

Trong Domain-Driven Design (DDD), thời gian không chỉ là kiểu dữ liệu kỹ thuật. **Múi giờ, ngày nghiệp vụ, giờ cắt giao dịch, ngày nghỉ và lịch làm việc có thể là một phần của ngôn ngữ và chính sách miền.** Cần phân biệt thời điểm tuyệt đối, ngày/giờ địa phương và lịch mà một tổ chức dùng để quyết định ngày làm việc.

Bài học này kết hợp hiểu biết về thời gian với cách đặt trách nhiệm trong domain model. Mục tiêu là để hệ thống lưu đúng sự kiện, tính đúng hạn, xử lý đúng ngày làm việc và giải thích được vì sao một giao dịch thuộc về ngày nghiệp vụ nào.

Sau bài học, người học có thể:

- Phân biệt Instant, LocalDate, LocalTime, LocalDateTime, OffsetDateTime và ZonedDateTime.
- Chọn múi giờ theo ngữ cảnh nghiệp vụ thay vì phụ thuộc múi giờ của máy chủ.
- Hiểu daylight saving time (DST), khoảng trống và khoảng lặp của đồng hồ địa phương.
- Mô hình hóa Business Date, Business Calendar, ngày nghỉ và giờ cắt giao dịch.
- Tính ngày làm việc, ngày đáo hạn và thời điểm xử lý tiếp theo theo quy tắc miền.
- Dùng Java Time API và Clock để viết logic thời gian có thể kiểm thử.
- Lưu thời điểm, múi giờ và dữ liệu lịch sử trong database với semantics rõ ràng.
- Tránh các lỗi phổ biến khi tích hợp hệ thống chạy ở nhiều múi giờ.

## 1. Thời gian trong nghiệp vụ có nhiều nghĩa

Một ứng dụng thường có nhiều câu hỏi khác nhau liên quan đến thời gian:

- Sự kiện đã xảy ra tại thời điểm tuyệt đối nào?
- Người dùng đã chọn ngày nào trên lịch địa phương?
- Một cửa hàng mở cửa lúc mấy giờ theo múi giờ của cửa hàng?
- Hợp đồng có hiệu lực từ ngày nào?
- Giao dịch gửi sau giờ cắt được tính vào ngày làm việc nào?
- Ngày đáo hạn rơi vào cuối tuần hoặc ngày nghỉ thì xử lý ra sao?
- Một lịch lặp hằng ngày lúc 09:00 có tiếp tục là 09:00 khi DST thay đổi không?

Không thể trả lời tất cả bằng một kiểu timestamp duy nhất. Trước khi chọn kiểu dữ liệu, hãy xác định **ý nghĩa của thời gian trong câu chuyện nghiệp vụ**.

### Instant: một điểm duy nhất trên dòng thời gian

Instant biểu diễn một thời điểm tuyệt đối, độc lập với múi giờ hiển thị. Ví dụ, thời điểm một khoản thanh toán được hệ thống xác nhận hoặc một message được ghi nhận.

Một Instant có thể được hiển thị ở nhiều múi giờ khác nhau nhưng vẫn là cùng một thời điểm.

### Local Date và Local Time: ngày hoặc giờ trên lịch địa phương

LocalDate chỉ biểu diễn ngày lịch, ví dụ ngày sinh hoặc ngày hiệu lực của một chính sách. Nó không mang giờ và không xác định một Instant.

LocalTime chỉ biểu diễn giờ trên đồng hồ, ví dụ cửa hàng mở lúc 08:30. Nó không có ngày hoặc múi giờ nên không xác định được một thời điểm tuyệt đối.

### LocalDateTime: ngày và giờ địa phương chưa gắn múi giờ

LocalDateTime biểu diễn một ngày cùng giờ trên đồng hồ, ví dụ 2026-11-18 09:00. Bản thân nó không cho biết thời điểm đó xảy ra ở đâu trên thế giới. Muốn chuyển thành Instant, cần thêm ZoneId và quy tắc xử lý DST.

### ZonedDateTime: ngày giờ địa phương cùng múi giờ

ZonedDateTime chứa ngày giờ địa phương, múi giờ và offset được áp dụng tại thời điểm đó. Nó phù hợp khi cần thể hiện một thời điểm theo quy tắc múi giờ cụ thể, chẳng hạn 09:00 ở Europe/Paris.

### OffsetDateTime: ngày giờ cùng độ lệch UTC

OffsetDateTime có offset như +07:00 hoặc -05:00. Offset cho biết đồng hồ địa phương lệch UTC bao nhiêu tại thời điểm đó, nhưng không chứa bộ quy tắc lịch sử/tương lai của một vùng múi giờ. Offset +07:00 không tương đương với một ZoneId như Asia/Ho_Chi_Minh về mặt semantics.

## 2. Chọn đúng kiểu thời gian trong Java

Java Time API trong package java.time cung cấp các kiểu bất biến, an toàn hơn các API ngày giờ cũ như java.util.Date và Calendar cho phần lớn logic mới.

| Kiểu Java | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| Instant | Điểm tuyệt đối trên timeline | thời điểm thanh toán, event occurredAt |
| LocalDate | Ngày lịch không có giờ | ngày sinh, ngày hiệu lực, ngày nghỉ |
| LocalTime | Giờ đồng hồ không có ngày | giờ mở cửa, giờ cắt |
| LocalDateTime | Ngày giờ địa phương chưa có zone | lịch hẹn nhập tại địa điểm |
| OffsetDateTime | Ngày giờ với UTC offset | payload API có offset tường minh |
| ZonedDateTime | Ngày giờ theo quy tắc của ZoneId | lịch chạy tại một thành phố |
| Duration | Khoảng thời gian theo số giây/nano | timeout, thời gian xử lý |
| Period | Khoảng thời gian theo năm/tháng/ngày lịch | thời hạn hợp đồng theo tháng |
| ZoneId | Định danh vùng múi giờ | Asia/Ho_Chi_Minh, Europe/London |
| ZoneOffset | Độ lệch cố định so với UTC | +07:00 |

Không nên dùng Duration và Period thay thế nhau. Một ngày lịch có thể dài 23, 24 hoặc 25 giờ ở vùng có DST. Cộng Duration 24 giờ nghĩa là cộng đúng 24 giờ trên timeline; cộng Period một ngày nghĩa là chuyển sang ngày lịch kế tiếp.

### Ví dụ: cùng một Instant, hai cách hiển thị

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant occurredAt = Instant.parse("2026-11-18T03:00:00Z");

ZonedDateTime inHoChiMinh =
        occurredAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime inLondon =
        occurredAt.atZone(ZoneId.of("Europe/London"));

System.out.println(inHoChiMinh);
System.out.println(inLondon);
~~~

Hai giá trị ZonedDateTime biểu diễn cùng một Instant. Phần ngày và giờ địa phương có thể khác nhau. Khi lưu event, thường lưu Instant làm thời điểm chuẩn; khi hiển thị hoặc áp dụng chính sách, chuyển sang múi giờ phù hợp với nghiệp vụ.

## 3. Múi giờ là quy tắc, không chỉ là một con số offset

### ZoneOffset và ZoneId khác nhau

Offset +07:00 chỉ nói rằng thời điểm địa phương nhanh hơn UTC bảy giờ. Nó không mô tả lịch sử hoặc thay đổi theo mùa.

ZoneId như Asia/Ho_Chi_Minh, America/New_York hoặc Europe/Paris đại diện cho bộ quy tắc múi giờ được quản lý trong cơ sở dữ liệu timezone. Một vùng có thể đổi offset theo thời gian do DST hoặc thay đổi chính sách của chính phủ.

Không nên lưu một offset cố định rồi dùng nó cho mọi ngày trong tương lai nếu nghiệp vụ gắn với một địa điểm. Hãy lưu ZoneId khi cần áp dụng quy tắc của địa điểm đó.

### Múi giờ phải thuộc về ngữ cảnh nghiệp vụ

Một hệ thống có thể có nhiều múi giờ đồng thời:

- Múi giờ của cửa hàng quyết định giờ mở cửa và ngày kinh doanh.
- Múi giờ của ngân hàng quyết định ngày làm việc và giờ cắt thanh toán.
- Múi giờ của người dùng quyết định cách hiển thị lịch cá nhân.
- Múi giờ của sàn giao dịch quyết định phiên giao dịch.
- Múi giờ của một hợp đồng có thể được quy định trong điều khoản.

Không nên dùng múi giờ mặc định của máy chủ làm múi giờ nghiệp vụ. Máy chủ có thể chạy UTC trong khi các chi nhánh ở nhiều quốc gia dùng lịch khác nhau.

### Ví dụ: ngày sinh và thời điểm đăng ký

Ngày sinh thường là LocalDate. Nếu lưu ngày sinh dưới dạng Instant ở UTC rồi chuyển qua múi giờ khác, ngày có thể bị lệch một ngày.

Thời điểm khách đăng ký là một sự kiện xảy ra tại một thời điểm, nên dùng Instant. Nếu cần biết khách đã nhìn thấy giờ địa phương nào khi đăng ký, có thể lưu thêm ZoneId hoặc metadata phù hợp, nhưng không nên thay Instant bằng chuỗi giờ địa phương.

## 4. DST: khoảng trống và khoảng lặp của giờ địa phương

Một số vùng thay đổi đồng hồ theo mùa. Khi đồng hồ tiến lên, một số giờ địa phương không tồn tại; khi đồng hồ lùi lại, một số giờ xuất hiện hai lần.

### Gap: giờ địa phương không tồn tại

Giả sử một vùng chuyển từ 01:59:59 sang 03:00:00. LocalDateTime 02:30 trong ngày đó không tương ứng với Instant nào trong vùng đó.

### Overlap: giờ địa phương xuất hiện hai lần

Khi đồng hồ lùi từ 03:00 về 02:00, giờ 02:30 có thể xảy ra hai lần, mỗi lần với offset khác nhau. LocalDateTime đơn lẻ không xác định được lần nào được chọn.

~~~mermaid
flowchart TD
    A[Nhận LocalDateTime + ZoneId] --> B{Giờ địa phương có hợp lệ?}
    B -->|Một offset| C[Chuyển thành một Instant]
    B -->|Không có offset: DST gap| D[Áp dụng chính sách gap]
    B -->|Hai offset: overlap| E[Chọn offset sớm/muộn theo chính sách]
    D --> F[Instant đã được xác định]
    E --> F
~~~

### Java có thể kiểm tra gap và overlap

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);

ZoneRules rules = zone.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    // Gap: giờ địa phương không tồn tại.
    throw new IllegalArgumentException("Local time falls in a DST gap");
}

if (offsets.size() == 1) {
    // Giờ hợp lệ, chỉ có một offset.
    var resolved = local.atOffset(offsets.get(0)).toInstant();
} else {
    // Overlap: có hai offset hợp lệ, cần chính sách rõ ràng.
    ZoneOffset chosen = offsets.get(0);
    var resolved = local.atOffset(chosen).toInstant();
}
~~~

Chọn offsets.get(0) trong ví dụ chỉ minh họa thao tác kỹ thuật. Quy tắc thực tế phải được quyết định theo nghiệp vụ: chọn lần đầu, lần thứ hai, yêu cầu người dùng chọn, hoặc từ chối giờ không rõ ràng.

### Không để thư viện tự quyết định thay nghiệp vụ

ZonedDateTime có các phương thức xử lý gap/overlap mặc định. Chúng tiện cho nhiều trường hợp, nhưng nếu thời điểm liên quan đến giao dịch tài chính, lịch bay hoặc phiên thị trường, cần quy định chính sách cụ thể và kiểm thử cho ngày DST.

Ví dụ:

- Lịch họp định kỳ 09:00 tại New York thường cần giữ 09:00 địa phương quanh năm, dù Instant tương ứng thay đổi.
- Một tác vụ chạy sau 24 giờ kể từ thời điểm trước thường cần cộng Duration 24 giờ.
- Hạn nộp hồ sơ đến hết ngày 31/3 tại một địa điểm thường là deadline theo LocalDate và múi giờ của địa điểm, không phải cộng 24 giờ từ một Instant bất kỳ.

## 5. Lịch nghiệp vụ (Business Calendar) là một khái niệm miền

Lịch Gregorian cho biết ngày, tháng và năm. Nhưng nhiều tổ chức có lịch làm việc riêng:

- Ngày làm việc ngân hàng.
- Lịch nghỉ lễ quốc gia hoặc địa phương.
- Lịch giao dịch chứng khoán.
- Lịch vận hành của trung tâm hỗ trợ.
- Lịch làm việc theo ca của nhà máy.
- Lịch xử lý thanh toán của nhà cung cấp.

Business Calendar xác định ngày nào được xem là ngày làm việc, ngày nghỉ, ngày đặc biệt và cách xử lý khi một deadline rơi vào ngày không làm việc.

Một Business Calendar có thể bao gồm:

- ZoneId áp dụng cho lịch.
- Các ngày trong tuần làm việc.
- Danh sách ngày nghỉ cố định.
- Ngày nghỉ thay thế hoặc ngày nghỉ phát sinh theo từng năm.
- Ngày làm việc đặc biệt hoặc ngày đóng cửa sớm.
- Giờ bắt đầu/kết thúc và giờ cắt giao dịch.
- Quy tắc điều chỉnh ngày đáo hạn.
- Phiên bản hoặc thời kỳ hiệu lực của lịch.

### Calendar khác với danh sách ngày nghỉ

Chỉ lưu bảng holiday không đủ để biểu diễn lịch nghiệp vụ. Một ngày có thể không phải ngày nghỉ chính thức nhưng chi nhánh đóng cửa vì bảo trì; một ngày thứ Bảy có thể là ngày làm việc trong một ngành; một phiên giao dịch có thể đóng cửa sớm trước ngày lễ.

Calendar cần mô tả chính sách vận hành, không chỉ là tập ngày bị loại.

### Calendar có thể là một Domain Service hoặc Aggregate riêng

Nếu lịch có nhiều quy tắc, phiên bản, quyền phê duyệt và vòng đời riêng, có thể mô hình hóa BusinessCalendar như một aggregate hoặc một domain service dựa trên dữ liệu lịch được quản lý. Nếu chỉ là một tập ngày nghỉ cấu hình đơn giản, có thể dùng một value object hoặc policy.

Không nên nhúng danh sách ngày nghỉ của mọi quốc gia vào entity Order. Order có thể tham chiếu CalendarId hoặc nhận kết quả tính ngày làm việc từ domain service phù hợp.

## 6. Business Date: ngày nghiệp vụ có thể khác ngày lịch của máy chủ

Một ngày nghiệp vụ là ngày mà tổ chức dùng để phân loại và xử lý giao dịch. Nó thường được xác định từ Instant kết hợp với múi giờ và giờ cắt.

Ví dụ, ngân hàng có giờ cắt giao dịch lúc 17:00 theo múi giờ địa phương:

- Giao dịch đến lúc 16:59 được tính vào business date hôm nay.
- Giao dịch đến lúc 17:05 được tính vào business date ngày làm việc tiếp theo.
- Nếu ngày tiếp theo là cuối tuần/ngày nghỉ, có thể chuyển sang ngày làm việc kế tiếp.

Business Date không nhất thiết bằng LocalDate của thời điểm hiện tại. Nó là kết quả của chính sách miền.

### Mô hình hóa giờ cắt

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public record BusinessDayPolicy(
        ZoneId zone,
        LocalTime cutOff
) {
    public LocalDate businessDateAt(Instant instant) {
        ZonedDateTime local = instant.atZone(zone);
        LocalDate date = local.toLocalDate();

        if (!local.toLocalTime().isBefore(cutOff)) {
            return date.plusDays(1);
        }
        return date;
    }
}
~~~

Đây là ví dụ đơn giản chưa điều chỉnh cuối tuần hoặc ngày nghỉ. Trong hệ thống thực tế, kết quả cần được đưa qua BusinessCalendar để tìm ngày làm việc phù hợp. Chính sách cũng cần làm rõ giao dịch đúng tại thời điểm cut-off được tính vào ngày nào; ví dụ trên dùng quy tắc thời điểm bằng hoặc sau cut-off thuộc ngày tiếp theo.

### Không nên dùng một business date cho mọi context

Order Context có thể dùng ngày đặt đơn theo múi giờ của cửa hàng. Payment Context có thể dùng ngày hạch toán theo lịch ngân hàng. Reporting Context có thể dùng ngày chốt báo cáo. Cùng một Instant có thể được phân loại thành những Business Date khác nhau theo chính sách của từng context.

## 7. Tính ngày làm việc và ngày đáo hạn

### Ngày lịch và ngày làm việc khác nhau

Cộng 5 ngày lịch và cộng 5 ngày làm việc cho kết quả khác nhau nếu khoảng thời gian có cuối tuần hoặc ngày nghỉ.

Ví dụ, nếu một yêu cầu được tiếp nhận vào thứ Năm và SLA là 2 ngày làm việc, ngày hoàn thành có thể là thứ Hai nếu thứ Bảy, Chủ nhật không làm việc. Nếu có ngày nghỉ thứ Sáu, kết quả có thể muộn hơn nữa.

### BusinessCalendar với ngày làm việc

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.Set;

public final class BusinessCalendar {
    private final Set<LocalDate> holidays;

    public BusinessCalendar(Set<LocalDate> holidays) {
        this.holidays = Set.copyOf(holidays);
    }

    public boolean isBusinessDay(LocalDate date) {
        DayOfWeek day = date.getDayOfWeek();
        boolean weekend = day == DayOfWeek.SATURDAY
                || day == DayOfWeek.SUNDAY;

        return !weekend && !holidays.contains(date);
    }

    public LocalDate nextBusinessDay(LocalDate date) {
        LocalDate candidate = date;
        do {
            candidate = candidate.plusDays(1);
        } while (!isBusinessDay(candidate));
        return candidate;
    }

    public LocalDate addBusinessDays(LocalDate start, int days) {
        if (days < 0) {
            throw new IllegalArgumentException("days must be non-negative");
        }

        LocalDate result = start;
        for (int i = 0; i < days; i++) {
            result = nextBusinessDay(result);
        }
        return result;
    }
}
~~~

Ví dụ này giả định tuần làm việc từ thứ Hai đến thứ Sáu và ngày nghỉ đã được nạp sẵn. Nó chưa xử lý lịch làm việc theo ca, ngày đóng cửa sớm hoặc nhiều khu vực. Quy tắc tính ngày bắt đầu có được tính là ngày thứ nhất hay không cũng cần được xác định rõ trong hợp đồng nghiệp vụ.

### Điều chỉnh ngày đáo hạn

Một khoản thanh toán có ngày đến hạn rơi vào cuối tuần có thể được xử lý theo một trong các convention:

- **Following**: chuyển sang ngày làm việc tiếp theo.
- **Modified Following**: chuyển sang ngày làm việc tiếp theo, nhưng nếu vượt sang tháng mới thì lùi về ngày làm việc trước đó.
- **Preceding**: chuyển về ngày làm việc trước đó.
- **Unadjusted**: giữ nguyên ngày lịch, dù là ngày nghỉ.

Các convention này thường gặp trong tài chính và hợp đồng. Chọn convention nào là quyết định nghiệp vụ/pháp lý, không nên hard-code theo sở thích của lập trình viên.

~~~java
public enum BusinessDayConvention {
    FOLLOWING,
    MODIFIED_FOLLOWING,
    PRECEDING,
    UNADJUSTED
}
~~~

Một service tính ngày điều chỉnh cần nhận BusinessCalendar và convention rõ ràng. Khi điều chỉnh ngày, cần giữ lại cả ngày gốc và ngày đã điều chỉnh nếu cần giải thích quyết định.

## 8. Giờ cắt, phiên làm việc và khoảng thời gian mở cửa

Một số nghiệp vụ không chỉ cần biết ngày làm việc mà còn cần biết thời gian trong ngày:

- Cửa hàng nhận đơn đến 21:00.
- Ngân hàng nhận lệnh chuyển tiền đến 17:00.
- Sàn giao dịch có phiên sáng, phiên chiều và thời gian nghỉ.
- Trung tâm hỗ trợ tiếp nhận yêu cầu từ 08:00 đến 18:00.
- Hệ thống xử lý batch bắt đầu sau khi đóng sổ.

Mô hình lịch có thể cần:

- LocalTime bắt đầu và kết thúc.
- ZoneId.
- Các khoảng nghỉ trong ngày.
- Quy tắc qua nửa đêm.
- Ngoại lệ cho ngày đặc biệt.
- Giờ cắt theo loại giao dịch.

Ví dụ cửa hàng mở từ 22:00 đến 02:00 hôm sau. Khoảng giờ này đi qua ranh giới ngày lịch. Một biểu diễn chỉ có startTime và endTime nhưng không quy định endTime nhỏ hơn startTime có nghĩa gì sẽ dễ gây lỗi.

Hãy mô hình hóa OpeningInterval hoặc TradingSession có semantics rõ ràng. Khi kiểm tra một Instant có nằm trong giờ mở cửa hay không, chuyển Instant sang ZoneId của địa điểm trước rồi áp dụng lịch địa phương.

## 9. Java Time API: dùng Clock thay cho gọi giờ hệ thống trực tiếp

Nếu domain logic gọi trực tiếp Instant.now() hoặc LocalDate.now(), test có thể phụ thuộc vào đồng hồ thật và thời điểm chạy. Thay vào đó, application layer nên cung cấp Clock hoặc giá trị thời gian cho use case.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public final class SubscriptionService {
    private final Clock clock;
    private final ZoneId businessZone;

    public SubscriptionService(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public Instant registeredAt() {
        return clock.instant();
    }

    public LocalDate registrationBusinessDate() {
        return LocalDate.now(clock.withZone(businessZone));
    }
}
~~~

Trong production, có thể cấu hình Clock.systemUTC() và ZoneId nghiệp vụ riêng. Trong test, dùng Clock.fixed():

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-18T03:00:00Z"),
        ZoneId.of("UTC")
);

SubscriptionService service =
        new SubscriptionService(fixed, ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Test sẽ luôn thấy cùng một Instant và Business Date, không phụ thuộc ngày chạy test.

### Truyền thời điểm vào hành vi miền

Với một hành vi cần thời điểm, có thể truyền Instant vào:

~~~java
public void activate(Instant activatedAt) {
    if (status != SubscriptionStatus.PENDING) {
        throw new IllegalStateException("Subscription cannot be activated");
    }

    this.status = SubscriptionStatus.ACTIVE;
    this.activatedAt = Objects.requireNonNull(activatedAt);
}
~~~

Application Service lấy thời gian từ Clock rồi gọi aggregate. Aggregate không cần phụ thuộc vào đồng hồ toàn cục. Điều này giúp logic có thể kiểm thử và làm rõ thời điểm nào được dùng làm căn cứ nghiệp vụ.

## 10. Lịch lặp và tác vụ định kỳ

Một lịch chạy “mỗi ngày lúc 09:00 tại Tokyo” không nên được lưu đơn giản thành một Instant rồi cộng 24 giờ. Khi DST thay đổi ở một số vùng, cộng 24 giờ có thể làm giờ địa phương dịch sang 08:00 hoặc 10:00.

Đối với lịch lặp theo giờ địa phương, lưu:

- LocalTime mong muốn.
- ZoneId.
- Quy tắc lặp (mỗi ngày, ngày làm việc, thứ trong tuần).
- Chính sách xử lý gap/overlap.
- Ngày bắt đầu và ngày kết thúc hiệu lực.
- Calendar ID nếu chỉ chạy vào ngày làm việc.

Ví dụ cấu hình:

~~~json
{
  "scheduleId": "daily-report",
  "localTime": "09:00",
  "zoneId": "Asia/Tokyo",
  "frequency": "BUSINESS_DAILY",
  "calendarId": "TOKYO_OFFICE",
  "gapPolicy": "NEXT_VALID_TIME",
  "overlapPolicy": "EARLIER_OFFSET"
}
~~~

Một scheduler có thể tính Instant kế tiếp từ cấu hình này. Sau khi tính, nên lưu thời điểm dự kiến chạy và khóa/idempotency key để tránh chạy hai lần khi nhiều worker cùng xử lý.

Với tác vụ “sau đúng 24 giờ”, semantics khác: dùng Instant hiện tại cộng Duration.ofHours(24). Đừng nhầm lịch theo giờ địa phương với khoảng thời gian trôi qua.

## 11. Ngày nghỉ và lịch có phiên bản

Lịch nghỉ có thể thay đổi theo quyết định của chính phủ, tổ chức hoặc đơn vị vận hành. Một ngày nghỉ có thể được công bố muộn, thay thế ngày làm việc khác hoặc áp dụng riêng cho một khu vực.

Nếu lịch được cập nhật, cần biết giao dịch cũ đã dùng phiên bản lịch nào để tính ngày đáo hạn. Nếu chỉ tính lại từ danh sách ngày nghỉ hiện tại, kết quả lịch sử có thể thay đổi mà không có dấu vết.

Có thể lưu:

- CalendarId.
- CalendarVersion hoặc effective period.
- Ngày nghiệp vụ đã tính.
- Convention đã áp dụng.
- Ngày gốc và ngày điều chỉnh.
- Thời điểm tính và nguồn quy tắc.

Ví dụ một payment due date được tính theo lịch ngân hàng phiên bản 2026. Khi lịch 2027 được cập nhật, các giao dịch đã chốt không nên tự động đổi ngày đáo hạn nếu hợp đồng không quy định tính lại.

Lịch có thể được quản lý bởi một context chuyên trách. Consumer nhận bản sao phiên bản lịch hoặc gọi dịch vụ tính ngày. Dù cách nào, cần quy định ai là owner và cách thông báo khi lịch thay đổi.

## 12. Lưu thời gian trong database

### Phân biệt timestamp có và không có múi giờ

Trong SQL, các hệ quản trị có semantics khác nhau cho kiểu timestamp. Với PostgreSQL:

- TIMESTAMP WITHOUT TIME ZONE lưu ngày giờ địa phương, không mang zone hoặc offset.
- TIMESTAMP WITH TIME ZONE (timestamptz) biểu diễn một Instant; PostgreSQL chuẩn hóa thời điểm và hiển thị theo timezone của session khi đọc.

Tên timestamptz không có nghĩa PostgreSQL lưu nguyên ZoneId như Europe/Paris. Nếu cần biết vùng múi giờ nghiệp vụ đã dùng, phải lưu ZoneId riêng.

Ví dụ:

~~~sql
CREATE TABLE payment (
    payment_id UUID PRIMARY KEY,
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL,
    business_date DATE NOT NULL,
    business_zone_id VARCHAR(64) NOT NULL,
    calendar_id VARCHAR(64),
    calendar_version VARCHAR(32)
);
~~~

captured_at là thời điểm tuyệt đối. business_date là ngày được tính theo quy tắc nghiệp vụ. business_zone_id và calendar_version giúp giải thích cách phân loại.

### Lưu ngày lịch dưới kiểu DATE

Ngày sinh, ngày nghỉ, ngày hiệu lực hoặc ngày đáo hạn theo lịch thường nên lưu bằng DATE. Không chuyển chúng thành midnight UTC chỉ để dùng chung một kiểu timestamp.

### Lưu LocalDateTime khi thực sự cần giờ địa phương chưa giải quyết

Một cuộc hẹn do người dùng chọn có thể cần lưu LocalDateTime và ZoneId trước khi hệ thống xác định Instant, đặc biệt khi người dùng có thể chọn thời gian rơi vào DST gap/overlap. Sau khi xác nhận, có thể lưu cả LocalDateTime, ZoneId, offset được chọn và Instant để tái hiện chính xác quyết định.

### Không lưu ZoneId bằng offset nếu cần quy tắc vùng

Lưu +07:00 không thay thế Asia/Ho_Chi_Minh. Với vùng không có DST hiện tại, chính sách tương lai vẫn có thể thay đổi. Nếu nghiệp vụ gắn với địa điểm, lưu ZoneId.

## 13. Truy vấn theo ngày địa phương nên dùng khoảng nửa mở

Một lỗi thường gặp là truy vấn sự kiện trong một ngày bằng điều kiện timestamp bằng đúng 23:59:59.999. Cách đó phụ thuộc độ chính xác timestamp và có thể bỏ sót dữ liệu ở phần nhỏ hơn của giây.

Thay vào đó, chuyển ngày địa phương thành khoảng Instant nửa mở:

**[startInclusive, endExclusive)**

~~~java
LocalDate businessDate = LocalDate.of(2026, 11, 18);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive = businessDate.atStartOfDay(zone).toInstant();
Instant endExclusive = businessDate.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
~~~

SQL:

~~~sql
SELECT *
FROM payment
WHERE captured_at >= :start_inclusive
  AND captured_at < :end_exclusive;
~~~

Khoảng nửa mở bao gồm toàn bộ thời điểm của ngày và tránh trùng lặp giữa hai ngày liên tiếp. Dùng atStartOfDay(zone) để lấy đầu ngày theo quy tắc zone; không tự cộng 24 giờ vì ngày địa phương có thể không dài đúng 24 giờ ở vùng DST.

Nếu ngày nghiệp vụ dùng giờ cắt 17:00 thay vì nửa đêm, hãy tính biên theo BusinessDayPolicy thay vì dùng atStartOfDay.

## 14. Lịch và múi giờ trong kiến trúc DDD

### Value Object cho Zone và thời điểm

Có thể tạo các kiểu miền như BusinessZone, BusinessDate, CutOffTime hoặc CalendarId để biểu đạt ngữ nghĩa rõ hơn kiểu Java thuần.

Ví dụ:

~~~java
public record BusinessZone(ZoneId value) {
    public BusinessZone {
        Objects.requireNonNull(value, "value");
    }
}

public record BusinessDate(LocalDate value) {
    public BusinessDate {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Các wrapper này hữu ích khi chúng mang validation hoặc semantics riêng. Không cần tạo một class mới cho mọi kiểu Java nếu nó không thêm ý nghĩa.

### BusinessCalendar như một chính sách miền

BusinessCalendar có thể là một domain service khi việc xác định ngày làm việc cần kết hợp:

- ZoneId.
- Weekend pattern.
- Holiday set.
- Exceptional working days.
- Business-day convention.
- Calendar version.

Nếu calendar được quản lý, phê duyệt và phát hành theo phiên bản, có thể cần aggregate riêng. Nếu chỉ là dữ liệu tham chiếu được cập nhật từ một nguồn bên ngoài, context sở hữu calendar có thể công bố Published Language hoặc integration event cho consumer.

### Không đưa lịch toàn cầu vào một aggregate

Một Order ở Việt Nam, một giao dịch ngân hàng tại London và một lịch giao dịch ở New York có thể dùng các calendar khác nhau. Không nên để Order aggregate chứa danh sách ngày nghỉ toàn cầu. Hãy lưu CalendarId hoặc kết quả quyết định đã được tính nếu nghiệp vụ cần giữ snapshot.

### Domain Event cần ghi rõ thời gian có ý nghĩa

Một event có thể chứa:

~~~java
public record PaymentCaptured(
        UUID paymentId,
        Instant occurredAt,
        LocalDate businessDate,
        ZoneId businessZone,
        String calendarVersion
) implements DomainEvent {
}
~~~

Không phải event nào cũng cần cả bốn field. Nhưng với giao dịch có ngày hạch toán, ngày kinh doanh hoặc deadline, ghi lại Business Date và quy tắc đã áp dụng có thể giúp giải thích về sau.

## 15. Ví dụ end-to-end: tính ngày xử lý thanh toán

Giả sử Payment Context nhận một lệnh chuyển tiền. Ngân hàng xử lý từ thứ Hai đến thứ Sáu, giờ cắt 17:00 theo múi giờ Asia/Ho_Chi_Minh. Nếu lệnh đến sau cut-off hoặc vào ngày nghỉ, nó được tính vào ngày làm việc kế tiếp.

### Chính sách nghiệp vụ

1. Chuyển Instant nhận lệnh sang LocalDateTime theo ZoneId của ngân hàng.
2. Nếu giờ địa phương trước cut-off và ngày đó là ngày làm việc, dùng ngày đó.
3. Nếu sau hoặc đúng cut-off, chuyển sang ngày lịch tiếp theo.
4. Tìm ngày làm việc kế tiếp theo BusinessCalendar.
5. Lưu receivedAt, businessDate, zoneId, calendarId và calendarVersion cùng quyết định.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class PaymentBusinessDatePolicy {
    private final ZoneId zone;
    private final LocalTime cutOff;
    private final BusinessCalendar calendar;

    public PaymentBusinessDatePolicy(
            ZoneId zone,
            LocalTime cutOff,
            BusinessCalendar calendar
    ) {
        this.zone = zone;
        this.cutOff = cutOff;
        this.calendar = calendar;
    }

    public LocalDate determineBusinessDate(Instant receivedAt) {
        ZonedDateTime local = receivedAt.atZone(zone);
        LocalDate candidate = local.toLocalDate();

        if (!local.toLocalTime().isBefore(cutOff)) {
            candidate = candidate.plusDays(1);
        }

        while (!calendar.isBusinessDay(candidate)) {
            candidate = candidate.plusDays(1);
        }

        return candidate;
    }
}
~~~

Ví dụ dùng convention cut-off inclusive: đúng 17:00 được chuyển sang ngày tiếp theo. Nếu ngân hàng quy định đúng 17:00 vẫn thuộc ngày hiện tại, điều kiện cần thay đổi thành isAfter(cutOff). Đây là chi tiết phải được xác nhận với nghiệp vụ.

### Lưu kết quả, không chỉ lưu đầu vào

Nếu chỉ lưu receivedAt rồi mỗi lần hiển thị lại tính businessDate bằng calendar mới nhất, một thay đổi lịch nghỉ có thể làm kết quả lịch sử khác đi. Khi businessDate là kết quả đã được chấp thuận trong một giao dịch, nên lưu nó cùng thông tin quy tắc/version đã áp dụng.

Nếu chính sách cho phép tính lại, cần phát một sự kiện điều chỉnh hoặc lưu quyết định mới có liên kết tới quyết định cũ. Không âm thầm ghi đè kết quả lịch sử.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Dùng LocalDateTime để lưu một sự kiện toàn cầu | Không xác định được Instant | Dùng Instant hoặc OffsetDateTime khi có offset |
| Dùng múi giờ máy chủ làm múi giờ nghiệp vụ | Kết quả khác nhau khi deploy ở vùng khác | Chỉ định ZoneId theo context/địa điểm |
| Lưu offset cố định thay cho ZoneId | Không áp dụng được quy tắc DST hoặc thay đổi timezone | Lưu ZoneId khi nghiệp vụ gắn với vùng |
| Dùng Instant cho ngày sinh/ngày nghỉ | Có thể lệch ngày khi hiển thị ở zone khác | Dùng LocalDate |
| Cộng 24 giờ để sang ngày kế tiếp | Sai quanh DST | Dùng LocalDate/Period và ZoneId |
| Cộng Period một ngày cho timeout 24 giờ | Khoảng thời gian thực có thể khác 24 giờ | Dùng Duration cho thời gian trôi qua |
| Bỏ qua DST gap/overlap | Lịch chạy sai hoặc giờ bị mơ hồ | Quy định chính sách gap/overlap |
| Dùng ngày nghỉ hiện tại để tính lại giao dịch cũ | Kết quả lịch sử thay đổi ngoài ý muốn | Lưu Business Date và Calendar Version |
| Coi thứ Bảy/Chủ nhật luôn là ngày nghỉ | Sai với lịch ngành/địa phương đặc thù | Để BusinessCalendar quyết định |
| Dùng updated_at làm thời điểm nghiệp vụ | Không phản ánh effective date hoặc occurred time | Lưu từng semantics thời gian riêng |
| Truy vấn ngày bằng 23:59:59.999 | Bỏ sót dữ liệu do precision | Dùng khoảng [start, end) |
| Gọi Instant.now() khắp domain | Test phụ thuộc đồng hồ thật, khó tái lập | Tiêm Clock hoặc truyền thời điểm |
| Lưu lịch lặp thành một Instant rồi cộng 24h | Giờ địa phương bị dịch theo mùa | Lưu LocalTime + ZoneId + recurrence policy |
| Không ghi quy tắc cut-off | Không giải thích được business date | Lưu policy/calendar version và kết quả |

## 17. Quy trình thiết kế thời gian và lịch nghiệp vụ

Khi một use case có yêu cầu thời gian, hãy thực hiện:

1. **Xác định câu hỏi:** cần biết một Instant, ngày địa phương, giờ địa phương hay ngày nghiệp vụ?
2. **Xác định owner:** context nào sở hữu múi giờ, lịch làm việc, giờ cắt hoặc chính sách deadline?
3. **Chọn kiểu dữ liệu:** Instant, LocalDate, LocalTime, LocalDateTime, ZonedDateTime hoặc kiểu miền chuyên biệt.
4. **Chọn ZoneId:** lấy từ địa điểm, tổ chức, thị trường hoặc điều khoản; không lấy ngầm từ server.
5. **Xác định DST policy:** xử lý gap/overlap thế nào nếu giờ địa phương không rõ ràng.
6. **Xác định BusinessCalendar:** tuần làm việc, ngày nghỉ, ngày đặc biệt và phiên bản lịch.
7. **Xác định convention:** cut-off inclusive/exclusive, following/preceding, tính ngày bắt đầu ra sao.
8. **Xác định snapshot:** kết quả ngày nghiệp vụ có cần giữ cùng giao dịch không?
9. **Thiết kế persistence/query:** lưu Instant và ZoneId phù hợp; truy vấn ngày bằng khoảng nửa mở.
10. **Kiểm thử biên:** DST, cuối tuần, ngày nghỉ, cut-off, năm nhuận, cuối tháng và thay đổi timezone rules.

## 18. Checklist rà soát

- [ ] Đã phân biệt thời điểm tuyệt đối với ngày/giờ địa phương.
- [ ] Dùng Instant cho event timestamp hoặc thời điểm tuyệt đối.
- [ ] Dùng LocalDate cho ngày lịch không có giờ.
- [ ] Dùng LocalTime cho giờ đồng hồ không gắn ngày.
- [ ] Dùng LocalDateTime chỉ khi semantics thực sự là local date-time.
- [ ] Dùng ZoneId cho quy tắc vùng, không chỉ lưu offset.
- [ ] Múi giờ thuộc về context/địa điểm nghiệp vụ, không phụ thuộc server.
- [ ] DST gap và overlap có chính sách rõ.
- [ ] BusinessCalendar định nghĩa ngày làm việc và ngày nghỉ.
- [ ] Cut-off và convention điều chỉnh ngày đáo hạn được xác nhận.
- [ ] Lịch có version/effective period khi kết quả lịch sử cần tái hiện.
- [ ] Dùng Clock để kiểm thử thời gian có thể tái lập.
- [ ] Phân biệt Duration với Period.
- [ ] Lưu Business Date khi nó là kết quả nghiệp vụ đã chốt.
- [ ] Query theo ngày dùng khoảng nửa mở theo ZoneId.
- [ ] Có test cho DST, ngày nghỉ, cuối tuần, cut-off và biên tháng/năm.
- [ ] Dữ liệu lịch và múi giờ được cập nhật, giám sát và có owner rõ.

## Kết luận

Thời gian trong DDD cần được mô hình hóa theo ý nghĩa mà nghiệp vụ sử dụng. Instant biểu diễn thời điểm tuyệt đối; LocalDate và LocalTime biểu diễn ngày/giờ địa phương; ZoneId cung cấp quy tắc vùng; BusinessCalendar và cut-off quyết định ngày làm việc hoặc ngày nghiệp vụ. DST, ngày nghỉ và lịch có phiên bản có thể làm thay đổi kết quả tính toán, vì vậy không nên để múi giờ máy chủ hoặc mặc định của thư viện quyết định chính sách. Khi chọn đúng kiểu thời gian, lưu lại quy tắc đã áp dụng và kiểm thử các ranh giới lịch, hệ thống có thể xử lý deadline, giao dịch và lịch vận hành nhất quán qua nhiều vùng địa lý.

