# cacheLevel và tương tác với giao dịch ngoài

> **Ngữ cảnh:** Default container trong Spring Framework JMS. `DefaultMessageListenerContainer` (DMLC) có thể giữ lại `Connection`, `Session` và `MessageConsumer` nhằm tránh tạo mới tài nguyên sau mỗi lần nhận. Tuy nhiên, khi listener được bọc bởi một `PlatformTransactionManager` bên ngoài (đặc biệt `JtaTransactionManager` trong hạ tầng JTA/XA), việc reuse JMS handles có thể ảnh hưởng đến **resource enlistment** — đăng ký JMS resource vào đúng giao dịch. Do đó, `cacheLevel` là quyết định **vừa về hiệu năng, vừa về tính đúng của transaction**.

## 1. Mục tiêu và câu hỏi chính

Sau bài này, bạn có thể:

1. Phân biệt các mức `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER` và `CACHE_AUTO`.
2. Giải thích vì sao `CACHE_AUTO` thường tương đương `CACHE_CONSUMER` nếu DMLC **không có external transaction manager**, nhưng tương đương `CACHE_NONE` nếu **có manager được gắn**.
3. Cấu hình mức cache thông qua `DefaultJmsListenerContainerFactory` cho `@JmsListener`.
4. Kiểm tra **mức cache hiệu lực sau khi container khởi tạo**, không chỉ giá trị `CACHE_AUTO` trong source code.
5. Phân biệt **local JMS session transaction**, `JmsTransactionManager`, `DataSourceTransactionManager` và **JTA/XA transaction**.
6. Chỉ ra các tình huống tái sử dụng connection/session làm application server không enlist đúng JMS resource vào transaction.
7. Chạy demo Java 17/Spring Boot 3.3.5/Artemis có `sessionTransacted=true`, cache AUTO, listener và assertions.
8. Lập kế hoạch benchmark và failure-injection test khi muốn tăng cache trong môi trường XA; không đánh đổi correctness lấy throughput.

**Ghi nhớ trước:** DMLC `cacheLevel` không phải là broker message cache, không thay đổi JMS persistence, không tự tạo XA, không bảo đảm exactly-once business side effect và không thay thế ACK/transaction.

## 2. Tổng quan `DefaultMessageListenerContainer`

Một `@JmsListener` dùng `DefaultJmsListenerContainerFactory` thường được thực thi qua `DefaultMessageListenerContainer`. Container quản lý:

- JMS connection để nói chuyện với broker;
- JMS session và cơ chế acknowledge/transaction;
- JMS consumer gắn với queue, topic hoặc subscription;
- các invoker threads và concurrency;
- vòng `receive(timeout)` → gọi handler → commit/rollback;
- recovery khi broker tạm unavailable;
- tham gia external transaction khi có `PlatformTransactionManager` được cấu hình.

~~~text
Spring @JmsListener
       |
       v
DefaultJmsListenerContainerFactory
       |
       v
DefaultMessageListenerContainer
       |
       +-- Invoker #1 -------------------------------------+
       |    obtain Connection / Session / MessageConsumer |
       |    receive -> listener -> commit/rollback        |
       |    cacheLevel quyết định có reuse handles không  |
       |
       +-- Invoker #2 (nếu concurrency >= 2) -------------+
            có vòng nhận và tài nguyên thích hợp riêng
~~~

Trong một ứng dụng queue xử lý hàng ngàn message, tạo rồi đóng mọi connection/session/consumer ở mỗi lượt có overhead đáng kể. Trong một hệ thống XA, reuse một session từ giao dịch trước có thể phá cách coordinator yêu cầu **enlist** tài nguyên. Cả hai mặt phải được kiểm chứng.

### 2.1. “Cache” ở đây là cache cái gì?

| Tầng | Ví dụ | Cache cái gì? |
| --- | --- | --- |
| **DMLC internal cache** | `container.setCacheLevel(CACHE_SESSION)` | JMS handles do listener container tự quản lý |
| **Spring JMS connection cache** | `CachingConnectionFactory` | Resources được factory/wrapper tái sử dụng |
| **Provider/server connection pool** | Artemis pool, Jakarta EE JNDI managed factory | Physical connections hoặc handles cấp từ pool |
| **Broker storage** | Artemis journal, paging, persistence | Message data trên broker |

Bốn tầng này không tương đương. `CACHE_NONE` của DMLC nghĩa là **container không giữ lại handles qua các lượt**, không có nghĩa server chắc chắn mở/đóng một socket vật lý mới cho từng message nếu factory bên dưới còn pooling.

## 3. Bảng năm mức cache của DMLC

Javadoc Spring định nghĩa:

| Constant | `int` | Resource giữ lại trong DMLC | Ý nghĩa |
| --- | ---: | --- | --- |
| `CACHE_NONE` | 0 | Không cache connection/session/consumer | Mỗi lượt lấy JMS resources mới ở tầng container |
| `CACHE_CONNECTION` | 1 | JMS `Connection` | Reuse connection; session/consumer được lấy lại |
| `CACHE_SESSION` | 2 | JMS `Connection` và `Session` | Reuse cả session; consumer được lấy lại |
| `CACHE_CONSUMER` | 3 | `Connection`, `Session`, `MessageConsumer` | Reuse nhiều nhất trong các mức cache thực |
| `CACHE_AUTO` | 4 | **Chọn tự động** theo transaction manager | Không phải mức “cao hơn 3” |

Theo mô tả API, ở môi trường native JMS, mỗi listener invoker có thể sử dụng JMS `Session`/`MessageConsumer` riêng được giữ lại; handles được làm mới khi lỗi/recovery.

### 3.1. Quy tắc cốt lõi của `CACHE_AUTO`

~~~text
                  cacheLevel = CACHE_AUTO
                            |
                  DMLC initialize()
                            |
                 +----------+-----------+
                 |                      |
        Có external TM?         Không có external TM?
                 |                      |
                YES                    NO
                 |                      |
          CACHE_NONE (0)        CACHE_CONSUMER (3)
                 |                      |
        Lấy resource mới        Giữ Connection,
        trong transaction       Session, Consumer
~~~

**Vì sao?** Một số Jakarta EE application servers chỉ đăng ký JMS resource vào một XA transaction đang hoạt động nếu connection/session được lấy mới **trong giao dịch đó**. Spring ưu tiên tương thích bằng cách không cache nội bộ khi external transaction manager đã được cấu hình.

**Bẫy hay gặp:** một service có `@Transactional` hoặc một bean `DataSourceTransactionManager` trong context **không tự đủ** để đổi mức cache. Quy tắc trên xét **transaction manager được gắn trên DMLC**, thường qua `factory.setTransactionManager(...)`, không chỉ sự tồn tại của DB transaction trong ứng dụng.

### 3.2. Cấu hình mức cache bằng API

Trên container:

~~~java
// Snippet: container là DefaultMessageListenerContainer.
container.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_SESSION);

// Hoặc tên constant:
container.setCacheLevelName("CACHE_SESSION");
~~~

Trên factory:

~~~java
// Snippet: factory là DefaultJmsListenerContainerFactory.
factory.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_AUTO);
factory.setConcurrency("2-4");
~~~

Import constant từ `org.springframework.jms.listener.DefaultMessageListenerContainer`. `DefaultJmsListenerContainerFactory` có `setCacheLevel(Integer)` và `setCacheLevelName(String)`; chọn **một** cách cấu hình trong ứng dụng thực, không đặt hai mức khác nhau lần lượt như thể chúng cộng dồn.

### 3.3. Mức cấu hình và mức hiệu lực khác nhau

Khi factory được tạo:

~~~java
factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
~~~

giá trị intent là AUTO = 4. Nhưng trong `DefaultMessageListenerContainer.initialize()`, Spring thay `CACHE_AUTO` bằng mức thực theo transaction strategy. Vì vậy `getCacheLevel()` **trên container sau initialize** có thể là 0 hoặc 3.

Đừng chỉ log constant `CACHE_AUTO` rồi tuyên bố đã đo hiệu lực. Ở phần ví dụ, ta lấy DMLC đã đăng ký thông qua `JmsListenerEndpointRegistry` để assert mức thực.

## 4. Local JMS transaction và cache

Đặt:

~~~java
factory.setSessionTransacted(true);
factory.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_AUTO);
~~~

và **không** đặt external transaction manager trên container thì `CACHE_AUTO` thường chọn `CACHE_CONSUMER`.

~~~text
DMLC invoker với cached Session/Consumer
       |
       +-- receive message #1
       +-- handle message #1
       +-- JMS Session.commit()
       |
       +-- receive message #2 trên cùng cached handle
       +-- listener ném exception
       +-- JMS Session.rollback()
       |         |
       |         +--> message #2 có thể được redeliver
       |
       +-- receive message tiếp theo ...
~~~

Reuse JMS session **không** có nghĩa giao dịch #1 và #2 là cùng một transaction. Với transacted session, mỗi lần `commit()`/`rollback()` kết thúc transaction hiện hành và session tiếp tục transaction mới theo JMS semantics.

### 4.1. Lợi ích của `CACHE_CONSUMER` khi không có TM ngoài

- Ít overhead tạo/đóng sessions và consumers.
- Ít resource churn ở phía broker.
- Phù hợp listener tồn tại lâu, queue ổn định và có concurrency được kiểm soát.
- Spring vẫn có recovery để làm mới resources hỏng sau broker failure.
- Với native JMS listener, là lựa chọn hiệu quả trong nhiều trường hợp.

**Không suy ra** “không bao giờ tạo mới handles” vì recovery, scaling, reconfiguration hoặc shutdown đều có thể làm mới consumer. Số handles còn phụ thuộc concurrency, mỗi listener endpoint và provider.

