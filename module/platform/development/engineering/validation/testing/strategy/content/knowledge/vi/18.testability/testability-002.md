# Thiết kế điểm giao tiếp giúp kiểm tra hành vi độc lập

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, khả năng kiểm thử (testability) cần được xem là một thuộc tính của thiết kế phần mềm. Một thành phần dễ kiểm thử khi nhóm có thể kích hoạt hành vi cần đánh giá, kiểm soát các điều kiện đầu vào và phụ thuộc, quan sát kết quả, rồi lặp lại phép kiểm tra mà không phải dựng toàn bộ hệ thống hoặc dựa vào môi trường bên ngoài khó kiểm soát.

Một cách thiết kế hữu ích là tạo **điểm giao tiếp (seam)** tại ranh giới giữa logic cần kiểm tra và những yếu tố bên ngoài như cơ sở dữ liệu, mạng, đồng hồ hệ thống, bộ sinh mã định danh, hàng đợi hoặc dịch vụ của nhà cung cấp. Điểm giao tiếp cho phép thay thế hoặc cấu hình cách một phụ thuộc hoạt động trong một phép kiểm thử. Khi ranh giới được thiết kế rõ, nhóm có thể kiểm tra hành vi của thành phần một cách độc lập, đồng thời vẫn có thể kiểm tra adapter và toàn bộ tích hợp ở những lớp phù hợp.

Mục tiêu không phải là tạo interface cho mọi lớp hoặc mock mọi phụ thuộc. Mục tiêu là làm cho hành vi quan trọng có thể kiểm tra được với chi phí hợp lý, kết quả đáng tin cậy và cấu trúc đủ gần với cách phần mềm thực sự vận hành.

## 1. Testability và điểm giao tiếp (seam) là gì?

**Testability** là mức độ dễ dàng mà một thành phần hoặc hệ thống có thể được kiểm tra để xác định nó có đáp ứng hành vi mong đợi hay không. Khả năng này phụ thuộc vào cách thiết kế đầu vào, đầu ra, trạng thái, phụ thuộc, cấu hình và tín hiệu quan sát.

**Seam** là một vị trí trong thiết kế nơi nhóm có thể thay đổi cách một phần của chương trình được kết nối hoặc được thực thi mà không phải sửa chính logic đang muốn kiểm tra. Trong kiểm thử, seam thường được dùng để đưa một implementation thay thế vào thay cho phụ thuộc thật.

Ví dụ, một dịch vụ đặt hàng cần kiểm tra thanh toán qua nhà cung cấp bên ngoài. Nếu `OrderService` tự tạo HTTP client, tự đọc URL từ biến môi trường và gọi thẳng nhà cung cấp, test đơn vị khó kiểm soát phản hồi, timeout và lỗi mạng. Nếu dịch vụ phụ thuộc vào một cổng `PaymentGateway` được truyền từ bên ngoài, test có thể cung cấp fake hoặc stub để mô phỏng thanh toán thành công, bị từ chối hoặc timeout.

```text
Không có seam rõ ràng:

OrderService -----> HTTP client tự tạo -----> Payment Provider
     |
     +---- test khó kiểm soát mạng, cấu hình và phản hồi

Có seam rõ ràng:

                 +--> PaymentGateway thật --> Payment Provider
OrderService ---|
                 +--> FakePaymentGateway --> Test
```

Điểm giao tiếp có thể là interface, function parameter, constructor injection, callback, adapter, port, cấu hình hoặc một ranh giới dữ liệu. Không phải seam nào cũng cần interface; điều quan trọng là phụ thuộc có thể được thay thế hoặc điều khiển tại một vị trí có chủ đích.

## 2. Vì sao cần thiết kế để kiểm tra hành vi độc lập?

Khi logic nghiệp vụ gắn chặt với hạ tầng, một phép kiểm thử nhỏ có thể cần khởi động cơ sở dữ liệu, mở kết nối mạng, tạo tài khoản bên ngoài hoặc chờ thời gian thực. Điều này làm test chậm, dễ lỗi và khó xác định nguyên nhân khi thất bại.

Thiết kế điểm giao tiếp rõ giúp:

- **Cô lập hành vi:** kiểm tra quy tắc nghiệp vụ mà không phụ thuộc vào trạng thái của hệ thống bên ngoài.
- **Kiểm soát điều kiện:** chủ động cung cấp dữ liệu, thời gian, lỗi, phản hồi và thứ tự sự kiện.
- **Tái lập kết quả:** chạy lại cùng một test với cùng điều kiện và nhận kết quả ổn định.
- **Chẩn đoán dễ hơn:** xác định lỗi nằm trong logic, adapter hay môi trường tích hợp.
- **Phản hồi sớm:** chạy test nhỏ thường xuyên trong quá trình phát triển.
- **Giảm chi phí môi trường:** không phải dựng toàn bộ hạ tầng cho mọi trường hợp kiểm tra.
- **Hỗ trợ thay đổi:** thay implementation của phụ thuộc mà không phải viết lại logic nghiệp vụ.

Khả năng kiểm thử cũng tạo ra lợi ích thiết kế rộng hơn. Một thành phần có đầu vào, đầu ra và trách nhiệm rõ thường dễ hiểu, dễ bảo trì và dễ thay thế. Tuy nhiên, việc thêm quá nhiều lớp trừu tượng cũng có chi phí. Ranh giới nên phản ánh một phụ thuộc hoặc biến động thực sự, không chỉ được tạo ra để làm cho test trông linh hoạt.

