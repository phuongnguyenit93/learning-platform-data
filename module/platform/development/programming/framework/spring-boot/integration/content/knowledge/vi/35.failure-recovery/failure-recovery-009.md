# Fallback có ý nghĩa nghiệp vụ và tránh che lỗi dữ liệu

## 1. Vì sao fallback không đơn thuần là trả giá trị mặc định?

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức kết nối giữa HTTP client, cơ sở dữ liệu, cache, message broker và các adapter Spring Integration. Những luồng này phải xử lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát được tình trạng tích hợp thực tế. Một hệ thống chịu lỗi không chỉ cần tiếp tục chạy khi downstream gặp sự cố; nó còn phải **không làm cho người dùng hoặc dịch vụ khác tin vào dữ liệu không đúng**.

**Fallback** là một hành vi thay thế được thiết kế trước khi đường xử lý chính thất bại hoặc tạm thời không khả dụng. Nó có thể là: trả một bản chụp còn đủ mới đã được xác minh, giảm bớt tính năng tùy chọn, giữ tác vụ ở trạng thái **PENDING**, chuyển một sự kiện sang nhánh khôi phục, hoặc **từ chối xử lý an toàn** khi không thể trả kết quả đáng tin cậy.

Ba ví dụ:

- Dịch vụ gợi ý sản phẩm tạm ngừng hoạt động: có thể ẩn khối gợi ý hoặc dùng danh sách đã được kiểm duyệt, vì không ảnh hưởng đến giao dịch chính.
- Dịch vụ theo dõi vận đơn trả 503: có thể hiển thị **trạng thái cuối cùng đã xác minh lúc 10:00**, với dấu hiệu dữ liệu có thể cũ; không được nói đó là trạng thái realtime.
- API xác nhận thanh toán timeout: **không** được mặc định coi là thanh toán thất bại, thành công, hoặc tạo lệnh thu tiền lần hai. Đây có thể là **kết quả chưa xác định** cần đối soát bằng idempotency key.

Vì vậy, fallback cần có **ý nghĩa nghiệp vụ, nguồn dữ liệu tin cậy, thời hạn hiệu lực, cách biểu diễn mức độ chắc chắn và quy trình phục hồi**. Chỉ viết **onErrorReturn(Collections.emptyList())**, **catch (Exception) { return true; }** hoặc đặt một giá trị mặc định không tạo ra tính chịu lỗi đúng nghĩa.

Sau bài học, bạn sẽ có thể:

1. Phân biệt lỗi hạ tầng tạm thời, lỗi nghiệp vụ, lỗi hợp đồng dữ liệu, lỗi bảo mật và kết quả chưa xác định.
2. Quyết định khi nào được **fail-open**, **fail-closed**, trả dữ liệu cũ có kiểm soát hoặc trả trạng thái PENDING.
3. Thiết kế fallback có nguồn, độ tươi, ngữ nghĩa và giới hạn thời gian rõ ràng.
4. Gắn fallback vào WebClient/Reactor, Resilience4j hoặc Spring Integration mà không che lỗi quan trọng.
5. Giữ đúng ranh giới giao dịch, ACK, retry, idempotency, dead-letter và event replay.
6. Kiểm thử fallback bằng tình huống thực, metric và hợp đồng API.

## 2. Phân loại lỗi trước khi quyết định có fallback hay không

Một bộ xử lý lỗi tổng quát kiểu **catch Exception** không đủ thông tin để chọn fallback. Hãy xây taxonomy theo nguyên nhân và hậu quả:

| Loại lỗi/kết quả | Ví dụ | Có thể fallback? | Cách xử lý thường phù hợp |
| --- | --- | --- | --- |
| **Transient infrastructure** | HTTP 503/504, connection timeout, database tạm quá tải | Có điều kiện | Retry có giới hạn, circuit breaker, dữ liệu dự phòng đã xác minh |
| **Rate limit** | HTTP 429 | Có điều kiện | Tôn trọng Retry-After, giảm tải, cache nếu hợp đồng cho phép |
| **Business not found** | Order ID không tồn tại thật | Thường **không** | Trả 404 hoặc domain NotFound, không biến thành 503 hoặc cache tùy tiện |
| **Business rejection** | Không đủ hàng, thanh toán bị từ chối | **Không** thay bằng success | Giữ kết quả từ chối theo nghiệp vụ |
| **Invalid data/contract** | JSON sai, thiếu trường bắt buộc, version schema lạ | **Không** để che lỗi | Báo lỗi hợp đồng, cách ly payload, điều tra producer |
| **Security failure** | Chữ ký không hợp lệ, token không đủ quyền | **Không** fail-open | Từ chối và ghi nhận bảo mật, không dùng dữ liệu nhạy cảm cũ |
| **Uncertain side effect** | HTTP POST timeout sau khi request đã gửi | Không tự quyết định thành công/thất bại | Tra cứu theo idempotency key, giữ PENDING, reconcile |
| **Cache miss** | Không có bản ghi dự phòng hợp lệ | Không có gì để fallback | Trả lỗi/giảm tính năng theo hợp đồng, không tự bịa dữ liệu |
| **Cached data expired/poisoned** | Snapshot quá hạn hoặc sai tenant | **Không** sử dụng | Fail closed cho dữ liệu đó; sửa cache/đối soát |
| **Circuit open** | Circuit breaker đang từ chối gọi upstream | Có điều kiện | Dữ liệu dự phòng có chứng minh độ tươi hoặc phản hồi unavailable |

**Một lỗi 404 là thông tin nghiệp vụ**, còn một lỗi 503 là thông tin về khả năng phục vụ của upstream. Không được chuyển cả hai thành **Optional.empty()** nếu caller cần phân biệt **không có dữ liệu** với **không truy cập được dữ liệu**.

### 2.1. Phân loại tại ranh giới adapter

Một HTTP adapter nên chuyển lỗi transport thành loại lỗi có ý nghĩa cho tầng nghiệp vụ:

~~~text
WebClientResponseException.NotFound
       → TrackingNotFoundException

HTTP 503, 504 hoặc timeout đã xác định
       → TrackingTemporarilyUnavailableException

JSON decode error / field bắt buộc thiếu
       → TrackingContractViolationException

HTTP 401 hoặc 403
       → UpstreamAuthorizationFailureException
~~~

Cấu trúc exception này là **quy ước của ứng dụng**, không phải một mapping mặc định của Spring. Không nên xây classifier chỉ dựa trên chuỗi **exception.getMessage()** vì message có thể thay đổi theo driver, locale, proxy hoặc phiên bản thư viện.

### 2.2. Lỗi có thể retry khác với lỗi được phép fallback

Hai quyết định không đồng nhất:

- **Retryable** nghĩa là cùng thao tác có thể được thử lại một cách an toàn và có khả năng thành công.
- **Fallback-eligible** nghĩa là có một cách trả kết quả thay thế **vẫn đúng hợp đồng nghiệp vụ**.

Ví dụ HTTP GET 503 có thể retry và có cache fallback. HTTP POST thanh toán 503 đôi khi cần tra cứu trạng thái, **không** được fallback sang **paid=true**. Payload JSON bị lỗi có thể không retry và cũng **không** được fallback bằng một giá trị đoán.

## 3. Ma trận fail-open, fail-closed và degraded mode

**Fail-open** cho phép luồng chính tiếp tục khi dịch vụ phụ không khả dụng. **Fail-closed** không thực hiện hành động cần dữ liệu chắc chắn. **Degraded mode** công khai một phần dịch vụ bị giảm chất lượng, với giới hạn rõ ràng.

