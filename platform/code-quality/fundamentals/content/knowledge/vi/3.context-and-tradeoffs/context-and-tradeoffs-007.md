# Đánh đổi sự đơn giản với tính linh hoạt mở rộng

Một thiết kế dễ hiểu ở hiện tại có thể trở nên khó sửa khi yêu cầu thay đổi liên tục. Ngược lại, một thiết kế có nhiều interface, tầng trừu tượng và cơ chế cấu hình có thể tiếp nhận thêm chức năng nhưng khiến một yêu cầu nhỏ mất nhiều thời gian để triển khai. Vì thế, **chất lượng mã nguồn không đồng nghĩa với việc có ít lớp nhất hoặc có nhiều điểm mở rộng nhất**. Thiết kế tốt phải phù hợp với những thay đổi thực sự có khả năng xảy ra.

Trong nền tảng *Code Quality Fundamentals*, sự đánh đổi này liên quan trực tiếp tới ba mục tiêu: mã **đáng tin cậy** (thay đổi không làm hỏng hành vi cũ), **dễ hiểu** (người đọc xác định được quy tắc và luồng xử lý) và **dễ thay đổi** (chi phí thêm yêu cầu mới nằm trong phạm vi hợp lý).

Sau bài học, bạn có thể:

- Phân biệt sự đơn giản hữu ích với việc đơn giản hóa quá mức, cũng như tính linh hoạt có cơ sở với trừu tượng hóa phòng xa.
- Nhận diện khi nào nên giữ một nhánh điều kiện trực tiếp và khi nào nên tạo điểm mở rộng.
- Đánh giá chi phí của hai lựa chọn qua các tình huống thay đổi cụ thể.
- Lựa chọn thiết kế có thể tiến hóa từng bước và được bảo vệ bằng kiểm thử.

## 1. Hiểu đúng hai phía của sự đánh đổi

### Sự đơn giản giúp gì cho chất lượng mã?

Một giải pháp đơn giản thường có ít khái niệm phải nhớ, ít đường đi của dữ liệu, ít phụ thuộc và ít nơi phải chỉnh sửa cho một thay đổi nhỏ. Chẳng hạn, một phương thức có hai nhánh điều kiện rõ nghĩa đôi khi dễ hiểu và an toàn hơn một hệ thống gồm nhiều interface, factory và registry.

Nhưng **đơn giản không có nghĩa là dồn mọi việc vào một phương thức**. Một hàm dài vừa tính giá, truy cập cơ sở dữ liệu, gửi email vừa bắt lỗi có thể ít lớp nhưng rất khó kiểm thử. Sự đơn giản đáng hướng tới là sự đơn giản của *mô hình tư duy*: người bảo trì biết quy tắc nằm ở đâu, dữ liệu đi qua những bước nào và hậu quả của một thay đổi là gì.

### Tính linh hoạt mở rộng là gì?

Tính linh hoạt là khả năng tiếp nhận **những dạng thay đổi đã xác định** mà không phải sửa quá nhiều phần không liên quan. Ví dụ:

- Thêm một cách tính phí vận chuyển trong khi giữ nguyên luồng tạo đơn.
- Thay nhà cung cấp gửi thông báo mà không sửa quy tắc nghiệp vụ.
- Cho một nhóm phát triển bổ sung bộ xử lý độc lập thông qua hợp đồng đã thống nhất.

Không có thiết kế nào linh hoạt trước *mọi* thay đổi. Một interface thuận tiện cho việc thay thuật toán tính phí chưa chắc giúp ích khi quy tắc thanh toán, dữ liệu và quy trình vận hành cùng thay đổi. Bởi vậy, câu hỏi cần trả lời là: **“Chúng ta cần dễ mở rộng theo hướng nào?”**

