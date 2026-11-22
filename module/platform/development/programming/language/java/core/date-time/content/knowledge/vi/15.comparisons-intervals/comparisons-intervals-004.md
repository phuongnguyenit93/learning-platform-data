# Sắp xếp ngày giờ và chọn Comparator theo ý nghĩa cần dùng

## Mục tiêu

Trong Java, “sắp xếp ngày giờ” có thể mang nhiều nghĩa: theo ngày–giờ trên đồng hồ, theo thời điểm thực trên timeline, theo offset, hoặc theo một khóa nghiệp vụ phụ. Chọn sai thứ tự so sánh có thể tạo ra lịch trình hoặc báo cáo nhìn có vẻ hợp lý nhưng sai về thời gian thực.

Bài này giải thích thứ tự tự nhiên của các kiểu `java.time`, cách xây dựng `Comparator`, cách xử lý giá trị `null`, tiêu chí phụ, thứ tự đảo ngược và lựa chọn phù hợp cho dữ liệu chưa có múi giờ hoặc có offset/vùng. Ví dụ dùng Java 17+.

## 1. Trước tiên hãy xác định “đúng thứ tự” nghĩa là gì

| Loại dữ liệu | Câu hỏi nghiệp vụ | Kiểu so sánh thường phù hợp |
|---|---|---|
| `LocalDate` | Ngày lịch nào đến trước? | Thứ tự tự nhiên của ngày |
| `LocalDateTime` | Giờ đồng hồ địa phương nào đến trước? | Thứ tự tự nhiên của local date-time |
| `Instant` | Sự kiện nào xảy ra trước trên timeline? | Thứ tự tự nhiên của Instant |
| `OffsetDateTime` | So sánh timestamp thực hay so sánh cả cách biểu diễn offset? | So sánh `toInstant()` nếu cần timeline; thứ tự tự nhiên nếu cần quy tắc của kiểu |
| `ZonedDateTime` | Sự kiện nào xảy ra trước, hay cần xem cả vùng giờ? | So sánh `toInstant()` cho timeline; thêm khóa phụ nếu cần phân biệt cách biểu diễn |
| Đối tượng lịch hẹn | Xếp theo thời điểm, sau đó theo mức ưu tiên hoặc mã? | `Comparator.comparing(...).thenComparing(...)` |

Trước khi viết comparator, trả lời ba câu:

1. Dữ liệu đã đại diện cho một thời điểm tuyệt đối chưa? `Instant`, `OffsetDateTime` và `ZonedDateTime` xác định được thời điểm; `LocalDateTime` thì không.
2. Khi hai giá trị cùng thời điểm nhưng có offset/vùng khác nhau, chúng có được xem như tương đương trong nghiệp vụ không?
3. Nếu thời gian bằng nhau, cần tiêu chí phụ nào để tạo thứ tự ổn định và có ý nghĩa?

## 2. Thứ tự tự nhiên của các kiểu java.time

Các kiểu ngày giờ phổ biến đều hỗ trợ so sánh tự nhiên, nhưng ý nghĩa không giống nhau.

### LocalDate và LocalDateTime

`LocalDate` so sánh năm, tháng rồi ngày trong lịch ISO. `LocalDateTime` so sánh các thành phần địa phương từ ngày đến nano giây. Không kiểu nào có offset hoặc zone, nên không thể suy ra thời điểm UTC từ chính giá trị đó.

```java
LocalDate firstDay = LocalDate.parse("2025-02-01");
LocalDate secondDay = LocalDate.parse("2025-01-31");

System.out.println(firstDay.compareTo(secondDay) > 0);
```

Kết quả:

```text
true
```

`LocalDateTime` có thể sắp xếp các giờ đồng hồ trong cùng một lịch địa phương. Nhưng nếu các giá trị đến từ nhiều múi giờ, so sánh local fields trực tiếp không cho thứ tự sự kiện thực. Ví dụ 09:00 tại Tokyo và 08:00 tại New York không thể sắp xếp toàn cầu chỉ bằng hai local date-time khi thiếu ngày/vùng liên quan.

