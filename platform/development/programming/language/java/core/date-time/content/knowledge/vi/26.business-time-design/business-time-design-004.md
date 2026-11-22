# Xác định thế nào là hôm nay theo múi giờ nghiệp vụ

## 1. “Hôm nay” cần cả thời điểm và múi giờ

Một `Instant` là thời điểm trên trục thời gian. Muốn trả lời “hôm nay là ngày nào?”, phải nhìn thời điểm đó trong một múi giờ cụ thể:

```text
Thời điểm tham chiếu + múi giờ nghiệp vụ → ngày lịch nghiệp vụ
```

Tại thời điểm giả lập `2024-01-01T00:30Z`:

| Múi giờ dùng để xác định ngày | Ngày nhận được |
| --- | --- |
| `Asia/Ho_Chi_Minh` | `2024-01-01` |
| `America/Los_Angeles` | `2023-12-31` |

Cả hai đều đúng với câu hỏi riêng của mình. Không có một “ngày hôm nay” toàn cầu độc lập với múi giờ.

`LocalDate` biểu diễn ngày nhưng không tự lưu múi giờ đã dùng để tạo nó. Vì thế, khi một hàm trả `LocalDate today`, hợp đồng của hàm cần nói rõ đó là ngày theo lịch nào và múi giờ nào.

Bài này dùng ngày lịch ISO theo múi giờ nghiệp vụ. “Ngày làm việc”, lịch nghỉ lễ hoặc kỳ chốt bắt đầu lúc 04:00 là các quy tắc bổ sung, không tự có trong `LocalDate.now`.

## 2. Chọn múi giờ theo người sở hữu quy tắc

Múi giờ của máy chủ, người dùng và tổ chức có thể khác nhau. Cần chọn theo mục đích:

| Nhu cầu | Múi giờ nên xuất phát từ đâu? |
| --- | --- |
| Báo cáo ngày của một tổ chức | Cấu hình múi giờ được tổ chức dùng cho báo cáo |
| Hạn nộp hồ sơ tại một cơ sở | Múi giờ của cơ sở/quy định xử lý hồ sơ |
| Trang cá nhân hiển thị ngày địa phương | Tùy chọn múi giờ của người dùng |
| Hệ thống nhiều tổ chức | Cấu hình của tổ chức gắn với dữ liệu đang xử lý |
| Xử lý cùng một sự kiện ở nhiều vùng | Truyền rõ vùng theo từng ngữ cảnh, giữ nguyên thời điểm sự kiện |

Máy chủ đặt tại đâu không tự quyết định lịch nghiệp vụ. Chuyển ứng dụng từ máy cá nhân sang máy chủ UTC không nên làm hạn “trong hôm nay” đổi nghĩa ngoài ý muốn.

Cũng không tự lấy múi giờ trình duyệt để thay quy tắc của tổ chức. Một người dùng đi công tác vẫn có thể phải tuân thủ ngày chốt của cơ sở ở nơi khác. Ngược lại, một chức năng cá nhân có thể chủ đích theo múi giờ do người dùng chọn.

Nên cấu hình bằng tên vùng như `Asia/Ho_Chi_Minh`, `Europe/Paris` khi quy tắc gắn với địa phương. Một offset như `+07:00` là độ lệch cố định, không đại diện đầy đủ cho mọi quy tắc thay đổi theo thời gian của một vùng. `ZoneId` liên kết tới các quy tắc chuyển đổi; xem [ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html).

## 3. Các cách gọi now có ý nghĩa khác nhau

| Cách gọi | Nguồn thời điểm | Múi giờ dùng để suy ra ngày |
| --- | --- | --- |
| `LocalDate.now()` | Đồng hồ hệ thống | Múi giờ mặc định JVM |
| `LocalDate.now(zone)` | Đồng hồ hệ thống | `zone` được truyền |
| `LocalDate.now(clock)` | `clock` được truyền | Múi giờ chứa trong `clock` |
| `LocalDate.ofInstant(instant, zone)` | Thời điểm được truyền rõ | `zone` được truyền |

`LocalDate.now(zone)` làm rõ múi giờ, nhưng vẫn đọc đồng hồ thực. Khi kiểm thử ranh giới nửa đêm, cách này khó điều khiển nếu được gọi trực tiếp trong lớp nghiệp vụ.

Truyền `Clock` cho phép thay nguồn thời điểm bằng `Clock.fixed` trong kiểm thử. Có hai thiết kế phù hợp:

- Clock của dịch vụ đã mang đúng múi giờ nghiệp vụ, rồi dùng `LocalDate.now(clock)`.
- Clock chỉ là nguồn thời điểm; dịch vụ nhận thêm `ZoneId` và dùng `LocalDate.ofInstant(clock.instant(), businessZone)`.

Chương trình trong bài chọn cách thứ hai: `businessZone` là nơi quyết định ngày nghiệp vụ, còn `Clock` cung cấp thời điểm. Nó không phụ thuộc múi giờ mặc định của JVM hay múi giờ đang gắn với nguồn clock.

Nếu dùng `clock.withZone(businessZone)`, thời điểm của clock không bị dịch chuyển; chỉ ngữ cảnh chuyển sang ngày giờ thay đổi. Đây khác với cộng thêm vài giờ vào `Instant`. Các biến thể clock và cách dùng cho kiểm thử được mô tả ở [Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).

## 4. Không nhầm đồng hồ UTC với ngày nghiệp vụ UTC

Dùng `Clock.systemUTC()` làm nguồn thời điểm là hợp lý, nhưng gọi `LocalDate.now(clockUtc)` sẽ cho ngày theo UTC.

Giả sử thời điểm tham chiếu là `2024-01-01T17:00Z`:

```text
Ngày theo UTC:                 2024-01-01
Ngày theo Asia/Ho_Chi_Minh:     2024-01-02
```

Nguồn clock UTC không có lỗi; phép suy ra ngày đã chọn múi giờ không đúng với câu hỏi nghiệp vụ.

Không sửa bằng “cộng 7 giờ rồi lấy ngày UTC” cho mọi trường hợp. Cách đó biến múi giờ thành một phép cộng số cố định, dễ sai khi quy tắc vùng thay đổi hoặc khi áp dụng cho vùng khác. Hãy để `ZoneId` thực hiện chuyển đổi.

Cũng không gọi `LocalDate.now()` rồi dùng kết quả như thể nó đã thuộc múi giờ nghiệp vụ. Đến lúc chỉ còn `LocalDate`, thông tin thời điểm và vùng gốc không còn đủ để sửa lại một cách tổng quát.

## 5. Lấy một mốc tham chiếu cho một lần xử lý

Nếu một yêu cầu cần nhiều phép kiểm tra “hôm nay”, hãy xác định ngày một lần rồi dùng lại. Hai lời gọi đọc thời gian riêng có thể nằm hai phía của nửa đêm.

Ví dụ một báo cáo lấy ngày tiêu đề trước nửa đêm nhưng tính khoảng truy vấn sau nửa đêm có thể ghép hai ngày khác nhau trong cùng kết quả.

Một cách làm rõ ràng là:

```java
// Minh họa bên trong một phương thức có clock và businessZone.
Instant reference = clock.instant();
LocalDate today = LocalDate.ofInstant(reference, businessZone);
```

Từ `today` đó, tính hạn, nhãn ngày và khoảng truy vấn trong cùng lần xử lý. Trong ví dụ đầy đủ, `todayWindow()` đọc một thời điểm rồi tạo cả ngày và hai ranh giới từ cùng ngày đã xác định.

Không lưu `today` vào trường khởi tạo một lần rồi dùng mãi suốt vòng đời dịch vụ. Kết quả đó sẽ trở thành ngày lúc dịch vụ khởi động. Cần chụp lại theo phạm vi phù hợp, chẳng hạn mỗi yêu cầu hoặc mỗi lần chạy báo cáo.

Với xử lý nền, cũng phải phân biệt “ngày lúc xử lý” và “ngày của sự kiện”. Nếu yêu cầu phân loại theo ngày sự kiện, dùng `eventInstant` và múi giờ nghiệp vụ, không dùng thời điểm hiện tại của tác vụ đọc lại.

## 6. Từ ngày nghiệp vụ sang khoảng thời điểm

Để chọn các sự kiện thuộc “hôm nay”, có thể tính khoảng nửa mở:

```text
[fromInclusive, toExclusive)
```

Trong đó:

- `fromInclusive` là đầu ngày nghiệp vụ.
- `toExclusive` là đầu ngày lịch kế tiếp trong cùng múi giờ.

Cách tính:

```java
// Minh họa bên trong một phương thức.
Instant fromInclusive = today.atStartOfDay(businessZone).toInstant();
Instant toExclusive =
        today.plusDays(1).atStartOfDay(businessZone).toInstant();
```

Điều kiện chọn sự kiện là `event >= fromInclusive && event < toExclusive`. Sự kiện đúng đầu ngày thuộc khoảng; sự kiện đúng đầu ngày kế tiếp không thuộc khoảng.

