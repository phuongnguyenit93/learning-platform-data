# Bình luận lý do thay vì diễn lại từng câu lệnh

## 1. Bình luận có ích khi cung cấp thông tin mà mã nguồn chưa nói được

Người đọc thường hiểu một câu lệnh Java nhanh hơn khi biết tên biến, kiểu dữ liệu và luồng điều khiển. Chẳng hạn, nhìn thấy `remainingAttempts--`, họ có thể nhận ra số lần thử còn lại đang giảm. Bình luận `// Giảm số lần thử còn lại` chỉ lặp lại điều đã thể hiện trong mã. Nó tăng số chữ cần đọc nhưng không bổ sung kiến thức.

Điều khó hơn thường là những câu hỏi **vì sao**: tại sao chỉ thử lại hai lần? Vì sao giao dịch timeout được để ở trạng thái chờ thay vì đánh dấu thất bại? Vì sao một nhánh phải chạy trước nhánh khác? Vì sao vẫn chấp nhận một trường JSON cũ dù đã có trường mới? Những câu trả lời này có thể xuất phát từ quy tắc nghiệp vụ, ràng buộc tương thích, kinh nghiệm xử lý sự cố hoặc một đánh đổi kỹ thuật đã được kiểm chứng. Nếu không được ghi nhận, người đến sau dễ "dọn sạch" đoạn mã và vô tình làm hỏng một cam kết quan trọng.

Trong module `CODE_QUALITY_FUNDAMENTALS`, mục tiêu là **hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Ở chương **Tài liệu**, bài này tập trung vào nguyên tắc: **ưu tiên viết bình luận giải thích lý do, giả định và ràng buộc không hiển nhiên, thay vì diễn lại từng câu lệnh**.

Một bình luận tốt giúp người đọc phân biệt **điều có thể thay đổi tùy ý** với **điều phải giữ vì một cam kết nào đó**. Nhưng bình luận không thể cứu một cấu trúc quá rối, không thay thế được kiểm thử và không thể làm cho hành vi sai trở thành đúng chỉ bằng lời giải thích.

Sau bài học, bạn có thể:

- Nhận diện bình luận chỉ tường thuật mã, bình luận giải thích lý do và tài liệu hợp đồng công khai.
- Viết bình luận có đủ ngữ cảnh cho quyết định bất thường, ràng buộc tương thích, tính nhất quán và xử lý lỗi.
- Chọn khi nào nên đổi tên, trích xuất phương thức, viết test hoặc tài liệu thiết kế thay vì thêm bình luận.
- Viết Javadoc và bình luận Java sao cho chúng không mâu thuẫn với hành vi thật.
- Review và cập nhật bình luận như một phần của thay đổi mã nguồn.

## 2. Phân biệt “what”, “how”, “why” và “contract”

Bình luận thường bị đánh giá chỉ theo độ dài hoặc số lượng. Cách hữu ích hơn là xem **nó mang loại thông tin gì và người đọc có lấy được thông tin ấy từ code không**.

| Loại thông tin | Câu hỏi | Nguồn thể hiện tốt |
| --- | --- | --- |
| **What — đang làm gì** | Đây là phép kiểm tra, phép cộng hay lời gọi nào? | Tên hàm, tên biến, kiểu dữ liệu và cấu trúc |
| **How — thực hiện thế nào** | Thuật toán, dữ liệu và các bước xử lý ra sao? | Mã nguồn, test, tài liệu thuật toán khi thực sự phức tạp |
| **Why — vì sao lựa chọn như vậy** | Ràng buộc, đánh đổi, sự cố hay quy tắc ngầm nào khiến cách này cần thiết? | Bình luận ngắn, tài liệu quyết định, tham chiếu được kiểm chứng |
| **Contract — bên gọi có thể dựa vào điều gì** | Đầu vào hợp lệ, đầu ra, ngoại lệ, tác dụng phụ, trạng thái nào? | Chữ ký, kiểu dữ liệu, Javadoc, API spec và contract test |

Nguyên tắc “bình luận lý do” **không có nghĩa cấm mô tả hành vi**. Public API vẫn cần Javadoc về những gì bên gọi được phép kỳ vọng, nhất là nơi kiểu Java chưa diễn đạt hết hành vi. Một thuật toán khó cũng có thể cần chú thích về bất biến, cách chia pha hoặc trường hợp biên. Nhưng ở **bên trong thân phương thức**, nơi code đã nói rõ từng bước, bình luận tường thuật sẽ nhanh trở thành nhiễu.

Ví dụ:

```java
// Tăng biến index lên 1.
index++;

// Kiểm tra tổng tiền có lớn hơn hoặc bằng ngưỡng.
if (subtotal.compareTo(freeShippingThreshold) >= 0) {
    // Đặt phí giao hàng bằng 0.
    fee = BigDecimal.ZERO;
}
```

Những câu trên có thể bị xóa mà người đọc không mất thông tin nào. Trong khi đó:

```java
// Quy tắc khuyến mãi hiện tại tính cả giá trị đúng bằng ngưỡng;
// việc đổi >= thành > sẽ thu phí sai cho đơn ở đúng ranh giới.
if (subtotal.compareTo(freeShippingThreshold) >= 0) {
    fee = BigDecimal.ZERO;
}
```

Bình luận thứ hai làm rõ **điểm biên cần giữ**, nhưng cũng phải cân nhắc: một test tên `freeAtExactThreshold` có thể là bằng chứng mạnh và bền hơn. Có thể giữ bình luận nếu quyết định biên thường bị hiểu nhầm; không cần lặp lại những gì test và tên đã giải thích đủ rõ.

