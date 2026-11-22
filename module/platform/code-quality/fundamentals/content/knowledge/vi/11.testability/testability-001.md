# Khả năng điều khiển đầu vào và quan sát kết quả

Trong chương **Khả năng kiểm thử** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu hai điều kiện nền tảng để một đoạn mã dễ được kiểm tra: **có thể chủ động tạo ra tình huống cần kiểm thử** và **có thể biết điều gì thực sự đã xảy ra sau khi chạy**.

Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Khi người phát triển kiểm soát được đầu vào và quan sát được kết quả, họ có thể tái hiện lỗi, thử trường hợp biên, xác nhận quy tắc nghiệp vụ và tự tin hơn khi sửa mã. Nếu phải chờ đến đúng ngày, gọi một dịch vụ thật đang hoạt động, nhìn log bằng mắt hoặc đoán trạng thái bên trong, ngay cả một quy tắc đơn giản cũng trở nên tốn công kiểm thử.

> **Một thiết kế dễ kiểm thử cho phép ta chủ động đặt hệ thống vào trạng thái cần xét, thực hiện hành động và đối chiếu được hành vi quan sát với một kỳ vọng rõ ràng.**

Tính điều khiển được (*controllability*) và tính quan sát được (*observability*) là những **thuộc tính của thiết kế**. Chúng giúp hoạt động kiểm thử (*testing*) hiệu quả hơn, nhưng không tự bảo đảm phần mềm đúng trong mọi tình huống.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt khả năng **điều khiển đầu vào/điều kiện** với khả năng **quan sát kết quả/tác dụng phụ**.
2. Nhận ra những phụ thuộc làm kiểm thử khó kiểm soát: đồng hồ hệ thống, dữ liệu ngẫu nhiên, database, API bên ngoài, trạng thái dùng chung và tác vụ bất đồng bộ.
3. Thiết kế phương thức có hợp đồng đầu vào–đầu ra rõ ràng, đưa các phụ thuộc có thể thay đổi vào ranh giới phù hợp.
4. Sử dụng `Clock`, tham số, interface và bản triển khai giả lập trong Java để tạo bài kiểm thử lặp lại được.
5. Kiểm tra giá trị trả về, ngoại lệ, biến đổi trạng thái và sự kiện phát ra mà không phụ thuộc vào chi tiết cài đặt riêng tư.
6. Phân biệt phạm vi bảo đảm của unit test với integration test và kiểm thử đầu cuối.
7. Đánh giá các đánh đổi như mock quá nhiều, mở API chỉ vì test, ghi log quá mức và thiết kế quá nhiều lớp trừu tượng.

## 2. Hai câu hỏi quyết định khả năng kiểm thử

Mọi bài kiểm thử đều cần ít nhất ba phần:

~~~text
Điều kiện ban đầu + hành động
                |
                v
       Hành vi thực tế
                |
                v
        Kết quả quan sát
                |
                v
       So với kỳ vọng
                |
                v
         PASS / FAIL
~~~

Nếu không chủ động tạo được điều kiện ban đầu, ta khó bảo đảm bài test đang kiểm tra đúng tình huống. Nếu không quan sát được điều gì đã xảy ra, bài test không có đủ dữ liệu để kết luận hành vi đúng hay sai.

### 2.1. Khả năng điều khiển (*controllability*)

**Khả năng điều khiển** là mức độ bài kiểm thử có thể thiết lập những yếu tố tác động đến hành vi của thành phần đang kiểm tra, ví dụ:

- Giá trị đầu vào, dữ liệu không hợp lệ, các giá trị ở ranh giới.
- Thời gian và múi giờ hệ thống dùng để quyết định hết hạn.
- Kết quả từ API, repository, hệ thống gửi thông báo.
- Chuỗi số ngẫu nhiên hoặc mã định danh được sinh.
- Trạng thái trước một thao tác và sự kiện thay đổi trạng thái.
- Tình huống timeout, lỗi kết nối hoặc phản hồi không mong muốn.

Không phải lúc nào cũng cần kiểm soát **toàn bộ hệ thống thực tế**. Với một unit test, thường chỉ cần kiểm soát những phụ thuộc tác động đến quy tắc đang xét. Với integration test, ta cần giữ một số thành phần thật và tổ chức dữ liệu/môi trường để thiết lập được tình huống mong muốn.

### 2.2. Khả năng quan sát (*observability*)

**Khả năng quan sát** là mức độ kết quả hoặc tác động của một thao tác có thể được kiểm tra bằng những dấu hiệu có ý nghĩa:

- Giá trị trả về và loại kết quả thành công/thất bại.
- Ngoại lệ được ném ra theo hợp đồng.
- Trạng thái đã lưu hoặc trạng thái của đối tượng sau thao tác.
- Sự kiện hoặc lệnh gửi đến một cổng giao tiếp bên ngoài.
- Phản hồi HTTP, dữ liệu được ghi, kết quả của một tác vụ hoàn thành.
- Những dấu vết cần thiết để tái hiện và chẩn đoán khi có lỗi.

Không nên đồng nhất khả năng quan sát trong kiểm thử với việc **ghi thật nhiều log**. Log và metrics có giá trị trong vận hành, nhưng một bài unit test kiểm tra được giá trị trả về và sự kiện ở ranh giới nghiệp vụ thường rõ ràng, nhanh và ít phụ thuộc vào định dạng log hơn.

### 2.3. Phân biệt bằng ví dụ

Giả sử yêu cầu là “mã giảm giá còn hiệu lực trong đúng ngày hết hạn”.

| Khía cạnh | Thiết kế khó kiểm thử | Thiết kế dễ kiểm thử |
| --- | --- | --- |
| Điều khiển thời gian | Hàm gọi trực tiếp `LocalDate.now()`, phải chờ ngày thật hoặc đổi đồng hồ máy. | Hàm nhận ngày cần xét hoặc phụ thuộc vào `Clock` được truyền vào. |
| Điều khiển mã giảm giá | Luôn truy vấn database thật với dữ liệu khó tạo. | Quy tắc nhận đối tượng mã; riêng lớp tích hợp mới truy vấn database. |
| Quan sát quyết định | Hàm chỉ ghi log “đã xử lý”. | Trả về quyết định được định nghĩa rõ. |
| Quan sát tác dụng phụ | Gửi email/API thật, khó xác nhận và có thể gây tác động không mong muốn. | Tác dụng phụ đi qua một cổng có thể ghi nhận trong test. |
| Tái lập | Kết quả thay đổi theo ngày, mạng hoặc dữ liệu còn sót. | Cùng đầu vào và phụ thuộc đã kiểm soát sẽ cho kết quả kỳ vọng ổn định. |

