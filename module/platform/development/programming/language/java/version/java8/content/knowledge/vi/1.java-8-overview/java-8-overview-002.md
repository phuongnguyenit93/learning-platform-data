# Mối liên hệ giữa lambda, Stream, Optional và java.time

Bốn thành phần này giải quyết những vấn đề khác nhau nhưng phối hợp rất tốt trong Java hiện đại: **lambda diễn tả hành vi**, **Stream tổ chức chuỗi xử lý dữ liệu**, **Optional diễn tả kết quả có thể vắng mặt**, còn **java.time biểu diễn và tính toán thời gian bằng các kiểu rõ nghĩa, bất biến**. Chúng đều xuất hiện từ Java 8; một số cách nối chúng thuận tiện hơn đã được bổ sung ở các phiên bản Java sau đó và vẫn hữu ích khi viết ứng dụng hiện nay.

## 1. Nhìn đúng vai trò và ranh giới

| Thành phần | Câu hỏi nó giải quyết | Dùng ở đâu | Không nên hiểu thành |
| --- | --- | --- | --- |
| Lambda / method reference | “Thực hiện thao tác nào cho phần tử?” | Predicate, Function, Consumer, Comparator, Supplier | Một cơ chế tự động chạy song song hay làm code luôn nhanh hơn |
| Stream API | “Lọc, biến đổi, tổng hợp tập dữ liệu thế nào?” | Dữ liệu trong Collection, mảng, nguồn tạo Stream | Cấu trúc lưu trữ hoặc luồng I/O; một Stream dùng đi dùng lại |
| Optional<T> | “Có thể không tìm thấy một giá trị hợp lệ không?” | Giá trị trả về của thao tác tìm kiếm/biến đổi | Cách thay mọi biến, tham số và thuộc tính bằng Optional; cách hợp thức hóa null |
| java.time | “Một ngày, thời điểm, múi giờ, khoảng thời gian có ý nghĩa gì?” | Thời gian nghiệp vụ, timestamp, lịch, kiểm tra hạn | Chỉ là cách format chuỗi ngày tháng |

Một luồng xử lý điển hình:

~~~text
Nguồn đơn hàng
  -> stream()
  -> filter(order -> điều kiện theo Instant/java.time)
  -> map/flatMap(order -> kết quả Optional hợp lệ)
  -> map(order -> ngày hiển thị theo ZoneId)
  -> sorted()/collect/toList()
  -> findFirst() -> Optional kết quả đầu tiên
~~~

**Điểm cốt lõi:** Lambda là “hàm truyền vào”; Stream quyết định *khi nào và trên phần tử nào* gọi hàm; Optional thể hiện trường hợp không có kết quả mà không buộc trả về null; java.time cung cấp kiểu thời gian để những điều kiện đó có nghĩa đúng.

## 2. Lambda là mắt xích diễn tả thao tác

Java nhận lambda khi nơi nhận có **functional interface**: giao diện với đúng một phương thức trừu tượng (có thể có thêm default/static method). Ví dụ các giao diện chuẩn:

- `Predicate<Order>` nhận một `Order` và trả về `boolean`: rất phù hợp với `filter`.
- `Function<Order, String>` chuyển từ một kiểu sang kiểu khác: dùng trong `map`.
- `Consumer<Order>` nhận giá trị và thực hiện hành động: gặp trong `forEach`.
- `Supplier<T>` tạo giá trị khi cần: hữu ích với `orElseGet`, hoặc nguồn dữ liệu lười.
- `Comparator<T>` định nghĩa cách so sánh: dùng cho `sorted`.

Cú pháp và method reference là hai cách biểu đạt cùng hợp đồng hàm:

~~~java
List<String> names = Arrays.asList("Lan", "An", "Minh");

List<String> upper = names.stream()
    .filter(name -> name.length() >= 3)
    .map(String::toUpperCase)
    .sorted(String::compareTo)
    .collect(Collectors.toList());
~~~

Đoạn này là phần thân minh họa; trong tệp Java độc lập cần import `java.util.*` và `java.util.stream.*` và đặt nó trong một phương thức. `String::toUpperCase` tương đương lambda `s -> s.toUpperCase()` ở vị trí này. Lambda có thể tham chiếu biến ngoài nếu biến đó là `final` hoặc *effectively final* (không bị gán lại).

