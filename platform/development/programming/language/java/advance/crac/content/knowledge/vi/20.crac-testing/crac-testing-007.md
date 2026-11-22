# Kiểm thử restore sau khi token, TTL và kết nối đã hết hạn

Checkpoint CRaC lưu trạng thái của một tiến trình Java tại một thời điểm, nhưng các hệ thống bên ngoài vẫn tiếp tục hoạt động trong lúc tiến trình tạm dừng. Khi restore, một access token có thể đã hết hạn, refresh token có thể bị thu hồi, cache có thể vượt TTL, database có thể đã đóng connection idle và broker có thể đã thay đổi session. Những object Java tương ứng vẫn có thể tồn tại trong heap được khôi phục, nhưng trạng thái bên ngoài mà chúng đại diện không còn hợp lệ.

Vì vậy, kiểm thử restore cần tạo ra khoảng thời gian thực sự giữa checkpoint và restore, đồng thời chủ động thay đổi trạng thái của dependency trong khoảng đó. Chỉ kiểm tra restore ngay sau checkpoint không đủ để phát hiện lỗi hết hạn. Cũng không nên chỉ kiểm tra field Java còn khác `null`; cần chứng minh ứng dụng đã xác thực lại, làm mới cache, tạo kết nối mới và chỉ bật readiness khi các dependency bắt buộc hoạt động.

Bài kiểm thử nên kết hợp hai lớp. Unit test dùng `Clock` có thể điều khiển để kiểm tra chính xác logic deadline và TTL. Integration test chạy với JDK CRaC và môi trường tương thích để xác minh callback, thời gian tạm dừng, token server, cache, database và kết nối mạng thực sự hoạt động đúng sau restore.

## 1. Những trạng thái có thể hết hạn khi tiến trình tạm dừng

Trước khi viết test, hãy liệt kê trạng thái nào được quản lý bởi tiến trình và trạng thái nào được quản lý bởi hệ thống bên ngoài.

| Trạng thái | Điều có thể xảy ra trong lúc checkpoint | Hành vi cần kiểm tra sau restore |
|---|---|---|
| Access token | Hết hạn, bị thu hồi hoặc không còn đúng audience/scope | Refresh hoặc xác thực lại trước khi gọi API |
| Refresh token | Hết hạn, bị rotation hoặc bị thu hồi | Lấy credential mới theo flow được cấp; nếu không thể thì readiness/operation phải thất bại rõ ràng |
| Signing key/JWKS | Key cũ bị rotate hoặc bị loại khỏi tập key tin cậy | Tải metadata/key hiện hành và xác minh token theo chính sách |
| Cache có TTL | TTL trôi qua; nguồn dữ liệu thay đổi | Không trả dữ liệu hết hạn; reload hoặc invalidate |
| Negative cache | Một lỗi tạm thời được cache quá lâu hoặc trạng thái lỗi đã thay đổi | Hết TTL phải thử lại theo chính sách |
| JDBC connection | Database, proxy hoặc firewall đóng connection idle | Tạo pool/connection mới và kiểm tra truy vấn |
| HTTP keep-alive | Server hoặc load balancer đóng socket | Client tạo kết nối mới, xử lý retry an toàn |
| WebSocket/gRPC stream | Peer timeout hoặc kết thúc session | Reconnect và resume theo giao thức ứng dụng |
| Kafka/RabbitMQ client | Heartbeat timeout, rebalance, channel bị đóng | Tạo client/session mới, tham gia group hoặc đăng ký consumer lại |
| Lease/distributed lock | Lease hết hạn và instance khác lấy quyền sở hữu | Acquire/renew lại; không tiếp tục thao tác độc quyền bằng trạng thái cũ |
| DNS/service discovery | Địa chỉ backend thay đổi | Resolve endpoint hiện hành và tạo client mới nếu cần |

Một test tốt phải xác minh cả hai chiều: ứng dụng phục hồi thành công khi có thể refresh/reconnect, và ứng dụng từ chối phục vụ khi credential hoặc dependency không thể phục hồi.

## 2. Xây dựng chiến lược kiểm thử theo nhiều lớp

Không phải mọi trường hợp đều cần khởi chạy CRaC thật. Hãy tách logic có thể kiểm thử nhanh khỏi các hành vi chỉ có thể xác minh trong môi trường checkpoint/restore.

| Lớp test | Mục tiêu | Công cụ/cách thực hiện |
|---|---|---|
| Unit test | Kiểm tra so sánh expiration, TTL, refresh window và retry policy | `Clock` giả lập, fake token provider, cache in-memory |
| Component test | Kiểm tra phối hợp giữa token manager, cache và connection manager | Mock HTTP server, database test instance, fake secret provider |
| Integration test | Kiểm tra callback `beforeCheckpoint`/`afterRestore` và client lifecycle | JDK CRaC tương thích, database/broker/container test |
| End-to-end restore test | Kiểm tra toàn bộ ứng dụng sau một khoảng dừng và thay đổi dependency | Checkpoint thật, chờ bên ngoài tiến trình, thay đổi trạng thái dependency, restore |
| Multi-replica test | Phát hiện refresh stampede, connection storm và tranh chấp lease | Restore nhiều replica từ cùng image, quan sát issuer/database/broker |

