# Kiểm tra hợp đồng, trường hợp biên và luồng lỗi

Một pull request có thể có mã Java dễ đọc, được formatter xử lý và vượt qua tất cả bài kiểm thử hiện có, nhưng vẫn chứa lỗi nghiêm trọng: điều kiện **>** thay vì **>=** tại ngưỡng miễn phí vận chuyển, chấp nhận dữ liệu không hợp lệ, ghi một phần đơn hàng rồi trả lỗi, hoặc thực hiện lại thanh toán sau một timeout không rõ kết quả. Những lỗi như vậy không nhất thiết lộ diện khi chỉ đọc diff theo thứ tự từng dòng.

Trong chương **Rà soát mã** của module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu các thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Bài này hướng dẫn review theo ba câu hỏi kết nối nhau: **hợp đồng cần giữ là gì**, **điều gì xảy ra ở các giá trị biên**, và **hệ thống còn đúng khi đường thực thi đi qua lỗi hay không**.

> Đừng chỉ hỏi “đường thành công có chạy không?”. Hãy hỏi “với mọi nhóm đầu vào và các tình huống thất bại quan trọng, lời hứa của API có còn được giữ không?”.

## 1. Code review cần một chuẩn đúng sai độc lập

**Code review** là quá trình xem xét thay đổi nhằm phát hiện rủi ro, nâng chất lượng thiết kế và chia sẻ hiểu biết. Reviewer không chỉ tìm lỗi cú pháp: compiler đã kiểm tra một phần cú pháp và kiểu. Trách nhiệm quan trọng hơn là đối chiếu mã với **yêu cầu và hợp đồng mà các thành phần liên quan đang phụ thuộc**.

Một đoạn mã trông hợp lý:

~~~java
boolean freeShipping(long subtotalVnd) {
    return subtotalVnd > 500_000L;
}
~~~

Nếu hợp đồng nói “**từ 500.000 VND trở lên**”, dấu so sánh đã sai. Nếu hợp đồng nói “**lớn hơn 500.000 VND**”, cùng biểu thức đó có thể đúng. Reviewer không thể kết luận chỉ từ vẻ ngoài của câu lệnh.

Vì vậy, cần xác định **test oracle**: quy tắc độc lập để biết kết quả nào đúng. Nguồn oracle có thể là đặc tả nghiệp vụ đã thống nhất, hợp đồng API, bảng quyết định, tài liệu dữ liệu, yêu cầu tương thích hoặc một bất biến được xác nhận.

### 1.1. Hợp đồng có nhiều mặt

| Mặt của hợp đồng | Câu hỏi review | Ví dụ |
| --- | --- | --- |
| **Tiền điều kiện** (*precondition*) | Đầu vào nào được chấp nhận, đầu vào nào bị từ chối? | Số lượng từ 1 đến 100 |
| **Hậu điều kiện** (*postcondition*) | Khi thành công, kết quả và trạng thái phải ra sao? | Tổng bằng đơn giá nhân số lượng |
| **Bất biến** (*invariant*) | Điều gì luôn phải đúng trước/sau thao tác? | Tổng tiền lưu không được âm |
| **Lỗi** | Lỗi nào được thông báo và bằng cách nào? | Invalid input gây IllegalArgumentException |
| **Tác dụng phụ** (*side effect*) | Có ghi DB, gửi email, thu tiền, thay cache không? | Không thu tiền khi đầu vào sai |
| **Thứ tự thực hiện** | Có thao tác nào bắt buộc hoàn tất trước thao tác khác? | Xác thực và kiểm tra quyền trước khi ghi |
| **Thời gian và đồng thời** | Có timeout, retry, race hoặc yêu cầu idempotency không? | Cùng request ID không được thu tiền hai lần |
| **Tương thích** | Bên gọi hiện tại có tiếp tục hoạt động không? | Không đổi nghĩa của trường JSON |

Các mục này không phải tất cả đều áp dụng cho mọi hàm. Một hàm tính toán thuần có thể không có tác dụng phụ; một API thanh toán lại phải làm rõ nhiều trạng thái thất bại và tái thử.

### 1.2. Hợp đồng viết ở đâu?

Hợp đồng có thể được thể hiện qua nhiều dạng:

- Javadoc nêu tham số, kết quả, ngoại lệ và trách nhiệm tài nguyên.
- Kiểu dữ liệu như **record**, **enum**, **Optional**, value object hoặc loại kết quả có mã lỗi.
- Constraint của DB và schema API.
- Quy tắc nghiệp vụ trong acceptance criteria hoặc bảng quyết định.
- Contract test và kiểm thử hồi quy có oracle đã xác nhận.
- Tài liệu về thời gian chờ, retry, idempotency và phạm vi hỗ trợ.

**Không nên coi tên phương thức hoặc việc test cũ đang xanh là bản hợp đồng đầy đủ.** Một API có thể có hành vi lâu năm chưa được ghi lại; hoặc test cũ đang vô tình xác nhận một lỗi hiện trạng. Nếu một yêu cầu quan trọng còn mơ hồ, review cần nêu rõ phần thiếu trước khi chấp thuận sửa đổi hành vi.

## 2. Reviewer bắt đầu từ ranh giới thay đổi

Một diff nhỏ vẫn có thể thay đổi những hợp đồng nằm ngoài tệp đang sửa. Trước khi xem từng biểu thức, nên xác định **ai gọi mã này, mã này gọi ai, và dữ liệu đi qua những ranh giới nào**.

~~~text
HTTP/API client
       |
       v
Controller / request validation
       |
       v
Service / quy tắc nghiệp vụ
       |
       +--> Repository / DB transaction
       |
       +--> Payment gateway / external service
       |
       +--> Queue / notification
~~~

Một thay đổi ở service có thể ảnh hưởng:

1. Giá trị response và các trường JSON.
2. Cách exception được ánh xạ thành HTTP status.
3. Số lần gọi DB hoặc cổng thanh toán.
4. Sự nhất quán giữa các bản ghi khi một bước thất bại.
5. Những job theo lịch hoặc module khác cũng gọi service.
6. Khả năng triển khai rolling update và rollback.

### 2.1. Phân biệt điều được phép thay đổi và điều phải giữ

Ví dụ một PR mang tên “tách logic phí vận chuyển khỏi controller”:

| Được phép thay đổi trong PR refactor | Cần giữ nếu không có yêu cầu khác |
| --- | --- |
| Tên biến cục bộ, bố cục phương thức | Ngưỡng tính phí và đơn vị VND |
| Chuyển công thức sang PricingPolicy | Cách báo lỗi đầu vào đã công bố |
| Bổ sung kiểm thử đơn vị | Số lần/thứ tự ghi đơn hàng |
| Giảm phụ thuộc giữa các lớp | JSON response và các client cũ |

Nếu PR đồng thời đổi **500.000 VND** thành **600.000 VND**, đây là thay đổi nghiệp vụ, không phải hệ quả tự nhiên của việc tách phương thức. Reviewer cần yêu cầu oracle mới và đánh giá ảnh hưởng riêng.

### 2.2. Phạm vi review không nhất thiết bằng phạm vi diff

Một thay đổi ở một dòng SQL cần xem:

- Đầu vào có thể do người dùng kiểm soát không?
- Điều kiện tenant hoặc quyền truy cập có còn được áp dụng?
- Có thay đổi cách sắp xếp/pagination làm mất hoặc trùng dữ liệu không?
- Có dùng đúng index hoặc giới hạn tải không?
- Ai xử lý lỗi/timeout và đóng tài nguyên?

Reviewer nên theo **luồng dữ liệu và hợp đồng** đến mức cần thiết, nhưng không biến mọi PR thành cuộc đại tu toàn hệ thống. Nếu thấy vấn đề ngoài phạm vi, cần phân biệt **lỗi chặn thay đổi hiện tại** với **nợ kỹ thuật có thể ghi nhận riêng**.

