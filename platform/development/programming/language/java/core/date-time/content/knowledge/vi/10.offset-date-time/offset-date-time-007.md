# Chuyển giữa OffsetDateTime, Instant và ZonedDateTime trong Java

## Mục tiêu

Ba kiểu dữ liệu `OffsetDateTime`, `Instant` và `ZonedDateTime` đều có thể biểu diễn một **thời điểm xác định**, nhưng chúng lưu các thông tin khác nhau. Sau bài học, bạn sẽ biết chuyển đổi theo từng chiều, hiểu dữ liệu nào được giữ hoặc mất, và chọn đúng phép chuyển khi phải giữ nguyên thời điểm thực thay vì giữ nguyên giờ hiển thị.

Các ví dụ sử dụng `java.time` của Java 17+ và cố định giá trị đầu vào để kết quả có thể tái lập.

## 1. Nhận diện ba kiểu trước khi chuyển đổi

| Kiểu | Chứa gì? | Ví dụ | Không chứa gì? |
|---|---|---|---|
| `Instant` | Một điểm trên trục thời gian UTC | `2025-01-15T03:30:00Z` | Không mang ngày giờ địa phương hoặc `ZoneId`. |
| `OffsetDateTime` | Ngày–giờ địa phương cùng **UTC offset cố định** ở giá trị đó | `2025-01-15T10:30+07:00` | Không biết quy tắc múi giờ khu vực như `Asia/Ho_Chi_Minh`. |
| `ZonedDateTime` | Ngày–giờ địa phương, `ZoneId`, offset áp dụng tại thời điểm đó | `2025-01-15T10:30+07:00[Asia/Ho_Chi_Minh]` | Có thể biểu diễn cả vùng có DST, nhưng một giá trị đơn lẻ không tự mang lịch lặp lại. |

**UTC offset** như `+07:00` là độ lệch với UTC. **Múi giờ khu vực** như `America/New_York` lưu tên vùng và quy tắc chọn offset tùy ngày, gồm lịch sử đổi giờ và DST. `ZoneOffset` cũng là một `ZoneId`, nhưng là ID có offset cố định, không mang quy tắc khu vực.

Ví dụ, ba giá trị sau biểu diễn **cùng một thời điểm**:

```text
Instant         2025-01-15T03:30:00Z
OffsetDateTime  2025-01-15T10:30+07:00
ZonedDateTime   2025-01-15T10:30+07:00[Asia/Ho_Chi_Minh]
```

Chuyển đổi đúng phải trả lời được hai câu hỏi:

1. **Có cần giữ nguyên thời điểm trên trục UTC?** Phần lớn thao tác đổi múi giờ, lưu timestamp và hiển thị lịch sử sự kiện cần điều này.
2. **Có cần giữ lại danh tính múi giờ khu vực?** Nếu phải biết quy tắc `America/New_York` cho lần diễn ra trong tương lai, chỉ lưu `-05:00` là chưa đủ.

## 2. Sơ đồ chuyển đổi và API

```text
                       toInstant()
OffsetDateTime ----------------------------> Instant
      ^                                       |
      |                                       | atOffset(offset)
      |                                       | ofInstant(instant, zone)
      |                                       v
      +---------------------------------------+
                  Instant -> OffsetDateTime

OffsetDateTime -- atZoneSameInstant(zone) --> ZonedDateTime
OffsetDateTime -- toZonedDateTime() -------> ZonedDateTime (ZoneId là chính ZoneOffset)
ZonedDateTime  -- toOffsetDateTime() ------> OffsetDateTime
Instant        -- atZone(zone) ------------> ZonedDateTime
ZonedDateTime  -- toInstant() -------------> Instant
```

Bảng tra nhanh:

| Từ | Sang | Cách chuyển | Giữ nguyên `Instant`? | Có giữ tên khu vực? |
|---|---|---|---|---|
| `OffsetDateTime` | `Instant` | `offsetDateTime.toInstant()` | Có | Không có tên khu vực để giữ |
| `Instant` | `OffsetDateTime` | `instant.atOffset(offset)` | Có | Không |
| `Instant` | `OffsetDateTime` | `OffsetDateTime.ofInstant(instant, zone)` | Có | Không, chỉ lấy offset phù hợp tại thời điểm |
| `OffsetDateTime` | `ZonedDateTime` | `offsetDateTime.atZoneSameInstant(zone)` | Có | Có, theo `zone` được truyền |
| `OffsetDateTime` | `ZonedDateTime` | `offsetDateTime.toZonedDateTime()` | Có | Không, vùng trở thành `ZoneOffset` cố định |
| `ZonedDateTime` | `OffsetDateTime` | `zonedDateTime.toOffsetDateTime()` | Có | Mất tên khu vực |
| `Instant` | `ZonedDateTime` | `instant.atZone(zone)` hoặc `ZonedDateTime.ofInstant(instant, zone)` | Có | Có |
| `ZonedDateTime` | `Instant` | `zonedDateTime.toInstant()` | Có | Mất thông tin biểu diễn vùng |

Lưu ý: “giữ tên khu vực” ở bảng nghĩa là kết quả *mang tên vùng được truyền vào*. Nó không chứng minh được đó chính là vùng của dữ liệu gốc nếu đầu vào là `OffsetDateTime`.

## 3. OffsetDateTime ⇄ Instant

`OffsetDateTime` có ngày, giờ và offset nên xác định duy nhất một `Instant`.

```java
OffsetDateTime source =
        OffsetDateTime.parse("2025-01-15T10:30+07:00");

Instant instant = source.toInstant();
// instant = 2025-01-15T03:30:00Z
```

Khi đi ngược từ `Instant` về `OffsetDateTime`, phải cung cấp thông tin cách hiển thị giờ:

```java
OffsetDateTime utcView = instant.atOffset(ZoneOffset.UTC);
// 2025-01-15T03:30Z

OffsetDateTime vietnamView =
        instant.atOffset(ZoneOffset.ofHours(7));
// 2025-01-15T10:30+07:00

OffsetDateTime newYorkView =
        OffsetDateTime.ofInstant(instant, ZoneId.of("America/New_York"));
// 2025-01-14T22:30-05:00
```

- `Instant.atOffset(ZoneOffset)` dùng offset **do bạn chỉ định**; đây là cách biểu diễn bằng offset cố định.
- `OffsetDateTime.ofInstant(Instant, ZoneId)` hỏi `ZoneRules` của khu vực để lấy **offset đúng tại `Instant`**, rồi tạo `OffsetDateTime`. Kết quả vẫn **không chứa** tên vùng `America/New_York`.

Khi chuyển `OffsetDateTime → Instant`, mất ngày–giờ và offset ban đầu: từ `Instant` không thể tự biết người gửi đã sử dụng `+07:00`, `+08:00` hay `Z`. Việc chọn offset khi dựng lại là một quyết định mới.

## 4. OffsetDateTime ⇄ ZonedDateTime: chọn cách hiểu đúng

### 4.1. atZoneSameInstant(zone): giữ nguyên thời điểm

```java
OffsetDateTime source =
        OffsetDateTime.parse("2025-01-15T10:30+07:00");

ZonedDateTime inNewYork =
        source.atZoneSameInstant(ZoneId.of("America/New_York"));
// 2025-01-14T22:30-05:00[America/New_York]
```

Phương thức này giữ nguyên `source.toInstant()`. Nó tính lại giờ địa phương và offset dựa trên vùng đích. Đây thường là lựa chọn chính xác khi chuyển một sự kiện đã xảy ra sang múi giờ người xem.

### 4.2. toZonedDateTime(): gắn chính ZoneOffset làm vùng

```java
ZonedDateTime fixedZone = source.toZonedDateTime();
// 2025-01-15T10:30+07:00

ZoneId zone = fixedZone.getZone();
// zone có ID "+07:00", không phải "Asia/Ho_Chi_Minh"
```

