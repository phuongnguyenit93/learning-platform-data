# Lifecycle, SmartLifecycle và thứ tự start, stop theo phase

Khi một ứng dụng Spring Boot hoạt động, không phải thành phần nào cũng chỉ cần được tạo rồi sử dụng. Một số thành phần còn phải **bắt đầu** một hoạt động có vòng đời riêng, chẳng hạn mở consumer nhận message, khởi động bộ nhận sự kiện, bắt đầu scheduler tự quản lý hoặc kích hoạt một kết nối dài hạn. Khi ứng dụng dừng, các thành phần này cần **ngừng nhận công việc mới, hoàn tất công việc đang xử lý và giải phóng tài nguyên** theo một trật tự phù hợp.

Spring Framework cung cấp các hợp đồng `Lifecycle` và `SmartLifecycle` để mô hình hóa hai thao tác `start()` và `stop()`. Spring quản lý chúng thông qua `LifecycleProcessor`, thường là `DefaultLifecycleProcessor`, và dùng **phase** để xác định nhóm thành phần nào khởi động trước, dừng sau.

Điểm dễ nhầm là **phase không phải thứ tự tạo object bằng constructor**. Phase sắp xếp lời gọi start/stop của các bean tham gia lifecycle. Việc tạo bean, dependency injection, `@PostConstruct` và destruction callbacks vẫn tuân theo cơ chế bean lifecycle riêng.

## 1. Vì sao một bean cần lifecycle riêng?

Một bean thông thường có thể hoạt động ngay sau khi Spring khởi tạo:

~~~java
@Service
public class PricingService {
    public long total(long price, long shippingFee) {
        return price + shippingFee;
    }
}
~~~

`PricingService` không cần một lệnh “bắt đầu xử lý” độc lập. Nó chỉ cung cấp các phương thức nghiệp vụ.

Trái lại, một message consumer có thể cần:

1. Tạo object và nhận các dependency.
2. Thiết lập kết nối hoặc đăng ký subscription.
3. Bắt đầu nhận message từ broker.
4. Hoạt động trong suốt vòng đời ứng dụng.
5. Khi dừng, ngừng nhận message mới.
6. Hoàn tất hoặc hủy có kiểm soát những message đang xử lý.
7. Đóng kết nối và giải phóng tài nguyên.

Nếu những bước này được đặt hoàn toàn trong constructor hoặc `@PostConstruct`, khó tổ chức thứ tự bắt đầu và dừng giữa nhiều thành phần. Hợp đồng `Lifecycle` tách **việc object được tạo** khỏi **việc một hoạt động được bật hoặc tắt**.

Ví dụ:

~~~text
Tạo bean                 Hoạt động runtime                Đóng ứng dụng
   |                            |                              |
   v                            v                              v
constructor -> injection -> initialization -> start() -> ... -> stop() -> destroy
                                                 ^                 ^
                                                 |                 |
                                           Lifecycle             Lifecycle
~~~

Sơ đồ biểu diễn các mốc ở mức khái quát. Tùy scope và cách ứng dụng chạy, không phải bean nào cũng tham gia mọi bước.

## 2. Lifecycle: hợp đồng cơ bản của Spring

`Lifecycle` là interface trong Spring Framework:

~~~java
import org.springframework.context.Lifecycle;
~~~

Nó có ba phương thức chính:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Ý nghĩa:

| Phương thức | Trách nhiệm |
|---|---|
| `start()` | Đưa thành phần vào trạng thái đang hoạt động |
| `stop()` | Ngừng hoạt động và thực hiện thao tác cần thiết để dừng |
| `isRunning()` | Cho biết trạng thái hoạt động hiện tại theo hợp đồng của component |

Ví dụ một component đơn giản:

~~~java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public class PollingController implements Lifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("Polling enabled");
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("Polling disabled");
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
~~~

Ví dụ chỉ biểu diễn trạng thái bật/tắt; một polling component thật còn cần quản lý worker, scheduling, exception và tài nguyên I/O. `AtomicBoolean` làm minh họa an toàn hơn khi trạng thái có thể được truy cập từ nhiều thread.

### 2.1. Lifecycle không mặc nhiên tự start khi refresh

Một bean chỉ triển khai `Lifecycle` thông thường **không tự động được start chỉ vì context được refresh**, theo cơ chế `DefaultLifecycleProcessor` tiêu chuẩn. Nó thường được start khi gọi tường minh `ApplicationContext.start()`, hoặc khi việc khởi động một thành phần có dependency buộc xử lý lifecycle liên quan.

Ví dụ:

~~~java
import org.springframework.context.ConfigurableApplicationContext;

ConfigurableApplicationContext context = /* context đã được tạo */;
context.start();  // Yêu cầu lifecycle processor start các Lifecycle bean.
context.stop();   // Yêu cầu lifecycle processor stop các Lifecycle bean.
~~~

Việc gọi `start()` hay `stop()` lên context là một lời yêu cầu lifecycle. Nó **không tương đương** với tạo/refresh lại application context hoặc đóng nó hoàn toàn.