## 3. Nhận diện những phụ thuộc làm test khó kiểm soát

Trước khi thiết kế seam, hãy tìm các nguồn không xác định hoặc có tác dụng phụ trong thành phần.

### Phụ thuộc vào thời gian

Các lệnh như `Instant.now()`, `LocalDate.now()` hoặc `System.currentTimeMillis()` làm kết quả phụ thuộc thời điểm chạy. Test có thể thất bại vào thời điểm khác, qua ngày mới hoặc tại múi giờ khác.

Ví dụ, quy tắc “đơn hàng hết hạn sau 15 phút” không nên phải chờ 15 phút trong test. Có thể truyền một `Clock` vào thành phần và dùng đồng hồ giả để kiểm tra trước, đúng và sau thời điểm hết hạn.

### Phụ thuộc vào ngẫu nhiên và mã định danh

UUID, số ngẫu nhiên, token hoặc giá trị sinh tự động có thể khiến kết quả khó dự đoán. Nếu test cần xác nhận mã được tạo và lưu đúng, hãy kiểm soát nguồn sinh mã hoặc chỉ kiểm tra các thuộc tính có ý nghĩa thay vì so sánh một giá trị ngẫu nhiên cố định.

### Phụ thuộc vào mạng và dịch vụ bên ngoài

HTTP API, payment gateway, email, SMS, dịch vụ bản đồ hoặc hệ thống đối tác có thể chậm, giới hạn tốc độ, thay đổi dữ liệu hoặc không sẵn sàng. Logic nghiệp vụ không nên phải tự quản lý chi tiết giao thức của mọi nhà cung cấp.

### Phụ thuộc vào lưu trữ và trạng thái dùng chung

Database, filesystem, cache, object storage và message broker tạo ra trạng thái tồn tại ngoài vòng đời của một phép kiểm thử. Nếu test không thể chuẩn bị và dọn trạng thái rõ ràng, kết quả có thể phụ thuộc vào thứ tự chạy hoặc dữ liệu còn sót.

### Phụ thuộc vào cấu hình và môi trường

Biến môi trường, feature flag, locale, múi giờ, quyền hệ điều hành, đường dẫn tệp và cấu hình mạng có thể làm thay đổi hành vi. Cần xác định cấu hình nào là đầu vào của logic và cung cấp cách thiết lập có kiểm soát.

### Phụ thuộc vào luồng xử lý và tác dụng phụ

Thread, executor, scheduler, callback và sự kiện bất đồng bộ khiến test khó biết khi nào công việc đã hoàn tất. Các thao tác gửi thông báo, ghi log bên ngoài, cập nhật nhiều hệ thống hoặc phát event cũng có thể tạo tác dụng phụ không mong muốn.

Một cách rà soát hữu ích là hỏi: “Điều gì có thể khiến cùng một đầu vào cho kết quả khác nhau giữa hai lần chạy?” Những yếu tố đó thường là ứng viên cần được kiểm soát hoặc quan sát qua seam.

## 4. Ưu tiên logic thuần và tách tác dụng phụ

Một trong những cách đơn giản nhất để tăng testability là tách phần tính toán và quyết định khỏi phần giao tiếp với thế giới bên ngoài.

**Logic thuần (pure logic)** nhận đầu vào rõ ràng, tính kết quả và không thay đổi trạng thái bên ngoài. Với cùng đầu vào, nó trả cùng kết quả. Những hàm này thường dễ kiểm thử bằng test đơn vị vì không cần mock mạng, database hoặc đồng hồ.

Ví dụ, quy tắc tính giảm giá nên nhận tổng tiền, loại khách hàng và chính sách giảm giá rồi trả về kết quả. Việc đọc dữ liệu khách hàng từ database, lấy chính sách từ API và lưu đơn hàng nên nằm ở lớp điều phối hoặc adapter khác.

```java
public record DiscountInput(
        long subtotalMinor,
        boolean premiumCustomer,
        boolean promotionEnabled) {}

public final class DiscountCalculator {
    public long calculate(DiscountInput input) {
        if (input.subtotalMinor() < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }
        if (!input.promotionEnabled()) {
            return 0;
        }
        return input.premiumCustomer()
                ? input.subtotalMinor() / 10
                : input.subtotalMinor() / 20;
    }
}
```

Test cho `DiscountCalculator` có thể kiểm tra số tiền âm, chương trình khuyến mãi tắt, khách hàng thường và khách hàng premium mà không cần khởi động Spring, database hoặc HTTP server.

Tách tác dụng phụ không có nghĩa là loại bỏ chúng. Ứng dụng vẫn cần đọc và ghi dữ liệu, gọi dịch vụ, phát event và gửi thông báo. Điều quan trọng là đặt các tác dụng phụ ở ranh giới có thể nhận diện, để phần quyết định nghiệp vụ không bị trộn lẫn với chi tiết thực thi.

## 5. Dùng interface và dependency injection tại ranh giới phù hợp

### Dependency inversion

Nguyên tắc đảo ngược phụ thuộc (Dependency Inversion Principle) khuyến khích logic cấp cao phụ thuộc vào abstraction ổn định thay vì phụ thuộc trực tiếp vào chi tiết hạ tầng. Ví dụ, `OrderService` phụ thuộc vào `PaymentGateway` thay vì phụ thuộc vào một lớp HTTP client cụ thể.

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

