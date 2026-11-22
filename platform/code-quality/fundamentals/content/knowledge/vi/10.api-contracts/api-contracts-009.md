# Thiết kế để khó sử dụng sai

Một API có thể viết đúng cú pháp Java, tài liệu đầy đủ và vượt qua mọi bài kiểm thử nội bộ nhưng vẫn dễ khiến người gọi mắc lỗi. Chẳng hạn, phương thức đặt chỗ nhận hai `String` liên tiếp: một chuỗi là mã sự kiện, chuỗi kia là mã người tham dự. Nếu lập trình viên đảo hai tham số, chương trình **vẫn biên dịch**. Lỗi chỉ xuất hiện khi dữ liệu được xử lý hoặc khi người dùng phát hiện đặt chỗ nhầm.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Hợp đồng API**, bài này tập trung vào nguyên tắc: **thiết kế giao diện sao cho cách dùng đúng dễ nhận ra, còn những cách dùng sai phổ biến khó biểu diễn, dễ bị từ chối hoặc dễ được phát hiện sớm**.

Đây là một mục tiêu thiết kế, không phải lời hứa rằng API có thể ngăn mọi lỗi. Kiểu dữ liệu giúp chặn một số sai sót lúc biên dịch; kiểm tra điều kiện đầu vào giúp chặn những giá trị sai lúc chạy; còn các quy tắc phụ thuộc trạng thái hệ thống vẫn cần xử lý và kiểm thử ở những ranh giới thích hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một API “dễ gọi” chưa chắc **dễ gọi đúng**.
- Nhận diện rủi ro từ tham số cùng kiểu, cờ Boolean, đơn vị đo không rõ, giá trị `null` và tác dụng phụ bất ngờ.
- Sử dụng **kiểu dữ liệu mang ý nghĩa nghiệp vụ**, `enum`, đối tượng tham số và kiểm tra bất biến để làm rõ hợp đồng.
- Thiết kế cách báo lỗi, kết quả và thao tác an toàn theo những tình huống sử dụng thực tế.
- Đánh giá những giới hạn của an toàn lúc biên dịch, đưa hành vi quan trọng vào kiểm thử và giữ tương thích khi API thay đổi.

## 1. “Khó sử dụng sai” nghĩa là gì?

Hãy xét chữ ký sau:

~~~java
void reserve(
    String eventId,
    String attendeeId,
    int seats,
    boolean notify,
    long timeout
);
~~~

Người gọi có thể viết:

~~~java
service.reserve("ATT-17", "EVT-42", -2, true, 30);
~~~

Chữ ký cho phép chương trình biên dịch, nhưng có ít nhất ba câu hỏi:

1. `"ATT-17"` có phải mã **người tham dự** bị đưa nhầm vào vị trí mã **sự kiện**?
2. `seats = -2` có ý nghĩa gì? Có được đặt số lượng chỗ âm không?
3. `timeout = 30` là **mili giây**, **giây** hay **phút**? `notify = true` là gửi thông báo cho ai, vào thời điểm nào?

Người dùng API phải nhớ quá nhiều quy tắc nằm ngoài kiểu tham số. Một lời gọi có thể hoàn toàn hợp lệ đối với trình biên dịch mà lại sai đối với nghiệp vụ.

Thiết kế khó sử dụng sai thường cố đạt ba đặc điểm:

| Đặc điểm | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| **Cách dùng đúng rõ ràng** | Tên và kiểu dữ liệu thể hiện ý định | `new SeatCount(2)` thay cho số nguyên không giải thích |
| **Cách dùng sai khó biểu diễn** | Một số sai sót bị từ chối bởi kiểu hoặc cấu trúc API | Không thể truyền `AttendeeId` vào tham số `EventId` |
| **Lỗi còn lại dễ phát hiện** | Ràng buộc có thông báo và điểm kiểm tra rõ ràng | Từ chối `SeatCount(0)` ngay khi tạo |

Không phải mọi sai sót đều xử lý được bằng kiểu. Ví dụ, `new EventId("EVT-999")` có cấu trúc hợp lệ nhưng sự kiện chưa chắc tồn tại; điều đó phải được kiểm tra tại repository hoặc dịch vụ có dữ liệu.

## 2. Từ tham số nguyên thủy sang khái niệm của bài toán

Giả sử hệ thống đặt chỗ sự kiện có những yêu cầu **giả định** sau:

