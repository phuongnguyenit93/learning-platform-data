# Phụ thuộc rõ ràng thay vì truy cập trạng thái toàn cục

Một chức năng kiểm tra mã giảm giá chạy đúng trên máy của lập trình viên nhưng đôi khi thất bại trong bộ kiểm thử. Khi chạy riêng, bài kiểm thử thành công; khi chạy cùng các bài khác, kết quả thay đổi. Kiểm tra kỹ mới phát hiện chức năng đang đọc repository từ một biến `static` có thể bị thay thế và lấy thời gian trực tiếp từ đồng hồ hệ thống. Kết quả không chỉ phụ thuộc vào tham số truyền vào mà còn phụ thuộc vào **trạng thái nằm ngoài phạm vi nhìn thấy của người gọi**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Bài thuộc chương **Cấu trúc và phụ thuộc** này tập trung vào nguyên tắc: **một thành phần nên thể hiện rõ những gì nó cần để hoạt động, thay vì âm thầm tìm hoặc thay đổi trạng thái toàn cục**. Điều đó giúp người đọc hiểu luồng dữ liệu, người kiểm thử kiểm soát điều kiện và người bảo trì thay một thành phần mà ít ảnh hưởng đến nơi khác.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **phụ thuộc tường minh**, **phụ thuộc ẩn** và **trạng thái toàn cục có thể thay đổi**.
- Giải thích vì sao truy cập trạng thái toàn cục làm giảm tính dễ hiểu, khả năng kiểm thử và độ tin cậy khi chạy đồng thời.
- Viết mã Java truyền phụ thuộc qua constructor hoặc tham số, đặc biệt với repository, cấu hình và `Clock`.
- Nhận biết ranh giới khởi tạo, phạm vi sống và trách nhiệm sở hữu của phụ thuộc.
- Chọn cách cải tiến vừa đủ, tránh biến dependency injection thành nhiều lớp hoặc tham số không cần thiết.

## 1. Phụ thuộc là gì và khi nào nó bị che giấu?

Một **phụ thuộc (dependency)** là thứ mà một thành phần cần để thực hiện trách nhiệm: dữ liệu đầu vào, nguồn thời gian, nơi lưu trữ, ứng dụng khách HTTP, cấu hình chính sách hoặc dịch vụ khác. Phụ thuộc không nhất thiết là một đối tượng; nó có thể là một giá trị như múi giờ, giới hạn số lần thử lại hoặc mã tiền tệ.

So sánh:

~~~java
// Phụ thuộc nhìn thấy ngay trong chữ ký.
boolean isExpired(Instant expiresAt, Instant now) {
    return !now.isBefore(expiresAt);
}
~~~

~~~java
// Phụ thuộc vào thời gian hiện tại bị ẩn trong thân hàm.
boolean isExpired(Instant expiresAt) {
    return !Instant.now().isBefore(expiresAt);
}
~~~

Cả hai phiên bản đều có thể đúng về nghiệp vụ. Nhưng ở phiên bản thứ hai, kết quả thay đổi theo thời gian thực mà người gọi không kiểm soát được. Đây là **phụ thuộc ẩn vào đồng hồ**, dù bản thân `Instant.now()` không làm thay đổi một biến toàn cục.

Vấn đề trở nên rõ hơn khi thành phần truy cập một đối tượng dùng chung có thể bị sửa từ nhiều nơi:

~~~java
// Ví dụ minh họa cách tổ chức dễ gây phụ thuộc ẩn.
final class GlobalState {
    static CouponRepository couponRepository;
}

boolean canRedeem(String code) {
    Coupon coupon = GlobalState.couponRepository.findByCode(code)
        .orElse(null);
    return coupon != null
        && coupon.active()
        && Instant.now().isBefore(coupon.expiresAt());
}
~~~

