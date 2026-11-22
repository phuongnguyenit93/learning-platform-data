# Chuyển LocalDateTime thành epoch cần độ lệch UTC phù hợp

Khi chuyển ngày giờ sang **epoch** (số giây hoặc mili giây tính từ `1970-01-01T00:00:00Z`), một lỗi phổ biến là đưa một `LocalDateTime` vào phép chuyển đổi mà **không biết nó thuộc offset UTC nào**. `LocalDateTime` chỉ có các trường năm, tháng, ngày, giờ, phút, giây và nano giây. Nó **không chứa múi giờ và không chứa UTC offset**. Vì vậy, riêng giá trị `2024-08-15T09:30` chưa xác định một thời điểm tuyệt đối.

Ví dụ cùng một giờ địa phương `2024-08-15 09:30`:

- Nếu mang offset `+07:00` thì tương ứng `2024-08-15T02:30:00Z`.
- Nếu mang offset `+00:00` thì tương ứng `2024-08-15T09:30:00Z`.
- Nếu mang offset `-04:00` thì tương ứng `2024-08-15T13:30:00Z`.

Ba thời điểm khác nhau **7 giờ hoặc 11 giờ** dù các trường của `LocalDateTime` đều giống nhau. Muốn đổi sang epoch đúng, phải xác định **UTC offset thực sự áp dụng cho ngày giờ đó**, hoặc cung cấp **ZoneId** để tra quy tắc vùng và xử lý những giờ không tồn tại hoặc bị lặp.

## 1. Phân biệt LocalDateTime, ZoneOffset, ZoneId và Instant

| Kiểu | Chứa gì? | Có xác định được một Instant không? | Vai trò |
|---|---|---|---|
| `LocalDateTime` | Ngày và giờ địa phương, không có offset/zone. | **Không**, nếu đứng riêng. | Diễn đạt “09:30 ngày 15/08” theo lịch. |
| `ZoneOffset` | Độ lệch cố định với UTC, ví dụ `+07:00` hay `-04:00`. | Khi ghép cùng `LocalDateTime` thì **có**. | Ánh xạ giờ địa phương sang timeline bằng offset đã biết. |
| `ZoneId` | Danh tính vùng và quy tắc offset có thể thay đổi theo lịch sử, ví dụ `Asia/Ho_Chi_Minh`, `America/New_York`. | Có thể giải quyết bằng quy tắc vùng, nhưng cần xử lý **gap/overlap**. | Diễn giải giờ địa phương theo luật múi giờ tại ngày cụ thể. |
| `OffsetDateTime` | `LocalDateTime` cộng với `ZoneOffset`. | **Có**. | Mang local time và offset xác định tại một sự kiện. |
| `ZonedDateTime` | Ngày giờ cộng `ZoneId` và offset đã giải quyết. | **Có**. | Lịch và thời điểm gắn quy tắc vùng. |
| `Instant` | Điểm thời gian tuyệt đối trong trục thời gian Java. | Chính nó là thời điểm. | Lưu timestamp, giao tiếp liên hệ thống, đo khoảng giữa sự kiện. |

Một offset như `+07:00` là **độ lệch của đồng hồ tại một thời điểm**, không phải tên một vùng. Ví dụ `Asia/Ho_Chi_Minh` hiện thường mang `+07:00`, nhưng zone chứa thêm thông tin lịch sử và quy tắc có thể thay đổi; không nên thay `ZoneId` bằng offset cố định trong bài toán lịch tương lai.

Công thức trực giác:

~~~text
UTC instant = local date/time - UTC offset

09:30 +07:00 -> 02:30 UTC
09:30 -04:00 -> 13:30 UTC
~~~

Nếu giờ địa phương “nhanh hơn” UTC 7 giờ (`+07:00`) thì UTC phải **lùi 7 giờ** so với giờ địa phương, không cộng 7 giờ. Dấu offset rất dễ bị tính ngược.

