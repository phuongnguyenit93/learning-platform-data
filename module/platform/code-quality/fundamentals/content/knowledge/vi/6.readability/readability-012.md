# Cân bằng quy ước chung với đặc điểm của bài toán

## 1. Mục tiêu bài học

Trong chương **Khả năng đọc** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu cách kết hợp các quy ước lập trình chung với ngôn ngữ và quy tắc riêng của một bài toán. Mục tiêu của module là **hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Một đoạn mã dễ đọc cần nhất quán với phần còn lại của dự án, đồng thời phản ánh đúng điều mà hệ thống đang giải quyết.

Sau bài học này, bạn có thể:

- Giải thích vai trò của quy ước chung và ngôn ngữ nghiệp vụ đối với khả năng đọc mã.
- Nhận biết lúc nào nên áp dụng quy ước mặc định, lúc nào cần thể hiện rõ đặc điểm bài toán trong tên gọi hoặc cấu trúc.
- Phân tích ví dụ Java về đặt sân để thấy khác biệt giữa một điều kiện kỹ thuật đúng cú pháp và một quy tắc nghiệp vụ được diễn đạt rõ.
- Đưa ra ngoại lệ có kiểm soát đối với quy ước và giải thích ngoại lệ đó trong code review.
- Kiểm tra tính đúng đắn của quy tắc nghiệp vụ bằng ví dụ và trường hợp biên, bên cạnh việc kiểm tra định dạng mã.

## 2. Hai nguồn thông tin giúp người đọc hiểu mã

### Quy ước chung tạo sự quen thuộc

**Quy ước lập trình (coding conventions)** là những cách trình bày, đặt tên và tổ chức mã mà nhóm thống nhất sử dụng. Ví dụ trong dự án Java: lớp thường dùng `PascalCase`, phương thức và biến dùng `camelCase`, hằng số `static final` dùng `UPPER_SNAKE_CASE`, cách thụt lề thống nhất và việc sử dụng ngoại lệ theo hợp đồng rõ ràng. Một số quy ước do ngôn ngữ và hệ sinh thái gợi ý; một số do nhóm hoặc công cụ định dạng quy định.

Khi người đọc gặp những mẫu quen thuộc, họ ít phải suy nghĩ về hình thức và có thể tập trung vào hành vi. Quy ước còn giảm những cuộc tranh luận lặp lại trong review: nếu nhóm đã thống nhất cách định dạng, máy có thể kiểm tra điều đó thay cho con người.

Tuy nhiên, **mã được định dạng giống nhau không có nghĩa là ý định giống nhau hoặc rõ ràng**. Các tên như `data`, `item`, `process` hay `check` đều có thể tuân thủ `camelCase` nhưng vẫn không cho biết mã đang xử lý điều gì.

### Đặc điểm bài toán quyết định ý nghĩa

**Đặc điểm của bài toán (domain semantics)** gồm khái niệm, quy tắc, giới hạn và thuật ngữ mà người dùng nghiệp vụ thực sự quan tâm. Với hệ thống đặt sân, những khái niệm như *sân*, *khung giờ đặt*, *trùng lịch*, *thời gian bắt đầu* và *thời gian kết thúc* mang ý nghĩa cụ thể. Hai khung giờ chỉ chạm nhau tại điểm kết thúc có thể được xem là **không trùng lịch** nếu sản phẩm định nghĩa khoảng thời gian theo dạng `[bắt đầu, kết thúc)`.

Một đoạn mã dễ đọc nên cho thấy những đặc điểm đó ở nơi chúng quan trọng. Khi tên gọi và cấu trúc khớp với cách nhóm nghiệp vụ mô tả quy tắc, lập trình viên, người kiểm thử và người phân tích có thể trao đổi ít mơ hồ hơn.

