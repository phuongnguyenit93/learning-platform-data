# Mối liên hệ giữa lịch, múi giờ, độ lệch UTC và dòng thời gian trong Java

## 1. Bốn khái niệm trả lời bốn câu hỏi khác nhau

Khi nói “cuộc họp diễn ra lúc 09:00 ngày 25/10/2026”, ta mới biết **ngày và giờ được ghi trên đồng hồ**, chưa chắc đã xác định được một thời điểm duy nhất trên thế giới. Để hiểu đúng ngày giờ trong ứng dụng Java, cần phân biệt:

1. **Lịch (calendar)** trả lời: ngày đó thuộc năm, tháng, ngày nào theo một hệ lịch, và các phép cộng/trừ theo lịch được tính ra sao?
2. **Dòng thời gian (timeline)** trả lời: sự kiện đã xảy ra tại thời điểm tuyệt đối nào, trước hay sau một sự kiện khác, cách nhau bao nhiêu giây?
3. **Độ lệch UTC (UTC offset)** trả lời: đồng hồ địa phương đang nhanh hay chậm hơn UTC bao nhiêu giờ và phút tại một thời điểm? Ví dụ **+07:00**.
4. **Múi giờ theo khu vực (time zone)** trả lời: tại một địa điểm/vùng, offset nào áp dụng vào một ngày cụ thể, dựa vào lịch sử và quy tắc chuyển giờ? Ví dụ **Asia/Ho_Chi_Minh**, **America/New_York**.

Bốn yếu tố liên hệ nhưng không thay thế cho nhau. Một **Instant** có thể được hiển thị thành nhiều ngày giờ địa phương; một **LocalDateTime** chưa gắn vùng có thể tương ứng với một, hai hoặc không có Instant trong một vùng.

### Sơ đồ chuyển đổi

~~~text
                DÒNG THỜI GIAN (Instant / UTC)
                             |
                  +----------+----------+
                  |                     |
          ZoneId khu vực          ZoneOffset cố định
       (quy tắc theo thời gian)     (ví dụ +07:00)
                  |                     |
        xác định offset của          cộng offset
       Instant tại vùng đó               |
                  |                     |
                  +----------+----------+
                             |
                   ngày + giờ địa phương
                    (LocalDateTime)
                             |
             cách biểu diễn theo hệ lịch (ISO)
                             |
                 ngày / tháng / năm, giờ
~~~

Hướng đi từ **Instant + ZoneId** sang ngày giờ địa phương thường xác định được duy nhất. Hướng ngược lại từ **LocalDateTime + ZoneId** cần xét trường hợp giờ không tồn tại hoặc giờ lặp khi chuyển giờ mùa hè.

## 2. Dòng thời gian: Instant là gì?

**java.time.Instant** biểu diễn một mốc duy nhất trên dòng thời gian. Java thường hiển thị nó theo UTC, ví dụ:

~~~text
2026-10-24T10:15:30Z
~~~

Chữ **Z** là ký hiệu offset **UTC+00:00**, không có nghĩa mọi người đều nhìn thấy đồng hồ chỉ 10:15. Cùng mốc đó, đồng hồ ở TP.HCM (UTC+07:00 vào ngày này) chỉ **17:15:30**.

**Unix epoch** là mốc 1970-01-01T00:00:00Z. Các API **Instant.getEpochSecond()**, **Instant.toEpochMilli()**, **Instant.ofEpochSecond(...)** và **Instant.ofEpochMilli(...)** biểu diễn thời gian quanh mốc này. Cần luôn ghi rõ đơn vị: số giây và số millisecond chênh nhau 1.000 lần; một Instant có độ chính xác nano không nhất thiết chuyển sang millisecond mà không mất phần lẻ.

**Instant** không mang sẵn thành phố, múi giờ, ngày sinh hay giờ mở cửa. Với timestamp của đơn hàng, bản ghi audit hoặc sự kiện đến từ nhiều máy chủ, mô hình Instant giúp so sánh thời điểm thống nhất. Java sử dụng thang thời gian Java Time-Scale; trong lập trình thông thường có thể dùng Instant như mốc UTC, nhưng cần biết rằng xử lý giây nhuận không tương đương một đồng hồ vật lý có ghi giây thứ 60 trong mọi API.

### Không nhầm thời điểm với cách hiển thị

Hai chuỗi:

~~~text
2026-10-24T10:15:30Z
2026-10-24T17:15:30+07:00
~~~

