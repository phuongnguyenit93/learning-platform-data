# Bridge request-reply

## 1. Mục tiêu và tình huống sử dụng

Trong chương **Messaging bridge** của module **SPRING_INTEGRATION_CORE**, bài này giải thích cách đặt bridge vào một luồng request-reply: chuyển yêu cầu đến nơi xử lý và đưa kết quả về đúng bên gọi. Trọng tâm là quan hệ giữa `Message`, `MessageChannel`, endpoint, gateway và Java DSL.

Sau bài học, bạn có thể:

- Giải thích khi nào bridge dùng output channel và khi nào dùng header `replyChannel`.
- Thiết kế đường đi của request và reply mà không nhầm bridge với gateway.
- Giữ đường trả lời khi luồng đi qua transformer, router, filter hoặc aggregator.
- Nhận diện lỗi thiếu nơi nhận, mất header, hết thời gian chờ và trả lời sai kiểu.
- Viết kiểm thử cho đường trả lời và thứ tự ưu tiên channel.

Xét dịch vụ báo giá: ứng dụng gửi mã sản phẩm và số lượng, bộ tính giá tạo kết quả, rồi kết quả trở về lời gọi ban đầu. Ta muốn nối các phần của flow bằng channel có tên rõ ràng để dễ thay thế hoặc quan sát từng điểm.

Bridge giải quyết việc nối các điểm đó. Bộ tính giá vẫn chịu trách nhiệm tạo kết quả nghiệp vụ.

## 2. Bridge làm gì trong một luồng request-reply?

### 2.1. Bridge chuyển tiếp message

`BridgeHandler` chuyển message nhận được đến đích tiếp theo mà không thực hiện biến đổi payload. Một bridge đứng cuối flow có thể không khai báo output channel; khi đó, header `replyChannel` cung cấp nơi nhận. Nếu không xác định được đích, xử lý thất bại bằng một messaging exception. Xem [API BridgeHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/BridgeHandler.html).

Vì vậy, cụm từ “bridge request-reply” mô tả **vai trò của bridge trong cả flow**, không có nghĩa bridge tự gọi một dịch vụ rồi quản lý việc chờ kết quả.

Ví dụ:

~~~text
QuoteRequest
    -> bridge chuyển yêu cầu
    -> bộ tính giá
    -> QuoteReply
    -> bridge chuyển kết quả
    -> nơi đang chờ trả lời
~~~

Bridge đầu tiên nhìn thấy một request. Bridge cuối nhìn thấy một reply. Cả hai đều chỉ chuyển tiếp message tại vị trí của mình.

Nếu bỏ bộ tính giá và nối request trực tiếp vào bridge cuối, bên gọi có thể nhận lại chính dữ liệu đầu vào. Đó là hành vi echo, chưa phải báo giá thành công. Nếu gateway mong đợi `QuoteReply` nhưng nhận `QuoteRequest`, việc ánh xạ kiểu trả về còn có thể thất bại.

### 2.2. Ba thành phần, ba trách nhiệm

| Thành phần | Trách nhiệm trong ví dụ báo giá | Có quản lý lời gọi request-reply không? |
| --- | --- | --- |
| Messaging gateway | Chuyển lời gọi Java thành request message và nhận reply | Có |
| Bridge | Chuyển message sang channel tiếp theo hoặc đường trả lời | Không tạo một lượt chờ reply riêng |
| Endpoint tính giá | Nhận yêu cầu và tạo kết quả nghiệp vụ | Tạo nội dung reply |

Cần phân biệt thêm hai cách nối trong Java DSL:

~~~java
// Chuyển tiếp sang flow tiếp theo.
IntegrationFlow.from("outerInput")
        .bridge()
        .channel("pricingInput")
        .get();
~~~

~~~java
// Gọi một flow con, nhận kết quả rồi tiếp tục flow hiện tại.
IntegrationFlow.from("outerInput")
        .gateway("pricingInput")
        .channel("afterPricing")
        .get();
~~~