| Khía cạnh | Quy ước chung trả lời | Ngữ nghĩa bài toán trả lời |
| --- | --- | --- |
| Đặt tên | Tên lớp, biến, phương thức được viết theo kiểu nào? | Tên đó biểu thị khái niệm và hành vi gì? |
| Cấu trúc | Phân chia phương thức, lớp, gói theo kiểu tổ chức nào? | Trách nhiệm nào thuộc cùng một quy tắc nghiệp vụ? |
| Kiểm tra dữ liệu | Sử dụng cách kiểm tra và thông báo lỗi nhất quán ra sao? | Dữ liệu thế nào được xem là hợp lệ? |
| Kiểm thử | Tên test, bố cục và công cụ có nhất quán không? | Trường hợp nào quyết định hành vi đúng hay sai? |
| Giao tiếp hệ thống | Kiểu DTO hoặc quy tắc ánh xạ được áp dụng thế nào? | Trường dữ liệu có ý nghĩa và hợp đồng gì với đối tác? |

**Cân bằng** không có nghĩa mỗi bên được ưu tiên một nửa. Hãy dùng quy ước chung làm **mặc định**, sau đó chọn tên gọi và ranh giới thiết kế phản ánh đúng bài toán. Nếu hai lựa chọn xung đột, phải làm rõ ràng buộc thực tế trước khi chọn phương án.

## 3. Vì sao áp dụng máy móc một phía lại gây khó đọc?

Có hai nhóm vấn đề đối xứng:

1. **Quá tổng quát:** mọi lớp đều mang tên `Manager`, mọi hành động đều là `process` hoặc `handle`, các trạng thái được mã hóa thành `flag`, `type` và `value`. Cấu trúc có thể thống nhất, nhưng người đọc không nhìn thấy nghiệp vụ.
2. **Quá tùy biến:** mỗi nhóm tự chọn cách viết tên, định dạng hoặc ký hiệu riêng; có đoạn dùng `getStartTime`, đoạn dùng `fromTs`, đoạn dùng `t0` cho cùng một ý nghĩa mà không có lý do. Người đọc mất thời gian học lại quy tắc ở từng nơi.

Ví dụ, những tên sau đều hợp lệ về cú pháp Java nhưng cung cấp lượng thông tin rất khác nhau:

```java
boolean check(String a, String b);             // Đang kiểm tra điều gì?
boolean isValid(String a, String b);           // Hợp lệ theo quy tắc nào?
boolean canCancelBooking(Booking booking);     // Quyết định nghiệp vụ được nói rõ.
```

Tên thứ ba không bảo đảm phương thức được cài đặt đúng, nhưng giúp người đọc biết phải tìm yêu cầu nào để đối chiếu và viết kiểm thử. Ngược lại, phương thức tên `canCancelBooking` mà âm thầm gửi email hoặc thay đổi trạng thái đặt sân cũng gây bất ngờ: **tên rõ nghĩa phải đi cùng hành vi đúng như đã hứa**.

## 4. Ví dụ Java: trùng lịch đặt sân

Giả sử ứng dụng nhận các lượt đặt cho nhiều sân. Nhóm sản phẩm xác nhận hai quy tắc:

- Hai lượt đặt chỉ xung đột nếu **cùng một sân** và các khoảng thời gian của chúng giao nhau.
- Khoảng đặt được hiểu là **bao gồm thời điểm bắt đầu, không bao gồm thời điểm kết thúc**: `[startsAt, endsAtExclusive)`. Vì vậy, lượt đặt 09:00–10:00 và lượt đặt 10:00–11:00 trên cùng sân có thể tồn tại liên tiếp.

Ví dụ sử dụng **Java 17**; tất cả thời điểm ở đây được giả định đã thống nhất theo giờ địa phương của **một cơ sở đặt sân**. Nếu ứng dụng phục vụ nhiều múi giờ hoặc có thay đổi giờ mùa hè, cần thiết kế cách lưu mốc thời gian và múi giờ riêng, chẳng hạn dùng `Instant` cho thời điểm tuyệt đối và giữ `ZoneId` của cơ sở.

### 4.1. Công thức ngắn nhưng che giấu quy tắc

```java
static boolean check(String a, String b,
                     LocalDateTime x, LocalDateTime y,
                     LocalDateTime z, LocalDateTime t) {
    return a.equals(b) && x.isBefore(t) && z.isBefore(y);
}
```

