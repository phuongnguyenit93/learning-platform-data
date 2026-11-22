# ReactiveRedisTemplate và ReactiveRedisConnectionFactory

## 1. Vị trí của hai thành phần trong kiến trúc Spring Data Redis

Khi một ứng dụng Spring WebFlux cần đọc/ghi Redis theo cách **không chặn luồng xử lý trong lúc chờ I/O** (non-blocking I/O), Spring Data Redis cung cấp hai thành phần quan trọng:

- **ReactiveRedisTemplate<K, V>**: API cấp cao để ứng dụng thao tác với key/value, hash, set, sorted set, list, stream và những cấu trúc dữ liệu Redis khác theo mô hình Reactor.
- **ReactiveRedisConnectionFactory**: hợp đồng cấp hạ tầng để tạo/cung cấp **reactive Redis connection** cho tầng thao tác dữ liệu. Nó tách code sử dụng Redis khỏi chi tiết driver và cách thiết lập kết nối.

Quan hệ kiến trúc có thể hình dung như sau:

~~~text
HTTP request / event / reactive pipeline
               |
               v
      Controller / Service
          Mono / Flux
               |
               v
 ReactiveRedisTemplate<K, V>
   - Redis operations
   - key/value serialization
   - error & result mapping
               |
               v
 ReactiveRedisConnectionFactory
   - cung cấp reactive connection
               |
               v
        Lettuce Redis driver
               |
          Redis server
~~~

Thông thường **service nên phụ thuộc vào template** thay vì tự quản lý kết nối, buffer dữ liệu và serializer. **Connection factory** thường được cấu hình một lần ở tầng ứng dụng rồi được Spring inject vào template.

Tên gọi gần giống nhau nhưng vai trò khác nhau: factory trả lời câu hỏi *“lấy kết nối reactive tới Redis qua đâu?”*, còn template trả lời câu hỏi *“thao tác với dữ liệu Redis bằng API nào, dùng serializer nào và nhận kết quả Reactor ra sao?”*.

## 2. Reactive ở đây có ý nghĩa gì?

Trong Spring Data Redis, API reactive trả kết quả bằng các kiểu **Project Reactor**:

| Kiểu | Ý nghĩa | Ví dụ thao tác Redis |
|---|---|---|
| **Mono<T>** | Luồng phát ra tối đa một kết quả rồi hoàn tất, hoặc hoàn tất rỗng, hoặc lỗi | Đọc một key: **Mono<String>** |
| **Mono<Boolean>** | Một kết quả cho biết thao tác thành công theo ngữ nghĩa API | **SET** giá trị |
| **Mono<Long>** | Một giá trị số, ví dụ số lượng hoặc bộ đếm | **INCR**, **DEL** |
| **Flux<T>** | Luồng có thể phát nhiều phần tử | **SCAN** nhiều key, đọc dòng phần tử |

Ví dụ:

~~~java
Mono<String> value = reactiveStringRedisTemplate
    .opsForValue()
    .get("profile:42:name");
~~~

Ở đây **value** là một mô tả của phép đọc dưới dạng **Mono**. Code tạo ra biến này không đồng nghĩa ứng dụng đã đồng bộ chờ và lấy xong dữ liệu. Với publisher lạnh (cold publisher) điển hình của thao tác Redis, lệnh được kích hoạt khi pipeline có subscriber.

~~~java
Mono<String> result = reactiveStringRedisTemplate
    .opsForValue()
    .get("profile:42:name")
    .map(String::toUpperCase)
    .defaultIfEmpty("CHƯA CÓ TÊN");

// Không gọi block() trong đường xử lý request WebFlux.
// Trả Mono cho WebFlux để framework subscribe và gửi HTTP response.
return result;
~~~

Khi request được xử lý, Reactor truyền kết quả tiếp qua các operator **map**, **flatMap**, **switchIfEmpty**, **onErrorResume**... mà không yêu cầu thread đang xử lý request đứng chờ một kết nối Redis trả lời theo kiểu đồng bộ.

