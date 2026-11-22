# receiveTimeout và độ phản hồi khi nhàn rỗi trong DefaultMessageListenerContainer (Spring JMS)

## 1. Tình huống: queue trống, listener vẫn phải sẵn sàng

Một dịch vụ Spring Boot nhận sự kiện từ queue `orders.in` bằng `@JmsListener`. Ban ngày queue có nhiều sự kiện; ban đêm gần như trống. Kỹ sư vận hành muốn vừa tiết kiệm tài nguyên khi không có message, vừa tiếp nhận nhanh khi message mới xuất hiện, lại dừng ứng dụng sạch khi deploy phiên bản mới.

Spring JMS cung cấp `org.springframework.jms.listener.DefaultMessageListenerContainer` (DMLC) để quản lý consumer. Container này chủ động gọi `MessageConsumer.receive(...)` trong các worker tasks. Thuộc tính `receiveTimeout` điều khiển **thời gian tối đa của một lần chờ nhận khi không có message**, tính bằng mili giây. Giá trị này liên quan trực tiếp đến lúc phát hiện **empty receive**, dừng hoặc thu hẹp các consumer không cần thiết và thời gian phản hồi của các hoạt động lifecycle.

Cần tránh kết luận sai: **`receiveTimeout=1000` không có nghĩa mọi message mới phải chờ đủ một giây mới được xử lý.** Nếu consumer đã ở trong lời gọi blocking receive và provider hỗ trợ nhận bình thường, message đến có thể đánh thức nó ngay. Một giây là giới hạn chờ của *lượt receive không nhận được message*, không phải chu kỳ hẹn giờ bắt buộc mà message phải đợi.

Mục tiêu bài học:

- Hiểu `receiveTimeout` của **DefaultMessageListenerContainer** và các giá trị `0`, số âm, số dương.
- Hiểu thread/consumer làm gì khi queue nhàn rỗi và khi có message vừa đến.
- Phân biệt latency tiếp nhận message, phát hiện idle, scale-down và shutdown/recovery.
- Đọc đúng `concurrentConsumers`, `maxConcurrentConsumers`, `idleConsumerLimit`, `idleReceivesPerTaskLimit`, `idleTaskExecutionLimit` và `maxMessagesPerTask`.
- Cấu hình bằng Spring Boot hoặc `DefaultJmsListenerContainerFactory`, kiểm thử và quan sát bằng một ví dụ Java 17+ có thể chạy trong project Spring Boot.

## 2. DMLC là listener bất đồng bộ ở cấp ứng dụng nhưng dùng blocking receive

Mã handler có vẻ “được gọi tự động”:

```java
@JmsListener(destination = "orders.in")
public void handle(String payload) {
    businessService.process(payload);
}
```

Đây là **đoạn method minh họa trong một Spring bean**, với `businessService` đã inject. Ứng dụng không gọi `receive` ở method này. Tuy vậy, bên dưới hạ tầng DMLC có thể sử dụng `MessageConsumer.receive(timeout)` trên thread do container quản lý:

```text
                        Spring ApplicationContext
                                  |
                              @JmsListener
                                  |
                      JmsListenerContainerFactory
                                  |
                                  v
                    DefaultMessageListenerContainer
                                  |
                +-----------------+-----------------+
                |                                   |
       consumer task #1                       consumer task #2
       (core hoặc surplus)                    (nếu được scale up)
                |                                   |
           JMS Session                         JMS Session
                |                                   |
     MessageConsumer.receive(T)         MessageConsumer.receive(T)
                |                                   |
          +-----+------+                      +-----+------+
          |            |                      |            |
        Message       null                  Message       null
          |       sau timeout                 |       sau timeout
          v            |                      v            |
     gọi handler  nhận lượt tiếp        gọi handler    đánh giá idle
          |            |                      |            |
       ACK/commit      +----------------------+            v
                                                có thể scale down surplus
```

Điều quan trọng:

1. **Container làm polling thay ứng dụng.** `@JmsListener` vẫn là mô hình xử lý hướng sự kiện ở tầng nghiệp vụ; nó không đồng nghĩa với busy-wait trong code người dùng.
2. **Thread chờ receive có thể bị block.** Vì thế `receiveTimeout` liên quan đến thời điểm thread quay lại vòng xử lý để xem trạng thái stop và cập nhật bookkeeping.
3. **Lượt receive trả `null` là bình thường** nếu queue không có message trong thời gian chờ. Nó không có nghĩa broker lỗi hay handler đã xử lý một message rỗng.
4. **Handler chỉ được gọi khi thực sự có message** được giao và adapter chuyển đổi thành dữ liệu hợp lệ; không có `@JmsListener` invocation theo mỗi lần timeout rỗng.
5. DMLC có **core consumers** duy trì nền và **surplus consumers** được thêm khi có tải, nếu cấu hình max lớn hơn min.

Không gộp DMLC với `SimpleMessageListenerContainer`. Loại Simple dựa vào việc đăng ký JMS `MessageListener` với provider, còn DMLC triển khai receive loop và các cơ chế scale/recovery riêng. Các chi tiết timeout/idle trong bài là của **DefaultMessageListenerContainer**, không áp đặt cho mọi container JMS.

## 3. Ngữ nghĩa chính xác của receiveTimeout

Trong Spring Framework 6.2, `AbstractPollingMessageListenerContainer` (lớp cha của DMLC) khai báo:

```java
public static final long DEFAULT_RECEIVE_TIMEOUT = 1000L;

// API cấu hình:
public void setReceiveTimeout(long receiveTimeout);
```

Đây là **chữ ký/constant API minh họa**, không phải code cần định nghĩa lại. Mặc định `receiveTimeout` là **1.000 ms = 1 giây**, tính trên một lần gọi receive trong vòng xử lý.

| Cấu hình ở DMLC | Ý nghĩa | Khi nào nên dùng |
| --- | --- | --- |
| `setReceiveTimeout(1000L)` | Chờ tối đa khoảng 1 giây cho một lần receive nếu không có message | Mặc định cân bằng, điểm khởi đầu tốt |
| `setReceiveTimeout(250L)` | Lượt chờ ngắn hơn | Có yêu cầu kiểm tra trạng thái/nhận diện idle nhanh hơn, chấp nhận nhiều vòng nhận hơn |
| `setReceiveTimeout(5000L)` | Lượt chờ lâu hơn | Muốn giảm tần suất empty returns và hạn chế dao động consumer, khi transaction/shutdown cho phép |
| `setReceiveTimeout(0L)` | **Chờ vô hạn** khi không có message | Nói chung **không khuyến khích**, vì khó shutdown sạch và không phù hợp với nhiều cấu hình transaction manager |
| `setReceiveTimeout(-1L)` | **No-wait receive**; không đợi message | Trường hợp đặc biệt có kiểm soát; không coi là cách tối ưu mặc định |

