# CachingConnectionFactory và bộ nhớ đệm Session, Producer, Consumer

Khi gửi message qua JMS, việc liên tục tạo và đóng Connection, Session, MessageProducer hoặc MessageConsumer có thể gây thêm chi phí cho ứng dụng và JMS provider. Spring JMS cung cấp **CachingConnectionFactory** để tái sử dụng một Connection và cache một số resource JMS sau khi chúng được trả lại.

CachingConnectionFactory giúp giảm số lần tạo resource, nhưng cần hiểu đúng phạm vi của từng cache. Factory chia sẻ Connection, cache Session theo acknowledgement mode, cache Producer trong Session và chỉ cache Consumer khi được bật. Cache không biến Session thành thread-safe, không tự tạo connection pool nhiều kết nối và không bảo đảm message được lưu bền vững.

## 1. Các resource JMS và chi phí khởi tạo

Một luồng gửi message thường đi qua các resource:

- **ConnectionFactory:** tạo kết nối đến JMS provider.
- **Connection:** kết nối vật lý hoặc logic đến provider.
- **Session:** ngữ cảnh single-threaded để tạo message, producer, consumer và quản lý acknowledgement/transaction.
- **MessageProducer:** gửi message đến Queue hoặc Topic.
- **MessageConsumer:** nhận message từ destination.

Tạo resource có thể tốn thời gian vì provider phải cấp phát object, thiết lập trạng thái giao thức, đăng ký consumer, tạo producer và trao đổi metadata với broker. Nếu ứng dụng gửi nhiều message ngắn trong các request khác nhau, việc tạo rồi đóng Session và Producer liên tục có thể làm tăng latency và tải lên provider.

Một cách đơn giản là giữ Connection lâu hơn và tái sử dụng Session/Producer. Tuy nhiên, việc tự giữ các resource trong singleton service rất dễ dẫn đến chia sẻ Session giữa nhiều thread. CachingConnectionFactory cung cấp cơ chế quản lý cache để ứng dụng tái sử dụng resource mà vẫn mượn/trả chúng theo từng lần sử dụng.

## 2. CachingConnectionFactory là gì?

**CachingConnectionFactory** thuộc package **org.springframework.jms.connection**. Đây là một wrapper quanh một target JMS ConnectionFactory. Nó kế thừa **SingleConnectionFactory**, do đó quản lý một Connection dùng chung và bổ sung cache cho các Session, MessageProducer và tùy chọn MessageConsumer.

Các vai trò chính:

1. Duy trì một Connection dùng chung thay vì tạo Connection vật lý mới cho mỗi thao tác.
2. Cache Session sau khi client đóng Session proxy.
3. Cache MessageProducer trong phạm vi Session và destination.
4. Có thể cache MessageConsumer nếu bật cấu hình tương ứng.
5. Có thể reset shared Connection khi gặp lỗi connection theo cấu hình reconnect.

Cần phân biệt CachingConnectionFactory với một connection pool tổng quát. CachingConnectionFactory tập trung chia sẻ một Connection và tái sử dụng các Session/resource bên trong. Nếu ứng dụng cần pool nhiều Connection vật lý, giới hạn số connection và quản lý lease theo từng connection, hãy xem xét pool do JMS provider hoặc thư viện pooling cung cấp.

### 2.1. Vòng đời khi dùng cache

Với JmsTemplate, một thao tác gửi thường mượn Session và Producer, thực hiện gửi, rồi đóng resource sau thao tác. Khi ConnectionFactory là CachingConnectionFactory, lời gọi close trên proxy có thể trả Session hoặc Producer về cache thay vì đóng resource vật lý ngay lập tức.

~~~mermaid
flowchart TD
    A["JmsTemplate operation"] --> B["Borrow Session"]
    B --> C["Borrow/create Producer"]
    C --> D["Send Message"]
    D --> E["Close Producer / Session proxy"]
    E --> F{"Cache has room?"}
    F -->|Yes| G["Return resource to cache"]
    F -->|No| H["Close physical resource"]
    G --> I["Reuse on later operation"]
