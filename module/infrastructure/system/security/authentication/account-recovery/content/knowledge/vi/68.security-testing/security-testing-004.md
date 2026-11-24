# Rate limit security test

## 1. Kiểm thử giới hạn phải chứng minh điều gì?

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, rate limit bảo vệ các điểm có thể bị lạm dụng khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Những điểm đó gồm khởi tạo recovery, gửi lại thông báo, thử mã xác minh, tạo hồ sơ hỗ trợ và thực hiện thao tác nhạy cảm sau xác minh.

Một test gửi nhiều request rồi thấy HTTP 429 chưa đủ. Hệ thống có thể trả lỗi nhưng đã gửi SMS, đã gọi nhà cung cấp xác minh có tính phí hoặc đã cho một số request đồng thời thay đổi credential. Cũng có thể limiter hoạt động đúng trên một instance nhưng mỗi instance lại cấp một ngân sách độc lập.

Mục tiêu của bài là thiết kế kiểm thử chứng minh ba điều: hành động nhạy cảm không vượt ngân sách được phép; phạm vi ngân sách không bị thay đổi bằng dữ liệu không đáng tin; người dùng hợp lệ còn đường khôi phục phù hợp sau khi giới hạn có hiệu lực.

OWASP khuyến nghị chống yêu cầu quên mật khẩu tự động quá mức, giữ phản hồi nhất quán giữa tài khoản tồn tại và không tồn tại, đồng thời tránh khóa tài khoản chỉ vì yêu cầu quên mật khẩu. Đây là các yêu cầu cần xem xét cùng nhau khi thiết kế phép thử. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Các endpoint, cấu hình và API Java trong bài là ví dụ cho test harness, không khẳng định dự án đã có những lớp hoặc route đó. Các ngưỡng nhỏ được chọn để dễ kiểm tra; phải lấy ngưỡng thực tế từ policy của môi trường cần đánh giá.

## 2. Phân biệt những loại ngân sách khác nhau

Rate limit theo thời gian, ngân sách đoán mã và giới hạn số thao tác đang chạy không có cùng ý nghĩa.

| Loại kiểm soát | Điều được giới hạn | Khi nào có thể cấp lại quyền thử? |
| --- | --- | --- |
| Giới hạn khởi tạo | Số yêu cầu recovery theo subject hoặc nguồn | Khi thuật toán và cửa sổ thời gian cho phép |
| Giới hạn delivery | Số thông báo được tạo hoặc gửi | Theo ngân sách delivery và quy tắc gửi lại |
| Ngân sách thử challenge | Số lần kiểm tra bằng chứng/mã của challenge | Theo vòng đời challenge; không mặc định phục hồi mỗi phút |
| Giới hạn đồng thời | Số công việc xác minh đang thực hiện | Khi công việc kết thúc hoặc lease hết hiệu lực theo thiết kế |
| Giới hạn chi phí | Chi phí provider theo tenant hoặc hệ thống | Theo kỳ ngân sách và cơ chế vận hành |
| Giới hạn hỗ trợ thủ công | Số thao tác của nhân viên hoặc trên subject | Theo policy hỗ trợ và phân quyền |

Ví dụ, một challenge cho phép tối đa năm lần thử sai trong cả vòng đời. Chờ hết cửa sổ một phút của limiter IP không được tự cấp thêm năm lần đoán cho challenge đó. Ngược lại, cạn ngân sách gửi email không nhất thiết phải cấm người dùng sử dụng token còn hợp lệ đã nhận trước đó.

Với passkey, không có một “mã PIN recovery” chung để đoán qua backend trong mọi thiết kế. Phải kiểm tra đúng bằng chứng thay thế mà luồng recovery sử dụng; không giả lập mất passkey bằng cách tiếp tục xác thực với private key đã được coi là mất.

### 2.1. Xác định đơn vị bị tính phí

Một request có thể dẫn đến nhiều công việc: tra cứu account, tạo challenge, ghi outbox và gọi provider. Cần ghi rõ giới hạn bảo vệ đơn vị nào.

Nếu ngân sách là “không quá năm lần tạo ý định gửi trong mười phút”, test đếm các ý định đã commit. Nếu ngân sách là “không quá năm lần gọi provider”, phải quan sát adapter gọi provider, kể cả retry. Không thay hai đại lượng này cho nhau.

Tương tự, một HTTP request có thể thử nhiều mã nếu API nhận một danh sách. Giới hạn request không tự giới hạn số lần kiểm tra bí mật; API phải từ chối batch không được hỗ trợ hoặc tính đúng số phép thử theo hợp đồng.

### 2.2. Quyết định bộ đếm tăng ở điểm nào

Đối với ngân sách chống đoán, thiết kế cần xử lý cả các lần kiểm tra đang chạy. Nếu chỉ tăng số lần sai sau khi trả kết quả, nhiều request đồng thời có thể cùng thấy còn lượt và thực hiện kiểm tra. Một phương án là đặt chỗ cho lượt thử trước khi kiểm tra rồi hoàn tất kết quả theo policy; phương án khác là tuần tự hóa trên challenge.

