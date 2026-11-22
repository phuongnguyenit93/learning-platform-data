# ZoneId biểu diễn múi giờ theo vùng trong Java

## 1. ZoneId là gì và giải quyết vấn đề nào?

`java.time.ZoneId` là kiểu dữ liệu của Java Date-Time API (`java.base`) dùng để **định danh một múi giờ**. Khi chọn tên vùng như `Asia/Ho_Chi_Minh`, `America/New_York` hay `Europe/Paris`, bạn đang chọn **bộ quy tắc quy đổi giữa thời điểm tuyệt đối (Instant) và ngày/giờ trên đồng hồ địa phương**. Những quy tắc này bao gồm độ lệch UTC ở các giai đoạn khác nhau, các lần chuyển giờ mùa hè (Daylight Saving Time, DST) nếu có và những thay đổi do luật địa phương.

Ví dụ cùng một sự kiện `2026-07-01T12:00:00Z`:

- Tại `Asia/Ho_Chi_Minh`, đồng hồ hiển thị **19:00 ngày 01/07/2026**, offset `+07:00`.
- Tại `America/New_York`, đồng hồ hiển thị **08:00 ngày 01/07/2026**, offset `-04:00` vào mùa hè.
- Tại `Europe/Paris`, đồng hồ hiển thị **14:00 ngày 01/07/2026**, offset `+02:00` vào mùa hè.

Ba giờ địa phương khác nhau nhưng **chỉ có một Instant**. Ngược lại, một giờ địa phương như `09:30 ngày 01/07/2026` chưa phải thời điểm toàn cầu duy nhất nếu chưa biết vùng/offset.

**Mục tiêu sau bài học:** tạo được `ZoneId` vùng, phân biệt với `ZoneOffset`, tra `ZoneRules`, chuyển từ `Instant` hoặc `LocalDateTime` qua vùng, xử lý DST gap/overlap, chọn kiểu lưu trữ đúng và kiểm thử không phụ thuộc cấu hình timezone của máy.

### Ba lớp khái niệm

| Thành phần | Đại diện cho | Ví dụ | Điều chưa nói |
| --- | --- | --- | --- |
| `LocalDateTime` | Ngày và giờ trên đồng hồ, chưa có zone/offset | `2026-07-01T09:30` | Không biết chính xác Instant |
| `ZoneId` dạng vùng | Danh tính múi giờ và quy tắc thay đổi offset | `America/New_York` | Không tự biểu diễn một thời điểm |
| `ZoneOffset` | Độ lệch so với UTC tại một thời điểm, không có lịch DST | `-04:00` | Không nói tên vùng, luật offset mùa khác |
| `ZonedDateTime` | Ngày/giờ địa phương kết hợp ZoneId và offset đã giải quyết | `2026-07-01T09:30-04:00[America/New_York]` | Đã có đủ dữ liệu để ra Instant |
| `Instant` | Một mốc duy nhất trên dòng thời gian | `2026-07-01T13:30:00Z` | Không lưu timezone hiển thị |

**ZoneId biểu diễn múi giờ theo vùng**, nghĩa là danh tính vùng bền vững theo ứng dụng (ví dụ lịch họp phải luôn lúc 09:00 “ở New York”). Múi giờ theo vùng có thể đổi offset từ mùa đông sang mùa hè; do đó không nên thay zone ID bằng offset lấy tại một ngày bất kỳ.

## 2. Tạo và nhận diện ZoneId

### 2.1. Tạo từ tên vùng IANA

```java
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId tokyo = ZoneId.of("Asia/Tokyo");
ZoneId newYork = ZoneId.of("America/New_York");
ZoneId paris = ZoneId.of("Europe/Paris");
```

Các giá trị như `Asia/Ho_Chi_Minh` là **region-based zone IDs** thông dụng của cơ sở dữ liệu IANA. Đó là những giá trị bạn nên lưu khi người dùng chọn khu vực theo địa điểm. Cú pháp `Region/City` thể hiện ID, không có nghĩa múi giờ áp dụng đúng ranh giới thành phố hành chính; một vùng có thể bao phủ nhiều địa điểm.

`ZoneId.of(id)` kiểm tra cú pháp và tồn tại của zone; với ID không hỗ trợ có thể ném `DateTimeException` hoặc lớp con như `ZoneRulesException`. Các zone có sẵn phụ thuộc tzdb của runtime; đừng giả định mọi ID trong danh sách trên Internet đều được runtime hiện tại hỗ trợ.

```java
import java.time.DateTimeException;
import java.time.ZoneId;

try {
    ZoneId selected = ZoneId.of("No/Such_Zone");
} catch (DateTimeException ex) {
    System.out.println("Múi giờ không được hỗ trợ");
}
```

Đây là **snippet đặt trong method**, chưa phải tệp chạy độc lập. Ứng dụng nên giới hạn/sửa lỗi zone ID tại đầu vào thay vì âm thầm chọn zone mặc định. Đối với API, có thể trả HTTP 400 kèm tên trường không hợp lệ.

### 2.2. Các dạng ID mà `ZoneId.of` chấp nhận

Java phân biệt các nhóm ID:

