# Clock cố định và các ranh giới ngày giờ trong Java

## 1. Mục tiêu và phạm vi

Ứng dụng thường phải xử lý những quy tắc phụ thuộc thời điểm: đơn hàng hết hạn lúc nửa đêm, báo cáo theo ngày địa phương, lịch làm việc, thời hạn thanh toán, sự kiện lặp lại theo múi giờ hoặc khoảng thời gian có thay đổi giờ mùa hè. Nếu code gọi trực tiếp thời gian hệ thống ở khắp nơi, test sẽ phụ thuộc vào ngày/giờ thực tế, môi trường chạy và múi giờ máy.

Trong chủ đề **Kiểm thử và tối ưu**, bài học này tập trung vào cách làm cho logic thời gian có thể kiểm thử lặp lại. Java cung cấp **java.time.Clock** để biểu diễn nguồn thời gian có thể thay thế. Nhờ truyền Clock vào logic nghiệp vụ, test có thể dùng **Clock.fixed** để luôn quan sát một thời điểm xác định. Các kiểu **Instant, LocalDate, LocalTime, LocalDateTime, ZonedDateTime, ZoneId, ZoneRules, Duration và Period** giúp mô hình hóa các ranh giới thời gian một cách rõ ràng.

Các API trong bài thuộc java.time, có từ Java 8 và vẫn được duy trì trong JDK hiện đại. Ví dụ dùng Java 17+, biên dịch bằng **javac --release 17**; stdout được kiểm tra trên **OpenJDK 24.0.2**.

Sau bài học, bạn có thể:

1. Phân biệt thời điểm tuyệt đối (Instant), ngày địa phương (LocalDate), giờ địa phương (LocalTime) và ngày giờ có múi giờ.
2. Dùng Clock.fixed để tạo test không phụ thuộc đồng hồ hệ thống.
3. Truyền Clock qua constructor hoặc method thay vì gọi now() trực tiếp trong logic nghiệp vụ.
4. Dùng Clock.offset và Clock.tick để mô phỏng thời gian tương lai/quá khứ và độ chính xác theo đơn vị.
5. Xác định đầu ngày và đầu ngày kế tiếp theo ZoneId.
6. Xây dựng khoảng thời gian **[start, end)** gồm start và loại trừ end.
7. Kiểm thử ngày DST có 23 giờ hoặc 25 giờ.
8. Hiểu DST gap (giờ địa phương không tồn tại) và overlap (giờ địa phương xuất hiện hai lần).
9. Chọn chính sách rõ ràng khi chuyển LocalDateTime thành ZonedDateTime.
10. Phân biệt Period (lịch) và Duration (thời lượng thực).
11. Tách múi giờ nghiệp vụ khỏi múi giờ mặc định của máy.
12. Viết test ổn định cho hết hạn, ngày nhuận, cuối tháng, ranh giới nửa đêm và thời điểm chuyển DST.
13. Biết khi nào cần Clock và khi nào cần đồng hồ đơn điệu System.nanoTime().

## 2. Những khái niệm thời gian cần tách biệt

Một lỗi phổ biến là dùng một kiểu ngày giờ cho mọi tình huống. Java có các kiểu riêng để biểu diễn các khái niệm khác nhau:

| Kiểu | Ý nghĩa | Có múi giờ/offset không? |
|---|---|---|
| Instant | Một điểm duy nhất trên timeline UTC | Không lưu ZoneId; đại diện thời điểm tuyệt đối |
| LocalDate | Ngày lịch, ví dụ 2025-01-31 | Không |
| LocalTime | Giờ trong ngày, ví dụ 09:30 | Không |
| LocalDateTime | Ngày + giờ trên đồng hồ địa phương | Không |
| ZoneId | Quy tắc múi giờ, ví dụ America/New_York | Là định danh quy tắc |
| ZoneOffset | Độ lệch cố định so với UTC, ví dụ -05:00 | Offset cố định |
| ZonedDateTime | Ngày giờ địa phương + ZoneId + offset được áp dụng | Có |
| Duration | Khoảng thời gian theo giây/nanosecond | Không gắn vùng |
| Period | Khoảng thời gian theo năm/tháng/ngày lịch | Không gắn vùng |

### Instant là thời điểm, LocalDateTime là giờ trên đồng hồ

Ví dụ 2024-03-10T06:30:00Z là một Instant duy nhất. Cùng thời điểm đó, ở New York có thể là 01:30 với offset -05:00; sau chuyển DST, một Instant khác có thể hiển thị là 03:30 với offset -04:00.

LocalDateTime 2024-03-10T02:30 tự nó không xác định được Instant nào. Muốn chuyển thành thời điểm, cần một ZoneId và xử lý quy tắc vùng tại ngày giờ đó.

### ZoneId và ZoneOffset khác nhau

- ZoneOffset.of("-05:00") biểu diễn offset cố định; nó không tự chuyển thành -04:00 khi New York đổi DST.
- ZoneId.of("America/New_York") mang quy tắc vùng theo dữ liệu time-zone của runtime; offset thay đổi theo thời điểm.
- Với lịch dân sự, họp, ngày làm việc, hạn theo vùng địa lý, thường cần **ZoneId vùng**.
- Với timestamp từ giao thức hoặc thời điểm tuyệt đối, dùng Instant; chỉ chuyển sang vùng khi hiển thị hoặc áp dụng quy tắc địa phương.

**Không dùng tên viết tắt mơ hồ** như EST, CST để thay cho region ID nếu nghiệp vụ cần quy tắc DST. Ưu tiên các ID rõ ràng như America/New_York, Europe/Paris, Asia/Ho_Chi_Minh.

## 3. Clock là nguồn thời gian có thể thay thế

Clock là một abstraction cung cấp instant hiện tại và zone dùng để chuyển instant thành ngày giờ địa phương. Các factory thường dùng:

~~~java
Clock systemUtc = Clock.systemUTC();
Clock systemNewYork = Clock.system(ZoneId.of("America/New_York"));
Clock fixed = Clock.fixed(
        Instant.parse("2025-01-31T23:30:00Z"), ZoneOffset.UTC);
~~~

- Clock.systemUTC() cung cấp thời gian hệ thống với UTC.
- Clock.system(zone) cung cấp thời gian hệ thống theo zone tường minh.
- Clock.systemDefaultZone() dùng default zone của máy; phù hợp khi thật sự muốn theo cấu hình host, nhưng tạo phụ thuộc môi trường.
- Clock.fixed(instant, zone) luôn trả cùng một instant.
- Clock.offset(baseClock, duration) tạo clock trả thời điểm lệch một khoảng so với clock gốc.
- Clock.tick(baseClock, duration) tạo clock làm tròn/truncate theo đơn vị tick được chỉ định.

Clock là object immutable/thread-safe theo các implementation chuẩn của API. Clock.fixed đặc biệt hữu ích trong test vì không phụ thuộc thời gian chạy thực.