## 3. Những yếu tố phải điều khiển thường nằm ngoài tham số

Một phương thức nhận hai tham số có thể trông đơn giản nhưng vẫn có nhiều **đầu vào ẩn**:

~~~java
boolean isCouponValid(Coupon coupon, long subtotalCents) {
    return coupon.enabled()
            && subtotalCents >= coupon.minimumCents()
            && !LocalDate.now().isAfter(coupon.expiresOn());
}
~~~

Bên cạnh `coupon` và `subtotalCents`, kết quả còn phụ thuộc vào thời gian hiện tại và múi giờ mặc định của hệ thống. Những phụ thuộc không xuất hiện trong chữ ký hoặc hợp đồng rất dễ bị bỏ qua.

### 3.1. Bảng các nguồn biến động

| Nguồn phụ thuộc | Vấn đề thường gặp | Điểm điều khiển có thể thiết kế |
| --- | --- | --- |
| Đồng hồ và múi giờ | Test hôm nay đỗ, ngày khác trượt. | Truyền `LocalDate` hoặc `Clock`; nêu múi giờ nghiệp vụ. |
| Ngẫu nhiên | Không tái lập được trường hợp lỗi. | Truyền bộ sinh có seed cố định hoặc nguồn cung cấp giá trị phù hợp. |
| Database | Test cần bản ghi tồn tại từ trước; test này ảnh hưởng test khác. | Khởi tạo dữ liệu riêng, giao dịch test, repository fake hoặc database test độc lập. |
| HTTP/API bên ngoài | Timeout, hạn mức gọi, phản hồi thay đổi hoặc cần credential. | Cổng giao tiếp rõ, stub phản hồi, test tích hợp riêng với dịch vụ thật. |
| File, cấu hình, biến môi trường | Kết quả khác giữa laptop và CI. | Truyền cấu hình/đường dẫn và tạo dữ liệu test tạm theo vòng đời. |
| Trạng thái dùng chung | Thứ tự chạy test quyết định kết quả. | Cô lập đối tượng, reset fixture, hạn chế field `static` mutable. |
| Bất đồng bộ | Test phụ thuộc vào `sleep` và lịch chạy thread. | Quan sát trạng thái hoàn tất, inject executor khi phù hợp, dùng cơ chế đồng bộ có điều kiện. |
| Hệ thống sự kiện | Không biết một thông điệp đã phát hay chưa. | Cổng xuất sự kiện có thể ghi lại; kiểm thử tích hợp xác minh broker thật. |

Mục tiêu không phải thay mọi thư viện thành interface. Một phương thức chỉ cần một ngày để so sánh có thể nhận thẳng `LocalDate`, đơn giản hơn việc tạo một hệ thống quản lý đồng hồ tùy biến.

## 4. Ví dụ Java: đánh giá mã giảm giá theo ngày và ghi nhận quyết định

Giả sử yêu cầu nghiệp vụ của cửa hàng:

- Mã giảm giá được chấp nhận khi **tồn tại**, **đang bật**, **giá trị đơn đạt mức tối thiểu** và **ngày hiện tại không sau ngày hết hạn**.
- Mã vẫn hợp lệ đến hết **ngày hết hạn theo múi giờ nghiệp vụ**.
- Mỗi lần đánh giá **một mã với số tiền đầu vào hợp lệ** phải trả về một kết quả và gửi **một bản ghi đánh giá** đến cổng audit.
- Tổng tiền âm là dữ liệu sai và bị từ chối bằng ngoại lệ **trước khi phát bản ghi đánh giá**.

Ta dùng Java 17+ với `record`, `LocalDate` và `Clock` để minh họa.

### 4.1. Cách viết khó điều khiển và khó quan sát

~~~java
// Mã minh họa ý tưởng: repository và auditClient là phụ thuộc bên ngoài.
boolean apply(String couponCode, long subtotalCents) {
    Coupon coupon = repository.find(couponCode);
    boolean accepted = coupon != null
            && coupon.enabled()
            && subtotalCents >= coupon.minimumCents()
            && !LocalDate.now().isAfter(coupon.expiresOn());

    auditClient.send("evaluated");  // Không thể thấy nội dung quyết định
    return accepted;
}
~~~

Có nhiều vấn đề đối với việc kiểm thử:

1. Ngày được đọc từ đồng hồ và múi giờ mặc định của máy.
2. Repository ngoài cần dữ liệu phù hợp, khiến test quy tắc phụ thuộc database.
3. Cổng audit thật gây tác dụng phụ trong quá trình thử.
4. Bản ghi `"evaluated"` thiếu kết quả cụ thể để xác minh quyết định.
5. Một ngoại lệ từ repository hoặc audit có thể làm người viết test khó phân biệt lỗi nghiệp vụ với lỗi hạ tầng.

Đây không phải lý do bỏ kiểm thử tích hợp. Vấn đề là **quy tắc nghiệp vụ đang bị trộn với các nguồn biến động và tác dụng phụ**, khiến ngay cả bài kiểm tra logic nhỏ cũng cần môi trường phức tạp.

### 4.2. Định nghĩa hợp đồng đầu vào, kết quả và cổng quan sát

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

record Coupon(boolean enabled, long minimumCents, LocalDate expiresOn) {
    Coupon {
        if (minimumCents < 0) {
            throw new IllegalArgumentException("Minimum must be non-negative");
        }
        Objects.requireNonNull(expiresOn, "expiresOn");
    }
}

enum Outcome {
    ACCEPTED, MISSING, DISABLED, BELOW_MINIMUM, EXPIRED
}

record Evaluation(Outcome outcome, LocalDate evaluatedOn) {}

interface AuditSink {
    void record(Evaluation evaluation);
}

final class CouponEvaluator {
    private final Clock clock;
    private final AuditSink audit;

