# Thử lại mọi ngoại lệ mà không xét tính tạm thời và tác động lặp

**Retry (thử lại)** là một cơ chế phục hồi khi thao tác có thể thất bại nhất thời. Tuy nhiên, cách xử lý kiểu `catch (Exception e) { retry(); }` có thể biến một lỗi nhỏ thành lỗi nghiêm trọng hơn: thử lại đầu vào vốn luôn sai, lặp thanh toán hoặc gửi email, làm nghẽn hệ thống đang quá tải, che mất bug lập trình và khiến một workflow không bao giờ dừng. Một exception **không tự chứng minh** rằng thất bại là tạm thời, và việc caller không nhận được phản hồi **không chứng minh** rằng thao tác chưa tạo ra tác động.

Để quyết định retry đúng trong Java, cần trả lời ba câu hỏi độc lập:

1. **Lỗi có khả năng phục hồi theo thời gian không?** Có cơ sở để tin rằng lần thử sau có thể thành công mà không đổi input hoặc trạng thái nghiệp vụ?
2. **Thử lại có an toàn đối với tác động lặp không?** Nếu lần đầu đã thực hiện một phần hoặc toàn bộ side effect, thao tác mới có tạo dữ liệu trùng, trừ tiền lần hai hay gửi thông báo nhiều lần không?
3. **Giới hạn và quyền hủy là gì?** Có deadline, số lần thử, backoff, jitter, ngân sách retry và tín hiệu interruption/cancellation rõ ràng không?

Câu trả lời của ba câu này quyết định retry policy; **không phải chỉ tên lớp `Exception`**. Bài này thuộc nhóm *Sai lầm thường gặp* của Java Core – Exception, tập trung vào phân loại lỗi, idempotency và thiết kế retry có kiểm soát trong Java 17+.

## 1. Vì sao `catch (Exception)` rồi retry vô điều kiện là sai?

Mã minh họa sau thể hiện anti-pattern:

```java
while (true) {
    try {
        sendPayment();
        break;
    } catch (Exception error) {
        // Sai: không phân loại lỗi, không giới hạn số lần,
        // không kiểm tra tác động lặp, không tôn trọng ngắt.
    }
}
```

Đây là đoạn **minh họa nguy hiểm**, không phải chương trình độc lập; `sendPayment()` do ứng dụng định nghĩa. Nó có thể gây:

- **Vòng lặp vô hạn:** nếu amount âm hoặc token không hợp lệ, gọi lại cùng dữ liệu không làm lỗi biến mất.
- **Tác động lặp:** nếu server đã ghi giao dịch nhưng response bị mất, retry có thể ghi giao dịch lần hai.
- **Retry storm:** khi dependency quá tải, mọi caller cùng thử lại nhanh làm dependency quá tải hơn.
- **Che bug:** `NullPointerException`, `ClassCastException` hoặc vi phạm invariant có thể bị xem nhầm là lỗi mạng.
- **Mất tín hiệu ngắt:** nếu bắt rộng và không xử lý đúng `InterruptedException`, shutdown có thể bị trì hoãn.
- **Tăng độ trễ:** một request tiếp tục chờ qua nhiều lần thử cho tới khi vượt deadline của người gọi.
- **Khó quan sát:** log chỉ xuất hiện ở lần cuối, hoặc mỗi attempt in cả stack trace làm log storm; nguyên nhân ban đầu bị che.
- **Rò rỉ tài nguyên:** mỗi attempt mở connection/stream rồi thất bại nhưng không cleanup đúng owner.

Một lỗi có thể được **bắt** không có nghĩa rằng code bắt lỗi đủ hiểu để **phục hồi**. Tầng retry nên hiểu loại thao tác, nguồn lỗi và ràng buộc tính nhất quán.

## 2. Phân loại theo khả năng khắc phục, không theo checked/unchecked

Java phân biệt checked và unchecked exception ở cơ chế biên dịch; nhưng **checked không đồng nghĩa transient**, cũng như unchecked không nhất thiết permanent.

| Loại tình huống | Ví dụ | Retry cùng input ngay có hợp lý? |
| --- | --- | --- |
| **Transient** — có thể đổi theo thời gian | Kết nối tới dịch vụ tạm gián đoạn, server đang quá tải, tranh chấp tài nguyên ngắn hạn | Có thể, nếu thao tác an toàn khi lặp và chính sách có backoff. |
| **Permanent / deterministic** | Thiếu trường bắt buộc, dữ liệu sai format, vi phạm quy tắc cố định, quyền truy cập bị từ chối | Thường không; cần sửa input/quyền/cấu hình. |
| **Ambiguous outcome** | Server có thể đã xử lý nhưng response/ack bị mất, client timeout sau khi gửi request | Chỉ retry an toàn khi có idempotency/deduplication hoặc cơ chế đối soát trạng thái. |
| **Cancellation/interruption** | Caller bị ngắt khi chờ, task bị hủy | Không nên chống lại yêu cầu dừng bằng retry tự động. |
| **Programming bug** | `NullPointerException` do invariant bị phá, lỗi cast, bug truy cập index | Không; sửa code, bảo toàn stack trace, cảnh báo phù hợp. |
| **Resource exhaustion** | Pool cạn, lỗi thiếu bộ nhớ, disk đầy | Phụ thuộc nguồn lực và chính sách; retry dồn dập thường làm tệ hơn. |

Một `IOException` có thể là mất kết nối thoáng qua, nhưng cũng có thể là đường dẫn không tồn tại, permission bị từ chối hoặc dữ liệu sai không thể sửa bằng retry. Một `SQLException` có thể báo deadlock có khả năng thử lại hoặc vi phạm unique constraint sẽ thất bại lặp đi lặp lại. **Không retry toàn bộ `IOException` hoặc `SQLException` chỉ vì chúng là checked exception.**

Ngược lại, một exception miền ứng dụng dạng unchecked, ví dụ `TemporaryCapacityException extends RuntimeException`, có thể đại diện cho lỗi transient được công khai rõ. Điều quan trọng là **hợp đồng API của lỗi**, không phải nhánh cây kế thừa duy nhất.

## 3. Transient failure là gì?

Một thất bại *transient* là tình huống có cơ sở để tin trạng thái gây lỗi **có thể thay đổi**, khiến thử lại có xác suất thành công. Ví dụ:

- Dịch vụ downstream trả tín hiệu quá tải tạm thời và yêu cầu thử lại sau.
- Kết nối bị reset trước khi gửi request trong một thao tác đọc an toàn, với điều kiện đã biết request chưa được server xử lý.
- Deadlock/serialization conflict có contract cho phép lặp **toàn bộ transaction**, không chỉ một câu lệnh rời rạc.
- Một tài nguyên do dịch vụ khác cập nhật có thể trở nên sẵn sàng sau một khoảng thời gian.

Tuy nhiên, từ “transient” không có nghĩa “retry ngay vô hạn”:

1. Dependency có thể còn đang lỗi — cần backoff.
2. Nhiều caller retry đồng thời — cần jitter và hạn chế tải.
3. Deadline của request có thể đã hết — retry tiếp không còn hữu ích.
4. Side effect có thể đã xảy ra trước khi exception lộ ra — cần xác định an toàn khi lặp.
5. Tăng retry đồng nghĩa tăng tổng số attempt, không phải luôn cải thiện availability.

Một timeout cũng **không tự chứng minh transient**: nó chỉ nói một thao tác chờ hoặc lời gọi đã không hoàn thành trong ngân sách thời gian. Kết quả phía remote có thể đang xử lý, đã commit hoặc đã thất bại. Retry policy phải xét thêm **mức độ không chắc chắn của outcome**.

## 4. Permanent failure: retry không thay đổi điều kiện thất bại

Một số lỗi chỉ có thể sửa bằng thay đổi dữ liệu, quyền hoặc chương trình:

- `IllegalArgumentException` do quantity âm.
- Lỗi schema/validation của payload mà lần retry vẫn gửi cùng bytes.
- Token hết hạn hoặc quyền không đủ; có thể cần cấp lại token theo một **workflow riêng**, không phải lặp vô hạn cùng request.
- Ràng buộc duy nhất của database bị vi phạm và dữ liệu không thay đổi.
- Endpoint hoặc cấu hình không tồn tại theo contract.
- Lỗi lập trình như dereference `null` không được phép.

Nếu caller retry cùng request nguyên trạng sau một trong các lỗi này, kết quả có thể chỉ lặp lại lỗi, tiêu tốn CPU/network và làm nhiễu metrics. Nên **fail fast với thông tin có thể hành động**: sửa input, xin quyền, cập nhật cấu hình hoặc sửa code.

Đôi khi một HTTP status như `404` có thể tạm thời trong hệ thống eventual consistency, nhưng có thể permanent ở API khác. Tương tự `409 Conflict` có thể là xung đột phiên bản giải quyết được bằng **đọc lại và tính toán lại**; retry y nguyên payload cũ chưa chắc có ích. Không gán toàn bộ status code thành transient/permanent khi thiếu contract.

## 5. Outcome không rõ: lỗi nguy hiểm nhất với thao tác có side effect

Giả sử client gửi lệnh “trừ 100.000 đồng”:

```text
Client                           Server
   |                               |
   |---- POST /payments ---------->|
   |                               | Ghi giao dịch thành công
   |                               | Commit dữ liệu
   |<---- phản hồi bị mất ----------X
   |
   +-- client timeout
   +-- retry POST /payments ------> ?
```

Nếu hệ thống chỉ nhìn `SocketTimeoutException` rồi thử lại, server có thể xử lý **hai giao dịch**. Timeout là lỗi ở đường truyền/quan sát; nó không khẳng định request chưa đến server. Đây là tình huống **ambiguous outcome**.

Các cách thiết kế an toàn hơn:

- **Idempotency key:** caller cấp một định danh ổn định cho **cùng một thao tác logic** qua các attempt. Server nhớ kết quả cho key đó và trả lại kết quả cũ thay vì làm tác động lần nữa.
- **Deduplication dựa trên business key:** số đơn hàng, transaction ID, operation ID duy nhất; enforce bằng transaction/unique constraint.
- **Đối soát/truy vấn trạng thái:** kiểm tra ID đã xử lý chưa trước khi quyết định gửi lại.
- **Transactional outbox/inbox:** ghi trạng thái nghiệp vụ và sự kiện theo giao dịch rồi xử lý giao nhận lặp với consumer idempotent.
- **Compensation:** có thể cần khi hệ thống không có giao dịch nguyên tử xuyên dịch vụ; thao tác bù không thay thế việc ngăn side effect trùng.

**Không được tạo idempotency key mới trên mỗi attempt của cùng operation**: làm vậy biến các attempt thành các lệnh logic độc lập trong mắt server. Cùng thao tác phải dùng **cùng key và payload phù hợp**. Một yêu cầu nghiệp vụ khác thực sự phải dùng key khác.

Idempotency key không phải “có chuỗi UUID là xong”. Server phải kiểm tra key **cùng payload/định danh khách hàng**, lưu trạng thái/kết quả đủ bền, xử lý tranh chấp đồng thời, xác định thời hạn lưu và ngăn reuse key với payload khác.

## 6. An toàn khi lặp: đọc, ghi và idempotency

**Idempotent** nghĩa là lặp cùng một operation nhiều lần có **tác động dự kiến lên trạng thái** như thực hiện một lần (theo contract quan sát được). Nó không nhất thiết đồng nghĩa số lần thực thi bằng một hoặc mọi response byte đều giống nhau.

Ví dụ:

| Operation | Khả năng retry | Điểm cần kiểm tra |
| --- | --- | --- |
| Đọc dữ liệu không có side effect | Thường an toàn hơn | Cache, snapshot, timeout, semantics đọc và tải xuống. |
| Đặt `status = ACTIVE` | Có thể idempotent về trạng thái | Audit/email phát sinh mỗi lần có thể vẫn là side effect lặp. |
| Tăng `counter = counter + 1` | **Không idempotent** nếu không có dedup | Lặp tạo tổng sai. |
| `POST` tạo một khoản thanh toán | Không tự an toàn | Cần idempotency key/dedup hoặc đối soát. |
| `PUT` thay thế trạng thái resource | Về semantics HTTP thường được thiết kế idempotent | Business hooks, version, side effects, conditional requests vẫn phải xét. |
| `DELETE` theo identifier | Có thể idempotent về trạng thái cuối | Response lần hai có thể khác; audit/notification cũng có thể lặp. |
| Gửi email/webhook | Không tự idempotent | Cần message ID, dedup ở downstream hoặc chấp nhận ít nhất một lần và xử lý trùng. |

Đừng suy rằng HTTP `GET` luôn an toàn bất chấp implementation vi phạm semantics, hoặc HTTP `POST` luôn không thể retry. Chính contract của endpoint và deduplication phía server quyết định.

Thao tác *at-least-once delivery* thường có thể nhận cùng sự kiện nhiều lần. Consumer phải idempotent nếu mục tiêu là trạng thái đúng qua sự kiện lặp. Từ “exactly once” trong hệ phân tán phải được hiểu dưới **ranh giới bảo đảm cụ thể**, không phải lời hứa chung rằng không bao giờ có retry hay xử lý trùng ở mọi tầng.

## 7. Ví dụ Java 17: chỉ retry lỗi transient

Ví dụ này tách rõ lỗi có thể thử lại và lỗi input không nên thử lại. Để stdout xác định, chương trình dùng bộ đếm số attempt và **không ngủ/backoff**; phần delay là cơ chế production phải bổ sung, không phải bằng chứng một policy production hoàn chỉnh.