Đây là chuyển đổi **không cần truyền `ZoneId`**: Java dùng `+07:00` làm một `ZoneId` cố định. Kết quả vẫn giữ nguyên `Instant`, ngày–giờ địa phương và offset của nguồn, nhưng **không phục hồi được tên khu vực** từ offset. Nhiều khu vực có thể cùng offset tại một thời điểm.

### 4.3. atZoneSimilarLocal(zone): cố giữ giờ đồng hồ

`OffsetDateTime.atZoneSimilarLocal(zone)` cố duy trì `LocalDateTime` của nguồn, ưu tiên offset nguồn nếu offset đó hợp lệ trong vùng đích. Nếu không hợp lệ, `ZonedDateTime` sẽ áp dụng quy tắc giải quyết giờ trùng/không tồn tại của vùng đích. **Thời điểm UTC có thể thay đổi.**

So sánh cùng một nguồn:

```java
OffsetDateTime source =
        OffsetDateTime.parse("2025-01-15T10:30+07:00");
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime sameInstant = source.atZoneSameInstant(ny);
// 2025-01-14T22:30-05:00[America/New_York]

ZonedDateTime similarLocal = source.atZoneSimilarLocal(ny);
// 2025-01-15T10:30-05:00[America/New_York]
```

Hai kết quả có giờ địa phương khác nhau và cách nhau **12 giờ trên trục UTC**. Nếu yêu cầu “hiển thị thời điểm sự kiện ở New York”, hãy dùng `atZoneSameInstant`. Nếu nghiệp vụ yêu cầu giữ nguyên giờ đồng hồ tại vùng mới, `atZoneSimilarLocal` có ý nghĩa, nhưng phải chấp nhận thời điểm mới và quy tắc DST.

### 4.4. ZonedDateTime.toOffsetDateTime(): bỏ tên khu vực

```java
ZonedDateTime zoned = ZonedDateTime.parse(
        "2025-01-14T22:30-05:00[America/New_York]");

OffsetDateTime offsetOnly = zoned.toOffsetDateTime();
// 2025-01-14T22:30-05:00
```

Ngày–giờ, offset và `Instant` không đổi, nhưng `America/New_York` không còn trong kết quả. Nếu muốn chuyển sang offset của **khu vực khác**, đổi khu vực trước rồi mới bỏ tên vùng:

```java
OffsetDateTime tokyoOffset = zoned
        .withZoneSameInstant(ZoneId.of("Asia/Tokyo"))
        .toOffsetDateTime();
// 2025-01-15T12:30+09:00
```

## 5. Instant ⇄ ZonedDateTime

Từ một `Instant`, chọn vùng để hiển thị:

```java
Instant instant = Instant.parse("2025-01-15T03:30:00Z");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = instant.atZone(vietnam);
// 2025-01-15T10:30+07:00[Asia/Ho_Chi_Minh]

ZonedDateTime equivalent =
        ZonedDateTime.ofInstant(instant, vietnam);
```

`atZone` và `ofInstant` đều dùng quy tắc múi giờ tại thời điểm thực đã biết. Chúng không phải phân giải sự mơ hồ của một `LocalDateTime` chưa có offset, kể cả khi `Instant` thuộc đêm đổi DST.

Để quay lại timestamp gốc:

```java
Instant roundTrip = zoned.toInstant();
// roundTrip.equals(instant) là true
```

Nếu giữ `ZonedDateTime` và chỉ đổi khu vực hiển thị, `withZoneSameInstant(otherZone)` cũng bảo toàn timestamp. Ngược lại, `withZoneSameLocal(otherZone)` cố giữ giờ địa phương, nên có thể tạo một `Instant` khác.

## 6. Ví dụ Java 17+ đầy đủ và kết quả xác định

