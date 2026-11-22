# Định dạng phần lẻ giây và ảnh hưởng tới độ chính xác

Trong Java Date-Time API (`java.time`), phần lẻ của giây được biểu diễn với độ chính xác tới nano giây. Tuy nhiên, **định dạng một giá trị với ít chữ số hơn không tự động làm tròn hoặc thay đổi đối tượng gốc**. Mẫu định dạng, cách parse chuỗi, phép cắt bớt và độ chính xác của nơi lưu trữ là những việc khác nhau.

Ví dụ, cùng một giá trị `LocalTime` có phần nano giây là `123_987_654` có thể được hiển thị theo ba cách:

~~~text
12:34:56.123          (3 chữ số thập phân, đến mili giây)
12:34:56.123987       (6 chữ số, đến micro giây)
12:34:56.123987654    (9 chữ số, đến nano giây)
~~~

Chuỗi đầu tiên chỉ **hiển thị** ba chữ số của phần lẻ. Giá trị đang nằm trong bộ nhớ vẫn có `123_987_654` nano giây cho tới khi ứng dụng chủ động biến đổi hoặc ghi nó vào nơi có độ chính xác thấp hơn.

## 1. Phần lẻ giây nghĩa là gì?

Một giây chia thành các đơn vị thập phân:

| Đơn vị | Số phần trên một giây | Ví dụ phần lẻ |
|---|---:|---|
| Giây | 1 | `12:34:56` |
| Mili giây (ms) | 1.000 | `.123` tương đương 123 ms |
| Micro giây (µs) | 1.000.000 | `.123987` tương đương 123.987 µs |
| Nano giây (ns) | 1.000.000.000 | `.123987654` tương đương 123.987.654 ns |

Trong `java.time`, `LocalTime`, `LocalDateTime`, `OffsetTime`, `OffsetDateTime`, `ZonedDateTime` và `Instant` hỗ trợ phần nano giây trong phạm vi các kiểu tương ứng. Có thể đọc nó bằng `getNano()` trên các kiểu có thành phần nano giây.

~~~java
LocalTime time = LocalTime.of(12, 34, 56, 123_987_654);
int nano = time.getNano(); // 123987654
~~~

`getNano()` trả về **nano giây trong giây hiện tại**, trong khoảng `0` tới `999_999_999`. Nó không phải số nano giây kể từ nửa đêm hoặc kể từ epoch.

Độ chính xác biểu diễn cũng không đảm bảo độ chính xác đo được: một đối tượng có thể chứa 9 chữ số nhưng đồng hồ hệ thống chỉ cung cấp giá trị cập nhật theo bước lớn hơn. Cần phân biệt ít nhất ba khái niệm:

- **Độ chính xác kiểu dữ liệu:** kiểu có khả năng giữ phần lẻ đến bao nhiêu chữ số.
- **Độ phân giải/độ chính xác của nguồn đồng hồ:** đồng hồ thực tế có thể đo hoặc trả về thời điểm ở mức nào.
- **Độ chính xác định dạng/lưu trữ:** có bao nhiêu chữ số được ghi ra chuỗi hoặc cơ sở dữ liệu.

## 2. Mẫu DateTimeFormatter dùng chữ S

Với `DateTimeFormatter.ofPattern(...)`, ký tự mẫu `S` có nghĩa **phần lẻ của giây**. Số chữ `S` quyết định số chữ số phần lẻ được xuất:

~~~java
DateTimeFormatter millis = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
DateTimeFormatter micros = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSS");
DateTimeFormatter nanos = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");
~~~

| Mẫu | Chữ số phần lẻ | Mức hiển thị tương ứng |
|---|---:|---|
| `HH:mm:ss` | 0 | Chỉ giờ, phút, giây |
| `HH:mm:ss.S` | 1 | 1 chữ số thập phân |
| `HH:mm:ss.SSS` | 3 | Mili giây |
| `HH:mm:ss.SSSSSS` | 6 | Micro giây |
| `HH:mm:ss.SSSSSSSSS` | 9 | Nano giây |