- Một yêu cầu chỉ định **một sự kiện**, **một người tham dự** và **số lượng chỗ dương**.
- Người gọi chọn rõ có gửi **thông báo xác nhận** hay không.
- Dịch vụ có thể từ chối khi sự kiện đóng đăng ký, không đủ chỗ hoặc người tham dự đã có một yêu cầu đăng ký không được phép trùng theo chính sách.
- Việc tính còn bao nhiêu chỗ và ghi nhận đăng ký diễn ra ở tầng xử lý nghiệp vụ, không được quyết định chỉ bằng kiểm tra kiểu của request.

Để giảm nguy cơ đảo tham số, ta đưa ý nghĩa vào kiểu dữ liệu. Các ví dụ dưới đây sử dụng **Java 17 trở lên**; mỗi kiểu `public` nên được đặt trong tệp Java riêng nếu đưa vào dự án.

~~~java
public record EventId(String value) {
    public EventId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "eventId must not be blank"
            );
        }
    }
}
~~~

~~~java
public record AttendeeId(String value) {
    public AttendeeId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "attendeeId must not be blank"
            );
        }
    }
}
~~~

~~~java
public record SeatCount(int value) {
    public SeatCount {
        if (value < 1) {
            throw new IllegalArgumentException(
                "seatCount must be positive"
            );
        }
    }
}
~~~

Ba kiểu trên có biểu diễn đơn giản nhưng **không thể bị thay thế lẫn nhau khi truyền tham số**. `EventId` và `AttendeeId` cùng chứa `String`, song trình biên dịch Java phân biệt chúng là hai kiểu khác nhau. `SeatCount` chỉ cho phép số nguyên dương, nên nhiều giá trị không hợp lệ bị chặn ở lúc tạo đối tượng.

Ví dụ:

~~~java
EventId eventId = new EventId("EVT-42");
AttendeeId attendeeId = new AttendeeId("ATT-17");
SeatCount seats = new SeatCount(2);

// new SeatCount(-2); // IllegalArgumentException khi chạy.
// EventId wrong = attendeeId; // Không biên dịch: sai kiểu.
~~~

Kết quả là người đọc không còn phải đoán `id1` hoặc `id2` đại diện cho thực thể nào. Kiểu cũng giúp IDE và trình biên dịch hướng dẫn việc gọi API.

### Giới hạn của kiểu mang ý nghĩa

`new EventId("ATT-17")` vẫn biên dịch vì kiểu `EventId` không tự xác minh chuỗi đó có thuộc hệ thống sự kiện hay không. Không nên nhầm lẫn **hợp lệ về cấu trúc** với **tồn tại và được phép dùng theo nghiệp vụ**. Kiểu dữ liệu giúp thu hẹp lớp sai sót, còn yêu cầu liên quan đến dữ liệu thật phải được kiểm tra ở tầng có đủ thông tin.

## 3. Thay cờ Boolean bằng lựa chọn có tên

Tham số `boolean notify` buộc người gọi nhớ `true` và `false` có ý nghĩa gì:

~~~java
service.reserve(eventId, attendeeId, 2, false, 30);
~~~

Nếu tên tham số không hiển thị ở vị trí gọi, `false` khó được hiểu ngay. Khi chính sách phát triển thêm lựa chọn “gửi email”, “gửi SMS” hoặc “không gửi”, một cờ Boolean cũng không còn đủ biểu diễn.

Với hai lựa chọn đã được nghiệp vụ xác nhận, dùng `enum` có tên:

~~~java
public enum ConfirmationPolicy {
    SEND,
    DO_NOT_SEND
}
~~~

Lời gọi sẽ nói rõ ý định:

~~~java
ConfirmationPolicy confirmation = ConfirmationPolicy.SEND;
~~~

Đây không phải quy tắc “cấm mọi Boolean”. Những phương thức trả kết quả câu hỏi như `isActive()` hoặc `hasAccess()` trả `boolean` rất tự nhiên. Vấn đề thường nằm ở **tham số Boolean điều khiển nhiều hành vi** nhưng không rõ nghĩa tại chỗ gọi, hoặc nhiều cờ kết hợp tạo ra những tổ hợp khó hiểu.

Nếu số lựa chọn thực sự tăng, `enum` có thể mở rộng phù hợp; nếu nhiều lựa chọn độc lập và có ràng buộc phức tạp, có thể cần đối tượng chính sách riêng. Không cần dự đoán mọi biến thể chưa tồn tại.

## 4. Gom những tham số liên quan thành một yêu cầu có bất biến