### Vì sao Clock.fixed không phải đồng hồ thật?

Nó luôn trả cùng một Instant; chờ 10 giây không làm thời gian tăng. Đây là chủ đích: test có thể tái lập. Nếu cần mô phỏng tiến về tương lai, dùng Clock.offset hoặc một abstraction clock do test kiểm soát.

### Đừng gọi now() không tham số sâu trong nghiệp vụ

~~~java
// Khó kiểm thử vì phụ thuộc đồng hồ hệ thống:
LocalDate today = LocalDate.now();

// Có thể kiểm soát trong test:
LocalDate today = LocalDate.now(clock);
~~~

Các phương thức now(clock) cho phép thay nguồn thời gian. Nếu một class có nhiều thao tác phụ thuộc thời điểm, truyền Clock qua constructor để tất cả dùng chung một nguồn thời gian và zone rõ ràng.
## 4. Ví dụ Java hoàn chỉnh 1 — kiểm soát thời gian bằng Clock.fixed

Tạo file **FixedClockDemo.java**:

~~~java
import java.time.*;

public class FixedClockDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2024-03-10T06:30:00Z");
        ZoneId newYork = ZoneId.of("America/New_York");
        Clock clock = Clock.fixed(instant, newYork);
        System.out.println("instant=" + Instant.now(clock));
        System.out.println("date=" + LocalDate.now(clock));
        System.out.println("time=" + LocalTime.now(clock));
        System.out.println("zoned=" + ZonedDateTime.now(clock));
        System.out.println("utc=" + clock.withZone(ZoneOffset.UTC).instant());
    }
}
~~~

Chạy:

~~~text
javac --release 17 FixedClockDemo.java
java FixedClockDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
instant=2024-03-10T06:30:00Z
date=2024-03-10
time=01:30
zoned=2024-03-10T01:30-05:00[America/New_York]
utc=2024-03-10T06:30:00Z
~~~

**Giải thích:**

1. Instant.parse tạo một điểm thời gian xác định trên UTC timeline.
2. Clock.fixed ghim clock vào đúng instant đó và mang zone America/New_York.
3. Instant.now(clock) vẫn trả cùng instant; zone không làm thay đổi thời điểm tuyệt đối.
4. LocalDate.now(clock) và LocalTime.now(clock) chuyển instant sang ngày/giờ theo zone của clock.
5. clock.withZone(UTC) tạo clock khác zone nhưng giữ nguyên instant. Thay zone không cộng/trừ thời gian.
6. Chương trình không phụ thuộc thời gian thực, nên output ổn định khi chạy lại với cùng JDK/time-zone rules.

### Fixed clock hữu ích ở đâu?

- Kiểm tra hạn thanh toán đúng ngày hoặc ngay sau ngày hết hạn.
- Kiểm tra báo cáo cuối ngày, đầu tháng, ngày nhuận.
- Kiểm tra thời điểm gửi thông báo và thời gian retry.
- Kiểm tra logic khóa tài khoản hoặc phiên hết hạn.
- Kiểm tra sự kiện theo giờ địa phương của một chi nhánh.

### Đừng nhầm fixed clock với việc giả lập múi giờ

Clock.fixed cố định instant; zone được truyền vào chỉ quyết định cách chuyển instant sang giờ địa phương. Nếu test cần mô phỏng cùng thời điểm ở nhiều nơi, dùng cùng Instant và clock.withZone hoặc tạo hai fixed clocks cùng Instant nhưng khác ZoneId.

## 5. Truyền Clock vào logic nghiệp vụ

Một class cần biết ngày hiện tại không nên tự gọi LocalDate.now() ở sâu bên trong. Thay vào đó, nhận Clock từ bên ngoài:

~~~java
public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(LocalDate expiryDate) {
        LocalDate today = LocalDate.now(clock);
        return expiryDate.isBefore(today);
    }
}
~~~

Production tạo Clock.system(zone) theo zone nghiệp vụ. Test tạo Clock.fixed với instant cụ thể. Cùng một class, cùng logic, nhưng nguồn thời gian có thể thay đổi.

### Chọn zone ở đâu?

Nếu chính sách nghiệp vụ nói “ngày hết hạn theo giờ New York”, hãy tạo clock với ZoneId New York hoặc gọi clock.withZone(newYork) tại nơi cần. Nếu chính sách chỉ so sánh timestamp toàn cầu, hãy dùng Instant và UTC. Đừng để zone của máy chủ quyết định một ngày nghiệp vụ.

### Clock nên được chia sẻ hay tạo mỗi lần?

Clock chuẩn của Java là immutable và thread-safe; có thể truyền cùng một instance cho nhiều service. Tạo Clock.system(zone) một lần ở composition root/DI container giúp mọi thành phần nhận cùng policy. Không tạo Clock.fixed trong production để xử lý request thông thường.

### Test boundary cần xác định điều kiện nghiệp vụ

Trong ví dụ ExpiryPolicy, expiryDate.isBefore(today) có nghĩa ngày hết hạn vẫn còn hiệu lực trong chính ngày đó và chỉ hết hạn từ ngày hôm sau. Nếu quy tắc của sản phẩm là hết hạn ngay đầu ngày expiryDate, biểu thức phải khác. Clock chỉ làm thời điểm có thể kiểm soát; nó không tự quyết định inclusive/exclusive semantics của nghiệp vụ.

## 6. Ví dụ Java hoàn chỉnh 2 — kiểm thử logic hết hạn với Clock được inject

Tạo file **ClockInjectionDemo.java**:

~~~java
import java.time.*;

public class ClockInjectionDemo {
    static final class ExpiryPolicy {
        private final Clock clock;
        ExpiryPolicy(Clock clock) { this.clock = clock; }
        boolean isExpired(LocalDate expiryDate) {
            return expiryDate.isBefore(LocalDate.now(clock));
        }
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2025-01-31T23:30:00Z"), ZoneOffset.UTC);
        ExpiryPolicy policy = new ExpiryPolicy(clock);
        System.out.println("today=" + LocalDate.now(clock));
        System.out.println("yesterdayExpired="
                + policy.isExpired(LocalDate.of(2025, 1, 30)));
        System.out.println("todayExpired="
                + policy.isExpired(LocalDate.of(2025, 1, 31)));
        System.out.println("tomorrowExpired="
                + policy.isExpired(LocalDate.of(2025, 2, 1)));
    }
}
~~~

Chạy:

~~~text
javac --release 17 ClockInjectionDemo.java
java ClockInjectionDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
today=2025-01-31
yesterdayExpired=true
todayExpired=false
tomorrowExpired=false
~~~

**Giải thích:**

- Thời điểm test được ghim ở 23:30 UTC ngày 31/01/2025.
- Ngày 30/01 đứng trước today nên đã hết hạn.
- Ngày 31/01 bằng today nên theo policy ví dụ vẫn chưa hết hạn.
- Ngày 01/02 ở tương lai nên chưa hết hạn.
- Không cần sleep, thay đổi đồng hồ máy hoặc sửa ngày hệ thống để kiểm thử các nhánh.

