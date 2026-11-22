# Tránh tạo interface cho mọi lớp khi chưa có nhu cầu

Trong Java, `interface` là công cụ để mô tả một hợp đồng mà nhiều kiểu có thể thực hiện. Tuy nhiên, **không phải lớp nào cũng cần một interface riêng**. Nếu tạo cặp `SomeService`/`SomeServiceImpl` cho mọi lớp dù không có nhu cầu thay thế, mở rộng hay tách ranh giới phụ thuộc, mã nguồn có thể nhiều tầng hơn nhưng không linh hoạt hơn.

Nguyên tắc thực tế là: **bắt đầu bằng thiết kế đơn giản nhất đáp ứng nhu cầu hiện tại; thêm interface khi nó thể hiện một ranh giới hoặc khả năng thay thế có ý nghĩa**. Đây là cách áp dụng YAGNI (*You Aren’t Gonna Need It*): đừng xây dựng tính linh hoạt giả định chỉ vì có thể sẽ cần trong tương lai. Điều đó không có nghĩa là cấm interface có một implementation; điều quan trọng là lý do thiết kế.

## 1. Interface giải quyết vấn đề gì?

Interface khai báo những thao tác mà một kiểu cam kết cung cấp, nhưng không buộc người gọi phụ thuộc vào một cách triển khai cụ thể.

Ví dụ, `PaymentGateway` có thể định nghĩa thao tác thanh toán. Một implementation dùng cổng thanh toán thật, implementation khác dùng sandbox, và test có thể dùng fake để ghi nhận lời gọi. `OrderService` chỉ cần biết hợp đồng thanh toán, không cần biết nhà cung cấp cụ thể.

Ngược lại, nếu một lớp chỉ định dạng chuỗi theo một quy tắc ổn định, chỉ có một người gọi và không có nhu cầu thay đổi hành vi, việc tạo `Formatter` interface, `DefaultFormatter` implementation và thêm lớp chuyển tiếp chỉ để gọi một method có thể tạo thêm tên kiểu, file và bước điều hướng mà không giải quyết vấn đề thực tế.

Interface hữu ích khi nó tạo ra **khả năng thay thế thực sự**, ranh giới giữa các thành phần, hoặc hợp đồng công khai. Nó không tự động làm thiết kế tốt hơn chỉ vì mã đã “trừu tượng hóa”.

## 2. Vì sao không nên tạo interface một cách máy móc?

- **Tăng indirection:** người đọc phải lần từ interface sang implementation để hiểu hành vi, dù chỉ có một đường thực thi duy nhất.
- **Tăng số kiểu và file:** một lớp đơn giản có thể biến thành interface, implementation mặc định, factory và lớp ủy quyền không cần thiết.
- **Tạo điểm mở rộng giả:** nhiều implementation chưa chắc sẽ tồn tại; API linh hoạt dựa trên giả định chưa được kiểm chứng có thể khiến thiết kế khó thay đổi hơn.
- **Tăng chi phí bảo trì:** khi hợp đồng thay đổi, mọi implementation và nơi cấu hình có thể phải cập nhật theo.
- **Làm test quá phụ thuộc cấu trúc:** nếu mock mọi lớp nội bộ, test dễ kiểm tra cách cài đặt hơn là kết quả/hành vi mà người dùng quan tâm.
- **Làm mờ trách nhiệm:** interface không có ý nghĩa nghiệp vụ hoặc ranh giới rõ ràng khiến tên gọi và vai trò của các thành phần khó hiểu.

Đây không phải lý do để tránh interface nói chung. Đó là lý do để yêu cầu một lợi ích cụ thể trước khi thêm một tầng trừu tượng.

## 3. Khi nào interface đáng được tạo?

### 3.1 Có nhiều cách triển khai thực sự

Khi cùng một hợp đồng có các implementation với hành vi hoặc cơ chế khác nhau, interface giúp caller chọn implementation mà không phải chứa logic `if/else` theo từng lớp cụ thể.

