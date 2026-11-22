# Chuyển LocalDateTime thành ZonedDateTime: cần ZoneId và chính sách DST

## 1. Vấn đề cốt lõi

`LocalDateTime` biểu diễn **ngày và giờ địa phương**: ví dụ, `2024-11-03T01:30`. Nó **không chứa múi giờ, offset UTC và không xác định duy nhất một thời điểm tuyệt đối**. Muốn chuyển sang `ZonedDateTime`, ứng dụng phải cung cấp một `ZoneId` và quyết định cách xử lý những giờ địa phương bị **thiếu** hoặc **lặp lại** khi quy tắc múi giờ đổi offset.

Ví dụ cùng chuỗi `2024-11-03T01:30`:

- Tại `Asia/Ho_Chi_Minh` trong ngày đó, offset là `+07:00` và giờ địa phương xác định một thời điểm.
- Tại `America/New_York`, ngày 03/11/2024 là ngày kết thúc DST: `01:30` xuất hiện **hai lần**, một lần với `-04:00` và một lần với `-05:00`.
- Tại `America/New_York` ngày 10/03/2024, khoảng `02:00–02:59:59.999999999` **không tồn tại** vì đồng hồ nhảy từ `01:59:59` tới `03:00`.

Vì vậy, lời gọi `local.atZone(zone)` luôn tạo ra một giá trị hoặc ném lỗi với các trường hợp vượt giới hạn, nhưng **không tự phản ánh chính sách nghiệp vụ của bạn**. Trong DST gap, Java mặc định dịch giờ về phía trước; trong DST overlap, Java mặc định ưu tiên offset trước khi đồng hồ chuyển, trừ khi API hoặc trạng thái chuyển đổi cụ thể quyết định khác. Với đặt lịch, thanh toán, deadline hay log sự kiện, cần xác định rõ có chấp nhận những lựa chọn mặc định này hay không.

Mục tiêu bài học:

1. Hiểu tại sao chỉ có `LocalDateTime` là chưa đủ.
2. Biết cách dùng `ZoneId`, `ZoneRules`, `ZoneOffsetTransition` và các phương thức chuyển đổi.
3. Phân biệt **normal**, **gap**, **overlap** qua số offset hợp lệ.
4. Chọn chính sách DST tường minh: từ chối, điều chỉnh giờ, hoặc yêu cầu chọn offset.
5. Biết cách bảo toàn thời điểm tuyệt đối khi chuyển múi giờ và viết kiểm thử ổn định.

## 2. Phân biệt kiểu dữ liệu và ý nghĩa

| Kiểu Java | Chứa thông tin | Điều chưa biết |
|---|---|---|
| `LocalDateTime` | Năm, tháng, ngày, giờ, phút, giây, nano | Không có offset hay zone |
| `ZoneId` | Định danh vùng múi giờ hoặc offset cố định | Chưa tự gắn với một giờ cụ thể |
| `ZoneOffset` | Độ lệch với UTC, ví dụ `-04:00` hoặc `+07:00` | Không chứa lịch sử/quy tắc DST của một vùng |
| `ZonedDateTime` | Giờ địa phương, `ZoneId`, offset được chọn | Đã xác định được một instant |
| `OffsetDateTime` | Giờ địa phương và offset cụ thể | Không giữ quy tắc múi giờ vùng |
| `Instant` | Thời điểm tuyệt đối trên dòng thời gian | Không có giờ địa phương nếu chưa chọn zone |

Một `ZoneId` dạng vùng, ví dụ `America/New_York`, sử dụng **quy tắc timezone (tzdb)** để tìm offset hợp lệ theo ngày giờ. Quy tắc có thể gồm DST và cả các thay đổi lịch sử/chính sách khác. `ZoneOffset.ofHours(-5)` chỉ diễn đạt offset cố định `-05:00`, **không tự biết khi nào New York chuyển DST**.

Hai đoạn sau có ý nghĩa khác nhau:

~~~java
ZoneId region = ZoneId.of("America/New_York");
ZoneOffset fixed = ZoneOffset.ofHours(-5);
~~~

