# Kiểm thử dịch vụ miền bằng dữ liệu và phụ thuộc có thể kiểm soát

Trong Domain-Driven Design (DDD), Domain Service (dịch vụ miền) biểu diễn một hành vi nghiệp vụ quan trọng nhưng không thuộc tự nhiên về một Entity hay Value Object cụ thể. Dịch vụ miền thường nhận các đối tượng hoặc giá trị đầu vào, áp dụng quy tắc và trả về một kết quả có ý nghĩa nghiệp vụ. Để kiểm thử đáng tin cậy, ta cần kiểm soát dữ liệu đầu vào và những phụ thuộc ảnh hưởng đến quyết định của dịch vụ.

Một Domain Service có thể phụ thuộc vào thời gian hiện tại, chính sách, dữ liệu tra cứu hoặc một dịch vụ miền khác. Nếu những phụ thuộc này được gọi trực tiếp từ hệ thống bên ngoài, kiểm thử dễ trở nên chậm, không ổn định và khó tái hiện lỗi. Thiết kế phụ thuộc qua abstraction, sau đó cung cấp dữ liệu giả lập có chủ đích, giúp kiểm tra hành vi nghiệp vụ một cách lặp lại được.

Bài học này trình bày cách xác định điều cần kiểm thử trong Domain Service, tổ chức dữ liệu kiểm thử, dùng fake hoặc stub để kiểm soát phụ thuộc, cố định thời gian bằng Clock, kiểm tra các trường hợp biên và phân biệt unit test với integration test. Ví dụ xuyên suốt sử dụng dịch vụ đánh giá điều kiện áp dụng khuyến mãi cho khách hàng.

## 1. Domain Service và trách nhiệm cần kiểm thử

### 1.1. Khi nào một hành vi thuộc Domain Service?

Một hành vi nên nằm trong Domain Service khi nó thể hiện quy tắc miền nhưng không thuộc tự nhiên về một Entity hoặc Value Object riêng lẻ.

Ví dụ, việc đánh giá một khuyến mãi có được áp dụng cho một đơn hàng hay không có thể cần đồng thời:

- Chính sách của chương trình khuyến mãi.
- Hạng thành viên của khách hàng.
- Giá trị đơn hàng.
- Số lần khách đã sử dụng chương trình.
- Thời điểm đánh giá.

Không một đối tượng nào trong số đó nhất thiết sở hữu toàn bộ quyết định. Một PromotionEligibilityService có thể biểu diễn quy tắc phối hợp các thông tin này và trả về quyết định đủ điều kiện hoặc lý do từ chối.

Domain Service không nên trở thành nơi chứa mọi logic. Nếu hành vi chỉ thay đổi trạng thái của một Entity, hãy cân nhắc đặt nó trong Entity. Nếu hành vi chỉ kiểm tra một giá trị độc lập, Value Object có thể là nơi phù hợp hơn.

### 1.2. Kiểm thử hành vi nghiệp vụ, không kiểm tra cấu trúc nội bộ

Một bài kiểm thử tốt tập trung vào kết quả mà người sử dụng mô hình có thể quan sát:

- Với dữ liệu đầu vào nào, dịch vụ chấp thuận?
- Điều kiện nào khiến dịch vụ từ chối?
- Khi có nhiều điều kiện không thỏa mãn, lý do nào được trả về?
- Phụ thuộc được gọi với đúng định danh và tham số cần thiết không?
- Lỗi kỹ thuật từ phụ thuộc được xử lý theo hợp đồng nào?

Không nên kiểm thử những chi tiết như thứ tự gọi private method, tên biến nội bộ hoặc cách tổ chức vòng lặp nếu chúng không phải cam kết nghiệp vụ. Khi cách cài đặt thay đổi nhưng hành vi vẫn đúng, test nên tiếp tục vượt qua.

### 1.3. Phân biệt Domain Service với Application Service

Hai loại dịch vụ có mục đích khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Domain Service | Quyết định hoặc tính toán theo quy tắc nghiệp vụ | Đánh giá khách có đủ điều kiện dùng khuyến mãi |
| Application Service | Điều phối một ca sử dụng | Tải khách hàng, đơn hàng, gọi Domain Service, lưu kết quả |
| Infrastructure Adapter | Kết nối hệ thống bên ngoài | Đọc lịch sử sử dụng khuyến mãi từ database hoặc API |

Unit test cho Domain Service thường không cần khởi động Spring, database hay message broker. Các thành phần đó được kiểm tra ở tầng tích hợp phù hợp.

## 2. Xác định hợp đồng của dịch vụ trước khi viết test

Trước khi tạo dữ liệu giả, hãy viết rõ đầu vào, đầu ra, điều kiện và những phụ thuộc của Domain Service.

### 2.1. Mô tả hành vi bằng ví dụ nghiệp vụ

Giả sử chương trình khuyến mãi có các điều kiện:

- Chương trình chỉ có hiệu lực từ thời điểm bắt đầu đến trước thời điểm kết thúc.
- Chỉ khách thuộc hạng thành viên được chỉ định mới được tham gia.
- Giá trị đơn hàng phải đạt mức tối thiểu.
- Mỗi khách chỉ được sử dụng chương trình tối đa một số lần.
- Khi mọi điều kiện đều thỏa mãn, dịch vụ trả về quyết định đủ điều kiện.

Đây là chính sách giả định cho bài học. Hệ thống thực tế cần xác nhận cách tính thời hạn, cách đếm lần sử dụng và cách xử lý đơn bị hủy hoặc hoàn tiền.

### 2.2. Viết bảng quyết định

Bảng quyết định giúp nhìn thấy các nhánh cần kiểm thử:

| Điều kiện | Kết quả mong đợi |
|---|---|
| Chương trình chưa bắt đầu | Từ chối: chưa có hiệu lực |
| Chương trình đã hết hạn | Từ chối: hết hiệu lực |
| Hạng thành viên không được hỗ trợ | Từ chối: không đủ hạng |
| Giá trị đơn thấp hơn mức tối thiểu | Từ chối: chưa đạt giá trị tối thiểu |
| Số lần sử dụng đã đạt giới hạn | Từ chối: hết lượt sử dụng |
| Tất cả điều kiện đều đạt | Chấp thuận |

Bảng này là cơ sở để tạo test case. Mỗi dòng nên có ít nhất một trường hợp kiểm thử. Các điều kiện biên như đúng thời điểm bắt đầu, đúng thời điểm kết thúc và đúng ngưỡng tiền cần được kiểm tra riêng.

### 2.3. Xác định thứ tự đánh giá

Nếu dịch vụ trả về lý do từ chối đầu tiên, thứ tự kiểm tra là một phần của hành vi quan sát được. Ví dụ, một khách vừa không đủ hạng vừa có đơn dưới mức tối thiểu sẽ nhận lý do nào?

Có hai cách thiết kế thường gặp:

- Trả về lý do đầu tiên theo thứ tự chính sách đã định nghĩa.
- Thu thập tất cả lý do không đạt trong một kết quả.

Hãy chọn theo nhu cầu nghiệp vụ và thể hiện rõ trong hợp đồng. Bài học này dùng cách trả về lý do đầu tiên để ví dụ đơn giản và dễ kiểm tra.

## 3. Thiết kế phụ thuộc để có thể kiểm soát trong kiểm thử

### 3.1. Không gọi trực tiếp hạ tầng từ Domain Service

Nếu Domain Service tự mở kết nối database, gọi HTTP hoặc đọc đồng hồ hệ thống, test sẽ phải phụ thuộc môi trường bên ngoài. Một lỗi mạng hoặc dữ liệu thay đổi có thể làm test thất bại dù quy tắc miền không đổi.

Thay vào đó, Domain Service nên nhận các phụ thuộc qua constructor hoặc tham số. Phụ thuộc biểu diễn nhu cầu nghiệp vụ bằng interface hoặc abstraction phù hợp.

Ví dụ, dịch vụ cần biết khách đã sử dụng khuyến mãi bao nhiêu lần. Nó có thể phụ thuộc vào một interface chỉ đọc:

~~~java
public interface PromotionUsageLookup {
    int completedUses(CustomerId customerId, PromotionId promotionId);
}
~~~

Trong production, adapter có thể truy vấn database. Trong unit test, một fake nhỏ trả về số lần sử dụng do test thiết lập.

### 3.2. Dùng Clock thay cho gọi thời gian hệ thống trực tiếp

Tránh gọi Instant.now() rải rác bên trong logic cần kiểm thử. Khi test chạy ở thời điểm khác nhau, kết quả có thể thay đổi.

Tiêm java.time.Clock vào dịch vụ:

~~~java
public PromotionEligibilityService(
    PromotionUsageLookup usageLookup,
    Clock clock
) {
    this.usageLookup = usageLookup;
    this.clock = clock;
}
~~~

Production có thể dùng Clock.systemUTC(). Test dùng Clock.fixed(...) để thời gian luôn giống nhau.

Cách này giúp kiểm thử chính xác thời điểm bắt đầu, thời điểm kết thúc và các điều kiện liên quan đến ngày giờ.

### 3.3. Phân biệt dependency với dữ liệu đầu vào

Không phải mọi giá trị đều cần mock:

- Customer, Promotion và Money là dữ liệu miền đầu vào; nên tạo object thật với giá trị có ý nghĩa.
- Clock là phụ thuộc cung cấp thời gian; có thể dùng fixed clock.
- PromotionUsageLookup là nguồn dữ liệu cần truy vấn; có thể dùng fake hoặc stub.
- Database adapter là hạ tầng; kiểm thử riêng bằng integration test.

Ưu tiên đối tượng miền thật trong unit test. Mock quá nhiều Entity hoặc Value Object có thể khiến test chỉ xác nhận cách mock được cấu hình, không xác nhận quy tắc thực sự.

### 3.4. Chỉ tạo abstraction khi có ranh giới hợp lý

Không cần tạo interface cho mọi lớp chỉ để dễ mock. Một phép tính thuần túy có thể nhận tham số trực tiếp và không cần phụ thuộc nào khác.

Abstraction hữu ích khi nó đại diện cho một nguồn dữ liệu, chính sách hoặc khả năng bên ngoài mà Domain Service cần sử dụng. Interface nên diễn đạt ngôn ngữ miền, chẳng hạn PromotionUsageLookup, thay vì tên kỹ thuật chung chung như GenericService.

## 4. Xây dựng ví dụ Domain Service

Các đoạn Java dưới đây dùng Java 17. Import chuẩn được lược bỏ để tập trung vào mô hình; các kiểu public có thể đặt trong file riêng khi triển khai.

### 4.1. Các kiểu dữ liệu miền

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Customer id is required"
            );
        }
    }
}
~~~

~~~java
public record PromotionId(String value) {
    public PromotionId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Promotion id is required"
            );
        }
    }
}
~~~

~~~java
public enum MembershipTier {
    BASIC,
    SILVER,
    GOLD
}
~~~

~~~java
public record Customer(
    CustomerId id,
    MembershipTier tier
) {
    public Customer {
        Objects.requireNonNull(id);
        Objects.requireNonNull(tier);
    }
}
~~~

Money biểu diễn số tiền và loại tiền. Ví dụ này cho phép giá trị không âm và so sánh hai khoản tiền cùng currency:

~~~java
public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Money cannot be negative"
            );
        }
    }

    public boolean isAtLeast(Money other) {
        requireSameCurrency(other);
        return amount.compareTo(other.amount) >= 0;
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currencies must match"
            );
        }
    }
}
~~~

### 4.2. Promotion chứa chính sách của chương trình

~~~java
public record Promotion(
    PromotionId id,
    Instant startsAt,
    Instant endsAt,
    Money minimumOrder,
    Set<MembershipTier> eligibleTiers,
    int maxUsesPerCustomer
) {
    public Promotion {
        Objects.requireNonNull(id);
        Objects.requireNonNull(startsAt);
        Objects.requireNonNull(endsAt);
        Objects.requireNonNull(minimumOrder);
        Objects.requireNonNull(eligibleTiers);

        if (!endsAt.isAfter(startsAt)) {
            throw new IllegalArgumentException(
                "Promotion end must be after start"
            );
        }

        if (maxUsesPerCustomer <= 0) {
            throw new IllegalArgumentException(
                "Usage limit must be positive"
            );
        }

        eligibleTiers = Set.copyOf(eligibleTiers);

        if (eligibleTiers.isEmpty()) {
            throw new IllegalArgumentException(
                "At least one eligible tier is required"
            );
        }
    }

    public boolean isActiveAt(Instant instant) {
        return !instant.isBefore(startsAt)
            && instant.isBefore(endsAt);
    }

    public boolean accepts(MembershipTier tier) {
        return eligibleTiers.contains(tier);
    }
}
~~~

Chính sách trong ví dụ dùng khoảng thời gian đóng ở đầu và mở ở cuối: thời điểm bắt đầu được chấp nhận, thời điểm kết thúc không còn hiệu lực. Nếu doanh nghiệp chọn cách tính khác, hãy thay đổi phương thức isActiveAt và các test biên tương ứng.

### 4.3. Kết quả đánh giá

~~~java
public enum RejectionReason {
    NOT_STARTED,
    EXPIRED,
    INELIGIBLE_TIER,
    ORDER_BELOW_MINIMUM,
    USAGE_LIMIT_REACHED
}
~~~

~~~java
public record PromotionDecision(
    boolean eligible,
    RejectionReason rejectionReason
) {
    public PromotionDecision {
        if (eligible && rejectionReason != null) {
            throw new IllegalArgumentException(
                "An eligible decision cannot have a rejection reason"
            );
        }

        if (!eligible && rejectionReason == null) {
            throw new IllegalArgumentException(
                "A rejected decision requires a reason"
            );
        }
    }

    public static PromotionDecision approved() {
        return new PromotionDecision(true, null);
    }

    public static PromotionDecision rejected(
        RejectionReason reason
    ) {
        return new PromotionDecision(false, reason);
    }
}
~~~

Kết quả là một Value Object đơn giản, giúp caller phân biệt quyết định chấp thuận với từng lý do từ chối. Có thể dùng sealed interface hoặc các kiểu kết quả riêng nếu miền có nhiều loại kết quả phức tạp hơn.

### 4.4. Interface tra cứu lịch sử sử dụng

~~~java
public interface PromotionUsageLookup {
    int completedUses(
        CustomerId customerId,
        PromotionId promotionId
    );
}
~~~

Interface này chỉ trả về số lần sử dụng đã hoàn tất theo định nghĩa của nghiệp vụ. Nó không quyết định khuyến mãi có hợp lệ hay không; quyết định đó thuộc Domain Service.

### 4.5. Cài đặt Domain Service

~~~java
public final class PromotionEligibilityService {

    private final PromotionUsageLookup usageLookup;
    private final Clock clock;

    public PromotionEligibilityService(
        PromotionUsageLookup usageLookup,
        Clock clock
    ) {
        this.usageLookup = Objects.requireNonNull(usageLookup);
        this.clock = Objects.requireNonNull(clock);
    }

    public PromotionDecision evaluate(
        Promotion promotion,
        Customer customer,
        Money orderSubtotal
    ) {
        Objects.requireNonNull(promotion);
        Objects.requireNonNull(customer);
        Objects.requireNonNull(orderSubtotal);

        Instant now = clock.instant();

        if (now.isBefore(promotion.startsAt())) {
            return PromotionDecision.rejected(
                RejectionReason.NOT_STARTED
            );
        }

        if (!promotion.isActiveAt(now)) {
            return PromotionDecision.rejected(
                RejectionReason.EXPIRED
            );
        }

        if (!promotion.accepts(customer.tier())) {
            return PromotionDecision.rejected(
                RejectionReason.INELIGIBLE_TIER
            );
        }

        if (!orderSubtotal.isAtLeast(promotion.minimumOrder())) {
            return PromotionDecision.rejected(
                RejectionReason.ORDER_BELOW_MINIMUM
            );
        }

        int completedUses = usageLookup.completedUses(
            customer.id(),
            promotion.id()
        );

        if (completedUses < 0) {
            throw new IllegalStateException(
                "Usage lookup returned a negative count"
            );
        }

        if (completedUses >= promotion.maxUsesPerCustomer()) {
            return PromotionDecision.rejected(
                RejectionReason.USAGE_LIMIT_REACHED
            );
        }

        return PromotionDecision.approved();
    }
}
~~~

Dịch vụ kiểm tra các điều kiện theo thứ tự đã xác định. Chỉ khi chương trình còn hiệu lực, khách đúng hạng và đơn đạt ngưỡng thì nó mới cần tra cứu lịch sử sử dụng.

