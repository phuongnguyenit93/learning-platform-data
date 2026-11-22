# Tách phụ thuộc để kiểm soát thời gian, ngẫu nhiên và dịch vụ ngoài

**Chương:** Khả năng kiểm thử  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Một thành phần phần mềm khó kiểm thử khi kết quả của nó phụ thuộc trực tiếp vào đồng hồ hệ thống, giá trị ngẫu nhiên, mạng hoặc dịch vụ bên ngoài. Cùng một đầu vào có thể cho kết quả khác nhau ở các lần chạy vì thời điểm thực khác nhau, dữ liệu ngẫu nhiên thay đổi, dịch vụ phản hồi chậm hoặc môi trường không sẵn sàng. Khi các phụ thuộc này bị gắn chặt vào logic nghiệp vụ, người kiểm thử khó tái hiện lỗi và khó xác định nguyên nhân.

Tách phụ thuộc (dependency separation) là thiết kế để logic cần kiểm tra nhận các khả năng bên ngoài thông qua giao diện hoặc tham số có thể thay thế. Trong môi trường thật, chương trình sử dụng đồng hồ, bộ sinh ngẫu nhiên và adapter kết nối dịch vụ thật. Trong kiểm thử, có thể cung cấp đồng hồ cố định, bộ sinh có seed xác định hoặc fake/stub có hành vi được kiểm soát. Nhờ vậy, test tập trung vào quy tắc cần xác minh và có thể tái lập điều kiện.

Bài học này trình bày cách nhận diện phụ thuộc gây khó kiểm thử, tách thời gian, ngẫu nhiên và dịch vụ ngoài khỏi logic nghiệp vụ, lựa chọn cơ chế thay thế phù hợp và kiểm tra các ranh giới tích hợp. Trọng tâm là làm cho hành vi có thể điều khiển và quan sát được, đồng thời vẫn giữ kiểm thử với hệ thống thật ở những nơi cần bằng chứng tích hợp.

Sau bài học, người học có thể:

- Nhận diện phụ thuộc vào đồng hồ, nguồn ngẫu nhiên, mạng và dịch vụ ngoài.
- Giải thích vì sao phụ thuộc trực tiếp làm test khó tái lập và khó chẩn đoán.
- Thiết kế constructor injection, interface hoặc adapter để tách phụ thuộc.
- Kiểm thử logic thời gian bằng `Clock` cố định và thời điểm được truyền vào.
- Kiểm thử hành vi ngẫu nhiên bằng seed hoặc nguồn giá trị có thể điều khiển.
- Dùng fake, stub và mock đúng mục tiêu khi kiểm thử dịch vụ ngoài.
- Kết hợp unit test, contract test và integration test để xác minh cả logic lẫn ranh giới thực.
- Tránh các cách tách phụ thuộc làm giảm tính thực tế, bảo mật hoặc khả năng bảo trì.

## 1. Phụ thuộc bên ngoài ảnh hưởng đến khả năng kiểm thử

Một phụ thuộc là thành phần hoặc nguồn dữ liệu mà logic đang xét cần sử dụng để hoàn thành công việc. Phụ thuộc có thể nằm trong cùng tiến trình, cùng hệ thống hoặc ngoài quyền kiểm soát của ứng dụng.

Các phụ thuộc thường gây khó khăn cho kiểm thử gồm:

- **Thời gian hệ thống:** ngày hiện tại, thời điểm hiện tại, múi giờ, thời gian hết hạn hoặc lịch chạy.
- **Nguồn ngẫu nhiên:** số ngẫu nhiên, UUID, token, lựa chọn ngẫu nhiên hoặc dữ liệu sinh tự động.
- **Dịch vụ ngoài:** cổng thanh toán, dịch vụ định danh, email, SMS, vận chuyển, tỷ giá hoặc API đối tác.
- **Tài nguyên môi trường:** hệ thống tệp, biến môi trường, cấu hình mạng, hàng đợi, cơ sở dữ liệu hoặc dịch vụ cloud.
- **Tác nhân không đồng bộ:** bộ lập lịch, webhook, message broker và tiến trình nền.

Không phải mọi phụ thuộc đều cần bị thay thế trong mọi test. Câu hỏi cần trả lời là: test đang xác minh logic nào, phụ thuộc nào tạo ra biến thiên không liên quan đến mục tiêu, và ranh giới nào cần được kiểm tra thật?

### 1.1. Dấu hiệu thiết kế khó kiểm thử

Một số dấu hiệu thường gặp:

- Hàm nghiệp vụ tự gọi `LocalDate.now()` hoặc `Instant.now()` ở nhiều vị trí.
- Logic tạo mã ngẫu nhiên trực tiếp bằng `new Random()` hoặc UUID bên trong phương thức.
- Quy tắc nghiệp vụ tự mở kết nối HTTP và phân tích response.
- Test phải chờ một thời điểm thực hoặc phụ thuộc dịch vụ bên ngoài đang hoạt động.
- Muốn kiểm tra một nhánh lỗi phải làm dịch vụ thật ngừng hoạt động.
- Test chỉ chạy được trên máy của một người vì phụ thuộc cấu hình hoặc trạng thái cục bộ.
- Không thể tái tạo chính xác dữ liệu đầu vào đã gây lỗi.

Các dấu hiệu này không tự động chứng minh mã thiết kế sai. Chúng cho biết cần xem xét ranh giới phụ thuộc và mục tiêu của test.