| Tiêu chí | Ưu tiên thiết kế trực tiếp | Ưu tiên cơ chế mở rộng |
| --- | --- | --- |
| Cách hiểu mã | Ít lớp và ít bước chuyển tiếp | Cần hiểu hợp đồng, cách lựa chọn và cách kết nối thành phần |
| Chi phí ban đầu | Thường thấp hơn | Thường cao hơn do phải thiết kế và kiểm thử điểm mở rộng |
| Khi thêm biến thể | Có thể phải sửa nhánh điều kiện | Có thể thêm thành phần mới trong ranh giới đã thiết kế |
| Rủi ro | Quy tắc có thể phình to hoặc bị sao chép | Trừu tượng sai làm tăng phụ thuộc, cấu hình và đường đi lỗi |
| Phù hợp khi | Yêu cầu ít, khá ổn định, phạm vi nhỏ | Biến thể có bằng chứng sẽ tăng và thay đổi tương đối độc lập |

**Tính linh hoạt có chi phí ngay hôm nay; lợi ích chỉ xuất hiện nếu thay đổi phù hợp xảy ra.** Ngược lại, thiếu điểm mở rộng có thể tạo chi phí lớn về sau khi cùng một quy tắc bị rải rác nhiều nơi.

## 2. Ví dụ Java: bắt đầu từ quy tắc rõ ràng

Giả sử hệ thống bán hàng hiện chỉ có hai hình thức giao hàng:

- **STANDARD:** phí 25.000 đồng; miễn phí nếu giá trị đơn từ 500.000 đồng.
- **EXPRESS:** phí cố định 45.000 đồng.

Quy tắc được dùng tại một chỗ, hai hình thức thay đổi cùng kỳ phát hành và chưa có yêu cầu tích hợp nhiều hãng vận chuyển.

Với bối cảnh này, một cách triển khai dễ đọc là:

```java
enum DeliveryMode {
    STANDARD, EXPRESS
}

record Order(long subtotalVnd) {}

final class ShippingFeeCalculator {
    long calculate(Order order, DeliveryMode mode) {
        if (order == null || mode == null || order.subtotalVnd() < 0) {
            throw new IllegalArgumentException("Invalid shipping input");
        }

        return switch (mode) {
            case STANDARD -> order.subtotalVnd() >= 500_000 ? 0 : 25_000;
            case EXPRESS -> 45_000;
        };
    }
}
```

Đoạn mã trên sử dụng cú pháp Java 17. Ưu điểm là người đọc nhìn thấy toàn bộ quy tắc trong một nơi. Không có cấu hình động, không cần tìm lớp triển khai nào được đăng ký và cũng không phải làm quen với một hợp đồng trừu tượng chỉ để hiểu hai công thức.

Đây chưa phải thiết kế kém chỉ vì có `switch`. **Một nhánh điều kiện tập trung, dễ đọc và được kiểm thử không tự động trở thành “code smell”.** Vấn đề nảy sinh nếu nhiều nơi cùng phân nhánh theo `DeliveryMode` để tính phí, hiển thị ước tính, chọn hãng và xử lý hoàn tiền; hoặc mỗi hình thức phát triển nhiều quy tắc và phụ thuộc riêng.

Các trường hợp nên kiểm thử gồm ranh giới 499.999/500.000 đồng, phí cố định của EXPRESS, giá trị âm và đầu vào `null`. Kiểm thử hành vi này vẫn hữu ích nếu sau đó ta thay cấu trúc bên trong.

## 3. Khi sự mở rộng bắt đầu có giá trị

Sau một thời gian, có thêm yêu cầu thực tế:

1. Mỗi hãng vận chuyển tự thay đổi quy tắc phí và có lịch phát hành riêng.
2. Một số cách tính phí cần tham số hoặc dịch vụ riêng.
3. Các thay đổi cùng chạm vào một `switch` ngày càng dài, gây xung đột khi tích hợp mã.

Đây là **bằng chứng về biến thể nghiệp vụ cần phát triển độc lập**. Ta có thể tách quy tắc tính phí ra một hợp đồng nhỏ:

