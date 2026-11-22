# Thiết lập kịch bản đọc dữ liệu cũ và đối chiếu bảo đảm nhất quán

Một người dùng xác nhận booking thành công. Cơ sở dữ liệu NoSQL chính đã ghi trạng thái CONFIRMED, phiên bản 2, nhưng API đọc qua một replica, cache hoặc chỉ mục dẫn xuất vẫn trả PENDING, phiên bản 1. Đây là hiện tượng **đọc dữ liệu cũ (stale read)**. Cùng một kết quả có thể đúng trong hợp đồng eventual consistency hoặc sai nếu API đã hứa read-your-writes, monotonic reads hay linearizable read.

Bài thuộc **Database No SQL → Thực hành tổng hợp**. Mục tiêu là thiết lập thí nghiệm có thể tái hiện, xác định chính xác trạng thái cũ, đối chiếu các mô hình nhất quán và ghi bằng chứng kiểm thử.

> **Nguyên tắc:** Không gọi read là stale khi chưa xác định được **write nào đã commit**, **mốc nào làm chuẩn**, **đường đọc nào trả phiên bản cũ** và **bảo đảm nào được áp dụng**. Một read stale không có nghĩa write bị mất. Một timeout khi ghi không có nghĩa server chắc chắn rollback.

> **Ranh giới:** Lab Java 21 phía dưới kiểm soát source và projection trong cùng tiến trình, tạo stale read một cách quyết định. Nó minh họa logic kiểm chứng, không chứng minh cơ chế phân tán/quorum của MongoDB, Cassandra, DynamoDB hay Redis. Muốn kết luận native engine, phải chạy integration test theo đúng phiên bản, topology, read concern/consistency level và fault model.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

- Xây timeline source v1 → commit v2, trong khi view vẫn v1.
- Tạo fixture có tenantId, bookingId, sourceVersion, deleted và eventId.
- Viết oracle PASS/FAIL/INCONCLUSIVE.
- Đối chiếu eventual, read-your-writes, monotonic, causal, sequential, linearizable, bounded staleness và snapshot reads.
- Dùng Java 21 tạo event gate, session minVersion, fallback và chống stale replay.
- Biết cách thử MongoDB source/view, secondary read, DynamoDB GSI, Cassandra consistency level, Redis cache, search/CDC.
- Đo freshness, stale-read fraction, unknown commits và recovery time.
- Phân biệt lỗi dữ liệu cũ, lost update, dirty read và timeout.

## 2. Hệ thống mẫu

Giả sử Booking API có:
- Authoritative source: lưu booking và version nghiệp vụ.
- Outbox/CDC: phát sự kiện sau commit.
- Read projection: phục vụ timeline theo customer.
- Redis cache: đọc booking detail.
- Search index: tìm kiếm, được phép trễ.
- Java API và client sessions.

~~~mermaid
flowchart LR
    C["Client session"] --> A["Java API"]
    A --> S[("Authoritative source")]
    S --> E["Outbox / CDC"]
    E --> W["Projection worker"]
    W --> V[("Read projection")]
    A --> V
    A --> R[("Redis cache")]
    W --> I[("Search index")]
    A --> I
    A -. "Session fallback" .-> S
~~~

Một sản phẩm database có thể cung cấp nhiều đường đọc có consistency khác nhau. Đọc qua primary, follower, global secondary index, global table ở region khác và search index không tự có cùng guarantee.

### 2.1. Dữ liệu v1

~~~json
{
  "tenantId":"T-7",
  "bookingId":"B-91",
  "status":"PENDING",
  "sourceVersion":1,
  "deleted":false,
  "updatedAt":"2026-11-14T09:00:00Z"
}
~~~

### 2.2. Dữ liệu v2

~~~json
{
  "tenantId":"T-7",
  "bookingId":"B-91",
  "status":"CONFIRMED",
  "sourceVersion":2,
  "deleted":false,
  "updatedAt":"2026-11-14T09:01:00Z"
}
~~~

Mốc để so là **sourceVersion của cùng logical key**, không phải đơn thuần updatedAt. Timestamps từ nhiều hosts có thể lệch clock hoặc khác precision. Một booking A v100 không có nghĩa mới hơn booking B v2 trong một thứ tự toàn hệ.

## 3. Kịch bản đọc cũ có thể tái hiện

~~~text
t0 Source B-91 = PENDING v1
   View   B-91 = PENDING v1

t1 Client A gửi confirm expectedVersion=1
t2 Source commit CONFIRMED v2
t3 Client A nhận ACK confirmed version 2

t4 Đọc source -> CONFIRMED v2
t5 Đọc view   -> PENDING v1
t6 Consumer nhận và áp event v2
t7 Đọc view   -> CONFIRMED v2
~~~

Tại t5, view là bản sao chậm hơn source. Để đánh giá **vi phạm hay không**, cần hỏi:
- Client nào đọc?
- Đã nhận ACK v2 chưa?
- Read có bắt đầu sau ACK không?
- Đọc nguồn nào và với consistency option nào?
- API có hứa RYW/strong/linearizable không?
- Nếu eventual, freshness bound là bao nhiêu?

### 3.1. Vì sao dùng event gate?

Nếu chỉ ghi vào database rồi đọc follower ngay, lag có thể xuất hiện hoặc không. CI dễ flaky. Chủ động giữ consumer chưa apply event v2 khiến view chắc chắn v1; sau đó chủ động thả event để kiểm tra convergence.

### 3.2. Không đánh đồng cố ý giữ projection với native replica lag

Cùng nhìn thấy v1 nhưng nguyên nhân khác nhau:
- Projection CDC chậm.
- Replica replication chậm.
- Cache stale.
- GSI eventual.
- Search chưa refresh.
- Application query nhầm namespace/region.

Thí nghiệm phải báo chính xác loại nào.

## 4. Bảng so sánh các bảo đảm nhất quán

