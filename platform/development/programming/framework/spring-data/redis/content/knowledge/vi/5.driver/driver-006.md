# Chia sẻ kết nối gốc và trường hợp cần kết nối chuyên biệt

Trong **Spring Data Redis**, việc gọi `redisTemplate.opsForValue().get(key)` không nhất thiết tạo một kết nối TCP mới đến Redis. Với **Lettuce** — driver phổ biến trong Spring Boot — nhiều thao tác có thể sử dụng chung **một kết nối Redis gốc (native connection)**. Tuy nhiên, có những lệnh hoặc mô hình xử lý cần một kết nối riêng để tránh giữ tài nguyên dùng chung, bảo toàn ngữ cảnh lệnh, hoặc phục vụ một luồng xử lý kéo dài.

Bài học này giải thích ranh giới giữa:

1. **`RedisConnectionFactory`**: đối tượng quản lý cách lấy kết nối Redis cho các thành phần Spring.
2. **`RedisConnection`**: đối tượng kết nối theo abstraction của Spring Data Redis mà mã Spring thao tác.
3. **Native connection của Lettuce**: kết nối driver thực sự dùng để gửi lệnh đến Redis; ví dụ `StatefulRedisConnection`.
4. **Shared connection, dedicated connection và connection pool**: ba cách sử dụng/quản lý kết nối với mục đích khác nhau.

Điểm quan trọng nhất: **`LettuceConnectionFactory` mặc định có thể chia sẻ một native connection an toàn theo mô hình Lettuce cho các thao tác thông thường; những thao tác blocking và transactional phải sử dụng kết nối phù hợp với ngữ cảnh riêng của chúng.** Một lời gọi `getConnection()` không có nghĩa luôn mở một socket mới.

> Phạm vi: Spring Data Redis với driver Lettuce, các API imperative thường dùng trong Spring Boot. Các ví dụ cấu hình Java giả định Redis standalone để tập trung vào quản lý kết nối; nguyên tắc phân biệt kết nối dùng chung và riêng vẫn có ý nghĩa khi triển khai Redis Sentinel hoặc Cluster.

## 1. Vì sao kết nối Redis là một quyết định kiến trúc?

Ứng dụng có thể có hàng trăm request đồng thời. Mỗi request gọi Redis để đọc cache, cập nhật counter hoặc kiểm tra trạng thái. Nếu mỗi lần gọi đều tạo TCP connection mới, hệ thống phải trả chi phí:

- Thiết lập TCP, xác thực và thương lượng TLS (nếu bật).
- Cấp phát tài nguyên cho socket, buffer và đối tượng driver.
- Giữ số lượng kết nối phía Redis, với giới hạn tài nguyên và `maxclients`.
- Đóng và tái tạo kết nối thường xuyên, làm tăng độ trễ và độ phức tạp khi tải lớn.

Ngược lại, Redis hỗ trợ nhiều lệnh liên tiếp qua một kết nối và Lettuce hỗ trợ sử dụng kết nối của nó từ nhiều thread. Vì vậy, **tái sử dụng kết nối** có thể giảm overhead rất nhiều.

Nhưng nếu một lệnh chờ dữ liệu nhiều giây, một thao tác giữ trạng thái transaction hoặc một subscription chạy liên tục cùng dùng ngữ cảnh với các lệnh thông thường, việc chia sẻ bừa bãi sẽ gây tác động ngoài mong muốn. Đây là lý do Spring Data Redis phân biệt các trường hợp cần kết nối chuyên biệt.

## 2. Ba lớp cần phân biệt: factory, Spring connection và native connection

~~~text
                        NHIỀU THREAD / REQUEST
                           |       |       |
                           v       v       v
                    RedisTemplate / Cache / Service
                           |       |       |
                           v       v       v
                       RedisConnectionFactory
                        (LettuceConnectionFactory)
                           |       |       |
                 tạo wrapper RedisConnection
                           |       |       |
                           +-------+-------+
                                   |
                      native connection của Lettuce
                     (thread-safe, có thể được chia sẻ)
                                   |
                                TCP/TLS
                                   |
                                   v
                             Redis server
~~~

### 2.1. `RedisConnectionFactory` là đối tượng tạo/thu hồi kết nối

Đây là interface của Spring Data Redis. Với Lettuce, implementation phổ biến là `LettuceConnectionFactory`.

- Factory thường là **singleton bean** trong Spring container.
- Factory nắm cấu hình Redis endpoint, authentication, SSL/TLS, timeout và thông tin client.
- Factory tạo đối tượng `RedisConnection` để tầng trên thực thi lệnh.
- Factory quyết định khi nào lấy native connection dùng chung hoặc yêu cầu một kết nối khác từ provider.
- Factory có vòng đời: khởi tạo, chạy, dừng và giải phóng tài nguyên do nó sở hữu.

