# java.sql.Timestamp với Instant hoặc LocalDateTime theo ngữ nghĩa

## 1. Chọn điều cần giữ trước khi chọn phương thức chuyển đổi

Khi gặp một cột ngày giờ và một đối tượng `java.sql.Timestamp`, cần hỏi dữ liệu đang biểu diễn điều gì:

- **Một thời điểm đã xác định trên trục thời gian**, chẳng hạn thời điểm ghi nhận sự kiện: dùng `Instant` trong phần xử lý.
- **Một bộ ngày giờ địa phương**, chẳng hạn “ngày 15/1 lúc 09:00” chưa gắn múi giờ: dùng `LocalDateTime`.
- **Một lịch hẹn tại một địa phương cụ thể**: ngày giờ địa phương thường cần đi cùng `ZoneId` hoặc chính sách múi giờ để xác định lần xảy ra cụ thể.

Hai loại đầu không thể đổi qua lại chỉ bằng cách thay tên kiểu. `2024-01-15T09:00` chưa cho biết 09:00 ở đâu. `2024-01-15T02:00Z` đã xác định thời điểm; tại offset +07:00 nó có bộ ngày giờ là 09:00.

`Timestamp` là kiểu cầu nối cũ của JDBC. Tên của lớp Java không tự cho biết cột nguồn mang ngữ nghĩa nào, cột SQL có lưu múi giờ hay không, hoặc driver đã diễn giải giá trị bằng múi giờ nào.

Bài này hướng dẫn chọn phép chuyển theo ngữ nghĩa, kiểm tra ảnh hưởng múi giờ mặc định và giữ độ chính xác. Phần chương trình chạy độc lập không cần cơ sở dữ liệu; các đoạn JDBC được ghi rõ là mã tích hợp minh họa.

## 2. Ba kiểu có trách nhiệm khác nhau

| Kiểu | Biểu diễn gì? | Điều không được tự suy ra |
| --- | --- | --- |
| `Instant` | Một điểm trên trục thời gian, gồm giây epoch và nano giây | Không lưu múi giờ địa phương gốc của sự kiện |
| `LocalDateTime` | Năm-tháng-ngày và giờ-phút-giây-nano, không có offset/múi giờ | Chưa xác định duy nhất một thời điểm |
| `java.sql.Timestamp` | Giá trị thời gian theo biểu diễn kế thừa từ `Date`, kèm phần nano giây để phục vụ JDBC | Không lưu `ZoneId` hay tự bảo đảm ngữ nghĩa của cột SQL |

`Instant` và `LocalDateTime` là bất biến. `Timestamp` có thể bị thay đổi bằng `setTime` hoặc `setNanos`; không đối xử với nó như một giá trị bất biến trong mô hình nghiệp vụ.

Một `Timestamp` trong bộ nhớ có thể chuyển thành mốc thời gian bằng `toInstant`. Nhưng nếu driver đã tạo nó từ một cột không có múi giờ bằng quy ước sai, kết quả `Instant` vẫn sai về nghiệp vụ. Phương thức chuyển đổi không thể khôi phục thông tin múi giờ chưa từng được cung cấp.

Định nghĩa hai kiểu hiện đại nằm ở [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) và [LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html).

## 3. Nhánh giữ thời điểm: Timestamp ↔ Instant

Cặp API trực tiếp:

```java
// Minh họa bên trong một phương thức, với createdAt đã có.
Timestamp legacy = Timestamp.from(createdAt);
Instant restored = legacy.toInstant();
```

Ở đây `createdAt` là `Instant`. Nếu giá trị nằm trong miền biểu diễn của `Timestamp`, cặp chuyển giữ cùng thời điểm và phần nano giây. Nó không cần chọn múi giờ để biết thời điểm là gì.

Ví dụ `2024-01-15T02:00:00.123456789Z` vẫn là thời điểm ấy sau khi chuyển qua `Timestamp`. Việc một chuỗi hiển thị thành 02:00 hay 09:00 không chứng minh thời điểm đã thay đổi; đó có thể chỉ là cách nhìn theo múi giờ.

Không dùng chuỗi `Timestamp.toString()` làm bằng chứng rằng giá trị đang ở UTC. Chuỗi này không kèm offset và được biểu diễn theo ngày giờ địa phương. Khi cần quan sát một thời điểm rõ ràng, có thể xem `timestamp.toInstant()`.

`Instant` có miền biểu diễn khác với `Timestamp`; không giả định chuyển đổi được mọi giá trị cực trị. Với dữ liệu thông thường, vẫn cần kiểm tra thêm miền ngày giờ mà cơ sở dữ liệu hỗ trợ.

