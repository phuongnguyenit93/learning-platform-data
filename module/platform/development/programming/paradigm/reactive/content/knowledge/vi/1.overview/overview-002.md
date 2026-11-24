# Tổng quan

## Từ cập nhật thủ công đến lan truyền thay đổi qua quan hệ phụ thuộc

Trong một chương trình thông thường, khi dữ liệu thay đổi, lập trình viên thường phải tự tìm những giá trị liên quan và cập nhật chúng theo đúng thứ tự. Cách làm này phù hợp với quy trình nhỏ, nhưng trở nên khó duy trì khi một thay đổi ảnh hưởng đến nhiều phép tính, giao diện hoặc dịch vụ. Tư duy reactive chuyển trọng tâm sang việc mô tả quan hệ phụ thuộc: khi đầu vào thay đổi, các giá trị được tạo ra từ đầu vào đó được tính lại và tín hiệu mới tiếp tục lan đến những thành phần đang quan tâm.

Đây là một bước chuyển quan trọng trong lập trình phản ứng. Thay vì phải nhớ từng nơi cần cập nhật, ta xác định nguồn dữ liệu, các phép biến đổi phụ thuộc vào nguồn đó và nơi tiêu thụ kết quả. Trong hệ sinh thái Java, Project Reactor cung cấp các publisher và toán tử để biểu diễn những luồng thay đổi như vậy. Bản thân thư viện không tự dò tìm mọi biến trong chương trình; quan hệ cần thiết phải được mô hình hóa rõ ràng trong pipeline.

### 1. Vấn đề của việc cập nhật thủ công

Xét màn hình tóm tắt một đơn hàng. Tổng tiền phụ thuộc vào số lượng sản phẩm và đơn giá:

\[
\text{subtotal} = \text{quantity} \times \text{unitPrice}
\]

Nếu số lượng hoặc đơn giá thay đổi, tổng tiền phải được tính lại. Trong cách viết mệnh lệnh (imperative), chương trình thường cập nhật từng trường rồi gọi hàm tính toán:

~~~java
import java.math.BigDecimal;

final class OrderSummary {
    private int quantity;
    private BigDecimal unitPrice;
    private BigDecimal subtotal;

    void changeQuantity(int nextQuantity) {
        quantity = nextQuantity;
        recalculate();
    }

    void changeUnitPrice(BigDecimal nextUnitPrice) {
        unitPrice = nextUnitPrice;
        recalculate();
    }

