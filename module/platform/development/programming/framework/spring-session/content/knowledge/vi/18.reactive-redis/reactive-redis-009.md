# Tùy chỉnh repository mà không chuyển sang thao tác chặn

Spring Session WebFlux lưu session bằng các API reactive. Khi cần bổ sung kiểm tra dữ liệu, metric, audit, quy tắc timeout hoặc cách lưu trữ riêng, phần tùy chỉnh phải tiếp tục trả về Mono/Flux và dùng các client non-blocking. Nếu một repository reactive gọi RedisTemplate imperative, JDBC blocking hoặc chờ kết quả bằng block(), toàn bộ pipeline có thể bị nghẽn dù chữ ký phương thức vẫn trả Mono.

Nguyên tắc quan trọng là giữ nguyên hợp đồng reactive từ request tới kho dữ liệu. Một thao tác tìm session phải hoàn tất bằng Mono, thao tác lưu phải hoàn tất khi dữ liệu đã được ghi, và lỗi phải được truyền về pipeline. Không tự subscribe bên trong repository, không chuyển lỗi Redis thành session không tồn tại và không phát hành session ID trước khi việc lưu hoàn tất.

Bài này giải thích hợp đồng ReactiveSessionRepository, các cách tùy chỉnh bằng composition/decorator, cách dùng ReactiveRedisTemplate, cách xử lý TTL và index, các lỗi thường gặp khi chuyển từ imperative sang reactive, cùng phương pháp kiểm thử tính non-blocking và độ tin cậy khi chạy nhiều instance.

## 1. Tùy chỉnh ở đâu trong kiến trúc WebFlux?

Trong ứng dụng Servlet, Spring Session thường dùng SessionRepository và SessionRepositoryFilter. Trong WebFlux, session được biểu diễn bằng WebSession và được quản lý qua WebSessionManager. Repository cần cung cấp API reactive để WebFlux không phải chờ thao tác I/O đồng bộ.

Luồng khái niệm:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[WebSessionManager]
    B --> C[WebSessionStore]
    C --> D[ReactiveSessionRepository]
    D --> E[Reactive Redis client]
    E --> F[Redis]
    F --> E
    E --> D
    D --> C
    C --> B
    B --> G[Response commit và resolver phát ID]
~~~

Các lớp có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| WebSessionManager | Tìm hoặc tạo WebSession trong request và điều phối lưu trước khi response commit |
| WebSessionIdResolver | Đọc session ID từ cookie/header và ghi hoặc xóa ID trong response |
| WebSessionStore | Cung cấp WebSession cho WebFlux và kết nối session với repository |
| ReactiveSessionRepository | Tạo, tìm, lưu và xóa session bằng các kiểu reactive |
| ReactiveRedisTemplate / ReactiveRedisOperations | Gửi lệnh Redis không chặn và trả kết quả bằng Publisher |
| Session implementation | Giữ ID, metadata, thuộc tính và chính sách timeout |

Thông thường, controller chỉ cần dùng WebSession qua ServerWebExchange. Chỉ tùy chỉnh repository khi cần thay đổi hành vi lưu trữ, quan sát hoặc quy tắc ở tầng persistence. Nếu chỉ muốn thêm header, cookie hoặc xác thực, hãy dùng resolver/security extension point phù hợp thay vì viết lại repository.

## 2. Hợp đồng ReactiveSessionRepository

ReactiveSessionRepository là abstraction cốt lõi cho kho session reactive. Các thao tác chính có dạng:

| Phương thức | Kết quả | Ý nghĩa |
|---|---|---|
| createSession() | Mono<S> | Tạo đối tượng session mới với ID và metadata ban đầu |
| findById(id) | Mono<S> | Tìm session; Mono rỗng khi không có session hợp lệ |
| save(session) | Mono<Void> | Lưu metadata và thuộc tính session |
| deleteById(id) | Mono<Void> | Xóa session theo ID |

S là kiểu triển khai Session. Các phương thức trả về Mono để biểu diễn một kết quả hoặc một thao tác hoàn tất. Repository không nên tự gọi subscribe(); bên gọi sẽ subscribe khi WebFlux hoàn tất pipeline.

Có ba kết quả cần phân biệt:

- **Tìm thấy:** findById phát ra một Session rồi hoàn tất.
- **Không tồn tại hoặc hết hạn:** findById hoàn tất mà không phát giá trị.
- **Lỗi kho dữ liệu:** Mono phát onError, ví dụ Redis timeout, lỗi xác thực, lỗi serialization hoặc mất kết nối.

