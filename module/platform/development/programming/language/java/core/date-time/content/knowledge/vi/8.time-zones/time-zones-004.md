# Tạo, kiểm tra và liệt kê mã múi giờ trong Java

## 1. Mục tiêu học tập

Khi xây dựng hệ thống đặt lịch, hiển thị giờ quốc tế hoặc lưu lịch hẹn, chương trình cần nhận biết **múi giờ** mà người dùng chọn. Java cung cấp `java.time.ZoneId` để biểu diễn định danh múi giờ và `java.time.ZoneOffset` để biểu diễn một độ lệch UTC cố định.

Sau bài này, bạn có thể:

- Tạo `ZoneId` bằng `ZoneId.of(...)`, dùng `ZoneOffset` khi cần một offset cụ thể và đọc múi giờ mặc định của hệ thống.
- Phân biệt **mã vùng có quy tắc lịch sử/DST** như `Europe/Paris` với **offset cố định** như `+07:00`.
- Kiểm tra mã múi giờ người dùng nhập, phân biệt mã sai cú pháp, mã không có trong dữ liệu và các alias không được ánh xạ.
- Liệt kê mã do Java hỗ trợ bằng `ZoneId.getAvailableZoneIds()`, lọc, sắp xếp và cung cấp danh sách cho giao diện.
- Hiểu giới hạn của việc kiểm tra mã, phiên bản dữ liệu múi giờ (tzdb) và sự thay đổi offset theo ngày.

Ví dụ sử dụng Java 17+, API `java.time` tiêu chuẩn. Khi ví dụ phụ thuộc bộ dữ liệu múi giờ cài trong JDK, bài sẽ nói rõ đầu ra có thể thay đổi theo phiên bản tzdb.

## 2. Mã múi giờ không đồng nghĩa với offset UTC

Một mã múi giờ là định danh dùng để tra **quy tắc áp dụng offset theo thời điểm**, bao gồm cả lịch sử và các lần chuyển giờ mùa hè (daylight saving time, DST) ở những vùng có áp dụng.

Ví dụ:

| Giá trị | Loại | Ý nghĩa |
| --- | --- | --- |
| `Asia/Ho_Chi_Minh` | ID vùng | Tập quy tắc múi giờ của thành phố/vùng |
| `Europe/Paris` | ID vùng | Quy tắc giờ tại Paris, bao gồm thay đổi offset theo mùa |
| `America/New_York` | ID vùng | Quy tắc giờ tại New York |
| `+07:00` | Offset cố định | Giờ địa phương sớm hơn UTC 7 giờ |
| `-05:00` | Offset cố định | Giờ địa phương chậm hơn UTC 5 giờ |
| `Z` hoặc `+00:00` | Offset 0 | Giờ UTC, cùng một độ lệch bằng 0 |
| `UTC`, `GMT`, `UT` | ID dạng tiền tố | Mã nhận diện UTC/GMT/UT theo quy tắc `ZoneId` |
| `UTC+07:00` | ID có tiền tố và offset | Dựa trên offset +07:00, không có quy tắc DST theo vùng |

Phân biệt quan trọng:

- **ZoneId vùng** có thể dẫn tới **offset khác nhau tại những thời điểm khác nhau**. Chẳng hạn Paris năm 2024 là `+01:00` vào giữa mùa đông và `+02:00` vào giữa mùa hè.
- **ZoneOffset** bản chất là độ lệch cố định. `+01:00` không tự biểu thị toàn bộ quy tắc của `Europe/Paris`.
- Hai ID có thể cho cùng offset tại một thời điểm nhưng không thể mặc nhiên thay thế nhau khi đặt lịch ở tương lai hoặc giải thích dữ liệu lịch sử.
- `LocalDateTime` chỉ chứa trường ngày/giờ địa phương; bản thân nó chưa biết ID vùng hay offset. Khi gắn `ZoneId` mới có thể giải quyết sang `ZonedDateTime` và một `Instant` cụ thể theo quy tắc múi giờ.

Mã IANA thường có dạng `Area/Location` nhưng không nên tự kết luận mọi chuỗi có dấu `/` đều là mã hợp lệ. Thư viện phải có quy tắc tương ứng trong dữ liệu múi giờ đang sử dụng.

## 3. Tạo ZoneId bằng ZoneId.of(...)

Cách thông dụng nhất là:

```java
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId newYork = ZoneId.of("America/New_York");
```

Đây là **đoạn mã minh họa** nằm trong một phương thức; `ZoneId.of(String)` trả giá trị không thay đổi sau khi tạo. Trả mã ID bằng `getId()`:

```java
System.out.println(vietnam.getId()); // Asia/Ho_Chi_Minh
System.out.println(paris.getId());   // Europe/Paris
```

Không nên đoán tên ID bằng cách thay dấu cách hoặc tên quốc gia. Chẳng hạn thành phố và tên vùng có quy ước lịch sử riêng; cần tra từ danh sách Java thực sự hỗ trợ.

`ZoneId.of(...)` cũng hiểu nhiều dạng ID khác:

```java
ZoneId sevenHours = ZoneId.of("+07:00");
ZoneId utc = ZoneId.of("UTC");
ZoneId utcWithOffset = ZoneId.of("UTC+07:00");
ZoneId gmtWithOffset = ZoneId.of("GMT+7");
ZoneId zeroOffset = ZoneId.of("Z");
```

Các ID chuẩn hóa khi gọi `getId()`:

| Đầu vào | `getId()` |
| --- | --- |
| `"+07:00"` | `+07:00` |
| `"UTC"` | `UTC` |
| `"UTC+07:00"` | `UTC+07:00` |
| `"GMT+7"` | `GMT+07:00` |
| `"Z"` | `Z` |

Dạng `GMT+7` được chuẩn hóa thành `GMT+07:00`. Mỗi tiền tố biểu diễn một kiểu ID do Java hỗ trợ; không nên tự nối chuỗi khi chưa rõ cách phân tích và chuẩn hóa offset.

### Dùng ZoneOffset nếu bài toán chỉ yêu cầu độ lệch

`ZoneOffset` kế thừa `ZoneId` và biểu diễn một offset cố định:

```java
import java.time.ZoneOffset;

ZoneOffset offset = ZoneOffset.of("+07:00");
ZoneOffset byHours = ZoneOffset.ofHours(7);
ZoneOffset utcOffset = ZoneOffset.UTC;
```

Đây là đoạn minh họa. `offset.equals(byHours)` trả `true`. Các offset phải thuộc phạm vi Java cho phép (từ -18:00 đến +18:00, với ràng buộc thành phần phút/giây hợp lệ).

`ZoneId.of("+07:00")` trả về một `ZoneOffset`, còn `ZoneId.of("UTC+07:00")` giữ dạng ID có tiền tố. Có thể gọi `normalized()` để lấy `ZoneOffset` khi quy tắc của ID thực chất là offset cố định:

```java
ZoneId namedFixed = ZoneId.of("UTC+07:00");
ZoneId normalized = namedFixed.normalized();
System.out.println(normalized.getId()); // +07:00
```

Đây là đoạn minh họa, cần `import java.time.ZoneId;`. Với vùng có quy tắc thay đổi offset, `normalized()` không biến nó thành một offset đại diện cho mọi thời điểm.

## 4. Lấy múi giờ mặc định của máy đang chạy

`ZoneId.systemDefault()` trả về múi giờ mặc định của hệ thống/JVM:

```java
ZoneId defaultZone = ZoneId.systemDefault();
System.out.println(defaultZone.getId());
```

Đây là đoạn minh họa, cần `import java.time.ZoneId;`. Đầu ra **phụ thuộc cấu hình môi trường**; có thể là `Asia/Ho_Chi_Minh`, `UTC` hoặc một mã khác. Không viết test cố định rằng kết quả luôn thuộc một quốc gia.

Múi giờ mặc định có thể chịu tác động bởi cấu hình môi trường chạy, hệ điều hành và thiết lập JVM. Trong container/cloud, server có thể chạy với UTC ngay khi người dùng ở Việt Nam.

**Nguyên tắc trong ứng dụng:** Nếu chức năng thực sự cần “giờ của người dùng”, hãy dùng `ZoneId` được chọn/lưu rõ ràng theo người dùng; đừng âm thầm lấy `systemDefault()` của server. Nếu chức năng cần một mốc thống nhất để lưu sự kiện, ưu tiên `Instant`, đồng thời lưu mã vùng khi cần tái dựng ý nghĩa lịch hẹn theo giờ địa phương.

## 5. Kiểm tra mã múi giờ bằng cách phân tích ID