    CouponEvaluator(Clock clock, AuditSink audit) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.audit = Objects.requireNonNull(audit, "audit");
    }

    Evaluation evaluate(Coupon coupon, long subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }

        LocalDate today = LocalDate.now(clock);
        Outcome outcome;

        if (coupon == null) {
            outcome = Outcome.MISSING;
        } else if (!coupon.enabled()) {
            outcome = Outcome.DISABLED;
        } else if (subtotalCents < coupon.minimumCents()) {
            outcome = Outcome.BELOW_MINIMUM;
        } else if (today.isAfter(coupon.expiresOn())) {
            outcome = Outcome.EXPIRED;
        } else {
            outcome = Outcome.ACCEPTED;
        }

        Evaluation result = new Evaluation(outcome, today);
        audit.record(result);
        return result;
    }
}
~~~

Trong phiên bản này:

- `Coupon` và `subtotalCents` là đầu vào trực tiếp.
- `Clock` là phụ thuộc có thể điều khiển; `LocalDate.now(clock)` xét ngày theo múi giờ mà clock mang theo.
- `AuditSink` là **ranh giới tác dụng phụ**, có thể thay bằng nơi ghi nhận dữ liệu trong bộ nhớ ở unit test.
- `Evaluation` cho người gọi biết **kết quả nào** xảy ra và kết quả được đánh giá theo ngày nào.
- Trường hợp số tiền âm có một **hợp đồng ngoại lệ** rõ và chưa gửi bản ghi audit.

**Điều kiện nghiệp vụ cần xác nhận:** thứ tự ưu tiên giữa `DISABLED`, `BELOW_MINIMUM` và `EXPIRED`. Ở ví dụ này, ta chọn thứ tự được nêu trong mã; hệ thống thật phải thống nhất với yêu cầu sản phẩm. Nếu nghiệp vụ muốn báo hết hạn trước khi báo số tiền thiếu, cần thay cả hợp đồng và test, không chỉ đổi vị trí các nhánh để mã trông ngắn hơn.

### 4.3. Lập môi trường giả lập để quan sát tác dụng phụ

Thay vì gửi audit ra dịch vụ thật, unit test dùng một triển khai ghi lại các sự kiện:

~~~java
import java.util.ArrayList;
import java.util.List;

final class InMemoryAuditSink implements AuditSink {
    final List<Evaluation> events = new ArrayList<>();

    @Override
    public void record(Evaluation evaluation) {
        events.add(evaluation);
    }
}
~~~

`InMemoryAuditSink` là một **fake** rất nhỏ: nó thực hiện hợp đồng `AuditSink` đủ để test kiểm tra sự kiện đã được ghi lại. Nó không mở kết nối mạng hoặc database, nên bài test có thể tự chạy và quan sát.

Ở phạm vi ví dụ, mỗi test tạo một instance mới. `ArrayList` không được bảo vệ cho cập nhật đồng thời; fake này chỉ dùng trong các unit test tuần tự minh họa. Muốn kiểm tra luồng đồng thời hoặc một hệ thống audit thực, cần một thiết kế và mức kiểm thử phù hợp.

### 4.4. Tạo thời điểm cố định và kiểm tra ranh giới ngày

Giả sử ngày hết hạn là **31/12/2026** theo múi giờ **Asia/Ho_Chi_Minh (UTC+07:00)**. Ở thời điểm UTC `2026-12-31T16:59:59Z`, địa phương vẫn là 23:59:59 ngày 31/12; một giây sau, địa phương đã sang 00:00:00 ngày 01/01/2027.

Unit test JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import org.junit.jupiter.api.Test;

class CouponEvaluatorTest {
    private static Clock at(String instant) {
        return Clock.fixed(
                Instant.parse(instant),
                ZoneId.of("Asia/Ho_Chi_Minh"));
    }

    private static Coupon activeCoupon() {
        return new Coupon(true, 100_000, LocalDate.of(2026, 12, 31));
    }

    @Test
    void acceptsCouponAtEndOfExpiryDay() {
        var audit = new InMemoryAuditSink();
        var evaluator = new CouponEvaluator(
                at("2026-12-31T16:59:59Z"), audit);

        Evaluation result = evaluator.evaluate(activeCoupon(), 100_000);

        assertEquals(Outcome.ACCEPTED, result.outcome());
        assertEquals(LocalDate.of(2026, 12, 31), result.evaluatedOn());
        assertEquals(List.of(result), audit.events);
    }

    @Test
    void rejectsCouponAfterLocalMidnight() {
        var audit = new InMemoryAuditSink();
        var evaluator = new CouponEvaluator(
                at("2026-12-31T17:00:00Z"), audit);

        Evaluation result = evaluator.evaluate(activeCoupon(), 100_000);

        assertEquals(Outcome.EXPIRED, result.outcome());
        assertEquals(LocalDate.of(2027, 1, 1), result.evaluatedOn());
        assertEquals(List.of(result), audit.events);
    }

    @Test
    void rejectsOrderBelowMinimum() {
        var audit = new InMemoryAuditSink();
        var evaluator = new CouponEvaluator(
                at("2026-12-01T00:00:00Z"), audit);

        Evaluation result = evaluator.evaluate(activeCoupon(), 99_999);

        assertEquals(Outcome.BELOW_MINIMUM, result.outcome());
        assertEquals(1, audit.events.size());
    }

    @Test
    void invalidSubtotalThrowsWithoutAudit() {
        var audit = new InMemoryAuditSink();
        var evaluator = new CouponEvaluator(
                at("2026-12-01T00:00:00Z"), audit);

        assertThrows(IllegalArgumentException.class,
                () -> evaluator.evaluate(activeCoupon(), -1));
        assertTrue(audit.events.isEmpty());
    }
}
~~~

Các test đã thể hiện cả **hai vế của khả năng kiểm thử**:

- **Điều khiển:** tạo thời điểm trước và sau đúng ranh giới ngày, cung cấp mã giảm giá và số tiền theo ý muốn.
- **Quan sát:** kiểm tra `Evaluation`, ngày đánh giá, số lượng/nội dung sự kiện, cũng như tình huống ngoại lệ không được gửi sự kiện.

