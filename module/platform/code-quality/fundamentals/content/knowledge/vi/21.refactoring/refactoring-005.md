# Thực hiện từng bước nhỏ có thể kiểm tra và hoàn tác

Một nhóm muốn cải thiện phương thức xử lý đơn hàng đang dài và khó hiểu. Phương án hấp dẫn là viết lại toàn bộ trong một nhánh lớn, đổi tên các lớp, tách repository, thêm abstraction mới rồi chạy test ở cuối. Nếu kết quả sai, nhóm sẽ phải tìm lỗi trong hàng chục thay đổi xảy ra cùng lúc. Nếu đã triển khai và phát sinh sự cố, việc quay lại phiên bản cũ cũng có thể không đơn giản.

Cách an toàn hơn là **tái cấu trúc theo các bước nhỏ, mỗi bước có mục tiêu rõ ràng, có bằng chứng kiểm chứng và có phương án hoàn tác**. Việc cải thiện cấu trúc lúc ấy trở thành một chuỗi quyết định có thể quan sát, thay vì một cuộc viết lại mà không biết chính xác lúc nào hành vi bắt đầu thay đổi.

Bài học thuộc chương **Tái cấu trúc** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu của module — hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không — bài này hướng dẫn lựa chọn bước refactor vừa đủ nhỏ, bảo vệ hành vi, tách thay đổi cấu trúc khỏi thay đổi nghiệp vụ, tổ chức commit có thể xem lại và phân biệt **hoàn tác mã nguồn** với **khôi phục hệ thống đã triển khai**.

## 1. Refactoring là gì, và điều gì không phải refactoring?

**Refactoring (tái cấu trúc mã)** là thay đổi cấu trúc bên trong nhằm làm mã dễ hiểu, dễ kiểm thử hoặc dễ thay đổi hơn, trong khi **giữ hành vi quan sát được theo hợp đồng đang áp dụng**.

Ví dụ:

- Trích một đoạn tính tổng tiền thành phương thức có tên rõ hơn, giữ nguyên công thức.
- Đổi tên biến cục bộ `x` thành `subtotalVnd`, không đổi kiểu và dữ liệu.
- Tách logic tính giá khỏi phần định dạng báo cáo nhưng vẫn trả đúng cùng kết quả.
- Bỏ tầng chuyển tiếp không có trách nhiệm riêng sau khi xác minh không có hợp đồng public phụ thuộc.
- Đưa một phụ thuộc I/O vào ranh giới rõ để kiểm thử tính toán độc lập, không đổi hành vi nghiệp vụ.

Những việc dưới đây **không thuần túy là refactor**:

- Đổi ngưỡng miễn phí vận chuyển từ 500.000 VND thành 600.000 VND.
- Sửa lỗi tính tiền bị làm tròn sai.
- Thêm trường vào response mà client trước đây không nhận.
- Thay thời điểm gửi email hay phát sự kiện theo cách caller quan sát được.
- Đổi thứ tự ghi dữ liệu làm thay đổi transaction hoặc khả năng retry.
- Thay đổi độ tươi dữ liệu khi thêm cache.

Những thay đổi đó có thể cần thiết và mang lại giá trị, nhưng cần được mô tả như **thay đổi hành vi**, **sửa lỗi** hoặc **thay đổi vận hành**, với test và quy trình triển khai phù hợp. Việc gọi tất cả là “refactor” dễ khiến reviewer bỏ sót tác động.

### 1.1. Hành vi cần giữ không chỉ là giá trị trả về

| Ranh giới | Điều cần hỏi trước khi sửa |
| --- | --- |
| **Kết quả nghiệp vụ** | Cùng dữ liệu có cho cùng tổng tiền, quyền và trạng thái không? |
| **Lỗi và ngoại lệ** | Loại lỗi, mã lỗi và điều kiện xảy ra có phải hợp đồng với caller không? |
| **I/O và tác dụng phụ** | Có ghi DB, gửi email, phát event, tạo file hoặc gọi API ở thời điểm khác không? |
| **Thứ tự và tính nguyên tử** | Có thay đổi thứ tự ghi, ranh giới transaction hoặc cách phục hồi không? |
| **Đồng thời** | Có đổi vùng state dùng chung, lock hoặc thứ tự có thể xảy ra không? |
| **Hợp đồng public** | Chữ ký method, JSON, schema, topic hoặc API có được bên ngoài sử dụng không? |
| **Tài nguyên và hiệu năng** | Có tác động đáng kể đến bộ nhớ, độ trễ hoặc số lần gọi hệ thống ngoài không? |
| **Bảo mật** | Quyền truy cập và mức lộ dữ liệu có được giữ như yêu cầu không? |

Không phải chi tiết nội bộ nào cũng cần giữ nguyên. Ví dụ, số lần gọi một helper private có thể thay đổi khi tách phương thức. Điều cần giữ là **hành vi mà người dùng, các bên tích hợp và hợp đồng kỹ thuật liên quan có quyền dựa vào**.

Trong một số trường hợp mã cũ có bug. **Giữ nguyên bug không phải mục tiêu cuối cùng**; điều quan trọng là phân biệt rõ giai đoạn tái cấu trúc với giai đoạn sửa lỗi để biết kết quả nào đã thay đổi, tại sao và có test bảo vệ hay không.

## 2. Vì sao bước nhỏ lại dễ kiểm chứng và hoàn tác?

Một thay đổi nhỏ tạo ra **ít giả thuyết cần kiểm tra cùng lúc**. Khi chuyển từ một trạng thái “xanh” sang trạng thái “đỏ”, nhóm biết phạm vi thay đổi vừa diễn ra và có thể sửa hoặc quay lại ngay.

Một vòng lặp thực dụng:

~~~mermaid
flowchart TD
    A[Chọn một vấn đề cấu trúc cụ thể] --> B[Giữ baseline xanh]
    B --> C[Đảm bảo test bảo vệ hành vi]
    C --> D[Thực hiện một biến đổi nhỏ]
    D --> E[Kiểm tra nhanh và review diff]
    E --> F{Đạt yêu cầu?}
    F -- Có --> G[Commit mốc nhỏ có ý nghĩa]
    F -- Không --> H[Sửa trong phạm vi nhỏ hoặc hoàn tác]
    H --> B
    G --> I{Còn vấn đề cần giải quyết?}
    I -- Có --> A
    I -- Không --> J[Kiểm chứng tích hợp và chuẩn bị bàn giao]
~~~

**Bước nhỏ** không có nghĩa “chỉ thay đúng một dòng”. Một bước phù hợp là thay đổi có thể diễn đạt rõ:

> “Đưa đoạn tính subtotal sang phương thức `calculateSubtotalVnd`, giữ nguyên dữ liệu, thứ tự phép tính và điều kiện lỗi.”

Bước quá lớn có thể là “viết lại toàn bộ checkout và đồng thời thêm chính sách thanh toán mới”. Bước quá nhỏ cũng có thể gây nhiễu nếu chia một thay đổi logic thành nhiều commit không tự đọc hiểu được. Mục tiêu là **đơn vị thay đổi có thể kiểm chứng và có ý nghĩa**, không chạy theo số dòng.

### 2.1. Ba tiêu chí để chọn kích thước bước

