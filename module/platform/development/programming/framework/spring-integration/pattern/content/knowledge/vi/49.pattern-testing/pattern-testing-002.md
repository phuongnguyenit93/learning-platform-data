# Kiểm thử payload và headers trong Spring Integration

## 1. Vì sao payload và headers phải được kiểm thử cùng nhau?

Trong **Enterprise Integration Patterns (EIP)**, một message được chuyển giữa các thành phần mà không buộc chúng phụ thuộc trực tiếp vào nhau. Với **Spring Integration**, nội dung nghiệp vụ nằm trong **payload**, còn **headers** cung cấp ngữ cảnh để định tuyến, theo dõi, ghép nhóm và phản hồi. Một Transformer có thể trả đúng payload nhưng làm mất mã tenant; một Router có thể gửi sai nhánh vì đọc nhầm kiểu dữ liệu của header; một Aggregator có thể ghép nhầm hai đơn hàng vì correlation ID sai.

Bài học thuộc chương **Kiểm thử pattern** của module **SPRING_INTEGRATION_PATTERN**. Mục tiêu là kiểm tra chính xác những gì đi qua Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry và error channel, đồng thời duy trì luồng thông điệp ít phụ thuộc, dễ mở rộng và có thể lần theo các nhánh xử lý.

Sau bài này, bạn có thể:

1. Tạo message nhỏ, có payload và các header thực sự cần cho kịch bản.
2. Kiểm tra giá trị, **kiểu**, cấu trúc và tính bất biến của payload.
3. Phân biệt header nghiệp vụ với header do framework quản lý.
4. Phát hiện header bị mất, thêm sai, ghi đè sai hoặc không có ở nơi phải có.
5. Kiểm tra correlation, sequence, routing, lỗi và retry qua các bước xử lý.
6. Viết assertion ổn định, tránh phụ thuộc vào ID, timestamp và thời điểm xử lý không được hệ thống cam kết.

**Nguyên tắc:** Một test tốt mô tả *hợp đồng của message tại một ranh giới*, gồm payload, headers và điều kiện phát ra message. Đừng khẳng định tất cả header chỉ vì chúng hiện diện trong một lần chạy.

## 2. Cấu trúc một message

