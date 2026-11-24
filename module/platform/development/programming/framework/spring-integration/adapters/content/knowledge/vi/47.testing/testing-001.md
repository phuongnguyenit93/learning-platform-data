# Test channel cho adapter trong Spring Integration

## 1. Mục tiêu và phạm vi

Trong Spring Integration, adapter kết nối **nguồn hoặc đích bên ngoài** với luồng message nội bộ. Inbound adapter tạo message từ file, SFTP, broker, HTTP hay cơ sở dữ liệu; outbound adapter nhận message rồi tạo tác động tại hệ thống ngoài. Gateway cung cấp giao tiếp yêu cầu–phản hồi khi phù hợp, poller lấy dữ liệu theo lịch, còn **MessageChannel** nối các endpoint và quyết định cơ chế chuyển giao.

**Test channel cho adapter** là kiểm tra ranh giới giữa adapter và hệ thống xử lý message: adapter đã phát/nhận đúng thông điệp chưa; channel chuyển đúng nơi, đúng contract và đúng cơ chế đồng bộ hay không; lỗi, timeout, retry và vòng đời kết nối được quan sát thế nào. Chỉ kiểm tra hàm biến đổi payload chưa đủ để chứng minh adapter hoạt động.

Trong module *Spring Integration Adapters*, bài học gắn test channel với các adapter **file, SFTP, HTTP, JMS, AMQP, Kafka và database**, theo cấu trúc inbound/outbound, gateway, poller, MessageChannel, hợp đồng message, lỗi và lifecycle.

Mục tiêu:

- Phân biệt **unit test logic**, **test channel/flow**, **test adapter** và **integration test với hệ thống ngoài thật được cô lập**.
- Chọn điểm quan sát phù hợp cho `DirectChannel`, `QueueChannel`, `PublishSubscribeChannel` và channel bất đồng bộ.
- Viết bài test JUnit 5 với payload, header, routing, reply và error.
- Kiểm tra poller, file filter, retry, duplicate, timeout và transaction boundary.
- Xác minh side effect tại đích thay vì chỉ thấy `send()` thành công.
- Làm cho test **có timeout hữu hạn, không phụ thuộc dữ liệu cũ và dễ chạy CI**.

> Ví dụ tập trung Spring Integration Java DSL, JUnit 5 và các API ổn định về mặt ý tưởng trong dòng Spring Integration hiện đại. Cần đối chiếu version đang dùng để chọn đúng module, overload và cấu hình endpoint; các đoạn test minh họa ranh giới riêng sẽ ghi rõ fixture cần có.

## 2. Hình dung đường đi của message

~~~mermaid
flowchart LR
    SRC["File / SFTP / HTTP / JMS / AMQP / Kafka / DB"] --> IN["Inbound adapter hoặc gateway"]
    IN --> IC["inputChannel"]
    IC --> LOGIC["Filter / transform / route / handle"]
    LOGIC --> OC["outputChannel"]
    OC --> OUT["Outbound adapter hoặc gateway"]
    OUT --> DEST["Hệ thống đích"]
    LOGIC -. "lỗi" .-> ERR["errorChannel / retry / DLQ"]
~~~

Có bốn mức bằng chứng khác nhau:

| Câu hỏi | Điểm kiểm tra | Bằng chứng cần có |
|---|---|---|
| Nguồn được đọc đúng chưa? | External system và inbound adapter | File/record/request được nhận, filter hợp lệ |
| Message vào flow đúng chưa? | Input channel | Payload/header/loại message đúng contract |
| Flow xử lý đúng chưa? | Output channel hoặc reply | Routing, transform, correlation, exception |
| Hệ thống đích có nhận kết quả chưa? | Outbound adapter và hệ thống đích | File tạo xong, HTTP request, broker record, DB row |

Ví dụ một message trên channel đầu ra **không chứng minh** FTP/SFTP đã upload thành công; một message được gửi vào input channel **không chứng minh** consumer bên broker đã xử lý nghiệp vụ. Mỗi bài test cần ghi rõ mức chứng minh.

## 3. Phân biệt các channel trước khi test

| Channel | Semantics | Cách quan sát phù hợp |
|---|---|---|
| `DirectChannel` | `SubscribableChannel`, thường dispatch đồng bộ trên thread người gửi đến một subscriber được chọn | Gắn handler/test endpoint, assert sau `send()` khi flow đồng bộ |
| `QueueChannel` | `PollableChannel`, lưu message để consumer `receive(timeout)` | Kiểm tra output ở queue có thời hạn |
| `PublishSubscribeChannel` | Phát tới nhiều subscriber; có thể đồng bộ hoặc dùng executor | Assert từng subscriber, fan-out và việc một subscriber lỗi |
| `ExecutorChannel` | Dispatch qua executor, không còn đồng bộ theo thread caller | Dùng latch hoặc await đến trạng thái quan sát được |
| `RendezvousChannel` | Rendezvous giữa bên gửi và bên nhận | Kiểm tra pairing và timeout của cả hai phía |
| `PriorityChannel` | Chọn thứ tự theo priority | Assert thứ tự theo priority và chính sách khi bằng nhau |
| `FluxMessageChannel` | Reactive stream với subscription và backpressure | Dùng công cụ test reactive, không kỳ vọng `receive()` kiểu pollable |

**Bẫy rất thường gặp:** `DirectChannel` không phải pub/sub. Nếu có hai subscriber, mặc định **không phải cả hai đều nhận cùng một message**. Nếu bài test cần nhiều bên cùng thấy message, dùng một channel fan-out đúng nghĩa hoặc kỹ thuật quan sát phụ như wire tap.

Khi thay một `DirectChannel` của production bằng `QueueChannel` trong test, semantics đồng bộ, xử lý exception và transaction có thể thay đổi. Hãy làm rõ đó là **test harness**, không dùng kết quả này để khẳng định mọi hành vi end-to-end giống production.

## 4. Thiết kế hợp đồng message

Trong Spring Integration, message có **payload** và **headers**. Contract phải mô tả cả hai:

| Thuộc tính | Kiểm thử |
|---|---|
| Payload type | `File`, `String`, `byte[]`, DTO, key/value... |
| Schema và encoding | CSV UTF-8, JSON, date/time, trường bắt buộc |
| Business identity | `eventId`, `orderId`, `correlationId` |
| Routing | Header `eventType`, `sourceSystem`, đích xử lý |
| Metadata transport | Tên file, remote path, broker key/partition, HTTP status |
| Reply | Kết quả request–reply, header và timeout |
| Error | Có exception, `errorChannel`, retry hay reject |
| Delivery | Có thể lặp hay không, idempotency key, ack/commit |
| Security | Không rò token/mật khẩu trong payload, log hoặc header trao đổi |

**Không dùng `MessageHeaders.ID` do framework sinh làm business ID bền vững qua nhiều endpoint**: message mới có thể nhận ID khác. Dùng correlation/business key riêng khi cần đối soát từ adapter này sang adapter khác.

Contract cần phân biệt **header do adapter chắc chắn tạo**, **header tùy thuộc cấu hình**, và **header nghiệp vụ do flow tự đặt**. Test đừng dựa vào một header transport không được công bố là ổn định.

## 5. Chiến lược test theo nhiều lớp

| Tầng | Chạy gì? | Chứng minh điều gì? |
|---|---|---|
| Unit | Mapper, transformer, filter, router thuần | Logic độc lập và lỗi dữ liệu |
| Channel/flow | Spring context gọn với channel và endpoint | Wiring, routing, payload/header, error flow |
| Adapter contract | Adapter + filesystem, test server hoặc test double | Message/protocol mapping, nguồn/đích tương tác |
| Integration | SFTP/JMS/AMQP/Kafka/DB test infrastructure | Ack, retry, offset/transaction, reconnect, side effect |
| End-to-end | Chuỗi từ nguồn đến đích ở môi trường cô lập | Kết quả nghiệp vụ và observability xuyên adapter |

Một bài test `Mockito.verify(sender)` có thể chứng minh handler đã gọi collaborator, nhưng **không** chứng minh RabbitMQ/Kafka thực sự nhận record. Ngược lại, chạy một cluster thật cho mọi unit test làm chậm suite và khó định vị lỗi. Dùng mỗi tầng cho đúng rủi ro.

## 6. Ví dụ 1 — Test channel và transformer bằng JUnit 5

Đây là test cho **hợp đồng channel nội bộ** mà inbound adapter có thể gửi message vào. Nó cố ý không chứa file/SFTP để test chạy nhanh và xác định nguyên nhân lỗi.

Cấu hình Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
class ChannelContractConfig {

    @Bean
    MessageChannel adapterInput() {
        return new DirectChannel();
    }

    @Bean
    PollableChannel observedOutput() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow normalizeFlow() {
        return IntegrationFlow.from("adapterInput")
                .<String, String>transform(String::trim)
                .channel("observedOutput")
                .get();
    }
}
~~~

Test JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ChannelContractConfig.class)
class ChannelContractTest {

    @Autowired
    @Qualifier("adapterInput")
    MessageChannel adapterInput;

    @Autowired
    @Qualifier("observedOutput")
    PollableChannel observedOutput;

    @Test
    void preservesHeadersAndTrimsPayload() {
        Message<String> input = MessageBuilder
                .withPayload("  order-42  ")
                .setHeader("sourceSystem", "sftp")
                .setHeader("correlationId", "corr-42")
                .build();

        assertTrue(adapterInput.send(input));

        Message<?> result = observedOutput.receive(1000);
        assertNotNull(result);
        assertEquals("order-42", result.getPayload());
        assertEquals("sftp", result.getHeaders().get("sourceSystem"));
        assertEquals("corr-42", result.getHeaders().get("correlationId"));
        assertNull(observedOutput.receive(50));
    }
}
~~~

Bài test chứng minh đúng flow `adapterInput → transform → observedOutput` và bảo toàn header nghiệp vụ. Nó **không** chứng minh SFTP đã tải file hay outbound adapter đã ghi kết quả ở đích. Test thất bại nếu không có subscriber/endpoint phù hợp hoặc transformer làm hỏng contract.

### 6.1. Channel không có subscriber

Một `DirectChannel` không có subscriber không thể chuyển message. Tùy vị trí và cấu hình, lời gọi `send()` có thể ném `MessageDeliveryException`; không nên viết test chỉ assert `send() == false` rồi coi mọi trường hợp lỗi đều có cùng semantics.

### 6.2. Quan sát qua queue và giới hạn race

`QueueChannel.receive(timeout)` là điểm quan sát tốt cho bài test, nhưng **không được có một consumer khác cũng đang hút cùng queue**. Nếu có competing consumer hoặc poller, message có thể đã được xử lý hợp lệ nhưng test nhận `null` và báo sai. Hãy dùng output queue riêng cho bài test, hoặc gắn handler/spy vào endpoint phù hợp.

## 7. Ví dụ 2 — Kiểm thử FileReadingMessageSource

File inbound source ánh xạ file từ thư mục thành message chứa đối tượng `File`. Đây là kiểm thử sát **adapter source** hơn, nhưng chưa chạy scheduler/poller.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.SimplePatternFileListFilter;
import org.springframework.messaging.Message;

class FileReadingSourceTest {

    @TempDir
    Path inputDirectory;

    @Test
    void readsOnlyCsvMatchingTheFilter() throws Exception {
        Files.writeString(
                inputDirectory.resolve("orders.csv"),
                "orderId,total\n42,100\n",
                StandardCharsets.UTF_8
        );
        Files.writeString(
                inputDirectory.resolve("ignore.tmp"),
                "not an order",
                StandardCharsets.UTF_8
        );

        FileReadingMessageSource source = new FileReadingMessageSource();
        source.setDirectory(inputDirectory.toFile());
        source.setFilter(new SimplePatternFileListFilter("*.csv"));
        source.afterPropertiesSet();

        Message<File> incoming = source.receive();

        assertNotNull(incoming);
        assertEquals("orders.csv", incoming.getPayload().getName());
        assertTrue(incoming.getPayload().isFile());
    }
}
~~~