API không có phương thức `ZoneId.isValid("...")`. Cách kiểm tra trực tiếp là thử tạo `ZoneId` và xử lý lỗi:

```java
import java.time.DateTimeException;
import java.time.ZoneId;

public class ZoneIdCheckDemo {
    public static void main(String[] args) {
        check("Asia/Ho_Chi_Minh");
        check("Europe/Paris");
        check("+07:00");
        check("CST");
        check("Mars/Olympus");
        check("UTC+25:00");
    }

    private static void check(String input) {
        try {
            ZoneId zone = ZoneId.of(input);
            System.out.println(input + " -> " + zone.getId());
        } catch (DateTimeException ex) {
            System.out.println(input + " -> INVALID");
        }
    }
}
```

Lưu file `ZoneIdCheckDemo.java`. Chạy:

```bash
javac ZoneIdCheckDemo.java
java ZoneIdCheckDemo
```

Kết quả với JDK có dữ liệu vùng thông dụng:

```text
Asia/Ho_Chi_Minh -> Asia/Ho_Chi_Minh
Europe/Paris -> Europe/Paris
+07:00 -> +07:00
CST -> INVALID
Mars/Olympus -> INVALID
UTC+25:00 -> INVALID
```

Giải thích:

- `Asia/Ho_Chi_Minh` và `Europe/Paris` là các ID vùng hợp lệ trong dữ liệu JDK phổ biến.
- `+07:00` là một offset hợp lệ dù không phải mã vùng `Area/Location`.
- `CST` là viết tắt có thể mang nhiều nghĩa, nên `ZoneId.of("CST")` mặc định không được tự suy ra múi giờ.
- `Mars/Olympus` không có quy tắc trong dữ liệu múi giờ chuẩn.
- `UTC+25:00` có offset ngoài phạm vi cho phép.

### Các ngoại lệ cần biết

`ZoneId.of(...)` có thể ném `DateTimeException` khi chuỗi sai định dạng hoặc múi giờ không được hỗ trợ. Một mã vùng trông đúng cấu trúc nhưng không có trong dữ liệu thường gây `java.time.zone.ZoneRulesException`, vốn là lớp con của `DateTimeException`. `null` gây `NullPointerException`.

Đừng chỉ bắt `ZoneRulesException`, vì lỗi cú pháp/offset có thể là `DateTimeException` khác. Khi kiểm tra một tham số string đã được kiểm tra khác null, bắt `DateTimeException` thường bao phủ các lỗi múi giờ người dùng nhập.

Trong ứng dụng REST/UI, việc bắt lỗi nên trả một thông báo như “mã múi giờ không hợp lệ hoặc không được server hỗ trợ”, chứ không tự động đổi thành UTC và tiếp tục xử lý lịch hẹn trong im lặng.

## 6. Kiểm tra “có trong danh sách vùng” khác với “ZoneId.of nhận được”

`ZoneId.getAvailableZoneIds()` trả về tập ID vùng mà các nhà cung cấp quy tắc múi giờ của môi trường Java hiện tại biết đến. Nhưng `ZoneId.of(...)` còn xử lý **offset cố định** và **ID có tiền tố** như `UTC+07:00`.

Do đó hai câu hỏi **khác nhau**:

1. **ID này có thể được Java phân tích và sử dụng?** → thử `ZoneId.of(input)` và xử lý ngoại lệ.
2. **ID này có nằm trong danh sách vùng được cung cấp?** → `ZoneId.getAvailableZoneIds().contains(input)`.

Ví dụ `ZoneId.of("+07:00")` thành công, trong khi chuỗi này không phải một mã vùng nằm trong tập do `getAvailableZoneIds()` cung cấp. Nếu giao diện chỉ cho chọn một ID vùng để biểu diễn quy tắc lịch theo địa phương, nên dùng danh sách vùng. Nếu API chủ ý nhận **cả offset cố định**, kiểm tra chỉ bằng tập vùng là quá hạn chế.

Một kiểm tra “cú pháp hợp lệ” bằng regex tự viết cũng chưa đủ: regex không xác thực vùng có tồn tại trong tzdb hoặc liệu hệ thống đã có quy tắc của vùng đó hay chưa.

## 7. Liệt kê các mã múi giờ có sẵn

Phương thức:

```java
Set<String> availableIds = ZoneId.getAvailableZoneIds();
```

