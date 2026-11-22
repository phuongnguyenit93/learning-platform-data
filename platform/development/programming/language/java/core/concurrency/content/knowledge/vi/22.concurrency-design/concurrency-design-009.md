# Đảm bảo idempotency khi task có thể được chạy lại

Trong hệ thống đồng thời, một task có thể được gửi hai lần, được retry sau timeout, chạy lại khi tiến trình khởi động hoặc được hai worker nhận gần như cùng lúc. Thiết kế đúng phải bảo đảm **một yêu cầu nghiệp vụ lặp lại không tạo thêm tác dụng ngoài ý muốn**, ngay cả khi ta không kiểm soát được số lần thực thi mã. Nội dung này áp dụng cho Java nói chung (thread, executor, queue, database, API ngoài), không phụ thuộc Spring.

## 1. Idempotency thực sự có nghĩa gì?

Một thao tác `f` có tính idempotent đối với trạng thái nghiệp vụ nếu áp dụng nhiều lần cùng một ý định cho kết quả quan sát được tương đương với áp dụng một lần: `f(f(s)) = f(s)`. “Cùng ý định” cần được nhận diện bằng một **idempotency key** ổn định, không phải bằng số lần gọi phương thức. Ví dụ:

| Thao tác | Khi chạy lại | Nhận xét |
|---|---|---|
| `order.status = SHIPPED` với cùng phiên bản/điều kiện hợp lệ | Trạng thái vẫn `SHIPPED` | Có thể idempotent |
| `balance += 100` | Số dư tiếp tục tăng | Không idempotent |
| `sendEmail()` | Gửi thêm email | Không idempotent nếu không có chống trùng ở nơi gửi |
| `INSERT event` với `event_id` duy nhất và bỏ qua bản ghi trùng | Không tạo thêm bản ghi | Idempotent trong ranh giới bảng đó |
| `UPSERT` nhưng mỗi lần đều đổi `updated_at` hay phát event | Có tác dụng mới | Chưa idempotent về toàn bộ hành vi |

Phân biệt các khái niệm:

- **Idempotency:** retry cùng một yêu cầu không gây thêm tác dụng nghiệp vụ.
- **Deduplication:** nhận diện và loại những yêu cầu trùng; thường là một công cụ để đạt idempotency.
- **Thread safety:** tránh race/data race khi các thread truy cập dữ liệu chung; một hàm thread-safe vẫn có thể tăng số dư hai lần.
- **At-most-once execution:** cố tránh thực thi lặp, có nguy cơ mất việc nếu lỗi xảy ra trước lúc làm.
- **At-least-once delivery:** tiếp tục gửi lại tới khi được xác nhận; có thể thực thi trùng.
- **Exactly-once effect:** một tác dụng được ghi nhận đúng một lần trong **ranh giới được bảo vệ**, chẳng hạn một transaction cơ sở dữ liệu. Không đồng nghĩa “mã chỉ chạy đúng một lần” trên mọi máy và mọi dịch vụ.

Trong thực tế, “đã làm xong nhưng mất phản hồi” không thể phân biệt với “chưa làm xong” chỉ bằng timeout. Vì vậy retry là bình thường; hậu quả của retry phải được kiểm soát.

## 2. Chọn idempotency key và hợp đồng trả kết quả

Key biểu diễn **ý định nghiệp vụ**, ví dụ `charge:order-842`, `import:file-sha256:row-17` hoặc request UUID do bên gọi tạo và **tái sử dụng cho mọi lần retry** của cùng yêu cầu. Key của lần thử (`attemptId`), thời điểm hiện tại hoặc UUID tạo mới trong mỗi lần chạy không giúp phát hiện retry.

Một hợp đồng thực dụng gồm:

1. **Phạm vi key:** chỉ rõ key có duy nhất theo toàn hệ thống, theo tenant, người dùng hay loại tác vụ. Nếu chia phạm vi, khóa duy nhất có thể là `(tenant_id, operation_type, idempotency_key)`.
2. **Ràng buộc payload:** lưu hash chuẩn hóa của các trường có ý nghĩa nghiệp vụ. Nếu cùng key mà payload khác, báo lỗi `KEY_REUSED_WITH_DIFFERENT_PAYLOAD`; không âm thầm xem là một yêu cầu cũ. Việc chuẩn hóa phải cố định (thứ tự field, encoding, tiền tệ, độ chính xác số).
3. **Kết quả ổn định:** nếu đã hoàn tất, trả lại kết quả đã lưu hoặc trạng thái tương đương, không thực hiện lại side effect. Có thể cần giữ HTTP status/operation ID cùng nội dung kết quả.
4. **Tác vụ đang chạy:** phản hồi `IN_PROGRESS`, trả operation ID để tra cứu hoặc chờ kết quả có giới hạn; không tự ý khởi tạo tác vụ thứ hai.
5. **Thời gian lưu:** giữ receipt/key đủ lâu cho retry muộn, replay từ queue và yêu cầu kiểm toán. Hết TTL quá sớm có thể khiến một bản tin cũ sinh side effect mới.

Key phải được kiểm soát quyền truy cập: không để client của tenant này dùng key để đọc kết quả bí mật của tenant khác. Hash payload chỉ là dấu nhận biết nội dung, không thay thế xác thực/ủy quyền.

## 3. Race condition: kiểm tra rồi ghi không đủ

Thiết kế sau có race:

```java
if (!processedIds.contains(taskId)) {
    performEffect();
    processedIds.add(taskId);
}
```

Hai thread đều có thể thấy “chưa xử lý”, rồi cùng gọi `performEffect()`. Đổi `HashSet` thành thread-safe set chỉ làm các thao tác đơn lẻ an toàn, không biến **cặp kiểm tra + tác dụng** thành một bước nguyên tử. Khóa `synchronized` có thể tuần tự hóa trong một JVM nếu tất cả callers dùng cùng khóa, nhưng không chống được worker ở JVM khác, restart hoặc mất dữ liệu sau crash.

Một thiết kế đúng cần xác định **điểm tuyến tính hóa (linearization point)**: một thao tác nguyên tử quyết định ai sở hữu key. Trong một process có thể dùng `ConcurrentHashMap.putIfAbsent` hoặc `computeIfAbsent` với điều kiện phù hợp. Giữa nhiều process nên dùng unique constraint, conditional update/compare-and-set hoặc primitive tương đương tại nguồn dữ liệu bền vững. Việc nhận key **chưa đủ** nếu side effect xảy ra ngoài ranh giới nguyên tử.

## 4. Ví dụ Java 17+: gộp các lần gọi đồng thời trong một JVM

Ví dụ đầy đủ sau sử dụng `FutureTask` để các caller cùng key nhận **chung một kết quả**. `putIfAbsent` xuất bản đúng một task; chỉ thread thắng cuộc gọi `run()`. Dù bốn caller đến đồng thời, phần xử lý giả lập chỉ chạy một lần.

Tệp `IdempotentTaskDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class IdempotentTaskDemo {
    private static final ConcurrentMap<String, FutureTask<String>> tasks =
            new ConcurrentHashMap<>();

    static String executeOnce(String key, Callable<String> action)
            throws InterruptedException, ExecutionException {
        FutureTask<String> candidate = new FutureTask<>(action);
        FutureTask<String> existing = tasks.putIfAbsent(key, candidate);
        FutureTask<String> selected = existing == null ? candidate : existing;

        if (existing == null) {
            selected.run(); // Chỉ caller thắng putIfAbsent thực thi action.
        }
        return selected.get(); // Caller khác cùng chờ một FutureTask.
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger effects = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<String>> replies = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                replies.add(pool.submit(() ->
                        executeOnce("job:42", () -> {
                            effects.incrementAndGet();
                            return "DONE";
                        })));
            }
            for (Future<String> reply : replies) {
                System.out.println(reply.get());
            }
            System.out.println("Số lần xử lý: " + effects.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac IdempotentTaskDemo.java
java IdempotentTaskDemo
```