public record PaymentRequest(String orderId, long amountMinor) {}

public record PaymentResult(boolean approved, String reference) {}

public final class OrderService {
    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult pay(String orderId, long amountMinor) {
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        return paymentGateway.charge(
                new PaymentRequest(orderId, amountMinor));
    }
}
```

Trong production, composition root hoặc dependency injection container cung cấp implementation thật. Trong test, test cung cấp implementation thay thế.

```java
final class FakePaymentGateway implements PaymentGateway {
    private PaymentResult nextResult;
    private PaymentRequest lastRequest;

    FakePaymentGateway(PaymentResult nextResult) {
        this.nextResult = nextResult;
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        lastRequest = request;
        return nextResult;
    }

    PaymentRequest lastRequest() {
        return lastRequest;
    }
}
```

Test có thể truyền `FakePaymentGateway` với kết quả được xác định trước rồi xác nhận `OrderService` gửi đúng order ID và số tiền. Một fake có thể giữ trạng thái để test kiểm tra tương tác; một stub đơn giản có thể chỉ trả về kết quả định sẵn.

### Constructor injection

Constructor injection làm phụ thuộc hiển thị ngay khi tạo đối tượng. Nếu một service cần `Clock`, `PaymentGateway` và `OrderRepository`, các phụ thuộc đó được khai báo trong constructor. Test có thể cung cấp implementation phù hợp mà không cần sửa trạng thái toàn cục.

```java
public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
```

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-16T08:00:00Z"), ZoneOffset.UTC);
ExpiryPolicy policy = new ExpiryPolicy(fixedClock);

assertTrue(policy.isExpired(
        Instant.parse("2026-11-16T07:59:59Z")));
assertFalse(policy.isExpired(
        Instant.parse("2026-11-16T08:00:01Z")));
```

Dependency injection không nhất thiết phải dùng framework. Việc truyền dependency qua constructor hoặc tham số hàm thường đã đủ. Framework chỉ hữu ích khi ứng dụng có nhiều implementation, vòng đời hoặc cấu hình phức tạp.

### Tránh service locator và phụ thuộc ẩn

Nếu một service tự lấy dependency từ registry toàn cục hoặc gọi `ApplicationContext.getBean()` ở bất kỳ đâu, test khó biết nó cần gì và khó thay thế đúng ranh giới. Hãy ưu tiên khai báo dependency tường minh. Nếu phải dùng cơ chế tra cứu động, cần giới hạn nó ở composition root hoặc adapter có trách nhiệm rõ.

## 6. Chọn seam cho các phụ thuộc phổ biến

### Đồng hồ và lịch

Truyền `Clock` hoặc một abstraction thời gian vào thành phần cần thời gian hiện tại. Dùng fixed clock để kiểm tra thời điểm cụ thể, hoặc clock có thể tiến lên để kiểm tra timeout và lịch chạy. Khi kiểm tra quy tắc ngày tháng, cần xác định timezone rõ ràng.

### Bộ sinh ID và số ngẫu nhiên

Đặt việc sinh ID sau một abstraction như `IdGenerator` nếu giá trị đó ảnh hưởng đến hành vi cần kiểm tra. Test có thể dùng generator trả lần lượt các giá trị xác định. Nếu ID chỉ là chi tiết không liên quan đến kết quả, có thể kiểm tra định dạng hoặc tính duy nhất thay vì cố định chính xác giá trị.

### HTTP client và dịch vụ bên ngoài

Đưa giao tiếp HTTP vào adapter riêng. Logic nghiệp vụ gọi một port như `PaymentGateway`; adapter chịu trách nhiệm URL, header, serialization, authentication, timeout và mapping lỗi. Test nghiệp vụ dùng fake; test adapter dùng HTTP stub server hoặc contract test; test tích hợp xác nhận cấu hình và kết nối với sandbox hoặc dịch vụ thật trong điều kiện được phép.

### Database và repository

Đưa thao tác lưu trữ qua repository hoặc port phù hợp với miền nghiệp vụ. Test logic có thể dùng fake repository để kiểm tra quyết định. Tuy nhiên, fake không chứng minh SQL, transaction, constraint, index hoặc mapping ORM đúng. Những phần đó cần test với database thật hoặc loại database tương thích trong môi trường tích hợp.

Không nên tạo interface cho mọi bảng hoặc mọi phương thức CRUD theo máy móc. Tạo abstraction khi nó thể hiện một ranh giới có ý nghĩa, giúp cô lập phụ thuộc hoặc bảo vệ logic khỏi chi tiết lưu trữ.

### Filesystem và object storage

Đưa thao tác đọc/ghi tệp qua một adapter hoặc truyền đường dẫn/thư mục tạm vào test. Dùng temporary directory để tránh phụ thuộc vào dữ liệu trên máy phát triển. Test cần dọn tài nguyên và kiểm tra lỗi quyền, thiếu tệp, dung lượng hoặc đường dẫn không hợp lệ khi các trường hợp đó nằm trong phạm vi.

### Message broker và sự kiện

