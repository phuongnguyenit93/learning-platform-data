# Kết hợp đối tượng thay cho kế thừa khi thay đổi thành phần cộng tác

## 1. Vấn đề thiết kế: một lớp phải làm việc với nhiều thành phần có thể thay đổi

Trong lập trình hướng đối tượng, **kế thừa** (inheritance) biểu diễn quan hệ *is-a*: một lớp con là một dạng hợp lệ của lớp cha. **Kết hợp đối tượng** (object composition) biểu diễn quan hệ *has-a/uses-a*: một đối tượng giữ tham chiếu đến những đối tượng khác và giao việc cho chúng.

Nguyên tắc **“ưu tiên kết hợp đối tượng hơn kế thừa”** đặc biệt hữu ích khi thứ cần thay đổi là **thành phần cộng tác** (collaborator), chẳng hạn cách tính phí, nơi lưu dữ liệu, dịch vụ gửi thông báo hoặc cách gọi hệ thống bên ngoài. Khi đó, ta thường muốn thay **đối tượng được sử dụng** mà không phải tạo một **lớp con mới của đối tượng sử dụng**.

Trong module Dependency Injection (DI), nguyên tắc này nối trực tiếp với hai ý tưởng:

- **Composition**: lớp nghiệp vụ giữ một hoặc nhiều đối tượng cộng tác qua các trường dữ liệu và ủy quyền công việc cho chúng.
- **Dependency Injection**: các đối tượng cộng tác được tạo, lựa chọn và **truyền từ bên ngoài** vào lớp nghiệp vụ, thay vì lớp nghiệp vụ tự quyết định cách tạo chúng.
- **Inversion of Control (IoC)**: quyền điều phối việc khởi tạo, lắp ghép được chuyển đến nơi lắp ráp ứng dụng, thường gọi là **composition root**.

DI thường triển khai bằng composition, nhưng chúng không đồng nghĩa: một lớp có thể dùng composition mà vẫn tự `new` cộng tác viên; chỉ khi cộng tác viên được cung cấp từ bên ngoài thì mới có injection. Cả hai kỹ thuật có thể sử dụng bằng Java thuần, không cần DI container.

**Mục tiêu học tập:** sau bài này, bạn có thể nhận ra lúc nào kế thừa đang bị dùng để thay một dependency, chuyển thiết kế đó sang composition và constructor injection, đồng thời đánh giá chi phí và giới hạn của lựa chọn này.

## 2. Khi dùng kế thừa để đổi collaborator, số lớp tăng nhanh

Giả sử hệ thống xử lý đơn hàng có hai lựa chọn độc lập:

1. **Chính sách phí giao hàng:** phí cố định hoặc miễn phí khi đơn đạt ngưỡng.
2. **Kênh thông báo:** gửi email hoặc ghi thông báo ra console trong môi trường demo.

Một hướng thiết kế dễ mắc là tạo lớp con cho từng kết hợp:

```text
CheckoutService
├── FixedFeeEmailCheckoutService
├── FixedFeeConsoleCheckoutService
├── FreeThresholdEmailCheckoutService
└── FreeThresholdConsoleCheckoutService
```

Mỗi lớp con phải quyết định vừa **tính phí thế nào** vừa **thông báo bằng cách nào**. Nếu có thêm một chính sách phí và một kênh thông báo, số kết hợp có thể tăng từ `2 × 2 = 4` lên `3 × 3 = 9` lớp con. Với `m` chính sách phí và `n` kênh thông báo, cách tạo subclass cho từng kết hợp có nguy cơ tạo đến `m × n` biến thể.

Ví dụ phản ánh mùi thiết kế này:

```java
// Minh họa anti-pattern, không phải chương trình chạy độc lập.
class CheckoutService {
    long deliveryFee(long subtotalVnd) {
        return 30_000;
    }

    void notifyCustomer(String orderId, long totalVnd) {
        // Gửi email mặc định.
    }

    long checkout(String orderId, long subtotalVnd) {
        long totalVnd = subtotalVnd + deliveryFee(subtotalVnd);
        notifyCustomer(orderId, totalVnd);
        return totalVnd;
    }
}

class FreeThresholdConsoleCheckoutService extends CheckoutService {
    @Override
    long deliveryFee(long subtotalVnd) {
        return subtotalVnd >= 500_000 ? 0 : 30_000;
    }

    @Override
    void notifyCustomer(String orderId, long totalVnd) {
        System.out.println(orderId + ": " + totalVnd);
    }
}
```