Để test **cả inbound adapter và poller**, tạo một context khác gồm flow:

~~~java
// Minh họa khai báo trong @Configuration test.
@Bean
IntegrationFlow fileInboundFlow(
        @Value("#{environment['app.test.inbound-dir']}") File inputDir
) {
    return IntegrationFlow.from(
            org.springframework.integration.file.dsl.Files
                    .inboundAdapter(inputDir)
                    .patternFilter("*.csv"),
            e -> e.poller(
                    Pollers.fixedDelay(java.time.Duration.ofMillis(100))
                           .maxMessagesPerPoll(1)
            )
    ).channel("fileMessages").get();
}
~~~

Fixture phải cung cấp giá trị property `app.test.inbound-dir`, bean `fileMessages` và lifecycle cho flow. Tạo file trong thư mục test, sau đó nhận ở `fileMessages` bằng timeout hữu hạn. Hai vấn đề cần kiểm tra riêng:

1. `patternFilter("*.csv")` lọc theo tên, **không tự bảo đảm accept-once**. Để chống xử lý lặp, bổ sung filter/metadata store phù hợp và test restart.
2. Inbound File source có thể phát payload `File`, còn một transformer đọc nội dung file mới tạo `byte[]` hay `String`. Assert payload tại **đúng channel**.

Không dùng thư mục production hoặc dữ liệu cũ của developer làm fixture; `@TempDir` giúp test độc lập và tự dọn.

## 8. Ví dụ 3 — Kiểm chứng outbound bằng side effect

Outbound adapter thường là **one-way**: channel nhận message, handler dùng nó để ghi file, upload SFTP, publish broker hoặc cập nhật database. Test chỉ thấy `send()` thành công chưa đủ; cần quan sát hệ thống đích.

Contract minh họa của File outbound:

~~~text
Input:
  payload = "orderId,total\n42,100\n"
  header targetFileName = "orders-42.csv"

Expected side effect:
  file orders-42.csv xuất hiện trong output directory cô lập
  nội dung bytes/encoding đúng
  không ghi đè file tồn tại nếu contract cấm
  lỗi I/O được đưa tới caller/error flow theo cấu hình
~~~

Một đoạn assertion, giả sử flow đã cung cấp `outboundInput` và fixture `outputDirectory`:

~~~java
@Test
void outboundFileAdapterCreatesTheExpectedFile() throws Exception {
    Message<String> outgoing = MessageBuilder
            .withPayload("orderId,total\n42,100\n")
            .setHeader("targetFileName", "orders-42.csv")
            .build();

    assertTrue(outboundInput.send(outgoing));

    Path expected = outputDirectory.resolve("orders-42.csv");
    assertTrue(Files.exists(expected));
    assertEquals(
            "orderId,total\n42,100\n",
            Files.readString(expected, StandardCharsets.UTF_8)
    );
}
~~~

**Điều kiện:** Cấu hình outbound flow phải thực sự dùng header `targetFileName` hoặc mapping tương đương làm filename; đoạn code là **phần assertion**, không phải test độc lập nếu chưa khai báo flow/fixture. Với channel bất đồng bộ, dùng cơ chế chờ side effect có timeout thay cho assert ngay.

Thử thêm các ca: filename trùng, thư mục không có quyền ghi, payload rỗng/không hợp lệ, temporary file name, rename sau khi ghi, xử lý crash giữa chừng và có còn file dở dang hay không.

## 9. Adapter một chiều và gateway có contract khác nhau

| Endpoint | Hướng | Cần kiểm tra |
|---|---|---|
| Inbound adapter | Hệ ngoài → channel | Dữ liệu đi vào, filter, message headers, poll/ack |
| Outbound adapter | Channel → hệ ngoài | Side effect, lỗi gửi, retry và trạng thái đích |
| Inbound gateway | External request → flow → response | HTTP/JMS request mapping, reply, status và timeout |
| Outbound gateway | Flow → external request → message phản hồi | Correlation, reply payload/status, timeout |
| Messaging gateway | Method Java → flow → giá trị trả về | Hợp đồng method, timeout và exception mapping |

**Không bắt outbound adapter one-way phải gửi reply** nếu hệ thống không có hợp đồng đó. Ngược lại, gateway request–reply cần test cả trường hợp **không có reply** và deadline đã hết.

## 10. Testing support của Spring Integration

Hệ sinh thái `spring-integration-test` cung cấp hỗ trợ để kiểm soát flow và mock endpoint, chẳng hạn `@SpringIntegrationTest`, `MockIntegrationContext` và các công cụ mock message handler ở những phiên bản hỗ trợ.

Một phương pháp test thường là:

1. Khởi tạo Spring test context với cấu hình flow thực.
2. Ngăn các inbound endpoint tự chạy nếu test cần điều khiển nguồn thủ công.
3. Thay **handler biên** bằng mock/spy qua test support ở đúng endpoint có ID, hoặc cung cấp một test double làm dependency.
4. Gửi `Message<?>` vào channel/gateway, rồi assert tham số hoặc message mà handler nhận.
5. Khôi phục mọi thay thế trong test teardown, tránh làm bẩn context chung.

Ví dụ ý tưởng:

~~~text
Context:
  inboundSource -> parseFlow -> outboundEndpoint(id=sendToPartner)

Trong test:
  dùng MockIntegrationContext thay outbound handler sendToPartner
  gửi message vào channel parseFlow
  xác minh mock nhận payload/header đúng
  reset thay thế sau test

Một integration test riêng:
  giữ outbound adapter thật
  cho adapter gọi mock HTTP server hoặc broker test
  xác minh side effect thực sự
~~~

**Lưu ý API:** phương thức thay endpoint phụ thuộc test-support API và ID được đặt trên endpoint/bean của phiên bản sử dụng. Không thay bừa cả flow bằng mock rồi xem như đã test adapter thực. Với poller có thể sử dụng test trigger hoặc lịch poll nhanh riêng cho test để tránh phụ thuộc đồng hồ thực.

## 11. Test HTTP inbound/outbound gateway

