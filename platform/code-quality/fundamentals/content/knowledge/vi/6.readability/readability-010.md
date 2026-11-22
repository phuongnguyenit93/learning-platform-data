# Bình luận giải thích lý do, giả thiết và giới hạn

Một đoạn mã có thể được viết rất gọn, đặt tên biến rõ ràng và vẫn khiến người bảo trì đặt câu hỏi: **“Vì sao lại làm như vậy?”**. Chẳng hạn, vì sao thời hạn khuyến mãi phải tính theo ngày tại Việt Nam thay vì UTC? Vì sao chưa thay thuật toán tìm kiếm tuyến tính bằng `HashMap`? Một phương thức có được gọi đồng thời không, và phạm vi nào nằm ngoài trách nhiệm của nó?

Trong chương **Khả năng đọc** của `CODE_QUALITY_FUNDAMENTALS`, bài học này tập trung vào cách dùng **bình luận mã nguồn (code comment)** để giữ lại những thông tin khó suy ra chỉ bằng việc đọc câu lệnh: **lý do (why)**, **giả thiết (assumptions)** và **giới hạn (limitations)**. Đây là một phần của chất lượng mã nguồn: mã đáng tin cậy, dễ hiểu và dễ thay đổi cần cho người đọc biết không chỉ chương trình *làm gì* mà còn *vì sao một lựa chọn có ý nghĩa và khi nào lựa chọn đó không còn phù hợp*.

> **Nguyên tắc cốt lõi:** Ưu tiên viết mã tự diễn đạt **việc đang làm**; dùng comment để bổ sung **bối cảnh, quyết định, giả thiết và ranh giới** mà mã khó tự truyền đạt.

## 1. Comment cần bổ sung thông tin, không đọc lại câu lệnh

Xem đoạn Java sau:

```java
int feeVnd = 30_000;
// Gán phí bằng 0 khi khách hàng VIP.
if (isVipCustomer) {
    feeVnd = 0;
}
```

Comment chỉ mô tả hành vi hiển nhiên từ điều kiện và phép gán. Khi đọc, người khác không biết **vì sao** khách hàng VIP được miễn phí giao hàng: do chính sách kinh doanh, chương trình thử nghiệm hay một ngoại lệ tạm thời?

Nếu chính sách đã được xác nhận là **khách VIP luôn được miễn phí giao hàng**, hãy phản ánh điều đó bằng tên rõ nghĩa và chỉ ghi phần bối cảnh có ích:

```java
// Chính sách vận chuyển ưu tiên khách VIP, kể cả đơn dưới ngưỡng miễn phí.
if (isVipCustomer) {
    return 0;
}
```

Ở ví dụ này, comment lưu lại một điều có thể bị bỏ sót khi ai đó bổ sung điều kiện ngưỡng đơn hàng: quyền miễn phí của khách VIP **không phụ thuộc tổng tiền**.

Tuy nhiên, nếu tên phương thức hoặc một đối tượng chính sách đã đủ rõ và quy tắc được mô tả chính thức ở hợp đồng nghiệp vụ, comment đó có thể không cần thiết. **Không có chỉ tiêu “mỗi khối mã phải có một comment”**.

| Comment ít giá trị | Vấn đề | Hướng cải thiện |
| --- | --- | --- |
| `// Tăng i thêm 1` ngay trên `i++` | Lặp lại câu lệnh | Bỏ comment |
| `// Kiểm tra hợp lệ` trên một điều kiện dài, khó hiểu | Không giải thích quy tắc thực tế | Đặt tên điều kiện, tách phương thức và mô tả quy tắc chưa hiển nhiên |
| `// Tính toán kết quả` | Quá chung chung | Giải thích công thức, đơn vị hoặc giả định nếu có |
| `// Không sửa đoạn này` | Cấm thay đổi nhưng không có lý do | Nêu ràng buộc, cách kiểm chứng và phạm vi ảnh hưởng |
| `// Sửa sau` | Không rõ việc gì, vì sao, khi nào | Ghi vấn đề cụ thể và tiêu chí xem lại nếu cần |

Một tín hiệu thực dụng: **Nếu bỏ comment mà ý nghĩa của đoạn mã vẫn đầy đủ, comment có thể đang dư thừa.** Ngược lại, nếu bỏ comment làm mất một điều kiện kinh doanh hoặc lựa chọn kỹ thuật quan trọng, comment đang mang thông tin cần bảo tồn.