Nếu policy cần chính xác tới giờ/phút/giây, hãy so sánh Instant thay vì LocalDate. Ví dụ một token hết hạn tại 10:00:00 UTC cần quy tắc rõ về thời điểm bằng đúng expiry instant có được chấp nhận hay không.

## 7. Clock.offset và Clock.tick cho test có kiểm soát

### Clock.offset

Clock.offset(clock, duration) tạo một clock hiển thị thời gian cộng thêm duration so với clock nền. Duration âm mô phỏng quá khứ, duration dương mô phỏng tương lai.

~~~java
Clock tomorrow = Clock.offset(baseClock, Duration.ofDays(1));
Clock yesterday = Clock.offset(baseClock, Duration.ofDays(-1));
~~~

Nó không làm thay đổi clock nền. Nếu base clock là fixed, offset clock cũng vẫn cố định. Nếu base clock là system clock, offset clock vẫn tiến theo thời gian thực nhưng lệch một duration.

### Clock.tick

Clock.tick(baseClock, duration) tạo clock trả thời điểm được truncate theo đơn vị tick. Ví dụ tick 30 giây sẽ loại bỏ phần nhỏ hơn mốc 30 giây gần nhất theo quy tắc của Clock. Dùng nó khi ứng dụng chủ ý chỉ quan sát độ phân giải thời gian thô hơn; không dùng để giả lập một scheduler hoặc một timer chính xác.

Duration truyền vào phải dương. Nếu duration có phần nhỏ hơn một millisecond, toàn bộ duration phải chia hết vào một giây; nếu không, factory ném IllegalArgumentException. Duration bằng 1 nanosecond không làm truncate. Implementation có thể dùng caching nên thời điểm bắt đầu tick quan sát được có thể trễ hơn clock nền. Vì vậy, Clock.tick không phải nguồn đo thời gian chính xác tuyệt đối hoặc scheduler; không dựa vào hiệu năng/caching của implementation như một contract nghiệp vụ.

### Clock.fixed, offset và tick khác nhau

| Factory | Hành vi | Công dụng |
|---|---|---|
| fixed | Luôn cùng một instant | Test một thời điểm cụ thể |
| offset | Cộng duration vào clock nền | Mô phỏng quá khứ/tương lai |
| tick | Truncate instant theo bước thời gian | Quan sát theo độ phân giải đã chọn |
| system/systemUTC | Theo đồng hồ hệ thống | Production time source |

## 8. Ví dụ Java hoàn chỉnh 3 — mô phỏng tương lai và tick 30 giây

Tạo file **ClockOffsetTickDemo.java**:

~~~java
import java.time.*;

public class ClockOffsetTickDemo {
    public static void main(String[] args) {
        Clock base = Clock.fixed(
                Instant.parse("2025-01-31T23:30:42Z"), ZoneOffset.UTC);
        Clock future = Clock.offset(base, Duration.ofMinutes(90));
        Clock ticked = Clock.tick(base, Duration.ofSeconds(30));
        System.out.println("base=" + base.instant());
        System.out.println("future=" + future.instant());
        System.out.println("tick30s=" + ticked.instant());
    }
}
~~~

Chạy:

~~~text
javac --release 17 ClockOffsetTickDemo.java
java ClockOffsetTickDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
base=2025-01-31T23:30:42Z
future=2025-02-01T01:00:42Z
tick30s=2025-01-31T23:30:30Z
~~~

**Giải thích:**

- Clock.offset cộng 90 phút nên vượt qua nửa đêm và sang ngày 01/02.
- Clock.tick với bước 30 giây truncate phần giây từ 42 xuống 30.
- base vẫn là 23:30:42; các clock dẫn xuất không sửa clock gốc.
- Ví dụ giúp test logic ngày mới hoặc dữ liệu chỉ lấy độ chính xác 30 giây mà không chờ đồng hồ thật.

## 9. Ranh giới ngày phải được tính theo ZoneId

Một ngày trên lịch địa phương không luôn tương ứng 24 giờ trên timeline. Khi vùng có thay đổi DST, ngày có thể ngắn hoặc dài hơn 24 giờ. Cách xác định ranh giới ngày an toàn là:

~~~java
LocalDate date = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");

Instant start = date.atStartOfDay(zone).toInstant();
Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
~~~

Đầu ngày được xác định bằng **atStartOfDay(zone)**. Đầu ngày kế tiếp được xác định bằng **date.plusDays(1).atStartOfDay(zone)**. Khoảng ngày đó được biểu diễn bằng hai Instant trên timeline.

### Vì sao không cộng 24 giờ vào start?

Nếu ngày có DST spring-forward, đồng hồ địa phương nhảy tới trước một giờ; ngày có thể chỉ có 23 giờ thực. Nếu ngày có fall-back, đồng hồ lùi lại một giờ; ngày có thể có 25 giờ thực.

Cộng Duration.ofHours(24) luôn cộng 24 giờ elapsed trên timeline. Nó không đồng nghĩa với “đầu ngày lịch kế tiếp ở cùng vùng”. Hãy tính ngày kế tiếp bằng LocalDate.plusDays(1), sau đó chuyển riêng ranh giới đó sang Instant.

### atStartOfDay không phải luôn tạo LocalTime 00:00

Theo quy tắc vùng, một số nơi có chuyển đổi offset ngay tại nửa đêm hoặc thậm chí bỏ qua một ngày lịch trong lịch sử. atStartOfDay(zone) trả về thời điểm hợp lệ sớm nhất của ngày theo quy tắc ZoneId; local time có thể được điều chỉnh nếu 00:00 không tồn tại.

Vì thế, nếu nghiệp vụ cần ranh giới ngày theo vùng, hãy dùng API này thay vì tự ghép LocalDate với LocalTime.MIDNIGHT rồi đoán offset.

## 10. Ví dụ Java hoàn chỉnh 4 — ngày DST có 23 giờ và 25 giờ

Tạo file **DailyBoundaryDemo.java**:

~~~java
import java.time.*;

public class DailyBoundaryDemo {
    private static void printDay(LocalDate date, ZoneId zone) {
        ZonedDateTime start = date.atStartOfDay(zone);
        ZonedDateTime end = date.plusDays(1).atStartOfDay(zone);
        long hours = Duration.between(start.toInstant(), end.toInstant())
                .toHours();
        System.out.println(date + " start=" + start);
        System.out.println(date + " end=" + end);
        System.out.println(date + " elapsedHours=" + hours);
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        printDay(LocalDate.of(2024, 3, 10), zone);
        printDay(LocalDate.of(2024, 11, 3), zone);
    }
}
~~~

Chạy:

~~~text
javac --release 17 DailyBoundaryDemo.java
java DailyBoundaryDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
2024-03-10 start=2024-03-10T00:00-05:00[America/New_York]
2024-03-10 end=2024-03-11T00:00-04:00[America/New_York]
2024-03-10 elapsedHours=23
2024-11-03 start=2024-11-03T00:00-04:00[America/New_York]
2024-11-03 end=2024-11-04T00:00-05:00[America/New_York]
2024-11-03 elapsedHours=25
~~~

**Phân tích:**

- Ngày 10/03/2024 ở New York chuyển đồng hồ từ -05:00 sang -04:00; khoảng giữa hai đầu ngày là 23 giờ.
- Ngày 03/11/2024 chuyển từ -04:00 sang -05:00; một giờ địa phương lặp lại nên ngày dài 25 giờ.
- Hai ngày đều bắt đầu ở 00:00 địa phương, nhưng offset đầu và cuối khác nhau.
- Số giờ được tính bằng Duration giữa hai Instant, không phải số ngày lịch nhân 24.
- Kết quả gắn với ZoneRules của America/New_York trong runtime kiểm thử; khi cập nhật tzdb, quy tắc vùng trong tương lai có thể thay đổi.

**Lưu ý:** Không phải mọi chuyển DST đều đúng một giờ hoặc mọi ngày chuyển đổi đều 23/25 giờ. Có nơi thay đổi 30 phút, thay đổi offset theo quyết định chính trị, hoặc lịch sử bỏ qua một ngày. Ví dụ này minh họa quy tắc phổ biến tại New York, không phải định luật cho mọi ZoneId.

## 11. Khoảng thời gian nửa mở [start, end)

Khi truy vấn dữ liệu theo ngày, nên dùng khoảng **bao gồm start, loại trừ end**:

~~~text
start <= timestamp < end
~~~

Trong Java:

~~~java
boolean contains =
        !instant.isBefore(start) && instant.isBefore(end);
~~~

Lợi ích:

- Hai ngày liên tiếp không bị trùng tại ranh giới.
- Không cần tự tạo thời điểm cuối ngày kiểu 23:59:59.999999999.
- Không phụ thuộc precision timestamp của database hoặc thiết bị.
- Dễ biểu diễn trong SQL: timestamp >= :start AND timestamp < :end.
- Có thể áp dụng nhất quán cho phút, giờ, ngày, tháng và kỳ báo cáo.

### Đừng dùng 23:59:59 làm cuối ngày

Timestamp có thể có precision milliseconds, microseconds hoặc nanoseconds. Một bản ghi lúc 23:59:59.500 có thể bị bỏ sót nếu end đặt sai precision. Cách [start,end) loại bỏ việc phải đoán giá trị cuối cùng của ngày.

### Dùng Instant cho ranh giới lưu trữ

Nếu dữ liệu trong database lưu timestamp UTC/Instant, hãy chuyển đầu ngày địa phương và đầu ngày kế tiếp thành Instant rồi truy vấn [start,end). Đừng so sánh timestamp UTC với LocalDateTime không có zone.

### Kiểm tra ranh giới chính xác

Một bộ test tối thiểu nên có:

- Instant bằng start: được bao gồm.
- Instant ngay trước end: được bao gồm.
- Instant bằng end: bị loại trừ.
- Instant trước start: bị loại trừ.
- Ngày chuyển DST: duration giữa start/end không mặc định 24 giờ.

## 12. Ví dụ Java hoàn chỉnh 5 — kiểm thử khoảng [start, end)

Tạo file **HalfOpenWindowDemo.java**:

~~~java
import java.time.*;

public class HalfOpenWindowDemo {
    static boolean contains(Instant now, Instant start, Instant end) {
        return !now.isBefore(start) && now.isBefore(end);
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDate day = LocalDate.of(2024, 3, 10);
        Instant start = day.atStartOfDay(zone).toInstant();
        Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();
        Instant justBeforeEnd = end.minusNanos(1);
        System.out.println("startIncluded=" + contains(start, start, end));
        System.out.println("lastInstantIncluded="
                + contains(justBeforeEnd, start, end));
        System.out.println("endExcluded=" + contains(end, start, end));
        System.out.println("durationHours="
                + Duration.between(start, end).toHours());
    }
}
~~~

Chạy:

~~~text
javac --release 17 HalfOpenWindowDemo.java
java HalfOpenWindowDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
startIncluded=true
lastInstantIncluded=true
endExcluded=false
durationHours=23
~~~

**Giải thích:**

- startIncluded=true chứng minh thời điểm đúng bằng đầu ngày thuộc khoảng.
- justBeforeEnd là một nanosecond trước end và vẫn nằm trong khoảng.
- endExcluded=false xác nhận ranh giới cuối không được bao gồm.
- Ngày New York 10/03/2024 chỉ có 23 giờ thực, nhưng logic [start,end) không cần sửa riêng cho DST.
- Trong database có precision thấp hơn nanosecond, không nên trừ một nanosecond để tạo end; hãy dùng end exclusive trực tiếp trong điều kiện truy vấn.

## 13. DST gap và overlap là gì?

Quy tắc vùng có thể khiến một LocalDateTime có **0, 1 hoặc 2 offset hợp lệ**:

1. **Normal:** một offset hợp lệ, là trường hợp thông thường.
2. **Gap:** không có offset hợp lệ. Đồng hồ nhảy về phía trước, nên một số giờ địa phương không tồn tại.
3. **Overlap:** có hai offset hợp lệ. Đồng hồ lùi về sau, nên một khoảng giờ địa phương xuất hiện hai lần.

~~~text
Spring forward (gap):
01:59:59 -05:00
       |
       +---- nhảy qua 02:00 đến 02:59
       |
03:00:00 -04:00

Fall back (overlap):
01:00 -04:00 ... 01:59 -04:00
       |
       +---- đồng hồ lùi lại
       |
01:00 -05:00 ... 01:59 -05:00
~~~

### Gap: giờ địa phương không tồn tại

Ví dụ ở New York ngày 10/03/2024, đồng hồ nhảy từ 01:59:59 lên 03:00. LocalDateTime 02:30 không có offset hợp lệ.

Khi gọi ZonedDateTime.of(localDateTime, zone), Java mặc định **đẩy giờ địa phương về phía trước theo độ dài gap**. Với gap một giờ, 02:30 trở thành 03:30.

Đây là policy mặc định của API, không nhất thiết là policy đúng cho mọi nghiệp vụ. Nếu người dùng đặt lịch lúc 02:30 vào ngày không tồn tại, sản phẩm có thể cần báo lỗi và yêu cầu chọn giờ khác thay vì tự động đẩy lịch.

### Overlap: giờ địa phương xuất hiện hai lần

Ngày 03/11/2024 tại New York, 01:30 xuất hiện hai lần:

- Lần đầu với offset -04:00.
- Lần thứ hai với offset -05:00.

