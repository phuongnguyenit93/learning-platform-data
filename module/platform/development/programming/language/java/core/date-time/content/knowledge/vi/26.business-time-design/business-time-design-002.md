# Phân biệt sự kiện đã xảy ra với lịch hẹn tương lai

## 1. Một dữ liệu ghi nhận sự thật, một dữ liệu giữ ý định

“Giao dịch đã xảy ra lúc nào?” cần một mốc trên trục thời gian. “Khách muốn gặp lúc 09:00 tại Berlin” cần giữ một ý định theo đồng hồ địa phương và địa điểm. Nếu lưu cả hai bằng một trường không rõ nghĩa như `timestamp`, mã xử lý dễ sửa nhầm lịch sử hoặc làm trôi giờ hẹn.

Sự phân biệt nằm ở **ý nghĩa nghiệp vụ**, không chỉ ở việc giá trị nhỏ hơn hay lớn hơn `now`. Một hạn chót tương lai có thể cố định theo UTC; một cuộc hẹn đã qua vẫn có dữ liệu lịch dự kiến và có thể chưa từng diễn ra.

| Câu hỏi | Mô hình thường phù hợp |
| --- | --- |
| Một việc đã thực sự xảy ra khi nào? | `Instant occurredAt` |
| Hệ thống nhận được thông tin khi nào? | `Instant receivedAt` hoặc `recordedAt` |
| Hẹn theo giờ tại một địa điểm | `LocalDateTime` + `ZoneId` + chính sách phân giải |
| Một sự kiện tương lai diễn ra đồng thời toàn cầu | `Instant` làm mốc đã chốt |
| Mỗi tuần vào 09:00 tại địa điểm | Quy tắc lặp + giờ địa phương + vùng |

## 2. Sự kiện đã xảy ra: giữ mốc thực tế

`Instant` biểu diễn một thời điểm không phụ thuộc cách hiển thị ở từng múi giờ. Cùng một lần thanh toán có thể được xem là 09:00 ở Berlin và 14:00 ở Việt Nam, nhưng vẫn là một mốc duy nhất. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Khi cần bối cảnh, có thể giữ thêm vùng, độ lệch hoặc chuỗi thời gian nguồn. Những trường đó phục vụ hiển thị hoặc truy vết; không được dùng việc đổi múi giờ người xem để sửa `occurredAt`.

Phân biệt thời điểm xảy ra và thời điểm nhận. Một thiết bị gửi dữ liệu chậm, một hàng đợi bị nghẽn hoặc một hệ thống đồng bộ sau khi mất mạng có thể làm `receivedAt` khác `occurredAt`. Dùng thời điểm nhận thay cho thời điểm xảy ra có thể làm sai báo cáo.

`Instant` cũng không chứng minh đồng hồ nguồn chính xác. Trong hệ thống phân tán, không nên coi timestamp từ các máy khác nhau là một thứ tự nhân quả hoàn hảo; nếu cần sắp thứ tự chắc chắn, bổ sung quy tắc thứ tự hoặc định danh thích hợp.

## 3. Cuộc hẹn tương lai: xác định điều phải được bảo toàn

Một cuộc hẹn “09:00 ngày 1/6/2030 tại Berlin” có ba thành phần gốc: ngày giờ địa phương, vùng `Europe/Berlin`, và quy tắc xử lý nếu giờ không tồn tại hoặc xuất hiện hai lần.

Chuyển thành `Instant` cho phép lập lịch thực thi hoặc so sánh với mốc hiện tại. Tuy nhiên, nếu chỉ giữ `Instant` rồi bỏ thông tin gốc, hệ thống có thể mất ý định “09:00 tại Berlin” khi có thay đổi quy tắc vùng.

Ngược lại, một buổi phát sóng được chốt “bắt đầu đúng 07:00Z ở mọi nơi” có thể chọn `Instant` là dữ liệu quyết định. Khi thay quy tắc vùng, người ở một địa phương có thể thấy giờ hiển thị khác đi; thời điểm bắt đầu vẫn giữ nguyên.

Cần chọn rõ một trong hai hợp đồng chính:

- **Giữ giờ địa phương:** khi quy tắc vùng thay đổi, tính lại thời điểm từ ngày giờ và vùng theo quy trình đã thống nhất.
- **Giữ thời điểm đã chốt:** giữ nguyên `Instant`; giờ hiển thị địa phương có thể đổi theo quy tắc vùng.

Không tự suy ra hợp đồng này từ tên kiểu hoặc từ việc dữ liệu “ở tương lai”.

## 4. Tại sao vùng khác với độ lệch?

`ZoneOffset` như `+02:00` chỉ là độ lệch tại một cách diễn giải. `ZoneId` như `Europe/Berlin` truy cập tập quy tắc có thể thay đổi theo ngày và theo các quyết định cập nhật múi giờ.