## 2. Ba loại thông tin nên có trong comment

### 2.1. Lý do: tại sao chọn cách này?

Mã nguồn thường cho thấy *cách* thực hiện nhưng không cho thấy *các phương án đã cân nhắc*. Comment về lý do thích hợp khi quyết định có vẻ lạ, dễ bị “tối ưu lại” theo hướng gây lỗi hoặc phụ thuộc vào bối cảnh bên ngoài.

Ví dụ:

```java
// API đối tác giới hạn tối đa 20 mã hàng mỗi yêu cầu.
// Duyệt tuần tự để giữ luồng kiểm tra đơn giản; nếu giới hạn này tăng,
// cần đo lại độ trễ trước khi quyết định chuyển sang chỉ mục HashMap.
for (String requestedSku : requestedSkus) {
    // ... đối chiếu với danh mục nhỏ đã được giới hạn.
}
```

Ở đây, comment trả lời ba điều: **ràng buộc có thật**, **lý do lựa chọn** và **điều kiện phải xem lại**. Nhưng nếu mã không thực thi hoặc tầng trước không đảm bảo giới hạn 20 mã hàng, phần giải thích này mới chỉ là một *tuyên bố chưa được kiểm chứng*. Comment không làm một giả định trở thành sự thật.

Các lý do thường xứng đáng ghi lại gồm:

- Tương thích với định dạng hoặc giao thức cũ trong giai đoạn chuyển đổi.
- Dùng thuật toán đơn giản vì quy mô đầu vào đã được xác minh là nhỏ.
- Giữ một bước kiểm tra đặc biệt để đáp ứng quy tắc nghiệp vụ ít gặp.
- Chọn thứ tự thao tác để bảo toàn tính nhất quán của dữ liệu.
- Tránh một hành vi không mong muốn của thư viện hoặc dịch vụ bên ngoài đã được xác nhận.

Đừng dùng `// performance` hoặc `// business requirement` làm lời giải thích duy nhất. Người bảo trì cần biết *ràng buộc nào* và *tác động của việc thay đổi nó*.

### 2.2. Giả thiết: điều gì phải đúng để mã hoạt động đúng?

**Giả thiết (assumption)** là điều kiện mà thuật toán hoặc thiết kế đang dựa vào. Ví dụ: danh sách đã sắp xếp, mã hàng không trùng, dữ liệu đầu vào không vượt ngưỡng, thời điểm được hệ thống cấp chứ không do client tự khai, hoặc một phương thức chỉ được gọi dưới khóa đồng bộ.

Comment có thể ghi:

```java
// priceBySku được xây từ danh mục đã xác thực: mỗi SKU xuất hiện đúng một lần.
// Nếu nguồn dữ liệu cho phép trùng SKU, chính sách chọn giá cần được xác định lại.
long price = priceBySku.get(sku);
```

Nhưng cách này **chưa an toàn nếu `sku` không tồn tại**: `Map.get` có thể trả về `null`, và gán sang `long` sẽ gây `NullPointerException` do unboxing. Vì vậy, comment không thay thế hợp đồng và xử lý lỗi. Nếu đầu vào có thể thiếu SKU, hãy kiểm tra và báo lỗi rõ:

```java
Long price = priceBySku.get(sku);
if (price == null) {
    throw new IllegalArgumentException("Unknown SKU: " + sku);
}
long priceVnd = price;
```

Giả thiết có thể được thể hiện ở nhiều nơi; cần dùng đúng công cụ:

| Loại giả thiết | Nên thể hiện bằng |
| --- | --- |
| Đầu vào không được `null`, số lượng phải dương | Kiểu dữ liệu, kiểm tra đầu vào, validation và kiểm thử |
| Danh mục bắt buộc có SKU duy nhất | Ràng buộc dữ liệu hoặc validation ở nơi tạo danh mục; kiểm thử |
| Phương thức chỉ kiểm tra thời gian, không kiểm tra tồn kho | Tên API, Javadoc về phạm vi trách nhiệm |
| Thời gian theo múi giờ kinh doanh đã thống nhất | Hằng số có tên, comment giải thích lý do, kiểm thử ranh giới |
| Thành phần chỉ an toàn khi được gọi từ một luồng | Hợp đồng đồng thời rõ ràng; thiết kế cưỡng chế được thì càng tốt |