Trong Spring Messaging, kiểu trung tâm là \`org.springframework.messaging.Message<T>\`:

~~~text
Message<T>
├── payload: T
│   └── "  SKU-42  "                (dữ liệu nghiệp vụ)
└── headers: MessageHeaders
    ├── id: UUID                   (framework quản lý)
    ├── timestamp: long            (framework quản lý)
    ├── tenantId: "shop-a"         (nghiệp vụ)
    ├── route: "priority"          (nghiệp vụ / định tuyến)
    ├── correlationId: "order-42"  (liên kết các phần tử cùng nhóm)
    ├── sequenceNumber: 1          (thứ tự thành viên trong nhóm)
    ├── sequenceSize: 2            (số thành viên dự kiến)
    ├── replyChannel: ...          (kênh trả lời, khi cần)
    └── errorChannel: ...          (kênh nhận lỗi, khi cần)
~~~

Ví dụ tạo message tối thiểu bằng \`MessageBuilder\`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<String> request = MessageBuilder.withPayload("  SKU-42  ")
        .setHeader("tenantId", "shop-a")
        .setHeader("route", "priority")
        .build();
~~~

\`MessageBuilder\` tự tạo các header hệ thống như \`id\` và \`timestamp\` theo quy tắc của framework. Các giá trị này hữu ích để chẩn đoán, nhưng thường **không** nên cố định trong test nghiệp vụ.

### Phân loại hợp đồng

| Phần message | Ví dụ | Test cần khẳng định | Điều dễ sai |
| --- | --- | --- | --- |
| Payload | \`"SKU-42"\` | Đúng giá trị sau chuẩn hóa | Chỉ kiểm tra khác \`null\`, bỏ qua dữ liệu sai |
| Kiểu payload | \`OrderDto\`, \`List<String>\` | Đúng kiểu và cấu trúc mà bước tiếp theo cần | Chuỗi JSON bị nhầm là DTO |
| Header nghiệp vụ | \`tenantId="shop-a"\` | Có, đúng kiểu và đúng giá trị | Header bị mất khi transform hoặc gateway |
| Header điều khiển | \`route="priority"\` | Router dùng đúng giá trị | Sai chữ hoa/thường hoặc mapping thiếu nhánh |
| Correlation | \`correlationId="order-42"\` | Các phần tử cùng nhóm có cùng khóa | Gộp message của hai đơn hàng |
| Sequence | \`sequenceNumber=1\`, \`sequenceSize=2\` | Đúng metadata theo chiến lược tách/gom | Nhóm giải phóng quá sớm hoặc không bao giờ giải phóng |
| Header framework | \`id\`, \`timestamp\` | Hiện diện và có kiểu phù hợp nếu cần | Test so sánh UUID hoặc timestamp cố định |
| Header phản hồi/lỗi | \`replyChannel\`, \`errorChannel\` | Message đi tới đúng kênh theo cấu hình | Mặc định nghĩ lỗi đồng bộ sẽ được gửi tới error channel |

## 3. Thiết kế tập dữ liệu kiểm thử nhỏ nhưng đủ mạnh

Không cần dùng một object đơn hàng với hàng chục thuộc tính nếu chỉ kiểm tra Transformer cắt khoảng trắng. Bắt đầu với giá trị nhỏ nhất khiến hành vi mong muốn **phân biệt được** với hành vi sai.

| Hợp đồng | Message tối thiểu | Thêm trường hợp nào để bắt lỗi? |
| --- | --- | --- |
| Chuẩn hóa chuỗi | Payload \`"  A  "\` | \`"A"\`, chuỗi toàn dấu cách và ký tự Unicode |
| Kiểm tra kiểu | Payload một \`OrderDto\` | Trường bắt buộc trống, giá trị không hợp lệ |
| Giữ tenant | Payload \`"A"\`, \`tenantId="t1"\` | Không có \`tenantId\`; giá trị sai kiểu |
| Header enrichment | Payload \`"A"\`, không có \`stage\` | Đã có \`stage\`: được ghi đè hay giữ nguyên? |
| Router theo header | Payload \`"A"\`, \`route="priority"\` | \`route="normal"\`, không có \`route\` |
| Splitter | Payload \`["A","B"]\` | Danh sách rỗng; xác minh correlation/sequence |
| Aggregator | Hai message chung \`correlationId\`, có số thứ tự 1 và 2 | Hai nhóm gửi xen kẽ, thiếu phần tử thứ hai |
| Retry | Payload \`"A"\`, \`requestId="r1"\` | Handler lỗi tạm thời rồi thành công, không đổi request ID |
| Error handling | Một message gây lỗi, có thông tin nguồn | Exception và failed message được ghi nhận theo cấu hình |

Ví dụ khi test \`tenantId\`, gửi payload \`"A"\` với một header duy nhất là đủ. Chỉ thêm \`correlationId\`, \`route\` hay \`sequenceSize\` nếu luồng thực sự sử dụng chúng. Tập test nhỏ làm rõ nguồn gốc của một lỗi, tránh phụ thuộc dữ liệu mẫu quá lớn.

## 4. Unit test: payload, kiểu dữ liệu và header

Ví dụ dưới đây dùng **Java 17**, **JUnit 5** và **AssertJ**. Bạn có thể chạy phần unit test với \`spring-boot-starter-test\` và dependency Spring Messaging/Integration tương thích. Mục tiêu của phần này là kiểm tra message trực tiếp, chưa cần tạo \`ApplicationContext\`.

~~~java
package example;

import static org.assertj.core.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

class PayloadHeaderUnitTest {

    @Test
    void payload_has_expected_value_and_type() {
        Message<String> message = MessageBuilder
                .withPayload("  SKU-42  ")
                .build();

        assertThat(message.getPayload()).isInstanceOf(String.class);
        assertThat(message.getPayload()).isEqualTo("  SKU-42  ");
    }

    @Test
    void business_headers_keep_values_and_types() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .setHeader("tenantId", "shop-a")
                .setHeader("attempt", 2)
                .setHeader("retryable", true)
                .build();

        assertThat(message.getHeaders().get("tenantId"))
                .isEqualTo("shop-a");
        assertThat(message.getHeaders().get("attempt"))
                .isInstanceOf(Integer.class)
                .isEqualTo(2);
        assertThat(message.getHeaders().get("retryable"))
                .isEqualTo(true);

        assertThat(message.getHeaders())
                .containsKeys(MessageHeaders.ID, MessageHeaders.TIMESTAMP);
    }

    @Test
    void absent_header_is_distinguished_from_present_header() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .build();

        assertThat(message.getHeaders()).doesNotContainKey("tenantId");
        assertThat(message.getHeaders().get("tenantId")).isNull();
    }

    @Test
    void setting_header_if_absent_does_not_override_existing_value() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .setHeader("tenantId", "shop-a")
                .setHeaderIfAbsent("tenantId", "fallback")
                .build();

        assertThat(message.getHeaders().get("tenantId"))
                .isEqualTo("shop-a");
    }

    @Test
    void message_headers_are_read_only() {
        Message<String> message = MessageBuilder.withPayload("SKU-42")
                .setHeader("tenantId", "shop-a")
                .build();

        assertThatThrownBy(() ->
                message.getHeaders().put("tenantId", "shop-b"))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

Các test này phân biệt ba tình huống quan trọng:

- **Header đúng giá trị nhưng sai kiểu** vẫn là lỗi. Chẳng hạn \`attempt="2"\` (String) khác \`attempt=2\` (Integer). Một bộ phận đọc số nguyên có thể không xử lý được chuỗi.
- **Header không tồn tại** khác một header có giá trị hợp lệ nhưng rỗng. Với \`MessageBuilder.setHeader("key", null)\`, hành vi thường là loại bỏ header; vì vậy hãy kiểm tra \`containsKey\` khi hợp đồng yêu cầu hiện diện.
- **MessageHeaders không cho sửa trực tiếp**. Nhưng payload có thể trỏ tới một object hoặc collection thay đổi được; tính bất biến của headers **không** bảo đảm tính bất biến sâu của payload. Dùng \`record\`, DTO immutable hoặc sao chép dữ liệu nếu các luồng song song có thể cùng sử dụng payload.

### Kiểm thử object payload

Trong hệ thống thật, payload thường là DTO. Test nên kiểm tra trường nghiệp vụ thay vì \`toString()\`:

~~~java
record OrderLine(String sku, int quantity) {}

@Test
void structured_payload_keeps_business_fields() {
    Message<OrderLine> message = MessageBuilder
            .withPayload(new OrderLine("SKU-42", 3))
            .build();

    assertThat(message.getPayload().sku()).isEqualTo("SKU-42");
    assertThat(message.getPayload().quantity()).isEqualTo(3);
}
~~~

Spring Messaging không cho dùng payload Java \`null\` trong một message thông thường được xây bởi \`MessageBuilder.withPayload(null)\`. Nếu nghiệp vụ cần biểu diễn “không có giá trị”, hãy định nghĩa hợp đồng rõ ràng: giá trị Optional ở biên ứng dụng, một DTO biểu thị trạng thái, thông điệp kết thúc luồng hoặc cơ chế xử lý rỗng phù hợp. Không dựng một \`Message<...>\` có payload \`null\` rồi kỳ vọng mọi endpoint nhận được.

## 5. Flow test: kiểm tra payload và header qua Transformer

Unit test chỉ chứng minh logic trong Java. Flow test xác nhận cách Spring Integration thực sự truyền \`Message\` qua channel và endpoint. Ví dụ tiếp theo tạo một luồng:

~~~mermaid
flowchart LR
    A["normalize.in\npayload='  SKU-42  '\ntenantId='shop-a'"] --> B["Transformer\nString.trim()"]
    B --> C["Header Enricher\nstage='normalized'"]
    C --> D["normalize.out\nQueueChannel"]
~~~

Đặt đoạn sau trong \`src/test/java/example/PayloadHeaderFlowTest.java\`. Đây là lớp kiểm thử độc lập, dùng \`QueueChannel\` để quan sát message đầu ra, không cần HTTP server hoặc message broker:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PayloadHeaderFlowTest.Config.class)
class PayloadHeaderFlowTest {

    @Autowired
    @Qualifier("normalize.in")
    MessageChannel input;

    @Autowired
    @Qualifier("normalize.out")
    QueueChannel output;

    @Test
    void transformer_changes_payload_and_preserves_business_headers() {
        Message<String> request = MessageBuilder
                .withPayload("  SKU-42  ")
                .setHeader("tenantId", "shop-a")
                .setHeader("requestId", "req-7")
                .setHeader("attempt", 1)
                .build();

        assertThat(input.send(request)).isTrue();

        Message<?> response = output.receive(1_000);
        assertThat(response).isNotNull();
        assertThat(response.getPayload()).isEqualTo("SKU-42");
        assertThat(response.getPayload()).isInstanceOf(String.class);
        assertThat(response.getHeaders().get("tenantId"))
                .isEqualTo("shop-a");
        assertThat(response.getHeaders().get("requestId"))
                .isEqualTo("req-7");
        assertThat(response.getHeaders().get("attempt"))
                .isEqualTo(1);
        assertThat(response.getHeaders().get("stage"))
                .isEqualTo("normalized");
        assertThat(response.getHeaders())
                .containsKeys(MessageHeaders.ID, MessageHeaders.TIMESTAMP);
        assertThat(output.receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("normalize.out")
        QueueChannel normalizeOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow normalizationFlow() {
            return IntegrationFlow.from("normalize.in")
                    .transform(String.class, String::trim)
                    .enrichHeaders(h -> h.header("stage", "normalized"))
                    .channel("normalize.out")
                    .get();
        }
    }
}
~~~

**Hợp đồng quan sát được** gồm: payload được cắt khoảng trắng; \`tenantId\`, \`requestId\`, \`attempt\` được giữ; \`stage\` được thêm đúng giá trị; chỉ có **một** message đầu ra. Dù Transformer tạo message mới, test không so sánh \`id\` hoặc \`timestamp\` của đầu ra với đầu vào, vì hai giá trị này có thể được framework tạo lại khi message được xây dựng.

**Giới hạn của phép kiểm tra \`receive(0)\`:** Nó phù hợp khi toàn bộ đoạn flow chạy đồng bộ. Nếu luồng có \`ExecutorChannel\`, broker hoặc một endpoint xử lý bất đồng bộ, \`receive(0)\` chỉ nói rằng *chưa có message tại thời điểm đọc*. Muốn khẳng định không có message thừa trong khoảng thời gian cụ thể, cần thiết kế cửa sổ quan sát có timeout và tránh giả định thứ tự xử lý khi không được cam kết.

### Nếu pipeline thay đổi header có chủ ý

Một Header Enricher có thể **thêm** header, **thay** giá trị hiện có hoặc chỉ điền giá trị mặc định, tùy cấu hình. Vì vậy, hãy viết test diễn tả chính sách mà dự án đã chọn:

| Chính sách | Header đầu vào | Kỳ vọng ở đầu ra |
| --- | --- | --- |
| Thêm giá trị mới | Không có \`stage\` | \`stage="normalized"\` |
| Ghi đè | \`stage="raw"\` | \`stage="normalized"\` |
| Chỉ thêm nếu thiếu | \`stage="approved"\` | Giữ \`stage="approved"\` |
| Loại header nội bộ | \`internalToken="tmp"\` | Không còn \`internalToken\` |
| Giữ khóa nghiệp vụ | \`tenantId="shop-a"\` | Vẫn là \`"shop-a"\` |

Đừng đoán cơ chế của Enricher chỉ từ tên header. Kiểm tra đúng cấu hình **Header Enricher**, **Header Filter** hoặc logic map message đang sử dụng. Với trường hợp thông tin nhạy cảm, hãy xác nhận header không bị chuyển ra một giao diện hoặc hệ thống mà nó không thuộc hợp đồng.

## 6. Kiểm thử Router và Filter dựa trên headers

Router thường đọc header như \`route\`, \`eventType\`, \`tenantId\`. Một lỗi có thể không làm payload thay đổi, nhưng gửi message sang nhánh khác.

~~~text
Input:
  payload = "SKU-42"
  route   = "priority"

Expected:
  priority.out  -> 1 message, payload vẫn là "SKU-42"
  normal.out    -> 0 message
  tenantId      -> không đổi
~~~

Nên có ít nhất ba kịch bản cho header quyết định tuyến:

1. Giá trị hợp lệ thứ nhất: \`route="priority"\` đi đúng kênh priority.
2. Giá trị hợp lệ thứ hai: \`route="normal"\` đi đúng kênh normal.
3. Không có hoặc sai giá trị \`route\`: áp dụng **chính sách đã định nghĩa** (default channel, exception, discard hoặc tuyến lỗi), tuyệt đối không dựa vào hành vi ngầm chưa thống nhất.

Ví dụ cấu hình mapping trong Java DSL:

~~~java
@Bean
IntegrationFlow routeByPriority() {
    return IntegrationFlow.from("route.in")
            .route("headers['route']", r -> r
                    .channelMapping("priority", "priority.out")
                    .channelMapping("normal", "normal.out"))
            .get();
}
~~~

Đoạn này giả định \`priority.out\` và \`normal.out\` là các channel đã đăng ký trong context. Khi làm test, dùng \`QueueChannel\` cho cả hai, gửi một message có \`route="priority"\`, đọc priority output và xác nhận normal output rỗng. Với hai nhánh xử lý bất đồng bộ, phải bổ sung cơ chế chờ phù hợp.

Filter có thể quyết định dựa vào payload **và** header, chẳng hạn từ chối yêu cầu không có tenant hợp lệ. Tách điều kiện ra hàm Java để dễ unit test:

~~~java
static boolean hasValidTenant(Message<?> message) {
    Object value = message.getHeaders().get("tenantId");
    return value instanceof String tenant && !tenant.isBlank();
}

@Test
void tenant_validation_handles_absent_and_wrong_type() {
    Message<String> valid = MessageBuilder.withPayload("SKU-42")
            .setHeader("tenantId", "shop-a").build();
    Message<String> missing = MessageBuilder.withPayload("SKU-42")
            .build();
    Message<String> wrongType = MessageBuilder.withPayload("SKU-42")
            .setHeader("tenantId", 42).build();

    assertThat(hasValidTenant(valid)).isTrue();
    assertThat(hasValidTenant(missing)).isFalse();
    assertThat(hasValidTenant(wrongType)).isFalse();
}
~~~

Khi tích hợp predicate này vào Filter, test thêm đầu ra và discard channel: message hợp lệ được giữ, message không hợp lệ bị loại theo chính sách. Đừng chỉ kiểm tra giá trị trả về của predicate rồi kết luận luồng đã nối channel đúng.

## 7. Kiểm thử Splitter, Aggregator và correlation headers

Khi Splitter tách một message thành nhiều phần tử, Spring Integration thường mang theo metadata như \`correlationId\`, \`sequenceNumber\`, \`sequenceSize\` để các endpoint tiếp theo có thể xử lý hoặc ghép nhóm. Kết quả cụ thể phụ thuộc cấu hình sequence và kiểu splitter.

~~~mermaid
flowchart TD
    A["Input\npayload=['A','B']\nrequestId='r-01'"] --> B[Splitter]
    B --> C["'A'\ncorrelationId=G\nsequenceNumber=1\nsequenceSize=2"]
    B --> D["'B'\ncorrelationId=G\nsequenceNumber=2\nsequenceSize=2"]
    C --> E[Aggregator]
    D --> E
    E --> F["Output\n['A','B']"]
~~~

### Assertion cần thiết sau Splitter

- **Payload** của từng message con chứa đúng phần tử (ví dụ \`"A"\` và \`"B"\`), không phải nguyên danh sách.
- **Số message** đúng bằng số phần tử dự kiến; không mất hay nhân đôi.
- **Header nghiệp vụ** cần thiết (ví dụ \`requestId\`) được giữ nếu hợp đồng yêu cầu.
- **Correlation** của hai message con giống nhau, khác nhóm khác.
- **Sequence** có đúng hai vị trí 1/2 và 2/2 nếu flow bật/tạo sequence metadata.

Không nên khẳng định UUID của correlation bằng một chuỗi cố định khi framework tự sinh. Lưu correlation ID của message thứ nhất rồi kiểm tra message thứ hai có cùng giá trị; kiểm tra giá trị này khác với correlation ID của một yêu cầu độc lập nếu đó là hợp đồng.

### Tạo message có correlation metadata để test Aggregator

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

static Message<String> part(
        String groupId, int position, int total, String payload) {
    return MessageBuilder.withPayload(payload)
            .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID, groupId)
            .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, position)
            .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, total)
            .setHeader("requestId", "r-01")
            .build();
}
~~~

Một test tốt gửi xen kẽ hai nhóm:

~~~text
Send A1 (correlationId=A, sequenceNumber=1, sequenceSize=2)
  -> chưa có kết quả
Send B1 (correlationId=B, sequenceNumber=1, sequenceSize=2)
  -> chưa có kết quả
Send B2 (correlationId=B, sequenceNumber=2, sequenceSize=2)
  -> có nhóm B: ["B1", "B2"]
Send A2 (correlationId=A, sequenceNumber=2, sequenceSize=2)
  -> có nhóm A: ["A1", "A2"]
~~~

Kiểm tra cả payload tổng hợp, số kết quả, thời điểm phát kết quả và mối liên hệ với nhóm. Nếu có dùng \`MessageGroupStore\` bền vững, release strategy hoặc timeout tùy chỉnh, bổ sung test message trùng, thiếu, đến muộn và expire theo chính sách đó. Không mặc định mọi Aggregator đều chờ đúng \`sequenceSize\` trong mọi cấu hình.

## 8. Gateway, retry và error channel: header nào quan trọng?

### Gateway và replyChannel

Gateway chuyển lời gọi Java thành request message và đưa reply về cho caller. Khi kiểm thử, xác nhận:

- Payload gửi vào gateway đúng kiểu và giá trị.
- Header nghiệp vụ mà gateway có trách nhiệm truyền được gắn đúng.
- Luồng trả về reply đúng hợp đồng, không làm mất các trường nghiệp vụ cần thiết.
- Timeout được cấu hình hữu hạn đối với trường hợp không có reply.

\`replyChannel\` thường là header do hạ tầng request/reply quản lý. Không cần assert chính xác object channel nội bộ trong mọi test. Điều quan trọng hơn là caller nhận được dữ liệu chính xác và một request không bị trả nhiều reply.

### Retry và danh tính nghiệp vụ

Retry có thể chạy một handler nhiều lần với cùng một request. Dùng header \`requestId\` hoặc khóa idempotency nghiệp vụ để theo dõi:

~~~text
Message:
  payload   = "charge-order-7"
  requestId = "req-7"

Attempt 1 -> handler lỗi tạm thời
Attempt 2 -> handler thành công

Assert:
  số lần handler được gọi = 2 (theo cấu hình maxAttempts=2)
  requestId quan sát trong cả hai lần = "req-7"
  output chỉ có một kết quả thành công
~~~

Phân biệt **lần xử lý** với **message nghiệp vụ**: retry có thể làm tăng số lần gọi, nhưng không được tạo hai tác dụng phụ không mong muốn như hai lần thanh toán. Header \`requestId\` là công cụ theo dõi/idempotency nếu ứng dụng thật sự dùng nó; chỉ có header này không tự động bảo đảm idempotency.

### ErrorMessage và dữ liệu thất bại

Trong Spring Integration, lỗi có thể được ném về caller (đường đồng bộ) hoặc phát thành \`ErrorMessage\` (khi có error handler/kênh lỗi phù hợp). Test phải phù hợp mô hình thực thi:

| Mô hình | Hành vi kiểm thử |
| --- | --- |
| \`DirectChannel\`, handler ném lỗi đồng bộ | Assert exception tại \`send()\` hoặc lời gọi Gateway |
| Luồng bất đồng bộ có cơ chế phát lỗi | Đọc \`ErrorMessage\` từ error channel có cấu hình |
| Retry có recovery | Assert message/giá trị recovery hoặc lỗi cuối theo hợp đồng |

Với \`ErrorMessage\`, payload là \`Throwable\` (thường là \`MessagingException\` hoặc loại liên quan), **không** phải payload nghiệp vụ ban đầu. Khi cần truy ra message gốc, kiểm tra \`failedMessage\` của exception hỗ trợ thuộc tính này hoặc metadata được giữ theo cấu hình. Đừng giả định mọi exception có đầy đủ request headers: việc đóng gói và chuyển lỗi phụ thuộc endpoint và cơ chế thực thi.

Đặc biệt, việc thêm \`errorChannel\` vào request không tự biến mọi exception đồng bộ thành một message ở kênh lỗi. Test error channel đúng cách phải tạo flow có error handler phù hợp và kiểm tra cả đường phát lỗi lẫn nội dung lỗi.

## 9. Những assertion nên dùng và những assertion dễ gây lỗi giả

| Nên kiểm tra | Nên tránh nếu không được hợp đồng cam kết |
| --- | --- |
| \`payload\` đúng kiểu, đúng giá trị | Chỉ assert output khác \`null\` |
| Header nghiệp vụ có mặt, đúng kiểu, đúng giá trị | So sánh mọi header với toàn bộ map đầu vào |
| Header đã bị loại thật sự **không còn tồn tại** | Chỉ kiểm tra \`get("key") == null\` khi cần phân biệt vắng mặt |
| Output có đúng số message theo thiết kế | Bỏ qua duplicate message |
| Correlation giống nhau trong một nhóm, không trộn hai nhóm | So sánh correlation tự sinh với chuỗi cố định |
| Sequence đúng khi flow cam kết sequence | Luôn giả định sequence có mặt |
| Exception hoặc ErrorMessage đi đúng đường được cấu hình | Mặc định mọi lỗi đi vào \`errorChannel\` |
| Timeout hữu hạn, phù hợp mô hình bất đồng bộ | Ngủ cố định rồi suy luận không có message |
| Giá trị header do ứng dụng đặt chủ động | So sánh \`id\` hoặc \`timestamp\` auto-generated bằng số cố định |

Để test có khả năng bảo trì, dùng assertion gần sát chỗ gửi message và chỗ nhận message. Nếu có nhiều bước, kiểm tra đầu ra từng bước bằng test riêng trước khi viết một test end-to-end. Khi test thất bại, điều này giúp xác định do Transformer, Router, Header Enricher, Splitter hay Aggregator.

### Chú ý về chuyển đổi kiểu

Payload có thể đi qua chuyển đổi kiểu dữ liệu, ví dụ \`String\` sang DTO hoặc DTO sang JSON. Nếu contract quy định DTO:

~~~java
assertThat(response.getPayload()).isInstanceOf(OrderLine.class);
OrderLine line = (OrderLine) response.getPayload();
assertThat(line.sku()).isEqualTo("SKU-42");
assertThat(line.quantity()).isEqualTo(3);
~~~

Nếu contract quy định JSON string, kiểm tra dữ liệu bằng JSON parser thay vì dựa vào thứ tự trường hay khoảng trắng trong chuỗi JSON. Việc nội dung JSON đúng không thay thế kiểm tra header \`contentType\` hoặc thông tin encoding nếu hệ thống bên nhận dựa vào chúng.

## 10. Kiểm tra tại các ranh giới tích hợp thật

Khi đi qua HTTP, Kafka, AMQP hoặc bộ chuyển đổi tự xây dựng, không phải header nào của \`MessageHeaders\` cũng được ánh xạ sang giao thức ngoài. Điều này là chủ ý: mỗi adapter có quy tắc header mapper, serializer và loại dữ liệu được hỗ trợ.

Ví dụ: trong flow nội bộ, \`tenantId="shop-a"\` là một String. Khi gửi sang HTTP, nó có thể phải được ánh xạ sang header HTTP phù hợp; khi gửi sang broker, nó cần kiểu dữ liệu header được adapter cho phép. Test tại ranh giới ngoài cần khẳng định **giá trị truyền đi/nhận về thực tế** qua adapter, không chỉ kiểm tra map header trước khi gửi.

Một chiến lược nhiều lớp:

1. **Unit test** mapper và điều kiện xử lý payload/header với dữ liệu nhỏ.
2. **Flow test** kiểm tra message qua các endpoint Spring Integration trong bộ nhớ.
3. **Adapter/contract test** kiểm tra serialization, header mapping, encoding, timeout và lỗi của giao thức ngoài.

Hạn chế đưa token truy cập, mật khẩu hoặc dữ liệu bí mật vào log để chứng minh header đi qua. Chỉ ghi thông tin cần thiết cho khả năng quan sát; với định danh yêu cầu hoặc correlation ID, dùng dữ liệu giả khi kiểm thử.

## 11. Checklist và bài thực hành

Trước khi kết luận một test payload/header đạt yêu cầu, đối chiếu các câu hỏi:

- Payload có đúng kiểu và giá trị sau endpoint không?
- Có cần kiểm tra cấu trúc DTO, số phần tử collection hoặc encoding không?
- Header nào bắt buộc phải có, vắng mặt hoặc bị loại?
- Header nghiệp vụ đã được giữ đúng kiểu, không chỉ đúng nội dung hiển thị?
- Router đã gửi đúng một nhánh, và các nhánh khác không nhận message?
- Correlation và sequence có hỗ trợ đúng luồng Splitter/Aggregator?
- Với retry, request ID có giữ nguyên và số lần xử lý có giới hạn?
- Với lỗi, ứng dụng thực sự dùng exception đồng bộ hay ErrorMessage?
- Các assertion có phụ thuộc UUID, timestamp, thứ tự hay timing không được bảo đảm?
- Test có chạy độc lập, không phụ thuộc message còn sót trong channel của test khác?

### Bài thực hành A: thay đổi một header

Mở rộng flow ở mục 5 bằng một endpoint Header Enricher bổ sung \`source="catalog"\`. Tạo request chỉ có \`tenantId="shop-a"\`, sau đó kiểm tra payload \`"SKU-42"\`, tenant được giữ và \`source\` được thêm. Tạo thêm request có sẵn \`source="manual"\`, rồi quyết định rõ trong yêu cầu nghiệp vụ nên giữ hay ghi đè; viết assertion cho chính sách đó.

### Bài thực hành B: dữ liệu sai kiểu

Tạo ba message có \`tenantId\` lần lượt là \`"shop-a"\`, không tồn tại và số nguyên \`42\`. Viết unit test cho hàm \`hasValidTenant\`. Kết nối hàm vào Filter trong một flow nhỏ, sau đó kiểm tra message hợp lệ đi tiếp và hai message còn lại được loại/chuyển vào discard channel theo cấu hình.

### Bài thực hành C: correlation hai nhóm

Gửi hai phần tử cho nhóm A và hai phần tử cho nhóm B theo thứ tự A1, B1, B2, A2. Chỉ dùng payload và ba header \`correlationId\`, \`sequenceNumber\`, \`sequenceSize\` để chứng minh:

1. Không có output trước khi một nhóm đủ phần tử.
2. Kết quả đầu tiên chỉ gồm phần tử nhóm B.
3. Kết quả thứ hai chỉ gồm phần tử nhóm A.
4. Không có kết quả thứ ba.

**Tiêu chí hoàn thành:** Mỗi test chứng minh được payload mang **đúng dữ liệu**, headers giữ **đúng ngữ nghĩa**, và message xuất hiện ở **đúng điểm** trong luồng. Khi các hợp đồng này rõ ràng, việc mở rộng Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry và error handling trở nên an toàn hơn vì sai lệch được phát hiện ngay tại ranh giới nơi nó phát sinh.
