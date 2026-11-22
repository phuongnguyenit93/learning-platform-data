# Header propagation qua channel

Trong chương **Message headers** của module `SPRING_INTEGRATION_CORE`, header propagation là việc các thông tin điều khiển và ngữ cảnh đi cùng thông điệp qua luồng tích hợp. Một đơn hàng có thể được chuẩn hóa, định tuyến, xử lý trên thread khác và ghép kết quả; `tenantId` hoặc mã theo dõi vẫn cần đến đúng nơi sử dụng.

Bài này tập trung vào quan hệ giữa `Message`, `MessageChannel` và endpoint. Đây là nền tảng để thiết kế luồng bằng Java DSL, dùng gateway, transformer, router, filter, aggregator và tìm nguyên nhân lỗi do thiếu metadata.

Sau bài học, bạn có thể:

- Phân biệt channel chuyển tiếp thông điệp với endpoint tạo thông điệp đầu ra.
- Dự đoán header nào được giữ khi đi qua channel đồng bộ, hàng đợi và channel dùng executor.
- Xử lý trường hợp transformer trả payload khác với trả toàn bộ `Message`.
- Chủ động giữ, ghi đè hoặc loại bỏ header tại một bước xử lý.
- Thiết kế kiểm thử xác nhận propagation mà không phụ thuộc vào thời gian chờ tùy ý.

## 1. Header thuộc về thông điệp

Giả sử producer tạo thông điệp sau:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

Message<String> input = MessageBuilder
        .withPayload("  order-42  ")
        .setHeader("acmeTraceId", "trace-2026-0042")
        .setHeader("tenantId", "tenant-hcm")
        .setHeader("sourceSystem", "web")
        .build();
~~~

`acmeTraceId`, `tenantId` và `sourceSystem` nằm trong `input.getHeaders()`. Chúng không phải thuộc tính riêng của channel và cũng không tự nằm trong biến thread-local của consumer.

Có ba thao tác khác nhau cần nhận diện:

| Thao tác | Ví dụ | Câu hỏi cần đặt |
| --- | --- | --- |
| Chuyển tiếp thông điệp | Gửi `input` qua một `DirectChannel` thông thường | Consumer nhận thông điệp nào? |
| Tạo đầu ra từ kết quả xử lý | Transformer trả chuỗi đã chuẩn hóa | Framework dựng thông điệp mới và lấy header từ đâu? |
| Thay đổi metadata có chủ đích | Header enricher thêm `processingStage` | Header cũ được giữ hay ghi đè theo cấu hình? |

~~~mermaid
flowchart LR
    P["Producer: M0 + headers"] --> C1["DirectChannel"]
    C1 --> T["Transformer: trả payload đã chuẩn hóa"]
    T --> C2["Channel tiếp theo: M1 + headers"]
    C2 --> H["Service activator"]
~~~

Trong sơ đồ này, vị trí cần xem xét quy tắc sao chép header là đầu ra transformer. `DirectChannel` đầu tiên chủ yếu nối producer với consumer của nó.

Khi đọc log, đừng mặc định rằng cứ đổi channel là header bị tạo lại. Hãy tìm bước đầu tiên mà giá trị thay đổi hoặc biến mất.

## 2. Phân biệt định danh thông điệp và ngữ cảnh nghiệp vụ

Không nên dùng một header cho mọi mục đích.

| Header | Ý nghĩa trong bài | Cách sử dụng |
| --- | --- | --- |
| `MessageHeaders.ID`, tên `id` | Định danh một message instance | Dùng khi đối chiếu các bước dựng thông điệp |
| `MessageHeaders.TIMESTAMP`, tên `timestamp` | Thời điểm tạo thông điệp | Không dùng làm mã giao dịch |
| `acmeTraceId` | Mã theo dõi do ứng dụng quy định | Giữ ổn định qua các bước của một yêu cầu |
| `tenantId` | Ngữ cảnh tenant | Xác minh từ nguồn tin cậy trước khi sử dụng |
| `IntegrationMessageHeaderAccessor.CORRELATION_ID` | Metadata liên kết nhóm thông điệp của framework | Phối hợp với splitter, publish-subscribe và aggregator |
| `SEQUENCE_NUMBER`, `SEQUENCE_SIZE` | Vị trí và kích thước chuỗi | Giữ đúng khi xử lý kết quả nhiều nhánh |
| `MessageHeaders.REPLY_CHANNEL` | Đích nhận phản hồi | Cần được quản lý trong luồng request-reply |
| `MessageHeaders.ERROR_CHANNEL` | Đích lỗi khi cơ chế xử lý lỗi sử dụng header này | Giữ đến bước có thể phát sinh lỗi bất đồng bộ |

