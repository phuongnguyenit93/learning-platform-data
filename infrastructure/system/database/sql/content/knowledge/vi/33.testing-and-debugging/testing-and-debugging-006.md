# Kiểm thử mốc ngày, đổi ngày, múi giờ và biên khoảng thời gian

> **Module:** Database SQL  
> **Chương:** Kiểm thử và gỡ lỗi  
> **Bài học:** Kiểm thử mốc ngày, đổi ngày, múi giờ và biên khoảng thời gian

Các lỗi ngày giờ thường không xuất hiện khi thử dữ liệu giữa trưa. Chúng xuất hiện ở **00:00**, cuối tháng, ngày 29/02, thời điểm đổi năm, thời điểm chuyển sang hoặc rời khỏi giờ mùa hè (DST), hoặc đúng ranh giới giữa hai khoảng thời gian.

Một truy vấn báo cáo có thể bỏ sót sự kiện xảy ra đúng nửa đêm. Một lịch nhắc việc có thể chạy hai lần vào giờ bị lặp khi đồng hồ lùi. Một hợp đồng có hiệu lực đến hết ngày có thể bị đóng sớm vì hệ thống hiểu ngày kết thúc là 00:00 đầu ngày. Một phép cộng 24 giờ có thể tạo ra giờ địa phương khác dự kiến khi đi qua DST. Một test chạy đúng trên máy lập trình viên có thể thất bại trong CI vì timezone của máy chủ hoặc session database khác nhau.

Muốn kiểm thử đúng, trước hết phải xác định **giá trị đang biểu diễn loại thời gian nào**:

- Ngày lịch, ví dụ ngày sinh hoặc ngày nghỉ phép.
- Giờ địa phương trên đồng hồ, ví dụ 09:00 tại văn phòng.
- Một thời điểm tuyệt đối (instant), ví dụ sự kiện xảy ra tại một điểm trên dòng thời gian UTC.
- Thời điểm kèm offset, ví dụ 09:00+07:00.
- Lịch lặp theo múi giờ có quy tắc DST, ví dụ 09:00 mỗi ngày tại Europe/Paris.
- Khoảng thời gian có biên đầu/cuối, ví dụ từ đầu ngày đến đầu ngày kế tiếp.

Bài học này hướng dẫn cách xây dựng fixture, truy vấn và kiểm thử biên ngày giờ trên **PostgreSQL, MySQL, SQL Server, Oracle Database, SQLite và Java/JDBC**. Trọng tâm là tạo kết quả có thể dự đoán, phân biệt ngày lịch với thời lượng thực, và không để timezone ngầm làm thay đổi nghiệp vụ.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt DATE, local datetime, offset datetime, zoned datetime và instant.
2. Xác định timezone có thẩm quyền cho nghiệp vụ: UTC, timezone người dùng hay timezone của tổ chức.
3. Giải thích vì sao offset như +07:00 không thay thế tên vùng timezone.
4. Viết bộ test cho đầu ngày, cuối ngày, nửa đêm và thời điểm đổi ngày.
5. Dùng khoảng nửa mở [start, end) để lọc dữ liệu theo ngày mà không phụ thuộc độ chính xác timestamp.
6. Phân biệt BETWEEN inclusive với điều kiện đầu-cuối nửa mở.
7. Kiểm thử khoảng rỗng, khoảng liền kề, chồng lấn, chứa và giao nhau.
8. Xử lý ngày cuối tháng, năm nhuận, ngày cuối năm và chuyển tuần ISO.
9. Phân biệt cộng một ngày lịch với cộng 24 giờ thực.
10. Kiểm thử DST gap (giờ địa phương không tồn tại) và DST overlap/fold (giờ địa phương xuất hiện hai lần).
11. Hiểu khác biệt kiểu ngày giờ và precision giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite.
12. Nhận diện tác động của timezone session, timezone server và timezone driver.
13. Bind thời gian qua JDBC bằng kiểu Java phù hợp, tránh chuyển qua chuỗi không có contract.
14. Làm test xác định bằng Clock/fixed clock thay vì phụ thuộc thời gian thực.
15. Tạo dữ liệu biên và expected results có thể chạy lặp lại.
16. Kiểm tra rounding/truncation của fractional seconds.
17. Tránh bọc cột timestamp bằng DATE()/CAST() khiến index khó được sử dụng.
18. Thiết kế test cho lịch lặp, thời hạn, retention và báo cáo theo ngày địa phương.
19. Phát hiện khác biệt timezone database giữa Java, OS và DBMS.
20. Xây dựng ma trận integration tests cho nhiều DBMS/driver.

## 2. Mô hình thời gian: xác định đúng thứ cần lưu

Trước khi viết SQL, hãy xác định domain.

| Khái niệm | Ví dụ | Có xác định một instant duy nhất? | Cách lưu thường phù hợp |
|---|---|---:|---|
| Ngày lịch | 2026-10-03 | Không cần instant | DATE hoặc LocalDate |
| Giờ địa phương | 09:30 | Không | TIME hoặc LocalTime |
| Local date-time | 2026-10-03 09:30 | Không, nếu thiếu zone | TIMESTAMP không timezone hoặc LocalDateTime |
| Offset date-time | 2026-10-03T09:30+07:00 | Có, nếu offset hợp lệ | Kiểu có offset hoặc chuyển sang instant |
| Instant | 2026-10-03T02:30:00Z | Có | UTC instant, timestamptz, datetimeoffset theo contract |
| Zoned schedule | 09:00 mỗi ngày tại Asia/Ho_Chi_Minh | Không phải một instant duy nhất cho mọi ngày | Local time + zone ID + recurrence rule |

### 2.1. DATE không phải timestamp lúc nửa đêm

Giá trị DATE = 2026-10-03 chỉ là một ngày lịch. Không nên tự động diễn giải nó thành UTC midnight hoặc local midnight nếu nghiệp vụ chưa định nghĩa timezone.

Ví dụ:
- Ngày sinh 1990-05-12 không phải một instant.
- Ngày nghỉ phép 2026-10-03 là ngày lịch của nhân viên theo timezone/chính sách tổ chức.
- Một sự kiện xảy ra 2026-10-03T00:15:00+07:00 là instant cụ thể.

Nếu lưu ngày sinh bằng timestamp rồi chuyển timezone, có thể hiển thị sang ngày hôm trước hoặc hôm sau. Chọn kiểu DATE cho dữ liệu thực sự chỉ có nghĩa ngày lịch.

### 2.2. LocalDateTime không tự là UTC

Giá trị 2026-10-03 09:00 không đủ thông tin để xác định instant toàn cầu. 09:00 ở Ho Chi Minh City và 09:00 ở London là hai thời điểm khác nhau.

Nếu lưu local timestamp mà sau này cần quy đổi, phải có zone/offset từ một nguồn khác. Không đặt tên cột created_at rồi ngầm giả định nó là UTC nếu kiểu dữ liệu không mang timezone và ứng dụng không enforce contract.

### 2.3. Offset khác timezone

+07:00 là độ lệch so với UTC tại một thời điểm. Asia/Ho_Chi_Minh là tên vùng timezone với quy tắc lịch sử/hiện hành.

Hai vùng có thể cùng offset hiện tại nhưng có lịch sử hoặc quy tắc tương lai khác nhau. Với lịch lặp, cần lưu **zone ID**, không chỉ offset.

### 2.4. Instant và cách hiển thị

Một instant có thể được hiển thị thành nhiều giờ địa phương:

~~~text
Instant: 2026-10-03T02:30:00Z

UTC:                 2026-10-03 02:30
Asia/Ho_Chi_Minh:    2026-10-03 09:30
America/New_York:    2026-10-02 22:30
~~~

Đây là cùng một instant. Khi so sánh hoặc sắp xếp event, hãy so instant; khi hiển thị hoặc nhóm theo ngày nghiệp vụ, chuyển sang timezone phù hợp.

## 3. Xác định timezone có thẩm quyền

Một hệ thống có thể có nhiều timezone:

- **UTC:** lưu/so sánh instant và trao đổi giữa service.
- **Timezone nghiệp vụ:** ví dụ timezone cửa hàng, chi nhánh hoặc tổ chức.
- **Timezone người dùng:** hiển thị trên giao diện.
- **Timezone session DB:** ảnh hưởng một số hàm và kiểu dữ liệu.
- **Timezone host/OS/container:** ảnh hưởng ứng dụng hoặc hàm localtime.
- **Timezone mặc định của JVM:** ảnh hưởng code dùng ZoneId.systemDefault() hoặc API legacy.

Không nên để timezone mặc định của một thành phần tự quyết định timezone nghiệp vụ.

### 3.1. Một chính sách thường dùng

- Lưu event instant theo UTC hoặc kiểu có semantics instant.
- Lưu ngày sinh/ngày nghỉ/ngày hiệu lực dạng DATE khi đó là ngày lịch.
- Lưu timezone ID của chi nhánh/người dùng nếu quy tắc nghiệp vụ phụ thuộc vùng.
- Khi truy vấn theo ngày địa phương, tính hai instant biên theo timezone đó.
- Bind hai biên vào SQL và dùng khoảng nửa mở.
- Cấu hình session timezone rõ ràng nếu DBMS có chuyển đổi ngầm.

### 3.2. Timezone của tenant

Nếu một ứng dụng phục vụ nhiều quốc gia, không dùng một timezone toàn hệ thống cho mọi báo cáo. Một đơn hàng của tenant A có thể thuộc ngày 03/10 tại Asia/Ho_Chi_Minh nhưng vẫn thuộc ngày 02/10 tại America/Los_Angeles.

Hãy xác định timezone từ tenant/store/business entity đã được xác thực, không nhận một chuỗi timezone tùy ý từ request mà không kiểm tra quyền và danh sách hợp lệ.

## 4. Khoảng thời gian và quy tắc biên

Một khoảng thời gian cần xác định rõ:
- Biên đầu có bao gồm không?
- Biên cuối có bao gồm không?
- Khoảng có thể rỗng không?
- Hai khoảng liền kề có chồng lấn không?
- Độ chính xác timestamp là microsecond hay nanosecond?
- Khoảng được đo theo instant hay lịch địa phương?

### 4.1. Khoảng đóng và khoảng nửa mở

Khoảng đóng [start, end] bao gồm cả start và end.

Khoảng nửa mở [start, end) bao gồm start nhưng không bao gồm end.

Ví dụ:

~~~text
Khoảng A: [10:00, 11:00)
Khoảng B: [11:00, 12:00)
~~~

Sự kiện đúng 11:00 thuộc B, không thuộc A. Hai khoảng liền kề không chồng lấn và không có khe hở.

### 4.2. Vì sao nên dùng [start, end)?

Giả sử cần lấy tất cả event của ngày 03/10/2026 theo timezone nghiệp vụ:

~~~sql
WHERE created_at >= :start_instant
  AND created_at <  :next_day_start_instant
~~~