| Bảo đảm | Ý nghĩa | Source v2, read v1 có thể hợp lệ? |
| --- | --- | --- |
| Eventual consistency | Khi ngừng ghi và hệ khỏe, các bản sao cuối cùng hội tụ; không có giới hạn thời gian mặc định | Có trong giai đoạn trễ |
| Read-your-writes | Session phải nhìn thấy writes của chính mình theo hợp đồng | Không nếu chính session đã viết v2 |
| Monotonic reads | Cùng session đã đọc v2 thì lần sau không đọc lùi v1 | Không trong cùng session |
| Monotonic writes | Thứ tự các writes của cùng session được bảo toàn | Không tự bảo đảm latest reads |
| Writes-follow-reads | Write tiếp theo giữ được phụ thuộc với dữ liệu đã đọc | Phụ thuộc lịch sử |
| Causal consistency | Hiệu ứng không được thấy trước nguyên nhân trong causal context | Có với cập nhật không liên quan |
| Sequential consistency | Có thứ tự chung tôn trọng program order từng process, không buộc real-time order liên process | Có trong một số lịch |
| Linearizability | Tôn trọng real-time precedence, mỗi operation atomic giữa invoke/response | Không nếu read bắt đầu sau confirmed write v2 |
| Bounded staleness | Độ trễ không vượt giới hạn thời gian hoặc phiên bản được định nghĩa | Có khi chưa vượt bound |
| Snapshot isolation | Một transaction đọc snapshot nhất quán, có thể bắt đầu trước write | Có thể hợp lệ với snapshot cũ |

### 4.1. Strong consistency không phải một cấu hình toàn cục

Tên gọi strong có thể chỉ một API nhất định. Cần ghi chính xác nghĩa linearizable, serializable, snapshot, base-table strong read, session consistency hay quorum-read contract của engine.

### 4.2. Eventual không tự có bound 5 giây

Nếu sản phẩm đặt freshness SLO 5 giây, đó là yêu cầu ứng dụng phải đo và vận hành. Eventual consistency không tự hứa tất cả reads sẽ hội tụ trong 5 giây.

## 5. Thiết kế oracle

Một test nên có:
- **Given:** nguồn B-91 v1 và view v1.
- **When:** source commit v2, event chưa phát tới view.
- **Observe:** source read v2, view read v1.
- **Then:** kết luận theo guarantee của từng read path.
- **Recovery:** apply event v2, chờ hội tụ.
- **Safety:** event v1 đến muộn không được ghi đè v2.
- **Deletion:** DELETE v3 không bị UPSERT v2 hồi sinh.

Bằng chứng nên gồm sourceVersion acknowledged, returnedVersion, path, client/session, timestamps, region/replica và consistency settings.

### 5.1. PASS, FAIL và INCONCLUSIVE

- PASS: hành vi khớp guarantee trong scope được kiểm thử.
- FAIL: có bằng chứng vi phạm guarantee hoặc invariant.
- INCONCLUSIVE: write UNKNOWN, read path không rõ, thiếu commit proof hoặc thời điểm thao tác chồng lấn.

Đừng đánh dấu PASS chỉ vì không có exception.

## 6. Java 21: tạo mô hình có thể chạy

Lab này gồm Source, Projection và SessionReader. Source xử lý đồng bộ để cung cấp mốc confirmed. Projection chỉ cập nhật khi test gọi apply. SessionReader giữ phiên bản tối thiểu đã thấy.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public final class StaleReadLab {

    public record Key(String tenantId, String bookingId) {
        public Key {
            if (tenantId == null || tenantId.isBlank()
                    || bookingId == null || bookingId.isBlank()) {
                throw new IllegalArgumentException("invalid key");
            }
        }
    }

    public record Booking(
            Key key,
            long sourceVersion,
            String status,
            boolean deleted
    ) {
        public Booking {
            Objects.requireNonNull(key);
            Objects.requireNonNull(status);
            if (sourceVersion < 1) {
                throw new IllegalArgumentException("version");
            }
        }
    }

    public static final class Source {
        private final Map<Key, Booking> rows = new HashMap<>();

        public synchronized void seed(Booking value) {
            if (rows.putIfAbsent(value.key(), value) != null) {
                throw new IllegalStateException("already exists");
            }
        }

        public synchronized Booking read(Key key) {
            Booking value = rows.get(key);
            if (value == null) {
                throw new IllegalStateException("missing");
            }
            return value;
        }

        public synchronized Booking change(
                Key key, long expected,
                String status, boolean deleted
        ) {
            Booking current = read(key);
            if (current.deleted()
                    || current.sourceVersion() != expected) {
                throw new IllegalStateException("conflict");
            }
            Booking next = new Booking(
                    key, Math.addExact(expected, 1),
                    status, deleted);
            rows.put(key, next);
            return next;
        }
    }

    public static final class Projection {
        private final Map<Key, Booking> rows = new HashMap<>();

        public synchronized void apply(Booking event) {
            Booking current = rows.get(event.key());
            if (current == null
                    || event.sourceVersion() > current.sourceVersion()) {
                rows.put(event.key(), event);
            } else if (event.sourceVersion()
                    == current.sourceVersion()
                    && !event.equals(current)) {
                throw new IllegalStateException(
                        "same version different payload");
            }
            // Older events do not overwrite newer events.
            // Deleted records remain as version tombstones here.
        }

        public synchronized Booking readRaw(Key key) {
            return rows.get(key);
        }
    }

    public static final class SessionReader {
        private final Source authority;
        private final Key key;
        private long minVersion = 0;

        public SessionReader(Source authority, Key key) {
            this.authority = Objects.requireNonNull(authority);
            this.key = Objects.requireNonNull(key);
        }

        public void observeWrite(Booking ack) {
            if (!ack.key().equals(key)) {
                throw new IllegalArgumentException("wrong entity");
            }
            minVersion = Math.max(
                    minVersion, ack.sourceVersion());
        }

        public Booking readWithFallback(Projection view) {
            Booking result = view.readRaw(key);
            if (result == null
                    || result.sourceVersion() < minVersion) {
                result = authority.read(key);
            }
            if (result.sourceVersion() < minVersion) {
                throw new IllegalStateException(
                        "minVersion not satisfied");
            }
            minVersion = Math.max(
                    minVersion, result.sourceVersion());
            return result;
        }
    }

    private static void require(boolean value, String reason) {
        if (!value) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) {
        Key key = new Key("T-7", "B-91");
        Source source = new Source();
        Projection view = new Projection();

        Booking v1 = new Booking(key, 1, "PENDING", false);
        source.seed(v1);
        view.apply(v1);

        // Write v2 is confirmed by the in-memory authority.
        Booking v2 = source.change(
                key, 1, "CONFIRMED", false);
        require(source.read(key).sourceVersion() == 2,
                "source should be v2");

        // CDC event is deliberately not applied yet.
        require(view.readRaw(key).sourceVersion() == 1,
                "expected stale projection v1");

        SessionReader session = new SessionReader(source, key);
        session.observeWrite(v2);
        Booking afterWrite = session.readWithFallback(view);
        require(afterWrite.sourceVersion() >= 2,
                "RYW violated");

        // Release the event and then replay an older event.
        view.apply(v2);
        require(view.readRaw(key).sourceVersion() == 2,
                "view did not converge");
        view.apply(v1);
        require(view.readRaw(key).sourceVersion() == 2,
                "version regressed");

        // A deletion at v3 must survive delayed UPSERT v2.
        Booking v3 = source.change(
                key, 2, "CONFIRMED", true);
        view.apply(v3);
        view.apply(v2);
        require(view.readRaw(key).deleted(),
                "deleted booking resurrected");
        require(view.readRaw(key).sourceVersion() == 3,
                "tombstone version changed");

        System.out.println(
                "PASS: stale v1, RYW v2, convergence v2, " +
                "no regression, no resurrection");
    }
}
~~~