## 4. Nhánh bộ ngày giờ địa phương: Timestamp ↔ LocalDateTime

Cặp API thường gặp:

```java
// Minh họa bên trong một phương thức, với scheduledLocal đã có.
Timestamp legacy = Timestamp.valueOf(scheduledLocal);
LocalDateTime restored = legacy.toLocalDateTime();
```

Điểm quan trọng là quy tắc múi giờ:

- `Timestamp.valueOf(LocalDateTime)` diễn giải bộ ngày giờ theo múi giờ địa phương mặc định của JVM.
- `Timestamp.toLocalDateTime()` đọc lại các thành phần ngày giờ theo múi giờ địa phương.
- Đối tượng `Timestamp` không ghi nhớ “múi giờ lúc tạo” để tự dùng lại cho mọi phép đọc sau này.

Với cùng giá trị địa phương `2024-01-15T09:00`:

| Múi giờ mặc định khi gọi valueOf | Thời điểm nhận được qua toInstant |
| --- | --- |
| UTC | `2024-01-15T09:00Z` |
| Offset +07:00 | `2024-01-15T02:00Z` |

Ngược lại, với cùng `Timestamp` đang biểu diễn thời điểm `2024-01-15T02:00Z`:

| Múi giờ mặc định khi gọi toLocalDateTime | Bộ ngày giờ nhận được |
| --- | --- |
| UTC | `2024-01-15T02:00` |
| Offset +07:00 | `2024-01-15T09:00` |

Các ví dụ dùng ngày giờ thông thường, không ở chỗ chuyển giờ mùa hè. Chúng cho thấy hai phép chuyển địa phương có phụ thuộc môi trường; không được coi đó là một cách chuyển trung lập về múi giờ. Hợp đồng của các phương thức được mô tả tại [Timestamp](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Timestamp.html).

Với ngày giờ thuộc khoảng thiếu hoặc khoảng lặp do chuyển giờ mùa hè, còn cần chính sách xử lý riêng. Không dùng một vòng chuyển qua kiểu cũ để xác thực rằng mọi `LocalDateTime` đều xác định duy nhất một thời điểm.

## 5. Cần đổi ngữ nghĩa thì cung cấp múi giờ rõ ràng

Nếu đã có `Instant` và muốn ngày giờ tại một nơi, dùng `LocalDateTime.ofInstant(instant, zone)`. Nếu đã có `LocalDateTime` và biết offset, dùng `localDateTime.toInstant(offset)`.

Ví dụ với offset cố định +07:00:

```java
// Đoạn minh họa bên trong một phương thức.
ZoneOffset offset = ZoneOffset.ofHours(7);
Instant event = Instant.parse("2024-01-15T02:00:00Z");
LocalDateTime local = LocalDateTime.ofInstant(event, offset);
// local = 2024-01-15T09:00
Instant resolved = local.toInstant(offset);
// resolved = 2024-01-15T02:00:00Z
```

Offset cố định được dùng để làm ví dụ dễ kiểm chứng. Nếu yêu cầu nói đến một địa phương có quy tắc múi giờ theo thời gian, hãy dùng `ZoneId` phù hợp và xử lý tính hợp lệ của giờ địa phương theo yêu cầu. Một offset không thay thế đầy đủ quy tắc của một vùng.

Không gắn UTC cho `LocalDateTime` chỉ để phương thức chuyển chịu biên dịch. Gắn UTC là một quyết định có nghĩa: tuyên bố rằng các thành phần đó được hiểu theo UTC. Nếu đầu vào là 09:00 ở offset +07:00, gắn UTC làm lệch thời điểm 7 giờ.

Tương tự, nếu chỉ cần giữ nguyên bộ ngày giờ của một lịch địa phương, đừng tự chuyển nó thành `Instant` rồi quên múi giờ đã dùng để diễn giải.

## 6. JDBC: cả cột, driver và hai chiều đọc/ghi đều phải thống nhất

Ngữ nghĩa của dữ liệu lưu không chỉ phụ thuộc lớp Java. Cần thống nhất:

1. Cột đang mang thời điểm hay ngày giờ địa phương?
2. Kiểu SQL thực tế và quy tắc của hệ quản trị là gì?
3. Driver hỗ trợ ánh xạ nào?
4. Múi giờ/offset được cung cấp ở bước nào?
5. Độ chính xác phần giây và quy tắc xử lý `NULL` là gì?

Không suy từ riêng tên `TIMESTAMP` rằng mọi hệ quản trị xử lý giống nhau. Một kiểu có hỗ trợ thời điểm/offset cũng không tự bảo đảm giữ được `ZoneId` vùng ban đầu. Nếu cần nhớ vùng của lịch hẹn, phải có dữ liệu tương ứng.

