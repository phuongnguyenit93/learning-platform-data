# JmsListenerEndpointRegistry và điều khiển vòng đời listener

## Mục tiêu

Trong Spring JMS, mỗi method được đánh dấu bằng `@JmsListener` được chuyển thành một listener endpoint và được phục vụ bởi một `MessageListenerContainer`. Spring tạo container thông qua `JmsListenerContainerFactory`, còn `JmsListenerEndpointRegistry` giữ các container đó và điều khiển vòng đời của chúng.

Registry giúp ứng dụng tra cứu listener theo ID, xem danh sách listener, khởi động hoặc dừng từng listener, điều khiển tất cả listener và đăng ký endpoint mới khi cần.

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa `@JmsListener`, endpoint, listener container và registry.
- Đặt ID ổn định để quản lý từng listener.
- Tra cứu container bằng `getListenerContainer()` và liệt kê bằng `getListenerContainerIds()`.
- Khởi động hoặc dừng một listener hay toàn bộ listener.
- Hiểu vai trò `SmartLifecycle` trong lúc ApplicationContext khởi động và đóng.
- Cấu hình auto-start cho listener container.
- Đăng ký endpoint bằng code và hiểu các giới hạn của registry.

## 1. Các thành phần trong cơ chế listener

Một endpoint mô tả nơi nhận message và cách gọi code xử lý. Khi Spring phát hiện `@JmsListener`, hạ tầng annotation tạo endpoint tương ứng. Một `JmsListenerContainerFactory` dùng endpoint đó để tạo `MessageListenerContainer`.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `@EnableJms` | Bật hạ tầng xử lý các annotation `@JmsListener` |
| `@JmsListener` | Khai báo destination và method xử lý message |
| `JmsListenerEndpoint` | Mô tả một endpoint JMS |
| `JmsListenerContainerFactory` | Tạo và cấu hình listener container |
| `MessageListenerContainer` | Quản lý consumer, session, kết nối và việc nhận message |
| `JmsListenerEndpointRegistry` | Lưu và quản lý vòng đời các container được tạo cho endpoint |

Luồng khởi tạo:

~~~text
@EnableJms
    |
    v
JmsListenerAnnotationBeanPostProcessor
    |
    v
Phát hiện method @JmsListener
    |
    v
JmsListenerEndpoint
    |
    v
JmsListenerContainerFactory
    |
    v
MessageListenerContainer
    |
    v
JmsListenerEndpointRegistry quản lý container
~~~

Mỗi method listener được phục vụ bởi một container được tạo từ factory tương ứng. Registry quản lý các container này trong vòng đời của Spring ApplicationContext.

**Điểm cần nhớ:** container do registry quản lý không phải là bean riêng trong ApplicationContext và không thể inject trực tiếp bằng tên bean như các bean thông thường. Muốn truy cập chúng để quản lý, hãy dùng registry. Các container được khai báo thủ công thành bean riêng là trường hợp khác và không tự động xuất hiện trong registry.

## 2. Bật annotation listener và tạo endpoint

Thêm `@EnableJms` vào cấu hình để Spring đăng ký hạ tầng xử lý `@JmsListener`.

Ví dụ cấu hình factory:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-6");
        return factory;
    }
}
~~~

Spring mặc định tìm factory có tên bean `jmsListenerContainerFactory` nếu endpoint không chỉ định factory riêng. Có thể đặt factory cụ thể trong thuộc tính `containerFactory` của `@JmsListener`.

Khai báo listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(
        id = "ordersListener",
        destination = "orders.queue"
    )
    public void handleOrder(String orderId) {
        System.out.println("Received order: " + orderId);
    }
}
~~~

Khi ApplicationContext khởi tạo, Spring phát hiện method `handleOrder`, tạo endpoint và container cho endpoint đó. Registry lưu container theo ID `ordersListener`.

Các ví dụ Java trong bài là đoạn tích hợp dành cho ứng dụng Spring JMS; chúng cần dependency Spring JMS, Jakarta Messaging provider và `ConnectionFactory` được cấu hình trong ứng dụng.

## 3. Vì sao cần đặt ID tường minh?

Thuộc tính `id` của `@JmsListener` là định danh của container quản lý endpoint.

~~~java
@JmsListener(
    id = "billingListener",
    destination = "billing.queue"
)
public void handleBilling(String message) {
    // Xử lý message billing.
}
~~~

Nếu bỏ qua `id`, Spring tự tạo ID. Điều đó vẫn cho phép listener hoạt động, nhưng khó quản lý bằng code vì ứng dụng không có tên ổn định để tra cứu.

