# Truyền ngữ cảnh truy vết, danh tính và dữ liệu theo luồng trong Spring Messaging

## 1. Context trong một luồng xử lý message

Một request hoặc message thường mang theo nhiều thông tin ngoài payload nghiệp vụ. Khi một đơn hàng đi qua API gateway, service đơn hàng, thanh toán và thông báo, các bước cần biết message thuộc request nào, ai khởi tạo thao tác, tenant nào sở hữu dữ liệu và đang chạy trong trace nào.

Nhóm thông tin này thường được gọi chung là **context**. Trong ứng dụng Spring, context có thể tồn tại ở nhiều nơi:

- **Payload:** dữ liệu nghiệp vụ chính, ví dụ OrderCreated hoặc PaymentCommand.
- **Message headers:** metadata đi cùng Message<T>, ví dụ correlationId, traceId, actorId hoặc schemaVersion.
- **ThreadLocal:** context gắn với thread hiện tại, thường dùng cho logging MDC, observation hoặc SecurityContextHolder.
- **Reactor Context:** context gắn với subscription trong reactive pipeline, không gắn cố định với một thread.
- **Transport headers/properties:** metadata được serialize và gửi qua HTTP, JMS hoặc broker.

Không có một cơ chế duy nhất tự động mang mọi loại context qua mọi ranh giới. Cần xác định context nào phải đi theo message, context nào chỉ cần tồn tại trong một lần thực thi, và context nào cần được xác minh lại ở dịch vụ nhận.

| Loại context | Ví dụ | Mục đích |
|---|---|---|
| Truy vết kỹ thuật | traceId, spanId, traceparent | Liên kết các bước xử lý thành một trace |
| Tương quan nghiệp vụ | correlationId, requestId, orderId | Liên kết nhiều message cùng một nghiệp vụ |
| Danh tính và bảo mật | SecurityContext, Authentication, principal | Xác định caller và quyền được phép thực hiện |
| Metadata nghiệp vụ | tenantId, locale, schemaVersion, source | Giữ ngữ cảnh cần thiết để xử lý đúng dữ liệu |
| Context thực thi | MDC, Observation, ThreadLocal | Làm cho logging, tracing hoặc code đồng bộ đọc được context hiện hành |

Các loại này có thể liên quan nhưng không thay thế nhau. Trace ID giúp tìm log và span; nó không chứng minh người dùng có quyền đọc đơn hàng.

## 2. Message headers là kênh mang metadata tường minh

Spring Messaging dùng Message<T> để gói payload và MessageHeaders. MessageHeaders là cấu trúc metadata bất biến; hãy dùng MessageBuilder để tạo message mới khi cần thêm hoặc thay header.

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader("correlationId", "order-2026-113")
    .setHeader("traceId", "trace-abc")
    .setHeader("actorId", "user-42")
    .setHeader("schemaVersion", 2)
    .build();
~~~

Headers phù hợp với dữ liệu nhỏ, có kiểu đơn giản và có ý nghĩa ổn định giữa producer và consumer. Các ví dụ thường gặp:

- correlationId: mã liên kết các message của một nghiệp vụ.
- traceId: mã trace kỹ thuật nếu ứng dụng đang quản lý propagation theo quy ước riêng.
- actorId: mã chủ thể thực hiện thao tác, phục vụ audit hoặc hiển thị.
- tenantId: tenant mà message thuộc về, sau khi được xác minh tại ranh giới tin cậy.
- locale: ngôn ngữ hoặc locale cần thiết cho bước xử lý sau.
- schemaVersion: phiên bản schema payload.
- source: thành phần phát message, nếu giá trị được tạo bởi hệ thống tin cậy.

Không đưa object request, SecurityContext, Authentication hoặc toàn bộ session vào headers để truyền qua channel. Các object đó thường không có hợp đồng serialization ổn định và có thể mang theo nhiều dữ liệu nhạy cảm hơn mức consumer cần.