1. **Một lý do chính:** reviewer có thể nói rõ ta đang cải thiện điều gì.
2. **Bằng chứng nhanh:** có test, phép kiểm tra cấu trúc hoặc đối chiếu hành vi phù hợp ngay sau bước đó.
3. **Đường lui rõ:** biết cách trở về trạng thái tốt trước đó mà không phải tháo gỡ hàng loạt thay đổi không liên quan.

Nếu một bước vừa đổi dữ liệu đầu vào, vừa thay SQL, vừa dời transaction và thêm caching, rất khó biết lỗi đến từ đâu. Nên chia theo ranh giới.

### 2.2. Refactor theo bước nhỏ không thay thế thiết kế

Các bước nhỏ vẫn cần **đích đến hợp lý**. Nếu cứ trích method ngẫu nhiên, code có thể xuất hiện nhiều lớp mỏng, khó đọc và làm phụ thuộc tăng.

Trước khi bắt đầu, hãy mô tả **khó khăn hiện tại** và **dấu hiệu thành công**: chẳng hạn “để thay quy tắc giảm giá, chỉ phải sửa một policy và test tương ứng; phần xuất báo cáo không phụ thuộc trực tiếp vào công thức tính”.

Mục tiêu này cho phép nhóm dừng khi vấn đề đã được giải quyết, thay vì tiếp tục tách lớp vì muốn kiến trúc trông “đẹp”.

## 3. Chuẩn bị baseline và bằng chứng bảo vệ hành vi

Trước refactor, cần xác định **trạng thái ban đầu đáng tin**:

- Phiên bản mã, cấu hình và môi trường đang được dùng.
- Các test liên quan đang qua hay đang lỗi từ trước.
- Đầu vào, đầu ra và hợp đồng nghiệp vụ nào cần giữ.
- Hệ thống ngoài nào tham gia và cần integration test.
- Những hành vi chưa rõ hoặc đang có lỗi đã biết.
- Khả năng quay lại commit và khả năng quay lại phiên bản triển khai.

Không nhất thiết đạt 100% coverage mới được refactor. Nhưng với vùng rủi ro, cần có **bằng chứng đủ nhạy để phát hiện sai lệch quan trọng**.

### 3.1. Characterization test và test theo đặc tả

**Characterization test** ghi lại hành vi quan sát được của mã hiện tại. Nó hữu ích khi code cũ ít tài liệu, khó nhìn hết các nhánh và muốn tránh thay đổi vô ý.

Tuy nhiên, nếu behavior cũ vốn sai, snapshot hoặc golden output có thể **đóng băng bug**. Vì thế:

- Ghi rõ trường hợp test chỉ mô tả **hành vi hiện tại**.
- Với quy tắc quan trọng, xác nhận **expected** từ đặc tả hoặc người sở hữu nghiệp vụ.
- Nếu phát hiện lỗi, tạo một công việc sửa lỗi riêng với expected đúng.
- Không âm thầm đổi expected để làm test xanh khi refactor.

### 3.2. Chọn các trường hợp có sức phân biệt

Ví dụ chính sách giảm giá có ngưỡng, nên thử:

| Trường hợp | Đầu vào | Điều cần xác nhận |
| --- | --- | --- |
| Khách VIP đúng ngưỡng | 500.000 VND | Có giảm giá |
| Khách VIP sát dưới ngưỡng | 499.999 VND | Không giảm |
| Khách thường trên ngưỡng | 800.000 VND | Không áp dụng ưu đãi VIP |
| Giá trị không hợp lệ | Tổng âm | Bị từ chối theo hợp đồng |
| Giá trị lớn | Gần giới hạn `long` | Không âm thầm tạo kết quả tràn |
| Đầu ra văn bản | Giá trị và thứ tự các dòng | Không đổi schema báo cáo |

Test gọi qua mã nhưng chỉ `assertNotNull` không đủ để bảo vệ các hành vi trên. **Mỗi test phải có oracle**: lý do tin kết quả mong đợi là đúng.

## 4. Ví dụ Java xuyên suốt: tách tính giá khỏi định dạng báo cáo

Giả sử một ứng dụng tạo báo cáo đơn hàng. Mã hiện tại xử lý cả phép tính giá và cách trình bày trong một method. Nhu cầu là **làm rõ trách nhiệm** để thay đổi chính sách giá không kéo theo mã xuất báo cáo.

Hợp đồng minh họa:

- Đơn có `orderId` không rỗng và các dòng hàng; giá đơn vị nguyên VND không âm, số lượng dương.
- Tổng trước giảm = tổng `unitPriceVnd × quantity`.
- Khách VIP có tổng từ 500.000 VND trở lên được giảm `subtotal / 10`, làm tròn xuống VND nguyên.
- Tổng phải trả = tổng trước giảm − giảm giá.
- Báo cáo UTF-8 ở ví dụ sử dụng các dòng kết thúc bằng ký tự `\n`, cố ý **không phụ thuộc** `System.lineSeparator()`.
- Các phép cộng, nhân và trừ dùng `Math.*Exact` để phát hiện tràn số.

Đây là **quy tắc giả định cho bài học**, không phải chính sách của một hệ thống cụ thể.

### 4.1. Mô hình dữ liệu đầu vào

Ví dụ Java 17 với record bất biến:

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, long unitPriceVnd, int quantity) {
    OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (unitPriceVnd < 0L) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}

record CheckoutOrder(
        String orderId,
        List<OrderLine> lines,
        boolean vip) {

    CheckoutOrder {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId is required");
        }
        Objects.requireNonNull(lines, "lines");
        lines = List.copyOf(lines);
    }
}
~~~

`List.copyOf` giữ snapshot cấu trúc danh sách và từ chối phần tử `null`. Nó là **bản sao nông**; đủ cho ví dụ vì `OrderLine` chỉ giữ trường bất biến. Đây là điều kiện đầu vào của cả phiên bản trước lẫn sau, không phải validation thêm giữa refactor.

### 4.2. Phiên bản trước: đúng hành vi nhưng gộp nhiều trách nhiệm

~~~java
final class LegacyCheckoutReport {
    String render(CheckoutOrder order) {
        long subtotalVnd = 0L;

        for (OrderLine line : order.lines()) {
            long lineTotalVnd = Math.multiplyExact(
                    line.unitPriceVnd(), (long) line.quantity());
            subtotalVnd = Math.addExact(
                    subtotalVnd, lineTotalVnd);
        }

        long discountVnd =
                order.vip() && subtotalVnd >= 500_000L
                        ? subtotalVnd / 10L
                        : 0L;

        long amountDueVnd = Math.subtractExact(
                subtotalVnd, discountVnd);

        return "orderId=" + order.orderId() + "\n"
                + "subtotalVnd=" + subtotalVnd + "\n"
                + "discountVnd=" + discountVnd + "\n"
                + "amountDueVnd=" + amountDueVnd + "\n";
    }
}
~~~

Mã này có thể trả kết quả đúng với hợp đồng đã nêu. **Mùi thiết kế** nằm ở việc công thức giá và định dạng báo cáo sống cùng nhau. Nếu sau này bổ sung nhiều định dạng hoặc sửa quy tắc giá, người bảo trì có thể vô ý chạm cả hai trách nhiệm.

Đừng refactor bằng cách đổi ngay thuật toán giảm giá, kiểu tiền, định dạng văn bản và cấu trúc class trong một lần. Ta sẽ đi qua từng bước với mốc kiểm chứng.