Đây là **hai phương án thay thế**; không đăng ký đồng thời cả hai cho cùng một ví dụ. Operator `gateway()` có cơ chế gửi request và nhận reply để flow ngoài tiếp tục xử lý. Xem [Java DSL gateway()](https://docs.spring.io/spring-integration/reference/dsl/java-gateway.html).

Dùng bridge khi bạn muốn chuyển giao message và tiếp tục sử dụng đường trả lời đang có. Dùng gateway khi một flow cần gọi flow khác như một bước xử lý có kết quả trả về.

## 3. Quy tắc chọn nơi gửi tiếp

Phần này xét cấu hình thông thường, không dùng routing slip hoặc tùy biến handler.

| Output channel của bridge | Header `replyChannel` | Đích gửi |
| --- | --- | --- |
| Có | Có hoặc không | Output channel đã cấu hình |
| Không | Có và phân giải được | Channel từ header |
| Không | Không | Phát sinh lỗi do thiếu đích gửi |

Quy tắc bỏ output channel để dùng reply channel được mô tả trong [tài liệu Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html).

Ví dụ XML tối thiểu cho hai vị trí:

~~~xml
<int:bridge input-channel="quoteRequests"
            output-channel="quoteProcessing"/>

<int:bridge input-channel="quoteResponses"/>
~~~

Đây là trích đoạn cấu hình; cần đặt trong tài liệu Spring XML đã khai báo namespace `int` và các channel tương ứng.

Bridge thứ hai không có nghĩa “không gửi đi đâu”. Nó yêu cầu message đầu vào mang đường trả lời.

Một điểm cần chú ý: output channel có cấu hình nhưng không gửi được **không** làm bridge tự chuyển sang `replyChannel`. Muốn xử lý lỗi gửi, bạn phải thiết kế chính sách lỗi riêng.

### 3.1. replyChannel là địa chỉ trả lời

Header `MessageHeaders.REPLY_CHANNEL` thường chứa một đối tượng `MessageChannel` hoặc một chuỗi được hạ tầng phân giải thành channel. Với tên bean, bean phải tồn tại trong context tương ứng. Header này khác với `correlationId`: một header chỉ nơi gửi, còn header kia dùng để liên kết các message. Xem [các header của Message](https://docs.spring.io/spring-integration/reference/message.html).

Trong request-reply qua gateway, gateway thường tạo reply channel tạm và đặt nó vào request. Các endpoint phía sau cần giữ được ngữ cảnh này cho đến lúc trả lời.

Ví dụ minh họa message:

~~~text
payload:
  QuoteRequest("BOOK-01", 2)

headers:
  replyChannel: <channel tạm của lượt gọi A>
  traceId: "trace-A"
~~~

Kết quả nghiệp vụ có thể có payload mới:

~~~text
payload:
  QuoteReply("BOOK-01", 2, 300000)

headers:
  replyChannel: <channel tạm của lượt gọi A>
  traceId: "trace-A"
~~~

Bridge cuối dùng đường trả lời của lượt A. Khi lượt B chạy đồng thời, nó phải giữ đường trả lời của B.

Không suy luận rằng cứ có cùng `correlationId` thì bridge sẽ biết gateway nào đang chờ. Bridge không phải bộ lưu và đối chiếu request theo mã tương quan.

## 4. Ví dụ Java DSL hoàn chỉnh: luồng báo giá

Ví dụ dùng Java 17 trở lên, Spring Integration 6 trở lên và thư viện `spring-integration-core`. Nếu dự án dùng Spring Boot, có thể dùng starter Spring Integration và để BOM của dự án quản lý phiên bản.

Các lớp dưới đây đặt cùng package `example.bridge`; mỗi kiểu `public` nằm trong tệp Java riêng. Tên tệp trong phần trình bày chỉ phục vụ việc thực hành.

### 4.1. Dữ liệu yêu cầu và kết quả

`QuoteRequest.java`:

~~~java
package example.bridge;

public record QuoteRequest(String sku, int quantity) {
}
~~~

`QuoteReply.java`:

~~~java
package example.bridge;

public record QuoteReply(
        String sku,
        int quantity,
        long totalVnd) {
}
~~~

Dùng số nguyên theo đơn vị đồng để ví dụ không bị nhiễu bởi phép tính dấu phẩy động.

### 4.2. Gateway dành cho bên gọi

`QuoteGateway.java`:

~~~java
package example.bridge;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "quoteRequests",
        defaultRequestTimeout = "1000",
        defaultReplyTimeout = "2000")
public interface QuoteGateway {

    QuoteReply quote(QuoteRequest request);
}
~~~

Các giá trị timeout trong annotation tính bằng mili giây. Ví dụ chủ động đặt giá trị để người đọc thấy giới hạn chờ mong muốn; giới hạn này còn phụ thuộc chỗ flow thực sự chờ, được giải thích ở phần sau. Xem [API MessagingGateway](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/MessagingGateway.html).

Không cần khai báo `defaultReplyChannel` trong ví dụ này: đường trả lời tạm của gateway là đủ.

### 4.3. Các channel và ba flow

`QuoteFlowConfig.java`:

~~~java
package example.bridge;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = QuoteGateway.class)
public class QuoteFlowConfig {