Hai giá trị cùng hiển thị 01:30 nhưng là **hai Instant khác nhau**, cách nhau một giờ. ZonedDateTime.of mặc định chọn offset sớm hơn trong overlap; có thể dùng withLaterOffsetAtOverlap() để chọn lần sau hoặc withEarlierOffsetAtOverlap() để chọn lần trước.

Nếu nghiệp vụ liên quan lịch tàu, thanh toán, audit hoặc thời gian pháp lý, cần lưu lựa chọn offset/instant rõ ràng. Chỉ lưu LocalDateTime 01:30 sẽ làm mất thông tin phân biệt hai lần xảy ra.

## 14. ZoneRules giúp kiểm tra gap/overlap trước khi tạo ZonedDateTime

ZoneId cung cấp ZoneRules để kiểm tra offset hợp lệ:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();

List<ZoneOffset> offsets = rules.getValidOffsets(localDateTime);
ZoneOffsetTransition transition = rules.getTransition(localDateTime);
~~~

- Danh sách có 1 phần tử: thời điểm địa phương bình thường.
- Danh sách có 0 phần tử: gap; getTransition trả chuyển đổi liên quan.
- Danh sách có 2 phần tử: overlap; phần tử đầu là offset sớm hơn, phần tử sau là offset muộn hơn theo hợp đồng API.
- Không dựa vào rules.getOffset(localDateTime) một mình để validate local input: trong gap/overlap nó trả offset “best” theo rule, không nhất thiết là offset duy nhất hợp lệ.

Nếu muốn **reject** giờ không tồn tại hoặc yêu cầu người dùng chọn lần xảy ra trong overlap, kiểm tra getValidOffsets trước. Nếu cần strict construction với offset do người dùng cung cấp, ZonedDateTime.ofStrict kiểm tra local date-time/offset/zone có hợp lệ hay không và ném DateTimeException nếu không hợp lệ.

### Chính sách khi nhận lịch từ người dùng

- Gap: từ chối và yêu cầu chọn giờ hợp lệ; hoặc điều chỉnh về thời điểm đầu gap/giờ tương ứng theo policy đã công bố.
- Overlap: hỏi người dùng chọn lần đầu hay lần sau; hoặc dùng policy thống nhất được ghi rõ.
- Bình thường: chỉ có một offset, tạo ZonedDateTime từ offset đó.
- Khi lưu: giữ Instant để xác định thời điểm đã chọn; giữ ZoneId nếu cần tái dựng lịch dân sự hoặc hiển thị theo vùng.

Không âm thầm thay đổi giờ người dùng nhập mà không thông báo, đặc biệt với lịch họp, đặt phòng hoặc giao dịch có thời hạn.

## 15. Ví dụ Java hoàn chỉnh 6 — phát hiện gap và overlap

Tạo file **DstGapOverlapDemo.java**:

~~~java
import java.time.*;
import java.time.zone.*;
import java.util.List;

public class DstGapOverlapDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        List<ZoneOffset> gapOffsets = rules.getValidOffsets(gap);
        ZoneOffsetTransition gapTransition = rules.getTransition(gap);
        System.out.println("gapValidOffsets=" + gapOffsets.size());
        System.out.println("gapDuration=" + gapTransition.getDuration());
        System.out.println("gapResolved=" + ZonedDateTime.of(gap, zone));

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> overlapOffsets = rules.getValidOffsets(overlap);
        ZonedDateTime earlier = ZonedDateTime.of(overlap, zone);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
        System.out.println("overlapOffsets=" + overlapOffsets);
        System.out.println("overlapEarlier=" + earlier);
        System.out.println("overlapLater=" + later);
    }
}
~~~

Chạy:

~~~text
javac --release 17 DstGapOverlapDemo.java
java DstGapOverlapDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
gapValidOffsets=0
gapDuration=PT1H
gapResolved=2024-03-10T03:30-04:00[America/New_York]
overlapOffsets=[-04:00, -05:00]
overlapEarlier=2024-11-03T01:30-04:00[America/New_York]
overlapLater=2024-11-03T01:30-05:00[America/New_York]
~~~

**Đọc kết quả:**

- Gap có 0 offset hợp lệ và transition dài một giờ.
- ZonedDateTime.of tự điều chỉnh 02:30 thành 03:30 theo policy mặc định.
- Overlap có hai offset -04:00 và -05:00.
- earlier và later cùng ngày giờ địa phương nhưng đại diện hai thời điểm khác nhau.
- Ví dụ dựa trên quy tắc America/New_York năm 2024 trong runtime đã kiểm thử; không hardcode giả định mọi vùng đều chuyển một giờ.
## 16. Period và Duration: ngày lịch không phải 24 giờ

Hai kiểu này biểu diễn hai loại lượng thời gian khác nhau:

- **Period** là khoảng thời gian theo lịch: năm, tháng, ngày. Ví dụ Period.ofDays(1) nghĩa là ngày kế tiếp trên lịch.
- **Duration** là khoảng thời gian trên timeline: giây và nanosecond. Duration.ofHours(24) là đúng 86.400 giây.

Khi thao tác trên ZonedDateTime:

- plusDays(1) làm việc trên **local time-line**, giữ giờ địa phương tương ứng của ngày kế tiếp nếu quy tắc vùng cho phép.
- plus(Duration.ofHours(24)) cộng đúng 24 giờ elapsed trên **instant time-line**; sau DST, giờ địa phương có thể lệch một giờ.

~~~java
ZonedDateTime nextCalendarDay = start.plusDays(1);
ZonedDateTime after24Hours = start.plus(Duration.ofHours(24));
~~~

Không chọn API theo tên gọi nghe có vẻ gần nhau; hãy hỏi nghiệp vụ cần “cùng giờ ngày mai” hay “đúng 24 giờ sau”.

### Ví dụ thường gặp

- Hẹn nhắc lại lúc 09:00 ngày kế tiếp theo giờ địa phương: dùng LocalDate/LocalTime/ZoneId hoặc ZonedDateTime.plusDays(1).
- Token hết hạn sau 24 giờ kể từ lúc phát hành: lưu Instant phát hành và cộng Duration.ofHours(24).
- Lương tháng, hạn cuối tháng: dùng YearMonth/LocalDate và quy tắc lịch.
- Timeout HTTP 30 giây: dùng thời lượng elapsed/đồng hồ đơn điệu, không cộng ngày lịch.

## 17. Ví dụ Java hoàn chỉnh 7 — plusDays và cộng 24 giờ khác nhau

Tạo file **CalendarVsElapsedDemo.java**:

~~~java
import java.time.*;

public class CalendarVsElapsedDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime noon = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, zone);
        ZonedDateTime nextCalendarDay = noon.plusDays(1);
        ZonedDateTime after24Hours = noon.plus(Duration.ofHours(24));
        System.out.println("start=" + noon);
        System.out.println("plusOneDay=" + nextCalendarDay);
        System.out.println("plus24Hours=" + after24Hours);
        System.out.println("dayElapsedHours="
                + Duration.between(noon.toInstant(),
                                   nextCalendarDay.toInstant()).toHours());
    }
}
~~~

