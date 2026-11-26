# RabbitListenerTestHarness để quan sát listener được gọi

## 1. Bài toán: publish thành công không chứng minh listener đã chạy

Trong hệ thống **Spring AMQP + RabbitMQ**, producer dùng `RabbitTemplate` publish tới **exchange**, broker áp dụng **binding** để định tuyến message đến **queue**, rồi một `@RabbitListener` xử lý bất đồng bộ. Một test thường bắt đầu như sau:

~~~java
rabbitTemplate.convertAndSend("orders.events.x", "order.created", "ORD-101");
// Làm sao biết @RabbitListener đã được gọi?
~~~

Ngay sau `convertAndSend()`, message có thể còn trên đường truyền, đang ở queue hoặc chưa được một consumer lấy ra. Vì vậy, gọi `Mockito.verify(listener).handle("ORD-101")` ngay tại đây có thể thất bại **do race condition**, dù ứng dụng vẫn đúng. Ngược lại, nếu test chỉ xác nhận `convertAndSend()` không ném exception thì **chưa có bằng chứng listener đã được gọi**.

Spring AMQP cung cấp module **`spring-rabbit-test`**. Trong đó, **`@RabbitListenerTest`** và **`RabbitListenerTestHarness`** giúp kiểm tra listener thực sự nhận được gì, được gọi bao nhiêu lần, trả về giá trị nào hoặc ném exception gì.

**Mục tiêu bài học:**

1. Bật đúng `@RabbitListenerTest` và lấy bean `RabbitListenerTestHarness`.
2. Phân biệt **spy** (Mockito) và **capture advice** (ghi dữ liệu lời gọi).
3. Chờ lời gọi đến từ **listener container thread** mà không dùng `Thread.sleep()` tùy tiện.
4. Viết test one-way và request–reply với `RabbitTemplate`, `@RabbitListener` và RabbitMQ thật.
5. Hiểu giới hạn của harness trong thử nghiệm retry, ACK, dead-letter, idempotency, transaction và topology.

> **Điểm chính:** `RabbitListenerTestHarness` quan sát **phương thức listener trong Spring context**. Nó không phải một công cụ đọc message trực tiếp trên RabbitMQ, không thay thế publisher confirms/consumer ACK và không tự chứng minh toàn bộ tác dụng phụ nghiệp vụ đã hoàn tất.

## 2. Harness hoạt động như thế nào?

`@RabbitListenerTest` khai báo trên một lớp `@Configuration` của môi trường kiểm thử. Nó cấu hình một bean post-processor đặc biệt, **`RabbitListenerTestHarness`**, thay thế `RabbitListenerAnnotationBeanPostProcessor` thông thường để tăng khả năng quan sát các method `@RabbitListener`.

Hai cơ chế:

| Cơ chế | Bật bằng | Quan sát được | API chính |
| --- | --- | --- | --- |
| **Mockito spy** | `@RabbitListenerTest(spy = true)` | Listener được gọi với tham số nào, bao nhiêu lần; có thể stubbing bằng Mockito. | `getSpy(id)`, `verify(...)`, `getLatchAnswerFor(...)` |
| **Capture advice** | `@RabbitListenerTest(capture = true)` | Arguments, return value, exception của lời gọi thật; có queue để chờ bất đồng bộ. | `getNextInvocationDataFor(id, wait, unit)` |

Có thể bật **cả hai**:

~~~java
@RabbitListenerTest(spy = true, capture = true)
~~~

Giá trị mặc định của annotation:

- `spy = true`.
- `capture = false`.

Vì vậy, **chỉ viết `@RabbitListenerTest` chưa cho phép gọi `getNextInvocationDataFor()` để nhận dữ liệu capture**. Muốn có `InvocationData`, đặt `capture = true`.

### 2.1. Luồng quan sát

~~~text
JUnit test thread
   |
   | RabbitTemplate.convertAndSend(...)
   v
exchange -- binding --> queue (RabbitMQ)
                             |
                             v
                   Listener container thread
                             |
                             v
                  @RabbitListener(id="ordersListener")
                             |
                    +--------+--------+
                    |                 |
                 Mockito spy       Capture advice
                    |                 |
          verify(...) sau wait     arguments/result/throwable
                    |                 |
                    +--------+--------+
                             |
                             v
                   RabbitListenerTestHarness
                             |
               JUnit đợi bằng latch / timed poll
~~~

**Yêu cầu bắt buộc:** listener phải khai báo **`id` ổn định** trên `@RabbitListener` để harness tìm được spy hoặc capture. `getSpy("ordersListener")` truy vấn bằng **listener ID**, không phải tên Java method, queue hoặc tên bean Spring nếu chúng khác nhau.

Theo tài liệu chính thức, **method `final` không thể được spy hoặc advise** theo cơ chế này. Các method/lớp dùng proxy không tương thích cũng có thể gây khó khăn; cần kiểm tra cấu trúc proxy và version thư viện. Nếu code dùng Kotlin, lưu ý method/class được tạo `final` theo mặc định nếu không cấu hình mở phù hợp.

## 3. Dependency và phạm vi phiên bản

Ví dụ chính của bài dùng **Spring Boot 3.x + Spring AMQP 3.x**, Java 17+, JUnit Jupiter và Mockito. Các package và phương thức quan sát bên dưới cũng xuất hiện trong tài liệu Spring AMQP 4.x, nhưng tên starter và thư viện test của Spring Boot có thể khác khi chuyển dòng lớn.

Maven:

~~~xml
<dependencies>
    <!-- Ứng dụng chạy RabbitTemplate và @RabbitListener -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>

    <!-- JUnit Jupiter, AssertJ, Mockito, Spring Test -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- @RabbitListenerTest, RabbitListenerTestHarness, TestRabbitTemplate -->
    <dependency>
        <groupId>org.springframework.amqp</groupId>
        <artifactId>spring-rabbit-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Chỉ cần nếu chọn test broker thật bằng Testcontainers -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>rabbitmq</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để dùng `@ServiceConnection` trong ví dụ, cần **Spring Boot 3.1+** và module `spring-boot-testcontainers`, cùng Docker có thể chạy container. Version các dependency nên do BOM tương thích với Spring Boot quản lý. Với Spring Boot 4.x, hãy kiểm tra tên starter và các module Testcontainers tương ứng thay vì trộn phiên bản test 3.x với runtime 4.x.