| Nghiệp vụ | Khi upstream lỗi | Hành vi có thể chấp nhận | Hành vi nguy hiểm |
| --- | --- | --- | --- |
| Khối sản phẩm gợi ý | Recommendation API lỗi | Ẩn khối tùy chọn, không ảnh hưởng checkout | Gán nhãn “được cá nhân hóa” cho danh sách mặc định |
| Tra cứu vận đơn | Tracking API 503 | Hiển thị trạng thái cuối đã xác minh cùng thời điểm và nhãn **STALE** | Trả dữ liệu cũ như realtime |
| Tính thời gian giao hàng ước lượng | ETA service lỗi | Hiển thị “chưa có ước lượng” nếu hợp đồng cho phép | Tự cam kết ngày giao chính xác |
| Kiểm tra tồn kho trước bán | Inventory service lỗi | Chặn xác nhận hoặc giữ **PENDING** | Mặc định **available=true** |
| Thanh toán | Provider timeout | Trạng thái **UNKNOWN/PENDING**, truy vấn lại bằng request ID | Mặc định thành công hoặc thất bại rồi thu tiền lại |
| Authorization/tenant isolation | Auth service lỗi | Từ chối truy cập vào tài nguyên cần bảo vệ | Cho phép toàn quyền khi không có quyết định |
| Ghi sổ cái/đối soát | Database không sẵn sàng | Giữ lệnh chờ bền vững hoặc báo unavailable | Coi ghi thành công dù chưa commit |
| Event audit bắt buộc | Publisher không gửi được | Outbox/retry, không xác nhận hoàn tất sai | Nuốt lỗi và ACK nguồn nếu sẽ mất audit |

Đối với dữ liệu **quyết định hành động không thể đảo ngược**, fallback nên nghiêng về **fail-closed** hoặc trạng thái chờ đối soát. Với dữ liệu **trình bày không thiết yếu**, fail-open có thể hợp lý.

### 3.1. Câu hỏi bắt buộc trước khi phê duyệt fallback

1. **Quyết định nào** sẽ được thực hiện từ kết quả dự phòng?
2. Dữ liệu dự phòng **đến từ đâu**, đã được xác minh theo schema/tenant/version chưa?
3. **Độ cũ tối đa** có thể chấp nhận là bao nhiêu cho từng nghiệp vụ?
4. Caller có **nhận biết đây là fallback** và có thể lựa chọn hành động khác không?
5. Trong trường hợp không có fallback hợp lệ, có **mã lỗi hoặc trạng thái PENDING** nào mô tả chính xác không?
6. Đường fallback có gây **side effect** hoặc vi phạm idempotency không?
7. Kết quả sẽ được **đo, đối soát và khôi phục** thế nào khi upstream phục hồi?

Không nên phê duyệt fallback chỉ vì nó làm tỷ lệ HTTP 5xx trên dashboard giảm.

## 4. Hợp đồng dữ liệu fallback: nguồn, độ tươi và mức độ chắc chắn

Một API theo dõi vận đơn có thể trả thông tin cuối cùng đã xác minh. Khi phản hồi đó được dùng như fallback, kết quả cần chỉ rõ:

~~~json
{
  "orderId": "O-204",
  "state": "IN_TRANSIT",
  "freshness": "STALE",
  "sourceUpdatedAt": "2026-11-21T09:58:00Z",
  "servedAt": "2026-11-21T10:02:00Z",
  "notice": "Last verified tracking update; live provider unavailable"
}
~~~

Ở đây:

- **state=IN_TRANSIT** là trạng thái **đã được xác minh trước đó**, không phải cam kết trạng thái hiện tại.
- **sourceUpdatedAt** là thời điểm trạng thái được upstream ghi nhận, không phải thời điểm cache được đọc.
- **servedAt** cho biết thời gian phản hồi được tạo.
- **freshness=STALE** giúp UI/consumer phân biệt dữ liệu cũ với dữ liệu live.
- **notice** là thông điệp giải thích; logic máy nên dựa vào các trường có cấu trúc, không parse câu tiếng Anh.

### 4.1. Kết quả có kiểu rõ ràng

~~~java
public enum Freshness {
    LIVE,
    STALE
}

public record TrackingView(
        String orderId,
        String state,
        Instant sourceUpdatedAt,
        Instant servedAt,
        Freshness freshness) {
}
~~~

Không nên đặt mọi lỗi là một chuỗi **status="UNKNOWN"** rồi giả vờ cùng ngữ nghĩa với trạng thái vận chuyển **IN_TRANSIT** hoặc **DELIVERED**. Nếu không có nguồn dữ liệu hợp lệ, API nên trả lỗi hoặc một trạng thái **availability** riêng thay vì tạo một bản ghi nghiệp vụ không có căn cứ.

Với một sản phẩm lớn, có thể dùng kiểu bao:

~~~java
public sealed interface LookupOutcome<T>
        permits LookupOutcome.Available, LookupOutcome.Unavailable {

    record Available<T>(
            T value,
            Freshness freshness,
            Instant sourceUpdatedAt) implements LookupOutcome<T> {
    }

    record Unavailable<T>(
            String reasonCode,
            boolean retryable) implements LookupOutcome<T> {
    }
}
~~~

Đây là ví dụ Java 17+ dùng **sealed interface** và record. Contract này cho phép tầng controller phân biệt **có dữ liệu đáng tin (LIVE/STALE)** và **không thể cung cấp dữ liệu**. Với lỗi **not found**, có thể bổ sung kiểu **NotFound** riêng nếu nghiệp vụ cần; không gộp vào unavailable.

### 4.2. Không dùng status HTTP để đánh lừa consumer

Nếu hợp đồng công khai cho phép hiển thị snapshot, **HTTP 200 kèm freshness=STALE** có thể hợp lý cho endpoint *informational*, nhưng phải được đặc tả rõ trong API contract. Nếu caller yêu cầu một quyết định authoritative, **HTTP 503** hoặc trạng thái tường minh **PENDING/UNAVAILABLE** thường đúng hơn.

Không mặc định trả **HTTP 200 + empty body** cho mọi failure. Nó có thể làm caller hiểu “đã xử lý, không có dữ liệu” và bỏ qua bước retry/đối soát. Với kết quả **UNKNOWN** của payment, cũng không được tự dùng 200 cho **PAID** chỉ vì request HTTP đã được nhận.

## 5. Chính sách cache fallback: chỉ dùng dữ liệu đã xác minh

Một cache fallback đúng phải thỏa **cùng tenant, cùng entity, schema hợp lệ, tính toàn vẹn và độ cũ tối đa**. Cần phân biệt:

| Thời điểm | Ý nghĩa |
| --- | --- |
| **sourceUpdatedAt** | Thời gian trạng thái tại hệ thống nguồn thực sự được cập nhật |
| **verifiedAt** | Lúc ứng dụng kiểm tra và chấp nhận nội dung làm dữ liệu đáng tin |
| **cachedAt** | Lúc ghi cache, có thể khác verifiedAt |
| **expiresAt / maxStale** | Thời hạn lưu và cửa sổ được phép phục vụ stale |
| **servedAt** | Lúc fallback được trả cho caller |

### 5.1. Cache TTL khác với maximum staleness

Một bản ghi có thể còn nằm trong Redis 24 giờ để phục vụ đối soát, nhưng **không có nghĩa UI được phép xem nó là trạng thái hiện tại trong 24 giờ**. Cần tách **retention TTL** khỏi **ngưỡng staleness dùng cho fallback**. Ngưỡng này phụ thuộc nghiệp vụ: gợi ý tùy chọn có thể chịu vài giờ; ETA có thể chịu vài phút; kết quả thanh toán authoritative có thể không được dùng stale để quyết định.

Ví dụ cache entry:

~~~java
public record VerifiedTrackingSnapshot(
        String tenantId,
        String orderId,
        String state,
        Instant sourceUpdatedAt,
        Instant verifiedAt) {
}
~~~