Test phải đo số phép kiểm tra thực sự bắt đầu, không chỉ đọc bộ đếm cuối. Ngoài ra phải làm rõ request sai cú pháp, request lặp lại, lỗi provider và timeout có tiêu tốn ngân sách hay không. Không tự giả định mọi lỗi đều được hoàn lượt.

## 3. Viết hợp đồng trước khi sinh tải

Một hợp đồng kiểm thử có thể được mô tả như sau:

```yaml
# Dữ liệu minh họa cho test, không phải cấu hình production đề xuất.
policyVersion: recovery-test-v1
startRecovery:
  algorithm: fixed_window
  subjectLimit: 5
  windowSeconds: 600
  countAt: admission
  blockedCallsExtendWindow: false
verifyChallenge:
  maxWrongAttemptsPerChallenge: 5
  resendResetsWrongAttempts: false
publicResponse:
  revealSubjectThrottle: false
storeFailure:
  allowSensitiveActionWithoutBudgetDecision: false
```

Phần `revealSubjectThrottle: false` có nghĩa caller chưa xác thực không nhận thông tin riêng cho biết subject đang bị giới hạn. Nó không cấm hệ thống trả 429 cho giới hạn nguồn đã được thiết kế độc lập với việc account tồn tại.

Với một fixed window có ngân sách `L`, nếu tất cả request dùng cùng khóa và rơi vào cùng cửa sổ:

```text
Số quyết định ALLOW đã cấp trong cửa sổ <= L.

Nếu có ít nhất L request hợp lệ,
kho đếm không lỗi, không có policy khác chặn,
và test chỉ gọi riêng primitive admission:
    số ALLOW = L.
```

Ở test endpoint, không ép số lần đổi credential bằng `L`. Các điều kiện token dùng một lần, challenge hết hạn hoặc xác minh thất bại có thể làm số thành công thấp hơn. Bất biến của limiter là không vượt ngân sách; bất biến của nghiệp vụ được kiểm tra riêng.

### 3.1. Oracle gồm cả quyết định và tác động

Oracle là căn cứ xác định kết quả đúng. Nên thu thập ít nhất hai lớp quan sát.

| Lớp | Quan sát cần thiết | Lỗi dễ bị bỏ sót nếu thiếu |
| --- | --- | --- |
| Admission | ALLOW, THROTTLE, UNAVAILABLE; scope và policy version | Timeout bị gộp thành từ chối thông thường |
| Delivery | Outbox intent, lần gọi provider, trạng thái retry | Trả lỗi nhưng vẫn gửi thông báo |
| Xác minh | Số lần validator thực sự được gọi | Nhiều request vượt ngân sách đoán mã |
| Credential | Phiên bản mật khẩu, MFA/passkey được đăng ký hoặc thu hồi | Request bị chặn vẫn có tác động |
| Session | Session mới, refresh token, bước thu hồi theo policy | Quyền truy cập được tạo dù bị chặn |
| Quan sát vận hành | Audit có kiểm soát, metric, độ trễ, queue | Cơ chế chặn tự làm cạn tài nguyên |

Request bị chặn vẫn có thể tạo audit hoặc tăng bộ đếm chống lạm dụng. Phát biểu “không có side effect” cần giới hạn vào những tác động nhạy cảm bị cấm, thay vì cấm mọi ghi nhận.

## 4. Kiểm thử khóa giới hạn và ranh giới tin cậy

Khóa quyết định request nào chia sẻ ngân sách. Một biểu diễn khái niệm:

```text
subjectScope = environment | tenant | purpose | canonicalSubject
sourceScope  = environment | resolvedClientSource | operationFamily
challengeScope = environment | tenant | serverBoundChallengeId
```

Không phải mọi ngân sách đều có cùng cấu trúc. Ngân sách subject thường cần tách tenant; ngân sách hạ tầng toàn cục có thể chủ ý dùng chung. Test phải phân biệt “chia sẻ đúng mục đích” với “đụng khóa ngoài ý muốn”.

### 4.1. Những trường không được giao cho client quyết định

Tenant phải được xác định theo ngữ cảnh định tuyến và xác thực hợp lệ. Purpose của hành động lấy từ operation phía server, không tin một field tùy ý trong body. Challenge ID phải gắn với subject và tenant đã được server xác nhận.

Caller không được tự thay ngân sách bằng cách gửi `policyVersion`, `risk=low`, `verified=true` hoặc một request ID mới. Những field này có thể tồn tại vì mục đích khác, nhưng không được trở thành bằng chứng cấp quota.

Đối với client IP sau reverse proxy, tạo test ở cả đường đi qua proxy được tin cậy và kết nối trực tiếp. Header `X-Forwarded-For` hay `Forwarded` từ peer không được tin cậy không nên tự biến thành danh tính nguồn có quyền chọn ngân sách. Không chỉ kiểm tra một hàm parse header bằng unit test.