**Không đặt `spring-rabbit-test` ở scope runtime/production** chỉ để nhìn listener hoạt động. Harness đưa Mockito/proxy testing vào context, dành cho test.

### 3.1. Import quan trọng

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.test.RabbitListenerTest;
import org.springframework.amqp.rabbit.test.RabbitListenerTestHarness;
import org.springframework.amqp.rabbit.test.RabbitListenerTestHarness.InvocationData;
import org.springframework.amqp.rabbit.test.mockito.LatchCountDownAndCallRealMethodAnswer;
~~~

`@RabbitListenerTest` không phải `@RabbitListener` và không phải `@SpringRabbitTest`:

- `@RabbitListener`: khai báo endpoint tiêu thụ.
- `@RabbitListenerTest`: thay bean post-processor để spy/capture endpoint có ID.
- `@SpringRabbitTest`: giúp thêm một số infrastructure bean cho Spring test context **không dùng auto-configuration của Spring Boot**; nó không tự thay thế harness.

## 4. Chuẩn bị ví dụ có hai listener

Ta dùng hai queue **test-only** và hai listener khác chức năng:

- `auditListener` là **one-way**, nhận một string, trả `void`.
- `rpcListener` là **request–reply**, nhận một string, trả string viết hoa.

### 4.1. Topology trong test

Dùng `AnonymousQueue` để tạo queue độc lập với tên ngẫu nhiên, tránh va chạm với queue production hoặc test khác:

~~~java
// ListenerHarnessTopology.java
import org.springframework.amqp.core.AnonymousQueue;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ListenerHarnessTopology {
    @Bean("harnessAuditQueue")
    Queue harnessAuditQueue() {
        return new AnonymousQueue();
    }

    @Bean("harnessRpcQueue")
    Queue harnessRpcQueue() {
        return new AnonymousQueue();
    }
}
~~~

Ví dụ sử dụng **default exchange** của RabbitMQ (tên exchange rỗng `""`): routing key là tên queue. Default exchange tự có binding đến các queue theo tên, nên không cần thêm một direct exchange cho bài cơ bản. Khi test nghiệp vụ thực, bạn nên provision exchange, binding và routing key riêng để kiểm tra đường đi đầy đủ.

Spring Boot thường tạo `RabbitAdmin` để khai báo `Queue` bean khi `spring.rabbitmq.dynamic` được bật (mặc định phổ biến). Cần broker thật và permission khai báo queue. `AnonymousQueue` được khai báo theo tên sinh ngẫu nhiên của context; không dùng tên cố định hoặc lấy tên queue từ một context khác.

### 4.2. One-way listener

~~~java
// AuditEventListener.java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AuditEventListener {
    @RabbitListener(
        id = "auditListener",
        queues = "#{harnessAuditQueue.name}"
    )
    public void handle(String eventId) {
        // Có thể gọi một business service/repository thật ở đây.
        // Ví dụ bài này tập trung quan sát invocation.
        System.out.println("Audit event: " + eventId);
    }
}
~~~

### 4.3. Request–reply listener

~~~java
// RpcExampleListener.java
import java.util.Locale;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class RpcExampleListener {
    @RabbitListener(
        id = "rpcListener",
        queues = "#{harnessRpcQueue.name}"
    )
    public String uppercase(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

Mỗi `@RabbitListener` có **ID riêng**. Tên bean queue `harnessAuditQueue` và `harnessRpcQueue` được SpEL tham chiếu bằng `#{...}` tại thời điểm Spring cấu hình listener. Để chạy ví dụ, các lớp phải nằm trong package được Spring Boot scan (hoặc được `@Import`), và ứng dụng có một `@SpringBootApplication`:

~~~java
// ListenerHarnessDemoApplication.java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ListenerHarnessDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ListenerHarnessDemoApplication.class, args);
    }
}
~~~

Trong ứng dụng thực, chỉ đặt **queue/test fixture** vào test source set; không đưa `AnonymousQueue` kiểm thử vào topology production. Ví dụ trên chia file theo tên chú thích để độc giả có thể đặt lại tại `src/test/java` hoặc một module demo phù hợp.

## 5. Kích hoạt spy và capture chỉ trong test

~~~java
// HarnessTestConfig.java (src/test/java)
import org.springframework.amqp.rabbit.test.RabbitListenerTest;
import org.springframework.boot.test.context.TestConfiguration;

@TestConfiguration(proxyBeanMethods = false)
@RabbitListenerTest(spy = true, capture = true)
public class HarnessTestConfig {
}
~~~

`@RabbitListenerTest` là annotation của module `spring-rabbit-test`, giúp thay processor thông thường bằng **`RabbitListenerTestHarness`** và kích hoạt detection `@RabbitListener` thông qua `@EnableRabbit`. Import cấu hình này vào Spring **test context**, đừng thêm nó vào `@SpringBootApplication` của production.

Khi chạy với `@SpringBootTest`, các bean `RabbitTemplate`, `ConnectionFactory`, `RabbitAdmin` và listener container factory thường do auto-configuration cung cấp. Khi dùng một Spring context tối giản không có Boot, bạn phải tự khai báo bean phù hợp hoặc dùng `@SpringRabbitTest` để có infrastructure cơ bản.

**Nếu harness bean không có hoặc `getSpy(id) == null`**, kiểm tra đầu tiên: cấu hình `@RabbitListenerTest` có thật sự được import, listener có ID, bean listener đã được Spring xử lý và method có thể proxy hay không.

## 6. Test tích hợp với RabbitMQ thật bằng Testcontainers

Testcontainers khởi tạo một RabbitMQ broker riêng để kiểm tra đường đi **RabbitTemplate → broker → queue → listener container**. `@ServiceConnection` cung cấp connection details cho Spring Boot, tránh hard-code port RabbitMQ đang được Docker ánh xạ.

Ví dụ dưới giả định các class `ListenerHarnessDemoApplication`, `ListenerHarnessTopology`, `AuditEventListener`, `RpcExampleListener` và `HarnessTestConfig` ở cùng package hợp lệ như các mục trước:

~~~java
// ListenerHarnessIntegrationTest.java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.test.RabbitListenerTestHarness;
import org.springframework.amqp.rabbit.test.RabbitListenerTestHarness.InvocationData;
import org.springframework.amqp.rabbit.test.mockito.LatchCountDownAndCallRealMethodAnswer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;