Nên đặt ID rõ ràng khi cần:

- Tạm dừng hoặc khởi động một listener theo yêu cầu nghiệp vụ.
- Hiển thị trạng thái listener trên trang quản trị.
- Kiểm soát listener theo tenant hoặc nhóm chức năng.
- Viết kiểm thử tích hợp cho từng endpoint.
- Điều phối listener theo trạng thái phụ thuộc, ví dụ chỉ nhận message sau khi dữ liệu cấu hình đã sẵn sàng.

ID phải duy nhất trong registry. Nếu đăng ký hai endpoint cùng ID, Spring báo `IllegalStateException`. Đặt tên theo chức năng và giữ ổn định qua các lần khởi động.

Trong Spring Framework 7.0.10, `@JmsListener` có thuộc tính `id`, `destination`, `containerFactory`, `concurrency`, `selector` và `subscription`; annotation không có thuộc tính `autoStartup`. Auto-start của container được cấu hình qua listener container factory.

## 4. Truy cập container qua JmsListenerEndpointRegistry

Registry thường được inject theo kiểu:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.stereotype.Component;

@Component
public class ListenerMonitor {

    private final JmsListenerEndpointRegistry registry;

    public ListenerMonitor(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }
}
~~~

Các phương thức tra cứu quan trọng:

| Phương thức | Kết quả |
|---|---|
| `getListenerContainer(id)` | Container có ID tương ứng; trả về `null` nếu không tồn tại |
| `getListenerContainerIds()` | Tập ID của các container được registry quản lý |
| `getListenerContainers()` | Collection các container được registry quản lý |
| `isRunning()` | Trạng thái chạy của registry theo các container đang quản lý |

Ví dụ liệt kê listener. Đây là method fragment đặt bên trong class quản lý listener:

~~~java
import java.util.Set;

public Set<String> getListenerIds() {
    return registry.getListenerContainerIds();
}
~~~

Ví dụ lấy một container:

~~~java
import org.springframework.jms.listener.MessageListenerContainer;

public MessageListenerContainer findListener(String id) {
    MessageListenerContainer container = registry.getListenerContainer(id);

    if (container == null) {
        throw new IllegalArgumentException("Unknown JMS listener: " + id);
    }

    return container;
}
~~~

Collection trả về từ `getListenerContainers()` và tập ID là các góc nhìn để đọc, không phải nơi thêm hoặc xóa endpoint. Đăng ký endpoint bằng API đăng ký của registry hoặc hạ tầng cấu hình JMS.

## 5. Điều khiển một listener

`MessageListenerContainer` triển khai `SmartLifecycle`, vì vậy container có các thao tác `start()`, `stop()`, `isRunning()` và `getPhase()`.

Có thể điều khiển một listener cụ thể qua ID:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerControl {

    private final JmsListenerEndpointRegistry registry;

    public OrderListenerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container = requireContainer("ordersListener");

        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container = requireContainer("ordersListener");

        if (container.isRunning()) {
            container.stop();
        }
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer container = registry.getListenerContainer(id);

        if (container == null) {
            throw new IllegalArgumentException("Unknown JMS listener: " + id);
        }

        return container;
    }
}
~~~

Đây là class tích hợp trong ứng dụng Spring, cần có bean listener mang ID `ordersListener` và hạ tầng JMS đã cấu hình. Các phương thức có thể được gọi từ service quản trị, scheduler hoặc một luồng điều phối nội bộ.

Khi gọi `stop()`, container dừng việc nhận message. Endpoint vẫn nằm trong registry, nên có thể gọi `start()` để chạy lại. Việc dừng consumer không xóa Queue/Topic trên broker và không tự xóa message đang chờ. Message tiếp tục tuân theo retention, subscription và delivery policy của provider.

## 6. Điều khiển tất cả listener

Registry cũng triển khai `SmartLifecycle` và cung cấp `start()`, `stop()` để điều khiển toàn bộ container do nó quản lý.

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.stereotype.Component;

@Component
public class AllListenersControl {

    private final JmsListenerEndpointRegistry registry;

    public AllListenersControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseAllListeners() {
        registry.stop();
    }

    public void resumeAllListeners() {
        registry.start();
    }
}
~~~

Hai thao tác trên có phạm vi toàn registry:

- `registry.stop()` dừng tất cả container được registry quản lý.
- `registry.start()` gửi tín hiệu khởi động tới tất cả container được registry quản lý. Khi gọi sau khi ApplicationContext đã refresh, các container đã đăng ký sẽ được khởi động.

