# Lưu đệm kết quả chỉ đọc theo dữ liệu, danh tính và thời hạn

Một công cụ Spring AI có thể được mô hình gọi nhiều lần để đọc cùng một đơn hàng, thông tin sản phẩm hoặc quy định nghiệp vụ. Mỗi lần gọi lại có thể tốn một truy vấn database, một HTTP request, thời gian chờ dịch vụ ngoài và chi phí vận hành. Lưu đệm (caching) có thể giảm chi phí này, nhưng nếu dùng một khóa cache quá đơn giản như orderId, kết quả của tenant này có thể bị trả cho tenant khác; nếu không giới hạn thời hạn, mô hình có thể dựa trên dữ liệu cũ để tư vấn hoặc quyết định sai.

Nguyên tắc trung tâm của bài:

> **Chỉ lưu đệm kết quả thực sự chỉ đọc; khóa phải thể hiện đủ dữ liệu và phạm vi danh tính quyết định kết quả; cache có TTL và cơ chế vô hiệu hóa phù hợp; authorization vẫn được kiểm tra khi có cache hit.**

Bài này nằm trong chương *Hiệu năng và chi phí* của Spring AI Tool Calling. Ví dụ sử dụng Spring AI 2.1.0 cùng Spring Cache, Caffeine và Spring Data Redis. Mục tiêu không phải lưu mọi câu trả lời của mô hình mà là tối ưu các lời gọi @Tool / ToolCallback truy xuất dữ liệu nghiệp vụ, đồng thời giữ quyền truy cập và tính mới của dữ liệu.

## 1. Cache đặt ở đâu trong một vòng tool calling?

Khi dùng ChatClient với ToolCallingAdvisor, mô hình đưa ra tool name và JSON arguments. Spring AI tìm ToolCallback, thực thi code ứng dụng rồi đưa kết quả công cụ vào lịch sử để mô hình tạo câu trả lời tiếp. ToolContext mang dữ liệu nội bộ như tenant, actor, request scope mà không gửi các giá trị đó cho mô hình.

Một vị trí cache thuận lợi là **service đọc** nằm sau bước kiểm tra quyền và trước một truy vấn đắt tiền:

~~~mermaid
flowchart TD
    A[User request] --> B[ChatClient + ToolCallingAdvisor]
    B --> C[Model chọn read-only tool]
    C --> D[ToolCallback + JSON arguments]
    E[ToolContext tenant / actor] --> D
    D --> F[Validate input + kiểm tra quyền hiện tại]
    F --> G[Cache key: dữ liệu + danh tính + biến thể]
    G --> H{Cache hit và còn hợp lệ?}
    H -- Có --> I[Snapshot chỉ đọc]
    H -- Không --> J[Authorized read service / API]
    J --> K[Đóng gói snapshot + cache theo TTL]
    K --> I
    I --> L[Tool result]
    L --> M[Model tạo câu trả lời]
~~~

Việc cache trả một OrderSnapshot không có nghĩa mô hình ngừng sinh token. Tool result vẫn được truyền lại cho model theo vòng điều phối thông thường; lợi ích trực tiếp là giảm latency, request xuống downstream, giới hạn API hoặc chi phí truy cập dữ liệu. Chỉ khi đồng thời làm ngắn tool result, giảm số tool call hoặc thay đổi chiến lược prompt thì token model mới có thể giảm.

### Phân biệt các lớp cache

| Lớp | Giá trị được cache | Ưu điểm | Điểm cần bảo vệ |
|---|---|---|---|
| Service-read cache | DTO/snapshot từ database hoặc API | Dễ định nghĩa key, authorization, TTL, invalidation | Phải gọi qua Spring proxy và kiểm tra quyền trước cache lookup |
| ToolCallback-result cache | Chuỗi String đã serialize từ tool | Có thể tái sử dụng formatter hoặc kết quả tool nhiều lần | Khó kiểm soát context, version và kết quả nhạy cảm nếu key quá sơ sài |
| HTTP/client cache | Response từ downstream có ETag/Cache-Control | Tận dụng khả năng cache của nguồn dữ liệu | Vẫn phải tuân thủ tenant, credential, Vary và quyền truy cập |
| Model response cache | Câu trả lời tự nhiên của mô hình | Có thể tránh model call trong bài toán rất ổn định | Khó bảo đảm prompt/context, tính mới và quyền; không thay thế tool data cache |
| Conversation memory | Lịch sử hội thoại | Giữ ngữ cảnh cho model | Không phải nguồn sự thật mới nhất và không có semantics TTL nghiệp vụ mặc định |

Trong phần còn lại, ta chủ yếu cache DTO chỉ đọc ở application service. Cách này giúp định nghĩa ranh giới quyền và dữ liệu độc lập với việc model dùng call() hay stream().

## 2. Chọn công cụ nào được cache?

Không phải method dùng tên get là chỉ đọc; cũng không phải mọi truy vấn đọc đều có thể chấp nhận dữ liệu cũ. Hãy phân loại tác động thật của tool và yêu cầu freshness của nghiệp vụ.

| Ví dụ tool | Cache? | Lý do |
|---|---|---|
| getProductCategory | Thường có | Dữ liệu ít đổi, ít nhạy cảm |
| getOrderStatus | Có điều kiện | Phải phân tách tenant/actor và giới hạn độ trễ trạng thái |
| getPublicExchangeRate | Có điều kiện | TTL phụ thuộc nguồn báo giá và thời điểm thị trường |
| getInventoryAvailability | Rất ngắn hoặc không | Tồn kho thay đổi nhanh; không dùng snapshot cũ để xác nhận giữ hàng |
| getMyAccountBalance | Thường không hoặc TTL cực ngắn | Dữ liệu tài chính nhạy cảm, yêu cầu nhất quán cao |
| listMyRecentOrders | Có điều kiện | Kết quả cá nhân hóa, phân trang/sort/filters phải là một phần key |
| getRefundEligibility | Cần cân nhắc | Điều kiện thay đổi; phải revalidate khi thực sự thực hiện refund |
| reserveInventory | Không | Có side effect |
| capturePayment | Không | Ghi dữ liệu; cần idempotency chứ không phải read cache |
| sendEmail | Không | Gửi lại hay bỏ qua lệnh không thể quyết định bằng response cache |

Đừng cache command có side effect để tránh chạy hai lần. Với command, hãy sử dụng **idempotency key + operation ledger** để biết lần chạy trước đã commit chưa. Một cached String "đã thành công" không bảo đảm thao tác hiện tại được phép, đã được commit hoặc có cùng business operation.

### Điều kiện tối thiểu để cache một kết quả

1. Tool không tạo side effect hoặc chỉ thực hiện truy vấn được định nghĩa là read-only.
2. Giá trị trả về có thể xác định bằng dữ liệu đầu vào, principal/quyền, thời điểm và phiên bản dữ liệu.
3. Nghiệp vụ có mức độ chấp nhận dữ liệu cũ rõ ràng.
4. Có chiến lược làm mới hoặc vô hiệu hóa khi dữ liệu và quyền thay đổi.
5. Có bộ nhớ/serializer phù hợp để không lưu object sống như JPA Entity hay credential.
6. Có test chứng minh không trả chéo tenant, actor hoặc mức quyền.