1. **Region-based:** `Asia/Ho_Chi_Minh`, `America/New_York`; quy tắc offset có thể biến đổi theo năm, ngày.
2. **Offset-based ID:** `+07:00` hoặc `-04:00`; `ZoneId.of("+07:00")` tạo một `ZoneOffset` là subtype của `ZoneId`. Đây là offset cố định, **không phải lịch sử một vùng**.
3. **Prefix UTC/GMT/UT:** `UTC`, `GMT`, `UTC+07:00`, `GMT-05:00`; chúng mô tả zone ID có offset cố định sau tiền tố, không cung cấp lịch DST của một vùng như New York.

`ZoneId.of("UTC")` có bộ quy tắc cố định UTC; `ZoneId.of("UTC+07:00")` là ID có quy tắc offset +07 cố định. Điều này **không đồng nghĩa** với `ZoneId.of("Asia/Ho_Chi_Minh")` về lịch sử hoặc ngữ nghĩa định danh vùng.

Một số tên ngắn có thể dùng qua `ZoneId.SHORT_IDS` kết hợp overload `ZoneId.of(shortId, ZoneId.SHORT_IDS)`; chúng có thể mơ hồ, thuộc cơ chế tương thích và có cách ánh xạ không giống kỳ vọng toàn cầu. Ưu tiên ID IANA đầy đủ cho dữ liệu liên vùng.

### 2.3. Đọc ID, lấy danh sách, hiển thị tên

```java
import java.time.ZoneId;
import java.time.format.TextStyle;
import java.util.Locale;
import java.util.Set;

ZoneId zone = ZoneId.of("America/New_York");
String stableId = zone.getId(); // "America/New_York"
String display = zone.getDisplayName(TextStyle.FULL, Locale.ENGLISH);
Set<String> available = ZoneId.getAvailableZoneIds();
boolean supported = available.contains("America/New_York");
```

- `getId()` dùng cho cấu hình, persistence, JSON và so sánh zone ID khi cần bảo toàn danh tính vùng.
- `getDisplayName(style, locale)` dùng trong UI; tên được địa phương hóa hoặc có thể fallback, **không nên lưu làm định danh kỹ thuật**.
- `getAvailableZoneIds()` trả các ID theo vùng có sẵn trong runtime (dữ liệu snapshot của phiên bản hiện hành). Dùng cho danh sách tìm kiếm/chọn múi giờ, có thể thêm friendly labels từ UI.
- `equals` dùng để so sánh ZoneId theo giá trị. Hai ID/alias khác nhau có thể phản ánh quy tắc tương đương ở một số giai đoạn nhưng `equals` không tự coi chúng là cùng ID.
- `normalized()` có thể trả về `ZoneOffset` nếu quy tắc hoàn toàn cố định; không dùng để thay mọi vùng bằng offset vì làm mất ngữ cảnh vùng.

## 3. ZoneId khác ZoneOffset như thế nào?

Điểm khác biệt lớn nhất: **ZoneId vùng xác định quy tắc theo thời gian**, còn **ZoneOffset chỉ là một số độ lệch cụ thể**.

Với `America/New_York`, năm 2026 thường có:

| Thời điểm kiểm tra (UTC) | Offset vùng New York | Giải thích |
| --- | --- | --- |
| `2026-01-15T12:00:00Z` | `-05:00` | Giờ chuẩn mùa đông |
| `2026-07-15T12:00:00Z` | `-04:00` | Giờ mùa hè (DST) |
| `2026-11-15T12:00:00Z` | `-05:00` | Đã chuyển lại giờ chuẩn |

`ZoneOffset.of("-05:00")` giữ **-05:00 cả năm**, vì nó không tra thông tin DST. Nếu lịch là “09:00 mỗi thứ Hai tại New York”, phải lưu `ZoneId.of("America/New_York")` để lần chạy vào mùa hè vẫn xảy ra lúc 09:00 giờ địa phương. Nếu chỉ lưu `-05:00`, lịch sẽ chạy lúc 10:00 theo đồng hồ New York ở những ngày có DST.

```java
import java.time.*;

ZoneId ny = ZoneId.of("America/New_York");

ZoneOffset winterOffset =
        ny.getRules().getOffset(Instant.parse("2026-01-15T12:00:00Z"));
// -05:00

ZoneOffset summerOffset =
        ny.getRules().getOffset(Instant.parse("2026-07-15T12:00:00Z"));
// -04:00
```

`ZoneOffset` bản thân kế thừa `ZoneId` nhưng không mang thay đổi offset theo vùng. Một `ZoneId` dạng vùng cũng có thể có quy tắc cố định ở giai đoạn hiện tại; **không kết luận vùng đó không có lịch sử thay đổi**. Ví dụ các vùng khác nhau có thể cùng offset hôm nay nhưng lịch sử, pháp lý hoặc quy tắc tương lai khác nhau.

### So sánh vùng và offset trong một bài toán đặt lịch

Người dùng yêu cầu: “Hẹn 09:30 ngày 01/07/2026 **ở New York**”.

