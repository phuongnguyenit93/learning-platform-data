# Phân biệt ngày, giờ cục bộ, thời điểm và múi giờ trong Java

## 1. Mục tiêu bài học

Trong **mô hình ngày giờ** của Java, cùng một chuỗi "2024-06-01 09:00" có thể biểu diễn lịch họp theo đồng hồ Hà Nội, lịch họp theo đồng hồ Paris hoặc một giá trị chưa xác định được thời điểm tuyệt đối. Đó là ba ý nghĩa khác nhau, không thể dùng bừa một kiểu dữ liệu.

Bài này tập trung vào các class trong java.time:

- **LocalDate**: ngày lịch, không có giờ hoặc múi giờ.
- **LocalTime**: giờ trên đồng hồ, không có ngày hoặc múi giờ.
- **LocalDateTime**: ngày và giờ cục bộ, chưa có zone/offset.
- **Instant**: một điểm tuyệt đối trên dòng thời gian.
- **ZoneId**: tên vùng và bộ quy tắc múi giờ.
- **ZoneOffset**: độ lệch cố định so với UTC.
- **ZonedDateTime**: local date-time gắn với ZoneId và offset hợp lệ.
- **OffsetDateTime**: local date-time gắn với offset, nhưng không lưu tên vùng địa lý.

Bạn sẽ biết cách chuyển đổi đúng, nhận diện DST gap/overlap, so sánh calendar time với elapsed time, dùng Clock để test và thiết kế thời gian cho lịch hẹn, log, API, cơ sở dữ liệu.

**Ghi chú phiên bản:** Các khái niệm cốt lõi được bổ sung từ Java 8, **vẫn còn áp dụng** trong những JDK hiện hành. Tất cả ví dụ độc lập biên dịch bằng Java 17+, dùng API được duy trì thay vì cách làm đã legacy.

## 2. Cùng một con số không đồng nghĩa cùng một thời điểm

Câu hỏi “09:00 ngày 1/6/2024” mới chỉ có **ngày giờ theo đồng hồ**, chưa nói đồng hồ ở đâu. Muốn chuyển thành một mốc trên timeline, cần biết ZoneId hoặc offset phù hợp:

~~~text
LocalDate 2024-06-01            -> chỉ ngày lịch
LocalTime 09:00                 -> chỉ giờ theo đồng hồ
LocalDateTime 2024-06-01T09:00  -> ngày + giờ, chưa có múi giờ

    + ZoneId Asia/Ho_Chi_Minh   -> Instant 2024-06-01T02:00:00Z
    + ZoneOffset UTC            -> Instant 2024-06-01T09:00:00Z
~~~

Nếu hai sự kiện thực sự xảy ra **cùng một Instant**, người ở các vùng khác nhau sẽ đọc giờ trên đồng hồ khác nhau. Nếu hai người cùng hẹn “09:00 địa phương” tại hai vùng, họ **không nhất thiết** hẹn cùng một Instant.

| Nhu cầu nghiệp vụ | Kiểu thông tin cần |
|---|---|
| Ngày sinh của người dùng | LocalDate |
| Giờ cửa hàng mở cửa mỗi ngày | LocalTime + ZoneId/chính sách lịch |
| Ngày giờ lịch họp chưa chốt zone | LocalDateTime |
| Sự kiện log được ghi nhận khi nào | Instant |
| Hẹn một lần tại Paris | LocalDateTime + ZoneId, sau đó chọn một Instant |
| Hiển thị một event theo giờ Việt Nam | Instant.atZone(ZoneId) |
| Timestamp đến từ API có +07:00 | OffsetDateTime hoặc Instant |
| Lịch hằng tuần tại Paris | Giờ/ngày theo lịch + ZoneId + quy tắc DST |

### Không dùng offset của “hiện tại” cho ngày khác

Một ZoneId địa lý có thể dùng offset khác nhau tùy mùa, thời kỳ lịch sử và quy định pháp luật. Vì vậy khi xử lý một ngày cụ thể, phải áp dụng **quy tắc múi giờ của chính ngày đó**, không lấy offset đang có rồi gắn vào mọi bản ghi.

## 3. LocalDate — ngày theo lịch, không phải timestamp

LocalDate chứa năm, tháng, ngày theo lịch ISO-8601, ví dụ 2024-02-29. Nó không chứa giờ, offset, hay ZoneId.

~~~java
// Mảnh mã, cần import java.time.LocalDate.
LocalDate birthday = LocalDate.of(2000, 2, 29);
LocalDate invoiceDate = LocalDate.parse("2024-11-06");
~~~

Phù hợp với ngày sinh, ngày hết hạn theo lịch, ngày nghỉ, ngày bắt đầu chương trình, thời điểm theo khái niệm “cả ngày”. Không nên đổi một ngày sinh thành 00:00 UTC nếu nghiệp vụ **không có khái niệm giờ sinh**: điều này có thể hiển thị thành ngày trước/sau ở vùng khác.

Khi cần biết “hôm nay ở Việt Nam”:

