# Time zone policy — Chính sách múi giờ trong bảo mật logic nghiệp vụ

## 1. Vì sao múi giờ là một phần của quy tắc bảo mật?

Trong chương **Time Based Rules**, chính sách múi giờ xác định cách chuyển các yêu cầu như “mỗi ngày một lần”, “trước giờ đóng sổ” hoặc “hết ngày cuối cùng” thành điều kiện mà server có thể thực thi nhất quán.

Sai múi giờ có thể làm sai quyền lợi và quyết định nghiệp vụ:

- Người dùng đổi múi giờ hồ sơ để nhận lại khuyến mại trong cùng một chu kỳ.
- Một node chấp nhận giao dịch sau hạn vì dùng múi giờ hệ điều hành khác node còn lại.
- Giờ địa phương xuất hiện hai lần khi đổi giờ mùa hè khiến một tác vụ chi trả chạy hai lần.
- Client gửi ngày quá khứ hoặc một offset khác để làm yêu cầu trông như còn hạn.
- Worker xử lý lại một sự kiện bằng cấu hình múi giờ mới và tạo thêm tác dụng phụ.

Vấn đề cần bảo vệ là **bất biến nghiệp vụ theo thời gian**, không chỉ là định dạng ngày giờ. Chính sách đúng phải phối hợp với quyền theo đối tượng, state machine, transaction và idempotency.

Sau bài học, người đọc cần phân biệt được thời điểm tuyệt đối với ngày nghiệp vụ; chọn nguồn múi giờ có thẩm quyền; quy định rõ thời điểm hết hạn; và thiết kế kiểm tra để việc đổi cách hiển thị không tạo thêm quyền.

## 2. Phân biệt các khái niệm trước khi viết điều kiện

| Khái niệm | Ví dụ | Ý nghĩa trong thiết kế |
|---|---|---|
| Thời điểm tuyệt đối | `2026-11-21T17:00:00Z` | Một điểm trên trục thời gian; dùng so sánh hạn hiệu lực |
| UTC offset | `+07:00` | Độ lệch tại một thời điểm; không mô tả đầy đủ lịch sử và quy tắc của một vùng |
| Múi giờ có tên | `Asia/Ho_Chi_Minh` | Bộ quy tắc chuyển đổi giữa thời gian địa phương và thời điểm |
| Ngày địa phương | `2026-11-22` | Nhãn ngày theo một lịch; chưa tự xác định một thời điểm |
| Ngày giờ địa phương | `2026-11-22T09:00:00` | Chưa có offset hoặc múi giờ để xác định thời điểm duy nhất |
| Thời lượng | 30 phút kể từ khi phát hành | Khoảng thời gian trôi qua, không phải tên ngày trên lịch |
| Chu kỳ nghiệp vụ | Ngày nhận ưu đãi của chiến dịch | Đơn vị cấp quyền lợi do chính sách nghiệp vụ xác định |

Trong Java, các kiểu thường tương ứng là `Instant`, `ZoneOffset`, `ZoneId`, `LocalDate`, `LocalDateTime` và `Duration`. Không chọn kiểu chỉ vì nó dễ serialize; chọn theo ý nghĩa dữ liệu.

Một ngày sinh có thể phù hợp với `LocalDate`. Một thời điểm hết hạn thanh toán thường cần `Instant`. Một lịch mở cửa lặp lại theo giờ địa phương cần cả giờ trên lịch và múi giờ áp dụng.

### 2.1. “Lưu UTC” chưa đủ để định nghĩa nghiệp vụ

UTC giúp lưu và so sánh thời điểm nhất quán. Tuy nhiên, từ một thời điểm đơn lẻ không thể suy ra chiến dịch phải tính ngày theo múi giờ của cửa hàng, tenant hay người dùng.

Cần trả lời riêng hai câu hỏi:

1. **Quy tắc nào tạo ra khoảng hiệu lực?** Ví dụ: ngày 22/11 theo múi giờ chiến dịch.
2. **Khoảng đó tương ứng những thời điểm nào?** Ví dụ: từ `2026-11-21T17:00:00Z` đến trước `2026-11-22T17:00:00Z`.

Lưu các mốc UTC mà bỏ mất chính sách tạo ra chúng sẽ gây khó khăn khi giải thích, đối soát hoặc sửa lịch tương lai.

### 2.2. Múi giờ, ngôn ngữ và vị trí là các cấu hình khác nhau

`LANG=vi` hoặc locale tiếng Việt không có nghĩa mọi quy tắc phải dùng giờ Việt Nam. Người dùng có thể đọc tiếng Việt trong khi xử lý hợp đồng của một đơn vị ở nước khác.

Không tự suy ra múi giờ nghiệp vụ từ:

- Ngôn ngữ giao diện hoặc `Accept-Language`.
- IP hoặc vị trí hiện tại.
- Múi giờ thiết bị hoặc trình duyệt.
- Giá trị `Time-Zone` do client tự gửi.
- Múi giờ mặc định của JVM, container hoặc session cơ sở dữ liệu.

Các tín hiệu này có thể hỗ trợ hiển thị hoặc đề xuất cấu hình. Chúng không tự cấp quyền thay đổi cách tính hạn hoặc chu kỳ quyền lợi.

## 3. Xác định nguồn múi giờ có thẩm quyền

### 3.1. Gắn múi giờ với đối tượng sở hữu quy tắc

Không có một thứ tự ưu tiên phù hợp cho mọi hệ thống. Mỗi loại quy tắc cần chỉ rõ chủ thể quyết định:

| Quy tắc | Nguồn có thẩm quyền trong một thiết kế minh họa |
|---|---|
| Ưu đãi của chiến dịch | Múi giờ được phê duyệt và chốt trên chiến dịch |
| Giờ tiếp nhận hồ sơ của chi nhánh | Múi giờ cấu hình của chi nhánh liên quan |
| Ngày chốt số liệu của tenant | Cấu hình kế toán hoặc vận hành đã được phân quyền |
| OTP có hiệu lực 5 phút | Thời điểm phát hành và thời lượng; không phụ thuộc múi giờ hiển thị |
| Cuộc hẹn do người dùng tạo | Múi giờ cuộc hẹn được xác nhận khi tạo, theo quyền đặt lịch |
| Giờ hiển thị trên trang cá nhân | Sở thích hiển thị của người dùng |

Server phải lấy cấu hình từ đúng đối tượng mà người gọi có quyền thao tác. Không tin `tenantId`, `campaignId` hoặc `zoneId` trong body mà bỏ qua quan hệ sở hữu và phân quyền.

Một người có quyền đổi múi giờ hiển thị chưa chắc có quyền sửa múi giờ chiến dịch. Ngay cả quản trị viên cũng có thể chỉ được sửa cấu hình có hiệu lực tương lai, không được diễn giải lại các giao dịch đã chốt.

### 3.2. Chốt chính sách với đối tượng hoặc chu kỳ

Một chính sách có thể được mô tả như sau:

~~~text
Tên chính sách: campaign-local-day-v1
Đối tượng sở hữu: chiến dịch đã phê duyệt
Múi giờ nghiệp vụ: lấy từ phiên bản chính sách trên chiến dịch
Nguồn "hiện tại": nguồn thời gian phía server được hệ thống lựa chọn
Ngày nghiệp vụ: ngày của thời điểm quyết định trong múi giờ chiến dịch
Khoảng hiệu lực: gồm mốc bắt đầu, không gồm mốc kết thúc
Đổi múi giờ hồ sơ: chỉ thay hiển thị
Đổi chính sách chiến dịch: không hồi tố quyền lợi đã phát sinh
Ngày địa phương không tồn tại: không tự tạo chu kỳ nhận ưu đãi cho ngày đó
~~~

Các thành phần cần được quy định thêm nếu hệ thống hỗ trợ lịch theo giờ địa phương: cách xử lý giờ không tồn tại, giờ bị lặp, lịch chạy bù và thay đổi dữ liệu múi giờ.

Nếu thiếu múi giờ bắt buộc hoặc cấu hình không hợp lệ, không âm thầm dùng UTC hay múi giờ máy. Hãy báo lỗi cấu hình theo quy trình vận hành; việc đổi sang một múi giờ khác có thể kéo dài quyền sử dụng hoặc mở lại chu kỳ.

## 4. Chuyển ngày nghiệp vụ thành khoảng hiệu lực

### 4.1. Sử dụng khoảng nửa mở

Một lựa chọn dễ kiểm tra là:

~~~text
[startInclusive, endExclusive)

Hợp lệ khi:
    now >= startInclusive
    AND now < endExclusive
~~~

Với chiến dịch minh họa chạy trong ngày 22/11/2026 theo `Asia/Ho_Chi_Minh`:

~~~text
Bắt đầu địa phương: 2026-11-22T00:00:00+07:00
Kết thúc loại trừ:  2026-11-23T00:00:00+07:00

Bắt đầu UTC:       2026-11-21T17:00:00Z
Kết thúc UTC:      2026-11-22T17:00:00Z
~~~

| Thời điểm quyết định | Kết quả kiểm tra khoảng |
|---|---|
| `2026-11-21T16:59:59Z` | Chưa bắt đầu |
| `2026-11-21T17:00:00Z` | Được tính vào khoảng |
| `2026-11-22T16:59:59Z` | Còn trong khoảng |
| `2026-11-22T17:00:00Z` | Đã ra ngoài khoảng |

