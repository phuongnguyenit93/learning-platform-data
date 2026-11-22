# Thiết kế lịch hẹn giữa nhiều múi giờ bằng Java

## 1. Mục tiêu bài học

Thiết kế lịch hẹn nhiều múi giờ không chỉ là “cộng hoặc trừ vài giờ”. Một buổi họp được tạo lúc 20:00 ở Thành phố Hồ Chí Minh có thể hiển thị là 09:00 ở New York và 14:00 ở London, nhưng **cả ba cách hiển thị phải trỏ về đúng một thời điểm**. Ngoài ra, khi người dùng đặt lịch hằng tuần, múi giờ có thể đổi offset vì giờ mùa hè (*Daylight Saving Time — DST*), và một giờ địa phương có thể không tồn tại hoặc xảy ra hai lần.

Bài này giải quyết đầy đủ những vấn đề thiết kế thực tế bằng API `java.time`:

- Phân biệt **thời điểm tuyệt đối**, **ngày giờ địa phương**, **UTC offset** và **múi giờ IANA**.
- Tạo cuộc hẹn một lần từ `LocalDateTime` cùng `ZoneId` rồi xác định `Instant` duy nhất.
- Hiển thị cùng cuộc hẹn cho nhiều người tham gia theo vùng thời gian riêng.
- Xử lý **DST gap** và **DST overlap** theo chính sách rõ ràng, tránh tự sửa dữ liệu ngoài ý muốn.
- Phân biệt lịch hẹn **một lần** với lịch hẹn **lặp theo giờ địa phương**, đặc biệt khi qua tuần đổi DST.
- Lưu dữ liệu để có thể đặt lại lịch, kiểm tra xung đột và theo dõi thay đổi quy tắc timezone.
- So sánh khoảng thời gian trên timeline, tránh giả định giờ địa phương của các người dùng có thể so trực tiếp.
- Tổ chức mã lỗi, xác thực, kiểm thử, đồng bộ lịch và chính sách thông báo phù hợp.

`java.time` đã có từ Java 8 và **vẫn là API tiêu chuẩn đang được hỗ trợ trong Java hiện đại**. Các ví dụ đầy đủ chạy được với **JDK 17 trở lên**; ví dụ dùng `record` yêu cầu Java 16+. Những phương pháp dựa trên `ZoneId`, `Instant`, `ZonedDateTime`, `Duration` và `ZoneRules` tiếp tục phù hợp trong Java hiện hành.

> **Quy tắc lớn nhất:** Lịch hẹn **một lần đã chốt** nên có một `Instant` xác định. Lịch hẹn **lặp theo giờ địa phương** phải lưu **quy tắc local time + ZoneId**, không chỉ lặp một Instant sau mỗi 168 giờ.

## 2. Mô hình thời gian cần hiểu trước khi viết code

| Kiểu Java | Lưu gì? | Có xác định một mốc trên timeline? | Vai trò trong lịch hẹn |
| --- | --- | --- | --- |
| `Instant` | Thời điểm UTC trên timeline | Có | Mốc bắt đầu/kết thúc một cuộc họp đã xác định |
| `LocalDate` | Ngày theo lịch, không có giờ/zone | Không | Ngày mà người tổ chức chọn |
| `LocalTime` | Giờ trong ngày, không có ngày/zone | Không | Giờ lặp như 09:00 mỗi thứ Hai |
| `LocalDateTime` | Ngày + giờ địa phương, không có offset/zone | **Chưa** | Điều người tổ chức nhập trên form |
| `ZoneId` | Định danh vùng và quy tắc timezone | Không có timestamp riêng | `Asia/Ho_Chi_Minh`, `America/New_York`, `Europe/Paris` |
| `ZoneOffset` | Độ lệch cố định, ví dụ `+07:00` hoặc `-04:00` | Không có timestamp riêng | Offset cụ thể tại một lần diễn ra |
| `ZonedDateTime` | Local date-time + ZoneId + offset đã resolve | Có | Lịch hẹn cụ thể trong vùng địa phương |
| `OffsetDateTime` | Local date-time + offset, **không** giữ ZoneId vùng | Có | API cần truyền timestamp cùng offset |
| `Duration` | Một khoảng thời gian tính theo seconds/nanos | Không phải timestamp | Độ dài buổi họp theo thời gian thực |
| `Period` | Khoảng thời gian theo **ngày/tháng/năm lịch** | Không phải timestamp | Phép toán theo lịch; cần xem chính sách DST |

**Phân biệt ZoneId với ZoneOffset:** `+07:00` không cho biết người tham gia đang ở vùng nào. `ZoneId.of("Europe/Paris")` cho phép tìm offset đúng tại **ngày cụ thể**, có thể là `+01:00` hoặc `+02:00` tùy quy tắc mùa hè. Một offset cố định không mang theo lịch sử hoặc những quy định sẽ thay đổi của một địa phương.

**Phân biệt Instant với LocalDateTime:** `Instant.parse("2024-06-10T13:00:00Z")` có ý nghĩa duy nhất trên timeline. `LocalDateTime.of(2024,6,10,13,0)` không xác định cùng thời điểm cho mọi vùng; cần biết ít nhất offset hợp lệ hoặc ZoneId cùng chính sách giải quyết.

### 2.1. Vì sao không chỉ lưu một số giờ cộng/trừ?

Đặt giờ theo tên thành phố rồi làm:

```text
giờ người khác = giờ người tổ chức + chênh lệch ước lượng
```

là cách dễ sai. Chênh lệch giữa hai vùng có thể đổi theo thời điểm trong năm; hai vùng có thể đổi DST ở những ngày khác nhau. Quy tắc địa phương cũng có thể được sửa bởi luật mới.

Thay vì hardcode “New York chậm 12 giờ so với TP.HCM”, hãy tính:

```text
LocalDateTime của người tổ chức
       + ZoneId + chính sách DST
                    |
                    v
                  Instant
            /         |          \
           v          v           v
       ZoneId A   ZoneId B    ZoneId C
           |          |           |
           v          v           v
      Giờ hiển thị của từng người tham gia
```

Khi đã có `Instant`, chuyển sang các vùng khác nhau bằng `instant.atZone(viewerZone)`. **Không chuyển từ chuỗi local time của người này sang chuỗi local time của người khác bằng phép tính thủ công.**

## 3. Quy trình chuẩn cho một cuộc hẹn một lần

Giả sử người tổ chức chọn “20:00 ngày 10/06/2024 tại TP.HCM, họp 90 phút”:

1. **Nhận input có cấu trúc:** `2024-06-10T20:00` và `Asia/Ho_Chi_Minh`, thời lượng 90 phút.
2. **Xác thực ZoneId:** vùng tồn tại và được ứng dụng hỗ trợ.
3. **Xác thực local time theo ZoneRules:** kiểm tra có đúng một offset hợp lệ không; nếu gap/overlap, áp dụng chính sách đã công bố.
4. **Resolve thành `ZonedDateTime`** và lấy `startInstant = zoned.toInstant()`.
5. **Tính kết thúc:** nếu độ dài được định nghĩa là 90 phút thời gian thực, dùng `endInstant = startInstant.plus(Duration.ofMinutes(90))`.
6. **Kiểm tra xung đột lịch trên timeline** bằng hai Instant bắt đầu/kết thúc.
7. **Lưu bản ghi:** Instant và duration/endInstant; giữ các trường gốc cần thiết như ZoneId, local time mong muốn và offset được chọn để audit.
8. **Hiển thị:** chuyển `startInstant` sang ZoneId của từng người dùng khi đọc.
9. **Thông báo:** dùng Instant cho thời điểm gửi nhắc nhở, không để server tự lấy timezone mặc định.

Đây là luồng thuận tiện cho sự kiện **đã chốt một lần**, vì mọi thành viên cùng tham chiếu một timestamp.

### 3.1. Instant làm “single source of truth” cho cuộc hẹn đã chốt

Nếu chỉ lưu `"2024-06-10T20:00"` thì chưa biết thời điểm tuyệt đối. Nếu chỉ lưu `"+07:00"` nhưng bỏ ngày giờ thì cũng chưa đủ. Nếu lưu `Instant`, ta biết chính xác khi nào buổi họp diễn ra trên timeline.

