# Phân biệt dữ liệu trong bộ nhớ với dữ liệu được lưu trữ lâu dài

> **Chương:** Định hướng  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Bối cảnh:** Hiểu nền tảng lưu trữ bền vững trong ứng dụng Java để lựa chọn mô hình dữ liệu, lược đồ, truy vấn, giao dịch, cơ chế phục hồi và cách vận hành phù hợp.

## 1. Vì sao cần phân biệt?

Giả sử một ứng dụng bán vé đang chạy và người dùng vừa đặt chỗ. Chương trình Java có thể lưu đơn đặt chỗ vào một đối tượng, một `HashMap` hoặc một biến `static`. Trong phiên làm việc hiện tại, giao diện vẫn hiển thị vé đã đặt. Nhưng khi server khởi động lại, những đối tượng ấy không còn trong JVM mới. Nếu ứng dụng không có nơi ghi nhận độc lập với tiến trình, lượt đặt vé sẽ biến mất.

Ngược lại, nếu ứng dụng ghi đơn đặt chỗ vào một kho dữ liệu bền vững và ghi thành công theo cơ chế đã thiết kế, lần chạy sau có thể đọc lại đơn hàng. Đây là sự khác biệt quan trọng giữa **trạng thái đang tồn tại trong bộ nhớ khi chương trình chạy** và **trạng thái được lưu giữ để truy xuất trong tương lai**.

Sau bài này, người học có thể:

1. Phân biệt vòng đời, mục đích, tốc độ truy cập và rủi ro mất dữ liệu của hai loại trạng thái.
2. Giải thích vì sao object Java, `static`, `HashMap`, cache và cả Java serialization không tự động bảo đảm persistence.
3. Quan sát một ví dụ Java có kết quả khác nhau giữa hai lần khởi động chương trình.
4. Nhận diện khác biệt giữa dữ liệu đã được ghi, giao dịch đã xác nhận, dữ liệu được nhân bản và dữ liệu đã sao lưu.
5. Quyết định thông tin nào nên để trong RAM, thông tin nào phải lưu bền vững, và cần xác nhận kết quả ghi vào lúc nào.

## 2. Hai loại dữ liệu, hai vòng đời

### 2.1. Dữ liệu trong bộ nhớ (*in-memory state*)

Trong ứng dụng Java, dữ liệu thường bắt đầu trong bộ nhớ của tiến trình:

~~~java
Map<String, Integer> remainingSeats = new HashMap<>();
remainingSeats.put("EVENT-42", 15);

remainingSeats.put("EVENT-42", 14);
System.out.println(remainingSeats.get("EVENT-42")); // 14
~~~

Trong đoạn mã này, `remainingSeats` là một đối tượng được quản lý trong vòng đời của JVM. Các lệnh tiếp theo có thể đọc giá trị `14`, nhưng chương trình chưa thể hiện một thao tác ghi dữ liệu ra kho bền vững.

Các đặc điểm thường gặp:

- **Vòng đời:** gắn với tiến trình, đối tượng hoặc phiên xử lý đang hoạt động; JVM mới không mặc nhiên khôi phục object của JVM cũ.
- **Tốc độ:** truy cập RAM thường có độ trễ thấp; không cần round trip đến dịch vụ dữ liệu khi truy cập một biến cục bộ.
- **Khả năng chia sẻ:** object Java thông thường chỉ nằm trong không gian địa chỉ tiến trình hiện tại; hai instance ứng dụng không tự chia sẻ cùng một `HashMap`.
- **Tính bền:** dữ liệu chưa được ghi ra ngoài có thể mất khi JVM dừng, bị kill, máy tính restart hoặc hết điện.
- **Quản lý bộ nhớ:** garbage collector có thể thu hồi object không còn truy cập được; GC không phải cơ chế ghi và khôi phục dữ liệu nghiệp vụ.

Điều này **không có nghĩa** dữ liệu trong RAM là không quan trọng. RAM thích hợp cho kết quả tính toán trung gian, trạng thái một request, cache có thể dựng lại và các phép biến đổi trước khi lưu.

### 2.2. Dữ liệu được lưu trữ lâu dài (*persistent state*)

Dữ liệu **persistent** là dữ liệu đã được ghi vào một hệ thống lưu trữ mà ứng dụng có thể truy xuất lại sau khi vòng đời thao tác hoặc tiến trình tạo ra nó kết thúc. Nơi lưu trữ có thể là:

- Tệp trên hệ thống tệp hoặc dịch vụ lưu trữ có cơ chế ghi bền.
- Cơ sở dữ liệu quan hệ hay cơ sở dữ liệu tài liệu.
- Kho khóa–giá trị có cấu hình lưu bền.
- Kho đối tượng, nhật ký sự kiện hoặc hệ thống lưu trữ chuyên dụng khác.

