# Lặp tri thức ở nhiều nơi cần thay đổi cùng nhau

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện **mùi mã lặp tri thức**: cùng một quy tắc, giả định hoặc quyết định được biểu diễn ở nhiều nơi và phải sửa đồng bộ khi ý nghĩa của nó thay đổi.
2. Phân biệt **lặp tri thức** với **trùng mã tình cờ**; hiểu vì sao hai đoạn code giống nhau chưa chắc cần gộp, còn hai đoạn khác cú pháp vẫn có thể lặp cùng một tri thức.
3. Phân tích hậu quả của việc sửa thiếu một nơi, bao gồm **lệch hành vi**, **lỗi ở trường hợp biên**, **change amplification** và **shotgun surgery**.
4. Thiết kế một **nguồn sở hữu quy tắc** rõ ràng trong Java, dùng kiểu dữ liệu, chính sách và kiểm thử để giảm rủi ro không nhất quán.
5. Chọn chiến lược xử lý lặp tri thức giữa controller, job nền, báo cáo, nhiều service và client, mà không phá vỡ yêu cầu bảo mật, lịch sử dữ liệu hay ranh giới triển khai.
6. Tránh tạo abstraction quá sớm, dùng chung các khái niệm khác nhau chỉ vì chúng hiện có cùng con số hoặc công thức.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã nguồn được đánh giá qua khả năng **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Mùi mã**, “lặp tri thức ở nhiều nơi cần thay đổi cùng nhau” là dấu hiệu cho thấy một quyết định quan trọng không có nơi sở hữu rõ ràng. Khi quy tắc đổi, người phát triển phải tìm và cập nhật nhiều bản sao; nếu bỏ sót một bản sao, hệ thống có thể đưa ra những kết quả mâu thuẫn.

Đây không phải vấn đề “cứ hai dòng giống nhau là sai”. **Điều đáng chú ý là có một tri thức hoặc lý do thay đổi chung nhưng đang được duy trì riêng lẻ ở nhiều nơi.**

## 1. Thế nào là lặp tri thức?

Hãy tưởng tượng hệ thống bán hàng có quy tắc:

> Với đơn hàng còn hiệu lực, nếu tổng tiền hàng từ **500.000 VND trở lên**, phí vận chuyển bằng **0 VND**; nếu thấp hơn, phí là **30.000 VND**. Đơn đã hủy không phát sinh phí vận chuyển.

Một quy tắc, nhưng có thể xuất hiện ở nhiều thành phần:

- **Màn hình xem trước đơn hàng** tính phí để báo cho khách.
- **Checkout service** tính phí khi xác nhận đơn.
- **Job nhập đơn** tạo đơn từ nguồn ngoài.
- **Tác vụ tạo hóa đơn** đọc và trình bày phí vận chuyển.
- **Báo cáo doanh thu** tổng hợp phí đã thu.

Nếu mỗi thành phần **tự viết lại quy tắc** thì khi ngưỡng thay từ 500.000 thành 700.000 VND, có thể phải sửa nhiều nơi. Nếu chỉ checkout được cập nhật, màn hình xem trước vẫn báo miễn phí ở ngưỡng cũ. Ngay cả trước khi đổi chính sách, một nơi có thể dùng **>**, nơi khác dùng **>=**, gây sai lệch ở đúng 500.000 VND.

Hai biểu hiện quan trọng là:

1. **Một quyết định nghiệp vụ tồn tại ở nhiều bản sao**: ngưỡng, công thức, phạm vi áp dụng và trường hợp biên.
2. **Các bản sao phải đổi đồng thời khi quyết định ấy đổi**: nếu không, đầu ra hoặc hành vi mâu thuẫn.

Tri thức bị lặp có thể là **số**, **công thức**, **tập điều kiện**, **ý nghĩa trạng thái**, **cách chuyển đổi dữ liệu**, **quy tắc lỗi**, **hợp đồng giao thức** hoặc **giả định về quyền và nguồn dữ liệu**.

### Ví dụ về những dạng lặp tri thức

| Tri thức chung | Các bản sao có thể xuất hiện | Lỗi dễ xảy ra khi thay đổi |
| --- | --- | --- |
| Ngưỡng miễn phí vận chuyển | Controller, service, import job | Giá trị báo trước khác giá trị tính thật |
| Công thức chiết khấu và làm tròn | Checkout, hóa đơn, job đối soát | Chênh lệch tiền giữa các kênh |
| Trạng thái đơn được phép hủy | API, ứng dụng di động, background worker | Kênh này cho hủy, kênh khác từ chối |
| Định nghĩa “đơn thanh toán thành công” | Event consumer, báo cáo, dashboard | Tổng hợp sai trạng thái hoặc đếm trùng |
| Schema một sự kiện | Producer, consumer, script import | Deserialize lỗi hoặc hiểu sai ý nghĩa trường |
| Cách diễn giải mã sản phẩm | Web, job nhập kho, adapter POS | Cùng SKU bị hiểu thành hai sản phẩm |
| Mã lỗi và tình huống dùng mã lỗi | API, SDK, tài liệu | Client xử lý sai hoặc hiển thị thông báo không đúng |
| Công thức phân trang/giới hạn dữ liệu | API, export, reporting | Thứ tự và số lượng kết quả không nhất quán |

Những trường hợp này đều đáng điều tra, nhưng **không tự động dẫn tới cùng một cách refactor**. Quy tắc nghiệp vụ có thể đưa vào domain policy; schema giao tiếp có thể quản lý bằng contract có phiên bản; dữ liệu báo cáo lịch sử có thể cần dùng giá trị đã chốt thay vì tính lại.

## 2. “Don't Repeat Yourself” nói về tri thức, không chỉ dòng mã

