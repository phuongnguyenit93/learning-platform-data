# Cộng trừ giờ với LocalTime và hiện tượng quay vòng qua nửa đêm

**LocalTime** trong gói **java.time** biểu diễn **giờ trong một ngày**, từ **00:00:00.000000000** đến **23:59:59.999999999**. Khi cộng hoặc trừ thời gian khiến đồng hồ đi qua nửa đêm, kết quả **quay vòng trong phạm vi 24 giờ**. Đây là đặc điểm cốt lõi của LocalTime: nó chỉ giữ vị trí kim đồng hồ trong một ngày, không mang ngày tháng, múi giờ hay số ngày đã đi qua.

Ví dụ, cộng 90 phút vào **23:40** cho **01:10**. Phép toán này đúng đối với **giờ trên đồng hồ**, nhưng kết quả LocalTime **không thể cho biết 01:10 thuộc ngày hôm sau**. Nếu cần ngày thực tế, tính hạn hoàn thành hoặc thời gian đã trôi qua, phải bổ sung thông tin phù hợp.

Bài học dùng Java 17+ và tập trung vào **plusHours**, **plusMinutes**, **plusSeconds**, **plusNanos**, các phương thức **minus…**, phép quay vòng, cách so sánh khoảng giờ băng qua nửa đêm và cách tránh mất thông tin ngày.

## 1. LocalTime đại diện cho điều gì?

Các giá trị sau đều là **LocalTime** hợp lệ:

- **00:00**: đầu ngày theo đồng hồ, có hằng **LocalTime.MIDNIGHT** hoặc **LocalTime.MIN**.
- **12:00**: giữa trưa, có hằng **LocalTime.NOON**.
- **23:59:59.999999999**: giờ lớn nhất trong một ngày, có hằng **LocalTime.MAX**.
- **09:30**: giờ mở cửa, thời điểm bắt đầu học, giờ báo thức lặp lại hằng ngày.

LocalTime **không chứa** ngày, ngày trong tuần, múi giờ, UTC offset hoặc quy tắc đổi giờ mùa hè (DST). Hai giá trị **LocalTime.of(9, 0)** là bằng nhau dù một người ở Hà Nội và một người ở New York: chúng cùng diễn tả **09:00 trên đồng hồ**, chưa xác định cùng một thời điểm thực tế.

Một số tình huống thích hợp với LocalTime:

| Yêu cầu | LocalTime có phù hợp? | Vì sao |
|---|---|---|
| Giờ mở cửa chi nhánh 08:30 mỗi ngày | Có | Chỉ cần giờ trong ngày |
| Chọn giờ nhắc việc 23:00 hằng tối | Có, kèm quy tắc lịch lặp nếu cần | Mốc đồng hồ, không phải thời điểm tuyệt đối |
| Cộng thêm 45 phút vào giờ bắt đầu trên đồng hồ | Có | Kết quả là một giờ khác trong ngày |
| Ghi đơn hàng xảy ra lúc nào | Không đủ | Cần **Instant** hoặc dữ liệu thời gian đầy đủ |
| Tính ca làm bắt đầu hôm nay và kết thúc ngày mai | Không đủ khi đứng một mình | Cần **LocalDateTime** hoặc ngày bắt đầu/kết thúc |
| Tính 8 giờ đã trôi qua qua một lần chuyển DST | Không đủ | Cần thời điểm có múi giờ/ngữ cảnh phù hợp |

**Nguyên tắc:** chỉ chọn LocalTime nếu nghiệp vụ thật sự quan tâm đến **giờ trên mặt đồng hồ**. Khi bài toán hỏi “ngày nào”, “sau bao nhiêu giờ thực tế”, “thời điểm này là lúc nào trên UTC”, LocalTime cần thêm thông tin.

## 2. Các phương thức cộng và trừ

Các phương thức quen thuộc của LocalTime:

| Cộng thời gian | Trừ thời gian | Tham số |
|---|---|---|
| **plusHours(long)** | **minusHours(long)** | Số giờ |
| **plusMinutes(long)** | **minusMinutes(long)** | Số phút |
| **plusSeconds(long)** | **minusSeconds(long)** | Số giây |
| **plusNanos(long)** | **minusNanos(long)** | Số nano giây |
| **plus(TemporalAmount)** | **minus(TemporalAmount)** | Lượng thời gian phù hợp, ví dụ **Duration** |
| **plus(long, TemporalUnit)** | **minus(long, TemporalUnit)** | Đơn vị được hỗ trợ, ví dụ **ChronoUnit.MINUTES** |