Tạo tệp `DateTimeConversionDemo.java`:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class DateTimeConversionDemo {
    public static void main(String[] args) {
        OffsetDateTime source =
                OffsetDateTime.parse("2025-01-15T10:30+07:00");
        Instant instant = source.toInstant();
        ZoneId newYork = ZoneId.of("America/New_York");

        ZonedDateTime nyZoned = source.atZoneSameInstant(newYork);
        OffsetDateTime nyOffset = nyZoned.toOffsetDateTime();
        ZonedDateTime fixedZone = source.toZonedDateTime();
        OffsetDateTime utcOffset = instant.atOffset(ZoneOffset.UTC);

        System.out.println("Source:     " + source);
        System.out.println("Instant:    " + instant);
        System.out.println("New York:   " + nyZoned);
        System.out.println("NY offset:  " + nyOffset);
        System.out.println("Fixed zone: " + fixedZone);
        System.out.println("Zone ID:    " + fixedZone.getZone());
        System.out.println("UTC offset: " + utcOffset);
        System.out.println("Same time:  "
                + source.toInstant().equals(nyOffset.toInstant()));

        ZonedDateTime similarLocal = source.atZoneSimilarLocal(newYork);
        System.out.println("Similar:    " + similarLocal);
        System.out.println("Same local: "
                + source.toLocalDateTime().equals(
                        similarLocal.toLocalDateTime()));
        System.out.println("Preserved:  "
                + source.toInstant().equals(similarLocal.toInstant()));
    }
}
```

Biên dịch và chạy:

```bash
javac DateTimeConversionDemo.java
java DateTimeConversionDemo
```

Đầu ra với quy tắc New York cho ngày tháng 1 năm 2025:

```text
Source:     2025-01-15T10:30+07:00
Instant:    2025-01-15T03:30:00Z
New York:   2025-01-14T22:30-05:00[America/New_York]
NY offset:  2025-01-14T22:30-05:00
Fixed zone: 2025-01-15T10:30+07:00
Zone ID:    +07:00
UTC offset: 2025-01-15T03:30Z
Same time:  true
Similar:    2025-01-15T10:30-05:00[America/New_York]
Same local: true
Preserved:  false
```

**Giải thích:** `sameInstant` tính giờ New York là 22:30 của **ngày trước đó** nhưng giữ UTC 03:30Z. `similarLocal` giữ 10:30 theo đồng hồ New York, tương ứng 15:30Z, nên **không** giữ cùng thời điểm. `fixedZone` vẫn có vùng `+07:00`, khác về danh tính so với `Asia/Ho_Chi_Minh`.

## 7. DST: vì sao Instant đáng tin hơn khi đổi vùng?

Vào ngày 03/11/2024 ở `America/New_York`, 01:30 xảy ra hai lần khi đồng hồ lùi từ `-04:00` về `-05:00`:

```java
OffsetDateTime first =
        OffsetDateTime.parse("2024-11-03T01:30-04:00");
OffsetDateTime second =
        OffsetDateTime.parse("2024-11-03T01:30-05:00");

Instant one = first.toInstant();  // 2024-11-03T05:30:00Z
Instant two = second.toInstant(); // 2024-11-03T06:30:00Z
```

Hai giá trị `OffsetDateTime` có **cùng giờ đồng hồ**, nhưng offset khác nên là hai thời điểm riêng biệt. Với `ZoneId.of("America/New_York")`, việc chuyển `first.atZoneSameInstant(zone)` và `second.atZoneSameInstant(zone)` vẫn phân biệt chính xác hai lần 01:30; Java tìm offset theo từng `Instant`.

Ngược lại, nếu bỏ cả offset lẫn múi giờ để giữ mỗi `LocalDateTime`, thông tin cần phân biệt hai lần 01:30 đã mất. Gọi `LocalDateTime.atZone(zone)` trong khoảng overlap mặc định chọn offset sớm hơn, thường là offset DST. Trong gap (đồng hồ nhảy tới trước), một giờ địa phương có thể không tồn tại và Java mặc định đẩy thời gian đến giá trị hợp lệ.

Lưu ý khác: một `OffsetDateTime` có offset `-05:00` không chứng minh rằng giờ địa phương nguồn tương ứng với quy tắc New York vào ngày bất kỳ. `atZoneSameInstant(ny)` luôn tính **lại** giờ địa phương hợp lệ theo vùng đích; `atZoneSimilarLocal(ny)` áp dụng quy tắc khác để ưu tiên giữ giờ đồng hồ. Không suy ra một `ZoneId` khu vực từ `ZoneOffset` vì nhiều vùng có thể trùng offset.

## 8. Phân biệt đổi offset: SameInstant và SameLocal

Cùng nguyên tắc giữ thời điểm/giữ đồng hồ cũng xuất hiện ngay trong `OffsetDateTime`:

```java
OffsetDateTime source =
        OffsetDateTime.parse("2025-01-15T10:30+07:00");