### 1.2. Tách phụ thuộc không đồng nghĩa giả lập mọi thứ

Một unit test cho quy tắc tính phí có thể thay thế dịch vụ tỷ giá bằng một giá trị cố định. Nhưng một contract test vẫn cần xác minh adapter gửi đúng request và đọc đúng response theo hợp đồng. Một integration test có thể gọi sandbox thật để kiểm tra xác thực, timeout hoặc định dạng dữ liệu.

Nếu mọi phụ thuộc đều bị mock, test có thể chạy nhanh nhưng không chứng minh các thành phần thực sự giao tiếp được. Nếu mọi test đều gọi dịch vụ thật, kết quả có thể phụ thuộc mạng và trạng thái nhà cung cấp, khiến lỗi khó tái hiện. Cần chọn mức thay thế theo câu hỏi kiểm thử.

## 2. Nguyên tắc thiết kế để kiểm soát phụ thuộc

### 2.1. Đưa phụ thuộc vào từ bên ngoài

Dependency injection là cách cung cấp phụ thuộc cho đối tượng thay vì để đối tượng tự tạo hoặc tự tìm phụ thuộc bên trong. Có thể truyền qua constructor, phương thức hoặc cơ chế cấu hình. Constructor injection thường dễ nhận biết vì các yêu cầu cần thiết được thể hiện ngay khi tạo đối tượng.

Ví dụ, lớp xử lý đơn hàng nhận `Clock` và `PaymentGateway` từ bên ngoài. Khi chạy thật, cấu hình ứng dụng cung cấp implementation thật; khi kiểm thử, test cung cấp implementation có thể điều khiển.

### 2.2. Phụ thuộc vào hợp đồng nhỏ và có ý nghĩa

Interface nên mô tả khả năng mà logic cần, chẳng hạn `PaymentGateway.charge()` hoặc `ExchangeRateProvider.rateFor()`. Tránh tạo một interface khổng lồ bao trùm toàn bộ SDK của nhà cung cấp nếu logic chỉ cần một thao tác nhỏ.

Hợp đồng nhỏ giúp:

- Thay implementation mà không sửa quy tắc nghiệp vụ.
- Tạo fake đơn giản và dễ hiểu.
- Xác định rõ dữ liệu vào, kết quả và lỗi có thể xảy ra.
- Kiểm tra tương thích ở ranh giới.
- Giảm việc logic nghiệp vụ phụ thuộc vào chi tiết thư viện hoặc giao thức.

### 2.3. Tách logic quyết định khỏi thao tác I/O

Logic quyết định nên nhận dữ liệu và trả kết quả càng thuần càng tốt. Các thao tác I/O như đọc đồng hồ, gọi HTTP, ghi cơ sở dữ liệu hoặc phát thông điệp nên nằm ở ranh giới phù hợp.

Ví dụ, quy tắc xác định mã giảm giá còn hiệu lực chỉ cần nhận ngày đánh giá và khoảng thời gian hiệu lực. Thành phần điều phối có thể lấy ngày từ đồng hồ rồi truyền vào quy tắc. Nhờ đó, unit test không cần thay đổi ngày hệ thống.

### 2.4. Giữ một nguồn sự thật cho mỗi phụ thuộc

Nếu một luồng đọc đồng hồ ở nhiều lớp khác nhau, việc cố định thời gian trong test có thể không đủ. Nếu mỗi lớp tự tạo `Random`, seed ở một nơi không kiểm soát được toàn bộ hành vi. Hãy xác định nơi tạo phụ thuộc và truyền nó đến các thành phần cần dùng.

### 2.5. Làm rõ vòng đời và phạm vi chia sẻ

Phụ thuộc có trạng thái cần được quản lý theo vòng đời. Một fake lưu lịch sử lời gọi có thể dùng cho một test, nhưng không nên chia sẻ giữa các test chạy song song nếu trạng thái của nó bị thay đổi. Đồng hồ cố định thường an toàn để chia sẻ nếu immutable; một generator ngẫu nhiên có trạng thái thì cần xác định rõ test nào sở hữu nó.

## 3. Tách phụ thuộc vào thời gian

Thời gian thực là một nguồn biến thiên phổ biến. Một test có thể đạt hôm nay nhưng thất bại ngày mai vì dữ liệu hết hạn, qua ngày mới hoặc rơi vào một ranh giới lịch khác.

### 3.1. Truyền thời điểm vào logic nghiệp vụ

Ví dụ khó kiểm thử:

```java
public boolean isPromotionActive(Promotion promotion) {
    LocalDate today = LocalDate.now();
    return !today.isBefore(promotion.startDate())
        && !today.isAfter(promotion.endDate());
}
```

Phương thức tự lấy ngày hiện tại. Test muốn kiểm tra ngày bắt đầu, ngày kết thúc hoặc ngày nằm ngoài khoảng phải phụ thuộc vào ngày chạy thực tế hoặc can thiệp đồng hồ toàn cục.

Một cách đơn giản là truyền ngày đánh giá:

```java
public boolean isPromotionActive(
        Promotion promotion,
        LocalDate evaluationDate) {
    return !evaluationDate.isBefore(promotion.startDate())
        && !evaluationDate.isAfter(promotion.endDate());
}
```

Giờ đây, unit test có thể cung cấp ngày cụ thể và kiểm tra ranh giới:

```java
@Test
void promotionIsActiveOnBothBoundaryDates() {
    Promotion promotion = new Promotion(
        LocalDate.of(2026, 5, 1),
        LocalDate.of(2026, 5, 31)
    );

    assertTrue(isPromotionActive(promotion, LocalDate.of(2026, 5, 1)));
    assertTrue(isPromotionActive(promotion, LocalDate.of(2026, 5, 31)));
    assertFalse(isPromotionActive(promotion, LocalDate.of(2026, 4, 30)));
    assertFalse(isPromotionActive(promotion, LocalDate.of(2026, 6, 1)));
}
```

Ví dụ giả định hai ngày biên đều được tính là hợp lệ. Nếu nghiệp vụ dùng khoảng nửa mở hoặc quy tắc khác, test phải phản ánh chính sách đã thống nhất.

### 3.2. Dùng `java.time.Clock`

Trong ứng dụng Java, `Clock` là abstraction có sẵn để cung cấp thời gian hiện tại. Có thể truyền một `Clock` vào constructor và gọi `LocalDate.now(clock)` hoặc `Instant.now(clock)`.

```java
import java.time.Clock;
import java.time.LocalDate;

public final class PromotionService {
    private final Clock clock;

    public PromotionService(Clock clock) {
        this.clock = clock;
    }

    public boolean isActive(Promotion promotion) {
        LocalDate today = LocalDate.now(clock);
        return !today.isBefore(promotion.startDate())
            && !today.isAfter(promotion.endDate());
    }
}
```

Ở cấu hình chạy thật, có thể dùng `Clock.systemUTC()` hoặc clock theo múi giờ nghiệp vụ. Trong test, dùng `Clock.fixed()`:

```java
@Test
void usesTheConfiguredEvaluationDate() {
    Clock fixedClock = Clock.fixed(
        Instant.parse("2026-05-15T10:00:00Z"),
        ZoneOffset.UTC
    );
    PromotionService service = new PromotionService(fixedClock);

    assertTrue(service.isActive(promotionForMay2026));
}
```

Clock cố định làm cho mọi lần gọi trong test trả về cùng một thời điểm. Có thể tạo clock dịch chuyển bằng `Clock.offset()` để kiểm tra thời gian tăng theo một khoảng xác định mà không cần chờ thời gian thật.

### 3.3. Phân biệt ngày nghiệp vụ, thời điểm và múi giờ

Không nên dùng một kiểu thời gian cho mọi mục đích:

- `LocalDate` phù hợp với ngày lịch không gắn trực tiếp vào một thời điểm toàn cầu, ví dụ ngày sinh hoặc ngày hiệu lực theo lịch địa phương.
- `Instant` biểu diễn một thời điểm trên trục thời gian UTC.
- `ZonedDateTime` kết hợp thời điểm với múi giờ và quy tắc lịch.
- `LocalDateTime` không chứa múi giờ hoặc offset; cần thận trọng khi chuyển đổi sang thời điểm toàn cầu.

Nếu quy tắc phụ thuộc ngày địa phương, cần xác định múi giờ nghiệp vụ. Không nên lấy `LocalDate.now()` theo múi giờ mặc định của máy chủ nếu khách hàng hoặc hợp đồng dùng múi giờ khác.

Ví dụ, một giao dịch hết hạn vào nửa đêm tại Việt Nam phải được diễn giải theo `Asia/Ho_Chi_Minh`, không phải tùy thuộc cấu hình của runner đặt ở vùng khác. Test nên cố định cả instant và zone để kiểm tra đúng ranh giới.

### 3.4. Dùng đồng hồ giả lập cho tiến trình và lịch chạy

Với logic cần kiểm tra “sau 15 phút”, “đến hạn lúc 00:00” hoặc “đã quá thời gian chờ”, không nên bắt test ngủ thật trong nhiều phút. Hãy truyền clock hoặc abstraction thời gian vào logic, sau đó điều khiển thời điểm trong test.

Một ví dụ đơn giản:

```java
Clock start = Clock.fixed(
    Instant.parse("2026-05-15T10:00:00Z"), ZoneOffset.UTC);
Clock later = Clock.offset(start, Duration.ofMinutes(16));

assertFalse(isWithinGracePeriod(start, Duration.ofMinutes(15)));
assertTrue(isWithinGracePeriod(later, Duration.ofMinutes(15)));
```

Trong thực tế, hàm cần nhận clock và mốc bắt đầu rõ ràng. Đoạn mã trên minh họa cách tạo hai mốc kiểm thử; không thay thế thiết kế cụ thể của ứng dụng.

### 3.5. Dùng đồng hồ đơn điệu để đo thời lượng

Đồng hồ lịch có thể được điều chỉnh bởi đồng bộ thời gian, thay đổi múi giờ hoặc thao tác quản trị. Khi đo thời lượng thực thi, timeout hoặc khoảng elapsed time, nên dùng nguồn thời gian đơn điệu như `System.nanoTime()` thay vì trừ hai timestamp lịch.

Có thể tách nguồn đo thời lượng thành một abstraction riêng nếu logic timeout cần kiểm thử. Không nên dùng `Clock.fixed()` để mô phỏng thời gian trôi qua cho mọi trường hợp, vì clock lịch và đồng hồ đơn điệu phục vụ hai mục tiêu khác nhau.

## 4. Tách nguồn ngẫu nhiên

Ngẫu nhiên tạo ra biến thiên có chủ đích. Nếu test không kiểm soát nguồn ngẫu nhiên, lỗi có thể khó tái hiện vì mỗi lần chạy sinh dữ liệu khác nhau.