~~~

Nhờ vậy, code nghiệp vụ vẫn dùng JmsTemplate theo cách thông thường. Template quản lý phạm vi thao tác; CachingConnectionFactory quyết định resource nào được tái sử dụng sau khi trả về.

## 3. Cache Session hoạt động như thế nào?

Session là resource quan trọng nhất vì Producer và Consumer được tạo từ Session. CachingConnectionFactory giữ các Session đã được trả lại để lần sử dụng tiếp theo có thể mượn lại.

### 3.1. Cache riêng theo acknowledgement mode

Session được cache theo acknowledgement mode. Ví dụ, Session dùng AUTO_ACKNOWLEDGE được giữ trong nhóm cache tương ứng; Session transacted thuộc nhóm khác. Điều này tránh tái sử dụng một Session với chế độ acknowledgement/transaction không phù hợp.

Các mode thường gặp:

- **AUTO_ACKNOWLEDGE:** provider tự xác nhận message theo semantics JMS.
- **CLIENT_ACKNOWLEDGE:** ứng dụng chủ động gọi acknowledge.
- **DUPS_OK_ACKNOWLEDGE:** provider có thể trì hoãn acknowledgement và cho phép duplicate.
- **SESSION_TRANSACTED:** Session quản lý giao dịch JMS bằng commit/rollback.

Cấu hình session cache size:

~~~java
CachingConnectionFactory cachingFactory =
        new CachingConnectionFactory(providerConnectionFactory);

cachingFactory.setSessionCacheSize(10);
~~~

sessionCacheSize xác định số Session tối đa được giữ trong cache cho mỗi acknowledgement mode. Giá trị mặc định của thuộc tính này là 1. Nếu ứng dụng dùng nhiều mode, mỗi mode có nhóm cache riêng.

### 3.2. Cache size không phải giới hạn concurrency

Đây là điểm dễ hiểu nhầm. sessionCacheSize không nhất thiết giới hạn số Session có thể đang hoạt động đồng thời.

Ví dụ, cache size là 5 nhưng tại một thời điểm có 12 thread cùng gửi message. Factory có thể phải tạo đủ Session để phục vụ các lần mượn đồng thời. Khi các thread trả Session về:

- Tối đa 5 Session của acknowledgement mode đó được giữ lại trong cache.
- Các Session dư có thể bị đóng vật lý thay vì giữ lại.

Vì vậy, cache size quyết định số Session nhàn rỗi có thể tái sử dụng, không phải semaphore giới hạn số thread hoặc số request. Nếu muốn giới hạn concurrency, cần dùng executor/semaphore hoặc giới hạn tài nguyên ở tầng phù hợp.

### 3.3. Session không trở thành thread-safe

CachingConnectionFactory không cho phép nhiều thread dùng chung một Session cùng lúc. Mỗi lần mượn Session phải có quyền sử dụng độc lập; chỉ sau khi Session được trả về cache, một thao tác khác mới có thể mượn lại resource đó.

Một service singleton có thể được nhiều thread gọi nếu nó dùng JmsTemplate và ConnectionFactory đã cấu hình đúng. Không nên lấy Session từ một lần callback, lưu vào field rồi chia sẻ cho các request khác.

## 4. Cache MessageProducer

MessageProducer được tạo từ một Session và gửi message đến một destination. Việc tạo Producer có thể cần trao đổi với provider hoặc thiết lập trạng thái gửi.

CachingConnectionFactory mặc định bật cache Producer. Producer được cache bên trong Session, gắn với destination mà nó gửi đến. Khi Session được tái sử dụng, Producer phù hợp cũng có thể được dùng lại.

Cấu hình:

~~~java
cachingFactory.setCacheProducers(true);
~~~

Nếu tắt cache Producer:

~~~java
cachingFactory.setCacheProducers(false);
~~~

thì Producer sẽ được đóng theo vòng đời thao tác thay vì được giữ lại để tái sử dụng. Điều này có thể hữu ích khi provider có hành vi đặc biệt hoặc ứng dụng cần kiểm soát lifecycle, nhưng thường làm tăng chi phí tạo resource.

