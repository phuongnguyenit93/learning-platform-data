# Kiểm thử splitter-aggregator

## 1. Mục tiêu và phạm vi

Trong chương **Testing support** của mô-đun **SPRING_INTEGRATION_CORE**, bài này trình bày cách kiểm thử một luồng tách thông điệp, xử lý từng phần rồi gom kết quả. Trọng tâm là hợp đồng giữa `Message`, `MessageChannel`, splitter endpoint, transformer và aggregator trong Java DSL.

Sau bài học, bạn có thể:

- Kiểm tra payload và các header liên kết những phần được tách.
- Chứng minh aggregator chờ đủ dữ liệu và không trộn các yêu cầu.
- Tạo dữ liệu kiểm thử sai thứ tự, đến muộn, bị thiếu hoặc bị trùng.
- Phân biệt kiểm thử chính sách hết hạn với kiểm thử bộ lập lịch.
- Quan sát đầu ra, nhánh discard, lỗi và trạng thái nhóm bằng các điểm kiểm tra rõ ràng.

Ví dụ dùng Java 17, JUnit Jupiter, Spring Test và API Spring Integration 6.5.x. Chọn phiên bản thư viện tương thích với BOM của dự án; không ghép tùy ý các phiên bản Spring. Các lớp ví dụ độc lập với Spring Boot, broker và cơ sở dữ liệu.

## 2. Bài toán: đúng tổng chưa đủ để chứng minh luồng đúng

Giả sử yêu cầu chứa danh sách `[1, 2, 3]`. Mỗi phần tử được nhân với `10`; aggregator tính tổng:

~~~text
[1, 2, 3] → 1, 2, 3 → 10, 20, 30 → 60
~~~

Một phép kiểm tra duy nhất `payload == 60` không trả lời được các câu hỏi sau:

- Có thông điệp nào bị đưa nhầm vào nhóm của yêu cầu khác không?
- Nhóm có từng phát kết quả trước khi nhận phần tử cuối không?
- Có phát thêm một kết quả ngoài dự kiến không?
- Header nghiệp vụ có còn nguyên sau transformer không?
- Thông điệp đến muộn có mở lại một yêu cầu đã hoàn tất không?
- Nếu phần tử thứ hai không bao giờ đến, dữ liệu được giữ bao lâu?

Vì vậy, hãy kiểm tra cả **giá trị**, **số lượng đầu ra** và **quá trình thay đổi trạng thái**. Với phép cộng, đổi thứ tự không làm đổi tổng; nếu nghiệp vụ cần thứ tự, phải có phép kiểm tra thứ tự riêng.

~~~mermaid
flowchart LR
    A["Yêu cầu: List<Integer>"] --> B["Splitter"]
    B --> C["Transformer: x * 10"]
    C --> D["Kênh trước aggregator"]
    D --> E["Aggregator"]
    E <--> S[("MessageGroupStore")]
    E --> F["Kết quả: tổng"]
    E --> G["Discard"]
    B --> H["Đầu vào rỗng"]
~~~

Trong bài, có ba mức kiểm thử:

| Mức | Gửi dữ liệu ở đâu? | Quan sát ở đâu? | Câu hỏi chính |
|---|---|---|---|
| Splitter | Trước splitter | Kênh chứa các phần | Payload và header sau tách có đúng không? |
| Aggregator | Ngay trước aggregator | Output, discard và store | Nhóm có được giữ, release và đóng đúng không? |
| Toàn luồng | Đầu vào nghiệp vụ | Kết quả cuối | Các endpoint có phối hợp đúng không? |

Không mock splitter hay aggregator trong phép kiểm thử hợp đồng của chính chúng. Với hệ thống thật, có thể thay dịch vụ tính giá hoặc adapter từ xa bằng một cộng tác viên kiểm soát được.

## 3. Hợp đồng thông điệp cần kiểm tra

### 3.1. Header sau splitter