Ưu điểm:
- Không phải đoán timestamp cuối ngày là 23:59:59.999.
- Không phụ thuộc cột lưu millisecond, microsecond hay nanosecond.
- Hai ngày liền kề ghép thành các khoảng không chồng lấn.
- Không bỏ sót giá trị có fractional seconds cao hơn precision bạn đoán.
- Dễ tạo khoảng thời gian cho tháng, tuần, quý và retention.

### 4.3. Vì sao BETWEEN thường gây lỗi ở biên cuối?

BETWEEN thường bao gồm cả hai đầu:

~~~sql
WHERE created_at BETWEEN :start AND :end
~~~

Nếu ngày 03/10 dùng start=00:00:00 và end=23:59:59.999, một giá trị 23:59:59.999500 có thể bị bỏ sót khi precision nguồn/đích cao hơn millisecond.

Nếu dùng end=00:00:00 ngày 04/10 với BETWEEN, event đúng nửa đêm 04/10 sẽ bị tính vào cả ngày 03 và ngày 04.

Với báo cáo theo ngày, điều kiện >= start AND < next_start rõ ràng hơn.

### 4.4. Không tạo “cuối ngày” bằng 23:59:59.999

Các DBMS có precision khác nhau:
- Millisecond.
- Microsecond.
- 100-nanosecond units.
- Nanosecond.
- Một số kiểu cũ có bước làm tròn đặc biệt.

Không có một giá trị cuối ngày dạng 23:59:59.xxx dùng đúng cho mọi cột. Hãy biểu diễn biên cuối là **đầu ngày kế tiếp, loại trừ**.

## 5. Mẫu lọc dữ liệu theo ngày địa phương

Giả sử cột created_at lưu instant và cần báo cáo ngày 03/10/2026 tại Asia/Ho_Chi_Minh.

Tính:
- start = đầu ngày 03/10 tại Asia/Ho_Chi_Minh, chuyển sang UTC.
- end = đầu ngày 04/10 tại Asia/Ho_Chi_Minh, chuyển sang UTC.

Với offset +07:00 ở hai ngày ví dụ này:

~~~text
start = 2026-10-02T17:00:00Z
end   = 2026-10-03T17:00:00Z
~~~

SQL:

~~~sql
SELECT id, created_at
FROM orders
WHERE created_at >= :start_utc
  AND created_at <  :end_utc;
~~~

Nếu timezone địa phương có DST, hai mốc UTC không nhất thiết cách nhau đúng 24 giờ. Phải tính hai đầu ngày độc lập theo timezone rules.

### 5.1. Lọc theo ngày UTC

Nếu nghiệp vụ định nghĩa ngày UTC, biên đơn giản:

~~~text
start = 2026-10-03T00:00:00Z
end   = 2026-10-04T00:00:00Z
~~~

Không dùng local timezone của server để tính các mốc này.

### 5.2. Lọc theo ngày của cửa hàng

Một cửa hàng ở New York có thể báo cáo theo America/New_York, trong khi service chạy ở UTC và người dùng ở Việt Nam. Tính ranh giới bằng zone ID của cửa hàng, không bằng systemDefault() của service hoặc timezone session tình cờ.

### 5.3. Tránh bọc cột bằng hàm

Một truy vấn dễ viết nhưng có thể khó tận dụng index:

~~~sql
WHERE DATE(created_at) = :business_date
~~~

Hoặc:

~~~sql
WHERE CAST(created_at AS DATE) = :business_date
~~~

Các biểu thức này còn phụ thuộc timezone/session và cách cast của DBMS. Nếu cột có B-tree index, thường nên tính biên bên ngoài rồi lọc trực tiếp:

~~~sql
WHERE created_at >= :start_instant
  AND created_at <  :end_instant
~~~

Expression/function index có thể giúp một số truy vấn, nhưng cần thiết kế và đo riêng; không nên bọc cột một cách vô thức.

## 6. Kiểm thử ngày cuối tháng, cuối năm và năm nhuận

Các mốc lịch không có độ dài cố định.

### 6.1. Số ngày trong tháng

| Tháng | Số ngày |
|---|---:|
| Tháng 1 | 31 |
| Tháng 2 năm thường | 28 |
| Tháng 2 năm nhuận | 29 |
| Tháng 4, 6, 9, 11 | 30 |
| Tháng 3, 5, 7, 8, 10, 12 | 31 |

### 6.2. Quy tắc năm nhuận Gregorian

Một năm là năm nhuận nếu:
- Chia hết cho 400; hoặc
- Chia hết cho 4 nhưng không chia hết cho 100.

Ví dụ:
- 2000 là năm nhuận.
- 1900 không phải năm nhuận.
- 2024 là năm nhuận.
- 2026 không phải năm nhuận.
- 2100 không phải năm nhuận.

Không chỉ test 2024; cần test cả năm thế kỷ để phát hiện code tự viết sai quy tắc chia hết cho 100/400.

### 6.3. Fixture ngày nhuận

| Input | Kỳ vọng |
|---|---|
| 2024-02-28 + 1 calendar day | 2024-02-29 |
| 2024-02-29 + 1 calendar day | 2024-03-01 |
| 2025-02-28 + 1 calendar day | 2025-03-01 |
| 2000-02-29 | Hợp lệ |
| 1900-02-29 | Không hợp lệ |
| 2100-02-29 | Không hợp lệ |

### 6.4. Ngày cuối tháng và cộng tháng

Cộng một tháng vào 31/01 không đơn giản:
- Có thư viện clamp về ngày cuối tháng 02.
- Có API có thể báo lỗi hoặc điều chỉnh theo quy tắc riêng.
- SQL date arithmetic có semantics tùy DBMS.

Ví dụ policy clamp:
- 2025-01-31 + 1 month → 2025-02-28.
- 2024-01-31 + 1 month → 2024-02-29.

Nếu nghiệp vụ yêu cầu “ngày 31 hàng tháng”, cần định nghĩa hành vi ở tháng không có ngày 31: chạy ngày cuối tháng, bỏ qua tháng đó hay chuyển sang ngày 01 tháng sau.

### 6.5. Đổi năm và biên tuần

Test:
- 31/12 sang 01/01.
- 30/12/2024 và 01/01/2025 theo ISO week.
- Tuần ISO bắt đầu thứ Hai và tuần 1 là tuần có thứ Năm đầu tiên.
- Ngày đầu tuần theo locale có thể khác ISO.
- Quý tài chính có thể không trùng quý lịch.

Không dùng WEEK() hoặc DAYOFWEEK() mà chưa xác định hệ thống đang dùng ISO week, tuần bắt đầu Chủ nhật hay quy ước riêng.

## 7. DST: giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần

DST (Daylight Saving Time) làm đồng hồ địa phương nhảy tiến hoặc lùi theo quy tắc của một vùng.

### 7.1. Gap — giờ địa phương không tồn tại

Khi đồng hồ nhảy từ 01:59:59 lên 03:00:00, các local times từ 02:00 đến 02:59 không tồn tại.

Một lịch “chạy lúc 02:30” trong ngày đó cần policy:
- Bỏ qua lần chạy.
- Chạy ngay ở thời điểm hợp lệ kế tiếp.
- Dời sang 03:30.
- Dùng một quy tắc khác do nghiệp vụ xác định.

Không thể chỉ lưu LocalDateTime 02:30 và mong nó tự ánh xạ thành một instant duy nhất.

### 7.2. Overlap/fold — giờ địa phương xuất hiện hai lần

Khi đồng hồ lùi, ví dụ từ 02:59:59 về 02:00:00, local time 02:30 có thể xuất hiện hai lần với hai offset khác nhau.

Một lịch chạy 02:30 có thể:
- Chạy ở lần đầu.
- Chạy ở lần thứ hai.
- Chạy hai lần.
- Chỉ chạy một lần theo một policy đã định nghĩa.

Một LocalDateTime đơn lẻ không phân biệt được hai instant đó.

### 7.3. DST không phải lúc nào cũng đổi đúng một giờ

Có timezone chuyển 30 phút, có thay đổi lịch sử lớn hơn, và có vùng từng bỏ qua cả một ngày lịch khi đổi đường đổi ngày. Không hardcode giả định mọi DST đều là +1 giờ vào Chủ nhật tháng 3 và -1 giờ vào tháng 11.

### 7.4. Zone rules có thể thay đổi

Chính phủ có thể thay đổi luật timezone sau khi ứng dụng đã được triển khai. JVM, OS và DBMS có thể cập nhật timezone database ở thời điểm khác nhau. Một lịch trong tương lai có thể được quy đổi khác sau khi tzdb được cập nhật.

Nếu nghiệp vụ cần tái hiện chính xác kết quả đã tính trong quá khứ, hãy lưu instant thực tế đã thực hiện, zone ID và metadata cần thiết theo chính sách audit.

## 8. Kiểm thử DST trong Java

Java Time API cung cấp ZoneId, ZoneRules và ZoneOffset.

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDate date = LocalDate.of(2026, 3, 8);

ZonedDateTime start = date.atStartOfDay(zone);
ZonedDateTime nextStart = date.plusDays(1).atStartOfDay(zone);

Instant startInstant = start.toInstant();
Instant endInstant = nextStart.toInstant();

Duration actualDay = Duration.between(startInstant, endInstant);
System.out.println(actualDay);
~~~

Với ngày DST bắt đầu ở vùng có thay đổi tương ứng, actualDay có thể ngắn hơn 24 giờ. Ngày DST kết thúc có thể dài hơn 24 giờ.

### 8.1. Kiểm tra local time có gap/overlap

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);

List<ZoneOffset> offsets =
    zone.getRules().getValidOffsets(local);

if (offsets.isEmpty()) {
    // Local time nằm trong DST gap: không tồn tại.
} else if (offsets.size() == 1) {
    // Local time có đúng một offset hợp lệ.
} else {
    // Local time nằm trong overlap: có hai offset hợp lệ.
}
~~~

Ngày minh họa cần được xác nhận theo timezone rules của tzdb trong runtime test; fixture chính thức nên chọn ngày DST của zone và pin/update tzdb có chủ đích.

### 8.2. atStartOfDay

~~~java
LocalDate businessDate = LocalDate.of(2026, 10, 3);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = businessDate.atStartOfDay(zone).toInstant();
Instant end = businessDate.plusDays(1).atStartOfDay(zone).toInstant();
~~~

atStartOfDay(zone) trả thời điểm đầu ngày hợp lệ theo quy tắc zone, không nhất thiết là 00:00 nếu nửa đêm bị chuyển tiếp. Với ngày bị bỏ qua toàn bộ do thay đổi timezone lịch sử, cần xác định policy của nghiệp vụ.

### 8.3. Hai phép cộng không tương đương

~~~java
ZonedDateTime zdt = ...;

ZonedDateTime nextCalendarDay = zdt.plusDays(1);
ZonedDateTime after24Hours = zdt.plus(Duration.ofHours(24));
~~~

plusDays(1) đi theo calendar day tại zone. Cộng Duration 24 giờ là cộng thời lượng tuyệt đối. Qua DST, giờ địa phương của hai kết quả có thể khác nhau.

## 9. Test timezone bằng Instant và ZoneId, không bằng giả định máy