    @Bean
    public DirectChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public DirectChannel quoteProcessing() {
        return new DirectChannel();
    }

    @Bean
    public DirectChannel quoteResponses() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow requestBridgeFlow() {
        return IntegrationFlow.from(quoteRequests())
                .bridge()
                .channel(quoteProcessing())
                .get();
    }

    @Bean
    public IntegrationFlow pricingFlow() {
        return IntegrationFlow.from(quoteProcessing())
                .handle(QuoteRequest.class,
                        (request, headers) -> calculate(request))
                .channel(quoteResponses())
                .get();
    }

    @Bean
    public IntegrationFlow replyBridgeFlow() {
        return IntegrationFlow.from(quoteResponses())
                .bridge()
                .get();
    }

    private QuoteReply calculate(QuoteRequest request) {
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be greater than zero");
        }

        if (!"BOOK-01".equals(request.sku())) {
            throw new IllegalArgumentException(
                    "unsupported sku: " + request.sku());
        }

        long unitPriceVnd = 150_000L;
        long totalVnd = Math.multiplyExact(
                unitPriceVnd, request.quantity());

        return new QuoteReply(
                request.sku(), request.quantity(), totalVnd);
    }
}
~~~

`@IntegrationComponentScan` tìm interface gateway trong package được chỉ định. Chỉ component scan thông thường chưa đủ để phát hiện interface theo cách này. Xem [khai báo messaging gateway bằng annotation](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-configuration-with-annotations-and-xml).

Ba flow được tách để thể hiện rõ từng điểm nối:

1. `requestBridgeFlow` đưa request từ `quoteRequests` sang `quoteProcessing`.
2. `pricingFlow` tính giá và đưa reply sang `quoteResponses`.
3. `replyBridgeFlow` không có output channel, nên đưa reply về channel trong header.

Endpoint tính giá đã được cấu hình output là `quoteResponses`, vì vậy nó gửi kết quả đến đó trước. Sự tồn tại của header trả lời không khiến nó bỏ qua channel này.

### 4.4. Khởi tạo và gọi thử

`BridgeDemo.java`:

~~~java
package example.bridge;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class BridgeDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             QuoteFlowConfig.class)) {

            QuoteGateway gateway =
                    context.getBean(QuoteGateway.class);

            QuoteReply reply = gateway.quote(
                    new QuoteRequest("BOOK-01", 2));

            System.out.println(reply);
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
QuoteReply[sku=BOOK-01, quantity=2, totalVnd=300000]
~~~

### 4.5. Theo dõi đường đi của một lượt gọi

~~~mermaid
sequenceDiagram
    participant C as Bên gọi
    participant G as QuoteGateway
    participant B1 as Bridge request
    participant P as Endpoint tính giá
    participant B2 as Bridge reply
    participant R as Reply channel tạm

    C->>G: quote(BOOK-01, 2)
    G->>B1: QuoteRequest và replyChannel=R
    B1->>P: Chuyển tiếp request
    P->>B2: QuoteReply qua quoteResponses
    B2->>R: Chuyển reply theo header
    R-->>G: Kết quả của lượt gọi
    G-->>C: QuoteReply
~~~

Sơ đồ rút gọn tên các channel đầu vào để tập trung vào đường trả lời. Trong cấu hình thực, message đi qua `quoteRequests`, `quoteProcessing` và `quoteResponses` đúng như ba flow đã khai báo.

Nếu endpoint tính giá kết thúc bằng kết quả trả về và không có output channel riêng, nó có thể trả thẳng theo `replyChannel`; khi đó không cần thêm bridge cuối. Ví dụ cố ý giữ `quoteResponses` như một điểm nối có tên để minh họa trường hợp cần bridge trả lời.

## 5. Giữ đường trả lời khi xử lý message

### 5.1. Trả payload từ endpoint

Trong ví dụ, hàm `calculate` chỉ trả về một `QuoteReply`. Hạ tầng reply-producing endpoint tạo message kết quả và truyền tiếp những request header phù hợp theo cấu hình mặc định. Cách viết này giảm nguy cơ tự tạo một message thiếu header trả lời.

Nếu bạn tự xây message rồi gửi trực tiếp vào một channel, hãy chủ động giữ ngữ cảnh cần thiết. Ví dụ dưới đây giả sử `request` là message đầu vào:

~~~java
Message<QuoteReply> response = MessageBuilder
        .withPayload(new QuoteReply("BOOK-01", 2, 300_000L))
        .copyHeaders(request.getHeaders())
        .build();
~~~

Các import tương ứng:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

Đoạn này minh họa sao chép header trong một luồng nội bộ. Khi tích hợp qua ranh giới tin cậy hoặc giao thức khác, hãy chọn các header được phép mang sang theo hợp đồng của hệ thống.

Một cách dễ gây mất đường trả lời là tự tạo message chỉ từ payload và gửi nó vào `quoteResponses`:

~~~java
// Không mang theo ngữ cảnh của request ban đầu.
Message<QuoteReply> detachedResponse = MessageBuilder
        .withPayload(new QuoteReply("BOOK-01", 2, 300_000L))
        .build();
~~~

Nếu gửi message này trực tiếp vào bridge cuối, bridge không có output channel và cũng không tìm thấy `replyChannel`.

Điểm quan trọng là phân biệt **trả kết quả từ một endpoint** với **tự tạo rồi gửi message ra ngoài endpoint đó**. Hai cách này không nên được xem là tương đương về việc truyền header.

### 5.2. Đi qua transformer, router, filter và aggregator

Các mẫu tích hợp khác phải cùng đáp ứng hợp đồng trả lời của flow:

| Thành phần trong đường request-reply | Điều cần thiết kế |
| --- | --- |
| Transformer | Payload kết quả đúng kiểu mà bước sau cần; không làm mất ngữ cảnh trả lời khi tùy biến header |
| Router | Mọi nhánh hợp lệ đều có đường đến một kết quả hoặc một kết thúc có chủ đích |
| Filter | Nếu loại request, xác định bên gọi sẽ nhận lỗi, nhận kết quả từ chối hay hết thời gian chờ |
| Splitter và aggregator | Gom các kết quả thành reply theo hợp đồng trước khi trả về gateway |
| Bridge cuối | Chỉ đặt ở vị trí mà message đã sẵn sàng trở thành reply |

Ví dụ, một request báo giá bị filter loại bỏ rồi dừng flow sẽ không tự biến thành thông báo “hàng không hợp lệ”. Nếu hợp đồng yêu cầu kết quả từ chối, cần tạo kết quả đó hoặc phát sinh lỗi rõ ràng.

Tương tự, đặt bridge trả lời ngay sau splitter có thể đẩy từng phần kết quả về một gateway chỉ mong đợi một reply. Hãy xác định điểm tổng hợp trước khi đóng đường xử lý.

Bridge không thay thế cho logic định tuyến, quyết định chấp nhận hay hoàn tất nhóm message.

### 5.3. Ranh giới tiến trình

Đối tượng channel tạm thuộc context và vòng đời của lời gọi hiện tại. Không xem nó là địa chỉ bền vững có thể gửi nguyên trạng qua broker, lưu lâu dài rồi dùng ở một tiến trình khác.

Nếu flow đi qua JMS, AMQP hoặc giao thức mạng, hãy dùng gateway, adapter và cơ chế tương quan của transport phù hợp. Bridge cục bộ vẫn có thể nối các channel ở mỗi phía, nhưng hợp đồng request-reply xuyên hệ thống phải được thiết kế ở ranh giới transport.

## 6. Khi đưa QueueChannel vào đường request

### 6.1. Bridge không tự tạo luồng bất đồng bộ

Trong ví dụ chính, tất cả channel đều là `DirectChannel`. Flow chạy trên thread của bên gửi theo cấu hình thông thường.

`QueueChannel` giữ message để consumer nhận sau; endpoint đọc queue cần poller. `ExecutorChannel` giao xử lý qua executor. Việc đổi thread đến từ channel và hạ tầng thực thi, không đến từ tên gọi bridge. Xem [các triển khai MessageChannel](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

Muốn bên gọi giao yêu cầu vào queue và chờ kết quả trong lúc poller xử lý, thay **hai bean tương ứng** trong `QuoteFlowConfig`; giữ nguyên các bean còn lại:

~~~java
@Bean
public QueueChannel quoteRequests() {
    return new QueueChannel(100);
}

@Bean
public IntegrationFlow requestBridgeFlow() {
    return IntegrationFlow.from(quoteRequests())
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(50)
                            .maxMessagesPerPoll(10)))
            .channel(quoteProcessing())
            .get();
}
~~~