Mono.empty() không phải cách biểu diễn mọi lỗi. Chỉ dùng nó cho trường hợp session thực sự không tồn tại hoặc đã hết hạn theo hợp đồng repository. Nếu Redis không khả dụng, phát lỗi để hệ thống biết trạng thái session chưa thể xác định.

Một repository reactive phải duy trì ngữ nghĩa vòng đời: tạo ID an toàn, cập nhật lastAccessTime, áp dụng maxIdleTime, lưu thuộc tính, xóa dữ liệu phụ trợ và không trả session đã hết hạn như thể vẫn hợp lệ.

## 3. Chọn cấu hình có sẵn trước khi viết repository mới

Spring Session cung cấp tích hợp WebFlux và repository reactive cho Redis. Với cấu hình thông thường, dùng @EnableRedisWebSession và các dependency reactive Redis phù hợp để Spring Session tạo thành phần quản lý session.

Ví dụ:

~~~java
@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
public class ReactiveSessionConfiguration {
}
~~~

Ứng dụng cần ReactiveRedisConnectionFactory được cấu hình đúng. Trong Spring Boot, factory có thể được auto-configure từ cấu hình Redis và dependency tương thích.

Trước khi viết repository mới, xác định nhu cầu thực sự:

| Nhu cầu | Hướng phù hợp |
|---|---|
| Đổi namespace hoặc timeout | Dùng thuộc tính cấu hình của repository hiện có |
| Chọn cách flush/save thuộc tính | Dùng chính sách được repository hỗ trợ trong phiên bản đang dùng |
| Thêm metric hoặc đo độ trễ | Bọc repository bằng decorator |
| Thêm kiểm tra dữ liệu trước khi lưu | Bọc repository hoặc đặt validation ở tầng service |
| Thay đổi cấu trúc key/serializer | Chỉ viết adapter/repository riêng khi cấu hình có sẵn không đáp ứng |
| Dùng kho dữ liệu reactive khác | Triển khai ReactiveSessionRepository và tích hợp qua WebSessionStore/manager phù hợp |
| Dùng JDBC blocking trong WebFlux | Không đưa repository blocking vào event loop; cần một thiết kế reactive thực sự nếu muốn dùng kho quan hệ |

Không bật đồng thời nhiều cấu hình tạo WebSessionManager/repository cho cùng ứng dụng. Nếu @EnableRedisWebSession đã cung cấp repository, việc tự đăng ký thêm manager hoặc repository khác có thể tạo hai đường quản lý session, khiến request và response không nhất quán.

## 4. Ưu tiên composition và decorator

Nếu repository hiện có đã xử lý đúng ID, TTL, serialization và vòng đời, hãy giữ nó làm thành phần lưu trữ rồi bọc bằng decorator. Cách này giảm lượng logic phải tự chịu trách nhiệm.

Ví dụ decorator ghi metric cho thao tác repository:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.session.ReactiveSessionRepository;
import org.springframework.session.Session;
import reactor.core.publisher.Mono;

public final class MeteredReactiveSessionRepository<S extends Session>
        implements ReactiveSessionRepository<S> {

    private final ReactiveSessionRepository<S> delegate;
    private final MeterRegistry meterRegistry;

    public MeteredReactiveSessionRepository(
            ReactiveSessionRepository<S> delegate,
            MeterRegistry meterRegistry) {
        this.delegate = delegate;
        this.meterRegistry = meterRegistry;
    }

    private void count(String operation, String outcome) {
        meterRegistry.counter(
                "spring.session.repository.operations",
                "operation", operation,
                "outcome", outcome
        ).increment();
    }

    @Override
    public Mono<S> createSession() {
        return Mono.defer(() -> delegate.createSession())
                .doOnNext(session -> count("create", "success"))
                .doOnError(error -> count("create", "error"));
    }

    @Override
    public Mono<S> findById(String id) {
        return Mono.defer(() -> delegate.findById(id))
                .doOnSuccess(session ->
                        count("find", session == null ? "miss" : "found"))
                .doOnError(error -> count("find", "error"));
    }

    @Override
    public Mono<Void> save(S session) {
        return Mono.defer(() -> delegate.save(session))
                .doOnSuccess(ignored -> count("save", "success"))
                .doOnError(error -> count("save", "error"));
    }

    @Override
    public Mono<Void> deleteById(String id) {
        return Mono.defer(() -> delegate.deleteById(id))
                .doOnSuccess(ignored -> count("delete", "success"))
                .doOnError(error -> count("delete", "error"));
    }
}
~~~

