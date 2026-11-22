# Correlation ID và theo dõi kết quả đến muộn

Trong hệ thống messaging, một yêu cầu có thể đi qua nhiều service, được chia thành nhiều nhánh, rồi nhận phản hồi theo thứ tự bất kỳ. Một phản hồi có thể đến sau timeout, sau khi nhóm đã được tổng hợp, hoặc sau khi ứng dụng đã gửi lại yêu cầu. Nếu chỉ dựa vào thứ tự nhận message hay ID tự sinh của từng message, ứng dụng rất dễ ghép nhầm kết quả, xử lý trùng hoặc mở lại một nhóm đã hoàn tất.

Correlation ID giải quyết bài toán xác định những message nào thuộc cùng một thao tác nghiệp vụ. Việc theo dõi kết quả đến muộn bổ sung trạng thái và chính sách vòng đời để ứng dụng biết phải làm gì khi phản hồi đến sau thời hạn chờ.

Bài học tập trung vào Spring Messaging và Spring Integration. Spring Messaging cung cấp abstraction Message và headers; Spring Integration bổ sung các header tương quan, splitter, aggregator, message store và chiến lược xử lý nhóm.

## 1. Phân biệt các loại ID

Không nên dùng một loại ID cho mọi mục đích. Các giá trị sau có vòng đời và ý nghĩa khác nhau:

| Giá trị | Ý nghĩa | Dùng khi nào |
|---|---|---|
| Message ID | Định danh một instance Message | Log, debug một message cụ thể |
| Correlation ID | Định danh một request hoặc một nhóm message có liên quan | Ghép request với reply, gom kết quả nhiều nhánh |
| Sequence number | Vị trí của message trong một nhóm | Sắp xếp hoặc xác định phần tử còn thiếu |
| Sequence size | Tổng số phần tử dự kiến trong nhóm | Xác định nhóm đã đủ để release |
| Operation ID | Định danh một thao tác nghiệp vụ xuyên suốt các lần retry | Idempotency, đối soát |
| Trace ID | Định danh một trace quan sát phân tán | Theo dõi các span qua service |

Trong Spring, MessageHeaders.ID là UUID do framework tạo cho từng Message. Khi message được tạo mới hoặc biến đổi thành instance khác, ID có thể thay đổi. Vì thế, không dùng MessageHeaders.ID làm khóa ghép request/reply xuyên suốt nhiều bước.

Spring Integration định nghĩa header CORRELATION_ID trong IntegrationMessageHeaderAccessor. Giá trị của header này là Object và được dùng để liên kết hai hoặc nhiều message. SEQUENCE_NUMBER và SEQUENCE_SIZE bổ sung vị trí và kích thước nhóm. SEQUENCE_DETAILS lưu ngăn xếp thông tin tương quan khi splitter/aggregator lồng nhau.

Ở ranh giới broker hoặc service, nên dùng một giá trị ổn định, dễ truyền và dễ quan sát, chẳng hạn UUID dạng String. Giá trị làm khóa phải có equals() và hashCode() ổn định; không dùng object mutable làm correlation key. Không đưa thông tin cá nhân hoặc bí mật vào ID.

## 2. Tạo và truyền Correlation ID

Tạo correlation ID khi bắt đầu một thao tác cần theo dõi. Đăng ký trạng thái chờ trước khi gửi request để tránh trường hợp reply rất nhanh đến trước khi ứng dụng tạo được bản ghi pending.

Ví dụ tạo Spring Message:

~~~java
import java.util.UUID;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

String correlationId = UUID.randomUUID().toString();

Message<String> request = MessageBuilder.withPayload("calculate-total")
        .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, correlationId)
        .build();
~~~

Khi tạo reply, giữ nguyên correlation ID của request:

~~~java
Message<String> reply = MessageBuilder.withPayload("125000")
        .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, correlationId)
        .build();
~~~

Nếu đang biến đổi một Message đã có, MessageBuilder.fromMessage(request) giúp giữ lại các header cần thiết:

~~~java
Message<String> reply = MessageBuilder.fromMessage(request)
        .setPayload("125000")
        .build();
~~~