Bổ sung import:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.Pollers;
~~~

Không giữ cả bean cũ lẫn bean mới cùng tên.

Đường xử lý trở thành:

~~~text
Thread bên gọi:
  gateway -> queue quoteRequests -> chờ reply

Thread poller:
  lấy request
    -> bridge
    -> quoteProcessing
    -> tính giá
    -> quoteResponses
    -> bridge cuối
    -> reply channel tạm
~~~

Gateway có thể vẫn cung cấp API đồng bộ cho bên gọi dù một phần flow xử lý trên thread khác.

### 6.2. Hiểu cấu hình poller theo điều kiện vận hành

Trong đoạn cấu hình trên:

- Queue có sức chứa 100 message.
- `fixedDelay(50)` đặt khoảng nghỉ 50 ms giữa các lượt poll theo cơ chế fixed delay.
- `maxMessagesPerPoll(10)` giới hạn số message xử lý trong một lượt poll.

Không lấy `10 / 50 ms` để khẳng định throughput thực tế. Nếu các bước sau bridge chạy đồng bộ trên thread poller, thời gian tính giá và gửi kết quả cũng chiếm thời gian của lượt poll. Cấu hình poller cho bridge được minh họa trong [Messaging Bridge với Java DSL](https://docs.spring.io/spring-integration/reference/bridge.html#configuring-a-bridge-with-the-java-dsl).

Khi vận hành, hãy theo dõi độ sâu queue, thời gian nằm trong queue và độ trễ từ lúc gửi đến lúc nhận reply. Queue chưa đầy không đồng nghĩa các request vẫn có thể được đáp ứng trong thời gian chờ của bên gọi.

## 7. Phân biệt các giới hạn thời gian

| Cấu hình | Giới hạn giai đoạn nào? | Ví dụ |
| --- | --- | --- |
| Gateway `requestTimeout` | Thời gian chờ gửi request nếu thao tác gửi có thể block | Queue yêu cầu đã đầy |
| Gateway `replyTimeout` | Thời gian chờ nhận reply khi gateway có thể đi vào giai đoạn chờ | Request đã được nhận vào queue nhưng kết quả chưa đến |
| Bridge `sendTimeout` | Thời gian chờ gửi message đến đích của bridge nếu đích có thể block | Bridge chuyển tiếp sang một queue có giới hạn |
| Timeout của HTTP client hoặc dịch vụ ngoài | Thời gian cho thao tác I/O tương ứng | Endpoint tính giá gọi API nhà cung cấp |

Một timeout ở gateway không thay thế các timeout ở tầng I/O.

### 7.1. Với DirectChannel, replyTimeout không ngắt hàm đang chạy

Trong cấu hình chính, gateway gọi vào một chuỗi xử lý đồng bộ. Nếu `calculate` mất 10 giây, đặt `defaultReplyTimeout = "2000"` không làm Java tự ngắt hàm sau 2 giây. Gateway vẫn còn ở trong call stack gửi request.

Khi request được chuyển qua queue và xử lý trên thread khác, gateway có thể chờ reply với timeout đã đặt. Xem [hành vi gateway khi xử lý downstream kéo dài](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-behavior-when-no-response-arrives).

### 7.2. Hết thời gian chờ không có nghĩa công việc đã bị hủy

Ví dụ một lượt xử lý qua queue:

~~~text
t = 0 ms       gateway gửi request
t = 2000 ms    hết thời gian chờ reply
t = 2600 ms    endpoint mới tạo xong kết quả
~~~

Bên gọi có thể đã ngừng chờ nhưng công việc vẫn hoàn thành. Cần có chính sách đối với kết quả đến muộn và thao tác gửi lại.

Trong hệ thống ghi đơn hàng hoặc trừ tiền, nếu ứng dụng gửi lại sau timeout, cần dùng mã yêu cầu nghiệp vụ và cơ chế chống xử lý lặp phù hợp. Bridge không cung cấp bảo đảm xử lý đúng một lần.

Với gateway thông thường, hết thời gian chờ có thể trả về `null`; ứng dụng phải quy định cách diễn giải kết quả thiếu. Nếu phiên bản dự án hỗ trợ tùy chọn phát sinh lỗi khi timeout, hãy cấu hình theo hợp đồng mong muốn và kiểm thử hành vi đó. Không dựa vào việc một bridge tồn tại để suy ra rằng chắc chắn sẽ có reply.

## 8. Channel trả lời có tên và nguy cơ nhận nhầm

`quoteResponses` trong ví dụ là một channel trung gian của flow. Nó không phải channel mà gateway đang trực tiếp dùng để chờ kết quả.

Gateway đang chờ trên channel tạm có trong header; bridge cuối nối hai điểm này:

~~~text
quoteResponses -> bridge cuối -> replyChannel của lượt gọi
~~~

Nếu khai báo `defaultReplyChannel` cho một gateway, Spring Integration có hạ tầng bridge nội bộ để nối channel trả lời được cấu hình với channel tạm của lượt gọi. Xem [cấu hình default reply channel](https://docs.spring.io/spring-integration/reference/gateway.html#setting-the-default-reply-channel).

Khi chọn phương án đó, hãy thiết kế lại đường reply cho nhất quán. Không thêm máy móc một consumer “hứng reply” trên cùng channel và cho rằng nó chỉ quan sát dữ liệu.

Với channel point-to-point, thêm consumer có thể làm message được chuyển cho consumer đó thay vì đường trả lời mong muốn. Muốn quan sát, có thể dùng wire tap hoặc interceptor thích hợp. Nếu dùng publish-subscribe cho đường reply có tên, phải thiết kế rõ từng subscriber và ảnh hưởng của lỗi từ subscriber lên flow.

Một cấu hình nguy hiểm khác là:

~~~text
quoteResponses -> bridge -> quoteResponses
~~~

Bridge đã có output channel nên tiếp tục chọn output đó; nó không tự phát hiện “đây là reply cuối” để chuyển sang header. Với đường đồng bộ, vòng nối có thể gây gọi lặp đến khi cạn stack; với queue, nó có thể khiến message quay vòng.

Hãy vẽ đường đi cho cả request lẫn reply trước khi thêm bridge tại một điểm nối.

## 9. Lỗi và cách chẩn đoán

### 9.1. Lỗi trong cùng thread và lỗi sau ranh giới bất đồng bộ

Với `DirectChannel`, lỗi trong xử lý có thể truyền theo call stack về phía gửi. Khi có queue hoặc executor, bên gửi đã tách khỏi thread xử lý; cần cơ chế chuyển lỗi qua error channel. `errorChannel` là đường xử lý lỗi, còn `replyChannel` là đường trả lời; cấu hình một cái không thay thế cho cái kia. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Trong cấu hình báo giá ban đầu, request có số lượng bằng 0 làm endpoint tính giá phát sinh `IllegalArgumentException`. Gateway không được cấu hình error flow riêng, nên bên gọi nhận lỗi; tùy đường xử lý, lỗi nghiệp vụ có thể nằm trong nguyên nhân của một messaging exception.

Nếu thêm error flow chỉ để ghi log rồi kết thúc, hãy xác định gateway đang chờ sẽ được giải phóng như thế nào. Một log lỗi không phải là reply.

Khi thiết kế phản hồi lỗi, có thể chọn:

- Truyền lỗi về bên gọi theo hợp đồng exception.
- Chuyển lỗi thành đối tượng kết quả có kiểu dữ liệu được gateway chấp nhận.
- Với xử lý kéo dài, dùng hợp đồng tiếp nhận yêu cầu và tra cứu trạng thái riêng.

Lựa chọn thuộc về hợp đồng dịch vụ, không thuộc về bridge.

### 9.2. Bảng triệu chứng

| Triệu chứng | Khả năng cần kiểm tra | Hành động chẩn đoán |
| --- | --- | --- |
| Bridge cuối báo thiếu đích gửi | Không có output và thiếu `replyChannel` | Kiểm tra header của message ngay trước bridge |
| Gateway hết thời gian chờ, queue vẫn còn dữ liệu | Poller chưa hoạt động hoặc xử lý không kịp | Kiểm tra lifecycle endpoint, poller và độ sâu queue |
| Gửi vào DirectChannel thất bại | Không có subscriber đang nhận | Kiểm tra bean flow, wiring và trạng thái endpoint |
| Bên gọi nhận payload đầu vào | Bridge trả lời được đặt trước bước tạo kết quả | Kiểm tra vị trí endpoint nghiệp vụ |
| Lỗi chuyển kiểu trả về | Kiểu reply không khớp gateway | Kiểm tra payload thực tế tại bridge cuối |
| Kết quả bị consumer khác lấy | Nhiều consumer trên channel point-to-point | Kiểm tra tất cả endpoint cùng nhận channel đó |
| Log lỗi có nhưng caller vẫn chờ | Error flow không hoàn tất hợp đồng trả lời | Kiểm tra đầu ra của error flow và timeout |
| Xử lý lặp hoặc message quay vòng | Output của bridge nối trở lại đường đã đi | Vẽ lại cạnh nối giữa các channel |

Khi ghi log phục vụ chẩn đoán, nên giữ mã yêu cầu nghiệp vụ, tên endpoint và thời gian. Tránh dựa hoàn toàn vào biểu diễn chuỗi của một channel tạm để đối chiếu các lượt gọi.

## 10. Kiểm thử đường trả lời

Các ví dụ sau là mã kiểm thử để thực hành với JUnit Jupiter. Mục tiêu là xác nhận hành vi quan sát được: trả đúng kết quả, giữ đường reply, ưu tiên output và báo lỗi khi thiếu đích.

### 10.1. Kiểm thử gateway đi hết flow

Đặt lớp test trong cùng package với cấu hình ở phần 4:

~~~java
package example.bridge;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class QuoteFlowTest {

    @Test
    void returnsCalculatedQuoteToCaller() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             QuoteFlowConfig.class)) {

            QuoteGateway gateway =
                    context.getBean(QuoteGateway.class);

            QuoteReply reply = gateway.quote(
                    new QuoteRequest("BOOK-01", 2));

            assertNotNull(reply);
            assertEquals("BOOK-01", reply.sku());
            assertEquals(2, reply.quantity());
            assertEquals(300_000L, reply.totalVnd());
        }
    }
}
~~~

