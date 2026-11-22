# Cân bằng các nguyên tắc với độ phức tạp thực tế

**Phạm vi:** OOP — SOLID trong Java.  
**Mục tiêu:** biết khi nào nên áp dụng một nguyên tắc thiết kế, áp dụng đến mức nào và khi nào nên giữ giải pháp đơn giản để hệ thống dễ hiểu, dễ kiểm thử và dễ thay đổi.

SOLID là năm nguyên tắc định hướng thiết kế hướng đối tượng, không phải bộ luật bắt mọi lớp, mọi phương thức đều đi qua interface, inheritance và dependency injection. Một thiết kế tốt phải giải quyết nhu cầu đang tồn tại, đồng thời giữ chi phí thay đổi trong tương lai ở mức hợp lý. Đôi khi đó là một lớp ngắn với vài nhánh điều kiện; đôi khi là các abstraction độc lập.

## 1. Tại sao áp dụng SOLID quá mức lại phản tác dụng?

Các nguyên tắc nhắc ta quản lý các **phụ thuộc** và **lý do thay đổi**:

| Nguyên tắc | Câu hỏi cần hỏi | Dấu hiệu áp dụng quá mức |
| --- | --- | --- |
| **SRP — Single Responsibility** | Module có tập trung vào một trách nhiệm, một nhóm lý do thay đổi nhất quán không? | Tách mỗi hàm thành một lớp, khiến một luồng nghiệp vụ đơn giản phải đi qua nhiều lớp trung gian. |
| **OCP — Open/Closed** | Có điểm biến thiên ổn định nào cần mở rộng mà ít sửa mã đã kiểm chứng không? | Tạo Strategy/Factory/Plugin cho mọi nhánh giả định chưa có yêu cầu thực tế. |
| **LSP — Liskov Substitution** | Mọi implementation có thực hiện đúng hợp đồng và bất biến mà client kỳ vọng không? | Dùng kế thừa chỉ để tái sử dụng mã dù subtype phải từ chối những thao tác của base type. |
| **ISP — Interface Segregation** | Client có bị ép phụ thuộc vào năng lực không sử dụng không? | Tách interface thành vô số loại một phương thức khi tất cả client luôn dùng cùng một nhóm thao tác. |
| **DIP — Dependency Inversion** | Logic quan trọng có phụ thuộc quá sâu vào chi tiết dễ đổi (database, HTTP, nhà cung cấp) không? | Bọc tất cả các lớp đơn giản bằng một interface tương ứng và cấu hình DI dù chỉ có một luồng không cần hoán đổi. |

**Tách trách nhiệm** không có nghĩa là “mỗi lớp chỉ được có một phương thức”. **Mở để mở rộng** không có nghĩa là “không bao giờ sửa một lớp”. **Lập trình hướng abstraction** không có nghĩa là “mọi lớp đều phải có interface”.

Một abstraction luôn có chi phí: đặt tên, tạo thêm điểm chuyển hướng khi đọc mã, quản lý dependency, duy trì hợp đồng công khai, điều hướng IDE, bảo trì mock/fake và giải thích cho đồng đội. Chi phí đó chỉ đáng trả khi nó làm giảm đáng kể chi phí thay đổi hoặc kiểm thử.

## 2. Bắt đầu từ trường hợp đơn giản thật sự

Giả sử phiên bản đầu tiên của cửa hàng **chỉ** có giao hàng tiêu chuẩn:

- Phí giao hàng: **30.000 VND**.
- Đơn hàng từ **500.000 VND** được miễn phí giao hàng.
- Chưa có API bên thứ ba, không có các gói giao hàng khác.
- Giá trị tiền là số nguyên VND để tránh lỗi làm tròn kiểu dấu phẩy động.

Trong tình huống này, một lớp có thể là thiết kế phù hợp:

~~~java
final class SimpleCheckout {
    long totalVnd(long goodsTotalVnd) {
        if (goodsTotalVnd < 0) {
            throw new IllegalArgumentException("Tổng tiền hàng không hợp lệ");
        }

        long shippingFee = goodsTotalVnd >= 500_000L ? 0L : 30_000L;
        return Math.addExact(goodsTotalVnd, shippingFee);
    }
}
~~~