Với splitter mặc định, đầu vào là một `List` có kích thước xác định và bật `applySequence`, các phần được gắn header trình tự. Dùng hằng số của `IntegrationMessageHeaderAccessor` trong mã kiểm thử để tránh lỗi gõ tên header. Xem [hợp đồng splitter](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

| Header | Ý nghĩa trong ví dụ | Điều cần assert |
|---|---|---|
| `CORRELATION_ID` | Liên kết các phần của một lần tách | Các phần có cùng giá trị; với splitter mặc định ở đây, giá trị bằng ID thông điệp đầu vào |
| `SEQUENCE_NUMBER` | Vị trí phần tử | Lần lượt là `1, 2, 3` |
| `SEQUENCE_SIZE` | Tổng số phần dự kiến | Cùng bằng `3` |
| `orderId` | Mã nghiệp vụ do ứng dụng đặt | Giữ nguyên giá trị mong đợi |

`orderId` không tự trở thành khóa gom nhóm chỉ vì nó có tên giống mã đơn hàng. Nếu muốn gom theo mã nghiệp vụ, phải cấu hình correlation strategy và kiểm thử chiến lược đó.

Các assertion trên áp dụng cho một splitter cụ thể trong ví dụ. Với splitter tùy chỉnh hoặc luồng tách lồng nhau, cần viết hợp đồng tương ứng.

### 3.2. Correlation, release và tạo kết quả là ba quyết định

Một aggregator cần trả lời:

1. Thông điệp thuộc nhóm nào?
2. Nhóm đã đủ điều kiện phát kết quả chưa?
3. Khi phát, payload kết quả được tính thế nào?

Cấu hình mặc định dùng header correlation để gom và kích thước sequence để quyết định release. Ví dụ bên dưới giữ hai quyết định đó, chỉ thay processor để tính tổng. Xem [mô hình aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

Điểm kiểm tra nên được đặt ở ranh giới của từng quyết định. Nếu một test toàn luồng thất bại, các test nhỏ sẽ giúp phân biệt lỗi metadata sau splitter với lỗi release hoặc lỗi tính tổng.

### 3.3. Phân biệt trạng thái hoàn tất và xóa nhóm

Nhóm có thể đã hoàn tất, không còn giữ phần tử, nhưng vẫn còn bản ghi để nhận diện thông điệp đến muộn. Với `expireGroupsUponCompletion(false)`, ví dụ chủ động giữ dấu vết này. Vì thế, không dùng `getMessageGroupCount() == 0` làm kỳ vọng cho mọi trường hợp hoàn tất.

Cần kiểm tra riêng `isComplete()`, `size()` và hành vi khi có dữ liệu đến muộn. Xem [vòng đời của AggregatingMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AggregatingMessageHandler.html).

## 4. Chuẩn bị phụ thuộc và môi trường

Trong dự án đã có dependency management của Spring Boot, có thể dùng:

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

Nếu không dùng Boot, cần quản lý phiên bản tương thích cho `spring-integration-core`, `spring-test`, JUnit Jupiter và các thư viện test liên quan. Cấu hình công cụ build để chạy JUnit Platform.

Bộ test chính dưới đây chỉ dùng Spring Test và JUnit; `spring-integration-test` phục vụ các tình huống thay endpoint ở phần sau. `@SpringIntegrationTest` cung cấp `MockIntegrationContext` khi cần thay một phần luồng; nó không bắt buộc chỉ để chạy `IntegrationFlow` trong Spring Test. Xem [testing support và test context](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

## 5. Bộ kiểm thử hoàn chỉnh cho splitter, aggregator và toàn luồng

Ví dụ tạo các điểm vào độc lập:

- `splitInput` chỉ đi qua splitter, thuận tiện kiểm tra các phần.
- `aggregateInput` nhận trực tiếp các phần đã có header, thuận tiện điều khiển thời điểm release.
- `fullInput` đi qua splitter và transformer rồi chuyển vào cùng aggregator.

Các điểm nhận kết quả là `QueueChannel`, để test chủ động đọc thông điệp. Các kênh xử lý là `DirectChannel`, nên việc gửi và xử lý thông thường trong cấu hình này diễn ra đồng bộ.

Lưu lớp sau trong source set kiểm thử của dự án khi thực hành:

~~~java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(SplitterAggregatorTest.Config.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SplitterAggregatorTest {

    @Autowired
    @Qualifier("splitInput")
    DirectChannel splitInput;

    @Autowired
    @Qualifier("splitParts")
    QueueChannel splitParts;

    @Autowired
    @Qualifier("emptySplits")
    QueueChannel emptySplits;

    @Autowired
    @Qualifier("fullInput")
    DirectChannel fullInput;

    @Autowired
    @Qualifier("aggregateInput")
    DirectChannel aggregateInput;

    @Autowired
    @Qualifier("totals")
    QueueChannel totals;

    @Autowired
    @Qualifier("discarded")
    QueueChannel discarded;

    @Autowired
    SimpleMessageStore groupStore;

    @Test
    void splitterPublishesPayloadsAndSequenceHeaders() {
        Message<List<Integer>> request =
                MessageBuilder.withPayload(List.of(1, 2, 3))
                        .setHeader("orderId", "ORD-101")
                        .build();

        assertTrue(splitInput.send(request));

        for (int number = 1; number <= 3; number++) {
            Message<?> part = splitParts.receive(0);
            assertNotNull(part);

            assertEquals(number, part.getPayload());
            assertEquals(request.getHeaders().getId(),
                    part.getHeaders().get(
                            IntegrationMessageHeaderAccessor.CORRELATION_ID));
            assertEquals(Integer.valueOf(number),
                    part.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                            Integer.class));
            assertEquals(Integer.valueOf(3),
                    part.getHeaders().get(
                            IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                            Integer.class));
            assertEquals("ORD-101", part.getHeaders().get("orderId"));
        }

        assertNull(splitParts.receive(0));
        assertNull(emptySplits.receive(0));
    }

    @Test
    void emptyListIsSentToSplitterDiscardChannel() {
        Message<List<Integer>> request =
                MessageBuilder.withPayload(List.<Integer>of()).build();

        assertTrue(splitInput.send(request));

        assertNull(splitParts.receive(0));
        Message<?> rejected = emptySplits.receive(0);
        assertNotNull(rejected);
        assertEquals(request.getHeaders().getId(),
                rejected.getHeaders().getId());
        assertEquals(List.of(), rejected.getPayload());
        assertNull(emptySplits.receive(0));
    }

    @Test
    void aggregatorWaitsUntilAllThreePartsArrive() {
        UUID groupId = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupId, 1, 3, 10)));
        assertNull(totals.receive(0));
        assertEquals(1, groupStore.getMessageGroup(groupId).size());
        assertFalse(groupStore.getMessageGroup(groupId).isComplete());

        assertTrue(aggregateInput.send(part(groupId, 2, 3, 20)));
        assertNull(totals.receive(0));
        assertEquals(2, groupStore.getMessageGroup(groupId).size());

        assertTrue(aggregateInput.send(part(groupId, 3, 3, 30)));
        assertTotal(60);
        assertTrue(groupStore.getMessageGroup(groupId).isComplete());
        assertEquals(0, groupStore.getMessageGroup(groupId).size());
        assertNull(discarded.receive(0));
    }

    @Test
    void outOfOrderArrivalStillProducesTheExpectedSum() {
        UUID groupId = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupId, 3, 3, 30)));
        assertNull(totals.receive(0));

        assertTrue(aggregateInput.send(part(groupId, 1, 3, 10)));
        assertNull(totals.receive(0));

        assertTrue(aggregateInput.send(part(groupId, 2, 3, 20)));
        assertTotal(60);
    }

    @Test
    void interleavedGroupsAreNotMixed() {
        UUID groupA = UUID.randomUUID();
        UUID groupB = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupA, 1, 2, 10)));
        assertTrue(aggregateInput.send(part(groupB, 1, 2, 100)));
        assertNull(totals.receive(0));
        assertEquals(1, groupStore.getMessageGroup(groupA).size());
        assertEquals(1, groupStore.getMessageGroup(groupB).size());

        assertTrue(aggregateInput.send(part(groupA, 2, 2, 20)));
        assertTotal(30);
        assertFalse(groupStore.getMessageGroup(groupB).isComplete());
        assertEquals(1, groupStore.getMessageGroup(groupB).size());

        assertTrue(aggregateInput.send(part(groupB, 2, 2, 200)));
        assertTotal(300);
    }

    @Test
    void latePartIsDiscardedWhenCompletedGroupIsRetained() {
        UUID groupId = UUID.randomUUID();

        assertTrue(aggregateInput.send(part(groupId, 1, 2, 10)));
        assertTrue(aggregateInput.send(part(groupId, 2, 2, 20)));
        assertTotal(30);

        Message<Integer> late = part(groupId, 2, 2, 999);
        assertTrue(aggregateInput.send(late));

        assertNull(totals.receive(0));
        Message<?> rejected = discarded.receive(0);
        assertNotNull(rejected);
        assertEquals(late.getHeaders().getId(),
                rejected.getHeaders().getId());
        assertEquals(999, rejected.getPayload());
        assertNull(discarded.receive(0));
    }

    @Test
    void fullFlowSplitsTransformsAndAggregates() {
        Message<List<Integer>> request =
                MessageBuilder.withPayload(List.of(1, 2, 3))
                        .setHeader("orderId", "ORD-202")
                        .build();

        assertTrue(fullInput.send(request));

        assertTotal(60);
        assertTrue(groupStore.getMessageGroup(
                request.getHeaders().getId()).isComplete());
        assertNull(discarded.receive(0));
    }

    private void assertTotal(int expected) {
        Message<?> output = totals.receive(0);
        assertNotNull(output);
        assertEquals(expected, output.getPayload());
        assertNull(totals.receive(0));
    }

    private static Message<Integer> part(
            UUID groupId, int number, int size, int payload) {
        return MessageBuilder.withPayload(payload)
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupId)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        size)
                .build();
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        DirectChannel splitInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel splitParts() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel emptySplits() {
            return new QueueChannel();
        }

        @Bean
        DirectChannel fullInput() {
            return new DirectChannel();
        }

        @Bean
        DirectChannel aggregateInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel totals() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel discarded() {
            return new QueueChannel();
        }

        @Bean
        SimpleMessageStore groupStore() {
            return new SimpleMessageStore();
        }

        @Bean
        IntegrationFlow splitterProbeFlow() {
            return IntegrationFlow.from(splitInput())
                    .split(spec -> spec
                            .applySequence(true)
                            .discardChannel(emptySplits()))
                    .channel(splitParts())
                    .get();
        }

        @Bean
        IntegrationFlow fullFlow() {
            return IntegrationFlow.from(fullInput())
                    .split()
                    .transform(Integer.class, value -> value * 10)
                    .channel(aggregateInput())
                    .get();
        }

        @Bean
        IntegrationFlow aggregationFlow() {
            return IntegrationFlow.from(aggregateInput())
                    .aggregate(spec -> spec
                            .messageStore(groupStore())
                            .outputProcessor(group -> group.getMessages()
                                    .stream()
                                    .mapToInt(message ->
                                            (Integer) message.getPayload())
                                    .sum())
                            .expireGroupsUponCompletion(false)
                            .discardChannel(discarded()))
                    .channel(totals())
                    .get();
        }
    }
}
~~~

