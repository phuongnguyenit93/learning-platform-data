# Kiểm thử flow tuyến tính trong Spring Integration

## 1. Flow tuyến tính là gì và vì sao phải kiểm thử?

Trong **Enterprise Integration Patterns (EIP)**, một luồng thông điệp có thể gồm nhiều endpoint nối tiếp nhau. Trường hợp đơn giản nhất là **flow tuyến tính**: message đi qua các bước xử lý theo một trật tự xác định, từ điểm vào đến điểm ra. Mỗi bước nhận kết quả của bước trước rồi chuyển cho bước kế tiếp.

Ví dụ với Spring Integration:

~~~mermaid
flowchart LR
    A["Input Channel"] --> B["Transformer: trim"]
    B --> C["Filter: không rỗng"]
    C --> D["Header Enricher"]
    D --> E["Transformer: uppercase"]
    E --> F["Service Activator"]
    F --> G["Output Channel"]
    C -.->|Bị loại| H["Discard Channel"]
~~~

Bài này thuộc chương **Kiểm thử pattern** của module **SPRING_INTEGRATION_PATTERN**. Module hướng tới xây dựng các luồng thông điệp ít phụ thuộc và dễ mở rộng bằng Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation; kiểm thử flow tuyến tính là nền tảng để xác minh từng đoạn trước khi ghép thành các luồng có nhiều nhánh.

Sau bài học, bạn có thể:

1. Xác định đầu vào, đầu ra và bất biến của một chuỗi endpoint.
2. Viết flow test bằng Java DSL, JUnit 5 và channel trong bộ nhớ.
3. Kiểm tra cả dữ liệu cuối cùng, header được giữ và số message phát ra.
4. Chứng minh các bước chạy đúng thứ tự, đặc biệt khi thứ tự làm thay đổi kết quả.
5. Kiểm tra điểm dừng của Filter, ngoại lệ ở giữa luồng và các điều kiện timeout.
6. Phân biệt điều được bảo đảm bởi flow đồng bộ với điều cần kiểm tra riêng khi luồng có xử lý bất đồng bộ.

Một flow có hình dạng tuyến tính **không bảo đảm mọi message sẽ luôn tới đích**. Filter có thể loại message; Transformer có thể ném lỗi; Service Activator có thể không trả reply. Chính các điểm kết thúc sớm này cần được mô tả bằng test.

## 2. Xác định hợp đồng trước khi viết test

Giả sử hệ thống nhận mã hàng dạng chuỗi và muốn chuẩn hóa trước khi ghi nhận:

~~~text
Đầu vào:
  payload  = "  sku-7  "
  tenantId = "shop-a"

Bước 1. trim                 -> "sku-7"
Bước 2. filter !isBlank()    -> giữ message
Bước 3. thêm stage           -> stage="validated"
Bước 4. uppercase            -> "SKU-7"
Bước 5. service activator    -> "accepted:SKU-7"

Đầu ra:
  payload  = "accepted:SKU-7"
  tenantId = "shop-a"
  stage    = "validated"
~~~

Từ mô tả này, tạo bảng hợp đồng:

| Điểm cần kiểm tra | Đầu vào tối thiểu | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | Payload \`"  sku-7  "\` và \`tenantId="shop-a"\` | Một output, payload \`"accepted:SKU-7"\` |
| Thứ tự xử lý | Payload chứa khoảng trắng và chữ thường | \`trim\` rồi \`uppercase\`, giữ nguyên ý nghĩa nghiệp vụ |
| Header nghiệp vụ | \`tenantId="shop-a"\` | Header còn tồn tại, không đổi |
| Header được bổ sung | Không có \`stage\` | Output có \`stage="validated"\` |
| Filter loại message | Payload \`"   "\` | Không có output thành công; discard nhận payload đã trim thành chuỗi rỗng |
| Không phát trùng | Một input hợp lệ | Có đúng một output |
| Thứ tự nhiều input | Gửi \`" b "\` rồi \`" a "\` qua flow đồng bộ | Nhận \`"accepted:B"\` rồi \`"accepted:A"\` |
| Lỗi ở giữa luồng | Một endpoint chủ động ném exception trong test | Exception đến caller hoặc đi error channel tùy mô hình thực thi |

**Chọn dữ liệu có tính phân biệt.** Payload \`"sku-7"\` không cho biết Transformer \`trim\` có chạy hay không. Payload \`"  sku-7  "\` chứng minh được việc cắt khoảng trắng. Payload \`"   "\` chứng minh được rằng **Filter chạy sau Transformer**, vì sau khi trim thì payload thành \`""\`.

## 3. Các mức kiểm thử cho một flow

| Mức | Kiểm tra gì? | Công cụ phù hợp |
| --- | --- | --- |
| Unit test | Hàm chuẩn hóa, điều kiện lọc, phép biến đổi nghiệp vụ | JUnit, AssertJ; không cần Spring context |
| Flow test | Cấu hình channel, thứ tự endpoint, message và headers | \`@SpringJUnitConfig\`, Spring Integration Java DSL, \`QueueChannel\` |
| Boundary/adapter test | Mapping qua HTTP, AMQP, Kafka, database hoặc gateway bên ngoài | Test adapter, stub, Testcontainers hoặc môi trường tích hợp phù hợp |
| End-to-end test | Cả quá trình nghiệp vụ qua nhiều hệ thống | Test ít nhưng có dữ liệu và điều kiện vận hành rõ ràng |

Một unit test có thể xác nhận \`"  sku-7  "\` biến thành \`"sku-7"\`, nhưng không chứng minh rằng Transformer được nối vào đúng channel. Flow test thực thi các endpoint trong Spring Integration nên phát hiện thêm lỗi wiring, tên channel, Filter, header và kết quả cuối. Đây là mức trọng tâm của bài học.

Với Spring Boot, bộ dependency thường gồm:

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

Các đoạn Java dưới đây dùng **Java 17, Spring Integration 6.x, JUnit 5 và AssertJ**. Dùng phiên bản Spring Boot và Spring Integration tương thích trong dự án thực tế. Ví dụ chỉ dùng bộ nhớ; không cần khởi động broker hoặc cơ sở dữ liệu.

## 4. Ví dụ hoàn chỉnh: kiểm thử một flow tuyến tính

Tạo file test \`src/test/java/example/LinearFlowTest.java\` như sau. Flow dùng các channel đồng bộ theo mặc định và kết thúc bằng \`QueueChannel\` để dễ nhận kết quả:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;

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

@SpringJUnitConfig(LinearFlowTest.Config.class)
class LinearFlowTest {

    @Autowired
    ApplicationContext context;

    private MessageChannel input() {
        return context.getBean("codes.in", MessageChannel.class);
    }

    private QueueChannel out() {
        return context.getBean("codes.out", QueueChannel.class);
    }

    private QueueChannel discard() {
        return context.getBean("codes.discard", QueueChannel.class);
    }

    private static Message<String> message(String code) {
        return MessageBuilder.withPayload(code)
                .setHeader("tenantId", "shop-a")
                .build();
    }

    @Test
    void valid_input_passes_through_all_steps() {
        assertThat(input().send(message("  sku-7  "))).isTrue();

        Message<?> result = out().receive(1_000);
        assertThat(result).isNotNull();
        assertThat(result.getPayload()).isEqualTo("accepted:SKU-7");
        assertThat(result.getHeaders().get("tenantId")).isEqualTo("shop-a");
        assertThat(result.getHeaders().get("stage")).isEqualTo("validated");

        assertThat(out().receive(0)).isNull();     // Không phát trùng
        assertThat(discard().receive(0)).isNull(); // Không bị loại
    }

    @Test
    void blank_input_stops_at_filter_after_trim() {
        assertThat(input().send(message("   "))).isTrue();

        Message<?> rejected = discard().receive(1_000);
        assertThat(rejected).isNotNull();
        assertThat(rejected.getPayload()).isEqualTo("");
        assertThat(rejected.getHeaders().get("tenantId")).isEqualTo("shop-a");
        assertThat(rejected.getHeaders()).doesNotContainKey("stage");
        assertThat(out().receive(0)).isNull();
    }

    @Test
    void synchronous_flow_preserves_send_order() {
        input().send(message(" b "));
        input().send(message(" a "));

        Message<?> first = out().receive(1_000);
        Message<?> second = out().receive(1_000);

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getPayload()).isEqualTo("accepted:B");
        assertThat(second.getPayload()).isEqualTo("accepted:A");
        assertThat(out().receive(0)).isNull();
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean("codes.out")
        QueueChannel output() {
            return new QueueChannel();
        }

        @Bean("codes.discard")
        QueueChannel discardOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow normalizeCodes() {
            return IntegrationFlow.from("codes.in")
                    .transform(String.class, String::trim)
                    .filter(String.class, text -> !text.isBlank(),
                            filter -> filter.discardChannel("codes.discard"))
                    .enrichHeaders(headers ->
                            headers.header("stage", "validated"))
                    .transform(String.class,
                            text -> text.toUpperCase(Locale.ROOT))
                    .handle(String.class,
                            (payload, headers) -> "accepted:" + payload)
                    .channel("codes.out")
                    .get();
        }
    }
}
~~~

Các test có ba kết quả khác nhau nhưng cùng sử dụng một flow:

- **Happy path:** Một input sinh một output với payload chuẩn hóa và header giữ đúng.
- **Dừng sớm:** Filter loại payload rỗng, gửi message vào discard channel; header \`stage\` chưa xuất hiện vì Header Enricher nằm **sau** Filter.
- **Thứ tự:** Khi không dùng executor và các endpoint trên đường đi đều xử lý đồng bộ, hai lệnh \`send\` nối tiếp tạo hai kết quả theo đúng thứ tự gửi.

Các test đều đọc hết message do chính mình gửi vào output/discard channel. Nếu bật chạy test song song và dùng chung Spring context, cần cô lập hàng đợi/context hoặc tắt parallel cho các test chia sẻ channel để tránh test này đọc nhầm message của test khác.

### Tại sao dùng QueueChannel ở cuối?

\`DirectChannel\` chuyển message trực tiếp cho handler đăng ký và thường thực thi trên thread của caller. \`QueueChannel\` giữ message để test có thể lấy ra bằng \`receive(timeout)\`. Đây là **cách quan sát output** thuận tiện; bản thân QueueChannel không tạo một worker thread riêng để xử lý các bước trước đó.

\`receive(1_000)\` giới hạn thời gian đợi message, tránh treo test nếu wiring sai. Với flow đồng bộ trên, \`receive(0)\` giúp xác nhận hàng đợi không còn message **ngay sau khi lệnh send hoàn tất**. Nếu luồng có xử lý bất đồng bộ, phép kiểm tra tức thời này không chứng minh rằng sẽ không có message đến muộn.

## 5. Chứng minh thứ tự các bước, không chỉ kết quả cuối

Có những phép biến đổi cho cùng kết quả dù chạy sai thứ tự, nên một assertion ở output không đủ để xác định mọi bước đã chạy đúng. Chọn dữ liệu khiến thứ tự ảnh hưởng đến kết quả hoặc quan sát tại điểm giữa.

Ví dụ:

~~~text
Input: "   "

Đúng: trim -> "" -> filter(!isBlank) -> discard payload ""
Sai:  filter(!isBlank) trước trim -> discard payload "   "
~~~

Nếu yêu cầu là loại cả chuỗi chỉ chứa khoảng trắng, test \`"   "\` phải kết thúc ở discard. Payload \`""\` ở discard còn chứng minh Transformer \`trim\` đã chạy **trước** Filter.

Một ví dụ khác, khi các bước xử lý có điều kiện dựa trên trạng thái:

~~~text
Input: " abc "

1. trim         -> "abc"
2. validate     -> hợp lệ
3. uppercase    -> "ABC"
4. prefix       -> "accepted:ABC"
~~~

Ở mỗi mốc, hãy xác định một dấu hiệu có thể quan sát được: payload thay đổi, header được thêm, message bị loại hoặc handler được gọi. Tránh tạo biến toàn cục chỉ để ghi log các bước trong production code; nếu cần kiểm tra tương tác, có thể dùng spy ở ranh giới service hoặc channel tap trong cấu hình test.

### Quan sát thông điệp giữa flow bằng Wire Tap

Spring Integration cung cấp **Wire Tap**, cho phép gửi bản message đi qua một channel tới kênh quan sát. Có thể mở rộng flow thử nghiệm để nhìn payload sau Transformer đầu tiên:

~~~java
@Bean("codes.afterTrim")
QueueChannel afterTrim() {
    return new QueueChannel();
}

// Trong định nghĩa flow:
return IntegrationFlow.from("codes.in")
        .transform(String.class, String::trim)
        .wireTap("codes.afterTrim")
        .filter(String.class, text -> !text.isBlank())
        // ... các bước còn lại
        .get();
~~~

Sau khi gửi \`"  sku-7  "\`, nhận từ \`codes.afterTrim\` phải được payload \`"sku-7"\`. Wire Tap giúp xác minh một **ranh giới** mà không phải đổi logic biến đổi chính. Đây là đoạn minh họa để bổ sung vào flow phù hợp, chưa phải một lớp Java độc lập có thể biên dịch. Khi chèn tap vào code thực tế, đảm bảo channel quan sát được đăng ký và được đọc hết trong test; nếu tap dùng hàng đợi có dung lượng giới hạn hoặc xử lý có tác dụng phụ, chính tap cũng có thể ảnh hưởng quá trình thử nghiệm.

Với flow nhiều bước, ưu tiên quan sát có chọn lọc (ví dụ trước/sau khâu quan trọng) thay vì gắn tap ở mọi channel. Việc quan sát liên tục làm test khó bảo trì nếu chỉ đổi cách tổ chức các bước mà hợp đồng bên ngoài không đổi.

## 6. Kiểm thử lỗi tại một bước ở giữa flow

Một luồng tuyến tính có thể dừng do exception trước khi sinh output. Với \`DirectChannel\` và các endpoint đồng bộ, exception thường truyền ngược về caller của \`send()\` hoặc Gateway. Để kiểm tra điều này, tạo một flow nhỏ có handler luôn ném lỗi, tách biệt với flow chuẩn hóa:

~~~java
@Bean
IntegrationFlow failingFlow() {
    return IntegrationFlow.from("failure.in")
            .transform(String.class, String::trim)
            .handle(String.class, (payload, headers) -> {
                throw new IllegalStateException("simulated failure");
            })
            .get();
}
~~~

Trong test có context đã đăng ký flow trên:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.messaging.MessagingException;

@Test
void synchronous_failure_propagates_to_sender() {
    MessageChannel failureInput =
            context.getBean("failure.in", MessageChannel.class);

    assertThatThrownBy(() ->
            failureInput.send(
                    MessageBuilder.withPayload(" bad ").build()))
            .isInstanceOf(MessagingException.class)
            .hasRootCauseInstanceOf(IllegalStateException.class);
}
~~~

Đoạn này kiểm tra **nguyên nhân** được bọc trong ngoại lệ nhắn tin, tránh chỉ assert một thông báo lỗi dễ thay đổi. Với cách cấu hình endpoint khác, loại wrapper cụ thể có thể khác; hãy kiểm tra exception thực tế của dự án. Nếu một phần đường đi có \`ExecutorChannel\` hoặc adapter bất đồng bộ, exception thường không tới \`send()\` theo cùng cách: cần kiểm tra \`ErrorMessage\` qua error handler/error channel đã cấu hình.

Tình huống lỗi cần kiểm tra gồm:

| Lỗi phát sinh ở đâu? | Điều cần xác nhận |
| --- | --- |
| Transformer | Không có output thành công; caller hoặc error handler nhận nguyên nhân đúng |
| Filter | Message bị loại có chủ đích theo chính sách discard, phân biệt với lỗi kỹ thuật |
| Header Enricher | Không mất headers cần thiết khi xử lý bình thường; exception đúng đường nếu expression lỗi |
| Service Activator | Không tự coi \`null\` reply là thành công nếu nghiệp vụ yêu cầu output |
| Adapter bên ngoài | Lỗi kết nối, timeout, retry và recovery tuân theo hợp đồng của adapter |

**Phân biệt Filter loại message với exception:** Filter trả \`false\` có thể là kết quả nghiệp vụ hợp lệ và không tạo output ở nhánh chính; không nên kiểm tra nó như một sự cố hệ thống trừ khi yêu cầu nghiệp vụ quy định như vậy.

## 7. Tương tác với Gateway, retry và correlation

Flow tuyến tính thường là một đoạn trong luồng lớn hơn. Khi nó nằm sau Gateway, đi qua retry advice hoặc kết nối với một Splitter/Aggregator, các điểm kiểm thử cần thêm thông tin.

### Gateway: một request phải có một phản hồi hợp lệ

Gateway biến lời gọi Java thành request message, chờ hoặc nhận reply theo cấu hình. Ví dụ một phương thức \`String normalize(String code)\` cần trả về \`"accepted:SKU-7"\` với input \`"  sku-7  "\`.

Nếu cuối flow chỉ có Filter loại message mà không tạo reply, Gateway đồng bộ có thể đợi tới timeout. Hãy đặt timeout hữu hạn và kiểm tra kết quả/exception theo hợp đồng. Không coi việc \`send()\` của request channel trả \`true\` là bằng chứng rằng Gateway đã có reply.

### Retry: các bước có thể được thực thi nhiều lần

Giả sử Service Activator gọi hệ thống ngoài và thất bại tạm thời. Khi có \`RequestHandlerRetryAdvice\`, một message có thể khiến handler được gọi nhiều lần. Test nên chứng minh:

1. Handler lỗi ở lần đầu và thành công ở lần thứ hai nếu cấu hình retry cho phép hai attempts.
2. Có đúng một kết quả thành công được phát tới kênh trả về.
3. Header \`requestId\` nghiệp vụ được giữ để tra cứu và hỗ trợ idempotency.
4. Nếu lỗi liên tục, quá trình dừng đúng giới hạn và đi đúng đường recovery/error.

Lưu ý: retry **có thể** bao bọc một endpoint riêng hoặc một đoạn flow tùy cách cấu hình. Không mặc định mọi Transformer và Filter phía trước đều được thực thi lại mỗi khi Service Activator retry. Test hãy đo số lần tại chính ranh giới được gắn advice.

### Correlation: lúc nào cần kiểm tra?

Trong flow tuyến tính một message vào, một message ra, correlation chỉ là header nghiệp vụ nếu hệ thống cần. Khi xuất hiện Splitter/Aggregator, luồng có thể đổi số lượng message và dùng correlation/sequence để ghép nhóm. Hãy kiểm tra các bất biến riêng:

~~~text
Trước Splitter:     1 message, requestId="r1"
Sau Splitter:       2 message, cùng correlationId="g1"
Sau Aggregator:     1 message, kết quả chỉ từ nhóm "g1"
~~~

Nếu dùng hai nhóm \`g1\` và \`g2\` gửi xen kẽ, output phải giữ đúng dữ liệu từng nhóm. Đây là phần mở rộng **sau** khi flow tuyến tính của từng nhánh đã hoạt động chính xác; không cần tự thêm \`sequenceNumber\` vào mọi test tuyến tính.

## 8. Khi nào thứ tự không còn được bảo đảm?

Điểm cần phân biệt là **thứ tự các endpoint trong định nghĩa flow** và **thứ tự hoàn thành của nhiều message**:

~~~mermaid
flowchart TD
    A["DirectChannel\nXử lý đồng bộ"] --> B["Bước 1"]
    B --> C["Bước 2"]
    C --> D["Output theo thứ tự send tuần tự"]
    E["ExecutorChannel\nNhiều worker"] --> F["Bước 1 cho A/B"]
    F --> G["Bước 2 cho A/B"]
    G --> H["Output có thể hoàn tất đảo thứ tự"]
~~~

Trong flow đồng bộ nối tiếp, một lệnh \`send()\` thường kết thúc sau khi xử lý xong các endpoint đồng bộ phía sau, hoặc khi gặp lỗi. Khi chèn \`ExecutorChannel\`, tác vụ có thể chuyển sang thread khác. Nếu có nhiều worker, message B có thể hoàn thành trước A, dù cả hai đều đi qua Bước 1 rồi Bước 2.

Điều chỉnh test theo hợp đồng:

| Kiến trúc | Assertion phù hợp |
| --- | --- |
| \`DirectChannel\` đồng bộ, gửi tuần tự | \`containsExactly("A", "B")\` nếu không có thay đổi thứ tự khác |
| Executor nhiều worker, không cam kết thứ tự | Nhận đủ số message và \`containsExactlyInAnyOrder("A", "B")\` |
| Bắt buộc giữ thứ tự dù xử lý song song | Cấu hình sequence/resequencing hoặc cơ chế ordering, rồi test thứ tự theo chính sách đó |
| Flow có PollableChannel | Thử nghiệm cần kích hoạt poller hoặc tiêu thụ qua cơ chế tương ứng |

Tránh kiểm thử bất đồng bộ bằng \`Thread.sleep(500)\` rồi đoán hệ thống đã xử lý xong. Dùng điều kiện chờ, \`receive(timeout)\` và timeout có giới hạn. Nếu xác nhận **không có message** trong luồng bất đồng bộ, cần một cửa sổ chờ có ý nghĩa hoặc tín hiệu cho biết tất cả tác vụ đã kết thúc.

## 9. Quan sát số message và đường đi

Một flow tuyến tính thông thường dự kiến **một input hợp lệ → một output**. Nhưng số lượng message thay đổi nếu có Splitter, Aggregator, publish-subscribe, Filter hoặc endpoint chủ động phát nhiều output.

Viết rõ quy tắc của đoạn đang test:

~~~text
Input       -> 1 message
Transformer -> 1 message
Filter      -> 0 nếu loại, 1 nếu giữ
Enricher    -> 1 message khi message được giữ
Activator   -> 1 reply khi handler trả về một giá trị
Output      -> 0 hoặc 1 message (theo quy tắc trên)
~~~

Ở happy path, sau khi nhận output đầu tiên, kiểm tra không còn output thứ hai nếu toàn bộ đường đi đồng bộ. Ở invalid path, kiểm tra cả output chính rỗng và discard channel có đúng một message. Khi thêm Router hoặc publish-subscribe, phép kiểm tra số lượng phải theo hợp đồng phân nhánh, không áp dụng máy móc quy tắc 1 → 1.

Để theo dõi nhánh trong production, có thể ghi log \`id\`, \`correlationId\` hoặc \`requestId\` và kênh phát sinh sự kiện. Test nên xác minh dữ liệu và kênh quan sát thực tế; không phụ thuộc vào số dòng log vì mức log và cơ chế ghi bất đồng bộ có thể thay đổi.

## 10. Những lỗi kiểm thử phổ biến

| Cách viết test dễ sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ assert output không \`null\` | Không phát hiện payload sai | Kiểm tra giá trị và kiểu payload |
| Chỉ test input đã chuẩn hóa | Không biết Transformer có chạy không | Dùng input khác output, ví dụ \`"  sku-7  "\` |
| Chỉ test input hợp lệ | Bỏ sót Filter nối sai hoặc không chạy | Thêm payload \`"   "\` và kiểm tra discard |
| Chỉ nhìn output mà bỏ qua headers | Có thể mất tenant/correlation | Assert headers thuộc hợp đồng nghiệp vụ |
| Tự giả định message nào cũng có reply | Gateway có thể chờ timeout | Test trường hợp không có reply với timeout hữu hạn |
| Luôn khẳng định thứ tự output | Test có thể flaky khi chèn executor | Chỉ assert thứ tự nếu kiến trúc bảo đảm |
| Kiểm tra output rỗng ngay sau \`send()\` bất đồng bộ | Có thể bỏ sót message đến muộn | Đồng bộ hóa hoặc dùng cửa sổ quan sát |
| Dùng chung queue còn dữ liệu giữa test | Test đọc nhầm message | Drain queue, cô lập context hoặc dùng correlation |
| Chạy broker và database cho mọi test | Test chậm và khó xác định nguyên nhân | Tách unit/flow/adapter tests |
| Chỉ kiểm tra log | Log không phản ánh đầy đủ hợp đồng | Assert vào output, exception và header |

Một bộ test hiệu quả nên báo lỗi ở nơi dễ xử lý: predicate sai thì unit test báo; wiring sai thì flow test báo; mapping adapter sai thì adapter test báo. Không cần biến mọi trường hợp thành một bài end-to-end dài.

## 11. Bài thực hành

Sử dụng lớp \`LinearFlowTest\` ở mục 4 và thực hiện các bài sau.

### Bài A — xác minh thứ tự Trim → Filter

Tạo input \`"   "\` và \`" a "\`. Chứng minh:

- \`"   "\` bị loại sau bước trim, có payload \`""\` tại discard channel.
- \`" a "\` đi đến output với payload \`"accepted:A"\`.
- \`stage\` chỉ xuất hiện trên message đã vượt qua Filter.

### Bài B — tăng cường kiểm tra header

Gắn thêm header \`requestId="req-19"\` vào input. Assert \`requestId\` còn tồn tại trên output, đúng kiểu String và đúng giá trị. Thử thêm một Header Enricher có hành vi ghi đè, rồi viết test phân biệt chính sách **giữ giá trị cũ** và **ghi đè**.

### Bài C — đặt lỗi tại Service Activator

Tạo flow test có handler ném \`IllegalStateException\`. Với \`DirectChannel\`, khẳng định caller nhận lỗi và không có success output. Sau đó chuyển điểm xử lý lỗi sang một luồng bất đồng bộ có error handler và viết test kiểm tra \`ErrorMessage\` ở error channel.

### Bài D — thêm một nhánh sau flow tuyến tính

Sau khi luồng chuẩn hóa hoạt động, thêm Router để tách mã hàng có tiền tố \`VIP-\` và mã thông thường. Tạo một message cho mỗi nhánh; kiểm tra cả kênh được chọn và kênh còn lại. So sánh bộ assertion mới với test tuyến tính để thấy tại sao quy tắc **1 input → 1 output chính** phải được điều chỉnh khi có nhiều nhánh.

### Tiêu chí hoàn thành

Một bộ kiểm thử flow tuyến tính đạt yêu cầu khi mỗi tình huống trả lời được: **message bắt đầu ở đâu, trải qua các phép biến đổi nào, dừng hay đi tiếp theo điều kiện nào, và tạo ra đúng bao nhiêu output với payload/header gì**. Đồng thời, các test phải độc lập, có timeout hữu hạn và chỉ khẳng định thứ tự khi cấu hình thực sự bảo đảm.

Từ nền tảng này, bạn có thể ghép các đoạn tuyến tính thành Router/Filter/Transformer nhiều nhánh, thêm Gateway, retry và error channel, hoặc đặt Splitter/Aggregator với correlation mà vẫn biết cách xác định chính xác đoạn nào làm thay đổi hành vi của message.