Khi các giá trị luôn đi cùng nhau để mô tả một thao tác, một **đối tượng yêu cầu (request object)** có thể làm chữ ký rõ hơn và tập trung kiểm tra đầu vào.

~~~java
import java.util.Objects;

public record ReservationRequest(
    EventId eventId,
    AttendeeId attendeeId,
    SeatCount seatCount,
    ConfirmationPolicy confirmationPolicy
) {
    public ReservationRequest {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(attendeeId, "attendeeId");
        Objects.requireNonNull(seatCount, "seatCount");
        Objects.requireNonNull(
            confirmationPolicy,
            "confirmationPolicy"
        );
    }
}
~~~

API dịch vụ có thể chỉ cần nhận đúng một đối tượng:

~~~java
public interface ReservationService {
    ReservationResult reserve(ReservationRequest request);
}
~~~

Ví dụ lời gọi:

~~~java
ReservationRequest request = new ReservationRequest(
    new EventId("EVT-42"),
    new AttendeeId("ATT-17"),
    new SeatCount(2),
    ConfirmationPolicy.SEND
);

ReservationResult result = reservationService.reserve(request);
~~~

Tại chỗ gọi, người đọc có thể nhận ra **sự kiện**, **người tham dự**, **số chỗ** và **chính sách xác nhận**. Nếu đổi vị trí hai tham số đầu:

~~~java
// Không biên dịch: constructor yêu cầu EventId trước AttendeeId.
// new ReservationRequest(
//     new AttendeeId("ATT-17"),
//     new EventId("EVT-42"),
//     new SeatCount(2),
//     ConfirmationPolicy.SEND
// );
~~~

**Bất biến** quan trọng được kiểm tra sớm: không có `SeatCount` bằng 0 hoặc âm; các trường bắt buộc của `ReservationRequest` không được `null`. Nhưng constructor **không thể** tự biết một sự kiện có còn chỗ tại lúc đặt chỗ hay không. Quy tắc đó phụ thuộc trạng thái hiện tại, phải được kiểm tra bằng thao tác nghiệp vụ thích hợp.

### Không biến một request nhỏ thành “túi tham số”

Đối tượng request chỉ hữu ích khi nó đại diện cho một thao tác có ý nghĩa. Nếu tạo một lớp `Options` chứa hàng chục trường không liên quan hoặc một `Map<String, Object>` để truyền mọi thứ, API có thể còn khó hiểu hơn: người gọi phải đoán khóa nào hợp lệ, kiểu nào đi kèm khóa nào và tổ hợp nào được hỗ trợ.

Với một hàm đơn giản có hai tham số dễ hiểu như `Math.max(a, b)`, không cần tạo đối tượng riêng. Mức trừu tượng phải tỷ lệ với **rủi ro bị dùng sai** và **độ phức tạp của hợp đồng**.

## 5. Đơn vị đo và thời gian phải được thể hiện tường minh

Tham số `long timeout` của API ban đầu dễ gây lỗi đơn vị. `30` có thể là 30 mili giây, 30 giây hoặc 30 phút. Lỗi này có thể chỉ bộc lộ khi ứng dụng chờ quá lâu, thử lại quá sớm hoặc hết thời gian chờ bất thường.

Trong Java, `Duration` thể hiện độ dài thời gian:

~~~java
import java.time.Duration;
import java.util.Objects;

public record RetryPolicy(int maxAttempts, Duration timeoutPerAttempt) {
    public RetryPolicy {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                "maxAttempts must be positive"
            );
        }
        Objects.requireNonNull(timeoutPerAttempt, "timeoutPerAttempt");
        if (timeoutPerAttempt.isZero() || timeoutPerAttempt.isNegative()) {
            throw new IllegalArgumentException(
                "timeoutPerAttempt must be positive"
            );
        }
    }
}
~~~

~~~java
RetryPolicy retryPolicy = new RetryPolicy(
    3,
    Duration.ofSeconds(2)
);
~~~

Lời gọi cuối thể hiện rõ: tối đa **3 lần thử**, thời gian chờ **2 giây cho mỗi lần thử**. Tên `timeoutPerAttempt` còn giúp phân biệt với **thời hạn tổng** của toàn bộ thao tác. Khi thực thi chính sách này, tầng client vẫn phải xác định khi nào timeout được áp dụng, những loại lỗi nào được retry, và cơ chế hủy tác vụ có thực sự hoạt động hay không.

Nguyên tắc tương tự áp dụng với:

| Giá trị dễ hiểu nhầm | Rủi ro | Cách diễn đạt phù hợp hơn |
| --- | --- | --- |
| `int timeout` | Không rõ mili giây hay giây | `Duration timeout` |
| `long timestamp` | Không rõ epoch giây hay mili giây | `Instant occurredAt` |
| `double amount` | Mất chính xác hoặc không rõ đơn vị tiền | Kiểu tiền với đơn vị, chẳng hạn `BigDecimal` + mã tiền tệ |
| `int distance` | Không rõ mét hay kilômét | Tên có đơn vị hoặc kiểu đo khoảng cách |
| `String date` | Không rõ định dạng, múi giờ | `LocalDate`, `Instant` hoặc `ZonedDateTime` theo nghiệp vụ |

Không phải kiểu chung nào cũng tự giải quyết mọi vấn đề. `BigDecimal` không ghi nhớ đồng tiền; `Instant` không nói ngày làm việc theo múi giờ nào; `Duration` không thay thế chính sách thời gian chờ. API phải diễn đạt **đơn vị và ngữ nghĩa cần thiết**, không chỉ thay kiểu nguyên thủy bằng một lớp thư viện.

## 6. Kết quả và lỗi phải chỉ rõ điều gì xảy ra

Một API như `boolean reserve(...)` không cho người gọi biết vì sao thất bại. Nếu chỉ có giá trị `false`, người gọi có thể không phân biệt được sự kiện đóng, hết chỗ hoặc yêu cầu bị trùng.

Tùy chính sách, ta có thể mô hình hóa kết quả bằng những kiểu khác nhau. Với Java 17, ví dụ dùng `sealed interface` để biểu diễn hai nhóm kết quả nghiệp vụ:

~~~java
public sealed interface ReservationResult
    permits Reserved, Refused {
}

public record Reserved(String reservationCode)
    implements ReservationResult {
    public Reserved {
        if (reservationCode == null || reservationCode.isBlank()) {
            throw new IllegalArgumentException(
                "reservationCode must not be blank"
            );
        }
    }
}

public enum RefusalReason {
    EVENT_CLOSED,
    NOT_ENOUGH_SEATS,
    DUPLICATE_RESERVATION
}

public record Refused(RefusalReason reason)
    implements ReservationResult {
    public Refused {
        java.util.Objects.requireNonNull(reason, "reason");
    }
}
~~~

Như vậy, hai kết quả nghiệp vụ có cấu trúc phân biệt:

- `new Reserved("RES-105")`: thao tác thành công, có mã đặt chỗ.
- `new Refused(RefusalReason.NOT_ENOUGH_SEATS)`: thao tác hợp lệ về cú pháp nhưng không thể hoàn tất vì thiếu chỗ.

Người gọi có thể xử lý rõ từng loại:

~~~java
ReservationResult result = reservationService.reserve(request);
if (result instanceof Reserved reserved) {
    System.out.println("Reservation: " + reserved.reservationCode());
} else if (result instanceof Refused refused) {
    System.out.println("Rejected: " + refused.reason());
}
~~~

Các kiểu trên diễn đạt kết quả nghiệp vụ. Chúng **không tự bảo đảm** rằng implementation thật sự ghi nhận chỗ thành công, không tạo trùng, hoặc mapping mọi lỗi đúng. Phần đó vẫn cần mã triển khai, transaction và kiểm thử phù hợp.

### Phân biệt đầu vào sai, từ chối nghiệp vụ và sự cố hạ tầng

Ba loại thất bại này không nhất thiết nên dùng chung một giá trị:

| Loại thất bại | Ví dụ | Cách thể hiện khả dĩ |
| --- | --- | --- |
| Đầu vào không hợp lệ | `SeatCount(0)`, thiếu mã sự kiện | Ném `IllegalArgumentException` hoặc lỗi validation tại ranh giới API |
| Từ chối theo quy tắc nghiệp vụ | Sự kiện đã đóng, không đủ chỗ | Kết quả `Refused(reason)` có nghĩa rõ |
| Sự cố kỹ thuật | Database mất kết nối, hết thời gian chờ | Lỗi hạ tầng được log và ánh xạ sang lỗi công khai phù hợp |

Đừng âm thầm chuyển lỗi hệ thống thành kết quả “hết chỗ” nếu nghiệp vụ không quy định vậy. Cách này khiến người dùng hiểu sai trạng thái và người vận hành khó phát hiện sự cố.