Cách viết này có thể hoạt động, nhưng biến hai cộng tác viên độc lập thành các nhánh của hệ thống phân cấp lớp. Nó gây ra những rủi ro cụ thể:

- **Nhân tổ hợp biến thể:** thêm lựa chọn ở một trục buộc tạo thêm lớp cho các trục còn lại.
- **Gắn lựa chọn vào kiểu lớp:** nơi tạo `CheckoutService` phải biết đúng subclass kết hợp hai chính sách.
- **Khó kiểm thử từng phần:** muốn kiểm thử phép tính tổng mà không gửi email thật vẫn phải đối phó với hành vi được thừa kế hoặc override.
- **Phụ thuộc vào chi tiết lớp cha:** lớp con có thể cần biết thứ tự gọi phương thức, trạng thái nội bộ và các “hook” của lớp cha. Sửa lớp cha có thể ảnh hưởng đến nhiều lớp con.

**Vấn đề nằm ở trục thay đổi.** Phí giao hàng và kênh thông báo là hai hành vi cộng tác độc lập; chúng không phải là những “loại bản chất” khác nhau của dịch vụ checkout. Tách chúng thành đối tượng riêng sẽ hợp lý hơn khi cần hoán đổi thường xuyên.

## 3. Đưa hành vi thay đổi thành những cộng tác viên được kết hợp

Ta định nghĩa hai hợp đồng nhỏ, mỗi hợp đồng mô tả **vai trò mà `CheckoutService` thực sự cần**:

```text
                            Composition root
                              tạo và truyền
                               /        \
                              v          v
CheckoutService ----uses----> DeliveryFeePolicy
       |
       +------------uses----> OrderNotifier
```

`CheckoutService` giữ tham chiếu đến `DeliveryFeePolicy` và `OrderNotifier`; mỗi hành vi có thể có nhiều implementation. Composition root quyết định **cặp đối tượng cụ thể** trước khi tạo `CheckoutService`.

### 3.1. Ví dụ chạy được với Java thuần

Lưu mã sau vào `CheckoutApp.java`:

```java
import java.util.Objects;

interface DeliveryFeePolicy {
    long feeFor(long subtotalVnd);
}

final class FlatDeliveryFee implements DeliveryFeePolicy {
    private final long feeVnd;

    FlatDeliveryFee(long feeVnd) {
        if (feeVnd < 0) {
            throw new IllegalArgumentException("Phí không được âm");
        }
        this.feeVnd = feeVnd;
    }

    @Override
    public long feeFor(long subtotalVnd) {
        return feeVnd;
    }
}

final class FreeOverThresholdFee implements DeliveryFeePolicy {
    private final long thresholdVnd;
    private final long feeVnd;

    FreeOverThresholdFee(long thresholdVnd, long feeVnd) {
        if (thresholdVnd <= 0 || feeVnd < 0) {
            throw new IllegalArgumentException("Ngưỡng/phí không hợp lệ");
        }
        this.thresholdVnd = thresholdVnd;
        this.feeVnd = feeVnd;
    }

    @Override
    public long feeFor(long subtotalVnd) {
        return subtotalVnd >= thresholdVnd ? 0 : feeVnd;
    }
}

interface OrderNotifier {
    void notifyConfirmed(String orderId, long totalVnd);
}

final class ConsoleOrderNotifier implements OrderNotifier {
    @Override
    public void notifyConfirmed(String orderId, long totalVnd) {
        System.out.println("Đã xác nhận " + orderId + ", tổng: " + totalVnd);
    }
}

final class CheckoutService {
    private final DeliveryFeePolicy feePolicy;
    private final OrderNotifier notifier;

    CheckoutService(DeliveryFeePolicy feePolicy, OrderNotifier notifier) {
        this.feePolicy = Objects.requireNonNull(feePolicy, "feePolicy");
        this.notifier = Objects.requireNonNull(notifier, "notifier");
    }

    long checkout(String orderId, long subtotalVnd) {
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("Mã đơn hàng không hợp lệ");
        }
        if (subtotalVnd <= 0) {
            throw new IllegalArgumentException("Tạm tính phải dương");
        }

        long feeVnd = feePolicy.feeFor(subtotalVnd);
        if (feeVnd < 0) {
            throw new IllegalStateException("Phí giao hàng không được âm");
        }

        long totalVnd = Math.addExact(subtotalVnd, feeVnd);
        notifier.notifyConfirmed(orderId, totalVnd);
        return totalVnd;
    }
}

public class CheckoutApp {
    public static void main(String[] args) {
        // Composition root của ví dụ: tạo và lắp các đối tượng.
        DeliveryFeePolicy policy = new FreeOverThresholdFee(500_000, 30_000);
        OrderNotifier notifier = new ConsoleOrderNotifier();

        CheckoutService checkout = new CheckoutService(policy, notifier);
        checkout.checkout("ORDER-101", 600_000);  // Tổng 600_000 VND

        // Đổi chính sách chỉ tại nơi lắp ghép; CheckoutService giữ nguyên.
        CheckoutService anotherCheckout = new CheckoutService(
                new FlatDeliveryFee(25_000),
                notifier);
        anotherCheckout.checkout("ORDER-102", 100_000); // Tổng 125_000 VND
    }
}
```