## 3. Khóa cache phải phản ánh dữ liệu, danh tính và biến thể

Khóa cache không chỉ là arguments do mô hình tạo. Giả sử model gọi getOrderStatus với orderId ORD-100. Hai người dùng có thể cùng gửi orderId này nhưng không được thấy cùng dữ liệu.

Một mô hình key có thể là:

~~~text
CacheKey =
  namespace + contractVersion
  + tenantId
  + principalScope / actorId / visibilityProfile
  + canonicalBusinessArguments
  + locale / currency / timeZone / filters / pagination
  + optionalDataVersion
~~~

Tùy nghiệp vụ, có những field không cần. Nhưng **mọi field có thể khiến kết quả khác nhau đều phải hiện diện trong key hoặc được kiểm soát bằng cơ chế tương đương**.

| Thành phần key | Vì sao quan trọng | Ví dụ |
|---|---|---|
| Tool/service namespace | Tránh trùng tên giữa các tool hoặc MCP server | orders:v2:status |
| Tenant ID | Cô lập dữ liệu đa tenant | tenant-acme |
| Actor hoặc permission projection | Kết quả có thể khác theo quyền hoặc danh tính | actor-42 hoặc visibility scope đã xác minh |
| Business arguments | Xác định resource và truy vấn | orderId=ORD-100 |
| Query variant | Filter, page size, sort, currency, locale, timezone | locale=vi-VN |
| Data/policy version | Chặn dùng kết quả cũ sau cập nhật | orderVersion=17 |
| Schema/contract version | Tránh trả DTO cũ sau khi đổi format | snapshot:v3 |

Ví dụ key **không an toàn**:

~~~java
@Cacheable(cacheNames = "orderSnapshots", key = "#orderId")
public OrderSnapshot find(String orderId, String tenantId, String actorId) {
    // tenantId/actorId bị bỏ khỏi khóa cache!
}
~~~

Ngay cả khi method bên trong có kiểm tra quyền, cache hit ở proxy sẽ bỏ qua việc chạy method. Nếu cùng orderId nhưng người khác gọi, Spring có thể trả dữ liệu của người đầu tiên mà không thực thi đoạn kiểm tra quyền trong method.

### Hai cách hợp lệ để phân tách danh tính

- **Phân vùng theo actor:** đưa actorId vào key khi DTO chứa dữ liệu cá nhân hóa hoặc quyền có thể khác nhau. Chi phí là số cache entries tăng theo lượng người dùng.
- **Phân vùng theo tập quyền/visibility ổn định:** chỉ dùng khi đã chứng minh mọi actor trong cùng scope nhận đúng cùng một projection và có cách vô hiệu hóa khi quyền đổi. Ví dụ tenant + orderId + publicSummaryScope; vẫn phải kiểm tra authorization cho từng request.

Không dùng role string như ADMIN hoặc USER làm bảo đảm quyền đầy đủ. Hai user cùng role vẫn có thể có quyền sở hữu resource khác nhau. Nếu kết quả phụ thuộc user cụ thể, hãy cache theo actor hoặc tách dữ liệu dùng chung khỏi phần cá nhân hóa.

### Không đưa secret và dữ liệu không ổn định vào key

Không đặt access token, cookie, raw JWT, password hoặc API key trong cache key. Redis key, logs và metrics có thể hiển thị key. Dùng identifier nội bộ đã chuẩn hóa hoặc HMAC/opaque key khi key chứa thông tin nhạy cảm; không dùng hash không khóa để che thông tin có không gian đoán nhỏ.

Các object Map có iteration order khác nhau, JSON với key order khác nhau hoặc timestamp được tạo ngẫu nhiên khiến cùng truy vấn thành nhiều key. Chuẩn hóa đối số trước khi sinh key, nhưng đừng normalize theo cách làm mất ý nghĩa:

- Trim/chuẩn hóa case của mã nếu domain thực sự không phân biệt case.
- Sort tập filter **chỉ khi** thứ tự không ảnh hưởng kết quả.
- Đưa timezone vào key nếu logic ngày làm việc hay hiển thị phụ thuộc timezone.
- Đưa sort order, page number, cursor vào key nếu list result thay đổi theo chúng.
- Không đưa runId, trace ID hay timestamp hiện tại vào key nếu chúng không đổi dữ liệu; điều đó phá hit rate.

## 4. ToolContext là nguồn dữ liệu thực thi, không phải JSON model

ToolContext của Spring AI cho phép ứng dụng gửi tenant, user và request scope trực tiếp tới tool callback. Những dữ liệu này không được gửi cho model cùng tool definitions. Model chỉ tạo arguments nghiệp vụ, ví dụ orderId.

~~~java
String answer = chatClient.prompt()
        .user(userQuestion)
        .tools(orderTools)
        .toolContext(Map.of(
                "tenantId", authenticatedPrincipal.tenantId(),
                "actorId", authenticatedPrincipal.userId(),
                "locale", "vi-VN"
        ))
        .call()
        .content();
~~~

Không lấy tenantId hoặc actorId từ @ToolParam do model tạo để quyết định key bảo mật. Cũng không tin raw tenantId từ HTTP request chưa được xác thực; hãy gắn chúng sau khi server xác minh principal.

Nếu ứng dụng gọi ToolCallback trực tiếp, vẫn phải tự tạo ToolContext từ danh tính đáng tin cậy. Một test tạo ToolContext bất kỳ chỉ chứng minh callback đọc đúng giá trị, không chứng minh caller production có xác thực.

## 5. Ví dụ Spring Cache + Caffeine: service cache sau authorization

Giả sử người dùng hỏi trạng thái đơn hàng. Mỗi request phải đi qua authorization, kể cả khi snapshot được cache. Vì vậy đặt kiểm tra quyền ở adapter @Tool trước khi gọi **một bean cache khác**.

~~~java
public record OrderSnapshot(
        String orderId,
        String status,
        String trackingCode,
        Instant lastUpdatedAt) {
}

@Component
public class OrderTools {

    private final OrderAccessPolicy accessPolicy;
    private final CachedOrderReader cachedReader;

    public OrderTools(
            OrderAccessPolicy accessPolicy,
            CachedOrderReader cachedReader) {
        this.accessPolicy = accessPolicy;
        this.cachedReader = cachedReader;
    }

    @Tool(description = "Chỉ đọc trạng thái hiện tại của đơn hàng theo mã")
    public OrderSnapshot getOrderStatus(
            @ToolParam(description = "Mã đơn hàng") String orderId,
            ToolContext toolContext) {

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Thiếu mã đơn hàng");
        }

        String tenantId = requireTrustedContext(toolContext, "tenantId");
        String actorId = requireTrustedContext(toolContext, "actorId");
        String locale = requireTrustedContext(toolContext, "locale");

        // Bắt buộc chạy ở MỌI request, trước cache hit/miss.
        accessPolicy.requireCanReadOrder(tenantId, actorId, orderId);