```java
import java.util.Map;

interface ShippingPolicy {
    long fee(Order order);
}

final class StandardShippingPolicy implements ShippingPolicy {
    @Override
    public long fee(Order order) {
        return order.subtotalVnd() >= 500_000 ? 0 : 25_000;
    }
}

final class ExpressShippingPolicy implements ShippingPolicy {
    @Override
    public long fee(Order order) {
        return 45_000;
    }
}

final class ShippingFeeService {
    private final Map<DeliveryMode, ShippingPolicy> policies;

    ShippingFeeService(Map<DeliveryMode, ShippingPolicy> policies) {
        this.policies = Map.copyOf(policies);
    }

    long calculate(Order order, DeliveryMode mode) {
        if (order == null || mode == null || order.subtotalVnd() < 0) {
            throw new IllegalArgumentException("Invalid shipping input");
        }

        ShippingPolicy policy = policies.get(mode);
        if (policy == null) {
            throw new IllegalArgumentException("Unsupported delivery mode: " + mode);
        }
        return policy.fee(order);
    }
}
```

Ví dụ thứ hai **dùng lại `Order` và `DeliveryMode` của phiên bản đầu**; các chính sách được đăng ký khi khởi tạo `ShippingFeeService`. Phần gọi dịch vụ chỉ cần biết `calculate(order, mode)`, còn từng quy tắc có thể được kiểm thử và chỉnh sửa riêng.

Đổi lại, ta có nhiều loại hơn, phải tạo `Map` đăng ký chính sách và phải xử lý trường hợp chưa đăng ký. Thêm `DeliveryMode` mới vẫn cần cập nhật enum và cấu hình đăng ký: **Strategy không tự biến hệ thống thành một nền tảng plug-in có thể mở rộng tại thời gian chạy**. Nếu cần cho bên thứ ba cài thành phần mà không phát hành lại ứng dụng, đó là một bài toán lớn hơn về định danh, tương thích, bảo mật và vòng đời plug-in.

Hai phiên bản đều có thể tốt tại những thời điểm khác nhau. Quyết định quan trọng nằm ở chỗ **chi phí thêm cấu trúc đã được bù bằng chi phí thay đổi thực tế hay chưa**.

### Không phải cứ có nhiều nhánh là cần Strategy

Số lượng `if` hay `switch` không đủ để quyết định. Cần nhìn vào cách thay đổi:

| Tình huống quan sát | Hướng xử lý hợp lý |
| --- | --- |
| Hai hoặc ba quy tắc ngắn, ổn định, chỉ dùng một chỗ | Giữ điều kiện tập trung và tên gọi rõ ràng |
| Một phép tính dài gây khó đọc nhưng chưa có nhiều biến thể | Trích thành phương thức nhỏ, đặt tên theo nghiệp vụ |
| Các nhánh có nhiều thuật toán độc lập, đổi thường xuyên | Cân nhắc Strategy hoặc các thành phần triển khai cùng hợp đồng |
| Cùng một phân nhánh bị sao chép qua nhiều lớp | Tập trung quy tắc trước khi lựa chọn mô hình mở rộng |
| Bên ngoài cần cung cấp triển khai mà không sửa mã lõi | Xác định API mở rộng, phiên bản hợp đồng, đăng ký và xử lý lỗi |

Một phép trích phương thức đơn giản thường giải quyết vấn đề dễ đọc mà chưa cần interface. Ngược lại, khi quy tắc thay đổi độc lập, một hợp đồng nhỏ có thể giảm rủi ro sửa nhầm quy tắc khác.

## 4. Thiết kế cho điểm biến thiên, giữ phần ổn định dễ hiểu

Thay vì cố gắng trừu tượng hóa toàn bộ hệ thống, hãy tách hai loại trách nhiệm:

- **Phần ổn định:** những bất biến hoặc luồng xử lý ít thay đổi, chẳng hạn kiểm tra dữ liệu đơn hàng, điều phối yêu cầu tính phí, định dạng kết quả và quy tắc lỗi chung.
- **Phần biến thiên:** những chính sách mà thay đổi mới có thể xuất hiện độc lập, chẳng hạn cách tính phí theo từng hình thức hoặc hãng vận chuyển.

Một điểm mở rộng tốt có **phạm vi hẹp và ý nghĩa nghiệp vụ rõ**. Hợp đồng `ShippingPolicy.fee(Order)` mô tả việc cần thực hiện. Hợp đồng mơ hồ kiểu `Processor.execute(Object, Map<String, Object>)` có vẻ áp dụng được cho mọi trường hợp, nhưng lại che giấu kiểu dữ liệu, ràng buộc và cách xử lý lỗi. Khả năng “làm được mọi thứ” trên giấy có thể làm giảm tính đáng tin cậy.

Khi tạo điểm mở rộng, hãy trả lời các câu hỏi:

1. Thành phần mới được phép thay đổi hành vi gì, và **không** được thay đổi bất biến nào?
2. Đầu vào, đầu ra, đơn vị đo và cách báo lỗi đã rõ chưa?
3. Có thể kiểm thử từng triển khai độc lập và kiểm thử hợp đồng chung không?
4. Hệ thống sẽ chọn triển khai tại lúc biên dịch, khi khởi tạo hay tại thời gian chạy?
5. Khi một triển khai không hợp lệ hoặc bị lỗi, người gọi nhận kết quả gì?

Ví dụ, với phí vận chuyển, quy tắc chung có thể yêu cầu đầu ra không âm và tính bằng đồng. Nếu các chính sách tự ý trả về giá trị âm hoặc trộn đơn vị tiền tệ, interface vẫn tồn tại nhưng hợp đồng thiếu chặt chẽ. Phần điều phối hoặc kiểm thử hợp đồng cần bảo vệ các bất biến này.

## 5. Chi phí thường bị bỏ sót của tính linh hoạt

Một thiết kế mở rộng được không chỉ thêm vài lớp. Nó còn tạo ra chi phí duy trì:

**Chi phí nhận thức.** Người đọc phải lần từ điểm gọi tới cấu hình, registry, factory và triển khai thực tế. Nếu để sửa một công thức phải hiểu nhiều tầng gián tiếp, khả năng bảo trì có thể giảm.

**Chi phí kiểm thử.** Ngoài kiểm thử kết quả nghiệp vụ, cần xác minh ánh xạ loại dịch vụ tới triển khai, xử lý thiếu cấu hình, tương thích giữa các triển khai và quy tắc lỗi.

**Chi phí thay đổi hợp đồng.** Khi nhiều lớp phụ thuộc vào một interface chung, sửa chữ ký phương thức hoặc ý nghĩa đầu vào có thể ảnh hưởng rộng. API công khai hay điểm mở rộng cho nhóm khác sử dụng có giá thay đổi đặc biệt cao.

**Chi phí vận hành.** Cấu hình động và plug-in làm tăng khả năng khởi tạo sai, chọn nhầm triển khai hoặc thất bại khi tải thành phần. Cần quan sát hệ thống đang dùng triển khai nào và vì sao.

**Chi phí hiệu năng và độ phức tạp hệ thống.** Một phép gọi interface trong Java thường không đáng lo hơn tính rõ ràng của mã. Tuy nhiên, thêm lời gọi mạng, hàng đợi, tiến trình riêng hoặc cấu hình phân tán chỉ để “mở rộng sau này” có thể làm tăng đáng kể độ trễ và số điểm lỗi.

Ở chiều ngược lại, thiết kế quá trực tiếp cũng có giá: sửa nhiều nhánh ở nhiều nơi, kiểm thử hồi quy trên phạm vi rộng và tăng xác suất các biến thể hành xử không nhất quán.

Do đó, hãy so sánh **tổng chi phí tạo, hiểu, kiểm thử và thay đổi** theo các kịch bản có khả năng xuất hiện. Số lượng dòng mã hay số lượng class chỉ là tín hiệu phụ.