Đầu ra:

```text
DONE
DONE
DONE
DONE
Số lần xử lý: 1
```

**Giới hạn cần hiểu trước khi dùng thực tế:**

- Map sống trong bộ nhớ của **một JVM**. Một restart hoặc hai instance sẽ không dùng chung receipt. Đây là single-flight/memoization trong process, không phải idempotency bền vững.
- Cùng key với payload khác vẫn nhận kết quả cũ: production phải ràng buộc thêm payload hash và scope trước khi trả kết quả.
- Nếu `Callable` lỗi, `FutureTask` ghi nhớ lỗi, mọi caller nhận `ExecutionException`; demo hiện tại không retry key đó. Muốn retry phải có chính sách lỗi rõ ràng và xóa bằng so sánh đối tượng, chẳng hạn `tasks.remove(key, selected)`, **chỉ sau khi xác định retry an toàn**. Xóa vô điều kiện có thể xóa task mới.
- Không gọi network I/O kéo dài ngay trong callback của `ConcurrentHashMap.computeIfAbsent` để làm cơ chế phân tán. Mapping function không được can thiệp đệ quy vào chính map; action chậm còn có thể chặn update khác.
- `selected.get()` chờ đến khi hoàn tất; production cần timeout, cancellation và chiến lược ngắt thread. Hủy một caller không nên tùy tiện hủy công việc chung còn caller khác đang chờ.
- Map giữ kết quả vô hạn nếu không có eviction/TTL. Eviction làm key có thể xử lý lại, nên tác dụng cần có lớp bền vững riêng.

## 5. Idempotency bền vững: receipt và transaction

Khi có restart, nhiều JVM hoặc queue phát lại, dùng một **receipt store** chung với ràng buộc unique tại nơi phát sinh tác dụng nghiệp vụ. Một cấu trúc cơ bản:

| Trường | Mục đích |
|---|---|
| `scope + idempotency_key` (unique/primary key) | Nhận diện cùng một yêu cầu |
| `payload_hash` | Từ chối dùng lại key cho nội dung khác |
| `status`: `PENDING`, `IN_PROGRESS`, `SUCCEEDED`, `FAILED` | Theo dõi vòng đời |
| `result` hoặc `resource_id` | Trả lại kết quả khi retry |
| `attempt`, `lease_until`, `fencing_token` | Quản lý takeover khi worker mất |
| `created_at`, `completed_at` | Giám sát và retention |

**Mẫu transaction ngắn (tác dụng và receipt trong cùng một database):**

```text
Nhận (scope, key, payload):
  BEGIN TRANSACTION
    Thử claim key bằng INSERT có UNIQUE constraint.
    Nếu trùng key:
      đọc receipt tương ứng theo chiến lược khóa/isolation phù hợp;
      nếu payload_hash khác -> từ chối;
      nếu SUCCEEDED -> trả result đã lưu;
      nếu đang xử lý -> trả IN_PROGRESS / chờ có giới hạn;
      nếu FAILED -> áp dụng chính sách retry;
    Nếu claim thành công:
      cập nhật dữ liệu nghiệp vụ;
      cập nhật receipt = SUCCEEDED và lưu result;
  COMMIT
  Trả result
```

Đây là **thuật toán minh họa**, không phải mã Java/SQL chạy độc lập. Với tác vụ nhanh, gói claim + business update + receipt success trong **cùng một transaction** là cách bảo đảm rollback đồng thời khi lỗi. Mọi transaction cạnh tranh phải tuân thủ unique constraint của database; thao tác “SELECT xem có chưa rồi INSERT” thiếu unique constraint vẫn có race.