~~~java
// Mảnh mã; lấy giờ hiện tại thật nên đầu ra thay đổi.
LocalDate today = LocalDate.now(
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Phương thức LocalDate.now() không tham số dùng default timezone của hệ thống, có thể khác ở laptop và máy chủ. Dùng ZoneId hoặc Clock cụ thể cho quy tắc nghiệp vụ.

Nếu cần bắt đầu một ngày tại một khu vực:

~~~java
// Mảnh mã: date là LocalDate; zone là ZoneId.
Instant start = date.atStartOfDay(zone).toInstant();
~~~

Hợp đồng atStartOfDay(zone) chọn **thời điểm sớm nhất hợp lệ của ngày đó** theo quy tắc vùng. Không phải mọi vùng lịch sử đều có đúng 00:00 làm thời điểm bắt đầu ngày.

## 4. LocalTime — giờ trên đồng hồ, chưa có ngày

LocalTime biểu diễn giờ trong ngày với độ chính xác tối đa tới nanosecond:

~~~java
// Mảnh mã:
LocalTime opening = LocalTime.of(9, 30);
LocalTime closing = LocalTime.parse("18:00");
~~~

Dùng cho giờ mở cửa, giờ trực, báo thức theo đồng hồ địa phương. Nó không thể tự trở thành Instant vì chưa có **ngày** và **zone/offset**. “09:00 hôm nay” khác “09:00 ngày mai”; và 09:00 tại Paris khác 09:00 tại Hà Nội.

Khi hệ thống có lịch lặp mỗi ngày lúc 09:00, không lưu duy nhất một Instant rồi cộng 24 giờ mãi mãi nếu quy tắc yêu cầu **09:00 theo đồng hồ địa phương**. Khi vùng áp dụng DST, khoảng cách thực giữa hai lần 09:00 có thể khác 24 giờ.

## 5. LocalDateTime — ngày và giờ cục bộ vẫn chưa đủ

LocalDateTime kết hợp LocalDate và LocalTime:

~~~java
// Mảnh mã:
LocalDateTime local =
        LocalDateTime.of(2024, 6, 1, 9, 0);
~~~

Giá trị 2024-06-01T09:00 không biết đây là giờ UTC, Việt Nam, Paris hay Tokyo. Nó chưa định nghĩa một Instant duy nhất.

Bạn có thể gắn zone rồi chuyển:

~~~java
// Mảnh mã:
Instant vietnam = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
Instant utc = local
        .atZone(ZoneOffset.UTC)
        .toInstant();
~~~

vietnam là 2024-06-01T02:00:00Z, còn utc là 2024-06-01T09:00:00Z. Hai sự kiện chênh bảy giờ dù có cùng LocalDateTime.

**Không nhầm LocalDateTime với “UTC timestamp thiếu chữ Z”.** Nếu API nhận LocalDateTime nhưng các bên hiểu khác timezone, dữ liệu có thể sai ngay từ lúc parse hoặc lưu DB.

### Khi nào LocalDateTime vẫn hữu ích?

- Người dùng đang chọn ngày và giờ địa phương **trước khi** chọn múi giờ.
- Một lịch có ý nghĩa theo “đồng hồ trên tường”, còn ZoneId lưu ở field riêng.
- Dữ liệu địa phương thuần túy không có mục đích so sánh toàn cầu.
- Lịch lặp cần giữ giờ địa phương cố định dù UTC offset thay đổi.

Trong mọi trường hợp biến thành timestamp, cần thêm thông tin vùng và chính sách xử lý DST nếu mốc local không hợp lệ hoặc mơ hồ.

## 6. Instant — một điểm trên timeline

Instant biểu diễn một mốc thời gian độc lập với khu vực địa lý. Nó được liên hệ với epoch tại 1970-01-01T00:00:00Z và có độ chính xác tới nanosecond theo mô hình Java Time-Scale.

~~~java
// Mảnh mã:
Instant event = Instant.parse("2024-06-01T02:00:00Z");
Instant epoch = Instant.EPOCH;
~~~

Dấu Z thể hiện offset 0 trong chuỗi ISO-8601. Instant không chứa ZoneId hay “giờ tại Paris”, chỉ là thời điểm có thể **hiển thị** bằng nhiều đồng hồ địa phương.

Instant phù hợp cho:

- Log, createdAt/updatedAt của event.
- Deadline tuyệt đối, như token hết hạn đúng 30 phút sau khi phát hành.
- So sánh sự kiện xảy ra trước/sau giữa các vùng.
- Thời điểm xử lý trong hệ thống phân tán.
- Mốc truyền qua API khi muốn nhất quán về timeline.

### Cẩn thận với epoch seconds và milliseconds

- Instant.ofEpochSecond nhận **giây**.
- Instant.ofEpochMilli nhận **mili giây**.
- Instant.toEpochMilli có thể mất phần độ chính xác dưới mili giây.
- Đừng suy đoán unit của số nguyên từ độ dài chuỗi; ghi rõ trong contract.

Instant chỉ giải quyết bài toán “thời điểm nào”; nó **không thay thế** LocalDate/LocalTime/ZoneId cho lịch lặp theo giờ địa phương.

## 7. Ví dụ chạy được 1 — giá trị local và hai Instant

Tạo file **LocalTemporalTypesDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class LocalTemporalTypesDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(9, 30);
        LocalDateTime local = LocalDateTime.of(2024, 6, 1, 9, 0);

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant accordingToVietnam = local.atZone(vietnam).toInstant();
        Instant accordingToUtc = local.atZone(ZoneOffset.UTC).toInstant();

        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("local=" + local);
        System.out.println("vietnamInstant=" + accordingToVietnam);
        System.out.println("utcInstant=" + accordingToUtc);
        System.out.println("sameInstant="
                + accordingToVietnam.equals(accordingToUtc));
    }
}
~~~

Chạy:

~~~text
javac --release 17 LocalTemporalTypesDemo.java
java LocalTemporalTypesDemo
~~~

Stdout:

~~~text
date=2024-02-29
time=09:30
local=2024-06-01T09:00
vietnamInstant=2024-06-01T02:00:00Z
utcInstant=2024-06-01T09:00:00Z
sameInstant=false
~~~

2024 là năm nhuận nên LocalDate 29/2 hợp lệ. Cùng LocalDateTime 09:00 nhưng theo hai zone khác nhau tạo ra hai Instant khác nhau. Trong ứng dụng thật, **nguồn cung cấp zone** phải được quy định rõ.

## 8. ZoneId và ZoneOffset khác nhau ở đâu?

### ZoneId — tên vùng và bộ quy tắc múi giờ