## 6. Tránh hai cực đoan

### Cực đoan 1: Đơn giản hóa đến mức mọi thứ dính vào nhau

Ví dụ một lớp `OrderService` vừa tính phí giao hàng, quyết định khuyến mãi, lưu cơ sở dữ liệu và gửi thông báo. Ban đầu việc gọi một lớp có thể tiện. Nhưng sau đó chỉnh phí vận chuyển dễ ảnh hưởng giao dịch lưu trữ hoặc luồng gửi email; kiểm thử yêu cầu dựng cả cơ sở dữ liệu và dịch vụ ngoài.

Cách cải thiện là **tách trách nhiệm thực sự khác nhau**, đặt tên rõ và giữ ranh giới phụ thuộc hợp lý. Tách trách nhiệm không đồng nghĩa với việc phải tạo interface cho từng lớp. Một lớp tính phí thuần túy có thể đủ để cô lập logic nghiệp vụ.

### Cực đoan 2: Trừu tượng hóa tất cả khả năng tưởng tượng

Ví dụ hệ thống mới chỉ gửi một loại email nhưng đã xây `NotificationProviderFactory`, `ProviderPluginManager`, `MessageTransformationPipeline` và nhiều tầng adapter cho những kênh chưa có yêu cầu. Hệ thống vẫn chạy, nhưng sửa nội dung email phải đi qua chuỗi đối tượng và cấu hình dài.

