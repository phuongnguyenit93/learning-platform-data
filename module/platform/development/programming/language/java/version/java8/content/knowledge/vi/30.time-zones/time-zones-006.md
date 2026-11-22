# atZone và chọn cách giải quyết thời gian không duy nhất trong Java

**Chủ đề cha:** Múi giờ (`java.time`). **Đề bài:** Hiểu cách `LocalDateTime.atZone(ZoneId)` gán múi giờ vào ngày–giờ cục bộ, và đặc biệt cách lựa chọn chính sách khi một giờ trên đồng hồ **không tồn tại** (*gap*) hoặc **xuất hiện hai lần** (*overlap*). Bài học phân biệt việc dùng mặc định của Java với quyết định nghiệp vụ phải được đưa ra tường minh khi đặt lịch, ghi nhận sự kiện, nhắc việc, giao dịch và báo cáo.

**Phiên bản:** Các kiểu `LocalDateTime`, `ZoneId`, `ZoneRules`, `ZonedDateTime` và `ZoneOffsetTransition` của `java.time` có từ Java 8 và vẫn là API được hỗ trợ trên JDK hiện đại. Ví dụ độc lập dưới đây viết cho **Java 17+**. Dữ liệu minh họa sử dụng các chuyển đổi đã xảy ra trong năm 2024 của `Europe/Berlin`, không phụ thuộc ngày hiện tại. Quy tắc múi giờ thực tế lấy từ cơ sở dữ liệu tzdb của JDK và có thể được cập nhật theo quyết định của các quốc gia.

> **Quy tắc quan trọng:** `LocalDateTime` chỉ có năm, tháng, ngày, giờ, phút… **không có múi giờ hay offset**; bản thân nó chưa xác định một thời điểm UTC duy nhất. `local.atZone(zone)` phải dùng `ZoneRules` để giải quyết. Với *gap*, Java **dịch giờ lên phía trước theo độ dài gap**; với *overlap*, nó thường chọn **offset sớm hơn trong hai offset hợp lệ**. Đây là **chính sách mặc định** của API, không phải quyết định tự động đúng cho mọi nghiệp vụ.

## 1. Tách biệt local time, zone, offset và instant

Một ví dụ người dùng nhập lịch hẹn: “Ngày 27/10/2024, lúc 02:30, ở Berlin”. Dữ liệu đó ban đầu là:

```java
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);
ZoneId zone = ZoneId.of("Europe/Berlin");
```

Đây là **đoạn mã trong phương thức** với import `java.time.LocalDateTime` và `java.time.ZoneId`. Nó chưa chọn được `Instant`; cần luật múi giờ.

| Kiểu Java | Chứa dữ liệu | Dùng khi |
| --- | --- | --- |
| `LocalDate` | Năm–tháng–ngày, không có giờ/zone | Sinh nhật, ngày giao hàng |
| `LocalTime` | Giờ–phút–giây, không có ngày/zone | Giờ mở cửa |
| `LocalDateTime` | Ngày + giờ cục bộ, không offset/zone | Người dùng đặt lịch theo đồng hồ địa phương |
| `ZoneId` | ID vùng múi giờ hoặc fixed offset | `Europe/Berlin`, `Asia/Ho_Chi_Minh` |
| `ZoneOffset` | Độ lệch cố định so với UTC | `+01:00`, `+02:00`, `Z` |
| `ZoneRules` | Tập quy tắc offset, chuyển đổi theo thời gian của một zone | Kiểm tra valid offsets và transition |
| `OffsetDateTime` | Local date-time + offset cụ thể | Một thời điểm xác định, nhưng không giữ lịch sử/tương lai của vùng |
| `ZonedDateTime` | Local date-time + ZoneId + offset được giải quyết | Ngày–giờ tại một khu vực theo các quy tắc đã chọn |
| `Instant` | Một điểm trên trục thời gian UTC | Lưu timestamp, so sánh sự kiện, đo duration |

**ZoneId khác ZoneOffset.** `ZoneId.of("Europe/Berlin")` dùng quy tắc vùng theo từng thời điểm, còn `ZoneOffset.of("+01:00")` là **một độ lệch cố định**, không đủ để mô tả các đợt thay đổi offset của Berlin. `Asia/Ho_Chi_Minh` là một Region ZoneId; đừng thay nó bằng `+07:00` khi yêu cầu của hệ thống là lưu danh tính vùng và áp dụng các quy tắc lịch sử/tương lai.

### 1.1. Vì sao cùng một local time chưa chắc có một instant?

Để chuyển `LocalDateTime` thành `Instant`, cần biết offset:

```text
Instant = LocalDateTime - ZoneOffset
```

Ví dụ `2024-10-27T02:30` tại Berlin có hai offset hợp lệ ở ngày chuyển đồng hồ mùa thu:

- Với `+02:00` → `2024-10-27T00:30:00Z`.
- Với `+01:00` → `2024-10-27T01:30:00Z`.

Chênh lệch một giờ dù **chữ số trên đồng hồ địa phương giống hệt nhau**. Nếu chỉ lưu chuỗi `2024-10-27T02:30` mà không lưu zone/offset/chính sách, không thể tái dựng chính xác instant được chọn.

Ngược lại, từ một `Instant` và một `ZoneId`, tại một thời điểm có **một offset thực sự có hiệu lực** theo ZoneRules; chuyển sang ZonedDateTime không phải đưa ra lựa chọn gap/overlap như khi bắt đầu từ LocalDateTime.

## 2. Ba trường hợp của ZoneRules: bình thường, gap, overlap

Trọng tâm của `atZone` là số offset hợp lệ cho cặp `(localDateTime, zone)`.

| Trường hợp | `ZoneRules.getValidOffsets(local).size()` | Ý nghĩa | Chiến lược cần xét |
| --- | ---: | --- | --- |
| **Normal** | 1 | Thời gian cục bộ ứng với đúng một instant | Dùng offset duy nhất |
| **Gap** | 0 | Đồng hồ nhảy tới, một dải local time **không từng xảy ra** | Từ chối, dịch theo gap, hoặc lấy đầu khoảng hợp lệ tiếp theo |
| **Overlap** | 2 | Đồng hồ quay lui, một dải local time **xảy ra hai lần** | Từ chối, chọn offset sớm hoặc muộn, hoặc yêu cầu người dùng quyết định |

Ví dụ kiểm thử trong `Europe/Berlin` năm 2024:

| LocalDateTime | Trạng thái | Offsets hợp lệ |
| --- | --- | --- |
| `2024-01-15T12:00` | Normal | `[+01:00]` |
| `2024-03-31T02:30` | Gap | `[]` |
| `2024-10-27T02:30` | Overlap | `[+02:00, +01:00]` |

Đây là **các mốc lịch sử cụ thể**, không phải quy tắc cố định rằng Berlin mãi mãi đổi giờ vào đúng những ngày này. Không được hard-code “gap luôn một giờ” hay “cứ Chủ nhật cuối tháng 3/tháng 10” làm thuật toán tổng quát: chính phủ có thể đổi luật, và thế giới có những thay đổi offset không tròn một giờ, thậm chí bỏ qua ngày.

### 2.1. API kiểm tra

```java
ZoneRules rules = zone.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.size() == 1) {
    // Normal: một offset.
} else if (offsets.isEmpty()) {
    // Gap: không tồn tại local time này.
} else {
    // Overlap: hai offset.
}
```

Đây là **mã minh họa bên trong phương thức**, cần import `java.time.zone.ZoneRules`, `java.time.ZoneOffset`, `java.time.ZoneId` và `java.util.List`. `getValidOffsets` là API phù hợp để **phân loại chính xác**, trong khi `ZoneRules.getOffset(LocalDateTime)` chỉ trả một offset “thích hợp nhất” cho gap/overlap (thường offset trước transition), **không xác minh local time có hợp lệ hay duy nhất**.