Unit test xác nhận logic ứng dụng nhưng không chứng minh socket hoặc runtime được phục hồi đúng. Ngược lại, một integration test thành công trên một máy không thay thế unit test cho các ranh giới thời gian. Kết hợp hai loại giúp test nhanh, ổn định và vẫn có bằng chứng về hành vi CRaC thật.

## 3. Dùng `Clock` để kiểm thử token và TTL một cách xác định

Không nên dùng `Thread.sleep()` trong unit test để chờ token hết hạn hoặc cache vượt TTL. Cách đó làm test chậm và dễ flaky do lịch chạy thread, tải máy hoặc độ chính xác của timer.

Hãy inject `java.time.Clock` vào thành phần cần đọc thời gian. Trong production dùng `Clock.systemUTC()`. Trong test dùng `Clock.fixed()` hoặc một clock có thể dịch chuyển.

Ví dụ một token provider kiểm tra thời điểm hết hạn:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

record AccessToken(String value, Instant expiresAt) { }

interface TokenClient {
    AccessToken refresh() throws Exception;
}

public final class AccessTokenProvider {

    private final Clock clock;
    private final Duration refreshSkew;
    private final TokenClient tokenClient;
    private final AtomicReference<AccessToken> current =
            new AtomicReference<>();

    public AccessTokenProvider(Clock clock,
                               Duration refreshSkew,
                               TokenClient tokenClient) {
        this.clock = clock;
        this.refreshSkew = refreshSkew;
        this.tokenClient = tokenClient;
    }

    public synchronized AccessToken current() throws Exception {
        AccessToken token = current.get();
        Instant refreshAt = token == null
                ? Instant.MIN
                : token.expiresAt().minus(refreshSkew);

        if (token == null || !clock.instant().isBefore(refreshAt)) {
            token = tokenClient.refresh();
            current.set(token);
        }
        return token;
    }

    public synchronized void refreshAfterRestore() throws Exception {
        current.set(tokenClient.refresh());
    }
}
```

Đây là ví dụ đơn giản về refresh trước thời điểm hết hạn một khoảng `refreshSkew`. Trong ứng dụng thực tế, cần xử lý giới hạn đồng bộ khi nhiều thread cùng cần token, lỗi refresh, timeout, retry có backoff và rotation của refresh token. Không log `token.value()`; chỉ ghi metadata an toàn như issuer, expiry và kết quả refresh.

Test có thể dùng `Clock.fixed()` để xác minh token còn hạn, nằm trong refresh window hoặc đã hết hạn mà không phải chờ:

```java
Instant issuedAt = Instant.parse("2026-11-13T08:00:00Z");
Clock beforeExpiry = Clock.fixed(issuedAt, ZoneOffset.UTC);

AccessToken token = new AccessToken(
        "test-token",
        issuedAt.plus(Duration.ofMinutes(10)));

assertTrue(beforeExpiry.instant().isBefore(token.expiresAt()));
```

Đoạn test này chỉ minh họa cách cố định thời gian. Nên kiểm tra hành vi của `AccessTokenProvider` bằng fake `TokenClient` đếm số lần refresh và trả về token có expiry được kiểm soát.

### Khi cần dịch chuyển đồng hồ trong cùng test

Có thể dùng một `MutableClock` nhỏ để tiến thời gian mà không chờ thật:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;

    public MutableClock(Instant initial) {
        this.current = new AtomicReference<>(initial);
    }

    public void advance(Duration duration) {
        current.updateAndGet(value -> value.plus(duration));
    }

    @Override
    public ZoneId getZone() {
        return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        throw new UnsupportedOperationException("UTC test clock only");
    }

    @Override
    public Instant instant() {
        return current.get();
    }
}
```

Test có thể tạo token hết hạn sau 5 phút, gọi `clock.advance(Duration.ofMinutes(6))`, rồi xác minh provider refresh trước khi trả token. Vì clock chỉ điều khiển logic trong tiến trình test, nó không làm token ở một identity provider hoặc database thật tự hết hạn. Muốn kiểm tra hệ thống bên ngoài, phải điều khiển clock/test fixture ở chính hệ thống đó hoặc dùng token TTL ngắn và chờ theo thời gian thực trong integration test.

## 4. Kiểm thử access token và refresh token

Token có thể hết hạn theo `exp`, bị thu hồi, bị rotate hoặc không còn hợp lệ do thay đổi issuer, audience, scope hay signing key. Kiểm thử chỉ tạo một JWT với `exp` trong quá khứ sẽ không bao phủ các trường hợp này.

### Ma trận test cho token

