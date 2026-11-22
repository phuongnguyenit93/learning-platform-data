# Ngày sinh, ngày hết hạn và lịch hẹn cần các kiểu thời gian khác nhau

## 1. Chọn kiểu từ câu hỏi nghiệp vụ

Ba dữ liệu đều có vẻ “liên quan đến ngày giờ”, nhưng trả lời ba câu hỏi khác nhau: người đó sinh vào ngày nào, quyền sử dụng chấm dứt khi nào, và cuộc hẹn diễn ra lúc nào theo đồng hồ ở đâu. Dùng cùng một kiểu cho cả ba thường khiến hệ thống phải tự đoán phần thông tin còn thiếu.

Kiểu thời gian là một phần của hợp đồng dữ liệu. Chọn kiểu đúng giúp những phép toán không phù hợp trở nên khó viết hơn, đồng thời làm rõ khi nào cần múi giờ, thời lượng hoặc quy tắc lịch.

| Yêu cầu | Mô hình thường phù hợp |
| --- | --- |
| Ngày sinh đầy đủ | `LocalDate` |
| Ngày kỷ niệm chỉ cần tháng/ngày | `MonthDay` |
| Hết hạn sau một thời lượng, ở cùng một thời điểm toàn cầu | `Instant` cho mốc, `Duration` cho lượng |
| Có hiệu lực đến hết một ngày tại vùng nghiệp vụ | `LocalDate` và `ZoneId`, cộng quy tắc ranh giới |
| Hết hạn chỉ ghi tháng/năm | `YearMonth`, rồi quy tắc diễn giải |
| Hẹn 09:00 ngày cụ thể tại một địa điểm | `LocalDateTime` và `ZoneId`, phân giải thành thời điểm |

Bảng là điểm khởi đầu; cùng cụm từ “ngày hết hạn” vẫn có thể cần mô hình khác nhau tùy ý nghĩa đã được thống nhất.

## 2. Ngày sinh: một ngày lịch, không phải nửa đêm UTC

`LocalDate` giữ năm, tháng, ngày mà không có giờ hoặc múi giờ. Đó thường là dữ liệu gốc cần lưu cho ngày sinh. Không cần tự tạo `2000-04-10T00:00Z`: khi hiển thị ở vùng có độ lệch âm, thời điểm giả đó có thể thành ngày 9/4, làm sai dữ liệu ngày sinh.

Muốn tính tuổi theo ngày lịch, trước hết xác định ngày “hôm nay” theo vùng nghiệp vụ, kiểm tra ngày sinh không ở tương lai, rồi tính số năm lịch trọn vẹn. Không lấy chênh lệch mili giây chia cho 365 ngày: năm có độ dài khác nhau.

`MonthDay` chỉ đủ để so khớp dịp kỷ niệm; bỏ năm sinh sẽ làm mất thông tin tính tuổi. Với ngày sinh 29/2, cách xác định dịp kỷ niệm trong năm thường cần chính sách riêng; không coi một phép điều chỉnh ngày mặc định là toàn bộ quy tắc nghiệp vụ. [LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html)

## 3. Hết hạn: chấm dứt tại một thời điểm hay sau một ngày?

### Hết hạn sau 15 phút

Đối với một mã có hiệu lực 15 phút từ khi phát hành, mô hình tự nhiên là `issuedAt: Instant`, `ttl: Duration`, `expiresAt: Instant`. Mọi nơi so sánh cùng một thời điểm hết hạn; múi giờ chỉ cần khi hiển thị.

Chốt ranh giới trước: ví dụ hiệu lực trong khoảng `[issuedAt, expiresAt)`, nghĩa là đúng `expiresAt` đã hết hạn. Khi đó điều kiện là `!now.isBefore(expiresAt)`, thay vì chỉ `now.isAfter(expiresAt)`, vốn bỏ sót đúng điểm bằng nhau. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

### Có giá trị đến hết ngày 9/4 tại một vùng

Nếu sản phẩm nói “có hiệu lực đến hết ngày 9/4 theo giờ Việt Nam”, dữ liệu gốc là một ngày và vùng quy định. Có thể biểu diễn mốc hết hiệu lực bằng **đầu ngày kế tiếp** tại vùng đó, rồi so sánh theo `Instant`.

Không gán cuối ngày là `23:59:59`: dữ liệu có phần lẻ giây sẽ làm xuất hiện khoảng hở hoặc sai độ chính xác. Không mặc định một ngày địa phương luôn dài 24 giờ. `atStartOfDay(zone)` chọn thời điểm hợp lệ sớm nhất của ngày theo quy tắc vùng, nên phù hợp hơn việc cộng một số giây cố định.

### Chỉ ghi tháng và năm

