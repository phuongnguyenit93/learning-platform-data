# TaskExecutor và số luồng thực tế của DefaultMessageListenerContainer trong Spring JMS

## 1. Câu hỏi thực tế: cấu hình 2–6 consumers thì ứng dụng có bao nhiêu thread?

Trong Spring JMS, `DefaultMessageListenerContainer` (thường viết tắt là **DMLC**) là listener container phổ biến để nhận message bất đồng bộ. Một cấu hình dễ gặp:

~~~java
factory.setConcurrency("2-6");
~~~

Nhiều người diễn giải câu lệnh này thành “Spring luôn tạo sáu thread” hoặc “ứng dụng chỉ có tối đa sáu thread”. Cả hai đều **không chính xác**.

`2-6` là **giới hạn số JMS consumer/invoker của một listener container**: thông thường container duy trì mức tối thiểu hai và có thể tăng động tới sáu khi lưu lượng message đủ lớn. Nó không có nghĩa lúc nào sáu handler đều đang thực thi. Số thread **thực sự tồn tại, đang chạy, đang chờ broker, đang xử lý nghiệp vụ** còn tùy:

1. `TaskExecutor` được gắn vào DMLC.
2. Cách executor tạo, giữ và tái sử dụng thread.
3. `concurrentConsumers` và `maxConcurrentConsumers`.
4. Lượng message, tốc độ xử lý và receive timeout.
5. Quy tắc tăng/giảm invoker khi có hoặc không có message.
6. Năng lực broker, quyền tạo consumer, kết nối và quá trình recovery.
7. Giới hạn CPU, container runtime, pool ngoài và tài nguyên khác.

~~~text
                          @JmsListener / DMLC
                                   |
                concurrency: concurrentConsumers=2
                             maxConcurrentConsumers=6
                                   |
                                   v
                            JMS invoker tasks
                              2 ... tối đa 6
                                   |
                                   v
                               TaskExecutor
                      +---------------------------+
                      | SimpleAsyncTaskExecutor  |
                      | hoặc ThreadPoolTaskExecutor
                      +---------------------------+
                                   |
                      Thread thật thực thi invoker
                                   |
                      JMS receive -> handler -> ACK/commit
                                   |
                               Broker Queue
~~~

**Ý chính:** Đừng dùng duy nhất số `concurrency` để khẳng định thread count, và đừng dùng duy nhất thread count để khẳng định số message đang được xử lý. Cần đo **các đại lượng khác nhau**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `TaskExecutor`, consumer, invoker task, Java thread và handler đang bận.
- Hiểu executor mặc định của `DefaultMessageListenerContainer`.
- Giải thích vì sao `setConcurrency("2-6")` không phải số thread tức thời.
- Cấu hình `ThreadPoolTaskExecutor` đúng cách, tránh queue của executor làm nghẽn việc tăng consumer.
- Đọc `getScheduledConsumerCount()`, `getActiveConsumerCount()` và metric thread pool.
- Chạy demo Java 17/Spring Boot 3/Artemis và quan sát thread names, handler concurrency.
- Nhận biết lỗi thread starvation, task rejection, mất ordering và ACK/transaction.

## 2. Kiến trúc: một consumer không đồng nghĩa một message đang xử lý

DMLC triển khai chiến lược **polling**: mỗi *async message listener invoker* lấy hoặc tạo JMS Session/MessageConsumer, chờ message, gọi listener rồi tiếp tục vòng nhận theo cấu hình. TaskExecutor chạy **các invoker**, không đơn giản tạo một task mới cho từng message.

~~~text
TaskExecutor thread: orders-jms-1
    |
    +-- Invoker A
          |
          +-- JMS Session A / MessageConsumer A
          +-- receive() đợi message
          +-- gọi listener.handle(message 1)
          +-- transaction/ack theo container
          +-- receive() lại
          +-- xử lý message kế tiếp

TaskExecutor thread: orders-jms-2
    |
    +-- Invoker B
          |
          +-- JMS Session B / MessageConsumer B
          +-- receive() đợi message
          +-- gọi listener.handle(message 2)
          +-- ...
~~~

Trong một cấu hình thông thường, mỗi invoker xử lý message tuần tự trên thread đang chạy invoker. Một invoker có thể sống lâu, giữ thread trong lúc **chờ broker**; thread tồn tại/đang hoạt động ở executor chưa chắc đang thực thi business handler.

Điểm khác biệt với mẫu quen thuộc:

~~~java
executor.execute(() -> processOneMessage(message));
~~~

DMLC **không mặc định** tách một task riêng cho từng message như đoạn trên. Task của DMLC quản lý cả chu kỳ nhận message và callback. Vì vậy, một thread pool “có 20 worker threads” nhưng listener container chỉ cấu hình tối đa 3 consumers thì không tự nhiên có 20 message handlers chạy song song.

### 2.1. Các khái niệm không được gộp làm một

| Đại lượng | Nghĩa chính xác |
| --- | --- |
| `concurrentConsumers` | Mức consumer tối thiểu được cấu hình cho một DMLC |
| `maxConcurrentConsumers` | Trần consumer/invoker mà DMLC có thể lên tới |
| `scheduledConsumerCount` | Số consumer invoker đang được container lên lịch |
| `activeConsumerCount` | Số invoker thực sự đang hoạt động/thực thi theo container |
| `ThreadPoolTaskExecutor.poolSize` | Số thread hiện có trong thread pool (nếu dùng pool) |
| `ThreadPoolTaskExecutor.activeCount` | Số thread pool đang bận chạy task, kể cả có thể đang chờ JMS receive |
| `handlerInFlight` | Số lần thực thi business method đang diễn ra (cần tự đo) |
| `brokerConsumerCount` | Số consumer broker thấy đã đăng ký; có thể chênh khi recovery/caching |
| `Runtime.availableProcessors()` | Ước lượng CPU khả dụng cho JVM, **không** phải số consumer |

Nếu số liệu khác nhau, chưa chắc có bug: chúng đo **các lớp khác nhau** và có thể thay đổi ngay giữa hai lần quan sát.

## 3. Executor mặc định: SimpleAsyncTaskExecutor

Theo Javadoc Spring Framework, nếu không gọi `setTaskExecutor(...)`, DMLC tự tạo `SimpleAsyncTaskExecutor`.

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();
// Không gọi container.setTaskExecutor(...)
// => container dùng SimpleAsyncTaskExecutor nội bộ.
~~~

`SimpleAsyncTaskExecutor` **không phải thread pool tái sử dụng thread**. Nó tạo thread mới cho các lần thực thi task; một task listener invoker có thể giữ thread trong thời gian dài vì task thực hiện chu kỳ polling.