Không nên tự tạo factory mới trong mỗi HTTP request hoặc mỗi service method. Spring Boot thường cung cấp bean factory theo cấu hình ứng dụng.

### 2.2. `RedisConnection` là lớp abstraction của Spring

`RedisConnection` là abstraction cho các lệnh Redis. Với Lettuce, `LettuceConnectionFactory.getConnection()` có thể trả về **một wrapper `LettuceConnection` mới** nhưng wrapper đó vẫn dùng **cùng native connection gốc** với wrapper khác.

Ví dụ mô hình:

~~~text
Thread A -> LettuceConnection wrapper A ----\
                                             > Shared native Lettuce connection
Thread B -> LettuceConnection wrapper B ----/
~~~

**Không chia sẻ cùng một đối tượng `RedisConnection` giữa nhiều thread.** Lớp Spring connection có thể chứa trạng thái theo phiên lệnh, như pipeline hoặc transaction; các implementation không được xem là thread-safe để dùng tùy tiện.

Ngược lại, bean `RedisTemplate` được cấu hình và khởi tạo đầy đủ là đối tượng có thể chia sẻ giữa các thread, vì template quản lý việc lấy/giải phóng connection thông qua factory.

### 2.3. Native connection là tài nguyên của driver

Trong Lettuce, `StatefulRedisConnection` đại diện cho kết nối mang trạng thái của client; driver hỗ trợ thao tác từ nhiều thread và điều phối các lệnh qua kết nối đó.

Điều đó **không có nghĩa** mỗi thread có luồng TCP riêng, hoặc socket dùng chung bảo đảm băng thông vô hạn. Các request vẫn chia sẻ tài nguyên mạng, bộ đệm và khả năng xử lý lệnh của một kết nối/Redis node. Các thao tác cần ngữ cảnh cô lập phải được xử lý bằng một kết nối thích hợp.

Ở Redis Cluster, việc định tuyến lệnh theo hash slot còn có thể dẫn đến nhiều kết nối vật lý nội bộ đến các node. Do đó, khái niệm “một native connection dùng chung” phải được hiểu theo cấu hình và loại connection thực tế; **không suy diễn rằng toàn ứng dụng Cluster chỉ có đúng một socket**.

## 3. Chế độ mặc định của `LettuceConnectionFactory`

Thuộc tính quan trọng là:

~~~java
lettuceConnectionFactory.setShareNativeConnection(true);
~~~

Giá trị `true` là chế độ chia sẻ native connection mặc định của `LettuceConnectionFactory` cho các **thao tác thông thường, không blocking và không transactional**.

Luồng minh họa:

~~~text
GET user:42 -------\
SET metric:views ---+--> Shared native connection --> Redis
INCR counter:1 -----/
~~~

Lettuce có thể gửi nhiều lệnh qua kết nối và phối hợp kết quả cho các lời gọi tương ứng. Khi ứng dụng chỉ thực hiện GET, SET, INCR, HGET, EXPIRE và các thao tác ngắn tương tự, việc giữ một native connection dùng chung thường đơn giản và tiết kiệm tài nguyên.

### 3.1. `getConnection()` không đồng nghĩa với “TCP connect”

Ví dụ:

~~~java
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class RawRedisReader {

    private final RedisConnectionFactory factory;

    public RawRedisReader(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public byte[] read(byte[] key) {
        try (RedisConnection connection = factory.getConnection()) {
            return connection.stringCommands().get(key);
        }
    }
}
~~~

Một lời gọi ở trên tạo/lấy đối tượng `RedisConnection` và đóng wrapper theo hợp đồng `close()`. **Trong chế độ chia sẻ native connection, đóng wrapper không có nghĩa mỗi lần đều đóng socket Redis dùng chung.**

Code trực tiếp cấp thấp có thể cần trong một số trường hợp, nhưng với CRUD Redis thông thường nên ưu tiên `RedisTemplate` hoặc `StringRedisTemplate` để Spring xử lý việc lấy/hoàn trả connection, serialize và quản lý tài nguyên nhất quán.

### 3.2. Khi bật `shareNativeConnection = false`

~~~java
lettuceConnectionFactory.setShareNativeConnection(false);
~~~

Khi đó, factory không sử dụng shared native connection cho những thao tác thông thường; mỗi connection được yêu cầu sẽ lấy kết nối gốc riêng, **mới hoặc lấy từ pool nếu đã cấu hình pooling**.

~~~text
Request A -> RedisConnection A -> Native connection A -> Redis
Request B -> RedisConnection B -> Native connection B -> Redis
Request C -> RedisConnection C -> Native connection C -> Redis
~~~

Nếu không dùng pool, việc liên tục tạo và đóng native connection có thể tốn chi phí hơn đáng kể. Nếu dùng pool, ứng dụng vay kết nối trong thời gian sử dụng rồi trả lại pool.

**Không nên bật `false` chỉ với lý do “nhiều request chạy song song”.** Lettuce vốn hỗ trợ dùng chung native connection cho các lệnh thông thường; cần có yêu cầu cô lập hoặc kết quả đo đạc cụ thể trước khi tăng số kết nối.

## 4. Những trường hợp cần kết nối chuyên biệt

### 4.1. Lệnh blocking: `BLPOP`, `BRPOP` và các lệnh chờ

Ví dụ worker dùng Redis List làm hàng đợi đơn giản:

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobConsumer {

    private final StringRedisTemplate redis;

    public JobConsumer(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String takeJob() {
        return redis.opsForList()
                .leftPop("jobs:pending", Duration.ofSeconds(10));
    }
}
~~~

Với dạng chờ có timeout, Redis giữ yêu cầu `BLPOP` cho đến khi có phần tử hoặc hết thời gian chờ. Nếu gửi trực tiếp lệnh blocking trên một kết nối không thích hợp rồi dùng cùng kết nối cho các công việc khác, các công việc khác có thể bị ảnh hưởng vì lệnh chờ giữ ngữ cảnh xử lý.

`LettuceConnectionFactory` có cơ chế lấy **kết nối riêng cho blocking operations** khi native connection sharing được bật, thay vì ép mọi thao tác blocking dùng shared native connection cho những lệnh ngắn.

Các điểm vận hành:

- Mỗi worker đang chờ bằng lệnh blocking có thể giữ một connection trong suốt thời gian chờ; số worker đồng thời ảnh hưởng nhu cầu kết nối/pool.
- Đảm bảo timeout của lệnh, timeout của client, pool wait timeout và chính sách retry phù hợp nhau. Nếu lệnh chờ 10 giây nhưng timeout client quá ngắn, có thể xuất hiện lỗi trước khi Redis trả kết quả.
- Không chạy một lượng lớn thao tác chờ vô hạn trong thread request HTTP nếu không có giới hạn concurrency và cơ chế dừng/ủy quyền phù hợp.
- Redis List + `BLPOP` chỉ minh họa blocking command; hệ thống queue cần độ tin cậy cao còn cần xét xác nhận xử lý, retry job, lost work và mô hình Redis Streams hoặc broker phù hợp.

### 4.2. Transaction: `MULTI` / `EXEC` giữ ngữ cảnh kết nối

Redis transaction được gắn với **chính kết nối** đã gửi lệnh `MULTI`. Các lệnh sau đó được xếp hàng cho đến `EXEC` hoặc hủy bằng `DISCARD`.

~~~text
Connection A:
    MULTI
    SET keyA 1
    INCR keyB
    EXEC

Connection B:
    GET keyC     (phải độc lập với transaction của A)
~~~

Nếu nhiều request chia sẻ tùy tiện một ngữ cảnh transaction, lệnh của request khác có thể bị xếp hàng ngoài ý muốn. Vì vậy, thao tác transactional cần một connection riêng được giữ ổn định trong suốt transaction.

Spring Data Redis cung cấp cơ chế bảo toàn ngữ cảnh qua `SessionCallback`:

~~~java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CounterTransaction {

    private final StringRedisTemplate redis;

    public CounterTransaction(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> updateAtomically() {
        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            public <K, V> List<Object> execute(RedisOperations<K, V> operations)
                    throws DataAccessException {
                operations.multi();
                operations.opsForValue().increment((K) "counter:orders");
                operations.opsForValue().set((K) "counter:last-update", (V) "done");
                return operations.exec();
            }
        });
    }
}
~~~

Đây là ví dụ minh họa phạm vi một transaction và hai key; các phép ép kiểu phục vụ chữ ký generic của `SessionCallback`. Với ứng dụng thật, có thể tạo abstraction chuyên biệt để tránh ép kiểu ở tầng nghiệp vụ. Khi dùng Redis Cluster, các key tham gia transaction phải tuân theo ràng buộc hash slot của Cluster.

Cần phân biệt:

- `SessionCallback` giúp thực hiện chuỗi lệnh của template trong một ngữ cảnh connection phù hợp.
- `setEnableTransactionSupport(true)` là một lựa chọn khác để tích hợp với quản lý transaction của Spring, có tác động tới binding connection và hành vi lệnh; không nên bật tùy tiện.
- Redis `MULTI`/`EXEC` **không** có ý nghĩa rollback như transaction của cơ sở dữ liệu quan hệ; Redis không tự đảo ngược các lệnh đã thực thi nếu một lệnh sinh lỗi thực thi.
- Kết nối và thời gian giữ transaction phải được giới hạn; không giữ transaction trong các thao tác chờ mạng hoặc xử lý nghiệp vụ kéo dài.

### 4.3. Pub/Sub: kết nối duy trì subscription

Một connection Redis đã vào chế độ subscription phải phục vụ luồng thông điệp lâu dài. Với Redis Pub/Sub, người đăng ký không thể dùng connection đó như connection thao tác lệnh thông thường tùy ý.

Trong Spring Data Redis, `RedisMessageListenerContainer` quản lý subscription và vòng đời kết nối:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.data.redis.listener.adapter.MessageListenerAdapter;

@Configuration
public class EventsRedisConfig {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory factory,
            MessageListenerAdapter orderMessageListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();
        container.setConnectionFactory(factory);
        container.addMessageListener(
                orderMessageListener,
                new ChannelTopic("shop:order-events")
        );
        return container;
    }
}
~~~

