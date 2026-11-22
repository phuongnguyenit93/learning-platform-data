# Đổi tên và tổ chức lại mã để làm rõ ý định

Bạn được giao sửa một chức năng gửi nhắc nhở hóa đơn. Phương thức hiện tại chỉ có vài dòng, nhưng tên tham số là `s`, `d` và `n`; trạng thái hóa đơn được biểu diễn bằng số `1`; còn điều kiện ngày đến hạn dùng hai phép so sánh phủ định. Người viết ban đầu hiểu đoạn mã, nhưng người bảo trì phải mở comment và tự tính xem hóa đơn nào sẽ được nhắc.

Yêu cầu lần này rất nhỏ: **làm cho mã thể hiện rõ ý định mà vẫn giữ nguyên hành vi đã được xác nhận**. Bạn sẽ thực hành đọc hợp đồng, ghi nhận hành vi, đổi tên theo ngôn ngữ nghiệp vụ, thay mã số bằng kiểu có tên, tách quy tắc thành thành phần phù hợp và viết test cho các giá trị biên.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Ở chương **Thực hành**, bài này là một bài tập có hướng dẫn về **đổi tên và tổ chức lại mã để làm rõ ý định**. Trọng tâm là làm cho người đọc hiểu được mục đích từ tên, kiểu và cấu trúc, đồng thời dùng kiểm thử để phát hiện thay đổi hành vi ngoài dự kiến.

## Mục tiêu thực hành

Sau bài tập, bạn có thể:

- Đọc mã hiện hữu và diễn đạt quy tắc của nó bằng ngôn ngữ nghiệp vụ.
- Phân biệt **ghi nhận hành vi hiện tại** với **xác nhận hành vi đúng theo yêu cầu**.
- Đổi tên lớp, phương thức, tham số và hằng số để giảm nhu cầu dựa vào comment.
- Thay mã trạng thái khó hiểu bằng `enum` và đóng gói dữ liệu liên quan bằng `record`.
- Tách một quy tắc nghiệp vụ vào thành phần có trách nhiệm rõ ràng mà không tạo thêm abstraction vô ích.
- Viết JUnit 5 tests cho đường bình thường, trạng thái từ chối, giá trị biên và đầu vào không hợp lệ.
- Review diff để xác nhận refactor giữ đúng hợp đồng và cải thiện khả năng bảo trì.

## 1. Bối cảnh và hợp đồng của bài tập

Ứng dụng có chức năng gửi nhắc nhở cho hóa đơn sắp đến hạn. Chính sách nghiệp vụ **đã được xác nhận cho bài tập này**:

1. Chỉ hóa đơn ở trạng thái **ISSUED** mới được xét gửi nhắc nhở.
2. Hóa đơn được nhắc nếu ngày đến hạn nằm trong khoảng **từ hôm nay đến hết ba ngày tiếp theo**, tính cả hai đầu mút.
3. Hóa đơn có ngày đến hạn trước hôm nay không thuộc chính sách nhắc sắp đến hạn này.
4. Hóa đơn ở trạng thái DRAFT, PAID hoặc CANCELLED không được nhắc.
5. Trạng thái và ngày đến hạn bắt buộc phải có; nếu thiếu thì từ chối ngay tại ranh giới bằng `NullPointerException`.
6. Phương thức chỉ **quyết định có cần nhắc hay không**. Nó không gửi email, không cập nhật hóa đơn và không ghi log.

Các mã trạng thái cũ được quy ước như sau:

| Mã cũ | Ý nghĩa |
| ---: | --- |
| 0 | DRAFT — bản nháp |
| 1 | ISSUED — đã phát hành |
| 2 | PAID — đã thanh toán |
| 3 | CANCELLED — đã hủy |

Ngày hiện tại được truyền vào phương thức thay vì đọc trực tiếp từ đồng hồ hệ thống. Cách này giúp quy tắc có thể kiểm thử với ngày cố định và không phụ thuộc thời điểm máy chạy.

## 2. Mã ban đầu: chạy được nhưng khó hiểu