Ví dụ `12:34:56.123987654` định dạng bằng `SSS` thành `12:34:56.123`; các chữ số sau mili giây không xuất hiện. Với `SSSSSS`, chuỗi là `12:34:56.123987`. Với 9 chữ `S`, toàn bộ `123987654` được giữ trong chuỗi.

**Không nhầm `S` với `s`:**

- `s` là trường **giây trong phút** (0–59).
- `S` là trường **phần lẻ của giây**.
- `m` là phút, còn `M` là tháng khi dùng trong mẫu ngày giờ.

Sai chữ hoa/thường có thể tạo chuỗi trông hợp lý nhưng mang ý nghĩa khác. Mẫu có dấu chấm như `HH:mm:ss.SSS` cũng cố định dấu chấm thập phân trong mẫu đó; nếu cần định dạng theo quy ước địa phương hoặc xử lý định dạng linh hoạt, hãy chọn formatter phù hợp thay vì ghép chuỗi thủ công.

## 3. Định dạng ngắn hơn là cắt phần hiển thị, không phải làm tròn

`DateTimeFormatter` chuyển đối tượng sang chuỗi. Nó **không sửa đối tượng nguồn** và không tự áp dụng phép làm tròn theo toán học khi mẫu có ít chữ số `S` hơn.

~~~java
LocalTime time = LocalTime.of(12, 34, 56, 123_987_654);
DateTimeFormatter formatter = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");

System.out.println(time.format(formatter)); // 12:34:56.123
System.out.println(time);                   // 12:34:56.123987654
~~~

Phần nano còn lại không còn trong chuỗi định dạng ngắn; nó vẫn còn trong `time`. Đây khác với gọi phép cắt bớt để tạo ra một giá trị mới:

~~~java
LocalTime truncated = time.truncatedTo(ChronoUnit.MILLIS);
// truncated = 12:34:56.123
// time vẫn là 12:34:56.123987654
~~~

Ở ví dụ này, chuỗi định dạng và giá trị đã cắt đều in ra `12:34:56.123`, nhưng **chỉ `truncated` mới là một đối tượng mất phần nano dưới mili giây**. Nếu cần giữ dữ liệu gốc cho tính toán nhưng chỉ muốn giao diện gọn, chỉ định dạng. Nếu hợp đồng dữ liệu yêu cầu chính xác tới mili giây, hãy chuẩn hóa giá trị có chủ đích trước khi lưu hoặc so sánh.

### Nếu thật sự cần làm tròn

`DateTimeFormatter` không thay thế quy tắc làm tròn của nghiệp vụ. Với giá trị giờ trong ngày và nhu cầu làm tròn tới mili giây gần nhất, phải xác định rõ cách xử lý khi làm tròn vượt qua giây hoặc nửa đêm. Ví dụ ở mức khái niệm:

- `.1234` giây làm tròn mili giây gần nhất thành `.123`.
- `.1236` giây làm tròn thành `.124`.
- `.9996` giây có thể cần chuyển sang giây tiếp theo sau khi làm tròn.

Đừng chỉ định dạng với `SSS` rồi gọi đó là “làm tròn”; định dạng sẽ không tự biến `.1236` thành `.124`. Nếu hệ thống cần làm tròn, định nghĩa và kiểm thử phép làm tròn riêng, bao gồm trường hợp carry sang giây/ngày tiếp theo và quy tắc làm tròn tại điểm đúng giữa hai giá trị.

## 4. Parse chuỗi cũng ảnh hưởng độ chính xác

Khi parse chuỗi bằng mẫu chỉ có ba chữ số phần lẻ, chuỗi kết quả chỉ cung cấp độ chính xác đến mili giây:

~~~java
DateTimeFormatter millis = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
LocalTime parsed = LocalTime.parse("12:34:56.123", millis);
System.out.println(parsed.getNano()); // 123000000
~~~

Chuỗi `.123` có thể biểu diễn giá trị nano `123_000_000`; không có dữ liệu trong chuỗi để phục hồi những chữ số sau đó của một giá trị gốc như `123_987_654`. Đó là **mất thông tin do biểu diễn đầu vào**, không phải Java tự bỏ dữ liệu đang có trong một đối tượng khác.