Tạo file `SelectiveRetryDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SelectiveRetryDemo {

    private static final class TemporaryFailureException
            extends RuntimeException {
        TemporaryFailureException(String message) {
            super(message);
        }
    }

    private static <T> T retryTransient(
            String label, Supplier<T> action, int maxAttempts) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                T value = action.get();
                System.out.println(label + " attempt " + attempt + ": SUCCESS");
                return value;
            } catch (TemporaryFailureException ex) {
                System.out.println(label + " attempt " + attempt + ": TRANSIENT");
                if (attempt == maxAttempts) {
                    throw ex;
                }
            } catch (IllegalArgumentException ex) {
                System.out.println(label + " attempt " + attempt + ": PERMANENT");
                throw ex;
            }
        }

        throw new AssertionError("unreachable");
    }

    public static void main(String[] args) {
        AtomicInteger readCalls = new AtomicInteger();

        String read = retryTransient("read", () -> {
            int number = readCalls.incrementAndGet();
            if (number <= 2) {
                throw new TemporaryFailureException("temporarily offline");
            }
            return "DATA";
        }, 3);
        System.out.println("read result: " + read);

        try {
            retryTransient("validate", () -> {
                throw new IllegalArgumentException("invalid input");
            }, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("validate stopped");
        }

        try {
            retryTransient("offline", () -> {
                throw new TemporaryFailureException("still offline");
            }, 2);
        } catch (TemporaryFailureException ex) {
            System.out.println("offline stopped");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SelectiveRetryDemo.java
java SelectiveRetryDemo
```

Stdout:

```text
read attempt 1: TRANSIENT
read attempt 2: TRANSIENT
read attempt 3: SUCCESS
read result: DATA
validate attempt 1: PERMANENT
validate stopped
offline attempt 1: TRANSIENT
offline attempt 2: TRANSIENT
offline stopped
```

Điểm cần học:

1. `TemporaryFailureException` ở ví dụ là **loại lỗi domain có hợp đồng cho phép thử lại**; tên class `RuntimeException`/`checked` không tự quyết định.
2. `read` thất bại hai lần rồi thành công ở lần thứ ba; toàn bộ operation được cho phép 3 attempt, **không phải 3 lần retry thêm**.
3. `validate` nhận lỗi permanent và dừng ngay ở attempt đầu, không lặp ba lần.
4. `offline` có giới hạn 2 attempt và truyền exception cuối ra ngoài; callback bên ngoài quyết định trả lỗi hoặc giám sát.
5. `Supplier.get()` có thể ném unchecked exception. Demo không bắt `Exception` tổng quát; những lỗi khác ngoài loại biết rõ sẽ truyền ra, tránh che bug.
6. Demo không có I/O, không có side effect và không thực hiện delay, deadline, jitter, circuit breaker hay interruption. Trong ứng dụng thật, chỉ dùng nó làm **minh họa phân loại và giới hạn**, không copy nguyên xi như retry framework production.

Với một operation có thể thay đổi trạng thái, **kiểm tra an toàn lặp trước khi gọi `retryTransient`**. Một exception loại temporary không làm cho thao tác ghi trở thành idempotent.

## 8. Ví dụ Java 17: idempotency key giữ side effect không bị lặp

Ví dụ mô phỏng việc server đã commit rồi client không nhận phản hồi. Client gọi lại bằng **cùng operation ID** và server trả kết quả đã ghi thay vì tăng counter lần nữa.

Tạo file `IdempotencyKeyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class IdempotencyKeyDemo {

    private static final class OutcomeUnknownException
            extends RuntimeException {
        OutcomeUnknownException(String message) {
            super(message);
        }
    }

    private static final class PaymentService {
        private final Map<String, Integer> committed = new HashMap<>();
        private int charges;

        int charge(String operationId, int amount, boolean loseResponse) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            Integer previous = committed.get(operationId);
            if (previous != null) {
                if (previous != amount) {
                    throw new IllegalArgumentException(
                            "same key with different amount");
                }
                return previous;
            }

            charges++;
            committed.put(operationId, amount);

            if (loseResponse) {
                throw new OutcomeUnknownException("response lost after commit");
            }
            return amount;
        }

        int chargeCount() {
            return charges;
        }
    }

    public static void main(String[] args) {
        PaymentService service = new PaymentService();

        try {
            service.charge("order-42", 50, true);
        } catch (OutcomeUnknownException ex) {
            System.out.println("client: outcome unknown");
        }

        int result = service.charge("order-42", 50, false);
        System.out.println("retry result: " + result);
        System.out.println("charges: " + service.chargeCount());

        try {
            service.charge("order-42", 75, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("key conflict: rejected");
        }

        service.charge("order-43", 50, false);
        System.out.println("charges after new order: " + service.chargeCount());
    }
}
```

Chạy với Java 17+:

```bash
javac -encoding UTF-8 IdempotencyKeyDemo.java
java IdempotencyKeyDemo
```

Kết quả:

```text
client: outcome unknown
retry result: 50
charges: 1
key conflict: rejected
charges after new order: 2
```

Giải thích:

- Lần đầu với `order-42` thực hiện `charges++` và lưu kết quả, **sau đó** giả lập mất response bằng `OutcomeUnknownException`.
- Retry bằng **cùng key `order-42` và amount 50** phát hiện kết quả đã có, trả `50` mà không tăng số lần charge.
- Cùng key nhưng amount khác bị từ chối; đó là bảo vệ chống reuse key sai payload.
- Một operation mới với `order-43` tăng counter lên 2, đúng vì đây là yêu cầu khác.
- **Đây chỉ là mô hình một luồng, trong bộ nhớ.** `HashMap`/counter không thread-safe, không được bảo vệ bởi transaction bền vững và sẽ mất dữ liệu khi restart. Production phải bảo đảm dedup có tính nguyên tử khi nhiều request cùng key đến đồng thời, khóa key theo tenant/context, lưu trạng thái/kết quả theo thời hạn và đồng bộ với commit nghiệp vụ.
- Ví dụ cũng giả định việc “charge” và ghi `committed` xảy ra như một bước logic; với DB/payment provider thật, hai hoạt động phải được phối hợp bằng transaction, unique constraint hoặc API idempotency của provider, không chỉ thêm một `HashMap` tại client.

**Một timeout sau commit không thể được giải quyết an toàn chỉ bằng việc retry cùng payload** nếu phía server không có hợp đồng idempotency/dedup. Ví dụ này minh họa chính điều kiện bảo đảm thêm mà server phải cung cấp.

## 9. Idempotency không phải chỉ là xử lý duplicate sau khi đã gây hại

Trong server đa luồng, mẫu kiểm tra rồi ghi không nguyên tử là lỗi:

```java
if (!processedIds.contains(id)) {
    performSideEffect();
    processedIds.add(id);
}
```

Đây là snippet minh họa anti-pattern. Hai request song song có thể cùng thấy ID chưa tồn tại và **cùng thực hiện side effect**, trước khi bên nào kịp thêm ID.