Một lỗi kỹ thuật từ PromotionUsageLookup được truyền ra để tầng ứng dụng quyết định cách xử lý. Không nên biến lỗi database hoặc timeout thành kết luận “khách không đủ điều kiện”, vì hai kết quả có ý nghĩa khác nhau.

## 5. Tạo dữ liệu kiểm thử có chủ đích

### 5.1. Dùng fixture để mô tả bối cảnh

Một fixture là tập dữ liệu chuẩn bị cho một nhóm test. Fixture tốt giúp người đọc hiểu điều kiện nghiệp vụ mà không phải đọc quá nhiều dòng thiết lập.

Ví dụ:

~~~java
class PromotionEligibilityServiceTest {

    private static final Instant NOW =
        Instant.parse("2026-05-10T10:00:00Z");

    private static final Currency VND =
        Currency.getInstance("VND");

    private Promotion activePromotion() {
        return new Promotion(
            new PromotionId("PROMO-1"),
            NOW.minus(Duration.ofDays(1)),
            NOW.plus(Duration.ofDays(1)),
            new Money(new BigDecimal("500000"), VND),
            Set.of(MembershipTier.SILVER, MembershipTier.GOLD),
            1
        );
    }

    private Customer goldCustomer() {
        return new Customer(
            new CustomerId("CUS-1"),
            MembershipTier.GOLD
        );
    }

    private Money eligibleSubtotal() {
        return new Money(new BigDecimal("800000"), VND);
    }
}
~~~

Các fixture thể hiện rõ: chương trình đang có hiệu lực, khách thuộc hạng được chấp nhận và đơn vượt mức tối thiểu.

Tránh dùng dữ liệu tùy tiện như BigDecimal("1") ở mọi test. Hãy chọn giá trị giúp người đọc nhận ra điều kiện đang được kiểm tra.

### 5.2. Mỗi test nên thay đổi một điều kiện chính

Khi kiểm tra khách không đủ hạng, giữ các điều kiện khác hợp lệ. Khi kiểm tra giá trị đơn thấp hơn ngưỡng, giữ chương trình còn hiệu lực và khách đúng hạng.

Cách này giúp nếu test thất bại, nguyên nhân dễ xác định. Nếu thay đổi nhiều yếu tố cùng lúc, test có thể chỉ chứng minh một điều kiện nào đó đã từ chối chứ không chắc điều kiện mục tiêu hoạt động đúng.

### 5.3. Kiểm tra cả hai phía của ngưỡng

Với một quy tắc có ngưỡng, nên kiểm tra:

- Ngay dưới ngưỡng.
- Đúng bằng ngưỡng.
- Ngay trên ngưỡng.

Ví dụ, nếu minimumOrder là 500.000 VND, hãy kiểm tra 499.999, 500.000 và 500.001 VND. Điều này giúp phát hiện nhầm lẫn giữa < và <=.

Tương tự, với thời gian, hãy kiểm tra ngay trước thời điểm bắt đầu, đúng thời điểm bắt đầu, ngay trước thời điểm kết thúc và đúng thời điểm kết thúc theo chính sách đã chọn.

## 6. Dùng Fake và Stub để kiểm soát phụ thuộc

### 6.1. Stub trả về dữ liệu định trước

Stub là một thành phần thay thế cung cấp kết quả cố định để kiểm thử một nhánh.

~~~java
PromotionUsageLookup noPriorUses = (customerId, promotionId) -> 0;
~~~

Stub này giúp kiểm tra trường hợp khách chưa sử dụng khuyến mãi. Nó không cần database hoặc dữ liệu mạng.

Có thể dùng lambda khi interface chỉ có một phương thức và hành vi thay thế đơn giản.

### 6.2. Fake mô phỏng hành vi nhỏ có trạng thái

Fake là một triển khai đơn giản có thể lưu dữ liệu trong bộ nhớ. Nó hữu ích khi nhiều test cần thiết lập số lần sử dụng khác nhau.

~~~java
final class InMemoryPromotionUsageLookup
    implements PromotionUsageLookup {

    private record UsageKey(
        CustomerId customerId,
        PromotionId promotionId
    ) {
    }

    private final Map<UsageKey, Integer> counts =
        new HashMap<>();

    public void setCompletedUses(
        CustomerId customerId,
        PromotionId promotionId,
        int count
    ) {
        counts.put(new UsageKey(customerId, promotionId), count);
    }

    @Override
    public int completedUses(
        CustomerId customerId,
        PromotionId promotionId
    ) {
        return counts.getOrDefault(
            new UsageKey(customerId, promotionId),
            0
        );
    }
}
~~~

Fake này đủ cho unit test vì mục tiêu là kiểm soát kết quả tra cứu. Nó không mô phỏng transaction, index, SQL hoặc concurrency của database thật.

### 6.3. Khi nào dùng Mock?

Mock hữu ích khi cần xác nhận một tương tác là bắt buộc, chẳng hạn:

- Một phụ thuộc được gọi với đúng customer ID và promotion ID.
- Một thao tác gửi thông báo phải được yêu cầu sau quyết định.
- Một cổng bên ngoài không được gọi khi điều kiện đầu vào đã không hợp lệ.

Không nên mock mọi đối tượng trong test. Nếu chỉ kiểm tra lời gọi mà không kiểm tra kết quả nghiệp vụ, test có thể vượt qua dù quyết định sai.

### 6.4. Tránh fake quá thông minh

Fake nên đơn giản và đáng tin cậy. Nếu fake tự triển khai toàn bộ quy tắc của database hoặc chính sách production, test có thể đang kiểm tra hai phiên bản khác nhau của cùng một logic.

Đối với thuật toán hoặc chính sách quan trọng, ưu tiên dùng implementation thật trong unit test. Fake chỉ thay thế phần dữ liệu hoặc khả năng bên ngoài mà test cần kiểm soát.