`rules.getTransition(local)` trả `ZoneOffsetTransition` khi local nằm trong gap/overlap, và thông thường trả `null` ở thời điểm normal. Từ transition có thể đọc `isGap()`, `isOverlap()`, `getDuration()`, `getDateTimeBefore()`, `getDateTimeAfter()`, `getOffsetBefore()`, `getOffsetAfter()`.

## 3. Chính xác `LocalDateTime.atZone(ZoneId)` làm gì?

Lời gọi:

```java
ZonedDateTime resolved = local.atZone(zone);
```

**Không đơn thuần chỉ đính nhãn múi giờ vào một LocalDateTime**. Java tìm offset theo `ZoneRules`, từ đó tạo một `ZonedDateTime` xác định được instant.

### Trường hợp bình thường

Nếu có **một** offset hợp lệ, `atZone` dùng offset đó; local date-time được giữ nguyên.

```text
2024-01-15T12:00 + Europe/Berlin
=> 2024-01-15T12:00+01:00[Europe/Berlin]
```

### Trường hợp gap: local time không tồn tại

Ngày 31/03/2024 ở Berlin, đồng hồ chuyển từ `01:59:59... +01:00` sang `03:00 +02:00`. Dải `02:00–02:59:59...` không tồn tại.

```text
Người dùng nhập:     2024-03-31T02:30[Europe/Berlin]
Offsets hợp lệ:      []
atZone trả:          2024-03-31T03:30+02:00[Europe/Berlin]
```

Java **đẩy local time tiến lên đúng độ dài gap là một giờ**, giữ phần phút `:30`. Nó không mặc định ném lỗi.

**Phân biệt hai chính sách:** “Dịch tiến thêm đúng độ dài gap” cho 03:30, còn “chọn thời điểm hợp lệ đầu tiên ngay sau gap” cho 03:00. Cả hai có thể hợp lý trong những domain khác nhau. Đừng gọi nhầm cả hai là cùng một thuật toán “dịch đến giờ hợp lệ”.

### Trường hợp overlap: local time có hai nghĩa

Ngày 27/10/2024 ở Berlin, đồng hồ lùi từ `03:00 +02:00` về `02:00 +01:00`. Vì vậy `02:30` xảy ra hai lần.

```text
Người dùng nhập:     2024-10-27T02:30[Europe/Berlin]
Offsets hợp lệ:      [+02:00, +01:00]
atZone mặc định:     2024-10-27T02:30+02:00[Europe/Berlin]
Instant mặc định:    2024-10-27T00:30:00Z
Lần xuất hiện sau:  2024-10-27T02:30+01:00[Europe/Berlin]
Instant lần sau:    2024-10-27T01:30:00Z
```

Với `LocalDateTime.atZone`, khi không có “previous offset” để duy trì, Java chọn **earlier valid offset**, thường là offset mùa hè. “Earlier offset” ở đây là khái niệm API chỉ offset trước lúc đồng hồ lùi, và nó tương ứng với **instant xảy ra trước** trong ví dụ.

**Không hiểu nhầm `+02:00` lớn hơn `+01:00` nên phải gọi là “later offset” theo toán học.** Tên earlier/later chỉ thứ tự ứng với chuyển tiếp của đồng hồ và hai lần diễn ra của giờ cục bộ.

## 4. Chương trình hoàn chỉnh: atZone mặc định và ZoneRules

Tạo file **`AtZoneDefaultDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class AtZoneDefaultDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZoneRules rules = berlin.getRules();

        LocalDateTime normal = LocalDateTime.of(
                2024, 1, 15, 12, 0);
        LocalDateTime gap = LocalDateTime.of(
                2024, 3, 31, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(
                2024, 10, 27, 2, 30);

        ZonedDateTime earlier = overlap.atZone(berlin);
        ZonedDateTime later =
                earlier.withLaterOffsetAtOverlap();

        System.out.println("Normal: " + normal.atZone(berlin));
        System.out.println("Gap offsets: "
                + rules.getValidOffsets(gap));
        System.out.println("Gap atZone: " + gap.atZone(berlin));
        System.out.println("Gap next valid: "
                + rules.getTransition(gap).getDateTimeAfter());
        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));
        System.out.println("Overlap default: " + earlier);
        System.out.println("Overlap later: " + later);
        System.out.println("Earlier instant: "
                + earlier.toInstant());
        System.out.println("Later instant: "
                + later.toInstant());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 AtZoneDefaultDemo.java
java AtZoneDefaultDemo
```

**Stdout kiểm chứng với dữ liệu tzdb hỗ trợ các transition Berlin 2024:**

```text
Normal: 2024-01-15T12:00+01:00[Europe/Berlin]
Gap offsets: []
Gap atZone: 2024-03-31T03:30+02:00[Europe/Berlin]
Gap next valid: 2024-03-31T03:00
Overlap offsets: [+02:00, +01:00]
Overlap default: 2024-10-27T02:30+02:00[Europe/Berlin]
Overlap later: 2024-10-27T02:30+01:00[Europe/Berlin]
Earlier instant: 2024-10-27T00:30:00Z
Later instant: 2024-10-27T01:30:00Z
```

**Phân tích:**

1. `rules.getValidOffsets(gap)` là danh sách rỗng, nhưng `gap.atZone(berlin)` vẫn trả ZonedDateTime vì mặc định **điều chỉnh** giờ sang 03:30.
2. `rules.getTransition(gap).getDateTimeAfter()` trả 03:00 — **đầu** của khoảng hợp lệ sau gap, không phải kết quả mặc định 03:30.
3. `rules.getValidOffsets(overlap)` có hai offset: `+02:00` và `+01:00`.
4. `atZone` chọn `+02:00`; `withLaterOffsetAtOverlap()` chuyển sang `+01:00` mà vẫn giữ local `02:30`.
5. Hai `Instant` khác nhau đúng một giờ. Khi hệ thống giao dịch ghi nhận thời điểm diễn ra, không thể lưu duy nhất local string để phân biệt hai lần 02:30.
6. `getTransition` chỉ cần gọi khi biết local nằm trong gap/overlap; trong production, nên kiểm tra số valid offsets hoặc kiểm tra `transition != null` trước khi truy cập.

## 5. Quy tắc khi không tồn tại giờ (gap): Không chỉ có một lựa chọn

Một lịch hẹn “02:30 ngày đổi giờ” có ít nhất ba chính sách hợp lý về mặt kỹ thuật. Chọn chính sách dựa trên yêu cầu người dùng, không phụ thuộc việc API tiện gọi nhất.

| Gap policy | Cách xử lý | Với Berlin 2024-03-31T02:30 |
| --- | --- | --- |
| **REJECT** | Từ chối dữ liệu, yêu cầu chọn lại | Báo lỗi “giờ này không tồn tại ở múi giờ đã chọn” |
| **SHIFT_FORWARD_BY_GAP** | Cộng đúng độ dài khoảng chuyển tiếp | 03:30 +02:00 |
| **NEXT_VALID_LOCAL_TIME** | Chọn mốc local hợp lệ đầu tiên ngay sau gap | 03:00 +02:00 |

**REJECT** phù hợp cho giờ khởi hành, lịch hẹn, lịch học, giao dịch cần giờ nhập được tôn trọng chính xác. Nếu người dùng nhập 02:30 nhưng hệ thống âm thầm đổi thành 03:30, có thể gây nhầm lẫn.

