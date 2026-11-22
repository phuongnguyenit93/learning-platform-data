# Chọn kiểu dữ liệu ngày giờ theo ý nghĩa nghiệp vụ trong Java

Trong Java, chọn kiểu ngày giờ là quyết định về **ý nghĩa của dữ liệu**, không đơn thuần là quyết định định dạng hiển thị. Cùng một chuỗi “2026-03-02 09:00” có thể là giờ mở cửa lặp lại mỗi ngày, lịch họp tại Hà Nội, hoặc dấu thời gian ghi nhận một sự kiện. Ba ý nghĩa đó đòi hỏi cách lưu trữ khác nhau.

Bài này tập trung vào cách đặt câu hỏi nghiệp vụ và lựa chọn kiểu trong **java.time** (Java 8+, ví dụ chạy trên Java 17+). Mục tiêu là tránh nhầm “ngày trên lịch”, “giờ trên đồng hồ” và “thời điểm tuyệt đối”.

## 1. Ba câu hỏi phải trả lời trước khi chọn kiểu

1. **Dữ liệu có chỉ ra một thời điểm duy nhất trên trục thời gian toàn cầu không?** Ví dụ đơn hàng được tạo lúc nào, token hết hạn vào lúc nào. Nếu có, cân nhắc **Instant**.
2. **Dữ liệu là giá trị lịch/đồng hồ theo cách con người hiểu, nhưng chưa gắn với một thời điểm tuyệt đối?** Ví dụ ngày sinh, tháng tính phí, 09:00 hằng ngày. Nếu có, chọn **LocalDate**, **YearMonth**, **LocalTime** hoặc **LocalDateTime** tùy phần thông tin thực sự có.
3. **Nghiệp vụ gắn với địa điểm hoặc quy tắc múi giờ cụ thể?** Ví dụ lớp học lúc 09:00 tại New York, nơi có thể đổi giờ mùa hè. Khi đó phải giữ **ZoneId** (như America/New_York), có thể cùng **ZonedDateTime** hoặc cặp ngày giờ địa phương + ZoneId. Chỉ lưu độ lệch UTC như -05:00 là chưa đủ cho lịch tương lai.

Đừng bắt đầu bằng câu hỏi “nên dùng Date hay String?”. Hãy bắt đầu bằng câu hỏi “dữ liệu này đại diện cho cái gì, và hành vi nào phải giữ đúng khi người dùng đổi múi giờ hoặc khi đồng hồ mùa hè thay đổi?”.

## 2. Bảng chọn kiểu nhanh

| Ý nghĩa nghiệp vụ | Kiểu Java phù hợp | Ví dụ / lý do |
|---|---|---|
| Sự kiện đã xảy ra, thời điểm tạo/cập nhật, hạn token | **Instant** | Một điểm duy nhất trên trục thời gian; dễ so sánh và tính thời hạn |
| Ngày sinh, ngày nghỉ, ngày giao hàng được chỉ định theo lịch | **LocalDate** | Chỉ có năm–tháng–ngày, không có giờ/múi giờ |
| Giờ mở/đóng cửa mỗi ngày | **LocalTime** | Chỉ có giờ–phút–giây, không xác định ngày hay thời điểm UTC |
| Ngày và giờ do người dùng nhập nhưng chưa xác định vùng | **LocalDateTime** | Có thông tin lịch và đồng hồ, chưa đủ để suy ra Instant |
| Cuộc hẹn diễn ra trong một vùng có quy tắc múi giờ | **ZonedDateTime** hoặc **LocalDateTime + ZoneId** | Giữ tên vùng, áp dụng đúng quy tắc DST khi quy đổi |
| Thời điểm có độ lệch UTC được cung cấp trong thông điệp | **OffsetDateTime** | Gồm ngày giờ và +07:00, -04:00…; offset không chứa quy tắc tương lai |
| Mốc giờ và độ lệch UTC, không có ngày | **OffsetTime** | Chỉ phù hợp khi offset cố định thực sự là một phần hợp đồng dữ liệu |
| Tháng lập hóa đơn, kỳ báo cáo theo tháng | **YearMonth** | Tránh tự chế ngày 01 của tháng khi nghiệp vụ chỉ có tháng |
| Năm ngân sách | **Year** | Không thêm tháng/ngày không tồn tại trong nghiệp vụ |
| Sinh nhật lặp hằng năm, ngày kỷ niệm | **MonthDay** | Chỉ có tháng/ngày; phải quy định cách xử lý 29/02 |
| 15 phút timeout, độ trễ, thời gian đã trôi qua | **Duration** | Lượng thời gian đo bằng giây/nano trên trục thời gian |
| 1 tháng gia hạn, 2 năm tuổi, 7 ngày trên lịch | **Period** | Lượng thời gian theo năm–tháng–ngày trên lịch |
| Vùng có quy tắc lịch sử và tương lai | **ZoneId** | Asia/Ho_Chi_Minh, Europe/Paris, America/New_York |
| Độ lệch UTC cố định | **ZoneOffset** | +07:00 là một offset, không đồng nghĩa tên vùng địa lý |
| Nguồn “thời điểm hiện tại” có thể thay thế khi kiểm thử | **Clock** | Tiêm Clock thay vì phụ thuộc trực tiếp đồng hồ hệ thống |