Biên dịch và chạy:

```bash
javac CheckoutApp.java
java CheckoutApp
```

Kết quả mong đợi:

```text
Đã xác nhận ORDER-101, tổng: 600000
Đã xác nhận ORDER-102, tổng: 125000
```

Ở đây, `CheckoutService` không có subclass nào. Nếu cần adapter `EmailOrderNotifier`, chỉ cần triển khai `OrderNotifier` và chọn nó ở composition root. Nếu cần chính sách phí khác, chỉ cần triển khai `DeliveryFeePolicy`. Hai thay đổi độc lập không buộc tạo các lớp checkout mới cho mọi cặp kết hợp.

**Hợp đồng phải đúng nghĩa:** `DeliveryFeePolicy.feeFor` phải trả về số tiền phí không âm tính theo VND cho `subtotalVnd` hợp lệ; `OrderNotifier.notifyConfirmed` là hành vi thông báo và có thể thất bại do I/O với adapter thật. Một interface không thay thế được việc mô tả và kiểm tra semantics của các implementation.

### 3.2. So sánh khả năng mở rộng

| Khía cạnh | Kế thừa để chọn collaborator | Composition + constructor injection |
| --- | --- | --- |
| Thêm chính sách phí | Có thể cần tạo subclass cho từng kênh thông báo. | Thêm một `DeliveryFeePolicy`; chọn ở composition root. |
| Thêm kênh thông báo | Có thể cần tạo subclass cho từng chính sách phí. | Thêm một `OrderNotifier`; chọn ở composition root. |
| Lớp xử lý nghiệp vụ | Gắn với điểm mở rộng của lớp cha và subclass. | Gọi vào hợp đồng của các cộng tác viên. |
| Kiểm thử | Thường phải tạo subclass hoặc vô hiệu hóa hành vi thừa kế. | Truyền fake/stub trực tiếp. |
| Độ phức tạp còn lại | Nằm ở phân cấp lớp và quy tắc override. | Nằm ở contract, object graph, cấu hình và vòng đời đối tượng. |

Composition giảm nhu cầu **định nghĩa lớp cho từng tổ hợp**; nó không làm biến mất số cấu hình thực tế. Nếu hệ thống hỗ trợ 9 kết hợp, vẫn cần quyết định 9 kết hợp đó có hợp lệ hay không và kiểm thử các kết hợp quan trọng.

## 4. Constructor injection giúp kiểm thử mà không cần gọi hệ thống ngoài

Giả sử adapter thông báo thật sẽ gửi email. Bài test chỉ muốn xác minh nghiệp vụ cộng phí và gọi đúng collaborator, không muốn gửi bất kỳ email nào. Ta truyền một fake đơn giản qua constructor.

Lưu đoạn sau vào `CheckoutAppTest.java`, cùng thư mục với `CheckoutApp.java`:

```java
final class RecordingNotifier implements OrderNotifier {
    int callCount;
    String orderId;
    long totalVnd;

    @Override
    public void notifyConfirmed(String orderId, long totalVnd) {
        callCount++;
        this.orderId = orderId;
        this.totalVnd = totalVnd;
    }
}

public class CheckoutAppTest {
    public static void main(String[] args) {
        // Stub phí cố định 7_000 VND, không cần tạo hệ thống giao hàng.
        DeliveryFeePolicy feePolicy = subtotalVnd -> 7_000;
        RecordingNotifier fake = new RecordingNotifier();
        CheckoutService checkout = new CheckoutService(feePolicy, fake);

        long returnedTotal = checkout.checkout("ORDER-TEST", 100_000);

        if (returnedTotal != 107_000
                || fake.callCount != 1
                || !"ORDER-TEST".equals(fake.orderId)
                || fake.totalVnd != 107_000) {
            throw new AssertionError("Checkout xử lý sai cộng tác viên");
        }
        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac CheckoutApp.java CheckoutAppTest.java
java CheckoutAppTest
```

Kết quả: `PASS`.

Bài test này kiểm tra được **cách `CheckoutService` hợp tác với các dependency** mà không cần DI container hoặc thư viện mocking. Nó **không kiểm tra** kết nối email, độ chính xác khi tính phí ở adapter thực tế, cấu hình hay cách xử lý lỗi của hệ thống ngoài. Những điều đó cần kiểm thử contract hoặc kiểm thử tích hợp phù hợp.

Điểm quan trọng là ta không cần thêm `TestCheckoutService extends CheckoutService` để thay phương thức thông báo: đối tượng fake đã được truyền vào qua một **đường phụ thuộc tường minh**.

## 5. Kết hợp đối tượng, Strategy, DIP và IoC có quan hệ thế nào?

Các khái niệm thường đi cùng nhau nhưng đảm nhiệm vai trò khác nhau:

| Khái niệm | Vai trò trong ví dụ |
| --- | --- |
| **Composition** | `CheckoutService` chứa và sử dụng hai đối tượng `feePolicy`, `notifier`. |
| **Strategy pattern** | `DeliveryFeePolicy` đóng gói các thuật toán tính phí có thể hoán đổi. |
| **Dependency Injection** | Constructor nhận hai đối tượng đã được tạo bên ngoài. |
| **Inversion of Control** | `CheckoutApp.main` kiểm soát việc chọn và lắp ghép thay cho `CheckoutService`. |
| **Dependency Inversion Principle (DIP)** | Nghiệp vụ phụ thuộc vào các hợp đồng `DeliveryFeePolicy`, `OrderNotifier` thay vì adapter cụ thể. |
| **Open/Closed Principle (OCP)** | Có thể bổ sung một chính sách tính phí bằng implementation mới mà không sửa logic checkout, nếu hợp đồng không đổi. |

Không phải mọi composition đều tuân thủ DIP. Ví dụ này **có composition nhưng vẫn gắn với cách tạo phụ thuộc**:

```java
// Mã minh họa: lựa chọn phụ thuộc bị cố định bên trong lớp.
class TightlyCoupledCheckout {
    private final DeliveryFeePolicy feePolicy = new FlatDeliveryFee(30_000);
}
```

Nó giữ một đối tượng cộng tác nhưng vẫn quyết định implementation. DI đưa quyết định tạo và chọn cộng tác viên ra ngoài. Ngược lại, việc truyền thẳng `VendorEmailSdk` vào constructor bằng DI vẫn có thể làm nghiệp vụ gắn với API của một vendor; **DI không tự bảo đảm DIP**.

Tương tự, OCP không có nghĩa là không bao giờ sửa lớp cũ. Nếu yêu cầu nghiệp vụ hoặc ý nghĩa của hợp đồng thay đổi, sửa lớp hiện có là bình thường. Lợi ích là những **biến thể dự kiến** có thể thêm ở vị trí mở rộng hợp lý mà không phải sửa logic điều phối.

## 6. Khi nào kế thừa vẫn là lựa chọn đúng?

Nguyên tắc ưu tiên composition không đồng nghĩa với “cấm `extends`”. Kế thừa có thể phù hợp khi:

- Có quan hệ **is-a** thật sự, và lớp con có thể thay thế lớp cha mà vẫn đáp ứng các giả định, tiền điều kiện và hậu điều kiện liên quan (**Liskov Substitution Principle**).
- Có một giao thức mở rộng ổn định, được tài liệu hóa và kiểm soát rõ; chẳng hạn framework yêu cầu kế thừa một lớp cơ sở với những hook đã định nghĩa.
- Các lớp chia sẻ một **abstraction** ổn định, không phải chỉ tình cờ dùng chung vài dòng mã.

Ví dụ, việc nhiều lớp cùng triển khai `OrderNotifier` thể hiện tính đa hình qua interface. Composition không loại bỏ đa hình hay nhu cầu tổ chức kiểu dữ liệu; nó giảm mức độ phụ thuộc vào **kế thừa implementation** để thay các cộng tác viên.

Một quy tắc nhận biết hữu ích:

- Nếu câu mô tả là **“A là một loại B”** và mọi lời gọi hợp lệ trên B cũng phải có nghĩa với A, hãy xem xét phân cấp kiểu.
- Nếu câu mô tả là **“A cần dùng B để hoàn thành công việc”**, đặc biệt khi B có thể thay đổi độc lập, hãy xem xét composition rồi inject B.

**Ví dụ:** `CheckoutService` “dùng chính sách giao hàng”, không phải “là một chính sách giao hàng”. Vì vậy, dịch vụ nên chứa `DeliveryFeePolicy` hơn là kế thừa nó hoặc tạo subclass chỉ để đổi chính sách.

## 7. Chọn đúng thời điểm và nơi thay collaborator

### 7.1. Thay tại startup khác thay ở từng request

Constructor injection thường chọn implementation **khi xây dựng object graph**. Với ví dụ trên, một `CheckoutService` giữ chính sách phí đã được truyền vào; nó không tự đổi chính sách sau mỗi request.

Nếu chính sách phụ thuộc dữ liệu của từng đơn, chẳng hạn khu vực giao hàng hoặc hạng thành viên, có thể:

- Inject một `DeliveryFeePolicy` biết tự tính dựa vào dữ liệu đầu vào được truyền khi gọi; hoặc
- Inject một `DeliveryFeePolicyResolver`/factory có nhiệm vụ chọn policy phù hợp theo ngữ cảnh đơn hàng.

Việc dùng resolver chỉ nên thực hiện khi sự thay đổi theo request là nhu cầu thật. Không cần biến các lựa chọn cố định thành một registry động khó theo dõi. Tránh để lớp nghiệp vụ gọi thẳng vào một service locator toàn cục như `Container.get(...)` để tìm dependency: điều đó che giấu những gì lớp cần và khiến kiểm thử khó cô lập hơn.

### 7.2. Phạm vi sử dụng và vòng đời phải phù hợp

Composition và DI cho ta khả năng truyền cùng một collaborator cho nhiều dịch vụ hoặc tạo collaborator mới cho từng dịch vụ. Nhưng người thiết kế phải quyết định:

- Một chính sách tính phí **bất biến, không giữ trạng thái request** có thể chia sẻ nếu triển khai của nó an toàn khi dùng đồng thời.
- Đối tượng giữ trạng thái **riêng cho một request** không nên bị vô tình đưa vào dịch vụ chia sẻ lâu dài khiến dữ liệu giữa các request bị trộn.
- Collaborator sở hữu kết nối, stream, thread pool hoặc client có tài nguyên phải có quy tắc **ai tạo, ai đóng, đóng lúc nào**. Constructor injection không tự động giải phóng tài nguyên.

DI container có thể giúp cấu hình scope hoặc lifecycle, nhưng không sửa được một đối tượng không thread-safe và không tự làm mọi scope tương thích nhau.

### 7.3. Tránh trừu tượng hóa vượt nhu cầu

Không phải biến thể nào cũng đáng có interface riêng. Một hàm tính toán đơn giản, đối tượng dữ liệu, giá trị tiền tệ hoặc bộ sưu tập tạm thường có thể tạo trực tiếp. Tạo interface cho từng lớp và inject mọi `new` làm số lượng đối tượng cần hiểu tăng lên mà chưa chắc giảm gắn kết.