Nếu đầu vào thật sự chỉ có tháng/năm, dùng `YearMonth` thay vì tự gán ngày 1 hoặc một ngày giả. Sau đó quy định rõ quyền sử dụng kết thúc đầu tháng kế tiếp hay ở ranh giới nào khác, theo vùng nào. Kiểu dữ liệu không tự quyết định quy tắc còn thiếu.

## 4. Lịch hẹn: giờ địa phương và vị trí

`LocalDateTime.of(2025, 4, 10, 9, 0)` có nghĩa “09:00 ngày 10/4”, nhưng chưa xác định thời điểm toàn cầu. 09:00 tại Thành phố Hồ Chí Minh khác 09:00 tại Berlin. Thêm `ZoneId` để áp dụng quy tắc vùng. [LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)

Ở nơi có đổi giờ mùa hè, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Vì vậy, lúc nhận lịch hẹn phải xác định cách xử lý:

- Không có độ lệch hợp lệ: từ chối giờ đó hoặc đề xuất một giờ khác theo chính sách.
- Có một độ lệch hợp lệ: phân giải bình thường.
- Có hai độ lệch hợp lệ: yêu cầu chọn lần đầu/lần sau, hoặc áp dụng chính sách đã công bố.

`atZone` có hành vi mặc định cho các trường hợp này; không nên để một lựa chọn vô tình thay cho ý định của người đặt lịch. `ZoneOffset` cố định như `+01:00` cũng không thay được quy tắc của một vùng như `Europe/Berlin`. [ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

## 5. Chương trình minh chứng ba hợp đồng

Ví dụ dưới đây chọn chính sách lịch hẹn nghiêm ngặt: chỉ tự phân giải khi giờ địa phương có đúng một độ lệch. Các trường hợp thiếu hoặc trùng giờ bị từ chối để phía gọi xử lý.

Lưu thành `BusinessTimeDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class BusinessTimeDemo {
    static int calendarAge(LocalDate birthDate, LocalDate today) {
        if (birthDate.isAfter(today)) {
            throw new IllegalArgumentException("Birth date is in the future");
        }
        return Period.between(birthDate, today).getYears();
    }

    static boolean expired(Instant now, Instant expiresAt) {
        return !now.isBefore(expiresAt);
    }

    static Instant endExclusive(LocalDate validThrough, ZoneId zone) {
        return validThrough.plusDays(1).atStartOfDay(zone).toInstant();
    }

    static Instant appointment(LocalDateTime local, ZoneId zone) {
        List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
        if (offsets.size() != 1) {
            throw new IllegalArgumentException("Local time requires an explicit policy");
        }
        return ZonedDateTime.ofStrict(local, offsets.get(0), zone).toInstant();
    }

    public static void main(String[] args) {
        LocalDate birthDate = LocalDate.of(2000, 4, 10);
        System.out.println("ageBeforeBirthday="
                + calendarAge(birthDate, LocalDate.of(2025, 4, 9)));
        System.out.println("ageOnBirthday="
                + calendarAge(birthDate, LocalDate.of(2025, 4, 10)));

        Instant issuedAt = Instant.parse("2025-04-09T10:00:00Z");
        Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));
        System.out.println("expiresAt=" + expiresAt);
        System.out.println("expiredBefore="
                + expired(expiresAt.minusNanos(1), expiresAt));
        System.out.println("expiredExactly=" + expired(expiresAt, expiresAt));

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        System.out.println("dayCutoff="
                + endExclusive(LocalDate.of(2025, 4, 9), vietnam));
        System.out.println("appointmentInstant="
                + appointment(LocalDateTime.of(2025, 4, 10, 9, 0), vietnam));

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        try {
            appointment(LocalDateTime.of(2025, 3, 30, 2, 30), berlin);
        } catch (IllegalArgumentException ex) {
            System.out.println("gapRejected");
        }
        try {
            appointment(LocalDateTime.of(2025, 10, 26, 2, 30), berlin);
        } catch (IllegalArgumentException ex) {
            System.out.println("overlapRejected");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 BusinessTimeDemo.java
java BusinessTimeDemo
```

Stdout với dữ liệu múi giờ IANA tương ứng các quy tắc năm 2025 trong ví dụ:

```text
ageBeforeBirthday=24
ageOnBirthday=25
expiresAt=2025-04-09T10:15:00Z
expiredBefore=false
expiredExactly=true
dayCutoff=2025-04-09T17:00:00Z
appointmentInstant=2025-04-10T02:00:00Z
gapRejected
overlapRejected
```

Mốc `dayCutoff` là 00:00 ngày 10/4 ở Việt Nam, tương ứng 17:00 UTC ngày 9/4. Nó không đổi ý nghĩa “hết ngày 9/4”; đó là cùng ranh giới được biểu diễn trên trục thời gian.

`calendarAge` minh họa số năm lịch trọn vẹn cho ngày sinh thông thường. Quy tắc tuổi đặc biệt, nhất là trường hợp 29/2, phải được xác định riêng nếu ứng dụng có yêu cầu cụ thể. `endExclusive` cũng giả định có thể biểu diễn ngày kế tiếp; tại biên `LocalDate.MAX`, cần từ chối hoặc có quy tắc khác.

## 6. Dữ liệu nào là gốc khi quy tắc múi giờ thay đổi?

Với một sự kiện đã xảy ra, `Instant` thường là mốc gốc để biết chính xác thứ tự thời gian; có thể lưu vùng/độ lệch để phục vụ hiển thị hoặc truy vết.

Với một cuộc hẹn tương lai “09:00 tại Berlin”, ý định gốc có thể là giờ địa phương và vùng. Nếu quy tắc múi giờ được cập nhật, cần quyết định giữ 09:00 địa phương hay giữ nguyên thời điểm đã chốt. Hai lựa chọn có thể cho hai kết quả khác nhau.

Một mô hình có thể giữ cả `localDateTime`, `zoneId`, `resolvedInstant` và lựa chọn khi trùng giờ, nhưng phải ghi rõ trường nào quyết định và khi nào tính lại. Lưu nhiều trường mà không có quy tắc đồng bộ chỉ tạo thêm mâu thuẫn.

Lịch lặp hằng tuần cũng không nên tạo toàn bộ tương lai bằng cách cộng `Duration.ofDays(7)` nếu yêu cầu là cùng giờ địa phương. Cần giữ quy tắc lặp và phân giải từng lần theo vùng.

## 7. Đưa hợp đồng vào tên trường và ranh giới hệ thống

Tên `date`, `time`, `timestamp` chung chung dễ che mất ý nghĩa. Những tên như `birthDate`, `validThroughDate`, `expiresAt`, `appointmentLocal` và `appointmentZone` cho biết quy tắc cần dùng.

Với API và cơ sở dữ liệu, chọn định dạng/kiểu lưu phù hợp:

- Ngày sinh: giữ ngày ISO `uuuu-MM-dd` hoặc cột ngày, không tự đổi sang thời điểm.
- Mốc hết hạn toàn cầu: trao đổi thời điểm có UTC/độ lệch rõ ràng; kiểm tra độ chính xác khi lưu.
- Cuộc hẹn theo địa điểm: giữ vùng có định danh và thông tin địa phương cần bảo toàn.
- Tháng/năm hoặc tháng/ngày: đừng âm thầm bù những thành phần không có.

Lấy “bây giờ” qua `Clock` được truyền vào hoặc qua tham số để kiểm tra được ranh giới hết hạn, sinh nhật và ngày cuối năm. Không gọi nhiều đồng hồ khác nhau trong cùng một quyết định nếu điều đó có thể làm các phép kiểm tra dùng các mốc khác nhau.

## 8. Các câu hỏi để chốt thiết kế

1. Dữ liệu là ngày lịch, giờ địa phương, thời điểm, hay quy tắc lặp?
2. Thành phần nào do người dùng cung cấp; thành phần nào là quy tắc nghiệp vụ?
3. Ngày/giờ được hiểu theo vùng nào?
4. Ranh giới cuối có được tính là còn hiệu lực không?
5. Khi thiếu/trùng giờ, ngày 29/2 hoặc thay đổi quy tắc vùng, chính sách là gì?

Không cần lưu mọi kiểu cùng lúc. Chỉ giữ những thông tin cần bảo toàn và thực hiện chuyển đổi tại nơi có đủ quy tắc.

## 9. Tự thực hành

1. Thiết kế trường cho thẻ thành viên có ngày sinh và hiệu lực đến hết một ngày tại Việt Nam.
2. Đổi thời hạn mã xác thực từ 15 phút thành 24 giờ và giải thích vì sao vẫn dùng `Duration`.
3. Nhận lịch hẹn `2025-10-26T02:30` ở Berlin: cần thêm lựa chọn nào trước khi chốt `Instant`?
4. Với quyền sử dụng hết hạn đúng 10:15:00Z, kiểm tra 10:14:59.999999999Z, đúng 10:15:00Z và sau đó.

Đối chiếu: (1) `LocalDate` cho hai ngày, vùng và ranh giới hiệu lực riêng; (2) yêu cầu là thời lượng thực trôi; (3) chọn lần xuất hiện theo độ lệch phù hợp; (4) lần lượt còn hiệu lực, hết hiệu lực, hết hiệu lực theo khoảng cuối loại trừ đã chọn.