### 4.3. Bước 0 — Viết test cho kết quả đang cam kết

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class LegacyCheckoutReportTest {
    private final LegacyCheckoutReport report =
            new LegacyCheckoutReport();

    @Test
    void preservesVipReportAtThreshold() {
        CheckoutOrder order = new CheckoutOrder(
                "O-01",
                List.of(new OrderLine("A", 250_000L, 2)),
                true);

        String actual = report.render(order);

        assertEquals(
                "orderId=O-01\n"
                        + "subtotalVnd=500000\n"
                        + "discountVnd=50000\n"
                        + "amountDueVnd=450000\n",
                actual);
    }

    @Test
    void preservesNonVipAndNoDiscount() {
        CheckoutOrder order = new CheckoutOrder(
                "O-02",
                List.of(new OrderLine("B", 300_000L, 2)),
                false);

        assertEquals(
                "orderId=O-02\n"
                        + "subtotalVnd=600000\n"
                        + "discountVnd=0\n"
                        + "amountDueVnd=600000\n",
                report.render(order));
    }

    @Test
    void preservesOverflowDetection() {
        CheckoutOrder order = new CheckoutOrder(
                "O-03",
                List.of(new OrderLine(
                        "C", Long.MAX_VALUE, 2)),
                false);

        assertThrows(ArithmeticException.class,
                () -> report.render(order));
    }
}
~~~

Đầu ra mong đợi cần được kiểm tra với hợp đồng đã thống nhất, không chỉ lấy tự động từ bản mã cũ. Trong ví dụ, test kiểm tra cả **số tiền và thứ tự các dòng**. Nếu định dạng báo cáo là public contract, đổi thứ tự hoặc xuống dòng cũng có thể làm client bị ảnh hưởng.

Sau khi có baseline xanh, nhóm có thể bắt đầu thay đổi cấu trúc. Nếu test ban đầu đỏ, hãy xác định **lỗi có sẵn** trước khi đổ lỗi cho refactor.

### 4.4. Bước 1 — Extract Method cho phép tính subtotal

Thay vòng lặp trong `render` bằng một lời gọi:

~~~java
long subtotalVnd = calculateSubtotalVnd(order);
~~~

Đồng thời đưa **nguyên vòng lặp đang có** vào phương thức private:

~~~java
private static long calculateSubtotalVnd(CheckoutOrder order) {
    long subtotalVnd = 0L;

    for (OrderLine line : order.lines()) {
        long lineTotalVnd = Math.multiplyExact(
                line.unitPriceVnd(), (long) line.quantity());
        subtotalVnd = Math.addExact(
                subtotalVnd, lineTotalVnd);
    }
    return subtotalVnd;
}
~~~

Không đổi thứ tự phép tính, không chuyển từ `Math.addExact` sang phép `+`, và chưa chuyển sang stream chỉ vì phong cách. **Một bước chỉ trích phương thức** giúp ta dễ khẳng định thuật toán cũ và mới thực thi tương đương trên các đầu vào đã chọn.

Kiểm tra sau bước:

1. Mã biên dịch được.
2. Test báo cáo, giá trị biên và overflow vẫn xanh.
3. Diff chỉ chứa việc tạo phương thức và thay bằng lời gọi.
4. Không xuất hiện phụ thuộc hoặc tác dụng phụ mới.

Đây là một **điểm dừng tốt**: nếu việc tiếp tục bị gián đoạn, mã vẫn có trạng thái hợp lệ và dễ hiểu hơn.

### 4.5. Bước 2 — Gom kết quả tính toán trong đối tượng rõ ý nghĩa

Khi cần tách tính giá khỏi định dạng, có thể đưa các giá trị liên quan vào một kiểu dữ liệu:

~~~java
record PriceQuote(
        String orderId,
        long subtotalVnd,
        long discountVnd,
        long amountDueVnd) {}
~~~

Trước khi chuyển logic sang class mới, có thể trích một phương thức `calculateQuote` ngay trong class cũ, trả về `PriceQuote`. Sau đó phần `render` đọc từng trường của `PriceQuote`.

Vì **dạng văn bản đầu ra không đổi**, test cũ vẫn có giá trị. Có thể thêm unit test riêng cho `calculateQuote` nếu phương thức được đưa ra package phù hợp hoặc chuyển sang class có hợp đồng riêng. Đừng thêm một abstraction mới chỉ để tăng số lớp; `PriceQuote` có giá trị vì nó **biểu diễn kết quả nghiệp vụ thực** đang được nhiều bước sử dụng.

### 4.6. Bước 3 — Move Method sang chính sách tính giá

Khi phương thức tính toán đã đứng riêng và test bảo vệ kết quả, chuyển nó sang `PricingPolicy`:

~~~java
final class PricingPolicy {
    PriceQuote quote(CheckoutOrder order) {
        long subtotalVnd = 0L;
        for (OrderLine line : order.lines()) {
            long lineTotalVnd = Math.multiplyExact(
                    line.unitPriceVnd(), (long) line.quantity());
            subtotalVnd = Math.addExact(
                    subtotalVnd, lineTotalVnd);
        }

        long discountVnd =
                order.vip() && subtotalVnd >= 500_000L
                        ? subtotalVnd / 10L
                        : 0L;

        long amountDueVnd = Math.subtractExact(
                subtotalVnd, discountVnd);

        return new PriceQuote(
                order.orderId(),
                subtotalVnd,
                discountVnd,
                amountDueVnd);
    }
}
~~~

Đây là cùng công thức và cùng thứ tự kiểm tra như ví dụ ban đầu. Mục tiêu của bước này là **đổi nơi chịu trách nhiệm**, không phải tối ưu công thức.

Nếu có nhiều package hoặc module, bảo đảm **chiều phụ thuộc** phù hợp: chính sách giá không nên phải import lớp định dạng báo cáo, HTTP controller hoặc JDBC chỉ để tính toán.

### 4.7. Bước 4 — Tách phần định dạng báo cáo

~~~java
import java.util.Objects;

final class CheckoutReportFormatter {
    private final PricingPolicy pricing;

    CheckoutReportFormatter(PricingPolicy pricing) {
        this.pricing = Objects.requireNonNull(pricing, "pricing");
    }

    String render(CheckoutOrder order) {
        PriceQuote quote = pricing.quote(order);

        return "orderId=" + quote.orderId() + "\n"
                + "subtotalVnd=" + quote.subtotalVnd() + "\n"
                + "discountVnd=" + quote.discountVnd() + "\n"
                + "amountDueVnd=" + quote.amountDueVnd() + "\n";
    }
}
~~~

Lúc này:

- `PricingPolicy` chịu trách nhiệm tính giá.
- `CheckoutReportFormatter` chịu trách nhiệm biểu diễn văn bản.
- `PriceQuote` diễn đạt dữ liệu trung gian có ý nghĩa.
- `CheckoutOrder` chứa đầu vào bất biến.

**Không tự ý đổi format sang JSON hoặc thêm dấu phân tách mới** trong cùng bước. Nếu muốn thay hợp đồng đầu ra, đó là một thay đổi riêng với test và kế hoạch tương thích.

### 4.8. Bước 5 — Giữ facade cũ trong giai đoạn di chuyển caller