**Giả thiết quan trọng mà mã có thể kiểm tra nên được kiểm tra.** Chỉ ghi “danh sách luôn khác `null`” mà không có cơ chế bảo đảm là một nguồn lỗi khó phát hiện. Nếu điều kiện được bảo đảm bởi một tầng khác, comment nên nêu **tầng nào chịu trách nhiệm**, thay vì chỉ nói “luôn đúng”.

### 2.3. Giới hạn: giải pháp này không bao phủ điều gì?

**Giới hạn (limitation)** cho biết phạm vi mà cách triển khai được thiết kế để xử lý, những tình huống chưa hỗ trợ hoặc điều kiện làm hiệu lực của quyết định chấm dứt.

Ví dụ:

```java
/**
 * Kiểm tra phạm vi ngày được áp dụng mã khuyến mãi.
 *
 * <p>Chỉ kiểm tra thời gian; điều kiện khách hàng, mặt hàng và hạn mức
 * sử dụng phải được kiểm tra ở bước khác của quy trình đặt hàng.
 */
boolean withinPromotionWindow(Instant submittedAt) {
    // ...
}
```

Comment này ngăn một lỗi sử dụng phổ biến: người gọi nhầm kết quả `true` thành “đơn hàng chắc chắn đủ điều kiện khuyến mãi”.

Giới hạn không phải cái cớ để hợp thức hóa hành vi sai. Nếu ứng dụng bắt buộc bảo đảm một thao tác an toàn khi gọi đồng thời, comment kiểu “chưa xử lý concurrency” **không thể thay thế việc sửa mã**. Những giới hạn có khả năng vi phạm yêu cầu phải được xử lý theo mức rủi ro, không chỉ được mô tả.

## 3. Ví dụ Java đầy đủ: vì sao phải tính hạn khuyến mãi theo giờ Việt Nam?

Giả sử một cửa hàng đưa ra **yêu cầu nghiệp vụ minh họa**:

> Khuyến mãi áp dụng từ đầu ngày 01/11/2026 đến hết ngày 30/11/2026 theo lịch Việt Nam. Thời điểm xét là lúc hệ thống ghi nhận yêu cầu đặt hàng.

Chúng ta cần viết phương thức Java trả lời: một thời điểm `Instant` có nằm trong khoảng khuyến mãi không?

### 3.1. Phiên bản thiếu bối cảnh

```java
import java.time.Instant;

final class PromotionWindow {
    static boolean isActive(Instant submittedAt) {
        return !submittedAt.isBefore(
                    Instant.parse("2026-10-31T17:00:00Z"))
                && submittedAt.isBefore(
                    Instant.parse("2026-11-30T17:00:00Z"));
    }
}
```

Đoạn mã có thể cho kết quả đúng cho yêu cầu minh họa, vì Việt Nam sử dụng UTC+07:00 tại các ngày đã nêu. Tuy nhiên, các mốc `17:00:00Z` dễ gây nghi ngờ: vì sao ngày 01/11 lại biểu diễn bằng ngày 31/10? Mốc cuối có bao gồm hay không? Nếu chương trình được chuyển sang thị trường khác thì sao?

Người đọc có thể “sửa cho dễ hiểu” thành `2026-11-01T00:00:00Z` và vô tình thay đổi quy tắc kinh doanh.

### 3.2. Phiên bản cho thấy ý định, giả thiết và giới hạn

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

final class PromotionWindow {
    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static final LocalDate START_DATE =
            LocalDate.of(2026, 11, 1);

    private static final LocalDate END_DATE =
            LocalDate.of(2026, 11, 30);

