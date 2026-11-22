# Kiểm thử không ổn định và nguyên nhân cần điều tra

Một bản thay đổi Java vượt qua toàn bộ kiểm thử trên máy lập trình viên. Cùng commit đó lên CI lại thất bại ở một test liên quan đến thời gian. Người phát triển bấm chạy lại, test chuyển sang màu xanh, rồi nhóm kết luận “chắc CI chậm”. Vài ngày sau, lỗi quay lại. Thực tế, **việc một lần chạy lại thành công không giải thích được vì sao lần trước thất bại**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu các thuộc tính làm mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Bằng chứng kiểm thử**, bài này tập trung vào **kiểm thử không ổn định (flaky test)** và cách điều tra có hệ thống. Một bài kiểm thử chỉ là bằng chứng hữu ích khi nhóm hiểu **điều kiện thực thi, kết quả mong đợi, cách quan sát và những yếu tố có thể khiến kết quả thay đổi**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện kiểm thử không ổn định và phân biệt nó với lỗi được tái hiện ổn định, thay đổi môi trường có chủ đích hoặc lỗi triển khai thực sự.
- Phân loại nguyên nhân thường gặp: thời gian, xử lý bất đồng bộ, cạnh tranh luồng, trạng thái dùng chung, thứ tự test, ngẫu nhiên, dữ liệu và hệ thống bên ngoài.
- Viết Java/JUnit 5 kiểm thử thời gian bằng `Clock.fixed` và chờ thao tác bất đồng bộ bằng tín hiệu hoàn thành thay vì ngủ tùy ý.
- Thu thập **bằng chứng đủ để điều tra**, gồm đầu vào, môi trường, phiên bản, lần chạy, dấu vết và đặc điểm khác biệt.
- Quyết định khi nào cần sửa test, sửa mã sản phẩm, sửa hạ tầng hoặc tạm cách ly test; tránh dùng retry để che giấu lỗi.

## 1. Flaky test là gì?

Một **flaky test** là bài kiểm thử có thể **đạt hoặc không đạt giữa những lần chạy được kỳ vọng là tương đương**, trong khi phần mã và hợp đồng hành vi đang kiểm tra không có thay đổi có chủ đích giải thích sự khác biệt. Triệu chứng thường gặp là cùng commit, cùng dữ liệu kiểm tra và cùng bộ cấu hình được công bố, nhưng kết quả lúc xanh lúc đỏ.

Định nghĩa này cần được dùng cẩn thận:

- Hai lần chạy tưởng là giống nhau có thể khác **múi giờ, biến môi trường, thứ tự test, tải CPU, dữ liệu còn sót, phiên bản phụ thuộc hoặc trạng thái dịch vụ đối tác**.
- Một test chập chờn có thể phản ánh **lỗi thật của sản phẩm**, ví dụ race condition hoặc logic thiếu tính nguyên tử, chứ không nhất thiết là test viết sai.
- Nếu quy tắc nghiệp vụ hoặc đầu vào đã thay đổi, kết quả khác nhau **không tự động** là flakiness.
- Một test luôn thất bại với cùng điều kiện thường là **lỗi có thể tái hiện**, chưa phải dấu hiệu không ổn định.

Hãy phân biệt **triệu chứng** với **chẩn đoán**: “test không ổn định” mô tả kết quả đã quan sát; “do `Thread.sleep`”, “do dữ liệu dùng chung” hay “do mã xử lý song song” mới là giả thuyết về nguyên nhân cần kiểm chứng.

### Vì sao kiểm thử không ổn định làm giảm chất lượng?

| Hậu quả | Cơ chế gây ra | Rủi ro cho dự án |
| --- | --- | --- |
| Mất niềm tin vào CI | Một test đỏ đôi khi tự xanh khi chạy lại | Nhóm bắt đầu bỏ qua cả lỗi thật |
| Phản hồi chậm | Nhiều lần chạy lại và điều tra thủ công | Thời gian phát triển, review, phát hành kéo dài |
| Che giấu hồi quy | Retry làm kết quả cuối cùng xanh | Lỗi mới lọt qua kiểm soát |
| Gây khó khăn khi bảo trì | Không biết thay đổi nào làm test hỏng | Ngại refactor và thay dependency |
| Không xác định được tác động | Test thất bại nhưng log thiếu ngữ cảnh | Không phân biệt bug sản phẩm với lỗi môi trường |