Tách logic tạo event khỏi việc publish thực tế. Test nghiệp vụ có thể xác nhận event được yêu cầu với dữ liệu đúng; test adapter xác nhận serialization, topic và metadata; test tích hợp với broker xác nhận routing, ack, retry, redelivery và DLQ. Với luồng cần bảo đảm ghi dữ liệu và phát event nhất quán, cần kiểm tra cơ chế như transactional outbox thay vì chỉ mock publisher.

### Cấu hình và feature flag

Đọc cấu hình tại ranh giới khởi tạo rồi truyền giá trị đã kiểm tra vào service. Test có thể tạo cấu hình cụ thể mà không phải thay biến môi trường toàn cục. Với feature flag, cần kiểm tra cả nhánh bật và tắt, giá trị mặc định, lỗi khi không truy cập được dịch vụ flag và cách cấu hình được đồng bộ giữa môi trường.

## 7. Ports and Adapters và ranh giới kiến trúc

Kiến trúc Ports and Adapters (còn gọi là Hexagonal Architecture) tổ chức ứng dụng quanh logic nghiệp vụ và các cổng giao tiếp (ports). Adapter kết nối cổng đó với công nghệ cụ thể như REST, database, message broker hoặc dịch vụ ngoài.

```text
             REST Controller
                   |
                   v
            +--------------+
            | Application  |
            | / Domain     |
            +--------------+
              |          |
       Repository Port   Payment Port
              |          |
              v          v
        DB Adapter   HTTP Payment Adapter
              |          |
              v          v
          Database   Payment Provider
```

Lợi ích với kiểm thử:

- Logic ứng dụng có thể được gọi trực tiếp mà không cần khởi động giao diện hoặc web server.
- Port thể hiện những khả năng bên ngoài mà logic cần, không ràng buộc vào thư viện cụ thể.
- Adapter có thể được kiểm tra riêng về mapping, giao thức và cấu hình.
- Test có thể thay adapter bằng fake tại ranh giới thích hợp.
- Việc thay công nghệ lưu trữ hoặc nhà cung cấp có thể ít ảnh hưởng đến logic nghiệp vụ hơn.

Không cần tái cấu trúc toàn bộ hệ thống thành Hexagonal Architecture để có testability. Có thể bắt đầu bằng cách tách một phụ thuộc khó kiểm soát hoặc một luồng nghiệp vụ có rủi ro cao, sau đó mở rộng khi có nhu cầu thực tế.

## 8. Chọn test double đúng mục đích

Test double là đối tượng thay thế một phụ thuộc trong kiểm thử. Các dạng thường gặp gồm:

- **Dummy:** đối tượng được truyền vào nhưng không thực sự được sử dụng.
- **Stub:** trả về dữ liệu hoặc kết quả đã định trước.
- **Fake:** implementation đơn giản nhưng có hành vi hoạt động, ví dụ repository lưu dữ liệu trong bộ nhớ.
- **Spy:** ghi nhận cách đối tượng được gọi để test có thể kiểm tra tương tác cần thiết.
- **Mock:** đối tượng được cấu hình kỳ vọng về lời gọi và có thể làm test thất bại nếu tương tác không như dự kiến.

Tên gọi và cách phân loại có thể khác giữa thư viện. Điều quan trọng là hiểu test double đang thay thế điều gì và giới hạn bằng chứng của nó.

### Khi nào nên dùng stub hoặc fake?

Dùng stub khi test cần một phản hồi xác định, chẳng hạn gateway trả về thanh toán bị từ chối. Dùng fake khi cần hành vi đơn giản có trạng thái, chẳng hạn repository trong bộ nhớ lưu đơn và truy vấn lại. Fake phù hợp cho test logic nhưng không thay thế test database thật.

### Khi nào nên dùng mock hoặc spy?

Dùng mock khi tương tác là một phần của hợp đồng quan trọng, ví dụ không được gửi thông báo khi giao dịch chưa commit. Dùng spy khi cần quan sát số lần hoặc tham số gọi mà không thay toàn bộ hành vi.

Không nên kiểm tra mọi lời gọi nội bộ. Nếu test khẳng định chính xác thứ tự các phương thức riêng tư hoặc số lần gọi một helper không thuộc hợp đồng, thay đổi cấu trúc code có thể làm test hỏng dù hành vi người dùng không đổi. Ưu tiên kiểm tra kết quả quan sát được và tương tác có ý nghĩa ở ranh giới.

### Tránh mock quá mức

Mock mọi lớp có thể làm test phản ánh cách code được viết hơn là hành vi cần bảo đảm. Các mock có thể mô phỏng một hệ thống không tồn tại hoặc che giấu lỗi mapping giữa các thành phần. Với ranh giới quan trọng, bổ sung contract test hoặc integration test sử dụng implementation thật.

Một quy tắc thực tế: thay thế phụ thuộc không thuộc mục tiêu của test; giữ thật phần đang muốn kiểm chứng; và dùng test tích hợp để xác nhận những điểm mà fake không thể chứng minh.

## 9. Làm cho trạng thái và bất đồng bộ có thể kiểm soát

### Trạng thái có thể thiết lập và quan sát

Test cần biết trạng thái ban đầu và có cách xác nhận trạng thái cuối. Hãy cung cấp API hoặc fixture phù hợp để tạo dữ liệu, truy vấn kết quả và dọn trạng thái. Tránh để test phụ thuộc vào dữ liệu tồn tại từ lần chạy trước.