## 7. Cố định thời gian để kiểm thử chính xác

### 7.1. Tạo Clock cố định

JUnit test có thể dùng:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-05-10T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Khi gọi fixedClock.instant(), kết quả luôn là cùng một thời điểm. Test không phụ thuộc ngày giờ máy đang chạy.

### 7.2. Kiểm tra thời điểm bắt đầu và kết thúc

Với chính sách khoảng thời gian đóng ở đầu và mở ở cuối:

- now < startsAt: chưa có hiệu lực.
- now == startsAt: có hiệu lực.
- startsAt < now < endsAt: có hiệu lực.
- now == endsAt: đã hết hiệu lực.
- now > endsAt: đã hết hiệu lực.

Nên có test cho các thời điểm biên vì lỗi timezone, precision hoặc toán tử so sánh thường xuất hiện tại đây.

### 7.3. Không dùng sleep trong unit test

Thread.sleep() khiến test chậm và phụ thuộc scheduler của hệ điều hành. Với logic thời gian, hãy dịch chuyển thời điểm bằng cách tạo Clock khác hoặc dùng Clock có thể điều chỉnh trong test.

Nếu nghiệp vụ liên quan đến múi giờ địa phương, cần xác định rõ timezone và daylight saving time. Tránh dựa vào timezone mặc định của máy phát triển hoặc CI.

## 8. Viết unit test cho Domain Service

### 8.1. Test trường hợp đủ điều kiện

~~~java
@Test
void shouldApprovePromotionForEligibleCustomer() {
    Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
    PromotionUsageLookup usageLookup = (customerId, promotionId) -> 0;

    PromotionEligibilityService service =
        new PromotionEligibilityService(usageLookup, clock);

    PromotionDecision decision = service.evaluate(
        activePromotion(),
        goldCustomer(),
        eligibleSubtotal()
    );

    assertTrue(decision.eligible());
    assertNull(decision.rejectionReason());
}
~~~

Test này dùng đối tượng miền thật, Clock cố định và stub đơn giản cho lịch sử sử dụng.

### 8.2. Test khách chưa đủ hạng

~~~java
@Test
void shouldRejectCustomerWithIneligibleTier() {
    PromotionEligibilityService service =
        new PromotionEligibilityService(
            (customerId, promotionId) -> 0,
            Clock.fixed(NOW, ZoneOffset.UTC)
        );

    Customer basicCustomer = new Customer(
        new CustomerId("CUS-2"),
        MembershipTier.BASIC
    );

    PromotionDecision decision = service.evaluate(
        activePromotion(),
        basicCustomer,
        eligibleSubtotal()
    );

    assertFalse(decision.eligible());
    assertEquals(
        RejectionReason.INELIGIBLE_TIER,
        decision.rejectionReason()
    );
}
~~~

Chỉ hạng thành viên thay đổi so với fixture hợp lệ. Vì vậy test tập trung đúng vào điều kiện hạng.

### 8.3. Test giá trị đơn ngay dưới ngưỡng

~~~java
@Test
void shouldRejectOrderBelowMinimum() {
    PromotionEligibilityService service =
        new PromotionEligibilityService(
            (customerId, promotionId) -> 0,
            Clock.fixed(NOW, ZoneOffset.UTC)
        );

    Money subtotal = new Money(
        new BigDecimal("499999"),
        VND
    );

    PromotionDecision decision = service.evaluate(
        activePromotion(),
        goldCustomer(),
        subtotal
    );

    assertEquals(
        RejectionReason.ORDER_BELOW_MINIMUM,
        decision.rejectionReason()
    );
}
~~~

Nên bổ sung test đúng bằng 500.000 VND để xác nhận ngưỡng là bao gồm giá trị tối thiểu.

### 8.4. Test đã dùng hết lượt

~~~java
@Test
void shouldRejectWhenUsageLimitReached() {
    PromotionUsageLookup usageLookup =
        (customerId, promotionId) -> 1;

    PromotionEligibilityService service =
        new PromotionEligibilityService(
            usageLookup,
            Clock.fixed(NOW, ZoneOffset.UTC)
        );

    PromotionDecision decision = service.evaluate(
        activePromotion(),
        goldCustomer(),
        eligibleSubtotal()
    );

    assertEquals(
        RejectionReason.USAGE_LIMIT_REACHED,
        decision.rejectionReason()
    );
}
~~~

Với giới hạn bằng 1, số lần đã hoàn tất là 1 thì khách không còn lượt. Hãy kiểm tra cả số lần bằng 0 và số lần lớn hơn giới hạn nếu dữ liệu lịch sử có thể bị nhập sai.

### 8.5. Test thời gian trước khi bắt đầu và tại thời điểm kết thúc

~~~java
@Test
void shouldRejectBeforePromotionStarts() {
    Clock beforeStart = Clock.fixed(
        NOW.minus(Duration.ofDays(2)),
        ZoneOffset.UTC
    );

    PromotionEligibilityService service =
        new PromotionEligibilityService(
            (customerId, promotionId) -> 0,
            beforeStart
        );

    PromotionDecision decision = service.evaluate(
        activePromotion(),
        goldCustomer(),
        eligibleSubtotal()
    );

    assertEquals(
        RejectionReason.NOT_STARTED,
        decision.rejectionReason()
    );
}
~~~