Đoạn này giả định ứng dụng đã khai báo `MessageListenerAdapter` tên `orderMessageListener` cùng listener mục tiêu.

Điểm cần hiểu:

- Subscription là hoạt động **kéo dài**, thường duy trì kết nối chuyên biệt, không phải mỗi message tạo một TCP connection mới.
- Container có thể chia sẻ một subscription connection cho nhiều listener/channel theo thiết kế của nó; không nhất thiết mỗi listener một socket.
- Publisher có thể dùng `RedisTemplate.convertAndSend(...)` với luồng kết nối thông thường.
- Pub/Sub không lưu message cho subscriber vắng mặt. Nếu cần khả năng đọc lại và xác nhận xử lý, xem xét Redis Streams thay vì giả định Pub/Sub là hàng đợi bền vững.

### 4.4. Pipeline lớn hoặc công việc cần cô lập tài nguyên

Pipeline gửi nhiều lệnh mà không đợi phản hồi sau từng lệnh, rồi thu thập kết quả. Spring Data Redis hỗ trợ `executePipelined(...)`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class BulkReader {

    private final StringRedisTemplate redis;

    public BulkReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> getMany() {
        return redis.executePipelined((RedisCallback<Object>) connection -> {
            for (int i = 0; i < 100; i++) {
                connection.stringCommands().get(
                        ("product:" + i).getBytes(StandardCharsets.UTF_8)
                );
            }
            return null; // kết quả pipeline được Spring trả ra bên ngoài callback
        });
    }
}
~~~

Đối với pipeline, điều quan trọng là giữ **ngữ cảnh pipeline nhất quán** cho toàn bộ chuỗi lệnh. Tuy nhiên, không nên kết luận rằng **mọi pipeline** được LettuceConnectionFactory cấp một socket chuyên biệt chỉ vì đó là pipeline: chi tiết sử dụng native connection còn phụ thuộc đường thực thi, API và cấu hình.

Khi pipeline rất lớn hoặc thao tác đặc thù có khả năng gây ảnh hưởng lên độ trễ các thao tác thông thường, ứng dụng có thể cân nhắc một factory/template riêng, pool riêng, giới hạn batch và giới hạn concurrency. Hãy đo lượng lệnh, độ trễ, bộ nhớ buffer và số socket trước khi quyết định.

### 4.5. Kết nối có trạng thái hoặc vòng đời do ứng dụng quản lý

Một số thành phần dùng API Lettuce trực tiếp để cần tính năng driver đặc biệt, chẳng hạn một luồng subscription riêng hoặc chính sách I/O, topology refresh và auto-reconnect chuyên sâu.

Khi tự tạo kết nối qua `RedisClient.connect(...)`, caller có trách nhiệm đóng connection và quản lý lifecycle RedisClient hoặc pool tương ứng. Không tự đóng native connection mà một `LettuceConnectionFactory` khác đang quản lý và chia sẻ, vì điều đó có thể ảnh hưởng toàn bộ ứng dụng.

## 5. Hành vi connection sharing: bảng quyết định