Cache Producer không có nghĩa một Producer object được chia sẻ đồng thời cho mọi thread. Producer thuộc Session; Session được mượn theo phạm vi sử dụng và không được dùng đồng thời bởi nhiều thread. Vì vậy, Producer được cache trong Session không phá vỡ nguyên tắc single-threaded của Session.

## 5. Cache MessageConsumer

Consumer nhận message từ destination, có thể dùng receive đồng bộ hoặc đăng ký listener tùy cách tích hợp.

CachingConnectionFactory mặc định **không cache Consumer**. Có thể bật:

~~~java
cachingFactory.setCacheConsumers(true);
~~~

Khi bật, Consumer có thể được giữ lại trong cache theo Session và các thuộc tính nhận dạng như destination, selector và cấu hình subscription liên quan. Cách cache cụ thể phụ thuộc implementation và phiên bản Spring.

Consumer có vòng đời phức tạp hơn Producer vì nó có thể giữ trạng thái nhận message, selector, subscription, prefetch và listener. Giữ Consumer quá lâu có thể làm thay đổi hành vi mong đợi, nhất là khi ứng dụng dùng selector động, durable subscription hoặc listener container.

Vì vậy:

- Giữ mặc định cacheConsumers=false nếu chưa có lý do đo đạc rõ ràng để bật.
- Nếu bật, kiểm thử kỹ selector, destination, durable/shared subscription và hành vi close/reuse trên JMS provider thực tế.
- Không dùng cache Consumer để thay thế lifecycle management của listener container.
- Tránh bật consumer caching đồng thời với một tầng khác đã cache Consumer nếu chưa hiểu cách hai tầng tương tác.

## 6. Cấu hình CachingConnectionFactory trong Spring

Thông thường, provider tạo ConnectionFactory gốc; CachingConnectionFactory bọc factory đó và được dùng làm ConnectionFactory cho JmsTemplate.

Ví dụ cấu hình:

~~~java
@Configuration
public class JmsCacheConfiguration {

    @Bean
    @Primary
    public CachingConnectionFactory cachingConnectionFactory(
            @Qualifier("providerConnectionFactory")
            ConnectionFactory providerConnectionFactory) {

        CachingConnectionFactory factory =
                new CachingConnectionFactory(providerConnectionFactory);

        factory.setSessionCacheSize(10);
        factory.setCacheProducers(true);
        factory.setCacheConsumers(false);
        factory.setReconnectOnException(true);

        return factory;
    }
}
~~~

Trong ví dụ, providerConnectionFactory là bean ConnectionFactory do ứng dụng hoặc JMS provider cấu hình. @Qualifier giúp tránh việc bean cache tự inject chính nó. @Primary khiến các thành phần cần ConnectionFactory ưu tiên dùng factory đã bọc cache.

Nếu ứng dụng dùng một tên bean khác, hãy thay qualifier tương ứng. Không tạo vòng phụ thuộc trong đó CachingConnectionFactory lại nhận chính nó làm target.

JmsTemplate có thể dùng factory này:

~~~java
@Bean
public JmsTemplate jmsTemplate(
        CachingConnectionFactory cachingConnectionFactory) {
    return new JmsTemplate(cachingConnectionFactory);
}
~~~

Hoặc để Spring Boot tự cấu hình JmsTemplate từ ConnectionFactory chính đã được chọn. Tên bean và cách auto-configuration phụ thuộc cấu trúc ứng dụng.

### 6.1. Những thuộc tính thường cần cân nhắc

| Thuộc tính | Vai trò | Mặc định thường gặp |
|---|---|---|
| sessionCacheSize | Số Session nhàn rỗi giữ lại cho mỗi acknowledgement mode | 1 |
| cacheProducers | Có cache MessageProducer trong Session hay không | true |
| cacheConsumers | Có cache MessageConsumer trong Session hay không | false |
| reconnectOnException | Reset shared Connection khi gặp lỗi connection theo cơ chế của factory | true |

