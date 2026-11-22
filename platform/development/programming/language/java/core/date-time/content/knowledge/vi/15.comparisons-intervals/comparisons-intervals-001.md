# `equals()`, `compareTo()`, `isBefore()` và `isAfter()` theo từng kiểu ngày giờ

Khi so sánh hai giá trị thời gian, cần làm rõ “bằng nhau” hoặc “trước/sau” theo nghĩa nào. Hai giá trị có thể cùng chỉ **một instant** nhưng khác cách ghi offset; hai `ZonedDateTime` có thể cùng ngày giờ địa phương nhưng thuộc vùng/offset khác; hai `Period` có thể biểu diễn các thành phần khác nhau dù khi áp vào một ngày cụ thể lại tạo cùng kết quả.

Java cung cấp `equals()` và `compareTo()` cho nhiều kiểu giá trị; một số kiểu ngày giờ còn có `isBefore()`, `isAfter()` hoặc `isEqual()`. Nhưng ý nghĩa chính xác **phụ thuộc kiểu dữ liệu**. Không có một quy tắc chung rằng mọi phương thức đều so “thời điểm tuyệt đối”.

Bài này hướng dẫn cách chọn phép so sánh theo `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `ZonedDateTime`, `Duration` và `Period`; chỉ ra những khác biệt có ý nghĩa khi kiểm tra thời hạn, sắp xếp sự kiện, so dữ liệu API và xử lý múi giờ.

## 1. Ba câu hỏi khác nhau cần phân biệt

Trước khi chọn phương thức, hãy xác định điều gì cần được so sánh:

1. **Giá trị có giống nhau theo định nghĩa của kiểu không?** Dùng `equals()`. Ví dụ `OffsetDateTime` còn chứa offset; `ZonedDateTime` còn chứa vùng.
2. **Giá trị nào đứng trước theo thứ tự tự nhiên của kiểu?** Dùng `compareTo()` nếu kiểu triển khai `Comparable`. Thứ tự tự nhiên được mỗi lớp định nghĩa riêng.
3. **Sự kiện nào xảy ra trước trên dòng thời gian?** Với thời điểm tuyệt đối, so bằng `Instant` hoặc dùng phương thức so sánh được định nghĩa theo instant, như `isBefore()` của `OffsetDateTime`/`ZonedDateTime`.

Ba câu hỏi có thể cho kết quả khác nhau. `equals()` trả `false` không có nghĩa hai giá trị nhất thiết đại diện hai instant khác nhau; ngược lại, hai `LocalDateTime` bằng nhau cũng không xác định được cùng một instant nếu chưa có vùng/offset.

## 2. `equals()`: bằng nhau theo kiểu dữ liệu

`equals(Object)` kiểm tra sự bằng nhau theo hợp đồng của chính lớp. Không nên tự giả định mọi lớp chỉ so những trường mình đang quan tâm.

### 2.1. Kiểu ngày giờ địa phương

Với `LocalDate`, `LocalTime` và `LocalDateTime`, không có offset hoặc zone:

~~~java
LocalDate d1 = LocalDate.of(2026, 6, 1);
LocalDate d2 = LocalDate.of(2026, 6, 1);
LocalDate d3 = LocalDate.of(2026, 6, 2);

System.out.println(d1.equals(d2)); // true
System.out.println(d1.equals(d3)); // false
~~~

`LocalDateTime.equals()` cũng so khớp giá trị ngày và giờ địa phương. Nó không thể xác nhận hai thời điểm tuyệt đối, bởi `LocalDateTime` không mang offset hoặc múi giờ.

Ví dụ, hai lịch hẹn đều ghi `2026-06-01T09:00` nhưng một lịch ở Hà Nội, một lịch ở Tokyo sẽ có cùng `LocalDateTime`; instant chỉ xác định được khi bổ sung vùng phù hợp. Do đó, đừng dùng giá trị địa phương đơn thuần để so các sự kiện ở những nơi khác nhau.

### 2.2. `Instant.equals()`

`Instant` đại diện mốc tuyệt đối. Hai `Instant` bằng nhau khi cùng mốc đến độ chính xác nano giây:

~~~java
Instant a = Instant.parse("2026-06-01T10:00:00Z");
Instant b = Instant.parse("2026-06-01T12:00:00+02:00");

System.out.println(a.equals(b)); // true
~~~

Hai chuỗi có cách ghi khác nhau nhưng cùng một instant. Với `Instant`, không tồn tại thành phần offset hoặc tên vùng cần so sánh.

### 2.3. `OffsetDateTime.equals()` và `isEqual()`

`OffsetDateTime` lưu ngày giờ cùng offset. `equals()` xét cả giá trị ngày giờ địa phương và offset; `isEqual()` kiểm tra xem hai giá trị biểu diễn cùng instant hay không.

~~~java
OffsetDateTime a =
        OffsetDateTime.parse("2026-06-01T12:00:00+02:00");
OffsetDateTime b =
        OffsetDateTime.parse("2026-06-01T10:00:00Z");

System.out.println(a.equals(b));  // false
System.out.println(a.isEqual(b)); // true
System.out.println(a.toInstant().equals(b.toInstant())); // true
~~~

Cả hai cùng là `2026-06-01T10:00:00Z` khi quy đổi thành instant, nhưng `a` ghi giờ địa phương 12:00 với `+02:00` còn `b` ghi 10:00 với `Z`. Vì offset là một phần của `OffsetDateTime`, hai đối tượng không bằng nhau theo `equals()`.

### 2.4. `ZonedDateTime.equals()` và `isEqual()`

`ZonedDateTime` chứa ngày giờ, offset đang áp dụng và zone. `equals()` xét tính đầy đủ của biểu diễn vùng; `isEqual()` chỉ xét cùng instant trên dòng thời gian:

~~~java
Instant moment = Instant.parse("2026-06-01T10:00:00Z");
ZonedDateTime utc = moment.atZone(ZoneId.of("UTC"));
ZonedDateTime paris = moment.atZone(ZoneId.of("Europe/Paris"));

System.out.println(utc.equals(paris));  // false
System.out.println(utc.isEqual(paris)); // true
~~~

Hai đối tượng mô tả cùng sự kiện tại hai vùng hiển thị khác nhau. `equals()` trả `false` vì vùng/biểu diễn khác; `isEqual()` trả `true` vì instant giống nhau.

**Quy tắc thực tế:** dùng `equals()` khi cần so sánh cả giá trị và ngữ cảnh mà kiểu giữ lại; dùng `isEqual()` hoặc `toInstant()` khi câu hỏi là “cùng thời điểm thật hay không?”.

## 3. `compareTo()`: thứ tự tự nhiên không đồng nghĩa với equals

`compareTo(other)` trả số âm nếu đối tượng đứng trước `other` theo thứ tự tự nhiên, số dương nếu đứng sau, và 0 nếu thứ tự tự nhiên coi hai giá trị tương đương ở mức so sánh. Đừng dựa vào việc kết quả nhất thiết là `-1` hoặc `1`; hợp đồng chỉ yêu cầu dấu âm, 0 hoặc dương.

Với `LocalDate`, thứ tự là ngày lịch; với `LocalTime` là giờ; với `LocalDateTime` là ngày giờ địa phương:

~~~java
LocalDate a = LocalDate.of(2026, 5, 31);
LocalDate b = LocalDate.of(2026, 6, 1);

System.out.println(a.compareTo(b) < 0); // true
~~~

Ví dụ trên dễ hiểu vì kiểu không có múi giờ và nhu cầu cũng chỉ là so lịch. Với kiểu chứa offset hoặc vùng, quy tắc thứ tự có nhiều chi tiết hơn.

### 3.1. `OffsetDateTime.compareTo()`

`OffsetDateTime.compareTo()` ưu tiên thứ tự theo instant. Khi hai giá trị cùng instant, nó còn dùng thông tin ngày giờ địa phương để tạo thứ tự tự nhiên phân biệt các biểu diễn khác nhau. Vì vậy, **hai giá trị có cùng instant không bắt buộc cho `compareTo() == 0`**.

~~~java
OffsetDateTime a =
        OffsetDateTime.parse("2026-06-01T12:00:00+02:00");
OffsetDateTime b =
        OffsetDateTime.parse("2026-06-01T10:00:00Z");

System.out.println(a.isEqual(b)); // true
System.out.println(a.compareTo(b) == 0); // false
System.out.println(a.isBefore(b)); // false
System.out.println(a.isAfter(b));  // false
~~~

Hai instant bằng nhau nên cả `isBefore` và `isAfter` đều là `false`. Nhưng `compareTo` có thể dùng phần ngày giờ địa phương làm tie-breaker; `a` có giờ địa phương 12:00, `b` có 10:00, nên phép so sánh tự nhiên không trả 0.

Do đó, nếu cần sắp xếp theo thời điểm, cách rõ nhất là sắp xếp bằng `toInstant()` hoặc dùng comparator theo `OffsetDateTime.toInstant()`. Nếu cần phát hiện cùng instant, dùng `isEqual()`.

### 3.2. `ZonedDateTime.compareTo()`

`ZonedDateTime.compareTo()` cũng so theo instant trước và có thể phân biệt các biểu diễn vùng/địa phương khi hai instant bằng nhau. Để kiểm tra cùng instant, dùng `isEqual()`; để kiểm tra đối tượng cùng biểu diễn đầy đủ, dùng `equals()`.

~~~java
Instant instant = Instant.parse("2026-06-01T10:00:00Z");
ZonedDateTime a = instant.atZone(ZoneId.of("UTC"));
ZonedDateTime b = instant.atZone(ZoneId.of("Europe/Paris"));

System.out.println(a.isEqual(b)); // true
System.out.println(a.equals(b));  // false
~~~

Khi sắp xếp `ZonedDateTime` cho lịch hiển thị theo vùng, hãy xác định mục tiêu: thứ tự sự kiện thực tế, thứ tự giờ trên đồng hồ hay nhóm theo khu vực. Các mục tiêu đó không thể thay thế tùy tiện cho nhau.

### 3.3. `Instant.compareTo()`

Với `Instant`, thứ tự tự nhiên đúng là thứ tự trên dòng thời gian:

~~~java
Instant earlier = Instant.parse("2026-06-01T09:59:59Z");
Instant later = Instant.parse("2026-06-01T10:00:00Z");

System.out.println(earlier.compareTo(later) < 0); // true
System.out.println(earlier.isBefore(later));       // true
System.out.println(later.isAfter(earlier));        // true
~~~

Vì không có offset/zone trong giá trị, `Instant.compareTo()` và các phép kiểm tra trước/sau thống nhất theo mốc tuyệt đối.

## 4. `isBefore()`, `isAfter()` và `isEqual()`

Các phương thức này có sẵn trên nhiều kiểu ngày giờ như `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime` và `ZonedDateTime` (chữ ký khác nhau theo lớp). Hãy đọc ý nghĩa theo lớp:

| Kiểu | Ý nghĩa của isBefore/isAfter |
| --- | --- |
| `LocalDate` | Trước/sau theo ngày lịch |
| `LocalTime` | Trước/sau theo giờ trên đồng hồ; không có ngày |
| `LocalDateTime` | Trước/sau theo thứ tự ngày giờ địa phương; không xét zone |
| `Instant` | Trước/sau trên dòng thời gian tuyệt đối |
| `OffsetDateTime` | Trước/sau theo instant |
| `ZonedDateTime` | Trước/sau theo instant |
| `Duration` | Không có `isBefore()/isAfter()`; so bằng `compareTo()` hoặc tính dấu của Duration |
| `Period` | Không có `compareTo()/isBefore()/isAfter()` vì không có độ dài tuyến tính cố định |

`isEqual()` của `OffsetDateTime` và `ZonedDateTime` là cách so sự bằng nhau theo instant. `isEqual()` của kiểu địa phương chỉ so giá trị ngày/giờ theo ngữ nghĩa local tương ứng; nó không thể bổ sung timezone còn thiếu.

Một lưu ý: `LocalTime` chỉ có giờ, không có ngày. Ví dụ 23:00 so với 01:00 theo thứ tự trong cùng một ngày thì 23:00 sau 01:00, nhưng nếu hai giờ thuộc hai ngày khác nhau thì cần thêm ngày để diễn giải thứ tự sự kiện. Không dùng riêng `LocalTime` làm thứ tự toàn cục của lịch.

## 5. `Duration`: so sánh độ dài, không so các mốc

`Duration` biểu diễn lượng thời gian. `equals()` so độ dài đã chuẩn hóa; `compareTo()` sắp xếp theo độ dài. Nó không đại diện mốc bắt đầu hay kết thúc:

~~~java
Duration a = Duration.ofSeconds(60);
Duration b = Duration.ofMinutes(1);
Duration c = Duration.ofSeconds(61);

System.out.println(a.equals(b)); // true
System.out.println(a.compareTo(b)); // 0
System.out.println(a.compareTo(c) < 0); // true
System.out.println(a.isNegative()); // false
~~~

Hai giá trị `ofSeconds(60)` và `ofMinutes(1)` bằng nhau vì cả hai biểu diễn đúng 60 giây. `Duration` có `isNegative()` và `isZero()`, nhưng không có `isBefore()` hay `isAfter()` bởi những tên đó dùng để nói một mốc đứng trước mốc khác. So hai duration bằng `compareTo`.

Để so hai mốc, hãy so `Instant`. Để so hai khoảng, so `Duration`. Đừng nhầm “duration ngắn hơn” với “thời điểm bắt đầu sớm hơn”.

## 6. `Period`: trường hợp đặc biệt không thể so thứ tự chung

`Period` biểu diễn thành phần năm, tháng và ngày, chẳng hạn `P1Y` hoặc `P12M`. Nó **không triển khai `Comparable`**, nên không có `compareTo()`; cũng không có `isBefore()` hoặc `isAfter()`. Lý do là hai khoảng lịch không có một độ dài cố định để so nếu chưa biết ngày bắt đầu và quy tắc lịch.

~~~java
Period oneYear = Period.ofYears(1);
Period twelveMonths = Period.ofMonths(12);

System.out.println(oneYear.equals(twelveMonths)); // false
System.out.println(oneYear);      // P1Y
System.out.println(twelveMonths); // P12M
~~~

`equals()` so các thành phần đã lưu trong `Period`, không tự chuẩn hóa tất cả period về cùng một đơn vị. Vì vậy `P1Y` và `P12M` không bằng nhau theo `equals()` dù thường có tác động tương tự khi áp vào nhiều ngày ISO; quy tắc cuối tháng, năm nhuận và cách chuẩn hóa khiến không nên giả định phép đổi đó luôn tương đương về mặt nghiệp vụ.

Nếu cần so hai `Period`, hãy xác định **ngày bắt đầu hoặc miền nghiệp vụ** trước, rồi áp mỗi period vào ngày đó và so các kết quả. Một lựa chọn khác là quy định một chuẩn quy đổi cụ thể, chẳng hạn “mọi tháng tính như 30 ngày”, nhưng đó là luật nghiệp vụ riêng, không phải độ dài nội tại của `Period`.

## 7. Không gộp “giống nhau”, “cùng instant” và “thứ tự”

Bảng sau giúp chọn phép so sánh:

| Mục tiêu | Phương thức nên dùng | Điều cần nhớ |
| --- | --- | --- |
| Hai `Instant` cùng mốc | `equals()` | So mốc tuyệt đối |
| Hai `OffsetDateTime` cùng instant | `isEqual()` hoặc so `toInstant()` | `equals()` còn xét offset/giờ địa phương |
| Hai `ZonedDateTime` cùng instant | `isEqual()` | `equals()` còn xét biểu diễn vùng |
| Hai `LocalDateTime` cùng ngày giờ địa phương | `equals()` | Không suy ra cùng instant |
| Sắp xếp các giao dịch | So/sắp xếp theo `Instant` | Không phụ thuộc múi giờ hiển thị |
| Sắp xếp lịch địa phương trong một vùng | So `LocalDateTime` khi đó là mục tiêu | Phải xử lý gap/overlap khi chuyển thành instant |
| So độ dài timeout | `Duration.compareTo()` | So khoảng thời gian |
| So hai `Period` | Áp vào mốc/ngữ cảnh đã xác định | Không có thứ tự nội tại chung |
| Xác định mốc A trước mốc B | `isBefore()` phù hợp kiểu hoặc `Instant` | Xác định trước ý nghĩa “trước” |

Đối với dữ liệu sự kiện đa múi giờ, một quy tắc an toàn thường là **chuẩn hóa sang `Instant` để so/sắp xếp thời điểm**, rồi giữ zone riêng để hiển thị. Nếu nghiệp vụ cần so ngày hoặc giờ lịch địa phương, dùng kiểu local tương ứng và không giả định nó chứa thông tin instant.

## 8. Bài toán thực tế: kiểm tra thời hạn

Giả sử một mã OTP hợp lệ trong năm phút sau khi tạo. Ta cần so sánh **mốc hiện tại** với deadline:

~~~java
Instant createdAt = Instant.parse("2026-05-01T10:00:00Z");
Instant expiresAt = createdAt.plus(Duration.ofMinutes(5));

Instant nowBefore = Instant.parse("2026-05-01T10:04:59Z");
Instant nowExact = Instant.parse("2026-05-01T10:05:00Z");

System.out.println(nowBefore.isBefore(expiresAt)); // true
System.out.println(nowExact.isBefore(expiresAt));  // false
System.out.println(!nowExact.isBefore(expiresAt)); // true
~~~

Nếu quy ước “đúng deadline được xem là đã hết hạn”, điều kiện `!now.isBefore(expiresAt)` xử lý đúng ranh giới. Việc dùng `LocalDateTime` không có zone để kiểm tra deadline trên các máy ở nhiều vùng sẽ tạo rủi ro; dùng `Instant` cho mốc hết hạn.

Chính sách về độ lệch đồng hồ và thời gian phía client vẫn là vấn đề hệ thống riêng. `equals()/isBefore()` không xác thực nguồn thời gian; chúng chỉ so các giá trị đã cung cấp.

## 9. Chương trình Java 17+ chạy độc lập

Chương trình minh họa: hai offset khác nhau có cùng instant; hai vùng hiển thị cùng instant; so độ dài Duration; và so các Period theo biểu diễn. Kết quả dùng giá trị cố định, không gọi đồng hồ thực.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TemporalComparisonDemo {
    public static void main(String[] args) {
        OffsetDateTime offsetA =
                OffsetDateTime.parse("2026-06-01T12:00:00+02:00");
        OffsetDateTime offsetB =
                OffsetDateTime.parse("2026-06-01T10:00:00Z");

        System.out.println("offsetEquals=" + offsetA.equals(offsetB));
        System.out.println("offsetIsEqual=" + offsetA.isEqual(offsetB));
        System.out.println("offsetBefore=" + offsetA.isBefore(offsetB));
        System.out.println("offsetAfter=" + offsetA.isAfter(offsetB));
        System.out.println("offsetCompareZero="
                + (offsetA.compareTo(offsetB) == 0));

        Instant point = offsetA.toInstant();
        ZonedDateTime utc = point.atZone(ZoneId.of("UTC"));
        ZonedDateTime paris = point.atZone(ZoneId.of("Europe/Paris"));
        System.out.println("zonedEquals=" + utc.equals(paris));
        System.out.println("zonedIsEqual=" + utc.isEqual(paris));

        Duration minute = Duration.ofMinutes(1);
        Duration sixtySeconds = Duration.ofSeconds(60);
        System.out.println("durationEquals=" + minute.equals(sixtySeconds));
        System.out.println("durationCompare="
                + minute.compareTo(Duration.ofSeconds(61)));

        Period oneYear = Period.ofYears(1);
        Period twelveMonths = Period.ofMonths(12);
        System.out.println("periodEquals=" + oneYear.equals(twelveMonths));
        System.out.println("periodA=" + oneYear);
        System.out.println("periodB=" + twelveMonths);
    }
}
~~~

Lưu file thành `TemporalComparisonDemo.java`, rồi chạy:

~~~bash
javac TemporalComparisonDemo.java
java TemporalComparisonDemo
~~~

Đầu ra:

~~~text
offsetEquals=false
offsetIsEqual=true
offsetBefore=false
offsetAfter=false
offsetCompareZero=false
zonedEquals=false
zonedIsEqual=true
durationEquals=true
durationCompare=-1
periodEquals=false
periodA=P1Y
periodB=P12M
~~~

Giải thích các dòng quan trọng:

1. `offsetEquals=false` vì giờ/offset của hai `OffsetDateTime` khác nhau.
2. `offsetIsEqual=true` vì cả hai cùng instant `2026-06-01T10:00:00Z`.
3. `offsetBefore` và `offsetAfter` đều false vì hai instant bằng nhau.
4. `offsetCompareZero=false` vì `compareTo` có tie-breaker theo biểu diễn địa phương khi instant bằng nhau.
5. Hai `ZonedDateTime` đều bắt đầu từ một `Instant` nhưng dùng vùng UTC và Paris, nên `equals` false và `isEqual` true.
6. Hai Duration một phút bằng nhau; một phút nhỏ hơn 61 giây nên `compareTo` trả giá trị âm (ở ví dụ này là -1).
7. `P1Y` và `P12M` khác nhau theo thành phần của `Period`. Không gọi `compareTo` trên `Period` vì lớp không hỗ trợ so thứ tự tổng quát.

## 10. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng `OffsetDateTime.equals()` để hỏi “cùng instant không?” | Equals xét offset/giờ địa phương nữa | Dùng `isEqual()` hoặc so `toInstant()` |
| Dùng `ZonedDateTime.equals()` để gom sự kiện đa múi giờ | Vùng/biểu diễn có thể khác dù cùng instant | Chuẩn hóa `Instant` khi cần cùng sự kiện |
| Dùng `LocalDateTime` để so thứ tự sự kiện toàn cầu | Thiếu offset/zone | Xác định vùng rồi so instant |
| Nghĩ `compareTo() == 0` luôn tương đương `equals()` cho mọi kiểu | Thứ tự tự nhiên của kiểu offset có thể dùng tie-breaker | Đọc hợp đồng lớp; tách “cùng instant” khỏi “bằng đối tượng” |
| Gọi `Period.compareTo()` | `Period` không triển khai Comparable | Áp vào ngày/mốc bắt đầu hoặc định nghĩa quy tắc so riêng |
| Dùng `LocalTime` để xếp lịch qua nhiều ngày | Không chứa ngày | Dùng `LocalDateTime` hoặc kiểu có instant |
| Dùng `isBefore` trên mốc client gửi để kiểm tra bảo mật | Phép so không xác minh nguồn thời gian | Quy định nguồn giờ phía server và chính sách lệch đồng hồ |
| Coi `Duration` và `Period` là cùng kiểu khoảng | Duration cố định, Period theo lịch | Chọn theo ý nghĩa nghiệp vụ |
| Dùng kết quả số cụ thể của compareTo thay vì dấu | Hợp đồng không yêu cầu luôn trả -1/0/1 | Chỉ kiểm tra < 0, == 0 hoặc > 0 |

## 11. Quy trình chọn phép so sánh

Khi viết điều kiện hoặc comparator, hãy đi theo thứ tự:

1. **Đối tượng là mốc hay khoảng?** Mốc thường dùng `Instant`; độ dài dùng `Duration`; khoảng lịch dùng `Period`.
2. **Có cần so vùng/offset như một phần dữ liệu không?** Nếu có, `equals()` của kiểu giàu thông tin có thể là điều mong muốn.
3. **Cần cùng instant hay cùng biểu diễn?** Với `OffsetDateTime`/`ZonedDateTime`, dùng `isEqual()` cho cùng instant.
4. **Cần thứ tự nào?** Giờ địa phương, thứ tự tự nhiên, hay thứ tự tuyệt đối? Chọn kiểu/comparator cho rõ.
5. **Có mơ hồ do DST?** Chuyển local time thành instant sau khi xử lý gap/overlap.
6. **Cần kiểm tra ranh giới không?** Thời hạn cần test trước, đúng bằng và sau deadline.
7. **Dữ liệu đến từ đâu?** So sánh không tự kiểm tra timezone, chuẩn hóa dữ liệu, độ lệch đồng hồ hay tính đáng tin cậy của timestamp nguồn.

## 12. Bài tập tự kiểm tra

1. Tại sao `OffsetDateTime` có thể `equals()==false` nhưng `isEqual()==true`? Viết ví dụ với hai offset khác nhau.
2. Tạo hai `ZonedDateTime` từ một `Instant` ở UTC và Paris. Kiểm tra `equals`, `isEqual`, `toInstant`.
3. Nếu `OffsetDateTime.compareTo()` trả giá trị khác 0, điều đó có nhất thiết nghĩa hai instant khác nhau không? Kiểm tra trường hợp cùng instant nhưng khác offset.
4. So sánh `LocalDateTime` 23:00 và 01:00. Vì sao cần ngày nếu xếp thứ tự sự kiện qua nửa đêm?
5. Vì sao `Period.ofYears(1)` và `Period.ofMonths(12)` không bằng nhau theo `equals()`? Tại sao không tồn tại compareTo tổng quát cho Period?
6. Viết điều kiện kiểm tra deadline tại đúng thời điểm hết hạn. Quy định rõ deadline inclusive hay exclusive.
7. Xây comparator sắp xếp `OffsetDateTime` theo `toInstant()` thay vì thứ tự tự nhiên. Khi nào lựa chọn này phù hợp?
8. Viết test với hai `Instant` chỉ khác nhau 1 nano giây để kiểm tra độ chính xác so sánh.

**Ghi nhớ:** `equals()` trả lời **“hai giá trị có bằng nhau theo kiểu này không?”**; `compareTo()` trả lời **“chúng đứng ở vị trí nào trong thứ tự tự nhiên của kiểu?”**; `isBefore()/isAfter()` cho biết thứ tự theo ý nghĩa của lớp. Với `OffsetDateTime` và `ZonedDateTime`, dùng `isEqual()` khi cần xác nhận cùng instant. `Period` không có thứ tự tổng quát vì tháng/năm phụ thuộc lịch; để so sánh nó, phải cung cấp ngày bắt đầu hoặc quy tắc nghiệp vụ.