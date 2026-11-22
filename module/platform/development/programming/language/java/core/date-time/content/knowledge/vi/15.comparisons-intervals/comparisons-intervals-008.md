# Biểu diễn cả ngày bằng đầu ngày tới đầu ngày tiếp theo

Khi cần lọc hoặc xử lý toàn bộ một ngày lịch, cách an toàn là biểu diễn ngày đó bằng một khoảng thời gian **nửa mở**: từ đầu ngày được lấy, bao gồm đầu mốc, đến đầu ngày kế tiếp, không bao gồm mốc kết thúc. Với Java, hãy dùng `LocalDate` và `ZoneId` để tìm hai ranh giới rồi chuyển chúng thành `Instant` nếu đang truy vấn các timestamp.

Khoảng được biểu diễn bằng:

```text
[startOfDay, startOfNextDay)
```

Tương ứng với điều kiện truy vấn:

```sql
created_at >= :startInclusive
AND created_at <  :endExclusive
```

Cách này không cần tự tạo mốc `23:59:59.999`, không phụ thuộc độ chính xác timestamp là giây, mili giây hay nano giây, đồng thời xử lý đúng ngày có 23 hoặc 25 giờ khi vùng có quy tắc đổi giờ theo mùa (DST).

## 1. Định nghĩa khoảng nửa mở

Một khoảng nửa mở `[start, end)` có hai quy tắc:

- **Bao gồm start:** giá trị đúng bằng `start` thuộc khoảng.
- **Loại trừ end:** giá trị đúng bằng `end` không thuộc khoảng.

Với ngày lịch `2026-05-10`, ta định nghĩa:

```text
[start of 2026-05-10, start of 2026-05-11)
```

Một sự kiện ngay đầu ngày 10/05 được tính; một sự kiện đúng vào đầu ngày 11/05 thuộc ngày kế tiếp. Hai ngày liên tiếp tạo hai khoảng không trùng nhau nhưng nối sát nhau:

```text
Ngày D:     [start(D),     start(D + 1))
Ngày D + 1: [start(D + 1), start(D + 2))
```

Mốc `start(D + 1)` chỉ là điểm kết thúc của ngày thứ nhất và điểm bắt đầu của ngày thứ hai. Không cần cộng hoặc trừ một mili giây để tránh trùng bản ghi.

## 2. Vì sao không dùng 23:59:59.999?

Cách làm như `timestamp <= 23:59:59.999` có nhiều rủi ro:

1. **Độ chính xác không cố định:** database có thể lưu micro giây hoặc nano giây; một sự kiện sau mili giây .999 nhưng vẫn trong ngày có thể bị bỏ sót.
2. **Khó dùng cho nhiều ngày liên tiếp:** phải tính mốc cuối ngày theo độ chính xác cụ thể của từng hệ thống.
3. **Giả định mọi ngày dài 24 giờ:** tại vùng có DST, ngày địa phương có thể dài 23 hoặc 25 giờ thực tế.
4. **Khó kết hợp các khoảng:** các khoảng nửa mở dễ ghép, phân trang và chia nhỏ mà không lặp hoặc bỏ qua ranh giới.

Hãy dùng `>= startInclusive` và `< endExclusive` thay vì `BETWEEN start AND 23:59:59.999`. Trong SQL, `BETWEEN` thường bao gồm cả hai đầu, nên cần thận trọng khi dùng cho ranh giới ngày.

## 3. Tạo ranh giới ngày bằng Java

`LocalDate` biểu diễn ngày lịch mà không có giờ hoặc múi giờ. `ZoneId` cung cấp quy tắc vùng. Dùng `LocalDate.atStartOfDay(zone)` để tìm thời điểm bắt đầu ngày hợp lệ trong vùng đó; sau đó chuyển thành `Instant`:

```java
LocalDate date = LocalDate.of(2026, 5, 10);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive = date.atStartOfDay(zone).toInstant();
Instant endExclusive = date.plusDays(1).atStartOfDay(zone).toInstant();
```

Đây là đoạn minh họa cần các import từ `java.time`. Quan trọng là phải cộng **một ngày lịch** bằng `date.plusDays(1)`, rồi tính lại đầu ngày trong vùng; không lấy `startInclusive.plus(Duration.ofHours(24))` làm ranh giới ngày kế tiếp.

`atStartOfDay(zone)` trả về thời điểm bắt đầu ngày hợp lệ sớm nhất theo các quy tắc của vùng. Ở phần lớn các vùng, thời gian đó là 00:00. Tuy nhiên, lịch sử timezone có thể có chuyển đổi ngay nửa đêm khiến thời điểm bắt đầu thực tế khác 00:00; API xử lý theo quy tắc vùng thay vì giả định cố định.

## 4. Chương trình hoàn chỉnh: tính khoảng cho một ngày