Nguyên tắc **DRY (Don't Repeat Yourself)** thường bị diễn giải thành “mọi đoạn code giống nhau phải gộp”. Cách hiểu đó quá hẹp.

Điều cần giảm là **nhiều nơi độc lập cùng biểu diễn một tri thức có một lý do thay đổi chung**.

Hãy so sánh:

~~~java
// Hàm A: ngưỡng miễn phí vận chuyển.
boolean freeShipping =
        subtotalVnd.compareTo(new BigDecimal("500000")) >= 0;

// Hàm B: điều kiện thưởng thành viên.
boolean receivesLoyaltyBonus =
        loyaltySpendingVnd.compareTo(new BigDecimal("500000")) >= 0;
~~~

Hai đoạn giống nhau về cấu trúc và cùng con số **500000**, nhưng có thể là **hai quy tắc độc lập**:
- Ngưỡng phí vận chuyển thuộc nhóm logistics.
- Ngưỡng thưởng thuộc nhóm loyalty.

Nếu đặt cả hai vào một hằng **GLOBAL_THRESHOLD_VND**, một thay đổi ở chính sách phí có nguy cơ làm thay đổi chính sách thưởng. Việc gộp này làm **tăng coupling**, dù giảm số chữ số được viết.

Ngược lại, hai đoạn có thể trông rất khác nhưng vẫn lặp một quy tắc:

~~~java
// Một nơi dùng BigDecimal.compareTo.
boolean eligibleAtCheckout =
        subtotalVnd.compareTo(new BigDecimal("500000")) >= 0;

// Một nơi khác dùng số nguyên long.
boolean eligibleInImportJob = subtotalInVnd >= 500_000L;
~~~

Đây có thể là hai cách biểu diễn **cùng một quyết định miễn phí vận chuyển**. Một công cụ chỉ dò dòng code giống nhau có thể không nhận ra sự lặp tri thức này.

### Câu hỏi trọng tâm: “Chúng có đổi vì cùng một lý do không?”

Khi thấy hai đoạn giống hoặc liên quan, hãy hỏi:

1. **Cùng chủ sở hữu nghiệp vụ không?** Ví dụ cùng do nhóm vận chuyển quy định.
2. **Cùng ý nghĩa không?** Cả hai đều quyết định phí giao hàng của đơn còn hiệu lực hay một bên quyết định điều khác?
3. **Khi quy tắc đổi, cả hai có bắt buộc đổi không?** Hay có thể phát triển độc lập?
4. **Trường hợp biên có phải giống nhau không?** Có cùng ngưỡng, cách làm tròn, điều kiện loại trừ?
5. **Dữ liệu đầu vào có cùng hợp đồng không?** Có cùng đơn vị, thời điểm hiệu lực, trạng thái?
6. **Nếu sửa một nơi nhưng không sửa nơi còn lại, hành vi có sai không?**

**Nếu có cùng lý do thay đổi và phải đồng bộ**, đó là dấu hiệu mạnh của lặp tri thức. **Nếu chỉ giống cú pháp nhưng sở hữu và lý do thay đổi khác nhau**, gộp lại có thể là lựa chọn kém.

## 3. Dấu hiệu nhận biết trong một codebase

Mùi mã không nhất thiết có hình dạng “copy-paste” rõ ràng. Những dấu hiệu thường gặp:

- Cùng một con số nghiệp vụ xuất hiện nhiều lần dưới tên khác nhau.
- Khi thay chính sách, pull request phải sửa controller, service, job và báo cáo.
- Một bug chỉ xuất hiện ở một kênh vì các kênh cùng nghiệp vụ lại dùng điều kiện khác.
- Các hàm **calculate...**, **validate...**, **isEligible...** có logic tương đương nhưng được viết riêng.
- Một trường JSON đổi tên phải sửa tay đồng thời nhiều mapper, tài liệu và client.
- Unit test chỉ kiểm tra từng bản sao riêng, không có test chứng minh hai đường sử dụng cùng hợp đồng.
- Người phát triển phải hỏi “giá trị nào mới là giá trị chuẩn?”.
- Một thay đổi được yêu cầu “nhớ sửa thêm ba chỗ khác” nhưng không có ràng buộc tự động.
- Cùng một trạng thái được mã hóa thành nhiều chuỗi, boolean hoặc số nguyên không thống nhất.
- Những phần độc lập giả định chung một cách tính nhưng không ai sở hữu định nghĩa chính thức.

### Change amplification và shotgun surgery

**Change amplification** mô tả tình trạng **một thay đổi yêu cầu nhỏ làm phát sinh sửa mã ở nhiều nơi**. Nếu thay ngưỡng vận chuyển buộc chỉnh mười hàm, phạm vi sửa có thể quá rộng so với phạm vi tri thức.

**Shotgun surgery** là mùi mã liên quan: khi muốn điều chỉnh một trách nhiệm, ta phải “bắn” thay đổi vào nhiều lớp/file khác nhau. Không phải shotgun surgery nào cũng do lặp tri thức, nhưng lặp quy tắc là một nguyên nhân phổ biến.

Những hệ quả thường gặp:
- **Thiếu nhất quán:** nơi này dùng quy tắc mới, nơi kia vẫn dùng quy tắc cũ.
- **Rủi ro hồi quy:** sửa một bản sao gây sai trường hợp biên mà bản sao khác đã xử lý đúng.
- **Chi phí review:** người kiểm tra phải đối chiếu nhiều nơi để bảo đảm chúng thực sự tương đương.
- **Khó điều tra:** cùng đầu vào nhưng kết quả khác nhau tùy đường xử lý.
- **Tốc độ thay đổi giảm:** mỗi yêu cầu mới phải phân tích lan truyền trên phạm vi rộng.

Tuy nhiên, **nhiều file cùng được sửa chưa chắc là lỗi thiết kế**. Một thay đổi API có chủ đích có thể buộc cập nhật producer, consumer, migration, tài liệu và test. Mục tiêu là giảm **lặp quyết định phải bảo trì độc lập**, không phải ép mọi thay đổi vào một file.

## 4. Ví dụ Java trước khi cải thiện: cùng quy tắc, hai kết quả

Giả sử hệ thống có hai đường tính phí:

~~~java
import java.math.BigDecimal;

// Mã minh họa có lặp tri thức.
final class ShippingPreview {
    BigDecimal fee(BigDecimal subtotalVnd) {
        // LỖI: chỉ miễn phí khi lớn hơn ngưỡng.
        return subtotalVnd.compareTo(new BigDecimal("500000")) > 0
                ? BigDecimal.ZERO
                : new BigDecimal("30000");
    }
}

final class ShippingConfirmation {
    BigDecimal fee(BigDecimal subtotalVnd) {
        // Đúng theo hợp đồng: bằng ngưỡng cũng được miễn phí.
        return subtotalVnd.compareTo(new BigDecimal("500000")) >= 0
                ? BigDecimal.ZERO
                : new BigDecimal("30000");
    }
}
~~~

Ở giá trị **500000**, một bên báo phí **30000** trong khi bên kia tính phí **0**.

Đó không chỉ là lỗi của dấu **>**; **nguyên nhân cấu trúc** là hai thành phần tự giữ bản sao của cùng một quy tắc. Dù sửa **>** thành **>=** hôm nay, khi chính sách thay đổi lần sau, nguy cơ lệch vẫn còn.

### Vì sao chỉ thêm comment không đủ?

Ta có thể thêm comment “đừng quên cập nhật preview khi đổi policy”. Nhưng comment:
- Không được biên dịch hoặc thực thi.
- Có thể lỗi thời khi mã thay đổi.
- Không ngăn một worker mới áp dụng sai quy tắc.
- Đẩy trách nhiệm đồng bộ sang trí nhớ của con người.

Comment về **lý do nghiệp vụ** vẫn hữu ích, nhưng không thay thế cơ chế **một nơi sở hữu quy tắc** và **kiểm thử hợp đồng**.

## 5. Xác định nơi sở hữu quy tắc trước khi refactor

Trước khi tạo một lớp tiện ích chung, hãy xác định **chủ sở hữu tri thức**.

Với ví dụ vận chuyển:
- **ShippingFeePolicy** chịu trách nhiệm quyết định phí vận chuyển theo dữ liệu hợp lệ.
- **OrderPreviewService** dùng policy để hiển thị mức phí dự kiến.
- **CheckoutService** dùng policy để tính và **chốt** mức phí khi xác nhận đơn.
- **InvoiceService** đọc **mức phí đã chốt trên đơn** để trình bày lịch sử, không mặc định tính lại bằng chính sách đang có hiệu lực hôm nay.
- **ReportingService** tổng hợp phí đã thực thu theo hợp đồng kế toán, không tự áp lại công thức dự báo.

Điểm tinh tế: **không phải mọi nơi từng có cùng công thức đều phải gọi công thức ấy ở mọi thời điểm**. Có nơi cần **quyết định chính sách tại thời điểm tạo đơn**; có nơi cần **hiển thị kết quả đã được lưu**. Nếu áp “DRY tuyệt đối” bằng cách cho hóa đơn cũ luôn gọi policy mới, người dùng có thể thấy hóa đơn lịch sử thay đổi sau khi công ty đổi ngưỡng.

### Sơ đồ trách nhiệm

~~~mermaid
flowchart TD
    A[OrderPreviewService] --> P[ShippingFeePolicy]
    B[CheckoutService] --> P
    P --> D[ShippingFeeDecision: fee + policyVersion]
    B --> E[Lưu phí đã chốt và phiên bản]
    E --> F[InvoiceService]
    E --> G[ReportingService]
    F --> H[Hóa đơn lịch sử]
    G --> I[Báo cáo]
~~~

Một **nguồn sở hữu quy tắc** không có nghĩa mọi biểu diễn dữ liệu đều nằm trong cùng một class. Các thành phần có trách nhiệm khác nhau vẫn tồn tại; chúng **không tự viết lại cùng chính sách khi ra quyết định**.

## 6. Ví dụ Java 17: đưa tri thức vào policy có hợp đồng rõ

Ta dùng một ví dụ độc lập, với quy tắc giả định:

1. Tiền là VND, được truyền dưới dạng **BigDecimal** không âm và không có phần lẻ theo quy ước của bài.
2. Đơn ở trạng thái **CANCELLED** không phát sinh phí vận chuyển.
3. Đơn **ACTIVE** có **subtotalVnd từ 500.000 trở lên** được miễn phí.
4. Đơn ACTIVE dưới ngưỡng có phí **30.000 VND**.
5. Kết quả mang **policyVersion** để biết phiên bản chính sách đã dùng.

Đây là chính sách minh họa, không phải một chuẩn áp dụng cho mọi hệ thống. Trong sản phẩm thật, cần làm rõ phí, thuế, hoàn tiền, thời điểm hiệu lực và khả năng có nhiều loại tiền.

### 6.1. Kiểu dữ liệu biểu diễn hợp đồng

~~~java
import java.math.BigDecimal;
import java.util.Objects;

enum OrderState {
    ACTIVE,
    CANCELLED
}

record ShippingContext(
        BigDecimal subtotalVnd,
        OrderState state) {

    ShippingContext {
        Objects.requireNonNull(subtotalVnd, "subtotalVnd");
        Objects.requireNonNull(state, "state");
        if (subtotalVnd.signum() < 0
                || subtotalVnd.stripTrailingZeros().scale() > 0) {
            throw new IllegalArgumentException(
                    "subtotalVnd must be a non-negative whole VND amount");
        }
    }
}

record ShippingFeeDecision(
        BigDecimal feeVnd,
        String policyVersion) {

    ShippingFeeDecision {
        Objects.requireNonNull(feeVnd, "feeVnd");
        Objects.requireNonNull(policyVersion, "policyVersion");
        if (feeVnd.signum() < 0 || policyVersion.isBlank()) {
            throw new IllegalArgumentException("invalid fee decision");
        }
    }
}

final class ShippingFeePolicy {
    static final String VERSION = "SHIPPING_FEE_V1";

    private static final BigDecimal FREE_SHIPPING_THRESHOLD_VND =
            new BigDecimal("500000");
    private static final BigDecimal STANDARD_FEE_VND =
            new BigDecimal("30000");

    ShippingFeeDecision decide(ShippingContext context) {
        Objects.requireNonNull(context, "context");

        BigDecimal feeVnd;
        if (context.state() == OrderState.CANCELLED) {
            feeVnd = BigDecimal.ZERO;
        } else if (context.subtotalVnd()
                .compareTo(FREE_SHIPPING_THRESHOLD_VND) >= 0) {
            feeVnd = BigDecimal.ZERO;
        } else {
            feeVnd = STANDARD_FEE_VND;
        }

        return new ShippingFeeDecision(feeVnd, VERSION);
    }
}
~~~

**Điểm cải thiện:**

- Ngưỡng, phí chuẩn, điều kiện trạng thái và trường hợp biên nằm trong **một nơi sở hữu quy tắc**.
- Tên **subtotalVnd**, **FREE_SHIPPING_THRESHOLD_VND** và **STANDARD_FEE_VND** diễn đạt **ý nghĩa và đơn vị**, tránh nhầm với các con số khác có cùng giá trị.
- **ShippingContext** chặn dữ liệu âm hoặc không đúng quy ước nguyên VND, thay vì để từng caller kiểm tra theo cách riêng.
- **ShippingFeeDecision** phân biệt **kết quả tính phí** với **đầu vào**; mang phiên bản để hỗ trợ giải thích về sau.
- Hàm **decide(...)** là phép tính thuần: không tự đọc bảng giá, gọi HTTP hoặc ghi database. Điều này giúp viết test tập trung.

Mã ở trên dùng các kiểu package-private để dễ đặt trong cùng một ví dụ. Đối với codebase thật, hãy tổ chức package và mức visibility theo ranh giới module. **Record** yêu cầu Java 16 trở lên và được hỗ trợ trong Java 17.

### 6.2. Hai luồng sử dụng cùng một policy

~~~java
import java.math.BigDecimal;
import java.util.Objects;

final class OrderPreviewService {
    private final ShippingFeePolicy feePolicy;

    OrderPreviewService(ShippingFeePolicy feePolicy) {
        this.feePolicy = Objects.requireNonNull(feePolicy);
    }

    ShippingFeeDecision preview(BigDecimal subtotalVnd) {
        return feePolicy.decide(
                new ShippingContext(subtotalVnd, OrderState.ACTIVE));
    }
}

final class CheckoutService {
    private final ShippingFeePolicy feePolicy;

    CheckoutService(ShippingFeePolicy feePolicy) {
        this.feePolicy = Objects.requireNonNull(feePolicy);
    }

    ShippingFeeDecision confirmShipping(BigDecimal subtotalVnd) {
        // Trong sản phẩm thật, kết quả này phải được chốt trên đơn
        // trong transaction/hợp đồng lưu trữ phù hợp.
        return feePolicy.decide(
                new ShippingContext(subtotalVnd, OrderState.ACTIVE));
    }
}
~~~

Cả hai thành phần phụ thuộc vào **cùng một nguồn quyết định**. Nếu ngưỡng thay đổi, logic ở **ShippingFeePolicy** thay đổi; bản thân hai luồng không giữ các bản sao riêng.

Ví dụ không có nghĩa chỉ cần truyền cùng một instance là đủ trong mọi hệ thống. Nếu preview và checkout chạy ở **hai phiên bản phần mềm khác nhau** hoặc khi chính sách được cập nhật giữa hai thời điểm, kết quả vẫn có thể khác. Cần xác định hợp đồng: preview có thể là ước tính, còn checkout phải dựa trên chính sách có hiệu lực khi xác nhận và công bố thay đổi khi cần.

### 6.3. Hóa đơn lịch sử cần một loại tri thức khác

Khi đơn đã được xác nhận, mức phí phải được lưu cùng dữ liệu giao dịch theo hợp đồng. Sau đó, hóa đơn nên đọc **phí đã chốt**, không tự áp policy mới.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record ConfirmedShippingCharge(
        String orderId,
        BigDecimal chargedFeeVnd,
        String policyVersion) {

    ConfirmedShippingCharge {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(chargedFeeVnd, "chargedFeeVnd");
        Objects.requireNonNull(policyVersion, "policyVersion");
        if (orderId.isBlank()
                || policyVersion.isBlank()
                || chargedFeeVnd.signum() < 0) {
            throw new IllegalArgumentException("invalid charge");
        }
    }
}

final class InvoiceFormatter {
    String shippingLine(ConfirmedShippingCharge charge) {
        Objects.requireNonNull(charge, "charge");
        return "Phí vận chuyển: "
                + charge.chargedFeeVnd().toPlainString()
                + " VND";
    }
}
~~~

**InvoiceFormatter** không lặp quy tắc miễn phí vận chuyển: nó chỉ trình bày một **giá trị lịch sử đã chốt**. Nếu ngưỡng thay đổi ngày mai, hóa đơn ngày hôm qua vẫn giữ giá trị ban đầu.

Đây là điểm cần phân biệt khi phát hiện mùi mã: **tái sử dụng quyết định tại thời điểm tính** khác **tái tính kết quả đã chốt tại thời điểm đọc**. Việc gom mọi nơi vào một policy không được phá hợp đồng lịch sử.

## 7. Kiểm thử chính sách chung và các đường sử dụng

Đưa quy tắc về một nơi giúp test tập trung vào các trường hợp biên và bảo vệ hợp đồng chính sách.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void chargesStandardFeeBelowThreshold() {
        var result = policy.decide(new ShippingContext(
                new BigDecimal("499999"), OrderState.ACTIVE));

        assertEquals(new BigDecimal("30000"), result.feeVnd());
        assertEquals("SHIPPING_FEE_V1", result.policyVersion());
    }

    @Test
    void freeShippingAtExactThreshold() {
        var result = policy.decide(new ShippingContext(
                new BigDecimal("500000"), OrderState.ACTIVE));

        assertEquals(BigDecimal.ZERO, result.feeVnd());
    }

    @Test
    void freeShippingAboveThreshold() {
        var result = policy.decide(new ShippingContext(
                new BigDecimal("500001"), OrderState.ACTIVE));

        assertEquals(BigDecimal.ZERO, result.feeVnd());
    }

    @Test
    void cancelledOrderHasNoShippingCharge() {
        var result = policy.decide(new ShippingContext(
                new BigDecimal("100000"), OrderState.CANCELLED));

        assertEquals(BigDecimal.ZERO, result.feeVnd());
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> new ShippingContext(
                        new BigDecimal("-1"), OrderState.ACTIVE));
    }
}
~~~