### 4.2. Local JMS commit không tự commit DB

Một kịch bản rủi ro:

~~~text
JMS receive -> listener cập nhật database
                         |
                         +-- JDBC COMMIT thành công
                         |
                         X  process crash trước JMS COMMIT
                         |
                   Broker redelivery
                         |
                   DB có thể bị cập nhật lần hai
~~~

Dùng `CACHE_CONSUMER` hay `CACHE_NONE` **không giải quyết** việc hai commit tách biệt. Để đạt business correctness, cần event ID ổn định và idempotent consumer/dedupe trong cùng DB transaction, hoặc kiến trúc XA/outbox phù hợp.

## 5. External transaction manager là gì?

Trên DMLC, `setTransactionManager(PlatformTransactionManager)` cho phép một transaction manager bên ngoài quản lý vòng nhận message và gọi listener. Nhưng **không phải mọi PlatformTransactionManager đều là XA**.

| Chiến lược | Phạm vi transaction | Có tự gộp JMS + JDBC thành atomic transaction? |
| --- | --- | --- |
| `sessionTransacted=true`, không external manager | JMS session local | Không |
| `JmsTransactionManager` | Local JMS resource qua Spring API | Không tự gộp DB |
| `DataSourceTransactionManager` | Một JDBC DataSource | Không tự enlist JMS |
| `JtaTransactionManager` + XA-aware JMS/JDBC + coordinator thật | Global JTA transaction với các enlisted XA resources | Có thể, nếu hạ tầng/configuration đúng |
| `@Transactional` trên DB method nhưng DMLC dùng local JMS | DB transaction ở method; local JMS riêng | Không mặc nhiên |

**Tại sao điều này ảnh hưởng cache?** Spring `CACHE_AUTO` chỉ kiểm tra DMLC có external `PlatformTransactionManager` hay không. Nếu gắn `JmsTransactionManager` hay một manager không phải JTA, nó vẫn có thể làm AUTO chọn `CACHE_NONE`. Điều đó không biến transaction thành XA.

### 5.1. `JmsTransactionManager`

`org.springframework.jms.connection.JmsTransactionManager` quản lý transaction của một JMS `ConnectionFactory`. Nó hữu ích cho những thao tác JMS local cần Spring transaction API, nhưng không bảo đảm một `DataSource` JDBC tự tham gia cùng transaction ấy.

~~~java
// Snippet Spring @Configuration; không phải chương trình độc lập.
@Bean
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Cần imports `org.springframework.jms.connection.JmsTransactionManager`, `org.springframework.context.annotation.Bean`, `jakarta.jms.ConnectionFactory`.

### 5.2. `DataSourceTransactionManager`

`org.springframework.jdbc.datasource.DataSourceTransactionManager` quản lý JDBC transaction. Đặt nó thành `transactionManager` của listener không tự đăng ký JMS resource vào global transaction. Hãy kiểm tra callback có ACK/commit JMS theo policy nào thay vì tin tên property `transactionManager`.

### 5.3. `JtaTransactionManager`

`org.springframework.transaction.jta.JtaTransactionManager` là adapter đến một JTA transaction coordinator đã được cấu hình. Để JMS receive và JDBC update thuộc **cùng một XA transaction** cần:
1. JTA coordinator với recovery logs.
2. XA-aware JMS connection factory/resource adapter đã đăng ký với coordinator.
3. XA-capable datasource và database support.
4. Listener container được gắn đúng `JtaTransactionManager`.
5. Transaction timeout, rollback, commit, crash recovery được test thật.

Chỉ khai báo `new JtaTransactionManager()` trong một bare Spring Boot application **không** tự tạo đầy đủ một XA coordinator và không biến client/DB thường thành XA.

## 6. Tại sao Spring tắt caching khi JTA tham gia?

Một số app server quản lý enlistment theo thời điểm lấy handle. Ví dụ:

~~~text
Global transaction TX-101 BEGIN
       |
       +-- obtain JMS Connection and Session (fresh)
       +-- resource adapter enlists JMS into TX-101
       +-- receive message
       +-- update JDBC under same TX-101
       +-- JTA COMMIT / ROLLBACK
       |
Global transaction TX-102 BEGIN
       |
       +-- obtain JMS Connection and Session (fresh)
       +-- JMS resource enlisted into TX-102
       +-- receive and process
       +-- JTA COMMIT / ROLLBACK
~~~

Nếu giữ một session từ TX-101 và reuse cho TX-102, một server/provider có thể **không enlist session đúng** vào TX-102. Hậu quả tùy hạ tầng:
- transaction log báo resource chưa enlist hoặc transaction context không đúng;
- JMS receive bị ACK ngoài giao dịch;
- DB rollback nhưng message không được redeliver;
- resource nằm trong transaction cũ;
- lỗi chỉ xuất hiện ở lần nhận thứ hai, hoặc sau failover.

