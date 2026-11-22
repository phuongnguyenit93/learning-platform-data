# Tránh áp dụng một bộ quy tắc tuyệt đối cho mọi loại mã

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao cùng một quy tắc thiết kế hoặc phong cách mã nguồn có thể hữu ích ở bối cảnh này nhưng gây tốn kém hoặc rủi ro ở bối cảnh khác.
2. Phân biệt **nguyên tắc cốt lõi phải bảo vệ** với **quy ước và kinh nghiệm thực hành cần vận dụng linh hoạt**.
3. Đánh giá đánh đổi giữa tính đúng đắn, dễ hiểu, khả năng thay đổi, hiệu năng, an toàn và chi phí phát triển.
4. Lựa chọn cách tổ chức, kiểm thử và rà soát phù hợp cho mã nghiệp vụ, mã tích hợp, đoạn xử lý hiệu năng cao, công cụ dùng một lần và mã sinh tự động.
5. Giải thích và ghi lại ngoại lệ đối với quy ước chung một cách có trách nhiệm.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã được xem xét qua những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Một sai lầm thường gặp là biến các lời khuyên như “hàm càng ngắn càng tốt”, “luôn tránh lặp mã”, “mọi lớp phải có interface” hay “độ bao phủ kiểm thử phải đạt một con số cố định” thành yêu cầu áp dụng cho mọi nơi.

Những lời khuyên đó thường chứa kinh nghiệm hữu ích, nhưng **giá trị của chúng phụ thuộc vào nhiệm vụ và rủi ro mà đoạn mã đang xử lý**. Vấn đề không nằm ở việc có tuân thủ một khẩu hiệu hay không; vấn đề là quyết định đó giúp hay cản trở chất lượng thực tế.

## 1. Vì sao không có một công thức chất lượng cho mọi đoạn mã?

Hãy đặt bốn loại mã cạnh nhau:

- **Tính giá đơn hàng:** sai một điều kiện biên có thể khiến khách hàng bị tính sai tiền. Tính đúng đắn, khả năng kiểm thử và việc biểu diễn số tiền rõ ràng là ưu tiên cao.
- **Xử lý dữ liệu lớn trong đường chạy nóng:** một phép cấp phát thừa có thể lặp lại hàng triệu lần. Tính đúng đắn vẫn bắt buộc, nhưng hiệu năng được đo đạc có thể biện minh cho cách viết ít trừu tượng hơn.
- **Script di chuyển dữ liệu chạy một lần:** mục tiêu là chuyển đổi an toàn, có thể kiểm chứng và phục hồi. Thiết kế cho hàng chục phương án mở rộng trong tương lai có thể không đem lại giá trị.
- **Test mô tả quy tắc nghiệp vụ:** việc lặp một ít dữ liệu thiết lập có thể giúp mỗi test tự giải thích. Gom hết thành một helper tổng quát đôi khi làm mất ý nghĩa mà test cần truyền đạt.

Cả bốn đều cần mã đúng và đủ dễ hiểu đối với người chịu trách nhiệm. Tuy nhiên, **thứ tự ưu tiên, tuổi thọ, tần suất thay đổi, chi phí sự cố và cách kiểm chứng** khác nhau.

### Những câu hỏi xác định bối cảnh

| Câu hỏi | Vì sao quan trọng? | Ví dụ |
| --- | --- | --- |
| Mã phục vụ mục đích gì? | Xác định kết quả phải bảo vệ | Tính tiền, hiển thị, đồng bộ dữ liệu, đo hiệu năng |
| Ai sẽ dùng và bảo trì mã? | Ảnh hưởng cách đặt tên, tài liệu và cấu trúc | Nhiều đội cùng gọi API hay một nhóm sở hữu tool nội bộ |
| Mã tồn tại bao lâu? | Quyết định mức đầu tư vào mở rộng và trừu tượng hóa | Luồng nghiệp vụ nhiều năm so với migration chỉ chạy lúc triển khai |
| Mã thay đổi thường xuyên ở đâu? | Cho biết điểm cần cô lập và nơi nên giữ đơn giản | Chính sách khuyến mại thay đổi mỗi tháng |
| Nếu sai, hậu quả là gì? | Quyết định mức độ kiểm thử, kiểm tra an toàn và giám sát | Sai số hiển thị so với chuyển nhầm tiền |
| Có giới hạn đo được nào? | Tránh tối ưu theo cảm giác | Độ trễ p99, lượng bộ nhớ, ngân sách truy vấn |
| Đoạn mã có hợp đồng bên ngoài không? | Thay đổi hình thức có thể phá tương thích | API công khai, dữ liệu lưu trữ, event schema |

Chỉ nói “đây là best practice” chưa đủ để trả lời những câu hỏi trên. Một quyết định kỹ thuật cần nêu **rủi ro cần giảm**, **chi phí phát sinh** và **bằng chứng đánh giá**.

## 2. Quy tắc thực hành là công cụ ra quyết định, không phải mục tiêu tự thân

Một quy tắc hữu ích thường mô tả điều kiện mặc định tốt. Khi bối cảnh thay đổi, ta cần kiểm tra xem lợi ích ban đầu còn tồn tại hay không.