## 3. Dấu hiệu bình luận chỉ kể lại mã nguồn

### 3.1. Bình luận lặp nguyên câu lệnh

```java
// Lấy người dùng theo ID.
User user = userRepository.findById(userId);

// Kiểm tra người dùng có null không.
if (user == null) {
    // Trả về false.
    return false;
}
```

Những bình luận này tạo thêm một lớp văn bản phải duy trì. Nếu đổi implementation sang `Optional<User>`, bình luận cũ có thể sai hoặc trở nên lạc chỗ. Cách tốt hơn là dùng tên và luồng xử lý đủ rõ, đồng thời xác định hợp đồng "không tìm thấy" ở ranh giới thích hợp.

### 3.2. Bình luận che tên gọi mơ hồ

```java
// d là số ngày khách hàng đã là thành viên.
if (d > 30 && !f) {
    // ...
}
```

Nếu có thể đổi `d` thành `membershipDays` và `f` thành `hasActivePromotion`, người đọc sẽ hiểu ngay tại mọi nơi sử dụng, không chỉ tại một dòng chú thích. Bình luận chỉ cần giữ lại những điều **không thể đoán chính xác từ tên**, ví dụ “khuyến mãi không được cộng dồn theo điều khoản hợp đồng”.

### 3.3. Bình luận mô tả điều mong muốn, không phải điều đang xảy ra

```java
// Luôn xử lý thanh toán đúng một lần.
gateway.charge(request);
```

Lời khẳng định này không chứng minh lời gọi `charge` có idempotency. Nếu client thử lại sau timeout, gateway có thể thực hiện hai giao dịch. Một bình luận khẳng định bảo đảm không có thật **nguy hiểm hơn việc không có bình luận**, vì nó gây tự tin sai.

Những tuyên bố về an toàn, tính nguyên tử, tính nhất quán hoặc đồng thời phải được **thực thi bằng thiết kế và kiểm chứng bằng test phù hợp**, không chỉ viết thành comment.

### 3.4. Bình luận thừa dễ lỗi thời

Càng có nhiều lời diễn giải chi tiết từng câu lệnh, càng nhiều chỗ cần cập nhật khi refactor. Đoạn mã có thể thay đổi nhưng người sửa quên sửa chú thích; người đọc sau đó phải lựa chọn tin code hay tin comment. Hãy giảm số thông tin được sao chép ở nhiều nơi mà không có cách kiểm chứng.

**Câu hỏi thực hành:** Nếu xóa bình luận này, người đọc có mất một lý do, giả định, ràng buộc hoặc hợp đồng quan trọng không? Nếu không, nhiều khả năng bình luận nên được xóa hoặc thông tin nên được chuyển sang tên/kiểu rõ hơn.

## 4. Những tình huống nên ghi rõ “vì sao”

Không phải mọi quyết định đều cần một bình luận. Ưu tiên những nơi **hành vi trông bất thường** hoặc **người sửa có nguy cơ chọn một cách có vẻ hợp lý nhưng thực tế sai**.

| Tình huống | Điều bình luận có giá trị nên nói | Điều không nên chỉ nói |
| --- | --- | --- |
| Quy tắc nghiệp vụ khó suy ra | Ai/điều kiện nào quyết định thứ tự ưu tiên hoặc ranh giới | “Kiểm tra điều kiện đầu tiên” |
| Tương thích ngược | Client/phiên bản cũ nào cần hợp đồng này, khi nào có thể bỏ | “Để tương thích” không có phạm vi |
| Lỗi bên thứ ba | Giới hạn đã được xác nhận và giải pháp vòng tránh | “Hack vì SDK lỗi” |
| Tính đồng thời | Bất biến phải giữ, vì sao cần lock/giao dịch/khóa duy nhất | “Khóa để tránh lỗi” |
| Timeout/retry | Vì sao không được kết luận thành công hoặc thất bại khi thiếu phản hồi | “Retry nếu có lỗi” |
| Hiệu năng | Phép đo nào cho thấy đường đi này có ảnh hưởng, đánh đổi gì | “Dùng map cho nhanh” |
| Bảo mật/quyền | Ranh giới tin cậy và nguy cơ nếu bỏ kiểm tra | “Kiểm tra security” |
| Dữ liệu lịch sử | Tại sao vẫn đọc định dạng cũ và tiêu chí xóa đường hỗ trợ | “Đọc dữ liệu legacy” |
| Vận hành | Vì sao phải ghi trạng thái/audit trước một tác dụng phụ | “Ghi log” |
| Quy tắc thời gian | Múi giờ, mốc tính, có tính đúng tại deadline hay không | “Kiểm tra ngày” |

Ví dụ minh họa một ràng buộc tương thích:

```java
// Mobile 2.x vẫn gửi "customer_id"; trong giai đoạn chuyển đổi,
// API phải chấp nhận cả hai tên. Chỉ bỏ alias sau khi xác nhận
// các phiên bản được hỗ trợ không còn sử dụng trường cũ.
String customerId = firstNonBlank(
        payload.get("customerId"),
        payload.get("customer_id"));
```

Ở đây, `firstNonBlank` là hàm minh họa cho quy tắc chọn giá trị, không có implementation trong ví dụ. Đoạn code production còn phải định nghĩa cách xử lý khi **cả hai trường cùng có nhưng khác nhau**; nếu không, việc chọn tùy thứ tự có thể che dữ liệu mâu thuẫn. Bình luận giúp giải thích vì sao alias còn tồn tại; test contract phải bảo vệ cách đọc dữ liệu cũ.