~~~java
@Test
void shouldRejectAtPromotionEndInstant() {
    Promotion promotion = activePromotion();

    Clock atEnd = Clock.fixed(
        promotion.endsAt(),
        ZoneOffset.UTC
    );

    PromotionEligibilityService service =
        new PromotionEligibilityService(
            (customerId, promotionId) -> 0,
            atEnd
        );

    PromotionDecision decision = service.evaluate(
        promotion,
        goldCustomer(),
        eligibleSubtotal()
    );

    assertEquals(
        RejectionReason.EXPIRED,
        decision.rejectionReason()
    );
}
~~~

Test thời điểm kết thúc xác nhận chính sách end-exclusive. Một test khác nên xác nhận đúng thời điểm bắt đầu được chấp nhận.

### 8.6. Test phụ thuộc nhận đúng tham số

Nếu việc tra cứu chỉ được thực hiện sau khi các điều kiện khác đạt, có thể dùng fake ghi nhận lời gọi:

~~~java
final class RecordingPromotionUsageLookup
    implements PromotionUsageLookup {

    private CustomerId lastCustomerId;
    private PromotionId lastPromotionId;
    private int completedUses;

    RecordingPromotionUsageLookup(int completedUses) {
        this.completedUses = completedUses;
    }

    @Override
    public int completedUses(
        CustomerId customerId,
        PromotionId promotionId
    ) {
        this.lastCustomerId = customerId;
        this.lastPromotionId = promotionId;
        return completedUses;
    }

    CustomerId lastCustomerId() {
        return lastCustomerId;
    }

    PromotionId lastPromotionId() {
        return lastPromotionId;
    }
}
~~~

Sau khi gọi service, test có thể xác nhận đúng định danh đã được truyền. Đồng thời, một test khách không đủ hạng có thể xác nhận lookup chưa được gọi nếu hợp đồng yêu cầu dừng sớm.

Chỉ kiểm tra tương tác khi nó là một phần có ý nghĩa của hành vi hoặc giúp bảo đảm tránh truy cập dữ liệu không cần thiết. Đừng làm test phụ thuộc quá mức vào thứ tự gọi nội bộ.

## 9. Kiểm thử dữ liệu biên và dữ liệu không hợp lệ

### 9.1. Kiểm tra constructor của mô hình

Promotion nên từ chối khoảng thời gian không hợp lệ, giới hạn sử dụng không dương và danh sách hạng rỗng. Những điều kiện này thuộc chính sách của Promotion nên có thể kiểm thử riêng bằng unit test cho Value Object hoặc Entity.

### 9.2. Kiểm tra tiền tệ không tương thích

Nếu subtotal và minimumOrder khác currency, ví dụ phải từ chối bằng exception rõ ràng hoặc áp dụng quy tắc chuyển đổi đã được mô hình hóa. Không nên âm thầm so sánh hai số tiền chỉ dựa trên amount.

### 9.3. Kiểm tra dữ liệu phụ thuộc bất thường

Nếu PromotionUsageLookup trả về số âm, ví dụ ném IllegalStateException. Đây là dữ liệu vi phạm hợp đồng của phụ thuộc, không phải kết luận khách đủ hoặc không đủ điều kiện.

Cũng cần quyết định cách xử lý khi lookup ném lỗi kết nối:

- Để lỗi truyền lên application layer.
- Chuyển thành một lỗi miền kỹ thuật có ngữ nghĩa rõ.
- Thử lại ở application layer nếu lỗi có thể phục hồi.

Không nên biến timeout thành số lần sử dụng bằng 0, vì điều đó có thể cho phép khuyến mãi sai chính sách.

### 9.4. Phân biệt kết quả nghiệp vụ và lỗi kỹ thuật

| Tình huống | Loại kết quả |
|---|---|
| Khách không đủ hạng | Từ chối nghiệp vụ |
| Đơn chưa đạt mức tối thiểu | Từ chối nghiệp vụ |
| Chương trình đã hết hạn | Từ chối nghiệp vụ |
| Database không truy cập được | Lỗi kỹ thuật |
| Dữ liệu lookup âm | Vi phạm hợp đồng phụ thuộc |
| Định dạng request sai | Lỗi validation đầu vào |

Test cần xác nhận các trường hợp này không bị gộp thành một kết quả chung gây hiểu sai cho người gọi.

## 10. Phân biệt Unit Test, Integration Test và Contract Test

### 10.1. Unit Test kiểm tra quy tắc của Domain Service

Unit test nên chạy nhanh, không cần database hoặc mạng. Nó dùng dữ liệu miền thật và fake/stub cho những phụ thuộc cần kiểm soát.

Các nội dung phù hợp:

- Điều kiện đủ và không đủ.
- Ngưỡng và thời điểm biên.
- Thứ tự ưu tiên lý do từ chối.
- Giá trị trả về.
- Exception khi đầu vào hoặc phụ thuộc vi phạm hợp đồng.
- Tương tác cần thiết với abstraction.

### 10.2. Integration Test kiểm tra adapter và hạ tầng

Integration test xác nhận triển khai thật của PromotionUsageLookup đọc dữ liệu đúng từ database hoặc hệ thống bên ngoài.

Ví dụ:

- Query đếm số lần sử dụng có lọc đúng customer và promotion.
- Bản ghi đã hủy hoặc hoàn tiền được tính theo chính sách.
- Transaction và isolation level phù hợp.
- Mapping database không làm sai ý nghĩa dữ liệu.

Không cần lặp lại toàn bộ bảng quyết định của Domain Service trong integration test. Tập trung kiểm tra hợp đồng giữa các thành phần thật.

### 10.3. Contract Test kiểm tra giao kèo giữa các hệ thống

Nếu lookup gọi một API do hệ thống khác cung cấp, contract test có thể xác nhận request và response tuân theo giao kèo đã thống nhất.

Nó giúp phát hiện thay đổi schema hoặc ý nghĩa trường dữ liệu mà unit test với fake không thể phát hiện.