Với HTTP outbound gateway, dùng server mô phỏng (MockWebServer/WireMock hoặc tương đương) và kiểm tra **request thực sự được phát**, hoặc `MockRestServiceServer` nếu gateway sử dụng chính `RestTemplate` được bind với mock server.

Ví dụ hợp đồng:

~~~text
Message vào:
  payload: {"orderId":"42","total":100}
  correlationId: corr-42

HTTP request mong đợi:
  POST /orders
  Content-Type: application/json
  X-Correlation-Id: corr-42

Mock server trả:
  HTTP 201
  {"accepted":true,"externalId":"ext-42"}

Reply mong đợi:
  accepted=true, externalId=ext-42
  correlation/các header cần thiết được giữ
~~~

Các ca tối thiểu: HTTP 2xx và chuyển đổi đúng, 4xx không retry bừa, 5xx/network timeout với retry/backoff giới hạn, response sai schema, header bảo mật và content type. Với **inbound HTTP**, gửi HTTP request thật đến endpoint trong test context rồi quan sát input channel và response, không chỉ gọi trực tiếp transformer.

## 12. Test SFTP bằng server cô lập

SFTP có các vấn đề mà file local không mô phỏng: SSH authentication, host key, remote directory, network timeout, reconnect, file upload dở, đồng bộ metadata. Một unit test mock session hữu ích để kiểm tra code xử lý lỗi, nhưng cần test server hoặc container SFTP để xác nhận giao thức.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Remote file phù hợp pattern | Được đồng bộ và tạo message đúng |
| File đang được upload | Không đọc dở dang theo quy tắc temporary name/rename |
| Trùng filename ở hai đường dẫn | Phân biệt path nếu hợp đồng cần |
| Network đứt khi poll/upload | Retry, reconnect và error được ghi nhận |
| Sai credential/host key | Từ chối, không vô hiệu host-key verification để test xanh |
| Poll lại hoặc restart | Filter/metadata store hạn chế duplicate theo thiết kế |
| Outbound upload | File có mặt và nội dung đúng trên remote, không chỉ `send()` thành công |

Nếu cấu trúc có **remote-to-local synchronizer** rồi một inbound file adapter đọc local, cần test cả hai bước. Việc sync remote thành công chưa đồng nghĩa message downstream đã được xử lý xong.

## 13. JMS, AMQP và Kafka: dùng broker thử nghiệm khi cần kiểm chứng delivery

| Hệ thống | Điều chỉ broker test mới chứng minh đáng tin |
|---|---|
| JMS | Session/ack mode, transaction, queue vs topic, selector, redelivery |
| AMQP/RabbitMQ | Exchange, binding, routing key, publisher confirms/returns, ack/nack, DLQ |
| Kafka | Topic, partition, record key, offset commit, group rebalance, ordering trong partition |

Một unit test có thể kiểm tra **payload trước outbound adapter**, nhưng không đủ cho các khẳng định như “message đã được publish”, “consumer đã commit” hoặc “khi rollback sẽ redeliver”.

Với Kafka, ví dụ các ca quan trọng:

- Producer gửi đúng topic, key và schema.
- Consumer group test riêng, không ăn record của lần chạy khác; offset được kiểm soát.
- Consumer xử lý lỗi, retry/DLT và idempotency.
- Thứ tự trong **một partition** theo key được giữ theo contract, không suy ra thứ tự toàn topic.
- Khi consumer xử lý xong, **side effect tại sink** xuất hiện; producer ack chưa chứng minh bước này.

Với RabbitMQ, test exchange/binding/routing key, confirm và trả message không route được; với JMS, test ack/commit/rollback. **Không tuyên bố exactly-once end-to-end chỉ vì transport có transaction**: side effect sang HTTP, SFTP hay DB còn có ranh giới giao dịch riêng.

## 14. Database adapter: polling, concurrency và transaction

Nguồn JDBC/JPA polling thường đọc record chờ xử lý rồi tạo message. Các lỗi quan trọng nằm ở **lấy lại record**, **đánh dấu quá sớm**, **hai poller chạy đồng thời** và **rollback không bao phủ thao tác mong đợi**.

~~~text
orders_outbox:
  id=42, status=NEW, payload=...

Poller:
  tìm row NEW
  tạo message kèm business id=42
  cập nhật trạng thái theo chiến lược giao dịch

Consumer:
  xử lý order-42
  ghi side effect ở hệ đích
~~~

Kiểm thử nên có: một record hợp lệ, record sai dữ liệu, rollback sau lỗi downstream, duplicate polling, hai instance cùng chọn row, restart, paging/batch limit, và phương án bù trừ khi transaction không kéo dài tới hệ thống ngoài. Nếu dùng outbox, kiểm tra việc ghi **business state + outbox record trong cùng DB transaction**, rồi test riêng publisher/consumer có thể đọc lặp.

## 15. Test đường lỗi: DirectChannel không giống channel bất đồng bộ

Trong một **flow đồng bộ**, lỗi xảy ra khi handler xử lý message thường lan ra caller đang gọi `send()` hoặc gateway, trừ khi đã có error handler/advice riêng. Với **endpoint chạy trên thread khác** (poller, executor, listener container), lỗi không thể quay về một caller đã kết thúc; framework và cấu hình endpoint quyết định nơi báo lỗi, retry, reject hoặc đưa `ErrorMessage` lên error channel.

| Tình huống | Kỳ vọng cần kiểm tra |
|---|---|
| `DirectChannel` → handler ném exception | Caller thấy exception hoặc advice chuyển hướng theo cấu hình |
| Polling inbound phát sinh lỗi | Exception được cơ chế error handler/poller xử lý, không bị mất âm thầm |
| Flow dùng executor | Lỗi được báo ở error channel/recoverer đã cấu hình |
| Outbound HTTP trả lỗi | Có phân biệt lỗi có thể retry và lỗi không nên retry |
| Broker listener fail | Ack/nack/requeue/redelivery/DLQ theo cấu hình |
| Error flow cũng fail | Có log/cảnh báo và chính sách fallback; không nuốt lỗi |
| Poison message | Không retry vô hạn làm chặn các message hợp lệ |

Ví dụ hợp đồng:

~~~text
Payload: invalid CSV record
Message header: correlationId=corr-42

Expected:
  validator báo lỗi kèm error category
  thông tin nguồn/ID message còn truy được
  lỗi không làm ghi dữ liệu sai vào DB
  retry chỉ xảy ra khi lỗi thuộc loại transient
  cuối cùng message đến error output/DLQ hoặc xử lý theo hợp đồng
~~~

**Không mặc định mọi lỗi sẽ tự gửi lên bean toàn cục `errorChannel`.** Cơ chế xử lý phụ thuộc kiểu endpoint, header `errorChannel`, error handler của poller/listener và các advice. Bài test phải kiểm tra **cấu hình đang chạy** chứ không chỉ giả định có một error channel là đủ.

### 15.1. Kiểm tra ErrorMessage và thông tin gốc

Với error flow đã được cấu hình xuất `ErrorMessage` tới một `PollableChannel` riêng cho test, cần assert:

- Error payload là exception được dự kiến hoặc có nguyên nhân phù hợp.
- `failedMessage` (nếu thành phần exception cung cấp) giúp nhận diện đúng payload/header/correlation.
- Nội dung log/error message không chứa password, secret hoặc dữ liệu cá nhân dư thừa.
- Message lỗi không đồng thời bị đưa tới success channel, trừ khi contract rõ ràng cho phép xử lý bù trừ.

Khi bắt lỗi, không nên assert nguyên văn toàn bộ stack trace: lời gọi framework và thông báo có thể khác giữa các phiên bản. Ưu tiên **loại lỗi, nguyên nhân, error code và hành vi tại đích**.

## 16. Test poller: thời gian, lịch chạy và tính xác định

Poller có các tham số đáng chú ý như trigger, `maxMessagesPerPoll`, `receiveTimeout` (khi applicable), transaction, error handler và task executor. Chúng tác động đến throughput, thứ tự, cách xử lý lỗi và nhịp đọc dữ liệu.

**Sai lầm:** `Thread.sleep(5000)` rồi kiểm tra một flag; nếu CI chậm, test flaky, nếu CI nhanh, suite lãng phí thời gian.

Thay bằng cơ chế chờ sự kiện có timeout hữu hạn. Ví dụ khi một subscriber của flow dùng executor:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

@Test
void asyncFlowEventuallyDeliversTheMessage() throws Exception {
    CountDownLatch received = new CountDownLatch(1);
    AtomicReference<Message<?>> observed = new AtomicReference<>();

    // testResultChannel là một SubscribableChannel riêng của test.
    // Phải subscribe trước khi gửi và cleanup subscriber sau test.
    testResultChannel.subscribe(message -> {
        observed.set(message);
        received.countDown();
    });

    MessageChannel input = asyncInputChannel;
    assertTrue(input.send(
            MessageBuilder.withPayload("order-42").build()
    ));

    assertTrue(received.await(2, TimeUnit.SECONDS));
    assertEquals("order-42", observed.get().getPayload());
}
~~~

Đoạn này chỉ minh họa **phần thân test**; `testResultChannel` và `asyncInputChannel` phải được cung cấp bởi fixture có flow bất đồng bộ thực. Trong suite dùng chung Spring context, nhớ **unregister handler** ở teardown hoặc tạo context riêng; nếu không các test sẽ nhìn thấy message của nhau.

Với inbound file/DB poller, nên thiết kế fixture:

1. Tạo dữ liệu nguồn trong thư mục/DB thử nghiệm.
2. Khởi động endpoint theo điều khiển của test.
3. Chờ channel output hoặc side effect với thời hạn phù hợp.
4. Kiểm tra chính xác số message và trạng thái nguồn.
5. Dừng endpoint, dọn tài nguyên, bảo đảm không còn poller chạy qua test sau.

### 16.1. Test số lượng và đợt poll

Khi dùng `maxMessagesPerPoll(1)`, điều đó giới hạn số message **mỗi lần kích hoạt poll**, không có nghĩa chỉ xử lý một message trong cả vòng đời ứng dụng. Muốn kiểm tra số lượng theo đợt, cần điều khiển trigger hoặc quan sát theo thời điểm đã xác định; không dựa vào may rủi scheduler.

### 16.2. Kiểm tra không xử lý cùng file hai lần

Inbound adapter thường phối hợp file list filter với metadata store. Test nên bao gồm: một file mới → nhận một lần; poll lại → không nhận trùng theo chính sách; restart với metadata store bền vững → hành vi có thể dự đoán. Nếu metadata chỉ nằm trong bộ nhớ, restart có thể thay đổi cách nhận file.

## 17. Retry, duplicate và idempotency

Các hệ thống tích hợp thường có đặc tính **at-least-once** ở một hoặc nhiều đoạn: message bị redeliver, poller đọc lại row, consumer crash sau side effect nhưng trước ack, hoặc HTTP timeout sau khi server đã xử lý thành công.

Hãy phân biệt:

- **Retry kỹ thuật:** thử lại một thao tác thất bại tạm thời (network/503), giới hạn số lần và backoff.
- **Redelivery:** broker/adapter đưa lại message do chưa ack/commit.
- **Duplicate nghiệp vụ:** cùng business event ID có thể đi qua hệ thống nhiều lần.
- **Idempotency:** xử lý cùng business ID nhiều lần vẫn có kết quả mong muốn, không tạo side effect ngoài ý định.

Ma trận tối thiểu:

| Input hoặc sự cố | Điều cần assert |
|---|---|
| Hai message cùng `eventId` | Không tạo hai đơn hàng nếu contract yêu cầu idempotency |
| HTTP timeout sau khi đích đã ghi dữ liệu | Retry không nhân đôi side effect hoặc có đối soát |
| Exception transient | Retry hữu hạn, có backoff và log |
| Payload vĩnh viễn sai schema | Không retry vô hạn; đưa đến nhánh lỗi |
| Process chết sau DB write, trước ack | Consumer khôi phục an toàn, dữ liệu không bị nhân đôi |
| Retry hết giới hạn | Message vào recoverer/DLQ hoặc được lưu để xử lý thủ công |