### 2.1. Phân biệt message ID, correlation ID và trace ID

Ba định danh này phục vụ ba câu hỏi khác nhau:

| Định danh | Câu hỏi được trả lời | Vòng đời |
|---|---|---|
| Message ID | Đây là message instance nào? | Một message cụ thể |
| Correlation ID | Message này thuộc nghiệp vụ/request nào? | Có thể dùng chung cho nhiều message |
| Trace ID | Các thao tác kỹ thuật nào thuộc cùng một trace? | Một distributed trace |

Spring thường tạo ID và timestamp mặc định cho MessageHeaders. Không dùng message ID đó thay cho correlation ID nghiệp vụ. Nếu một nghiệp vụ phát ra nhiều event hoặc retry tạo message mới, correlation ID có thể được giữ nguyên trong khi message ID thay đổi.

Trace ID cũng không nhất thiết bằng correlation ID. Một nghiệp vụ có thể chạy qua nhiều trace khác nhau do retry, tác vụ nền hoặc một request mới; ngược lại, một trace có thể chứa nhiều message và nhiều operation.

### 2.2. Bổ sung context tại ranh giới gửi

Nếu ứng dụng có một context đã được xác minh ở tầng gọi, có thể bổ sung những trường cần thiết trước khi gửi:

~~~java
Message<?> enriched = MessageBuilder
    .fromMessage(message)
    .setHeaderIfAbsent("correlationId", requestContext.correlationId())
    .setHeader("actorId", authenticatedActor.id())
    .build();

channel.send(enriched);
~~~

Đây là ví dụ minh họa cách tạo message mới. requestContext và authenticatedActor phải đến từ context đáng tin cậy của ứng dụng. Không lấy actorId hoặc tenantId trực tiếp từ một header do client tự gửi rồi coi đó là danh tính đã xác thực.

Nếu dùng ChannelInterceptor để chuẩn hóa metadata, preSend chạy trên đường gửi của channel đã đăng ký interceptor. Interceptor chỉ áp dụng cho channel đó; việc tạo MessageBuilder riêng không tự chạy interceptor. Hãy giữ logic này nhanh và xác định, vì kiểm tra chậm ở preSend sẽ làm chậm thao tác send.

## 3. Truyền ngữ cảnh truy vết

Distributed tracing nối các thao tác ở nhiều thread hoặc service thành một trace. Thông thường, mỗi operation có span riêng; các span liên kết với nhau bằng trace context và quan hệ parent-child hoặc link.

### 3.1. Trace context khác với correlation ID

Trace context chứa dữ liệu phục vụ tracer tạo và nối span. Tùy propagator được cấu hình, nó có thể được biểu diễn qua W3C Trace Context như traceparent/tracestate hoặc một định dạng khác như B3.

Không nên tự tạo traceparent bằng cách ghép chuỗi traceId và spanId. Tracer phải tạo span, quản lý scope, inject context vào carrier gửi đi và extract context khi nhận. Nếu chỉ copy một chuỗi traceId vào custom header, bạn có thể tìm log theo ID nhưng chưa chắc đã tạo được quan hệ span chính xác.

Correlation ID vẫn hữu ích ở tầng nghiệp vụ. Nó có thể được giữ qua retry, event và tác vụ nền kể cả khi trace mới được bắt đầu.

### 3.2. Micrometer Observation và Micrometer Tracing

Micrometer Observation cung cấp abstraction để ghi nhận một operation. Khi có ObservationHandler phù hợp, một Observation có thể tạo metrics và span. Micrometer Tracing cung cấp API tracer, span, baggage và propagation.

Ở ranh giới message, instrumentation sender có thể inject trace context vào headers/carrier trước khi gửi. Consumer extract context từ headers và tạo observation/span tiếp nối. Cơ chế cụ thể phụ thuộc transport hoặc messaging integration đang dùng.