Javadoc Spring nêu rõ: giá trị này cần **nhỏ hơn transaction timeout** của transaction manager nếu có transaction manager. `0` chờ vô hạn thường không phù hợp do container không thể dừng sạch một cách đáng tin khi receive cứ chờ message. Số âm như `-1` được ánh xạ thành receive không chờ.

### 3.1. Vì sao số 0 hay gây nhầm?

Ba API dễ bị đọc sai:

| Vị trí | Giá trị `0` | Giá trị `-1` |
| --- | --- | --- |
| `DefaultMessageListenerContainer.setReceiveTimeout` | Chờ vô hạn | No-wait |
| `jakarta.jms.MessageConsumer.receive(long timeout)` | Chờ vô hạn theo JMS API | Không nên xem `-1` là cách gọi portable trực tiếp; dùng `receiveNoWait()` |
| `JmsTemplate.setReceiveTimeout` | **No-wait** theo quy ước template | **Chờ vô hạn** theo quy ước template |

DMLC và `JmsTemplate` **không dùng cùng quy ước** cho hai giá trị đặc biệt. Đừng copy `setReceiveTimeout(0)` của `JmsTemplate` vào DMLC với ý định poll không chờ.

Nếu không cần zero/negative semantics, nên dùng **giá trị dương hữu hạn** theo đơn vị rõ ràng, chẳng hạn `250ms`, `1s`, `3s` trong Spring Boot configuration.

### 3.2. receiveTimeout chỉ áp dụng cho một lần nhận

Giả sử timeout `T = 1000ms` và queue trống. Một worker gọi receive, sau khoảng thời gian T mà không có message thì nhận `null`. Container cập nhật trạng thái idle rồi có thể bắt đầu lượt receive tiếp hoặc quyết định tái lịch/thu hẹp task.

Nếu message đến ở thời điểm `t = 300ms` trong khi consumer đang chờ, provider có thể trả message ngay, không phải đợi hết `T`. Nếu message đến đúng lúc container đang thay đổi task/connection, có thêm scheduling/recovery overhead. Vì thế không thể kết luận latency nhận chính xác là `T`, `T/2` hay `0` chỉ từ giá trị timeout.

Ví dụ timeline:

```text
T = 1000 ms

t=0ms      consumer bắt đầu receive(T)
t=300ms    broker có message M1
t≈300ms    receive có thể trả M1 ngay nếu consumer đang sẵn sàng
           -> adapter -> @JmsListener -> handler

t=500ms    worker bắt đầu receive(T) lần kế tiếp
t=1500ms   không có message -> receive trả null
           -> container ghi nhận empty receive/idle
           -> bắt đầu nhận tiếp hoặc quyết định lifecycle
```

Các mốc xấp xỉ chỉ để giải thích. Chúng **không phải SLA** hoặc kết quả benchmark cho Artemis hay provider bất kỳ.

## 4. “Độ phản hồi khi nhàn rỗi” thực chất gồm nhiều đại lượng

Một câu “timeout càng ngắn thì listener càng responsive” quá mơ hồ. Nên tách ít nhất năm đại lượng:

| Đại lượng | Cần đo gì? | Vai trò của receiveTimeout |
| --- | --- | --- |
| **Message arrival-to-dispatch latency** | Message đã khả dụng trên broker → handler bắt đầu | Có thể nhỏ hơn T rất nhiều nếu consumer đang chờ; còn phụ thuộc provider, network, thread/executor |
| **Empty-receive detection time** | Bao lâu container biết lần receive không có message | Thường tối đa khoảng T cho một lượt receive đang chờ |
| **Surplus-consumer scale-down delay** | Sau khi hết tải, bao lâu consumer **dư** được giảm | Phụ thuộc T *và* giới hạn idle, kiểu executor, maxMessagesPerTask |
| **Stop/shutdown responsiveness** | Khi yêu cầu dừng, bao lâu receive loop nhường quyền cho lifecycle | T hữu hạn thường tạo cơ hội kiểm tra trạng thái; stop thực tế còn tùy provider và handler in-flight |
| **Recovery latency** | Broker down rồi lên, bao lâu có consumer hoạt động lại | Phụ thuộc recovery/backoff và kết nối; **không** do receiveTimeout một mình quyết định |

**Kết luận quan trọng:** giảm T từ `1000ms` xuống `100ms` **không chứng minh p95 business latency giảm 10 lần**. Nếu consumer luôn block trong receive và được provider đánh thức ngay, thông số ảnh hưởng mạnh hơn có thể là thread scheduling, broker dispatch, network, số consumer, throughput xử lý hoặc prefetch.

### 4.1. Khi queue hoàn toàn trống

Một core consumer vẫn có thể tồn tại và tiếp tục vòng receive. “Nhàn rỗi” **không** có nghĩa container đã dừng hay đã giải phóng tất cả threads. Mức tiêu thụ CPU thường thấp khi thread block hợp lý, nhưng connection/consumer/session vẫn có tài nguyên.

### 4.2. Khi tải xuất hiện lại sau một quãng im lặng

Nếu có sẵn core consumer đã connected và đang chờ, message mới có thể được xử lý sớm. Nếu tất cả consumers đã bị stop thủ công, broker đang offline, executor hết tài nguyên, hoặc chỉ còn một core consumer đang bận xử lý message khác, thời gian bắt đầu xử lý còn phụ thuộc các yếu tố đó.

### 4.3. Khi ứng dụng đang shutdown

Một số receive calls có thể đang block. T hữu hạn giúp worker định kỳ quay về loop để kiểm tra dừng; nhưng **không nên coi T là upper bound cứng cho toàn bộ shutdown**. Handler có thể chạy lâu, database có thể chặn, JMS transaction phải commit/rollback và provider có thể có hành vi interrupt/close riêng.

## 5. Core consumer, surplus consumer và “idle” trong DMLC

DMLC hỗ trợ:

