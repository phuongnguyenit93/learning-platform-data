# Chọn dữ liệu ngày thuần túy, giờ địa phương hay thời điểm khi lưu trữ

## 1. Kiểu lưu trữ phải giữ ý nghĩa của dữ liệu

Một trường có tên `date` có thể là ngày sinh, giờ mở cửa, lịch hẹn tại một thành phố hoặc thời điểm một sự kiện đã xảy ra. Những dữ liệu ấy không có cùng hợp đồng dù đều được trình bày bằng chữ số ngày giờ.

Trước khi chọn cột cơ sở dữ liệu hay cách viết JSON, hãy trả lời: **dữ liệu mô tả điều gì và có cần xác định một thời điểm duy nhất trên trục thời gian không?**

| Ý nghĩa | Kiểu Java phù hợp ban đầu | Thông tin được giữ |
|---|---|---|
| Ngày sinh, ngày kế toán, ngày được chọn không có giờ | `LocalDate` | Năm-tháng-ngày |
| Giờ mở cửa trong ngày | `LocalTime` | Giờ-phút-giây, không có ngày/vùng |
| Ngày-giờ được nhìn trên đồng hồ tại một địa phương | `LocalDateTime` | Ngày và giờ, chưa có vùng/offset |
| Một sự kiện đã xảy ra hoặc hạn tại một thời điểm xác định | `Instant` | Điểm trên trục thời gian |
| Ngày-giờ kèm độ lệch UTC của dữ liệu nguồn | `OffsetDateTime` | Ngày-giờ và offset |
| Ngày-giờ cần giữ múi giờ vùng | `ZonedDateTime`, hoặc mô hình tách các trường cần thiết | Ngày-giờ, vùng và offset tương ứng |

Tên kiểu giúp bộc lộ ý nghĩa trong mã. Hợp đồng lưu trữ/trao đổi vẫn phải nêu rõ những thông tin ấy; chỉ có tên cột “timestamp” chưa đủ chứng minh hệ thống đang giữ đúng ngữ nghĩa.

## 2. Ngày thuần túy: đừng tạo giờ và múi giờ không có trong dữ liệu

Ngày sinh `2000-10-25` thường chỉ cần `LocalDate`. Nó không nói “một thời điểm tại nửa đêm” và không có múi giờ để chuyển qua chuyển lại.

Nếu tự thêm nửa đêm Việt Nam rồi đổi thành UTC, ngày UTC là 24/10. Một phía khác chỉ lấy phần ngày từ UTC có thể làm ngày sinh biến thành ngày trước đó.

Đây không phải lỗi phép đổi múi giờ. Bạn đã biến một ngày thuần túy thành thời điểm bằng cách thêm thông tin mà dữ liệu nguồn không chứa, rồi bỏ lại phần giờ ở nơi khác.

Đối với lưu trữ, chọn cách biểu diễn ngày không có giờ theo khả năng của hệ thống; đối với trao đổi, chuỗi như `2000-10-25` có thể được quy định là ngày ISO. Không gắn hậu tố `Z` vào một ngày chỉ để mọi trường trông giống timestamp.

Nếu bài toán là “còn hiệu lực hết ngày 25/10 tại vùng X”, ngày và vùng X cùng tham gia xác định ranh giới thời điểm. Đó là một quyết định nghiệp vụ bổ sung, khác với tự động coi mọi LocalDate là UTC nửa đêm.

## 3. Giờ địa phương: giữ ý định theo đồng hồ nhưng không giả vờ đã có thời điểm

### LocalTime cho một giờ trong ngày

`09:00` có thể là giờ mở cửa thường lệ. `LocalTime` giữ phần giờ, nhưng để tính lần mở cửa cụ thể cần thêm ngày, vùng và lịch hoạt động. Không lấy một ngày tùy ý như 01/01/1970 để cất giờ rồi vô tình khiến ngày ấy tham gia phép so sánh.

Một lịch hoạt động có thể cần thứ trong tuần, ngày nghỉ, giờ đóng cửa hoặc ca qua nửa đêm. Chỉ lưu `LocalTime` là một thành phần, không phải đã mô hình xong toàn bộ lịch lặp.

### LocalDateTime cho ngày-giờ chưa có vùng

Chuỗi `2026-10-25T09:00` mô tả ngày-giờ địa phương. Nó chưa đủ để nói sự kiện xảy ra cùng lúc ở đâu trên thế giới.