Bảng chỉ đánh giá thời gian. Người gọi vẫn cần đúng quyền, đúng trạng thái và chưa nhận quyền lợi của chu kỳ.

Tránh biểu diễn “hết ngày” bằng `23:59:59` hoặc `23:59:59.999`. Cách đó phụ thuộc độ chính xác của hệ thống và dễ bỏ sót phần thời gian cuối ngày. Mốc đầu ngày kế tiếp làm biên loại trừ rõ hơn.

### 4.2. Một ngày trên lịch khác một thời lượng 24 giờ

Hai điều kiện sau không tương đương:

~~~text
A. Hết hạn sau đúng 24 giờ kể từ khi tiếp nhận.
B. Hết hạn lúc bắt đầu ngày địa phương kế tiếp.
~~~

A là thời lượng. B là quy tắc lịch và phụ thuộc múi giờ. Trong Java, `Duration.ofDays(1)` biểu diễn đúng 24 giờ; không dùng nó để suy ra độ dài mọi ngày địa phương. [Java Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html)

Ngay cả tại nơi không đổi offset trong ví dụ, nếu tạo quyền lúc 23:50 thì “đến hết ngày” chỉ còn khoảng 10 phút, còn “24 giờ” kéo dài sang tối hôm sau. Vì vậy, phải chọn ý nghĩa trước khi chọn phép cộng.

Tương tự, “ba ngày làm việc” cần lịch ngày nghỉ và quy tắc nghiệp vụ; chỉ có một `ZoneId` chưa giải quyết được yêu cầu đó.

## 5. Giờ không tồn tại và giờ bị lặp

### 5.1. Không phải mọi giờ địa phương đều ánh xạ một-một

Khi quy tắc offset thay đổi, một giá trị ngày giờ địa phương có thể có:

- Một offset hợp lệ: ánh xạ thông thường.
- Không có offset hợp lệ: nằm trong khoảng giờ bị bỏ qua, gọi là **gap**.
- Hai offset hợp lệ trong trường hợp overlap thông thường: đồng hồ đã quay lại nên giờ đó xuất hiện hai lần.

Java cung cấp `ZoneRules.getValidOffsets(localDateTime)` để xem các offset hợp lệ, thay vì đoán từ một offset cố định. [Java ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html)

Ví dụ giả định một vùng chuyển đồng hồ từ 02:00 lên 03:00: 02:30 của ngày đó không tồn tại. Nếu đồng hồ quay từ 02:00 về 01:00, giá trị 01:30 có thể chỉ hai thời điểm khác nhau.

Đây là ví dụ mô tả chuyển đổi, không phải khẳng định mọi nơi chuyển giờ theo các mốc này.

### 5.2. Chính sách phải chọn hành vi rõ ràng

| Tình huống | Các lựa chọn có thể có | Điều cần tránh |
|---|---|---|
| Người dùng đặt một giờ nằm trong gap | Từ chối và yêu cầu chọn lại; hoặc dời theo quy tắc đã thông báo | Thư viện tự dời nhưng giao diện vẫn hứa giờ cũ |
| Giờ đặt lịch nằm trong overlap | Yêu cầu xác nhận offset hoặc chọn lần đầu/lần sau theo hợp đồng | Mỗi service tự chọn một lần khác nhau |
| Lịch chạy hằng ngày gặp giờ bị lặp | Chạy một lần cho chu kỳ, hoặc hai lần nếu nghiệp vụ thực sự yêu cầu | Hai lần chi trả chỉ vì scheduler kích hoạt hai lần |
| Ngày địa phương bị bỏ qua hoàn toàn | Bỏ chu kỳ hoặc chuyển theo chính sách được phê duyệt | Tạo quyền lợi giả cho một ngày không tồn tại |
| Biên đầu ngày có thay đổi offset | Dùng biên được chính sách định nghĩa và ghi nhận | Luôn giả định đầu ngày phải là 00:00 hợp lệ |

Một số phép dựng `ZonedDateTime` có quy tắc tự giải quyết gap hoặc overlap. Với hạn chót hoặc lịch nhạy cảm, cần chủ động chọn hành vi; `ofStrict` cho phép kiểm tra sự phù hợp của ngày giờ, offset và múi giờ. [Java ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html)

Không cho người gọi tự chọn cách giải quyết overlap để kéo dài một hạn chót đã được server chốt. Khả năng chọn offset chỉ phù hợp với thao tác thực sự cho phép họ chọn lịch.

## 6. Minh họa Java: khoảng ngày và kiểm tra giờ địa phương