Nếu `LegacyCheckoutReport` đang được nhiều nơi gọi, không bắt buộc sửa tất cả caller ngay. Có thể giữ một lớp tương thích:

~~~java
final class LegacyCheckoutReport {
    private final CheckoutReportFormatter formatter =
            new CheckoutReportFormatter(new PricingPolicy());

    String render(CheckoutOrder order) {
        return formatter.render(order);
    }
}
~~~

Đây là một **tầng chuyển tiếp có mục đích và vòng đời rõ**, không phải abstraction mới “để dành”. Nó cho phép đổi cấu trúc nội bộ mà giữ điểm gọi cũ. Khi caller đã chuyển và không còn phụ thuộc tương thích, có thể xóa trong một bước khác.

Cần kiểm tra thêm:

- Bên ngoài repository có dùng class/phương thức cũ không?
- Framework có nạp class qua reflection hoặc DI không?
- Constructor hoặc exception của facade cũ có hợp đồng khác không?
- Việc tạo phụ thuộc trong facade có tác động state, thread-safety hay tài nguyên không?

Với ví dụ tính toán thuần này, một `PricingPolicy` dùng chung không giữ mutable state nên phù hợp. Nhưng không được sao chép mô hình khởi tạo này cho HTTP client, DB connection hoặc đối tượng giữ request state mà không xét vòng đời.

## 5. Phân chia việc kiểm chứng theo từng bước

Không phải mọi bước đều cần chạy bộ end-to-end kéo dài. Nhưng mọi bước cần **phép kiểm chứng tương xứng với rủi ro**.

| Bước | Thay đổi dự kiến | Kiểm chứng nhanh | Kiểm chứng bổ sung |
| --- | --- | --- | --- |
| Đổi tên biến private | Cải thiện tên, không đổi dữ liệu | Compile, unit test liên quan, diff review | Tìm string/reflection nếu tên có thể bị dùng gián tiếp |
| Extract Method | Di chuyển cùng logic | Unit test, linter, đối chiếu thứ tự phép tính | Test lỗi/overflow nếu vùng có rủi ro |
| Move Method | Đổi nơi chứa logic | Test theo hành vi và kiểm tra phụ thuộc | Architecture test, wiring module |
| Introduce Parameter Object | Nhóm dữ liệu có ý nghĩa | Test validate, giá trị và nullability | Serialization/compatibility nếu là hợp đồng public |
| Tách I/O khỏi domain | Đổi ranh giới nhưng không đổi use case | Unit test với fake, test kết quả | Integration test adapter, transaction |
| Thay đổi signature public | Có thể ảnh hưởng caller | Compile và contract tests | Tương thích SDK, consumer ngoài |
| Chuyển cấu hình/DI | Đổi cách khởi tạo hoặc chọn implementation | Startup/wiring test | Smoke test môi trường đại diện |
| Đổi database/schema | Có thể vượt phạm vi refactor thuần | Migration test | Mixed-version, rollback, backup/recovery theo rủi ro |

**Compile thành công không chứng minh nghiệp vụ đúng**. Test xanh cũng chỉ chứng minh các điều kiện đã được chọn. Cần đặt lớp bằng chứng nơi có rủi ro, thay vì chạy một bộ test khổng lồ như nghi thức rồi bỏ qua kết quả.

## 6. Chia commit để dễ review, bisect và hoàn tác

Một commit refactor tốt nên chứa **một thay đổi có lý do rõ và ở trạng thái có thể kiểm tra được**. Ví dụ lịch sử hợp lý:

~~~text
1. test(checkout): bảo vệ report ở ngưỡng VIP và overflow
2. refactor(checkout): trích calculateSubtotalVnd
3. refactor(checkout): đưa kết quả tính toán vào PriceQuote
4. refactor(checkout): chuyển chính sách tính giá sang PricingPolicy
5. refactor(checkout): tách CheckoutReportFormatter
6. refactor(checkout): giữ adapter tương thích, cập nhật caller
7. chore(checkout): xóa adapter cũ khi không còn người dùng
~~~

Tên commit là minh họa, không phải yêu cầu bắt buộc dùng một convention nhất định. Điều quan trọng là reviewer có thể kiểm tra **mỗi bước giữ hay cố ý đổi hành vi nào**.

### 6.1. Vì sao tránh trộn “refactor + fix bug + thêm tính năng”?

Khi một PR đồng thời thay tên, đổi thuật toán giảm giá và sửa SQL, một test thất bại sẽ có rất nhiều nguyên nhân khả dĩ. Bản rollback cũng có thể xóa theo cả bug fix hoặc feature quan trọng mà nhóm muốn giữ.

Có thể tổ chức:

- **Commit bảo vệ hành vi hiện tại.**
- **Commit refactor thuần.**
- **Commit sửa bug hoặc đổi yêu cầu**, với test riêng chứng minh hành vi mong đợi mới.

Đôi khi không thể tách tuyệt đối, chẳng hạn thay interface để sửa lỗi bảo mật. Khi đó phải ghi rõ **phần nào là behavior change**, phần nào là structural change và đánh giá rủi ro tương ứng; không gắn nhãn “refactor only” thiếu trung thực.

### 6.2. Khả năng kiểm tra độc lập của từng mốc

Lý tưởng, sau mỗi commit có thể:

1. Checkout đúng phiên bản mã.
2. Biên dịch ở cấu hình được hỗ trợ.
3. Chạy các test liên quan.
4. Đọc diff hiểu thay đổi mà không phải mở nhiều commit sau.
5. Dùng `git bisect` hoặc xem lịch sử để xác định mốc bắt đầu hồi quy khi phù hợp.

Có thể có các bước trung gian ngắn ở workspace chưa biên dịch, nhưng **đừng lưu một lịch sử toàn các commit không thể kiểm thử** nếu quy trình dự án yêu cầu commit xanh. Mục tiêu là có nhiều mốc an toàn để phục hồi.

### 6.3. Một số thao tác Git minh họa

~~~bash
# Chỉ là lệnh minh họa; chưa thực thi trên repository nào.
git status
git diff --check
git diff
git add path/to/changed-file.java
git commit -m "refactor(checkout): extract subtotal calculation"

# Khi muốn xem riêng một commit:
git show <commit-id>

# Hoàn tác tác động của commit đã chia sẻ bằng một commit mới:
git revert <commit-id>
~~~

Với `git revert`, cần giải quyết conflict nếu các commit sau đã phụ thuộc vào thay đổi đó. **Revert một commit không bảo đảm hệ thống quay lại đúng trạng thái trước đó** nếu có dữ liệu đã ghi, message đã gửi hoặc migration đã chạy. Không dùng `git reset --hard` trên nhánh làm việc chứa thay đổi chưa lưu hoặc nhánh chia sẻ mà không hiểu hậu quả.

Bài học không yêu cầu chạy lệnh Git; các lệnh trên chỉ minh họa cách duy trì mốc kiểm chứng.

## 7. Hoàn tác mã và rollback hệ thống là hai việc khác nhau

Một refactor ở hàm tính toán thuần thường có thể quay lại phiên bản cũ khá dễ. Nhưng refactor đi qua **API, database, message broker hoặc tài nguyên bên ngoài** có thể tạo trạng thái không đảo ngược chỉ bằng Git.