## 5. Ví dụ Java xuyên suốt: bình luận quyết định về deadline, không tường thuật phép so sánh

### 5.1. Yêu cầu và điểm dễ hiểu sai

Giả sử một hệ thống có chính sách **hoàn trả trong vòng 72 giờ kể từ thời điểm thanh toán đã được xác nhận**. Theo quyết định nghiệp vụ **giả định của bài học**, yêu cầu được tạo **đúng tại thời điểm hết hạn** vẫn hợp lệ; sau thời điểm đó thì không.

Hai chi tiết không hiển nhiên:

1. Mốc bắt đầu là **thời điểm đã xác nhận thanh toán**, không phải lúc người dùng bấm nút đặt hàng.
2. Ranh giới **bao gồm** đúng thời điểm hết hạn; đổi phép so sánh từ `isAfter` sang `!isBefore` ở sai chỗ có thể đảo quy tắc.

Một phiên bản có nhiều comment tường thuật:

```java
// Tạo duration 72 giờ.
Duration window = Duration.ofHours(72);
// Cộng thời gian vào thời điểm thanh toán.
Instant deadline = capturedAt.plus(window);
// Kiểm tra evaluatedAt có sau deadline không.
return !evaluatedAt.isAfter(deadline);
```

Những câu này mô tả cú pháp. Chúng không nói vì sao mốc thanh toán được chọn hoặc tại sao có dấu bằng ở ranh giới.

### 5.2. Ví dụ có hợp đồng rõ và một bình luận thật sự giải thích lý do

Đặt mã Java 17+ sau trong tệp `RefundWindowPolicy.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RefundWindowPolicy {
    private static final Duration WINDOW = Duration.ofHours(72);

    private RefundWindowPolicy() {}

    /**
     * Kiểm tra yêu cầu hoàn trả có nằm trong cửa sổ 72 giờ
     * từ lúc giao dịch được xác nhận thu tiền hay không.
     *
     * @param capturedAt mốc xác nhận thu tiền
     * @param evaluatedAt mốc đánh giá yêu cầu hoàn trả
     * @return true nếu evaluatedAt thuộc đoạn [capturedAt, capturedAt + 72 giờ]
     * @throws NullPointerException nếu một mốc thời gian là null
     * @throws IllegalArgumentException nếu evaluatedAt trước capturedAt
     */
    public static boolean isRefundRequestWithinWindow(
            Instant capturedAt, Instant evaluatedAt) {
        Objects.requireNonNull(capturedAt, "capturedAt");
        Objects.requireNonNull(evaluatedAt, "evaluatedAt");

        if (evaluatedAt.isBefore(capturedAt)) {
            throw new IllegalArgumentException(
                    "Evaluation cannot precede captured payment");
        }

        Instant deadline = capturedAt.plus(WINDOW);

        // Chính sách áp dụng cho cả yêu cầu đến đúng deadline.
        // Dùng isAfter để chỉ loại trừ các yêu cầu đến MUỘN HƠN mốc này.
        return !evaluatedAt.isAfter(deadline);
    }
}
```

Trong ví dụ:

- Tên `capturedAt` nói rõ mốc bắt đầu, thay vì `createdAt` chung chung.
- Kiểu `Instant` tách mốc thời gian khỏi thời lượng `Duration`.
- Javadoc diễn đạt **hợp đồng công khai**: dữ liệu vào, đoạn thời gian được chấp nhận, ngoại lệ.
- Bình luận trong thân phương thức giải thích **vì sao dùng biên bao gồm**, điểm người sửa có thể làm khác đi nếu chỉ nhìn toán tử.
- Code tự diễn đạt các bước cộng thời gian và so sánh, nên không cần diễn lại từng câu lệnh.

**Giới hạn của ví dụ:** cửa sổ `Duration.ofHours(72)` là đúng 72 giờ theo trục thời gian liên tục, không mặc nhiên bằng “ba ngày lịch” ở mọi múi giờ và tình huống đổi giờ mùa. Nếu nghiệp vụ quy định ngày làm việc, thời gian mở cửa hoặc ngày lịch địa phương, cần mô hình khác. Việc dùng `Instant.plus` với giá trị cực hạn cũng có thể ném lỗi do tràn phạm vi thời gian.

### 5.3. Test diễn đạt quy tắc chính xác hơn bình luận đơn lẻ

```java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class RefundWindowPolicyTest {
    private final Instant capturedAt =
            Instant.parse("2026-11-16T08:00:00Z");

    @Test
    void acceptsRequestAtExactDeadline() {
        Instant deadline = capturedAt.plus(Duration.ofHours(72));

        assertTrue(RefundWindowPolicy.isRefundRequestWithinWindow(
                capturedAt, deadline));
    }

    @Test
    void rejectsRequestImmediatelyAfterDeadline() {
        Instant afterDeadline = capturedAt.plus(Duration.ofHours(72))
                .plusNanos(1);

        assertFalse(RefundWindowPolicy.isRefundRequestWithinWindow(
                capturedAt, afterDeadline));
    }

    @Test
    void acceptsRequestBeforeDeadline() {
        Instant beforeDeadline = capturedAt.plus(Duration.ofHours(71));

        assertTrue(RefundWindowPolicy.isRefundRequestWithinWindow(
                capturedAt, beforeDeadline));
    }

    @Test
    void rejectsInvalidOrderOfTimePoints() {
        Instant beforeCapture = capturedAt.minusSeconds(1);

        assertThrows(IllegalArgumentException.class, () ->
                RefundWindowPolicy.isRefundRequestWithinWindow(
                        capturedAt, beforeCapture));
    }
}
```