Chữ ký `canRedeem(String code)` chỉ cho biết cần `code`, nhưng để kết quả đúng còn cần `GlobalState.couponRepository` đã được khởi tạo, kho dữ liệu ở trạng thái phù hợp và đồng hồ hệ thống ở thời điểm mong đợi. Một bài kiểm thử khác có thể thay repository toàn cục và vô tình ảnh hưởng đến bài hiện tại.

### Các khái niệm cần phân biệt

| Khái niệm | Cách nhận biết | Hệ quả thường gặp |
| --- | --- | --- |
| Phụ thuộc tường minh | Xuất hiện trong tham số, constructor hoặc hợp đồng của thành phần | Dễ biết cần cung cấp gì để tạo và dùng thành phần |
| Phụ thuộc ẩn | Thành phần tự truy xuất nguồn bên ngoài mà hợp đồng không nói rõ | Khó kiểm soát khi kiểm thử, khó nhận ra nguyên nhân thay đổi hành vi |
| Trạng thái toàn cục có thể thay đổi | Dữ liệu dùng chung, có thể đọc/ghi từ nhiều nơi, ví dụ trường `static` không được bảo vệ | Dễ có tác động ngoài ý muốn giữa các tính năng và luồng |
| Hằng số bất biến dùng chung | Giá trị không thay đổi sau khởi tạo, ví dụ `static final int MAX_RETRIES = 3` | Thường không gây vấn đề về chia sẻ trạng thái, nếu giá trị phù hợp ngữ cảnh |
| Hàm tĩnh thuần túy | Hàm `static` chỉ phụ thuộc tham số và không có tác dụng phụ | Thường dễ kiểm thử; bản thân `static` không phải lỗi thiết kế |

**Không phải mọi sử dụng `static` đều xấu.** Điều cần xem là thành phần có đọc hoặc sửa **trạng thái ẩn, có thể biến động**, và điều đó gây khó khăn gì khi hiểu, thay đổi hoặc kiểm chứng hành vi.

## 2. Những tác động thực tế của trạng thái toàn cục

Giả sử hệ thống có biến `GlobalState.couponRepository` như trên. Ba nơi khác nhau có thể sử dụng nó: bộ xử lý yêu cầu web, tác vụ nền và bộ kiểm thử. Nếu một nơi thay thế repository bằng phiên bản giả lập, nơi khác có thể nhận kết quả bất ngờ.

| Vấn đề | Cơ chế phát sinh | Biểu hiện |
| --- | --- | --- |
| Thứ tự chạy kiểm thử ảnh hưởng kết quả | Test A đổi biến toàn cục, test B đọc lại biến đã đổi | Test chạy riêng thành công nhưng chạy chung thất bại |
| Khó tái hiện lỗi | Kết quả phụ thuộc dữ liệu, thời gian và trạng thái ngoài tham số | Gửi cùng tham số nhưng không tái tạo được cùng kết quả |
| Tăng liên kết giữa các thành phần | Nhiều lớp truy cập trực tiếp một đối tượng dùng chung | Thay cách lưu trữ phải sửa ở nhiều nơi |
| Khó chạy nhiều cấu hình cùng lúc | Biến toàn cục chỉ giữ một giá trị tại một thời điểm | Hai tenant hoặc hai bài test cần cấu hình khác nhau |
| Rủi ro đồng thời | Nhiều luồng đọc/ghi trạng thái chia sẻ thiếu đồng bộ phù hợp | Race condition, mất cập nhật, dữ liệu không nhất quán |
| Vòng đời khó quản lý | Không rõ ai tạo, ai đóng và khi nào thay thế tài nguyên | Tài nguyên bị giữ quá lâu hoặc bị đóng khi vẫn đang dùng |