Tạo tệp **`LocalDayWindowDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class LocalDayWindowDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate date = LocalDate.of(2026, 5, 10);

        Instant startInclusive = date.atStartOfDay(zone).toInstant();
        Instant endExclusive = date.plusDays(1)
                .atStartOfDay(zone)
                .toInstant();

        System.out.println("Zone: " + zone);
        System.out.println("Start inclusive: " + startInclusive);
        System.out.println("End exclusive: " + endExclusive);
        System.out.println("Duration hours: "
                + java.time.Duration.between(startInclusive, endExclusive).toHours());
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac LocalDayWindowDemo.java
java LocalDayWindowDemo
```

Kết quả:

```text
Zone: Asia/Ho_Chi_Minh
Start inclusive: 2026-05-09T17:00:00Z
End exclusive: 2026-05-10T17:00:00Z
Duration hours: 24
```

Việt Nam dùng UTC+07:00 ở mốc ví dụ này. Đầu ngày 10/05 tại Việt Nam tương đương 17:00 UTC ngày 09/05; đầu ngày 11/05 tương đương 17:00 UTC ngày 10/05. Ranh giới được tính từ ngày và vùng, không phải từ chuỗi giờ cuối ngày.

## 5. Dùng khoảng nửa mở trong truy vấn dữ liệu

Khi lưu timestamp dưới dạng thời điểm, tính hai ranh giới theo vùng nghiệp vụ rồi dùng điều kiện nửa mở. Ví dụ với Spring Data hoặc JDBC, có thể truyền hai biến `Instant` vào truy vấn:

```sql
SELECT id, created_at, amount
FROM orders
WHERE created_at >= :startInclusive
  AND created_at < :endExclusive
ORDER BY created_at, id
```

`startInclusive` và `endExclusive` được tính bằng Java như phần trước. Tên tham số cần được bind an toàn qua API database; không ghép chuỗi input vào SQL.

Lợi ích của khoảng nửa mở:

- **Không trùng ngày:** bản ghi đúng tại ranh giới ngày mới không thuộc ngày cũ.
- **Không bỏ sót timestamp hợp lệ:** mọi giá trị nhỏ hơn ranh giới kế tiếp được bao phủ.
- **Dễ phân trang theo thời gian:** trang sau có thể bắt đầu đúng tại `endExclusive` của trang trước.
- **Dùng được với mọi độ chính xác:** không phải đoán timestamp cuối cùng có thể biểu diễn trong database.

Nếu lọc dựa trên một cột kiểu `DATE` lưu riêng ngày lịch thì truy vấn theo ngày trực tiếp thường phù hợp hơn. Khoảng `Instant` nửa mở đặc biệt hữu ích khi cột chứa thời điểm thực tế, chẳng hạn `created_at`.

## 6. DST: một ngày địa phương không luôn dài 24 giờ

Tại vùng có Daylight Saving Time, đồng hồ có thể nhảy tiến hoặc lùi. Một ngày địa phương có thể dài 23 hoặc 25 giờ thực tế. Vì thế, ranh giới ngày phải được tính từ `LocalDate` và `ZoneId`; đừng định nghĩa đầu ngày kế tiếp bằng cách cộng cố định 24 giờ thực tế.