Hệ quả:

- Mức mặc định của DMLC là `concurrentConsumers=1` và `maxConcurrentConsumers=1` nếu chưa thay đổi.
- Với `setConcurrency("2-6")`, tối thiểu hai invokers được duy trì khi container hoạt động ổn định; các invokers dư có thể được tạo thêm khi có lưu lượng.
- Các task invoker thường chạy lâu; “SimpleAsync” không đồng nghĩa “tạo thread mới sau **mỗi** message”.
- Khi invoker kết thúc và được lên lịch lại, executor này có thể dùng thread Java mới thay vì tái sử dụng thread cũ.
- Không tồn tại `getPoolSize()` cho executor mặc định như với `ThreadPoolTaskExecutor`, vì không có pool theo nghĩa đó.
- Dùng thread dump và metric của DMLC để hiểu runtime, thay vì cố lấy một chỉ số pool không tồn tại.

### 3.1. Spring 6.2 và virtual threads

Ở Spring Framework **6.2 trở lên**, DMLC có khả năng cấu hình virtual threads cho executor mặc định, dành cho Java 21+. Điều đó **không áp dụng** cho dự án Java 17/Spring 6.1 trong ví dụ phía dưới. Virtual thread không làm mất giới hạn `concurrentConsumers` và `maxConcurrentConsumers`; broker, session, message processing và DB vẫn cần giới hạn tài nguyên riêng.

Khi đọc tài liệu, phải đối chiếu **đúng phiên bản**: một API mới của 6.2 không nhất thiết có trong 6.1. Hành vi idle rescheduling cũng được điều chỉnh giữa các bản. Đừng copy cấu hình virtual-thread từ Javadoc bản mới rồi kỳ vọng Java 17 biên dịch.

## 4. Concurrency: minimum, maximum và số thực tế

DMLC có thể được cấu hình bằng một trong hai cách:

~~~java
// Cách 1: cấu hình tách:
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(6);

// Cách 2: dùng một String range:
container.setConcurrency("2-6");
~~~

`setConcurrency("2-6")` tương đương ý định đặt minimum=2 và maximum=6. Theo Spring, dạng chỉ một số như `setConcurrency("6")` được diễn giải là **minimum=1, maximum=6**, không phải giữ cố định sáu consumers.

| Cấu hình | Minimum | Maximum | Ý nghĩa |
| --- | ---: | ---: | --- |
| Không cấu hình | 1 | 1 | Một invoker thường trực |
| `setConcurrency("2")` | 1 | 2 | Có thể mở rộng lên hai |
| `setConcurrency("2-6")` | 2 | 6 | Có mức nền hai, mở rộng theo tải |
| `setConcurrentConsumers(4)` cùng maximum mặc định | 4 | Ít nhất 4 | Setter có thể nâng max khi minimum mới lớn hơn max cũ |
| `setConcurrentConsumers(2); setMaxConcurrentConsumers(6)` | 2 | 6 | Đặt hai giới hạn tường minh |

Không tăng consumers cho Topic một cách máy móc. Với Queue, nhiều consumer chia công việc; với Topic không có subscription phù hợp, nhiều consumer có thể nhận cùng một thông điệp theo các subscription riêng. Với các ứng dụng phụ thuộc thứ tự, tăng consumer có thể phá vỡ ordering mong muốn.

### 4.1. Vì sao số scheduled tăng dần, không lên maximum ngay?

DMLC tạo invoker bổ sung khi phát hiện message đến và thấy chưa vượt `maxConcurrentConsumers` cùng giới hạn idle consumer. Nó không gọi “start max threads” chỉ vì bạn khai báo upper bound.

Ví dụ với `2-6`:

~~~text
Queue rỗng hoặc tải thấp:
  minimum 2 invokers thường được duy trì

Lưu lượng tăng:
  2 -> 3 -> 4 -> ... có thể lên 6 invokers

Lưu lượng giảm:
  surplus invokers được nhả sau điều kiện idle
  thường trở về mức minimum=2
~~~

Đây là **mô hình**, không phải output chính xác theo từng giây. Tốc độ tăng/giảm còn chịu ảnh hưởng receive timeout, idle settings, cấu hình executor và broker.

### 4.2. Các thông số điều chỉnh scaling

DMLC có các setter:

| Tùy chọn | Vai trò |
| --- | --- |
| `setIdleConsumerLimit(int)` | Số invoker idle tối đa cho phép khi xem xét có tạo invoker mới hay không |
| `setIdleTaskExecutionLimit(int)` | Giới hạn lần một task được xem là idle trước khi surplus task ngừng |
| `setIdleReceivesPerTaskLimit(int)` | Số lần receive không có message liên tiếp trước khi xem task là idle |
| `setMaxMessagesPerTask(int)` | Giới hạn số *receive attempts* cho một lần task thực thi |
| `setReceiveTimeout(long)` | Mỗi lần receive có thể đợi bao lâu để có message |
| `setTaskExecutor(Executor)` | Nơi thực thi và tái lịch các invoker tasks |

Các thuộc tính này tương tác với nhau. Không coi chúng là những công tắc độc lập để “mở thêm thread” mà không tính lại hành vi container.

**Quan trọng:** `maxMessagesPerTask` tính cả những lần thử `receive` không lấy được message. Nếu đặt `20` mà mỗi lần receive timeout, một task có thể kết thúc sau 20 lượt không nhận được message, không phải sau “20 message thật đã xử lý”.

### 4.3. Executor có thể ảnh hưởng mặc định của task lifecycle

Javadoc DMLC nêu:

- Với executor thông thường, task có thể sống lâu, nhận nhiều message liên tiếp.
- Với `SchedulingTaskExecutor` báo ưu tiên short-lived tasks, DMLC có thể mặc định dùng `maxMessagesPerTask=10` để trả thread về pool thường xuyên hơn.
- Với simple/non-pooling executor, chiến lược kết thúc invoker idle thường khác, nhất là surplus consumers.

Hành vi chi tiết của idle scheduling khác giữa Spring 6.1 và 6.2; hãy đọc **Javadoc phiên bản đã dùng** trước khi copy một số mặc định. Nếu cần hành vi xác định, đặt giới hạn tường minh và test trên workload thực tế, nhưng tránh chỉnh quá nhiều knob trước khi có số liệu.

## 5. TaskExecutor cho DMLC không phải @Async executor