Với Java, một trường `static` có thể được nhiều luồng truy cập. Việc thêm `volatile` có thể hỗ trợ một số yêu cầu về khả năng nhìn thấy cập nhật, nhưng **không tự biến chuỗi thao tác đọc–kiểm tra–ghi thành nguyên tử** và không giải quyết việc nhiều nơi tùy ý đổi cùng trạng thái. Cần xem lại trách nhiệm sở hữu và mô hình đồng thời, thay vì chỉ bổ sung một từ khóa.

## 3. Ví dụ xuyên suốt: kiểm tra mã giảm giá

Giả sử yêu cầu nghiệp vụ đã được xác nhận như sau:

- Mã giảm giá tồn tại và đang ở trạng thái hoạt động.
- Mã chỉ hợp lệ **trước thời điểm hết hạn**; đúng thời điểm hết hạn đã không còn hợp lệ.
- Mã rỗng hoặc không tồn tại được xem là không hợp lệ.
- Chức năng chỉ kiểm tra điều kiện, không trừ số lần sử dụng hoặc ghi dữ liệu.

Ta cần hai loại dữ liệu bên ngoài: **kho mã giảm giá** và **thời gian hiện tại**. Hai nguồn này nên xuất hiện rõ ở ranh giới tạo đối tượng, thay vì được tự tìm trong biến toàn cục.

### Mô hình dữ liệu và hợp đồng kho lưu trữ

Các đoạn mã dưới đây minh họa Java 17 trở lên. Nếu đưa vào dự án, hãy đặt các kiểu `public` vào tệp Java phù hợp.

~~~java
import java.time.Instant;
import java.util.Objects;

public record Coupon(String code, boolean active, Instant expiresAt) {
    public Coupon {
        Objects.requireNonNull(code, "code");
        Objects.requireNonNull(expiresAt, "expiresAt");
    }
}
~~~

~~~java
import java.util.Optional;

public interface CouponRepository {
    Optional<Coupon> findByCode(String code);
}
~~~

`CouponRepository` diễn đạt đúng thứ mà logic cần: tìm mã giảm giá theo định danh. Nó chưa quy định dữ liệu đến từ JDBC, bộ nhớ hay một dịch vụ khác. Cách tổ chức này giúp thành phần kiểm tra mã tập trung vào chính sách nghiệp vụ.

### Truyền phụ thuộc qua constructor

~~~java
import java.time.Clock;
import java.util.Objects;

public final class CouponEligibility {
    private final CouponRepository repository;
    private final Clock clock;

