# Lợi ích, chi phí và giới hạn của việc áp dụng Dependency Injection

## 1. Nhìn DI như một quyết định thiết kế có đánh đổi

**Dependency Injection (DI)** là cách truyền những đối tượng mà một thành phần cần sử dụng từ bên ngoài vào, thay vì để thành phần đó tự tạo hoặc tự tìm kiếm chúng. Đây là một kỹ thuật thực hiện **Inversion of Control (IoC)**: quyền quyết định cách tạo và lắp ghép các đối tượng được chuyển ra khỏi lớp đang thực hiện nghiệp vụ.

Ví dụ, `CheckoutService` cần một thành phần thanh toán. Nếu nó tự gọi `new BankPaymentGateway(...)`, phần xử lý đơn hàng sẽ gắn với cách khởi tạo cổng thanh toán. Khi nhận `PaymentGateway` qua constructor, dịch vụ chỉ cần biết cách **sử dụng** cổng thanh toán; nơi khởi động ứng dụng sẽ chịu trách nhiệm **chọn, tạo và lắp ghép** đối tượng phù hợp.

DI thường đem lại khả năng thay thế phụ thuộc, kiểm thử dễ hơn và ranh giới trách nhiệm rõ hơn. Đổi lại, ta phải quản lý cấu hình, luồng khởi tạo, phạm vi chia sẻ và vòng đời đối tượng. **DI là công cụ để kiểm soát sự phụ thuộc, không phải mục tiêu cần áp dụng cho mọi lớp.**

Sau bài này, bạn có thể:

- Giải thích DI giúp giảm mức độ gắn kết và cải thiện khả năng kiểm thử như thế nào.
- Nhận diện chi phí về mã nguồn, cấu hình, gỡ lỗi, phạm vi sử dụng và vòng đời đối tượng.
- Phân biệt lợi ích thật của DI với những lợi ích mà DI **không tự bảo đảm**.
- Chọn DI thủ công với Java thuần hoặc DI container theo độ phức tạp của ứng dụng.

## 2. Ví dụ xuyên suốt: thay thế phụ thuộc tại composition root

Xét dịch vụ thanh toán đơn hàng. Thiết kế gắn chặt có thể bắt đầu như sau:

```java
final class CheckoutService {
    String checkout(String orderId, long amountVnd) {
        BankPaymentGateway gateway = new BankPaymentGateway(/* cấu hình */);
        return gateway.pay(orderId, amountVnd);
    }
}
```

Trong cách viết trên, `CheckoutService` vừa xử lý ca sử dụng, vừa quyết định công nghệ thanh toán và cách tạo đối tượng. Chẳng hạn, để kiểm thử mà không thực hiện giao dịch thật, ta phải thay đổi mã lớp này hoặc dùng kỹ thuật can thiệp phức tạp vào quá trình tạo đối tượng.

Với **constructor injection**, ta chuyển quyết định đó ra ngoài. Ví dụ Java sau không cần framework; đặt toàn bộ mã trong `App.java`:

```java
import java.util.Objects;

interface PaymentGateway {
    String pay(String orderId, long amountVnd);
}

final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    String checkout(String orderId, long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amountVnd phải dương");
        }
        return gateway.pay(orderId, amountVnd);
    }
}

// Chỉ mô phỏng thanh toán; không kết nối tới ngân hàng.
final class DemoPaymentGateway implements PaymentGateway {
    @Override
    public String pay(String orderId, long amountVnd) {
        return "demo-transaction-for-" + orderId;
    }
}

public class App {
    public static void main(String[] args) {
        // Composition root: nơi tạo và nối các đối tượng của ứng dụng.
        PaymentGateway gateway = new DemoPaymentGateway();
        CheckoutService checkout = new CheckoutService(gateway);

        System.out.println(checkout.checkout("ORDER-42", 120_000));
    }
}
```