Các giá trị mong đợi **30000** và **0** trong test xuất phát từ **hợp đồng nghiệp vụ được viết độc lập**, không phải từ việc gọi lại chính policy để tạo expected value. Nếu viết:

~~~java
// Test ít giá trị: expected và actual cùng lấy từ logic đang kiểm tra.
BigDecimal expected = policy.decide(context).feeVnd();
BigDecimal actual = policy.decide(context).feeVnd();
assertEquals(expected, actual);
~~~

thì test gần như chỉ so sánh một phép tính với chính nó. Để phát hiện sai điều kiện **>** so với **>=**, expected value phải được lấy từ quy tắc đã xác nhận hoặc bảng ví dụ độc lập.

### Test bảo vệ đường gọi, không chỉ policy

Ngoài test chính sách, cần test rằng các entry point quan trọng **đang sử dụng đúng policy** thay vì vô tình có logic mới riêng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class ShippingEntryPointsTest {
    @Test
    void previewAndCheckoutApplyTheSameCurrentPolicy() {
        var feePolicy = new ShippingFeePolicy();
        var preview = new OrderPreviewService(feePolicy);
        var checkout = new CheckoutService(feePolicy);
        BigDecimal threshold = new BigDecimal("500000");

        assertEquals(
                BigDecimal.ZERO,
                preview.preview(threshold).feeVnd());

        assertEquals(
                BigDecimal.ZERO,
                checkout.confirmShipping(threshold).feeVnd());
    }

    @Test
    void invoiceDisplaysPersistedChargeInsteadOfRecalculating() {
        var historical = new ConfirmedShippingCharge(
                "O-001", new BigDecimal("30000"), "SHIPPING_FEE_V0");

        String line = new InvoiceFormatter().shippingLine(historical);

        assertEquals("Phí vận chuyển: 30000 VND", line);
    }
}
~~~