    public CouponEligibility(CouponRepository repository, Clock clock) {
        this.repository = Objects.requireNonNull(repository, "repository");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean canRedeem(String code) {
        if (code == null || code.isBlank()) {
            return false;
        }

        return repository.findByCode(code)
            .filter(Coupon::active)
            .map(coupon -> clock.instant().isBefore(coupon.expiresAt()))
            .orElse(false);
    }
}
~~~

Thiết kế này diễn đạt rõ:

1. **Đầu vào nghiệp vụ của mỗi lần gọi** là `code`.
2. **Phụ thuộc dùng trong vòng đời đối tượng** là `CouponRepository` và `Clock`, được cung cấp khi tạo `CouponEligibility`.
3. **Quy tắc hết hạn** là `now < expiresAt`; khi `now == expiresAt`, kết quả là `false`.
4. **Không tồn tại hoặc không hoạt động** cũng cho kết quả `false`.
5. Đối tượng không thể tự đổi repository hay clock sau khi được tạo, vì các trường là `final` và không có setter.

Các trường `final` giúp cố định **tham chiếu** tới phụ thuộc. Chúng **không bảo đảm** đối tượng repository bên trong là bất biến, an toàn luồng hoặc không có tác dụng phụ. Một repository thực tế vẫn có thể truy cập cơ sở dữ liệu; đó là hành vi phù hợp với trách nhiệm của nó.

## 4. Tại sao truyền `Clock` giúp kiểm thử đáng tin cậy?

Lấy thời gian từ `Instant.now()` ngay trong logic khiến bài kiểm thử phụ thuộc vào đồng hồ thực. Nếu kiểm thử đúng lúc ranh giới hết hạn hoặc dùng `Thread.sleep()` để chờ, kết quả dễ bị ảnh hưởng bởi thời điểm chạy và tốc độ máy.

`Clock.fixed(...)` giúp tạo một thời điểm có thể lặp lại:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class CouponEligibilityTest {
    private static final Instant EXPIRES_AT =
        Instant.parse("2026-11-16T12:00:00Z");

    private CouponEligibility serviceAt(String currentTime, boolean active) {
        CouponRepository repository = code ->
            "SAVE10".equals(code)
                ? Optional.of(new Coupon("SAVE10", active, EXPIRES_AT))
                : Optional.empty();

        Clock fixedClock = Clock.fixed(
            Instant.parse(currentTime),
            ZoneOffset.UTC
        );
        return new CouponEligibility(repository, fixedClock);
    }

    @Test
    void acceptsActiveCouponBeforeExpiry() {
        CouponEligibility service =
            serviceAt("2026-11-16T11:59:59Z", true);
        assertTrue(service.canRedeem("SAVE10"));
    }

    @Test
    void rejectsCouponAtExactExpiry() {
        CouponEligibility service =
            serviceAt("2026-11-16T12:00:00Z", true);
        assertFalse(service.canRedeem("SAVE10"));
    }

    @Test
    void rejectsExpiredOrInactiveCoupon() {
        assertFalse(serviceAt("2026-11-16T12:00:01Z", true)
            .canRedeem("SAVE10"));
        assertFalse(serviceAt("2026-11-16T11:59:59Z", false)
            .canRedeem("SAVE10"));
    }

    @Test
    void rejectsUnknownAndBlankCode() {
        CouponEligibility service =
            serviceAt("2026-11-16T11:59:59Z", true);
        assertFalse(service.canRedeem("UNKNOWN"));
        assertFalse(service.canRedeem(" "));
        assertFalse(service.canRedeem(null));
    }
}
~~~

Bộ test xác nhận những mốc **trước, đúng và sau thời điểm hết hạn**, không cần chờ đồng hồ thực trôi. Repository giả lập ở đây là một lambda đơn giản, tạo đủ dữ liệu để kiểm tra chính sách. Nó không cần khởi động hệ thống hay ghi vào biến toàn cục.

**Giới hạn:** kiểm thử đơn vị này chưa chứng minh adapter lưu trữ thật truy vấn đúng dữ liệu. Nếu triển khai `CouponRepository` bằng JDBC hoặc HTTP, vẫn cần kiểm thử tích hợp cho adapter đó, bao gồm cách xử lý dữ liệu thiếu, lỗi kết nối và thời điểm hết hạn. Việc truyền phụ thuộc giúp tách trách nhiệm kiểm thử, không tự thay thế mọi mức kiểm thử.

## 5. Constructor, tham số và ranh giới khởi tạo

Phụ thuộc nên xuất hiện ở nơi phù hợp với **thời gian sử dụng** và **trách nhiệm sở hữu**:

| Cách truyền | Hợp với trường hợp nào? | Ví dụ |
| --- | --- | --- |
| **Tham số phương thức** | Giá trị thay đổi theo mỗi lời gọi | `canRedeem(String code)` |
| **Constructor injection** | Dịch vụ cần một cộng tác viên trong suốt vòng đời | `CouponEligibility(CouponRepository, Clock)` |
| **Factory hoặc điểm khởi tạo ứng dụng** | Cần tạo và nối các đối tượng, chọn adapter, cấu hình | Tạo repository thật, clock thật rồi truyền vào dịch vụ |
| **Đối tượng ngữ cảnh có phạm vi rõ** | Nhiều giá trị cùng thuộc một request/job cụ thể | `RequestContext` chứa tenant ID, correlation ID đã xác thực |

Ở điểm khởi tạo ứng dụng (thường gọi là **composition root**), mã có thể nối các thành phần:

~~~java
// Minh họa ở nơi đã tạo repository dùng cho môi trường chạy thực tế.
CouponRepository repository = createCouponRepository();
Clock clock = Clock.systemUTC();
CouponEligibility eligibility = new CouponEligibility(repository, clock);
~~~

Trong đoạn phác thảo, `createCouponRepository()` biểu thị công đoạn tạo adapter thật, không phải hàm đã được định nghĩa trong ví dụ. Điểm quan trọng là **một nơi biết cách tạo đối tượng**, còn thành phần nghiệp vụ chỉ biết **hợp đồng của phụ thuộc**.

Không bắt buộc dùng Spring hoặc một DI framework để áp dụng cách thiết kế này. Constructor và tham số Java thông thường đã đủ cho nhiều chương trình. Framework có thể giúp tự động lắp ghép và quản lý vòng đời khi ứng dụng lớn, nhưng nó không thay thế việc thiết kế hợp đồng và phạm vi sống rõ ràng.

### Đừng biến tham số thành một “túi toàn cục” mới

Một cách làm kém là truyền một đối tượng `ApplicationContext` cực lớn cho mọi lớp:

~~~java
class CouponEligibility {
    private final ApplicationContext context;