Đoạn mã ngắn, có quy tắc rõ ràng, dễ debug và dễ kiểm thử. Tạo ngay **FeePolicy**, **PolicyFactory**, **PolicyRegistry** và một hệ thống cấu hình động chỉ vì “sau này *có thể* thêm gói giao hàng” sẽ khiến phần mềm phức tạp hơn khi chưa có bằng chứng về lợi ích.

Nếu các quy tắc còn ít và ổn định, một vài nhánh **if/switch** đơn giản, kiểm thử được, hoàn toàn có thể là lựa chọn tốt. Khi nhu cầu thật sự mở rộng, refactor dựa trên hành vi đã được kiểm chứng.

## 3. Khi yêu cầu thay đổi, thiết kế cũng cần tiến hóa

Sáu tháng sau, bài toán khác đi:

- Có thêm giao hàng **Express**, phí cơ bản 50.000 VND cộng 5.000 VND cho mỗi kilogram, phần lẻ kilogram làm tròn lên.
- Giao hàng **Standard** vẫn miễn phí khi tổng tiền hàng từ 500.000 VND.
- Hai chính sách do hai nhóm nghiệp vụ phụ trách và thay đổi độc lập.
- Hệ thống có thể kết nối thêm chính sách giao hàng mới qua cấu hình.

Lúc này các *quy tắc thực sự thay đổi độc lập* là lý do thực tế để tách một abstraction. Cách tiếp cận có thể như sau:

~~~mermaid
flowchart TD
    A["Checkout cần tính phí"] --> B["DeliveryFeePolicy (hợp đồng)"]
    B --> C["StandardFeePolicy"]
    B --> D["ExpressFeePolicy"]
    E["Cấu hình chế độ giao hàng"] --> F["Bảng chọn policy"]
    F --> A
~~~

### Ví dụ Java 17+ hoàn chỉnh

Lưu thành **DeliveryDemo.java**. Ví dụ dùng **record**, **enum** và **Map** để giữ cho mô hình nhỏ nhưng có thể thay đổi chính sách độc lập.

~~~java
import java.util.Map;
import java.util.Objects;

public class DeliveryDemo {
    enum DeliveryMode {
        STANDARD, EXPRESS
    }

    record Order(long goodsTotalVnd, long weightGrams) {
        Order {
            if (goodsTotalVnd < 0 || weightGrams < 0) {
                throw new IllegalArgumentException(
                        "Tiền hàng và khối lượng phải không âm");
            }
        }
    }

    record Receipt(
            long goodsTotalVnd,
            long deliveryFeeVnd,
            long grandTotalVnd
    ) {}

    // Abstraction nhỏ: một chính sách chịu trách nhiệm tính phí.
    interface DeliveryFeePolicy {
        long calculateFeeVnd(Order order);
    }

    static final class StandardFeePolicy implements DeliveryFeePolicy {
        @Override
        public long calculateFeeVnd(Order order) {
            return order.goodsTotalVnd() >= 500_000L
                    ? 0L : 30_000L;
        }
    }

    static final class ExpressFeePolicy implements DeliveryFeePolicy {
        @Override
        public long calculateFeeVnd(Order order) {
            // Phần lẻ kilogram được tính thành một kilogram đầy đủ.
            long grams = order.weightGrams();
            // Ceil(grams / 1000) mà không cộng 999 gây overflow long.
            long kilograms = grams / 1_000L
                    + (grams % 1_000L == 0 ? 0 : 1);
            long weightSurchargeVnd = Math.multiplyExact(kilograms, 5_000L);
            return Math.addExact(50_000L, weightSurchargeVnd);
        }
    }

    static final class Checkout {
        private final Map<DeliveryMode, DeliveryFeePolicy> policies;

        Checkout(Map<DeliveryMode, DeliveryFeePolicy> policies) {
            this.policies = Map.copyOf(
                    Objects.requireNonNull(policies));
        }

        Receipt price(Order order, DeliveryMode mode) {
            Objects.requireNonNull(order, "order");
            Objects.requireNonNull(mode, "mode");

            DeliveryFeePolicy policy = policies.get(mode);
            if (policy == null) {
                throw new IllegalArgumentException(
                        "Chưa cấu hình chính sách cho: " + mode);
            }

            long fee = policy.calculateFeeVnd(order);
            if (fee < 0) {
                throw new IllegalStateException(
                        "Chính sách trả về phí âm");
            }

            long total = Math.addExact(order.goodsTotalVnd(), fee);
            return new Receipt(order.goodsTotalVnd(), fee, total);
        }
    }