Ví dụ đơn giản:

~~~java
LocalTime start = LocalTime.of(9, 15);

LocalTime afterOneHour = start.plusHours(1);      // 10:15
LocalTime after45Minutes = start.plusMinutes(45); // 10:00
LocalTime before20Minutes = start.minusMinutes(20); // 08:55
~~~

Đoạn này là **minh họa** đặt trong ngữ cảnh đã import **java.time.LocalTime**; chương trình độc lập được cung cấp ở phần 6.

**LocalTime là immutable (bất biến)**. Mỗi phương thức trả về một giá trị LocalTime mới hoặc giá trị tương đương; nó **không sửa đối tượng ban đầu**. Phải dùng kết quả trả về:

~~~java
LocalTime alarm = LocalTime.of(7, 0);
alarm.plusMinutes(30);             // Không thay đổi biến alarm
alarm = alarm.plusMinutes(30);     // alarm bây giờ là 07:30
~~~

Không cần so sánh tham chiếu bằng **==** để suy luận hành vi; dùng **equals()**, **isBefore()**, **isAfter()** hoặc **compareTo()** khi so sánh giá trị.

### Số âm trong phép cộng/trừ

Đối với lượng thời gian nhỏ thông thường:

- **plusMinutes(-15)** tương ứng lùi 15 phút.
- **minusMinutes(-15)** tương ứng tiến 15 phút.
- **plusHours(24)** hoặc **minusHours(24)** trả về cùng giờ đồng hồ.
- Cộng hoặc trừ nhiều giờ hơn một ngày vẫn chỉ trả về giờ trong ngày.

Các hàm sử dụng **long**, nhưng kết quả LocalTime luôn nằm trong **một chu kỳ 24 giờ**. Nếu số giờ/ngày đã đi qua là kết quả nghiệp vụ cần giữ, không nên dùng riêng LocalTime.

## 3. Vì sao đồng hồ quay vòng qua nửa đêm?

Một ngày đồng hồ trong mô hình LocalTime có:

- **24 giờ**;
- **1.440 phút**;
- **86.400 giây**;
- **86.400.000.000.000 nano giây**.

Khi cộng/trừ, LocalTime lấy kết quả trong **chu kỳ một ngày**. Có thể hình dung:

~~~text
23:00 ── +1 giờ ──> 00:00
23:40 ── +90 phút ──> 01:10
00:15 ── -45 phút ──> 23:30
09:00 ── +25 giờ ──> 10:00
09:00 ── +24 giờ ──> 09:00
~~~

Từ **23:40** cộng **90 phút**:

1. Còn **20 phút** để tới **00:00**.
2. Còn **70 phút** sau thời điểm đồng hồ chuyển sang ngày mới.
3. **70 phút = 1 giờ 10 phút**, vậy giá trị LocalTime trả về **01:10**.

Từ **00:15** trừ **45 phút** thì quay về **23:30** trên đồng hồ.

**Quan trọng:** kết quả **01:10** tự thân không chứng minh đã đi sang ngày kế tiếp. Nếu cộng **48 giờ**, kết quả LocalTime vẫn bằng thời gian bắt đầu mặc dù về mặt tiến trình có thể đã đi qua hai ngày. LocalTime không cung cấp biến **dayCarry**, không trả số ngày vượt qua và không bổ sung LocalDate ngầm.

### Công thức trực quan của phép quay vòng

Nếu quy mọi thời điểm về số phút từ nửa đêm (**0 đến 1.439**), thì:

~~~text
phút_mới = floorMod(phút_cũ + phút_thay_đổi, 1440)
~~~

Ví dụ:

~~~text
23:40 = 23 × 60 + 40 = 1420 phút
1420 + 90 = 1510
1510 mod 1440 = 70
70 phút từ 00:00 = 01:10
~~~