**Thói quen nên giữ:** Biểu thức trong pipeline nên dễ hiểu, ít tác dụng phụ và không tự sửa danh sách đang duyệt. Lambda không làm dữ liệu trở nên bất biến; nếu đồng thời cập nhật biến chia sẻ trong `parallelStream()` vẫn có race condition. Với logic lớn hoặc cần xử lý lỗi rõ ràng, đặt logic trong phương thức có tên rồi dùng method reference.

## 3. Stream kết nối các bước xử lý

Stream gồm **nguồn**, **thao tác trung gian** và **thao tác kết thúc**:

- Nguồn: `list.stream()`, `Arrays.stream(array)`, `Stream.of(...)`.
- Trung gian: `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`. Chúng thường **lazy**: khai báo pipeline chưa có nghĩa đã xử lý từng phần tử.
- Kết thúc: `toList`, `collect`, `count`, `reduce`, `findFirst`, `anyMatch`, `forEach`. Thao tác kết thúc kích hoạt việc đánh giá cần thiết; một số thao tác như `findFirst` có thể dừng sớm.

Không thể dùng lại cùng một đối tượng Stream sau terminal operation. Hãy gọi `source.stream()` lần nữa khi cần pipeline thứ hai. Không suy luận rằng mọi bước sẽ luôn được gọi đúng một lần trên mọi phần tử: tối ưu hóa và các terminal operation ngắn mạch có thể thay đổi số lần gọi. Tránh dùng `peek` để thực hiện thay đổi trạng thái nghiệp vụ; nó chủ yếu thích hợp để quan sát/debug với những giới hạn trên.

### `map` và `flatMap`

- `map(f)` biến **một phần tử thành một kết quả**: `Stream<Order> -> Stream<String>` khi `f` trả về String.
- `flatMap(f)` biến **một phần tử thành một Stream con rồi trải phẳng**: `Stream<Order> -> Stream<String>` khi `f` trả về `Stream<String>`. Phần tử không có kết quả có thể trả về `Stream.empty()`.
- Với kết quả kiểu `Optional<String>`, `Optional.stream()` (Java 9+) tạo Stream có **0 hoặc 1 phần tử**. Nhờ đó `stream.flatMap(o -> findValue(o).stream())` bỏ được giá trị vắng mặt mà không cần null hay gọi `get()`.

Nếu cần một danh sách kết quả trên Java 16+, `stream.toList()` trả về **List không sửa được**. Còn `collect(Collectors.toList())` có mặt từ Java 8 nhưng **không hứa rõ** loại List, khả năng sửa hoặc thread-safety. Nếu cần một `ArrayList` có thể sửa được, chọn rõ `collect(Collectors.toCollection(ArrayList::new))`.

Mặc định ưu tiên `stream()` tuần tự. `parallelStream()` chỉ nên chọn sau đo đạc với khối lượng phù hợp, phép toán độc lập, bộ gom đúng và hiểu rõ thứ tự cũng như chi phí phân chia công việc. Nó không phải cách tự động tăng tốc truy cập database hoặc HTTP.

## 4. Optional đặt ý nghĩa cho sự vắng mặt

`Optional<T>` là container có thể chứa một giá trị khác null hoặc không chứa gì. Ví dụ một phương thức `findFirst()` không tìm được đơn hàng thì trả về `Optional.empty()` thay vì buộc người gọi đoán null có ý nghĩa gì.

Những thao tác phổ biến:

| Phương thức | Ý nghĩa thực tế |
| --- | --- |
| `Optional.of(value)` | Bắt buộc value khác null, nếu null sẽ ném `NullPointerException` |
| `Optional.ofNullable(value)` | Giá trị null biến thành Optional rỗng |
| `map(f)` | Biến đổi giá trị có mặt; kết quả null của mapper trở thành rỗng |
| `filter(predicate)` | Giữ giá trị chỉ khi qua điều kiện |
| `flatMap(f)` | Ghép một phép biến đổi **đã trả về Optional**, tránh `Optional<Optional<T>>` |
| `orElse(defaultValue)` | Lấy giá trị hoặc phương án dự phòng; biểu thức đối số được tính trước lời gọi |
| `orElseGet(supplier)` | Chỉ tính phương án dự phòng khi Optional rỗng |
| `orElseThrow(...)` | Không có giá trị là lỗi nghiệp vụ cần báo rõ |
| `ifPresent(consumer)` | Thực hiện hành động khi có giá trị |
| `stream()` | Chuyển thành Stream 0 hoặc 1 phần tử (Java 9+) |