### 6.1. Chạy chương trình

Trong một thư mục thực hành với Java 21:

~~~bash
javac StaleReadLab.java
java StaleReadLab
~~~

Output mong đợi:

~~~text
PASS: stale v1, RYW v2, convergence v2, no regression, no resurrection
~~~

### 6.2. Ý nghĩa

- Read projection trả v1 trong khi authority đã v2.
- Session minVersion=2 không chấp nhận v1: fallback authority.
- Event v2 khiến projection hội tụ.
- Event v1 đến muộn không rollback.
- Delete v3 được giữ lại làm tombstone, không hồi sinh.

### 6.3. Giới hạn

Đây là chương trình đơn tiến trình:
- synchronized không thay replication/quorum.
- Không đo durability hoặc failover.
- Chưa có idempotency ledger cho create booking.
- minVersion chỉ áp cho một key.
- Tombstone giữ vô hạn trong lab, không phải retention policy production.
- Không đo stale duration theo SLO.

Nó giúp xây **oracle đúng trước khi cấu hình các tests phân tán**.

## 7. JUnit Jupiter: ba test độc lập

Có thể dùng cùng các kiểu public trong StaleReadLab:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class StaleReadLabTest {

    @Test
    void viewCanBeOlderThanConfirmedSource() {
        var key = new StaleReadLab.Key("T-7", "B-91");
        var source = new StaleReadLab.Source();
        var view = new StaleReadLab.Projection();

        var v1 = new StaleReadLab.Booking(
                key, 1, "PENDING", false);
        source.seed(v1);
        view.apply(v1);

        var v2 = source.change(
                key, 1, "CONFIRMED", false);

        assertEquals(2, source.read(key).sourceVersion());
        assertEquals(1, view.readRaw(key).sourceVersion());

        view.apply(v2);
        assertEquals(2, view.readRaw(key).sourceVersion());
    }

    @Test
    void sessionReadCannotGoBelowOwnWrite() {
        var key = new StaleReadLab.Key("T-7", "B-91");
        var source = new StaleReadLab.Source();
        var view = new StaleReadLab.Projection();

        var v1 = new StaleReadLab.Booking(
                key, 1, "PENDING", false);
        source.seed(v1);
        view.apply(v1);
        var v2 = source.change(
                key, 1, "CONFIRMED", false);

        var session = new StaleReadLab.SessionReader(source, key);
        session.observeWrite(v2);

        assertTrue(session
                .readWithFallback(view).sourceVersion() >= 2);
    }

    @Test
    void lateUpsertCannotUndoDeletion() {
        var key = new StaleReadLab.Key("T-7", "B-91");
        var source = new StaleReadLab.Source();
        var view = new StaleReadLab.Projection();

        var v1 = new StaleReadLab.Booking(
                key, 1, "PENDING", false);
        source.seed(v1);
        view.apply(v1);

        var v2 = source.change(
                key, 1, "CONFIRMED", false);
        var v3 = source.change(
                key, 2, "CONFIRMED", true);

        view.apply(v3);
        view.apply(v1);
        view.apply(v2);

        assertEquals(3, view.readRaw(key).sourceVersion());
        assertTrue(view.readRaw(key).deleted());
    }
}
~~~

Các tests này chủ ý có **dữ liệu ít nhưng phân biệt rõ hành vi**. Không thay unit lab bằng một tập dữ liệu random lớn chưa có oracle.

## 8. Session read-your-writes

Client A:
1. POST confirm trả version 2.
2. GET booking detail qua projection mới version 1.
3. API có hợp đồng RYW.

Để pass:
- Đọc trực tiếp authority, hoặc
- Mang minVersion=2 vào request.
- Chọn replica đủ watermark.
- Chờ projection đạt v2 với deadline.
- Fallback authority nếu view chưa đủ.
- Trả explicit not-ready/error nếu không đáp ứng, theo policy.

### 8.1. minVersion không tự tạo guarantee

Một header mang minVersion=2 nhưng server vẫn trả v1 là lỗi nếu API hứa RYW. Server **phải so returnedVersion với requiredVersion**.

### 8.2. Token phải gắn quyền

- minVersion thuộc tenant/key cụ thể.
- Không bỏ tenant filter khi fallback.
- Không dùng token của tenant khác.
- Có kiểm soát đối với token không hợp lệ hoặc quá lớn.
- Nếu dùng opaque token, bảo vệ chữ ký/expiry theo thiết kế.

### 8.3. RYW ở API không đồng nghĩa projection strong

Một API đạt RYW bằng fallback có thể vẫn dùng eventual projection cho traffic khác. Report cần tách **bảo đảm API** và **bảo đảm store**.

## 9. Monotonic reads

Session B không phải người ghi, nhưng:
- B đọc replica R1 thấy v2.
- B chuyển sang R2 thấy v1.

Nếu API hứa monotonic reads, v2→v1 là vi phạm. Nếu API chỉ eventual không mang session context, read lùi có thể được phép.

Các cơ chế:
- Session watermark/minVersion.
- Sticky read routing với failover policy.
- Read from a sufficiently caught-up replica.
- Bounded wait, source fallback hoặc explicit error.

**Sticky routing đơn thuần** không tự chứng minh monotonic qua replica restart, region switch hay internal rollback; cần đúng guarantee của engine hoặc check version.

## 10. Linearizability và thời gian thực