**Spring Messaging core không tự động tạo distributed trace chỉ vì Message có header traceId.** Với mỗi transport hoặc broker, cần instrumentation hoặc adapter hỗ trợ inject/extract trace context và ánh xạ headers phù hợp.

Spring Framework có instrumentation cho JMS thông qua Micrometer khi có dependency `io.micrometer:micrometer-jakarta9` trên classpath. Để bật observation cho gửi JMS, cấu hình ObservationRegistry trên JmsTemplate; để bật observation xử lý, cấu hình registry trên listener container factory. Khi được cấu hình, instrumentation ghi nhận publish/process observation và truyền tracing context qua JMS message headers.

Với Spring Integration, bật observation trên channel và consumer tương ứng để tạo chuỗi span qua flow; đây là khả năng của Spring Integration, không phải tự động của mọi MessageChannel trong Spring Framework core.

### 3.3. Baggage: truyền thêm metadata trong trace

Baggage là metadata gắn với trace context và có thể được truyền qua các service. Ví dụ có thể dùng locale hoặc một mã phân loại cần thiết cho xử lý tiếp theo, nếu chính sách của hệ thống cho phép.

Không nên đưa mọi thông tin nghiệp vụ vào baggage. Chỉ cấu hình các field cần thiết và được phép truyền từ xa. Tránh token, mật khẩu, cookie, dữ liệu cá nhân và thông tin có thể thay đổi quyền truy cập. Baggage cũng có thể xuất hiện trong log hoặc được forward qua nhiều dịch vụ; cần xem nó như metadata có phạm vi chia sẻ rộng.

## 4. Truyền danh tính và SecurityContext

### 4.1. Actor metadata không phải bằng chứng xác thực

Header actorId có thể giúp consumer biết thao tác được khởi tạo bởi ai để ghi audit. Tuy nhiên, một chuỗi như `actorId=user-42` không chứng minh user-42 đã đăng nhập hoặc có quyền thực hiện thao tác.

Tách biệt hai mục đích:

- **Audit context:** ai là actor được hệ thống xác thực đã khởi tạo thao tác; có thể lưu actorId, source hoặc requestId.
- **Authorization context:** principal nào đang được xác thực, có authorities nào và có được phép truy cập resource cụ thể hay không.

Không dùng actorId, role hoặc tenantId do message bên ngoài tự khai báo làm cơ sở cấp quyền. Consumer phải xác minh danh tính và quyền theo security boundary của chính nó.

### 4.2. SecurityContext gắn với thread

Trong Spring Security, SecurityContextHolder thường lưu SecurityContext theo thread. Khi code chạy trên thread mới, context của thread gọi không tự động xuất hiện ở thread mới.

Nếu một tác vụ nền cần chạy với danh tính hiện tại, Spring Security cung cấp các wrapper như:

- DelegatingSecurityContextRunnable
- DelegatingSecurityContextCallable
- DelegatingSecurityContextExecutor
- DelegatingSecurityContextExecutorService
- DelegatingSecurityContextAsyncTaskExecutor

Ví dụ dùng executor wrapper:

~~~java
Executor securityAwareExecutor =
    new DelegatingSecurityContextExecutor(delegateExecutor);

securityAwareExecutor.execute(() -> {
    securedService.performOperation();
});
~~~

Với constructor không truyền SecurityContext cố định, wrapper lấy SecurityContext hiện hành tại thời điểm submit task, cài đặt context đó khi task chạy và dọn context sau khi task hoàn tất. Có thể truyền SecurityContext tường minh nếu tác vụ phải chạy dưới một service identity đã được chỉ định.

Đây là API của **Spring Security**, không phải Spring Framework Messaging. Hãy chọn đúng executor cho các tác vụ cần SecurityContext; không giả định ContextPropagatingTaskDecorator tự động truyền mọi loại SecurityContext nếu chưa có ThreadLocalAccessor tương ứng.

### 4.3. Qua ranh giới service hoặc broker