Ví dụ một đơn đặt vé cần có `booking_id`, `event_id`, `seat_id`, `customer_id`, `status` và thời điểm tạo. Các giá trị này nên được lưu theo ràng buộc nghiệp vụ, để lần truy vấn tiếp theo có thể xác định **chỗ đã được đặt hay chưa**.

Persistence được xác định bằng **hành vi và cam kết lưu giữ**, không chỉ bằng tên công nghệ. Một database chạy hoàn toàn trong RAM mà không có cơ chế ghi bền có thể mất dữ liệu khi dịch vụ dừng. Ngược lại, một tệp được ghi đúng cách cũng có thể lưu giữ trạng thái sau khi JVM thoát.

### 2.3. Bảng so sánh

| Tiêu chí | Dữ liệu trong bộ nhớ ứng dụng | Dữ liệu lưu trữ bền vững |
| --- | --- | --- |
| Ví dụ | Biến cục bộ, `HashMap`, object trên heap | Hàng trong database, nội dung tệp, đối tượng đã lưu |
| Vòng đời | Thường không vượt quá tiến trình chứa dữ liệu | Có thể vượt qua nhiều lần khởi động của ứng dụng |
| Khi JVM dừng | Object trong JVM không còn | Có thể truy xuất lại từ nơi lưu |
| Khi một request kết thúc | Có thể được giữ lại nếu còn tham chiếu, nhưng không được bảo đảm | Dữ liệu đã ghi không phụ thuộc vào request cũ |
| Truy cập | Thường nhanh, trực tiếp trong tiến trình | Có thêm chi phí I/O, giao thức, truy vấn hoặc mạng |
| Chia sẻ giữa nhiều instance | Cần một cơ chế chia sẻ/đồng bộ riêng | Có thể dùng một nguồn dữ liệu chung, theo quyền truy cập |
| Kiểm soát đồng thời | Cần bảo vệ các thao tác giữa thread; `HashMap` không an toàn cho cập nhật đồng thời | Cần giao dịch, ràng buộc, khóa hoặc kiểm soát phiên bản giữa các tác nhân ghi |
| Khả năng phục hồi | Thường tính toán hoặc nạp lại từ nguồn gốc | Phụ thuộc độ bền của thao tác ghi, hạ tầng và kế hoạch khôi phục |
| Mục tiêu chính | Tính toán và xử lý đang diễn ra | Lưu giữ sự thật nghiệp vụ qua thời gian |

Hai loại trạng thái **phối hợp với nhau**. Ứng dụng đọc dữ liệu bền vững vào RAM để xử lý, rồi ghi những thay đổi cần giữ trở lại nơi lưu. Một object vừa được tải từ database vẫn là object trong RAM; thay đổi field của nó **không nhất thiết** đã trở thành thay đổi bền vững.

## 3. Vòng đời của dữ liệu qua các sự kiện

Hãy theo dõi một bản ghi đặt vé:

~~~mermaid
flowchart TD
    A["Tạo đối tượng Booking trong JVM"] --> B{"Đã ghi ra kho lưu trữ?"}
    B -- "Chưa" --> C["Chỉ tồn tại trong trạng thái ứng dụng"]
    C --> D["JVM dừng / object bị giải phóng"]
    D --> E["Không còn bản ghi để nạp lại"]
    B -- "Có" --> F["Kho lưu trữ xử lý thao tác ghi"]
    F --> G{"Có xác nhận thành công theo hợp đồng ghi?"}
    G -- "Chưa hoặc không rõ" --> H["Kiểm tra lại trạng thái, xử lý lỗi hoặc retry an toàn"]
    G -- "Có" --> I["Đọc lại bằng ứng dụng hoặc phiên chạy khác"]
~~~

Sơ đồ nhấn mạnh một ranh giới: **thay đổi trạng thái trong RAM** và **xác nhận lưu dữ liệu** là hai sự kiện khác nhau.

| Sự kiện | Chỉ có object Java | Đã commit vào database giao dịch được cấu hình lưu bền |
| --- | --- | --- |
| Phương thức hiện tại kết thúc | Có thể còn nếu object vẫn được giữ tham chiếu | Bản ghi vẫn có thể được truy vấn |
| JVM khởi động lại | Object cũ không được giữ nguyên | Ứng dụng mới có thể đọc lại bản ghi |
| Một instance ứng dụng khác xử lý request | Không thấy object chỉ thuộc instance đầu tiên | Có thể đọc qua dịch vụ dữ liệu chung |
| Mất điện hoặc hỏng thiết bị | Trạng thái chỉ trong RAM thường mất | Phụ thuộc cam kết lưu bền, bản sao và tình trạng thiết bị |
| Xóa nhầm bản ghi đã lưu | Không liên quan | Dữ liệu có thể mất hoặc bị đồng bộ xóa; cần cơ chế phục hồi riêng |

Không nên hiểu cột bên phải là lời bảo đảm tuyệt đối. **Commit** có nghĩa theo cam kết của hệ quản trị và cấu hình cụ thể; dữ liệu có thể vẫn gặp rủi ro khi ổ đĩa hỏng, cấu hình durability yếu, sao lưu không hoạt động hoặc có thao tác sai từ người vận hành.

