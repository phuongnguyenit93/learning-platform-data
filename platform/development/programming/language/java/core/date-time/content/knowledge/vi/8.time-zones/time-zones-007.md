# Quy tắc lịch sử và thay đổi tương lai trong cơ sở dữ liệu múi giờ

Một tên múi giờ như `America/New_York`, `Asia/Kathmandu` hay `Pacific/Apia` **không tương đương với một offset UTC cố định**. Đó là định danh của một bộ quy tắc: tại **mỗi thời điểm**, đồng hồ địa phương phải chạy theo offset nào và trong quá khứ/tương lai đã hoặc dự kiến sẽ có các lần đổi giờ nào. Những quy tắc này có thể thay đổi vì luật pháp, daylight saving time (DST), thay đổi đường đổi ngày hoặc vì dữ liệu lịch sử được sửa lại.

Java sử dụng `ZoneId` và `ZoneRules` từ `java.time` để tra cứu những quy tắc đó. Dữ liệu múi giờ thường được phân phối theo **IANA Time Zone Database (tzdb)** và được đóng gói vào bản cập nhật JDK/runtime. Bài này giải thích cách đọc dữ liệu lịch sử, hiểu mức độ chắc chắn của các dự đoán tương lai và thiết kế ứng dụng chịu được việc tzdb được cập nhật.

## 1. Múi giờ vùng là một tập quy tắc biến đổi theo thời gian

Cần phân biệt bốn khái niệm:

| Khái niệm | Ví dụ | Chứa thông tin gì? |
| --- | --- | --- |
| `Instant` | `2025-01-15T12:00:00Z` | Một điểm xác định trên trục thời gian; không giữ địa danh |
| `ZoneOffset` | `-05:00`, `+05:45` | Độ lệch UTC cố định, không có lịch sử hay DST |
| `ZoneId` theo vùng | `America/New_York` | Định danh có quy tắc offset thay đổi theo thời điểm |
| `ZoneRules` | `ZoneId.of("America/New_York").getRules()` | Các phép tra offset, thay đổi giờ và quy tắc chuyển đổi của vùng |

Ví dụ, một offset `-05:00` chỉ cho biết đồng hồ địa phương chậm hơn UTC năm giờ. Nó **không nói được** New York dùng offset nào vào tháng bảy. Với `America/New_York`, quy tắc tzdb biết New York thường dùng `-05:00` vào mùa đông và `-04:00` vào mùa hè theo quy tắc DST hiện hành của giai đoạn tương ứng.

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
ZoneRules rules = newYork.getRules();

ZoneOffset winter = rules.getOffset(
        Instant.parse("2025-01-15T12:00:00Z")); // -05:00
ZoneOffset summer = rules.getOffset(
        Instant.parse("2025-07-15T12:00:00Z")); // -04:00
~~~

Đoạn mã trên là ví dụ sử dụng trong một phương thức có import `java.time.*` và `java.time.zone.ZoneRules`. `getOffset(Instant)` trả offset theo **thời điểm đã xác định**. Đối với một `Instant`, việc xác định offset từ một `ZoneRules` là không mơ hồ.

Một **time zone** không phải đơn giản là “UTC cộng trừ một số giờ”. Dữ liệu còn phải chứa thời điểm áp dụng chính sách, chuyển đổi DST, các thay đổi hiếm gặp có bước nhảy khác một giờ và, ở một số vùng, cả sự thay đổi về ngày trên lịch.

## 2. IANA tzdb lưu lịch sử và dự đoán tương lai như thế nào?

IANA Time Zone Database (`tzdb` hoặc `zoneinfo`) là nguồn dữ liệu phổ biến của hệ điều hành và các thư viện ngôn ngữ, trong đó có những bản phân phối JDK. Nó có các định danh dạng `Area/Location`, ví dụ `Europe/London`, `Asia/Ho_Chi_Minh`, `Pacific/Apia` và `America/New_York`.

Dữ liệu thường mô tả:

1. **Khoảng lịch sử đã biết:** offset áp dụng tại các thời điểm trong quá khứ, các lần chuyển offset, các giai đoạn áp dụng hoặc bỏ DST.
2. **Quy tắc chuyển giờ lặp lại:** chẳng hạn chuyển sang DST vào một ngày Chủ nhật được định nghĩa bởi quy tắc, rồi trở lại giờ chuẩn vào thời điểm khác.
3. **Dự đoán tương lai theo thông tin hiện có:** khi luật hiện tại được giả định tiếp tục, tzdb có thể tính offset cho nhiều năm tiếp theo.
4. **Sửa dữ liệu cũ:** khi có bằng chứng lịch sử mới hoặc phát hiện sai lệch, tzdb có thể cập nhật offset của các mốc đã qua.
5. **Sửa dữ liệu tương lai:** khi một quốc gia/vùng công bố đổi chính sách, phiên bản mới có thể thay đổi những thời điểm chuyển giờ chưa diễn ra.

Một lưu ý quan trọng trong tài liệu IANA: tzdb được thiết kế chủ yếu để mô tả hành vi đồng hồ của các vùng **từ mốc POSIX epoch 1970** trở đi; dữ liệu cũ hơn có thể không đầy đủ và không nên mặc định chính xác tuyệt đối cho mọi địa điểm nhỏ. Tzdb là kết quả tổng hợp cộng đồng và nhà phân phối, không phải một văn bản luật có thẩm quyền thay cho quy định của từng quốc gia.

**Tương lai trong tzdb là dự báo theo bộ luật đang biết**, không phải cam kết pháp lý vĩnh viễn. Một Chính phủ có thể thay đổi DST hoặc offset với thời gian thông báo ngắn, dẫn đến kết quả lịch họp trong tương lai thay đổi khi runtime cài bản tzdb mới.