Decorator trên giữ nguyên kết quả của repository gốc và chỉ bổ sung metric. Mono.defer bảo đảm lời gọi delegate diễn ra khi pipeline được subscribe, không chạy sớm trong lúc tạo Mono.

Các metric label chỉ dùng operation và outcome có số lượng giá trị nhỏ. Không gắn session ID, cookie hoặc principal name vào label vì dữ liệu đó có cardinality lớn và có thể nhận diện người dùng.

### Khi nào nên dùng doOnNext, map và flatMap?

- doOnNext phù hợp với side effect đồng bộ, nhẹ như tăng counter hoặc ghi một log đã loại bỏ dữ liệu nhạy cảm.
- map chuyển đổi một giá trị đồng bộ, không phát sinh I/O.
- flatMap nối một thao tác reactive tiếp theo, chẳng hạn tải dữ liệu bổ sung hoặc lưu session.
- then chuyển sang publisher tiếp theo sau khi publisher trước hoàn tất.
- concatMap giữ thứ tự xử lý từng phần tử khi cần tuần tự.
- Mono.when chạy các publisher độc lập song song, nhưng không làm chúng trở thành một transaction nguyên tử.

Không thực hiện gọi Redis, JDBC hoặc HTTP đồng bộ bên trong map/doOnNext. Nếu cần I/O, hãy dùng API reactive và flatMap.

## 5. Đảm bảo thao tác repository thực sự lazy

Reactive pipeline là mô tả công việc cho tới khi có subscriber. Một lỗi thường gặp là gọi thao tác blocking ngay khi tạo Mono rồi bọc kết quả bằng Mono.just.

Không nên:

~~~java
public Mono<Session> findById(String id) {
    Session session = blockingRepository.findById(id);
    return Mono.justOrEmpty(session);
}
~~~

Đoạn code trên vẫn thực hiện truy vấn đồng bộ trước khi trả Mono. Việc bọc kết quả sau đó không làm truy vấn trở thành non-blocking.

Cũng không nên:

~~~java
public Mono<Void> save(Session session) {
    blockingRepository.save(session);
    return Mono.empty();
}
~~~

Lệnh save đã chạy và có thể chặn thread trước khi Mono được subscribe.

Nếu repository delegate đã reactive, hãy trì hoãn việc gọi nó bằng Mono.defer:

~~~java
public Mono<Session> findById(String id) {
    return Mono.defer(() -> reactiveRepository.findById(id));
}
~~~

Với thao tác nhiều bước, nối các Publisher:

~~~java
public Mono<Session> updateLocale(String id, String locale) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new SessionMissingException()
            ))
            .flatMap(session -> {
                session.setAttribute("app.locale", locale);
                return repository.save(session).thenReturn(session);
            });
}
~~~

Ví dụ trên thể hiện việc tìm, cập nhật thuộc tính và lưu theo thứ tự. Trong handler WebFlux thông thường, nên cập nhật WebSession lấy từ exchange.getSession() để WebSessionManager quản lý response cookie và lưu trước commit. Gọi repository trực tiếp phù hợp hơn với service quản trị hoặc tác vụ backend đã có session ID và quy tắc quyền rõ ràng.

## 6. Dùng ReactiveRedisTemplate thay cho RedisTemplate imperative

Khi cần thao tác Redis tùy chỉnh, chọn ReactiveRedisTemplate hoặc ReactiveRedisOperations được xây dựng trên ReactiveRedisConnectionFactory. Các thao tác trả về Mono/Flux và có thể nối vào pipeline.

Phân biệt:

| API | Đặc điểm |
|---|---|
| RedisTemplate / StringRedisTemplate | API imperative; lệnh thường thực hiện đồng bộ và chặn |
| ReactiveRedisTemplate / ReactiveStringRedisTemplate | API reactive; thao tác trả về Publisher |
| ReactiveRedisConnectionFactory | Tạo kết nối Redis cho client reactive |
| ReactiveRedisOperations | Abstraction thao tác Redis theo kiểu reactive |

Ví dụ một thao tác key-value có TTL bằng ReactiveRedisTemplate:

~~~java
public Mono<Void> cacheSessionMetadata(
        ReactiveRedisTemplate<String, SessionMetadata> redis,
        String key,
        SessionMetadata metadata,
        Duration ttl) {

    return redis.opsForValue()
            .set(key, metadata, ttl)
            .flatMap(saved -> saved
                    ? Mono.empty()
                    : Mono.error(new IllegalStateException(
                            "Redis did not confirm the write"
                    )));
}
~~~

Đây chỉ là ví dụ một thao tác Redis reactive, không phải một repository Spring Session hoàn chỉnh. Repository session còn phải quản lý ID, metadata, thuộc tính, timeout, serialization, xóa và các cấu trúc phụ trợ. Không thể thay toàn bộ repository bằng một lệnh set key-value đơn giản rồi kỳ vọng mọi hành vi WebSession được đáp ứng.

Cấu hình serializer phải thống nhất giữa các instance. Với dữ liệu session, tránh lưu object tùy ý mà không có chính sách tương thích phiên bản. Chỉ lưu các kiểu nhỏ, có thể serialize và deserialize ổn định.

### Không trộn client reactive và imperative

Một lớp có thể vô tình dùng ReactiveRedisTemplate ở phương thức findById nhưng lại dùng RedisTemplate ở phương thức save. Khi đó một phần pipeline vẫn chặn.

Hãy kiểm tra toàn bộ đường đi:

- Kết nối được tạo từ ReactiveRedisConnectionFactory.
- Các thao tác key/hash/set/expire dùng API reactive.
- Không gọi RedisTemplate imperative ở giữa pipeline.
- Không gọi block(), blockFirst(), blockLast() hoặc chờ Future.
- Không dùng scheduler để che một API blocking nếu có API reactive tương ứng.

## 7. Nếu phải tự triển khai ReactiveSessionRepository

Chỉ tự triển khai repository khi repository có sẵn không đáp ứng yêu cầu về kho dữ liệu hoặc quy tắc lưu. Đây là phần có trách nhiệm lớn vì repository phải duy trì đầy đủ ngữ nghĩa session.

Một triển khai cần xác định:

1. Kiểu Session cụ thể và cách tạo ID an toàn.
2. Cách lưu creation time, last access time và max inactive interval.
3. Cách serialize từng thuộc tính và quản lý schema version.
4. Cách tìm session theo ID.
5. Cách refresh TTL khi session được truy cập và lưu.
6. Cách xóa session cùng dữ liệu phụ trợ.
7. Cách xử lý session hết hạn ngay cả khi cleanup vật lý chưa chạy.
8. Cách xử lý nhiều request cập nhật cùng session đồng thời.
9. Cách phân biệt not found với lỗi hạ tầng.
10. Cách bảo đảm các instance dùng cùng namespace, serializer và cấu hình.

Các phương thức phải có ngữ nghĩa nhất quán:

| Thao tác | Hành vi cần bảo đảm |
|---|---|
| createSession | Sinh ID không đoán được, thiết lập metadata và trả session chưa lưu hoặc theo contract đã chọn |
| findById | Trả Mono.empty khi session không tồn tại/hết hạn; phát lỗi khi kho dữ liệu không khả dụng |
| save | Ghi metadata, thuộc tính và TTL; chỉ hoàn tất khi thao tác lưu cần thiết hoàn tất |
| deleteById | Xóa session và các index/key phụ trợ liên quan |

Không tự tạo session ID bằng UUID trong controller. Dùng cơ chế ID của session implementation hoặc repository được thiết kế an toàn. Không lưu session ID trong URL hay log.

### Cấu trúc key và TTL

Nếu repository dùng Redis, cần thiết kế namespace riêng và quy ước key ổn định. Ví dụ minh họa:

~~~text
app:checkout:session:<session-id>
app:checkout:session-expiry:<session-id>
app:checkout:principal:<principal-key>
~~~

Đây chỉ là tên key ví dụ, không phải cấu trúc nội bộ Spring Session. Khi tự quản lý nhiều key, phải xử lý trường hợp ghi session thành công nhưng cập nhật TTL hoặc index thất bại.

Với một key đơn giản, ReactiveRedisTemplate có thể cung cấp thao tác set kèm Duration. Với nhiều key liên quan, chuỗi các Mono tuần tự không tự tạo transaction nguyên tử. Nếu yêu cầu nhất quán giữa session record, expiration và index, hãy dùng cơ chế atomic phù hợp như Lua script hoặc transaction Redis đã được kiểm chứng trên topology triển khai.