    /**
     * Kiểm tra thời điểm ghi nhận đơn có nằm trong cửa sổ khuyến mãi.
     *
     * <p>Chỉ kiểm tra thời gian, không kiểm tra quyền sử dụng của khách,
     * mặt hàng áp dụng hoặc số lượt dùng còn lại.
     *
     * @param submittedAt thời điểm hệ thống ghi nhận đơn, không được null
     * @return true nếu thuộc một ngày từ START_DATE đến END_DATE
     */
    static boolean isActive(Instant submittedAt) {
        Objects.requireNonNull(submittedAt, "submittedAt");

        // Khuyến mãi công bố theo NGÀY tại Việt Nam; xét ngày UTC sẽ làm
        // mốc đầu/cuối bị lệch với thời gian hiển thị cho khách hàng.
        LocalDate businessDate =
                submittedAt.atZone(BUSINESS_ZONE).toLocalDate();

        return !businessDate.isBefore(START_DATE)
                && !businessDate.isAfter(END_DATE);
    }
}
```

Trong đoạn trên:

- **Tên biến và hằng số** thể hiện *điều đang được tính*: ngày nghiệp vụ, ngày bắt đầu, ngày kết thúc, múi giờ kinh doanh.
- **Javadoc** ghi *hợp đồng và phạm vi* của phương thức: giá trị đầu vào, ý nghĩa `true` và những kiểm tra **không thuộc trách nhiệm** của nó.
- **Comment nội tuyến** giải thích *lý do* chuyển `Instant` sang `LocalDate` tại `BUSINESS_ZONE` trước khi so sánh, điều khó suy ra chỉ từ câu lệnh.
- **`Objects.requireNonNull`** thực thi một điều kiện đầu vào cần thiết, thay vì chỉ ghi “không được null” rồi hy vọng nơi gọi luôn tuân thủ.

`Instant` biểu diễn một thời điểm tuyệt đối. `LocalDate` biểu diễn ngày trong một hệ lịch không gắn múi giờ. Việc dùng `atZone(BUSINESS_ZONE)` trả lời câu hỏi “thời điểm này thuộc **ngày nào đối với cửa hàng**?”. Nhờ vậy, hai mốc 01/11 và 30/11 trong yêu cầu được diễn đạt đúng như cách người dùng hiểu.

Đoạn mã không tự bảo đảm `submittedAt` là thời điểm đáng tin cậy do server cấp. Nếu client có thể tùy ý gửi giá trị này, tầng nhận yêu cầu phải xác thực hoặc tự ghi nhận thời điểm theo chính sách nghiệp vụ. Đây là **giả thiết về nguồn dữ liệu**, cần được giải quyết tại ranh giới thích hợp.

### 3.3. Kiểm thử ranh giới chứng minh ý nghĩa của comment

Các ca kiểm thử JUnit 5 sau dùng chính sách và múi giờ minh họa ở trên:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class PromotionWindowTest {
    @Test
    void usesVietNamCalendarDatesIncludingBothEndpoints() {
        // 23:59:59 ngày 31/10 tại Việt Nam: chưa bắt đầu.
        assertFalse(PromotionWindow.isActive(
                Instant.parse("2026-10-31T16:59:59Z")));

        // 00:00:00 ngày 01/11 tại Việt Nam: bắt đầu.
        assertTrue(PromotionWindow.isActive(
                Instant.parse("2026-10-31T17:00:00Z")));

        // 23:59:59 ngày 30/11 tại Việt Nam: vẫn còn hiệu lực.
        assertTrue(PromotionWindow.isActive(
                Instant.parse("2026-11-30T16:59:59Z")));

        // 00:00:00 ngày 01/12 tại Việt Nam: đã hết hạn.
        assertFalse(PromotionWindow.isActive(
                Instant.parse("2026-11-30T17:00:00Z")));
    }
}
```

Các comment trong bài kiểm thử làm rõ **ý nghĩa nghiệp vụ của thời điểm UTC trông khó hiểu**. Chúng không lặp lại `assertTrue` hoặc `assertFalse`. Kết quả kiểm thử cung cấp bằng chứng cụ thể cho quy tắc, giúp người sửa mã nhận ra nếu thay đổi vô tình làm lệch ngày.

**Phân biệt vai trò:** Comment giải thích *vì sao* phải dùng lịch Việt Nam; kiểm thử giúp phát hiện *hành vi có bị thay đổi ngoài ý muốn không*. Cả hai bổ sung cho tên biến rõ nghĩa, không thay thế việc kiểm chứng yêu cầu.

### 3.4. Khi giả thiết thay đổi, phải sửa gì?

Nếu sau này cửa hàng mở rộng khuyến mãi sang nhiều khu vực, một `BUSINESS_ZONE` cố định có thể không còn phù hợp. Nhóm cần làm rõ mỗi chiến dịch dùng múi giờ nào và đưa thông tin đó thành cấu hình hoặc đầu vào có hợp đồng rõ ràng. Khi quy tắc nghiệp vụ thay đổi, cần sửa **mã, kiểm thử và comment/Javadoc liên quan trong cùng thay đổi**.