Nếu ứng dụng đặt cuộc họp “09:00 tại New York vào tháng 7”, phải giữ vùng `America/New_York` để áp dụng quy tắc của ngày tháng 7. Dùng offset `-05:00` cố định có thể sai giờ thực tế vì mùa hè New York thường là `-04:00`.

## 3. Chuyển đổi cơ bản khi giờ địa phương hợp lệ duy nhất

Cách ngắn gọn:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 1, 15, 10, 30);
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime result = local.atZone(zone);
~~~

Ở thời điểm minh họa, New York có offset `-05:00`, nên `result` là:

~~~text
2024-01-15T10:30-05:00[America/New_York]
~~~

Có thể dùng factory tương đương khi có ngày giờ địa phương và zone:

~~~java
ZonedDateTime result =
        ZonedDateTime.of(local, zone);
~~~

Trong trường hợp bình thường, `local.atZone(zone)` hoặc `ZonedDateTime.of(local, zone)` chọn offset duy nhất đúng theo `ZoneRules`. Khi ngày giờ nằm trong **gap/overlap**, hai cách đều dùng chính sách giải quyết mặc định của Java.

Nếu chưa có `ZoneId`, không thể suy ra offset chính xác từ `LocalDateTime` một mình. `ZoneId.systemDefault()` chỉ phù hợp khi **múi giờ hệ thống chính là quy định nghiệp vụ**; trong dịch vụ chạy trên nhiều máy, container hay CI, timezone hệ điều hành có thể khác nhau.

### 3.1. Một giờ địa phương có bao nhiêu thời điểm tương ứng?

Với `ZoneRules.getValidOffsets(localDateTime)`:

| Số offset hợp lệ | Trạng thái | Ý nghĩa |
|---:|---|---|
| 1 | Normal | Một giờ địa phương ánh xạ tới một instant |
| 0 | Gap | Giờ địa phương không tồn tại do thay đổi offset tiến |
| 2 | Overlap | Giờ địa phương xuất hiện hai lần do đổi offset lùi |

Trong mô hình timezone tiêu chuẩn của Java, gap và overlap thường gắn với chuyển đổi DST; tuy nhiên chuyển offset còn có thể do thay đổi luật hoặc múi giờ lịch sử, và độ dài chuyển không nhất thiết bằng một giờ.

Không nên chỉ kiểm tra `zonedDateTime != null` để kết luận “giờ đầu vào hợp lệ, được giữ nguyên”. Một `LocalDateTime` trong gap có thể được Java **điều chỉnh sang giờ khác** mà không ném exception.

## 4. DST gap — khoảng giờ không tồn tại

Tại `America/New_York`, ngày **10/03/2024**, đồng hồ nhảy từ gần `02:00` đến `03:00` khi bắt đầu DST. Vì vậy:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(2024, 3, 10, 2, 30);

ZonedDateTime adjusted = missing.atZone(ny);
System.out.println(adjusted);
~~~

Stdout:

~~~text
2024-03-10T03:30-04:00[America/New_York]
~~~

`02:30` không tồn tại tại New York ngày hôm đó. Mặc định Java đẩy giờ địa phương tiến thêm **độ dài gap là một giờ**, thành `03:30` và chọn offset mới `-04:00`. Việc này tiện trong một số ứng dụng, nhưng có thể không đúng nếu người dùng đã đặt một lịch “chính xác 02:30”.

Để phát hiện trước khi chuyển:

~~~java
ZoneRules rules = ny.getRules();
List<ZoneOffset> validOffsets = rules.getValidOffsets(missing);

System.out.println(validOffsets.size()); // 0
~~~

Khi gap xảy ra, `rules.getTransition(missing)` cung cấp `ZoneOffsetTransition` với offset trước/sau và độ dài chuyển tiếp. Với ngày trên:

~~~java
ZoneOffsetTransition transition = rules.getTransition(missing);
System.out.println(transition.getDuration());      // PT1H
System.out.println(transition.getDateTimeAfter()); // 2024-03-10T03:00
~~~

`getDateTimeAfter()` là **đầu khoảng giờ hợp lệ sau chuyển đổi**, trong khi chuyển mặc định của `02:30` thành `03:30` bảo toàn số phút trong khoảng gap bằng cách đẩy toàn bộ giờ thêm một giờ. Đây là **hai chính sách khác nhau**:

- “Dịch thêm độ dài gap”: `02:30 → 03:30`.
- “Chuyển đến thời điểm hợp lệ đầu tiên sau gap”: `02:30 → 03:00`.

Không thể tự quyết định thay người dùng; tùy ứng dụng hẹn giờ, deadline hay phiên làm việc mà chính sách phù hợp khác nhau.

## 5. DST overlap — một giờ xuất hiện hai lần

Tại `America/New_York` ngày **03/11/2024**, khi kết thúc DST, đồng hồ đổi offset từ `-04:00` sang `-05:00`. Giờ `01:30` xuất hiện hai lần:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime repeated = LocalDateTime.of(2024, 11, 3, 1, 30);

ZonedDateTime first = repeated.atZone(ny);
ZonedDateTime second = first.withLaterOffsetAtOverlap();
~~~

Hai kết quả:

~~~text
first  = 2024-11-03T01:30-04:00[America/New_York]
second = 2024-11-03T01:30-05:00[America/New_York]
~~~

Mặc định `atZone(ny)` chọn **offset trước chuyển đổi** trong overlap (`-04:00` ở ví dụ này). `withLaterOffsetAtOverlap()` chọn **offset sau chuyển đổi** (`-05:00`). Tên phương thức “earlier/later offset” trong `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()` chỉ cách chọn hai offset tại overlap; với New York, lần đầu xảy ra sớm hơn trên dòng thời gian tuyệt đối.

Các instant tương ứng:

~~~text
first.toInstant()  = 2024-11-03T05:30:00Z
second.toInstant() = 2024-11-03T06:30:00Z
~~~

Cùng “01:30 tại New York” nhưng chênh **một giờ tuyệt đối**. Nếu lưu duy nhất chuỗi `2024-11-03T01:30` và vùng New York rồi sau đó khôi phục mà không giữ lựa chọn offset, bạn có thể không thể xác định sự kiện xảy ra trong lần nào.

Đọc các offset hợp lệ:

~~~java
List<ZoneOffset> offsets =
        ny.getRules().getValidOffsets(repeated);
System.out.println(offsets);
~~~

Stdout:

~~~text
[-04:00, -05:00]
~~~

Thứ tự trả về thường là offset trước chuyển đổi, rồi offset sau chuyển đổi. Tuy nhiên, nghiệp vụ nên nêu rõ **“lần đầu” hay “lần sau”** hoặc **offset cụ thể**, không yêu cầu người dùng tự đoán từ hai số này.

## 6. Ba chính sách cần lựa chọn khi chuyển đổi

Một ứng dụng nghiêm túc cần mô tả cách xử lý **gap**, **overlap** và **giờ bình thường**. Các lựa chọn phổ biến:

| Trạng thái | Chính sách 1 | Chính sách 2 | Rủi ro nếu mặc định âm thầm |
|---|---|---|---|
| Normal (1 offset) | Chọn offset hợp lệ duy nhất | — | Ít mơ hồ |
| Gap (0 offset) | Từ chối để người dùng chọn giờ khác | Dịch theo độ dài gap hoặc sang đầu khoảng hợp lệ | Lịch bị chuyển thành giờ người dùng không nhập |
| Overlap (2 offset) | Yêu cầu chọn “lần đầu/lần sau” | Quy ước chọn offset trước/sau chuyển đổi | Sự kiện có thể lệch một giờ |

Với **lịch họp quan trọng, phiên giao dịch, audit hoặc hệ thống cần chính xác instant**, chính sách **từ chối gap và yêu cầu offset ở overlap** giúp tránh mơ hồ. Với ứng dụng hiển thị hoặc lịch đặt lặp lại có quy tắc rõ, có thể chủ động chọn “dịch qua gap” và “offset trước chuyển đổi” rồi tài liệu hóa.

### 6.1. APIs giải quyết cụ thể