Spring có nhiều nơi dùng `Executor`: task cho `@Async`, scheduler cho `@Scheduled`, một executor phục vụ HTTP request, và executor dành cho JMS listener invokers.

**Chúng không tự động là cùng một pool.** Ví dụ:

~~~properties
spring.task.execution.pool.core-size=8
spring.task.execution.pool.max-size=16
~~~

Các key Spring Boot task execution chỉ điều khiển executor auto-configured tương ứng. Chúng **không mặc nhiên đổi** executor bên trong DMLC nếu không có wiring cụ thể.

Muốn gắn một executor vào listener, có thể làm tại container:

~~~java
container.setTaskExecutor(myExecutor);
~~~

Hoặc qua `DefaultJmsListenerContainerFactory`:

~~~java
factory.setTaskExecutor(myExecutor);
~~~

`myExecutor` phải là bean hoặc instance thực thi giao diện `java.util.concurrent.Executor` tương thích. Spring hỗ trợ `TaskExecutor` qua cùng abstraction.

**Cảnh báo thiết kế:** dùng chung pool giữa JMS invokers chạy lâu và tác vụ `@Async` ngắn có thể gây starvation. Những invoker chờ JMS vẫn chiếm threads của pool; tác vụ khác có thể nằm queue dù ứng dụng không xử lý message nào.

## 6. ThreadPoolTaskExecutor: khi nào tốt, khi nào gây nghẽn?

`ThreadPoolTaskExecutor` là executor dựa trên `ThreadPoolExecutor` của JDK, có:

- `corePoolSize`: số thread lõi.
- `maxPoolSize`: giới hạn số thread pool.
- `queueCapacity`: khả năng xếp hàng task trước khi tạo thêm thread đến maximum.
- `keepAliveSeconds`: thời gian giữ non-core idle thread.
- `threadNamePrefix`: cách nhận diện thread trong logs/dump.
- `getPoolSize()` và `getActiveCount()`: metric runtime của executor.

Nhưng DMLC **không** đơn giản nộp một task ngắn cho từng message. Nó nộp các invoker tasks, thường thực hiện cả receive loop và handler. Nếu cấu hình pool không phù hợp, có thể không đủ thread để chạy số invoker bạn yêu cầu.

### 6.1. Bẫy queueCapacity quá lớn

Giả sử:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(100);
~~~

Khi hai core threads đang chạy hai invoker dài hạn, những invoker mới thường được **xếp vào queue của executor**. Pool có thể không tăng lên sáu thread cho đến khi queue đầy theo quy tắc `ThreadPoolExecutor`.

Tình huống:

~~~text
DMLC: concurrency=2-6
Executor: core=2, max=6, queueCapacity=100

2 invokers đang chạy -> chiếm 2 core threads
DMLC muốn lên lịch invoker thứ 3:
  executor xếp task vào queue
  không cấp thread thứ 3 ngay
DMLC metrics có thể:
  scheduled=3, active=2
Pool:
  poolSize=2, activeCount=2
~~~

Vì vậy **maxPoolSize=6 không có nghĩa pool sẽ tự lên sáu** khi queueCapacity=100. Với mục tiêu cho invokers có thread chạy sớm, cân nhắc queue nhỏ hoặc `queueCapacity=0`, và giới hạn maximum phù hợp.

### 6.2. queueCapacity=0 giúp mở thread nhanh nhưng cần giới hạn

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(0);
executor.setThreadNamePrefix("orders-jms-");
~~~

Với queueCapacity=0, task mới không nằm chờ trong queue có dung lượng lưu trữ, nên pool thường tạo thread mới đến maximum nếu core threads đang bận. Nhưng nếu đã chạm maximum, executor **có thể từ chối task** bằng `TaskRejectedException`. DMLC có cơ chế ghi log/tái lịch nhất định, song không được suy ra task rejection là vô hại.

Một pool dành riêng cho JMS invokers giúp phân biệt resource với `@Async`/web executor, nhất là khi receive tasks sống lâu. Đừng dùng chung một pool `queueCapacity=0` giữa hàng chục listeners mà không tính tổng nhu cầu.

### 6.3. Vì sao nhiều thread pool không đồng nghĩa nhiều JMS consumers?

Nếu pool có maxPoolSize=20 nhưng DMLC maxConcurrentConsumers=4, container không lên quá bốn JMS invokers theo giới hạn của nó. Pool có thể có thread không phục vụ JMS hoặc đang idle. Ngược lại, nếu DMLC muốn sáu nhưng pool chỉ có bốn slots chạy task, một số invokers có thể chưa chạy.

Nói cách khác:

~~~text
Số JMS invokers đang chạy
  <= giới hạn DMLC
  và còn bị ràng buộc bởi executor/broker/resources.

Số handler executions đang diễn ra
  <= số invokers thực sự đang chạy
  và có thể thấp hơn nhiều nếu chúng đang receive-wait.
~~~

Không lấy số CPU cores làm số JMS consumers theo một công thức cố định: nếu handler chủ yếu chờ DB/network thì concurrency phù hợp có thể khác với CPU-bound workload. Phải load test và đo saturation.

## 7. Dùng các getter nào để biết "số thực tế"?

DMLC có getter hữu ích:

~~~java
int configuredMin = container.getConcurrentConsumers();
int configuredMax = container.getMaxConcurrentConsumers();

int scheduled = container.getScheduledConsumerCount();
int active = container.getActiveConsumerCount();
~~~

Theo Javadoc:

- `getConcurrentConsumers()` / `getMaxConcurrentConsumers()` trả về **giá trị cấu hình**.
- `getScheduledConsumerCount()` là số invokers đã được container lên lịch, **có thể lớn hơn active** nếu executor chưa có thread để chạy một số invokers.
- `getActiveConsumerCount()` là số invokers đang thực sự hoạt động theo DMLC, **không đồng nghĩa số method handler đang chạy**.
- Khi container startup, shutdown hoặc recovering, các số có thể thay đổi hoặc ở mức thấp hơn bình thường. Đừng biến một ảnh chụp vào đúng lúc failure thành kết luận cấu hình luôn sai.

### 7.1. Từ @JmsListener tới container thực tế qua registry

Annotation `@JmsListener` dùng `JmsListenerEndpointRegistry` để quản lý các listener containers. Với listener có `id="ordersTasks"`:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

// Snippet trong service đã inject registry:
MessageListenerContainer value =
        registry.getListenerContainer("ordersTasks");
if (value instanceof DefaultMessageListenerContainer dmlc) {
    System.out.println(dmlc.getScheduledConsumerCount());
    System.out.println(dmlc.getActiveConsumerCount());
}
~~~