ZoneId.of("Europe/Paris"), ZoneId.of("Asia/Ho_Chi_Minh") hoặc ZoneId.of("America/New_York") mô tả một vùng có quy tắc đổi offset qua các giai đoạn lịch sử và, nếu có, theo mùa.

ZoneId cung cấp ZoneRules để tra offset ứng với **ngày/Instant cụ thể**. Quy tắc phụ thuộc dữ liệu múi giờ tzdb được JDK duy trì và có thể được cập nhật khi luật của một quốc gia thay đổi.

### ZoneOffset — độ lệch cố định

ZoneOffset.of("+07:00"), ZoneOffset.of("+01:00"), ZoneOffset.UTC mô tả chênh lệch giờ so với UTC, **không** chứa đầy đủ lịch đổi giờ của một vùng.

| Vùng/ngữ cảnh | Ví dụ offset |
|---|---|
| UTC | Z / +00:00 |
| Việt Nam ở thời điểm hiện đại thường dùng | +07:00 |
| Paris mùa đông 2024 | +01:00 |
| Paris mùa hè 2024 | +02:00 |

Nếu chỉ lưu offset +01:00 cho lịch gặp mặt tại Paris, đến mùa hè bạn có thể tính lệch một giờ. Muốn giữ lịch “09:00 Paris”, hãy lưu ZoneId vùng.

**Không dựa vào chữ viết tắt mơ hồ** như CST/IST vì chúng có thể được dùng cho nhiều nơi hoặc quy ước. Dùng tên khu vực theo định dạng Area/Location hoặc một offset theo contract rõ ràng.

### ZoneId.systemDefault

ZoneId.systemDefault() truy vấn timezone mặc định của JVM tại thời điểm gọi. Nó có thể khác nhau giữa máy dev, container, CI và production. Nếu dữ liệu thuộc người dùng, cửa hàng hoặc thị trường cụ thể, hãy dùng **zone của nghiệp vụ**, không âm thầm lấy zone của máy chạy server.

## 9. ZonedDateTime — local date-time với quy tắc vùng

ZonedDateTime kết hợp LocalDateTime, ZoneId và một offset được xác định theo luật zone. Nhờ đó, nó gắn với một Instant cụ thể.

~~~java
// Mảnh mã:
Instant event = Instant.parse("2024-06-01T00:00:00Z");
ZonedDateTime inVietnam =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime inParis =
        event.atZone(ZoneId.of("Europe/Paris"));
~~~

Cùng Instant có thể hiển thị:

~~~text
2024-06-01T07:00+07:00[Asia/Ho_Chi_Minh]
2024-06-01T02:00+02:00[Europe/Paris]
~~~

Không có mâu thuẫn: đây là **hai đồng hồ cho cùng một thời điểm**.

### withZoneSameInstant và withZoneSameLocal

Hai phương thức trông giống nhau nhưng ngữ nghĩa khác:

- withZoneSameInstant(newZone) **giữ nguyên Instant**, chuyển local fields để hiển thị theo vùng khác.
- withZoneSameLocal(newZone) cố **giữ nguyên ngày giờ địa phương**, rồi áp dụng quy tắc vùng mới. Instant có thể thay đổi; trong DST gap local time thậm chí có thể được điều chỉnh.

Khi hiển thị log, lịch hẹn đã xác nhận hoặc event cho người ở vùng khác, phần lớn trường hợp phải giữ **same instant**. Giữ same local chỉ khi bạn thực sự muốn “cùng số trên đồng hồ ở vùng mới”.

## 10. OffsetDateTime — ngày giờ và offset, nhưng không biết vùng địa lý

OffsetDateTime gồm LocalDateTime + ZoneOffset. Ví dụ:

~~~java
// Mảnh mã:
OffsetDateTime received =
        OffsetDateTime.parse("2024-06-01T09:30+07:00");
Instant actual = received.toInstant();
~~~

actual là 2024-06-01T02:30:00Z. Timestamp API có offset là đủ xác định Instant, nhưng +07:00 **không chứng minh** dữ liệu gốc ở vùng Asia/Ho_Chi_Minh.

| Kiểu | Ngày/giờ cục bộ | ZoneOffset | ZoneId vùng | Có thể xác định Instant? |
|---|---|---|---|---|
| LocalDate | Chỉ ngày | Không | Không | Chưa |
| LocalTime | Chỉ giờ | Không | Không | Chưa |
| LocalDateTime | Có | Không | Không | Chưa |
| Instant | Không lưu local fields | Không cần | Không cần | Chính nó |
| OffsetDateTime | Có | Có | Không có tên vùng | Có |
| ZonedDateTime | Có | Có | Có | Có |

Dùng OffsetDateTime khi API cần giữ offset được gửi kèm. Dùng ZonedDateTime khi việc tính lịch phụ thuộc **quy tắc của khu vực**. Dùng Instant khi điều quan trọng là một điểm trên timeline.

## 11. Ví dụ chạy được 2 — chuyển vùng và giữ gì?

Tạo file **SameInstantDifferentZonesDemo.java**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class SameInstantDifferentZonesDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse("2024-06-01T00:00:00Z");

        ZonedDateTime vietnam =
                event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        ZonedDateTime paris =
                event.atZone(ZoneId.of("Europe/Paris"));

        ZonedDateTime converted = vietnam.withZoneSameInstant(
                ZoneId.of("Europe/Paris"));
        ZonedDateTime sameClock = vietnam.withZoneSameLocal(
                ZoneId.of("Europe/Paris"));

        System.out.println("event=" + event);
        System.out.println("vietnam=" + vietnam);
        System.out.println("paris=" + paris);
        System.out.println("converted=" + converted);
        System.out.println("sameInstant="
                + vietnam.toInstant().equals(paris.toInstant()));
        System.out.println("sameClock=" + sameClock);
        System.out.println("sameClockInstant=" + sameClock.toInstant());
    }
}
~~~

Chạy:

~~~text
javac --release 17 SameInstantDifferentZonesDemo.java
java SameInstantDifferentZonesDemo
~~~