Test đầu là **ví dụ unit test cho các luồng nhỏ**. Với ứng dụng nhiều module hoặc nhiều service, còn cần **integration/contract test** để xác minh cấu hình dependency injection, phiên bản policy, serialization và dữ liệu lưu trữ. Test hóa đơn dùng một phiên bản cũ giả định (**SHIPPING_FEE_V0**) để minh họa yêu cầu: **không tự dùng chính sách hiện tại tính lại lịch sử**.

**Lưu ý:** Trong ví dụ, CheckoutService chưa thực sự lưu phí, quản lý giao dịch hoặc xác nhận thanh toán. Một test trong bộ nhớ không chứng minh các bước đó hoạt động đúng ở cơ sở dữ liệu hoặc khi nhiều request đồng thời.

## 8. Khi nào trùng code nhưng không phải lặp cùng tri thức?

Một người viết hai hàm giống nhau có thể đang giải quyết **hai quy tắc độc lập**. Khi ấy gộp chúng quá sớm làm tạo một abstraction sai.

### 8.1. Trùng phép tính nhưng khác ý nghĩa

~~~java
BigDecimal shippingDiscount =
        shippingSubtotal.multiply(new BigDecimal("0.10"));

BigDecimal loyaltyBonus =
        loyaltySpending.multiply(new BigDecimal("0.10"));
~~~

Cùng nhân **0.10**, nhưng hai tỷ lệ có thể thay đổi độc lập. Không nên tạo:

~~~java
// Ví dụ thiết kế có nguy cơ sai: gộp hai chính sách vào một hằng.
static final BigDecimal UNIVERSAL_RATE = new BigDecimal("0.10");
~~~

Có thể chia sẻ một tiện ích tính phần trăm **nếu thực sự cần** và nếu tiện ích đó chỉ mô tả **phép toán ổn định**, không mang giả định nghiệp vụ của một chính sách.

Ví dụ:

~~~java
static BigDecimal percentageOf(
        BigDecimal base, BigDecimal rate) {
    return base.multiply(rate);
}
~~~

Ngay cả hàm tiện ích trên cũng không tự giải quyết **đơn vị tiền**, **làm tròn** hoặc **phạm vi giá trị tỷ lệ**. Nếu phép toán chỉ có một dòng và không chứa tri thức đáng kể, việc thêm helper có thể không đem lại giá trị.

### 8.2. Hai validation giống nhau nhưng bảo vệ hai ranh giới

Một form web có thể kiểm tra số lượng **từ 1 đến 100** để phản hồi ngay; backend cũng kiểm tra để bảo vệ hệ thống khỏi request không hợp lệ.

Có hai nhu cầu riêng:
- **Client validation:** trải nghiệm nhập liệu.
- **Server validation:** ranh giới tin cậy và bất biến nghiệp vụ.

Không nên xóa validation phía server vì “frontend đã kiểm tra”, cũng không nhất thiết xóa validation phía frontend để tránh trùng. Điều cần giảm là **hai định nghĩa không thống nhất của cùng một hợp đồng**. Có thể phát hành schema/contract rõ ràng, sinh validation thích hợp hoặc dùng test contract để phát hiện lệch.

Ở đây **nhiều nơi kiểm tra có thể là chủ đích**, trong khi **định nghĩa giới hạn và ý nghĩa** vẫn nên có chủ sở hữu xác định.

### 8.3. Dữ liệu được sao chép có chủ đích

Các trường hợp sau có thể là quyết định thiết kế hợp lý:
- **Cache** dữ liệu để giảm độ trễ.
- **Read model/denormalization** để tối ưu truy vấn.
- **Snapshot** giá và thuế đã chốt trên đơn hàng.
- **Event** mang dữ liệu cần thiết cho consumer.
- **Bản sao database** để phục vụ đọc.

Chúng là sự lặp về **giá trị dữ liệu**, không nhất thiết là lặp **tri thức cần sửa ở nhiều nơi**. Nhưng phải có hợp đồng về **nguồn sự thật, thời điểm cập nhật, tính nhất quán, khả năng đối soát và lịch sử**. Nếu không, việc sao chép dữ liệu cũng có thể gây lệch kết quả.

### 8.4. Hai test cùng mô tả một quy tắc

Một unit test xác nhận công thức phí ở lớp policy, còn integration test xác nhận API trả cùng phí qua HTTP. Chúng có cùng kỳ vọng nghiệp vụ nhưng kiểm tra **hai rủi ro khác nhau**: logic trong bộ nhớ và kết nối framework/hợp đồng giao tiếp.

Không nên gộp mọi test chỉ để số assertion không lặp. **Trùng tình huống ở các tầng test có thể là có chủ đích**, miễn là mỗi test có mục tiêu rõ.

## 9. Cách phân biệt “cùng lý do thay đổi” và “giống nhau tình cờ”

Một cách thực dụng là lập **bản đồ tri thức**:

| Câu hỏi | Quy tắc A | Quy tắc B |
| --- | --- | --- |
| Tên nghiệp vụ | Miễn phí vận chuyển | Thưởng khách hàng thân thiết |
| Người sở hữu quyết định | Chính sách vận chuyển | Chính sách loyalty |
| Dữ liệu đầu vào | Subtotal của đơn còn hiệu lực | Doanh số tích lũy theo khách |
| Giá trị hiện tại | Ngưỡng 500.000 | Ngưỡng 500.000 |
| Trường hợp biên | Bằng ngưỡng được miễn phí | Tùy chính sách loyalty |
| Lý do sửa | Thay chính sách giao hàng | Thay quyền lợi thành viên |
| Có buộc đổi đồng thời không? | Không | Không |

Dù cả hai ngưỡng giống nhau hôm nay, chúng **không nên chia sẻ một hằng số chính sách**. Có thể một ngày chính sách vận chuyển đổi thành 700.000 trong khi loyalty giữ 500.000.

Ngược lại, nếu **Preview Service** và **Checkout Service** đều tính cùng **phí vận chuyển tại thời điểm xác nhận đơn**, cả hai có cùng người sở hữu, cùng ngưỡng và cùng trường hợp biên. Chúng là ứng viên tốt để dùng một nguồn quyết định.

### Sự lặp có thể bị che bởi tên khác

Ví dụ:
- **MIN_CART_VALUE** trong checkout.
- **FREE_DELIVERY_LIMIT** ở frontend.
- **SHIPPING_PROMOTION_THRESHOLD** trong job.
- **500000** ghi trực tiếp ở truy vấn SQL báo cáo.

Tên khác nhau không nhất thiết biểu thị bốn khái niệm khác nhau. Khi phát hiện, đừng chỉ “find all 500000”; hãy truy ra **quy tắc, thời điểm và người sở hữu** ở từng nơi.

## 10. Nguyên tắc chọn abstraction để loại bỏ lặp tri thức

Một abstraction tốt phải làm rõ **thứ được chia sẻ** và **điều được phép thay đổi**.

### 10.1. Chia sẻ quy tắc, không chia sẻ mọi thao tác

Nếu hai nơi đều tính cùng chính sách giao hàng, đưa **quy tắc** về một policy rõ tên. Không cần bắt hai luồng có UI, logging, transaction và response HTTP giống nhau.

Ví dụ:
- **ShippingFeePolicy** đưa ra **ShippingFeeDecision**.
- **Preview Service** có trách nhiệm hiển thị mức phí ước tính.
- **Checkout Service** có trách nhiệm chốt quyết định và ghi nhận.
- **Invoice Service** có trách nhiệm trình bày dữ liệu lịch sử.

Các lớp này **có thể khác nhau về orchestration** mà không bị coi là “lặp tri thức”, vì chúng có lý do thay đổi riêng.

### 10.2. Đặt abstraction ở đúng miền

Một lớp tên **CommonUtils**, **RuleHelper** hoặc **GlobalConstants** có thể nhanh chóng gom các thứ không liên quan. Khi nhiều module cùng phụ thuộc một “túi tiện ích”, một thay đổi nhỏ có thể ảnh hưởng xa.

Tên **ShippingFeePolicy**, **OrderStateTransitions** hoặc **DiscountRoundingPolicy** cho biết rõ chủ sở hữu và hợp đồng. Một nhóm các policy vẫn có thể chung package theo miền, nhưng không nên biến nó thành “kho chứa mọi hằng số”.

### 10.3. Chọn interface khi có nhu cầu thay thế thực

Một **interface ShippingFeePolicy** có ích khi thực tế có nhiều chính sách theo khu vực, quốc gia, loại khách hoặc giai đoạn hiệu lực và người gọi cần thay thế chúng theo một hợp đồng.