Không gửi nguyên object SecurityContext hoặc Authentication trong message headers. Object đó gắn với framework và quá trình xác thực nội bộ, không phải hợp đồng truyền tải giữa dịch vụ.

Nếu consumer ở một service khác cần xác thực người gọi, dùng cơ chế xác thực được hệ thống hỗ trợ: credential/token có chữ ký hoặc reference bảo mật được truyền qua kênh được bảo vệ, sau đó consumer xác minh issuer, audience, expiry, scope/authority và các điều kiện liên quan. Nếu message được phát bởi service trung gian, cần xác định rõ danh tính là người dùng ban đầu, service phát message hay cả hai; không nhập nhằng các vai trò này.

Trong hệ thống event bất đồng bộ, nhiều khi consumer chỉ cần actorId đã được xác thực để audit, còn quyền xử lý event được quyết định theo service identity và policy riêng. Điều đó giúp không phụ thuộc vào phiên đăng nhập của người dùng có thể đã kết thúc từ lâu.

## 5. ThreadLocal không tự đi theo task sang thread khác

ThreadLocal chỉ lưu giá trị trong thread hiện tại. Nếu producer gửi message qua executor hoặc gọi một tác vụ bất đồng bộ, worker thread khác sẽ không tự thấy ThreadLocal của producer.

Không nên giải quyết bằng cách dùng InheritableThreadLocal cho thread pool. Thread pool tái sử dụng worker; context cũ có thể bị sót lại giữa các task hoặc không được cập nhật theo lần submit mới.

Spring cung cấp TaskDecorator để bọc Runnable trước khi executor thực thi. Từ Spring Framework 6.1, ContextPropagatingTaskDecorator tích hợp với Micrometer Context Propagation để capture và restore các context đã đăng ký.

Cần có hai thành phần:

1. ThreadLocalAccessor mô tả cách đọc, đặt và xóa một loại ThreadLocal.
2. ContextPropagatingTaskDecorator capture context khi task được submit và khôi phục context khi task chạy.

Ví dụ đăng ký accessor cho một ThreadLocal tự định nghĩa:

~~~java
ContextRegistry.getInstance().registerThreadLocalAccessor(
    new ThreadLocalAccessor<String>() {
        @Override
        public Object key() {
            return "demo.trace-context";
        }

        @Override
        public String getValue() {
            return TRACE_CONTEXT.get();
        }

        @Override
        public void setValue(String value) {
            if (value == null) {
                TRACE_CONTEXT.remove();
            }
            else {
                TRACE_CONTEXT.set(value);
            }
        }

        @Override
        public void setValue() {
            TRACE_CONTEXT.remove();
        }
    }
);
~~~

Sau đó gắn decorator vào executor:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(100);
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
executor.initialize();
~~~

Khi task được submit, các context có accessor đã đăng ký có thể được khôi phục trong worker thread. Scope được đóng sau khi task hoàn tất để trả worker về trạng thái context trước đó, tránh rò rỉ dữ liệu sang task kế tiếp.

Decorator có overhead do capture/restore context. Không nên bật một cách máy móc cho hàng triệu task cực nhỏ mà không đo chi phí. Chỉ đăng ký các accessor cần thiết và đảm bảo mỗi accessor có logic clear/reset chính xác.

### 5.1. ContextPropagatingTaskDecorator không phải cơ chế truyền message

Decorator chỉ truyền context qua ranh giới task/thread trong cùng process. Nó không serialize metadata vào Message, không gửi headers qua broker và không thay thế W3C Trace Context hoặc security token.

Vì vậy, hai cơ chế có thể cùng cần thiết:

- Message headers mang metadata tường minh qua message/channel/transport.
- TaskDecorator khôi phục context thực thi như observation hoặc logging context khi task được chạy trên worker thread.

## 6. Context trong reactive pipeline