Tuy nhiên, nếu cần giải thích “người tổ chức đã đặt lúc 20:00 ở vùng nào”, **không nên bỏ hết thông tin nhập ban đầu**. `Instant` giữ timestamp nhưng không giữ timezone mà người tổ chức chọn; phần dữ liệu đó có thể quan trọng cho sửa lịch, giao diện và audit.

## 4. Ví dụ 1 — cùng một cuộc hẹn ở TP.HCM, New York, London

Tạo file **MeetingAcrossZonesDemo.java**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;

public class MeetingAcrossZonesDemo {
    public static void main(String[] args) {
        Instant start =
            Instant.parse("2024-06-10T13:00:00Z");

        Duration length = Duration.ofMinutes(90);

        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneId london = ZoneId.of("Europe/London");

        System.out.println("startUTC=" + start);

        System.out.println("hcm=" +
            start.atZone(hcm));

        System.out.println("newYork=" +
            start.atZone(newYork));

        System.out.println("london=" +
            start.atZone(london));

        System.out.println("endUTC=" +
            start.plus(length));

        System.out.println("sameStart=" +
            start.atZone(hcm).toInstant().equals(
                start.atZone(newYork).toInstant()
            ));
    }
}
```

Biên dịch, chạy:

```bash
javac MeetingAcrossZonesDemo.java
java MeetingAcrossZonesDemo
```

Đầu ra với quy tắc múi giờ năm 2024 đã kiểm thử:

```text
startUTC=2024-06-10T13:00:00Z
hcm=2024-06-10T20:00+07:00[Asia/Ho_Chi_Minh]
newYork=2024-06-10T09:00-04:00[America/New_York]
london=2024-06-10T14:00+01:00[Europe/London]
endUTC=2024-06-10T14:30:00Z
sameStart=true
```

**Diễn giải:**

- Tại TP.HCM, cuộc họp bắt đầu 20:00 với offset +07:00.
- Tại New York ở ngày lịch sử này, quy tắc DST dùng offset -04:00, nên giờ hiển thị 09:00.
- Tại London ở ngày lịch sử này, offset +01:00, nên hiển thị 14:00.
- Ba giờ hiển thị khác nhau nhưng `toInstant()` đều bằng `2024-06-10T13:00Z`.
- End Instant `14:30Z` đến từ **90 phút thời gian thực**, không phải 90 phút trên đồng hồ tại một địa phương tùy ý.

**Lưu ý:** Các chuỗi có `[Asia/Ho_Chi_Minh]`, `[America/New_York]` và `[Europe/London]` là biểu diễn của `ZonedDateTime`. Nếu chuyển thành `OffsetDateTime` thì phần ZoneId trong ngoặc vuông **không còn được lưu**. Khi cần giữ ZoneId, ưu tiên `ZonedDateTime` hoặc lưu zone ID riêng trong dữ liệu.

## 5. Nhận input đúng: không đoán timezone từ server

Với một form tạo lịch hẹn, API nên định nghĩa rõ dữ liệu được yêu cầu. Một contract khả thi cho lịch một lần:

```json
{
  "startLocal": "2024-06-10T20:00:00",
  "zoneId": "Asia/Ho_Chi_Minh",
  "durationMinutes": 90,
  "disambiguation": "REJECT_AMBIGUOUS"
}
```

Đây là **ví dụ thiết kế schema ứng dụng**, không phải cấu trúc do `java.time` tự định nghĩa.

- `startLocal` là ngày giờ mà người tổ chức nhìn thấy trên đồng hồ.
- `zoneId` là **vùng thời gian IANA**, không phải tên viết tắt mơ hồ.
- `durationMinutes` xác định độ dài theo thời gian thực.
- `disambiguation` quy định điều gì xảy ra khi local time không tồn tại hoặc có nhiều offset.

Không nên dùng:

```java
// Mã minh họa anti-pattern, không áp dụng khi chưa xác định zone.
LocalDateTime start = LocalDateTime.parse(input);
Instant timestamp = start.atZone(ZoneId.systemDefault())
                         .toInstant();
```

vì `ZoneId.systemDefault()` là múi giờ của **máy chủ/chạy chương trình**, không nhất thiết là vùng người dùng chọn. Kết quả có thể khác trên laptop lập trình viên, CI hoặc production.

### 5.1. ZoneId khác offset và abbreviation

Các chuỗi nên dùng: `Asia/Ho_Chi_Minh`, `America/New_York`, `Europe/Paris`, `Europe/London`. Chúng cho phép Java tìm quy tắc được cài đặt cho **ngày hẹn cụ thể**.

Các abbreviation như `CST`, `EST` hay `IST` có thể mơ hồ giữa các vùng. Không giả định abbreviation có một nghĩa toàn cầu. Nếu UI cho người dùng chọn thành phố/vùng, hãy lưu **ID IANA đã xác nhận**, và hiển thị tên thân thiện riêng cho UI.

Nếu input chỉ cung cấp `+07:00`, bạn có thể tạo một `OffsetDateTime` cho thời điểm cụ thể, nhưng **không thể khôi phục chắc chắn vùng địa lý** hoặc áp dụng chính sách DST của vùng trong những lần lặp tiếp theo.

### 5.2. Validate ZoneId

`ZoneId.of(userInput)` có thể ném `DateTimeException` khi ID sai hoặc không có dữ liệu quy tắc trong runtime. Tránh chấp nhận các ID tự đặt nếu hệ thống cần dữ liệu vùng đầy đủ.

Đối với API public, có thể dùng danh sách vùng được phép do ứng dụng quản lý, kết hợp `ZoneId.of(...)` để xác thực. Đừng mặc định máy chạy luôn có dữ liệu timezone mới nhất. Quy tắc vùng có thể được cập nhật trong JDK hoặc môi trường runtime.

## 6. DST gap/overlap: điểm khó nhất khi chọn giờ địa phương

Một `LocalDateTime` như `2024-03-31T02:30` hợp lệ về **trường số**, nhưng chưa chắc tồn tại trong một vùng. Java cung cấp `ZoneRules` để biết những offset thực sự có thể áp dụng.

Gọi:

```java
// Đoạn minh họa.
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local =
    LocalDateTime.of(2024, 3, 31, 2, 30);

List<ZoneOffset> valid =
    zone.getRules().getValidOffsets(local);
```

Kết quả của `getValidOffsets(local)`:

| Số offset hợp lệ | Trạng thái | Quyết định nghiệp vụ |
| --- | --- | --- |
| `0` | **Gap**: giờ bị nhảy qua và không tồn tại | Từ chối, hoặc dời giờ theo chính sách đã công bố |
| `1` | Giờ bình thường, mốc UTC xác định | Chọn offset duy nhất |
| `2` trong tình huống DST phổ biến | **Overlap**: đồng hồ lùi, giờ địa phương xuất hiện hai lần | Yêu cầu người dùng chọn lần sớm/muộn, hoặc dùng một chính sách mặc định được công bố |

Về mặt tổng quát, API trả một danh sách offset, không phải enum chỉ có ba giá trị. Javadoc lưu ý lý thuyết có thể có tình huống hiếm với hơn hai offset nếu nhiều chuyển đổi gần nhau; logic vững chắc nên xử lý **`size()>1`** là mơ hồ thay vì giả định chỉ đúng hai offset trong mọi thế giới.

### 6.1. Ví dụ lịch sử: gap tại Paris

Ngày 31/03/2024, vùng `Europe/Paris` chuyển sang giờ mùa hè; `2024-03-31T02:30` không tồn tại. `local.atZone(zone)` thường **tự điều chỉnh sang 03:30** theo chính sách của `ZonedDateTime`, không ném exception.

Đối với lịch hẹn, tự đổi 02:30 thành 03:30 mà không hỏi có thể khiến người tổ chức không đồng ý với giờ được lưu. Một hệ thống đặt lịch có thể chọn **REJECT_GAP** và yêu cầu chọn giờ khác.

### 6.2. Ví dụ lịch sử: overlap tại Paris

Ngày 27/10/2024, đồng hồ lùi. `2024-10-27T02:30` tương ứng:

```text
2024-10-27T02:30+02:00[Europe/Paris]
    -> 2024-10-27T00:30Z

2024-10-27T02:30+01:00[Europe/Paris]
    -> 2024-10-27T01:30Z
