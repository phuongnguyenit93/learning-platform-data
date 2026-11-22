# Vì sao offset không chứa đầy đủ quy tắc của múi giờ vùng

Một cuộc họp được ghi là **09:00 ngày 01/07/2026, UTC-04:00**. Ta có thể chuyển giá trị này sang một thời điểm UTC chính xác. Nhưng từ `-04:00`, Java có biết cuộc họp ở New York, Toronto hay vùng khác không? Nếu cuộc họp diễn ra lúc 09:00 hằng tháng, liệu offset của tháng 12 vẫn là `-04:00`?

Câu trả lời là **không**. UTC offset chỉ cho biết **độ lệch giữa đồng hồ địa phương và UTC tại một thời điểm**. Múi giờ vùng còn có **quy tắc phụ thuộc ngày**, bao gồm các thay đổi giờ mùa hè (DST), điều chỉnh lịch sử và thay đổi pháp luật. Trong `java.time`, đây là sự khác nhau giữa `ZoneOffset` và một `ZoneId` khu vực với `ZoneRules`.

Bài học thuộc nhóm **Ngày giờ có offset** và tập trung vào ý nghĩa dữ liệu, cách chọn đúng API Java, xử lý các giờ không tồn tại/lặp lại và thiết kế lưu trữ cho lịch hẹn, lịch lặp, giao dịch. Mọi ví dụ dựa trên Java 17+.

## 1. Offset nói điều gì — và không nói điều gì?

Offset là hiệu số có dấu giữa giờ địa phương và UTC:

~~~text
Giờ địa phương = UTC + offset
UTC 13:00 + (-04:00) = 09:00
UTC 02:30 + (+07:00) = 09:30
~~~

Trong Java:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 7, 1, 9, 0);
ZoneOffset offset = ZoneOffset.of("-04:00");

OffsetDateTime dated = local.atOffset(offset);
Instant instant = dated.toInstant();

// dated   = 2026-07-01T09:00-04:00
// instant = 2026-07-01T13:00:00Z
~~~

Với **một ngày giờ cụ thể**, offset đúng là đủ để quy đổi thành `Instant`. Nhưng bản thân offset **không cho biết**:

- Tên vùng địa lý như `America/New_York`, `Europe/Paris`.
- Quy tắc khi nào một vùng chuyển sang giờ mùa hè và khi nào kết thúc.
- Offset đúng cho vùng đó ở những ngày/tháng/năm khác.
- Các lần thay đổi luật múi giờ trước đây hoặc tương lai.
- Ngày giờ địa phương nào bị bỏ qua (**gap**) hoặc xảy ra hai lần (**overlap**).

Đây không phải hạn chế độ chính xác của `OffsetDateTime` đối với một mốc đã biết. Nó là giới hạn về **ngữ nghĩa vùng** và **quy tắc qua thời gian**.

## 2. Một vùng có thể dùng các offset khác nhau

`America/New_York` là một định danh vùng. Trong năm 2026, vùng này có giờ mùa hè và giờ tiêu chuẩn:

| Giờ đồng hồ ở New York | Offset áp dụng | Instant UTC |
| --- | --- | --- |
| `2026-07-01 09:00` | `-04:00` | `2026-07-01T13:00:00Z` |
| `2026-12-01 09:00` | `-05:00` | `2026-12-01T14:00:00Z` |

Cùng **09:00 theo giờ New York**, nhưng offset khác giữa tháng 7 và tháng 12. Nếu dùng cố định `-04:00` cho cuộc họp tháng 12, instant sẽ là `13:00Z`, **sớm hơn 1 giờ** so với 09:00 New York thật.

~~~java
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime summer =
        LocalDateTime.of(2026, 7, 1, 9, 0).atZone(ny);
ZonedDateTime winter =
        LocalDateTime.of(2026, 12, 1, 9, 0).atZone(ny);

// summer = 2026-07-01T09:00-04:00[America/New_York]
// winter = 2026-12-01T09:00-05:00[America/New_York]
~~~

`atZone(ny)` tra các quy tắc của vùng theo ngày/giờ đã chỉ định. `ZoneOffset.ofHours(-4)` thì luôn là `-04:00`; nó không thể “biết” khi nào New York chuyển về `-05:00`.

**Lưu ý:** không phải vùng nào cũng áp dụng DST. Một vùng có offset cố định trong hiện tại vẫn có thể có lịch sử thay đổi hoặc bị thay đổi quy tắc trong tương lai. Do đó, đừng lấy offset đo được hôm nay để kết luận “vùng luôn như thế”.