| Kịch bản | Chuẩn bị trước checkpoint | Thay đổi trong lúc tạm dừng | Kết quả mong đợi sau restore |
|---|---|---|---|
| Access token còn hạn | Token còn thời gian sống đủ dài | Restore trước `exp` | Có thể dùng token nếu policy cho phép; không refresh không cần thiết |
| Access token hết hạn | Token có expiry gần | Chờ đến sau `exp` | Provider refresh trước API call hoặc trước readiness theo thiết kế |
| Refresh token còn hạn | Có access token và refresh token hợp lệ | Access token hết hạn | Refresh thành công, client dùng token mới |
| Refresh token hết hạn | Refresh token TTL ngắn | Chờ vượt cả hai expiry | Re-authenticate hoặc báo lỗi; không dùng token cũ |
| Refresh token bị thu hồi | Token ban đầu hợp lệ | Thu hồi trên issuer trước restore | Refresh thất bại rõ ràng; readiness/operation theo policy |
| Secret rotation | Credential cũ đang được dùng | Rotate secret hoặc certificate | Lấy giá trị mới và tạo lại client phụ thuộc |
| Signing key rotation | Token ký bằng key cũ | Cập nhật JWKS/key set | Xác minh theo key hiện hành và chính sách overlap |
| Issuer/audience thay đổi | Client dùng cấu hình cũ | Thay policy ở identity provider | Client nạp config mới hoặc thất bại an toàn |
| Nhiều replica cùng restore | Cùng checkpoint chứa trạng thái token cũ | Cùng lúc cần refresh | Refresh được giới hạn/coalesce; không tạo stampede hoặc reuse sai session |

### Test token hết hạn trong khoảng pause

Một integration test nên thực hiện theo trình tự:

1. Khởi chạy ứng dụng với token test có TTL ngắn, ví dụ 30–60 giây.
2. Gọi một API được bảo vệ để xác nhận token còn hiệu lực trước checkpoint.
3. Ghi nhận expiry và trạng thái token mà không ghi giá trị token vào log.
4. Yêu cầu checkpoint.
5. Từ test controller hoặc test harness bên ngoài JVM, chờ vượt expiry.
6. Restore tiến trình.
7. Gọi API yêu cầu xác thực hoặc kiểm tra readiness tùy kiến trúc.
8. Xác nhận client lấy token mới, API call thành công và token cũ không được gửi lại.

Điểm quan trọng là thời gian chờ phải diễn ra bên ngoài tiến trình đã checkpoint. Nếu test gọi `Thread.sleep()` trong ứng dụng trước khi checkpoint, nó chỉ kiểm tra một khoảng chờ khi JVM đang chạy, không kiểm tra thời gian tạm dừng của CRaC.

### Kiểm tra refresh thất bại

Không chỉ kiểm tra đường thành công. Hãy thu hồi refresh token hoặc làm cho token endpoint trả `invalid_grant`, `401`, `429` hoặc `5xx` tùy trường hợp. Xác minh:

- Ứng dụng không gửi lại access token đã hết hạn như thể còn hợp lệ.
- Lỗi xác thực vĩnh viễn không bị retry vô hạn.
- Lỗi tạm thời được retry theo backoff có giới hạn.
- Secret/token không xuất hiện trong log hoặc exception message.
- Readiness vẫn false nếu token là dependency bắt buộc.
- Nếu ứng dụng hỗ trợ degraded mode, chỉ các capability không cần token mới được mở.

### Đồng bộ refresh khi nhiều replica restore

Nếu 20 replica cùng restore từ checkpoint chứa một access token gần hết hạn, tất cả có thể cùng gọi token endpoint. Kiểm thử cần quan sát số lần refresh, thời điểm gọi và cách ứng dụng xử lý rotation. Có thể cần single-flight refresh trong mỗi process, jitter giữa các replica hoặc token cache tập trung nếu issuer và mô hình bảo mật cho phép. Không chia sẻ refresh token có tính chất rotation/one-time giữa nhiều replica nếu issuer không hỗ trợ mô hình đó.

## 5. Kiểm thử TTL của cache và dữ liệu đã hết hạn

TTL là thời lượng một giá trị được xem là còn mới. Nếu cache chỉ lưu `remainingSeconds` tại thời điểm checkpoint, giá trị đó có thể bị đóng băng trong heap trong lúc tiến trình tạm dừng. Sau restore, ứng dụng có nguy cơ dùng dữ liệu đã hết hạn như thể TTL chưa trôi qua.

Ưu tiên lưu thời điểm hết hạn tuyệt đối hoặc metadata đủ để xác định độ mới:

```java
record CacheEntry<T>(T value, Instant expiresAt, String version) { }

public final class TtlCache<T> {

    private final Clock clock;
    private final Map<String, CacheEntry<T>> entries = new ConcurrentHashMap<>();

    public TtlCache(Clock clock) {
        this.clock = clock;
    }

    public Optional<T> get(String key) {
        CacheEntry<T> entry = entries.get(key);
        if (entry == null) {
            return Optional.empty();
        }

        if (!clock.instant().isBefore(entry.expiresAt())) {
            entries.remove(key, entry);
            return Optional.empty();
        }
        return Optional.of(entry.value());
    }
}
```