Chương trình **`DstDayWindowDemo.java`** minh họa ngày đổi DST tại New York trong năm 2026:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class DstDayWindowDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        showDay(zone, LocalDate.of(2026, 3, 8));
        showDay(zone, LocalDate.of(2026, 11, 1));
    }

    private static void showDay(ZoneId zone, LocalDate date) {
        Instant start = date.atStartOfDay(zone).toInstant();
        Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
        long hours = Duration.between(start, end).toHours();

        System.out.println(date + ": " + start + " -> " + end
                + ", hours=" + hours);
    }
}
```

Chạy:

```bash
javac DstDayWindowDemo.java
java DstDayWindowDemo
```

Kết quả theo quy tắc timezone của New York năm 2026:

```text
2026-03-08: 2026-03-08T05:00:00Z -> 2026-03-09T04:00:00Z, hours=23
2026-11-01: 2026-11-01T04:00:00Z -> 2026-11-02T05:00:00Z, hours=25
```

Ngày 08/03, New York chuyển đồng hồ từ giờ mùa đông sang giờ mùa hè; một giờ địa phương không tồn tại và ngày chỉ dài 23 giờ. Ngày 01/11, đồng hồ lùi lại và giờ địa phương 01:00–01:59 xuất hiện hai lần; ngày dài 25 giờ.

Dù thời lượng của hai ngày khác 24 giờ, cả hai khoảng đều đúng cho **toàn bộ ngày lịch địa phương** khi ranh giới được tính theo `atStartOfDay(zone)`. Nếu dùng `start.plus(Duration.ofHours(24))`, khoảng có thể kết thúc sai giữa ngày lịch.

## 7. Chọn đúng vùng: người dùng hay nghiệp vụ?

Cần quyết định ngày được hiểu theo vùng nào trước khi xây dựng khoảng:

- **Lịch cá nhân:** dùng múi giờ người dùng đã chọn.
- **Báo cáo hoặc chốt sổ chi nhánh:** dùng `ZoneId` được cấu hình cho chi nhánh/thị trường.
- **Ngày kỹ thuật UTC:** dùng vùng UTC khi mục tiêu thực sự là ngày UTC.
- **Ngày lưu trong cột `DATE`:** giữ giá trị `LocalDate`, không biến ngày thuần túy thành timestamp nếu domain không cần thời điểm.

Ví dụ một giao dịch được tạo tại `2026-05-10T01:00:00Z` có thể vẫn thuộc ngày 09/05 ở California nhưng là ngày 10/05 ở Việt Nam. Nếu báo cáo chốt theo California, dùng vùng California để tính `startInclusive` và `endExclusive`; vùng thiết bị của người chạy báo cáo không nên làm thay đổi kết quả nghiệp vụ.

## 8. Cộng ngày lịch và cộng thời lượng thực tế khác nhau

Hai biểu thức sau có nghĩa khác nhau:

```java
LocalDate tomorrow = date.plusDays(1);
Instant after24Hours = start.plus(java.time.Duration.ofHours(24));
```

- `date.plusDays(1)` chuyển sang ngày lịch tiếp theo. Khi chuyển ngày thành thời điểm trong vùng, hãy dùng `tomorrow.atStartOfDay(zone)`.
- `start.plus(Duration.ofHours(24))` đi đúng 24 giờ trên trục thời gian từ một instant đã biết.

Ở ngày thường, hai kết quả có thể trùng nhau. Qua DST hoặc một thay đổi timezone khác, chúng có thể khác nhau. Quy tắc chung: **lịch địa phương dùng phép tính ngày và vùng; thời lượng tuyệt đối dùng Instant và Duration**.

## 9. Biên khoảng và các lỗi thường gặp

| Cách làm sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| Dùng `23:59:59.999` làm cuối ngày | Có thể bỏ timestamp có độ chính xác cao hơn | Dùng mốc đầu ngày kế tiếp, loại trừ |
| Dùng `BETWEEN start AND end` với end là đầu ngày kế | Bao gồm cả bản ghi đúng tại ranh giới ngày kế tiếp trong SQL có `BETWEEN` bao hàm hai đầu | `>= start AND < end` |
| Cộng 24 giờ vào đầu ngày | Sai trong ngày dài 23/25 giờ | Tính `date.plusDays(1).atStartOfDay(zone)` |
| Dùng timezone của máy chủ cho báo cáo chi nhánh | Kết quả phụ thuộc môi trường chạy | Dùng timezone nghiệp vụ được cấu hình rõ |
| Chuyển qua `LocalDateTime` rồi giả định là instant | Mất offset và vùng | Lưu/truyền `Instant`, dùng `ZoneId` khi tạo ranh giới |
| Giả định đầu ngày mọi nơi luôn đúng 00:00 | Có quy tắc vùng lịch sử chuyển đổi tại nửa đêm | Dùng `LocalDate.atStartOfDay(zone)` |
| Không kiểm thử ranh giới | Bỏ sót đúng thời điểm bằng end hoặc trùng bản ghi | Test start inclusive, end exclusive, hai khoảng liền kề |
| Đếm cả hai đầu khi cần các ngày liên tiếp | Hai khoảng có thể cùng chứa sự kiện tại ranh giới | Dùng quy ước nửa mở nhất quán |

## 10. Kiểm thử ranh giới

Nên kiểm tra ít nhất các trường hợp sau:

1. Timestamp đúng `startInclusive` được đưa vào kết quả.
2. Timestamp nhỏ hơn `endExclusive` một đơn vị độ chính xác được database hỗ trợ vẫn được bao gồm.
3. Timestamp đúng `endExclusive` không được tính vào ngày trước.
4. Hai khoảng của hai ngày liền kề không trùng nhau và không để hở ranh giới.
5. Ngày DST có 23 hoặc 25 giờ vẫn có đủ đầu ngày đến đầu ngày kế tiếp.
6. Múi giờ của người dùng khác vùng nghiệp vụ nhưng báo cáo vẫn theo vùng nghiệp vụ đã chọn.
7. Database và driver giữ được round-trip đúng cho hai giá trị `Instant`, tránh mất độ chính xác ở thời điểm đầu mút.

Có thể kiểm thử tính liên tục bằng cách xác nhận `endExclusive(day)` bằng `startInclusive(day.plusDays(1))` khi dùng cùng `ZoneId`. Đây là tính chất then chốt của mô hình khoảng nửa mở.

### Ghi nhớ

Để biểu diễn một ngày lịch, dùng khoảng **`[startOfDay, startOfNextDay)`**. Tính hai mốc bằng `LocalDate.atStartOfDay(zone)`, sau đó chuyển sang `Instant` để truy vấn timestamp với `>= start` và `< end`. Cách này tránh lỗi độ chính xác, không trùng bản ghi giữa các ngày, và tôn trọng quy tắc DST của múi giờ được chọn.