biểu diễn **cùng một Instant**, dù phần giờ khác nhau. Ngược lại, **2026-10-24T10:15:30** (không Z, không offset, không ZoneId) chỉ là ngày giờ địa phương, chưa đủ thông tin để so sánh tuyệt đối với hai chuỗi trên.

## 3. Lịch: LocalDate, LocalTime và LocalDateTime

Một hệ lịch quy định cách đánh số và phân chia năm, tháng, ngày, năm nhuận; không tự quy định đồng hồ của một địa điểm đang lệch UTC bao nhiêu. Theo mặc định, các kiểu thông dụng trong **java.time** sử dụng lịch **ISO-8601**, dựa trên lịch Gregorian mở rộng (proleptic Gregorian).

| Kiểu | Chứa gì? | Không chứa gì? | Dùng khi |
| --- | --- | --- | --- |
| **LocalDate** | Năm, tháng, ngày theo lịch ISO | Giờ, múi giờ, offset | Ngày sinh, ngày hóa đơn, ngày nghỉ |
| **LocalTime** | Giờ, phút, giây, nano | Ngày, múi giờ, offset | Cửa hàng mở lúc 08:30 |
| **LocalDateTime** | Ngày và giờ địa phương | Offset, múi giờ, Instant | Lịch hẹn “09:00 ngày 25/10” khi nơi diễn ra được lưu riêng |
| **YearMonth** | Năm và tháng | Ngày, giờ, zone | Kỳ báo cáo tháng |
| **MonthDay** | Tháng và ngày | Năm, giờ, zone | Ngày kỷ niệm lặp theo lịch |

Ví dụ **LocalDate.of(2026, 2, 28).plusDays(1)** trả **2026-03-01** vì năm 2026 không nhuận. **LocalDate.of(2024, 2, 28).plusDays(1)** trả **2024-02-29** vì năm 2024 nhuận.

Một **LocalDate** tự nó không là Instant. “Ngày 24/10/2026” ở Tokyo bắt đầu trước “ngày 24/10/2026” tại New York theo dòng thời gian. Khi chuyển một ngày lịch thành khoảng thời gian, phải biết ngày đó thuộc **vùng nào**. Mốc bắt đầu ngày địa phương thường được lấy bằng **LocalDate.atStartOfDay(zone)**, không nên mặc định ghép 00:00 vào offset cố định: vài vùng từng đổi offset đúng quanh nửa đêm, khiến 00:00 không tồn tại hoặc một ngày có độ dài khác 24 giờ.

### Hệ lịch khác có thay đổi Instant không?

Java hỗ trợ thêm **Chronology**, **ChronoLocalDate**, **JapaneseDate**, **ThaiBuddhistDate**, **HijrahDate** và các kiểu liên quan khi nghiệp vụ cần hệ lịch ngoài ISO. Hệ lịch quyết định **cách gọi ngày**; nó không tự xác định múi giờ. Nhiều hệ lịch có thể đặt tên khác nhau cho cùng một ngày trong lịch sử, và cùng một Instant khi hiển thị theo các quy tắc thời gian tương ứng. Trong hệ thống trao đổi giữa dịch vụ, nên quy định rõ hệ lịch; mặc định Java Core thường dùng **LocalDate** theo ISO rồi định dạng cho người dùng khi cần.

## 4. UTC offset: độ lệch chính xác tại một thời điểm

Một **ZoneOffset** biểu thị độ lệch so với UTC:

- **Z** hoặc **+00:00**: giờ UTC.
- **+07:00**: giờ địa phương = giờ UTC + 7 giờ.
- **-04:00**: giờ địa phương = giờ UTC − 4 giờ.

Về mặt trực giác, tại một Instant đang xét:

~~~text
đồng hồ địa phương = đồng hồ UTC + UTC offset
UTC = đồng hồ địa phương − UTC offset
~~~

Đây là phép ánh xạ đồng hồ có xét đổi ngày theo lịch. Ví dụ:

~~~text
Instant UTC:        2026-10-24 22:30Z
Offset:             +07:00
Giờ địa phương:     2026-10-25 05:30 (ngày hôm sau)

Giờ địa phương:     2026-10-24 08:30
Offset:             -04:00
Instant UTC:        2026-10-24 12:30Z
~~~

**OffsetDateTime** gắn ngày giờ địa phương với một offset nên xác định được Instant, ví dụ **2026-10-24T17:15:30+07:00**. Tuy nhiên, nó **không chứa quy tắc múi giờ** để biết offset sẽ là bao nhiêu vào một tháng khác.