    CouponEligibility(ApplicationContext context) {
        this.context = context;
    }

    // Bên trong tự lấy repository, clock, config và bất kỳ dịch vụ nào khác.
}
~~~

Mặc dù `context` được truyền qua constructor, thành phần vẫn có thể tự do lấy **mọi** phụ thuộc từ bên trong. Người đọc khó biết nó cần thứ gì thực sự; mỗi lớp lại bị buộc vào một container rộng. Kiểu thiết kế này thường được gọi là **service locator** hoặc biến thể của nó.

Hãy truyền **đúng các hợp đồng cần thiết**. Nếu constructor cần tới mười dịch vụ khác nhau, hãy xem lớp có đang ôm quá nhiều trách nhiệm không. Không nên tự động giấu tất cả vào một đối tượng context chỉ để rút ngắn chữ ký.

## 6. Phụ thuộc vào hợp đồng, không phụ thuộc cách tạo

Trong ví dụ trên, `CouponEligibility` cần `CouponRepository` chứ không cần biết `JdbcCouponRepository` hay `InMemoryCouponRepository` được tạo ra thế nào. Đây là cách hạn chế liên kết giữa logic nghiệp vụ và chi tiết hạ tầng.

~~~text
      Điểm khởi tạo ứng dụng
                |
        Tạo adapter cụ thể
                |
                v
    +-------------------------+
    | CouponEligibility       |
    | - CouponRepository      | ---> hợp đồng tra cứu
    | - Clock                 | ---> nguồn thời gian
    +-------------------------+
                |
                v
       Quy tắc hợp lệ coupon
~~~

Thay một repository JDBC bằng một adapter khác không yêu cầu thay đổi quy tắc hết hạn nếu **cả hai triển khai tuân thủ cùng hợp đồng**. Đây là một lợi ích của tách phụ thuộc.

Tuy nhiên, không phải mọi đối tượng phải có interface. Một đối tượng giá trị đơn giản, một lớp thuần với hành vi ổn định hoặc một utility không có phụ thuộc I/O có thể được gọi trực tiếp. Tạo interface chỉ để luôn có “một interface cho một class” thường làm tăng mã mà không tăng khả năng thay đổi thực tế.

## 7. Giới hạn phạm vi sống và đồng thời

Ngay cả khi phụ thuộc được truyền rõ ràng, **vòng đời và phạm vi sử dụng** vẫn phải được xác định.

Ví dụ:

- `Clock.systemUTC()` có thể được dùng chung bởi nhiều dịch vụ nếu cách dùng đáp ứng yêu cầu.
- Một repository dùng kết nối hoặc transaction có thể cần tài nguyên riêng cho mỗi thao tác; không nên mặc định một kết nối JDBC có thể được chia sẻ tùy ý giữa nhiều luồng.
- Dữ liệu của một yêu cầu cụ thể, như `tenantId` hoặc quyền người dùng, cần được ràng buộc vào đúng request/operation. Đặt chúng trong biến `static` dùng chung có thể dẫn tới đọc nhầm ngữ cảnh của người khác.
- Nếu dùng `ThreadLocal` hoặc request context do framework quản lý, phải hiểu cách lan truyền và dọn dẹp trong luồng xử lý bất đồng bộ; chúng không biến phụ thuộc thành vô hình một cách an toàn.

| Câu hỏi thiết kế | Ví dụ cần làm rõ |
| --- | --- |
| Ai tạo phụ thuộc? | Điểm khởi tạo ứng dụng hay một factory cho từng request? |
| Ai sở hữu tài nguyên và đóng nó? | Ai chịu trách nhiệm đóng pool, client HTTP hoặc kết nối? |
| Có thể dùng chung giữa luồng không? | Repository, cache và đối tượng có trạng thái có thread-safe không? |
| Phạm vi dữ liệu là gì? | Cấu hình toàn ứng dụng, tenant hay từng request? |
| Có thể thay trong test không? | Có truyền được fake repository và fixed clock không? |

**Truyền phụ thuộc tường minh giải quyết việc nhìn thấy mối quan hệ; bảo đảm an toàn đồng thời và quản lý tài nguyên còn cần quyết định thiết kế riêng.**

## 8. Khi nào không cần dependency injection?

Một hàm không phụ thuộc I/O, thời gian hoặc trạng thái dùng chung thường có thể giữ rất đơn giản:

~~~java
public final class Percentage {
    private Percentage() {
    }