Nếu một thành phần phải tự động hoạt động ngay trong quá trình startup thông thường của Spring Boot, `SmartLifecycle` thường phù hợp hơn.

## 3. SmartLifecycle: mở rộng Lifecycle để tự động khởi động và dừng có phối hợp

`SmartLifecycle` nằm trong:

~~~java
import org.springframework.context.SmartLifecycle;
~~~

Interface này mở rộng `Lifecycle` và `Phased`, đồng thời bổ sung các khái niệm:

- **Auto-startup:** bean có được tự động start trong quá trình refresh context hay không.
- **Phase:** thứ tự ưu tiên tương đối khi start và stop nhiều lifecycle bean.
- **Callback dừng bất đồng bộ:** cho phép thông báo khi thao tác dừng hoàn tất bằng `stop(Runnable callback)`.

Với hành vi mặc định của Spring Framework hiện đại, `SmartLifecycle.isAutoStartup()` trả về `true` và phase mặc định của SmartLifecycle là `SmartLifecycle.DEFAULT_PHASE` (giá trị `Integer.MAX_VALUE`). Có thể override hai phương thức để biểu đạt nhu cầu thực tế của module.

### 3.1. Ví dụ SmartLifecycle hoàn chỉnh

~~~java
package com.example.messaging;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class MessageIngressLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("Start accepting messages");
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("Stop accepting messages");
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Ở đây:

- Khi Spring xử lý startup và lifecycle processor khởi động các auto-start SmartLifecycle bean, nó có thể gọi `start()` của component này.
- `isRunning()` phản ánh component đã được bật hay chưa.
- `getPhase() = 100` đặt nó vào một nhóm lifecycle tương đối.
- `stop(Runnable callback)` gọi `stop()` rồi thông báo đã hoàn tất bằng `callback.run()`.

Ví dụ dừng đồng bộ nên callback được gọi ngay sau khi `stop()` hoàn thành. Nếu việc ngừng nhận message và chờ message đang xử lý cần thời gian, không nên dùng callback ngay lập tức; cần thực hiện stop bất đồng bộ đúng cách như phần tiếp theo.

## 4. Phase là gì?

`SmartLifecycle` có method `getPhase()` từ interface `Phased`:

~~~java
@Override
public int getPhase() {
    return 100;
}
~~~

**Phase là một số nguyên thể hiện thứ tự tương đối giữa các nhóm lifecycle bean.**

Nguyên tắc:

- **Start:** phase nhỏ hơn chạy **trước** phase lớn hơn.
- **Stop:** phase lớn hơn được dừng **trước** phase nhỏ hơn.

Ví dụ ba thành phần:

| Bean | Phase | Trách nhiệm |
|---|---:|---|
| `ConnectionInfrastructure` | -100 | Chuẩn bị hạ tầng kết nối |
| `MessageProcessor` | 0 | Xử lý message |
| `InboundConsumer` | 100 | Bắt đầu nhận message mới |

Khi bắt đầu:

~~~text
START: tăng dần theo phase

phase -100: ConnectionInfrastructure.start()
      |
      v
phase    0: MessageProcessor.start()
      |
      v
phase  100: InboundConsumer.start()
~~~

Khi dừng:

~~~text
STOP: giảm dần theo phase

phase  100: InboundConsumer.stop(...)
      |
      v
phase    0: MessageProcessor.stop(...)
      |
      v
phase -100: ConnectionInfrastructure.stop(...)
~~~

Trật tự này có ích về mặt vận hành: **hạ tầng có trước khi bắt đầu nhận việc, và chỉ bị tắt sau khi ngừng nhận việc**.

### 4.1. Vì sao stop chạy ngược chiều start?

Giả sử consumer cần processor, còn processor cần connection.

Nếu shutdown theo đúng chiều start, connection có thể bị đóng trước khi consumer ngừng nhận message và processor hoàn tất xử lý. Hệ quả có thể là lỗi I/O và mất khả năng xử lý nốt công việc đang dở.

Khi shutdown ngược chiều:

1. Consumer ngừng lấy message mới.
2. Processor xử lý nốt hoặc hủy có kiểm soát những tác vụ còn lại.
3. Connection và hạ tầng hỗ trợ mới được giải phóng.

Đây là nguyên tắc thường gặp ở hệ thống có producer/consumer, listener container, streaming pipeline và resource pool.

### 4.2. Phase âm, 0 và phase dương

Phase có thể là số âm, 0 hoặc dương:

~~~java
@Override
public int getPhase() {
    return -1000;
}
~~~

Không có yêu cầu phase phải bắt đầu từ 0. Có thể dùng các khoảng có ý nghĩa như:

~~~text
-1000  Hạ tầng nền
 -100  Các dependency runtime
    0  Processor xử lý
  100  Consumer tiếp nhận
 1000  Entry point cần khởi động sau cùng
~~~

Đó là **quy ước tự chọn của dự án**, không phải các giá trị Spring bắt buộc. Mục tiêu là giữ đủ khoảng cách để bổ sung thành phần mới mà không phải đổi mọi phase.