Đây là đoạn minh họa, cần `import java.time.ZoneId;` và `import java.util.Set;`.

Đặc điểm:

- Trả về một `Set<String>` chứa các mã vùng có sẵn từ provider múi giờ.
- **Không có thứ tự duyệt được bảo đảm**; không in trực tiếp set và chụp nguyên đầu ra làm dữ liệu cố định.
- Số lượng/tập ID có thể khác nhau tùy phiên bản JDK, bộ dữ liệu tzdb và provider.
- Không mặc nhiên chứa mọi alias, mã viết tắt, ID offset hay ID tiền tố mà `ZoneId.of(...)` có thể nhận.
- Tập được trả về có thể được lọc và chuyển sang danh sách để xây picker cho người dùng.

Muốn hiển thị ổn định theo tên, hãy **sắp xếp**:

```java
List<String> sortedIds = ZoneId.getAvailableZoneIds()
        .stream()
        .sorted()
        .toList();
```

Đây là đoạn minh họa với `import java.time.ZoneId;` và `import java.util.List;`. `Stream.toList()` có trong Java 16+, nên dùng được từ Java 17; danh sách nhận được là unmodifiable.

### Lọc theo khu vực

Khi chỉ muốn mã bắt đầu bằng `Asia/`:

```java
List<String> asiaIds = ZoneId.getAvailableZoneIds()
        .stream()
        .filter(id -> id.startsWith("Asia/"))
        .sorted()
        .toList();
```

Đây là đoạn minh họa với import tương ứng. Mã có tiền tố `Asia/` không có nghĩa nó nhất thiết thuộc một quốc gia cụ thể; đây chỉ là quy ước tổ chức ID.

Có thể tìm chuỗi con theo từ khóa:

```java
String keyword = "Ho_Chi_Minh";
List<String> matches = ZoneId.getAvailableZoneIds()
        .stream()
        .filter(id -> id.contains(keyword))
        .sorted()
        .toList();
```

Đây là đoạn minh họa. Cách tìm theo chuỗi hữu ích cho chức năng tra cứu đơn giản, nhưng tên ID là **mã kỹ thuật**, không phải tên hiển thị tiếng Việt đầy đủ. Trong UI thực tế, nên hỗ trợ tìm theo tên thành phố, tên vùng và nhãn đã bản địa hóa phù hợp.

## 8. Chương trình hoàn chỉnh: tạo, lọc và liệt kê có thứ tự

Lưu file **`ZoneIdCatalogDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.ZoneId;
import java.util.List;
import java.util.Set;

public class ZoneIdCatalogDemo {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneId fixed = ZoneId.of("+07:00");

        System.out.println("vietnam = " + vietnam.getId());
        System.out.println("paris = " + paris.getId());
        System.out.println("fixed = " + fixed.getId());

        Set<String> all = ZoneId.getAvailableZoneIds();
        System.out.println("hasVietnam = "
                + all.contains("Asia/Ho_Chi_Minh"));

        List<String> selected = all.stream()
                .filter(id -> id.equals("Asia/Ho_Chi_Minh")
                        || id.equals("Europe/Paris"))
                .sorted()
                .toList();
        System.out.println("selected = " + selected);

        for (String candidate : List.of(
                "Asia/Ho_Chi_Minh", "+07:00", "Mars/Olympus")) {
            try {
                System.out.println("valid = "
                        + ZoneId.of(candidate).getId());
            } catch (DateTimeException ex) {
                System.out.println("invalid = " + candidate);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ZoneIdCatalogDemo.java
java ZoneIdCatalogDemo
```

Kết quả xác định trên JDK có bộ ID vùng chuẩn bao gồm hai vùng trong ví dụ:

```text
vietnam = Asia/Ho_Chi_Minh
paris = Europe/Paris
fixed = +07:00
hasVietnam = true
selected = [Asia/Ho_Chi_Minh, Europe/Paris]
valid = Asia/Ho_Chi_Minh
valid = +07:00
invalid = Mars/Olympus
```

Điểm học được:

1. Tạo ID vùng và offset bằng cùng API `ZoneId.of(...)`, nhưng ngữ nghĩa khác nhau.
2. Kiểm tra `contains(...)` áp dụng với danh sách **ID vùng**.
3. Khi in danh sách, gọi `sorted()` để không phụ thuộc thứ tự của `Set`.
4. Dùng `try/catch` khi phân tích chuỗi do người dùng cung cấp.
5. Không kiểm tra số lượng chính xác của `getAvailableZoneIds()` trong một test chạy trên nhiều phiên bản tzdb.