### 4.2. Chuẩn hóa định danh phải theo quy tắc thật

Dùng các biến thể được hệ thống coi là cùng một subject: khoảng trắng ngoài được phép, alias nội bộ đã được xác nhận, hoặc chữ hoa/thường nếu quy tắc định danh có quy định tương ứng. Các biến thể đó phải cùng chịu ngân sách subject.

Không tự áp dụng quy tắc bỏ dấu chấm hay bỏ phần sau dấu cộng cho mọi email. Đây có thể là những địa chỉ khác nhau ở nhà cung cấp khác. Việc test cần chứng minh là limiter dùng cùng phép định danh với recovery, không phải limiter tự sáng tạo phép hợp nhất account.

Với định danh không tồn tại, vẫn cần một cách tính chi phí và phản hồi được thiết kế nhất quán. Đừng chỉ sinh khóa sau khi account được tìm thấy rồi để đường không tồn tại hoàn toàn khác về thời gian, bộ đếm hoặc header.

### 4.3. Ma trận khóa

| Thay đổi giữa các request | Kỳ vọng cần chốt trước |
| --- | --- |
| Cùng subject, thay nguồn mạng | Ngân sách subject tiếp tục có hiệu lực |
| Cùng nguồn, nhiều subject | Ngân sách nguồn hoặc tổng chi phí có hiệu lực theo policy |
| Cùng local account ID, hai tenant | Ngân sách subject tách đúng tenant |
| Hai route phục vụ cùng một thao tác | Không vô tình cấp hai ngân sách độc lập |
| Password recovery và MFA recovery | Tách hoặc chia sẻ theo purpose đã thiết kế |
| Mỗi lần tạo challenge mới | Không tự làm mới mọi ngân sách chống đoán |
| Thay request ID, cookie chưa xác thực | Không tạo quyền cấp quota mới |
| Thay header nguồn từ peer không tin cậy | Không đổi danh tính nguồn đã được server xác định |

## 5. Test tuần tự tại ngưỡng

Với fixture `L = 5`, cửa sổ mười phút và thời gian được giữ trong cùng cửa sổ, thực hiện ba nhóm: trước ngưỡng, đúng ngưỡng và sau ngưỡng.

```text
Request 1..5: primitive admission trả ALLOW.
Request 6:    trả THROTTLE.
Request 7:    vẫn THROTTLE khi chưa có điều kiện cấp lại ngân sách.

Quan sát:
- Chỉ các admission được phép mới đi tới tác động cần bảo vệ.
- Request bị chặn không đổi credential hay tạo recovery session.
- Tác động delivery không vượt đơn vị ngân sách đã công bố.
```

Mỗi request phải hợp lệ ở các điều kiện khác để bài test thực sự chạm limiter. Nếu cả sáu request đều sai schema và bị validation từ chối, sáu HTTP 400 không chứng minh giới hạn hoạt động.

Tách hai test: một test cho primitive admission với các input hợp lệ, và một test qua endpoint để chứng minh middleware hoặc service thực sự gọi primitive trước tác động nhạy cảm.

Nếu public endpoint luôn trả thông điệp chung, không dùng public response để đếm ALLOW. Dùng quan sát nội bộ của test harness và outbox/provider giả; các quan sát đó không được mở thành API debug công khai.

## 6. Biên thời gian và thuật toán giới hạn

### 6.1. Fixed window

Giả sử cửa sổ là `[10:00:00Z, 10:10:00Z)`. Test cần bao phủ một thời điểm trước biên, đúng biên và sau biên. Chọn độ phân giải được implementation và storage hỗ trợ; đừng giả định nanosecond trong Java còn nguyên sau khi ghi database.

Fixed window có thể cho phép một nhóm request ở cuối cửa sổ và nhóm khác ngay đầu cửa sổ kế tiếp. Điều này có thể đúng thuật toán nhưng không đáp ứng yêu cầu “không quá năm lần trong bất kỳ mười phút liên tiếp nào”. Khi đó phát hiện cần ghi là policy chọn thuật toán chưa phù hợp, không mặc định coi việc reset tại biên là lỗi lập trình.

### 6.2. Sliding window và token bucket

Với sliding window, tạo hai cụm request nằm sát biên của một cửa sổ cố định để kiểm tra ngân sách không bị cấp lại toàn bộ chỉ vì đổi phút. Cần xác định implementation là sliding log chính xác hay phép xấp xỉ có sai số.

Với token bucket, test dung lượng burst ban đầu, tốc độ nạp lại, cách xử lý token phân số và mức trần khi để rỗi lâu. Trong khoảng thời gian `Δt`, với dung lượng `B` và tốc độ nạp `r`, số admission tiêu tốn một token không được vượt ngân sách ban đầu cộng lượng nạp được phép; tính kỳ vọng cụ thể theo quy tắc làm tròn và trạng thái ban đầu.

Không dùng oracle fixed window cho token bucket. Một token được nạp lại trước khi “hết mười phút” có thể là hành vi đúng của bucket.