Trong HTTP API, cách biểu diễn có thể là mã trạng thái và body lỗi ổn định; trong thư viện Java, có thể là kiểu kết quả hoặc ngoại lệ có hợp đồng. **Điều quan trọng là người gọi biết điều gì có thể xảy ra và phải làm gì với từng trường hợp.**

## 7. Tên phương thức phải khớp với tác dụng phụ

Tên `checkReservation()` khiến người đọc nghĩ đây là thao tác chỉ kiểm tra. Nếu phương thức tự ghi dữ liệu hoặc gửi email, người dùng API có thể gọi “kiểm tra” nhiều lần và vô tình tạo nhiều đặt chỗ.

Một cách đặt tên rõ trách nhiệm:

~~~java
boolean canReserve(ReservationRequest request); // Truy vấn điều kiện.

ReservationResult reserve(ReservationRequest request); // Thay đổi trạng thái.

void cancel(ReservationId reservationId); // Yêu cầu hủy đặt chỗ.
~~~

`canReserve(...)` là truy vấn, không nên có tác dụng phụ nghiệp vụ; `reserve(...)` là mệnh lệnh có thể ghi dữ liệu. `ReservationId` ở đây là một kiểu định danh minh họa, sẽ cần định nghĩa nếu đưa ví dụ này vào chương trình thực tế.

Tuy nhiên, **không được dựa vào `canReserve` để bảo đảm thao tác tiếp theo thành công**. Giữa lúc kiểm tra và đặt chỗ, một người khác có thể đặt hết những chỗ còn lại:

~~~text
Người A: canReserve() -> true
Người B: reserve()    -> thành công, hết chỗ
Người A: reserve()    -> phải kiểm tra lại và từ chối
~~~

Đây là hiện tượng *time of check to time of use* (TOCTOU). Nếu API tách “kiểm tra” và “thực hiện”, thao tác thực hiện vẫn phải kiểm tra điều kiện và cập nhật trạng thái **một cách nhất quán**, thường ở tầng transaction hoặc cơ chế đồng bộ phù hợp.

Một API dễ dùng đúng phải làm rõ đâu là **thông tin dự đoán tại thời điểm kiểm tra**, đâu là **kết quả đã được xác nhận khi ghi nhận nghiệp vụ**.

## 8. Mặc định an toàn và quyền sửa dữ liệu

API khó sử dụng sai thường giới hạn những thao tác có thể gây tác động ngoài ý muốn. Ví dụ, nếu trả trực tiếp danh sách đăng ký có thể sửa, người gọi có thể bỏ qua phương thức `reserve` và tự thêm người tham dự:

~~~java
// Nguy hiểm nếu danh sách là trạng thái nội bộ.
List<AttendeeId> attendees = event.getAttendees();
attendees.add(new AttendeeId("ATT-999"));
~~~

Nếu hợp đồng chỉ cho phép đọc danh sách, API có thể trả bản chụp:

~~~java
public List<AttendeeId> attendeeSnapshot() {
    return List.copyOf(attendees);
}
~~~

Với giả định các `AttendeeId` là kiểu giá trị bất biến, `List.copyOf` giúp người gọi không thể thay đổi cấu trúc danh sách trả về, và các thay đổi sau đó trong danh sách nội bộ không làm đổi phần tử của bản chụp. Nếu phần tử có trạng thái thay đổi được, sao chép danh sách **không tự sao chép sâu** những phần tử đó.

Các yếu tố khác cần xác định rõ:

- Giá trị mặc định có tác dụng phụ hay không? Nếu không được chỉ định chính sách thông báo, có nên bắt người gọi chọn tường minh thay vì tự gửi?
- Tham số nào cho phép `null`? Nếu có, `null` mang ý nghĩa gì và khác “không cung cấp” hay “rỗng” thế nào?
- Đối tượng trả về có thể bị sửa không, và sửa có làm thay đổi trạng thái của dịch vụ không?
- Dữ liệu bí mật hoặc quyền hạn có được giới hạn theo phạm vi gọi hay không?

“Mặc định an toàn” phải được định nghĩa theo bối cảnh. Ví dụ, mặc định **không gửi thông báo** có thể tránh gửi sai người trong một hệ thống, nhưng lại không phù hợp nếu quy trình pháp lý bắt buộc gửi xác nhận. Không được tự suy diễn chính sách thay cho yêu cầu nghiệp vụ.

## 9. Kết quả đúng còn phụ thuộc vào điều kiện khi chạy

Các kiểu `EventId`, `AttendeeId` và `SeatCount` kiểm tra được một số điều ngay tại điểm tạo dữ liệu. Nhưng những điều sau chỉ có thể xác minh khi dịch vụ truy cập trạng thái hiện tại:

- Sự kiện có tồn tại và cho phép đặt chỗ không?
- Người tham dự có quyền đặt chỗ không?
- Số chỗ còn đủ ngay tại lúc ghi nhận không?
- Đã tồn tại một đăng ký cần ngăn trùng chưa?
- Nếu retry sau timeout, làm sao không ghi nhận lại cùng thao tác?

Những rủi ro này không biến mất khi thêm kiểu dữ liệu. Cần đặt kiểm tra ở **ranh giới chịu trách nhiệm**, kết hợp giao dịch, khóa, ràng buộc duy nhất hoặc idempotency key theo cách hệ thống lưu trữ và xử lý thực tế.

Ví dụ, với yêu cầu có thể bị gửi lại do lỗi mạng, nếu chính sách là **mỗi thao tác logic chỉ tạo một đặt chỗ**, hợp đồng có thể phải có một `RequestId` do phía gọi cung cấp để nhận diện các lần thử lại của cùng thao tác. Khi đó, dịch vụ phải lưu và kiểm tra khóa đó nhất quán. Chỉ thêm tham số `requestId` vào chữ ký mà không thực hiện cơ chế chống trùng ở phía server sẽ không bảo đảm an toàn.

Vì vậy nên phân tầng bảo vệ:

| Tầng | Sai sót có thể phát hiện | Ví dụ |
| --- | --- | --- |
| Biên dịch | Sai loại tham số | Truyền `AttendeeId` vào vị trí `EventId` |
| Tạo giá trị | Vi phạm bất biến cục bộ | `new SeatCount(-1)` |
| Ranh giới request/API | Thiếu trường bắt buộc, dữ liệu sai định dạng | JSON không chứa `eventId` |
| Logic nghiệp vụ | Không đáp ứng quy tắc hiện hành | Sự kiện hết chỗ |
| Lưu trữ/đồng thời | Cạnh tranh hoặc xử lý trùng | Hai lời gọi cùng cố giữ một chỗ |
| Giám sát vận hành | Hệ thống ngoài lỗi hoặc suy giảm | Timeout, retry bất thường, ghi nhận thiếu |

Mục tiêu là **đưa lỗi đến nơi phát hiện sớm nhất có đủ thông tin và thẩm quyền kiểm tra**.

## 10. Khi API thay đổi, cách dùng cũ có còn đúng?

Một API tốt còn cần dễ thay đổi mà không gây lỗi âm thầm cho người gọi. Giả sử phiên bản đầu chỉ có:

~~~java
ReservationResult reserve(
    EventId eventId,
    AttendeeId attendeeId
);
~~~

Đội phát triển muốn bổ sung số chỗ và chính sách thông báo. Việc thay chữ ký cũ bằng các tham số cùng kiểu hoặc gán mặc định thiếu cơ sở có thể làm ứng dụng khách thay đổi hành vi mà không biết.

Các phương án cần cân nhắc:

1. **Thêm overload** có nghĩa rõ và giữ overload cũ với hành vi đã cam kết, nếu yêu cầu tương thích ngược.
2. **Dùng đối tượng yêu cầu mới** khi có nhiều trường liên quan, cùng hướng dẫn chuyển đổi rõ.
3. **Công bố thay đổi không tương thích** nếu chính sách mới bắt buộc và không thể giữ hành vi cũ; lập kế hoạch phiên bản và di chuyển.
4. **Kiểm thử với ứng dụng khách thực tế hoặc contract tests** để phát hiện các thay đổi ở giao diện và ý nghĩa dữ liệu.

Tương thích ở mức biên dịch không đủ. Cùng một chữ ký có thể đổi quy tắc nghiệp vụ, từ chối dữ liệu đã được chấp nhận trước đây, thay đơn vị `timeout` hoặc đổi loại lỗi. Đó vẫn có thể là **thay đổi hợp đồng hành vi**.

Ngoài ra, `builder` thường giúp dễ đọc những lời gọi có nhiều tùy chọn:

~~~java
// Minh họa phong cách sử dụng; cần triển khai builder thực tế.
ReservationRequest request = ReservationRequestBuilder
    .forEvent(new EventId("EVT-42"))
    .forAttendee(new AttendeeId("ATT-17"))
    .seats(new SeatCount(2))
    .confirmation(ConfirmationPolicy.SEND)
    .build();
~~~