```

Hai Instant **cách nhau 60 phút**, dù cùng hiển thị `02:30` ở Paris. Nếu thiếu chính sách chọn offset, bạn chưa xác định được một cuộc hẹn đơn lẻ.

Mặc định của nhiều factory `ZonedDateTime` trong overlap là chọn **offset sớm hơn** khi không có offset ưu tiên. Nhưng chính sách này chỉ hợp lý khi nghiệp vụ **cho phép chọn tự động**. Đối với đặt lịch cần cam kết, một lựa chọn rõ ràng là yêu cầu người dùng xác nhận lần thứ nhất hoặc thứ hai.

### 6.3. Strict resolution

`ZonedDateTime.ofStrict(local, offset, zone)` chỉ chấp nhận nếu offset thực sự hợp lệ cho local time/zone. Trong gap không có offset hợp lệ; trong overlap có thể truyền một trong những offset hợp lệ sau khi người dùng chọn.

Đừng dùng chỉ `zone.getRules().getOffset(local)` làm cơ chế xác thực nghiêm ngặt: trong gap/overlap, method này có thể trả một “best offset”, không nhất thiết là một xác nhận giá trị duy nhất và hợp lệ. `getValidOffsets` mới là API trực tiếp để phát hiện gap/overlap.

## 7. Ví dụ 2 — từ chối gap và overlap chưa được chọn

Tạo file **StrictResolveDemo.java**:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StrictResolveDemo {
    static ZonedDateTime resolve(
        LocalDateTime local,
        ZoneId zone,
        ZoneOffset preferred
    ) {
        List<ZoneOffset> allowed =
            zone.getRules().getValidOffsets(local);

        if (allowed.isEmpty()) {
            throw new IllegalArgumentException("GAP");
        }

        if (allowed.size() > 1 && preferred == null) {
            throw new IllegalArgumentException("OVERLAP");
        }

        ZoneOffset offset = preferred == null
            ? allowed.get(0)
            : preferred;

        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        LocalDateTime gap =
            LocalDateTime.of(2024, 3, 31, 2, 30);

        LocalDateTime overlap =
            LocalDateTime.of(2024, 10, 27, 2, 30);

        try {
            resolve(gap, paris, null);
        } catch (IllegalArgumentException ex) {
            System.out.println("gap=" + ex.getMessage());
        }

        try {
            resolve(overlap, paris, null);
        } catch (IllegalArgumentException ex) {
            System.out.println("overlap=" + ex.getMessage());
        }

        System.out.println("early=" +
            resolve(overlap, paris, ZoneOffset.ofHours(2)));

        System.out.println("late=" +
            resolve(overlap, paris, ZoneOffset.ofHours(1)));

        System.out.println("normal=" +
            resolve(
                LocalDateTime.of(2024, 4, 1, 9, 0),
                paris,
                null
            ));
    }
}
```

```bash
javac StrictResolveDemo.java
java StrictResolveDemo
```

Stdout đã kiểm thử:

```text
gap=GAP
overlap=OVERLAP
early=2024-10-27T02:30+02:00[Europe/Paris]
late=2024-10-27T02:30+01:00[Europe/Paris]
normal=2024-04-01T09:00+02:00[Europe/Paris]
```

**Phân tích:**

1. Gap bị từ chối vì `allowed.isEmpty()`.
2. Overlap không có offset được chọn bị từ chối vì `allowed.size()>1`.
3. Sau khi truyền offset `+02:00` hoặc `+01:00`, `ofStrict` bảo đảm offset thuộc các giá trị zone chấp nhận ở local time đó.
4. Thời điểm bình thường có đúng một offset nên có thể tạo lịch ngay.
5. Nếu truyền offset không hợp lệ ngay cả khi local time bình thường, `ofStrict` sẽ ném `DateTimeException`; đừng bỏ qua lỗi này.

Đây là **một chính sách minh họa**: REJECT gap, REQUIRE_SELECTION overlap. Một hệ thống khác có thể quyết định dời gap theo quy tắc và thông báo rõ, nhưng phải xác định và kiểm thử hành vi đó. Phần code ném `IllegalArgumentException("GAP")`/`"OVERLAP"` cho mục đích giáo dục; ứng dụng thực tế nên dùng kiểu lỗi/enum như `NONEXISTENT_LOCAL_TIME` và `AMBIGUOUS_LOCAL_TIME` thay vì dựa vào message string.

## 8. Bẫy khi chuỗi có cả offset lẫn ZoneId

Giả sử client gửi:

```text
2024-06-10T09:00-04:00[America/New_York]
```

Trong ngày lịch sử này, -04:00 là offset phù hợp ở New York. Chuỗi có thể được parse bằng `ZonedDateTime.parse(...)`.

Nhưng nếu client gửi **offset mâu thuẫn**:

```text
2024-06-10T09:00+02:00[America/New_York]
```

`ZonedDateTime.parse(...)` theo ISO có thể **dùng offset để xác định Instant rồi biểu diễn lại theo zone**, khiến **giờ địa phương bị đổi** thành giá trị khác. Parse chạy thành công không đồng nghĩa cặp `09:00, +02:00, America/New_York` được xác nhận là chính xác theo ý nghĩa dữ liệu ban đầu.

Ví dụ đã kiểm thử với JDK:

```java
// Đoạn minh họa, đã import java.time.*.
ZonedDateTime parsed = ZonedDateTime.parse(
    "2024-06-10T09:00+02:00[America/New_York]"
);
// 2024-06-10T03:00-04:00[America/New_York]
```

Nếu hợp đồng API yêu cầu **local time và offset người gửi nhập phải hợp lệ đúng theo zone**, hãy parse các thành phần và kiểm tra bằng:

```java
// Đoạn minh họa.
ZonedDateTime strict = ZonedDateTime.ofStrict(
    LocalDateTime.of(2024, 6, 10, 9, 0),
    ZoneOffset.ofHours(2),
    ZoneId.of("America/New_York")
);
// Ném DateTimeException: +02:00 không hợp lệ cho local time này ở New York.
```

**Bài học:** Bắt buộc xác định schema: chỉ nhận một timestamp có offset và tin offset là nguồn sự thật? Hay yêu cầu timestamp local và ZoneId phải nhất quán? Hai cách có contract khác nhau. Không để behavior của parser quyết định một lựa chọn nghiệp vụ chưa được phát biểu.

## 9. Lịch một lần khác lịch lặp định kỳ

Đây là điểm thiết kế khiến nhiều hệ thống lịch hoạt động đúng trong vài tuần nhưng sai khi sang mùa khác.

### 9.1. Lịch một lần

Với cuộc họp “20:00 ngày 10/06/2024 ở TP.HCM”, sau khi resolve, có thể lưu một `Instant` duy nhất. Nếu chỉ đổi vùng hiển thị, timestamp không đổi.

### 9.2. Lịch hằng tuần theo giờ địa phương

Với yêu cầu “09:00 sáng Chủ Nhật hằng tuần theo giờ Paris”, ý nghĩa chính là **giữ 09:00 trên đồng hồ Paris**.

Nếu chỉ lưu Instant của tuần đầu rồi luôn:

```java
// Sai cho recurrence phải giữ giờ địa phương khi qua DST.
Instant next = firstInstant.plus(Duration.ofDays(7));
```

thì khoảng cách là **168 giờ UTC**, nhưng giờ địa phương có thể trượt sang **10:00** hoặc **08:00** sau chuyển DST.

Cách đúng cho recurring wall-clock meeting:

1. Lưu `LocalTime.of(9,0)` và quy tắc ngày trong tuần.
2. Lưu `ZoneId.of("Europe/Paris")`.
3. Sinh **từng ngày xảy ra** theo lịch địa phương, ví dụ `LocalDate.plusWeeks(1)`.
4. Ghép từng ngày với giờ thành `LocalDateTime`.
5. Resolve theo ZoneRules tại **ngày cụ thể**, áp dụng chính sách gap/overlap.
6. Đưa ra `Instant` cho occurrence đã xác định, phục vụ thông báo và hiển thị.

### 9.3. Duration và Period: hai ý nghĩa khác nhau

| Khái niệm | Dùng khi | Tác dụng |
| --- | --- | --- |
| `Duration.ofMinutes(90)` | Họp dài 90 phút theo thời gian thực | `Instant.plus(duration)` cho end Instant |
| `Duration.ofDays(7)` | Cần đúng 168 giờ thời gian thực | Không bảo đảm lặp đúng cùng giờ địa phương |
| `LocalDate.plusWeeks(1)` | Cần tuần kế tiếp trên lịch | Giữ quy tắc ngày trong tuần |
| `ZonedDateTime.plusWeeks(1)` | Muốn cộng theo ngày lịch của vùng | Điều chỉnh offset theo timezone rules khi cần |
| `Period.ofWeeks(1)` | Diễn đạt một tuần theo lịch ngày | Không phải một khoảng elapsed-time cố định khi quy chiếu qua DST |