### 6.1. Tạo khoảng ngày theo chính sách đã phê duyệt

Đoạn mã Java 17+ dưới đây minh họa quy tắc: ngày bắt đầu ở thời điểm hợp lệ sớm nhất của ngày đó; ngày bị bỏ qua hoàn toàn thì từ chối tạo khoảng. Múi giờ và phiên bản chính sách phải đến từ cấu hình đã kiểm tra quyền phía server.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

final class BusinessCalendar {
    record Window(
            Instant startInclusive,
            Instant endExclusive,
            ZoneId businessZone,
            String policyVersion) {

        Window {
            Objects.requireNonNull(startInclusive);
            Objects.requireNonNull(endExclusive);
            Objects.requireNonNull(businessZone);
            Objects.requireNonNull(policyVersion);

            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException("Empty business window");
            }
        }

        boolean contains(Instant decisionAt) {
            return !decisionAt.isBefore(startInclusive)
                    && decisionAt.isBefore(endExclusive);
        }
    }

    static Window calendarDay(
            LocalDate day,
            ZoneId approvedZone,
            String policyVersion) {

        var start = day.atStartOfDay(approvedZone);
        var end = day.plusDays(1).atStartOfDay(approvedZone);

        if (!start.toLocalDate().equals(day)) {
            throw new IllegalArgumentException("Local date does not exist");
        }

        return new Window(
                start.toInstant(),
                end.toInstant(),
                approvedZone,
                policyVersion);
    }
}
~~~

`LocalDate.atStartOfDay(zone)` tìm thời gian hợp lệ sớm nhất theo quy tắc vùng, nên không phải lúc nào kết quả cũng là 00:00. Code trên chấp nhận cách xử lý đó trong cùng ngày, nhưng không chấp nhận việc đầu ngày bị dời sang một ngày khác. Đây là chính sách minh họa cần được nghiệp vụ đồng ý. [Java LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html)

Nếu ngày kế tiếp bị bỏ qua, biên kết thúc có thể nằm ở đầu ngày hợp lệ sau đó. Không suy ra số giờ của khoảng từ hiệu hai nhãn ngày; tiếp tục dùng các mốc `Instant` đã giải quyết.

Đoạn mã không bao gồm cơ chế khóa, phân quyền hay lưu quyền lợi. Kiểm tra `contains` đúng vẫn chưa ngăn được hai request cùng nhận ưu đãi.

### 6.2. Giải quyết đầu vào giờ địa phương một cách tường minh

Khi một thao tác được phép nhận lịch từ người dùng, có thể dùng cách xử lý nghiêm ngặt sau:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

final class StrictLocalSchedule {
    static Instant resolve(
            LocalDateTime local,
            ZoneId approvedZone,
            ZoneOffset selectedOffset) {

        var offsets = approvedZone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new IllegalArgumentException("Local time does not exist");
        }

        if (selectedOffset == null) {
            if (offsets.size() != 1) {
                throw new IllegalArgumentException("Offset confirmation required");
            }
            selectedOffset = offsets.get(0);
        }

        if (!offsets.contains(selectedOffset)) {
            throw new IllegalArgumentException("Offset conflicts with zone");
        }

        return ZonedDateTime.ofStrict(
                local, selectedOffset, approvedZone).toInstant();
    }
}
~~~

Ý nghĩa bảo mật của ví dụ là xác nhận tính nhất quán của ba dữ liệu: giờ địa phương, offset và vùng được phép dùng. Một offset có cú pháp hợp lệ chưa chứng minh nó phù hợp với vùng tại ngày giờ đó.

API thực tế cần chuyển các lỗi xác thực đầu vào thành mã lỗi ổn định và kiểm tra quyền tạo lịch. Không dùng hàm này để nhận một `expiresAt` tùy ý cho mã khuyến mại do server phát hành.

## 7. Ngăn việc đổi múi giờ để nhận lại quyền lợi

### 7.1. Kịch bản lạm dụng

Giả sử hệ thống có quy tắc “mỗi tài khoản nhận một mã mỗi ngày”, nhưng triển khai như sau:

~~~text
businessDate = ngày hiện tại theo profile.timeZone
nếu chưa có bản ghi (accountId, businessDate):
    cấp mã
~~~

Người dùng nhận mã, đổi múi giờ hồ sơ sang vùng đang ở một ngày khác rồi nhận tiếp. Nếu múi giờ được gửi theo từng request, họ thậm chí không cần sửa hồ sơ.

Việc dùng `ZoneId` hợp lệ hoặc lưu tất cả timestamp ở UTC không tự chặn được hành vi này. Lỗi nằm ở việc người nhận quyền lợi được tự chọn biên chu kỳ.