`a` và `b` là mã sân, `x` và `y` là thời gian bắt đầu/kết thúc của lượt thứ nhất, còn `z` và `t` là của lượt thứ hai. Với dữ liệu đã được kiểm tra hợp lệ, công thức thể hiện điều kiện giao nhau của hai khoảng nửa mở.

Nhưng người đọc phải tự ghép ý nghĩa của sáu tham số. Hàm cũng chưa nói rõ điều kiện `startsAt < endsAt`. Nếu người gọi truyền khoảng không hợp lệ, công thức có thể cho kết quả vô nghĩa. Tên `check` không thể hiện câu hỏi nghiệp vụ mà hàm trả lời.

### 4.2. Giữ quy ước Java, đưa ý nghĩa bài toán vào tên và cấu trúc

```java
import java.time.LocalDateTime;
import java.util.Objects;

public record CourtBooking(
        String courtId,
        LocalDateTime startsAt,
        LocalDateTime endsAtExclusive) {

    public CourtBooking {
        Objects.requireNonNull(courtId, "courtId");
        Objects.requireNonNull(startsAt, "startsAt");
        Objects.requireNonNull(endsAtExclusive, "endsAtExclusive");

        if (courtId.isBlank()) {
            throw new IllegalArgumentException("courtId must not be blank");
        }
        if (!startsAt.isBefore(endsAtExclusive)) {
            throw new IllegalArgumentException(
                    "startsAt must be before endsAtExclusive");
        }
    }

    public boolean conflictsWith(CourtBooking other) {
        Objects.requireNonNull(other, "other");

        return courtId.equals(other.courtId())
                && startsAt.isBefore(other.endsAtExclusive())
                && other.startsAt().isBefore(endsAtExclusive);
    }
}
```

Cách viết này vẫn tuân theo quy ước quen thuộc: `CourtBooking` là tên kiểu Java, `courtId`, `startsAt`, `conflictsWith` dùng `camelCase`, tên biểu thị đối tượng và hành vi, không có ký hiệu bí ẩn. Điểm khác biệt nằm ở **ý nghĩa được đưa vào mô hình**:

- `CourtBooking` cho biết ba thuộc tính thuộc cùng một lượt đặt.
- `courtId` khiến điều kiện *cùng sân* không bị lẫn với điều kiện giao thời gian.
- `endsAtExclusive` diễn đạt chính sách loại trừ thời điểm kết thúc, thay vì tên mơ hồ `end`.
- `conflictsWith` trả lời trực tiếp câu hỏi nghiệp vụ: hai lượt đặt có xung đột không?
- Constructor xác nhận bất biến `startsAt < endsAtExclusive`, tránh tạo đối tượng thời gian không hợp lệ.

Vì `record` trong Java sinh accessor theo tên thành phần, cách gọi `other.endsAtExclusive()` là đúng quy ước của `record`; không cần tự thêm `getEndsAtExclusive()` chỉ để bắt chước JavaBean. Nếu hệ thống cần tương thích với framework đòi hỏi một quy ước accessor cụ thể, hãy xử lý tại ranh giới phù hợp thay vì đặt ra nhiều phiên bản tên không cần thiết.

Không nên hiểu ví dụ như yêu cầu mọi khoảng thời gian đều phải được biểu diễn bằng `CourtBooking`. Nếu chức năng khác chỉ cần so sánh hai khoảng thời gian thuần túy, một kiểu `TimeInterval` có hợp đồng rõ có thể thích hợp hơn. Tên và cấu trúc phải phản ánh **trách nhiệm thật sự**, không chỉ cố gắn thuật ngữ nghiệp vụ vào mọi lớp.