### Instant

`Instant` là lựa chọn tự nhiên nhất cho thứ tự thời điểm thực. `compareTo()` và phép sắp xếp tự nhiên so sánh điểm trên timeline, không phụ thuộc người dùng xem ở múi giờ nào.

```java
Instant a = Instant.parse("2025-01-15T03:30:00Z");
Instant b = Instant.parse("2025-01-15T04:00:00Z");

System.out.println(a.isBefore(b));
```

Kết quả:

```text
true
```

### OffsetDateTime và ZonedDateTime

Hai kiểu này đều chứa đủ thông tin để xác định một `Instant`, nhưng còn có dữ liệu biểu diễn địa phương, offset hoặc zone. Thứ tự tự nhiên của chúng không nên được thay bằng giả định “chỉ luôn so sánh giờ trên đồng hồ”. Nếu nghiệp vụ quan tâm duy nhất sự kiện xảy ra trước hay sau, hãy thể hiện rõ bằng comparator dựa trên `toInstant()`.

Hai giá trị sau đại diện cùng một thời điểm:

```text
2025-01-15T10:30+07:00
2025-01-15T03:30Z
```

Chúng có thể khác cách biểu diễn nhưng `toInstant()` giống nhau. Comparator theo timeline coi chúng có khóa thời gian bằng nhau; khi cần một kết quả thứ tự toàn phần cho cách biểu diễn, hãy thêm tiêu chí phụ.

## 3. Comparator theo thời điểm thực (timeline order)

Nếu đầu vào đã là `OffsetDateTime` hoặc `ZonedDateTime`, dùng `toInstant()` làm khóa thời gian:

```java
Comparator<OffsetDateTime> timelineOrder =
        Comparator.comparing(OffsetDateTime::toInstant);
```

Với `ZonedDateTime`:

```java
Comparator<ZonedDateTime> timelineOrder =
        Comparator.comparing(ZonedDateTime::toInstant);
```

Cách viết này thể hiện đúng ý nghĩa: so sánh **thời điểm tuyệt đối**. Nếu chỉ sắp xếp `OffsetDateTime`/ `ZonedDateTime` bằng natural order, kết quả vẫn có thứ tự theo hợp đồng `Comparable` của kiểu, nhưng có thể dùng thông tin phụ của giá trị khi hai đầu vào cùng thời điểm. Comparator timeline chuyên dụng giúp người đọc mã biết chính xác tie có nghĩa gì.

Nếu hai sự kiện cùng timestamp nhưng cần thứ tự xác định, thêm khóa phụ như ID:

```java
Comparator<Event> order = Comparator
        .comparing(Event::occurredAt)
        .thenComparing(Event::id);
```

Đoạn trên giả sử `occurredAt` trả về `Instant` và `id` là kiểu có thứ tự tự nhiên. Khi timestamp giống nhau, ID quyết định thứ tự còn lại.

## 4. Tạo Comparator với comparing() và thenComparing()

`Comparator.comparing(keyExtractor)` tạo comparator từ một khóa có thể so sánh. `thenComparing` chỉ dùng khóa tiếp theo khi các khóa trước bằng nhau.

Ví dụ sắp xếp lịch hẹn theo thời điểm rồi theo tên:

```java
Comparator<Appointment> order = Comparator
        .comparing(Appointment::start)
        .thenComparing(Appointment::title);
```

Để comparator này hợp lệ và có hành vi rõ ràng, các getter nên trả về giá trị không null hoặc bạn phải đặt chính sách xử lý null. Nếu `start` là `Instant`, khóa chính là thứ tự timeline. Nếu `start` là `LocalDateTime`, nó là thứ tự giờ địa phương.

Các tiêu chí phụ nên phản ánh nghiệp vụ. Không nên thêm trường không liên quan chỉ để “làm comparator phức tạp hơn”. Một tiêu chí như ID thường hữu ích khi cần đầu ra tái lập nếu nhiều sự kiện có cùng thời điểm.