Đây là snippet, không phải một file Java độc lập. Dùng `instanceof` để không ép kiểu sai nếu ứng dụng dùng container factory khác.

**Lưu ý:** các container được tạo từ `@JmsListener` không nhất thiết tồn tại dưới dạng bean của ApplicationContext với tên annotation id. Registry là đường truy cập đúng để quản lý chúng.

### 7.2. Đo pool và business handlers riêng

Khi dùng `ThreadPoolTaskExecutor`:

~~~java
int poolSize = ordersExecutor.getPoolSize();
int activePoolThreads = ordersExecutor.getActiveCount();
~~~

Hai metric này vẫn chưa cho biết có bao nhiêu message handler đang chạy. Một invoker có thể chiếm thread, đang `MessageConsumer.receive()` chờ broker, không xử lý business.

Muốn đo handler concurrency, đặt instrumentation **bên trong handler**:

~~~java
private final AtomicInteger inFlight = new AtomicInteger();
private final AtomicInteger peak = new AtomicInteger();

public void onMessage(String body) {
    int now = inFlight.incrementAndGet();
    peak.accumulateAndGet(now, Math::max);
    try {
        processBusiness(body);
    } finally {
        inFlight.decrementAndGet();
    }
}
~~~

Đây là snippet trong class đã có `processBusiness`, import `AtomicInteger`. `inFlight` phản ánh số lần callback đang xử lý trên instance đó; `peak` phản ánh đỉnh được quan sát **kể từ khi bean khởi tạo**, không phải số callback đồng thời hiện tại. Với nhiều pods/instances, phải tổng hợp metric theo từng instance và không nhầm với một số toàn cluster.

## 8. Dự án Java 17 + Spring Boot 3.3 + Artemis: đo bốn loại số

Bài lab tạo một Queue, một listener `@JmsListener` với DMLC, một executor pool chuyên dụng và một sender gửi nhiều message. Mỗi handler ngủ một khoảng nhỏ để mô phỏng I/O, từ đó nhiều message có thể được xử lý song song.

**Mục tiêu:** quan sát sự khác biệt giữa:

1. Giới hạn min/max được cấu hình.
2. Số invokers scheduled/active của DMLC.
3. Thread pool size/active.
4. Số handler thực sự đang xử lý tại cùng thời điểm.

### 8.1. Artemis local

Máy có Docker:

~~~bash
docker run --detach --rm --name artemis-taskexecutor-lab -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest
~~~

Đợi broker sẵn sàng và xem log:

~~~bash
docker logs artemis-taskexecutor-lab
~~~

Tài khoản `demo/demo` chỉ dành cho lab. Nếu broker chặn auto-create Queue, tạo `orders.tasks.demo` trước và cấp quyền gửi/nhận. Dùng Queue sạch hoặc cấu hình tên riêng mỗi lần chạy để message cũ không làm sai kết quả.

### 8.2. Cấu trúc file

~~~text
jms-executor-lab/
  settings.gradle
  build.gradle
  src/main/resources/application.properties
  src/main/java/demo/jms/
    ExecutorLabApplication.java
    JmsWorkerConfig.java
    CountingOrderListener.java
    DemoSender.java
  src/test/java/demo/jms/
    CountingOrderListenerTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-executor-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là bộ dependency cố định để minh họa, không tuyên bố là bản release mới nhất. Dùng JDK 17+ và Gradle tương thích; Spring Boot 3 yêu cầu `jakarta.jms` (không trộn `javax.jms` đời cũ).

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.cache.enabled=false

app.jms.destination=${JMS_QUEUE:orders.tasks.demo}
~~~

Các placeholder của Spring thực tế có dạng `${...}` được thay thành cú pháp chuẩn có dấu dollar khi lưu bài. `spring.jms.cache.enabled=false` làm lab đơn giản hơn về connection factory lifecycle: DMLC quản lý consumer/session của mình; đây không phải tuyên bố rằng caching luôn sai trong production.

Chỉ dùng fallback credential `demo` ở local. Trong production, inject secret/credentials an toàn và cấp ACL theo destination.

### 8.4. Entry point