Vì vậy, mặc định external TM → `CACHE_NONE` là lựa chọn **tương thích rộng**. Spring Javadoc cũng nêu có môi trường cho phép reuse ít nhất `Connection` hoặc cả `Session` dù có external TM. Khả năng đó **không mặc định**: cần chứng cứ từ provider/server và integration tests.

### 6.1. Ép cache khi có JTA có được không?

Có thể:

~~~java
// Snippet: factory đã có setTransactionManager(jtaManager).
factory.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_CONNECTION);
~~~

Điều này yêu cầu DMLC reuse connection, khác với mức AUTO/NONE. Muốn tiến tới `CACHE_SESSION`, phải xác nhận XA enlistment vẫn đúng khi session được reuse. `CACHE_CONSUMER` giữ cả consumer nên cần kiểm chứng kỹ hơn.

| Mức trong JTA | Hiệu năng kỳ vọng | Rủi ro cần đánh giá |
| --- | --- | --- |
| `CACHE_NONE` | Churn JMS handles nhiều hơn | Baseline an toàn về compatibility |
| `CACHE_CONNECTION` | Bớt tạo connection | Connection reuse có giữ được enlistment đúng? |
| `CACHE_SESSION` | Bớt tạo connection/session | Session reuse có làm XA coordinator nhầm transaction? |
| `CACHE_CONSUMER` | Bớt cả consumer creation | Consumer/session reuse, subscription, recovery và enlistment |

**Không kết luận mức 3 luôn nhanh nhất**: còn tùy connection factory pool, broker, consumer prefetch, receive timeout, scaling và task executor. Đo throughput phải đi cùng đo correctness.

### 6.2. Kiểm thử bắt buộc khi override trong XA

- Gửi một message và xác nhận cả JMS receive lẫn JDBC update commit.
- Cố ý ném exception trước khi listener hoàn thành: cả DB và JMS phải rollback nếu XA được cam kết.
- Chạy **nhiều** messages, nhiều transactions nối tiếp: session reused giữa các transaction mới là điểm nguy hiểm.
- Failover/restart broker hoặc ngắt DB ở các thời điểm gần commit trên **môi trường test**.
- Kiểm tra transaction coordinator logs, XA resource enlistment và trạng thái in-doubt.
- Benchmark latency/throughput/connection churn với cùng tải khi `CACHE_NONE` và mức mới.
- Có rollback plan về AUTO/NONE nếu quan sát behavior không đúng.

Chỉ thấy listener “nhận được message” **không chứng minh** XA rollback đúng. Điều cần chứng minh là **tính nguyên tử của state JMS+DB** dưới lỗi.

## 7. Ví dụ runnable: `CACHE_AUTO` với local JMS transaction

Ví dụ dùng Java 17, Spring Boot 3.3.5 và Apache ActiveMQ Artemis. Chương trình:
- tạo listener factory mặc định;
- bật `sessionTransacted=true`;
- cấu hình `CACHE_AUTO`;
- **không** đặt external transaction manager;
- lấy container qua registry **sau khởi tạo**;
- xác nhận mức cache thực là `CACHE_CONSUMER`;
- gửi `TextMessage` và nhận tại `@JmsListener`.

### 7.1. Môi trường

Cần JDK 17+, Gradle, Artemis broker tại `tcp://localhost:61616`, queue anycast test `demo.cache.local` và tài khoản có quyền send/consume. Để có broker demo local cách ly, có thể chạy:

~~~bash
docker run --detach --rm --name artemis-cache-test -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Đợi broker ready bằng `docker logs artemis-cache-test`. Image demo thường tạo tài khoản `artemis/artemis`; chỉ dùng credentials mặc định ở máy cá nhân cách ly, **không sử dụng cho production**. Khi xong: `docker stop artemis-cache-test`. Không chạy thêm container nếu cổng 61616 đã có broker khác.

Queue test nên được tạo trước hoặc broker demo cho phép auto-create. Không dùng queue nghiệp vụ thật vì listener có thể nhận/ACK message.

### 7.2. Cấu trúc project

~~~text
jms-cache-level-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── CacheLevelApplication.java
    │   └── CacheLevelListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-cache-level-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "artemis"
    password: "artemis"
~~~

Dữ liệu đăng nhập chỉ nhằm minh họa broker local. Khi dùng hạ tầng khác, ghi đè bằng `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` và `SPRING_ARTEMIS_BROKER_URL` hoặc secret manager. Không commit credentials thật.

### 7.3. Listener nhận đúng message