Cách cải thiện là giữ luồng đơn giản, tách việc tạo nội dung và việc gửi nếu chúng có trách nhiệm khác nhau; chỉ tạo hợp đồng nhiều kênh khi có yêu cầu hoặc bằng chứng đáng tin cậy. Đây là tinh thần **YAGNI** (*You Aren't Gonna Need It*): đừng trả trước chi phí cho khả năng chưa chứng minh được giá trị.

YAGNI **không có nghĩa là bỏ qua cấu trúc căn bản**. Kiểm tra đầu vào, tên dễ hiểu, kiểm thử nghiệp vụ và tách phụ thuộc gây khó kiểm thử đều đem lại giá trị ngay cả khi chưa có yêu cầu mở rộng.

## 7. Quy trình lựa chọn thiết kế trong một yêu cầu thực tế

### Bước 1: Xác định điều chắc chắn ở hiện tại

Ghi rõ chức năng phải hoạt động như thế nào, đầu vào/đầu ra và các trường hợp biên. Với ví dụ giao hàng: STANDARD có ngưỡng miễn phí, EXPRESS có phí cố định, không chấp nhận tổng tiền âm. Đây là những yêu cầu có thể kiểm chứng bằng test.

### Bước 2: Phân loại thay đổi tương lai theo bằng chứng

Phân biệt giữa:

- **Đã cam kết:** yêu cầu trong kế hoạch phát triển có chủ sở hữu và thời điểm dự kiến.
- **Có bằng chứng:** hệ thống từng đổi cùng nhóm quy tắc nhiều lần hoặc đã có các biến thể độc lập.
- **Chỉ giả định:** “sau này biết đâu cần thêm hàng chục nhà cung cấp”.

Thiết kế có thể chừa chỗ cho hai nhóm đầu, nhưng không nên đánh đổi quá nhiều độ dễ hiểu vì nhóm cuối.

### Bước 3: Mô phỏng một thay đổi cụ thể

Thay vì hỏi “thiết kế nào mở rộng tốt?”, hãy thử: “Nếu thêm phí giao hàng theo cân nặng, cần sửa những file nào? Cần kiểm thử lại phạm vi nào? Có chạm vào quy tắc EXPRESS hiện có không?”. Mô phỏng hai hoặc ba thay đổi gần với sản phẩm thường chỉ ra ranh giới mở rộng hiệu quả hơn một sơ đồ lớp trừu tượng.

### Bước 4: Chọn phương án ít phức tạp nhất đáp ứng các kịch bản đó

Có thể tiến hóa theo mức độ:

```text
Điều kiện ngắn, tập trung
        |
        | Quy tắc dài hoặc cần tái sử dụng
        v
Phương thức/lớp nghiệp vụ riêng
        |
        | Nhiều biến thể độc lập, thay đổi thường xuyên
        v
Hợp đồng nhỏ + các triển khai riêng
        |
        | Nhiều nhóm/bên ngoài cần tự tích hợp
        v
API mở rộng có phiên bản + cơ chế đăng ký/quản lý
```

Đây là các lựa chọn, **không phải các giai đoạn bắt buộc**. Một hệ thống có thể ổn định nhiều năm ở mức đầu tiên; hệ thống khác có nhu cầu API mở rộng ngay từ ngày đầu vì đó là yêu cầu sản phẩm.

### Bước 5: Giữ khả năng đảo chiều

Đối với quyết định chưa chắc chắn, ưu tiên cách thay đổi có thể cô lập. Để quy tắc tính phí trong một lớp và tránh lặp lại trên nhiều màn hình giúp lần sau thay `switch` bằng Strategy dễ hơn. Một bộ kiểm thử theo hành vi cung cấp bằng chứng rằng phép refactor không làm đổi kết quả.

Nguyên tắc quan trọng là **trì hoãn sự phức tạp chưa cần thiết nhưng không trì hoãn việc làm rõ ranh giới và kiểm thử**.

## 8. Dấu hiệu đã đến lúc điều chỉnh mức độ linh hoạt

Hãy xem lại thiết kế khi quan sát được một hoặc nhiều hiện tượng sau:

- Thêm một biến thể phải sửa cùng điều kiện ở nhiều file khác nhau.
- Các nhóm phát triển thường xuyên xung đột khi chỉnh cùng khối phân nhánh.
- Nhánh mới có nhiều phụ thuộc hoặc vòng đời riêng khiến đoạn xử lý chung khó đọc.
- Mỗi thay đổi nhỏ đòi hỏi kiểm thử lại nhiều chức năng không liên quan.
- API hoặc quy tắc biến thể đã đủ ổn định để mô tả bằng một hợp đồng nhỏ.

Đồng thời, hãy xem lại **sự trừu tượng hóa quá mức** khi một yêu cầu đơn giản phải chỉnh qua nhiều interface, factory và file cấu hình; khi hầu hết interface chỉ có một triển khai mà không có nhu cầu thay thế; hoặc khi tên trừu tượng không nói rõ trách nhiệm nghiệp vụ. Tuy nhiên, interface một triển khai vẫn có thể hợp lý tại ranh giới với dịch vụ ngoài hoặc để kiểm soát phụ thuộc, nên cần xem ngữ cảnh trước khi xóa.

Không có ngưỡng cứng như “từ ba nhánh phải dùng Strategy”. Những con số kiểu đó không đo được mức độ độc lập, tốc độ thay đổi và rủi ro của từng nhánh.

## 9. Cách refactor an toàn từ thiết kế trực tiếp sang mở rộng

Khi tín hiệu thay đổi đã đủ rõ, có thể tiến hành theo thứ tự:

1. **Đóng băng hành vi bằng kiểm thử:** xác nhận kết quả với mọi lựa chọn hiện tại và các trường hợp biên; ghi rõ hành vi lỗi.
2. **Tập trung logic bị phân tán:** nếu cùng quy tắc xuất hiện nhiều nơi, đưa về một đầu mối có tên nghiệp vụ trước.
3. **Xác định phần thay đổi độc lập:** tìm điểm khác biệt thật sự giữa các chính sách; không đưa các chi tiết không liên quan vào hợp đồng.
4. **Trích từng triển khai:** chuyển công thức từ `switch` sang các lớp hoặc hàm riêng, giữ đầu ra tương đương.
5. **Điều phối lựa chọn tại một nơi:** đăng ký các triển khai, xử lý lựa chọn không hợp lệ và đảm bảo bất biến chung.
6. **Chạy lại kiểm thử và loại bỏ đường cũ:** tránh giữ hai cơ chế tính phí cùng hoạt động, dễ dẫn tới kết quả lệch nhau.

Refactor thành công cần giữ nguyên hành vi nhìn từ bên ngoài. Nếu đồng thời sửa quy tắc giá hoặc yêu cầu sản phẩm, cần tách rõ thay đổi hành vi với thay đổi cấu trúc để dễ đánh giá lỗi hồi quy.

## 10. Bài tập tình huống

**Tình huống A.** Một ứng dụng nội bộ chỉ xuất báo cáo CSV theo một định dạng cố định. Có đề xuất xây hệ thống `ReportExporterPlugin` để “sau này hỗ trợ mọi định dạng”.

*Gợi ý:* Đầu tiên giữ một thành phần xuất CSV có trách nhiệm rõ ràng và kiểm thử dữ liệu đầu ra. Chưa cần API plug-in khi chưa có bằng chứng về các định dạng hoặc nhóm phát triển độc lập. Nếu sau này cần PDF và Excel, xem xét hợp đồng xuất báo cáo phù hợp với sự khác biệt thực tế.

**Tình huống B.** Hệ thống thanh toán đã tích hợp ba cổng. Mỗi cổng có xác thực, timeout, lỗi và lịch cập nhật riêng. Một `switch` lớn chứa toàn bộ chi tiết gọi API.

*Gợi ý:* Cân nhắc hợp đồng cho thao tác thanh toán và các adapter riêng theo cổng. Chuẩn hóa kết quả, lỗi và cách xử lý idempotency ở ranh giới chung; kiểm thử riêng từng tích hợp và kiểm thử hợp đồng. Việc thay adapter giúp tránh đụng tới luồng nghiệp vụ thanh toán không liên quan.

**Tình huống C.** Một màn hình có ba trạng thái `LOADING`, `SUCCESS`, `ERROR`. Nhóm muốn thay điều kiện hiển thị bằng hệ thống rule engine cấu hình động.

*Gợi ý:* Ba trạng thái đơn giản, ổn định thường phù hợp với phân nhánh rõ ràng. Rule engine thêm ngôn ngữ cấu hình, cơ chế thực thi và xử lý lỗi mà chưa mang lại lợi ích tương xứng.

Với mỗi tình huống, hãy thử viết một thay đổi dự kiến, liệt kê nơi cần sửa và phạm vi kiểm thử. Chính sự so sánh đó mới cung cấp cơ sở lựa chọn.

## 11. Ghi nhớ khi đánh giá chất lượng thiết kế

Một thiết kế đáng tin cậy, dễ hiểu và dễ thay đổi thường có các đặc điểm:

- **Hành vi hiện tại minh bạch:** người mới vào dự án có thể lần theo quy tắc mà không cần biết quá nhiều cơ chế gián tiếp.
- **Điểm mở rộng gắn với nhu cầu có thật:** hợp đồng đại diện cho biến thể nghiệp vụ rõ ràng, không chỉ là khả năng giả định.
- **Phần ổn định ít bị tác động:** thay đổi một chính sách không vô tình thay đổi chính sách khác.
- **Hợp đồng có giới hạn và được kiểm thử:** đầu vào, đầu ra và cách xử lý trường hợp lỗi nhất quán.
- **Có thể tiến hóa:** mã không lặp bừa bãi, trách nhiệm có ranh giới, kiểm thử bảo vệ hành vi để refactor khi cần.

Hãy đánh giá sự đơn giản và tính linh hoạt bằng **chi phí thay đổi theo bối cảnh**, thay vì dựa vào sở thích đối với `if`, `switch`, interface hay design pattern. Mức trừu tượng đúng hôm nay có thể được điều chỉnh khi sản phẩm, đội ngũ và tốc độ thay đổi khác đi.