Khi DST đổi, một ngày theo lịch địa phương có thể tương ứng **23 hoặc 25 giờ** elapsed-time trong vùng. Vì vậy “một ngày lịch” và “24 giờ thời gian thực” không phải lúc nào cũng đồng nghĩa.

## 10. Ví dụ 3 — lịch lặp 09:00 Paris qua tuần đổi DST

Tạo file **RecurringWeeklyDemo.java**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class RecurringWeeklyDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Paris");
        LocalDate first = LocalDate.of(2024, 3, 24);
        LocalTime wall = LocalTime.of(9, 0);

        for (int i = 0; i < 3; i++) {
            LocalDate date = first.plusWeeks(i);

            ZonedDateTime slot =
                LocalDateTime.of(date, wall).atZone(zone);

            System.out.println(
                "weekly" + i + "=" + slot +
                " | utc=" + slot.toInstant()
            );
        }

        Instant fixedNext =
            LocalDateTime.of(first, wall)
                .atZone(zone)
                .toInstant()
                .plus(Duration.ofDays(7));

        System.out.println("fixedNext=" +
            fixedNext.atZone(zone));
    }
}
```

```bash
javac RecurringWeeklyDemo.java
java RecurringWeeklyDemo
```

Stdout:

```text
weekly0=2024-03-24T09:00+01:00[Europe/Paris] | utc=2024-03-24T08:00:00Z
weekly1=2024-03-31T09:00+02:00[Europe/Paris] | utc=2024-03-31T07:00:00Z
weekly2=2024-04-07T09:00+02:00[Europe/Paris] | utc=2024-04-07T07:00:00Z
fixedNext=2024-03-31T10:00+02:00[Europe/Paris]
```

**So sánh rất quan trọng:**

- Ba occurrence tạo từ **ngày lịch + 09:00 + ZoneId** đều hiển thị **09:00 Paris**.
- Offset chuyển từ `+01:00` thành `+02:00` tại tuần đổi DST; Instant của occurrence thứ hai là 07:00Z chứ không phải 08:00Z.
- Cộng đúng 168 giờ vào Instant đầu tiên cho `fixedNext` lúc **10:00 Paris**, lệch một giờ so với yêu cầu 09:00 địa phương.

**Lưu ý:** Ví dụ dùng `atZone` vì local time `09:00` không rơi vào gap/overlap của các ngày lịch sử nêu trên. Đối với ứng dụng tổng quát, nên dùng resolver có chính sách gap/overlap rõ ràng như phần 7 khi sinh từng occurrence.

## 11. Lịch lặp cũng có thể rơi vào overlap

Nếu người dùng đặt “02:30 mỗi Chủ Nhật tại Paris”, khoảng cuối tháng 10 có tuần mà 02:30 xảy ra **hai lần**. Quy tắc recurrence phải quy định liệu cuộc hẹn là:

- **Một** occurrence chọn offset sớm hơn.
- **Một** occurrence chọn offset muộn hơn.
- **Hai** occurrence trong ngày overlap (nếu nghiệp vụ thật sự muốn).
- Hoặc **từ chối/tạm dừng** ngày mơ hồ và yêu cầu xác nhận.

Không tự tạo hai cuộc hẹn vì API báo hai offset nếu người dùng chỉ muốn một cuộc họp mỗi tuần; cũng không mặc nhiên bỏ qua tuần đó nếu họ không đồng ý.

### Ví dụ 4 — FallOverlapDemo.java

Tạo file **FallOverlapDemo.java**:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class FallOverlapDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Paris");
        LocalTime wall = LocalTime.of(2, 30);
        LocalDate first = LocalDate.of(2024, 10, 20);

        for (int i = 0; i < 3; i++) {
            LocalDateTime local =
                LocalDateTime.of(first.plusWeeks(i), wall);

            List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

            System.out.println(
                "day" + i + "=" + local +
                " | offsets=" + offsets
            );

            if (offsets.size() > 1) {
                System.out.println("candidate0=" +
                    ZonedDateTime.ofStrict(
                        local, offsets.get(0), zone
                    ).toInstant());

                System.out.println("candidate1=" +
                    ZonedDateTime.ofStrict(
                        local, offsets.get(1), zone
                    ).toInstant());
            }
        }
    }
}
```

```bash
javac FallOverlapDemo.java
java FallOverlapDemo
```

Stdout:

```text
day0=2024-10-20T02:30 | offsets=[+02:00]
day1=2024-10-27T02:30 | offsets=[+02:00, +01:00]
candidate0=2024-10-27T00:30:00Z
candidate1=2024-10-27T01:30:00Z
day2=2024-11-03T02:30 | offsets=[+01:00]
```

Chỉ tuần 27/10/2024 có hai offset. Hai candidate này khác nhau một giờ trên timeline. Một lịch recurring tốt phải lưu chính sách để xác định **candidate nào trở thành occurrence** và áp dụng nhất quán mỗi lần tính lại lịch.

**Không lưu đơn giản “UTC time của tuần đầu + 7 ngày”** cho các occurrence tương lai khi business muốn giữ 02:30 Paris. Những quy tắc DST không thể khôi phục đầy đủ từ offset của một tuần đầu.

## 12. Mô hình dữ liệu để lưu lịch hẹn

### 12.1. Một cuộc hẹn một lần đã chốt

Một thiết kế khả thi:

| Trường | Kiểu/nghĩa | Tại sao cần |
| --- | --- | --- |
| `meeting_id` | ID duy nhất | Nhận dạng và cập nhật |
| `start_instant` | `Instant` hoặc timestamp UTC chuẩn | Mốc bắt đầu thực |
| `end_instant` hoặc `duration` | Instant kết thúc hoặc `Duration` | Tính khoảng bận và nhắc nhở |
| `organizer_zone_id` | Chuỗi ZoneId IANA | Khôi phục vùng người tổ chức chọn |
| `requested_local` | LocalDateTime ban đầu | Audit mong muốn của người tổ chức |
| `resolved_offset` | Offset được chấp nhận tại occurrence | Ghi nhận cách xử lý overlap |
| `dst_resolution_policy` | Mã chính sách | Giải thích và kiểm thử |
| `status` | scheduled/cancelled/rescheduled... | Không coi lịch đã hủy là cuộc hẹn đang hoạt động |
| `version` | Số phiên bản/ETag | Hỗ trợ cập nhật đồng thời an toàn |

Đây là ví dụ **schema đề xuất**, không phải bảng mặc định của Java hoặc của một database cụ thể.

Nếu lưu cả `start_instant` và `end_instant`, có thể xác minh `end > start` và xác nhận độ dài mong đợi. Nếu lưu duration, phải kiểm tra duration dương và tính end nhất quán. Với một lịch họp có **pause** hay nhiều phân đoạn, mô hình đơn giản một khoảng thời gian có thể chưa đủ.

### 12.2. Một quy tắc lịch lặp

Một recurrence cần chứa **ý định trên lịch**, chẳng hạn:

- `ZoneId` của lịch.
- Ngày bắt đầu local.
- Giờ local (ví dụ 09:00).
- Quy tắc lặp (hằng tuần vào Chủ Nhật, hằng tháng ngày 15...).
- Ngày/giờ kết thúc chuỗi, số lần lặp hoặc giới hạn sinh.
- Chính sách gap: REJECT, SKIP, SHIFT_FORWARD hoặc quy tắc nghiệp vụ khác.
- Chính sách overlap: EARLIER, LATER, ASK, BOTH nếu thật sự cần.
- Danh sách ngoại lệ: ngày nghỉ, hủy riêng occurrence, chỉnh giờ một lần.
- ID chuỗi, ID occurrence và phiên bản để theo dõi cập nhật.

**Không coi chỉ một `Instant` + `Duration.ofDays(7)` là toàn bộ recurrence** nếu mục đích là “cùng giờ địa phương mỗi tuần”. Tập occurrences đã sinh cho một khoảng thời gian có thể được cache, nhưng phải có cách cập nhật khi quy tắc múi giờ hoặc lịch thay đổi.

### 12.3. Câu chuyện cập nhật timezone rules