## 3. Đọc đầu vào bằng phân hoạch tương đương và giá trị biên

Để tìm lỗi mà happy path bỏ sót, có thể phân chia miền đầu vào thành các **lớp tương đương** (*equivalence classes*) và tìm các **điểm chuyển hành vi** (*boundaries*).

Giả sử một API tính báo giá có hợp đồng:

- Mỗi dòng hàng có **quantity trong khoảng 1..100**, tính cả hai đầu.
- **unitPriceVnd** là số nguyên không âm.
- Có ít nhất một dòng hàng.
- Khách VIP được miễn phí vận chuyển nếu subtotal **từ 300.000 VND**.
- Mọi khách đều được miễn nếu subtotal **từ 500.000 VND**.
- Các trường hợp khác trả phí vận chuyển **30.000 VND**.
- Phép tính không được âm thầm tràn phạm vi kiểu **long**.

### 3.1. Phân hoạch tương đương

| Đầu vào | Các lớp đáng review | Kỳ vọng |
| --- | --- | --- |
| quantity | Nhỏ hơn 1, từ 1 đến 100, lớn hơn 100 | Từ chối / chấp nhận / từ chối |
| unitPriceVnd | Âm, bằng 0, dương | Từ chối / chấp nhận / chấp nhận |
| lines | null, rỗng, có phần tử null, hợp lệ | Từ chối / từ chối / từ chối / tính |
| subtotal VIP | Dưới 300.000, từ 300.000 trở lên | Thu phí / miễn |
| subtotal thường | Dưới 500.000, từ 500.000 trở lên | Thu phí / miễn |
| Kết quả số học | Biểu diễn được bằng long, vượt giới hạn | Trả kết quả / báo lỗi |

Không cần thử mọi số trong miền 1..100 để xác minh phép so sánh đơn giản. Nhưng phải chắc chắn mỗi **lớp hành vi** có đại diện và ranh giới phù hợp.

### 3.2. Phân tích ngay sát hai đầu miền giá trị

Với **quantity 1..100**, những giá trị nổi bật:

~~~text
0 | 1 | 2 .......... 99 | 100 | 101
    ^                    ^
    Biên dưới            Biên trên
~~~

| Giá trị | Lý do |
| ---: | --- |
| 0 | Ngay dưới biên dưới, phải bị từ chối |
| 1 | Đúng biên dưới, phải hợp lệ |
| 2 | Ngay trong miền hợp lệ |
| 99 | Ngay trong biên trên |
| 100 | Đúng biên trên, phải hợp lệ |
| 101 | Ngay trên biên trên, phải bị từ chối |

Với ngưỡng VIP **300.000 VND**, kiểm tra **299.999**, **300.000**, **300.001**. Với khách thường, kiểm tra **499.999**, **500.000**, **500.001**. Đây là cách phát hiện nhầm lẫn giữa **>** và **>=**, hoặc giữa **<** và **<=**.

### 3.3. Biên không chỉ là số nguyên

Các ranh giới khác cần cân nhắc khi phù hợp với hợp đồng:

- **Chuỗi:** null, rỗng, chỉ khoảng trắng, độ dài 1, tối đa, tối đa + 1; Unicode có dấu hoặc ký tự ghép.
- **Danh sách:** rỗng, một phần tử, phần tử trùng, phần tử null, đúng/vượt giới hạn.
- **Thời gian:** ngay trước, đúng bằng, ngay sau hạn; ngày nhuận, múi giờ và DST nếu nghiệp vụ liên quan.
- **Trạng thái:** chuyển từ PENDING sang PAID, thao tác lặp khi đã PAID, chuyển trạng thái bị cấm.
- **Quyền truy cập:** người dùng được phép và người dùng không được phép; tài nguyên cùng tenant và khác tenant.
- **Dung lượng và tài nguyên:** hết connection pool, tệp có kích thước 0, kết quả quá lớn, timeout.
- **Kiểu số:** **Integer.MAX_VALUE**, **Long.MAX_VALUE**, số âm, trường hợp làm tròn hoặc tràn số.

Một tên người dùng chứa dấu nháy hoặc tiếng Việt có thể là **dữ liệu bất thường nhưng hợp lệ**, không nên mặc nhiên từ chối. Quy tắc xét dữ liệu phải dựa trên trường cụ thể, không dựa vào cảm giác “ít gặp”.

### 3.4. Tìm các tổ hợp thay vì chỉ một chiều

Một số lỗi chỉ xuất hiện khi nhiều điều kiện gặp nhau:

- VIP đúng ngưỡng và có một dòng hàng giá 0.
- Đơn hàng có nhiều dòng và tổng vượt phạm vi long dù mỗi dòng riêng lẻ hợp lệ.
- Một phiếu giảm giá đúng lúc hết hạn trong khi số dư ví bằng mức tối thiểu.
- Hai request cùng dùng một idempotency key nhưng payload khác nhau.

Với nhiều trường đầu vào, không nên liệt kê mọi tổ hợp một cách máy móc vì số lượng có thể tăng theo cấp số nhân. Ưu tiên các **tương tác có quy tắc hoặc rủi ro thật**; pairwise testing có thể giúp lấy mẫu, nhưng không thay thế hiểu biết về bất biến nghiệp vụ.

## 4. Ví dụ Java: review một API tính báo giá

Xét một đoạn mã có vẻ ngắn và hoạt động với đơn hàng điển hình:

~~~java
public long quote(long unitPriceVnd, int quantity,
                  boolean vip) {
    long subtotalVnd = unitPriceVnd * quantity;
    boolean free = vip && subtotalVnd > 300_000L
            || subtotalVnd > 500_000L;
    return subtotalVnd + (free ? 0L : 30_000L);
}
~~~

Các câu hỏi reviewer cần đặt:

1. Phương thức có từ chối **unitPriceVnd âm** và **quantity ngoài 1..100** không?
2. Khi subtotal đúng **300.000** hoặc **500.000 VND**, điều kiện có đúng yêu cầu “từ ngưỡng trở lên” không?
3. Phép nhân và phép cộng có thể **tràn số long** không?
4. API có xử lý nhiều dòng hàng không, hay caller phải tự cộng?
5. **return** là subtotal hay số phải trả gồm phí? Tên **quote** có nói rõ đơn vị và thành phần giá không?
6. Nếu code này phục vụ một endpoint, API có thực hiện side effect trước khi xác thực đầu vào không?

Không phải vấn đề nào cũng phải giải quyết trong một hàm. Nhưng review cần chỉ ra **hợp đồng thiếu hoặc giả định chưa được ghi**, không chấp nhận chỉ vì ví dụ happy path chạy đúng.

### 4.1. Một phiên bản có hợp đồng rõ hơn

Tệp **QuoteCalculator.java** (Java 17 trở lên):

~~~java
import java.util.List;

public final class QuoteCalculator {
    private static final long VIP_FREE_FROM_VND = 300_000L;
    private static final long ALL_FREE_FROM_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    private QuoteCalculator() {}

    public record Line(long unitPriceVnd, int quantity) {
        public Line {
            if (unitPriceVnd < 0 || quantity < 1 || quantity > 100) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }

        public long subtotalVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    public record Quote(
            long subtotalVnd,
            long shippingFeeVnd,
            long payableVnd) {}

    /**
     * Computes a quote in whole VND without external side effects.
     *
     * @param lines non-null, non-empty list of non-null lines;
     *              caller must not mutate the list during calculation
     * @param vip whether the customer has VIP shipping privileges
     * @return merchandise subtotal, shipping fee and payable amount
     * @throws IllegalArgumentException for invalid input
     * @throws ArithmeticException if arithmetic overflows long
     */
    public static Quote quote(List<Line> lines, boolean vip) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Missing order lines");
        }