## 5. Ví dụ Java hoàn chỉnh: sắp xếp lịch hẹn theo Instant, rồi ID

Tạo tệp `AppointmentSortingDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class AppointmentSortingDemo {
    record Appointment(String id, String title, Instant start) {}

    public static void main(String[] args) {
        List<Appointment> appointments = new ArrayList<>(List.of(
                new Appointment("A3", "Review", Instant.parse("2025-01-15T04:00:00Z")),
                new Appointment("A2", "Planning", Instant.parse("2025-01-15T03:30:00Z")),
                new Appointment("A1", "Stand-up", Instant.parse("2025-01-15T03:30:00Z"))
        ));

        Comparator<Appointment> order = Comparator
                .comparing(Appointment::start)
                .thenComparing(Appointment::id);

        appointments.sort(order);

        for (Appointment appointment : appointments) {
            System.out.println(appointment.id() + " | "
                    + appointment.start() + " | " + appointment.title());
        }
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac AppointmentSortingDemo.java
java AppointmentSortingDemo
```

Đầu ra:

```text
A1 | 2025-01-15T03:30:00Z | Stand-up
A2 | 2025-01-15T03:30:00Z | Planning
A3 | 2025-01-15T04:00:00Z | Review
```

Hai sự kiện A1 và A2 cùng thời điểm; khóa phụ ID đưa A1 đứng trước A2. `List.sort` sắp xếp danh sách tại chỗ. Nếu không muốn thay đổi danh sách gốc, sao chép danh sách hoặc dùng stream và thu kết quả thành danh sách mới.

## 6. Sắp xếp OffsetDateTime theo timeline hay theo biểu diễn?

Giả sử hai timestamp được ghi theo offset khác nhau:

```java
OffsetDateTime tokyo =
        OffsetDateTime.parse("2025-01-15T12:30+09:00");
OffsetDateTime utc =
        OffsetDateTime.parse("2025-01-15T03:30Z");

System.out.println(tokyo.toInstant().equals(utc.toInstant()));
System.out.println(Comparator.comparing(OffsetDateTime::toInstant)
        .compare(tokyo, utc));
```

Kết quả:

```text
true
0
```

Với comparator timeline, chúng bằng nhau vì cùng `Instant`. Điều đó hữu ích khi sắp xếp sự kiện thực theo thời gian, dù cách lưu offset khác nhau.

Nếu cần một thứ tự duy nhất cho từng đối tượng biểu diễn, hãy thêm khóa phụ tường minh, ví dụ local date-time rồi offset:

```java
Comparator<OffsetDateTime> deterministicRepresentationOrder =
        Comparator.comparing(OffsetDateTime::toInstant)
                .thenComparing(OffsetDateTime::toLocalDateTime)
                .thenComparing(OffsetDateTime::getOffset);
```

Không nên vô tình dùng thứ tự biểu diễn thay cho thứ tự timeline. Hãy đặt tên comparator theo ý nghĩa của nó, chẳng hạn `timelineOrder` hoặc `representationOrder`, để tránh dùng nhầm ở nơi khác.

## 7. Sắp xếp LocalDateTime khác với sắp xếp Instant

`LocalDateTime` chưa xác định được một thời điểm thực bởi nó không có offset/zone. Nếu các bản ghi được lấy từ một khu vực duy nhất và cần xếp lịch theo giờ địa phương, sort trực tiếp `LocalDateTime` thường phù hợp.

Nếu dữ liệu chứa các sự kiện từ nhiều vùng, cần chuyển đổi chúng dựa trên `ZoneId` thích hợp để thu được `Instant` rồi mới sort theo timeline. Không nên tự gắn `ZoneId.systemDefault()` cho mọi local value nếu nguồn thực tế thuộc vùng khác.

Điều này đặc biệt quan trọng khi DST tạo ra giờ địa phương không tồn tại hoặc lặp hai lần. Một local value như 01:30 trong vùng có overlap không thể xác định duy nhất thứ tự trên timeline nếu thiếu offset/lựa chọn xử lý. Trước khi tạo `ZonedDateTime`, hệ thống lập lịch có thể phải kiểm tra `ZoneRules.getValidOffsets(local)` và yêu cầu chính sách cụ thể.