Ví dụ: `FileStorage` và `CloudStorage`, nhiều chính sách tính phí, nhiều chiến lược sắp xếp, hoặc các nhà cung cấp thanh toán khác nhau. Nhiều implementation phải cùng tuân thủ một hợp đồng ổn định; nếu không, chỉ có nhiều class chưa chắc đã cần interface.

### 3.2 Có ranh giới với hệ thống bên ngoài

Database, HTTP client, email gateway, hàng đợi hoặc dịch vụ thanh toán là những phụ thuộc có thể thay đổi theo môi trường và khó chạy trong unit test. Một interface ở ranh giới đó giúp logic nghiệp vụ không phụ thuộc trực tiếp vào thư viện hoặc nhà cung cấp.

Không nhất thiết phải tạo interface cho mọi wrapper quanh thư viện. Hãy đặt hợp đồng ở nơi nó có ý nghĩa với thành phần sử dụng, và chỉ đưa ra các thao tác mà thành phần đó thực sự cần.

### 3.3 Có API công khai, plugin hoặc điểm mở rộng được thiết kế rõ

Nếu mã khác sẽ triển khai hợp đồng, hoặc hệ thống hỗ trợ plugin/extension, interface có thể là phần API cần ổn định. Trong trường hợp này, dù ban đầu chỉ có một implementation, hợp đồng vẫn có giá trị vì nó là ranh giới được chủ động công bố.

### 3.4 Có nhu cầu thay thế phụ thuộc trong test

Interface hữu ích khi fake hoặc stub giúp test hành vi của thành phần mà không cần khởi động hệ thống bên ngoài. Tuy vậy, không nên suy luận rằng “muốn test được thì mọi lớp phải có interface”. Các hàm thuần, lớp nhỏ có hành vi xác định và nhiều thành phần nội bộ có thể test trực tiếp. Chỉ tách hợp đồng ở ranh giới mà việc thay thế mang lại giá trị rõ ràng.

### 3.5 Cần phụ thuộc vào hợp đồng thay vì chi tiết triển khai

Theo nguyên tắc đảo ngược phụ thuộc (*Dependency Inversion Principle*), chính sách cấp cao không nên bị ràng buộc chặt vào chi tiết cấp thấp; cả hai nên phụ thuộc vào abstraction phù hợp. Nhưng điều này **không đồng nghĩa mọi dependency đều phải là interface**. Một lớp cụ thể nhỏ, ổn định và không tạo ra coupling đáng lo có thể là lựa chọn đơn giản, dễ đọc hơn.

## 4. Khi nào nên giữ lớp cụ thể?

Thường nên bắt đầu với một class cụ thể khi phần lớn các điều kiện sau đúng:

- Có một hành vi rõ ràng, ổn định và hiện chỉ có một cách thực hiện hợp lý.
- Lớp không phải API mở rộng cho mã bên ngoài và không nằm ở ranh giới dễ thay đổi.
- Không có caller thực tế nào cần chọn hoặc hoán đổi implementation.
- Thêm interface sẽ chỉ đổi tên kiểu, chuyển tiếp lời gọi hoặc sao chép đúng một hợp đồng mà chưa có mục đích độc lập.
- Test có thể xác minh kết quả qua API công khai của lớp mà không cần giả lập chi tiết nội bộ.

Ví dụ: `ReceiptFormatter` chỉ ghép mã đơn hàng thành dòng biên nhận theo một quy tắc đơn giản. Nếu chưa có nhu cầu chọn định dạng theo vùng, kênh hoặc chính sách, một class cụ thể là đủ. Khi xuất hiện yêu cầu thực tế như nhiều định dạng biên nhận có thể hoán đổi, lúc đó có thể trích xuất `ReceiptFormatter` interface với những tên và phương thức phản ánh nhu cầu mới.

Không nên dùng “chỉ có một implementation” như quy tắc tuyệt đối. Một interface một implementation vẫn hợp lý nếu nó là port ở ranh giới hạ tầng, API công khai hoặc seam thay thế quan trọng. Ngược lại, hai implementation chỉ khác tên nhưng không có nhu cầu thay thế cũng chưa chắc tạo nên một abstraction tốt.

## 5. Ví dụ Java 17+: trừu tượng hóa đúng ranh giới