## 2. Epoch second, epoch milli và đơn vị

**Unix epoch** là mốc `1970-01-01T00:00:00Z`. Trong các API Java thời gian thông dụng:

- `Instant.getEpochSecond()` và `LocalDateTime.toEpochSecond(ZoneOffset)`: số **giây** kể từ epoch, kiểu `long`.
- `Instant.toEpochMilli()`: số **mili giây** kể từ epoch, kiểu `long`.
- Phần lẻ dưới giây được giữ trong `Instant.getNano()` hoặc trường nano của đối tượng liên quan.

Không được lẫn `epochSecond` và `epochMilli`: hai giá trị thường khác nhau khoảng **1.000 lần**. Ví dụ `1723689000` giây tương ứng `1723689000000` mili giây, cùng một instant.

**Thời gian trước epoch** mang giá trị âm. Với thời điểm `1969-12-31T23:59:59.500Z`, `getEpochSecond()` bằng `-1` còn `toEpochMilli()` bằng `-500`. Điều này phù hợp với số giây nguyên theo mốc và phần nano lẻ, không đồng nghĩa “một giây âm không thể có phần lẻ”.

**Không phải nano giây kể từ epoch:** `System.nanoTime()` không liên quan đến Unix epoch, có mốc tùy ý và được dùng để đo thời lượng trôi qua. Không chuyển trực tiếp nó thành `Instant`.

## 3. Trường hợp đã biết chính xác UTC offset

Nếu đầu vào `LocalDateTime` **đi kèm UTC offset hợp lệ và đã được xác minh**, có hai cách tương đương:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 8, 15, 9, 30);
ZoneOffset offset = ZoneOffset.ofHours(7);

long seconds = local.toEpochSecond(offset);
Instant instant = local.atOffset(offset).toInstant();
long millis = instant.toEpochMilli();
~~~

Đây là đoạn mã minh họa; để chạy cần import các lớp `java.time` và đặt trong phương thức/class.

- `local.toEpochSecond(offset)` trả về giây epoch và cần **offset do người gọi cung cấp**.
- `local.atOffset(offset)` tạo `OffsetDateTime`; `toInstant()` cho mốc tuyệt đối, từ đó lấy giây/mili giây và phần nano.
- Không cần tự viết công thức trừ giờ, tránh nhầm dấu và trường hợp đổi ngày.

**Điều quan trọng:** `toEpochSecond(offset)` **không tự tra ZoneId để kiểm chứng offset**. Nếu truyền sai `+07:00` cho một thời gian thực ra thuộc `-04:00` thì Java vẫn tính được một con số hợp lệ về mặt phép tính, nhưng con số đó đại diện cho **thời điểm sai**.

### Ví dụ đầy đủ, đầu ra xác định