Nếu hiện chỉ có một quy tắc và không có biến thể nào, một lớp cụ thể như ví dụ có thể đủ. Tạo sẵn **RuleEngine<T, U>**, factory, registry và nhiều adapter chỉ để thay một điều kiện có thể làm hệ thống **phức tạp hơn phần lặp ban đầu**.

### 10.4. Cân nhắc thời điểm tách abstraction

**AHA (Avoid Hasty Abstractions)** nhắc rằng khi chưa hiểu rõ hai đoạn có cùng lý do thay đổi, đôi khi nên **chấp nhận sự giống nhau tạm thời** thay vì gộp sớm thành một mô hình sai.

Có thể theo dõi hai đoạn qua một vài thay đổi thực:
- Chúng có liên tục được chỉnh cùng nhau không?
- Các trường hợp biên có hội tụ không?
- Có người sở hữu chung không?
- Nếu được gộp, người gọi có dễ hiểu hơn không?

Không có “quy tắc ba lần lặp” luôn đúng. Một bản sao của quy tắc tính tiền quan trọng giữa hai đường thanh toán có thể cần xử lý ngay; ba đoạn giống phép cộng vô hại nhưng khác ý nghĩa vẫn không nên gộp.

## 11. Khác biệt giữa chia sẻ mã và chia sẻ tri thức giữa nhiều service

Trong một monolith, các caller có thể gọi cùng một class policy. Nhưng khi preview, checkout và reporting nằm ở những service triển khai độc lập, bài toán phức tạp hơn.

### Phương án A: chia sẻ thư viện có phiên bản

Một module chung chứa policy và được các service phụ thuộc vào.

**Lợi ích:**
- Logic được duy trì ở một nơi nguồn.
- Có thể chạy unit test chính sách chung.
- Mã tính toán không cần request mạng ở mỗi lần dùng.

**Đánh đổi:**
- Các service vẫn có thể chạy **phiên bản thư viện khác nhau**.
- Cần kế hoạch phát hành, tương thích và nâng version.
- Có nguy cơ kéo quá nhiều dependency chung khiến các service coupling vào nhau.
- Logic có thể cần dữ liệu động hoặc cấu hình ngoài thư viện, không thể giải quyết bằng chia sẻ code.

### Phương án B: một dịch vụ có thẩm quyền quyết định

Một service chuyên trách nhận dữ liệu hợp lệ và trả quyết định phí.

**Lợi ích:**
- Có nơi sở hữu quy tắc vận hành và phiên bản đang có hiệu lực.
- Các caller không cần tự thực hiện công thức.
- Có thể quản lý quyền, cấu hình, audit và versioning tập trung.

**Đánh đổi:**
- Thêm network latency, timeout, lỗi phụ thuộc và hạn mức tải.
- Nếu service không sẵn sàng, nhiều luồng có thể bị ảnh hưởng.
- Cần xác định cache, retry, idempotency và hợp đồng phản hồi.
- Phải đảm bảo quyết định tương ứng với dữ liệu và **thời điểm hiệu lực**.

### Phương án C: hợp đồng/schema chung và triển khai riêng có kiểm chứng

Với những kiểm tra ở **client** và **server**, không nhất thiết mọi nơi đều chạy cùng Java code. Có thể duy trì:
- Định nghĩa schema và các ràng buộc được công bố.
- Ví dụ hợp đồng và **contract test** cho consumer/provider.
- Mã được sinh từ schema ở những phần phù hợp.
- Tài liệu phiên bản và chính sách tương thích.

Hạn chế: sinh code không tự chứng minh **quy tắc nghiệp vụ động** như số dư thực, quyền truy cập hay khả năng giữ chỗ. Contract test cũng không tự thay thế integration test các phụ thuộc thực.

### Chọn giải pháp theo bản chất tri thức

| Loại tri thức | Hướng sở hữu phổ biến | Điểm cần chú ý |
| --- | --- | --- |
| Công thức thuần, ít phụ thuộc ngoài | Domain module hoặc thư viện có version | Phát hành version và giữ tương thích |
| Quy tắc có cấu hình động hoặc dữ liệu tập trung | Service có thẩm quyền | Độ sẵn sàng, latency, snapshot quyết định |
| API/schema giao tiếp | Contract/schema có version, codegen và test | Producer/consumer không cùng chu kỳ triển khai |
| Kiểm tra giá trị ở giao diện | Client validation + server validation bảo vệ ranh giới | Đồng bộ định nghĩa, không bỏ server check |
| Giá trị giao dịch lịch sử | Snapshot được chốt khi ghi | Không tính lại bằng policy mới |
| Báo cáo tổng hợp | Định nghĩa metric có chủ sở hữu và phiên bản | Cửa sổ thời gian, trạng thái, nguồn và đối soát |

Không có phương án “đưa tất cả sang common module” luôn đúng. **Nguồn sở hữu tri thức** phải rõ, nhưng hình thức phân phối có thể tùy kiến trúc.

## 12. Quy tắc có phiên bản: khi chính sách thay đổi theo thời gian

Giả sử ngưỡng miễn phí vận chuyển thay từ 500.000 lên 700.000 đồng vào ngày 01/12.

Có hai câu hỏi khác nhau:

1. Đơn được tạo **sau thời điểm hiệu lực** dùng ngưỡng nào?
2. Hóa đơn của đơn đã xác nhận **trước thời điểm hiệu lực** hiển thị phí nào?

Nếu hệ thống chỉ sửa một hằng số trong thư viện mà không xét thời điểm, việc xem lại một đơn cũ có thể cho kết quả khác.

Một chính sách có phiên bản hoặc ngày hiệu lực có thể giúp:
- Chọn quy tắc tại thời điểm ra quyết định.
- Lưu quyết định đã chốt vào đơn.
- Tái hiện hoặc đối soát kết quả lịch sử nếu dữ liệu nguồn còn đủ.
- Phân biệt hành vi khác nhau **do chính sách đổi** với hành vi khác nhau **do code bị lệch**.

**Lưu ý:** Một tên version như **SHIPPING_FEE_V1** là metadata, không tự bảo đảm tính đúng. Nếu nội dung chính sách đổi mà vẫn giữ cùng version, việc truy nguyên vẫn khó khăn. Khi version có vai trò pháp lý, kế toán hoặc kiểm toán, cần chính sách quản lý vòng đời và dữ liệu đáng tin cậy.

### Đừng sửa lịch sử bằng cách đồng bộ mọi bản sao theo chính sách mới

Một số bản sao của số tiền hoặc ngưỡng là **sự thật tại thời điểm quá khứ**. Chúng có thể được giữ nguyên có chủ đích:
- Đơn hàng lưu phí đã chốt.
- Invoice lưu số tiền đã phát hành.
- Event ghi lại điều đã xảy ra và phiên bản quy tắc.
- Báo cáo đã công bố dùng snapshot có thời điểm xác định.

Những dữ liệu ấy cần **khả năng truy nguyên và đối soát**, không phải bị cập nhật để “giống cấu hình hiện tại”.

## 13. Lặp tri thức trong validation và bảo mật

Các quy tắc như **quantity từ 1 đến 100**, **SKU không rỗng** hoặc **mã đơn có định dạng cụ thể** có thể được khai báo ở DTO, domain model, database constraint và client.

Có nên xóa bớt để tránh lặp không?

**Không đơn giản như vậy.** Một số tầng phải bảo vệ những mối nguy khác nhau:

| Tầng | Mục tiêu | Có thể có biểu diễn lặp lại không? |
| --- | --- | --- |
| Client form | Giúp người dùng sửa đầu vào ngay | Có, nhưng không phải nguồn tin cậy cuối |
| API validation | Từ chối request sai schema/miền | Có, cần giữ hợp đồng rõ |
| Domain constructor | Ngăn tạo trạng thái nghiệp vụ không hợp lệ từ mọi đường vào | Có, vì job/consumer có thể bỏ qua controller |
| Database constraint | Bảo vệ dữ liệu khi nhiều tiến trình và đường ghi cùng truy cập | Có, do rủi ro lưu trữ/đồng thời |
| Contract/schema | Công bố yêu cầu cho các bên tích hợp | Có, nên là nguồn mô tả được quản lý có version |

Ở đây, “DRY” không có nghĩa chỉ giữ kiểm tra ở frontend và bỏ tất cả nơi khác. **Bảo vệ ở nhiều ranh giới là chủ đích**. Điều cần ngăn là những nơi đó **mâu thuẫn về hợp đồng** hoặc dùng các giá trị ngầm khó bảo trì.

