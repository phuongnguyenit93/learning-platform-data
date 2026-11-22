# `Clock.systemUTC()` và `Clock.system(ZoneId)`

## Chọn nguồn “bây giờ” và chọn cách nhìn ngày giờ địa phương

Một ứng dụng cần ghi thời điểm tạo bài làm, đồng thời xác định “hôm nay” theo giờ Việt Nam. Hai việc này liên quan nhưng không giống nhau:

- Thời điểm tạo là một mốc trên dòng thời gian, thường biểu diễn bằng `Instant`.
- “Hôm nay” là một ngày địa phương, cần một múi giờ để xác định.

`Clock` tập hợp một nguồn cung cấp thời điểm cùng vùng dùng khi suy ra ngày/giờ. Hai factory thông dụng là:

```java
Clock utcClock = Clock.systemUTC();
Clock vietnamClock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đây là đoạn minh họa, cần import `java.time.Clock` và `java.time.ZoneId`.

Cả hai đều đọc nguồn thời gian hệ thống; khác biệt chính ở đây là vùng được cấu hình trong Clock. Chọn vùng Việt Nam không có nghĩa `Instant` phải bị cộng bảy giờ.

## 1. Hai thành phần cần phân biệt trong một `Clock`

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| Thời điểm được đồng hồ cung cấp | `clock.instant()` | Một `Instant` |
| Múi giờ dùng để suy ra ngày giờ | `clock.getZone()` | Một `ZoneId` |
| Đổi vùng cho cùng kiểu nguồn đồng hồ | `clock.withZone(zone)` | Một Clock mang vùng khác |

Có thể hình dung:

```text
Nguồn thời gian hệ thống
          │
          ▼
       Instant
          │
          ├── UTC                 → ngày/giờ theo UTC
          └── Asia/Ho_Chi_Minh    → ngày/giờ tại vùng Việt Nam
```

`Clock.systemUTC()` dùng vùng UTC. `Clock.system(zone)` dùng vùng được truyền vào. Các factory hệ thống chọn nguồn thời gian hệ thống tốt nhất có sẵn; không nên giả định độ phân giải luôn là nano giây chỉ vì `Instant` có thể biểu diễn phần nano. [Tài liệu `Clock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)

Với cùng thời điểm quan sát, đổi vùng làm thay đổi cách nhìn ngày giờ địa phương. Các lời gọi đọc hai đồng hồ thật diễn ra nối tiếp vẫn có thể trả về hai thời điểm hơi khác nhau, vì thời gian đã trôi qua giữa hai lần đọc.

## 2. Factory nào dùng cho mục đích nào?

### `Clock.systemUTC()`

Phù hợp khi lớp cần nguồn thời điểm hệ thống với vùng mặc định của nguồn được khai báo là UTC. Ví dụ:

```java
Clock clock = Clock.systemUTC();
Instant createdAt = Instant.now(clock);
```

Đây là đoạn minh họa. `Instant` không giữ một “giờ địa phương UTC” như trường giờ riêng; nó biểu diễn mốc thời gian. Dạng chuỗi thường thấy kết thúc bằng `Z`.

Nếu lấy:

```java
LocalDate today = LocalDate.now(clock);
```

thì “hôm nay” ở đây là ngày theo UTC, vì lớp `LocalDate` cần dùng vùng của Clock để suy ra ngày. Không mặc định ngày ấy luôn bằng ngày hiện tại của người dùng ở Việt Nam.

### `Clock.system(ZoneId)`

Phù hợp khi nguồn thời gian hệ thống phải đi cùng một vùng nghiệp vụ cụ thể:

```java
Clock clock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDate businessToday = LocalDate.now(clock);
```

`businessToday` được tính theo vùng đã chỉ định. Nếu dùng `Instant.now(clock)`, kết quả vẫn là mốc thời gian, không phải một mốc đã được dịch thêm bảy giờ.

### Khác với `systemDefaultZone()`

`Clock.systemDefaultZone()` lấy vùng mặc định của môi trường lúc tạo Clock. Nếu nghiệp vụ đã yêu cầu vùng cụ thể, chọn `system(zone)` làm cấu hình ấy rõ ràng và tránh để máy chạy quyết định ngầm.

Tạo một Clock có vùng cụ thể không thay đổi múi giờ mặc định của JVM hay của hệ điều hành. Nó chỉ cung cấp một đối tượng với cấu hình để mã của bạn sử dụng.

## 3. Chương trình hoàn chỉnh