@Testcontainers
@SpringBootTest(classes = ListenerHarnessDemoApplication.class)
@Import(HarnessTestConfig.class)
class ListenerHarnessIntegrationTest {

    @Container
    @ServiceConnection
    static RabbitMQContainer broker =
            new RabbitMQContainer("rabbitmq:4.1-management");

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Autowired
    RabbitListenerTestHarness harness;

    @Autowired
    @Qualifier("harnessAuditQueue")
    Queue auditQueue;

    @Autowired
    @Qualifier("harnessRpcQueue")
    Queue rpcQueue;

    @Test
    void oneWayListenerWasCalled() throws Exception {
        // getSpy nhận đúng @RabbitListener.id.
        AuditEventListener spy = harness.getSpy("auditListener");
        assertNotNull(spy);

        // Phải lắp Answer TRƯỚC khi gửi để không bỏ lỡ lời gọi.
        LatchCountDownAndCallRealMethodAnswer answer =
                harness.getLatchAnswerFor("auditListener", 1);
        doAnswer(answer).when(spy).handle(anyString());

        // Default exchange: routing key = tên queue.
        rabbitTemplate.convertAndSend(auditQueue.getName(), "evt-101");

        // Chờ tối đa 10 giây; không gọi verify ngay sau send.
        assertTrue(answer.await(10), "listener was not called");
        verify(spy).handle("evt-101");

        // Vì capture=true, ta kiểm tra thêm arguments/throwable.
        InvocationData data = harness.getNextInvocationDataFor(
                "auditListener", 5, TimeUnit.SECONDS);

        assertNotNull(data, "capture record not found");
        assertEquals("evt-101", data.getArguments()[0]);
        assertNull(data.getResult());       // void listener
        assertNull(data.getThrowable());    // listener không ném lỗi
    }

    @Test
    void requestReplyListenerReturnedExpectedResult() throws Exception {
        // convertSendAndReceive chờ reply của @RabbitListener.
        Object reply = rabbitTemplate.convertSendAndReceive(
                rpcQueue.getName(), "spring amqp");
        assertEquals("SPRING AMQP", reply);

        InvocationData data = harness.getNextInvocationDataFor(
                "rpcListener", 5, TimeUnit.SECONDS);
        assertNotNull(data);
        assertEquals("spring amqp", data.getArguments()[0]);
        assertEquals("SPRING AMQP", data.getResult());
        assertNull(data.getThrowable());

        RpcExampleListener spy = harness.getSpy("rpcListener");
        assertNotNull(spy);
        verify(spy).uppercase("spring amqp");
    }
}
~~~

**Khi sử dụng ví dụ này:** file test đặt ở `src/test/java`, Spring Boot app ở package được scan; Docker phải chạy được. `spring-rabbit-test` và Mockito có scope test. Nếu trong project có nhiều `RabbitTemplate` hoặc listener container factory, hãy dùng `@Qualifier` để tiêm đúng bean, không dựa vào bean `@Primary` ngẫu nhiên.

### 6.1. Cách đọc kết quả one-way

Trong `oneWayListenerWasCalled()`:

1. `harness.getSpy("auditListener")` lấy Mockito spy được harness tạo cho listener mang ID đó.
2. `getLatchAnswerFor("auditListener", 1)` tạo `Answer` đặc biệt có latch một lần; nó **gọi phương thức thật** thay vì thay toàn bộ nghiệp vụ bằng stub.
3. `doAnswer(answer).when(spy).handle(anyString())` gắn Answer **trước khi gửi message**.
4. `rabbitTemplate.convertAndSend(...)` publish qua broker thật.
5. `answer.await(10)` cho test thread chờ tối đa **10 giây** để method listener chạy.
6. `verify(spy).handle("evt-101")` kiểm tra tham số của invocation, và `InvocationData` cho phép xem thêm return/exception.

**Tại sao không dùng `Thread.sleep(1000)`?** Thời gian consumer start, Docker scheduling và broker routing thay đổi giữa CI/local. Sleep ngắn có thể gây flaky test; sleep dài làm bộ test chậm không cần thiết. Timed wait bằng latch/capture chờ **đúng sự kiện** rồi kết thúc sớm.

**Vì sao dùng `harness.getLatchAnswerFor(...)` thay vì một `CountDownLatch` trong `doAnswer` tự chế?** Spring AMQP tạo proxy/spy quanh listener; Answer được harness cấu hình để **forward đến delegate thực** đúng cách. Nếu tự viết Answer không forward đúng, test có thể đếm được một lời gọi nhưng **logic listener thật không chạy**, làm kết quả sai.

### 6.2. Cách đọc kết quả request–reply

Trong `requestReplyListenerReturnedExpectedResult()`, `RabbitTemplate.convertSendAndReceive(...)` đã chờ reply nên ta không cần chờ thêm lâu trước khi kiểm tra phản hồi. Tuy nhiên, gọi `getNextInvocationDataFor("rpcListener", 5, SECONDS)` vẫn hữu ích để lấy **kết quả thật của listener invocation**, thay vì chỉ dựa vào kết quả được converter trả về.

`InvocationData.getArguments()` phản ánh arguments của method sau bước Spring chuyển đổi/resolve tham số, chứ không nhất thiết là toàn bộ raw AMQP bytes. `getResult()` là giá trị method trả về; `getThrowable()` là exception được capture nếu phương thức ném lỗi.

Lưu ý: test request–reply dùng RabbitMQ thật xác nhận đường đi tới listener và reply được gửi lại qua broker, nhưng **không tự chứng minh publisher confirm cho các publish khác hoặc hoàn thành transaction nghiệp vụ ngoài method**.

### 6.3. Điều gì khiến test có thể thất bại lúc khởi động?

| Triệu chứng | Nguyên nhân hay gặp |
| --- | --- |
| Không kết nối được RabbitMQ | Docker/Testcontainers chưa chạy, policy không cho chạy container, container chưa sẵn sàng. |
| Không tạo được `AnonymousQueue` | RabbitAdmin không khai báo queue, user thiếu configure permission, listener khởi động trước topology. |
| Không tìm thấy `RabbitListenerTestHarness` | Chưa import `HarnessTestConfig` hoặc thiếu dependency `spring-rabbit-test`. |
| `getSpy("auditListener") == null` | Annotation ID sai, `spy=false`, listener không qua harness hoặc method không proxy được. |
| Không có `InvocationData` | `capture=false`, sai listener ID, test đọc dữ liệu quá sớm hoặc listener không chạy. |
| Message không tới listener | Sai queue/routing, container chưa start, consumer cạnh tranh, message converter lỗi. |