| Loại thay đổi | Hoàn tác source code | Việc phải xét thêm khi đã triển khai |
| --- | --- | --- |
| Đổi tên phương thức private | Thường đơn giản | Build và consumer nội bộ |
| Di chuyển logic giữa class | Có thể revert commit | Wiring/DI và cấu hình triển khai |
| Đổi tên API public | Có thể khôi phục source | Client đã nâng phiên bản, tính tương thích |
| Đổi schema database | Có thể revert migration file | Dữ liệu mới, khóa, index và các phiên bản app đang chạy |
| Đổi định dạng event | Có thể khôi phục producer | Consumer đã nhận event phiên bản mới |
| Đổi cách ghi thanh toán | Có thể khôi phục handler | Giao dịch đã gửi, retry, idempotency và đối soát |
| Xóa đường đọc cũ | Có thể khôi phục source | Dữ liệu cũ có còn đọc được không? |
| Bật feature flag | Có thể tắt flag nếu được thiết kế đúng | State và side effect đã tạo bởi đường mới |

### 7.1. Hoàn tác source code

Một commit refactor nhỏ, chỉ đổi cấu trúc private, có test giữ hành vi thường dễ:

- Dùng commit trước đó làm baseline.
- Revert hoặc đưa lại đúng phần thay đổi.
- Chạy lại test và xác minh artifact mới.

Đây là **khả năng hoàn tác ở cấp repository**.

### 7.2. Rollback deployment

Ứng dụng đã triển khai có thể cần quay về artifact trước, đổi cấu hình hoặc tắt feature flag. Nhưng rollback chỉ an toàn nếu **artifact cũ vẫn đọc/ghi được dữ liệu và hợp đồng đang tồn tại**.

Nếu bản mới tạo bản ghi có schema khác mà bản cũ không hiểu, việc triển khai lại bản cũ có thể làm dịch vụ lỗi ngay. Vì vậy, tính đảo ngược phải được thiết kế **trước khi rollout**, không chỉ chuẩn bị một nút “deploy previous”.

### 7.3. Tác dụng phụ nghiệp vụ không tự hoàn tác

Ví dụ hệ thống đã gửi email xác nhận, đã chuyển tiền hoặc đã phát message tiêu thụ bởi hệ thống khác. Revert code không thể “thu hồi” tất cả tác dụng phụ đó.

Cần kế hoạch riêng: idempotency, đối soát, bù trừ nghiệp vụ, ngăn ghi trùng, phân biệt trạng thái chưa xác định và kiểm soát retry. Những việc này thuộc thiết kế độ tin cậy của luồng nghiệp vụ, vượt quá một refactor nội bộ thuần.

## 8. Thay đổi database: mở rộng trước, chuyển đổi sau

Khi refactor đi kèm đổi schema, một kỹ thuật thường dùng là **expand–migrate–contract**, nhằm cho các phiên bản ứng dụng cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp.

~~~mermaid
flowchart LR
    A[Schema cũ đang hoạt động] --> B[Expand: thêm cấu trúc tương thích]
    B --> C[Migrate: ghi và đọc theo hợp đồng chuyển tiếp]
    C --> D[Kiểm chứng dữ liệu và toàn bộ consumer]
    D --> E[Contract: bỏ cấu trúc cũ]
~~~

### 8.1. Expand

Thêm trường hoặc bảng mới theo cách **không phá việc đọc/ghi của phiên bản cũ**. Ví dụ thêm cột nullable để app cũ vẫn thao tác được. Kiểm tra ảnh hưởng của migration đến khóa, index, thời gian lock và tài nguyên.

Không phải mọi thay đổi schema đều tương thích; cần xem engine DB, loại cột, constraint và hành vi viết của ứng dụng đang chạy.

### 8.2. Migrate

Chuyển dữ liệu hoặc triển khai logic đọc/ghi mới theo từng bước:

- Xác định nguồn dữ liệu chuẩn trong thời gian chuyển đổi.
- Nếu cần dual-write, thiết kế kiểm tra nhất quán và xử lý ghi lỗi một phần.
- Backfill dữ liệu theo batch có thể phục hồi, không làm quá tải DB.
- Đo số bản ghi đã chuyển và các trường hợp không thể ánh xạ.
- Kiểm tra trạng thái khi bản cũ và bản mới cùng chạy.

Đừng mặc định **ghi hai nơi luôn nguyên tử**. Hai database, hai service hoặc cả DB và message broker cần cơ chế giao dịch và khôi phục phù hợp.

### 8.3. Contract

Chỉ xóa trường/bảng cũ khi đã có bằng chứng:

- Các phiên bản ứng dụng cũ không còn phụ thuộc.
- Job nền và consumer ngoài đã được cập nhật.
- Dữ liệu cũ đã được chuyển và có khả năng khôi phục.
- Việc quay về artifact trước không còn là chiến lược rollback bắt buộc hoặc đã có phương án khác.

**Contract thường là bước khó hoàn tác nhất.** Nên coi đây là một thay đổi riêng, có thời điểm và điều kiện rõ ràng, không gộp cùng bước “đổi tên field trong code”.

## 9. Feature flag như công cụ chuyển đổi, không phải phép màu rollback

Khi cần duy trì đường cũ và đường mới trong giai đoạn rollout, feature flag có thể cho phép đổi luồng xử lý theo phạm vi người dùng hoặc môi trường. Nhưng hai nhánh đồng tồn tại làm tăng chi phí test, cấu hình và rủi ro trạng thái.

Một thiết kế an toàn cần nêu:

1. **Mục đích flag:** chuyển đổi phiên bản hay kích hoạt tính năng mới?
2. **Phạm vi:** user, tenant, vùng triển khai hay tỷ lệ traffic?
3. **Điều kiện an toàn:** hai đường có cùng dữ liệu đầu vào và kết quả theo hợp đồng không?
4. **Tác dụng phụ:** tắt flag có đảo ngược được dữ liệu đã ghi không?
5. **Quan sát:** lỗi, latency và kết quả theo từng nhánh được theo dõi thế nào?
6. **Chủ sở hữu và thời hạn xóa:** khi nào đường cũ không còn cần nữa?

Một flag **không thể đảm bảo rollback** nếu luồng mới đã ghi định dạng dữ liệu mà luồng cũ không đọc được. Đồng thời, việc giữ flag mãi mãi có thể tạo **mùi mã nhánh cũ không còn nhu cầu**, làm mọi thay đổi sau phải xét hai đường xử lý.

### 9.1. Shadow execution cũng cần thận trọng

Chạy song song logic cũ và mới rồi so sánh kết quả có thể hữu ích cho **hàm thuần**, ví dụ tính giá từ snapshot đầu vào. Nhưng **không được** vô tư chạy hai lần chức năng có tác dụng phụ như trừ tiền, ghi đơn hoặc gửi email.

Nếu muốn shadow một luồng có I/O, cần cách ly tác dụng phụ hoặc chỉ so sánh kết quả được mô hình hóa an toàn, với giới hạn quyền, chi phí và dữ liệu phù hợp.

## 10. Refactor có trạng thái dùng chung và xử lý đồng thời

Một thay đổi cấu trúc tưởng đơn giản có thể làm thay đổi tính an toàn đồng thời nếu:

- Chuyển biến cục bộ của request thành field singleton.
- Chia sẻ một instance chứa bộ tích lũy mutable cho nhiều thread.
- Đưa `synchronized` ra ngoài hoặc bỏ lock để “sạch mã”.
- Thay collection có đồng bộ bằng collection thường.
- Đổi thứ tự đọc và ghi state hoặc ranh giới transaction.

Ví dụ không an toàn:

~~~java
final class SharedCounter {
    private int processed;

    void markProcessed() {
        processed++; // Không nguyên tử trong nhiều thread.
    }
}
~~~

Nếu refactor tạo một `SharedCounter` dùng chung ở nơi trước đó mỗi task có bộ đếm riêng, hành vi đồng thời đã thay đổi. Unit test tuần tự có thể vẫn xanh.

Khi refactor state, cần vẽ rõ **ai sở hữu dữ liệu và vòng đời**:

| Trạng thái | Ranh giới cần giữ |
| --- | --- |
| Biến tạm khi tính giá | Riêng từng lời gọi |
| Context request | Không rò sang request khác hoặc thread pool |
| Bộ đếm metric | Cơ chế cập nhật đồng thời theo thư viện phù hợp |
| Số dư/tồn kho | Giao dịch hoặc cơ chế nhất quán theo nghiệp vụ |
| Cache | Key, tenant, phiên bản, invalidation và giới hạn dung lượng |

Đừng đưa xử lý concurrency vào cùng commit với đổi tên hàm. Nếu cần sửa lỗi race, hãy mô tả rõ behavior correction, thiết kế test và xem độ tin cậy khi tải thật.

## 11. Điều kiện thành công: kiểm tra gì ngoài test xanh?

Một refactor đạt mục tiêu khi:

- Hành vi được cam kết **không đổi** trong phạm vi đã xác định.
- Code mới có trách nhiệm và luồng dữ liệu **dễ nhận ra hơn**.
- Thay đổi nghiệp vụ sắp tới **ít phải chạm nơi không liên quan hơn**.
- Test **dễ đọc và có sức phát hiện lỗi**, không chỉ tăng số lượng.
- Không tạo thêm phụ thuộc vòng, state dùng chung hoặc API khó duy trì.
- Chi phí vận hành và hiệu năng không vượt ràng buộc.
- Có thể xác định mốc tốt và đường lui khi phát hiện hồi quy.

Các chỉ số như số dòng, Cyclomatic Complexity hoặc số class chỉ là **tín hiệu bổ sung**. Chia một method dài thành mười method vô nghĩa có thể giảm điểm đo cục bộ nhưng tăng thời gian điều hướng. Xóa nhiều dòng code có thể làm mất validation hoặc xử lý lỗi quan trọng.

### 11.1. Đo tác động phù hợp

| Mục tiêu refactor | Bằng chứng hữu ích |
| --- | --- |
| Cô lập logic miền khỏi I/O | Unit test chạy không cần DB; adapter có integration test riêng |
| Giảm coupling giữa module | Kiểm tra chiều phụ thuộc, số nơi sửa khi đổi một hợp đồng |
| Cải thiện khả năng đọc | Reviewer giải thích luồng và trách nhiệm không phải mở nhiều lớp vô ích |
| Dễ kiểm thử trường hợp biên | Test có expected nghiệp vụ đúng ở ngưỡng, lỗi và trạng thái thiếu |
| Giảm rủi ro sửa lỗi | Lỗi cũ có regression test, không phải chỉ thêm snapshot |
| Giữ tương thích | Contract test với consumer, test migration hoặc kiểm tra public API |
| Giảm rủi ro vận hành | Quan sát rollback, tỷ lệ lỗi, p95/p99 và dữ liệu sau rollout |

Đừng tự tuyên bố “refactor nhanh hơn 30%” nếu không có benchmark cùng workload. Với phần lớn refactor cấu trúc, **độ rõ trách nhiệm và khả năng thay đổi** mới là giá trị trực tiếp; hiệu năng phải có bằng chứng riêng.

## 12. Những điểm làm refactor khó hoàn tác

### 12.1. Thay đổi hợp đồng public trước khi chuyển consumer

Đổi tên field trong JSON hoặc đổi chữ ký SDK mà không có giai đoạn tương thích có thể buộc phải điều phối nhiều bên khi rollback.

**Cách giảm rủi ro:** giữ adapter tương thích, thêm phiên bản hợp đồng nếu cần, triển khai consumer trước producer theo chiến lược phù hợp và theo dõi mức sử dụng API cũ.

### 12.2. Thay đổi dữ liệu bền vững không đảo ngược

Xóa cột, gộp dữ liệu mất thông tin, đổi timezone không kiểm soát hoặc làm tròn tiền khi migration có thể khiến quay lại schema cũ không còn khả thi.

**Cách giảm rủi ro:** thiết kế giai đoạn chuyển đổi, backup/recovery theo chính sách, đối chiếu dữ liệu và kế hoạch ngừng dùng phiên bản cũ.

### 12.3. Trộn refactor và cập nhật phụ thuộc lớn

Đổi code, cập nhật Java runtime, đổi framework và nâng JDBC driver cùng lúc tạo nhiều nguồn hồi quy.

**Cách giảm rủi ro:** tách nâng dependency khỏi thay đổi cấu trúc khi có thể; dùng test tương thích và ghi thay đổi hành vi đã biết của thư viện.

### 12.4. Không có cách phân biệt lỗi trước và sau

Một bộ test đã flaky hoặc fail từ trước khiến nhóm không biết lỗi mới có do refactor không.

**Cách giảm rủi ro:** ghi baseline, sửa/đánh dấu test không ổn định theo quy trình, giữ kết quả test và cấu hình trước-sau để đối chiếu.

### 12.5. Đổi nhiều thành phần dùng chung một lúc

Một helper dùng rộng hoặc package core bị sửa đồng loạt có thể ảnh hưởng hàng chục module.

**Cách giảm rủi ro:** xác định consumers, tạo seam hoặc adapter, chuyển từng nhóm caller, và xác minh sau mỗi đợt.

## 13. Lựa chọn kỹ thuật refactor theo bước nhỏ

| Kỹ thuật | Dùng khi | Bước nhỏ đầu tiên | Cần giữ hoặc kiểm tra |
| --- | --- | --- | --- |
| **Rename Variable/Method** | Tên không nói đúng ý nghĩa | Đổi tên cục bộ với công cụ hỗ trợ | Public API, reflection, serialization |
| **Extract Method** | Đoạn logic có trách nhiệm rõ | Trích nguyên đoạn, chưa sửa công thức | Thứ tự chạy, ngoại lệ, biến mutable |
| **Inline Method/Class** | Tầng chỉ chuyển tiếp | Gộp nơi dùng ít nhất trước | Hợp đồng public hoặc hook runtime |
| **Move Method** | Logic nằm sai đối tượng | Đưa một phép tính thuần sang type phù hợp | Phụ thuộc và khả năng truy cập state |
| **Introduce Parameter Object** | Nhiều tham số cùng khái niệm | Thêm type, adapter caller cũ nếu cần | Nullability, validation, serialization |
| **Extract Interface / Port** | Ranh giới I/O thực sự cần tách | Định nghĩa hợp đồng hẹp theo use case | Lỗi tích hợp, transaction, lifecycle |
| **Replace Conditional with Polymorphism** | Có nhiều biến thể thật và độc lập | Tách một biến thể đã được test | Chọn đúng policy, cấu hình và fallback |
| **Split Phase** | Một hàm vừa chuẩn bị dữ liệu vừa tính/ghi | Tách rõ một giai đoạn dữ liệu | Thứ tự tác dụng phụ, snapshot, concurrency |
| **Strangler migration** | Thay một thành phần lớn từng phần | Chuyển một tuyến/luồng rõ ràng | Routing, state, compatibility, rollback |