### 10.4. Không dùng unit test để giả lập toàn bộ hệ thống

Nếu test phải khởi động nhiều service, database, broker và container chỉ để kiểm tra một phép quyết định miền, ranh giới giữa domain và infrastructure có thể chưa rõ.

Ngược lại, nếu không có integration test nào cho adapter, fake có thể che giấu lỗi query hoặc mapping. Hãy chọn loại test theo rủi ro cần kiểm tra.

## 11. Tách logic quyết định khỏi việc thực thi tác động

Domain Service thường nên trả về kết quả nghiệp vụ. Application Service chịu trách nhiệm thực hiện các tác động như lưu dữ liệu, phát message hoặc gọi cổng thanh toán.

Ví dụ:

~~~java
public class ApplyPromotionUseCase {

    private final CustomerRepository customers;
    private final OrderRepository orders;
    private final PromotionRepository promotions;
    private final PromotionEligibilityService eligibilityService;
    private final OrderDiscountPolicy discountPolicy;
    private final UnitOfWork unitOfWork;

    public ApplyPromotionUseCase(
        CustomerRepository customers,
        OrderRepository orders,
        PromotionRepository promotions,
        PromotionEligibilityService eligibilityService,
        OrderDiscountPolicy discountPolicy,
        UnitOfWork unitOfWork
    ) {
        this.customers = customers;
        this.orders = orders;
        this.promotions = promotions;
        this.eligibilityService = eligibilityService;
        this.discountPolicy = discountPolicy;
        this.unitOfWork = unitOfWork;
    }

    public void execute(
        CustomerId customerId,
        OrderId orderId,
        PromotionId promotionId
    ) {
        Customer customer = customers.get(customerId);
        Order order = orders.get(orderId);
        Promotion promotion = promotions.get(promotionId);

        PromotionDecision decision =
            eligibilityService.evaluate(
                promotion,
                customer,
                order.subtotal()
            );

        if (!decision.eligible()) {
            throw new PromotionNotEligibleException(
                decision.rejectionReason()
            );
        }

        order.applyDiscount(
            discountPolicy.discountFor(promotion, order.subtotal())
        );

        orders.save(order);
        unitOfWork.commit();
    }
}
~~~

Ví dụ chỉ minh họa ranh giới trách nhiệm; chi tiết tính chiết khấu và ghi nhận lượt sử dụng cần theo chính sách thực tế.

Unit test cho PromotionEligibilityService không cần kiểm tra việc lưu Order. Use case có test riêng để xác nhận nó tải đúng dữ liệu, gọi dịch vụ miền, áp dụng kết quả và lưu Aggregate.

Việc tách quyết định khỏi tác động giúp test tập trung và tránh buộc Domain Service phụ thuộc vào transaction, ORM hoặc framework.

## 12. Cẩn thận với kiểm tra hạn mức khi có đồng thời

Một điểm quan trọng: PromotionEligibilityService ở ví dụ trên chỉ đọc số lần sử dụng đã hoàn tất. Hai request đồng thời có thể cùng đọc số lần bằng 0 và cả hai đều được đánh giá đủ điều kiện dù giới hạn là 1.

Do đó, quyết định eligibility chưa phải là cam kết giữ lượt khuyến mãi. Nếu doanh nghiệp cần giới hạn cứng, cần một hành vi đặt chỗ hoặc tiêu thụ lượt được bảo vệ nguyên tử tại Aggregate hoặc cơ sở dữ liệu.

Ví dụ luồng có thể là:

1. Domain Service đánh giá điều kiện ban đầu.
2. Application Service yêu cầu tạo một PromotionRedemption hoặc giữ lượt.
3. Aggregate hoặc database kiểm tra giới hạn đồng thời.
4. Chỉ một request được giữ lượt cuối cùng.
5. Request còn lại nhận kết quả từ chối hoặc xung đột có thể xử lý lại.

Unit test của Domain Service không chứng minh cơ chế concurrency đó an toàn. Cần integration test với database thật hoặc test đồng thời phù hợp để xác minh invariant giới hạn sử dụng.

Điều này cũng nhấn mạnh việc đặt đúng trách nhiệm: Domain Service đánh giá quy tắc dựa trên dữ liệu; thao tác giữ tài nguyên có giới hạn cần có ranh giới nhất quán riêng.

## 13. Những sai lầm thường gặp khi kiểm thử Domain Service

### Dùng thời gian hệ thống trực tiếp

Test có thể chạy hôm nay nhưng thất bại ngày mai. Hãy tiêm Clock và cố định thời gian trong test.

### Gọi database thật trong unit test

Unit test trở nên chậm và phụ thuộc dữ liệu môi trường. Hãy thay thế read port bằng fake; kiểm tra adapter thật ở integration test.

### Mock cả Entity và Value Object

Test chỉ phản ánh hành vi của mock, không kiểm tra invariant của mô hình thật. Hãy dùng object miền thật với fixture rõ ràng.

### Chỉ kiểm tra nhánh thành công

Các lỗi thường nằm ở thời điểm biên, ngưỡng tiền, dữ liệu thiếu và giới hạn sử dụng. Hãy chuyển bảng quyết định thành bộ test.

### Kiểm tra quá nhiều chi tiết nội bộ

Test phụ thuộc vào số lần gọi private helper hoặc thứ tự triển khai có thể thất bại khi refactor dù nghiệp vụ không đổi. Chỉ xác nhận tương tác là một phần của hợp đồng.

### Nuốt lỗi phụ thuộc

Trả về “không đủ điều kiện” khi database timeout có thể khiến người dùng nhận thông báo sai và che giấu sự cố. Phân biệt từ chối nghiệp vụ với lỗi kỹ thuật.