**Lưu ý:** Không có kiểu nào “tốt nhất cho mọi ngày giờ”. Cố ép mọi trường vào **Instant**, hoặc mọi trường vào **LocalDateTime**, đều làm mất ý nghĩa ở một số bài toán.

## 3. Phân biệt thời điểm tuyệt đối với giờ địa phương

### 3.1. Instant: một sự kiện đã có thời điểm xảy ra

**Instant** biểu diễn một điểm trên trục thời gian theo UTC (độ chính xác tới nano giây trong mô hình Java), không mang tên múi giờ hoặc cách trình bày theo địa phương.

Ví dụ: thanh toán được xác nhận, yêu cầu API tới hệ thống, phiên đăng nhập hết hạn. Nếu hai máy chủ ghi các **Instant** bằng đồng hồ đã đồng bộ, ta có thể so sánh thứ tự sự kiện mà không cần biết vị trí người xem.

Một **Instant** có thể được hiển thị ở nhiều múi giờ mà vẫn là cùng một sự kiện: 02:00 UTC = 09:00 ở Asia/Ho_Chi_Minh khi offset là +07:00. Đổi vùng hiển thị không được làm thay đổi **Instant** đã ghi.

### 3.2. LocalDate: ngày trên lịch, không phải nửa đêm UTC

Ngày sinh 2000-02-29 là một **LocalDate**. Nó không tự biến thành 2000-02-28 hoặc 2000-03-01 khi người dùng đi du lịch. Không ép LocalDate thành Instant bằng “00:00 UTC” chỉ để lưu trữ: như vậy bạn đã tự thêm giờ và vùng không thuộc dữ liệu gốc.

Tương tự, **ngày giao hàng** có thể là LocalDate trong múi giờ của cửa hàng. Nếu cần tính “hết ngày giao hàng” thành hạn tuyệt đối, phải lấy **LocalDate + ZoneId + quy tắc hạn cụ thể** rồi mới đổi ra Instant.

### 3.3. LocalTime: lịch đồng hồ, chưa phải độ dài

“Cửa hàng mở lúc 09:00” là **LocalTime**; “mở trong 8 giờ” là **Duration**. Hai khái niệm khác nhau. **LocalTime** không biết múi giờ, ngày hoặc DST, vì vậy không thể trực tiếp so sánh 09:00 ở Hà Nội với 09:00 ở New York theo trục thời gian.

Với lịch mở cửa lặp lại, thường cần thêm ngày trong tuần, lịch ngoại lệ, ngày nghỉ và **ZoneId** của chi nhánh. Một mình LocalTime không giải quyết tất cả quy tắc đó.

### 3.4. LocalDateTime: chưa đủ thông tin để xác định thời điểm

**LocalDateTime** gồm ngày và giờ nhưng không chứa offset hoặc ZoneId. Giá trị 2026-03-02T09:00 có thể xảy ra ở nhiều Instant khác nhau. Nó hợp lý làm **giờ người dùng yêu cầu** trước khi áp dụng múi giờ, hoặc làm giờ tường trong một kế hoạch lịch.

Sai lầm phổ biến là coi **LocalDateTime.now()** như timestamp toàn cầu: giá trị trên hai máy ở hai múi giờ khác nhau không trực tiếp so sánh được. Để ghi nhật ký sự kiện, ưu tiên **Instant.now(clock)**.