Test này xác nhận kết quả cuối cùng của cả đường request và reply. Một kiểm thử chỉ xác nhận `send()` thành công chưa chứng minh rằng bên gọi đã nhận được kết quả nghiệp vụ.

### 10.2. Kiểm thử riêng quy tắc chọn channel

Các test dưới đây gọi trực tiếp handler. `QueueChannel` đóng vai trò hộp thư để test đọc kết quả; chúng không cần poller vì test tự gọi `receive()`.

~~~java
package example.bridge;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.BridgeHandler;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BridgeReplyRoutingTest {

    @Test
    void usesReplyHeaderWhenOutputIsAbsent() {
        QueueChannel replies = new QueueChannel(1);
        BridgeHandler bridge = initializedBridge(null);

        Message<String> request = MessageBuilder
                .withPayload("reply-body")
                .setReplyChannel(replies)
                .setHeader("traceId", "trace-001")
                .build();

        bridge.handleMessage(request);

        Message<?> reply = replies.receive(100);
        assertNotNull(reply);
        assertEquals("reply-body", reply.getPayload());
        assertEquals("trace-001",
                reply.getHeaders().get("traceId"));
    }

    @Test
    void explicitOutputTakesPriorityOverReplyHeader() {
        QueueChannel output = new QueueChannel(1);
        QueueChannel replies = new QueueChannel(1);
        BridgeHandler bridge = initializedBridge(output);

        Message<String> request = MessageBuilder
                .withPayload("forward-body")
                .setReplyChannel(replies)
                .build();

        bridge.handleMessage(request);

        Message<?> forwarded = output.receive(100);
        assertNotNull(forwarded);
        assertEquals("forward-body", forwarded.getPayload());
        assertNull(replies.receive(0));
    }

    @Test
    void failsWhenNoOutputAndNoReplyHeaderExist() {
        BridgeHandler bridge = initializedBridge(null);

        Message<String> request = MessageBuilder
                .withPayload("no-destination")
                .build();

        assertThrows(MessagingException.class,
                () -> bridge.handleMessage(request));
    }

    private static BridgeHandler initializedBridge(
            QueueChannel output) {

        BridgeHandler bridge = new BridgeHandler();
        bridge.setBeanFactory(
                new DefaultListableBeanFactory());

        if (output != null) {
            bridge.setOutputChannel(output);
        }

        bridge.afterPropertiesSet();
        return bridge;
    }
}
~~~