Giữ comment cũ “khuyến mãi luôn theo giờ Việt Nam” sau khi đã có các chiến dịch quốc tế sẽ làm tài liệu **sai lệch với hành vi**. Comment sai có thể gây hại hơn việc thiếu comment vì khiến người đọc tin vào một ràng buộc không còn tồn tại.

## 4. Chọn vị trí comment phù hợp

Đặt thông tin càng gần quyết định mà nó giải thích càng tốt, nhưng tránh lặp đi lặp lại một quy tắc trong hàng chục file.

| Vị trí | Khi nào phù hợp? | Nội dung nên ưu tiên |
| --- | --- | --- |
| **Comment nội tuyến** | Một nhánh hoặc phép xử lý đặc biệt có lý do khó thấy | Bối cảnh, bất biến, rủi ro khi “đơn giản hóa” |
| **Javadoc cho API** | Người gọi cần biết hợp đồng của lớp, phương thức hoặc kiểu dữ liệu | Tham số, kết quả, trường hợp lỗi, giả thiết, phạm vi, mức bảo đảm |
| **Comment cấp lớp/module** | Cần hiểu trách nhiệm hoặc ranh giới tổng thể của thành phần | Quy tắc thiết kế, thứ gì thuộc/không thuộc module |
| **Test có tên rõ** | Một hành vi quan trọng, điều kiện biên hoặc quy tắc khó nhận ra | Kiểm chứng hành vi; comment chỉ giải thích dữ liệu kiểm thử khác thường |
| **ADR/tài liệu thiết kế** | Quyết định liên quan nhiều thành phần, phương án đánh đổi hoặc vận hành | Lựa chọn đã cân nhắc, tác động, bằng chứng, điều kiện xem lại |

Với API Java, Javadoc là công cụ phù hợp để công bố thông tin cho người sử dụng:

```java
/**
 * Tìm giá theo SKU trong danh mục đã xác thực.
 *
 * <p>Danh mục phải có SKU duy nhất. Nếu thiếu SKU được yêu cầu,
 * phương thức ném IllegalArgumentException thay vì trả giá mặc định.
 *
 * @param sku mã hàng, khác null và không rỗng
 * @return giá sản phẩm theo VND
 * @throws IllegalArgumentException nếu SKU không hợp lệ hoặc không tồn tại
 */
long priceOf(String sku) {
    // ... triển khai minh họa.
    throw new UnsupportedOperationException("Example only");
}
```

Đây là **minh họa về cấu trúc Javadoc**, không phải phương thức tính giá đã triển khai. Khi viết mã thực tế, hợp đồng phải khớp với kiểm tra và hành vi thật; không thể chỉ viết Javadoc đầy đủ rồi để phương thức luôn ném `UnsupportedOperationException`.

Comment trên một **giao diện công khai** cần ổn định và đủ cụ thể để người gọi không phải đọc phần triển khai. Ngược lại, với một biến cục bộ đơn giản, đặt tên tốt thường hiệu quả hơn thêm Javadoc hoặc chú thích.

## 5. Comment về giả thiết phải dẫn tới kiểm soát rủi ro

Một số giả thiết nếu bị phá vỡ có thể gây lỗi âm thầm, làm sai kết quả hoặc ảnh hưởng nhiều người dùng. Comment khi đó cần đi cùng cơ chế kỹ thuật thích hợp.

### Ví dụ A: đơn vị đo

```java
// timeoutMs là mili giây (đơn vị API đối tác), không phải giây.
long timeoutMs = 1_500L;
```

Thông tin đơn vị là quan trọng; tuy nhiên, chỉ comment chưa đủ chống nhầm lẫn. Có thể dùng một kiểu diễn đạt rõ hơn:

```java
import java.time.Duration;

Duration requestTimeout = Duration.ofMillis(1_500);
```

`Duration` giảm nguy cơ truyền nhầm mili giây thành giây ở nơi hỗ trợ kiểu thời gian. Comment vẫn có ích nếu lựa chọn **1.500 ms** đến từ một giới hạn bên ngoài khó suy ra, chẳng hạn ngân sách độ trễ của hệ thống. Khi đó, nên ghi nguồn hoặc phạm vi của giới hạn thay vì lặp lại phép chuyển đổi đơn vị.