Chi phí của composition gồm nhiều collaborator, constructor dài, mã lắp ráp, contract phải bảo trì và số kết hợp cấu hình phải kiểm tra. Nếu một lớp nhận quá nhiều dependency, nên đánh giá lại trách nhiệm của nó trước khi chỉ thêm container để tự lắp ghép.

## 8. Cách chuyển một hệ thống đang dùng subclass sang composition

Khi gặp một phân cấp lớp dùng override để thay thành phần cộng tác, có thể đi theo các bước:

1. **Xác định trục biến thiên:** liệt kê hành vi nào khác nhau giữa các subclass và hành vi nào luôn giống nhau.
2. **Tách hợp đồng collaborator:** đặt tên theo vai trò cần sử dụng, ví dụ `DeliveryFeePolicy`, thay vì theo chi tiết công nghệ hoặc subclass đang có.
3. **Chuyển logic từng biến thể:** triển khai các hợp đồng bằng các lớp độc lập, tránh dùng dữ liệu private/protected của lớp gốc.
4. **Truyền qua constructor:** lớp nghiệp vụ nhận collaborator cần thiết và gọi nó qua hợp đồng; kiểm tra dependency bắt buộc tại điểm tạo.
5. **Di chuyển việc chọn implementation:** đưa cấu hình và việc tạo đối tượng tới composition root; xác định scope và chủ sở hữu tài nguyên.
6. **Kiểm thử hành vi và tích hợp:** dùng fake cho nghiệp vụ, kiểm thử thật cho adapter và lắp ghép; cuối cùng bỏ subclass không còn cần thiết.

Trong một hệ thống thực tế, không nhất thiết thực hiện toàn bộ thay đổi một lần. Có thể chuyển từng trục biến thiên để giữ nguyên hành vi trong khi thu hẹp phân cấp lớp.

## 9. Bài tập tự luyện

**Bối cảnh:** `ReportService` đang có bốn subclass `CsvFileReportService`, `CsvEmailReportService`, `PdfFileReportService`, `PdfEmailReportService`. Từng lớp override cách **định dạng báo cáo** và **xuất báo cáo**.

Hãy thực hiện:

1. Chỉ ra hai trục biến thiên và giải thích vì sao mỗi trục phù hợp với collaborator riêng.
2. Đề xuất hai hợp đồng, chẳng hạn `ReportFormatter` (đầu vào là dữ liệu báo cáo, đầu ra là nội dung đã định dạng) và `ReportPublisher` (nhận nội dung cùng thông tin đích).
3. Viết constructor `ReportService(ReportFormatter formatter, ReportPublisher publisher)`; tạo một composition root lắp `CsvFormatter` với `EmailPublisher`.
4. Viết fake publisher để xác minh báo cáo được xuất đúng một lần; chỉ rõ phần nào vẫn cần kiểm thử tích hợp.
5. Nêu một trường hợp kế thừa có thể vẫn hợp lý, và một trường hợp không cần thêm interface.

**Gợi ý đối chiếu:** `ReportService` điều phối tác vụ tạo báo cáo, còn formatter và publisher thay đổi độc lập. Composition root chọn từng implementation; bài test đơn vị nhận fake publisher nên không cần ghi file hay gửi email. Kiểm thử tích hợp vẫn cần xác minh định dạng CSV/PDF và cơ chế xuất thật. Nếu framework có một lớp cơ sở với hợp đồng mở rộng ổn định, kế thừa có thể phù hợp; nếu đang tạo một DTO cho từng báo cáo, không cần đưa DTO đó qua DI.

**Ghi nhớ:** Khi yêu cầu là **thay thành phần mà một lớp sử dụng**, hãy ưu tiên tách thành collaborator và kết hợp bằng quan hệ *has-a/uses-a*. Constructor injection làm các dependency tường minh; composition root kiểm soát việc tạo và lắp ghép. Kế thừa vẫn có vai trò khi có quan hệ *is-a* hợp lệ, còn scope, vòng đời, kiểm thử tích hợp và độ rõ ràng của hợp đồng vẫn phải được thiết kế riêng.