**SHIFT_FORWARD_BY_GAP** là hành vi của `LocalDateTime.atZone` và `ZonedDateTime.of(local, zone)`; phù hợp khi hợp đồng sản phẩm đã công khai cách dịch lịch. Không coi đó là mặc định của nghiệp vụ.

**NEXT_VALID_LOCAL_TIME** bảo đảm chọn **đầu** khoảng hợp lệ ngay sau chuyển tiếp, hữu ích cho một số cửa sổ xử lý hay quy tắc “thực thi sớm nhất có thể”. Với gap Berlin 2024 ví dụ, chọn 03:00 chứ không phải 03:30.

Tổng quát hơn, **độ dài gap có thể không phải đúng một giờ**, và thậm chí một zone có thể bỏ qua cả một ngày theo quyết định chính trị. `transition.getDuration()`, `getDateTimeBefore/After` là nguồn thông tin đáng tin cho **transition cụ thể**, không nên hard-code “cộng một giờ” hoặc “giờ 02 luôn đặc biệt”.

### 5.1. Nếu dùng `ZonedDateTime.ofStrict`

`ZonedDateTime.ofStrict(local, offset, zone)` kiểm tra **cả local + offset + zone** và ném `DateTimeException` nếu offset không hợp lệ theo luật zone. Trong gap, không có offset hợp lệ nào; vì thế không dùng `ofStrict` để “tự dịch” gap.

```java
ZonedDateTime strict = ZonedDateTime.ofStrict(
        LocalDateTime.of(2024, 3, 31, 2, 30),
        ZoneOffset.ofHours(1),
        ZoneId.of("Europe/Berlin"));
```

Đây là **đoạn mã cố ý thất bại** trong phương thức: `DateTimeException` vì giờ 02:30 trong gap không tồn tại. Đừng để example bị hiểu là chương trình biên dịch/chạy không lỗi.

Để yêu cầu **không bao giờ điều chỉnh thầm lặng**, hãy **kiểm tra valid offsets trước**, sau đó dùng `ofStrict` với đúng offset được chọn. `ofStrict` tự nó **không giải quyết lựa chọn** giữa hai offset hợp lệ trong overlap; nó kiểm tra lựa chọn mà bạn đã cung cấp.

## 6. Quy tắc khi một giờ xuất hiện hai lần (overlap)

Overlap không có một “local time không hợp lệ”: cả hai lần 02:30 đều **hợp lệ nhưng khác instant**.

| Overlap policy | Ý nghĩa | Berlin 2024-10-27T02:30 |
| --- | --- | --- |
| **REJECT** | Không chấp nhận thông tin mơ hồ, yêu cầu người dùng chọn | Báo lỗi có hai lần 02:30 |
| **EARLIER** | Chọn lần xảy ra **trước** | `+02:00` → `00:30Z` |
| **LATER** | Chọn lần xảy ra **sau** | `+01:00` → `01:30Z` |

Có thể áp dụng `withEarlierOffsetAtOverlap()` hoặc `withLaterOffsetAtOverlap()` trên một `ZonedDateTime` đã giải quyết cùng local/zone:

```java
ZonedDateTime defaultValue =
        LocalDateTime.of(2024, 10, 27, 2, 30)
                .atZone(ZoneId.of("Europe/Berlin"));

ZonedDateTime first =
        defaultValue.withEarlierOffsetAtOverlap();

ZonedDateTime second =
        defaultValue.withLaterOffsetAtOverlap();
```

Đây là đoạn trong phương thức. Khi không ở overlap, hai phương thức `with...OffsetAtOverlap` **không có tác dụng**. Chúng không phải công cụ sửa gap; gap cần một chính sách riêng.

### 6.1. `ofLocal` với preferred offset

`ZonedDateTime.ofLocal(local, zone, preferredOffset)` cho phép chỉ định **offset ưu tiên**. Khi overlap và offset đó là một trong hai offset hợp lệ, Java dùng nó; nếu ưu tiên không hợp lệ, Java rơi về offset sớm hơn. Khi gap, nó vẫn dịch giờ lên theo độ dài gap.

```java
ZonedDateTime chosen = ZonedDateTime.ofLocal(
        LocalDateTime.of(2024, 10, 27, 2, 30),
        ZoneId.of("Europe/Berlin"),
        ZoneOffset.ofHours(1));
```

Đây là đoạn trong phương thức: kết quả chọn `02:30+01:00[Europe/Berlin]`. **Không dùng `ofLocal` làm cơ chế kiểm tra strict** nếu nghiệp vụ muốn từ chối offset không hợp lệ; dùng `ofStrict` hoặc kiểm tra `getValidOffsets`.

### 6.2. `ofStrict` với offset đúng và sai

```java
ZonedDateTime late = ZonedDateTime.ofStrict(
        LocalDateTime.of(2024, 10, 27, 2, 30),
        ZoneOffset.ofHours(1),
        ZoneId.of("Europe/Berlin"));
```

Đây là đoạn trong phương thức và **hợp lệ** vì `+01:00` là offset thứ hai của overlap. Nếu thay thành `+03:00`, `ofStrict` ném `DateTimeException` dù ngày giờ cục bộ vẫn ở overlap — offset `+03:00` không thuộc danh sách hợp lệ của Berlin lúc đó.

**Tránh tạo hai cách hiểu chỉ từ số offset:** Với hai offset `+02:00`/`+01:00`, mô tả cho người dùng là “lần 02:30 đầu tiên / lần 02:30 thứ hai”, hoặc thể hiện offset và timezone, thay vì nói trống “offset lớn hơn” / “offset nhỏ hơn”.

## 7. Java 17+: Chính sách quyết định tường minh, chạy được

Tạo file **`DstResolutionPoliciesDemo.java`**. Chương trình minh họa **cả ba trường hợp normal/gap/overlap**, không bọc mọi kết quả trong một `atZone` mặc định, và không bỏ qua lựa chọn của domain:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;
import java.util.Objects;

public class DstResolutionPoliciesDemo {
    enum GapPolicy {
        REJECT, SHIFT_FORWARD, NEXT_VALID
    }

    enum OverlapPolicy {
        REJECT, EARLIER, LATER
    }

    static ZonedDateTime resolve(
            LocalDateTime local,
            ZoneId zone,
            GapPolicy gapPolicy,
            OverlapPolicy overlapPolicy
    ) {
        Objects.requireNonNull(local, "local");
        Objects.requireNonNull(zone, "zone");
        Objects.requireNonNull(gapPolicy, "gapPolicy");
        Objects.requireNonNull(overlapPolicy, "overlapPolicy");

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> offsets = rules.getValidOffsets(local);

        if (offsets.size() == 1) {
            return ZonedDateTime.ofStrict(
                    local, offsets.get(0), zone);
        }

        if (offsets.isEmpty()) {
            ZoneOffsetTransition transition =
                    rules.getTransition(local);

            return switch (gapPolicy) {
                case REJECT ->
                        throw new DateTimeException(
                                "nonexistent local time");
                case SHIFT_FORWARD -> local.atZone(zone);
                case NEXT_VALID ->
                        transition.getDateTimeAfter().atZone(zone);
            };
        }

        // Hai offsets hợp lệ trong overlap.
        return switch (overlapPolicy) {
            case REJECT ->
                    throw new DateTimeException(
                            "ambiguous local time");
            case EARLIER -> ZonedDateTime.ofStrict(
                    local, offsets.get(0), zone);
            case LATER -> ZonedDateTime.ofStrict(
                    local, offsets.get(1), zone);
        };
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 31, 2, 30);
        LocalDateTime overlap =
                LocalDateTime.of(2024, 10, 27, 2, 30);

        System.out.println("Gap shift: " + resolve(
                gap, berlin,
                GapPolicy.SHIFT_FORWARD, OverlapPolicy.EARLIER));