### 5.1. Vì sao test nhận ngay bằng receive(0)?

Trong cấu hình này không có executor, poller hay tác vụ timeout. Khi `DirectChannel.send()` trở về thành công, việc xử lý trên đường gửi đã hoàn tất; kết quả nếu có đã nằm trong queue đầu ra. `receive(0)` chỉ lấy dữ liệu sẵn có và không chờ.

Điều này cũng làm assertion “chưa có kết quả sau phần thứ nhất” có ý nghĩa rõ ràng. Khi chuyển một đoạn sang `ExecutorChannel`, phải thay cách chờ; không bê nguyên các assertion tức thời sang luồng bất đồng bộ. Hành vi theo luồng gọi của `DirectChannel` được mô tả trong [error handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

### 5.2. Vì sao mỗi test có một context sạch?

Aggregator và queue đều có trạng thái. Một test có thể để lại nhóm chưa hoàn tất hoặc thông điệp chưa được lấy ra. `@DirtiesContext` trong ví dụ yêu cầu tạo lại context cho test kế tiếp, giúp các tình huống độc lập.

Đây là lựa chọn ưu tiên sự rõ ràng cho fixture nhỏ. Với suite lớn, có thể dùng store riêng theo test và dọn tài nguyên có kiểm soát. Chỉ đổi group ID sang UUID không tự dọn những nhóm còn treo trong store.

### 5.3. Vì sao không dùng QueueChannel làm kênh quan sát giữa luồng?

Nếu một `QueueChannel` có cả poller xử lý thật và test cùng gọi `receive()`, hai bên cạnh tranh lấy thông điệp. Test có thể lấy mất phần tử đáng lẽ đi đến aggregator.

Trong ví dụ, `splitParts` là đầu cuối của một flow kiểm tra riêng. Nó không đồng thời là đầu vào cho phần xử lý tiếp theo. Khi cần quan sát flow thật, dùng interceptor hoặc nhánh quan sát sao cho không lấy mất thông điệp; xác định rõ điểm quan sát trước khi viết assertion.

### 5.4. Những gì bộ test đã và chưa chứng minh

Bộ test chứng minh cấu hình trong bộ nhớ xử lý đúng các tình huống được nêu. Nó không kiểm chứng độ bền qua khởi động lại, nhiều instance cùng gom một nhóm, rollback cơ sở dữ liệu hoặc chính sách giao lại của broker.

Kết quả test toàn luồng là `60` cho thấy các phần đã tới cùng nhóm với đủ metadata cần thiết. Nếu hợp đồng còn yêu cầu giữ `orderId`, hãy quan sát từng thông điệp ngay trước aggregator và assert header này; không suy ra việc bảo toàn mọi header chỉ từ tổng cuối đúng.

## 6. Kiểm thử thời hạn mà không phụ thuộc Thread.sleep()

### 6.1. Tách hai câu hỏi về thời gian

Với nhóm mới nhận hai trong ba phần, có hai điều khác nhau cần kiểm chứng:

| Câu hỏi | Loại test |
|---|---|
| Khi buộc kết thúc một nhóm chưa đủ, phát kết quả một phần hay discard? | Test chính sách hết hạn |
| Scheduler có gọi xử lý hết hạn đúng sau khoảng cấu hình không? | Test tích hợp với scheduler |

`sendPartialResultOnExpiry(true)` chọn cách xử lý khi hết hạn; riêng tùy chọn này không tạo ra lịch hết hạn. Khi cấu hình, phân biệt thêm việc giữ dấu vết nhóm và xóa hẳn nhóm. Các API nằm trong [CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html).

Không viết mọi test theo dạng gửi thông điệp, `Thread.sleep(1000)` rồi kiểm tra. Kiểu đó vừa kéo dài suite vừa phụ thuộc tải máy.

### 6.2. Test chính sách bằng một adapter chỉ có trong test

Lớp dưới đây mở một phương thức gọi `forceComplete` được bảo vệ của handler. Nó dùng aggregator thật, store thật trong bộ nhớ và queue thật; chỉ chủ động kích hoạt sự kiện kết thúc nhóm.

Đây là kiểm thử chính sách, không đi qua callback chọn nhóm cũ của store và không kiểm thử thời điểm scheduler chạy. `forceComplete` là điểm mở rộng `protected`; adapter chỉ đặt trong mã test và cần được đối chiếu khi nâng phiên bản. Xem [API AbstractCorrelatingMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html).

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.aggregator.AggregatingMessageHandler;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class AggregatorExpiryPolicyTest {

    @Test
    void expiryCanProduceAPartialResult() {
        verifyExpiry(true);
    }

    @Test
    void expiryCanDiscardTheIncompleteGroup() {
        verifyExpiry(false);
    }

    private void verifyExpiry(boolean partialResult) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            TestAggregator handler = context.getBean(TestAggregator.class);
            SimpleMessageStore store =
                    context.getBean(SimpleMessageStore.class);
            QueueChannel results =
                    context.getBean("results", QueueChannel.class);
            QueueChannel discarded =
                    context.getBean("discarded", QueueChannel.class);

            handler.setSendPartialResultOnExpiry(partialResult);

            UUID groupId = UUID.randomUUID();
            handler.handleMessage(part(groupId, 1, 3, 10));
            handler.handleMessage(part(groupId, 2, 3, 20));

            assertNull(results.receive(0));
            assertEquals(2, store.getMessageGroup(groupId).size());

            handler.expireNow(groupId);

            if (partialResult) {
                Message<?> output = results.receive(0);
                assertNotNull(output);
                assertEquals(30, output.getPayload());
                assertNull(results.receive(0));
                assertNull(discarded.receive(0));
            }
            else {
                assertNull(results.receive(0));
                Message<?> first = discarded.receive(0);
                Message<?> second = discarded.receive(0);
                assertNotNull(first);
                assertNotNull(second);
                int sum = (Integer) first.getPayload()
                        + (Integer) second.getPayload();
                assertEquals(30, sum);
                assertNull(discarded.receive(0));
            }

            assertEquals(0, store.getMessageGroupCount());
            assertEquals(0, store.getMessageCountForAllMessageGroups());
        }
    }

    private static Message<Integer> part(
            UUID groupId, int number, int size, int payload) {
        return MessageBuilder.withPayload(payload)
                .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupId)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        number)
                .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        size)
                .build();
    }

    static class TestAggregator extends AggregatingMessageHandler {

        private final SimpleMessageStore store;

        TestAggregator(SimpleMessageStore store) {
            super(group -> group.getMessages().stream()
                    .mapToInt(message -> (Integer) message.getPayload())
                    .sum(), store);
            this.store = store;
        }

        void expireNow(Object groupId) {
            forceComplete(this.store.getMessageGroup(groupId));
        }
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        SimpleMessageStore store() {
            return new SimpleMessageStore();
        }

        @Bean
        QueueChannel results() {
            return new QueueChannel();
        }

        @Bean
        QueueChannel discarded() {
            return new QueueChannel();
        }

        @Bean
        TestAggregator aggregator() {
            TestAggregator handler = new TestAggregator(store());
            handler.setOutputChannel(results());
            handler.setDiscardChannel(discarded());
            handler.setDiscardIndividuallyOnExpiry(true);
            handler.setExpireGroupsUponTimeout(true);
            return handler;
        }
    }
}
~~~