### 6.3. Cửa sổ không được kéo dài ngoài hợp đồng

Nếu request bị chặn không được gia hạn thời gian chặn, hãy gửi thêm request bị chặn trong khoảng chờ và xác nhận thời điểm mở lại không bị dời vô hạn. Nếu policy chủ ý dùng backoff tăng dần, test phải bao phủ mức trần và điều kiện khôi phục khả dụng.

Đối với thử mã challenge, hết TTL của một khóa rate limit phụ không được làm biến mất bộ đếm thử đã gắn với vòng đời challenge. Thử gửi lại mã hoặc tạo request mới để xác nhận ngân sách ở cấp subject vẫn được áp dụng.

### 6.4. Kiểm soát đúng nguồn thời gian

`Clock.fixed(...)` chỉ điều khiển nơi thực sự đọc clock đó. Nó không tự thay clock của Redis, database, gateway hoặc provider. Một integration test dùng TTL native phải quan sát thời gian của kho thật, dùng cửa sổ kiểm thử ngắn với dung sai hợp lý, hoặc dùng cơ chế điều khiển thời gian được môi trường test hỗ trợ.

Không thêm header công khai cho client đặt thời gian hiện tại. Tránh `sleep` dài làm căn cứ duy nhất; ưu tiên điểm đồng bộ và polling có deadline cho điều kiện quan sát được.

## 7. Request đồng thời và nhiều instance

Một lỗi phổ biến là tách “đọc số lượt” và “tăng số lượt” thành hai bước không bảo vệ chung. Hai request cùng đọc giá trị bốn rồi cùng được cho phép dù ngân sách là năm.

Kiểm thử cần tạo va chạm có chủ đích:

1. Khởi tạo scope mới với ngân sách năm lượt.
2. Chuẩn bị nhiều tác vụ, giữ chúng ở cùng một barrier.
3. Mở barrier để cùng gọi admission trong một cửa sổ.
4. Thu thập mọi kết quả, kể cả exception và timeout.
5. Đếm ALLOW và đối chiếu tác động thực tế.

Với limiter có cam kết quyết định chính xác và môi trường không có lỗi, test primitive có thể yêu cầu đúng năm ALLOW. Nếu hệ thống công bố sai số do cơ chế phân tán, phép thử phải dùng giới hạn sai số cụ thể đã được duyệt; không tự thêm một mức dung sai để test qua.

### 7.1. Mẫu hợp đồng kiểm thử Java

Đoạn dưới minh họa JUnit 5 cho primitive, với adapter `fixture` do test suite cung cấp. Đây không phải implementation limiter và chưa đủ để chạy độc lập. Fixture phải tạo scope biệt lập, nối tới chính primitive cần kiểm tra, giữ các lần gọi trong cùng cửa sổ và không phát sinh admission phụ.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

abstract class AdmissionContract {
    enum Outcome { ALLOW, THROTTLE, UNAVAILABLE }

    record Scope(String tenant, String purpose, String subjectRef) {}

    interface Fixture extends AutoCloseable {
        // Tạo ngân sách mới; không reset namespace của test khác.
        Scope freshScope(int capacity);

        // Gọi primitive đang được đánh giá, không gọi oracle thay thế.
        Outcome admit(Scope scope);

        @Override
        void close();
    }

    protected abstract Fixture newFixture();

    @Test
    void sixthAdmissionIsBlocked() {
        try (Fixture fixture = newFixture()) {
            Scope scope = fixture.freshScope(5);
            for (int i = 0; i < 5; i++) {
                assertEquals(Outcome.ALLOW, fixture.admit(scope));
            }
            assertEquals(Outcome.THROTTLE, fixture.admit(scope));
            assertEquals(Outcome.THROTTLE, fixture.admit(scope));
        }
    }

