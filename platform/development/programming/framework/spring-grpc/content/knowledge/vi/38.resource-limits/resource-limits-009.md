# Rate limit theo client

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích rate limit theo client và phân biệt nó với giới hạn concurrency, message size và quota tổng.
- Xác định client bằng danh tính đã xác thực thay vì tin metadata do caller tự khai báo.
- Chọn phạm vi quota theo client, method, tenant hoặc nhóm dịch vụ.
- So sánh fixed window, sliding window, token bucket và leaky bucket.
- Triển khai token bucket có khả năng kiểm thử bằng đồng hồ monotonic.
- Áp dụng rate limit ở server interceptor trước khi gọi business handler.
- Giới hạn tốc độ message riêng cho client-streaming và bidirectional streaming.
- Chọn local hoặc distributed limiter khi chạy nhiều replica.
- Trả status phù hợp, hướng dẫn client backoff và quan sát hiệu quả policy.

## 1. Rate limit theo client giải quyết vấn đề gì?

Trong **SPRING_GRPC**, nhiều client có thể gọi cùng một service hoặc method. Một client gửi request quá nhanh có thể chiếm worker, connection pool, database capacity và băng thông, làm giảm chất lượng dịch vụ của những client khác.

**Rate limit theo client** giới hạn tốc độ một client được phép tạo request hoặc gửi message trong một khoảng thời gian. Mục tiêu là bảo vệ năng lực xử lý và chia sẻ tài nguyên công bằng. Khi client vượt ngưỡng, server từ chối sớm trước khi request đi vào business logic.

Rate limit khác các giới hạn tài nguyên khác:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| Rate limit | Tốc độ request/message theo thời gian | 20 RPC/giây/client |
| Concurrency limit | Số RPC đang hoạt động cùng lúc | Tối đa 5 stream/client |
| Message-size limit | Kích thước từng gRPC message | Tối đa 2 MiB/message |
| Message-count limit | Tổng số message trong một stream | Tối đa 1.000 message/stream |
| Byte quota | Tổng dữ liệu trong một khoảng hoặc một phiên | 100 MiB/phút/client |
| Deadline | Thời gian tối đa của một RPC | 2 giây/call |

Rate limit xử lý tốc độ đến; concurrency limit xử lý số công việc đang giữ tài nguyên; message-size và byte quota kiểm soát dung lượng. Một hệ thống thường cần kết hợp các cơ chế này.

Ví dụ, một client có thể gửi 100 RPC mỗi giây nhưng mỗi RPC hoàn tất trong 5 ms; concurrency thấp nhưng rate cao. Client khác mở 2 stream và giữ chúng 10 phút; rate mở stream thấp nhưng concurrency và lifetime cao. Không dùng một limiter duy nhất để thay thế mọi giới hạn.

~~~mermaid
flowchart TD
    A["gRPC call đến server"] --> B["Xác thực client"]
    B --> C["Lấy client identity từ Context"]
    C --> D["Tính quota theo client và method"]
    D --> E{"Còn token?"}
    E -- "Có" --> F["Cho phép gọi handler"]
    E -- "Không" --> G["RESOURCE_EXHAUSTED"]
    F --> H["Business logic và downstream"]
~~~

## 2. Định danh client một cách đáng tin cậy

Rate limit chỉ công bằng nếu server biết request thuộc về client nào. Không nên dùng trực tiếp một header tùy ý như x-client-id làm khóa quota, vì caller có thể tự đổi giá trị để nhận bucket mới hoặc giả mạo client khác.

Nguồn định danh nên đến từ authentication đã hoàn tất, ví dụ:

- Client ID trong access token đã được xác minh chữ ký và issuer.
- Service account hoặc workload identity được xác thực.
- API key đã được tra cứu và ánh xạ sang client record nội bộ.
- Certificate identity từ mTLS, sau khi kiểm tra trust chain và mapping.

Authentication interceptor xác minh credential rồi ghi principal vào grpc Context. Rate-limit interceptor đọc principal đó. Nếu không có identity đã xác thực, request phải bị authentication layer từ chối; không tạo bucket cho giá trị mặc định như anonymous hoặc unknown rồi vô tình cho mọi caller dùng chung quota.