### 4.1. Truyền generator hoặc nguồn giá trị vào

Ví dụ, logic chọn một phần tử ngẫu nhiên có thể nhận `RandomGenerator`:

```java
import java.util.random.RandomGenerator;

public final class PrizePicker {
    private final RandomGenerator random;

    public PrizePicker(RandomGenerator random) {
        this.random = random;
    }

    public int chooseIndex(int itemCount) {
        if (itemCount <= 0) {
            throw new IllegalArgumentException("itemCount must be positive");
        }
        return random.nextInt(itemCount);
    }
}
```

Trong test, có thể truyền generator có seed cố định:

```java
@Test
void selectedIndexIsRepeatableForTheSameSeed() {
    var first = new PrizePicker(new Random(42));
    var second = new PrizePicker(new Random(42));

    assertEquals(first.chooseIndex(10), second.chooseIndex(10));
}
```

Hai generator độc lập cùng seed và cùng chuỗi lời gọi sẽ tạo cùng chuỗi kết quả theo thuật toán của generator. Điều này giúp tái lập test. Nếu test cần xác minh chính xác một giá trị, có thể dùng fake generator trả về giá trị được chỉ định để tránh phụ thuộc vào chi tiết thuật toán.

### 4.2. Dùng fake nguồn ngẫu nhiên khi cần điều khiển chính xác

Đôi khi mục tiêu là kiểm tra các nhánh: chọn phần tử đầu, phần tử cuối hoặc giá trị nằm ở biên. Khi đó, fake có thể trả về kết quả định trước:

```java
final class FixedRandom implements RandomGenerator {
    private final int nextIntValue;

    FixedRandom(int nextIntValue) {
        this.nextIntValue = nextIntValue;
    }

    @Override
    public int nextInt(int bound) {
        if (nextIntValue < 0 || nextIntValue >= bound) {
            throw new IllegalArgumentException("value outside bound");
        }
        return nextIntValue;
    }

    // Các phương thức khác cần được triển khai hoặc dùng interface hẹp hơn
    // theo đúng nhu cầu của ứng dụng.
}
```

Trong mã thực tế, có thể định nghĩa interface nhỏ như `IndexSource` nếu chỉ cần một thao tác, để fake không phải triển khai toàn bộ `RandomGenerator`. Điều quan trọng là test có thể ép logic đi qua các trường hợp cần xác minh.

### 4.3. Seed cố định và test nhiều seed

Seed cố định phù hợp để tái lập một ca kiểm thử. Tuy nhiên, nếu chỉ dùng một seed, test có thể bỏ sót lỗi phụ thuộc vào một chuỗi giá trị khác.

Một chiến lược tốt là:

- Dùng seed cố định cho test hồi quy cần tái lập.
- Chạy một tập seed được chọn trước để mở rộng dữ liệu trong một nhóm test riêng.
- Khi phát hiện lỗi với seed bất kỳ, ghi seed vào báo cáo để tái hiện.
- Giữ một test hồi quy với seed đã gây lỗi sau khi sửa.
- Tránh dùng seed ngẫu nhiên không được ghi nhận trong pipeline quan trọng.

Nếu kiểm thử thuộc tính (property-based testing) sinh hàng nghìn đầu vào, framework thường hỗ trợ ghi seed và thu nhỏ trường hợp lỗi. Cần lưu thông tin này cùng kết quả chạy.

### 4.4. Không làm yếu bảo mật khi kiểm soát ngẫu nhiên

Nguồn ngẫu nhiên dùng cho bảo mật, chẳng hạn sinh token xác thực, nonce hoặc khóa, cần có đặc tính mật mã phù hợp. Không thay `SecureRandom` bằng generator có seed cố định trong cấu hình sản xuất để làm test dễ lặp lại.

Có thể tách một interface cung cấp khả năng tạo token để unit test kiểm tra luồng xử lý bằng fake. Sau đó, kiểm thử riêng adapter dùng `SecureRandom` và các yêu cầu bảo mật liên quan. Test không được làm lộ token thật hoặc khóa trong log.

### 4.5. Phân biệt ngẫu nhiên nghiệp vụ và định danh duy nhất

UUID hoặc mã định danh sinh tự động cũng là một dạng phụ thuộc. Nếu logic chỉ cần một ID, có thể truyền `Supplier<UUID>` hoặc interface `IdGenerator`. Test dùng ID cố định để assertion dễ đọc và có thể tái lập.

Tuy nhiên, nếu mục tiêu là kiểm tra tính duy nhất hoặc va chạm, cần kiểm thử riêng với generator và kho lưu trữ phù hợp. Fake luôn trả về cùng một ID không chứng minh cơ chế sinh ID thật không va chạm.

## 5. Tách dịch vụ bên ngoài khỏi logic nghiệp vụ

Gọi HTTP trực tiếp trong logic nghiệp vụ làm test phụ thuộc mạng, endpoint, xác thực và định dạng response. Một thay đổi nhỏ ở nhà cung cấp có thể khiến unit test thất bại dù quy tắc nghiệp vụ không thay đổi.

### 5.1. Tạo cổng giao tiếp (port) có ý nghĩa nghiệp vụ

Ví dụ, thay vì để `OrderService` sử dụng SDK của cổng thanh toán trực tiếp, hãy định nghĩa một interface nhỏ:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
```

Logic nghiệp vụ phụ thuộc vào hợp đồng `PaymentGateway`, còn implementation cụ thể chịu trách nhiệm giao tiếp với nhà cung cấp:

```java
public final class OrderService {
    private final PaymentGateway paymentGateway;
    private final Clock clock;