Java nên dùng:
- Instant cho thời điểm tuyệt đối.
- LocalDate cho ngày lịch.
- LocalTime cho giờ trên đồng hồ.
- LocalDateTime cho local wall-clock chưa gắn zone.
- OffsetDateTime khi cần offset.
- ZonedDateTime khi cần zone rules.
- Duration cho thời lượng tuyệt đối.
- Period cho khoảng lịch theo năm/tháng/ngày.

### 9.1. Không dùng systemDefault trong logic nghiệp vụ nếu không chủ đích

~~~java
ZoneId.systemDefault()
~~~

trả timezone mặc định của JVM/host. Nó có thể khác giữa máy developer, CI, container và production.

Thay vào đó:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
~~~

hoặc lấy zone ID đã lưu/được cấu hình cho tenant.

### 9.2. Test Clock

Không gọi LocalDate.now() hoặc Instant.now() rải rác trong business logic nếu cần test xác định. Inject Clock:

~~~java
public final class BillingService {
    private final Clock clock;
    private final ZoneId businessZone;

    public BillingService(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public LocalDate today() {
        return LocalDate.now(clock.withZone(businessZone));
    }

    public Instant now() {
        return Instant.now(clock);
    }
}
~~~

Test:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-10-03T02:30:00Z"),
    ZoneOffset.UTC
);

BillingService service =
    new BillingService(fixed, ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Kết quả không thay đổi theo thời điểm test chạy hoặc timezone mặc định của máy.

## 10. Precision và rounding của timestamp

Không phải mọi kiểu timestamp lưu được cùng độ chính xác.

| DBMS | Kiểu thường gặp | Precision cần chú ý |
|---|---|---|
| PostgreSQL | timestamp/timestamptz | Độ phân giải lưu thường đến microsecond |
| MySQL | DATETIME/TIMESTAMP | Fractional seconds precision tối đa 6 chữ số |
| SQL Server | datetime2/datetimeoffset | Có thể khai báo precision 0–7; datetime cũ có bước làm tròn riêng |
| Oracle | TIMESTAMP variants | Fractional seconds precision có thể đến 9 |
| SQLite | TEXT/REAL/INTEGER | Không có timestamp storage class với precision thống nhất; do format/representation ứng dụng chọn |

### 10.1. Millisecond không bằng microsecond

Ví dụ:
- 12:00:00.123
- 12:00:00.123456
- 12:00:00.123999

Nếu ứng dụng Java giữ nanosecond nhưng cột chỉ giữ microsecond, dữ liệu có thể bị truncate hoặc round theo DBMS/driver. Không so timestamp bằng equality sau round-trip nếu chưa chuẩn hóa precision.

### 10.2. Rounding và truncation

Cần xác định:
- DBMS làm tròn hay cắt phần dư?
- Driver chuyển Java nanoseconds ra sao?
- CAST sang kiểu precision thấp làm gì?
- So sánh trước/sau có sai số nào?
- Có lưu original timestamp từ nguồn để audit không?

Ví dụ, timestamp 10:00:00.123456789 ghi vào cột microsecond có thể thành .123456 hoặc .123457 tùy chuyển đổi. Kiểm thử bằng đúng driver và kiểu cột.

### 10.3. Biên khoảng không phụ thuộc precision

Dùng [start, end) giúp không cần tự tạo 23:59:59.999999. Tuy nhiên, vẫn phải kiểm tra dữ liệu được làm tròn qua biên khi nguồn và đích có precision khác nhau.

### 10.4. Leap second

Nhiều DBMS và Java time APIs không biểu diễn leap second như một giây :60 theo cùng cách hệ thiên văn. Một số nguồn thời gian có thể smear hoặc normalize. Nếu nghiệp vụ yêu cầu độ chính xác thời gian khoa học/viễn thông, cần contract riêng và nguồn timekeeping chuyên dụng; không giả định timestamp SQL là UTC clock vật lý hoàn hảo.

## 11. Kiểu ngày giờ trên PostgreSQL

PostgreSQL có:
- DATE.
- TIME [WITHOUT TIME ZONE].
- TIME WITH TIME ZONE (timetz).
- TIMESTAMP WITHOUT TIME ZONE.
- TIMESTAMP WITH TIME ZONE (timestamptz).
- INTERVAL.

### 11.1. TIMESTAMP WITHOUT TIME ZONE

Lưu local date-time, không tự biểu diễn instant. Khi bind/đọc, đừng tự chuyển sang UTC nếu không có zone contract.

### 11.2. TIMESTAMPTZ

TIMESTAMP WITH TIME ZONE biểu diễn instant; PostgreSQL chuẩn hóa theo semantics nội bộ và hiển thị theo timezone session. Nó **không giữ nguyên zone ID nguồn** như Asia/Ho_Chi_Minh.

Hai input có offset khác nhau nhưng cùng instant sẽ biểu diễn cùng thời điểm.

### 11.3. Kiểm tra session timezone

~~~sql
SHOW TimeZone;
~~~

Có thể đặt cho session test:

~~~sql
SET TIME ZONE 'UTC';
~~~

hoặc:

~~~sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';
~~~

Cùng một timestamptz có thể hiển thị giờ khác nhau theo session, nhưng instant không đổi.

### 11.4. Tính ngày theo timezone

Với timestamp có timezone, việc truncate/cast sang ngày có thể phụ thuộc timezone session. Tính ranh giới ở ứng dụng theo ZoneId hoặc dùng biểu thức PostgreSQL có timezone chỉ định rõ, rồi test trên session UTC và session khác.

### 11.5. Test khoảng

~~~sql
SELECT id
FROM event_log
WHERE occurred_at >= TIMESTAMPTZ '2026-10-02 17:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-10-03 17:00:00+00';
~~~

Đây là khoảng một ngày địa phương UTC+07 ở ví dụ cụ thể, không phải công thức tổng quát cho timezone có DST.

## 12. Kiểu ngày giờ trên MySQL

MySQL có DATE, TIME, DATETIME, TIMESTAMP và YEAR.

### 12.1. DATETIME và TIMESTAMP

- DATETIME lưu giá trị ngày giờ theo format của cột và không tự chuyển theo session timezone như TIMESTAMP.
- TIMESTAMP có conversion theo timezone connection/session giữa giá trị được gửi/nhận và lưu trữ UTC theo semantics MySQL.

Vì vậy cùng một chuỗi bind vào DATETIME và TIMESTAMP có thể hiển thị khác khi session time_zone thay đổi.

### 12.2. Kiểm tra timezone session

~~~sql
SELECT
    @@session.time_zone,
    @@global.time_zone,
    NOW(),
    UTC_TIMESTAMP();
~~~

Trong test, đặt session time_zone rõ ràng. Không chỉ kiểm tra global config vì connection pool có thể thiết lập session riêng.

### 12.3. CONVERT_TZ

~~~sql
SELECT CONVERT_TZ(
    '2026-10-03 09:00:00',
    'Asia/Ho_Chi_Minh',
    '+00:00'
);
~~~

Named timezone conversions cần timezone tables được nạp/duy trì. Nếu function trả NULL, kiểm tra timezone tables và tên zone hợp lệ; đừng vội coi dữ liệu input là NULL.

### 12.4. DATE arithmetic

MySQL có DATE_ADD/DATE_SUB:

~~~sql
SELECT DATE_ADD(DATE '2026-01-31', INTERVAL 1 MONTH);
~~~

Kết quả cuối tháng phải được kiểm thử theo semantics MySQL và kiểu đối số; đừng giả định giống Java Period hay Oracle interval.

### 12.5. Precision

DATETIME(fsp) và TIMESTAMP(fsp) có fractional seconds precision tối đa 6. Nếu source giữ nanoseconds, hãy định nghĩa rounding/truncation khi import.

## 13. Kiểu ngày giờ trên SQL Server

Các kiểu phổ biến:
- DATE.
- TIME(p).
- DATETIME.
- SMALLDATETIME.
- DATETIME2(p).
- DATETIMEOFFSET(p).

### 13.1. DATETIME2 và DATETIMEOFFSET

DATETIME2 lưu date/time với precision cấu hình, không chứa timezone. DATETIMEOFFSET lưu local date/time cùng offset, biểu diễn thời điểm có offset; nó không giữ tên vùng IANA/Windows timezone như một schedule zone.

Nếu cần tái hiện lịch tại một vùng, lưu zone ID riêng.

### 13.2. DATETIME cũ

DATETIME cũ có độ chính xác và rounding khác DATETIME2. Không kiểm thử chỉ bằng chuỗi đến millisecond rồi giả định round-trip chính xác. Với schema mới, thường cân nhắc DATETIME2 theo precision cần thiết.

### 13.3. AT TIME ZONE

SQL Server có AT TIME ZONE với tên timezone theo hệ Windows:

~~~sql
SELECT
    CAST('2026-10-03T09:00:00' AS datetime2)
    AT TIME ZONE 'SE Asia Standard Time';
~~~

Tên zone của Windows không luôn giống IANA ID như Asia/Ho_Chi_Minh. Cần mapping có kiểm soát giữa hai hệ tên và kiểm thử DST.

### 13.4. GETDATE, SYSDATETIME và SYSUTCDATETIME

Các hàm trả kiểu/precision/timezone khác:
- GETDATE(): datetime theo thời gian local của server.
- SYSDATETIME(): datetime2 độ chính xác cao hơn, local server.
- SYSUTCDATETIME(): datetime2 theo UTC.

Không thay một hàm bằng hàm khác mà không xác định domain semantics và kiểu kết quả.

## 14. Kiểu ngày giờ trên Oracle

Oracle có:
- DATE: ngày và thành phần giờ/phút/giây.
- TIMESTAMP(p).
- TIMESTAMP WITH TIME ZONE.
- TIMESTAMP WITH LOCAL TIME ZONE.
- INTERVAL YEAR TO MONTH.
- INTERVAL DAY TO SECOND.

### 14.1. DATE của Oracle không phải date-only

Oracle DATE có giờ, phút và giây. Nếu cột lưu ngày sinh nhưng giá trị được insert với giờ khác 00:00:00, so sánh bằng DATE literal có thể không match như mong đợi.

Dùng TRUNC(date_column) có thể bỏ phần giờ trong so sánh nhưng ảnh hưởng index thường; tốt hơn lưu ngày theo contract hoặc dùng khoảng đầu ngày kế tiếp.

### 14.2. TIMESTAMP WITH TIME ZONE

Có thông tin timezone/offset trong giá trị, với các quy tắc Oracle. Khi so sánh/hiển thị, xác định semantics của source và session.

### 14.3. TIMESTAMP WITH LOCAL TIME ZONE

Oracle chuẩn hóa lưu trữ theo database timezone và hiển thị theo session timezone; không giữ nguyên timezone vùng ban đầu của client. Kiểm thử đổi SESSIONTIMEZONE để quan sát kết quả.

### 14.4. Xem timezone môi trường

~~~sql
SELECT DBTIMEZONE, SESSIONTIMEZONE
FROM dual;
~~~

Các giá trị này có thể khác. Không giả định session timezone bằng database timezone hoặc timezone của OS.

### 14.5. CURRENT_DATE, CURRENT_TIMESTAMP và SYSDATE

Các hàm Oracle có nguồn timezone/kiểu trả về khác nhau:
- CURRENT_DATE theo timezone session, kiểu DATE.
- CURRENT_TIMESTAMP theo timezone session, kiểu TIMESTAMP WITH TIME ZONE.
- SYSDATE theo clock của database host, kiểu DATE.
- SYSTIMESTAMP theo clock hệ thống và thông tin timezone/offset của host.

Chọn theo contract; không dùng thay thế tùy tiện.

## 15. SQLite: ngày giờ là contract ứng dụng

SQLite không có một storage class TIMESTAMP riêng. Ngày giờ thường được lưu:
- TEXT theo format ISO-8601 đã quy định.
- REAL theo Julian day.
- INTEGER theo Unix epoch (thường seconds hoặc milliseconds do ứng dụng định nghĩa).

### 15.1. Chọn một representation và pin đơn vị

Ví dụ INTEGER milliseconds:

~~~sql
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY,
    occurred_at_epoch_ms INTEGER NOT NULL
);
~~~