Chỉ lưu snapshot sau khi **payload upstream đã được validate đầy đủ**. Không ghi một response JSON lỗi hoặc dữ liệu chưa xác minh vào cache rồi sử dụng nó ở fallback tiếp theo.

### 5.2. Bảo vệ không gian khóa của tenant

Cache key phải phản ánh phạm vi dữ liệu:

~~~text
tracking:v2:{tenantId}:{orderId}
~~~

Nhưng tenantId đến từ user input **không tự đáng tin**. Nguồn tenant phải được xác thực và phân quyền tại ingress; cache lookup cũng phải kiểm tra khóa và giá trị thuộc đúng tenant. Nếu fallback trả snapshot của tenant khác, đây là **lỗi bảo mật**, không phải “phục hồi thành công”.

Nếu cache bị đánh dấu poisoned, quá hạn hoặc có field thiếu, **không** được tự bỏ qua validation để tăng tỷ lệ fallback success. Thay vào đó, loại entry khỏi đường phục vụ, ghi metric phân loại và dùng quy trình rebuild/đối soát nguồn dữ liệu.

## 6. WebClient: chỉ fallback với lỗi được cho phép

Ví dụ đầy đủ ở mức service: đọc trạng thái vận chuyển từ một downstream HTTP và dùng snapshot đã được xác minh khi gặp **timeout hoặc 503/504**. Đoạn code giả định ứng dụng WebFlux và có một kho snapshot reactive.

### 6.1. Contract và abstraction

~~~java
public record TrackingDto(
        String orderId,
        String state,
        Instant sourceUpdatedAt) {
}

public interface VerifiedTrackingStore {
    Mono<VerifiedTrackingSnapshot> findVerified(
            String tenantId, String orderId);
}

public final class TrackingNotFoundException
        extends RuntimeException {
    public TrackingNotFoundException(String orderId) {
        super("Unknown tracking order: " + orderId);
    }
}

public final class TrackingContractViolationException
        extends RuntimeException {
    public TrackingContractViolationException(String message) {
        super(message);
    }
}
~~~

**VerifiedTrackingStore** là interface của ứng dụng; implementation có thể dùng Redis, database hoặc document store. Nó chỉ được trả snapshot đã được validate/được phép sử dụng, **không phải cache của tất cả response kể cả response lỗi**.

### 6.2. Service có fallback có điều kiện

~~~java
@Service
public class OrderTrackingLookup {

    private static final Duration MAX_STALE =
            Duration.ofMinutes(5);
    private static final Duration MAX_SOURCE_AGE =
            Duration.ofHours(24);
    private static final Set<String> ALLOWED_STATES =
            Set.of("CREATED", "IN_TRANSIT", "DELIVERED");

    private final WebClient trackingWebClient;
    private final VerifiedTrackingStore snapshots;
    private final Clock clock;

    public OrderTrackingLookup(
            WebClient trackingWebClient,
            VerifiedTrackingStore snapshots,
            Clock clock) {
        this.trackingWebClient = trackingWebClient;
        this.snapshots = snapshots;
        this.clock = clock;
    }

    public Mono<TrackingView> find(
            String authenticatedTenantId,
            String orderId) {
        return trackingWebClient.get()
                .uri("/tracking/{orderId}", orderId)
                .header("X-Tenant-Id", authenticatedTenantId)
                .retrieve()
                .onStatus(
                        status -> status.value() == 404,
                        response -> Mono.error(
                                new TrackingNotFoundException(orderId)))
                .bodyToMono(TrackingDto.class)
                .switchIfEmpty(Mono.error(
                        new TrackingContractViolationException(
                                "Tracking response body is missing")))
                .map(dto -> verifiedLiveView(orderId, dto))
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(
                        this::isEligibleForFallback,
                        error -> fromVerifiedSnapshot(
                                authenticatedTenantId, orderId, error));
    }

    private TrackingView verifiedLiveView(
            String requestedOrderId, TrackingDto dto) {
        if (dto.orderId() == null
                || !dto.orderId().equals(requestedOrderId)
                || dto.sourceUpdatedAt() == null
                || !ALLOWED_STATES.contains(dto.state())) {
            throw new TrackingContractViolationException(
                    "Tracking response failed contract validation");
        }
        return new TrackingView(
                dto.orderId(),
                dto.state(),
                dto.sourceUpdatedAt(),
                clock.instant(),
                Freshness.LIVE);
    }

    private boolean isEligibleForFallback(Throwable error) {
        if (error instanceof TimeoutException) {
            return true;
        }
        if (error instanceof WebClientResponseException response) {
            int status = response.getStatusCode().value();
            return status == 503 || status == 504;
        }
        return false;
    }

    private Mono<TrackingView> fromVerifiedSnapshot(
            String tenantId, String orderId, Throwable originalError) {
        Instant now = clock.instant();

        return snapshots.findVerified(tenantId, orderId)
                .filter(entry ->
                        tenantId.equals(entry.tenantId())
                        && orderId.equals(entry.orderId())
                        && ALLOWED_STATES.contains(entry.state())
                        && entry.sourceUpdatedAt() != null
                        && entry.verifiedAt() != null
                        && !entry.verifiedAt().isAfter(now)
                        && !entry.sourceUpdatedAt().isAfter(now)
                        && Duration.between(
                                entry.verifiedAt(), now)
                                .compareTo(MAX_STALE) <= 0
                        && Duration.between(
                                entry.sourceUpdatedAt(), now)
                                .compareTo(MAX_SOURCE_AGE) <= 0)
                .map(entry -> new TrackingView(
                        orderId,
                        entry.state(),
                        entry.sourceUpdatedAt(),
                        now,
                        Freshness.STALE))
                .switchIfEmpty(Mono.error(originalError));
    }
}
~~~

Các import được lược bỏ: WebClient, WebClientResponseException, Mono, Duration, Instant, Clock, Set, TimeoutException và @Service. **authenticatedTenantId** phải được lấy từ ngữ cảnh đã xác thực, không chấp nhận tùy ý từ request header của người dùng. Trong ứng dụng thật còn phải kiểm tra tenant được phép truy cập order đó, và có thể validate không cho timestamp của nguồn ở tương lai bất hợp lý.

Điểm thiết kế:

1. **404** được chuyển thành **TrackingNotFoundException** và **không** lọt vào fallback.
2. Response 2xx thiếu body hoặc sai schema thành **TrackingContractViolationException**, **không** lọt vào fallback.
3. Chỉ **timeout operator**, HTTP **503** và **504** được xét đến.
4. Snapshot phải khớp tenant/orderId, trạng thái cho phép, timestamp hợp lệ, **verifiedAt không quá 5 phút** và **sourceUpdatedAt không quá 24 giờ** trong chính sách minh họa. Hai ngưỡng là độc lập; production cần xác định theo trạng thái và mức độ quan trọng của dữ liệu.
5. Nếu cache không có entry hợp lệ, phát lại **lỗi gốc**, không trả status giả.
6. Kết quả fallback luôn mang **Freshness.STALE** và **sourceUpdatedAt** gốc.

**Phạm vi cố ý bảo thủ:** timeout của transport Netty hoặc lỗi kết nối có thể xuất hiện dưới kiểu exception khác **TimeoutException**. Đoạn code không tự fallback với mọi **WebClientRequestException**, vì nhóm đó còn có thể chứa lỗi TLS hoặc vấn đề bảo mật. Muốn hỗ trợ connect timeout/DNS failure, hãy bổ sung classifier đã kiểm chứng theo cause ở HTTP adapter và test rõ từng loại lỗi. Đừng viết **onErrorResume(Throwable.class, ...)**.

### 6.3. Còn việc lưu snapshot mới thì sao?