Với workflow nhiều bước, có thể biểu diễn trạng thái bằng enum hoặc state machine rõ ràng, thay vì nhiều boolean khó kết hợp. Điều này giúp test từng chuyển trạng thái hợp lệ và không hợp lệ.

### Bất đồng bộ và thời gian chờ

Không nên dùng `Thread.sleep()` dài để chờ một công việc hoàn tất nếu có thể chờ theo điều kiện hoặc đồng bộ hóa rõ ràng. Test nên có cách quan sát completion, ví dụ future, latch, callback, event test hook hoặc polling có timeout hợp lý.

Với scheduler và retry, truyền clock hoặc scheduler có thể điều khiển để test không phải chờ thời gian thực. Nếu ứng dụng dùng message broker, có thể chờ đến khi consumer xử lý xong theo điều kiện xác định và luôn có timeout để tránh test treo.

### Tác dụng phụ có thể quan sát

Nếu một thao tác cần phát event, gửi thông báo hoặc ghi audit, cần xác định điều gì thuộc hợp đồng. Có thể kiểm tra event được phát với dữ liệu phù hợp, nhưng không nên buộc test nghiệp vụ phụ thuộc vào chi tiết triển khai không liên quan. Với các tác dụng phụ quan trọng, kiểm tra cả việc không phát khi điều kiện không thỏa mãn.

## 10. Thiết kế test độc lập mà vẫn kiểm chứng tích hợp thật

Một kiến trúc có seam tốt cho phép chọn mức kiểm thử phù hợp thay vì cố dùng một loại test cho mọi mục tiêu.

| Mức kiểm thử | Thành phần giữ thật | Thành phần có thể thay thế | Điều được chứng minh |
|---|---|---|---|
| Unit test logic thuần | Logic nghiệp vụ đang kiểm tra | Không cần hoặc chỉ phụ thuộc đơn giản | Quy tắc và kết quả với đầu vào xác định |
| Unit/service test | Service đang kiểm tra | Gateway, clock, repository port, ID generator | Điều phối, quyết định và xử lý lỗi của service |
| Adapter test | Adapter và mapping cần kiểm tra | HTTP server, broker hoặc database test tùy mục tiêu | Giao thức, serialization, mapping và xử lý phản hồi |
| Contract test | Consumer/provider contract | Broker hoặc provider có thể được mô phỏng theo công cụ | Hai phía tương thích với hợp đồng đã định nghĩa |
| Integration test | Các thành phần cần xác nhận cùng hoạt động | Phụ thuộc không liên quan có thể được mô phỏng | Tương tác thật giữa các phần trong ranh giới đã chọn |
| End-to-end test | Luồng người dùng và các hệ thống cần xác nhận | Chỉ mô phỏng những phụ thuộc được phê duyệt | Quy trình xuyên hệ thống trong điều kiện đại diện |

Test độc lập giúp chẩn đoán nhanh; test tích hợp giúp phát hiện lỗi ở adapter, cấu hình, schema và môi trường. Không loại bỏ một lớp chỉ vì lớp khác đang pass. Hãy phân bổ theo rủi ro và giá trị bằng chứng.

### Test contract cho implementation thay thế

Khi có nhiều implementation của cùng một port, có thể xây dựng một bộ contract test dùng chung để kiểm tra tất cả implementation phải tuân thủ cùng hành vi. Ví dụ, repository dùng PostgreSQL và fake repository có thể cùng chạy một tập kiểm tra về cách lưu, truy vấn và xử lý bản ghi trùng, trong phạm vi hợp đồng mà hai implementation cùng cam kết.

Không phải mọi khác biệt của implementation đều phải bị che giấu. Nếu database thật có transaction, constraint hoặc concurrency behavior mà fake không mô phỏng, cần có test chuyên biệt cho database để kiểm tra những đặc tính đó.

## 11. Ví dụ xuyên suốt: thiết kế OrderService có thể kiểm thử

Giả sử hệ thống thương mại điện tử cần tạo đơn hàng, giữ tồn kho, tính hạn thanh toán và phát sự kiện `OrderPlaced`. Những phụ thuộc bên ngoài gồm repository, inventory service, đồng hồ và event publisher.

### Xác định hành vi cần kiểm tra

- Không tạo đơn nếu dữ liệu đầu vào không hợp lệ.
- Chỉ giữ hàng khi số lượng còn đủ.
- Hạn thanh toán được tính từ thời điểm hiện tại theo chính sách.
- Nếu giữ hàng thất bại, đơn không được chuyển sang trạng thái đã xác nhận.
- Event chỉ được ghi nhận khi thao tác tạo đơn thành công theo quy tắc.
- Khi một phụ thuộc lỗi, service trả kết quả phù hợp và không để lại trạng thái sai.

### Định nghĩa các port

```java
public interface InventoryPort {
    boolean reserve(String productId, int quantity, String orderId);
}

public interface OrderRepository {
    void save(Order order);
}

public interface EventPublisher {
    void publish(OrderPlaced event);
}

public interface IdGenerator {
    String nextId();
}
```

Đồng hồ có thể dùng `java.time.Clock` sẵn có. Các interface trên chỉ đại diện cho những khả năng mà service cần; adapter cụ thể chịu trách nhiệm giao tiếp với database, inventory API hoặc broker.

### Service nhận phụ thuộc từ bên ngoài