| Hoạt động | Dùng shared native connection mặc định? | Cần lưu ý |
|---|---|---|
| GET, SET, HGET, INCR, EXPIRE ngắn | Thường có, với Lettuce và `shareNativeConnection=true` | Đường đi phổ biến cho ứng dụng web |
| Nhiều HTTP thread gọi `StringRedisTemplate` | Có thể cùng dùng native connection | Chia sẻ **template/factory**, không chia sẻ cùng wrapper `RedisConnection` giữa thread |
| Blocking pop/chờ | Thường dùng connection riêng do provider cấp | Số tác vụ đang chờ ảnh hưởng pool/concurrency |
| `MULTI` / `EXEC` | Cần connection riêng và giữ trong cùng ngữ cảnh | Dùng cơ chế transaction/`SessionCallback` phù hợp |
| Pub/Sub subscriber | Subscription kết nối dài hạn, do listener container quản lý | Không dùng kết nối subscribe cho GET/SET thông thường |
| Publisher `convertAndSend` | Có thể dùng luồng kết nối thông thường | Publisher không phải subscriber |
| Pipeline | Cần ngữ cảnh pipeline nhất quán | Không mặc định đồng nhất mọi pipeline với một socket riêng |
| Tự gọi `getConnection()` | Tùy factory, có thể chỉ nhận wrapper mới | `getConnection()` không chứng minh socket mới |
| `setShareNativeConnection(false)` | Không dùng shared native connection cho các thao tác thông thường | Nếu không có pool, có thể phát sinh nhiều lần connect/close |
| Redis Cluster | Phụ thuộc kết nối driver theo topology/node | Không đếm socket bằng số factory/template một cách máy móc |

## 6. Cấu hình Spring Boot: chia sẻ kết nối gốc

Với Spring Boot dùng Lettuce, thông thường chỉ cần cấu hình endpoint Redis rồi để Spring Boot tạo `LettuceConnectionFactory`:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      timeout: 3s
      connect-timeout: 2s
~~~

Ứng dụng có thể inject template và sử dụng:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCounter {

    private final StringRedisTemplate redis;

    public ProductCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long addOne(long productId) {
        return redis.opsForValue()
                .increment("product:views:" + productId);
    }
}
~~~

Không cần gọi `factory.getConnection()` trong mỗi service, cũng không cần tự quản lý socket. Cấu hình Redis trong môi trường thực tế còn có thể gồm username/password, ACL, TLS, Sentinel hoặc Cluster.

### 6.1. Cấu hình thủ công `LettuceConnectionFactory`

Ví dụ sau cho thấy nơi điều khiển chính sách chia sẻ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClientConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("redis.internal", 6379);

        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(server);

        factory.setShareNativeConnection(true);
        return factory;
    }
}
~~~

Giá trị `true` vốn là mặc định; đặt tường minh ở đây nhằm thể hiện ý nghĩa. Khi tự tạo bean factory, cần bổ sung xác thực, TLS và những customizer mà cấu hình tự động của Spring Boot trước đó đang đảm nhiệm; không nên copy ví dụ này vào production mà bỏ qua cấu hình hiện hữu.

Trong các phiên bản hỗ trợ, có thể cấu hình **kiểm tra tính hợp lệ của shared connection** khi cần. Việc kiểm tra connection ở mỗi lần lấy connection có chi phí nên không phải mặc định tốt cho mọi workload; driver cũng có cơ chế tự động tái kết nối cần được hiểu riêng.

## 7. Khi thực sự muốn factory/template dùng kết nối chuyên biệt

Nếu có một workload cần cô lập khỏi các thao tác Redis thông thường, có thể định nghĩa **hai factory** với hai chính sách:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class TwoRedisFactoriesConfig {

    private RedisStandaloneConfiguration endpoint() {
        return new RedisStandaloneConfiguration("redis.internal", 6379);
    }

    @Bean("mainRedisConnectionFactory")
    @Primary
    public LettuceConnectionFactory mainRedisConnectionFactory() {
        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(endpoint());
        factory.setShareNativeConnection(true);
        return factory;
    }

    @Bean("isolatedRedisConnectionFactory")
    public LettuceConnectionFactory isolatedRedisConnectionFactory() {
        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(endpoint());
        factory.setShareNativeConnection(false);
        return factory;
    }

    @Bean("isolatedRedisTemplate")
    public StringRedisTemplate isolatedRedisTemplate(
            @Qualifier("isolatedRedisConnectionFactory")
            RedisConnectionFactory connectionFactory) {

        return new StringRedisTemplate(connectionFactory);
    }
}
~~~

Những gì ví dụ này thể hiện:

- `mainRedisConnectionFactory` phục vụ các luồng có thể chia sẻ native connection; annotation `@Primary` giúp phân giải injection khi có nhiều bean cùng type.
- `isolatedRedisConnectionFactory` cấp connection riêng cho các thao tác sử dụng factory đó.
- `isolatedRedisTemplate` gắn với factory riêng; các service muốn dùng nó cần inject bằng `@Qualifier("isolatedRedisTemplate")`.
- **Hai factory đang cùng truy cập một Redis endpoint**; đây chỉ là cách tách tài nguyên kết nối phía client, không tạo dữ liệu/hạ tầng Redis độc lập.
- Factory thứ hai không có pool trong ví dụ. Nếu có tần suất request cao, cần đánh giá overhead kết nối và xem xét pooling.
- Khi tự tạo nhiều `RedisConnectionFactory`, các bean auto-configuration của Spring Boot, Spring Cache hoặc Spring Session có thể lựa chọn bean mặc định theo điều kiện và ưu tiên riêng. Cần cấu hình rõ owner của từng factory, tránh để Redis Session/Cache vô tình chọn một factory có chính sách không mong muốn.

Trong nhiều trường hợp, **không cần factory thứ hai** chỉ vì ứng dụng dùng `BLPOP` hoặc `MULTI`: LettuceConnectionFactory đã có cơ chế lấy kết nối phù hợp cho các trường hợp này khi sharing được bật. Factory riêng chỉ hợp lý nếu cần cô lập chính sách hoặc tài nguyên theo thiết kế.

## 8. Connection pool: khi nào thêm và điều gì không thay đổi?

Pooling là cơ chế giữ sẵn một số native connection để ứng dụng **vay rồi hoàn trả**, tránh tạo/đóng socket mới liên tục.

~~~text
                Các request cần dedicated connection
                              |
                              v
                      Connection provider
                              |
                         Connection pool
                     /        |         \
                   conn1    conn2      conn3
                     \        |         /
                              v
                         Redis server
~~~

Với Lettuce, Spring Data Redis có thể sử dụng cấu hình pooling thông qua `LettucePoolingClientConfiguration` và thư viện Apache Commons Pool 2.

### 8.1. Pool không tự động biến mọi GET thành một socket riêng

Đây là điểm dễ nhầm nhất:

**Nếu `shareNativeConnection=true`, các lệnh thông thường có thể vẫn dùng một native connection chia sẻ ngay cả khi đã bật pooling.** Pool được dùng cho những đường cần kết nối riêng, như blocking/transactional operations theo cơ chế factory.

Nếu `shareNativeConnection=false`, các lời gọi lấy Spring RedisConnection có thể vay native connection từ pool cho những thao tác thông thường; khi đóng wrapper, kết nối được hoàn trả theo lifecycle của provider/pool.

Vì thế, muốn tối ưu hóa hệ thống cần xác định **workload nào thực sự borrow connection**, không dựa đơn thuần vào thuộc tính `max-active`.

### 8.2. Ví dụ tạo factory dùng pool

~~~java
import io.lettuce.core.api.StatefulConnection;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettucePoolingClientConfiguration;

@Configuration
public class PooledRedisConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        GenericObjectPoolConfig<StatefulConnection<?, ?>> pool =
                new GenericObjectPoolConfig<>();

        pool.setMaxTotal(16);
        pool.setMaxIdle(8);
        pool.setMinIdle(2);

        LettucePoolingClientConfiguration client =
                LettucePoolingClientConfiguration.builder()
                        .poolConfig(pool)
                        .build();

        LettuceConnectionFactory factory = new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("redis.internal", 6379),
                client
        );

        factory.setShareNativeConnection(false);
        return factory;
    }
}
~~~

Ví dụ cố ý dùng `shareNativeConnection(false)` để minh họa việc pool phục vụ cả những thao tác thông thường. Cần có dependency `commons-pool2` và cấu hình Redis endpoint đúng môi trường.

Các tham số cần cân nhắc:

| Tham số | Ý nghĩa | Khi cấu hình quá thấp/quá cao |
|---|---|---|
| `maxTotal` / số connection tối đa | Số native connection cùng được pool quản lý | Quá thấp gây chờ connection; quá cao tăng socket/tài nguyên Redis |
| `maxIdle` | Số connection rảnh tối đa được giữ | Quá thấp tăng connect churn; quá cao giữ tài nguyên |
| `minIdle` | Mục tiêu số connection rảnh tối thiểu | Duy trì connection dự phòng nhưng có chi phí |
| Thời gian chờ borrow | Thời gian caller đợi pool có connection | Có thể timeout trước khi được dùng Redis |
| Validation/eviction của pool | Kiểm tra và thu hồi connection cũ/hỏng | Tăng chi phí kiểm tra, nhưng có thể giảm lỗi do stale connection |

Pooling không thay thế giới hạn concurrency của ứng dụng. Ví dụ 100 consumer chờ `BLPOP` trong khi pool tối đa 16 connection: các consumer dư có thể phải đợi connection từ pool và timeout trước khi chờ Redis được.