MessageHeaders là cấu trúc chỉ đọc. Không sửa trực tiếp bằng put(), remove() hoặc clear(); hãy tạo Message mới qua MessageBuilder. Khi endpoint tạo output chỉ từ payload, Spring Integration thường truyền tiếp các header đầu vào. Nếu code transformer trả về một Message hoàn chỉnh, code đó chịu trách nhiệm cung cấp các header cần giữ. Các tùy chọn not-propagated-headers cũng có thể chủ động loại header khỏi đường đi.

Với message đi qua broker hoặc giao thức khác, kiểm tra adapter có ánh xạ correlation ID vào header/properties trên dây và trả lại nó ở reply hay không. Việc có header trong Message nội bộ không đảm bảo broker tự động truyền header đó xuyên suốt.

## 3. Hai kiểu tương quan thường gặp

### 3.1. Request/reply một-một

Mỗi request có một correlation ID riêng. Một bảng pending lưu ID, future/callback, thời hạn và trạng thái. Khi reply đến, consumer tra cứu đúng ID, hoàn tất future và xóa trạng thái chờ.

~~~text
Client                 Message flow                 Reply handler
  |                         |                            |
  |-- request, id=R17 ----->|--------------------------->|
  |                         |                            |
  |                         |<----- reply, id=R17 --------|
  |                         |                            |
  |<--------------- complete future for R17 ------------|
~~~

Nếu không tìm thấy ID trong pending registry, reply có thể là kết quả đến muộn, bản gửi lặp, hoặc message không thuộc request nào mà instance này quản lý. Không nên mặc định coi mọi trường hợp đều là lỗi giống nhau.

### 3.2. Fan-out/fan-in với Aggregator

Một request được tách thành nhiều message con. Các message con cùng mang correlation ID của nhóm; mỗi phần có sequence number riêng và thường có cùng sequence size. Aggregator lưu chúng vào MessageGroupStore rồi dùng ReleaseStrategy để quyết định lúc nào nhóm đủ điều kiện tổng hợp.

Spring Integration mặc định nhóm message theo IntegrationMessageHeaderAccessor.CORRELATION_ID. ReleaseStrategy mặc định dựa vào SEQUENCE_SIZE và sequence number. Splitter tự thêm các header sequence cần thiết. Nếu fan-out được tạo bằng publish-subscribe channel hoặc recipient list router, cần bật apply-sequence để thêm CORRELATION_ID, SEQUENCE_NUMBER và SEQUENCE_SIZE.

Nếu số nhánh thay đổi theo dữ liệu hoặc có nhánh bị filter loại bỏ, chiến lược đợi đủ SEQUENCE_SIZE có thể không bao giờ release. Khi đó cần custom ReleaseStrategy, hoặc phát message bù để báo rằng một nhánh đã được bỏ qua. Không nên chỉ tăng timeout để che giấu một nhóm không thể hoàn tất.

## 4. Retry: tách correlation ID khỏi operation ID

Một retry có thể tạo ra nhiều lần thực thi cho cùng một thao tác nghiệp vụ. Nếu tái sử dụng correlation ID của lần thử trước, reply đến muộn từ attempt cũ có thể bị ghép nhầm với attempt mới.

Nên tách hai khái niệm:

- Operation ID giữ nguyên qua các lần retry, giúp downstream nhận biết đây là cùng một thao tác nghiệp vụ và thực hiện idempotency.
- Correlation ID mới được tạo cho từng attempt, giúp reply được ghép đúng với lần gửi đã tạo ra nó.

Ví dụ:

| Lần gửi | Operation ID | Correlation ID | Kết quả |
|---|---|---|---|
| Attempt 1 | order-842 | req-a1 | Timeout |
| Attempt 2 | order-842 | req-a2 | Reply thành công |
| Reply muộn attempt 1 | order-842 | req-a1 | Ghi nhận late; không hoàn tất req-a2 |

Nếu hệ thống yêu cầu giữ cùng correlation ID qua retry, cần thêm attempt number và quy tắc chọn response thắng cuộc. Không để hai attempt cùng tranh quyền hoàn tất một future mà không có chính sách rõ ràng.

## 5. Mô hình trạng thái và xử lý reply đến muộn

Timeout của client chỉ có nghĩa là client đã ngừng chờ trong thời hạn đã định. Nó không chứng minh rằng service phía sau đã dừng xử lý. Reply vẫn có thể đến sau timeout do queue, retry, mạng chậm hoặc consumer bị nghẽn.