Chạy:

~~~text
javac --release 17 CalendarVsElapsedDemo.java
java CalendarVsElapsedDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
start=2024-03-09T12:00-05:00[America/New_York]
plusOneDay=2024-03-10T12:00-04:00[America/New_York]
plus24Hours=2024-03-10T13:00-04:00[America/New_York]
dayElapsedHours=23
~~~

**Giải thích:**

- plusDays(1) giữ giờ dân sự 12:00 ở ngày kế tiếp; offset đã đổi từ -05:00 sang -04:00.
- Khoảng cách thực giữa hai instant là 23 giờ.
- Duration.ofHours(24) luôn cộng 24 giờ elapsed, nên kết quả hiển thị thành 13:00 ngày hôm sau.
- Với lịch họp, nhắc việc theo giờ địa phương, plusDays có thể đúng hơn; với thời hạn chính xác sau 24 giờ, Duration phù hợp hơn.

## 18. Ranh giới tháng, năm và ngày nhuận

Tương tự ngày, ranh giới tháng nên tính bằng **YearMonth** hoặc LocalDate, không bằng cách cộng số giờ cố định:

~~~java
YearMonth month = YearMonth.of(2024, 2);
LocalDate start = month.atDay(1);
LocalDate end = month.plusMonths(1).atDay(1);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant startInstant = start.atStartOfDay(zone).toInstant();
Instant endInstant = end.atStartOfDay(zone).toInstant();
~~~

Khoảng báo cáo tháng là [startInstant, endInstant). Không cần biết tháng có 28, 29, 30 hay 31 ngày để viết logic truy vấn.

### Ngày nhuận và cuối tháng

- LocalDate.of(2024, 2, 29) là ngày hợp lệ trong năm nhuận.
- LocalDate.of(2025, 2, 29) không hợp lệ và ném DateTimeException.
- LocalDate.plusYears(1) trên 29/02/2024 sẽ điều chỉnh về ngày hợp lệ cuối tháng 02/2025.
- Cộng một tháng vào ngày 31 cần hiểu policy điều chỉnh cuối tháng; nếu nghiệp vụ cần “ngày cuối tháng”, dùng YearMonth.atEndOfMonth() thay vì tự cộng 30 ngày.
- Khi cần kỳ tháng, lưu YearMonth hoặc ngày đầu kỳ, đừng suy ra từ Duration.ofDays(30).

### Mẫu ranh giới tháng

~~~java
YearMonth current = YearMonth.from(LocalDate.now(clock));
Instant from = current.atDay(1).atStartOfDay(zone).toInstant();
Instant until = current.plusMonths(1)
        .atDay(1).atStartOfDay(zone).toInstant();
~~~

Với clock được inject và zone nghiệp vụ rõ, test có thể ghim ngày 31/01 hoặc 29/02 để xác minh chuyển tháng/năm mà không chờ ngày thật.

## 19. Kiểm thử ngày giờ quanh nửa đêm

Ranh giới nửa đêm dễ tạo lỗi lệch ngày nếu clock và zone không thống nhất. Ví dụ cùng một Instant có thể là ngày 31/01 ở một vùng nhưng ngày 01/02 ở vùng khác.

Một test tốt nên kiểm tra:

1. Instant ngay trước nửa đêm địa phương.
2. Instant đúng thời điểm bắt đầu ngày mới.
3. Instant ngay sau ranh giới.
4. Ngày tính bằng ZoneId nghiệp vụ, không phải zone máy test.
5. Quy tắc inclusive/exclusive của ngày hết hạn.
6. Chuyển tháng/năm nếu ranh giới rơi vào cuối tháng hoặc ngày nhuận.

Ví dụ tạo Clock.fixed với Instant ngay trước nửa đêm ở vùng cụ thể; sau đó kiểm tra LocalDate.now(clock) ở hai phía. Không dùng sleep để chờ đồng hồ thật đi qua nửa đêm.

### Đừng lấy giờ mặc định của máy làm zone nghiệp vụ

Clock.systemDefaultZone() và ZoneId.systemDefault() phụ thuộc cấu hình JVM/OS. Nếu dịch vụ chạy trong container UTC nhưng người dùng thuộc Asia/Ho_Chi_Minh, việc dùng default zone có thể làm lệch ngày báo cáo hoặc ngày hết hạn. Đưa zone từ cấu hình/tenant/business rule vào một cách tường minh.

## 20. Clock và System.nanoTime: thời điểm tường và thời gian đo elapsed

Clock trả thời điểm trên timeline dân sự. Đồng hồ hệ thống có thể được điều chỉnh bởi NTP, quản trị viên hoặc hệ điều hành; nó không phải đồng hồ đơn điệu được bảo đảm cho đo khoảng thời gian.

Nếu cần đo elapsed time, timeout hoặc benchmark, dùng **System.nanoTime()**:

~~~java
long start = System.nanoTime();
performOperation();
long elapsedNanos = System.nanoTime() - start;
~~~

- nanoTime không đại diện ngày giờ lịch; giá trị origin là tùy ý và chỉ có ý nghĩa khi lấy hiệu giữa hai lần đọc trong cùng JVM.
- Không lưu nanoTime làm timestamp nghiệp vụ hoặc gửi sang máy khác.
- Dùng Clock/Instant để ghi nhận thời điểm sự kiện, lưu trữ hoặc hiển thị.
- Dùng nanoTime để đo thời lượng, timeout, latency trong một tiến trình.

**Không dùng Instant.now().plusSeconds(30) làm timer chính xác cho timeout** nếu mục tiêu là đo elapsed duration trong môi trường có thể chỉnh đồng hồ. Dùng API timeout chuyên dụng hoặc deadline dựa trên nanoTime.

## 21. Dữ liệu time-zone có thể thay đổi

ZoneId vùng như America/New_York không phải một offset cố định. Nó tra cứu quy tắc từ time-zone database (tzdb) đi cùng runtime. Quy tắc tương lai có thể thay đổi theo quyết định pháp lý của từng quốc gia; JDK cập nhật tzdb qua các bản phát hành.

Hệ quả:

- Cùng ZoneId và ngày tương lai có thể cho offset khác sau khi nâng JDK/tzdb.
- Test lịch sử có thể ổn định hơn test dự báo nhiều năm tới, nhưng vẫn nên pin runtime nếu assert output snapshot chính xác.
- Với lịch định kỳ dân sự, thường lưu LocalDate/LocalTime/ZoneId để áp dụng quy tắc vùng mới khi đến ngày chạy.
- Với sự kiện đã xảy ra, lưu Instant là nguồn xác định thời điểm.
- Nếu nghiệp vụ cần lưu lại quyết định offset đã được chấp nhận tại thời điểm tạo lịch, có thể lưu thêm ZoneOffset hoặc ZonedDateTime/Instant cùng dữ liệu audit.