Dữ liệu quy tắc IANA tzdb được cập nhật vì một số chính phủ thay đổi thời gian/offset. Ví dụ IANA đã công bố **tzdb 2026f ngày 27/10/2026**, gồm điều chỉnh quy tắc Cuba liên quan giai đoạn sắp tới. Đây là minh họa thực tế rằng **offset tương lai không nên hardcode lâu dài**.

JDK và các môi trường triển khai có thể chứa phiên bản tzdb khác nhau. Khi luật thay đổi, một recurrence được định nghĩa “09:00 theo giờ địa phương” có thể tương ứng **Instant mới** sau khi rules được cập nhật. Hệ thống cần quyết định:

1. Giữ **giờ địa phương theo luật mới** và tính lại Instant.
2. Hay giữ **Instant đã thông báo** đối với occurrence đã chốt.
3. Thông báo ai khi một occurrence bị thay đổi.
4. Cách kiểm tra đồng bộ giữa các server/timezone database và version audit.

Không thể trả lời mọi trường hợp chỉ bằng một conversion function; đây là **chính sách sản phẩm** phải được ghi rõ.

## 13. Ví dụ 5 — lưu Instant và dữ liệu gốc để audit

Tạo file **MeetingRecordDemo.java**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

record MeetingRecord(
    Instant start,
    String zoneId,
    LocalDateTime requestedLocal,
    ZoneOffset chosenOffset,
    Duration duration
) {}

public class MeetingRecordDemo {
    public static void main(String[] args) {
        ZoneId organizer =
            ZoneId.of("Asia/Ho_Chi_Minh");

        LocalDateTime requested =
            LocalDateTime.of(2024, 6, 10, 20, 0);

        ZonedDateTime resolved =
            ZonedDateTime.ofStrict(
                requested,
                ZoneOffset.ofHours(7),
                organizer
            );

        MeetingRecord record = new MeetingRecord(
            resolved.toInstant(),
            organizer.getId(),
            requested,
            resolved.getOffset(),
            Duration.ofMinutes(90)
        );

        System.out.println("storedUTC=" +
            record.start());

        System.out.println("storedZone=" +
            record.zoneId());

        System.out.println("storedLocal=" +
            record.requestedLocal());

        System.out.println("storedOffset=" +
            record.chosenOffset());

        System.out.println("restored=" +
            record.start().atZone(
                ZoneId.of(record.zoneId())
            ));

        System.out.println("london=" +
            record.start().atZone(
                ZoneId.of("Europe/London")
            ));

        System.out.println("minutes=" +
            record.duration().toMinutes());
    }
}
```

```bash
javac MeetingRecordDemo.java
java MeetingRecordDemo
```

Stdout:

```text
storedUTC=2024-06-10T13:00:00Z
storedZone=Asia/Ho_Chi_Minh
storedLocal=2024-06-10T20:00
storedOffset=+07:00
restored=2024-06-10T20:00+07:00[Asia/Ho_Chi_Minh]
london=2024-06-10T14:00+01:00[Europe/London]
minutes=90
```

Ở đây:

- `start` là mốc tuyệt đối cần cho đồng bộ và xung đột lịch.
- `requestedLocal` + `zoneId` + `chosenOffset` giữ lại thông tin quyết định đầu vào.
- `duration` mô tả đúng 90 phút đã chọn.
- `restored` được tạo từ Instant và ZoneId đã lưu. Trong tình huống timezone rules sau này thay đổi, **giờ hiển thị lại có thể phản ánh rules mới**, vì vậy các trường dữ liệu gốc giúp audit lý do đã đặt lịch vào thời điểm đó.

Đoạn dùng `record` cần Java 16+; với dự án bắt buộc Java 8, dùng một class dữ liệu bất biến với constructor/getter tương ứng. Các API `java.time` xuất hiện trong phép chuyển đổi vẫn áp dụng trong Java 8.

## 14. Xung đột lịch phải được xét theo Instant, không theo local string

Khi kiểm tra hai cuộc hẹn có trùng nhau hay không, hãy chuyển các khoảng thời gian về cùng một timeline. Không so sánh chuỗi như `"09:00"` ở New York với `"20:00"` ở TP.HCM: hai giờ địa phương không nằm trên cùng hệ quy chiếu.

Đối với các khoảng bận được hiểu là **[start, end)** (bao gồm thời điểm bắt đầu, loại trừ thời điểm kết thúc), hai khoảng không rỗng có giao nhau khi:

```text
aStart < bEnd  AND  bStart < aEnd
```

Đây là hợp đồng thực dụng cho lịch hẹn: một cuộc họp kết thúc lúc đúng `14:00Z` có thể đứng ngay trước cuộc họp khác bắt đầu lúc `14:00Z` mà **không bị coi là xung đột**.

Cần xác thực:

- `startInstant != null` và `endInstant != null`.
- `endInstant.isAfter(startInstant)`.
- Duration dương và trong giới hạn cho phép.
- Nếu hệ thống có buffer trước/sau buổi họp, nới khoảng bận theo chính sách đã định **trước** khi áp dụng phép kiểm tra.

### Ví dụ 6 — OverlapDetectorDemo.java

Tạo file **OverlapDetectorDemo.java**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;

public class OverlapDetectorDemo {
    static boolean overlaps(
        Instant aStart,
        Instant aEnd,
        Instant bStart,
        Instant bEnd
    ) {
        return aStart.isBefore(bEnd)
            && bStart.isBefore(aEnd);
    }

    public static void main(String[] args) {
        Instant a =
            Instant.parse("2024-06-10T13:00:00Z");

        Instant aEnd =
            a.plus(Duration.ofHours(1));

        Instant b =
            Instant.parse("2024-06-10T13:30:00Z");

        Instant c =
            Instant.parse("2024-06-10T14:00:00Z");

        System.out.println("ab=" +
            overlaps(
                a,
                aEnd,
                b,
                b.plus(Duration.ofHours(1))
            ));

        System.out.println("ac=" +
            overlaps(
                a,
                aEnd,
                c,
                c.plus(Duration.ofHours(1))
            ));

        System.out.println("viewerB=" +
            b.atZone(ZoneId.of("America/New_York")));
    }
}
```

```bash
javac OverlapDetectorDemo.java
java OverlapDetectorDemo
```

Stdout:

```text
ab=true
ac=false
viewerB=2024-06-10T09:30-04:00[America/New_York]
```

A diễn ra từ 13:00Z đến 14:00Z, B bắt đầu 13:30Z nên **trùng**, C bắt đầu đúng 14:00Z nên **không trùng** theo cách hiểu [start,end). Giờ New York của B chỉ là cách hiển thị; điều kiện xung đột không thay đổi.

**Lưu ý transaction:** Một phép kiểm tra trùng trước khi ghi **chưa tự bảo đảm** không double-booking khi hai request chạy đồng thời. Với nhiều worker/server, hệ thống còn cần transaction, locking, exclusion constraints hoặc cơ chế đặt chỗ nhất quán theo database. Logic thời gian đúng và cơ chế đồng thời an toàn là **hai bài toán độc lập**.

## 15. Hiển thị lịch cho người tham gia và cập nhật timezone

Mỗi người dùng nên có một vùng hiển thị `ZoneId` được xác định theo cài đặt tài khoản hoặc lựa chọn rõ ràng. Khi hiển thị:

```java
// Đoạn minh họa.
ZonedDateTime visible =
    meetingStartInstant.atZone(viewerZone);
```

`meetingStartInstant` là `Instant` đã lưu; `viewerZone` là `ZoneId` của người xem. Không cần chuyển lần lượt qua timezone của người tổ chức và của người dùng, vì từ `Instant` có thể chuyển trực tiếp sang bất kỳ vùng được hỗ trợ nào.

### 15.1. Người dùng đi du lịch thì sao?

Nếu một người dùng chuyển vùng từ `Asia/Ho_Chi_Minh` sang `Europe/London`, buổi họp **đã chốt theo Instant** vẫn diễn ra đúng cùng thời điểm tuyệt đối. Chỉ thay đổi giờ hiển thị nếu người dùng chọn xem theo vùng mới.

Nhưng lịch lặp “của tôi mỗi sáng 09:00 ở nơi tôi đang ở” lại có nghĩa khác với “09:00 hằng tuần theo giờ TP.HCM”. Hệ thống phải biết timezone **gắn với người/thiết bị lúc xem** hay **gắn với quy tắc lịch hẹn**. Đây là lựa chọn sản phẩm, không tự suy ra từ `ZoneId.systemDefault()`.