Kỳ vọng `getMessageGroupCount() == 0` ở đây có cơ sở vì fixture đặt rõ `expireGroupsUponTimeout(true)`. Nó khác fixture giữ nhóm sau hoàn tất bình thường ở phần trước.

Cấu hình `setDiscardIndividuallyOnExpiry(true)` chỉ rõ mỗi thông điệp hết hạn được gửi riêng sang discard. Vì không dựa vào thứ tự duyệt store, test cộng payload của hai thông điệp đã nhận thay vì đòi thông điệp `10` luôn đến trước `20`.

### 6.3. Bổ sung một test thật với scheduler

Để kiểm tra dây nối thời gian trong ứng dụng, tạo fixture riêng, ví dụ:

~~~java
.aggregate(spec -> spec
        .messageStore(timeoutStore)
        .groupTimeout(200)
        .sendPartialResultOnExpiry(true)
        .expireGroupsUponTimeout(true))
~~~

`timeoutStore` là store dành riêng cho aggregator đó. Trong một context bật integration, bảo đảm scheduler của flow hoạt động. Gửi hai phần có `sequenceSize = 3`, rồi chờ:

~~~java
Message<?> output = results.receive(5_000);
assertNotNull(output);
assertEquals(30, output.getPayload());
~~~

`5_000` là giới hạn chờ của test, không phải giá trị timeout nghiệp vụ. Nếu cần xác nhận không có kết quả thứ hai, dùng thêm một khoảng quan sát hữu hạn phù hợp với fixture; kiểm tra tức thời không chứng minh được tương lai không có thông điệp.