| Lời khuyên thường nghe | Khi nào có giá trị? | Khi áp dụng máy móc có thể gây gì? | Cách đặt câu hỏi tốt hơn |
| --- | --- | --- | --- |
| **Hàm phải thật ngắn** | Hàm đang trộn nhiều trách nhiệm hoặc nhánh khó hiểu | Chia một thuật toán liền mạch thành nhiều hàm nhỏ chỉ chuyển tiếp dữ liệu, làm mất mạch đọc | Hàm có một mục đích rõ và người đọc theo dõi được luồng không? |
| **Không được lặp mã (DRY)** | Nhiều nơi thực sự chia sẻ một quy tắc và cùng lý do thay đổi | Gom hai nghiệp vụ chỉ tình cờ giống nhau, khiến sửa một nơi ảnh hưởng nơi khác | Đây là cùng tri thức nghiệp vụ hay chỉ giống cú pháp? |
| **Luôn tạo interface cho lớp** | Có nhiều cách triển khai thật, ranh giới module hoặc nhu cầu thay thế rõ ràng | Tạo thêm tầng điều hướng, tên gọi rỗng và cấu hình không cần thiết | Interface có diễn đạt hợp đồng ổn định hoặc giúp cô lập phụ thuộc không? |
| **Mọi dữ liệu đều bất biến** | Trạng thái không nên đổi, chia sẻ dữ liệu cần an toàn, cần suy luận đơn giản | Sao chép cấu trúc lớn nhiều lần trong vòng lặp nóng dù không mang lại lợi ích tương xứng | Bất biến bảo vệ điều kiện nào, chi phí cấp phát là bao nhiêu? |
| **Luôn dùng Stream** | Biểu thức biến đổi dữ liệu tuyến tính, dễ đọc | Pipeline phức tạp gây khó debug hoặc cấp phát không cần thiết trong hot path | Stream hay vòng lặp giúp thể hiện ý định rõ hơn và đáp ứng hiệu năng đo được? |
| **Mọi lỗi phải bắt tại chỗ** | Có hành động phục hồi hoặc chuyển lỗi thành hợp đồng tại đúng ranh giới | Nuốt ngoại lệ, log lặp nhiều lần hoặc báo thành công giả | Vị trí nào thực sự biết cách xử lý hoặc bổ sung ngữ cảnh cho lỗi? |
| **Coverage phải đạt 100%** | Một số đoạn logic rất nhỏ, cực kỳ trọng yếu và có thể bao phủ đầy đủ | Test chỉ chạy qua mã mà không xác nhận đúng hành vi; bỏ qua kiểm tra tích hợp | Test có bắt được những lỗi quan trọng và điều kiện biên không? |
| **Không bao giờ viết comment** | Comment chỉ lặp lại điều mã đã nói hoặc đã lỗi thời | Mất lý do nghiệp vụ, bất biến hay đánh đổi quan trọng không suy ra từ cú pháp | Comment có giải thích “tại sao” mà mã không thể nói rõ không? |
| **Mọi nơi phải giống một mẫu kiến trúc** | Thành phần có cùng vai trò và cùng yêu cầu thay đổi | Ép tác vụ nhỏ hoặc dữ liệu đơn giản qua nhiều lớp không cần thiết | Những phần nào thực sự chia sẻ ranh giới, hợp đồng và trách nhiệm? |

Một số nguyên tắc thường hỗ trợ nhau: **KISS** (giữ giải pháp đủ đơn giản), **YAGNI** (chưa xây tính năng chưa có nhu cầu) và **DRY** (tránh lặp tri thức). Tuy nhiên, nếu vận dụng DRY bằng cách tạo abstraction trước khi rõ nhu cầu, ta có thể vi phạm chính KISS và YAGNI. Không thể chọn một khẩu hiệu làm trọng tài tuyệt đối cho tất cả trường hợp.

## 3. Phân biệt chuẩn bắt buộc và lựa chọn linh hoạt

Không nên hiểu “linh hoạt” là được tùy tiện bỏ qua mọi tiêu chuẩn. Có ít nhất hai nhóm khác nhau:

**Nhóm A — Điều kiện phải được đáp ứng.** Chẳng hạn: tính toán phải đúng với hợp đồng nghiệp vụ; không được bỏ qua kiểm soát quyền truy cập; không để lộ khóa bí mật; không được phá tương thích API đã cam kết khi chưa có kế hoạch chuyển đổi; thao tác dữ liệu quan trọng phải đáp ứng yêu cầu an toàn đã xác định. Những điều này là yêu cầu chất lượng hoặc ràng buộc hệ thống. Đội ngũ cần tìm cách đáp ứng, dù cách triển khai khác nhau.

**Nhóm B — Cách thực hiện để đạt mục tiêu.** Ví dụ: giới hạn độ dài hàm, số lớp, cách chia package, dùng Stream hay vòng lặp, dùng chung helper hay viết rõ ràng tại chỗ, định dạng comment. Chúng là lựa chọn kỹ thuật hoặc quy ước; có thể chấp nhận ngoại lệ khi chứng minh được lý do và vẫn thỏa mãn nhóm A.

Một tiêu chuẩn nội bộ có thể bắt buộc theo chính sách dự án. Khi đó, thay đổi tiêu chuẩn cần đi qua quy trình thống nhất của nhóm; lập trình viên không nên tự ý vượt qua quy định. Điều cần tránh là **đồng nhất một lựa chọn thiết kế với một chân lý luôn đúng**, rồi bỏ qua bằng chứng trái ngược.

### Ví dụ về cách trao đổi trong review

Nhận xét chưa đủ rõ:

> Phương thức này có 35 dòng. Theo clean code, phải tách nhỏ.

Nhận xét có căn cứ hơn:

> Phương thức đang vừa xác thực yêu cầu, vừa tính giá và ghi database. Khi test quy tắc giá, ta phải tạo kết nối dữ liệu. Có thể tách phép tính giá khỏi phần I/O để kiểm tra độc lập và giảm khả năng tác dụng phụ không?

Nhận xét thứ hai chỉ ra **trách nhiệm đang bị trộn**, **hậu quả quan sát được** và **hướng cải thiện**. Nếu một phương thức 35 dòng chỉ thực hiện một thuật toán tuyến tính với tên biến rõ ràng, kết luận cần có thể khác.

## 4. Cùng một quy tắc, các loại mã cần quyết định khác nhau

| Loại mã | Ưu tiên thường gặp | Cách đầu tư phù hợp | Điều nên tránh |
| --- | --- | --- | --- |
| **Logic nghiệp vụ cốt lõi** | Đúng hợp đồng, dễ kiểm chứng, dễ thay đổi khi chính sách đổi | Mô hình dữ liệu rõ; test giá trị biên; cô lập quy tắc khỏi I/O | Quy tắc bị sao chép ở nhiều kênh; điều kiện ngầm |
| **API và lớp tích hợp** | Tương thích, xử lý lỗi, bảo mật, khả năng quan sát | Contract/integration test, timeout, retry đúng ngữ nghĩa, mã lỗi rõ | Che giấu lỗi; retry thao tác không an toàn khiến tác dụng phụ nhân đôi |
| **Đường xử lý hiệu năng cao** | Kết quả đúng, độ trễ, tài nguyên | Đo benchmark/profile trước; tối ưu điểm nghẽn; test hồi quy | Tối ưu “trông có vẻ nhanh” và hi sinh tính dễ hiểu khi chưa có số liệu |
| **Migration dữ liệu** | An toàn, tính toàn vẹn, khả năng kiểm chứng và phục hồi | Dry run, sao lưu/điểm phục hồi, kiểm tra số lượng và bất biến, ghi nhận kết quả | Tập trung vào framework tái sử dụng mà quên tình huống chạy dở |
| **Test và fixture** | Dễ hiểu ý định, đáng tin, phản hồi nhanh | Tên test có ý nghĩa; assertion quan sát hành vi; fixture minh bạch | Helper quá tổng quát che dữ liệu quan trọng; test phụ thuộc thứ tự chạy |
| **Tool nội bộ nhỏ** | Đạt mục đích, an toàn trong phạm vi sử dụng, dễ chỉnh sửa vừa đủ | Giao diện đơn giản, kiểm tra lỗi thiết yếu, tài liệu chạy | Mô phỏng kiến trúc hệ thống lớn khi nhu cầu nhỏ và ổn định |
| **Mã sinh tự động** | Phù hợp hợp đồng nguồn sinh, có thể tạo lại ổn định | Kiểm tra template/schema và kết quả sinh; chỉnh sửa ở nguồn | Chỉnh tay file sinh rồi mất thay đổi khi tái tạo |
| **Mã bảo mật hoặc thanh toán** | Đúng đắn, kiểm soát quyền, truy vết và bảo vệ dữ liệu | Thiết kế ranh giới chặt, kiểm thử lỗi và tấn công, review chuyên sâu | Nới bỏ kiểm tra vì muốn đơn giản hoặc nhanh hơn |

Đây là **ưu tiên để phân tích**, không phải quyền miễn trừ. Mã chạy một lần vẫn có thể làm hỏng toàn bộ dữ liệu; mã hiệu năng cao vẫn phải đảm bảo tính đúng đắn và kiểm soát đầu vào; test vẫn phải đáng tin cậy.

## 5. Ví dụ Java 1: DRY không đồng nghĩa phải gom mọi phép tính giống nhau

Giả sử ứng dụng có hai chính sách tính phí vận chuyển:

- **Bán lẻ:** miễn phí nếu tạm tính từ 500.000 đồng; thấp hơn tính 30.000 đồng.
- **Bán sỉ:** tính 20.000 đồng trên mỗi kiện, có quy định riêng về số lượng kiện.

Hai chính sách đều tính “phí vận chuyển” nhưng có **đầu vào và lý do thay đổi khác nhau**. Nếu cố gộp bằng hàng loạt cờ, mã có thể trở nên khó hiểu:

~~~java
// Cách viết dễ tích lũy nhánh khi chính sách tiếp tục thay đổi.
// Minh họa vấn đề thiết kế, không phải mẫu được khuyến nghị.
BigDecimal shippingFee(
        BigDecimal subtotal,
        boolean wholesale,
        int packageCount,
        boolean priority) {

    if (wholesale) {
        BigDecimal base = new BigDecimal("20000")
                .multiply(BigDecimal.valueOf(packageCount));
        return priority ? base.multiply(new BigDecimal("2")) : base;
    }
    return subtotal.compareTo(new BigDecimal("500000")) >= 0
            ? BigDecimal.ZERO
            : new BigDecimal("30000");
}
~~~

Một hàm như vậy dễ phát triển thêm **nhánh theo kênh bán, loại khách, địa điểm, thời điểm**. Người sửa chính sách bán lẻ phải đọc nhiều nhánh bán sỉ không liên quan. Nếu bối cảnh nghiệp vụ cần hai chính sách riêng, có thể biểu diễn trực tiếp:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

final class RetailShippingPolicy {
    private static final BigDecimal FREE_THRESHOLD =
            new BigDecimal("500000");
    private static final BigDecimal STANDARD_FEE =
            new BigDecimal("30000");