Ví dụ, nếu API cho phép quantity 1–100 nhưng database từ chối lớn hơn 50, cần xác định ràng buộc đúng theo nghiệp vụ rồi điều chỉnh mô hình, validation và migration. Mục tiêu là **thống nhất tri thức**, không phải xóa biện pháp phòng vệ độc lập.

### Không dùng chung chính sách quá rộng

Một lỗi khác là tạo **ValidationUtils.isSafeString(...)** rồi dùng cho SKU, tên người, ghi chú và mật khẩu. Những trường này có miền giá trị khác nhau. Dùng chung một “bộ lọc an toàn” có thể từ chối dữ liệu hợp lệ hoặc bỏ sót lỗ hổng tại điểm sử dụng.

Đặc biệt, kiểm tra dữ liệu đầu vào **không thay thế**:
- PreparedStatement cho SQL.
- Mã hóa đầu ra theo ngữ cảnh HTML.
- Kiểm tra quyền theo **người gọi + hành động + tài nguyên**.
- Chính sách truy cập URL, đường dẫn hoặc hệ thống ngoài.

Một abstraction đúng phải bảo vệ **cùng một hợp đồng**, không phải chỉ nhận cùng kiểu String.

## 14. Lặp tri thức trong báo cáo và truy vấn dữ liệu

Lỗi khó phát hiện thường không nằm ở các phương thức Java giống nhau mà ở **định nghĩa chỉ số** được viết nhiều lần.

Giả sử nhóm kinh doanh định nghĩa:

> Doanh thu ròng theo ngày = tổng số tiền của các giao dịch đã hoàn tất trong ngày, trừ khoản hoàn tiền được ghi nhận trong ngày, theo múi giờ báo cáo.

Nhưng hệ thống có:
- SQL trong dashboard tính theo **created_at**.
- Job nền tính theo **paid_at**.
- API tổng hợp bỏ qua hoàn tiền.
- Báo cáo CSV dùng múi giờ UTC, còn giao diện dùng Asia/Ho_Chi_Minh.

Các đoạn SQL có thể khác nhau hoàn toàn về cú pháp nhưng vẫn đang **cố diễn đạt cùng một tri thức**. Không có định nghĩa được sở hữu và kiểm thử, thay quy tắc sẽ làm các chỉ số lệch.

### Nên xác định những điều gì?

- **Tên và ý nghĩa chỉ số**: “doanh thu ròng” bao gồm những khoản nào.
- **Trạng thái hợp lệ**: PAID, COMPLETED, REFUNDED có được tính thế nào.
- **Trục thời gian**: event time hay processing time; múi giờ và ranh giới ngày.
- **Công thức**: xử lý giảm giá, thuế, vận chuyển, hoàn tiền và làm tròn.
- **Nguồn dữ liệu**: bảng gốc, dữ liệu sao chép hay snapshot nào.
- **Phiên bản định nghĩa**: khi quy tắc đổi, báo cáo cũ so với mới ra sao.
- **Bộ test đối soát**: cùng bộ tình huống nghiệp vụ cho ra cùng con số ở các đường triển khai hợp lệ.

Một hướng là xây dựng **semantic layer** hoặc mô hình dữ liệu báo cáo được quản lý tập trung. Nhưng chưa chắc cần một nền tảng lớn; với hệ thống nhỏ, một định nghĩa SQL có phiên bản và bộ test đối soát có thể đủ.

**Lưu ý:** Một số báo cáo có mục tiêu khác nhau có thể cần công thức khác thật, ví dụ *doanh thu kế toán* và *tổng đơn đã tạo*. Đừng gộp chỉ vì cả hai đều có cột tên **revenue**.

## 15. Phát hiện lặp tri thức bằng công cụ: khả năng và giới hạn

Công cụ phân tích tĩnh, tìm kiếm mã và lịch sử thay đổi có thể hỗ trợ phát hiện dấu hiệu lặp, nhưng không thay thế hiểu biết nghiệp vụ.

### 15.1. Duplicate code detection

Các công cụ có thể báo:
- **Type-1 clone:** đoạn code gần như giống hệt, khác khoảng trắng hoặc comment.
- **Type-2 clone:** cấu trúc giống nhau nhưng đổi tên biến, literal hoặc kiểu tương đương tùy công cụ.
- **Type-3 clone:** các đoạn tương tự có thêm/bớt hoặc sửa một số câu lệnh.
- **Type-4 semantic clone:** code có thể thực hiện hành vi tương đương nhưng cấu trúc khác nhiều; việc phát hiện tự động khó hơn.

Đây là cách phân loại thường gặp, **không phải bảo đảm rằng mọi công cụ đều hỗ trợ cả bốn loại**. Không có công cụ quét giống cú pháp nào tự chứng minh hai quy tắc có cùng chủ sở hữu và lý do thay đổi.

### 15.2. Tìm các literal và tên có ý nghĩa nghiệp vụ

Tìm kiếm **500000**, **FREE_SHIPPING**, **isEligible**, **discount**, **rounding** có thể gợi ý nơi quy tắc xuất hiện.

Nhưng tìm kiếm literal có cả:
- Con số của chính sách khác tình cờ bằng nhau.
- Giá trị trong test fixture.
- Giá trị đã chốt trên dữ liệu lịch sử.
- Ngưỡng không liên quan đến vận chuyển.
- Dữ liệu ví dụ trong tài liệu.

Sau tìm kiếm cần **phân loại theo ý nghĩa**. Không nên thay mọi literal giống nhau bằng cùng một hằng.

### 15.3. Phân tích lịch sử thay đổi đồng thời

Nếu hai file thường được sửa trong cùng những commit cho một chính sách, đó là dấu hiệu cần điều tra về **co-change**. Tuy nhiên, file cùng sửa không chứng minh chúng chứa cùng tri thức: một tính năng có thể tự nhiên yêu cầu sửa API, UI, test và tài liệu.

Dùng lịch sử để đặt câu hỏi:
- Vì sao hai file luôn được sửa cùng nhau?
- Có cùng người sở hữu quyết định?
- Có nơi nào thường bị bỏ sót?
- Một nguồn quy tắc chung có làm giảm phạm vi sửa mà vẫn giữ ranh giới đúng không?

### 15.4. Các giới hạn của con số “duplicated lines”

Tỷ lệ dòng lặp là một **tín hiệu cấu trúc**, không phải thước đo đầy đủ của chất lượng:
- Mã generated có thể lặp nhiều mà không nên sửa tay.
- Mã test có thể lặp fixture có chủ đích cho khả năng đọc.
- Hai đoạn giống nhau có thể thuộc chính sách độc lập.
- Một quy tắc lặp ở nhiều service/ngôn ngữ có thể không bị công cụ cục bộ nhận ra.
- Những lỗi nguy hiểm có thể xuất hiện từ hai công thức chỉ khác một dấu so sánh.

Vì vậy, khi review mùi mã, **hãy điều tra “tri thức trùng” chứ không chỉ tối ưu chỉ số duplicated lines**.

## 16. Quy trình refactor an toàn khi nghi ngờ lặp tri thức

Một quy trình từng bước giúp tránh gộp quá sớm hoặc làm sai hành vi đang chạy.

### Bước 1 — Ghi lại quyết định nghiệp vụ độc lập với code

Viết bằng lời hoặc bảng quyết định:
- Đầu vào hợp lệ là gì?
- Giá trị và trường hợp biên nào được chấp nhận?
- Những ngoại lệ nghiệp vụ nào tồn tại?
- Quy tắc có hiệu lực từ lúc nào?
- Ai có quyền thay đổi quy tắc?

Ví dụ: “Miễn phí nếu subtotal **>= 500000 VND** đối với đơn ACTIVE; đơn CANCELLED không phát sinh phí.”

### Bước 2 — Tìm mọi nơi đang biểu diễn cùng quyết định

Tìm trong controller, service, worker, report, SQL, cấu hình và client liên quan. Không tự đọc/sửa mọi thứ vô giới hạn trong một thay đổi nhỏ; đây là bước phân tích nguyên tắc cho codebase, không phải yêu cầu sửa tất cả.

Tạo bảng:

| Vị trí | Quy tắc đang dùng | Có cùng hợp đồng không? |
| --- | --- | --- |
| Preview | Ngưỡng 500.000, dùng **>** | Có, nhưng sai trường hợp bằng ngưỡng |
| Checkout | Ngưỡng 500.000, dùng **>=** | Có |
| Invoice lịch sử | Hiển thị phí đã lưu | Không phải nơi ra quyết định mới |
| Loyalty service | Ngưỡng thưởng 500.000 | Không, khác chính sách |

### Bước 3 — Phân loại: bản sao nào cần gộp?

Đánh giá **lý do thay đổi**, **ngữ nghĩa**, **thời điểm** và **ranh giới bảo mật/triển khai**. Nếu chỉ giống cú pháp nhưng khác hợp đồng, giữ tách biệt.

