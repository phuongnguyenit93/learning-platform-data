# Lỗi đồng bộ và bất đồng bộ

Trong Spring Integration, cách một lỗi đến được nơi xử lý phụ thuộc vào **ranh giới thực thi của luồng thông điệp**. Cùng một transformer ném `NumberFormatException`, người gửi có thể nhận exception ngay trong lời gọi `send()`, hoặc chỉ biết lỗi qua một `ErrorMessage` được gửi đến kênh khác. Muốn thiết kế đúng, cần xác định ai đang chạy handler, ai còn chờ kết quả và thành phần nào chịu trách nhiệm chuyển exception thành thông điệp.

Bài học thuộc chương **Error handling** của module **SPRING_INTEGRATION_CORE**, nối kiến thức về `Message`, `MessageChannel`, endpoint, gateway và Java DSL với việc quan sát, xử lý và kiểm thử lỗi.

Sau bài này, bạn có thể:

- Phân biệt lỗi truyền theo call stack với lỗi được biểu diễn thành thông điệp.
- Xác định tác động của `DirectChannel`, `ExecutorChannel` và `QueueChannel` lên đường đi của lỗi.
- Đọc `ErrorMessage`, tìm thông điệp thất bại và giữ thông tin tương quan nghiệp vụ.
- Viết kiểm thử chứng minh lỗi đã đi đúng đường, thay vì chỉ kiểm tra rằng `send()` trả về.

## 1. Đồng bộ và bất đồng bộ phải được xét từ một điểm gọi

Giả sử ứng dụng nhận chuỗi số lượng hàng, đổi chuỗi thành số nguyên rồi cập nhật đơn hàng. Có ba cách tổ chức:

~~~text
A. caller -> DirectChannel -> transformer -> handler
   Một thread chạy toàn bộ đoạn này.

B. caller -> ExecutorChannel | worker -> transformer -> handler
   Dấu | là điểm giao công việc cho executor.

C. caller -> QueueChannel | poller -> transformer -> handler
   Người gửi đưa message vào queue; poller nhận message để xử lý.
~~~

Trong A, nếu handler thất bại mà không có thành phần nào bắt lỗi, exception có thể quay về caller theo call stack. Trong B và C, exception của phần xử lý trên thread khác không thể tự nhảy vào một khối `try/catch` đã kết thúc ở thread người gửi.

Tuy nhiên, một handler nằm sau `DirectChannel` vẫn có thể đang chạy trên worker. Ví dụ:

~~~text
HTTP thread -> ExecutorChannel | worker -> DirectChannel -> transformer
~~~

Transformer chạy đồng bộ với worker gọi nó, nhưng bất đồng bộ so với HTTP thread ban đầu. Vì vậy, khi phân tích lỗi, hãy vẽ toàn bộ đường đi từ điểm vào đến nơi thất bại, rồi đánh dấu các chỗ chuyển thread.

### 1.1. Channel ảnh hưởng đến thực thi như thế nào?

| Thành phần | Cách thực thi thông thường | Ý nghĩa với người gửi ban đầu |
| --- | --- | --- |
| `DirectChannel` | Gọi subscriber ngay trên thread gửi | Handler có thể ném lỗi trở lại lời gọi `send()` |
| `ExecutorChannel` dùng thread pool | Giao dispatch cho executor | Lỗi handler cần một đường báo lỗi riêng |
| `QueueChannel` cùng polling endpoint | Lưu message rồi được poller lấy ra | Lỗi xử lý thuộc lần thực thi của poller |
| `PublishSubscribeChannel` không cấu hình executor | Gọi subscriber trên thread gửi | Bản thân publish-subscribe không bảo đảm bất đồng bộ |

`QueueChannel` không tự tạo worker. Một `PollingConsumer`, hoặc code chủ động gọi `receive()`, mới thực hiện việc lấy message. Nếu bạn tự nhận và xử lý message trên cùng thread, cần phân tích call stack của chính đoạn code đó. Các channel dùng queue mặc định lưu trong bộ nhớ; buffering không đồng nghĩa với lưu bền vững. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

