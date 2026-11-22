# Kiểm thử Router theo từng route trong Spring Integration

## 1. Mục tiêu của bài học

**Router** là một Enterprise Integration Pattern dùng để quyết định message tiếp tục đi qua kênh nào. Trong **Spring Integration**, quyết định có thể dựa trên payload, một hoặc nhiều headers, biểu thức SpEL, loại payload hoặc logic nghiệp vụ. Router rất dễ bị bỏ sót lỗi khi chỉ kiểm tra rằng “có một message tới đầu ra”: message có thể đi nhầm nhánh, được phát thêm sang nhánh khác, bị mất khi không khớp route hoặc mang sai metadata sau định tuyến.

Bài **Kiểm thử Router theo từng route** thuộc chương **Kiểm thử pattern** của module **SPRING_INTEGRATION_PATTERN**. Đây là nền tảng để xây dựng các luồng thông điệp ít phụ thuộc, dễ mở rộng; sau Router, từng nhánh có thể nối tiếp Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và các bước xử lý correlation.

Sau khi học, bạn có thể:

1. Liệt kê các route cần kiểm thử từ hợp đồng đầu vào, không dựa vào các nhánh đã vô tình được code.
2. Gửi **một message tối thiểu cho mỗi route** và xác nhận đúng kênh nhận.
3. Khẳng định **những kênh còn lại không nhận message** đối với Router chỉ chọn một đích.
4. Kiểm tra route mặc định, header thiếu, giá trị lạ và sai kiểu dữ liệu.
5. Phân biệt Router định tuyến một đích với Recipient List hoặc publish-subscribe có nhiều đích.
6. Kiểm tra payload, headers, exception, correlation và hành vi đồng bộ/bất đồng bộ tại ranh giới định tuyến.

Điều quan trọng nhất: một test route đạt yêu cầu khi chứng minh được **message đã đến đúng nhánh** và **không xuất hiện ở các nhánh ngoài hợp đồng**.

## 2. Hiểu hợp đồng Router trước khi viết test