Stdout:

~~~text
event=2024-06-01T00:00:00Z
vietnam=2024-06-01T07:00+07:00[Asia/Ho_Chi_Minh]
paris=2024-06-01T02:00+02:00[Europe/Paris]
converted=2024-06-01T02:00+02:00[Europe/Paris]
sameInstant=true
sameClock=2024-06-01T07:00+02:00[Europe/Paris]
sameClockInstant=2024-06-01T05:00:00Z
~~~

Hàm withZoneSameInstant đổi 07:00 Việt Nam thành 02:00 Paris **vẫn cùng 00:00Z**. Hàm withZoneSameLocal giữ 07:00 trên đồng hồ Paris, biến thành 05:00Z. Đây là lỗi chuyển timezone khá phổ biến.

## 12. DST: có những giờ địa phương không tồn tại hoặc xuất hiện hai lần

DST (*Daylight Saving Time*) là chính sách đổi offset của một số vùng theo mùa. Không phải nơi nào cũng áp dụng và luật có thể đổi theo năm.

### Gap: đồng hồ nhảy tới trước

Ở Europe/Paris, ngày 31/03/2024:

~~~text
01:59:59 +01:00
  -> 03:00:00 +02:00

LocalDateTime 2024-03-31T02:30 không tồn tại tại Paris.
~~~

LocalDateTime.of(2024,3,31,2,30) **tự nó hợp lệ** vì ngày và các trường đồng hồ hợp lệ. Nhưng khi gắn với ZoneId Europe/Paris, **không có offset hợp lệ** cho 02:30.

### Overlap: đồng hồ quay lại

Ở Europe/Paris, ngày 27/10/2024:

~~~text
02:59:59 +02:00
  -> 02:00:00 +01:00

LocalDateTime 2024-10-27T02:30 xảy ra hai lần:
02:30 +02:00 -> Instant 2024-10-27T00:30:00Z
02:30 +01:00 -> Instant 2024-10-27T01:30:00Z
~~~

Với overlap, chỉ có local date-time + ZoneId vẫn chưa đủ để xác định **lần thứ nhất hay thứ hai** nếu ứng dụng cần chọn chính xác.

### Quy tắc mặc định của atZone

Java ZonedDateTime có cách giải quyết thuận tiện:

- Bình thường: local date-time có một offset hợp lệ.
- Gap: atZone tự đưa local time tiến lên theo độ dài gap; ví dụ 02:30 thành 03:30 tại Paris.
- Overlap: khi tạo một ZonedDateTime từ LocalDateTime, thường chọn offset sớm hơn (mùa hè +02:00 trong ví dụ), trừ khi có offset hợp lệ được ưu tiên trong các thao tác phù hợp.

**Đừng coi hành vi tự điều chỉnh là quyết định nghiệp vụ đã được người dùng đồng ý.** Với ứng dụng đặt lịch, cần biết có dời cuộc hẹn trong gap hay từ chối và có cần người dùng chọn lần thứ mấy trong overlap.

## 13. ZoneRules và việc kiểm tra hợp lệ

ZoneId.getRules().getValidOffsets(localDateTime) cho biết số offset hợp lệ:

| Số offset | Ý nghĩa | Hành động gợi ý |
|---:|---|---|
| 0 | Gap, giờ địa phương không tồn tại | Chặn hoặc giải quyết theo chính sách |
| 1 | Một giờ hợp lệ bình thường | Có thể lấy offset đó |
| 2 | Overlap, giờ được lặp lại | Chọn offset trước/sau rõ ràng |

Có thể dùng ZoneRules.getTransition(localDateTime) để phân tích trường hợp gap/overlap và ZoneRules.isValidOffset để kiểm tra offset do API nhận vào.

**ZonedDateTime.ofStrict(local,offset,zone)** chỉ chấp nhận offset hợp lệ với local time trong zone; ném DateTimeException nếu không hợp lệ. Với overlap, dùng withEarlierOffsetAtOverlap hoặc withLaterOffsetAtOverlap để chọn lần mong muốn.

Với dữ liệu lịch đã xác nhận, có thể lưu cả Instant được chọn và ZoneId để phân biệt **mốc thực tế đã chốt** với **cách người dùng đặt lịch**.

## 14. Ví dụ chạy được 3 — gap và overlap tại Paris

Tạo file **DstGapOverlapDemo.java**:

~~~java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class DstGapOverlapDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);
        List<ZoneOffset> gapOffsets =
                paris.getRules().getValidOffsets(gap);
        ZonedDateTime shifted = gap.atZone(paris);

        System.out.println("gap.validOffsets=" + gapOffsets);
        System.out.println("gap.resolved=" + shifted);

        try {
            ZonedDateTime.ofStrict(gap, ZoneOffset.ofHours(1), paris);
        } catch (DateTimeException expected) {
            System.out.println("gap.strict=DateTimeException");
        }

        LocalDateTime overlap =
                LocalDateTime.of(2024, 10, 27, 2, 30);
        List<ZoneOffset> overlapOffsets =
                paris.getRules().getValidOffsets(overlap);

        ZonedDateTime earlier = overlap.atZone(paris);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("overlap.validOffsets=" + overlapOffsets);
        System.out.println("overlap.earlier=" + earlier);
        System.out.println("overlap.later=" + later);
        System.out.println("earlier.instant=" + earlier.toInstant());
        System.out.println("later.instant=" + later.toInstant());
        System.out.println("between.minutes="
                + Duration.between(earlier.toInstant(),
                        later.toInstant()).toMinutes());
    }
}
~~~

Chạy:

~~~text
javac --release 17 DstGapOverlapDemo.java
java DstGapOverlapDemo
~~~

Stdout:

~~~text
gap.validOffsets=[]
gap.resolved=2024-03-31T03:30+02:00[Europe/Paris]
gap.strict=DateTimeException
overlap.validOffsets=[+02:00, +01:00]
overlap.earlier=2024-10-27T02:30+02:00[Europe/Paris]
overlap.later=2024-10-27T02:30+01:00[Europe/Paris]
earlier.instant=2024-10-27T00:30:00Z
later.instant=2024-10-27T01:30:00Z
between.minutes=60
~~~

Điểm quan trọng:

1. Gap không có offset hợp lệ; atZone tự điều chỉnh đến 03:30+02:00, trong khi ofStrict từ chối.
2. Overlap có đúng hai offset; hai cách hiểu 02:30 cách nhau 60 phút trên timeline.
3. withLaterOffsetAtOverlap chuyển từ lần đầu +02:00 sang lần sau +01:00, **không sửa giờ địa phương 02:30**.
4. Các ngày 2024 được chọn vì có quy tắc lịch sử đã biết; đừng mặc định DST tương lai luôn theo đúng mẫu này.

## 15. Period và Duration: một ngày lịch không nhất thiết dài 24 giờ

Trong java.time có hai ý nghĩa khác nhau:

- **Period**: khoảng cách theo **năm, tháng, ngày của lịch**, phù hợp với “cộng một ngày lịch”, ngày kỷ niệm, chu kỳ theo calendar.
- **Duration**: khoảng thời gian thực tính theo **giây/nanosecond**, phù hợp “90 phút nữa”, deadline, elapsed time.

Xét Paris ngày trước đợt đổi giờ mùa xuân:

~~~text
2024-03-30T12:00+01:00[Europe/Paris] = 11:00Z

plusDays(1):
2024-03-31T12:00+02:00[Europe/Paris] = 10:00Z
=> elapsed time 23 giờ.

plusHours(24):
2024-03-31T13:00+02:00[Europe/Paris] = 11:00Z
=> elapsed time đúng 24 giờ.
~~~

Vì đổi offset, cộng một ngày lịch và cộng 24 giờ không luôn ra cùng local time. Ở mùa thu, một ngày theo đồng hồ địa phương có thể dài 25 giờ.

**Quy tắc nghiệp vụ:**

- “Họp đúng 09:00 mỗi ngày” cần calendar scheduling + ZoneId + giải quyết DST.
- “Token hết hạn sau đúng 24 giờ” nên cộng Duration lên Instant.
- “Đến hết ngày 31/3 tại Paris” cần diễn giải LocalDate theo zone và xác định ranh giới ngày theo chính sách.
- Duration.between(LocalDateTimeA, LocalDateTimeB) không đủ để đo elapsed time **qua DST** vì không có ZoneId.

## 16. Ví dụ chạy được 4 — cộng ngày và cộng giờ qua DST

Tạo file **CalendarVsTimelineDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class CalendarVsTimelineDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        ZonedDateTime start =
                ZonedDateTime.of(2024, 3, 30, 12, 0, 0, 0, paris);
        ZonedDateTime calendarNext = start.plusDays(1);
        ZonedDateTime after24Hours = start.plusHours(24);

        System.out.println("start=" + start);
        System.out.println("calendarNext=" + calendarNext);
        System.out.println("after24Hours=" + after24Hours);
        System.out.println("calendar.elapsedHours="
                + Duration.between(start.toInstant(),
                        calendarNext.toInstant()).toHours());
        System.out.println("fixed.elapsedHours="
                + Duration.between(start.toInstant(),
                        after24Hours.toInstant()).toHours());

        LocalDate before = LocalDate.of(2024, 3, 30);
        LocalDate after = before.plusDays(1);
        System.out.println("period=" + Period.between(before, after));

        ZonedDateTime fall =
                ZonedDateTime.of(2024, 10, 26, 12, 0, 0, 0, paris);
        ZonedDateTime fallNext = fall.plusDays(1);
        System.out.println("fall.elapsedHours="
                + Duration.between(fall.toInstant(),
                        fallNext.toInstant()).toHours());
    }
}
~~~

Chạy:

~~~text
javac --release 17 CalendarVsTimelineDemo.java
java CalendarVsTimelineDemo
~~~

Stdout:

~~~text
start=2024-03-30T12:00+01:00[Europe/Paris]
calendarNext=2024-03-31T12:00+02:00[Europe/Paris]
after24Hours=2024-03-31T13:00+02:00[Europe/Paris]
calendar.elapsedHours=23
fixed.elapsedHours=24
period=P1D
fall.elapsedHours=25
~~~

Period.between của hai LocalDate là P1D, bất kể thời gian thực giữa hai ngày theo vùng là 23, 24 hay 25 giờ. Hãy chọn Period và Duration theo **ý nghĩa** chứ không chỉ theo kiểu dữ liệu đầu vào.

## 17. Clock — thay thế phụ thuộc thời gian thật trong test

Instant.now() và ZonedDateTime.now() lấy thời điểm hiện tại nên chạy lại có thể cho kết quả khác. **Clock** giúp đưa nguồn thời gian vào API và tạo test deterministic.