    BigDecimal fee(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be non-negative");
        }
        return subtotal.compareTo(FREE_THRESHOLD) >= 0
                ? BigDecimal.ZERO
                : STANDARD_FEE;
    }
}

final class WholesaleShippingPolicy {
    private static final BigDecimal FEE_PER_PACKAGE =
            new BigDecimal("20000");

    BigDecimal fee(int packageCount) {
        if (packageCount <= 0) {
            throw new IllegalArgumentException("packageCount must be positive");
        }
        return FEE_PER_PACKAGE.multiply(
                BigDecimal.valueOf(packageCount));
    }
}
~~~

Ví dụ sử dụng Java 17 hoặc các phiên bản hiện đại có **BigDecimal**. Những mức phí ở đây chỉ là giả định học tập, chưa tính thuế, tiền tệ hoặc chính sách làm tròn thật.

Tách hai chính sách là hợp lý **khi nghiệp vụ xác nhận chúng có thể phát triển độc lập**. Nếu về sau nhiều kênh thực sự dùng chung một chính sách ổn định, nhóm có thể trích xuất thành phần dùng chung lúc có đủ bằng chứng. Việc không tạo abstraction ngay hôm nay không ngăn chúng ta cải tiến ngày mai.

### Kiểm thử thể hiện điểm khác biệt có chủ đích

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class ShippingPolicyTest {
    @Test
    void retailBecomesFreeAtExactThreshold() {
        var policy = new RetailShippingPolicy();

        assertEquals(BigDecimal.ZERO,
                policy.fee(new BigDecimal("500000")));
        assertEquals(new BigDecimal("30000"),
                policy.fee(new BigDecimal("499999")));
    }

    @Test
    void wholesaleUsesNumberOfPackages() {
        var policy = new WholesaleShippingPolicy();

        assertEquals(new BigDecimal("60000"), policy.fee(3));
        assertThrows(IllegalArgumentException.class,
                () -> policy.fee(0));
    }
}
~~~

Hai test không cần có cấu trúc giống hệt nhau. Chúng cùng tuân thủ nguyên tắc **xác nhận hợp đồng và trường hợp biên**, nhưng kiểm tra những quy tắc nghiệp vụ khác nhau. Đó là sự thống nhất ở mục tiêu chất lượng, đồng thời linh hoạt ở cách thực hiện.

## 6. Ví dụ Java 2: dễ đọc và hiệu năng đều quan trọng, nhưng phải đo đúng điểm nghẽn

Lời khuyên “ưu tiên biểu thức khai báo bằng Stream” thường giúp mã xử lý danh sách dễ đọc. Tuy nhiên, trong một đường xử lý chạy hàng triệu lần mỗi giây, việc tránh cấp phát và thao tác trung gian có thể quan trọng. Điều ngược lại cũng đúng: thay mọi Stream bằng vòng lặp vì tin rằng “loop luôn nhanh hơn” là một kết luận thiếu bằng chứng.

Giả sử cần tính tổng các mẫu thời gian thực thi không âm, đơn vị mili giây. Một cách viết trực tiếp:

~~~java
final class LatencySamples {
    private LatencySamples() {}

    static long totalMillis(int[] samples) {
        long total = 0L;
        for (int sample : samples) {
            if (sample < 0) {
                throw new IllegalArgumentException("negative latency");
            }
            total = Math.addExact(total, (long) sample);
        }
        return total;
    }
}
~~~

Ở đây, vòng lặp thuận tiện vì:
- Có thể kiểm tra dữ liệu không hợp lệ ngay tại mỗi phần tử.
- Cộng vào **long** và dùng **Math.addExact** để báo lỗi khi tràn số, tránh âm thầm cho kết quả sai.
- Không cần tạo collection trung gian.

Có thể viết bằng Stream với ngữ nghĩa tương đương; lựa chọn nào tốt hơn phải dựa trên **tính rõ ràng, đặc trưng dữ liệu và kết quả đo trong môi trường đại diện**. Đối với một danh sách nhỏ ở đường chạy hiếm khi sử dụng, khác biệt vài nano giây (nếu có) thường không đáng đổi lấy độ khó đọc. Với một nút thắt đã được profiler xác định, thay đổi cách duyệt có thể đáng làm nếu benchmark và test chứng minh lợi ích.

Khi tối ưu, hãy ghi lại:
1. **Chỉ số:** độ trễ trung bình, p95/p99, throughput, phân bổ bộ nhớ hay mức sử dụng CPU.
2. **Mốc trước thay đổi:** đo được khi chạy dữ liệu và cấu hình phù hợp.
3. **Hành vi bất biến:** kết quả, thứ tự, xử lý giá trị không hợp lệ và điều kiện biên phải giữ nguyên.
4. **Kết quả sau thay đổi:** mức cải thiện đủ ý nghĩa so với độ phức tạp thêm vào.

Với Java, **JMH** có thể hỗ trợ microbenchmark; cần tránh đo một đoạn mã bị JIT tối ưu bỏ đi, không làm nóng JVM hoặc dùng dữ liệu không đại diện. Microbenchmark cũng không thay thế đo trong ứng dụng thật, nơi còn có I/O, GC, đồng thời và cache.

## 7. Ví dụ 3: mã dùng một lần vẫn phải đúng, nhưng không nhất thiết cần kiến trúc tổng quát