Một request registry có thể dùng các trạng thái sau:

- PENDING: đã đăng ký và đang chờ reply.
- COMPLETED: reply hợp lệ đã được nhận.
- TIMED_OUT: thời hạn chờ đã hết.
- CANCELLED: ứng dụng chủ động hủy thao tác.
- FAILED: thao tác kết thúc do lỗi không thể retry tại chỗ.

Chuyển trạng thái phải nguyên tử. Reply và timeout có thể chạy trên hai thread khác nhau; chỉ một bên được phép chuyển PENDING sang trạng thái kết thúc. Có thể dùng compareAndSet hoặc thao tác remove(key, expectedValue) để bảo đảm chỉ một bên thắng cuộc đua.

Khi reply đến sau timeout:

1. Tra correlation ID trong pending registry.
2. Nếu request vẫn PENDING, nhận reply, chuyển sang COMPLETED và hủy timeout task.
3. Nếu request đã TIMED_OUT, ghi nhận late reply và áp dụng chính sách đã chọn.
4. Nếu request đã COMPLETED, xem đây là duplicate reply.
5. Nếu không có pending hoặc terminal record, phân loại là unknown reply.

Chính sách cho late reply phụ thuộc nghiệp vụ: bỏ qua có log/metric, đưa vào kênh quarantine, lưu lại để đối soát, hoặc chạy một luồng reconciliation/compensation. Không tự động thực thi lại side effect chỉ vì reply đến muộn. Nếu kết quả có giá trị tài chính hoặc trạng thái nghiệp vụ, nên lưu lại để người hoặc quy trình đối soát quyết định.

Giữ một terminal record (tombstone) trong một khoảng thời gian sau khi request hoàn tất hoặc timeout. Record này cho phép phân biệt late reply với reply không rõ nguồn gốc và duplicate. TTL nên dài hơn thời gian trễ tối đa dự kiến cộng thêm cửa sổ retry/replay. Khi TTL kết thúc, một reply cực muộn sẽ được phân loại là unknown; cần metric để phát hiện tình trạng này.

Không tái sử dụng correlation ID trong thời gian terminal record còn hiệu lực. Nếu ID được tái sử dụng quá sớm, một reply cũ có thể khớp với request mới.

## 6. Theo dõi nhóm trong Spring Integration Aggregator

Aggregator có trạng thái và cần MessageGroupStore để giữ các message trong khi chờ nhóm hoàn tất. Có hai thời điểm kết thúc cần phân biệt:

- Hoàn tất bình thường: ReleaseStrategy quyết định nhóm đã đủ. Mặc định expire-groups-upon-completion là false; nhóm rỗng vẫn được giữ lại để nhận biết và discard message đến muộn có cùng correlation ID.
- Hết hạn do timeout: group-timeout hoặc MessageGroupStoreReaper buộc nhóm kết thúc. Mặc định expire-groups-upon-timeout là true; nhóm bị xóa hoàn toàn và message đến muộn có thể tạo một nhóm mới.

Để giữ metadata của nhóm đã timeout và discard reply đến muộn thay vì tạo một nhóm mới, có thể cấu hình expire-groups-upon-timeout="false". Ví dụ cấu hình XML dưới đây giả định đã khai báo các channel và namespace Spring Integration tương ứng:

~~~xml
<int:aggregator input-channel="results"
                output-channel="completed"
                discard-channel="late-or-discarded"
                group-timeout="30000"
                expire-groups-upon-completion="false"
                expire-groups-upon-timeout="false"
                send-partial-result-on-expiry="false"/>
~~~

Trong ví dụ, group-timeout là 30 giây tính từ lần message cuối cùng đến nhóm. Khi timeout, ReleaseStrategy được hỏi thêm một lần. Nếu vẫn chưa đủ điều kiện, nhóm hết hạn. Với send-partial-result-on-expiry="false", các message còn lại của nhóm hết hạn được đưa vào discard-channel thay vì phát kết quả tổng hợp một phần. Message đến sau khi nhóm đã hoàn tất mà metadata vẫn còn cũng có thể được đưa vào discard-channel.