        long subtotalVnd = 0L;
        for (Line line : lines) {
            if (line == null) {
                throw new IllegalArgumentException("Null order line");
            }
            subtotalVnd = Math.addExact(
                    subtotalVnd, line.subtotalVnd());
        }

        boolean freeShipping =
                (vip && subtotalVnd >= VIP_FREE_FROM_VND)
                || subtotalVnd >= ALL_FREE_FROM_VND;
        long shippingFeeVnd =
                freeShipping ? 0L : STANDARD_FEE_VND;
        long payableVnd =
                Math.addExact(subtotalVnd, shippingFeeVnd);

        return new Quote(
                subtotalVnd, shippingFeeVnd, payableVnd);
    }
}
~~~

Hợp đồng của ví dụ:

- **Line** yêu cầu đơn giá không âm và số lượng trong **1..100**.
- Danh sách **lines** không được null, rỗng hoặc chứa null. Giá trị không hợp lệ làm phát sinh **IllegalArgumentException**.
- Tiền là **long VND nguyên**, không có làm tròn hay đổi tiền tệ.
- Phép nhân/cộng vượt khả năng biểu diễn của **long** gây **ArithmeticException** từ **Math.multiplyExact/Math.addExact**, không được phép im lặng làm tràn.
- Phương thức **quote** không ghi DB, không gửi thông báo, không thay đổi trạng thái bên ngoài; nó không giữ dữ liệu request trong field.
- Bên gọi không được sửa danh sách khi phương thức đang duyệt. Record **Line** bất biến theo các trường nguyên thủy, nhưng cấu trúc **List** có thể mutable nếu bên gọi cung cấp một ArrayList.

Đây là **chính sách tính phí minh họa**; hệ thống thật có thể phải xét thuế, giảm giá, số lượng tối đa cả đơn, tiền tệ và chính sách giao hàng khác. **Không nên mang các ngưỡng minh họa thành quy tắc thực tế nếu chưa có hợp đồng nghiệp vụ tương ứng.**

### 4.2. Đọc lại implementation theo từng lời hứa

| Lời hứa | Vị trí reviewer kiểm tra | Rủi ro còn lại |
| --- | --- | --- |
| Số lượng chỉ 1..100 | Compact constructor của Line | Có API nào tạo Line theo đường khác không? |
| Không chấp nhận giá âm | Điều kiện **unitPriceVnd < 0** | Giá 0 có hợp lệ đúng hợp đồng không? |
| Không để null/rỗng | Đầu quote và vòng lặp | List có bị sửa đồng thời khi duyệt không? |
| Không tràn số | **multiplyExact/addExact** | Bên gọi có xử lý ArithmeticException đúng không? |
| Ngưỡng bao gồm điểm bằng | **>=** ở hai so sánh | Ngưỡng có đúng phiên bản chính sách không? |
| Không I/O | Không có repository, gateway, logger side effect | Caller phía trên có gọi side effect trước quote không? |
| Kết quả có nghĩa rõ | Record Quote có ba trường và đơn vị VND | Có cần biểu diễn thêm discount/tax không? |

Một phương thức **đúng theo hợp đồng cục bộ** không đồng nghĩa toàn bộ luồng đặt hàng đúng. Review nên chuyển tiếp tới **ranh giới điều phối** nếu API được dùng để tạo đơn hoặc thu tiền.

## 5. Review luồng lỗi như một luồng thực thi chính thức

Đường lỗi không phải “ngoại lệ hiếm có thể bỏ qua”. Dữ liệu sai, mất kết nối, timeout hoặc tranh chấp trạng thái là điều hệ thống có thể gặp khi hoạt động bình thường.

Một cách review hữu ích là đánh dấu **mỗi điểm có thể thất bại** và hỏi: *đến thời điểm này, hệ thống đã thay đổi những gì?*

### 5.1. Lỗi đầu vào: từ chối trước khi gây tác dụng phụ

Ví dụ một service làm ngược thứ tự:

~~~java
public void submit(OrderRequest request) {
    orderRepository.saveDraft(request);
    validate(request);
    paymentGateway.capture(request);
}
~~~

**OrderRequest**, **orderRepository**, **validate** và **paymentGateway** là các thành phần minh họa. Nếu **validate** ném ngoại lệ, bước **saveDraft** đã chạy. Kết quả sai hay đúng còn tùy hợp đồng: hệ thống có chủ ý lưu bản nháp invalid không? Nếu yêu cầu là **“dữ liệu sai không được tạo đơn”**, thứ tự trên vi phạm hợp đồng.

Một hướng xem xét:

~~~java
public void submit(OrderRequest request) {
    validate(request);
    Quote quote = pricing.quote(request.lines(), request.vip());
    orderRepository.saveDraft(request, quote);
    paymentGateway.capture(request, quote);
}
~~~

Đoạn thứ hai **chỉ minh họa thứ tự validate và tính trước bước ghi**; các kiểu/đối tượng không được định nghĩa đầy đủ. Nó **chưa giải quyết** tình huống saveDraft thành công rồi capture thất bại. Reviewer không nên đánh dấu “đã bảo đảm tính nguyên tử” chỉ vì hai dòng được đổi chỗ.

### 5.2. Ma trận lỗi tại mỗi ranh giới

| Thời điểm lỗi | Điều đã có thể xảy ra | Reviewer cần hỏi |
| --- | --- | --- |
| Trước validation | Chưa tạo tác dụng phụ | Có báo lỗi rõ, không lộ dữ liệu nhạy cảm? |
| Khi tính toán | Có kết quả trung gian trong bộ nhớ | Có trả kết quả tràn hoặc dữ liệu không hợp lệ? |
| Khi lưu DB | Có thể chưa ghi, hoặc đã ghi một phần tùy transaction | Transaction, rollback và trạng thái sau lỗi ra sao? |
| Sau DB, trước gọi gateway | Đơn nháp đã tồn tại | Có trạng thái cần xử lý tiếp và cleanup? |
| Gateway trả lỗi rõ | Có thể bị từ chối hoặc lỗi vận hành | Có được phép retry; đơn đang ở trạng thái nào? |
| Gateway timeout/mất phản hồi | Bên ngoài **có thể đã xử lý** | Có idempotency, tra cứu trạng thái và đối soát? |
| Gateway thành công, cập nhật DB thất bại | Tiền có thể đã thu nhưng đơn chưa PAID | Có cơ chế phục hồi, đối soát hoặc bù trừ? |
| Gửi event hoặc email thất bại | Đơn có thể đã lưu và thanh toán | Có outbox/retry phù hợp hay được phép bỏ qua? |
| Request bị gọi lại | Các bước trước có thể đã chạy | Có chống tạo đơn/thu tiền/gửi thông báo trùng? |

Không thể giải quyết mọi hàng trong bảng bằng một **try/catch(Exception)**. Những rủi ro này cần thiết kế về **trạng thái, idempotency, transaction boundary và quan sát được**.

### 5.3. Ngoại lệ không tự đảo ngược side effect

~~~java
paymentGateway.capture(paymentId, amountVnd);
orderRepository.markPaid(orderId);
~~~

Nếu lệnh đầu đã thu tiền và lệnh sau thất bại, việc ném một **RuntimeException** chỉ báo lỗi cho caller; nó **không hoàn tác** giao dịch ở hệ thống thanh toán.

Tương tự, transaction của DB chỉ kiểm soát các thao tác nằm trong **cùng phạm vi transaction DB**, không tự biến lời gọi mạng, message broker và DB thành một giao dịch nguyên tử.

Phương án giải quyết tùy nghiệp vụ:

- **Idempotency key** có hợp đồng rõ cho các thao tác có thể retry.
- Trạng thái đơn như **PENDING, PAYMENT_UNKNOWN, PAID, FAILED** được định nghĩa chặt chẽ.
- Tra cứu trạng thái bên ngoài sau timeout thay vì đoán là thất bại.
- **Outbox pattern** hoặc cơ chế lưu ý định gửi sự kiện trong transaction DB khi cần tránh mất thông điệp.
- Hoạt động **đối soát** và bù trừ có kiểm soát cho tác dụng phụ không thể rollback.

