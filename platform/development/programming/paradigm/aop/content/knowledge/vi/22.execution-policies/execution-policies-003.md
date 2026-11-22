# Thử lại và yêu cầu tính lặp an toàn của thao tác trong Aspect (AOP)

## 1. Mục tiêu và bài toán

**Retry (thử lại)** là một chính sách thực thi gọi lại một thao tác khi có lỗi được đánh giá là tạm thời. Với **Aspect-Oriented Programming (AOP)**, có thể đặt chính sách tại một `around advice` để nhiều phương thức cùng sử dụng các quy tắc về phân loại lỗi, số lần thử, thời gian chờ và ngân sách thời gian.

Tuy nhiên, tự động chạy lại một lời gọi mang rủi ro nghiêm trọng: lần trước **có thể đã thực hiện thành công hiệu ứng nghiệp vụ**, dù bên gọi vẫn nhận timeout, mất phản hồi hoặc ngoại lệ. Nếu lần gọi tiếp theo tạo thêm giao dịch, gửi thêm email hoặc trừ tiền thêm lần nữa, cơ chế retry đã thay đổi ý nghĩa nghiệp vụ.

Bài học giúp bạn:

- Phân biệt **retry**, **idempotency (tính lặp an toàn)**, **duplicate suppression** và bảo đảm **at-most-once / at-least-once / effectively-once**.
- Xác định lỗi nào có thể thử lại, lỗi nào cần dừng, và giới hạn retry bằng `maxAttempts`, backoff, jitter và deadline.
- Thiết kế advice bao quanh `proceed()` mà không làm mất nguyên nhân lỗi, không gọi lại tác vụ không an toàn và không nhân bội retry giữa các tầng.
- Thiết kế **idempotency key** và nơi lưu trạng thái để chịu được lời gọi trùng, request đồng thời, crash và kết quả không rõ ràng.
- Hiểu quan hệ của retry với giao dịch, API ngoài, message handler, luồng bất đồng bộ và observability.
- Viết và kiểm thử một interceptor AOP bằng Java 17.

Phạm vi là **AOP nói chung**: join point, pointcut, around advice, weaving hoặc proxy interception, không phụ thuộc một thư viện AOP cụ thể. Chi tiết API dùng để cài đặt advice có thể khác nhau, nhưng nguyên tắc về side effect và ranh giới trách nhiệm không đổi.

## 2. Ba khái niệm phải tách biệt

### 2.1. Retry không có nghĩa thao tác an toàn

Retry chỉ điều khiển việc **gọi lại**:

```text
caller -> advice -> operation
                  <- lỗi tạm thời
                  -> operation (lần nữa)
                  <- thành công / lỗi
```

Với tác vụ đọc dữ liệu hoặc tính toán thuần túy, thử lại thường dễ kiểm soát hơn. Với một lệnh ghi dữ liệu, tính an toàn của lần thử sau tùy vào **hợp đồng nghiệp vụ và thiết kế trạng thái**, không được suy ra chỉ từ kiểu ngoại lệ.

### 2.2. Idempotency là tính chất của kết quả tác động

Một thao tác `f` được gọi là **idempotent** khi áp dụng lặp lại có cùng hiệu quả quan sát được trên trạng thái mục tiêu như áp dụng một lần, với cùng dữ liệu/hợp đồng:

```text
f(f(state, command), command) = f(state, command)
```

Đây là mô hình khái niệm; phép so sánh cụ thể phải xác định cái gì được xem là **hiệu quả nghiệp vụ**. Ví dụ:

| Thao tác | Có an toàn khi gọi lại không? | Giải thích |
|---|---|---|
| Gán trạng thái tài khoản thành `ACTIVE` | Thường có, nếu hợp đồng và điều kiện ổn định | Gán cùng giá trị nhiều lần có thể không đổi trạng thái cuối |
| Tăng số dư thêm 100 | Không theo mặc định | Hai lần tăng tạo kết quả khác một lần |
| Tạo đơn hàng với ID mới mỗi lần | Không | Có thể tạo hai đơn |
| Tạo đơn với khóa nghiệp vụ duy nhất, trả lại kết quả cũ cho yêu cầu trùng | Có thể có | Cần kiểm soát cạnh tranh, payload, transaction và kho khóa |
| Đọc bản ghi | Thường an toàn về side effect | Nhưng kết quả có thể đổi giữa hai lần do cập nhật đồng thời |
| Gửi email | Không mặc định | Retry sau timeout có thể gửi hai email |

**Idempotent không đồng nghĩa trả về cùng mọi byte trong mọi lần gọi.** Ví dụ việc gán cùng trạng thái có thể trả timestamp khác nhau. Nếu API cam kết replay **cùng một kết quả** cho khóa cũ, phải quy định cụ thể cách lưu và trả kết quả trước.

Ngoài ra, một thao tác có trạng thái cuối giống nhau có thể vẫn phát hai event, hai email hoặc hai phí xử lý. Khi nói “lặp an toàn”, hãy xác định cả **side effect ngoài cơ sở dữ liệu**.