### Bước 4 — Chọn nơi sở hữu và hợp đồng mới

Ví dụ, **ShippingFeePolicy** nhận **ShippingContext** và trả **ShippingFeeDecision**. Đặt tên đủ cụ thể và bảo vệ các bất biến quan trọng. Không tạo một lớp trừu tượng chung chứa mọi quy tắc giảm giá, phí vận chuyển, hoàn tiền nếu chúng không cùng lý do thay đổi.

### Bước 5 — Viết test cho hành vi đã xác nhận

Kiểm tra ít nhất:
- Dưới ngưỡng.
- **Bằng** ngưỡng.
- Trên ngưỡng.
- Trạng thái bị loại trừ.
- Dữ liệu lỗi.
- Các đường dùng chính sách có cùng kết quả tại cùng thời điểm.
- Hóa đơn/báo cáo lịch sử không bị tự tính lại nếu hợp đồng yêu cầu.

Nếu hai bản sao cũ đang cho kết quả khác nhau, cần **quyết định hành vi đúng theo nghiệp vụ trước**, không gộp theo một bản sao được chọn tùy ý.

### Bước 6 — Chuyển từng caller sang nguồn chung

Thực hiện qua các thay đổi nhỏ, bảo vệ API công khai và dữ liệu cũ. Không đồng thời đổi toàn bộ hình thức lưu trữ, tên trường và quy tắc nếu không cần. Nếu có nhiều service, lên kế hoạch version, contract và thứ tự triển khai.

### Bước 7 — Xóa logic trùng và kiểm chứng tích hợp

Sau khi caller đã dùng nguồn quyết định mới, loại bỏ phần logic cũ để tránh hai “nguồn sự thật”. Kiểm tra kết quả qua API, worker, database và các đường quan trọng. Nếu còn bản sao trong giai đoạn chuyển đổi, cần xác định **nó được giữ vì lý do gì và khi nào được loại bỏ**.

### Bước 8 — Quan sát sau thay đổi

Nếu chính sách ảnh hưởng tiền hoặc quy trình quan trọng, cần có logging/metrics/đối soát phù hợp:
- Version nào đã ra quyết định?
- Bao nhiêu đơn được miễn phí?
- Có chênh lệch preview và checkout không?
- Có lỗi khi đọc dữ liệu lịch sử không?

Không nên coi refactor thành công chỉ vì số dòng giảm; mục tiêu là **giảm rủi ro lệch tri thức và chi phí thay đổi**.

## 17. Khi nào việc gộp gây hại nhiều hơn lặp?

### 17.1. Wrong abstraction — dùng chung vì hai đoạn nhìn giống nhau

Một hàm chung nhận hàng loạt cờ:

~~~java
// Mẫu dễ trở thành abstraction sai khi các quy tắc khác bản chất.
BigDecimal calculate(
        BigDecimal amount,
        boolean shipping,
        boolean loyalty,
        boolean refundable,
        int mode) {
    // Mỗi cờ mở thêm một tập điều kiện không liên quan.
    throw new UnsupportedOperationException("illustration only");
}
~~~

Nó có thể dùng cho nhiều nơi nhưng làm người gọi khó hiểu chính sách nào đang áp dụng. Nếu luật shipping và loyalty có lý do thay đổi khác nhau, tách chúng vẫn là lựa chọn tốt hơn.

### 17.2. Shared library trở thành điểm coupling tổ chức

Một **common-library** chứa mọi DTO, entity, hằng số, validator và business rule khiến nhiều service phải nâng version cùng nhau. Khi ấy, cố gắng tránh lặp mã có thể làm giảm khả năng triển khai độc lập.

Chia sẻ **hợp đồng đủ nhỏ, ổn định và có version** sẽ khác với chia sẻ toàn bộ mô hình nội bộ. Có lúc **giữ các adapter riêng** ở từng service giúp bảo vệ tính độc lập tốt hơn, miễn là giao tiếp có contract được kiểm chứng.

### 17.3. Mã ngắn hơn nhưng khó hiểu hơn

Gộp hai hàm rõ nghĩa thành một hàm tổng quát với nhiều tham số và callback không tự làm mã dễ bảo trì. Hãy xét:
- Người gọi cần hiểu thêm bao nhiêu cấu hình?
- Một thay đổi ở nhánh A có ảnh hưởng nhánh B không?
- Hợp đồng có còn rõ?
- Test có còn dễ viết và dễ diễn giải?
- Abstraction có tên theo nghiệp vụ hay chỉ theo hình dạng code?

Nếu chi phí nhận thức và coupling tăng, **ít dòng lặp hơn** chưa chắc là tiến bộ.

### 17.4. Không còn biểu diễn đúng khác biệt lịch sử

Một quy tắc áp dụng từ năm ngoái khác quy tắc hiện tại có thể là **hai phiên bản cùng một chính sách**. Đừng xóa phiên bản cũ khi vẫn cần tái hiện hoặc giải thích giao dịch trước đây.

Cần tổ chức versioning, migration hoặc snapshot theo hợp đồng. “Chỉ còn một định nghĩa duy nhất” không có nghĩa “chỉ được tồn tại một phiên bản đang và từng có hiệu lực”.

## 18. Tình huống tổng hợp: giới hạn số lượng đặt hàng không nhất quán

Một ứng dụng thương mại có các thành phần:

1. Web form giới hạn tối đa **100** sản phẩm cho một dòng.
2. REST controller dùng annotation cho tối đa **100**.
3. Application service chỉ kiểm tra số lượng **> 0**.
4. Job nhập đơn từ đối tác cho phép tới **500** vì đối tác gửi đơn sỉ.
5. Database có cột **quantity** kiểu số nguyên và constraint không âm.
6. Một batch tổng hợp áp dụng giới hạn **200** khi chia lô giao hàng.

Nhóm định “thống nhất mọi số về 100” để áp dụng DRY. Nhưng chưa xác định liệu 500 và 200 có phải cùng một quy tắc hay không.

### Phân tích đúng hướng

**Câu hỏi 1 — Giới hạn nào thuộc nghiệp vụ gì?**

- **100** có thể là giới hạn một dòng của kênh bán lẻ.
- **500** có thể là giới hạn khác hợp lệ cho kênh bán sỉ.
- **200** có thể là kích thước một lô xử lý vận chuyển, không phải giới hạn số lượng đơn hàng.
- Constraint database **quantity >= 0** là lớp bảo vệ lưu trữ, nhưng không đủ để xác nhận số lượng theo kênh.

Nếu vậy, ba con số **không cùng một tri thức** và không nên bị thay bằng một **MAX_QUANTITY** toàn cục.

**Câu hỏi 2 — Những nơi nào cần giữ cùng hợp đồng?**

Web form và REST endpoint của **cùng luồng bán lẻ** có thể phải thống nhất giới hạn 100. Nhưng server không nên dựa hoàn toàn vào web validation; application service phải bảo vệ quy tắc bán lẻ ở nơi mọi đường tạo đơn bán lẻ đều đi qua.

Job nhập đơn sỉ có thể dùng chính sách khác nhưng phải khai báo rõ loại kênh, quyền và giới hạn theo hợp đồng.

**Câu hỏi 3 — Thiết kế lại như thế nào?**

Có thể mô hình hóa một khái niệm **OrderingChannel** hoặc một **OrderQuantityPolicy** theo kênh, với test cho từng kênh. Nhưng nếu nghiệp vụ chỉ có hai luồng độc lập và không cần cấu hình động, hai policy cụ thể có tên rõ cũng có thể dễ hiểu hơn một rule engine tổng quát.

**Câu hỏi 4 — Cần test gì?**

- Retail: 1, 100 hợp lệ; 0, 101 không hợp lệ.
- Wholesale: theo giới hạn chính thức, ví dụ 500 nếu hợp đồng xác nhận.
- Batch giao hàng: giới hạn 200 áp dụng cho **kích thước lô**, không ngăn đơn hàng bán sỉ hợp lệ.
- REST và import job không thể bỏ qua bất biến hoặc quyền phù hợp.
- Database từ chối các giá trị không thể chấp nhận ở tầng lưu trữ.

Bài học: **tránh cả hai cực đoan** — lặp cùng quy tắc bán lẻ ở nhiều nơi không kiểm soát, và gộp những giới hạn thuộc các khái niệm khác nhau thành một hằng số chung.

## 19. Bài tập thực hành

### Bài tập 1 — Phân loại lặp tri thức

Hãy xác định trường hợp nào có thể là lặp tri thức, trường hợp nào chỉ giống cú pháp:

1. Checkout và preview cùng tính phí vận chuyển theo ngưỡng 500.000 VND.
2. Chính sách hoàn tiền và phí vận chuyển đều nhân tỷ lệ 10%.
3. Frontend và backend cùng từ chối số lượng âm trong luồng đặt hàng.
4. Hóa đơn lịch sử lưu phí đã chốt, còn checkout tính phí hiện tại.
5. Hai báo cáo có tên “doanh thu” nhưng một tính theo ngày thanh toán, một theo ngày tạo đơn.
6. Controller, service và job đều tự viết bảng chuyển trạng thái đơn ACTIVE → CANCELLED.

**Gợi ý:** (1) và (6) là ứng viên mạnh; (2) có thể chỉ giống phép toán; (3) có lý do bảo vệ hai ranh giới nhưng cần hợp đồng nhất quán; (4) là hai trách nhiệm theo thời điểm; (5) cần làm rõ định nghĩa chỉ số trước khi kết luận.

### Bài tập 2 — Tìm lỗi trường hợp biên

Xét hai đoạn:

~~~java
boolean inApi(BigDecimal amount) {
    return amount.compareTo(new BigDecimal("500000")) > 0;
}

boolean inJob(BigDecimal amount) {
    return amount.compareTo(new BigDecimal("500000")) >= 0;
}
~~~

Giả sử cả hai phải theo quy tắc: “Từ 500.000 đồng trở lên”. Hãy:
- Chỉ ra giá trị nhỏ nhất làm hai hàm khác nhau.
- Viết ba test cho dưới, bằng và trên ngưỡng.
- Đề xuất một nguồn sở hữu quy tắc, không chỉ sửa một dấu so sánh.
- Nêu cách kiểm chứng cả API và job thực sự dùng nguồn mới.

### Bài tập 3 — Có nên tạo hằng số toàn cục?

Một PR đề xuất:

~~~java
static final int DEFAULT_LIMIT = 100;
~~~

rồi dùng cho số lượng mặt hàng tối đa, số bản ghi mỗi trang và số phần tử trong một batch. Ba nơi hiện cùng lấy giá trị 100.

Hãy giải thích vì sao đây có thể là **wrong abstraction** và đặt tên/ranh giới rõ hơn cho từng giới hạn. Có trường hợp nào nên cùng chia sẻ **một giới hạn thật sự chung** không?

**Gợi ý:** Hãy phân tích người sở hữu và lý do thay đổi. Mỗi giới hạn có thể được điều chỉnh độc lập vì nghiệp vụ và hiệu năng khác nhau.

### Bài tập 4 — Giữ lịch sử khi chính sách thay đổi

Từ ngày 01/12, ngưỡng miễn phí vận chuyển chuyển từ 500.000 lên 700.000 VND. Một đơn ngày 28/11 đã chốt phí 0 VND vì subtotal 550.000 VND.

Hãy nêu:
- Checkout ngày 02/12 nên dùng ngưỡng nào?
- Hóa đơn cũ nên hiển thị phí gì?
- Cần lưu dữ liệu hoặc metadata nào để giải thích chênh lệch?
- Tại sao gọi lại **current ShippingFeePolicy** để tái tạo hóa đơn cũ có thể sai?

### Bài tập 5 — Kiểm tra giới hạn giữa nhiều service

Service A và B cùng xử lý mã lỗi **ORDER_NOT_FOUND**. A chuyển sang **ORDER_MISSING**, B vẫn gửi mã cũ. Ứng dụng di động nhận hai mã khác nhau cho cùng tình huống.

Hãy đề xuất:
- Nơi sở hữu **hợp đồng mã lỗi**.
- Cách triển khai có version và tương thích.
- Consumer/provider contract test thích hợp.
- Cách chuyển đổi có kiểm soát thay vì cập nhật mọi service trong một thời điểm bắt buộc.

### Bài tập 6 — Review một rule engine quá lớn

Một nhóm gộp kiểm tra giảm giá, phí vận chuyển, quyền hủy đơn và quota API vào **GlobalRuleEngine**. Mọi quy tắc dùng hàm **evaluate(String type, Map<String, Object> data)**.

Hãy nhận xét:
- Các rule có cùng lý do thay đổi không?
- Hợp đồng kiểu dữ liệu và lỗi còn rõ không?
- Các bản kiểm thử có còn diễn đạt trường hợp biên?
- Mức coupling có tăng không?
- Có thể chia thành các policy theo miền như thế nào?

**Gợi ý:** Tái sử dụng cơ chế thực thi chung có thể hợp lý trong một số hệ thống, nhưng không nên để nó xóa ranh giới nghiệp vụ hoặc tạo cấu hình khó kiểm chứng.

## 20. Tự kiểm tra kiến thức

**Câu 1.** Hai phương thức có cùng mười dòng Java thì chắc chắn cần gộp?

*Trả lời:* Không. Cần xác định chúng có cùng ngữ nghĩa và cùng lý do thay đổi không. Trùng cú pháp có thể chỉ là tình cờ.

**Câu 2.** Hai phương thức dùng cách viết khác nhau nhưng cùng ngưỡng miễn phí vận chuyển có thể là lặp tri thức?

*Trả lời:* Có. Nếu chúng biểu diễn cùng chính sách và phải thay đổi đồng bộ, đó là lặp tri thức dù cú pháp khác.

**Câu 3.** Vì sao một hằng số **GLOBAL_THRESHOLD** có thể làm thiết kế tệ hơn?

*Trả lời:* Nó có thể buộc những chính sách độc lập phải thay đổi cùng nhau chỉ vì hiện đang dùng cùng giá trị, tạo coupling sai.

**Câu 4.** Nếu frontend đã có validation số lượng, có nên bỏ validation server để tránh lặp?

*Trả lời:* Không. Server phải bảo vệ ranh giới tin cậy và bất biến nghiệp vụ. Cần đồng bộ định nghĩa hợp đồng, không xóa lớp bảo vệ cần thiết.

**Câu 5.** Tại sao hóa đơn đã phát hành không nên luôn tính lại phí theo chính sách mới?

*Trả lời:* Vì kết quả lịch sử phải phản ánh quyết định đã chốt tại thời điểm giao dịch. Tính lại có thể làm thay đổi dữ liệu lịch sử.

**Câu 6.** Một công cụ duplicate-code báo nhiều dòng lặp có chứng minh code quality thấp không?

*Trả lời:* Chưa. Nó báo dấu hiệu cấu trúc; cần xem tính sở hữu, hợp đồng, generated code, test và lý do thay đổi.

**Câu 7.** Sau khi đưa quy tắc về một policy, có cần test các caller nữa không?

*Trả lời:* Có. Unit test bảo vệ policy, nhưng caller vẫn có thể không dùng policy, dùng phiên bản cũ, truyền sai dữ liệu hoặc mapping sai. Cần test ranh giới phù hợp.

**Câu 8.** Nếu hai service dùng chung một thư viện chính sách, có chắc chúng cho kết quả như nhau?

*Trả lời:* Không. Chúng có thể chạy version khác, cấu hình khác hoặc dữ liệu đầu vào/thời điểm khác. Cần quản lý hợp đồng và triển khai.

**Câu 9.** Khi nào nên giữ hai cách triển khai tương tự tạm thời?

*Trả lời:* Khi chưa rõ chúng có cùng lý do thay đổi hay không, hoặc khi gộp sẽ tạo abstraction sai, coupling cao hơn hay phá ranh giới. Cần ghi nhận và theo dõi bằng chứng thay đổi.

**Câu 10.** Thành công của refactor lặp tri thức nên được đo bằng gì?

*Trả lời:* Bằng tính nhất quán của hành vi, ít nơi phải sửa độc lập khi chính sách đổi, kiểm thử trường hợp biên, khả năng truy nguyên và mức coupling hợp lý — không chỉ số dòng bị xóa.

## Ghi nhớ

**Mùi mã lặp tri thức** xuất hiện khi cùng một quyết định, quy tắc hoặc giả định được duy trì ở nhiều nơi **phải thay đổi cùng nhau**. Nó làm tăng nguy cơ lệch hành vi, bỏ sót khi sửa và khó xác định nguồn sự thật. Cách cải thiện không phải xóa mọi đoạn code giống nhau, mà là **xác định đúng tri thức chung, người sở hữu và lý do thay đổi**, rồi đưa quyết định vào một hợp đồng hoặc nguồn chính sách phù hợp, kèm test và chiến lược versioning. Đồng thời, phải giữ nguyên những khác biệt có chủ đích: validation ở nhiều ranh giới, những chính sách độc lập, snapshot lịch sử và dữ liệu sao chép phục vụ hiệu năng. **DRY có giá trị khi giảm các bản sao của cùng tri thức mà không gộp sai những trách nhiệm thực sự khác nhau.**