### 6.1. Dữ liệu ngày giờ địa phương

Với cột và driver JDBC hỗ trợ ánh xạ tương ứng, có thể dùng trực tiếp `LocalDateTime` qua API có kiểu:

```java
// Mã tích hợp minh họa, không phải chương trình chạy độc lập.
// ps và rs là PreparedStatement/ResultSet đã được tạo và dùng đúng vòng đời.
// Cột scheduled_local được thiết kế để giữ các thành phần ngày giờ địa phương.
ps.setObject(1, scheduledLocal);

// Ở thao tác đọc, sau khi rs đã trỏ đến hàng kết quả:
LocalDateTime loadedLocal =
        rs.getObject("scheduled_local", LocalDateTime.class);
```

Cần xác nhận khả năng hỗ trợ của driver và kiểu cột cụ thể. Không mặc định mọi driver nhận `Instant` trực tiếp giống như các kiểu ngày giờ khác.

Nếu mã cũ bắt buộc dùng `setTimestamp`/`getTimestamp`, phải kiểm tra quy ước múi giờ của hai chiều trước khi dùng `valueOf`/`toLocalDateTime`. Hai phương thức đó chỉ là cầu nối cũ; chúng không tự sửa cấu hình driver.

### 6.2. Dữ liệu thời điểm qua cột không có múi giờ nhưng được quy ước UTC

Nếu hệ thống đã chọn rõ quy ước “các thành phần trong cột này luôn là UTC”, đường JDBC cũ có thể truyền `Calendar` UTC ở cả chiều ghi và đọc:

```java
// Mã tích hợp minh họa; cần kết nối, câu lệnh và cột đúng với quy ước UTC.
// Các kiểu cần import: java.sql.*, java.time.*, java.util.Calendar,
// java.util.TimeZone.
Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));

if (createdAt == null) {
    ps.setNull(1, Types.TIMESTAMP);
} else {
    ps.setTimestamp(1, Timestamp.from(createdAt), utc);
}

// Ở thao tác đọc, sau khi rs đã trỏ đến hàng kết quả:
Timestamp raw = rs.getTimestamp("created_at_utc", utc);
Instant loaded = raw == null ? null : raw.toInstant();
```

`createdAt` ở đây là `Instant`. Tên cột chỉ giúp nhắc quy ước, không tự làm cơ sở dữ liệu hiểu UTC. Dữ liệu cũ và mọi bên ghi/đọc phải tuân thủ cùng quy ước.

API `setTimestamp(..., Calendar)` cho driver múi giờ để tạo các thành phần SQL; `getTimestamp(..., Calendar)` dùng lịch cung cấp để diễn giải giá trị thiếu thông tin múi giờ. Xem [PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) và [ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html).

`Calendar` có thể thay đổi trạng thái, nên đoạn minh họa tạo một đối tượng trong phạm vi thao tác, không chia sẻ một đối tượng dùng chung giữa các luồng.

Nếu cột/driver hỗ trợ cách lưu thời điểm qua kiểu SQL có offset, có thể chọn ánh xạ phù hợp như `OffsetDateTime`, rồi chuyển sang `Instant` trong mô hình. Đó là một hợp đồng lưu trữ khác, cần kiểm tra với hệ quản trị cụ thể; không trộn nó tùy ý với quy ước cột địa phương lưu UTC.

## 7. Nano giây, mili giây và dữ liệu có thể thay đổi

`Timestamp` có phần nano giây tách biệt với biểu diễn kế thừa từ `Date`. Cặp `Timestamp.from(instant)`/`toInstant()` giữ phần này khi giá trị được biểu diễn được.

Nếu chuyển vòng qua `getTime()`, kết quả chỉ có độ chính xác mili giây:

```text
Ban đầu:                2024-01-15T02:00:00.123456789Z
Qua getTime/epochMilli:  2024-01-15T02:00:00.123Z
```

Vì vậy, không thay `timestamp.toInstant()` bằng `Instant.ofEpochMilli(timestamp.getTime())` khi yêu cầu giữ nano giây.

Khả năng giữ nano trong Java không bảo đảm cột SQL giữ đủ 9 chữ số phần giây. Cột hoặc driver có thể dùng độ chính xác thấp hơn. Phép kiểm tra đọc lại cần so với độ chính xác và quy tắc làm tròn/cắt đã được xác định.