Ví dụ một context key dùng chung:

~~~java
import io.grpc.Context;

public final class ClientIdentityContext {

    public static final Context.Key<String> CLIENT_ID =
            Context.key("authenticated-client-id");

    private ClientIdentityContext() {
    }
}
~~~

Authentication interceptor đặt giá trị sau khi xác minh credential:

~~~java
Context context = Context.current().withValue(
        ClientIdentityContext.CLIENT_ID,
        authenticatedClient.internalId());

return Contexts.interceptCall(
        context, call, headers, next);
~~~

Chỉ ghi internal client ID ổn định đã được xác thực. Không đưa raw bearer token, API key, certificate bytes hoặc thông tin cá nhân vào limiter key, log hay metric label.

Nếu một credential đại diện cho nhiều tenant, contract phải xác định quota tính theo client, tenant hay cặp client-tenant. Không cho caller tự chọn tenant key trước khi kiểm tra membership.

## 3. Chọn phạm vi quota

Một rate limit policy cần xác định rõ bucket key. Các lựa chọn thường gặp:

- **Per client:** mọi method của một client dùng chung ngân sách.
- **Per client + method:** một client có quota riêng cho từng RPC method.
- **Per tenant:** các client trong tenant chia sẻ quota.
- **Per client + method + tenant:** quota chi tiết cho một client trong một tenant và một method.
- **Per service class/tier:** quota khác nhau cho free, standard hoặc premium clients.

Ví dụ một hệ thống có thể đặt 100 RPC/giây/client tổng thể, nhưng method GenerateReport chỉ cho 2 call/giây/client vì method này tiêu thụ CPU và database nhiều hơn. Một method GetStatus nhẹ có thể có quota cao hơn.

Cần tránh tạo bucket key với cardinality vô hạn từ input không đáng tin. Chỉ dùng client/tenant identity đã xác minh và method name lấy từ gRPC descriptor. Giới hạn số bucket lưu trong memory và đặt eviction policy.

Nếu một client có nhiều API key, quyết định quota gắn với từng key hay với client sở hữu các key đó. Quota theo client thường tránh việc một tổ chức vượt hạn mức bằng cách tạo nhiều credential.

## 4. Chọn thuật toán rate limiting

Các thuật toán phổ biến có semantics khác nhau:

| Thuật toán | Cách hoạt động | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Fixed window | Đếm request trong từng cửa sổ thời gian cố định | Đơn giản, ít state | Burst ở ranh giới hai cửa sổ có thể gần gấp đôi |
| Sliding window log | Lưu thời điểm từng request trong cửa sổ trượt | Chính xác | Tốn memory theo số request |
| Sliding window counter | Ước lượng cửa sổ trượt từ hai bucket | Nhẹ hơn log | Là phép xấp xỉ |
| Token bucket | Token được nạp đều; mỗi request tiêu thụ token | Cho phép burst có giới hạn và kiểm soát tốc độ dài hạn | Cần lưu state cho từng bucket |
| Leaky bucket | Đưa request vào hàng đợi và xử lý theo tốc độ cố định | Làm phẳng tốc độ xử lý | Có thể tăng queue latency; cần queue hữu hạn |

Token bucket thường phù hợp cho gRPC API vì cho phép burst ngắn trong capacity xác định nhưng giới hạn tốc độ trung bình. Ví dụ bucket capacity 40 token, refill 20 token/giây: client có thể gửi burst tối đa 40 request khi bucket đầy, sau đó tốc độ ổn định tối đa khoảng 20 request/giây.

Không nhầm capacity với refill rate. Capacity quyết định burst tối đa; refill rate quyết định tốc độ duy trì trong dài hạn.

## 5. Token bucket hoạt động thế nào?

Token bucket có ba thành phần:

- **Capacity:** số token tối đa trong bucket.
- **Refill rate:** số token được thêm vào mỗi giây.
- **Cost:** số token một operation tiêu thụ.