Xét một công cụ chỉ chạy trong một đợt di chuyển trường dữ liệu **customerCode** sang định dạng mới. Một người có thể đề xuất tạo framework có plugin, factory, nhiều lớp trừu tượng để “đảm bảo mở rộng”. Trước khi đầu tư, cần biết liệu công cụ có thực sự được dùng lại không.

Trong tình huống chỉ chạy một lần, đầu tư có giá trị hơn thường là:

- **Xác nhận tiền điều kiện:** phiên bản schema, số lượng bản ghi và dữ liệu đầu vào đúng như dự kiến.
- **Chạy thử trên bản sao đại diện:** xác định cách xử lý bản ghi bất thường, trùng lặp hoặc thiếu trường.
- **Khả năng chạy lại an toàn:** nếu job dừng giữa chừng, có thể tiếp tục hoặc khôi phục mà không nhân đôi tác dụng phụ.
- **Quan sát tiến trình:** ghi số bản ghi đã đọc, sửa, bỏ qua, thất bại; không log dữ liệu nhạy cảm.
- **Kiểm chứng hậu điều kiện:** kiểm tra bất biến dữ liệu và đối chiếu tổng số bản ghi.
- **Kế hoạch khôi phục:** chuẩn bị backup, rollback hoặc phương án phục hồi phù hợp trước khi sửa dữ liệu thật.

Một file Java rõ ràng với các bước tách vừa đủ, phép kiểm tra đầu vào và báo cáo kết quả có thể đáp ứng mục tiêu hơn một kiến trúc đa tầng. Tuy nhiên, nếu công cụ là nền tảng migration dùng hàng tháng, đầu tư vào thư viện, test và cấu trúc tái sử dụng có thể trở nên hợp lý. **Tuổi thọ và tần suất thay đổi** làm thay đổi quyết định.

## 8. Ví dụ 4: test cần dễ hiểu, không nhất thiết phải cực kỳ DRY

Trong mã sản phẩm, sao chép quy tắc khuyến mại tại nhiều chỗ có thể dẫn tới sai lệch. Trong test, lặp lại một ít dữ liệu cụ thể đôi khi lại làm ý định rõ hơn:

~~~java
@Test
void rejectsOrderWhenQuantityIsZero() {
    var line = new OrderLine("SKU-01", 0, new BigDecimal("100000"));

    assertThrows(IllegalArgumentException.class,
            () -> orderValidator.validate(line));
}

@Test
void acceptsOrderWhenQuantityIsOne() {
    var line = new OrderLine("SKU-01", 1, new BigDecimal("100000"));

    assertDoesNotThrow(() -> orderValidator.validate(line));
}
~~~

**OrderLine**, **orderValidator**, **assertThrows** và **assertDoesNotThrow** ở đây minh họa cấu trúc test theo JUnit Jupiter; giả định **OrderLine** cho phép tạo đầu vào chưa hợp lệ và validator chịu trách nhiệm kiểm tra. Nếu constructor của **OrderLine** đã từ chối số lượng bằng 0, test phải đặt assertion ở constructor thay vì validator.

Trong ví dụ này, việc lặp cách tạo dữ liệu giúp người đọc nhìn ngay điểm khác nhau là **quantity = 0** và **quantity = 1**. Trích xuất helper có 8 tham số hoặc tạo test fixture có trạng thái ngầm có thể làm test khó hiểu hơn.

Ngược lại, nếu thiết lập kết nối kiểm thử phức tạp được lặp ở hàng trăm test, gom thành fixture hoặc factory có tên rõ ràng sẽ giảm công bảo trì. Câu hỏi cần đặt ra là **helper có làm lộ ý định kiểm thử hay che mất nó?**.

Không thể kết luận “test phải luôn trùng lặp” hoặc “test tuyệt đối không lặp”: cả hai cách hiểu đều quá cực đoan.

## 9. Đánh đổi giữa các chiều chất lượng

Trong thực tế, cải thiện một thuộc tính có thể làm tăng chi phí ở thuộc tính khác. Không nên gắn nhãn “mã sạch” chỉ bằng một chỉ số hoặc một hình thức viết.

| Quyết định | Lợi ích có thể đạt | Chi phí/rủi ro có thể phát sinh | Cách kiểm chứng |
| --- | --- | --- | --- |
| Tách thêm lớp và interface | Cô lập phụ thuộc, thay thế cách triển khai | Nhiều điểm điều hướng, phức tạp cấu hình | Xem có ít nhất một ranh giới thay đổi/kiểm thử rõ ràng không |
| Gom logic dùng chung | Sửa một quy tắc ở một nơi | Liên kết các nghiệp vụ vốn thay đổi độc lập | So sánh hợp đồng và lịch sử/yêu cầu thay đổi |
| Ưu tiên dữ liệu bất biến | Dễ suy luận trạng thái, tránh một số lỗi chia sẻ | Tăng sao chép/cấp phát trong một số trường hợp | Test đồng thời, profiler và chỉ số tài nguyên |
| Thêm logging chi tiết | Dễ chẩn đoán sự cố | Tốn chi phí lưu trữ, tăng nhiễu, nguy cơ lộ dữ liệu | Chính sách dữ liệu, log mẫu và khả năng truy vết |
| Kiểm thử end-to-end nhiều hơn | Xác minh luồng xuyên hệ thống | Chậm, dễ bị ảnh hưởng môi trường, khó xác định nguồn lỗi | Xem mức rủi ro được bao phủ so với thời gian phản hồi |
| Viết comment giải thích quyết định | Giúp hiểu ngữ cảnh khó suy ra từ code | Có thể lỗi thời nếu không bảo trì | Comment có giải thích lý do, bất biến hoặc ngoại lệ hữu ích không |
| Tối ưu đường chạy nóng | Giảm CPU, bộ nhớ hoặc độ trễ | Có thể giảm tính rõ ràng và tăng chi phí sửa | Benchmark, profiler, test hồi quy |
| Chuẩn hóa toàn bộ API cũ | Giao tiếp thống nhất hơn | Phá client hiện tại, tốn công di chuyển | Contract test, phân tích client và kế hoạch phiên bản |

