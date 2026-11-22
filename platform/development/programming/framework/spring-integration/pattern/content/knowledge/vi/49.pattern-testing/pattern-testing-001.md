# Kiểm thử từng pattern với message tối thiểu

## 1. Mục tiêu và phạm vi

Enterprise Integration Patterns (EIP) giúp tách các thành phần bằng thông điệp và kênh giao tiếp. Trong Spring Integration, một luồng có thể đi qua **Router**, **Filter**, **Transformer**, **Splitter**, **Aggregator**, **Gateway**, cơ chế **retry** và **error channel**. Luồng có thể chạy đúng khi thử thủ công nhưng vẫn sai ở một nhánh hiếm gặp, mất header hoặc ghép nhầm các message thuộc hai yêu cầu khác nhau.

Bài này thuộc chương **Kiểm thử pattern** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu là học cách kiểm thử từng pattern bằng tập message **nhỏ nhất vẫn chứng minh được hành vi mong muốn**, sau đó ghép các phép kiểm tra để bảo đảm luồng thông điệp ít phụ thuộc, dễ mở rộng và dễ quan sát:

- Xác định hợp đồng đầu vào, đầu ra và tác dụng phụ của một pattern.
- Dựng message với payload và header cần thiết; không cần khởi động broker, HTTP server hay cơ sở dữ liệu khi đang kiểm tra logic nội bộ.
- Kiểm tra cả nhánh thành công, nhánh bị loại, nhánh lỗi và đường đi của message.
- Kiểm tra số lượng message, thứ tự khi được bảo đảm, correlation, retry và thời điểm hoàn tất một nhóm.
- Giữ test độc lập, lặp lại được và thất bại với thông báo đủ rõ để tìm ra pattern gây lỗi.

**Message tối thiểu** không nhất thiết là *một message*. Router thường chỉ cần một message cho mỗi nhánh; Splitter cần một message có ít nhất hai phần tử để chứng minh có tách; Aggregator cần đủ message của một nhóm để kiểm tra điều kiện giải phóng. Nếu muốn chứng minh hai nhóm không bị trộn, phải có ít nhất hai correlation ID.

## 2. Hợp đồng kiểm thử: quan sát gì ở mỗi pattern?

Một message của Spring Integration thường có hai phần:

~~~text
Message<T>
├── payload: dữ liệu nghiệp vụ (ví dụ "order-1", 3, List<String>)
└── headers: metadata định tuyến, tương quan và phản hồi
    ├── id, timestamp       (framework tạo sẵn)
    ├── kind, tenantId      (header nghiệp vụ nếu luồng cần)
    ├── correlationId        (nhóm message liên quan)
    ├── sequenceNumber       (vị trí trong nhóm)
    ├── sequenceSize         (số phần tử dự kiến)
    ├── replyChannel         (địa chỉ nhận phản hồi, khi cần)
    └── errorChannel         (đích xử lý lỗi, khi cần)
~~~