Nếu muốn trả kết quả một phần khi timeout, đặt send-partial-result-on-expiry="true" và thiết kế consumer nhận biết rõ kết quả chưa đầy đủ. Không được diễn giải partial result thành kết quả hoàn tất. Với group-timeout-expression, có thể tính thời hạn dựa trên thời điểm tạo nhóm thay vì thời điểm message cuối cùng đến. group-timeout và group-timeout-expression là hai lựa chọn loại trừ nhau.

Giữ metadata vô thời hạn sẽ làm MessageGroupStore tăng kích thước. Cần cấu hình MessageGroupStoreReaper và empty-group-min-timeout phù hợp với cửa sổ tối đa mà reply muộn còn có thể đến. Chỉ xóa tombstone sau khi hệ thống đã chấp nhận rằng reply sau thời điểm đó không còn được ghép tự động.

Mặc định MessageGroupStore là store trong bộ nhớ, phù hợp với luồng đơn giản nhưng không giữ được trạng thái qua restart. Nếu cần khôi phục nhóm sau khi ứng dụng khởi động lại, dùng persistent store phù hợp, chẳng hạn JDBC MessageStore. Khi nhiều instance cùng cập nhật một store dùng chung, cần LockRegistry dùng chung để đồng bộ thao tác trên cùng correlation key. Mỗi aggregator nên có store/lock registry riêng theo cấu hình phù hợp; không chia sẻ một MessageGroupStore tùy tiện giữa các aggregator độc lập.

## 7. Ví dụ Java 17: registry xử lý reply, timeout và late reply

Ví dụ sau dùng JDK thuần để minh họa phần request/reply. Nó đăng ký request trước khi gửi, dùng ScheduledExecutorService để timeout, AtomicReference để phân định cuộc đua giữa reply và timeout, và terminal record có TTL để nhận biết reply đến muộn. Trong ứng dụng thực tế, receive() được gọi từ message listener sau khi đọc correlation ID từ header của reply.