Đoạn mã ví dụ sử dụng API JUnit Jupiter của JUnit 5; khi đưa vào dự án thật, cần đặt các loại dữ liệu và lớp test trong file/package hợp lệ, cấu hình JUnit trong công cụ build.

### 4.5. Phạm vi của ví dụ

Ví dụ mới kiểm tra **quy tắc và bản ghi gửi tới cổng audit**. Nó chưa chứng minh:

- Repository có lấy đúng mã từ database không.
- Audit service thật có nhận và lưu bản ghi không.
- Giao dịch có bảo đảm kết quả và audit nhất quán nếu audit thất bại không.
- Hệ thống chạy nhiều instance có cập nhật một lượt sử dụng mã chính xác không.

Đặc biệt, ở mã hiện tại, nếu `audit.record(result)` ném ngoại lệ thì `evaluate` cũng ném ngoại lệ và không trả `Evaluation`. Đây là **hành vi có ý nghĩa của hợp đồng**, cần được quyết định theo yêu cầu thực tế. Nếu audit không được phép làm thất bại quyết định nghiệp vụ, cần cơ chế xử lý lỗi hoặc ghi sự kiện bền khác với phiên bản minh họa.

## 5. Điều khiển thời gian mà không can thiệp đồng hồ máy

Thời gian là phụ thuộc rất thường gặp trong quy tắc hết hạn token, giảm giá, đặt vé, lịch hẹn và giới hạn sử dụng.

### 5.1. Truyền giá trị ngày khi chỉ cần một phép so sánh

Nếu chức năng chỉ tính toán theo ngày đã biết, cách đơn giản nhất có thể là:

~~~java
import java.time.LocalDate;

static boolean isValidOn(LocalDate today, LocalDate expiresOn) {
    return !today.isAfter(expiresOn);
}
~~~

Bài test truyền thẳng `today = expiresOn` hoặc ngày hôm sau. Không cần interface hay dependency injection framework.

### 5.2. Truyền Clock khi thành phần chịu trách nhiệm lấy ngày hiện tại

Khi service cần tự xác định “bây giờ”, `Clock` là một phụ thuộc phù hợp:

~~~java
Clock productionClock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
Clock testClock = Clock.fixed(
        Instant.parse("2026-12-31T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

`Clock` giữ cả nguồn thời điểm và múi giờ. Test có thể đặt chính xác mốc thời gian mà không cần chờ, đổi ngày máy hoặc dùng `Thread.sleep`. Với các quy tắc theo ngày, việc sử dụng múi giờ nào vẫn phải xuất phát từ đặc tả nghiệp vụ.

### 5.3. Không nên đọc thời gian nhiều lần trong cùng một quyết định

Nếu một phương thức gọi `LocalDate.now(clock)` ở ba nhánh khác nhau và chạy đúng thời điểm qua ngày mới, các nhánh có thể dùng hai ngày khác nhau. Khi muốn toàn bộ quyết định nhất quán tại một thời điểm, **lấy mốc thời gian một lần rồi truyền giá trị đó cho những bước cần dùng**.

Tuy vậy, với thao tác dài thực sự cần biết thời gian ở nhiều giai đoạn, việc cố định một mốc duy nhất có thể không đúng. Cần xác định “thời điểm quyết định” theo nghiệp vụ thay vì áp dụng mẹo chung cho mọi chức năng.

## 6. Điều khiển phản hồi của phụ thuộc và lỗi hạ tầng

Một dịch vụ thanh toán hay vận chuyển có thể trả thành công, từ chối, timeout hoặc dữ liệu không hợp lệ. Không thể chờ hệ thống thật tình cờ phát sinh đủ mọi lỗi để viết unit test ổn định.

Một ranh giới phụ thuộc rõ có thể có dạng:

~~~java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

Với unit test, ta cung cấp một bản triển khai mô phỏng `PaymentGateway` trả kết quả hoặc ném ngoại lệ theo tình huống đã chọn. Điều này giúp kiểm tra logic xử lý **thanh toán bị từ chối**, **lỗi tạm thời** và **quyết định retry** mà không tạo giao dịch thật.

### 6.1. Phân biệt các loại bản thay thế thường gặp

| Loại | Vai trò trong kiểm thử | Ví dụ |
| --- | --- | --- |
| **Stub** | Trả giá trị đã định để tạo tình huống. | API trả “hết hàng”. |
| **Fake** | Triển khai đơn giản nhưng có hành vi đủ dùng. | Repository dùng `Map` trong bộ nhớ. |
| **Spy** | Ghi lại tương tác để kiểm tra về sau. | Ghi các sự kiện gửi tới `AuditSink`. |
| **Mock** | Tạo kỳ vọng về lời gọi và tham số, thường nhờ framework. | Xác nhận cổng thanh toán được gọi một lần. |

Trong thực hành, ranh giới giữa tên gọi các loại test double có thể khác nhau theo đội nhóm và framework. Điều quan trọng là **bản thay thế phải phản ánh phần hợp đồng mà bài test cần**, không chỉ làm test chạy xanh.

### 6.2. Đừng giả lập mất phần hành vi quan trọng

Một fake repository có thể lưu dữ liệu trong bộ nhớ, nhưng không tự mô phỏng:

- Constraint và isolation của database thật.
- Transaction, rollback hoặc deadlock.
- Serialize/deserialize và mapping kiểu dữ liệu.
- Timeout, retry hoặc phân quyền của hệ thống ngoài.

Do đó, test với fake có thể xác minh logic sử dụng repository; **integration test** vẫn cần thiết để xác minh thực tế kết nối và những bảo đảm mà database chịu trách nhiệm.

### 6.3. Không tạo interface cho mọi phép toán

Truyền `Math.max` qua interface chỉ để mock là dư thừa. Đối với logic thuần túy, dùng giá trị thật thường đơn giản hơn. Interface/cổng là hợp lý khi có **ranh giới bên ngoài, tính không xác định, chi phí lớn hoặc thay đổi độc lập**.

Nguyên tắc là đặt **điểm điều khiển ở nơi có biến động cần kiểm thử**, không thêm tầng trừu tượng đồng loạt.

## 7. Quan sát kết quả: không chỉ kiểm tra giá trị trả về

Một phương thức có thể gây tác dụng phụ dù trả về `void`, hoặc có kết quả chính là thay đổi dữ liệu bên ngoài. Cần chọn điểm quan sát tương ứng với hợp đồng.

### 7.1. Quan sát giá trị trả về

Với hàm tính tiền:

~~~java
long shippingFee(long subtotalCents) {
    return subtotalCents >= 500_000 ? 0 : 30_000;
}
~~~

Test có thể khẳng định:

~~~java
assertEquals(0, shippingFee(500_000));
assertEquals(30_000, shippingFee(499_999));
~~~

Giá trị đầu vào có thể kiểm soát và đầu ra được trả trực tiếp, vì vậy không cần log hoặc mock. Ví dụ giả định đầu vào không âm và chính sách đã nêu là đúng.

### 7.2. Quan sát ngoại lệ và kết quả thất bại

Nếu đặc tả yêu cầu số tiền âm bị từ chối, kiểm tra loại ngoại lệ là một phần hợp đồng:

~~~java
assertThrows(IllegalArgumentException.class,
        () -> evaluator.evaluate(activeCoupon(), -1));
~~~

Không nên bắt mọi ngoại lệ rồi trả một giá trị mặc định nếu điều đó khiến bên gọi không biết thao tác đã thất bại. Ngược lại, không phải mọi tình huống nghiệp vụ “không hợp lệ” đều cần ngoại lệ; một giá trị kết quả có lý do từ chối có thể rõ hơn. Lựa chọn phải dựa trên hợp đồng.

### 7.3. Quan sát trạng thái sau thao tác

Với `OrderRepository`, việc lưu đơn hàng cần được xác minh bằng cách đọc lại dữ liệu qua giao diện công khai hoặc truy vấn kho dữ liệu của môi trường test. Đừng chỉ khẳng định “phương thức `save` đã được gọi” rồi kết luận dữ liệu đã được lưu bền: một lời gọi không bảo đảm commit thành công.

Nếu thao tác cần giữ bất biến “đơn đã thanh toán không thể hủy”, test nên kiểm tra trạng thái cuối và đường đi thất bại phù hợp.

### 7.4. Quan sát sự kiện và tác dụng phụ qua cổng rõ ràng

Khi yêu cầu là “sau khi chấp nhận mã, phát một sự kiện đánh giá”, việc ghi lại dữ liệu gửi qua `AuditSink` cho phép test kiểm tra **nội dung, số lượng và thời điểm tương đối**.

Nếu chỉ có yêu cầu “trả kết quả đúng”, việc ép test xác minh một chuỗi chính xác các lời gọi private helper sẽ khiến test phụ thuộc vào cấu trúc nội bộ. Một lần đổi cách tổ chức mã có thể làm test trượt dù hành vi người dùng không đổi.

**Hãy quan sát điều mà hợp đồng cam kết.** Các chi tiết cài đặt chỉ nên được kiểm tra khi chính chúng là yêu cầu quan trọng, chẳng hạn “không gửi lệnh thanh toán hai lần”.

### 7.5. Quan sát bất đồng bộ

Một phương thức `CompletableFuture<Result>` nên cho bài test quan sát được **sự hoàn tất hoặc thất bại** qua future, callback hay sự kiện có hợp đồng rõ. Việc test gọi `Thread.sleep(1000)` rồi hy vọng công việc đã xong là tín hiệu không ổn định: máy CI chậm hơn hoặc scheduler khác có thể làm test trượt ngẫu nhiên.

Có thể dùng `future.get(timeout, unit)` để giới hạn thời gian chờ và phân biệt timeout với kết quả nghiệp vụ, hoặc đồng bộ theo điều kiện/sự kiện phù hợp. **Timeout dùng để tránh chờ vô hạn**, không thay thế cơ chế xác nhận công việc hoàn tất đúng.

## 8. Mức quan sát vừa đủ để tìm nguyên nhân sai lệch

Một test báo `expected: ACCEPTED, actual: EXPIRED` hữu ích hơn thông báo chung “test failed”. Nhưng nếu chỉ kiểm tra kết quả cuối, đôi khi vẫn khó biết tại sao hệ thống quyết định như vậy.

Có thể bổ sung dấu hiệu chẩn đoán như:

- Mã lý do từ chối có nghĩa nghiệp vụ.
- Mốc thời gian và múi giờ được dùng khi đánh giá.
- Mã định danh tương quan giữa request và sự kiện.
- Thông tin về nguồn dữ liệu/phiên bản chính sách trong phạm vi phù hợp.
- Ngoại lệ giữ được nguyên nhân gốc khi xử lý lỗi.

### 8.1. Phân biệt quan sát cho kiểm thử và cho vận hành

Trong **unit test**, giá trị trả về và fake cho cổng giao tiếp thường là điểm quan sát trực tiếp. Trong **production**, logging, tracing và metrics giúp vận hành nhận biết lỗi xảy ra ở đâu, với tần suất nào, nhưng chúng không thay thế assertion xác minh quy tắc.

Dữ liệu chẩn đoán cần tuân thủ yêu cầu bảo mật. Không nên ghi mật khẩu, token truy cập, thông tin thanh toán nhạy cảm hoặc toàn bộ dữ liệu khách hàng chỉ để test dễ quan sát hơn.

### 8.2. Đừng mở quyền sửa trạng thái private chỉ vì test

Ví dụ, thêm `public void setInternalCounter(...)` vào một service để test cưỡng ép trạng thái có thể phá ranh giới bất biến. Cách tốt hơn là:

- Tạo trạng thái qua hành vi công khai đã được phép.
- Đưa dữ liệu đầu vào hoặc phụ thuộc vào constructor.
- Tách một quy tắc thuần túy có giao diện rõ.
- Dùng test fixture hoặc seed data tại ranh giới lưu trữ phù hợp.

Mục tiêu là **mở các điểm kiểm soát có ý nghĩa trong thiết kế**, không phải biến toàn bộ nội tạng của object thành API công khai.

## 9. Test oracle: quan sát được chưa có nghĩa biết kết quả đúng

*Test oracle* là cách bài test xác định **kết quả nào phải xảy ra**. Một hệ thống có thể quan sát rất rõ nhưng test vẫn sai nếu kỳ vọng không đúng đặc tả.

Ví dụ, với yêu cầu “mã còn giá trị trong ngày hết hạn”, assertion:

~~~java
assertEquals(Outcome.EXPIRED,
        evaluator.evaluate(coupon, amount).outcome());
~~~

sẽ là **oracle sai** nếu `coupon.expiresOn()` bằng ngày hiện tại và các điều kiện khác đều hợp lệ. Test vẫn có thể chạy ổn định; nó chỉ đang bảo vệ hành vi sai.

Để oracle đáng tin hơn:

1. Chuyển yêu cầu thành tiêu chí chấp nhận cụ thể.
2. Xác nhận quy tắc ở ranh giới và trường hợp bất thường.
3. Phân biệt lỗi đầu vào với kết quả nghiệp vụ bị từ chối.
4. Dùng các bảng quyết định hoặc ví dụ đầu vào–đầu ra được người có trách nhiệm xác nhận.
5. Khi bug xảy ra, giữ một test hồi quy phản ánh **kết quả cần có**, không sao chép kết quả của phiên bản lỗi.

Kiểm thử chỉ cung cấp bằng chứng từ những trường hợp đã chạy. **Điều khiển đầu vào tốt** giúp chọn được ca cần thiết; **quan sát tốt** giúp đọc được kết quả; **oracle đúng** mới giúp kết luận ca đó đạt hay không.

## 10. Một ma trận kiểm thử theo điều kiện và kết quả

Với quy tắc `CouponEvaluator`, có thể lập bảng trước khi viết test:

| Ca | Trạng thái mã | Số tiền | Ngày đánh giá | Kết quả kỳ vọng | Quan sát thêm |
| --- | --- | ---: | --- | --- | --- |
| 1 | Bật, tồn tại | Đúng mức tối thiểu | Trước hạn | `ACCEPTED` | Một audit với ngày đã chọn. |
| 2 | Bật, tồn tại | Đúng mức tối thiểu | Đúng ngày hết hạn | `ACCEPTED` | Một audit. |
| 3 | Bật, tồn tại | Đúng mức tối thiểu | Sau hạn một ngày | `EXPIRED` | Một audit. |
| 4 | Bật, tồn tại | Thấp hơn ngưỡng một đơn vị | Trước hạn | `BELOW_MINIMUM` | Một audit. |
| 5 | Tắt, tồn tại | Đủ ngưỡng | Trước hạn | `DISABLED` | Một audit. |
| 6 | Không tồn tại (`null`) | Đủ ngưỡng | Trước hạn | `MISSING` | Một audit. |
| 7 | Bật, tồn tại | Âm | Trước hạn | `IllegalArgumentException` | Không có audit. |

Bảng này giúp người viết test tách rõ **điều có thể chủ động thiết lập** khỏi **điều phải quan sát**. Khi yêu cầu thay đổi, ta cũng biết những ca nào cần xem lại.

Tất cả tình huống trên chỉ phản ánh chính sách đã giả định. Nếu tổ chức không muốn ghi audit cho mã không tồn tại, đó là một thay đổi hợp đồng cần xác nhận chứ không phải lỗi của cơ chế kiểm thử.

## 11. Những rủi ro khi khả năng điều khiển và quan sát kém

### 11.1. Flaky test do thời gian và môi trường

Một bài test chạy đúng vào thời điểm đổi ngày có thể trả kết quả khác nhau. API thật có thể đôi khi timeout; dữ liệu chung có thể thay đổi do bài test khác.

**Cải thiện:** dùng clock cố định, dữ liệu độc lập, phụ thuộc được thiết lập tường minh, tránh sleep tùy ý và kiểm soát vòng đời tài nguyên.

### 11.2. Kết quả bị che giấu bởi log hoặc trạng thái ngầm

Một hàm chỉ ghi “đã xong” có thể không cho biết thao tác thành công hay thất bại. Một field mutable dùng chung chứa trạng thái của request trước có thể khiến kết quả phụ thuộc lịch chạy.

**Cải thiện:** trả về kết quả hoặc lỗi có ý nghĩa, truyền dữ liệu theo từng request, có cổng ghi nhận các tác dụng phụ quan trọng.

### 11.3. Test phụ thuộc thứ tự chạy

Nếu test A tạo bản ghi để test B sử dụng, test B chạy riêng có thể trượt. Nếu service dùng `static` mutable, test này có thể để lại trạng thái cho test khác.

**Cải thiện:** setup/teardown rõ ràng, fixture độc lập, dữ liệu riêng cho từng ca, dọn tài nguyên ở đúng vòng đời và tránh phụ thuộc vào trạng thái còn sót.

### 11.4. Mock quá chặt làm test dễ vỡ

Một unit test xác nhận chính xác mọi lời gọi nội bộ có thể thất bại khi refactor chia/tách helper dù kết quả không đổi. Test như vậy tạo gánh nặng bảo trì và khiến nhóm ngại cải thiện cấu trúc.

**Cải thiện:** ưu tiên assertion về kết quả, trạng thái, sự kiện và tương tác thật sự nằm trong hợp đồng. Không đo chất lượng test chỉ bằng số lượng mock hoặc câu `verify`.

### 11.5. Không nhìn thấy lỗi cập nhật đồng thời

Hai request có thể cùng được chấp nhận khi cả hai đọc tồn kho trước lúc ghi. Unit test cho hàm kiểm tra điều kiện có thể đỗ hoàn toàn, nhưng invariant của database vẫn bị phá.

**Cải thiện:** kiểm thử tính nguyên tử tại lớp dữ liệu và kết hợp suy luận về đồng thời. Fake in-memory không chứng minh isolation của database thật.

## 12. Khi kiểm thử nhiều tầng, hãy kiểm soát và quan sát đúng ranh giới

| Tầng kiểm thử | Điều khiển thường dùng | Điều có thể quan sát | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Unit test** | Giá trị đầu vào, `Clock`, stub/fake, dữ liệu tại chỗ. | Giá trị trả về, ngoại lệ, sự kiện qua cổng, trạng thái đối tượng. | Không tự xác minh tích hợp với hệ thống thật. |
| **Integration test** | Database test, dịch vụ mô phỏng, transaction/fixture rõ. | Dữ liệu lưu, hợp đồng API, rollback, thông điệp tại ranh giới. | Thường chậm hơn và bị ảnh hưởng bởi môi trường. |
| **Contract test** | Phản hồi hoặc yêu cầu theo schema/hợp đồng. | Khả năng hai bên tương tác đúng giao diện thỏa thuận. | Không bảo đảm mọi luồng người dùng. |
| **End-to-end test** | Dữ liệu và môi trường gần vận hành thực. | Phản hồi qua ứng dụng hoàn chỉnh và kết quả nghiệp vụ. | Ít kiểm soát hơn, khó xác định nguyên nhân nếu lỗi. |
| **Kiểm thử vận hành/khả năng chịu lỗi** | Tải, độ trễ, lỗi mạng hoặc lỗi thành phần được tạo theo kịch bản. | Metrics, log, trace, thời gian phục hồi, trạng thái dữ liệu. | Kết luận phụ thuộc điều kiện thử nghiệm và rủi ro được mô phỏng. |

Không phải tầng càng cao thì mọi thứ đều “đúng hơn”. Tầng cao cung cấp bằng chứng về khả năng các phần kết nối thật làm việc với nhau; tầng thấp giúp kiểm tra nhiều trường hợp nghiệp vụ nhanh và chính xác hơn.

Một chiến lược tốt đặt **nhiều ca logic nhỏ, ổn định ở tầng unit**, kết hợp **những ca tích hợp quan trọng tại ranh giới** và **một số luồng đầu cuối có giá trị nghiệp vụ**. Tỷ lệ cụ thể phải theo mức độ rủi ro và chi phí của hệ thống.

## 13. Kiểm thử lỗi và trường hợp khó tái hiện

Đặc điểm của một hệ thống dễ kiểm thử không chỉ là chạy tốt với đầu vào đúng, mà còn có thể **chủ động tạo ra tình huống bất thường** và nhìn thấy cách hệ thống phản ứng.

Một danh sách tình huống đáng cân nhắc:

- API từ chối hoặc trả `5xx`.
- Yêu cầu vượt thời gian chờ.
- Repository ném ngoại lệ khi lưu.
- Sự kiện bị gửi trùng hoặc gửi muộn.
- Dữ liệu chứa `null`, vượt phạm vi số hoặc có mã không tồn tại.
- Hai thao tác cạnh tranh cập nhật cùng tài nguyên.
- Clock đi qua ranh giới ngày, tháng, năm hoặc múi giờ.
- Cấu hình chính sách được thay giữa hai lần đọc.

Ví dụ, nếu hệ thống có retry khi gọi API, test cần kiểm soát chuỗi phản hồi “thất bại tạm thời → thành công”, đồng thời quan sát **số lần gọi** và **kết quả cuối**. Tuy nhiên, phải tránh kiểm thử retry bằng chờ thời gian thực khi có thể thay thế scheduler/backoff theo giao diện rõ ràng.

Với hệ thống phân tán, đôi khi không thể kiểm soát mọi thứ trong một unit test. Ta dùng thêm kiểm thử tích hợp và kỹ thuật tạo lỗi có kiểm soát, đồng thời chỉ đưa ra kết luận trong phạm vi đã kiểm tra.

## 14. Đánh đổi khi tăng khả năng kiểm thử

Thiết kế để kiểm thử tốt cũng có chi phí.

### 14.1. Truyền phụ thuộc làm hợp đồng rõ nhưng tăng số đối tượng

`Clock` và `AuditSink` bổ sung tham số constructor. Lợi ích là nguồn thời gian và tác dụng phụ được nhìn thấy; chi phí là nơi khởi tạo phải cung cấp các phụ thuộc ấy.

Không nên vì muốn giảm số tham số mà chuyển chúng vào singleton toàn cục khó kiểm soát. Mặt khác, cũng không cần tạo 20 interface cho 20 phép toán thuần túy.

### 14.2. Kết quả giàu thông tin giúp debug nhưng phải ổn định

`Evaluation` mang `Outcome` và ngày đánh giá giúp test và bên gọi hiểu lý do. Nếu kết quả công khai chứa nhiều chi tiết triển khai tạm thời, mỗi refactor có thể thành thay đổi API. Hãy đưa ra **thông tin có ý nghĩa và ổn định theo hợp đồng**, không trả mọi biến cục bộ.

### 14.3. Tạo bản giả có thể che khác biệt với hệ thống thật

Fake giúp test nhanh, nhưng không thể tự mô phỏng hành vi giao dịch, timeout, serialization hoặc phân quyền của môi trường thật. Chi phí của fake còn gồm việc cập nhật theo hợp đồng.

Một số thành phần có thể phù hợp hơn với kiểm thử tích hợp trên dependency thật trong môi trường cô lập; cần cân đối tốc độ, độ tin cậy và mức độ đại diện.

### 14.4. Quan sát nhiều không đồng nghĩa lộ thông tin riêng tư

Trace, log và sự kiện debug có thể làm tăng chi phí lưu trữ và phát tán thông tin nhạy cảm. Chỉ ghi dữ liệu cần thiết, dùng định danh tương quan thích hợp và tuân thủ hợp đồng bảo mật. Không mở trạng thái nội bộ tùy tiện để chiều theo một cách kiểm thử ngắn hạn.

## 15. Tình huống thực tế: lỗi thông báo giao hàng lúc nửa đêm

Giả sử nhóm có tính năng gửi thông báo “đơn đã trễ hẹn” nếu thời gian hiện tại vượt mốc giao dự kiến. Một số khách hàng báo rằng thông báo bị gửi sớm vào ngày đổi múi giờ. Test trên máy lập trình viên vẫn đỗ.

**Dấu hiệu điều khiển kém:** mã đọc thời gian hệ thống mặc định; test không thể chọn chính xác thời điểm ngay trước và ngay sau ranh giới ngày.

**Dấu hiệu quan sát kém:** phương thức gửi email rồi trả `void`; test chỉ tìm dòng log “sent” mà không xác nhận đúng khách hàng, đúng đơn và đúng mốc thời gian.

Một hướng sửa có căn cứ là:

1. Xác định theo yêu cầu nghiệp vụ thời điểm “trễ” được so sánh bằng `Instant` hay ngày địa phương, và múi giờ nào áp dụng.
2. Đưa nguồn thời gian vào `Clock` hoặc truyền thời điểm cần xét tới phần quyết định.
3. Trả về một quyết định có lý do, đồng thời tách cổng gửi thông báo để ghi nhận sự kiện trong unit test.
4. Tạo test ở **một giây trước** và **đúng mốc trễ**; kiểm tra người nhận, đơn hàng, lý do và không gửi trùng khi nghiệp vụ yêu cầu.
5. Thêm kiểm thử tích hợp ở ranh giới queue/email nếu cần bảo đảm việc phát thông báo thật và cơ chế retry.

Bằng cách đó, nhóm không phải đợi lỗi xảy ra lại trong production mới có thể tái hiện. Test logic trở nên ổn định; test tích hợp được dùng để xác minh phần phụ thuộc bên ngoài theo phạm vi riêng.

## 16. Bài tập tự đánh giá

### Tình huống A: hàm tính lãi

Hàm `calculateInterest` nhận số dư nhưng tự gọi hệ thống cấu hình để lấy lãi suất hiện hành. Test muốn kiểm tra chính xác số tiền khi lãi suất thay đổi.

**Câu hỏi:** đầu vào ẩn nào cần điều khiển, cách tổ chức nào đơn giản nhất và kết quả nên quan sát ra sao?

**Gợi ý:** lãi suất là đầu vào ảnh hưởng trực tiếp tới phép tính. Có thể đưa lãi suất vào tham số của hàm thuần túy, còn việc đọc cấu hình nằm tại tầng gọi. Test kiểm tra số tiền và quy tắc làm tròn với các giá trị biên. Không cần mock hệ thống cấu hình trong mọi unit test của hàm tính.

### Tình huống B: lệnh lưu đơn hàng

Service gọi `repository.save(order)` và trả `void`. Test dùng mock để xác nhận `save` được gọi, nhưng ở môi trường thật transaction bị rollback.

**Câu hỏi:** bài test hiện chứng minh được gì? Cần thêm điểm quan sát ở đâu?

**Gợi ý:** test xác nhận service đã yêu cầu repository lưu. Nó chưa chứng minh commit thành công. Cần integration test với database phù hợp, kiểm tra dữ liệu đã lưu và xử lý lỗi transaction; kết quả service nên phản ánh hợp đồng thành công/thất bại nếu người gọi cần biết.

### Tình huống C: tác vụ nền gửi hai email

Bài test gọi xử lý bất đồng bộ, sau đó `Thread.sleep(1000)` và kiểm tra rằng có hai dòng log chứa chữ “sent”.

**Câu hỏi:** vì sao test vẫn dễ sai và cách làm nào quan sát chính xác hơn?

**Gợi ý:** thời gian hoàn tất không chắc định; log không bảo đảm đúng người nhận hoặc tránh gửi trùng. Nên chờ tín hiệu hoàn tất có thời hạn, dùng fake ghi nhận nội dung/correlation ID của lệnh gửi, và kiểm tra chính xác các sự kiện cần có. Tích hợp với email provider thật là trách nhiệm của mức test khác.

## 17. Checklist khi thiết kế hoặc review mã có thể kiểm thử

- [ ] Tôi có thể thiết lập các đầu vào thường gặp, trường hợp biên và dữ liệu không hợp lệ.
- [ ] Những nguồn biến động như thời gian, ngẫu nhiên, cấu hình hoặc API bên ngoài được kiểm soát ở ranh giới thích hợp.
- [ ] Mỗi ca test có dữ liệu và trạng thái độc lập hoặc cơ chế dọn sạch rõ ràng.
- [ ] Kết quả có thể kiểm tra qua giá trị trả về, ngoại lệ, trạng thái sau thao tác hoặc sự kiện có hợp đồng.
- [ ] Test không chỉ khẳng định một phương thức đã được gọi nếu yêu cầu thực tế là dữ liệu phải được lưu hoặc thao tác phải hoàn tất.
- [ ] Fake/stub/mock phản ánh đủ phần hợp đồng cần thử và có kiểm thử tích hợp cho những khác biệt quan trọng.
- [ ] Test có oracle dựa trên yêu cầu, đặc biệt ở ngưỡng, ngày hết hạn và thứ tự xử lý lỗi.
- [ ] Tôi tránh phụ thuộc vào `Thread.sleep` hoặc thời gian thật khi có thể quan sát hoàn tất theo cơ chế rõ ràng.
- [ ] Một lần refactor chi tiết nội bộ không làm hỏng hàng loạt test nếu hành vi công khai không đổi.
- [ ] Phụ thuộc được đưa vào vì có biến động hoặc ranh giới thật, không phải chỉ để tăng số lượng interface.
- [ ] Hệ thống có đủ thông tin chẩn đoán nhưng không phơi bày dữ liệu nhạy cảm không cần thiết.
- [ ] Tôi có thể nói rõ điều đã được kiểm tra ở tầng unit, điều cần kiểm tra ở tầng tích hợp và những rủi ro còn lại.

## 18. Kết luận

**Khả năng điều khiển đầu vào** cho phép tạo chủ động và tái lập các điều kiện cần kiểm tra. **Khả năng quan sát kết quả** cho phép nhìn thấy hành vi cần xác minh qua hợp đồng rõ ràng, thay vì đoán từ chi tiết nội bộ hoặc log chung chung. Hai thuộc tính kết hợp với **test oracle đúng** tạo nền tảng cho các bài kiểm thử có ý nghĩa.

Trong **CODE_QUALITY_FUNDAMENTALS**, thiết kế mã nguồn có điểm điều khiển và quan sát phù hợp góp phần làm mã **đáng tin cậy, dễ hiểu và dễ thay đổi**. Hãy bắt đầu từ đầu vào và kết quả có ý nghĩa nghiệp vụ, tách những phụ thuộc biến động ở ranh giới cần thiết, dùng test tự động để bảo vệ các hành vi quan trọng và tiếp tục xác minh tích hợp ở nơi có phụ thuộc thật. Mục tiêu không phải làm mọi chi tiết có thể bị mock, mà là **khi một yêu cầu thay đổi hoặc một lỗi xuất hiện, ta có thể tạo lại tình huống và biết chính xác hành vi nào cần được sửa**.