## 8. Thứ tự đảo ngược

`reversed()` tạo comparator với thứ tự đảo ngược. Có thể dùng để lấy sự kiện mới nhất trước:

```java
Comparator<Event> newestFirst =
        Comparator.comparing(Event::occurredAt).reversed();
```

Nếu cần giữ tiêu chí phụ tăng dần trong khi thời gian giảm dần, đặt `reversed()` đúng phần comparator cần đảo. Ví dụ:

```java
Comparator<Event> newestThenId =
        Comparator.comparing(Event::occurredAt)
                .reversed()
                .thenComparing(Event::id);
```

Ở đây thời gian giảm dần, còn ID tăng dần cho các sự kiện cùng timestamp. Nếu viết `Comparator.comparing(Event::occurredAt).thenComparing(Event::id).reversed()`, toàn bộ tổ hợp sẽ bị đảo, bao gồm cả thứ tự ID. Vị trí của `reversed()` làm thay đổi ý nghĩa.

## 9. Xử lý null rõ ràng

`Comparator.comparing` thường giả định khóa được trích xuất có thể so sánh và không null. Nếu dữ liệu có thể thiếu thời điểm, khai báo rõ nó đứng trước hay sau:

```java
Comparator<Appointment> nullStartsLast = Comparator
        .comparing(
                Appointment::start,
                Comparator.nullsLast(Comparator.naturalOrder()))
        .thenComparing(Appointment::id);
```

Đoạn này giả sử getter `start` có thể trả về `Instant` null. `nullsLast` đưa bản ghi thiếu thời gian về cuối; `nullsFirst` làm ngược lại. Nếu bản thân đối tượng cần sort có thể null, cần chính sách khác ở cấp đối tượng, ví dụ `Comparator.nullsLast(order)`.

Không nên thay null bằng `Instant.now()` chỉ để tránh lỗi sort. Việc đó bịa ra một thời điểm, khiến bản ghi có thể lọt vào vị trí sai và làm kết quả không tái lập. Tùy nghiệp vụ, hãy từ chối dữ liệu, để null theo quy tắc đã định, hoặc biểu diễn trạng thái “chưa có lịch” riêng.

## 10. sort() thay đổi danh sách hay tạo danh sách mới?

`List.sort(comparator)` sắp xếp danh sách đang có. Nếu người gọi vẫn đang dùng tham chiếu đó, thứ tự phần tử sẽ thay đổi. `Stream.sorted(comparator)` tạo một stream được sắp xếp; nó không tự sửa nguồn, nhưng kết quả cuối phụ thuộc thao tác terminal và kiểu collection bạn tạo.

```java
List<Instant> source = List.of(
        Instant.parse("2025-01-15T04:00:00Z"),
        Instant.parse("2025-01-15T03:00:00Z"));

List<Instant> sorted = source.stream()
        .sorted()
        .toList();

System.out.println(source.get(0));
System.out.println(sorted.get(0));
```

Kết quả:

```text
2025-01-15T04:00:00Z
2025-01-15T03:00:00Z
```

Trong Java 17, `Stream.toList()` trả về danh sách không sửa đổi được. Vì vậy nếu cần sort tiếp trên kết quả, hãy tạo `new ArrayList<>(sorted)` trước khi gọi phương thức sửa danh sách. Với `Collections.sort(list, comparator)`, danh sách nguồn cũng bị sắp xếp tại chỗ.

## 11. Comparator phải nhất quán

Comparator nên đáp ứng hợp đồng: dấu của `compare(a, b)` phải đảo khi đổi thứ tự đối số; quan hệ phải bắc cầu; nếu comparator trả 0, việc so sánh với phần tử thứ ba cũng phải nhất quán. Một comparator có điều kiện tùy tiện hoặc dùng thời gian hiện tại làm khóa ngay trong lần so sánh có thể vi phạm tính ổn định và gây kết quả khó giải thích.