Reviewer nên yêu cầu **mô tả đường phục hồi** tương ứng với rủi ro, không chỉ đề nghị thêm một câu lệnh catch.

## 6. Các đường lỗi khác thường bị bỏ quên trong review

### 6.1. Catch quá rộng có thể che mất loại lỗi

~~~java
try {
    return repository.load(orderId);
} catch (Exception ignored) {
    return null;
}
~~~

Đoạn minh họa này gộp nhiều tình huống thành **null**: không tìm thấy đơn, mất kết nối DB, lỗi dữ liệu và lỗi lập trình. Bên gọi không phân biệt được trường hợp “không tồn tại” với “không truy vấn được”.

Khi review, cần đối chiếu hợp đồng:

- **Không tìm thấy** có phải kết quả bình thường và được biểu diễn bằng **Optional.empty()** hoặc một loại kết quả rõ?
- **Hạ tầng thất bại** có cần được báo cho caller để retry/điều tra?
- Có được phép trả dữ liệu cache cũ khi DB lỗi, hay việc đó làm sai tính nhất quán?
- Có đang mất dấu nguyên nhân gốc hoặc che thông tin quan trọng của exception?

Không có một chuẩn “mọi lỗi đều phải ném exception”. Nhưng phải **phân biệt được những trường hợp mà người gọi cần hành xử khác nhau**.

### 6.2. Thứ tự kiểm tra có thể làm đổi hợp đồng lỗi

~~~java
public long calculate(long unitPriceVnd, int quantity) {
    long amountVnd = Math.multiplyExact(unitPriceVnd, quantity);
    if (quantity < 1 || quantity > 100) {
        throw new IllegalArgumentException("Invalid quantity");
    }
    return amountVnd;
}
~~~

Nếu **quantity = 101** và **unitPriceVnd** rất lớn, phép nhân có thể ném **ArithmeticException** **trước** khi hệ thống báo số lượng ngoài miền hợp lệ. Điều đó có thể trái với hợp đồng lỗi của API.

Nếu yêu cầu là kiểm tra miền đầu vào trước mọi phép tính, nên đặt validation trước:

~~~java
public long calculate(long unitPriceVnd, int quantity) {
    if (unitPriceVnd < 0 || quantity < 1 || quantity > 100) {
        throw new IllegalArgumentException("Invalid line");
    }
    return Math.multiplyExact(unitPriceVnd, quantity);
}
~~~

Khi nhiều điều kiện cùng sai, reviewer cần biết **loại lỗi nào được ưu tiên**, hoặc hợp đồng chỉ yêu cầu “từ chối” mà không cam kết thứ tự validation. Đừng làm test giòn bởi thông điệp hoặc thứ tự mà API chưa hề hứa.

### 6.3. Timeout không chứng minh tác vụ chưa hoàn thành

Giả sử một ứng dụng gọi dịch vụ ngoài với timeout 2 giây. Sau 2 giây chưa có phản hồi, người gọi **không thể suy ra chắc chắn**:

- Dịch vụ chưa nhận request.
- Dịch vụ đã nhận nhưng chưa xử lý.
- Dịch vụ đã hoàn tất tác dụng phụ nhưng phản hồi bị mất.

Nếu tự động gửi lại yêu cầu thu tiền mà không có **idempotency** và đối soát, có nguy cơ tạo hành động trùng. Khi review retry, cần xác định **điều kiện nào an toàn để thử lại** và **cách xử lý kết quả chưa xác định**.

### 6.4. Cancellation và interruption là cơ chế hợp tác

Trong Java, **Future.cancel(true)** cố gắng hủy bằng cách yêu cầu interrupt nếu tác vụ đang chạy ở thread có thể ngắt. Nó **không bảo đảm** tác vụ đã dừng hoặc hoàn tác I/O.

Một lỗi dễ gặp:

~~~java
try {
    Thread.sleep(1_000L);
} catch (InterruptedException ignored) {
    // Bỏ qua tín hiệu dừng.
}
~~~

Nếu phương thức không xử lý ngắt theo hợp đồng riêng, một phương án thường phù hợp là **khôi phục cờ interrupt** rồi kết thúc công việc:

~~~java
try {
    Thread.sleep(1_000L);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đoạn này giả định nằm trong một **phương thức void** và có thể dừng an toàn sau ngắt. Với một API khác, có thể cần ném lại **InterruptedException** thay vì bắt nó. Reviewer phải bảo đảm không bỏ dở tài nguyên hoặc trạng thái nghiệp vụ theo cách nguy hiểm.

### 6.5. Tài nguyên có được đóng trên mọi đường đi?

~~~java
InputStream input = Files.newInputStream(path);
String text = new String(
        input.readAllBytes(), StandardCharsets.UTF_8);
input.close();
return text;
~~~

Nếu **readAllBytes()** ném exception, lệnh close có thể không được gọi. Cách thường phù hợp:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    return new String(
            input.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

Đoạn mã giả định có import phù hợp cho **Files**, **InputStream**, **Path** và **StandardCharsets**, cùng khai báo/lan truyền **IOException**. **Try-with-resources** bảo đảm cơ chế đóng được thực hiện khi rời khối theo ngữ nghĩa Java, kể cả đường lỗi; bản thân thao tác đóng cũng có thể thất bại, và lỗi đóng được xử lý theo cơ chế exception/suppressed exception của ngôn ngữ.

Reviewer còn cần kiểm tra **quyền sở hữu**: phương thức có phải đóng connection/stream đó không, hay đối tượng được quản lý bởi transaction manager hoặc một caller khác?

### 6.6. Log phải hữu ích nhưng không làm lộ dữ liệu

Một lỗi cần quan sát, nhưng không nên ghi tùy tiện **mật khẩu, token, thông tin thanh toán hoặc dữ liệu cá nhân**. Reviewer cần cân bằng:

- Có đủ **correlation ID**, loại thao tác, trạng thái và mã lỗi để chẩn đoán?
- Có log trùng cùng exception qua nhiều tầng, tạo nhiễu không?
- Có log dữ liệu không đáng tin làm sai cấu trúc hoặc tạo dòng giả không?
- Có đang hiển thị stack trace hoặc thông tin nội bộ cho người dùng cuối không?
- Có metrics để phân biệt lỗi input, lỗi phụ thuộc và timeout không?

Logging và monitoring giúp phát hiện sự cố, **không biến một luồng lỗi sai thành đúng**.

## 7. Kiểm thử là bằng chứng hỗ trợ review, không thay thế review

Một PR đáng tin nên có test **gắn với lời hứa có thể sai**, thay vì chỉ tăng số lượng ca test. Cần kiểm tra:

1. **Oracle** có đến từ hợp đồng độc lập hay bị sao chép từ implementation?
2. Ca test có bao phủ **đúng ngưỡng**, không chỉ một giá trị lớn hoặc nhỏ?
3. Đầu vào lỗi có **không gây side effect** nếu hợp đồng yêu cầu?
4. Test có phân biệt **lỗi được dự kiến** và **lỗi vận hành**?
5. Có test trạng thái sau lỗi, không chỉ assert ném exception?
6. Có phụ thuộc vào thời gian thực, thứ tự test hoặc shared state khiến test flaky?

### 7.1. Bảng oracle cho QuoteCalculator

| Ca | VIP | Đơn giá VND | Số lượng | Phí mong đợi | Tổng phải trả |
| --- | --- | ---: | ---: | ---: | ---: |
| T1 – VIP dưới ngưỡng | true | 299.999 | 1 | 30.000 | 329.999 |
| T2 – VIP đúng ngưỡng | true | 300.000 | 1 | 0 | 300.000 |
| T3 – VIP trên ngưỡng | true | 300.001 | 1 | 0 | 300.001 |
| T4 – thường dưới ngưỡng | false | 499.999 | 1 | 30.000 | 529.999 |
| T5 – thường đúng ngưỡng | false | 500.000 | 1 | 0 | 500.000 |
| T6 – thường trên ngưỡng | false | 500.001 | 1 | 0 | 500.001 |
| T7 – hàng giá 0 | false | 0 | 1 | 30.000 | 30.000 |

Những con số trong bảng được suy ra từ hợp đồng minh họa. **Không nên tính expected bằng cùng phương thức quote đang kiểm tra**, vì khi đó test có thể xác nhận chính lỗi của implementation.

### 7.2. JUnit 5 kiểm tra ca bình thường và biên

Tệp **QuoteCalculatorTest.java** (cần dependency JUnit Jupiter và JUnit Jupiter Params):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class QuoteCalculatorTest {
    @ParameterizedTest
    @CsvSource({
        "true, 299999, 30000, 329999",
        "true, 300000, 0, 300000",
        "true, 300001, 0, 300001",
        "false, 499999, 30000, 529999",
        "false, 500000, 0, 500000",
        "false, 500001, 0, 500001",
        "false, 0, 30000, 30000"
    })
    void checksShippingThresholds(
            boolean vip,
            long subtotalVnd,
            long expectedShippingVnd,
            long expectedPayableVnd) {
        var lines = List.of(
                new QuoteCalculator.Line(subtotalVnd, 1));

        var quote = QuoteCalculator.quote(lines, vip);

        assertEquals(subtotalVnd, quote.subtotalVnd());
        assertEquals(
                expectedShippingVnd, quote.shippingFeeVnd());
        assertEquals(expectedPayableVnd, quote.payableVnd());
    }
}
~~~

Một ca test có tên rõ, dữ liệu có ý nghĩa và assertion đúng hợp đồng là bằng chứng mạnh hơn một test chỉ kiểm tra **assertNotNull(quote)**.

### 7.3. JUnit 5 kiểm tra lỗi và tràn số

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class QuoteCalculatorInvalidTest {
    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 101, 1_000})
    void rejectsQuantityOutsideContract(int quantity) {
        assertThrows(IllegalArgumentException.class,
                () -> new QuoteCalculator.Line(100L, quantity));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> new QuoteCalculator.Line(-1L, 1));
    }

    @Test
    void rejectsMissingOrEmptyLines() {
        assertThrows(IllegalArgumentException.class,
                () -> QuoteCalculator.quote(null, false));
        assertThrows(IllegalArgumentException.class,
                () -> QuoteCalculator.quote(List.of(), false));
    }

    @Test
    void rejectsNullLineElement() {
        List<QuoteCalculator.Line> lines =
                new java.util.ArrayList<>();
        lines.add(null);

        assertThrows(IllegalArgumentException.class,
                () -> QuoteCalculator.quote(lines, false));
    }

    @Test
    void detectsOverflowInLineAmount() {
        var line = new QuoteCalculator.Line(
                Long.MAX_VALUE, 2);
        assertThrows(ArithmeticException.class,
                () -> QuoteCalculator.quote(
                        List.of(line), false));
    }

    @Test
    void detectsOverflowAcrossLines() {
        var lines = List.of(
                new QuoteCalculator.Line(Long.MAX_VALUE, 1),
                new QuoteCalculator.Line(1L, 1));

        assertThrows(ArithmeticException.class,
                () -> QuoteCalculator.quote(lines, false));
    }
}
~~~