    public static void main(String[] args) {
        Checkout checkout = new Checkout(Map.of(
                DeliveryMode.STANDARD, new StandardFeePolicy(),
                DeliveryMode.EXPRESS, new ExpressFeePolicy()
        ));

        Order order = new Order(600_000L, 1_500L);
        System.out.println(checkout.price(order, DeliveryMode.STANDARD));
        System.out.println(checkout.price(order, DeliveryMode.EXPRESS));
    }
}
~~~

Chạy:

~~~bash
javac DeliveryDemo.java
java DeliveryDemo
~~~

Kết quả:

~~~text
Receipt[goodsTotalVnd=600000, deliveryFeeVnd=0, grandTotalVnd=600000]
Receipt[goodsTotalVnd=600000, deliveryFeeVnd=60000, grandTotalVnd=660000]
~~~

Ở thiết kế này:

1. **SRP:** mỗi policy chứa quy tắc tính phí thuộc một chế độ; **Checkout** điều phối lựa chọn chính sách và tính tổng.
2. **OCP:** có thể bổ sung implementation chính sách mới mà không sửa mã tính tổng trong **Checkout**. Việc khai báo chế độ mới trong **DeliveryMode**, cập nhật cấu hình và các thành phần liên quan vẫn có thể cần sửa — OCP không có nghĩa hệ thống hoàn toàn bất biến khi thêm tính năng.
3. **LSP:** các policy cần thực hiện hợp đồng nhất quán: trả về phí hợp lệ, không âm cho đơn hàng hợp lệ, và không tự ý thay đổi đối tượng đơn hàng. Nếu một policy báo thành công giả hoặc âm phí, việc thay thế policy trở nên không an toàn.
4. **ISP:** **Checkout** chỉ cần khả năng **calculateFeeVnd**. Không bắt mọi policy triển khai các thao tác như gửi email, xuất hóa đơn hoặc lưu database.
5. **DIP:** **Checkout** phụ thuộc vào **DeliveryFeePolicy** thay vì phụ thuộc trực tiếp vào **StandardFeePolicy** hay **ExpressFeePolicy**. Phần cấu hình ở **main** (composition root) quyết định implementation nào được cấp vào.

**Giới hạn có chủ ý:** dùng **enum** và registry đơn giản đủ cho hai chế độ trong ví dụ. Nếu nhu cầu thực tế chỉ có hai nhánh rất ổn định, **switch** rõ ràng vẫn có thể rẻ hơn hai class policy và bộ registry. Abstraction này trở nên đáng giá khi các chính sách phát triển, kiểm thử và được thay thế độc lập.

## 4. Kiểm thử điều gì để việc tách lớp có giá trị?

Kiểm thử **hành vi có ý nghĩa**, không kiểm tra nội bộ chỉ để chứng minh thiết kế gồm bao nhiêu lớp. Với JUnit Jupiter (JUnit 5), các trường hợp sau bắt các ranh giới nghiệp vụ và phép tính:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import org.junit.jupiter.api.Test;

class DeliveryDemoTest {
    @Test
    void standardMiễnPhíKhiĐạtNgưỡng() {
        var checkout = new DeliveryDemo.Checkout(Map.of(
                DeliveryDemo.DeliveryMode.STANDARD,
                new DeliveryDemo.StandardFeePolicy()));

        var result = checkout.price(
                new DeliveryDemo.Order(500_000L, 1_800L),
                DeliveryDemo.DeliveryMode.STANDARD);

        assertEquals(0L, result.deliveryFeeVnd());
        assertEquals(500_000L, result.grandTotalVnd());
    }

    @Test
    void expressLàmTrònLênTheoKilogram() {
        var policy = new DeliveryDemo.ExpressFeePolicy();

        assertEquals(50_000L, policy.calculateFeeVnd(
                new DeliveryDemo.Order(100_000L, 0L)));
        assertEquals(55_000L, policy.calculateFeeVnd(
                new DeliveryDemo.Order(100_000L, 1L)));
        assertEquals(60_000L, policy.calculateFeeVnd(
                new DeliveryDemo.Order(100_000L, 1_001L)));
        // Với khối lượng cực lớn, phí tràn long phải báo lỗi,
        // không tạo ra số kilogram âm do phép cộng bị overflow.
        assertThrows(ArithmeticException.class, () ->
                policy.calculateFeeVnd(
                        new DeliveryDemo.Order(100_000L, Long.MAX_VALUE)));
    }