Ví dụ phân biệt `map` và `flatMap`:

~~~java
Optional<String> input = Optional.of("  Lan  ");
Optional<String> clean = input.map(String::trim);

Optional<String> fromLookup = input.flatMap(s ->
    s.trim().isEmpty() ? Optional.empty() : Optional.of(s.trim())
);
~~~

Với ứng dụng hiện nay, thường dùng Optional cho **giá trị trả về có thể thiếu** của API Java thông thường (ví dụ tìm kiếm). Tránh truyền `null` thay cho một đối tượng Optional; tránh lạm dụng Optional làm trường DTO/entity, tham số bắt buộc hay phần tử collection khi không có lý do rõ ràng về hợp đồng. Tránh `optional.get()` không có kiểm tra vì giá trị rỗng sẽ gây `NoSuchElementException`; ưu tiên `map`/`flatMap`, `orElseGet` hoặc `orElseThrow` theo ý nghĩa nghiệp vụ.

**Không đồng nhất “không có” với “xử lý thất bại”.** Không nên nuốt lỗi kết nối, quyền truy cập hoặc định dạng dữ liệu thành `Optional.empty()` nếu caller cần biết lỗi. Optional chỉ thể hiện vắng mặt hợp lệ, không thay một mô hình lỗi.

## 5. java.time làm dữ liệu thời gian chính xác về nghĩa

Các kiểu nên biết và vẫn dùng phổ biến:

| Kiểu | Nó biểu diễn | Ví dụ sử dụng |
| --- | --- | --- |
| `Instant` | Một thời điểm trên trục UTC | Timestamp sự kiện, lưu thời điểm tạo đơn |
| `LocalDate` | Ngày lịch, không có giờ/múi giờ | Ngày sinh, ngày hóa đơn tại địa phương |
| `LocalTime` | Giờ trong một ngày, không có múi giờ | Giờ mở cửa |
| `LocalDateTime` | Ngày + giờ địa phương, **không xác định một thời điểm toàn cầu** | Lịch hẹn trước khi gắn vùng thời gian |
| `ZonedDateTime` | Ngày giờ gắn với `ZoneId` và quy tắc vùng | Lịch họp ở `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` |
| `OffsetDateTime` | Ngày giờ với độ lệch UTC cụ thể | Dữ liệu API mang offset |
| `Duration` | Khoảng thời gian theo giây/nano | Timeout, thời gian xử lý |
| `Period` | Khoảng lịch theo năm/tháng/ngày | Tăng ngày/tháng hoặc tính kỳ lịch |
| `Clock` | Nguồn thời gian có thể thay thế | Kiểm thử logic “hiện tại” một cách xác định |

Đối tượng `java.time` cơ bản là **bất biến**: `date.plusDays(1)` trả về giá trị mới, không sửa `date` cũ. Bởi vậy chúng phù hợp với phép biến đổi trong Stream và dữ liệu nhiều luồng hơn các đối tượng lịch mutable kiểu cũ.

### Múi giờ là dữ liệu nghiệp vụ

Giá trị `Instant.parse("2026-10-31T17:00:00Z")` là **2026-11-01 00:00** ở `Asia/Ho_Chi_Minh`. Lọc “từ ngày 1/11” theo giờ Việt Nam phải chuyển **đầu ngày tại múi giờ nghiệp vụ** thành Instant để so với timestamp, không so sánh tùy tiện chuỗi ngày hoặc dùng `LocalDateTime` thiếu zone.

Mẫu đúng:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate fromDay = LocalDate.of(2026, 11, 1);
Instant inclusiveStart = fromDay.atStartOfDay(businessZone).toInstant();