Ca **detectsOverflowInLineAmount** thể hiện rằng giá trị đầu vào hợp lệ riêng lẻ chưa bảo đảm phép nhân biểu diễn được. Ca **detectsOverflowAcrossLines** kiểm tra việc cộng nhiều dòng. Việc dùng phép toán kiểm tra tràn số trong implementation là quyết định dựa trên hợp đồng **không được trả sai âm thầm**.

### 7.4. Những điều test này chưa chứng minh

Mặc dù test giá trị biên và lỗi thành công, vẫn chưa thể khẳng định:

- JSON request được ánh xạ đúng sang **Line** ở mọi trường hợp thiếu/null.
- Người dùng được phép mua hoặc xem giá của mọi sản phẩm.
- Kết quả từ repository luôn là đơn giá đáng tin cậy.
- Hai request đồng thời không ghi đè trạng thái đơn hàng.
- Cổng thanh toán chỉ được gọi đúng một lần khi retry.
- Những tính toán về thuế, giảm giá hoặc tiền tệ khác đã đúng.

**Ranh giới của test phải khớp ranh giới của kết luận.** Test đơn vị cho một hàm thuần không chứng minh toàn bộ workflow.

## 8. Kiểm tra “không được xảy ra” khi có lỗi

Nhiều review chỉ nhìn thấy assertion cho exception hoặc response lỗi. Với service có tác dụng phụ, một phần quan trọng của hợp đồng là **những lời gọi không được thực hiện khi thất bại**.

### 8.1. Tách kiểm tra khỏi nơi lưu

Tệp **CheckoutService.java** dưới đây dùng interface đơn giản để minh họa:

~~~java
import java.util.List;

public final class CheckoutService {
    public interface OrderWriter {
        void savePayable(long payableVnd);
    }

    private final OrderWriter writer;

    public CheckoutService(OrderWriter writer) {
        this.writer = java.util.Objects.requireNonNull(writer);
    }

    public long submit(
            List<QuoteCalculator.Line> lines,
            boolean vip) {
        var quote = QuoteCalculator.quote(lines, vip);
        writer.savePayable(quote.payableVnd());
        return quote.payableVnd();
    }
}
~~~

Ở đây, việc tính toán và validation hoàn tất **trước** thao tác lưu. **OrderWriter** là ranh giới được đơn giản hóa để kiểm tra thứ tự gọi; nó không phải một repository hoàn chỉnh có transaction, định danh đơn hàng và kiểm tra quyền.

### 8.2. Kiểm thử không lưu khi validation thất bại

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void invalidCartDoesNotCallWriter() {
        AtomicInteger saveCalls = new AtomicInteger();
        CheckoutService.OrderWriter writer =
                amount -> saveCalls.incrementAndGet();

        var checkout = new CheckoutService(writer);

        assertThrows(IllegalArgumentException.class,
                () -> checkout.submit(List.of(), false));
        assertEquals(0, saveCalls.get());
    }

    @Test
    void validCartSavesOnceAndReturnsPayable() {
        AtomicInteger saveCalls = new AtomicInteger();
        long[] savedValue = {-1L};

        CheckoutService.OrderWriter writer = amount -> {
            savedValue[0] = amount;
            saveCalls.incrementAndGet();
        };
        var checkout = new CheckoutService(writer);

        long result = checkout.submit(
                List.of(new QuoteCalculator.Line(500_000L, 1)),
                false);

        assertEquals(500_000L, result);
        assertEquals(500_000L, savedValue[0]);
        assertEquals(1, saveCalls.get());
    }

    @Test
    void writerFailureIsNotReportedAsSuccess() {
        CheckoutService.OrderWriter writer = amount -> {
            throw new IllegalStateException("Storage unavailable");
        };
        var checkout = new CheckoutService(writer);

        assertThrows(IllegalStateException.class,
                () -> checkout.submit(
                        List.of(new QuoteCalculator.Line(100L, 1)),
                        false));
    }
}
~~~

Đây là **unit test với fake dependency**, không ghi DB thật. Nó xác minh thứ tự validation trước save và số lần service **gọi** writer trong một số trường hợp.

**Không thể từ một test fake suy ra rằng DB đã commit đúng một bản ghi.** Nếu writer timeout hoặc lỗi sau khi DB thực tế đã ghi, caller vẫn có thể chưa biết kết quả. Những trường hợp đó cần kiểm thử tích hợp và cơ chế idempotency/đối soát ở ranh giới lưu trữ.