Chạy bằng `javac App.java` rồi `java App` với JDK phù hợp. Trong ứng dụng thật, `DemoPaymentGateway` có thể được thay bằng adapter ngân hàng nhận HTTP client, thông tin cấu hình và các đối tượng liên quan. **`CheckoutService` không cần thay đổi khi đổi cách tạo hoặc triển khai cổng thanh toán**, miễn là hợp đồng `PaymentGateway` vẫn phù hợp.

```text
Composition root (App.main)
   | tạo DemoPaymentGateway
   | tạo CheckoutService(gateway)
   v
CheckoutService ---> PaymentGateway <--- DemoPaymentGateway
  (sử dụng)          (hợp đồng)        (triển khai)
```

Đây là **DI thủ công**: mã nguồn trực tiếp tạo và truyền phụ thuộc. DI container tự động hóa một phần quá trình lắp ghép nhưng không phải điều kiện để có DI.

## 3. Những lợi ích có thể quan sát được

### 3.1. Giảm gắn kết với chi tiết triển khai

`CheckoutService` không cần biết cổng thanh toán được khởi tạo ra sao, gọi API bằng thư viện nào hoặc thông tin xác thực được nạp từ đâu. Khi phụ thuộc thay đổi, phạm vi sửa đổi thường tập trung ở adapter và composition root.

Tuy nhiên, mức độ tách biệt thực sự phụ thuộc vào **chất lượng hợp đồng**: nếu interface làm lộ kiểu dữ liệu riêng của một nhà cung cấp, lớp sử dụng vẫn gắn chặt với nhà cung cấp đó. Việc tạo một interface cho mỗi lớp cũng không tự động tạo ra kiến trúc tốt.

### 3.2. Kiểm thử nghiệp vụ nhanh và có kiểm soát

Ta có thể truyền một đối tượng giả vào lớp cần kiểm thử. Ví dụ sau đặt trong `CheckoutTest.java`, cùng thư mục với `App.java` đã biên dịch:

```java
public class CheckoutTest {
    static final class SpyGateway implements PaymentGateway {
        String receivedOrderId;
        long receivedAmount;

        @Override
        public String pay(String orderId, long amountVnd) {
            receivedOrderId = orderId;
            receivedAmount = amountVnd;
            return "fake-transaction";
        }
    }

    public static void main(String[] args) {
        SpyGateway spy = new SpyGateway();
        CheckoutService service = new CheckoutService(spy);

        String result = service.checkout("ORDER-1", 30_000);
        if (!"fake-transaction".equals(result)
                || !"ORDER-1".equals(spy.receivedOrderId)
                || spy.receivedAmount != 30_000) {
            throw new AssertionError("Checkout không chuyển đúng yêu cầu");
        }

        System.out.println("PASS");
    }
}
```

Chạy `javac App.java CheckoutTest.java` và `java CheckoutTest`. Bài kiểm thử trên không cần kết nối mạng hay DI container: nó kiểm tra hành vi `CheckoutService` và cách dịch vụ sử dụng hợp đồng `PaymentGateway`.

**Giới hạn quan trọng:** kiểm thử với fake chỉ cho thấy lớp dùng phụ thuộc đúng theo giả định của test. Nó **không chứng minh** adapter thanh toán thật, cấu hình, giao dịch và cách các đối tượng được lắp ghép hoạt động đúng. Vẫn cần các bài kiểm thử tích hợp thích hợp.

### 3.3. Tập trung việc cấu hình và khởi tạo

Khi ứng dụng có nhiều môi trường hoặc nhiều lựa chọn triển khai, composition root là nơi rõ ràng để quyết định cung cấp phụ thuộc nào. Chẳng hạn, môi trường phát triển có thể dùng adapter mô phỏng; môi trường chạy thật dùng adapter tích hợp với nhà cung cấp thanh toán. Thành phần nghiệp vụ không cần rải điều kiện `if (environment == ...)` trong mã của mình.

Điều này giúp xác định **ai chịu trách nhiệm tạo tài nguyên**, **ai sở hữu tài nguyên** và **khi nào phải giải phóng**. Nhưng bản thân việc truyền đối tượng vào constructor không tự đóng kết nối hay quyết định đối tượng có an toàn khi chia sẻ giữa nhiều luồng hay không.