Thêm test trường hợp nhóm nhận đủ ba phần trước thời hạn. Nhóm phải phát một kết quả đầy đủ; tác vụ timeout còn lại không được gây kết quả lặp. Với yêu cầu kiểm tra ranh giới thời gian chính xác, dùng scheduler điều khiển được thay vì assertion dựa vào số mili giây thực tế.

Khi chọn cơ chế dọn bằng reaper, `MessageGroupStoreReaper.run()` là điểm kích hoạt quét store; test có thể chủ động chạy nó sau khi chuẩn bị tuổi nhóm. Xem [API MessageGroupStoreReaper](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStoreReaper.html). Test trực tiếp `forceComplete` ở trên không thay thế phép kiểm tra lựa chọn nhóm đủ tuổi của reaper.

## 7. Các trường hợp biên cần thiết kế riêng

### 7.1. Phần tử trùng: phân biệt ID thông điệp và số thứ tự

Hai tình huống sau không tương đương:

~~~java
Message<Integer> original = part(groupId, 1, 3, 10);

// Gửi lại đúng đối tượng, giữ nguyên MessageHeaders.ID.
aggregateInput.send(original);
aggregateInput.send(original);

// Hai thông điệp mới: cùng sequence number, khác ID.
aggregateInput.send(part(groupId, 1, 3, 10));
aggregateInput.send(part(groupId, 1, 3, 10));
~~~

Store có thể đối xử khác với hai trường hợp này. Không dùng trường hợp đầu để kết luận hệ thống loại trùng nghiệp vụ trong trường hợp sau.

`SimpleSequenceSizeReleaseStrategy` so sánh số phần trong nhóm với kích thước dự kiến, không bảo đảm kiểm tra sequence number bị trùng. Vì thế, một tổng đúng trong kịch bản không trùng không chứng minh tính idempotent. Xem [API SimpleSequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SimpleSequenceSizeReleaseStrategy.html).

Nếu cần chặn sequence trùng trong một nhóm, có thể đánh giá `SequenceSizeReleaseStrategy` với handler tương ứng; API này có cơ chế hỗ trợ phát hiện sequence trùng. Vẫn cần test cấu hình thực tế. Xem [API SequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html).