Tên cột làm rõ đơn vị. Không trộn seconds và milliseconds trong cùng cột.

Ví dụ TEXT UTC:

~~~text
2026-10-03T02:30:00.123Z
~~~

Cần thống nhất:
- Có luôn Z/UTC không?
- Có fractional seconds mấy chữ số?
- Có padding/format cố định không?
- Có lưu offset khác UTC không?
- Lexicographic ordering có tương đương chronological ordering trong mọi format được phép không?

### 15.2. Date/time functions

~~~sql
SELECT datetime('now');
SELECT date('now');
SELECT time('now');
SELECT unixepoch('now');
~~~

Các hàm có modifier như localtime/utc và hỗ trợ format phụ thuộc SQLite version. 'now' là thời điểm hiện tại theo clock SQLite, không phải clock giả lập của Java Clock.

### 15.3. Không dùng localtime như IANA zone converter tổng quát

Modifier localtime phụ thuộc môi trường local của host. SQLite built-in không thay thế timezone database đầy đủ cho mọi zone ID/tenant. Với timezone nghiệp vụ, tính biên trong Java/ứng dụng có tzdb phù hợp rồi bind giá trị vào SQLite.

### 15.4. Test runtime

SQLite được nhúng qua JDBC có thể dùng native library khác version với CLI trên máy. Kiểm tra sqlite_version() từ chính connection ứng dụng và xác nhận JSON/date/RETURNING features cần dùng.

## 16. CURRENT_TIMESTAMP và clock của DBMS

Hàm “bây giờ” không có semantics giống nhau ở mọi DBMS.

| DBMS | Hàm ví dụ | Điều cần kiểm tra |
|---|---|---|
| PostgreSQL | CURRENT_TIMESTAMP, now(), statement_timestamp(), clock_timestamp() | now()/CURRENT_TIMESTAMP gắn với thời điểm bắt đầu transaction; các hàm khác có semantics khác |
| MySQL | NOW(), CURRENT_TIMESTAMP, UTC_TIMESTAMP() | Session timezone và thời điểm đánh giá statement |
| SQL Server | GETDATE(), SYSDATETIME(), SYSUTCDATETIME() | Local server clock hay UTC; kiểu/precision |
| Oracle | SYSDATE, SYSTIMESTAMP, CURRENT_DATE, CURRENT_TIMESTAMP | DB host vs session timezone; DATE vs TIMESTAMP |
| SQLite | datetime('now'), unixepoch('now') | Clock/runtime UTC và cách biểu diễn |

### 16.1. Không viết test phụ thuộc đồng hồ thật

Test như:

~~~sql
INSERT INTO event_log(created_at) VALUES (CURRENT_TIMESTAMP);
SELECT * FROM event_log WHERE created_at = CURRENT_TIMESTAMP;
~~~

có thể thất bại vì hai lần gọi ở hai thời điểm khác nhau, precision khác nhau hoặc transaction semantics.

Thay vào đó:
- Bind timestamp fixture cố định.
- Hoặc dùng clock abstraction trong ứng dụng.
- Nếu cần test DB current-time function, kiểm tra theo khoảng/tolerance đã định nghĩa và cô lập khỏi business logic.

### 16.2. Clock của ứng dụng và database có thể lệch

Nếu app tạo created_at bằng Java Clock còn DB tạo updated_at bằng DEFAULT CURRENT_TIMESTAMP, hai timestamp có thể lệch do NTP, timezone hoặc transaction timing.

Quyết định một nguồn authoritative:
- DB clock cho toàn bộ thời điểm ghi; hoặc
- App clock được đồng bộ và bind vào DB; hoặc
- Lưu cả source_event_time và received_at nếu cần phân biệt thời điểm xảy ra với thời điểm hệ thống nhận.

Không trộn hai nguồn mà không ghi semantics.

## 17. SQL function và date arithmetic giữa các DBMS

Tên hàm tương tự không bảo đảm semantics giống nhau.

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Cắt về đầu ngày/đơn vị | date_trunc | DATE()/DATE_FORMAT | DATETRUNC theo version; CAST | TRUNC(date) | date()/strftime |
| Cộng ngày | + INTERVAL | DATE_ADD | DATEADD | + number/INTERVAL | date/time modifier |
| Đổi timezone | AT TIME ZONE | CONVERT_TZ | AT TIME ZONE | AT TIME ZONE/FROM_TZ | App/host/extension |
| Hiện tại UTC | now() với zone semantics; timezone session | UTC_TIMESTAMP | SYSUTCDATETIME | SYSTIMESTAMP/AT TIME ZONE UTC | datetime('now') |
| Trích năm/tháng | EXTRACT | YEAR/MONTH | DATEPART | EXTRACT | strftime |
| Epoch | EXTRACT(EPOCH...) | UNIX_TIMESTAMP | DATEDIFF_BIG/logic | Epoch calculation | unixepoch |

Cần kiểm tra kiểu trả về, timezone, precision, null handling và behavior khi date invalid.

### 17.1. DATE_TRUNC và timezone

PostgreSQL date_trunc trên timestamptz có thể dùng timezone session nếu không chỉ định rõ. Một test chạy session UTC và session Asia/Ho_Chi_Minh có thể tạo nhóm ngày khác nhau. Tính biên bằng zone rõ ràng hoặc chỉ định timezone trong hàm phù hợp phiên bản.

### 17.2. DATEADD và calendar semantics

SQL Server DATEADD(month,1,'2026-01-31') có quy tắc điều chỉnh về ngày hợp lệ cuối tháng. Oracle phép cộng month bằng ADD_MONTHS có semantics riêng và có thể chịu NLS_CALENDAR. Java Period cũng có quy tắc của API. Hãy test ngày 28/29/30/31.

### 17.3. Week numbering

ISO week, week-of-year theo locale và WEEK() của MySQL có nhiều mode. Test ngày gần đầu năm/cuối năm, đặc biệt khi 01/01 thuộc ISO week của năm trước hoặc tuần 1 của năm mới.

## 18. Kiểm thử biên khoảng thời gian

Với khoảng [start, end), hãy tạo fixture:

| ID | Timestamp | Kỳ vọng với [10:00, 11:00) |
|---|---|---|
| A | 09:59:59.999999 | Ngoài, trước start |
| B | 10:00:00.000000 | Trong, đúng start |
| C | 10:30:00.000000 | Trong |
| D | 10:59:59.999999 | Trong, trước end |
| E | 11:00:00.000000 | Ngoài, đúng end |
| F | 11:00:00.000001 | Ngoài, sau end |

Sau đó chạy cùng logic với precision cột thực tế. Nếu DBMS chỉ giữ millisecond, fixture cần kiểm tra round-trip và giá trị đã được lưu ra sao.

### 18.1. Hai ngày liền kề

Ngày A: [2026-10-03T00:00, 2026-10-04T00:00)  
Ngày B: [2026-10-04T00:00, 2026-10-05T00:00)

Event đúng 2026-10-04T00:00 chỉ thuộc ngày B. Tổng số event của A và B không bị đếm trùng.

### 18.2. Khoảng rỗng

Nếu start=end thì [start,end) là khoảng rỗng. Nếu end<start, input thường không hợp lệ.

Không để query vô tình diễn giải start=end thành một instant được bao gồm. Validate start<end nếu nghiệp vụ không cho phép khoảng rỗng.

### 18.3. Overlap

Hai khoảng [a,b) và [c,d) chồng lấn khi:

~~~text
a < d AND c < b
~~~

Nếu b=c, chúng chỉ liền kề và không chồng lấn.

### 18.4. Chứa và giao nhau

Khoảng [a,b) chứa instant t khi:

~~~text
a <= t AND t < b
~~~

Khoảng [a,b) chứa toàn bộ [c,d) khi c>=a và d<=b, với policy xử lý khoảng rỗng đã xác định.

Giao của hai khoảng:
- start = max(a,c)
- end = min(b,d)
- Có giao có độ dài dương nếu start<end.

## 19. SQL kiểm thử khoảng và overlap

Ví dụ bảng reservation:

~~~sql
CREATE TABLE reservation (
    id BIGINT PRIMARY KEY,
    starts_at TIMESTAMP NOT NULL,
    ends_at TIMESTAMP NOT NULL,
    CHECK (starts_at < ends_at)
);
~~~

Kiểm tra một lịch mới [new_start,new_end) có overlap với lịch đã có:

~~~sql
SELECT id
FROM reservation
WHERE starts_at < :new_end
  AND :new_start < ends_at;
~~~

Nếu query trả hàng, có khoảng chồng lấn.

### 19.1. Tránh lỗi dùng BETWEEN

Sai cho overlap:

~~~sql
WHERE starts_at BETWEEN :new_start AND :new_end
   OR ends_at BETWEEN :new_start AND :new_end
~~~

Biểu thức này bỏ sót trường hợp khoảng hiện có bao trọn khoảng mới. Công thức overlap tổng quát là hai bất đẳng thức strict ở trên.

### 19.2. Kiểm tra khi insert concurrent

Hai transaction có thể cùng kiểm tra không overlap rồi cùng INSERT hai khoảng chồng lấn. Chỉ chạy SELECT kiểm tra trước INSERT không bảo đảm constraint dưới concurrency.

Cần cơ chế bảo đảm:
- Constraint loại exclusion/range nếu DBMS hỗ trợ.
- Locking phù hợp.
- Serializable transaction hoặc predicate locking phù hợp.
- Một bảng khóa theo resource và transaction.
- Unique/constraint mô hình hóa được quy tắc.

### 19.3. PostgreSQL range types

PostgreSQL có range types như tstzrange và operator overlap &&:

~~~sql
SELECT *
FROM reservation
WHERE period && tstzrange(:start_at, :end_at, '[)');
~~~

Có thể dùng exclusion constraint với GiST để ngăn overlap theo resource. Đây là khả năng PostgreSQL-specific; DBMS khác cần giải pháp tương đương theo engine.

## 20. Kiểm thử lịch lặp và thời hạn

Không phải mọi “lặp mỗi ngày” đều là cộng 24 giờ.

