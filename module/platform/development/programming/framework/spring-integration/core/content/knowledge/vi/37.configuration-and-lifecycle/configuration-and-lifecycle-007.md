# Phase và lifecycle

Trong chương **Cấu hình và lifecycle** của module **SPRING_INTEGRATION_CORE**, bài này giải thích cách điều khiển thời điểm các thành phần bắt đầu và ngừng xử lý thông điệp. Mục tiêu là dùng `phase`, `autoStartup` và các thao tác lifecycle để đưa một luồng Spring Integration vào hoạt động theo thứ tự phù hợp.

Các khái niệm này áp dụng cho endpoint bao quanh transformer, filter, router, service activator và aggregator, cũng như các adapter hoặc gateway có lifecycle riêng. Ta vẫn thiết kế nghiệp vụ bằng `Message`, `MessageChannel` và Java DSL; lifecycle bổ sung cách vận hành luồng đó khi ứng dụng khởi động, tạm dừng hoặc đóng lại.

Ví dụ chính dùng Java 17+, Spring Integration 6.5 và Spring Framework 6.2. Các dependency cần được quản lý bằng một bộ phiên bản tương thích. Những số phase trong ví dụ là lựa chọn thiết kế của bài, không phải giá trị mặc định của framework.

## 1. Vấn đề thực tế: nguồn đã chạy nhưng nơi nhận chưa sẵn sàng

Giả sử ứng dụng nhận đơn hàng theo luồng:

~~~text
Nguồn đơn hàng → pendingOrders → Chuẩn hóa mã → completedOrders
~~~

Khi khởi động, ta muốn nơi xử lý có thể nhận việc trước khi bật nguồn tạo việc. Khi dừng, ta muốn chặn đầu vào trước, sau đó dành cơ hội xử lý phần việc đã nhận.

Nếu chỉ nhìn vào thứ tự các phương thức `@Bean` trong tệp cấu hình, rất dễ nhầm rằng luồng sẽ hoạt động theo đúng thứ tự ấy. Tuy nhiên, có ít nhất ba việc riêng biệt:

| Việc | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Tạo và khởi tạo bean | Đối tượng đã được tạo, inject và cấu hình chưa? | Tạo channel và gán handler |
| Khởi động thành phần | Thành phần đã bắt đầu nhận hoặc phát thông điệp chưa? | Đăng ký subscriber, lên lịch polling |
| Sẵn sàng về nghiệp vụ | Thành phần có thực sự phục vụ được yêu cầu hiện tại không? | Dịch vụ đích có phản hồi, dữ liệu tham chiếu đã nạp đủ chưa? |

Callback khởi tạo như `@PostConstruct` phục vụ việc chuẩn bị bean. Thao tác `start()`/`stop()` phục vụ việc đưa thành phần vào hoặc ra khỏi hoạt động. Đó là hai nhóm callback khác nhau trong Spring. [Tài liệu về lifecycle của bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).

Trong tình huống đơn hàng, một bean consumer có thể đã tồn tại nhưng chưa bắt đầu polling. Ngược lại, consumer có thể đã chạy nhưng hệ thống thanh toán mà nó gọi đang lỗi. Khi thiết kế vận hành, cần xác định mình đang chờ điều kiện nào.

## 2. Các hợp đồng lifecycle cần biết

### 2.1. Lifecycle: bắt đầu, dừng và trạng thái

Giao diện `Lifecycle` cung cấp ba thao tác cốt lõi:

~~~java
void start();
void stop();
boolean isRunning();
~~~

Nó mô tả trạng thái hoạt động của một thành phần. Gọi `stop()` không đồng nghĩa xóa bean hoặc đóng toàn bộ `ApplicationContext`; thành phần hỗ trợ khởi động lại có thể được `start()` sau đó. [Javadoc Lifecycle](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/Lifecycle.html).

Đối với bài này, hãy hình dung consumer có hai trạng thái quan sát được:

~~~mermaid
stateDiagram-v2
    [*] --> Stopped: Bean đã được khởi tạo
    Stopped --> Running: start()
    Running --> Stopped: stop()
    Stopped --> [*]: Bean bị hủy
~~~

Sơ đồ chỉ mô tả trạng thái hoạt động đơn giản. Một triển khai thực tế còn có thể có công việc đang hoàn thành trong lúc chuyển trạng thái.