### Fake triển khai lại chính quy tắc cần kiểm thử

Nếu fake tự quyết định khách đủ điều kiện, test không còn kiểm tra Domain Service. Fake chỉ nên cung cấp dữ liệu hoặc mô phỏng khả năng bên ngoài.

### Để Domain Service thực hiện mọi tác động

Nếu dịch vụ miền vừa quyết định, vừa lưu dữ liệu, gửi email và gọi HTTP, test sẽ khó cô lập. Tách quyết định miền khỏi điều phối use case và adapter.

### Nhầm unit test với kiểm thử concurrency

Một fake trả về số lượt cố định không thể chứng minh giới hạn sử dụng được bảo vệ khi nhiều request đồng thời. Cần test tích hợp cho transaction và constraint.

## 14. Mẫu tổ chức test và checklist

Một cấu trúc test dễ đọc có thể nhóm theo hành vi:

~~~text
PromotionEligibilityServiceTest
    shouldApproveWhenAllConditionsAreMet
    shouldRejectBeforeStart
    shouldRejectAtEndInstant
    shouldRejectIneligibleTier
    shouldRejectBelowMinimum
    shouldRejectWhenUsageLimitReached
    shouldQueryUsageWithCorrectIdentifiers
    shouldNotQueryUsageWhenEarlierRuleRejects
    shouldPropagateUsageLookupFailure
~~~

Checklist trước khi hoàn thành:

- Hợp đồng đầu vào và kết quả của Domain Service đã rõ.
- Các quy tắc được viết thành bảng quyết định hoặc ví dụ Given-When-Then.
- Dữ liệu test được tạo rõ ràng và có ý nghĩa nghiệp vụ.
- Value Object và Entity thật được dùng khi phù hợp.
- Clock được kiểm soát nếu quy tắc phụ thuộc thời gian.
- Repository hoặc nguồn dữ liệu được thay bằng fake/stub trong unit test.
- Test kiểm tra ngưỡng, thời điểm biên và các nhánh từ chối.
- Lỗi kỹ thuật được phân biệt với kết quả nghiệp vụ.
- Test không phụ thuộc thứ tự triển khai nội bộ không cần thiết.
- Integration test xác minh adapter và truy vấn thật.
- Concurrency được kiểm tra riêng nếu invariant có giới hạn dùng chung.
- Test có thể chạy lặp lại với cùng kết quả.

## 15. Bài tập thực hành: kiểm thử chính sách phí giao hàng

Một nền tảng thương mại điện tử có Domain Service đánh giá phí giao hàng dựa trên:

- Khu vực giao hàng.
- Khối lượng đơn.
- Loại dịch vụ giao hàng.
- Mức miễn phí theo giá trị đơn.
- Thời gian nhận đơn.

Chính sách giả định:

- Đơn vượt mức giá trị quy định được miễn phí giao hàng tiêu chuẩn.
- Khu vực ngoài vùng phục vụ bị từ chối.
- Khối lượng vượt giới hạn của dịch vụ tiêu chuẩn phải chọn dịch vụ khác.
- Mức phí thay đổi theo khu vực và loại dịch vụ.
- Mốc thời gian chốt đơn ảnh hưởng đến ngày giao dự kiến.

Hãy thực hiện:

1. Xác định hành vi nào thuộc Domain Service.
2. Xác định dữ liệu nào là Value Object và dữ liệu nào cần tra cứu.
3. Thiết kế interface cho bảng giá hoặc chính sách vùng giao hàng.
4. Cố định Clock để kiểm thử thời điểm chốt đơn.
5. Tạo fake cho bảng giá với các khu vực và mức phí định trước.
6. Viết test cho đơn miễn phí, ngoài vùng phục vụ, vượt khối lượng và đúng ngưỡng.
7. Tách integration test để xác minh adapter đọc bảng giá từ nguồn thật.
8. Xác định trường hợp nào cần kiểm thử concurrency, nếu có giới hạn năng lực giao hàng theo khung giờ.

### 15.1. Gợi ý tổ chức dữ liệu

| Dữ liệu | Cách kiểm soát trong unit test |
|---|---|
| Khu vực giao hàng | Tạo Value Object với mã khu vực cố định |
| Khối lượng | Tạo Weight có đơn vị đo rõ |
| Giá trị đơn | Tạo Money với currency xác định |
| Loại dịch vụ | Dùng enum hoặc Value Object |
| Bảng giá | Fake trả về mức phí định trước |
| Thời gian nhận đơn | Clock.fixed |
| Kết quả | So sánh phí, ngày giao hoặc lý do từ chối |

Mục tiêu là mỗi test làm rõ một quy tắc. Không cần dựng database hoặc gọi nhà vận chuyển thật để kiểm tra phép quyết định miền.

## Kết luận

Kiểm thử Domain Service hiệu quả bắt đầu từ việc xác định rõ hành vi và hợp đồng nghiệp vụ. Dữ liệu đầu vào nên là các đối tượng miền thật; phụ thuộc bên ngoài được thay bằng fake hoặc stub có thể điều khiển; thời gian được cố định bằng Clock; và các trường hợp biên được lấy trực tiếp từ bảng quyết định.

Unit test giúp xác nhận quy tắc miền nhanh và ổn định. Integration test kiểm tra adapter, truy vấn và transaction thật. Những invariant có nguy cơ bị vi phạm do request đồng thời cần kiểm tra ở cấp lưu trữ hoặc tích hợp. Khi phân chia đúng các trách nhiệm này, Domain Service giữ được tính độc lập, dễ hiểu và có thể kiểm chứng mà không bị gắn chặt vào hạ tầng.