Đây là phiên bản hiện tại của chức năng:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public final class ReminderService {
    public boolean check(int s, LocalDate d, LocalDate n) {
        Objects.requireNonNull(d, "d");
        Objects.requireNonNull(n, "n");

        // 0 = draft, 1 = issued, 2 = paid, 3 = cancelled.
        // Chỉ nhắc hóa đơn đã phát hành trong ba ngày tới.
        if (s != 1) {
            return false;
        }
        return !d.isBefore(n) && !d.isAfter(n.plusDays(3));
    }
}
~~~

Đoạn mã này không nhất thiết có lỗi với hợp đồng đã nêu, nhưng người đọc phải nhớ:

- `ReminderService` đang chịu trách nhiệm gì ngoài việc quyết định có nhắc?
- `check` kiểm tra điều kiện nào?
- `s` là trạng thái nào và mã `1` có nghĩa gì?
- `d` là ngày nào: ngày phát hành, ngày đến hạn hay ngày thanh toán?
- `n` là ngày hiện tại hay ngày kế tiếp?
- Vì sao dùng hai phép phủ định `isBefore` và `isAfter`?
- Ba ngày có tính cả ngày thứ ba hay không?

Comment đang làm nhiệm vụ giải mã một phần tên và giá trị. Người gọi cũng khó hiểu ý nghĩa:

~~~java
boolean result = reminderService.check(1, dueDate, today);
~~~

Một lời gọi rõ hơn nên cho người đọc thấy ngay **đang kiểm tra điều kiện gửi nhắc hóa đơn**.

## 3. Bước 1 — Viết lại hợp đồng trước khi sửa mã

Trước khi đổi tên hoặc tách hàm, hãy chuyển chính sách thành bảng quyết định. Đây là cơ sở để xác định hành vi nào cần được giữ.

| Trạng thái | Ngày đến hạn | Ngày hiện tại | Kỳ vọng |
| --- | --- | --- | --- |
| ISSUED | Trước hôm nay 1 ngày | 10/05/2026 | Không nhắc |
| ISSUED | Đúng hôm nay | 10/05/2026 | Nhắc |
| ISSUED | Hôm nay + 3 ngày | 10/05/2026 | Nhắc |
| ISSUED | Hôm nay + 4 ngày | 10/05/2026 | Không nhắc |
| DRAFT | Hôm nay + 1 ngày | 10/05/2026 | Không nhắc |
| PAID | Hôm nay + 1 ngày | 10/05/2026 | Không nhắc |
| CANCELLED | Hôm nay + 1 ngày | 10/05/2026 | Không nhắc |

Hai ranh giới quan trọng là **hôm nay** và **hôm nay cộng ba ngày**. Nếu chỉ kiểm tra một hóa đơn có hạn sau một ngày, ta chưa biết phương thức có vô tình bao gồm ngày quá hạn hoặc loại trừ ngày cuối của cửa sổ nhắc hay không.

### Phân biệt hai loại test

- **Characterization test** ghi lại kết quả mà mã hiện tại tạo ra với những đầu vào đã chọn. Nó giúp phát hiện thay đổi ngoài ý muốn khi refactor.
- **Acceptance test** xác minh kết quả theo chính sách nghiệp vụ đã được xác nhận. Nếu mã cũ có bug, acceptance test có thể cố ý yêu cầu kết quả khác.

Trong bài này, bảng quyết định ở trên là hợp đồng nghiệp vụ. Không lấy biểu thức hiện tại làm nguồn duy nhất để tạo expected value.

## 4. Bước 2 — Viết test cho hành vi trước khi refactor