### Ví dụ B: thứ tự và đồng thời

```java
// Phương thức này chỉ được gọi khi caller giữ khóa của orderId.
void updateState(String orderId) {
    // ...
}
```

Comment có thể rất quan trọng nhưng không cưỡng chế được quyền truy cập đồng thời. Nếu bỏ sót khóa dẫn đến sai trạng thái, cần xem xét thiết kế API, đồng bộ ở điểm thích hợp, dùng transaction hoặc cơ chế kiểm soát cạnh tranh. Một hợp đồng không được bảo đảm hoặc kiểm thử có thể bị vi phạm khi nhóm bảo trì thay đổi mã.

### Ví dụ C: giới hạn dữ liệu

```java
// Chỉ phục vụ danh mục tối đa 30 sản phẩm; thuật toán O(n^2).
// Nếu dùng cho danh mục lớn hơn, cần đánh giá lại độ phức tạp.
```

Đây là mô tả giới hạn có ích **chỉ khi** đã có nơi thực thi ngưỡng 30, và việc dùng thuật toán O(n²) thực sự phù hợp với mục tiêu hiệu năng. Nếu không có giới hạn đầu vào hoặc số đo, comment đang đưa ra một cam kết chưa có cơ sở. Nên bổ sung validation ở ranh giới, các test ở kích thước tối đa và đo hiệu năng khi cần.

## 6. Viết comment cho giải pháp tạm thời và nợ kỹ thuật

Đôi khi dự án phải giữ một cách làm chưa tối ưu vì yêu cầu tương thích, thời gian triển khai hoặc phụ thuộc vào nhà cung cấp. Comment kiểu “đừng sửa” không cho người sau biết **khi nào có thể bỏ giải pháp tạm thời**.

Ví dụ giả định hệ thống cần đọc hai định dạng sự kiện trong giai đoạn chuyển đổi:

```java
// Tạm nhận cả event V1 và V2 vì đối tác còn gửi V1 trong giai đoạn
// chuyển đổi. Xem lại sau khi dữ liệu giám sát xác nhận V1 đã ngừng.
// Điều kiện gỡ bỏ: tất cả nguồn gửi đã chuyển sang V2 và test tích hợp đạt.
if (eventVersion == 1) {
    return parseLegacyEvent(payload);
}
return parseCurrentEvent(payload);
```

Comment nêu **lý do giữ nhánh cũ**, **tình huống đang hỗ trợ**, và **điều kiện được phép loại bỏ**. Mã minh họa giả định `parseLegacyEvent` và `parseCurrentEvent` đã tồn tại và biến `eventVersion` được xác thực.

Một comment dạng `TODO` hoặc `FIXME` có thể hữu ích nhưng nên cụ thể:

- `TODO: Đối chiếu số lượng event V1 trong dashboard trước khi xóa adapter cũ. Theo dõi tại issue PROJ-123.`
- `FIXME: Thiếu kiểm thử cho kết quả không xác định khi API thanh toán timeout. Bổ sung trước khi cho phép retry tự động.`

Mã issue ở đây chỉ là **ví dụ về cách liên kết công việc**, không phải tham chiếu tới một issue có thật. Trong dự án, dùng định danh công việc thực tế, có người chịu trách nhiệm và được theo dõi.

**Không nên để comment trở thành nơi lưu duy nhất của những quyết định cần quản lý ở cấp dự án.** Vấn đề tác động lớn có thể cần ticket, tài liệu thiết kế hoặc bản ghi quyết định kỹ thuật (ADR). Comment chỉ nên giữ phần ngữ cảnh cần thiết ngay tại điểm sửa mã và trỏ tới tài liệu chi tiết khi thích hợp.

## 7. Nguy cơ lớn nhất: comment cũ không còn đúng

Mã được biên dịch và kiểm thử; comment thường không được máy kiểm tra về tính đúng đắn. Khi thay đổi triển khai nhưng không cập nhật chú thích, một comment từng đúng có thể biến thành thông tin sai.

Ví dụ:

```java
// Danh sách luôn được sắp theo ngày tạo tăng dần.
List<Order> orders = repository.findRecentOrders();
```