Trong Redis Cluster, các key tham gia cùng một script/transaction có thể cần cùng hash slot. Thiết kế hash tag trong key nếu thao tác atomic nhiều key đòi hỏi điều đó. Không dùng Mono.when để giả định nhiều lệnh Redis được thực hiện nguyên tử; Mono.when chỉ phối hợp completion của các Publisher.

## 8. Giữ đúng ngữ nghĩa timeout và expiration

Session có idle timeout. Về khái niệm:

~~~text
expiresAt = lastAccessTime + maxIdleTime
~~~

Khi session được sử dụng theo chính sách của repository, lastAccessTime có thể được cập nhật. Khi lưu session, repository phải áp dụng TTL mới. Nếu custom repository chỉ lưu hash mà quên refresh TTL, người dùng có thể bị đăng xuất sớm. Nếu quên đặt TTL, session có thể tồn tại vô thời hạn.

Cần phân biệt:

- **Logical expiration:** session không còn hợp lệ theo thời gian không hoạt động.
- **Physical deletion:** key hoặc record được xóa khỏi kho dữ liệu.
- **Expiration event:** thông báo được phát khi kho dữ liệu phát hiện key hết hạn.

Không phụ thuộc expiration event để quyết định quyền truy cập. findById phải kiểm tra tính hợp lệ của session theo repository contract, ngay cả khi key vật lý hoặc index phụ chưa được cleanup.

Với Redis, key expiration có thể được xử lý trễ so với thời điểm dự kiến. Với repository JDBC, cleanup có thể chạy theo lịch. Tùy kho dữ liệu, cần giữ cơ chế kiểm tra thời gian hết hạn độc lập với việc dọn dữ liệu nền.

## 9. Xử lý lỗi reactive đúng cách

Một repository tốt phân biệt lỗi nghiệp vụ với lỗi hạ tầng:

| Tình huống | Biểu diễn phù hợp |
|---|---|
| Session không tồn tại | Mono.empty() từ findById |
| Session đã hết hạn | Mono.empty() hoặc kết quả không hợp lệ theo contract |
| Redis timeout | onError |
| Redis authentication failure | onError và cảnh báo cấu hình |
| Serialization failure | onError, ghi nhận lỗi tương thích dữ liệu |
| Lưu session thất bại | onError; không phát ID như thể đã lưu thành công |
| Request bị hủy | Cancellation truyền xuống Publisher nếu client hỗ trợ |

Không viết:

~~~java
return repository.findById(id)
        .onErrorResume(error -> Mono.empty());
~~~

Đoạn code này biến mọi lỗi Redis, lỗi mạng và lỗi serialization thành “không tìm thấy session”. Hệ thống có thể hiểu nhầm người dùng đã đăng xuất hoặc tạo session mới, trong khi kho dữ liệu đang gặp sự cố.

Chỉ dùng onErrorResume cho lỗi đã xác định và có fallback an toàn. Nếu lỗi kho session làm ứng dụng không thể xác định trạng thái đăng nhập, API nhạy cảm nên thất bại rõ ràng theo chính sách hệ thống, thường là lỗi server thay vì tiếp tục như anonymous.

### Timeout và retry

Có thể đặt timeout cho thao tác repository:

~~~java
return repository.findById(id)
        .timeout(Duration.ofMillis(500));
~~~

Retry chỉ nên áp dụng cho lỗi tạm thời đã phân loại và với số lần hữu hạn:

~~~java
return repository.findById(id)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .filter(this::isTransientRedisFailure));
~~~

Không retry mọi lỗi. Không retry lỗi xác thực, lỗi schema hoặc lỗi deserialize như thể chúng sẽ tự hết. Đặc biệt, thao tác createSession có thể sinh ID mới; retry mù quáng có thể tạo nhiều session. Với save/delete, chỉ retry khi semantics và tính idempotent của implementation đã được xác nhận.

## 10. Không tự subscribe và không chặn pipeline

Ba lỗi phổ biến làm mất tính reactive:

**Gọi subscribe() bên trong repository**

~~~java
public Mono<Void> save(Session session) {
    redis.save(session).subscribe();
    return Mono.empty();
}
~~~