Đừng sửa lỗi bằng cách tăng timeout từ 10 giây lên vài phút ngay. Trước tiên kiểm tra bean, consumer/container, queue/exchange/binding và broker logs; timeout lớn có thể chỉ che race hoặc lỗi topology.

## 7. Test capture-only: không cần Mockito spy

Khi chỉ muốn **quan sát tham số, kết quả và exception** mà không cần stubbing/verifying bằng Mockito, có thể đổi cấu hình:

~~~java
@TestConfiguration(proxyBeanMethods = false)
@RabbitListenerTest(spy = false, capture = true)
public class CaptureOnlyHarnessConfig {
}
~~~

Test sau chỉ cần gửi rồi chờ capture:

~~~java
rabbitTemplate.convertAndSend(auditQueue.getName(), "evt-202");

InvocationData data =
        harness.getNextInvocationDataFor("auditListener", 10, TimeUnit.SECONDS);

assertNotNull(data, "listener did not invoke within deadline");
assertEquals("evt-202", data.getArguments()[0]);
assertNull(data.getResult());
assertNull(data.getThrowable());
~~~

**Chỉ sử dụng một cấu hình `@RabbitListenerTest` phù hợp trong một test context.** Đoạn `CaptureOnlyHarnessConfig` là lựa chọn **thay thế `HarnessTestConfig`** ở mục 5, không phải bean cần import thêm vào cùng test. Vì `spy=false`, `getSpy("auditListener")` không trả một Mockito spy để verify.

Điểm mạnh của `getNextInvocationDataFor(id, wait, unit)` là nó đọc dữ liệu từ **hàng đợi capture riêng theo listener ID** và có thể block test thread đến thời hạn. Không cần tự sửa code production để chèn latch hoặc debug flag.

## 8. Chờ nhiều lời gọi và kiểm tra thứ tự

Ví dụ listener nhận 3 message:

~~~java
String[] events = {"evt-1", "evt-2", "evt-3"};
for (String event : events) {
    rabbitTemplate.convertAndSend(auditQueue.getName(), event);
}

for (String expected : events) {
    InvocationData data = harness.getNextInvocationDataFor(
            "auditListener", 10, TimeUnit.SECONDS);
    assertNotNull(data);
    assertEquals(expected, data.getArguments()[0]);
    assertNull(data.getThrowable());
}
~~~

Đoạn trên **chỉ thích hợp khi test cố ý cấu hình một consumer, một queue và đường xử lý tuần tự**. Nếu có nhiều consumer hoặc concurrency lớn hơn 1, thứ tự hoàn thành các method invocation **không luôn giống thứ tự publish**. Lúc đó, thu thập 3 IDs và kiểm tra **tập dữ liệu**, không assert thứ tự không được hợp đồng bảo đảm.

Một dạng spy với latch nhiều lượt:

~~~java
AuditEventListener spy = harness.getSpy("auditListener");
LatchCountDownAndCallRealMethodAnswer answer =
        harness.getLatchAnswerFor("auditListener", 3);
doAnswer(answer).when(spy).handle(anyString());

for (int i = 1; i <= 3; i++) {
    rabbitTemplate.convertAndSend(auditQueue.getName(), "batch-" + i);
}

assertTrue(answer.await(10));
verify(spy).handle("batch-1");
verify(spy).handle("batch-2");
verify(spy).handle("batch-3");
~~~

`await(10)` ở đây là **10 giây** và chỉ báo latch đạt số lượt kỳ vọng. Nếu hệ thống có retry/redelivery, ba lượt listener invocation **có thể không tương ứng ba message logic khác nhau**. Để kiểm tra chính xác “mỗi event xử lý thành công đúng một lần” cần **eventId + dữ liệu DB/inbox + business assertions**, không chỉ đếm invocation.

### 8.1. Đừng dùng verify(noMoreInteractions) khi vẫn đang chạy asynchronous

Một assert như `verify(spy, times(1)).handle("evt-1")` có ý nghĩa tại thời điểm thực thi. Nếu container có thể retry sau đó, test không chứng minh listener sẽ **không bao giờ** gọi lại. Tính đúng của hệ thống at-least-once nên được kiểm chứng bằng idempotency key và trạng thái nghiệp vụ.

Trong test thứ tự nghiêm ngặt, kiểm soát consumer count, prefetch, retry, queue độc lập, dữ liệu sạch và đồng bộ trước khi assert. Không suy luận trật tự toàn cục qua nhiều queue/consumer trong RabbitMQ.

## 9. Kiểm tra lỗi phương thức bằng InvocationData

Một lợi thế của `capture=true` là lấy được exception method đã ném. Ví dụ mở rộng listener:

~~~java
// Ví dụ một listener lỗi, cần queue riêng trong test.
@RabbitListener(id = "invalidEventListener", queues = "harness.invalid.q")
public void validate(String payload) {
    if (payload.startsWith("INVALID:")) {
        throw new IllegalArgumentException("invalid test event");
    }
}
~~~

Test đọc exception:

~~~java
rabbitTemplate.convertAndSend("harness.invalid.q", "INVALID:abc");

InvocationData data = harness.getNextInvocationDataFor(
        "invalidEventListener", 10, TimeUnit.SECONDS);

assertNotNull(data);
assertEquals("INVALID:abc", data.getArguments()[0]);
assertNotNull(data.getThrowable());
assertEquals("invalid test event",
        data.getThrowable().getMessage());
~~~

**Cảnh báo quan trọng:** đây là đoạn mở rộng, không thể chạy độc lập nếu chưa tạo queue `harness.invalid.q` và gắn listener vào test context. Nếu listener throw, container có thể retry hoặc **requeue vô hạn** theo mặc định; một test không giới hạn lỗi có thể tạo hàng nghìn invocation và làm CI treo.

Để kiểm tra **đúng một lần reject rồi vào DLQ**, test cần:

- Queue đầu vào và dead-letter exchange/queue được khai báo đúng.
- Container factory có `defaultRequeueRejected=false` hoặc cơ chế retry hữu hạn + recoverer phù hợp.
- Listener throw exception không retry hoặc hết số lần thử theo cấu hình.
- Assertion **trên DLQ** hoặc dữ liệu nghiệp vụ, không chỉ `InvocationData.getThrowable()`.