Cần thiết kế theo từng trường hợp:

- **Unique constraint + transaction:** key của operation và cập nhật trạng thái nghiệp vụ cùng một transaction, tránh trùng ở DB.
- **Lock/coordinator theo key:** tránh thực thi song song cùng operation; phải xử lý crash/restart và phân tán nhiều node.
- **Trạng thái `IN_PROGRESS`/`COMPLETED`/`FAILED`** có nghĩa rõ, tránh một request khác diễn lại khi attempt đầu chưa kết thúc.
- **Lưu response hoặc resource ID:** có thể trả kết quả nhất quán cho duplicate.
- **Quy tắc payload mismatch:** cùng key khác input bị reject thay vì xem là cùng thao tác.
- **Retention/expiration:** nếu key hết hạn mà caller vẫn retry, nguy cơ thực hiện lại phải được tài liệu hóa.
- **Tenant isolation:** key `order-42` của hai khách hàng không được đụng nhau nếu chúng là operation độc lập.

Trong message queue, consumer nên xử lý delivery trùng bằng message/operation ID. Retry và dedup là hai nửa của thiết kế; một bên thiếu có thể làm hệ thống đúng trong healthy path nhưng sai khi failure.

## 10. Backoff: đừng retry dồn dập

Ngay cả với lỗi transient và thao tác idempotent, retry liên tục ngay sau mỗi exception có thể tạo **retry storm**. Backoff tăng dần giúp dependency có thời gian hồi phục.

Cách đơn giản là exponential backoff có trần:

\[
d_k = \min(d_{\max},\, d_0 \times 2^{k-1})
\]

Trong đó `d_0` là delay ban đầu, `d_{\max}` là trần, `k` là lần **retry sau một attempt đã thất bại**, bắt đầu từ 1. Ví dụ `d_0 = 100 ms`, trần `500 ms`:

| Retry thứ | Delay chưa jitter |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 500 ms (capped) |
| 5 trở đi | 500 ms (capped) |

Không tính delay bằng phép nhân không kiểm soát nếu số attempt lớn vì có thể tràn số nguyên. Production nên dùng hàm giới hạn, dữ liệu `long` và ràng buộc thời gian phù hợp.

### Jitter chống đồng bộ retry

Nếu hàng nghìn client gặp lỗi cùng lúc và đều đợi chính xác 100 ms, sau 100 ms họ lại đồng loạt đánh vào server. **Jitter** thêm độ ngẫu nhiên vào delay để các attempt phân tán hơn.

Một chiến lược là *full jitter* với delay chọn ngẫu nhiên trong khoảng `[0, cappedDelay]`. Không có một công thức jitter duy nhất tối ưu cho mọi hệ thống; yêu cầu chính là có phân bố hợp lý, nằm trong deadline và được giám sát.

Đoạn code **minh họa**, không độc lập:

```java
long cappedDelayMillis = Math.min(maxDelayMillis, exponentialMillis);
long actualDelayMillis =
        ThreadLocalRandom.current().nextLong(cappedDelayMillis + 1);
Thread.sleep(actualDelayMillis);
```

Giả định `maxDelayMillis` và `exponentialMillis` hợp lệ, không âm, `cappedDelayMillis + 1` không tràn và có import `java.util.concurrent.ThreadLocalRandom`. `Thread.sleep` có thể ném `InterruptedException`; không nuốt interruption chỉ để hoàn thành retry. Trong hệ thống event-loop/async, ưu tiên scheduler thay vì block worker bằng `Thread.sleep`.

Cần ưu tiên hướng dẫn của server như HTTP `Retry-After` khi có và được API tin cậy hỗ trợ; vẫn áp dụng deadline, trần và kiểm tra an toàn lặp. Không bỏ qua retry hint rồi tạo backoff riêng trái hợp đồng.

## 11. Ví dụ Java 17: tính lịch backoff không chờ thật

Để minh họa delay có trần mà không phụ thuộc timing/scheduling, chương trình chỉ **tính và in lịch**, không gọi sleep hay network.

Tạo file `BackoffScheduleDemo.java`:

```java
public class BackoffScheduleDemo {

    static long cappedExponentialMillis(
            int retryNumber, long baseMillis, long maxMillis) {
        if (retryNumber < 1 || baseMillis < 0 || maxMillis < 0) {
            throw new IllegalArgumentException("invalid retry config");
        }

        long delay = Math.min(baseMillis, maxMillis);

        for (int i = 1; i < retryNumber; i++) {
            if (delay >= maxMillis) {
                break;
            }
            delay = delay > maxMillis / 2
                    ? maxMillis
                    : Math.min(maxMillis, delay * 2);
        }
        return delay;
    }

    public static void main(String[] args) {
        for (int retry = 1; retry <= 5; retry++) {
            System.out.println(
                "retry " + retry + ": "
                    + cappedExponentialMillis(retry, 100, 500) + " ms");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 BackoffScheduleDemo.java
java BackoffScheduleDemo
```

Stdout:

```text
retry 1: 100 ms
retry 2: 200 ms
retry 3: 400 ms
retry 4: 500 ms
retry 5: 500 ms
```

Hàm không triển khai jitter, retry policy đầy đủ hay scheduler; nó chỉ chứng minh quy tắc delay có trần với input mẫu. Trong production, thêm điều kiện không ngủ vượt **remaining deadline**, đo elapsed time bằng nguồn thời gian phù hợp và kiểm tra cancellation.

## 12. Retry limit, retry budget và deadline

Đừng chỉ giới hạn `maxAttempts`. Một chính sách retry thực tế thường cần **cả ba loại giới hạn**:

**1. Giới hạn attempt:** tổng số lần gọi (bao gồm lần đầu) không vượt mức cho phép. `maxAttempts=3` nghĩa là lần đầu + tối đa hai lần retry, không phải ba lần retry thêm.

**2. Deadline tổng:** chỉ tiếp tục nếu còn đủ thời gian để attempt và trả kết quả cho caller. Nếu request còn 50 ms nhưng backoff tối thiểu 200 ms, retry vô ích hoặc vi phạm deadline.

**3. Retry budget toàn hệ thống:** giới hạn số retry phát sinh so với lưu lượng thành công/hệ thống nhằm tránh khuếch đại tải lên dependency. Một dịch vụ có hàng nghìn request cùng retry 3 lần có thể gần như nhân bốn số cuộc gọi khi sự cố; cần giới hạn bổ sung theo host/tenant/operation hoặc global retry budget.

Ví dụ khái niệm:

```text
Request budget: 2.0 s
Attempt 1: 350 ms → transient failure
Backoff:   100 ms
Attempt 2: 400 ms → transient failure
Backoff:   200 ms
Remaining: 950 ms (trước overhead khác)
Attempt 3: chỉ bắt đầu nếu estimated timeout + xử lý response
           vẫn phù hợp với remaining deadline
```