Khi phân giải từ `Instant` sang giờ địa phương, quy tắc vùng chọn một độ lệch cho mốc đó. Khi đi từ `LocalDateTime` sang thời điểm, có thể gặp ba trường hợp: một độ lệch hợp lệ, không có độ lệch do nhảy giờ, hoặc hai độ lệch do lùi giờ.

Vì vậy, “09:00 +02:00” và “09:00 tại Berlin” không phải hai cách ghi luôn tương đương. Hẹn một ngày mùa đông có thể có độ lệch khác. [ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

Nếu giờ đặt rơi vào khoảng thiếu hoặc trùng, có thể từ chối, đề nghị giờ khác, hoặc yêu cầu chọn lần xuất hiện. Điều cần tránh là để mặc định của `atZone` vô tình trở thành chính sách chưa được sản phẩm quyết định.

## 5. Chương trình minh chứng: đổi cách nhìn khác với dời lịch

Ví dụ dưới đây lưu một sự kiện đã xảy ra và một lịch hẹn có ý định địa phương. Lịch hẹn chỉ được tự phân giải khi có đúng một độ lệch hợp lệ.

Lưu thành `EventAndPlanDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Objects;

public class EventAndPlanDemo {
    record ObservedEvent(Instant occurredAt, Instant receivedAt) {
        ObservedEvent {
            Objects.requireNonNull(occurredAt, "occurredAt");
            Objects.requireNonNull(receivedAt, "receivedAt");
        }
    }

    record Appointment(LocalDateTime localStart, ZoneId zone) {
        Appointment {
            Objects.requireNonNull(localStart, "localStart");
            Objects.requireNonNull(zone, "zone");
        }

        Instant resolve() {
            List<ZoneOffset> offsets = zone.getRules().getValidOffsets(localStart);
            if (offsets.size() != 1) {
                throw new IllegalArgumentException("Choose a policy for gap or overlap");
            }
            return ZonedDateTime.ofStrict(localStart, offsets.get(0), zone).toInstant();
        }
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ObservedEvent event = new ObservedEvent(
                Instant.parse("2025-06-01T07:00:00Z"),
                Instant.parse("2025-06-01T07:00:30Z"));

        System.out.println("eventBerlin=" + event.occurredAt().atZone(berlin));
        System.out.println("eventVietnam=" + event.occurredAt().atZone(vietnam));
        System.out.println("eventInstant=" + event.occurredAt());
        System.out.println("receiveDelaySeconds="
                + Duration.between(event.occurredAt(), event.receivedAt()).toSeconds());

        Appointment original = new Appointment(
                LocalDateTime.of(2030, 6, 1, 9, 0), berlin);
        Instant firstResolution = original.resolve();
        Appointment rescheduled = new Appointment(
                original.localStart().plusHours(1), original.zone());

        System.out.println("plannedInstant=" + firstResolution);
        System.out.println("rescheduledInstant=" + rescheduled.resolve());
        System.out.println("originalLocal=" + original.localStart());
        System.out.println("originalSnapshot=" + firstResolution);

        Instant fixedGlobalStart = Instant.parse("2030-06-01T07:00:00Z");
        System.out.println("globalBerlin=" + fixedGlobalStart.atZone(berlin));
        System.out.println("globalVietnam=" + fixedGlobalStart.atZone(vietnam));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 EventAndPlanDemo.java
java EventAndPlanDemo
```

Stdout với dữ liệu IANA có quy tắc Berlin mùa hè là `+02:00` cho các ngày trong ví dụ:

```text
eventBerlin=2025-06-01T09:00+02:00[Europe/Berlin]
eventVietnam=2025-06-01T14:00+07:00[Asia/Ho_Chi_Minh]
eventInstant=2025-06-01T07:00:00Z
receiveDelaySeconds=30
plannedInstant=2030-06-01T07:00:00Z
rescheduledInstant=2030-06-01T08:00:00Z
originalLocal=2030-06-01T09:00
originalSnapshot=2030-06-01T07:00:00Z
globalBerlin=2030-06-01T09:00+02:00[Europe/Berlin]
globalVietnam=2030-06-01T14:00+07:00[Asia/Ho_Chi_Minh]
```

Hai dòng hiển thị sự kiện không tạo hai lần xảy ra khác nhau. Dời cuộc hẹn từ 09:00 sang 10:00 mới làm thay đổi ý định và mốc dự kiến. Biến `firstResolution` giữ kết quả phân giải ban đầu; nó không tự cập nhật khi tạo bản lịch mới.

Kiểm tra `getValidOffsets` giúp nhận diện lúc cần chính sách. Nó không chọn chính sách thay phía gọi. [ZoneRules.getValidOffsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))