Đoạn code minh họa expiration theo `Instant`. Cache thực tế cần xử lý tải lại khi miss, concurrency, invalidation và nguồn dữ liệu. Nếu giá trị nhạy cảm hoặc ảnh hưởng quyền truy cập, nên fail closed khi không xác minh được độ mới.

### Ma trận test TTL

| Kịch bản | Thời gian restore | Kết quả mong đợi |
|---|---|---|
| Cache còn TTL | Trước `expiresAt` | Có thể trả cache nếu version/source vẫn hợp lệ |
| Cache vừa hết hạn | Sau `expiresAt` một khoảng nhỏ | Cache miss và reload; không trả entry cũ |
| Cache hết hạn lâu | Sau TTL nhiều lần | Invalidate; không chạy nhiều reload đồng thời không giới hạn |
| Cache bị invalidation bên ngoài | Nguồn phát event invalidation khi app tạm dừng | Sau restore phát hiện version mismatch hoặc reload |
| Negative cache hết hạn | Trước đó cache kết quả “not found” | Sau TTL thử lại nguồn dữ liệu |
| Cache chứa quyền/role | Role bị thu hồi khi checkpoint | Không tiếp tục cho phép dựa vào entry cũ |
| Nhiều replica cùng miss | Tất cả restore sau TTL | Có giới hạn tải, single-flight hoặc jitter phù hợp |

Test phải kiểm tra giá trị trả về, số lần gọi source loader, số lần invalidate và latency. Chỉ kiểm tra rằng field `expiresAt` vẫn tồn tại không chứng minh cache hoạt động đúng.

### Phân biệt cache trong heap và cache bên ngoài

Cache trong heap có thể được lưu cùng checkpoint nhưng cần đánh giá TTL và độ mới. Redis, distributed cache, database buffer cache hoặc CDN cache nằm ngoài tiến trình; chúng có vòng đời riêng. Một request warm-up trước checkpoint không chứng minh cache ngoài vẫn còn sau restore. Test cần kiểm tra từng lớp cache và xác định nguồn sự thật cuối cùng.

## 6. Kiểm thử database connection và connection pool đã hết hạn

Database, proxy, firewall hoặc pooler có thể đóng connection idle trong lúc ứng dụng tạm dừng. Sau restore, field Java có thể vẫn giữ `DataSource` hoặc connection wrapper, nhưng socket bên dưới đã bị peer đóng.

Không nên dùng riêng `Connection.isClosed()` để chứng minh connection còn dùng được. Một số driver không biết peer đã đóng socket cho đến khi thực hiện I/O. Hãy kiểm tra bằng validation query hoặc API validation của pool, đồng thời thiết kế để connection lỗi được loại khỏi pool và tạo lại.

### Kịch bản integration test database

1. Khởi chạy database test có timeout idle hoặc proxy có khả năng đóng connection.
2. Tạo pool và mượn connection để xác nhận truy vấn thành công.
3. Đưa ứng dụng về trạng thái không còn transaction hoặc query đang chạy.
4. Tạo checkpoint theo CRaC integration của pool/driver hoặc đóng pool trước checkpoint nếu ứng dụng tự quản lý.
5. Trong lúc tiến trình tạm dừng, chờ vượt idle timeout hoặc chủ động restart database/proxy.
6. Restore ứng dụng.
7. Xác nhận pool tạo connection mới và validation query thành công.
8. Gửi một request nghiệp vụ đọc/ghi an toàn để chứng minh đường đi thực tế hoạt động.
9. Kiểm tra connection cũ không được tái sử dụng và số connection mới nằm trong giới hạn.

Nếu môi trường test không hỗ trợ ép timeout database, có thể đóng connection từ phía database/proxy hoặc restart container dependency trong khoảng pause. Cần ghi nhận chính xác hành động để phân biệt lỗi do CRaC với lỗi do dependency chưa sẵn sàng.

### Test pool được tạo lại sau restore

Nếu pool cần đóng trước checkpoint, hãy xác minh sau restore ứng dụng không giữ reference tới pool đã đóng. Một facade có thể trỏ đến pool hiện hành:

```java
public final class SwappableDataSource {

    private final AtomicReference<DataSource> current = new AtomicReference<>();

    public void replace(DataSource replacement) {
        current.set(Objects.requireNonNull(replacement));
    }

    public Connection getConnection() throws SQLException {
        DataSource dataSource = current.get();
        if (dataSource == null) {
            throw new SQLException("DataSource is not ready");
        }
        return dataSource.getConnection();
    }
}
```

Đây là cấu trúc minh họa. Khi thay pool, cần ngừng request mới, drain connection đang mượn, tạo pool mới, chạy validation, atomically chuyển reference và đóng pool cũ. Trong `afterRestore()`, không bật readiness trước khi pool mới hợp lệ.