### 3.4. Làm rõ những gì lớp cần để hoạt động

Constructor như `CheckoutService(PaymentGateway gateway)` cho thấy lớp không hoạt động nếu thiếu cổng thanh toán. Một constructor với quá nhiều tham số lại là dấu hiệu đáng xem xét: lớp có thể đang ôm quá nhiều trách nhiệm, hoặc các phụ thuộc chưa được gom thành những vai trò có ý nghĩa.

DI cũng giúp áp dụng nguyên tắc **Dependency Inversion Principle (DIP)** khi nghiệp vụ phụ thuộc vào hợp đồng ổn định thay vì chi tiết hạ tầng. Nhưng cần phân biệt: DIP là một nguyên tắc thiết kế; DI là kỹ thuật cung cấp phụ thuộc. Có thể dùng DI mà vẫn vi phạm DIP, ví dụ truyền thẳng một SDK vendor cụ thể vào phần nghiệp vụ.

## 4. Chi phí phải trả khi dùng DI

| Loại chi phí | Biểu hiện | Cách kiểm soát |
| --- | --- | --- |
| Mã lắp ghép | Phải tạo và nối các đối tượng; nhiều constructor hoặc factory hơn. | Tập trung tại composition root; chỉ trừu tượng hóa những điểm thật sự cần thay thế hoặc cô lập. |
| Độ phức tạp của đồ thị phụ thuộc | Một đối tượng kéo theo nhiều đối tượng khác; có thể xuất hiện chu trình `A -> B -> A`. | Giữ luồng phụ thuộc có hướng; chia lại trách nhiệm để loại bỏ chu trình. |
| Cấu hình sai | Truyền nhầm triển khai, thiếu phụ thuộc, dùng sai cấu hình môi trường. | Kiểm tra cấu hình và khởi tạo trong bài kiểm thử tích hợp hoặc smoke test. |
| Vòng đời và phạm vi chia sẻ | Dùng chung đối tượng có trạng thái giữa nhiều request, giữ tài nguyên quá lâu hoặc đóng quá sớm. | Định nghĩa rõ ai tạo, ai dùng, ai đóng; kiểm tra thread safety và scope. |
| Khả năng lần dấu khi có lỗi | Phải theo từ lớp nghiệp vụ tới nơi tạo đối tượng; với container có thể cần xem binding/configuration. | Đặt tên rõ ràng, giữ cấu hình gần composition root, hạn chế đăng ký động không cần thiết. |
| Chi phí học và vận hành framework | Annotation, cơ chế quét lớp, proxy, quy tắc chọn bean và lỗi khi khởi động. | Bắt đầu bằng constructor injection trong Java thuần; thêm container khi khối lượng lắp ghép đủ lớn. |

### 4.1. Chi phí không chỉ là số dòng mã

Không phải dự án nào cũng cần nhiều interface hoặc framework. Với một ứng dụng nhỏ chỉ có một implementation ổn định, việc thêm hàng loạt factory và lớp trung gian có thể khiến người đọc phải mở nhiều file mới hiểu được một chức năng đơn giản.

Chi phí đáng chú ý hơn số dòng mã là **chi phí nhận thức**: người bảo trì phải biết một dependency đến từ đâu, triển khai nào được chọn, đối tượng được tái sử dụng trong bao lâu và điều gì xảy ra khi khởi tạo thất bại.

### 4.2. Scope và vòng đời có thể tạo lỗi khó phát hiện

Ba mô hình thường gặp:

- **Một đối tượng dùng chung** trong ứng dụng: phù hợp với thành phần không giữ trạng thái thay đổi theo người dùng, hoặc thành phần đã được thiết kế thread-safe. Không được tự suy luận mọi singleton đều thread-safe.
- **Đối tượng mới cho mỗi lần sử dụng**: giảm nguy cơ chia sẻ trạng thái, nhưng có thể tốn chi phí khởi tạo và tạo nhiều tài nguyên.
- **Đối tượng gắn với một request hoặc một đơn vị công việc**: hữu ích với trạng thái hoặc tài nguyên chỉ nên tồn tại trong phạm vi đó; cần bảo đảm không bị giữ lại bởi đối tượng sống lâu hơn.