```java
public final class OrderService {
    private final InventoryPort inventory;
    private final OrderRepository orders;
    private final EventPublisher events;
    private final IdGenerator ids;
    private final Clock clock;

    public OrderService(
            InventoryPort inventory,
            OrderRepository orders,
            EventPublisher events,
            IdGenerator ids,
            Clock clock) {
        this.inventory = inventory;
        this.orders = orders;
        this.events = events;
        this.ids = ids;
        this.clock = clock;
    }

    public OrderResult create(String productId, int quantity) {
        if (quantity <= 0) {
            return OrderResult.invalid("Quantity must be positive");
        }

        String orderId = ids.nextId();
        if (!inventory.reserve(productId, quantity, orderId)) {
            return OrderResult.rejected("Insufficient inventory");
        }

        Instant paymentDeadline = clock.instant().plus(Duration.ofMinutes(15));
        Order order = Order.pendingPayment(
                orderId, productId, quantity, paymentDeadline);
        orders.save(order);
        events.publish(new OrderPlaced(orderId, paymentDeadline));

        return OrderResult.created(order);
    }
}
```

Đoạn code là ví dụ rút gọn để minh họa ranh giới. Trong hệ thống thật, việc giữ hàng, lưu đơn và phát event có thể cần một transaction hoặc transactional outbox để bảo đảm tính nhất quán. Không nên dùng thứ tự gọi trong ví dụ làm quy tắc cho mọi kiến trúc.

### Kiểm tra hành vi bằng fake

Test có thể cung cấp inventory fake, repository trong bộ nhớ, publisher ghi lại event, ID generator cố định và clock cố định. Sau đó kiểm tra:

- Khi quantity bằng 0, không gọi inventory, không lưu đơn và không phát event.
- Khi inventory từ chối, đơn không được lưu và event không được phát.
- Khi inventory chấp nhận, đơn có deadline đúng theo clock và event chứa đúng order ID.
- Khi repository thất bại, service xử lý lỗi theo hợp đồng và trạng thái giữ hàng được xử lý theo cơ chế bù trừ đã thiết kế.

Các test này chạy nhanh và không cần database hoặc broker thật. Nhưng chúng chưa chứng minh transaction, SQL, serialization hay broker hoạt động đúng. Cần thêm adapter test và integration test tương ứng.

## 12. Thiết kế seam mà không làm kiến trúc phức tạp quá mức

Một rủi ro phổ biến là tạo abstraction chỉ để mock, khiến code có nhiều interface, factory và lớp chuyển tiếp nhưng không mang lại ranh giới có ý nghĩa.

### Khi nào nên tạo seam?

Nên cân nhắc seam khi:

- Phụ thuộc là tài nguyên bên ngoài hoặc có tính không xác định.
- Logic cần kiểm tra có quy tắc quan trọng nhưng hiện bị gắn chặt với I/O.
- Có nhiều implementation hoặc nhà cung cấp có thể thay đổi.
- Test thường xuyên chậm hoặc không ổn định vì phụ thuộc môi trường.
- Cần mô phỏng lỗi khó tạo trong hệ thống thật.
- Ranh giới đó có ý nghĩa kiến trúc hoặc nghiệp vụ độc lập.

### Khi nào không cần abstraction riêng?

Không nhất thiết tạo interface mới cho:

- Một lớp nhỏ, thuần và ổn định không có phụ thuộc khó kiểm soát.
- Chi tiết nội bộ không phải ranh giới và không cần thay implementation.
- Một wrapper không thêm ý nghĩa, chỉ chuyển tiếp từng lời gọi.
- Mỗi method chỉ được tạo một mock khác nhau nhưng không thể hiện hợp đồng ổn định.

Có thể truyền function hoặc tham số trực tiếp nếu đó là giải pháp đơn giản và rõ ràng. Chỉ nâng thành port/interface khi số lượng hành vi, implementation hoặc trách nhiệm thực sự cần một hợp đồng riêng.

### Tránh thiết kế test theo cấu trúc hiện tại

Nếu test phải biết quá nhiều chi tiết nội bộ, việc refactor nhỏ cũng làm hàng loạt test hỏng. Hãy kiểm tra hành vi ở public API hoặc ranh giới có ý nghĩa, giữ test gần với cách người dùng hoặc thành phần khác tương tác. Một test tốt nên bảo vệ hợp đồng hành vi, không đóng băng mọi bước triển khai.

## 13. Các dấu hiệu cho thấy thành phần khó kiểm thử

Những dấu hiệu sau thường cho thấy cần xem lại thiết kế:

- Khởi tạo một service phải mở kết nối mạng hoặc đọc nhiều biến môi trường.
- Test cần chờ thời gian thực hoặc phụ thuộc vào múi giờ máy chạy.
- Test thất bại không ổn định do thứ tự chạy hoặc dữ liệu dùng chung.
- Không thể kiểm tra kết quả nếu không đọc trực tiếp database production-like.
- Lỗi từ nhà cung cấp bên ngoài không thể mô phỏng an toàn.
- Một thay đổi nhỏ buộc phải khởi động toàn bộ hệ thống để chạy test.
- Không thể xác định tác dụng phụ đã xảy ra hay chưa sau timeout.
- Test phải mock quá nhiều lớp và vẫn không chứng minh được hành vi quan trọng.
- Không thể quan sát trạng thái cuối của một workflow bất đồng bộ.
- Các test phụ thuộc vào implementation cụ thể hơn là hợp đồng hành vi.