### Region ID và fixed offset

Nếu nghiệp vụ yêu cầu luôn theo giờ UTC+07:00 cố định, ZoneOffset.ofHours(7) có thể đúng. Nếu nghiệp vụ yêu cầu giờ dân sự tại một địa điểm và có thể đổi quy tắc theo luật, dùng ZoneId vùng. Không đổi region ID thành fixed offset chỉ để làm test dễ hơn nếu điều đó thay đổi ý nghĩa nghiệp vụ.

## 22. Định dạng và parse thời gian trong test

DateTimeFormatter có thể được cấu hình rõ để output xác định:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ISO_ZONED_DATE_TIME;
String text = zonedDateTime.format(formatter);
ZonedDateTime parsed = ZonedDateTime.parse(text, formatter);
~~~

Các formatter ISO chuẩn thường phù hợp cho dữ liệu máy và kiểm thử. Nếu dùng mẫu custom, chọn pattern rõ ràng và locale khi có tên tháng/ngày bản địa hóa.

- Dùng ISO_INSTANT cho Instant.
- Dùng ISO_LOCAL_DATE cho LocalDate.
- Dùng ISO_OFFSET_DATE_TIME hoặc ISO_ZONED_DATE_TIME khi cần offset/zone.
- Không parse một chuỗi ngày giờ địa phương rồi đoán múi giờ từ máy chạy.
- Nếu chuỗi input không có offset/zone, hợp đồng phải xác định zone nghiệp vụ trước khi biến thành Instant.
- Khi cần hiển thị cho người dùng, truyền Locale và ZoneId tường minh.

Một chuỗi như 2025-01-31T09:00 không mang thông tin múi giờ; không được coi nó tương đương 2025-01-31T09:00Z.

## 23. Các lỗi thường gặp khi kiểm thử ngày giờ

### 23.1. Gọi LocalDate.now() hoặc Instant.now() sâu trong service

Test không điều khiển được thời điểm. Truyền Clock vào service và dùng now(clock) để cố định thời gian.

### 23.2. Chỉ fixed clock nhưng quên zone

Cùng Instant có thể thuộc ngày khác nhau ở các vùng khác nhau. Test phải chọn ZoneId nghiệp vụ; không dùng zone mặc định của máy một cách vô tình.

### 23.3. Cộng 24 giờ để lấy đầu ngày kế tiếp

Ngày địa phương có thể dài 23 hoặc 25 giờ. Dùng date.plusDays(1).atStartOfDay(zone) rồi chuyển sang Instant.

### 23.4. Dùng LocalDateTime như một timestamp tuyệt đối

LocalDateTime không có offset/zone nên không xác định một Instant duy nhất. Phải bổ sung ZoneId và xử lý gap/overlap.

### 23.5. Coi mọi ngày đều có đúng 24 giờ

DST và thay đổi quy tắc vùng có thể làm ngày ngắn/dài hơn; một số chuyển đổi còn không tròn một giờ. Đo Duration giữa hai Instant nếu cần elapsed time.

### 23.6. Dùng ZoneOffset khi cần quy tắc vùng

Offset cố định không thay đổi theo DST. Dùng ZoneId vùng khi cần giờ dân sự.

### 23.7. Dùng giờ viết tắt như EST/CST

Tên viết tắt mơ hồ giữa các vùng. Dùng ID rõ như America/New_York hoặc Asia/Ho_Chi_Minh.

### 23.8. Bỏ qua gap khi đặt lịch

Một LocalDateTime trong gap không có offset hợp lệ. ZonedDateTime.of tự điều chỉnh về sau theo độ dài gap; nghiệp vụ có thể cần từ chối và hỏi người dùng.

### 23.9. Bỏ qua overlap

Một giờ địa phương có thể xảy ra hai lần. Chỉ lưu LocalDateTime làm mất khả năng phân biệt; cần chọn offset hoặc lưu Instant.

### 23.10. Lấy rules.getOffset(localDateTime) để validate

Trong gap/overlap, phương thức trả offset phù hợp nhất theo quy tắc chứ không phải danh sách offset hợp lệ. Dùng getValidOffsets và getTransition để phân loại.

### 23.11. Dùng Duration khi nghiệp vụ cần ngày lịch

Duration.ofDays(1) là 24 giờ; Period.ofDays(1) hoặc plusDays(1) biểu diễn một ngày lịch. Chọn theo ý nghĩa nghiệp vụ.

### 23.12. Dùng Period khi cần timeout

Period là đơn vị lịch. Timeout/elapsed nên dùng Duration hoặc System.nanoTime.

### 23.13. Tạo cuối ngày bằng 23:59:59.999

Precision của database/runtime có thể khác. Dùng [start,end) với đầu ngày kế tiếp làm end exclusive.

### 23.14. Dùng Clock.tick để làm scheduler

Clock.tick chỉ giới hạn độ phân giải thời gian quan sát; nó không lập lịch, không bảo đảm callback chạy đúng lúc và có thể dùng caching.

### 23.15. Coi Clock.fixed sẽ tự tiến sau khi chờ

Fixed clock luôn trả cùng một instant. Dùng offset clock hoặc clock test có thể điều khiển nếu cần mô phỏng bước tiến.

### 23.16. Đổi Clock system bằng cách sửa đồng hồ máy trong test

Thao tác này ảnh hưởng môi trường và có thể làm hỏng test khác. Dùng Clock.fixed/offset thay vì sửa system time.

### 23.17. Dùng Instant.now() để đo thời lượng chính xác

Wall clock có thể được điều chỉnh. Dùng System.nanoTime() cho elapsed duration/timeout trong cùng JVM.

### 23.18. Assert thời gian hiện tại chính xác tới nanosecond

Đồng hồ hệ thống có precision/accuracy phụ thuộc nền tảng. Không assert một instant hardcoded khi dùng Clock.system; inject fixed clock để test xác định.

### 23.19. Quên khôi phục default zone/clock state

Không đổi default timezone toàn JVM theo từng test hoặc request. Truyền ZoneId tường minh; nếu test buộc phải thay global setting, lưu và khôi phục trong finally và không chạy song song.

### 23.20. Cho rằng tzdb không thay đổi

Luật địa phương có thể thay đổi và JDK cập nhật dữ liệu vùng. Pin JDK cho snapshot test; review thay đổi khi nâng runtime.

### 23.21. Lưu giờ địa phương mà không lưu zone

Lịch lặp lại 09:00 mỗi thứ Hai cần LocalTime + ZoneId + quy tắc lặp; một Instant duy nhất không mô tả lịch tương lai. Ngược lại, một giao dịch đã xảy ra cần Instant làm thời điểm chính xác.

### 23.22. Dùng clock zone không thống nhất trong cùng một policy

Nếu LocalDate.now(clock) lấy ngày theo UTC nhưng ranh giới báo cáo lại theo New York, kết quả có thể lệch ngày. Mỗi policy phải định nghĩa rõ zone và dùng nhất quán.