Với builder mặc định, `id` và `timestamp` là header chỉ đọc do framework quản lý. Thông điệp mới có định danh mới; việc chuyển tiếp cùng instance không đòi hỏi đổi định danh. Xem [Message và các header định nghĩa sẵn](https://docs.spring.io/spring-integration/reference/message.html).

Ví dụ, hai thông điệp có thể mang cùng `acmeTraceId=trace-2026-0042` nhưng có `id` khác nhau vì một bước đã thay đổi payload. Điều đó phù hợp với yêu cầu theo dõi một nghiệp vụ xuyên suốt nhiều phép biến đổi.

Hai message cũng có thể được tạo trong cùng một mili giây. Vì vậy, kiểm thử không nên buộc hai `timestamp` phải khác nhau chỉ để chứng minh đã tạo message mới.

`acmeTraceId` trong bài là header tự đặt, không mặc nhiên kết nối với hệ thống distributed tracing. Nếu ứng dụng dùng công cụ tracing, cần tích hợp theo cơ chế truyền context của công cụ đó.

## 3. Channel ảnh hưởng đến propagation như thế nào?

Bảng sau xét cấu hình cơ bản: channel trong cùng JVM, không có interceptor sửa thông điệp, không có chuyển đổi datatype và không có message store bền vững.

| Channel | Cách chuyển giao | Header cần chú ý |
| --- | --- | --- |
| `DirectChannel` | Gọi một consumer trên thread gửi trong đường xử lý thành công thông thường | Chuyển thông điệp cùng header; không tự xóa header vì đổi channel |
| `QueueChannel` dùng hàng đợi trong bộ nhớ | Lưu thông điệp để consumer nhận sau | Header đi cùng thông điệp; `send` thành công chỉ xác nhận đã đưa vào hàng đợi |
| `ExecutorChannel` dùng thread pool | Giao tác vụ xử lý cho executor | Header vẫn đi cùng thông điệp; context nằm trên thread cần xử lý riêng |
| `PublishSubscribeChannel`, `applySequence=false` | Phát tới các subscriber | Các subscriber có thể cùng nhận một message instance |
| `PublishSubscribeChannel`, `applySequence=true` | Tạo thông điệp mang metadata chuỗi cho từng subscriber | Có `correlationId`, `sequenceNumber` và `sequenceSize` phù hợp từng nhánh |

`QueueChannel` không tự chạy nghiệp vụ khi nhận `send`. Nếu nối nó với endpoint trong một luồng do Spring quản lý, consumer polling cần được cấu hình poller. Gọi trực tiếp `receive` như trong kiểm thử bên dưới không cần poller. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

`ExecutorChannel` không đảm bảo luôn dùng thread khác với mọi loại executor: executor chạy trực tiếp hoặc cơ chế từ chối tác vụ chạy trên thread gọi có thể làm thay đổi cách thực thi. Bài này dùng `Executors.newSingleThreadExecutor()` để minh họa một ranh giới thread rõ ràng.

Điểm cần tách bạch là:

- **Metadata trong message:** consumer đọc từ `message.getHeaders()`.
- **Context gắn với thread:** ví dụ giá trị trong `ThreadLocal` hoặc MDC của thư viện logging.
- **Ranh giới giao dịch:** transaction đang gắn với thread gửi không tự trở thành transaction của worker chỉ vì message còn đủ header.

Việc log trên worker thiếu mã theo dõi chưa đủ để kết luận channel đã làm mất header. Trước hết hãy đọc `acmeTraceId` trực tiếp từ message mà worker nhận.

## 4. Endpoint quyết định cách dựng đầu ra

Giả sử thông điệp đầu vào có:

~~~text
payload = "  order-42  "
headers:
  acmeTraceId = "trace-2026-0042"
  tenantId = "tenant-hcm"
  region = "VN"
~~~

Cần phân biệt các trường hợp sau:

| Endpoint hoặc kết quả | Kết quả propagation điển hình |
| --- | --- |
| Bridge hoặc router chuyển tiếp thông điệp | Tiếp tục chuyển message; không phải một phép dựng payload đầu ra |
| Filter chấp nhận thông điệp | Chuyển thông điệp được chấp nhận |
| Filter từ chối thông điệp | Không có đầu ra trên đường thành công; discard/error phụ thuộc cấu hình |
| Transformer trả payload | Framework tạo message đầu ra và giữ các header đầu vào theo quy tắc của nó |
| Transformer trả toàn bộ `Message<?>` | Message do transformer trả về là kết quả hoàn chỉnh; code phải cung cấp header cần thiết |
| Service activator trả payload | Thông thường kế thừa header đầu vào khi dựng đầu ra |
| Service activator trả `Message<?>` | Thông thường bổ sung header đầu vào còn thiếu; giá trị đã có ở đầu ra được ưu tiên |

Quy tắc propagation và ngoại lệ của transformer được mô tả tại [Header Propagation](https://docs.spring.io/spring-integration/reference/message.html#message-header-propagation).

### 4.1. Chỉ thay payload

Đoạn DSL sau trả về một chuỗi:

~~~java
.transform(String.class, text ->
        text.trim().toUpperCase(java.util.Locale.ROOT))
~~~

Kết quả nghiệp vụ là `ORDER-42`. Khi dựng message đầu ra, transformer xử lý việc giữ header. Bạn không phải tự sao chép `tenantId` chỉ vì đã dùng một hàm chuyển chuỗi.

### 4.2. Trả toàn bộ Message và bỏ quên header

Đoạn sau dùng một `Transformer` nhận và trả toàn bộ message:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.integration.transformer.Transformer;

Transformer rebuildWithoutHeaders = source -> MessageBuilder
        .withPayload(source.getPayload().toString().trim())
        .build();
~~~

Khi truyền transformer này vào `.transform(rebuildWithoutHeaders)`, đầu ra có payload `order-42` và các header hệ thống của message mới. `acmeTraceId` và `tenantId` không được tự khôi phục.

Đây là lỗi do cách tạo message đầu ra. Channel tiếp theo chỉ nhận message đã thiếu metadata.

Nếu cần đổi payload và giữ header, hãy chỉ rõ việc sao chép:

~~~java
Transformer normalizeAndKeepHeaders = source -> MessageBuilder
        .withPayload(source.getPayload().toString().trim())
        .copyHeaders(source.getHeaders())
        .setHeader("processingStage", "normalized")
        .build();
~~~

Đoạn này dùng `org.springframework.integration.support.MessageBuilder`. Với hành vi mặc định, builder không dùng phép sao chép để ghi đè `id` và `timestamp` chỉ đọc của thông điệp mới.

Nếu chỉ đổi header và giữ payload, có thể bắt đầu bằng:

~~~java
Message<?> updated = MessageBuilder.fromMessage(input)
        .setHeader("processingStage", "received")
        .build();
~~~

`copyHeadersIfAbsent` hữu ích khi muốn giữ các giá trị đã đặt trên builder rồi chỉ bổ sung những khóa chưa có. Builder có thể trả lại message gốc nếu không có thay đổi phù hợp; không nên dùng `fromMessage(...).build()` như cách bắt buộc tạo một instance mới. Xem [MessageBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/MessageBuilder.html) và [BaseMessageBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/BaseMessageBuilder.html).

## 5. Header map chỉ đọc không đồng nghĩa dữ liệu được deep copy

Không sửa trực tiếp bản đồ header theo cách sau:

~~~java
input.getHeaders().put("tenantId", "tenant-other");
~~~

Với message mặc định, phép sửa này gây `UnsupportedOperationException`. Tuy nhiên, đối tượng được tham chiếu bởi một header vẫn có thể mutable.

Ví dụ:

~~~java
java.util.List<String> tags = new java.util.ArrayList<>();
tags.add("web");

Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("tags", tags)
        .build();

tags.add("changed-after-build");
~~~

Message có thể quan sát danh sách đã thay đổi dù bạn không gọi `put` trên header map. Đây là khác biệt giữa tính bất biến của cấu trúc map và tính bất biến của giá trị bên trong. Xem [Message Headers](https://docs.spring.io/spring-integration/reference/message.html#message-headers).

Với luồng nhiều nhánh, hãy chọn giá trị đơn giản hoặc bất biến:

~~~java
Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("tags", java.util.List.copyOf(tags))
        .build();
~~~

`List.copyOf` bảo vệ cấu trúc danh sách trong ví dụ chuỗi này; nó không deep copy mọi phần tử của một đồ thị đối tượng bất kỳ. Payload mutable cũng cần được thiết kế tương tự.

Nếu subscriber A sửa một object dùng chung, subscriber B có thể thấy dữ liệu thay đổi hoặc gặp race condition. Việc tạo message wrapper riêng cho từng nhánh không tự tách biệt toàn bộ dữ liệu bên trong.

## 6. Thực hành một luồng Java DSL hoàn chỉnh

Tình huống: tiếp nhận mã đơn hàng, thêm tên pipeline, chuẩn hóa payload, chuyển qua một channel trung gian và xác nhận đơn. Đến đầu ra cuối, giữ metadata phục vụ nghiệp vụ nhưng ngừng sao chép header dùng nội bộ.

Các ví dụ dùng Java DSL với `spring-integration-core` và JUnit Jupiter cho phần test. Dự án cần bộ dependency Spring tương thích; Spring Boot có thể quản lý phiên bản qua BOM. Mã dưới đây dùng context Spring trực tiếp, không yêu cầu khởi động một ứng dụng Boot.

### 6.1. Cấu hình luồng

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class HeaderPropagationConfig {

    @Bean
    public DirectChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    public DirectChannel handoff() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel completed() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersIn")
                .enrichHeaders(headers ->
                        headers.header("pipeline", "order-v1"))
                .transform(String.class, payload ->
                        payload.trim().toUpperCase(Locale.ROOT))
                .channel("handoff")
                .handle(String.class,
                        (payload, headers) -> payload + "|VALIDATED",
                        endpoint -> endpoint.notPropagatedHeaders(
                                "internal*", "authToken"))
                .channel("completed")
                .get();
    }
}
~~~

`notPropagatedHeaders` thuộc cấu hình endpoint `handle`. Nó quy định những header đầu vào không được sao chép khi handler dựng đầu ra, không cấu hình việc xóa header trên channel `handoff`. API hỗ trợ tên header và mẫu ký tự `*` đơn giản, không phải biểu thức chính quy. Xem [ConsumerEndpointSpec.notPropagatedHeaders](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

### 6.2. Kiểm thử payload và header đầu ra

Đặt test dưới đây cùng package với `HeaderPropagationConfig`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class HeaderPropagationFlowTest {

    @Test
    void keepsBusinessContextAndSuppressesInternalHeaders() {
        try (var context = new AnnotationConfigApplicationContext(
                HeaderPropagationConfig.class)) {

            DirectChannel input =
                    context.getBean("ordersIn", DirectChannel.class);
            QueueChannel output =
                    context.getBean("completed", QueueChannel.class);

            Message<String> request = MessageBuilder
                    .withPayload("  order-42  ")
                    .setHeader("acmeTraceId", "trace-2026-0042")
                    .setHeader("tenantId", "tenant-hcm")
                    .setHeader("internalRouteMemo", "temporary-note")
                    .setHeader("authToken", "demo-token")
                    .build();

            assertTrue(input.send(request, 1_000));

            Message<?> result = output.receive(1_000);
            assertNotNull(result);
            assertEquals("ORDER-42|VALIDATED", result.getPayload());
            assertEquals("trace-2026-0042",
                    result.getHeaders().get("acmeTraceId"));
            assertEquals("tenant-hcm",
                    result.getHeaders().get("tenantId"));
            assertEquals("order-v1",
                    result.getHeaders().get("pipeline"));
            assertFalse(result.getHeaders()
                    .containsKey("internalRouteMemo"));
            assertFalse(result.getHeaders().containsKey("authToken"));
            assertNotEquals(request.getHeaders().getId(),
                    result.getHeaders().getId());
        }
    }
}
~~~

Kết quả mong đợi:

| Thuộc tính | Đầu vào | Đầu ra |
| --- | --- | --- |
| Payload | `"  order-42  "` | `"ORDER-42\|VALIDATED"` |
| `acmeTraceId` | `trace-2026-0042` | Giữ nguyên |
| `tenantId` | `tenant-hcm` | Giữ nguyên |
| `pipeline` | Không có | `order-v1` |
| `internalRouteMemo` | Có | Không có |
| `authToken` | Có | Không có |
| `id` | ID của request | ID của message đầu ra |

Ở luồng này, `completed` là output channel được cấu hình tường minh. Test chủ động nhận từ hàng đợi nên không cần poller. Nó cũng không dựa vào `Thread.sleep`: thao tác `receive` có timeout chờ chính kết quả cần kiểm tra.

Các test trong bài là mã thực hành để chạy trong dự án có dependency phù hợp; bài không kèm kết quả chạy test.

## 7. Kiểm chứng qua DirectChannel và ExecutorChannel

Test luồng phía trên kiểm tra kết quả của nhiều endpoint. Để phân biệt rõ chuyển giao message với việc tạo đầu ra, có thể kiểm tra channel riêng lẻ.

Ví dụ sau dùng channel trong bộ nhớ và không cài interceptor hay message history:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class ChannelHeaderHandoffTest {

    @Test
    void directChannelHandsTheMessageToItsSubscriber() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Message<?>> received = new AtomicReference<>();
        channel.subscribe(received::set);

        Message<String> sent = MessageBuilder.withPayload("order-42")
                .setHeader("acmeTraceId", "trace-42")
                .build();

        assertTrue(channel.send(sent, 1_000));

        assertSame(sent, received.get());
        assertEquals("trace-42",
                received.get().getHeaders().get("acmeTraceId"));
    }

    @Test
    void executorChannelKeepsHeadersAcrossTheThreadBoundary()
            throws InterruptedException {

        var executor = Executors.newSingleThreadExecutor();
        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            QueueChannel observed = new QueueChannel(1);
            AtomicReference<Thread> worker = new AtomicReference<>();
            Thread sender = Thread.currentThread();

            channel.subscribe(message -> {
                worker.set(Thread.currentThread());
                observed.send(message, 1_000);
            });

            Message<String> sent = MessageBuilder.withPayload("order-42")
                    .setHeader("acmeTraceId", "trace-42")
                    .setHeader("tenantId", "tenant-hcm")
                    .build();

            assertTrue(channel.send(sent, 1_000));

            Message<?> received = observed.receive(1_000);
            assertNotNull(received);
            assertEquals("trace-42",
                    received.getHeaders().get("acmeTraceId"));
            assertEquals("tenant-hcm",
                    received.getHeaders().get("tenantId"));
            assertNotNull(worker.get());
            assertNotSame(sender, worker.get());
        }
        finally {
            executor.shutdownNow();
            executor.awaitTermination(1, TimeUnit.SECONDS);
        }
    }
}
~~~

`assertSame` trong test đầu tiên chỉ diễn tả đường chuyển giao ở cấu hình tối giản đó. Khi có interceptor tạo message mới hoặc chức năng khác bổ sung metadata, ứng dụng nên kiểm tra hợp đồng header cần thiết thay vì bắt buộc giữ cùng tham chiếu Java ở mọi nơi.

Ở test thứ hai, việc lấy được thông điệp từ `observed` xác nhận worker đã thực sự nhận message. Chỉ kiểm tra `channel.send(...) == true` chưa xác nhận được bước nghiệp vụ bất đồng bộ đã hoàn tất.

## 8. PublishSubscribeChannel và metadata chuỗi

Giả sử một đơn hàng cần hai nhánh:

- Nhánh A tính chi phí vận chuyển.
- Nhánh B kiểm tra kho.
- Aggregator phía sau chờ kết quả của hai nhánh.

`PublishSubscribeChannel` có tùy chọn `applySequence`. Mặc định tùy chọn này là `false`. Khi bật, channel cung cấp metadata chuỗi cho các subscriber; message mỗi nhánh có thể khác wrapper nhưng vẫn dùng chung tham chiếu payload. Xem [PublishSubscribeChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-configuration-pubsubchannel).

Test dưới đây minh họa hai nhánh đồng bộ; không gắn executor nên có thể thu kết quả ngay sau `send`:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class FanOutHeadersTest {

    @Test
    void addsSequenceMetadataAndKeepsBusinessHeaders() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setApplySequence(true);

        List<Message<?>> copies = new ArrayList<>();
        channel.subscribe(message -> {
            copies.add(message);
        });
        channel.subscribe(message -> {
            copies.add(message);
        });

        Message<String> request = MessageBuilder.withPayload("order-42")
                .setHeader("acmeTraceId", "trace-42")
                .setHeader("tenantId", "tenant-hcm")
                .build();

        assertTrue(channel.send(request, 1_000));
        assertEquals(2, copies.size());

        String correlation =
                IntegrationMessageHeaderAccessor.CORRELATION_ID;
        String sequenceNumber =
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER;
        String sequenceSize =
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE;

        for (Message<?> branch : copies) {
            assertEquals("trace-42",
                    branch.getHeaders().get("acmeTraceId"));
            assertEquals("tenant-hcm",
                    branch.getHeaders().get("tenantId"));
            assertEquals(request.getHeaders().getId(),
                    branch.getHeaders().get(correlation));
            assertEquals(2, branch.getHeaders().get(sequenceSize));
        }

        assertEquals(1,
                copies.get(0).getHeaders().get(sequenceNumber));
        assertEquals(2,
                copies.get(1).getHeaders().get(sequenceNumber));
        assertNotSame(copies.get(0), copies.get(1));
    }
}
~~~