### 7.2. Định danh chu kỳ do server quản lý

Một thiết kế minh họa cho chiến dịch:

~~~text
campaignId: định danh chiến dịch
entitlementCycleId: định danh chu kỳ do server tạo và chốt
businessDate: nhãn ngày để giải thích, báo cáo
businessZone: vùng được chốt trong chính sách
startInclusive / endExclusive: biên tuyệt đối đã tính
policyVersion: phiên bản quy tắc áp dụng

Ràng buộc quyền lợi:
    UNIQUE(campaignId, accountId, entitlementCycleId)
~~~

Server chọn chu kỳ từ chiến dịch và thời điểm quyết định, không từ ngày hoặc cycle ID tùy ý mà client tự khai. Nếu có tenant, mọi truy vấn và ràng buộc phải giữ đúng phạm vi tenant theo mô hình khóa của hệ thống.

Không thêm `zoneId` hoặc `policyVersion` vào ràng buộc duy nhất theo cách làm một quyền lợi cũ trở thành quyền lợi mới sau khi đổi cấu hình.

Chỉ tạo cycle ID ổn định chưa đủ nếu một đợt chuyển múi giờ tự tạo thêm chu kỳ chồng lấn. Chính sách di chuyển phải chỉ rõ quyền lợi đang mở được giữ như thế nào và bảo đảm cùng một quyền lợi không được cấp lại.

### 7.3. Transaction bảo vệ quyết định

Luồng tham chiếu cho thao tác nhận ưu đãi:

~~~text
1. Xác thực người gọi và xác định tenant/account từ ngữ cảnh server.
2. Kiểm tra quyền truy cập chiến dịch.
3. Mở transaction và điều phối truy cập vào dữ liệu liên quan.
4. Kiểm tra idempotency key trong đúng phạm vi chủ thể và thao tác.
5. Nếu đã có kết quả, kiểm tra quyền đọc rồi trả kết quả cũ.
6. Nếu là ý định mới:
   - đọc chính sách và trạng thái chiến dịch có hiệu lực;
   - lấy thời điểm quyết định từ nguồn được hệ thống chọn;
   - kiểm tra start <= decisionAt < end;
   - xác định chu kỳ đã chốt;
   - kiểm tra điều kiện nghiệp vụ và ngân sách;
   - ghi nhận quyền lợi với ràng buộc duy nhất;
   - lưu kết quả idempotency và outbox nếu có tác dụng phụ.
7. Commit; tác dụng phụ bên ngoài được xử lý với cơ chế chống trùng.
~~~

Hai request khác idempotency key vẫn phải bị ràng buộc quyền lợi chặn nếu thuộc cùng tài khoản và chu kỳ. Idempotency chống lặp cùng ý định; ràng buộc nghiệp vụ chống việc tạo nhiều ý định để nhận quá quyền.

Kiểm tra trạng thái chiến dịch và ngân sách phải đủ an toàn trước thay đổi đồng thời. `@Transactional` không tự tạo mọi khóa hoặc mức cô lập cần thiết.

## 8. Chọn thời điểm đánh giá hạn chót

### 8.1. Nhận request, tiếp nhận lệnh và xử lý xong là các mốc khác nhau

Một request có thể đến gateway trước hạn, nằm trong hàng đợi rồi tới application sau hạn. Hoặc application kiểm tra trước hạn nhưng commit sau hạn.

Chính sách cần xác định mốc có ý nghĩa:

| Cách quy định | Hệ quả cần xử lý |
|---|---|
| Dựa trên lúc server có thẩm quyền nhận request | Cần bằng chứng thời gian đáng tin từ đường vào, không tin header công khai |
| Dựa trên lúc tiếp nhận lệnh nghiệp vụ | Gắn thời điểm với quyết định và bản ghi tiếp nhận |
| Yêu cầu hoàn thành trước hạn | Cần định nghĩa hoàn thành, kiểm soát thực thi và lỗi sau hạn |
| Dựa trên thời điểm sự kiện bên ngoài xảy ra | Cần xác thực nguồn sự kiện, chống replay và quy định sự kiện đến muộn |

Trong ví dụ nhận ưu đãi, có thể chọn **thời điểm quyết định tiếp nhận**, sau khi đã lấy dữ liệu và quyền điều phối cần thiết, rồi lưu `acceptedAt` cùng quyết định. Nếu transaction được phép commit sau mốc đóng cửa, điều đó phải là một phần của hợp đồng, không được mô tả thành “commit trước hạn”.

Nếu nghiệp vụ yêu cầu mốc khác, phải thiết kế tương ứng. Đọc `now` ở đầu request rồi xử lý lâu không tự chứng minh thao tác thực sự được tiếp nhận trước hạn.