Hãy kiểm tra Javadocs đúng phiên bản Spring Framework đang dùng trước khi dựa vào giá trị mặc định trong một hệ thống cụ thể. Provider, phiên bản JMS API và cấu hình transaction có thể ảnh hưởng đến cách resource được tạo và quản lý.

## 7. JmsTemplate và CachingConnectionFactory phối hợp ra sao?

JmsTemplate là abstraction cấp cao để gửi và nhận message. Nó quản lý thao tác lấy Connection/Session/Producer, thực hiện công việc và đóng resource trong phạm vi lời gọi.

Khi JmsTemplate dùng CachingConnectionFactory:

1. JmsTemplate yêu cầu Session.
2. CachingConnectionFactory trả Session từ cache nếu có, hoặc tạo Session mới.
3. JmsTemplate yêu cầu Producer cho destination.
4. Factory trả Producer đã cache trong Session nếu có, hoặc tạo Producer mới.
5. JmsTemplate gửi message.
6. Khi thao tác kết thúc, resource proxy được đóng và trả về cache theo chính sách.

Ví dụ service có thể dùng template từ nhiều thread:

~~~java
@Service
public class NotificationPublisher {

    private final JmsTemplate jmsTemplate;

    public NotificationPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String destination, String payload) {
        jmsTemplate.convertAndSend(destination, payload);
    }
}
~~~

NotificationPublisher có thể là singleton. Nhiều request có thể gọi publish đồng thời vì JmsTemplate được thiết kế để tái sử dụng sau khi cấu hình. Mỗi thao tác mượn resource theo cơ chế của factory; Session đang được một thao tác sử dụng không bị chia sẻ đồng thời cho thao tác khác.

Không nên tự mở một Session ở field của NotificationPublisher để “tối ưu” thêm. Làm vậy có thể phá vỡ quản lý cache, transaction và thread safety mà Spring cung cấp.

## 8. CachingConnectionFactory và listener container

Consumer bất đồng bộ thường được quản lý bởi Spring JMS listener container như **DefaultMessageListenerContainer** hoặc **SimpleMessageListenerContainer**. Container chịu trách nhiệm tạo và quản lý Session, MessageConsumer, thread và vòng đời listener.

Listener container có cơ chế cache resource riêng, bao gồm cache level/caching policy. Vì vậy, cần tránh bật nhiều lớp cache một cách máy móc:

- Kiểm tra listener container đang cache Connection, Session hay Consumer ở mức nào.
- Không mặc định bật cacheConsumers=true trên CachingConnectionFactory khi listener container cũng quản lý Consumer.
- Với DefaultMessageListenerContainer, cân nhắc cache level và transaction manager đang dùng.
- Kiểm thử reconnect, shutdown, durable subscription và redelivery trên provider thật.

Với các listener container quản lý lâu dài, container thường giữ consumer/session trong vòng đời của listener thay vì tạo lại cho mỗi message. CachingConnectionFactory có thể vẫn chia sẻ Connection hoặc hỗ trợ các thao tác khác, nhưng không nên coi nó là cơ chế duy nhất quản lý consumer concurrency.

## 9. Transaction và acknowledgement khi cache Session

Cache chỉ thay đổi việc tái sử dụng resource; nó không thay đổi bản chất transaction và acknowledgement của JMS.

### 9.1. Session theo acknowledgement mode

Vì Session được cache theo acknowledgement mode, một thao tác dùng AUTO_ACKNOWLEDGE không lấy nhầm Session transacted. Nếu ứng dụng có nhiều kiểu thao tác, hãy kiểm tra cách JmsTemplate và transaction manager yêu cầu Session.

### 9.2. Transaction gắn với Session

Một JMS transacted Session có transaction riêng. commit() và rollback() áp dụng cho thao tác gửi/nhận thuộc Session đó. Việc trả Session về cache không biến transaction thành transaction chung với các Session khác.

Khi Spring quản lý transaction, hãy để JmsTransactionManager hoặc transaction manager tương ứng quản lý resource theo cấu hình. Không gọi commit/rollback thủ công trên Session đang được Spring transaction manager quản lý.