Một báo cáo “98% test pass” có thể che giấu một số ít test quan trọng không đáng tin cậy. **Độ tin cậy của bằng chứng không chỉ phụ thuộc số lượng test đạt**, mà còn phụ thuộc độ ổn định, tính đại diện và khả năng giải thích các lần thất bại.

## 2. Nhận diện mô hình thất bại

Khi gặp một test đỏ rồi xanh trở lại, đừng vội khẳng định nguyên nhân. Hãy ghi lại **điều kiện và hình dạng của lỗi**.

| Quan sát | Giả thuyết nên kiểm tra | Điều chưa được kết luận |
| --- | --- | --- |
| Chạy riêng luôn đạt, chạy cả suite đôi khi thất bại | Trạng thái giữa test, thứ tự, chạy song song | Chưa biết test nào gây nhiễm trạng thái |
| Chỉ đỏ ở gần nửa đêm | Phụ thuộc ngày hoặc múi giờ mặc định | Chưa chắc lỗi nằm trong test thay vì code nghiệp vụ |
| Đỏ chủ yếu trên CI tải cao | Timeout, chờ cố định, cuộc đua đồng bộ | Không được mặc định mọi thất bại là “CI chậm” |
| Chỉ đỏ ở Windows | Phân biệt hoa/thường, đường dẫn, line ending, locale | Không tự động chứng minh Windows sai |
| Đỏ sau khi chạy một test khác | Static state, tệp chung, database chưa dọn | Phải xác nhận thứ tự gây lỗi |
| Đỏ khi phụ thuộc dịch vụ thật | Mạng, rate limit, dữ liệu, timeout, lỗi đối tác | Có thể là sự cố tích hợp thật cần xử lý |
| Cùng seed nhưng kết quả vẫn thay đổi | Trạng thái ngoài seed, thứ tự luồng, dữ liệu dùng chung | Seed cố định không kiểm soát mọi nguồn biến động |

Các dấu hiệu này **gợi ý hướng điều tra**, không phải bảng chẩn đoán tự động. Cần tái hiện có kiểm soát và thu thập dấu vết tương ứng.

## 3. Nguồn bất định thứ nhất: thời gian thực

Một test kiểm tra mã ưu đãi trước khi hết hạn có thể viết như sau:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class FlakyExpiryTest {
    @Test
    void couponIsStillValid() throws InterruptedException {
        Instant expiresAt = Instant.now().plusMillis(30);

        Thread.sleep(10);

        assertTrue(Instant.now().isBefore(expiresAt));
    }
}
~~~

Ý định là kiểm tra mã vẫn còn hiệu lực khi chưa tới hạn. Nhưng `Thread.sleep(10)` chỉ yêu cầu luồng ngủ **ít nhất trong một khoảng dự kiến**, không bảo đảm sau đúng 10 mili giây test sẽ chạy tiếp. JVM có thể bị tạm dừng bởi garbage collection, máy CI có thể bận hoặc hệ điều hành có thể lập lịch trễ. Khi thời gian thực vượt 30 mili giây, kiểm thử thất bại dù quy tắc `now < expiresAt` hoàn toàn đúng.

**Nguyên nhân cốt lõi:** thời gian vừa là **dữ liệu đầu vào nghiệp vụ**, vừa bị ẩn trong quá trình thực thi test. Test không kiểm soát chính điều kiện quyết định kết quả.

### Đưa đồng hồ thành phụ thuộc