### 2.2. SmartLifecycle: tự khởi động và thứ tự

`SmartLifecycle` mở rộng hợp đồng trên bằng các thông tin sau:

| Thành phần hợp đồng | Ý nghĩa |
| --- | --- |
| `isAutoStartup()` | Có tham gia tự khởi động khi context refresh không |
| `getPhase()` | Nhóm thứ tự khởi động và dừng |
| `stop(Runnable callback)` | Báo hoàn tất khi quá trình dừng có thể thực hiện bất đồng bộ |

Khi thành phần triển khai dừng bất đồng bộ, nó phải gọi `callback.run()` sau khi hoàn tất việc dừng theo hợp đồng của mình. Callback bị bỏ quên có thể làm bên điều phối phải chờ đến timeout. [Javadoc SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html).

`autoStartup(false)` là lựa chọn để điều khiển khởi động chủ động. Nó không loại bean khỏi context và không tự thay thế một cơ chế kiểm tra readiness. Trong ví dụ đơn hàng, ta dùng nó để giữ nguồn ở trạng thái dừng trong khi kiểm tra consumer.

### 2.3. LifecycleProcessor là bên điều phối

Khi context được refresh hoặc đóng theo quy trình bình thường, lifecycle processor điều phối các bean lifecycle theo nhóm phase. `DefaultLifecycleProcessor` cũng xử lý yêu cầu start/stop ở cấp context. [Javadoc DefaultLifecycleProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html).

Vì vậy, cần phân biệt:

- `context.start()`: một yêu cầu ở cấp context, có thể khởi động nhiều thành phần.
- `endpoint.start()`: yêu cầu trực tiếp cho một endpoint.
- Gọi một phương thức nghiệp vụ trên service: chưa chắc đi qua endpoint hay tuân theo trạng thái của endpoint.

Trong một công cụ vận hành, dùng đúng endpoint ID sẽ giúp thao tác có phạm vi rõ ràng hơn.

## 3. Quy tắc của phase

### 3.1. Phase nhỏ khởi động trước, dừng sau

Với các thành phần được điều phối theo phase và không có ràng buộc dependency làm thay đổi thứ tự:

~~~text
Khởi động:  phase thấp → phase cao
Dừng:       phase cao → phase thấp
~~~

Các thành phần cùng phase không có thứ tự tương đối được bảo đảm chỉ nhờ phase. Quan hệ `depends-on` tường minh được ưu tiên hơn thứ tự phase. [Quy tắc thứ tự trong SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html).

Với luồng đơn hàng, một cách phân bổ minh họa là:

| Thành phần | Phase do ứng dụng chọn | Khởi động | Dừng |
| --- | ---: | --- | --- |
| Hạ tầng có lifecycle do ứng dụng quản lý | 0 | Trước các bước bên dưới | Sau các bước bên dưới |
| Consumer chuẩn hóa đơn | 100 | Trước nguồn | Sau nguồn |
| Nguồn tạo đơn | 200 | Sau consumer | Trước consumer |

~~~mermaid
flowchart LR
    subgraph Startup["Thứ tự khởi động minh họa"]
        A["Hạ tầng: 0"] --> B["Consumer: 100"] --> C["Nguồn: 200"]
    end
    subgraph Shutdown["Thứ tự dừng minh họa"]
        D["Nguồn: 200"] --> E["Consumer: 100"] --> F["Hạ tầng: 0"]
    end
~~~

Đây là một quy ước cục bộ để giải thích ý đồ thiết kế. Nếu ứng dụng sử dụng executor, scheduler hoặc listener container do thư viện cung cấp, phải xem lifecycle thực tế của chính các bean ấy thay vì giả định tất cả hạ tầng đều ở phase 0.

### 3.2. Phase không phải độ trễ hoặc mức ưu tiên thông điệp

Giá trị `200` không có nghĩa chờ 200 mili giây. Phase không đặt độ ưu tiên cho từng message và không thay thế khoảng polling.

Ví dụ, consumer phase 100 vẫn có thể dùng poller cách nhau 50 mili giây. Con số đầu mô tả thứ tự vận hành; con số sau mô tả lịch kiểm tra công việc.