- `concurrentConsumers`: số consumer **cơ sở** duy trì khi container đang chạy; mặc định `1`.
- `maxConcurrentConsumers`: mức tối đa cho phép container scale thêm consumers; mặc định `1`.
- `idleConsumerLimit`: giới hạn số consumers có thể đang idle khi quyết định có lập lịch invoker mới; mặc định `1`.
- `idleReceivesPerTaskLimit`: số lượt receive liên tiếp trả `null` trước khi coi task đang idle; với default/simple executor và surplus consumers, mặc định hiệu dụng `10` trong Spring 6.2.
- `idleTaskExecutionLimit`: số lần task được đánh dấu idle trước khi dừng **surplus task** trong cơ chế dynamic scaling; mặc định `1`.
- `maxMessagesPerTask`: tối đa số **lượt thử receive** một task xử lý trước khi nhường scheduling, tính cả lượt `null`; với standard executor mặc định `-1` (không giới hạn), với executor báo thích tác vụ ngắn có thể mặc định `10`.

Cần hiểu chính xác **phần tử nào được thu hẹp**:

```text
concurrentConsumers = 1
maxConcurrentConsumers = 4

Sau startup, khi queue nhàn rỗi:
    core: 1 invoker (duy trì)
    surplus: 0

Khi lượng message tăng và đủ điều kiện:
    core: 1
    surplus: 0..3   <- container có thể scale up

Khi hết tải:
    core: 1         <- vẫn duy trì
    surplus: 3..0   <- xem xét scale down theo idle limits
```

Nếu đặt `concurrentConsumers = maxConcurrentConsumers = 4`, cả bốn là **core consumers**. Không nên mong `idleReceivesPerTaskLimit=10` sẽ tự giảm về 1 vì không có khái niệm “surplus” trong cấu hình đó.

### 5.1. idleReceivesPerTaskLimit khác maxMessagesPerTask

Ví dụ một task đã xử lý 200 message và sau đó queue trống:

- `maxMessagesPerTask=500`: task có giới hạn 500 **lượt thử receive**, có thể gồm cả lượt không có message. Nó có thể cần thêm nhiều lần thử trước khi kết thúc theo giới hạn này.
- `idleReceivesPerTaskLimit=10`: sau 10 lần receive liên tiếp trả `null`, task được đánh dấu idle theo quy tắc tương ứng và có cơ hội được thu hồi nếu là surplus.
- `idleTaskExecutionLimit=1`: khi dynamic scheduling đánh giá task có một lần idle execution ở ngưỡng cần thiết, surplus task có thể dừng.

Đừng suy `maxMessagesPerTask=500` nghĩa luôn xử lý đúng 500 message thành công; Javadoc xác định đây là **lượt receive attempt**, không chỉ các message đã đến. Cũng đừng suy `idleTaskExecutionLimit=1` nghĩa “dừng sau đúng 1 giây”: giới hạn này đếm **idle executions**, không đếm thời gian.

### 5.2. Mô hình xấp xỉ thời gian thu hẹp consumer dư

Với default/simple executor, đặt:

- `T` = receive timeout (ms).
- `N` = số lượt receive liên tiếp trả null trước khi coi surplus invoker idle.

Nếu không có message, một chuỗi gồm N lượt chờ đầy đủ mất **xấp xỉ `N × T`** (chưa tính scheduling/provider/transaction overhead). Nếu N = 10:

| T | N | Ước lượng idle receives liên tiếp |
| ---: | ---: | ---: |
| 200 ms | 10 | ~2 giây |
| 1.000 ms | 10 | ~10 giây |
| 5.000 ms | 10 | ~50 giây |

Đây là **phép tính xấp xỉ từ tham số**, **không phải deadline chính xác cho scale-down**. Một message xen vào sẽ phá chuỗi idle. `maxMessagesPerTask`, task executor, activity của các invokers, `idleTaskExecutionLimit` và scheduling quyết định khi nào surplus thực sự bị hủy.

Spring 6.2 mô tả mặc định surplus task với simple executor có `idleReceivesPerTaskLimit=10` và `T=1000ms`, dẫn đến thu hẹp sau khoảng 10 giây nhận rỗng. **Core consumers không bị loại vì chỉ đặt idleReceivesPerTaskLimit** trong cấu hình thông thường; chính Javadoc nhấn mạnh khác biệt đó.

### 5.3. maxMessagesPerTask và TaskExecutor có thể đổi bức tranh

Với default executor, invoker có thể sống lâu và tái dùng thread liên tục. Với một `SchedulingTaskExecutor` thích tác vụ ngắn, Spring có thể chọn `maxMessagesPerTask` mặc định `10` để cho phép scheduling/scale linh hoạt hơn.

Điều đó có nghĩa:

- Task có thể được nhường/re-scheduled theo số lượt thử, **kể cả khi vừa xử lý message**.
- Giới hạn idle có thể tác động đến core consumers theo **cách tái lập lịch** khi kết hợp maxMessagesPerTask; không được áp dụng công thức “N × T rồi core biến mất” một cách giản lược.
- Một fixed thread pool quá nhỏ có thể làm invokers bị xếp hàng chờ executor, tạo latency và gây metric hoạt động không như mong đợi.

Khi đổi executor, không bê nguyên các quan sát mặc định của simple executor sang hệ mới. Nên đo với cấu hình cụ thể.

## 6. Các thông số đừng nhầm với receiveTimeout

| Thông số | Ảnh hưởng chính | Có cùng ý nghĩa T không? |
| --- | --- | --- |
| `receiveTimeout` | Lượt chờ nhận **một message** khi không có message khả dụng | Chính là T |
| `recoveryInterval` / `BackOff` | Khoảng cách/chiến lược **thử khôi phục** khi kết nối/consumer gặp lỗi | **Không**; DMLC mặc định recovery interval 5 giây |
| `idleReceivesPerTaskLimit` | Số lượt null liên tiếp khiến task thành idle | Không; đếm lượt |
| `idleTaskExecutionLimit` | Số lần idle execution trước khi surplus task dừng | Không; đếm executions |
| `maxMessagesPerTask` | Số lượt receive attempt mỗi task | Không; đếm lượt |
| `idleConsumerLimit` | Ngưỡng số consumer idle dùng khi quyết định mở thêm invoker | Không; đếm consumers |
| `concurrentConsumers / maxConcurrentConsumers` | Số concurrent consumers tối thiểu/tối đa | Không; giới hạn concurrency |
| `sessionTransacted` | JMS local transaction khi nhận/xử lý | Không; ảnh hưởng commit/redelivery |
| `transactionTimeout` | Giới hạn transaction do transaction manager quản lý | Không; cần lớn hơn receiveTimeout khi có transaction manager |
| `JmsTemplate.receiveTimeout` | Timeout của lệnh **nhận đồng bộ từ ứng dụng** | API khác, quy ước 0/-1 khác |
| Producer `timeToLive` | Thời gian sống của message trước expiration | Không |
| JMS message `deliveryDelay` | Trì hoãn thời điểm message đủ điều kiện giao | Không |