- Có **`LocalDateTime` + `ZoneId("America/New_York")`** → Java áp dụng offset hợp lệ theo ngày: `-04:00`; instant là `2026-07-01T13:30:00Z`.
- Có **`LocalDateTime` + `ZoneOffset("-05:00")`** → Java tính tức thì `2026-07-01T14:30:00Z`, nhưng sai với giờ 09:30 ở New York vào ngày đó.
- Có **`Instant` cho sự kiện đã chốt** → có thể hiển thị ở bất kỳ vùng nào, không cần giữ một offset cũ làm offset vĩnh viễn.

## 4. ZoneRules: nơi ZoneId lấy quy tắc

Mỗi `ZoneId` cho phép truy xuất quy tắc qua `zone.getRules()`, trả một `java.time.zone.ZoneRules`. Quy tắc này quyết định offset dựa trên mốc tuyệt đối hoặc các offset khả dĩ khi đầu vào là ngày giờ địa phương.

Một số method quan trọng:

| API | Input | Kết quả / ý nghĩa |
| --- | --- | --- |
| `getOffset(Instant)` | Một mốc UTC đã xác định | Một `ZoneOffset` đúng với mốc đó |
| `getValidOffsets(LocalDateTime)` | Ngày giờ đồng hồ địa phương | Danh sách offset hợp lệ (thường 0, 1 hoặc 2) |
| `getTransition(LocalDateTime)` | Ngày giờ địa phương ở vùng chuyển giờ | `ZoneOffsetTransition` nếu trong gap/overlap; `null` nếu bình thường |
| `isValidOffset(local, offset)` | Ngày giờ local và offset | Kiểm tra offset có hợp lệ tại giờ ấy không |
| `isFixedOffset()` | Không cần input | `true` nếu bộ quy tắc chỉ có một offset cố định |
| `nextTransition(Instant)` | Instant | Lần chuyển offset tiếp theo, nếu tồn tại |
| `previousTransition(Instant)` | Instant | Lần chuyển offset trước đó, nếu tồn tại |

**Cách đọc đúng:** `getOffset(instant)` luôn trả offset duy nhất vì mốc UTC đã xác định. Ngược lại, từ một `LocalDateTime` có thể chưa suy ra offset duy nhất; để kiểm tra tình huống bất thường hãy dùng `getValidOffsets(local)`. Overload `getOffset(LocalDateTime)` có chính sách chọn giá trị khi gap/overlap; **đừng dùng nó để xác thực input local một cách nghiêm ngặt**.

### 4.1. Truy cập quy tắc một cách tường minh

```java
import java.time.*;
import java.time.zone.ZoneRules;

ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();

ZoneOffset winter = rules.getOffset(
        Instant.parse("2026-01-15T12:00:00Z"));
ZoneOffset summer = rules.getOffset(
        Instant.parse("2026-07-15T12:00:00Z"));

boolean fixed = rules.isFixedOffset(); // false với vùng New York
```

`ZoneRules` được thiết kế để tái sử dụng trong các tác vụ tra cứu; các kiểu java.time chủ yếu immutable và thread-safe. Các quy tắc vùng có thể thay đổi giữa **các phiên bản tzdb/JDK**. Nếu ứng dụng tạo lịch xa trong tương lai, đừng cố định giả định rằng mọi quốc gia sẽ giữ nguyên luật hiện tại.

## 5. Chuyển Instant thành giờ địa phương theo vùng

Khi bạn **đã có Instant**, quy tắc chuyển đổi rõ ràng: vùng sẽ quyết định cách trình bày ngày giờ local. Một Instant có thể hiển thị khác ngày giữa hai quốc gia nhưng vẫn giữ mốc gốc.

```java
import java.time.*;

Instant event = Instant.parse("2026-07-01T02:30:00Z");
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime hcmView = event.atZone(hcm);
// 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]

ZonedDateTime nyView = event.atZone(ny);
// 2026-06-30T22:30-04:00[America/New_York]

boolean same = hcmView.toInstant().equals(nyView.toInstant()); // true
```

Ở đây 09:30 ngày 01/07 tại TP.HCM chính là 22:30 **ngày 30/06** tại New York. Cần hiển thị cả ngày cùng giờ nếu người dùng có thể nằm tại vùng khác, vì ngày có thể thay đổi khi chuyển vùng.

Có hai API trên `ZonedDateTime` dễ nhầm:

- `withZoneSameInstant(targetZone)`: giữ **cùng Instant**, chỉ đổi bản hiển thị.
- `withZoneSameLocal(targetZone)`: cố giữ **cùng con số ngày giờ local**, dùng zone mới để giải quyết offset, tức mốc UTC thường thay đổi.

Ví dụ cuộc họp `09:30 TP.HCM` chuyển **same instant** sang New York thành `22:30 ngày hôm trước`; chuyển **same local** sẽ là `09:30 New York` và một mốc UTC khác. Với lịch họp toàn cầu, gần như luôn cần `withZoneSameInstant`.

## 6. Ghép LocalDateTime với ZoneId: tạo thời điểm

`LocalDateTime` có ngày và giờ nhưng **không có múi giờ**. `LocalDateTime.atZone(zone)` hoặc `ZonedDateTime.of(local, zone)` tra quy tắc vùng để tạo `ZonedDateTime`.