Nguồn tham khảo gốc: [IANA Time Zones](https://www.iana.org/time-zones), [IANA – Theory and pragmatics](https://www.iana.org/time-zones/theory).

## 3. Một mã ZoneId có thể có nhiều offset trong lịch sử

Ví dụ được kiểm chứng trong Java: `Asia/Kathmandu` từng dùng `+05:30` vào cuối năm 1985 và dùng `+05:45` sau thay đổi đầu năm 1986 trong dữ liệu múi giờ hiện có.

~~~java
ZoneId kathmandu = ZoneId.of("Asia/Kathmandu");
ZoneRules rules = kathmandu.getRules();

ZoneOffset oldOffset = rules.getOffset(
        Instant.parse("1985-12-01T00:00:00Z")); // +05:30
ZoneOffset laterOffset = rules.getOffset(
        Instant.parse("1986-02-01T00:00:00Z")); // +05:45
~~~

Cùng một `ZoneId` nhưng hai `Instant` thuộc những giai đoạn lịch sử khác nhau có offset khác nhau. Đây là lý do không thể lấy offset **hiện tại** rồi áp ngược cho dữ liệu quá khứ.

Một ví dụ khác là vùng `Pacific/Apia`. Khi Samoa thay đổi phía của đường đổi ngày, lịch địa phương **bỏ qua ngày 30/12/2011**. Theo dữ liệu zone của Java:

~~~java
ZoneId apia = ZoneId.of("Pacific/Apia");
LocalDate skipped = LocalDate.of(2011, 12, 30);

List<ZoneOffset> valid = apia.getRules().getValidOffsets(
        LocalDateTime.of(2011, 12, 30, 12, 0));
// valid = []: trưa ngày đó không tồn tại ở Apia

ZonedDateTime firstValid = skipped.atStartOfDay(apia);
// 2011-12-31T00:00+14:00[Pacific/Apia]
~~~

Đoạn này cần các import `java.time.*`, `java.time.zone.*` và `java.util.List`. Dù `LocalDate.of(2011,12,30)` là một ngày lịch ISO hợp lệ, **ngày ấy không có giờ địa phương hợp lệ trong vùng Apia theo tzdb**. Không phải mọi chuyển đổi offset đều là thao tác cộng hoặc trừ một giờ DST.

## 4. Lấy offset theo Instant khác với phân tích LocalDateTime

Có hai hướng chuyển đổi phải tách riêng:

**Hướng A — đã có thời điểm tuyệt đối:** `Instant → ZonedDateTime`. Bạn biết thời điểm trên trục UTC, nên theo một phiên bản tzdb cụ thể, hệ thống xác định được offset và giờ địa phương của vùng.

~~~java
Instant event = Instant.parse("2025-07-15T12:00:00Z");
ZonedDateTime local = event.atZone(
        ZoneId.of("America/New_York"));
// 2025-07-15T08:00-04:00[America/New_York]
~~~

**Hướng B — chỉ có giờ địa phương:** `LocalDateTime + ZoneId → một hoặc nhiều Instant khả dĩ`. Điều này có thể không đơn trị, vì một số giờ bị bỏ qua hoặc lặp lại khi đồng hồ đổi offset.

| Trạng thái của `LocalDateTime` trong một zone | Số offset hợp lệ | Ý nghĩa |
| --- | ---: | --- |
| Giờ thông thường | 1 | Có thể xác định một instant |
| **Gap** khi đồng hồ nhảy tiến | 0 | Giờ địa phương đó không tồn tại |
| **Overlap** khi đồng hồ quay lùi | 2 | Cùng giờ địa phương biểu diễn hai instant khác nhau |

Ví dụ tại New York vào năm 2025:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();

LocalDateTime gap = LocalDateTime.of(2025, 3, 9, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2025, 11, 2, 1, 30);

System.out.println(rules.getValidOffsets(gap));     // []
System.out.println(rules.getValidOffsets(overlap)); // [-04:00, -05:00]
~~~

Khi DST bắt đầu ngày 09/03/2025, 02:30 địa phương không tồn tại. Khi DST kết thúc ngày 02/11/2025, 01:30 xuất hiện hai lần. `ZoneRules.getTransition(local)` giúp tra lần chuyển đổi liên quan; `ZoneOffsetTransition.isGap()` và `isOverlap()` phân biệt hai trường hợp.

Mặc định `LocalDateTime.atZone(zone)` có chính sách giải quyết gap/overlap: trong gap thường điều chỉnh giờ tiến qua khoảng thiếu; trong overlap thường chọn offset trước chuyển đổi. Điều này thuận tiện cho nhiều tình huống nhưng **có thể sai quy tắc nghiệp vụ** đối với booking, tính công hay xử lý thanh toán. Hệ thống cần định nghĩa rõ khi nào báo lỗi hoặc cho người dùng chọn một offset cụ thể.

## 5. Ví dụ Java 17+ chạy độc lập: dữ liệu lịch sử và chuyển giờ

Lưu chương trình sau thành `ZoneRulesHistoryDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;
import java.time.zone.ZoneRulesProvider;
import java.util.List;

public class ZoneRulesHistoryDemo {
    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");
        ZoneRules rules = ny.getRules();

        Instant winter = Instant.parse("2025-01-15T12:00:00Z");
        Instant summer = Instant.parse("2025-07-15T12:00:00Z");
        LocalDateTime gap = LocalDateTime.of(2025, 3, 9, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2025, 11, 2, 1, 30);

        System.out.println("winter=" + rules.getOffset(winter));
        System.out.println("summer=" + rules.getOffset(summer));
        System.out.println("gapValid=" + rules.getValidOffsets(gap));
        System.out.println("gapIsGap="
                + rules.getTransition(gap).isGap());
        System.out.println("overlapValid="
                + rules.getValidOffsets(overlap));
        System.out.println("overlapIsOverlap="
                + rules.getTransition(overlap).isOverlap());
        System.out.println("gapResolved=" + gap.atZone(ny));
        System.out.println("overlapDefault=" + overlap.atZone(ny));
        System.out.println("overlapLate="
                + ZonedDateTime.ofLocal(
                        overlap, ny, ZoneOffset.ofHours(-5)));
        System.out.println("next="
                + rules.nextTransition(
                        Instant.parse("2025-01-01T00:00:00Z"))
                        .getInstant());

        ZoneId apia = ZoneId.of("Pacific/Apia");
        System.out.println("apiaValid="
                + apia.getRules().getValidOffsets(
                        LocalDateTime.of(2011, 12, 30, 12, 0)));
        System.out.println("apiaStart="
                + LocalDate.of(2011, 12, 30)
                        .atStartOfDay(apia));

        ZoneId kathmandu = ZoneId.of("Asia/Kathmandu");
        System.out.println("kath1985="
                + kathmandu.getRules().getOffset(
                        Instant.parse("1985-12-01T00:00:00Z")));
        System.out.println("kath1986="
                + kathmandu.getRules().getOffset(
                        Instant.parse("1986-02-01T00:00:00Z")));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac ZoneRulesHistoryDemo.java
java ZoneRulesHistoryDemo
~~~

Đầu ra với dữ liệu tzdb chứa những quy tắc lịch sử nêu trên:

~~~text
winter=-05:00
summer=-04:00
gapValid=[]
gapIsGap=true
overlapValid=[-04:00, -05:00]
overlapIsOverlap=true
gapResolved=2025-03-09T03:30-04:00[America/New_York]
overlapDefault=2025-11-02T01:30-04:00[America/New_York]
overlapLate=2025-11-02T01:30-05:00[America/New_York]
next=2025-03-09T07:00:00Z
apiaValid=[]
apiaStart=2011-12-31T00:00+14:00[Pacific/Apia]
kath1985=+05:30
kath1986=+05:45
~~~

`nextTransition(Instant)` tra lần chuyển tiếp **sau** instant cho trước theo bộ rules hiện tại; `getTransition(LocalDateTime)` dành cho trường hợp cần giải thích gap/overlap tại một giờ địa phương cụ thể. Bộ quy tắc múi giờ có thể được cập nhật về sau, nên với ví dụ lịch sử hiếm hoặc vùng có thay đổi mới, hãy kiểm tra phiên bản tzdb nếu đầu ra trên môi trường khác nhau.

## 6. Quy tắc quá khứ có thể được sửa sau khi sự kiện đã xảy ra

Một hiểu nhầm thường gặp là “tzdb chỉ thay đổi các ngày trong tương lai”. Trên thực tế, **các bản cập nhật có thể sửa dữ liệu lịch sử** khi có bằng chứng mới. IANA đôi khi sửa ngày chuyển DST, offset cũ hoặc thông tin một vùng từng dùng theo thời điểm nào. Ví dụ, release tzdb `2026e` (29/09/2026) có ghi nhận một sửa đổi thời điểm chuyển giờ của Ireland trong năm 1925. Đây là ví dụ cụ thể cho việc một ngày đã qua từ lâu vẫn có thể được hiệu chỉnh ở phiên bản dữ liệu mới.

Hệ quả là:

- Một `Instant` đã lưu — ví dụ timestamp của giao dịch `2025-04-09T07:30:00Z` — **không đổi** chỉ vì tzdb được cập nhật.
- Kết quả chuyển **instant đó sang giờ địa phương** của một vùng có thể khác giữa phiên bản tzdb cũ và mới nếu chính quy tắc liên quan được sửa.
- Một cặp `LocalDateTime + ZoneId` được giữ nguyên nhưng khi chuyển về `Instant` theo rules khác nhau có thể cho **instant khác nhau**.
- Với dữ liệu pháp lý hoặc lịch sử cần tái hiện chính xác kết quả tính toán trước đây, đôi khi phải lưu cả **định danh zone, offset đã thực sự áp dụng, instant gốc và phiên bản quy tắc** tại thời điểm xử lý.

Không có nghĩa tất cả các lần cập nhật đều làm thay đổi dữ liệu cũ. Mỗi release chỉ thay đổi những vùng/giai đoạn được ghi trong release notes. Đừng dựa vào giả định “mọi bản JDK sẽ cho cùng local time trong mọi năm” khi xây hệ thống lưu hồ sơ lịch sử.

Ví dụ lịch sử tzdb: [IANA release 2026e](https://www.iana.org/time-zones/releases/2026e).

## 7. Quy tắc tương lai có thể thay đổi sau khi đã đặt lịch

Giả sử ứng dụng lưu lịch họp cho **09:00 ngày 01/12/2027 theo giờ một thành phố**, nhưng trước thời điểm đó cơ quan quản lý đổi luật DST. Khi phiên bản tzdb mới được áp dụng, cùng một ý định “09:00 địa phương” có thể tương ứng **một instant UTC khác** so với lần tính ban đầu.

Có hai kiểu cam kết nghiệp vụ khác nhau:

| Điều người dùng muốn giữ cố định | Cách hiểu | Dữ liệu cần lưu |
| --- | --- | --- |
| **Thời điểm tuyệt đối** | “Gửi thông báo ở instant UTC này, bất kể luật múi giờ sau đó thay đổi” | `Instant` (+ thông tin hiển thị nếu cần) |
| **Giờ dân sự tại địa phương** | “Cuộc hẹn luôn bắt đầu 09:00 theo đồng hồ thành phố này” | `LocalDateTime` hoặc `LocalDate + LocalTime` **kèm `ZoneId`**, và chính sách DST |

Với lịch một lần theo giờ địa phương trong tương lai, mô hình lưu có thể là:

~~~java
public record ScheduledMeeting(
        LocalDateTime localStart,
        String zoneId,
        Instant calculatedStart,
        String rulesVersion
) {}
~~~

Đây là khai báo record minh họa, cần import `java.time.*`. `localStart` và `zoneId` mô tả **ý định lịch**; `calculatedStart` là instant được tính tại một thời điểm để hệ thống có thể xếp lịch, còn `rulesVersion` giúp truy vết bản quy tắc đã sử dụng. Không phải ứng dụng nào cũng cần cả bốn trường: hãy chọn theo yêu cầu kiểm toán và hành vi khi quy tắc đổi.

Một quy trình đáng tin cậy:

1. **Khi người dùng tạo lịch:** nhận ngày, giờ địa phương, mã vùng IANA và quy tắc giải quyết gap/overlap.
2. **Khi lên lịch thực thi:** tính `Instant` bằng phiên bản tzdb hiện hành, ghi nhận giá trị nếu cần truy vết.
3. **Khi runtime/tzdb được cập nhật:** kiểm tra lại các cuộc hẹn **chưa diễn ra**, đặc biệt ở các vùng nằm trong release notes.
4. **Khi luật làm đổi thời điểm:** xác định theo hợp đồng nên cập nhật instant thực thi, giữ instant cũ, hay yêu cầu người dùng xác nhận.
5. **Khi lịch đã thực thi:** không viết lại `Instant` đã ghi nhận như sự thật lịch sử; nếu cần hiển thị, có thể trình bày theo quy tắc mới hoặc giữ offset thực tế đã lưu theo mục đích kiểm toán.

Riêng **lịch lặp** như “09:00 thứ Hai hằng tuần”, tránh lấy instant lần đầu rồi cộng cố định `Duration.ofDays(7)` cho mọi lần tiếp theo nếu muốn giữ đúng **09:00 địa phương**. Chuyển DST có thể khiến các lần lặp lệch đồng hồ một giờ. Thay vào đó, tạo từng lần lặp từ ngày/giờ địa phương và `ZoneId` theo rules được cập nhật.

## 8. Tzdb được cập nhật qua JDK và có thể khác nhau giữa môi trường

Mỗi JDK/runtime Java phân phối một bộ dữ liệu múi giờ của mình. Việc cập nhật hệ điều hành **không bảo đảm** ngay lập tức cập nhật dữ liệu tzdb mà tiến trình Java đang dùng; cần xem chính bản phân phối JDK, cách đóng gói ứng dụng (container, custom runtime) và tài liệu của nhà cung cấp.

Ví dụ thực tế, IANA phát hành các bộ dữ liệu có phiên bản như `2025b`, `2026a`, `2026e`. Tại thời điểm bài này (24/10/2026), trang IANA ghi `2026e` là bản phát hành ngày 29/09/2026; nhưng ứng dụng **không thể suy ra** rằng mọi JDK cài đặt đều đã dùng đúng phiên bản đó. Các vendor có lịch cập nhật, chính sách backport và cơ chế cập nhật khác nhau.

Java cung cấp API kiểm tra phiên bản do time-zone provider cung cấp:

~~~java
import java.time.zone.ZoneRulesProvider;
import java.util.NavigableMap;
import java.time.zone.ZoneRules;

NavigableMap<String, ZoneRules> versions =
        ZoneRulesProvider.getVersions("America/New_York");

System.out.println(versions.keySet());
System.out.println(versions.lastKey());
~~~

Đây là đoạn minh họa thực thi trong một phương thức. Đầu ra tùy thuộc runtime: ví dụ một JDK được kiểm tra có thể in `[2025b]`. **Không hard-code `2025b` hay `2026e` làm giá trị mong đợi**, vì các bản JDK khác nhau có thể trả phiên bản khác nhau; provider tùy chỉnh còn có cách đặt phiên bản riêng. `getVersions` trả các phiên bản khả dụng **trong provider hiện đang chạy**, không bảo đảm lưu toàn bộ lịch sử mọi release IANA.

Ở Java, `ZoneId.getRules()` cung cấp `ZoneRules` đã được tải cho vùng. Đừng cho rằng một đối tượng `ZoneRules` đang giữ hoặc một tiến trình chạy lâu sẽ tự cập nhật tức thì nếu image JDK/dữ liệu nền được thay đổi bên ngoài. Phần lớn ứng dụng nên nâng cấp và triển khai lại bằng runtime đã được xác minh khi cần thay đổi tzdb.

Nguồn chính thức: [Oracle – Timezone Data Versions in the Java Runtime](https://ops.java/tzdata/), [Oracle – Timezone Updater Tool](https://www.oracle.com/java/technologies/javase/tzupdater-readme.html).

## 9. Khám phá quy tắc ZoneRules qua API

Các API quan trọng và ý nghĩa:

| API | Tác dụng | Cần lưu ý |
| --- | --- | --- |
| `zone.getRules()` | Lấy bộ quy tắc cho `ZoneId` | Phụ thuộc provider/runtime |
| `rules.getOffset(instant)` | Lấy offset đúng tại một instant | Không mơ hồ khi có `Instant` |
| `rules.getValidOffsets(localDateTime)` | Lấy 0, 1 hoặc 2 offset hợp lệ ở giờ địa phương | Phát hiện gap/overlap |
| `rules.getTransition(localDateTime)` | Lấy lần chuyển giờ liên quan đến gap/overlap | Có thể trả `null` ở giờ thường |
| `rules.nextTransition(instant)` | Tìm lần chuyển offset tiếp theo | Có thể `null` nếu không còn lần chuyển |
| `rules.previousTransition(instant)` | Tìm lần chuyển offset trước đó | Có thể `null` |
| `rules.getTransitions()` | Danh sách transition đã định nghĩa đầy đủ | Không nhất thiết chứa vô hạn chuyển đổi tương lai |
| `rules.getTransitionRules()` | Các quy tắc dùng để sinh chuyển đổi về sau | Có thể là danh sách trống |
| `rules.isFixedOffset()` | Kiểm tra bộ rules có offset bất biến hay không | Không thay cho việc xem lịch sử/nguồn dữ liệu |
| `ZoneRulesProvider.getVersions(zoneId)` | Tra phiên bản quy tắc provider cung cấp | Phiên bản phụ thuộc runtime/vendor |

**Đừng** hiểu `getTransitions()` là toàn bộ các lần đổi giờ đã và sẽ xảy ra cho tới vô hạn. Khi vùng dùng quy tắc DST lặp lại vào tương lai, Java còn có `getTransitionRules()` để mô tả thuật toán chuyển đổi ở các năm tiếp theo. Ngay cả thuật toán ấy cũng chỉ là dự đoán theo dữ liệu phiên bản hiện tại.

Ví dụ kiểm tra gap/overlap trước khi lưu cuộc hẹn:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime requested = LocalDateTime.of(2025, 11, 2, 1, 30);
List<ZoneOffset> candidates =
        zone.getRules().getValidOffsets(requested);

if (candidates.size() == 0) {
    throw new IllegalArgumentException("Giờ địa phương không tồn tại");
} else if (candidates.size() == 2) {
    // Yêu cầu chọn offset hoặc dùng chính sách nghiệp vụ rõ ràng.
} else {
    Instant start = requested.toInstant(candidates.get(0));
    // start là thời điểm tuyệt đối duy nhất theo offset đã chọn.
}
~~~

Đây là mã minh họa trong một phương thức có các import `java.time.*` và `java.util.List`. Với vùng có lịch sử chuyển đổi phức tạp, hãy để API tính tập offset hợp lệ thay vì tự cộng trừ một giờ. Việc kiểm tra ở thời điểm nhập liệu vẫn cần được xem xét lại nếu quy tắc thay đổi trước khi sự kiện diễn ra.

## 10. Thử nghiệm khi tzdb thay đổi và quản lý lịch dài hạn

Để tránh lỗi chỉ xuất hiện ở production, nên kiểm tra trên dữ liệu xác định và các múi giờ có quy tắc khác nhau:

- **Mốc lịch sử:** tra cùng một vùng ở hai giai đoạn đã từng thay offset, ví dụ `Asia/Kathmandu` năm 1985 và 1986.
- **DST gap:** `America/New_York` ngày 09/03/2025 lúc 02:30 có 0 offset hợp lệ theo dữ liệu được dùng trong ví dụ.
- **DST overlap:** `America/New_York` ngày 02/11/2025 lúc 01:30 có 2 offset hợp lệ.
- **Đổi ngày cực đoan:** `Pacific/Apia` có ngày 30/12/2011 bị bỏ qua.
- **Sự kiện tương lai:** kiểm tra lại lịch đã lên trước/sau khi nâng cấp JDK/tzdb, đánh giá chênh lệch `Instant` được tính.
- **Nhiều môi trường:** đọc và ghi nhận phiên bản tzdb từ mỗi instance; so sánh kết quả trên local, CI, container và production.
- **Không mặc định 24 giờ/ngày địa phương:** nếu truy vấn dữ liệu cho một ngày theo zone, xác định đầu ngày và đầu ngày tiếp theo bằng `LocalDate.atStartOfDay(zone)` rồi dùng khoảng nửa kín `[start, end)`.

Một ngày lịch ở vùng có DST có thể dài 23 hoặc 25 giờ; trong sự kiện đổi ngày hiếm gặp, thậm chí có ngày bị bỏ qua. Bởi vậy, tính "đầu ngày tiếp theo = đầu ngày hôm nay + 86.400 giây" **không luôn đúng** với ý nghĩa ngày lịch địa phương. Cách xác định hai ranh giới qua `ZoneRules` của zone cụ thể an toàn hơn.

Khi tích hợp với hệ thống bên ngoài, một số nền tảng dùng dữ liệu vùng từ hệ điều hành, ICU, thư viện ứng dụng hay cơ sở dữ liệu riêng. Hai dịch vụ có thể **khác phiên bản quy tắc** dù đều sử dụng cùng tên `Europe/London` hoặc `America/New_York`. Hãy xác định ai chịu trách nhiệm chuyển local time sang instant, và chuẩn hóa trao đổi timestamp tuyệt đối bằng ISO-8601/UTC khi đó là dữ liệu sự kiện đã xác định.

## 11. Những nhầm lẫn phổ biến

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| “`ZoneId` luôn có đúng một offset.” | Đổi sai lịch sử và DST | Zone chứa rules biến đổi theo thời gian |
| “`ZoneOffset.ofHours(-5)` tương đương `America/New_York`.” | Sai vào mùa hè và giai đoạn lịch sử khác | Offset cố định không chứa luật DST |
| “Luật DST hiện tại cũng đúng cho năm 1950.” | Sai timestamp lịch sử | Tra `getOffset(instant)` trên tzdb có phiên bản phù hợp |
| “Bản cập nhật tzdb chỉ sửa tương lai.” | Không tái hiện được một số kết quả lịch sử | Tzdb có thể sửa cả dữ liệu cũ |
| “Tính trước instant cho lịch năm 2030 là vĩnh viễn đúng với 09:00 địa phương.” | Lịch lệch nếu quốc gia đổi luật | Lưu ý định local + `ZoneId` và chính sách cập nhật |
| “`Instant` đổi khi múi giờ bị cập nhật.” | Nhầm điểm thời gian với cách hiển thị | Instant giữ nguyên; local time từ zone có thể đổi |
| “`getTransitions()` liệt kê mọi lần chuyển tương lai.” | Bỏ sót quy tắc lặp lại | Xem thêm `getTransitionRules()` |
| “JDK và hệ điều hành chắc chắn có cùng tzdb.” | Kết quả khác giữa các dịch vụ | Kiểm tra thực tế runtime/provider |
| “LocalDateTime ở gap luôn tự báo lỗi.” | Vô tình dời lịch mà không biết | Kiểm tra `getValidOffsets()` và chọn chính sách |
| “Chỉ lưu offset là đủ cho lịch lặp.” | Mất quy tắc mùa/historical changes | Lưu `ZoneId` của vùng |
| “Tzdb là bản lịch sử chính xác tuyệt đối cho mọi thời kỳ.” | Sai dữ liệu thời gian xa xưa | Chú ý độ bao phủ, đặc biệt trước 1970 |

## 12. Bài tập tự kiểm tra

**Câu 1.** Tại sao `ZoneOffset.ofHours(-5)` không thay thế `ZoneId.of("America/New_York")` cho một lịch họp hằng tháng?

**Đáp án:** Offset `-05:00` cố định; New York có giai đoạn dùng `-04:00` và có thể thay đổi luật DST. Lịch địa phương cần quy tắc theo ngày, không chỉ một số lệch UTC.

**Câu 2.** Một sự kiện đã xảy ra được lưu bằng `Instant`. Khi cài tzdb mới sửa dữ liệu lịch sử, điều gì có thể khác?

**Đáp án:** `Instant` của sự kiện không đổi. Giờ địa phương hiển thị bằng `instant.atZone(zone)` có thể thay đổi nếu offset tương ứng của zone được hiệu chỉnh.

**Câu 3.** `getValidOffsets(LocalDateTime)` trả danh sách rỗng có nghĩa gì?

**Đáp án:** Giờ địa phương ấy không tồn tại theo rules của zone (gap). Không nên tự chọn offset ngẫu nhiên để tạo một instant.

**Câu 4.** Một cuộc hẹn trong tương lai cần giữ **09:00 theo đồng hồ thành phố** khi luật múi giờ đổi. Chỉ lưu `Instant` đã tính là đủ không?

**Đáp án:** Không đủ để giữ ý định giờ dân sự. Cần lưu `LocalDateTime`/ngày giờ gốc và `ZoneId`; sau cập nhật tzdb phải xem xét tính lại instant thực thi theo chính sách.

**Câu 5.** Có phải phiên bản tzdb mới luôn tồn tại trong mọi bản JDK sau khi IANA công bố release không?

**Đáp án:** Không. Phiên bản được phân phối theo vendor và bản cập nhật runtime. Có thể dùng `ZoneRulesProvider.getVersions(zoneId)` để kiểm tra các phiên bản provider hiện có.

**Câu 6.** Tại sao ngày 30/12/2011 vẫn tạo được bằng `LocalDate.of(...)` nhưng không có giờ 12:00 hợp lệ ở `Pacific/Apia` theo rules đã trình bày?

**Đáp án:** `LocalDate` chỉ xét lịch ISO; lịch dân sự địa phương tại Apia đã nhảy qua ngày đó khi đổi phía đường đổi ngày. Muốn biết ngày giờ có tồn tại tại một địa điểm, cần áp `ZoneRules`.

## 13. Nguồn tham khảo

- [IANA Time Zone Database](https://www.iana.org/time-zones): danh sách phiên bản và tổng quan dữ liệu vùng.
- [IANA Theory and Pragmatics](https://www.iana.org/time-zones/theory): phạm vi lịch sử, độ tin cậy và dự đoán thời gian dân sự trong tương lai.
- [IANA Release History](https://www.iana.org/time-zones/releases): thay đổi từng phiên bản, bao gồm chỉnh sửa quá khứ và luật tương lai.
- [Java ZoneRules API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html): `getOffset`, `getValidOffsets`, `getTransitions`, `getTransitionRules`.
- [Java ZoneRulesProvider API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRulesProvider.html): phiên bản rules từ provider.
- [Oracle Timezone Data Versions](https://ops.java/tzdata/): ánh xạ cập nhật tzdata vào các bản JDK.

**Ghi nhớ:** `ZoneId` biểu diễn **quy tắc giờ địa phương theo thời gian**, không phải một offset bất biến. Tzdb chứa lịch sử được biết và giả định về tương lai; cả hai có thể được hiệu chỉnh. Hãy **lưu `Instant` cho những sự kiện tuyệt đối**, lưu **ngày giờ địa phương + `ZoneId` cho ý định lịch dân sự**, và kiểm tra tác động khi nâng cấp dữ liệu múi giờ.