Giả sử hệ thống xử lý đơn hàng theo header \`route\`:

~~~mermaid
flowchart LR
    IN["orders.in\npayload + headers"] --> R{"Router\nheaders['route']"}
    R -->|VIP| VIP["orders.vip"]
    R -->|STANDARD| STD["orders.standard"]
    R -->|BULK| BULK["orders.bulk"]
    R -->|khác hoặc thiếu| DEF["orders.fallback"]
~~~

Trong ví dụ, Router dùng giá trị header \`route\` **đúng như đã được gửi vào**:

| Giá trị \`route\` | Kênh mong đợi | Các kênh phải rỗng sau khi nhận kết quả |
| --- | --- | --- |
| \`"VIP"\` | \`orders.vip\` | \`standard\`, \`bulk\`, \`fallback\` |
| \`"STANDARD"\` | \`orders.standard\` | \`vip\`, \`bulk\`, \`fallback\` |
| \`"BULK"\` | \`orders.bulk\` | \`vip\`, \`standard\`, \`fallback\` |
| \`"UNKNOWN"\` | \`orders.fallback\` | \`vip\`, \`standard\`, \`bulk\` |
| Không có header \`route\` | \`orders.fallback\` | \`vip\`, \`standard\`, \`bulk\` |

Đây là **hợp đồng ví dụ**: dự án thực tế có thể chọn exception, default channel hoặc discard đối với route không hợp lệ. Hãy xác định chính sách trước khi viết assertion; đừng mặc định mọi Router đều có fallback.

Một message tối thiểu cho route VIP:

~~~java
Message<String> message = MessageBuilder.withPayload("order-7")
        .setHeader("route", "VIP")
        .setHeader("tenantId", "shop-a")
        .build();
~~~

Payload \`"order-7"\` cho phép kiểm tra message không bị biến đổi ngoài ý muốn; \`route\` quyết định tuyến; \`tenantId\` là header nghiệp vụ phải còn nguyên. Không cần tự tạo \`sequenceSize\`, \`replyChannel\` hay \`correlationId\` nếu Router này không dùng chúng.

### Phân biệt ba lớp hợp đồng

| Lớp | Câu hỏi kiểm thử | Ví dụ assertion |
| --- | --- | --- |
| **Quyết định** | Giá trị route chọn kênh nào? | \`VIP\` chỉ đi \`orders.vip\` |
| **Dữ liệu** | Message mang payload/header gì sau Router? | Payload vẫn là \`order-7\`, tenant còn nguyên |
| **Số lượng** | Router có phát đúng số message được yêu cầu? | Một input hợp lệ → đúng một output ở một kênh |

Nếu thiếu lớp số lượng, test có thể vượt qua dù Router gửi cùng message tới cả VIP và STANDARD. Nếu thiếu lớp dữ liệu, test không bắt được lỗi làm mất \`tenantId\` hoặc thay đổi payload ở endpoint gắn liền với Router.

## 3. Lựa chọn mức kiểm thử

### Unit test cho logic phân loại

Nếu quyết định route là một hàm Java thuần, hãy kiểm tra trực tiếp:

~~~java
static String selectRoute(int orderAmount) {
    if (orderAmount >= 10_000) {
        return "VIP";
    }
    return "STANDARD";
}

@Test
void amount_at_boundary_goes_to_vip() {
    assertThat(selectRoute(9_999)).isEqualTo("STANDARD");
    assertThat(selectRoute(10_000)).isEqualTo("VIP");
}
~~~

Unit test bắt được lỗi so sánh biên, nhưng không biết \`"VIP"\` có thực sự được ánh xạ sang \`orders.vip\` trong Spring context hay không. Vì vậy cần **flow test** để kiểm tra wiring thực tế.

### Flow test cho mapping và kênh đầu ra

Flow test dựng Router và các channel trong bộ nhớ, gửi message qua input channel rồi đọc kết quả. \`QueueChannel\` hữu ích vì lưu message cho test gọi \`receive(timeout)\`. Không cần HTTP server, Kafka, RabbitMQ hay database khi đang kiểm tra riêng một Router.

Ví dụ dùng **Java 17, JUnit 5, AssertJ và Spring Integration Java DSL 6.x**. Với Maven và Spring Boot, dự án thường có:

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

Hãy dùng phiên bản Spring Boot và Spring Integration tương thích với nhau. Đoạn minh họa dưới đây tập trung vào một Router chạy đồng bộ; các trường hợp dùng executor hoặc message broker được bàn ở phần sau.

## 4. Ví dụ hoàn chỉnh: test từng route

Tạo lớp \`src/test/java/example/RouteByHeaderTest.java\`. Chúng ta định nghĩa rõ bốn \`QueueChannel\` đầu ra và một flow đọc header \`route\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RouteByHeaderTest.Config.class)
class RouteByHeaderTest {

    private static final String[] OUTPUTS = {
            "orders.vip", "orders.standard",
            "orders.bulk", "orders.fallback"
    };

    @Autowired
    ApplicationContext context;

    private MessageChannel input() {
        return context.getBean("orders.in", MessageChannel.class);
    }

    private QueueChannel output(String name) {
        return context.getBean(name, QueueChannel.class);
    }

    private Message<String> request(String orderId, Object route) {
        var builder = MessageBuilder.withPayload(orderId)
                .setHeader("tenantId", "shop-a")
                .setHeader("requestId", "req-7");

        if (route != null) {
            builder.setHeader("route", route);
        }
        return builder.build();
    }

    private void assertOnlyRoute(
            String expectedChannel, String orderId, Object route) {
        Message<String> inputMessage = request(orderId, route);
        assertThat(input().send(inputMessage)).isTrue();

        Message<?> actual = output(expectedChannel).receive(1_000);
        assertThat(actual)
                .as("Expected one message on %s", expectedChannel)
                .isNotNull();
        assertThat(actual.getPayload()).isEqualTo(orderId);
        assertThat(actual.getHeaders().get("tenantId")).isEqualTo("shop-a");
        assertThat(actual.getHeaders().get("requestId")).isEqualTo("req-7");

        if (route == null) {
            assertThat(actual.getHeaders()).doesNotContainKey("route");
        } else {
            assertThat(actual.getHeaders().get("route")).isEqualTo(route);
        }

        // Đã lấy message mong đợi; cả bốn queue phải không còn message.
        for (String channel : OUTPUTS) {
            assertThat(output(channel).receive(0))
                    .as("Unexpected extra message on %s", channel)
                    .isNull();
        }
    }

    @Test
    void vip_goes_only_to_vip_channel() {
        assertOnlyRoute("orders.vip", "order-1", "VIP");
    }

    @Test
    void standard_goes_only_to_standard_channel() {
        assertOnlyRoute("orders.standard", "order-2", "STANDARD");
    }

    @Test
    void bulk_goes_only_to_bulk_channel() {
        assertOnlyRoute("orders.bulk", "order-3", "BULK");
    }

    @Test
    void unknown_route_uses_fallback() {
        assertOnlyRoute("orders.fallback", "order-4", "UNKNOWN");
    }

    @Test
    void missing_header_uses_fallback() {
        assertOnlyRoute("orders.fallback", "order-5", null);
    }

    @Test
    void wrong_type_is_not_treated_as_known_route() {
        assertOnlyRoute("orders.fallback", "order-6", 42);
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("orders.vip")
        QueueChannel vip() {
            return new QueueChannel();
        }

        @Bean("orders.standard")
        QueueChannel standard() {
            return new QueueChannel();
        }

        @Bean("orders.bulk")
        QueueChannel bulk() {
            return new QueueChannel();
        }

        @Bean("orders.fallback")
        QueueChannel fallback() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow routeOrders() {
            return IntegrationFlow.from("orders.in")
                    .route("headers['route']", spec -> spec
                            .channelMapping("VIP", "orders.vip")
                            .channelMapping("STANDARD", "orders.standard")
                            .channelMapping("BULK", "orders.bulk")
                            .defaultOutputChannel("orders.fallback"))
                    .get();
        }
    }
}
~~~

**Điểm đáng chú ý trong ví dụ:**

- Ba route hợp lệ có ba test độc lập. Nếu sau này thêm \`EXPRESS\`, hãy cập nhật bảng hợp đồng, thêm kênh và thêm test cho route đó.
- \`"UNKNOWN"\`, thiếu header và giá trị số nguyên \`42\` là các nhánh đối chứng. Chúng chứng minh fallback không làm sai dữ liệu đầu vào.
- Hàm \`assertOnlyRoute\` đọc đúng một output rồi kiểm tra cả bốn queue rỗng, nên phát hiện cả gửi nhầm nhánh lẫn phát trùng trong luồng đồng bộ.
- Payload và các header \`tenantId\`, \`requestId\` được kiểm tra vì chúng thuộc hợp đồng; test không so sánh chính xác header \`id\` hoặc \`timestamp\` do framework tạo.
- Test chỉ tạo một input tại một thời điểm. Mỗi phép thử phải tiêu thụ hết message đã tạo để không phụ thuộc vào thứ tự thực thi của JUnit.

**Lưu ý về chính sách fallback:** Spring Integration hỗ trợ các cách chọn kênh khác nhau; việc dùng giá trị kết quả làm tên channel, ánh xạ qua \`channelMapping\` hoặc đưa vào default channel phụ thuộc cấu hình Router. Ví dụ cố ý ánh xạ các giá trị được công nhận và chỉ định default channel. Nếu hệ thống yêu cầu *chỉ nhận các route khai báo*, hãy kiểm tra thêm tùy chọn fallback theo channel key của phiên bản bạn sử dụng và bảo đảm không có kênh ngoài danh sách bị chọn ngoài ý muốn.

## 5. Kiểm thử từng route không có nghĩa là chỉ thử happy path

Một Router có ba nhánh nghiệp vụ có thể cần nhiều hơn ba test. Thử **một giá trị hợp lệ cho mỗi nhánh** là mức tối thiểu để bao phủ mapping; sau đó bổ sung các tình huống ở ranh giới của bộ chọn route.

| Tình huống | Ví dụ input | Câu hỏi phải trả lời |
| --- | --- | --- |
| Đúng route VIP | \`route="VIP"\` | Chỉ VIP nhận message? |
| Đúng route STANDARD | \`route="STANDARD"\` | Có bị chuyển nhầm sang VIP không? |
| Đúng route BULK | \`route="BULK"\` | Có message trùng ở nơi khác không? |
| Không khớp mapping | \`route="UNKNOWN"\` | Default, exception hay discard? |
| Thiếu header | Không có \`route\` | Chính sách nào áp dụng? |
| Sai kiểu | \`route=42\` | Có bị ép kiểu hoặc route sai không? |
| Sai hoa/thường | \`route="vip"\` | Hệ thống có chuẩn hóa không? |
| Có khoảng trắng | \`route=" VIP "\` | Có bước trim hay thuộc nhóm invalid? |
| Giá trị trống | \`route=""\` | Default, validation error hay discard? |
| Giá trị hợp lệ nhưng payload lỗi | \`route="VIP"\`, payload sai | Router có trách nhiệm validation không, hay Filter sau Router? |

Không cần xây dựng mọi trường hợp nếu không liên quan đến yêu cầu. Nhưng **thứ tự ưu tiên của validation và routing** cần được xác nhận rõ. Ví dụ, nếu header \`" vip "\` phải thành \`"VIP"\`, hãy dùng Transformer hoặc Header Enricher trước Router để chuẩn hóa, rồi kiểm tra cả đầu vào thô lẫn kết quả. Không mặc định SpEL hoặc \`channelMapping\` tự thực hiện trim và chuyển chữ hoa.

### Bảng route là một tập case kiểm thử

Khi số route tăng, thay các test lặp bằng \`@ParameterizedTest\`:

~~~java
@ParameterizedTest
@CsvSource({
    "VIP, orders.vip",
    "STANDARD, orders.standard",
    "BULK, orders.bulk",
    "UNKNOWN, orders.fallback"
})
void routes_to_expected_channel(String route, String channel) {
    assertOnlyRoute(channel, "order-x", route);
}
~~~

Đoạn này thuộc cùng lớp \`RouteByHeaderTest\`, cần thêm các import \`org.junit.jupiter.params.ParameterizedTest\` và \`org.junit.jupiter.params.provider.CsvSource\`. Với \`spring-boot-starter-test\` phiên bản tương thích, JUnit Jupiter Params thường có sẵn. Trường hợp thiếu header cần test riêng vì CSV nhập chuỗi rỗng hoặc \`null\` cần quy tắc biểu diễn rõ ràng; không nên vô tình biến “không có header” thành header là chuỗi rỗng.

Parameterized test đặc biệt hữu ích khi các route có cùng chính sách. Nếu mỗi route cần nội dung payload khác nhau hoặc có side effect riêng, hãy giữ những test mô tả rõ hành vi của từng nhánh.

## 6. Kiểm thử chính sách đối với route không hợp lệ

**Default channel** chỉ là một trong các chính sách Router có thể có. Chọn một trong các hành vi được sản phẩm quy định và viết test rõ ràng:

### Trường hợp A — đi vào default channel

Kịch bản trong ví dụ: \`route="UNKNOWN"\` đưa message nguyên vẹn đến \`orders.fallback\`. Test phải khẳng định fallback nhận đúng một message và tất cả kênh nghiệp vụ rỗng.

### Trường hợp B — thất bại rõ ràng

Nếu một giá trị route lạ phải bị từ chối, cấu hình Router không có default output và yêu cầu route phải được giải quyết. Với đường đồng bộ, một route không phân giải được có thể gây \`MessagingException\`:

~~~java
assertThatThrownBy(() ->
        input.send(MessageBuilder.withPayload("order-x")
                .setHeader("route", "UNKNOWN")
                .build()))
        .isInstanceOf(MessagingException.class);
~~~

Đây là **khung assertion**, giả định \`input\` là channel của một flow khác được cấu hình để từ chối route không hợp lệ. Cần xác định chính sách của Router cụ thể, bao gồm default channel, tên channel từ khóa route và \`resolutionRequired\`. Nếu có nhánh xử lý lỗi riêng, kiểm tra thêm exception gốc và không có success output.

### Trường hợp C — loại message theo chủ đích

Một số luồng chủ động bỏ qua message không có route hợp lệ. Lúc đó điều cần kiểm tra là message không xuất hiện ở bất kỳ output nào và cơ chế theo dõi/đếm discard đúng yêu cầu. Không dùng “không có output” làm bằng chứng thành công khi không biết Router đã *chủ động bỏ* hay bị lỗi wiring.

### Phân biệt route hợp lệ nhưng không có subscriber

Một route có key đúng không đồng nghĩa channel đích sẵn sàng nhận. Với \`DirectChannel\`, gửi tới channel không có subscriber có thể phát sinh \`MessageDeliveryException\` khi gọi \`send()\`; với \`QueueChannel\`, message có thể xếp hàng và chưa được xử lý tiếp. Đây là vấn đề **delivery và wiring**, tách biệt với logic xác định route. Flow test nên kiểm tra đúng loại channel đích đã được khai báo.

## 7. Kiểm thử Router theo payload hoặc biểu thức

Không phải mọi Router đều đọc header \`route\`. Dưới đây là các cách chọn route thường gặp và dữ liệu tối thiểu để kiểm thử:

| Kiểu Router | Tiêu chí | Input tối thiểu |
| --- | --- | --- |
| Header-value Router | \`headers['route']\` | Hai message khác \`route\`, cùng payload |
| Payload-value Router | Payload \`"VIP"\`/\`"STANDARD"\` | Hai payload thuộc hai nhóm |
| Payload-type Router | Java class của payload | Một \`String\` và một DTO |
| Expression Router | SpEL trả giá trị mapping | Input ở hai phía của điều kiện |
| Method Router | Phương thức Java tính route | Test unit hàm + test mapping |

Ví dụ khi route được tính theo payload:

~~~java
@Bean
IntegrationFlow routeByAmount() {
    return IntegrationFlow.from("amount.in")
            .route(Integer.class,
                    amount -> amount >= 10_000 ? "VIP" : "STANDARD",
                    spec -> spec
                            .channelMapping("VIP", "amount.vip")
                            .channelMapping("STANDARD", "amount.standard"))
            .get();
}
~~~

Đây là đoạn cấu hình minh họa, giả định đã đăng ký hai channel \`amount.vip\` và \`amount.standard\`. Bộ test tối thiểu nên gửi \`9_999\`, \`10_000\`, rồi xác minh nhánh trước và sau ngưỡng. Chọn hai giá trị cùng một phía ngưỡng không chứng minh được điều kiện so sánh biên.

Nếu expression dùng nhiều header (ví dụ \`tenantId\` và \`priority\`), xây dựng bảng điều kiện rõ ràng trước khi viết test. Với ba điều kiện Boolean không nên chỉ thử một message “đầy đủ đúng”, vì test đó không xác minh các nhánh mà điều kiện sai.

## 8. Kiểm thử payload và headers sau khi định tuyến

Router thông thường chọn đích của message; các thao tác biến đổi payload, loại dữ liệu hoặc enrich header thường là trách nhiệm của endpoint trước/sau Router. Test nên bắt được lỗi ở ranh giới:

~~~text
Input:
  payload     = "order-7"
  route       = "VIP"
  tenantId    = "shop-a"
  requestId   = "req-7"

After Router:
  expected channel = orders.vip
  payload          = "order-7"
  route            = "VIP"
  tenantId         = "shop-a"
  requestId        = "req-7"
~~~

Đừng so sánh toàn bộ header map của input và output vì framework có thể thêm/thay metadata điều khiển (\`id\`, \`timestamp\`, reply/error channel tùy điểm xử lý). Thay vào đó, assert **các header thuộc hợp đồng nghiệp vụ**. Nếu module có tracing, xác nhận \`requestId\` hoặc correlation ID giữ nguyên qua Router để người vận hành lần theo cùng yêu cầu.

### Route trước hay sau Transformer?

Giả sử message gửi vào có \`route=" vip "\`. Nếu yêu cầu nghiệp vụ cho phép chuẩn hóa route, pipeline hợp lý có thể là:

~~~mermaid
flowchart LR
    IN["route=' vip '"] --> T["Header Enricher\ntrim + uppercase"]
    T --> R{"Router"}
    R -->|"VIP"| V["VIP channel"]
    R -->|"khác"| F["Fallback / Error"]
~~~

Test tối thiểu gồm một message cần chuẩn hóa và một message không khớp. Xác minh output đúng kênh, header đã chuẩn hóa và payload giữ nguyên. Nếu Transformer chỉ áp dụng trên payload, nó **không tự động chuẩn hóa header**; cần endpoint thay đổi header thực sự hoặc bộ chọn route có xử lý rõ ràng.

## 9. Khi Router chọn nhiều đích

Các ví dụ trước dùng hợp đồng **một message đi đúng một channel**. Nhưng Spring Integration còn có \`RecipientListRouter\`, \`PublishSubscribeChannel\` và các flow chọn nhiều recipient. Khi đó, assertion “mọi nhánh khác đều rỗng” sẽ sai vì thông điệp được **chủ động nhân tới nhiều đích**.

Ví dụ hợp đồng:

~~~text
Input:
  payload = "order-7"
  audit = true

Expected recipients:
  order.processing  -> 1 message
  order.audit       -> 1 message
  order.alert       -> 0 message
~~~

Với trường hợp này, test cần:

1. Khẳng định từng channel **được chọn** nhận đúng một message.
2. Khẳng định channel **không được chọn** không nhận message.
3. Kiểm tra payload/header được giữ hoặc thay đổi đúng với chính sách sao chép và sequence.
4. Kiểm tra xử lý lỗi khi một recipient không nhận được: Router có dừng, gửi tiếp hay bỏ qua lỗi tùy cấu hình?

Nếu có \`applySequence\`, metadata \`sequenceNumber\` và \`sequenceSize\` có thể được bổ sung cho các bản message hướng tới những recipient khác nhau. Chỉ assert sequence khi đã bật và xác định rõ ý nghĩa của nó trong luồng; không mặc định mọi Router đều tạo sequence.

## 10. Đồng bộ, bất đồng bộ và kiểm thử không có message

Ví dụ ở mục 4 dùng các endpoint đồng bộ trước \`QueueChannel\`. Sau khi \`send()\` hoàn thành, \`receive(0)\` giúp xác nhận ngay trạng thái của các queue đầu ra. Nhưng nếu đặt \`ExecutorChannel\` hoặc broker trên đường đi, một nhánh có thể nhận message muộn.

| Mô hình | Cách quan sát phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| DirectChannel đồng bộ | Gửi một message, đọc kênh được chọn, kiểm tra các queue khác rỗng | Chỉ kiểm tra sau khi \`send()\` hoàn tất |
| ExecutorChannel bất đồng bộ | \`receive(timeout)\` cho nhánh dự kiến; theo dõi kết quả nhánh không được chọn trong cửa sổ phù hợp | \`receive(0)\` ngay lập tức chưa chứng minh không có message muộn |
| Message broker | Adapter test có timeout, correlation ID riêng và dọn hàng đợi test | Message có thể bị giao lại hoặc có sẵn từ lượt trước |
| Router phát nhiều recipient | Đợi đủ các đầu ra được chỉ định | Không áp dụng quy tắc “đúng một output tổng cộng” |

Tránh dựa vào \`Thread.sleep(500)\` để suy luận các tác vụ đã kết thúc. Dùng tín hiệu hoàn tất, barrier/test latch thích hợp hoặc một khoảng quan sát có giới hạn được định nghĩa rõ. Nếu dự án yêu cầu đúng một message và không trùng trong môi trường có retry, kiểm tra cả tác dụng phụ và cơ chế idempotency, vì message có thể được xử lý lại dù Router logic đúng.

### Cô lập message giữa các test

Mỗi test nên tiêu thụ hết kết quả của chính mình. Nếu nhiều test cùng dùng Spring context và chạy song song, \`QueueChannel\` dùng chung có thể khiến test A đọc message của test B. Cách khắc phục là cô lập context/kênh, dùng request ID riêng hoặc chạy tuần tự các test chia sẻ hàng đợi. Không đặt tên channel phụ thuộc vào trạng thái còn sót từ test trước.

## 11. Router trong luồng nhiều pattern

Trong thực tế, Router là một chốt quyết định trước các tuyến xử lý độc lập:

~~~mermaid
flowchart TD
    IN["Gateway / Input"] --> R{"Router"}
    R -->|VIP| T["Transformer"]
    T --> A["Service Activator"]
    R -->|STANDARD| F{"Filter"}
    F -->|hợp lệ| S["Splitter"]
    S --> G["Aggregator"]
    F -->|bị loại| D["Discard"]
    R -->|UNKNOWN| E["Fallback / Error"]
    A --> O1["VIP Reply"]
    G --> O2["Standard Result"]
~~~

Để kiểm thử hiệu quả, chia các phép kiểm tra theo ranh giới:

- **Router test:** Chỉ khẳng định message đến đúng nhánh, payload/header không bị đổi ngoài hợp đồng và số output đúng.
- **Branch test:** Kiểm tra riêng Transformer, Filter, Splitter/Aggregator, correlation và điều kiện lỗi của từng nhánh.
- **Gateway/integration test:** Kiểm tra request/reply hoàn chỉnh, timeout, retry và xử lý lỗi theo end-to-end contract.

Một test toàn luồng thất bại ở kết quả cuối có thể do Router, Filter hoặc Aggregator. Khi có test Router riêng cho từng route, bạn có thể loại trừ nhanh lỗi mapping để tập trung vào nhánh bị lỗi.

### Retry và error channel có ảnh hưởng gì?

Một Router có thể định tuyến đúng nhưng downstream handler ném lỗi. Với đường đồng bộ, lỗi có thể truyền về caller; với đường bất đồng bộ có error handler, lỗi có thể đến error channel. Vì thế:

1. Test Router độc lập với channel nhận trong bộ nhớ để kiểm tra chính xác tuyến được chọn.
2. Test handler ở mỗi nhánh để kiểm tra exception, retry và recovery.
3. Test kết hợp một số đường chính để bảo đảm \`requestId\`/correlation ID giúp truy vết một message qua nhiều endpoint.

Không xem \`send()\` trả \`true\` là bằng chứng xử lý nghiệp vụ đã hoàn tất khi downstream bất đồng bộ. Nó chỉ xác nhận thao tác gửi được channel chấp nhận theo semantics của channel đó.

## 12. Bài thực hành và tiêu chí hoàn thành

### Bài A — Thêm route EXPRESS

Từ ví dụ ở mục 4, thêm channel \`orders.express\`, mapping \`"EXPRESS"\` và test cho \`"EXPRESS"\`. Mở rộng danh sách \`OUTPUTS\` trong helper để xác minh mọi channel không được chọn vẫn rỗng. Sau khi thêm route, bộ test cũ phải tiếp tục pass vì các mapping cũ giữ nguyên.

### Bài B — Chuẩn hóa header

Cho phép \`route=" vip "\` được xử lý như \`VIP\`. Bổ sung bước chuẩn hóa trước Router và viết test xác nhận:

- Input \`" vip "\` đi VIP sau khi được chuẩn hóa.
- Header \`route\` tại output mang giá trị theo hợp đồng mới.
- Input \`"unknown"\` vẫn đi default channel.
- Message không hợp lệ không rơi vào VIP ngoài ý muốn.

### Bài C — Từ chối route không hợp lệ

Thay fallback bằng chính sách ném lỗi đối với route chưa được khai báo. Gửi \`"UNKNOWN"\` và message không có \`route\`. Assert exception đồng bộ phù hợp, không có output thành công và nguyên nhân lỗi đủ rõ để chẩn đoán. Nếu triển khai error channel bất đồng bộ, đổi assertion theo mô hình đó.

### Bài D — Kiểm thử Recipient List

Giả sử input \`audit=true\` cần đi cả \`orders.process\` và \`orders.audit\`. Tạo test xác nhận **hai recipient** đều nhận đúng một message; khi \`audit=false\`, chỉ \`orders.process\` nhận. Kiểm tra không có message thừa trong những channel còn lại.

### Tiêu chí tự đánh giá

Bộ test Router theo từng route đạt yêu cầu khi:

1. Tất cả giá trị route hợp lệ đều có test hoặc case rõ ràng trong bảng dữ liệu.
2. Route không hợp lệ, thiếu header và trường hợp biên được xử lý đúng chính sách.
3. Mỗi test kiểm tra chính xác **đầu ra được chọn, đầu ra không được chọn và số message**.
4. Payload và các header nghiệp vụ thiết yếu được giữ hoặc thay đổi đúng hợp đồng.
5. Assertion về thời gian và thứ tự phù hợp channel đồng bộ hay bất đồng bộ.
6. Test có thể chạy độc lập; lỗi ở Router được phân biệt với lỗi của endpoint downstream.

Khi mỗi tuyến đã được kiểm thử bằng một message tối thiểu và những trường hợp đối chứng phù hợp, bạn có thể thêm các pattern khác mà vẫn giữ quyền kiểm soát đường đi của message, dữ liệu nghiệp vụ và khả năng quan sát toàn bộ luồng Spring Integration.