Nếu hai OffsetDateTime khác cách biểu diễn nhưng có cùng Instant, kiểm tra **toInstant()**, **isEqual(...)** hoặc so sánh timestamp tương ứng. **equals(...)** còn xem các thành phần ngày giờ và offset nên có thể trả false với hai giá trị cùng Instant mà khác offset.

Offset cố định phù hợp với giao thức nhận một timestamp có offset hoặc vùng vốn không cần quy tắc lịch sử; để diễn tả thời gian dân sự tại một khu vực qua nhiều năm, dùng **ZoneId khu vực**.

## 5. ZoneId: vùng có quy tắc offset theo thời gian

**ZoneId.of("Asia/Ho_Chi_Minh")** là định danh vùng IANA, còn **ZoneOffset.of("+07:00")** là độ lệch cố định. Hai kiểu đều có thể dùng để tạo ZonedDateTime, nhưng ngữ nghĩa khác nhau:

- **ZoneId khu vực** có các quy tắc thời gian (ZoneRules). Hệ thống tra offset của vùng theo Instant hoặc theo ngày giờ địa phương; quy tắc có thể đổi theo lịch sử và quyết định của cơ quan nhà nước.
- **ZoneOffset** luôn là độ lệch đó; nó không tự chứa lịch chuyển giờ mùa hè hay các thay đổi lịch sử của địa phương.
- **ZonedDateTime** chứa ngày giờ địa phương, **ZoneId** và offset được chọn theo quy tắc tại thời điểm tương ứng.
- Tên vùng thời gian viết tắt như **EST**, **CST** dễ mơ hồ giữa quốc gia và không chứa đủ quy tắc. Trong dữ liệu máy cần ưu tiên ID như **America/New_York**.

Bộ dữ liệu quy tắc IANA (tzdb) có thể được cập nhật trong các phiên bản JDK. Chính sách về giờ của một quốc gia có thể đổi, nên không được coi quy tắc tương lai là bất biến. Nếu cần tái hiện chính xác thời gian mà người dùng đã xác nhận, cân nhắc lưu **Instant đã xác nhận** lẫn **ZoneId** và thông tin lịch hẹn gốc. Với lịch lặp trong tương lai, cần chấp nhận rằng khi luật timezone đổi, những lần chạy sẽ được tính lại theo chính sách nghiệp vụ.

### Vì sao “+07:00” không phải “Asia/Ho_Chi_Minh”?

Tại một thời điểm hiện đại, Asia/Ho_Chi_Minh áp dụng +07:00. Nhưng **+07:00** không nói tên vùng, không cho biết các thay đổi từng xảy ra, và có thể là offset của nhiều khu vực khác nhau. Lưu mỗi +07:00 cho lịch hẹn tại thành phố có DST có thể khiến giờ họp bị lệch sau khi đến mùa khác.

## 6. Hai hướng chuyển đổi và tính duy nhất

### Từ Instant sang ngày giờ vùng: thường là một-một ở thời điểm đó

Khi đã có **Instant** và **ZoneId**, Java biết offset áp dụng tại Instant. Từ đó tính ngày giờ địa phương:

~~~java
Instant instant = Instant.parse("2026-10-24T10:15:30Z");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime displayed = instant.atZone(vietnam);
// 2026-10-24T17:15:30+07:00[Asia/Ho_Chi_Minh]
~~~

Đây là đoạn trích cần đặt trong phương thức và import từ java.time nếu sử dụng độc lập. Nếu lấy cùng Instant và đổi sang **America/New_York**, ngày giờ địa phương thay đổi nhưng **displayed.toInstant()** vẫn bằng Instant ban đầu.

Java sử dụng **Instant.atZone(zone)** hoặc **ZonedDateTime.ofInstant(instant, zone)**. Mọi Instant hợp lệ nằm trong khoảng thời gian mà quy tắc/tổ hợp kiểu cần có thể biểu diễn sẽ được chiếu sang một giờ địa phương duy nhất trong vùng.

### Từ ngày giờ địa phương sang Instant: có 0, 1 hoặc 2 lựa chọn

Từ **LocalDateTime** và **ZoneId**:

1. **Bình thường**: một offset hợp lệ, tương ứng một Instant.
2. **Gap (giờ bị bỏ qua)**: khi đồng hồ nhảy tiến, có những ngày giờ địa phương **không tồn tại**; không có offset hợp lệ tại thời điểm đồng hồ đó.
3. **Overlap (giờ bị lặp)**: khi đồng hồ lùi, một giờ địa phương xuất hiện **hai lần** với hai offset, nên có hai Instant khác nhau.