Ví dụ DDL tối giản, cú pháp PostgreSQL (hệ khác cần điều chỉnh):

```sql
CREATE TABLE job_receipt (
    scope          VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    payload_hash   CHAR(64) NOT NULL,
    status         VARCHAR(20) NOT NULL,
    result_ref     VARCHAR(200),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at   TIMESTAMPTZ,
    PRIMARY KEY (scope, idempotency_key)
);
```

Để nhận key, PostgreSQL hỗ trợ `INSERT ... ON CONFLICT DO NOTHING RETURNING ...`. Nếu câu lệnh trả một dòng, caller vừa claim thành công; nếu không, nó phải đọc trạng thái đã có, so payload hash và xử lý đúng nhánh. Cơ chế unique index giải quyết tranh chấp claim đồng thời; **không** tự bảo vệ side effect ngoài transaction.

Tránh một lỗi tinh vi: nếu commit receipt `IN_PROGRESS` trước, rồi gọi nghiệp vụ và crash trước khi ghi `SUCCEEDED`, key bị treo. Thiết kế phải có lease/recovery, hoặc bảo đảm cập nhật nghiệp vụ và receipt trong một transaction chung để retry sau rollback có thể bắt đầu lại. Không nên giữ transaction mở hàng phút/giờ chỉ để khóa một task dài: khóa lâu tạo contention và giữ connection.

### Tác vụ dài: lease, token và chống worker cũ

Khi task mất nhiều thời gian, worker có thể claim kèm `lease_until` và gia hạn định kỳ. Sau thời hạn, worker khác được claim lại. Tuy nhiên **lease hết hạn không làm worker cũ ngừng chạy**. Nếu hai worker cùng thao tác, cần **fencing token** tăng đơn điệu qua mỗi lần claim và đưa token vào điều kiện ghi của tài nguyên được bảo vệ:

```text
Worker A nhận token 7 -> lease hết hạn
Worker B nhận token 8 -> bắt đầu xử lý
Worker A tỉnh dậy, cố ghi với token 7 -> hệ thống đích từ chối stale token
Worker B ghi với token 8 -> được chấp nhận
```

Ví dụ logic cập nhật có điều kiện: chỉ chấp nhận tác dụng khi token của worker còn hợp lệ với version/token hiện tại của tài nguyên. Cần đặt kiểm tra này **ở chính nơi thực hiện thay đổi**, trong cùng thao tác nguyên tử với thay đổi. Kiểm tra ở Java rồi ghi sau đó tạo một cửa sổ race mới. Token nội bộ cũng không chặn được email/API ngoài đã gửi; ranh giới ngoài cần cơ chế riêng.

## 6. Side effect ngoài database: outbox, inbox và downstream key

Transaction database không thể rollback email đã gửi hoặc một HTTP request đã được đối tác chấp nhận. Cửa sổ nguy hiểm:

```text
Worker -> đối tác chấp nhận yêu cầu -> phản hồi bị mất
Worker không biết đối tác đã xử lý -> retry -> đối tác nhận lần nữa
```

Nếu API đối tác hỗ trợ idempotency key, gửi **cùng key nghiệp vụ** ở mọi lần retry, đồng thời xác minh phạm vi, TTL và hành vi khi payload khác theo tài liệu của đối tác. Nếu đối tác không chống trùng, không thể hứa exactly-once effect chỉ nhờ khóa/map trong Java. Cân nhắc reconciliation (truy vấn trạng thái bằng external reference) hoặc thiết kế nghiệp vụ bù trừ, tùy mức rủi ro.

Với event/message, thường dùng hai lớp:

1. **Transactional outbox (bên phát):** ghi thay đổi nghiệp vụ **và** bản ghi outbox có `event_id` ổn định trong cùng transaction. Dispatcher có thể gửi event nhiều lần; đánh dấu đã gửi sau khi publish không loại bỏ hoàn toàn khả năng gửi trùng.
2. **Idempotent inbox/consumer (bên nhận):** ghi `event_id` vào bảng có unique constraint **trong cùng transaction với xử lý nghiệp vụ**. Nếu trùng, bỏ qua hoặc trả kết quả cũ. Nếu consumer gọi hệ thống ngoài, tiếp tục cần key/kiểm soát tại hệ thống ngoài.

Ví dụ chuyển trạng thái một đơn hàng từ `READY` sang `SHIPPED`: dùng điều kiện `WHERE status = 'READY'` khi cập nhật, tạo outbox event với `event_id` ổn định trong cùng transaction; bản tin gửi lại không khiến consumer áp dụng tác dụng thứ hai nếu inbox và cập nhật của consumer cùng transaction. Nếu thứ tự sự kiện có ý nghĩa, kiểm tra thêm version/sequence; chống trùng **không** tự bảo đảm đúng thứ tự.

## 7. Retry, lỗi và kết quả có thể quan sát

Thiết kế chính sách retry dựa trên **lỗi và trạng thái side effect**, không chỉ số lần thất bại.

| Tình huống | Cách xử lý |
|---|---|
| Lỗi chắc chắn xảy ra trước side effect, transaction rollback | Có thể retry cùng key |
| Side effect cùng transaction đã commit nhưng response mất | Đọc receipt và trả lại kết quả; không thực thi lại |
| Lỗi tạm thời, chưa rõ đối tác đã xử lý hay chưa | Tra cứu bằng key/reference hoặc retry bằng idempotency key được đối tác hỗ trợ |
| Payload mới dùng lại key cũ | Từ chối và báo lỗi rõ ràng |
| Đang có worker xử lý | Chờ có timeout, trả pending hoặc cho khách hàng poll; không sinh worker thứ hai |
| Lỗi nghiệp vụ cố định (thiếu quyền, dữ liệu không hợp lệ) | Không retry vô hạn; lưu trạng thái/đặc tả lỗi thích hợp |
| Lease hết hạn | Takeover có fencing và phục hồi trạng thái trung gian an toàn |

Backoff có jitter giảm retry đồng loạt; max attempts và dead-letter queue (nếu dùng queue) tránh vòng lặp vô hạn. **Retry giữ nguyên key** và nội dung logic. Cẩn thận khi hủy task: `Future.cancel(true)` chỉ yêu cầu ngắt, không thể hoàn tác side effect đã commit. Thiết kế operation ID cho phép kiểm tra kết quả thật trước khi xác nhận thất bại.

Không xóa receipt ngay khi task thành công để “tiết kiệm bộ nhớ” nếu vẫn còn cửa sổ replay. Chính sách lưu nên dựa trên thời gian retry tối đa, thời gian giữ message, khả năng phục hồi dữ liệu, hợp đồng API và nhu cầu đối soát.

## 8. Những lỗi thiết kế thường gặp

- **Chỉ dựa vào `synchronized`, `ReentrantLock` hoặc một static map:** không bảo vệ qua nhiều JVM hay restart.
- **Check-then-act:** kiểm tra “đã xử lý?” rồi ghi ở bước khác mà thiếu unique constraint/transaction.
- **Tạo key mới khi retry:** khiến mọi lần thử có vẻ là yêu cầu mới.
- **Cùng key, payload thay đổi:** trả nhầm kết quả cũ hoặc áp dụng side effect của nội dung mới.
- **Ghi `SUCCEEDED` trước side effect:** crash khiến tác vụ bị bỏ sót. Ghi side effect trước receipt ở hai transaction riêng lại cho phép thực thi trùng.
- **Đánh dấu `IN_PROGRESS` rồi không có recovery:** task kẹt mãi khi worker chết.
- **Tin rằng TTL/lease là khóa tuyệt đối:** worker cũ có thể còn chạy sau khi lease hết hạn.
- **Giả định queue/Future/HTTP timeout cho biết chắc có hay không có side effect:** trạng thái có thể chưa xác định.
- **Dùng `putIfAbsent` nhưng side effect chạy trước khi insert:** cả hai caller vẫn thực thi.
- **Coi database commit là đủ cho API ngoài:** cần idempotency/reconciliation tại downstream.