Nếu chỉ muốn dừng một listener, lấy container theo ID và gọi `stop()` trên container đó. Không dùng `registry.stop()` để tạm dừng một endpoint riêng lẻ vì các listener khác cũng sẽ dừng.

## 7. SmartLifecycle và vòng đời ApplicationContext

`JmsListenerEndpointRegistry` triển khai `SmartLifecycle`, một hợp đồng vòng đời của Spring. Nhờ vậy, Spring có thể khởi động và dừng registry theo vòng đời của ApplicationContext.

Các phương thức quan trọng:

- `start()`: khởi động các container được quản lý.
- `stop()`: dừng các container được quản lý theo cách đồng bộ.
- `stop(Runnable callback)`: dừng container và gọi callback sau khi các container đã dừng.
- `isRunning()`: cho biết registry có đang chạy hay không.
- `isAutoStartup()`: cho biết thành phần lifecycle có được Spring tự khởi động khi context refresh hay không.
- `getPhase()`: trả về phase dùng để sắp xếp thứ tự lifecycle.

Spring dùng phase để điều phối thứ tự start và stop giữa các thành phần lifecycle. Khi cấu hình phase tùy chỉnh cho listener container, các container được registry quản lý nên dùng phase nhất quán. Registry lấy phase từ container có phase tùy chỉnh; các giá trị tùy chỉnh khác nhau giữa các factory có thể gây lỗi phase mismatch.

Trong quá trình đóng ApplicationContext, Spring gọi lifecycle stop trước khi hủy bean. Registry dừng các container được quản lý; khi registry bị destroy, nó cũng hủy các container triển khai `DisposableBean`. Thông thường ứng dụng không cần tự gọi `destroy()`.

### 7.1. Dừng bất đồng bộ

`stop(Runnable callback)` hữu ích khi container cần thời gian hoàn tất thao tác dừng. Registry gửi yêu cầu dừng tới từng container và gọi callback sau khi tất cả callback dừng đã hoàn tất.

Ví dụ:

~~~java
registry.stop(() -> {
    System.out.println("All JMS listener containers have stopped");
});
~~~

Callback chỉ chạy sau khi registry nhận đủ tín hiệu dừng từ các container. Cách này phù hợp với quy trình shutdown cần phối hợp nhiều thành phần.

## 8. Cấu hình auto-start của listener container

Factory điều khiển việc container có tự khởi động trong lúc ApplicationContext refresh hay không. Ví dụ tắt auto-start:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setAutoStartup(false);
    return factory;
}
~~~

Với cấu hình này, listener container được tạo và đăng ký, nhưng không tự nhận message trong giai đoạn tự khởi động của context. Ứng dụng có thể đợi một điều kiện sẵn sàng rồi khởi động listener.

Ví dụ khởi động sau khi một dependency đã sẵn sàng:

~~~java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class StartupCoordinator {

    private final JmsListenerEndpointRegistry registry;

    public StartupCoordinator(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void onDependenciesReady() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException("ordersListener is not registered");
        }

        container.start();
    }
}
~~~

Cần phân biệt hai lớp cấu hình:

- `setAutoStartup(false)` trên factory điều khiển auto-start của các container được factory tạo.
- `registry.start()` là thao tác lifecycle ở phạm vi toàn registry; nó khởi động các container được quản lý khi được gọi tường minh sau khi context đã refresh.

Trong Spring Framework 7.0.10, `@JmsListener` không khai báo `autoStartup`. Hãy cấu hình thuộc tính này trên `JmsListenerContainerFactory` hoặc điều khiển trực tiếp container sau khi tra cứu bằng ID.

## 9. Đăng ký endpoint bằng code

Ngoài endpoint phát hiện từ `@JmsListener`, Spring cho phép đăng ký một `JmsListenerEndpoint` bằng code. `SimpleJmsListenerEndpoint` là triển khai đơn giản nhận một JMS `MessageListener`.

Ví dụ:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.config.JmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;
import org.springframework.stereotype.Component;

@Component
public class DynamicListenerRegistrar {

    private final JmsListenerEndpointRegistry registry;
    private final JmsListenerContainerFactory<?> listenerFactory;

    public DynamicListenerRegistrar(
            JmsListenerEndpointRegistry registry,
            @Qualifier("jmsListenerContainerFactory")
            JmsListenerContainerFactory<?> listenerFactory) {
        this.registry = registry;
        this.listenerFactory = listenerFactory;
    }