    public OrderService(PaymentGateway paymentGateway, Clock clock) {
        this.paymentGateway = paymentGateway;
        this.clock = clock;
    }

    public OrderResult placeOrder(Order order) {
        PaymentRequest request = PaymentRequest.from(order);
        PaymentResult payment = paymentGateway.charge(request);

        if (!payment.approved()) {
            return OrderResult.paymentRejected(payment.reason());
        }

        return OrderResult.confirmed(order.id(), Instant.now(clock));
    }
}
```

Ví dụ tập trung minh họa việc tách phụ thuộc. Trong hệ thống thật, cần xác định transaction, idempotency, trạng thái trung gian và cách xử lý timeout theo quy tắc nghiệp vụ. Không nên giả định lời gọi thanh toán đồng bộ luôn trả về kết quả cuối.

### 5.2. Adapter kết nối nhà cung cấp

Adapter chuyển đổi hợp đồng nghiệp vụ nội bộ sang giao thức cụ thể như HTTP/JSON, SOAP hoặc SDK. Nó chịu trách nhiệm:

- Tạo request và ánh xạ trường dữ liệu.
- Thiết lập endpoint, timeout, xác thực và header.
- Gửi request và đọc response.
- Chuyển mã lỗi nhà cung cấp thành lỗi nội bộ có ý nghĩa.
- Áp dụng retry hoặc circuit breaker nếu chính sách cho phép.
- Ghi log và trace theo quy tắc bảo mật.

Logic nghiệp vụ không cần biết chi tiết HTTP status, tên header hoặc cấu trúc SDK. Điều này giúp unit test tập trung vào quyết định nghiệp vụ, trong khi adapter được kiểm tra riêng.

### 5.3. Chọn test double phù hợp

Test double là đối tượng thay thế một phụ thuộc thật trong kiểm thử. Các dạng phổ biến:

| Loại | Vai trò | Khi phù hợp |
|---|---|---|
| Dummy | Được truyền vào nhưng không dùng trong test | Thỏa mãn tham số bắt buộc không liên quan đến hành vi đang xét |
| Stub | Trả về dữ liệu hoặc lỗi đã định trước | Điều khiển nhánh thành công, từ chối hoặc lỗi |
| Fake | Implementation đơn giản có hành vi hoạt động, ví dụ repository trong bộ nhớ | Kiểm thử logic cần trạng thái nhưng không cần hạ tầng thật |
| Mock | Ghi nhận hoặc xác minh tương tác mong đợi | Khi tương tác là một phần của hợp đồng cần xác minh |
| Spy | Bao bọc hoặc theo dõi một đối tượng thật | Khi cần quan sát lời gọi mà vẫn dùng một phần hành vi thật |

Không nên dùng mock cho mọi phụ thuộc. Nếu test chỉ xác minh một chuỗi lời gọi nội bộ, nó có thể trở nên mong manh khi refactor dù hành vi nghiệp vụ vẫn đúng. Ưu tiên kiểm tra kết quả có ý nghĩa; dùng xác minh tương tác khi việc gọi hay không gọi một dịch vụ thực sự là yêu cầu.

### 5.4. Ví dụ stub dịch vụ thanh toán

```java
final class StubPaymentGateway implements PaymentGateway {
    private final PaymentResult result;

    StubPaymentGateway(PaymentResult result) {
        this.result = result;
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return result;
    }
}

