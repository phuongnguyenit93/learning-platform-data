# ZonedDateTime: Đổi múi giờ giữ giờ địa phương với withZoneSameLocal()

Một cuộc hẹn được nhập là **19:00 theo đồng hồ địa phương**. Khi chuyển cách diễn giải sang một múi giờ khác, có hai lựa chọn hoàn toàn khác nhau: **giữ 19:00** và chấp nhận thay đổi thời điểm thực, hoặc **giữ nguyên thời điểm thực** và chấp nhận giờ hiển thị thay đổi.

Trong Java, `ZonedDateTime.withZoneSameLocal(ZoneId zone)` thực hiện lựa chọn thứ nhất: tạo giá trị `ZonedDateTime` ở vùng mới và **cố giữ các thành phần ngày, giờ địa phương như cũ khi có thể**. Từ “khi có thể” rất quan trọng: do quy tắc chuyển đồng hồ mùa hè (DST) hoặc thay đổi offset, một giờ địa phương có thể **không tồn tại** hoặc **xảy ra hai lần** trong vùng đích.

Nếu mục tiêu là hiển thị **cùng sự kiện tại thời điểm không đổi** ở múi giờ khác, hãy dùng `withZoneSameInstant(...)`. Bài này tập trung vào `withZoneSameLocal(...)`, ý nghĩa nghiệp vụ và các trường hợp biên của nó.

## 1. Đầu tiên, phân biệt giờ địa phương và thời điểm thực

`ZonedDateTime` chứa ba nhóm thông tin:

- **Ngày và giờ địa phương**: ví dụ `2024-02-29T19:00`.
- **Múi giờ** (*ZoneId*): ví dụ `Asia/Ho_Chi_Minh`, với bộ quy tắc offset theo thời điểm.
- **Độ lệch UTC đang áp dụng** (*ZoneOffset*): ví dụ `+07:00`.

Từ bộ ngày giờ địa phương và offset, Java suy ra được **`Instant`**, tức một điểm trên trục thời gian toàn cục. Với `2024-02-29T19:00+07:00`:

~~~text
Giờ địa phương: 2024-02-29 19:00
Offset:         +07:00
Thời điểm UTC:  2024-02-29 12:00Z
~~~

Nếu thay offset thành `Z` (UTC) mà vẫn giữ `19:00`, ta sẽ có thời điểm thực `19:00Z`, **muộn hơn 7 giờ**. Đây là cơ chế chính phía sau `withZoneSameLocal(ZoneOffset.UTC)` với giá trị ví dụ.

## 2. Cú pháp và hành vi của withZoneSameLocal()

Phương thức thuộc lớp `java.time.ZonedDateTime`:

~~~java
ZonedDateTime result = source.withZoneSameLocal(destinationZone);
~~~

Tham số `destinationZone` là `ZoneId`; có thể là ID vùng như `Europe/Paris`, `America/New_York`, `Asia/Ho_Chi_Minh`, hoặc một `ZoneOffset` cố định như `ZoneOffset.UTC`.

Điều Java cố thực hiện:
1. Lấy **`source.toLocalDateTime()`** gồm năm, tháng, ngày, giờ, phút, giây, nano.
2. Diễn giải ngày giờ đó theo **quy tắc của vùng đích**.
3. Chọn offset hợp lệ theo quy tắc vùng đích, xử lý trường hợp giờ không tồn tại hoặc trùng lặp.
4. Trả một đối tượng `ZonedDateTime` ứng với vùng đích, thường có **`Instant` khác** nguồn.

Không có thao tác sửa đối tượng tại chỗ. `ZonedDateTime` là immutable: source vẫn giữ nguyên giá trị sau khi gọi phương thức.