boolean matches = !eventInstant.isBefore(inclusiveStart); // eventInstant: Instant
LocalDate displayDate = eventInstant.atZone(businessZone).toLocalDate();
~~~

Đoạn trên là minh họa bên trong một phương thức, giả sử `eventInstant` đã được khai báo. Dùng `ZoneId` vùng (ví dụ `Europe/Paris`) khi cần quy tắc giờ mùa hè và thay đổi lịch sử; offset cố định như `+01:00` không mang đủ quy tắc theo ngày. Ở vùng có chuyển giờ, một `LocalDateTime` có thể rơi vào khoảng giờ không tồn tại hoặc bị lặp; cần chính sách xử lý DST khi chuyển từ giờ địa phương sang thời điểm toàn cầu.

Dùng `DateTimeFormatter` bất biến để parse/format khi trao đổi với người dùng hoặc API; chọn ISO 8601 khi phù hợp. Dùng `Clock` tiêm vào logic cần “bây giờ” để kiểm thử ổn định, ví dụ `Instant.now(clock)` hoặc `LocalDate.now(clock)`. Không gọi `now()` rải rác rồi mong nhiều lần đọc sẽ có cùng một thời điểm.

## 6. Ví dụ tích hợp đầy đủ: lọc đơn hàng theo ngày, chuẩn hóa liên hệ, chọn kết quả

Tình huống: nguồn đơn hàng có timestamp UTC, email liên hệ có thể thiếu và số tiền tính bằng cents. Cần lấy đơn từ **00:00 ngày 01/11/2026 theo giờ Việt Nam**, tối thiểu 10.000 cents, chỉ giữ dòng có email sau khi trim, chuyển sang nhãn “email | ngày địa phương”, sắp xếp và lấy nhãn đầu tiên nếu tồn tại.

Ví dụ chạy được với **JDK 17+**, dùng các API cốt lõi từ Java 8 cộng `Optional.stream()` (Java 9) và `Stream.toList()` (Java 16).

Tệp **Java8PipelineDemo.java**:

~~~java
import java.time.*;
import java.util.*;

public class Java8PipelineDemo {
    static final class Order {
        final String email;
        final Instant placedAt;
        final long cents;

        Order(String email, Instant placedAt, long cents) {
            this.email = email;
            this.placedAt = placedAt;
            this.cents = cents;
        }
    }