`ExecutorChannel` cũng phụ thuộc executor thực tế. Executor chạy inline hoặc chính sách `CallerRunsPolicy` có thể làm công việc chạy trên thread gửi trong một số tình huống. Không dùng khả năng này làm cam kết về thread hoặc transaction; xem [ExecutorChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

## 2. Lỗi đồng bộ: exception đi theo call stack

Với một đoạn xử lý hoàn toàn trực tiếp:

~~~java
try {
    inputChannel.send(message);
} catch (MessagingException exception) {
    // Có thể đọc failedMessage và chuỗi nguyên nhân tại đây.
}
~~~

Khi một transformer hoặc service activator ném lỗi nghiệp vụ, framework thường bọc lỗi bằng một exception của tầng messaging. Với transformer, có thể gặp `MessageTransformationException`; với handler khác, có thể gặp `MessageHandlingException`. Cả hai thuộc họ `MessagingException`.

Vì vậy, bắt trực tiếp `NumberFormatException` quanh `MessageChannel.send()` có thể bỏ sót lỗi đã được bọc. Cần phân biệt:

- **Exception bên ngoài:** cho biết lỗi được phát hiện ở tầng messaging nào.
- **Cause bên trong:** giải thích nguyên nhân, chẳng hạn dữ liệu không chuyển thành số được.
- **`failedMessage`:** thông điệp đang được xử lý tại vị trí lỗi, nếu exception cung cấp được thông tin đó.

Không nên viết logic vận hành phụ thuộc cứng vào đúng một lớp wrapper hoặc đúng số tầng `getCause()`. Chuỗi bọc có thể khác khi thêm transformer, advice hoặc một endpoint trung gian.

### 2.1. Header `errorChannel` không tự bắt mọi lỗi đồng bộ

Gắn header như sau chưa tạo ra cơ chế bắt exception quanh toàn bộ flow:

~~~java
Message<String> request = MessageBuilder.withPayload("khong-phai-so")
        .setHeader(MessageHeaders.ERROR_CHANNEL, errors)
        .build();

directInput.send(request);
~~~

Nếu caller gửi trực tiếp vào `DirectChannel` và transformer thất bại ngay trên call stack đó, exception vẫn truyền về caller. Header chỉ xác định nơi nhận lỗi khi có thành phần thực sự bắt exception và công bố `ErrorMessage`, chẳng hạn bộ xử lý lỗi của executor, poller hoặc gateway được cấu hình phù hợp. Đây là điểm cần phân biệt giữa **địa chỉ nhận lỗi** và **cơ chế bắt lỗi**.

## 3. Lỗi bất đồng bộ: exception trở thành dữ liệu trên một đường khác

Khi task của Spring Integration chạy qua cơ chế xử lý lỗi bất đồng bộ, exception có thể được đóng trong `ErrorMessage`. Với cơ chế mặc định, header `errorChannel` của request được ưu tiên; nếu không có, lỗi đi tới kênh toàn cục mang tên `errorChannel`. Poller cũng có cơ chế công bố lỗi. Kênh toàn cục mặc định là `PublishSubscribeChannel` với subscriber ghi log ở mức ERROR. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant I as ExecutorChannel
    participant W as Worker
    participant E as Error channel
    participant H as Error consumer
    C->>I: send(request)
    I->>W: Giao task
    I-->>C: Kết quả gửi hoặc lỗi giao task
    W->>W: Thực thi transformer/handler
    W->>E: Công bố ErrorMessage khi xử lý thất bại
    E->>H: Chuyển thông điệp lỗi
~~~

Sơ đồ mô tả vai trò của các bên; không cam kết worker chỉ bắt đầu sau khi `send()` đã trả về. Worker có thể chạy rất nhanh và hoàn thành trước thời điểm đó. Điều bất biến là exception trên worker không được truyền trực tiếp bằng call stack của thread người gửi.

### 3.1. Phân biệt lỗi giao công việc và lỗi xử lý công việc

Một flow bất đồng bộ vẫn có thể làm `send()` thất bại ngay:

| Giai đoạn | Ví dụ lỗi | Nơi cần quan sát |
| --- | --- | --- |
| Trước hoặc trong lúc giao task | Interceptor từ chối, executor từ chối task, channel không nhận được message | Kết quả hoặc exception tại điểm gửi |
| Đưa message vào queue | Queue đầy và hết thời gian gửi | Kết quả `send(message, timeout)` và chính sách xử lý tại caller |
| Chạy handler trên worker/poller | Parse dữ liệu lỗi, service ném exception | Đường xử lý lỗi của task, thường là error flow |
| Công bố hoặc tiêu thụ lỗi | Error channel không nhận được message, error handler lại thất bại | Log, metric và cơ chế dự phòng của đường lỗi |

Do đó, `try/catch` quanh thao tác gửi vẫn hữu ích trong flow bất đồng bộ. Nó bảo vệ bước giao công việc; để biết kết quả xử lý nghiệp vụ, phải có reply, kết quả tác vụ hoặc kênh báo lỗi tương ứng.

### 3.2. `send() == true` có ý nghĩa gì?

Trong flow dùng queue hoặc executor, giá trị này thường cho biết message đã được channel chấp nhận theo cơ chế gửi của nó. Nó không chứng minh rằng:

- Dữ liệu đã được kiểm tra hợp lệ.
- Đơn hàng đã cập nhật thành công.
- Transaction của worker đã commit.
- Message có thể được khôi phục sau khi tiến trình dừng.

Ngay cả một flow đồng bộ cũng có thể có filter loại message hoặc handler thực hiện một hành động không tạo reply. Kết quả gửi thuộc hợp đồng của channel; kết quả nghiệp vụ thuộc hợp đồng của ứng dụng.

### 3.3. Error flow có thể chạy đồng bộ trên worker

Tên gọi “lỗi bất đồng bộ” mô tả mối quan hệ với caller ban đầu. Nếu worker gửi `ErrorMessage` vào một `DirectChannel`, error handler có thể chạy ngay trên worker đó. Nếu error channel là `QueueChannel`, consumer khác sẽ xử lý khi nhận được message.

Vì thế, một error handler ghi log chậm hoặc gọi dịch vụ cảnh báo chậm có thể chiếm thời gian của worker. Cần chọn channel và giới hạn tài nguyên cho đường lỗi theo tải thực tế.

Việc tự gọi `executor.execute(...)`, tự tạo thread hoặc tự khởi chạy một `CompletableFuture` trong service không mặc nhiên được kết nối với error flow của Spring Integration. Khi công việc tách khỏi lời gọi mà framework đang quản lý, ứng dụng phải thiết kế cách chuyển kết quả hoặc exception về một cơ chế được quan sát.

## 4. Đọc `ErrorMessage` và tìm lại ngữ cảnh thất bại

`ErrorMessage` là một `Message<Throwable>`. Payload thường là `MessagingException`, nhưng không nên ép kiểu vô điều kiện. Nó có thể mang một `Throwable` khác. Hai vị trí thông tin cần phân biệt là:

| Thông tin | Cách truy cập | Ý nghĩa |
| --- | --- | --- |
| Exception được công bố | `errorMessage.getPayload()` | Điểm bắt đầu để xem wrapper và cause |
| Message tại điểm thất bại | `messagingException.getFailedMessage()` | Payload và header mà endpoint đang xử lý |
| Message gốc, nếu được cung cấp | `errorMessage.getOriginalMessage()` | Message tại ngữ cảnh tạo error message; có thể `null` |

`failedMessage` có thể đã trải qua biến đổi nên khác với message đầu vào ban đầu. `originalMessage` là thông tin tùy chọn và cũng không phải cam kết rằng đó luôn là request đầu tiên của toàn hệ thống. Xem [ErrorMessage API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html).

Ví dụ một hàm đọc mã tương quan từ message thất bại:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

static Object findBusinessRequestId(ErrorMessage errorMessage) {
    Throwable current = errorMessage.getPayload();
    while (current != null) {
        if (current instanceof MessagingException messagingException) {
            Message<?> failed = messagingException.getFailedMessage();
            if (failed != null) {
                Object requestId = failed.getHeaders().get("businessRequestId");
                if (requestId != null) {
                    return requestId;
                }
            }
        }
        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    Message<?> original = errorMessage.getOriginalMessage();
    return original == null
            ? null
            : original.getHeaders().get("businessRequestId");
}
~~~

Hàm này dùng cú pháp Java 17 và dành cho cause chain thông thường của exception trong ứng dụng. Cần chấp nhận kết quả `null`, vì có lỗi xảy ra khi chưa có message hoặc ngữ cảnh không được giữ lại.

Không mặc định rằng mọi header nghiệp vụ đã được sao chép sang header của `ErrorMessage`. Đặt mã tương quan ngay ở biên nhận request, bảo toàn nó khi biến đổi message và lấy từ message thất bại khi ghi nhận lỗi. Với thông điệp đi qua broker hoặc kho lưu trữ, không dựa vào việc serialize một đối tượng channel nằm trong header; cần chiến lược ánh xạ header và địa chỉ lỗi phù hợp với biên hệ thống.

## 5. Thực hành Java DSL: cùng một lỗi qua ba kiểu channel

Ví dụ sau chuyển chuỗi thành số nguyên. Dữ liệu `"42"` tạo kết quả `42`; `"abc"` làm transformer thất bại.

Ứng dụng cần `spring-integration-core`; phần test cần `spring-test`, JUnit Jupiter và engine tương ứng. Dùng các phiên bản Spring đồng bộ theo dependency management của dự án. Ví dụ không cần Spring Boot, broker hay cơ sở dữ liệu; cú pháp Java dùng Java 17 trở lên và cần JDK phù hợp với phiên bản Spring đã chọn.

Đặt cấu hình và lớp test ở cùng package, hoặc thêm import cho lớp cấu hình. Tên các lớp ở đây phục vụ bài thực hành, không yêu cầu thay đổi cấu trúc module hiện có.

### 5.1. Cấu hình ba luồng

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
public class ErrorBoundaryConfig {

    @Bean
    public DirectChannel syncInput() {
        return new DirectChannel();
    }

    @Bean
    public ThreadPoolTaskExecutor workerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("integration-worker-");
        return executor;
    }

    @Bean
    public ExecutorChannel asyncInput(
            @Qualifier("workerExecutor") ThreadPoolTaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    public QueueChannel queuedInput() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel parsedResults() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel asyncErrors() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel pollerErrors() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow syncParseFlow(
            @Qualifier("syncInput") MessageChannel input,
            @Qualifier("parsedResults") QueueChannel results) {
        return IntegrationFlow.from(input)
                .<String, Integer>transform(Integer::valueOf)
                .channel(results)
                .get();
    }

    @Bean
    public IntegrationFlow asyncParseFlow(
            @Qualifier("asyncInput") MessageChannel input,
            @Qualifier("parsedResults") QueueChannel results) {
        return IntegrationFlow.from(input)
                .<String, Integer>transform(Integer::valueOf)
                .channel(results)
                .get();
    }

    @Bean
    public IntegrationFlow queuedParseFlow(
            @Qualifier("queuedInput") QueueChannel input,
            @Qualifier("parsedResults") QueueChannel results) {
        return IntegrationFlow.from(input)
                .<String, Integer>transform(Integer::valueOf,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofMillis(50))
                                        .maxMessagesPerPoll(1)
                                        .errorChannel("pollerErrors")))
                .channel(results)
                .get();
    }
}
~~~