### 2.3. Các ngữ nghĩa giao hàng và “exactly once”

- **At-most-once:** một yêu cầu không bị thực thi quá một lần nhưng có thể bị mất, không có thử lại; không bảo đảm thành công.
- **At-least-once:** có thể lặp lại để tăng cơ hội hoàn tất; bên xử lý phải sẵn sàng tiếp nhận trùng.
- **Effectively-once:** nhiều lần tiếp nhận có thể xảy ra, nhưng cơ chế idempotency/deduplication khiến *hiệu ứng nghiệp vụ được bảo vệ* như thực thi một lần, trong phạm vi các giả định đã xác định.
- **Exactly-once:** cam kết mạnh, phụ thuộc hệ thống, giao thức, định nghĩa hiệu ứng và miền lỗi; một advice retry đơn thuần **không thể** đảm bảo điều đó với mọi cơ sở dữ liệu và dịch vụ bên ngoài.

Không suy diễn: “gọi lại cùng tham số” ⇒ “chỉ xử lý một lần”; “đã nhận HTTP thành công” ⇒ “không bao giờ có duplicate”; “có unique key” ⇒ “mọi side effect bên ngoài đều đúng một lần”.

## 3. Lỗi nào đáng để thử lại?

Khi một lời gọi thất bại, advice cần **phân loại nguyên nhân** và trạng thái hoàn tất. Một số nhóm:

| Nhóm lỗi | Ví dụ | Quyết định mặc định |
|---|---|---|
| Có khả năng tạm thời | Kết nối bị reset, dịch vụ báo quá tải, tranh chấp khóa có thể thử lại | Có thể retry **nếu** hợp đồng thao tác an toàn và còn ngân sách |
| Có yêu cầu retry sau khoảng cụ thể | Thông báo rate limit cùng thời điểm `Retry-After` hợp lệ | Cân nhắc chờ theo yêu cầu, trong deadline còn lại |
| Vĩnh viễn | Input không hợp lệ, thiếu quyền, trạng thái nghiệp vụ không cho phép | Không retry |
| Lỗi lập trình | `NullPointerException`, lỗi invariant, loại dữ liệu sai | Không retry mặc định; sửa nguyên nhân |
| Không rõ đã commit hay chưa | Timeout sau khi gửi lệnh ghi, mất phản hồi sau commit | **Chỉ retry khi có idempotency protocol** hoặc bước truy vấn trạng thái đáng tin |
| Hủy/gián đoạn | Caller cancel, deadline hết, thread interrupt | Dừng theo hợp đồng, giữ nguyên tín hiệu hủy |
| Thiếu tài nguyên kéo dài | Hệ thống quá tải hàng loạt | Có thể dùng backpressure/circuit-breaker; retry vô hạn làm nặng thêm tình hình |

Không nên bắt mọi `Exception` hoặc `Throwable` và retry vô điều kiện. `Error` nghiêm trọng như lỗi tài nguyên JVM không nên bị che bằng vòng lặp. Tương tự, không nên retry chỉ dựa vào câu chữ của `getMessage()`; dùng loại lỗi, trạng thái đã chuẩn hóa hoặc predicate được kiểm thử.

**Một lỗi timeout có ý nghĩa mơ hồ:** client ngừng chờ không chứng minh server chưa xử lý xong. Đây chính là lý do các lệnh ghi có side effect cần khóa idempotency hoặc cơ chế hỏi lại trạng thái có định danh.

## 4. Bốn giới hạn của chính sách retry

### 4.1. Số lần thử tối đa

`maxAttempts = 3` thường nghĩa là **1 lần ban đầu + tối đa 2 lần gọi lại**, không phải 3 lần retry sau lần đầu. Đặt tên rõ trong cấu hình và test off-by-one. Có thể thêm giới hạn số lần retry theo loại lỗi.

### 4.2. Exponential backoff có giới hạn trên

Lịch chờ đơn giản:

```text
delay(attempt) = min(maxDelay, initialDelay * 2^(attempt - 1))
```

Với `initialDelay = 100 ms` và `maxDelay = 2 s`, những khoảng chờ sau lần thất bại thứ 1, 2, 3 lần lượt là 100 ms, 200 ms, 400 ms (trước khi chạm trần). Triển khai cần chống overflow khi nhân/lũy thừa và chống cấu hình âm.

### 4.3. Jitter để tránh retry đồng loạt

Nếu hàng nghìn client cùng lỗi rồi cùng đợi chính xác 100 ms, chúng có thể đồng loạt gọi lại, tạo **thundering herd**. Jitter phân tán thời điểm thử:

```text
cappedDelay = min(maxDelay, initialDelay * 2^retryIndex)
sleepTime  = random(0, cappedDelay)  // full jitter
```