        System.out.println("Gap next valid: " + resolve(
                gap, berlin,
                GapPolicy.NEXT_VALID, OverlapPolicy.EARLIER));

        System.out.println("Overlap earlier: " + resolve(
                overlap, berlin,
                GapPolicy.REJECT, OverlapPolicy.EARLIER));

        System.out.println("Overlap later: " + resolve(
                overlap, berlin,
                GapPolicy.REJECT, OverlapPolicy.LATER));

        try {
            resolve(gap, berlin,
                    GapPolicy.REJECT, OverlapPolicy.EARLIER);
            System.out.println("Gap rejected: false");
        } catch (DateTimeException ex) {
            System.out.println("Gap rejected: true");
        }

        try {
            resolve(overlap, berlin,
                    GapPolicy.REJECT, OverlapPolicy.REJECT);
            System.out.println("Overlap rejected: false");
        } catch (DateTimeException ex) {
            System.out.println("Overlap rejected: true");
        }
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 DstResolutionPoliciesDemo.java
java DstResolutionPoliciesDemo
```

**Stdout với quy tắc Berlin năm 2024:**

```text
Gap shift: 2024-03-31T03:30+02:00[Europe/Berlin]
Gap next valid: 2024-03-31T03:00+02:00[Europe/Berlin]
Overlap earlier: 2024-10-27T02:30+02:00[Europe/Berlin]
Overlap later: 2024-10-27T02:30+01:00[Europe/Berlin]
Gap rejected: true
Overlap rejected: true
```

**Điểm quan trọng của thiết kế:**

1. **Normal:** offset duy nhất được dùng qua `ZonedDateTime.ofStrict`. Không cần áp dụng gap/overlap policy.
2. **Gap:** `getValidOffsets` rỗng; `NEXT_VALID` dùng **mốc sau chuyển tiếp** (`getDateTimeAfter()`), khác với `SHIFT_FORWARD` là `atZone` giữ số phút bằng cách cộng độ dài gap.
3. **Overlap:** danh sách có hai offset và được sắp theo thứ tự trước/sau của transition; `ofStrict` xác minh offset đã chọn.
4. **REJECT:** chương trình ném `DateTimeException` thay vì âm thầm tự ý đổi giờ.
5. Hai enum `GapPolicy` và `OverlapPolicy` làm hợp đồng rõ hơn một cờ boolean “useLate” vốn có thể mơ hồ hoặc không áp dụng trong gap.
6. Trong ứng dụng thực tế, thay việc in một thông báo thành phản hồi validation có thể hiểu được cho người dùng (ví dụ hiển thị danh sách offset/instant hợp lệ để họ chọn).
7. Mã ví dụ giả định hành vi ZoneRules chuẩn với 0/1/2 offset. Luôn xác minh chính vùng, ngày, version tzdb thực tế đang dùng và kiểm tra chính sách của hệ thống trước khi đưa vào lịch thật.

## 8. `ZoneRules.getValidOffsets` và `getTransition`: Khi nào dùng từng API?

**Kiểm tra một local date-time:**

```java
ZoneRules rules = ZoneId.of("Europe/Berlin").getRules();
LocalDateTime local = LocalDateTime.of(2024, 10, 27, 2, 30);

List<ZoneOffset> offsets = rules.getValidOffsets(local);
boolean validFirst = rules.isValidOffset(
        local, ZoneOffset.ofHours(2));
ZoneOffsetTransition transition = rules.getTransition(local);
```

Đây là đoạn mã trong phương thức, cần các import `java.time.`, `java.time.zone.`, `java.util.List`.

- `getValidOffsets`: **0/1/2 offset** hợp lệ cho local time, đủ để nhận biết normal/gap/overlap.
- `isValidOffset(local, offset)`: kiểm tra một lựa chọn offset cụ thể có hợp lệ hay không.
- `getTransition(local)`: lấy thông tin transition khi local nằm trong gap/overlap; có thể `null` nếu không có transition ở local này.
- `getOffset(local)`: cung cấp một offset “best effort”; ở gap/overlap thường trả offset **trước chuyển tiếp**. Không dùng nó để khẳng định local time chỉ có một nghĩa.
- `getOffset(instant)`: từ một instant, tìm offset thực sự theo quy tắc zone; không có vấn đề chọn giữa hai instant vì instant đã được xác định.

### 8.1. Đọc transition mà không hard-code 1 giờ

```java
ZoneOffsetTransition transition =
        rules.getTransition(local);

if (transition != null && transition.isOverlap()) {
    ZoneOffset before = transition.getOffsetBefore();
    ZoneOffset after = transition.getOffsetAfter();
    // Hệ thống có thể hiển thị before/after để người dùng chọn.
}
```

Đây là đoạn minh họa trong phương thức. Với gap Berlin 31/03/2024, transition có `getOffsetBefore() == +01:00`, `getOffsetAfter() == +02:00` và `getDuration() == PT1H`. Với overlap Berlin 27/10/2024, chiều đổi offset đảo ngược; `getDuration()` âm, và `isOverlap() == true`.

Những chuyển đổi này là **dữ liệu lịch sử** trong zone rules, không phải một hằng luật chung cho mọi quốc gia và năm. Nếu độ dài gap là nửa giờ hoặc nhiều giờ, không ép nó về một giờ trong code.

## 9. `Instant` trước, rồi `atZone`: Không có ambiguity đầu vào

Khi một hệ thống đã biết thời điểm diễn ra, chẳng hạn một sự kiện server có UTC timestamp, nó **không cần lựa chọn gap/overlap** khi chuyển sang một zone để hiển thị.

```java
Instant firstInstant =
        Instant.parse("2024-10-27T00:30:00Z");
Instant secondInstant =
        Instant.parse("2024-10-27T01:30:00Z");

ZonedDateTime first = firstInstant.atZone(
        ZoneId.of("Europe/Berlin"));
ZonedDateTime second = secondInstant.atZone(
        ZoneId.of("Europe/Berlin"));
```

Đây là đoạn trong phương thức. Hai kết quả lần lượt là:

```text
2024-10-27T02:30+02:00[Europe/Berlin]
2024-10-27T02:30+01:00[Europe/Berlin]
```

**Cùng local 02:30 nhưng hai offset/instant khác nhau**, và khi bắt đầu từ Instant, mỗi kết quả được xác định duy nhất.

Nguyên tắc lưu dữ liệu:

- Đối với **sự kiện đã xảy ra**: lưu `Instant` (hoặc timestamp chuẩn UTC) để so sánh thời gian và xác định trật tự.
- Đối với **lịch hẹn người dùng nhập trước khi diễn ra**: lưu local date-time, `ZoneId` vùng và **quy tắc chọn gap/overlap** (và có thể cả instant đã giải quyết), vì timezone rules có thể thay đổi theo phiên bản dữ liệu.
- Đối với **lịch lặp lại 09:00 mỗi ngày ở một địa phương**: lưu `LocalTime` + `ZoneId` + rule về ngày/lần lặp; **không chỉ thêm 24 giờ lên một Instant** nếu muốn giữ 09:00 trên đồng hồ địa phương xuyên mùa chuyển giờ.

Chọn cấu trúc lưu trữ dựa trên ý nghĩa: một *instant cố định*, một *local appointment* hay một *recurrence* cần được tính lại khi lịch vùng thay đổi.

## 10. `withZoneSameInstant` khác `withZoneSameLocal`

Sau khi đã có `ZonedDateTime`, bạn có thể chuyển sang một vùng khác theo hai ý định khác nhau:

- `withZoneSameInstant(targetZone)`: **giữ đúng thời điểm UTC**, đổi đồng hồ địa phương để hiển thị ở vùng mới.
- `withZoneSameLocal(targetZone)`: **cố giữ cùng chữ số ngày–giờ**, áp dụng luật vùng mới; **instant thường thay đổi** và nếu local mới rơi vào gap thì có thể bị dịch.

Ví dụ 01/07/2024 10:00 ở Berlin (offset `+02:00`), chuyển sang `Asia/Ho_Chi_Minh`:

```text
Berlin gốc:   2024-07-01T10:00+02:00[Europe/Berlin]
SameInstant:  2024-07-01T15:00+07:00[Asia/Ho_Chi_Minh]
SameLocal:    2024-07-01T10:00+07:00[Asia/Ho_Chi_Minh]
```

`SameInstant` giữ UTC `08:00Z`; `SameLocal` chọn UTC `03:00Z`. Đổi múi giờ để **hiển thị một giao dịch đã xảy ra** phải chọn `withZoneSameInstant`, không chọn `withZoneSameLocal`.

### 10.1. Ví dụ Java 17+ độc lập

Tạo file **`ZoneConversionDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZoneConversionDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");