**Non-blocking** không có nghĩa Redis xử lý mọi lệnh song song, cũng không có nghĩa kết quả luôn nhanh hơn. Lợi ích chính là trong thời gian chờ I/O, hệ thống có thể sử dụng thread hiệu quả hơn khi nhiều request đang diễn ra.

### Khác nhau giữa imperative và reactive

~~~java
// Imperative: đọc trả về giá trị trực tiếp; lời gọi chờ I/O hoàn tất.
String name = stringRedisTemplate.opsForValue().get("profile:42:name");

// Reactive: đọc trả về publisher mô tả kết quả trong tương lai.
Mono<String> namePublisher = reactiveStringRedisTemplate
    .opsForValue()
    .get("profile:42:name");
~~~

**StringRedisTemplate** và **ReactiveStringRedisTemplate** không phải hai cách đặt tên cho cùng một hành vi. Một bên có API đồng bộ, một bên cung cấp API Reactor và dùng hạ tầng reactive tương ứng.

## 3. ReactiveRedisConnectionFactory: ranh giới kết nối

**ReactiveRedisConnectionFactory** là interface thuộc Spring Data Redis. Nó cung cấp kết nối thấp hơn template, qua đó các Redis command có thể thực thi theo mô hình reactive.

Một triển khai quen thuộc là **LettuceConnectionFactory**. Khi sử dụng Lettuce, cùng loại factory này có thể phục vụ cả API Redis imperative lẫn reactive vì Lettuce hỗ trợ kết nối bất đồng bộ/non-blocking.

Tại tầng thiết kế:

1. **Spring Boot** đọc cấu hình Redis và quản lý các bean kết nối nếu auto-configuration phù hợp.
2. **LettuceConnectionFactory** nắm cấu hình máy chủ, xác thực, topology và tài nguyên client.
3. **ReactiveRedisTemplate** nhận factory và serialization context qua constructor.
4. **Service** inject template và nối các phép thao tác thành **Mono/Flux**.

Không tạo một **LettuceConnectionFactory** mới trong mỗi phương thức service hoặc mỗi request. Factory và các tài nguyên kết nối đi kèm nên được Spring quản lý theo vòng đời ứng dụng.

### Tại sao không inject trực tiếp connection vào mọi service?

API cấp connection hữu ích khi cần thao tác cấp thấp không được template bao bọc hoặc đang xây dựng một infrastructure adapter chuyên biệt. Nhưng khi tự thao tác trực tiếp, ứng dụng phải chịu trách nhiệm chi tiết codec, command result, quản lý tài nguyên/phiên và nhiều quy tắc xử lý lỗi.

Template đã cung cấp abstraction thống nhất cho phần lớn thao tác dữ liệu thông thường. Vì vậy service nghiệp vụ thường chỉ cần phụ thuộc vào **ReactiveRedisTemplate<K, V>** hoặc **ReactiveStringRedisTemplate**.

### Chọn Lettuce cho Reactive Redis

Với Spring Data Redis, **Lettuce** là lựa chọn driver phổ biến hỗ trợ reactive. Không nên suy luận rằng bất kỳ **RedisConnectionFactory** nào cũng tự động dùng được làm **ReactiveRedisConnectionFactory**: driver và implementation phải thực sự hỗ trợ contract reactive.

Khi ứng dụng sử dụng Redis Cluster hoặc Sentinel, factory cũng là nơi phối hợp cấu hình topology và driver, nhưng điều đó không biến nhiều Redis node thành một giao dịch chung.

## 4. Cấu hình ứng dụng Spring Boot

Trong project Spring Boot dùng Gradle, có thể khai báo starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
~~~

Starter tương ứng đưa Spring Data Redis và driver phù hợp vào dependency graph. Reactor cũng cần có mặt trong application, thường đã được kéo vào qua WebFlux hoặc starter reactive.

Ví dụ cấu hình kết nối cho Redis chạy ở máy phát triển:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Trong môi trường thực tế, thiết lập thêm mật khẩu/TLS, topology Cluster hoặc Sentinel, timeout, monitoring và quyền truy cập mạng theo kiến trúc vận hành. Không nhúng credential vào source code.