## 6. Cập nhật quy tắc múi giờ cần một quyết định, không phải sửa dữ liệu ngầm

Quy tắc vùng chịu ảnh hưởng quyết định hành chính và có thể được cập nhật. Một `LocalDateTime` cùng `ZoneId` có thể được phân giải khác khi bộ quy tắc thay đổi; dữ liệu tương lai là nơi sự khác biệt này thường có ý nghĩa lập lịch.

Với hợp đồng giữ giờ địa phương, có thể rà lại các lịch chưa diễn ra, tính mốc mới và lưu việc đổi lịch theo quy trình nghiệp vụ. Với hợp đồng giữ thời điểm, không được đổi mốc chỉ vì bộ quy tắc mới làm thay giờ địa phương hiển thị.

Với sự kiện đã xảy ra, không tái tính `occurredAt` từ một giờ địa phương bằng quy tắc mới rồi ghi đè lịch sử. Nếu cần giữ chính xác cách nguồn từng diễn giải thời gian, có thể lưu độ lệch đã dùng, chuỗi nguồn hoặc thông tin phiên bản quy tắc.

`ZoneRulesProvider.getVersions(zoneId)` có thể cho biết các phiên bản do provider cung cấp, nhưng chỉ lưu một nhãn phiên bản không bảo đảm mọi môi trường sau này còn chứa bộ quy tắc cũ. Yêu cầu tái hiện chính xác cần chiến lược lưu dữ liệu phù hợp. [ZoneRulesProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRulesProvider.html)

## 7. Lịch dự kiến và sự kiện thực tế cần trường riêng

Một cuộc hẹn có `plannedStart`, nhưng khi khách đến có thể sinh `actualStartedAt`; lúc kết thúc có `actualEndedAt`. Các thời điểm thực tế không nhất thiết trùng lịch dự kiến. Việc hủy hẹn cũng không tạo một sự kiện “đã diễn ra” chỉ vì ngày hẹn đã ở quá khứ.

Khi dời lịch, nên phân biệt bản lịch hiện tại với lịch sử thay đổi. Khi sửa dữ liệu sự kiện do nguồn báo sai, giữ nguồn gốc và lý do sửa theo nhu cầu truy vết. Đây là các thao tác nghiệp vụ khác với việc đổi múi giờ hiển thị.

Lịch lặp là một quy tắc sinh nhiều lần hẹn, không phải một `Instant` duy nhất. “Mỗi thứ Hai 09:00 ở Berlin” cần giữ thứ, giờ, vùng và cách xử lý ngoại lệ. Cộng đều 168 giờ từ một lần hẹn có thể làm trôi giờ địa phương qua đổi giờ mùa hè.

## 8. Tránh những mô hình gây mất ý nghĩa

- Chỉ lưu `LocalDateTime` cho sự kiện nhiều vùng: không đủ dữ liệu xác định cùng một thời điểm.
- Chỉ lưu độ lệch của hôm nay cho mọi cuộc hẹn tương lai: bỏ qua quy tắc vùng theo ngày.
- Chỉ giữ `Instant` cho lịch phải bảo toàn giờ địa phương mà không lưu ý định gốc.
- Giữ cả giờ địa phương, vùng và thời điểm nhưng không nói trường nào quyết định khi chúng mâu thuẫn.
- Đổi trạng thái lịch thành “đã xảy ra” chỉ dựa trên `scheduledAt < now`.

Không cần mọi mô hình đều lưu mọi trường. Chọn thông tin gốc, thông tin tính ra, chính sách cập nhật và tên trường rõ ràng. Các tên `occurredAt`, `receivedAt`, `scheduledLocal`, `scheduleZone`, `resolvedStart` giúp tránh nhập nhằng hơn một trường `time` chung.

## 9. Tự thực hành

1. Một thanh toán được ghi nhận ở UTC và hiển thị cho hai vùng: trường nào phải giữ nguyên?
2. Một lớp học được yêu cầu luôn bắt đầu 09:00 tại địa điểm: cần giữ gì ngoài mốc đã phân giải?
3. Một buổi trực tuyến bắt đầu cùng lúc toàn cầu: có thể dùng `Instant` làm dữ liệu quyết định dù ở tương lai không?
4. Thiết bị gửi sự kiện chậm hai phút: vì sao cần tách thời điểm xảy ra và thời điểm nhận?

Đối chiếu: (1) thời điểm thực tế; (2) ngày giờ địa phương, vùng và chính sách; (3) có, khi hợp đồng giữ thời điểm; (4) hai mốc phản ánh hai sự việc khác nhau và phục vụ các phép phân tích khác nhau.