Đặc biệt, **mất broker** không phải “queue đang rỗng”. Nếu broker down, DMLC đi vào nhánh lỗi và recovery. Giảm receiveTimeout không thay `recoveryInterval` mặc định 5.000 ms; muốn điều khiển retry kết nối, dùng API recovery/backoff phù hợp.

## 7. Chọn giá trị T theo mục tiêu, không theo trực giác

### 7.1. Trường hợp queue hiếm khi có message

Với queue thường trống:

- Giữ `T=1000ms` là điểm khởi đầu an toàn.
- Duy trì core consumers tối thiểu (thường 1), không cố giảm về 0 chỉ vì không có message.
- Quan sát số lượt empty receive, connections, threads và broker metrics.
- Nếu muốn các surplus consumers rút nhanh hơn, cân nhắc idle limits và T vừa phải, thay vì luôn giảm T xuống mức vài mili giây.
- Nếu giảm T quá nhỏ, vòng receive rỗng có thể diễn ra nhiều lần hơn và tăng chi phí cấp transaction/receive hoặc broker/network overhead tùy provider.

### 7.2. Trường hợp cần gần realtime

Nếu SLA từ lúc message tới broker đến lúc handler bắt đầu là 100–300 ms, điều chỉnh `T=100ms` **không tự đáp ứng SLA đó**. Cần đo thực:

- Producer → broker latency và broker dispatch.
- Consumer có còn core thread nhận không?
- Broker prefetch/buffer, selector, queue backlog, priority và mạng.
- Thời gian chờ executor khi container muốn schedule consumer task.
- Xử lý message trước có chiếm hết consumers không?
- CPU, GC, hệ thống downstream và transaction overhead.

Nếu core consumer đang block trong `receive(1000)`, message có thể đến và được đánh thức ngay; thay T không phải biện pháp tối ưu p99 rõ ràng.

### 7.3. Trường hợp cần shutdown nhanh

Giữ timeout **hữu hạn**, có thời gian shutdown hợp lý và thiết kế xử lý in-flight. `T=5000ms` có thể khiến receive loop quay lại muộn hơn `T=500ms` trong một số điều kiện, nhưng tổng shutdown còn phụ thuộc provider interrupt, handler thời lượng dài, transaction, số thread và lifecycle processor.

Không đặt `T=0` để “ngủ cho tiết kiệm CPU” nếu hệ thống cần stop theo Kubernetes termination window. Spring Javadoc cảnh báo 0 (chờ vô hạn) thường cản clean shutdown.

### 7.4. Trường hợp muốn scale-down không dao động

Surplus consumers liên tục scale up/down khi workload theo đợt ngắn có thể tạo churn connection/session/consumer và tăng latency khi burst mới đến. Tăng `idleReceivesPerTaskLimit` hoặc T hợp lý giúp giữ surplus sống lâu hơn; đổi lại tiêu thụ tài nguyên lâu hơn lúc rỗi.

Nếu cần consumer tăng nhanh dưới load, `idleConsumerLimit` có thể ảnh hưởng mức độ chủ động scheduling thêm invokers. Không tăng nó vô hạn, vì thêm consumers có thể gây quá tải database và phá yêu cầu thứ tự theo aggregate.

## 8. Cấu hình Spring Boot: phân biệt listener receive timeout và template receive timeout

Spring Boot 3.4 có property dành cho **default JMS listener container factory**:

```yaml
spring:
  jms:
    listener:
      receive-timeout: 1s
      min-concurrency: 1
      max-concurrency: 4
```

`spring.jms.listener.receive-timeout` là cấu hình listener container; `spring.jms.template.receive-timeout` là cấu hình `JmsTemplate`. Không hoán đổi tên và ý nghĩa.

Với Boot 3.4:

- `spring.jms.listener.receive-timeout` mặc định `1s`.
- `0` biểu thị **chờ vô hạn** cho listener; `-1` biểu thị no-wait.
- `min-concurrency` và `max-concurrency` quy định vùng concurrency nếu dùng factory do Boot auto-configure.
- `max-messages-per-task` là property khác, **không** tự đặt `idleReceivesPerTaskLimit`.
- `receive-timeout` dùng kiểu `Duration`, nên viết `250ms`, `1s`, `5s` để dễ bảo trì.

**Chú ý:** nếu ứng dụng định nghĩa **custom `DefaultJmsListenerContainerFactory`** mà không dùng `DefaultJmsListenerContainerFactoryConfigurer` của Spring Boot, các property `spring.jms.listener.*` không tự áp dụng vào factory tùy biến đó. Cần gọi setters tường minh hoặc cho Boot configurer khởi tạo factory trước rồi override.

## 9. Ví dụ hoàn chỉnh Spring Boot 3.4/Java 17: quan sát consumer khi idle

Ta tạo một project học tập dùng ActiveMQ Artemis với hai profile:

- `listener`: bật `@JmsListener` và monitor số consumers.
- `publish`: gửi N message test qua `JmsTemplate`, không tạo listener ở process này.

Cần broker Artemis chạy với queue `orders.in` và credentials hợp lệ, cùng khả năng tạo hoặc tra cứu destination theo policy. Đây là **dự án Spring Boot đầy đủ file chính**, cần Gradle/JDK/dependencies và broker thực; không phải chương trình thuần Java chạy chỉ bằng `javac`.

### 9.1. Cấu trúc project

```text
jms-idle-demo/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/idle/IdleDemoApplication.java
  src/main/java/demo/idle/OrdersListener.java
  src/main/java/demo/idle/PublishRunner.java
  src/main/java/demo/idle/ConsumerMonitor.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'jms-idle-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.4.13 là một bản phát hành có thật để giữ ví dụ tái lập được, nhưng **nhánh 3.4.x đã hết hỗ trợ open source**. Với dự án production mới, chọn nhánh Spring Boot đang được hỗ trợ và kiểm tra thay đổi API/behavior tương ứng. Java 17+ là yêu cầu tối thiểu của ví dụ.

### 9.2. application.yml: cấu hình từ mức mặc định

File `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"
  jms:
    listener:
      receive-timeout: "${JMS_RECEIVE_TIMEOUT:1s}"
      min-concurrency: 1
      max-concurrency: 4

app:
  jms:
    queue: "${JMS_ORDERS_QUEUE:orders.in}"
    demo-count: "${JMS_DEMO_COUNT:12}"