    @Test
    void chưaCấuHìnhPolicyPhảiBáoLỗiRõRàng() {
        var checkout = new DeliveryDemo.Checkout(Map.of());

        assertThrows(IllegalArgumentException.class, () ->
                checkout.price(
                        new DeliveryDemo.Order(50_000L, 100L),
                        DeliveryDemo.DeliveryMode.EXPRESS));
    }
}
~~~

**Chú ý:** test trên cần JUnit Jupiter có trong classpath của dự án. Quy tắc làm tròn trong ví dụ là giả định nghiệp vụ minh họa. Nếu nhà vận chuyển quy định khối lượng tối thiểu một kilogram, trọng lượng quy đổi, làm tròn tiền hay phụ phí vùng miền, phải sửa đặc tả và test tương ứng trước khi sửa implementation.

Có thể truyền một fake **DeliveryFeePolicy** cho **Checkout** để kiểm tra việc cộng tổng mà không cần gọi dịch vụ vận chuyển thật. Tuy nhiên, nếu toàn bộ logic chỉ là một công thức ổn định, test trực tiếp hàm thuần túy có thể đủ; không cần tạo interface chỉ vì muốn dùng mock.

## 5. Quyết định giữa sự đơn giản và khả năng mở rộng

Một kỹ thuật thiết kế chỉ có ý nghĩa khi giải quyết *áp lực thay đổi cụ thể*. Có thể dùng bảng sau khi review:

| Tình huống thực tế | Cách tiếp cận cân nhắc | Vì sao |
| --- | --- | --- |
| Một quy tắc nhỏ, ít thay đổi | Hàm thuần hoặc một lớp đơn giản | Ít khái niệm, dễ đọc và test. |
| Hai biến thể với điều kiện ngắn, ổn định | **if/switch** rõ ràng, có test | Tổng chi phí có thể thấp hơn Strategy/Factory. |
| Nhiều thuật toán cùng vai trò, thay đổi độc lập | **Strategy** hoặc policy interface | Giới hạn tác động của thay đổi và test từng thuật toán. |
| Logic nghiệp vụ quan trọng gọi database/HTTP dễ thay thế | Port/repository interface ở ranh giới phù hợp | Giảm phụ thuộc vào hạ tầng; test nghiệp vụ độc lập. |
| Client đọc và client ghi có nhu cầu khác nhau | Tách interface đọc/ghi nếu cần | Tránh ép client phụ thuộc vào thao tác không dùng. |
| Một lớp vừa tính giá vừa gửi email, truy cập DB, render PDF | Tách những trách nhiệm có lý do thay đổi khác nhau | Cô lập lỗi và tác động của thay đổi. |
| Kế thừa khiến subclass phải ném **UnsupportedOperationException** | Xem lại subtype; ưu tiên composition/hợp đồng phù hợp | Giữ đúng cam kết hành vi với client. |
| Tạo nhiều tầng interface cho một mô hình bất biến nhỏ | Gộp/loại bỏ lớp trung gian không có giá trị | Giảm độ sâu khi đọc mã và chi phí đồng bộ thay đổi. |

Đừng chọn chỉ bằng **số dòng**, **số class** hay **số interface**. Một module nhiều dòng nhưng mạch lạc có thể tốt hơn một mô hình phân lớp sâu buộc người đọc mở 12 file để hiểu một phép tính.

### Câu hỏi trước khi tạo abstraction

- **Ai là client?** Những client nào cần tập thao tác hoặc quy tắc khác nhau?
- **Điều gì thật sự biến thiên?** Có hai hoặc nhiều trường hợp hiện hữu, yêu cầu đã được xác nhận, hoặc thay đổi lặp lại không?
- **Ranh giới ở đâu?** Thay đổi nghiệp vụ có độc lập với database, giao thức, UI, nhà cung cấp không?
- **Có quy ước chung không?** Các implementation có tuân thủ cùng một hợp đồng hành vi hay chỉ tình cờ trùng tên?
- **Chi phí của cách đơn giản là gì?** Thêm một biến thể đòi sửa bao nhiêu chỗ, có bao nhiêu test hồi quy chịu ảnh hưởng?
- **Chi phí của abstraction là gì?** Thêm bao nhiêu kiểu, cấu hình DI, cách chọn implementation, API versioning và rủi ro khó đọc?