Kỹ thuật không phải mục tiêu. Nếu dùng `Extract Interface` khiến xuất hiện nhiều layer không mang ý nghĩa, hoặc dùng polymorphism cho hai điều kiện nhỏ khiến code khó đọc hơn, đó có thể không phải cải thiện thực tế.

## 14. Kiểm soát phạm vi: biết khi nào nên dừng

Một điểm khó khi refactor là phát hiện “tiện tay” có nhiều vấn đề khác. Nếu đang tách tính giá khỏi báo cáo, nhóm có thể muốn:

- Đổi cách tính tiền từ `long` sang `BigDecimal`.
- Thêm nhiều loại tiền.
- Sửa tất cả tên package.
- Chuyển toàn bộ ứng dụng sang một framework DI mới.
- Đổi cách báo lỗi API.
- Viết lại SQL và thêm caching.

Những việc đó có thể hợp lý về dài hạn, nhưng mỗi việc là một **mục tiêu riêng** với rủi ro riêng. Hãy ghi chúng vào danh sách quyết định sau, không tự động gộp vào PR hiện tại.

Một quy tắc đơn giản:

> Nếu không thể diễn đạt thay đổi tiếp theo như một bước giữ cùng hợp đồng, dễ kiểm chứng và dễ hoàn tác, hãy **tạm dừng để tách yêu cầu hoặc lập kế hoạch mới**.

Cách này không cản trở cải tiến. Nó giữ cho tiến độ có mốc rõ, giúp nhóm ship giá trị mà không phải chờ một đợt viết lại lớn.

## 15. Mẫu kế hoạch refactor theo các checkpoint

Có thể dùng mẫu ngắn để đồng bộ giữa tác giả và reviewer:

~~~markdown
### REFACTOR-005 — <vùng mã và khó khăn cần giải quyết>

Mục tiêu:
- Vấn đề cấu trúc hiện tại:
- Điều gì phải dễ hơn sau refactor:
- Điều gì KHÔNG thay đổi về hành vi:

Phạm vi:
- Class/module và consumer liên quan:
- Public API, DB, event, config hoặc ranh giới quyền:
- Các giả thiết chưa xác minh:

Baseline:
- Commit/version và cấu hình:
- Unit/integration/contract tests đang chạy:
- Bug đã biết và test flaky:
- Cách tái hiện hành vi quan trọng:

Các bước nhỏ:
1. <bước một> — phép kiểm tra — cách quay lại
2. <bước hai> — phép kiểm tra — cách quay lại
3. <bước ba> — phép kiểm tra — cách quay lại

Checkpoint:
- Khi nào commit để có trạng thái xanh:
- Khi nào cần review hoặc test tích hợp:
- Nếu có rollback triển khai, artifact và dữ liệu có tương thích?

Tiêu chí hoàn thành:
- Bằng chứng hành vi được giữ:
- Bằng chứng cấu trúc cải thiện:
- Tác dụng phụ/hiệu năng/tài nguyên không xấu đi quá giới hạn:

Điều kiện dừng hoặc hoàn tác:
- Lỗi nào, chỉ số nào hoặc thay đổi hợp đồng nào kích hoạt?
- Người chịu trách nhiệm quyết định:

Công việc tách riêng:
- Bug fix, đổi yêu cầu, tối ưu hiệu năng hoặc migration cần PR khác:
~~~

Mẫu không cần áp dụng đầy đủ cho việc đổi tên biến private. Nó hữu ích khi refactor kéo qua nhiều lớp, nhiều người review hoặc có tác động triển khai.

## 16. Những ngộ nhận phổ biến

**“Refactor là làm cho mã chạy nhanh hơn.”** Không nhất thiết. Trọng tâm là cấu trúc và khả năng thay đổi, trong khi giữ hành vi theo hợp đồng. Tối ưu hiệu năng là mục tiêu riêng cần số đo.

**“Test xanh nghĩa là refactor an toàn tuyệt đối.”** Không. Test có thể thiếu dữ liệu biên, thiếu kiểm tra tác dụng phụ, hoặc chỉ chạy với mock. Cần lựa chọn bằng chứng theo rủi ro thật.

**“Bước nhỏ nghĩa là một dòng/commit.”** Không. Bước nhỏ là đơn vị có thể hiểu, kiểm tra và hoàn tác, không phải một giới hạn số dòng cứng.

**“Có Git thì rollback luôn dễ.”** Git hỗ trợ hoàn tác source code; nó không tự đảo ngược database, email, message, giao dịch hay API đã được bên khác dùng.

**“Muốn refactor thì phải sửa luôn mọi bug thấy được.”** Không. Cần ghi nhận và có thể ưu tiên sửa bug quan trọng, nhưng tách behavior correction khỏi structural change khi có thể để tránh lẫn bằng chứng.

**“Đổi class private chắc không ảnh hưởng bên ngoài.”** Chưa chắc. Reflection, dependency injection, serialization và cấu hình theo tên có thể tạo nơi dùng không hiện trong compile-time search.

**“Refactor lớn một lần sẽ tiết kiệm review.”** Có thể giảm số PR nhưng làm tăng kích thước diff, khó xác định lỗi và khó revert riêng một phần. Mức phù hợp phụ thuộc bối cảnh, không phải cứ nhiều thay đổi là tốt.

**“Characterization test luôn mô tả hành vi đúng.”** Nó chỉ mô tả hành vi hiện tại; cần phân biệt với oracle được xác nhận từ nghiệp vụ.

**“Mỗi lần tách method đều cải thiện chất lượng.”** Không. Tách thiếu tên và trách nhiệm có thể tăng chi phí điều hướng.

**“Feature flag bảo đảm hoàn tác trong một nút bấm.”** Không nếu đường mới đã tạo side effect hoặc schema mà đường cũ không hiểu.

**“Nếu phải dừng refactor giữa chừng là thất bại.”** Không. Một chuỗi checkpoint đã kiểm chứng cho phép nhóm dừng ở trạng thái tốt và tiếp tục sau, thay vì bị mắc kẹt trong nhánh không thể merge.

**“Có thể bỏ qua kiểm thử tích hợp nếu chỉ đổi cấu trúc.”** Không khi thay đổi tác động đến wiring, I/O, hợp đồng, transaction hoặc consumer ngoài.

## 17. Bài tập vận dụng

### Tình huống A — Refactor cùng bug fix

Một hàm báo giá dài đang dùng `>` thay vì `>=` ở ngưỡng miễn phí. Nhóm muốn vừa Extract Method vừa sửa điều kiện.

**Câu hỏi:** nên chia thế nào?