## 3. Nhiều vùng có thể có cùng một offset

Ngay tại một instant, nhiều khu vực có thể trùng offset. Ví dụ `Asia/Ho_Chi_Minh` và `Asia/Bangkok` thường cùng dùng `+07:00` trong thời hiện đại. Nhiều vùng Bắc Mỹ cùng có `-04:00` trong mùa hè nhưng có thể khác lịch sử và quy tắc riêng.

~~~text
America/New_York ----\
                      \        một thời điểm cụ thể
America/Toronto -------> -04:00
                      /
Các vùng khác --------/

-04:00 không suy ra duy nhất America/New_York
~~~

Phép ánh xạ `(ZoneId, Instant) -> ZoneOffset` có thể thực hiện nhờ quy tắc vùng. Chiều ngược `(ZoneOffset, Instant) -> ZoneId` thường **không có đáp án duy nhất**.

Vì thế, từ một `OffsetDateTime` chẳng hạn `2026-07-01T09:00-04:00`, ứng dụng xác định được instant `13:00Z`, nhưng **không thể phục hồi chắc chắn tên thành phố/vùng ban đầu**. Muốn giữ địa điểm sự kiện hoặc quy tắc lịch địa phương, phải lưu `ZoneId` hay thông tin địa điểm riêng.

## 4. `ZoneId` và `ZoneRules` lưu điều gì?

`ZoneId` như `America/New_York` là định danh khu vực. Java dùng `ZoneRules` của định danh đó để ánh xạ giữa instant và giờ địa phương/offset dựa trên dữ liệu múi giờ (tzdb).

Những việc `ZoneRules` có thể làm:

1. Tra offset hợp lệ tại **một instant đã xác định**.
2. Xác định các offset hợp lệ với **một `LocalDateTime`**: 0, 1 hoặc 2.
3. Cung cấp các chuyển tiếp offset mà dữ liệu quy tắc hiện có mô tả.
4. Cho phép chuyển `Instant` thành giờ địa phương và offset tương ứng trong vùng.

Ví dụ tra từ instant sang offset:

~~~java
ZoneId zone = ZoneId.of("America/New_York");

ZoneOffset summer = zone.getRules().getOffset(
        Instant.parse("2026-07-01T13:00:00Z")); // -04:00

ZoneOffset winter = zone.getRules().getOffset(
        Instant.parse("2026-12-01T14:00:00Z")); // -05:00
~~~

Một `Instant` đã biết, với một bộ `ZoneRules` cụ thể, cho **một offset** tương ứng. Nhưng khi bắt đầu từ giờ địa phương, việc chuyển có thể mơ hồ ở ngày đổi DST. Đó là lý do cần `getValidOffsets(LocalDateTime)`.

**Chi tiết kiểu Java:** `ZoneOffset` thực sự là một kiểu con của `ZoneId`. Có thể truyền `ZoneOffset` vào phương thức nhận `ZoneId`; tuy nhiên khi đó ta dùng **vùng offset cố định**, không phải tên vùng IANA có lịch chuyển giờ. Quan hệ kế thừa trong Java **không khiến offset trở thành bộ quy tắc của New York**.

## 5. Gap và overlap: thông tin offset đơn lẻ bỏ sót

### 5.1. Gap — giờ không tồn tại lúc bắt đầu DST

Theo quy tắc New York trong năm 2026, ngày `08/03` đồng hồ nhảy qua khoảng `02:00–02:59`:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);

List<ZoneOffset> valid = ny.getRules().getValidOffsets(gap);
// valid.size() == 0
~~~

Giờ 02:30 **không xảy ra** ở New York ngày đó. Nhưng `gap.atOffset(ZoneOffset.of("-05:00"))` vẫn tạo được một `OffsetDateTime` hợp lệ về mặt Java và quy đổi được sang instant. Điều đó **không xác nhận** 02:30 là một giờ có thật ở khu vực này.

`gap.atZone(ny)` mặc định chuyển giờ không tồn tại tiến lên theo độ dài gap, trong ví dụ thành `03:30-04:00`. Với ứng dụng đặt lịch, cần quy định có tự dời hay **yêu cầu người dùng sửa**.

### 5.2. Overlap — giờ lặp lại khi kết thúc DST

Ngày `01/11/2026` ở New York, đồng hồ lùi, vì thế `01:30` xảy ra hai lần:

~~~java
LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
List<ZoneOffset> valid =
        ny.getRules().getValidOffsets(overlap);

// valid = [-04:00, -05:00]
~~~

Hai cách diễn giải:

| Giờ địa phương | Offset | Instant |
| --- | --- | --- |
| `2026-11-01T01:30` | `-04:00` | `2026-11-01T05:30:00Z` |
| `2026-11-01T01:30` | `-05:00` | `2026-11-01T06:30:00Z` |

`overlap.atZone(ny)` mặc định chọn offset sớm hơn (trong ví dụ `-04:00`). Nếu người dùng muốn lần thứ hai, dùng `withLaterOffsetAtOverlap()` hoặc chọn rõ offset hợp lệ. Một offset riêng lẻ không chứa thông tin rằng có **hai lựa chọn** vào lúc này.

### 5.3. Bảng kiểm tra bằng `ZoneRules`

| `getValidOffsets(local).size()` | Trạng thái | Xử lý thường cần |
| ---: | --- | --- |
| 0 | Gap, giờ địa phương không tồn tại | Từ chối hoặc dời theo chính sách |
| 1 | Một giờ bình thường | Dùng offset duy nhất |
| 2 | Overlap, giờ địa phương bị lặp | Chọn offset trước/sau theo nghiệp vụ |

Các quy tắc này thuộc `ZoneId` khu vực. Với lịch hẹn quan trọng, không nên chỉ gọi `atZone` rồi tin rằng lựa chọn mặc định luôn phản ánh ý muốn thực tế.

## 6. `OffsetDateTime` và `ZonedDateTime` khác nhau thế nào?

| Năng lực | `OffsetDateTime` | `ZonedDateTime` có `ZoneId` khu vực |
| --- | --- | --- |
| Biết ngày/giờ địa phương | Có | Có |
| Biết offset đang áp dụng | Có | Có |
| Xác định `Instant` | Có | Có |
| Giữ tên vùng như `America/New_York` | Không | Có |
| Tra offset hợp lệ cho ngày khác theo vùng | Không | Có |
| Biết gap/overlap theo vùng | Không | Có, qua `ZoneRules` |
| Biểu diễn lịch lặp hằng tuần | Chưa đủ thông tin | Có thành phần vùng, nhưng vẫn cần quy tắc lặp |

`OffsetDateTime` phù hợp khi cần truyền **một mốc cụ thể có offset** và không quan tâm đến địa điểm. Ví dụ log có `2026-07-01T09:00-04:00` là chính xác nếu offset thuộc dữ liệu gốc và đúng tại sự kiện.

`ZonedDateTime` giữ được địa chỉ quy tắc vùng (nếu được tạo từ `ZoneId` khu vực), nên phù hợp hơn khi xử lý **lịch có ý nghĩa theo địa phương**. Tuy nhiên, một `ZonedDateTime` được tạo từ `ZoneOffset` vẫn có thể chỉ mang **zone cố định**, không có lịch sử chuyển giờ địa phương.

## 7. Chuyển kiểu: giữ thời điểm khác giữ giờ đồng hồ

### 7.1. Giữ cùng instant

~~~java
OffsetDateTime source = OffsetDateTime.parse(
        "2026-07-01T09:00-04:00");

ZonedDateTime inTokyo = source.atZoneSameInstant(
        ZoneId.of("Asia/Tokyo"));

// inTokyo = 2026-07-01T22:00+09:00[Asia/Tokyo]
// source.toInstant() == inTokyo.toInstant()
~~~

`09:00-04:00` là `13:00Z`, nên cùng instant đó tại Tokyo là 22:00. Đây là phép chuyển **đúng** khi chỉ muốn hiển thị một sự kiện đã xảy ra cho người ở vùng khác.

Cách tương đương:

~~~java
Instant event = source.toInstant();
ZonedDateTime view = event.atZone(ZoneId.of("Asia/Tokyo"));
~~~

### 7.2. Cố giữ cùng giờ địa phương

~~~java
ZonedDateTime inTokyoAtNine =
        source.atZoneSimilarLocal(ZoneId.of("Asia/Tokyo"));

// inTokyoAtNine = 2026-07-01T09:00+09:00[Asia/Tokyo]
~~~

Giờ đồng hồ vẫn là 09:00, nhưng instant giờ đây thành `00:00Z` thay vì `13:00Z`. Dùng phép này **chỉ** khi nghiệp vụ thực sự đổi địa điểm nhưng vẫn giữ 09:00 địa phương. Nếu giờ rơi vào gap/overlap ở vùng đích, quy tắc giải quyết địa phương sẽ được áp dụng.