Nếu cần bước A hoàn tất xử lý một đơn rồi bước B mới xử lý chính đơn đó, hãy thể hiện quan hệ bằng channel, request-reply, correlation hoặc cơ chế đồng bộ nghiệp vụ thích hợp. Đặt A ở phase 100 và B ở phase 200 không mô tả quan hệ xử lý từng đơn.

### 3.3. Gọi start trực tiếp không sắp xếp lại toàn bộ ứng dụng

Giả sử mã vận hành gọi:

~~~java
orderIngress.start();
normalizeOrder.start();
~~~

Đó là hai lời gọi trực tiếp theo thứ tự người viết đã chọn. Không có một lượt điều phối toàn context được tạo ra chỉ vì cả hai đối tượng đều có phase.

Nếu cần bật một nhóm, hãy dùng bên điều phối nhóm thích hợp, hoặc chủ động đưa các bước kiểm tra và thứ tự cần thiết vào mã điều phối. Việc đặt phase vẫn có ích cho các đợt start/stop do container quản lý.

## 4. Phase thuộc thành phần nào trong Spring Integration?

Một bước xử lý thường có hai lớp cần phân biệt:

~~~text
Endpoint
  ├─ quản lý cách kết nối với input channel và lifecycle
  └─ gọi MessageHandler
       └─ thực hiện transform, filter hoặc xử lý nghiệp vụ
~~~

`ConsumerEndpointFactoryBean` chọn loại endpoint dựa trên channel đầu vào: `PollableChannel` dẫn tới polling consumer; `SubscribableChannel` dẫn tới event-driven consumer. [Mã nguồn ConsumerEndpointFactoryBean, nhánh 6.5.x](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/config/ConsumerEndpointFactoryBean.java).

Với `EventDrivenConsumer`, khởi động đăng ký handler với channel; dừng hủy đăng ký đó. Nếu handler cũng có lifecycle, endpoint còn điều phối lifecycle của handler. [Mã nguồn EventDrivenConsumer, nhánh 6.5.x](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/EventDrivenConsumer.java).

Trong Java DSL:

~~~java
.transform(
    transformer,
    endpoint -> endpoint
        .id("normalizeOrder")
        .phase(100)
        .autoStartup(true)
)
~~~