### 8.3. Khi không cần pool

Lettuce có cơ chế multiplexing và native connection thread-safe cho lệnh thông thường, nên một ứng dụng chủ yếu GET/SET/INCR không phải cứ nhiều thread là cần pool lớn. Hãy đo độ trễ, throughput, số socket, khả năng xử lý Redis server và dấu hiệu nghẽn thực tế.

Nếu cần dedicated connection vì lý do blocking hoặc transaction, pooling thường đáng cân nhắc hơn so với mở kết nối mới cho từng lần dùng.

## 9. Liên hệ với Redis Cluster, Sentinel và driver khác

### 9.1. Redis Sentinel

Sentinel giúp client tìm primary hiện tại và khôi phục kết nối sau failover. Connection sharing vẫn là chính sách ở tầng Lettuce/Spring Data Redis.

Khi failover:

- Shared native connection có thể cần reconnect tới primary mới.
- Dedicated connection hoặc pooled connection có thể phải bị loại bỏ và tạo lại theo topology mới.
- Lệnh đang chạy có thể timeout hoặc lỗi; việc retry cần xét lệnh có idempotent hay không.

Không suy ra rằng shared connection bảo đảm không gián đoạn trong lúc failover.

### 9.2. Redis Cluster

Client Cluster-aware định tuyến key theo hash slot và có thể duy trì kết nối đến nhiều Redis node. Khi slot di chuyển hoặc node mất kết nối, tập connection vật lý có thể đổi.

Điều này khác với hình dung một standalone server chỉ có một TCP socket. Với Cluster cần quan sát kết nối **theo node, topology và driver**, đồng thời đảm bảo các địa chỉ node được Cluster quảng bá có thể truy cập từ ứng dụng.

Dedicated connection không giải quyết ràng buộc multi-key cross-slot; đó là vấn đề phân mảnh dữ liệu và khả năng của client.

### 9.3. Jedis có giống Lettuce không?

Không nên chuyển nguyên mô hình chia sẻ native connection của Lettuce sang Jedis:

- Lettuce có API native connection hỗ trợ đa thread và cơ chế multiplexing, nên một native connection có thể phục vụ nhiều thao tác đồng thời.
- Jedis có mô hình quản lý kết nối và pooling riêng; tùy phiên bản/API, cách chia sẻ connection có quy tắc khác.
- `shareNativeConnection` là chính sách của **`LettuceConnectionFactory`**, không phải thuộc tính chung của mọi Redis driver.

Nếu ứng dụng đổi driver, cần xem lại cấu hình factory, pool, timeout và các thành phần dùng connection dài hạn.

## 10. Lỗi hay gặp và cách nhận diện

### Lỗi 1 — Chia sẻ `RedisConnection` giữa các thread

~~~java
// Không nên giữ RedisConnection làm field và dùng trên nhiều request.
private RedisConnection connection = factory.getConnection();
~~~

Một wrapper Spring RedisConnection có thể chứa trạng thái pipeline/transaction và không được thiết kế để dùng chung tùy tiện. Hãy giữ `RedisTemplate` hoặc factory làm bean, và để mỗi operation lấy connection theo cơ chế Spring.

### Lỗi 2 — Tưởng `getConnection()` luôn là dedicated socket

~~~java
RedisConnection a = factory.getConnection();
RedisConnection b = factory.getConnection();
~~~

`a != b` không chứng minh hai kết nối TCP khác nhau. Với Lettuce sharing bật, hai wrapper có thể trỏ tới cùng một native connection. Nếu cần cách ly thực sự, phải cấu hình factory/provider hoặc sử dụng connection driver riêng phù hợp.

### Lỗi 3 — Dùng blocking command rồi tăng pool vô hạn

Lệnh chờ giữ connection trong một khoảng thời gian. Tăng pool không giới hạn làm Redis phải quản lý nhiều client hơn, trong khi bottleneck có thể nằm ở khả năng xử lý job hoặc thiếu backpressure. Cần giới hạn số consumer, timeout và độ dài hàng đợi.

### Lỗi 4 — Tắt sharing cho mọi request mà không đo đạc

`setShareNativeConnection(false)` có thể tăng số kết nối vật lý và overhead nếu không có pool. Ngược lại, bật sharing không tự động làm mọi workload tối ưu. Cần theo dõi latency và resource usage trước khi đổi.

### Lỗi 5 — Dùng connection transaction cho các lệnh ngoài transaction

Các lệnh trong ngữ cảnh `MULTI` được queue; nếu trộn lệnh từ các luồng độc lập trên cùng connection, kết quả không đúng ý đồ. Hãy giữ transaction trong một phạm vi rõ ràng thông qua API Spring tương ứng.