Linearizability yêu cầu mỗi operation có thể được đặt tại một điểm atomic giữa invoke/response và tôn trọng thứ tự real-time của các operations không overlap.

~~~text
W2 invoked ------- W2 confirmed
                              |
                              R3 invoked ----- R3 returns v1
~~~

Nếu R3 bắt đầu sau W2 đã hoàn tất, không có write khác làm trạng thái quay về v1, và R3 là đường đọc hứa linearizable cho cùng logical object, thì v1 là vi phạm.

### 10.1. Khi operations overlap

~~~text
W2 invoked ------------ W2 confirmed
       R3 invoked -------- R3 returns v1
~~~

R3 có thể được linearize trước W2; một giá trị cũ không tự là vi phạm.

### 10.2. Không so nanoTime giữa hai hosts

System.nanoTime không có mốc chung giữa machines. Một test controller có thể đợi W2 confirmed rồi mới gửi R3 để tạo ordering đáng tin. Với logs phân tán, cần clock-uncertainty awareness.

### 10.3. Sequential consistency

Sequential consistency yêu cầu tồn tại một thứ tự toàn cục tôn trọng program order của từng process nhưng không nhất thiết real-time precedence giữa processes độc lập. Vì vậy có những lịch cross-client mà sequential cho phép read v1 dù W2 hoàn tất trước thời điểm read theo đồng hồ thực. Không đánh đồng sequential và linearizable.

## 11. Causal consistency: nhìn thấy nguyên nhân trước hệ quả

Hai events:
- E1: Booking B-91 confirmed v2.
- E2: Notification N-1 được tạo vì booking confirmed, dependency B-91 >= v2.

Nếu read model hiển thị N-1 nhưng chưa hiển thị E1 trong cùng causal context, có thể vi phạm causal consistency đã hứa.

### 11.1. Thực hành

1. Seed booking v1.
2. Commit E1 booking v2.
3. Tạo notification N-1 mang dependency E1.
4. Trì hoãn event E1 nhưng cho E2 tới consumer.
5. Causal-aware consumer chưa được publish N-1 như độc lập.
6. Apply E1, sau đó publish E2.
7. Assert reader không thấy effect trước cause.

### 11.2. Concurrent operations

Hai writes độc lập không có causal relationship có thể được quan sát khác thứ tự. Causal consistency không tự tạo một total order toàn hệ.

### 11.3. Một per-key sourceVersion chưa đủ

Multi-key causal dependencies có thể cần session tokens, dependency vectors hoặc commit frontier phù hợp. updatedAt không mã hóa đầy đủ happens-before.

## 12. Bounded staleness và freshness

Có thể định nghĩa:
- maxVersionLag = k phiên bản cho cùng key, hoặc
- maxVisibilityDelay = Δ giây từ mốc commit theo định nghĩa, hoặc
- một model bounded staleness khác do engine cung cấp.

Không được tự suy từ eventual ra Δ=5 giây.

### 12.1. Version lag khác time lag

Source v100, view v99 có thể trễ 20 phút nếu một key hiếm ghi. Source v200, view v150 có thể chỉ trễ 200 ms trong một burst lớn. Chọn metric phù hợp nghiệp vụ.

### 12.2. Bounded polling

Một phép thử:
1. Ghi sourceVersion confirmed=2.
2. Ghi mốc bắt đầu đo.
3. Poll đúng read projection với interval có giới hạn.
4. Nếu observedVersion>=2 trước deadline, ghi time-to-visible.
5. Nếu hết deadline, FAIL freshness SLO và giữ latest observedVersion.
6. Không fallback source trong test **đang đo độ mới của projection**, vì làm vậy sẽ che lag.

### 12.3. Đo p99 cần nhiều samples

Một lần converged trong 100 ms chưa chứng minh p99 ≤5 giây. Cần nhiều writes, phân bố tenants/partitions/regions, loại trừ kết luận ngụy từ completed-only samples và theo dõi timeouts.

## 13. Bounded wait bằng Java

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

public final class WaitForVersion {
    private WaitForVersion() {}

    public static boolean until(
            LongSupplier readVersion,
            long minVersion,
            Duration deadlineBudget,
            Duration pollInterval
    ) throws InterruptedException {
        long budget = deadlineBudget.toNanos();
        long step = pollInterval.toNanos();

        if (budget <= 0 || step <= 0) {
            throw new IllegalArgumentException("invalid duration");
        }

        long start = System.nanoTime();

        while (true) {
            if (readVersion.getAsLong() >= minVersion) {
                return true;
            }

            long elapsed = System.nanoTime() - start;
            long remaining = budget - elapsed;
            if (remaining <= 0) {
                return false;
            }

            TimeUnit.NANOSECONDS.sleep(
                    Math.min(step, remaining));
        }
    }
}
~~~

Đoạn code giả định readVersion trả long hợp lệ và không lỗi. Production cần xử lý timeout/cancellation/errors, source unavailable và resource limits. Không poll hàng nghìn requests mỗi millisecond làm quá tải chính projection đang đo.

## 14. MongoDB: tái hiện source và view ở hai collections

Đây là ví dụ ứng dụng dùng MongoDB làm **source và derived collection riêng**, không phải test native MongoDB secondary lag.

Chỉ chạy trong test database cô lập. Các commands ví dụ cho mongosh:

### 14.1. Seed v1

~~~javascript
use stale_read_lab_586

db.sourceBookings.insertOne({
  _id: "T-7#B-91",
  tenantId: "T-7",
  bookingId: "B-91",
  status: "PENDING",
  sourceVersion: 1,
  deleted: false
})

db.bookingReadView.insertOne({
  _id: "T-7#B-91",
  tenantId: "T-7",
  bookingId: "B-91",
  status: "PENDING",
  sourceVersion: 1,
  deleted: false
})
~~~

### 14.2. Confirm source v2

~~~javascript
const result = db.sourceBookings.updateOne(
  {
    _id: "T-7#B-91",
    tenantId: "T-7",
    sourceVersion: 1,
    deleted: false
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { sourceVersion: 1 }
  }
)
printjson(result)
printjson(
  db.sourceBookings.findOne({ _id: "T-7#B-91" })
)
~~~

Khi matchedCount=1 và thao tác có confirmed outcome theo write settings, source ở v2.

### 14.3. Đọc projection trước khi apply

~~~javascript
printjson(
  db.bookingReadView.findOne({ _id: "T-7#B-91" })
)
~~~