## 9. Kiểm tra thay đổi hợp đồng lỗi ở tầng API

Khi service trả hoặc ném lỗi, tầng API có thể cần ánh xạ sang phản hồi cho người gọi. Ví dụ:

| Tình huống | Hợp đồng HTTP minh họa | Điều cần review |
| --- | --- | --- |
| Số lượng 0 | 400 Bad Request | Không tạo đơn; thông báo đủ rõ |
| Người dùng không được phép | 403 Forbidden hoặc lựa chọn phù hợp chính sách | Không lộ dữ liệu của người khác |
| Không tìm thấy tài nguyên | 404 Not Found | Không nhầm với DB lỗi |
| Xung đột trạng thái đơn | 409 Conflict | Chỉ có chuyển trạng thái hợp lệ |
| Lỗi DB ngoài dự kiến | 5xx phù hợp | Không giả báo thành công; có log an toàn |
| Gateway timeout và kết quả chưa rõ | Trạng thái được định nghĩa trong hợp đồng | Không suy diễn thanh toán chưa xảy ra |

Các mã trên là **gợi ý thiết kế theo bối cảnh**, không phải phép ánh xạ bắt buộc cho mọi API. Ví dụ, lựa chọn 403 hay 404 cho tài nguyên nhạy cảm phụ thuộc chính sách tránh tiết lộ sự tồn tại; một luồng bất đồng bộ có thể trả 202 Accepted và yêu cầu client tra cứu tiến độ.

### 9.1. Tránh thay đổi vô tình khi “dọn lỗi”

Nếu phiên bản cũ trả **Optional.empty()** khi không tìm thấy đơn, phiên bản mới chuyển sang ném **IllegalStateException** có thể làm hỏng caller ngay cả khi code mới trông “chặt chẽ”. Reviewer nên hỏi:

- Đây là **bug fix**, thay đổi contract hay refactor?
- Client hiện tại có dùng kiểu lỗi cũ để quyết định retry hoặc hiển thị?
- Có cần versioning hoặc giai đoạn tương thích không?
- Test contract đã được cập nhật từ yêu cầu hay chỉ sửa để khớp code mới?

**Đừng tự động xem thay đổi ngoại lệ là chi tiết cài đặt.** Với nhiều API, loại lỗi, thời điểm lỗi và khả năng retry chính là một phần hợp đồng công khai.

### 9.2. Không biến mọi lỗi thành “success với giá trị mặc định”

~~~java
try {
    return pricingApi.fetchPrice(productId);
} catch (Exception error) {
    return 0L;
}
~~~

Nếu giá **0 VND** là giá bán hợp lệ, việc gộp lỗi fetch vào giá 0 có thể khiến hệ thống cho hàng miễn phí. Cần phân biệt **không có dữ liệu**, **đơn giá 0 hợp lệ** và **không lấy được dữ liệu** theo hợp đồng; có thể dùng result type, exception phân loại hoặc trạng thái lỗi tường minh.

Giá trị fallback có thể đúng trong vài bài toán (ví dụ cache được phép stale), nhưng phải có **chính sách và giới hạn rõ**, không được tùy tiện chọn vì muốn tránh exception.

## 10. Từ phát hiện sang nhận xét code review có thể hành động

Một nhận xét hữu ích không chỉ nói “đoạn này sai” mà cần chỉ ra **hợp đồng liên quan, tình huống tái hiện, tác động và đề xuất kiểm chứng**.

### 10.1. Mẫu nhận xét có căn cứ

Thay vì:

> Dấu so sánh ở đây có vẻ sai. Sửa đi.

Nên viết:

> Theo yêu cầu miễn phí vận chuyển *từ 500.000 VND*, đơn 500.000 VND phải có phí 0. Điều kiện **subtotalVnd > 500_000L** hiện trả phí 30.000 tại đúng ngưỡng. Đề xuất dùng **>=** và thêm test cho **499.999 / 500.000 / 500.001**.

Thay vì:

> Catch exception này không ổn.

Nên viết:

> Đoạn **catch(Exception)** đang trả giá 0 cả khi price service mất kết nối. Vì 0 là giá hợp lệ, bên gọi có thể hiểu nhầm lỗi vận hành thành hàng miễn phí. Hãy phân biệt “không tìm thấy giá” với “không truy vấn được”, và thêm test cho nhánh service timeout.

Thay vì:

> Đây có thể là race condition.

Nên viết:

> **currentOrderId** là field mutable trong service dùng chung cho nhiều request. Hai lời gọi song song có thể ghi đè giá trị trước khi **markPaid** đọc nó, dẫn tới cập nhật nhầm đơn. Nên truyền orderId qua tham số của từng lời gọi hoặc làm rõ phạm vi một request; thêm kiểm thử hai request có ID khác nhau.

Mẫu cấu trúc:

~~~text
Quan sát:
  Điều kiện hoặc thao tác cụ thể nào đang có rủi ro?

Hợp đồng:
  Quy tắc nào phải được giữ?

Tình huống:
  Đầu vào, thời điểm hoặc trạng thái nào làm vấn đề xuất hiện?

Tác động:
  Sai kết quả, lộ dữ liệu, ghi trùng, giữ tài nguyên hay phá tương thích?

Hướng xử lý:
  Sửa mã, làm rõ hợp đồng, thêm test hoặc giảm rủi ro thế nào?
~~~

### 10.2. Phân loại mức độ ưu tiên

Có thể dùng các mức ưu tiên nội bộ để giúp tác giả biết việc nào cần xử lý trước khi merge:

| Mức xem xét | Ví dụ | Cách trao đổi |
| --- | --- | --- |
| **Chặn vì sai hợp đồng hoặc an toàn** | Thu tiền hai lần, thiếu phân quyền, sai số tại ngưỡng được xác nhận | Nêu tình huống và yêu cầu xử lý/biện pháp được phê duyệt |
| **Chặn hoặc cần quyết định thiết kế** | Không có phương án khi gateway timeout, migration có thể mất dữ liệu | Làm rõ hợp đồng, owner và chiến lược trước khi triển khai |
| **Cải tiến chất lượng nên làm** | Tên mơ hồ, logic lặp đang làm test khó | Nêu lợi ích và phạm vi phù hợp |
| **Gợi ý không chặn** | Cách xuống dòng, tên biến khác chút so với gu cá nhân | Để formatter/quy ước chung xử lý khi có thể |

Đây là **phân loại gợi ý**, không phải một chuẩn P0/P1/P2 áp dụng cho mọi tổ chức. Mức độ nghiêm trọng phải xét **khả năng xuất hiện, hậu quả, phạm vi triển khai và biện pháp giảm thiểu**, không chỉ nhãn từ công cụ tĩnh.

### 10.3. Khi chưa có đủ thông tin

Review nên phân biệt **phát hiện chắc chắn** với **giả thuyết cần xác minh**:

- “Mã dùng **>** trong khi acceptance criteria nêu **>=**” là khác biệt có thể kiểm chứng.
- “Phương thức này có thể được gọi đồng thời; instance có được dùng chung không?” là câu hỏi về cấu hình runtime.
- “Đường ghi này có chạy trong cùng một DB transaction không?” là câu hỏi cần xem contract repository/transaction manager.

Nếu chưa biết, nên hỏi một câu **cụ thể có thể trả lời bằng chứng**, thay vì khẳng định một lỗi chưa được chứng minh. Đồng thời không nên im lặng trước rủi ro cao chỉ vì diff không chứa toàn bộ cấu hình.

## 11. Quy trình review theo hợp đồng, biên và luồng lỗi

### Bước 1 — Xác nhận mục đích thay đổi

Đọc mô tả PR, yêu cầu và tiêu chí chấp nhận. Tách rõ **refactor giữ hành vi**, **sửa bug** và **đổi yêu cầu nghiệp vụ**. Nếu mục tiêu chưa rõ, reviewer khó đánh giá một sai khác có phải chủ ý hay không.