Các quy tắc chuyển đổi mặc định của Java tiện cho nhiều ứng dụng nhưng đôi khi chưa đúng yêu cầu nghiệp vụ:

- **LocalDateTime.atZone(zone)**: trong gap thường đẩy giờ địa phương tiến đến một giờ hợp lệ; trong overlap thường chọn offset sớm hơn theo quy tắc Java.
- **ZoneRules.getValidOffsets(localDateTime)**: trả 0, 1 hoặc 2 offset hợp lệ để ứng dụng quyết định.
- **ZoneRules.getTransition(localDateTime)**: giúp lấy thông tin chuyển offset tại gap/overlap.
- **ZonedDateTime.withEarlierOffsetAtOverlap()** và **withLaterOffsetAtOverlap()**: chọn một trong hai lần xuất hiện của giờ bị lặp.
- **ZonedDateTime.ofStrict(localDateTime, offset, zone)**: xác thực tổ hợp rõ ràng; ném DateTimeException khi không hợp lệ thay vì tự điều chỉnh.

Khi người dùng đặt lịch y tế, giao dịch tài chính hoặc hệ thống chạy tác vụ vào thời điểm chuyển giờ, nên định nghĩa chính sách gap/overlap rõ ràng và báo cho người dùng nếu giờ họ chọn mơ hồ.

## 7. DST: giờ mùa hè tạo khoảng trống và giờ lặp

Tại **America/New_York** năm 2026:

| Sự kiện | Giờ đồng hồ vùng New York | Offset trước → sau | Hệ quả |
| --- | --- | --- | --- |
| Bắt đầu DST, **08/03/2026** | Từ 01:59:59 nhảy đến 03:00 | -05:00 → -04:00 | **02:30 không tồn tại** |
| Kết thúc DST, **01/11/2026** | Từ 01:59:59 DST quay về 01:00 giờ chuẩn | -04:00 → -05:00 | **01:30 xuất hiện hai lần** |

Vào ngày 01/11/2026, cả hai biểu diễn dưới đây cùng có giờ địa phương **01:30** ở New York nhưng là hai Instant:

~~~text
2026-11-01T01:30-04:00[America/New_York]
  -> 2026-11-01T05:30:00Z

2026-11-01T01:30-05:00[America/New_York]
  -> 2026-11-01T06:30:00Z
~~~

Chúng chênh nhau **1 giờ thực** trên dòng thời gian. Vì vậy, không đủ nếu chỉ lưu **2026-11-01 01:30** rồi hy vọng hệ thống tự biết là lần nào.

Tại gap ngày 08/03/2026, **2026-03-08T02:30** không tồn tại ở New York. Nếu dùng **LocalDateTime.of(2026, 3, 8, 2, 30).atZone(ZoneId.of("America/New_York"))**, Java sẽ điều chỉnh thành **03:30-04:00**. Với hệ thống cần độ chính xác nghiêm ngặt, phải kiểm tra valid offsets trước và quyết định từ chối, dời lịch hay đề nghị người dùng chọn giờ khác.

**Không phải vùng nào cũng có DST**, và không phải mọi lần điều chỉnh múi giờ đều đúng một tiếng hoặc diễn ra lúc 02:00. Logic tổng quát cần đọc ZoneRules thay vì tự viết luật “tháng 3 cộng một giờ”.

## 8. Phép cộng theo lịch khác thời lượng trên timeline

Câu “ngày mai vào lúc 12:00” khác câu “sau đúng 24 giờ”. Qua ngày bắt đầu DST tại New York:

~~~text
Bắt đầu:        2026-03-07T12:00-05:00[America/New_York]
Cộng 1 ngày:    2026-03-08T12:00-04:00[America/New_York]
Cộng 24 giờ:    2026-03-08T13:00-04:00[America/New_York]
~~~

**plusDays(1)** trên ZonedDateTime giữ ý nghĩa ngày lịch tại vùng; từ 12:00 hôm trước đến 12:00 hôm sau chỉ trôi qua **23 giờ** do đổi DST. **plusHours(24)** giữ thời lượng thực 24 giờ trên dòng thời gian và kết thúc lúc **13:00** theo đồng hồ địa phương.

