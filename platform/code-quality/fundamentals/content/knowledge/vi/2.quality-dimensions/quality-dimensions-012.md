# Quan hệ hỗ trợ hoặc xung đột giữa các tiêu chí

Trong một hệ thống phần mềm, chất lượng không phải một con số duy nhất. Mã chạy đúng nhưng khó thay đổi vẫn có thể làm dự án chậm lại; mã rất dễ đọc nhưng xử lý sai dữ liệu vẫn không đáng tin cậy; một tối ưu hiệu năng có thể khiến hành vi trở nên khó kiểm chứng. Vì vậy, đánh giá chất lượng cần xem **các tiêu chí ảnh hưởng lẫn nhau như thế nào** thay vì cố tối đa hóa từng tiêu chí một cách riêng lẻ.

Bài học thuộc chương **Các chiều chất lượng** của **CODE_QUALITY_FUNDAMENTALS**. Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở đây, ta sẽ nhận diện các quan hệ hỗ trợ, quan hệ xung đột và cách chọn đánh đổi có căn cứ bằng ví dụ Java.

## 1. Các tiêu chí chất lượng cùng tồn tại trong một quyết định

Một số chiều chất lượng thường gặp:

| Tiêu chí | Câu hỏi thực tế | Bằng chứng thường dùng |
| --- | --- | --- |
| **Tính đúng đắn (correctness)** | Đầu ra và trạng thái hệ thống có tuân thủ yêu cầu, quy tắc nghiệp vụ không? | Kiểm thử với trường hợp thường, biên, bất biến nghiệp vụ |
| **Độ tin cậy (reliability)** | Hệ thống có tiếp tục cung cấp hành vi mong đợi trong điều kiện sử dụng và sự cố đã xét không? | Tỷ lệ lỗi, khả năng khôi phục, thử nghiệm sự cố, giám sát |
| **Bảo mật (security)** | Có bảo vệ dữ liệu, quyền truy cập và tài nguyên trước các hành vi không được phép không? | Kiểm tra phân quyền, kiểm thử bảo mật, rà soát phụ thuộc |
| **Hiệu năng và hiệu quả tài nguyên (performance/resource efficiency)** | Có đáp ứng thời gian, thông lượng, bộ nhớ, chi phí tài nguyên theo mục tiêu không? | p95/p99 độ trễ, thông lượng, CPU, heap, kết quả benchmark |
| **Khả năng đọc hiểu (readability)** | Người khác có nắm được ý định, luồng xử lý và điều kiện quan trọng không? | Review, sự rõ ràng của tên, cấu trúc và tài liệu cần thiết |
| **Khả năng bảo trì và thay đổi (maintainability/modifiability)** | Thay một yêu cầu có thể thực hiện an toàn, với phạm vi ảnh hưởng kiểm soát được không? | Thời gian sửa đổi, mức kết dính, phụ thuộc, số điểm cần sửa |
| **Khả năng kiểm thử (testability)** | Có thể cô lập hành vi, điều khiển dữ liệu đầu vào và quan sát kết quả không? | Kiểm thử có tính quyết định, dễ dựng fixture, ít phụ thuộc ngoài |
| **Khả năng quan sát (observability)** | Khi hệ thống sai hoặc chậm, có đủ tín hiệu để hiểu nguyên nhân không? | Log, metric, trace, correlation ID phù hợp |
| **Tính đơn giản (simplicity)** | Giải pháp có tránh được cơ chế và giả định chưa cần thiết không? | Số khái niệm phải hiểu, nhánh logic, mức phức tạp phù hợp |

Các tiêu chí này khác nhau về **đối tượng đo** và **thời điểm thể hiện**. Một phép kiểm thử chứng minh hành vi tại những trường hợp đã kiểm tra; nó không tự chứng minh hệ thống an toàn trước mọi tấn công. Mã ít dòng cũng không tự chứng minh dễ bảo trì.

Để nói về “hỗ trợ” hoặc “xung đột”, phải nêu rõ **bối cảnh**, **phương án được so sánh** và **đặc tính thay đổi**. Ví dụ, tăng kiểm tra đầu vào có thể làm phát sinh một chút thời gian xử lý, nhưng giảm lỗi và giúp người vận hành hiểu dữ liệu sai nằm ở đâu. Kết luận phải dựa trên tác động thực, không chỉ dựa trên nhãn tiêu chí.

## 2. Bốn kiểu quan hệ cần phân biệt

### 2.1. Hỗ trợ lẫn nhau (synergy)

Một thay đổi cải thiện nhiều tiêu chí cùng lúc.