## 4. Thí nghiệm Java: chạy hai lần để thấy sự khác biệt

Ví dụ dưới đây dùng **biến `static` trong RAM** và **một tệp trên đĩa** để lưu hai bộ đếm. Mục đích là quan sát vòng đời dữ liệu; đoạn mã dùng một tiến trình, một người ghi và không thay thế hệ thống lưu trữ giao dịch.

Tạo tệp `VisitCounterDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class VisitCounterDemo {
    private static int visitsInMemory = 0;

    public static void main(String[] args) throws IOException {
        Path file = Path.of("data", "visits.txt");
        Files.createDirectories(file.getParent());

        long visitsOnDisk = Files.exists(file)
                ? Long.parseLong(
                        Files.readString(file, StandardCharsets.UTF_8).trim())
                : 0;

        visitsInMemory++;
        visitsOnDisk++;

        Files.writeString(
                file,
                Long.toString(visitsOnDisk),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);

        System.out.printf(
                "Trong JVM: %d | Doc tu tep va tang: %d%n",
                visitsInMemory,
                visitsOnDisk);
    }
}
~~~

Biên dịch và chạy hai lần trong cùng thư mục làm việc:

~~~text
javac VisitCounterDemo.java
java VisitCounterDemo
Trong JVM: 1 | Doc tu tep va tang: 1

java VisitCounterDemo
Trong JVM: 1 | Doc tu tep va tang: 2
~~~

**Giải thích:**

1. Mỗi lệnh `java VisitCounterDemo` tạo một JVM mới; biến `visitsInMemory` lại bắt đầu bằng `0`, rồi tăng thành `1`.
2. Lần chạy đầu tạo `data/visits.txt` chứa `1`.
3. Lần chạy thứ hai đọc `1` từ tệp, tăng thành `2` rồi ghi trở lại tệp.
4. Nếu chạy từ thư mục khác, đường dẫn tương đối `data/visits.txt` trỏ tới vị trí khác; kết quả có thể bắt đầu lại.

**Giới hạn quan trọng của ví dụ:** `TRUNCATE_EXISTING` có thể cắt nội dung tệp trước khi ghi giá trị mới. Nếu tiến trình chết đúng lúc ghi, tệp có thể rỗng hoặc không đầy đủ. Nếu hai tiến trình cùng đọc `2` rồi cùng ghi `3`, một lượt tăng bị mất. Việc `Files.writeString` hoàn tất cũng chưa tự nó định nghĩa bảo đảm khi mất điện đột ngột. Vì vậy, với dữ liệu nghiệp vụ cần tính đúng đắn và nhiều người ghi, nên dùng cơ chế cập nhật nguyên tử/giao dịch và chính sách durability rõ ràng.

### Một thay đổi chỉ xảy ra trong RAM

Ngay cả khi đã đọc một bản ghi từ kho lưu trữ, việc sửa một object không nhất thiết làm database thay đổi:

~~~java
record TicketView(String bookingId, String status) {}

TicketView ticket = new TicketView("B-901", "HELD");
TicketView confirmed = new TicketView(ticket.bookingId(), "CONFIRMED");

// confirmed chỉ là object Java mới.
// Muốn lưu kết quả, phải gọi thao tác ghi được thiết kế rõ ràng
// (ví dụ repository.updateStatus(...)).
~~~

Với ORM như JPA, một entity đang được quản lý có thể được đồng bộ vào database thông qua cơ chế *dirty checking* và *flush*. Tuy nhiên, *flush* không đồng nghĩa giao dịch đã commit, và một thay đổi có thể bị rollback. Cần hiểu rõ ranh giới transaction thay vì chỉ dựa vào việc setter đã được gọi.

## 5. “Ở trong RAM” không đồng nghĩa “không bao giờ liên quan đến dữ liệu lưu”

Trên hệ thống thực tế, phân biệt hai kiểu dữ liệu theo **vòng đời và hợp đồng bảo đảm** đáng tin hơn phân loại máy móc theo vị trí phần cứng.

### 5.1. Hệ điều hành có bộ đệm I/O

Khi ứng dụng đọc tệp hoặc database đọc một trang dữ liệu, hệ điều hành có thể giữ nội dung trong **page cache** để lần truy cập sau nhanh hơn. Một lệnh ghi cũng có thể được đưa vào bộ đệm rồi mới được đẩy xuống thiết bị.

Như vậy, dữ liệu **đã được ứng dụng yêu cầu ghi** vẫn có thể tạm nằm trong RAM trên đường tới thiết bị lưu trữ. Ghi xong ở mức API không luôn tương đương với việc dữ liệu đã vượt qua mọi rủi ro khi mất điện. Các cơ chế như `fsync`, `FileChannel.force(...)` hoặc chế độ commit bền vững của database hỗ trợ kiểm soát điểm xác nhận ghi; mức bảo đảm cuối cùng còn tùy hệ điều hành, hệ thống tệp và thiết bị.

### 5.2. Một “in-memory database” có thể hoặc không thể bền vững

Tên gọi *in-memory* nói rằng RAM giữ vai trò chính trong xử lý dữ liệu, nhưng sản phẩm có thể có cơ chế ghi nhật ký hoặc snapshot để phục hồi. Tương tự, kho khóa–giá trị có thể có nhiều chế độ từ **không lưu bền**, **snapshot định kỳ**, đến **append-only log**.

Để đánh giá, cần đọc cụ thể: dữ liệu nào có thể được phục hồi, khi nào thao tác ghi được xác nhận, mất bao nhiêu dữ liệu khi dịch vụ hoặc thiết bị ngừng đột ngột, và khôi phục theo quy trình nào.

### 5.3. `static`, `transient` và serialization trong Java

Một số khái niệm dễ gây nhầm lẫn:

| Khái niệm | Ý nghĩa đúng |
| --- | --- |
| `static` | Field gắn với lớp trong JVM; **không** tự tồn tại sau khi JVM dừng |
| `transient` trong Java | Đánh dấu field không được lưu trong **cơ chế Java Object Serialization mặc định**; không phải một chế độ bảo đảm xóa khỏi mọi nơi lưu trữ |
| Serialization | Chuyển trạng thái đối tượng thành một dạng biểu diễn (byte, JSON…); cần thêm bước ghi bền mới tạo persistence |
| `@Transient` trong JPA | Chỉ định thuộc tính không tham gia ánh xạ persistence theo JPA; khác với vai trò của từ khóa `transient` trong Java serialization |
| Cache trong ứng dụng | Có thể chứa bản sao dữ liệu gốc; không nên coi là nguồn duy nhất nếu cache có thể bị xóa hoặc tái tạo |

Ví dụ, `new ObjectOutputStream(...)` có thể ghi byte biểu diễn một object xuống tệp. Nhưng thiết kế còn phải xử lý việc thay đổi cấu trúc lớp, phiên bản dữ liệu, đọc lỗi, bảo mật định dạng và độ bền của thao tác ghi. **Serialization là cách biểu diễn, còn persistence là cam kết lưu giữ và khôi phục.**

## 6. Khi nào nên lưu RAM, khi nào cần lưu bền?

Không phải mọi biến đều cần database. Việc lưu quá nhiều trạng thái trung gian làm tăng I/O, chi phí vận hành và độ phức tạp. Ngược lại, nếu đặt dữ liệu nghiệp vụ quan trọng trong RAM, ứng dụng có thể đánh mất sự thật cần bảo vệ.

| Dữ liệu | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Kết quả tính tổng của một giỏ hàng đang hiển thị | Tính trong RAM; tính lại khi dữ liệu đầu vào đổi | Là giá trị dẫn xuất, có thể tái tạo |
| Số lượng hàng đang có và những đơn đã được xác nhận | Lưu ở nguồn dữ liệu bền vững | Là trạng thái nghiệp vụ, cần giữ qua nhiều phiên |
| Danh sách sản phẩm vừa tìm kiếm | Cache trong RAM nếu chấp nhận dữ liệu cũ ngắn hạn | Có thể truy vấn lại từ nguồn dữ liệu gốc |
| Hồ sơ người dùng | Lưu bền, kiểm soát quyền truy cập | Cần giữ lâu dài và bảo vệ dữ liệu cá nhân |
| Tiến độ xử lý một batch quan trọng | Lưu checkpoint phù hợp | Cần tiếp tục sau restart và tránh làm lại sai |
| Trạng thái UI đang nhập nhưng chưa gửi | RAM phía client hoặc cơ chế draft theo yêu cầu | Vòng đời tùy trải nghiệm mong muốn; cần phân biệt “nháp” và “đã gửi” |
| Dữ liệu cấu hình cần giữ sau restart | Tệp cấu hình hoặc kho cấu hình bền vững | Cần tái sử dụng ở lần chạy sau |
| Kết quả đo thời gian của một request | RAM trong lúc đo; đẩy tới hệ thống quan sát nếu cần lưu lịch sử | Không phải mọi phép đo tạm thời đều cần persistence |

Trước khi quyết định, tự hỏi:

1. **Nguồn sự thật ở đâu?** Nếu object hiện tại mất, có thể tính lại từ dữ liệu đáng tin cậy nào?
2. **Cần tồn tại đến khi nào?** Chỉ trong request, trong phiên đăng nhập, qua restart, hay nhiều năm?
3. **Ai cần nhìn thấy?** Một thread, một JVM, nhiều instance hoặc hệ thống khác?
4. **Mất dữ liệu gây hậu quả gì?** Chỉ chậm hơn vài giây hay gây mất đơn, sai tiền, sai số lượng?
5. **Phải cập nhật nhất quán với dữ liệu nào khác?** Có cần giao dịch, ràng buộc hoặc kiểm soát đồng thời?
6. **Khi có sự cố, làm sao biết trạng thái cuối cùng?** Dùng khóa duy nhất, truy vấn lại, snapshot, nhật ký hay bản sao lưu?

## 7. Thiết kế ranh giới giữa bộ nhớ và persistence cho Java

Một hướng thiết kế là để mã nghiệp vụ thao tác với **hợp đồng lưu trữ** thay vì phụ thuộc vào việc dữ liệu được giữ trong `HashMap` hay database.

~~~java
import java.util.Optional;
import java.util.UUID;

record Booking(UUID id, String eventId, String seatId, String status) {}

interface BookingRepository {
    Optional<Booking> findById(UUID id);
    void save(Booking booking);
}

final class BookingService {
    private final BookingRepository repository;

    BookingService(BookingRepository repository) {
        this.repository = repository;
    }

    void confirm(UUID bookingId) {
        Booking current = repository.findById(bookingId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Khong tim thay booking"));

        repository.save(new Booking(
                current.id(),
                current.eventId(),
                current.seatId(),
                "CONFIRMED"));
    }
}
~~~

Đây là ví dụ **phân tách trách nhiệm**, chưa bao gồm kiểm tra quyền đặt chỗ, ngăn đặt trùng, quy tắc trạng thái hoặc giao dịch. Một triển khai repository giữ dữ liệu trong map có thể thích hợp cho thử nghiệm hay mô phỏng, nhưng không đạt yêu cầu lưu giữ xuyên tiến trình. Một triển khai JDBC/JPA có thể lưu và truy vấn từ database; đồng thời phải xác định giao dịch, lỗi, mức cô lập và ràng buộc.

### 7.1. Từ câu lệnh RAM sang cập nhật bền vững có kiểm soát

Hãy so sánh thao tác tăng bộ đếm:

~~~java
// Chỉ tác động đến bộ nhớ của tiến trình.
AtomicLong visits = new AtomicLong(0);
long current = visits.incrementAndGet();
~~~

`AtomicLong` cho phép tăng nguyên tử đối với các thread dùng **cùng đối tượng**, nhưng nó không làm giá trị sống qua restart và không đồng bộ sang JVM khác. Nếu bộ đếm là một thống kê nghiệp vụ cần lưu, một thao tác trên database có thể có dạng:

~~~sql
-- Minh họa trong một CSDL quan hệ có bảng counters(id, total).
UPDATE counters
SET total = total + 1
WHERE id = :counterId;
~~~

Lệnh SQL cập nhật dựa trên giá trị trong database; ứng dụng phải kiểm tra số hàng được cập nhật, xử lý giao dịch và xác nhận commit. Dấu `:counterId` biểu thị tham số do lớp truy cập dữ liệu truyền vào, không phải cú pháp SQL có thể chạy nguyên xi trong mọi công cụ. Khi thao tác được thực hiện bởi nhiều tiến trình, database áp dụng cơ chế đồng thời và giao dịch riêng, không dựa vào một `AtomicLong` của JVM.

**Quy tắc thực hành:** Dùng RAM để tính toán và giảm độ trễ khi phù hợp, nhưng đặt các **bất biến nghiệp vụ** và **quyết định ghi cuối cùng** tại ranh giới lưu trữ được bảo vệ đúng mức.

### 7.2. Bước chuyển object qua ranh giới lưu trữ

~~~mermaid
flowchart LR
    A["Request / Dữ liệu đầu vào"] --> B["Object Java trong RAM"]
    B --> C["Kiểm tra nghiệp vụ"]
    C --> D["Repository / DAO"]
    D --> E["Lệnh SQL / Giao thức lưu trữ"]
    E --> F[("Kho dữ liệu bền vững")]
    F --> G["Đọc / Khôi phục"]
    G --> H["Object Java mới trong lần chạy sau"]
~~~

Object tại điểm **H** được dựng lại từ dữ liệu đã lưu. Nó có thể chứa cùng thông tin nghiệp vụ với object tại **B**, nhưng không nhất thiết có cùng địa chỉ bộ nhớ hay cùng định danh object trong JVM. Nên dựa vào **khóa nghiệp vụ hoặc khóa dữ liệu** (chẳng hạn `bookingId`) để liên kết giữa các lần chạy, không dựa vào `System.identityHashCode(...)` hoặc địa chỉ object.

## 8. Dữ liệu đã “lưu” có bền đến mức nào?

Khả năng tồn tại sau restart của JVM chỉ là **mức yêu cầu đầu tiên**. Những sự cố khác đòi hỏi cơ chế khác:

| Điều cần chịu được | Cơ chế có thể cần | Điều cơ chế đó không tự giải quyết |
| --- | --- | --- |
| JVM dừng rồi chạy lại | Tệp lưu bền hoặc database độc lập với JVM | Chưa bảo đảm khi thiết bị lưu trữ hỏng |
| Thao tác đang ghi bị ngắt giữa chừng | Ghi nguyên tử, transaction, write-ahead logging | Không loại bỏ mọi lỗi lập trình nghiệp vụ |
| Nhiều phiên cùng thay đổi một bản ghi | Transaction, ràng buộc, khóa hoặc cập nhật có điều kiện | Không bảo đảm mọi mức cô lập có cùng hành vi |
| Máy chủ hoặc một nút database ngừng hoạt động | Failover/replication phù hợp | Xóa nhầm vẫn có thể lan qua các bản sao |
| Xóa nhầm hoặc lỗi ứng dụng lan rộng | Backup độc lập và khả năng phục hồi theo thời điểm | Không tự bảo đảm hệ thống sẵn sàng ngay lập tức |
| Lộ dữ liệu nhạy cảm | Kiểm soát quyền, mã hóa, quản lý bí mật và audit | Không tự sửa sai logic truy cập ở ứng dụng |

### 8.1. Ghi tệp và crash consistency

Đối với ghi tệp quan trọng, cách làm thường bao gồm ghi vào tệp tạm, đồng bộ dữ liệu xuống thiết bị bằng cơ chế thích hợp, đổi tên/thay thế tệp theo khả năng của hệ thống tệp và bảo vệ thông tin thư mục khi cần. Không phải mọi hệ thống tệp đều hỗ trợ cùng một mức **atomic move** hay cam kết đồng bộ. Nếu nhiều tiến trình cùng ghi, còn phải có cơ chế khóa hoặc điều phối.

### 8.2. Database: commit, log và phục hồi

Một database giao dịch có thể giữ nhật ký phục hồi để dựng lại trạng thái nhất quán sau crash. Tuy nhiên, “đã gửi câu lệnh `INSERT`” khác với “đã commit thành công”. Trong một giao dịch có nhiều lệnh, nếu rollback thì các thay đổi có thể bị hủy. Mức độ bền của **commit** còn tùy cấu hình hệ quản trị, thiết bị và chính sách đồng bộ.

Một trường hợp khó xảy ra khi ứng dụng gửi `COMMIT`, nhưng mạng ngắt trước khi nhận phản hồi. Ứng dụng có thể không biết giao dịch đã commit hay chưa. Nếu tự động gửi lại thao tác tạo mới với mã khác, có thể tạo trùng. **Khóa yêu cầu duy nhất (idempotency key)**, ràng buộc unique và khả năng tra cứu trạng thái giúp giải quyết tình huống này.

### 8.3. Backup, replication, RPO và RTO

- **Replication:** duy trì bản sao ở một hoặc nhiều nơi, thường để tăng khả năng sẵn sàng và chịu lỗi; không mặc nhiên lưu lại trạng thái trước khi xóa nhầm.
- **Backup:** tạo dữ liệu phục hồi độc lập để khôi phục khi có mất mát hoặc thay đổi sai; cần kiểm tra khả năng restore.
- **RPO (Recovery Point Objective):** lượng dữ liệu có thể chấp nhận mất, thường được biểu diễn bằng một khoảng thời gian tính đến điểm khôi phục.
- **RTO (Recovery Time Objective):** khoảng thời gian mục tiêu để đưa hệ thống hoạt động trở lại.

Ví dụ, bộ đếm lượt xem có thể cho phép mất một phần nhỏ khi sự cố; lịch sử thanh toán thường đòi hỏi mức bảo vệ và khả năng đối soát nghiêm ngặt hơn. Vì vậy, yêu cầu durability phải xuất phát từ **hậu quả nghiệp vụ của mất hoặc sai dữ liệu**, không chỉ từ loại ổ đĩa.

## 9. Cân bằng tốc độ, tính nhất quán và chi phí

Đọc RAM thường nhanh hơn gọi database qua mạng; vì vậy ứng dụng có thể giữ dữ liệu thường dùng trong cache. Nhưng cache chỉ hữu ích khi có chính sách:

- **Nguồn sự thật:** xác định nơi chứa dữ liệu chính thức nếu cache và database khác nhau.
- **Nạp:** quyết định khi nào đọc từ database rồi đưa vào cache.
- **Hết hạn/vô hiệu:** xóa hoặc cập nhật cache khi dữ liệu gốc thay đổi, hoặc chấp nhận khoảng thời gian dữ liệu cũ.
- **Lỗi:** nếu cache trống hay dịch vụ cache ngừng hoạt động, ứng dụng có thể lấy lại dữ liệu bằng cách nào.
- **Phân tán:** nếu chạy nhiều instance, cần cân nhắc cache riêng từng node so với cache chung, và cách đồng bộ.

Một số mô hình phổ biến:

| Mô hình | Dòng ghi/đọc | Lợi ích và rủi ro |
| --- | --- | --- |
| **Cache-aside** | Đọc cache; miss thì đọc nguồn dữ liệu gốc; ghi dữ liệu gốc rồi vô hiệu cache theo chính sách | Dễ áp dụng; có thể trả dữ liệu cũ nếu vô hiệu không đúng |
| **Write-through** | Ghi qua tầng cache và tới nguồn bền theo hợp đồng | Đơn giản hóa một số đường ghi nhưng tăng độ trễ và phụ thuộc cách xác nhận ghi |
| **Write-behind** | Ghi cache trước, ghi kho bền sau theo lô/bất đồng bộ | Giảm độ trễ trước mắt nhưng có nguy cơ mất dữ liệu chưa flush khi cache gặp sự cố |
| **Không dùng cache** | Đọc và ghi trực tiếp nguồn dữ liệu | Dễ quản lý tính nhất quán hơn ở quy mô nhỏ; có thể tốn I/O hơn |

Với dữ liệu cần xác nhận ngay như tạo đơn hoặc trừ tồn kho, không nên dựa vào một bản ghi **chỉ mới nằm trong cache dễ mất** để tuyên bố thao tác nghiệp vụ đã hoàn tất, trừ khi kiến trúc đã đưa ra cam kết lưu bền và cơ chế phục hồi phù hợp.

## 10. Bảo mật, thời gian lưu giữ và tiến hóa schema

Dữ liệu lưu lâu dài có **vòng đời dài hơn bản phát hành của ứng dụng**. Đây là lý do cần lưu ý:

1. **Schema và phiên bản:** khi ứng dụng Java thêm, đổi tên hoặc bỏ field, dữ liệu cũ vẫn tồn tại. Cần migration có kiểm soát và bảo đảm đọc được trong giai đoạn chuyển tiếp.
2. **Bảo mật:** giới hạn quyền truy cập, dùng truy vấn tham số hóa thay vì ghép SQL, bảo vệ thông tin xác thực và mã hóa thích hợp khi truyền hoặc lưu.
3. **Dữ liệu nhạy cảm:** log, cache, file tạm và backup cũng có thể chứa thông tin cá nhân; không chỉ bảng chính mới cần được bảo vệ.
4. **Chính sách lưu giữ:** dữ liệu cần lưu bao lâu, khi nào được xóa hoặc chuyển sang lưu trữ lịch sử, ai được phép xem?
5. **Hiệu năng theo thời gian:** dữ liệu ngày càng lớn làm thay đổi hiệu quả của truy vấn; cần xem xét chỉ mục, phân trang, lưu trữ lịch sử và kế hoạch dung lượng.

Ở phía RAM, tránh giữ những tập dữ liệu quá lớn hoặc không còn cần thiết, vì áp lực bộ nhớ và GC có thể làm ứng dụng chậm hoặc hết bộ nhớ. Ở phía lưu bền, tránh ghi mọi trạng thái tạm thời thành bản ghi vĩnh viễn, vì dễ làm phình dung lượng và khó quản lý vòng đời dữ liệu.

## 11. Những nhận định dễ nhầm

| Nhận định | Đánh giá và cách hiểu đúng |
| --- | --- |
| “Dùng `static` thì dữ liệu giữ nguyên sau restart.” | **Sai.** `static` chỉ giữ field thuộc lớp trong JVM hiện tại. |
| “Ghi object vào `HashMap` là đã lưu dữ liệu.” | **Sai trong nghĩa persistence.** Map trong tiến trình không phải một nguồn lưu bền. |
| “Object được GC quản lý thì tự được ghi xuống đĩa.” | **Sai.** GC quản lý vòng đời cấp phát bộ nhớ, không thực hiện lưu dữ liệu nghiệp vụ. |
| “Dùng database thì không thể mất dữ liệu.” | **Sai.** Cấu hình, crash, lỗi thao tác, thiết bị hỏng và thiếu backup vẫn tạo rủi ro. |
| “File trên ổ đĩa luôn an toàn hơn RAM trong mọi tình huống.” | **Không đầy đủ.** Ghi tệp có thể bị cắt ngang hoặc chưa đồng bộ xuống thiết bị; cần xác định mức độ bền. |
| “Serialize object tức là dữ liệu đã được lưu lâu dài.” | **Sai.** Serialization mới tạo biểu diễn; còn phải lưu vào nơi bền vững và có cách phục hồi. |
| “Có cache nhanh thì không cần lưu dữ liệu gốc.” | **Tùy yêu cầu.** Nếu cache có thể mất mà dữ liệu không thể tái tạo, cache không đáp ứng nghĩa vụ lưu giữ. |
| “Transaction, replication và backup là một thứ.” | **Sai.** Chúng lần lượt giải quyết tính nguyên tử/nhất quán của cập nhật, chịu lỗi nhờ bản sao và phục hồi dữ liệu lịch sử. |

## 12. Bài tập vận dụng

### Bài tập 1: Xếp loại trạng thái

Một ứng dụng học trực tuyến có các dữ liệu sau:

1. Chuỗi gõ tìm kiếm khóa học đang nằm trong ô nhập.
2. Điểm bài kiểm tra đã được nộp và xác nhận.
3. Danh sách gợi ý khóa học được tính từ hồ sơ người học.
4. Trạng thái đã thanh toán học phí.
5. Bộ đếm các request HTTP trong 10 giây gần nhất để hiển thị màn hình giám sát.

Hãy chỉ ra dữ liệu nào **cần lưu bền vững**, dữ liệu nào **có thể chỉ nằm trong RAM**, và những điều kiện có thể làm thay đổi quyết định.

**Gợi ý đáp án:**

- (1) Thường là trạng thái tạm thời; chỉ lưu nháp khi sản phẩm yêu cầu tiếp tục sau khi đóng trang.
- (2) Cần lưu bền vì phản ánh kết quả học tập chính thức, có thể phải phục vụ tra cứu và đối soát.
- (3) Thường có thể cache và tính lại; cần quy định độ mới.
- (4) Cần nguồn bền vững, kèm định danh thanh toán và khả năng đối soát/idempotency.
- (5) Có thể lưu RAM nếu chỉ hiển thị tức thời; cần hệ thống metrics hoặc dữ liệu lịch sử nếu muốn phân tích xu hướng lâu dài.

### Bài tập 2: Kiểm tra qua restart

Chạy `VisitCounterDemo` ba lần, kiểm tra `data/visits.txt`, sau đó xóa tệp và chạy lần nữa. Giải thích vì sao bộ đếm trong JVM luôn bắt đầu lại, trong khi bộ đếm tệp tăng dần khi tệp còn tồn tại. Thử thay đổi thư mục chạy và nhận xét về đường dẫn tương đối.

### Bài tập 3: Phân tích lỗi đồng thời

Hai JVM cùng dùng một tệp lưu số lượt đăng ký. Cả hai đọc `100`, đều tính `101` và cùng ghi lại. Sau khi hai yêu cầu hoàn thành, tệp vẫn chứa `101` thay vì `102`. Hãy giải thích đây là **lost update** và đề xuất một cơ chế cập nhật an toàn hơn (giao dịch database, cập nhật có điều kiện/khóa, hoặc điều phối một người ghi).

### Bài tập 4: Thiết kế một ranh giới dữ liệu

Một API trả về `201 Created` sau khi đặt chỗ. Hãy xác định thời điểm hợp lý để trả `201` nếu API cam kết chỗ đã được ghi nhận; nêu cách xử lý nếu mất kết nối database khi commit và vì sao cần định danh yêu cầu ổn định.

**Gợi ý:** Kiểm tra commit theo hợp đồng lưu trữ trước khi xác nhận; nếu kết quả không rõ thì tra cứu bằng mã yêu cầu/định danh duy nhất trước khi thử lại, tránh nhân đôi đặt chỗ.

## 13. Checklist khi thiết kế persistence cho Java

- [ ] Tôi biết dữ liệu nào là nguồn sự thật của nghiệp vụ và dữ liệu nào có thể tái tạo.
- [ ] Tôi đã xác định rõ lúc dữ liệu chỉ nằm trong RAM và lúc dữ liệu được xem là lưu thành công.
- [ ] Tôi không dựa vào vòng đời object, `static`, cache hay GC để bảo đảm lưu lâu dài.
- [ ] Tôi đã chọn cơ chế lưu thích hợp cho quy mô, yêu cầu truy vấn và nhiều người ghi.
- [ ] Tôi đã xem xét transaction, ràng buộc, kiểm soát đồng thời và idempotency khi có cập nhật quan trọng.
- [ ] Tôi biết kết quả ghi có thể không rõ khi timeout hoặc mất kết nối.
- [ ] Tôi đã xác định cách khôi phục qua restart, sự cố thiết bị hoặc xóa nhầm và biết giới hạn của backup/replication.
- [ ] Tôi có kế hoạch quản lý schema, quyền truy cập, thời gian lưu giữ và đo hiệu năng.

## 14. Ghi nhớ

**RAM giúp ứng dụng xử lý dữ liệu đang dùng; persistence giúp ứng dụng ghi nhớ dữ liệu phải tồn tại qua thời gian.** Một biến Java có thể chứa đúng giá trị hiện tại nhưng sẽ không tự trở thành bản ghi bền vững. Tương tự, một bản ghi trong database chỉ đáng tin khi ứng dụng hiểu **điểm xác nhận**, **giới hạn durability** và **cách phục hồi** của hệ thống.

Khi thiết kế ứng dụng Java, hãy quyết định dựa trên **vòng đời và hậu quả khi dữ liệu mất hoặc bị sai**. Giữ dữ liệu có thể tính lại trong RAM khi hợp lý; bảo vệ dữ liệu nghiệp vụ cần tồn tại bằng một nguồn lưu bền vững, giao dịch và chính sách vận hành phù hợp. Đây là nền tảng cho các chủ đề tiếp theo như mô hình dữ liệu, lược đồ, chỉ mục, giao dịch, cô lập, xử lý lỗi kết nối, migration và tối ưu hiệu năng.