Trong Reactor, một pipeline có thể chuyển thread nhiều lần do publishOn, subscribeOn hoặc scheduler. Vì vậy, không nên coi ThreadLocal là nơi lưu context chính của reactive chain.

Reactor Context gắn với subscription, không gắn với thread. Khi code imperative cần đọc context từ Reactor hoặc code reactive cần dùng một ThreadLocal-based library, Micrometer Context Propagation có thể hỗ trợ chuyển đổi giữa các loại context.

Spring MVC cũng có hướng dẫn tích hợp Context Propagation khi controller trả về Flux hoặc Mono: nếu thư viện có trên classpath, các ThreadLocal có ThreadLocalAccessor đã đăng ký có thể được ghi vào Reactor Context. Với các tình huống async khác, có thể dùng ContextSnapshot trực tiếp để capture và restore.

Quy tắc thực tế:

- Code imperative: dùng API context imperative tương ứng, như ThreadLocal hoặc SecurityContextHolder.
- Code reactive: dùng Reactor Context cho dữ liệu theo subscription.
- Khi đi qua ranh giới imperative/reactive hoặc executor: dùng Context Propagation với accessor phù hợp.
- Không dựa vào việc hai đoạn code tình cờ chạy trên cùng một thread.

## 7. Đưa context vào message flow và bảo toàn hợp đồng dữ liệu

Một message có thể đi qua nhiều channel, interceptor, handler và adapter. Mỗi bước cần quyết định metadata nào được giữ lại, bổ sung, thay đổi hoặc loại bỏ.

Một quy trình mẫu:

1. Tại ranh giới nhận request, xác thực caller và tạo correlation/trace context.
2. Tạo payload nghiệp vụ; thêm các header được phép như correlationId, actorId và schemaVersion.
3. Trước khi dispatch qua executor, cấu hình context propagation cho những ThreadLocal cần thiết.
4. Consumer đọc payload và metadata; kiểm tra tenant/actor nếu chúng ảnh hưởng tới quyền hoặc phạm vi dữ liệu.
5. Khi gửi sang broker hoặc service khác, inject trace context theo propagator và chỉ forward allowlist header.
6. Consumer ở đầu kia extract trace context, xác thực credential nếu cần và tạo context mới cho lần xử lý của nó.

Không mặc định mọi header đều được bảo toàn qua mọi adapter. Header mapper, message converter hoặc protocol có thể chỉ hỗ trợ một số kiểu dữ liệu. Kiểm tra mapping ở cả chiều outbound và inbound, đặc biệt với JMS properties, HTTP headers hoặc native headers của broker.

Với metadata không được phép truyền tiếp, loại bỏ trước khi message rời khỏi ranh giới tin cậy. Với message được tạo mới, dùng MessageBuilder để copy có chọn lọc thay vì sao chép toàn bộ headers một cách mù quáng.

## 8. Ví dụ Java 17+ chạy độc lập

Ví dụ dưới đây kết hợp hai đường truyền context:

- Message headers mang traceId, correlationId và actorId cùng payload.
- Micrometer Context Propagation khôi phục một ThreadLocal trace context trong worker thread của ExecutorSubscribableChannel.

actorId trong ví dụ là metadata audit do server đặt sau khi xác thực. Nó không thay thế SecurityContext hoặc quyết định quyền truy cập.

**Cấu trúc dự án**