        // Lời gọi tới một bean khác đi qua Spring caching proxy.
        return cachedReader.load(tenantId, actorId, orderId, locale);
    }

    private static String requireTrustedContext(
            ToolContext context, String key) {
        if (context == null) {
            throw new IllegalArgumentException("Thiếu tool context");
        }
        Object value = context.getContext().get(key);
        if (!(value instanceof String s) || s.isBlank()) {
            throw new IllegalArgumentException("Thiếu context: " + key);
        }
        return s;
    }
}
~~~

CachedOrderReader:

~~~java
@Service
public class CachedOrderReader {

    private final OrderDataGateway orderDataGateway;

    public CachedOrderReader(OrderDataGateway orderDataGateway) {
        this.orderDataGateway = orderDataGateway;
    }

    @Cacheable(cacheNames = "orderSnapshots", sync = true)
    public OrderSnapshot load(
            String tenantId,
            String actorId,
            String orderId,
            String locale) {

        return orderDataGateway.loadAuthorizedSnapshot(
                tenantId, actorId, orderId, locale);
    }
}
~~~

Với key generator mặc định của Spring Cache, tổ hợp **toàn bộ tham số method** trở thành key. Vì vậy tenantId, actorId, orderId và locale đều tham gia định danh một kết quả cache. Một Spring proxy thực thi @Cacheable trước khi chạy thân method; authorization ở OrderTools vẫn được gọi mỗi lần trước cache lookup.

loadAuthorizedSnapshot có thể kiểm tra thêm điều kiện bảo mật ở data-access layer (defense in depth), nhưng trên cache hit code đó không chạy. Vì vậy việc accessPolicy.requireCanReadOrder không bị cache và tra cứu trạng thái quyền đủ mới là một invariant quan trọng.

### Bật Spring Cache và Caffeine

Trong Maven, thêm dependency quản lý bằng BOM của dự án:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
~~~

Bật annotation-driven caching:

~~~java
@Configuration
@EnableCaching
class CacheConfiguration {
}
~~~

Trong application.properties:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=orderSnapshots
spring.cache.caffeine.spec=maximumSize=20000,expireAfterWrite=30s,recordStats
~~~

expireAfterWrite=30s đặt TTL từ lần ghi/refresh cache, không tăng thời hạn chỉ vì có người đọc. maximumSize=20000 giới hạn số entry theo cache policy, không phải 20.000 byte. recordStats giúp quan sát hit/miss ở provider nếu metrics integration hỗ trợ.

**TTL 30 giây chỉ là ví dụ.** Một hệ thống thanh toán, tồn kho hoặc xác nhận đơn có thể cần giới hạn khác, hoặc không được phép cache. Phải lấy quyết định từ yêu cầu consistency của nghiệp vụ chứ không từ một hằng số chung.

### Những điều cần lưu ý về Spring proxy

Spring caching dùng AOP interceptor. Nếu class tự gọi this.load(...), lời gọi không đi qua proxy trong chế độ proxy mặc định, nên @Cacheable có thể không hoạt động. Đặt method cache trên bean riêng và inject bean đó vào tool adapter như ví dụ.

@EnableCaching phải hoạt động trong application context có bean tương ứng. Không dùng new CachedOrderReader(...) rồi mong annotation tự chạy. Nếu đọc dữ liệu và cache method nằm trong transaction ghi dài, cache hit/miss và invalidation có thể quan sát trạng thái không mong muốn; ưu tiên transaction đọc ngắn và event invalidation sau commit.

### Giới hạn của sync=true

@Cacheable(sync = true) đề nghị provider chỉ tính một giá trị cho nhiều thread cùng miss một key. Nó là hint và cần được cache implementation hỗ trợ. Đổi lại:

- Không thể dùng unless cùng sync=true.
- Chỉ dùng một cache.
- Không kết hợp operation cache khác trên cùng method.
- Sync của Caffeine tại một JVM **không đồng nghĩa** có distributed lock giữa nhiều instance.

Nếu cần tránh cache null hoặc kết quả đặc biệt, hãy thiết kế loader trả kiểu phù hợp, phân biệt not-found theo policy hoặc dùng @Cacheable không sync với unless = "#result == null" khi đúng nhu cầu. Không mặc định cache lỗi network, permission denial, exception hay kết quả chưa xác minh.

## 6. Chọn Caffeine hay Redis?

Spring Cache là abstraction; cache provider quyết định nơi lưu entry, eviction, TTL, serialization và hành vi đồng thời. Caffeine và Redis đều phù hợp cho read-only tool results nhưng giải quyết bài toán khác nhau.

| Đặc điểm | Caffeine | Redis |
|---|---|---|
| Vị trí dữ liệu | Bộ nhớ trong mỗi JVM | Kho cache ngoài tiến trình, dùng chung nhiều instance |
| Latency | Rất thấp, không qua network | Có network hop, nhưng có thể chia sẻ hit toàn cụm |
| Dữ liệu giữa các pod | Mỗi pod có cache riêng | Các pod có thể dùng chung cache |
| Tác động restart | Entry biến mất khi JVM restart | Có thể còn entry theo cấu hình Redis |
| Invalidation | Mỗi node phải xóa cache riêng | Một lệnh evict tác động kho chung; cần xem topology/near-cache |
| Bộ nhớ | Giới hạn heap và maximumSize | Giới hạn Redis memory, eviction policy và cấu hình |
| Serialization | Có thể lưu object JVM trực tiếp | Phải serialize key/value, quản lý schema và bảo mật |
| Lỗi hạ tầng | Ứng dụng vẫn chạy nếu đủ heap | Cần policy khi Redis không kết nối được |
| Hợp với | Một node, dữ liệu nóng, TTL ngắn | Nhiều pod, cần chia sẻ cache và TTL trung tâm |

Không nên dùng một cache duy nhất cho mọi loại tool. Ví dụ public catalog có TTL dài và ít nhạy cảm; order snapshot cần key theo tenant/actor và TTL ngắn; dữ liệu về quyền truy cập nên xác minh ở nguồn đáng tin cậy.

### Ví dụ RedisCacheManager với TTL

Spring Data Redis hỗ trợ cấu hình TTL per-cache bằng RedisCacheConfiguration.entryTtl và có thể vô hiệu hóa caching null:

~~~java
@Configuration
@EnableCaching
class RedisCacheConfigurationApp {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofSeconds(30))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
~~~

Ví dụ này minh họa TTL, không phải cấu hình bảo mật/serialization đầy đủ cho production. RedisCacheConfiguration mặc định có key prefix theo cache name; không tắt prefix tùy tiện vì có thể va chạm tên khóa giữa các cache. Hãy chọn serializer phù hợp DTO và schema version, hạn chế native Java serialization với dữ liệu không đáng tin cậy, và phân quyền kết nối Redis bằng credential/TLS/network controls phù hợp.

TTL của Redis mặc định được đặt/reset khi ghi entry, không tự gia hạn chỉ vì một GET thông thường. Nếu muốn time-to-idle, Spring Data Redis có hỗ trợ enableTimeToIdle trong những điều kiện nhất định, với Redis phiên bản tương thích và mọi reader dùng GETEX nhất quán. **Time-to-idle không tương đương một giới hạn tuổi tối đa**: dữ liệu nóng có thể sống lâu hơn mong muốn. Với thông tin nghiệp vụ cần thời hạn cứng, ưu tiên TTL từ lúc ghi và kiểm tra freshness rõ ràng.