Để cache chỉ chứa dữ liệu đã xác minh, nên tổ chức một bước **storeVerified** riêng sau khi kiểm tra payload và trước khi phân phối tới downstream có hợp đồng phù hợp:

~~~text
Live response
  → validate contract + tenant/orderId + version
  → update verified snapshot với điều kiện version
  → trả LIVE hoặc phát sự kiện nguồn đã xác minh
~~~

Nếu việc lưu cache thất bại nhưng live response hợp lệ, chính sách có thể coi cache là **best-effort** và vẫn trả LIVE; tuy nhiên phải ghi metric lỗi cache. Không tự **subscribe()** một operation lưu cache trong mapper khiến lỗi ghi bị mất và chạy ngoài lifecycle của request. Nếu cache giữ một snapshot cũ hơn do race, cần dùng **version/updatedAt conditional update** để chống dữ liệu đi lùi.

### 6.4. Timeout không chứng minh downstream chưa xử lý

Với **GET thuần đọc**, fallback từ snapshot có thể chấp nhận. Với **POST/PUT có side effect**, timeout có thể xảy ra sau khi downstream commit. **Hủy subscription của WebClient không bảo đảm remote transaction rollback**. Cần idempotency key, tra cứu trạng thái và quy trình xác nhận trước khi retry.

## 7. Retry, timeout, circuit breaker và fallback phải có thứ tự rõ

Một đường phục hồi thường có nhiều tầng:

~~~mermaid
flowchart TD
    A["Business request"] --> B["Validate + authorize"]
    B --> C["Circuit breaker / bulkhead"]
    C -->|"Cho phép"| D["HTTP/DB attempt với timeout riêng"]
    C -->|"Open / rejected"| E{"Fallback hợp lệ?"}
    D -->|"Thành công, dữ liệu hợp lệ"| F["Trả LIVE"]
    D -->|"Lỗi retryable"| G{"Còn ngân sách retry?"}
    G -->|"Có"| H["Backoff có giới hạn"]
    H --> D
    G -->|"Không"| E
    D -->|"Dữ liệu sai / 4xx nghiệp vụ"| I["Trả lỗi thật, không fallback"]
    E -->|"Cache verified, còn hạn"| J["Trả STALE có metadata"]
    E -->|"Không"| K["Trả UNAVAILABLE / PENDING"]
~~~

Không nên mặc định flow luôn chạy đủ retry rồi mới fallback. Nếu circuit breaker mở hoặc deadline tổng sắp hết, fallback sớm có thể giảm tải; nhưng phải có chỉ dẫn nghiệp vụ rõ để không che việc downstream đang hỏng kéo dài.

### 7.1. Retry có giới hạn trước fallback

~~~java
Mono<TrackingView> live = trackingWebClient.get()
        .uri("/tracking/{id}", orderId)
        .retrieve()
        .bodyToMono(TrackingDto.class)
        .map(dto -> verifiedLiveView(orderId, dto))
        .timeout(Duration.ofSeconds(1))
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .filter(this::isEligibleForFallback))
        .timeout(Duration.ofSeconds(3));
~~~

**Retry.backoff(2, ...)** cho phép tối đa **hai lần thử lại**, ngoài attempt đầu. **timeout(1 giây)** bên trong chuỗi retry giới hạn từng attempt; **timeout(3 giây)** bên ngoài giới hạn tổng thời gian gồm retry và backoff. Đoạn minh họa này cần thêm kiểm tra body rỗng và schema/HTTP 404 từ phần 6 trong code production; không nên copy nó thay cho service hoàn chỉnh. Với retry và fallback, phải kiểm thử đúng vị trí các operator, vì đặt **timeout** sau **retryWhen** có nghĩa khác với đặt trước.

Không được cho phép retry không giới hạn ở cả **WebClient**, **Resilience4j**, **Spring Integration advice** và **broker redelivery**. Nếu mỗi tầng retry ba lần, tổng request có thể tăng mạnh, gây tải đột biến lên upstream vốn đang lỗi.

### 7.2. Circuit breaker không phải máy chọn dữ liệu

**Circuit breaker** quan sát lỗi và tạm ngừng gọi một downstream khi vượt ngưỡng; nó không biết cache nào được phép dùng, không biết một đơn thanh toán có thể tiếp tục hay không. Một lỗi **CallNotPermittedException** (ví dụ của Resilience4j) có thể là tín hiệu kích hoạt **chính sách fallback đã định nghĩa**, không phải bằng chứng rằng mọi trạng thái có thể được thay bằng true/empty.

Với Resilience4j, cần các module tương thích Spring Boot, và nếu tích hợp Reactor thì có adapter reactive phù hợp. Không nhầm **fallbackMethod** của annotation là cơ chế transaction hoặc validation dữ liệu. Lớp fallback nên được tách thành business policy có thể kiểm thử độc lập, thay vì trả một giá trị mặc định chung cho mọi exception.

### 7.3. Bulkhead và rate limit

Khi fallback là cache/DB nội bộ, nó cũng có thể quá tải. **Bulkhead** giới hạn số request đồng thời tới downstream; fallback phải có ngân sách latency, concurrency và bộ nhớ riêng. Khi upstream trả **429**, hãy đánh giá **Retry-After**, không tạo retry storm rồi dồn toàn bộ tải vào cache đang yếu.

## 8. Trạng thái UNKNOWN/PENDING là một phương án phục hồi hợp lệ

Đối với nghiệp vụ có side effect, fallback an toàn không nhất thiết là trả một giá trị nghiệp vụ thay thế. Ví dụ payment provider có thể đã nhận lệnh nhưng client timeout:

~~~text
POST /payments với idempotency key=pay-7821
      |
      +--- Provider trả kết quả rõ ràng ---> lưu kết quả thật
      |
      +--- Timeout / mất response -------> trạng thái UNKNOWN
                                              |
                                              v
                                    GET status theo pay-7821
                                              |
                         +--------------------+-------------------+
                         |                                        |
                   Đã hoàn thành                              Chưa rõ
                         |                                        |
                         v                                        v
                  Ghi kết quả đã xác minh              PENDING + retry/reconcile
~~~

**Không tạo paymentId mới và gửi lại một khoản thu** chỉ vì response timeout. Nếu provider hỗ trợ idempotency key, dùng đúng key cũ theo thời hạn hợp đồng; nếu không, cần cơ chế tìm giao dịch theo tham chiếu/correlation và xử lý thủ công trường hợp không chắc chắn.

Một API có thể trả kiểu domain:

~~~java
public enum PaymentDecision {
    CONFIRMED,
    REJECTED,
    PENDING_RECONCILIATION
}

public record PaymentOutcome(
        String paymentRequestId,
        PaymentDecision decision,
        Instant checkedAt) {
}
~~~

**PENDING_RECONCILIATION** không phải là một trạng thái thanh toán thành công. Client/UI phải được thiết kế để **không giao hàng, không ghi nhận doanh thu cuối cùng và không lặp lệnh thu tiền mới** chỉ vì đang chờ đối soát.

Một fallback như trên phải có **dữ liệu chờ bền vững**, cơ chế poll hoặc callback, timeout nghiệp vụ cuối cùng, cảnh báo các giao dịch treo lâu và quy tắc xử lý khi provider không cung cấp được trạng thái.

## 9. Fallback trong Spring Integration: errorChannel không phải kết quả thành công

Trong Spring Integration, một flow có thể nhận thông điệp từ HTTP gateway, file adapter, Kafka, RabbitMQ hoặc JMS. Khi handler lỗi, kết quả phụ thuộc vào **DirectChannel/ExecutorChannel**, loại endpoint, retry advice, transaction và error channel. Không thể áp dụng một quy tắc “bắt exception rồi gửi message khác” cho mọi luồng.