## 24. Checklist thiết kế và kiểm thử

- Logic nghiệp vụ có nhận Clock qua constructor hoặc method không?
- Test có dùng Clock.fixed với instant cụ thể không?
- ZoneId nghiệp vụ có được truyền tường minh không?
- Có phân biệt Instant, LocalDateTime và ZonedDateTime không?
- Có dùng atStartOfDay(zone) cho ranh giới ngày địa phương không?
- End của truy vấn có exclusive không?
- Có test chính xác start, end-minus-unit và end không?
- Có test ngày chuyển DST spring-forward và fall-back không?
- Nếu nhận giờ người dùng, có policy gap/overlap rõ ràng không?
- Có dùng getValidOffsets/getTransition khi cần validate local time không?
- Có phân biệt plusDays với Duration.ofHours(24) không?
- Có test cuối tháng, năm nhuận và ngày kế tiếp không?
- Có tránh default timezone của host trong logic nghiệp vụ không?
- Có dùng System.nanoTime cho elapsed time/timeout thay vì Clock không?
- Có tránh Thread.sleep để chờ tới một ranh giới thời gian không?
- Có hiểu tzdb có thể thay đổi theo JDK không?
- Có lưu Instant cho sự kiện đã xảy ra và ZoneId cho lịch dân sự khi phù hợp không?
- Nếu dữ liệu database có precision thấp hơn nanosecond, có truy vấn theo end exclusive thay vì trừ một nano không?

## 25. Bài tập tự kiểm tra

**Câu 1.** Clock.fixed(instant, zone) có làm thời gian tăng khi test chạy lâu hơn không?

*Đáp án:* Không. Nó luôn trả cùng Instant; zone chỉ quyết định cách chuyển instant sang ngày giờ địa phương.

**Câu 2.** Cùng một Instant nhưng hai Clock.withZone khác nhau có cho Instant khác nhau không?

*Đáp án:* Không. Chúng giữ nguyên thời điểm, chỉ khác zone hiển thị.

**Câu 3.** Vì sao LocalDate.now(clock) tốt hơn LocalDate.now() trong logic cần kiểm thử?

*Đáp án:* Caller có thể inject clock cố định và zone xác định, không phụ thuộc thời gian thực hoặc default zone.

**Câu 4.** Ngày New York 10/03/2024 dài bao nhiêu giờ thực?

*Đáp án:* 23 giờ vì đồng hồ nhảy từ -05:00 sang -04:00.

**Câu 5.** Ngày New York 03/11/2024 dài bao nhiêu giờ thực?

*Đáp án:* 25 giờ vì đồng hồ lùi từ -04:00 về -05:00.

**Câu 6.** Cách lấy end của một ngày theo vùng an toàn là gì?

*Đáp án:* date.plusDays(1).atStartOfDay(zone).toInstant(), dùng làm end exclusive.

**Câu 7.** Vì sao dùng [start,end) thay cho end 23:59:59.999?

*Đáp án:* Không phụ thuộc precision của timestamp và không chồng lấn hai ngày liền kề.

**Câu 8.** DST gap có bao nhiêu offset hợp lệ?

*Đáp án:* Không có offset hợp lệ; local time không tồn tại.

**Câu 9.** DST overlap có bao nhiêu offset hợp lệ trong trường hợp thông thường?

*Đáp án:* Hai offset; cùng một local time ánh xạ tới hai Instant.

**Câu 10.** ZonedDateTime.of xử lý gap thế nào theo mặc định?

*Đáp án:* Dịch local date-time về phía trước theo độ dài gap.

**Câu 11.** ZonedDateTime.of xử lý overlap thế nào theo mặc định?

*Đáp án:* Chọn offset sớm hơn nếu không có preferred offset; có thể chọn lần sau bằng withLaterOffsetAtOverlap().

**Câu 12.** Duration.ofDays(1) và Period.ofDays(1) có giống nhau không?

*Đáp án:* Không. Duration là đúng 24 giờ; Period là một ngày lịch.

**Câu 13.** Khi nào dùng System.nanoTime()?

*Đáp án:* Đo elapsed time, timeout và latency trong cùng JVM; không dùng làm timestamp lịch.

**Câu 14.** Clock.tick có phải scheduler không?

*Đáp án:* Không. Nó truncate thời điểm theo tick duration, không lập lịch tác vụ.

**Câu 15.** Vì sao phải dùng ZoneId vùng thay vì offset cố định cho lịch địa phương?

*Đáp án:* ZoneId chứa quy tắc vùng thay đổi theo thời gian; ZoneOffset chỉ là độ lệch cố định.

**Câu 16.** Khi nào nên lưu Instant và khi nào cần lưu ZoneId?

*Đáp án:* Instant xác định thời điểm sự kiện đã xảy ra; ZoneId giữ quy tắc vùng cho lịch dân sự hoặc hiển thị theo địa phương.

**Câu 17.** Tại sao test DST snapshot có thể đổi sau khi nâng JDK?

*Đáp án:* Runtime cập nhật time-zone database theo quy định vùng mới; offset và kết quả chuyển đổi tương lai có thể thay đổi.

## 26. Tài liệu chính thức còn được duy trì

- Oracle Java SE 25 — **Clock**: fixed, offset, tick, system clock và dependency injection: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html
- Oracle Java SE 25 — **Instant**: điểm thời gian trên timeline: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html
- Oracle Java SE 25 — **LocalDate**: ngày lịch và atStartOfDay(ZoneId): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- Oracle Java SE 25 — **ZonedDateTime**: quy tắc gap/overlap, cộng ngày và offset: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html
- Oracle Java SE 25 — **ZoneRules**: getValidOffsets, transition và kiểm tra offset: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html
- Oracle Java SE 25 — **ZoneId**: region IDs và quy tắc time-zone: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html
- Oracle Java SE 25 — **Duration**: thời lượng trên timeline: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html
- Oracle Java SE 25 — **Period**: khoảng thời gian theo lịch: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Period.html
- Oracle Java SE 25 — **DateTimeFormatter**: định dạng và parse ngày giờ: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Oracle Java SE 25 — **Time Zone Database**: dữ liệu múi giờ trong JDK: https://www.oracle.com/latam/java/technologies/tzdata-versions.html

**Kết luận:** Đưa Clock vào logic nghiệp vụ để kiểm thử được thời điểm; dùng Clock.fixed cho test xác định, Clock.offset để mô phỏng thời gian và Clock.tick khi cần độ phân giải thô. Tính ranh giới ngày theo LocalDate + ZoneId + atStartOfDay, dùng khoảng [start,end) trên Instant. Ngày dân sự có thể không dài 24 giờ; gap/overlap cần policy rõ ràng. Phân biệt Period với Duration và dùng System.nanoTime cho elapsed time. Đây là nền tảng để kiểm thử lịch, thời hạn và báo cáo ổn định qua nhiều môi trường.