### Trường hợp database chưa sẵn sàng sau restore

Cho database test trì hoãn accept connection hoặc trả lỗi tạm thời trong vài lần đầu. Xác nhận ứng dụng:

- Retry có backoff và jitter.
- Không tạo hàng trăm connection đồng thời.
- Không giữ request vô hạn trong queue.
- Readiness false trong lúc chưa kết nối được.
- Chuyển readiness true sau khi validation thành công.
- Không cần restart toàn bộ process cho lỗi dependency tạm thời nếu thiết kế hỗ trợ reconnect.

## 7. Kiểm thử HTTP, TLS, WebSocket và gRPC connection

HTTP keep-alive socket có thể bị server hoặc load balancer đóng trong thời gian pause. TLS certificate hoặc client credential có thể hết hạn. WebSocket/gRPC stream có thể bị peer timeout hoặc kết thúc. Test cần xác minh client có thể tạo kết nối mới và phục hồi trạng thái ứng dụng.

Các kịch bản nên bao gồm:

- Server đóng keep-alive connection khi tiến trình tạm dừng.
- DNS trả địa chỉ backend mới sau restore.
- TLS certificate được rotate hoặc hết hạn.
- Token dùng cho HTTP client hết hạn.
- WebSocket server đóng session và yêu cầu subscribe lại.
- gRPC server kết thúc stream; client phải mở RPC mới và resume từ cursor.
- Request đầu tiên sau restore nhận lỗi mạng tạm thời rồi retry thành công.

Không nên kiểm tra chỉ bằng cách gọi `connect()` hoặc xem client object khác `null`. Hãy gọi endpoint test thực sự, xác minh peer mới, TLS hostname, authentication và response. Với stream, kiểm tra sequence/cursor để chứng minh không bỏ sót hoặc xử lý trùng ngoài chính sách.

## 8. Kiểm thử Kafka và RabbitMQ sau khi connection/lease hết hạn

Với Kafka, tiến trình có thể bị loại khỏi consumer group trong thời gian pause. Sau restore, consumer phải tạo kết nối, tham gia group và nhận partition assignment mới. Test cần xác minh record chưa commit có thể được giao lại và handler idempotent.

Với RabbitMQ, broker có thể đóng connection/channel khi heartbeat timeout. Delivery chưa ack có thể được requeue và giao lại. Test cần xác minh consumer tạo channel mới, đăng ký lại queue và xử lý message trùng an toàn.

| Broker | Thao tác trong lúc tiến trình tạm dừng | Assertion sau restore |
|---|---|---|
| Kafka | Chờ session timeout hoặc thay đổi group membership | Consumer mới tham gia group, nhận assignment và tiếp tục từ offset hợp lệ |
| Kafka | Gửi record nhưng chưa có kết quả commit/confirm rõ ràng | Outbox/retry xử lý theo semantics, không mất record đã xác nhận |
| RabbitMQ | Chờ heartbeat timeout hoặc restart broker | Connection/channel mới được tạo và consumer đăng ký lại |
| RabbitMQ | Giữ message unacked rồi đóng channel | Message được giao lại và consumer không tạo side effect trùng |
| Cả hai | Restore nhiều replica đồng thời | Không tạo connection/consumer vượt giới hạn; identity và membership đúng |

Đừng giả định một callback reconnect đã khôi phục toàn bộ semantics của broker. Kiểm tra offset, acknowledgement, publisher confirm, transaction và assignment bằng API/metrics của broker.

## 9. Tích hợp kiểm thử với CRaC Resource callbacks