Projection giữ v1. Đó là lag **do thí nghiệm chưa cập nhật view**, không phải bằng chứng read concern MongoDB sai.

### 14.4. Đồng bộ v2

~~~javascript
const applied = db.bookingReadView.updateOne(
  {
    _id: "T-7#B-91",
    tenantId: "T-7",
    sourceVersion: 1
  },
  {
    $set: {
      status: "CONFIRMED",
      sourceVersion: 2,
      deleted: false
    }
  }
)
printjson(applied)
printjson(
  db.bookingReadView.findOne({ _id: "T-7#B-91" })
)
~~~

View giờ đạt v2. Consumer thật cần version-aware apply, idempotent event handling và tombstone; đây mới là một update minh họa.

### 14.5. Stale event không được overwrite

~~~javascript
const ignored = db.bookingReadView.updateOne(
  {
    _id: "T-7#B-91",
    tenantId: "T-7",
    sourceVersion: { $lt: 1 }
  },
  {
    $set: {
      status: "PENDING",
      sourceVersion: 1
    }
  }
)
printjson(ignored)
~~~

Expected matchedCount=0 vì view đang v2. Trong ứng dụng thật, không tự bật upsert với filter version nhỏ hơn rồi tưởng đã giải quyết missing records; có thể gặp duplicate-key race. Cần protocol insert-if-absent/CAS/reconcile phù hợp.

## 15. MongoDB: primary vs secondary

Để kiểm tra native consistency:
1. Dựng replica set thử nghiệm đủ nodes.
2. Ghi writeConcern và readConcern/readPreference được hỗ trợ.
3. Xác nhận write v2 và ACK.
4. Đọc primary/secondary theo đúng path.
5. Thu node, role, sourceVersion và latency.
6. Nếu muốn tạo lag, dùng approved fault injection trong isolated lab.
7. Heal và đo catch-up.
8. Đánh giá theo tài liệu guarantee của phiên bản.

### 15.1. ReadConcern majority không mặc nhiên là linearizable

Các mức read concern và read preference khác nhau. Cần phân biệt linearizable read trong điều kiện được hỗ trợ với majority reads và secondary reads. Đừng lấy cùng nhãn strong cho tất cả.

### 15.2. Causal session phải được dùng thật

Nếu muốn RYW/causal session guarantees theo cơ chế MongoDB hỗ trợ, cần:
- Một session thực cho các operations liên quan.
- Read/write concerns phù hợp.
- Truyền session vào cả write/read.
- Không bỏ session context khi chuyển driver/API layer.

### 15.3. Một lần không thấy stale không chứng minh replica luôn mới

Secondary có thể bắt kịp trước read. Muốn tạo stale chắc chắn, kiểm soát derived projection; muốn đánh giá native guarantees, cần topology/fault/lịch sử phù hợp.

## 16. DynamoDB: base table, GSI và global tables

DynamoDB cần phân biệt:
- Base table GetItem có thể yêu cầu strongly consistent read theo phạm vi hỗ trợ.
- Eventually consistent base table read có thể trả phiên bản cũ.
- GSI được cập nhật bất đồng bộ, không có strongly consistent read giống base table.
- Multi-region Global Tables có replication/conflict semantics khác region-local reads.

### 16.1. Kịch bản

1. Seed item sourceVersion=1.
2. Update item lên v2 có condition expectedVersion=1.
3. GetItem trên base table với ConsistentRead theo hỗ trợ.
4. Query GSI, ghi sourceVersion thấy được.
5. Poll bounded tới v2, đo time-to-visible.
6. Lặp để đo distribution.

### 16.2. GSI có thể đã bắt kịp

Một lần query GSI trả v2 ngay không chứng minh nó strong. Một lần trả v1 có thể là hành vi eventual hợp contract, nhưng vẫn có thể vi phạm ứng dụng nếu SLO freshness quá chặt.

### 16.3. Đừng đọc GSI để kết luận write rollback

GSI miss không chứng minh source item chưa commit. Với timeout khi write, đọc base table/operation ledger theo consistency phù hợp để reconcile.

## 17. Cassandra: ONE và LOCAL_QUORUM

Một lab Cassandra có RF=3 trong một datacenter:
- Seed key K v1.
- Xác định replicas sở hữu partition của K.
- Trì hoãn một replica trong lab.
- Write v2 ở consistency level được chọn.
- Read tại ONE, LOCAL_QUORUM và ghi kết quả.
- Heal, quan sát repair/catch-up.
- So oracle theo topology, replica ownership và level thực tế.

### 17.1. Quorum không bảo đảm một cách máy móc mọi lần đọc latest

Các giả định về membership, coordinator, consistency levels, repair, concurrent writes và timestamp conflict rất quan trọng. Không tự dùng R+W>N như bằng chứng universal về linearizability.

### 17.2. Storage timestamp khác sourceVersion

Cassandra timestamp conflict resolution có thể ghi đè một field chứa version nếu stale write mang timestamp thắng. Nếu domain cần CAS, dùng conditional/LWT hoặc protocol phù hợp, không chỉ thêm số version.

### 17.3. Multi-DC

LOCAL_QUORUM khác QUORUM. Test cần biết datacenter/replica placement, không kill một node bất kỳ rồi suy nó là replica của key.

## 18. Redis: replica và cache stale fill

Có thể kiểm tra:
- Primary vs replica GET.
- Cache key v1 sau source v2.
- Invalidation delayed.
- Stale fill race.
- Failover và Redis persistence.
- TTL/negative cache.

### 18.1. Stale-fill race

~~~text
t0 Reader R1 miss cache, đọc source v1
t1 R1 dừng trước SET cache
t2 Writer ghi source v2
t3 Invalidate cache
t4 R1 SET cache v1
t5 Reader R2 hit cache v1
~~~

Đây là race ở application cache, không nhất thiết do replica lag. Test phải kiểm tra versioned cache fill, generation counter hoặc cơ chế tương ứng.

### 18.2. Read-your-writes với cache

Nếu session minVersion=2 và cache entryVersion=1, API không được trả v1 như kết quả đúng khi hứa RYW; phải fallback/chờ/refuse.

### 18.3. Redis replication không là transaction consensus toàn cục

Cơ chế replica ACK/WAIT và failover có giới hạn; không tự suy mọi acknowledged write sẽ tồn tại qua mọi failure. Xem durability contract theo phiên bản và topology.