Test dùng hai lambda subscriber riêng để tạo hai đăng ký khác nhau. Danh sách thường phù hợp vì ví dụ chạy đồng bộ; nếu chuyển sang xử lý song song, cần cơ chế thu nhận kết quả an toàn giữa các thread.

Khi nối các nhánh với aggregator, hãy giữ metadata nhóm và chuỗi cho đến khi aggregator đã sử dụng xong. Ví dụ, nếu một transformer trả message hoàn toàn mới và chỉ giữ `acmeTraceId`, metadata `sequenceSize` có thể biến mất dù mã theo dõi vẫn còn.

`acmeTraceId` phục vụ theo dõi nghiệp vụ. `correlationId` ở ví dụ fan-out phục vụ liên kết nhóm. Tách hai mục đích này giúp tránh việc một bước tạo nhóm làm hỏng mã theo dõi xuyên suốt.

Bật `applySequence` cũng không bảo đảm aggregator sẽ có đủ kết quả: nếu một nhánh bị filter loại bỏ hoặc kết thúc mà không phát đầu ra, cần chính sách release/timeout phù hợp với nghiệp vụ.

## 9. Chủ động kiểm soát header

### 9.1. Đặt giá trị đầu ra và quy tắc ưu tiên

Một service activator có thể chủ động trả message mang giá trị mới:

~~~java
.handle(String.class, (payload, headers) ->
        MessageBuilder.withPayload(payload)
                .setHeader("region", "APAC")
                .build())
~~~

Với propagation mặc định của service activator, các header đầu vào còn thiếu có thể được bổ sung. `region=APAC` đã nằm trên đầu ra được ưu tiên so với `region=VN` của đầu vào.

Với header enricher, có thể chỉ rõ việc cho phép ghi đè:

~~~java
.enrichHeaders(headers ->
        headers.header("processingStage", "validated", true))
~~~

Tham số `true` ở đây là lựa chọn ghi đè. Nên ghi rõ lựa chọn này khi trạng thái phải phản ánh bước hiện tại. Xem [HeaderEnricherSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/HeaderEnricherSpec.html).

### 9.2. Ngừng sao chép không tương đương xóa mọi nguồn header

`notPropagatedHeaders("authToken")` chặn việc sao chép `authToken` từ message đầu vào sang đầu ra ở handler phù hợp. Nếu chính code handler đã tạo đầu ra có `authToken`, đừng xem cấu hình này là lớp xóa header toàn diện.

Một bẫy khác là xóa header khỏi message trả về của service activator nhưng vẫn cho phép propagation mặc định: framework có thể bổ sung lại khóa còn thiếu từ request.