**Cẩn trọng với transaction:** một transaction chỉ bao phủ đúng tài nguyên tham gia vào nó. Đừng giả định rollback của database sẽ rollback được upload SFTP hoặc request HTTP đã thành công.

## 18. Test concurrency, capacity và ordering

Concurrency có thể đến từ executor của channel, nhiều consumer cùng queue, nhiều listener broker, poller nhiều instance hoặc partition. Khi bật song song, test nên đo được **kết quả đúng**, không khóa vào một thứ tự toàn cục không được thiết kế.

| Bài test | Điều phải quyết định trước |
|---|---|
| Nhiều producer gửi cùng channel | Có cần bảo toàn thứ tự từng producer không? |
| Nhiều consumer nhận cùng queue | Là phân tải công việc hay phát đồng thời cho tất cả? |
| `PublishSubscribeChannel` có executor | Có cần mỗi subscriber hoàn tất trước khi xét done? |
| Kafka nhiều partition | Thứ tự theo key/partition hay thứ tự toàn topic? |
| Channel có capacity hữu hạn | Khi đầy thì chặn, timeout hay báo lỗi? |
| Downstream chậm | Backpressure và tốc độ tạo message được giới hạn thế nào? |
| Một consumer ném lỗi | Message của consumer khác có tiếp tục theo hợp đồng không? |

Bài kiểm thử cạnh tranh nên dùng `CountDownLatch` hoặc barrier để bắt đầu đồng thời, business ID để đếm kết quả và timeout hữu hạn. Chạy lặp test có giá trị tìm race, nhưng **kết quả xanh khi chạy một lần không chứng minh không có race**.

Nếu bài test quan tâm thứ tự, chọn một đường truyền có ordering guarantee cụ thể. Không viết test giả định ba adapter chạy qua executor và broker khác nhau vẫn giữ thứ tự toàn cục.

## 19. Lifecycle: start, stop, restart, disconnect, reconnect

Adapter có vòng đời kết nối và endpoint. Một context load thành công không chứng minh kết nối bền vững.

Các tình huống đáng thử:

- **Start:** endpoint được khởi động và chỉ bắt đầu poll/consume khi cấu hình cho phép.
- **Stop:** endpoint dừng nhận dữ liệu mới; tài nguyên thread/session được giải phóng theo semantics framework.
- **Restart:** filter/metadata store và ack/offset vẫn nhất quán; không lặp vô hạn những message đã hoàn tất.
- **Kết nối mất tạm thời:** SFTP/broker/server không khả dụng rồi phục hồi; có retry/reconnect/alert.
- **Credential hết hạn:** adapter phát hiện và xử lý lỗi xác thực, không bỏ qua kiểm tra TLS/SSH để tự phục hồi.
- **Shutdown khi đang xử lý:** công việc in-flight được drain, nack/requeue hoặc có bằng chứng trạng thái theo thiết kế.
- **Cleanup:** test không để listener, port, thread, connection hay temporary file ảnh hưởng lượt tiếp theo.

Với các endpoint Spring Integration hỗ trợ lifecycle như `SmartLifecycle`, có thể điều khiển start/stop qua bean/endpoint phù hợp ở **test context riêng**. Không làm thay đổi endpoint chia sẻ trong production context hoặc test khác chỉ để chạy một bài test.

## 20. WireTap, interceptors và khả năng quan sát

Đôi khi cần quan sát message **mà không đổi người nhận chính**. Spring Integration có các cơ chế như `WireTap`, channel interceptor và các thành phần quan sát/metrics. Chúng hữu ích khi đo đường đi của message, nhưng cũng có giới hạn:

- Wire tap có thể chuyển bản message qua nhánh phụ; **nhánh quan sát không phải đích nghiệp vụ**.
- Nếu quan sát bất đồng bộ, message có thể đến tap sau khi flow chính hoàn tất.
- Không để test tap giữ các object mutable rồi suy ra payload không bị thay đổi; nên thiết kế payload bất biến hoặc copy khi cần.
- Không coi việc tap thấy message là bằng chứng outbound hệ thống ngoài đã thành công.
- Giới hạn nội dung log: message có thể chứa PII, token hoặc secret; kiểm tra metadata thích hợp thay vì dump toàn bộ payload nhạy cảm.

Một test hữu ích có thể xác nhận: inbound message có `correlationId`, transformer giữ đúng correlation, error flow ghi cùng business ID và outbound request truyền identifier qua header thích hợp.

~~~mermaid
flowchart TD
    A["Adapter inbound"] --> C["inputChannel"]
    C --> T["Transformer / handler"]
    C -. "WireTap" .-> OBS["Observability channel"]
    T --> O["outboundChannel"]
    O --> X["External target"]
    X --> VERIFY["Assert side effect tại đích"]
    OBS --> EVIDENCE["Test trace/header assertion"]
~~~

## 21. Thiết kế test infrastructure và dữ liệu cô lập

Các lựa chọn thường dùng:

| Phụ thuộc | Fixture phù hợp |
|---|---|
| File adapter | `@TempDir` hoặc thư mục tạm riêng |
| HTTP | Mock server với port ngẫu nhiên, request log |
| SFTP | SFTP server test/Container với user và host key dành riêng |
| JMS | Embedded/test broker nếu phù hợp, hoặc container broker |
| AMQP/RabbitMQ | RabbitMQ container, exchange/queue tách biệt |
| Kafka | Kafka container/embedded broker, topic và consumer group riêng |
| SQL/DB | Testcontainers database hoặc DB test có transaction/isolation |
| Secret/config | Credential test, không dùng secret production |

**Testcontainers** thường giúp kiểm tra phiên bản protocol/broker gần môi trường thật hơn mock, nhưng phải quản lý thời điểm container sẵn sàng, port động, lifecycle và cleanup. Dùng tên queue/topic/schema/consumer group độc lập, có thể thêm một prefix dựa trên test run, để tránh trùng giữa các test song song.

Với broker hoặc database tồn tại qua nhiều method, cần dọn queue/record/offset hoặc tạo namespace mới. Không lấy việc message đã có từ lần chạy trước làm bằng chứng flow hiện tại đã hoạt động.