Khi request đến, limiter tính token đã được nạp từ thời điểm cập nhật trước. Nếu đủ token, trừ cost và cho phép request. Nếu không đủ, từ chối và có thể tính thời gian ước lượng đến khi đủ token.

Công thức khái niệm:

\[
T_{\text{new}} =
\min(C,\ T_{\text{old}} + \Delta t \times R)
\]

Trong đó C là capacity, R là token/giây và Δt là thời gian trôi qua theo đồng hồ monotonic.

Dùng đồng hồ monotonic như System.nanoTime(), không dùng wall clock như Instant.now() để đo elapsed time. Đồng hồ hệ thống có thể bị điều chỉnh bởi NTP hoặc thao tác quản trị; monotonic clock phù hợp hơn để tính khoảng thời gian.

## 6. Triển khai token bucket đơn giản trong Java

Ví dụ dưới đây dùng synchronized để làm thao tác refill và consume nguyên tử cho một bucket. Ticker được inject để unit test có thể điều khiển thời gian mà không cần chờ thực:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

public final class TokenBucket {

    private final double capacity;
    private final double tokensPerNano;
    private final LongSupplier ticker;

    private double tokens;
    private long lastRefillNanos;

    public TokenBucket(
            long capacity,
            double tokensPerSecond,
            LongSupplier ticker) {

        if (capacity <= 0 || tokensPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "capacity and refill rate must be positive");
        }

        this.capacity = capacity;
        this.tokensPerNano =
                tokensPerSecond / TimeUnit.SECONDS.toNanos(1);
        this.ticker = ticker;
        this.tokens = capacity;
        this.lastRefillNanos = ticker.getAsLong();
    }

    public synchronized boolean tryConsume(long cost) {
        if (cost <= 0 || cost > capacity) {
            return false;
        }

        refill();

        if (tokens < cost) {
            return false;
        }

        tokens -= cost;
        return true;
    }

    private void refill() {
        long now = ticker.getAsLong();
        long elapsed = now - lastRefillNanos;

        if (elapsed > 0) {
            tokens = Math.min(
                    capacity,
                    tokens + elapsed * tokensPerNano);
            lastRefillNanos = now;
        }
    }

    public synchronized double availableTokens() {
        refill();
        return tokens;
    }
}
~~~

Khởi tạo bucket cho 20 request/giây với burst tối đa 40:

~~~java
TokenBucket bucket = new TokenBucket(
        40,
        20.0,
        System::nanoTime);
~~~

Đây là implementation minh họa cho một bucket trong một process. synchronized giúp state của bucket nhất quán khi nhiều thread cùng consume. Khi có rất nhiều client, cần registry quản lý bucket theo identity và eviction; không tạo object bucket mới cho mỗi RPC.

Với quota cần độ chính xác cao hoặc nhiều replica, nên dùng thư viện limiter đã được kiểm chứng hoặc distributed limiter có thao tác atomic. Không tự xây distributed algorithm chỉ bằng cách đọc rồi ghi counter qua nhiều lệnh network.

## 7. Registry bucket theo client và method

Một registry có thể dùng khóa gồm internal client ID và full method name:

~~~java
public record RateLimitKey(
        String clientId,
        String fullMethodName) {
}

public interface ClientRateLimiter {

    boolean tryAcquire(
            String clientId,
            String fullMethodName,
            long cost);
}
~~~

Implementation tạo bucket theo policy:

~~~java
public final class LocalClientRateLimiter
        implements ClientRateLimiter {

    private final ConcurrentMap<RateLimitKey, TokenBucket> buckets =
            new ConcurrentHashMap<>();

    private final RateLimitPolicy policy;

    public LocalClientRateLimiter(RateLimitPolicy policy) {
        this.policy = policy;
    }

    @Override
    public boolean tryAcquire(
            String clientId,
            String fullMethodName,
            long cost) {

        RateLimitKey key =
                new RateLimitKey(clientId, fullMethodName);

        RateLimitRule rule = policy.ruleFor(fullMethodName);
        TokenBucket bucket = buckets.computeIfAbsent(
                key,
                ignored -> new TokenBucket(
                        rule.capacity(),
                        rule.refillPerSecond(),
                        System::nanoTime));

        return bucket.tryConsume(cost);
    }
}
~~~