### 4.3. Kiểm thử điều kiện biên, không chỉ kiểm tra định dạng

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class CourtBookingTest {
    private static LocalDateTime at(int hour, int minute) {
        return LocalDateTime.of(2026, 11, 16, hour, minute);
    }

    @Test
    void adjacentBookingsOnSameCourtDoNotConflict() {
        var first = new CourtBooking("COURT-A", at(9, 0), at(10, 0));
        var next = new CourtBooking("COURT-A", at(10, 0), at(11, 0));

        assertFalse(first.conflictsWith(next));
        assertFalse(next.conflictsWith(first));
    }

    @Test
    void overlappingBookingsOnlyConflictOnSameCourt() {
        var first = new CourtBooking("COURT-A", at(9, 0), at(10, 0));
        var sameCourt = new CourtBooking("COURT-A", at(9, 30), at(10, 30));
        var otherCourt = new CourtBooking("COURT-B", at(9, 30), at(10, 30));

        assertTrue(first.conflictsWith(sameCourt));
        assertFalse(first.conflictsWith(otherCourt));
    }

    @Test
    void invalidTimeWindowIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new CourtBooking("COURT-A", at(10, 0), at(10, 0)));
    }
}
```

Các trường hợp trên xác minh ngữ nghĩa quan trọng: **chạm ranh giới không trùng**, **trùng thời gian chỉ xung đột khi cùng sân**, và **không chấp nhận khoảng rỗng**. Chúng bảo vệ ý nghĩa của `conflictsWith` trước lỗi hồi quy. Đây vẫn chỉ là kiểm thử minh họa, chưa bao phủ toàn bộ chức năng đặt sân như hủy lịch, khung giờ bảo trì, đặt quá khứ hoặc giao dịch đồng thời.

Đáng chú ý, công cụ định dạng mã có thể làm cả hai phiên bản trông ngay ngắn, nhưng **không thể suy ra quy tắc xung đột từ `check(a, b, x, y, z, t)`**. Tính dễ đọc có phần ngữ nghĩa mà việc định dạng không thay thế được.

## 5. Chọn tên gọi theo mức độ đặc thù của bài toán

Người viết mã thường phải chọn giữa tên **chung, dễ tái sử dụng** và tên **đặc thù, mô tả đúng ý nghĩa**. Có thể ra quyết định theo bảng sau:

| Nhu cầu | Tên quá chung hoặc dễ gây nhầm | Tên hoặc cấu trúc rõ hơn | Lý do |
| --- | --- | --- | --- |
| Kiểm tra xung đột đặt sân | `check`, `validate` | `conflictsWith` | Cho biết câu hỏi được trả lời. |
| Khoảng có điểm cuối không được tính | `end`, `to` | `endsAtExclusive` | Tránh sai ở ranh giới. |
| Trạng thái có thể hủy đặt sân | `active`, `statusFlag` | `canCancel` hoặc `cancellationEligibility` theo hợp đồng | Không đánh đồng “đang hoạt động” với “được phép hủy”. |
| Tổng tiền dùng cho quy tắc ngưỡng | `amount`, `value` | `subtotalVnd` nếu đó là tổng tiền hàng bằng VND | Cho biết loại tiền và đơn vị. |
| Khóa nhận dạng sân | `id`, `key` trong API nhiều thực thể | `courtId` | Phân biệt sân với mã đặt chỗ hay người dùng. |
| Phép so sánh thời gian dùng cho nhiều bài toán | `CourtBookingHelper` | `TimeInterval` nếu thực sự không phụ thuộc đặt sân | Tránh đưa quy tắc nghiệp vụ vào tiện ích tổng quát. |

Một tên dài hơn đôi khi rất đáng giá vì nó mang **ràng buộc khó đoán**, chẳng hạn `endsAtExclusive` hoặc `subtotalVnd`. Tuy nhiên, không phải cứ thêm nhiều từ là tốt. Nếu tên thành `theCurrentCourtBookingEndingDateTimeForBusinessValidation`, người đọc lại phải xử lý thông tin thừa. Chọn **cụ thể vừa đủ** để người đọc hiểu điều có thể ảnh hưởng đến kết quả.

### Thuật ngữ phải thống nhất giữa các bên

Nếu nhóm nghiệp vụ dùng từ **lượt đặt (booking)** và **khung giờ (slot)** để chỉ hai khái niệm khác nhau, mã cũng nên phân biệt. Đừng dùng `reservation`, `booking`, `schedule`, `slot` thay thế cho nhau chỉ để tránh lặp từ. Một thuật ngữ có cùng nghĩa trong tài liệu, API và mã sẽ giảm hiểu nhầm; ngược lại, khi nghĩa khác nhau phải thể hiện sự khác biệt bằng tên hoặc hợp đồng.

Nếu một thuật ngữ có cách dịch hoặc viết tắt phổ biến trong nhóm, nên chốt một cách dùng, ví dụ `sku` cho mã hàng khi đó là khái niệm chuẩn của miền nghiệp vụ. Nhưng các viết tắt chỉ một vài người hiểu như `bkSt` hoặc `rtFlg` làm giảm khả năng đọc của người mới. Quy ước viết tắt cần có phạm vi và lý do rõ.

## 6. Giữ nhất quán giữa các lớp, tôn trọng hợp đồng bên ngoài

Hệ thống thường có nhiều lớp với quy ước khác nhau. Ví dụ cơ sở dữ liệu dùng `snake_case`, Java dùng `camelCase`, còn một API bên ngoài có thể dùng tên trường đã công bố trước đó:

| Lớp / hợp đồng | Ví dụ | Cách cân bằng |
| --- | --- | --- |
| Cơ sở dữ liệu | `court_id`, `starts_at` | Giữ tên cột theo chuẩn schema; ánh xạ rõ sang kiểu nội bộ. |
| Java | `courtId`, `startsAt` | Dùng quy ước Java và thuật ngữ nghiệp vụ thống nhất. |
| JSON từ API đối tác | `court_id`, `start_time` | Giữ hợp đồng đã thỏa thuận; ánh xạ tại ranh giới API. |
| Thông điệp hiển thị cho người dùng | “Khung giờ này đã có người đặt” | Dùng ngôn ngữ mà người dùng hiểu, không lộ tên class/exception. |

Không cần đổi tên API của đối tác thành `courtId` chỉ để tương tự biến Java nếu điều đó phá vỡ tương thích. Cũng không cần mang `snake_case` vào toàn bộ mã Java chỉ vì cơ sở dữ liệu đang dùng kiểu đó. Một tầng ánh xạ nhỏ, được đặt tên rõ, giúp mỗi bên tuân theo quy ước phù hợp và tránh làm rò rỉ chi tiết hạ tầng vào nghiệp vụ.

Tương tự, khi framework yêu cầu một cách viết đặc thù (ví dụ tên phương thức hoặc cấu trúc DTO), nên **cô lập yêu cầu ấy ở phần tích hợp**. Phần triển khai quy tắc nghiệp vụ nên giữ cách biểu đạt dễ hiểu nhất cho người bảo trì.

## 7. Khi nào có thể tạo ngoại lệ đối với quy ước?

Quy ước chung giúp giảm biến thể, nhưng không phải luật bất biến. Một ngoại lệ hợp lý cần có lý do mà người khác có thể kiểm tra được. Ví dụ:

- **Tương thích hợp đồng:** tên trường từ API hoặc schema đã công bố không thể đổi tùy ý; giữ nguyên ở ranh giới và ánh xạ nội bộ.
- **Thuật ngữ chuyên môn ổn định:** tên như `IBAN`, `SKU`, `VAT` có thể có cách viết riêng theo quy ước thực tế của nhóm và công cụ; nhất quán cách sử dụng trong phạm vi liên quan.
- **Công thức toán học ngắn, thông dụng:** trong một phạm vi rất hẹp, `x`, `y`, `i` có thể rõ hơn tên dài khi vai trò đã được định nghĩa; điều này không biện minh cho những tên mơ hồ trong API công khai.
- **Ràng buộc kỹ thuật có bằng chứng:** một đoạn mã hiệu năng cao có thể cần bố cục ít quen thuộc, nhưng phải ghi rõ lý do và có benchmark hoặc kiểm thử phù hợp. Tránh hy sinh khả năng đọc chỉ vì tối ưu hóa chưa đo được.

Trước khi chấp nhận ngoại lệ, hãy trả lời ba câu hỏi: **quy ước nào đang bị lệch, lợi ích cụ thể là gì, và người đến sau sẽ hiểu ngoại lệ này từ đâu?** Nếu không có câu trả lời thuyết phục, quay về cách viết đã thống nhất thường là lựa chọn dễ duy trì hơn.

Một chú thích hữu ích giải thích **vì sao**, thay vì nhắc lại **đoạn mã làm gì**:

```java
// Khoảng đặt dùng [bắt đầu, kết thúc); hai lượt đặt chạm ranh giới
// có thể xếp liên tiếp theo chính sách của cơ sở.
return firstStart.isBefore(secondEnd)
        && secondStart.isBefore(firstEnd);