File `src/main/java/demo/jms/ExecutorLabApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ExecutorLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExecutorLabApplication.class, args);
    }
}
~~~

`@EnableJms` bật xử lý `@JmsListener`. Spring Boot cung cấp `ConnectionFactory`/`JmsTemplate` khi Artemis starter và cấu hình hợp lệ.

### 8.5. ThreadPoolTaskExecutor riêng cho JMS và factory

File `src/main/java/demo/jms/JmsWorkerConfig.java`:

~~~java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class JmsWorkerConfig {

    @Bean("ordersExecutor")
    ThreadPoolTaskExecutor ordersExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("orders-jms-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(0);
        return executor;
    }

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            @Qualifier("ordersExecutor")
            ThreadPoolTaskExecutor executor) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-4");
        factory.setTaskExecutor(executor);

        // Task tương đối ngắn để pool có cơ hội tái lịch:
        factory.setMaxMessagesPerTask(20);
        factory.setReceiveTimeout(1000L);

        // Chỉ là JMS local session transaction:
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Các điểm cần hiểu:

- `ordersExecutor` là **bean riêng**. Không dùng chung với `@Async` hoặc mọi JMS listener khác nếu chưa tính tổng resource.
- Pool có minimum/core hai, maximum bốn thread; `queueCapacity=0` giúp pool có cơ hội mở thêm thread sớm, thay vì xếp invoker sau các core tasks.
- DMLC cũng có minimum hai và maximum bốn invokers. Hai giới hạn này được cấu hình phù hợp nhau cho lab, nhưng **không bảo đảm bốn threads luôn hoạt động**.
- `setMaxMessagesPerTask(20)` điều khiển số receive attempts một task thực thi, không phải batch size business message độc lập.
- `setReceiveTimeout(1000L)` áp dụng mỗi lần DMLC poll JMS; không phải thời gian timeout của HTTP request hay `JmsTemplate.receive`.
- `setSessionTransacted(true)` thiết lập JMS local transaction: handler thành công có thể commit JMS session; lỗi có thể rollback/redeliver theo broker. Nó không tạo transaction DB+JMS tự động.
- Spring quản lý lifecycle của executor bean. Không gọi `executor.initialize()` thủ công trên bean `@Bean` trong cấu hình này.

### 8.6. Listener có bộ đếm số handler đang xử lý

File `src/main/java/demo/jms/CountingOrderListener.java`:

~~~java
package demo.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class CountingOrderListener {

    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();
    private final AtomicInteger finishedCalls = new AtomicInteger();
    private final CountDownLatch latch = new CountDownLatch(12);

    @JmsListener(
            id = "ordersTasks",
            destination = "${app.jms.destination}",
            containerFactory = "ordersListenerFactory")
    public void onOrder(String body) {
        int current = inFlight.incrementAndGet();
        peak.accumulateAndGet(current, Math::max);

        try {
            // Mô phỏng handler chờ I/O trong 250 ms.
            Thread.sleep(250);
            System.out.printf(
                    "HANDLE body=%s thread=%s inFlight=%d%n",
                    body, Thread.currentThread().getName(),
                    current);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        } finally {
            inFlight.decrementAndGet();
            finishedCalls.incrementAndGet();
            latch.countDown();
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return latch.await(timeout, unit);
    }

    public int peakHandlerConcurrency() {
        return peak.get();
    }

    public int inFlightHandlers() {
        return inFlight.get();
    }

    public int finishedCalls() {
        return finishedCalls.get();
    }
}
~~~

Đây là demo, không phải code business production:

- `inFlight` tăng **ngay khi callback bắt đầu** và giảm trong `finally`.
- `peak` lưu mức song song cao nhất của callback từ khi bean được tạo.
- `finishedCalls` đếm **những lần handler thoát**, kể cả khi có exception, không đếm business commits thành công.
- `CountDownLatch(12)` giúp main chờ 12 lần handler kết thúc; nó không chứng minh ACK, DB commit hoặc exactly-once.
- `Thread.sleep` chỉ mô phỏng I/O; không nên cố tình giữ transaction JMS bằng sleep trong handler production.

### 8.7. Sender và đoạn đo runtime

File `src/main/java/demo/jms/DemoSender.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class DemoSender implements CommandLineRunner {

    private final JmsTemplate template;
    private final JmsListenerEndpointRegistry registry;
    private final ThreadPoolTaskExecutor executor;
    private final CountingOrderListener listener;
    private final String queue;

    public DemoSender(
            JmsTemplate template,
            JmsListenerEndpointRegistry registry,
            @Qualifier("ordersExecutor")
            ThreadPoolTaskExecutor executor,
            CountingOrderListener listener,
            @Value("${app.jms.destination}") String queue) {
        this.template = template;
        this.registry = registry;
        this.executor = executor;
        this.listener = listener;
        this.queue = queue;
    }

    @Override
    public void run(String... args) throws Exception {
        for (int i = 1; i <= 12; i++) {
            template.convertAndSend(queue, "ORDER-" + i);
        }

        boolean done = listener.await(20, TimeUnit.SECONDS);
        var container = registry.getListenerContainer("ordersTasks");

        if (!(container instanceof DefaultMessageListenerContainer dmlc)) {
            throw new IllegalStateException(
                    "ordersTasks is not a DMLC");
        }

        System.out.printf(
                "LIMITS min=%d max=%d%n",
                dmlc.getConcurrentConsumers(),
                dmlc.getMaxConcurrentConsumers());

        System.out.printf(
                "RUNTIME scheduled=%d activeInvokers=%d " +
                "poolSize=%d poolActive=%d handlerInFlight=%d%n",
                dmlc.getScheduledConsumerCount(),
                dmlc.getActiveConsumerCount(),
                executor.getPoolSize(),
                executor.getActiveCount(),
                listener.inFlightHandlers());

        System.out.printf(
                "DONE=%s FINISHED_CALLS=%d HANDLER_PEAK=%d%n",
                done,
                listener.finishedCalls(),
                listener.peakHandlerConcurrency());
    }
}
~~~

**Tại sao phải có `JmsListenerEndpointRegistry`?** Container tạo từ `@JmsListener` được registry quản lý; annotation `id="ordersTasks"` cho phép tìm đúng container. Không giả định DMLC này có thể lấy bằng `applicationContext.getBean("ordersTasks")`.

### 8.8. Chạy và đọc stdout đúng cách

Sau khi Artemis sẵn sàng:

~~~bash
gradle test
gradle bootRun
~~~

Với Queue lab sạch, broker có quyền gửi/nhận và không có competing consumer, chương trình thường in 12 dòng `HANDLE ...` và ba dòng thống kê. **Thứ tự của HANDLE, tên thread, số invokers tại đúng thời điểm lấy snapshot và HANDLER_PEAK là dữ liệu runtime; không cố gán một output cứng.**

Một phần output có tính minh họa:

~~~text
HANDLE body=ORDER-2 thread=orders-jms-2 inFlight=2
HANDLE body=ORDER-1 thread=orders-jms-1 inFlight=1
...
LIMITS min=2 max=4
RUNTIME scheduled=2 activeInvokers=2 poolSize=4 poolActive=2 handlerInFlight=0
DONE=true FINISHED_CALLS=12 HANDLER_PEAK=4
~~~

**Chỉ dòng `LIMITS min=2 max=4` có giá trị cấu hình cố định.** Những số runtime trong ví dụ là **một snapshot minh họa**, không phải stdout bảo đảm; `scheduled` có thể là 2–4 khi hoạt động bình thường, `poolSize` có thể lớn hơn số active, và peak phụ thuộc thời điểm message và tải. Có thể thấy `HANDLER_PEAK=2` hoặc `3` thay vì `4` mà vẫn là hành vi bình thường.

Nếu `DONE=false`, hãy kiểm tra Queue có message cũ, competing consumer, broker chưa sẵn sàng, task rejection, authorization/transaction failure và logs; không kết luận ngay do thiếu thread.

Dừng broker:

~~~bash
docker stop artemis-taskexecutor-lab
~~~

## 9. Một demo Java 17 không cần JMS để hiểu pool size và task queue

Để tách khái niệm thread pool ra khỏi broker, chương trình sau cố ý khóa hai task trong một fixed pool có hai threads rồi nộp thêm hai task đang đợi. Nó chứng minh **bốn task được nộp không đồng nghĩa bốn thread thực thi song song**.