## 9. Mã viết tắt và bảng ZoneId.SHORT_IDS

Các viết tắt như `CST`, `IST`, `EST`, `PST` đôi khi mơ hồ hoặc mang ý nghĩa lịch sử khác nhau theo địa điểm. Ví dụ “CST” có thể được hiểu theo nhiều vùng trên thế giới.

Java cung cấp map `ZoneId.SHORT_IDS` để hỗ trợ một số chuỗi viết tắt cũ khi **chủ động yêu cầu**:

```java
ZoneId legacy = ZoneId.of("PST", ZoneId.SHORT_IDS);
System.out.println(legacy.getId());
// America/Los_Angeles
```

Đây là đoạn minh họa, cần `import java.time.ZoneId;`. `ZoneId.of("PST")` không tự dùng bảng `SHORT_IDS`. Bảng này là phép ánh xạ do Java định nghĩa, không phải hệ thống giải nghĩa mọi mã viết tắt ở mọi quốc gia và thời điểm.

**Khuyến nghị:** Khi thiết kế dữ liệu mới, nhận/lưu ID vùng đầy đủ như `America/Los_Angeles` hoặc offset được quy định rõ. Chỉ sử dụng `SHORT_IDS` cho tương thích dữ liệu cũ mà bạn biết rõ ý nghĩa và muốn ánh xạ cụ thể. Đừng dựa vào viết tắt để tự đoán khu vực của người dùng.

## 10. Kiểm tra quy tắc offset của một ID

Sau khi có `ZoneId`, dùng `zone.getRules()` để xem quy tắc múi giờ qua `java.time.zone.ZoneRules`. Offset phụ thuộc **thời điểm**; dùng `Instant` khi đặt câu hỏi “offset là bao nhiêu vào ngày đó?”.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId paris = ZoneId.of("Europe/Paris");
ZoneOffset winter = paris.getRules().getOffset(
        Instant.parse("2024-01-15T12:00:00Z"));
ZoneOffset summer = paris.getRules().getOffset(
        Instant.parse("2024-07-15T12:00:00Z"));

System.out.println(winter); // +01:00
System.out.println(summer); // +02:00
```

Đây là đoạn minh họa trong một phương thức; hai kết quả dựa trên dữ liệu tzdb có quy tắc lịch sử của Paris năm 2024. Việc đổi offset chứng minh vì sao **một ZoneId vùng không thể thay bằng một offset cố định** cho mọi ngày.

Một số thao tác kiểm tra quy tắc:

- `zone.getRules().isFixedOffset()`: quy tắc có offset cố định (không thay đổi theo thời điểm) hay không.
- `zone.getRules().getOffset(instant)`: offset áp dụng tại một `Instant` cụ thể.
- `zone.getRules().isDaylightSavings(instant)`: thời điểm có thuộc giai đoạn được quy tắc xem là DST hay không.
- `zone.getRules().getValidOffsets(localDateTime)`: danh sách offset hợp lệ cho một nhãn `LocalDateTime`; có thể rỗng trong DST gap hoặc chứa hai phần tử trong overlap.

Không nên lấy offset tại `Instant.now()` rồi coi là offset cố định cho lịch họp vào năm sau. Chính sách DST của vùng có thể làm kết quả khác, và luật múi giờ còn có thể được chính phủ thay đổi trong tương lai.

### Ví dụ hoàn chỉnh: so sánh vùng và offset

Lưu file **`ZoneRulesDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ZoneRulesDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");
        ZoneOffset fixed = ZoneOffset.ofHours(1);

        Instant winter = Instant.parse("2024-01-15T12:00:00Z");
        Instant summer = Instant.parse("2024-07-15T12:00:00Z");

        System.out.println("Paris winter = "
                + paris.getRules().getOffset(winter));
        System.out.println("Paris summer = "
                + paris.getRules().getOffset(summer));
        System.out.println("Fixed winter = "
                + fixed.getRules().getOffset(winter));
        System.out.println("Fixed summer = "
                + fixed.getRules().getOffset(summer));
        System.out.println("Fixed isFixedOffset = "
                + fixed.getRules().isFixedOffset());
    }
}
```

Chạy:

```bash
javac ZoneRulesDemo.java
java ZoneRulesDemo
```

Kết quả với quy tắc Paris năm 2024:

```text
Paris winter = +01:00
Paris summer = +02:00
Fixed winter = +01:00
Fixed summer = +01:00
Fixed isFixedOffset = true
```

**Diễn giải:** Cả hai có thể cùng offset vào tháng 1, nhưng vào tháng 7 Paris đổi sang +02:00, còn offset cố định vẫn +01:00. Vì vậy **kiểm tra một ID có tồn tại** là bước khác với **xác nhận ID đáp ứng ý nghĩa nghiệp vụ cần lưu**.

## 11. Cách dùng ZoneId trong lịch hẹn và chuyển đổi ngày giờ

Nếu một người chọn ngày giờ địa phương `2024-07-15 09:00` và vùng `Europe/Paris`, bạn có thể kết hợp:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.Instant;

LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 0);
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();

System.out.println(zoned);
// 2024-07-15T09:00+02:00[Europe/Paris]

System.out.println(instant);
// 2024-07-15T07:00:00Z
```