Dùng JUnit 5 để ghi nhận các trường hợp của phiên bản cũ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class ReminderServiceCharacterizationTest {
    private final ReminderService service = new ReminderService();
    private static final LocalDate TODAY =
        LocalDate.of(2026, 5, 10);

    static Stream<Arguments> existingBehavior() {
        return Stream.of(
            Arguments.of(1, TODAY.minusDays(1), false),
            Arguments.of(1, TODAY, true),
            Arguments.of(1, TODAY.plusDays(3), true),
            Arguments.of(1, TODAY.plusDays(4), false),
            Arguments.of(0, TODAY.plusDays(1), false),
            Arguments.of(2, TODAY.plusDays(1), false),
            Arguments.of(3, TODAY.plusDays(1), false)
        );
    }

    @ParameterizedTest
    @MethodSource("existingBehavior")
    void recordsCurrentResults(
            int statusCode, LocalDate dueDate, boolean expected) {
        assertEquals(expected, service.check(statusCode, dueDate, TODAY));
    }

    @Test
    void rejectsMissingDates() {
        assertThrows(
            NullPointerException.class,
            () -> service.check(1, null, TODAY)
        );
        assertThrows(
            NullPointerException.class,
            () -> service.check(1, TODAY, null)
        );
    }
}
~~~

Test dùng ngày cố định, không đọc `LocalDate.now()`. Vì thế kết quả không thay đổi theo ngày chạy CI. Các expected value được lấy từ bảng chính sách.

**Việc cần làm:** chạy test trên phiên bản ban đầu và xác nhận chúng đạt. Nếu có test thất bại, dừng refactor để tìm hiểu sự khác biệt giữa code và hợp đồng. Đừng sửa expected cho xanh chỉ vì implementation hiện tại cho kết quả khác.

## 5. Bước 3 — Đổi tên để nói đúng ý định

Hãy thay tên theo khái niệm nghiệp vụ:

| Tên cũ | Tên rõ hơn | Lý do |
| --- | --- | --- |
| `ReminderService` | `InvoiceReminderPolicy` | Thành phần chỉ quyết định chính sách nhắc |
| `check` | `shouldSendReminder` | Nói rõ câu hỏi mà phương thức trả lời |
| `s` | `statusCode` | Cho biết đây là mã trạng thái |
| `d` | `dueDate` | Nêu rõ ý nghĩa ngày |
| `n` | `today` | Nêu rõ ngày dùng để tính cửa sổ |
| `3` | `REMINDER_WINDOW_DAYS` | Đặt tên cho giới hạn ba ngày |

Sau bước đổi tên, chữ ký tạm thời có thể là:

~~~java
public boolean shouldSendReminder(
        int statusCode,
        LocalDate dueDate,
        LocalDate today) {
    Objects.requireNonNull(dueDate, "dueDate");
    Objects.requireNonNull(today, "today");

    if (statusCode != 1) {
        return false;
    }

    LocalDate lastReminderDate = today.plusDays(3);
    return !dueDate.isBefore(today)
        && !dueDate.isAfter(lastReminderDate);
}
~~~

Tên tham số và phương thức đã rõ hơn, nhưng mã vẫn còn hai vấn đề:

- `statusCode != 1` vẫn buộc người đọc nhớ mã số.
- Giá trị `3` vẫn chưa có tên và ý nghĩa ổn định.

Đổi tên là bước cải thiện hữu ích, nhưng **không nhất thiết là bước cuối cùng**.

### Khi nào cần giữ API cũ?

Nếu `ReminderService.check(...)` là API công khai đã được module khác sử dụng, đổi tên hoặc đổi kiểu tham số có thể phá vỡ tương thích. Khi đó:

1. Tìm caller và xác định phạm vi sử dụng.
2. Tạo API mới có tên rõ.
3. Chuyển caller theo từng bước.
4. Có thể giữ adapter/deprecated method trong giai đoạn chuyển đổi nếu chính sách dự án yêu cầu.
5. Chỉ xóa API cũ sau khi xác minh không còn consumer.

Không được coi việc rename là thay đổi nội bộ nếu chữ ký đó đã là hợp đồng với thành phần khác.

## 6. Bước 4 — Thay mã trạng thái bằng enum

Mã số `1` không diễn đạt ý nghĩa nghiệp vụ. Hãy tạo kiểu trạng thái:

~~~java
public enum InvoiceStatus {
    DRAFT,
    ISSUED,
    PAID,
    CANCELLED
}
~~~