OffsetDateTime utcSameInstant =
        source.withOffsetSameInstant(ZoneOffset.UTC);
// 2025-01-15T03:30Z: giữ Instant, đổi giờ hiển thị.

OffsetDateTime utcSameLocal =
        source.withOffsetSameLocal(ZoneOffset.UTC);
// 2025-01-15T10:30Z: giữ đồng hồ, đổi Instant.
```

`withOffsetSameLocal` thường phù hợp khi cần **diễn giải lại** một ngày–giờ với offset đã nhập sai hoặc khi nghiệp vụ cố ý thay đổi offset mà không đổi số giờ. Nó không phải thao tác chuyển múi giờ để xem một thời điểm lịch sử.

## 9. So sánh kết quả đúng cách

Khi cần xác nhận hai đối tượng đại diện **cùng một thời điểm**, so sánh `toInstant()`:

```java
OffsetDateTime original =
        OffsetDateTime.parse("2025-01-15T10:30+07:00");
ZonedDateTime converted =
        original.atZoneSameInstant(ZoneId.of("America/New_York"));

boolean sameInstant =
        original.toInstant().equals(converted.toInstant()); // true
```

Tránh kiểm tra `equals()` một cách máy móc giữa những kiểu hoặc cách biểu diễn khác nhau. `OffsetDateTime.equals` kiểm tra cả ngày–giờ địa phương và offset; hai `OffsetDateTime` có thể cùng `Instant` nhưng `equals` trả `false`. `ZonedDateTime.equals` còn xét cả zone ID, nên cùng `Instant` không bắt buộc bằng nhau theo `equals`.

Một chu trình chuyển đổi bảo toàn thời điểm:

```text
OffsetDateTime --> toInstant() --> Instant
      ^                            |
      |                            | atZone(zone)
      |                            v
      +---- toOffsetDateTime() -- ZonedDateTime