Ví dụ: tách phần tính phí vận chuyển khỏi phần gọi cơ sở dữ liệu có thể làm quy tắc **dễ đọc hơn**, **dễ kiểm thử hơn**, đồng thời giảm nguy cơ làm hỏng kết nối dữ liệu khi sửa nghiệp vụ. Việc dùng một tên có nghĩa như **freeShippingThresholdVnd** thay cho số **500_000** rải rác cũng giúp đọc hiểu và thay đổi an toàn.

Hiệu quả hỗ trợ không mặc nhiên xảy ra: tách quá nhiều lớp vụn có thể khiến người đọc phải đi qua nhiều tệp mà không tăng độ rõ ràng.

### 2.2. Xung đột hoặc đánh đổi (trade-off)

Một phương án có thể cải thiện tiêu chí này nhưng làm xấu đi tiêu chí khác trong **một điều kiện cụ thể**.

Ví dụ: cache giá sản phẩm giảm số lần truy vấn, có thể cải thiện độ trễ, nhưng nếu giá thay đổi mà cache không làm mới đúng lúc thì tính đúng đắn suy giảm. Khắc phục cần chính sách nhất quán, hết hạn hoặc gắn phiên bản, thường làm tăng độ phức tạp.

Đánh đổi không có nghĩa “muốn nhanh thì bắt buộc phải sai”. Nó có nghĩa **phương án cụ thể đang chuyển chi phí hoặc rủi ro sang một chiều khác**; có thể tồn tại phương án tốt hơn cả hai.

### 2.3. Xung đột biểu kiến

Đôi khi hai mục tiêu chỉ có vẻ mâu thuẫn vì giải pháp ban đầu chưa hợp lý hoặc phép đo chưa phù hợp.

Ví dụ: biểu thức lồng nhiều toán tử được viết trên một dòng không chắc nhanh hơn vài câu lệnh rõ ràng; trình biên dịch Java thường tối ưu nhiều cấu trúc tương đương. Việc đặt tên biến và tách hàm nhỏ có thể nâng cao khả năng đọc mà không tạo khác biệt hiệu năng đáng kể. Muốn kết luận phải đo trên đường chạy quan trọng.

### 2.4. Đánh đổi thay đổi theo thời gian và quy mô

Một quyết định có thể tốt lúc bắt đầu nhưng trở thành gánh nặng sau khi dữ liệu, nhóm hoặc yêu cầu tăng. Ngược lại, trừu tượng hóa quá sớm tạo chi phí ban đầu trong khi giá trị tái sử dụng chưa xuất hiện.

Ví dụ: một ứng dụng nội bộ ban đầu chỉ có một nguồn dữ liệu; thêm giao diện tổng quát cho mười loại nguồn khi chưa có nhu cầu có thể giảm tính đơn giản. Khi thực sự tích hợp thêm nhiều nguồn với quy tắc độc lập, ranh giới đó có thể giúp thay đổi an toàn hơn.

## 3. Bản đồ những quan hệ thường gặp

| Cặp tiêu chí | Quan hệ thường thấy | Cơ chế ảnh hưởng | Điều kiện cần lưu ý |
| --- | --- | --- | --- |
| Dễ đọc ↔ Dễ bảo trì | Thường hỗ trợ | Ý định rõ, người mới giảm thời gian hiểu trước khi sửa | Mã dài dòng hoặc chia nhỏ quá mức có thể phản tác dụng |
| Kiểm thử được ↔ Đúng đắn, tin cậy | Thường hỗ trợ | Dễ viết ca biên và phát hiện hồi quy | Kiểm thử kém chất lượng có thể gây tự tin sai |
| Ranh giới mô-đun ↔ Dễ thay đổi | Thường hỗ trợ | Giới hạn phạm vi phụ thuộc, tách trách nhiệm | Quá nhiều abstraction làm tăng chi phí điều hướng |
| Kiểm tra đầu vào ↔ Tin cậy, bảo mật | Thường hỗ trợ | Từ chối sớm dữ liệu không hợp lệ | Cần phân biệt kiểm tra ở ranh giới và kiểm tra lặp vô ích |
| Log chi tiết ↔ Khả năng chẩn đoán | Thường hỗ trợ | Có dữ kiện điều tra lỗi sản xuất | Có nguy cơ lộ thông tin và tăng I/O |
| Cache ↔ Độ trễ, tính nhất quán | Có thể xung đột | Giảm truy vấn nhưng dữ liệu có thể cũ | TTL, vô hiệu hóa và phiên bản dữ liệu phải rõ |
| Song song hóa ↔ Thông lượng, tính quyết định | Có thể xung đột | Nhiều tác vụ chạy đồng thời, khó tái hiện thứ tự | Race condition, lock contention, tính idempotent |
| Tái sử dụng ↔ Đơn giản, tính độc lập | Có thể xung đột | Gộp logic giảm lặp nhưng tạo phụ thuộc chung | Chỉ trừu tượng hóa khi ý nghĩa và nhịp thay đổi thực sự giống nhau |
| Sao chép phòng vệ ↔ Cô lập trạng thái, bộ nhớ | Có thể xung đột | Tránh bị sửa ngoài ý muốn nhưng tăng cấp phát | Dữ liệu lớn hoặc đường chạy nóng cần đo |
| Kiểm soát bảo mật ↔ Độ trễ/tiện dụng | Có thể xung đột | Xác thực, mã hóa, phân quyền có chi phí thực thi | Không được hạ chuẩn bảo vệ bắt buộc chỉ để đạt benchmark |