### 20.1. Lịch theo giờ địa phương

Ví dụ cửa hàng mở cửa lúc 09:00 mỗi ngày tại America/New_York. Lịch nên lưu:
- Local time = 09:00.
- Zone ID = America/New_York.
- Recurrence = daily.
- Effective date range.
- Policy nếu giờ đó rơi vào gap/overlap.

Mỗi ngày, tính instant kế tiếp từ local date + local time + zone rules.

### 20.2. Job chạy mỗi 24 giờ

Nếu yêu cầu “chạy sau đúng 24 giờ kể từ lần trước”, đó là duration schedule, có thể dùng instant + Duration.ofHours(24).

Nếu yêu cầu “chạy lúc 09:00 theo giờ địa phương mỗi ngày”, đó là calendar schedule, dùng ZonedDateTime/local date + zone.

Hai yêu cầu khác nhau qua DST.

### 20.3. Hợp đồng có hiệu lực đến hết ngày

Không lưu end_at là 23:59:59.999. Lưu ngày hiệu lực cuối theo DATE hoặc chuyển thành exclusive boundary là đầu ngày kế tiếp:

~~~text
effective_from = 2026-10-01
effective_until_inclusive = 2026-10-31
query interval = [2026-10-01T00:00 zone,
                  2026-11-01T00:00 zone)
~~~

Tên cột phải làm rõ inclusive hay exclusive. Có thể lưu end_date_exclusive để giảm mơ hồ.

### 20.4. Thời hạn theo số ngày

“Trong vòng 30 ngày” có thể nghĩa:
- 30 × 24 giờ kể từ instant phát hành.
- 30 ngày lịch theo timezone nghiệp vụ.
- Bao gồm ngày phát hành và 29 ngày tiếp theo.
- Hết hạn vào đầu ngày thứ 31.
- Hết hạn cuối ngày địa phương.

Viết acceptance criteria trước khi chọn Duration, Period hoặc SQL INTERVAL.

## 21. Java/JDBC: kiểu bind và đọc

Dùng Java Time API:

| Java | Domain | JDBC mapping thường gặp |
|---|---|---|
| LocalDate | Ngày lịch | DATE |
| LocalTime | Giờ địa phương | TIME |
| LocalDateTime | Local timestamp không zone | TIMESTAMP |
| Instant | Thời điểm tuyệt đối | Thường chuyển qua UTC/OffsetDateTime hoặc driver-specific mapping |
| OffsetDateTime | Date-time có offset | TIMESTAMP WITH TIME ZONE/DATETIMEOFFSET theo driver |
| ZonedDateTime | Date-time + zone rules | Thường cần lưu zone ID riêng; không phải DB nào bảo toàn nguyên vẹn |
| Duration | Thời lượng tuyệt đối | Số đơn vị hoặc kiểu interval theo adapter |
| Period | Khoảng lịch | Số tháng/ngày hoặc interval theo DBMS |

### 21.1. Bind LocalDate

~~~java
ps.setObject(1, LocalDate.of(2026, 10, 3));
~~~

Đọc:

~~~java
LocalDate date = rs.getObject("business_date", LocalDate.class);
~~~

Driver phải hỗ trợ mapping JDBC 4.2 tương ứng.

### 21.2. Bind Instant

Không phải mọi driver map Instant trực tiếp như nhau. Một cách rõ ràng là chuyển sang OffsetDateTime UTC nếu driver/DBMS hỗ trợ:

~~~java
OffsetDateTime utc = instant.atOffset(ZoneOffset.UTC);
ps.setObject(1, utc);
~~~

Hoặc dùng timestamp/Calendar API theo driver và kiểu cột. Test round-trip bằng đúng driver/version, không giả định setTimestamp(Timestamp.from(instant)) luôn không phụ thuộc JVM/session timezone.

### 21.3. Tránh java.sql.Date/Time/ Timestamp khi code mới

Các lớp legacy có liên hệ với timezone/default JVM trong một số overload. Nếu dùng API cũ, chỉ rõ Calendar/UTC khi phù hợp và test môi trường. Ưu tiên java.time và JDBC 4.2 typed mapping khi driver hỗ trợ.

### 21.4. Không truyền timestamp qua String tùy tiện

Chuỗi 2026-10-03 09:00:00 có thể được parse theo session timezone, locale hoặc kiểu đích. Dùng typed bind và định dạng ISO có offset/UTC khi trao đổi qua text boundary.

## 22. Bộ test xác định bằng Clock

Ví dụ test service:

~~~java
@Test
void reportUsesBusinessDate() {
    Instant fixedInstant =
        Instant.parse("2026-10-03T02:30:00Z");

    Clock clock = Clock.fixed(fixedInstant, ZoneOffset.UTC);
    ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

    LocalDate businessDate = LocalDate.now(clock.withZone(zone));

    assertEquals(LocalDate.of(2026, 10, 3), businessDate);
}
~~~

Không cần sleep hoặc chờ đồng hồ thật chạm nửa đêm.

### 22.1. Test rollover

Chọn instant ngay trước và ngay sau nửa đêm địa phương:

~~~java
Instant before = Instant.parse("2026-10-02T16:59:59.999Z");
Instant after  = Instant.parse("2026-10-02T17:00:00Z");

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
~~~

Kỳ vọng:
- before thuộc ngày 02/10 theo giờ +07.
- after thuộc ngày 03/10 theo giờ +07.

### 22.2. Test tháng/năm

Đặt fixed clock ở:
- 31/01 23:59:59.999.
- 01/02 00:00:00.
- 28/02 năm thường.
- 29/02 năm nhuận.
- 31/12 23:59:59.
- 01/01 00:00:00.

Test business date, expiry, billing period và week number.

### 22.3. Test DST

Dùng ZoneId có DST và fixture gap/fold thực tế. Đừng chỉ test Asia/Ho_Chi_Minh, vì timezone này hiện không có DST theo quy tắc hiện hành; một bộ test chỉ dùng nó không kiểm tra được DST logic.

## 23. Test session timezone và connection pool

Mỗi connection có thể mang session state riêng:
- PostgreSQL TimeZone.
- MySQL time_zone và sql_mode.
- SQL Server language/dateformat, session settings và kiểu conversion.
- Oracle SESSIONTIMEZONE/NLS settings.
- SQLite không có session timezone kiểu tương đương, nhưng hàm localtime phụ thuộc host.

### 23.1. Connection pool

Một connection được trả về pool có thể giữ session setting nếu pool không reset. Ví dụ:
1. Request A đổi timezone session sang một zone.
2. Connection trở lại pool.
3. Request B mượn lại và query CURRENT_DATE.
4. Kết quả B bị ảnh hưởng bởi session của A.

Hãy:
- Thiết lập session state ở connection initialization hoặc transaction boundary.
- Reset state trước khi trả pool nếu cần.
- Tránh để request tự thay timezone tùy tiện.
- Test mượn lại cùng connection để phát hiện leakage.

### 23.2. Test nhiều session song song

Chạy hai session:
- A timezone UTC.
- B timezone America/New_York.
- Query cùng một instant có timezone.
- Xác nhận instant so sánh giống nhau nhưng display/local date có thể khác.

Không lấy output text đã format làm tiêu chí equality của instant.

## 24. Tạo test matrix cho biên ngày giờ

Một ma trận hữu ích:

| Nhóm | Fixture | Kết quả cần xác nhận |
|---|---|---|
| Midnight | Ngay trước 00:00 | Thuộc ngày trước |
| Midnight | Đúng 00:00 | Thuộc ngày mới |
| Day end | Gần end-exclusive | Vẫn thuộc khoảng |
| Day end | Đúng end | Ngoài khoảng |
| Month | 31/01 → 01/02 | Ngày/tháng đổi đúng |
| Leap | 28/02 năm nhuận | Ngày sau là 29/02 |
| Leap | 29/02 | Ngày sau là 01/03 |
| Century | 1900/2000/2100 | Quy tắc leap year |
| Year | 31/12 → 01/01 | Năm đổi đúng |
| ISO week | Cuối/đầu năm | ISO week-year đúng |
| DST gap | Local time không tồn tại | Theo gap policy |
| DST fold | Local time có hai offset | Theo overlap policy |
| DST day | Ngày ngắn/dài | Biên UTC cách nhau đúng |
| Precision | Fractional seconds | Round-trip theo policy |
| Zone | Cùng instant, khác zone | Instant bằng, local date có thể khác |
| Offset | Offset khác nhau cùng instant | So sánh cùng instant |
| Range | end=start | Khoảng rỗng hoặc invalid |
| Range | end=start của khoảng kế | Không overlap |
| Range | Bao trọn khoảng kia | Overlap được phát hiện |
| Session | Đổi timezone session | Conversion đúng contract |
| Pool | Reuse connection | Không rò session state |
| Clock | Fixed clock | Test lặp lại ổn định |

## 25. Fixture SQL cho biên nửa đêm

Ví dụ cột lưu timestamp UTC với precision microsecond:

~~~sql
CREATE TABLE event_fixture (
    id VARCHAR(20) PRIMARY KEY,
    occurred_at TIMESTAMP NOT NULL
);
~~~

Nạp dữ liệu theo representation UTC mà DBMS/driver đã thống nhất:

~~~sql
INSERT INTO event_fixture (id, occurred_at) VALUES
('before', '2026-10-02 23:59:59.999999'),
('start',  '2026-10-03 00:00:00.000000'),
('middle', '2026-10-03 12:00:00.000000'),
('end',    '2026-10-04 00:00:00.000000'),
('after',  '2026-10-04 00:00:00.000001');
~~~

Query:

~~~sql
SELECT id
FROM event_fixture
WHERE occurred_at >= :start_utc
  AND occurred_at < :end_utc
ORDER BY occurred_at;
~~~

Với start=2026-10-03 00:00:00 và end=2026-10-04 00:00:00, expected IDs: start, middle. Fixture này minh họa UTC day; nếu cột là PostgreSQL timestamptz hoặc SQL Server datetimeoffset, hãy bind typed instants thay vì dựa vào implicit conversion của chuỗi.

## 26. Kiểm thử ngày theo timezone trên năm DBMS

Một ngày địa phương nên được chuyển thành hai instant biên trong tầng ứng dụng hoặc bằng hàm timezone đã được xác định rõ. Sau đó query theo [start,end).

### 26.1. PostgreSQL

Nếu cột là timestamptz, bind hai OffsetDateTime/Instant đã được chuyển theo zone:

~~~sql
SELECT id
FROM event_log
WHERE occurred_at >= :start_instant
  AND occurred_at <  :end_instant;
~~~

Để kiểm thử session:
~~~sql
SET TIME ZONE 'UTC';
SHOW TimeZone;
~~~

Rồi lặp lại với một timezone khác. Result set theo instant không đổi nếu biên bind vẫn là cùng instant; cách hiển thị cột có thể đổi.

### 26.2. MySQL

Nếu cột TIMESTAMP, session timezone ảnh hưởng conversion. Kiểm tra:

~~~sql
SELECT @@session.time_zone, @@global.time_zone;
~~~