So sánh:

| Thao tác | Giá trị nguồn | Kết quả |
|---|---|---|
| Format với `SSS` | `12:34:56.123987654` | Chuỗi `12:34:56.123`, đối tượng nguồn giữ nguyên |
| Parse chuỗi `.123` | `12:34:56.123` | Đối tượng mới có `getNano() == 123000000` |
| `truncatedTo(MILLIS)` | `12:34:56.123987654` | Đối tượng mới `12:34:56.123` |
| Round-trip qua định dạng 3 chữ số | `12:34:56.123987654` | Không thể phục hồi phần `987654` ns đã không được xuất |

Khi viết dữ liệu trao đổi giữa dịch vụ, chọn rõ độ chính xác của giao thức. ISO-8601 có thể biểu diễn phần lẻ với số chữ số khác nhau; bên gửi và bên nhận cần thống nhất có cho phép tối đa 3, 6 hoặc 9 chữ số, có chuẩn hóa hay không và có cần giữ chính xác toàn bộ dữ liệu đầu vào không.

### Định dạng số chữ số cố định và định dạng ISO

`DateTimeFormatter.ISO_LOCAL_TIME` và các formatter ISO tương ứng là lựa chọn tiện dụng khi cần định dạng ngày giờ theo chuẩn. Chúng thường chỉ xuất phần lẻ cần thiết, không nhất thiết luôn có 9 chữ số. Mẫu `SSSSSSSSS` phù hợp khi yêu cầu rõ ràng cần 9 chữ số cố định; chuỗi sẽ có các số 0 ở cuối nếu cần để đủ độ rộng.