`getThrowable()` chỉ chứng minh method đã ném lỗi; nó **không nói broker đã NACK, đã requeue hay đã dead-letter**. Các hành động đó xảy ra ở container/broker sau khi lời gọi listener được xử lý.

## 10. Mockito spy, delegate và LambdaAnswer: dùng đúng để không phá test

`harness.getSpy(id)` là **Mockito spy**, nghĩa là nó có thể gọi logic thật nhưng cũng có thể bị stubbed. Vì vậy, cách viết test quyết định việc code nghiệp vụ có chạy hay không.

### 10.1. Stubbing có thể che lỗi nghiệp vụ

Xét đoạn giả định:

~~~java
AuditEventListener spy = harness.getSpy("auditListener");

// Stubbing tùy ý bằng Answer không forward đến method thật:
doAnswer(invocation -> null)
        .when(spy).handle(anyString());
~~~

Nếu sau đó test chỉ kiểm tra `verify(spy).handle("evt-101")`, nó có thể **PASS dù phần thân `handle` không hề chạy**. Đây là test xác nhận phương thức được gọi, không phải kiểm thử kết quả thực thi.

Muốn giữ logic thật khi đếm lời gọi `void`, ưu tiên:

~~~java
LatchCountDownAndCallRealMethodAnswer answer =
        harness.getLatchAnswerFor("auditListener", 1);
doAnswer(answer).when(spy).handle(anyString());
~~~

Đây là Answer được Spring AMQP thiết kế để **forward invocation đến delegate** tương ứng. Với các Answer tùy biến, tài liệu Spring nhấn mạnh cần dùng kiểu forward-to-delegate phù hợp; nếu không, có thể gặp đệ quy vào spy hoặc bỏ qua logic thật.

### 10.2. getDelegate(id)

`getDelegate("auditListener")` trả về object listener **thực** ở dưới lớp spy. Nó hữu ích khi cần viết một Answer tùy biến mà vẫn gọi phương thức thật, hoặc điều tra khi proxy khiến test hiểu nhầm một lần gọi.

~~~java
AuditEventListener actual = harness.getDelegate("auditListener");
assertNotNull(actual);

AuditEventListener spy = harness.getSpy("auditListener");
assertNotNull(spy);
// spy và delegate không phải cùng mục đích quan sát.
~~~

**Không gọi `getDelegate(...).handle(...)` để giả lập broker đã giao message.** Một lời gọi trực tiếp vào delegate không đi qua RabbitMQ, listener adapter, conversion, error handling hay ACK. Test broker-backed nên publish qua `RabbitTemplate`.

### 10.3. LambdaAnswer

`harness.getLambdaAnswerFor(id, callRealMethod, callback)` cung cấp một `LambdaAnswer` được tạo đúng cho spy. Có thể dùng để khảo sát return value hoặc xử lý thêm thông tin khi method trả kết quả:

~~~java
RpcExampleListener spy = harness.getSpy("rpcListener");

var answer = harness.<String>getLambdaAnswerFor(
        "rpcListener",
        true,  // vẫn gọi phương thức thật
        (invocation, realResult) -> realResult);

doAnswer(answer).when(spy).uppercase(anyString());
~~~

Ví dụ này trả lại kết quả thật; callback có thể thêm kiểm tra hoặc biến đổi kết quả trong một test đặc biệt. Nếu callback cố ý thay return value, response gửi tới caller cũng có thể thay đổi — **đừng coi đó là kết quả logic production ban đầu**. Với nhu cầu chỉ kiểm tra result, `capture=true` và `InvocationData.getResult()` thường dễ hiểu hơn.

Trong Spring AMQP 2.2.3+ các helper Answer có cơ chế thu thập exception; ví dụ `answer.getExceptions()` giúp điều tra nếu delegate ném lỗi. Vẫn cần kiểm tra ACK/retry/DLQ riêng.

## 11. TestRabbitTemplate: khi nào không cần RabbitMQ thật?

Module `spring-rabbit-test` còn có **`TestRabbitTemplate`**. Nó tìm listener container trong Spring context và **gọi message listener trực tiếp** trong test, **không cần broker RabbitMQ chạy**. Nó hỗ trợ định tuyến cơ bản **theo queue name** và request–reply cho listener trả kết quả.

Sự khác biệt:

| Khả năng | `TestRabbitTemplate` (không broker) | `RabbitTemplate` + RabbitMQ/Testcontainers |
| --- | --- | --- |
| Gọi logic listener qua Spring adapter | Có, với các giới hạn mô phỏng. | Có, qua broker thật. |
| Định tuyến bằng exchange và binding thật | **Không**; chỉ mô phỏng theo queue name. | Có. |
| Kiểm tra consumer concurrency và redelivery broker | Không phản ánh đầy đủ. | Có thể kiểm tra bằng cấu hình thích hợp. |
| Kiểm tra ACK/NACK, DLX, publisher confirm | Không thể thay cho broker thật. | Có, nếu test chủ động quan sát. |
| Tốc độ test | Nhanh và không cần Docker. | Chậm hơn, phải khởi động/khai báo broker. |
| Kết hợp với harness để quan sát method | Có thể, trong Spring context cấu hình đúng. | Có, đầy đủ đường đi message. |

Ví dụ gọi `TestRabbitTemplate` theo tên queue:

~~~java
// Ví dụ khi test context đã đăng ký TestRabbitTemplate
// và các listener container tương ứng.
testRabbitTemplate.convertAndSend("test.orders.q", "evt-501");

InvocationData data = harness.getNextInvocationDataFor(
        "ordersListener", 1, TimeUnit.SECONDS);
assertNotNull(data);
assertEquals("evt-501", data.getArguments()[0]);
~~~

**Đoạn này minh họa cách sử dụng**, chưa phải test độc lập: cần một bean `TestRabbitTemplate`, queue/listener ID phù hợp và Spring context có listener containers. Trong brokerless test, method listener có thể được gọi **ngay trên test thread**, nên không cần suy đoán timing của broker; vẫn phải phân biệt đường mô phỏng này với vận hành thật.

Khi test cần kiểm chứng **exchange type, routing key, queue binding, retry, DLQ, publisher confirms hoặc transaction AMQP**, chọn RabbitMQ thật/Testcontainers. Nếu chỉ cần kiểm thử phương thức xử lý dữ liệu, có thể dùng unit test gọi service trực tiếp mà không cần harness.