Với lượng trừ lớn hơn số phút ban đầu, phải dùng **phép modulo không âm** khi tự tính: trong Java, toán tử **%** giữ dấu của toán hạng trái, nên biểu thức **(-30) % 1440** cho **-30**, không phải phút hợp lệ trong ngày. **Math.floorMod(-30, 1440)** cho **1410**, tương ứng **23:30**. Trong code nghiệp vụ Java thông thường, ưu tiên **LocalTime.plusMinutes(...)** hoặc **minusMinutes(...)** thay vì tự xử lý modulo.

Công thức trên mô tả độ chính xác tới **phút**. LocalTime hỗ trợ chính xác tới **nano giây**, nên các phép cộng giây hoặc nano không bị giới hạn bởi số nguyên phút.

## 4. Qua nửa đêm ở từng mức độ chính xác

### 4.1. Giờ và phút

~~~java
LocalTime.of(23, 0).plusHours(2);      // 01:00
LocalTime.of(23, 59).plusMinutes(2);  // 00:01
LocalTime.of(0, 10).minusMinutes(20); // 23:50
~~~

Các chú thích thể hiện **giờ đồng hồ sau phép tính**. Nếu hệ thống cần “01:00 ngày mai”, phải tự giữ **ngày bắt đầu**.

### 4.2. Giây

~~~java
LocalTime.of(23, 59, 59).plusSeconds(1); // 00:00
LocalTime.of(0, 0, 0).minusSeconds(1);   // 23:59:59
~~~

LocalTime hoạt động theo ngày gồm **86.400 giây đồng hồ**, không biểu diễn **23:59:60** như một giây nhuận. Không dùng riêng LocalTime để xây dựng phép đo thời gian thiên văn hoặc tính thời gian hệ thống thực tế có những yêu cầu đặc biệt về đồng hồ.

### 4.3. Nano giây

~~~java
LocalTime.MIDNIGHT.minusNanos(1); // 23:59:59.999999999
LocalTime.MAX.plusNanos(1);       // 00:00
~~~

**LocalTime.MAX** nằm ngay trước nửa đêm trong mô hình chính xác tới nano giây. Đừng xem **23:59:59.999999999** là cách biểu diễn “kết thúc ngày” dùng chung cho tất cả cơ sở dữ liệu: nhiều hệ thống lưu độ chính xác thấp hơn. Nếu cần khoảng thời gian trong một ngày, thường dùng giới hạn **đầu bao gồm, cuối không bao gồm** với ngày/thời điểm thích hợp.

### 4.4. Khi cộng hơn một ngày

~~~java
LocalTime.of(9, 0).plusHours(25);     // 10:00
LocalTime.of(9, 0).plusHours(48);     // 09:00
LocalTime.of(9, 0).minusHours(49);    // 08:00
~~~

Các kết quả chỉ trả lại **vị trí trên đồng hồ**. Vì vậy không thể nhìn kết quả **09:00** để biết đã cộng **0**, **24**, **48** hay **72** giờ. Nếu “đã trôi qua bao lâu?” là câu hỏi nghiệp vụ, giữ độ dài bằng **Duration** và mốc có ngày hoặc Instant.

## 5. Cộng Duration và giới hạn đơn vị hỗ trợ

**Duration** biểu diễn lượng thời gian dưới dạng giây và nano giây; nó phù hợp để mô tả việc cộng 75 phút hoặc trừ 2 giờ trên mặt đồng hồ.

~~~java
import java.time.Duration;
import java.time.LocalTime;

LocalTime time = LocalTime.of(23, 30);
LocalTime later = time.plus(Duration.ofMinutes(75)); // 00:45
~~~

**Duration.ofHours(26)** có thể cộng vào LocalTime và kết quả vẫn là giờ quay vòng. Nhưng LocalTime không ghi lại “một ngày cộng hai giờ”.

Không phải mọi **TemporalUnit** hay **TemporalAmount** đều được LocalTime hỗ trợ. Nó xử lý những đơn vị thời gian thích hợp từ nano giây đến nửa ngày theo hợp đồng **Temporal**, trong khi đơn vị ngày/tháng/năm thuộc về lịch:

~~~java
LocalTime.NOON.plus(1, ChronoUnit.DAYS);
~~~