Lưu dưới tên `SystemClockZonesDemo.java`. Chương trình dùng Java 17 trở lên:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.Objects;

public class SystemClockZonesDemo {
    record Snapshot(Instant observedAt, LocalDate businessDate) {}

    static final class LearningService {
        private final Clock clock;

        LearningService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        Snapshot snapshot() {
            Instant observedAt = clock.instant();
            LocalDate businessDate =
                    observedAt.atZone(clock.getZone()).toLocalDate();
            return new Snapshot(observedAt, businessDate);
        }
    }

    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        Clock systemUtc = Clock.systemUTC();
        Clock systemVietnam = Clock.system(vietnam);

        System.out.println("systemUtcZone=" + systemUtc.getZone().getId());
        System.out.println("systemVietnamZone="
                + systemVietnam.getZone().getId());
        System.out.println("utcConfigured="
                + systemUtc.getZone().normalized().equals(ZoneOffset.UTC));
        System.out.println("vietnamConfigured="
                + systemVietnam.getZone().equals(vietnam));

        Clock changedView = systemUtc.withZone(vietnam);
        System.out.println("changedViewZone=" + changedView.getZone().getId());
        System.out.println("originalStillUtc="
                + systemUtc.getZone().normalized().equals(ZoneOffset.UTC));

        Instant actualNow = Instant.now(systemUtc);
        System.out.println("systemInstantRead=" + (actualNow != null));

        Instant sample = Instant.parse("2024-06-15T18:30:00Z");
        Clock fixedUtc = Clock.fixed(sample, ZoneOffset.UTC);
        Clock fixedVietnam = fixedUtc.withZone(vietnam);

        System.out.println("fixedUtcInstant=" + Instant.now(fixedUtc));
        System.out.println("fixedVietnamInstant=" + Instant.now(fixedVietnam));
        System.out.println("sameFixedInstant="
                + Instant.now(fixedUtc).equals(Instant.now(fixedVietnam)));

        System.out.println("utcDate=" + LocalDate.now(fixedUtc));
        System.out.println("vietnamDate=" + LocalDate.now(fixedVietnam));
        System.out.println("utcLocal=" + LocalDateTime.now(fixedUtc));
        System.out.println("vietnamLocal=" + LocalDateTime.now(fixedVietnam));
        System.out.println("vietnamZoned=" + ZonedDateTime.now(fixedVietnam));

        LearningService service = new LearningService(fixedVietnam);
        Snapshot snapshot = service.snapshot();
        System.out.println("snapshotInstant=" + snapshot.observedAt());
        System.out.println("snapshotBusinessDate=" + snapshot.businessDate());