Đây là đoạn minh họa trong một phương thức. `local.atZone(zone)` áp dụng quy tắc offset của vùng tại ngày giờ được chọn. Lịch hẹn có thể cần giữ cả **local date-time** (giờ mà người dùng chọn), **ID vùng**, và/hoặc **Instant** (mốc tuyệt đối) tùy hợp đồng lưu trữ và chính sách cập nhật quy tắc tương lai.

**DST gap/overlap:** Một số giá trị giờ địa phương có thể không tồn tại hoặc có hai offset hợp lệ. Cách mặc định của `atZone(...)` xử lý theo quy tắc Java; với nghiệp vụ tài chính/đặt chỗ có yêu cầu đặc biệt, cần xác định và kiểm tra rõ trường hợp đó thay vì tự giả định một nhãn ngày giờ luôn ánh xạ duy nhất.

## 12. Xây danh sách chọn múi giờ cho người dùng

Một picker tối thiểu có thể dựa trên tập ID vùng của Java:

```java
import java.time.ZoneId;
import java.util.List;

public class ZonePickerDemo {
    public static void main(String[] args) {
        List<String> ids = ZoneId.getAvailableZoneIds()
                .stream()
                .sorted()
                .toList();

        List<String> selected = ids.stream()
                .filter(id -> id.startsWith("Asia/"))
                .filter(id -> id.contains("Ho_Chi_Minh")
                        || id.contains("Tokyo"))
                .toList();

        System.out.println("selected = " + selected);
    }
}
```

Lưu file `ZonePickerDemo.java`. Biên dịch và chạy:

```bash
javac ZonePickerDemo.java
java ZonePickerDemo
```

Kết quả trên JDK có hai ID vùng này:

```text
selected = [Asia/Ho_Chi_Minh, Asia/Tokyo]
```

Đây chỉ là ví dụ **lọc hai mã để minh họa thao tác**. Picker thực tế nên tìm kiếm trên danh sách đầy đủ; có thể dùng nhãn hiển thị dễ hiểu như “Hồ Chí Minh” hoặc “Tokyo”, nhưng **giá trị gửi về API nên là ID có quy tắc rõ ràng**, không phải nhãn giao diện.

Có thể dùng:

```java
String label = ZoneId.of("Europe/Paris").getDisplayName(
        java.time.format.TextStyle.FULL,
        java.util.Locale.forLanguageTag("vi-VN"));
```

Đây là đoạn minh họa trong phương thức. Kết quả nhãn bản địa hóa có thể phụ thuộc dữ liệu locale của JDK; không nên viết test assert một chuỗi hiển thị cố định trên mọi môi trường. Đừng dùng nhãn đã dịch làm định danh lưu trữ.

### Quy trình kiểm tra một giá trị gửi từ picker