Không phải mọi dấu hiệu đều yêu cầu tái cấu trúc lớn. Có thể bắt đầu bằng việc truyền `Clock`, tách HTTP adapter, tạo fixture dữ liệu, bổ sung ID tương quan hoặc cung cấp cách truy vấn trạng thái rõ ràng.

## 14. Quy trình cải thiện testability

Một cách tiếp cận từng bước giúp tránh thiết kế quá mức:

### Bước 1: Chọn hành vi quan trọng

Chọn một quy tắc nghiệp vụ hoặc luồng có rủi ro cao đang khó kiểm thử. Mô tả đầu vào, điều kiện, kết quả và tác dụng phụ cần xác minh.

### Bước 2: Lập bản đồ phụ thuộc

Ghi các thành phần mà logic gọi đến, gồm database, HTTP, clock, random, filesystem, queue, cấu hình và trạng thái toàn cục. Xác định phụ thuộc nào làm test chậm, không ổn định hoặc không thể tái lập.

### Bước 3: Phân biệt logic với tác dụng phụ

Chuyển phép tính và quyết định thuần ra khỏi phần đọc/ghi hoặc giao tiếp. Giữ trách nhiệm mỗi thành phần rõ ràng.

### Bước 4: Đặt seam tại ranh giới có ý nghĩa

Dùng constructor injection, function parameter, port/interface hoặc adapter tùy mức độ phức tạp. Khai báo dependency tường minh và tạo composition root để chọn implementation.

### Bước 5: Viết test với implementation thay thế

Dùng stub, fake, spy hoặc mock đúng mục tiêu. Kiểm tra kết quả và tác dụng phụ có ý nghĩa; tránh kiểm tra chi tiết nội bộ không thuộc hợp đồng.

### Bước 6: Bổ sung test cho implementation thật

Viết adapter test, contract test hoặc integration test để xác nhận mapping, giao thức, transaction, schema và cấu hình. Không suy rộng kết quả fake sang phụ thuộc thật.

### Bước 7: Đo lại chi phí và độ tin cậy

So sánh thời gian chạy, độ ổn định, khả năng chẩn đoán và chi phí bảo trì test trước/sau. Kiểm tra xem abstraction mới có thực sự giảm phụ thuộc hay chỉ chuyển độ phức tạp sang nơi khác.

### Bước 8: Mở rộng theo nhu cầu

Áp dụng cách làm cho các ranh giới khác khi có bằng chứng cần thiết. Duy trì hợp đồng và test khi implementation hoặc nhà cung cấp thay đổi.

## 15. Bằng chứng và chỉ số đánh giá testability

Không có một chỉ số duy nhất đo được toàn bộ khả năng kiểm thử. Nên kết hợp quan sát định tính và số liệu trong bối cảnh cụ thể.

Một số tín hiệu có thể theo dõi:

- Thời gian để chạy test cho một thành phần mà không khởi động toàn bộ hệ thống.
- Tỷ lệ test flaky và số lần chạy lại do môi trường hoặc timing.
- Thời gian chuẩn bị dữ liệu và dọn dẹp trạng thái.
- Thời gian từ khi phát hiện test thất bại đến khi xác định được nguyên nhân.
- Số phụ thuộc bên ngoài cần được mock trong một test quan trọng và lý do.
- Khả năng tái lập lỗi bằng cùng build, dữ liệu và điều kiện.
- Mức độ test kiểm tra hành vi qua hợp đồng thay vì chi tiết nội bộ.
- Tỷ lệ rủi ro quan trọng có test độc lập và test tích hợp bổ sung.

Đừng tối ưu bằng cách giảm số lượng mock hoặc tăng số interface một cách máy móc. Hãy xem test có đáng tin, dễ hiểu, có thể bảo trì và tạo ra bằng chứng đúng với rủi ro hay không.

## 16. Những sai lầm thường gặp

**Tạo interface cho mọi lớp.** Việc này làm tăng số lượng abstraction và chi phí điều hướng mà không nhất thiết tăng testability. Tập trung vào phụ thuộc có biến động, I/O hoặc cần điều khiển trong test.

**Mock mọi thứ.** Test có thể pass với các mock không phản ánh hành vi thật. Giữ logic đang kiểm tra thật và bổ sung test adapter/contract/integration cho ranh giới quan trọng.

**Để service tự tạo dependency.** Việc gọi constructor của HTTP client, đọc biến môi trường hoặc truy cập singleton bên trong service làm phụ thuộc bị ẩn. Đưa việc tạo và cấu hình dependency ra composition root.

**Dùng sleep để đồng bộ test.** Chờ một khoảng thời gian cố định làm test chậm và không ổn định. Dùng clock/scheduler có thể điều khiển, completion signal hoặc chờ theo điều kiện với timeout.

**Dùng fake để kết luận database thật đúng.** Fake không kiểm tra SQL, transaction, constraint, locking hoặc behavior đặc thù của database. Cần test với implementation thật ở phạm vi thích hợp.

**Kiểm tra quá nhiều lời gọi nội bộ.** Test gắn chặt vào thứ tự method và helper dễ hỏng khi refactor mà không có thay đổi hành vi. Ưu tiên kết quả quan sát được và tương tác thuộc hợp đồng.