- `local.atZone(zone)` / `ZonedDateTime.of(local, zone)`: dùng quy tắc mặc định; gap có thể được điều chỉnh, overlap thường chọn offset trước chuyển đổi.
- `ZonedDateTime.ofLocal(local, zone, preferredOffset)`: ưu tiên offset nếu nó hợp lệ trong overlap; nếu không, áp dụng quy tắc mặc định. **Không phải API strict**.
- `ZonedDateTime.ofStrict(local, offset, zone)`: chấp nhận **chỉ khi offset được chọn hợp lệ** với local date-time trong zone; ném `DateTimeException` trong gap hoặc khi offset không hợp lệ.
- `zoned.withEarlierOffsetAtOverlap()` / `withLaterOffsetAtOverlap()`: chọn một trong hai offset khi đối tượng nằm trong overlap. Ngoài overlap, chúng không đổi instant vì chỉ có một offset thích hợp.
- `zone.getRules().getValidOffsets(local)`: kiểm tra có 0/1/2 offset để tự thực thi chính sách.

**Lưu ý:** Chữ “strict” ở `ofStrict` thể hiện kiểm tra chính xác bộ ba local time + offset + zone. Với overlap, nếu bạn cấp **một offset hợp lệ trong hai offset**, `ofStrict` vẫn nhận; nó không tự hỏi người dùng nên chọn lần nào.

### 6.2. Ví dụ chọn offset tường minh

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);

ZonedDateTime earlier = ZonedDateTime.ofStrict(
        local, ZoneOffset.ofHours(-4), zone);

ZonedDateTime later = ZonedDateTime.ofStrict(
        local, ZoneOffset.ofHours(-5), zone);
~~~

Đây là hai giá trị hợp lệ khác nhau, cùng local time và zone, nhưng khác instant. Nếu truyền `ZoneOffset.ofHours(-5)` cho ngày giờ trong gap `2024-03-10T02:30`, `ofStrict` sẽ ném `DateTimeException` vì không có offset hợp lệ nào cho giờ bị thiếu.

## 7. Chương trình Java 17+ chạy độc lập