| Bài toán | Phương pháp phù hợp | Vì sao |
| --- | --- | --- |
| Nhắc lịch vào 09:00 ngày hôm sau | LocalDate/LocalTime + ZoneId, hoặc ZonedDateTime.plusDays(1) với chính sách gap/overlap | Theo ngày dân sự |
| Timeout 30 giây | Duration.ofSeconds(30), Instant hoặc đồng hồ đo khoảng thời gian | Theo giây thực |
| Tính tuổi theo ngày tháng | Period.between(birthDate, today) | Theo lịch |
| Tính số phút giữa hai sự kiện | Duration.between(instant1, instant2) | Theo timeline |
| Tính ngày cuối tháng tiếp theo | LocalDate.plusMonths(1) với TemporalAdjusters | Không có tháng cố định 30 ngày |
| Tính một ngày làm việc | Quy tắc lịch nghiệp vụ và ngày nghỉ | PlusDays không tự bỏ cuối tuần/ngày lễ |

**Period** biểu diễn năm, tháng, ngày theo lịch; **Duration** biểu diễn giây và nano theo khoảng thời gian. Không được suy ra rằng **Period.ofDays(1)** luôn tương đương **Duration.ofHours(24)** khi áp dụng với ZonedDateTime. Một ngày lịch ở vùng nào đó có thể dài 23, 24 hoặc 25 giờ; thay đổi chính sách từng khiến có ngày ngắn/dài bất thường hơn.

**ChronoUnit.DAYS.between(LocalDate, LocalDate)** đếm số ngày lịch giữa hai ngày. **Duration.between(Instant, Instant)** tính thời gian thực trôi qua. Lựa chọn phải dựa trên câu hỏi nghiệp vụ.

## 9. Ví dụ Java 17+ chạy độc lập: cùng mốc, hai vùng, DST

Tạo tệp **CalendarZoneTimelineDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class CalendarZoneTimelineDemo {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");
        Instant event = Instant.parse("2026-10-24T10:15:30Z");

        System.out.println("Instant: " + event);
        System.out.println("Viet Nam: " + event.atZone(vietnam));
        System.out.println("New York: " + event.atZone(newYork));

        // 01:30 xuất hiện hai lần khi New York kết thúc DST.
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> offsets =
                newYork.getRules().getValidOffsets(overlap);
        System.out.println("Overlap offsets: " + offsets);
        ZonedDateTime first = ZonedDateTime.ofLocal(
                overlap, newYork, offsets.get(0));
        ZonedDateTime second = ZonedDateTime.ofLocal(
                overlap, newYork, offsets.get(1));
        System.out.println("First instant: " + first.toInstant());
        System.out.println("Second instant: " + second.toInstant());

        // 02:30 không tồn tại khi đồng hồ nhảy tiến.
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        System.out.println("Gap offsets: " +
                newYork.getRules().getValidOffsets(gap));
        System.out.println("Gap atZone: " + gap.atZone(newYork));

        // Một ngày lịch khác với đúng 24 giờ trôi qua.
        ZonedDateTime noon = ZonedDateTime.of(
                2026, 3, 7, 12, 0, 0, 0, newYork);
        ZonedDateTime nextCalendarDay = noon.plusDays(1);
        ZonedDateTime after24Hours = noon.plusHours(24);
        System.out.println("Plus one day: " + nextCalendarDay);
        System.out.println("Plus 24 hours: " + after24Hours);
        System.out.println("Elapsed hours for one calendar day: " +
                Duration.between(
                        noon.toInstant(),
                        nextCalendarDay.toInstant()).toHours());
    }
}
~~~

Lệnh biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 CalendarZoneTimelineDemo.java
java CalendarZoneTimelineDemo
~~~

Kết quả mong đợi với cơ sở dữ liệu múi giờ hỗ trợ quy tắc New York năm 2026:

~~~text
Instant: 2026-10-24T10:15:30Z
Viet Nam: 2026-10-24T17:15:30+07:00[Asia/Ho_Chi_Minh]
New York: 2026-10-24T06:15:30-04:00[America/New_York]
Overlap offsets: [-04:00, -05:00]
First instant: 2026-11-01T05:30:00Z
Second instant: 2026-11-01T06:30:00Z
Gap offsets: []
Gap atZone: 2026-03-08T03:30-04:00[America/New_York]
Plus one day: 2026-03-08T12:00-04:00[America/New_York]
Plus 24 hours: 2026-03-08T13:00-04:00[America/New_York]
Elapsed hours for one calendar day: 23
~~~

Giải thích:

- Một **Instant** chuyển sang hai ZoneId tạo ra hai chuỗi đồng hồ khác nhau nhưng cùng thời điểm thực.
- **getValidOffsets** tại overlap trả hai offset; chọn lần đầu hoặc lần sau tương ứng hai mốc UTC cách nhau một giờ.
- Tại gap, danh sách offset rỗng, còn **atZone** sử dụng chính sách điều chỉnh mặc định.
- Cộng một ngày theo lịch và cộng 24 giờ cho kết quả khác nhau qua ngày đổi DST.

Ví dụ dùng ngày tháng cố định, không dựa vào giờ hệ thống. Trong tương lai, quy tắc tzdb có thể cập nhật khi pháp luật địa phương thay đổi; với hệ thống nghiệp vụ cần kiểm thử quy tắc trên JDK/tzdb triển khai thực tế.

## 10. Ngày của cùng một sự kiện có thể khác nhau

Xét Instant **2026-10-24T23:30:00Z**:

- Ở UTC, ngày lịch là **24/10/2026**, giờ **23:30**.
- Tại Asia/Ho_Chi_Minh (+07:00), giờ **06:30 ngày 25/10/2026**.
- Tại America/New_York (-04:00 lúc đó), giờ **19:30 ngày 24/10/2026**.

Vì thế “ngày diễn ra giao dịch” theo **ngày UTC** có thể khác “ngày giao dịch tại Việt Nam”. Một báo cáo doanh thu theo ngày phải quy định rõ **vùng nghiệp vụ**, rồi tính LocalDate dựa vào Instant và vùng đó. Nếu lưu mỗi LocalDate mà không biết nguồn và vùng, rất khó kiểm toán doanh thu qua biên ngày.

### “Đầu ngày” và “cuối ngày” trong một vùng

Nếu cần truy vấn các sự kiện thuộc **ngày 25/10/2026 ở Việt Nam**:

1. Lấy **LocalDate.of(2026, 10, 25)**.
2. Lấy **start = date.atStartOfDay(zone).toInstant()**.
3. Lấy **end = date.plusDays(1).atStartOfDay(zone).toInstant()**.
4. Truy vấn **start <= instant < end** (đầu gồm, cuối loại).

Cách dùng khoảng **[start, end)** không cần giả định ngày luôn dài 86.400 giây và tránh lỗi tính “23:59:59.999” khi hệ thống lưu độ chính xác nano hoặc khi đổi múi giờ. Tại vùng DST, khoảng thời gian này có thể không bằng 24 giờ.

## 11. Lựa chọn kiểu Java theo ý nghĩa dữ liệu

| Bài toán | Kiểu chính | Thông tin bổ sung |
| --- | --- | --- |
| Log/audit thanh toán thực tế | **Instant** | ZoneId chỉ cần khi hiển thị |
| Ngày sinh, ngày hạn theo lịch | **LocalDate** | Quy định hệ lịch và vùng nghiệp vụ nếu cần |
| Giờ mở cửa hằng ngày | **LocalTime** | ZoneId địa điểm để tính Instant cho một ngày cụ thể |
| Cuộc họp 09:00 tại New York ngày 01/11/2026 | **LocalDateTime + ZoneId** | Xác nhận offset/lần xuất hiện nếu trùng DST; sau đó lưu Instant đã giải quyết |
| Trao đổi timestamp đã có offset qua API | **OffsetDateTime** | Nếu cần luật khu vực tương lai thì lưu ZoneId riêng |
| Biểu diễn lịch hẹn tại một địa điểm cụ thể | **ZonedDateTime** | Hiểu quy tắc gap/overlap khi tạo từ local time |
| Thời lượng chạy, timeout | **Duration** | Nên phân biệt wall-clock và đồng hồ đo thời gian trôi qua |
| Tuổi hoặc kỳ hạn tháng | **Period** | Dựa vào ngày lịch |
| Logic lấy “bây giờ” dễ test | **Clock** | Inject Clock hoặc Clock.fixed trong test |

Đối với dữ liệu phân tán, tránh truyền **LocalDateTime** mà không nói rõ vùng/offset rồi giả định phía nhận hiểu giống phía gửi.

## 12. Parse, định dạng và giao tiếp giữa dịch vụ

Ưu tiên định dạng **ISO 8601** có offset rõ ràng cho timestamp:

~~~text
2026-10-24                         ngày ISO thuần
2026-10-24T17:15:30                LocalDateTime, chưa có offset
2026-10-24T17:15:30+07:00          OffsetDateTime, xác định Instant
2026-10-24T10:15:30Z               Instant ở UTC
2026-10-24T17:15:30+07:00[Asia/Ho_Chi_Minh]
                                   ZonedDateTime có ZoneId