Đánh đổi hợp lý không đồng nghĩa với việc sẵn sàng hi sinh tính đúng đắn hay an toàn. Trước tiên phải bảo vệ các **yêu cầu bắt buộc**; sau đó mới chọn giữa những phương án đều đáp ứng yêu cầu.

### Chú ý “chi phí tương lai” và “chi phí hiện tại”

Đôi khi một thiết kế trông phức tạp vì dự đoán rất nhiều khả năng mở rộng chưa được yêu cầu. Chi phí hiện tại là thời gian viết, đọc, sửa và kiểm thử những tầng trừu tượng đó. Lợi ích tương lai chỉ xuất hiện nếu dự đoán thật sự xảy ra.

Ở chiều ngược lại, viết tất cả logic ngay trong một controller có thể rẻ khi bắt đầu nhưng rất đắt khi nhiều giao diện cùng cần quy tắc ấy. Vì vậy, cần phân tích **khả năng xảy ra thay đổi, hậu quả và khả năng đảo ngược quyết định**, thay vì luôn chọn “thiết kế ít lớp nhất” hoặc “thiết kế tổng quát nhất”.

## 10. Một khung ra quyết định dựa trên bối cảnh

Khi gặp bất đồng về code quality, nhóm có thể làm theo quy trình ngắn dưới đây.

### Bước 1 — Mô tả nhiệm vụ và hợp đồng

Viết một hoặc hai câu cho biết đoạn mã giải quyết vấn đề gì và điều kiện nào phải đúng. Chẳng hạn: “Hàm trả phí giao hàng theo chính sách bán lẻ; tổng tạm tính không âm; tại ngưỡng 500.000 đồng thì miễn phí.”

Càng làm rõ hợp đồng, càng dễ nhận ra những quy tắc kỹ thuật chỉ liên quan đến phong cách.

### Bước 2 — Xác định rủi ro và đặc điểm vận hành

Liệt kê những yếu tố thực sự có tác động:
- Sai kết quả ảnh hưởng ai và mức độ nghiêm trọng thế nào?
- Đường chạy có thường xuyên được gọi hay có giới hạn tài nguyên đã đo?
- Ai chịu trách nhiệm bảo trì, có bao nhiêu nơi sử dụng?
- Hợp đồng có nằm ở ranh giới công khai hoặc dữ liệu lâu dài không?
- Thay đổi có dễ hoàn nguyên, có tác động đến dữ liệu đang tồn tại không?

Ưu tiên những rủi ro có hậu quả lớn hoặc khó phục hồi. Không cần biến mọi thay đổi nhỏ thành bản đánh giá dài.

### Bước 3 — Nêu ít nhất hai phương án có thể đáp ứng hợp đồng

Ví dụ: giữ hai chính sách tính phí riêng và dùng chung kiểu tiền; hoặc hợp nhất dưới một giao diện chung nếu có nhiều cách triển khai thực sự. Mô tả điểm mạnh, chi phí đọc hiểu, khả năng test và rủi ro liên kết.

Đừng đưa ra chỉ một phương án rồi gọi đó là “best practice”.

### Bước 4 — Chọn bằng chứng tương ứng

- **Tính đúng đắn:** unit test trường hợp biên, test nghiệp vụ, contract/integration test khi có giao tiếp.
- **Hiệu năng:** profile và benchmark theo tải đại diện, không phỏng đoán từ vẻ ngoài cú pháp.
- **Dễ hiểu:** code review với người bảo trì, mức độ rõ ràng của tên và trách nhiệm.
- **Khả năng thay đổi:** phạm vi phải sửa khi một quy tắc đổi, mức phụ thuộc giữa các phần.
- **An toàn:** kiểm tra quyền, xử lý dữ liệu nhạy cảm, thử tình huống lỗi và phục hồi.

Bằng chứng không nhất thiết là số đo phức tạp; đôi khi một test ranh giới và một diff nhỏ đã đủ chứng minh quyết định.

### Bước 5 — Chọn phương án đủ tốt và ghi lý do nếu có ngoại lệ

Nếu quyết định khác quy ước nhóm, ghi rõ **quy ước nào được điều chỉnh, vì sao, phạm vi áp dụng, bằng chứng và thời điểm xem xét lại**. Có thể dùng mô tả ngắn trong pull request hoặc ADR cho quyết định có ảnh hưởng lâu dài.

Ví dụ:

> **Quyết định:** Giữ vòng lặp trong bộ xử lý mẫu thời gian, dù phần còn lại thường dùng Stream.  
> **Lý do:** Profiler xác định đây là điểm nóng; benchmark với dữ liệu đại diện cho thấy phiên bản vòng lặp giảm đáng kể phân bổ bộ nhớ và đáp ứng giới hạn độ trễ.  
> **Bảo vệ:** Test xác minh kết quả, dữ liệu âm và tràn số; code review kiểm tra bất biến.  
> **Phạm vi:** Chỉ phương thức xử lý mẫu này. Sẽ đo lại nếu thuật toán hoặc phiên bản JVM thay đổi.