### Cache nhiều tầng (L1/L2)

Có thể đặt Caffeine làm L1, Redis làm L2 để giảm latency, nhưng mỗi tầng bổ sung cửa sổ dữ liệu cũ và yêu cầu invalidation. Không tự suy ra Spring Cache ghép hai CacheManager là có cascade L1/L2 đúng nghĩa; nếu triển khai, cần một composite cache được thiết kế rõ thứ tự đọc/ghi, TTL và phát invalidation giữa các node.

Với dữ liệu nhạy cảm hoặc yêu cầu chính xác cao, kiến trúc đơn giản với một cache được quản lý tốt thường đáng tin cậy hơn một hệ đa tầng khó đồng bộ.

## 7. TTL là một chính sách nghiệp vụ, không phải thông số tiện tay

Time-to-live (TTL) là thời gian tối đa một entry tồn tại trong cache theo cơ chế đã cấu hình. Nhưng TTL không luôn bảo đảm dữ liệu còn mới: nguồn có thể thay đổi một mili-giây sau lần load. TTL chỉ giới hạn khoảng thời gian **có thể** dùng lại snapshot khi chưa có invalidation khác.

Tách các khái niệm:

| Khái niệm | Ý nghĩa | Rủi ro nếu nhầm |
|---|---|---|
| expire-after-write | Hết hạn tính từ lúc entry được ghi/cập nhật | Hợp để giới hạn tuổi tối đa sau lần load |
| expire-after-access / time-to-idle | Hết hạn nếu không được truy cập trong khoảng thời gian | Entry được truy cập liên tục có thể rất cũ |
| Source freshness | Lần cập nhật gần nhất tại nguồn dữ liệu | Cache TTL không thay thế source version |
| Maximum staleness | Độ cũ tối đa nghiệp vụ chấp nhận | Có thể nghiêm hơn TTL cache |
| Stale-while-revalidate | Tạm trả dữ liệu cũ trong khi refresh | Phải công bố và giới hạn tính cũ; không hợp với mọi dữ liệu |
| Explicit invalidation | Xóa entry khi dữ liệu/quyền thay đổi | Giảm cửa sổ stale nhưng cần đường phát event đáng tin cậy |

### Đặt TTL theo mức biến động và hậu quả sai lệch

Ví dụ các mức **minh họa, không phải chuẩn cố định**:

| Loại dữ liệu | TTL ban đầu để thử nghiệm | Điều kiện đặc biệt |
|---|---|---|
| Danh mục sản phẩm công khai | 5–30 phút | Có version/eviction khi catalog publish |
| Bảng cấu hình tĩnh đã version hóa | 30 phút hoặc dài hơn | Key có cấu hình version; không cache secret |
| Tracking đơn hàng | 10–60 giây | Khi user vừa cập nhật đơn, phải có cách bypass/read-your-writes |
| Tồn kho khả dụng | 1–5 giây hoặc không cache | Không dùng để bảo đảm đặt chỗ thành công |
| Eligibility, hạn mức còn lại | Không cache hoặc rất ngắn | Phải kiểm tra lại khi thực thi lệnh ghi |
| ACL/quyền truy cập | Không dùng như bảo đảm duy nhất | Revocation phải có hiệu lực theo SLA bảo mật |

Nếu nghiệp vụ yêu cầu dữ liệu mới tức thời, không sử dụng cached snapshot chỉ vì có TTL ngắn. Một TTL 1 giây vẫn có thể vi phạm invariant kiểm tra số dư ngay trước thanh toán.

### Phải ghi nhận thời gian dữ liệu, không chỉ thời gian cache

Với snapshot có ý nghĩa nghiệp vụ, trả về lastUpdatedAt hoặc dataVersion do nguồn cung cấp:

~~~java
public record OrderSnapshot(
        String orderId,
        String status,
        Instant lastUpdatedAt,
        long dataVersion) {
}
~~~

Không biến timestamp tạo tại cache thành timestamp "đơn hàng cập nhật lúc". Khi cache hit, giá trị lastUpdatedAt vẫn là thời điểm nguồn thay đổi, còn cacheHitAt là thời điểm quan sát khác. UI và mô hình cần phân biệt hai khái niệm nếu có nguy cơ thông tin cũ.

### TTL khác theo mức rủi ro: cách triển khai

Nếu chỉ có một cache manager và một cấu hình TTL, dễ làm các loại dữ liệu dùng chung TTL sai. Dùng cache names tách biệt, ví dụ productCatalog, orderSnapshots, publicRates, rồi đặt TTL per-cache:

~~~java
RedisCacheConfiguration base =
        RedisCacheConfiguration.defaultCacheConfig()
                .disableCachingNullValues();

Map<String, RedisCacheConfiguration> cacheConfigs = Map.of(
        "productCatalog", base.entryTtl(Duration.ofMinutes(15)),
        "orderSnapshots", base.entryTtl(Duration.ofSeconds(30)),
        "publicRates", base.entryTtl(Duration.ofSeconds(20))
);

RedisCacheManager manager = RedisCacheManager
        .builder(connectionFactory)
        .cacheDefaults(base.entryTtl(Duration.ofMinutes(1)))
        .withInitialCacheConfigurations(cacheConfigs)
        .build();
~~~

Đây là fragment cấu hình minh họa; trong ứng dụng, đặt nó trong @Bean và tránh khai báo thêm một CacheManager cạnh tranh ngoài ý muốn. Giá trị Duration phải được xác định bằng thỏa thuận với nguồn dữ liệu và yêu cầu nghiệp vụ.

## 8. Invalidation khi dữ liệu hoặc quyền thay đổi

TTL là đường dự phòng, còn sự kiện thay đổi dữ liệu là cơ hội làm mới sớm. Với getOrderStatus, khi cancelOrder, shipOrder hoặc changeDeliveryAddress thành công, snapshot cũ có thể không còn phù hợp.

### Evict sau commit, không xóa khi transaction còn có thể rollback

~~~mermaid
sequenceDiagram
    participant Command as OrderCommandService
    participant DB as Database
    participant Event as After-commit listener
    participant Cache as CacheManager
    Command->>DB: BEGIN + UPDATE order
    DB-->>Command: OK
    Command->>Event: Publish OrderChanged trong transaction
    Note over Event: Đăng ký listener cho phase AFTER_COMMIT
    Command->>DB: COMMIT
    DB-->>Command: Commit successful
    Event->>Cache: Listener chạy và evict sau commit
    Cache-->>Event: Evicted
~~~

Sơ đồ diễn giải thứ tự cam kết nghiệp vụ; trong thực tế, event thường được publish trong transaction và listener AFTER_COMMIT chỉ được kích hoạt sau commit thành công:

~~~java
@Transactional
public void changeOrderStatus(String orderId, String tenantId) {
    orderRepository.changeStatus(orderId, tenantId);
    events.publishEvent(new OrderChanged(tenantId, orderId));
}
~~~

Listener ví dụ:

~~~java
@Component
class OrderCacheInvalidator {

    private final CacheManager cacheManager;

    OrderCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderChanged(OrderChanged changed) {
        Cache cache = cacheManager.getCache("orderSnapshots");
        if (cache != null) {
            // Cách đơn giản nhưng rất rộng, chỉ phù hợp cache nhỏ.
            cache.clear();
        }
    }
}
~~~

Cách clear toàn bộ chỉ phù hợp để minh họa điểm "evict sau commit", hoặc trường hợp cache nhỏ và cập nhật hiếm. Khi cache chứa hàng nghìn tenant/actor, clear toàn bộ gây stampede và xóa nhiều entry không liên quan. Hãy áp dụng targeted eviction hoặc version-based keying để xóa đúng dữ liệu chịu ảnh hưởng.

### Vì sao evict theo orderId không đơn giản?

Nếu key gồm tenantId + actorId + orderId + locale, một thay đổi orderId phải vô hiệu hóa nhiều key tương ứng với actor/locale khác nhau. Không thể gọi evict(orderId) rồi kỳ vọng Spring Cache tự tìm tất cả key chứa orderId.

Một số cách thiết kế:

1. **Versioned key:** nếu mỗi request có thể lấy dataVersion mới đáng tin cậy với chi phí thấp, đưa version vào key. Sau update, version tăng và các lần đọc mới không còn khớp key cũ; entry cũ hết hạn theo TTL.
2. **Reverse index:** lưu mapping tenant/order -> tập cache keys cần xóa. Phải bảo đảm cập nhật và dọn reverse index đúng khi eviction/expiration.
3. **Provider-specific tags/namespaces:** dùng khả năng quản lý key của cache provider, có cơ chế kiểm soát xóa theo phạm vi.
4. **Invalidate toàn phân vùng:** nếu quy mô nhỏ, xóa cache của riêng tenant hoặc phân vùng thay vì toàn bộ hệ thống.
5. **Giảm TTL hoặc bỏ cache:** khi việc invalidate chính xác quá phức tạp hoặc dữ liệu phải luôn mới.

Version-based key không phải phép màu: nếu source version lấy từ một cache khác cũng stale, entry mới vẫn có thể bị tái sử dụng sai. Version phải đến từ nguồn có độ mới đáp ứng hợp đồng.

### Race giữa load và eviction

Xét trường hợp:

1. Thread A cache miss, đọc status cũ từ database.
2. Thread B cập nhật status mới và evict entry.
3. Thread A hoàn tất load muộn và ghi status cũ vào cache.

Cache có thể chứa dữ liệu cũ **sau cả lúc đã evict**. Đây là stale-fill race. Cách giảm rủi ro gồm key theo version, invalidation có fencing/sequence, hoặc bỏ cache với dữ liệu cần nhất quán ngay. TTL đơn thuần chỉ giới hạn thời gian dữ liệu cũ còn tồn tại.

### Invalidation phân tán không nguyên tử với DB commit

Nếu DB commit rồi process chết trước khi gửi invalidation qua Redis/pubsub, cache có thể stale đến TTL. Với yêu cầu strong consistency, không nên đặt correctness phụ thuộc vào một best-effort event after commit. Có thể lưu outbox event trong cùng DB transaction và chuyển thông điệp invalidation theo một relay bền vững, nhưng outbox vẫn có độ trễ và consumer phải idempotent. Luôn giữ TTL làm đường giới hạn cuối cùng và có khả năng bypass cache khi cần đọc dữ liệu ngay sau ghi.

## 9. Khi quyền truy cập thay đổi, TTL không đủ

Caching theo actorId chặn dữ liệu người A bị lấy từ key của người B, nhưng không bảo đảm người A vẫn được phép đọc. Một người có thể mất quyền giữa lần load đầu và lần đọc sau. Vì vậy kiểm tra permission hiện tại **trước khi gọi service cache**.

~~~text
Request 1: actor A có quyền -> authz PASS -> cache miss -> lưu snapshot
Permission update: actor A bị thu hồi quyền
Request 2: actor A yêu cầu lại -> authz DENY -> không đọc snapshot
~~~

Nếu authorization bản thân cũng được cache với TTL 5 phút, lời hứa thu hồi quyền tức thời có thể sai. Hãy thiết kế SLA rõ: recheck qua policy store, role version, revocation event đáng tin cậy hoặc bỏ cache cho permission nhạy cảm. Đừng kết luận kết quả an toàn chỉ vì đã đưa actorId vào key.

Không cache permission denied theo một key chung như orderId: phản hồi từ chối của actor A có thể làm actor B bị từ chối sai; ngược lại một cached success từ A có thể lộ dữ liệu cho B. Với denied results, giải pháp mặc định an toàn là không cache.

### Read-your-writes và thao tác ngay sau ghi

Người dùng vừa sửa địa chỉ giao hàng rồi hỏi lại ngay. Nếu cache còn snapshot cũ, câu trả lời tạo cảm giác cập nhật thất bại.

Các lựa chọn:

- Evict sau commit và chỉ trả thành công khi đường trạng thái đã được cập nhật theo SLA.
- Trả kết quả đã commit trực tiếp từ command response, không buộc model đọc lại qua cache.
- Thêm cờ bypassCache trong **ToolContext từ server** cho request theo workflow cần đọc mới, không để model tự đặt cờ này từ arguments.
- Dùng dataVersion từ command để truy vấn snapshot có version tối thiểu.

Với yêu cầu mới nhất tuyệt đối, bypass cache và đọc authoritative source. Đừng cố "chữa" bằng cách giảm TTL 30 giây xuống 1 giây nếu business invariant đòi dữ liệu mới ngay.

## 10. Cache key theo version và bypass một cách có chủ đích

Đối với nguồn có version tăng đơn điệu, có thể tách truy vấn lấy version nhẹ khỏi truy vấn snapshot đắt tiền. Cache method nhận version như một tham số chính thức:

~~~java
@Service
class VersionedOrderReader {

    private final OrderDataGateway gateway;

    VersionedOrderReader(OrderDataGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "versionedOrderSnapshots", sync = true)
    public OrderSnapshot load(
            String tenantId,
            String actorId,
            String orderId,
            String locale,
            long authoritativeVersion) {

        return gateway.loadSnapshotAtLeastVersion(
                tenantId, actorId, orderId, locale, authoritativeVersion);
    }
}
~~~

Lớp adapter gọi gateway.currentVersion(...) theo nguồn đủ mới rồi mới gọi bean trên. Cần định nghĩa rõ loadSnapshotAtLeastVersion: nếu replica chỉ trả version thấp hơn, nó phải retry theo budget, chuyển về primary hoặc trả lỗi, không trả dữ liệu cũ rồi cache nó dưới key version mới.

Ưu điểm: khi version tăng, key mới không khớp bản cũ. Nhược điểm: vẫn phải đọc version ở mỗi request, số entry tăng theo phiên bản và có thể phát sinh race với replica lag. Chỉ chọn cách này nếu kết quả đo chứng minh giảm chi phí so với đọc snapshot đầy đủ.

### Bypass an toàn