Nếu gắn vùng Việt Nam, kết quả là `2026-10-25T02:00:00Z`. Nếu diễn giải cùng các trường theo UTC, kết quả là `2026-10-25T09:00:00Z`. Chênh lệch đến từ ngữ cảnh được thêm vào, không phải từ việc LocalDateTime tự giữ một vùng ẩn.

Nếu hệ thống lưu một LocalDateTime với quy ước “các trường này là UTC”, phải công bố và thực thi quy ước đó nhất quán. Bản thân kiểu không ngăn một nơi gọi diễn giải nhầm theo múi giờ máy chủ. Khi dữ liệu thật sự là thời điểm, dùng kiểu biểu đạt thời điểm ở lớp nghiệp vụ giúp tránh phụ thuộc quy ước ngầm.

## 4. Thời điểm: giữ một mốc, trình bày theo vùng khi cần

Một sự kiện “đã nhận yêu cầu lúc nào” có thể được lưu dưới dạng `Instant`. Một mốc như `2026-10-24T18:30:00Z` có thể được trình bày:

```text
UTC:               2026-10-24 18:30
Việt Nam:          2026-10-25 01:30
```

Giữ thời điểm làm nguồn cho phép so sánh trước/sau và tính chênh lệch nhất quán. Ngày địa phương dùng cho báo cáo cần được suy ra theo múi giờ báo cáo đã chọn.

Nếu cần biết vùng ban đầu của người dùng, một Instant đơn lẻ không giữ thông tin đó. Có thể lưu thêm mã vùng hoặc offset nguồn theo yêu cầu. Ngược lại, chỉ giữ `+07:00` cũng không nói đầy đủ quy tắc của một vùng địa lý qua lịch sử/tương lai.

Không coi offset và ZoneId là cùng một loại dữ liệu:

- Offset là độ lệch cụ thể như `+07:00`.
- ZoneId vùng như `Asia/Ho_Chi_Minh` tham chiếu bộ quy tắc theo thời gian.

Khi bên nhận chỉ cần một mốc toàn cục, hợp đồng Instant/UTC có thể đủ. Khi cần tái tạo ngữ cảnh nguồn hoặc lịch hẹn tương lai theo vùng, hãy giữ đúng phần thông tin bổ sung ấy.

## 5. Lịch hẹn tương lai cần chính sách khi giờ địa phương không xác định duy nhất

Lưu `LocalDateTime` cùng `ZoneId` thể hiện ý định “09:00 tại vùng này”. Nhưng ở vùng có DST, có thời gian địa phương không tồn tại hoặc xuất hiện hai lần.

`zone.getRules().getValidOffsets(localDateTime)` cho biết các offset hợp lệ:

| Số offset thường gặp | Tình huống | Quyết định cần có |
|---|---|---|
| 0 | Khoảng giờ bị bỏ qua (gap) | Từ chối hoặc dời theo quy tắc đã công bố |
| 1 | Ngày-giờ xác định bình thường | Tạo thời điểm từ offset ấy |
| 2 | Khoảng giờ lặp lại (overlap) | Chọn lần sớm/muộn hoặc yêu cầu làm rõ |

Không chỉ gọi một phép gắn vùng có hành vi điều chỉnh mặc định rồi cho rằng dữ liệu luôn mang ý nghĩa người dùng muốn. Ví dụ chương trình dưới chọn chính sách đơn giản: **chỉ chấp nhận đúng một offset**, còn thiếu hoặc mơ hồ thì báo lỗi.

Dữ liệu quy tắc vùng có thể được cập nhật. Với lịch hẹn tương lai, cần quyết định cái gì là nguồn sự thật: giữ cố định Instant đã chốt, hay giữ ý định giờ địa phương/vùng và tính lại khi quy tắc đổi. Có thể lưu cả ý định và mốc đã phân giải cùng ngữ cảnh cần thiết, nhưng phải có chính sách xử lý khác biệt; lưu thêm trường không tự giải quyết xung đột.

## 6. Hợp đồng lưu trữ và trao đổi

Một số biểu diễn JSON minh họa, mỗi trường có ý nghĩa được quy định riêng:

```json
{
  "birthDate": "2000-10-25",
  "dailyOpeningTime": "09:00",
  "appointmentLocalDateTime": "2026-10-25T09:00",
  "appointmentZoneId": "Asia/Ho_Chi_Minh",
  "occurredAt": "2026-10-24T18:30:00Z"
}
```