## 19. Search index: CDC lag và refresh lag

Một read search trả cũ có thể do:
- CDC event chưa được phát.
- Broker lag.
- Consumer offline.
- Index write chậm.
- Refresh chưa làm document visible.
- Alias còn trỏ index cũ.
- Query cache.

Đo các mốc:
1. Source commit.
2. Event emitted.
3. Consumer received.
4. Index write acknowledged.
5. Search first sees version 2.

### 19.1. Tách consistency và freshness

Một search index eventual có thể đúng contract nhưng trễ 30 giây trong khi SLO ứng dụng là 5 giây; khi đó **service-level freshness FAIL** dù model eventual không bị mô tả sai.

### 19.2. Version guard cho consumer

Event v3 có thể đến trước v2. Apply stale v2 sau v3 là data regression. Delete event v4 phải ngăn upsert v3 hồi sinh deleted record.

### 19.3. Search miss không chứng minh booking absent

Một UI tạo booking rồi tìm kiếm chưa thấy, không được retry create bằng operationId mới mà không reconcile authority.

## 20. Out-of-order và delete/tombstone

Events:
- E1: UPSERT B-91 v1 PENDING.
- E2: UPSERT B-91 v2 CONFIRMED.
- E3: DELETE B-91 v3.

Test các thứ tự:
- 1,2,3.
- 2,1,3.
- 3,2,1.
- 2,2,3.
- 1,3,2.

**Oracle:** nếu v3 deleted đã apply thì E2/E1 không hồi sinh B-91. Một UPSERT v4 hợp lệ theo business policy là trường hợp khác.

### 20.1. Tombstone có retention

Xóa vật lý và mất watermark có thể cho old backfill ghi lại v1. Cần tombstone/erasure ledger với retention đủ cho replay horizon và chính sách privacy.

### 20.2. Duplicate event idempotency

Nếu E2 phát hai lần, trạng thái cuối vẫn v2, không có side effect nghiệp vụ hai lần. Nếu hai events cùng sourceVersion nhưng payload khác, nên quarantine/reconcile thay vì chọn ngẫu nhiên.

### 20.3. Checkpoint

Consumer không checkpoint/ACK trước khi target durable apply theo contract. Crash giữa apply và ACK có thể làm delivery trùng; adapter phải idempotent.

## 21. Timeout và UNKNOWN commit

Một confirm request:
1. Server ghi v2.
2. ACK bị mất.
3. Client nhận timeout.
4. Client đọc GSI view v1.
5. Client suy sai write chưa commit.
6. Client retry với operationId khác và gây duplicate business effect.

Để xử lý:
- Giữ stable operationId/idempotency key.
- Reconcile authoritative source/operation ledger.
- Phân biệt CONFIRMED, REJECTED, UNKNOWN.
- Không dùng eventual index miss làm bằng chứng rollback.
- Không khẳng định read stale so với confirmed write nếu chưa có commit proof.

### 21.1. Điều kiện strong read

Một write đang pending và read overlap nó có thể trả v1 hợp lệ ngay cả khi linearizable, vì read có thể được linearize trước write. Phải tạo ordering write response trước read invocation nếu muốn test real-time precedence.

## 22. Snapshot read không đồng nghĩa latest read

Trong snapshot isolation, một transaction bắt đầu trước W2 có thể tiếp tục thấy v1 trong snapshot của nó sau khi W2 commit. Nếu đó là hợp đồng transaction, read v1 không tự là vi phạm.

### 22.1. Dirty read khác stale read

- Dirty read: quan sát dữ liệu chưa commit và có thể rollback.
- Stale read: quan sát trạng thái cũ so với mốc đã commit.
- Snapshot read: thấy trạng thái đúng tại snapshot mốc quá khứ.

### 22.2. Multi-shard snapshot

Không ghép read shard A ở t1 và shard B ở t2 rồi gọi là một globally consistent snapshot nếu không có cơ chế consistent cut.

## 23. Phân trang qua các replicas

API lấy timeline:
- Page 1 từ replica R1 đã thấy phiên bản mới.
- Page 2 từ R2 chưa cập nhật.
- Một số bookings có thể bị lặp hoặc thiếu nếu query/cursor không kiểm soát snapshot.

Fixture:
- B-003 @10:00.
- B-001 @09:00.
- B-002 @09:00.
- pageSize=2.
- Sort createdAt DESC, bookingId ASC.

Expected khi nguồn đứng yên:
- Page 1: B-003, B-001.
- Page 2: B-002.

### 23.1. Cursor không tự bảo đảm snapshot

Keyset cursor chỉ bảo vệ ordering dựa trên sort keys. Concurrent inserts/deletes có thể làm tập trang thay đổi. Nếu sản phẩm yêu cầu traversal consistent, cần snapshot/causal/session frontier hoặc công bố semantics live pagination.

## 24. Fault injection an toàn

Các faults có thể thử trong lab cô lập:
- Consumer pause/restart.
- Delay source→broker.
- Delay broker→projection.
- Block app→replica.
- Primary/follower failover.
- Network partition giữa regions.
- Cache outage.
- Index refresh delay.
- Lost ACK after write commit.

Mỗi fault ghi:
- Cạnh/hướng traffic.
- Thời lượng.
- Test namespace.
- Data seed.
- Target metrics.
- Expected oracle.
- Stop/cleanup.
- Người chịu trách nhiệm.

**Không inject các lệnh network phá kết nối lên host dùng chung hoặc production ngoài quy trình được phê duyệt.** Unit lab với event gate đủ để học sự khác biệt logic trước khi thử chaos trên cluster.

## 25. Metrics cần thu

| Metric | Ý nghĩa |
| --- | --- |
| confirmedSourceVersion | Mốc đã commit/ACK |
| observedVersion | Phiên bản đọc được |
| requiredMinVersion | Mốc của session |
| staleReadFraction | Stale / reads đủ điều kiện |
| versionLag | SourceVersion−ObservedVersion theo key |
| timeToVisibility | Commit→projection visible |
| oldestUnprocessedEventAge | Tuổi event backlog |
| CDC offset lag | Checkpoint còn chậm |
| RYW violations | Reads dưới minVersion |
| monotonic read violations | Phiên đọc lùi |
| tombstone resurrection | Bản ghi bị xóa tái xuất hiện trái policy |
| unknown write count | Writes chưa reconcile |
| retry amplification | Physical attempts / logical operations |
| crossTenantLeak | An toàn quyền truy cập |
| recoveryToSlo | Thời gian sau heal đến đạt SLO |