    public static long calculate(long total, int rate) {
        if (total < 0 || rate < 0 || rate > 100) {
            throw new IllegalArgumentException("Invalid total or rate");
        }
        return Math.multiplyExact(total, rate) / 100;
    }
}
~~~

Hàm này chỉ cần các tham số và không truy cập trạng thái bên ngoài. Nó có thể được kiểm thử bằng đầu vào/đầu ra mà không tạo đối tượng hoặc mock. `Math.multiplyExact` giúp báo lỗi nếu phép nhân vượt miền `long`; chính sách xử lý tràn số cần phù hợp với yêu cầu nghiệp vụ.

Không có lợi ích rõ ràng nếu tạo `PercentageCalculatorInterface`, một factory và container chỉ để gọi hàm trên. Hãy ưu tiên phương án **đơn giản nhất vẫn diễn đạt đầy đủ phụ thuộc và giữ được hành vi cần kiểm chứng**.

Các hằng số bất biến như `static final int SECONDS_PER_MINUTE = 60` cũng thường hợp lý. Vấn đề trọng tâm là **trạng thái có thể thay đổi, phụ thuộc khó kiểm soát hoặc trách nhiệm không rõ**, chứ không phải sự xuất hiện của từ khóa `static`.

## 9. Chuyển dần mã cũ đang dùng trạng thái toàn cục

Một dự án lớn có thể đã sử dụng một singleton hoặc các biến `static` trong nhiều năm. Không cần thay toàn bộ trong một lần nếu rủi ro cao. Có thể tiến hành theo từng bước:

1. **Xác định phụ thuộc ẩn:** đọc thân phương thức để tìm nơi gọi `getInstance()`, đọc biến `static` có thể sửa, tự khởi tạo client, lấy `Instant.now()` hoặc tự đọc cấu hình hệ thống.
2. **Mô tả hành vi hiện có và quy tắc nghiệp vụ:** xác định đầu vào, kết quả, lỗi và tác dụng phụ cần giữ. Bổ sung test ở những nhánh có rủi ro.
3. **Đưa một phụ thuộc ra ranh giới:** ví dụ bổ sung tham số `Clock` hoặc constructor nhận `CouponRepository`.
4. **Cập nhật nơi tạo đối tượng:** chọn adapter và nối phụ thuộc tại lớp khởi tạo phù hợp, tránh để mỗi nơi gọi tự tạo một cách.
5. **Viết test độc lập:** dùng fake/stub và dữ liệu cố định, xác minh có thể chạy không phụ thuộc thứ tự các test khác.
6. **Loại bỏ đường truy cập toàn cục cũ:** khi mọi nơi đã chuyển và kiểm thử đạt, xóa đường dùng chung không còn cần thiết.
7. **Xem lại vòng đời và triển khai:** bảo đảm tài nguyên được tạo, chia sẻ và đóng đúng phạm vi; kiểm tra luồng tích hợp thật.

### Một ví dụ chuyển đổi an toàn

Giả sử lớp cũ đọc trực tiếp `System.getenv("COUPON_ENABLED")` ở nhiều phương thức. Nếu chính sách chỉ cần biết một cờ bật/tắt tại thời điểm tạo dịch vụ, có thể dùng:

~~~java
public final class CouponFeature {
    private final boolean enabled;