Đây chỉ là ví dụ hình thức dữ liệu, không phải cấu hình serializer tự chạy. Hợp đồng cần xác định trường nào bắt buộc, quan hệ giữa các trường lịch hẹn và cách kiểm tra giá trị.

Với epoch số nguyên, phải công bố đơn vị: giây, mili giây hay cặp giây/phần lẻ. Một số không tự mang thông tin đơn vị; hiểu sai có thể tạo thời điểm khác hàng nghìn lần về khoảng cách từ epoch.

Với cơ sở dữ liệu, chọn kiểu cột dựa trên ngữ nghĩa và tài liệu của hệ quản trị/driver đang dùng. Không giả định mọi kiểu tên “timestamp with time zone” đều giữ nguyên mã ZoneId vùng, offset nguồn hoặc có cùng cách chuyển đổi. Nếu vùng là dữ liệu cần giữ, kiểm tra và lưu nó tường minh khi kiểu cột không bảo toàn.

Cần xác nhận bằng kiểm tra ghi/đọc qua tầng thật:

- Giá trị ngày thuần có giữ nguyên khi môi trường đổi múi giờ không?
- Thời điểm đọc lại có giữ cùng mốc không?
- Driver, session cơ sở dữ liệu hoặc ORM có tự dùng múi giờ mặc định không?
- Phần lẻ giữ được đến giây, mili giây, micro giây hay nano giây?
- ZoneId/offset cần giữ có còn sau vòng trao đổi không?

Không dùng một ví dụ thuần Java để khẳng định đã kiểm chứng mọi ánh xạ JDBC, ORM hoặc cơ sở dữ liệu.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `StorageMeaningDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Nó minh họa ý nghĩa dữ liệu và phân giải vùng, không mở kết nối cơ sở dữ liệu.

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StorageMeaningDemo {
    record AppointmentIntent(LocalDateTime localDateTime, ZoneId zone) {}

    static Instant resolveUnique(AppointmentIntent intent) {
        List<ZoneOffset> offsets = intent.zone().getRules()
                .getValidOffsets(intent.localDateTime());
        if (offsets.size() != 1) {
            throw new DateTimeException("local time is missing or ambiguous");
        }
        return ZonedDateTime.ofStrict(intent.localDateTime(),
                offsets.get(0), intent.zone()).toInstant();
    }

    public static void main(String[] args) {
        LocalDate birthday = LocalDate.parse("2000-10-25");
        LocalTime dailyOpening = LocalTime.parse("09:00");
        LocalDateTime appointment = LocalDateTime.parse("2026-10-25T09:00");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        System.out.println("dateOnly=" + birthday);
        System.out.println("timeOnly=" + dailyOpening);
        System.out.println("localDateTime=" + appointment);
        System.out.println("appointmentVietnam="
                + resolveUnique(new AppointmentIntent(appointment, vietnam)));
        System.out.println("appointmentUtc="
                + resolveUnique(new AppointmentIntent(
                        appointment, ZoneOffset.UTC)));

        Instant occurredAt = Instant.parse("2026-10-24T18:30:00Z");
        System.out.println("eventUtc="
                + occurredAt.atZone(ZoneOffset.UTC));
        System.out.println("eventVietnam=" + occurredAt.atZone(vietnam));
        System.out.println("eventRoundTrip="
                + occurredAt.equals(Instant.parse(occurredAt.toString())));

        Instant inventedMidnight = birthday.atStartOfDay(vietnam).toInstant();
        System.out.println("birthdayAfterUtcConversion="
                + inventedMidnight.atZone(ZoneOffset.UTC).toLocalDate());

        ZoneId newYork = ZoneId.of("America/New_York");
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        System.out.println("gapOffsetCount="
                + newYork.getRules().getValidOffsets(gap).size());
        System.out.println("overlapOffsetCount="
                + newYork.getRules().getValidOffsets(overlap).size());
        try {
            resolveUnique(new AppointmentIntent(overlap, newYork));
        } catch (DateTimeException e) {
            System.out.println("ambiguousAppointment=ERROR");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac StorageMeaningDemo.java
java StorageMeaningDemo
```

Kết quả đã kiểm chứng trên Zulu OpenJDK 24.0.2 với dữ liệu múi giờ của bản JDK đó:

```text
dateOnly=2000-10-25
timeOnly=09:00
localDateTime=2026-10-25T09:00
appointmentVietnam=2026-10-25T02:00:00Z
appointmentUtc=2026-10-25T09:00:00Z
eventUtc=2026-10-24T18:30Z
eventVietnam=2026-10-25T01:30+07:00[Asia/Ho_Chi_Minh]
eventRoundTrip=true
birthdayAfterUtcConversion=2000-10-24
gapOffsetCount=0
overlapOffsetCount=2
ambiguousAppointment=ERROR
```

`ERROR` là nhãn của chương trình khi chính sách `resolveUnique` từ chối giờ mơ hồ. Các ví dụ DST dựa trên bộ quy tắc vùng có trong môi trường chạy; khi đổi JDK/dữ liệu vùng, hãy kiểm tra các trường hợp chuyển tiếp liên quan.

Các dòng lịch hẹn cho thấy cùng ngày-giờ địa phương có thể thành hai Instant khác nhau nếu vùng khác. Hai dòng sự kiện lại cho thấy cùng một Instant có hai cách nhìn địa phương. Hai chiều này không được nhầm lẫn.

`birthdayAfterUtcConversion` cố ý minh họa lỗi thiết kế: gán nửa đêm để chuyển một ngày sinh rồi lấy ngày UTC khiến giá trị ngày đổi. Không dùng bước ấy trong cách lưu ngày sinh thực tế.

## 8. Những quyết định cần giữ trong mô hình dữ liệu

### Không có giá trị khác với một giá trị mặc định

Thiếu giờ không tự nghĩa là 00:00. Thiếu vùng không tự nghĩa là UTC hoặc vùng máy chủ. Nếu dữ liệu cho phép thiếu thành phần, mô hình trạng thái thiếu và quyết định bổ sung ở đúng nơi có ngữ cảnh.

### Độ chính xác là một phần của hợp đồng

Một kiểu Java hỗ trợ nano giây không bảo đảm đường lưu trữ giữ đến nano giây. Nếu cột chỉ giữ mili giây, phải chọn cách cắt/làm tròn và kiểm tra tác động lên so sánh, hạn dùng, khóa duy nhất hoặc thứ tự sự kiện. Hai sự kiện khác thời điểm có thể trở thành cùng timestamp sau khi giảm độ chính xác.

### Ngôn ngữ hiển thị không quyết định định dạng dữ liệu nguồn

Chuỗi `25/10/2026`, tên tháng tiếng Việt hay nhãn định dạng dài phục vụ người đọc. Giá trị nội bộ và hợp đồng trao đổi cần cú pháp được công bố rõ. Không lưu nguyên một nhãn giao diện rồi mong mọi môi trường đọc lại với đúng locale.

### Ngày địa phương khi báo cáo cần vùng báo cáo

Nếu lưu sự kiện bằng Instant nhưng muốn nhóm theo ngày làm việc tại một địa phương, chuyển bằng vùng của báo cáo trước khi lấy LocalDate. Lấy ngày UTC rồi đổi nhãn sang tiếng Việt không biến nhóm đó thành nhóm ngày Việt Nam.

## 9. Tự thực hành

Chọn cách biểu diễn cho từng trường hợp:

| Trường hợp | Lựa chọn có ý nghĩa |
|---|---|
| Ngày cấp trên giấy tờ không có giờ | LocalDate |
| Giờ mở cửa hằng ngày của chi nhánh | LocalTime, kèm vùng và lịch hoạt động ở mô hình lịch |
| Thời điểm máy chủ đã nhận một sự kiện | Instant, có thể thêm ngữ cảnh nguồn nếu cần |
| Lịch hẹn 09:00 tại New York | Ngày-giờ địa phương + ZoneId + chính sách gap/overlap và chốt thời điểm |
| Thời gian nguồn gửi kèm offset cần được giữ lại | OffsetDateTime hoặc các trường trao đổi giữ được cả mốc và offset |

Sau đó thử đổi vùng lịch hẹn trong chương trình mà giữ nguyên LocalDateTime, rồi đổi vùng hiển thị sự kiện mà giữ nguyên Instant. Giải thích vì sao thao tác đầu đổi mốc thời gian, còn thao tác sau chỉ đổi cách nhìn cùng mốc.

Tham khảo: [LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html), [LocalTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html) và [ZoneRules — getValidOffsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime)) trong Java SE 21.