### 3.5. ZonedDateTime và OffsetDateTime khác nhau ở đâu?

- **ZonedDateTime** giữ ngày giờ, offset hiện có và **ZoneId** như Europe/Paris. ZoneId cho phép tra quy tắc múi giờ/DST. Rất hữu ích khi phải diễn giải lịch theo nơi diễn ra.
- **OffsetDateTime** giữ ngày giờ và offset như +07:00. Nó xác định được Instant, nhưng không cho biết đây là Hà Nội, Bangkok hay một vùng có cùng offset; từ offset không suy ra được thay đổi DST sau này.
- **ZoneOffset** (+07:00) là một độ lệch. **ZoneId** (Asia/Ho_Chi_Minh) là danh tính vùng kèm quy tắc. Khi đặt lịch tương lai theo địa phương, ưu tiên lưu ZoneId.

**ZonedDateTime** biểu diễn một cuộc hẹn cụ thể đã được giải quyết sang offset theo dữ liệu vùng hiện có. Với lịch lặp “09:00 thứ Hai hàng tuần tại Paris”, phải giữ quy tắc **LocalTime + ngày trong tuần + ZoneId** và tạo lần diễn ra theo từng ngày; không lấy một Instant rồi cộng cố định 7 × 24 giờ.

## 4. Duration khác Period: “24 giờ” khác “một ngày lịch”

**Duration** đo thời gian đã trôi qua, chủ yếu theo giây/nano giây. Dùng cho timeout, hạn xử lý sau 15 phút, đo độ trễ, thời gian chạy tác vụ. Ví dụ: một hạn ở **Instant** cộng **Duration.ofMinutes(15)**.

**Period** đo phần chênh lệch theo năm, tháng, ngày trong lịch ISO. Dùng cho “gia hạn 1 tháng”, “sau 2 năm”, “cộng 7 ngày lịch” khi quy tắc nghiệp vụ là theo lịch. Một tháng không có số giây cố định và các tháng có độ dài khác nhau.

Ví dụ ngày 31/01/2026 cộng một tháng theo **LocalDate.plusMonths(1)** ra 28/02/2026, không phải 30 hoặc 31 ngày sau. Khi cộng **Period** vào LocalDate phải chấp nhận và kiểm thử quy tắc điều chỉnh ngày cuối tháng; khi cộng **Duration** vào Instant, số giây là chính xác.

**Đặc biệt về DST:** ở nơi đổi giờ mùa hè, từ 12:00 hôm trước đến 12:00 hôm sau có thể chỉ 23 hoặc tới 25 giờ. Trên ZonedDateTime, **plusDays(1)** đi tới cùng giờ đồng hồ của ngày kế tiếp theo lịch; **plusHours(24)** cộng đúng 24 giờ trên trục thời gian. Chúng không luôn cho cùng kết quả.

## 5. Quy trình ra quyết định theo nghiệp vụ

1. **Liệt kê thuộc tính thực sự được nhập:** chỉ ngày, chỉ giờ, cả ngày giờ, offset, ZoneId, hay chỉ độ dài? Đừng tự điền ngày 01 hoặc 00:00 chỉ vì lớp dữ liệu đòi hỏi.
2. **Xác định điều bất biến:** “ngày sinh không đổi theo vùng”, “cuộc họp luôn là 09:00 tại văn phòng Paris”, hoặc “token hết hạn sau đúng 15 phút”. Điều bất biến quyết định kiểu.
3. **Xác định thời điểm cần đổi về Instant:** một lịch dự kiến có thể giữ LocalDateTime + ZoneId; khi tạo nhắc lịch hoặc thực thi sự kiện mới chuyển thành Instant sau khi xử lý DST.
4. **Xác định chính sách vùng và lịch:** vùng của người dùng, cửa hàng hay nơi diễn ra? Chính sách cho giờ không tồn tại/trùng lặp là gì? Nếu nghiệp vụ chưa quyết định, không tự mặc định âm thầm.
5. **Xác định ranh giới hệ thống:** JSON/API, database, timezone mặc định máy chủ và người dùng. Cần giữ những thành phần nào để round-trip không mất nghĩa?
6. **Viết phép thử đối chứng:** thay đổi vùng hiển thị, qua DST, cuối tháng, ngày nhuận và sự kiện ở cùng thời điểm. Nếu mô hình còn đúng, lựa chọn mới đáng tin.