```java
import java.time.*;

LocalDateTime local = LocalDateTime.of(2026, 7, 1, 9, 30);
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(hcm);
// 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]

Instant exactMoment = zoned.toInstant();
// 2026-07-01T02:30:00Z
```

Với thời gian thông thường, phép chuyển này đơn giản. Nhưng phải hiểu rằng **gap** và **overlap** gây ra tình huống đặc biệt:

- **Gap:** local date-time không xảy ra, Java mặc định dời local time sang sau gap theo độ dài của gap.
- **Overlap:** cùng local date-time xảy ra hai lần với hai offset, Java mặc định chọn offset trước/sớm hơn, thường là offset mùa hè.
- **Thời gian bình thường:** đúng một offset hợp lệ.

Nếu nghiệp vụ nghiêm ngặt (vé tàu, lịch khám, thanh toán theo giờ, đặt lịch chính xác), hãy kiểm tra trước khi dùng `atZone`. Việc Java tự dời hoặc chọn offset mặc định có thể trái mong đợi người dùng.

## 7. Daylight Saving Time (DST): gap và overlap

### 7.1. Gap: một số giờ địa phương không tồn tại

Tại `America/New_York` ngày **08/03/2026**, đồng hồ nhảy từ `01:59:59` lên `03:00`. `2026-03-08T02:30` vì vậy **không có offset hợp lệ**.

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(2026, 3, 8, 2, 30);

int count = ny.getRules().getValidOffsets(missing).size(); // 0
ZonedDateTime adjusted = missing.atZone(ny);
// 2026-03-08T03:30-04:00[America/New_York]
```

Đây là ví dụ cho hành vi mặc định của `atZone`: tự đẩy 02:30 lên 03:30 theo độ dài gap. Chương trình nhắc việc có thể quyết định dịch lịch, còn hệ thống đặt chỗ chính xác có thể phải trả lỗi và yêu cầu người dùng chọn lại giờ.

### 7.2. Overlap: cùng giờ xuất hiện hai lần

Tại `America/New_York` ngày **01/11/2026**, đồng hồ lùi và giờ `01:30` xảy ra **hai lần**:

| Giờ địa phương | Offset hợp lệ | Instant |
| --- | --- | --- |
| `2026-11-01T01:30` | `-04:00` (lần trước) | `2026-11-01T05:30:00Z` |
| `2026-11-01T01:30` | `-05:00` (lần sau) | `2026-11-01T06:30:00Z` |

Hai Instant khác nhau 60 phút thực. `LocalDateTime` và `ZoneId` **một mình chưa đủ** để biết người dùng muốn lần nào. `getValidOffsets` trả hai offset trong thứ tự sớm rồi muộn.

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime repeated = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneRules rules = ny.getRules();

List<ZoneOffset> choices = rules.getValidOffsets(repeated);
// [-04:00, -05:00]

ZonedDateTime first = ZonedDateTime.ofStrict(repeated, choices.get(0), ny);
ZonedDateTime second = ZonedDateTime.ofStrict(repeated, choices.get(1), ny);
```

`first.toInstant()` là `2026-11-01T05:30:00Z`; `second.toInstant()` là `2026-11-01T06:30:00Z`. `ZonedDateTime.ofStrict(local, chosenOffset, zone)` bảo đảm offset thuộc danh sách hợp lệ, nếu sai sẽ ném `DateTimeException`.

### 7.3. Quy tắc xử lý rõ ràng cho ứng dụng

Trình tự đáng tin cho **LocalDateTime + ZoneId**:

1. Đọc `rules = zone.getRules()`.
2. Lấy `options = rules.getValidOffsets(local)`.
3. Nếu danh sách **rỗng**, trả lỗi hoặc dời lịch theo policy **được định nghĩa trước**; không âm thầm tự sửa giờ khi cần độ chính xác.
4. Nếu danh sách **hai phần tử**, yêu cầu chọn lần đầu/lần sau hoặc dùng một policy rõ ràng.
5. Nếu **một phần tử**, dùng offset đó.
6. Cuối cùng tạo `ZonedDateTime.ofStrict(local, chosen, zone)` và gọi `toInstant()`.

Với thời gian bình thường, `atZone` tiện hơn. Cần hiểu `getValidOffsets` cho câu hỏi local time; muốn xác định offset của **Instant đã biết**, dùng `getOffset(instant)`.

**Không có một chính sách DST đúng cho mọi sản phẩm.** Với lịch chạy tự động, “dời sang giờ hợp lệ gần nhất” có thể hợp lý; với chốt sổ ngân hàng hoặc đặt tàu, yêu cầu người dùng quyết định có thể an toàn hơn.

## 8. Chương trình Java 17+ chạy được: ZoneId theo vùng

Ví dụ tổng hợp dưới đây biểu diễn các việc thường gặp: đọc zone ID, cùng một Instant ở hai vùng, offset mùa đông/mùa hè, gap/overlap, offset cố định. Dữ liệu ngày giờ cố định nên kết quả không phụ thuộc đồng hồ hiện tại.

Tạo tệp **`ZoneIdRegionDemo.java`** với nội dung:

```java
import java.time.*;
import java.time.format.TextStyle;
import java.time.zone.ZoneRules;
import java.util.List;
import java.util.Locale;

public class ZoneIdRegionDemo {
    public static void main(String[] args) {
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");
        LocalDateTime local = LocalDateTime.of(2026, 7, 1, 9, 30);

        ZonedDateTime inHcm = local.atZone(hcm);
        Instant instant = inHcm.toInstant();
        ZonedDateTime inNewYork = instant.atZone(newYork);

        System.out.println("Zone ID: " + hcm.getId());
        System.out.println("HCM: " + inHcm);
        System.out.println("Instant: " + instant);
        System.out.println("New York: " + inNewYork);
        System.out.println("Same instant: " + inNewYork.toInstant().equals(instant));

        ZoneRules rules = newYork.getRules();
        System.out.println("NY winter offset: " +
                rules.getOffset(Instant.parse("2026-01-15T12:00:00Z")));
        System.out.println("NY summer offset: " +
                rules.getOffset(Instant.parse("2026-07-15T12:00:00Z")));

        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
        List<ZoneOffset> choices = rules.getValidOffsets(overlap);
        System.out.println("Gap valid offsets: " + rules.getValidOffsets(gap).size());
        System.out.println("Gap atZone default: " + gap.atZone(newYork));
        System.out.println("Overlap valid offsets: " + choices);
        System.out.println("Overlap early UTC: " +
                ZonedDateTime.ofStrict(overlap, choices.get(0), newYork).toInstant());
        System.out.println("Overlap late UTC: " +
                ZonedDateTime.ofStrict(overlap, choices.get(1), newYork).toInstant());

        System.out.println("Fixed offset zone: " +
                ZoneId.of("+07:00").getRules().isFixedOffset());
        System.out.println("NY fixed offset: " + rules.isFixedOffset());
    }
}
```

Lưu file đúng tên class. Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ZoneIdRegionDemo.java
java ZoneIdRegionDemo
```

Kết quả stdout chính xác khi dùng quy tắc tzdb cho các ngày New York năm 2026:

```text
Zone ID: Asia/Ho_Chi_Minh
HCM: 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]
Instant: 2026-07-01T02:30:00Z
New York: 2026-06-30T22:30-04:00[America/New_York]
Same instant: true
NY winter offset: -05:00
NY summer offset: -04:00
Gap valid offsets: 0
Gap atZone default: 2026-03-08T03:30-04:00[America/New_York]
Overlap valid offsets: [-04:00, -05:00]
Overlap early UTC: 2026-11-01T05:30:00Z
Overlap late UTC: 2026-11-01T06:30:00Z
Fixed offset zone: true
NY fixed offset: false
```

Ý nghĩa các kết quả:

- Một sự kiện ở TP.HCM ngày 01/07 lúc 09:30 tương ứng **22:30 ngày hôm trước** tại New York, nhưng `toInstant()` không thay đổi.
- New York không có một offset duy nhất suốt năm: `-05:00` mùa đông, `-04:00` mùa hè.
- `getValidOffsets` cho gap không có offset; cho overlap có hai offset hợp lệ. Hai lần 01:30 trùng giờ hiển thị nhưng khác mốc UTC.
- `ZoneId.of("+07:00")` có quy tắc cố định, còn vùng `America/New_York` có quy tắc chuyển giờ; `isFixedOffset()` thể hiện sự khác nhau.

Ví dụ không sử dụng `ZoneId.systemDefault()` để tránh thay đổi output theo cấu hình máy. Quy tắc múi giờ của các vùng có thể được cập nhật trong tzdb; khi bảo trì hệ thống lâu dài, nên kiểm thử lại những kỳ vọng cho lịch tương lai.

## 9. Múi giờ mặc định, Clock và phụ thuộc môi trường

### 9.1. `ZoneId.systemDefault()`

`ZoneId.systemDefault()` trả timezone mặc định của JVM/host ở thời điểm gọi. Nó có thể khác giữa laptop, Docker, server, CI hoặc phiên bản cấu hình. Không nên ngầm dựa vào nó khi nghiệp vụ có zone xác định.

```java
import java.time.*;

ZoneId machineZone = ZoneId.systemDefault();
ZonedDateTime nowMachine = ZonedDateTime.now();
ZonedDateTime nowTokyo = ZonedDateTime.now(ZoneId.of("Asia/Tokyo"));
```

Hai lệnh `now` đọc **thời điểm hiện tại** nhưng trình bày theo zone tương ứng. `nowMachine` thay đổi theo runtime; `nowTokyo` có vùng tường minh. Nếu sau đó chỉ lấy `toLocalDateTime()`, bạn đã bỏ thông tin zone.

Trong hệ thống nhiều khách hàng, hãy đọc timezone từ cấu hình của chính tenant/người dùng hoặc vùng nơi sự kiện diễn ra; không suy ra từ locale hoặc địa chỉ IP.

### 9.2. Tiêm Clock để test ổn định

`Clock` nằm trong `java.time`, cho phép tách truy vấn thời gian hiện tại khỏi code nghiệp vụ:

```java
import java.time.*;