        Clock explicitUtc = Clock.system(ZoneOffset.UTC);
        System.out.println("explicitUtcConfigured="
                + explicitUtc.getZone().equals(ZoneOffset.UTC));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SystemClockZonesDemo.java
java SystemClockZonesDemo
```

Stdout:

```text
systemUtcZone=Z
systemVietnamZone=Asia/Ho_Chi_Minh
utcConfigured=true
vietnamConfigured=true
changedViewZone=Asia/Ho_Chi_Minh
originalStillUtc=true
systemInstantRead=true
fixedUtcInstant=2024-06-15T18:30:00Z
fixedVietnamInstant=2024-06-15T18:30:00Z
sameFixedInstant=true
utcDate=2024-06-15
vietnamDate=2024-06-16
utcLocal=2024-06-15T18:30
vietnamLocal=2024-06-16T01:30
vietnamZoned=2024-06-16T01:30+07:00[Asia/Ho_Chi_Minh]
snapshotInstant=2024-06-15T18:30:00Z
snapshotBusinessDate=2024-06-16
explicitUtcConfigured=true
```

Chương trình thực sự đọc Clock hệ thống nhưng không in mốc hiện tại thay đổi theo lần chạy. Phần so sánh ngày/giờ dùng một mốc cố định để stdout có thể kiểm chứng.

## 4. Cùng mốc thời gian, hai ngày địa phương

Mốc mẫu là:

```text
2024-06-15 18:30 UTC
            │
            └── tại Asia/Ho_Chi_Minh: 2024-06-16 01:30
```

Vì vậy:

| Lời gọi | Clock UTC | Clock vùng Việt Nam |
| --- | --- | --- |
| `Instant.now(clock)` trên Clock cố định cùng mốc | Cùng `Instant` | Cùng `Instant` |
| `LocalDate.now(clock)` | 2024-06-15 | 2024-06-16 |
| `LocalDateTime.now(clock)` | 2024-06-15T18:30 | 2024-06-16T01:30 |
| `ZonedDateTime.now(clock)` | Giữ cả vùng/offset tương ứng | Giữ cả vùng/offset tương ứng |

`LocalDate.now(clock)` tính ngày hiện tại từ thời điểm và vùng của Clock. `LocalDate` kết quả không tiếp tục giữ múi giờ bên trong nó. [Tài liệu `LocalDate.now(Clock)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#now(java.time.Clock))

Đây là lý do một hệ thống kiểm tra “bài có thuộc hôm nay không?” cần thống nhất vùng. Dùng ngày UTC ở một chỗ và ngày Việt Nam ở chỗ khác có thể cho hai kết luận quanh ranh giới nửa đêm, dù mọi máy đều có thời gian chính xác.

Đối với một mốc hết hạn tuyệt đối, thường so sánh `Instant`. Đối với quy tắc theo ngày lịch của một vùng, cần suy ra ngày bằng vùng đó. Không chọn kiểu và Clock chỉ theo thói quen in chuỗi.

## 5. `withZone` đổi vùng, không đóng băng thời gian hay dịch thời điểm

Trong chương trình:

```java
Clock changedView = systemUtc.withZone(vietnam);
```

tạo một Clock có vùng Việt Nam cho cùng cách cung cấp thời điểm. Clock nguồn vẫn giữ vùng UTC. Không cần sửa Clock gốc hoặc thay cấu hình toàn cục.

Tuy nhiên, `withZone` không làm đồng hồ hệ thống thành cố định. Mỗi lần gọi `instant()` trên Clock hệ thống vẫn là một lần đọc nguồn thời gian.

Do đó, đoạn sau không phải một kiểm tra ổn định:

```java
// Minh họa điều không nên dùng để kiểm tra sự tương đương vùng.
boolean same = systemUtc.instant().equals(changedView.instant());
```

Hai lời gọi có thể khác mốc vì được thực hiện vào hai lúc. Giá trị false không chứng minh vùng đã làm dịch thời điểm.

Chương trình dùng `Clock.fixed` chỉ để cô lập tác động của vùng ở cùng một mốc. Trong môi trường chạy thật, chọn factory hệ thống; trong kiểm thử cần tái lập, truyền một nguồn thời gian có thể điều khiển.

`Clock.systemUTC()` và `Clock.system(ZoneOffset.UTC)` đều thể hiện lựa chọn nguồn hệ thống cùng vùng UTC. Không cần dựa vào chúng có phải cùng tham chiếu đối tượng hay cùng tên lớp triển khai nội bộ.

## 6. Truyền Clock để nơi dùng thời gian có thể kiểm thử

Lớp `LearningService` nhận `Clock` qua hàm khởi tạo. Khi chạy thật, ứng dụng có thể lắp ghép:

```java
LearningService service = new LearningService(
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
```

Đây là đoạn trích, cần đặt trong ngữ cảnh có lớp `LearningService` như chương trình đầy đủ.

Khi kiểm thử, truyền `Clock.fixed` tại một mốc gần ranh giới ngày. Logic không cần đổi sang nhánh riêng “đang test”; nguồn thời gian là phần có thể thay.

Nếu trong lớp lại tạo mới:

```java
Clock clock = Clock.systemUTC();
```

ở mỗi phương thức, việc truyền Clock kiểm thử từ bên ngoài sẽ mất tác dụng. Tương tự, một lời gọi `LocalDate.now()` chen vào giữa mã đang dùng Clock được truyền vào sẽ đọc nguồn/vùng mặc định khác.

Hãy kiểm tra đường dùng thời gian thực sự phụ thuộc đối tượng được cung cấp, không chỉ kiểm tra lớp có một trường tên `clock`. `Clock` được thiết kế để hỗ trợ thay nguồn thời gian cho các mục đích như kiểm thử. [Tài liệu sử dụng Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)

## 7. Đọc một lần khi cần một ảnh chụp nhất quán

Đồng hồ hệ thống không dừng giữa hai dòng lệnh. Nếu làm:

```java
Instant createdAt = Instant.now(clock);
LocalDate businessDate = LocalDate.now(clock);
```

thì đó là hai lần đọc. Gần nửa đêm, lần đọc thứ hai có thể sang ngày mới trong khi mốc đầu vẫn ở ngày cũ.

Trong `snapshot()`, chương trình đọc một `Instant` rồi suy ra ngày từ chính mốc ấy:

```java
Instant observedAt = clock.instant();
LocalDate businessDate =
        observedAt.atZone(clock.getZone()).toLocalDate();
```

Cách này phù hợp khi `businessDate` phải diễn đạt ngày địa phương của `observedAt`. Nó không có nghĩa mọi ứng dụng luôn phải chụp thời gian một lần cho cả tiến trình dài. Hãy chọn thời điểm đọc theo ý nghĩa của từng thao tác.

Cũng không lưu sẵn `LocalDate.now(clock)` vào một hằng khởi tạo rồi dùng mãi như “hôm nay”. Hằng Clock là nguồn có thể đọc lại; một ngày đã đọc chỉ là giá trị tại lúc quan sát.

## 8. Những điều Clock hệ thống không tự bảo đảm

- Chọn UTC không làm giờ hệ thống chính xác hơn. Cả hai factory vẫn phụ thuộc nguồn thời gian hệ thống có sẵn.
- Chọn vùng không phải một thao tác kết nối đến máy chủ thời gian của vùng đó.
- Một Clock hệ thống không phải Clock cố định để so sánh tuyệt đối từng nano giây trong kiểm thử.
- Không suy ra độ chính xác vật lý từ độ chi tiết mà `Instant` lưu được.
- Thời gian theo đồng hồ hệ thống có thể bị hiệu chỉnh; không dùng giả định mọi lần đọc đều tăng một lượng chính xác để thay cho kiểm chứng yêu cầu thực tế.
- Múi giờ vùng có thể thay offset theo ngày. Dùng `ZoneId` và quy tắc vùng thay vì cộng tay một số giờ cố định cho mọi trường hợp.

Nếu mục tiêu là đo thời lượng thực thi của một đoạn mã, cần phân biệt phép đo thời gian trôi qua với đọc mốc thời gian lịch. Bài này tập trung vào nguồn “hiện tại” để tạo giá trị ngày giờ nghiệp vụ, không dùng Clock hệ thống như công cụ đo hiệu năng chính xác.

## 9. Kiểm chứng cấu hình và hành vi

Những kiểm tra có ích:

| Điều cần xác nhận | Cách kiểm tra phù hợp |
| --- | --- |
| UTC được cấu hình | Xem `getZone()`, chuẩn hóa nếu muốn so sánh vùng cố định |
| Vùng nghiệp vụ chính xác | So với `ZoneId` được yêu cầu |
| Cùng mốc có ngày khác qua vùng | Dùng Clock cố định tại mốc gần nửa đêm |
| Clock truyền vào thực sự được sử dụng | Chạy logic với một ngày cố định khác xa ngày thật |
| Mốc và ngày địa phương trong một bản ghi nhất quán | Suy ra chúng từ cùng lần đọc |
| Không phụ thuộc máy chạy | Cấu hình vùng rõ ràng và tránh các lời gọi mặc định chen vào |

Khi kiểm tra ngày địa phương, nên có mốc trước và sau ranh giới ngày của vùng nghiệp vụ. Chỉ thử giữa trưa dễ khiến Clock UTC và Clock vùng Việt Nam cho cùng ngày, che mất cấu hình sai.

## 10. Tự thực hành

1. `Clock.system(Asia/Ho_Chi_Minh)` có làm `Instant` tự được cộng bảy giờ không?
2. `LocalDate.now(Clock.systemUTC())` trả ngày theo vùng nào?
3. Vì sao không nên kiểm tra hai lần đọc Clock hệ thống bằng `Instant.equals` rồi coi đó là bằng chứng về múi giờ?
4. Muốn dùng vùng Việt Nam khi chạy thật và mốc cố định khi test, lớp nghiệp vụ nên nhận gì?
5. Nếu mốc tạo và ngày nghiệp vụ phải nhất quán, có nên đọc hai lần độc lập sát nửa đêm không?

Gợi ý đáp án:

1. Không; vùng được dùng khi suy ra ngày giờ địa phương.
2. UTC.
3. Hai lần đọc diễn ra ở hai lúc; khác biệt có thể do thời gian đã trôi qua.
4. Nhận `Clock` qua hàm khởi tạo hoặc tham số, rồi dùng nguồn ấy.
5. Nên đọc một mốc rồi suy ra ngày từ cùng mốc nếu đó là yêu cầu của bản ghi.

Hãy dùng `systemUTC()` hoặc `system(zone)` để chọn nguồn hệ thống cùng vùng rõ ràng, đồng thời truyền Clock vào nơi cần “bây giờ” để hành vi có thể kiểm chứng.