```

Chú thích này có giá trị vì lưu lại quyết định nghiệp vụ về ranh giới. Nếu hợp đồng có tài liệu chính thức, có thể liên kết đến quy tắc đó tại vị trí phù hợp; tránh rải cùng một bản mô tả dài ở nhiều nơi vì khó đồng bộ khi chính sách đổi.

## 8. Dùng công cụ và review vào đúng mục đích

Một số vấn đề về khả năng đọc có thể được kiểm tra tự động, số khác cần người hiểu bối cảnh đánh giá:

| Cách kiểm tra | Hữu ích để xác nhận | Không thể tự kết luận |
| --- | --- | --- |
| Formatter, lint, Checkstyle | Thụt lề, cách viết tên, độ dài dòng, quy tắc dự án | `conflictsWith` có phản ánh đúng định nghĩa trùng lịch không? |
| Static analysis | Mẫu lỗi, nhánh rối, độ phức tạp bất thường | Tên nào đúng với thuật ngữ mà khách hàng sử dụng? |
| Unit test và kiểm thử ranh giới | Hành vi ở một tập tình huống đã chọn | Quy tắc nghiệp vụ được nhóm hiểu đúng ngay từ đầu chưa? |
| Code review với ngữ cảnh | Tên gọi, ranh giới trách nhiệm, sự phù hợp với mã xung quanh | Đảm bảo mọi lỗi đều bị phát hiện hoặc sản phẩm không còn rủi ro. |
| Tài liệu yêu cầu và ví dụ nghiệp vụ | Ý nghĩa của thuật ngữ và điều kiện biên | Mã chạy chính xác trong mọi điều kiện vận hành. |

Khi review, có thể hỏi theo thứ tự:

1. **Người đọc hiểu quy tắc chưa?** Có thể diễn đạt điều kiện trong mã thành một câu nghiệp vụ không? Tên có khớp nghĩa với câu đó không?
2. **Mã có nhất quán với dự án không?** Các tên và cấu trúc tương tự được dùng nhất quán ở những nơi cùng trách nhiệm không?
3. **Có giả định quan trọng nào bị ẩn?** Múi giờ, đơn vị tiền, quyền truy cập, ranh giới bao gồm/loại trừ, trạng thái hợp lệ có được ghi rõ không?
4. **Có đưa sự phức tạp vào sai chỗ không?** Quy tắc miền nghiệp vụ có bị nhốt trong utility chung, controller hay mapper chỉ vì nhóm quen cách tổ chức đó không?
5. **Có thể kiểm chứng hành vi không?** Test đã bao gồm các trường hợp phân biệt rõ quy tắc chưa, hay chỉ kiểm tra đường đi thông thường?

Một review hiệu quả nên nêu đề xuất cụ thể như “`endsAtExclusive` sẽ giúp phân biệt quy tắc khoảng nửa mở” hơn là nhận xét mơ hồ “đặt tên đẹp hơn”. Với những tranh luận thuần định dạng, sử dụng cấu hình formatter chung sẽ tiết kiệm thời gian hơn.

## 9. Các ngộ nhận thường gặp

**“Tuân thủ convention là mã đã dễ đọc.”** Định dạng và quy tắc đặt tên chỉ tạo sự nhất quán về hình thức. Người đọc còn cần hiểu mô hình dữ liệu, điều kiện nghiệp vụ và các trường hợp biên.

**“Tên càng gần từ chuyên môn thì càng tốt.”** Một từ chuyên môn chỉ hữu ích khi nhóm sử dụng nó với nghĩa ổn định. Dùng nhiều từ viết tắt ít người biết, hoặc tên lĩnh vực không phản ánh trách nhiệm thật, vẫn gây khó hiểu.

**“Cần đổi mọi tên thành thuật ngữ nghiệp vụ.”** Lớp xử lý kết nối, mã hóa hay sắp xếp tổng quát vẫn có thể dùng tên kỹ thuật thích hợp. Không nên cố gắn “đặt sân” vào một hàm tính toán có trách nhiệm độc lập với miền nghiệp vụ.

**“Mỗi trường hợp đặc biệt nên có một ngoại lệ coding style.”** Nhiều ngoại lệ nhỏ không có lý do sẽ tạo một hệ quy ước ngầm khó học. Chỉ lệch chuẩn khi có nhu cầu cụ thể, giải thích được và kiểm soát được phạm vi.

**“Viết thêm comment sẽ sửa được tên khó hiểu.”** Chú thích nên ghi lại những giả định hoặc lý do khó thấy từ mã. Với một tên mơ hồ có thể đổi trực tiếp, đổi tên thường tốt hơn việc để người đọc liên tục đối chiếu chú thích.

**“Chỉ cần đặt tên tốt thì logic sẽ đúng.”** `conflictsWith` nghe rất rõ, nhưng vẫn có thể cài đặt sai ở điểm kết thúc hoặc quên điều kiện cùng sân. Kiểm thử và xác nhận đặc tả vẫn cần thiết.

## 10. Bài tập áp dụng

Hãy xem đoạn mã Java sau trong chức năng hủy lượt đặt:

```java
boolean process(Booking b, LocalDateTime t) {
    return b.getStatus() == Status.CONFIRMED
            && t.isBefore(b.getStartTime().minusHours(2));
}
```

Giả sử quy định nghiệp vụ là: **chỉ lượt đặt đã xác nhận được hủy và yêu cầu hủy phải đến sớm hơn ít nhất 2 giờ so với thời gian bắt đầu**, trong đó *đúng 2 giờ trước* cũng được chấp nhận.

Hãy trả lời:

1. Những tên nào khó hiểu dù vẫn hợp lệ về quy ước Java?
2. Điều kiện nào đang sai so với câu “ít nhất 2 giờ trước”?
3. Bạn sẽ đặt tên phương thức và tham số như thế nào để mô tả rõ quyết định nghiệp vụ?
4. Cần thêm ca kiểm thử ranh giới nào để bảo vệ quy tắc?

**Gợi ý:** `process` chưa nói điều gì, `b` và `t` không mô tả vai trò; có thể dùng `canCancel`, `booking`, `requestedAt`. Điều kiện `isBefore` loại trừ thời điểm đúng 2 giờ trước, nên nếu chính sách cho phép tại ranh giới cần dùng `!requestedAt.isAfter(booking.getStartTime().minusHours(2))`, hoặc biểu thức tương đương đã được kiểm thử. Kiểm tra ít nhất ba thời điểm: trước ngưỡng, đúng ngưỡng và sau ngưỡng; thêm trường hợp trạng thái không phải `CONFIRMED`. Lưu ý cách dùng giờ địa phương hay thời điểm tuyệt đối vẫn phải theo hợp đồng thời gian của ứng dụng.

## 11. Ghi nhớ

**Quy ước chung giúp mã quen thuộc; đặc điểm bài toán giúp mã có nghĩa.** Khả năng đọc tốt xuất hiện khi hai yếu tố hỗ trợ nhau: đặt tên và định dạng nhất quán, dùng thuật ngữ ổn định, đưa điều kiện quan trọng vào mô hình và bảo vệ những ranh giới dễ nhầm bằng kiểm thử. Khi cần lệch quy ước, hãy giữ phạm vi nhỏ và giải thích lý do. Mã chất lượng là mã mà người đến sau có thể **hiểu đúng quy tắc, kiểm chứng kết quả và thay đổi an toàn**.