Một Resource có thể phối hợp refresh token và reconnect dependency sau restore. Nên tách các bước theo trách nhiệm để test có thể thay fake provider hoặc fake connection factory.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExternalStateResource implements Resource {

    private final TokenProvider tokenProvider;
    private final ConnectionManager connectionManager;
    private final ReadinessGate readiness;

    public ExternalStateResource(TokenProvider tokenProvider,
                                 ConnectionManager connectionManager,
                                 ReadinessGate readiness) {
        this.tokenProvider = tokenProvider;
        this.connectionManager = connectionManager;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.markNotReady();
        connectionManager.stopNewWorkAndDrain();
        connectionManager.closeForCheckpoint();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        readiness.markNotReady();
        tokenProvider.refreshAfterRestore();
        connectionManager.reconnectWithCurrentCredentials();
        connectionManager.verifyConnections();
        readiness.markReady();
    }
}
```

`TokenProvider`, `ConnectionManager` và `ReadinessGate` là abstraction minh họa. Nếu một thư viện đã có CRaC integration, không đăng ký callback thứ hai để đóng/mở cùng resource. Nếu nhiều resource phụ thuộc lẫn nhau, hãy xác định thứ tự callback hoặc gom chúng vào một lifecycle coordinator để token được refresh trước khi client tạo kết nối.

Trong code thực tế, readiness chỉ được bật sau khi mọi dependency bắt buộc đã xác minh. Nếu refresh token thất bại, không tiếp tục tạo client bằng credential cũ. Nếu database reconnect thất bại, giữ readiness false và để cơ chế retry có giới hạn hoạt động theo policy.

### Unit test callback không cần restore process thật

Có thể kiểm tra logic của coordinator bằng cách gọi các phương thức lifecycle trong test với fake dependency, hoặc dùng abstraction riêng tách khỏi interface `Resource`. Tuy nhiên, gọi `afterRestore()` thủ công không tương đương với restore thật; nó không kiểm tra runtime, thread, socket, file descriptor hoặc thứ tự callback do CRaC thực hiện.

## 10. Kịch bản end-to-end: checkpoint, làm hết hạn dependency, restore

Một bài test tích hợp có giá trị nên có một harness điều khiển tiến trình từ bên ngoài. Harness khởi chạy ứng dụng, chờ trạng thái sẵn sàng, yêu cầu checkpoint, thay đổi dependency trong thời gian process dừng, rồi khởi động restore.

```text
Test harness
   |
   +--> Start application with CRaC JDK
   |
   +--> Wait for pre-checkpoint readiness
   |
   +--> Create token/cache/DB fixtures with short TTLs
   |
   +--> Verify one successful request
   |
   +--> Request checkpoint
   |
   +--> Wait until checkpoint process has completed
   |
   +--> Outside the stopped process:
   |      - wait beyond token expiry
   |      - expire cache TTL
   |      - close DB/proxy connections
   |      - optionally rotate credentials or DNS
   |
   +--> Restore from the checkpoint
   |
   +--> Wait for afterRestore lifecycle and readiness
   |
   +--> Assert fresh token, fresh connection, cache reload
   |
   +--> Send representative business request
   |
   +--> Assert no stale credential or connection was reused