### 4.3. Phase mặc định

Với Spring Framework hiện đại:

- Bean triển khai `SmartLifecycle` có phase mặc định là `SmartLifecycle.DEFAULT_PHASE`, tương ứng `Integer.MAX_VALUE`.
- Bean chỉ triển khai `Lifecycle` mà không có `Phased` thường được bộ xử lý lifecycle xem như phase 0 khi cần sắp xếp.

Vì vậy, một SmartLifecycle không override `getPhase()` thường được start khá muộn và stop khá sớm so với các bean có phase nhỏ hơn.

Không nên ngầm tin mọi bean framework có phase mặc định giống nhau. Các thành phần như web server, message listener container hoặc scheduler có thể khai báo phase của riêng chúng. Khi cần phối hợp chính xác với bean framework, hãy kiểm tra phase của thành phần đó trên phiên bản thư viện đang sử dụng.

## 5. SmartLifecycle và auto-startup

`SmartLifecycle` định nghĩa:

~~~java
@Override
public boolean isAutoStartup() {
    return true;
}
~~~

Khi `isAutoStartup()` trả về `true`, `DefaultLifecycleProcessor` cố gắng start bean trong quá trình refresh context, theo thứ tự phase và các dependency.

Nếu muốn component **không tự động bắt đầu** lúc startup:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

Khi đó, component có thể được start tường minh qua lifecycle processor hoặc khi `context.start()` được gọi, tùy cách điều phối. Cần phân biệt: `isAutoStartup() = false` không có nghĩa Spring không tạo bean instance. Nó chỉ nói về việc có **tự động gọi start trong lifecycle refresh** hay không.

### 5.1. SmartLifecycle và @Lazy

Một ngộ nhận khác là chỉ cần `@Lazy` thì SmartLifecycle sẽ không được tạo khi ứng dụng khởi động:

~~~java
@Lazy
@Component
class BackgroundConsumer implements SmartLifecycle {
    // ...
}
~~~

Trong nhiều trường hợp, lifecycle processor cần tìm các SmartLifecycle bean để quyết định auto-start nên vẫn có thể khiến bean được khởi tạo trong quá trình refresh, dù bean definition có `@Lazy`. Spring Framework lưu ý rằng auto-startup hỗ trợ khiến tác dụng của lazy-init trên SmartLifecycle bị giới hạn.

Nếu yêu cầu nghiệp vụ là **chỉ tạo và chạy một component khi người dùng thực sự yêu cầu**, đừng dựa hoàn toàn vào `@Lazy` kết hợp SmartLifecycle auto-start. Cân nhắc provider/factory có chủ đích và vòng đời được quản lý rõ ràng.

## 6. DefaultLifecycleProcessor hoạt động như thế nào?

`LifecycleProcessor` là giao diện mà Spring ApplicationContext sử dụng để điều khiển các lifecycle bean. Implementation mặc định thường là `DefaultLifecycleProcessor`.

Nó có hai trách nhiệm lớn:

1. Khi context refresh hoàn tất các bước khởi tạo cần thiết, gọi lifecycle startup cho những bean phù hợp.
2. Khi context đóng, điều phối stop lifecycle theo phase trước khi container hủy các singleton do nó quản lý.

Ở mức khái quát:

~~~text
ApplicationContext.refresh()
           |
           v
Tạo/đăng ký bean và hoàn thành các bước refresh cần thiết
           |
           v
LifecycleProcessor.onRefresh()
           |
           v
Chọn SmartLifecycle auto-start và dependency liên quan
           |
           v
Start theo phase tăng dần
           |
           v
Context hoàn thành refresh
           |
           v
Các sự kiện và runner của Spring Boot ở mốc tiếp theo
~~~

Và khi context đóng:

~~~text
ApplicationContext.close()
           |
           v
Phát ContextClosedEvent
           |
           v
LifecycleProcessor.onClose()
           |
           v
Stop theo phase giảm dần
           |
           v
Hủy singleton và gọi destruction callbacks
           |
           v
Giải phóng tài nguyên của context
~~~

Lưu ý rằng Spring có các bước shutdown phức tạp hơn, và quá trình đóng có thể bị ảnh hưởng bởi lỗi hoặc timeout. Sơ đồ giúp thấy mối quan hệ: **Lifecycle stop diễn ra trước việc hủy bean thông thường** trong shutdown có kiểm soát.

### 6.1. context.start() khác context.refresh()

~~~java
context.start();
~~~

là lời yêu cầu bắt đầu các lifecycle bean của một context đã được chuẩn bị. Nó không tạo một application context mới, cũng không thực hiện toàn bộ quy trình đăng ký lại bean definitions.

Tương tự:

~~~java
context.stop();
~~~

yêu cầu lifecycle beans dừng, nhưng context có thể vẫn tồn tại. `context.close()` mới thực hiện quá trình đóng container và destruction lifecycle.

Nói cách khác:

| Hành động | Ý nghĩa |
|---|---|
| `refresh()` | Xây dựng/làm mới context theo hợp đồng của implementation |
| `start()` | Yêu cầu các bean có Lifecycle bắt đầu |
| `stop()` | Yêu cầu các bean có Lifecycle dừng |
| `close()` | Đóng context và hủy tài nguyên/bean do context quản lý |

Trong Spring Boot, đừng gọi `refresh()` một cách tùy tiện trên context đang chạy chỉ để “restart service”. Nhu cầu start/stop một component nên được thiết kế theo lifecycle của chính component hoặc container phù hợp.

## 7. @DependsOn và dependency thực sự có thể ưu tiên hơn phase

Phase là quy tắc ordering cho lifecycle, nhưng **quan hệ phụ thuộc được khai báo rõ ràng có ưu tiên quan trọng**.

Giả sử bean consumer có phase nhỏ hơn connection pool, nhưng consumer lại khai báo phụ thuộc vào pool:

~~~java
@Configuration(proxyBeanMethods = false)
class IntegrationConfiguration {

    @Bean("connectionManager")
    ConnectionManager connectionManager() {
        return new ConnectionManager();
    }

    @Bean("inboundConsumer")
    @DependsOn("connectionManager")
    InboundConsumer inboundConsumer(ConnectionManager manager) {
        return new InboundConsumer(manager);
    }
}
~~~

Trong ví dụ:

- Bean `inboundConsumer` phụ thuộc `connectionManager`.
- Spring phải phân giải và tạo dependency khi cần tạo consumer.
- Với lifecycle dependencies, processor cố gắng đảm bảo dependency bắt đầu trước dependent và dừng sau dependent, kể cả khi phase có quan hệ tưởng như ngược lại.

Để giữ thiết kế dễ hiểu, nên làm **phase và dependency graph nhất quán** thay vì cố tình tạo thứ tự mâu thuẫn.

Nếu B cần A như dependency bình thường, ưu tiên constructor injection hoặc tham số `@Bean`:

~~~java
@Bean
InboundConsumer inboundConsumer(ConnectionManager manager) {
    return new InboundConsumer(manager);
}
~~~

`@DependsOn` hữu ích khi cần ràng buộc thứ tự khởi tạo theo tên bean mà không có dependency injection trực tiếp, ví dụ một side effect thiết lập tài nguyên. Không nên dùng nó để che giấu một dependency nghiệp vụ chưa được mô hình hóa.

### 7.1. @Order không điều khiển Lifecycle phase

`@Order` thường dùng để sắp xếp các bean trong collection hoặc extension point hỗ trợ ordering:

~~~java
@Component
@Order(10)
class FirstHandler implements Handler {
}
~~~

Điều đó không tương đương:

~~~java
@Override
public int getPhase() {
    return 10;
}
~~~

| Cơ chế | Phạm vi chính |
|---|---|
| `SmartLifecycle.getPhase()` | Điều phối start/stop của lifecycle components |
| `@Order` hoặc `Ordered` | Sắp xếp collection, pipeline hoặc extension point hỗ trợ ordering |
| `@DependsOn` | Tạo quan hệ phụ thuộc khởi tạo theo bean name |
| Constructor injection | Biểu diễn dependency thật giữa các bean |
| `@AutoConfiguration(before/after)` | Thứ tự xử lý các lớp auto-configuration, không phải thứ tự start/stop |

Không thay phase bằng `@Order` khi mục tiêu là “consumer phải stop trước connection manager”.

## 8. stop(Runnable callback): dừng bất đồng bộ đúng cách

`Lifecycle.stop()` là phương thức đồng bộ theo giao diện cơ bản. `SmartLifecycle` có thêm:

~~~java
void stop(Runnable callback);
~~~

Ý nghĩa là container có thể yêu cầu component bắt đầu quá trình dừng, rồi **được thông báo khi công việc dừng thực sự hoàn tất**.

`callback.run()` là tín hiệu hoàn thành cho lifecycle processor. Với dừng đồng bộ, có thể gọi callback sau `stop()`:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

### 8.1. Dừng bất đồng bộ cần báo hoàn tất khi thật sự dừng

Giả sử một component có API dừng trả về `CompletionStage<Void>`:

~~~java
public interface MessageReceiver {
    void startReceiving();
    java.util.concurrent.CompletionStage<Void> stopAndDrainAsync();
}
~~~