Đây là ví dụ về **cách ghi nhận quyết định**; không phải tuyên bố rằng mọi vòng lặp luôn nhanh hơn Stream hoặc rằng kết quả benchmark trên một môi trường áp dụng cho mọi hệ thống.

### Bước 6 — Đánh giá lại khi bối cảnh đổi

Một tool ban đầu chạy một lần có thể trở thành quy trình hằng tuần. Một policy từng chỉ có một cách triển khai có thể phát sinh nhiều biến thể. Một micro-optimization có thể hết tác dụng sau khi nâng JVM. Quy ước nên được xem lại khi **thực tế sử dụng** thay đổi.

## 11. Dấu hiệu áp dụng quy tắc quá cứng nhắc

Những tình huống sau là tín hiệu cần xem lại cách ra quyết định:

1. **Đếm dòng để phán xét độ rõ ràng:** mỗi hàm vượt một ngưỡng cố định đều bị tách, dù các hàm con chỉ chuyển tiếp dữ liệu và khiến luồng khó theo dõi.
2. **Tạo interface theo thói quen:** một lớp có một cách triển khai, không có ranh giới cần thay thế, nhưng vẫn đi qua interface, factory và adapter không mang lại lợi ích cụ thể.
3. **Gộp mọi đoạn trùng lặp:** hai quy tắc nghiệp vụ được ép dùng một helper với nhiều cờ và điều kiện; thay đổi của nhóm này vô tình làm hỏng nhóm khác.
4. **Tối ưu chỉ số coverage:** test tăng số dòng đã chạy nhưng không có assertion phát hiện sai lệch, trong khi luồng quan trọng thiếu kiểm thử tích hợp.
5. **Áp dụng cùng tiêu chuẩn cho mã sinh và mã viết tay:** formatter hoặc refactor thủ công liên tục sửa file generated, rồi mọi thay đổi bị ghi đè khi sinh lại.
6. **Tối ưu hiệu năng theo trực giác:** mã được viết ngắn gọn hoặc phức tạp hơn chỉ vì một câu khẳng định tốc độ, không có số đo hoặc hợp đồng giữ nguyên.
7. **Phớt lờ tính tương thích:** đổi schema lỗi hoặc tên trường vì muốn “đẹp hơn”, nhưng không xem xét client hiện có.
8. **Coi ngoại lệ là thất bại:** đội ngũ phải giấu ngoại lệ hợp lý thay vì giải thích bối cảnh và đưa ra tiêu chí kiểm chứng.

Khi phát hiện một dấu hiệu, không nhất thiết phải bỏ quy ước. Cần quay lại câu hỏi: **quy ước này đang giảm rủi ro nào, và có cách nào đáp ứng mục tiêu tốt hơn trong bối cảnh này?**

## 12. Tình huống tổng hợp: ba thay đổi trong một hệ thống đặt hàng

Nhóm cần thực hiện ba công việc trong cùng sprint:

**A. Sửa lỗi tính phí vận chuyển:** đơn đúng bằng ngưỡng miễn phí đang bị thu phí. Đây là logic nghiệp vụ quan trọng, có thể ảnh hưởng tiền của khách.

**B. Tăng tốc luồng đọc số liệu thống kê:** profiler cho biết một vòng biến đổi hàng triệu bản ghi tạo quá nhiều object trung gian, gây áp lực GC.

**C. Viết migration cập nhật mã định danh cũ:** script chạy trong một đợt triển khai, trên dữ liệu có giá trị và cần khả năng phục hồi.

Nếu áp dụng một bộ quy tắc tuyệt đối như “mọi thay đổi phải có interface, formatter, 100% coverage và dùng Stream”, nhiều yêu cầu quan trọng vẫn không được giải quyết.

| Công việc | Câu hỏi chất lượng quan trọng | Hướng thực hiện có căn cứ |
| --- | --- | --- |
| A — Phí vận chuyển | Hợp đồng ngưỡng được hiểu đúng chưa? Điều kiện biên nào bị sai? Có dùng cùng quy tắc trên mọi kênh không? | Chốt yêu cầu “từ ngưỡng”, test ngay dưới/bằng/trên; đặt quy tắc tại nơi sở hữu rõ |
| B — Đọc thống kê | Độ trễ và phân bổ bộ nhớ thay đổi bao nhiêu? Có giữ kết quả, lỗi và độ chính xác không? | Profile, benchmark, tối ưu cục bộ, giữ test kết quả và số đo trước/sau |
| C — Migration | Nếu chạy dở thì dữ liệu ở trạng thái nào? Có thể chạy lại, đối chiếu và phục hồi không? | Dry run, kiểm tra trước/sau, backup/khôi phục, log tiến trình an toàn |

Cả ba vẫn cần mã có ý định rõ ràng, không chứa lỗi đã biết và tuân thủ ràng buộc dự án. Nhưng **cùng một thước đo hình thức** sẽ không thay thế được việc xác định rủi ro riêng của từng công việc.

## 13. Bài tập thực hành

### Bài tập 1 — DRY hay giữ hai triển khai?

Hai module **refund** và **discount** đang có đoạn tính phần trăm với cùng công thức nhân và chia. Có đề xuất đưa tất cả vào **PercentageBusinessService** dùng chung.