### 21.1. Khi nào dùng @SpringBootTest?

- Dùng Spring context nhỏ, chẳng hạn `@SpringJUnitConfig`, khi cần test một flow/channel; nhanh, ít auto-configuration ngoài dự kiến.
- Dùng `@SpringBootTest` khi cần kiểm tra wiring/auto-config của ứng dụng thực, nhưng tách external resources rõ.
- Dùng `@SpringIntegrationTest` và test support khi cần điều khiển inbound endpoint, mock handler/trigger theo khả năng phiên bản.
- Dùng `@DirtiesContext` khi test cố ý thay đổi bean/lifecycle làm context không thể dùng lại an toàn; đừng lạm dụng nếu có cách reset fixture sạch hơn.

## 22. Ma trận test theo loại adapter

| Adapter | Happy path | Negative path | Vòng đời/độ tin cậy |
|---|---|---|---|
| **File inbound** | Đọc đúng filename và payload | File sai pattern/encoding | Accept-once, rename, restart |
| **File outbound** | Tạo file đúng tên/nội dung | Path không hợp lệ, write denied | Atomic write/temp file policy |
| **SFTP inbound** | Tải file rồi phát message | Auth fail, remote path không tồn tại | Retry, reconnect, metadata |
| **SFTP outbound** | Upload đúng remote path | Kết nối đứt giữa upload | File dở dang, retry, dedup |
| **HTTP inbound gateway** | Request → channel → response | Invalid body, missing header | Timeout, concurrency |
| **HTTP outbound gateway** | Request gửi thật, reply đúng | 4xx/5xx/timeout | Backoff, idempotency |
| **JMS inbound/outbound** | Send/receive và map headers | Handler fail, invalid payload | Ack, rollback, redelivery |
| **AMQP/RabbitMQ** | Exchange định tuyến tới queue | Unroutable, consumer reject | Confirm, DLQ, reconnect |
| **Kafka** | Topic/key/schema đúng | Deserialization, poison record | Offset, replay, rebalance |
| **JDBC/JPA polling** | Chọn và map row đúng | DB outage, wrong status | Lock, tx, parallel poll |
| **Service gateway** | Method–message–reply đúng | Missing reply, converter fail | Timeout và exception mapping |

Chọn **các cột có ảnh hưởng thật đến nghiệp vụ**. Chẳng hạn một channel nhận file CSV có độ tin cậy kiểu **at-least-once** phải ưu tiên test duplicate và idempotency hơn việc assert một timestamp của framework.

## 23. Case study: File inbound → kiểm tra dữ liệu → HTTP outbound

Giả sử ứng dụng nhận file đơn hàng từ một thư mục được đồng bộ từ đối tác, kiểm tra nội dung và gọi một HTTP API của hệ thống giao hàng.

**Contract đề xuất:**

~~~text
Input:
  order-42.csv, encoding UTF-8, schema orderId,total
  orderId=42,total=100

Flow:
  file inbound poller
    -> fileInputChannel
    -> file-to-text/CSV parser
    -> validator
    -> validOrderChannel
    -> HTTP outbound gateway
    -> reply/result channel

Error:
  invalid input -> rejectedOrderChannel
  transient HTTP failure -> retry policy
  exhausted retry -> recovery queue/record with reason

Business rule:
  orderId là idempotency key
  xử lý lại cùng orderId không tạo shipment thứ hai
~~~

Kế hoạch kiểm thử theo thứ tự:

1. **Parser unit test:** CSV hợp lệ/thiếu cột/encoding không hợp lệ; lỗi đúng loại.
2. **Channel contract test:** message từ `fileInputChannel` giữ source filename và correlation; DTO đúng kiểu trên `validOrderChannel`.
3. **File inbound test:** tạo file tạm; poller phát message; filter bỏ file không hợp lệ theo tên; xác minh duplicate filter.
4. **HTTP gateway test:** mock server nhận đúng JSON, header idempotency/correlation; response 201 được chuyển thành result.
5. **Negative test:** file thiếu orderId không gọi HTTP; error đi nhánh rejected.
6. **Retry test:** server trả 503 rồi 201; số lần gọi đúng policy, không retry vô hạn; 400 không retry nếu business rule quy định.
7. **Replay test:** cùng orderId được xử lý hai lần; nếu gateway/đích hỗ trợ idempotency thì chỉ có một shipment.
8. **Restart test:** dừng khi file đã được thấy nhưng chưa hoàn tất; xác minh retry/recovery và metadata trạng thái.
9. **End-to-end test:** từ file thực trong thư mục test đến bản ghi mock server và kết quả nghiệp vụ; assert cả **message nội bộ lẫn side effect ngoài**.

Một cách trình bày kết quả test tốt:

| Case | Channel thấy gì? | Đích ghi gì? | Kết luận |
|---|---|---|---|
| Valid file | `OrderCreated(42)` | Một POST hợp lệ | PASS |
| Invalid CSV | Message lỗi có source ID | Không có POST | PASS |
| HTTP 503 → 201 | Message retry/error theo policy | Hai request, một kết quả hợp lệ | PASS nếu đúng contract |
| Duplicate order | Hai lần nhận input có cùng business ID | Không tạo hai shipment | PASS |
| Adapter disconnect | Không gửi dữ liệu sai | Có cảnh báo/retry, phục hồi | PASS nếu theo policy |

Không ghi `PASS` cho “duplicate” chỉ vì queue nhận hai message; đó có thể chính là lỗi nếu contract yêu cầu kết quả idempotent.

## 24. Anti-pattern trong chính bài test