~~~

Để parse:

~~~java
LocalDate date = LocalDate.parse("2026-10-24");
LocalDateTime local = LocalDateTime.parse("2026-10-24T17:15:30");
Instant instant = Instant.parse("2026-10-24T10:15:30Z");
OffsetDateTime offset = OffsetDateTime.parse(
        "2026-10-24T17:15:30+07:00");
ZonedDateTime zoned = ZonedDateTime.parse(
        "2026-10-24T17:15:30+07:00[Asia/Ho_Chi_Minh]");
~~~

Đây là đoạn trích cần đặt trong phương thức và import java.time nếu biên dịch riêng. Khi định dạng theo **DateTimeFormatter**, chú ý **MM** là tháng, **mm** là phút; **HH** là giờ 0–23; **dd** là ngày trong tháng; **uuuu** là năm proleptic. Những mẫu có tên tháng/ngày trong tuần phụ thuộc Locale nên phải xác định Locale thích hợp.

**Thứ tự so sánh ngày giờ dưới dạng chuỗi không phải lúc nào cũng tương đương thứ tự Instant** nếu chúng mang offset khác nhau. Hãy parse thành kiểu có ngữ nghĩa, lấy Instant rồi mới so sánh.

### Độ lệch offset và ZoneId trong hợp đồng API

Nếu API chỉ muốn biết **sự kiện xảy ra khi nào**, gửi **Instant** ISO có Z là rõ nhất. Nếu cần lưu “giờ người dùng muốn gặp tại Paris trong năm sau”, phải gửi **LocalDateTime + ZoneId** và chính sách áp dụng khi vùng đổi DST. Một offset ghi lúc đặt hẹn chưa chắc là offset của ngày diễn ra. Nếu gửi cả offset lẫn vùng, xác minh offset tương thích với ZoneRules tại giờ địa phương; nhất là tại overlap. Nếu offset không hợp lệ, cần báo lỗi hoặc quy định cách xử lý.

## 13. Quản lý Clock và đồng hồ hệ thống

**Instant.now()**, **ZonedDateTime.now()** hay **LocalDate.now()** lấy từ đồng hồ và múi giờ môi trường theo cách gọi. Dùng **Clock** trong logic nghiệp vụ để kiểm thử có thể tái lập:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-10-24T23:30:00Z"),
        ZoneId.of("UTC"));
Instant now = Instant.now(clock);
LocalDate businessDate = LocalDate.now(
        clock.withZone(ZoneId.of("Asia/Ho_Chi_Minh")));
// now = 2026-10-24T23:30:00Z
// businessDate = 2026-10-25
~~~

Đoạn trích cần import java.time và đặt trong phương thức. **Clock.systemUTC()** hợp lý khi lưu Instant. Nếu logic ngày tháng phụ thuộc địa điểm nghiệp vụ, truyền **ZoneId** vào hàm thay vì mặc định dựa trên **ZoneId.systemDefault()**, vốn có thể thay đổi giữa máy phát triển, máy chủ và container.

Đồng hồ hệ thống có thể được điều chỉnh bởi cơ chế đồng bộ giờ và không bảo đảm là đồng hồ đơn điệu. Khi đo thời lượng thực thi ngắn trong một tiến trình Java, **System.nanoTime()** thường phù hợp để lấy **hiệu giữa hai lần đo**; giá trị tuyệt đối của nanoTime không phải UTC timestamp và không có nghĩa để lưu hoặc gửi sang máy khác.

## 14. Các sai lầm thường gặp