Hãy trả lời:
1. Những thông tin nghiệp vụ nào cần hỏi trước khi quyết định?
2. Khi nào việc gom logic tạo lợi ích thực sự?
3. Khi nào sự tương đồng chỉ là cú pháp và nên giữ hai ranh giới riêng?
4. Nếu dùng chung một phép toán toán học nhỏ, bạn sẽ làm gì để không gộp luôn quy tắc hoàn tiền và giảm giá?

**Gợi ý:** Xem xét quy tắc làm tròn, quyền xử lý, trạng thái, đơn vị tiền, giới hạn hoàn tiền, lý do thay đổi. Có thể chia sẻ hàm toán học có hợp đồng rõ mà vẫn giữ hai policy nghiệp vụ độc lập.

### Bài tập 2 — Mã hiệu năng cao

Một đồng nghiệp thay đoạn code dễ đọc bằng một thuật toán phức tạp hơn và nói: “Cách này nhanh hơn vì không dùng Stream.”

Hãy đề xuất cách review. **Gợi ý:** Yêu cầu xác định điểm nghẽn, tải đại diện, chỉ số trước/sau và test bảo vệ kết quả. Nếu không có bằng chứng về hiệu năng hoặc không có vấn đề cần giải quyết, phương án đơn giản hơn thường dễ bảo trì hơn.

### Bài tập 3 — Đánh giá một quy tắc tuyệt đối

Nhóm đặt tiêu chí: “Mọi method có hơn 20 dòng đều phải tách”. Một method dài 28 dòng xử lý một thuật toán chuyển đổi ngày giờ tuyến tính, có test đầy đủ; một method dài 12 dòng vừa kiểm tra quyền, gửi email và ghi tiền vào database.

Hãy trả lời:
1. Method nào cần xem lại trước, vì sao?
2. Số dòng nói lên điều gì và không nói lên điều gì?
3. Bạn sẽ thay quy tắc hiện tại bằng hướng dẫn review nào?

**Gợi ý:** Trách nhiệm, tác dụng phụ, độ phức tạp nhánh, mức khó kiểm thử và rủi ro phải được ưu tiên hơn một ngưỡng dòng cố định.

### Bài tập 4 — Viết quyết định kỹ thuật ngắn

Chọn một ngoại lệ có thể có trong dự án Java của bạn, ví dụ dùng vòng lặp tại điểm nóng, giữ chút lặp trong test hoặc tách riêng policy cho hai nghiệp vụ. Viết tối đa 6 câu nêu: **bối cảnh, quy ước hiện tại, quyết định, lý do, cách kiểm chứng và điều kiện xem xét lại**.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Nếu không có một bộ quy tắc áp dụng tuyệt đối, có phải mọi lựa chọn về chất lượng đều chủ quan?

*Trả lời:* Không. Hợp đồng, yêu cầu an toàn, dữ liệu, chi phí sự cố và kết quả kiểm thử/đo đạc tạo ra tiêu chí khách quan. Sự linh hoạt nằm ở cách đạt mục tiêu, không phải quyền bỏ mục tiêu.

**Câu 2.** Có nên giảm độ bao phủ kiểm thử vì đây là script chạy một lần?

*Trả lời:* Không thể kết luận từ tuổi thọ ngắn. Migration có thể gây thiệt hại nghiêm trọng; kiểm chứng toàn vẹn, thử với dữ liệu đại diện và kế hoạch phục hồi có thể quan trọng hơn mục tiêu coverage hình thức.

**Câu 3.** Hai đoạn mã có cùng bốn dòng tính toán thì chắc chắn nên gộp?

*Trả lời:* Chưa. Cần xem chúng có chia sẻ cùng hợp đồng và cùng lý do thay đổi hay không. Trùng cú pháp không nhất thiết là trùng tri thức nghiệp vụ.

**Câu 4.** Khi nào chấp nhận một đoạn mã khó đọc hơn để tăng hiệu năng?

*Trả lời:* Khi có giới hạn hiệu năng thực, điểm nghẽn đã được đo, phương án mới cải thiện đủ lớn và vẫn bảo vệ tính đúng đắn, an toàn, khả năng kiểm thử. Lý do và phạm vi tối ưu cần được ghi lại để người khác bảo trì.

**Câu 5.** Nhận xét code review nào có ích hơn: “Không được dùng loop” hay “Đoạn này ở hot path hay xử lý ít dữ liệu? Nếu không có yêu cầu hiệu năng đặc biệt, Stream có thể diễn đạt ý định rõ hơn; nếu có số liệu benchmark, hãy nêu để cùng đánh giá”?

*Trả lời:* Nhận xét thứ hai. Nó liên hệ đề xuất với bối cảnh, lợi ích và bằng chứng, tạo cơ sở quyết định thay vì dựa vào khẩu hiệu.

## Ghi nhớ

**Chất lượng mã nguồn phụ thuộc vào bối cảnh sử dụng và những đánh đổi có thể chứng minh.** Những quy tắc như DRY, KISS, YAGNI, chia nhỏ phương thức, dùng interface, bất biến hay chỉ tiêu coverage là công cụ định hướng; cần áp dụng theo trách nhiệm, mức rủi ro, tuổi thọ và hành vi thực tế của từng loại mã. Các yêu cầu về tính đúng đắn, an toàn và hợp đồng vẫn phải được bảo vệ. Quyết định tốt là quyết định giải thích được **vấn đề đang giải quyết, lợi ích mong đợi, chi phí chấp nhận và cách kiểm chứng**, đồng thời sẵn sàng được xem xét lại khi bối cảnh thay đổi.