### 8.2. Không dùng thời gian client làm bằng chứng mặc định

Các trường như `clientSentAt`, `deviceTime` và `localDate` có thể hữu ích cho chẩn đoán. Chúng không mặc nhiên có thẩm quyền quyết định một yêu cầu còn hạn.

Nếu cần chấp nhận sự kiện offline hoặc thông báo từ đối tác, hãy quy định riêng:

- Nguồn nào được tin và được xác thực bằng cách nào.
- Thời gian nào là thời gian sự kiện, thời gian nhận và thời gian xử lý.
- Độ trễ tối đa được chấp nhận.
- Cách xử lý trùng lặp, sửa đổi, tranh chấp và đối soát.
- Quyền ghi nhận hồi tố và bằng chứng audit.

Không thêm một “khoảng dung sai” ngầm vào mọi deadline. Nếu được phép dung sai, nó là một phần của chính sách và phải có phạm vi rõ ràng.

### 8.3. Clock là phụ thuộc của hệ thống

Có thể inject `Clock` để việc đọc thời gian được tập trung và kiểm thử bằng `Clock.fixed`. `Clock.systemUTC()` dùng nguồn đồng hồ hệ thống với vùng UTC; nó không tự bảo đảm mọi node đều đồng bộ chính xác. [Java Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)

Thiết kế phân tán cần chọn nguồn thời gian và mức sai lệch có thể chấp nhận. Nếu dùng thời gian của cơ sở dữ liệu, phải hiểu hàm được chọn trả thời điểm bắt đầu transaction, bắt đầu statement hay thời điểm gọi thực tế. Không giả định chúng có cùng ý nghĩa.

Đổi múi giờ không phải sửa lệch đồng hồ. Hai vấn đề cần quan sát riêng: sai quy tắc chuyển đổi và sai nguồn “hiện tại”.

## 9. Lưu trữ, API và hiển thị nhất quán

### 9.1. Dữ liệu tối thiểu để giải thích quyết định

Với đối tượng nhạy cảm theo thời gian, tùy nghiệp vụ có thể cần lưu:

| Trường | Mục đích |
|---|---|
| `createdAt`, `acceptedAt` | Ghi nhận các sự kiện dưới dạng thời điểm tuyệt đối |
| `startInclusive`, `endExclusive` | Biên hiệu lực đã được giải quyết |
| `businessZone` | Vùng dùng để diễn giải quy tắc |
| `businessDate`, `entitlementCycleId` | Nhãn ngày và định danh quyền lợi |
| `policyVersion` | Tái dựng quy tắc đã dùng |
| Giờ địa phương ban đầu và offset được chọn | Giải thích lịch nhập trong trường hợp cần thiết |
| Thông tin bản dữ liệu múi giờ của môi trường tính toán | Hỗ trợ đối soát lịch tương lai khi quy tắc thay đổi |

Không phải mọi bản ghi đều cần tất cả các trường. Mục tiêu là lưu đủ bằng chứng để giải thích quyết định mà không phải lấy cấu hình hiện tại và giả định quá khứ cũng giống vậy.

Kiểm tra ngữ nghĩa kiểu thời gian của database, driver và serializer. Tên có chữ “time zone” chưa chứng minh cơ sở dữ liệu giữ nguyên tên vùng mà ứng dụng đã nhập; một offset cũng không thay thế được `businessZone`.

Thống nhất độ chính xác lưu trữ và so sánh. Nếu ứng dụng giữ nanosecond nhưng database chỉ giữ microsecond hoặc millisecond, cần chính sách chuẩn hóa rõ ràng và kiểm thử tại biên.

### 9.2. Hợp đồng API minh họa

~~~json
{
  "campaignId": "campaign-example",
  "cycleId": "cycle-example",
  "businessDate": "2026-11-22",
  "businessZone": "Asia/Ho_Chi_Minh",
  "startInclusive": "2026-11-21T17:00:00Z",
  "endExclusive": "2026-11-22T17:00:00Z",
  "policyVersion": "campaign-local-day-v1"
}
~~~

Đây là phản hồi đọc chính sách cho đối tượng mà người gọi được phép xem, không phải tập trường client được quyền gửi lại để quyết định hạn.

Client có thể hiển thị cả giờ nghiệp vụ và giờ của người xem:

~~~text
Kết thúc lúc 00:00 ngày 23/11 theo Asia/Ho_Chi_Minh.
Mốc kết thúc không được tính vào thời gian nhận ưu đãi.
~~~

Không chỉ hiện “hết hạn hôm nay” khi người xem và chiến dịch có thể đang ở hai ngày khác nhau. Bộ đếm ngược phía giao diện hỗ trợ trải nghiệm; server vẫn quyết định hiệu lực.