Có thể thiết lập session test rõ ràng và bind biên theo quy tắc driver. Nếu cột DATETIME được quy ước lưu UTC, giữ quy ước đó trong tất cả writer/reader vì kiểu không tự mang timezone.

### 26.3. SQL Server

Nếu cột datetimeoffset, bind offset-aware values. Nếu dùng datetime2 quy ước UTC, đảm bảo mọi ứng dụng ghi UTC. Với timezone chuyển đổi bằng AT TIME ZONE, kiểm tra tên Windows zone và DST handling của SQL Server version.

### 26.4. Oracle

Kiểm tra SESSIONTIMEZONE/DBTIMEZONE. Với TIMESTAMP WITH TIME ZONE, bind offset-aware values; với TIMESTAMP WITH LOCAL TIME ZONE, test cùng giá trị dưới các session timezone khác nhau để hiểu display behavior.

### 26.5. SQLite

Chọn INTEGER epoch hoặc ISO text UTC. Tính biên bằng ZoneId ở ứng dụng; không dựa vào host localtime cho timezone của tenant. Bind cùng representation/unit ở mọi query.

## 27. Tính toán khoảng thời gian và sargability

Một query kiểm tra ngày thường nên là:

~~~sql
WHERE occurred_at >= :start
  AND occurred_at < :end
~~~

Thay vì:

~~~sql
WHERE CAST(occurred_at AS DATE) = :d
~~~

Lý do:
- B-tree index trên occurred_at có thể được dùng cho range seek.
- Không phải tính hàm trên mọi row.
- Không phụ thuộc implicit timezone khi cast.
- Biên được tính một lần và có thể log/test.
- Dễ so sánh query plan giữa DBMS.

### 27.1. Không đổi timezone của cột ở mỗi hàng

Biểu thức như CONVERT_TZ(occurred_at,...) hoặc AT TIME ZONE trên cột có thể làm predicate khó sargable. Thường tốt hơn chuyển start/end về timezone của cột trước, rồi lọc trực tiếp.

### 27.2. Partition pruning

Nếu bảng partition theo ngày/tháng UTC, query theo ngày địa phương phải chuyển thành instant range trước khi lọc. Nếu bọc partition key trong hàm, optimizer có thể không prune được partition như mong muốn.

Test EXPLAIN/actual plan với ngày bình thường, ngày DST và khoảng nhiều partition.

## 28. Kiểm thử thời hạn và khoảng liền kề

Giả sử một coupon có hiệu lực từ đầu ngày 01/10 đến hết ngày 31/10 tại timezone cửa hàng.

Cách biểu diễn dễ test:
- start inclusive = đầu ngày 01/10.
- end exclusive = đầu ngày 01/11.

Kiểm thử:
- 30/09 23:59:59.999... → không hiệu lực.
- 01/10 00:00 → hiệu lực.
- 31/10 23:59:59.999... → hiệu lực.
- 01/11 00:00 → hết hiệu lực.

Không lưu end là 31/10 23:59:59.999999999. Không phụ thuộc precision kiểu cột.

### 28.1. Grace period

“Thanh toán trong vòng 15 phút” nên được định nghĩa là:
- deadline = issued_at + 15 phút duration; hoặc
- hết hạn tại mốc calendar cụ thể.

Test:
- deadline - 1 microsecond.
- đúng deadline.
- deadline + 1 microsecond.

Nếu predicate là valid khi now < deadline, đúng deadline đã hết hiệu lực. Nếu valid khi now <= deadline, đúng deadline vẫn hợp lệ. Viết rõ inclusive/exclusive.

### 28.2. Retention

“Xóa dữ liệu cũ hơn 90 ngày” thường là:

~~~sql
DELETE FROM event_log
WHERE occurred_at < :cutoff_instant;
~~~

Nhưng 90 ngày có thể là 90×24 giờ hoặc 90 ngày lịch theo zone. Nếu retention theo calendar day, tính cutoff theo timezone nghiệp vụ. Nếu theo duration, dùng instant trừ Duration.

## 29. Test lịch làm việc và ngày nghỉ

Ngày làm việc không phải mọi ngày lịch:
- Cuối tuần theo quốc gia.
- Ngày nghỉ lễ theo lịch địa phương.
- Ngày nghỉ bù.
- Giờ mở cửa thay đổi theo mùa.
- Ca qua nửa đêm.
- Ngày làm việc có DST transition.

Không suy ra business day chỉ từ DAYOFWEEK hoặc ngày thứ Hai–thứ Sáu nếu nghiệp vụ có holiday calendar.

Nên lưu lịch ngày nghỉ/working calendar theo jurisdiction/organization và test:
- Ngày trước holiday.
- Holiday.
- Ngày nghỉ bù.
- Cuối tuần.
- Năm đổi.
- Calendar version thay đổi.

## 30. Kiểm thử ngày giờ trong dữ liệu phân tán

Trong hệ thống nhiều service:
- Event producer có clock lệch.
- Message có event_time và received_at khác nhau.
- Consumer retry sau nhiều phút.
- DB insert time có thể sau event time.
- Event đến không đúng thứ tự.
- Timestamp chỉ có millisecond ở một service nhưng nanosecond ở service khác.

Phân biệt:
- occurred_at: thời điểm nghiệp vụ xảy ra theo nguồn.
- received_at: thời điểm hệ thống nhận.
- processed_at: thời điểm xử lý.
- committed_at: thời điểm commit nếu hệ có cơ chế ghi nhận.

Không dùng một cột created_at cho mọi ý nghĩa.

### 30.1. Clock skew

Nếu service A nhanh hơn service B 3 giây, timestamp từ hai service có thể không phản ánh thứ tự nhân quả. Nếu cần ordering chính xác, dùng sequence/offset/event version hoặc causal metadata phù hợp; không chỉ sort timestamp.

### 30.2. Monotonic clock và wall clock

Wall clock có thể bị chỉnh bởi NTP. Đo thời lượng xử lý trong process nên dùng monotonic clock (ví dụ System.nanoTime trong Java), không trừ hai Instant nếu mục tiêu là đo elapsed time ngắn và cần tránh clock adjustment.

## 31. Kiểm thử timezone database và môi trường

Timezone rules không chỉ nằm trong code:
- JVM tzdb.
- OS zoneinfo.
- MySQL timezone tables.
- SQL Server Windows timezone registry/data.
- Oracle timezone files.
- Container image và package update.

Ghi nhận version/môi trường trong test logs:
- DBMS product/version.
- JDBC driver version.
- JVM version.
- OS/container image.
- JVM default timezone.
- DB session timezone.
- DB timezone file/tzdb version nếu truy cập được.

### 31.1. Không pin offset thay zone ID trong lịch tương lai

Nếu lưu schedule cho ngày 2027-04-01 tại vùng có luật DST, offset hiện tại có thể không đúng offset vào ngày đó. Lưu zone ID và tính offset cho ngày mục tiêu bằng timezone rules cập nhật.

### 31.2. Chính sách khi luật đổi sau khi schedule đã tạo

Có hai kiểu:
- **Floating local schedule:** luôn chạy lúc 09:00 theo luật mới của vùng.
- **Fixed instant schedule:** đã xác định instant một lần và không đổi dù luật timezone thay đổi.

Cần chọn theo nghiệp vụ. Vé máy bay, cuộc họp và lịch thanh toán có thể có yêu cầu khác nhau.

## 32. Bộ test dữ liệu biên mở rộng

Nên có các nhóm fixture sau:

**Ngày lịch**
- Ngày đầu/cuối tháng.
- 28/02, 29/02, 01/03.
- Năm chia hết cho 100 và 400.
- 31/12 và 01/01.
- Tuần ISO giao năm.
- Ngày lịch bị bỏ qua trong lịch sử timezone nếu hỗ trợ vùng đó.

**Thời điểm**
- Một đơn vị precision trước start.
- Đúng start.
- Ngay trước end.
- Đúng end.
- Ngay sau end.
- Cùng instant với offset khác.
- Fractional seconds vượt precision đích.

**Timezone**
- UTC.
- Zone không DST.
- Zone DST gap.
- Zone DST fold.
- Zone có thay đổi offset không tròn một giờ.
- Session timezone khác app timezone.

**Khoảng**
- start<end.
- start=end.
- start>end.
- Hai khoảng liền kề.
- Hai khoảng overlap một phần.
- Một khoảng chứa khoảng kia.
- Khoảng không giao nhau.
- Biên inclusive/exclusive.

**Ứng dụng**
- Fixed clock.
- Clock ngay trước/sau midnight.
- Connection pool reuse.
- Driver bind/read.
- Retry sau timeout.
- DST tzdb upgrade.

## 33. Những lỗi thường gặp và cách xử lý

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Coi DATE là UTC midnight | Ngày lịch đổi khi chuyển zone | Giữ DATE/LocalDate |
| Coi LocalDateTime là instant | Không xác định được thời điểm | Gắn zone/offset theo contract |
| Lưu offset thay zone ID cho lịch lặp | Sai khi DST/luật đổi | Lưu IANA zone ID |
| Dùng timezone mặc định máy | Dev/CI/prod khác ngày | ZoneId cấu hình rõ |
| Lọc ngày bằng BETWEEN end-of-day | Bỏ sót precision cao hoặc đếm trùng midnight | [start,next_start) |
| Dùng 23:59:59.999999 | Phụ thuộc precision cột | Exclusive next boundary |
| Dùng DATE(column)=date | Có thể mất index và phụ thuộc session | Range predicate |
| Cộng 24 giờ để sang ngày địa phương | Sai qua DST | Calendar day + zone |
| Cộng một ngày lịch cho deadline 24h | Thời lượng có thể 23/25h | Duration |
| Giả định DST luôn một giờ | Sai với một số vùng | ZoneRules/tzdb |
| Không định nghĩa gap policy | Job bị bỏ qua hoặc dời ngoài ý muốn | Gap resolution policy |
| Không định nghĩa fold policy | Job chạy một hoặc hai lần ngoài ý muốn | Offset/first/second/both policy |
| Test chỉ ở Việt Nam | Không kiểm tra DST | Thêm zone có DST |
| Dùng systemDefault() | Test phụ thuộc host | Inject ZoneId/Clock |
| Gọi Instant.now() rải rác | Test flaky | Inject Clock |
| So timestamp text giữa zone | Cùng instant nhưng text khác | So Instant |
| Không kiểm tra session timezone | Conversion/display thay đổi | Set/assert session state |
| Nhầm DB timezone với session timezone | Sai ngày/giờ | Kiểm tra cả hai |
| Giả định DATETIME có timezone | Không tự chuyển đổi | Contract UTC/local rõ |
| Giả định TIMESTAMPTZ giữ zone ID | Mất tên vùng nguồn | Lưu zone ID riêng |
| Oracle DATE chỉ có ngày | Bỏ sót giờ | Dùng DATE semantics đúng |
| SQLite có TIMESTAMP native | Mapping mơ hồ | Chọn TEXT/INTEGER/REAL và unit |
| Trộn epoch seconds/milliseconds | Sai lệch ×1000 | Đặt tên cột/unit rõ |
| Không kiểm tra fractional seconds | Round-trip sai | Test precision/rounding |
| Test đúng millisecond nhưng cột microsecond | Bỏ sót biên | Fixture ở precision đích |
| Dùng BETWEEN cho overlap | Bỏ sót khoảng bao trọn | Công thức a<d AND c<b |
| SELECT kiểm tra overlap rồi INSERT | Race condition | Constraint/locking/serializable |
| Không validate start<end | Khoảng đảo/rỗng bất ngờ | Check constraint/validation |
| Dùng locale week thay ISO week | Sai báo cáo tuần | Chốt week convention |
| Dùng 90 ngày thay 3 tháng | Sai retention/business period | Duration vs calendar policy |
| Trộn event time với received time | Sai thứ tự/báo cáo | Cột riêng, semantics rõ |
| Dùng wall clock đo elapsed time | Sai khi clock chỉnh | Monotonic clock |
| Không cập nhật timezone tables | Named conversion trả NULL/sai | Quản lý tzdb/version |
| Dùng Windows zone như IANA ID | Không map đúng | Mapping có kiểm soát |
| Không test connection pool | Session state rò | Reset/init session |
| Dùng current timestamp trong test equality | Flaky | Bind fixed fixture |
| Gửi event trước COMMIT | Event có thể nói về transaction rollback | Outbox/after-commit |
| Dùng timestamp làm optimistic version duy nhất | Collision precision | Integer version |