```

Các lệnh checkpoint/restore cụ thể phụ thuộc JDK CRaC và môi trường container/VM. Harness nên dùng công cụ đã được xác nhận trong dự án và kiểm tra exit code/log để biết checkpoint hoàn tất trước khi thay đổi dependency. Không giả định chỉ gửi tín hiệu hoặc nhận được một log bất kỳ là checkpoint đã ghi xong.

### Giữ test có thể lặp lại

- Tạo namespace/database/queue riêng cho mỗi test run.
- Gắn run ID vào fixture và log để không lẫn dữ liệu giữa test.
- Dùng token TTL ngắn nhưng đủ thời gian để hoàn tất bước checkpoint.
- Chờ expiry bằng timestamp thực tế do issuer cấp, không dựa vào đồng hồ giả của ứng dụng nếu issuer dùng clock riêng.
- Dọn fixture sau khi test hoàn tất.
- Đặt timeout tổng để test không treo khi restore hoặc dependency không phản hồi.
- Giữ image/JDK/kernel cố định trong cùng một test suite.

## 11. Ma trận kiểm thử tổng hợp

Nên có một ma trận kết hợp thời gian tạm dừng và tình trạng dependency. Không nhất thiết mọi tổ hợp đều chạy trong mỗi commit; có thể chạy unit test nhanh thường xuyên và các scenario nặng trong CI integration/nightly.

| Scenario | Token | Cache TTL | Database/network | Kết quả cần xác nhận |
|---|---|---|---|---|
| Restore nhanh | Còn hạn | Còn hạn | Connection còn hoạt động | Restore không refresh/reconnect thừa nếu policy không yêu cầu |
| Pause ngắn | Gần hết hạn | Còn TTL | Connection idle | Token refresh theo skew; connection validation đúng |
| Pause vừa | Hết hạn | Vừa hết TTL | Peer đóng idle connection | Token mới, cache reload, pool/client mới |
| Pause dài | Access và refresh token hết hạn | Hết TTL lâu | Database/proxy restart | Re-auth hoặc fail closed; cache reload; reconnect có retry |
| Credential revoked | Bị thu hồi | Bất kỳ | Dependency còn hoạt động | Không dùng token cũ; readiness theo policy |
| Secret rotated | Credential cũ không còn hợp lệ | Cache có thể còn hạn | Database yêu cầu credential mới | Lấy secret mới và tạo pool mới |
| DNS/backend đổi | Còn hạn hoặc refresh được | Còn hạn | Endpoint cũ đóng | Resolve endpoint mới và tạo client mới |
| Dependency unavailable | Refresh endpoint hoặc DB tạm lỗi | TTL hết hạn | Không thể kết nối ngay | Readiness false, retry giới hạn, không crash loop |
| Multi-replica restore | Cùng token state cũ | Nhiều cache miss | Nhiều connection mới | Không có refresh/connection stampede vượt giới hạn |
| Clock anomaly | Expiry gần biên | TTL gần biên | Kết nối bình thường | Xử lý clock skew theo policy; không dùng thời gian âm sai lệch |

## 12. Xác minh readiness và fail-closed behavior

Một trong những assertion quan trọng nhất là ứng dụng không nhận traffic quá sớm. Sau restore, JVM có thể đã hoạt động nhưng token chưa refresh, database chưa reconnect hoặc consumer chưa tham gia group.

Test cần xác minh:

1. Readiness bắt đầu ở trạng thái false trong giai đoạn restore.
2. Token hết hạn không được dùng cho request tới dependency được bảo vệ.
3. Cache hết hạn không được trả như dữ liệu mới.
4. Connection cũ không được coi là khỏe chỉ vì wrapper object còn tồn tại.
5. Dependency retry có timeout/backoff và không giữ request vô hạn.
6. Readiness chỉ chuyển true sau khi các bước bắt buộc hoàn tất.
7. Nếu credential bị thu hồi vĩnh viễn, ứng dụng không báo ready và không tạo vòng retry vô hạn.

Nếu một số chức năng có thể hoạt động khi một dependency không khả dụng, readiness có thể dựa trên capability hoặc endpoint riêng. Tuy nhiên, phải xác định rõ capability nào bị tắt; không nên đánh dấu toàn bộ service ready khi luồng nghiệp vụ chính không thể hoạt động.

## 13. Kiểm thử nhiều replica và chống stampede

Một checkpoint image có thể được restore thành nhiều replica. Tất cả có thể chứa cùng token, cache entry, deadline và trạng thái client đã lưu. Khi restore đồng thời, chúng có thể cùng refresh token, tải lại cache hoặc mở connection.

Hãy kiểm tra:

- Số lần gọi token endpoint trong một khoảng thời gian.
- Số connection mới/giây và tổng connection theo database user.
- Số cache reload đồng thời cho cùng key.
- Thời gian từ restore đến readiness của từng replica.
- Jitter/backoff có phân tán các lần retry hay không.
- Instance identity và lease có được cấp riêng hay không.
- Một replica thất bại refresh có ảnh hưởng các replica khác không.

Không dùng một biến `AtomicBoolean` trong heap làm khóa toàn cụm. Nó chỉ điều phối thread trong một process và sẽ được nhân bản cùng checkpoint. Muốn giới hạn ở cấp cụm, cần coordinator, distributed lock/lease hoặc giới hạn rollout ở nền tảng triển khai.

## 14. Quan sát và log trong test

Để phân biệt lỗi token, TTL và connection, hãy ghi các mốc lifecycle có định danh rõ:

- `beforeCheckpoint-start` và `beforeCheckpoint-complete`.
- `checkpoint-created` kèm checkpoint ID/build ID.
- `afterRestore-start`.
- `token-refresh-start`, `token-refresh-success` hoặc `token-refresh-failure`.
- `cache-entry-expired`, `cache-reload-start` và `cache-reload-complete`.
- `connection-validation-failed`, `connection-recreated` và `dependency-ready`.
- `readiness-ready`.

Các metric hữu ích:

| Metric | Điều cần biết |
|---|---|
| Restore pause duration | Khoảng thời gian từ mốc checkpoint đến restore theo cách đo đã chọn |
| Token refresh count/latency | Số lần refresh và thời gian gọi issuer |
| Token refresh failure by class | Phân biệt lỗi hết hạn, thu hồi, cấu hình và lỗi tạm thời |
| Cache expired/reload count | Số entry hết hạn và số lần tải lại |
| Connection validation failures | Connection cũ không còn dùng được |
| New connection rate | Tốc độ mở kết nối sau restore |
| Pool acquisition latency/timeouts | Request phải chờ connection bao lâu |
| Reconnect attempts | Số lần retry trước khi dependency sẵn sàng |
| Restore-to-readiness duration | Thời gian thực tế để ứng dụng có thể phục vụ |

Không log access token, refresh token, cookie, password hoặc connection string có secret. Dùng token ID/hash đã được thiết kế an toàn nếu cần liên kết sự kiện, và tránh đưa ID có cardinality cao vào metric label.

## 15. Những lỗi thường gặp khi kiểm thử

### Chỉ restore ngay sau checkpoint

Token và connection vẫn có thể còn hạn, nên test không đi qua nhánh refresh/reconnect. Hãy tạo pause đủ dài hoặc chủ động thu hồi/đóng dependency từ bên ngoài.

### Dùng `Thread.sleep()` trong unit test

Test chậm và phụ thuộc lịch chạy. Inject `Clock` để kiểm thử deadline/TTL xác định; chỉ dùng thời gian thực trong integration test cần xác minh hệ thống bên ngoài.

### Dùng clock giả của ứng dụng để kết luận token server đã hết hạn

Issuer có clock riêng. Dịch chuyển `Clock` trong JVM không làm token server thay đổi thời gian. Dùng token TTL ngắn hoặc test issuer có thể điều khiển.

### Chỉ kiểm tra `isClosed()` hoặc object khác null

Wrapper có thể chưa biết peer đã đóng socket. Thực hiện validation query hoặc request thật sau restore.

### Không kiểm tra refresh token bị thu hồi

Test thành công khi refresh token còn hạn chưa chứng minh ứng dụng xử lý được `invalid_grant` hoặc rotation. Cần kiểm tra cả trường hợp thất bại.

### Không kiểm tra cache hết hạn

Cache object vẫn có thể tồn tại trong heap. Assertion cần chứng minh dữ liệu cũ không được trả và loader được gọi khi TTL hết.

### Bật readiness trước khi reconnect xong

Health endpoint có thể trả healthy dù request nghiệp vụ đầu tiên thất bại. Kiểm tra readiness và gọi đường nghiệp vụ thật.

### Dùng chung fixture hoặc credential giữa các test

Test song song có thể thu hồi token hoặc xóa cache của test khác. Tạo namespace, user, key và resource riêng theo test run.

### Chỉ test một replica

Không phát hiện refresh stampede, connection storm hoặc lease conflict. Chạy thêm scenario nhiều bản restore từ cùng image.

## 16. Quy trình triển khai bộ test trong CI

Một pipeline có thể chia test thành các nhóm:

```text
Pull request
  - Unit test với Clock giả lập
  - Token expiry/refresh policy
  - Cache TTL/invalidation
  - Connection manager state transitions