Một thành phần có thể đọc thời gian từ `Clock` được truyền vào constructor:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class CouponValidity {
    private final Clock clock;

    public CouponValidity(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean isValidUntil(Instant expiresAt) {
        Objects.requireNonNull(expiresAt, "expiresAt");
        return clock.instant().isBefore(expiresAt);
    }
}
~~~

Trong chương trình thật, điểm khởi tạo có thể dùng `new CouponValidity(Clock.systemUTC())`. Trong test, dùng `Clock.fixed` để chọn **một thời điểm xác định**:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class CouponValidityTest {
    private static final Instant EXPIRES_AT =
        Instant.parse("2026-11-16T12:00:00Z");

    private CouponValidity at(String time) {
        Clock clock = Clock.fixed(
            Instant.parse(time),
            ZoneOffset.UTC
        );
        return new CouponValidity(clock);
    }

    @Test
    void validBeforeExpiry() {
        assertTrue(at("2026-11-16T11:59:59Z")
            .isValidUntil(EXPIRES_AT));
    }

    @Test
    void invalidAtExactExpiry() {
        assertFalse(at("2026-11-16T12:00:00Z")
            .isValidUntil(EXPIRES_AT));
    }

    @Test
    void invalidAfterExpiry() {
        assertFalse(at("2026-11-16T12:00:01Z")
            .isValidUntil(EXPIRES_AT));
    }
}
~~~

Bây giờ thời gian là **đầu vào kiểm soát được**, và các test xác minh quy tắc tại đúng những mốc quan trọng: **trước, bằng và sau hạn**. Chúng không phụ thuộc vào tốc độ máy hoặc thời điểm lịch của ngày chạy test.

Nếu quy tắc dùng ngày địa phương, hãy làm rõ `ZoneId` và loại ngày/giờ phù hợp. Chỉ cố định `Instant` trong test không giải quyết được việc ứng dụng ngầm sử dụng múi giờ mặc định ở nơi khác.

## 4. Nguồn bất định thứ hai: chờ bất đồng bộ sai cách

Một test gửi công việc sang luồng khác rồi chờ một khoảng cố định thường trông như sau:

~~~java
// Minh họa mẫu dễ bị lỗi: tác vụ hoàn thành nhanh hay chậm
// còn phụ thuộc lịch chạy của executor.
executor.submit(() -> processOrder(orderId));
Thread.sleep(50);
assertTrue(orderWasProcessed(orderId));
~~~

Test đang **đoán** rằng 50 mili giây là đủ. Khi máy chậm, tác vụ chưa xong nên test đỏ; tăng lên 500 mili giây chỉ đẩy xác suất lỗi xuống và làm test chậm hơn, chưa xác định được điều kiện hoàn thành.

### Chờ theo tín hiệu hoàn thành

Với API trả về `Future` hoặc `CompletableFuture`, có thể chờ chính tác vụ đó với **giới hạn thời gian**. Ví dụ JUnit 5 tự chứa:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class AsyncResultTest {
    @Test
    void waitsForResultInsteadOfGuessingDelay() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<String> result = executor.submit(() -> "PROCESSED");

            assertEquals("PROCESSED", result.get(2, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

`Future.get(timeout, unit)` chờ tới khi tác vụ **thực sự hoàn thành**, trả lỗi hoặc hết hạn chờ. Giá trị hai giây ở đây là **giới hạn bảo vệ test khỏi treo vô hạn**, không phải yêu cầu ngủ đúng hai giây trước khi kiểm tra. Khi tác vụ xong sớm, test tiếp tục ngay.

Trong hệ thống có callback hoặc sự kiện, `CountDownLatch`, `CompletableFuture`, cơ chế await có điều kiện hoặc một giao diện nhận kết quả rõ ràng có thể phù hợp. Điều kiện chờ phải gắn với **sự kiện có ý nghĩa**, ví dụ “đơn hàng được ghi nhận”, chứ không chỉ “đã qua một khoảng thời gian”.

**Chú ý:** chờ theo tín hiệu không tự sửa được race condition trong sản phẩm. Nếu sản phẩm thực sự xử lý sai thứ tự hoặc mất cập nhật, một test đồng bộ tốt có thể giúp **tái hiện chính xác lỗi thật**, thay vì khiến lỗi bị che bởi chờ tùy ý.

## 5. Nguồn bất định thứ ba: trạng thái và thứ tự chạy test

Ví dụ sau minh họa một lớp kiểm thử dùng trạng thái `static`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class SharedStateTest {
    private static final Map<String, Integer> STOCK = new HashMap<>();

    @Test
    void addsStock() {
        STOCK.put("PEN", 5);
        assertEquals(5, STOCK.get("PEN"));
    }

    @Test
    void startsWithNoStock() {
        assertEquals(0, STOCK.getOrDefault("PEN", 0));
    }
}
~~~

Nếu `addsStock()` chạy trước `startsWithNoStock()` trong cùng JVM và bản đồ chưa được dọn, test thứ hai thất bại. Nếu thứ tự ngược lại, cả hai có thể đạt. Trong tình huống chạy song song, `HashMap` còn không phải cấu trúc an toàn cho các thao tác truy cập đồng thời tùy ý.

Đây không phải “JUnit chạy sai thứ tự”. Bài test thứ hai đang ngầm phụ thuộc vào một **tiền điều kiện chưa được thiết lập**: kho hàng phải rỗng.

### Tạo fixture độc lập cho từng test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class IsolatedStateTest {
    private Map<String, Integer> stock;

    @BeforeEach
    void setUp() {
        stock = new HashMap<>();
    }

    @Test
    void addsStock() {
        stock.put("PEN", 5);
        assertEquals(5, stock.get("PEN"));
    }

    @Test
    void startsWithNoStock() {
        assertEquals(0, stock.getOrDefault("PEN", 0));
    }
}
~~~

Ví dụ này dựa vào **vòng đời mặc định per-method của JUnit Jupiter**: mỗi phương thức test dùng một instance riêng, và `@BeforeEach` tạo bản đồ mới. Nếu dự án thay `@TestInstance(PER_CLASS)` và chạy test song song trên cùng instance, việc chia sẻ trường cần được xem xét lại. Điều quan trọng là **mỗi bài test sở hữu fixture của mình**, không phải chỉ dựa vào việc gọi `clear()` trên một cấu trúc `static` vẫn bị nhiều test dùng chung.

Với database thật, cô lập thường cần **schema hoặc database riêng**, transaction rollback phù hợp, dữ liệu có định danh duy nhất, hoặc quy trình dọn dẹp được kiểm chứng. Với filesystem, dùng thư mục tạm riêng cho mỗi test (ví dụ `@TempDir` trong JUnit 5). Với cổng mạng, không giả định một cổng cố định luôn rảnh. Với biến môi trường và `System.setProperty`, cần nhớ đây là trạng thái có phạm vi rộng hơn một đối tượng test.

### Cẩn trọng với kiểm thử chạy song song

Vấn đề thứ tự không chỉ nằm ở fixture. Nếu test chạy song song và cùng chỉnh một đối tượng hoặc tài nguyên chung, kết quả có thể tùy thuộc vào **interleaving** — thứ tự xen kẽ các thao tác từ nhiều luồng.

Không nên mặc định chữa bằng cách **tắt toàn bộ kiểm thử song song**. Điều đó có thể giảm triệu chứng nhưng cũng che một rò rỉ trạng thái hoặc race condition đáng sửa. Có những tài nguyên buộc phải chạy tuần tự; khi đó hãy đánh dấu và cô lập **phạm vi thực sự cần tuần tự**, đồng thời ghi rõ lý do.

## 6. Các nguyên nhân khác: môi trường, dữ liệu, ngẫu nhiên và hệ thống ngoài

Ngoài ba nhóm chính, rất nhiều test không ổn định vì dựa vào điều kiện bên ngoài mà không công bố:

| Nguồn thay đổi | Ví dụ | Cách làm rõ hoặc kiểm soát |
| --- | --- | --- |
| **Múi giờ/locale** | Parse `01/02/2026` theo định dạng mặc định | Chỉ định `Locale`, `ZoneId` và định dạng được hỗ trợ |
| **Thứ tự collection** | Test so sánh chuỗi kết quả dựa vào thứ tự `HashMap` | Quy định thứ tự nếu là hợp đồng; sắp xếp trước khi so sánh hoặc so sánh như tập |
| **Dữ liệu kiểm thử** | Dùng chung mã khách hàng/đơn hàng với test khác | Fixture riêng, định danh độc lập, dọn dẹp có kiểm chứng |
| **Filesystem** | Đường dẫn cứng, thư mục cũ hoặc khác biệt hoa/thường | Thư mục tạm riêng, chuẩn đường dẫn và quyền phù hợp |
| **Ngẫu nhiên** | Test sinh dữ liệu khác nhau mỗi lần nhưng không lưu seed | Seed có thể tái hiện; lưu cả seed và dữ liệu gây lỗi |
| **Mạng và dịch vụ ngoài** | Timeout, DNS, rate limit hoặc dữ liệu API bên thứ ba thay đổi | Fake/contract test cho logic; integration test riêng với điều kiện vận hành rõ |
| **Phiên bản hạ tầng** | JDK, DB, thư viện, cấu hình JVM khác giữa local và CI | Ghi phiên bản và chạy lại trên môi trường tương đương |
| **Tài nguyên máy** | Tranh CPU, kết nối cạn, đĩa gần đầy | Ghi tình trạng tài nguyên; điều tra timeout và giới hạn |
| **Bộ nhớ đệm và thứ tự khởi tạo** | Cache từ ca trước làm thay đổi kết quả | Tạo cache mới, xóa theo giao thức an toàn hoặc dùng khóa dữ liệu riêng |

### Ngẫu nhiên có seed cố định có giải quyết hết không?

Không. Ví dụ `new Random(12345L)` giúp chuỗi giá trị do chính đối tượng đó tạo ra có thể được lặp lại khi giữ cùng thuật toán. Nhưng kết quả vẫn có thể khác nếu mã cũng dựa vào thời gian, thứ tự luồng, dữ liệu service ngoài hoặc số lần gọi hàm sinh ngẫu nhiên thay đổi.

Khi test property-based hoặc fuzzing phát hiện lỗi, nên ghi lại **seed, đầu vào thu nhỏ (nếu công cụ có hỗ trợ), phiên bản công cụ và lệnh tái hiện**. Seed chỉ là một phần của hồ sơ bằng chứng.

### Test dùng hệ thống thật có luôn là flaky test kém chất lượng?

Không. Một bài kiểm thử tích hợp gọi dịch vụ thật có thể thất bại vì hệ thống ngoài thực sự đang không đáp ứng **mức dịch vụ mà sản phẩm phải xử lý**. Đây có thể là tín hiệu quan trọng về khả năng phục hồi.

Vấn đề là **mục tiêu test** phải rõ: nếu unit test logic định dạng số tiền phụ thuộc mạng Internet, đó thường là phụ thuộc không cần thiết. Nếu test đang chứng minh quy trình thanh toán end-to-end, sự cố mạng hoặc đối tác lại là phần môi trường cần quan sát, phân loại và có cách báo lỗi phù hợp.

## 7. Thu thập bằng chứng trước khi thay đổi

Khi một test không ổn định, đầu ra “Failed” hoặc “Passed” không đủ để kết luận nguyên nhân. Cần có **bản ghi điều tra** phản ánh cả lần thất bại và các lần chạy lại.

| Trường thông tin | Vì sao cần | Ví dụ minh họa |
| --- | --- | --- |
| Test và tình huống | Biết chính xác hành vi nào được kiểm tra | `CouponValidityTest.invalidAtExactExpiry` |
| Commit/build | Xác nhận mã nào đã chạy | SHA hoặc mã CI run |
| Môi trường | So sánh JDK, OS, timezone, locale, dependency | JDK 17, Linux, UTC |
| Đầu vào hoặc seed | Tái tạo tình huống quyết định | `expiresAt=...12:00:00Z` |
| Actual và expected | Thấy sai lệch cụ thể | expected=false, actual=true |
| Stack trace/log liên quan | Định vị điểm phát sinh | Assertion, timeout, lỗi DB |
| Thứ tự và chế độ thực thi | Phát hiện chia sẻ trạng thái | Chạy riêng/suite, tuần tự/song song |
| Thời gian và tài nguyên | Phát hiện áp lực và race | Độ trễ, CPU, thời gian chờ |
| Kết quả nhiều lần | Mô tả mức không ổn định đã quan sát | 3 fail trên 20 lần chạy |

**Ví dụ:** 3 lần thất bại trong 20 lần thử tương đương **15% thất bại quan sát được trong mẫu đó**. Đây không phải xác suất thất bại thực của mọi môi trường hay mọi lần chạy tương lai; mẫu nhỏ, thứ tự chạy và cấu hình có thể làm kết quả thay đổi. Ghi con số kèm **điều kiện thử** sẽ hữu ích hơn nói “thi thoảng fail”.

Khi lưu log, cần **khử thông tin nhạy cảm**, không đưa token, mật khẩu hoặc dữ liệu thật của khách hàng vào báo cáo lỗi. Dấu vết phải đủ tái hiện nhưng vẫn tuân thủ ranh giới bảo mật dữ liệu.

## 8. Quy trình điều tra có hệ thống

Có thể áp dụng quy trình sau cho một test thất bại không thường xuyên:

1. **Giữ lại lần thất bại đầu tiên.** Lưu kết quả, stack trace, log và mã CI run trước khi chạy lại. Không chỉ chụp kết quả cuối cùng sau retry.
2. **Xác định phạm vi.** Lỗi xảy ra ở một test, một nhóm test hay cả suite? Chỉ ở một OS/JDK? Chỉ khi chạy song song hoặc khi có tải?
3. **Kiểm tra giả định “cùng điều kiện”.** So sánh cấu hình, dữ liệu, time zone, biến môi trường, phiên bản dependency, thứ tự test, fixture và tài nguyên chung.
4. **Tái hiện có kiểm soát.** Chạy test riêng, chạy cùng nhóm test nghi ngờ, đổi thứ tự, bật/tắt song song hoặc chạy lặp lại; mỗi phép thử chỉ nên thay đổi một yếu tố chính để rút ra kết luận.
5. **Khoanh vùng theo nguồn biến động.** Đọc nơi gọi `now()`, `sleep()`, bộ sinh số ngẫu nhiên, biến `static`, cache, mạng, filesystem, DB và các callback không có điểm chờ.
6. **Kiểm tra có phải bug sản phẩm không.** Nếu thao tác song song có thể làm mất dữ liệu thật hoặc một kết quả nghiệp vụ sai, cần sửa logic đồng thời hoặc hợp đồng, không chỉ sửa test.
7. **Sửa đúng nguyên nhân.** Ví dụ dùng `Clock.fixed`, fixture riêng, tín hiệu hoàn thành, cô lập nguồn dữ liệu, hoặc bổ sung bảo vệ transaction/đồng bộ cho hành vi thật.
8. **Xác nhận và lưu bằng chứng sau sửa.** Chạy lại những tình huống từng fail, chạy suite liên quan và ghi nhận môi trường/lệnh kiểm tra. Tiếp tục giám sát nếu lỗi trước đó hiếm gặp.

Trong quá trình này, **mỗi lần chạy lại nên trả lời một câu hỏi**: “nếu chỉ thay đổi thứ tự test, lỗi có biến mất không?”, “nếu đồng hồ cố định, kết quả còn dao động không?”, “nếu chạy với nhiều luồng, có xuất hiện lỗi?”.

Lặp lại test hàng trăm lần có thể giúp làm lộ lỗi hiếm, nhưng chỉ **chạy nhiều lần rồi thấy xanh** chưa chứng minh nguyên nhân đã được loại bỏ. Bằng chứng mạnh hơn là một thay đổi hợp lý theo giả thuyết và quan sát tương ứng trước/sau trong điều kiện kiểm soát.

## 9. Sửa test hay sửa sản phẩm?

Một nguyên tắc quan trọng là **không mặc định coi mọi flake là lỗi của test**.

| Tình huống | Vấn đề nằm ở đâu? | Hướng giải quyết |
| --- | --- | --- |
| Test ngủ 50 ms rồi kiểm tra tác vụ hoàn thành | Cách đồng bộ của test | Chờ Future/latch/tín hiệu thực |
| Test lấy ngày hiện tại nhưng kỳ vọng ngày cố định | Dữ liệu/đồng hồ chưa được kiểm soát | Truyền `Clock`, cố định ngày và múi giờ |
| Test A để dữ liệu lại làm test B fail | Fixture hoặc trạng thái chia sẻ | Cô lập dữ liệu, đóng tài nguyên, làm sạch đúng phạm vi |
| Hai yêu cầu rút tiền đồng thời làm số dư âm | Bug tính nhất quán của sản phẩm | Bảo vệ transaction/đồng bộ, thêm kiểm thử hồi quy |
| Adapter trả dữ liệu không có thứ tự trong khi hợp đồng yêu cầu thứ tự | Có thể là bug sản phẩm | Quy định `ORDER BY` hoặc sắp xếp đúng ranh giới |
| Test áp đặt thứ tự lên tập dữ liệu vốn **không có cam kết thứ tự** | Kỳ vọng của test sai | So sánh theo tập/multiset phù hợp |
| Dịch vụ ngoài hết thời gian chờ | Có thể là hạ tầng, tích hợp hoặc sản phẩm thiếu xử lý | Phân loại theo SLO/hợp đồng và kiểm tra cơ chế phục hồi |

Thực tế có thể có **nhiều nguyên nhân đồng thời**. Ví dụ, test có timeout quá ngắn *và* sản phẩm có khóa tranh chấp làm độ trễ không chấp nhận được. Không nên điều chỉnh timeout để che một vấn đề hiệu năng thực tế nếu sản phẩm đã cam kết giới hạn thời gian.

## 10. Retry, quarantine và việc bảo vệ độ tin cậy của CI

**Retry** có thể giúp thu thập thêm bằng chứng, nhất là khi lỗi hiếm, nhưng không nên được dùng như cách xóa dấu vết thất bại. Nếu hệ thống CI tự chạy lại, báo cáo cần giữ:

- Kết quả **lần chạy đầu tiên**.
- Số lần retry và kết quả từng lần.
- Loại lỗi, thông tin môi trường và liên kết log.
- Trạng thái theo dõi nguyên nhân, không chỉ trạng thái xanh cuối cùng.

**Quarantine** (tạm cách ly test khỏi bộ chặn phát hành) đôi khi cần thiết khi một test đang gây chặn toàn bộ pipeline và đã được xác nhận là không đáng tin cậy. Đây là **biện pháp quản lý rủi ro tạm thời**, không phải sửa lỗi:

| Điều kiện quản lý | Cách thực hiện có trách nhiệm |
| --- | --- |
| Có lý do cách ly rõ ràng | Ghi lỗi và bằng chứng flakiness |
| Có người hoặc nhóm chịu trách nhiệm | Chỉ định chủ sở hữu điều tra |
| Có thời hạn xem lại | Đặt mốc khắc phục hoặc đánh giá tiếp |
| Không làm mất thông tin | Tiếp tục chạy và lưu kết quả test ngoài luồng chặn nếu khả thi |
| Đánh giá mức độ rủi ro | Không âm thầm bỏ bảo vệ cho chức năng tiền, quyền, an toàn hoặc dữ liệu quan trọng |

Nếu test quan trọng đang bắt được một race condition của hệ thống thật, việc cách ly có thể khiến lỗi nghiêm trọng lọt qua. Cần phân loại rủi ro và có sự chấp thuận phù hợp trước khi thay đổi cổng chất lượng của dự án.

**Không được “sửa” test bằng cách xóa assertion có ý nghĩa, thay expected cho khớp actual sai, hoặc tăng timeout vô hạn.** Những thay đổi như vậy có thể làm giảm bằng chứng thay vì cải thiện sản phẩm.

## 11. Thiết kế test ổn định ngay từ đầu

Một số thực hành giúp tránh nhiều nguồn flakiness:

**Thiết lập trạng thái đầy đủ trong từng test.** Đầu vào, fixture, quyền, dữ liệu và đồng hồ phải được kiểm soát hoặc ghi rõ. Một test không nên “tình cờ” dùng dữ liệu còn sót từ test trước.

**Giới hạn phụ thuộc ngoài.** Unit test nên có ranh giới rõ và dùng fake/stub cho I/O khi thích hợp; integration test dành để chứng minh adapter và hệ thống ngoài hoạt động đúng theo hợp đồng. Không mock mọi thứ, nhưng cũng không để một phép tính thuần túy đòi hỏi mạng.

**Chờ theo điều kiện có thể quan sát.** Với xử lý bất đồng bộ, đợi Future hoặc tín hiệu hoàn thành, có timeout hữu hạn và thông tin chẩn đoán khi hết hạn.

**Chọn dữ liệu không nhập nhằng.** Dùng mã định danh riêng, timezone/locale tường minh, thứ tự được xác định khi đó là hợp đồng, seed tái hiện và khoảng biên được kiểm soát.

**Quản lý vòng đời tài nguyên.** Đóng executor, client, file stream, transaction và dọn trạng thái test đúng phạm vi. Với Java, có thể dùng `try-with-resources` cho tài nguyên triển khai `AutoCloseable` hoặc xử lý cleanup trong `finally`.

**Kiểm tra hành vi thay vì chi tiết ngẫu nhiên.** Nếu hợp đồng nói “danh sách chứa A và B” nhưng không nói thứ tự, không nên buộc kết quả bằng đúng chuỗi `"[A, B]"`. Ngược lại, nếu thứ tự có nghĩa nghiệp vụ, test phải kiểm tra điều đó.

**Thiết kế cho chẩn đoán.** Assertion nên thể hiện expected/actual có ý nghĩa, log lỗi có correlation ID, thời điểm hoặc seed khi cần, và cho phép nhận biết lỗi đến từ test, adapter hay hệ thống thật.

## 12. Bài tập tình huống

Xét bộ kiểm thử cho một kho lưu trữ đơn hàng tối giản:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderStoreTest {
    private static final List<String> ORDERS = new ArrayList<>();

    @Test
    void savesOrder() {
        ORDERS.add("ORD-001");
        assertEquals(1, ORDERS.size());
    }

    @Test
    void startsEmpty() {
        assertEquals(0, ORDERS.size());
    }
}
~~~

**Câu hỏi A.** Test nào có thể thất bại khi đổi thứ tự chạy? Tại sao?

**Câu hỏi B.** Thay `ORDERS.clear()` bằng một lệnh trong `@BeforeEach` có đủ an toàn khi các test dùng chung danh sách `static` và chạy song song không?

**Câu hỏi C.** Làm sao viết lại bộ test để giảm phụ thuộc thứ tự mà vẫn xác minh hành vi lưu đơn?

**Câu hỏi D.** Nếu test chỉ đỏ khi chạy trên CI, bạn sẽ thu thập tối thiểu những bằng chứng nào trước khi kết luận do hạ tầng?

### Gợi ý đáp án

**A.** `startsEmpty()` có thể thất bại nếu `savesOrder()` đã chạy trước và danh sách chưa được dọn. `savesOrder()` cũng có thể thất bại nếu có dữ liệu còn sót từ lần chạy khác trong cùng JVM. Chạy song song còn khiến hành vi truy cập `ArrayList` dùng chung không có bảo đảm thread-safe.

**B.** Không. `@BeforeEach` xóa một danh sách `static` dùng chung có thể làm test này can thiệp vào test khác ngay giữa lúc kiểm tra. Nó tạo thêm biến động chứ không giải quyết quyền sở hữu dữ liệu.

**C.** Cho mỗi test một `List<String>` hoặc một instance `OrderStore` mới trong fixture, khởi tạo đúng dữ liệu từng test. Nếu test phải dùng database, cung cấp phạm vi dữ liệu/transaction độc lập và xác nhận chiến lược cleanup.

**D.** Ghi commit, CI run, JDK/OS, timezone/locale, log và assertion expected–actual, thứ tự test, chế độ chạy song song, dữ liệu ban đầu, tình trạng tài nguyên và kết quả chạy riêng/chạy cả suite. Chỉ sau khi so sánh các điều kiện đó mới có cơ sở khoanh vùng hạ tầng hay phụ thuộc chia sẻ.

## Ghi nhớ

**Kiểm thử không ổn định là một tín hiệu cần điều tra, không phải một ngoại lệ nên được bỏ qua.** Nó có thể bắt nguồn từ test viết không xác định, dữ liệu hoặc hạ tầng thiếu cô lập, nhưng cũng có thể phát hiện **lỗi đồng thời hoặc quy tắc thật trong sản phẩm**.

Để bằng chứng kiểm thử đáng tin cậy, hãy kiểm soát **thời gian, dữ liệu, thứ tự, tài nguyên và điểm hoàn thành của thao tác bất đồng bộ**; giữ **dấu vết của lần thất bại đầu tiên**; xác minh giả thuyết bằng phép thử có kiểm soát; và sửa đúng nguyên nhân. **Chạy lại để thấy xanh không đồng nghĩa đã chứng minh hệ thống đúng.**