```

Giải thích:

1. `mode: native` yêu cầu kết nối tới broker Artemis bên ngoài. Broker phải được provision riêng và có queue `orders.in` (hoặc cho phép auto-create theo policy).
2. `JMS_USER`/`JMS_PASSWORD` phải được cấp qua môi trường/secrets phù hợp, không commit mật khẩu thật.
3. Có thể thử `JMS_RECEIVE_TIMEOUT=200ms`, `1s` và `5s` **mỗi lần chạy một cấu hình** để so sánh số consumer idle và thời gian scale-down.
4. `min-concurrency: 1` giữ một core consumer; `max-concurrency: 4` cho phép tối đa ba surplus consumers khi đủ tải. Không hứa mọi burst nhỏ sẽ tạo đủ bốn consumers.
5. `demo-count` giới hạn số message mà profile publish tạo trong một lần khởi động.
6. Chỉ Boot factory mặc định được cấu hình qua `spring.jms.listener.*` trong demo này; **không định nghĩa custom factory** ở phần chạy chính.

### 9.3. Application bật annotation listener và monitor theo lịch

File `src/main/java/demo/idle/IdleDemoApplication.java`:

```java
package demo.idle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableJms
@EnableScheduling
public class IdleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdleDemoApplication.class, args);
    }
}
```

`@EnableJms` kích hoạt hạ tầng listener annotation, còn `@EnableScheduling` chỉ để component monitor định kỳ quan sát counts. Monitor **không** thay đổi thời gian chờ nhận JMS và không tự gửi message.

### 9.4. Listener xử lý message

File `src/main/java/demo/idle/OrdersListener.java`:

```java
package demo.idle;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("listener")
public class OrdersListener {

    @JmsListener(id = "ordersListener", destination = "${app.jms.queue}")
    public void onOrder(String body) {
        if (body == null || !body.startsWith("OrderCreated:")) {
            throw new IllegalArgumentException("Unexpected event body");
        }
        System.out.println("HANDLED " + body);
    }
}
```

Nội dung được converter mặc định chuyển từ `TextMessage` sang `String`. Handler chỉ kiểm tra rồi in ra console nên không thể dùng như business logic production. Với các consumer đồng thời, method trên bean singleton có thể được gọi từ nhiều thread; không lưu trạng thái mutable không đồng bộ vào field.

### 9.5. Producer riêng gửi một batch nhỏ

File `src/main/java/demo/idle/PublishRunner.java`:

```java
package demo.idle;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
@Profile("publish")
public class PublishRunner implements ApplicationRunner {

    private final JmsTemplate template;
    private final String destination;
    private final int count;

    public PublishRunner(
            JmsTemplate template,
            @Value("${app.jms.queue}") String destination,
            @Value("${app.jms.demo-count:12}") int count) {
        this.template = template;
        this.destination = destination;
        this.count = count;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (count < 1 || count > 1000) {
            throw new IllegalArgumentException(
                    "demo-count must be between 1 and 1000");
        }
        for (int i = 1; i <= count; i++) {
            template.convertAndSend(
                    destination, "OrderCreated:ORDER-" + i);
        }
        System.out.println("PUBLISHED " + count);
    }
}
```

Producer chạy trong profile `publish`, không kích hoạt bean listener (vì listener chỉ có profile `listener`). Việc ứng dụng producer in `PUBLISHED 12` chứng minh vòng gọi gửi của template hoàn tất không lỗi; nó **không** chứng minh listener đã nhận hay business đã commit.

### 9.6. Monitor tình trạng consumer

File `src/main/java/demo/idle/ConsumerMonitor.java`:

```java
package demo.idle;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("listener")
public class ConsumerMonitor {

    private final JmsListenerEndpointRegistry registry;