Trong ví dụ sau, `PaymentGateway` là interface vì cách thực hiện thanh toán có thể thay đổi hoặc được thay thế khi test. `ReceiptFormatter` vẫn là class cụ thể vì quy tắc định dạng hiện tại đơn giản và ổn định. `OrderService` phụ thuộc vào hợp đồng thanh toán, nhưng không tạo interface riêng cho mọi collaborator.

Lưu đoạn mã đầy đủ vào `InterfaceWhenNeededDemo.java`:

```java
public class InterfaceWhenNeededDemo {
    @FunctionalInterface
    interface PaymentGateway {
        void charge(String orderId, int amountCents);
    }

    static final class SandboxPaymentGateway implements PaymentGateway {
        @Override
        public void charge(String orderId, int amountCents) {
            System.out.println("Charged " + orderId + ": "
                    + amountCents + " cents");
        }
    }

    static final class ReceiptFormatter {
        String format(String orderId) {
            return "Receipt for " + orderId;
        }
    }

    static final class OrderService {
        private final PaymentGateway paymentGateway;
        private final ReceiptFormatter receiptFormatter =
                new ReceiptFormatter();

        OrderService(PaymentGateway paymentGateway) {
            this.paymentGateway = paymentGateway;
        }

        void checkout(String orderId, int amountCents) {
            paymentGateway.charge(orderId, amountCents);
            System.out.println(receiptFormatter.format(orderId));
        }
    }

    public static void main(String[] args) {
        OrderService service =
                new OrderService(new SandboxPaymentGateway());
        service.checkout("ORD-42", 1250);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac InterfaceWhenNeededDemo.java
java InterfaceWhenNeededDemo
```

Stdout chính xác:

```text
Charged ORD-42: 1250 cents
Receipt for ORD-42
```

### Đọc thiết kế trong ví dụ

- `OrderService` gọi `PaymentGateway.charge(...)` thay vì phụ thuộc trực tiếp vào `SandboxPaymentGateway`. Một implementation khác có thể thay thế mà không cần sửa logic checkout.
- `SandboxPaymentGateway` là implementation chạy minh họa. Trong hệ thống thật, adapter có thể gọi nhà cung cấp thanh toán; không nên coi sandbox là giao dịch tiền thật.
- `ReceiptFormatter` được dùng trực tiếp vì hiện tại nó chỉ thực hiện một quy tắc định dạng nhỏ, xác định. Không có lợi ích rõ ràng khi thêm `ReceiptFormatter` interface chỉ để có thêm một kiểu.
- `PaymentGateway` có một phương thức trừu tượng nên được đánh dấu `@FunctionalInterface`. Trong test, có thể cung cấp lambda làm fake, ví dụ:

```java
PaymentGateway fake = (orderId, amountCents) ->
        System.out.println("Fake charge: " + orderId + ", " + amountCents);
OrderService service = new OrderService(fake);
service.checkout("TEST-1", 500);
```

Đoạn test trên được đặt trong ngữ cảnh có thể truy cập các kiểu lồng của `InterfaceWhenNeededDemo` (ví dụ bên trong lớp demo hoặc test cùng package với quyền truy cập phù hợp). Nó minh họa khả năng thay thế phụ thuộc, không phải phần của `main` ở chương trình chạy chính. Khi dự án lớn hơn, có thể chuyển các kiểu thành top-level types và điều chỉnh modifier theo ranh giới package/API.

## 6. Chọn class, interface hay abstract class?

| Lựa chọn | Chọn khi | Ví dụ điển hình |
| --- | --- | --- |
| Class cụ thể | Có một hành vi xác định, ổn định; chưa cần thay thế implementation. | `ReceiptFormatter`, lớp tính toán thuần. |
| Interface | Cần một hợp đồng/capability để nhiều implementation hoặc thành phần bên ngoài có thể tuân thủ. | `PaymentGateway`, `Storage`, `Clock` ở ranh giới cần thay thế. |
| Abstract class | Các lớp cùng họ cần chia sẻ trạng thái, mã triển khai hoặc quy trình chung; Java chỉ cho kế thừa một class. | Một lớp cơ sở có template method và trạng thái dùng chung thực sự. |