Bypass cache cần có một đường code rõ ràng, ví dụ adapter chọn gọi cachedReader.load(...) hoặc orderDataGateway.loadAuthorizedSnapshot(...) sau authorization. Đừng tự gọi this.load(...) trong cùng bean cache với hy vọng Spring sẽ "bỏ qua proxy" theo cách ổn định.

~~~java
boolean requireFresh =
        Boolean.TRUE.equals(toolContext.getContext().get("requireFresh"));

accessPolicy.requireCanReadOrder(tenantId, actorId, orderId);

return requireFresh
        ? orderDataGateway.loadAuthorizedSnapshot(
                tenantId, actorId, orderId, locale)
        : cachedReader.load(tenantId, actorId, orderId, locale);
~~~

Trong code thực tế, orderDataGateway được inject ở adapter như các dependency khác. Cờ requireFresh phải được server cấp từ workflow có quyền, ví dụ ngay sau một write đã commit, không phải một boolean do mô hình tự cung cấp để thay đổi business policy.

## 11. Negative caching và kết quả lỗi

Một cache miss có thể dẫn đến:

- Resource tồn tại và được phép xem: có thể cache snapshot.
- Resource không tồn tại: có thể cân nhắc negative cache TTL rất ngắn nếu key đã phân vùng an toàn.
- Resource tồn tại nhưng không được phép xem: **không cache như kết quả dữ liệu**; xử lý authorization trước.
- Downstream trả timeout, 429, 503 hoặc mạng lỗi: không lưu response lỗi như kết quả thành công.
- DTO chỉ hoàn thành một phần: không lưu như snapshot đầy đủ nếu caller cần toàn bộ dữ liệu.

Negative cache có lợi khi hệ thống bị hỏi lặp lại nhiều ID không tồn tại, nhưng có thể gây sai sau khi resource vừa được tạo. Nếu tạo orderId mới, phải evict negative entry hoặc dùng TTL thật ngắn. Tránh để negative entry phân biệt được "không tồn tại" với "không có quyền" khi API cố ý không tiết lộ sự tồn tại của resource.

Ví dụ lưu kết quả thành công và bỏ null khi không dùng sync:

~~~java
@Cacheable(
        cacheNames = "publicCatalog",
        unless = "#result == null")
public PublicCatalogItem findPublishedItem(String sku) {
    return catalogGateway.findPublished(sku).orElse(null);
}
~~~

Đây là pattern cho dữ liệu công khai, không phải cách khuyến nghị trả null từ mọi tool. Khi dùng sync=true, không kết hợp unless; hãy dùng thiết kế khác hoặc cache provider có semantics phù hợp. Với kết quả chứa thông tin nhạy cảm, cache negative và lỗi phải được review riêng.

## 12. Stampede, hot keys và concurrency

Cache stampede xảy ra khi nhiều request cùng đến lúc một key hết hạn, tất cả cùng tải dữ liệu từ nguồn. Ví dụ 500 người dùng truy vấn bảng giá công khai đúng thời điểm TTL 60 giây hết hạn; nếu mỗi request gọi API ngoài, tải có thể đột biến.

Các kỹ thuật:

| Kỹ thuật | Mục đích | Lưu ý |
|---|---|---|
| Single-flight per key | Chỉ một loader chạy cho cùng key tại một JVM | Spring @Cacheable(sync=true) là hint, phụ thuộc provider |
| TTL jitter | Tránh nhiều key hết hạn đồng thời | Không vượt maximum staleness đã cam kết |
| Refresh ahead | Làm mới trước khi hết hạn cho key nóng | Dùng budget, không refresh tất cả vô điều kiện |
| Rate limit / concurrency cap | Bảo vệ service nguồn | Có thể cần queue hoặc backpressure |
| Circuit breaker + timeout | Không giữ hàng loạt worker chờ downstream chết | Không tự động trả stale nếu nghiệp vụ cấm |
| Distributed coordination | Hạn chế load duplicate giữa nhiều pod | Có chi phí lock/lease, cần fencing và timeout |

Spring @Cacheable(sync=true) có thể giảm stampede trong một JVM với Caffeine, nhưng không có nghĩa khóa phân tán toàn cụm Redis. Nếu ứng dụng có 20 pod, có thể vẫn có 20 loader đồng thời cho cùng key khi tất cả miss. Hãy đo tải thực và dùng cơ chế provider-specific khi cần.

### Chú ý riêng với Mono/Flux và Reactor Context

Với service reactive, đừng tự suy rằng @Cacheable hoạt động như cache một DTO đồng bộ. Trong các bản Spring Framework hiện đại, caching cho Mono/Flux được thích ứng theo kiểu trả về; với sync=true, cache có thể tự subscribe để chia sẻ load giữa nhiều caller, và Reactor Context của caller không nhất thiết được truyền nguyên vẹn vào loader. Nếu kết quả phụ thuộc security context, locale hoặc tenant trong Reactor Context, hãy đưa dữ liệu ảnh hưởng kết quả thành tham số method và cache key sau khi xác thực; tốt hơn nữa là thiết kế riêng reactive caching khi cần backpressure/cancellation tinh vi.

Test cả cache miss, cache hit và hai subscription đồng thời với các Reactor Context khác nhau. Không đặt một Mono/Flux có chứa request-scoped mutable state vào cache rồi cho rằng nó an toàn giữa các tenant.

### Hết hạn đồng loạt không phải luôn tốt

Đặt cùng TTL 30 phút cho 100.000 entry được khởi tạo lúc deploy dễ làm chúng expire gần nhau. Với dữ liệu không nhạy cảm, jitter ngẫu nhiên vài phần trăm TTL có thể trải tải. Tuy nhiên, nếu dữ liệu có deadline nghiêm ngặt, jitter chỉ được giảm TTL, không kéo dài quá hạn an toàn.

### Đừng cache object mutable dùng chung giữa request

Với Caffeine, một cache hit có thể trả lại đúng object reference đã lưu. Nếu caller sửa List/Map/DTO mutable, request khác có thể quan sát object đã bị biến đổi.

Ưu tiên immutable records, collection không cho sửa hoặc defensive copy. Không cache JPA entity đang attached với persistence context, Hibernate proxy, input/output stream hoặc object mang request-scoped security context. Nếu DTO chứa list, cần chú ý bất biến sâu chứ không chỉ record wrapper.

## 13. Cách xử lý khi cache provider lỗi

Lỗi cache không nên làm ứng dụng bỏ qua authorization. Một thiết kế read-only cache thường cho phép fallback tới authoritative service khi cache lỗi, miễn là mức tải cho phép và timeout được kiểm soát.

Phân biệt:

| Tình huống | Xử lý phù hợp |
|---|---|
| Cache miss bình thường | Load từ nguồn, cache nếu kết quả hợp lệ |
| Cache unavailable nhưng nguồn tốt | Bypass cache, vẫn kiểm tra quyền; bảo vệ nguồn bằng rate/concurrency limit |
| Cache unavailable và nguồn cũng lỗi | Trả lỗi có kiểm soát; không giả mạo dữ liệu thành công |
| Lỗi deserialize do đổi DTO | Evict/skip entry hỏng, đọc lại nguồn, ghi log có lọc |
| Chỉ có stale entry nhưng nghiệp vụ yêu cầu mới | Không trả stale; trả lời chưa thể xác minh hoặc fallback |
| Stale entry của dữ liệu công khai có policy cho phép | Có thể stale-while-revalidate với thông báo thời điểm cập nhật |