Điều kiện trở nên rõ hơn:

~~~java
if (status != InvoiceStatus.ISSUED) {
    return false;
}
~~~

Nếu trạng thái được lưu trong database dưới dạng số, chuyển đổi mã cũ ở **ranh giới persistence** bằng mapper tường minh:

~~~java
public final class InvoiceStatusMapper {
    public InvoiceStatus fromLegacyCode(int statusCode) {
        return switch (statusCode) {
            case 0 -> InvoiceStatus.DRAFT;
            case 1 -> InvoiceStatus.ISSUED;
            case 2 -> InvoiceStatus.PAID;
            case 3 -> InvoiceStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown invoice status code: " + statusCode
            );
        };
    }
}
~~~

Mapper làm rõ cách dữ liệu cũ đi vào domain. Nếu gặp mã lạ, hệ thống báo lỗi rõ ràng thay vì mặc định coi đó là trạng thái không được nhắc. Việc ánh xạ cần được kiểm thử, đặc biệt nếu dữ liệu lịch sử có mã khác hoặc null.

**Không dùng `ordinal()` của enum làm mã lưu trữ bền vững.** Thứ tự enum có thể thay đổi khi thêm trạng thái. Dùng mapper hoặc mã ổn định được định nghĩa riêng.

## 7. Bước 5 — Đóng gói dữ liệu liên quan

Ba tham số rời rạc khiến caller có thể đảo thứ tự hoặc truyền dữ liệu không nhất quán. Có thể đóng gói trạng thái và ngày đến hạn vào một `record`:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public record Invoice(
    InvoiceStatus status,
    LocalDate dueDate
) {
    public Invoice {
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(dueDate, "dueDate");
    }
}
~~~

Lời gọi giờ thể hiện rõ đối tượng nghiệp vụ:

~~~java
Invoice invoice = new Invoice(
    InvoiceStatus.ISSUED,
    LocalDate.of(2026, 5, 13)
);

boolean shouldRemind =
    policy.shouldSendReminder(invoice, LocalDate.of(2026, 5, 10));
~~~

`record` phù hợp vì ví dụ cần một đối tượng dữ liệu nhỏ, bất biến theo tham chiếu và có accessor rõ. Nếu hóa đơn thật có vòng đời, hành vi và nhiều bất biến cần bảo vệ, có thể dùng một class domain đầy đủ thay vì nhồi mọi quy tắc vào record.

## 8. Bước 6 — Tổ chức quy tắc vào thành phần có trách nhiệm rõ

Tạo `InvoiceReminderPolicy` để sở hữu quy tắc quyết định có gửi nhắc:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public final class InvoiceReminderPolicy {
    private static final long REMINDER_WINDOW_DAYS = 3;

    public boolean shouldSendReminder(
            Invoice invoice,
            LocalDate today) {
        Objects.requireNonNull(invoice, "invoice");
        Objects.requireNonNull(today, "today");

        if (invoice.status() != InvoiceStatus.ISSUED) {
            return false;
        }

        LocalDate lastReminderDate =
            today.plusDays(REMINDER_WINDOW_DAYS);

        return !invoice.dueDate().isBefore(today)
            && !invoice.dueDate().isAfter(lastReminderDate);
    }
}
~~~

Đọc phương thức theo thứ tự:

1. Kiểm tra đối tượng và ngày hiện tại bắt buộc.
2. Từ chối ngay những trạng thái không phải ISSUED.
3. Tính ngày cuối cửa sổ nhắc.
4. Kiểm tra ngày đến hạn nằm trong khoảng bao gồm cả hôm nay và ngày cuối.

Tên `REMINDER_WINDOW_DAYS` làm rõ ý nghĩa của hằng số. Tên `lastReminderDate` cho biết ngày cuối là một mốc **được tính bao gồm**. Guard clause giúp người đọc nhìn thấy đường từ chối trước khi xem điều kiện ngày.

### Tại sao không tách mọi biểu thức thành helper?

Không nhất thiết tạo các phương thức như:

~~~java
private static boolean isIssued(Invoice invoice) {
    return invoice.status() == InvoiceStatus.ISSUED;
}

private static boolean isDueDateAfterToday(Invoice invoice, LocalDate today) {
    return !invoice.dueDate().isBefore(today);
}
~~~

Những helper này chỉ có ích nếu chúng đại diện cho khái niệm được dùng lại hoặc giúp che giấu một chi tiết phức tạp. Nếu mỗi phép so sánh đơn giản đều được bọc riêng, người đọc phải nhảy qua nhiều nơi để hiểu một quy tắc ngắn.

**Tách theo ý nghĩa và trách nhiệm**, không tách chỉ để giảm số dòng hoặc tạo thêm tên.

## 9. Bước 7 — Kiểm thử phiên bản đã refactor

Acceptance test cho chính sách mới:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.LocalDate;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class InvoiceReminderPolicyTest {
    private static final LocalDate TODAY =
        LocalDate.of(2026, 5, 10);

    private final InvoiceReminderPolicy policy =
        new InvoiceReminderPolicy();

    static Stream<Arguments> reminderCases() {
        return Stream.of(
            Arguments.of(
                InvoiceStatus.ISSUED, TODAY.minusDays(1), false
            ),
            Arguments.of(
                InvoiceStatus.ISSUED, TODAY, true
            ),
            Arguments.of(
                InvoiceStatus.ISSUED, TODAY.plusDays(3), true
            ),
            Arguments.of(
                InvoiceStatus.ISSUED, TODAY.plusDays(4), false
            ),
            Arguments.of(
                InvoiceStatus.DRAFT, TODAY.plusDays(1), false
            ),
            Arguments.of(
                InvoiceStatus.PAID, TODAY.plusDays(1), false
            ),
            Arguments.of(
                InvoiceStatus.CANCELLED, TODAY.plusDays(1), false
            )
        );
    }

    @ParameterizedTest
    @MethodSource("reminderCases")
    void appliesConfirmedReminderPolicy(
            InvoiceStatus status,
            LocalDate dueDate,
            boolean expected) {
        Invoice invoice = new Invoice(status, dueDate);

        assertEquals(expected, policy.shouldSendReminder(invoice, TODAY));
    }

    @Test
    void rejectsMissingRequiredValues() {
        assertThrows(
            NullPointerException.class,
            () -> policy.shouldSendReminder(null, TODAY)
        );
        assertThrows(
            NullPointerException.class,
            () -> policy.shouldSendReminder(
                new Invoice(InvoiceStatus.ISSUED, TODAY),
                null
            )
        );
        assertThrows(
            NullPointerException.class,
            () -> new Invoice(null, TODAY)
        );
        assertThrows(
            NullPointerException.class,
            () -> new Invoice(InvoiceStatus.ISSUED, null)
        );
    }
}
~~~

Test kiểm tra:

- Ngày quá khứ bị loại.
- Hôm nay được tính.
- Ngày cuối cửa sổ `today + 3` được tính.
- Ngày `today + 4` bị loại.
- Ba trạng thái không được nhắc đều bị loại.
- Giá trị bắt buộc bị thiếu được từ chối.

Kiểm thử mapper:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class InvoiceStatusMapperTest {
    private final InvoiceStatusMapper mapper = new InvoiceStatusMapper();

    @Test
    void mapsKnownLegacyCodes() {
        assertEquals(InvoiceStatus.DRAFT, mapper.fromLegacyCode(0));
        assertEquals(InvoiceStatus.ISSUED, mapper.fromLegacyCode(1));
        assertEquals(InvoiceStatus.PAID, mapper.fromLegacyCode(2));
        assertEquals(InvoiceStatus.CANCELLED, mapper.fromLegacyCode(3));
    }

    @Test
    void rejectsUnknownLegacyCode() {
        assertThrows(
            IllegalArgumentException.class,
            () -> mapper.fromLegacyCode(99)
        );
    }
}
~~~

Expected value trong test được lấy từ **hợp đồng ở đầu bài**, không gọi lại cùng biểu thức production để tính kết quả. Điều đó giúp test có khả năng phát hiện implementation sai.