Interface chủ yếu mô tả hợp đồng; abstract class có thể giữ state và triển khai một phần hành vi dùng chung. Đừng tạo abstract class chỉ để tránh lặp một vài dòng, cũng đừng tạo interface chỉ vì một class có public methods.

## 7. Cách ra quyết định trước khi thêm interface

Có thể tự hỏi theo thứ tự:

1. **Ai là consumer?** Có thành phần nào cần gọi qua hợp đồng thay vì biết class cụ thể không?
2. **Điều gì cần thay thế?** Có các implementation, môi trường hoặc chính sách thực sự khác nhau không? Nếu chưa có, ranh giới đó có lý do công khai/kiến trúc nào khác không?
3. **Thay đổi có bị chặn bởi coupling không?** Nếu class cụ thể thay đổi, nó có buộc logic nghiệp vụ hoặc test phải phụ thuộc vào thư viện/hạ tầng không?
4. **Interface nói lên điều gì?** Tên và method có mô tả capability hoặc hợp đồng có ý nghĩa không, hay chỉ lặp lại tên class thêm chữ `I`, `Default` hoặc `Impl`?
5. **Chi phí có xứng đáng không?** Lợi ích về thay thế, kiểm thử, API hoặc ranh giới module có lớn hơn số kiểu và điểm điều hướng mới không?
6. **Có thể trì hoãn một cách an toàn không?** Nếu chưa có nhu cầu hiện tại và không có ranh giới quan trọng cần bảo vệ, hãy bắt đầu bằng class cụ thể rồi trích xuất interface khi bằng chứng thiết kế xuất hiện.

Không cần mọi câu trả lời đều là “có nhiều implementation”. Interface cũng có thể bảo vệ một ranh giới trước khi implementation thứ hai tồn tại. Nhưng lý do đó nên cụ thể và có thể giải thích được, không chỉ là dự đoán mơ hồ.

## 8. Những cách làm dễ gây vấn đề

### Tạo interface chỉ để tuân thủ quy ước đặt tên

Ví dụ, mọi class đều bị bắt buộc có cặp `CustomerService` và `CustomerServiceImpl` dù không có hợp đồng hay consumer độc lập. Quy ước này có thể hợp lý trong một framework hoặc kiến trúc đã xác định rõ, nhưng không phải quy tắc chung của Java. Hãy dựa vào yêu cầu của hệ thống, không tạo lớp trung gian chỉ vì thói quen.

### Dùng interface để che giấu một thiết kế chưa rõ

Đặt tên `Manager`, `Processor` hoặc `Handler` chung chung không làm trách nhiệm rõ hơn. Trước khi tạo abstraction, xác định capability, dữ liệu đầu vào/đầu ra và điều kiện mà mọi implementation phải tuân thủ.

### Mock tất cả các class trong unit test

Mock có thể hữu ích ở ranh giới bên ngoài, nhưng mock mọi collaborator nhỏ làm test dễ vỡ khi cấu trúc nội bộ đổi. Hãy ưu tiên kiểm tra hành vi quan sát được; dùng fake/mock ở nơi cần kiểm soát kết quả phụ thuộc hoặc tránh I/O thật.

### Giữ abstraction không còn giá trị

Nếu nhiều implementation đã bị xóa và hợp đồng không còn được consumer nào cần đến, xem xét đơn giản hóa có kiểm soát. Ngược lại, đừng xóa interface chỉ vì hôm nay mới có một implementation nếu nó vẫn là ranh giới API/hạ tầng quan trọng.

## Kết luận

Interface là công cụ để thể hiện hợp đồng và tạo khả năng thay thế có ý nghĩa, không phải bước bắt buộc cho mỗi class. Hãy giữ lớp cụ thể khi hành vi đơn giản và ổn định; tạo interface khi cần nhiều implementation, ranh giới với hạ tầng, API mở rộng hoặc một điểm thay thế thực sự hữu ích. Thiết kế tốt không phải là trừu tượng hóa nhiều nhất, mà là **đặt abstraction đúng nơi có nhu cầu và tránh indirection không mang lại giá trị**.