Tương tự với `ZonedDateTime`:
- `withZoneSameInstant(zone)` giữ **instant**.
- `withZoneSameLocal(zone)` cố giữ **ngày và giờ đồng hồ**.

### 7.3. `toZonedDateTime()` không phục hồi tên vùng

~~~java
OffsetDateTime value =
        OffsetDateTime.parse("2026-07-01T09:00-04:00");

ZonedDateTime converted = value.toZonedDateTime();

// converted.getZone() là -04:00, không phải America/New_York.
~~~

Chuyển kiểu từ `OffsetDateTime` sang `ZonedDateTime` **không có thuật toán thần kỳ đoán vùng từ offset**. Nếu ứng dụng muốn hiển thị cùng instant tại New York thì phải biết `America/New_York` từ nơi khác, rồi sử dụng `atZoneSameInstant(ZoneId.of("America/New_York"))`.

## 8. Ví dụ Java 17+ hoàn chỉnh

Ví dụ dùng ngày cố định: tháng 7 và tháng 12 tại New York, chuyển dữ liệu từ offset sang Tokyo, và giờ trùng ngày kết thúc DST. Không sử dụng đồng hồ mặc định của máy.

~~~java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class OffsetRegionDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDateTime summerLocal = LocalDateTime.of(2026, 7, 1, 9, 0);
        LocalDateTime winterLocal = LocalDateTime.of(2026, 12, 1, 9, 0);
        ZonedDateTime summer = summerLocal.atZone(newYork);
        ZonedDateTime winter = winterLocal.atZone(newYork);

        System.out.println("summer=" + summer);
        System.out.println("winter=" + winter);
        System.out.println("summerOffset=" + summer.getOffset());
        System.out.println("winterOffset=" + winter.getOffset());

        OffsetDateTime offsetOnly = summer.toOffsetDateTime();
        System.out.println("offsetOnly=" + offsetOnly);
        System.out.println("offsetOnlyZone="
                + offsetOnly.toZonedDateTime().getZone());

        ZoneId tokyo = ZoneId.of("Asia/Tokyo");
        ZonedDateTime sameInstant = offsetOnly.atZoneSameInstant(tokyo);
        ZonedDateTime sameLocal = offsetOnly.atZoneSimilarLocal(tokyo);

        System.out.println("sameInstantTokyo=" + sameInstant);
        System.out.println("sameLocalTokyo=" + sameLocal);
        System.out.println("sameMoment="
                + sameInstant.toInstant().equals(sameLocal.toInstant()));

        OffsetDateTime wrongWinter =
                winterLocal.atOffset(ZoneOffset.ofHours(-4));
        System.out.println("winterFixedUtc=" + wrongWinter.toInstant());
        System.out.println("winterZoneUtc=" + winter.toInstant());

        LocalDateTime repeated =
                LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> choices =
                newYork.getRules().getValidOffsets(repeated);

        ZonedDateTime first = repeated.atZone(newYork);
        ZonedDateTime second = first.withLaterOffsetAtOverlap();
        System.out.println("overlapOffsets=" + choices);
        System.out.println("overlapFirst=" + first);
        System.out.println("overlapSecond=" + second);
        System.out.println("overlapElapsed=" + Duration.between(
                first.toInstant(), second.toInstant()));
    }
}
~~~

Lưu file `OffsetRegionDemo.java`, biên dịch và chạy với JDK 17+:

~~~bash
javac OffsetRegionDemo.java
java OffsetRegionDemo
~~~

Kết quả với quy tắc múi giờ chuẩn cho những ngày ví dụ:

~~~text
summer=2026-07-01T09:00-04:00[America/New_York]
winter=2026-12-01T09:00-05:00[America/New_York]
summerOffset=-04:00
winterOffset=-05:00
offsetOnly=2026-07-01T09:00-04:00
offsetOnlyZone=-04:00
sameInstantTokyo=2026-07-01T22:00+09:00[Asia/Tokyo]
sameLocalTokyo=2026-07-01T09:00+09:00[Asia/Tokyo]
sameMoment=false
winterFixedUtc=2026-12-01T13:00:00Z
winterZoneUtc=2026-12-01T14:00:00Z
overlapOffsets=[-04:00, -05:00]
overlapFirst=2026-11-01T01:30-04:00[America/New_York]
overlapSecond=2026-11-01T01:30-05:00[America/New_York]
overlapElapsed=PT1H
~~~