        ZonedDateTime summer = LocalDateTime.of(
                2024, 7, 1, 10, 0).atZone(berlin);

        ZonedDateTime sameInstant =
                summer.withZoneSameInstant(hcm);
        ZonedDateTime sameLocal =
                summer.withZoneSameLocal(hcm);

        System.out.println("Berlin summer: " + summer);
        System.out.println("Same instant: " + sameInstant);
        System.out.println("Same local: " + sameLocal);
        System.out.println("Instant kept: "
                + summer.toInstant()
                        .equals(sameInstant.toInstant()));
        System.out.println("Instant changed: "
                + !summer.toInstant()
                        .equals(sameLocal.toInstant()));

        Instant first =
                Instant.parse("2024-10-27T00:30:00Z");
        Instant second =
                Instant.parse("2024-10-27T01:30:00Z");

        System.out.println("First from instant: "
                + first.atZone(berlin));
        System.out.println("Second from instant: "
                + second.atZone(berlin));
    }
}
```

Chạy:

```bash
javac --release 17 ZoneConversionDemo.java
java ZoneConversionDemo
```

**Stdout:**

```text
Berlin summer: 2024-07-01T10:00+02:00[Europe/Berlin]
Same instant: 2024-07-01T15:00+07:00[Asia/Ho_Chi_Minh]
Same local: 2024-07-01T10:00+07:00[Asia/Ho_Chi_Minh]
Instant kept: true
Instant changed: true
First from instant: 2024-10-27T02:30+02:00[Europe/Berlin]
Second from instant: 2024-10-27T02:30+01:00[Europe/Berlin]
```

Điều cần nhớ: `ZoneOffset` và `ZoneId` là hai lớp thông tin khác nhau. Một chuỗi chỉ có `+02:00` xác định offset cho một thời điểm, nhưng không đủ mô tả quy tắc tương lai của Berlin. Khi kết nối các hệ thống, đừng xóa `ZoneId` chỉ vì hiện tại đã biết offset.

## 11. `plusDays(1)` không luôn bằng `plusHours(24)`

Ở vùng có chuyển đồng hồ, **một ngày lịch địa phương** không phải lúc nào cũng có 24 giờ thực tế. `ZonedDateTime.plusDays(1)` hoạt động trên **local timeline** (dịch ngày, giải quyết lại zone), trong khi `plusHours(24)` dịch **24 giờ trên instant timeline**.

Ví dụ vào ngày chuyển sang DST ở Berlin:

```text
2024-03-30T12:00+01:00[Europe/Berlin]
  + 1 calendar day -> 2024-03-31T12:00+02:00[Europe/Berlin]
  + 24 hours       -> 2024-03-31T13:00+02:00[Europe/Berlin]
```

Khoảng cách thực từ gốc đến `plusDays(1)` chỉ **23 giờ** vì đồng hồ nhảy tới một giờ. Ở nhiều đợt chuyển ngược về mùa đông, khoảng một ngày lịch có thể là **25 giờ**.

Khi nghiệp vụ yêu cầu:

- “Mỗi ngày lúc 12:00 theo giờ địa phương” → thao tác theo **ngày/giờ địa phương** và giải quyết lại vùng theo policy.
- “Sau chính xác 24 giờ kể từ lúc bắt đầu” → dùng `Duration.ofHours(24)`/`plusHours(24)` hoặc `Instant.plus(...)`.
- “Đến hết ngày làm việc thứ N” → cần `LocalDate`, lịch làm việc/holiday calendar và zone.
- “Sau một tháng lịch” → dùng `plusMonths` với quy tắc điều chỉnh ngày, **không nhân số ngày cố định**.

### 11.1. Ví dụ Java 17+ có kết quả xác định

Tạo file **`ZonedArithmeticDemo.java`**:

```java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedArithmeticDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0, berlin);

        ZonedDateTime calendarDay = start.plusDays(1);
        ZonedDateTime twentyFourHours =
                start.plusHours(24);

        long hoursInCalendarDay = Duration.between(
                start.toInstant(),
                calendarDay.toInstant()
        ).toHours();

        System.out.println("Start: " + start);
        System.out.println("Plus day: " + calendarDay);
        System.out.println("Plus 24h: " + twentyFourHours);
        System.out.println("Hours in day: "
                + hoursInCalendarDay);
    }
}
```

Chạy:

```bash
javac --release 17 ZonedArithmeticDemo.java
java ZonedArithmeticDemo
```

**Stdout:**

```text
Start: 2024-03-30T12:00+01:00[Europe/Berlin]
Plus day: 2024-03-31T12:00+02:00[Europe/Berlin]
Plus 24h: 2024-03-31T13:00+02:00[Europe/Berlin]
Hours in day: 23
```

Không dùng `Duration.between(localBefore, localAfter)` làm thước đo chính xác của **thời gian thực** qua thay đổi timezone: `LocalDateTime` không biết offset. Chuyển hai điểm đã giải quyết sang `Instant` rồi mới đo `Duration`.

## 12. Các cách tạo ZonedDateTime: Chọn đúng mức độ kiểm soát

| API | Hành vi | Phù hợp khi |
| --- | --- | --- |
| `local.atZone(zone)` | Tự dịch gap, ưu tiên offset sớm ở overlap | Chính sách mặc định đã được chấp nhận |
| `ZonedDateTime.of(local, zone)` | Quy tắc gap/overlap tương tự `atZone` | Muốn gọi factory tường minh |
| `ZonedDateTime.ofLocal(local, zone, preferredOffset)` | Dùng preferred offset **nếu hợp lệ**, nếu không fallback; gap tự dịch | Có offset ưu tiên nhưng vẫn cho phép fallback |
| `ZonedDateTime.ofStrict(local, offset, zone)` | Offset phải hợp lệ, sai thì ném exception | Muốn chấp nhận một offset đã chọn và xác minh chặt |
| `instant.atZone(zone)` | Chuyển từ instant duy nhất | Hiển thị thời điểm đã xảy ra |
| `ZonedDateTime.ofInstant(instant, zone)` | Tương tự bắt đầu từ Instant | Hệ thống có UTC timestamp |
| `zdt.withEarlierOffsetAtOverlap()` | Chọn offset sớm của overlap, nếu có | Chính sách chọn lần đầu |
| `zdt.withLaterOffsetAtOverlap()` | Chọn offset muộn của overlap, nếu có | Chính sách chọn lần sau |
| `zone.getRules().getValidOffsets(local)` | Trả danh sách hợp lệ, không tự chọn | Domain cần phân loại hoặc hỏi người dùng |
| `zone.getRules().getTransition(local)` | Trả transition của gap/overlap, nếu có | Cần độ dài gap và mốc sau chuyển tiếp |

**Không có một phương thức nào “đọc suy nghĩ” ý định người dùng.** Java đặt ra default để thao tác dễ dàng, còn quy tắc “có dịch lịch không, dịch ra sao, nếu cùng giờ xảy ra hai lần thì chọn lần nào” thuộc domain.

### 12.1. Phân biệt `ofInstant(local, offset, zone)` và `ofStrict`

Có overload `ZonedDateTime.ofInstant(LocalDateTime, ZoneOffset, ZoneId)` diễn giải cặp `(local, offset)` như **một instant đã xác định**, rồi biểu diễn lại trong `zone`. Nếu offset cung cấp **không hợp lệ** cho local time của vùng đó, **local time kết quả có thể khác** để giữ instant. Đây không phải validation chặt.

`ofStrict`, ngược lại, **kiểm tra** bộ `(local, offset, zone)` có hợp lệ theo luật vùng không và từ chối nếu không. Trong API đặt lịch có thông tin local từ người dùng, đừng dùng hai overload này như thể đồng nghĩa.

## 13. Parse/format: Giữ zone và offset khi cần phân biệt

Chuỗi `2024-10-27T02:30` chỉ là local date-time. Chuỗi `2024-10-27T02:30+02:00` có offset nên xác định được instant; chuỗi `2024-10-27T02:30+02:00[Europe/Berlin]` còn mang **danh tính vùng**.

```java
ZonedDateTime first = ZonedDateTime.parse(
        "2024-10-27T02:30+02:00[Europe/Berlin]");