Spring Cache cho phép cấu hình CacheErrorHandler để xử lý một số lỗi cache access; việc nuốt lỗi một cách rộng rãi có thể che giấu outage và khiến backend bị dồn tải. Dùng handler có giám sát, chính sách fallback và load shedding rõ ràng.

Không coi cache là kho dữ liệu chính. Cache entry có thể bị eviction vì thiếu bộ nhớ, TTL, deploy hoặc lỗi hạ tầng; ứng dụng phải hoạt động đúng về mặt nghiệp vụ khi một entry không tồn tại.

## 14. An toàn dữ liệu và tuân thủ

Một kết quả cache có thể chứa thông tin cá nhân, lịch sử thanh toán, giá hợp đồng hoặc dữ liệu nội bộ. Ngoài phân tách key, cần kiểm soát cả quá trình lưu trữ:

1. Cấu hình quyền truy cập Redis/Caffeine metrics phù hợp; Redis không nên mở công khai.
2. Mã hóa kết nối và lưu trữ nếu chính sách yêu cầu.
3. Dùng serializer có kiểu cho phép, schema version và giới hạn payload.
4. Không lưu access token, secret, credential hoặc raw ToolContext.
5. Không biến cache key chứa PII thành metric label có cardinality rất cao.
6. Xác định retention, việc xóa dữ liệu theo yêu cầu và backup/snapshot của cache nếu được bật.
7. Kiểm tra logging/debug endpoint có thể phơi bày key/value.
8. Chặn cache poisoning: không tin field tenant/actor do model tạo hoặc dữ liệu chưa kiểm tra từ nguồn ngoài.

Cache không thay thế authorization, tenant isolation hoặc kiểm soát quyền ở database. Đặc biệt với multi-tenant SaaS, dùng tenant-scoped key và kiểm thử chính xác request tenant A không bao giờ thấy snapshot tenant B ngay cả khi hai tenant dùng cùng orderId.

### Tool result có thể làm lộ dữ liệu khi đưa trở lại mô hình

Ngay cả khi cache cô lập đúng, tool result vẫn được chuyển thành thông tin để model tổng hợp câu trả lời. Chỉ trả projection mà người dùng được phép xem, giới hạn kích thước và loại bỏ trường nội bộ; không đưa nguyên entity, secret, audit log hay metadata quyền vào ToolCallResultConverter.

Với kết quả rất lớn, trả danh sách rút gọn hoặc phân trang. Cache một DTO nhỏ và có chủ đích thường giúp giảm cả thời gian serialize, bộ nhớ và số token hơn là cache một bản ghi khổng lồ không dùng hết.

## 15. Đo hiệu quả bằng dữ liệu, không chỉ nhìn hit rate

Các chỉ số cần theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Cache hit ratio | Tỷ lệ lookup lấy được dữ liệu cache |
| Miss/load ratio | Tỷ lệ phải đọc nguồn |
| Stale response rate | Tỷ lệ kết quả bị đánh giá cũ theo policy |
| Authorization denial | Quyền bị từ chối trước cache lookup |
| Eviction/expiration count | Áp lực bộ nhớ, TTL hoặc invalidation |
| Loader latency p50/p95/p99 | Chi phí truy cập dữ liệu khi miss |
| Tool callback latency p95 | Latency toàn callback gồm quyền và cache |
| Cache memory/entry size | Dung lượng và khả năng mở rộng |
| Downstream requests per tool turn | Mức giảm request thật đến DB/API |
| Error/fallback count | Độ ổn định khi cache hỏng |
| Token usage per conversation | Kiểm tra tác động thực tế tới LLM (nếu có) |

Không dùng userId, raw orderId, JWT, query text hoặc toàn bộ JSON arguments làm label metric. Giữ tag thấp cardinality như cacheName, toolName, hit/miss, errorCategory và riskTier; correlation ID nên nằm trong trace/log có kiểm soát.

### Ví dụ tính chi phí kỳ vọng

Giả sử một phép đọc nguồn tốn 100 ms, cache lookup tốn 2 ms, hit rate là 80% và bỏ qua độ trễ authorization cố định:

~~~text
Latency đọc trung bình
  ~= 0.80 * 2 ms
   + 0.20 * (2 ms + 100 ms)
  = 22 ms

Giảm so với không cache
  ~= (100 - 22) / 100
  = 78%
~~~

Đây là ví dụ giả định để hướng dẫn cách tính, không phải benchmark. Thực tế còn phân phối tail latency, TTL expiration, serialization, số lần gọi model và độ trễ check quyền. Nếu hit rate cao nhưng backend đã rất nhanh, chi phí bộ nhớ/invalidation của cache có thể lớn hơn lợi ích.

### Tác động tới token mô hình

Nếu mô hình vẫn nhận cùng một tool result dài 2.000 token sau cache hit, 2.000 token ấy **vẫn phải được xử lý** trong lượt model tiếp theo. Caching không tự rút ngắn câu trả lời của tool. Muốn giảm token, hãy kết hợp DTO projection nhỏ, lọc field, giới hạn list, lookup chỉ khi cần và đánh giá tool search để tránh công cụ không liên quan.

## 16. Kiểm thử cache và quyền truy cập

Unit test cho cache key và integration test với Spring caching proxy nên được tách riêng:

| Test case | Kết quả cần xác minh |
|---|---|
| Cùng tenant/actor/order/locale gọi hai lần | Policy chạy hai lần, loader chỉ chạy một lần khi hit |
| Hai tenant cùng orderId | Không trả chéo dữ liệu |
| Hai actor cùng tenant/order | Không dùng chung snapshot nếu key theo actor |
| Một actor bị thu hồi quyền | Lần sau bị từ chối dù entry vẫn còn |
| Locale, currency, page hoặc filter khác | Tạo key khác khi dữ liệu có thể khác |
| TTL hết hạn | Lần đọc mới quay về nguồn |
| Dữ liệu đổi rồi evict sau commit | Kết quả mới được đọc lại |
| DB rollback | Không evict như thể write đã commit |
| Stale-fill race | Không để old version ghi đè new version trong mode cần consistency |
| Cùng key có nhiều reader đồng thời | Đo số lần loader thật và kiểm tra sync/provider |
| Cache provider unavailable | Không bỏ qua authorization; fallback có kiểm soát |
| Result null/not-found | Áp policy negative caching đã khai báo |
| Downstream timeout/503 | Không lưu lỗi như snapshot thành công |
| Cached DTO bị mutate | Reader khác không nhìn thấy dữ liệu sai |
| Tool bị mô hình gọi với tenantId giả | Tenant quyết định từ ToolContext đáng tin cậy |
| Tool có side effect | Không dùng read cache thay cho idempotency/transaction |

### Ví dụ integration test: hit không bỏ qua authorization

~~~java
@SpringBootTest
class OrderToolCacheIT {

    @Autowired OrderTools orderTools;
    @Autowired CacheManager cacheManager;