## 9. Checklist thiết kế và kiểm thử

Trước khi triển khai, trả lời rõ: một “cùng yêu cầu” được nhận ra bằng trường nào? Receipt và dữ liệu nghiệp vụ có cùng transaction không? Nếu hai instance nhận cùng key đồng thời, ai thắng? Nếu một worker chết ở từng điểm giữa claim, side effect, commit, ack thì worker mới quan sát gì? Nếu đối tác đã nhận nhưng trả timeout thì hỏi lại bằng gì? Bao giờ key được phép hết hạn? Có cách nào chặn worker cũ sau takeover?

Kiểm thử nên có cả **interleaving thực tế**, không chỉ gọi hai lần tuần tự:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Gọi cùng key tuần tự 2–10 lần | Một side effect, mọi lần có kết quả tương đương |
| 50–100 caller đồng thời với cùng key | Một claim thành công; các caller còn lại không làm thêm effect |
| Cùng key nhưng payload khác | Báo lỗi, không trả nhầm kết quả |
| Hai JVM/worker cạnh tranh | Unique/conditional claim vẫn bảo vệ được |
| Crash trước transaction commit | Rollback; retry có thể xử lý |
| Commit thành công nhưng mất response/ack | Retry lấy receipt/result, không xử lý lại |
| Crash sau claim `IN_PROGRESS` | Lease/recovery lấy lại task, không để kẹt |
| Lease hết hạn khi worker cũ còn chạy | Stale token bị từ chối tại nơi ghi |
| Gửi event lặp, event đến đảo thứ tự | Inbox chặn duplicate; version/sequence chặn cập nhật lùi |
| TTL hết, retry rất muộn | Hành vi được xác định và không làm phát sinh tác dụng ngoài hợp đồng |

Khi chạy production, theo dõi các chỉ số như `claim_success`, `duplicate_seen`, `key_payload_conflict`, `in_progress_age`, `retry_count`, `stale_fence_rejected` và độ trễ end-to-end. Log bằng key/operation ID đã được xử lý an toàn, tránh ghi dữ liệu nhạy cảm. Tỉ lệ duplicate tăng đột biến có thể báo hiệu mất ack, timeout hoặc vòng retry bị lỗi.

## 10. Chọn cơ chế theo phạm vi bảo đảm

| Phạm vi | Công cụ phù hợp | Giới hạn |
|---|---|---|
| Nhiều thread trong **một JVM** | `ConcurrentHashMap` + `FutureTask`, atomic CAS, lock | Không bền qua restart/khác JVM |
| Nhiều process, side effect nằm trong **một DB** | Unique key, transaction, receipt/result | Cần giải quyết transaction dài và trạng thái pending |
| Worker dài, có takeover | Lease + fencing token + conditional write | Token phải được thực thi ở tài nguyên đích |
| Message/event có thể phát lại | Transactional outbox + idempotent inbox | Có thể còn duplicate khi chuyển qua hệ thống ngoài |
| API/email/thanh toán ngoài | Downstream idempotency key, external reference, reconciliation | Phụ thuộc khả năng bảo đảm của đối tác |

**Nguyên tắc cốt lõi:** cho phép task chạy lại, nhưng đặt rào bảo vệ nguyên tử và bền vững **ở đúng nơi side effect được ghi nhận**. Single-flight trong Java tối ưu công việc trùng; transaction/unique key bảo vệ tác dụng trong database; outbox/inbox và hợp đồng với hệ thống ngoài mở rộng bảo đảm qua các ranh giới. Luôn thiết kế cho tình huống kết quả đã thành công nhưng tín hiệu xác nhận bị mất.