### 15.2. Email mời họp và thông báo

Trong lời mời:

- Có thể gửi mốc bắt đầu dạng **ISO-8601 với offset** hoặc UTC Instant để tránh mơ hồ.
- Nếu giao thức lịch như iCalendar được dùng, phải tuân thủ yêu cầu biểu diễn DATE-TIME/VTIMEZONE hoặc UTC theo chuẩn và thư viện được chọn.
- Nên hiển thị **vùng thời gian** trong nội dung con người đọc khi cần, không chỉ ghi `09:00`.
- Nếu lịch bị reschedule, thông báo phải tham chiếu occurrence/meeting ID và version chính xác để tránh cập nhật nhầm một bản cũ.
- Nhắc nhở “trước buổi họp 15 phút” thông thường nên tính từ **Instant của occurrence** bằng `minus(Duration.ofMinutes(15))`, không bằng trừ 15 phút trên một chuỗi local mà bỏ qua DST.

Không đảm bảo email client của người nhận hiển thị cùng múi giờ như server; lưu/trao đổi mốc thời gian chuẩn và để client xử lý trình bày theo timezone tương ứng.

## 16. Parse ZoneId, chuỗi offset và dữ liệu sai

Các chuỗi đầu vào có ba kiểu ý nghĩa:

```text
2024-06-10T13:00:00Z
    -> Instant, đã có mốc UTC

2024-06-10T09:00-04:00
    -> OffsetDateTime, đã có offset

2024-06-10T09:00-04:00[America/New_York]
    -> ZonedDateTime, có ZoneId

2024-06-10T09:00
    -> LocalDateTime, thiếu offset/ZoneId
```

Khi một API **bắt buộc có timestamp**, không được mặc nhiên coi local string `2024-06-10T09:00` là UTC hoặc server local zone nếu hợp đồng chưa nói như vậy.

Một số case validation:

| Input | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `Mars/Base` | ID vùng không tồn tại trong dữ liệu runtime | Từ chối `INVALID_ZONE` |
| `2024-06-10T09:00` gửi vào `OffsetDateTime.parse` | Thiếu offset | Từ chối `MISSING_OFFSET` |
| `2024-02-30T09:00+07:00` | Ngày không tồn tại | Từ chối `INVALID_DATE_TIME` |
| Paris `2024-03-31T02:30` | Gap | Từ chối hoặc dời theo policy rõ |
| Paris `2024-10-27T02:30` | Overlap | Yêu cầu offset hoặc chọn theo policy |
| `2024-06-10T09:00+02:00[America/New_York]` | Local, offset và region không nhất quán | Parse các trường rồi `ofStrict` nếu contract yêu cầu khớp chính xác |

### Ví dụ 7 — ScheduleValidationDemo.java

Tạo file **ScheduleValidationDemo.java**:

```java
import java.time.DateTimeException;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeParseException;

public class ScheduleValidationDemo {
    public static void main(String[] args) {
        try {
            ZoneId.of("Mars/Base");
        } catch (DateTimeException ex) {
            System.out.println("invalidZone=" +
                ex.getClass().getSimpleName());
        }

        try {
            OffsetDateTime.parse("2024-06-10T09:00");
        } catch (DateTimeParseException ex) {
            System.out.println("missingOffset=REJECTED");
        }

        ZonedDateTime confirmed =
            ZonedDateTime.parse(
                "2024-06-10T09:00-04:00[America/New_York]"
            );

        System.out.println("confirmed=" + confirmed);
        System.out.println("confirmedUTC=" +
            confirmed.toInstant());
    }
}
```

```bash
javac ScheduleValidationDemo.java
java ScheduleValidationDemo
```

Stdout:

```text
invalidZone=ZoneRulesException
missingOffset=REJECTED
confirmed=2024-06-10T09:00-04:00[America/New_York]
confirmedUTC=2024-06-10T13:00:00Z
```

**Chú ý:** Không catch tất cả `DateTimeException` rồi biến mọi vấn đề thành lỗi người dùng. `ZoneRulesException` đôi khi phản ánh **lỗi cấu hình dữ liệu timezone của runtime**; `DateTimeParseException` thường là input không phù hợp. Ứng dụng cần phân loại lỗi đúng tầng.

## 17. Khi thay đổi lịch, áp dụng lại chính sách nào?

Một lịch hẹn có thể thay đổi theo nhiều ý định:

| Thay đổi người dùng yêu cầu | Điều cần giữ | Cách xử lý |
| --- | --- | --- |
| Xem ở timezone khác | Instant | `instant.atZone(newViewerZone)` |
| Chuyển cuộc họp sang **10:00 theo giờ người tổ chức** | Giờ local được chọn và ZoneId | Resolve lại thành Instant theo rules |
| Dời cuộc họp muộn hơn đúng **30 phút thời gian thực** | Duration trên timeline | `instant.plus(Duration.ofMinutes(30))` |
| Lặp vào cùng **09:00 mỗi tuần** | LocalTime, ngày trong tuần, ZoneId | Sinh từng LocalDate rồi resolve |
| Đổi vùng tổ chức mà **giữ nguyên sự kiện** | Instant | Chỉ cập nhật vùng hiển thị/metadata phù hợp |
| Đổi vùng tổ chức mà **giữ 09:00 trên đồng hồ vùng mới** | LocalDateTime tại vùng mới | Có thể tạo Instant khác; phải xác nhận |
| Thay đổi DST policy của lịch lặp | Quy tắc recurrence theo phiên bản | Tính lại những occurrence bị ảnh hưởng |

**Phải đặt câu hỏi nghiệp vụ đúng:** “Đổi timezone” có nghĩa đổi **góc nhìn hiển thị** hay đổi **giờ thực sự diễn ra**? Cùng một nút UI mơ hồ có thể gây lỗi nghiêm trọng nếu hai loại thao tác bị trộn lẫn.

### 17.1. OffsetDateTime không thay cho ZoneId trong recurrence

`OffsetDateTime` có local time và offset đủ xác định một timestamp, nhưng không mang ID vùng để tra lại DST trong tương lai. Nếu muốn lịch lặp “09:00 tại Paris”, lưu `Europe/Paris` là quy tắc; không chỉ lưu offset `+01:00` của lần đầu.

### 17.2. Nếu timezone rules thay đổi sau khi đặt

Một occurrence đã gửi lời mời theo Instant có thể được coi là **đã chốt**, hoặc có thể phải được tính lại để giữ giờ địa phương theo quy định mới. Hệ thống nên xác định:

- Khi nào tự cập nhật những occurrence tương lai?
- Khi nào người tổ chức phải duyệt?
- Có giữ timestamp cũ để audit không?
- Có gửi thông báo đổi giờ cho người tham gia không?
- Quy trình đồng bộ giữa các dịch vụ dùng các bản tzdb khác nhau là gì?

Không có một lựa chọn “đúng mặc định” cho mọi sản phẩm. Điều đúng là **chính sách được xác định và thử nghiệm**, không phụ thuộc tình cờ vào phiên bản JDK trên từng server.

## 18. Thời lượng buổi họp và khoảng bận qua DST

Với cuộc hẹn **một lần** dài 90 phút theo elapsed time:

```java
// Đoạn minh họa.
Instant end = start.plus(Duration.ofMinutes(90));
```

Thao tác này giữ đúng **90 phút** trên timeline ngay cả khi local clock nhảy qua một giờ DST.

Nhưng có những nghiệp vụ khác:

- Một khóa học diễn ra “09:00–17:00 theo giờ địa phương” cần xác định cả **local start** và **local end** theo ngày/vùng, bởi độ dài elapsed-time có thể khác vào ngày chuyển DST.
- Một lịch hẹn qua nửa đêm có thể hiển thị **ngày kết thúc khác ngày bắt đầu** ở một số vùng.
- Một buổi họp qua DST overlap có thể có local clock lúc kết thúc **nhìn như nhỏ hơn** lúc bắt đầu, dù trên timeline thời gian vẫn đi tới.
- Khi người tham gia ở phía bên kia đường đổi ngày quốc tế, cùng cuộc hẹn có thể mang **ngày lịch khác** trên giao diện.

**Nguyên tắc:** Xác định duration là **thời gian thực** hay **độ chênh trên đồng hồ địa phương**. Đừng tự coi hai định nghĩa đó là tương đương qua DST.