Một bộ dữ liệu kiểm thử phù hợp:

| Bước | Sequence number | Payload | Kỳ vọng nếu hợp đồng yêu cầu loại trùng |
|---|---|---|---|
| 1 | `1/3` | `10` | Chưa release |
| 2 | `1/3`, message ID mới | `10` | Chưa release, không tính thêm vào tổng |
| 3 | `2/3` | `20` | Chưa release |
| 4 | `3/3` | `30` | Phát đúng một kết quả `60` |

Nếu cùng khóa phần tử nhưng payload khác, ví dụ hai phần `1/3` lần lượt là `10` và `99`, phải quyết định rõ: giữ bản đầu, bản sau hay báo xung đột. Release strategy không tự định nghĩa đầy đủ chính sách nghiệp vụ này.

Với dữ liệu đến từ broker, khóa chống trùng thường cần bao gồm định danh nghiệp vụ của yêu cầu và của phần tử. Kiểm thử thêm việc gửi lại toàn bộ yêu cầu sau khi nhóm cũ đã bị xóa, vì lúc đó aggregator có thể nhận một nhóm mới.

### 7.2. Có filter giữa splitter và aggregator

Ví dụ splitter tạo ba phần nhưng filter loại một phần:

~~~text
sequenceSize = 3
       ↓
10 → giữ
20 → loại
30 → giữ
       ↓
aggregator chỉ nhận 2 phần
~~~

Hãy tạo test gửi `[1, 2, 3]` vào flow có filter rồi quan sát:

1. Có hai phần được chuyển tới aggregator.
2. Một phần được chuyển vào discard của filter theo cấu hình.
3. Nhóm chưa phát kết quả đầy đủ.
4. Chính sách xử lý nhóm thiếu được kích hoạt theo thiết kế.

Từ hợp đồng cần có ba kết quả, việc chỉ nhận hai phần không đủ để coi là hoàn tất. Có thể chọn trả thông điệp bù biểu diễn một phần bị từ chối, tính tổng số phần hợp lệ trước khi tách hoặc dùng điều kiện release nghiệp vụ khác. Mỗi lựa chọn cần có test phân biệt “đủ kết quả” với “đã xử lý xong tất cả phần”.

Không sửa `sequenceSize` tùy ý ở một vài thông điệp chỉ để test xanh; metadata cần nhất quán với thiết kế của toàn nhóm.

### 7.3. Iterator hoặc nguồn chưa biết kích thước

Với nguồn không xác định được tổng số phần, `sequenceSize` có thể là `0`. Hãy assert giá trị header thực tế trước khi kiểm thử release, thay vì giả định nó luôn bằng số phần đã nhận.

Nếu hợp đồng không có tổng số phần, cần một tín hiệu kết thúc, metadata tổng số từ nguồn hoặc chính sách kết thúc theo thời gian. Dùng cùng dữ liệu nghiệp vụ để thử cả đầu vào `List` và nguồn không biết kích thước, nhưng viết kỳ vọng release theo hợp đồng từng nguồn. Xem thêm [xử lý Iterator của splitter](https://docs.spring.io/spring-integration/reference/6.5/splitter.html#splitter-iterators).

### 7.4. Đầu vào rỗng và splitter trả null

Bộ test chính chủ động cấu hình discard cho đầu vào rỗng. Không có phần nào được gửi tới aggregator nên không thể kỳ vọng aggregator tự tạo tổng `0`.

Nếu nghiệp vụ cần trả về đơn hàng rỗng, có thể route đầu vào rỗng sang nhánh tạo kết quả riêng trước splitter và kiểm tra nhánh đó.

Không gộp trường hợp container rỗng với hàm splitter trả `null`. Tùy chọn discard của splitter áp dụng cho kết quả rỗng có thể duyệt, không phải một quy tắc chung cho mọi giá trị `null`. Xem [API SplitterSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/SplitterSpec.html).

### 7.5. Kết quả cần đúng thứ tự

Phép cộng trong ví dụ không quan tâm thứ tự. Nếu kết quả là danh sách có vị trí nghiệp vụ, hãy định nghĩa thứ tự ngay trong output processor, chẳng hạn sắp theo sequence number:

~~~java
.outputProcessor(group -> group.getMessages().stream()
        .sorted(java.util.Comparator.comparingInt(message ->
                message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        Integer.class)))
        .map(Message::getPayload)
        .toList())
~~~

Đoạn này giả định header sequence có mặt và hợp lệ. Gửi các phần theo thứ tự `3, 1, 2` rồi assert danh sách kết quả là `[10, 20, 30]`. Không lấy thứ tự lặp của một store làm hợp đồng nghiệp vụ.

Nếu cần phát từng thông điệp theo thứ tự thay vì tạo một kết quả tổng hợp, hãy đánh giá resequencer. Test cần phản ánh kiểu đầu ra mà ứng dụng thật sử dụng.

## 8. Kiểm thử lỗi ở đoạn xử lý từng phần

Giả sử transformer của phần tử `2` ném ngoại lệ. Có hai câu hỏi cần tách:

- Ngoại lệ được chuyển tới người gọi hoặc kênh lỗi nào?
- Phần xử lý lỗi có tạo một kết quả bù để nhóm tiếp tục hoàn tất không?