Lưu thành CorrelationTrackerDemo.java:

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public final class CorrelationTrackerDemo {

    private enum Status { PENDING, COMPLETED, TIMED_OUT }

    private record Terminal(Status status, long expiresAtNanos) {}

    private static final class Pending {
        private final CompletableFuture<String> result = new CompletableFuture<>();
        private final AtomicReference<Status> status =
                new AtomicReference<>(Status.PENDING);
        private volatile ScheduledFuture<?> timeoutTask;

        private void cancelTimeout() {
            ScheduledFuture<?> task = timeoutTask;
            if (task != null) {
                task.cancel(false);
            }
        }
    }

    private static final class Tracker implements AutoCloseable {
        private final ConcurrentMap<String, Pending> pending =
                new ConcurrentHashMap<>();
        private final ConcurrentMap<String, Terminal> terminal =
                new ConcurrentHashMap<>();
        private final ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        private final long timeoutNanos;
        private final long tombstoneTtlNanos;

        private Tracker(Duration timeout, Duration tombstoneTtl) {
            if (timeout.isZero() || timeout.isNegative()
                    || tombstoneTtl.isZero() || tombstoneTtl.isNegative()) {
                throw new IllegalArgumentException("Durations must be positive");
            }
            this.timeoutNanos = timeout.toNanos();
            this.tombstoneTtlNanos = tombstoneTtl.toNanos();

            long cleanupPeriodMillis = Math.max(1, tombstoneTtl.toMillis() / 2);
            scheduler.scheduleAtFixedRate(
                    this::purgeExpiredTombstones,
                    cleanupPeriodMillis,
                    cleanupPeriodMillis,
                    TimeUnit.MILLISECONDS);
        }

        private synchronized CompletableFuture<String> register(String correlationId) {
            if (correlationId == null || correlationId.isBlank()) {
                throw new IllegalArgumentException("correlationId is required");
            }
            purgeExpiredTombstones();
            if (terminal.containsKey(correlationId)) {
                throw new IllegalArgumentException(
                        "correlationId is still in the retention window");
            }

            Pending request = new Pending();
            if (pending.putIfAbsent(correlationId, request) != null) {
                throw new IllegalArgumentException("correlationId is already pending");
            }

            try {
                request.timeoutTask = scheduler.schedule(
                        () -> timeout(correlationId, request),
                        timeoutNanos,
                        TimeUnit.NANOSECONDS);
            }
            catch (RuntimeException ex) {
                pending.remove(correlationId, request);
                throw ex;
            }
            return request.result;
        }

        private void timeout(String correlationId, Pending request) {
            if (request.status.compareAndSet(Status.PENDING, Status.TIMED_OUT)) {
                remember(correlationId, Status.TIMED_OUT);
                pending.remove(correlationId, request);
                request.result.completeExceptionally(
                        new TimeoutException("Timed out: " + correlationId));
            }
        }

        private void receive(String correlationId, String payload) {
            if (correlationId == null || correlationId.isBlank()) {
                System.out.println("reply without correlation ID ignored");
                return;
            }

            Pending request = pending.get(correlationId);
            if (request != null) {
                if (request.status.compareAndSet(Status.PENDING, Status.COMPLETED)) {
                    remember(correlationId, Status.COMPLETED);
                    pending.remove(correlationId, request);
                    request.cancelTimeout();
                    request.result.complete(payload);
                    return;
                }
                Status current = request.status.get();
                if (current == Status.TIMED_OUT) {
                    System.out.println("late reply ignored: " + correlationId);
                    return;
                }
                if (current == Status.COMPLETED) {
                    System.out.println("duplicate reply ignored: " + correlationId);
                    return;
                }
            }

            Terminal marker = terminal.get(correlationId);
            if (marker != null
                    && System.nanoTime() - marker.expiresAtNanos() < 0) {
                if (marker.status() == Status.TIMED_OUT) {
                    System.out.println("late reply ignored: " + correlationId);
                }
                else {
                    System.out.println("duplicate reply ignored: " + correlationId);
                }
            }
            else {
                if (marker != null) {
                    terminal.remove(correlationId, marker);
                }
                System.out.println("unknown reply ignored: " + correlationId);
            }
        }

        private synchronized void remember(String correlationId, Status status) {
            terminal.put(correlationId,
                    new Terminal(status, System.nanoTime() + tombstoneTtlNanos));
        }

        private void purgeExpiredTombstones() {
            long now = System.nanoTime();
            terminal.entrySet().removeIf(
                    entry -> now - entry.getValue().expiresAtNanos() >= 0);
        }

        @Override
        public void close() {
            scheduler.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        try (Tracker tracker = new Tracker(
                Duration.ofMillis(100), Duration.ofSeconds(5))) {

            CompletableFuture<String> fast = tracker.register("req-1");
            tracker.receive("req-1", "OK");
            System.out.println("reply req-1: " + fast.get(1, TimeUnit.SECONDS));

            CompletableFuture<String> slow = tracker.register("req-2");
            try {
                slow.get(1, TimeUnit.SECONDS);
            }
            catch (ExecutionException ex) {
                if (ex.getCause() instanceof TimeoutException) {
                    System.out.println("request req-2 timed out");
                }
                else {
                    throw ex;
                }
            }

            tracker.receive("req-2", "too late");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac --release 17 CorrelationTrackerDemo.java
java CorrelationTrackerDemo
~~~

Stdout chính xác:

~~~text
reply req-1: OK
request req-2 timed out
late reply ignored: req-2
~~~

Ví dụ này minh họa chính sách bỏ qua reply muộn. Trong production, thay System.out bằng logger và metric; đưa late reply có giá trị nghiệp vụ vào nơi lưu trữ/reconciliation nếu cần. Terminal map trong demo có TTL 5 giây để minh họa việc giới hạn bộ nhớ. Trong demo, `register()` và `remember()` được đồng bộ trên cùng Tracker để việc kiểm tra tombstone và thêm pending entry không bị race với việc ghi trạng thái terminal. TTL thực tế phải được chọn từ độ trễ tối đa, retry policy và retention của broker. Registry trong bộ nhớ chỉ hoạt động trong một JVM; nếu request có thể được gửi ở instance A nhưng reply được nhận ở instance B, cần một pending store/response router dùng chung hoặc định tuyến reply về đúng instance.

## 8. Quan sát và vận hành

Mỗi log của request/reply nên có correlation ID, operation ID, attempt, message ID, sequence number nếu có, trạng thái và thời gian chờ. Dùng cùng correlation ID trong log của các service để tìm toàn bộ hành trình của một thao tác. Trace ID phục vụ distributed tracing; correlation ID phục vụ liên kết nghiệp vụ và message. Hai giá trị có thể được liên kết trong log nhưng không nên mặc định thay thế nhau.

Các metric hữu ích:

- Số request đang PENDING và tuổi của request cũ nhất.
- Tỷ lệ timeout theo destination/operation.
- Số late reply, duplicate reply và unknown reply.
- Độ trễ từ lúc gửi đến lúc nhận reply, gồm percentile p50/p95/p99.
- Số message group đang chờ, số group hết hạn và kích thước MessageGroupStore.
- Số kết quả partial, discard và reconciliation thành công/thất bại.

Nếu late reply tăng, kiểm tra queue depth, consumer lag, retry, thời gian xử lý downstream, timeout cấu hình và thời gian truyền mạng. Không chỉ tăng timeout mà không xác định nguyên nhân; timeout quá dài có thể giữ nhiều pending request và message group trong bộ nhớ.

## 9. Lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng MessageHeaders.ID làm correlation key | ID đổi khi tạo Message mới; reply không khớp request ban đầu | Tạo correlation ID riêng và truyền qua mọi hop |
| Dùng chung một correlation ID cho nhiều request độc lập | Reply của request này bị ghép vào request khác | Tạo ID riêng cho từng request/attempt |
| Retry nhưng tái sử dụng ID mà không có attempt policy | Reply muộn của lần cũ có thể hoàn tất lần mới | ID mới cho mỗi attempt; operation ID ổn định để idempotency |
| Xóa pending ngay khi timeout mà không giữ terminal record | Không phân biệt late reply với unknown reply | Giữ tombstone trong cửa sổ trễ hợp lý |
| Cho phép nhóm timeout bị xóa hoàn toàn | Reply muộn có thể tạo một nhóm mới không bao giờ đủ | Cân nhắc expire-groups-upon-timeout=false |
| Giữ metadata aggregator mãi mãi | MessageGroupStore tăng không giới hạn | Dùng reaper và empty-group-min-timeout |
| Đợi đủ sequence size dù một nhánh đã bị filter | Aggregator không bao giờ release bình thường | Custom ReleaseStrategy hoặc compensation message |
| Chỉ log payload mà thiếu correlation ID | Khó truy vết khi message đến sai thứ tự | Log correlation ID, attempt, trạng thái và thời gian |
| Coi timeout là downstream đã hủy | Side effect vẫn có thể xảy ra sau timeout | Thiết kế cancel protocol hoặc reconciliation riêng |

## 10. Checklist thiết kế

- Sinh correlation ID duy nhất trước khi gửi request và đăng ký pending trước thao tác send.
- Dùng một correlation ID cho đúng một request hoặc một nhóm fan-in; không dùng lại giữa các thao tác độc lập.
- Giữ operation ID ổn định qua retry để hỗ trợ idempotency; dùng attempt ID/correlation ID riêng nếu cần phân biệt từng lần thử.
- Đảm bảo mọi response, error reply và message con mang đúng correlation ID.
- Nếu dùng splitter/aggregator, kiểm tra sequence number, sequence size, apply-sequence và release strategy.
- Quy định rõ kết quả sau timeout: discard, quarantine, lưu để đối soát hay compensation.
- Bảo đảm chỉ một thread thắng cuộc đua giữa reply và timeout.
- Giữ terminal record đủ lâu để nhận diện late/duplicate reply, sau đó dọn dẹp có giới hạn.
- Dùng persistent/shared state khi request và reply có thể đi qua nhiều instance hoặc cần phục hồi sau restart.
- Theo dõi timeout, late, duplicate, unknown và số group đang chờ bằng metric.
- Kiểm tra header propagation và ánh xạ header của broker/transport trên đường đi thực tế.

## Tài liệu tham khảo

- [Spring Integration — Message và Message Headers](https://docs.spring.io/spring-integration/reference/message.html)
- [Spring Integration — Aggregator, CorrelationStrategy và ReleaseStrategy](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration API — IntegrationMessageHeaderAccessor](https://docs.spring.io/spring-integration/api/org/springframework/integration/IntegrationMessageHeaderAccessor.html)
- [Spring Framework API — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