    // Cấu hình OrderAccessPolicy và OrderDataGateway thành test doubles
    // qua @TestConfiguration hoặc bean mocks của Spring test.
    @Autowired OrderAccessPolicy accessPolicy;
    @Autowired OrderDataGateway dataGateway;

    @BeforeEach
    void clearCache() {
        Cache cache = cacheManager.getCache("orderSnapshots");
        assertThat(cache).isNotNull();
        cache.clear();
    }

    @Test
    void checksAuthorizationEvenWhenSnapshotIsCached() {
        ToolContext context = new ToolContext(Map.of(
                "tenantId", "tenant-a",
                "actorId", "user-7",
                "locale", "vi-VN"
        ));

        OrderSnapshot first =
                orderTools.getOrderStatus("ORD-100", context);
        OrderSnapshot second =
                orderTools.getOrderStatus("ORD-100", context);

        assertThat(second).isEqualTo(first);
        verify(accessPolicy, times(2)).requireCanReadOrder(
                "tenant-a", "user-7", "ORD-100");
        verify(dataGateway, times(1)).loadAuthorizedSnapshot(
                "tenant-a", "user-7", "ORD-100", "vi-VN");
    }
}
~~~

Test này giả định test doubles đã được cấu hình để trả cùng một OrderSnapshot; nếu không, cần stub rõ kết quả trước khi gọi. Đừng tạo CachedOrderReader bằng new trong integration test, vì khi ấy @Cacheable có thể không đi qua Spring proxy. Không bọc toàn bộ test trong một transaction làm che khuất hành vi commit/evict.

### Kiểm thử TTL không dùng Thread.sleep tùy ý

Với Caffeine, có thể cấu hình Ticker giả trong test để điều khiển thời gian và đánh giá hết hạn chính xác, thay vì Thread.sleep(30000). Với Redis integration test, sử dụng một Redis test instance và TTL đủ ngắn/đồng hồ điều khiển được, đo độ trễ thực tế với dung sai hợp lý. Nên kiểm thử Redis key prefix/serialization/TTL riêng, không chỉ mock CacheManager.

### Kiểm thử race condition giữa nhiều tenant

Để phát hiện cache key thiếu tenant, hãy setup hai nguồn dữ liệu có cùng orderId nhưng status khác nhau:

~~~text
tenant-a + ORD-100 -> SHIPPING
tenant-b + ORD-100 -> CANCELLED
~~~

Gọi với tenant-a rồi tenant-b; nếu cache key chỉ là orderId, test sẽ trả SHIPPING cho tenant-b và bắt được lỗi. Lặp lại với hai actor của cùng tenant nhưng có visibility khác nhau.

## 17. Bài tập thực hành

Xây dựng ứng dụng có ba read-only tool:

1. getOrderStatus(orderId): snapshot theo tenant/actor, TTL ngắn.
2. getPublishedProduct(sku): danh mục công khai, TTL dài.
3. getPublicRate(pair): dữ liệu thị trường, TTL dựa trên nguồn và thời điểm báo giá.

Yêu cầu thực hiện:

1. Đặt ToolContext tenantId/actorId từ principal đã xác thực; không đưa chúng vào JSON schema mô hình.
2. Viết @Tool adapter, policy check và @Cacheable service ở hai bean riêng.
3. Cấu hình Caffeine expireAfterWrite và maximumSize theo từng cache phù hợp.
4. Đo hit/miss và giảm số lời gọi database/API bằng fake gateway.
5. Thử cùng orderId giữa hai tenant và hai actor có quyền khác nhau.
6. Thu hồi quyền sau cache hit đầu và xác minh lần sau vẫn bị từ chối.
7. Thêm cập nhật order và invalidation AFTER_COMMIT; thử rollback không xóa cache sai.
8. Thử stale-fill race và lựa chọn key theo source dataVersion nếu cần.
9. Thử nhiều request đồng thời tại lúc cache miss, đo loader count.
10. Đổi provider sang Redis, kiểm tra key prefix, TTL, serializer và lỗi kết nối.
11. So sánh downstream cost, p95 latency, cache size và token thực tế.
12. Viết một ca kiểm thử chứng minh capturePayment không bị đưa vào read cache.

Kết quả bài tập cần trả lời được ba câu hỏi: cache key có đủ phân vùng danh tính không; dữ liệu còn đúng thời hạn và bị vô hiệu hóa khi cần không; và lợi ích đo được có lớn hơn chi phí/bảo trì cache không.

## 18. Danh sách kiểm tra trước khi triển khai

- [ ] Chỉ cache tool/read service không có side effect, hoặc dữ liệu được phép dùng lại.
- [ ] Không dùng read-result cache để chống lặp thao tác ghi; dùng idempotency cho command.
- [ ] Key bao gồm dữ liệu nghiệp vụ, tenant, actor/visibility và mọi biến thể ảnh hưởng kết quả.
- [ ] Không đưa access token, raw JWT hoặc secret vào key/value.
- [ ] ToolContext lấy danh tính từ server đã xác thực, không từ model arguments.
- [ ] Authorization chạy trên mọi request, kể cả cache hit.
- [ ] @Cacheable được gọi qua Spring bean proxy, @EnableCaching đã bật.
- [ ] TTL được chọn theo freshness SLA, không mặc định áp cùng thời hạn cho mọi loại dữ liệu.
- [ ] Không dùng expireAfterAccess khi cần giới hạn tuổi tối đa mà không có kiểm soát thêm.
- [ ] Có chiến lược invalidation sau commit và xử lý stale-fill race.
- [ ] Quyền bị thu hồi không thể tiếp tục đọc qua cached snapshot.
- [ ] Caffeine có maximumSize; Redis có TTL, key prefix và serializer an toàn.
- [ ] Đã cân nhắc multi-node cache consistency và việc sync=true không phải distributed lock.
- [ ] Không cache exception, lỗi quyền hoặc response chưa xác minh như dữ liệu tốt.
- [ ] Có policy rõ cho null/not-found, stale-while-revalidate và cache outage.
- [ ] DTO cache là projection nhỏ, hạn chế mutable shared objects.
- [ ] Metrics không mang PII hoặc high-cardinality labels.
- [ ] Có test tenant isolation, permission revocation, TTL, eviction, concurrency, lỗi cache và fresh read.
- [ ] Đã đo hit ratio, giảm downstream requests, p95 latency và chi phí tổng thể.

**Kết luận:** caching kết quả công cụ chỉ đọc có ích khi ứng dụng định nghĩa được cái gì giống nhau, **ai được phép thấy** kết quả đó và **kết quả còn đúng đến khi nào**. Spring AI ToolContext cung cấp danh tính ngoài tầm kiểm soát của mô hình; Spring Cache cung cấp cơ chế lưu đệm; application service vẫn sở hữu authorization, freshness và invalidation. Đo lợi ích thực tế và luôn giữ đường đọc dữ liệu mới cho những thao tác có yêu cầu nhất quán cao.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Tool Calling và ToolContext](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — ToolCallingAdvisor và vòng lặp thực thi](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cacheable: key, sync và unless](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- [Spring Boot — Cache Abstraction và Caffeine Configuration](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Data Redis — RedisCache, TTL và cache configuration](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