Test đầu không chứa endpoint nghiệp vụ: nó chủ động chứng minh bridge chỉ chuyển message theo header. Test gateway ở mục trước mới chứng minh request báo giá được tính thành `QuoteReply`.

### 10.3. Các tình huống cần kiểm chứng khi mở rộng flow

| Thay đổi trong hệ thống | Hành vi cần chứng minh |
| --- | --- |
| Thêm nhiều lời gọi đồng thời | Mỗi request nhận đúng reply của mình |
| Đưa queue vào đường xử lý | Poller nhận request và kết quả vẫn về đúng gateway |
| Cho filter loại request | Bên gọi nhận kết thúc đúng hợp đồng |
| Thêm splitter và aggregator | Gateway nhận kết quả đã gom, không nhận một phần bất kỳ |
| Mô phỏng xử lý lâu hơn timeout | Xác định được hành vi khi hết chờ và kết quả đến muộn |
| Thêm error flow | Lỗi đến được bên gọi hoặc được đổi thành kết quả hợp lệ |

Với thử nghiệm timeout hoặc đồng thời, dùng cơ chế phối hợp như latch và các thời hạn hữu hạn. Tránh chỉ chèn `Thread.sleep()` rồi coi việc test chạy qua là bằng chứng chắc chắn.

## 11. Nguyên tắc áp dụng

Một luồng bridge request-reply cần có đường đi rõ ràng từ lúc nhận yêu cầu đến lúc trả lời:

1. Gateway hoặc bên gửi cung cấp ngữ cảnh trả lời.
2. Endpoint nghiệp vụ tạo kết quả đúng hợp đồng.
3. Các bước trung gian giữ được thông tin cần thiết để trả lời.
4. Bridge có output thì gửi tiếp đến output đó.
5. Bridge cuối không có output thì dùng đường reply đang có.
6. Mọi nhánh bị loại, phát sinh lỗi hoặc hết thời gian chờ đều có cách kết thúc được xác định.

Khi đọc một cấu hình, hãy tìm nơi tạo kết quả trước, rồi lần theo channel từ kết quả đó về bên gọi. Cách đọc này giúp phát hiện bridge đặt quá sớm, channel thiếu consumer và những nhánh không thể hoàn tất lời gọi.