### Cây quyết định ngắn

~~~text
Có phải một sự kiện/hạn xảy ra tại một thời điểm xác định?
  Có -> Instant
  Cần giữ offset ban đầu từ giao thức? -> OffsetDateTime (+ chính sách lưu offset)
  Cần giữ vùng diễn ra? -> lưu thêm ZoneId / dữ liệu lịch gốc

Không:
  Chỉ năm?                -> Year
  Chỉ tháng và năm?       -> YearMonth
  Chỉ ngày và tháng?      -> MonthDay
  Chỉ ngày lịch?          -> LocalDate
  Chỉ giờ đồng hồ?        -> LocalTime
  Ngày + giờ chưa có vùng?-> LocalDateTime
  Ngày + giờ tại một vùng?-> LocalDateTime + ZoneId, rồi giải quyết thành
                             ZonedDateTime/Instant khi nghiệp vụ cần
  Độ dài thực tế?         -> Duration
  Khoảng theo lịch?       -> Period
~~~

Đây là cách xác định ý nghĩa, không phải quy tắc ép mọi trường có cùng cấu trúc dữ liệu.

## 6. Ví dụ Java 17+: chọn đúng kiểu cho nhiều quy tắc cùng tồn tại

Giả sử một ứng dụng có các yêu cầu:

- Ghi thời điểm tạo giao dịch và thời điểm giao dịch hết hạn sau đúng 15 phút.
- Lưu ngày sinh không thay đổi theo múi giờ người dùng.
- Lưu kỳ hóa đơn tháng 02/2026.
- Lưu giờ mở cửa hằng ngày tại một chi nhánh.
- Tổ chức cuộc hẹn lúc 09:00 ngày 02/03/2026 tại Thành phố Hồ Chí Minh.