Đây là skeleton: registry production phải có eviction, maximum bucket count và xử lý policy update. Nếu client ID có thể thay đổi hoặc có nhiều triệu client, map không giới hạn sẽ trở thành memory leak. Có thể dùng cache có maximumSize và expireAfterAccess; khi bucket bị evict, lần sau nó được tạo mới với bucket đầy, vì vậy eviction policy phải được đánh giá về fairness và khả năng lách quota.

Nếu policy thay đổi, xác định bucket hiện tại được giữ rule cũ tới khi hết hạn hay được cập nhật ngay. Không để một lần deploy rule mới vô tình reset mọi bucket và tạo burst đồng loạt nếu điều đó vượt downstream capacity.

## 8. Áp dụng rate limit trong ServerInterceptor

Server interceptor là ranh giới phù hợp để giới hạn số RPC mới trước khi gọi service handler. Authentication phải chạy trước và đưa client identity đã xác thực vào Context.

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ClientRateLimitInterceptor
        implements ServerInterceptor {

    private final ClientRateLimiter rateLimiter;

    public ClientRateLimitInterceptor(
            ClientRateLimiter rateLimiter) {
        this.rateLimiter = rateLimiter;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String clientId = ClientIdentityContext.CLIENT_ID.get();

        if (clientId == null || clientId.isBlank()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authenticated client identity is required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        String method =
                call.getMethodDescriptor().getFullMethodName();

        if (!rateLimiter.tryAcquire(clientId, method, 1)) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Client rate limit exceeded"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

Khi quota hết, interceptor đóng call bằng RESOURCE_EXHAUSTED trước khi handler chạy. Đây là lỗi quota/capacity, không phải lỗi xác thực hoặc phân quyền.

Đảm bảo authentication interceptor được thực thi trước rate-limit interceptor. Thứ tự đăng ký và cách compose interceptor có thể khác theo grpc-java builder hoặc Spring gRPC starter; hãy xác minh bằng integration test rằng Context đã có principal khi limiter chạy và handler không bị gọi khi request bị từ chối.

Không dùng metadata x-client-id trực tiếp làm clientId. Metadata chỉ là đầu vào do caller gửi; identity phải được xác minh trước. Nếu identity thiếu, fail closed thay vì cho mọi caller dùng chung một bucket.

## 9. Rate limit theo RPC khác rate limit message trong streaming

ServerInterceptor interceptCall chạy một lần cho mỗi RPC. Với client-streaming hoặc bidirectional streaming, nó giới hạn tốc độ mở RPC mới, không tự động giới hạn số message gửi trong một stream đã mở.

Nếu cần giới hạn tốc độ message inbound, wrap ServerCall.Listener và consume token trong onMessage:

~~~java
ServerCall.Listener<ReqT> delegate =
        next.startCall(call, headers);

return new ForwardingServerCallListener
        .SimpleForwardingServerCallListener<ReqT>(delegate) {

    @Override
    public void onMessage(ReqT message) {
        if (!messageRateLimiter.tryAcquire(
                clientId, method, 1)) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Message rate limit exceeded"),
                    new Metadata());
            return;
        }

        super.onMessage(message);
    }
};
~~~

Đây là skeleton; implementation thực tế cần terminal guard và cleanup subscription/worker khi stream bị đóng. Không tiếp tục chuyển message vào delegate sau khi đã kết thúc call. Với outbound streaming, áp dụng limiter trước khi phát mỗi response hoặc điều tiết producer bằng flow control.

Có thể định nghĩa ba policy độc lập:

- RPC start rate: số call mới mỗi giây/client.
- Inbound message rate: số request message mỗi giây/client/method.
- Outbound message rate: số response message mỗi giây/client/method.

Không dùng một token bucket cho cả ba chiều nếu contract cần ngân sách riêng. Một client có thể mở ít stream nhưng gửi message rất nhanh; một client khác có thể mở nhiều stream rỗng. Mỗi kiểu tải cần limiter phù hợp.

## 10. Đăng ký policy trong Spring gRPC

Trong ứng dụng Spring, cấu hình policy và limiter thành bean dùng chung:

~~~java
@Configuration
public class GrpcRateLimitConfiguration {

    @Bean
    RateLimitPolicy rateLimitPolicy() {
        return RateLimitPolicy.defaults();
    }

    @Bean
    ClientRateLimiter clientRateLimiter(
            RateLimitPolicy policy) {
        return new LocalClientRateLimiter(policy);
    }

    @Bean
    ClientRateLimitInterceptor clientRateLimitInterceptor(
            ClientRateLimiter limiter) {
        return new ClientRateLimitInterceptor(limiter);
    }
}
~~~

Đăng ký interceptor qua server builder customizer/configurer hoặc extension point của Spring gRPC starter đang sử dụng. Không giả định mọi starter có cùng cách khai báo bean hoặc property. Kiểm tra tài liệu/API của đúng phiên bản trong dự án và viết application integration test để xác minh interceptor thực sự nằm trong server chain.

Nếu có nhiều service, có thể dùng policy theo full method name để đặt quota riêng. Với method nhạy cảm, có thể kết hợp client rate limit và concurrency limit. Không tạo limiter bean riêng cho từng request; limiter registry cần sống cùng application context và có lifecycle rõ ràng.

## 11. Local limiter và distributed limiter

Local token bucket nằm trong memory của một instance. Khi chạy nhiều replica, mỗi instance có bucket riêng. Nếu quota là 20 request/giây/client và có 4 replica, client có thể đạt gần 80 request/giây nếu traffic phân phối đều và mỗi replica cấp đủ token.

Có ba mô hình:

| Mô hình | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Per-instance local limit | Mỗi replica tự giới hạn | Bảo vệ từng instance; quota tổng có thể nhân theo replica |
| Sticky routing | Client thường quay về một replica | Giảm phân tán bucket nhưng không bảo đảm khi rebalance/failover |
| Distributed shared limiter | Nhiều replica cùng tiêu thụ một quota atomic | Cần quota toàn client/tenant trên cluster |

Distributed limiter có thể dùng Redis script, database atomic counter hoặc rate-limit service chuyên dụng. Thao tác consume/refill cần atomic để hai replica không cùng đọc một token cuối rồi đều cho phép request.

Cần quyết định behavior khi limiter store lỗi:

- **Fail closed:** từ chối request khi không thể xác minh quota; bảo vệ downstream nhưng giảm availability.
- **Fail open:** cho phép request khi limiter unavailable; tăng availability nhưng có thể vượt quota.
- **Local fallback:** áp dụng quota bảo thủ tại từng instance khi shared store lỗi; giảm rủi ro nhưng semantics không còn là quota cluster chính xác.

Chọn theo mức độ quan trọng của downstream và công bố trong vận hành. Không để một Redis outage làm tất cả RPC treo vô thời hạn; limiter lookup cũng cần timeout hữu hạn.

## 12. Xử lý client khi bị rate limit

Khi vượt quota, server trả **RESOURCE_EXHAUSTED**. Client nên giảm tốc độ và retry theo policy, không gửi lại ngay lập tức.

Các nguyên tắc:

- Exponential backoff kèm jitter.
- Tôn trọng retry delay nếu server cung cấp metadata/status detail theo contract.
- Không retry lỗi validation, authentication hoặc authorization.
- Retry chỉ với operation an toàn hoặc có idempotency key.
- Không tạo retry storm khi nhiều client cùng bị giới hạn.
- Giữ deadline tổng của operation; retry không được reset budget vô hạn.

gRPC có thể mang rich status details như google.rpc.RetryInfo nếu hệ thống dùng protobuf error details phù hợp. Nếu chưa có contract đó, client có thể dùng backoff mặc định có giới hạn. Không parse description tự do như "try again in 3 seconds" để điều khiển retry.

Nếu client-streaming đã gửi một phần dữ liệu trước khi bị rate limit, reconnect từ đầu có thể tạo side effect trùng. Dùng sequence, acknowledgement, idempotency key và resume cursor để tiếp tục an toàn.

## 13. Bucket key, eviction và bảo vệ memory

Mỗi client/method có thể tạo một bucket state. Nếu số client lớn hoặc client identity không được kiểm soát, registry có thể tăng không giới hạn.

Cần:

- Chỉ tạo bucket sau authentication.
- Giới hạn maximum bucket count.
- Expire bucket không hoạt động sau một khoảng thời gian.
- Dùng internal ID có kích thước giới hạn.
- Không đưa raw token hoặc metadata tùy ý vào key.
- Theo dõi eviction và bucket creation rate.
- Đặt quota riêng cho tenant lớn nếu policy yêu cầu.

Eviction có hệ quả về quota: bucket bị xóa rồi tạo lại có thể bắt đầu với capacity đầy. Với client thường xuyên hoạt động, expire-after-access có thể phù hợp; nhưng eviction dưới áp lực memory có thể cho phép caller lách quota. Nếu quota có ý nghĩa billing/security nghiêm ngặt, dùng shared persistent/distributed state thay vì cache dễ eviction.

Không giữ object principal, credential hoặc request payload trong bucket. Chỉ lưu state tối thiểu: token count, timestamp, rule reference và các metric cần thiết.

## 14. Quan sát và vận hành rate limit

Theo dõi theo method và client tier, tránh metric cardinality vô hạn:

- Request allowed và rejected.
- Rate limit rejection theo method/status.
- Token bucket available token hoặc bucket saturation theo bucket group.
- Client identity count và active bucket count.
- Bucket creation/eviction rate.
- Retry và backoff rate ở client.
- Latency của distributed limiter store.
- Limiter store timeout/error và fail-open/fail-closed decision.
- Downstream CPU, DB pool, queue depth và latency trước/sau khi bật policy.

Không dùng raw client ID, API key hoặc tenant ID tùy ý làm metric label nếu cardinality lớn. Có thể dùng client tier, method và rejection reason; log/trace dùng identifier đã pseudonymize hoặc redacted khi cần điều tra.

Rate limit tốt phải làm giảm quá tải downstream mà không tạo tỷ lệ reject quá cao cho client hợp lệ. Theo dõi phân phối request theo client tier và method; nếu một client liên tục chạm limit, xem lại contract, burst capacity và hành vi retry trước khi tăng quota.

## 15. Kiểm thử rate limit

Dùng ticker giả hoặc clock controllable để kiểm thử token bucket mà không phải chờ thời gian thực.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Bucket mới, request trong capacity | Được phép |
| Gửi đúng capacity request liên tiếp | Được phép đến khi hết token |
| Request tiếp theo khi không có token | Bị từ chối |
| Thời gian trôi qua và token refill | Request được phép lại theo refill rate |
| Hai client identity khác nhau | Bucket độc lập |
| Cùng client, hai method khác nhau | Quota tách biệt nếu policy per-method |
| Client chưa xác thực | Bị auth layer từ chối; không tạo bucket |
| Request bị limiter từ chối | Handler không chạy |
| Streaming mở một RPC rồi gửi nhiều message | RPC-start limit chỉ tính một call; message limiter tính từng message |
| Nhiều replica dùng shared limiter | Tổng quota được chia sẻ atomic |
| Limiter store unavailable | Fail-open/closed/fallback theo policy |
| Bucket eviction | Không tạo đường lách quota ngoài dự kiến |

Test interceptor bằng in-process gRPC hoặc transport integration test. Dùng raw generated stub để chứng minh caller không đi qua client SDK chính thức vẫn bị server giới hạn. Test thứ tự authentication và rate-limit interceptor để principal đã có trong Context trước khi limiter đọc.

Với distributed limiter, test concurrency nhiều client/replica cùng consume token cuối để bảo đảm không vượt capacity do race. Với streaming, test message N+1 theo tốc độ và xác minh không có message sau terminal state được xử lý.

## 16. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng x-client-id làm bucket key trực tiếp | Caller tự đổi ID để lấy quota mới | Dùng authenticated principal |
| Chỉ giới hạn tổng toàn hệ thống | Một client có thể chiếm quota của client khác | Thêm per-client bucket |
| Dùng fixed window mà không xét boundary burst | Request dồn ở ranh giới cửa sổ | Token bucket hoặc sliding window |
| Chỉ giới hạn RPC start | Một streaming RPC gửi message không giới hạn | Thêm inbound/outbound message rate |
| Local limiter nhưng kỳ vọng quota cluster | Tổng quota nhân theo số replica | Dùng distributed limiter hoặc xác định per-instance quota |
| Bucket map không eviction | Memory tăng theo số client | Maximum size và expiry có kiểm soát |
| Limiter chạy trước authentication | Không có identity đáng tin | Đặt auth trước rate-limit và test chain |
| Dùng UNAVAILABLE cho mọi rejection | Client retry sai semantics | Dùng RESOURCE_EXHAUSTED cho quota |
| Retry ngay khi bị từ chối | Retry storm và quá tải lớn hơn | Backoff, jitter và deadline |
| Không xử lý shared store timeout | RPC bị treo khi Redis chậm | Timeout limiter lookup và failure policy |

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo authentication interceptor ghi internal client ID đã xác thực vào grpc Context.
2. Viết TokenBucket dùng System.nanoTime và ticker có thể thay thế trong unit test.
3. Tạo registry bucket theo client ID và full method name, có maximum size và eviction policy.
4. Viết ServerInterceptor từ chối RPC vượt quota bằng RESOURCE_EXHAUSTED trước khi handler chạy.
5. Với client-streaming, thêm inbound message limiter trong onMessage; với server-streaming, giới hạn response trước khi phát.
6. Đăng ký limiter qua Spring gRPC configuration và xác minh thứ tự interceptor.
7. Chạy thử local limiter trên nhiều replica để quan sát quota bị nhân; sau đó đánh giá distributed limiter.
8. Viết test cho capacity, refill, client isolation, method isolation, unauthenticated request, streaming message rate, eviction và store failure.

### Câu hỏi tự kiểm tra

**1. Rate limit theo client giới hạn điều gì?**  
Tốc độ client được phép tạo RPC hoặc gửi message trong một khoảng thời gian.

**2. Vì sao không dùng header x-client-id trực tiếp?**  
Caller có thể giả mạo hoặc đổi giá trị; limiter phải dùng principal đã xác thực.

**3. Token bucket capacity và refill rate khác nhau thế nào?**  
Capacity giới hạn burst tối đa; refill rate quyết định tốc độ token được nạp lại dài hạn.

**4. ServerInterceptor có giới hạn tốc độ message trong streaming RPC không?**  
Không tự động. Interceptor giới hạn RPC start; muốn giới hạn message phải kiểm tra từng onMessage hoặc từng outbound response.

**5. Vì sao local limiter không bảo đảm quota toàn cluster?**  
Mỗi replica có bucket riêng nên tổng token có thể nhân theo số replica.

**6. Status nào phù hợp khi client vượt rate limit?**  
RESOURCE_EXHAUSTED.

**7. Vì sao bucket registry cần eviction?**  
Để memory không tăng theo số client/method vô hạn; eviction phải được đánh giá vì bucket tạo lại có thể được cấp burst mới.

**8. Client nên retry thế nào sau RESOURCE_EXHAUSTED?**  
Dùng exponential backoff, jitter, tôn trọng retry delay và giữ idempotency/resume semantics.

## Tổng kết

Rate limit theo client bảo vệ gRPC service trước caller gửi request hoặc message nhanh hơn năng lực xử lý. Xác định client từ principal đã xác thực, chọn bucket scope theo client/method/tenant và dùng thuật toán có semantics rõ như token bucket. Server interceptor giới hạn RPC start; streaming cần limiter riêng cho inbound/outbound message. Local bucket bảo vệ từng replica, còn quota toàn cluster cần shared atomic limiter. Khi vượt ngưỡng, trả RESOURCE_EXHAUSTED, client backoff có jitter và giữ deadline/idempotency. Giới hạn bucket registry, quan sát rejection và kiểm thử race, eviction, streaming cùng Spring interceptor wiring để policy có hiệu lực trong production.