Nhưng builder không tự bảo đảm trạng thái hợp lệ: `build()` vẫn phải từ chối thiếu trường bắt buộc hoặc tổ hợp không được hỗ trợ. Đối với request chỉ có bốn trường có tên rõ ràng, constructor của `record` có thể đã đủ đơn giản.

## 11. Kiểm thử API phải thử cả những cách dùng sai

Một test chỉ xác nhận `SeatCount(2)` được tạo thành công không cho biết `SeatCount(0)` hoặc `SeatCount(-1)` có bị ngăn hay không. Thiết kế API cần được kiểm thử ở cả **đường thành công** và **ranh giới bị từ chối**.

Ví dụ JUnit 5 cho các kiểu đã giới thiệu:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ReservationApiTest {

    @Test
    void rejectsNonPositiveSeatCount() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new SeatCount(0)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new SeatCount(-1)
        );
    }

    @Test
    void rejectsBlankIds() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new EventId(" ")
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> new AttendeeId(null)
        );
    }

    @Test
    void rejectsMissingRequestFields() {
        assertThrows(
            NullPointerException.class,
            () -> new ReservationRequest(
                new EventId("EVT-42"),
                null,
                new SeatCount(1),
                ConfirmationPolicy.DO_NOT_SEND
            )
        );
    }

    @Test
    void requestRetainsExplicitBusinessValues() {
        ReservationRequest request = new ReservationRequest(
            new EventId("EVT-42"),
            new AttendeeId("ATT-17"),
            new SeatCount(2),
            ConfirmationPolicy.SEND
        );

        assertEquals(new SeatCount(2), request.seatCount());
        assertEquals(ConfirmationPolicy.SEND, request.confirmationPolicy());
    }
}
~~~

Các test trên kiểm tra **bất biến cục bộ của API**. Chúng không thay thế kiểm thử nghiệp vụ của `ReservationService`. Với một implementation cụ thể, cần thêm các ca:

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Sự kiện còn mở, đủ chỗ | Trả `Reserved` và ghi nhận đúng một đặt chỗ |
| Sự kiện đóng đăng ký | Trả `Refused(EVENT_CLOSED)`, không ghi đặt chỗ |
| Thiếu chỗ | Trả `Refused(NOT_ENOUGH_SEATS)`, không làm âm tồn kho chỗ |
| Yêu cầu đặt chỗ trùng | Theo chính sách đã xác nhận; không tạo tác dụng phụ trùng |
| Hai yêu cầu cạnh tranh chỗ cuối | Không cho cả hai vượt tổng sức chứa |
| Thông báo được bật/tắt | Tác dụng phụ thực tế khớp `ConfirmationPolicy` |
| Lỗi hạ tầng | Không báo thành công sai; lỗi được ánh xạ theo hợp đồng |

Không thể viết test cho **lỗi kiểu biên dịch** theo cách gọi trực tiếp mã sai trong một test Java đang cần biên dịch thành công. Khi muốn xác minh kiểu ngăn một lời gọi, có thể sử dụng kiểm tra biên dịch chuyên biệt hoặc xem xét chữ ký API bằng trình biên dịch và code review. Còn JUnit phù hợp cho hành vi ở thời điểm chạy.

## 12. Checklist khi review một API

Trước khi công bố hoặc sửa một giao diện, hãy tự hỏi:

1. **Người gọi có thể nhìn vào tên phương thức và chữ ký để hiểu hành động không?** Có phải họ mở phần triển khai mới biết phương thức ghi dữ liệu hay gửi thông báo?
2. **Hai tham số cùng kiểu có thể bị đảo không?** Nếu sai sót gây hậu quả đáng kể, có nên dùng kiểu riêng hoặc đối tượng request?
3. **Đơn vị, thời gian, định dạng dữ liệu có rõ không?** `timeout`, số tiền, timestamp có đơn vị xác định không?
4. **Giá trị không hợp lệ có bị chặn sớm không?** `null`, số âm, chuỗi trống, tổ hợp tùy chọn mâu thuẫn được xử lý thế nào?
5. **Người gọi có biết kết quả và nguyên nhân thất bại không?** Đâu là từ chối nghiệp vụ, đâu là lỗi đầu vào và đâu là sự cố kỹ thuật?
6. **Đối tượng trả về có cho sửa trạng thái nội bộ không?** Có cần bản chụp, vỏ bọc chỉ đọc hoặc kiểu bất biến?
7. **Phải kiểm tra lại điều kiện nào khi chạy?** Kiểu dữ liệu không thay thế kiểm tra quyền, trạng thái và tính nguyên tử.
8. **Điều gì xảy ra khi gọi lại?** API có idempotent không, hoặc phải cung cấp khóa nhận diện yêu cầu?
9. **Thay đổi hợp đồng có làm hỏng ứng dụng khách cũ không?** Có test tương thích và hướng dẫn di chuyển?
10. **Thiết kế có quá phức tạp so với nhu cầu thực tế không?** Kiểu riêng, builder, sealed result và interface chỉ hữu ích khi giảm nhầm lẫn hoặc cô lập biến động thực sự.