    static Optional<String> normalizedEmail(String raw) {
        return Optional.ofNullable(raw)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .map(s -> s.toLowerCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate fromDate = LocalDate.of(2026, 11, 1);
        Instant cutoff = fromDate.atStartOfDay(zone).toInstant();

        List<Order> orders = Arrays.asList(
            new Order(" AN@example.com ",
                    Instant.parse("2026-10-31T17:00:00Z"), 12_000),
            new Order("mai@example.com",
                    Instant.parse("2026-11-02T02:00:00Z"), 9_000),
            new Order(" MAI@example.com ",
                    Instant.parse("2026-11-03T03:00:00Z"), 20_000),
            new Order(null,
                    Instant.parse("2026-11-04T04:00:00Z"), 30_000)
        );

        List<String> result = orders.stream()
                .filter(o -> !o.placedAt.isBefore(cutoff))
                .filter(o -> o.cents >= 10_000)
                .flatMap(o -> normalizedEmail(o.email)
                        .map(email -> email + " | "
                                + o.placedAt.atZone(zone).toLocalDate())
                        .stream())
                .sorted()
                .toList();

        System.out.println(result);
        System.out.println(
                result.stream().findFirst().orElse("No results")
        );
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 Java8PipelineDemo.java
java Java8PipelineDemo
~~~

Kết quả đúng:

~~~text
[an@example.com | 2026-11-01, mai@example.com | 2026-11-03]
an@example.com | 2026-11-01
~~~

**Giải thích từng mắt xích:**

1. `Instant` giữ thời điểm thực của từng đơn; `fromDate.atStartOfDay(zone).toInstant()` chuyển ranh giới ngày nghiệp vụ thành thời điểm so sánh được.
2. Hai lambda `filter` biểu đạt điều kiện thời gian và số tiền. Dòng đầu tiên được giữ dù timestamp có ngày UTC là 31/10, vì tại Việt Nam đó đã là 1/11.
3. `normalizedEmail` trả về `Optional<String>`: null hoặc chuỗi trống thành rỗng; email hợp lệ theo **quy tắc tối thiểu của ví dụ** thành chữ thường sau trim. Trong hệ thống thật, việc xác thực email và chính sách chuẩn hóa định danh cần định nghĩa riêng; không suy ra rằng chỉ trim/lowercase là đã kiểm chứng địa chỉ.
4. `map` bên trong Optional tạo nhãn từ dữ liệu có mặt; `Optional.stream()` chuyển nhãn thành Stream 1 phần tử hoặc 0 phần tử. `flatMap` bên ngoài kết hợp chúng thành luồng nhãn, không tạo null hay `Optional<Optional<String>>`.
5. `sorted` định thứ tự kết quả; `toList` thực thi pipeline và trả danh sách không sửa được.
6. `findFirst` trên danh sách kết quả có thể trả Optional rỗng; `orElse("No results")` cung cấp thông báo khi không có dòng nào.

**Tương thích phiên bản:** Nếu bắt buộc biên dịch bằng Java 8, dùng cách gom tương đương ở các phần phù hợp: thay `.toList()` bằng `.collect(Collectors.toList())` (thêm import `java.util.stream.Collectors`) và xử lý Optional trong pipeline bằng một giải pháp Java 8 rõ ràng, ví dụ một hàm trả Stream rỗng/1 phần tử với `optional.map(Stream::of).orElseGet(Stream::empty)` (thêm import `java.util.stream.Stream`). Với dự án JDK 17+ đang phát triển, `Optional.stream()` và `Stream.toList()` là cách viết gọn, hiện hành; không cần bỏ chúng chỉ vì module có tiêu đề Java 8.

## 7. Khi thiết kế ứng dụng thực tế

**Tách ba quyết định:** (a) điều kiện nghiệp vụ dùng kiểu thời gian nào, (b) giá trị nào có thể vắng mặt và cách xử lý, (c) phép biến đổi nào nằm trong pipeline. Ví dụ hàm tìm đơn mới nhất có thể trả `Optional<Order>`, còn thuộc tính `placedAt` của một Order hợp lệ nên có hợp đồng khác null rõ ràng ngay từ lúc tạo.

**Tránh gọi dịch vụ cho từng phần tử Stream một cách vô thức.** Một pipeline `map(order -> repository.find... )` có thể gây N+1 truy vấn hoặc nhiều lời gọi mạng. Batching, phân trang hoặc truy vấn trực tiếp có thể phù hợp hơn. Đừng đưa Stream vào mọi vòng lặp: vòng `for` thường rõ hơn khi cần cập nhật trạng thái, break phức tạp hoặc xử lý ngoại lệ theo từng bản ghi.

**Phân biệt vắng mặt và dữ liệu lỗi.** Nếu thiếu email là tình huống được phép, Optional rỗng có thể phù hợp. Nếu timestamp sai định dạng, thiếu bắt buộc hoặc đến từ nguồn không tin cậy, parse/validate riêng và trả thông tin lỗi có cấu trúc; đừng lặng lẽ bỏ bản ghi chỉ để pipeline chạy.

**Chú ý thứ tự và chi phí.** Trên Stream có thứ tự, `findFirst()` quan tâm phần tử đầu tiên trong encounter order, còn `findAny()` có thể chọn phần tử bất kỳ. `sorted` là thao tác có thể tốn bộ nhớ, đặc biệt trước `limit`. Với tập rất lớn, cân nhắc truy vấn giới hạn sớm, thuật toán thống kê theo bước hoặc xử lý streaming phù hợp thay vì luôn tạo List đầy đủ.

**Kiểm thử thời gian có kiểm soát.** Ví dụ kiểm tra một thời điểm cố định:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-05T00:00:00Z"),
        ZoneId.of("UTC")
);
Instant now = Instant.now(clock); // luôn là 2026-11-05T00:00:00Z
~~~

Đây là mảnh mã có thể đặt trong một phương thức (import `java.time.*`). Trong nghiệp vụ thực, truyền `Clock` qua constructor/tham số giúp viết test cho hạn chót, múi giờ và ranh giới ngày mà không phụ thuộc đồng hồ máy chạy test.

## 8. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách phù hợp hơn |
| --- | --- | --- |
| Gọi `optional.get()` ngay sau `findFirst()` | Không có phần tử sẽ ném exception | `orElse`/`orElseGet`, `orElseThrow` có thông điệp, hoặc xử lý Optional tiếp |
| Lồng `Optional<Optional<T>>` do `map` | Mapper đã trả Optional, cấu trúc bị lồng | Dùng `Optional.flatMap` |
| Đưa `Optional<T>` trực tiếp vào `Stream<T>` | Stream cần phần tử T, Optional còn là container | `flatMap(Optional::stream)` từ Java 9+ |
| Biến đổi thứ tự rồi duyệt một Stream cũ lần hai | Stream chỉ được tiêu thụ một lần | Tạo pipeline mới từ nguồn |
| Dùng `LocalDateTime` như timestamp UTC | Không có offset/zone nên chưa định danh một Instant | Lưu `Instant`; đổi sang `ZonedDateTime` tại ranh giới hiển thị/nghiệp vụ |
| Dùng `ZoneId.systemDefault()` tùy tiện | Kết quả phụ thuộc môi trường server | Chọn và truyền `ZoneId` nghiệp vụ rõ ràng |
| Dùng `orElse(expensiveCall())` | Đối số được tính ngay cả khi Optional có giá trị | `orElseGet(() -> expensiveCall())` khi fallback thực sự tốn kém |
| Ghi/sửa shared list trong `parallelStream()` | Không đảm bảo thread safety, thứ tự và tính đúng | Biến đổi thuần, collector phù hợp; chỉ parallel sau khi đo |
| Giả định `Stream.toList()` trả List sửa được | List trả về không cho mutate | Dùng `Collectors.toCollection(ArrayList::new)` khi cần sửa |
| Dùng `peek` để bắt buộc ghi dữ liệu | Side effect có thể không chạy như mong đợi | Thực hiện thay đổi bằng một bước riêng có kiểm soát |

## 9. Tự kiểm tra hiểu biết

1. Tại sao điều kiện “đơn từ ngày 1/11 theo giờ Việt Nam” cần `ZoneId` nếu timestamp nguồn là `Instant`? Hãy xét bản ghi `2026-10-31T17:00:00Z`.
2. Một hàm trả `Optional<String>` được gọi cho từng phần tử của Stream. Vì sao `flatMap(optional -> optional.stream())` gọn và an toàn hơn tạo null để lọc?
3. Khi nào chọn `map` thay `flatMap`? Hãy phân biệt mapper trả `String`, `Optional<String>` và `Stream<String>`.
4. Vì sao không thể tiêu thụ hai lần cùng một Stream? Nếu cần hai phép tổng hợp, bạn sẽ xử lý từ nguồn như thế nào?
5. Vì sao `LocalDateTime` của “09:00 ngày mai” chưa tương đương một `Instant` khi người dùng ở nhiều khu vực?
6. Hãy thay `findFirst().orElse("No results")` bằng chính sách “không có đơn là lỗi” và giải thích khi nào yêu cầu đó hợp lý.
7. Nếu cần List có thể thêm/xóa phần tử, vì sao `toList()` không phù hợp? Chọn collector nào?
8. Nếu chạy test kiểm tra hết hạn vào đúng nửa đêm, vì sao nên truyền `Clock` thay vì gọi trực tiếp `Instant.now()` ở nhiều nơi?

## Tài liệu API tham khảo

- Java SE 17 — `Stream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
- Java SE 17 — `Optional`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html
- Java SE 17 — `java.time`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html

Các API được nêu đều còn hữu dụng khi phát triển Java hiện đại. Điểm phân biệt phiên bản quan trọng cho bài này là: lambda, Stream, Optional và java.time bắt đầu từ Java 8; `Optional.stream()` bắt đầu từ Java 9; `Stream.toList()` bắt đầu từ Java 16.