1. **“LocalDateTime chính là UTC”**: sai; chỉ là trường ngày-giờ không có thông tin offset hay vùng. Nếu nghiệp vụ quy ước UTC, phải lưu và công bố quy ước đó, rồi gắn **ZoneOffset.UTC** một cách rõ ràng.
2. **“Asia/Ho_Chi_Minh và +07:00 là cùng một kiểu thông tin”**: sai; một bên là vùng có quy tắc, một bên là độ lệch cố định.
3. **“Tất cả ngày đều 24 tiếng”**: sai ở các vùng/ngày chuyển offset. Ngày lịch và Duration 24 giờ là hai ý niệm.
4. **“01:30 ngày kết thúc DST xác định được một Instant”**: sai nếu chưa chọn offset thích hợp.
5. **“02:30 ngày bắt đầu DST chắc chắn hợp lệ”**: không đúng ở những vùng đang nhảy đồng hồ qua 02:30.
6. **“Một Instant có cùng LocalDate ở mọi nơi”**: sai; việc đổi ngày khác nhau ở từng vùng.
7. **“Offset hôm nay đủ để tái tạo lịch lặp của năm sau”**: sai khi vùng có thể thay đổi offset.
8. **“Chỉ cần format chuỗi là chuyển được múi giờ”**: format chỉ thay cách hiển thị; phải dùng **atZone**, **withZoneSameInstant** hoặc cách chuyển đúng ngữ nghĩa.
9. **“Thay zone bằng withZoneSameLocal cũng giữ Instant”**: sai; **withZoneSameInstant** giữ mốc trên timeline, còn **withZoneSameLocal** cố giữ trường đồng hồ địa phương và có thể đổi Instant.
10. **“Mọi database tự lưu IANA ZoneId trong TIMESTAMP WITH TIME ZONE”**: không có bảo đảm như vậy; DB và driver có quy ước khác nhau. Nên định nghĩa hợp đồng rõ ràng và lưu ZoneId riêng nếu cần.
11. **“Cứ lấy 24 * 60 * 60 để tìm cuối ngày”**: dễ sai qua DST. Hãy dùng ranh giới ngày của từng ZoneId.
12. **“Instant và giờ đồng hồ không cần test ngày cuối tháng/năm nhuận/DST”**: bỏ sót những bug phát sinh đúng tại biên lịch.

## 15. Quy trình xác định mô hình đúng

Khi nhận yêu cầu “lưu giờ hẹn và gửi thông báo trước 30 phút”, có thể lần lượt quyết định:

1. **Định nghĩa lịch**: người dùng chọn ngày tháng theo hệ lịch nào (thường ISO)? Ngày/giờ đó là giờ tại địa điểm hay giờ thiết bị?
2. **Định nghĩa vùng**: nhận ZoneId IANA của địa điểm, ví dụ **Asia/Ho_Chi_Minh** hoặc **America/New_York**.
3. **Giải quyết mơ hồ**: dùng ZoneRules kiểm tra LocalDateTime. Nếu gap, áp dụng chính sách từ chối/đẩy lịch; nếu overlap, yêu cầu chọn một trong hai offset hoặc dùng quy tắc thống nhất.
4. **Xác định Instant của cuộc hẹn** sau khi đã biết offset hợp lệ.
5. **Tính nhắc trước 30 phút** bằng **Instant.minus(Duration.ofMinutes(30))**, vì yêu cầu là 30 phút thực trước thời điểm diễn ra.
6. **Hiển thị lại** bằng **instant.atZone(userZone)** và formatter phù hợp. Với lịch hẹn lặp, giữ quy tắc lịch/zone riêng và tính lần diễn ra kế tiếp theo lịch.

Cách làm này phân biệt đầy đủ **ngày trên lịch**, **giờ tường đồng hồ**, **quy tắc vùng**, **offset của ngày được chọn** và **mốc tuyệt đối**, tránh các lỗi chỉ xuất hiện khi đổi múi giờ hoặc DST.

### Câu hỏi tự kiểm tra

- **Hai người thấy đồng hồ 09:00 cùng ngày, có chắc gặp cùng Instant?** Không; cần offset/zone và giải quyết giờ lặp.
- **Hai người cùng quan sát một Instant, có chắc cùng LocalDate?** Không; khác múi giờ có thể qua biên ngày.
- **Cộng một ngày lịch có luôn trôi qua 86.400 giây?** Không; DST làm độ dài ngày địa phương thay đổi.
- **Lưu ZoneId có còn cần lưu Instant đã chốt?** Có thể cần cả hai nếu lịch hẹn đã xác nhận phải giữ nguyên mốc tuyệt đối và vẫn muốn hiển thị/giải thích theo vùng.
- **Có thể chuyển LocalDateTime sang Instant bằng UTC offset đã biết không?** Có, nếu offset là thông tin hợp lệ của giá trị đó; dùng **localDateTime.toInstant(offset)**. Nếu cần luật giờ địa phương lâu dài, vẫn cần ZoneId.

## Tài liệu tham khảo

- [Java SE 17 — java.time package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): khái niệm ngày giờ và các lớp cốt lõi.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): mốc timeline, epoch và độ chính xác.
- [Java SE 17 — ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): định danh vùng và quy tắc.
- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): valid offsets, gap và overlap.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): ánh xạ giữa local time và Instant, phép cộng ngày giờ.
- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html) và [Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): thời lượng thực và đơn vị lịch.