Một số hệ thống dùng equal jitter hoặc decorrelated jitter. Chọn công thức theo workload và quan sát hiệu quả; không nhầm giá trị ngẫu nhiên với cam kết retry luôn diễn ra sau đúng một khoảng cố định.

### 4.4. Deadline và retry budget

Ngoài số lần, dùng một deadline **end-to-end**. Trước mỗi lần thử và trước khi ngủ, kiểm tra thời gian còn lại. Cần tính cả thời gian của từng attempt, DNS, network, xử lý và backoff. Chỉ kiểm tra deadline trước lần đầu nhưng không hủy request đang chạy có thể khiến tổng thời gian vượt rất xa giới hạn.

Với đồng hồ trong JVM, dùng `System.nanoTime()` cho khoảng thời gian trôi qua (không dùng đồng hồ lịch để đo duration). Một timeout cấu hình trên client I/O hoặc cancellation riêng vẫn cần thiết để attempt đơn lẻ không chặn quá lâu.

**Budget cấp hệ thống:** hạn chế phần trăm truy cập dành cho retry, số retry đồng thời và kích thước queue để tránh khuếch đại một sự cố chung.

## 5. Advice triển khai retry như thế nào?

Một `around advice` lý tưởng bao quanh **đơn vị thực thi có thể lặp lại**, tức có thể gọi lại `proceed()` nếu cơ chế interception cho phép. Mỗi lần gọi lại là một attempt, nhưng lời gọi nghiệp vụ ở ngoài vẫn là **một logical operation**.

```text
Client
   |
   v
[Retry around advice]
   |-- attempt 1 -> proceed() -> temporary failure
   |-- backoff / budget check
   |-- attempt 2 -> proceed() -> success
   v
Result to client
```

Pseudocode độc lập công cụ:

```text
around(call):
    policy = lookupPolicy(call.method)
    verifyOperationIsEligibleForRetry(call, policy)
    deadline = start + policy.totalTimeout

    for attempt = 1 .. maxAttempts:
        ensureNotCancelledOrInterrupted()
        ensureWithinDeadline()
        try:
            return proceed()                    // gọi tác vụ gốc
        catch error:
            if !isRetryable(error) or attempt == maxAttempts:
                throw error
            wait = calculateBackoffWithJitter(attempt)
            if wait cannot fit in remaining deadline:
                throw error or policy timeout
            waitCancellable(wait)

    unreachable
```

Đây là **pseudocode**, không phải Java biên dịch được. Những điểm phải quy định:

- `proceed()` có được gọi lại nhiều lần trong công cụ AOP đang dùng hay không? Một số API/interceptor không cho phép replay lời gọi tùy ý, hoặc chỉ cho phép gọi một lần.
- **Các đối số có thể dùng lại được không?** Một `InputStream` đã đọc, iterator, publisher một lần hoặc request body không còn replay được sẽ làm attempt sau khác attempt đầu.
- **Định danh logic** và idempotency key phải giữ nguyên giữa các attempt; không tạo khóa mới mỗi lần.
- Nếu `proceed()` có thể thay đổi args, cần xác định có tạo bản sao an toàn hay không và không làm mất identity/correlation.
- Việc bắt lỗi để retry không được nuốt exception gốc, biến lỗi nghiệp vụ thành thành công giả hoặc vô tình gọi handler lỗi nhiều lần.
- Không nên sleep trên luồng event loop; lựa chọn scheduler bất đồng bộ với continuation thích hợp.

Với logging/tracing, ghi rõ **logical operation** và **attempt**. Ví dụ một span logic chứa các event `attempt=1,2`; nếu hệ thống dùng span con cho từng attempt, quan hệ giữa chúng cần giữ nhất quán. Không đếm hai attempt thành hai giao dịch người dùng đã hoàn thành.

## 6. Khi nào yêu cầu idempotency key?

Một **idempotency key** là danh tính ổn định của một yêu cầu nghiệp vụ logic, dùng để nhận ra các lần gửi lại. Khóa thường do client tạo trước lần gửi đầu và dùng lại *chính xác* cho những attempt/retry cùng một yêu cầu.

Một hợp đồng chặt phải trả lời:

1. **Phạm vi khóa:** key có duy nhất theo tenant, người dùng, operation, namespace và khoảng thời gian nào? Cùng key của hai tenant khác nhau không được vô tình va nhau.
2. **Ràng buộc payload:** cùng key nhưng tham số khác là một lỗi xung đột, không được trả nhầm kết quả của một yêu cầu khác. Có thể lưu fingerprint/canonical representation an toàn theo schema đã quy định.
3. **Thời gian giữ:** lưu khóa bao lâu? TTL phải phù hợp thời gian retry, delay queue và thời gian xử lý; nếu hết hạn quá sớm, retry muộn có thể gây side effect mới.
4. **Trạng thái:** đang thực hiện, đã thành công, thất bại đã quyết định, hay không rõ commit. Mỗi trạng thái có chính sách replay khác nhau.
5. **Kết quả trả lại:** trả cùng response, redirect đến trạng thái đã có hay trả tín hiệu `IN_PROGRESS`? Điều này thuộc hợp đồng API, không thể suy ra chung.
6. **Tương tranh:** hai request cùng key tới cùng lúc phải được khóa hoặc phân xử **nguyên tử** để không cùng thực hiện hiệu ứng.