Integration job
  - Start database, broker và test identity provider
  - Start ứng dụng bằng JDK CRaC tương thích
  - Checkpoint thật
  - Chờ expiry/đóng connection/rotate credential
  - Restore thật
  - Verify token, cache, connection và readiness

Nightly / release gate
  - Pause dài và dependency restart
  - Token revoked/refresh token expired
  - DNS/TLS rotation
  - Multiple replicas restore đồng thời
  - Load/connection rate và failure recovery
```

CI phải pin phiên bản JDK CRaC, kernel/runtime và container image đã được xác minh. Nếu runner CI không hỗ trợ các yêu cầu checkpoint/restore, hãy chạy integration suite trên node pool hoặc VM chuyên dụng; unit test vẫn chạy ở mọi pull request.

Không đưa production secret vào test. Dùng issuer giả lập, credential staging và dữ liệu tổng hợp. Artifact checkpoint test nên có retention ngắn và quyền truy cập giới hạn vì nó cũng có thể chứa dữ liệu trong heap.

## 17. Checklist cho một bài test restore hoàn chỉnh

- [ ] Xác định token, TTL, lease và connection nào có thể hết hạn trong khoảng pause.
- [ ] Unit test dùng `Clock` để kiểm tra expiration ở trước, đúng tại và sau ranh giới hết hạn.
- [ ] Test access token hết hạn nhưng refresh token còn hợp lệ.
- [ ] Test refresh token hết hạn, bị thu hồi hoặc issuer tạm thời không khả dụng.
- [ ] Test cache TTL hết hạn và invalidation xảy ra khi tiến trình tạm dừng.
- [ ] Test database/proxy đóng connection idle và pool tạo connection mới.
- [ ] Test HTTP/WebSocket/gRPC hoặc broker reconnect theo giao thức ứng dụng đang dùng.
- [ ] Integration test tạo checkpoint thật và để thời gian trôi qua bên ngoài tiến trình.
- [ ] Restore test chạy trên JDK/kernel/runtime tương thích.
- [ ] Readiness false trong lúc refresh/reconnect và chỉ true sau khi dependency sẵn sàng.
- [ ] Test lỗi vĩnh viễn và lỗi tạm thời có chính sách khác nhau.
- [ ] Test nhiều replica để phát hiện refresh stampede và connection storm.
- [ ] Log/metric không làm lộ token, secret hoặc dữ liệu cá nhân.
- [ ] Test dọn fixture, checkpoint và tài nguyên sau khi hoàn tất.

## 18. Kết luận

Kiểm thử restore sau khi token, TTL và kết nối hết hạn phải xác minh trạng thái bên ngoài tiến trình đã thay đổi trong lúc checkpoint. Dùng `Clock` giả lập cho unit test để kiểm tra expiration và deadline một cách xác định. Dùng integration test với JDK CRaC thật để checkpoint, chờ bên ngoài tiến trình, làm hết hạn hoặc thu hồi token, để TTL trôi qua, đóng connection hoặc thay đổi backend rồi restore.

Sau restore, ứng dụng cần refresh credential, loại bỏ cache hết hạn, tạo lại connection và xác minh dependency bằng thao tác thực tế. Test cả đường phục hồi thành công lẫn trường hợp refresh/reconnect thất bại; readiness phải giữ false khi dependency bắt buộc chưa sẵn sàng. Cuối cùng, kiểm tra nhiều replica cùng restore để phát hiện refresh stampede, cache reload burst và connection storm. Khi các tình huống này được tự động hóa, checkpoint image có thể được kiểm chứng theo đúng vòng đời thực tế thay vì chỉ chứng minh rằng JVM có thể khôi phục bộ nhớ.