**Ngưỡng thay đổi không thể được quyết định bằng một con số cố định.** Quy tắc “đợi ba trường hợp mới trừu tượng hóa” có thể hữu ích như lời nhắc chống thiết kế trước quá xa, nhưng không phải quy luật. Một ranh giới liên quan thanh toán, pháp lý hoặc tích hợp ngoài có thể đáng tách ngay vì tính độc lập và rủi ro thay đổi đã rõ.

## 6. Ba dạng phức tạp cần nhận diện

### 6.1. Phức tạp vốn có của nghiệp vụ

Ví dụ: giao hàng phụ thuộc khoảng cách, cân nặng, giờ cao điểm, vùng địa lý, điều kiện miễn phí và quy tắc hoàn tiền. Những điều này không thể biến mất bằng mẫu thiết kế. Công việc của ta là biểu diễn chúng thành quy tắc minh bạch và có test.

### 6.2. Phức tạp do cách triển khai

Ví dụ: cùng công thức nằm trong controller, service, repository và frontend, hoặc một client phải gọi qua năm adapter không thêm ý nghĩa. Có thể giảm bằng cách gom quy tắc vào một chỗ, tách phụ thuộc ở đúng ranh giới và bỏ tầng trung gian thừa.

### 6.3. Phức tạp để dự phòng tương lai