    public ConsumerMonitor(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void report() {
        MessageListenerContainer listener =
                registry.getListenerContainer("ordersListener");

        if (listener == null) {
            System.out.println("MONITOR endpoint not registered");
            return;
        }
        if (!(listener instanceof DefaultMessageListenerContainer dmlc)) {
            System.out.println("MONITOR different container type");
            return;
        }

        System.out.printf(
                "MONITOR running=%s scheduled=%d active=%d%n",
                dmlc.isRunning(),
                dmlc.getScheduledConsumerCount(),
                dmlc.getActiveConsumerCount());
    }
}
```

Các getter trên là snapshot của **container hiện tại**:

- `getScheduledConsumerCount()`: số invoker/consumer tasks đã lên lịch theo định nghĩa container; không đồng nghĩa số thread đang chạy business method.
- `getActiveConsumerCount()`: số invokers đang ở trạng thái active theo cơ chế nội bộ của DMLC; **không** nên diễn giải là số JMS message được xử lý trong giây hiện tại.
- `isRunning()`: lifecycle state của container; không tự chứng minh broker connection khỏe hoặc queue rỗng.

Khi queue rỗng lâu, `scheduled` thường trở về core count (ví dụ 1) nếu không có tải; `active` có thể nhỏ. Khi burst tới, surplus count có thể tăng và sau đó giảm. **Không cố định stdout** vì timing, broker provider và số lượng message thực tế làm con số thay đổi.

### 9.7. Cách chạy demo

Yêu cầu: JDK 17+, Gradle tương thích, broker Artemis riêng và queue `orders.in`. Sau khi tạo project, chạy bằng Gradle cài sẵn; nếu có Gradle wrapper, thay `gradle` bằng `./gradlew` (Windows là `gradlew.bat`).

Terminal thứ nhất chạy **listener**:

```bash
gradle bootRun --args='--spring.profiles.active=listener'
```

Để queue trống một lúc, quan sát các dòng `MONITOR` cách nhau khoảng 5 giây. Đây là nhịp lấy **metrics**, không phải `receiveTimeout`. Sau đó từ terminal thứ hai, trong **cùng project** và cùng broker/queue:

```bash
gradle bootRun --args='--spring.profiles.active=publish'
```

Producer sẽ cố gửi N message rồi in, ví dụ:

```text
PUBLISHED 12
```

Listener có thể in các dòng như:

```text
HANDLED OrderCreated:ORDER-1
HANDLED OrderCreated:ORDER-2
```

Đó chỉ là **hai dòng minh họa trong số N message**; log Spring Boot/Artemis, thứ tự các message và số consumer phụ thuộc thực tế. Không dùng thứ tự `ORDER-i` như một cam kết business FIFO khi chạy nhiều consumers. Nếu broker không hoạt động hoặc queue thiếu, chương trình có thể fail/recover thay vì in các dòng kỳ vọng.

Sau khi xử lý hết queue, chờ và quan sát `scheduled` quay lại gần min concurrency. Với burst 12 message và handler rất nhanh, container **có thể không scale lên 4**, điều đó không chứng minh cấu hình thất bại. Muốn khảo sát scale-down thực sự, tạo một workload test có xử lý chậm có kiểm soát hoặc gửi nhiều message hơn, theo dõi nhiều snapshots và broker metrics.

### 9.8. Thử biến nhận timeout

Không sửa Java. Thử các cấu hình, lần lượt restart listener sau mỗi lần đổi:

```bash
# Với shell Bash/Linux/macOS:
JMS_RECEIVE_TIMEOUT=200ms gradle bootRun --args='--spring.profiles.active=listener'

JMS_RECEIVE_TIMEOUT=1s gradle bootRun --args='--spring.profiles.active=listener'

JMS_RECEIVE_TIMEOUT=5s gradle bootRun --args='--spring.profiles.active=listener'
```

Không chạy ba listener cùng lúc trên một queue khi muốn benchmark từng cấu hình, vì chúng trở thành competing consumers. Trên Windows/PowerShell, đặt `$env:JMS_RECEIVE_TIMEOUT="200ms"` trước khi gọi `gradlew.bat`.

Ghi lại 4 nhóm quan sát:

1. Latency message có sẵn trên broker → handler bắt đầu (đo bằng clock/tracing phù hợp).
2. Các mốc `scheduled/active` tăng/giảm khi burst xuất hiện rồi hết.
3. Chi phí tài nguyên khi queue rỗng (CPU, thread, connections).
4. Thời gian ứng dụng ngừng nhận và kết thúc shutdown, bao gồm business in-flight.

**Kết luận chỉ sau khi đo:** T ngắn có thể đẩy nhanh phát hiện idle hoặc giải phóng invoker dư, nhưng không mặc định làm message dispatch nhanh hơn.

## 10. Nếu cần điều chỉnh idleReceivesPerTaskLimit: cấu hình nâng cao

`DefaultJmsListenerContainerFactory` trực tiếp có setter `setReceiveTimeout(Long)` và `setMaxMessagesPerTask(Integer)`, nhưng **không có** setter public `setIdleReceivesPerTaskLimit(...)` trên chính factory trong Spring 6.2. Setter đó nằm ở **`DefaultMessageListenerContainer`**. Có thể dùng container bean trực tiếp hoặc subclass factory để tùy biến container lúc tạo.

Ví dụ **một factory tùy biến thay thế** cho factory mặc định:

File `IdleAwareFactory.java` (đặt trong package `demo.idle` nếu dùng để mở rộng project):

```java
package demo.idle;

import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

public class IdleAwareFactory
        extends DefaultJmsListenerContainerFactory {

    @Override
    protected void initializeContainer(
            DefaultMessageListenerContainer container) {
        super.initializeContainer(container);
        container.setIdleReceivesPerTaskLimit(5);
        container.setIdleTaskExecutionLimit(1);
    }
}
```

File `IdleAwareConfiguration.java`:

```java
package demo.idle;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class IdleAwareConfiguration {

    @Bean("idleAwareJmsFactory")
    public IdleAwareFactory idleAwareJmsFactory(
            DefaultJmsListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory) {

        IdleAwareFactory factory = new IdleAwareFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setReceiveTimeout(1000L);
        factory.setConcurrency("1-4");
        return factory;
    }
}
```

Để **thực sự sử dụng factory này**, sửa annotation trong `OrdersListener` thành:

```java
@JmsListener(
        id = "ordersListener",
        destination = "${app.jms.queue}",
        containerFactory = "idleAwareJmsFactory")
public void onOrder(String body) {
    // Giữ nguyên body của handler ở ví dụ chính.
}
```

Đoạn cuối là **minh họa thay đổi annotation**, không được tạo một method `onOrder` thứ hai trong cùng bean. Khi triển khai thật, giữ một method hiện có và chỉ thêm `containerFactory`.

Lưu ý:

- Sử dụng `DefaultJmsListenerContainerFactoryConfigurer` của Boot để bảo toàn mặc định phù hợp của listener factory (transaction, unwrapped connection factory, converter...) trước khi tùy biến.
- `setIdleReceivesPerTaskLimit(5)` giúp đánh dấu surplus consumer idle sớm hơn trong một số scenario; nó **không tự cắt core consumers**.
- `setIdleTaskExecutionLimit(1)` là ngưỡng theo **số idle task executions**, không phải 1 giây.
- Với `maxMessagesPerTask` và executor khác default, hiệu ứng khác; đo thay vì chỉ nhân số.
- Không cấu hình đồng thời cả factory mới và factory cũ lên cùng queue ở các endpoints khác nhau rồi kỳ vọng mỗi message được nhân bản.
- Khi muốn sửa các thuộc tính container ở runtime, xem hỗ trợ cụ thể của từng setter và cơ chế quản lý thay đổi; cách dễ kiểm soát nhất trong demo là cấu hình lúc tạo container, restart có kế hoạch, không thay đổi ngầm trên production load.

## 11. Java 17 độc lập: tính *xấp xỉ* cửa sổ nhận rỗng

Để hiểu `N × T` mà không cần broker, tạo file `IdleReceiveEstimate.java`:

```java
public class IdleReceiveEstimate {

    static long estimateMillis(long receiveTimeoutMs, int emptyReceives) {
        if (receiveTimeoutMs <= 0 || emptyReceives <= 0) {
            throw new IllegalArgumentException(
                    "Use positive timeout and emptyReceives");
        }
        return Math.multiplyExact(receiveTimeoutMs, emptyReceives);
    }