Publisher bên trong chạy độc lập với pipeline bên ngoài. WebFlux có thể hoàn tất response trước khi dữ liệu được lưu, lỗi bị tách khỏi request và cancellation không còn điều khiển được thao tác.

Hãy trả publisher cho caller:

~~~java
public Mono<Void> save(Session session) {
    return redis.save(session);
}
~~~

**Gọi block()**

~~~java
Session session = repository.findById(id).block();
~~~

Lệnh này chờ đồng bộ, có thể chặn event loop và làm giảm khả năng phục vụ đồng thời.

**Dùng API blocking rồi bọc Mono**

~~~java
return Mono.just(jdbcTemplate.queryForObject(sql, mapper));
~~~

Truy vấn JDBC đã chạy trước khi Mono được tạo. Mono.just không làm I/O thành non-blocking.

Nếu buộc phải tích hợp một API blocking cũ trong giai đoạn chuyển đổi, có thể cô lập lời gọi bằng Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()). Đây chỉ là cầu nối để tránh chặn event loop; thao tác bên dưới vẫn blocking, tiêu thụ thread và không phải một repository reactive thực sự. Với WebFlux session, ưu tiên ReactiveSessionRepository và client reactive.

## 11. Thứ tự, tính nguyên tử và cập nhật đồng thời

Một session có thể được truy cập từ nhiều request cùng lúc, ví dụ nhiều tab hoặc client gửi retry. Nếu custom repository lưu toàn bộ snapshot, request cũ có thể ghi đè thay đổi mới hơn.

Ví dụ:

1. Request A tải session version 4.
2. Request B cũng tải version 4.
3. B cập nhật locale và lưu version 5.
4. A cập nhật một thuộc tính khác rồi lưu snapshot cũ.
5. Nếu repository ghi đè toàn bộ session, thay đổi của B có thể bị mất.

Các cách giảm rủi ro:

- Tránh lưu object mutable lớn trong session.
- Dùng thuộc tính độc lập và cập nhật có chủ đích.
- Nếu cần kiểm soát ghi đồng thời, thêm version và compare-and-set hoặc Lua script.
- Dùng transaction database phù hợp nếu custom store là kho quan hệ reactive.
- Đưa dữ liệu nghiệp vụ cần tính nguyên tử vào database nghiệp vụ.
- Không dùng session làm bộ đếm thanh toán, tồn kho hoặc nguồn sự thật cho giao dịch.

Một chuỗi reactive tuần tự chỉ bảo đảm thứ tự trong pipeline đó. Nó không tự khóa session giữa nhiều request hoặc nhiều instance.

## 12. Tích hợp custom repository với WebSessionManager

Khi chỉ bọc repository hiện có, giữ nguyên WebSessionManager và resolver để framework tiếp tục điều phối vòng đời request/response.

Khi thay hoàn toàn repository, cần bảo đảm WebSessionStore hoặc cấu hình WebSessionManager dùng đúng ReactiveSessionRepository mới. Cách đăng ký cụ thể phụ thuộc phiên bản Spring Framework/Spring Session; kiểm tra API của phiên bản dự án và tránh tạo manager thứ hai ngoài ý muốn.

Các nguyên tắc tích hợp:

- WebSessionManager chỉ có một đường quản lý session rõ ràng.
- Repository mới thực hiện đủ create/find/save/delete reactive contract.
- Resolver vẫn là thành phần duy nhất đọc và phát session ID.
- Session được lưu trước response commit.
- Nếu save thất bại, lỗi phải truyền vào quá trình commit; không phát ID trỏ tới dữ liệu chưa lưu.
- Invalidate phải xóa session và dữ liệu phụ trợ.
- Các instance dùng chung namespace, serializer và timeout.
- Không đăng ký đồng thời @EnableRedisWebSession và một repository/manager độc lập có cùng trách nhiệm nếu chưa kiểm soát rõ cấu hình.

Không tự ghi cookie từ repository. Repository quản lý dữ liệu; resolver quản lý định danh client. Giữ ranh giới này giúp tránh phát hành ID trước khi session được lưu hoặc phát cookie sai Domain/Path.

## 13. Principal index và chức năng quản trị

Một số ứng dụng cần tìm tất cả session theo principal để hiển thị thiết bị hoặc thu hồi session. Không giả định mọi reactive Redis repository có cùng API index như RedisIndexedSessionRepository của mô hình Servlet. Hãy kiểm tra implementation và phiên bản đang dùng.