Các hàng trong bảng là **giả thuyết để kiểm tra**, không phải định luật. Trên một đường chạy, cache có thể giảm cả độ trễ lẫn tải cơ sở dữ liệu nên làm hệ thống ổn định hơn; trên đường chạy khác nó có thể tạo lỗi dữ liệu cũ. Cùng một kỹ thuật, kết quả khác nhau vì yêu cầu và ranh giới hệ thống khác nhau.

## 4. Quan hệ hỗ trợ: rõ ràng hơn có thể làm thay đổi an toàn hơn

Xét một hàm tính chiết khấu. Mục tiêu nghiệp vụ: khách VIP được giảm 10% nếu đơn hàng từ 1.000.000 VND trở lên. Để minh họa, giá trị tiền là số nguyên VND, đơn hàng không âm.

Một phiên bản cô đọng nhưng khó hiểu:

~~~java
static long discount(long x, boolean y) {
    return y && x >= 1_000_000 ? x / 10 : 0;
}
~~~

Mã có thể đúng với các đầu vào hợp lệ, nhưng tên **x**, **y** buộc người đọc tự đoán, điều kiện biên và hành vi với giá trị âm không được diễn đạt rõ.

Có thể cải thiện mà không cần thêm tầng kiến trúc:

~~~java
final class DiscountPolicy {
    private static final long VIP_MINIMUM_ORDER_VND = 1_000_000L;

    static long discountVnd(long orderTotalVnd, boolean isVip) {
        if (orderTotalVnd < 0) {
            throw new IllegalArgumentException(
                    "Order total must not be negative");
        }

        boolean eligibleForVipDiscount =
                isVip && orderTotalVnd >= VIP_MINIMUM_ORDER_VND;

        return eligibleForVipDiscount ? orderTotalVnd / 10 : 0;
    }
}
~~~

Thay đổi này hỗ trợ đồng thời:

- **Dễ đọc:** tên biến và hằng số giúp nhận ra chính sách nghiệp vụ.
- **Đúng đắn:** từ chối dữ liệu âm theo giả định đầu vào; điều kiện ở ngưỡng 1.000.000 được biểu đạt rõ.
- **Dễ kiểm thử:** phương thức thuần với đầu vào và đầu ra xác định, không gọi hệ thống ngoài.
- **Dễ thay đổi:** nếu ngưỡng thay đổi, có một nơi thể hiện chính sách.

Một vài bài kiểm thử JUnit 5 có thể khóa hành vi quan trọng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DiscountPolicyTest {
    @Test
    void appliesDiscountAtBoundaryForVip() {
        assertEquals(100_000L,
                DiscountPolicy.discountVnd(1_000_000L, true));
    }

    @Test
    void doesNotApplyBelowBoundary() {
        assertEquals(0L,
                DiscountPolicy.discountVnd(999_999L, true));
    }

    @Test
    void doesNotApplyForNonVip() {
        assertEquals(0L,
                DiscountPolicy.discountVnd(1_000_000L, false));
    }

    @Test
    void rejectsNegativeTotal() {
        assertThrows(IllegalArgumentException.class,
                () -> DiscountPolicy.discountVnd(-1L, true));
    }
}
~~~

Đây là ví dụ về **quan hệ cộng hưởng**: tăng rõ ràng và kiểm chứng giúp sửa đổi ít rủi ro hơn. Tuy nhiên, bộ kiểm thử chỉ xác nhận các ca được viết; nếu nghiệp vụ quy định làm tròn khác hoặc cần xử lý giá trị tiền vượt giới hạn, vẫn phải bổ sung yêu cầu và ca kiểm thử tương ứng. Không nên kết luận “đã tuyệt đối đúng” từ vài trường hợp.