## 10. Bài tập dành cho bạn

Hãy thực hiện refactor trên một nhánh riêng hoặc trong bài thực hành:

### Phần A — Đọc và ghi nhận

1. Chép lại hợp đồng nghiệp vụ bằng lời của bạn.
2. Đánh dấu tên nào không diễn đạt ý nghĩa: lớp, phương thức, tham số, hằng số.
3. Xác định những comment nào chỉ giải thích cú pháp hoặc mã số.
4. Liệt kê các trường hợp biên và trạng thái từ chối.
5. Viết characterization tests cho mã hiện tại.

### Phần B — Refactor

1. Đổi `ReminderService` và `check` sang tên có ý nghĩa.
2. Đổi tên tham số theo ngôn ngữ nghiệp vụ.
3. Thay status code bằng `InvoiceStatus`.
4. Đưa mapping mã cũ vào một mapper ở ranh giới persistence.
5. Tạo `Invoice` để gom status và due date.
6. Tách quy tắc vào `InvoiceReminderPolicy`.
7. Đặt tên cho cửa sổ ba ngày và dùng guard clause cho trạng thái không phù hợp.
8. Xóa comment lặp lại điều kiện đã rõ; giữ lại comment giải thích lý do nếu có quyết định không thể suy ra từ mã.

### Phần C — Xác minh

1. Chạy toàn bộ test trước và sau refactor.
2. So sánh kết quả cho cùng các đầu vào đã đặc tả.
3. Kiểm tra ngày hôm qua, hôm nay, ngày thứ ba và ngày thứ tư.
4. Kiểm tra tất cả trạng thái hóa đơn.
5. Kiểm tra null và mã trạng thái không hợp lệ ở đúng ranh giới.
6. Đọc diff để bảo đảm không vô tình thay đổi logic, API hoặc side effect.
7. Ghi lại điều đã xác minh và giới hạn còn lại.

## 11. Gợi ý đáp án và cách review kết quả

Một kết quả refactor hợp lý có thể có cấu trúc:

~~~text
Persistence / API boundary
        |
        v
InvoiceStatusMapper
        |
        v
Invoice(status, dueDate)
        |
        v
InvoiceReminderPolicy
        |
        v
shouldSendReminder(invoice, today)
~~~

### Tiêu chí đạt

| Tiêu chí | Dấu hiệu đạt |
| --- | --- |
| **Tên rõ nghĩa** | Người đọc biết lớp và phương thức chịu trách nhiệm gì mà không cần comment giải mã |
| **Kiểu dữ liệu phù hợp** | Trạng thái dùng enum; ngày đến hạn và ngày hiện tại dùng LocalDate |
| **Trách nhiệm rõ** | Mapping dữ liệu cũ tách khỏi chính sách nghiệp vụ |
| **Hợp đồng đầu vào** | Giá trị bắt buộc được kiểm tra tại ranh giới phù hợp |
| **Hành vi được giữ** | Các ca đã xác nhận cho kết quả đúng trước và sau refactor |
| **Giá trị biên** | Hôm nay và ngày cuối cửa sổ được kiểm thử |
| **Không trừu tượng hóa quá mức** | Helper chỉ được tạo khi làm rõ khái niệm hoặc giảm lặp có ý nghĩa |
| **Tương thích** | Caller và dữ liệu cũ được chuyển đổi có kiểm soát |
| **Comment có chất lượng** | Comment lặp cú pháp được bỏ; lý do thiết kế quan trọng được giữ |

### Những kết quả chưa đạt

- Chỉ đổi tên `s` thành `status` nhưng vẫn giữ mã số `1` rải rác ở nhiều nơi.
- Xóa comment nhưng không thay bằng tên hoặc kiểu dữ liệu rõ nghĩa.
- Tách mọi phép so sánh thành helper khiến luồng chính khó theo dõi.
- Thay `isAfter`/`isBefore` mà không có test biên.
- Đọc ngày hiện tại bằng `LocalDate.now()` bên trong policy khiến test phụ thuộc đồng hồ thật.
- Dùng `enum.ordinal()` để đọc/ghi mã trạng thái bền vững.
- Đưa việc gửi email vào `shouldSendReminder`, làm lẫn quyết định với side effect.
- Viết test chỉ gọi phương thức mà không assert kết quả.