Lưu thành tệp **`DstConversionDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstConversionDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime normal =
                LocalDateTime.of(2024, 1, 15, 12, 0);
        System.out.println("Normal offsets: "
                + rules.getValidOffsets(normal));
        System.out.println("Normal: " + normal.atZone(zone));

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 10, 2, 30);
        List<ZoneOffset> gapOffsets = rules.getValidOffsets(gap);
        ZoneOffsetTransition gapTransition = rules.getTransition(gap);

        System.out.println("Gap offsets: " + gapOffsets.size());
        System.out.println("Gap duration: "
                + gapTransition.getDuration());
        System.out.println("Gap default: " + gap.atZone(zone));

        try {
            ZonedDateTime.ofStrict(
                    gap, ZoneOffset.ofHours(-5), zone);
        } catch (DateTimeException ex) {
            System.out.println("Gap strict: rejected");
        }

        LocalDateTime overlap =
                LocalDateTime.of(2024, 11, 3, 1, 30);
        ZonedDateTime earlier = overlap.atZone(zone);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));
        System.out.println("Overlap earlier: " + earlier);
        System.out.println("Overlap later: " + later);
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Later instant: " + later.toInstant());

        ZonedDateTime strictLater = ZonedDateTime.ofStrict(
                overlap, ZoneOffset.ofHours(-5), zone);
        System.out.println("Strict later: " + strictLater);
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac DstConversionDemo.java
java DstConversionDemo
~~~

Stdout trên JDK có quy tắc tzdb tương ứng với New York năm 2024:

~~~text
Normal offsets: [-05:00]
Normal: 2024-01-15T12:00-05:00[America/New_York]
Gap offsets: 0
Gap duration: PT1H
Gap default: 2024-03-10T03:30-04:00[America/New_York]
Gap strict: rejected
Overlap offsets: [-04:00, -05:00]
Overlap earlier: 2024-11-03T01:30-04:00[America/New_York]
Overlap later: 2024-11-03T01:30-05:00[America/New_York]
Earlier instant: 2024-11-03T05:30:00Z
Later instant: 2024-11-03T06:30:00Z
Strict later: 2024-11-03T01:30-05:00[America/New_York]
~~~

Ví dụ dùng ngày đã biết và không gọi đồng hồ hiện tại. Khi quy tắc timezone được cập nhật cho vùng khác hoặc một thời kỳ khác, kết quả có thể đổi theo phiên bản cơ sở dữ liệu timezone của JDK. Điều đó cho thấy **quy tắc múi giờ là dữ liệu phụ thuộc môi trường**, không nên hardcode offset cho một vùng ở mọi ngày.

## 8. Viết bộ giải quyết DST theo chính sách ứng dụng

Bài toán thực tế thường là người dùng nhập:

~~~text
localDateTime = 2024-11-03T01:30
zoneId        = America/New_York
preference    = AFTER_TRANSITION
~~~

Ứng dụng có thể kiểm tra trước khi tạo và từ chối nếu chưa đủ thông tin:

~~~java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public final class StrictDstResolver {
    public static ZonedDateTime resolve(
            LocalDateTime local,
            ZoneId zone,
            boolean chooseLaterOffset) {

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new DateTimeException(
                    "Local time does not exist in zone: " + local);
        }

        if (offsets.size() > 2) {
            throw new DateTimeException("Unexpected offset count");
        }

        ZoneOffset chosen = offsets.size() == 1
                ? offsets.get(0)
                : offsets.get(chooseLaterOffset ? 1 : 0);

        return ZonedDateTime.ofStrict(local, chosen, zone);
    }
}
~~~

Đây là một lớp độc lập đặt trong **`StrictDstResolver.java`**. Nó **từ chối gap** và chọn offset trước/sau chuyển đổi theo tham số của ứng dụng. Trong chương trình production, tên `chooseLaterOffset` chỉ nên dùng khi nguồn yêu cầu đã xác định rõ lựa chọn. Nếu người dùng chưa chọn offset cho overlap, nên trả trạng thái cần xác nhận thay vì tự đặt boolean mặc định.

Một chính sách khác là dịch giờ bị thiếu:

~~~java
ZoneOffsetTransition transition =
        zone.getRules().getTransition(local);

if (transition != null && transition.isGap()) {
    LocalDateTime shifted =
            local.plus(transition.getDuration());
    ZonedDateTime adjusted = shifted.atZone(zone);
}
~~~

Đây là **đoạn minh họa bên trong phương thức** khi đã có biến `zone` (`ZoneId`), `local` (`LocalDateTime`) và các import phù hợp. Nó đưa `02:30` của New York ngày 10/03/2024 thành `03:30`. Nếu yêu cầu là “bắt đầu sớm nhất có thể sau gap”, chọn `transition.getDateTimeAfter()` sẽ cho `03:00` ở ví dụ này. Đây là hai phương án khác nhau; cần một quyết định nghiệp vụ rõ ràng.

### 8.1. Xử lý đầu vào trong REST API hoặc UI

Khi người dùng chỉ nhập local date-time và vùng, một API có thể trả kết quả kiểm tra trước khi lưu:

| Dạng | Phản hồi phù hợp |
|---|---|
| Normal | Tạo `ZonedDateTime` và lưu hoặc trả instant |
| Gap | Báo “giờ không tồn tại”, đưa ra giờ hợp lệ gần nhất hoặc đề nghị đổi giờ |
| Overlap | Báo giờ có hai offset; yêu cầu chọn lượt đầu/lượt sau |
| ZoneId không hợp lệ | Trả lỗi validation; không tự đổi sang timezone máy chủ |

Nếu sản phẩm đã có quy tắc chuẩn (ví dụ “dịch gap theo độ dài gap, chọn lần xảy ra sớm hơn”), có thể không cần hỏi người dùng mỗi lần. Nhưng quy tắc phải nằm trong hợp đồng API, tài liệu nghiệp vụ và test; không nên bị ẩn trong hành vi ngầm của `atZone`.

## 9. Đã có Instant thì cách chuyển lại khác

Nếu bạn có một `Instant`, nó **đã xác định chính xác thời điểm**. Muốn trình bày trong vùng múi giờ:

~~~java
Instant instant =
        Instant.parse("2024-11-03T06:30:00Z");
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime zoned = instant.atZone(zone);
// 2024-11-03T01:30-05:00[America/New_York]
~~~

Khi chuyển **Instant → ZonedDateTime**, thông thường không có sự mơ hồ DST về instant: zone chọn được offset chính xác cho thời điểm đã biết. Ngược lại, **LocalDateTime → ZonedDateTime** cần giải bài toán 0/1/2 offset.

Một API ít dùng hơn:

~~~java
ZonedDateTime zoned = ZonedDateTime.ofInstant(
        local, ZoneOffset.ofHours(-5), zone);
~~~

Khi cung cấp `local + offset`, cặp đó đã định danh một instant. `ofInstant(local, offset, zone)` diễn giải cặp thành instant rồi biểu diễn lại trong zone đích; nếu offset không hợp lệ với local của zone đích, giờ địa phương có thể **thay đổi**. Không xem nó là `ofStrict`, bởi `ofStrict` sẽ từ chối bộ ba không hợp lệ. Khi cần bảo vệ lựa chọn của người dùng và kiểm tra offset có đúng cho zone không, dùng `ofStrict`.

## 10. Đổi zone: giữ instant hay giữ local time?

Sau khi có một `ZonedDateTime`, có hai phép chuyển đổi rất dễ nhầm:

~~~java
ZonedDateTime ny = LocalDateTime
        .of(2024, 11, 3, 1, 30)
        .atZone(ZoneId.of("America/New_York"));

ZonedDateTime sameInstant =
        ny.withZoneSameInstant(ZoneOffset.UTC);

ZonedDateTime sameLocal =
        ny.withZoneSameLocal(ZoneOffset.UTC);
~~~

Kết quả:

~~~text
ny          = 2024-11-03T01:30-04:00[America/New_York]
sameInstant = 2024-11-03T05:30Z
sameLocal   = 2024-11-03T01:30Z
~~~

- `withZoneSameInstant(targetZone)`: **giữ nguyên thời điểm tuyệt đối**, đổi cách nhìn ngày giờ cho vùng đích. Đây là lựa chọn phù hợp khi chuyển timestamp sự kiện.
- `withZoneSameLocal(targetZone)`: cố giữ **đồng hồ địa phương** tương ứng; instant có thể đổi và vẫn chịu quy tắc gap/overlap tại vùng mới. Chỉ dùng khi chủ ý tái diễn giải giờ đồng hồ ở một vùng khác.

Đừng áp dụng `withZoneSameLocal(ZoneOffset.UTC)` để “chuyển giờ New York sang UTC” khi mục đích là giữ cùng sự kiện: thao tác đó có thể dịch chuyển instant nhiều giờ.

## 11. DST ảnh hưởng phép cộng một ngày và 24 giờ

Khi đã có `ZonedDateTime`, **cộng một ngày lịch** và **cộng 24 giờ tuyệt đối** có thể cho kết quả khác nhau ở ngày chuyển DST:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, ny);

ZonedDateTime oneCalendarDay = start.plusDays(1);
ZonedDateTime twentyFourHours = start.plusHours(24);
~~~

Với New York khi bắt đầu DST 2024:

~~~text
start           = 2024-03-09T12:00-05:00[America/New_York]
oneCalendarDay  = 2024-03-10T12:00-04:00[America/New_York]
twentyFourHours = 2024-03-10T13:00-04:00[America/New_York]
~~~

`plusDays(1)` làm việc theo ngày lịch địa phương: giữ 12:00 ngày hôm sau và đổi offset, chỉ **23 giờ tuyệt đối** trôi qua. `plusHours(24)` cộng lượng thời gian 24 giờ, dẫn đến 13:00 theo giờ địa phương ngày hôm sau.

Chọn phép cộng theo bản chất nghiệp vụ:

- “Họp lúc 12:00 hằng ngày tại New York” → ngày lịch địa phương và quy tắc xử lý gap/overlap.
- “Chạy một tác vụ sau đúng 24 giờ đã trôi qua” → thời lượng theo instant.

Với lịch lặp, mỗi lần xuất hiện có thể cần được kiểm tra riêng theo `ZoneRules`. Không suy từ offset ngày hôm nay rằng nó sẽ đúng ở mọi ngày trong tương lai.

## 12. Thiết kế lưu trữ và round-trip

Nếu mục tiêu là tái tạo chính xác một sự kiện đã xảy ra, **`Instant`** là cách lưu phù hợp cho thời điểm tuyệt đối; khi hiển thị, chuyển sang `ZoneId` theo yêu cầu:

~~~java
Instant occurredAt = zoned.toInstant();
ZonedDateTime view = occurredAt.atZone(displayZone);
~~~

Cần phân biệt:

1. **Sự kiện đã xảy ra:** lưu instant, có thể lưu thêm zone để hiển thị theo quy ước.
2. **Cuộc hẹn trong tương lai vào “09:00 tại New York”:** lưu ngày giờ địa phương, `ZoneId` và chính sách DST để áp dụng quy tắc vùng ở ngày thực hiện. Quy tắc timezone có thể thay đổi theo luật, nên dùng tzdb mới và xác định chiến lược cập nhật lịch.
3. **Một giờ trùng lặp cụ thể đã được chọn:** lưu `Instant` hoặc offset/lựa chọn lần đầu/lần sau để không mất quyết định người dùng. Chỉ giữ local date-time và zone có thể làm mất thông tin offset đã chọn.
4. **Chỉ có offset cố định từ nguồn:** lưu `OffsetDateTime` hoặc chuyển thành instant; một offset không thay thế đầy đủ region `ZoneId` cho lịch hẹn theo vùng.

Trong JSON hoặc CSDL, tránh lưu chuỗi local date-time một mình rồi giả định backend có thể suy ra timestamp duy nhất. Ví dụ payload có thể dùng:

~~~json
{
  "localDateTime": "2024-11-03T01:30:00",
  "zoneId": "America/New_York",
  "preferredOffset": "-05:00"
}
~~~

Backend dùng `ofStrict` để đảm bảo offset được chọn thực sự hợp lệ theo tzdb. Với gap, API nên từ chối hoặc yêu cầu xử lý riêng; không được đánh đồng một offset được cung cấp với việc local date-time có tồn tại trong vùng.

## 13. Những lỗi phổ biến

1. **Chỉ có LocalDateTime rồi kết luận đã biết một Instant:** sai; thiếu offset hoặc `ZoneId` và khả năng mơ hồ DST.
2. **Dùng ZoneId.systemDefault() để suy ra vùng người dùng:** server/CI có thể chạy UTC và thay đổi môi trường.
3. **Dùng ZoneOffset cố định thay cho ZoneId vùng trong lịch hẹn tương lai:** offset của một vùng có thể thay đổi theo DST hoặc pháp luật.
4. **Tin rằng atZone giữ nguyên local date-time trong gap:** Java mặc định dịch giờ bị thiếu về phía trước.
5. **Quên overlap cho hai instant khác nhau:** cùng “01:30” có thể xảy ra hai lần, cần giữ hoặc hỏi lựa chọn offset.
6. **Dùng ofLocal với preferredOffset và nghĩ đây là kiểm tra strict:** API có thể fallback, nên dùng `ofStrict` để bắt lỗi offset không hợp lệ.
7. **Dùng ofInstant(local, offset, zone) để xác thực bộ ba:** API có thể điều chỉnh local khi offset không phù hợp với zone đích; `ofStrict` mới kiểm tra.
8. **Nhầm withZoneSameLocal với withZoneSameInstant:** phép đầu có thể thay đổi sự kiện tuyệt đối.
9. **Coi mọi ngày là 24 giờ:** một ngày địa phương có thể dài 23/25 giờ hoặc độ dài khác vì chuyển offset.
10. **Tính lịch hằng ngày bằng cộng 86.400 giây:** có thể làm giờ địa phương lệch sau DST.
11. **Hardcode gap luôn 1 giờ và overlap luôn 2 offset cách 1 giờ:** nhiều vùng có chuyển đổi khác một giờ; nên đọc `ZoneOffsetTransition`.
12. **Giả định mọi quốc gia đều áp dụng DST:** nhiều vùng không sử dụng DST hoặc có lịch sử chuyển đổi riêng.
13. **Không kiểm tra timezone database ở runtime:** tzdb có thể được cập nhật do thay đổi luật; test với những ngày/vùng trọng yếu.
14. **Chỉ lưu local date-time và zone sau khi chọn offset trong overlap:** nếu cần tái tạo chính xác sự kiện, phải lưu instant hoặc offset đã chọn.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `LocalDateTime.of(2024,11,3,1,30)` chưa xác định một instant khi gắn `America/New_York`?

**Đáp án:** Do DST kết thúc ngày hôm đó khiến giờ 01:30 xuất hiện với hai offset `-04:00` và `-05:00`, tương ứng hai instant cách nhau một giờ.

**Câu 2.** `LocalDateTime.of(2024,3,10,2,30).atZone(ZoneId.of("America/New_York"))` cho gì?

**Đáp án:** `2024-03-10T03:30-04:00[America/New_York]`, vì `02:30` thuộc gap một giờ và Java điều chỉnh về phía trước.

**Câu 3.** Làm sao từ chối giờ địa phương không tồn tại?

**Đáp án:** Kiểm tra `zone.getRules().getValidOffsets(local).isEmpty()` và báo lỗi, hoặc dùng `ZonedDateTime.ofStrict(local, offset, zone)` khi offset đã được xác định.

**Câu 4.** Muốn chọn lần thứ hai của 01:30 New York trong overlap, làm thế nào?

**Đáp án:** Chọn offset `-05:00` bằng `ZonedDateTime.ofStrict(local, ZoneOffset.ofHours(-5), zone)` hoặc gọi `withLaterOffsetAtOverlap()` từ giá trị overlap phù hợp.

**Câu 5.** Khác biệt `withZoneSameInstant` và `withZoneSameLocal`?

**Đáp án:** Một cái giữ nguyên **instant**, cái kia cố giữ **giờ địa phương**, có thể thay đổi instant.

**Câu 6.** Vì sao `plusDays(1)` có thể khác `plusHours(24)` trên `ZonedDateTime`?

**Đáp án:** `plusDays` làm việc theo ngày lịch địa phương, còn `plusHours` theo lượng thời gian trên trục instant; ngày có DST có thể không dài đúng 24 giờ.

**Câu 7.** Khi chỉ muốn hiển thị một `Instant` đã biết ở New York, có cần chọn offset overlap thủ công không?

**Đáp án:** Không. `instant.atZone(ny)` tự xác định offset từ instant và quy tắc zone; ambiguity chỉ nảy sinh khi xuất phát từ local date-time thiếu offset.

**Câu 8.** Có nên lưu một offset `-05:00` cho tất cả cuộc họp New York quanh năm?

**Đáp án:** Không. Dùng `ZoneId.of("America/New_York")` để áp dụng quy tắc vùng ở ngày cụ thể và xử lý gap/overlap.

## 15. Quy tắc thực hành

- **Đầu vào là LocalDateTime** → yêu cầu `ZoneId`, đọc `ZoneRules` và chọn chính sách cho normal/gap/overlap trước khi khẳng định đã có một instant.
- **Đầu vào là Instant** → có thể gọi `instant.atZone(zone)`; không có mơ hồ về thời điểm tuyệt đối.
- **Gap** → từ chối, chuyển thêm độ dài gap hoặc chọn đầu khoảng giờ hợp lệ, tùy yêu cầu nghiệp vụ.
- **Overlap** → chọn offset trước/sau chuyển đổi hoặc yêu cầu người dùng xác nhận; lưu lựa chọn để có thể tái tạo.
- **Dữ liệu audit/sự kiện** → lưu `Instant` khi cần định danh thời điểm; **lịch hẹn theo giờ vùng** → lưu local time, region ZoneId, và quy tắc chuyển đổi.
- **Chuyển sang zone khác** → dùng `withZoneSameInstant` khi muốn giữ sự kiện, chỉ dùng `withZoneSameLocal` khi có chủ đích tái diễn giải giờ đồng hồ.

`LocalDateTime.atZone(zone)` rất thuận tiện, nhưng sự đúng đắn của hệ thống còn phụ thuộc cách định nghĩa và kiểm tra **chính sách DST** tại mọi lần chuyển local time thành instant.