```

Dù `toInstant()` của điểm đầu và điểm cuối giống nhau, `OffsetDateTime` sau chu trình có thể có **offset hoặc ngày–giờ địa phương khác** nếu `zone` được chọn khác vùng/offset ban đầu.

## 10. Chọn kiểu dữ liệu theo công việc

| Công việc | Nên ưu tiên | Lý do |
|---|---|---|
| Lưu thời điểm sự kiện, log, gửi message giữa hệ thống | `Instant` | Thể hiện duy nhất thời điểm tuyệt đối, không phụ thuộc giờ hiển thị. |
| API chấp nhận ngày giờ kèm offset (ví dụ `2025-01-15T10:30+07:00`) | `OffsetDateTime` | Dữ liệu truyền có offset, chuyển sang `Instant` được ngay. |
| Hiển thị một timestamp tại vùng người dùng | `Instant.atZone(userZone)` | Bảo toàn thời điểm và áp dụng đúng quy tắc vùng. |
| Làm việc với lịch và quy tắc địa phương của một vùng | `ZonedDateTime` cùng `ZoneId` thực | Có tên vùng để biết quy tắc DST của vùng. |
| Chỉ cần dạng có offset để xuất API từ `ZonedDateTime` | `toOffsetDateTime()` | Giữ thời điểm/offset, cố ý bỏ tên vùng. |
| Chuyển `OffsetDateTime` sang vùng đích | `atZoneSameInstant(zone)` | Giữ thời điểm; tính giờ và offset theo vùng đích. |

Với lịch hẹn **tương lai**, đôi khi cần lưu cả giờ dự định theo địa phương (`LocalDateTime`), `ZoneId` và chính sách cho gap/overlap thay vì chỉ một `Instant` được tính trước. Quy tắc vùng có thể được cơ quan quản lý thay đổi trước ngày diễn ra; timestamp tuyệt đối phù hợp hơn cho sự kiện **đã xảy ra**.

## 11. Lỗi thường gặp

1. **Cho rằng `+07:00` chính là `Asia/Ho_Chi_Minh`.** Offset chỉ nêu số giờ lệch ở một thời điểm; nó không nhận dạng duy nhất một khu vực.
2. **Gọi `toZonedDateTime()` và nghĩ đã có vùng địa lý.** Phương thức này chỉ dùng offset làm zone ID. Nếu cần vùng thật, cung cấp `ZoneId` cho `atZoneSameInstant`.
3. **Dùng `atZoneSimilarLocal` để hiển thị timestamp ở múi giờ khác.** Phương thức này có thể đổi `Instant`; dùng `atZoneSameInstant` khi cần giữ thời điểm.
4. **Tạo `OffsetDateTime` từ `Instant` mà không chỉ định offset hoặc zone.** `Instant` không chứa ngữ cảnh hiển thị; bạn phải chọn `ZoneOffset` hoặc `ZoneId`.
5. **Lưu mỗi `LocalDateTime` sau khi bỏ offset.** Khi gặp overlap, không thể xác định lại timestamp gốc từ riêng local time và vùng.
6. **So sánh `equals` thay cho cùng thời điểm.** Dùng `toInstant().equals(...)` khi yêu cầu là thời điểm thực; dùng so sánh đầy đủ khi cần cả cấu trúc biểu diễn.
7. **Phụ thuộc `ZoneId.systemDefault()` trong test hoặc dịch vụ chạy nhiều máy.** Hãy truyền vùng rõ ràng từ yêu cầu nghiệp vụ để tránh thay đổi theo cấu hình máy chủ.

## 12. Câu hỏi tự kiểm tra

**1.** Một giá trị `OffsetDateTime` là `2025-01-15T10:30+07:00`. Đổi sang `Instant` được gì?

**Đáp án:** `2025-01-15T03:30:00Z`. UTC đi sau đồng hồ `+07:00` đúng 7 giờ.

**2.** `OffsetDateTime.toZonedDateTime()` có khôi phục được `Asia/Ho_Chi_Minh` không?

**Đáp án:** Không. Nó dùng chính `+07:00` làm vùng cố định. Nếu muốn mang `Asia/Ho_Chi_Minh`, bạn phải truyền `ZoneId` khu vực, ví dụ bằng `atZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"))`.

**3.** Đổi một sự kiện từ offset `+07:00` sang New York để xem giờ tại đó nên dùng `atZoneSameInstant` hay `atZoneSimilarLocal`?

**Đáp án:** `atZoneSameInstant`, vì yêu cầu là xem **cùng sự kiện** tại vùng khác.

**4.** Tại sao hai `OffsetDateTime` đều hiển thị 01:30 ngày 03/11/2024 ở New York có thể không đại diện cùng sự kiện?

**Đáp án:** Khoảng overlap tạo hai offset `-04:00` và `-05:00`, tức hai `Instant` cách nhau một giờ.

**5.** Muốn xác định hai kết quả khác kiểu `OffsetDateTime` và `ZonedDateTime` có cùng thời điểm hay không, kiểm tra gì?

**Đáp án:** So sánh `a.toInstant().equals(b.toInstant())`.

---

**Quy tắc thực hành:** Chuyển qua `Instant` khi dữ liệu cần mang ý nghĩa “thời điểm thực”; mang `ZoneId` khi cần “giờ địa phương thuộc vùng nào”; chỉ dùng `OffsetDateTime` khi ngày–giờ và offset đã đủ cho hợp đồng dữ liệu của bạn.