Clock fixed = Clock.fixed(
        Instant.parse("2026-07-01T02:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime captured = ZonedDateTime.now(fixed);
// 2026-07-01T09:30+07:00[Asia/Ho_Chi_Minh]
```

`Clock.fixed` giúp test ổn định trên mọi máy. Khi cần test logic đổi vùng, truyền `Clock.system(businessZone)` ở production, `Clock.fixed(...)` ở test. Zone ID của Clock chỉ ảnh hưởng cách tạo ngày/giờ local bằng API đọc Clock; instant cố định vẫn là mốc tuyệt đối như nhau.

### 9.3. Kiểm tra tính hợp lệ của zone từ user

Một cấu hình ví dụ:

```json
{
  "userTimeZone": "America/New_York",
  "reminderLocalTime": "09:00"
}
```

Nên parse `ZoneId.of(userTimeZone)` với xử lý exception; lưu `getId()` để giữ vùng. Khi tính lần nhắc kế tiếp, lấy **ngày local theo vùng** rồi ghép với `LocalTime`, áp dụng `ZoneRules` để xác định offset hợp lệ. Đừng lưu `-05:00` nếu người dùng yêu cầu “09:00 New York” suốt cả năm.

## 10. Thiết kế lưu trữ và truyền API

Một ứng dụng nên phân biệt **mốc sự kiện tuyệt đối** với **quy tắc theo giờ địa phương**.

| Nhu cầu | Dữ liệu nên lưu | Lý do |
| --- | --- | --- |
| Log/createAt/updateAt | `Instant` | Sắp xếp và so sánh trên một timeline |
| Lịch hẹn một lần đã chốt | `Instant` và `ZoneId` tổ chức nếu cần | Giữ mốc, đồng thời biết vùng gốc |
| Nhắc việc mỗi ngày lúc 09:00 trong vùng | `LocalTime` + `ZoneId` + quy tắc nhắc | Offset có thể thay đổi theo mùa |
| Lịch họp định kỳ thứ Hai lúc 09:00 | `DayOfWeek`, `LocalTime`, `ZoneId`, ngày hiệu lực | Phải dựng từng occurrence theo zone rules |
| Ngày sinh, ngày nghỉ | `LocalDate` | Không phải sự kiện ở một Instant cố định |
| API nhận mốc kèm offset | `OffsetDateTime` → `Instant` | Offset đủ xác định mốc; không tự suy ra zone gốc |

Khi JSON nhận cả local datetime và vùng:

```json
{
  "localStart": "2026-11-01T01:30:00",
  "timeZone": "America/New_York",
  "selectedOffset": "-05:00"
}
```

Ví dụ trên chọn **lần xuất hiện sau** của giờ 01:30 trong overlap, tương ứng `2026-11-01T06:30:00Z`. Server nên kiểm tra `selectedOffset` có nằm trong `zone.getRules().getValidOffsets(localStart)` rồi mới tạo `ZonedDateTime.ofStrict(...)`. Nếu input không có offset ở overlap, cần policy riêng thay vì âm thầm quyết định trong một hệ thống đòi giờ chính xác.

Sau khi lưu:

```json
{
  "startInstant": "2026-11-01T06:30:00Z",
  "organizerTimeZone": "America/New_York"
}
```

**Chọn kiểu SQL/JDBC cẩn thận:** nhiều hệ quản trị có kiểu `TIMESTAMP WITH TIME ZONE` nhưng không bảo toàn ID IANA gốc; cách chuẩn hóa offset và timestamp khác nhau giữa DB/driver. Nếu cần khôi phục vùng như `America/New_York`, lưu zone ID trong cột riêng. Không lưu mốc sự kiện dưới dạng `LocalDateTime` không offset nếu sau đó hệ thống có thể hiểu nhầm thành timezone máy chủ.

## 11. Vì sao ZoneId rất quan trọng với lịch lặp?

Giả sử người dùng muốn mở phiên học **mỗi thứ Hai lúc 09:00 theo New York** trong cả năm 2026. 09:00 local ngày mùa đông tương ứng `14:00Z` (offset `-05:00`), còn 09:00 local ngày mùa hè tương ứng `13:00Z` (offset `-04:00`). Vì thế:

- **Sai ngữ nghĩa:** lưu một lần đầu tiên bằng `Instant` rồi liên tục cộng `Duration.ofDays(7)` hoặc 7×24 giờ. Trong tuần DST, giờ trên đồng hồ có thể thành 08:00 hoặc 10:00.
- **Đúng ngữ nghĩa:** lưu giờ `09:00`, thứ trong tuần và `ZoneId.of("America/New_York")`; với mỗi ngày tuần cần chạy, tạo `LocalDateTime` và giải quyết bằng rules của ngày đó.
- **Cần policy:** quy tắc lặp vào `02:30` tại vùng có DST có thể gặp gap; quy tắc lặp vào `01:30` có thể gặp overlap. Quy định dời/bỏ/hỏi cần được thống nhất.

Với lịch “chạy mỗi **168 giờ thực**” thì cộng một `Duration` trên `Instant` lại đúng. Bài toán “cùng giờ theo địa phương” và “cách nhau cùng số giây trên timeline” là hai bài toán khác nhau.

### Bảng so sánh phép cộng

| Phép toán | Điều muốn bảo toàn | Hệ quả qua DST |
| --- | --- | --- |
| `zoned.plusDays(1)` | Ngày lịch tiếp theo, cố giữ giờ local | Có thể cách 23/25 giờ thực |
| `instant.plus(Duration.ofHours(24))` | Chính xác 24 giờ thực | Giờ local có thể thay đổi |
| `zoned.withZoneSameInstant(otherZone)` | Cùng mốc UTC | Giờ/ngày local thay đổi |
| `zoned.withZoneSameLocal(otherZone)` | Cùng ngày/giờ local (nếu có thể) | Mốc UTC có thể thay đổi |

## 12. Chi tiết nâng cao: lịch sử, alias và cơ sở dữ liệu timezone

### 12.1. Một vùng không chỉ là offset hiện tại

Luật timezone có thể thay đổi. Hệ thống quản lý vùng IANA (tzdb) lưu lịch sử điều chỉnh địa phương và các quy tắc tương lai hiện được biết. Vì vậy `ZoneId` như `Asia/Ho_Chi_Minh` có thể được dùng để diễn giải thời điểm lịch sử khác với offset `+07:00` của hiện tại.

`getRules().isFixedOffset()` phải hiểu trong toàn bộ dữ liệu rules, không chỉ là “hiện giờ vùng không dùng DST”. Dù một quốc gia không chuyển giờ mùa hè hiện tại, nó vẫn có thể có thay đổi offset trong lịch sử.

### 12.2. Alias và tên hiển thị

Đôi khi một địa điểm có nhiều ID cũ/alias được cơ sở dữ liệu hỗ trợ. Việc hai ID cùng hoạt động không có nghĩa `ZoneId.equals` luôn trả `true`; ID là dữ liệu có ý nghĩa định danh. Trong UI nên hiển thị nhãn thân thiện nhưng lưu ID đã chọn, hoặc có quy tắc canonicalization rõ ràng nếu nghiệp vụ cần.

`getDisplayName(...)` chỉ phù hợp UI; không parse ngược tùy tiện tên hiển thị thành ID. Các chữ viết tắt `EST`, `CST`, `IST` có thể mang nghĩa khác nhau ở những vùng khác nhau; tránh coi chúng là ID kỹ thuật toàn cầu.

### 12.3. ZoneRulesProvider và cập nhật tzdb

`java.time.zone.ZoneRulesProvider` là API hạ tầng cung cấp rules. Phần lớn ứng dụng **chỉ cần `ZoneId.of(id)` và `zone.getRules()`**, không cần cài custom provider. Các thay đổi quy tắc tzdb trong bản cập nhật JDK có thể ảnh hưởng việc tính các occurrence tương lai; khi dự báo lịch dài hạn hoặc lưu lịch lặp, cần chính sách đánh giá lại lịch sau khi dữ liệu quy tắc được cập nhật.

Một `ZoneId` đơn độc chỉ là danh tính vùng, không “đóng băng” toàn bộ rules cho tất cả các bản JDK. Khi hệ thống cần audit chính xác lịch đã xác nhận, lưu **`Instant` đã giải quyết** bên cạnh zone ID và những thông tin lựa chọn offset/phiên bản dữ liệu cần thiết theo yêu cầu kiểm toán.

## 13. Những lỗi thường gặp

1. **Dùng `ZoneOffset.ofHours(7)` thay cho một ZoneId vùng trong mọi trường hợp.** Offset hiện tại không đủ diễn tả lịch sử hoặc quy tắc thay đổi tại địa phương.
2. **Nghĩ `ZoneId` tự mang Instant.** ZoneId là định danh/luật; muốn mốc cụ thể phải kết hợp ngày giờ với offset hợp lệ, hoặc bắt đầu từ Instant.
3. **Lưu offset thay vì zone cho lịch định kỳ theo giờ địa phương.** Qua DST, lịch có thể lệch giờ đồng hồ.
4. **Để timezone của host/server lọt vào nghiệp vụ.** `ZoneId.systemDefault()` có thể đổi theo môi trường, làm sai dữ liệu đa quốc gia.
5. **Giả định local datetime nào cũng tồn tại.** DST gap có thời gian không hợp lệ; `atZone` mặc định có thể đẩy giờ.
6. **Giả định local datetime luôn duy nhất.** DST overlap có hai offset và hai Instant; cần quyết định chính sách.
7. **Dùng `getOffset(LocalDateTime)` như một bộ kiểm tra strict.** Hãy xét `getValidOffsets` hoặc `ofStrict` để phát hiện gap/overlap.
8. **Chuyển ZoneId nhưng giữ lại timestamp local cũ.** Dùng `withZoneSameInstant` cho cùng một sự kiện.
9. **So sánh hai cuộc hẹn bằng `toLocalDateTime()`.** Hai bản hiển thị khác vùng có thể là cùng Instant; so `toInstant()` cho sự kiện tuyệt đối.
10. **Parse một giờ local không offset như thể đó là UTC.** Không tự gán UTC nếu người dùng chưa định nghĩa.
11. **Lưu tên hiển thị múi giờ hoặc abbreviation vào database.** Dùng `ZoneId.getId()` hoặc ID vùng chuẩn được chấp nhận.
12. **Bỏ qua timezone/offset sau khi đọc JSON có thông tin vùng.** Có thể không phục hồi mốc ban đầu.
13. **Nghĩ `plusDays(1)` và cộng 24 giờ luôn giống nhau.** Qua DST thời lượng thực khác 24 giờ.
14. **Chạy test thời gian bằng giờ thực tại máy.** Dùng ngày/mốc/zone cố định và `Clock.fixed`.
15. **Dự báo offset của một ngày tương lai bằng offset hiện tại.** Tra theo đúng ngày/Instant cần sử dụng và giữ khả năng cập nhật luật vùng.

## 14. Bài tập tự luyện và đáp án định hướng

### Bài 1 — Hiểu danh tính vùng

Tạo `ZoneId.of("Asia/Ho_Chi_Minh")`, `ZoneId.of("America/New_York")` và `ZoneOffset.of("+07:00")`. In `getId()` và so `getRules().isFixedOffset()`. Giải thích vì sao một offset cố định và một ID vùng hiện có cùng offset vẫn khác ý nghĩa.

**Điểm cần đạt:** phân biệt offset cụ thể với quy tắc vùng, không suy ra DST từ offset.

### Bài 2 — Hai nơi, cùng một sự kiện

Cho `Instant.parse("2026-07-01T02:30:00Z")`. Dùng `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` và `instant.atZone(ZoneId.of("America/New_York"))`, kiểm tra:

- TP.HCM: `2026-07-01T09:30+07:00`.
- New York: `2026-06-30T22:30-04:00`.
- `toInstant()` của hai kết quả cùng bằng mốc đầu vào.

### Bài 3 — Offset theo mùa

Hỏi `rules.getOffset(Instant)` ở New York cho hai mốc `2026-01-15T12:00:00Z` và `2026-07-15T12:00:00Z`. Kết quả **-05:00** và **-04:00**. Nêu lý do dùng `ZoneId.of("America/New_York")` cho lịch họp thay vì lưu cứng `-05:00`.

### Bài 4 — Gap và overlap

Kiểm tra giờ địa phương `2026-03-08T02:30` và `2026-11-01T01:30` tại New York bằng `getValidOffsets`. Kết quả danh sách lần lượt **0** và **2** offset. Dùng `ofStrict` để tạo hai Instant hợp lệ cho overlap; không tự tạo Instant nếu gap.

### Bài 5 — Chọn zone cho hệ thống nhắc việc

Thiết kế thông báo “mỗi ngày 09:00 giờ của người dùng”. Đề xuất trường lưu trữ tối thiểu: `LocalTime`, `ZoneId` và luật lặp. Khi lên lịch lần chạy tới, tính ngày địa phương hợp lệ, kiểm tra offset và chuyển thành `Instant`. Thử kiểm tra lịch quanh thời điểm New York đổi DST.

### Bài 6 — Câu hỏi thiết kế cơ sở dữ liệu

Với một lịch hẹn đã chốt có `startInstant = 2026-11-01T06:30:00Z` tại `America/New_York`, hãy giải thích tại sao ngoài `Instant` có thể cần giữ zone gốc. Nếu chỉ lưu `-05:00` sẽ mất thông tin gì? Nếu chỉ lưu `2026-11-01T01:30` thì điều gì mơ hồ?

**Đáp án định hướng:** Instant bảo toàn mốc cụ thể; ZoneId bảo toàn ngữ cảnh múi giờ địa phương/luật lặp; một LocalDateTime ở overlap không chỉ tới đúng một Instant.

## 15. Checklist tự đánh giá

- [ ] Nói đúng rằng `ZoneId` dạng vùng đại diện cho **danh tính múi giờ và quy tắc offset theo thời gian**.
- [ ] Biết tạo/validate zone ID bằng `ZoneId.of`, lấy `getId`, không dùng tên hiển thị làm khóa kỹ thuật.
- [ ] Phân biệt `ZoneId` vùng với `ZoneOffset` cố định, bao gồm các ví dụ DST.
- [ ] Dùng `zone.getRules().getOffset(instant)` để tra offset tại một mốc đã biết.
- [ ] Hiểu `getValidOffsets(local)` trả 0/1/2 offset trong trường hợp gap/bình thường/overlap.
- [ ] Tạo `ZonedDateTime` từ `LocalDateTime.atZone(zone)` và biết chính sách ngầm ở gap/overlap.
- [ ] Sử dụng `ZonedDateTime.ofStrict(local, offset, zone)` để áp dụng offset đã chọn.
- [ ] Chuyển `Instant` sang các vùng mà không đổi mốc UTC.
- [ ] Giải thích khác nhau giữa `withZoneSameInstant` và `withZoneSameLocal`.
- [ ] Dùng ZoneId cho lịch lặp theo địa phương, Instant cho sự kiện đã xác định.
- [ ] Viết test ngày giờ cố định với zone tường minh và `Clock.fixed` cho logic “bây giờ”.

## Tài liệu chính thức cho JDK 17

- [`ZoneId` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [`ZoneOffset` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html)
- [`ZoneRules` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
- [`ZonedDateTime` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
- [`Instant` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [`Clock` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