### Bước 2 — Lập bản đồ hợp đồng

Ghi ngắn:

- Input nào được chấp nhận hoặc từ chối?
- Output, exception, side effect nào được cam kết?
- Bất biến nào phải giữ trước và sau lời gọi?
- Bên gọi hiện tại, hệ thống ngoài và dữ liệu lịch sử phụ thuộc gì?

Một bảng ngắn thường đủ:

~~~text
API: createOrder(...)

Trước:
  - Yêu cầu đã được xác thực và phân quyền.

Thành công:
  - Lưu một đơn với tổng tiền theo chính sách.
  - Trả orderId và trạng thái đã được công bố.

Thất bại:
  - Dữ liệu invalid không tạo đơn.
  - Lỗi thanh toán có trạng thái có thể truy vấn.
  - Retry không được tạo thanh toán trùng.
~~~

Đây chỉ là **mẫu hợp đồng minh họa**. Trong thực tế, nhiều workflow có thể chủ ý lưu đơn nháp khi thanh toán thất bại. Quan trọng là hợp đồng phải **nêu rõ trạng thái đó**, không mặc định mọi lỗi sẽ rollback tất cả hệ thống.

### Bước 3 — Đi qua các lớp dữ liệu và giá trị biên

Sử dụng phân hoạch tương đương, ngưỡng và các điểm chuyển trạng thái. Viết một số đầu vào cụ thể thay vì bình luận chung “thêm test edge case”.

Ví dụ với số lượng **1..100** và ngưỡng **500.000**, bộ trọng tâm có thể gồm **0/1/100/101** và **499.999/500.000/500.001**.

### Bước 4 — Lần theo từng đường lỗi

Với mỗi lệnh có thể ném ngoại lệ hoặc timeout:

1. Trước khi lỗi, có ghi DB, gửi network request hoặc cập nhật state nào chưa?
2. Khi lỗi, chương trình sẽ trả gì cho caller?
3. Các thay đổi trước đó được giữ, rollback hay phục hồi thế nào?
4. Có tài nguyên nào bị để mở?
5. Một retry có thể thực hiện tác dụng phụ trùng không?

Nếu có nhiều hệ thống tham gia, nên vẽ trạng thái trước–sau thay vì cố suy từ một khối **try/catch**.

### Bước 5 — Kiểm tra bằng chứng đi kèm

Đọc test code và kết quả CI theo phạm vi:

- Có assertion kiểm tra kết quả **đúng nghiệp vụ**, không chỉ “không ném lỗi”?
- Có test cho **biên và lỗi** đã nhận diện?
- Có test **không gây side effect** ở nhánh invalid?
- Có integration/contract test nơi hành vi phụ thuộc DB, gateway hoặc serialization?
- Có vùng source/module/config nào bị bỏ qua bởi pipeline?

Không có ca test nào chứng minh mọi lịch chạy đồng thời đều đúng. Với các bất biến concurrency quan trọng, cần kết hợp thiết kế đồng bộ/transaction đúng, kiểm thử có điều phối và review.

### Bước 6 — Ghi nhận xét theo rủi ro và xác nhận giải pháp

Ưu tiên nhận xét **có tình huống tái hiện và hướng kiểm chứng**. Nếu tác giả đưa ra bằng chứng hợp lệ hoặc làm rõ yêu cầu, reviewer cần cập nhật kết luận. Mục tiêu là giảm lỗi và xây dựng sự hiểu biết chung, không phải tối đa hóa số bình luận.

## 12. Review cũng cần nhìn vào mức độ kiểm chứng

### 12.1. Coverage và static analysis có ích nhưng có giới hạn

**Code coverage** phản ánh phần mã được chạy theo thước đo như line hoặc branch coverage; nó không đo trực tiếp oracle có đúng hay không. Một test chỉ gọi phương thức nhưng không kiểm tra kết quả có thể tăng coverage mà không phát hiện lỗi tại ngưỡng.

**Static analysis** có thể phát hiện các mẫu lỗi như dereference null, bỏ đóng tài nguyên, nối dữ liệu vào câu SQL hoặc cấu trúc dễ gây hiểu nhầm. Nhưng công cụ không tự biết chính sách miễn phí vận chuyển phải dùng **>=** nếu không được cung cấp quy tắc tương ứng.

**Mutation testing** có thể thử đổi dấu so sánh ở implementation để kiểm tra liệu test có phân biệt được hành vi. Nếu đổi **>=** thành **>** nhưng test vẫn xanh, cần xem lại việc kiểm tra **đúng ngưỡng**. Mutation testing cũng có giới hạn, không thay thế review và không phải mọi biến đổi đều tương ứng với lỗi thực.

### 12.2. Test flaky làm giảm giá trị bằng chứng

Kiểm thử dùng **Thread.sleep** để đoán thời điểm task hoàn thành có thể xanh/đỏ tùy tốc độ máy. Test dùng thời gian hệ thống có thể bị ảnh hưởng bởi múi giờ và thời gian chạy. Test dùng DB chung có thể phụ thuộc thứ tự thực thi.

Khi review test:

- Truyền **Clock** hoặc thời điểm cố định nếu quy tắc phụ thuộc thời gian.
- Với concurrency, dùng **CountDownLatch/CyclicBarrier** hoặc hạ tầng điều phối phù hợp thay vì thời gian chờ mơ hồ.
- Không chia sẻ dữ liệu test mutable mà không dọn trạng thái.
- Không gọi dịch vụ ngoài không ổn định cho unit test cần tái lập.

Một test chạy lại rồi xanh không chứng minh lỗi đã biến mất. Nên điều tra nguyên nhân mất ổn định.

### 12.3. Test phải phân biệt “đã gọi” và “đã thành công”

Fake ghi nhận **writer.save(...) được gọi một lần** là bằng chứng về **tương tác của service với dependency**, không phải bằng chứng bản ghi đã commit đúng một lần trong DB thật. Fake gateway ghi nhận capture được gọi không chứng minh tiền đã được thu hoặc không thu trùng.

Khi đánh giá test, hỏi: **hành vi này được quan sát ở tầng nào?** Nếu test ở tầng service nhưng kết luận nói về tính nguyên tử của DB và gateway, kết luận đang vượt quá phạm vi bằng chứng.

## 13. Tình huống thực hành code review

Một đội phát triển nhận yêu cầu:

- Người dùng gửi mã đơn, số tiền và **idempotency key**.
- Phí xử lý bằng **0 VND** với số tiền từ **500.000 VND** trở lên; nhỏ hơn ngưỡng trả **20.000 VND**.
- Đầu vào **amountVnd** phải là số không âm.
- Cùng idempotency key và cùng nội dung yêu cầu không được gây thanh toán trùng.
- Khi bên ngoài trả timeout, hệ thống không được tự khẳng định thanh toán chắc chắn thất bại.

Tác giả gửi đoạn code minh họa sau:

~~~java
public PaymentResult pay(
        String orderId, String idempotencyKey, long amountVnd) {
    long fee = amountVnd > 500_000L ? 0L : 20_000L;
    long total = amountVnd + fee;

    repository.markProcessing(orderId);
    try {
        gateway.capture(orderId, total);
        repository.markPaid(orderId);
        return PaymentResult.success(total);
    } catch (Exception error) {
        repository.markFailed(orderId);
        return PaymentResult.failed();
    }
}
~~~

Đây là đoạn Java **minh họa ở mức review**, không phải chương trình có đủ khai báo **PaymentResult**, **repository** và **gateway**. Reviewer chưa biết chính xác API của gateway, phạm vi transaction hoặc schema dữ liệu; cần đặt câu hỏi phù hợp.

### 13.1. Những điểm phải nhận diện