### 9.3. Database và JMS không tự thành một giao dịch nguyên tử

CachingConnectionFactory không tạo distributed transaction. Nếu cần atomicity giữa database và JMS, phải dùng JTA/XA với provider và database hỗ trợ, hoặc dùng Transactional Outbox phù hợp kiến trúc.

Outbox ghi dữ liệu nghiệp vụ và ý định phát message trong cùng database transaction, sau đó relay gửi message. Consumer vẫn cần idempotency để xử lý duplicate.

## 10. Cách chọn sessionCacheSize và đo hiệu năng

Không nên chọn cache size chỉ vì một con số phổ biến. Hãy đo concurrency và thời gian giữ resource:

1. Ước lượng số thao tác gửi/nhận đồng thời.
2. Xác định số acknowledgement mode thực sự dùng.
3. Đo thời gian tạo Session và Producer trên provider.
4. Đo throughput và latency trước/sau khi bật cache.
5. Quan sát số Session đang mở và tài nguyên provider sử dụng.
6. Điều chỉnh cache size để cân bằng tái sử dụng với số resource nhàn rỗi giữ lại.

Nếu cache size quá nhỏ so với concurrency thường xuyên, các Session dư có thể bị đóng khi trả về và phải tạo lại ở lần sau. Nếu cache quá lớn, ứng dụng giữ nhiều Session nhàn rỗi, làm tăng tài nguyên phía client và broker.

Cần phân biệt peak concurrency ngắn hạn với concurrency ổn định. Cache có ích nhất khi resource được tái sử dụng thường xuyên. Nếu workload rất thưa, cache lớn có thể không đem lại lợi ích tương xứng.

## 11. CachingConnectionFactory không phải connection pool

| Tiêu chí | CachingConnectionFactory | Provider connection pool |
|---|---|---|
| Connection | Chia sẻ một Connection theo mô hình SingleConnectionFactory | Có thể quản lý nhiều Connection vật lý |
| Session | Cache Session sau khi trả về | Thường pool/lease Session theo cấu hình |
| Producer | Có cache theo Session | Tùy implementation/pool |
| Consumer | Mặc định không cache; có thể bật | Tùy provider/pool |
| Mục tiêu | Giảm chi phí tạo lại resource JMS trong mô hình shared connection | Quản lý số lượng và tái sử dụng nhiều kết nối/tài nguyên |
| Giới hạn concurrency | Không phải semaphore giới hạn số Session đang hoạt động | Có thể có giới hạn pool rõ ràng |

Nếu cần cô lập tải bằng nhiều Connection vật lý, giới hạn số connection tới broker hoặc pool theo ứng dụng, hãy dùng provider pool phù hợp. Không nên kỳ vọng tăng sessionCacheSize sẽ tạo thêm Connection.

## 12. Các lỗi thường gặp

### 12.1. Tăng sessionCacheSize nhưng vẫn dùng chung Session

Tăng cache size không làm Session thread-safe. Mỗi thao tác đồng thời vẫn cần Session riêng; cache chỉ tái sử dụng sau khi thao tác trả Session.

### 12.2. Nhầm cache size với số worker tối đa

Cache size là số Session nhàn rỗi được giữ lại theo acknowledgement mode. Khi concurrency vượt mức đó, factory vẫn có thể tạo thêm Session rồi đóng những Session dư khi trả về.

### 12.3. Bật cacheConsumers mà không kiểm thử

Consumer giữ selector, subscription và trạng thái nhận message. Cache Consumer có thể làm hành vi nhận khác kỳ vọng hoặc xung đột với listener container. Mặc định false là lựa chọn an toàn khi chưa có yêu cầu đo đạc cụ thể.

### 12.4. Dùng CachingConnectionFactory như một pool nhiều Connection

Factory chia sẻ một Connection. Nếu cần nhiều Connection vật lý hoặc giới hạn pool, chọn provider pool thay vì chỉ tăng cache Session.

### 12.5. Đóng shared Connection trong lúc worker khác đang chạy