### 25.1. Không dùng average để che tenant nóng

Thu per-tenant tier, partition, region và read path. Một tenant lớn có thể bị lag hàng phút dù trung bình toàn hệ thấp.

### 25.2. Denominator phải rõ

Một read không biết authoritative frontier chưa thể phân loại stale chính xác; không tự tính nó là fresh chỉ vì không phát hiện mismatch.

### 25.3. Bounded polling thay sleep cố định

Poll cho đến version>=required hoặc deadline. Ghi elapsed và latest observedVersion khi fail. Không làm polling overload chính index đang đo.

## 26. Ma trận test tổng hợp

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Source=view=v1 | Baseline |
| T02 | Source confirmed v2, view gated v1 | Stale observation |
| T03 | Same-session write v2, view read v1 | RYW fallback/wait |
| T04 | Session read v2 rồi v1 | Monotonic violation nếu hứa |
| T05 | Linearizable read starts after ACK v2 | Không v1 |
| T06 | View receives event v2 | Converges v2 |
| T07 | Replay E1 after E2 | Không lùi version |
| T08 | Delete v3, replay E2 | Không resurrection |
| T09 | Duplicate event E2 | One logical effect |
| T10 | Lost ACK after commit | UNKNOWN rồi reconcile |
| T11 | Dependency notification after booking | Causal ordering |
| T12 | View lag >Δ | Bounded freshness failure |
| T13 | Cache invalidation then stale fill | Version guard |
| T14 | GSI lag | Eventual behavior/SLO |
| T15 | Native secondary lag | Theo read concern |
| T16 | Cassandra ONE/LOCAL_QUORUM | Theo topology/consistency |
| T17 | Redis replica lag | Theo replication contract |
| T18 | Search index lag | CDC/refresh breakdown |
| T19 | Cross-tenant same bookingId | Không leakage |
| T20 | Pagination across different replicas | Đúng snapshot/live contract |
| T21 | Region A write, B read | Theo region guarantees |
| T22 | View recover from old snapshot | Deletes preserved |
| T23 | Read timeout | Availability, không là stale value |
| T24 | Overlapping read/write | Phân tích history đúng |

## 27. Một report mẫu

~~~text
SCENARIO=STALE-READ-586-01
ENVIRONMENT=Java 21 deterministic model
KEY=T-7/B-91
SOURCE_WRITE=CONFIRMED v2
SOURCE_READ=CONFIRMED v2
VIEW_BEFORE_DELIVERY=PENDING v1
SESSION_MIN_VERSION=2
SESSION_READ=CONFIRMED v2 via fallback
VIEW_AFTER_DELIVERY=CONFIRMED v2
OLD_EVENT_REPLAY=v1 ignored
DELETE=v3 preserved after v2 replay
RESULT:
  STALE_REPRODUCTION=PASS
  RYW_APPLICATION_LOGIC=PASS_IN_MODEL
  CONVERGENCE_AFTER_EVENT=PASS_IN_MODEL
  NATIVE_REPLICA_GUARANTEES=NOT_TESTED
  BOUNDED_FRESHNESS_P99=NOT_MEASURED
~~~

### 27.1. Giới hạn báo cáo

Một simulation in-memory không chứng minh linearizability của cluster thật. Một lần view hội tụ không chứng minh p99 freshness. Một read thấy v2 không chứng minh mọi replicas đã hội tụ.

## 28. Runbook

### Bước 1 — Chốt hợp đồng

Nêu rõ read path, entity/key, consistency model, SLO và invariants.

### Bước 2 — Seed v1

Source và view đều chứa B-91 PENDING v1. Kiểm tra tenant scope.

### Bước 3 — Điều khiển delivery

Tạm dừng event-to-view trong lab; xác nhận consumer chưa apply event mới.

### Bước 4 — Commit v2

Dùng conditional expectedVersion=1. Nếu write timeout, reconcile trước.

### Bước 5 — Đọc source

Xác nhận authority ở v2 với read settings phù hợp.

### Bước 6 — Đọc view

Ghi v1, read path, phiên, timestamps, trace ID.

### Bước 7 — Đối chiếu

Eventual có thể cho v1; RYW/linearizable theo điều kiện không cho; monotonic không cho đọc lùi trong phiên; bounded cần đo Δ.

### Bước 8 — Kiểm tra session fallback

Dùng minVersion=2 và assert returnedVersion>=2 hoặc explicit failure theo contract.

### Bước 9 — Release event

Apply v2, poll bounded, đo convergence.

### Bước 10 — Replay/out-of-order/delete

Test v1 sau v2, v2 sau DELETE v3, duplicate event và missing event.

### Bước 11 — Native integration

Đổi từ fake sang MongoDB/Cassandra/DynamoDB/Redis/test cluster với read level, topology và versions đã ghi. Không ngoại suy từ fake.

### Bước 12 — Báo cáo

PASS/FAIL/INCONCLUSIVE theo guarantee, metric và evidence, bao gồm mọi giới hạn chưa chứng minh.

## 29. Bài tập

### A. Stale observation

Dựng source v2 và view v1. Khi nào là stale? Khi nào stale được phép?

### B. RYW

Session vừa ghi v2 nhưng view còn v1. Thiết kế minVersion token và fallback. Nếu source unavailable thì làm gì?

### C. Monotonic

Session thấy v2 ở replica R1 rồi v1 ở R2. Điều gì vi phạm? Làm sao giữ watermark?

### D. Linearizability

Viết lịch W2 completed trước R3 invoked. R3 trả v1. Khi nào đủ để kết luận? Nếu R3 overlap W2 thì sao?

### E. Sequential

Vì sao một thứ tự serial tôn trọng program order có thể khác thứ tự wall-clock giữa hai processes?

### F. Causal

Booking confirmed v2 tạo notification. Notification tới trước booking event. Phải giữ dependency thế nào?

### G. Bounded staleness

Tạo freshness SLO 5 giây, đo 1.000 synthetic writes, báo p99 và missing fraction.

### H. MongoDB

Tạo sourceBookings và bookingReadView, seed v1, source v2, view v1, apply v2. Vì sao đây không là test native secondary replication?

### I. DynamoDB

Giải thích base table strong read vs GSI eventual; làm sao đo convergence và tại sao GSI không bắt buộc stale trong lần query đầu?