~~~java
// Mảnh mã, cần import java.time.*.
Clock clock = Clock.fixed(
        Instant.parse("2024-12-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
Instant now = Instant.now(clock);
LocalDate today = LocalDate.now(clock);
~~~

- Clock.fixed giữ nguyên Instant trong mọi lần truy vấn, phù hợp unit test.
- LocalDate.now(clock) dùng ZoneId của Clock để quyết định ngày địa phương.
- Instant.now(clock) dùng Instant của Clock, không cần ZoneId để biểu diễn timeline.
- Clock.systemUTC() vẫn là đồng hồ thời gian thực; **không giống Clock.fixed**.
- Trong service, nhận Clock/ZoneId qua constructor hoặc dependency injection giúp test được logic mà không đổi đồng hồ của máy.

Với deadline, lưu Instant, tính qua Duration rồi đối chiếu Instant.now(clock). Với lịch định kỳ, dùng local time + zone và một bộ lập lịch hiểu DST.

## 18. Ví dụ chạy được 5 — sự kiện hết hạn và lịch hẹn

Tạo file **SchedulingWithClockDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class SchedulingWithClockDemo {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId paris = ZoneId.of("Europe/Paris");

        Clock fixed = Clock.fixed(
                Instant.parse("2024-12-01T00:00:00Z"), vietnam);

        System.out.println("now=" + Instant.now(fixed));
        System.out.println("today=" + LocalDate.now(fixed));

        Instant expires = Instant.now(fixed)
                .plus(Duration.ofMinutes(90));
        System.out.println("expires=" + expires);

        LocalDateTime bookingLocal =
                LocalDateTime.of(2024, 12, 2, 9, 0);
        ZonedDateTime bookingVietnam = bookingLocal.atZone(vietnam);
        ZonedDateTime bookingParis =
                bookingVietnam.withZoneSameInstant(paris);

        System.out.println("booking.vn=" + bookingVietnam);
        System.out.println("booking.instant="
                + bookingVietnam.toInstant());
        System.out.println("booking.paris=" + bookingParis);
    }
}
~~~

Chạy:

~~~text
javac --release 17 SchedulingWithClockDemo.java
java SchedulingWithClockDemo
~~~

Stdout:

~~~text
now=2024-12-01T00:00:00Z
today=2024-12-01
expires=2024-12-01T01:30:00Z
booking.vn=2024-12-02T09:00+07:00[Asia/Ho_Chi_Minh]
booking.instant=2024-12-02T02:00:00Z
booking.paris=2024-12-02T03:00+01:00[Europe/Paris]
~~~

Bài toán có **hai loại thời gian**. Hết hạn sau 90 phút là Duration tính từ Instant. Lịch hẹn 09:00 ngày 02/12 theo đồng hồ Việt Nam cần ZoneId trước khi trở thành Instant. Khi hiển thị cho người ở Paris, chuyển **cùng Instant** và nhận 03:00 theo giờ Paris mùa đông.

## 19. Parse ISO-8601: chuỗi có đủ thông tin chưa?

| Chuỗi | Kiểu parse phù hợp | Có đủ để biết Instant? |
|---|---|---|
| 2024-06-01 | LocalDate.parse | Không |
| 09:30 | LocalTime.parse | Không |
| 2024-06-01T09:30 | LocalDateTime.parse | Không |
| 2024-06-01T09:30+07:00 | OffsetDateTime.parse | Có |
| 2024-06-01T02:30:00Z | Instant.parse | Có |
| 2024-06-01T09:30+07:00[Asia/Ho_Chi_Minh] | ZonedDateTime.parse | Có |

**Đừng mặc định chuỗi thiếu offset/zone là UTC.** Nó có thể là dữ liệu đồng hồ người dùng theo một vùng do API quy định, nhưng một chuỗi đơn thuần không tự nói điều đó.

### DateTimeFormatter

DateTimeFormatter có các formatter ISO tiêu chuẩn và pattern tùy biến. Formatter immutable và thread-safe, thường có thể tái sử dụng.

Nếu format chỉ in uuuu-MM-dd HH:mm mà không có offset/zone, dữ liệu được truyền **mất thông tin về Instant**. Nên phân biệt pattern cho offset và zone trong hệ thống. Parsing thành một LocalDateTime hợp lệ chưa xác nhận mốc đó hợp lệ tại ZoneId trong kỳ DST: kiểm tra rules sau khi biết zone.

### OffsetDateTime so với ZonedDateTime trong API

OffsetDateTime lưu offset +07:00 nhận từ client; điều đó đủ quy về Instant, nhưng **không biết thành phố/vùng**. ZonedDateTime có ZoneId và offset; dùng khi cần giữ ngữ cảnh múi giờ địa lý. Đừng tự suy luận rằng +07:00 là Asia/Ho_Chi_Minh nếu contract không nói như vậy.

## 20. Ví dụ chạy được 6 — parse đúng loại thông tin

Tạo file **TimeParsingDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TimeParsingDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.parse("2024-06-01");
        LocalTime time = LocalTime.parse("09:30");
        LocalDateTime local =
                LocalDateTime.parse("2024-06-01T09:30");

        OffsetDateTime offset =
                OffsetDateTime.parse("2024-06-01T09:30+07:00");
        ZonedDateTime zoned = ZonedDateTime.parse(
                "2024-06-01T09:30+07:00[Asia/Ho_Chi_Minh]");
        Instant direct = Instant.parse("2024-06-01T02:30:00Z");

        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("local=" + local);
        System.out.println("offset.instant=" + offset.toInstant());
        System.out.println("zoned.instant=" + zoned.toInstant());
        System.out.println("sameInstant="
                + offset.toInstant().equals(direct));
        System.out.println("zone=" + zoned.getZone().getId());

        Instant explicit = local.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh")).toInstant();
        System.out.println("explicit.instant=" + explicit);
    }
}
~~~

Chạy:

~~~text
javac --release 17 TimeParsingDemo.java
java TimeParsingDemo
~~~

Stdout:

~~~text
date=2024-06-01
time=09:30
local=2024-06-01T09:30
offset.instant=2024-06-01T02:30:00Z
zoned.instant=2024-06-01T02:30:00Z
sameInstant=true
zone=Asia/Ho_Chi_Minh
explicit.instant=2024-06-01T02:30:00Z
~~~

Hai đối tượng OffsetDateTime và ZonedDateTime quy về cùng Instant trong ví dụ này. Nhưng chỉ ZonedDateTime còn biết tên vùng địa lý để áp dụng quy tắc múi giờ với **những local date-time khác**.

## 21. Thiết kế dữ liệu thời gian trong ứng dụng