    @Test
    void concurrentAdmissionsShareOneBudget() throws Exception {
        int callers = 24;
        ExecutorService pool = Executors.newFixedThreadPool(callers);
        CountDownLatch ready = new CountDownLatch(callers);
        CountDownLatch start = new CountDownLatch(1);

        try (Fixture fixture = newFixture()) {
            Scope scope = fixture.freshScope(5);
            List<Future<Outcome>> futures = new ArrayList<>();
            try {
                for (int i = 0; i < callers; i++) {
                    futures.add(pool.submit(() -> {
                        ready.countDown();
                        if (!start.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("start barrier timeout");
                        }
                        return fixture.admit(scope);
                    }));
                }
                assertTrue(ready.await(5, TimeUnit.SECONDS));
                start.countDown();

                int allowed = 0;
                int throttled = 0;
                for (Future<Outcome> future : futures) {
                    Outcome outcome = future.get(10, TimeUnit.SECONDS);
                    assertNotEquals(Outcome.UNAVAILABLE, outcome);
                    if (outcome == Outcome.ALLOW) allowed++;
                    if (outcome == Outcome.THROTTLE) throttled++;
                }
                assertEquals(5, allowed);
                assertEquals(callers - 5, throttled);
            } finally {
                start.countDown();
                for (Future<Outcome> future : futures) future.cancel(true);
                pool.shutdownNow();
                assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS));
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Barrier có cùng số worker thực thi với số tác vụ chờ; nếu pool chỉ có vài thread nhưng chờ toàn bộ 24 tác vụ báo sẵn sàng trước khi mở barrier, test có thể tự deadlock. Deadline trong ví dụ là giới hạn cho môi trường test, không phải cấu hình timeout production.

Không bỏ qua future bị lỗi rồi chỉ đếm các kết quả còn lại. Nếu 20 request timeout và bốn request ALLOW, kết quả chưa chứng minh hệ thống đáp ứng đúng ngưỡng hoặc giữ được khả dụng.

### 7.2. Vượt qua ranh giới process

Chạy cùng kịch bản với request được phân phối qua ít nhất hai instance sử dụng cùng policy và kho ngân sách. Chứng minh qua log/trace test rằng cả hai instance đều nhận request; sticky session có thể khiến bài test trông phân tán nhưng thực chất chỉ gọi một process.

Thử tiếp sau khi restart một instance. Nếu quota thuộc subject trong cửa sổ vẫn còn hiệu lực, restart không được tự cấp ngân sách mới. Với limiter có phần cache cục bộ, cần đánh giá rõ cách đồng bộ và sai số đã cam kết.

Một unit test dùng `synchronized` trên object Java chỉ chứng minh tính tuần tự hóa của object đó. Nó không chứng minh admission giữa nhiều JVM, vùng triển khai hoặc shard.

## 8. Kho đếm, TTL và lỗi không rõ kết quả

Nếu dùng Redis, tính nguyên tử của từng lệnh không có nghĩa chuỗi lệnh từ ứng dụng nguyên tử. Tài liệu `INCR` nêu tình huống tăng bộ đếm nhưng không gắn hạn khi client ngắt giữa `INCR` và `EXPIRE`, và minh họa cách gom thao tác bằng script. Hãy kiểm tra đúng cơ chế mà hệ thống đang triển khai. [Redis INCR](https://redis.io/docs/latest/commands/incr/).

Các bài test cần quan tâm đến trạng thái trung gian và vòng đời:

| Tình huống tạo lỗi | Kết quả cần kiểm tra theo hợp đồng |
| --- | --- |
| Process chết giữa cập nhật và đặt hạn | Không để một khóa chặn vĩnh viễn hoặc mất kiểm soát quota |
| Request bị chặn liên tục | TTL chỉ đổi nếu policy cho phép đổi |
| Kho trả timeout sau khi đã nhận thao tác | Hệ thống xử lý kết quả chưa rõ một cách xác định |
| Kho không truy cập được | Không tự coi việc thiếu quyết định là ALLOW |
| Replica chậm hoặc failover | Quota và sai số nằm trong cam kết thực tế |
| Key bị eviction | Hành vi mất ngân sách được phát hiện và xử lý theo thiết kế |
| Nhiều quota được kiểm tra lần lượt | Tác động trừ lượt từng scope khớp policy |
| Lỗi script hoặc kiểu dữ liệu không hợp lệ | Không âm thầm bỏ qua kiểm soát |

Đừng giả định transaction/script của một kho bao phủ cả database credential hoặc provider bên ngoài. Admission và tác động nhạy cảm có thể cần reservation, outbox hoặc cơ chế idempotency riêng; test phải quan sát đường kết nối đó.

### 8.1. Không đồng nhất timeout với chưa tính lượt

Server có thể đã tăng bộ đếm nhưng phản hồi bị mất. Retry mù có thể trừ hai lần, còn hoàn lượt mù có thể làm thiếu số lượt thực đã dùng. Tạo fault injection ở cả hai vị trí: trước khi kho xử lý và sau khi kho xử lý nhưng trước khi client nhận kết quả.

Nếu dùng idempotency, hợp đồng phải xác định khóa gắn với operation, subject, tenant và payload nào. Cùng một khóa không được cho phép đổi sang mã đoán khác rồi dùng lại quyết định cũ. Có thể vẫn tính chi phí request ở một ngân sách bảo vệ hạ tầng dù tác động nghiệp vụ được khử trùng lặp.

### 8.2. Chế độ suy giảm có giới hạn

Đối với hành động thay mật khẩu, reset MFA hoặc cấp recovery session, không cho phép tiếp tục chỉ vì không đọc được ngân sách, trừ khi có cơ chế thay thế đã được thiết kế và kiểm chứng. Nếu có limiter cục bộ dự phòng, test phải dùng chính giới hạn suy giảm đó và phân tích tổng ngân sách qua nhiều instance.

Không ép mọi lỗi kho thành 429. Request bị throttle và request chưa thể quyết định do dependency lỗi là hai tình trạng vận hành khác nhau. Public response có thể che chi tiết, nhưng metric và test oracle cần phân biệt.

## 9. Kiểm thử đường vòng và vòng đời recovery

### 9.1. Khởi tạo, gửi lại và cấp challenge mới

Sau khi cạn ngân sách subject, thử các đường khởi tạo tương đương mà hệ thống công khai: phiên bản API còn hỗ trợ, giao diện web/mobile và đường gửi lại. Mục tiêu là xác nhận các đường cùng ý nghĩa đi qua kiểm soát chung phù hợp.

Tạo challenge mới không được vô tình loại bỏ mọi giới hạn trên subject. Tuy nhiên, không áp đặt rằng mọi challenge trong cả đời account phải chia sẻ một bộ đếm sai không bao giờ được reset. Chính sách cần nêu vòng đời và điều kiện cấp lại quyền thử dựa trên bằng chứng phù hợp.

Resend cần được kiểm tra ở cả hai mặt: có bị tính ngân sách gửi đúng không, và có thay đổi ngân sách đoán mã hoặc làm token cũ mất hiệu lực như policy đã công bố không.

### 9.2. Mã đúng ở thời điểm hết lượt

Khi challenge đã hết ngân sách thử, gửi một mã đúng được tạo từ fixture và xác minh hành vi theo policy. Không mặc định mã đúng phải luôn được chấp nhận: nếu đã hết quyền thực hiện phép kiểm tra, hệ thống có thể yêu cầu một luồng xác minh khác.

Đồng thời, việc cạn ngân sách khởi tạo không nên tự động phá token đã cấp hợp lệ nếu policy không yêu cầu như vậy. Kiểm tra hai ngân sách độc lập để tránh biến kiểm soát chống spam thành khả năng hủy recovery của nạn nhân.

### 9.3. Tác động sau xác minh

Với request bị chặn tại bước nhạy cảm, xác minh không có password version mới, không đăng ký passkey/MFA mới, không cấp session có quyền đầy đủ và không thực hiện các thay đổi session ngoài policy.

Một recovery thành công hợp lệ vẫn phải tiêu thụ token và xử lý session theo thiết kế. Rate limit không thay thế xác minh danh tính, token dùng một lần hoặc kiểm tra purpose; một request nằm trong quota vẫn có thể phải bị từ chối.

### 9.4. Luồng hỗ trợ thủ công

Nếu nhân viên có đường khôi phục riêng, test quyền của actor, phạm vi tenant và ngân sách tác động trên subject. Đừng chỉ kiểm tra limiter của API công khai rồi mặc định đường hỗ trợ cũng được bảo vệ.

Trường hợp có override được phê duyệt cần bằng chứng quyền, lý do và audit phù hợp. Thêm một field `support=true` từ caller không được tự tạo quyền override.

## 10. Enumeration và khả dụng của người dùng hợp lệ

Limiter có thể làm lộ sự tồn tại của account nếu chỉ account thật mới chuyển sang trạng thái khác. So sánh hai subject tổng hợp, một tồn tại và một không tồn tại, với lịch sử request tương đương.

Cần so sánh status, cấu trúc body, header, cookie và những dấu hiệu công khai khác. Đối với thời gian phản hồi, lặp lại mẫu trong môi trường kiểm soát, báo phân bố và độ nhiễu; vài request có độ trễ gần nhau không chứng minh đã loại bỏ mọi kênh thời gian.

Ví dụ public message có thể tiếp tục là:

```text
Nếu thông tin phù hợp, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.
```

Hành vi delivery nội bộ vẫn phải được giới hạn. Một thông điệp chung không có tác dụng chống spam nếu mọi request đều tạo SMS thật.

### 10.1. Không biến giới hạn recovery thành khóa đăng nhập

Trong môi trường test, dùng một actor gây cạn ngân sách khởi tạo trên tài khoản mẫu, rồi kiểm tra chủ tài khoản vẫn đăng nhập được bằng credential hợp lệ nếu không có lý do độc lập để khóa. Kiểm tra session hợp lệ hiện có và những phương án recovery thay thế được policy cho phép.

Một mạng NAT có nhiều người dùng hợp lệ. Tạo nhóm người dùng khác nhau cùng một nguồn để đo ảnh hưởng của giới hạn nguồn. Mục tiêu không phải miễn mọi request cùng IP, mà chứng minh việc kết hợp nguồn, subject và rủi ro giữ được mức khả dụng đã định.

### 10.2. Không để request bị chặn giữ khóa quá lâu

Kiểm tra request bị chặn có giữ database lock, chiếm connection hoặc gọi provider trước khi trả kết quả hay không. Backoff thực hiện bằng cách giữ thread ngủ cho từng request có thể làm hệ thống cạn worker.

Nếu hệ thống dùng queue, phân biệt “đã nhận để xử lý” và “đã cấp quyền thực hiện”. Khi worker thực thi muộn, quyền và các điều kiện thời hạn phải được kiểm tra ở những điểm mà thiết kế yêu cầu; một quyết định cũ không mặc định cho phép mọi retry tương lai.

## 11. HTTP 429 và hướng dẫn thử lại

RFC 6585 định nghĩa 429 cho tình trạng quá nhiều request trong khoảng thời gian và cho phép dùng `Retry-After`; RFC không quy định hệ thống phải nhận diện người dùng hoặc đếm request theo khóa nào. Do đó, đúng status không chứng minh đúng scope. [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Ví dụ khi policy công khai cho phép trả 429:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 60

{"code":"RECOVERY_TEMPORARILY_LIMITED","message":"Vui lòng thử lại sau."}
```

`Retry-After` có thể biểu diễn bằng HTTP-date hoặc số giây chờ không âm. Test parser và giá trị theo dạng hệ thống đã chọn, kể cả biên làm tròn. [RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).

Thời gian chờ công khai không được trở thành kênh tiết lộ lịch sử quota riêng của subject trái với hợp đồng chống enumeration. Nếu có nhiều quota, test xem thời điểm được công bố có phản ánh đúng giới hạn cần chờ và có yêu cầu thêm điều kiện nào khác không.

`Retry-After` không phải lời hứa rằng request tiếp theo chắc chắn thành công: người khác có thể tiếp tục sử dụng ngân sách, bằng chứng có thể hết hạn hoặc dependency có thể lỗi. Client cần hiển thị trạng thái phù hợp thay vì tự động retry dồn dập.

Kiểm tra qua gateway và proxy để xác nhận phản hồi chặn không bị cache rồi áp cho caller khác. RFC 6585 không cho cache lưu phản hồi 429; chỉ kiểm tra header ở controller chưa chứng minh được hành vi toàn đường đi. [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

## 12. Ma trận kiểm thử có thể đưa vào suite

| ID | Thiết lập và thao tác | Điều kiện đạt |
| --- | --- | --- |
| RL-01 | Gọi primitive tuần tự với L lượt và lượt L+1 | Ngưỡng chính xác, request thừa không được admission |
| RL-02 | Gọi endpoint khi subject đã cạn ngân sách | Không có tác động nhạy cảm bị cấm |
| RL-03 | Nhiều nguồn cùng subject | Ngân sách subject không bị phân mảnh |
| RL-04 | Nhiều subject cùng nguồn | Ngân sách nguồn/tổng chi phí áp dụng đúng |
| RL-05 | Hai tenant trùng local ID | Không đụng khóa subject ngoài thiết kế |
| RL-06 | Biến thể định danh hợp lệ và header giả | Khóa dựa trên định danh, nguồn đáng tin |
| RL-07 | Gửi ở trước/đúng/sau biên thời gian | Khớp đúng thuật toán, độ phân giải và policy |
| RL-08 | Request bị chặn tiếp tục đến | Không gia hạn cửa sổ ngoài hợp đồng |
| RL-09 | Nhiều request mở cùng barrier | ALLOW và số phép kiểm tra không vượt ngân sách |
| RL-10 | Phân phối qua nhiều instance, rồi restart | Giữ phạm vi quota và sai số đã cam kết |
| RL-11 | Resend và tạo challenge mới | Không reset ngoài ý muốn ngân sách chống đoán |
| RL-12 | Store timeout trước/sau áp dụng | Xử lý unknown outcome đúng; không cấp quyền mù |
| RL-13 | Delivery retry hoặc queue phát lại | Không tạo tác động trùng ngoài hợp đồng |
| RL-14 | Account tồn tại/không tồn tại | Không khác biệt công khai trái yêu cầu |
| RL-15 | Nạn nhân có credential hợp lệ sau khi bị spam | Khả dụng đúng policy, không bị khóa do recovery spam |
| RL-16 | Request nhạy cảm bị throttle | Credential/session giữ đúng bất biến |
| RL-17 | Hết chu kỳ hoặc hoàn tất recovery | Dọn trạng thái và cấp lại quota theo vòng đời |
| RL-18 | Định danh ngẫu nhiên số lượng có kiểm soát | Số khóa, bộ nhớ, log và chi phí nằm trong giới hạn môi trường |

Các test không nhất thiết đều chạy ở cùng một tầng. Unit test phù hợp với phép tạo khóa và tính biên; integration test phù hợp với atomicity, TTL và fault injection; test xuyên hệ thống phù hợp với proxy, nhiều instance, queue và delivery.

## 13. Tổ chức dữ liệu và quan sát để test đáng tin

Mỗi test nên có namespace hoặc run ID riêng. Chỉ cleanup những khóa và bản ghi thuộc test đó; không xóa cả kho dùng chung để làm số đếm trở về không. Account, token, mã và provider đều dùng dữ liệu tổng hợp hoặc sandbox.

Metric tổng của một môi trường dùng chung thường không đủ để làm oracle chính xác vì request từ test khác cũng đóng góp. Nên có event test được gắn correlation ID hoặc truy vấn các bản ghi thuộc namespace của ca đang chạy. Correlation ID không phải khóa cấp quota và không được dùng làm cách vượt giới hạn.

Trong log và report, lưu case ID, policy version, instance, loại scope và kết quả admission. Không ghi raw token, OTP, mật khẩu, session cookie hoặc toàn bộ định danh cá nhân. Nếu cần một giá trị giả danh để đối chiếu, dùng cơ chế và phạm vi truy cập đã được thiết kế; không coi hash không khóa của email phổ biến là biện pháp che danh tính chắc chắn.

Cũng cần kiểm tra cardinality: nếu mỗi định danh chưa tồn tại tạo một khóa không có hạn hoặc mỗi request bị chặn tạo một metric label mới, chính limiter có thể làm cạn bộ nhớ. Bài test nên dùng số lượng hữu hạn đã định và quan sát cơ chế hết hạn, giới hạn dung lượng hoặc cơ chế bảo vệ tương ứng.

Chạy test đồng thời nhiều lần có ích để tăng khả năng bắt lỗi lịch thực thi, nhưng không thay thế việc tạo điểm va chạm rõ ràng. Một trăm lần PASS khi các request thực tế được gửi tuần tự chưa chứng minh đã đánh giá race condition.

## 14. Đọc và báo cáo kết quả

Một báo cáo có ích cần đủ dữ liệu để người khác hiểu điều đã được chứng minh:

```text
CASE: RL-09
POLICY: recovery-test-v1
TARGET: primitive admission, một scope subject
SETUP: capacity=5; cửa sổ còn hiệu lực; namespace biệt lập
TRAFFIC: 24 caller mở cùng barrier
TOPOLOGY: 2 application instance, cùng kho ngân sách
OBSERVED: allow=5; throttle=19; unavailable=0
SIDE_EFFECT_CHECK: chỉ 5 tác vụ được admission đi tới test sink
TIMEOUT_OR_EXCEPTION: 0
RESULT: PASS cho bất biến admission trong cấu hình được kiểm tra
```

Không ghi kết quả theo mẫu nếu chưa thực sự chạy test. Khi một test minh họa mới được viết hoặc mới kiểm tra ở một instance, báo rõ phạm vi đó. PASS của primitive không tự trở thành PASS cho endpoint, multi-region hoặc hành vi provider.

Ví dụ một lỗi cần mô tả cụ thể: “Với quota năm lượt trên subject, 24 request qua hai instance tạo tám delivery intent trong cùng cửa sổ; HTTP vẫn trả thông điệp chung.” Cách ghi này xác định tác động và điều kiện tái hiện rõ hơn “rate limit bị bypass”.

Sau khi sửa implementation, chạy lại ca tái hiện và các ca lân cận có liên quan: ngưỡng tuần tự, cạnh tranh, hết hạn, lỗi kho và khả dụng của người dùng hợp lệ. Các yêu cầu ngoài phạm vi test đã chạy cần được giữ là chưa được chứng minh.

## 15. Bài tập thực hành

**Tình huống A — Đúng 429 nhưng vẫn gửi SMS.** API gọi provider rồi mới hỏi limiter. Hãy viết oracle đếm số lần gọi provider và số intent đã commit. Xác định vị trí tạo lỗi, thứ tự admission cần được bảo vệ và cách chứng minh request bị chặn không còn tạo delivery mới.

**Tình huống B — Mỗi instance đều “đúng”.** Hai instance có bộ đếm riêng, mỗi bộ cho năm lượt trên cùng subject. Thiết kế test có routing xác nhận được, nêu kết quả tối đa quan sát trong mô hình đó và chỉ ra bất biến quota toàn hệ thống bị vi phạm.

**Tình huống C — Resend làm mới quyền đoán.** Một challenge có năm lần thử sai, nhưng resend xóa bộ đếm thử. Thiết kế chuỗi thử sai, resend và thử tiếp; phân biệt ngân sách của challenge với ngân sách subject và delivery để chọn điều kiện đạt đúng policy.

**Tình huống D — Kho đã tăng, client không biết.** Tạo timeout sau khi kho áp dụng admission. So sánh retry có idempotency với retry dùng request ID mới. Nêu dữ liệu nào cần quan sát để tránh vừa trừ lặp vừa hoàn lượt sai.

**Tình huống E — Nạn nhân bị chặn khôi phục.** Caller chưa xác thực làm cạn ngân sách khởi tạo. Kiểm tra đường đăng nhập bằng credential hiện có, sử dụng token hợp lệ đã cấp và phương án recovery thay thế theo policy. Xác định điều gì là chặn thao tác hợp lý và điều gì là khóa tài khoản ngoài yêu cầu.

Một bộ kiểm thử đạt mục tiêu khi gắn được mỗi ngân sách với ranh giới tin cậy, thuật toán thời gian, điểm quyết định và tác động cần bảo vệ. Kết quả quan trọng là số hành động thực sự được cấp quyền và trạng thái tài khoản sau đó, cùng bằng chứng người dùng hợp lệ vẫn có hành vi đúng theo thiết kế.