Connection dùng chung có vòng đời do factory quản lý. Không tự đóng target Connection từ một worker. Hãy để Spring container đóng factory khi ứng dụng shutdown.

### 12.6. Double caching với listener container

Listener container có cơ chế cache Session/Consumer riêng. Bật thêm consumer caching ở ConnectionFactory có thể tạo hai tầng giữ resource, gây khó quan sát lifecycle và reconnect. Cần chọn chiến lược phù hợp với loại container và provider.

### 12.7. Không theo dõi reconnect và lỗi provider

Khi Connection bị lỗi, factory có thể reset/reconnect theo cấu hình. Ứng dụng vẫn cần theo dõi exception, broker availability, số lần reconnect và message retry/redelivery. Cache không thay thế giám sát broker.

## 13. Ví dụ Java 17: mô phỏng cache Session theo acknowledgement mode

Ví dụ sau dùng JDK thuần để mô phỏng một cache Session nhỏ. Nó minh họa Session được cache theo acknowledgement mode, Producer được cache theo destination trong Session và mỗi lần mượn có quyền sử dụng độc lập. Đây không phải implementation của Spring CachingConnectionFactory hoặc JMS provider.

Tạo file **SessionResourceCacheDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class SessionResourceCacheDemo {

    enum AckMode {
        AUTO_ACKNOWLEDGE,
        CLIENT_ACKNOWLEDGE,
        TRANSACTED
    }

    record DemoProducer(String id, String destination) {}

    static final class DemoSession {
        private final String id;
        private final AckMode ackMode;
        private final Map<String, DemoProducer> producers = new HashMap<>();

        DemoSession(String id, AckMode ackMode) {
            this.id = id;
            this.ackMode = ackMode;
        }

        String id() {
            return id;
        }

        DemoProducer producer(
                String destination,
                AtomicInteger producerIds) {
            return producers.computeIfAbsent(
                    destination,
                    key -> new DemoProducer(
                            "producer-" + producerIds.incrementAndGet(),
                            key
                    )
            );
        }
    }

    static final class SessionLease implements AutoCloseable {
        private final DemoCachingConnectionFactory factory;
        private final DemoSession session;
        private boolean closed;

        SessionLease(
                DemoCachingConnectionFactory factory,
                DemoSession session) {
            this.factory = factory;
            this.session = session;
        }

        DemoSession session() {
            if (closed) {
                throw new IllegalStateException("Lease is closed");
            }
            return session;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                factory.release(session);
            }
        }
    }

    static final class DemoCachingConnectionFactory {
        private final int sessionCacheSize;
        private final Map<AckMode, ArrayDeque<DemoSession>> cache =
                new EnumMap<>(AckMode.class);
        private final AtomicInteger sessionIds = new AtomicInteger();
        private final AtomicInteger producerIds = new AtomicInteger();

        DemoCachingConnectionFactory(int sessionCacheSize) {
            this.sessionCacheSize = sessionCacheSize;
            for (AckMode mode : AckMode.values()) {
                cache.put(mode, new ArrayDeque<>());
            }
        }

        synchronized SessionLease acquire(AckMode mode) {
            DemoSession session = cache.get(mode).pollFirst();

            if (session == null) {
                session = new DemoSession(
                        "session-" + sessionIds.incrementAndGet(),
                        mode
                );
            }

            return new SessionLease(this, session);
        }

        synchronized void release(DemoSession session) {
            ArrayDeque<DemoSession> sessions = cache.get(session.ackMode);

            if (sessions.size() < sessionCacheSize) {
                sessions.addLast(session);
            }
            // Nếu cache đã đủ, mô hình bỏ resource dư.
        }

        AtomicInteger producerIds() {
            return producerIds;
        }
    }

    public static void main(String[] args) throws Exception {
        DemoCachingConnectionFactory factory =
                new DemoCachingConnectionFactory(1);

        try (SessionLease lease =
                     factory.acquire(AckMode.AUTO_ACKNOWLEDGE)) {
            DemoProducer producer = lease.session().producer(
                    "orders.queue",
                    factory.producerIds()
            );
            System.out.println(
                    "First lease: " + lease.session().id()
                            + ", " + producer.id());
        }

        try (SessionLease lease =
                     factory.acquire(AckMode.AUTO_ACKNOWLEDGE)) {
            DemoProducer producer = lease.session().producer(
                    "orders.queue",
                    factory.producerIds()
            );
            System.out.println(
                    "Second lease: " + lease.session().id()
                            + ", " + producer.id());
        }

        try (SessionLease lease =
                     factory.acquire(AckMode.TRANSACTED)) {
            DemoProducer producer = lease.session().producer(
                    "orders.queue",
                    factory.producerIds()
            );
            System.out.println(
                    "Transacted lease: " + lease.session().id()
                            + ", " + producer.id());
        }

        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch acquired = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            var task = (java.util.concurrent.Callable<String>) () -> {
                try (SessionLease lease =
                             factory.acquire(AckMode.AUTO_ACKNOWLEDGE)) {
                    acquired.countDown();
                    release.await();
                    return lease.session().id();
                }
            };

            Future<String> first = workers.submit(task);
            Future<String> second = workers.submit(task);

            if (!acquired.await(5, java.util.concurrent.TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Workers did not acquire sessions in time");
            }

            release.countDown();

            boolean distinctSessions =
                    !first.get().equals(second.get());

            System.out.println(
                    "Concurrent leases are distinct: " + distinctSessions);
        }
        finally {
            release.countDown();
            workers.shutdown();
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac SessionResourceCacheDemo.java
java SessionResourceCacheDemo
~~~

Kết quả:

~~~text
First lease: session-1, producer-1
Second lease: session-1, producer-1
Transacted lease: session-2, producer-2
Concurrent leases are distinct: true
~~~

Hai lần mượn AUTO_ACKNOWLEDGE tuần tự tái sử dụng cùng Session và Producer. Session TRANSACTED nằm trong nhóm cache khác. Hai worker đồng thời nhận hai Session khác nhau dù cache size chỉ là 1; điều này minh họa cache size không phải giới hạn concurrency.

## 14. Quy trình triển khai và kiểm thử

Khi đưa CachingConnectionFactory vào ứng dụng, nên thực hiện theo thứ tự:

1. Xác định target ConnectionFactory do provider cung cấp.
2. Bọc target factory bằng CachingConnectionFactory và dùng bean cache làm ConnectionFactory chính cho JmsTemplate.
3. Bắt đầu với cacheProducers=true, cacheConsumers=false.
4. Chọn sessionCacheSize dựa trên concurrency và số acknowledgement mode thực tế.
5. Xác nhận Session không được chia sẻ đồng thời giữa các thread.
6. Kiểm tra transaction, acknowledgement và reconnect trên provider thật.
7. Nếu dùng listener container, kiểm tra cache level của container trước khi bật thêm consumer cache.
8. Đo throughput, latency, số Session/Producer được tạo và số resource đang mở.
9. Kiểm thử shutdown và reconnect để bảo đảm resource được giải phóng đúng vòng đời.

Các test quan trọng gồm gửi đồng thời từ nhiều thread, xác nhận message đến đúng destination, kiểm tra producer được tái sử dụng, kiểm tra Session tách biệt theo acknowledgement mode và kiểm tra hành vi khi broker ngắt kết nối. Nếu bật cache Consumer, cần test riêng selector, subscription, receive timeout và việc đóng/reconnect.

CachingConnectionFactory giúp tái sử dụng JMS resource và giảm chi phí tạo Session/Producer trong các ứng dụng gửi nhận thường xuyên. Hiểu rõ cache theo acknowledgement mode, cache Producer bên trong Session và việc Consumer mặc định không được cache giúp cấu hình đúng. Cache size chỉ quyết định số resource nhàn rỗi được giữ lại; mỗi thao tác đồng thời vẫn cần Session riêng. Kết hợp JmsTemplate hoặc listener container với lifecycle rõ ràng sẽ giúp ứng dụng tận dụng cache mà vẫn giữ đúng semantics của JMS.