1. **Hợp đồng đầu vào:** Có kiểm tra amount âm, orderId/idempotencyKey thiếu hoặc không hợp lệ không?
2. **Biên:** Với **500.000 VND**, điều kiện **>** có tính đúng mức phí 0 không?
3. **Tràn số:** amount + fee có thể tràn long không, và phần tổng có được xác minh trước khi đổi state không?
4. **Thứ tự:** **markProcessing** được gọi trước mọi validation; khi input sai, trạng thái có bị đổi ngoài ý muốn không?
5. **Timeout:** Bắt mọi exception rồi đánh dấu FAILED có phản ánh đúng khả năng gateway đã thu tiền không?
6. **Retry:** idempotencyKey được truyền vào phương thức nhưng không được sử dụng; liệu gateway hoặc repository có ràng buộc tương ứng không?
7. **Cập nhật một phần:** Nếu capture thành công nhưng **markPaid** thất bại, catch lại **markFailed**; đây có phải trạng thái sai không?
8. **Lỗi thứ cấp:** Nếu **markFailed** cũng thất bại, exception nào tới caller và trạng thái DB thực sự thế nào?
9. **Bảo mật:** Ai được phép thanh toán cho orderId này, và số tiền đến từ client hay dữ liệu server đã xác minh?
10. **Bằng chứng:** Test nào cần bổ sung cho biên, invalid, timeout, capture thành công/DB thất bại và replay?

### 13.2. Một hướng cải tiến cần làm rõ hợp đồng

Trước khi sửa:

- Xác định **nguồn số tiền đáng tin cậy**, quyền truy cập và tính hợp lệ của đơn hàng.
- Tính phí bằng một chính sách riêng có test biên và phép toán kiểm tra tràn.
- Định nghĩa trạng thái cho **kết quả thanh toán chưa xác định** và cách tra cứu/đối soát.
- Định nghĩa idempotency key áp dụng cho **order + nội dung yêu cầu** ra sao, cách lưu kết quả và xử lý replay khác payload.
- Đảm bảo dữ liệu và trạng thái DB được chuyển với transaction, constraint hoặc cơ chế phù hợp.
- Tách đường gửi yêu cầu thanh toán khỏi logic phục hồi nếu có thể, làm rõ retry nào an toàn.

Một phác thảo trạng thái để thảo luận:

~~~text
VALIDATED
    |
    v
PAYMENT_REQUESTED
    |
    +---- Gateway xác nhận thành công ---> PAID
    |
    +---- Gateway từ chối rõ -----------> DECLINED
    |
    +---- Timeout / mất phản hồi -------> PAYMENT_UNKNOWN
                                              |
                                              v
                                      Tra cứu / đối soát
                                              |
                                   +----------+---------+
                                   v                    v
                                  PAID              DECLINED
~~~

Sơ đồ trên chỉ là **một mô hình minh họa**. Trong hệ thống thật còn có trạng thái retry, hủy, hoàn tiền và các cơ chế xử lý sự cố khác. Không thể lấy sơ đồ làm bảo đảm tính đúng khi chưa có hợp đồng và cách lưu trạng thái tương ứng.

### 13.3. Gợi ý bảng test cần yêu cầu trước merge

| Nhóm | Tình huống | Điều cần xác minh |
| --- | --- | --- |
| Bình thường | amount 200.000, không có lỗi | Phí 20.000 theo chính sách; một kết quả hợp lệ |
| Biên | amount 499.999 / 500.000 / 500.001 | Phí 20.000 / 0 / 0 |
| Lỗi input | amount -1, thiếu idempotency key | Từ chối trước mọi side effect |
| Biên kiểu số | amount = Long.MAX_VALUE | Phí 0, tổng vẫn là Long.MAX_VALUE; không tràn số |
| Lỗi gateway rõ | Thanh toán bị từ chối | Trạng thái phản ánh bị từ chối, không nhầm với timeout |
| Timeout | Gateway chưa xác nhận kết quả | Không đánh dấu FAILED như chắc chắn chưa thu tiền |
| Lỗi DB sau capture | Capture thành công, markPaid thất bại | Có đường phục hồi/đối soát, không báo sai sự thật |
| Retry cùng payload | Lặp cùng idempotency key | Không thu tiền hai lần theo hợp đồng |
| Retry khác payload | Cùng key, nội dung khác | Bị từ chối hoặc xử lý theo chính sách được công bố |
| Đồng thời | Hai request cùng key chạy cùng lúc | Không tạo hai tác dụng phụ dù race |
| Quyền | Người dùng không sở hữu đơn | Không được gọi gateway hoặc lộ dữ liệu |

**Gợi ý đối chiếu:** Biểu thức **>** vi phạm chính sách ngưỡng. Catch **Exception** rồi đánh dấu FAILED là nguy hiểm khi kết quả gateway chưa rõ hoặc đã thành công. **Idempotency key** không được dùng là dấu hiệu hợp đồng retry chưa được thực thi trong đoạn minh họa. Cần sửa theo **rủi ro và trạng thái nghiệp vụ**, không chỉ thay một catch bằng nhiều catch mà vẫn không có cơ chế đối soát.

## 14. Những hiểu nhầm thường gặp

**“Code đọc dễ hiểu và CI xanh là review xong.”** Mã vẫn có thể sai ngưỡng, thiếu validation hoặc làm tác dụng phụ trùng. Cần đối chiếu hợp đồng.

**“Nhiều ca happy path là đủ.”** Phần lớn lỗi quan trọng nằm ở ranh giới, input sai và các bước thất bại, không nhất thiết ở dữ liệu điển hình.

**“Chỉ cần assertThrows là đã kiểm tra đường lỗi.”** Cần xem trạng thái và side effect sau khi exception xuất hiện.

**“Có transaction DB thì mọi thứ đều rollback.”** Transaction DB không tự rollback lời gọi gateway, event hoặc email bên ngoài.

**“Timeout nghĩa là thao tác thất bại.”** Timeout thường chỉ cho biết người gọi không có kết quả trong hạn; tác vụ bên ngoài có thể đã xử lý.

**“Retry luôn làm hệ thống đáng tin cậy hơn.”** Retry không có idempotency, điều kiện dừng và chiến lược xử lý kết quả chưa rõ có thể làm hỏng dữ liệu.

**“Đầu vào lạ phải bị từ chối.”** Unicode, dấu nháy hoặc chuỗi dài có thể hợp lệ tùy trường; kiểm tra theo hợp đồng, không theo cảm giác.

**“Coverage 100% chứng minh không có bug.”** Coverage không xác nhận oracle, miền đầu vào hoặc hệ thống ngoài.

**“Thấy một rủi ro thì phải yêu cầu viết lại toàn module.”** Review hiệu quả phân biệt lỗi cần chặn với công việc cải thiện có thể xử lý riêng, và đề xuất sửa đổi có phạm vi kiểm soát.

## 15. Ghi nhớ

- **Review theo hợp đồng:** xác định tiền điều kiện, hậu điều kiện, bất biến, lỗi, tác dụng phụ và tương thích trước khi kết luận mã đúng.
- **Review trường hợp biên:** dùng lớp tương đương và giá trị ngay dưới/bằng/trên ngưỡng; xét cả dữ liệu thiếu, tràn số, thời gian, trạng thái và tổ hợp rủi ro.
- **Review luồng lỗi:** lần theo những gì đã xảy ra trước điểm lỗi, trạng thái còn lại, khả năng phục hồi, tài nguyên, retry và idempotency.
- **Review bằng chứng:** test oracle phải độc lập, kiểm tra cả điều **không được xảy ra**, và kết luận không được vượt phạm vi kiểm thử.
- **Review như cộng tác kỹ thuật:** nêu một tình huống cụ thể, hợp đồng bị ảnh hưởng, hậu quả và cách kiểm chứng. Không biến sở thích cá nhân thành yêu cầu chặn khi không có rủi ro tương ứng.