Các điểm then chốt trong output:

1. `summer` và `winter` cùng `ZoneId` nhưng có offset khác nhau. Một offset không đại diện cho quy tắc suốt cả năm.
2. `offsetOnly` giữ đúng instant, nhưng `toZonedDateTime().getZone()` chỉ còn `-04:00`.
3. `sameInstantTokyo` giữ `13:00Z` nhưng hiển thị 22:00; `sameLocalTokyo` giữ 09:00 và chuyển sang `00:00Z`.
4. `wrongWinter` dùng offset mùa hè cho tháng 12 nên lệch **1 giờ** so với `winter.toInstant()`.
5. Danh sách offset tại `01:30` ngày 01/11 có hai phần tử, cho hai `Instant` cách nhau `PT1H`.

Các kết quả này là xác định với bộ dữ liệu múi giờ có quy tắc New York/Tokyo tương ứng năm 2026; cập nhật luật/tzdb có thể thay đổi hành vi của lịch tương lai.

## 9. Cách lưu đúng thông tin trong hệ thống

### 9.1. Timestamp của sự kiện đã xảy ra

Ví dụ thanh toán hoàn tất lúc `2026-07-01T13:00:00Z`. Ứng dụng chủ yếu cần một mốc tuyệt đối để đối chiếu và sắp xếp, nên `Instant` là biểu diễn thích hợp.

Một `OffsetDateTime` chứa offset đúng cũng xác định được instant. Tuy nhiên, nếu cần biết **địa phương ban đầu** của giao dịch, phải lưu tên vùng hoặc thông tin địa điểm riêng; `Instant` lẫn `OffsetDateTime` đều không tự giữ điều đó.

### 9.2. Quy tắc lịch hẹn định kỳ ở địa phương

Với “09:00 mỗi thứ Hai tại New York”, cần giữ:
- Giờ địa phương `09:00`.
- Quy tắc lặp (thứ Hai, phạm vi ngày, ngoại lệ).
- `ZoneId` `America/New_York`.
- Chính sách xử lý gap/overlap nếu lịch có thể rơi vào những giờ nhạy cảm.
- `Instant` từng buổi sau khi đã giải quyết, nếu cần thông báo hoặc đồng bộ.

Nếu chỉ giữ offset `-04:00` từ một cuộc họp tháng 7, lịch tháng 12 sẽ sai. Nếu chỉ giữ `Instant` buổi đầu rồi cộng cố định 7 × 24 giờ, sau ngày đổi DST giờ địa phương cũng có thể không còn là 09:00. Cách đúng là tính từng kỳ theo lịch địa phương và quy tắc vùng.

### 9.3. Một lần hẹn ở giờ trùng

Nếu người dùng nhập `2026-11-01T01:30` tại New York, có hai instant. Việc lưu chỉ `LocalDateTime` + `ZoneId` mà bỏ lựa chọn offset có thể khiến hệ thống không phục dựng đúng lần 01:30 đã chốt. Hãy lưu **instant đã quyết định** (và zone/offset đã chọn khi cần giải trình), đồng thời ghi rõ quy tắc nghiệp vụ.

Nếu pháp luật đổi múi giờ tương lai, cần phân biệt lịch chưa xảy ra có thể **tính lại theo giờ địa phương** với sự kiện đã cam kết ở một instant cố định. Đó là quyết định nghiệp vụ, không phải phép đổi kiểu tự động của Java.

### 9.4. Hợp đồng API phải rõ vùng và offset

Chuỗi `2026-07-01T09:00:00-04:00` cho biết instant nhưng **không cho biết** vùng. Nếu mục tiêu là lập lịch tại New York, payload nên có thêm trường riêng như `timeZoneId: "America/New_York"` bên cạnh local date-time/offset đã chốt.

Không nên đoán vùng theo offset bằng một danh sách thành phố: nhiều vùng có thể trùng offset, và quy tắc có thể đổi. Cũng không nên dùng `ZoneId.systemDefault()` làm giả định ngầm định cho một địa điểm nghiệp vụ, vì cấu hình máy chủ có thể khác máy phát triển.

## 10. Những sai lầm thường gặp