**Để trạng thái toàn cục điều khiển test.** Static mutable state, singleton, system clock và biến môi trường dùng chung khiến test ảnh hưởng lẫn nhau. Cô lập trạng thái hoặc truyền dependency tường minh.

**Tạo seam nhưng không kiểm tra adapter.** Logic có thể pass với fake trong khi adapter thật serialize sai, gửi sai topic hoặc mapping sai dữ liệu. Bổ sung test cho adapter và tích hợp.

**Thiết kế seam chỉ để vượt qua một test.** Một abstraction chỉ giải quyết test đơn lẻ có thể không phù hợp với kiến trúc. Hãy xem xét trách nhiệm, khả năng thay đổi và hợp đồng thực tế trước khi chọn ranh giới.

## 17. Checklist thiết kế điểm giao tiếp có thể kiểm thử

Khi thiết kế thành phần:

- [ ] Trách nhiệm và hành vi của thành phần được mô tả rõ.
- [ ] Logic nghiệp vụ được tách khỏi I/O và tác dụng phụ khi phù hợp.
- [ ] Các phụ thuộc quan trọng được khai báo tường minh.
- [ ] Thời gian, random, ID, cấu hình và trạng thái bên ngoài có thể kiểm soát khi cần.
- [ ] Ranh giới interface/port phản ánh phụ thuộc có ý nghĩa, không tạo abstraction thừa.
- [ ] Có thể tạo trạng thái đầu vào và quan sát kết quả cuối.

Khi viết test:

- [ ] Phần đang kiểm tra được giữ thật.
- [ ] Test double được chọn theo mục tiêu và giới hạn của nó được hiểu rõ.
- [ ] Test kiểm tra hành vi và tác dụng phụ thuộc hợp đồng.
- [ ] Kết quả có thể tái lập và test không phụ thuộc thứ tự chạy.
- [ ] Test có timeout hợp lý và không dùng sleep tùy tiện.
- [ ] Dữ liệu và tài nguyên được dọn dẹp sau test.

Khi xác nhận tích hợp:

- [ ] Adapter được kiểm tra về serialization, mapping, giao thức và lỗi.
- [ ] Contract test xác nhận consumer/provider tương thích khi cần.
- [ ] Integration test dùng database, broker hoặc dịch vụ thật ở ranh giới có rủi ro.
- [ ] Các tình huống timeout, retry, lỗi và tác dụng phụ được kiểm tra theo phạm vi.
- [ ] Giới hạn của fake, mock, sandbox và môi trường được ghi nhận.

## 18. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Một service gọi `LocalDate.now()` để quyết định đơn có hết hạn không. Test chạy vào ngày khác cho kết quả khác nhau. Cách cải thiện là truyền `Clock` hoặc giá trị thời gian vào service, rồi kiểm tra các mốc trước, đúng và sau hạn.

**Tình huống 2:** Một service tự khởi tạo HTTP client và gọi nhà cung cấp thanh toán. Test phải kết nối mạng thật. Có thể tách `PaymentGateway` thành port, đưa HTTP client vào adapter và truyền implementation qua constructor. Test service dùng fake; adapter được kiểm tra riêng bằng stub server hoặc sandbox.

**Tình huống 3:** Test dùng fake repository pass, nhưng production gặp lỗi SQL do constraint. Fake chỉ chứng minh logic gọi repository theo cách mong đợi; nó không chứng minh database thật hoạt động đúng. Cần thêm integration test với database tương thích để kiểm tra schema, transaction và constraint.

**Tình huống 4:** Một test mock mọi helper và kiểm tra chính xác 12 lời gọi nội bộ. Refactor đổi thứ tự gọi nhưng kết quả nghiệp vụ không đổi, test lại thất bại. Nên xem lại test để tập trung vào hợp đồng và kết quả quan sát được, chỉ giữ kỳ vọng tương tác khi nó mang ý nghĩa nghiệp vụ hoặc kỹ thuật thực sự.

**Tình huống 5:** Consumer xử lý message bất đồng bộ; test dùng `Thread.sleep(5000)` rồi đọc database. Test lúc pass lúc fail. Có thể cung cấp completion signal, chờ theo điều kiện có timeout, dùng scheduler/clock điều khiển nếu cần và xác nhận trạng thái cuối bằng một truy vấn có ý nghĩa.

Khi thiết kế một thành phần, hãy tự hỏi: **logic nào cần được kiểm tra độc lập, phụ thuộc nào làm kết quả khó kiểm soát, seam nào thể hiện ranh giới có ý nghĩa và test nào vẫn cần chạy với implementation thật?** Trả lời được các câu hỏi này giúp tạo thiết kế dễ kiểm tra mà không làm kiến trúc phức tạp quá mức.

## Kết luận

Thiết kế điểm giao tiếp giúp kiểm tra hành vi độc lập bằng cách tách logic cần xác minh khỏi các phụ thuộc và tác dụng phụ khó kiểm soát. Ưu tiên logic thuần, khai báo dependency tường minh, dùng constructor injection và port/interface ở ranh giới có ý nghĩa; kiểm soát thời gian, dữ liệu, ID và trạng thái; chọn test double đúng mục đích; đồng thời bổ sung adapter, contract và integration test cho implementation thật. Khi test tập trung vào hành vi quan sát được và mỗi loại bằng chứng có giới hạn rõ, hệ thống trở nên dễ kiểm thử, dễ chẩn đoán và an toàn hơn khi thay đổi.