Khi auto-configuration được áp dụng và điều kiện về bean/dependency thỏa mãn, Spring Boot có thể cung cấp factory Lettuce và các Redis template chuẩn. Vì vậy nhiều ứng dụng không cần tự tạo connection factory.

Một service làm việc với chuỗi có thể inject **ReactiveStringRedisTemplate** trực tiếp:

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class VisitCounterService {
    private final ReactiveStringRedisTemplate redis;

    public VisitCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increment(String pageId) {
        return redis.opsForValue().increment("page:views:" + pageId);
    }

    public Mono<String> readRaw(String pageId) {
        return redis.opsForValue().get("page:views:" + pageId);
    }
}
~~~

**increment** là một lệnh tăng ở Redis, nên không gặp lỗi mất cập nhật do tự thực hiện **GET → tính toán → SET** bên Java. Đổi lại, API vẫn có thể phát lỗi nếu Redis không khả dụng hoặc dữ liệu đang chứa chuỗi không phải số nguyên.

## 5. ReactiveRedisTemplate: abstraction thao tác dữ liệu có kiểu

**ReactiveRedisTemplate<K, V>** tách hai lớp trách nhiệm:

**Tầng thao tác dữ liệu**

~~~java
redis.opsForValue();
redis.opsForHash();
redis.opsForList();
redis.opsForSet();
redis.opsForZSet();
redis.opsForStream();
~~~

**Tầng tuần tự hóa (serialization)**

- Java key được chuyển thành bytes gửi tới Redis.
- Java value được chuyển thành bytes theo serializer đã cấu hình.
- Dữ liệu trả về từ Redis được giải mã thành kiểu Java mong đợi.

Redis không lưu một đối tượng Java theo kiểu gốc. **String**, JSON hoặc binary format thực chất đều được biểu diễn bằng bytes. Cặp generic **<K, V>** không tự động đảm bảo dữ liệu trong Redis tương thích với serializer; schema và định dạng của các client vẫn cần được thống nhất.

### ReactiveStringRedisTemplate và ReactiveRedisTemplate khác nhau ở đâu?

**ReactiveStringRedisTemplate** là biến thể tiện dụng cho key/value dạng chuỗi, sử dụng các serializer chuỗi tương ứng. Nó phù hợp với counter, marker, token hoặc các giá trị nhỏ mà service muốn chủ động chuyển đổi thành String.

**ReactiveRedisTemplate<K, V>** thích hợp khi ứng dụng muốn ánh xạ value sang một DTO hay kiểu dữ liệu khác thông qua **RedisSerializationContext**.

| Tiêu chí | ReactiveStringRedisTemplate | ReactiveRedisTemplate<K, V> |
|---|---|---|
| Key/value thông thường | String/String | Tùy serializer và generic |
| Cấu hình | Thường dùng bean chuẩn | Có thể cần tự cấu hình context |
| Trường hợp quen thuộc | Counter, key text, flag | Object JSON, dữ liệu domain |
| Kiểu kết quả | Mono/Flux | Mono/Flux |
| Nguồn kết nối | ReactiveRedisConnectionFactory | ReactiveRedisConnectionFactory |

Hai template đều là abstraction ở tầng application; chúng không thay thế connection factory.

## 6. Tạo một ReactiveRedisTemplate có serializer riêng

Giả sử dữ liệu session được lưu ở Redis dưới dạng JSON với key là chuỗi. Có thể định nghĩa DTO:

~~~java
public record SessionPayload(
    String userId,
    String displayName
) {}
~~~

Sau đó tạo template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ReactiveSessionRedisConfig {

    @Bean
    public ReactiveRedisTemplate<String, SessionPayload> sessionRedisTemplate(
            ReactiveRedisConnectionFactory connectionFactory) {

        var keySerializer = new StringRedisSerializer();
        var valueSerializer =
            new Jackson2JsonRedisSerializer<>(SessionPayload.class);

        RedisSerializationContext<String, SessionPayload> context =
            RedisSerializationContext
                .<String, SessionPayload>newSerializationContext(keySerializer)
                .value(valueSerializer)
                .build();

        return new ReactiveRedisTemplate<>(connectionFactory, context);
    }
}
~~~