Test tạo bằng chứng thực thi cho hợp đồng tại biên. Nếu ai đó đổi `!evaluatedAt.isAfter(deadline)` thành `evaluatedAt.isBefore(deadline)`, ca đúng deadline sẽ thất bại. Bình luận giúp người đọc hiểu quyết định; test giúp **phát hiện sự thay đổi phá quyết định**. Chúng bổ trợ, không thay thế hoàn toàn cho nhau.

## 6. Javadoc là tài liệu hợp đồng, không phải nơi chép code

Bình luận nội bộ thường giải thích lý do của một lựa chọn. **Javadoc cho API công khai** cần cung cấp thông tin bên gọi phải biết để sử dụng đúng. Vì vậy Javadoc có thể mô tả *what* và *contract*, miễn là nó cung cấp nội dung chưa tự suy ra đầy đủ từ tên và kiểu dữ liệu.

Ví dụ:

```java
/**
 * Tìm hóa đơn đã lưu theo mã.
 *
 * <p>Không tìm thấy là kết quả bình thường và trả Optional.empty().
 * Lỗi truy cập cơ sở dữ liệu không được chuyển thành Optional.empty().
 *
 * @param invoiceId mã hóa đơn không được null hoặc rỗng
 * @return hóa đơn nếu tồn tại
 * @throws IllegalArgumentException nếu mã rỗng
 */
Optional<Invoice> findById(String invoiceId);
```

Đoạn trên là **phác thảo hợp đồng**; `Invoice` và implementation cần được định nghĩa riêng. Nó hữu ích vì phân biệt rõ “không tìm thấy” với “đọc dữ liệu thất bại”. Nếu thiếu điều này, người gọi có thể coi mọi `Optional.empty()` là không có hóa đơn và âm thầm bỏ qua sự cố.

Một số thông tin Javadoc thường đáng ghi:

| Đặc điểm API | Thông tin có giá trị |
| --- | --- |
| Đầu vào | Ý nghĩa, đơn vị, giá trị hợp lệ, `null` có chấp nhận không |
| Kết quả | Điều gì được xác nhận, thiếu dữ liệu biểu diễn ra sao |
| Ngoại lệ | Điều kiện ném ngoại lệ và cách caller phản ứng |
| Tác dụng phụ | Ghi database, phát sự kiện, tác động hệ thống ngoài |
| Thread safety | Có an toàn khi gọi đồng thời hay cần đồng bộ không |
| Bất đồng bộ | Khi nào trả về, kết quả là “đã nhận” hay “đã hoàn tất” |
| Tính lặp an toàn | Gọi lại với cùng request ID có ý nghĩa gì |
| Tương thích | Hành vi cũ nào vẫn được hỗ trợ và giới hạn của nó |

Với public API, ví dụ sử dụng nhỏ có thể hữu ích hơn nhiều dòng diễn giải câu lệnh nội bộ. Nhưng đừng biến Javadoc thành một bản sao của implementation: thay đổi thuật toán không làm đổi hợp đồng thì không nên buộc phải sửa toàn bộ tài liệu.

### 6.1. Lưu ý về comment trong Java

- `// ...` phù hợp với một lý do ngắn gần quyết định.
- `/* ... */` có thể phù hợp với ghi chú nhiều dòng nhưng không nên dùng để giải thích cả phương thức vốn có thể tách thành các phần rõ nghĩa.
- `/** ... */` dùng cho Javadoc và có ý nghĩa ở hợp đồng API; hỗ trợ các thẻ `@param`, `@return`, `@throws`...
- Bình luận nhiều dòng đặt ở một vị trí cố định có thể bị tách khỏi code trong refactor; review cần kiểm tra nó còn đúng với phạm vi sau sửa.

Không phải phương thức private nào cũng cần Javadoc, cũng không phải API công khai nào cũng cần bình luận dài. Hãy xem **có những cam kết không hiển nhiên nào người gọi phải biết**.

## 7. Ghi nhận quyết định kỹ thuật: đủ ngữ cảnh, đủ bằng chứng

Một lý do đôi khi lớn hơn một dòng code. Ví dụ: nhóm giữ lại một adapter cũ vì ứng dụng di động có lịch cập nhật dài; nhóm chọn cơ chế outbox để tránh mất sự kiện giữa thao tác ghi và publish; hoặc nhóm giữ một truy vấn SQL phức tạp vì cách đơn giản hơn gây tăng tải đã được đo.

Bình luận nên giải thích ngắn gọn ở nơi hành vi xuất hiện, nhưng **chi tiết dài** có thể nằm trong issue, ADR (*Architecture Decision Record*), runbook hoặc tài liệu thiết kế. Một cách làm thực dụng là tạo mối liên hệ rõ giữa code và quyết định.

### 7.1. Cấu trúc cho một bình luận quyết định có giá trị

Cân nhắc bốn thành phần, chỉ viết những phần thực sự cần:

1. **Bối cảnh:** tình huống hoặc ràng buộc nào khiến cách viết hiện tại không hiển nhiên?
2. **Lý do:** nguy cơ hay cam kết nào cần bảo vệ?
3. **Giới hạn:** khi nào cách xử lý này còn đúng; giả định nào có thể thay đổi?
4. **Điểm xác minh:** test, issue, số đo hoặc tài liệu nào giúp người sau kiểm tra lại?

Ví dụ **giả định** về giới hạn từ một bên thứ ba:

```java
// Đối tác A có thể gửi callback trùng trong cửa sổ retry (theo hợp đồng
// tích hợp hiện tại). Phải khử trùng lặp theo eventId đã lưu bền vững;
// chỉ bỏ logic này khi hợp đồng mới bảo đảm hành vi khác và có test đối ứng.
eventRepository.recordIfAbsent(eventId, eventPayload);
```

Ví dụ này **không tự chứng minh** `recordIfAbsent` thật sự nguyên tử dưới concurrency: cần constraint và transaction phù hợp trong implementation. Bình luận nêu lý do cần bảo vệ; test tích hợp kiểm tra ranh giới thực thi. Trong dự án thật, nếu có số phiên bản hợp đồng đối tác hoặc đường dẫn tài liệu nội bộ ổn định, nên liên kết để người sau xác minh.

### 7.2. Comment, issue và ADR dùng cho việc khác nhau

| Nơi ghi | Thông tin phù hợp | Hạn chế |
| --- | --- | --- |
| Bình luận cạnh code | Lý do tại điểm quyết định, điều kiện biên, cảnh báo sửa đổi | Không phù hợp lịch sử dài hoặc nhiều phương án |
| Javadoc/API spec | Cam kết dành cho caller, tham số, kết quả, lỗi | Không nên lệ thuộc chi tiết implementation |
| Test có tên và fixture rõ | Ví dụ thực thi của hành vi và trường hợp biên | Test không giải thích đủ mọi bối cảnh kinh doanh |
| Issue / ticket | Sự cố, trao đổi, bằng chứng, người xử lý | Liên kết có thể mất hoặc quyền truy cập thay đổi |
| ADR | Quyết định kiến trúc, phương án loại bỏ, đánh đổi và bối cảnh | Cần được liên kết khi thay đổi làm nó không còn đúng |
| Runbook | Cách quan sát, đối soát, khôi phục khi có sự cố | Cần cập nhật theo hệ thống đang chạy |

Không cần ghi mọi phép gán biến thành ADR. Chỉ tạo tài liệu đủ nặng tương xứng với **tầm ảnh hưởng và độ khó đảo ngược** của quyết định.

## 8. Bình luận quanh lỗi, retry và đồng thời cần chính xác đặc biệt

Những bình luận ở mã liên quan dữ liệu và tác dụng phụ có ảnh hưởng lớn tới độ tin cậy. Một cách diễn đạt cẩu thả dễ làm người đọc quyết định sai khi có sự cố.

### 8.1. Timeout không tự chứng minh thất bại

Bình luận nguy hiểm:

```java
// Timeout nghĩa là giao dịch chưa xử lý.
catch (GatewayTimeoutException e) {
    return PaymentStatus.FAILED;
}
```

Gateway có thể đã thu tiền rồi mất phản hồi. Trong ví dụ nghiệp vụ thanh toán, nếu hệ thống có cơ chế đối soát, một bình luận đúng hơn phải làm rõ:

```java
// Timeout không xác định được cổng thanh toán đã thực hiện giao dịch hay chưa.
// Giữ trạng thái chờ đối soát; thử lại chỉ qua cơ chế idempotency đã xác nhận.
catch (GatewayTimeoutException e) {
    return PaymentStatus.PENDING_RECONCILIATION;
}
```

Đoạn code là **minh họa một nhánh**; `PaymentStatus` và `GatewayTimeoutException` được giả định tồn tại trong ứng dụng. Để an toàn thật, trạng thái chờ phải được lưu bền vững, có quy trình đối soát, và khóa idempotency phải được phía nhận thực thi. Bình luận không thể thay thế các cơ chế ấy.

### 8.2. Thứ tự thao tác và tính nguyên tử

Bình luận:

```java
// Ghi đơn hàng trước khi phát sự kiện để tránh mất dữ liệu.
repository.save(order);
messagePublisher.publish(order.createdEvent());
```

Câu này có thể gây hiểu nhầm: nếu `save` thành công và tiến trình dừng trước `publish`, **sự kiện vẫn có thể mất**. Nếu nghiệp vụ yêu cầu sự kiện không thất lạc, có thể cần transactional outbox hoặc chiến lược phục hồi tương đương, cùng test khởi động lại tiến trình.

Bình luận giá trị ở đây phải nói rõ **bất biến và cơ chế bảo đảm**, không tự ca ngợi thứ tự câu lệnh là an toàn. Ví dụ khi đã thật sự triển khai outbox:

```java
// Lưu đơn và bản ghi outbox trong cùng transaction để worker có thể
// phát lại sự kiện sau restart. Consumer vẫn phải xử lý trùng an toàn.
orderRepository.save(order);
outboxRepository.append(order.createdEvent());
```

Đoạn trên chỉ minh họa hai lời gọi **giả định đang nằm trong một transaction chung**. Nếu ranh giới transaction không tồn tại hoặc không bao phủ cả hai, bình luận trở thành sai. Tính đúng đắn phải được chứng minh bằng cấu hình giao dịch, thiết kế lưu trữ và kiểm thử tích hợp.

### 8.3. Ghi lý do của điều kiện bảo mật

Một nhánh có thể phải kiểm tra quyền **trước khi** truy vấn hoặc trả dữ liệu để không lộ sự tồn tại của tài nguyên cho người không có quyền. Bình luận có thể nói rõ mục tiêu bảo vệ, nhưng không nên chứa bí mật, token, khóa API, hoặc diễn đạt những chi tiết khai thác không cần thiết.

Ví dụ:

```java
// Kiểm tra phạm vi truy cập trước khi dựng response vì nội dung
// và cả sự tồn tại của tài nguyên đều thuộc ranh giới phân quyền.
authorization.requireAccess(currentUser, documentId);
Document document = documentRepository.load(documentId);
```