`src/main/java/demo/CacheLevelListener.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class CacheLevelListener {

    private final CountDownLatch received = new CountDownLatch(1);
    private volatile String expectedBody;

    public void expect(String value) {
        expectedBody = value;
    }

    @JmsListener(
            id = "cache-level-demo",
            destination = "demo.cache.local")
    public void onMessage(String body) {
        String expected = expectedBody;
        if (expected != null && expected.equals(body)) {
            received.countDown();
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

Listener có `CountDownLatch` và body mang run ID riêng để không báo thành công do một message cũ. Lưu ý một message cũ trên queue test vẫn có thể bị listener nhận và ACK mà không kích hoạt latch; cần dùng dedicated queue trống. Demo không phù hợp với nhiều requests chạy đồng thời trên cùng listener instance.

### 7.4. Application cấu hình và đọc mức hiệu lực

`src/main/java/demo/CacheLevelApplication.java`:

~~~java
package demo;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
@EnableJms
public class CacheLevelApplication {

    private static final String QUEUE = "demo.cache.local";

    public static void main(String[] args) {
        SpringApplication.run(CacheLevelApplication.class, args);
    }

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory defaultFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        // Native/local JMS session transaction.
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        // Spring sẽ resolve AUTO thành CONSUMER khi không có TM ngoài.
        factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
        return factory;
    }

    @Bean
    ApplicationRunner verify(
            JmsListenerEndpointRegistry registry,
            JmsTemplate jmsTemplate,
            CacheLevelListener listener) {

        return args -> {
            MessageListenerContainer current =
                    registry.getListenerContainer("cache-level-demo");

            if (!(current instanceof DefaultMessageListenerContainer dmlc)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            // DMLC đã initialize: đọc cache level đang hoạt động.
            int effective = dmlc.getCacheLevel();
            if (effective != DefaultMessageListenerContainer.CACHE_CONSUMER) {
                throw new IllegalStateException(
                        "Unexpected cache level: " + effective);
            }

            String id = UUID.randomUUID().toString();
            String body = "cache-probe:" + id;
            listener.expect(body);

            jmsTemplate.convertAndSend(QUEUE, body);

            if (!listener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive probe within 10s");
            }

            System.out.println("EFFECTIVE_CACHE_LEVEL=CACHE_CONSUMER");
            System.out.println("LOCAL_JMS_TRANSACTION=true");
            System.out.println("LISTENER_RECEIVED=true");
        };
    }
}
~~~

**Điểm kiểm tra quan trọng:**

1. `@Bean("jmsListenerContainerFactory")` đặt tên chính xác cho factory mặc định của `@JmsListener` không khai báo `containerFactory`.
2. `@EnableJms` kích hoạt listener annotations.
3. `DefaultJmsListenerContainerFactory` tạo `DefaultMessageListenerContainer` cho endpoint.
4. `setSessionTransacted(true)` bật **local JMS transaction**, không phải XA.
5. Vì không có `setTransactionManager(...)` trên factory, `CACHE_AUTO` được resolve thành `CACHE_CONSUMER`. Code đọc **container thực tế** qua registry thay vì đoán từ factory.
6. `JmsTemplate.convertAndSend` chuyển String sang `TextMessage` bằng converter mặc định và gửi đến queue test.
7. Listener dùng run ID mới; latch đợi tối đa 10 giây.
8. Việc latch hoàn thành chỉ chứng minh method đã xử lý đúng body; **JMS commit của container có thể diễn ra sau khi method return**, nên không gọi output này là bằng chứng commit JMS cuối cùng.
9. Nếu broker/queue/quyền sai, demo không giả PASS: có thể timeout/exception.
10. Listener container tiếp tục chạy sau output; dừng ứng dụng bằng `Ctrl+C` khi hoàn tất.

### 7.5. Chạy và stdout

Trong thư mục project:

~~~bash
gradle bootRun
~~~

Khi broker sẵn sàng, permissions và listener đúng, những dòng ứng dụng in là:

~~~text
EFFECTIVE_CACHE_LEVEL=CACHE_CONSUMER
LOCAL_JMS_TRANSACTION=true
LISTENER_RECEIVED=true
~~~

Spring Boot/Artemis có thể ghi thêm logs; output trên là **kỳ vọng**, không phải số liệu đo được trong mọi môi trường. Nếu `getCacheLevel()` không đúng dự kiến, đầu tiên kiểm tra có transaction manager được custom configurer gắn vào factory hay không.

**Cấu hình bổ sung:** Spring Boot auto-configured JMS listener factory thường sử dụng underlying/native `ConnectionFactory` cho listener để tự quản lý recovery. Demo dùng connection factory inject trực tiếp để minh họa API. Khi triển khai production, cân nhắc Boot configurer ở mục 8 và inspect wrapper.

## 8. Sử dụng Boot configurer mà không làm mất mặc định

Nếu đang dùng Spring Boot 3.x, thay vì tự dựng factory thuần, có thể áp dụng `DefaultJmsListenerContainerFactoryConfigurer` để kế thừa thiết lập từ Boot rồi đặt cache level:

~~~java
// Snippet Spring Boot 3.x trong @Configuration; không chạy độc lập.
@Bean("jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory configuredFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {

    var factory = new DefaultJmsListenerContainerFactory();
    configurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
    return factory;
}
~~~

Imports:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
~~~

Tại Spring Boot 3, configurer có thể gắn một `JtaTransactionManager` được auto-detected, hoặc bật `sessionTransacted` mặc định khi không có JTA. Vì vậy, **cùng cấu hình CACHE_AUTO có thể cho effective level khác** giữa local Boot và môi trường JTA.

Đừng áp dụng snippet của Spring Boot 3 nguyên xi cho Boot 4 mà không xem lại package auto-config/imports, vì Boot 4 đã tổ chức lại modules. Khi có custom listener factory, kiểm tra converter, destination resolver, transaction manager và caching wrapper có được chuyển sang đúng factory hay không.

### 8.1. Phân biệt cache của DMLC với `CachingConnectionFactory`

Một cấu hình có thể có hai tầng:

~~~text
DefaultMessageListenerContainer
   |
   +-- internal cacheLevel = CACHE_CONSUMER
   |             |
   v             v
Spring CachingConnectionFactory (nếu được bọc)
                 |
                 v
        Native JMS ConnectionFactory
                 |
                 v
              Broker
~~~

`CachingConnectionFactory.sessionCacheSize` là setting ở **factory wrapper**, không phải `DefaultMessageListenerContainer.cacheLevel`. Nếu cả hai tầng reuse, metric connection count và lifecycle khó suy luận từ một setter.

Spring Boot thường unwrap cached factory trước khi giao cho listener factory auto-configured. Nhưng tùy provider/pool/JNDI managed connection factory, **không phải mọi wrapper có cùng semantics**. Với XA, ưu tiên hướng dẫn của transaction coordinator/resource adapter hơn một quy tắc tối ưu chung.

## 9. Cấu hình factory cho JTA/XA (snippet, không chạy độc lập)

Đây là ví dụ **chỉ dành cho môi trường có JTA coordinator thực và một JMS connection factory XA-aware đã được đăng ký**:

~~~java
// Snippet trong @Configuration có xaJmsConnectionFactory và JTA thực.
@Bean("xaListenerContainerFactory")
DefaultJmsListenerContainerFactory xaListenerFactory(
        @Qualifier("xaJmsConnectionFactory")
                ConnectionFactory xaJmsConnectionFactory,
        JtaTransactionManager jtaTransactionManager) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(xaJmsConnectionFactory);
    factory.setTransactionManager(jtaTransactionManager);
    factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
    factory.setConcurrency("1-3");
    return factory;
}
~~~

Imports:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.transaction.jta.JtaTransactionManager;
~~~

Một listener chọn factory trên:

~~~java
// Snippet trong @Component có hỗ trợ JMS annotations.
@JmsListener(
    destination = "orders.xa",
    containerFactory = "xaListenerContainerFactory")
public void handle(String body) {
    // Xử lý DB qua DataSource đã được enlist vào cùng JTA.
}
~~~

Với `CACHE_AUTO` và external manager được đặt trên factory, DMLC sẽ chọn **`CACHE_NONE`**. Nhưng câu “global XA đảm bảo JMS+DB commit cùng nhau” chỉ đúng **nếu** JMS resource, JDBC resource, coordinator và recovery được cấu hình chuẩn. Chỉ nhìn annotation `@Transactional` hay kiểu class `JtaTransactionManager` chưa đủ.

### 9.1. Không dùng cache để sửa thiếu transaction

Nếu bạn có:

~~~text
DB COMMIT thành công
          |
          X JVM crash trước JMS COMMIT
          |
   message có thể redeliver
          |
     business side effect trùng
~~~

thì chuyển `CACHE_CONSUMER` sang `CACHE_NONE` không làm hai commit thành một. Đó là **vấn đề dual-write/commit boundary**, thường xử lý bằng idempotency key trong DB, hoặc XA coordination nếu yêu cầu/hạ tầng cho phép.

### 9.2. `@Transactional` bên trong listener

Một method được đánh dấu `@Transactional` dùng transaction manager do Spring chọn cho lời gọi đó; với nhiều managers, phải bảo đảm selection chính xác. Local JMS session transaction của container thường bắt đầu trước rồi kết thúc sau listener. Một transaction JDBC của method có thể commit trước JMS commit, và **không cùng một global atomic transaction** chỉ vì đều dùng Spring.

Do vậy, kiểm thử nên có tình huống DB đã ghi nhưng JMS rollback, để bảo đảm consumer dùng idempotent processing.

## 10. Cache level, concurrency và subscription

### 10.1. Queue nhiều consumers

Nếu factory dùng `setConcurrency("3-6")`, DMLC có thể tạo 3 consumer invokers tối thiểu và mở rộng tới 6 khi tải tăng. Với `CACHE_CONSUMER`, mỗi invoker thường giữ session/consumer tương ứng. Khi tăng concurrency, cần đo:

- số JMS consumers ở broker;
- số sessions/connections trong pool/provider;
- độ trễ xử lý và queue age;
- DB pool capacity và số side effects concurrent;
- message ordering có còn đúng yêu cầu không.

Không có bảo đảm strict ordering tổng thể khi nhiều consumers cùng nhận trên một queue. Tối ưu concurrency và cacheLevel là hai trục khác nhau.

### 10.2. Non-durable topic subscriptions

Spring reference cảnh báo: khi **không caching**, container có thể tạo lại connection/session qua mỗi lượt nhận. Với **non-durable topic subscription** dưới tải cao, subscription có thể biến mất giữa các lần đó và làm mất message. Do đó:
- Không áp dụng `CACHE_NONE` cho non-durable topic quan trọng mà không test điều kiện này.
- Nếu cần nhận khi subscriber offline, cấu hình durable subscription đúng với `clientId`/subscription name và JMS provider.
- Kiểm tra ngữ nghĩa shared/non-shared subscriptions trước khi nâng concurrency.
- Không coi persistent delivery mode của producer là thay thế cho durable subscription.

### 10.3. Recovery

DMLC có cơ chế tự phục hồi sau lỗi broker và có thể tạo lại handles dù cacheLevel cao. Spring Framework mặc định thường retry theo `BackOff`/recovery interval khoảng 5 giây. Khi thấy consumer count biến động, kiểm tra recovery logs và broker restarts trước khi kết luận cache policy không hoạt động.

## 11. Kiểm thử hiệu năng và correctness

Đổi cache level cần ít nhất hai nhóm test.

### 11.1. Positive cases

| Test | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| P01 | `sessionTransacted=true`, không external TM, AUTO | DMLC effective `CACHE_CONSUMER` |
| P02 | external TM được set, AUTO | DMLC effective `CACHE_NONE` |
| P03 | Local JMS, listener thành công | JMS transaction commit sau handler theo container |
| P04 | Local JMS, listener ném exception | JMS rollback/redelivery theo broker policy |
| P05 | JTA/XA đầy đủ, listener + JDBC update | JMS và DB enlist/commit cùng global transaction |
| P06 | JTA/XA, JDBC update lỗi | JMS receive và DB update cùng rollback |
| P07 | Provider hỗ trợ reuse, chuyển NONE → CONNECTION | P05/P06 vẫn đúng; đo overhead giảm thật |
| P08 | Broker restart trong test | DMLC recovery, xử lý message pending đúng |

### 11.2. Negative/failure cases

| Test | Tình huống | Điều cần xác minh |
| --- | --- | --- |
| N01 | Local JMS DB commit xong, kill trước JMS commit | Redelivery được xử lý idempotently |
| N02 | JMS XA resource không được enlist | Transaction logs và dữ liệu chứng minh lỗi |
| N03 | Cached XA session mang trạng thái giao dịch cũ | Test nhiều transactions liên tiếp, không chỉ một message |
| N04 | Broker mất kết nối rồi phục hồi | Handles được làm mới, listener tiếp tục |
| N05 | Cache NONE và non-durable topic | Kiểm tra message gaps khi subscription churn |
| N06 | Concurrency lớn hơn DB pool | Backlog, timeout, error rate |
| N07 | AUTO_ACKNOWLEDGE được dùng thay transacted | Failure handler có thể không redeliver |
| N08 | DMLC và factory đều cache | Đo đúng từng tầng resource reuse |
| N09 | Đặt nhầm DataSourceTransactionManager làm DMLC TM | JMS không được tự động tham gia XA |
| N10 | Thay cache trong production mà không rollback plan | Không thể đối chiếu và phục hồi cấu hình an toàn |

Chỉ thực hiện kill broker/DB/failure injection trên **môi trường thử nghiệm**, không xóa journal/queue production. Không kết luận XA “đã đúng” chỉ dựa vào stdout từ listener.

## 12. Theo dõi thực tế để phân biệt các vấn đề

Ghi lại cho mỗi test:
- Spring Framework/Boot/JMS provider version.
- `cacheLevel` cấu hình trên factory và `getCacheLevel()` sau initialization trên DMLC.
- Manager class thực sự gắn vào DMLC; có JTA coordinator/XA resources hay không.
- Loại connection factory, wrapper, vendor pool/JNDI configuration.
- Queue/topic, subscription mode, concurrency, receive timeout.
- Broker connection/session/consumer counts, reconnect/recovery logs.
- Transaction IDs, resource enlistment, rollback/commit evidence.
- Event ID, JMS redelivery count, DB dedupe/side-effect outcomes.
- Throughput, p95/p99 latency, CPU/memory và connection churn.

Nếu `getCacheLevel()` là 0 nhưng physical sockets vẫn được tái sử dụng, đó có thể là provider pool; không có mâu thuẫn với `CACHE_NONE` nội bộ. Nếu getCacheLevel là 3 nhưng broker báo connection mới sau restart, đó có thể là recovery, không phải cache “không có tác dụng”.

### Chẩn đoán theo triệu chứng

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| AUTO thành NONE bất ngờ | Có external manager được configurer gắn vào factory? |
| AUTO vẫn CONSUMER dù service có JDBC `@Transactional` | Manager của DB có thực sự được set trên DMLC không? |
| JMS không rollback cùng DB trong XA | Resource adapter/JNDI XA factory, transaction enlistment, manager selection |
| Dùng CACHE_SESSION bị lỗi từ message thứ hai | Session được reuse qua nhiều JTA transactions có được provider hỗ trợ không? |
| Consumer count tăng sau tăng concurrency | Điều chỉnh scaling và provider limits; không phải cacheLevel tự tạo message |
| Message bị xử lý trùng | Redelivery/producer retry/idempotency, không chỉ cache |
| Lỗi connection sau broker restart | DMLC recovery, wrapper stale resources, broker/TLS credentials |
| Throughput thấp khi CACHE_NONE | Đo session creation và pool; chỉ override nếu correctness tests PASS |
| Mất message ở non-durable topic | Subscription recreation/no cache, topic durability semantics |
| Ứng dụng Boot custom factory không giống mặc định | Dùng Boot configurer và kiểm tra cache/transaction policy |

## 13. Checklist ra quyết định

- [ ] Đã nhận diện đúng `DefaultMessageListenerContainer`, không nhầm `SimpleMessageListenerContainer`.
- [ ] Nắm cả 5 cache constants và giá trị.
- [ ] Hiểu `CACHE_AUTO` chọn **CACHE_CONSUMER không external TM** và **CACHE_NONE có external TM**.
- [ ] Đọc hiệu lực từ container sau khi Spring khởi tạo.
- [ ] Biết listener dùng local JMS, JmsTransactionManager, DataSourceTransactionManager hay JTA/XA.
- [ ] Với XA, JMS ConnectionFactory/DB DataSource/coordinator hỗ trợ và enlist đúng.
- [ ] Không dùng cacheLevel để giải quyết vấn đề dual-write hoặc exactly-once business side effect.
- [ ] Có idempotent consumer nếu JDBC transaction và JMS transaction tách biệt.
- [ ] Khi override cache trong XA, đã chạy multi-transaction rollback/recovery tests.
- [ ] Đã phân biệt DMLC caching với CachingConnectionFactory và vendor connection pooling.
- [ ] Đã kiểm tra queue/topic/durable subscription/concurrency.
- [ ] Khi dùng Spring Boot custom factory, giữ configurer/native factory behavior phù hợp.
- [ ] Có metrics và logs cho resource handles, transaction outcome và redelivery.
- [ ] Có kế hoạch revert về AUTO/NONE nếu optimization làm sai atomicity.

### Câu hỏi tự kiểm tra

1. `CACHE_AUTO` mang giá trị số mấy, và nó có cache nhiều nhất không?
2. `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER` giữ lại những JMS handles nào?
3. Vì sao `CACHE_AUTO` chọn `CACHE_NONE` khi DMLC có external transaction manager?
4. Nếu chỉ bật `sessionTransacted=true` và không set external manager, expected effective cache là gì?
5. Vì sao một app server có thể không enlist đúng cached JMS `Session` vào XA transaction mới?
6. `JmsTransactionManager` có đồng nghĩa `JtaTransactionManager` không?
7. `@Transactional` trên method JDBC có khiến DMLC tự chọn CACHE_NONE không?
8. Vì sao tăng cacheLevel trong JTA chỉ an toàn sau khi test rollback cả JMS và DB?
9. DMLC `cacheLevel` và `CachingConnectionFactory.sessionCacheSize` có giống nhau không?
10. Vì sao non-durable topic subscription có thể mất message nếu liên tục recreate consumers?
11. Vì sao phải đọc `getCacheLevel()` sau initialize thay vì chỉ in cấu hình?
12. Nếu DB commit xong nhưng JMS commit chưa xong rồi JVM crash, chuyện gì có thể xảy ra?
13. Nếu latency tốt hơn nhưng XA failure test không PASS, nên chọn kết quả nào cho production?

**Kết luận:** `CACHE_AUTO` là điểm khởi đầu hợp lý: **local JMS/no external manager → CACHE_CONSUMER**, **có external manager → CACHE_NONE**. Tắt cache trong giao dịch ngoài nhằm bảo vệ tính tương thích với resource enlistment, không phải một mẹo giảm hiệu năng vô cớ. Chỉ override khi hạ tầng cho phép và đã chứng minh **transaction correctness trước throughput**.

## Tài liệu tham khảo

1. Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc, constants và `setCacheLevel`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
2. Spring Framework — Message Listener Containers và transaction management: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
3. Spring Framework — Receiving a Message và JTA: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
4. Spring Framework — Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
5. Spring Framework 6.2 — `DefaultJmsListenerContainerFactory`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
6. Spring Boot 3.x — JMS/Artemis and transactional listener defaults: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
7. Spring Boot — Messaging how-to, listener factory and native connection factory: https://docs.spring.io/spring-boot/how-to/messaging.html
8. Jakarta Messaging 3.1 Specification — Sessions, transactions and acknowledgement: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