Không đưa mọi header vào mọi test. Chỉ cung cấp header mà nhánh đang kiểm tra thực sự đọc; các header hệ thống có thể do framework tạo ra. Tránh kiểm tra chính xác giá trị \`id\` hoặc \`timestamp\` tự sinh vì chúng không phải hợp đồng nghiệp vụ.

| Pattern | Message đầu vào tối thiểu | Điều cần khẳng định | Trường hợp đối chứng |
| --- | --- | --- | --- |
| Router | Payload \`"m1"\` và \`kind=VIP\` | Chỉ nhánh VIP nhận message | \`kind=STANDARD\` đi nhánh còn lại; nhánh không liên quan rỗng |
| Filter | Payload \`"ok"\` | Message hợp lệ được chuyển tiếp | Payload trắng bị loại hoặc vào discard channel |
| Transformer | Payload \`"  a  "\` | Payload đầu ra thành \`"a"\`; header cần thiết được giữ | Input không hỗ trợ được xử lý theo hợp đồng |
| Splitter | Payload \`["A", "B"]\` | Có đúng hai message con, mỗi con mang một phần tử | Danh sách một phần tử; danh sách rỗng theo chính sách đã chọn |
| Aggregator | Hai message có cùng \`correlationId\`, \`sequenceSize=2\`, số thứ tự 1 và 2 | Chưa phát kết quả sau message thứ nhất, phát đúng một kết quả sau message thứ hai | Nhóm khác không bị gộp chung |
| Gateway | Một lời gọi \`normalize(" a ")\` | Lời gọi nhận \`"a"\` qua đường request/reply | Timeout hoặc lỗi khi không có phản hồi |
| Retry | Một message và handler lỗi tạm thời ở lần đầu | Handler được gọi hai lần rồi thành công nếu cấu hình tối đa hai lần | Lỗi liên tục thì dừng đúng giới hạn |
| Error channel | Một message gây lỗi, có kênh lỗi phù hợp | Nhận được \`ErrorMessage\` chứa nguyên nhân | Không được nhầm exception đồng bộ với lỗi phát qua kênh bất đồng bộ |
| Correlation | Hai nhóm A/B, mỗi nhóm hai message | Mỗi kết quả chỉ chứa phần tử cùng nhóm | Gửi xen kẽ A1, B1, B2, A2 |

**Nguyên tắc đo:** Kiểm tra cả điều đã xảy ra và điều *không* được xảy ra. Một test Router xác nhận VIP nhận message nhưng không kiểm tra nhánh STANDARD có rỗng hay không vẫn bỏ sót lỗi phát trùng.

## 3. Chọn mức kiểm thử

| Mức | Phạm vi | Dùng khi |
| --- | --- | --- |
| Unit test | Hàm chọn nhánh, predicate, phép biến đổi, hàm correlation | Logic thuần Java, chưa cần ApplicationContext |
| Flow/component test | Channel → một hoặc vài endpoint Spring Integration → channel quan sát được | Muốn chứng minh cấu hình Router, Filter, Splitter, Aggregator và header hoạt động thật |
| Integration test | Gateway, broker, database, HTTP, giao dịch và hệ thống ngoài | Muốn xác minh hợp đồng I/O, timeout, retry với hạ tầng thật hoặc môi trường mô phỏng |

Ưu tiên unit test cho logic thuần, dùng flow test để bắt lỗi wiring. Chỉ kết nối dịch vụ ngoài ở những test mà tính đúng đắn phụ thuộc vào dịch vụ đó. Nhờ vậy test nhanh, ổn định và chỉ báo đúng nguyên nhân.

Với dự án Spring Boot dùng Spring Integration, các dependency thử nghiệm thường là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ví dụ bên dưới minh họa Java 17, JUnit 5, AssertJ và Java DSL của Spring Integration 6.x. Trong dự án khác, dùng phiên bản Spring Boot và Spring Integration tương thích với nhau. Test chỉ dùng \`DirectChannel\` và \`QueueChannel\`, không yêu cầu message broker.

## 4. Ví dụ có thể chạy: năm pattern cốt lõi

Đặt lớp sau vào phần test, ví dụ \`src/test/java/example/PatternMessageTest.java\`. Các luồng bắt đầu từ channel tên \`*.in\`; đầu ra là \`QueueChannel\` để test có thể lấy message và kiểm tra kết quả. Mỗi bài test tạo đúng lượng message cần thiết.

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PatternMessageTest.Flows.class)
class PatternMessageTest {

    @Autowired
    ApplicationContext context;

    private MessageChannel input(String name) {
        return context.getBean(name, MessageChannel.class);
    }

    private QueueChannel output(String name) {
        return context.getBean(name, QueueChannel.class);
    }

    private Message<?> received(String channel) {
        Message<?> message = output(channel).receive(1_000);
        assertThat(message).as("Expected message from %s", channel).isNotNull();
        return message;
    }

    @Test
    void router_goes_to_exactly_one_branch() {
        Message<String> message = MessageBuilder.withPayload("order-1")
                .setHeader("kind", "VIP")
                .build();

        assertThat(input("router.in").send(message)).isTrue();

        assertThat(received("router.vip").getPayload()).isEqualTo("order-1");
        assertThat(output("router.standard").receive(0)).isNull();
    }

    @Test
    void filter_accepts_valid_and_sends_invalid_to_discard() {
        input("filter.in").send(MessageBuilder.withPayload("ok").build());
        input("filter.in").send(MessageBuilder.withPayload("  ").build());

        assertThat(received("filter.accept").getPayload()).isEqualTo("ok");
        assertThat(received("filter.discard").getPayload()).isEqualTo("  ");
        assertThat(output("filter.accept").receive(0)).isNull();
    }

    @Test
    void transformer_changes_payload_and_keeps_business_header() {
        Message<String> message = MessageBuilder.withPayload("  abc  ")
                .setHeader("tenantId", "tenant-7")
                .build();

        input("transform.in").send(message);

        Message<?> result = received("transform.out");
        assertThat(result.getPayload()).isEqualTo("abc");
        assertThat(result.getHeaders().get("tenantId")).isEqualTo("tenant-7");
    }

    @Test
    void splitter_emits_one_message_for_each_element() {
        input("split.in").send(
                MessageBuilder.withPayload(List.of("A", "B")).build());

        Message<?> first = received("split.out");
        Message<?> second = received("split.out");

        assertThat(List.of(first.getPayload(), second.getPayload()))
                .containsExactly("A", "B");
        assertThat(first.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE)).isEqualTo(2);
        assertThat(output("split.out").receive(0)).isNull();
    }

    @Test
    void aggregator_waits_for_the_whole_group() {
        input("aggregate.in").send(part("batch-1", 1, 2, "A"));
        assertThat(output("aggregate.out").receive(0)).isNull();

        input("aggregate.in").send(part("batch-1", 2, 2, "B"));
        Message<?> result = received("aggregate.out");

        assertThat(result.getPayload()).isInstanceOf(List.class);
        assertThat((List<?>) result.getPayload())
                .containsExactlyInAnyOrder("A", "B");
        assertThat(output("aggregate.out").receive(0)).isNull();
    }

    private static Message<String> part(
            String groupId, int sequence, int size, String value) {
        return MessageBuilder.withPayload(value)
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, groupId)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, sequence)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, size)
                .build();
    }

    @Configuration
    @EnableIntegration
    static class Flows {

        @Bean("router.vip")
        QueueChannel vip() {
            return new QueueChannel();
        }

        @Bean("router.standard")
        QueueChannel standard() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow router() {
            return IntegrationFlow.from("router.in")
                    .route("headers['kind']", r -> r
                            .channelMapping("VIP", "router.vip")
                            .channelMapping("STANDARD", "router.standard"))
                    .get();
        }

        @Bean("filter.accept")
        QueueChannel accepted() {
            return new QueueChannel();
        }

        @Bean("filter.discard")
        QueueChannel discarded() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow filter() {
            return IntegrationFlow.from("filter.in")
                    .filter(String.class, text -> !text.isBlank(),
                            f -> f.discardChannel("filter.discard"))
                    .channel("filter.accept")
                    .get();
        }

        @Bean("transform.out")
        QueueChannel transformed() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow transformer() {
            return IntegrationFlow.from("transform.in")
                    .transform(String.class, String::trim)
                    .channel("transform.out")
                    .get();
        }

        @Bean("split.out")
        QueueChannel splitOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow splitter() {
            return IntegrationFlow.from("split.in")
                    .split()
                    .channel("split.out")
                    .get();
        }

        @Bean("aggregate.out")
        QueueChannel aggregateOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow aggregator() {
            return IntegrationFlow.from("aggregate.in")
                    .aggregate()
                    .channel("aggregate.out")
                    .get();
        }
    }
}
~~~

**Cách đọc kết quả:**

1. Router xác nhận cả **đúng đầu ra** lẫn **nhánh còn lại không có message**. Muốn bao phủ nhánh STANDARD, bổ sung test đối xứng với \`kind=STANDARD\`; muốn bao phủ nhánh không nhận diện được, xác định rõ chính sách *ném lỗi*, *đưa vào default channel* hoặc *bỏ qua* rồi test đúng chính sách đó.
2. Filter gửi hai message: \`"ok"\` được nhận và \`"  "\` được chuyển vào discard channel. Khi không cấu hình discard channel, một message bị loại có thể kết thúc tại Filter mà không sinh đầu ra; khi đó chỉ khẳng định output channel rỗng.
3. Transformer chỉ đổi payload. Test còn kiểm tra \`tenantId\`, bởi việc bỏ mất metadata quan trọng là một dạng lỗi tích hợp dù giá trị trả về đúng.
4. Splitter tạo hai message con với sequence metadata. Với danh sách hai phần tử và channel đồng bộ trong ví dụ, ta có thể kiểm tra thứ tự \`A, B\`; trong hệ thống xử lý song song, đừng khẳng định thứ tự nếu kiến trúc không cam kết.
5. Aggregator không phát kết quả khi chỉ có phần tử 1/2. Chỉ sau khi có phần tử 2/2 thì nhóm mới hoàn tất. Default aggregator dùng correlation và sequence metadata để gom nhóm; cấu hình release strategy khác phải được kiểm tra theo hợp đồng riêng.

### Không lạm dụng thời gian chờ

\`receive(0)\` là phép kiểm tra tức thời hữu ích với luồng **đồng bộ** như ví dụ. Với ExecutorChannel, broker hoặc tác vụ bất đồng bộ, \`receive(0) == null\` ngay sau khi gửi chưa chứng minh rằng message sẽ không xuất hiện muộn. Khi cần kiểm tra *không có message trong một khoảng quan sát*, dùng timeout hữu hạn và hiểu rõ giả định về lịch chạy; với lệnh mong đợi có message, dùng \`receive(1_000)\` hoặc cơ chế chờ theo điều kiện, tránh \`Thread.sleep\` cố định.

## 5. Gateway: kiểm tra request/reply bằng một lời gọi

Gateway biến lời gọi Java thành message đi vào flow và chuyển message phản hồi về giá trị trả về. Kiểm thử tối thiểu cần **một request**, **một reply** và ràng buộc timeout. Ví dụ, khai báo trong package được Spring Integration scan:

~~~java
@MessagingGateway(defaultRequestChannel = "gateway.in")
public interface NormalizeGateway {
    String normalize(String input);
}
~~~

Cấu hình luồng đáp ứng request (cùng ApplicationContext với gateway):

~~~java
@Bean
IntegrationFlow normalizeFlow() {
    return IntegrationFlow.from("gateway.in")
            .transform(String.class, String::trim)
            .get();
}
~~~

Trong test có Spring context và gateway được đăng ký (chẳng hạn qua \`@IntegrationComponentScan\`):

~~~java
@Autowired
NormalizeGateway gateway;

@Test
void gateway_returns_the_reply() {
    assertThat(gateway.normalize("  hello  ")).isEqualTo("hello");
}
~~~

Gateway cần một đường phản hồi đến \`replyChannel\` do framework thiết lập. Nếu endpoint cuối cùng không tạo reply, lời gọi có thể chờ đến timeout theo cấu hình. Test nhánh không phản hồi phải đặt timeout hữu hạn để không treo bộ test. Với nghiệp vụ bất đồng bộ, xác định liệu Gateway thật sự trả về ngay, trả \`Future\`/\`CompletableFuture\` hay cung cấp cơ chế callback; không giả định mọi gateway đều đồng bộ.

## 6. Retry: một message, nhiều lần xử lý

Trong luồng tích hợp, retry thường áp dụng cho lỗi **tạm thời** như timeout hoặc dịch vụ chưa sẵn sàng. Test phải chứng minh được **số lần thử** và **kết quả cuối**, thay vì chỉ nhìn thấy kết quả thành công:

~~~java
AtomicInteger attempts = new AtomicInteger();

GenericHandler<String> occasionallyFailingHandler = (payload, headers) -> {
    int current = attempts.incrementAndGet();
    if (current == 1) {
        throw new IllegalStateException("temporary failure");
    }
    return "processed:" + payload;
};
~~~

Đưa handler này vào một endpoint được gắn retry advice (ví dụ \`RequestHandlerRetryAdvice\` với \`RetryTemplate\`, tối đa **2 attempts**). Gửi duy nhất message payload \`"M1"\` và kiểm tra:

~~~java
assertThat(received("retry.out").getPayload()).isEqualTo("processed:M1");
assertThat(attempts.get()).isEqualTo(2);
~~~

Đây là **đoạn minh họa phần handler và assertion**; để thực thi cần gắn handler, retry advice và output channel trong flow. Trường hợp đối chứng là handler luôn ném lỗi: xác nhận tối đa hai lần thử, không có message thành công và lỗi được chuyển đúng kênh hoặc ném ra caller theo cấu hình. Nếu policy có backoff, dùng độ trễ rất ngắn trong test. Nếu có recovery callback, kiểm tra kết quả recovery thay vì mặc định phải có exception.

**Phân biệt ba khái niệm:** \`maxAttempts=2\` thường nghĩa là **một lần đầu + một lần thử lại**; retry có thể khiến handler chạy nhiều lần cho cùng message; vì vậy xử lý có tác dụng phụ (ghi đơn hàng, tính phí, phát sự kiện) phải cân nhắc idempotency. Một test retry thành công không chứng minh được giao dịch bên ngoài an toàn trước xử lý trùng.

## 7. Error channel: xác định lỗi đồng bộ và bất đồng bộ

Đường lỗi của Spring Integration phụ thuộc vào cách thực thi:

~~~mermaid
flowchart TD
    A[Message vào flow] --> B{Channel / endpoint chạy thế nào?}
    B -->|Đồng bộ: DirectChannel| C[Handler ném exception]
    C --> D[Caller send hoặc Gateway nhận exception]
    B -->|Bất đồng bộ: ExecutorChannel| E[Handler ném exception]
    E --> F[ErrorMessage được publish]
    F --> G[errorChannel được cấu hình]
~~~

Với \`DirectChannel\` đồng bộ, lỗi thông thường lan ra caller của \`send()\` hoặc Gateway:

~~~java
assertThatThrownBy(() ->
        input.send(MessageBuilder.withPayload("invalid").build()))
        .isInstanceOf(MessagingException.class);
~~~

Với luồng bất đồng bộ có error handler phát lỗi, gửi message mang \`errorChannel\` (hoặc dùng global \`errorChannel\` đúng cấu hình), rồi kiểm tra kênh lỗi:

~~~java
Message<String> badMessage = MessageBuilder.withPayload("invalid")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "flow.errors")
        .build();

input.send(badMessage);
ErrorMessage error = (ErrorMessage) errors.receive(1_000);

assertThat(error).isNotNull();
assertThat(error.getPayload()).isInstanceOf(MessagingException.class);
~~~

Đoạn sau giả định \`input\` đi qua endpoint bất đồng bộ, \`errors\` là \`QueueChannel\` đăng ký tên \`flow.errors\` và error handler được cấu hình để publish \`ErrorMessage\`. Không thể chỉ thêm header \`errorChannel\` vào flow đồng bộ rồi mặc định exception sẽ xuất hiện ở channel đó. Trong test thực tế, kiểm tra thêm loại exception gốc, thông điệp lỗi có ích cho chẩn đoán và khả năng truy ra message thất bại.

## 8. Correlation: chứng minh hai nhóm không lẫn nhau

Aggregator thường nhóm theo \`correlationId\`. Để phát hiện lỗi trộn nhóm, một nhóm đơn lẻ là chưa đủ. Dùng **bốn message** tạo thành hai nhóm, mỗi nhóm có kích thước 2; gửi xen kẽ:

~~~text
A1 (correlationId=A, sequenceNumber=1, sequenceSize=2)
B1 (correlationId=B, sequenceNumber=1, sequenceSize=2)
B2 (correlationId=B, sequenceNumber=2, sequenceSize=2) -> chỉ B hoàn tất
A2 (correlationId=A, sequenceNumber=2, sequenceSize=2) -> A hoàn tất
~~~

Mở rộng lớp test ở mục 4 bằng phép kiểm tra:

~~~java
@Test
void aggregator_keeps_interleaved_groups_separate() {
    input("aggregate.in").send(part("A", 1, 2, "A1"));
    input("aggregate.in").send(part("B", 1, 2, "B1"));
    assertThat(output("aggregate.out").receive(0)).isNull();

    input("aggregate.in").send(part("B", 2, 2, "B2"));
    Message<?> groupB = received("aggregate.out");
    assertThat((List<?>) groupB.getPayload())
            .containsExactlyInAnyOrder("B1", "B2");

    input("aggregate.in").send(part("A", 2, 2, "A2"));
    Message<?> groupA = received("aggregate.out");
    assertThat((List<?>) groupA.getPayload())
            .containsExactlyInAnyOrder("A1", "A2");
    assertThat(output("aggregate.out").receive(0)).isNull();
}
~~~

Test này phát hiện được tình huống grouping sai, chỉ cần **bốn message**. Đối với luồng sản xuất thực tế, còn phải quyết định rõ các trường hợp: trùng \`sequenceNumber\`, message đến muộn, nhóm thiếu phần tử, nhóm hết hạn, correlation key rỗng, và trạng thái nhóm sau restart. Các hành vi đó phụ thuộc \`MessageGroupStore\`, \`ReleaseStrategy\`, \`MessageGroupProcessor\` và chính sách timeout/expiry được cấu hình; không nên tự giả định.

## 9. Kiểm thử một chuỗi pattern từ đầu đến cuối

Sau khi kiểm tra riêng từng pattern, thêm một số test đường đi chính để bảo đảm các endpoint nối với nhau đúng:

~~~mermaid
flowchart LR
    IN[Message tối thiểu] --> R{Router}
    R -->|VIP| F{Filter}
    R -->|STANDARD| OUT2[Standard output]
    F -->|Hợp lệ| T[Transformer]
    F -->|Bị loại| DROP[Discard channel]
    T --> S[Splitter]
    S --> A[Aggregator]
    A --> OUT[Result / Gateway reply]
    F -. Lỗi xử lý .-> ERR[Error channel hoặc exception]
~~~

Ví dụ nghiệp vụ: yêu cầu VIP chứa hai mã hàng \`[" P01 ", " P02 "]\`. Router chọn nhánh VIP, Filter loại yêu cầu không hợp lệ, Transformer chuẩn hóa dữ liệu, Splitter phát hai dòng hàng, Aggregator đợi đủ hai dòng rồi trả kết quả. Test end-to-end tối thiểu phải trả lời: đúng nhánh chưa, có mất mã hàng không, số message trước/sau Splitter có đúng không, Aggregator có chỉ xuất kết quả khi đủ nhóm không, và Gateway có nhận reply không.

Để test dễ chẩn đoán, gán tên channel rõ nghĩa và dùng \`QueueChannel\` ở các điểm quan sát. Không nên đặt assertion vào log: log có thể đổi mức ghi hoặc định dạng mà không làm thay đổi hành vi của flow. Khi cần xác nhận một nhánh, kiểm tra message nhận ở channel đó. Khi cần xác nhận lỗi, bắt exception hoặc đọc \`ErrorMessage\` tùy mô hình thực thi.

### Ma trận happy path và edge case

| Tình huống | Input nhỏ nhất | Phát hiện lỗi gì? |
| --- | --- | --- |
| Chọn VIP | Một message \`kind=VIP\` | Mapping sai, phát vào nhiều nhánh |
| Chọn STANDARD | Một message \`kind=STANDARD\` | Thiếu hoặc đảo nhánh |
| Loại payload trắng | Một message payload \`" "\` | Filter bỏ sót điều kiện |
| Giữ metadata | Một message có \`tenantId\` | Transformer làm mất header cần thiết |
| Tách hai phần tử | Một message payload \`["A","B"]\` | Thiếu/thừa output, hỏng sequence |
| Hoàn tất nhóm | Hai message A1, A2 | Release sớm, không release hoặc phát nhiều lần |
| Không trộn nhóm | A1, B1, B2, A2 | Correlation sai |
| Trả lời Gateway | Một request \`" a "\` | Mất reply, reply sai payload |
| Lỗi nhất thời | Một message, handler lỗi lần đầu | Retry thiếu hoặc vượt giới hạn |
| Lỗi vĩnh viễn | Một message, handler luôn lỗi | Treo vô hạn, nuốt lỗi, publish sai kênh |

## 10. Giữ bộ test ổn định, có khả năng mở rộng

1. **Cô lập trạng thái:** Mỗi bài test nên dùng correlation ID riêng; không chia sẻ group store, hàng đợi, bộ đếm retry giữa các test nếu không dọn trạng thái. Nếu test chạy song song, ưu tiên tạo context/bean và kênh độc lập.
2. **Có giới hạn chờ:** Đặt timeout hữu hạn cho QueueChannel, Gateway và chờ tác vụ bất đồng bộ. Tránh \`Thread.sleep\` và giả định về tốc độ máy chạy CI.
3. **Không khẳng định thứ tự không được cam kết:** Kiểm tra tập payload khi xử lý có thể song song; chỉ kiểm tra thứ tự khi flow dùng đường đồng bộ hoặc cơ chế sắp xếp đã định nghĩa.
4. **Tách logic và wiring:** Unit test predicate/mapper/correlation function bằng Java thuần; flow test dùng Spring context để phát hiện sai tên channel hoặc sai header.
5. **Mock ở biên tích hợp:** Với HTTP, database, broker, dùng stub hoặc test adapter ở những trường hợp chưa cần hạ tầng thật. Spring Integration cung cấp \`spring-integration-test\`, \`@SpringIntegrationTest\` và \`MockIntegrationContext\` hỗ trợ thay thế endpoint trong bài test phù hợp.
6. **Quan sát có chủ đích:** Ghi lại message ID/correlation ID ở điểm đầu, nhánh quan trọng và error handler khi cần điều tra. Bài test nên dựa vào payload/header/output channel, không phụ thuộc chuỗi log.
7. **Kiểm soát tác dụng phụ:** Với retry, kiểm tra số lần gọi và idempotency khi có ghi dữ liệu; với Aggregator, kiểm tra quy tắc hết hạn hoặc loại nhóm lỗi nếu sản phẩm có yêu cầu đó.

## 11. Bài thực hành tự kiểm tra

Tự thêm bốn test vào ví dụ ở mục 4:

1. **Router nhánh STANDARD:** Gửi một message có \`kind=STANDARD\`; xác nhận chỉ \`router.standard\` nhận được.
2. **Filter toàn bộ bị loại:** Gửi một message payload \`" "\`; khẳng định \`filter.accept\` rỗng và \`filter.discard\` nhận đúng payload.
3. **Aggregator nhiều nhóm:** Sử dụng chuỗi A1, B1, B2, A2. Chứng minh kết quả thứ nhất chỉ là B, kết quả thứ hai chỉ là A.
4. **Retry hết lượt:** Handler luôn lỗi; cấu hình tối đa hai attempts; xác nhận số lần gọi đúng bằng 2 và kết quả cuối phù hợp với error/recovery policy.

Một bài làm đạt yêu cầu khi mỗi test có thể chạy độc lập, dùng đúng lượng message tối thiểu và thể hiện rõ ba điều: **message đã đi đâu**, **payload/header cuối có gì**, và **điều gì không được xảy ra**. Đây là nền tảng để kiểm thử các luồng Spring Integration nhiều nhánh mà vẫn giữ được khả năng bảo trì khi mở rộng thêm pattern.