Lệnh cuối ném **UnsupportedTemporalTypeException** vì LocalTime không có thông tin ngày. **Period.ofDays(1)** cũng không phải cách cộng ngày vào LocalTime. Nếu cần “ngày mai lúc 12:00”, dùng **LocalDate.plusDays(1)** kết hợp LocalTime, hoặc **LocalDateTime.plusDays(1)**.

## 6. Chương trình Java 17+ chạy được: phép cộng/trừ quay vòng

Tạo tệp **LocalTimeWrapDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class LocalTimeWrapDemo {
    public static void main(String[] args) {
        LocalTime start = LocalTime.of(23, 40);

        System.out.println("start=" + start);
        System.out.println("plus90m=" + start.plusMinutes(90));
        System.out.println("minus45m=" +
                LocalTime.of(0, 15).minusMinutes(45));
        System.out.println("plus25h=" +
                LocalTime.of(9, 0).plusHours(25));
        System.out.println("plus24h=" +
                LocalTime.of(9, 0).plusHours(24));
        System.out.println("minusNano=" +
                LocalTime.MIDNIGHT.minusNanos(1));

        System.out.println("addDuration=" +
                start.plus(Duration.ofMinutes(90)));
        System.out.println("rawBetween=" +
                Duration.between(start, start.plusMinutes(90))
                        .toMinutes());

        LocalDateTime first =
                LocalDate.of(2026, 10, 24).atTime(start);
        LocalDateTime next = first.plusMinutes(90);

        System.out.println("dateTime=" + next);
        System.out.println("elapsed=" +
                Duration.between(first, next).toMinutes());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LocalTimeWrapDemo.java
java LocalTimeWrapDemo
~~~

Đầu ra:

~~~text
start=23:40
plus90m=01:10
minus45m=23:30
plus25h=10:00
plus24h=09:00
minusNano=23:59:59.999999999
addDuration=01:10
rawBetween=-1350
dateTime=2026-10-25T01:10
elapsed=90
~~~

**Giải thích các kết quả quan trọng:**

- **plus90m=01:10** chứng minh LocalTime quay vòng qua nửa đêm.
- **plus24h=09:00** cho thấy một vòng 24 giờ không làm đổi giá trị giờ trên đồng hồ.
- **minusNano** cho thấy LocalTime hỗ trợ ranh giới ở mức nano giây.
- **rawBetween=-1350** là kết quả thường gây nhầm: **Duration.between(23:40, 01:10)** khi cả hai đều chỉ là LocalTime tính khoảng lệch giữa hai giá trị trên **cùng một ngày giả định**, nên **01:10 đứng trước 23:40** tới 1.350 phút. API không tự đoán rằng giờ kết thúc thuộc ngày mai.
- **dateTime=2026-10-25T01:10** giữ được sự thật rằng đã qua ngày hôm sau.
- **elapsed=90** là độ dài thực tế của phép cộng 90 phút trên LocalDateTime trong mô hình lịch không gắn múi giờ. Nếu đã gắn vùng có DST, cần mô hình thời điểm thực tế riêng như mục 9.

## 7. So sánh giờ và tính khoảng cách khi băng qua nửa đêm

**isBefore**, **isAfter**, **compareTo** của LocalTime so sánh **giờ trong ngày**, không suy luận thứ tự sự kiện thực tế.

~~~java
LocalTime begin = LocalTime.of(23, 30);
LocalTime end = LocalTime.of(1, 0);

System.out.println(end.isBefore(begin)); // true
~~~

Kết quả **true** đúng về giá trị mặt đồng hồ: **01:00** nhỏ hơn **23:30**. Nhưng nếu ca làm bắt đầu **23:30 hôm nay** và kết thúc **01:00 ngày mai**, sự kiện kết thúc thực tế diễn ra **sau** sự kiện bắt đầu.

Tương tự:

~~~java
Duration.between(LocalTime.of(23, 30),
                 LocalTime.of(1, 0)).toMinutes(); // -1350
~~~

**Duration.between** không tự suy ra “90 phút”. Muốn tính đúng phải xác định **ngày kết thúc** hoặc có quy tắc nghiệp vụ rõ ràng về băng qua nửa đêm.

### Quy tắc dành cho ca trong vòng dưới 24 giờ

Nếu hợp đồng quy định:

1. Ca bắt đầu vào ngày được chỉ định;
2. Ca **không dài quá 24 giờ**;
3. Nếu giờ kết thúc nhỏ hơn giờ bắt đầu, đó là **ngày kế tiếp**;
4. Nếu giờ kết thúc bằng giờ bắt đầu, phải nói rõ **0 giờ hay tròn 24 giờ**;

thì có thể dùng **LocalDateTime** để giữ ngày kết thúc. Đối với ca dài hơn 24 giờ hoặc ca bắt đầu/kết thúc có ngày cụ thể từ người dùng, phải lưu **ngày kết thúc tường minh** thay vì suy đoán.

## 8. Ví dụ thực tế: ca làm việc từ 22:30 đến 01:15 hôm sau

Tạo tệp **OvernightShiftDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class OvernightShiftDemo {
    public static void main(String[] args) {
        LocalDate businessDay = LocalDate.of(2026, 10, 24);
        LocalTime opens = LocalTime.of(22, 30);
        LocalTime closes = LocalTime.of(1, 15);

        LocalDateTime openedAt = businessDay.atTime(opens);

        // Chỉ đúng với ca có độ dài dưới 24 giờ theo hợp đồng.
        LocalDate closeDay = closes.isBefore(opens)
                ? businessDay.plusDays(1)
                : businessDay;

        LocalDateTime closedAt = closeDay.atTime(closes);

        System.out.println("opened=" + openedAt);
        System.out.println("closed=" + closedAt);
        System.out.println("minutes=" +
                Duration.between(openedAt, closedAt).toMinutes());
    }
}
~~~

Chạy:

~~~bash
javac OvernightShiftDemo.java
java OvernightShiftDemo
~~~

Kết quả:

~~~text
opened=2026-10-24T22:30
closed=2026-10-25T01:15
minutes=165
~~~

**Vì sao cần LocalDateTime?** Đối với giờ đồng hồ, **01:15** “nhỏ hơn” **22:30**; đối với ca được gắn **ngày**, **01:15 ngày 25/10** xảy ra sau **22:30 ngày 24/10**. Phép **Duration.between** trên hai LocalDateTime trả về **165 phút**, tương ứng 2 giờ 45 phút trong mô hình thời gian địa phương liên tục.

Nếu ca có thể kéo dài **24 giờ**, **36 giờ** hoặc qua nhiều ngày, so sánh hai LocalTime **không cho biết** số ngày đã trôi qua. Khi đó cần dữ liệu **startDateTime** và **endDateTime** rõ ràng hoặc một **Duration** do nghiệp vụ cung cấp.

**Ngoại lệ quan trọng:** LocalDateTime cũng không tự biểu diễn sự thay đổi offset do DST. Để tính thời gian làm việc đã trôi qua ở một vùng có đổi giờ mùa hè, cần giải quyết thời điểm bắt đầu/kết thúc trong ZoneId rồi tính theo **Instant** hoặc ZonedDateTime thích hợp; xem mục 9.

## 9. Nửa đêm, ngày lịch và DST là ba vấn đề khác nhau

Hiện tượng quay vòng của **LocalTime** là **quy tắc toán học 24 giờ**. Nó **không liên quan trực tiếp** đến việc múi giờ thực tế có ngày dài 23, 24 hay 25 giờ.

Ví dụ:

- **LocalTime.of(23, 30).plusHours(2)** cho **01:30**, bất kể địa điểm hay ngày nào. Không có múi giờ nên không thể biết quá trình đó đi qua thay đổi DST hay không.
- **LocalDateTime.of(2026, 10, 24, 23, 30).plusHours(2)** cho **2026-10-25T01:30**, giữ ngày theo lịch địa phương nhưng vẫn chưa xác định offset UTC.
- Khi một sự kiện có **ZoneId**, thời điểm theo đồng hồ địa phương có thể không tồn tại hoặc trùng lặp tại ngày đổi DST. Muốn đo **2 giờ thực sự đã trôi qua**, thông thường lấy **Instant bắt đầu + Duration.ofHours(2)** và hiển thị lại ở vùng cần thiết.
- Nếu nghiệp vụ yêu cầu **giữ giờ đồng hồ**, ví dụ “09:00 mỗi ngày tại New York”, phải dùng quy tắc lịch địa phương + ZoneId; không cộng cố định 24 giờ vào Instant trước đó.

**Đừng đánh đồng:**

| Câu hỏi | Dữ liệu/cách tính phù hợp |
|---|---|
| “Sau 120 phút, đồng hồ hiển thị mấy giờ?” | **LocalTime.plusMinutes(120)** |
| “120 phút sau là ngày nào, giờ nào?” | **LocalDateTime.plusMinutes(120)** nếu muốn cộng trên lịch địa phương |
| “Chính xác 120 phút thực tế sau là thời điểm nào?” | **Instant.plus(Duration.ofMinutes(120))** |
| “Ngày mai cửa hàng mở 09:00 theo giờ địa phương?” | **LocalDate + LocalTime + ZoneId** |
| “Ca làm kéo dài bao nhiêu giờ thực tế trong ngày đổi DST?” | Hai mốc đã xác định ZoneId/offset → **Instant** → **Duration.between** |

Các quy tắc DST thuộc **ZonedDateTime**, **ZoneRules** và mô hình lịch đầy đủ. **LocalTime không tự động cộng/trừ theo múi giờ và không ném ngoại lệ DST chỉ vì nó quay qua 00:00**.

## 10. Xử lý nửa đêm trong mô hình dữ liệu và API

### 10.1. Cách biểu diễn lịch lặp mỗi ngày

Giờ báo thức **06:30** hoặc giờ đóng cửa định kỳ **01:00** phù hợp với **LocalTime**. Nhưng nếu giờ đóng cửa **01:00 thuộc sáng hôm sau** so với giờ mở **22:00**, nên biểu diễn rõ quy tắc này trong nghiệp vụ, ví dụ:

~~~json
{
  "openingTime": "22:00",
  "closingTime": "01:00",
  "closingDayOffset": 1,
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

Đây là **ví dụ hợp đồng API**, không phải cấu trúc mặc định Java. **closingDayOffset=1** lưu ý định “ngày kế tiếp”; **zoneId** xác định vùng nếu ứng dụng cần tạo các lần chạy thực tế. Dữ liệu này không tự bao quát ngày nghỉ, ngày ngoại lệ hay DST; các yếu tố đó phải được mô hình hóa thêm nếu nghiệp vụ cần.

### 10.2. Khoảng thời gian băng qua 00:00

Một khoảng thời gian thực tế nên có **mốc bắt đầu/kết thúc** đủ ngữ cảnh:

~~~json
{
  "startLocal": "2026-10-24T22:30:00",
  "endLocal": "2026-10-25T01:15:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

Khi cần lưu **mốc tuyệt đối**, sau khi xử lý zone và tính hợp lệ của giờ địa phương, có thể lưu thêm Instant; nếu cần giữ ý định lịch hẹn, bảo toàn **local time + zone**.

### 10.3. Giới hạn cuối ngày

Không có **LocalTime.of(24, 0)** trong giá trị LocalTime chuẩn. **24:00** thường là cách diễn đạt “00:00 ngày kế tiếp” trong một số quy ước hiển thị, còn LocalTime biểu diễn nửa đêm bằng **00:00**.

Để xác định khoảng “[hôm nay, ngày mai)”, dùng **LocalDate.atStartOfDay(zone)** cho đầu ngày và đầu ngày tiếp theo làm **endExclusive**; đừng cố tạo **24:00** hoặc gắn “23:59:59.999999999” làm giới hạn cuối cho mọi cơ sở dữ liệu.

## 11. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Cho rằng **23:40.plusMinutes(90)** có ngày hôm sau | LocalTime chỉ trả **01:10**; mất thông tin ngày | Dùng LocalDateTime nếu cần ngày |
| Nghĩ **plusHours(24)** báo ngày đã tăng | Kết quả cùng giờ cũ | Giữ ngày hoặc duration riêng |
| Dùng **isBefore()** để kết luận ca qua đêm kết thúc trước khi bắt đầu | So sánh mặt đồng hồ khác thứ tự sự kiện | So sánh mốc có ngày |
| Dùng **Duration.between(23:40, 01:10)** và mong 90 phút | Trả **-1350 phút** | Xác định ngày kết thúc hoặc dùng hợp đồng ca <24 giờ |
| Thấy giờ kết thúc bằng giờ bắt đầu và luôn lấy 24 giờ | Có thể chỉ 0 giờ; cũng có thể nhiều ngày | Quy định rõ ngày/độ dài |
| Cộng **ChronoUnit.DAYS** trực tiếp vào LocalTime | Đơn vị không hỗ trợ | Dùng LocalDate/LocalDateTime |
| Cộng giờ mà không gán giá trị trả về | LocalTime bất biến | **time = time.plusHours(...)** |
| Tính giờ thực tế qua DST bằng LocalTime hoặc LocalDateTime đơn thuần | Có thể lệch số giờ thực tế | Giải quyết vùng và tính bằng Instant |
| Lưu giờ đóng cửa **01:00** mà không giữ quy tắc “ngày mai” | Không biết ca có qua nửa đêm | Lưu day offset/ngày kết thúc rõ ràng |
| Chấp nhận **24:00** như một LocalTime thông thường | Dữ liệu không hợp lệ với mô hình | Diễn giải thành **00:00 ngày kế tiếp** nếu hợp đồng yêu cầu |

## 12. Checklist trước khi dùng LocalTime để cộng trừ

1. Bài toán chỉ cần **giờ đồng hồ**, hay cần cả **ngày**?
2. Phép toán có thể vượt **00:00** hoặc hơn **24 giờ** không?
3. Kết quả có cần **số ngày đã đi qua** không? Nếu có, không dùng LocalTime đơn độc.
4. Đang tính **giờ hiển thị** hay **khoảng thời gian thực sự đã trôi qua**?
5. Nếu tính ca qua đêm, **ngày kết thúc** được nhập trực tiếp hay suy ra từ quy tắc có giới hạn?
6. Trường hợp **start == end** nghĩa là ca 0 giờ, 24 giờ hay yêu cầu dữ liệu bổ sung?
7. Có **ZoneId** và DST trong nghiệp vụ không?
8. Đã kiểm thử đúng các ranh giới **23:59:59**, **00:00**, âm số phút, lớn hơn 24 giờ và nano giây chưa?

### Câu hỏi tự kiểm tra

**1.** **23:50.plusMinutes(20)** bằng bao nhiêu?  
**Đáp án:** **00:10**, nhưng chưa có thông tin ngày.

**2.** **00:10.minusMinutes(20)** bằng bao nhiêu?  
**Đáp án:** **23:50**, không tự chỉ ra ngày hôm trước.

**3.** **09:00.plusHours(49)** bằng bao nhiêu?  
**Đáp án:** **10:00**, vì 49 giờ = hai vòng 24 giờ và 1 giờ.

**4.** **LocalTime.of(22, 0).until(LocalTime.of(1, 0), ChronoUnit.HOURS)** cho giá trị nào?  
**Đáp án:** **-21**, do tính theo hai giá trị giờ trong cùng ngày giả định, không tự hiểu ca qua nửa đêm.

**5.** Muốn biết “ca bắt đầu 22:00 ngày 24/10 và kết thúc 01:00 ngày 25/10” dài bao lâu thì dùng gì?  
**Đáp án:** Hai **LocalDateTime** rồi **Duration.between** cho 3 giờ theo lịch địa phương; nếu muốn số giờ thực tế tại vùng có DST, cần xử lý vùng/offset và tính trên Instant.

**6.** Có thể cộng 90 phút vào một LocalTime mà không biết múi giờ không?  
**Đáp án:** Có, nếu chỉ cần giờ trên mặt đồng hồ. Không thể xác định thời điểm UTC hoặc quy tắc DST từ kết quả đó.

**Ghi nhớ:** **LocalTime.plus… / minus… quay vòng trong 24 giờ** và không lưu ngày đã đi qua. Hãy dùng LocalTime cho thao tác với **giờ đồng hồ**, LocalDateTime cho **ngày + giờ địa phương**, và Instant/ZonedDateTime khi cần **thời điểm thực tế cùng ngữ cảnh múi giờ**. Sai lệch thường không nằm ở phép cộng, mà ở việc mô hình dữ liệu đã bỏ mất ngày hoặc quy tắc vùng mà nghiệp vụ cần.