Nếu `findRecentOrders()` không có hợp đồng đảm bảo thứ tự, comment tạo cảm giác an toàn giả. Nếu sau này repository thay cách truy vấn, một thuật toán tìm nhị phân dựa trên thứ tự có thể cho kết quả sai.

Cách xử lý phù hợp là:

1. Xác minh xem thứ tự có thực sự là yêu cầu bắt buộc không.
2. Nếu có, thể hiện hợp đồng rõ trong API hoặc sắp xếp dữ liệu ở nơi có trách nhiệm.
3. Thêm kiểm thử khi thứ tự là điều kiện quyết định kết quả.
4. Viết lại comment để mô tả **lý do cần thứ tự** và tầng nào bảo đảm thứ tự đó.

**Một comment tốt phải được xem là một phần của thay đổi mã.** Khi refactor, đổi quy tắc hoặc bỏ một workaround, người sửa cần rà soát các chú thích liên quan như rà soát kiểm thử và hợp đồng API.

Đặc biệt, những câu khẳng định tuyệt đối như “always safe”, “never null”, “100% thread-safe”, “không thể lỗi” cần được kiểm chứng kỹ. Nếu không thể bảo đảm, dùng ngôn ngữ mô tả điều kiện cụ thể và cách xử lý khi điều kiện bị vi phạm.

## 8. Bảo mật và khả năng đọc: không viết mọi thứ vào comment

Comment nằm trong kho mã nguồn, có thể được chia sẻ cho nhiều người hơn nhóm trực tiếp vận hành và có thể tồn tại lâu trong lịch sử Git. Do đó:

- **Không đưa bí mật** như mật khẩu, token, API key, khóa ký hay thông tin truy cập nội bộ nhạy cảm vào comment.
- **Không sao chép dữ liệu khách hàng thật** để minh họa tình huống lỗi hoặc quy tắc nghiệp vụ.
- **Không dùng comment để che một hành vi nguy hiểm**. Ví dụ, ghi “bỏ kiểm tra quyền vì cần tốc độ” không làm một lỗ hổng bảo mật trở thành đánh đổi hợp lệ.
- **Không công bố giả định như bảo đảm tuyệt đối** nếu chưa có cơ chế thực thi hoặc kiểm chứng.

Thông tin về rủi ro có thể cần được ghi nhận và xử lý, nhưng nơi lưu giữ và mức chi tiết phải tuân theo yêu cầu bảo vệ dữ liệu của hệ thống. Trong mã nguồn, nên mô tả **quy tắc và tác động kỹ thuật cần thiết**, không nhúng thông tin bí mật.

## 9. Quy trình viết và review comment

Khi gặp một phần mã khó hiểu, đừng mặc định thêm comment ngay. Có thể kiểm tra theo trình tự sau:

1. **Đọc mục đích của đoạn mã.** Có thể làm rõ bằng tên phương thức, biến, kiểu dữ liệu hoặc tách một khối phức tạp không?
2. **Xác định phần thông tin còn thiếu.** Người đọc thiếu lý do, giả thiết, điều kiện biên, phạm vi hay nguồn của quy tắc?
3. **Kiểm chứng lời giải thích.** Có bằng chứng từ yêu cầu nghiệp vụ, hợp đồng API, kết quả đo, kiểm thử hoặc ràng buộc thiết kế không?
4. **Viết comment ngắn ở nơi có ích nhất.** Ưu tiên mô tả hậu quả của việc thay đổi quyết định và những điều mã không thể tự biểu đạt.
5. **Thực thi giả thiết có thể kiểm tra.** Đừng dùng comment thay `null` check, validation, test hoặc kiểm soát đồng thời.
6. **Ghi giới hạn và điều kiện xem lại nếu có.** Với lựa chọn tạm thời, nêu tiêu chí dừng hoặc chuyển sang phương án khác.
7. **Review cùng mỗi lần sửa mã.** Cập nhật hoặc xóa comment lỗi thời; tránh giữ hai nguồn sự thật mâu thuẫn.

Một đoạn hội thoại code review hữu ích có thể là:

> **Reviewer:** “Tại sao phải đổi `Instant` sang giờ Việt Nam trước khi kiểm tra hạn? Đây có phải quy tắc kinh doanh không?”

> **Tác giả:** “Có. Khách hàng nhìn thấy hạn đến hết ngày 30/11 theo giờ Việt Nam. Tôi sẽ ghi rõ giả thiết này tại phép chuyển ngày và bổ sung test ở mốc 00:00 ngày 01/12.”