@Test
void rejectedPaymentDoesNotConfirmTheOrder() {
    PaymentGateway gateway = new StubPaymentGateway(
        PaymentResult.rejected("INSUFFICIENT_FUNDS")
    );
    OrderService service = new OrderService(gateway, fixedClock);

    OrderResult result = service.placeOrder(validOrder);

    assertFalse(result.confirmed());
    assertEquals("INSUFFICIENT_FUNDS", result.reason());
}
```

Stub giúp kiểm tra nhánh từ chối mà không cần gọi cổng thanh toán thật. Một test khác có thể dùng kết quả được duyệt để xác minh nhánh thành công.

### 5.5. Kiểm tra lỗi, timeout và phản hồi không hợp lệ

Dịch vụ ngoài không chỉ trả về thành công hoặc từ chối. Nó có thể timeout, mất kết nối, trả dữ liệu thiếu trường, lỗi xác thực hoặc phản hồi không đúng hợp đồng.

Test double nên cho phép tạo các trường hợp này một cách có kiểm soát. Hãy xác minh:

- Hệ thống có phân biệt từ chối nghiệp vụ với lỗi kỹ thuật không?
- Timeout có dẫn đến trạng thái chưa xác định cần đối soát không?
- Retry có tuân theo chính sách và có an toàn với tác dụng phụ không?
- Lỗi từ nhà cung cấp có được ánh xạ thành thông tin phù hợp cho người dùng và log không?
- Dữ liệu không hợp lệ có bị từ chối an toàn không?

Với thao tác thanh toán, timeout không đồng nghĩa giao dịch chắc chắn thất bại. Nhà cung cấp có thể đã xử lý giao dịch nhưng phản hồi không đến được ứng dụng. Cần dùng mã định danh, idempotency và quy trình truy vấn/đối soát phù hợp thay vì gửi lại một khoản thu mới một cách mù quáng.

## 6. Kiểm thử các ranh giới tích hợp

Sau khi tách phụ thuộc, cần có chiến lược xác minh implementation thật và hợp đồng giao tiếp.

### 6.1. Unit test cho logic nghiệp vụ

Unit test dùng đồng hồ cố định, nguồn ngẫu nhiên có thể điều khiển và stub/fake cho dịch vụ ngoài. Nó kiểm tra quy tắc và nhánh một cách nhanh, ổn định.

Ví dụ câu hỏi:

- Mã giảm giá có hiệu lực đúng tại ngày bắt đầu và ngày kết thúc không?
- Khi nguồn chọn trả về chỉ số cuối, logic có xử lý đúng không?
- Khi cổng thanh toán từ chối, đơn hàng có giữ trạng thái phù hợp không?
- Khi dịch vụ tỷ giá không có dữ liệu, nghiệp vụ có từ chối hoặc dùng chính sách dự phòng đúng không?

### 6.2. Contract test cho adapter

Contract test xác minh hai phía thống nhất về request, response, schema, mã lỗi và quy tắc giao tiếp. Có thể dùng provider verification hoặc một bộ kiểm tra hợp đồng độc lập tùy kiến trúc.

Các nội dung nên kiểm tra:

- Đường dẫn, method, header và trường bắt buộc.
- Kiểu dữ liệu, định dạng ngày giờ và quy tắc tiền tệ.
- Mã trạng thái và cấu trúc lỗi.
- Hành vi khi trường tùy chọn vắng mặt hoặc có giá trị null.
- Phiên bản API và khả năng tương thích.
- Cách xử lý timeout, retry và idempotency nếu hợp đồng quy định.

Contract test giúp phát hiện lệch hợp đồng, nhưng không thay thế mọi kiểm tra vận hành với dịch vụ thật.

### 6.3. Integration test với adapter hoặc sandbox

Integration test xác minh adapter kết nối đúng với hệ thống phụ thuộc trong môi trường kiểm soát. Có thể dùng sandbox của nhà cung cấp, server giả lập giao thức hoặc môi trường tích hợp.

Nên kiểm tra:

- Cấu hình endpoint và xác thực.
- Request thực tế được gửi và response được phân tích đúng.
- Timeout và lỗi kết nối được xử lý theo chính sách.
- Serialization/deserialization tương thích.
- Log, trace và correlation ID hỗ trợ điều tra.
- Tài nguyên và dữ liệu được dọn dẹp sau test.

### 6.4. System/E2E test cho hành trình đại diện

Một số luồng cần xác minh nhiều thành phần hoạt động cùng nhau. Giữ một tập E2E đại diện cho các hành trình quan trọng, chẳng hạn tạo đơn, thanh toán sandbox và nhận trạng thái cuối. Không cần lặp lại mọi tổ hợp lỗi ở E2E nếu chúng đã được kiểm tra chi tiết ở tầng thấp hơn.

### 6.5. Ma trận chọn tầng kiểm thử

| Câu hỏi cần trả lời | Tầng phù hợp | Phụ thuộc nên dùng |
|---|---|---|
| Quy tắc ngày hết hạn có đúng không? | Unit | Clock cố định |
| Mọi nhánh chọn phần thưởng có được xử lý không? | Unit | Generator seed cố định hoặc fake |
| Khi cổng thanh toán từ chối, đơn hàng xử lý ra sao? | Unit | Stub PaymentGateway |
| Adapter gửi đúng request theo hợp đồng không? | Contract | Contract fixture hoặc provider verification |
| HTTP client xử lý response và timeout đúng không? | Integration | Server giả lập giao thức hoặc sandbox |
| Luồng mua hàng hoàn tất với các thành phần tích hợp không? | System/E2E | Môi trường tích hợp và sandbox đại diện |

## 7. Thiết kế cấu hình để thay thế phụ thuộc an toàn

Tách phụ thuộc cần có điểm cấu hình rõ ràng để ứng dụng thật và test sử dụng implementation tương ứng.

### 7.1. Cấu hình ở composition root

Composition root là nơi ứng dụng tạo và kết nối các đối tượng chính. Đây là nơi phù hợp để chọn implementation thật, ví dụ `Clock.systemUTC()`, `SecureRandom` hoặc adapter HTTP. Test tạo đối tượng trực tiếp với fake hoặc stub.

Tránh để lớp nghiệp vụ tự kiểm tra biến môi trường hoặc profile rồi tự quyết định tạo mock hay implementation thật. Cách đó làm logic khó hiểu và có thể khiến cấu hình test vô tình lọt vào môi trường sản xuất.

### 7.2. Không dùng service locator toàn cục cho test

Một registry hoặc singleton toàn cục cho phép bất kỳ lớp nào lấy clock, generator hoặc service từ nơi dùng chung. Cách này có thể tiện lúc đầu nhưng khiến phụ thuộc ẩn và làm test song song khó an toàn: một test thay fake có thể ảnh hưởng test khác.

Ưu tiên truyền phụ thuộc rõ ràng. Nếu dùng container DI, hãy cấu hình binding ở composition root và giữ vòng đời phù hợp.

### 7.3. Quản lý cấu hình và bí mật

Endpoint, token, chứng thư và khóa cần được cấu hình qua cơ chế an toàn. Test dùng thông tin xác thực riêng của môi trường kiểm thử hoặc fake. Không đưa bí mật vào mã nguồn, fixture công khai, log hoặc báo cáo.

Đảm bảo test không thể vô tình gọi endpoint sản xuất khi đang chạy trong CI. Có thể dùng allowlist endpoint, cấu hình profile kiểm thử và kiểm tra trước khi thực hiện thao tác có tác dụng phụ.

### 7.4. Giữ implementation thật có thể quan sát

Adapter thật cần log và trace đủ để phân biệt lỗi kết nối, lỗi xác thực, lỗi giao thức và lỗi nghiệp vụ. Dùng correlation ID xuyên các dịch vụ nếu có thể. Không ghi payload nhạy cảm nguyên vẹn khi không cần thiết.

## 8. Các lỗi thiết kế khi tách phụ thuộc

### 8.1. Tạo interface cho mọi lớp

Không phải mọi class đều cần interface chỉ để có thể mock. Interface nên thể hiện ranh giới có ý nghĩa, đặc biệt khi có nhiều implementation hoặc khi cần tách I/O khỏi logic. Tạo abstraction không cần thiết làm tăng số thành phần và chi phí bảo trì.

### 8.2. Mock quá sâu vào chi tiết nội bộ

Nếu test phải mock nhiều phương thức nội bộ theo một chuỗi dài, nó có thể đang phụ thuộc vào cách triển khai hơn là hành vi. Hãy xem xét tách logic thuần, dùng fake ở ranh giới hoặc kiểm tra kết quả nghiệp vụ.

### 8.3. Dùng fake không tương thích với implementation thật

Fake có thể đơn giản hóa hành vi và vô tình bỏ qua quy tắc quan trọng như transaction, unique constraint, timeout hoặc thứ tự sự kiện. Cần có contract test hoặc integration test để phát hiện khác biệt giữa fake và implementation thật.

### 8.4. Tạo một đồng hồ toàn cục có thể thay đổi

Clock toàn cục có thể khiến test chạy song song ảnh hưởng lẫn nhau. Ưu tiên truyền clock theo đối tượng hoặc phạm vi test. Nếu buộc phải dùng cơ chế toàn cục, cần reset an toàn và không chạy đồng thời các test thay đổi nó.

### 8.5. Dùng seed cố định trong môi trường thật

Seed cố định phù hợp với kiểm thử tái lập, nhưng có thể làm mất tính khó đoán cần thiết của token bảo mật hoặc dữ liệu ngẫu nhiên trong sản xuất. Phải phân biệt nguồn ngẫu nhiên nghiệp vụ với nguồn ngẫu nhiên mật mã.

### 8.6. Giả lập thời gian nhưng bỏ qua múi giờ

Clock cố định theo UTC không tự chứng minh logic ngày địa phương đúng. Cần xác định múi giờ nghiệp vụ và kiểm tra các thời điểm sát ranh giới ngày, giờ mùa hè nếu miền hoạt động có áp dụng.

### 8.7. Chỉ kiểm thử fake mà không kiểm thử adapter thật

Unit test đạt với stub chỉ chứng minh logic xử lý kết quả giả lập. Cần contract/integration test để xác minh adapter và cấu hình thực sự giao tiếp đúng.

## 9. Ví dụ tổng hợp: kiểm tra dịch vụ tính phí giao hàng

Giả sử phí giao hàng phụ thuộc vào thời điểm đặt hàng, lựa chọn ngẫu nhiên một đối tác khi nhiều đối tác có cùng mức giá và dịch vụ định tuyến bên ngoài trả về khoảng cách.

### 9.1. Thiết kế ban đầu khó kiểm thử

Một lớp có thể trực tiếp gọi `Instant.now()`, `new Random()` và HTTP client trong cùng phương thức. Test phải chờ thời gian thật, không kiểm soát được đối tác được chọn và cần dịch vụ định tuyến đang hoạt động. Khi test thất bại, khó biết nguyên nhân nằm ở quy tắc tính phí hay dịch vụ ngoài.

### 9.2. Tách các phụ thuộc

Định nghĩa các hợp đồng nhỏ:

```java
public interface RouteDistanceProvider {
    Distance distanceFor(Address origin, Address destination);
}