Không dùng `23:59:59` làm cuối ngày, vì có phần giây nhỏ hơn một giây. Cũng không cần đoán “nano giây cuối cùng” trong khi kho có thể giữ mức chính xác khác. Cận trên loại trừ đầu ngày kế tiếp tránh những vấn đề đó.

`atStartOfDay(zone)` trả thời gian hợp lệ sớm nhất của ngày theo quy tắc vùng; không bảo đảm mọi nơi, mọi ngày đều bắt đầu tại 00:00 thông thường. Hành vi này nằm trong hợp đồng của [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

### Không mặc định khoảng ngày luôn dài 24 giờ

Khi offset đổi do giờ mùa hè, khoảng từ đầu một ngày đến đầu ngày kế tiếp có thể dài 23 hoặc 25 giờ.

Ví dụ theo quy tắc vùng `Europe/Paris` cho các ngày trong chương trình:

- Ngày 31/3/2024: 23 giờ.
- Ngày 27/10/2024: 25 giờ.

Nếu lấy đầu ngày rồi cộng cố định `Duration.ofHours(24)`, ranh giới có thể không còn là đầu ngày nghiệp vụ kế tiếp. Các ví dụ 23/25 giờ không phải danh sách mọi trường hợp lịch sử; một số vùng còn có thay đổi khác. Cần dùng quy tắc vùng thay vì tự mã hóa độ dài ngày. Xem cơ chế offset, khoảng thiếu và khoảng lặp ở [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).

## 7. Chương trình Java 17+ kiểm chứng ngày nghiệp vụ

Lưu mã sau thành `BusinessToday.java`. Chương trình dùng clock cố định, không phụ thuộc ngày chạy và không cần chờ đến nửa đêm.

`BusinessCalendar` nhận nguồn thời điểm cùng múi giờ nghiệp vụ. `DayWindow` chứa ngày và khoảng thời điểm tương ứng. Các đối tượng này chỉ minh họa cách tổ chức trách nhiệm; không yêu cầu dùng một framework cụ thể.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class BusinessToday {
    public record DayWindow(LocalDate date, Instant fromInclusive,
                            Instant toExclusive) {
        public boolean contains(Instant value) {
            return !value.isBefore(fromInclusive) && value.isBefore(toExclusive);
        }

        public long elapsedHours() {
            return Duration.between(fromInclusive, toExclusive).toHours();
        }
    }

    public static final class BusinessCalendar {
        private final Clock clock;
        private final ZoneId zone;

        public BusinessCalendar(Clock clock, ZoneId zone) {
            this.clock = Objects.requireNonNull(clock, "clock");
            this.zone = Objects.requireNonNull(zone, "zone");
        }

        public LocalDate today() {
            return LocalDate.ofInstant(clock.instant(), zone);
        }

        public DayWindow todayWindow() {
            Instant snapshot = clock.instant();
            return windowFor(LocalDate.ofInstant(snapshot, zone));
        }

        public DayWindow windowFor(LocalDate date) {
            Objects.requireNonNull(date, "date");
            return new DayWindow(date,
                    date.atStartOfDay(zone).toInstant(),
                    date.plusDays(1).atStartOfDay(zone).toInstant());
        }
    }

    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId customerZone = ZoneId.of("America/Los_Angeles");
        Instant reference = Instant.parse("2024-01-01T00:30:00Z");
        Clock source = Clock.fixed(reference, ZoneOffset.UTC);
        BusinessCalendar business = new BusinessCalendar(source, businessZone);
        BusinessCalendar customer = new BusinessCalendar(source, customerZone);
        eq(business.today(), LocalDate.of(2024, 1, 1));
        eq(customer.today(), LocalDate.of(2023, 12, 31));

        Clock before = Clock.fixed(
                Instant.parse("2024-01-01T16:59:59.999999999Z"), ZoneOffset.UTC);
        Clock after = Clock.fixed(
                Instant.parse("2024-01-01T17:00:00Z"), ZoneOffset.UTC);
        eq(new BusinessCalendar(before, businessZone).today(),
                LocalDate.of(2024, 1, 1));
        BusinessCalendar afterMidnight = new BusinessCalendar(after, businessZone);
        eq(afterMidnight.today(), LocalDate.of(2024, 1, 2));
        eq(LocalDate.now(after), LocalDate.of(2024, 1, 1));
        eq(LocalDate.now(after.withZone(businessZone)), LocalDate.of(2024, 1, 2));
        eq(after.withZone(businessZone).instant(), after.instant());

        DayWindow day = afterMidnight.todayWindow();
        eq(day.date(), LocalDate.of(2024, 1, 2));
        eq(day.fromInclusive(), Instant.parse("2024-01-01T17:00:00Z"));
        eq(day.toExclusive(), Instant.parse("2024-01-02T17:00:00Z"));
        eq(day.contains(day.fromInclusive()), true);
        eq(day.contains(day.toExclusive().minusNanos(1)), true);
        eq(day.contains(day.toExclusive()), false);
        eq(day.contains(day.fromInclusive().minusNanos(1)), false);
        eq(day.elapsedHours(), 24L);

        BusinessCalendar paris = new BusinessCalendar(source, ZoneId.of("Europe/Paris"));
        DayWindow spring = paris.windowFor(LocalDate.of(2024, 3, 31));
        DayWindow autumn = paris.windowFor(LocalDate.of(2024, 10, 27));
        eq(spring.elapsedHours(), 23L);
        eq(autumn.elapsedHours(), 25L);
        eq(spring.fromInclusive(), Instant.parse("2024-03-30T23:00:00Z"));
        eq(spring.toExclusive(), Instant.parse("2024-03-31T22:00:00Z"));
        eq(spring.fromInclusive().plus(Duration.ofHours(24))
                .equals(spring.toExclusive()), false);

        System.out.println("businessToday=" + business.today());
        System.out.println("customerToday=" + customer.today());
        System.out.println("afterBusinessMidnight=" + afterMidnight.today());
        System.out.println("sourceClockDate=" + LocalDate.now(after));
        System.out.println("dayStart=" + day.fromInclusive());
        System.out.println("dayEndExclusive=" + day.toExclusive());
        System.out.println("springDayHours=" + spring.elapsedHours());
        System.out.println("autumnDayHours=" + autumn.elapsedHours());
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BusinessToday.java
java BusinessToday
```

Stdout:

```text
businessToday=2024-01-01
customerToday=2023-12-31
afterBusinessMidnight=2024-01-02
sourceClockDate=2024-01-01
dayStart=2024-01-01T17:00:00Z
dayEndExclusive=2024-01-02T17:00:00Z
springDayHours=23
autumnDayHours=25
PASS checks=20
```

Hàm `eq` chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Những ca quan trọng gồm:

1. Cùng thời điểm nhưng hai vùng cho hai ngày khác nhau.
2. Ngày nghiệp vụ đổi giữa `16:59:59.999999999Z` và `17:00:00Z` trong ví dụ Việt Nam.
3. Clock UTC và lịch nghiệp vụ không nhất thiết cùng ngày.
4. Khoảng ngày chứa đầu ngày, chứa thời điểm ngay trước cuối khoảng, nhưng không chứa đầu ngày kế tiếp.
5. Ngày chuyển giờ có độ dài khác 24 giờ.

Có thể chạy lại với hai múi giờ mặc định khác nhau:

```shell
java "-Duser.timezone=UTC" BusinessToday
java "-Duser.timezone=America/New_York" BusinessToday
```

Cả hai lần phải có cùng kết quả trên. Các múi giờ nghiệp vụ vẫn do đối số cấu hình quyết định; đổi múi giờ máy chủ không làm thay hợp đồng của dịch vụ.

Chương trình dùng các ngày giả lập năm 2024 để kiểm tra cơ chế. Nó không khẳng định những dòng ngày in ra là ngày hiện tại khi người học chạy.

## 8. Phân biệt ngày lịch, ngày làm việc và ngày chốt

Câu hỏi “hôm nay” có thể đang bị dùng thay cho ba khái niệm khác nhau:

| Khái niệm | Quy tắc cần có |
| --- | --- |
| Ngày lịch tại vùng nghiệp vụ | Thời điểm tham chiếu + `ZoneId` |
| Ngày làm việc | Ngày lịch + lịch cuối tuần/nghỉ lễ/quy định cơ sở |
| Ngày xử lý hoặc kỳ chốt | Ranh giới vận hành đã được quy định, có thể khác nửa đêm |

Nếu ngày xử lý bắt đầu lúc 04:00, 02:00 sáng có thể vẫn được gán vào kỳ vận hành trước đó theo chính sách. `LocalDate.now(zone)` không tự biết quy tắc đó.

Không gộp ngày chốt vào một hàm tên `today()` mà không công bố ý nghĩa. Hãy đặt hợp đồng riêng, nêu ranh giới, múi giờ và cách xử lý khi ranh giới gặp thay đổi offset. Ví dụ trong bài chỉ tính ngày lịch, chưa triển khai lịch nghỉ hoặc kỳ bắt đầu lúc 04:00.

## 9. Cấu hình và dữ liệu cần được dùng nhất quán

Một số quyết định cần rõ trong thiết kế:

- **Nguồn múi giờ:** lấy từ cấu hình tổ chức, cơ sở hay hồ sơ người dùng theo chức năng.
- **Phạm vi dùng:** một quyết định nghiệp vụ không nên trộn ngày theo trình duyệt với ngày theo máy chủ.
- **Cấu hình sai:** phân tích `ZoneId` và báo lỗi rõ, thay vì âm thầm quay về múi giờ máy chủ.
- **Sự kiện lịch sử:** nếu phải tái tạo ngày đã gán, cần giữ thời điểm và ngữ cảnh vùng/quy tắc liên quan; chỉ giữ một chuỗi “hôm nay” không đủ.
- **Xử lý nhiều ngày:** đọc sự kiện theo khoảng thời điểm được tính từ từng ngày trong cùng vùng, thay vì tăng ranh giới UTC bằng 24 giờ cho mọi ngày.

Nếu cơ sở dữ liệu có hàm “ngày hiện tại”, kiểm tra múi giờ của phiên/kết nối trước khi coi nó tương đương với hàm Java. Hai phía dùng cùng một thời điểm nhưng khác múi giờ vẫn có thể trả khác ngày.

Trong một hệ thống nhiều tổ chức, cache kết quả ngày phải có ngữ cảnh phù hợp. Một ngày tính theo tổ chức ở vùng A không được tái sử dụng như kết quả chung cho vùng B.

## 10. Lỗi thường gặp và thực hành

| Lỗi | Tại sao xảy ra? | Cách sửa |
| --- | --- | --- |
| Gọi `LocalDate.now()` ở mọi nơi | Phụ thuộc múi giờ mặc định JVM | Truyền clock và vùng theo hợp đồng |
| Dùng clock UTC rồi quên vùng nghiệp vụ | Lấy ngày theo UTC | Suy ra ngày bằng vùng nghiệp vụ rõ ràng |
| Cộng cố định 7 giờ để “đổi múi giờ” | Trộn độ lệch với quy tắc vùng | Chuyển `Instant` qua `ZoneId` |
| Đọc ngày nhiều lần trong một báo cáo | Có thể đi qua nửa đêm | Giữ một mốc tham chiếu cho lần xử lý |
| Tính đầu ngày kế tiếp bằng cộng 24 giờ | Ngày địa phương có thể dài khác | Lấy ngày kế tiếp rồi `atStartOfDay(zone)` |
| Dùng ngày hiện tại để phân loại sự kiện cũ | Nhầm thời điểm xử lý với thời điểm sự kiện | Tính từ thời điểm của sự kiện |
| Đóng băng ngày khi dịch vụ khởi động | Không cập nhật qua ngày mới | Chụp ngày theo từng phạm vi xử lý |
| Coi hôm nay tự động là ngày làm việc | Thiếu quy tắc lịch nghỉ | Tách khái niệm và chính sách tương ứng |

Thực hành:

1. **Giữ nguyên thời điểm `2024-01-01T00:30Z`, đổi vùng của báo cáo sang Los Angeles.** Ngày phải là `2023-12-31`; đừng thay đổi thời điểm để ép cùng ngày với Việt Nam.

2. **Một hạn được ghi bằng `LocalDate` theo lịch cơ sở.** Tính hôm nay theo cùng vùng trước khi so; không lấy ngày máy chủ làm chuẩn ngầm.

3. **Truy vấn sự kiện đúng lúc đầu ngày kế tiếp.** Sự kiện đó không thuộc khoảng của ngày trước vì cận trên là loại trừ.

4. **Chạy báo cáo vào ngày 31/3/2024 tại Paris.** Khoảng từ đầu ngày đến đầu ngày kế tiếp dài 23 giờ, nên điều kiện đúng không phải “luôn đủ 86.400 giây”.

5. **Tác vụ chạy hôm nay nhưng xử lý sự kiện từ tuần trước.** Nếu yêu cầu là ngày nghiệp vụ của sự kiện, dùng thời điểm sự kiện và vùng tương ứng; nếu yêu cầu là ngày xử lý, dùng clock hiện tại. Hãy nêu rõ lựa chọn.

Muốn xác định hôm nay đúng, hãy giữ rõ ba yếu tố: thời điểm tham chiếu, múi giờ quyết định ngày và chính sách nghiệp vụ đang nói đến ngày lịch hay một loại ngày xử lý khác.