Việc lựa chọn trả 403 hay 404 vẫn phụ thuộc hợp đồng bảo mật cụ thể; cần kiểm thử không lộ thông tin qua các đường lỗi khác. Comment chỉ làm rõ lý do, không chứng minh hệ thống đã chặn hết rò rỉ.

## 9. Khi mã khó đọc, hãy sửa mã trước khi viết bình luận dài

Bình luận thường được dùng làm “miếng vá” cho tên gọi mơ hồ hoặc một phương thức làm quá nhiều việc.

```java
// s là tổng tiền chưa thuế; f là có ưu đãi.
// Nếu f thì kiểm tra s lớn hơn 100 và tiếp tục ...
if (f && s.compareTo(LIMIT) > 0) {
    // ...
}
```

Nếu có thể đổi thành:

```java
boolean eligibleForPromotion =
        hasActivePromotion &&
        subtotalBeforeTax.compareTo(promotionThreshold) > 0;

if (eligibleForPromotion) {
    // ...
}
```

thì nhiều bình luận trở nên không cần thiết. Sau khi tên đã đủ rõ, vẫn cần kiểm thử và có thể cần một câu giải thích **vì sao ngưỡng không bao gồm giá trị bằng** nếu đó là quyết định bất thường.

### 9.1. Khi nào trích xuất phương thức có ích?

Một khối xử lý nhiều bước có thể rõ hơn nếu tách thành các phương thức theo trách nhiệm:

```java
validateOrder(command);
reserveInventory(command);
recordAcceptedOrder(command);
```

Nhưng tách thành `part1()`, `part2()`, `part3()` hoặc tạo nhiều lớp chỉ để né bình luận không tự làm mã tốt hơn. Tên phương thức phải truyền đạt **quy tắc hoặc ý định thực**, và việc chia tách không được làm mất transaction, thứ tự hoặc tính nhất quán.

### 9.2. Khi nào bình luận vẫn cần thiết?

- Một thuật toán tiêu chuẩn nhưng khó nhận ra có thể hưởng lợi từ tên thuật toán, bất biến và tham chiếu nguồn đáng tin cậy.
- Một giải pháp vòng tránh tương thích có thể có tên rõ mà **lý do chưa thể bỏ** vẫn cần bình luận.
- Một quyết định ưu tiên điều kiện có thể nằm trong bảng quyết định; bình luận ngắn liên kết với bảng có ích nếu logic trông trái trực giác.
- Một tối ưu có cấu trúc khó hơn bình thường có thể cần liên kết với phép đo để tránh bị “đơn giản hóa” rồi làm xấu hiệu năng.
- Một đường khôi phục dữ liệu có thể cần giải thích tại sao chấp nhận trạng thái trung gian và ai chịu trách nhiệm xử lý tiếp.

**Không lấy độ dài bình luận làm mục tiêu.** Thông tin giúp người sửa ra quyết định đúng mới là giá trị cần tối ưu.

## 10. TODO, FIXME và workaround: ghi điều kiện hoàn tất, không để lại lời hứa mơ hồ

Các ghi chú `TODO` hoặc `FIXME` có thể hữu ích khi còn công việc có chủ đích. Nhưng `// TODO: fix later`, `// HACK` hay `// optimize someday` không cho người khác biết lỗi nào, độ nghiêm trọng ra sao hoặc khi nào có thể gỡ bỏ.

Thay vì:

```java
// TODO: remove old stuff.
useLegacyCustomerField(payload);
```

Có thể viết, nếu đã có kế hoạch thật:

```java
// TODO(COMPAT-42): bỏ alias customer_id khi các phiên bản client
// còn hỗ trợ đã chuyển sang customerId; kiểm tra metric sử dụng
// trước khi xóa và cập nhật contract test cho đường chuyển đổi.
useLegacyCustomerField(payload);
```

`COMPAT-42` trong ví dụ là **mã công việc giả định**. Không tạo mã ticket giả trong dự án thật; dùng liên kết hoặc định danh đã có. Nếu chưa có kế hoạch chính thức, ghi thẳng rủi ro và người cần xác nhận, không bịa một thời điểm gỡ bỏ.

### 10.1. Phân biệt workaround có chủ đích với lỗi chưa sửa

| Loại ghi chú | Khi có ích | Thông tin tối thiểu |
| --- | --- | --- |
| `TODO` | Công việc được hoãn có kiểm soát | Điều kiện cần làm, lý do hoãn, nguồn theo dõi |
| `FIXME` | Khiếm khuyết đã biết cần sửa | Hậu quả, điều kiện kích hoạt, liên kết lỗi và mức ưu tiên |
| Workaround | Phải đi đường vòng do hạn chế đã xác nhận | Hạn chế cụ thể, rủi ro, điều kiện gỡ bỏ |
| Compatibility note | Duy trì hành vi cũ cho caller/dữ liệu còn được hỗ trợ | Đối tượng phụ thuộc, cách đo khi có thể dừng |
| Performance note | Cấu trúc phức tạp do bottleneck đã đo | Workload, giả thuyết, kết quả hoặc nơi tìm báo cáo |

Không nên để TODO trở thành giải pháp thay thế việc sửa một lỗi nghiêm trọng đang gây mất tiền hoặc dữ liệu. Bình luận có thể ghi lại nợ kỹ thuật, nhưng **việc chấp nhận rủi ro phải có chủ sở hữu và quy trình ưu tiên phù hợp**.