Ví dụ, truyền một đối tượng chứa `currentUserId` có thể thay đổi vào dịch vụ dùng chung cho mọi request sẽ dễ gây rò rỉ dữ liệu giữa các yêu cầu nếu không quản lý đồng thời đúng cách. Một lớp sở hữu kết nối, stream hoặc executor phải có quy tắc đóng tài nguyên riêng; **DI không tự biến đối tượng thành thread-safe và không tự quản lý việc đóng tài nguyên**. Một số DI container có hỗ trợ lifecycle hook, nhưng phải cấu hình và dùng đúng.

### 4.3. Container giảm mã nối dây nhưng tăng cơ chế ngầm

DI container có thể giải quyết sự lặp lại khi đồ thị phụ thuộc lớn, quản lý scope và kiểm tra một số lỗi khởi tạo. Đổi lại, việc chọn implementation có thể phụ thuộc vào annotation, cấu hình, tên binding hoặc quy tắc ưu tiên. Một số lỗi chỉ xuất hiện ở thời điểm ứng dụng khởi động hoặc khi một nhánh cấu hình được sử dụng.

Không nên suy ra rằng DI container luôn làm ứng dụng nhanh hơn hoặc chậm hơn đáng kể. Chi phí tạo và tra cứu đối tượng phụ thuộc framework, cấu hình và thời điểm thực hiện; với dịch vụ gọi mạng hoặc cơ sở dữ liệu, chi phí I/O thường quan trọng hơn. Chỉ tối ưu dựa trên đo đạc phù hợp.

## 5. Giới hạn: DI không giải quyết thay các vấn đề thiết kế khác

1. **Không sửa được nghiệp vụ sai hoặc lớp ôm quá nhiều trách nhiệm.** Một `CheckoutService` có 15 dependency vẫn có thể là một lớp khó bảo trì, dù cả 15 dependency đều được inject.
2. **Không bảo đảm phụ thuộc thật có thể thay thế một cách an toàn.** Hai adapter có cùng interface vẫn có thể khác nhau về thời gian phản hồi, lỗi, giao dịch hoặc tính nhất quán. Cần hợp đồng rõ ràng và kiểm thử tích hợp.
3. **Không thay thế việc quản lý cấu hình và bí mật.** DI truyền một HTTP client hoặc cấu hình vào đối tượng; nó không tự bảo vệ credential hay kiểm soát quyền truy cập.
4. **Không loại bỏ sự phụ thuộc giữa các thành phần.** Quan hệ sử dụng vẫn tồn tại, chỉ được thể hiện rõ và dịch chuyển quyền quyết định cách tạo, lắp ghép ra bên ngoài.
5. **Không làm mọi đối tượng cần được inject.** Value object, DTO, tập hợp tạm, kết quả tính toán hoặc đối tượng đơn giản được tạo trong phạm vi hàm thường không cần đi qua DI.

Một dấu hiệu sai hướng là dùng **Service Locator** trong mã nghiệp vụ:

```java
// Ví dụ cần tránh trong lớp nghiệp vụ:
PaymentGateway gateway = Registry.get(PaymentGateway.class);
```

Lúc này, dependency không hiện diện trong constructor; lớp phải biết registry toàn cục và các bài kiểm thử phải chuẩn bị trạng thái của registry. Với các dependency bắt buộc, **constructor injection thường minh bạch hơn**.

Tương tự, không cần biến tất cả lời gọi `new` thành DI. Tạo `new Money(...)` hoặc `new ArrayList<>()` trong logic thường là bình thường. Cần quan tâm chủ yếu tới những **cộng tác viên** có hành vi, hiệu ứng phụ, cấu hình hoặc vòng đời cần được quản lý ở ranh giới ứng dụng.

## 6. Khi nào DI đem lại giá trị?