~~~text
context-propagation-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          ContextPropagationDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-propagation-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
            <version>1.1.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/ContextPropagationDemo.java**

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ThreadLocalAccessor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ContextPropagationDemo {

    private static final String TRACE_KEY = "demo.trace-context";
    private static final ThreadLocal<String> TRACE_CONTEXT = new ThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        ContextRegistry.getInstance().registerThreadLocalAccessor(
            new ThreadLocalAccessor<String>() {
                @Override
                public Object key() {
                    return TRACE_KEY;
                }

                @Override
                public String getValue() {
                    return TRACE_CONTEXT.get();
                }

                @Override
                public void setValue(String value) {
                    if (value == null) {
                        TRACE_CONTEXT.remove();
                    }
                    else {
                        TRACE_CONTEXT.set(value);
                    }
                }

                @Override
                public void setValue() {
                    TRACE_CONTEXT.remove();
                }
            }
        );

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("message-worker-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();

        try {
            ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel(executor);

            CountDownLatch handled = new CountDownLatch(1);
            AtomicReference<String> payload = new AtomicReference<>();
            AtomicReference<String> messageTrace = new AtomicReference<>();
            AtomicReference<String> correlation = new AtomicReference<>();
            AtomicReference<String> actor = new AtomicReference<>();
            AtomicReference<String> threadTrace = new AtomicReference<>();

            channel.subscribe(message -> {
                payload.set(message.getPayload().toString());
                messageTrace.set(
                    (String) message.getHeaders().get("traceId")
                );
                correlation.set(
                    (String) message.getHeaders().get("correlationId")
                );
                actor.set(
                    (String) message.getHeaders().get("actorId")
                );
                threadTrace.set(TRACE_CONTEXT.get());
                handled.countDown();
            });

            TRACE_CONTEXT.set("trace-113");

            Message<String> message = MessageBuilder
                .withPayload("order-created")
                .setHeader("traceId", "trace-113")
                .setHeader("correlationId", "order-113")
                .setHeader("actorId", "user-42")
                .build();

            boolean accepted = channel.send(message);

            if (!handled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Message was not handled in time"
                );
            }

            System.out.println("payload=" + payload.get());
            System.out.println("messageTraceId=" + messageTrace.get());
            System.out.println("correlationId=" + correlation.get());
            System.out.println("actorId=" + actor.get());
            System.out.println("workerThreadTraceContext=" + threadTrace.get());
            System.out.println("sendAccepted=" + accepted);
        }
        finally {
            TRACE_CONTEXT.remove();
            executor.shutdown();
        }
    }
}
~~~

Chạy từ thư mục context-propagation-demo:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextPropagationDemo
~~~

**stdout**

~~~text
payload=order-created
messageTraceId=trace-113
correlationId=order-113
actorId=user-42
workerThreadTraceContext=trace-113
sendAccepted=true
~~~

Trong ví dụ, message headers vẫn có mặt khi consumer xử lý; ThreadLocal trace context cũng được khôi phục trong worker thread nhờ ContextPropagatingTaskDecorator. Hai kết quả này minh họa hai phạm vi khác nhau: dữ liệu gắn với message và context gắn với lần thực thi task.

trace-113 ở ví dụ chỉ là giá trị minh họa trong custom ThreadLocal/header. Một ứng dụng distributed tracing thật cần tracer tạo span và propagator inject/extract trace context theo định dạng đã cấu hình; không dùng đoạn demo này để tự tạo W3C traceparent.

## 9. Lỗi thường gặp