    public void register(String endpointId, String destination) {
        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId(endpointId);
        endpoint.setDestination(destination);
        endpoint.setMessageListener(
            message -> System.out.println("Received a dynamic JMS message")
        );

        registry.registerListenerContainer(endpoint, listenerFactory, true);
    }
}
~~~

Đây là ví dụ tích hợp; ứng dụng cần cung cấp một factory phù hợp và destination hợp lệ. Khi gọi sau khi context đã khởi động, tham số `startImmediately=true` yêu cầu registry khởi động container mới ngay nếu cần.

Có hai overload:

~~~java
registry.registerListenerContainer(endpoint, listenerFactory);
registry.registerListenerContainer(endpoint, listenerFactory, true);
~~~

Overload không có tham số boolean tương đương đăng ký mà không yêu cầu khởi động ngay. Khi cần endpoint hoạt động ngay sau khi đăng ký runtime, dùng overload có `true`.

Endpoint cần có ID khác các endpoint đang tồn tại. Nếu ID bị trùng, registry ném `IllegalStateException`. API registry cung cấp đăng ký và tra cứu container; không có API public tương ứng để unregister endpoint. Vì vậy, hãy thiết kế rõ vòng đời của endpoint động trước khi tạo nhiều endpoint theo tenant hoặc theo yêu cầu runtime.

### 9.1. Đăng ký endpoint trong giai đoạn cấu hình

Nếu endpoint được biết ngay lúc ứng dụng khởi động, có thể dùng `JmsListenerConfigurer` và `JmsListenerEndpointRegistrar` để đăng ký endpoint trong giai đoạn cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration
@EnableJms
public class ProgrammaticJmsConfiguration implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(JmsListenerEndpointRegistrar registrar) {
        var endpoint = new SimpleJmsListenerEndpoint();
        endpoint.setId("auditListener");
        endpoint.setDestination("audit.queue");
        endpoint.setMessageListener(
            message -> System.out.println("Audit message received")
        );

        registrar.registerEndpoint(endpoint);
    }
}
~~~

Registrar dùng trong giai đoạn đăng ký endpoint của cấu hình. Registry dùng ở runtime để truy cập và điều khiển các container đã được tạo. Hai đối tượng có vai trò liên quan nhưng khác nhau.

## 10. Registry quản lý những container nào?

Registry quản lý container được tạo từ các endpoint đã đăng ký với hạ tầng JMS listener, bao gồm endpoint phát hiện từ `@JmsListener` và endpoint đăng ký qua cơ chế endpoint registrar hoặc API đăng ký của registry.

Container được khai báo thủ công thành bean riêng không tự động thuộc registry:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean
DefaultMessageListenerContainer manualListenerContainer(
        ConnectionFactory connectionFactory) {
    var container = new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("manual.queue");
    container.setMessageListener(message -> {
        System.out.println("Manual container received a message");
    });
    return container;
}
~~~

Container này được quản lý như một bean Spring riêng. Ứng dụng có thể inject bean trực tiếp và điều khiển vòng đời của nó theo bean đó. `registry.getListenerContainers()` chỉ trả về các container do registry quản lý.

## 11. Điều phối listener theo trạng thái ứng dụng

Có thể dùng registry để điều khiển listener theo trạng thái nghiệp vụ hoặc trạng thái hạ tầng:

- Chỉ nhận message sau khi cache hoặc dữ liệu tham chiếu đã nạp xong.
- Tạm dừng một nhóm consumer trong lúc bảo trì.
- Khởi động lại listener sau khi broker hoặc dịch vụ phụ thuộc phục hồi.
- Chạy một số listener trong chế độ bảo trì trong khi listener khác tiếp tục hoạt động.
- Hiển thị ID và trạng thái container cho công cụ giám sát nội bộ.

Ví dụ quy trình:

~~~text
ApplicationContext khởi động
        |
        v
Các listener được đăng ký
        |
        v
Kiểm tra dependency và cấu hình
        |
        +---- Chưa sẵn sàng ---> Giữ listener ở trạng thái stopped
        |
        v
Dependency sẵn sàng
        |
        v
registry.getListenerContainer("ordersListener")
        |
        v
container.start()
        |
        v
Listener nhận và xử lý message
        |
        v
Bảo trì hoặc shutdown
        |
        v
container.stop() hoặc registry.stop()
~~~