Trong cấu hình trên:

1. **ReactiveRedisConnectionFactory** xác định cách template nhận kết nối reactive.
2. **StringRedisSerializer** chuyển key kiểu String thành bytes có thể quan sát/tra cứu trong Redis.
3. **Jackson2JsonRedisSerializer** chuyển **SessionPayload** sang JSON và đọc lại theo loại đối tượng đã định nghĩa.
4. **RedisSerializationContext** cung cấp các serializer mà template sử dụng.
5. **ReactiveRedisTemplate** kết hợp connection factory với serialization context để triển khai các Redis operations.

Ví dụ chỉ thiết lập serializer value vì service dưới đây dùng **opsForValue()**. Nếu thao tác với hash, cần xác định rõ serializer cho **hash key** và **hash value**; nếu ứng dụng có nhiều DTO hoặc định dạng dữ liệu, hãy thiết kế cách phân tách key/serializer tương ứng.

JSON giúp quan sát dữ liệu và làm việc với nhiều ngôn ngữ lập trình, nhưng vẫn phải quản lý thay đổi schema, kiểu dữ liệu, tương thích giữa phiên bản và các trường có thông tin nhạy cảm. Không giả định serializer Java mặc định của mọi template là JSON.

### Dùng template trong service

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SessionStore {
    private final ReactiveRedisTemplate<String, SessionPayload> redis;

    public SessionStore(
            ReactiveRedisTemplate<String, SessionPayload> redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(
            String sessionId,
            SessionPayload payload,
            Duration ttl) {
        return redis.opsForValue()
            .set("session:" + sessionId, payload, ttl);
    }

    public Mono<SessionPayload> find(String sessionId) {
        return redis.opsForValue().get("session:" + sessionId);
    }

    public Mono<Long> delete(String sessionId) {
        return redis.delete("session:" + sessionId);
    }
}
~~~

Trong **save**, TTL được chuyển vào cùng thao tác **SET** thay vì tạo giá trị rồi mới gọi **EXPIRE** ở một bước riêng. **find** phát **Mono.empty()** khi key không tồn tại; đây là kết quả bình thường, khác với một lỗi kết nối Redis.

## 7. Ghép các thao tác Redis thành reactive pipeline

Các operator Reactor làm rõ luồng điều khiển mà không cần **block()**:

~~~java
public Mono<SessionPayload> updateDisplayName(
        String sessionId,
        String newName) {

    return redis.opsForValue()
        .get("session:" + sessionId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Session not found")))
        .flatMap(oldValue -> {
            SessionPayload updated =
                new SessionPayload(oldValue.userId(), newName);

            return redis.opsForValue()
                .set("session:" + sessionId, updated, Duration.ofMinutes(30))
                .thenReturn(updated);
        });
}
~~~

Mỗi request đi theo luồng:

~~~text
get(key) ──► Mono<SessionPayload>
                │
                ├─ empty ─► not-found error
                │
                └─ value ─► tạo SessionPayload mới
                               │
                               ▼
                       set(key, updated, ttl)
                               │
                               ▼
                       Mono<SessionPayload>
~~~

**Cảnh báo về race condition:** ví dụ này thể hiện cách phối hợp các publisher, **không bảo đảm cập nhật nguyên tử** giữa GET và SET. Nếu hai request cùng đọc và thay đổi một phiên, request chạy sau có thể ghi đè cập nhật của request trước. Khi nghiệp vụ cần kiểm tra và ghi là một đơn vị không bị xen vào, hãy thiết kế **Lua script/Redis Function** hoặc cơ chế điều kiện phù hợp như **WATCH + MULTI/EXEC**, tuân thủ hỗ trợ của reactive API và phạm vi Redis deployment.

Việc sử dụng **flatMap** chỉ đảm bảo sự phụ thuộc theo luồng dữ liệu trong một subscription; nó không tạo khóa phân tán, giao dịch hay tính tuần tự giữa những subscriber khác nhau.

### Ví dụ expose Mono qua WebFlux

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/sessions")
public class SessionController {
    private final SessionStore store;

    public SessionController(SessionStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<SessionPayload>> find(
            @PathVariable String id) {

        return store.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

Controller trả về publisher và để WebFlux thực hiện subscription theo vòng đời HTTP request. Không cần gọi **subscribe()** thủ công trong controller hoặc service chỉ để “làm cho Redis chạy”.

## 8. Vòng đời publisher, subscription và backpressure

Một điểm dễ nhầm là:

~~~java
Mono<Boolean> action =
    reactiveStringRedisTemplate.opsForValue().set("flag:ready", "yes");
~~~

Nếu biến **action** chỉ được tạo ra rồi bỏ qua, không có subscriber tiêu thụ publisher, thao tác thường sẽ chưa được phát lệnh. Cần **return action** cho framework, ghép nó vào pipeline khác bằng **then/flatMap**, hoặc có subscriber do hệ thống quản lý trong trường hợp chủ động tạo subscription.

~~~java
public Mono<String> writeThenRead() {
    return reactiveStringRedisTemplate.opsForValue()
        .set("flag:ready", "yes")
        .then(reactiveStringRedisTemplate.opsForValue().get("flag:ready"));
}
~~~

**then** đợi publisher ghi hoàn tất thành công trước khi chuyển sang publisher đọc. Ngược lại, tạo hai Mono độc lập rồi trả về một Mono bất kỳ sẽ không bảo đảm publisher còn lại được tiêu thụ.

Trong mô hình Reactor:

- **Subscription** kích hoạt pipeline.
- **Cancellation** thông báo không còn cần kết quả; không nên xem cancellation là lệnh hoàn tác một thay đổi đã được Redis thực thi.
- **Backpressure** cho phép subscriber yêu cầu lượng dữ liệu phù hợp khi tiêu thụ **Flux**, nhưng không biến mọi Redis command thành một nguồn có thể tạm dừng tức thời hoặc đảo ngược sau khi gửi. Cần cân nhắc bộ nhớ, số lệnh đang chờ và cách driver nhận/phát phản hồi.
- **Concurrency** do các operator như **flatMap** tạo ra có thể mở nhiều thao tác Redis cùng lúc; số lượng request và độ nóng của key vẫn cần giới hạn phù hợp.

Ví dụ quét key theo luồng:

~~~java
import org.springframework.data.redis.core.ScanOptions;
import reactor.core.publisher.Flux;

public Flux<String> scanProfileKeys() {
    return reactiveStringRedisTemplate.scan(
        ScanOptions.scanOptions()
            .match("profile:*")
            .count(100)
            .build()
    );
}
~~~

**SCAN** là thao tác duyệt theo cursor, thích hợp hơn việc dùng **KEYS** để lấy toàn bộ key trong một lần trên Redis lớn. **COUNT** chỉ là gợi ý về khối lượng quét, không phải số lượng kết quả được bảo đảm; quá trình quét có thể gặp phần tử lặp hoặc thay đổi khi dữ liệu đang bị sửa. Với Cluster, cần hiểu phạm vi node và hỗ trợ scan của client.

## 9. Lỗi, timeout và dữ liệu rỗng

Cần phân biệt tối thiểu ba đường xử lý:

| Trạng thái | Ví dụ | Cách tiếp cận |
|---|---|---|
| **Có dữ liệu** | GET thành công | Map thành DTO hoặc HTTP 200 |
| **Không có dữ liệu** | Key không tồn tại, **Mono.empty()** | **switchIfEmpty** hoặc **defaultIfEmpty** |
| **Lỗi** | Redis mất kết nối, timeout, sai kiểu dữ liệu | Xử lý **onErrorMap/onErrorResume**, log/metrics phù hợp |

Ví dụ ánh xạ không tìm thấy thành fallback:

~~~java
public Mono<String> nickname(String userId) {
    return reactiveStringRedisTemplate.opsForValue()
        .get("nickname:" + userId)
        .defaultIfEmpty("anonymous");
}
~~~

Nếu Redis gặp lỗi kết nối, **defaultIfEmpty** không nuốt lỗi; nó chỉ xử lý publisher hoàn tất mà không phát giá trị.

Ví dụ giới hạn thời gian chờ tại tầng reactive:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

public Mono<String> readWithTimeout(String key) {
    return reactiveStringRedisTemplate.opsForValue()
        .get(key)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
            error -> Mono.error(
                new IllegalStateException("Redis read timed out", error)));
}
~~~

Timeout ở pipeline giới hạn thời gian mà **subscriber chờ kết quả**; nếu một lệnh ghi đã đến Redis, việc timeout/cancel ở phía client không chứng minh lệnh chưa được thực thi. Khi tự động retry lệnh tạo tác dụng phụ, phải xét idempotency, yêu cầu nghiệp vụ và khả năng xử lý trùng.

Trong thực tế nên cấu hình timeout ở driver/connection và ở request pipeline có chủ đích; không dùng **onErrorResume** để thay thế mọi lỗi bằng một dữ liệu giả nếu điều đó có thể làm ứng dụng hiểu sai trạng thái lưu trữ.

## 10. Transaction và tính nguyên tử trong reactive Redis

Reactive không thay đổi tính chất nguyên tử cơ bản của lệnh Redis. Một lệnh **INCR** vẫn là thao tác tăng nguyên tử tại server, còn chuỗi reactive **get().flatMap(...set(...))** vẫn là hai lệnh độc lập.

Ba loại hành vi dễ bị nhầm:

| Cơ chế | Bảo đảm chính | Điều không tự bảo đảm |
|---|---|---|
| **Mono/Flux + flatMap/then** | Thứ tự phụ thuộc trong pipeline | Nguyên tử giữa nhiều command |
| **Một Redis command** | Một command hoàn tất không bị command khác chen vào trên instance xử lý | Giao dịch gồm nhiều thao tác Java |
| **MULTI/EXEC** | Redis thực thi lệnh đã queue liên tiếp, không bị command từ client khác chen vào | Rollback nếu một command bị lỗi khi thực thi |
| **WATCH + MULTI/EXEC** | Phát hiện key bị thay đổi và hủy transaction trước EXEC | Thành công sau mọi lần retry; rollback lỗi runtime |
| **Lua script / Redis Function** | Điều kiện và cập nhật trong một lần thực thi server | Rollback sau khi script đã ghi rồi gặp lỗi |

Reactive API không khiến một method gắn **@Transactional** tự động trở thành distributed transaction giữa Redis, database và message broker. Cơ chế transaction, khả năng hỗ trợ ở từng tầng Redis API và vòng đời connection cần được lựa chọn, cấu hình rõ ràng.

Nếu service cần “trừ tồn kho chỉ khi còn đủ”, hãy đánh giá một thao tác server-side nguyên tử; nếu service chỉ cần tăng bộ đếm, dùng **increment** thay vì triển khai giao dịch phức tạp.

## 11. Các lỗi kiến trúc thường gặp

### 11.1. Gọi block() trong chuỗi xử lý WebFlux

~~~java
// Không nên trong controller hoặc service đang chạy trên event-loop:
String value = reactiveStringRedisTemplate
    .opsForValue()
    .get("key")
    .block();
~~~

**block()** chuyển việc chờ kết quả thành kiểu đồng bộ, có thể chặn thread và còn bị Reactor từ chối trên một số thread không cho blocking. Trả lại **Mono** hoặc ghép dữ liệu bằng operator reactive thường là lựa chọn đúng.

### 11.2. Tự subscribe() rồi bỏ qua kết quả

~~~java
// Có nguy cơ mất quản lý lỗi và vòng đời:
reactiveStringRedisTemplate.opsForValue()
    .set("flag", "ready")
    .subscribe();
~~~

Lệnh được khởi chạy tách khỏi kết quả caller đang chờ; lỗi có thể không đến được luồng xử lý HTTP, cancellation và tracing cũng khó theo dõi hơn. Đối với nghiệp vụ request-response, **return Mono** để caller/framework quản lý subscription.

### 11.3. Dùng serializer không đồng nhất

Một template ghi đối tượng bằng JSON, template khác dùng Java native serialization hoặc string serializer để đọc cùng key. Dữ liệu Redis có thể vẫn tồn tại nhưng deserialization thất bại hoặc giá trị được hiểu sai. Cần thống nhất **key prefix, serializer, kiểu value, thời hạn và định dạng schema** ở những nơi cùng dùng dữ liệu.

### 11.4. Coi reactive là phương án bảo đảm atomicity

~~~java
return reactiveStringRedisTemplate.opsForValue()
    .get("stock")
    .flatMap(current -> {
        long remaining = Long.parseLong(current) - 1;
        return reactiveStringRedisTemplate.opsForValue()
            .set("stock", Long.toString(remaining));
    });
~~~

Đoạn này non-blocking nhưng vẫn có race condition. Non-blocking I/O, thread safety của template và atomicity của nghiệp vụ là **ba thuộc tính khác nhau**.

### 11.5. Dùng Redis Cluster mà không chú ý hash slot

Khi cần thao tác nhiều key cùng lúc bằng Redis command hoặc script, cluster có các ràng buộc về hash slot. Key như **cart:{user42}:items** và **cart:{user42}:total** có thể được thiết kế cùng hash tag để nằm cùng slot; việc đặt tên key có chủ đích thuộc trách nhiệm thiết kế dữ liệu, không phải template tự giải quyết toàn bộ.

### 11.6. Dùng reactive khi toàn bộ đường đi vẫn blocking

Nếu controller gọi Redis reactive rồi lập tức **block()**, sau đó gọi JDBC hoặc tác vụ file sync trên event loop, ứng dụng không thu được lợi ích kiến trúc mong muốn. Một luồng reactive hiệu quả cần xem xét cả controller, service, client và các phần xử lý dữ liệu liên quan.

Không nhất thiết toàn hệ thống phải chuyển sang reactive. Lựa chọn imperative hay reactive nên dựa trên kiến trúc ứng dụng và đặc điểm tải; **ReactiveRedisTemplate** phù hợp nhất khi đường xử lý đã sử dụng Reactor/WebFlux hoặc cần tích hợp tự nhiên với reactive pipeline.

## 12. Thiết kế service và vận hành thực tế

Một cách tổ chức dễ bảo trì:

~~~text
Spring Boot configuration
  ├─ Redis connection properties
  ├─ LettuceConnectionFactory
  │    └─ ReactiveRedisConnectionFactory
  └─ ReactiveRedisTemplate<String, DTO>
       └─ RedisSerializationContext

Application service
  ├─ kiểm tra đầu vào
  ├─ gọi template operations
  ├─ compose Mono/Flux
  └─ ánh xạ lỗi / dữ liệu rỗng

WebFlux controller / message handler
  └─ return publisher cho framework
~~~

Các quyết định cần chốt khi thiết kế:

1. **Key naming và TTL:** đặt namespace, phân tách môi trường/tenant nếu cần; xác định thời hạn dữ liệu theo nghiệp vụ.
2. **Serializer:** chọn string/JSON/binary, version schema và khả năng tương thích giữa các service.
3. **Connection và driver:** quản lý bằng Spring; đặt timeout, credentials, SSL/TLS, topology và quan sát lỗi kết nối.
4. **Atomicity:** xác định thao tác nào cần một command nguyên tử hoặc logic server-side.
5. **Reactive composition:** trả publisher, tránh blocking, tránh subscription bị tách rời và kiểm soát concurrency.
6. **Failure behavior:** xử lý key không tồn tại, Redis không sẵn sàng, timeout, failover, retry và thao tác có tác dụng phụ.
7. **Monitoring:** quan sát latency, tỷ lệ lỗi, số request, hotspot key, hàng đợi xử lý, throughput và sử dụng kết nối.

### Minh họa kiểm soát đồng thời trong một batch

Giả sử cần lấy nhiều nickname từ Redis:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

public Flux<String> findNicknames(List<String> userIds) {
    return Flux.fromIterable(userIds)
        .flatMap(
            id -> reactiveStringRedisTemplate.opsForValue()
                .get("nickname:" + id)
                .defaultIfEmpty("anonymous"),
            16
        );
}
~~~

Tham số **16** ở đây giới hạn số inner publisher được **flatMap** xử lý đồng thời, giúp kiểm soát lượng lệnh in-flight của thao tác batch. Đây là một mức ví dụ cần điều chỉnh theo tải thực tế. **flatMap** có thể phát kết quả khác thứ tự đầu vào; nếu cần giữ thứ tự, cân nhắc **flatMapSequential** hoặc **concatMap**, với đánh đổi về lưu đệm và concurrency.

## 13. Tình huống suy luận

**Tình huống 1 — Factory và template:** Service cần lưu một DTO vào Redis dưới dạng JSON. Nên đưa **ReactiveRedisConnectionFactory** hay **ReactiveRedisTemplate<String, DTO>** vào constructor?

**Giải thích:** Inject template đã cấu hình serializer cho DTO. Factory nên được dùng tại tầng cấu hình để xây dựng template hoặc khi cần command cấp thấp có chủ đích.

**Tình huống 2 — Không thấy dữ liệu được ghi:** Code tạo **Mono<Boolean> save = template.opsForValue().set(...)** nhưng không return, compose hoặc subscribe publisher đó. Vì sao Redis chưa có key?

**Giải thích:** Tạo một publisher lạnh không tự bảo đảm lệnh đã chạy. Hãy đưa publisher vào chuỗi được subscribe bởi framework hoặc caller.

**Tình huống 3 — Lost update:** Hai HTTP request cùng dùng **get().flatMap(value -> set(value + 1))**. Tại sao bộ đếm đôi khi tăng chỉ một lần?

**Giải thích:** Reactive chỉ thay cách biểu diễn và thực thi bất đồng bộ; mỗi **GET** và **SET** vẫn là lệnh Redis riêng. Dùng **increment()** để diễn đạt phép tăng thành một command nguyên tử.

**Tình huống 4 — Phản hồi HTTP bị timeout sau khi ghi:** Một request gọi **set()** rồi timeout phía client. Có chắc Redis chưa ghi dữ liệu?

**Giải thích:** Không. Timeout có thể xảy ra khi lệnh đã đến Redis nhưng response chưa được nhận. Nếu client retry, cần tính đến yêu cầu idempotency và khả năng trạng thái đã thay đổi.

**Tình huống 5 — Đọc key ra dữ liệu lạ:** Một service ghi session bằng JSON serializer, service khác dùng string serializer. Có phải connection factory bị lỗi?

**Giải thích:** Chưa đủ cơ sở kết luận kết nối lỗi. Hai service có thể đang dùng **cùng kết nối hợp lệ** nhưng khác định dạng bytes. Kiểm tra serialization context, key prefix và schema của dữ liệu.

## Kết luận

Trong kiến trúc Spring Data Redis, **ReactiveRedisConnectionFactory** là tầng cung cấp kết nối Redis reactive, còn **ReactiveRedisTemplate** là tầng API dữ liệu cho service với serializer và thao tác Redis được thể hiện bằng **Mono/Flux**. **ReactiveStringRedisTemplate** là lựa chọn thuận tiện khi key/value ở dạng chuỗi.

Hiểu đúng ba ranh giới — **kết nối**, **serialization** và **subscription/reactive execution** — giúp ứng dụng WebFlux sử dụng Redis rõ ràng và dễ bảo trì. Đồng thời, luôn phân biệt **I/O không chặn** với **tính nguyên tử nghiệp vụ**: một pipeline reactive gồm nhiều lệnh Redis vẫn có thể gặp race condition và cần giải pháp đồng bộ phù hợp.