## 34. Bài tập thực hành có đáp án

### Bài 1 — DATE hay TIMESTAMP?

Ngày sinh 1990-05-12 có nên lưu dưới dạng instant UTC không?

<details>
<summary>Đáp án</summary>

Không. Ngày sinh là ngày lịch, dùng DATE/LocalDate. Không tự gắn midnight UTC nếu nghiệp vụ không yêu cầu instant.

</details>

### Bài 2 — LocalDateTime

Giá trị 2026-10-03 09:00 có xác định một instant duy nhất không?

<details>
<summary>Đáp án</summary>

Không. Cần timezone hoặc offset để ánh xạ local date-time thành instant.

</details>

### Bài 3 — Offset và zone

+07:00 có thay thế Asia/Ho_Chi_Minh trong lịch lặp nhiều năm không?

<details>
<summary>Đáp án</summary>

Không. Offset chỉ là độ lệch tại một thời điểm; zone ID chứa quy tắc lịch sử/tương lai.

</details>

### Bài 4 — Khoảng nửa mở

Khoảng [10:00,11:00) có bao gồm đúng 11:00 không?

<details>
<summary>Đáp án</summary>

Không. Start inclusive, end exclusive.

</details>

### Bài 5 — BETWEEN

BETWEEN thường bao gồm hai biên hay chỉ biên đầu?

<details>
<summary>Đáp án</summary>

Bao gồm cả hai biên. Vì vậy không dùng end-of-day ước lượng làm biên cuối khi lọc ngày.

</details>

### Bài 6 — Hai ngày liền kề

Event đúng 00:00 ngày 04/10 thuộc khoảng ngày 03/10 [03/10 00:00,04/10 00:00) không?

<details>
<summary>Đáp án</summary>

Không. Nó thuộc khoảng ngày 04/10 bắt đầu tại đúng instant đó.

</details>

### Bài 7 — End-of-day

Vì sao không nên dùng 23:59:59.999999 làm end?

<details>
<summary>Đáp án</summary>

Precision cột/driver có thể cao hơn hoặc khác; có thể bỏ sót giá trị sát cuối ngày. Dùng đầu ngày kế tiếp exclusive.

</details>

### Bài 8 — Overlap

Hai khoảng [a,b) và [c,d) overlap khi nào?

<details>
<summary>Đáp án</summary>

Khi a<d và c<b. Nếu b=c, chúng liền kề, không overlap.

</details>

### Bài 9 — Khoảng rỗng

[start,start) có chứa instant start không?

<details>
<summary>Đáp án</summary>

Không. Đây là khoảng rỗng theo quy ước nửa mở.

</details>

### Bài 10 — Ngày nhuận

Năm 2000 có nhuận không? Năm 1900 có nhuận không?

<details>
<summary>Đáp án</summary>

2000 có vì chia hết cho 400; 1900 không vì chia hết cho 100 nhưng không chia hết cho 400.

</details>

### Bài 11 — Năm 2100

Ngày 29/02/2100 có hợp lệ theo lịch Gregorian không?

<details>
<summary>Đáp án</summary>

Không. 2100 chia hết cho 100 nhưng không chia hết cho 400.

</details>

### Bài 12 — Cộng tháng

2025-01-31 + 1 month có luôn cho cùng kết quả trong Java, Oracle và SQL Server không?

<details>
<summary>Đáp án</summary>

Không mặc định. Quy tắc điều chỉnh cuối tháng phụ thuộc API/DBMS; phải định nghĩa policy và test.

</details>

### Bài 13 — Calendar day vs duration

Cộng một calendar day khác cộng 24 giờ ở điểm nào?

<details>
<summary>Đáp án</summary>

Calendar day theo ngày địa phương và zone rules; 24 giờ là duration tuyệt đối. Qua DST, hai kết quả có thể khác giờ địa phương.

</details>

### Bài 14 — DST gap

Local time 02:30 nằm trong gap. Có bao nhiêu offset hợp lệ?

<details>
<summary>Đáp án</summary>

Không có offset hợp lệ. Phải áp dụng policy bỏ qua, dời giờ hoặc xử lý khác.

</details>

### Bài 15 — DST fold

Local time 01:30 nằm trong overlap có thể có bao nhiêu offset hợp lệ?

<details>
<summary>Đáp án</summary>

Có thể có hai offset hợp lệ, tương ứng hai instant khác nhau.

</details>

### Bài 16 — Ngày DST

Một ngày địa phương có thể dài bao nhiêu giờ?

<details>
<summary>Đáp án</summary>

Thường có thể là 23, 24 hoặc 25 giờ trong các vùng có DST một giờ; một số vùng có thay đổi khác nên không hardcode các giá trị này cho toàn cầu.

</details>

### Bài 17 — Java ZoneId

Để tính đầu ngày tại New York, dùng LocalDate.atStartOfDay(ZoneId) hay tự ghép chuỗi 00:00Z?

<details>
<summary>Đáp án</summary>

Dùng atStartOfDay(zone) rồi chuyển Instant. Nó áp dụng zone rules và xử lý nửa đêm không hợp lệ theo API.

</details>

### Bài 18 — Java Clock

Vì sao inject Clock tốt hơn gọi Instant.now() trực tiếp trong business service?

<details>
<summary>Đáp án</summary>

Có thể dùng Clock.fixed để test xác định, không phụ thuộc thời gian thật hoặc timezone mặc định.

</details>

### Bài 19 — PostgreSQL timestamptz

TIMESTAMPTZ có giữ nguyên zone ID Asia/Ho_Chi_Minh nguồn không?

<details>
<summary>Đáp án</summary>

Không. Nó biểu diễn instant; cách hiển thị phụ thuộc session timezone. Nếu cần zone ID, lưu riêng.

</details>

### Bài 20 — PostgreSQL session

Cùng một timestamptz hiển thị khác nhau sau SET TIME ZONE. Instant có đổi không?

<details>
<summary>Đáp án</summary>

Không. Chỉ representation/display theo session timezone thay đổi.

</details>

### Bài 21 — MySQL DATETIME

DATETIME có tự chuyển đổi theo session timezone như TIMESTAMP không?

<details>
<summary>Đáp án</summary>

Không theo cùng semantics. DATETIME lưu local date-time; TIMESTAMP có conversion theo timezone session.

</details>

### Bài 22 — MySQL named zone

CONVERT_TZ trả NULL với tên zone hợp lệ. Một nguyên nhân cần kiểm tra?

<details>
<summary>Đáp án</summary>

Timezone tables của MySQL có thể chưa được nạp/cập nhật hoặc tên zone không được nhận diện trong môi trường.

</details>

### Bài 23 — SQL Server

DATETIME2 có lưu zone ID không?

<details>
<summary>Đáp án</summary>

Không. DATETIMEOFFSET giữ offset nhưng cũng không lưu tên vùng timezone như IANA ID.

</details>

### Bài 24 — Oracle DATE

Oracle DATE có lưu giờ/phút/giây không?

<details>
<summary>Đáp án</summary>

Có. Oracle DATE không phải date-only.

</details>

### Bài 25 — SQLite

SQLite có storage class TIMESTAMP chuyên biệt không?

<details>
<summary>Đáp án</summary>

Không. Thường lưu TEXT, REAL hoặc INTEGER theo contract ứng dụng.

</details>

### Bài 26 — Precision

Cột chỉ lưu microsecond nhận Java Instant có nanosecond. Có cần test round-trip không?

<details>
<summary>Đáp án</summary>

Có. Phải xác định driver/DBMS truncate hay round và chuẩn hóa equality theo precision đích.

</details>

### Bài 27 — Sargability

Vì sao WHERE DATE(created_at)=:d có thể kém hơn range predicate?

<details>
<summary>Đáp án</summary>

Hàm trên cột có thể làm index range seek khó được dùng và có thể phụ thuộc timezone/cast. Tính start/end rồi lọc trực tiếp.

</details>

### Bài 28 — Session timezone

Global timezone đúng có đảm bảo mọi pooled connection có session timezone đúng không?

<details>
<summary>Đáp án</summary>

Không. Session có thể được thiết lập riêng và connection pool có thể giữ state. Cần initialize/reset và test reuse.

</details>

### Bài 29 — ISO week

Vì sao ngày 01/01 có thể thuộc ISO week-year trước đó?

<details>
<summary>Đáp án</summary>

ISO week 1 là tuần chứa thứ Năm đầu tiên; các ngày đầu năm có thể vẫn thuộc tuần cuối của ISO week-year trước.

</details>

### Bài 30 — 90 ngày

“90 ngày retention” có luôn bằng “3 tháng lịch” không?

<details>
<summary>Đáp án</summary>

Không. 90 ngày là duration/calendar-day count theo contract; 3 tháng có độ dài khác nhau.

</details>

### Bài 31 — Event time

occurred_at khác received_at thế nào?

<details>
<summary>Đáp án</summary>

occurred_at là lúc sự kiện nghiệp vụ xảy ra theo nguồn; received_at là lúc hệ thống nhận nó. Hai giá trị khác nhau khi có mạng trễ/retry.

</details>

### Bài 32 — Clock skew

Vì sao không thể luôn dùng timestamp từ hai service để xác định thứ tự nhân quả?

<details>
<summary>Đáp án</summary>

Clock hai máy có thể lệch hoặc bị điều chỉnh. Cần version/sequence/causal metadata nếu thứ tự nhân quả quan trọng.

</details>

### Bài 33 — Monotonic clock

Đo thời lượng xử lý trong Java nên ưu tiên API nào?

<details>
<summary>Đáp án</summary>

System.nanoTime() cho elapsed duration trong process; Instant/wall clock dùng cho timestamp nghiệp vụ.

</details>

### Bài 34 — Hợp đồng đến hết ngày