~~~java
LocalTime time = LocalTime.of(12, 34, 56, 120_000_000);
System.out.println(time.format(DateTimeFormatter.ISO_LOCAL_TIME));
System.out.println(time.format(DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS")));
~~~

Output:

~~~text
12:34:56.120
12:34:56.120000000
~~~

Hai chuỗi biểu diễn cùng giờ, nhưng có quy ước về số chữ số khác nhau. Nếu người nhận coi độ dài chuỗi là dấu hiệu của độ chính xác, hãy ghi rõ quy tắc giao thức; đừng để hai bên suy diễn khác nhau.

## 5. Tác động khi chuyển sang epoch milliseconds

Đối với `Instant`, `toEpochMilli()` trả một số mili giây từ epoch. Phần độ chính xác nhỏ hơn một mili giây bị loại bỏ:

~~~java
Instant event = Instant.parse("2024-01-01T00:00:00.123987654Z");
long millis = event.toEpochMilli();
Instant restored = Instant.ofEpochMilli(millis);
~~~

Trong ví dụ này, `event` có phần lẻ `.123987654`, còn round-trip qua epoch milliseconds chỉ giữ `.123`:

~~~text
event = 2024-01-01T00:00:00.123987654Z
millis = 1704067200123
restored = 2024-01-01T00:00:00.123Z
~~~

Mất `987_654` nano giây sau phần mili giây là hệ quả của đơn vị lưu trữ. Nếu dữ liệu ban đầu cần độ chính xác nano, đừng lưu duy nhất một số epoch milliseconds rồi mong khôi phục lại các chữ số đã mất.

Cũng cần để ý phép chuyển đổi số học có phạm vi hữu hạn: chuyển một `Instant` rất xa sang `long` milliseconds hoặc nano giây có thể vượt miền biểu diễn và ném `ArithmeticException`. Độ chính xác thấp hơn không chỉ ảnh hưởng phần lẻ mà đôi khi còn ảnh hưởng phạm vi giá trị có thể lưu.

## 6. Định dạng trong API và cơ sở dữ liệu

Chọn độ chính xác theo **hợp đồng**, không theo cảm giác:

- **Log và timestamp sự kiện:** xác định nguồn đồng hồ, độ chính xác thực tế cần thiết và định dạng giao tiếp. Việc xuất 9 chữ số không bảo đảm đồng hồ đo đúng tới nano giây.
- **API JSON:** ghi rõ trường biểu diễn ISO-8601, offset và mức phần lẻ được phép; kiểm thử cả chuỗi 0, 3, 6 và 9 chữ số nếu giao thức hỗ trợ.
- **Cơ sở dữ liệu:** một số kiểu timestamp lưu tới mili giây hoặc micro giây, một số kiểu/engine hỗ trợ độ chính xác khác. Kiểm tra precision của kiểu cột, driver và phép bind; không giả định mọi database giữ đủ nano giây của `Instant`.
- **So sánh/khóa sự kiện:** nếu một hệ thống làm tròn tới mili giây còn hệ thống kia giữ nano giây, hai timestamp có thể không còn bằng nhau sau round-trip. Nếu cần so sánh theo độ chính xác chung, chuẩn hóa cả hai theo quy tắc được ghi rõ.
- **Ngày giờ địa phương:** không ghép một phần lẻ giây với múi giờ mặc định để suy ra timestamp nếu thiếu offset hoặc vùng cần thiết.

Ví dụ, nếu hệ thống chỉ lưu mili giây, hãy quyết định từ đầu liệu sẽ **cắt bớt**, **làm tròn**, hay **từ chối dữ liệu có độ chính xác cao hơn**. Ba chính sách này cho kết quả khác nhau; không để driver hoặc định dạng chuỗi quyết định ngầm chính sách nghiệp vụ.

## 7. Chương trình Java 17 hoàn chỉnh

Lưu thành **`FractionalSecondDemo.java`**:

~~~java
import java.time.Instant;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class FractionalSecondDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(12, 34, 56, 123_987_654);
        DateTimeFormatter millis = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
        DateTimeFormatter micros = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSS");
        DateTimeFormatter nanos = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");

        System.out.println("stored nano = " + time.getNano());
        System.out.println("millis display = " + time.format(millis));
        System.out.println("micros display = " + time.format(micros));
        System.out.println("nanos display = " + time.format(nanos));
        System.out.println("original = " + time);
        System.out.println("truncated millis value = " +
                time.truncatedTo(ChronoUnit.MILLIS));
        LocalTime parsed = LocalTime.parse("12:34:56.123", millis);
        System.out.println("parsed nano = " + parsed.getNano());
        System.out.println("parsed value = " + parsed);

        Instant event = Instant.parse("2024-01-01T00:00:00.123987654Z");
        System.out.println("instant original = " + event);
        System.out.println("epoch millis = " + event.toEpochMilli());
        System.out.println("instant after millis roundtrip = " +
                Instant.ofEpochMilli(event.toEpochMilli()));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac FractionalSecondDemo.java
java FractionalSecondDemo
~~~

Đầu ra đã được kiểm chứng bằng `javac --release 17`:

~~~text
stored nano = 123987654
millis display = 12:34:56.123
micros display = 12:34:56.123987
nanos display = 12:34:56.123987654
original = 12:34:56.123987654
truncated millis value = 12:34:56.123
parsed nano = 123000000
parsed value = 12:34:56.123
instant original = 2024-01-01T00:00:00.123987654Z
epoch millis = 1704067200123
instant after millis roundtrip = 2024-01-01T00:00:00.123Z
~~~

**Cách đọc kết quả:**

1. Đối tượng gốc có `123_987_654` nano giây.
2. Formatter `SSS` chỉ xuất `.123`; formatter 6 và 9 chữ số lần lượt xuất `.123987` và `.123987654`.
3. Biến `time` ban đầu vẫn có đầy đủ nano giây sau định dạng.
4. Khi parse chuỗi chỉ có `.123`, đối tượng mới có nano `123_000_000` vì đầu vào không mang phần thấp hơn mili giây.
5. Round-trip `Instant → epoch milliseconds → Instant` làm mất phần dưới mili giây và không thể phục hồi chính xác timestamp gốc.

## 8. Lỗi thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| Nghĩ `SSS` làm tròn đến mili giây | Định dạng chỉ xuất ba chữ số phần lẻ | Dùng phép làm tròn riêng nếu nghiệp vụ yêu cầu |
| Nghĩ định dạng ngắn làm thay đổi đối tượng | `DateTimeFormatter` chỉ tạo chuỗi | Dùng `truncatedTo(...)` khi muốn tạo giá trị cắt bớt |
| Nghĩ parse `.123` có thể khôi phục `.123987654` | Chuỗi không có các chữ số bị thiếu | Giao thức cần giữ phần lẻ thì phải truyền đầy đủ |
| Nhầm `S` và `s` | Một chữ là phần lẻ, một chữ là giây trong phút | Kiểm tra bảng ký tự mẫu |
| Luôn xuất 9 chữ số dù API chỉ yêu cầu mili giây | Chuỗi dài hơn không đảm bảo nguồn chính xác hơn | Thống nhất độ chính xác theo hợp đồng |
| Lưu `Instant` nano vào cột chỉ có độ chính xác ms | Dữ liệu bị giảm độ chính xác khi ghi/đọc | Xác nhận precision của cột/driver |
| Chỉ nhìn `getNano()` để xác định độ chính xác | Nó là thành phần nano trong giây, không chứng minh đồng hồ thực | Xem nguồn thời gian, precision và hợp đồng |
| So sánh timestamp từ hệ thống khác nhau sau khi một bên đã cắt | Hai bên có thể đại diện độ chi tiết khác nhau | Chuẩn hóa chung và ghi rõ quy tắc |
| Tự coi phần lẻ là mili giây dựa trên 3 chữ số | Đơn vị/format phải được nêu trong giao thức | Xác định mẫu và đơn vị rõ ràng |
| Cho rằng ISO formatter luôn xuất 9 chữ số | Formatter ISO có thể dùng số chữ số cần thiết | Dùng mẫu cố định nếu định dạng yêu cầu chiều dài cố định |

## 9. Tự kiểm tra

1. Với giá trị nano `123_987_654`, mẫu `SSS` hiển thị phần lẻ nào? **`.123`**.
2. `SSSSSS` hiển thị bao nhiêu chữ số? **6**, ví dụ `.123987`.
3. Định dạng với `SSS` có sửa đối tượng gốc không? **Không**.
4. Parse `12:34:56.123` bằng đúng formatter mili giây tạo `getNano()` bằng bao nhiêu? **123000000**.
5. `getNano()` trả toàn bộ nano kể từ epoch không? **Không**, chỉ nano trong giây hiện tại.
6. Round-trip qua epoch milliseconds có giữ `.123987654` không? **Không**; kết quả chỉ còn `.123` trong ví dụ.
7. Nếu cần làm tròn chứ không cắt phần lẻ, dùng formatter `SSS` có đủ không? **Không**, cần định nghĩa phép làm tròn riêng.
8. Vì sao 9 chữ số phần lẻ không chứng minh đồng hồ có độ chính xác nano? **Kiểu dữ liệu và chuỗi có thể chứa 9 chữ số, trong khi nguồn đồng hồ có độ phân giải thấp hơn**.
9. Cột database có precision 3 chữ số mà ứng dụng cần nano giây thì cần kiểm tra gì? **Kiểu cột, driver, quy tắc chuyển đổi và khả năng round-trip**.
10. Nên quyết định cắt hay làm tròn ở đâu? **Trong hợp đồng dữ liệu hoặc logic nghiệp vụ được kiểm thử**, không để mẫu hiển thị hoặc driver quyết định ngầm.

**Ghi nhớ:** `S` là phần lẻ giây; số chữ `S` kiểm soát độ chi tiết được **hiển thị/parse**. Format ngắn không tự thay đổi đối tượng, nhưng parse chuỗi thiếu chữ số hoặc chuyển sang đơn vị lưu trữ thấp hơn sẽ làm mất thông tin. Phân biệt **định dạng, cắt bớt, làm tròn và precision của nơi lưu**; chọn quy tắc rõ ràng để tránh timestamp sai hoặc so sánh không nhất quán.

### Tài liệu tham khảo

- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE 17 — DateTimeFormatter pattern letters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE 17 — LocalTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