| Anti-pattern testing | Vì sao gây kết quả giả |
|---|---|
| Assert `channel.send() == true` rồi kết luận outbound thành công | Không kiểm tra hệ thống đích hoặc reply |
| Dùng `Thread.sleep` cố định | Flaky theo CPU/CI và poller scheduling |
| Dùng `QueueChannel` thay mọi channel | Thay đổi đồng bộ, exception và transaction boundary |
| Mock cả adapter, broker, parser lẫn handler trong một test | Không còn phần tích hợp thật để kiểm chứng |
| Dùng thư mục/topic/queue chung giữa test | Có message hoặc file tồn dư làm xanh giả |
| Assert số lần gọi ngay ở luồng bất đồng bộ | Race giữa assertion và consumer |
| Không test lỗi và retry | Happy path che mất duplicate, poison message, timeout |
| So sánh toàn bộ `MessageHeaders` | Header ID/timestamp thay đổi ngoài business contract |
| Tắt TLS/SSH verification trong fixture để dễ chạy | Bỏ qua kiểm soát bảo mật cần có trong production |
| Không cleanup endpoint/thread/subscriber | Test sau nhận nhầm message hoặc bị resource leak |
| Không test restart/transaction | Thiếu bằng chứng khi process crash hoặc reconnect |
| Dùng data/secret production | Rủi ro vận hành và bảo mật không cần thiết |

## 25. Checklist nghiệm thu một test channel cho adapter

- [ ] Đã xác định đây là inbound adapter, outbound adapter hay gateway.
- [ ] Biết channel là subscribable/pollable, đồng bộ hay bất đồng bộ.
- [ ] Hợp đồng payload/header/correlation được ghi rõ.
- [ ] Test dùng dữ liệu cô lập và có setup/teardown.
- [ ] Có test message hợp lệ và không hợp lệ.
- [ ] Đã chọn đúng **điểm quan sát** (channel, handler, reply hoặc external system).
- [ ] Với outbound có assertion side effect thật ở mock server/broker/filesystem/DB.
- [ ] Với inbound có assertion nguồn được tiêu thụ và message được phát.
- [ ] Poller được kiểm soát về thời gian, không phụ thuộc sleep tùy tiện.
- [ ] Timeout hữu hạn và có thông báo hữu ích khi lỗi.
- [ ] Retry, duplicate, idempotency và DLQ/recovery được test nếu transport yêu cầu.
- [ ] Transaction/ack/offset test bằng hạ tầng có semantics tương đương khi quan trọng.
- [ ] Header bảo mật và dữ liệu nhạy cảm không xuất hiện trong log.
- [ ] Có test start/stop/restart/reconnect cho adapter có lifecycle.
- [ ] Có bài test xuyên luồng để xác nhận contract giữa adapter và flow.
- [ ] Thông tin về coverage ghi rõ **điều đã chứng minh và điều chưa chứng minh**.

## 26. Câu hỏi tình huống tự đánh giá

**Tình huống A.** Một bài test gọi `inputChannel.send(message)` thành công; flow có HTTP outbound adapter. Có thể kết luận partner API nhận đơn hàng chưa?

**Trả lời:** Chưa. Cần kiểm tra server đích/mock HTTP nhận request và trạng thái trả về hoặc side effect tương ứng. `send()` chỉ chứng minh đến mức channel/handler theo semantics của flow.

**Tình huống B.** Người viết test thay `DirectChannel` bằng `QueueChannel` để dễ `receive()`. Sau đó lỗi runtime biến mất. Kết luận gì?

**Trả lời:** Có thể đã đổi semantics đồng bộ và exception/transaction boundary. Phải giữ ít nhất một integration test với topology production, và chỉ dùng queue làm điểm quan sát có kiểm soát.

**Tình huống C.** Test File inbound có `patternFilter("*.csv")`; lần poll sau vẫn nhận cùng file. Đây chắc chắn là lỗi Spring Integration?

**Trả lời:** Không. Filter theo pattern không tự có nghĩa accept-once. Cần kiểm tra file list filter, metadata store và chiến lược xử lý sau khi đọc.

**Tình huống D.** Kafka producer được broker ack nhưng consumer fail khi ghi database. Bài test producer có chứng minh đơn hàng đã được xử lý không?

**Trả lời:** Không. Broker ack và side effect tại DB là hai điểm khác nhau; cần test consumer và transaction/idempotency.

**Tình huống E.** Poller đọc cùng DB row hai lần khi có hai instance; handler tạo hai email gửi khách. Kiểm soát cần test?

**Trả lời:** Phân phối/locking/transaction và idempotency theo business key, không chỉ query SQL happy path.

**Tình huống F.** Adapter nhận payload sai schema trên thread poller. Caller đã gửi request trước đó không nhận exception. Có thể kết luận lỗi bị mất?

**Trả lời:** Chưa. Với xử lý bất đồng bộ, phải xem error handler/error channel, log, retry hoặc DLQ; không kỳ vọng exception nhất thiết quay về thread gọi ban đầu.

**Tình huống G.** Integration test SFTP ổn định trên máy cá nhân nhưng CI flaky. Nên tăng `Thread.sleep(60000)` không?

**Trả lời:** Không nên coi sleep dài là giải pháp chính. Kiểm tra readiness server, poller lifecycle, timeout có giới hạn, metadata filter, race và isolation; chờ điều kiện có thể quan sát.

**Tình huống H.** Outbound file test phát hiện file từ lượt chạy trước nên xanh, dù handler hiện tại đã bị disconnect. Cần cải thiện gì?

**Trả lời:** Dùng `@TempDir` riêng, bảo đảm output trống trước test, tạo ID/file duy nhất và assert nội dung, số lượng, metadata theo chính lượt chạy.

## Kết luận

**Test channel cho adapter** trong Spring Integration là kiểm tra **hợp đồng message và cơ chế chuyển giao tại ranh giới giữa hệ thống ngoài với luồng nội bộ**, chứ không chỉ assert một lời gọi `send()`. Một chiến lược đáng tin kết hợp **unit test payload**, **channel/flow test**, **adapter contract test** và **integration test với giao thức thật được cô lập**. Cần lựa chọn điểm quan sát đúng với `DirectChannel`, `QueueChannel` và các channel bất đồng bộ; kiểm tra poller, header/correlation, error/retry, duplicate, transaction và lifecycle. Khi test được cả **message đi đúng đường** và **hệ thống đích có kết quả đúng**, các luồng file, SFTP, HTTP, JMS, AMQP, Kafka và database mới có bằng chứng vận hành vững chắc thay vì chỉ “chạy được trên happy path”.