## 19. Kiểm thử hệ thống nhiều múi giờ

Cần kiểm thử cả logic Java thuần túy và dòng dữ liệu từ API/database/UI.

### 19.1. Ma trận test trọng yếu

| Test case | Kỳ vọng |
| --- | --- |
| Instant cố định đổi sang HCM, London, New York | Tất cả `toInstant()` bằng Instant gốc |
| Cuộc họp một lần có người ở nhiều vùng | Mỗi người thấy local khác nhưng cùng sự kiện |
| LocalDateTime không có offset/zone | Không tự biến thành Instant |
| Paris gap `2024-03-31T02:30` | Không có valid offset |
| Paris overlap `2024-10-27T02:30` | Có hai offset hợp lệ trong dữ liệu lịch sử |
| Offset không được zone chấp nhận | `ZonedDateTime.ofStrict` từ chối |
| Recurrence 09:00 Paris trước/sau DST | Giữ 09:00, UTC Instant thay đổi |
| Cộng `Duration.ofDays(7)` vào occurrence trước DST | Giữ 168h thực, có thể lệch local clock |
| Hai khoảng [13:00,14:00) và [14:00,15:00) UTC | Không trùng |
| Hai khoảng [13:00,14:00) và [13:30,14:30) UTC | Trùng |
| Cuộc họp qua nửa đêm theo người xem | Hiển thị đúng **ngày địa phương** |
| Người dùng đổi timezone để xem | Instant cuộc họp không đổi |
| Lưu và đọc lại UTC Instant cùng zone metadata | Không mất timestamp và contract hiển thị |
| Tải một phiên bản TZDB khác | Phát hiện những occurrence tương lai cần xem lại |
| Server chạy ở timezone khác người tổ chức | Không thay đổi kết quả nếu code dùng ZoneId rõ ràng |
| Nhiều request đặt cùng slot | Bảo đảm không double-book bằng transaction/constraint |

### 19.2. Dùng Clock cho các test phụ thuộc hiện tại

Nếu logic cần so với “bây giờ”, nên inject `Clock` thay vì gọi `Instant.now()` không kiểm soát trong nhiều chỗ:

```java
// Đoạn minh họa.
Clock fixed = Clock.fixed(
    Instant.parse("2024-06-10T12:00:00Z"),
    ZoneId.of("UTC")
);

Instant now = Instant.now(fixed);
// 2024-06-10T12:00:00Z
```

Giữ `Instant` và zone cố định giúp test tái lập trên CI/máy khác nhau. Khi kiểm thử “hôm nay của người dùng”, dùng `LocalDate.now(clock.withZone(userZone))` hoặc logic tương đương theo zone của user, không dùng ngày mặc định của server.

### 19.3. Property quan trọng

Với một occurrence đã resolve hợp lệ:

```java
// Đoạn minh họa.
Instant original = resolved.toInstant();
Instant restored = original.atZone(resolved.getZone()).toInstant();

boolean same = original.equals(restored); // true.
```

Đây là một invariant có giá trị: **chuyển Instant sang zone rồi trở lại phải giữ đúng Instant**. Nhưng nó không thay thế test chính sách gap/overlap từ một `LocalDateTime` chưa resolve.

## 20. Những lỗi thường gặp khi thiết kế lịch nhiều múi giờ

### Lỗi 1 — lưu mỗi chuỗi “2024-06-10 20:00”

Không có ZoneId/offset thì chuỗi local chưa xác định một mốc UTC.

**Cách khắc phục:** lưu Instant đã resolve cùng thông tin nguồn cần thiết.

### Lỗi 2 — hardcode offset giữa hai thành phố

Offset theo vùng có thể thay đổi theo DST hoặc luật mới.

**Cách khắc phục:** dùng `ZoneId` và tra quy tắc tại **ngày/Instant** của cuộc hẹn.

### Lỗi 3 — dùng timezone mặc định của server

`ZoneId.systemDefault()` không tự là timezone của người tổ chức hay người xem.

**Cách khắc phục:** truyền ZoneId rõ ràng vào mọi bước xử lý.

### Lỗi 4 — coi offset và ZoneId là một

`+02:00` không chứng minh đó là Paris hay bất cứ một vùng địa lý cụ thể nào.

**Cách khắc phục:** khi cần lịch lặp/DST, giữ ZoneId IANA.

### Lỗi 5 — tự cho phép atZone điều chỉnh gap không báo người dùng

`local.atZone(zone)` có thể dời local clock vào giờ hợp lệ.

**Cách khắc phục:** kiểm tra `getValidOffsets` và chọn chính sách gap trước khi lưu.

### Lỗi 6 — không xử lý overlap

Một local clock có thể có hai Instant.

**Cách khắc phục:** yêu cầu chọn offset, hoặc dùng chính sách nhất quán và được công bố.

### Lỗi 7 — dùng getOffset(local) và tưởng nó xác nhận giờ hợp lệ

Trong gap/overlap, `ZoneRules.getOffset(local)` có thể trả best effort, không phải xác nhận không mơ hồ.

**Cách khắc phục:** dùng `getValidOffsets`, hoặc `ofStrict` khi đã có offset.

### Lỗi 8 — cộng 7 × 24h để lặp 09:00 hằng tuần

Qua DST, giờ địa phương có thể trôi.

**Cách khắc phục:** sinh từng ngày theo lịch và resolve lại giờ địa phương tại ZoneId.

### Lỗi 9 — bỏ ZoneId khi convert OffsetDateTime

`OffsetDateTime` chỉ giữ offset; không đủ để suy ra quy tắc vùng cho recurrence.

**Cách khắc phục:** lưu ZoneId riêng hoặc dùng `ZonedDateTime` khi cần.

### Lỗi 10 — so sánh giờ local của hai người dùng

`09:00` New York và `20:00` TP.HCM có thể là cùng Instant; so chuỗi sẽ báo sai.

**Cách khắc phục:** chuyển hai khoảng về `Instant` trước khi kiểm tra xung đột.

### Lỗi 11 — dùng khoảng [start,end] ở cả hai đầu mà không thống nhất

Nếu coi cuối cũng được bao gồm, hai cuộc họp chạm nhau tại biên có thể bị báo trùng ngoài ý muốn.

**Cách khắc phục:** công bố [start,end) và test trường hợp end == nextStart.

### Lỗi 12 — chỉ chạy “check conflict” trước INSERT

Hai request đồng thời có thể đều thấy slot trống và cùng ghi.

**Cách khắc phục:** kết hợp transaction, khóa hoặc constraint phù hợp với dữ liệu.

### Lỗi 13 — biến timestamp UTC thành local rồi bỏ offset quá sớm

`Instant -> LocalDateTime` làm mất thông tin cần cho round-trip.

**Cách khắc phục:** giữ `Instant` cho timestamp đã chốt, chỉ dùng local để hiển thị hoặc chỉnh sửa theo ý định.

### Lỗi 14 — tin parse thành công nghĩa offset và ZoneId nhất quán

Khi chuỗi chứa offset mâu thuẫn với vùng, parser có thể resolve lại local clock.

**Cách khắc phục:** dùng `ZonedDateTime.ofStrict(local, offset, zone)` nếu contract yêu cầu ba thành phần khớp nhau.

### Lỗi 15 — mặc định mọi cuộc hẹn “60 phút” đều là một giờ local

Qua DST, local clock có thể nhảy hoặc lùi.

**Cách khắc phục:** nêu rõ duration là elapsed-time hay wall-clock interval.

### Lỗi 16 — không lưu chính sách recurrence/DST

Tính lại occurrences sau cập nhật TZDB có thể cho kết quả khác mà không biết nguyên nhân.

**Cách khắc phục:** lưu quy tắc và chính sách, phiên bản/điều kiện giải quyết, audit và thông báo.

### Lỗi 17 — dùng mỗi một offset ở lần lặp đầu tiên

Offset không đủ cho các ngày sau khi timezone rules đổi.

**Cách khắc phục:** sinh occurrence từng ngày dựa trên ZoneId và local schedule.

### Lỗi 18 — gửi thông báo theo “giờ server” thay vì Instant

Server thay vùng hoặc chạy ở region khác có thể làm nhắc nhở sai.

**Cách khắc phục:** tính nhắc nhở trên timeline với Instant và Duration.

### Lỗi 19 — giả định mọi JVM đều dùng cùng tzdb