Lambda thứ hai cấu hình endpoint của bước transform. Nó không đặt phase lên từng message và cũng không thay đổi chính sách lưu trữ của channel. [API ConsumerEndpointSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

Một `@MessagingGateway` cung cấp cửa vào cho lời gọi nghiệp vụ. Khi thiết kế lifecycle, vẫn cần xác định endpoint hoặc proxy cụ thể nào phải được điều khiển và consumer phía sau nó đã sẵn sàng chưa. Việc có gateway không tự tạo ra một hàng đợi bền vững hoặc một cơ chế chờ tất cả thành phần sẵn sàng. [IntegrationFlow bắt đầu từ gateway](https://docs.spring.io/spring-integration/reference/6.5/dsl/integration-flow-as-gateway.html).

### Giá trị mặc định cần đọc theo loại endpoint

Không nên khái quát rằng mọi thành phần Spring Integration đều có cùng phase mặc định. Ví dụ trong mã nguồn nhánh 6.5.x:

| Triển khai | Phase ban đầu khi chưa được cấu hình lại |
| --- | --- |
| Lớp cơ sở `AbstractEndpoint` | `0` |
| `AbstractPollingEndpoint` | `Integer.MAX_VALUE / 2` |
| `EventDrivenConsumer` | `Integer.MIN_VALUE`, hoặc `Integer.MIN_VALUE + 1000` khi handler là `MessageProducer` |

Các giá trị này được khai báo trong [AbstractEndpoint](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractEndpoint.java), [AbstractPollingEndpoint](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java) và [EventDrivenConsumer](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/endpoint/EventDrivenConsumer.java).

Bảng mô tả các triển khai được nêu, không bao quát mọi adapter và gateway. Với những bước cần thứ tự vận hành rõ ràng, đặt phase tường minh rồi quan sát `getPhase()` của endpoint thực tế.

## 5. Ví dụ Java DSL: consumer chạy trước, nguồn bật chủ động

### 5.1. Thiết kế

Ta dùng hai channel trong bộ nhớ:

~~~text
orderIngress (phase 200, không tự khởi động)
       │
       ▼
pendingOrders: QueueChannel
       │
       ▼
normalizeOrder (phase 100, tự khởi động, có poller)
       │
       ▼
completedOrders: QueueChannel
~~~

`pendingOrders` chứa đầu vào chờ chuẩn hóa. `completedOrders` chỉ là nơi chương trình minh họa lấy kết quả; trong ứng dụng thật, nó có thể được thay bằng bước xử lý tiếp theo.

Điều kiện chuẩn bị:

- Có dependency `org.springframework.integration:spring-integration-core` thuộc bộ phiên bản đã chọn.
- Có Java 17 trở lên.
- Đặt lớp dưới đây vào dự án Java có classpath Spring phù hợp.
- Nếu chạy trong Spring Boot, tích hợp cấu hình vào context hiện có; phần `main` dưới đây dành cho ứng dụng Spring độc lập.

~~~java
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class PhaseLifecycleDemo {

    @Configuration
    @EnableIntegration
    public static class FlowConfig {

        @Bean
        public QueueChannel pendingOrders() {
            return new QueueChannel(100);
        }

        @Bean
        public QueueChannel completedOrders() {
            return new QueueChannel(100);
        }

        @Bean
        public IntegrationFlow orderIngressFlow(
                @Qualifier("pendingOrders") QueueChannel pendingOrders) {

            AtomicInteger sequence = new AtomicInteger();

            return IntegrationFlow.fromSupplier(
                    () -> " order-" + sequence.incrementAndGet() + " ",
                    source -> source
                            .id("orderIngress")
                            .phase(200)
                            .autoStartup(false)
                            .sendTimeout(1000)
                            .poller(Pollers.fixedDelay(250)
                                    .maxMessagesPerPoll(1)))
                    .channel(pendingOrders)
                    .get();
        }

        @Bean
        public IntegrationFlow orderProcessingFlow(
                @Qualifier("pendingOrders") QueueChannel pendingOrders,
                @Qualifier("completedOrders") QueueChannel completedOrders) {

            return IntegrationFlow.from(pendingOrders)
                    .<String, String>transform(
                            value -> value.trim().toUpperCase(Locale.ROOT),
                            endpoint -> endpoint
                                    .id("normalizeOrder")
                                    .phase(100)
                                    .autoStartup(true)
                                    .poller(Pollers.fixedDelay(50)
                                            .receiveTimeout(0)
                                            .maxMessagesPerPoll(1)))
                    .channel(completedOrders)
                    .get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(FlowConfig.class)) {

            SmartLifecycle ingress =
                    context.getBean("orderIngress", SmartLifecycle.class);
            SmartLifecycle consumer =
                    context.getBean("normalizeOrder", SmartLifecycle.class);

            QueueChannel input =
                    context.getBean("pendingOrders", QueueChannel.class);
            QueueChannel output =
                    context.getBean("completedOrders", QueueChannel.class);

            require(consumer.isRunning(), "Consumer phải tự khởi động");
            require(!ingress.isRunning(), "Nguồn phải chờ bật chủ động");

            Message<String> manualOrder = MessageBuilder
                    .withPayload(" manual-1 ")
                    .build();

            require(input.send(manualOrder, 1000), "Không gửi được đơn thủ công");

            Message<?> manualResult = output.receive(3000);
            require(manualResult != null, "Không nhận được kết quả thủ công");
            require("MANUAL-1".equals(manualResult.getPayload()),
                    "Kết quả chuẩn hóa không đúng");

            System.out.println("manual=" + manualResult.getPayload());
            System.out.println("consumer.phase=" + consumer.getPhase());
            System.out.println("ingress.phase=" + ingress.getPhase());

            ingress.start();

            Message<?> generatedResult = output.receive(3000);
            require(generatedResult != null, "Nguồn chưa tạo được kết quả");
            System.out.println("generated=" + generatedResult.getPayload());

            ingress.stop();

            require(!ingress.isRunning(), "Nguồn chưa chuyển sang trạng thái dừng");
            require(consumer.isRunning(), "Consumer cần tiếp tục chạy");

            System.out.println("ingress.running=" + ingress.isRunning());
            System.out.println("consumer.running=" + consumer.isRunning());
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
~~~

`IntegrationFlow.fromSupplier(...)` tạo nguồn thông điệp được kích hoạt bằng polling. Các tùy chọn nguồn như `phase`, `autoStartup` và `sendTimeout` được áp dụng qua source endpoint spec. [API IntegrationFlow, nhánh 6.5.x](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/dsl/IntegrationFlow.java), [SourcePollingChannelAdapterSpec, nhánh 6.5.x](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/dsl/SourcePollingChannelAdapterSpec.java).

### 5.2. Diễn giải kết quả mong đợi

Khi thực hành thành công, đầu ra nghiệp vụ dự kiến là:

~~~text
manual=MANUAL-1
consumer.phase=100
ingress.phase=200
generated=ORDER-1
ingress.running=false
consumer.running=true
~~~

Các dòng log của framework có thể xuất hiện xen kẽ. Đây là đầu ra mong đợi của ví dụ, không phải bản ghi một lần chạy đã thực hiện trong tài liệu này.

Những quan sát có ý nghĩa:

1. Sau khi context tạo xong, consumer đã chạy còn nguồn chưa chạy.
2. Đơn gửi thủ công vào `pendingOrders` vẫn được xử lý. Dừng nguồn chỉ ảnh hưởng nguồn đó; chương trình vẫn có thể gửi vào channel bằng đường khác.
3. Sau `ingress.start()`, thông điệp từ supplier đi qua cùng consumer.
4. Sau `ingress.stop()`, consumer vẫn ở trạng thái chạy.
5. `try-with-resources` đóng context khi thoát khối, kể cả khi phần kiểm tra ném exception.

Lời gọi `ingress.start()` ở đây chỉ minh họa bật riêng nguồn; nó không kiểm tra lại readiness của mọi thành phần khác.

### 5.3. Quan sát thứ tự phase tự động

Để quan sát cả hai endpoint tự khởi động, tạo một biến thể:

- Đổi nguồn thành `autoStartup(true)`.
- Bỏ kiểm tra yêu cầu nguồn đang dừng và bỏ giả định kết quả đầu tiên là đơn thủ công.
- Bật log lifecycle phù hợp rồi quan sát sự kiện start/stop của hai endpoint ID.

Với phase tường minh 100 và 200 trong cấu hình này, thứ tự mong muốn là consumer trước nguồn khi khởi động, nguồn trước consumer khi đóng context. Không dùng thứ tự các dòng `println` sau khi context đã tạo xong để suy ra thứ tự start đã xảy ra trước đó.

## 6. Chọn channel làm thay đổi ý nghĩa của việc dừng

### 6.1. Với QueueChannel

`QueueChannel` có thể giữ thông điệp khi consumer chưa nhận, miễn là còn dung lượng. Mặc định, nội dung được giữ trong bộ nhớ; muốn lưu bền phải cấu hình message store thích hợp hoặc dùng cơ chế bên ngoài. Với `DirectChannel`, handler chạy trực tiếp trên thread gửi và channel không cung cấp bộ đệm như queue. [Các triển khai MessageChannel](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Trong ví dụ, nếu dừng consumer và tiếp tục gửi dữ liệu, hãy dự kiến dung lượng `pendingOrders` tăng. Với queue giới hạn 100 phần tử, cần xác định điều gì xảy ra khi hết chỗ và thời gian gửi cho phép là bao lâu.

Kịch bản thực hành dễ quan sát là đặt cả hai endpoint `autoStartup(false)` ngay từ lúc tạo context, rồi:

1. Gửi một đơn vào `pendingOrders`.
2. Xác nhận chưa có kết quả ở `completedOrders`.
3. Bật consumer và nhận kết quả.
4. Chỉ bật nguồn sau khi đã kiểm tra consumer.

Cách chuẩn bị này tránh phải suy luận về một lượt polling đang chạy dở khi dừng consumer giữa chừng.

### 6.2. Với DirectChannel

Khi endpoint consumer hủy subscription và channel không còn subscriber phù hợp, lần gửi tiếp theo không có nơi xử lý và có thể báo lỗi dispatch. Dừng consumer cũng không biến channel thành hàng đợi.

Với luồng đồng bộ, không nên dùng cách “tạm dừng consumer rồi để bên gửi tự xếp hàng trong DirectChannel”. Cần chủ động chặn đầu vào hoặc chọn channel có khả năng đệm phù hợp.

Nếu handler đã được gọi trước thời điểm dừng, thao tác hủy subscription không có nghĩa công việc đang chạy ấy bị thu hồi. Đây là lý do phải theo dõi công việc đang xử lý riêng với trạng thái endpoint.

## 7. Phase và quá trình shutdown có kiểm soát

### 7.1. Dừng đúng thứ tự chưa bảo đảm xử lý hết hàng đợi

Xét thời điểm bắt đầu shutdown:

~~~text
pendingOrders còn 30 đơn
nguồn ở phase 200
consumer ở phase 100
~~~

Điều phối phase có thể yêu cầu dừng nguồn trước rồi dừng consumer. Khoảng giữa hai lời gọi không tự trở thành một cửa sổ đủ dài để xử lý 30 đơn.

Trong ví dụ này, cần phân biệt:

| Dấu hiệu | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Nguồn báo `isRunning() == false` | Nguồn đã chuyển trạng thái lifecycle | Không còn tác vụ hoặc thông điệp nào đang trên đường vào |
| Queue có kích thước 0 | Không có phần tử đang chờ tại thời điểm quan sát | Không có handler đang xử lý hoặc transaction đang commit |
| Consumer báo `isRunning() == true` | Consumer ở trạng thái hoạt động | Mọi đơn đều xử lý thành công |
| Đã nhận một kết quả | Đơn tương ứng đã đi đến điểm quan sát | Toàn bộ luồng đã hết việc |

Bảng là cách phân tích tình huống đơn hàng, không phải giao thức drain có sẵn.

### 7.2. Một trình tự drain do ứng dụng thiết kế

Với hệ thống cần hoàn tất phần việc đã nhận, có thể thiết kế các bước:

1. Ngừng nhận yêu cầu mới ở biên ứng dụng.
2. Dừng hoặc tạm ngưng các nguồn, rồi xác nhận tác vụ đầu vào đang chạy đã ổn định theo hợp đồng của adapter.
3. Giữ consumer, đường xử lý lỗi và tài nguyên cần thiết tiếp tục hoạt động.
4. Chờ điều kiện hoàn tất có giới hạn thời gian.
5. Dừng các thành phần xử lý còn lại và đóng tài nguyên.

Điều kiện hoàn tất cần phản ánh ứng dụng. Một mô hình đơn giản có thể xem xét:

~~~text
đầu vào đã yên
AND không còn thông điệp đang chờ
AND không còn công việc đang xử lý
AND các giao dịch hoặc xác nhận bắt buộc đã hoàn tất
~~~

Nếu có executor, cần tính cả tác vụ đã nhận vào executor nhưng chưa xử lý. Nếu có aggregator, cần quyết định cách xử lý nhóm chưa đủ phần tử. Nếu có retry, phải xác định công việc đang chờ thử lại được hoàn tất, lưu lại hay chuyển sang nơi xử lý khác.

Không nên chờ vô hạn một nhóm aggregator mà các phần tử còn thiếu không thể đến sau khi nguồn đã dừng. Tình huống đó cần một quyết định nghiệp vụ về timeout, lưu trạng thái hoặc xử lý phần còn thiếu.

### 7.3. Cơ chế orderly shutdown của Spring Integration

Spring Integration có cơ chế `IntegrationMBeanExporter.stopActiveComponents(timeout)` để hỗ trợ orderly shutdown. Cơ chế này chuẩn bị các thành phần hỗ trợ `OrderlyShutdownCapable`, hạn chế nguồn vào và dành khoảng thời gian cho thông điệp đang xử lý. Tài liệu cũng nêu việc giữ poller hoạt động để thông điệp trong queue có cơ hội được xử lý hết. [Orderly Shutdown](https://docs.spring.io/spring-integration/reference/6.5/shutdown.html).

Đây là một cơ chế điều phối riêng cần được cấu hình và gọi phù hợp. Không suy ra rằng chỉ đặt `phase` là đã kích hoạt toàn bộ quy trình đó.

Với hệ thống lưu đơn trong queue bộ nhớ, cần có lựa chọn rõ ràng khi hết thời gian chờ mà vẫn còn dữ liệu: kéo dài thời gian, chuyển giao dữ liệu hoặc chấp nhận giới hạn của mô hình. Thứ tự lifecycle không tự bổ sung độ bền lưu trữ.

## 8. Timeout dừng và callback hoàn tất

Trong ứng dụng Spring độc lập, có thể cấu hình lifecycle processor bằng bean tên chuẩn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.support.DefaultLifecycleProcessor;

// Phương thức đặt trong một lớp @Configuration.
@Bean(name = "lifecycleProcessor")
public static DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(20_000);
    return processor;
}
~~~

`setTimeoutPerShutdownPhase` đặt thời gian chờ tính bằng mili giây cho từng nhóm phase khi dừng. Nó không phải một timeout tổng duy nhất của toàn ứng dụng. [Cấu hình timeout của DefaultLifecycleProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html).

Ví dụ, nếu nhiều phase đều phải chờ thành phần dừng bất đồng bộ, tổng thời gian đóng context có thể dài hơn 20 giây. Ngược lại, phase hoàn tất nhanh không phải chờ đủ 20 giây.

Đối với một thành phần lifecycle tùy biến, có thể hình dung hợp đồng dừng như sau; đây là giả mã thiết kế, không phải API có sẵn:

~~~text
stop(callback):
    chặn nhận công việc mới
    yêu cầu tác vụ hiện tại kết thúc
    khi các điều kiện dừng đã đạt:
        cập nhật trạng thái stopped
        gọi callback đúng một lần
~~~

Bên triển khai phải xử lý cả tình huống không có công việc cần chờ. Gọi callback quá sớm khiến bên điều phối tưởng việc dừng đã hoàn tất; không gọi khiến bên điều phối tiếp tục chờ.

Timeout không ép một phương thức `stop()` đang chặn vô hạn phải kết thúc, không tự rollback nghiệp vụ và không tự chờ mọi message hoàn tất. Vì vậy, thao tác I/O, retry và quy trình drain vẫn cần giới hạn riêng.

Nếu ứng dụng đã có cấu hình lifecycle processor qua nền tảng chạy, hãy dùng cơ chế cấu hình phù hợp của nền tảng đó thay vì thêm một bean trùng tên.

## 9. Điều khiển một nhóm endpoint bằng role

Khi nhiều nguồn cần bật hoặc dừng cùng nhau, có thể gán role cho endpoint:

~~~java
endpoint -> endpoint
        .id("orderIngress")
        .phase(200)
        .autoStartup(false)
        .role("order-import")
~~~

Sau đó, thành phần điều phối có thể dùng `SmartLifecycleRoleController`:

~~~java
roleController.startLifecyclesInRole("order-import");
roleController.stopLifecyclesInRole("order-import");
~~~

Role gom các thành phần để điều khiển lifecycle; nó không phải quyền truy cập hoặc tên channel. Khi việc bật nhóm phụ thuộc vào quyền leader, đặt `autoStartup(false)` giúp tránh bật nguồn trước khi có quyết định leader. [Endpoint Roles](https://docs.spring.io/spring-integration/reference/6.5/endpoint-roles.html).

Một quy ước hữu ích cho tình huống đơn hàng là gom các nguồn nhập đơn vào role riêng, để consumer tiếp tục xử lý tồn đọng khi tạm dừng nhập. Chỉ gom cả nguồn lẫn consumer vào cùng thao tác dừng nếu đó thực sự là ý đồ vận hành.

Với flow đăng ký động, dùng `IntegrationFlowContext` để quản lý đăng ký và lifecycle của flow. Một flow được thêm sau khi context đã chạy không làm các bean đang chạy tự khởi động lại theo phase mới. [Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-runtime-flows.html).

## 10. Xử lý lỗi và quan sát trong lúc thay đổi lifecycle

Lifecycle thay đổi khả năng nhận việc, còn lỗi xử lý thông điệp cần đường xử lý riêng.

Trong luồng đồng bộ qua `DirectChannel`, lỗi handler có thể truyền về thread gửi. Với tác vụ polling hoặc xử lý bất đồng bộ do Spring Integration quản lý, lỗi có thể được đóng gói thành `ErrorMessage` và gửi tới error channel theo cấu hình. Không phải mọi lỗi lúc context khởi động đều trở thành thông điệp trên `errorChannel`. [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Trong tình huống đơn hàng, nên ghi nhận các dữ liệu sau để hiểu lần thay đổi trạng thái:

| Dữ liệu quan sát | Câu hỏi được giải đáp |
| --- | --- |
| Endpoint ID, phase, auto-startup, running | Thành phần nào được kỳ vọng chạy ở thời điểm này? |
| Thời điểm yêu cầu và hoàn tất start/stop | Đang chậm ở bước điều phối nào? |
| Số message đang chờ và thời gian chờ lâu nhất | Có tồn đọng cần xử lý trước khi đóng không? |
| Số công việc đang xử lý và số kết quả đã xác nhận | Queue rỗng có phải do công việc đã hoàn tất không? |
| Lỗi, retry và kết quả chuyển sang nơi xử lý lỗi | Công việc thất bại đang ở đâu? |

Khi giữ consumer hoạt động để drain, đường xử lý lỗi và tài nguyên nó sử dụng cũng phải còn khả dụng. Nếu tắt nơi xử lý lỗi quá sớm, một lỗi nghiệp vụ xuất hiện muộn có thể làm quy trình dừng khó theo dõi hơn.

Để xem trực tiếp cấu hình của một endpoint trong ví dụ:

~~~java
SmartLifecycle endpoint =
        context.getBean("normalizeOrder", SmartLifecycle.class);

System.out.println("phase=" + endpoint.getPhase());
System.out.println("autoStartup=" + endpoint.isAutoStartup());
System.out.println("running=" + endpoint.isRunning());
~~~

Các dòng này cung cấp trạng thái thành phần tại thời điểm đọc. Muốn kết luận hệ thống đã sẵn sàng hoặc hết việc, phải kết hợp thêm các điều kiện nghiệp vụ đã xác định.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu và xử lý phù hợp |
| --- | --- |
| Phase lớn khởi động trước | Dùng quy tắc tăng dần khi khởi động, giảm dần khi dừng |
| Viết phương thức @Bean trước thì endpoint chạy trước | Cấu hình thứ tự bằng lifecycle và dependency thực tế |
| Cùng phase có thứ tự cố định | Không dựa vào phase để phân biệt hai thành phần cùng giá trị |
| autoStartup(false) nghĩa là không tạo bean | Bean vẫn cần được tạo và cấu hình để có thể bật chủ động |
| Dừng nguồn sẽ chặn mọi đường gửi vào channel | Kiểm tra cả gateway, lời gọi trực tiếp và các nguồn khác |
| Dừng consumer làm DirectChannel giữ dữ liệu | Chọn bộ đệm phù hợp nếu cần giữ việc chờ xử lý |
| isRunning() chứng minh nghiệp vụ thành công | Theo dõi kết quả xử lý và xác nhận nghiệp vụ riêng |
| Queue rỗng chứng minh đã drain xong | Xem thêm công việc đang xử lý, executor, transaction và nhóm tổng hợp |
| Tăng shutdown timeout tự bảo đảm không mất message | Thiết kế cả lưu trữ, xác nhận, retry và điều kiện hoàn tất |
| Chỉ cần phase để kiểm soát toàn bộ shutdown | Xác định bên điều phối, hợp đồng stop và giới hạn thời gian |

## 12. Áp dụng vào một luồng cụ thể

Trước khi chọn giá trị phase, hãy mô tả bằng tên các thành phần: ai tạo việc, ai nhận việc, ai giữ dữ liệu chờ và ai xác nhận hoàn tất. Sau đó chọn thứ tự khởi động, thứ tự dừng và những điều kiện cần chờ ở giữa.

Với ví dụ trong bài, quyết định thiết kế là: consumer chuẩn hóa ở phase 100, nguồn ở phase 200, nguồn được bật chủ động sau khi kiểm tra consumer. Hai queue giúp quan sát thông điệp đi qua các điểm của luồng, còn chính sách drain vẫn cần được bổ sung nếu yêu cầu vận hành đòi hỏi xử lý hết phần việc đã nhận.

Khi mở rộng luồng bằng transformer, router, filter hoặc aggregator, tiếp tục đặt cùng câu hỏi cho từng endpoint và từng ranh giới bất đồng bộ. Một sơ đồ thông điệp rõ ràng, kết hợp hợp đồng lifecycle rõ ràng, giúp giải thích được cả đường đi của dữ liệu lẫn hành vi của ứng dụng khi bắt đầu và kết thúc hoạt động.