Các thời gian trong ví dụ là giả định minh họa, không là số đo. Chính sách có thể dùng per-attempt timeout ≤ remaining deadline và **không cho phép retry** nếu việc gọi lại không còn lợi ích.

Không dùng riêng `Thread.sleep` để thực thi deadline: nó chỉ trì hoãn thread. Thời hạn phải được truyền/kiểm tra ở các tầng gọi network/DB hoặc workflow phù hợp.

## 13. Interruption và cancellation: retry không được chống shutdown

`InterruptedException` thường đại diện cho yêu cầu dừng một thao tác chờ. Nếu code retry nuốt exception này rồi tiếp tục `sleep`/gọi network, nó có thể làm shutdown không hoàn tất.

Ví dụ không nên áp dụng:

```java
for (;;) {
    try {
        doBlockingCall();
        break;
    } catch (InterruptedException ignored) {
        // Sai: bỏ tín hiệu ngắt và thử lại mãi.
    }
}
```

Đây là snippet minh họa, `doBlockingCall` giả định. Với API có thể khai báo `throws InterruptedException`, tốt nhất thường là truyền tiếp lên caller đủ quyền quyết định. Nếu phải bọc vào exception khác, thường cần **phục hồi interrupt flag**:

```java
try {
    doBlockingCall();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException("operation interrupted", ex);
}
```

`OperationCancelledException` là kiểu minh họa, chưa được định nghĩa trong đoạn độc lập. Điều cốt lõi là không coi interruption là transient failure để retry.

Một `Future.get(timeout)` ném `TimeoutException` chỉ báo **caller hết thời gian chờ**; task có thể vẫn chạy. `Future.cancel(true)` có thể yêu cầu interrupt worker theo implementation, nhưng không đảm bảo worker đã dừng hoặc cleanup hoàn tất. Nếu retry một task mới trong khi task cũ vẫn có side effect, cần idempotency/cancellation acknowledgement hoặc đối soát.

Với `CompletableFuture`, `orTimeout` có thể làm future completed exceptionally nhưng **không đảm bảo công việc nền được dừng**. `exceptionally(error -> retry().join())` có thể block thread callback và làm mất kiểm soát deadline; ưu tiên composition async và scheduler có giới hạn khi cần.

## 14. Phân loại IOException, HTTP, database và nghiệp vụ

Không nên viết policy kiểu:

```java
catch (IOException | RuntimeException ex) {
    // Retry tất cả.
}
```

Đây là snippet minh họa anti-pattern. Một chính sách tốt dựa vào **contract của dependency** và đặc điểm operation:

### HTTP/network

| Tín hiệu | Có thể xử lý | Điều kiện bổ sung |
| --- | --- | --- |
| HTTP 429 / tín hiệu rate limit | Thử lại sau khoảng server chỉ định khi phù hợp | `Retry-After`, quota, deadline, concurrency limit, idempotency. |
| HTTP 503 / server unavailable | Có thể transient | Backoff, jitter, tránh retry storm; write phải idempotent/dedup. |
| HTTP 500 | Có thể transient hoặc bug phía server | Không mặc nhiên retry POST có side effect; kiểm tra API contract. |
| HTTP 400 validation | Thường permanent với cùng payload | Sửa request, không tự retry y nguyên. |
| HTTP 401/403 | Thường cần xử lý authentication/authorization riêng | Refresh token chỉ nếu policy cho phép, không lặp vô hạn. |
| HTTP 404 | Có thể permanent hoặc tạm trong eventual consistency | Phụ thuộc resource workflow và hợp đồng. |
| HTTP 409 | Có thể là conflict yêu cầu đọc lại state | Retry nguyên trạng chưa chắc giúp gì; cần optimistic concurrency policy. |
| Connection lost / read timeout | Có thể outcome không rõ | Kiểm tra request có thể đã được xử lý, idempotency key hoặc đối soát. |

Không nên chỉ dùng tên `SocketTimeoutException` để kết luận an toàn khi retry: timeout lúc kết nối khác timeout lúc đợi response sau khi server đã nhận request. Điều kiện truyền dữ liệu và semantics phía remote mới quyết định.

### SQL/database

- **Deadlock/serialization conflict:** nhiều database cho phép thử lại toàn bộ transaction sau rollback theo loại lỗi/SQLState phù hợp. Cần đảm bảo transaction cũ đã rollback và mọi side effect ngoài DB không bị lặp sai.
- **Unique constraint violation:** với cùng dữ liệu thường permanent; nếu dùng unique key để dedup, có thể là tín hiệu truy vấn lại kết quả operation, **không** phải blindly retry insert.
- **Connection failure:** có thể transient nhưng outcome của transaction đôi khi không rõ khi mất connection gần thời điểm commit. Cần thiết kế recovery/transaction ID.
- **Syntax error/schema mismatch:** thường cần sửa code/migration; retry vô hạn không có ích.
- **Lock timeout:** có thể thử lại có giới hạn, nhưng cần hiểu transaction isolation, deadlock policy và tác động lên concurrent load.

JDBC cung cấp các subtype exception như `SQLTransientException` và `SQLNonTransientException` để gợi ý về khả năng retry. Dù vậy, nhà cung cấp driver và operation cụ thể vẫn quan trọng; **không xem subclass là quyền retry không điều kiện**, nhất là nếu dữ liệu đã commit hoặc thao tác gồm nhiều side effect.

### Nghiệp vụ

Một `InsufficientBalanceException` có thể không giải quyết được bằng retry vài mili giây với cùng tài khoản, trong khi `TemporaryInventoryLockException` có thể thử lại sau khi contention giảm. Hãy thiết kế các loại lỗi/mã lỗi nghiệp vụ theo ý nghĩa của chúng, không quyết định retry bằng kiểm tra mọi `RuntimeException`.

## 15. Không retry lỗi lập trình và lỗi tài nguyên nghiêm trọng

`NullPointerException`, `ClassCastException`, `AssertionError`, `OutOfMemoryError` thường không phải tín hiệu thích hợp để retry cùng code/path. Cố retry có thể gây:

- Lặp lại bug liên tục.
- Tạo thêm allocation trong tình trạng bộ nhớ cạn.
- Mất khả năng chẩn đoán do log storm.
- Giữ tài nguyên/cơ chế lock ở trạng thái không xác định.
- Làm health check báo hoạt động bình thường dù thành phần lõi đã hỏng.

Không nên bắt `Throwable` để retry. `Throwable` bao gồm `Error`; nhiều error biểu thị trạng thái runtime nghiêm trọng và không được thiết kế làm tín hiệu phục hồi nghiệp vụ.

Lỗi do `InterruptedException` thuộc kênh cancellation; trả quyền quyết định cho lifecycle owner. Một `CancellationException` từ `Future` cũng thường là trạng thái hủy cần được bảo lưu chứ không chuyển thành “lỗi tạm thời” để chạy lại.