## 12. Mở rộng: điều gì thay đổi khi quy tắc nghiệp vụ thay đổi?

Giả sử nghiệp vụ quyết định cửa sổ nhắc đổi từ **ba ngày** thành **năm ngày**.

Với thiết kế cũ, người sửa phải tìm xem số `3` xuất hiện ở những đâu và comment có còn đúng không. Với thiết kế mới, hằng số có tên `REMINDER_WINDOW_DAYS` cung cấp một điểm sửa rõ ràng.

Nhưng nếu cửa sổ nhắc khác nhau theo loại hóa đơn hoặc nhóm khách hàng, một hằng số toàn cục có thể không còn phù hợp. Khi đó cần xác định **ai sở hữu chính sách** và dữ liệu nào quyết định cửa sổ. Có thể cần một `ReminderPolicyConfiguration` hoặc một chiến lược riêng theo loại hóa đơn. Chỉ thêm abstraction khi yêu cầu thực sự xuất hiện, không xây trước một framework cấu hình phức tạp cho một quy tắc đơn giản.

Ví dụ về thay đổi có chủ đích:

~~~java
public record ReminderWindow(int days) {
    public ReminderWindow {
        if (days < 0) {
            throw new IllegalArgumentException("days must not be negative");
        }
    }
}
~~~

Nếu cửa sổ trở thành cấu hình, test cần xác minh cấu hình bằng 0, cấu hình hợp lệ và cấu hình không hợp lệ. Hành vi cũ chỉ được thay đổi khi chủ sở hữu nghiệp vụ xác nhận yêu cầu mới.

## 13. Checklist cuối trước khi hoàn thành refactor

- [ ] Tôi có thể giải thích quy tắc mà không dựa vào comment giải mã tên biến.
- [ ] Tên lớp, phương thức và tham số thể hiện ngôn ngữ nghiệp vụ.
- [ ] Các mã số hoặc chuỗi trạng thái đã được chuyển thành kiểu/hằng có tên phù hợp.
- [ ] Dữ liệu liên quan được gom thành abstraction có ý nghĩa, không chỉ để giảm số tham số.
- [ ] Mỗi thành phần có một trách nhiệm rõ và side effect được thể hiện đúng.
- [ ] Test có expected độc lập và bao phủ các giá trị biên quan trọng.
- [ ] Test trước và sau cho thấy hành vi đã xác nhận được giữ nguyên.
- [ ] Mapping từ dữ liệu cũ có kiểm tra mã không hợp lệ.
- [ ] API/caller được chuyển đổi có kiểm soát nếu chữ ký thay đổi.
- [ ] Comment lặp lại cú pháp được bỏ; lý do nghiệp vụ và ràng buộc khó suy ra được giữ.
- [ ] Diff không chứa thay đổi ngoài phạm vi refactor.

## Ghi nhớ

**Đổi tên và tổ chức lại mã để làm rõ ý định** bắt đầu bằng việc hiểu hợp đồng, sau đó đưa ý nghĩa vào tên, kiểu dữ liệu và cấu trúc trách nhiệm. Test giúp bảo vệ hành vi đã xác nhận trong khi thay đổi cách biểu đạt.

Một refactor tốt không được đánh giá bằng số dòng giảm hay số helper tăng. Hãy đánh giá bằng việc người đọc có hiểu nhanh hơn, người gọi có khó sử dụng sai hơn, quy tắc có một nơi chịu trách nhiệm rõ hơn và các hành vi quan trọng có được kiểm chứng hay không. **Mã tự diễn đạt tốt giảm nhu cầu giải mã bằng comment, còn kiểm thử giữ cho sự rõ ràng đó không phải đánh đổi bằng hành vi sai.**