Khi dừng listener, cần tính đến message đang tồn đọng và chính sách redelivery của broker. Nếu listener dùng transaction hoặc acknowledgement, cấu hình container và provider quyết định cách xử lý message đang được giao khi dừng.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `getListenerContainer(id)` trả về `null` | ID sai, endpoint chưa được đăng ký hoặc factory chưa tạo container | Kiểm tra ID trong `getListenerContainerIds()` và cấu hình annotation |
| Không tìm thấy bean container để inject | Container do registry quản lý không phải bean riêng trong context | Inject `JmsListenerEndpointRegistry` rồi tra cứu theo ID |
| Gọi `registry.stop()` làm mọi listener dừng | Phương thức điều khiển toàn bộ registry | Tra cứu container theo ID và gọi `stop()` trên container đó |
| Listener không tự nhận message sau khi khởi động | Factory đặt `autoStartup=false` hoặc container chưa được start | Kiểm tra factory và gọi `container.start()` khi điều kiện sẵn sàng |
| Hai endpoint cùng ID | ID bị trùng trong registry | Đặt ID duy nhất cho từng endpoint |
| Dynamic listener không chạy ngay | Đăng ký bằng overload không yêu cầu start ngay | Dùng `registerListenerContainer(endpoint, factory, true)` hoặc chủ động start container |
| Listener thủ công không xuất hiện trong registry | Container được khai báo thành bean riêng | Quản lý bean trực tiếp hoặc chuyển sang endpoint registration |
| Ứng dụng đóng nhưng listener chưa dừng đúng thứ tự | Lifecycle phase hoặc callback dừng chưa được phối hợp | Kiểm tra phase và dùng `stop(Runnable)` khi cần dừng bất đồng bộ |
| Listener nhận message lặp sau khi restart | Message được redeliver do acknowledgement/transaction | Thiết kế consumer idempotent và kiểm tra transaction của listener |
| Phase mismatch khi đăng ký nhiều container | Các factory dùng phase tùy chỉnh không đồng nhất | Dùng phase nhất quán cho các container cùng registry |

## 13. Nguyên tắc vận hành an toàn

- Đặt `id` tường minh cho listener cần quản lý ở runtime.
- Inject registry theo kiểu `JmsListenerEndpointRegistry`, không cố inject container do registry tạo như một bean riêng.
- Dùng `getListenerContainer(id)` và kiểm tra trường hợp không tìm thấy container.
- Dùng `container.start()` hoặc `container.stop()` khi chỉ điều khiển một listener.
- Dùng `registry.start()` và `registry.stop()` khi cần điều khiển toàn bộ listener do registry quản lý.
- Đặt `setAutoStartup(false)` trên factory nếu listener phải chờ điều kiện sẵn sàng trước khi nhận message.
- Dùng `registerListenerContainer(endpoint, factory, true)` khi đăng ký endpoint mới và cần chạy ngay.
- Đảm bảo ID của endpoint động là duy nhất.
- Phân biệt endpoint registrar dùng lúc cấu hình với endpoint registry dùng khi vận hành.
- Đặt lifecycle phase nhất quán nếu cần điều khiển thứ tự start/stop.
- Thiết kế acknowledgement, transaction và idempotency để xử lý message đang giao khi listener dừng hoặc khởi động lại.
- Theo dõi listener ID, trạng thái chạy, lỗi kết nối, số message xử lý và số lần redelivery.

## 14. Checklist triển khai

- [ ] Đã bật `@EnableJms` nếu dùng annotation listener.
- [ ] Đã khai báo `JmsListenerContainerFactory` phù hợp.
- [ ] Mỗi listener cần quản lý có ID ổn định và duy nhất.
- [ ] Đã biết container do registry tạo không phải bean riêng trong ApplicationContext.
- [ ] Đã dùng `getListenerContainerIds()` hoặc `getListenerContainer(id)` để tra cứu.
- [ ] Đã chọn điều khiển một container hay toàn registry.
- [ ] Đã cấu hình auto-start trên factory phù hợp với trình tự khởi động ứng dụng.
- [ ] Đã xử lý trường hợp ID không tồn tại.
- [ ] Nếu đăng ký endpoint runtime, đã đặt ID duy nhất và chọn `startImmediately` đúng yêu cầu.
- [ ] Đã kiểm tra lifecycle phase khi có nhiều factory tùy chỉnh.
- [ ] Đã phối hợp stop, transaction và acknowledgement trong shutdown.
- [ ] Đã kiểm thử start, stop, restart, context shutdown và dynamic registration.

## 15. Tài liệu tham khảo

- [Spring Framework — JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html)
- [Spring Framework — JmsListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework — JmsListenerEndpoint Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpoint.html)
- [Spring Framework — MessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/MessageListenerContainer.html)
- [Spring Framework — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework — SimpleJmsListenerEndpoint Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/SimpleJmsListenerEndpoint.html)
- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