## 12. Harness đặt ở đâu trong chiến lược kiểm thử?

Nên tổ chức test theo nhiều lớp, mỗi lớp có phạm vi và tốc độ khác nhau:

| Loại test | Thành phần thật | Assertion nên có |
| --- | --- | --- |
| **Unit test business service** | Java service, mock repository hoặc test database. | Input/output, validation, idempotency và logic nghiệp vụ. |
| **Listener adapter test không broker** | Spring listener adapter, `TestRabbitTemplate`, harness. | Conversion, method arguments, trả lời, exception ở cấp listener. |
| **Broker-backed integration test** | `RabbitTemplate`, RabbitMQ, listener container, harness. | Message đến đúng listener, tham số, result/throwable, tương tác broker. |
| **Reliability integration test** | Broker, DB thật hoặc Testcontainers, retry/DLX/ACK. | DB commit, duplicate-safe behavior, DLQ, redelivery và phục hồi. |
| **End-to-end test** | Nhiều service/DB/broker thực hoặc mô phỏng gần production. | Điều kiện hoàn tất nghiệp vụ và độ trễ đầu cuối. |

### 12.1. Điều harness không tự chứng minh

| Kiểm tra bằng harness | Chưa thể suy ra |
| --- | --- |
| `getSpy(id)` khác `null` | Broker khỏe hay queue đã tồn tại. |
| `verify(spy).handle("evt-1")` | Publisher confirm ACK hoặc DB commit thành công. |
| `getResult() == "OK"` | Reply tới caller thành công hoặc đã được downstream chấp nhận. |
| `getThrowable() != null` | RabbitMQ đã reject, requeue hoặc dead-letter. |
| Một invocation duy nhất | Message sẽ không bị redeliver trong tương lai. |
| Hai invocation với cùng payload | Chắc chắn producer đã publish hai lần. |

Khi test nghiệp vụ, **kiểm tra cả kết quả ở database/side effect**. Ví dụ listener tạo tác vụ giao hàng, harness có thể nói listener đã được gọi, nhưng test reliability phải xác minh bảng task có đúng một record với `eventId` và trạng thái mong đợi.

### 12.2. Kiểm thử producer và consumer độc lập

Consumer có thể đúng nhưng producer publish sai routing key. Vì vậy có thể có:

- **Publisher test**: gửi qua exchange, kiểm tra publisher confirm/return và message tới queue đúng. Harness chưa cần tham gia.
- **Listener test**: tạo message trực tiếp vào queue, harness xác nhận arguments/result/throwable.
- **Integration test đầy đủ**: publish theo đường nghiệp vụ thật rồi kiểm tra listener và kết quả DB.

Đặc biệt trong hệ thống có nhiều broker/vhost, listener test phải dùng đúng `ConnectionFactory` và container factory; một harness bean không tự phân biệt được kết nối test đã trỏ đúng broker hay chưa nếu chỉ nhìn ID.

## 13. Lỗi flakiness và cách thiết kế test ổn định

### 13.1. Không giả định listener xử lý ngay sau publish

Sai:

~~~java
rabbitTemplate.convertAndSend(queueName, "evt-1");
verify(harness.getSpy("auditListener")).handle("evt-1");
~~~

Phần verify chạy trên JUnit thread có thể đến **trước** consumer thread. Đúng hơn là sử dụng `getLatchAnswerFor` hoặc `getNextInvocationDataFor` với timeout hữu hạn. Mockito `timeout(...)` cũng có thể hữu ích nhưng không thay thế cơ chế đảm bảo phương thức thật chạy như harness Answer.

### 13.2. Đừng để test dùng chung một queue

Nếu hai test class dùng chung queue cố định trên local RabbitMQ, một consumer ở test A có thể lấy mất message của test B. Kết quả là test B đôi lúc timeout, đôi lúc pass.

Biện pháp:

1. Dùng **broker Testcontainers riêng** theo phạm vi suite/class thích hợp.
2. Dùng `AnonymousQueue` hoặc queue name có suffix duy nhất nếu thực sự cần test song song.
3. Không khởi động nhiều listener cạnh tranh trên cùng queue trừ khi đang kiểm tra competing consumers.
4. Không để môi trường CI trỏ tới RabbitMQ production hoặc shared vhost có message nghiệp vụ.

### 13.3. Dọn dữ liệu capture và Mockito interactions

`getNextInvocationDataFor(...)` **lấy một record khỏi hàng đợi capture**. Nếu test trước đã tạo invocation mà không lấy ra, test sau đọc cùng listener ID có thể thấy **record cũ**. Không tái sử dụng Spring context và queue theo cách gây nhiễu mà không dọn trạng thái.

Mockito spy giữ lịch sử tương tác, nên `verify(spy, times(1))` ở test sau có thể đếm cả lần gọi của test trước nếu dùng chung context. Có thể tách test context, thiết kế queue/ID riêng hoặc reset interactions có kiểm soát — **chỉ reset sau khi chắc chắn không còn invocation bất đồng bộ**, và không reset spy giữa lúc listener đang xử lý.

### 13.4. Container startup và timeout

Kiểm tra trước khi publish:

- RabbitMQ container đã ready, connection có thể tạo.
- Queue đã được RabbitAdmin khai báo.
- Listener container đã start và đang consume đúng queue.
- Không có startup exception từ MessageConverter, SpEL hoặc bean resolver.

Nếu cần, lấy `RabbitListenerEndpointRegistry` để kiểm tra tình trạng container theo ID:

~~~java
import org.springframework.amqp.rabbit.listener.RabbitListenerEndpointRegistry;

// Inject registry vào test.
var container = registry.getListenerContainer("auditListener");
assertNotNull(container);
assertTrue(container.isRunning());
~~~

Container **isRunning()** là bằng chứng lifecycle đã start, **không bảo đảm broker đã cấp consumer hoặc message sẽ được xử lý ngay**. Điều kiện test quan trọng nhất vẫn là chờ đúng invocation/side effect.

### 13.5. Concurrency, retry và độ chính xác của assertions

Khi xử lý bất đồng bộ với nhiều consumer:

- Đừng assert thứ tự toàn cục nếu không có hợp đồng bảo đảm thứ tự.
- Đừng dùng số invocation để suy ra số business event duy nhất khi có retry.
- Đừng chờ vô hạn; đặt deadline rõ ràng và log state khi timeout.
- Tránh callback Answer giữ lock lâu, gọi HTTP chậm hoặc tự publish vòng lặp.
- Với lỗi có thể tái xử lý, assert theo **eventId và kết quả cuối cùng**, không chỉ theo tham số method.

Khi test một message cần retry đúng 3 lần, hãy cấu hình retry policy/chế độ ACK rõ ràng và quan sát attempts ở cấp thích hợp. Không coi `getLatchAnswerFor("id", 3)` là công cụ tự cấu hình retry.

## 14. Tình huống thực tế: listener tạo bản ghi nghiệp vụ

Giả sử `OrderCreatedListener` nhận `order.created` rồi tạo một tác vụ giao hàng:

~~~java
@RabbitListener(
    id = "orderCreatedListener",
    queues = "fulfillment.order.created.q"
)
public void onOrderCreated(String json) {
    OrderCreated event = decoder.decode(json);
    fulfillmentService.acceptOnce(event.eventId(), event.orderId());
}
~~~

Trong test end-to-end tích hợp, không nên chỉ viết:

~~~java
verify(harness.getSpy("orderCreatedListener"))
        .onOrderCreated(anyString());
~~~

Nó chứng minh method đã được gọi với một string, nhưng **chưa chứng minh** JSON được parse đúng, `acceptOnce` commit thành công hay một task được tạo đúng một lần.

Một quy trình có thể kiểm tra:

1. Ghi một event `eventId=evt-700`, `orderId=ORD-700` vào exchange bằng `RabbitTemplate` thật.
2. Dùng harness capture chờ `orderCreatedListener` được gọi với JSON tương ứng.
3. Kiểm tra database có **một task** đúng `eventId/orderId` và trạng thái mong đợi.
4. Phát lại cùng payload để mô phỏng redelivery hoặc duplicate publish.
5. Kiểm tra harness có thể quan sát **hai lần gọi listener**, nhưng database **vẫn chỉ có một task** nhờ unique constraint và logic idempotency.
6. Mô phỏng lỗi database trước commit, bảo đảm không ghi dấu inbox thành công sai; kiểm tra retry/DLQ theo policy.
7. Kiểm tra publisher confirm, ACK, queue depth và DLQ riêng khi mục tiêu test là độ tin cậy đầu cuối.

Ở đây hai assertion **hai lần gọi method** và **một tác dụng phụ nghiệp vụ** không hề mâu thuẫn. RabbitMQ và Spring AMQP có thể vận hành theo ngữ nghĩa at-least-once; vì vậy, test idempotency nên dựa vào trạng thái bền vững.

## 15. Bảng tra cứu API RabbitListenerTestHarness

| API | Yêu cầu | Công dụng và lưu ý |
| --- | --- | --- |
| `@RabbitListenerTest` | `spring-rabbit-test`, đặt trên configuration của test. | Kích hoạt harness; mặc định `spy=true, capture=false`. |
| `harness.getSpy("id")` | `spy=true`, listener có `id`. | Lấy Mockito spy để `verify` hoặc `doAnswer`. |
| `harness.getDelegate("id")` | Listener có `id` và được harness xử lý. | Lấy object listener thật, dùng cho advanced Answer/điều tra proxy. |
| `harness.getLatchAnswerFor("id", count)` | `spy=true`; thường dùng method `void`. | Answer gọi method thật và đếm latch; `await(seconds)`. |
| `harness.getLambdaAnswerFor("id", true, callback)` | `spy=true`. | Callback gắn với kết quả method thật, có thể điều chỉnh giá trị trong test. |
| `harness.getNextInvocationDataFor("id", wait, unit)` | **`capture=true`**. | Lấy invocation tiếp theo, chờ hữu hạn; trả `null` nếu chưa có trong thời gian chờ. |
| `data.getArguments()` | `InvocationData` khác `null`. | Tham số method đã được gọi. |
| `data.getResult()` | `InvocationData` khác `null`. | Giá trị trả về của method; `null` với `void` hoặc method trả `null`. |
| `data.getThrowable()` | `InvocationData` khác `null`. | Exception của method nếu có, không tự nói ACK/NACK. |

**Mẹo chọn cách kiểm thử:**

- **Chỉ cần biết invocation, arguments, result, exception** → `@RabbitListenerTest(spy=false, capture=true)` và `getNextInvocationDataFor` là lựa chọn gọn.
- **Cần Mockito.verify, stubbing hoặc latch count** → `spy=true` và `getSpy`; với method `void` dùng `getLatchAnswerFor`.
- **Muốn cả Mockito và capture** → `spy=true, capture=true`, như ví dụ tích hợp.
- **Muốn kiểm tra exchange–binding–queue, ACK, DLQ, publisher confirm** → phải có broker thật hoặc môi trường test gần broker thật.

## 16. Bài thực hành

**Bối cảnh:** một service nhận sự kiện thanh toán `payment.completed`. Sau khi listener chạy, hệ thống lưu bản ghi nghiệp vụ và có thể phát sự kiện tiếp theo. Mục tiêu trước mắt là chứng minh listener đã nhận message đúng dữ liệu; sau đó mở rộng sang test reliability.

**Các bước triển khai:**

1. Khai báo queue test và listener `@RabbitListener(id = "paymentListener", queues = "...")` với method không `final`.
2. Thêm dependency `spring-rabbit-test`, JUnit Jupiter, Mockito và Spring Boot test support.
3. Tạo `@TestConfiguration @RabbitListenerTest(spy=true, capture=true)` và import vào test context.
4. Chạy RabbitMQ bằng Testcontainers hoặc một broker test riêng; tạo exchange, queue và binding đúng với message `payment.completed`.
5. Dùng `RabbitTemplate.convertAndSend` gửi message có `eventId` kiểm tra.
6. Lắp `getLatchAnswerFor("paymentListener",1)` **trước khi gửi**, chờ và `verify` spy.
7. Đọc `InvocationData` để kiểm tra argument, result và throwable.
8. Thêm message sai dữ liệu, quan sát `getThrowable()` và kiểm chứng retry/DLQ bằng broker state; bảo đảm không requeue vô hạn.
9. Phát hai message với cùng `eventId` và kiểm tra database chỉ có một thay đổi nghiệp vụ nhờ idempotency.
10. Cho 2 consumer chạy song song và điều chỉnh assertions theo **tập message nhận** thay vì thứ tự publish.