1. **Đồng nhất traceId với correlationId:** traceId phục vụ tracing; correlationId phục vụ liên kết nghiệp vụ. Chúng có thể khác nhau.
2. **Cho rằng MessageHeaders tự truyền mọi context:** message chỉ mang các header được tạo; adapter hoặc transport có thể lọc hoặc chuyển đổi chúng.
3. **Cho rằng ThreadLocal tự đi theo executor:** worker thread khác không tự nhận ThreadLocal của sender. Dùng TaskDecorator hoặc cơ chế propagation phù hợp.
4. **Dùng InheritableThreadLocal với thread pool:** worker tái sử dụng có thể giữ context cũ hoặc không nhận context mới như mong muốn.
5. **Truyền SecurityContext như custom header:** không serialize Authentication hoặc SecurityContext vào message. Dùng Spring Security concurrency wrappers trong cùng process và cơ chế xác thực phù hợp qua service boundary.
6. **Tin actorId hoặc tenantId từ message ngoài:** các giá trị này có thể bị giả mạo. Xác thực nguồn và quyền trước khi sử dụng.
7. **Dùng baggage để chứa dữ liệu tùy ý:** baggage có thể được truyền xa và xuất hiện trong trace/log. Chỉ allowlist trường nhỏ, cần thiết và không nhạy cảm.
8. **Không dọn context sau khi task kết thúc:** ThreadLocal/MDC còn sót có thể làm log của task kế tiếp mang nhầm user hoặc trace.
9. **Cho rằng ContextPropagatingTaskDecorator tự xử lý mọi context:** chỉ các giá trị có accessor được đăng ký mới được capture/restore; SecurityContext cần tích hợp Spring Security tương ứng.
10. **Log toàn bộ headers:** có thể làm lộ token, cookie, dữ liệu cá nhân hoặc metadata định tuyến. Chỉ log các trường đã được phê duyệt.
11. **Dùng context để thay thế payload:** metadata mô tả nguồn gốc và cách xử lý; dữ liệu nghiệp vụ vẫn phải nằm trong payload.
12. **Cho rằng send thành công đồng nghĩa consumer đã xử lý xong:** sendAccepted chỉ phản ánh channel chấp nhận gửi theo cơ chế của nó; không thay thế acknowledgment hoặc kết quả transaction.

## 10. Checklist thiết kế context propagation

Trước khi triển khai một message flow, hãy trả lời:

1. Context nào cần đi cùng payload qua queue/broker và context nào chỉ cần trong thread hiện tại?
2. Trace được tạo và inject/extract bởi tracer/propagator nào?
3. Correlation ID nghiệp vụ có được giữ qua retry và message mới không?
4. Actor ID có được lấy từ principal đã xác thực và chỉ dùng cho audit không?
5. SecurityContext có cần chạy tiếp trong async task không; nếu có, executor đã được bọc bằng Spring Security chưa?
6. Các ThreadLocal cần thiết đã có ThreadLocalAccessor và executor decorator chưa?
7. Nếu dùng Reactor, context có được lưu trong Reactor Context và bridge đúng khi qua imperative code không?
8. Header nào được allowlist qua từng transport; header nào phải bị loại bỏ?
9. Tenant, destination và routing metadata đã được xác minh trước khi sử dụng chưa?
10. Context được restore/clear sau khi xử lý để tránh rò rỉ sang task tiếp theo chưa?
11. Log và metrics có tránh token, dữ liệu cá nhân và tag cardinality cao không?
12. Có integration test chứng minh trace/correlation/actor context đi đúng qua channel, executor và transport không?

## 11. Kết luận

Truyền context trong Spring Messaging cần kết hợp nhiều cơ chế theo đúng ranh giới. Message headers mang metadata tường minh qua message flow; Micrometer Context Propagation và TaskDecorator khôi phục context khi task chuyển thread; Reactor Context quản lý dữ liệu theo subscription; Spring Security cung cấp wrapper riêng để truyền SecurityContext trong các tác vụ đồng bộ/bất đồng bộ.

Trace context, correlation ID, actor metadata và quyền truy cập là những khái niệm riêng. Hãy dùng tracer/propagator cho distributed tracing, dùng correlation ID cho liên kết nghiệp vụ, dùng actorId đã xác thực cho audit và dùng SecurityContext hoặc credential đã xác minh cho authorization. Chỉ truyền các header cần thiết, kiểm tra chúng ở ranh giới tin cậy và luôn dọn context sau khi xử lý.

## 12. Tài liệu tham khảo

- [Spring Framework 6.2 — Observability Support](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [ContextPropagatingTaskDecorator — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html)
- [Micrometer Context Propagation — Usage Examples](https://docs.micrometer.io/context-propagation/reference/usage.html)
- [Micrometer Tracing — Baggage and Propagation API](https://docs.micrometer.io/tracing/reference/api.html)
- [Micrometer — Instrumentation and Context Propagation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)