Ngoài ra, `Timestamp.setNanos` hoặc `setTime` làm thay đổi đối tượng. Nên chuyển sang kiểu bất biến ở ranh giới JDBC, và không để cùng một đối tượng `Timestamp` có thể thay đổi bị chia sẻ ngoài ý muốn. Không coi việc kế thừa `Date` là bảo đảm mọi quy tắc so sánh và độ chính xác của hai lớp giống nhau.

## 8. Chương trình Java 17+ kiểm chứng phụ thuộc múi giờ

Lưu mã sau thành `TimestampMeaning.java`. Chương trình chỉ dùng JDK, không kết nối cơ sở dữ liệu.

Nó tạm đổi múi giờ mặc định để chứng minh ảnh hưởng lên các phép chuyển địa phương, rồi khôi phục trong `finally`. Hãy chạy như tiến trình Java riêng như lệnh bên dưới; không sao chép cách đổi mặc định toàn JVM vào luồng xử lý yêu cầu của ứng dụng đang phục vụ nhiều tác vụ.

```java
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Objects;
import java.util.TimeZone;

public class TimestampMeaning {
    private static int checks;

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        TimeZone previousDefault = TimeZone.getDefault();
        try {
            Instant event = Instant.parse("2024-01-15T02:00:00.123456789Z");
            LocalDateTime wall = LocalDateTime.parse("2024-01-15T09:00:00.123456789");
            Timestamp timeline = Timestamp.from(event);
            eq(timeline.toInstant(), event);
            eq(timeline.getNanos(), 123_456_789);

            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
            LocalDateTime utcFields = timeline.toLocalDateTime();
            Instant utcEncoded = Timestamp.valueOf(wall).toInstant();
            eq(utcFields, LocalDateTime.parse("2024-01-15T02:00:00.123456789"));
            eq(utcEncoded, Instant.parse("2024-01-15T09:00:00.123456789Z"));
            eq(Timestamp.valueOf(wall).toLocalDateTime(), wall);

            TimeZone.setDefault(TimeZone.getTimeZone("GMT+07:00"));
            LocalDateTime plusSevenFields = timeline.toLocalDateTime();
            Instant plusSevenEncoded = Timestamp.valueOf(wall).toInstant();
            eq(plusSevenFields, wall);
            eq(plusSevenEncoded, event);
            eq(Timestamp.valueOf(wall).toLocalDateTime(), wall);
            eq(timeline.toInstant(), event);

            ZoneOffset offset = ZoneOffset.ofHours(7);
            LocalDateTime explicitFields = LocalDateTime.ofInstant(event, offset);
            Instant explicitEvent = wall.toInstant(offset);
            eq(explicitFields, wall);
            eq(explicitEvent, event);
            eq(Timestamp.from(explicitEvent).toInstant(), event);
            eq(utcEncoded.equals(plusSevenEncoded), false);

            Instant millisOnly = Instant.ofEpochMilli(timeline.getTime());
            eq(millisOnly, event.truncatedTo(ChronoUnit.MILLIS));
            eq(millisOnly.equals(event), false);

            Timestamp mutableCopy = Timestamp.from(event);
            mutableCopy.setNanos(999_000_000);
            eq(mutableCopy.toInstant(),
                    Instant.parse("2024-01-15T02:00:00.999Z"));
            eq(event, Instant.parse("2024-01-15T02:00:00.123456789Z"));

            System.out.println("event=" + event);
            System.out.println("utcFields=" + utcFields);
            System.out.println("plusSevenFields=" + plusSevenFields);
            System.out.println("utcEncoded=" + utcEncoded);
            System.out.println("plusSevenEncoded=" + plusSevenEncoded);
            System.out.println("explicitEvent=" + explicitEvent);
            System.out.println("millisOnly=" + millisOnly);
            System.out.println("PASS checks=" + checks);
        } finally {
            TimeZone.setDefault(previousDefault);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TimestampMeaning.java
java TimestampMeaning
```

Stdout:

```text
event=2024-01-15T02:00:00.123456789Z
utcFields=2024-01-15T02:00:00.123456789
plusSevenFields=2024-01-15T09:00:00.123456789
utcEncoded=2024-01-15T09:00:00.123456789Z
plusSevenEncoded=2024-01-15T02:00:00.123456789Z
explicitEvent=2024-01-15T02:00:00.123456789Z
millisOnly=2024-01-15T02:00:00.123Z
PASS checks=17
```

Các điểm cần đọc từ kết quả:

- `utcFields` và `plusSevenFields` khác nhau dù lấy từ cùng một `Timestamp`.
- `utcEncoded` và `plusSevenEncoded` khác thời điểm dù bắt đầu từ cùng một `LocalDateTime`.
- `explicitEvent` được xác định bằng offset truyền rõ, không phụ thuộc múi giờ mặc định.
- `millisOnly` đã mất 456.789 nano giây còn lại sau phần mili giây.