### 9.3. Cache và khóa dữ liệu

Cache cửa sổ hiệu lực phải gắn với đúng đối tượng và phiên bản chính sách đã được phê duyệt. Tránh cache chỉ theo tên ngày rồi dùng lại giữa tenant hoặc chiến dịch có vùng khác nhau.

TTL giúp dọn cache; nó không thay thế kiểm tra `endExclusive` khi xử lý thao tác. Một bản ghi chưa bị scheduler xóa vẫn có thể đã hết hạn, và một lần xóa trễ không được kéo dài quyền sử dụng.

## 10. Thay đổi múi giờ và cập nhật dữ liệu quy tắc

### 10.1. Hai loại thay đổi khác nhau

1. **Đổi cấu hình nghiệp vụ:** tenant hoặc chiến dịch được chuyển sang một múi giờ khác.
2. **Đổi dữ liệu quy tắc múi giờ:** cùng tên vùng nhưng các quy tắc lịch tương lai được cập nhật.

IANA duy trì dữ liệu lịch sử và các quy tắc múi giờ; những quyết định thay đổi có thể được thông báo gấp. Vì vậy, một tên vùng không phải lời hứa rằng mọi lịch tương lai sẽ luôn ánh xạ như lúc triển khai. [IANA Time Zone Database](https://data.iana.org/time-zones/tz-link.html)

Với một deadline đã chốt thành `Instant`, thường cần giữ nguyên mốc đã cam kết, trừ khi có thay đổi nghiệp vụ được phê duyệt. Với lịch “09:00 địa phương mỗi ngày”, hệ thống có thể cần áp dụng quy tắc vùng mới cho các lần chạy tương lai. Hai cách diễn giải này phải được phân biệt trong hợp đồng.

### 10.2. Di chuyển cấu hình không được tạo lại quyền lợi

Một quy trình tham chiếu:

- Phân quyền người sửa và ghi lại lý do, cấu hình cũ, cấu hình mới.
- Chọn mốc hiệu lực tương lai; không tùy ý diễn giải lại giao dịch đã chốt.
- Với chiến dịch ngắn hạn đang chạy, cân nhắc giữ nguyên chính sách tới khi kết thúc.
- Với chương trình dài hạn, xác định cách kết thúc chu kỳ cũ và mở chu kỳ mới.
- Kiểm tra khoảng trùng hoặc khoảng trống và quyền lợi đã cấp trong giai đoạn chuyển tiếp.
- Giữ liên kết quyền lợi cũ; không reset bộ đếm chỉ vì phiên bản chính sách thay đổi.
- Đồng bộ các thành phần tính lịch và kiểm tra các lịch tương lai chịu ảnh hưởng.

Chỉ đặt `effectiveFrom` chưa tự bảo đảm không cấp thêm quyền. Nếu chu kỳ mới bắt đầu ngay sau đổi vùng và mọi người đều được nhận lại dù vừa nhận ở chu kỳ cũ, chính sách chuyển tiếp vẫn có thể sai.

Không âm thầm tính lại tất cả `endExclusive` từ múi giờ hồ sơ hiện tại. Hạn chót đã chốt cần có lịch sử thay đổi tường minh.

## 11. Scheduler, retry và state machine

Scheduler chỉ phát tín hiệu đến hạn; nó không phải bằng chứng cuối cùng rằng thao tác được phép.

Khi thực thi, worker vẫn cần:

1. Đọc đúng đối tượng và chính sách đã gắn với đối tượng.
2. Kiểm tra trạng thái hiện tại và quyền thực thi của tác vụ.
3. Kiểm tra mốc thời gian theo hợp đồng tiếp nhận hoặc thực thi.
4. Dùng định danh lần chạy hoặc chu kỳ ổn định.
5. Ghi chuyển trạng thái và bảo vệ tác dụng phụ khỏi trùng lặp.

Ví dụ, worker chi trả hằng ngày cần một khóa nghiệp vụ tương đương `(payoutProgramId, entitlementCycleId)`. Hai lần kích hoạt trong giờ overlap hoặc một lần retry sau khi mất kết nối không được tạo hai khoản chi.

Với thao tác đã được tiếp nhận trước hạn nhưng worker chạy sau hạn, phải áp dụng hợp đồng đã định: tiếp tục hoàn thành lệnh đã tiếp nhận, hay yêu cầu kiểm tra hiệu lực tại lúc thực thi. Không tự đổi lựa chọn chỉ vì worker đang dùng múi giờ khác.

Các trạng thái tham chiếu có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> Scheduled
    Scheduled --> Active: đạt startInclusive
    Active --> Closed: đạt endExclusive
    Active --> Suspended: quyết định đình chỉ
    Suspended --> Closed: hết hiệu lực
    Active --> Cancelled: hủy theo quyền
~~~

Không cho việc thay múi giờ hiển thị làm `Closed` quay về `Active`. Nếu chính sách cho phép mở lại, đó phải là chuyển trạng thái được phân quyền và có audit, không phải hệ quả phụ của phép đổi ngày.

## 12. Kịch bản kiểm thử tình huống lạm dụng

Bảng này mô tả yêu cầu kiểm thử cho một triển khai, không khẳng định đã chạy kiểm thử hệ thống cụ thể.

| Kịch bản | Điều phải xác minh |
|---|---|
| Đổi múi giờ trình duyệt, hồ sơ hoặc header | Không thay chu kỳ hoặc hạn đã chốt |
| Gửi một `zoneId` hợp lệ nhưng không thuộc chính sách đối tượng | Không được áp dụng để kéo dài quyền |
| Đổi `campaignId` hoặc tenant trong body | Không vượt quyền theo đối tượng hoặc đọc nhầm chính sách |
| Hai node có múi giờ mặc định khác nhau | Cùng thời điểm và cùng chính sách cho cùng quyết định |
| Đúng mốc bắt đầu | Được tính vào khoảng nếu các điều kiện khác thỏa |
| Đúng mốc kết thúc | Bị loại khỏi khoảng |
| Trước/sau biên theo độ chính xác lưu trữ | Không sai do làm tròn hoặc cắt phần lẻ |
| Một ngày có thay đổi offset | Biên theo lịch được tính đúng, không mặc định cộng 24 giờ |
| Ngày hoặc giờ địa phương không tồn tại | Thực hiện đúng chính sách từ chối hoặc điều chỉnh |
| Giờ địa phương có nhiều offset hợp lệ | Giải quyết tường minh, không tạo hai quyền lợi |
| Hai request đồng thời với key khác nhau | Chỉ một quyền lợi theo ràng buộc chu kỳ |
| Retry cùng ý định qua thời điểm nửa đêm | Trả kết quả cũ đúng quyền, không biến thành lần nhận mới |
| Request đến trước hạn nhưng chờ xử lý lâu | Quyết định theo mốc được hợp đồng lựa chọn |
| Client khai thời điểm gửi trong quá khứ | Không tự trở thành bằng chứng còn hạn |
| Đổi chính sách giữa chu kỳ | Không nhận thêm quyền do đổi zone, version hoặc cycle |
| Worker xử lý lặp và scheduler kích hoạt trùng | Chỉ một tác dụng phụ nghiệp vụ |
| Hệ thống lệch đồng hồ hoặc một node dùng quy tắc vùng cũ | Phát hiện sai lệch và xử lý theo chính sách vận hành |
| Cleanup hoặc cache hết hạn chậm | Không kéo dài hiệu lực thực tế |

Có thể cố định thời gian bằng `Clock.fixed` và truyền `ZoneId` tường minh trong bộ kiểm thử. Đối với gap và overlap, chọn dữ liệu phù hợp với bản quy tắc múi giờ của môi trường kiểm thử và ghi nhận giả định đó.

Ngoài HTTP status, cần quan sát sổ quyền lợi, lần chuyển trạng thái và số tác dụng phụ đã commit. Một API trả lỗi đúng ở lần thứ hai vẫn có thể đã cấp quyền lợi hai lần trước khi trả lỗi.

## 13. Những bất biến cần giữ

Một chính sách múi giờ phục vụ bảo mật nghiệp vụ phải giữ được các điều sau:

- Thay đổi cách hiển thị không thay đổi quyền đã được cấp hoặc hạn đã chốt.
- Người gọi không tự chọn lịch hoặc múi giờ để vượt điều kiện của đối tượng.
- Cùng một chính sách và một thời điểm cho quyết định nhất quán giữa các thành phần.
- Mỗi chu kỳ cấp tối đa quyền lợi đã quy định, kể cả khi có retry hoặc xử lý đồng thời.
- Việc chuyển múi giờ và phiên bản không tạo quyền lợi bổ sung ngoài chính sách.
- Hết hạn không bỏ qua kiểm tra trạng thái; còn hạn không thay thế kiểm tra quyền.
- Quyết định có đủ bằng chứng để giải thích bằng thời điểm, vùng, chu kỳ và phiên bản đã dùng.

Cốt lõi là chọn **ai có quyền quyết định múi giờ**, **quy tắc lịch nào được áp dụng** và **thời điểm nào quyết định hiệu lực**, rồi lưu và thực thi các lựa chọn đó cùng bất biến nghiệp vụ. Việc chuyển đổi sang UTC là một phần của quá trình này.