Một bảng trạng thái minh họa:

| Trạng thái lưu theo key | Yêu cầu trùng đúng fingerprint | Ý nghĩa |
|---|---|---|
| `ABSENT` | Có thể giành quyền xử lý | Chưa thấy yêu cầu hoặc bản ghi đã hết hạn |
| `IN_PROGRESS` | Trả đang xử lý hoặc chờ có deadline | Tránh hai worker đồng thời tạo side effect |
| `SUCCEEDED` | Replay kết quả/định danh đã lưu | Không gọi lại phần tạo hiệu ứng |
| `FAILED_FINAL` | Replay lỗi cuối theo hợp đồng | Không tái thực thi lỗi vĩnh viễn |
| `UNKNOWN` | Đối soát trước khi quyết định | Chưa biết external side effect đã commit hay chưa |

Nếu lưu fingerprint, cần tránh đưa payload nhạy cảm vào kho key/log. Việc hash có bảo vệ quyền riêng tư hay không phụ thuộc miền dữ liệu và cách sử dụng; chọn thuật toán/phương án lưu phù hợp với loại dữ liệu. Khóa cũng cần giới hạn độ dài, xác thực cú pháp và không đưa dữ liệu bí mật thô vào metric label.

## 7. Lưu idempotency bền vững và xử lý chạy đồng thời

Một bộ nhớ `ConcurrentHashMap` có thể minh họa duplicate suppression trong **một tiến trình đang chạy**, nhưng sẽ mất nội dung khi restart và không phối hợp giữa nhiều instance. Để bảo vệ thao tác có giá trị cao, nơi lưu khóa phải có tính bền vững và ràng buộc nguyên tử phù hợp: unique constraint trong database, record trạng thái transactional, hoặc dịch vụ chuyên trách đáp ứng cùng bảo đảm.

Mô hình thường gặp khi **side effect nằm cùng cơ sở dữ liệu**:

```text
BEGIN TRANSACTION
  INSERT (tenant, operation, idempotency_key, payload_fingerprint, status)
  với UNIQUE(tenant, operation, idempotency_key)

  nếu key đã tồn tại:
      xác minh fingerprint
      lấy trạng thái / kết quả
      không thực thi thêm side effect

  nếu giành được key:
      ghi hiệu ứng nghiệp vụ
      lưu kết quả / trạng thái hoàn tất
COMMIT
```

Đây là kiến trúc khái niệm; transaction và unique constraint cần được thiết kế đúng mức cô lập của DB. Khi lưu key và effect **cùng một transaction**, sự kiện commit của hai thành phần có thể gắn với nhau. Nếu dùng hai kho lưu khác nhau hoặc gọi một hệ thống ngoài transaction, mô hình này không tự tạo nguyên tử xuyên biên.

Để giải quyết hai request cùng key, một mẫu phổ biến là **insert với unique constraint**, rồi xử lý xung đột bằng cách tra trạng thái và kiểm tra fingerprint; hoặc đặt row lock/lease có fencing token nếu công việc kéo dài. Cẩn trọng với trạng thái `IN_PROGRESS` bị bỏ lại sau crash: cần quy trình recovery, không đơn thuần xóa và chạy lại nếu có thể đã commit.

**Không coi cache là nguồn đúng duy nhất** khi sự cố mất cache có thể tạo giao dịch lặp. Nếu yêu cầu kinh doanh chỉ chịu được “best effort”, tài liệu phải nói rõ giới hạn này.

### 7.1. Commit đã xảy ra nhưng phản hồi mất

```text
Caller                   Service                   Database
  | ---- request(key=K) ---> |                         |
  |                          | ---- COMMIT order ----> |
  |          X mất phản hồi  |                         |
  | -- retry (key=K) ------> |                         |
  | <-- replay receipt ----- | (không tạo order lần nữa)|
```

Đây là tình huống điển hình mà retry “thành công” nếu có idempotency nhưng gây duplicate nếu không có. Nếu client tự sinh khóa **mới** mỗi attempt, server không biết hai request tương ứng cùng một logical operation.

### 7.2. Hiệu ứng bên ngoài cơ sở dữ liệu

Một transaction DB không thể rollback email đã gửi hoặc lệnh thanh toán mà nhà cung cấp đã chấp nhận. Cần phối hợp thêm một hoặc nhiều kỹ thuật tùy hệ thống:

- **Idempotency ở đích:** truyền cùng khóa cho dịch vụ bên ngoài nếu dịch vụ đó hỗ trợ và có hợp đồng xác định.
- **Transactional outbox:** ghi bản ghi tác vụ gửi đi cùng transaction nghiệp vụ; dispatcher có thể gửi lại, còn consumer/đích phải chống xử lý trùng.
- **Inbox/deduplication của consumer:** ghi định danh message đã xử lý và effect với ranh giới transaction phù hợp.
- **Đối soát trạng thái:** khi timeout sau khi gửi, tra cứu bằng reference duy nhất trước khi quyết định gửi lại.
- **Compensation:** nếu không thể bảo đảm hiệu ứng một lần, thiết kế nghiệp vụ bù trừ có kiểm soát; bù trừ không đồng nghĩa rollback nguyên tử.

Các kỹ thuật này thường tạo bảo đảm “hiệu ứng một lần” **trong phạm vi cụ thể**, không phải đúng một lần tuyệt đối trên mọi hệ thống.

## 8. Ví dụ Java 17: AOP retry và khóa idempotency

Chương trình sau dùng **JDK dynamic proxy** để tạo around interceptor cho lời gọi thông qua interface. Annotation `@Retryable` cấu hình tổng số attempts; interceptor chỉ retry loại lỗi `TemporaryFailure`. Một `Store` mô phỏng ghi kết quả với idempotency key, cố tình ném lỗi **sau khi đã ghi** ở lần gọi đầu để mô phỏng phản hồi bị mất.

Để output dễ kiểm chứng, `Sleeper` được tiêm vào và trong `main` chỉ **in thời gian backoff**, không ngủ thật. Đó là lựa chọn của demo, không phải cách quản lý thời gian khi vận hành production.