### Lỗi 6 — Tự đóng native connection dùng chung

Đóng `RedisConnection` theo hợp đồng Spring là việc bình thường; đóng trực tiếp đối tượng native connection do một factory dùng chung quản lý là chuyện khác. Hãy để chính factory/client owner quản lý lifecycle.

### Lỗi 7 — Nghĩ connection pool giải quyết mọi lỗi Redis

Pool quản lý tài nguyên phía client; nó không làm Redis server hết quá tải, không giải quyết mất primary, không bảo đảm dữ liệu bền vững và không khiến transaction/multi-key trong Cluster vượt qua quy tắc hash slot.

## 11. Quan sát và lựa chọn trong production

Để chọn mô hình kết nối, quan sát ít nhất những tín hiệu sau:

| Tín hiệu | Cách hiểu |
|---|---|
| Latency Redis ở phía client | Tăng do mạng, queue lệnh, server load hoặc connection acquisition |
| Tổng connection đang mở tại Redis | Có tăng theo request không? Có gần `maxclients` không? |
| Borrow wait và số connection đang hoạt động trong pool | Caller có phải chờ trước khi gửi lệnh không? |
| Số worker blocking và thời gian chờ trung bình | Có đang chiếm phần lớn dedicated connection không? |
| Timeout/reconnect khi failover | Có cần điều chỉnh retry, timeout và topology discovery không? |
| Redis CPU, network, memory, slowlog | Nghẽn ở server hay ở phía client? |

Có thể xem nhanh số client từ Redis CLI:

~~~bash
redis-cli INFO clients
redis-cli CLIENT LIST
~~~

Kết quả phụ thuộc quyền ACL và cấu hình môi trường. `CLIENT LIST` cho thấy connection từ nhiều nguồn, không tự gắn từng connection với bean Spring nào; khi cần phân tích chi tiết, dùng thêm metrics/tracing ở phía ứng dụng.

### Checklist quyết định theo nhu cầu

**Nếu phần lớn là lệnh Redis ngắn và độc lập:** giữ `LettuceConnectionFactory` mặc định với shared native connection; dùng singleton `RedisTemplate` để thao tác.

**Nếu có Redis transaction:** dùng API đảm bảo cùng một connection trong transaction, ví dụ `SessionCallback` hoặc cơ chế transaction support tương ứng. Không tự lấy connection dùng chung rồi trộn transaction từ nhiều thread.

**Nếu có nhiều consumer blocking:** dùng API Spring phù hợp, kiểm tra provider/pool, giới hạn số consumer và thiết lập timeout theo thời gian chờ thực tế.

**Nếu subscribe Pub/Sub:** để `RedisMessageListenerContainer` quản lý kết nối dài hạn và vòng đời subscription.

**Nếu workload đặc biệt gây nhiễu lệnh thường:** cân nhắc factory/template riêng hoặc client riêng, pooling và giới hạn concurrency. Đo đạc trước và sau khi tách tài nguyên.

**Nếu Redis Cluster hoặc Sentinel:** giữ nguyên tư duy quản lý connection nhưng bổ sung topology discovery, reconnect và khả năng truy cập các node thực tế.

## 12. Tổng kết qua sơ đồ

~~~text
                  Spring Data Redis + Lettuce
                              |
                  LettuceConnectionFactory
                              |
                   shareNativeConnection?
                     /                 \
                   true                false
                    |                    |
            Lệnh ngắn thông thường     Kết nối riêng
            dùng shared native         hoặc lấy từ pool
                    |                    |
                    v                    v
              Redis server         Redis server
                    |
                    +-- Blocking/transaction?
                            |
                            v
                    Connection riêng qua provider

             Pub/Sub subscriber --> Kết nối subscription
             Pipeline dài       --> Quản lý ngữ cảnh và cô lập khi cần
~~~

**Chia sẻ native connection** là lựa chọn mặc định phù hợp với nhiều lệnh Redis ngắn của Lettuce. **Kết nối chuyên biệt** dành cho ngữ cảnh cần độc lập như blocking, transaction, subscription và workload phải cô lập tài nguyên. **Pool** giúp tái sử dụng các kết nối chuyên biệt khi số lượng thao tác tăng, nhưng không thay thế thiết kế đúng ngữ cảnh lệnh.

Khi làm việc với Spring Data Redis, hãy quản lý kết nối tại `RedisConnectionFactory`/`RedisTemplate`, giới hạn việc dùng trực tiếp native driver cho những nhu cầu thực sự đặc biệt, và đo đạc tác động lên Redis server trước khi tối ưu số lượng kết nối.