Spring quản lý việc khởi tạo và đóng `ThreadPoolTaskExecutor` vì nó là bean. Cả ba flow dùng chung phép biến đổi để chỉ làm thay đổi ranh giới thực thi.

Trong cấu hình này:

- `syncInput` gọi transformer ngay trên thread gửi.
- `asyncInput` giao việc cho worker; test sẽ gắn header chỉ đến `asyncErrors`.
- `queuedInput` được một polling endpoint nhận message; poller được cấu hình kênh lỗi mặc định riêng là `pollerErrors`.
- `parsedResults` giữ kết quả để test quan sát được việc xử lý đã hoàn tất.

Các error channel và result channel dùng queue có giới hạn để bài thực hành dễ quan sát bằng `receive(timeout)`. Chúng không có consumer nghiệp vụ chạy ngầm. Trong ứng dụng thực, phải có consumer, chính sách khi queue đầy và cơ chế lưu trữ phù hợp; nếu chỉ gửi vào mà không đọc, các queue sẽ đầy.

Poller thuộc endpoint tiêu thụ `queuedInput`, không thuộc bản thân `QueueChannel`. `errorChannel(...)` là tùy chọn của poller; xem [PollerSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/PollerSpec.html). Phân biệt polling endpoint với nguồn thông điệp có poller tại [Poller](https://docs.spring.io/spring-integration/reference/polling-consumer.html).

### 5.2. Kiểm thử đường truyền lỗi

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(ErrorBoundaryConfig.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ErrorBoundaryTest {

    @Autowired
    @Qualifier("syncInput")
    MessageChannel syncInput;

    @Autowired
    @Qualifier("asyncInput")
    MessageChannel asyncInput;

    @Autowired
    @Qualifier("queuedInput")
    QueueChannel queuedInput;

    @Autowired
    @Qualifier("parsedResults")
    QueueChannel parsedResults;

    @Autowired
    @Qualifier("asyncErrors")
    QueueChannel asyncErrors;

    @Autowired
    @Qualifier("pollerErrors")
    QueueChannel pollerErrors;

    @Test
    void directFailureReturnsToSenderEvenWithErrorHeader() {
        Message<String> request = badRequest("SYNC-001", asyncErrors);

        MessagingException exception = assertThrows(
                MessagingException.class,
                () -> syncInput.send(request, 1_000));

        assertInstanceOf(NumberFormatException.class, rootCause(exception));
        Message<?> failed = exception.getFailedMessage();
        assertNotNull(failed);
        assertEquals("SYNC-001", failed.getHeaders().get("businessRequestId"));
        assertNull(asyncErrors.receive(0));
        assertNull(parsedResults.receive(0));
    }

    @Test
    void executorFailureArrivesAtRequestErrorChannel() {
        Message<String> request = badRequest("ASYNC-001", asyncErrors);

        assertTrue(asyncInput.send(request, 1_000));

        ErrorMessage error = receiveError(asyncErrors);
        assertFailure(error, "ASYNC-001");
        assertNull(parsedResults.receive(0));
    }

    @Test
    void executorSuccessIsObservedThroughResultMessage() {
        Message<String> request = MessageBuilder.withPayload("42")
                .setHeader("businessRequestId", "ASYNC-OK-001")
                .setHeader(MessageHeaders.ERROR_CHANNEL, asyncErrors)
                .build();

        assertTrue(asyncInput.send(request, 1_000));

        Message<?> result = parsedResults.receive(3_000);
        assertNotNull(result);
        assertEquals(42, result.getPayload());
        assertEquals("ASYNC-OK-001",
                result.getHeaders().get("businessRequestId"));
        assertNull(asyncErrors.receive(0));
    }

    @Test
    void pollingFailureArrivesAtConfiguredPollerChannel() {
        Message<String> request = MessageBuilder.withPayload("abc")
                .setHeader("businessRequestId", "POLL-001")
                .build();

        assertTrue(queuedInput.send(request, 1_000));

        ErrorMessage error = receiveError(pollerErrors);
        assertFailure(error, "POLL-001");
        assertNull(parsedResults.receive(0));
    }

    private static Message<String> badRequest(
            String requestId, MessageChannel errors) {
        return MessageBuilder.withPayload("abc")
                .setHeader("businessRequestId", requestId)
                .setHeader(MessageHeaders.ERROR_CHANNEL, errors)
                .build();
    }

    private static ErrorMessage receiveError(QueueChannel errors) {
        Message<?> message = errors.receive(3_000);
        assertNotNull(message, "Không nhận được error message trong thời hạn");
        return assertInstanceOf(ErrorMessage.class, message);
    }

    private static void assertFailure(ErrorMessage error, String requestId) {
        assertInstanceOf(NumberFormatException.class,
                rootCause(error.getPayload()));
        MessagingException exception = assertInstanceOf(
                MessagingException.class, error.getPayload());
        Message<?> failed = exception.getFailedMessage();
        assertNotNull(failed);
        assertEquals("abc", failed.getPayload());
        assertEquals(requestId, failed.getHeaders().get("businessRequestId"));
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

Các assertion trên wrapper và `failedMessage` phù hợp với transformer cụ thể trong bài. Hàm đọc lỗi dùng chung cho nhiều loại endpoint nên linh hoạt hơn, như ví dụ ở mục 4.

`@DirtiesContext` tạo lại context sau từng test để queue, scheduler và executor không mang trạng thái sang test tiếp theo. Đây là lựa chọn đơn giản cho bài thực hành; bộ test lớn có thể dùng cách cô lập khác để giảm thời gian khởi tạo. Những test dùng chung queue này không được chạy song song trên cùng một context.

Không dùng `Thread.sleep()` để đoán khi nào worker đã xong. `receive(3_000)` vừa chờ có giới hạn vừa chờ đúng sự kiện mà test cần quan sát. Timeout trong test là ngưỡng phát hiện thất bại, không phải SLA của ứng dụng. Trong thực tế, chọn ngưỡng phù hợp với môi trường CI.

Test thành công nhận một result message, chứ không kết luận thành công chỉ từ việc chưa thấy lỗi. Các kiểm tra `receive(0)` chỉ kiểm tra trạng thái hiện tại sau sự kiện đã quan sát; chúng không chứng minh sẽ không bao giờ có lỗi trong tương lai. Cấu hình ở đây không có retry hoặc công việc nền phát sinh tiếp sau kết quả.

Ví dụ chỉ cần Spring Test vì đang dùng các channel thật. Khi cần thay handler hoặc ngăn inbound adapter kết nối ra ngoài, có thể dùng `spring-integration-test` với `MockIntegrationContext`; xem [Testing support](https://docs.spring.io/spring-integration/reference/testing.html).

## 6. Poller có thêm một biên lỗi cần hiểu rõ

Một poller có thể thất bại ở hai vị trí khác nhau:

1. **Khi lấy dữ liệu:** nguồn dữ liệu ném exception trước khi tạo được message. Lúc này có thể chưa có `failedMessage` và không có header từ request để chọn kênh lỗi.
2. **Khi xử lý message đã nhận:** transformer, router hoặc service activator ở phía sau ném exception. Lúc này framework thường có thể đính kèm message thất bại.

Trong ví dụ, lỗi xảy ra ở vị trí thứ hai. Request không có header `errorChannel`, nên đường lỗi mặc định được cấu hình trên poller là `pollerErrors`.

Với `MessagePublishingErrorHandler` tiêu chuẩn, header `errorChannel` lấy được từ message thất bại có thể ưu tiên hơn kênh mặc định của error handler. Đừng suy diễn rằng khai báo kênh trên poller luôn ghi đè mọi header. Nếu ứng dụng cấu hình `ErrorHandler` tùy chỉnh, cần xét chính hợp đồng của handler đó. API cho phép đặt kênh mặc định qua `setDefaultErrorChannel` hoặc `setDefaultErrorChannelName`; xem [MessagePublishingErrorHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html).

Điều này cũng giải thích vì sao nên có kênh mặc định cho lỗi của nguồn polling: không thể yêu cầu một message chưa được tạo ra phải mang sẵn địa chỉ nhận lỗi.

## 7. Gateway làm hợp đồng quan sát lỗi khác với lời gọi `send()`

Một messaging gateway có thể giữ caller chờ reply, dù bên trong flow có `ExecutorChannel` hoặc polling endpoint. Khi đường reply/error còn được bảo toàn, framework có thể chuyển lỗi từ nhánh bất đồng bộ về gateway đang chờ rồi ném ra cho caller. Đây là trao đổi thông điệp lỗi qua hạ tầng gateway, không phải exception nhảy giữa hai call stack.

Gateway mặc định có thể gỡ wrapper trước khi ném lỗi; khi cấu hình `errorChannel`, nó còn có thể đưa lỗi qua một flow chuyển thành phản hồi phù hợp với kiểu trả về. Vì vậy, cùng một lỗi nghiệp vụ, caller của gateway và caller gửi trực tiếp vào channel có thể nhận lớp exception khác nhau. Xem [Messaging Gateways — Error Handling](https://docs.spring.io/spring-integration/reference/gateway.html#error-handling).

### 7.1. Xác định rõ hợp đồng tại biên ứng dụng

| Cách gọi | Caller thực sự cần biết | Thiết kế đường lỗi |
| --- | --- | --- |
| Gửi một chiều vào channel bất đồng bộ | Việc tiếp nhận đã thành công hay chưa | Kiểm tra bước gửi; ghi nhận kết quả xử lý qua error flow hoặc trạng thái tác vụ |
| Gateway request-reply trả DTO | Thành công hoặc lỗi theo hợp đồng trả về | Duy trì reply/error path; ánh xạ lỗi sang DTO nếu hợp đồng yêu cầu |
| Gateway trả kiểu bất đồng bộ | Kết quả sẽ hoàn tất sau lời gọi | Quan sát completion và exceptional completion theo kiểu trả về và cấu hình gateway |

Một gateway trả `void` không phải lời bảo đảm rằng công việc chạy bất đồng bộ. Ngược lại, gateway trả DTO vẫn có thể chờ một flow xử lý trên worker. Cần tách **kiểu trả về của API**, **cách bố trí thread** và **cơ chế báo lỗi** khi đọc cấu hình.

### 7.2. Error handler chỉ ghi log có thể không tạo được reply

Giả sử caller chờ `OrderResult`, nhưng error flow chỉ ghi log rồi kết thúc. Khi đó phải xác định caller sẽ nhận gì khi không có reply: hết thời gian chờ, giá trị rỗng hoặc exception theo cấu hình. Một bản ghi log không tự trở thành phản hồi nghiệp vụ.

Nếu chọn ánh xạ lỗi thành kết quả, nên có một DTO rõ ràng, chẳng hạn:

~~~java
public record OrderResult(
        String orderId,
        boolean successful,
        String errorCode) {
}
~~~

Ví dụ với dữ liệu số lượng không hợp lệ, error flow trả `successful=false` và mã `INVALID_QUANTITY`. Không trả một số mặc định hợp lệ như `0` rồi để caller hiểu nhầm xử lý đã thành công. Ngữ cảnh `orderId` cần được lấy từ message thất bại hoặc dữ liệu tương quan đã bảo toàn.

### 7.3. Timeout không hủy công việc đang chạy

Với flow hoàn toàn đồng bộ trên thread caller, `replyTimeout` không ngắt được một service đang chạy lâu trong chính call stack đó. Khi flow đã giao sang thread khác và gateway chờ reply, timeout giới hạn thời gian chờ; worker vẫn có thể hoàn tất sau đó. Vì vậy cần có deadline cho thao tác I/O và cơ chế theo dõi kết quả đến muộn nếu nghiệp vụ yêu cầu. Các tình huống này được mô tả tại [Gateway Behavior When No response Arrives](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

Đối với đặt hàng hoặc thanh toán, caller hết thời gian chờ không đủ để kết luận thao tác chưa diễn ra. Một lần gọi lại cần gắn với khóa nghiệp vụ và chiến lược chống xử lý trùng.

## 8. Ranh giới thread cũng ảnh hưởng transaction và retry

### 8.1. Transaction không tự đi theo message sang worker

Một transaction gắn với thread caller có thể bao phủ chuỗi xử lý trực tiếp nếu các thao tác tham gia đúng transaction đó. Khi công việc được giao sang worker, không được mặc định transaction cũ tiếp tục bao phủ handler. Nếu handler cần transaction, phải thiết lập transaction ở phần xử lý thích hợp trên worker hoặc poller.

Ví dụ:

~~~text
caller: bắt đầu transaction -> gửi sang ExecutorChannel -> commit
worker: nhận công việc -> cập nhật database thất bại
~~~

Lỗi của worker không tự rollback transaction mà caller đã commit. Tương tự, gửi một `ErrorMessage` không tự hoàn tác email, lời gọi API hoặc bản ghi đã ghi thành công trước đó. Với quy trình nhiều bước, cần thiết kế trạng thái, idempotency hoặc hành động bù theo nghiệp vụ. Cơ sở về việc `ExecutorChannel` không chia sẻ transaction giữa sender và handler được nêu trong [ExecutorChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

### 8.2. Đưa lỗi vào error channel không đồng nghĩa retry

Một error consumer ghi log chỉ tạo ra khả năng quan sát. Nếu muốn retry, phải cấu hình chính sách retry, phạm vi thực hiện lại và hành vi khi hết lượt. `RequestHandlerRetryAdvice` có thể bao quanh handler; khi có recovery callback, hành vi sau cùng có thể khác với việc tiếp tục ném exception. Xem [Provided Advice Classes — Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html#retry-advice).

Trước khi thêm retry cho ví dụ đặt hàng, cần trả lời:

- Lỗi dữ liệu như `NumberFormatException` có thể hết chỉ bằng cách thử lại không? Thông thường cần sửa dữ liệu.
- Nếu lời gọi bên ngoài đã thành công nhưng mất phản hồi, thực hiện lại có tạo đơn trùng không?
- Retry chỉ thực hiện lại handler lỗi hay chạy lại cả đoạn có tác dụng phụ?
- Sau lần cuối, lỗi được ném tiếp, chuyển sang recovery flow hay lưu để xử lý thủ công?

Không tự động gửi mọi message thất bại trở lại chính đầu vào mà không có giới hạn. Cách đó có thể tạo vòng lặp nhanh, chiếm worker và làm error queue đầy.

## 9. Tổ chức error flow để vận hành được

Một lỗi bất đồng bộ cần được biến thành thông tin có thể hành động. Với luồng cập nhật đơn hàng, bản ghi lỗi nên có:

| Trường | Mục đích |
| --- | --- |
| `businessRequestId` hoặc `orderId` | Liên hệ với yêu cầu mà người dùng biết |
| Message ID và endpoint/flow | Tìm vị trí xử lý thất bại |
| Loại wrapper và nguyên nhân | Phân biệt lỗi hạ tầng với lỗi dữ liệu/nghiệp vụ |
| Thời điểm, lần thử, trạng thái cuối | Phân biệt đang thử lại với đã thất bại |
| Tham chiếu dữ liệu cần phục hồi | Cho phép kiểm tra hoặc xử lý lại có kiểm soát |

Chỉ ghi dữ liệu cần thiết và phù hợp với ứng dụng; với payload chứa thông tin cá nhân hoặc thông tin xác thực, ưu tiên mã định danh và dữ liệu đã che thay vì ghi toàn bộ message.

Error handler cũng có thể lỗi. Nếu nó gọi một hệ thống cảnh báo đang ngừng hoạt động, đường báo lỗi ban đầu có thể tiếp tục thất bại. Nên giữ thao tác ghi nhận tối thiểu đơn giản, giới hạn chờ cho các phụ thuộc và có nơi lưu hoặc metric dự phòng. Tránh nối lỗi của error handler trở lại chính flow đó theo vòng lặp.

Đặc biệt, khi biến lỗi thành một message phản hồi bình thường, phía upstream có thể coi công việc đã được xử lý theo hợp đồng. Nếu đang dùng nguồn có acknowledgement hoặc transaction, cần kiểm tra hậu quả đối với commit, rollback và redelivery của chính adapter đó. Bài thực hành dùng queue trong bộ nhớ nên không mô phỏng các bảo đảm của broker.

## 10. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu cần sửa |
| --- | --- |
| “Có header `errorChannel` thì mọi exception đều vào đó” | Header là địa chỉ; phải có thành phần bắt và công bố lỗi |
| “Flow bất đồng bộ thì `send()` không thể ném lỗi” | Bước gửi hoặc giao task vẫn có thể thất bại đồng bộ |
| “Có `DirectChannel` nghĩa là toàn flow chạy trên caller” | Nó chạy trên thread gửi hiện tại, có thể là worker sau một biên khác |
| “Error channel luôn tạo thêm thread” | Cách thực thi phụ thuộc loại channel và consumer của đường lỗi |
| “Không thấy exception ở caller nghĩa là xử lý thành công” | Có thể mới tiếp nhận, chưa xử lý hoặc lỗi đã đi theo đường khác |
| “Gateway timeout thì worker dừng” | Hết thời gian chờ không phải cơ chế hủy handler |
| “ErrorMessage giữ nguyên toàn bộ header của request” | Phải đọc ngữ cảnh được cung cấp, đặc biệt `failedMessage` và `originalMessage` |
| “Ghi log là đủ cho lỗi đặt hàng” | Còn cần trạng thái nghiệp vụ, tương quan và phương án phục hồi |

## 11. Bài tập củng cố

1. Trong test `executorFailureArrivesAtRequestErrorChannel`, đổi giá trị header từ đối tượng `asyncErrors` thành tên bean `"asyncErrors"`. Xác minh framework vẫn phân giải được kênh và lỗi mang đúng `businessRequestId`.
2. Thêm một test gửi message lỗi vào `queuedInput` với header trỏ đến `asyncErrors`. Với error handler tiêu chuẩn, kiểm tra header được ưu tiên và `pollerErrors` không nhận lỗi của request này.
3. Thêm một handler sau transformer để giả lập cập nhật đơn hàng. Chứng minh handler đó không chạy khi transformer thất bại, nhưng không suy diễn rằng các tác dụng phụ xảy ra trước transformer được hoàn tác.
4. Thiết kế một kết quả tác vụ có ba trạng thái `ACCEPTED`, `SUCCEEDED`, `FAILED`. Xác định sự kiện nào được quyền chuyển trạng thái, thay vì dùng kết quả `send()` để gán ngay `SUCCEEDED`.
5. Vẽ flow có một filter và một gateway request-reply. Chỉ ra điều gì xảy ra khi filter loại message mà không tạo reply, rồi đề xuất cách biểu diễn từ chối dữ liệu theo hợp đồng của gateway.

Khi tự phân tích một flow mới, hãy xác định điểm gửi, các biên chuyển thread, nơi bắt exception và người còn chờ kết quả. Sau đó chọn cách quan sát phù hợp: exception tại caller, reply theo hợp đồng, kết quả hoàn tất bất đồng bộ hoặc `ErrorMessage` có ngữ cảnh đủ để xử lý.