Nếu một bug thật sự được phát hiện, sửa code và test; đừng thêm `catch(RuntimeException)` để làm triệu chứng biến mất.

## 16. Mọi attempt phải cleanup tài nguyên đúng owner

Nếu một attempt mở stream/connection/subscription rồi ném exception, retry sẽ mở thêm tài nguyên. Không cleanup attempt trước có thể làm rò rỉ nhanh hơn với mỗi vòng lặp.

Cấu trúc minh họa:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (ConnectionHandle owned = acquireConnection()) {
        return performOperation(owned);
    } catch (TransientConnectionException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }
        // Chỉ retry nếu operation an toàn khi lặp.
    }
}
throw new AssertionError("unreachable");
```

Đây là đoạn **minh họa**, với `ConnectionHandle` triển khai `AutoCloseable` và các symbol còn lại được định nghĩa trong ứng dụng. `try-with-resources` đóng handle của từng attempt **trước** khi quyết định retry. Không đóng pool dùng chung nếu connection được mượn; chỉ release/close handle theo contract pool.

Nếu `close()` cũng ném, cần giữ thông tin primary/suppressed exception. Nếu retry ngay sau lỗi cleanup có thể làm trạng thái không xác định, phải phân loại lỗi cleanup và tính an toàn lặp, không đơn giản xem nó là transient.

Trong hệ thống nhiều thao tác, hãy định nghĩa rõ **ranh giới retry**: thử lại cả transaction hay chỉ câu lệnh? Đã commit một phần chưa? Nếu một operation gồm ghi DB rồi gửi email, retry toàn operation có thể gửi email trùng dù DB đã rollback hay ngược lại.

## 17. Retry nhiều tầng tạo tải khuếch đại

Giả sử một request đi qua ba service A → B → C. Nếu mỗi tầng tự retry tối đa 3 attempt, trong trường hợp xấu, một request bên ngoài có thể tạo tới:

\[
3 \times 3 \times 3 = 27
\]

lần gọi tới thao tác sâu nhất, nếu mỗi tầng retry khi downstream báo lỗi. Đây là **giới hạn minh họa** trong cấu trúc ba tầng, không là con số bắt buộc cho mọi kiến trúc.

Khi dependency đang lỗi, multiplicative retries có thể làm sự cố trầm trọng. Các cách giảm:

- Quy định **tầng sở hữu retry** ở boundary phù hợp, tránh mỗi thư viện/adapter tự retry mù.
- Truyền tổng deadline và **retry budget** qua các tầng.
- Dùng circuit breaker/rate limiting/bulkhead khi cần, với chính sách có thể kiểm chứng.
- Giới hạn concurrency và độ dài queue.
- Tôn trọng `Retry-After`/backpressure của server.
- Thu metrics theo attempt, request và dependency; không chỉ đếm request lỗi.

Circuit breaker không phải phép màu sửa nghiệp vụ; nó chủ yếu giúp chặn bớt lưu lượng tới dependency có tín hiệu lỗi để giảm thiệt hại. Khi breaker mở, caller cần nhận lỗi/response rõ ràng thay vì tự tạo vòng lặp khác vượt qua breaker.

## 18. Retry, fallback và trạng thái “chưa biết”

Ba phản ứng sau khác nhau:

**Retry:** gọi lại tác vụ, có thể tăng số side effect; chỉ an toàn khi đủ điều kiện.

**Fallback:** trả kết quả dự phòng có hợp đồng rõ, ví dụ danh sách gợi ý trống khi recommendation service unavailable. Fallback không đồng nghĩa đã thực hiện thành công thao tác gốc.

**Unknown/pending:** chưa xác minh kết quả cuối của thao tác có side effect. Có thể cần trả operation ID để client query status, thay vì nói thành công/thất bại sai.

Ví dụ một API thanh toán nên phân biệt:

```text
SUCCESS     — giao dịch được xác nhận
FAILED      — đã biết giao dịch thất bại
PENDING     — đang xử lý/chưa có kết quả cuối
UNKNOWN     — không chắc remote đã commit hay chưa; cần đối soát
```

Đây là các trạng thái **minh họa**; tên và contract thực tế thuộc hệ thống ứng dụng. Retry bừa có thể biến UNKNOWN thành hai khoản ghi thành công, còn fallback `SUCCESS` giả có thể gây sai dữ liệu.

Đối với read-only operation, fallback cache có thể có nghĩa rõ nếu dữ liệu còn hợp lệ. Đối với write có tác động quan trọng, cần tránh “phục hồi bằng giá trị mặc định” che mất kết quả chưa được xác nhận.

## 19. Retry bất đồng bộ và CompletableFuture

Khi dùng `CompletableFuture`, lỗi có thể được lưu trong stage dưới dạng exceptional completion. Một chuỗi:

```java
serviceCall()
    .exceptionally(error -> serviceCall().join());