Hàm `eq` chủ động ném `AssertionError` khi sai, không cần cờ `-ea`. Mười bảy kiểm tra chứng minh hành vi chuyển đổi trong bộ nhớ ở các giá trị đã chọn. Chúng không chứng minh driver, phiên kết nối hoặc kiểu cột của một cơ sở dữ liệu chưa được chạy thử là đúng.

## 9. Kiểm tra tích hợp nên xác nhận điều gì?

Với dữ liệu **thời điểm**, kiểm tra giá trị đọc lại có cùng `Instant` sau khi tính đến độ chính xác cột đã công bố. Thử ứng dụng trong ít nhất hai cấu hình múi giờ để phát hiện phụ thuộc ngầm.

Với dữ liệu **địa phương**, kiểm tra các trường năm-tháng-ngày và giờ-phút-giây được giữ đúng, thay vì chỉ so epoch. Nếu dữ liệu cần gắn với một vùng, kiểm tra cả quy tắc thiếu/lặp giờ khi vùng đó chuyển offset.

Các trường hợp có giá trị học tập:

- Cùng giá trị được ghi và đọc bởi hai JVM có múi giờ mặc định khác nhau.
- Phần nano giây có nhiều chữ số hơn độ chính xác của cột.
- Giá trị SQL `NULL`.
- Thời điểm gần ranh giới ngày, để thấy giờ lệch có thể làm đổi ngày.
- Đọc lại dữ liệu cũ được tạo trước khi quy ước múi giờ được thống nhất.

Không sửa sai bằng cộng/trừ cố định 7 giờ trong mọi đường đọc. Phải tìm đúng bước đã diễn giải sai múi giờ và sửa hợp đồng ở bước đó; độ lệch không phải lúc nào cũng cố định giữa mọi vùng và mọi ngày.

## 10. Lỗi thường gặp và thực hành

| Lỗi | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Gọi `toLocalDateTime` rồi mặc định đó là UTC | Có thể diễn giải lại giờ địa phương thành thời điểm sai | Dùng `toInstant` khi cần giữ thời điểm |
| Gọi `valueOf(local).toInstant()` mà chưa biết múi giờ | Thời điểm phụ thuộc môi trường JVM | Xác định vùng/offset trước |
| Cho rằng `Timestamp` lưu múi giờ lúc tạo | Đọc địa phương có thể đổi khi môi trường đổi | Lưu vùng riêng nếu cần và chuyển tường minh |
| Dựa vào `toString` để kết luận giá trị UTC | Chuỗi không có offset | Quan sát `Instant` hoặc định dạng có offset |
| Vòng qua mili giây | Mất phần nano dưới mili giây | Dùng cặp API chuyển trực tiếp |
| Coi driver đã luôn ánh xạ đúng | Sai lệch có thể xuất hiện trước bước chuyển | Kiểm tra hai chiều JDBC với cột thực tế |
| Trộn quy ước địa phương và quy ước UTC trong một cột | Không còn diễn giải nhất quán | Chọn và kiểm chứng một hợp đồng lưu trữ rõ |

Thực hành:

1. **Cột ghi thời điểm sự kiện, driver đã trả đúng `Timestamp`.** Chọn `toInstant()`. Không đi qua `toLocalDateTime` để tự gắn lại UTC.

2. **Nhận lịch 09:00 ngày 15/1/2024 tại offset +07:00.** Chuyển đúng thành `2024-01-15T02:00Z`. Nếu gắn UTC trực tiếp cho bộ giờ 09:00, kết quả lệch 7 giờ.

3. **Đọc ngày giờ địa phương chưa có múi giờ.** Giữ `LocalDateTime` nếu đó là đúng dữ liệu cần lưu; đừng tự khẳng định một `Instant` khi thiếu quy tắc diễn giải.

4. **Phần giây ban đầu là `.123456789` nhưng cột chỉ giữ 6 chữ số.** Xác định quy tắc xử lý độ chính xác rồi kiểm tra kết quả tương ứng. Không quy lỗi ngay cho múi giờ.

5. **Cùng một sự kiện in ra 02:00 ở máy A và 09:00 ở máy B.** So `toInstant()` và kiểm tra cách định dạng trước; hai cách hiển thị có thể cùng một thời điểm.

Trước khi viết phép chuyển, hãy xác định thứ phải được giữ: thời điểm hay bộ ngày giờ địa phương. Sau đó cung cấp ngữ cảnh múi giờ ở đúng chỗ và kiểm tra cả đường lưu lẫn đường đọc.