Một thước đo thực tế là **số câu hỏi người dùng API phải tự đoán**. Chữ ký, kiểu dữ liệu và tài liệu nên trả lời những câu hỏi quan trọng về ý nghĩa, điều kiện và kết quả.

## 13. Bài tập tình huống

Bạn được giao thiết kế API tạo lịch nhắc:

~~~java
void schedule(String user, String message, long time, boolean repeat);
~~~

Nhóm nghiệp vụ xác nhận: mỗi lời nhắc thuộc một người dùng, có nội dung không rỗng, có thời điểm kích hoạt theo UTC và có chế độ lặp hoặc chỉ chạy một lần. Nếu nhắc lặp, cần biết **chu kỳ lặp**; nếu chỉ chạy một lần thì không có chu kỳ.

**Câu hỏi A.** Chữ ký hiện tại dễ bị dùng sai ở những điểm nào?

**Câu hỏi B.** Đề xuất các kiểu và cấu trúc để hạn chế tạo một yêu cầu “không lặp nhưng lại có chu kỳ” hoặc “có lặp nhưng không có chu kỳ”.

**Câu hỏi C.** Những điều gì vẫn phải kiểm tra ở thời điểm chạy dù đã dùng kiểu dữ liệu mạnh?

### Gợi ý đáp án

**A.** `String user` không cho biết đây là ID hay tên hiển thị; `String message` có thể rỗng; `long time` không rõ epoch giây/mili giây hoặc múi giờ; `boolean repeat` không thể mang theo chu kỳ lặp.

**B.** Có thể dùng `UserId`, `ReminderText`, `Instant scheduledAt` và một kiểu biểu diễn chế độ chạy:

~~~java
import java.time.Duration;

sealed interface ScheduleMode permits OneTime, Repeating {}

record OneTime() implements ScheduleMode {}

record Repeating(Duration interval) implements ScheduleMode {
    public Repeating {
        if (interval == null || interval.isNegative() || interval.isZero()) {
            throw new IllegalArgumentException(
                "interval must be positive"
            );
        }
    }
}
~~~

Như vậy, `OneTime` **không có trường chu kỳ**, còn `Repeating` **bắt buộc có** một `Duration` dương. Tùy chính sách, còn có thể yêu cầu chu kỳ tối thiểu, giới hạn số lần lặp hoặc quy tắc tạm dừng. Kiểu `Instant` mô tả một thời điểm tuyệt đối; nếu người dùng muốn nhắc lúc 09:00 theo múi giờ địa phương vào mỗi ngày, cần làm rõ quy tắc lịch và dùng kiểu phù hợp hơn `Duration` đơn thuần.

**C.** Cần xác minh người dùng có tồn tại và được phép tạo lịch không, thời điểm đã qua được xử lý thế nào, scheduler có thực sự lưu yêu cầu bền vững không, retry có gây gửi nhắc trùng không và việc hủy lịch đang chạy được giải quyết ra sao.

## Ghi nhớ

**Thiết kế API để khó sử dụng sai** là đưa những quy tắc quan trọng vào **tên gọi, kiểu dữ liệu, bất biến và hợp đồng hành vi**, để sai sót phổ biến được phát hiện sớm và cách dùng đúng trở nên rõ ràng. Kiểu riêng hạn chế truyền nhầm; `enum` và đối tượng request giúp thể hiện ý định; giá trị thời gian/tiền tệ có đơn vị; kiểu kết quả và lỗi rõ ràng giúp người gọi xử lý phù hợp.

Một API đáng tin cậy còn phải làm rõ **tác dụng phụ, quyền sửa dữ liệu, trạng thái khi chạy, xử lý đồng thời và tương thích phiên bản**. Không cần tạo lớp cho mọi giá trị; hãy bổ sung cấu trúc nơi nó thực sự giúp người gọi hiểu đúng, thực hiện đúng và kiểm tra đúng hợp đồng.