    private void recalculate() {
        subtotal = unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Đoạn mã này có thể hoạt động tốt. Tuy nhiên, mỗi đường thay đổi dữ liệu phải nhớ gọi **recalculate()**. Khi thêm giảm giá, phí vận chuyển và thuế, hàm tính toán có thể dài hơn; khi thêm một đường cập nhật mới, lập trình viên phải nhớ gọi đúng các bước liên quan. Nếu một nhánh quên tính lại hoặc tính sai thứ tự, giao diện có thể hiển thị tổng tiền cũ trong khi số lượng đã thay đổi.

Một cách sửa thường thấy là tập trung mọi phép tính vào một hàm duy nhất. Điều đó giảm việc lặp công thức, nhưng chương trình vẫn phải chủ động gọi hàm ở mọi điểm có thể làm thay đổi đầu vào. Khi nhiều thành phần cùng quan tâm đến một giá trị, việc gọi cập nhật thủ công đến từng thành phần cũng dễ tạo ra sự phụ thuộc chặt chẽ.

### 2. Nhìn dữ liệu như một mạng lưới phụ thuộc

Thay vì xem các trường dữ liệu là những ô độc lập, ta mô tả giá trị nào được suy ra từ giá trị nào. Với đơn hàng, quan hệ có thể là:

~~~text
Số lượng ─────┐
              ├──> Tạm tính ───> Giảm giá ───┐
Đơn giá ──────┘                               ├──> Tổng thanh toán
Phương thức giao hàng ──> Phí vận chuyển ─────┘
~~~

Số lượng và đơn giá là dữ liệu đầu vào. Tạm tính được suy ra từ hai đầu vào; giảm giá phụ thuộc vào tạm tính và quy tắc khuyến mãi; tổng thanh toán phụ thuộc vào giảm giá và phí vận chuyển. Những đường nối biểu diễn quan hệ phụ thuộc (dependency).

Khi số lượng thay đổi, thay đổi có thể lan theo các cạnh đi ra từ nút số lượng: tạm tính được tính lại, quy tắc giảm giá được áp dụng lại, rồi tổng thanh toán được cập nhật. Khi phương thức giao hàng thay đổi, nhánh phí vận chuyển được tính lại và ảnh hưởng đến tổng thanh toán. Những nhánh không phụ thuộc vào dữ liệu vừa đổi không cần tính lại.

Trong một mô hình đơn giản, đồ thị phụ thuộc nên không có chu trình. Nếu A phụ thuộc B, B lại phụ thuộc C và C phụ thuộc A, chương trình không có thứ tự tính toán rõ ràng; việc thay đổi một giá trị có thể kích hoạt cập nhật lặp vô hạn. Các hệ thống reactive cần phát hiện, ngăn chu trình hoặc định nghĩa rõ ngữ nghĩa đặc biệt cho trường hợp đó.

### 3. Từ yêu cầu cập nhật đến cơ chế lan truyền

Một mô hình reactive thường có ba loại thành phần:

| Thành phần | Vai trò | Ví dụ trong đơn hàng |
| --- | --- | --- |
| Nguồn (source) | Phát ra thay đổi hoặc giá trị mới | Số lượng, đơn giá, phương thức giao hàng |
| Giá trị dẫn xuất (derived value) | Tính từ một hay nhiều nguồn khác | Tạm tính, giảm giá, phí vận chuyển |
| Thành phần quan sát (consumer) | Nhận kết quả để hiển thị hoặc thực hiện công việc | Màn hình thanh toán, dịch vụ tạo hóa đơn |

Khi một nguồn phát giá trị mới, thành phần phụ thuộc nhận được tín hiệu và thực hiện phép biến đổi đã khai báo. Kết quả mới lại trở thành đầu vào cho bước kế tiếp. Chuỗi đó tạo nên sự lan truyền thay đổi (change propagation).

Có thể hình dung quá trình này qua các bước:

1. Một nguồn phát ra giá trị mới, ví dụ số lượng đổi từ 2 thành 3.
2. Các phép tính trực tiếp phụ thuộc vào số lượng nhận biết thay đổi và tạo kết quả mới.
3. Những phép tính phụ thuộc vào kết quả vừa tạo tiếp tục chạy.
4. Các consumer nhận kết quả cuối để cập nhật giao diện, lưu dữ liệu hoặc gửi thông báo.

Điểm quan trọng là mỗi bước biết mình phụ thuộc vào dữ liệu nào. Nhờ vậy, logic tính toán có thể được ghép thành pipeline thay vì phải rải các lệnh cập nhật trên nhiều nhánh xử lý.

### 4. Observer và Publisher–Subscriber

Một cách triển khai quen thuộc của việc lan truyền thay đổi là Observer pattern. Đối tượng quan sát đăng ký với đối tượng phát sự kiện; khi trạng thái thay đổi, đối tượng phát thông báo cho các observer. Mô hình này tách nơi phát thay đổi khỏi nơi phản ứng với thay đổi.

Reactive Streams mở rộng tư tưởng truyền tín hiệu đó cho luồng dữ liệu bất đồng bộ. Publisher phát các tín hiệu theo hợp đồng; Subscriber nhận đăng ký, yêu cầu số phần tử muốn tiêu thụ và xử lý phần tử, lỗi hoặc hoàn tất. Subscription cho phép subscriber yêu cầu thêm dữ liệu hoặc hủy đăng ký. Cơ chế yêu cầu dữ liệu là nền tảng cho backpressure khi bên tiêu thụ xử lý chậm.

Observer đơn giản thường thông báo rằng một đối tượng đã thay đổi; observer có thể phải đọc lại trạng thái để biết giá trị mới. Một publisher trong Reactive Streams phát trực tiếp các phần tử theo thời gian và tuân theo giao thức tín hiệu. Với Project Reactor, ta thường biểu diễn nguồn và các phép biến đổi bằng **Mono** hoặc **Flux**, sau đó kết nối chúng bằng các toán tử.

Không nên hiểu rằng cứ dùng Publisher–Subscriber là toàn bộ đối tượng Java tự động trở nên reactive. Một trường thông thường như **order.quantity** không tự phát sự kiện khi bị gán giá trị mới. Ta cần đưa thay đổi vào một nguồn có thể quan sát, hoặc dùng một cơ chế quản lý trạng thái có hỗ trợ thông báo thay đổi.

### 5. Mô hình hóa quan hệ phụ thuộc bằng Reactor

Giả sử hệ thống nhận được hai luồng cập nhật: số lượng và đơn giá. Khi cả hai nguồn đã phát ít nhất một giá trị, mỗi lần một nguồn phát giá trị mới, ta muốn tạo lại bản tóm tắt đơn hàng từ giá trị mới nhất của cả hai nguồn.

**Flux.combineLatest** phù hợp với quan hệ này. Toán tử giữ giá trị gần nhất của mỗi nguồn và gọi hàm kết hợp khi có cập nhật mới:

~~~java
import java.math.BigDecimal;

import reactor.core.publisher.Flux;

record OrderAmounts(
    BigDecimal subtotal,
    BigDecimal shipping,
    BigDecimal total
) {}

Flux<Integer> quantityUpdates = getQuantityUpdates();
Flux<BigDecimal> unitPriceUpdates = getUnitPriceUpdates();

Flux<OrderAmounts> orderAmounts =
    Flux.combineLatest(
        quantityUpdates,
        unitPriceUpdates,
        (quantity, unitPrice) -> {
            BigDecimal subtotal =
                unitPrice.multiply(BigDecimal.valueOf(quantity));
            BigDecimal shipping =
                subtotal.compareTo(new BigDecimal("500.00")) >= 0
                    ? BigDecimal.ZERO
                    : new BigDecimal("30.00");
            BigDecimal total = subtotal.add(shipping);

            return new OrderAmounts(subtotal, shipping, total);
        }
    );

orderAmounts.subscribe(System.out::println);
~~~

Trong ví dụ, **getQuantityUpdates()** và **getUnitPriceUpdates()** đại diện cho các phương thức trả về publisher từ nguồn dữ liệu thực tế. Chúng cần phát giá trị ban đầu để **combineLatest** có đủ dữ liệu tính kết quả đầu tiên. Sau đó, khi số lượng hoặc đơn giá thay đổi, toán tử dùng giá trị mới nhất của nguồn vừa đổi cùng giá trị gần nhất của nguồn còn lại để tạo **OrderAmounts** mới.

Quan hệ phụ thuộc được thể hiện ngay trong pipeline: kết quả đơn hàng phụ thuộc đồng thời vào số lượng và đơn giá. Phí giao hàng và tổng tiền được tính từ tạm tính. Nếu thêm một quy tắc mới, ta có thể tách phép tính thành một bước **map** riêng hoặc kết hợp thêm một publisher, tùy cấu trúc nghiệp vụ.

Ví dụ trên minh họa cách mô hình hóa luồng. Trong ứng dụng thực tế, cần xác định cách nguồn cung cấp giá trị ban đầu, cách xử lý lỗi và thời điểm hoàn tất. Nếu chỉ có một nguồn phát dữ liệu mà không phát giá trị nào, **combineLatest** chưa thể tạo kết quả. Khi một nguồn hoàn tất sau khi đã phát giá trị, giá trị cuối của nguồn đó vẫn có thể được dùng để kết hợp với những cập nhật tiếp theo của nguồn còn lại.

### 6. Push, pull và thời điểm tính lại

Có hai cách phổ biến để lấy giá trị dẫn xuất:

- **Pull:** khi consumer cần kết quả, nó chủ động đọc đầu vào và tính giá trị tại thời điểm đó. Cách này phù hợp khi việc tính toán rẻ và không cần giữ kết quả cập nhật liên tục.
- **Push:** khi đầu vào thay đổi, nguồn phát tín hiệu đến các bước phụ thuộc để chúng tính lại và chuyển kết quả mới. Cách này phù hợp khi nhiều consumer cần được thông báo ngay khi có thay đổi.

Nhiều hệ thống kết hợp cả hai. Nguồn có thể đẩy thông báo thay đổi, còn consumer chỉ đọc hoặc truy vấn chi tiết khi cần. Chọn mô hình nào phụ thuộc vào tần suất thay đổi, chi phí tính toán, độ trễ mong muốn và số lượng consumer.

Trong Reactor, các toán tử biến đổi luồng thường được thực thi khi có tín hiệu đi qua. Việc khai báo pipeline không nhất thiết đồng nghĩa công việc đã chạy; với các nguồn lạnh, subscription kích hoạt quá trình tiêu thụ. Các consumer cũng có thể đăng ký độc lập, vì vậy cần suy nghĩ về việc mỗi subscription có tạo lại tác vụ hoặc truy vấn nguồn hay không.

### 7. Giữ kết quả nhất quán khi nhiều đầu vào cùng thay đổi

Lan truyền thay đổi cần có quy tắc rõ ràng về tính nhất quán. Giả sử số lượng và đơn giá cùng được cập nhật trong một thao tác nghiệp vụ. Nếu chúng được phát thành hai sự kiện riêng, **combineLatest** có thể tạo một kết quả trung gian từ số lượng mới và đơn giá cũ, rồi tạo kết quả khác khi đơn giá mới đến. Kết quả trung gian đó có thể hợp lệ với luồng sự kiện, nhưng không phù hợp nếu nghiệp vụ yêu cầu hai trường phải thay đổi nguyên tử.

Khi nhiều trường tạo thành một đơn vị cập nhật, hãy cân nhắc phát một đối tượng tổng hợp thay vì phát từng trường độc lập:

~~~java
record OrderInput(int quantity, BigDecimal unitPrice) {}

Flux<OrderInput> orderInputUpdates = getOrderInputUpdates();

Flux<OrderAmounts> orderAmounts =
    orderInputUpdates.map(input -> {
        BigDecimal subtotal =
            input.unitPrice().multiply(BigDecimal.valueOf(input.quantity()));
        BigDecimal shipping =
            subtotal.compareTo(new BigDecimal("500.00")) >= 0
                ? BigDecimal.ZERO
                : new BigDecimal("30.00");
        return new OrderAmounts(
            subtotal,
            shipping,
            subtotal.add(shipping)
        );
    });
~~~

Mỗi phần tử **OrderInput** chứa một bộ giá trị nhất quán. Khi một sự kiện đến, pipeline tính kết quả từ đúng bộ dữ liệu đó, tránh phát các trạng thái trung gian do cập nhật từng trường. Trong hệ thống có giao dịch hoặc phiên bản dữ liệu, có thể bổ sung mã phiên bản, thời điểm hiệu lực hoặc định danh giao dịch để consumer kiểm tra thứ tự và tính nhất quán.

Ngoài ra, cần chú ý đến:

- **Chu trình phụ thuộc:** tránh để kết quả dẫn xuất quay lại làm thay đổi chính nguồn tạo ra nó mà không có quy tắc dừng rõ ràng.
- **Cập nhật trùng:** nếu nguồn phát lại cùng một giá trị, cân nhắc toán tử như **distinctUntilChanged** khi việc bỏ giá trị lặp là đúng với nghiệp vụ.
- **Tác dụng phụ:** nên giữ các bước tính toán thuần (pure transformation) khi có thể; đặt thao tác ghi dữ liệu hoặc gửi thông báo ở vị trí có chủ đích.
- **Nhu cầu tiêu thụ:** nếu consumer chậm, cần chọn chiến lược backpressure phù hợp với ý nghĩa dữ liệu và giới hạn tài nguyên.
- **Vòng đời:** hủy subscription khi consumer không còn cần dữ liệu để tránh tiếp tục xử lý hoặc giữ tài nguyên không cần thiết.

### 8. Khi nào mô hình lan truyền thay đổi có ích?

Mô hình này hữu ích khi nhiều kết quả phụ thuộc vào một tập đầu vào thường xuyên thay đổi: bảng điều khiển cập nhật theo sự kiện, giá đơn hàng được tính từ nhiều thành phần, trạng thái quy trình được tổng hợp từ các bước, hoặc dịch vụ cần phản ứng với dữ liệu đến từ nhiều nguồn.

Trước khi thiết kế pipeline, hãy xác định nguồn dữ liệu nào là dữ liệu gốc, giá trị nào chỉ là kết quả dẫn xuất, consumer nào cần nhận thay đổi và những cập nhật nào phải được xem là một đơn vị nhất quán. Sau đó, chọn cách kết hợp luồng và chính sách tiêu thụ phù hợp. Nếu dữ liệu ít thay đổi và chỉ có một nơi sử dụng, cập nhật trực tiếp có thể đơn giản hơn; nếu nhiều thành phần cần phản ứng theo thời gian, quan hệ phụ thuộc tường minh giúp hệ thống dễ mở rộng và kiểm soát hơn.

Đây là nền tảng để tiếp tục học cách kết hợp nhiều publisher bằng toán tử, điều phối việc thực thi trên scheduler, xử lý lỗi trong pipeline và kiểm thử sự lan truyền tín hiệu trong Project Reactor.