Coupon có hiệu lực hết ngày 31/10. Biên exclusive nên là gì?

<details>
<summary>Đáp án</summary>

Đầu ngày 01/11 theo timezone nghiệp vụ, chuyển sang instant rồi dùng created_at < end.

</details>

### Bài 35 — Grace period

Nếu hợp đồng còn hiệu lực khi now < deadline, tại đúng deadline còn hiệu lực không?

<details>
<summary>Đáp án</summary>

Không. Điều kiện strict less-than loại đúng instant deadline.

</details>

### Bài 36 — Oracle timezone

Nên kiểm tra hai giá trị nào để hiểu DB timezone và session timezone?

<details>
<summary>Đáp án</summary>

DBTIMEZONE và SESSIONTIMEZONE.

</details>

### Bài 37 — SQL Server timezone name

AT TIME ZONE của SQL Server thường dùng hệ tên zone nào?

<details>
<summary>Đáp án</summary>

Windows timezone names; cần mapping với IANA IDs nếu ứng dụng dùng Java ZoneId.

</details>

### Bài 38 — Lịch lặp

Một cửa hàng chạy 09:00 mỗi ngày theo giờ địa phương. Nên cộng Duration 24 giờ hay tính ngày kế tiếp theo ZoneId?

<details>
<summary>Đáp án</summary>

Tính ngày lịch kế tiếp theo ZoneId. Cộng 24 giờ có thể làm giờ địa phương lệch qua DST.

</details>

### Bài 39 — Fixed instant schedule

Một job phải chạy chính xác sau 24 giờ từ lần trước. Nên dùng Period hay Duration?

<details>
<summary>Đáp án</summary>

Duration 24 giờ trên instant.

</details>

### Bài 40 — Test chỉ ở UTC

Test chỉ chạy UTC có phát hiện lỗi DST ở New York không?

<details>
<summary>Đáp án</summary>

Không. Cần fixture zone có DST gap/fold.

</details>

### Bài 41 — Query overlap

Điều kiện starts_at BETWEEN new_start AND new_end OR ends_at BETWEEN ... có bỏ sót trường hợp nào?

<details>
<summary>Đáp án</summary>

Bỏ sót khoảng hiện có bao trọn khoảng mới. Dùng starts_at < new_end AND new_start < ends_at.

</details>

### Bài 42 — Concurrent reservation

Hai transaction cùng SELECT không có overlap rồi INSERT có thể tạo lịch chồng lấn không?

<details>
<summary>Đáp án</summary>

Có. Cần constraint/locking/transaction isolation phù hợp để bảo vệ invariant dưới concurrency.

</details>

### Bài 43 — Precision cuối ngày

Cột microsecond có thể nhận timestamp nanosecond mà không mất thông tin không?

<details>
<summary>Đáp án</summary>

Không. Phải làm tròn/cắt theo precision cột hoặc lưu raw source riêng.

</details>

### Bài 44 — Timezone update

Một chính phủ đổi luật DST cho năm sau. Ứng dụng lịch lặp nên dùng gì?

<details>
<summary>Đáp án</summary>

Lưu zone ID và recurrence rule, cập nhật tzdb theo chính sách. Phân biệt floating local schedule với fixed instant schedule.

</details>

### Bài 45 — Test database current time

Vì sao equality giữa hai lần gọi CURRENT_TIMESTAMP có thể flaky?

<details>
<summary>Đáp án</summary>

Thời điểm đánh giá/precision/transaction semantics có thể khác. Dùng fixed bound values hoặc assert trong tolerance có định nghĩa.

</details>

### Bài 46 — Connection pool

Một request đổi session timezone rồi trả connection về pool mà không reset có thể gây gì?

<details>
<summary>Đáp án</summary>

Request tiếp theo có thể nhận lại connection với timezone cũ và query ra ngày/giờ khác kỳ vọng.

</details>

### Bài 47 — UTC storage

Nếu cột DATETIME được quy ước chứa UTC, DBMS có tự enforce UTC không?

<details>
<summary>Đáp án</summary>

Không. DATETIME không mang timezone; tất cả writer/reader phải tuân thủ contract hoặc dùng kiểu/constraint/adapter phù hợp.

</details>

### Bài 48 — Tổng hợp

Thiết kế test cho báo cáo ngày địa phương của cửa hàng ở New York, cột event là instant UTC, database có index trên occurred_at.

<details>
<summary>Đáp án</summary>

1. Chọn ZoneId America/New_York và ngày business date.
2. Tính start = date.atStartOfDay(zone).toInstant() và end = date.plusDays(1).atStartOfDay(zone).toInstant().
3. Bind hai instant vào query occurred_at >= start AND occurred_at < end.
4. Tạo fixtures ngay trước start, đúng start, ngay trước end, đúng end.
5. Chọn thêm ngày DST gap/fold và xác nhận độ dài khoảng UTC có thể là 23/25 giờ.
6. Test trên session timezone UTC và một zone khác.
7. Xác nhận index range seek/partition pruning bằng EXPLAIN.
8. Dùng fixed Clock cho business logic và kiểm thử JDBC round-trip precision.

</details>

## 35. Checklist trước khi phát hành tính năng ngày giờ

- [ ] Đã xác định dữ liệu là DATE, local time, instant hay schedule có zone.
- [ ] Đã xác định timezone có thẩm quyền cho từng nghiệp vụ.
- [ ] Đã lưu zone ID khi lịch phụ thuộc luật timezone.
- [ ] Đã chốt semantics inclusive/exclusive của deadline và khoảng.
- [ ] Đã dùng [start,end) cho truy vấn khoảng phù hợp.
- [ ] Đã test đúng start, ngay trước end, đúng end và ngay sau end.
- [ ] Đã test tháng cuối, năm nhuận, cuối năm và ISO week.
- [ ] Đã test DST gap/fold bằng zone có DST.
- [ ] Đã test ngày địa phương dài/ngắn hơn 24 giờ.
- [ ] Đã kiểm tra precision và rounding qua JDBC.
- [ ] Đã kiểm tra DB timezone và session timezone.
- [ ] Đã kiểm tra timezone tables/tzdb version.
- [ ] Đã inject Clock trong business logic.
- [ ] Đã test connection pool không rò session state.
- [ ] Đã bind typed parameters, không parse chuỗi theo locale ngầm.
- [ ] Đã dùng range predicate để tận dụng index khi phù hợp.
- [ ] Đã test overlap/concurrency nếu có reservation/scheduling.
- [ ] Đã phân biệt event time, received time và processing time.
- [ ] Đã xác định retry/idempotency cho job chạy qua mốc thời gian.
- [ ] Đã chạy integration tests trên đúng DBMS/driver/runtime production.

## 36. Tổng kết cần ghi nhớ

1. **DATE là ngày lịch; LocalDateTime không tự là instant; Instant là thời điểm tuyệt đối.**
2. **Offset không phải zone ID.** Lịch lặp cần timezone rules, không chỉ +07:00.
3. Hãy xác định timezone nghiệp vụ thay vì dựa vào timezone mặc định của JVM, OS hoặc DB session.
4. Khoảng **[start,end)** giúp lọc ngày, tháng, tuần và các khoảng liền kề không đếm trùng.
5. BETWEEN thường bao gồm cả hai biên; không dùng 23:59:59.999 làm end-of-day portable.
6. Tính hai đầu ngày độc lập theo ZoneId; ngày DST có thể dài/ngắn khác 24 giờ.
7. DST gap không có local time hợp lệ; DST fold có thể có hai offset. Lịch phải có policy rõ.
8. Cộng calendar day khác cộng Duration 24 giờ.
9. Ngày nhuận theo quy tắc Gregorian; cần test cả năm thế kỷ như 1900, 2000, 2100.
10. Cộng tháng ở ngày cuối tháng có semantics riêng giữa Java và DBMS.
11. ISO week-year có thể khác calendar year ở đầu/cuối năm.
12. PostgreSQL timestamptz lưu instant và hiển thị theo session; không giữ zone ID nguồn.
13. MySQL TIMESTAMP có conversion theo session timezone; DATETIME không mang timezone.
14. SQL Server datetime2 không có timezone; datetimeoffset có offset nhưng không giữ zone ID.
15. Oracle DATE có cả thành phần giờ; TIMESTAMP WITH LOCAL TIME ZONE hiển thị theo session.
16. SQLite cần contract rõ cho TEXT/INTEGER/REAL và đơn vị epoch.
17. Timestamp precision khác nhau; test rounding/truncation bằng driver thực.
18. Dùng Clock.fixed và Java ZoneId/ZoneRules để test xác định.
19. Query theo range trên cột thay vì bọc cột bằng DATE()/CAST() nếu cần index.
20. Kiểm tra session timezone, connection pool, timezone tables và tzdb/OS updates.
21. Phân biệt occurred_at, received_at, processed_at và commit time.
22. Kiểm thử overlap và concurrency bằng constraint/locking, không chỉ SELECT trước INSERT.
23. Một test chỉ chạy UTC hoặc Asia/Ho_Chi_Minh không đủ kiểm tra DST; cần zone có gap/fold.
24. Hãy hỏi: **“Giá trị này là ngày lịch, giờ địa phương hay instant; biên nào được bao gồm; timezone và precision nào quyết định kết quả?”**

### Tài liệu chính thức nên tham khảo

- **Java Documentation:** java.time; Instant; LocalDate; LocalDateTime; ZonedDateTime; ZoneRules; Clock; Duration; Period; JDBC 4.2 temporal mappings.
- **PostgreSQL Documentation:** Date/Time Types; Date/Time Functions and Operators; Time Zones; Date/Time Input and Output; Range Types.
- **MySQL Reference Manual:** Date and Time Data Types; Time Zone Support; Date and Time Functions; Fractional Seconds; Server System Variables.
- **Microsoft Learn — SQL Server:** Date and Time Data Types; AT TIME ZONE; Date and Time Functions; datetime2; datetimeoffset; SET DATEFIRST/DATEFORMAT.
- **Oracle Database SQL Language Reference:** Datetime Data Types and Time Zone Support; Datetime Expressions; CURRENT_DATE; CURRENT_TIMESTAMP; DBTIMEZONE; SESSIONTIMEZONE; Interval Types.
- **SQLite Documentation:** Date And Time Functions; Datatypes; unixepoch; datetime modifiers; Compile-Time Options.
- **IANA Time Zone Database:** Zone rules and release notes for changes in civil time.
- **JDBC Driver Documentation:** Temporal type mappings, Calendar handling, precision, session initialization and timezone connection properties.

**Thông điệp cuối cùng:** Kiểm thử ngày giờ phải bắt đầu từ ý nghĩa của dữ liệu và quy tắc biên. Hãy dùng instant cho thời điểm tuyệt đối, zone ID cho lịch địa phương, khoảng nửa mở cho truy vấn, fixture cố định cho test và kiểm tra đúng precision/session timezone của DBMS. Khi các mốc trước, đúng và sau biên đều cho kết quả đã định nghĩa, ứng dụng mới đáng tin cậy ở nửa đêm, cuối tháng và lúc đồng hồ đổi giờ.