| Nghiệp vụ | Biểu diễn gợi ý | Lý do |
|---|---|---|
| Ngày sinh, ngày kỷ niệm | LocalDate | Không ép ngày lịch thành timestamp |
| Giờ cửa hàng mở mỗi ngày | LocalTime + ZoneId + lịch | Không phải một mốc UTC cố định |
| Cuộc hẹn một lần, đã chọn thời điểm | Instant; có thể giữ ZoneId gốc | Khôi phục mốc thực tế và ngữ cảnh |
| Người dùng đang chọn 02:30 vào ngày DST overlap | LocalDateTime + ZoneId + lựa chọn offset | Cần phân biệt hai lần đồng hồ |
| Lịch họp hằng tuần tại Paris | DayOfWeek + LocalTime + ZoneId + DST policy | UTC offset thay đổi theo thời gian |
| Timestamp event/log | Instant | So sánh độc lập khu vực |
| Hết hạn sau 90 phút | Instant + Duration | Đo thời lượng thực |
| Đến hết ngày thị trường | LocalDate + ZoneId + cutoff policy | Phụ thuộc ngày địa phương |
| Báo cáo theo ngày tại cửa hàng | Group các Instant sang LocalDate trong ZoneId của cửa hàng | UTC day khác business day |
| Payload API có offset cụ thể | OffsetDateTime hoặc Instant | Có mốc timeline, chưa chắc có tên vùng |

**Có thể cần lưu đồng thời nhiều trường:** Instant dùng xác nhận sự kiện đã chọn, LocalDateTime/ZoneId dùng tái hiện đúng cách người dùng đặt lịch. Nếu lưu nhiều biểu diễn, hệ thống cần quy tắc cập nhật để chúng không mâu thuẫn.

### JSON, SQL và driver

- Khi gửi Instant, dùng chuỗi ISO với Z hoặc epoch với đơn vị rõ.
- Khi gửi lịch hẹn địa phương, truyền local date-time và ZoneId riêng nếu muốn bảo toàn quy tắc vùng.
- SQL TIMESTAMP và TIMESTAMP WITH TIME ZONE không nhất thiết lưu cùng dữ liệu ở mọi DB; nhiều hệ chuẩn hóa mốc và không lưu tên ZoneId gốc. Kiểm tra database/driver thực tế.
- JSON serializer có thể giữ Instant nhưng bỏ ZoneId; cần round-trip test nếu cần vùng lịch để chạy lịch tương lai.
- Không coi một số epoch đơn vị mili giây là giây, hoặc lưu nanosecond rồi giả định DB giữ đủ độ chính xác.

## 22. Những lỗi phổ biến

### 22.1. Lưu LocalDateTime.now() như UTC timestamp

LocalDateTime.now() lấy ngày giờ theo zone mặc định của runtime, nhưng giá trị trả **không mang zone**. Nếu server chạy ở Việt Nam và DB/app khác ngầm hiểu UTC, timestamp có thể bị dịch bảy giờ. Với event timestamp, dùng Instant hoặc kiểu DB có contract rõ ràng.

### 22.2. Đổi từ Việt Nam sang Paris bằng cộng/trừ số giờ cố định

Paris có thể ở UTC+1 mùa đông và UTC+2 mùa hè. Không viết vietnam.plusHours(-6) để đổi cho mọi ngày. Hãy chuyển cùng Instant sang ZoneId khác.

### 22.3. Coi ZoneOffset như ZoneId địa lý

+01:00 là chênh lệch; Europe/Paris có lịch đổi offset. Không lưu +01:00 thay cho Europe/Paris nếu muốn lịch cố định theo giờ vùng.

### 22.4. Giả định local time luôn hợp lệ và duy nhất

Khi DST gap, không có Instant đúng với một local time; khi overlap có hai Instant. Cần chính sách, kiểm tra ZoneRules và lưu lựa chọn.

### 22.5. Cộng 24 giờ cho một ngày lịch

Qua DST, plusDays(1) và plusHours(24) có thể khác nhau. Chọn calendar arithmetic nếu nghiệp vụ cần cùng giờ địa phương, chọn elapsed Duration nếu cần đủ số giây.

### 22.6. So sánh LocalDateTime của hai vùng như một timeline

Nếu a và b là local date-time ở các vùng khác nhau, a.isBefore(b) chỉ so các trường lịch, không quyết định event thật nào xảy ra trước. Khi đã biết ZoneId/offset, chuyển sang Instant trước khi so.

### 22.7. Dùng systemDefault cho người dùng

ZoneId.systemDefault() trả zone của JVM, không nhất thiết zone của khách hàng. Service, container và CI có thể cấu hình khác nhau. Truyền ZoneId/Clock tường minh.

### 22.8. Không lưu zone của lịch lặp

Một Instant cho lịch họp đầu tiên không đủ diễn đạt quy tắc “09:00 mỗi thứ Hai Paris”. Lưu giờ địa phương, quy tắc lịch, ZoneId và chính sách DST; tính các Instant cho từng lần.

### 22.9. Coi tzdb tương lai bất biến

Chính quyền có thể thay đổi quy định timezone. Các bản JDK/tzdb mới có thể thay đổi offset dự đoán cho lịch tương lai. Với lịch đặt trước lâu dài, cần chính sách tính lại/đối chiếu mốc đã chốt.

### 22.10. Dùng Instant để giải thích mọi loại ngày giờ

Instant mô tả timeline, không thay được LocalDate ngày sinh hoặc LocalTime giờ mở cửa. Bản thân Instant không giữ ngữ cảnh địa phương. Ngược lại, LocalDateTime không đủ để làm event timestamp toàn cầu.

### 22.11. Đo Duration từ hai LocalDateTime qua DST

LocalDateTime không chứa luật múi giờ; phép đo local không phải elapsed time trên timeline khi đổi offset. Dùng Instant hoặc zoned date-time đã resolve.

### 22.12. Dùng clock thật trong test logic thời gian