| Nhận định/thiết kế sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| “`-04:00` luôn là New York” | Một offset có thể thuộc nhiều vùng | Lưu `ZoneId` riêng |
| “New York quanh năm `-04:00`” | DST làm offset thay đổi | Tra `ZoneRules` ở đúng ngày |
| “Offset không đủ xác định một thời điểm” | Nhầm giới hạn vùng với giới hạn instant | Ngày giờ + offset đúng là đủ cho `Instant` |
| “`toZonedDateTime()` tìm lại zone cũ” | Zone thu được có thể chỉ là fixed offset | Có vùng thì truyền `ZoneId` thật |
| “Cứ `atZone` là giờ nhập hợp lệ” | Gap bị dời, overlap có lựa chọn mặc định | Kiểm tra `getValidOffsets` trước |
| “Chỉ cần `LocalDateTime` cho giao dịch đa múi giờ” | Không có offset hoặc instant để đối chiếu | Lưu `Instant` cho mốc tuyệt đối |
| “Lịch tuần chỉ cần offset của lần đầu” | Khi luật/giờ mùa hè đổi, giờ địa phương sai | Lưu lịch lặp + `ZoneId` |
| “`atZoneSameInstant` giống `atZoneSimilarLocal`” | Một hàm giữ instant, hàm kia giữ giờ địa phương | Chọn theo nghiệp vụ |
| “Một bản tzdb dùng mãi không cần cập nhật” | Quy tắc vùng chịu thay đổi pháp luật | Cập nhật dữ liệu múi giờ và test |

## 11. Kiểm thử và vận hành an toàn

Một bộ test hữu ích nên bao gồm:

1. New York `2026-07-01T09:00` dùng offset `-04:00`; `2026-12-01T09:00` dùng `-05:00`.
2. `2026-03-08T02:30` ở New York có 0 offset hợp lệ (gap).
3. `2026-11-01T01:30` có 2 offset hợp lệ (overlap), tương ứng hai instant cách một giờ.
4. Chuyển `Instant -> ZonedDateTime -> Instant` phải giữ nguyên mốc tuyệt đối.
5. Chuyển `ZonedDateTime -> OffsetDateTime -> ZonedDateTime` không được mặc định là bảo toàn **tên** vùng.
6. Quy tắc lịch “09:00 New York mỗi thứ Hai” tiếp tục giữ 09:00 sau DST nếu tính bằng local + `ZoneId`.
7. Chạy test với `ZoneId` tường minh để tránh phụ thuộc vùng mặc định của môi trường.
8. Tổ chức cập nhật JDK/tzdb và kiểm tra hồi quy đối với lịch tương lai nếu vùng thay đổi luật.

**Đừng hard-code offset theo từng ngày vào mã sản phẩm.** Cho `ZoneRules` giải quyết các ngày lịch; chỉ cố định offset khi hợp đồng thực sự nói về offset đó, không phải khu vực.

## 12. Bài tập

1. Tại sao `OffsetDateTime.parse("2026-07-01T09:00-04:00").toInstant()` có một kết quả rõ ràng dù không biết thành phố?
2. Dùng `ZoneRules` để so offset của New York ngày 01/07 và 01/12/2026. Vì sao không thể dùng offset mùa hè cho cả năm?
3. Có thể khôi phục chắc chắn `Asia/Ho_Chi_Minh` chỉ từ `+07:00` không? Giải thích ánh xạ nhiều-vùng-một-offset.
4. Với `2026-11-01T01:30` ở New York, in `getValidOffsets` và hai instant tương ứng.
5. So sánh `atZoneSameInstant(Asia/Tokyo)` và `atZoneSimilarLocal(Asia/Tokyo)` từ cùng `OffsetDateTime` `09:00-04:00`; cái nào phù hợp hiển thị một giao dịch đã xảy ra?
6. Thử `OffsetDateTime.toZonedDateTime().getZone()`. Tại sao chỉ thu được offset?
7. Thiết kế các trường dữ liệu cho “09:00 mỗi thứ Hai ở New York” và cho “giao dịch hoàn tất lúc 13:00Z”.
8. Khi quy tắc múi giờ ở một khu vực thay đổi theo luật, ứng dụng cần làm gì với lịch tương lai và các instant đã ghi nhận?

**Ghi nhớ:** `ZoneOffset` cung cấp chênh lệch so với UTC và, khi kết hợp với ngày giờ, **đủ xác định một `Instant`**. Nhưng nó không chứa **tên vùng, DST, lịch sử hay lịch chuyển đổi offset**. Muốn diễn giải ngày giờ theo địa phương qua nhiều ngày/tháng/năm, hãy dùng `ZoneId` khu vực và `ZoneRules`; lưu offset hoặc instant đã quyết định khi cần phân biệt một giờ trùng.