public interface PartnerSelector {
    Partner select(List<Partner> candidates);
}
```

Dịch vụ tính phí nhận các phụ thuộc:

```java
public final class DeliveryFeeService {
    private final Clock clock;
    private final RouteDistanceProvider routeProvider;
    private final PartnerSelector partnerSelector;

    public DeliveryFeeService(
            Clock clock,
            RouteDistanceProvider routeProvider,
            PartnerSelector partnerSelector) {
        this.clock = clock;
        this.routeProvider = routeProvider;
        this.partnerSelector = partnerSelector;
    }

    public DeliveryQuote quote(
            Address origin,
            Address destination,
            List<Partner> candidates) {
        Instant quotedAt = Instant.now(clock);
        Distance distance = routeProvider.distanceFor(origin, destination);
        Partner partner = partnerSelector.select(candidates);
        Money fee = calculateFee(distance, partner, quotedAt);
        return new DeliveryQuote(fee, partner.id(), quotedAt);
    }
}
```

Hàm `calculateFee` nên được tách thành quy tắc thuần nếu có thể. Ví dụ chỉ tập trung vào ranh giới phụ thuộc; việc chọn đối tác thực tế cần xử lý trường hợp danh sách rỗng, đối tác không khả dụng và chính sách ưu tiên.

### 9.3. Kiểm thử logic với fake

- Cố định clock để kiểm tra bảng giá theo thời điểm.
- Dùng fake route provider trả về khoảng cách đã biết.
- Dùng selector giả lập trả về đối tác xác định.
- Kiểm tra phí, đối tác và timestamp trong kết quả.
- Kiểm tra các trường hợp khoảng cách biên và không có đối tác phù hợp.

### 9.4. Kiểm thử adapter riêng

Một integration test dùng server giả lập giao thức hoặc môi trường sandbox để xác minh adapter gửi đúng địa chỉ, xử lý đơn vị đo, parse response, timeout và lỗi. Contract test xác minh schema request/response. Một E2E đại diện xác minh hành trình đặt giao hàng trên môi trường tích hợp.

### 9.5. Bằng chứng và giới hạn

Test unit chứng minh quy tắc tính phí với đầu vào xác định. Contract test chứng minh cấu trúc giao tiếp theo hợp đồng. Integration test chứng minh adapter xử lý giao thức trong môi trường được chọn. E2E chứng minh các thành phần phối hợp trong một hành trình. Báo cáo phải nêu rõ phụ thuộc nào dùng fake, sandbox hay dịch vụ thật để tránh diễn giải quá mức phạm vi đã kiểm tra.

## 10. Quy trình áp dụng trong dự án

Có thể áp dụng các bước sau khi một thành phần khó kiểm thử do phụ thuộc bên ngoài:

1. **Xác định hành vi cần kiểm tra:** mô tả quy tắc, đầu vào, kết quả và rủi ro.
2. **Liệt kê phụ thuộc:** thời gian, nguồn ngẫu nhiên, dịch vụ, dữ liệu, tài nguyên và môi trường.
3. **Xác định điểm tạo phụ thuộc:** tìm nơi gọi đồng hồ, khởi tạo generator hoặc tạo client.
4. **Chọn ranh giới phù hợp:** truyền tham số, dùng interface nhỏ hoặc adapter.
5. **Cấu hình implementation thật:** kết nối clock, generator và adapter ở composition root.
6. **Tạo test double có mục tiêu:** fixed clock, seeded/fake generator, stub hoặc fake service.
7. **Viết unit test:** kiểm tra quy tắc và nhánh bằng điều kiện xác định.
8. **Viết contract/integration test:** xác minh adapter và hợp đồng với phụ thuộc thật hoặc môi trường kiểm soát.
9. **Kiểm tra an toàn cấu hình:** bảo đảm test không gọi nhầm production và không làm lộ bí mật.
10. **Theo dõi sau triển khai:** quan sát lỗi môi trường, độ ổn định và sai lệch giữa fake với hệ thống thật.

Không cần tách mọi phụ thuộc cùng lúc. Ưu tiên nơi biến thiên đang gây test không ổn định, nơi có rủi ro cao hoặc nơi việc tái hiện lỗi đang tốn nhiều công sức.

## 11. Danh sách rà soát khả năng kiểm thử của phụ thuộc

Trước khi hoàn tất thiết kế hoặc review một thành phần, hãy kiểm tra:

- [ ] Logic nghiệp vụ không tự đọc thời gian hệ thống ở nhiều vị trí không kiểm soát.
- [ ] Clock được truyền vào và có thể cố định trong test.
- [ ] Múi giờ nghiệp vụ và kiểu dữ liệu thời gian được xác định.
- [ ] Đo thời lượng dùng nguồn đơn điệu khi phù hợp.
- [ ] Nguồn ngẫu nhiên có thể điều khiển và seed được lưu khi cần tái lập.
- [ ] Nguồn ngẫu nhiên mật mã không bị thay bằng generator dễ đoán trong môi trường thật.
- [ ] ID hoặc token có thể được tạo qua hợp đồng phù hợp khi cần test.
- [ ] Dịch vụ ngoài được truy cập qua port/adapter có hợp đồng nhỏ.
- [ ] Test double được chọn đúng mục tiêu và không thay thế bằng chứng tích hợp cần thiết.
- [ ] Có contract test hoặc integration test cho adapter quan trọng.
- [ ] Timeout, retry, lỗi và tác dụng phụ được kiểm tra theo chính sách.
- [ ] Phụ thuộc có vòng đời và phạm vi chia sẻ rõ ràng.
- [ ] Cấu hình test không thể vô tình gọi endpoint sản xuất.
- [ ] Log và trace hỗ trợ chẩn đoán mà không lộ bí mật hoặc dữ liệu nhạy cảm.
- [ ] Báo cáo nêu rõ phần nào dùng fake, sandbox và dịch vụ thật.

## 12. Kết luận

Tách phụ thuộc vào thời gian, ngẫu nhiên và dịch vụ ngoài giúp kiểm thử có thể điều khiển, tái lập và chẩn đoán tốt hơn. Logic nghiệp vụ nên nhận các khả năng bên ngoài qua tham số hoặc hợp đồng rõ ràng; cấu hình ứng dụng chọn implementation thật, còn test có thể dùng clock cố định, generator có seed hoặc fake/stub phù hợp.

Việc thay thế phụ thuộc trong unit test cần đi cùng contract test và integration test ở các ranh giới quan trọng. Clock lịch phải được phân biệt với đồng hồ đo thời lượng; seed cố định chỉ dùng cho kiểm thử tái lập, không làm suy yếu nguồn ngẫu nhiên bảo mật; fake phải được đối chiếu với implementation thật. Thiết kế tốt giúp test kiểm soát được biến thiên mà vẫn cung cấp bằng chứng đúng về cách hệ thống hoạt động khi tích hợp.