```

là **mảnh minh họa anti-pattern**: `serviceCall()` giả định trả `CompletableFuture<T>`. Lambda `exceptionally` có thể thực thi trên thread completion, gọi `join()` blocking và gây nghẽn/deadlock nếu executor thiếu thread. Nó cũng không phân loại lỗi, không có giới hạn attempt và có thể lặp side effect.

Đối với fallback sang một nguồn async khác, Java 17 có `exceptionallyCompose` để nối stage mà không phải block bằng `join()`. Tuy nhiên, `exceptionallyCompose` **tự nó không phải retry framework**: nếu dùng để gọi lại operation, vẫn cần phân loại lỗi, giới hạn attempts, deadline, jitter/backoff scheduler, cancellation và idempotency.

Một cách tổ chức thực tế là để bộ phận có quyền sở hữu workflow quản lý state machine retry (attempt count, last failure, remaining deadline), tạo attempt mới khi được phép và hoàn thành một `CompletableFuture` tổng sau khi success/final failure/cancel. Sử dụng scheduled executor có lifecycle rõ thay vì `Thread.sleep` blocking trong callback.

Khi caller của `Future.get(timeout)` bị `TimeoutException`, chỉ **lần chờ** hết hạn; stage/task nền có thể còn chạy. Đừng tạo attempt mới với side effect nếu chưa giải quyết quyền hủy, result tracking và idempotency.

## 20. Logging và quan sát retry đúng cách

Nếu mỗi attempt lỗi đều in stack trace đầy đủ rồi tầng ngoài lại log khi hết attempts, một request có thể sinh hàng chục bản ghi cùng nguyên nhân. Khi dependency lỗi diện rộng, điều này có thể tạo log storm và làm chậm hệ thống.

Nên ghi nhận:

| Metric/thuộc tính | Mục đích |
| --- | --- |
| `operation_id` / idempotency key an toàn | Nối các attempt của cùng một operation để đối soát. |
| `attempt_number` và `max_attempts` | Phân biệt lần đầu với retry. |
| `retry_reason` / mã lỗi | Hiểu vì sao policy cho phép retry. |
| `retry_outcome` | Thành công sau retry, exhausted, permanent, canceled, deadline exceeded. |
| Backoff delay | Phân tích latency và sự đồng bộ retry. |
| Retry amplification | Số attempt trên mỗi request, theo downstream. |
| Pending/unknown outcomes | Theo dõi các operation cần đối soát. |
| Circuit state và queue saturation | Nhận diện hệ thống đang được bảo vệ hay bị overload. |

Tầng retry có thể ghi metric cho **mỗi attempt**, nhưng stack trace đầy đủ thường nên log chọn lọc theo chính sách ở boundary có ngữ cảnh, không nhất thiết một lần cho mọi attempt. Khi log mẫu, vẫn cần metrics đếm toàn bộ lỗi để không đánh giá thấp sự cố.

Không dùng toàn bộ exception message, URL chứa token, payload thanh toán hoặc ID cá nhân làm metric label/log key; chọn mã lỗi và trường correlation được bảo vệ.

Khi một attempt cuối thất bại, giữ `cause` và đủ ngữ cảnh attempt để điều tra. Không bọc mọi lỗi thành `RuntimeException("retry failed")` rồi bỏ nguyên nhân gốc.

## 21. Tính nhất quán của retry với transaction

Giả sử transaction làm hai việc: ghi đơn hàng và phát sự kiện “order created”. Nếu ghi DB thành công nhưng phát sự kiện thất bại, retry cả luồng có thể tạo đơn trùng hoặc phát nhiều sự kiện.

Các phương án tùy kiến trúc:

- **Transaction DB đúng ranh giới:** với deadlock có thể rollback rồi thử lại *toàn transaction*. Cần biết phần việc nào nằm trong transaction.
- **Transactional outbox:** ghi business state và outbox event trong cùng transaction; worker phát event có thể retry gửi, consumer dùng dedup.
- **Optimistic concurrency:** mỗi lần conflict có thể cần đọc version mới, tính lại quyết định rồi ghi; retry nguyên payload cũ có thể cứ fail.
- **Idempotency token:** server biết cùng một operation ID đã xử lý và trả kết quả ổn định.
- **SAGA/compensation:** nếu nhiều hệ không thể có transaction chung, workflow điều phối trạng thái và bù khi cần; retry chỉ một hành động có rủi ro riêng.

Đừng thiết kế retry trước rồi mới hỏi “có side effect không?”. **Tính chất nghiệp vụ và giao dịch quyết định chính sách retry**, không phải ngược lại.

## 22. Trường hợp đáng retry nhưng không nên tự động retry ngay

Có những tình huống lỗi có thể hồi phục, nhưng tự động retry vẫn không phù hợp:

- Giao dịch chi tiền có outcome không rõ và không có idempotency key.
- Lỗi rate limit đòi đợi 60 giây nhưng deadline caller còn 2 giây.
- Dịch vụ đang trong maintenance với retry hint dài hơn ngân sách request.
- Caller đã hủy request hoặc service đang shutdown.
- Dependency có dấu hiệu quá tải, retry budget đã cạn.
- Operation có side effect không bù được hoặc vi phạm điều kiện duy nhất khi lặp.
- Lỗi có thể khắc phục bằng yêu cầu người dùng xác nhận thay đổi dữ liệu; retry tự động không làm được việc đó.
- Một attempt đã vượt thời hạn toàn workflow và công việc cũ có thể vẫn chạy.

Ở đây hành động đúng có thể là **trả trạng thái pending**, **đưa job vào hàng đợi bền vững**, **yêu cầu đối soát**, **cảnh báo vận hành** hoặc **dừng với lỗi có ý nghĩa**, không phải ném thêm một request lập tức.

## 23. Kiểm thử retry policy theo tình huống

Bộ kiểm thử tốt phải xác nhận cả hai điều: **lần nào được retry** và **lần nào tuyệt đối không được retry**.

| Tình huống | Kỳ vọng |
| --- | --- |
| Transient lỗi hai lần rồi thành công | Tổng 3 attempts, một kết quả thành công, không tiếp tục retry. |
| Permanent validation failure | Chỉ 1 attempt, truyền lỗi rõ ràng. |
| Transient tiếp tục lỗi đến giới hạn | Đúng `maxAttempts`, sau đó trả failure cuối. |
| Deadline hết trước attempt tiếp | Không gọi tiếp, báo deadline exhausted. |
| Backoff có trần | Delay không vượt trần và không vượt remaining deadline. |
| 1000 caller đồng thời transient failure | Jitter/limit giúp tránh cùng retry một lúc; đo số attempt và queue depth. |
| Caller/worker bị interruption | Kết thúc theo cancellation policy, phục hồi/truyền interrupt khi phù hợp. |
| Server commit nhưng response mất | Retry với cùng idempotency key không tạo thêm side effect. |
| Hai retry cùng key đồng thời | Server không chạy side effect hai lần; duplicate nhận kết quả hoặc trạng thái đúng. |
| Cùng key với payload khác | Bị từ chối/được xử lý theo contract, không lặng lẽ coi là trùng hợp lệ. |
| Idempotency key hết thời gian lưu | Có contract rõ về rủi ro và thời hạn retry. |
| Database deadlock | Retry đúng ranh giới transaction sau rollback, không nhân đôi tác động ngoài transaction. |
| Retry bị thiếu tài nguyên | Mỗi attempt cleanup tài nguyên đã acquire, không leak connection/permit. |
| Exception không được phân loại | Fail/propagate, không tự retry mọi `RuntimeException`. |
| Log/metrics của retry | Biết tổng attempts, outcomes, không spam stack trace hoặc lộ dữ liệu. |

Khi test concurrency/idempotency, dùng latch/barrier điều khiển hai request cùng key chạy đồng thời; đừng chỉ chạy tuần tự rồi kết luận server đã an toàn trong race.

Khi test backoff, tốt hơn nên **inject clock/scheduler** hoặc tính delay thuần để có test quyết định; không dựa vào `Thread.sleep(100)` và thời gian thực của CI. Đối với I/O thật, dùng fake adapter cho lỗi trước gửi, lỗi sau commit và mất response để kiểm tra outcome.

## 24. Những anti-pattern thường gặp

**Retry mọi `Exception` hoặc `Throwable`.** Sai vì permanent error, cancellation, bug và resource exhaustion có ý nghĩa khác nhau. Phân loại theo contract, không bắt rộng tùy tiện.

**Retry mọi HTTP 5xx hoặc `IOException` cho thao tác ghi.** Không đủ: request có thể đã commit, response có thể mất. Cần idempotency/dedup hoặc đối soát.

**Retry cùng payload khi validation fail.** Không thay đổi nguyên nhân; cần sửa input.

**Retry ngay, không delay.** Có thể làm quá tải dependency hơn, tạo đồng bộ giữa các client.

**Dùng backoff nhưng không có maxAttempts/deadline.** Có thể kéo dài workflow vô hạn và giữ tài nguyên.

**Retry ở nhiều tầng không phối hợp.** Tải có thể nhân lên theo tích số attempts ở mỗi tầng.

**Tạo idempotency key mới ở mỗi lần retry.** Biến duplicate thành operation mới; có nguy cơ thực hiện side effect nhiều lần.

**Dùng `HashMap` check-then-write trong server đa luồng như thể đã exactly-once.** Có race/crash/restart; cần atomic/durable dedup theo operation.

**Coi timeout là failure chắc chắn của server.** Timeout chỉ có thể báo mất khả năng quan sát kết quả.

**Nuốt `InterruptedException` để tiếp tục retry.** Chống lại shutdown/cancellation; có thể làm service treo.

**Dùng `CompletableFuture.exceptionally(...join())` để “retry async”.** Có thể block thread callback và thiếu policy đầy đủ.

**Ghi stack trace mọi attempt.** Log storm, tăng CPU/I/O và giảm khả năng quan sát.

**Không cleanup sau attempt lỗi.** Mỗi retry nhân thêm rò rỉ tài nguyên.

**Chỉ kiểm tra kết quả cuối mà không kiểm tra số attempts.** Một test “cuối cùng thành công” vẫn có thể che việc retry 1000 lần hoặc gửi email trùng.

**Nhầm retry và fallback.** Fallback là kết quả dự phòng, không chứng minh operation gốc đã thành công.

## 25. Bài tập tự kiểm tra

**Câu 1.** Một API trả `IllegalArgumentException("quantity must be positive")`. Caller retry 5 lần cùng quantity -2. Có ích không?

**Đáp án:** Không. Đây là lỗi đầu vào permanent; không có thay đổi nào giữa các lần gọi.

**Câu 2.** Client gửi lệnh chuyển tiền, server commit rồi response mất. Caller nhận `SocketTimeoutException`. Có thể retry ngay với request mới không?

**Đáp án:** Chưa an toàn. Outcome không rõ; cần idempotency key cố định cho cùng operation hoặc truy vấn/đối soát trạng thái. Gửi request mới không dedup có thể chuyển tiền hai lần.

**Câu 3.** Một operation read-only gặp `TemporaryServiceUnavailableException`. Caller còn deadline 3 giây, server gửi `Retry-After: 10` giây. Nên làm gì?

**Đáp án:** Không đợi rồi retry trong request 3 giây. Tôn trọng deadline, trả lỗi/trạng thái phù hợp hoặc chuyển sang workflow background có quyền sở hữu riêng nếu contract cho phép.

**Câu 4.** Một tầng A retry 3 attempts, B retry 3 và C retry 3. Khi mọi lần thất bại, C có thể nhận tối đa bao nhiêu attempts cho một request A?

**Đáp án:** Theo mô hình lồng nhau đơn giản có thể tới `3 × 3 × 3 = 27` attempts ở tầng sâu. Đây là lý do phải phối hợp retry budget và ownership.

**Câu 5.** `Future.get(timeout)` ném `TimeoutException`. Task nền đã ngừng và rollback chưa?

**Đáp án:** Không thể kết luận. Đây là timeout của thao tác chờ; task có thể đang chạy hoặc đã tạo side effect.

**Câu 6.** `retryTransient` trong `SelectiveRetryDemo` được gọi với `maxAttempts=3` và task lỗi transient hai lần rồi thành công. Có bao nhiêu lần retry *sau* lần gọi đầu?

**Đáp án:** Hai lần retry; tổng ba attempts.

**Câu 7.** Server dùng `processedIds.contains(id)` rồi `performSideEffect()` và `processedIds.add(id)`. Hai request cùng id chạy đồng thời có an toàn không?

**Đáp án:** Không. Cả hai có thể thấy ID chưa tồn tại và cùng thực hiện side effect. Cần dedup/transaction/lock có bảo đảm nguyên tử theo key và môi trường triển khai.

**Câu 8.** Một `InterruptedException` ném trong `Thread.sleep(backoff)`. Retry loop nên bắt rồi sleep lại đến hết attempts?

**Đáp án:** Không. Cần tôn trọng tín hiệu ngắt; truyền tiếp `InterruptedException` hoặc phục hồi cờ rồi chấm dứt theo lifecycle policy.

## 26. Checklist trước khi thêm retry vào Java API

- [ ] Đã phân loại lỗi transient, permanent, ambiguous outcome, cancellation và bug.
- [ ] Chỉ retry **những lỗi được API cho phép** và các operation an toàn khi lặp.
- [ ] Biết side effect đã xảy ra trước điểm lỗi hay chưa, hoặc có cơ chế idempotency/đối soát.
- [ ] Cùng operation dùng cùng idempotency key; server bảo đảm dedup nguyên tử và có lưu trạng thái phù hợp.
- [ ] Có maxAttempts rõ, phân biệt attempt tổng và số retry thêm.
- [ ] Có deadline tổng và timeout từng attempt không vượt remaining time.
- [ ] Có bounded backoff, jitter và tôn trọng retry hint phù hợp.
- [ ] Có retry budget, concurrency limit/circuit breaker khi dependency quá tải.
- [ ] Không nuốt interruption/cancellation; không retry khi caller đã dừng.
- [ ] Mỗi attempt cleanup owned resources và rollback/compensation đúng ranh giới.
- [ ] Không retry nhiều tầng không phối hợp.
- [ ] Ghi metrics theo request và attempt, không double-log full stack trace vô ích.
- [ ] Có test permanent error chỉ một attempt, transient hồi phục, exhaustion và timeout.
- [ ] Có test mất response **sau commit**, duplicate đồng thời và reuse key sai payload.
- [ ] Đã kiểm tra correctness, duplicate side effect, p95/p99 latency và tải dependency trong error burst.

## 27. Kết luận

**Không phải mọi exception đều nên retry.** Lỗi tạm thời có thể xứng đáng được thử lại, nhưng chỉ khi operation **an toàn khi lặp**, caller còn ngân sách thời gian, và hệ thống không bị khuếch đại tải. Lỗi đầu vào, bug lập trình và tín hiệu hủy thường cần dừng ngay; lỗi mạng sau khi gửi lệnh có side effect còn có thể là **kết quả chưa xác định**, không phải thất bại chắc chắn.

Retry đúng là một **chính sách nghiệp vụ và vận hành**: phân loại lỗi, giới hạn attempts/deadline, backoff có jitter, bảo đảm idempotency hoặc đối soát, cleanup theo ownership và giám sát từng attempt. Làm rõ những điều kiện này trước khi viết vòng lặp `catch/retry` sẽ giúp hệ thống phục hồi khi đáng phục hồi mà không tạo thêm dữ liệu trùng, lỗi dây chuyền hoặc mất khả năng chẩn đoán.