### J. Cassandra

RF3 ONE/LOCAL_QUORUM, token replica ownership, write timestamp, LWT. Cần dữ liệu nào để xây oracle?

### K. Redis

Dựng stale cache fill race. Tại sao invalidation chưa đủ? Thiết kế version guard.

### L. Search

Phân biệt CDC lag, consumer backlog và refresh. Vì sao search miss không phải dấu hiệu tạo booking thất bại?

### M. Delete

Apply DELETE v3 rồi stale UPSERT v2. Cách ngăn resurrection và phục hồi từ snapshot cũ?

### N. UNKNOWN commit

Write mất ACK. Trước khi so stale, cần thu bằng chứng gì?

### O. Incident report

Viết report gồm source commit proof, observedVersion, read path, guarantee, verdict và phần chưa chứng minh.

### Hướng giải

- Tạo timeline có nguồn v2 được xác nhận và projection giữ v1.
- Tách **stale observation** khỏi **guarantee violation**.
- RYW/monotonic cần session minVersion hoặc cơ chế engine thực sự bảo vệ.
- Linearizable test cần write hoàn thành trước read invocation.
- Causal test giữ nguyên nhân–hệ quả.
- Eventual/bounded staleness phải đo time-to-visibility.
- Dùng version/tombstone guards khi replay.
- Không dựa index/cache để kết luận source write rollback.
- Thực hiện native replica tests trong môi trường cô lập với đúng cấu hình.
- Ghi kết quả có phạm vi, không tuyên bố quá bằng chứng.

## 30. Các ngộ nhận thường gặp

1. **Đọc v1 khi source v2 luôn là bug.** Có thể hợp eventual.
2. **Stale read chứng minh write bị mất.** Có thể do lag.
3. **Không thấy stale một lần chứng minh strong.** Không.
4. **Primary, replica và GSI luôn cùng consistency.** Không.
5. **Read concern majority tự là linearizable.** Không tự đồng nhất.
6. **GSI có strong read giống base table.** Không.
7. **Redis replica luôn mới nhất.** Không mặc định.
8. **R+W>N là universal linearizability guarantee.** Không.
9. **updatedAt thay được commit order.** Không.
10. **Version của hai keys khác nhau so trực tiếp được.** Không.
11. **Write timeout là rollback.** Có UNKNOWN.
12. **Search miss nên retry create.** Nguy cơ duplicate.
13. **Read overlap write mà thấy v1 luôn vi phạm linearizable.** Không.
14. **Monotonic reads và RYW là một.** Khác.
15. **Causal giống linearizable.** Không.
16. **Sequential buộc real-time cross-client.** Không.
17. **Snapshot cũ là dirty read.** Không.
18. **Eventual luôn converges trong 5 giây.** Không mặc định.
19. **Thread.sleep tạo deterministic replica lag.** Không.
20. **minVersion header tự làm API RYW.** Server phải enforce.
21. **Fallback source chứng minh projection đã converged.** Không.
22. **Event arrival order bằng commit order.** Không luôn.
23. **DELETE vật lý không cần tombstone.** Có resurrection risk.
24. **Một 200 nghĩa fresh/correct.** Không.
25. **Một timeout là stale read.** Không có returned value.
26. **Unit in-memory chứng minh native quorum.** Không.
27. **Một lần convergence chứng minh p99.** Không.
28. **Không cần read path trong incident report.** Không thể đối chiếu.
29. **Không cần tenant check khi fallback.** Security risk.
30. **Cursor tự bảo đảm snapshot.** Không.
31. **Read-your-writes thay conditional write.** Không.
32. **Monotonic nanoTime giữa máy có mốc chung.** Không.
33. **Một per-key version đủ cho mọi causal multi-key dependency.** Không.
34. **Có index refresh là mọi client thấy cùng trạng thái ngay.** Không.
35. **Test không exception là PASS.** Cần oracle.

## 31. Checklist hoàn thành

1. **Có source authority và read path rõ?**
2. **Key và tenant được chỉ định?**
3. **Có sourceVersion/commit token đáng tin?**
4. **Seed source=view=v1?**
5. **Có cách trì hoãn event quyết định?**
6. **Write v2 đã confirmed?**
7. **Nếu UNKNOWN đã reconcile?**
8. **Source read đã thấy v2?**
9. **View read vẫn v1 trước delivery?**
10. **Đã ghi đường đọc và consistency setting?**
11. **Eventual vs RYW được phân biệt?**
12. **Session minVersion được enforce?**
13. **Đã thử monotonic v2→v1?**
14. **Đã thử non-overlap real-time ordering?**
15. **Đã thử causal dependency nếu cần?**
16. **Bounded staleness có k/Δ rõ?**
17. **Có poll với deadline?**
18. **View hội tụ v2 sau event?**
19. **Old event không rollback version?**
20. **Tombstone ngăn resurrection?**
21. **Có thử cache stale fill?**
22. **Có cross-tenant assertions?**
23. **Có phân biệt application projection vs native replica?**
24. **Có engine/driver/topology versions?**
25. **Có freshness/CDC/index metrics?**
26. **Không suy stale từ timeout?**
27. **Có isolation/cleanup với synthetic data?**
28. **Có report PASS/FAIL/INCONCLUSIVE?**
29. **Có nêu giới hạn test chưa chứng minh?**
30. **Có kế hoạch mở rộng integration/fault test?**

**Kết luận:** Kịch bản đọc dữ liệu cũ đáng tin phải có **source v2 được xác nhận, read view v1 được tạo có kiểm soát, phiên/đường đọc được ghi rõ và oracle theo đúng bảo đảm nhất quán**. Eventual cho phép trễ trong quá trình hội tụ; RYW bảo vệ writes của session; monotonic ngăn đọc lùi; causal bảo vệ quan hệ nguyên nhân–kết quả; bounded staleness cần giới hạn đo được; linearizability đòi tôn trọng thứ tự real-time. Lab Java 21 kiểm chứng được logic stale→fallback→convergence và chống stale replay/tombstone, nhưng không thay thử nghiệm trên NoSQL cluster thật. Mọi kết luận cần ghi **mốc commit, sourceVersion, consistency configuration, read path, phiên, time-to-visibility và giới hạn bằng chứng** để phân biệt chính xác dữ liệu cũ được phép với lỗi nhất quán thực sự.