Tạo tệp **DomainDateTimeDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class DomainDateTimeDemo {
    public static void main(String[] args) {
        ZoneId branchZone = ZoneId.of("Asia/Ho_Chi_Minh");

        // Clock cố định: ví dụ có đầu ra lặp lại được.
        Clock clock = Clock.fixed(
                Instant.parse("2026-03-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        Instant createdAt = Instant.now(clock);
        Instant expiresAt = createdAt.plus(Duration.ofMinutes(15));

        LocalDate birthday = LocalDate.of(2000, 2, 29);
        YearMonth invoiceMonth = YearMonth.of(2026, 2);
        LocalTime dailyOpening = LocalTime.of(9, 0);

        LocalDateTime meetingWallTime =
                LocalDateTime.of(2026, 3, 2, 9, 0);
        ZonedDateTime meetingAtBranch =
                meetingWallTime.atZone(branchZone);
        Instant meetingInstant = meetingAtBranch.toInstant();

        System.out.println("createdAt=" + createdAt);
        System.out.println("expiresAt=" + expiresAt);
        System.out.println("birthday=" + birthday);
        System.out.println("invoiceMonth=" + invoiceMonth);
        System.out.println("dailyOpening=" + dailyOpening);
        System.out.println("meetingLocal=" +
                meetingAtBranch.toLocalDateTime());
        System.out.println("meetingZone=" + meetingAtBranch.getZone());
        System.out.println("meetingInstant=" + meetingInstant);
        System.out.println("elapsedMinutes=" +
                Duration.between(createdAt, expiresAt).toMinutes());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DomainDateTimeDemo.java
java DomainDateTimeDemo
~~~

Kết quả:

~~~text
createdAt=2026-03-01T00:00:00Z
expiresAt=2026-03-01T00:15:00Z
birthday=2000-02-29
invoiceMonth=2026-02
dailyOpening=09:00
meetingLocal=2026-03-02T09:00
meetingZone=Asia/Ho_Chi_Minh
meetingInstant=2026-03-02T02:00:00Z
elapsedMinutes=15
~~~

Điểm cần hiểu:

- **Clock.fixed** giúp kết quả bài học và phép thử độc lập đồng hồ thật. Trong ứng dụng, có thể tiêm **Clock.systemUTC()** khi chạy thật và **Clock.fixed(...)** khi kiểm thử.
- **createdAt** và **expiresAt** là **Instant** vì quy tắc “đúng 15 phút”.
- **birthday** là **LocalDate**; việc quy đổi vùng trong giao diện không làm đổi ngày sinh.
- **invoiceMonth** là **YearMonth** vì không có “ngày hóa đơn” trong dữ kiện.
- **dailyOpening** là **LocalTime**; khi dùng để thực thi phải kết hợp với ngày, vùng và lịch ngoại lệ.
- **meetingWallTime + branchZone** tạo một lịch hẹn ở vùng xác định; mới lúc đó suy ra **meetingInstant**. 09:00 ở UTC+07:00 tương ứng 02:00 UTC vào ngày nêu trên.

Ví dụ trên dùng một cuộc hẹn không nằm trong thời gian chuyển DST. Với những vùng có DST, cần thêm chính sách rõ ràng như phần tiếp theo.

## 7. DST: giờ địa phương có thể không tồn tại hoặc xảy ra hai lần

Khi đồng hồ chuyển sang giờ mùa hè (**gap**), một khoảng giờ địa phương bị bỏ qua. Khi chuyển về giờ mùa đông (**overlap**), một khoảng giờ địa phương xuất hiện hai lần với hai offset khác nhau. Vì vậy, cặp **LocalDateTime + ZoneId** có thể tương ứng với 0, 1 hoặc 2 Instant.

Ví dụ tại **America/New_York** trong năm 2026: ngày 08/03 chuyển sang giờ mùa hè và ngày 01/11 chuyển về giờ tiêu chuẩn. Tạo tệp **DstChoiceDemo.java**:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class DstChoiceDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        ZonedDateTime before = ZonedDateTime.of(
                2026, 3, 7, 12, 0, 0, 0, newYork);

        System.out.println("calendarDay=" + before.plusDays(1));
        System.out.println("elapsed24Hours=" + before.plusHours(24));

        LocalDateTime missing =
                LocalDateTime.of(2026, 3, 8, 2, 30);
        System.out.println("gapOffsets=" +
                newYork.getRules().getValidOffsets(missing));
        System.out.println("gapAtZone=" + missing.atZone(newYork));

        LocalDateTime repeated =
                LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> candidates =
                newYork.getRules().getValidOffsets(repeated);
        System.out.println("overlapOffsets=" + candidates);
    }
}
~~~

Chạy:

~~~bash
javac DstChoiceDemo.java
java DstChoiceDemo
~~~

Kết quả dự kiến theo quy tắc múi giờ IANA hiện hành cho các ngày trên:

~~~text
calendarDay=2026-03-08T12:00-04:00[America/New_York]
elapsed24Hours=2026-03-08T13:00-04:00[America/New_York]
gapOffsets=[]
gapAtZone=2026-03-08T03:30-04:00[America/New_York]
overlapOffsets=[-04:00, -05:00]
~~~

**Giải thích:** một ngày lịch từ trưa 07/03 tới trưa 08/03 chỉ cách nhau 23 giờ do đồng hồ nhảy từ 02:00 lên 03:00. **LocalDateTime.atZone(...)** mặc định đẩy giờ không tồn tại 02:30 tới 03:30; ở thời điểm trùng lặp, có hai offset hợp lệ.

Trong nghiệp vụ đặt vé, thanh toán hoặc gửi thông báo, **không nên mặc nhiên coi cách phân giải mặc định là chính sách sản phẩm**. Hãy quyết định rõ: từ chối giờ không tồn tại, dịch sang giờ hợp lệ hay yêu cầu người dùng chọn offset. Có thể kiểm tra **ZoneRules.getValidOffsets(localDateTime)**: 0 phần tử là gap, 1 là duy nhất, 2 là overlap. Khi cần chính sách nghiêm ngặt, cân nhắc **ZonedDateTime.ofStrict(...)** với offset đã xác nhận.

Quy tắc múi giờ theo địa phương có thể được cập nhật bởi chính quyền. Với sự kiện **tương lai**, nếu phải luôn diễn ra đúng 09:00 theo luật địa phương lúc đó, hãy giữ thông tin lịch gốc và ZoneId để tái tính Instant khi quy tắc được cập nhật. Đừng chỉ lưu Instant rồi xóa thông tin thời gian mong muốn theo địa phương.

## 8. Tình huống nghiệp vụ: mô hình nên lưu những trường nào?

### 8.1. Sinh nhật và ngày kỷ niệm

- Ngày sinh đầy đủ: **LocalDate**.
- Ngày kỷ niệm lặp hằng năm mà không cần năm gốc: **MonthDay**.
- Nếu rơi vào **29/02** trong năm không nhuận, phải quy định tổ chức vào 28/02, 01/03 hay chỉ đúng năm nhuận. Đây là chính sách nghiệp vụ, không do kiểu dữ liệu tự chọn.
- Tuổi phụ thuộc **ngày hiện tại theo vùng áp dụng**, không phải lấy số mili giây chia 365 ngày. Có thể dùng **Period.between(birthDate, today).getYears()**, sau khi xác định today theo vùng liên quan và chính sách tuổi cho ngày nhuận.

### 8.2. Lịch hẹn và sự kiện có giờ bắt đầu

Ví dụ người dùng đặt khám lúc **09:00 ngày 02/03/2026 ở Asia/Ho_Chi_Minh**. Thiết kế có thể lưu:

~~~text
appointmentLocal = 2026-03-02T09:00
appointmentZone  = Asia/Ho_Chi_Minh
resolvedStartAt   = 2026-03-02T02:00:00Z
~~~

**appointmentLocal + appointmentZone** giữ ý định người dùng; **resolvedStartAt (Instant)** phục vụ xếp lịch, sắp thứ tự, gửi thông báo sau khi đã giải quyết múi giờ. Nếu nghiệp vụ không được phép dời giờ địa phương sau khi đặt, cần định nghĩa chính sách cập nhật khi quy tắc múi giờ thay đổi.

Nếu hệ thống chỉ tổ chức sự kiện đã cố định theo thời điểm tuyệt đối, một Instant có thể đủ. Nếu lịch lặp theo giờ địa phương, không thể tái tạo đầy đủ chỉ từ một Instant.

### 8.3. Tác vụ chạy hằng ngày hoặc hằng tuần

“Chạy lúc 08:00 mỗi ngày theo múi giờ của công ty” nên lưu **LocalTime + ZoneId + quy tắc lịch lặp**. Lần chạy kế tiếp cần được tính từ **ngày địa phương kế tiếp hợp lệ**. Nếu chỉ cộng **Duration.ofDays(1)** vào Instant lần trước, sau chuyển DST lịch có thể chuyển thành 07:00 hoặc 09:00 theo đồng hồ địa phương.

### 8.4. Khuyến mại theo ngày địa phương

“Giảm giá tới hết ngày 31/03 tại Tokyo” bắt đầu từ thông tin **LocalDate + ZoneId** và quy tắc bao hàm ngày cuối. Để lọc đơn hàng theo thời điểm, thường nên tạo **[startInclusive, endExclusive)** trên trục Instant:

- start = đầu ngày bắt đầu tại **Asia/Tokyo**;
- endExclusive = đầu ngày **01/04** tại cùng ZoneId;
- điều kiện: **createdAt >= start** và **createdAt < endExclusive**.

Không tự đặt “23:59:59.999”, vì độ chính xác lưu trữ khác nhau và có thể bỏ sót dữ liệu. Đầu ngày ở một số vùng/ngày lịch sử không luôn bằng 00:00:00; dùng **LocalDate.atStartOfDay(zone)** để nhận thời điểm hợp lệ sớm nhất của ngày theo quy tắc vùng.

### 8.5. Thanh toán, timeout và SLA

“Phiên hết hạn sau đúng 15 phút” dùng **Instant + Duration**. “Hóa đơn đến hạn sau 1 tháng lịch tại địa phương khách hàng” cần **LocalDate / ZonedDateTime + Period hoặc plusMonths**, theo chính sách ngày cuối tháng, rồi chuyển thành Instant nếu cần tự động thực thi. Hai yêu cầu có thể cùng xuất hiện trong một hệ thống mà không nên dùng chung một kiểu.

## 9. Lưu trữ, API và múi giờ: giữ trọn ý nghĩa qua các tầng

### JSON và hợp đồng API

Ưu tiên chuỗi ISO-8601 với thông tin đúng nghĩa:

~~~json
{
  "createdAt": "2026-03-01T00:00:00Z",
  "birthDate": "2000-02-29",
  "billingMonth": "2026-02",
  "dailyOpening": "09:00:00",
  "appointmentLocal": "2026-03-02T09:00:00",
  "appointmentZone": "Asia/Ho_Chi_Minh",
  "appointmentInstant": "2026-03-02T02:00:00Z"
}
~~~

Những trường trên minh họa các loại thông tin khác nhau. Khi thiết kế API thật, chỉ trả những trường hợp đồng cần và xác định nguồn chân lý để tránh hai trường mâu thuẫn.

- Chuỗi **2026-03-02T09:00:00** không chứa offset: không gọi nó là UTC.
- Chuỗi **2026-03-02T09:00:00+07:00** có offset nhưng chưa chứa danh tính vùng theo quy tắc địa lý.
- Chuỗi **2026-03-02T02:00:00Z** xác định Instant.
- **ZonedDateTime.toString()** có thể chứa phần **[Asia/Ho_Chi_Minh]**; không giả định mọi hệ thống JSON đều hỗ trợ định dạng vùng mở rộng này. Khi cần, gửi ZoneId thành trường riêng.

### Cơ sở dữ liệu

| Dữ liệu | Ánh xạ thường phù hợp | Điều phải kiểm tra |
|---|---|---|
| LocalDate | SQL DATE | Driver/ORM và loại lịch |
| LocalTime | SQL TIME không timezone | Độ chính xác phần giây |
| LocalDateTime | TIMESTAMP WITHOUT TIME ZONE | Không hiểu nhầm là UTC/Instant |
| Instant hoặc OffsetDateTime | Kiểu timestamp biểu diễn thời điểm (ví dụ PostgreSQL TIMESTAMPTZ) | Driver/ORM, chuyển đổi UTC và độ chính xác |
| YearMonth / MonthDay | Hai thành phần rõ nghĩa hoặc chuỗi có ràng buộc | Schema và validation; không tự thêm ngày |
| LocalDateTime + ZoneId | Nhiều cột: giờ lịch + định danh vùng | Giữ thông tin vùng nếu nghiệp vụ cần |

**Cảnh báo về PostgreSQL:** **TIMESTAMPTZ** biểu diễn thời điểm đã quy đổi; nó **không giữ nguyên tên ZoneId** hoặc offset văn bản ban đầu. Muốn giữ “Asia/Ho_Chi_Minh”, phải có cột riêng. Cách ánh xạ kiểu Java với SQL phụ thuộc JDBC driver, ORM, phiên bản và cấu hình; kiểm thử vòng **ghi → đọc lại** trên hệ quản trị dữ liệu đang dùng, đặc biệt cho **Instant**, **OffsetDateTime**, phần nano giây và timezone mặc định kết nối.

### Hiển thị, nhập liệu và timezone mặc định

- Khi **lưu dấu thời gian sự kiện**, dùng Instant làm giá trị chuẩn; khi **hiển thị**, chuyển sang vùng của người xem bằng **instant.atZone(viewerZone)**.
- Khi **nhận lịch địa phương**, yêu cầu hoặc suy ra rõ ZoneId từ ngữ cảnh nghiệp vụ đã xác nhận, kiểm tra gap/overlap, rồi mới tạo Instant.
- Không để **ZoneId.systemDefault()** âm thầm quyết định quy tắc nghiệp vụ. Múi giờ máy chủ/container có thể khác vùng khách hàng và thay đổi sau triển khai.
- **Locale** quyết định cách trình bày ngôn ngữ, còn **ZoneId** quyết định quy tắc thời gian. Định dạng ngày kiểu Việt Nam không có nghĩa vùng thời gian tự là Việt Nam.
- Tránh biểu diễn nghiệp vụ bằng **String** hoặc kiểu di sản **java.util.Date / Calendar** khi thiết kế mới; String là dạng truyền tải/hiển thị, còn các lớp java.time giàu ngữ nghĩa và phần lớn bất biến.

## 10. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Lưu ngày sinh dưới dạng Instant lúc 00:00 UTC | Có thể hiển thị thành ngày hôm trước ở múi giờ âm | LocalDate |
| Lưu thời gian tạo đơn hàng bằng LocalDateTime của máy chủ | Mất vùng, khó so sánh giữa hệ thống | Instant với Clock |
| Lưu lịch hẹn tương lai chỉ bằng offset +07:00 | Không giữ danh tính vùng và quy tắc thay đổi | LocalDateTime + ZoneId (và Instant đã phân giải khi cần) |
| Dùng Instant cho “08:00 hằng ngày” | Khó giữ giờ địa phương qua DST | LocalTime + ZoneId + quy tắc lặp |
| Dùng Duration.ofDays(30) cho “thêm một tháng” | Tháng có 28/29/30/31 ngày | plusMonths(1) / Period với chính sách cuối tháng |
| Cộng 24 giờ để tính “cùng giờ ngày mai” | DST có ngày 23/25 giờ | plusDays(1) trên giá trị lịch/vùng |
| Chuyển LocalDateTime thành Instant như thể là UTC | Tự gán múi giờ sai | Xác định ZoneId hoặc offset trước |
| Cho phép giờ DST gap/overlap mà không xử lý | Có thể dịch giờ hoặc chọn một trong hai Instant ngoài ý muốn | Kiểm tra ZoneRules, đặt chính sách rõ |
| Lưu ZoneId chỉ như +07:00 | Không còn danh tính vùng | Lưu tên IANA, ví dụ Asia/Ho_Chi_Minh |
| Dùng now() trực tiếp trong mọi nhánh và test | Test phụ thuộc đồng hồ hệ thống, đôi khi thiếu ổn định | Tiêm Clock và xác định zone rõ |

## 11. Checklist thiết kế và kiểm thử

Trước khi chốt mô hình dữ liệu, hãy trả lời:

- Người dùng nghĩ đây là **ngày**, **giờ**, **thời điểm**, **khoảng thời gian thực**, hay **khoảng theo lịch**?
- Nghiệp vụ yêu cầu đúng một Instant hay yêu cầu giữ đúng giờ địa phương dù offset tương lai thay đổi?
- Có cần **ZoneId** hay chỉ cần offset mà giao thức cung cấp?
- Quy tắc cho giờ DST không tồn tại/trùng lặp, 29/02, ngày cuối tháng và ngày hết hạn là gì?
- Trường hợp **ngày đóng cửa** có bao gồm cả ngày cuối không, và giới hạn khoảng thời gian được biểu diễn ra sao?
- JSON/database có giữ nguyên giá trị và ý nghĩa sau vòng lưu và đọc không?
- Đã có test với **Clock.fixed**, hai vùng khác nhau, chuyển DST và ngày nhuận chưa?

### Bài luyện tập tự đánh giá

1. “Sinh nhật 15/08” không cần năm gốc: chọn **MonthDay**; nếu cần cả năm sinh, chọn **LocalDate**.
2. “Log lỗi xảy ra ở máy chủ lúc nào?”: chọn **Instant**, hiển thị theo ZoneId khi đọc.
3. “Báo cáo doanh thu kỳ 2026-02”: chọn **YearMonth**.
4. “Chi nhánh Paris mở cửa 09:00 hằng ngày”: **LocalTime + ZoneId + lịch ngoại lệ**, không chỉ Instant.
5. “Đợi đúng 90 giây rồi retry”: **Duration** cho độ dài; có thể cộng vào Instant để tính hạn.
6. “Gia hạn hợp đồng thêm một tháng theo lịch”: **Period / plusMonths** trên ngày thích hợp, cần quy tắc cuối tháng.
7. “Lịch khám 01:30 ngày chuyển giờ mùa đông tại New York”: **LocalDateTime + ZoneId**, yêu cầu chọn offset hoặc xác định chính sách overlap trước khi chốt Instant.

**Nguyên tắc nhớ lâu:** kiểu dữ liệu phải giữ được điều **nghiệp vụ muốn bảo toàn**. **Instant** giữ một thời điểm tuyệt đối; **Local*** giữ thông tin lịch/đồng hồ; **ZonedDateTime / ZoneId** gắn giờ với quy tắc vùng; **Duration** giữ lượng thời gian trôi qua; **Period** giữ đơn vị lịch. Chọn đúng ngữ nghĩa từ đầu giúp tránh lỗi lệch ngày, lệch lịch hẹn và hạn xử lý khi hệ thống mở rộng sang nhiều múi giờ.