### 8.1. Với flow đồng bộ

Tạo fixture riêng với một transformer thất bại có chủ đích:

~~~java
.transform(Integer.class, value -> {
    if (value == 2) {
        throw new IllegalStateException("Cannot process item 2");
    }
    return value * 10;
})
~~~

Khi gửi qua kênh trực tiếp, kiểm tra exception theo hợp đồng endpoint; ngoại lệ nghiệp vụ có thể được bọc trong exception của hệ thống messaging. Không assert nguyên văn toàn bộ stack trace hoặc mọi lớp bọc nếu ứng dụng không cam kết chúng.

Trong luồng đồng bộ không có advice phục hồi của ví dụ, lỗi ở phần thứ hai có thể làm lần gửi danh sách dừng trước khi phần thứ ba được gửi. Hãy kiểm tra số phần thực tế đã tới aggregator, nhóm còn thiếu gì và cách dọn nhóm đó.

Không mặc định một lần gửi có splitter là một giao dịch nguyên tử bao phủ mọi phần đã đi qua luồng.

### 8.2. Với flow bất đồng bộ

Dùng kênh lỗi quan sát được và chờ `ErrorMessage` bằng thời hạn hữu hạn. Kiểm tra:

- Nguyên nhân nghiệp vụ cuối cùng của lỗi.
- Thông điệp bị lỗi và định danh yêu cầu hoặc phần tử.
- Số kết quả đã phát và trạng thái của nhóm.
- Kết quả sau retry, recovery hoặc thông điệp bù nếu có.

Chỉ assertion “`send()` không ném exception” không chứng minh worker bất đồng bộ thành công. Cần chờ cả kết quả và lỗi theo hợp đồng của flow. Cơ chế lỗi phụ thuộc executor, poller và error handler được cấu hình; không phải mọi executor tùy chỉnh đều tự có cùng chính sách xuất lỗi.

### 8.3. Gateway timeout không đồng nghĩa aggregator đã được dọn

Nếu ứng dụng dùng messaging gateway để đợi kết quả, thời hạn chờ reply của gateway là hợp đồng phía người gọi. Nhóm đang giữ trong aggregator là trạng thái phía luồng xử lý.

Viết test riêng cho tình huống gateway hết thời gian chờ nhưng nhóm vẫn thiếu phần tử. Sau đó kiểm tra chính sách timeout hoặc dọn store của aggregator. Không xem việc người gọi thôi chờ là bằng chứng nhóm đã kết thúc.

## 9. Cô lập dịch vụ ngoài mà vẫn giữ splitter-aggregator thật

Khi flow có lời gọi tính giá qua HTTP, mục tiêu của test splitter-aggregator thường là kiểm tra số lần gọi, metadata và cách gom kết quả. Hãy gán ID rõ ràng cho endpoint của dịch vụ ngoài, rồi dùng `MockIntegrationContext` để thay handler của endpoint đó trong test.

Một trình tự phù hợp:

1. Nạp flow thật và bật `@SpringIntegrationTest`.
2. Thay handler ở endpoint tính giá bằng một handler test có trả reply.
3. Gửi một yêu cầu nhiều phần vào đầu vào thật.
4. Kiểm tra mọi phần đã được xử lý với dữ liệu dự kiến.
5. Kiểm tra aggregator thật phát kết quả đúng.
6. Khôi phục endpoint bằng `resetBeans()` sau test.

`substituteMessageHandlerFor` nhận tên **endpoint consumer**, không phải tên channel và không phải một ID handler tự suy đoán. Nếu dùng Mockito thuần cho một handler trả lời, phải cấu hình phản hồi thích hợp; một handler chỉ đếm lời gọi mà không trả kết quả có thể khiến nhóm thiếu phần tử.

Không thay aggregator bằng mock rồi tuyên bố đã kiểm chứng release strategy. Phép kiểm tra đó chỉ cho thấy đoạn trước aggregator đã gửi dữ liệu tới nơi mong đợi.

## 10. Kiểm thử đồng thời và store bền vững

### 10.1. Kiểm thử đồng thời

Test các phần đến theo thứ tự `3, 1, 2` là test thứ tự đến, chưa phải test nhiều luồng thực thi cùng lúc.

Khi ứng dụng thật xử lý song song, bổ sung fixture có executor được quản lý và đóng sau test. Dùng latch hoặc barrier để điều phối các worker tới điểm cần cạnh tranh; chờ các future với timeout, rồi kiểm tra output.

Các bất biến nên giữ trong một nhóm:

- Đúng số kết quả theo hợp đồng.
- Không mất phần tử hợp lệ.
- Không trộn correlation giữa hai yêu cầu.
- Không phát lại kết quả khi có thông điệp đến muộn.
- Không để nhóm chưa hoàn tất tồn tại ngoài chính sách lưu giữ.

Không dùng `Thread.sleep` để tạo điều kiện tranh chấp “có lẽ sẽ xảy ra”. Khi test thất bại, cần có dữ liệu nhóm, sequence và nguyên nhân worker để tái hiện.

### 10.2. Kiểm thử với persistent MessageGroupStore

`SimpleMessageStore` là store trong bộ nhớ, phù hợp với ví dụ cô lập. Nó không chứng minh hành vi khi quá trình ứng dụng dừng rồi khởi động lại. Xem [API SimpleMessageStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/SimpleMessageStore.html).