    public CouponFeature(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
~~~

Giá trị `enabled` được đọc từ môi trường ở nơi khởi tạo và truyền vào. Test có thể tạo `new CouponFeature(true)` hoặc `new CouponFeature(false)` mà không phải chỉnh biến môi trường toàn tiến trình.

Nhưng nếu sản phẩm yêu cầu **thay đổi cờ động mà không khởi động lại**, chụp giá trị một lần trong constructor sẽ **đổi hành vi**. Khi đó phụ thuộc tường minh nên là một `FeatureFlagProvider` có hợp đồng rõ về thời điểm đọc và tính nhất quán của cập nhật. Cách truyền phụ thuộc phải bám vào **yêu cầu thực tế**, không cố ép mọi thứ thành giá trị bất biến.

## 10. Cách đánh giá sau khi cải tiến

Không nên đánh giá kết quả chỉ bằng số lớp sử dụng injection. Hãy kiểm tra tác động đến hành vi và khả năng bảo trì:

| Tiêu chí | Trước: trạng thái toàn cục | Sau: phụ thuộc tường minh |
| --- | --- | --- |
| Đọc chữ ký/constructor | Khó biết dùng repository và đồng hồ nào | Nhìn thấy `CouponRepository` và `Clock` |
| Test điều kiện thời gian | Phụ thuộc thời gian thật hoặc phải thay global | Dùng `Clock.fixed` |
| Chạy test độc lập | Có thể phụ thuộc thứ tự nếu test sửa trạng thái chung | Mỗi test tạo dịch vụ và fake riêng |
| Thay adapter lưu trữ | Nhiều nơi có thể truy cập trực tiếp cách tạo | Chọn adapter tại nơi nối các thành phần |
| Truy vết lỗi | Phải dò nơi sửa biến toàn cục | Có thể lần từ nơi tạo dịch vụ và phụ thuộc truyền vào |
| Phạm vi tài nguyên | Dễ mơ hồ nếu không ai chịu trách nhiệm | Có nơi rõ ràng để quy định tạo và đóng tài nguyên |

Đây là **kỳ vọng thiết kế**, không phải bảo đảm tự động. Nếu repository bên trong vẫn có trạng thái chia sẻ không an toàn, hoặc nơi khởi tạo truyền nhầm adapter, lỗi vẫn có thể xảy ra. Cần kiểm thử và review các đường đi quan trọng.

Khi code review, có thể đặt những câu hỏi:

- Thành phần đang cần những phụ thuộc nào? Người đọc có nhận ra chúng từ chữ ký hoặc constructor không?
- Những giá trị như thời gian, cấu hình, quyền và tenant ID có thuộc đúng phạm vi sử dụng không?
- Test có phải can thiệp vào trạng thái của cả tiến trình để kiểm tra một chức năng nhỏ không?
- Một thay đổi ở adapter hạ tầng có buộc sửa quy tắc nghiệp vụ không?
- Ai chịu trách nhiệm tạo, dùng chung và giải phóng tài nguyên?
- Việc tạo thêm interface hoặc factory có thật sự giải quyết một biến động cần hỗ trợ không?

## 11. Bài tập thực hành

Cho đoạn mã sau trong hệ thống xử lý đơn hàng:

~~~java
final class AppGlobals {
    static int maxRetries = 3;
    static PaymentGateway gateway;
}

class PaymentService {
    boolean charge(String orderId) {
        for (int attempt = 0; attempt < AppGlobals.maxRetries; attempt++) {
            if (AppGlobals.gateway.charge(orderId)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Giả sử `PaymentGateway` là một giao diện có phương thức `boolean charge(String orderId)`. Đoạn mã nhằm minh họa phụ thuộc và chưa bao gồm chính sách an toàn xử lý thanh toán thực tế.

**Câu hỏi A.** Những phụ thuộc nào bị ẩn trong `PaymentService`? Điều gì xảy ra nếu một test thay `AppGlobals.gateway` trong lúc test khác chạy?

**Câu hỏi B.** Hãy thiết kế lại chữ ký constructor để `PaymentService` nhận đúng các phụ thuộc cần thiết.

**Câu hỏi C.** Vì sao chỉ thêm constructor injection vẫn chưa đủ để kết luận thao tác thanh toán đúng và an toàn khi retry?

### Gợi ý đáp án

**A.** Hai phụ thuộc ẩn là `maxRetries` và `gateway`. Nếu bị thay đổi trong lúc đang chạy, các lời gọi có thể dùng cấu hình hoặc đối tượng không mong đợi; test trở nên phụ thuộc thứ tự hoặc gây lỗi đồng thời.

**B.** Có thể dùng:

~~~java
class PaymentService {
    private final PaymentGateway gateway;
    private final int maxRetries;

    PaymentService(PaymentGateway gateway, int maxRetries) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
        if (maxRetries < 1) {
            throw new IllegalArgumentException("maxRetries must be positive");
        }
        this.maxRetries = maxRetries;
    }

    // Phương thức charge sẽ dùng hai trường của đối tượng này.
}
~~~

**C.** Một lời gọi charge có thể thành công ở phía đối tác nhưng phản hồi bị mất. Gọi lại thiếu cơ chế idempotency có thể thu tiền hai lần. Cần quy định rõ các loại lỗi được phép retry, timeout, khoảng chờ, giới hạn số lần, định danh yêu cầu duy nhất và cách đối chiếu trạng thái giao dịch. Dependency injection giúp kiểm soát `gateway` và `maxRetries`, nhưng không tự giải quyết quy tắc nghiệp vụ hoặc tính nhất quán giữa các hệ thống.

## Ghi nhớ

**Phụ thuộc tường minh giúp người đọc biết thành phần cần gì và ai cung cấp những điều kiện để nó hoạt động.** Khi thay việc truy cập trạng thái toàn cục bằng tham số, constructor và hợp đồng rõ ràng, mã thường dễ hiểu hơn, test có thể lặp lại và thay đổi hạ tầng có phạm vi ảnh hưởng nhỏ hơn.

Hãy ưu tiên **làm rõ nguồn dữ liệu, thời gian, cấu hình, quyền và vòng đời của tài nguyên**, đồng thời giữ thiết kế vừa đủ đơn giản. Việc bỏ trạng thái toàn cục là một phương tiện nâng chất lượng cấu trúc và phụ thuộc; kết quả cuối cùng vẫn cần được xác nhận bằng **hành vi đúng, kiểm thử phù hợp và quản lý đồng thời an toàn**.