Ví dụ: hỗ trợ động hàng trăm plugin giao hàng trước khi dự án có nhà vận chuyển thứ hai. Đây là nơi cần xem xét **YAGNI** (*You Aren't Gonna Need It*) và trì hoãn quyết định có thể đảo ngược. Tuy vậy, trì hoãn thiết kế không có nghĩa bỏ qua lỗi kiến trúc đã biết; nếu thay đổi sau này gây rủi ro lớn hoặc mất tương thích dữ liệu, có thể cần đầu tư sớm.

**KISS** (*Keep It Simple*) khuyên chọn giải pháp đơn giản đáp ứng yêu cầu. **DRY** (*Don't Repeat Yourself*) khuyên tránh lặp lại tri thức/quy tắc có nguy cơ sai khác; không yêu cầu gộp mọi đoạn mã giống nhau về cú pháp. Gộp hai quy tắc trông giống nhưng khác chủ sở hữu nghiệp vụ có thể tạo coupling nguy hiểm.

## 7. Đo mức độ tốt của thiết kế bằng hậu quả thay đổi

Thay vì hỏi “đã dùng đủ năm chữ SOLID chưa?”, hãy kiểm tra bằng các tình huống thay đổi đại diện.

| Tín hiệu | Cách quan sát | Diễn giải thận trọng |
| --- | --- | --- |
| **Change surface** | Một yêu cầu nhỏ phải sửa bao nhiêu module và hợp đồng công khai? | Sửa nhiều nơi không tự động xấu, nhưng có thể chỉ ra coupling không cần thiết. |
| **Khả năng kiểm thử** | Viết test tình huống lỗi/biên có cần dựng quá nhiều hạ tầng không? | Dễ test thường phản ánh ranh giới tốt; mock quá nhiều có thể che thiết kế khó hiểu. |
| **Độ dễ đọc** | Một người mới có lần theo đường đi của dữ liệu và business rule nhanh không? | Nhiều tầng chuyển tiếp không đóng góp logic là chi phí nhận thức. |
| **Tính thay thế** | Thay adapter, phương thức thanh toán hay policy có giữ được hợp đồng không? | Tính mở rộng chỉ có giá trị khi điểm biến thiên là thật. |
| **Rủi ro hồi quy** | Sau thay đổi, test nào chứng minh behavior cũ và behavior mới? | Thiết kế tốt đi cùng đặc tả và kiểm thử, không thay thế chúng. |
| **Chi phí vận hành** | Có tăng cấu hình, quản trị dependency, khởi tạo bean, tracing/debug không? | Mẫu thiết kế có thể chuyển chi phí từ code sang cấu hình và vận hành. |

Không có điểm số tuyệt đối cho mọi dự án. Mức độ cần phân tách của thư viện public dùng bởi nhiều nhóm thường khác với script nội bộ dùng một lần.

## 8. Refactor theo bằng chứng, không theo phong trào

Một lộ trình có kiểm soát:

1. **Ghi rõ hành vi hiện tại** và bảo vệ bằng test các ca chính, ca biên và lỗi.
2. **Chỉ ra lý do thay đổi đã quan sát được**: hai rule có lịch phát hành khác nhau, DB adapter thường xuyên đổi, hoặc một client đang gánh thao tác không dùng.
3. **Chọn ranh giới hẹp nhất** thực sự giúp thay đổi dễ hơn; đặt tên theo domain, không chỉ thêm hậu tố **Manager**, **Processor**, **Factory**.
4. **Refactor từng bước nhỏ**, giữ nguyên kết quả nghiệp vụ ở các đầu vào cũ; chạy test sau mỗi bước có tác động.
5. **Thêm biến thể mới** qua hợp đồng vừa được ổn định, kiểm tra rằng logic cũ không cần sửa lan rộng.
6. **Dọn lớp/adapter cũ đã hết nhiệm vụ** nếu không còn client phụ thuộc; với public API phải có kế hoạch tương thích và chuyển đổi.

Trong Java/Spring, dependency injection giúp đưa implementation vào constructor, nhưng DI container không thay việc xác định ranh giới. Không cần đưa một giá trị hoặc helper thuần túy vào Spring bean chỉ để “tuân thủ DIP”. Interface thường hữu ích ở chỗ có nhiều implementation, có ranh giới hạ tầng, có hợp đồng công khai cần ổn định hoặc có nhiều client với nhu cầu khác nhau.

### Các lỗi cần tránh khi review

- **Speculative generality:** thêm cơ chế đăng ký plugin, override nhiều tầng hoặc generic phức tạp khi chưa có yêu cầu.
- **Premature optimization:** tối ưu hoặc thay cấu trúc trước khi đo vấn đề hiệu năng thực tế.
- **Shotgun surgery:** sửa một rule nhỏ phải chạm nhiều module không liên quan.
- **Feature envy/God class:** một lớp đọc và thao túng trạng thái của quá nhiều lớp khác để quyết định nghiệp vụ.
- **Inheritance misuse:** subclass không giữ đúng tiền điều kiện, hậu điều kiện hoặc bất biến của base type.
- **Test phụ thuộc implementation:** kiểm tra thứ tự gọi nội bộ thay vì kết quả nghiệp vụ, khiến refactor không đổi hành vi vẫn làm test hỏng.

## 9. Bài tập áp dụng

Một ứng dụng ban đầu tính giảm giá cố định 5% cho tất cả khách hàng; sau đó có thêm giảm theo hạng thành viên và mã khuyến mãi.

**Yêu cầu thực hành:**

1. Viết bản đầu chỉ cần một hàm tính số tiền giảm, dùng kiểu số nguyên hoặc **BigDecimal** với quy tắc làm tròn được xác định rõ.
2. Bổ sung hạng thành viên bằng **if/switch** và test; xác định khi nào logic vẫn dễ đọc.
3. Giả lập thay đổi nghiệp vụ: mỗi chương trình khuyến mãi có vòng đời và cách kiểm tra điều kiện riêng. Cân nhắc **DiscountPolicy**, nhưng chỉ nếu có nhiều chính sách thực sự cần thay đổi độc lập.
4. Kiểm tra **LSP**: mọi policy có cùng quy định về đầu vào, kết quả không âm, không vượt số tiền hàng hay không?
5. Thử tính số file/lớp phải sửa khi thêm một chương trình mới; nếu mô hình phức tạp hơn mà chi phí thay đổi không giảm, hãy đơn giản hóa lại.

**Tiêu chí tự đánh giá:** giải pháp đúng nghiệp vụ, giữ được các bất biến quan trọng, test được ca biên, có số lượng abstraction phù hợp với thay đổi đã biết và người khác có thể hiểu đường đi dữ liệu mà không phải lần qua nhiều tầng vô nghĩa.

**Thông điệp cốt lõi:** SOLID là công cụ kiểm soát phụ thuộc và chi phí thay đổi. Hãy áp dụng nguyên tắc vào nơi có rủi ro thật, giữ thiết kế nhỏ khi bài toán nhỏ, và mở rộng abstraction khi nhu cầu đã xuất hiện hoặc có bằng chứng đủ mạnh.