## 11. Bình luận là dữ liệu cần bảo trì cùng hành vi

Bình luận có thể **lỗi thời** trong nhiều cách: ngưỡng đã đổi, API cũ không còn được hỗ trợ, SDK đã sửa bug, test đã thay, hoặc lời giải thích thiết kế ban đầu không còn đúng.

Một quy trình tốt khi sửa code:

1. **Đọc lý do hiện có:** nhận diện điều kiện, sự cố hoặc cam kết đã thúc đẩy thiết kế.
2. **Xác minh lý do còn hiệu lực:** xem hợp đồng được duyệt, test liên quan và dữ liệu vận hành nếu thay đổi phụ thuộc vào chúng.
3. **Đổi code và bình luận trong cùng thay đổi:** không để comment nói về nhánh đã bị xóa hoặc kết quả cũ.
4. **Cập nhật test và tài liệu hợp đồng:** nếu thay đổi hành vi có chủ đích, diễn đạt rõ sự thay đổi.
5. **Xóa bình luận không còn cần:** khi tên/kiểu/tách phương thức đã thể hiện đủ hoặc lý do không còn tồn tại.
6. **Giữ lịch sử ở nơi phù hợp:** nếu bối cảnh dài còn giá trị, liên kết tới tài liệu quyết định thay vì nhồi cả lịch sử vào thân hàm.

### 11.1. Bình luận và code mâu thuẫn: tin điều gì?

Khi thấy:

```java
// Không bao gồm đúng deadline.
return !evaluatedAt.isAfter(deadline);
```

Code hiện tại **bao gồm** deadline, còn bình luận nói ngược lại. Không nên chọn một phía chỉ từ cảm giác. Cần kiểm tra hợp đồng đã xác nhận, các test biên, quyết định nghiệp vụ và hành vi thực của hệ thống. Sau đó sửa logic hoặc sửa bình luận (hoặc cả hai) cho thống nhất.

Một bình luận sai có thể nằm rất lâu vì không được compiler kiểm tra. Vì thế **review comment là review một phần của hợp đồng tri thức**, không chỉ sửa chính tả.

### 11.2. Khi nào comment chứa số đo?

Ví dụ:

```java
// Với workload lọc hàng chục nghìn bản ghi, benchmark đã ghi nhận
// linear search chiếm phần đáng kể CPU; giữ index này cho đường nóng.
// Xem báo cáo hiệu năng của bản phát hành tương ứng trước khi đổi.
Map<String, Account> accountById = buildIndex(accounts);
```

Đây là **mẫu bình luận**, không phải tuyên bố về một phép đo đã chạy trong bài học. Trong code thật, cần liên kết đến báo cáo đo có phiên bản, dữ liệu, môi trường và kết quả cụ thể. Tránh các câu không thể kiểm chứng như “nhanh hơn 100 lần” khi không biết workload, JVM hay cách đo.

Nếu tối ưu không còn đem lại lợi ích hoặc chi phí bộ nhớ đã thay đổi, bình luận và thiết kế phải được xem lại.

## 12. Quy trình review bình luận bằng những câu hỏi cụ thể

Trong một pull request, hãy đọc comment như người sẽ bảo trì đoạn mã sau vài tháng.

| Câu hỏi review | Cách đánh giá |
| --- | --- |
| Bình luận có nói điều mã chưa tự thể hiện không? | Nếu chỉ lặp cú pháp, cân nhắc xóa hoặc đổi tên code |
| Có nêu lý do của quyết định bất thường không? | Nêu ràng buộc, hậu quả khi thay đổi hoặc điều kiện ngoại lệ |
| Có khẳng định điều đã được kiểm chứng không? | Nếu nói “nguyên tử”, “không trùng”, “luôn đúng”, yêu cầu bằng chứng |
| Có đủ ngữ cảnh để kiểm tra lại không? | Khi cần, liên kết test, hợp đồng, issue hoặc ADR thật |
| Đúng với phiên bản code sau thay đổi không? | So từng nhánh và từng điểm biên với chú thích |
| Có lộ thông tin nhạy cảm không? | Không đưa token, thông tin cá nhân hoặc bí mật vào comment |
| Bình luận có quá dài vì thiết kế khó hiểu không? | Cân nhắc tách trách nhiệm, tên/kiểu có ý nghĩa |
| Có mô tả giá trị biên và thứ tự ưu tiên không? | Với logic dễ hiểu sai, bổ sung test để bảo vệ |
| Javadoc có thể được caller tin không? | Tham số, kết quả, lỗi và tác dụng phụ phải khớp hành vi thực |
| Có TODO vô chủ hoặc vô hạn không? | Làm rõ rủi ro, người theo dõi hoặc điều kiện hoàn tất |

Một góp ý review cụ thể hơn “comment chưa tốt” là:

> “Bình luận nói timeout nghĩa là giao dịch thất bại, nhưng cổng thanh toán có thể đã xử lý trước khi mất phản hồi. Cần làm rõ hợp đồng trạng thái chưa xác định và test đối soát; không nên chỉ đổi câu chữ.”

Điều quan trọng là người review nhận ra **nguy cơ thiết kế nằm sau lời bình luận**, không chỉ tối ưu cách viết tiếng Việt.

## 13. Bài tập thực hành

### Bài 1 — Xóa bình luận tường thuật

Cho đoạn sau:

```java
// Đặt total bằng 0.
BigDecimal total = BigDecimal.ZERO;
// Lặp qua các sản phẩm.
for (LineItem item : items) {
    // Cộng tiền của sản phẩm vào tổng.
    total = total.add(item.price());
}
```