Với store bền vững, một kịch bản tích hợp có giá trị là:

1. Khởi tạo store và aggregator thứ nhất.
2. Gửi phần `1/3` và `2/3`, xác nhận dữ liệu đã lưu.
3. Mô phỏng điều kiện khởi động lại theo mục tiêu test.
4. Khởi tạo aggregator mới trỏ tới cùng dữ liệu.
5. Gửi phần `3/3`.
6. Xác nhận kết quả và dữ liệu còn lại trong store.

Phân biệt dừng ứng dụng có trật tự với tiến trình bị ngắt đột ngột: lifecycle khi đóng có thể tác động tới nhóm. Kịch bản kiểm thử phục hồi cần ghi rõ điều kiện nào được mô phỏng.

Dùng định danh nhóm ổn định, cấu hình transaction và serialization tương ứng với hệ thống thật. Khi nhiều instance cùng làm việc, cần kiểm thử cơ chế khóa phù hợp; kết quả từ một store trong bộ nhớ ở một JVM không bao phủ trường hợp đó.

Khi dùng cơ chế expire qua callback, dành store logic riêng cho từng aggregator để tránh một endpoint tác động tới nhóm của endpoint khác. Có thể cùng dùng hạ tầng lưu trữ vật lý nếu cấu hình phân vùng của implementation cho phép.

## 11. Ma trận kiểm thử để chọn theo hợp đồng nghiệp vụ

| Tình huống | Dữ liệu tạo ra | Kỳ vọng trọng tâm |
|---|---|---|
| Một phần tử | List có một phần | Một phần có sequence `1/1`; một kết quả |
| Nhiều phần hợp lệ | List có ba phần | Đủ header, đúng payload và đúng một kết quả |
| Chưa đủ phần | `1/3` rồi `2/3` | Chưa release; nhóm có hai phần |
| Sai thứ tự đến | `3/3`, `1/3`, `2/3` | Release sau khi đủ; thứ tự đầu ra theo hợp đồng |
| Hai nhóm xen kẽ | A1, B1, A2, B2 | Kết quả A và B tách biệt |
| List rỗng | Không có phần | Nhánh rỗng hoặc discard được xử lý rõ ràng |
| Một phần bị filter | Chỉ hai trong ba phần tới aggregator | Không giả vờ hoàn tất; áp dụng chính sách nhóm thiếu |
| Sequence trùng | Cùng số thứ tự, ID khác nhau | Theo chính sách chống trùng hoặc báo xung đột |
| Phần tới muộn | Gửi sau khi nhóm hoàn tất | Discard hoặc mở nhóm mới theo cấu hình |
| Hết hạn, cho phép kết quả một phần | Thiếu một phần | Kết quả một phần và trạng thái store đúng |
| Hết hạn, không cho phép kết quả một phần | Thiếu một phần | Discard đúng dữ liệu; không có kết quả bình thường |
| Transformer thất bại | Một phần gây exception | Lỗi quan sát được và nhóm thiếu có hướng xử lý |
| Xử lý song song | Nhiều worker cùng gửi | Không mất, trộn hoặc phát lặp ngoài hợp đồng |
| Khởi động lại | Store giữ một phần dữ liệu | Phục hồi đúng theo chính sách vận hành |

Đây là danh sách lựa chọn theo thiết kế, không phải yêu cầu đưa mọi tình huống vào một test duy nhất. Mỗi test nên có một lý do thất bại dễ giải thích.

## 12. Cách chẩn đoán khi test không nhận được kết quả

Đi từ điểm quan sát gần lỗi nhất:

1. **Splitter có thực sự phát phần tử không?** Kiểm tra payload đầu vào, kết quả rỗng và số phần.
2. **Header có còn đầy đủ trước aggregator không?** Đối chiếu correlation, sequence number và sequence size.
3. **Nhóm có đúng khóa không?** Hai khóa nhìn giống nhau trong log có thể khác kiểu dữ liệu.
4. **Nhóm có bị xem là hoàn tất từ lần xử lý trước không?** Xem trạng thái và nhánh discard.
5. **Release strategy có phù hợp với dữ liệu không?** Đặc biệt với filter và nguồn không biết kích thước.
6. **Có exception ở đoạn giữa không?** Kiểm tra exception của lần gửi hoặc kênh lỗi.
7. **Test có lấy mất phần tử khỏi kênh trung gian không?** Xem queue và các consumer.
8. **Nếu dùng timeout, scheduler đã chạy chưa?** Phân biệt lỗi lịch với lỗi chính sách hết hạn.

Khi xem store, ưu tiên kiểm tra theo group ID cụ thể. `getMessageGroupCount()` và `getMessageCountForAllMessageGroups()` trả lời hai câu hỏi khác nhau; số nhóm không bằng số thông điệp. Các thao tác hết hạn và thống kê được mô tả trong [MessageGroupStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageGroupStore.html).

Một test splitter-aggregator hữu ích cho thấy dữ liệu thuộc nhóm nào, khi nào được release, đi tới đầu ra nào và còn trạng thái gì sau xử lý. Đó là cơ sở để mở rộng luồng bằng router, filter, gateway hoặc xử lý lỗi mà vẫn giữ được hợp đồng tích hợp.