| Tình huống | Quyết định thường hợp lý | Lý do |
| --- | --- | --- |
| Dịch vụ gửi email, thanh toán, gọi API hoặc truy cập dữ liệu | Inject collaborator qua constructor. | Dễ thay adapter và kiểm thử nghiệp vụ không cần I/O thật. |
| Ứng dụng có nhiều adapter hoặc nhiều cấu hình môi trường | Lắp ghép tập trung tại composition root; cân nhắc container khi graph lớn. | Kiểm soát lựa chọn triển khai và vòng đời ở một nơi. |
| Hàm tính thuế thuần túy, không giữ trạng thái, không I/O | Gọi hàm hoặc tạo đối tượng đơn giản trực tiếp. | DI khó mang lại lợi ích tương xứng với độ phức tạp thêm vào. |
| Script nhỏ, một dependency cố định, ít kiểm thử | DI thủ công tối thiểu hoặc khởi tạo trực tiếp. | Giữ thiết kế dễ đọc; có thể tách sau khi xuất hiện nhu cầu thật. |
| Thành phần giữ trạng thái theo request hoặc nắm tài nguyên cần đóng | Inject được, nhưng phải thiết kế scope/ownership rõ ràng. | DI không tự giải quyết chia sẻ trạng thái và giải phóng tài nguyên. |

Có thể tự đánh giá trước khi tạo một abstraction mới:

1. Phụ thuộc này có liên quan tới I/O, thời gian, random, môi trường, hoặc hệ thống bên ngoài khiến bài kiểm thử khó kiểm soát không?
2. Có khả năng cần thay implementation, thay cấu hình hoặc mô phỏng hành vi ở ranh giới này không?
3. Đối tượng có vòng đời, tài nguyên hoặc trạng thái cần chủ sở hữu rõ ràng không?
4. Chi phí thêm abstraction và mã lắp ghép có thấp hơn chi phí duy trì sự gắn kết hiện tại không?

Nếu câu trả lời chủ yếu là **có**, constructor injection và composition root thường là điểm khởi đầu tốt. Nếu chủ yếu là **không**, thiết kế đơn giản có thể phù hợp hơn; chỉ mở rộng khi xuất hiện nhu cầu được chứng minh.

## 7. Bài tập thực hành và cách tự kiểm tra

**Bối cảnh:** `ReportService` tạo báo cáo, lấy dữ liệu từ database, định dạng nội dung và gửi qua email.

Hãy thử:

1. Xác định những collaborator cần inject (gợi ý: đọc dữ liệu, gửi email) và phần nào có thể là hàm thuần (gợi ý: định dạng nội dung khi không có trạng thái ngoài).
2. Phác thảo constructor của `ReportService` và một composition root sử dụng adapter thật trong ứng dụng, adapter fake trong test.
3. Chỉ ra ai tạo và đóng tài nguyên database; phân biệt đối tượng kết nối có vòng đời ngắn với thành phần dùng chung quản lý connection pool.
4. Xác định ít nhất một bài test đơn vị với fake và một bài test tích hợp cần adapter thật hoặc môi trường thử nghiệm tương đương.

Một thiết kế hợp lý có thể là `ReportService(ReportRepository repository, EmailSender sender)`, nơi lớp này chỉ điều phối ca sử dụng. Composition root khởi tạo các adapter tương ứng; quản lý tài nguyên database theo contract của thư viện được dùng. Test đơn vị xác minh dữ liệu báo cáo được chuyển cho `EmailSender`; test tích hợp kiểm tra truy vấn, ánh xạ dữ liệu, kết nối và cấu hình gửi email trong môi trường kiểm thử.

**Điểm cần nhớ:** DI có giá trị khi nó làm cho phần sử dụng phụ thuộc độc lập hơn với phần tạo và lắp ghép, giúp kiểm thử và thay đổi triển khai có kiểm soát. Hãy cân nhắc lợi ích đó cùng chi phí cấu hình, độ phức tạp đồ thị, scope và vòng đời; bắt đầu bằng Java thuần, và chỉ dùng container khi mức độ phức tạp của ứng dụng thực sự cần nó.