**Gợi ý:** xác nhận đặc tả và viết test biên tái hiện bug. Có thể sửa bug trong commit riêng rồi chạy lại bộ test; sau đó refactor trong các commit giữ hành vi đúng mới. Nếu thứ tự ngược lại cần thiết, phải ghi rõ test nào mô tả behavior cũ và khi nào behavior correction xảy ra. Không tuyên bố toàn bộ PR chỉ là refactor.

### Tình huống B — Bước refactor khó quay lui

Một PR đổi tên JSON field, xóa cột DB, chuyển adapter và viết lại handler. Khi triển khai, consumer cũ báo lỗi.

**Câu hỏi:** vì sao việc revert khó? Nên thiết kế lại thứ tự ra sao?

**Gợi ý:** thay đổi public contract và dữ liệu bền vững khiến artifact cũ có thể không tương thích. Nên tách giai đoạn schema expand, chuyển reader/writer có kiểm chứng, cập nhật consumer, đối chiếu dữ liệu rồi contract sau; có kế hoạch rollback theo từng giai đoạn.

### Tình huống C — Unit test qua nhưng wiring lỗi

Nhóm đưa logic sang `PricingPolicy` và test bằng `new PricingPolicy()`. Ứng dụng triển khai qua DI container lại báo thiếu bean.

**Câu hỏi:** bước nào còn thiếu bằng chứng?

**Gợi ý:** test lõi chỉ bảo vệ tính toán. Khi thay đổi cấu trúc DI, cần startup/wiring test hoặc integration test trong cấu hình thực. Có thể giữ adapter tương thích và chuyển wiring ở một bước riêng.

### Tình huống D — Tạo class mới nhưng không thay đổi dễ hơn

Một hàm 100 dòng bị chia thành 15 method đặt tên `step1`, `process`, `handle`, còn state mutable được truyền qua nhiều tham số.

**Câu hỏi:** đã đạt mục tiêu refactor chưa?

**Gợi ý:** số dòng mỗi method giảm chưa chứng minh trách nhiệm rõ. Hãy đánh giá tên, tính gắn kết, phụ thuộc, thời gian người mới hiểu và số nơi phải sửa cho một yêu cầu. Có thể cần nhóm theo khái niệm miền thay vì chia cơ học.

### Tình huống E — Đã tắt feature flag nhưng dữ liệu không tương thích

Đường xử lý mới ghi trường `amount_minor_units` và bỏ cập nhật trường cũ. Khi tắt flag, đường đọc cũ không có dữ liệu mới.

**Câu hỏi:** vì sao flag không tạo rollback an toàn?

**Gợi ý:** hành vi ghi bền vững đã thay đổi. Cần chiến lược tương thích dữ liệu, nguồn chuẩn, dual-write được kiểm soát nếu cần, test mixed-version và kế hoạch khôi phục/đối soát trước khi rollout.

### Tình huống F — Không có test đủ mạnh để bảo vệ code cũ

Một job nhập liệu không có unit test và phụ thuộc file, database và thời gian thực. Nhóm muốn tách logic kiểm tra dữ liệu.

**Câu hỏi:** bước nhỏ đầu tiên nên là gì?

**Gợi ý:** xác định hợp đồng đầu vào/đầu ra và lỗi, tạo fixture an toàn, thêm integration/characterization test cho một vài kịch bản trọng yếu, sau đó trích hàm kiểm tra dữ liệu thuần. Đừng mock mọi thứ đến mức test không xác nhận job thật hoạt động.

### Tình huống G — Thay đổi đã chia nhỏ nhưng test đều dùng expected sai

Nhóm refactor chính sách thuế thành nhiều bước, tất cả test đều qua vì expected được lấy từ mã cũ có bug. Khi chạy production vẫn tính sai.

**Câu hỏi:** vấn đề nằm ở kích thước bước hay bằng chứng?

**Gợi ý:** test bảo vệ tốt hành vi cũ nhưng oracle không được kiểm chứng từ đặc tả. Bước nhỏ giúp định vị thay đổi, nhưng không thay việc xác nhận hành vi đúng. Cần test theo quy tắc thuế và sửa bug như một thay đổi hành vi riêng.

## 18. Checklist trước, trong và sau refactor

### Trước khi bắt đầu

- **Mục tiêu:** vấn đề cấu trúc nào cần cải thiện, làm sao biết đã tốt hơn?
- **Hành vi:** những giá trị, lỗi, side effect và hợp đồng nào phải giữ?
- **Baseline:** test nào đang xanh, lỗi nào đã có sẵn và trên phiên bản nào?
- **Phạm vi:** code, module, public API, DI, database và consumer nào liên quan?
- **Rủi ro:** có dữ liệu, quyền, tiền, concurrency hoặc tính sẵn sàng cần bảo vệ?
- **Đường lui:** có thể revert commit, deploy artifact cũ và đọc dữ liệu mới không?

### Trong từng bước

- **Một lý do:** thay đổi có mục tiêu nhỏ, không trộn nhiều công việc?
- **Diff:** code review có hiểu rõ sự khác nhau và nơi hành vi được giữ?
- **Kiểm chứng:** compile, test, analysis và integration checks thích hợp đã chạy?
- **Checkpoint:** có trạng thái tốt để tiếp tục hoặc dừng?
- **Phạm vi:** có phát sinh thay đổi nghiệp vụ ngoài ý muốn?
- **Hoàn tác:** nếu bước này sai, có cách quay lại mà không xóa sửa lỗi/tính năng khác?

### Khi hoàn thành

- **Kết quả:** hành vi theo hợp đồng có được bảo vệ bởi test đủ mạnh?
- **Cấu trúc:** trách nhiệm, tên, phụ thuộc và khả năng đọc hiểu có cải thiện?
- **Tích hợp:** wiring, consumer ngoài, schema, transaction và security đã được xác nhận?
- **Triển khai:** rollback có thực sự tương thích với dữ liệu và message đã tạo?
- **Theo dõi:** có tín hiệu lỗi, độ trễ và tình trạng dùng đường cũ cần giám sát?
- **Dọn dẹp:** adapter tạm, flag và tài liệu cũ có chủ sở hữu, điều kiện xóa?
- **Lịch sử:** các commit có thể đọc hiểu, kiểm chứng và hoàn tác riêng khi cần?

## 19. Kết luận

**Refactor an toàn không phải là refactor không bao giờ có lỗi, mà là quá trình khiến sai lệch dễ bị phát hiện sớm, dễ khoanh vùng và có đường khôi phục đã được suy nghĩ trước.** Các bước nhỏ tạo điều kiện cho test, review và quyết định kỹ thuật cung cấp bằng chứng ngay tại thời điểm thay đổi.

Với mã thuần, điều đó thường là **giữ test đỏ/xanh có ý nghĩa, đổi một trách nhiệm mỗi lần và commit tại trạng thái tốt**. Với hệ thống đang chạy, còn phải xét **tính tương thích của API, dữ liệu, giao dịch và tác dụng phụ** — vì hoàn tác Git không đồng nghĩa hoàn tác thế giới bên ngoài.

Trong **CODE_QUALITY_FUNDAMENTALS**, thực hiện refactor từng bước nhỏ có thể kiểm tra và hoàn tác giúp mã **đáng tin cậy hơn nhờ có bằng chứng hồi quy, dễ hiểu hơn nhờ trách nhiệm tường minh và dễ thay đổi hơn nhờ không phải đánh cược toàn bộ hệ thống vào một lần viết lại**.
