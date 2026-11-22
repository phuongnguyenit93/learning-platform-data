# Kiểm thử Splitter và Aggregator theo correlation

## 1. Bài toán và mục tiêu

Trong **Enterprise Integration Patterns (EIP)**, **Splitter** tách một message thành nhiều message con; **Aggregator** thu thập các message liên quan và phát kết quả khi một nhóm đã đủ điều kiện hoàn tất. Hai pattern thường đi cùng nhau trong Spring Integration, nhưng không nhất thiết nằm sát nhau: giữa chúng có thể là Transformer, Filter, Router, Service Activator hoặc xử lý bất đồng bộ.

Điểm khó không chỉ là kiểm tra số message. Nếu hai yêu cầu được xử lý đồng thời, Aggregator cần biết **message nào thuộc cùng một yêu cầu**. Nếu không kiểm thử correlation, một luồng có thể chạy đúng với một đơn hàng nhưng trộn dữ liệu khi nhận nhiều đơn hàng xen kẽ.

Bài này thuộc chương **Kiểm thử pattern** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng bằng Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử và theo dõi đường đi của message. Ở đây, chúng ta tập trung vào việc **chứng minh dữ liệu được tách đúng, gắn nhóm đúng, ghép đúng và phát kết quả đúng thời điểm**.

Sau bài học, bạn có thể:

1. Xác định payload và các headers cần kiểm tra khi Splitter tạo message con.
2. Kiểm tra \`correlationId\`, \`sequenceNumber\` và \`sequenceSize\` theo đúng hợp đồng của flow.
3. Chứng minh Aggregator chờ đủ message trước khi phát kết quả.
4. Dùng hai nhóm gửi xen kẽ để phát hiện lỗi ghép lẫn nhóm.
5. Viết flow test với JUnit 5, Spring Integration Java DSL và channel trong bộ nhớ.
6. Thiết kế test bổ sung cho message thiếu, trùng, sai thứ tự, timeout và retry.

## 2. Correlation là gì trong một luồng Splitter → Aggregator?

Giả sử request \`R-A\` có hai dòng hàng \`["A1", "A2"]\`. Splitter tạo hai message; cả hai phải được nhận diện là thành viên của cùng một nhóm. Request \`R-B\` cũng có hai dòng hàng \`["B1", "B2"]\`, nhưng là **nhóm khác**.

~~~mermaid
flowchart TD
    A["Request A: [A1, A2]"] --> SA["Splitter A"]
    B["Request B: [B1, B2]"] --> SB["Splitter B"]
    SA --> A1["A1 / correlation=A / seq=1/2"]
    SA --> A2["A2 / correlation=A / seq=2/2"]
    SB --> B1["B1 / correlation=B / seq=1/2"]
    SB --> B2["B2 / correlation=B / seq=2/2"]
    A1 --> AGG["Aggregator"]
    B1 --> AGG
    B2 --> AGG
    A2 --> AGG
    AGG --> OA["Kết quả A: [A1, A2]"]
    AGG --> OB["Kết quả B: [B1, B2]"]
~~~

Trong Spring Integration, các header liên quan thường được truy cập qua \`IntegrationMessageHeaderAccessor\`:

| Header | Ý nghĩa trong ví dụ | Assertion hữu ích |
| --- | --- | --- |
| \`correlationId\` | Khóa định danh một nhóm | Hai phần tử cùng nhóm có cùng khóa; hai nhóm khác khóa |
| \`sequenceNumber\` | Vị trí của phần tử trong nhóm, thường bắt đầu từ 1 | Với nhóm hai phần tử, có đủ các vị trí 1 và 2 |
| \`sequenceSize\` | Số phần tử dự kiến trong nhóm | Hai message con đều có giá trị 2 |
| \`requestId\` | Khóa theo dõi nghiệp vụ do ứng dụng đặt | Được giữ nếu flow yêu cầu, không dùng thay correlation ngầm định |
| \`id\`, \`timestamp\` | Metadata do framework quản lý | Chỉ kiểm tra khi thật sự cần; tránh giá trị UUID/timestamp cố định |

**Đừng đánh đồng correlation với sequence.** \`correlationId\` trả lời *thuộc nhóm nào?*; \`sequenceNumber\` trả lời *ở vị trí nào?*; \`sequenceSize\` trả lời *dự kiến có bao nhiêu phần tử?*. Nếu hai message có cùng \`sequenceNumber=1\` nhưng khác correlation, chúng vẫn có thể thuộc hai nhóm hợp lệ khác nhau.

Một Splitter tiêu chuẩn tạo sequence headers khi cấu hình áp dụng sequence. Khi Splitter tạo nhóm từ message đầu vào, correlation thường dựa trên định danh message nguồn. Tuy nhiên, **không nên mặc định một correlation ID cụ thể** trong test nếu code không tự đặt; điều cần chứng minh là sự nhất quán của các message cùng nhóm.

## 3. Xác định các hợp đồng phải kiểm thử

Trước khi viết Java, mô tả từng ranh giới:

~~~text
Request:
  payload   = ["A1", "A2"]
  requestId = "r-A"

Sau Splitter:
  message #1: payload="A1", correlation=G, sequenceNumber=1, sequenceSize=2
  message #2: payload="A2", correlation=G, sequenceNumber=2, sequenceSize=2

Tại Aggregator:
  đã nhận #1/2  -> chưa có output
  đã nhận #2/2  -> có một output chứa ["A1", "A2"]
~~~

| Kịch bản | Input nhỏ nhất | Điều phải chứng minh |
| --- | --- | --- |
| Splitter cơ bản | Một list gồm hai phần tử | Hai output, đúng payload, đủ sequence |
| Giữ metadata nghiệp vụ | Một list và \`requestId\` | Cả hai message con giữ \`requestId\` nếu hợp đồng yêu cầu |
| Aggregator đợi đủ nhóm | Hai message có correlation giống nhau, size 2 | Chưa có output khi mới nhận một message |
| Aggregator hoàn tất nhóm | Message thứ hai của nhóm | Có một kết quả, không phát thêm |
| Tách biệt correlation | Nhóm A hai phần tử, nhóm B hai phần tử | Không trộn A với B khi gửi xen kẽ |
| Kiểm tra toàn luồng | Một message list đi qua Splitter rồi Aggregator | Một kết quả với đủ payload, không mất/thừa phần tử |
| Sai correlation | Một phần tử mang correlation khác | Không được tính vào nhóm còn thiếu |
| Lỗi hoặc thiếu phần tử | Một nhóm chỉ nhận phần tử đầu | Chính sách timeout, giữ nhóm hoặc phát partial result phải rõ |

**Số lượng message tối thiểu phụ thuộc mục tiêu kiểm thử.** Hai phần tử đủ để chứng minh hành vi split/aggregate cơ bản; **bốn message thuộc hai correlation khác nhau** mới đủ làm lộ lỗi trộn nhóm.

## 4. Dựng môi trường flow test

Các ví dụ sử dụng **Java 17, JUnit 5, AssertJ và Spring Integration Java DSL 6.x**. Chúng dùng \`DirectChannel\` mặc định và \`QueueChannel\` làm đầu ra quan sát nên không cần Kafka, RabbitMQ, HTTP server hoặc database.

Với dự án Spring Boot, có thể sử dụng các dependency tương thích:

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

Để dễ xác định lỗi, tạo **ba flow độc lập trong cùng context**:

~~~mermaid
flowchart LR
    S1["split.in"] --> S2["Splitter"] --> S3["split.out"]
    A1["aggregate.in"] --> A2["Aggregator"] --> A3["aggregate.out"]
    E1["roundtrip.in"] --> E2["Splitter"] --> E3["Aggregator"] --> E4["roundtrip.out"]
~~~

- Flow thứ nhất giúp nhìn trực tiếp **payload và sequence headers sau Splitter**.
- Flow thứ hai cho phép tự gửi **các message có correlation xác định** để kiểm tra Aggregator.
- Flow thứ ba kiểm tra **tương tác Splitter → Aggregator** như một pipeline hoàn chỉnh.

Đây là cách tổ chức bài test, không phải yêu cầu phải tạo ba flow trùng lặp trong production.

## 5. Ví dụ Java hoàn chỉnh: ba nhóm test

Tạo file \`src/test/java/example/SplitAggregateCorrelationTest.java\`:

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

@SpringJUnitConfig(SplitAggregateCorrelationTest.Flows.class)
class SplitAggregateCorrelationTest {

    @Autowired
    ApplicationContext context;

    private MessageChannel input(String name) {
        return context.getBean(name, MessageChannel.class);
    }

    private QueueChannel output(String name) {
        return context.getBean(name, QueueChannel.class);
    }

    private Message<?> receive(String name) {
        Message<?> result = output(name).receive(1_000);
        assertThat(result)
                .as("Expected a message on channel %s", name)
                .isNotNull();
        return result;
    }

    private static Message<String> part(
            String groupId, int position, int size, String payload) {
        return MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        groupId)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        position)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        size)
                .build();
    }

    private static List<String> items(Message<?> aggregated) {
        assertThat(aggregated.getPayload()).isInstanceOf(List.class);
        return ((List<?>) aggregated.getPayload()).stream()
                .map(String.class::cast)
                .toList();
    }

    @Test
    void splitter_produces_two_correlated_messages() {
        Message<List<String>> request = MessageBuilder
                .withPayload(List.of("A1", "A2"))
                .setHeader("requestId", "r-A")
                .build();

        assertThat(input("split.in").send(request)).isTrue();

        Message<?> first = receive("split.out");
        Message<?> second = receive("split.out");

        assertThat(List.of(first.getPayload(), second.getPayload()))
                .containsExactlyInAnyOrder("A1", "A2");
        assertThat(first.getHeaders().get("requestId")).isEqualTo("r-A");
        assertThat(second.getHeaders().get("requestId")).isEqualTo("r-A");

        Object correlation = first.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID);
        assertThat(correlation).isNotNull();
        assertThat(second.getHeaders().get(
                IntegrationMessageHeaderAccessor.CORRELATION_ID))
                .isEqualTo(correlation);

        assertThat(List.of(
                first.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER),
                second.getHeaders().get(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER)))
                .containsExactlyInAnyOrder(1, 2);
        assertThat(first.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE)).isEqualTo(2);
        assertThat(second.getHeaders().get(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE)).isEqualTo(2);

        assertThat(output("split.out").receive(0)).isNull();
    }

    @Test
    void aggregator_waits_until_group_is_complete() {
        input("aggregate.in").send(part("group-1", 1, 2, "A1"));

        // Chỉ có một trong hai phần tử: không được release.
        assertThat(output("aggregate.out").receive(0)).isNull();

        input("aggregate.in").send(part("group-1", 2, 2, "A2"));

        Message<?> result = receive("aggregate.out");
        assertThat(items(result)).containsExactlyInAnyOrder("A1", "A2");
        assertThat(output("aggregate.out").receive(0)).isNull();
    }

    @Test
    void aggregator_does_not_mix_interleaved_groups() {
        input("aggregate.in").send(part("group-A", 1, 2, "A1"));
        input("aggregate.in").send(part("group-B", 1, 2, "B1"));
        assertThat(output("aggregate.out").receive(0)).isNull();

        // B hoàn tất trước; A vẫn thiếu A2.
        input("aggregate.in").send(part("group-B", 2, 2, "B2"));
        Message<?> resultB = receive("aggregate.out");
        assertThat(items(resultB)).containsExactlyInAnyOrder("B1", "B2");
        assertThat(output("aggregate.out").receive(0)).isNull();

        input("aggregate.in").send(part("group-A", 2, 2, "A2"));
        Message<?> resultA = receive("aggregate.out");
        assertThat(items(resultA)).containsExactlyInAnyOrder("A1", "A2");
        assertThat(output("aggregate.out").receive(0)).isNull();
    }

    @Test
    void two_batches_from_splitter_have_distinct_correlation() {
        input("split.in").send(MessageBuilder
                .withPayload(List.of("A1", "A2")).build());
        Message<?> a1 = receive("split.out");
        Message<?> a2 = receive("split.out");

        input("split.in").send(MessageBuilder
                .withPayload(List.of("B1", "B2")).build());
        Message<?> b1 = receive("split.out");
        Message<?> b2 = receive("split.out");

        String header = IntegrationMessageHeaderAccessor.CORRELATION_ID;
        Object groupA = a1.getHeaders().get(header);
        Object groupB = b1.getHeaders().get(header);

        assertThat(groupA).isNotNull();
        assertThat(groupB).isNotNull();
        assertThat(a2.getHeaders().get(header)).isEqualTo(groupA);
        assertThat(b2.getHeaders().get(header)).isEqualTo(groupB);
        assertThat(groupA).isNotEqualTo(groupB);
        assertThat(output("split.out").receive(0)).isNull();
    }

    @Test
    void roundtrip_splits_and_aggregates_one_batch() {
        input("roundtrip.in").send(MessageBuilder
                .withPayload(List.of("SKU-1", "SKU-2", "SKU-3"))
                .setHeader("requestId", "request-42")
                .build());

        Message<?> result = receive("roundtrip.out");
        assertThat(items(result))
                .containsExactlyInAnyOrder("SKU-1", "SKU-2", "SKU-3");
        assertThat(output("roundtrip.out").receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class Flows {

        @Bean("split.out")
        QueueChannel splitOutput() {
            return new QueueChannel();
        }

        @Bean("aggregate.out")
        QueueChannel aggregateOutput() {
            return new QueueChannel();
        }

        @Bean("roundtrip.out")
        QueueChannel roundtripOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow splitOnly() {
            return IntegrationFlow.from("split.in")
                    .split()
                    .channel("split.out")
                    .get();
        }

        @Bean
        IntegrationFlow aggregateOnly() {
            return IntegrationFlow.from("aggregate.in")
                    .aggregate()
                    .channel("aggregate.out")
                    .get();
        }

        @Bean
        IntegrationFlow splitAndAggregate() {
            return IntegrationFlow.from("roundtrip.in")
                    .split()
                    .aggregate()
                    .channel("roundtrip.out")
                    .get();
        }
    }
}
~~~

Phép kiểm tra \`roundtrip\` không yêu cầu danh sách kết quả giữ thứ tự vì hợp đồng ở đây chỉ là **đủ ba phần tử, không thiếu và không thừa**. Khi sản phẩm có yêu cầu thứ tự, hãy cấu hình cơ chế bảo toàn/sắp xếp thích hợp và viết test riêng cho thứ tự; chỉ dựa vào hành vi quan sát ở một lần chạy là chưa đủ.

### Cách đọc kết quả từng test

1. \`splitter_produces_two_correlated_messages\` kiểm tra đúng **hai** message, payload từng phần tử, hai sequence number, cùng correlation và header nghiệp vụ \`requestId\`.
2. \`aggregator_waits_until_group_is_complete\` chứng minh Aggregator **không phát kết quả sớm** sau phần tử thứ nhất; khi nhận phần tử thứ hai, nó phát **đúng một** message nhóm.
3. \`aggregator_does_not_mix_interleaved_groups\` gửi A1, B1, B2, A2; kết quả B đến trước A, nhưng không chứa phần tử của A. Đây là test trực tiếp nhất cho correlation.
4. \`two_batches_from_splitter_have_distinct_correlation\` chứng minh hai request độc lập tạo hai khóa nhóm khác nhau khi sử dụng splitter tiêu chuẩn tạo sequence.
5. \`roundtrip_splits_and_aggregates_one_batch\` chứng minh việc nối hai pattern hoạt động và kết quả giữ đủ phần tử.

**Vì sao không so sánh \`correlationId\` với UUID viết sẵn?** Splitter có thể tạo correlation từ message nguồn. Khi không tự đặt khóa nhóm, test nên kiểm tra *cùng nhóm bằng nhau, khác nhóm khác nhau*. Điều này giữ test ổn định khi ID do framework tạo ngẫu nhiên.

**Vì sao kiểm tra \`sequenceSize=2\`?** Default release strategy của Aggregator thường dựa trên sequence metadata để quyết định nhóm đã đủ phần tử. Nếu message khai báo \`sequenceSize=3\` nhưng mới có hai phần tử, Aggregator có thể tiếp tục đợi dù dữ liệu nghiệp vụ nghĩ nhóm đã hoàn tất.

## 6. Kiểm thử sự thay đổi thứ tự nhận message

Trong hệ thống thực tế, hai message có thể đến Aggregator không theo thứ tự 1 rồi 2. Khi dùng ExecutorChannel, broker hoặc xử lý song song, phần tử \`sequenceNumber=2\` có thể về trước \`sequenceNumber=1\`.

Test tình huống này bằng một nhóm riêng:

~~~java
@Test
void aggregator_accepts_out_of_order_fragments() {
    input("aggregate.in").send(part("group-reverse", 2, 2, "second"));
    assertThat(output("aggregate.out").receive(0)).isNull();

    input("aggregate.in").send(part("group-reverse", 1, 2, "first"));
    Message<?> result = receive("aggregate.out");

    assertThat(items(result))
            .containsExactlyInAnyOrder("first", "second");
    assertThat(output("aggregate.out").receive(0)).isNull();
}
~~~

Đoạn test trên có thể thêm vào lớp \`SplitAggregateCorrelationTest\`. Nó kiểm tra khả năng **đợi đủ phần tử** dù thứ tự đến khác nhau. Nó **không** chứng minh Aggregator luôn xuất danh sách theo số thứ tự: nếu thứ tự đầu ra là một phần của hợp đồng nghiệp vụ, cần cấu hình phép xử lý nhóm/sắp xếp theo \`sequenceNumber\` hoặc đặt Resequencer phù hợp rồi assert \`containsExactly("first", "second")\`.

Phân biệt rõ:

- **Thứ tự đến**: thứ tự message được gửi/nhận qua channel.
- **Thứ tự ghép**: thứ tự phần tử trong payload do \`MessageGroupProcessor\` tạo ra.
- **Thứ tự phát kết quả nhóm**: nhóm nào hoàn tất trước thì có thể phát trước, bất kể nhóm nào bắt đầu trước.

Một flow có thể bảo đảm đủ số lượng và đúng correlation mà **không** bảo đảm cả ba thứ tự trên.

## 7. Trường hợp thiếu phần tử và timeout

Giả sử một nhóm khai báo ba phần tử nhưng chỉ có hai phần tử được gửi đến:

~~~text
G1: sequenceSize=3
  1/3 -> đến
  2/3 -> đến
  3/3 -> bị mất hoặc xử lý thất bại
~~~

Không thể chờ vô hạn trong sản phẩm thực tế. Bạn cần xác định và kiểm tra một trong các chính sách:

| Chính sách | Kỳ vọng kiểm thử |
| --- | --- |
| Chờ đủ phần tử | Khi mới có 2/3, chưa có output |
| Timeout rồi loại nhóm | Sau timeout, không có success output; tài nguyên nhóm được dọn theo chính sách |
| Timeout rồi phát kết quả một phần | Sau timeout, có partial result được đánh dấu/phân biệt rõ |
| Chuyển nhóm thiếu vào đường lỗi | Có tín hiệu lỗi hoặc sự kiện hết hạn mang correlation ID để điều tra |
| Đợi xử lý lại một phần tử | Sau retry thành công và nhận 3/3, nhóm phát kết quả đúng một lần |

Các cấu hình liên quan có thể gồm \`groupTimeout\`, \`sendPartialResultOnExpiry\`, \`expireGroupsUponCompletion\`, \`MessageGroupStore\` và các thành phần xử lý nhóm. **Tham số và hành vi cụ thể cần được đối chiếu với phiên bản Spring Integration và cấu hình của dự án.** Đừng viết test mong chờ partial result nếu flow chưa chủ động cho phép.

Với test timeout, dùng khoảng chờ nhỏ nhưng đủ ổn định trong CI; có thể dựa vào đồng hồ/trigger điều khiển được nếu giải pháp hỗ trợ. Dùng \`receive(timeout)\` hoặc chờ điều kiện thay cho \`Thread.sleep\` cố định. Nếu Aggregator được kích hoạt bởi scheduler/poller, cần bảo đảm scheduler thật sự chạy trong test.

### Kiểm tra nhóm chưa hoàn tất mà vẫn dọn trạng thái

Một test chỉ gửi message thứ nhất rồi dừng có thể để lại group dang dở trong memory store dùng chung. Với test đơn giản, hãy gửi tiếp phần tử còn lại và đọc output như ví dụ \`aggregator_waits_until_group_is_complete\`. Với test timeout/expiry, tạo group store độc lập hoặc có cleanup rõ ràng. Đây là một trong những nguyên nhân phổ biến khiến test Aggregator pass riêng lẻ nhưng fail khi chạy cả suite.

## 8. Duplicate message, retry và tính idempotent

Trong luồng thông điệp, retry có thể làm một fragment được gửi lại. Một Aggregator dựa trên **đếm số message** có nguy cơ coi message lặp là phần tử mới nếu không có cơ chế loại trùng.

~~~text
Nhóm G: sequenceSize=2
  đến: 1/2 (A)
  đến: 1/2 (A) lần nữa
  2/2 (B) chưa đến

Yêu cầu nghiệp vụ: chưa được phát kết quả chứa [A, A].
~~~

Nếu test này thất bại với cấu hình mặc định, đây là dấu hiệu cần bổ sung **idempotent receiver**, chiến lược lưu nhóm hoặc release strategy xét đúng định danh phần tử. Không được giả định rằng việc có \`sequenceNumber\` tự động loại trùng.

Một hợp đồng an toàn cho hệ thống đơn hàng có thể là:

1. Mỗi fragment có một khóa nghiệp vụ duy nhất, ví dụ \`lineId\` trong phạm vi \`correlationId\`.
2. Fragment đã xử lý không được tính hai lần.
3. Chỉ release khi tất cả định danh phần tử bắt buộc đã được nhận.
4. Nếu fragment đến sau khi nhóm hoàn tất, xử lý theo chính sách rõ ràng (bỏ qua, cảnh báo, nhóm mới hay sự kiện lỗi).

**Retry** của một Service Activator trước Aggregator và **retry phát message** ở broker có thể làm tăng số lần một fragment đi qua cùng đường. Việc kiểm tra happy path một lần không chứng minh hệ thống có idempotency. Test duplicate cần dùng cấu hình deduplication thực tế để xác nhận hành vi mong muốn.

## 9. Correlation key: chọn thế nào cho an toàn?

Correlation ID có thể do Splitter tạo hoặc do ứng dụng đặt. Nếu Aggregator nhận fragment từ nhiều nguồn, khóa nghiệp vụ thường rõ nghĩa hơn, ví dụ:

~~~text
correlationId = "tenant:shop-a/order:1729"
~~~

Khi đặt correlation từ dữ liệu nghiệp vụ, cần tránh hai nhóm không liên quan vô tình dùng chung khóa. Trong hệ thống nhiều tenant, \`orderId\` chỉ duy nhất trong một tenant có thể chưa đủ; dùng cặp tenant/order nếu đó là hợp đồng của hệ thống.

Ma trận kiểm thử nên có:

| Fragment | Tenant | Order | Correlation mong đợi |
| --- | --- | --- | --- |
| A1, A2 | \`shop-a\` | \`order-7\` | Nhóm A |
| B1, B2 | \`shop-b\` | \`order-7\` | Nhóm B |
| C1, C2 | \`shop-a\` | \`order-8\` | Nhóm C |

Nhờ vậy test phát hiện lỗi khi correlation chỉ tính theo \`orderId\` và làm trộn hai tenant. Với Gateway hoặc Router, đừng để một nhánh làm mất correlation header trước Aggregator. Khi Transformer tái tạo \`Message\`, hãy kiểm tra header cần thiết vẫn được truyền tiếp.

### Những trường hợp correlation cần phân loại rõ

- **Thiếu \`correlationId\`**: flow có từ chối, tự tạo từ dữ liệu nguồn hay route sang error channel?
- **Sai kiểu correlation**: một số khóa có thể là UUID, String hoặc object; các nguồn phải thống nhất kiểu để cùng nhóm.
- **Cùng giá trị nhưng khác kiểu**: \`"42"\` (String) và \`42\` (Integer) không nên bị xem là một khóa nếu ứng dụng không chủ động chuẩn hóa.
- **Khóa tái sử dụng**: một correlation ID đã hoàn tất lại xuất hiện sau đó có thể tạo group mới hoặc được từ chối tùy store và chính sách expiry.
- **Nested splitter**: tách nhiều cấp tạo các phạm vi sequence/correlation khác nhau; cần xác định Aggregator đang ghép nhóm ở cấp nào.

Các tình huống này không có một chính sách đúng cho mọi sản phẩm. Test phải diễn đạt rõ quy tắc nghiệp vụ và cấu hình của flow.

## 10. Filter giữa Splitter và Aggregator: bẫy hay gặp

Giả sử Splitter tạo ba message với \`sequenceSize=3\`, nhưng Filter loại phần tử thứ hai:

~~~mermaid
flowchart LR
    IN["[A, B, C]"] --> S["Splitter, size=3"]
    S --> A["A / 1/3"]
    S --> B["B / 2/3"]
    S --> C["C / 3/3"]
    A --> AG["Aggregator"]
    B --> F["Filter loại B"]
    C --> AG
    AG --> X["Nhóm thiếu 1 phần tử"]
~~~

Nếu Aggregator vẫn dùng release strategy chờ ba phần tử, nhóm có thể không bao giờ hoàn tất theo đường bình thường. Đây là **khác biệt giữa “đã tạo 3 fragment” và “sẽ có 3 fragment tới Aggregator”**.

Kiểm thử tình huống trên phải trả lời:

1. Filter có loại message trước khi tới Aggregator không?
2. Aggregator có biết thành viên bị loại là một kết quả hợp lệ hay không?
3. Có cần phát marker/placeholder để giữ đủ sequence, điều chỉnh release strategy, hoặc chuyển Filter trước Splitter?
4. Nếu nhóm chỉ hoàn tất khi timeout, kết quả một phần được xử lý thế nào?

Không nên sửa \`sequenceSize\` bằng cách đoán số message còn lại ở từng nhánh. Hãy thiết kế hợp đồng rõ giữa Splitter, Filter và Aggregator. Một test với danh sách \`["A", "B", "C"]\` và Filter loại \`"B"\` thường đủ để phát hiện rủi ro này.

## 11. Kiểm thử đồng bộ và bất đồng bộ

Ví dụ Java ở trên dùng flow đồng bộ trước \`QueueChannel\`. Khi \`send()\` kết thúc, ta có thể kiểm tra ngay queue có message nào hay không:

~~~java
input("aggregate.in").send(part("g", 1, 2, "A"));
assertThat(output("aggregate.out").receive(0)).isNull();
~~~

Trong trường hợp này, \`receive(0)\` là phép đọc **không chờ** tại thời điểm xác định. Nếu luồng có \`ExecutorChannel\`, broker hoặc poller, một message có thể đến muộn; \`receive(0) == null\` ngay sau \`send()\` không chứng minh được rằng Aggregator sẽ không phát kết quả sớm trong vài mili giây kế tiếp.

| Loại luồng | Điều nên kiểm tra | Cách quan sát |
| --- | --- | --- |
| DirectChannel đồng bộ | Không release khi chưa đủ; đúng kết quả sau khi đủ | \`receive(0)\` và \`receive(timeout)\` |
| ExecutorChannel đa luồng | Đúng nhóm bất chấp thời điểm và thứ tự đến | Đợi đủ output theo điều kiện, so sánh tập phần tử |
| Broker có thể giao lại | Không trùng kết quả khi fragment bị giao lại | Kết hợp test idempotency với adapter thực tế |
| MessageGroupStore bền vững | Nhóm đang chờ có được khôi phục sau restart? | Test với store thật và vòng đời context phù hợp |
| Timeout/partial result | Nhóm thiếu có hết hạn đúng policy? | Chờ sự kiện hoặc kết quả trong khoảng chờ hữu hạn |

Với luồng song song, **không khẳng định thứ tự các nhóm** nếu sản phẩm chỉ yêu cầu mỗi nhóm có kết quả đúng. Ví dụ A1, B1, A2, B2 có thể khiến A hoàn tất trước B; A1, B1, B2, A2 khiến B hoàn tất trước A. Kết quả ghép của từng nhóm vẫn phải đúng trong cả hai trường hợp.

## 12. Quan sát, lỗi và kiểm tra ranh giới

Trong hệ thống thực tế, test chỉ dựa trên payload đôi khi chưa đủ. Khi một nhóm bị kẹt, người vận hành cần biết correlation ID, số fragment đã nhận, số fragment dự kiến và nguyên nhân chậm.

Có thể theo dõi những thông tin sau bằng log/metrics/tracing được thiết kế phù hợp:

- \`correlationId\` hoặc khóa nghiệp vụ được dùng để nhóm.
- Số message trong group và \`sequenceSize\` dự kiến.
- Thời gian từ message đầu tiên đến khi nhóm release.
- Số group hết hạn, số fragment trùng hoặc đến muộn.
- Exception từ Transformer/Service Activator ở trước Aggregator.

Đừng ghi toàn bộ payload nhạy cảm vào log chỉ để xác định correlation. Trong test, dùng ID và dữ liệu giả như \`group-A\`, \`A1\`, \`B1\`.

Nếu một fragment xử lý thất bại **trước khi tới Aggregator**, lỗi có thể truyền về caller đối với đường đồng bộ hoặc tới error channel nếu có error handler cho đường bất đồng bộ. Test cần xác định liệu fragment lỗi được retry, loại, đưa vào dead letter hay khiến cả nhóm thất bại. Việc một error channel nhận được exception **không đồng nghĩa** Aggregator tự biết nhóm đã hết khả năng hoàn tất.

## 13. Các lỗi kiểm thử thường gặp

| Sai sót | Vì sao nguy hiểm? | Cách cải thiện |
| --- | --- | --- |
| Chỉ kiểm tra một nhóm | Không phát hiện trộn hai correlation | Gửi hai nhóm xen kẽ |
| Chỉ assert output khác \`null\` | Bỏ sót thiếu/thừa thành viên | Kiểm tra đầy đủ các payload phần tử |
| Chỉ assert đủ số message sau Splitter | Không biết sequence và correlation có đúng | Kiểm tra từng header liên quan |
| Mặc định đầu ra luôn có thứ tự 1, 2, 3 | Test không ổn định khi xử lý song song | Kiểm tra nội dung không phụ thuộc thứ tự, trừ khi có cam kết ordering |
| So sánh correlation tự sinh với UUID cố định | Test thất bại giả khi ID thay đổi | So sánh quan hệ cùng nhóm/khác nhóm |
| Không kiểm tra output sau fragment đầu | Aggregator có thể release quá sớm | Kiểm tra không có output trước khi đủ điều kiện |
| Không tiêu thụ hết queue của test | Message còn sót làm test khác thất bại | Đọc hết output hoặc cô lập context/store |
| Giả định sequenceSize đồng nghĩa loại trùng | Duplicate có thể đẩy nhóm release sớm | Test duplicate và cơ chế idempotency |
| Không test Filter giữa Splitter và Aggregator | Nhóm có thể chờ vĩnh viễn | Kiểm tra partial group và expiry policy |
| Dùng \`Thread.sleep\` cố định | Test chậm và dễ flaky | Dùng chờ theo điều kiện, timeout hữu hạn |

## 14. Bài thực hành

### Bài A — Thêm nhóm thứ ba

Mở rộng test Aggregator với ba nhóm \`G1\`, \`G2\`, \`G3\`, mỗi nhóm có hai fragment. Gửi theo thứ tự \`G1-1, G2-1, G3-1, G3-2, G1-2, G2-2\`. Kiểm tra ba output lần lượt chứa đúng dữ liệu nhóm G3, G1, G2 trong **flow đồng bộ** của ví dụ.

### Bài B — Đảo thứ tự sequence

Gửi \`2/2\` trước \`1/2\`. Chứng minh Aggregator không phát kết quả sau fragment đầu và chỉ phát một kết quả sau khi có đủ hai fragment. Nếu ứng dụng yêu cầu output có thứ tự sequence, hãy cấu hình sắp xếp rõ ràng rồi kiểm tra thứ tự đó.

### Bài C — Fragment bị mất

Tạo nhóm ba phần tử nhưng chỉ gửi \`1/3\` và \`2/3\`. Cấu hình timeout/expiry phù hợp với chính sách dự án; kiểm tra không phát success result sớm, sau đó xác minh nhóm được xử lý khi hết hạn và không còn trạng thái treo ngoài dự kiến.

### Bài D — Fragment được gửi lại

Gửi \`1/2\` hai lần, sau đó mới gửi \`2/2\`. Mục tiêu là thiết kế và kiểm thử cơ chế loại trùng để không coi hai bản \`1/2\` là hai thành viên hợp lệ. Test chỉ đạt khi Aggregator phát đúng một kết quả chứa **A và B**, không chứa hai bản A.

### Bài E — Filter giữa Splitter và Aggregator

Cho Splitter phát ba phần tử \`A\`, \`B\`, \`C\` nhưng Filter loại \`B\`. Giải thích vì sao điều kiện release dựa trên \`sequenceSize=3\` không còn phù hợp nếu không có cơ chế xử lý thành viên bị loại. Chọn một chính sách và viết test xác nhận nhóm không tồn tại vô hạn.

## 15. Tiêu chí hoàn thành

Một bộ kiểm thử Splitter/Aggregator theo correlation đạt yêu cầu khi xác nhận được tất cả các điểm sau:

1. Splitter sinh đúng số message, đúng payload và các sequence headers cần thiết.
2. Các fragment thuộc một request dùng cùng correlation; các request độc lập không bị gộp.
3. Aggregator không release khi thiếu phần tử và chỉ tạo đúng số output sau khi đủ điều kiện.
4. Hai hoặc nhiều nhóm gửi xen kẽ vẫn tạo kết quả riêng, không trộn dữ liệu.
5. Kịch bản đến sai thứ tự, thiếu, trùng hoặc đến muộn được xử lý theo chính sách minh bạch.
6. Các test có timeout hữu hạn, độc lập về group store và không dựa trên timing hoặc thứ tự không được bảo đảm.

Khi correlation và release condition đã được kiểm chứng ở mức message, bạn có thể kết nối thêm Router, Filter, Gateway, retry, error channel và các bước xử lý bất đồng bộ mà vẫn lần theo được **message thuộc nhóm nào, nhóm đã đủ điều kiện chưa, và kết quả được phát vì lý do gì**.