Hãy xóa những bình luận không bổ sung thông tin. Sau đó giải thích vì sao vẫn cần kiểm tra xem `price()` có thực sự là tổng tiền dòng hàng hay chỉ là giá một đơn vị. Có nên đổi tên hoặc sửa phép tính trước khi viết comment không?

### Bài 2 — Thêm lý do cho biên ngày

Một API cho phép hủy đặt phòng đến đúng 18:00 theo múi giờ của địa điểm lưu trú. Code đang dùng `localTime.isAfter(deadline)` để từ chối, nhưng người sửa định đổi sang `!localTime.isBefore(deadline)`.

Hãy viết bình luận hoặc Javadoc làm rõ **đúng 18:00 có được hủy hay không**, phân biệt `LocalTime` với mốc thời gian thực khi có múi giờ, và đề xuất hai test tại đúng deadline và sau deadline.

### Bài 3 — Bình luận tạo tự tin sai

Đoạn code:

```java
// Giao dịch đảm bảo chỉ gửi email đúng một lần.
emailClient.send(message);
```

Hãy phân tích vì sao lời khẳng định chưa có cơ sở khi mạng timeout hoặc service restart. Viết lại một chú thích trung thực về **điều chưa được bảo đảm** và nêu cần kiểm thử/tái thiết kế gì để có yêu cầu chống gửi trùng.

### Bài 4 — Tương thích API lâu dài

Một serializer vẫn xuất field `customer_id` dù API mới dùng `customerId`. Một lập trình viên muốn xóa field cũ vì “không theo naming convention”.

Hãy viết bình luận ngắn giải thích ràng buộc tương thích, điều kiện có thể gỡ field cũ, đồng thời đề xuất contract test cho client cũ. Nếu không biết client nào còn phụ thuộc, bình luận nên thể hiện sự chưa chắc chắn ra sao?

### Bài 5 — TODO có thể hành động

Cho ghi chú `// TODO: optimize this` cạnh đoạn code xử lý 20 bản ghi mỗi request. Hãy mô tả bằng chứng cần có trước khi tối ưu, viết lại ghi chú theo dạng **giả thuyết, phép đo và ngưỡng xem xét** hoặc quyết định xóa TODO nếu chưa có vấn đề thực.

### Bài 6 — Comment sai sau refactor

Một phương thức đã đổi từ đọc database trực tiếp sang gọi API đối tác, nhưng Javadoc vẫn cam kết “trả `Optional.empty()` khi không có bản ghi; mọi lỗi I/O đều được thử lại ba lần”. API mới có thể timeout và chưa xác định kết quả.

Hãy xác định tài liệu nào đang sai, điều gì phải hỏi bên cung cấp mới, các trạng thái caller cần phân biệt và test nào chứng minh hợp đồng đã cập nhật.

### Bài 7 — Comment hay kiểm thử?

Trong mã có bình luận “không bao giờ cho phép tồn kho âm”, nhưng cập nhật được thực hiện bằng chuỗi đọc rồi ghi không có ràng buộc đồng thời. Hãy đề xuất thay đổi thiết kế dữ liệu, loại kiểm thử cần bổ sung và một bình luận ngắn giải thích **vì sao dùng cập nhật nguyên tử/constraint** thay vì chỉ lặp lại tên phương thức.

Với mỗi bài, hãy trả lời theo ba tiêu chí: **thông tin code đã tự thể hiện**, **lý do/hợp đồng còn thiếu**, và **cách xác minh điều được bình luận thực sự đúng**.

## 14. Ghi nhớ

- **Mã nguồn nên nói rõ nó làm gì** bằng tên, kiểu và luồng xử lý; bình luận không nên chỉ thuật lại câu lệnh.
- **Bình luận có giá trị nói rõ vì sao**: ràng buộc nghiệp vụ, tương thích, xử lý lỗi, thứ tự ưu tiên, giải pháp vòng tránh hoặc đánh đổi kỹ thuật.
- **Javadoc công khai là ngoại lệ quan trọng của quy tắc “chỉ viết why”**: nó còn phải mô tả hợp đồng đầu vào, kết quả, lỗi và tác dụng phụ mà caller có quyền dựa vào.
- **Không dùng comment để thay cơ chế đúng đắn**: idempotency, transaction, quyền truy cập, phục hồi và tính đồng thời cần được thực thi, kiểm thử và quan sát.
- **Nếu phải giải thích từng dòng, hãy xem lại code**: tên rõ, phương thức có trách nhiệm, kiểu miền nghiệp vụ và test thường hiệu quả hơn một lớp bình luận dài.
- **TODO phải có ý nghĩa vận hành**: nêu lý do, rủi ro, điều kiện hoàn tất và nơi theo dõi khi cần, không chỉ để lại lời hứa “sửa sau”.
- **Bình luận phải được bảo trì** cùng code và tài liệu. Một chú thích sai có thể làm hại tính đáng tin cậy nhiều hơn việc thiếu chú thích.
- **Test và bình luận bổ trợ nhau**: bình luận giúp hiểu lựa chọn, test giúp phát hiện khi hành vi đã được cam kết bị thay đổi.

Một bình luận tốt là câu trả lời cho câu hỏi mà người bảo trì sẽ phải đặt ra: **“Nếu cách này trông kỳ lạ hoặc phức tạp hơn cần thiết, điều gì sẽ bị phá vỡ nếu tôi thay đổi nó?”** Khi lời giải thích đủ chính xác, có thể kiểm chứng và đặt đúng chỗ, tài liệu trở thành một phần hữu ích của mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**.