Kết quả của trao đổi không chỉ là thêm một dòng comment. Nó còn làm rõ **hợp đồng**, **hành vi cần bảo vệ bằng test**, và **vị trí cần xem lại nếu mở rộng sang thị trường khác**.

## 10. Bài tập thực hành

### Bài tập 1: Chọn comment hữu ích hơn

Cho đoạn mã:

```java
if (isLegacyClient) {
    response = toVersion1Response(data);
}
```

Bạn sẽ chọn comment nào?

A. `// Kiểm tra nếu là legacy client.`

B. `// Giữ định dạng V1 cho các client chưa nâng cấp; việc bỏ nhánh này phụ thuộc thời hạn hỗ trợ V1 đã công bố.`

**Gợi ý:** B có giá trị hơn vì nêu lý do tương thích và điều kiện xem lại. Nhưng vẫn phải xác minh chính sách hỗ trợ V1 và cách phát hiện client cũ trong hệ thống thật.

### Bài tập 2: Tìm giả thiết ẩn

```java
int median = sortedValues.get(sortedValues.size() / 2);
```

Những giả thiết nào cần làm rõ?

**Gợi ý:** Danh sách phải không rỗng và đã sắp xếp theo đúng thứ tự. Với số phần tử chẵn, cách lấy phần tử giữa phía trên có thể **không phải** định nghĩa trung vị mà sản phẩm yêu cầu. Ngoài comment, cần thực thi precondition và làm rõ hợp đồng thuật toán.

### Bài tập 3: Comment có giải quyết lỗi không?

```java
// orderId sẽ luôn không null.
return orderId.trim();
```

Nếu `orderId` đến trực tiếp từ request bên ngoài, bình luận đã đủ chưa?

**Gợi ý:** Chưa. Cần kiểm tra hoặc dùng cơ chế validation đáng tin cậy trước khi gọi `trim()`. Comment chỉ có ý nghĩa khi nêu hợp đồng đã được thực thi ở đâu hoặc vì sao tầng này có thể dựa vào nó.

### Bài tập 4: Khi nào phải xóa comment?

Ban đầu hệ thống chỉ bán hàng ở Việt Nam và có comment: “Mọi chương trình khuyến mãi đều theo giờ Việt Nam”. Sáu tháng sau, chương trình có thêm khuyến mãi theo giờ địa phương của từng thị trường.

**Gợi ý:** Phải cập nhật mã, hợp đồng, test và comment liên quan. Một lời giải thích đúng trong quá khứ không còn đúng cho hành vi mới. Nếu vẫn có khuyến mãi riêng theo giờ Việt Nam, nên giới hạn lời giải thích vào đúng thành phần áp dụng quy tắc ấy.

### Bài tập 5: Quyết định tạm thời đã đủ rõ chưa?

```java
// TODO: tối ưu sau.
return products.stream().filter(p -> p.id().equals(id)).findFirst();
```

**Gợi ý:** Chưa. Cần biết quy mô danh sách, mục tiêu hiệu năng, lý do chưa dùng chỉ mục, tác động và điều kiện đánh giá lại. Nếu dữ liệu nhỏ hoặc không có vấn đề hiệu năng, thậm chí có thể **xóa TODO** và giữ triển khai đơn giản thay vì tạo một khoản nợ kỹ thuật không có thật.

## Ghi nhớ

**Comment đáng giữ giải thích những điều khó suy ra từ mã: lý do lựa chọn, giả thiết cần đúng và giới hạn áp dụng.** Tên biến, cấu trúc, kiểu dữ liệu và kiểm thử nên làm rõ hành vi; comment bổ sung bối cảnh và hệ quả của việc thay đổi. Một giả thiết quan trọng cần được thực thi hoặc kiểm chứng ở tầng thích hợp, thay vì chỉ tuyên bố trong lời chú thích.

Hãy viết comment đủ chính xác để đồng nghiệp biết **khi nào có thể thay đổi an toàn**, và cập nhật nó khi yêu cầu thay đổi. Nhờ vậy, mã nguồn không chỉ dễ đọc ở thời điểm hiện tại mà còn **đáng tin cậy và dễ bảo trì** trong những lần phát triển tiếp theo.