## 5. Quan hệ xung đột: tối ưu độ trễ nhưng làm dữ liệu có thể cũ

Một dịch vụ đọc giá hàng hóa từ nguồn dữ liệu. Để giảm độ trễ, nhóm thêm cache.

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class NaivePriceService {
    private final Map<String, BigDecimal> cache =
            new ConcurrentHashMap<>();
    private final PriceRepository repository;

    NaivePriceService(PriceRepository repository) {
        this.repository = repository;
    }

    BigDecimal currentPrice(String sku) {
        return cache.computeIfAbsent(
                sku, repository::loadCurrentPrice);
    }
}

interface PriceRepository {
    BigDecimal loadCurrentPrice(String sku);
}
~~~

Phần cache có thể giúp giảm truy vấn cho cùng **sku**. Nhưng **computeIfAbsent** chỉ nạp lần đầu và không tự làm mới giá khi nguồn thay đổi. Nếu yêu cầu là “giá hiển thị phải phản ánh phiên bản bảng giá đang hiệu lực”, phương án này có thể tạo lỗi nghiệp vụ dù độ trễ tốt.

Phải làm rõ hợp đồng trước khi sửa:

- Giá được phép cũ tối đa bao lâu?
- Một đơn hàng phải dùng giá tại thời điểm nào: lúc xem, lúc đặt hay lúc xác nhận?
- Ai phát hành thay đổi giá và làm thế nào các instance nhận biết?
- Cache cần xử lý giới hạn bộ nhớ, thời gian hết hạn và tải đồng thời ra sao?

Một lựa chọn là cache theo **phiên bản bảng giá bất biến**, nếu nguồn dữ liệu thật sự hỗ trợ truy vấn giá theo phiên bản:

~~~java
import java.math.BigDecimal;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

record PriceKey(String sku, long catalogVersion) {}

interface VersionedPriceRepository {
    BigDecimal loadPrice(String sku, long catalogVersion);
}

final class VersionedPriceService {
    private final ConcurrentMap<PriceKey, BigDecimal> cache =
            new ConcurrentHashMap<>();
    private final VersionedPriceRepository repository;

    VersionedPriceService(VersionedPriceRepository repository) {
        this.repository = repository;
    }

    BigDecimal priceAt(String sku, long catalogVersion) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (catalogVersion < 0) {
            throw new IllegalArgumentException(
                    "catalogVersion must not be negative");
        }

        PriceKey key = new PriceKey(sku, catalogVersion);
        return cache.computeIfAbsent(
                key,
                k -> repository.loadPrice(k.sku(), k.catalogVersion()));
    }
}
~~~

**Điều kiện để ví dụ này đúng:** **catalogVersion** đại diện cho một snapshot nhất quán, dữ liệu giá theo phiên bản không bị sửa, và thành phần gọi biết phiên bản cần áp dụng. Nếu những điều kiện đó không được đáp ứng, đưa phiên bản vào khóa cache **không giải quyết được tính đúng đắn**. Đây cũng chỉ là mã minh họa; cache có thể tăng không giới hạn nên hệ thống thực cần chính sách giới hạn kích thước/loại bỏ mục cũ hoặc giải pháp tương ứng.

Bài học rút ra: có thể đạt **hiệu năng** và **độ nhất quán** bằng một hợp đồng dữ liệu rõ ràng, nhưng phải chấp nhận **chi phí thiết kế, vận hành và bộ nhớ**. Quyết định tốt là quyết định đáp ứng mức nhất quán thực sự cần, được kiểm chứng bằng bài kiểm thử và số đo tải thực tế.

## 6. Xung đột khác: quan sát nhiều hơn có thể tăng rủi ro bảo mật

Log giúp chẩn đoán lỗi, hỗ trợ vận hành và phát hiện hành vi bất thường. Nhưng ghi toàn bộ request có thể vô tình lưu:

- Mật khẩu, token truy cập hoặc khóa API.
- Thông tin định danh cá nhân, số thẻ hoặc dữ liệu nhạy cảm.
- Payload lớn làm tăng I/O, chi phí lưu trữ và thời gian phản hồi.
- Quá nhiều thông báo trùng lặp, che khuất dấu hiệu quan trọng.

Giải pháp thường là **ghi các trường cần cho việc điều tra** thay vì toàn bộ dữ liệu:

~~~java
// Minh họa: không log token hoặc dữ liệu thanh toán.
logger.info("orderAccepted orderId={} result={}",
        orderId, "ACCEPTED");
~~~