Khi mục đích là loại bỏ header khỏi thông điệp hiện tại, có thể dùng header filter tại một bước riêng:

~~~java
.headerFilter("authToken")
~~~

Đây là transformer dành cho header, khác với `filter(...)` dùng để quyết định có cho toàn bộ message đi tiếp hay không. Ví dụ dùng tên chính xác; khi cần loại theo mẫu hãy cấu hình khả năng pattern matching của header filter theo API đang dùng. Xem [Java DSL headerFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html#headerFilter(java.lang.String...)).

Không đặt `notPropagatedHeaders` trên router hoặc bridge rồi kỳ vọng các component chỉ chuyển tiếp thông điệp sẽ dựng lại đầu ra để loại header.

### 9.3. Chọn danh sách header được phép cho ranh giới rõ ràng

Ở một luồng chỉ xuất sự kiện, có thể dựng message với danh sách metadata được chọn:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.integration.transformer.Transformer;

Transformer toExportEvent = source -> MessageBuilder
        .withPayload(source.getPayload())
        .setHeader("acmeTraceId",
                source.getHeaders().get("acmeTraceId", String.class))
        .setHeader("tenantId",
                source.getHeaders().get("tenantId", String.class))
        .build();
~~~

Khi dùng `.transform(toExportEvent)`, danh sách header nghiệp vụ đầu ra do đoạn code này quyết định. Đây là cách có chủ đích thay vì vô tình quên sao chép.

Đoạn này thích hợp ở ranh giới xuất sự kiện đã được thiết kế không cần trả lời người gọi. Nếu tái sử dụng trong luồng request-reply, phải xem xét thêm `replyChannel`, `errorChannel` và metadata nhóm còn cần thiết.

Tương tự, việc giữ `tenantId` chỉ cung cấp thông tin ngữ cảnh; nó không thay thế xác thực hoặc kiểm tra quyền truy cập tenant.

## 10. Reply channel, error channel và lỗi khó quan sát

### 10.1. Gateway cần đường phản hồi hoàn chỉnh

Gateway request-reply thường tạo reply channel tạm thời và đặt tham chiếu của nó trong header của request. Nếu các endpoint giữ ngữ cảnh cần thiết, phản hồi có thể quay về nơi gateway đang chờ. Xem [Messaging Gateways: Setting the Default Reply Channel](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-default-reply-channel).

Ví dụ đường đi:

~~~text
Gateway
  -> requestChannel
  -> transformer
  -> service activator trả kết quả
  -> replyChannel của request
~~~

Nếu transformer giữa luồng trả một `Message` mới mà không giữ `replyChannel`, các bước sau có thể thiếu đường trả lời. Khi không có output channel hoặc cơ chế định tuyến khác, endpoint có thể báo lỗi không tìm được đích; người gọi cũng có thể không nhận phản hồi tùy cấu hình lỗi và timeout.

Cần kiểm tra đồng thời:

1. Gateway đang gửi request đến channel nào?
2. Bước nào dựng lại toàn bộ message?
3. Endpoint cuối có output channel tường minh không?
4. Header trả lời và timeout có còn phù hợp với thời gian xử lý không?

Luồng thực hành ở mục 6 kết thúc tại `completed`. Nếu đổi người gọi sang gateway mà giữ nguyên output này, gateway không tự động nhận được kết quả từ hàng đợi chỉ vì request có `replyChannel`. Cần thiết kế đường trả lời tương ứng.

### 10.2. Có errorChannel chưa đủ để mọi lỗi được chuyển thành message

Với lời gọi trực tiếp qua `DirectChannel`, exception thường truyền ngược theo call stack. Khi xử lý bằng tác vụ bất đồng bộ do Spring Integration quản lý, cơ chế error handler có thể phát `ErrorMessage`, ưu tiên đích trong `errorChannel` của request rồi đến channel lỗi chung. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Do đó, hai biểu hiện cần phân biệt là:

| Biểu hiện | Điều cần kiểm tra |
| --- | --- |
| Producer bắt được exception ngay khi `send` | Luồng đang thực thi trên thread người gửi |
| `send` thành công nhưng nghiệp vụ lỗi sau đó | Error handler và channel nhận lỗi của tác vụ bất đồng bộ |
| Lỗi tới channel chung thay vì channel riêng | `errorChannel` có còn trên message tại thời điểm lỗi không? |
| Header nghiệp vụ thiếu trên `ErrorMessage` | Xem request thất bại hoặc failed message; không giả định toàn bộ header request nằm ở cấp ngoài của message lỗi |

Một hàng đợi tự nó không biết nghiệp vụ consumer thất bại như thế nào. Nếu tự viết vòng `receive` và gọi handler ngoài cơ chế endpoint/poller của framework, bạn phải thiết kế cách bắt và chuyển lỗi tương ứng.

## 11. Khi ra khỏi bộ nhớ của một tiến trình

Giữ header qua một channel nội bộ không chứng minh rằng header sẽ đi qua được broker, HTTP hoặc cơ chế lưu trữ.

### 11.1. Message store có thể serialize dữ liệu

Nếu lưu message vào message store bền vững, khả năng giữ payload và header phụ thuộc serializer và implementation. Một object Java truyền tốt qua `DirectChannel` có thể không lưu được nguyên vẹn. `JdbcMessageStore` mặc định, chẳng hạn, có xử lý loại header không serializable trước khi serialize. Xem [Message Store](https://docs.spring.io/spring-integration/reference/message-store.html).

Với ví dụ đơn hàng, các giá trị `String` như `tenantId` và `acmeTraceId` dễ thiết kế hợp đồng hơn việc đặt service bean, connection hay object ngữ cảnh thực thi vào header.

Kiểm thử ở ranh giới này cần đọc lại message sau khi đã thực sự đi qua store, thay vì chỉ kiểm tra map trước khi lưu.

### 11.2. Tham chiếu channel là tài nguyên của tiến trình

`replyChannel` có thể chứa một đối tượng `MessageChannel`. Khi cần serialize, cơ chế header channel registry có thể đổi tham chiếu channel thành khóa chuỗi để giải quyết lại về sau. Khóa đó phụ thuộc registry còn tồn tại và entry còn hiệu lực. Xem [Header Channel Registry](https://docs.spring.io/spring-integration/reference/content-enrichment.html#header-channel-registry).

Đừng coi khóa registry là địa chỉ mạng cho mọi instance ứng dụng. Với giao tiếp giữa hai service, cần hợp đồng phản hồi qua transport và mã correlation thích hợp.

### 11.3. Transport có header mapper riêng

Một header nội bộ tên `tenantId` không tự trở thành HTTP header hoặc broker property. Adapter và mapper quyết định tên, kiểu và phạm vi header được đưa qua transport.

Ví dụ với HTTP, phải xem cấu hình mapped headers hoặc `DefaultHttpHeaderMapper`. Xem [HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html).

Phép kiểm tra đầy đủ gồm: message trước adapter, thông tin thực sự ra ngoài transport và message được phía nhận dựng lại. Bài này không triển khai adapter; nguyên tắc này xác định ranh giới của các cam kết propagation trong core.

## 12. Tìm điểm mất header và tự thực hành

### 12.1. Ghi nhận đúng vị trí

Khi một consumer không nhận `tenantId`, hãy so sánh từng chặng:

~~~text
A. Message vừa được producer tạo
B. Message đầu vào endpoint chuẩn hóa
C. Message đầu ra endpoint chuẩn hóa
D. Message trước khi đưa vào executor hoặc queue
E. Message consumer thực sự nhận
~~~

Ở mỗi chặng, chỉ ghi metadata cần điều tra, ví dụ:

~~~text
checkpoint=normalized-out
id=<message-id>
acmeTraceId=trace-2026-0042
tenantId=tenant-hcm
thread=<thread-name>
~~~

Một `ChannelInterceptor` có thể quan sát các lần gửi hoặc nhận; `preSend` cũng có thể thay message bằng kết quả khác. Vì vậy, khi thấy thông điệp thay đổi ngay trên một channel, hãy xem cả interceptor cục bộ và interceptor toàn cục. Các hook nhận chỉ áp dụng cho pollable channel. Xem [Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html).

Không log toàn bộ message chỉ để tìm một header vì payload hoặc header khác có thể chứa dữ liệu riêng tư hay token.

### 12.2. Các tình huống cần nhận diện

| Hiện tượng | Nguyên nhân có thể kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Sau transformer còn payload nhưng mất metadata nghiệp vụ | Trả toàn bộ message và quên copy header | Trả payload hoặc chủ động dựng đủ header |
| Qua executor, message còn trace nhưng log thiếu trace | Context logging nằm trên thread | Thiết kế phục hồi và dọn context ở worker |
| Header bị xóa rồi xuất hiện lại sau service activator | Đầu ra thiếu khóa và propagation bổ sung từ đầu vào | Suppress ở handler hoặc dùng header filter ở bước rõ ràng |
| Hai subscriber ảnh hưởng dữ liệu của nhau | Giá trị header hoặc payload mutable dùng chung | Dùng dữ liệu bất biến hoặc sao chép có chủ đích |
| Aggregator không đủ dữ kiện ghép nhóm | Thiếu metadata chuỗi hoặc thiếu kết quả một nhánh | Kiểm tra đầu ra từng nhánh và chính sách hoàn tất nhóm |
| Nội bộ đủ header, phía HTTP nhận thiếu | Mapper không đưa header qua transport | Kiểm tra cấu hình và message phía nhận |
| Message đổi tham chiếu dù chỉ đi qua channel | Interceptor hoặc chức năng bổ sung metadata | Kiểm tra hợp đồng header, không chỉ so sánh tham chiếu |

### 12.3. Bài tập mở rộng

1. Thay transformer trả payload trong mục 6 bằng `rebuildWithoutHeaders`. Dự đoán assertion nào không còn đúng, rồi kiểm chứng trong dự án.
2. Đổi transformer thành `normalizeAndKeepHeaders` và xác nhận cả payload lẫn header nghiệp vụ.
3. Bỏ `notPropagatedHeaders` khỏi service activator. Quan sát `authToken` ở đầu ra và thêm `headerFilter("authToken")` tại bước thích hợp.
4. Thay `handoff` bằng `ExecutorChannel` có executor do Spring quản lý vòng đời. Giữ cách chờ kết quả bằng `receive(timeout)` và kiểm tra header như cũ.
5. Mở rộng fan-out thành hai nhánh có kết quả khác nhau. Giữ metadata nhóm tới aggregator và thiết kế trường hợp một nhánh không trả kết quả.
6. Với một gateway request-reply riêng, viết test có timeout hữu hạn cho cả trường hợp giữ và làm mất đường trả lời.

Mục tiêu khi hoàn thành là giải thích được **header do ai tạo, đang thuộc message nào, endpoint nào quyết định sao chép và ranh giới nào cần hợp đồng riêng**. Những câu hỏi này giúp bạn đọc và thiết kế luồng Spring Integration mà không dựa vào giả định “mọi header luôn được giữ”.