Gọi Instant.now() nhiều lần có thể gây test phụ thuộc thời gian thực, đổi ngày hoặc deadline. Dùng Clock.fixed và zone được chọn rõ cho unit test.

### 22.13. Coi múi giờ là chuyện format

Chuyển từ LocalDateTime sang Instant đòi quyết định **đúng zone/offset và DST**; chỉ chỉnh pattern hiển thị không tạo được thông tin thiếu.

### 22.14. Hiểu nhầm chi tiết leap second và độ chính xác

Instant dựa trên Java Time-Scale, có các chi tiết mô hình UTC-SLS và leap seconds; đừng đồng nhất mọi tính toán vật lý với một “đồng hồ UTC lý tưởng”. Với ứng dụng thông thường ISO Instant có Z là đủ, nhưng các hệ thống đo đạc/đồng bộ clock cần thêm chính sách và kiến thức nguồn thời gian.

## 23. Checklist kiểm thử

1. Dùng Clock.fixed để có mốc hiện tại cố định và deterministic.
2. Chọn ZoneId.of(...) tường minh, không phụ thuộc timezone của máy chạy.
3. Kiểm tra một Instant hiển thị ở nhiều zone mà vẫn toInstant() bằng nhau.
4. Kiểm tra một LocalDateTime khi gắn hai zone cho Instant khác nhau.
5. Test gap bằng ZoneRules.getValidOffsets trả rỗng và áp dụng chính sách nghiệp vụ.
6. Test overlap bằng hai offset hợp lệ và hai Instant khác nhau.
7. Test plusDays và plusHours qua 23/25 giờ DST.
8. Test parse payload có offset/ZoneId và payload thiếu zone theo contract API.
9. Test lưu/đọc DB/JSON về unit epoch, độ chính xác mili/nanosecond và ZoneId.
10. Test lịch tương lai khi tzdb được cập nhật và kỳ vọng DST policy không đổi.

## 24. Bài tập và đáp án

**Bài 1:** Hệ thống lưu ngày sinh 2001-05-03. Nên dùng Instant hay LocalDate?

*Đáp án:* LocalDate. Ngày sinh là ngày theo lịch, không nhất thiết có thời điểm tuyệt đối.

**Bài 2:** Cùng Instant 2024-06-01T00:00Z, Việt Nam và Paris hiển thị mấy giờ?

*Đáp án:* 07:00+07:00 ở Việt Nam và 02:00+02:00 tại Paris (mùa hè 2024).

**Bài 3:** Có thể coi ZoneOffset.of("+01:00") tương đương Europe/Paris không?

*Đáp án:* Không cho mọi ngày. Offset cố định không biết quy tắc DST của vùng.

**Bài 4:** LocalDateTime 2024-03-31T02:30 ở Paris có hợp lệ không?

*Đáp án:* Bản thân LocalDateTime hợp lệ, nhưng không có offset hợp lệ theo zone Europe/Paris lúc đó (gap). atZone mặc định chuyển thành 03:30; một hệ thống đặt lịch cần quyết định chính sách chấp nhận hay từ chối.

**Bài 5:** LocalDateTime 2024-10-27T02:30 ở Paris tương ứng mấy Instant?

*Đáp án:* Hai: 00:30Z với +02:00, và 01:30Z với +01:00.

**Bài 6:** Tại sao cộng 1 ngày có thể khác cộng 24 giờ?

*Đáp án:* Một ngày theo calendar có thể dài 23/25 giờ thực ở vùng đổi DST, trong khi 24 giờ timeline luôn là 24 giờ.

**Bài 7:** Khi client gửi "2024-06-01T09:30" mà không có offset, server có thể tự hiểu UTC không?

*Đáp án:* Không, trừ khi contract API quy định rõ. Nó chỉ là LocalDateTime; cần zone/offset trước khi quy về Instant.

**Bài 8:** Khi xác thực token hết hạn sau 90 phút, nên dùng LocalDateTime.now hay Instant.now(clock)?

*Đáp án:* Instant.now(clock) và cộng Duration.ofMinutes(90) diễn đạt deadline tuyệt đối rõ hơn.

**Bài 9:** Khi đổi múi giờ để hiển thị một event, nên dùng withZoneSameInstant hay withZoneSameLocal?

*Đáp án:* withZoneSameInstant để giữ mốc timeline đã xảy ra.

**Bài 10:** Tại sao phải test giờ mùa thu hai lần?

*Đáp án:* Vì local time trong overlap có thể diễn ra hai lần, có hai offset hợp lệ và hai Instant khác nhau; nếu bỏ chọn offset, lịch có thể chạy sai lần.

## Tài liệu chính thức còn được duy trì

- Oracle Java SE 25 — LocalDate: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- Oracle Java SE 25 — LocalTime: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalTime.html
- Oracle Java SE 25 — LocalDateTime: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html
- Oracle Java SE 25 — Instant: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html
- Oracle Java SE 25 — ZoneId, ZoneOffset: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneOffset.html
- Oracle Java SE 25 — ZonedDateTime: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html
- Oracle Java SE 25 — OffsetDateTime: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html
- Oracle Java SE 25 — ZoneRules: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html
- Oracle Java SE 25 — Clock: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html
- Oracle Java SE 25 — Duration và Period: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Period.html
- Oracle Java SE 25 — DateTimeFormatter: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html

**Kết luận:** LocalDate và LocalTime biểu diễn các giá trị lịch/đồng hồ; LocalDateTime gom cả hai nhưng chưa chỉ ra một thời điểm tuyệt đối. Instant là mốc timeline; ZoneId mang luật khu vực, ZoneOffset là chênh lệch cụ thể; ZonedDateTime kết hợp các thông tin để quy về Instant. Chọn kiểu dữ liệu từ **ngữ nghĩa nghiệp vụ**, kiểm tra DST ở điểm gắn zone và test với Clock cố định để hạn chế lỗi thời gian giữa các môi trường.