ZonedDateTime second = ZonedDateTime.parse(
        "2024-10-27T02:30+01:00[Europe/Berlin]");
```

Đây là đoạn trong phương thức; cả hai biểu diễn hai instant khác nhau và các offset này hợp lệ trong overlap Berlin 2024.

Lưu ý khi trao đổi dữ liệu:

1. Nếu API client chỉ gửi **local date-time**, server cần `ZoneId` và **policy** hoặc phải yêu cầu người dùng chọn khi ambiguity.
2. Nếu client gửi **offset**, có thể xác định instant, nhưng vẫn nên xác minh offset có hợp lệ **với zone vùng mà người dùng định chọn** hay không nếu contract yêu cầu.
3. Nếu client gửi **Instant**, hiển thị giờ địa phương theo `zone`, không áp dụng “lựa chọn” gap/overlap ở chiều chuyển này.
4. Với **recurrence**, một offset cố định không thay thế được region zone; lần lặp sau có thể rơi vào thời điểm có offset khác.
5. `DateTimeFormatter.ISO_ZONED_DATE_TIME` có thể dùng format/parse chuẩn chứa offset và zone. Không coi cách hiển thị có tên viết tắt như CET/CEST là khóa vùng bất biến cho mọi bối cảnh.

### 13.1. Không dùng định dạng local làm khóa duy nhất của sự kiện

Nếu database chỉ dùng `(zone, localDateTime)` làm khóa duy nhất, hai sự kiện trong overlap có thể bị **gộp sai**, dù chúng diễn ra ở hai instant khác nhau. Khi sự kiện đại diện cho một thời điểm đã giải quyết, khóa nên được xây từ định danh sự kiện/Instant hoặc từ bộ thông tin đủ để phân biệt **offset/lần xuất hiện** theo contract.

Ngược lại, với lịch lặp “mỗi ngày lúc 02:30 tại Berlin”, chỉ lưu Instant sẽ đánh mất ý nghĩa “02:30 theo đồng hồ địa phương” ở lần tiếp theo. Thường cần cả lịch gốc và chính sách xử lý gap/overlap.

## 14. Chọn chính sách theo nghiệp vụ, không đoán

### 14.1. Đặt chỗ có mặt trực tiếp

Người dùng đặt lịch khám/học/làm việc tại một chi nhánh theo giờ địa phương. Khi gap, **nên thông báo không có giờ 02:30 và yêu cầu chọn lại**, hoặc làm rõ rule dịch lên giờ hợp lệ. Khi overlap, **hiển thị hai lựa chọn cụ thể** nếu hai lần 02:30 có thể được dùng như hai suất riêng.

Không âm thầm đổi giờ/đặt sai suất nếu sự thay đổi ảnh hưởng đến quyền lợi hoặc gây nhầm lịch.

### 14.2. Một tác vụ lặp định kỳ

Yêu cầu “chạy mỗi ngày lúc 02:30 tại Berlin” cần chính sách:

- Vào ngày gap: **bỏ qua lần chạy**, **dịch theo gap** hay **chạy ngay mốc hợp lệ tiếp theo**?
- Vào ngày overlap: **chạy lần đầu**, **chạy lần sau**, **chạy cả hai** hay **chỉ chạy một lần theo một policy**?
- Nếu chính phủ đổi múi giờ trong tương lai: giữ theo local 02:30 ở khu vực hay giữ khoảng cách tuyệt đối giữa các lần thực thi?

`atZone` mặc định chỉ chọn **một** kết quả; nó không tự quyết định số lần công việc phải chạy trong overlap. Muốn **chạy cả hai**, domain phải chủ động sinh **hai instants** từ hai offsets hợp lệ. Muốn **bỏ qua gap**, domain phải từ chối/bỏ qua slot thay vì dùng `atZone` mặc định sẽ dịch nó.

### 14.3. Giao dịch, audit, logging

Với sự kiện đã xảy ra, hệ thống có thể ghi `Instant` để bảo đảm sắp xếp chính xác, cộng với `ZoneId`/offset hiển thị khi cần bối cảnh. Không dùng local time không offset làm timestamp duy nhất cho audit trong vùng có overlap.

### 14.4. Booking toàn cầu và hệ thống phân tán

Một service có thể có server ở nhiều timezone. **Đừng dựa vào `ZoneId.systemDefault()` hoặc `LocalDateTime.now()`** cho business rule mà không nêu rõ zone. Dùng `Clock` được inject, `ZoneId` của địa điểm kinh doanh hoặc zone đã được người dùng chọn theo hợp đồng.

**Không coi giờ UTC như giờ địa phương:** Nếu lưu một UTC instant đúng mà sau đó gọi `withZoneSameLocal` thay vì `withZoneSameInstant`, bạn đã thay đổi thời điểm sự kiện trong lúc đổi vùng hiển thị.

## 15. Quản lý thay đổi quy tắc múi giờ và tzdb

`ZoneId` dạng region là ID của bộ luật lịch sử/tương lai; `ZoneRules` do JDK cung cấp. Các quốc gia có thể sửa giờ mùa hè, xóa/đặt lịch chuyển đổi hoặc thay offset, và **tzdb có thể cập nhật qua phiên bản JDK**.

Do đó:

- Hãy **dùng `ZoneId.of("Europe/Berlin")`** thay vì hard-code `ZoneOffset.ofHours(1)` khi thật sự muốn lịch Berlin.
- Đừng viết thuật toán giả định mọi gap/overlap đều dài một giờ; `ZoneOffsetTransition.getDuration()` giúp lấy chuyển đổi thực tế.
- Những ví dụ Berlin 2024 ở đây dựa trên các chuyển đổi **đã xảy ra**, phù hợp cho học cơ chế; đừng lấy chúng làm bằng chứng luật tương lai không đổi.
- Với lịch dự kiến xa trong tương lai, hãy xác định việc **cập nhật lịch/đặt lại Instant** nếu tzdb thay đổi thuộc trách nhiệm dịch vụ nào và người dùng được thông báo ra sao.
- Đối với audit, lưu **Instant đã được thực thi**; nếu cần tái dựng vì sao lịch hẹn ban đầu được chọn như vậy, có thể lưu thêm local, zone, policy và offset/phiên bản nguồn quy tắc khi khả thi.
- `ZoneRulesProvider` là cơ chế tra cứu rules; không nên tạo offset thủ công rồi nghĩ đã phản ánh đủ luật lịch sử toàn vùng.

**Tính đúng của đoạn mã ≠ tính đúng của chính sách.** Lịch doanh nghiệp cần làm rõ trường hợp mơ hồ ngay trong yêu cầu sản phẩm, rồi mới chọn API.

## 16. Bộ kiểm thử biên nên có

| Ca kiểm thử | Ví dụ | Điều phải xác nhận |
| --- | --- | --- |
| Normal winter | Berlin 2024-01-15 12:00 | Đúng một offset +01 |
| Normal summer | Berlin 2024-07-01 12:00 | Đúng một offset +02 |
| Ngay trước gap | Berlin 2024-03-31 01:59 | Giờ vẫn hợp lệ |
| Trong gap | Berlin 2024-03-31 02:30 | 0 offsets; policy được áp dụng |
| Ngay sau gap | Berlin 2024-03-31 03:00 | Giờ hợp lệ, offset +02 |
| Trong overlap | Berlin 2024-10-27 02:30 | 2 offsets, 2 instants |
| Trước/lúc sau overlap | Berlin 2024-10-27 01:59/03:00 | Một offset, đúng giai đoạn |
| Strict gap | `ofStrict(gap, +01, zone)` | Ném exception |
| Strict overlap offset đúng | `ofStrict(overlap, +01, zone)` | Chấp nhận |
| Strict offset sai | `ofStrict(overlap, +03, zone)` | Ném exception |
| Shift và next valid | 02:30 gap | 03:30 khác 03:00 |
| Đổi zone giữ instant | Berlin → Ho Chi Minh City | `toInstant` không đổi |
| Đổi zone giữ local | Berlin → Ho Chi Minh City | Instant có thể thay đổi |
| Cộng ngày/giờ qua DST | 2024-03-30 12:00 | plusDays(1) khác plusHours(24) |
| Lặp qua overlap | 02:30 | Số lần chạy đúng policy (1 hoặc 2) |
| Zone fixed offset | `ZoneOffset.UTC` | Không áp dụng gap/overlap của vùng |
| Thay đổi tzdb | Recalculate lịch tương lai | Chính sách versioning rõ ràng |
| Null/unknown zone | `ZoneId.of("bad-zone")` | Báo lỗi input, không fallback sang máy chủ |

Với unit test, cố định **ngày cụ thể**, **zone cụ thể** và điều kiện kỳ vọng. Đừng lấy `LocalDateTime.now()` hay ngày chuyển giờ của năm đang chạy để tạo test phụ thuộc thời gian. Trong ứng dụng nhận thời gian thực, kiểm tra dữ liệu phiên bản tzdb ở môi trường triển khai nếu điều đó ảnh hưởng đến nghiệp vụ.

## 17. Java 17+: Bài kiểm tra tự động, không phụ thuộc cờ -ea

Tạo file **`DstBoundaryChecks.java`**:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstBoundaryChecks {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Berlin");
        ZoneRules rules = zone.getRules();

        LocalDateTime normal =
                LocalDateTime.of(2024, 1, 15, 12, 0);
        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 31, 2, 30);
        LocalDateTime overlap =
                LocalDateTime.of(2024, 10, 27, 2, 30);

        check(rules.getValidOffsets(normal).size() == 1,
                "normal must have one offset");
        check(rules.getValidOffsets(gap).isEmpty(),
                "gap must have no offsets");
        System.out.println("Normal and gap: PASS");

        List<ZoneOffset> offsets =
                rules.getValidOffsets(overlap);
        check(offsets.size() == 2,
                "overlap must have two offsets");
        check(offsets.get(0).equals(ZoneOffset.ofHours(2)),
                "wrong earlier offset");
        check(offsets.get(1).equals(ZoneOffset.ofHours(1)),
                "wrong later offset");
        System.out.println("Overlap offsets: PASS");

        ZonedDateTime earlier = overlap.atZone(zone);
        ZonedDateTime later =
                earlier.withLaterOffsetAtOverlap();

        check(Duration.between(
                earlier.toInstant(), later.toInstant())
                .toHours() == 1, "wrong instant difference");
        System.out.println("Two instants: PASS");

        check(gap.atZone(zone)
                .toLocalDateTime()
                .equals(LocalDateTime.of(
                        2024, 3, 31, 3, 30)),
                "gap did not shift by duration");
        check(rules.getTransition(gap)
                .getDateTimeAfter()
                .equals(LocalDateTime.of(
                        2024, 3, 31, 3, 0)),
                "incorrect next valid local time");
        System.out.println("Gap policies: PASS");

        boolean rejectedGap = false;
        try {
            ZonedDateTime.ofStrict(
                    gap, ZoneOffset.ofHours(1), zone);
        } catch (DateTimeException ex) {
            rejectedGap = true;
        }
        check(rejectedGap, "ofStrict accepted gap");
        System.out.println("Strict validation: PASS");

        Instant instant =
                Instant.parse("2024-10-27T01:30:00Z");
        check(instant.atZone(zone)
                .toLocalDateTime().equals(overlap),
                "wrong local from instant");
        check(instant.atZone(zone)
                .getOffset().equals(ZoneOffset.ofHours(1)),
                "wrong offset from instant");
        System.out.println("Instant conversion: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 DstBoundaryChecks.java
java DstBoundaryChecks
```