Ngay cả **orderId** cũng cần được đánh giá theo chính sách dữ liệu và quyền truy cập log của hệ thống. Có thể ưu tiên correlation ID không chứa thông tin cá nhân, che dữ liệu theo quy định và giới hạn thời gian lưu. Khi cần điều tra sâu, việc tăng mức log nên có kiểm soát, giới hạn thời gian và kiểm tra quyền truy cập.

Ở đây có sự hỗ trợ giữa **observability** và **reliability** nhưng cũng có rủi ro đối với **security/privacy** và **performance**. Phương án hợp lý bảo toàn lượng thông tin cần thiết mà không làm lộ dữ liệu hoặc tạo gánh nặng tài nguyên không cần thiết.

## 7. Tái sử dụng và đơn giản: giảm trùng lặp chưa chắc giảm chi phí thay đổi

Hai hàm có vài dòng giống nhau có thể đại diện cho hai khái niệm độc lập:

- Một dịch vụ tính **phí hủy đơn** theo hợp đồng khách hàng.
- Một dịch vụ tính **phí hoàn hàng** theo chính sách kho vận.

Hôm nay cả hai cùng nhân một tỷ lệ 5%. Nếu đưa chúng vào một hàm “tính phí chung” chỉ vì công thức giống nhau, yêu cầu mới của một nghiệp vụ có thể buộc sửa logic dùng chung và làm hỏng nghiệp vụ kia.

Lựa chọn phù hợp phụ thuộc vào **nguyên nhân thay đổi**:

| Quan sát | Hành động cân nhắc | Lý do |
| --- | --- | --- |
| Hai đoạn dùng cùng một quy tắc nghiệp vụ và phải luôn đồng bộ | Tập trung hóa quy tắc, kiểm thử dùng chung | Giảm nguy cơ sửa thiếu |
| Hai đoạn tình cờ có công thức tương tự nhưng chính sách độc lập | Giữ ranh giới, có thể chấp nhận ít lặp | Tránh phụ thuộc không mong muốn |
| Có hai cách lấy dữ liệu với hợp đồng giống nhau | Trừu tượng hóa khi cần thay thế nguồn | Giúp kiểm thử và thay đổi triển khai |
| Chỉ có một cách triển khai và chưa có tín hiệu mở rộng | Giữ thiết kế đơn giản, ghi nhận giả thiết | Tránh tạo nhiều tầng trước nhu cầu |