~~~java
ZonedDateTime source = ZonedDateTime.of(
        2024, 2, 29, 19, 0, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime target = source.withZoneSameLocal(ZoneOffset.UTC);
// source: 2024-02-29T19:00+07:00[Asia/Ho_Chi_Minh]
// target: 2024-02-29T19:00Z
~~~

Vì ở ví dụ này 19:00 là giờ hợp lệ của cả hai vùng, **ngày và giờ địa phương giống nhau**. Tuy nhiên:

~~~text
source Instant = 2024-02-29T12:00:00Z
target Instant = 2024-02-29T19:00:00Z
~~~

Do đó `withZoneSameLocal` là thao tác **diễn giải lại giờ địa phương**, không phải cách dịch hiển thị của một sự kiện đã xảy ra.

## 3. Đối chiếu với withZoneSameInstant()

Hai phương thức dễ bị nhầm lẫn:

| Câu hỏi | `withZoneSameLocal(newZone)` | `withZoneSameInstant(newZone)` |
|---|---|---|
| Điều cố giữ | Ngày giờ **trên đồng hồ**, khi hợp lệ | **Cùng điểm thời gian** |
| Có thể thay đổi giờ hiển thị? | Có, khi rơi vào gap của vùng đích | Có, thường sẽ thay đổi |
| Có thể thay đổi `Instant`? | **Có**, thường thay đổi | **Không** |
| Khi nào dùng? | Ý định “giữ lịch 19:00 nhưng gán sang vùng khác” | Hiển thị cùng sự kiện ở vùng khác |
| Ví dụ từ 19:00 TP.HCM sang UTC | `19:00Z` | `12:00Z` |

~~~java
ZonedDateTime source = ZonedDateTime.of(
        2024, 2, 29, 19, 0, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime sameLocal =
        source.withZoneSameLocal(ZoneOffset.UTC);

ZonedDateTime sameInstant =
        source.withZoneSameInstant(ZoneOffset.UTC);
~~~

Kết quả:

~~~text
source      = 2024-02-29T19:00+07:00[Asia/Ho_Chi_Minh]
sameLocal   = 2024-02-29T19:00Z
sameInstant = 2024-02-29T12:00Z
~~~

Hãy hỏi rõ nghiệp vụ:

- “Cuộc họp xảy ra lúc 19:00 tại TP.HCM; đồng nghiệp ở UTC nhìn thấy giờ mấy?” → **`withZoneSameInstant`**, kết quả 12:00 UTC.
- “Đổi lịch 19:00 ở TP.HCM thành lịch 19:00 theo UTC” → **`withZoneSameLocal`**, tạo một thời điểm mới.

Một quy tắc chọn đơn giản là: với **event đã xảy ra, timestamp, audit log, đơn hàng, giao dịch**, thường giữ `Instant`. Với **giờ hẹn địa phương dự định áp dụng tại một khu vực khác**, có thể cần giữ `LocalDateTime` và diễn giải theo `ZoneId` mới.

## 4. Ví dụ Java 17: cùng giờ nhưng khác thời điểm

Tạo `source` như trong ví dụ. Hai lệnh sau kiểm chứng được sự khác biệt:

~~~java
boolean sameClock =
        source.toLocalDateTime().equals(sameLocal.toLocalDateTime());
// true khi chuyển sang UTC ở mốc này

boolean sameMoment =
        source.toInstant().equals(sameLocal.toInstant());
// false
~~~

`ZonedDateTime.isEqual(...)` so sánh theo **thời điểm thực**:

~~~java
source.isEqual(sameLocal);   // false
source.isEqual(sameInstant); // true
~~~

Chênh lệch giữa hai instant trong ví dụ:

~~~java
long hours = Duration.between(
        source.toInstant(), sameLocal.toInstant()).toHours();
// 7
~~~

Một điểm quan trọng: chỉ vì `source.getHour() == target.getHour()` không có nghĩa hai giá trị chỉ cùng một thời điểm. Nếu offset thay đổi, timestamp cũng đổi theo.

## 5. Giữ giờ địa phương “khi có thể”: gap do DST

Các vùng múi giờ không chỉ là độ lệch cố định. `ZoneId.of("America/New_York")` có quy tắc chuyển giờ mùa hè theo lịch địa phương. Năm 2024, ngày **10/03**, giờ địa phương ở New York nhảy từ **01:59:59...** lên **03:00**; khoảng **02:00–02:59** không tồn tại.

Giả sử ta có ngày giờ `2024-03-10 02:30` ở Paris, rồi yêu cầu giữ cùng giờ địa phương khi chuyển sang New York:

~~~java
ZonedDateTime inParis = ZonedDateTime.of(
        2024, 3, 10, 2, 30, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime inNewYork = inParis.withZoneSameLocal(
        ZoneId.of("America/New_York"));
~~~

Kết quả theo quy tắc 2024:

~~~text
Paris:    2024-03-10T02:30+01:00[Europe/Paris]
New York: 2024-03-10T03:30-04:00[America/New_York]
~~~

Vì 02:30 không tồn tại tại vùng đích, Java **dịch giờ địa phương tiến một giờ qua khoảng trống**. Không thể vừa giữ nguyên 02:30 vừa có `ZonedDateTime` hợp lệ tại New York trong khoảng đó.

Có thể kiểm tra bằng `ZoneRules`:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime requested = LocalDateTime.of(2024, 3, 10, 2, 30);
List<ZoneOffset> valid = ny.getRules().getValidOffsets(requested);
// valid rỗng: không offset nào hợp lệ với giờ 02:30 này
~~~

Đây là đoạn minh họa bên trong một phương thức, cần import `java.util.List` và các kiểu `java.time` liên quan.

**Bài học:** Đừng hứa rằng `withZoneSameLocal()` *luôn luôn* giữ nguyên ngày/giờ. Nó cố giữ giá trị địa phương, **nhưng phải giải quyết giờ không tồn tại theo quy tắc múi giờ đích**.

## 6. Overlap do DST: một giờ địa phương có thể xuất hiện hai lần

Ngày **03/11/2024**, tại `America/New_York`, khoảng giờ **01:00–01:59** xuất hiện hai lần khi đồng hồ kết thúc giờ mùa hè. Cùng một `LocalDateTime` `2024-11-03T01:30` có thể dùng hai offset:

~~~text
2024-11-03T01:30-04:00[America/New_York]
2024-11-03T01:30-05:00[America/New_York]
~~~

Đó là **hai instant khác nhau**, dù mặt đồng hồ đều hiển thị 01:30.

Nếu nguồn mang 01:30 theo giờ Paris (`+01:00`) rồi đổi sang New York:

~~~java
ZonedDateTime paris = ZonedDateTime.of(
        2024, 11, 3, 1, 30, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime ny = paris.withZoneSameLocal(
        ZoneId.of("America/New_York"));
// 2024-11-03T01:30-04:00[America/New_York]
~~~

Trong trường hợp overlap, khi offset hiện có của nguồn **hợp lệ ở vùng đích**, Java ưu tiên giữ offset đó. Nếu offset hiện có **không hợp lệ ở vùng đích**, Java thường chọn offset **sớm hơn trong danh sách hợp lệ** (thường là offset mùa hè, tại New York là `-04:00` ở mốc này).

Có thể chủ động chọn lần xuất hiện sau bằng:

~~~java
ZonedDateTime laterOccurrence = ny.withLaterOffsetAtOverlap();
// 2024-11-03T01:30-05:00[America/New_York]
~~~

Hoặc hỏi các offset hợp lệ:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);
List<ZoneOffset> offsets =
        ZoneId.of("America/New_York").getRules().getValidOffsets(local);
// [-04:00, -05:00] trên dữ liệu quy tắc 2024
~~~

Cần import `java.util.List` khi dùng danh sách. Đừng mặc định chọn offset nào là phù hợp cho mọi nghiệp vụ. Với lịch hẹn và dữ liệu được con người nhập tại thời điểm đồng hồ đổi giờ, cần xác định có ý định **lần 01:30 đầu tiên hay thứ hai** hay không.

## 7. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`ZonedSameLocalDemo.java`**:

~~~java
import java.time.*;
import java.util.List;

public class ZonedSameLocalDemo {
    public static void main(String[] args) {
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId utc = ZoneOffset.UTC;
        ZonedDateTime source = ZonedDateTime.of(
                2024, 2, 29, 19, 0, 0, 0, hcm);
        ZonedDateTime sameLocal = source.withZoneSameLocal(utc);
        ZonedDateTime sameInstant = source.withZoneSameInstant(utc);

        System.out.println("source = " + source);
        System.out.println("sameLocal = " + sameLocal);
        System.out.println("sameInstant = " + sameInstant);
        System.out.println("source instant = " + source.toInstant());
        System.out.println("sameLocal instant = " + sameLocal.toInstant());
        System.out.println("sameInstant instant = " + sameInstant.toInstant());
        System.out.println("same local fields = " +
                source.toLocalDateTime().equals(sameLocal.toLocalDateTime()));
        System.out.println("same instant local = " + source.isEqual(sameLocal));
        System.out.println("same instant converted = " + source.isEqual(sameInstant));
        System.out.println("local difference hours = " +
                Duration.between(
                        source.toInstant(), sameLocal.toInstant()).toHours());

        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneId newYork = ZoneId.of("America/New_York");
        ZonedDateTime gapSource = ZonedDateTime.of(
                2024, 3, 10, 2, 30, 0, 0, paris);
        ZonedDateTime gapResult = gapSource.withZoneSameLocal(newYork);
        System.out.println("gap source = " + gapSource);
        System.out.println("gap NY result = " + gapResult);
        System.out.println("gap local preserved = " +
                gapSource.toLocalDateTime().equals(gapResult.toLocalDateTime()));
        System.out.println("NY gap valid offsets = " +
                newYork.getRules().getValidOffsets(
                        LocalDateTime.of(2024, 3, 10, 2, 30)));

        ZonedDateTime overlapSource = ZonedDateTime.of(
                2024, 11, 3, 1, 30, 0, 0, paris);
        ZonedDateTime overlapResult = overlapSource.withZoneSameLocal(newYork);
        List<ZoneOffset> valid = newYork.getRules().getValidOffsets(
                overlapSource.toLocalDateTime());
        System.out.println("overlap source = " + overlapSource);
        System.out.println("overlap NY result = " + overlapResult);
        System.out.println("overlap valid offsets = " + valid);
        System.out.println("overlap later alternative = " +
                overlapResult.withLaterOffsetAtOverlap());
    }
}
~~~

Biên dịch/chạy (JDK 17+):

~~~bash
javac ZonedSameLocalDemo.java
java ZonedSameLocalDemo
~~~

Đầu ra đã được kiểm tra bằng `javac --release 17` với dữ liệu múi giờ của JDK được dùng để chạy ví dụ:

~~~text
source = 2024-02-29T19:00+07:00[Asia/Ho_Chi_Minh]
sameLocal = 2024-02-29T19:00Z
sameInstant = 2024-02-29T12:00Z
source instant = 2024-02-29T12:00:00Z
sameLocal instant = 2024-02-29T19:00:00Z
sameInstant instant = 2024-02-29T12:00:00Z
same local fields = true
same instant local = false
same instant converted = true
local difference hours = 7
gap source = 2024-03-10T02:30+01:00[Europe/Paris]
gap NY result = 2024-03-10T03:30-04:00[America/New_York]
gap local preserved = false
NY gap valid offsets = []
overlap source = 2024-11-03T01:30+01:00[Europe/Paris]
overlap NY result = 2024-11-03T01:30-04:00[America/New_York]
overlap valid offsets = [-04:00, -05:00]
overlap later alternative = 2024-11-03T01:30-05:00[America/New_York]
~~~

Đọc chương trình theo ba nhóm:

1. **Trường hợp bình thường:** chuyển `2024-02-29T19:00` TP.HCM sang UTC giữ nguyên 19:00 về mặt đồng hồ, nhưng instant dịch +7 giờ. Cách giữ `Instant` cho kết quả 12:00Z.
2. **Gap:** 02:30 tại New York ngày 10/03/2024 không tồn tại, nên Java điều chỉnh lên 03:30.
3. **Overlap:** 01:30 tại New York ngày 03/11/2024 có hai offset `-04:00` và `-05:00`. Ví dụ chọn offset sớm hơn; `withLaterOffsetAtOverlap()` chọn giá trị sau.

Các quy tắc vùng đến từ tzdb tích hợp trong môi trường Java. Chính sách DST theo ngày đã minh họa là dữ liệu vùng cụ thể; kiểm tra lại khi chạy trên tzdb khác hoặc nếu ứng dụng phải bảo toàn cách diễn giải các lịch tương lai sau khi quy tắc múi giờ được cập nhật.

## 8. Ứng dụng thực tế: lựa chọn đúng theo ý định người dùng

### Thay vùng áp dụng cho giờ hẹn đã được nhập

Giả sử công cụ lên lịch có cuộc hẹn `2024-02-29 19:00` theo giờ TP.HCM, nhưng người dùng quyết định thay địa điểm thành một vùng khác và muốn **giữ nguyên 19:00 của đồng hồ ở nơi mới**. Có thể dùng `withZoneSameLocal(newZone)`, với điều kiện kiểm tra ngày/giờ đó có hợp lệ trong vùng mới hay không.

Trong ứng dụng đặt lịch thật, tốt hơn nên phân biệt rõ dữ liệu **ý định lịch dân sự** gồm `LocalDateTime` + `ZoneId` và **thời điểm thực để thực thi** là `Instant` sau khi giải quyết các quy tắc múi giờ.

### Hiển thị sự kiện cho người ở vùng khác

Một sự kiện đã xảy ra tại `2024-02-29T12:00:00Z`. Khi người xem ở TP.HCM, hiển thị 19:00; khi xem ở UTC, hiển thị 12:00. Đây là trường hợp **`withZoneSameInstant`**, hoặc bắt đầu từ `Instant` và gọi `instant.atZone(userZone)`.

Dùng `withZoneSameLocal` tại đây sẽ biến một event thành event khác, gây sai log, deadline, ngày giao dịch hoặc dữ liệu đồng bộ.

### Đổi múi giờ của deadline

Một hệ thống có deadline “20:00 giờ New York” là thời hạn tính theo **lịch địa phương của vùng**. Nếu người quản trị muốn chuyển chính sách sang “20:00 giờ Paris”, đây là thay đổi ý nghĩa thời điểm hết hạn. Có thể liên quan `withZoneSameLocal`, nhưng **phải áp dụng quy tắc DST và quyết định gap/overlap**, đồng thời xác nhận đây thật sự là thay đổi yêu cầu nghiệp vụ.

Ngược lại, nếu cần hiển thị **cùng deadline không thay đổi** theo Paris, `withZoneSameInstant` là lựa chọn đúng.

### Thiết kế giao diện: hai hành vi nên có tên rõ ràng

Với lựa chọn “Đổi múi giờ” trong UI, nên diễn đạt rõ:

| Lựa chọn | Hành vi Java |
|---|---|
| “Giữ thời điểm; xem theo giờ vùng khác” | `withZoneSameInstant` |
| “Giữ giờ trên đồng hồ; áp dụng vùng khác” | `withZoneSameLocal` |

Chỉ một nút “Change timezone” không đủ giải thích ý định của người dùng; lỗi dễ xảy ra khi người dùng không biết timestamp có đổi hay không.

## 9. Những sai lầm dễ gặp

| Nhầm lẫn | Điều thực tế xảy ra | Cách xử lý |
|---|---|---|
| Nghĩ `withZoneSameLocal` luôn giữ cùng `Instant` | Đổi offset thường đổi instant | Dùng `withZoneSameInstant` khi cần cùng thời điểm |
| Nghĩ `withZoneSameLocal` luôn giữ chính xác giờ đồng hồ | Giờ đích có thể rơi vào DST gap và phải điều chỉnh | Kiểm tra `ZoneRules.getValidOffsets(...)` |
| Nghĩ mọi `LocalDateTime` có đúng một instant | DST overlap có thể có hai offset; gap có thể không có offset nào | Xác định chính sách gap/overlap |
| Dùng `withZoneSameLocal` để hiển thị event đã ghi timestamp | Vô tình dịch thời điểm xảy ra sự kiện | Bắt đầu từ `Instant` hoặc dùng `withZoneSameInstant` |
| Chỉ so `getHour()` rồi kết luận bằng nhau | Bỏ qua ngày, phút, giây, offset và instant | So `toLocalDateTime()` khi cần giờ địa phương; `isEqual()` khi cần instant |
| Lầm `ZoneOffset` với `ZoneId` vùng | Offset cố định không có lịch sử thay đổi vùng | Giữ ID vùng khi nghiệp vụ cần quy tắc giờ dân sự |
| Cho rằng gọi phương thức sẽ sửa source | `ZonedDateTime` bất biến | Gán hoặc nhận kết quả trả về |
| Dựa hoàn toàn vào `equals` để so cùng thời điểm | `equals` xét đầy đủ biểu diễn, vùng và offset | Dùng `isEqual(...)` hoặc so `toInstant()` |
| Coi giá trị DST trong ví dụ là bất biến trên mọi JDK | Quy tắc timezone có thể cập nhật | Cố định dữ liệu test phù hợp và kiểm tra phiên bản tzdb |
| Không xử lý `null` ở `newZone` | Gọi phương thức với zone null bị lỗi | Cung cấp `ZoneId` hợp lệ, xử lý dữ liệu nhập |

## 10. Câu hỏi tự kiểm tra

1. `withZoneSameLocal(...)` cố giữ yếu tố nào? **Ngày giờ địa phương**, nếu hợp lệ tại vùng đích.
2. Từ `2024-02-29T19:00+07:00[Asia/Ho_Chi_Minh]` sang UTC với `withZoneSameLocal` sẽ là gì? **`2024-02-29T19:00Z`**.
3. Cùng nguồn trên, dùng `withZoneSameInstant(UTC)` sẽ là gì? **`2024-02-29T12:00Z`**.
4. Hai kết quả trên có cùng `Instant` không? **Không**, khác 7 giờ.
5. `withZoneSameLocal` có sửa đối tượng gốc không? **Không**, `ZonedDateTime` là immutable.
6. Nếu giờ địa phương tại vùng đích rơi vào DST gap, Java thường làm gì? **Dời giờ tiến qua khoảng trống** theo quy tắc của vùng.
7. Nếu giờ địa phương bị lặp trong overlap, có bao nhiêu offset hợp lệ? **Hai** trong trường hợp overlap DST thông thường; cần chọn offset phù hợp.
8. Muốn xem offset hợp lệ cho một local datetime, dùng gì? **`zone.getRules().getValidOffsets(localDateTime)`**.
9. Muốn dùng thời điểm xuất hiện thứ hai khi overlap trong `ZonedDateTime`, dùng gì? **`withLaterOffsetAtOverlap()`**.
10. Với giao dịch đã xảy ra và chỉ muốn hiển thị theo vùng khác, chọn cách nào? **`withZoneSameInstant` hoặc `instant.atZone(targetZone)`**.

**Ghi nhớ:** `withZoneSameLocal()` là thao tác **đổi cách gắn múi giờ cho giờ địa phương**, thường làm thay đổi `Instant`. Nó giữ ngày giờ địa phương **khi có thể**, nhưng DST gap/overlap đòi hỏi xử lý quy tắc vùng. Nếu cần giữ **cùng một thời điểm thực**, chọn `withZoneSameInstant()`.

### Tài liệu tham khảo

- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java SE 17 — LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [Java SE 17 — ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