File `ExecutorCapacityProof.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorCapacityProof {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger inFlight = new AtomicInteger();

        try {
            for (int i = 0; i < 4; i++) {
                pool.execute(() -> {
                    inFlight.incrementAndGet();
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        inFlight.decrementAndGet();
                    }
                });
            }

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Threads not started");
            }

            System.out.println("SUBMITTED_TASKS=4");
            System.out.println("POOL_SIZE_LIMIT=2");
            System.out.println(
                    "IN_FLIGHT_DURING_GATE=" + inFlight.get());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac ExecutorCapacityProof.java
java ExecutorCapacityProof
~~~

Output trong điều kiện hai threads được khởi tạo bình thường:

~~~text
SUBMITTED_TASKS=4
POOL_SIZE_LIMIT=2
IN_FLIGHT_DURING_GATE=2
~~~

Hai task đầu chiếm hai threads và chờ ở latch; hai task còn lại nằm chờ trong executor queue. Chương trình không dùng JMS và **không mô phỏng cơ chế nhận broker**; nó chỉ minh họa lý do phải tách *tasks đã nộp*, *threads đang chạy* và *tasks đang đợi*.

## 10. Unit test: giới hạn ở Java code, không xác minh broker

File `src/test/java/demo/jms/CountingOrderListenerTest.java`:

~~~java
package demo.jms;

import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CountingOrderListenerTest {

    @Test
    void recordsHandlerExecution() throws Exception {
        CountingOrderListener listener = new CountingOrderListener();

        listener.onOrder("ORDER-1");

        assertTrue(listener.await(1, TimeUnit.MILLISECONDS) == false);
        assertEquals(1, listener.finishedCalls());
        assertEquals(0, listener.inFlightHandlers());
        assertEquals(1, listener.peakHandlerConcurrency());
    }
}
~~~

Test gọi trực tiếp một handler; vì latch yêu cầu 12 lượt nên `await` chưa hoàn thành sau một lần. Đây là unit test **có thể chạy mà không có broker**, kiểm tra instrumentation, không kiểm tra DMLC thread scheduling.

Mặc dù test có một `Thread.sleep(250)` và `await(1 ms)`, nó xác định vì lời gọi `onOrder` chạy đồng bộ ngay trong test thread và đã kết thúc trước khi assert. Không dùng test này để kết luận Artemis đã tạo một session hoặc ACK thành công.

### 10.1. Integration test cần kiểm chứng điều gì?

Với broker Artemis/Testcontainers:

1. Factory cấu hình `concurrency="2-4"` và pool dedicated 2–4 threads.
2. Endpoint registry có `ordersTasks` và đúng loại DMLC.
3. DMLC báo configured min/max như mong đợi.
4. Có message thật để callback chạy trên tên thread mang prefix `orders-jms-`.
5. Thay đổi tốc độ xử lý và backlog để quan sát `scheduled`, `active` và `handlerInFlight` theo thời gian.
6. Message không mất/không bị xử lý lặp quá mức theo ACK/transaction đã thiết kế.
7. Khi queue rỗng, số surplus invokers có thể giảm theo idle policy.
8. Khi broker restart, container recover và metrics có thể tạm thời chênh lệch.
9. Khi pool quá nhỏ hoặc task bị từ chối, logging/alert phản ánh lỗi.
10. Khi nâng concurrency, handler thread-safe và business ordering phù hợp.

Dùng **thời gian chờ hữu hạn và điều kiện cuối**, không assert rằng tại đúng một millisecond `scheduled==4`. Dynamic scaling là quá trình bất đồng bộ, timing phụ thuộc máy CI.

## 11. Sự khác biệt nguy hiểm với SimpleMessageListenerContainer

Tên `DefaultMessageListenerContainer` và `SimpleMessageListenerContainer` gần nhau, nhưng `setTaskExecutor` **không có cùng ngữ nghĩa**.

- **DMLC:** TaskExecutor thực thi **các polling invoker tasks**. Một invoker thực hiện receive rồi gọi listener trên task thread; container quản lý session/transaction theo cách của DMLC.
- **SimpleMessageListenerContainer:** TaskExecutor có thể được dùng để dispatch listener callback sang thread khác sau khi JMS provider nhận message. Theo Javadoc Spring, điều này có thể làm **ACK xảy ra trước khi handler thực thi** và gây kết quả không xác định khi kết hợp với transacted session/client acknowledgment.

Vì vậy, **không sao chép cấu hình TaskExecutor của DMLC sang SMLC rồi cho rằng ACK/transaction giống nhau**. Nếu nghiệp vụ cần rollback JMS khi handler lỗi, hãy chọn container và transaction policy đúng từ đầu, đọc Javadoc riêng của loại container đó.

## 12. Thread dump, JMX và metrics cho production

Với một service production, nên đo nhiều lớp:

| Nguồn | Metric/tín hiệu | Điều nó cho biết |
| --- | --- | --- |
| DMLC JMX/bean | `getConcurrentConsumers()`, `getMaxConcurrentConsumers()` | Min/max cấu hình |
| DMLC runtime | `getScheduledConsumerCount()` | Invokers đã được container lên lịch |
| DMLC runtime | `getActiveConsumerCount()` | Invokers đang thực sự hoạt động |
| ThreadPoolTaskExecutor | `getPoolSize()`, `getActiveCount()` | Tổng thread pool và thread đang chạy task |
| Handler instrumentation | inFlight, peak, duration p95/p99 | Số callback nghiệp vụ đang xử lý và latency |
| Broker Artemis | consumer count, queue depth, delivering, messages added/acked | Trạng thái message và consumer phía broker |
| JVM | thread dump, CPU, GC, blocked threads | Trạng thái hệ thống tổng thể |
| DB | connection pool active/pending, transaction latency | Downstream bottleneck có thể khiến handler treo |

Thread dump có thể thấy nhiều thread `orders-jms-...` ở `WAITING` hoặc `TIMED_WAITING` trong `MessageConsumer.receive`. Điều này thường là **chờ message** bình thường, không phải deadlock. Một thread `RUNNABLE` cũng không chắc đang dùng CPU; native I/O có thể xuất hiện trong trạng thái đó.

### 12.1. Đừng cộng active threads và suy ra tổng messages/second

Một service có tám active threads nhưng mỗi handler mất một giây chờ DB không đồng nghĩa chắc chắn đạt tám messages/second. Còn overhead, transaction, broker prefetch, tải không đồng đều và lỗi retry. Công thức xấp xỉ theo Little's Law chỉ có giá trị khi đo workload ổn định:

~~~text
Concurrency cần thiết ≈ throughput mục tiêu × thời gian xử lý trung bình
~~~

Ví dụ mục tiêu 20 messages/s với handler trung bình 0,1 s có nhu cầu song song khoảng hai trong điều kiện đơn giản. Đây là **ước tính đầu vào để load test**, không phải cấu hình được bảo đảm đúng cho mọi JMS broker hay tail latency. Phải tính DB capacity, peak load và ACK/transaction.

### 12.2. Chú ý số trên nhiều instance

`concurrency="2-6"` là cấu hình **mỗi DMLC trên mỗi app instance**, không phải mức tối đa toàn cluster. Nếu chạy bốn pods, cluster có thể lên tới 24 invokers cùng loại trong điều kiện tương ứng, chứ không phải sáu.

Nhưng không nên xem số đó là chính xác broker consumer count nếu connection failure, scale-down hoặc các replica khác. Theo dõi metric có nhãn instance, queue, listener ID và deployment revision.

## 13. Khi nào nên tăng concurrentConsumers?

Tăng minimum khi:

- Queue có tải đều, muốn giảm latency khi message đến.
- Có đủ DB/API connections để xử lý song song.
- Muốn tránh ramp-up quá trễ ở giai đoạn tải bình thường.
- Handler thread-safe và không phụ thuộc thứ tự tuyệt đối.

Giữ minimum nhỏ, maximum lớn hơn khi:

- Load biến động theo giờ hoặc theo batch.
- Chấp nhận ramp-up theo message traffic.
- Không muốn giữ quá nhiều JMS Sessions/Consumers khi idle.
- Có metrics rõ để điều chỉnh idle behavior.

Không tăng khi:

- Logic nghiệp vụ đòi hỏi xử lý tuần tự và không có key grouping.
- DB pool đang bão hòa; thêm consumers chỉ tạo thêm waiting threads.
- Broker có giới hạn sessions/consumers nghiêm ngặt.
- Consumer chưa idempotent và redelivery gây tác dụng phụ lặp.
- Topic subscription semantics có thể khiến message được xử lý nhiều lần.

## 14. Cấu hình an toàn và khả năng phục hồi

### 14.1. Giới hạn capacity của executor theo nhu cầu JMS

Ví dụ một DMLC tối đa sáu invokers dùng pool dành riêng:

~~~java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(6);
executor.setQueueCapacity(0);
factory.setConcurrency("2-6");
factory.setTaskExecutor(executor);
~~~

Dù matching maximum là cấu hình dễ hiểu, nó không phải định luật. Nếu nhiều DMLCs chia một pool, phải xét **tổng số invokers**, số tasks khác và rescheduling; có thể cần dự phòng capacity hoặc pool riêng.

### 14.2. Không dùng thread pool vô hạn

`ThreadPoolTaskExecutor` mặc định có core pool nhỏ và queue capacity lớn. Nếu đặt `maxPoolSize=Integer.MAX_VALUE` kết hợp queueCapacity=0 mà không có giới hạn phù hợp, surge có thể tạo quá nhiều threads, gây memory pressure và broker/DB overload. Đặt bound rõ cả phía executor và phía DMLC.

### 14.3. Transaction và resource ownership

Một invoker thường quản lý JMS Session/MessageConsumer tương ứng. DMLC có cache level và transaction management riêng. Nếu dùng `CachingConnectionFactory`, pool/executor ngoài hoặc XA transaction manager, cần đánh giá ownership và recovery; đừng tự thêm caching nhiều lớp rồi cho rằng tốt hơn.

### 14.4. Khi handler lỗi

Nếu dùng `sessionTransacted=true`, container có thể rollback JMS session khi handler ném lỗi; message có thể redeliver theo broker policy. Thread count không giải quyết các lỗi dữ liệu vĩnh viễn. Cần DLQ, retry/backoff, event ID và idempotency. Không swallow exception rồi tính message là thành công.

### 14.5. Order và competing consumers

Nhiều consumers trong cùng Queue có thể xử lý message song song, khiến thứ tự **handler completion** khác thứ tự gửi. Nếu cùng order ID cần tuần tự, cân nhắc JMS Message Groups, key partitioning hoặc thiết kế xử lý theo aggregate thay vì chỉ chỉnh min/max threads.

## 15. Các lỗi tư duy phổ biến

| Khẳng định sai | Điều đúng |
| --- | --- |
| “concurrency=6 thì luôn có sáu threads” | DMLC có thể có ít hơn, tùy syntax và tải; active khác configured |
| “concurrency=2-6 nghĩa là chính xác sáu handlers cùng chạy” | Đó là min/max consumers, handlers có thể đang idle |
| “TaskExecutor tạo một task cho từng JMS message” | Với DMLC, executor chạy polling invoker có receive loop |
| “SimpleAsyncTaskExecutor tái sử dụng thread trong pool” | Nó không là thread pool tái sử dụng |
| “Pool max=6 thì tự tăng lên sáu khi có thêm task” | Queue capacity lớn có thể giữ task đợi, không tăng thread ngay |
| “activeConsumerCount là số handler đang xử lý body” | Invoker có thể đang receive-wait |
| “getScheduledConsumerCount = JVM thread count” | Scheduled invokers có thể chưa chạy do executor |
| “getPoolSize là số consumer broker thấy” | Đó là metric pool, không phải JMS destination registration |
| “Tăng consumers sẽ giải quyết mọi backlog” | Có thể bottleneck ở DB, broker, network, lock, schema, retry |
| “Thread WAITING là deadlock” | Có thể đang chờ `receive()` bình thường |
| “@Async pool size tự đổi DMLC executor” | Cần wiring `setTaskExecutor` phù hợp |
| “SimpleMessageListenerContainer có cùng executor/ACK behavior” | Ngữ nghĩa dispatch/ACK có thể khác đáng kể |
| “Một Queue có sáu consumers giữ thứ tự hoàn thành tuyệt đối” | Concurrency làm thay đổi ordering quan sát |
| “maxConcurrentConsumers=6 là tối đa sáu trên cluster” | Là trần theo từng container/instance |
| “ThreadPoolTaskExecutor activeCount=4 có bốn messages đang xử lý” | Các task có thể đang poll broker, chưa gọi handler |

## 16. Troubleshooting nhanh

| Triệu chứng | Khả năng | Hành động |
| --- | --- | --- |
| Scheduled > Active lâu dài | Pool thiếu threads, task bị queue/rejected, đang recovery | Kiểm tra executor poolSize/activeCount/queueCapacity và DMLC logs |
| Active invokers > Handler inFlight | Invokers đang chờ message hoặc giữa các callbacks | Xem broker queue depth, receive timeout, thread dump |
| maxConcurrentConsumers cao nhưng không scale | Ít message, idleConsumerLimit, executor capacity hoặc broker | Load test đúng điều kiện, kiểm tra task scheduling |
| Thread pool không vượt corePoolSize | queueCapacity lớn và invokers sống lâu | Xem queue của executor; cân nhắc capacity nhỏ/0 |
| Có TaskRejectedException | Pool bão hòa hoặc đang shutdown | Nâng capacity có giới hạn, tách pool, chỉnh rescheduling |
| Queue depth tăng, CPU thấp | Chờ DB/API/lock, backlog, insufficient consumers | Đo handler latency, DB pool và consumer count |
| Nhiều threads nhưng TPS không tăng | Downstream bottleneck hoặc transaction overhead | Profile business path, DB, broker; không tiếp tục tăng threads |
| Sau broker restart active giảm | Reconnect/recovery hoặc resource unavailable | Theo dõi recovery logs, ACL, session/connection metrics |
| Pod startup tạo quá nhiều consumers | Nhiều listeners/instances mỗi cái có minimum | Nhân tổng theo containers và replicas |
| Handler xử lý trùng khi nâng concurrency | Retry/redelivery và idempotency thiếu | Giữ event ID, xử lý trùng, rollback/DLQ |
| Test chờ đúng bốn threads nhưng fail | Dynamic scaling không deterministic | Assert bounds và throughput/peak thay vì snapshot tuyệt đối |

## 17. Bài tập tự luyện

**Bài 1 — dự đoán số consumer.** Với `setConcurrency("4")`, cấu hình minimum/maximum là bao nhiêu? Hãy tra `getConcurrentConsumers` và `getMaxConcurrentConsumers`; đừng đoán “cố định bốn”.

**Bài 2 — queueCapacity.** Thử thay `setQueueCapacity(0)` thành `setQueueCapacity(100)` với core=2, max=4. Giữ nguyên 12 message và sleep 250ms. Quan sát poolSize, activeCount, scheduled/active invokers theo thời gian. Giải thích vì sao pool có thể không mở tới bốn threads.

**Bài 3 — số handler đang bận.** Bỏ `Thread.sleep(250)` hoặc tăng lên 1000ms. Quan sát `HANDLER_PEAK` và tổng thời gian xử lý. Có phải peak luôn bằng maxConcurrentConsumers không? Tại sao?

**Bài 4 — TaskExecutor mặc định.** Bỏ `factory.setTaskExecutor(executor)` để DMLC dùng SimpleAsyncTaskExecutor nội bộ. Đo thread names trong callback và số invokers qua registry. Vì sao không còn `getPoolSize` chung cho executor này?

**Bài 5 — multi-instance.** Với ba pods và mỗi pod `2-6` consumers, hãy ước lượng upper bound tổng consumers là bao nhiêu, sau đó giải thích vì sao broker metric thực tế có thể thấp hơn.

**Bài 6 — lỗi broker.** Dừng Artemis trong khi app chạy, theo dõi DMLC recovery, active/scheduled counts và ThreadPoolTaskExecutor. Chạy lại broker và xác minh message flow hồi phục. Không thử lỗi này trên production.

**Bài 7 — isolation.** Tạo thêm một `@Async` service dùng executor riêng, rồi so sánh với việc chia chung `ordersExecutor`. Điều gì xảy ra nếu JMS invokers giữ hết pool threads?

**Bài 8 — transaction.** Cho handler ném exception ở một message cụ thể, dùng session transacted, quan sát redelivery và DLQ policy. Vì sao chỉ tăng số luồng không chữa được một poison message?

## 18. Câu hỏi tự kiểm tra

**1.** DMLC mặc định dùng executor gì?

`SimpleAsyncTaskExecutor`, không phải thread pool tái sử dụng theo kiểu `ThreadPoolTaskExecutor`.

**2.** `setConcurrency("5")` tương đương minimum/maximum nào?

Minimum=1, maximum=5 trong DMLC, không phải cố định năm consumers.

**3.** `getScheduledConsumerCount()` và `getActiveConsumerCount()` khác nhau thế nào?

Scheduled đếm invokers container đã lên lịch; active đếm invokers thực sự đang hoạt động. Scheduled có thể cao hơn active nếu executor chưa cho task chạy.

**4.** Vì sao pool activeCount có thể lớn hơn số handler đang xử lý?

Các JMS invoker tasks có thể đang block ở `receive()`, vẫn chiếm thread nhưng chưa chạy business callback.

**5.** Đặt `maxPoolSize=6` có bảo đảm ThreadPoolTaskExecutor lên sáu threads không?

Không. Nếu queueCapacity lớn, task mới có thể xếp hàng sau core threads thay vì kích hoạt thêm threads tới maximum.

**6.** Một invoker có tạo task mới sau từng JMS message không?

Không mặc định. DMLC invoker thường thực hiện vòng receive và có thể xử lý nhiều message trong cùng task.

**7.** Có thể lấy container được tạo bởi `@JmsListener(id="ordersTasks")` bằng API nào?

`JmsListenerEndpointRegistry.getListenerContainer("ordersTasks")`, sau đó kiểm tra loại DMLC trước khi lấy runtime counters.

**8.** TaskExecutor của SimpleMessageListenerContainer và DefaultMessageListenerContainer có cùng ACK behavior không?

Không. SMLC có thể dispatch callback sang thread khác và làm thay đổi mốc ACK; cần đọc Javadoc riêng.

**9.** Concurrency “2-6” áp dụng cho toàn cluster có nhiều pods không?

Không. Nó áp dụng cho từng listener container trên từng instance.

**10.** Chỉ số nào phản ánh đúng số lần callback nghiệp vụ đang chạy tại thời điểm hiện tại?

Một metric instrumentation như `handlerInFlight` được tăng/giảm bên trong callback, không phải riêng `poolSize` hoặc configured max.

## 19. Tài liệu tham khảo chính thức

- Spring Framework 6.1 — `DefaultMessageListenerContainer` Javadoc: https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.1 — `DefaultJmsListenerContainerFactory` Javadoc: https://www.springframework.org/spring/docs/6.1.0-RC2/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — JMS receiving and listener containers: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework 6.1 — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 — `SchedulingTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/scheduling/SchedulingTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `SimpleMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0-M3/javadoc-api/org/springframework/jms/listener/SimpleMessageListenerContainer.html
- Spring Framework 6.2 Release Notes — thay đổi idle scheduling và virtual thread support: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.2-Release-Notes
- Spring Boot 3.3 — JMS/Artemis support: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html

**Ghi nhớ:** `TaskExecutor` chạy những **invoker tasks** của DMLC, còn `concurrency` định giới hạn số consumer. Để biết “bao nhiêu luồng thực tế”, hãy đối chiếu **configured min/max**, **scheduled/active invokers**, **pool threads**, **handlerInFlight** và số consumer broker ghi nhận. Một snapshot thread dump không thay thế phép đo workload và transaction behavior.