**DRY (Don't Repeat Yourself)** nên tập trung vào trùng lặp **tri thức hoặc quy tắc** hơn là trùng lặp từng ký tự. Mặt khác, việc giữ mọi thứ tách biệt bằng cách sao chép cùng một quy tắc thật sự có thể tăng nợ kỹ thuật. Quan hệ giữa tái sử dụng và dễ bảo trì cần được đánh giá theo bối cảnh thay đổi.

## 8. Song song hóa: thông lượng cao có thể làm kiểm thử và chẩn đoán khó hơn

Giả sử một job xử lý tuần tự 10.000 tác vụ độc lập. Chạy nhiều tác vụ đồng thời có thể tăng thông lượng nếu phần lớn thời gian chờ I/O. Nhưng nếu các tác vụ cùng cập nhật một số dư hoặc một bản ghi tổng hợp mà không có cơ chế đồng bộ thích hợp, hệ thống có thể gặp **race condition**.

Song song hóa có thể tạo chi phí mới:

- Trạng thái chia sẻ và thứ tự thực thi khó dự đoán.
- Lỗi không dễ tái hiện vì phụ thuộc vào lịch chạy.
- Timeout, retry và xử lý trùng có thể phát sinh lỗi nghiệp vụ.
- Lock, điều phối và tranh chấp tài nguyên có thể làm thông lượng không tăng như kỳ vọng.

Không nên chọn concurrency chỉ từ số core CPU. Cần xác định tác vụ có độc lập không, yêu cầu nhất quán là gì, giới hạn tài nguyên ở đâu và tác dụng của retry. Với nghiệp vụ ghi dữ liệu, cơ chế giao dịch, điều kiện cập nhật, khóa hoặc **idempotency** phải phù hợp với dữ liệu và nền tảng đang sử dụng.

Lựa chọn tối ưu có thể là **song song hóa phần tính toán thuần** trong khi giữ **điểm cập nhật trạng thái** có kiểm soát. Như vậy, có thể cải thiện thông lượng mà vẫn quản lý được tính đúng đắn và khả năng kiểm thử.

## 9. Xác định ưu tiên: có tiêu chí bắt buộc và tiêu chí được tối ưu

Đánh đổi có căn cứ thường bắt đầu bằng cách tách hai loại mục tiêu.

**Ràng buộc bắt buộc (must-have):** yêu cầu không được vi phạm. Ví dụ: dữ liệu phải được phân quyền đúng, số tiền không được tính sai, kết quả phải đáp ứng hợp đồng API và điều kiện lưu trữ bắt buộc. Không được đánh đổi một vi phạm rõ ràng để lấy vài mili giây độ trễ.

**Mục tiêu tối ưu (optimize):** được cải thiện trong phạm vi các ràng buộc. Ví dụ: giảm p95 độ trễ từ 350 ms xuống 200 ms, giảm dung lượng heap, giảm thời gian bổ sung một loại báo cáo mới.

Cách lập tiêu chí thực tế:

| Mục tiêu | Cách diễn đạt thiếu rõ ràng | Cách diễn đạt có thể kiểm chứng |
| --- | --- | --- |
| Đúng đắn | “Tính phí phải chuẩn” | “Áp dụng đúng chính sách phí tại phiên bản được xác định; kiểm thử trường hợp biên và hoàn tiền” |
| Hiệu năng | “API thật nhanh” | “p95 thời gian xử lý dưới 250 ms tại tải 100 yêu cầu/giây trong môi trường thử nghiệm xác định” |
| Tin cậy | “Không bị lỗi” | “Job được chạy lại an toàn, có thông báo lỗi và không tạo bản ghi trùng khi retry theo hợp đồng” |
| Dễ thay đổi | “Kiến trúc sạch” | “Thêm một phương thức thanh toán mới mà không cần sửa logic của những phương thức hiện có, ngoài điểm đăng ký tích hợp” |
| Quan sát | “Log đầy đủ” | “Có request ID, loại lỗi và thời gian xử lý, không lưu bí mật hoặc dữ liệu không cần thiết” |

Các con số hiệu năng là **ví dụ**; dự án thật phải đặt ngưỡng từ yêu cầu người dùng, khả năng hạ tầng và dữ liệu đo đạc.

Một phương án chỉ đáng được xem là cải thiện nếu giữ được **các ràng buộc bắt buộc**. Trong nhóm phương án còn lại, nhóm mới so sánh chi phí xây dựng, độ phức tạp, tốc độ thay đổi và lợi ích hiệu năng.

## 10. Phương pháp đánh giá một đánh đổi kỹ thuật

### Bước 1 — Mô tả tác vụ và bối cảnh

Đây là mã thử nghiệm, công cụ nội bộ hay dịch vụ được duy trì lâu dài? Ai sử dụng và hậu quả khi sai là gì? Nơi nào là đường chạy nóng và nơi nào chỉ thỉnh thoảng được dùng? Một tối ưu cho hệ thống phục vụ hàng triệu request khác với tối ưu cho script chạy một lần mỗi tháng.

### Bước 2 — Chốt ràng buộc, ưu tiên và thước đo

Nêu rõ yêu cầu bắt buộc, mục tiêu mong muốn và cách đo. Ví dụ: “không trả giá của phiên bản bảng giá khác”, “p95 dưới ngưỡng đã thống nhất”, “người bảo trì có thể kiểm thử offline”. Đừng lấy số dòng mã hoặc điểm lint làm thước đo duy nhất cho khả năng bảo trì.

### Bước 3 — Đề xuất ít nhất hai phương án thực tế

Nên có **phương án giữ nguyên** để so sánh, cùng một hoặc vài thay đổi hợp lý. Mỗi phương án ghi lợi ích, rủi ro, phụ thuộc và chi phí triển khai. Tránh tạo một phương án giả yếu để phương án yêu thích luôn thắng.

### Bước 4 — Thu thập bằng chứng cân xứng với rủi ro

Dùng benchmark phù hợp, kiểm thử hợp đồng, kiểm thử hồi quy, code review, spike kỹ thuật hoặc dữ liệu vận hành. Với Java, benchmark vi mô có thể cần công cụ chuyên dụng như JMH, warm-up và cấu hình JVM hợp lý; đồng hồ đo thời gian cho một lần chạy thường không đủ kết luận về hiệu năng.

### Bước 5 — So sánh các phương án và chấp nhận hậu quả rõ ràng

Một bảng quyết định ngắn có thể dùng:

| Phương án | Độ trễ | Tính đúng đắn | Chi phí bảo trì | Nhận xét |
| --- | --- | --- | --- | --- |
| Truy vấn trực tiếp, chưa có cache | Cao hơn nhưng đo được | Nguồn dữ liệu mới nhất theo hợp đồng | Ít cơ chế | Thích hợp nếu đã đạt SLO |
| Cache không có chính sách làm mới | Có thể thấp | Rủi ro dữ liệu cũ không kiểm soát | Thấp ban đầu, tăng khi gặp sự cố | Không phù hợp nếu vi phạm yêu cầu nhất quán |
| Cache có hợp đồng phiên bản và giới hạn dung lượng | Có thể thấp | Có thể kiểm chứng theo snapshot | Thêm quản lý phiên bản và cache | Cân nhắc khi số đo chứng minh lợi ích |

Các nhận xét trong bảng là định tính. Khi quyết định thật, cần thay bằng kết quả đo trong cùng môi trường và điều kiện thử.

### Bước 6 — Ghi giả thiết và tín hiệu cần đánh giá lại

Ví dụ: “Giữ truy vấn trực tiếp vì p95 hiện dưới 250 ms tại tải sản xuất; xem lại nếu p95 vượt 250 ms trong 7 ngày hoặc số truy vấn cơ sở dữ liệu vượt ngân sách.” Cần nêu ai theo dõi, nguồn số đo và hành động khi ngưỡng xuất hiện.

Điều kiện xem lại là **điểm kích hoạt phân tích**, không tự động là lệnh triển khai thay đổi. Nếu bối cảnh đổi, nhóm đo lại và đưa ra quyết định mới.

## 11. Nhìn mối quan hệ theo thời gian: hôm nay và lần thay đổi tiếp theo

Chất lượng không chỉ đo tại thời điểm chạy. Chi phí của một quyết định còn xuất hiện trong những lần bổ sung tính năng, xử lý sự cố và bàn giao.

Một số đánh đổi thường gặp:

- **Ít tầng trừu tượng:** tăng tính đơn giản và tốc độ triển khai trong phạm vi nhỏ, nhưng có thể khiến quy tắc bị phân tán khi tính năng mở rộng.
- **Nhiều tầng trừu tượng:** có thể cô lập thay đổi ở hệ thống phức tạp, nhưng tăng chi phí hiểu và điều hướng nếu ranh giới chưa có nhu cầu thật.
- **Kiểm thử tự động:** tốn công ban đầu, có thể giảm rủi ro hồi quy và thời gian xác minh qua nhiều lần sửa; kiểm thử quá bám vào chi tiết triển khai lại gây khó refactor.
- **Thiết kế cho khả năng cấu hình:** hỗ trợ thay đổi thường xuyên khi số cấu hình có ý nghĩa, nhưng có thể tạo trạng thái kết hợp khó kiểm thử nếu mở rộng vô hạn.
- **Tối ưu hóa sớm:** đôi khi giúp xử lý giới hạn chắc chắn đã biết, nhưng thường thêm độ phức tạp khi nút thắt chưa được xác nhận.

Vì vậy, “mã dễ bảo trì” phải được hiểu là mã **dễ thay đổi theo kiểu thay đổi có khả năng xảy ra**. Nếu không có bằng chứng, ưu tiên giải pháp đúng, đơn giản, có kiểm thử và đủ điểm mở rộng hợp lý; bổ sung cơ chế phức tạp khi yêu cầu và số đo thực sự đòi hỏi.

## 12. Tình huống luyện tập và gợi ý phân tích

### Tình huống A — Nên bật cache cho danh mục sản phẩm?

API đọc danh mục mất 180 ms ở p95, trong khi yêu cầu là dưới 300 ms. Một nhóm đề xuất thêm cache phức tạp để giảm còn khoảng 80 ms.

**Cần hỏi:** người dùng có thực sự cần giảm nữa không? Giá, tồn kho và danh mục phải tươi ở mức nào? Cần thêm bao nhiêu mã, test, bộ nhớ và cách quan sát cache?

**Gợi ý:** nếu API đã đáp ứng mục tiêu và chưa có nút thắt, có thể giữ thiết kế đơn giản. Nếu tải dự kiến tăng hoặc truy vấn gây nghẽn, thử cache với hợp đồng dữ liệu rõ ràng và đo lại. Không kết luận chỉ từ một số p95.

### Tình huống B — Có nên ghi nguyên payload để điều tra lỗi?

Đội vận hành khó tái hiện một số lỗi nhập liệu và đề xuất log toàn bộ request.

**Cần hỏi:** payload có bí mật hoặc dữ liệu cá nhân không? Có thể chỉ log schema version, request ID, mã loại lỗi và trường vi phạm không? Ai có quyền xem log và dữ liệu lưu bao lâu?

**Gợi ý:** cải thiện quan sát bằng dữ liệu có chọn lọc, bảo vệ thông tin cần bảo vệ và đo ảnh hưởng I/O. Tối đa hóa độ chi tiết log không đồng nghĩa tối đa hóa chất lượng.

### Tình huống C — Có nên gom hai chính sách cùng công thức?

Chính sách chiết khấu cho đối tác và chiết khấu nội bộ hiện cùng 5%, được lưu ở hai vị trí.

**Cần hỏi:** chúng có chung nguồn quy tắc không, hay có thể thay đổi độc lập? Ai phê duyệt mỗi chính sách? Nếu một chính sách tăng lên 7%, chính sách kia phải thay đổi không?

**Gợi ý:** nếu bản chất độc lập, giữ chúng tách biệt có thể giúp thay đổi an toàn; nếu bắt buộc đồng bộ, trùng lặp gây rủi ro sửa thiếu. Phân tích ý nghĩa nghiệp vụ trước khi trừu tượng hóa.

## 13. Những nhầm lẫn thường gặp

**“Tăng một tiêu chí chắc chắn phải giảm tiêu chí khác.”** Không đúng. Đặt tên rõ ràng, bỏ điều kiện dư thừa hoặc tách logic thuần có thể giúp nhiều tiêu chí đồng thời.

**“Mã có hiệu năng tốt là mã chất lượng cao.”** Chưa đủ. Phải kiểm tra tính đúng đắn, bảo mật, khả năng khôi phục và khả năng thay đổi theo nhu cầu.

**“Càng có nhiều lớp thì càng dễ bảo trì.”** Không nhất thiết. Abstraction chỉ có giá trị khi nó thể hiện ranh giới có ý nghĩa và giúp kiểm soát thay đổi.

**“Có nhiều bài kiểm thử nên chắc chắn đáng tin cậy.”** Số lượng test không đảm bảo bao phủ đúng rủi ro. Kiểm thử bỏ sót trường hợp biên, phụ thuộc thật hoặc tình huống lỗi vẫn có thể để lọt sự cố.

**“Chỉ cần nhìn code để biết lựa chọn nào nhanh hơn.”** Nhiều kết luận hiệu năng cần dữ liệu chạy thực tế và benchmark đúng cách. Thuật toán có độ phức tạp tốt hơn về lý thuyết cũng có thể không hiệu quả hơn với dữ liệu nhỏ hoặc chi phí triển khai thực tế.

**“Chỉ số càng nhiều càng dễ ra quyết định.”** Quá nhiều số đo không gắn với nhu cầu có thể làm nhiễu. Nên chọn tiêu chí biểu đạt hành vi mong muốn, giá trị cho người dùng và rủi ro thiết yếu.

**“Một giải pháp tốt cho mọi dự án.”** Không đúng. Tác động của lỗi, quy mô, tuổi thọ, năng lực vận hành và dạng thay đổi quyết định giá trị của từng tiêu chí.

## 14. Bộ câu hỏi dùng khi review quyết định kỹ thuật

Trước một đề xuất “cải thiện chất lượng”, hãy hỏi:

1. **Đang muốn nâng cao tiêu chí gì?** Diễn đạt bằng hành vi và bằng chứng cụ thể.
2. **Điều gì không được phép xấu đi?** Ghi các ràng buộc về đúng đắn, an toàn dữ liệu, bảo mật, tương thích.
3. **Có tiêu chí nào cùng được hưởng lợi?** Tìm cơ hội đơn giản hóa, cô lập phụ thuộc hoặc tăng khả năng kiểm thử.
4. **Chi phí bị chuyển sang đâu?** Độ phức tạp, bộ nhớ, I/O, thao tác vận hành, thời gian onboarding?
5. **Đã đo hay mới suy đoán?** Phân biệt dữ kiện, giả thiết và dự báo.
6. **Giải pháp có phù hợp với bối cảnh hiện tại?** Đang thử nghiệm ngắn hạn, vận hành nội bộ hay duy trì lâu dài?
7. **Khi nào cần xem lại?** Nêu điều kiện kích hoạt, người phụ trách và cách thu thập số đo.

Quan hệ giữa các tiêu chí chất lượng là **động**, có thể đổi khi yêu cầu và quy mô thay đổi. Thực hành tốt trong **CODE_QUALITY_FUNDAMENTALS** là xác định ràng buộc không thể vi phạm, ưu tiên lợi ích có thể kiểm chứng, chấp nhận đánh đổi có lý do và ghi điều kiện xem lại. Nhờ đó, mã nguồn có thể đồng thời **đáng tin cậy, dễ hiểu và dễ thay đổi** trong bối cảnh mà nó thực sự phục vụ.