1. Nhận chuỗi mã với giới hạn độ dài hợp lý và loại bỏ trường hợp null/trống theo hợp đồng.
2. Nếu chỉ cho chọn **ID vùng**, đối chiếu với danh sách vùng hợp lệ mà server công bố.
3. Nếu cho phép cả **offset**, dùng `ZoneId.of(...)` để xác thực theo cú pháp/ngữ nghĩa Java.
4. Áp dụng chính sách nghiệp vụ: có cho chọn vùng ngoài danh sách hoạt động, vùng không hỗ trợ DST, hoặc chỉ những khu vực cần phục vụ?
5. Lưu **mã chuẩn hóa** từ `getId()` hoặc quy tắc ánh xạ được định nghĩa rõ; không tự suy đoán từ ký tự viết tắt.

Bộ ID trên frontend có thể khác backend nếu hai môi trường cập nhật tzdb khác nhau. Backend vẫn phải xác thực độc lập thay vì tin rằng mọi giá trị gửi lên từ UI đã hợp lệ.

## 13. Tại sao danh sách mã có thể khác nhau giữa các JDK?

Các ID vùng và chuyển đổi offset được tra từ **timezone database (tzdb)** và các provider mà môi trường Java sử dụng. Phiên bản dữ liệu múi giờ được cập nhật khi có thay đổi pháp luật/lịch chuyển giờ.

Hệ quả:

- Mã mới có thể xuất hiện sau khi cập nhật JDK/tzdb.
- Một số alias/tên vùng có thể khác hoặc được xử lý theo quy tắc tương thích.
- Cùng một ID vùng có thể có **quy tắc tương lai được cập nhật** khi nhà nước thay đổi DST; mã vẫn hợp lệ nhưng offset của một ngày tương lai có thể khác trước.
- Không hardcode số lượng phần tử của `ZoneId.getAvailableZoneIds()` như một hằng số toàn hệ thống.
- Không dựa vào thứ tự lặp trực tiếp của `Set`; sắp xếp rõ ràng khi hiển thị hoặc xuất dữ liệu.

Nếu cần chẩn đoán phiên bản quy tắc, Java cung cấp API `java.time.zone.ZoneRulesProvider.getVersions(zoneId)` cho ID vùng phù hợp. Nó trả về mapping phiên bản → `ZoneRules`; tên phiên bản cụ thể tùy provider nên tránh giả định một số hiệu cố định trong tài liệu hoặc test.

Với hệ thống liên quan lịch hẹn tương lai, cần chiến lược cập nhật JDK/tzdb và kiểm thử với các vùng có quy tắc DST, thay vì “chốt” một offset từ thời điểm tạo dữ liệu.

## 14. Những trường hợp dễ nhầm

### Không dùng viết tắt làm định danh chính

`CST` hoặc `IST` không mang một nghĩa duy nhất toàn cầu. Hãy yêu cầu một ID vùng rõ ràng hoặc một offset nếu nghiệp vụ thực sự chỉ cần offset. `ZoneId.SHORT_IDS` là cầu nối cho dữ liệu cũ, không phải cách tự đoán mọi viết tắt.

### Coi +07:00 tương đương toàn bộ Asia/Ho_Chi_Minh

Hai giá trị có thể cùng offset hiện tại, nhưng mã vùng mang quy tắc lịch sử và có thể được cập nhật trong tương lai. Nếu cần biểu diễn lịch địa phương, giữ ID vùng.

### Tưởng getAvailableZoneIds() liệt kê mọi ZoneId.of(...) hợp lệ

Tập ID vùng không phải toàn bộ không gian các offset. `ZoneId.of("+07:00")` được Java chấp nhận dù đó không phải tên vùng trong tập returned IDs.

### Dùng offset của “bây giờ” cho một ngày khác

`zone.getRules().getOffset(Instant.now())` chỉ phản ánh offset tại thời điểm đang xem. Lịch họp vào một ngày khác cần tra offset tại ngày đó, với quy tắc DST/zone thích hợp.

### Quên vùng mặc định của server khác vùng người dùng

Dùng `ZoneId.systemDefault()` tùy ý khiến cùng ứng dụng trả kết quả khác giữa laptop, container và production. Chỉ dùng hệ thống mặc định khi đó thực sự là mục đích. Trong API nghiệp vụ, truyền `ZoneId` rõ ràng.

### Dùng regex thay cho xác thực quy tắc

Một chuỗi có dạng `Region/City` không được chứng minh có tồn tại. Hãy dựa vào provider thực tế bằng `ZoneId.of(...)`, rồi kiểm tra allowlist của ứng dụng nếu cần.

### Quên các dạng tên GMT nghịch dấu