Nếu repository reactive không cung cấp principal index, có thể xây dựng index phụ bằng ReactiveRedisOperations. Khi làm vậy, cần:

- Dùng principal name đã được xác thực ở phía server.
- Chuẩn hóa định danh và tránh dữ liệu cá nhân trong key nếu không cần thiết.
- Cập nhật index cùng lúc với session save/delete.
- Có TTL hoặc cleanup để loại bỏ session ID cũ.
- Xử lý principal đổi tên và session hết hạn.
- Kiểm tra ownership trước khi thu hồi session.
- Dùng thao tác atomic khi cập nhật session key và index nếu yêu cầu nhất quán cao.

Không lấy principal name trực tiếp từ request rồi dùng làm key. Không trả session ID ra API quản trị nếu có thể dùng handle riêng. Mọi endpoint liệt kê hoặc thu hồi session cần kiểm soát quyền và audit phù hợp.

## 14. Kiểm thử repository reactive

Unit test nên dùng StepVerifier để kiểm tra tín hiệu Mono, thay vì gọi block() trong test logic chính.

Ví dụ kiểm tra session được tìm thấy:

~~~java
StepVerifier.create(repository.findById(sessionId))
        .assertNext(session -> {
            assertThat(session.getId()).isEqualTo(sessionId);
            assertThat(session.getAttribute("app.locale"))
                    .isEqualTo("vi-VN");
        })
        .verifyComplete();
~~~

Kiểm tra session không tồn tại:

~~~java
StepVerifier.create(repository.findById("missing-session"))
        .verifyComplete();
~~~

Kiểm tra lỗi được truyền ra:

~~~java
StepVerifier.create(repository.save(session))
        .expectError()
        .verify();
~~~

Không chỉ kiểm tra giá trị trả về. Cần xác nhận operation thực sự được subscribe và hoàn tất trước khi response commit.

### Integration test với Redis thật

Dùng Redis test instance hoặc Testcontainers để kiểm tra:

| Ca kiểm thử | Điều cần xác nhận |
|---|---|
| Create và save | Session được lưu và có thể tìm lại |
| Find miss | ID không tồn tại trả Mono.empty |
| Update | Thuộc tính mới được lưu đúng |
| Delete | Session và index phụ trợ bị xóa |
| TTL | Session hết hạn theo maxIdleTime |
| Serialization | Dữ liệu đọc lại đúng kiểu và schema |
| Redis outage | Lỗi được truyền, không biến thành empty |
| Timeout | Pipeline kết thúc trong thời hạn đã cấu hình |
| Cancellation | Hủy request không để thao tác nền tự subscribe ngoài luồng |
| Concurrent update | Không có mất cập nhật ngoài chính sách đã chấp nhận |
| Cross-instance | Node A lưu, node B đọc cùng session |
| Response commit | Cookie/header chỉ được phát khi save thành công |

WebTestClient kiểm thử HTTP và response resolver; StepVerifier kiểm thử publisher ở tầng repository. Hai loại test bổ sung cho nhau.

### Phát hiện blocking call

Có thể dùng BlockHound trong test hoặc môi trường kiểm thử để phát hiện một số lời gọi blocking trên Reactor thread. Kết quả cần được phân tích vì một số thư viện có thể có hành vi nội bộ đặc biệt. BlockHound không thay thế code review, nhưng hữu ích để phát hiện vô tình gọi JDBC, Thread.sleep hoặc API blocking trong pipeline.

## 15. Quan sát và vận hành nhiều instance

Khi tùy chỉnh repository, metric nên phản ánh hiệu năng và độ tin cậy mà không làm lộ dữ liệu session.

Các chỉ số hữu ích:

- Số thao tác create/find/save/delete.
- Tỷ lệ find miss so với find success.
- Tỷ lệ lỗi Redis theo nhóm nguyên nhân.
- Độ trễ p50/p95/p99 của từng thao tác.
- Timeout và retry count.
- Số session hết hạn hoặc bị xóa.
- Kích thước payload session và số thuộc tính nếu đo được an toàn.
- Tình trạng connection pool và Redis health.
- Số lỗi serialization và lỗi schema compatibility.

Không dùng session ID, cookie, token hoặc principal name làm metric label. Log nên dùng correlation ID và outcome tổng quát.

Trong cụm nhiều instance, mọi node phải thống nhất:

- Redis endpoint/cluster và credential.
- Namespace và quy ước key.
- Serializer và schema version.
- Timeout và cách refresh TTL.
- Chính sách SaveMode/FlushMode nếu repository có hỗ trợ.
- Cách cập nhật index và xử lý expiration.

Nếu một node dùng namespace khác hoặc serializer khác, người dùng có thể gặp lỗi ngẫu nhiên theo node nhận request. Hãy kiểm tra cấu hình runtime của tất cả instance trong rollout.

## 16. Lỗi thường gặp khi tùy chỉnh repository

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Event loop bị nghẽn | Dùng RedisTemplate/JdbcTemplate hoặc block() | Chuyển sang client reactive và nối Publisher |
| Request trả về trước khi session được lưu | Repository tự subscribe và trả Mono.empty | Trả Publisher cho WebFlux quản lý |
| Redis outage bị coi là đăng xuất | onErrorResume biến mọi lỗi thành Mono.empty | Phân biệt miss với lỗi hạ tầng |
| Session không hết hạn | Không refresh TTL hoặc không áp dụng maxIdleTime | Kiểm tra save và expiration logic |
| Cookie trỏ tới session không tồn tại | Resolver phát ID trước khi save hoàn tất | Để manager lưu xong rồi mới phát ID |
| Index principal tồn tại lâu | Delete/expiration không dọn index | Cập nhật index cùng lifecycle và có cleanup |
| Mất thuộc tính khi request đồng thời | Ghi đè snapshot cũ | Dùng version/CAS hoặc giảm trạng thái mutable |
| Nhiều instance đọc khác nhau | Namespace/serializer/timeout không đồng nhất | Đồng bộ cấu hình và kiểm thử cross-instance |
| Retry tạo nhiều session | Retry create không có tính idempotent | Thiết kế idempotency hoặc không retry thao tác tạo |
| Metric tăng cardinality | Gắn session ID/principal vào label | Chỉ dùng label hữu hạn như operation/outcome |

Khi điều tra, xác định publisher có được subscribe không, lệnh Redis có hoàn tất không, lỗi được phát hay bị nuốt, TTL có được đặt và response có commit sau khi lưu thành công không.

## 17. Checklist trước khi phát hành custom reactive repository

- Đã xác định cấu hình repository có sẵn không đáp ứng yêu cầu nào.
- Đã ưu tiên decorator/composition nếu chỉ cần metric, audit hoặc validation.
- Repository triển khai đúng ReactiveSessionRepository contract.
- Tất cả I/O dùng ReactiveRedisOperations hoặc API reactive tương ứng.
- Không dùng RedisTemplate imperative, JDBC blocking hoặc block() trong event loop.
- Không gọi subscribe() bên trong repository.
- Mono.defer được dùng khi cần trì hoãn lời gọi delegate.
- Mono.empty chỉ biểu diễn session không tồn tại/hết hạn.
- Lỗi Redis, timeout và serialization được truyền rõ ràng.
- Save hoàn tất trước khi WebSessionManager phát session ID.
- TTL và lastAccessTime được cập nhật đúng.
- Delete dọn session cùng index/key phụ trợ.
- Đã xem xét cập nhật đồng thời và tính nguyên tử nhiều key.
- Serializer tương thích giữa các phiên bản.
- Tất cả instance dùng cùng namespace và cấu hình.
- Có StepVerifier, WebTestClient, Redis integration test và kiểm tra blocking.
- Metric/log không chứa session ID, cookie hoặc principal nhạy cảm.

Tùy chỉnh repository trong WebFlux không chỉ là đổi kiểu trả về thành Mono. Mọi I/O phải thực sự reactive, lỗi và cancellation phải được giữ trong pipeline, còn vòng đời session—ID, TTL, serialization, index và xóa dữ liệu—phải được duy trì đầy đủ. Bắt đầu bằng cấu hình có sẵn hoặc decorator khi có thể; chỉ tự triển khai ReactiveSessionRepository khi cần kiểm soát storage semantics. Cách làm này giữ cho WebFlux không phải chờ thao tác blocking và giúp session hoạt động nhất quán qua nhiều request, nhiều instance và nhiều lần triển khai.

## Tài liệu tham khảo

- [Spring Session — WebFlux Integration](https://docs.spring.io/spring-session/reference/web-session.html)
- [Spring Session — ReactiveSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/ReactiveSessionRepository.html)
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Framework — Reactive Redis Support](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html)
- [Project Reactor — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)