Tệp `FixedOffsetEpochDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class FixedOffsetEpochDemo {
    public static void main(String[] args) {
        LocalDateTime local = LocalDateTime.of(2024, 8, 15, 9, 30);
        ZoneOffset offset = ZoneOffset.ofHours(7);

        OffsetDateTime withOffset = local.atOffset(offset);
        Instant instant = withOffset.toInstant();

        System.out.println("Local: " + local);
        System.out.println("Offset: " + offset);
        System.out.println("OffsetDateTime: " + withOffset);
        System.out.println("UTC: " + instant);
        System.out.println("Seconds: " + local.toEpochSecond(offset));
        System.out.println("Millis: " + instant.toEpochMilli());
        System.out.println("Reconstructed: "
                + LocalDateTime.ofInstant(instant, offset));
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac FixedOffsetEpochDemo.java
java FixedOffsetEpochDemo
~~~

Kết quả:

~~~text
Local: 2024-08-15T09:30
Offset: +07:00
OffsetDateTime: 2024-08-15T09:30+07:00
UTC: 2024-08-15T02:30:00Z
Seconds: 1723689000
Millis: 1723689000000
Reconstructed: 2024-08-15T09:30
~~~

Cùng con số giờ địa phương, nếu cố tình đổi offset sang `UTC` (`ZoneOffset.UTC`), giá trị epoch sẽ ứng với `2024-08-15T09:30Z`, muộn hơn kết quả `+07:00` đúng 7 giờ. Việc dữ liệu mang giờ Việt Nam **không cho phép** mặc định ghi nó là UTC.

## 4. Nếu biết vị trí/múi giờ, hãy dùng ZoneId

Trong dữ liệu thực tế, người dùng thường cung cấp **địa điểm hoặc tên vùng**, ví dụ “09:00 giờ New York” hoặc “18:30 giờ Việt Nam”. Khi đó offset phải được xác định **theo ngày giờ của vùng**, vì một số vùng chuyển DST hoặc thay đổi chính sách múi giờ.

Ví dụ:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime winter = LocalDateTime.of(2024, 1, 15, 9, 0);
LocalDateTime summer = LocalDateTime.of(2024, 7, 15, 9, 0);

ZonedDateTime winterZoned = winter.atZone(zone);
ZonedDateTime summerZoned = summer.atZone(zone);
~~~

Đây là đoạn mã minh họa, cần import `java.time` và đặt vào chương trình. Tại New York trong năm 2024, mùa đông `09:00` dùng `-05:00`, còn mùa hè `09:00` dùng `-04:00`. Không thể lấy offset của **ngày hôm nay** áp dụng cho mọi ngày quá khứ hoặc tương lai.

Để đổi:

~~~text
LocalDateTime + ZoneId
        |
        v
Áp dụng quy tắc ZoneRules tại local date/time
        |
        v
ZonedDateTime (đã xác định offset; cần chính sách gap/overlap)
        |
        v
Instant -> epoch second / epoch milli
~~~

Các bước API thông thường:

~~~java
ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
long epochSecond = instant.getEpochSecond();
long epochMilli = instant.toEpochMilli();
~~~

Đây cũng là mã minh họa, trong đó `local` và `zone` phải đã được khai báo. Cách này thường phù hợp khi thời gian được diễn giải theo lịch địa phương ở một địa điểm, nhưng **`atZone` có chính sách mặc định khi gặp DST**. Đối với đặt lịch hoặc dữ liệu nghiệp vụ nhạy cảm, phải đánh giá chính sách đó trước khi chuyển.

## 5. DST có thể làm một LocalDateTime không có Instant hoặc có hai Instant

Trong một vùng có giờ mùa hè (*daylight saving time*, DST), đồng hồ có thể tiến hoặc lùi, dẫn đến hai trường hợp:

**Gap — giờ địa phương không tồn tại.** Ở `America/New_York` vào ngày 10/03/2024, đồng hồ tiến từ 01:59:59 (`-05:00`) sang 03:00:00 (`-04:00`). Giờ `2024-03-10T02:30` không tồn tại dưới quy tắc của vùng này. Nếu dùng `local.atZone(zone)`, Java mặc định **đẩy 02:30 thành 03:30** theo độ dài gap, cho `2024-03-10T03:30-04:00`. Đây là một sự điều chỉnh có thể không phù hợp nếu hệ thống cần từ chối giờ không có thật.

**Overlap — một giờ địa phương có hai thời điểm.** Ngày 03/11/2024, đồng hồ New York lùi từ 01:59:59 (`-04:00`) về 01:00:00 (`-05:00`). Do đó `2024-11-03T01:30` có thể là:

- `2024-11-03T01:30-04:00` = `2024-11-03T05:30:00Z`, epoch second `1730611800`.
- `2024-11-03T01:30-05:00` = `2024-11-03T06:30:00Z`, epoch second `1730615400`.

Chỉ riêng `LocalDateTime` không cho biết người dùng muốn lần 01:30 thứ nhất hay thứ hai. `atZone` mặc định ưu tiên offset trước chuyển đổi trong trường hợp này (`-04:00`); có thể chọn `withLaterOffsetAtOverlap()` để lấy lần sau.

### Ví dụ kiểm tra offset hợp lệ, chọn lần đầu/lần sau

Tệp `DstEpochDemo.java`:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class DstEpochDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneRules rules = newYork.getRules();

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        System.out.println("Gap offsets: " + rules.getValidOffsets(gap));
        System.out.println("Gap default: " + gap.atZone(newYork));

        System.out.println("Overlap offsets: "
                + rules.getValidOffsets(overlap));

        ZonedDateTime earlier = overlap.atZone(newYork);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("Earlier: " + earlier);
        System.out.println("Earlier instant: " + earlier.toInstant());
        System.out.println("Earlier epoch: "
                + earlier.toEpochSecond());

        System.out.println("Later: " + later);
        System.out.println("Later instant: " + later.toInstant());
        System.out.println("Later epoch: "
                + later.toEpochSecond());

        ZoneOffset chosen = ZoneOffset.ofHours(-5);
        ZonedDateTime strict = ZonedDateTime.ofStrict(
                overlap, chosen, newYork);
        System.out.println("Strict instant: " + strict.toInstant());
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac DstEpochDemo.java
java DstEpochDemo
~~~

Stdout với quy tắc New York năm 2024:

~~~text
Gap offsets: []
Gap default: 2024-03-10T03:30-04:00[America/New_York]
Overlap offsets: [-04:00, -05:00]
Earlier: 2024-11-03T01:30-04:00[America/New_York]
Earlier instant: 2024-11-03T05:30:00Z
Earlier epoch: 1730611800
Later: 2024-11-03T01:30-05:00[America/New_York]
Later instant: 2024-11-03T06:30:00Z
Later epoch: 1730615400
Strict instant: 2024-11-03T06:30:00Z
~~~

Các chi tiết cần hiểu:

- `rules.getValidOffsets(local)` trả **0 offset** ở gap, **1 offset** trong giờ bình thường và **2 offset** trong overlap.
- `LocalDateTime.atZone(zone)` xử lý gap/overlap theo quy tắc mặc định của Java; đây là **quyết định** mà ứng dụng nên chủ động kiểm tra.
- `ZonedDateTime.ofStrict(local, offset, zone)` yêu cầu offset được chọn thật sự hợp lệ cho vùng ở local time đó; nếu không thì ném `DateTimeException`.
- `toEpochSecond()` trên `ZonedDateTime` dùng offset đã xác định trong đối tượng. Hai giá trị có cùng `LocalDateTime` trong overlap nhưng có epoch khác nhau.

Một API đặt lịch cho người dùng nên từ chối hoặc xin chọn cách xử lý khi gặp gap/overlap, thay vì tùy tiện chọn một thời điểm và che giấu sự nhập nhằng.

## 6. Có offset chưa đủ nếu không biết nó đúng cho vùng và ngày

Ví dụ `2024-03-10T02:30` tại New York là giờ **không tồn tại**. Dù vậy:

~~~java
LocalDateTime impossible = LocalDateTime.of(2024, 3, 10, 2, 30);
long seconds = impossible.toEpochSecond(ZoneOffset.ofHours(-5));
~~~

Đây là đoạn minh họa, không phải chương trình độc lập; cần import `java.time` và đặt trong phương thức. Hai câu lệnh **không tự ném ngoại lệ DST** vì `toEpochSecond(ZoneOffset)` đơn giản xem `-05:00` là offset được cung cấp và tính mốc tuyệt đối. Kết quả là `1710055800` (tức `2024-03-10T07:30:00Z`), nhưng nhãn địa phương `02:30 -05:00` **không phải thời gian dân sự hợp lệ** trong New York vào lúc đó.

Nếu nhu cầu chỉ là “ngày giờ với offset cố định `-05:00`” thì phép đổi vẫn hợp lệ theo *offset* đó, vì `ZoneOffset` không áp dụng quy tắc DST. Nếu nhu cầu là “giờ lịch tại `America/New_York`” thì cần xác thực `ZoneRules`, và không được tự khẳng định offset đã cho hợp lệ chỉ vì phép tính số học chạy thành công.

Điều tương tự xảy ra với overlap: nếu API tự lấy một offset thay vì hỏi hoặc áp chính sách, nó sẽ đánh rơi ý định chọn **lần xuất hiện thứ nhất/thứ hai**. Kết quả có thể lệch cả giờ đối với log, đặt lịch, kế toán hoặc đối soát.

### Mẫu xử lý nghiêm ngặt một local time tại vùng

Chương trình `StrictLocalTimeDemo.java` minh họa ba khả năng hợp lệ:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StrictLocalTimeDemo {
    static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone, ZoneOffset selectedOffset) {

        List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local time does not exist in zone");
        }
        if (valid.size() == 2 && selectedOffset == null) {
            throw new IllegalArgumentException(
                    "Ambiguous local time; choose offset");
        }

        ZoneOffset offset = selectedOffset != null
                ? selectedOffset
                : valid.get(0);

        if (!valid.contains(offset)) {
            throw new IllegalArgumentException(
                    "Offset is not valid for local time");
        }
        return ZonedDateTime.ofStrict(local, offset, zone);
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

        ZonedDateTime result = resolve(
                overlap, zone, ZoneOffset.ofHours(-5));
        System.out.println(result.toInstant());
        System.out.println(result.toEpochSecond());
    }
}
~~~

Chạy:

~~~bash
javac StrictLocalTimeDemo.java
java StrictLocalTimeDemo
~~~

Stdout:

~~~text
2024-11-03T06:30:00Z
1730615400
~~~

Hàm `resolve` buộc người gọi chọn offset khi local time nhập nhằng. Ở giờ bình thường, nó tự chọn offset duy nhất; nếu người gọi cung cấp offset không hợp lệ, hàm từ chối. Đây chỉ là **một chính sách minh họa**; với gap, sản phẩm có thể có chính sách dời cuộc hẹn đến giờ hợp lệ tiếp theo, nhưng phải quy định rõ và kiểm thử.

## 7. Chi tiết nano giây: epoch seconds không mang hết phần lẻ

`LocalDateTime.toEpochSecond(offset)` chỉ trả về **số giây nguyên**. Nếu `LocalDateTime` có phần nano giây, việc chỉ lưu giây sẽ mất phần lẻ.

Ví dụ:

~~~java
LocalDateTime local = LocalDateTime.of(
        2024, 8, 15, 9, 30, 0, 123_456_789);
Instant instant = local.atOffset(ZoneOffset.ofHours(7)).toInstant();

long seconds = instant.getEpochSecond();
int nanos = instant.getNano();
long millis = instant.toEpochMilli();
~~~

Đây là đoạn mã minh họa, cần import lớp thời gian và đặt vào class/phương thức. Kết quả tương ứng:

- `seconds = 1723689000`.
- `nanos = 123456789`.
- `millis = 1723689000123`; phần dưới một mili giây không còn nằm trong số nguyên mili giây đó.

Khi cần round-trip **đúng từng nano giây**, lưu `Instant`, chuỗi ISO-8601 phù hợp, hoặc cặp epochSecond/nano. `Instant.ofEpochSecond(seconds, nanos)` dựng lại instant từ hai thành phần.

**Thận trọng trước epoch:** số giây âm và phần lẻ cần xử lý nhất quán theo quy ước Java. Chẳng hạn instant `1969-12-31T23:59:59.500Z` được biểu diễn bằng `epochSecond = -1`, `nano = 500000000`; `toEpochMilli()` là `-500`. Đừng đơn giản lấy `epochSecond = epochMillis / 1000` với phép chia nguyên của Java nếu cần giữ độ chính xác cho các epoch âm không tròn giây.

**Tràn số/miền giá trị:** `Instant.toEpochMilli()` có thể ném `ArithmeticException` nếu kết quả ngoài miền `long`. Các đối tượng thời gian hỗ trợ miền lớn hơn nhiều thời điểm ứng dụng. Với dữ liệu thực, nên kiểm tra phạm vi và kiểu lưu trữ.

## 8. Đọc lại từ epoch: phải chọn vùng để lấy đúng LocalDateTime

Một epoch xác định **một instant**, nhưng cách hiển thị thành ngày giờ địa phương phụ thuộc vào vùng:

~~~java
Instant instant = Instant.ofEpochSecond(1723689000L);
LocalDateTime inVietnam =
        LocalDateTime.ofInstant(instant, ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDateTime inUtc =
        LocalDateTime.ofInstant(instant, ZoneOffset.UTC);
~~~

Đây là mã minh họa; cần import `java.time`. `inVietnam` là `2024-08-15T09:30`, còn `inUtc` là `2024-08-15T02:30`. Hai biểu diễn cùng chỉ **một instant**.

Muốn round-trip dữ liệu lịch gốc:

1. Xác định rõ `LocalDateTime` ban đầu thuộc vùng/offset nào.
2. Chuyển sang `Instant` và lưu timestamp.
3. Nếu sau này muốn hiển thị theo **vùng gốc**, hãy lưu kèm `ZoneId` (và nếu liên quan, offset đã chọn lúc overlap/chính sách chuyển đổi).
4. Khi hiển thị lại, dùng `instant.atZone(zone)` hoặc `LocalDateTime.ofInstant(instant, zone)`.

**Không thể suy ngược duy nhất ZoneId từ epoch hoặc offset**: nhiều vùng chia sẻ cùng offset tại một thời điểm. Nếu chỉ lưu `LocalDateTime`, bạn cũng không thể dựng lại duy nhất instant mà không biết offset/zone và quy tắc áp dụng.

## 9. Thực tế khi đọc/ghi JSON, database và API

### 9.1. Tách hai loại dữ liệu nghiệp vụ

**Sự kiện đã xảy ra:** ví dụ “đơn hàng đã tạo lúc nào?” — ưu tiên lưu `Instant` hoặc timestamp có thông tin offset/UTC rõ ràng. Có thể truyền chuỗi ISO-8601 mang `Z` hoặc offset, hoặc epoch với **đơn vị nêu rõ** (`epochSecond` / `epochMillis`). Không tự động coi chuỗi thiếu offset là UTC.

**Lịch hẹn dân sự:** ví dụ “08:30 ngày 15/08 theo giờ Hà Nội” hoặc “09:00 mỗi thứ Hai theo giờ New York” — nên lưu ngày/giờ địa phương cùng `ZoneId`, quy tắc lặp và chính sách xử lý giờ DST. Nếu là một lịch hẹn đã xác nhận, có thể lưu thêm `Instant` thực thi đã giải quyết và offset chọn ở overlap.

### 9.2. Chuỗi thiếu offset không tự trở thành UTC

`2024-08-15T09:30:00` là chuỗi phù hợp cho `LocalDateTime.parse(...)`, nhưng **thiếu offset**. Trong khi đó `2024-08-15T09:30:00+07:00` mang offset; `2024-08-15T02:30:00Z` mang UTC và xác định instant.

Khi thiết kế request JSON, đừng đặt tên mơ hồ như `timestamp` mà không mô tả rõ định dạng, múi giờ và đơn vị. Một payload mẫu cho lịch hẹn có thể là:

~~~json
{
  "localDateTime": "2024-08-15T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

Khi xử lý, server phải diễn giải cặp dữ liệu bằng `ZoneRules` cho thời điểm cần đặt lịch rồi tạo `Instant`. Với vùng có overlap, có thể cần trường phụ để chọn offset hoặc xác nhận với người dùng.

Một payload cho sự kiện đã xác định thời điểm:

~~~json
{
  "occurredAt": "2024-08-15T02:30:00Z"
}
~~~

Chuỗi mang `Z` tự định vị trên dòng thời gian; khi hiển thị giờ địa phương hãy dùng vùng của người nhận.

### 9.3. JDBC/SQL và LocalDateTime

Các kiểu cơ sở dữ liệu có ngữ nghĩa khác nhau về múi giờ, có thể mang tên gần nhau nhưng xử lý khác nhau giữa PostgreSQL, MySQL, Oracle và các driver JDBC. Nếu cột chỉ lưu timestamp **không kèm thông tin vùng**, đừng suy luận rằng mọi giá trị đều có thể đổi sang epoch bằng offset của server.

- Xác định quy ước dữ liệu được lưu là UTC local representation, local time theo vùng nào, hay instant có offset.
- Kiểm tra schema, driver, cấu hình session timezone và mapper.
- Round-trip thử một giờ bình thường, giờ gap, giờ overlap và phần lẻ giây.
- Chuẩn hóa dữ liệu sự kiện đã xảy ra thành `Instant`/UTC thường giúp giảm nhập nhằng; lịch dân sự vẫn có thể cần giữ `ZoneId` và local-time nguyên thủy.

## 10. Công thức kiểm tra và những hiểu lầm cần tránh

Nếu một `LocalDateTime` đã biết **đúng** `ZoneOffset`, mối quan hệ về mặt ý tưởng là:

~~~text
epochSecond
    = localDateTime tính như UTC - offset.totalSeconds

Ví dụ: 2024-08-15T09:30 với offset +07:00
    = 2024-08-15T09:30Z - 7 giờ
    = 2024-08-15T02:30Z
    = 1723689000 giây tính từ epoch
~~~

Không cần tự triển khai công thức vì API `toEpochSecond(offset)` và `atOffset(offset).toInstant()` đã thực hiện an toàn trong miền hỗ trợ. Công thức ở trên dùng để **kiểm tra dấu offset** và hiểu ý nghĩa.

| Cách làm sai | Vì sao sai | Cách đúng |
|---|---|---|
| `local.toEpochSecond(ZoneOffset.UTC)` cho mọi `LocalDateTime`. | Chỉ đúng nếu giá trị thực sự được định nghĩa theo UTC. | Dùng offset hợp lệ của dữ liệu. |
| Dùng offset **hiện tại** của New York cho ngày bất kỳ. | Có DST và lịch sử thay đổi luật. | Tra `ZoneRules` theo local date/time. |
| Xem `ZoneId` giống `ZoneOffset`. | ZoneId có quy tắc vùng qua thời gian; offset chỉ là độ lệch cố định. | Lưu ZoneId cho ý định giờ dân sự theo vùng. |
| Gọi `local.atZone(zone)` và bỏ qua gap/overlap. | Có thể đổi giờ trong gap hoặc tự chọn lần đầu ở overlap. | Kiểm tra `getValidOffsets` và chính sách nghiệp vụ. |
| Nghĩ `toEpochSecond(offset)` xác thực offset của vùng. | Phương thức chỉ dùng offset được cung cấp để tính. | Dùng `ZonedDateTime.ofStrict`/`ZoneRules` nếu cần chặt chẽ. |
| Nhân epoch second với 1000 rồi coi là đủ mọi nano giây. | Phần lẻ giây bị mất. | Lấy `Instant.toEpochMilli()` khi chỉ cần ms hoặc lưu second+nano. |
| Nghĩ một `Instant` luôn có một local time không cần vùng. | Cùng instant hiện thành giờ khác ở từng vùng. | Chuyển với `instant.atZone(zone)`. |
| Lưu `LocalDateTime.now()` như thời điểm tuyệt đối mà không lưu vùng. | Mất quy tắc diễn giải; về sau không khôi phục epoch chắc chắn. | Ghi `Instant.now()` hoặc lưu vùng/offset rõ ràng. |
| Nhầm `System.nanoTime()` là epoch nano. | Giá trị có mốc không liên quan UTC. | Dùng `Instant`, `currentTimeMillis` hoặc API epoch đúng mục đích. |
| Đoán epoch trong JSON là giây hay mili giây. | Sai ngày rất lớn dù số vẫn parse được. | Nêu rõ đơn vị và kiểm tra range. |

## 11. Hướng dẫn ra quyết định nhanh

Trước khi đổi `LocalDateTime` thành epoch, trả lời lần lượt:

1. **Nguồn `LocalDateTime` này có thật sự biểu diễn ngày giờ của một sự kiện hay một lịch hẹn địa phương?** Nếu đã có `Instant`, dùng trực tiếp và tránh biến đổi qua local time không cần thiết.
2. **Có offset gốc đáng tin cậy không?** Nếu có, dùng `local.atOffset(offset).toInstant()` hoặc `local.toEpochSecond(offset)`.
3. **Chỉ biết vùng địa lý?** Dùng `ZoneId` và quy tắc tại chính ngày giờ đó, không lấy offset cố định đang hiện hành.
4. **Giờ rơi vào gap/overlap?** Chọn chính sách cụ thể: từ chối, điều chỉnh, hỏi offset, chọn lần đầu/lần sau. Nếu cần chắc chắn, kiểm tra danh sách offset hợp lệ và dùng `ofStrict`.
5. **Epoch đầu ra cần đơn vị nào?** Giây, mili giây hoặc giữ cả nano; nêu rõ trong API/schema và đảm bảo không vượt kiểu dữ liệu.

## 12. Tự kiểm tra kiến thức

**Câu 1.** `LocalDateTime.of(2024, 8, 15, 9, 30)` có epoch duy nhất không?

**Đáp án:** Không. Cần `ZoneOffset` hoặc `ZoneId` kèm quy tắc giải quyết. Với `+07:00`, epoch second là `1723689000`; với UTC, epoch khác.

**Câu 2.** Vì sao `local.toEpochSecond(ZoneOffset.ofHours(-5))` không chứng minh giá trị hợp lệ tại New York?

**Đáp án:** Phương thức chỉ dùng offset được cung cấp để tính, không đối chiếu luật vùng. Giờ thuộc gap có thể vẫn cho kết quả số học.

**Câu 3.** `2024-11-03T01:30` tại New York có mấy epoch hợp lệ?

**Đáp án:** Hai, ứng với `-04:00` và `-05:00`. Chúng cách nhau 3.600 giây.

**Câu 4.** `2024-03-10T02:30` tại New York có epoch hợp lệ theo giờ dân sự New York không?

**Đáp án:** Không có offset hợp lệ cho **local time** đó trong vùng; Java `atZone` mặc định dời tới `03:30-04:00`. Nếu người dùng thực sự yêu cầu `02:30` thì cần chính sách xử lý gap.

**Câu 5.** Nếu đã có `Instant` và muốn hiển thị giờ Việt Nam, có cần đoán offset rồi thay đổi epoch không?

**Đáp án:** Không. Epoch giữ nguyên; dùng `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` để biểu diễn cùng instant dưới ngày giờ của vùng.

**Câu 6.** Một instant có `epochSecond = -1` và `nano = 500000000` tương ứng epoch milli nào?

**Đáp án:** `-500`, tức 500 ms trước mốc Unix epoch.

## Ghi nhớ

**`LocalDateTime` không chứa UTC offset hoặc ZoneId, nên không thể tự suy ra một epoch duy nhất.** Khi biết offset đúng, dùng `toEpochSecond(offset)` hoặc `atOffset(offset).toInstant()`. Khi biết vùng, dùng `ZoneId`/`ZoneRules` để xác định offset đúng cho **ngày giờ đó**, xử lý rõ gap/overlap trước khi tạo `Instant`. Cuối cùng phân biệt chính xác **giây, mili giây và nano giây** trong lưu trữ và giao tiếp API.