Một số ID lịch sử thuộc họ `Etc/GMT±N` tuân theo quy ước dấu POSIX, có thể **ngược với cách hiểu offset ISO-8601**. Chẳng hạn `Etc/GMT+7` tương ứng offset `-07:00` trong tzdb thông dụng. Đừng xây offset bằng cách tự nối `Etc/GMT` và số giờ; nếu chỉ cần offset, dùng `ZoneOffset.of("+07:00")` rõ ràng hơn.

## 15. Bài tập thực hành

**Câu 1.** Khi nào dùng `ZoneId.of("Europe/Paris")`, khi nào dùng `ZoneOffset.of("+01:00")`?

**Đáp án:** Dùng vùng Paris khi cần quy tắc offset theo ngày/lịch sử và DST. Dùng offset +01:00 khi hợp đồng yêu cầu độ lệch cố định 1 giờ, không phụ thuộc quy tắc vùng.

**Câu 2.** `ZoneId.getAvailableZoneIds().contains("+07:00")` có phải cách xác nhận mọi chuỗi dùng được với `ZoneId.of(...)`?

**Đáp án:** Không. `+07:00` là offset hợp lệ; danh sách available zone IDs chủ yếu phục vụ các ID vùng. Thử parse khi muốn hỗ trợ cả offset.

**Câu 3.** Tại sao không nên in `ZoneId.getAvailableZoneIds()` rồi kỳ vọng thứ tự cố định?

**Đáp án:** Kết quả là `Set` không có thứ tự lặp được bảo đảm. Dùng `stream().sorted().toList()` khi cần thứ tự ổn định.

**Câu 4.** Chuỗi `CST` có phải mã vùng duy nhất không?

**Đáp án:** Không. Đây là viết tắt mơ hồ; `ZoneId.of("CST")` không tự dùng ánh xạ `SHORT_IDS`. Chọn mã vùng đầy đủ.

**Câu 5.** Paris có thể là `+01:00` vào mùa đông và `+02:00` vào mùa hè. Cần gọi API nào để hỏi offset tại một instant?

**Đáp án:** `ZoneId.of("Europe/Paris").getRules().getOffset(instant)` với một `Instant` rõ ràng.

**Câu 6.** Một người dùng ở Việt Nam chọn “09:00 ngày 15/7/2024 tại Paris”. Lưu chuỗi `"2024-07-15T09:00"` có đủ để biết instant không?

**Đáp án:** Chưa. Cần múi giờ/offset phù hợp, ví dụ ID vùng `Europe/Paris`; khi đó `09:00` ngày ấy ứng với `07:00Z` theo quy tắc Paris năm 2024.

**Câu 7.** API nhận ID `Mars/Olympus` nên làm gì?

**Đáp án:** Bắt `DateTimeException` khi thử `ZoneId.of(...)` và trả thông báo mã không hợp lệ/không được hỗ trợ. Không tự thay thành múi giờ khác làm sai lịch người dùng.

## 16. Checklist khi triển khai

- Dùng `ZoneId.of(id)` để phân tích mã vùng và các ID hợp lệ khác; bắt lỗi đầu vào.
- Dùng `ZoneOffset.of(...)` khi thực sự muốn **độ lệch UTC cố định**.
- Dùng `ZoneId.getAvailableZoneIds()` để tạo danh sách **vùng**; sắp xếp và lọc trước khi đưa ra giao diện.
- Luôn phân biệt **mã định danh vùng**, **offset tại một instant**, và **nhãn ngày-giờ địa phương**.
- Tránh rút gọn mã thành viết tắt; kiểm tra dữ liệu DST/tzdb khi lập lịch vào ngày khác.
- Cập nhật dữ liệu múi giờ khi cần, không hardcode số lượng ID hay offset của một vùng cho mọi thời điểm.
- Khi nhận giá trị từ UI/API, kiểm tra phù hợp chính sách ứng dụng và cung cấp thông báo lỗi rõ ràng.

**Ghi nhớ:** Mã múi giờ vùng như `Europe/Paris` biểu diễn **quy tắc thời gian của một vùng**, còn `+07:00` chỉ là **độ lệch cố định**. Tạo và xác thực qua `ZoneId.of(...)`; liệt kê mã vùng bằng `ZoneId.getAvailableZoneIds()`; luôn tra offset theo thời điểm khi ngày giờ cụ thể quan trọng.