Không tạo comparator dùng giá trị thay đổi giữa các lần gọi, ví dụ:

```java
// Thiết kế xấu: "now" khác nhau qua các lần gọi.
Comparator<Event> unstable = Comparator.comparing(
        event -> Duration.between(event.occurredAt(), Instant.now()));
```

Nếu cần sắp xếp theo độ tuổi của sự kiện tại một mốc tham chiếu, lấy mốc đó một lần rồi đóng vai trò khóa bất biến hoặc so sánh timestamp trực tiếp. `now` thay đổi trong lúc sort có thể làm quan hệ so sánh không nhất quán.

Ngoài ra, tránh trừ hai timestamp hoặc epoch milli để lấy comparator bằng `(int) (a - b)`: phép trừ có thể tràn và việc ép sang `int` mất phần lớn thông tin. Hãy dùng `compareTo`, `Comparator.comparing` hoặc `Long.compare(a, b)`.

## 12. Hướng dẫn chọn comparator

| Mục đích | Cách tiếp cận |
|---|---|
| Ngày lịch tăng dần | `Comparator.naturalOrder()` hoặc `Comparator.comparing(Event::date)` |
| Ngày giờ địa phương tăng dần trong cùng ngữ cảnh | `Comparator.comparing(Event::localDateTime)` |
| Sự kiện toàn cầu theo thời điểm | `Comparator.comparing(Event::instant)` |
| OffsetDateTime/ZonedDateTime theo timeline | `Comparator.comparing(value -> value.toInstant())` |
| Thời gian trước, ID tăng dần khi bằng | `comparing(time).thenComparing(id)` |
| Mới nhất trước | `comparing(time).reversed()` |
| Thời gian null xuống cuối | `Comparator.nullsLast(Comparator.naturalOrder())` làm comparator cho khóa |
| Giữ bản gốc nguyên thứ tự | Dùng stream `sorted` hoặc sao chép rồi sort |
| Cần phân biệt cách biểu diễn cùng Instant | Thêm local date-time/offset/zone như khóa phụ có chủ đích |

## 13. Tự kiểm tra

**Câu 1.** Hai `OffsetDateTime` có offset khác nhưng cùng `toInstant()` nên xếp theo thứ tự timeline thế nào?

**Đáp án:** Comparator timeline trả 0 cho khóa thời gian. Nếu cần phân biệt hai cách biểu diễn thì thêm khóa phụ riêng.

**Câu 2.** `LocalDateTime` có thể dùng trực tiếp để sắp xếp sự kiện từ mọi múi giờ trên thế giới không?

**Đáp án:** Không. Nó chỉ chứa giờ địa phương, không xác định `Instant`; cần vùng/offset nguồn để chuyển sang timeline trước khi sort toàn cầu.

**Câu 3.** `reversed()` đặt sau `thenComparing(id)` có khác với đặt trước `thenComparing(id)` không?

**Đáp án:** Có. Đảo toàn comparator sẽ đảo cả thứ tự khóa phụ; đảo riêng khóa thời gian rồi nối khóa phụ sẽ giữ ID theo chiều tăng dần.

**Câu 4.** Khi trường thời gian có thể null, cách nào nói rõ null đứng cuối?

**Đáp án:** Dùng `Comparator.nullsLast(...)` làm comparator cho khóa, hoặc bọc toàn bộ comparator bằng `Comparator.nullsLast(order)` nếu chính đối tượng có thể null.

**Câu 5.** Tại sao không dùng `(int) (timeA - timeB)` làm comparator?

**Đáp án:** Phép trừ có thể tràn số và ép sang `int` mất dữ liệu, vi phạm thứ tự mong muốn. Dùng API so sánh chuẩn.

---

**Ghi nhớ:** Sắp xếp đúng bắt đầu bằng việc chọn đúng ý nghĩa thời gian. Dùng local order cho lịch địa phương, timeline order cho sự kiện có thời điểm tuyệt đối, và tiêu chí phụ tường minh cho các trường hợp bằng nhau, null hoặc cần thứ tự ổn định.