    public static void main(String[] args) {
        int count = 10;
        long[] timeouts = {200, 1_000, 5_000};

        for (long timeout : timeouts) {
            long estimated = estimateMillis(timeout, count);
            System.out.printf(
                    "T=%dms N=%d approximate=%dms%n",
                    timeout, count, estimated);
        }
    }
}
```

Chạy bằng Java 17+:

```bash
javac IdleReceiveEstimate.java
java IdleReceiveEstimate
```

**Stdout chính xác**:

```text
T=200ms N=10 approximate=2000ms
T=1000ms N=10 approximate=10000ms
T=5000ms N=10 approximate=50000ms
```

Đây là **bài toán số học độc lập** tính N lần timeout liên tiếp, không mô phỏng JMS container thật. Nó không bao gồm lịch thread, nhận message xen vào, maxMessagesPerTask, rollback, scaling policy hay broker response. Đừng sử dụng kết quả làm SLA scale-down hoặc shutdown.

## 12. Transaction, ACK và lỗi: nhận rỗng không phải xử lý thất bại

DMLC có thể chạy listener với local JMS transaction hoặc external transaction manager. Nếu listener nhận được message thật rồi ném exception, kết quả phụ thuộc cách cấu hình ACK/transaction và chính sách broker.

Nhưng **lượt receive trả `null`** là chuyện khác:

- Không có handler business được gọi chỉ vì một receive trống.
- Container vẫn phải quản lý session và có thể cần hoàn thành transaction scope của lần receive nếu cấu hình transaction.
- Không ghi nhận một receive trống thành lỗi nghiệp vụ hoặc redelivery.
- Đối với transaction manager, `receiveTimeout` nên **ngắn hơn transaction timeout** để vòng chờ không vượt thời gian transaction.
- Một message bị expired, selector không khớp hoặc chưa được broker dispatch cũng có thể dẫn đến receive trống từ góc nhìn consumer; điều đó không chứng minh toàn broker không có dữ liệu.

### 12.1. receiveTimeout không phải timeout xử lý nghiệp vụ

Nếu `receiveTimeout=1000ms` nhưng handler chạy 30 giây, Spring **không** tự chấm dứt handler sau 1 giây. Timeout chỉ áp dụng khi đang gọi `receive` để đợi message.

Cần thiết kế **timeout của database/HTTP**, circuit breaker hoặc cancel policy của handler riêng. Thời gian business processing còn ảnh hưởng khi nào consumer trở lại receive loop, nên cũng ảnh hưởng latency của message tiếp theo nếu không có consumer rảnh.

### 12.2. receiveTimeout không phải message expiration

Producer có thể đặt `timeToLive` hoặc delivery delay, broker có thể giữ message theo selector/priority. Những cơ chế đó quyết định message có đủ điều kiện giao hay không. Timeout receive ở consumer **không thay đổi TTL** hay xóa message khỏi queue khi chờ hết hạn.

### 12.3. receiveTimeout không phải recovery interval

DMLC có `setRecoveryInterval(long)` hoặc `setBackOff(BackOff)`. Mặc định recovery interval 5.000ms trong Spring 6.2 là khoảng thử lại khi **broker/consumer gặp sự cố**. Nó không phải thời gian chờ một lần receive ở queue trống.

```text
Queue trống:
  receive(timeout) -> null -> idle bookkeeping -> receive tiếp

Broker mất kết nối:
  receive hoặc connection gặp lỗi
       -> DMLC failure/recovery path
       -> đợi theo recoveryInterval / BackOff policy
       -> thử tạo/khôi phục tài nguyên và nhận tiếp
```

Nếu broker down 15 giây, việc giảm `receiveTimeout` từ 1 giây xuống 100ms không đảm bảo ứng dụng sẽ kết nối lại trong 100ms; phải quan sát recovery policy, broker và network thực tế.

## 13. Shutdown và responsiveness: không lấy timeout làm bảo đảm tuyệt đối

Trong shutdown, DMLC cần ngừng scheduling consumer tasks, xử lý in-flight (theo policy) rồi giải phóng connection/session. Những thread đang block ở receive có thể được giải phóng khi nhận message, timeout, stop/close hoặc lỗi provider. Do đó:

- `T=0` chờ vô hạn là lựa chọn rủi ro; Spring Javadoc cảnh báo container khó clean shutdown khi receive không bao giờ trả về.
- `T>0` là cấu hình an toàn hơn để các task có cơ hội quay lại loop.
- Dù `T=200ms`, một listener đang xử lý nghiệp vụ 20 giây vẫn có thể khiến shutdown mất nhiều thời gian.
- Broker/provider có thể chặn ở bước đóng session, transaction/connection; timeout receive không ràng buộc mọi bước đó.
- Stop một container chỉ tác động đến consumers thuộc container ấy, không ngừng các JVM khác cùng queue.

Ví dụ cấu hình Spring Boot để lifecycle processor chờ một khoảng phù hợp trên mỗi shutdown phase:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

Property này **không** đặt receive timeout; nó điều khiển khoảng chờ cho **shutdown phase** của Spring lifecycle processor. Nếu handler chạy lâu hơn budget, cần có policy rõ ràng cho stop và redelivery, thay vì giả định shutdown luôn thành công sạch sẽ.

## 14. Quan sát hoạt động và thiết kế benchmark

### 14.1. Metrics nên đo

| Metric đề xuất | Ý nghĩa | Vì sao cần |
| --- | --- | --- |
| `listener_running` | Lifecycle state của container | Biết listener có được bật không |
| `scheduled_consumers` | DMLC `getScheduledConsumerCount()` | Quan sát thay đổi task count |
| `active_consumers` | DMLC `getActiveConsumerCount()` | Quan sát hoạt động theo định nghĩa container |
| `queue_depth` | Message pending ở broker | Biết backlog |
| `oldest_message_age` | Tuổi message cũ nhất | Biết queue có bị kẹt |
| `message_delivery_latency` | Thời gian broker message available → handler bắt đầu | Đo responsiveness tiếp nhận |
| `handler_latency` | Thời gian xử lý nghiệp vụ | Đo bottleneck ngoài receive |
| `redelivery_total` | Số lượt nhận lại sau lỗi | Đo transaction/retry tác động |
| `recoveries_total` | Số lần phục hồi connection | Phân biệt broker failure với queue idle |
| `shutdown_duration` | Thời gian stop/drain resource | Kiểm chứng hiệu quả timeout |

Các tên metrics là **gợi ý của ứng dụng**, không phải tất cả có sẵn trong Boot Actuator. Có thể dùng Micrometer/Observation cùng broker metrics và tracing. Snapshot `scheduled/active` từ demo là dữ liệu hỗ trợ, không thay thế broker consumer count và in-flight queue metrics.

### 14.2. Đo latency thế nào cho đúng?

Nên ghi timestamp gần thời điểm **broker xác nhận message khả dụng** và timestamp khi **handler bắt đầu**, hoặc dùng tracing/benchmark trong cùng môi trường đồng hồ đồng bộ. Nếu producer và consumer ở hai máy, sai lệch clock có thể làm latency âm hoặc sai lớn; cần đồng bộ thời gian và hiểu điểm đo.

Đừng đo “lần monitor sau bao lâu thấy tăng active consumers” rồi gọi đó là message latency: monitor chạy mỗi 5 giây có **sampling lag** hoàn toàn khác `receiveTimeout`. Đừng suy ra p99 từ vài lần gửi vào queue rỗng.

### 14.3. Bộ kịch bản benchmark thực hành

1. **Queue rỗng lâu:** giữ listener profile chạy, đo CPU/thread/connection và scheduled consumer count ở các T.
2. **Một message sau im lặng:** gửi message khi core consumer đang chờ, đo arrival-to-handler latency. Kiểm chứng nó thường có thể nhỏ hơn T.
3. **Burst vừa đủ gây scale-up:** gửi nhiều message với handler chậm có kiểm soát, xem scheduled count tăng tới đâu.
4. **Hết burst:** quan sát surplus giảm về core count; so sánh T và idle limits.
5. **Broker down/up:** kiểm tra recovery interval/backoff, không nhầm với timeout nhận rỗng.
6. **Graceful shutdown lúc queue trống:** đo stop time với T ngắn/dài.
7. **Shutdown lúc handler đang chạy:** kiểm tra in-flight/transaction/redelivery, không chỉ stop flag.
8. **Đổi executor/maxMessagesPerTask:** xác minh mô hình scale-down cũ còn đúng không.
9. **Nhiều replica:** xem tổng consumer và throughput; một container có min=1 không có nghĩa cả cluster chỉ có một consumer.

Dùng nhiều lần đo, tách warm-up khỏi measurement, cố định broker, payload, queue type, concurrency và resource budget. Nếu đổi cả T, max concurrency và handler latency cùng lúc, rất khó quy sự khác biệt cho receiveTimeout.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| `receiveTimeout=1000` làm mọi message chờ ít nhất 1 giây | Blocking receive có thể trả ngay khi message tới | T là thời gian chờ tối đa của lần receive không có message |
| Giảm T 10 lần thì business SLA nhanh gấp 10 | Business latency có nhiều nguồn | Đo broker dispatch, thread, backlog và handler |
| `T=0` nghĩa “không chờ” như `JmsTemplate` | DMLC và template có quy ước khác | DMLC 0 là indefinite, -1 no-wait |
| `T=-1` luôn tiết kiệm tài nguyên | No-wait có thể tạo nhiều receive iterations | Chỉ dùng khi có lý do và benchmark |
| Queue rỗng nghĩa listener container không chạy | Core consumer vẫn thường chạy nền | Kiểm tra registry, scheduled consumers và broker |
| `idleReceivesPerTaskLimit=10` giảm tất cả consumers về 0 | Core consumers được giữ lại | Chỉ surplus consumers được thu hẹp mặc định |
| `idleTaskExecutionLimit=1` nghĩa sau 1 giây sẽ stop | Nó đếm idle executions | Xét cùng T, maxMessagesPerTask và executor |
| `maxMessagesPerTask=10` là “10 message đã xử lý” | Nó giới hạn receive attempts, kể cả null | Đọc đúng Javadoc |
| `recoveryInterval=5s` nghĩa poll queue trống mỗi 5 giây | Recovery là nhánh lỗi broker | Không lẫn recovery với receive timeout |
| `spring.jms.template.receive-timeout` điều khiển `@JmsListener` | Cấu hình template khác listener factory | Dùng `spring.jms.listener.receive-timeout` |
| T nhỏ đảm bảo shutdown trong T | Handler/provider/transaction có thể chờ lâu hơn | Test stop/drain và cấu hình shutdown phase |
| `scheduledConsumerCount` bằng số business methods đang chạy | Getter là chỉ số invoker scheduling | Kết hợp broker metrics và handler timers |
| Số consumer cao luôn tốt | Có thể làm overload DB, đảo thứ tự xử lý | Tune concurrency và transaction/idempotency |
| Chỉnh T giúp xử lý lỗi converter/poison message | Lỗi nằm sau receive | Thiết kế redelivery/DLQ và converter/validation |

## 16. Checklist áp dụng production

Khi cần tuning DMLC, đi theo thứ tự:

1. **Xác nhận implementation:** ứng dụng dùng `DefaultMessageListenerContainer` hay container khác? Property T ở đâu?
2. **Xác nhận cấu hình thực:** Boot factory mặc định, custom factory hay XML/container bean? Có configurer không?
3. **Giữ T dương hữu hạn:** bắt đầu bằng `1s` trừ khi đo được lý do phải đổi.
4. **Xác nhận transaction:** nếu có external transaction manager, T phải nhỏ hơn transaction timeout.
5. **Nhìn min/max concurrency:** nếu max = min thì không kỳ vọng surplus scale-down; nếu max > min thì xem idle limits.
6. **Đọc đúng executor:** standard/simple hay scheduling short-lived? `maxMessagesPerTask` có đang override không?
7. **Đo idle và burst riêng:** empty receive detection/scale-down khác arrival-to-handler latency.
8. **Phân biệt lỗi kết nối:** recovery interval/backoff không phải receive timeout.
9. **Kiểm tra graceful stop:** cả queue rỗng và handler đang xử lý, không suy thời gian shutdown chỉ từ T.
10. **Đặt giới hạn tài nguyên:** consumer threads, sessions, connections, downstream DB và delivery ordering.
11. **Vận hành có quan sát:** queue age, active/scheduled consumers, redelivery, DLQ, CPU và metrics p95/p99.
12. **Đảm bảo idempotency:** JMS transaction/ack và business database commit không mặc nhiên exactly-once.

**Ghi nhớ:** `receiveTimeout` của DefaultMessageListenerContainer **quy định thời gian chờ một lần receive khi không có message**, mặc định **1 giây** trong Spring Framework 6.2. Nó giúp vòng nhận có các thời điểm kiểm tra idle và lifecycle; nó **không phải timer trì hoãn mọi message**. Độ phản hồi khi nhàn rỗi phụ thuộc đồng thời vào core/surplus consumers, các ngưỡng idle, executor, tính sẵn sàng broker, transaction và khả năng xử lý downstream. Tuning đúng phải dựa vào **benchmark có kịch bản rỗng → có tải → hết tải**, không dựa vào một con số T đứng riêng.

### Tài liệu tham khảo

- Spring Framework 6.2 — `AbstractPollingMessageListenerContainer`: mặc định 1.000 ms, ngữ nghĩa 0/-1 và transaction timeout: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultMessageListenerContainer`: min/max concurrent consumers, idle limits, maxMessagesPerTask, recovery và scheduled/active counts: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `DefaultJmsListenerContainerFactory`: setReceiveTimeout và cấu hình container cho `@JmsListener`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — Annotation-driven listener endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot 3.4 — Common Application Properties, `spring.jms.listener.receive-timeout` và `spring.jms.template.receive-timeout`: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- Spring Boot 3.4 — JMS + Artemis, factory configurer và connection factory unwrapping: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot 3.4.13 — thông báo phát hành và kết thúc OSS support của 3.4.x: https://spring.io/blog/2025/12/18/spring-boot-3-4-13-available-now