### Câu hỏi tự kiểm tra

**Câu 1.** Test gọi `convertAndSend()` xong `verify(spy)` ngay và thỉnh thoảng thất bại. Vì sao?

**Đáp án:** Listener chạy trên container thread và nhận message bất đồng bộ qua broker. `convertAndSend()` trả về không bảo đảm listener đã chạy. Dùng `getLatchAnswerFor` hoặc `getNextInvocationDataFor` với timeout để đồng bộ.

**Câu 2.** Đã khai báo `@RabbitListenerTest` nhưng `getNextInvocationDataFor` không trả dữ liệu. Kiểm tra gì?

**Đáp án:** `capture` mặc định **false**. Cần `@RabbitListenerTest(capture=true)`, listener có `id`, phương thức proxy được và test thực sự gửi message tới đúng queue.

**Câu 3.** Vì sao `harness.getSpy("orders")` trả `null` dù method tên `orders` tồn tại?

**Đáp án:** `getSpy` tra **`@RabbitListener.id`**, không theo tên method. Ngoài ra có thể do `spy=false`, thiếu test config hoặc method không thể spy.

**Câu 4.** `InvocationData.getThrowable()` cho biết `IllegalArgumentException`. Có thể kết luận message đã vào DLQ không?

**Đáp án:** Không. Exception được ghi lại tại method invocation; quyết định ACK/requeue/reject và dead-letter do listener container, error handler, retry policy và broker xử lý.

**Câu 5.** Một spy test dùng `doAnswer(invocation -> null)` cho listener `void` rồi `verify` PASS. Logic nghiệp vụ đã chắc chắn chạy chưa?

**Đáp án:** Chưa. Stubbing đó có thể chặn method thật. Dùng `harness.getLatchAnswerFor` để forward hoặc kiểm tra kết quả nghiệp vụ độc lập.

**Câu 6.** Vì sao `TestRabbitTemplate` không thay thế RabbitMQ thật khi test exchange/binding?

**Đáp án:** Nó gọi listener qua Spring context và chỉ mô phỏng routing theo **queue name**, không chạy broker routing, publisher confirm, ACK hay dead-letter thật.

**Câu 7.** Harness ghi nhận 2 lần listener xử lý cùng `eventId` nhưng database có 1 task. Có phải test thất bại?

**Đáp án:** Không nhất thiết. Đây có thể là xử lý duplicate/redelivery đúng theo at-least-once kết hợp idempotent consumer. Assertion nghiệp vụ cần bảo đảm **một tác dụng phụ duy nhất**.

## 17. Checklist chất lượng trước khi đưa test vào CI

- [ ] Dependency `spring-rabbit-test` và Mockito ở **test scope**.
- [ ] `@RabbitListenerTest` chỉ nằm trong test configuration được import đúng.
- [ ] Mỗi listener cần quan sát có **`id` rõ ràng, duy nhất**.
- [ ] Method listener không `final` và phù hợp cơ chế proxy của harness.
- [ ] Test chọn `spy`/`capture` đúng mục đích, không dựa vào giá trị mặc định khi cần capture.
- [ ] Với one-way message, dùng **timed wait**; không viết `Thread.sleep` dựa vào đoán thời gian.
- [ ] Với spy `void`, dùng `getLatchAnswerFor` để method thật được gọi.
- [ ] Test đọc đúng `InvocationData` và không tái sử dụng record cũ.
- [ ] Có queue/broker test độc lập; không có consumer ngoài suite tranh message.
- [ ] Nếu chạy song song, assertions không giả định thứ tự không được bảo đảm.
- [ ] Test lỗi có **retry giới hạn** và deadline, không tạo hot loop.
- [ ] Test reliability có assertions riêng về **DB commit, ACK/NACK, DLQ, outbox/inbox và idempotency**.
- [ ] Test broker-backed không kết nối tới RabbitMQ production.

## 18. Tổng kết

**`RabbitListenerTestHarness`** là công cụ của **`spring-rabbit-test`** giúp quan sát phương thức **`@RabbitListener`** trong ứng dụng Spring AMQP. Khi bật `@RabbitListenerTest` với các lựa chọn `spy` và `capture`, test có thể dùng **Mockito.verify**, **LatchCountDownAndCallRealMethodAnswer** hoặc **InvocationData** để xác minh listener được gọi với dữ liệu, kết quả và exception mong đợi.

Điểm thiết yếu của kiểm thử bất đồng bộ là **chờ đúng sự kiện** bằng latch hoặc timed capture, thay vì sleep hoặc verify ngay sau publish. Khi cần kiểm tra các tính năng thực của **RabbitMQ**, hãy dùng Testcontainers/broker thật; và khi cần độ tin cậy đầu cuối, bổ sung kiểm chứng **exchange–queue–binding, publisher confirm, ACK, retry, dead-letter, giao dịch, idempotency và trạng thái nghiệp vụ**. Harness là công cụ quan sát listener, **không phải bằng chứng duy nhất rằng message đã được giao và xử lý đáng tin cậy**.

### Tài liệu tham khảo

- [Spring AMQP Reference – Testing Support](https://docs.spring.io/spring-amqp/reference/testing.html): `@RabbitListenerTest`, spy/capture, `RabbitListenerTestHarness`, `TestRabbitTemplate`.
- [Spring AMQP 3.2 – Testing Support](https://docs.spring.io/spring-amqp/reference/3.2/testing.html): tài liệu tương ứng dòng 3.x dùng trong ví dụ.
- [Javadoc – RabbitListenerTestHarness (Spring AMQP 3.2)](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/test/RabbitListenerTestHarness.html): `getSpy`, `getDelegate`, `getLatchAnswerFor`, `getNextInvocationDataFor`.
- [Javadoc – RabbitListenerTest](https://docs.spring.io/spring-amqp/docs/3.2.5/api/org/springframework/amqp/rabbit/test/RabbitListenerTest.html): `spy` và `capture` mặc định.
- [Javadoc – LatchCountDownAndCallRealMethodAnswer](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/test/mockito/LatchCountDownAndCallRealMethodAnswer.html): `await` và gọi delegate thật.
- [Spring Boot 3.5 – Testcontainers and Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` và kết nối broker test.
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): khác biệt giữa lời gọi listener, ACK và publish confirm.