Một SmartLifecycle có thể triển khai:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public final class ReceiverLifecycle implements SmartLifecycle {

    private final MessageReceiver receiver;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public ReceiverLifecycle(MessageReceiver receiver) {
        this.receiver = receiver;
    }

    @Override
    public void start() {
        if (!running.get()) {
            receiver.startReceiving();
            running.set(true);
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.get()) {
            callback.run();
            return;
        }

        try {
            receiver.stopAndDrainAsync().whenComplete((ignored, failure) -> {
                try {
                    if (failure != null) {
                        // Ghi nhận lỗi dừng bằng logger của ứng dụng.
                    }
                    running.set(false);
                } finally {
                    callback.run();
                }
            });
        } catch (RuntimeException ex) {
            running.set(false);
            callback.run();
            throw ex;
        }
    }

    @Override
    public void stop() {
        // Đường dừng trực tiếp phải có chính sách đồng bộ riêng.
        receiver.stopAndDrainAsync().toCompletableFuture().join();
        running.set(false);
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

`MessageReceiver` là abstraction do ứng dụng định nghĩa; đoạn này minh họa **thời điểm callback cần được gọi**, không phải một implementation message broker đầy đủ.

Các điểm quan trọng:

- Không gọi `callback.run()` ngay sau khi lên lịch một tác vụ dừng bất đồng bộ nếu tác vụ vẫn đang chạy.
- Phải đảm bảo callback được gọi sau khi receiver đã ngừng nhận message và quá trình drain đã hoàn thành hoặc đã kết thúc theo chính sách lỗi.
- Với đường dừng đồng bộ `stop()`, cần đảm bảo trạng thái thực sự dừng trước khi method trả về.
- Các thao tác dừng nên có khả năng gọi lặp (idempotent) vì shutdown, failure handling hoặc điều khiển thủ công có thể gặp cùng component ở nhiều trạng thái.

Trong hệ thống thực tế, `stop()` và `stop(Runnable)` nên dùng chung một state machine hoặc một thao tác dừng có kiểm soát để tránh dừng trùng, gọi callback hai lần hoặc tạo race condition.

### 8.2. Nếu quên gọi callback thì sao?

Lifecycle processor sử dụng callback để biết rằng một SmartLifecycle đã hoàn thành dừng. Nếu component không gọi callback, quá trình shutdown có thể phải chờ **hết timeout của phase** trước khi tiếp tục.

Dấu hiệu có thể thấy:

- Ứng dụng dừng chậm.
- Log cảnh báo timeout ở một nhóm phase.
- Những dependency ở phase thấp hơn bị giữ lại lâu hơn dự kiến.
- Kubernetes hoặc hệ thống orchestration có thể hết thời gian cho phép trước khi shutdown hoàn tất.

Do đó, một SmartLifecycle có dừng async phải thiết kế đường hoàn thành **thành công, thất bại và hủy** sao cho callback được báo đúng lúc. Không nên để một exception trên worker thread âm thầm làm mất tín hiệu hoàn thành.

## 9. Timeout cho từng shutdown phase trong Spring Boot

Dừng các thành phần có thể mất thời gian, nhất là khi cần chờ request hoặc message đang xử lý. Spring Boot cung cấp property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Hoặc YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Property này đặt khoảng thời gian chờ tối đa cho **mỗi phase khi shutdown**, trong phạm vi cơ chế lifecycle processor tương ứng. Nó không đồng nghĩa với “toàn bộ ứng dụng chắc chắn thoát trong đúng 20 giây”.

Ví dụ có ba phase:

~~~text
phase 100: chờ stop của InboundConsumer (tối đa theo timeout phase)
phase   0: chờ stop của MessageProcessor
phase -100: chờ stop của ConnectionInfrastructure
~~~

Nếu một phase có nhiều bean dừng bất đồng bộ, lifecycle processor phối hợp đợi những callback trong phase đó theo ngân sách thời gian phase. Các phase khác vẫn có giai đoạn dừng riêng.

Timeout nên được chọn dựa trên đặc tính nghiệp vụ:

- Tác vụ bình thường cần bao lâu để hoàn thành?
- Có cho phép ngừng nhận message mới trước khi chờ task đang xử lý không?
- Nếu quá hạn, có thể hủy task, rollback hoặc phát lại message không?
- Nền tảng triển khai có giới hạn dừng tiến trình bao lâu?
- Broker hoặc external service có timeout riêng không?

**Không nên chỉ tăng timeout để che giấu callback bị quên hoặc một component không thể dừng.** Timeout chỉ là cơ chế giới hạn việc chờ; thành phần vẫn cần có logic dừng đúng.

## 10. Kết hợp với graceful shutdown của web server

Lifecycle stop hữu ích cho message consumers, schedulers và resource managers. Với HTTP server, Spring Boot còn có cơ chế **graceful shutdown** để ngừng nhận request mới theo đặc tính web server, đồng thời cho request đang xử lý một khoảng thời gian hoàn tất.

Ví dụ cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Cần phân biệt:

- `server.shutdown=graceful` là lựa chọn hành vi dừng web server được Spring Boot hỗ trợ.
- `spring.lifecycle.timeout-per-shutdown-phase` liên quan ngân sách thời gian chờ từng phase trong quá trình lifecycle shutdown.
- SmartLifecycle của một consumer tùy chỉnh phải tự triển khai logic ngừng nhận, drain và callback; cấu hình graceful HTTP không tự dừng message broker thay consumer.

Ví dụ kiến trúc mong muốn:

~~~text
Bắt đầu:
    tạo bean và tài nguyên
           |
           v
    bắt đầu infrastructure
           |
           v
    bắt đầu processor
           |
           v
    bắt đầu nguồn nhận traffic/message

Dừng:
    ngừng tiếp nhận traffic/message mới
           |
           v
    chờ công việc đang xử lý kết thúc
           |
           v
    dừng processor
           |
           v
    giải phóng infrastructure và resource
~~~

Khi dùng web server và các SmartLifecycle tự viết, cần xem phase của web server lifecycle trên phiên bản Boot sử dụng để phối hợp chính xác. Đừng tự đoán web server luôn ở phase 0.

Việc JVM nhận SIGTERM, application context đóng và orchestration platform cho phép bao lâu là những yếu tố vận hành riêng. Nếu môi trường chỉ cho 10 giây để dừng process nhưng hệ thống có nhiều phase cùng timeout dài hơn, cấu hình lifecycle không thể tự kéo dài hạn chót của nền tảng triển khai.

## 11. SmartLifecycle khác @PostConstruct, @PreDestroy như thế nào?

Cả hai nhóm API đều liên quan vòng đời bean, nhưng thời điểm và mục đích khác nhau.

| Cơ chế | Mốc thực hiện | Mục đích thường gặp |
|---|---|---|
| Constructor | Khi tạo instance | Khởi tạo trạng thái cơ bản |
| Dependency injection | Trước khi bean hoàn tất khởi tạo | Cung cấp dependency |
| `@PostConstruct` | Sau khi inject dependency | Chuẩn bị trạng thái nội bộ của bean |
| `SmartLifecycle.start()` | Khi lifecycle processor start component | Bắt đầu hoạt động runtime dài hạn |
| `SmartLifecycle.stop(Runnable)` | Khi lifecycle processor yêu cầu dừng | Ngừng hoạt động có thứ tự và báo hoàn tất |
| `@PreDestroy` | Khi Spring hủy bean được quản lý | Giải phóng tài nguyên cuối vòng đời |
| `DisposableBean.destroy()` | Trong destruction callbacks | Dọn dẹp ở giai đoạn destroy |

Ví dụ bean vừa chuẩn bị trạng thái vừa chạy một consumer:

~~~java
@Component
public class JobConsumer implements SmartLifecycle {

    private boolean running;

    @PostConstruct
    void prepareResources() {
        // Khởi tạo nội bộ, không bắt đầu consume message.
    }

    @Override
    public void start() {
        running = true;
        // Bắt đầu consume.
    }

    @Override
    public void stop() {
        running = false;
        // Ngừng consume.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

Trong ví dụ, `@PostConstruct` không làm thay công việc `start()`. Ngược lại, `@PreDestroy` cũng không thay thế hoàn toàn nhu cầu dừng theo phase nếu component cần nhường lượt cho các thành phần khác.

Đối với Spring Boot hiện đại dựa trên Jakarta APIs, import:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Với các phiên bản Spring Boot 2.x dựa trên Spring Framework 5.x, import lifecycle annotation thường dùng namespace `javax.annotation`. Thay đổi này không làm đổi ý nghĩa của `Lifecycle` hay `SmartLifecycle`, vốn là các interface thuộc Spring Framework.

## 12. Thời điểm start/stop so với startup events và runner

Spring Boot cung cấp nhiều mốc startup:

~~~text
Tạo và cấu hình ApplicationContext
           |
           v
Refresh context và khởi tạo singleton cần thiết
           |
           v
LifecycleProcessor.onRefresh() / SmartLifecycle.start()
           |
           v
Context refresh hoàn thành
           |
           v
ApplicationStartedEvent
           |
           v
ApplicationRunner / CommandLineRunner
           |
           v
ApplicationReadyEvent
~~~

Điều đó cho thấy một SmartLifecycle auto-start thường được bật **trong quá trình refresh context**, trước khi `ApplicationStartedEvent` và trước khi các runner chạy.

Nếu component cần ứng dụng đã chạy xong runner hoặc đã sẵn sàng nhận traffic mới bắt đầu một công việc nghiệp vụ, chỉ sử dụng `SmartLifecycle` auto-start có thể không đúng mốc. Hãy cân nhắc `ApplicationReadyEvent` hoặc một cơ chế startup orchestration thích hợp.

Đồng thời, không nên dùng `ApplicationReadyEvent` để thay cho khả năng stop có thứ tự. Một bean có quá trình hoạt động dài hạn có thể vẫn cần `SmartLifecycle` để được Spring điều phối khi shutdown.

## 13. Một ví dụ với ba SmartLifecycle bean

Giả sử một ứng dụng nhận message từ queue rồi xử lý dựa trên tài nguyên chung. Ta tách ba lớp:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public abstract class AbstractPhasedComponent implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();
    private final String name;
    private final int phase;

    protected AbstractPhasedComponent(String name, int phase) {
        this.name = name;
        this.phase = phase;
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("START " + name);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("STOP " + name);
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return phase;
    }
}
~~~

Khai báo các bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ProcessingLifecycleConfiguration {

    @Bean
    AbstractPhasedComponent connectionInfrastructure() {
        return new AbstractPhasedComponent("connection", -100) {};
    }

    @Bean
    AbstractPhasedComponent messageProcessor() {
        return new AbstractPhasedComponent("processor", 0) {};
    }

    @Bean
    AbstractPhasedComponent inboundConsumer() {
        return new AbstractPhasedComponent("consumer", 100) {};
    }
}
~~~

Khi Spring refresh context và tự động start SmartLifecycle, thứ tự dự kiến:

~~~text
START connection
START processor
START consumer
~~~

Khi context đóng có kiểm soát:

~~~text
STOP consumer
STOP processor
STOP connection
~~~

Điều này minh họa quan hệ phase. Trong ứng dụng thực tế, các component nên có tên và kiểu rõ ràng, kết hợp dependency injection cho resource mà chúng sử dụng, thay vì chỉ phát log.

Nếu hai bean có **cùng phase**, không nên dựa vào thứ tự đăng ký để thiết lập quan hệ bắt buộc giữa chúng. Hãy dùng dependency hoặc phase khác nếu thực sự có quan hệ start/stop.

## 14. Kiểm thử phase và shutdown

Có thể kiểm thử thứ tự start/stop bằng một context nhỏ để quan sát các callback mà không cần khởi chạy web server.

### 14.1. Bean ghi nhận lifecycle event

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

final class RecordingLifecycle implements SmartLifecycle {

    private final String name;
    private final int phase;
    private final List<String> events;
    private final AtomicBoolean running = new AtomicBoolean();

    RecordingLifecycle(String name, int phase, List<String> events) {
        this.name = name;
        this.phase = phase;
        this.events = events;
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            events.add("start:" + name);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            events.add("stop:" + name);
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

### 14.2. Configuration cho test

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class LifecycleTestConfiguration {

    @Bean
    List<String> events() {
        return new CopyOnWriteArrayList<>();
    }

    @Bean
    RecordingLifecycle infrastructure(List<String> events) {
        return new RecordingLifecycle("infra", -100, events);
    }

    @Bean
    RecordingLifecycle consumer(List<String> events) {
        return new RecordingLifecycle("consumer", 100, events);
    }
}
~~~

### 14.3. Assertion trước và sau close

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LifecyclePhaseTest {

    @Test
    void startsAscendingAndStopsDescending() {
        var context = new AnnotationConfigApplicationContext(
                LifecycleTestConfiguration.class);

        List<String> events = context.getBean("events", List.class);

        assertThat(events).containsExactly(
                "start:infra",
                "start:consumer"
        );

        context.close();

        assertThat(events).containsExactly(
                "start:infra",
                "start:consumer",
                "stop:consumer",
                "stop:infra"
        );
    }
}
~~~

Test tạo context, quan sát auto-start sau refresh, rồi đóng context và xác nhận stop diễn ra theo phase ngược lại. Vì các callback minh họa đều đồng bộ, test có thể kiểm tra thứ tự trực tiếp.

Trong hệ thống thực tế, nên có thêm các test:

- `isAutoStartup() = false` không tự start theo đường refresh thông thường.
- `start()` và `stop()` có thể gọi lặp mà không gây tác động không mong muốn.
- `stop(Runnable)` chỉ gọi callback khi drain đã hoàn tất.
- Đường lỗi khi drain thất bại vẫn phát tín hiệu hoàn tất theo chính sách.
- Timeout được xử lý khi một component không phản hồi.
- Dependency `@DependsOn` được tôn trọng dù phase cần phối hợp.
- Sau `close()`, component không tiếp tục nhận công việc mới.

Test unit cho `getPhase()` không đủ để chứng minh container thật sự điều phối lifecycle đúng cách. Nên kiểm thử với `ApplicationContext` thật cho những ràng buộc start/stop quan trọng.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bean đã được tạo nhưng không start | Chỉ triển khai `Lifecycle` hoặc `isAutoStartup() = false` | Chọn `SmartLifecycle` với auto-start phù hợp; kiểm tra lời gọi `context.start()` |
| Listener/consumer start quá sớm | Phase quá thấp hoặc start khi resource chưa sẵn sàng | Xác định dependency và tăng phase thích hợp |
| Resource bị đóng trước khi consumer dừng | Phase và dependency không phản ánh quan hệ sử dụng | Cho consumer phase cao hơn resource; biểu diễn dependency rõ |
| Ứng dụng dừng rất chậm | `stop(Runnable)` không gọi callback hoặc drain bị kẹt | Đảm bảo callback ở mọi đường hoàn tất; đặt timeout phù hợp |
| Gọi stop rồi isRunning vẫn true | Trạng thái không được cập nhật đúng | Thiết kế state machine và cập nhật flag sau khi dừng hoàn tất |
| @Order không làm thay đổi thứ tự start | Nhầm collection ordering với lifecycle phase | Dùng `getPhase()` |
| @Lazy nhưng bean vẫn được tạo khi startup | Auto-start của `SmartLifecycle` khiến processor phải xử lý bean | Chọn kiến trúc lazy thực sự thay vì dựa vào annotation |
| @PreDestroy chạy nhưng tác vụ đang nhận message | Chưa dùng lifecycle stop để chặn nguồn việc | Triển khai stop, drain và callback đúng |
| Phase giống nhau cho nhiều bean phụ thuộc lẫn nhau | Chưa khai báo quan hệ phụ thuộc cần thiết | Dùng dependency injection hoặc `@DependsOn` |
| Lỗi shutdown chỉ xảy ra khi triển khai | Timeout của nền tảng nhỏ hơn thời gian drain | Phối hợp deadline vận hành với shutdown-phase timeout |

### 15.1. Quan sát lifecycle bằng log

Có thể bật log chi tiết cho hạ tầng lifecycle trong môi trường phát triển:

~~~properties
logging.level.org.springframework.context.support.DefaultLifecycleProcessor=DEBUG
~~~

Thông điệp cụ thể phụ thuộc phiên bản Spring. Log giúp thấy những thành phần đang start/stop và có thể hỗ trợ chẩn đoán timeout. Không nên bật logging quá chi tiết tại production nếu tạo nhiều log hoặc tiết lộ cấu trúc nội bộ.

Ngoài log framework, các component quan trọng nên ghi nhận những mốc như “stop requested”, “no longer accepting work”, “in-flight work drained” và “callback completed”, nhưng không ghi dữ liệu bí mật hoặc payload nhạy cảm.

## 16. Khi nào nên sử dụng SmartLifecycle?

`SmartLifecycle` hữu ích với những bean có **hoạt động runtime dài hạn cần start/stop riêng và cần phối hợp với bean khác**:

- Consumer hoặc listener nhận message từ broker.
- Một scheduler tự quản lý vòng chạy hoặc hệ thống polling.
- Thành phần nhận dữ liệu liên tục từ socket/stream.
- Pipeline nhiều bước cần ngừng ingress trước khi đóng worker.
- Kết nối dài hạn hoặc subsystem có giai đoạn activate/deactivate riêng.
- Hạ tầng cần dừng có kiểm soát để ứng dụng đóng an toàn.

`SmartLifecycle` thường không cần thiết cho:

- Service stateless chỉ cung cấp method cho controller.
- Repository/JPA entity hoặc DTO bình thường.
- Object chỉ cần dọn dẹp khi bị hủy, không có hoạt động dài hạn cần start/stop riêng.
- Công việc chạy **một lần** sau startup, vốn có thể phù hợp hơn với `ApplicationRunner` hoặc `CommandLineRunner`.
- Một task cần bắt đầu sau khi Boot sẵn sàng hoàn toàn, nếu `ApplicationReadyEvent` mới là mốc đúng.

Nhiều framework integration đã triển khai lifecycle cho listener container, web server hoặc scheduler. Không nên bọc thêm SmartLifecycle chỉ vì muốn “chắc chắn nó có lifecycle”; trước tiên xem thành phần đã có cơ chế start/stop và cấu hình phase riêng hay chưa.

## 17. Những nguyên tắc cần ghi nhớ

1. **Phân biệt tạo bean và start component.** Constructor/`@PostConstruct` giải quyết khởi tạo object; `Lifecycle.start()` bật một hoạt động runtime.
2. **Dùng `SmartLifecycle` khi cần auto-start và phase.** `Lifecycle` cơ bản không tự động start khi refresh theo quy tắc mặc định.
3. **Phase nhỏ start trước, stop sau.** Phase lớn start sau, stop trước.
4. **Dependency quan trọng hơn con số phase.** Biểu diễn quan hệ thật bằng constructor injection và `@DependsOn` khi phù hợp.
5. **Đừng dùng `@Order` để điều phối start/stop.** Đó là một cơ chế ordering khác.
6. **Dừng async phải gọi callback.** Gọi `callback.run()` sau khi công việc dừng hoàn tất; không báo hoàn tất khi vẫn còn task đang chạy.
7. **Đặt timeout phù hợp.** `spring.lifecycle.timeout-per-shutdown-phase` giới hạn thời gian chờ của từng phase; nó không thay thế logic stop đúng.
8. **Phối hợp với shutdown của môi trường.** Graceful web shutdown, broker acknowledgement và giới hạn SIGTERM/orchestration là các yếu tố cần xem xét cùng lifecycle.
9. **Kiểm thử với context thật.** Start/stop order, auto-start flag, callback và các tình huống lỗi cần được kiểm chứng qua lifecycle processor.
10. **Giữ hành vi idempotent, quan sát được và có giới hạn.** Startup và shutdown là hai giai đoạn dễ phát sinh sự cố; những trạng thái không rõ ràng sẽ làm ứng dụng khó vận hành.

`Lifecycle` cung cấp hợp đồng tối thiểu `start()`, `stop()` và `isRunning()`. `SmartLifecycle` bổ sung auto-start, phase và khả năng thông báo kết thúc dừng bất đồng bộ. Spring điều phối các thành phần theo **phase tăng dần lúc start và giảm dần lúc stop**, trong khi dependency graph vẫn giữ vai trò bảo đảm các thành phần phụ thuộc được xử lý đúng. Hiểu đúng sự khác biệt này giúp tổ chức các consumer, worker và hạ tầng trong Spring Boot để khởi động có trật tự và dừng an toàn.