**Stdout:**

```text
Normal and gap: PASS
Overlap offsets: PASS
Two instants: PASS
Gap policies: PASS
Strict validation: PASS
Instant conversion: PASS
```

`check` chủ động ném `AssertionError` nên test hoạt động mà không cần bật `-ea`. Bộ dữ liệu minh họa các transition của Berlin 2024; có thể kiểm tra tương tự cho zone, lịch sử và các edge case được sản phẩm thực sự hỗ trợ. Kiểm thử hành vi Java **chưa thay thế** kiểm thử lựa chọn chính sách của nghiệp vụ.

## 18. Lỗi phổ biến cần tránh

1. **Gọi `atZone` và nghĩ chỉ gắn nhãn ZoneId:** hàm có thể thay **local time** khi gap.
2. **Nghĩ mỗi LocalDateTime ở mọi zone đều chỉ có một instant:** gap 0, overlap 2.
3. **Nghĩ `atZone` ném exception ở gap:** mặc định dịch theo độ dài gap.
4. **Nghĩ `atZone` luôn chọn lần xuất hiện sau trong overlap:** mặc định chọn earlier offset.
5. **Gộp “dịch theo gap” và “mốc hợp lệ đầu tiên” thành một:** Berlin 02:30 tạo 03:30 và 03:00.
6. **Hard-code gap luôn một giờ:** thay đổi offset có thể khác 1 giờ; đọc transition.
7. **Gọi `ZoneRules.getOffset(local)` rồi cho là local hợp lệ:** API trả best offset ngay cả gap/overlap.
8. **Dùng `getTransition(local)` không kiểm tra null:** normal không có transition tương ứng.
9. **Dùng `ofLocal` như validator strict:** preferred offset có thể bị bỏ qua và fallback.
10. **Dùng `ofInstant(local, offset, zone)` thay cho `ofStrict`:** ofInstant bảo toàn instant, không xác nhận local + offset hợp lệ trong zone.
11. **Dùng `withLaterOffsetAtOverlap` để “sửa” gap:** nó chỉ có hiệu lực ở overlap.
12. **Nhầm earlier/later offset với so sánh số học của `+01`/`+02`:** tên gọi dựa trên hai lần xuất hiện ở chuyển tiếp.
13. **Chỉ lưu `LocalDateTime` cho giao dịch audit:** mất thông tin instant trong overlap.
14. **Chỉ lưu offset fixed cho lịch lặp theo vùng:** không có luật offset thay đổi theo mùa hoặc pháp luật.
15. **Chuyển timezone bằng `withZoneSameLocal` khi muốn hiển thị sự kiện đã xảy ra:** instant bị thay đổi.
16. **Coi `plusDays(1)` là đúng 24 giờ mọi ngày:** local calendar day qua DST có thể 23/25 giờ.
17. **Lưu hai sự kiện overlap dưới cùng một khóa local:** hai instants có thể bị gộp.
18. **Dùng `ZoneId.systemDefault()` cho hợp đồng toàn cầu:** server có thể chạy ở zone khác địa điểm.
19. **Coi luật 2024 Berlin là luật vĩnh viễn:** tzdb và quy định quốc gia có thể thay đổi.
20. **Tự động đổi giờ đặt hẹn mà không thông báo:** có thể sai ý định người dùng.
21. **Tưởng `ZonedDateTime` có thể sửa tại chỗ:** các kiểu `java.time` bất biến, method trả instance mới.
22. **Coi hai ZonedDateTime có local bằng nhau là cùng instant:** cần so `toInstant()` hoặc sử dụng API so sánh theo timeline.
23. **Coi hai ZonedDateTime ở zone khác nhau là khác thời điểm dù instant bằng nhau:** `equals` so nhiều thành phần, còn so cùng thời điểm dùng `toInstant().equals(...)` hoặc `isEqual(...)`.
24. **Tự sinh hai lần thực thi ở overlap chỉ bằng một lời gọi `atZone`:** phải kiểm tra hai offsets và chủ động xác định 1 hoặc 2 instants.
25. **Dựa vào thời gian hiện tại để test chuyển giờ:** dùng ngày cố định và kiểm soát tzdb trong môi trường.