Lưu toàn bộ chương trình trong **RetryAspectDemo.java**:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class RetryAspectDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @interface Retryable {
        int maxAttempts() default 3;
    }

    static final class TemporaryFailure extends RuntimeException {
        TemporaryFailure(String message) { super(message); }
    }

    @FunctionalInterface
    interface Sleeper {
        void pause(long millis) throws InterruptedException;
    }

    interface Command {
        @Retryable(maxAttempts = 3)
        String execute(String idempotencyKey);
    }

    static final class Store implements Command {
        final ConcurrentHashMap<String, String> receipts = new ConcurrentHashMap<>();
        final AtomicInteger invocations = new AtomicInteger();
        final AtomicInteger effects = new AtomicInteger();

        public String execute(String idempotencyKey) {
            int number = invocations.incrementAndGet();
            String receipt = receipts.computeIfAbsent(idempotencyKey,
                    key -> "receipt-" + effects.incrementAndGet());
            if (number == 1) {
                throw new TemporaryFailure("acknowledgment lost");
            }
            return receipt;
        }
    }

    static Object invoke(Method method, Object target, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static <T> T withRetry(Class<T> api, T target, Sleeper sleeper) {
        return api.cast(Proxy.newProxyInstance(
                api.getClassLoader(), new Class<?>[] { api },
                (proxy, method, args) -> {
                    Retryable policy = method.getAnnotation(Retryable.class);
                    if (policy == null) return invoke(method, target, args);
                    int maxAttempts = policy.maxAttempts();
                    if (maxAttempts < 1) throw new IllegalArgumentException("maxAttempts");
                    for (int attempt = 1; ; attempt++) {
                        try {
                            Object result = invoke(method, target, args);
                            System.out.println("attempt=" + attempt + " success");
                            return result;
                        } catch (TemporaryFailure ex) {
                            System.out.println("attempt=" + attempt + " transient");
                            if (attempt >= maxAttempts) throw ex;
                            long delay = Math.min(100L, 10L << Math.min(attempt - 1, 6));
                            sleeper.pause(delay);
                        }
                    }
                }));
    }

    public static void main(String[] args) {
        Store store = new Store();
        Command command = withRetry(Command.class, store,
                millis -> System.out.println("backoff_ms=" + millis));
        System.out.println("result=" + command.execute("request-42"));
        System.out.println("invocations=" + store.invocations.get());
        System.out.println("side_effects=" + store.effects.get());
        System.out.println("same_key=" + command.execute("request-42"));
        System.out.println("side_effects_after_same_key=" + store.effects.get());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 RetryAspectDemo.java
java RetryAspectDemo
```

Kết quả chính xác:

```text
attempt=1 transient
backoff_ms=10
attempt=2 success
result=receipt-1
invocations=2
side_effects=1
attempt=1 success
same_key=receipt-1
side_effects_after_same_key=1
```

Giải thích theo thứ tự:

1. `execute("request-42")` lần đầu dùng `computeIfAbsent` để ghi `receipt-1` và tăng số hiệu ứng lên 1, sau đó cố tình ném `TemporaryFailure`.
2. Advice bắt được lỗi thuộc loại cho phép retry; vì còn lượt, nó tính backoff 10 ms và gọi lại cùng `args`, trong đó khóa vẫn là `request-42`.
3. Lần thứ hai trả lại `receipt-1` đã tồn tại. Tổng lượt gọi là 2 nhưng số lần tạo hiệu ứng chỉ là 1.
4. Khi client gọi lại cùng khóa lần nữa, interceptor bắt đầu một logical invocation mới và có một attempt thành công; bộ lưu giữ khóa vẫn trả receipt cũ. Số hiệu ứng không tăng.

**Giới hạn bắt buộc của ví dụ:** bộ `ConcurrentHashMap` chỉ ở trong một JVM, không bền vững, chưa kiểm tra fingerprint khi cùng key nhưng khác payload, chưa xét trạng thái đang xử lý kéo dài, crash hoặc giao dịch ngoài. `computeIfAbsent` minh họa đồng bộ hóa việc tạo value trong map cho cùng key ở tình huống thành công, **không** thay thế transaction với database và dịch vụ ngoài. `TemporaryFailure` được tạo có chủ ý; trong thực tế một số timeout không có dấu hiệu chắc chắn về việc commit. Việc tiêm `Sleeper` fake có nghĩa demo kiểm tra luồng retry và phép tính delay, không kiểm tra đồng hồ thực hay hủy task.

Ngoài ra, handler minh họa chỉ áp dụng cho method annotation đặt trên interface `Command`; proxy không tự intercept lời gọi nội bộ bên trong đối tượng `Store`. `Method.invoke` có thể gói ngoại lệ nghiệp vụ bằng `InvocationTargetException` và hàm `invoke` đã tháo lớp này để policy kiểm tra đúng loại lỗi gốc.

## 9. Thứ tự advice và phạm vi giao dịch

Khi kết hợp retry với authorization, transaction, timeout, circuit breaker, tracing và audit, **thứ tự bọc** quyết định điều gì thực sự được chạy lại.

Hai cách đặt retry với transaction:

```text
A. Retry ngoài transaction (thường phù hợp nếu cần transaction mới mỗi attempt)
   Retry
      -> Begin Transaction
          -> Business Operation
      -> Commit/Rollback
   (khi lỗi được phép: attempt kế tiếp bắt đầu transaction mới)

B. Transaction ngoài retry
   Begin Transaction
      -> Retry
          -> Business Operation (nhiều lần trong cùng transaction)
   Commit/Rollback
```

Ở phương án B, một lỗi có thể khiến transaction hiện tại bị đánh dấu rollback-only hoặc mất khả năng tiếp tục; retry ngay trong cùng transaction có thể vô nghĩa hoặc nguy hiểm. Trong phương án A, cần chắc rằng sau rollback mọi resource/connection/lock của attempt cũ đã được giải phóng và thao tác thực sự có thể chạy lại. **Không có thứ tự nào đúng cho mọi môi trường**: hợp đồng transaction, loại lỗi và khả năng quan sát commit quyết định.

Các khía cạnh phối hợp khác:

- **Authorization:** mỗi attempt cần tuân thủ ngữ cảnh quyền hợp lệ; không cho retry để né kiểm tra quyền. Nếu auth context hết hạn, chính sách làm mới hoặc dừng phải rõ.
- **Rate limit:** quyết định giới hạn theo logical request hay từng attempt; mỗi attempt vẫn tiêu thụ tài nguyên thật.
- **Circuit breaker:** có thể đặt ngoài để bảo vệ logical call hoặc trong để chặn từng attempt, tùy mục đích đo/cắt. Tránh circuit bị đánh giá sai vì đếm mọi lần lặp thành request độc lập.
- **Timeout:** tổng deadline nằm ngoài retry; timeout từng attempt nằm phía trong. Nếu chỉ có timeout mỗi attempt, thời gian end-to-end có thể quá lớn.
- **Tracing/logging:** giữ một correlation/idempotency key cố định, thêm attempt index; không ghi secret của request như idempotency key vào nhãn metric có cardinality cao.
- **Audit:** “yêu cầu đã được tiếp nhận” khác “attempt đã thử” và “hiệu ứng đã commit”. Cần phân biệt để không nhân đôi audit nghiệp vụ.

Tránh hiện tượng **retry amplification**: tầng HTTP client retry 3 lần, tầng domain retry 3 lần và message worker retry 3 lần có thể dẫn tới tới 27 nỗ lực phía dưới cho một yêu cầu ban đầu. Cần thiết kế quyền sở hữu retry theo tầng, hoặc truyền deadline và retry budget dùng chung.

## 10. Bất đồng bộ, hủy và scheduling

Một around advice đồng bộ có thể nhận về `CompletableFuture<T>` **ngay lập tức** trước khi công việc thật hoàn tất. Nếu nó chỉ catch ngoại lệ từ `proceed()` thì sẽ không bắt được một future hoàn thành exceptionally sau đó.

Cần phân biệt:

1. **Retry quá trình tạo future:** `proceed()` ném lỗi ngay trước khi trả handle; có thể áp dụng vòng lặp đồng bộ theo chính sách.
2. **Retry công việc trong future:** future hoàn tất với lỗi; muốn retry phải có **factory** tạo attempt mới hoặc khả năng gọi lại thao tác theo đúng hợp đồng, gắn callback xử lý lỗi và lập lịch lần sau.
3. **Retry của publisher/stream lười:** công việc có thể bắt đầu lúc subscribe, retry có thể là resubscribe; stream có side effect hoặc đã phát một phần dữ liệu nên không đương nhiên lặp an toàn.
4. **Retry message handler:** phải xét cơ chế acknowledge/nack, visibility timeout, redelivery và idempotency ở consumer.

Trong thực thi bất đồng bộ, không dùng `Thread.sleep` trên event loop. Dùng scheduler với timer không chặn, kiểm soát deadline và hủy. Nếu caller cancel, cần quyết định có cancel attempt đang chạy không, có ngăn task đã lên lịch kế tiếp không, và side effect đã commit được đối soát thế nào.

**Tác vụ bị hủy không có nghĩa side effect đã rollback.** Cancellation thường chỉ là yêu cầu hủy; một lời gọi network hoặc bước commit có thể đang tiếp diễn. Vẫn cần idempotency/reconciliation khi kết quả không rõ.

Khi truyền trace/security context qua scheduler hoặc executor, phải chụp đúng ngữ cảnh cho từng attempt và khôi phục tại luồng chạy. Chuyển sang luồng khác không tự sao chép mọi `ThreadLocal`. Không giữ context của request cũ trong pool sau khi attempt kết thúc.

## 11. Tiêu chuẩn retry trước lời gọi có side effect

Để đánh giá một join point có thể gắn retry hay không, hãy lần lượt trả lời:

**Một: đây là loại thao tác gì?** Tính toán thuần, đọc, cập nhật cùng giá trị, tăng số lượng, tạo tài nguyên, gửi thông báo hay kết hợp nhiều bước? Có file/stream/iterator tiêu thụ một lần hay input không replay được không?

**Hai: khi lỗi, có thể đã xảy ra hiệu ứng chưa?** Phân biệt thất bại trước khi gửi request, thất bại có phản hồi rõ ràng chưa xử lý, thất bại sau commit, và timeout không rõ. Chỉ thông tin phía caller không đủ thì yêu cầu khóa idempotency hoặc đối soát.

**Ba: ai tạo và giữ khóa?** Khóa phải tồn tại xuyên attempt, retry qua network/queue và process restart khi hợp đồng đòi hỏi; không sinh key mới trong retry advice. Nếu key có nguồn từ dữ liệu người dùng, kiểm tra namespace/ownership để tránh va chạm giữa các principal.

**Bốn: bên nhận có deduplicate thực sự không?** Unique constraint, bản ghi kết quả, kiểm tra fingerprint và xử lý đồng thời phải có hành vi rõ. Nếu đích không hỗ trợ, retry write không được tự mặc định an toàn.

**Năm: ngân sách và cách dừng?** Số attempt, deadline, điều kiện lỗi, jitter, quota và cancellation được test cụ thể. Không “cứ thử đến khi thành công”.

**Sáu: trạng thái kết thúc nào được báo?** Phải phân biệt success, failed-final, cancelled và outcome-unknown. Không nên phát “thành công” chỉ vì một advice đã gửi lại request.

## 12. Các lỗi thiết kế phổ biến

| Dấu hiệu | Nguyên nhân sâu | Cách xử lý |
|---|---|---|
| Đơn hàng bị tạo đôi | Retry sau timeout với key khác hoặc không có key | Khóa logic ổn định, dedup bền vững ở nơi tạo effect |
| Trừ tiền hai lần | Thao tác tăng/chuyển tiền không idempotent | Idempotency contract phía dịch vụ thanh toán, tra cứu trạng thái |
| Cùng key nhưng nội dung khác nhận kết quả cũ | Không lưu/kiểm tra fingerprint | Trả lỗi xung đột, bắt buộc cùng request logic |
| Hai worker cùng xử lý một key | Chỉ check-then-insert thiếu tính nguyên tử | Unique constraint/locking và state transition có kiểm soát |
| Retry vô hạn và tạo tải đột biến | Không giới hạn attempt, deadline và backoff | Budget + capped backoff + jitter + breaker/rate limit |
| Không retry dù future lỗi | Advice chỉ catch lỗi khi tạo handle | Quan sát completion và tạo attempt mới theo hợp đồng |
| Retry một giao dịch đã hỏng | Transaction bao ngoài mọi attempt | Cân nhắc transaction riêng từng attempt |
| Retry che lỗi nghiệp vụ | Catch-all và phân loại sai | Chỉ retry whitelist transient, propagate nguyên nhân cuối |
| Chặn thread event loop | Backoff bằng sleep đồng bộ | Scheduler bất đồng bộ/cancellable |
| Mỗi lần thử tạo một trace logic riêng | Interceptor không giữ correlation | Giữ logical operation ID, thêm attempt metadata |
| Lỗi không thể tái hiện | Random jitter không kiểm soát trong test | Tiêm clock/sleeper/random, dùng lịch giả xác định |
| Đã retry nhưng không thể replay input | Stream/file/iterator dùng một lần | Tạo nguồn có thể phát lại hoặc dừng retry |

## 13. Kiểm thử trước khi đưa vào hệ thống

Các test quan trọng cần mô phỏng **ranh giới thất bại thực tế**:

1. **Transient trước side effect:** lần 1 thất bại, lần 2 thành công; assert số attempts, delay và kết quả.
2. **Lỗi vĩnh viễn:** dữ liệu không hợp lệ/không có quyền; assert chỉ một attempt, bảo toàn exception.
3. **Hết maxAttempts:** mọi lần đều lỗi được phép; assert dừng đúng mốc và trả lỗi cuối theo hợp đồng.
4. **Timeout sau commit:** ghi hiệu ứng thành công rồi mất response; gửi lại **cùng key**; assert không tăng số hiệu ứng.
5. **Cùng key nhưng payload khác:** phải trả lỗi xung đột, không tái sử dụng kết quả sai.
6. **Cạnh tranh:** hai hoặc nhiều worker gửi cùng key đồng thời; assert chỉ một worker thắng quyền tạo effect.
7. **Crash/restart:** mất process sau commit nhưng trước trả response; storage bền vững vẫn replay/đối soát được.
8. **TTL và retry trễ:** xác minh chính sách hết hạn và cửa sổ bảo vệ; không để việc dọn khóa âm thầm tạo duplicate trong khoảng cần bảo đảm.
9. **Tổng deadline:** attempt lâu + backoff không vượt budget được hứa ở lớp caller; timeout từng attempt có hiệu lực.
10. **Cancel/interrupt:** không phát thêm attempt sau hủy; thread interrupt không bị nuốt.
11. **Nested retries:** mô phỏng nhiều tầng, assert tải tối đa không bùng nổ.
12. **Async future:** exception xảy ra *sau* khi trả handle; wrapper thật sự quan sát completion, không báo thành công sớm.
13. **Nhiều side effect:** DB, outbox, message và API ngoài đều có thử nghiệm duplicate phù hợp.
14. **Metrics và audit:** thử lại tạo metric attempt, nhưng số logical operation hoặc business effect không bị đếm sai.

Đối với Java, dùng clock/scheduler/sleeper giả để test điều kiện dừng mà không cần chờ thực tế. Với concurrency test, dùng `CountDownLatch` hoặc barrier để tạo cuộc đua ổn định thay vì trông chờ `Thread.sleep`. Phân biệt test chứng minh đúng trong một JVM với test hệ thống nhiều instance, crash recovery hoặc network uncertainty.

## 14. Danh sách quyết định cho một retry advice

- [ ] Xác định rõ tập pointcut và kiểu phương thức mà advice thực sự intercept.
- [ ] Chỉ bật retry cho phương thức có hợp đồng replay rõ, hoặc có idempotency/đối soát đáng tin.
- [ ] Khóa idempotency được giữ nguyên giữa mọi attempt của cùng logical operation.
- [ ] Phân loại transient/permanent/unknown outcome bằng tiêu chí rõ và có test.
- [ ] `maxAttempts` (gồm lần đầu), delay, jitter, tổng deadline, timeout mỗi attempt và cancellation có giới hạn.
- [ ] Không retry tự động stream một lần, non-repeatable input hoặc lỗi nghiệp vụ vĩnh viễn.
- [ ] Nơi dedup kiểm tra fingerprint và xử lý hai request cùng key nguyên tử.
- [ ] Idempotency record và hiệu ứng nghiệp vụ ở ranh giới transaction phù hợp; hiệu ứng ngoài phải có cơ chế riêng.
- [ ] Thứ tự retry/transaction/timeout/tracing được kiểm thử theo từng attempt.
- [ ] Future, publisher và message handler dùng đúng tín hiệu hoàn tất và mô hình scheduling.
- [ ] Không biến log retry thành log chứa token, dữ liệu riêng tư hoặc metric có cardinality vô hạn.
- [ ] Có test kết quả **không rõ sau commit**, crash, concurrency và hủy.

## 15. Ghi nhớ

**Retry là chính sách lặp lại việc thực thi; idempotency là hợp đồng bảo vệ hiệu ứng của việc lặp đó.** Một AOP advice có thể tổ chức attempts, xử lý transient error, backoff, jitter và deadline rất tốt, nhưng không thể tự làm mọi thao tác ghi trở nên an toàn. Khi thao tác có side effect, tính đúng đắn nằm ở **khóa yêu cầu logic ổn định, kiểm soát trùng nguyên tử, ranh giới transaction, cơ chế đối soát và hợp đồng phía hệ thống đích**. Thiết kế hai phần này cùng nhau trước khi bật retry rộng rãi.