~~~mermaid
flowchart TD
    A["Inbound adapter nhận message"] --> B["Validate, parse, authorize"]
    B --> C["Handler/HTTP/database"]
    C -->|"Thành công"| D["Ghi nhận nghiệp vụ/ACK theo contract"]
    C -->|"Lỗi transient"| E["Retry policy có giới hạn"]
    E -->|"Khắc phục được"| D
    E -->|"Hết retry"| F["Recovery decision"]
    C -->|"Poison/invalid contract"| G["Lỗi dữ liệu: không fallback thành success"]
    G --> F
    F -->|"Optional enrichment"| H["Degraded result có provenance"]
    F -->|"Bắt buộc xử lý"| I["Durable retry/DLQ/outbox"]
    F -->|"Không có đường phục hồi"| J["Propagate failure, giữ khả năng redelivery"]
~~~

**ErrorMessage trên errorChannel** là thông điệp mô tả lỗi trong flow, **không phải** bản tin đã vào dead-letter queue/topic của broker. Một error flow nhận được ErrorMessage, ghi log rồi kết thúc thành công có thể khiến adapter upstream coi là lỗi đã được xử lý, tùy cơ chế ACK và recovery callback.

### 9.1. RequestHandlerRetryAdvice và recovery callback

Spring Integration có **RequestHandlerRetryAdvice** để retry một message handler theo chính sách Spring Retry, và **ErrorMessageSendingRecoverer** có thể chuyển lỗi cuối thành ErrorMessage sang một channel. Một thiết kế khái niệm:

~~~text
inputChannel
  → idempotency/validation
  → request handler + RequestHandlerRetryAdvice
       ├─ transient error, attempts còn → retry
       ├─ success → outputChannel
       └─ exhausted → ErrorMessageSendingRecoverer
                         → recoveryChannel
                             ├─ optional lookup → STALE có metadata
                             ├─ critical command → durable failure queue
                             └─ invalid payload → quarantine/DLQ
~~~

**Recovery callback có thể khiến exception không còn lan về listener chính.** Nếu recovery flow chưa ghi nhận kết quả bền vững mà vẫn return, broker có thể ACK nguồn và sự kiện quan trọng bị mất. Do đó, trước khi gắn recoverer, cần kiểm tra:

1. Callback được coi là **đã xử lý** trong container hay sẽ rethrow?
2. Đường recovery có **lưu bền** bản tin cần xử lý lại không?
3. Publish sang dead-letter có được **xác nhận**, hay chỉ mới gửi bất đồng bộ?
4. Có trạng thái idempotency/outbox/inbox để xử lý crash sau một phần công việc không?
5. Khi recovery channel lại lỗi, exception sẽ đi đâu và source adapter có ACK không?

Không đồng nhất **nullChannel** với DLQ. Gửi một lệnh quan trọng tới nullChannel rồi báo “đã phục hồi” thực chất có thể là **xóa bỏ trách nhiệm xử lý message**.

### 9.2. Fallback read-only khác với fallback command

Đối với một **enrichment service** bổ sung thông tin trình bày tùy chọn, có thể dùng cache verified để tiếp tục xử lý nếu downstream đọc thất bại. Kết quả phải có cờ **degraded/freshness** để router biết đây là dữ liệu thiếu độ tươi.

Đối với một **command handler** cập nhật kho, ghi ledger hoặc xác nhận thanh toán, không nên thay lỗi bằng payload **success=true**. Nếu không thể hoàn tất, phải để nguồn biết kết quả chưa có, giữ message ở durable queue hoặc tạo một trạng thái **PENDING_RECONCILIATION** có thể theo dõi.

### 9.3. Async boundary thay đổi cách lỗi được nhìn thấy

Với **DirectChannel**, handler thường chạy trên thread gửi, exception có thể lan ngược trực tiếp tới gateway/adapter. Với **ExecutorChannel** hoặc QueueChannel, lỗi có thể được xử lý bất đồng bộ và chuyển thành **ErrorMessage** thay vì ném ngay trên thread nguồn. Transaction thread-bound ban đầu cũng có thể không đi qua ranh giới async.

Khi thiết kế fallback, phải vẽ rõ:

~~~text
Thread nguồn / transaction A
   ↓ send qua async channel
Thread worker / transaction B
   ↓ handler failed
errorChannel / recoverer
   ↓? ACK, DLQ, retry, fallback
~~~

Không dựa vào việc HTTP gateway đã trả 202 để kết luận message sẽ không bị mất; cần có durable handoff nếu contract yêu cầu.

## 10. Message broker: ACK, retry và DLQ không được che thất bại

Với giao nhận **at-least-once**, message có thể được gửi lại khi chưa ACK. Fallback không nên biến một lỗi cần retry thành một phản hồi thành công giả.

### 10.1. Tình huống nguy hiểm

~~~text
Broker gửi InventoryReserved
  → consumer ghi DB bước A
  → gọi warehouse service thất bại
  → catch Exception
  → return success / không throw
  → container ACK message
  → warehouse không cập nhật, nhưng không còn redelivery
~~~

Nếu side effect warehouse là bắt buộc, đây **không phải** fallback hợp lệ. Cần một protocol như outbox/inbox, trạng thái workflow bền vững, saga có bù trừ hoặc retry queue với dead-letter policy phù hợp.

### 10.2. Ma trận quyết định sau thất bại

| Kết quả handler | Hành động nguồn thường hợp lý | Điều kiện cần kiểm tra |
| --- | --- | --- |
| Business commit thành công | ACK/commit offset theo adapter | Đã commit và có idempotency |
| Event duplicate đã xử lý trước đó | ACK, không side effect lặp | Receipt/unique key đã commit |
| Lỗi tạm thời trước commit | Retry/requeue có giới hạn | Không ACK sớm, có deadline/backoff |
| Poison message không thể xử lý | DLQ/quarantine theo chính sách | Đích lỗi tồn tại và publish/route đáng tin |
| Lỗi sau một phần side effect | Đối soát/bù trừ/idempotent retry | Không tự suy ra rollback các hệ thống khác |
| Fallback optional được chấp nhận | Có thể ACK sau khi outcome dự phòng được ghi nhận | Contract nói rõ đây là kết quả cuối hợp lệ |
| Kết quả chưa xác định | Giữ PENDING/reconciliation | Không phát success hoặc duplicate payment |

**Cấu hình ACK khác nhau giữa Spring Kafka, Spring AMQP/RabbitMQ, JMS và Spring Integration adapters**. Một ErrorMessage được xử lý hoặc một listener return không phải bằng chứng mọi broker đều ACK cùng thời điểm. Phải kiểm tra cơ chế transaction, manual/auto acknowledgement, recoverer và dead-letter route thực tế.

### 10.3. Dead-letter cũng cần bằng chứng

Phân biệt:

- **Quyết định dead-letter**: ứng dụng muốn đưa bản tin sang nhánh lỗi.
- **Publish/route confirmed**: có bằng chứng broker đã ghi/route theo cơ chế phù hợp.
- **Dead-letter observed**: một consumer/metric broker thấy bản tin ở queue/topic đích.

Nếu publish dead-letter lỗi nhưng nguồn đã ACK, message có thể mất. Do đó, “fallback sang DLQ” chỉ hợp lệ khi có cơ chế **durable handoff** và đường khôi phục khi DLQ không sẵn sàng.

## 11. Giao dịch, rollback và fallback: tránh commit trạng thái dở dang

Một transaction chỉ rollback khi framework quan sát đúng failure hoặc được yêu cầu rollback. Nếu service nuốt exception bên trong ranh giới **@Transactional**, Spring có thể xem lời gọi là thành công và commit những thao tác đã ghi.

Ví dụ anti-pattern:

~~~java
// ANTI-PATTERN: không dùng kiểu này cho nghiệp vụ bắt buộc.
@Transactional
public void processOrder(OrderCommand command) {
    orderRepository.markProcessing(command.orderId());

    try {
        paymentGateway.capture(command.paymentRequestId());
    } catch (Exception ex) {
        // Log và return có thể làm DB commit PROCESSING
        // mặc dù trạng thái payment chưa rõ.
        log.warn("Payment unavailable");
        return;
    }

    orderRepository.markPaid(command.orderId());
}
~~~

Đoạn minh họa không phải code production, các interface do ứng dụng định nghĩa. Hai vấn đề:

1. **Payment API bên ngoài không nằm trong transaction DB**, kể cả khi method có @Transactional.
2. **Return sau catch** có thể commit trạng thái **PROCESSING** chưa được xử lý đúng, và caller/broker có thể xem là hoàn thành.

Thay vào đó, thiết kế một state machine bền vững:

~~~text
NEW
  → PAYMENT_REQUESTED (có idempotency key)
      → CONFIRMED (đã có bằng chứng provider)
      → REJECTED (đã có kết quả từ chối)
      → PENDING_RECONCILIATION (kết quả chưa rõ)
             → status inquiry / webhook / manual review
~~~

Trong transaction DB, ghi **trạng thái đã biết** và **outbox event** tương ứng; bên ngoài transaction, gọi provider rồi ghi nhận kết quả bằng một transaction mới có optimistic version/checkpoint phù hợp. Không tạo ra **CONFIRMED** từ một exception handler.

### 11.1. Fallback ghi dữ liệu là một nghiệp vụ mới

Nếu fallback cần ghi cache, hàng đợi, audit hay trạng thái PENDING, thao tác đó cũng có thể lỗi. Nó cần:

- Trạng thái bền vững hoặc transaction phù hợp.
- Idempotency key/correlation ID ổn định qua retry.
- Đường bù trừ và đối soát nếu một phần được commit.
- Metrics riêng cho **fallback attempted**, **fallback succeeded** và **fallback failed**.
- Quy tắc ACK rõ nếu việc ghi fallback chưa hoàn tất.

**Không coi ghi một entry in-memory là bảo đảm phục hồi** khi tiến trình có thể restart.

## 12. Đảm bảo fallback không làm sai hợp đồng dữ liệu

### 12.1. Không che lỗi bằng giá trị “hợp lệ” giả

Các mẫu code thường dẫn tới lỗi nghiệp vụ:

~~~java
// Sai: upstream mất kết nối thành "không còn sản phẩm".
return productClient.findById(id)
        .onErrorReturn(Optional.empty());

// Sai: inventory API lỗi thành có hàng.
return inventoryClient.available(sku)
        .onErrorReturn(true);

// Sai: có thể che JSON/schema/auth error và đánh mất tín hiệu.
return partnerClient.fetch(request)
        .onErrorResume(ex -> Mono.just(defaultBusinessRecord()));
~~~

Các hàm trong ví dụ là API minh họa của ứng dụng. Vấn đề chính không phải cú pháp Reactor, mà là **một lỗi hạ tầng bị biến thành giá trị nghiệp vụ thành công**.

**Giá trị 0**, **false**, **empty list** và **null** đều có ý nghĩa nghiệp vụ khác nhau theo từng API. Ví dụ **price=0** có thể tạo hàng miễn phí; **available=0** có thể làm gián đoạn bán hàng; **permissions=[]** có thể là fail-closed hợp lý trong một API authorization nhưng phải được diễn giải là “không cấp quyền” và bảo đảm không rò rỉ trạng thái nội bộ.

### 12.2. Phân biệt payload sai với dữ liệu thiếu

| Trạng thái | Ví dụ | Kết quả đúng hơn |
| --- | --- | --- |
| **ABSENT** | Kho dữ liệu xác nhận đơn không tồn tại | NotFound/domain absence |
| **EMPTY** | API thành công với danh sách sự kiện thực sự rỗng | Kết quả rỗng hợp lệ |
| **UNAVAILABLE** | API không liên lạc được | Error/unavailable, có thể fallback hợp lệ |
| **STALE** | Dữ liệu đã xác minh trước đó, hiện được phục vụ theo chính sách độ cũ cho phép | Snapshot kèm freshness và as-of |
| **INVALID** | Schema sai, hash/chữ ký không khớp | Contract/security error; không biến thành EMPTY |
| **UNKNOWN** | Side effect gửi thành công nhưng response mất | PENDING/reconciliation |

Đặc biệt, **trả về một Optional.empty khi JSON không deserialize được** sẽ che lỗi hợp đồng dữ liệu. Hệ thống có thể silently ngừng hiển thị đơn, bỏ lỡ cập nhật hoặc bỏ qua event cần sửa.

### 12.3. Versioning và snapshot cũ

Một cache snapshot có thể được verified 2 phút trước nhưng **sourceUpdatedAt** là 4 ngày trước. Tùy nghiệp vụ, đó có thể là trạng thái bình thường (vận đơn chưa thay đổi) hoặc dữ liệu quá cũ. Vì vậy, cần chọn cả:

- **Maximum cache age**: thời gian kể từ lần xác minh/cập nhật cache.
- **Maximum acceptable source age** hoặc quy tắc **event version**: có chấp nhận tình trạng nguồn không cập nhật trong thời gian dài?
- **Trạng thái cuối có thể thay đổi hay không**: ví dụ trạng thái DELIVERED đã xác minh có thể có quy tắc retention khác IN_TRANSIT.
- **Thứ tự cập nhật**: cache write của response cũ không được ghi đè response mới chỉ vì network trả không theo thứ tự.

Thiết kế policy nên là một hàm thuần có đầu vào **snapshot + request context + thời gian hiện tại + contract version**, và trả về quyết định có lý do. Không phân tán các điều kiện này vào hàng chục catch block.

## 13. Quan sát được fallback là bắt buộc

Một fallback có thể làm người dùng không gặp 5xx, nhưng cũng có thể che giấu sự cố downstream kéo dài hàng giờ. Vì vậy, phải đo **sự thất bại của đường chính** dù cuối cùng API đã trả được kết quả dự phòng.

| Metric đề xuất | Điểm đo | Ý nghĩa |
| --- | --- | --- |
| **app.integration.primary.outcomes** | Sau mỗi attempt chính | success / failure và error_kind |
| **app.integration.retry.started** | Khi retry attempt bắt đầu | Số lần thực thi lại, không phải lịch hẹn retry |
| **app.integration.fallback.attempts** | Bước đầu của policy fallback | Số lần đường chính phải chuyển sang dự phòng |
| **app.integration.fallback.outcomes** | Khi fallback hoàn tất | success / rejected / failure |
| **app.integration.fallback.age** | Khi trả stale snapshot | Độ cũ của dữ liệu đã verified |
| **app.integration.fallback.rejections** | Policy từ chối cache | expired / invalid / wrong_scope / absent |
| **app.integration.pending.reconciliation** | Số lệnh đang chờ kiểm chứng | Ngăn trạng thái UNKNOWN bị quên |
| **app.integration.deadletter.confirmed** | Sau xác nhận publish phù hợp | Khả năng phục hồi qua DLQ |
| **app.integration.primary.duration** | Timer đường chính | Latency/p95/p99 và timeout |

Đây là **quy ước metric đề xuất cho ứng dụng**, không phải toàn bộ meter mặc định của Spring Boot, Spring Integration hay Resilience4j.

### 13.1. Tag có cardinality thấp

Tag nên là tập giá trị hữu hạn:

~~~text
flow=order-tracking | inventory-check | payment-status
dependency=tracking-service | inventory-service | payment-provider
error_kind=timeout | unavailable | invalid_contract | auth_failure
fallback_type=verified_cache | hide_optional_widget | pending
outcome=success | rejected | failed
~~~

Không dùng **orderId, customerId, paymentId, raw tenantId, token, URL chứa query động** làm metric tag; chúng làm số time series tăng không kiểm soát. Có thể dùng các ID này trong log/trace được bảo vệ để phục vụ đối soát theo chính sách dữ liệu.

### 13.2. Logging và tracing

Một log có cấu trúc không nhạy cảm:

~~~text
flow=order-tracking
dependency=tracking-service
primaryOutcome=timeout
fallbackType=verified_cache
fallbackOutcome=success
freshness=STALE
verifiedAgeSeconds=120
traceId=...
~~~

Đừng log nội dung token/API secret, Authorization header, toàn bộ response body chứa thông tin cá nhân hoặc cache key có raw customer ID nhạy cảm.

Trace:

~~~text
HTTP inbound
  → authenticate + validate request
  → tracking WebClient GET
       → timeout
  → verified-cache lookup
       → valid snapshot age=120s
  → return STALE result
~~~

Trace nên thể hiện cả **nguyên nhân đường chính thất bại** và **bước phục hồi**; một phản hồi HTTP 200 không tự chứng minh upstream đang khỏe.

### 13.3. Cảnh báo cần dựa vào tỷ lệ và thời gian

Đặt cảnh báo khi:

- Tỷ lệ **fallback/requests** tăng liên tục hoặc vượt ngân sách SLO.
- **Tỷ lệ invalid cache entry** tăng, có thể do mismatch schema hoặc lỗi cache data.
- **Cache age** tiến sát ngưỡng tối đa, cho thấy snapshot không còn được cập nhật.
- **Pending reconciliation** tích tụ hoặc oldest pending vượt SLA.
- **Fallback failed** tăng đồng thời primary failure, tức đường dự phòng cũng đang hỏng.
- DLQ tăng hoặc fallback khiến final failure giảm bất thường mà side effect nghiệp vụ không tăng.

Không đặt alert dựa vào việc một counter tích lũy khác 0; dùng tỷ lệ/cửa sổ thời gian và phân biệt counter reset khi ứng dụng restart.

## 14. Kiểm thử fallback theo hợp đồng, không chỉ theo mã HTTP

Test chức năng **đã trả một object** chưa đủ. Cần kiểm tra object đó có thật sự được phép xuất hiện khi source lỗi và có bảo vệ dữ liệu.

### 14.1. Ma trận kiểm thử bắt buộc

| Case | Primary | Snapshot/recovery | Kết quả cần assert |
| --- | --- | --- | --- |
| Thành công bình thường | HTTP 200 JSON hợp lệ | Có/không | Trả LIVE, không đọc fallback vô ích |
| HTTP 503 tạm thời | 503 | Đúng tenant, verified còn hạn | Trả STALE với sourceUpdatedAt/servedAt |
| HTTP 504 và cache thiếu | 504 | Không có | Lỗi upstream được giữ lại, không tạo dữ liệu |
| Timeout transport đã phân loại | Timeout | Cache hợp lệ | Fallback chỉ nếu classifier cho phép |
| HTTP 404 | Not found | Cache cũ tồn tại | Không dùng cache để làm một ID đã bị xóa “sống lại” nếu contract không cho phép |
| HTTP 401/403 | Auth failure | Có cache | Không bypass quyền truy cập nhờ cache |
| HTTP 200 nhưng JSON sai schema | Invalid | Có cache | Trả lỗi contract, không che sự cố dữ liệu |
| Cache của tenant khác | 503 | Wrong tenant | Từ chối cache; không rò rỉ dữ liệu |
| Cache quá hạn | 503 | verifiedAge > maxStale | Không sử dụng |
| Cache có trạng thái không hợp lệ | 503 | Poisoned data | Từ chối và báo metric |
| Event version cũ ghi đè cache | 503 | Cache bị lùi version | Phát hiện/test conditional write |
| Circuit breaker open | Không gọi upstream | Cache hợp lệ | Đúng fallback policy; không tắt cảnh báo upstream |
| Cache lookup lỗi | 503 | Cache timeout | Có deadline và outcome rõ, không chờ vô hạn |
| POST payment timeout | Kết quả chưa rõ | Không có receipt | PENDING/reconcile; không tự retry với ID mới |
| Broker handler lỗi bắt buộc | Throw | Recovery chưa bền vững | Không ACK sai; vẫn còn khả năng redelivery |

### 14.2. Kiểm thử operator timeout của Reactor

Một test độc lập xác minh TimeoutException được tạo khi Mono không phát tín hiệu:

~~~java
@Test
void monoTimeoutIsNotEquivalentToEmptyResult() {
    StepVerifier.withVirtualTime(
            () -> Mono.<TrackingView>never()
                    .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

Test này chứng minh **semantics của Reactor timeout**, không chứng minh chính sách fallback nghiệp vụ. Trong unit test của policy, dùng **Clock.fixed(...)** và các snapshot cụ thể để kiểm tra đúng ngưỡng tuổi; tránh **Thread.sleep** và phụ thuộc đồng hồ thật.

### 14.3. Mock HTTP server để kiểm chứng service thật

Với **MockWebServer/WireMock** hoặc HTTP test server tương đương:

1. Cho upstream trả 200 đúng schema → assert **Freshness.LIVE**.
2. Cho upstream trả 503, cache verified tuổi 2 phút → assert **Freshness.STALE**, timestamp giữ nguyên.
3. Cho upstream trả 503, cache tuổi 6 phút → assert lỗi/UNAVAILABLE thay vì STALE.
4. Cho upstream trả 200 nhưng thiếu trường **sourceUpdatedAt** → assert contract violation, **không fallback**.
5. Cho upstream trả 404/403 → assert không đọc cache như một đường vượt qua chính sách.
6. Trả body chậm để kiểm tra timeout thực ở WebClient/transport và budget cache fallback.
7. Bật concurrency nhiều request cho cùng order → assert cache không bị response cũ ghi đè response mới.

**Không dùng mock chỉ ném TimeoutException rồi kết luận WebClient đã cấu hình đúng connect/read timeout.** Muốn kiểm tra transport, phải dùng chính connector và HTTP server có khả năng điều khiển delay/disconnect.

### 14.4. Kiểm thử transaction, redelivery và idempotency

Với database/broker test (Testcontainers nếu phù hợp), dựng tình huống:

~~~text
Event được broker giao lần 1
  → DB ghi dấu một phần
  → downstream timeout
  → ứng dụng rollback hoặc ghi PENDING bền vững
  → broker redelivery / reconciler chạy
  → cùng eventId không gây side effect trùng
~~~

Kiểm tra **business state** và **ACK/DLQ** thật, không chỉ assert số lần handler được gọi. Một fallback được thiết kế đúng phải chịu được **crash giữa các bước**, không chỉ exception trong một process đang chạy ổn định.

## 15. Quy trình vận hành khi fallback tăng bất thường

Một runbook có thể bắt đầu từ câu hỏi:

~~~mermaid
flowchart TD
    A["Fallback rate tăng"] --> B{"Đường chính đang lỗi?"}
    B -->|"503/timeout"| C["Kiểm tra latency, pool, DNS, broker, rate limit"]
    B -->|"Không"| D["Kiểm tra classifier, schema và chính sách fallback"]
    C --> E{"Snapshot còn an toàn?"}
    E -->|"Có"| F["Phục vụ degraded có nhãn + theo dõi age"]
    E -->|"Không"| G["Từ chối fallback, thông báo UNAVAILABLE"]
    F --> H["Khôi phục upstream, refresh cache và đối soát"]
    G --> H
    D --> I["Sửa data contract / classifier, không nuốt lỗi"]
~~~

Các bước vận hành:

1. Xác định **nguồn lỗi gốc** theo downstream, error_kind và deployment gần nhất.
2. Kiểm tra tỷ lệ fallback **được chấp nhận** và **bị từ chối**, độ tuổi dữ liệu, pending reconciliation.
3. Nếu dữ liệu cache không còn an toàn, **tắt fallback đó bằng chính sách có kiểm soát**; chuyển sang unavailable/PENDING chứ không nới TTL vô hạn.
4. Khôi phục upstream bằng retry có giới hạn, rate limiting và bảo vệ pool; tránh retry storm.
5. Làm mới dữ liệu verified, replay/reconcile các tác vụ pending theo idempotency key.
6. Đối soát dashboard **primary failures, business success, broker ACK, DLQ** thay vì chỉ nhìn HTTP success rate.
7. Sau sự cố, cập nhật rule phân loại lỗi, hợp đồng dữ liệu và test cho những trường hợp chưa được dự đoán.

### Cấu hình chính sách fallback tách khỏi code

~~~yaml
app:
  recovery:
    tracking:
      primary-timeout: 2s
      max-verified-cache-age: 5m
      max-source-age: 24h
      cache-lookup-timeout: 300ms
      allow-stale-informational-view: true
~~~

Các property là **cấu hình ứng dụng đề xuất**, không phải property mặc định của Spring Boot. Bind bằng **@ConfigurationProperties**, validate Duration dương và bật/tắt theo chính sách được phê duyệt. Cần áp **timeout riêng cho cache lookup**: ví dụ service phần 6 nên bổ sung timeout ngân sách fallback theo cấu hình, vì **timeout đặt trước onErrorResume chỉ giới hạn nguồn primary**, không tự giới hạn toàn bộ bước fallback.

**Không dùng feature flag để tắt validation hoặc bypass authorization.** Một flag có thể tắt đường stale lookup và trả unavailable, chứ không được cấp quyền truy cập rộng hơn khi hạ tầng bị lỗi.

## 16. Những sai lầm thường gặp

**“Fallback thành công nghĩa là downstream khỏe.”** Sai. Fallback có thể đang che sự cố dài ngày. Phải đo primary failure và fallback riêng.

**“Trả empty list khi HTTP lỗi luôn an toàn.”** Chỉ đúng nếu hợp đồng coi sự vắng mặt dữ liệu tùy chọn là một kết quả thay thế hợp lệ. Không dùng với đơn hàng, thanh toán, tồn kho hoặc quyền truy cập.

**“404/401/JSON invalid đều giống timeout.”** Không. Chúng biểu diễn không tồn tại, quyền bị từ chối hoặc dữ liệu sai; fallback có thể che sai sót nghiêm trọng.

**“Cache còn tồn tại tức là còn đủ mới.”** Không. TTL lưu trữ khác với max staleness và sourceUpdatedAt.

**“Dữ liệu của tenant khác cũng có thể dùng tạm.”** Tuyệt đối không. Fallback không được bỏ qua ranh giới bảo mật.

**“HTTP 200 + fallback không cần metadata.”** Nếu caller không biết đó là stale, nó có thể đưa ra quyết định sai. Hợp đồng phải thể hiện freshness/provenance.

**“Circuit breaker mở thì mặc định trả success.”** Circuit breaker chỉ hạn chế lời gọi; business policy mới được quyết định fallback.

**“onErrorResume(Exception.class) là cách xử lý lỗi gọn nhất.”** Nó thường che cả lỗi hợp đồng dữ liệu, authorization hoặc bug nội bộ.

**“Timeout POST chứng minh tiền chưa được trừ.”** Không. Kết quả có thể chưa xác định; cần idempotency và reconciliation.

**“Đã có recoveryChannel tức là đã lưu lỗi bền vững.”** Không. Channel trong bộ nhớ và ErrorMessage chưa phải durable queue hoặc DLQ.

**“Catch exception trong @Transactional rồi return sẽ rollback.”** Không nhất thiết. Có thể khiến Spring commit phần dữ liệu đã ghi.

**“Retry ở nhiều tầng càng an toàn.”** Tổng attempts có thể tăng theo cấp số nhân, làm downstream quá tải; cần ngân sách chung.

**“Chỉ cần test HTTP status và exception.”** Phải test dữ liệu stale, tenant scope, version, TTL, side effect, ACK, crash, metric và recovery.

## 17. Checklist trước khi phát hành

1. Phân loại rõ **transient infrastructure**, **business result**, **invalid contract**, **security failure**, **uncertain side effect**.
2. Xác định chức năng nào được **fail-open**, chức năng nào phải **fail-closed/PENDING**; có sự phê duyệt của chủ sở hữu nghiệp vụ.
3. Chỉ cho fallback khi tồn tại một kết quả dự phòng **đúng schema, đúng tenant, đúng version và còn hạn**.
4. Hợp đồng API thể hiện **LIVE/STALE/UNAVAILABLE/UNKNOWN**, thời điểm dữ liệu và khả năng tiếp tục hành động.
5. Không biến thiếu dữ liệu, 404, 401/403 hoặc payload sai thành kết quả nghiệp vụ giả.
6. Dùng retry/breaker/bulkhead/timeout với ngân sách rõ, tránh nhiều tầng cùng retry vô hạn.
7. Với dữ liệu có side effect, giữ idempotency key, transaction/outbox/inbox và quy trình đối soát khi kết quả không rõ.
8. Không ACK message quan trọng nếu fallback chỉ log hoặc gửi qua in-memory channel mà chưa có durable handoff.
9. Kiểm tra lỗi fallback thứ cấp: cache unavailable, hết hạn, sai tenant, dữ liệu bị poisoned và race version.
10. Đặt timeout riêng cho đường fallback; đo latency tổng của request.
11. Thu thập metric **primary failure, fallback accepted/rejected, freshness age, pending count, DLQ**; không dùng ID cá nhân làm label.
12. Test đầy đủ cả kết quả đúng, dữ liệu sai, broker redelivery, transaction rollback, circuit open và lỗi giữa workflow.
13. Có runbook tắt fallback không an toàn, phục hồi nguồn, làm mới snapshot và reconcile những message/công việc pending.

**Kết luận:** fallback tốt không phải là “không bao giờ ném exception”, mà là **giữ được ý nghĩa nghiệp vụ khi đường chính gặp sự cố**. Một fallback chỉ nên hoạt động khi dữ liệu dự phòng đáng tin, hợp đồng công khai mức độ suy giảm, và không che lỗi cần được sửa. Với các luồng tích hợp có side effect hoặc yêu cầu nhất quán mạnh, **từ chối an toàn, giữ trạng thái PENDING và đối soát** thường đúng hơn một giá trị mặc định trông giống thành công.

## Tài liệu tham khảo

- [Spring Framework — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): phân loại status, bodyToMono và xử lý lỗi HTTP.
- [Spring Framework — WebClient exchangeToMono/Flux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): tùy chỉnh xử lý response, lỗi và release body.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): onErrorResume, onErrorReturn, retry và timeout.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel và xử lý lỗi bất đồng bộ.
- [Spring Integration — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): RequestHandlerRetryAdvice, recoverer và retry.
- [Spring Cloud Circuit Breaker — Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/): circuit breaker, Resilience4j và tích hợp Spring.
- [Resilience4j — Getting Started](https://resilience4j.readme.io/docs/getting-started-3): circuit breaker, retry, bulkhead và các decorator.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, tag và quan sát latency/outcome.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): retry, recoverer, DLT và xử lý listener thất bại.
- [Spring AMQP — Message Recovery](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): retry, recoverer, DLQ và cơ chế broker.