## 19. Checklist thiết kế hệ thống giải quyết thời gian không duy nhất

Trước khi đưa một thời gian cục bộ vào scheduler/booking/API, hãy trả lời:

1. Đầu vào đang là **Instant** hay **LocalDateTime**? Chỉ local mới có thể cần chọn gap/overlap khi gán zone.
2. Có lưu **ZoneId dạng region** thay vì chỉ fixed offset không?
3. Có kiểm tra `rules.getValidOffsets(local)` trước khi cam kết thời điểm hay không?
4. Nếu **gap**, sẽ REJECT, SHIFT_FORWARD_BY_GAP, NEXT_VALID_LOCAL_TIME hay SKIP lần lịch? Đây có phải quyết định được người dùng biết không?
5. Nếu **overlap**, sẽ chọn EARLIER, LATER, REJECT, hay tạo **hai** lần sự kiện?
6. Khi có offset được người dùng gửi, có xác minh nó thuộc `rules.getValidOffsets(local)` của vùng đó không?
7. Đã phân biệt `ofStrict` với `ofLocal` và `ofInstant` chưa?
8. Mốc “sau một ngày” có nghĩa **ngày lịch địa phương** hay **24 giờ tuyệt đối**?
9. Dữ liệu lưu có đủ để tái dựng **Instant đã giải quyết** và bối cảnh lịch người dùng muốn không?
10. Nếu tzdb thay đổi trong tương lai, sự kiện lặp và lịch đã đặt sẽ được **tính lại hay giữ nguyên instant** theo chính sách nào?
11. Có test bình thường, gap, overlap, offset sai, các ngày sát transition, đổi zone và khoảng duration không?
12. Nếu hiển thị hai lần 02:30, giao diện có ghi rõ offset/lần xuất hiện để người dùng hiểu sự khác nhau không?

## 20. Câu hỏi tự kiểm tra

1. Tại sao `LocalDateTime.of(2024,10,27,2,30)` ở Berlin chưa xác định một Instant duy nhất?
2. `rules.getValidOffsets(local)` có thể trả số lượng bao nhiêu? Ý nghĩa của từng trường hợp?
3. `LocalDateTime.of(2024,3,31,2,30).atZone(Berlin)` cho local time nào trong ví dụ? Vì sao không phải 03:00?
4. Nếu nghiệp vụ chọn **mốc local hợp lệ đầu tiên sau gap**, API nào cung cấp mốc đó?
5. `atZone` mặc định chọn offset nào khi overlap? Làm sao chọn lần 02:30 sau?
6. `ZonedDateTime.ofStrict(overlap, +03:00, Berlin)` có thành công không? Tại sao?
7. `ZoneRules.getOffset(LocalDateTime)` có đủ để khẳng định thời gian hợp lệ và duy nhất không?
8. Cùng `2024-10-27T02:30` với `+02:00` và `+01:00` tạo hai Instants nào?
9. `withZoneSameInstant` khác `withZoneSameLocal` như thế nào khi chuyển Berlin sang Ho Chi Minh City?
10. Vì sao `plusDays(1)` khác `plusHours(24)` qua đợt DST spring?
11. Nếu ứng dụng muốn chạy công việc **hai lần** ở overlap, một `atZone` có đủ không?
12. Khi đặt lịch lặp qua nhiều năm, chỉ lưu offset `+01:00` có đủ để giữ lịch địa phương Berlin không?

**Gợi ý:** (1) có hai offsets hợp lệ. (2) 0 = gap, 1 = normal, 2 = overlap. (3) 03:30 vì dịch tiến đúng một giờ, giữ :30. (4) `getTransition(local).getDateTimeAfter()`. (5) earlier offset; dùng `withLaterOffsetAtOverlap()` hoặc `ofStrict` với later offset. (6) không; offset +03 không hợp lệ ở Berlin lúc đó. (7) không; API trả best offset cho gap/overlap. (8) 00:30Z và 01:30Z. (9) cái đầu giữ Instant, cái sau giữ local fields và có thể đổi Instant. (10) ngày lịch địa phương có 23 giờ trong ví dụ. (11) không; chủ động sinh hai Instants. (12) không, cần ZoneId vùng và policy.

**Kết luận:** `LocalDateTime.atZone` là một **phép giải quyết** ngày–giờ cục bộ theo luật vùng, không phải phép đính nhãn vô hại. Trong normal, có một offset; trong gap, không có offset và Java mặc định **dịch tiến giờ**; trong overlap, có hai offset và Java mặc định dùng **lần sớm**. Với ứng dụng thật, hãy nêu **gap policy / overlap policy** tường minh, kiểm tra `ZoneRules`, chọn `ofStrict` khi cần xác nhận offset, giữ `Instant` cho sự kiện đã xảy ra và `ZoneId` cho lịch theo vùng. Đó là cách tránh đặt sai lịch, nhân đôi hoặc làm mất sự kiện khi đồng hồ địa phương thay đổi.

## Tài liệu Java chính thức — API hiện hành

- `LocalDateTime.atZone` — cách giải quyết gap/overlap: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html
- `ZonedDateTime` — `ofLocal`, `ofStrict`, `ofInstant`, `withEarlierOffsetAtOverlap`, `withLaterOffsetAtOverlap` và đổi zone: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html
- `ZoneRules` — `getValidOffsets`, `getOffset`, `getTransition`, `isValidOffset`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html
- `ZoneOffsetTransition` — `isGap`, `isOverlap`, `getDuration`, `getDateTimeAfter`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html
- `ZoneId` — tên vùng và fixed offsets: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html
- `Instant` — một thời điểm UTC: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html
- `Duration` — thời lượng thực tế giữa instants: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html
- Tổng quan `java.time` và các loại local/zoned/instant: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html