JDK/container có thể cập nhật khác nhau; dữ liệu tương lai có thể khác.

**Cách khắc phục:** quản lý version và cập nhật môi trường, test các vùng quan trọng.

### Lỗi 20 — không phân biệt lịch một lần với recurring rule

Một cuộc hẹn một lần và lịch hẹn theo giờ local hằng tuần có contract khác nhau.

**Cách khắc phục:** mô hình dữ liệu và API tách biệt, không dùng chung một thuật toán cộng duration cho mọi trường hợp.

## 21. Checklist thực thi

Trước khi giao tính năng scheduling:

1. Người dùng đang tạo **một cuộc hẹn** hay **quy tắc lặp**?
2. Có xác định ZoneId IANA của người tổ chức/recurrence không?
3. Đầu vào là local date-time, OffsetDateTime hay Instant? Các trường có được gắn nhãn rõ?
4. Nếu local date-time có zone, đã kiểm tra gap/overlap chưa?
5. Khi overlap, hệ thống chọn offset theo yêu cầu nào và có ghi lại quyết định không?
6. Khi gap, hệ thống từ chối, skip hay shift? Người dùng có được thông báo?
7. Buổi họp có thời lượng tính theo elapsed-time hay giờ trên đồng hồ?
8. Đã lưu start/end Instant để đồng bộ và kiểm tra xung đột?
9. Có lưu requested local, ZoneId, offset/policy khi cần sửa/audit?
10. Với recurrence, đã lưu quy tắc local + ZoneId và sinh occurrence bằng lịch, không chỉ cộng giây?
11. Khi người dùng đổi timezone hiển thị, Instant vẫn giữ nguyên?
12. Logic conflict có dùng [start,end) trên `Instant`?
13. Việc reserve slot có transaction/constraint tránh double booking đồng thời?
14. Đã xử lý timezone rule updates và quyết định chính sách tính lại occurrence?
15. Đã test Paris gap/overlap, những vùng có/không DST và giờ qua nửa đêm?
16. Input thiếu zone/offset có bị từ chối thay vì đoán múi giờ máy chủ?
17. Các trường dạng ISO-8601 có xác thực và xử lý exception đúng tầng?
18. Lời mời/nhắc nhở có lưu ID sự kiện, Instant và version để gửi đúng lịch?
19. Có bảo vệ dữ liệu người dùng và dùng error code thay vì log mọi chuỗi nhập?
20. Có kiểm tra round-trip giữa các JVM, database, API và client không?

## 22. Tự kiểm tra kiến thức

**Câu 1.** Cuộc họp bắt đầu `2024-06-10T13:00Z`. New York và TP.HCM ở ngày lịch sử này hiển thị giờ nào?

**Đáp án:** New York 09:00 với `-04:00`, TP.HCM 20:00 với `+07:00`. Cả hai cùng Instant.

**Câu 2.** Vì sao không dùng `ZoneId.systemDefault()` để đoán múi giờ người tổ chức?

**Đáp án:** Vì đó là timezone của máy chạy chương trình, không phải ý định người dùng.

**Câu 3.** Một lịch một lần đã resolve nên lấy gì làm mốc chung giữa các participant?

**Đáp án:** `Instant`, có thể kèm dữ liệu ZoneId và local time đầu vào để audit.

**Câu 4.** `ZoneRules.getValidOffsets(local)` trả danh sách rỗng nghĩa gì?

**Đáp án:** Local time nằm trong gap, không có offset hợp lệ của zone tại giờ đó.

**Câu 5.** Trong overlap, vì sao cùng 02:30 có thể chỉ hai Instant khác nhau?

**Đáp án:** Vì đồng hồ bị lùi và có hai offset hợp lệ. Phải chọn offset hoặc chính sách rõ.

**Câu 6.** Muốn từ chối cặp local time và offset không hợp lệ cho ZoneId, dùng gì?

**Đáp án:** `ZonedDateTime.ofStrict(local, offset, zone)` sau khi kiểm tra/định nghĩa chính sách.

**Câu 7.** Với lịch 09:00 Paris hằng tuần, có nên cộng `Duration.ofDays(7)` vào Instant đầu không?

**Đáp án:** Không nếu phải giữ 09:00 local qua DST. Sinh ngày theo lịch rồi resolve trong `Europe/Paris`.

**Câu 8.** `OffsetDateTime` có lưu tên vùng Paris để tự áp dụng quy tắc DST trong nhiều năm không?

**Đáp án:** Không; nó chỉ giữ local date-time và offset. Cần ZoneId cho lịch vùng.

**Câu 9.** Hai buổi họp lần lượt [13:00,14:00) và [14:00,15:00) UTC có trùng nhau không?

**Đáp án:** Không, nếu dùng khoảng half-open [start,end).

**Câu 10.** Tại sao check conflict theo Instant chưa đủ để chống double-booking?

**Đáp án:** Hai request đồng thời có thể vượt qua check rồi cùng ghi; cần transaction/constraint.

**Câu 11.** Nếu người dùng đổi timezone xem lịch, có nên tự thay `startInstant` không?

**Đáp án:** Không. Đổi vùng hiển thị chỉ thay `ZonedDateTime` khi trình bày.

**Câu 12.** Nếu người dùng đổi giờ hẹn từ 09:00 Paris sang 10:00 Paris, có nên giữ cùng Instant không?

**Đáp án:** Thông thường không; đó là thay đổi thời gian họp, phải resolve local time mới theo ZoneId.

**Câu 13.** Vì sao không lưu riêng offset +01:00 cho toàn bộ lịch lặp Paris?

**Đáp án:** Vì offset của vùng có thể chuyển thành +02:00 qua DST hoặc đổi theo luật trong tương lai.

**Câu 14.** `ZonedDateTime.parse` với offset mâu thuẫn với ZoneId có bảo đảm giữ nguyên local time người gửi nhập không?

**Đáp án:** Không. Parser có thể lấy offset để xác định Instant rồi thể hiện lại theo rules của vùng; nếu cần validate ba thành phần, dùng ofStrict.

**Câu 15.** Muốn nhắc nhở 15 phút trước buổi họp đã chốt, nên tính thế nào?

**Đáp án:** `meetingInstant.minus(Duration.ofMinutes(15))`, không dùng giờ server mặc định.

**Câu 16.** Một quy tắc lặp bị thay đổi Instant sau khi cập nhật tzdb, hệ thống cần làm gì?

**Đáp án:** Áp dụng chính sách sản phẩm đã công bố: giữ giờ địa phương và tính lại hoặc giữ timestamp đã chốt, đánh dấu version/audit và thông báo người liên quan khi cần.

## 23. Tài liệu chính thức

- [Oracle Java SE 26 — ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): chuyển Instant, DST gap/overlap, `ofStrict` và xử lý offset.
- [Oracle Java SE 26 — ZoneRules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html): `getValidOffsets`, `getTransition`, `isValidOffset` và các quy tắc vùng.
- [Oracle Java SE 26 — ZoneId](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): timezone ID, quy tắc offset và lỗi zone.
- [Oracle Java SE 26 — Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): mốc trên timeline, cộng/trừ Duration và chuyển đổi vùng.
- [Oracle Java SE 26 — LocalDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html): local date-time không có zone/offset.
- [Oracle Java SE 26 — Duration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html): thời lượng tính theo elapsed-time.
- [IANA — Time Zone Database](https://www.iana.org/time-zones): nguồn quy tắc múi giờ được cập nhật định kỳ theo các thay đổi pháp lý.
- [IANA — Time Zone Database Releases](https://www.iana.org/time-zones/releases): lịch sử các bản tzdb, minh chứng cần quản lý cập nhật dữ liệu vùng.

**Kết luận:** Thiết kế lịch hẹn nhiều múi giờ đúng đắn phải tách **ý định địa phương** khỏi **mốc thời gian tuyệt đối**. Lịch một lần được resolve thành Instant rồi hiển thị trong ZoneId của từng người; lịch lặp phải giữ local schedule + ZoneId và xử lý từng occurrence theo quy tắc DST. Kiểm tra gap/overlap, chỉ chấp nhận offset hợp lệ, so sánh xung đột trên Instant, phân biệt duration thực với lịch địa phương, và chuẩn bị cho những thay đổi tzdb là những nguyên tắc giúp hệ thống lịch vẫn đúng khi người dùng, máy chủ và luật múi giờ thay đổi.