# Khi nên dùng orchestration thay vì event chain trong Spring Framework

## 1. Vấn đề cần giải quyết

Trong một hệ thống sử dụng **Spring Framework Application Events**, ta có thể nối các bước xử lý bằng **event chain**: một listener nhận event A, sau đó publish hoặc trả về event B; listener nhận B lại tạo event C. Cách này có thể ngắn gọn, ghép nối lỏng và phù hợp với nhiều phản ứng độc lập.

Tuy nhiên, khi quy trình có **thứ tự bắt buộc**, **kết quả tổng thể cần xác nhận**, **timeout**, **retry**, **bù trừ** hoặc **trạng thái phải phục hồi sau khi ứng dụng khởi động lại**, việc phân tán logic ra nhiều listener có thể làm mất đi nơi chịu trách nhiệm cho toàn bộ workflow. Khi đó, **orchestration** thường là lựa chọn rõ ràng và an toàn hơn.

**Orchestration** nghĩa là một **workflow coordinator** (application service, process manager, saga orchestrator hoặc durable workflow engine) sở hữu trạng thái và quyết định **bước tiếp theo phải làm gì**, **điều kiện hoàn tất**, **lỗi phải xử lý thế nào**. Nó có thể dùng cả **lời gọi trực tiếp**, **commands**, **events** và **message broker**. Vì thế orchestration **không đối lập với event-driven architecture**; điểm khác biệt là **ai sở hữu quyền điều phối và kết quả nghiệp vụ**.

So sánh nhanh:

~~~text
EVENT CHAIN / CHOREOGRAPHY
OrderSubmitted
      |
      v
PaymentListener -> PaymentCaptured
                       |
                       v
               StockListener -> StockReserved
                                    |
                                    v
                             ShippingListener
(Mỗi listener chỉ biết một phần của hành trình)
~~~

~~~text
ORCHESTRATION
CheckoutWorkflow (sở hữu tiến trình)
      |
      +-- reserveStock()
      |       |
      +-- chargePayment()
      |       |
      +-- scheduleShipment()
      |       |
      +-- COMPLETED -> publish OrderFulfilled
      |
      +-- lỗi? retry / compensate / manual review
(Thứ tự, điều kiện và kết quả được mô tả tại một nơi)
~~~

Ví dụ checkout chỉ được coi là thành công khi giữ hàng, thanh toán và tạo vận đơn đều thành công. Nếu thanh toán thành công nhưng bước vận chuyển lỗi, phải có người quyết định **refund**, **retry** hay **chuyển trạng thái chờ hỗ trợ**. Đây là nhu cầu orchestration điển hình.

## 2. Phân biệt event chain, choreography, orchestration và saga

### 2.1. Domain event

Một **event** diễn đạt một sự thật đã xảy ra, chẳng hạn **OrderConfirmed**, **PaymentCaptured**, **ShipmentScheduled**. Event có thể có nhiều subscriber. Một subscriber không mặc nhiên sở hữu quyền điều khiển các subscriber khác.

Một **command** như **ReserveStock** hay **ChargePayment** lại yêu cầu hành động cần thực hiện. Sự phân biệt này quan trọng trong workflow: orchestrator thường gửi command rồi chờ kết quả, thay vì giả định rằng phát event đồng nghĩa với việc bước tiếp theo chắc chắn đã hoàn tất.

### 2.2. Event chain

Một **event chain** gồm các sự kiện nối tiếp: A kích hoạt listener, listener tạo B, B kích hoạt listener khác. Trong Spring, method **@EventListener** đồng bộ có thể **return một object** để Spring publish object đó thành event mới; **return Collection/array** thì từng phần tử được publish riêng; **return null/void** không tạo sự kiện mới từ kết quả.

Ví dụ minh họa:

~~~java
@EventListener
public PaymentRequested onOrderSubmitted(OrderSubmitted event) {
    return new PaymentRequested(event.orderId());
}
~~~

Đây chỉ là **snippet minh họa**; cần các event types, imports và Spring-managed bean. Return-value chaining **không được hỗ trợ với asynchronous @EventListener**; khi listener chạy async, muốn phát tiếp cần gọi **ApplicationEventPublisher.publishEvent(...)** tường minh.

Event chain thuần trong process **không tự cung cấp** persistent state, giao hàng bền vững, retry, compensation hoặc transactional atomicity.

### 2.3. Choreography

**Choreography** là kiểu phối hợp các thành phần thông qua event/message mà không có một coordinator trung tâm quyết định từng bước. Mỗi participant tự biết khi nào phản ứng. Choreography có thể mở rộng tốt khi các thành phần độc lập, nhưng workflow trải qua nhiều service dễ thiếu một cái nhìn tổng thể nếu không thiết kế correlation, trạng thái và observability.

### 2.4. Orchestration

**Orchestration** có một thành phần nắm **workflow state** và **transition rules**. Nó quyết định **gửi command nào**, **chờ outcome gì**, **timeout khi nào**, **bù trừ bước nào**, và **khi nào trả kết quả thành công/thất bại/đang xử lý**.

Orchestration có thể dùng Spring application service đồng bộ cho quy trình nhỏ hoặc saga/workflow engine bền vững cho quy trình kéo dài qua nhiều dịch vụ. Không bắt buộc tất cả lệnh phải là HTTP đồng bộ; orchestrator vẫn có thể tiêu thụ và phát events qua broker.

### 2.5. Saga

**Saga** là cách phối hợp một chuỗi **local transactions** ở nhiều thành phần, với các **compensating actions** khi cần khắc phục. Saga có thể được triển khai theo orchestration hoặc choreography. Compensation **không phải rollback ACID toàn cục**: refund là giao dịch bù lại charge đã xảy ra, không làm giao dịch gốc biến mất khỏi lịch sử.

## 3. Dấu hiệu nên chuyển từ event chain sang orchestration

### 3.1. Bắt buộc theo thứ tự và có điều kiện tiên quyết

Nếu **không giữ được stock thì không được charge**, hoặc **chưa charge thành công thì không được tạo shipment**, thứ tự không chỉ là ưu tiên gọi listener mà là **business invariant của use case**. Khi có nhiều điều kiện rẽ nhánh và kết quả từ các bên, orchestrator trình bày các điều kiện này trực tiếp.

**@Order** trong Spring chỉ giúp ưu tiên dispatch giữa các listener trong ngữ cảnh phù hợp; nó không tạo một workflow engine, không lưu state và không bảo đảm thứ tự hoàn tất của xử lý bất đồng bộ.

### 3.2. Một điểm chịu trách nhiệm cho kết quả

API checkout hoặc job scheduling cần trả lời rõ:

- **COMPLETED**: toàn bộ bước bắt buộc đã xác nhận thành công.
- **REJECTED/FAILED**: use case bị từ chối hoặc lỗi xác định.
- **PENDING**: đã chấp nhận yêu cầu nhưng còn các bước đang xử lý.
- **COMPENSATING**: một bước lỗi và hệ thống đang bù trừ.
- **MANUAL_REVIEW**: không thể tự quyết định hoặc khôi phục.

Chỉ publish **OrderSubmitted** rồi trả **200 OK** không có nghĩa toàn bộ chain đã thành công, đặc biệt khi các bước chạy async. Với workflow dài, API có thể trả **202 Accepted** và **workflowId**; client dùng status endpoint để theo dõi. 202 chỉ xác nhận yêu cầu đã được chấp nhận theo hợp đồng, không xác nhận kết quả cuối cùng.

### 3.3. Có lỗi, retry và timeout cần điều phối

Ví dụ payment provider timeout sau khi gửi yêu cầu trừ tiền. Ta chưa biết tiền đã bị trừ hay chưa:

~~~text
Orchestrator -> PaymentProvider: charge(orderId, attemptId)
                       |
                       x timeout
                       |
          Không biết provider đã charge hay chưa
~~~

Nếu listener cứ retry với request ID mới, khách có thể bị trừ tiền hai lần. Orchestrator cần **idempotency key ổn định**, khả năng **query trạng thái của attempt**, giới hạn retry/backoff và nhánh xử lý **UNKNOWN**. Một chain các callback không tự giải quyết tình huống này.

### 3.4. Có nhiều bước bù trừ

Sau khi đã giữ stock và charge, nếu shipping bị từ chối, hệ thống cần xác định nên **refund payment** rồi **release stock**. Nếu refund lỗi, cần lưu trạng thái **COMPENSATING** để retry, không được ghi “đã rollback hoàn toàn”.

Orchestrator nắm những bước nào đã được xác nhận, từ đó quyết định bù trừ theo thứ tự phù hợp. Không nên để một listener ngẫu nhiên suy đoán rằng tất cả các bước trước đó đã thành công.

### 3.5. Cần resume, audit và hỗ trợ vận hành

Một workflow có thể chạy nhiều phút, nhiều ngày hoặc qua nhiều deploy. Nếu process chết, cần lưu **workflowId**, **currentStep**, **attempts**, **deadline**, **lastError**, **step outcomes** và các hành động cần thực hiện tiếp.

Durable orchestrator hoặc workflow engine có thể lưu trạng thái và phục hồi; event chain trong bộ nhớ của một ApplicationContext không tự làm được điều đó. Choreography cũng có thể bền vững nếu từng service có state, outbox/inbox và monitoring tốt; orchestration thường giúp xác định ownership dễ hơn.

## 4. Khi nào event chain vẫn là giải pháp tốt hơn?

Không biến mọi phản ứng thành một bước orchestration. **Event chain/choreography** phù hợp khi các handler **độc lập về kết quả nghiệp vụ**:

- Đơn hàng đã được xác nhận; analytics cập nhật báo cáo.
- Search index nhận event và cập nhật projection.
- Cache invalidation phản ứng với thay đổi trạng thái.
- Telemetry/audit best-effort nhận event sau khi nghiệp vụ chính hoàn tất.
- Nhiều bounded contexts đăng ký một integration event mà không cần coordinator ra quyết định thay từng service.
- Một phép biến đổi sự kiện ngắn, không có side effect quan trọng và không cần resume theo workflow.

Điều cốt lõi: nếu **analytics lỗi nhưng đơn hàng vẫn hợp lệ**, analytics không nên quyết định checkout có thành công hay không. Với nhiều subscribers độc lập, event-driven fan-out có thể giảm coupling hơn một orchestrator gọi lần lượt từng subscriber.

Vẫn phải có **error policy** phù hợp: với Spring **SimpleApplicationEventMulticaster** đồng bộ mặc định, exception từ observer có thể truyền ngược về publisher. Nếu observer không critical, có thể dùng durable queue/outbox, xử lý lỗi tách biệt hoặc cơ chế không blocking có giới hạn. **@Async** một mình không biến in-memory callback thành durable message.

## 5. Bảng quyết định

| Tiêu chí | Orchestration thường phù hợp | Event chain/choreography thường phù hợp |
| --- | --- | --- |
| B có bắt buộc đợi A thành công? | Có và nhiều điều kiện | Không có thứ tự nghiệp vụ cứng |
| Một lỗi có quyết định toàn bộ kết quả? | Có | Subscriber độc lập |
| Phải bù trừ side effect? | Có | Không hoặc mỗi subscriber có trách nhiệm riêng |
| Workflow kéo dài qua nhiều service? | Durable saga/workflow dễ quản trị | Choreography vẫn khả thi nếu trạng thái phân tán được thiết kế đầy đủ |
| Cần timeout/backoff/manual review? | Có | Không hoặc chỉ ở từng handler |
| Cần status endpoint theo workflowId? | Rất phù hợp | Phải ghép trạng thái từ nhiều nguồn |
| Event đã xảy ra cần nhiều observer? | Publish event sau bước chính | Phù hợp cho fan-out |
| Cần mở rộng tính năng không sửa core workflow? | Dùng event ở rìa | Điểm mạnh của loose coupling |
| Phải phục hồi sau restart? | Persistent workflow + durable messaging | Event store/broker + consumer state; chain in-memory không đủ |
| Cần một kết quả đồng bộ cho caller? | Service/orchestrator trả rõ ràng | Publication đơn lẻ không trả kết quả của toàn chain |

**Heuristic:** Nếu để trả lời “order này đã thành công chưa?” cần đọc log từ năm listeners và đoán thứ tự các event, hãy cân nhắc **một workflow owner**. Nếu thêm một listener báo cáo mà không ảnh hưởng tính đúng đắn của use case, **giữ observer độc lập**.

## 6. Phản ví dụ: workflow thanh toán bị chia rải qua listeners

~~~java
@EventListener
public PaymentRequested onOrderSubmitted(OrderSubmitted event) {
    return new PaymentRequested(event.orderId());
}

@EventListener
public ShippingRequested onPaymentCaptured(PaymentCaptured event) {
    return new ShippingRequested(event.orderId());
}
~~~

Đây là **các snippet**, không phải chương trình đầy đủ. Cách viết không sai về cú pháp event chaining, nhưng vẫn bỏ ngỏ:

1. Ai xác định PaymentCaptured thuộc đúng payment attempt, đúng amount và đúng order?
2. Ai xác minh shipping đã được lên lịch thành công?
3. Khi mất event hoặc broker downtime, ai khôi phục?
4. Nếu payment đã thành công còn shipping thất bại, ai refund?
5. Nếu nhận event trùng hai lần, ai chống duplicate charge?
6. Sau 30 giây không có event, ai timeout hay chuyển manual review?
7. Khi API hỏi trạng thái cuối, hệ thống đọc ở đâu?

Có thể giải quyết bằng choreography có durable state ở từng participant và correlation tốt. Nhưng càng nhiều rule chuyển trạng thái và bù trừ, một orchestrator lưu workflow state thường dễ kiểm chứng hơn, đặc biệt khi hệ thống có chính sách vận hành thống nhất.

## 7. Ví dụ chạy được Java 17+: orchestration cho bước bắt buộc, Spring event cho observer

Ví dụ sau sử dụng **Spring Framework 6.2.9**, **JDK 17+** và **Gradle 8.x**, không cần Spring Boot, database hoặc broker. **CheckoutWorkflow** điều phối giữ hàng, thu tiền, lên lịch vận chuyển. Nếu shipping lỗi, code gọi **refund** và **release**. Khi thành công, workflow publish **OrderFulfilled** để listener quan sát.

Đây là **demo in-memory**, không có persistence hoặc remote services. Các thao tác compensation được mô phỏng bằng logging, không thể thay thế saga thực tế.

Cấu trúc:

~~~text
checkout-orchestration-demo/
  build.gradle
  src/main/java/demo/CheckoutOrchestrationDemo.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.CheckoutOrchestrationDemo'
}
~~~

**src/main/java/demo/CheckoutOrchestrationDemo.java**:

~~~java
package demo;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class CheckoutOrchestrationDemo {

    public record OrderFulfilled(String id) {}

    public static final class Stock {
        public void reserve(String id) {
            System.out.println("stock: reserve " + id);
        }

        public void release(String id) {
            System.out.println("stock: release " + id);
        }
    }

    public static final class Payment {
        public void charge(String id) {
            System.out.println("payment: charge " + id);
        }

        public void refund(String id) {
            System.out.println("payment: refund " + id);
        }
    }

    public static final class Shipping {
        public void schedule(String id) {
            System.out.println("shipping: schedule " + id);
            if (id.equals("FAIL")) {
                throw new IllegalStateException("shipping unavailable");
            }
        }
    }

    public static final class CompletionNotifier {
        private final ApplicationEventPublisher publisher;

        public CompletionNotifier(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void notifyCompleted(String id) {
            publisher.publishEvent(new OrderFulfilled(id));
        }
    }

    public static final class CheckoutWorkflow {
        private final Stock stock;
        private final Payment payment;
        private final Shipping shipping;
        private final CompletionNotifier notifier;

        public CheckoutWorkflow(
                Stock stock,
                Payment payment,
                Shipping shipping,
                CompletionNotifier notifier) {
            this.stock = stock;
            this.payment = payment;
            this.shipping = shipping;
            this.notifier = notifier;
        }

        public void execute(String id) {
            boolean reserved = false;
            boolean charged = false;

            try {
                stock.reserve(id);
                reserved = true;

                payment.charge(id);
                charged = true;

                shipping.schedule(id);
            } catch (RuntimeException original) {
                // Demo đơn giản: compensation ngược thứ tự thực hiện.
                if (charged) {
                    payment.refund(id);
                }
                if (reserved) {
                    stock.release(id);
                }
                System.out.println("workflow: failed " + id);
                throw original;
            }

            System.out.println("workflow: completed " + id);
            notifier.notifyCompleted(id);
        }
    }

    public static final class CompletionObserver {
        @EventListener
        public void on(OrderFulfilled event) {
            System.out.println("observer: fulfilled " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Stock stock() {
            return new Stock();
        }

        @Bean
        Payment payment() {
            return new Payment();
        }

        @Bean
        Shipping shipping() {
            return new Shipping();
        }

        @Bean
        CompletionNotifier completionNotifier(
                ApplicationEventPublisher publisher) {
            return new CompletionNotifier(publisher);
        }

        @Bean
        CheckoutWorkflow checkoutWorkflow(
                Stock stock,
                Payment payment,
                Shipping shipping,
                CompletionNotifier notifier) {
            return new CheckoutWorkflow(stock, payment, shipping, notifier);
        }

        @Bean
        CompletionObserver completionObserver() {
            return new CompletionObserver();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            CheckoutWorkflow workflow =
                    context.getBean(CheckoutWorkflow.class);

            System.out.println("caller: OK");
            workflow.execute("OK");

            System.out.println("caller: FAIL");
            try {
                workflow.execute("FAIL");
            } catch (IllegalStateException e) {
                System.out.println("caller: " + e.getMessage());
            }
        }
    }
}
~~~

Chạy tại thư mục **checkout-orchestration-demo** với Java 17+ và Gradle 8.x:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chương trình in ra** với cấu hình synchronous event multicaster mặc định:

~~~text
caller: OK
stock: reserve OK
payment: charge OK
shipping: schedule OK
workflow: completed OK
observer: fulfilled OK
caller: FAIL
stock: reserve FAIL
payment: charge FAIL
shipping: schedule FAIL
payment: refund FAIL
stock: release FAIL
workflow: failed FAIL
caller: shipping unavailable
~~~

Giải thích:

- Với **OK**, orchestrator quyết định thứ tự: reserve, charge rồi schedule. Sau khi ba bước thành công, nó thông báo hoàn thành.
- **CompletionObserver** chỉ ghi nhận event **OrderFulfilled** sau đường thành công; nó không phải nơi quyết định thanh toán hay điều phối hoàn tiền.
- Với **FAIL**, **Shipping.schedule** cố ý ném exception. **CheckoutWorkflow** đã biết stock và payment giả lập thành công nên gọi refund, release rồi trả lại lỗi cho caller.
- Vì observer được publish chỉ sau nhánh thành công, không có **observer: fulfilled FAIL**.
- Trong demo, **refund** và **release** luôn thành công. Trong đời thực, các lời gọi này có thể lỗi; exception từ compensation có thể che lỗi gốc hoặc ngăn bước bù trừ tiếp theo. Cần error handling, persistent workflow state và retry riêng.
- Nếu observer ném exception, event publisher đồng bộ mặc định có thể ném ngược về caller sau khi các bước bắt buộc đã hoàn tất. Không vì thế mà tự động refund đơn hàng đã hoàn tất; thiết kế observer và error policy riêng.

**Vì sao đây là orchestration?** Class **CheckoutWorkflow** sở hữu thứ tự, điều kiện thành công, danh sách bước đã xác nhận và nhánh lỗi. Spring event được dùng **ở ranh giới quan sát sau kết quả**, không thay thế quyền điều phối.

### Giới hạn an toàn của demo

Các biến **reserved** và **charged** chỉ phản ánh những method giả lập đã trả về. Với payment API thật, một timeout có thể xảy ra **sau khi provider đã charge** nhưng trước khi client nhận response; biến charged vẫn false. Do đó không được dùng code này nguyên dạng để quyết định refund trong production.

Phải phân biệt **SUCCESS**, **FAILED** và **UNKNOWN** của từng remote operation; dùng **idempotency keys**, khả năng truy vấn trạng thái bên thứ ba, durable step state, timeout và manual review.

Một orchestrator production cũng cần ghi nhận **OrderFulfilled** hoặc ý định publish một cách bền vững nếu downstream không được mất event. **publishEvent(Object)** in-memory chỉ thực hiện hand-off trong ApplicationContext.

## 8. Thiết kế orchestration như state machine

Khi workflow trải qua nhiều hệ thống hoặc cần phục hồi, hãy mô hình hóa rõ trạng thái:

~~~text
NEW
  |
  v
STOCK_RESERVED
  |
  v
PAYMENT_CHARGED
  |
  v
SHIPPING_SCHEDULED
  |
  v
COMPLETED

Nếu lỗi có side effect:
  -> COMPENSATING
  -> COMPENSATED
  -> FAILED

Nếu compensation không thể tự hoàn thành:
  -> MANUAL_REVIEW
~~~

Một workflow record có thể chứa:

| Trường | Ý nghĩa |
| --- | --- |
| **workflowId** | ID ổn định để correlate commands, events và API |
| **orderId** | Business entity liên quan |
| **state** | Trạng thái đã xác nhận, không tự suy đoán |
| **currentStep** | Bước đang hoặc chuẩn bị xử lý |
| **stepOutcome** | SUCCESS/FAIL/UNKNOWN cho từng bước |
| **attempts** | Số lần retry và backoff |
| **deadline** | Thời điểm timeout hoặc escalation |
| **idempotencyKey** | Chống lặp side effect ở adapter/provider |
| **lastError** | Thông tin lỗi đã sanitize |
| **updatedAt** | Truy vết và hỗ trợ vận hành |

**Transition guards** phải được kiểm tra: không chuyển từ NEW thẳng sang COMPLETED nếu còn payment chưa xác minh. Sau khi restart, orchestrator đọc trạng thái và tiếp tục ở bước hợp lệ thay vì chạy lại từ đầu.

Nếu workflow chỉ gồm vài thao tác local trong một database transaction, không nhất thiết cần một engine riêng. Một **application service với @Transactional** có thể là orchestrator đủ tốt; độ phức tạp của công cụ phải tương xứng yêu cầu nghiệp vụ.

## 9. Orchestration không có nghĩa transaction phân tán tự động

### 9.1. Local transaction

Với các thao tác ghi **cùng một database**, một Spring application service có thể dùng **@Transactional** để giữ invariant và atomicity trong local transaction. Trong trường hợp đó, không nhất thiết tách logic bắt buộc thành các listener.

Nhưng **@Transactional không biến HTTP call** đến payment gateway thành một phần của DB transaction. Giữ transaction mở trong lúc chờ network lâu có thể gây lock contention, timeout hoặc deadlock.

### 9.2. Event chain và thời điểm commit

Với **SimpleApplicationEventMulticaster** đồng bộ mặc định, một **@EventListener** thường chạy khi **publishEvent(...)** được gọi. Nếu publisher đang ở trong **@Transactional**, listener có thể xử lý **trước khi transaction commit**.

~~~text
BEGIN TX
  -> save order
  -> publish OrderConfirmed
      -> @EventListener sends email
  -> exception -> ROLLBACK DB
Email đã gửi, thay đổi DB lại rollback.
~~~

**Return event tiếp theo không đồng nghĩa after-commit**. Event chaining mô tả quan hệ publication; transaction phase là vấn đề độc lập.

### 9.3. AFTER_COMMIT và outbox

Spring cho phép listener theo phase:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderConfirmed event) {
    // Phản ứng sau khi transaction liên quan đã commit.
}
~~~

Đây chỉ là **snippet minh họa** cần bean, imports và một transaction manager phù hợp. Mặc định **fallbackExecution=false**, nên listener không chạy nếu event publish ngoài transaction tương thích. Sau commit, nếu phải ghi dữ liệu mới có commit riêng, thường cần transaction mới (**REQUIRES_NEW**) qua Spring-managed service.

**AFTER_COMMIT** tránh nhiều side effect trước commit nhưng không cung cấp bảo đảm durable delivery nếu process chết ngay sau commit.

Nếu event/công việc tiếp theo **không được mất**, cân nhắc **transactional outbox**:

~~~text
BEGIN DB TRANSACTION
  -> save business state
  -> save outbox command/event message
COMMIT
  -> worker reads outbox
  -> publish to message broker / next participant
  -> retry and record delivery
  -> consumer deduplicates and handles message
~~~

Outbox message và business state cùng commit; worker có thể phục hồi sau restart. Việc gửi lặp vẫn có thể xảy ra nếu worker publish thành công nhưng đánh dấu đã gửi thất bại, nên consumer phải **idempotent**. Không tự tuyên bố exactly-once end-to-end chỉ nhờ outbox.

Một durable orchestrator có thể dùng outbox để gửi command, **inbox/deduplication** để xử lý result events, và cập nhật workflow state bằng local transaction.

## 10. Orchestration cũng có thể bất đồng bộ và event-driven

Một orchestrator không nhất thiết gọi ba HTTP API đồng bộ theo chuỗi. Kiểu điều phối qua commands và result events:

~~~text
CheckoutOrchestrator
    -> command ReserveStock(workflowId, orderId)
StockService
    -> event StockReserved(workflowId) / StockRejected
CheckoutOrchestrator
    -> command ChargePayment(workflowId, paymentAttemptId)
PaymentService
    -> event PaymentCaptured / PaymentDeclined
CheckoutOrchestrator
    -> command ScheduleShipment(workflowId, orderId)
ShippingService
    -> event ShipmentScheduled / ShipmentFailed
CheckoutOrchestrator
    -> state COMPLETED / COMPENSATING / MANUAL_REVIEW
~~~

Orchestrator là chủ sở hữu bước tiếp theo. Các participants có thể triển khai bằng Spring Boot, Kafka hoặc RabbitMQ, nhưng **domain rules** và các cổng gọi nên được giữ riêng khỏi framework vận chuyển khi phù hợp.

Một kiến trúc thường gặp:

~~~text
application/
  CheckoutWorkflow (orchestrator)
  StockGateway, PaymentGateway, ShippingGateway (ports)
domain/
  Order, payment policies, invariants, domain events
infrastructure/
  Spring adapters, HTTP/messaging adapters
  workflow state repository, outbox/inbox implementation
~~~

Việc đổi broker không buộc domain import Kafka. Nếu một quy trình dài hơn khả năng quản lý của custom state machine, hãy cân nhắc workflow engine có persistence, durable timers và orchestration history.

## 11. Phát lại event (replay) và event chain

Vì chủ đề nằm trong nhóm **“Phát lại và chuỗi event”**, cần phân biệt **replay** và việc event chain tự tạo bước tiếp:

- **Event chain:** một event hiện tại khiến listener tạo event mới ngay. Không yêu cầu lịch sử đã lưu.
- **Event replay:** phát lại các event **đã lưu** từ event log, event store hoặc outbox để tái tạo projection, xử lý lại hay phục hồi.
- **Retry:** thực hiện lại một bước theo chính sách; có thể gây side effect trùng nếu không idempotent.
- **Redelivery:** broker gửi lại message; consumer có thể gặp cùng event nhiều lần.

Nguy cơ: một listener khi replay **OrderConfirmed** để dựng lại báo cáo lại gọi charge payment hoặc return **ChargePaymentRequested**. Khi đó một thao tác chỉ để tái dựng projection đã kích hoạt side effect mới. Orchestrator nên tách **business state transitions** khỏi các read-model projections, đồng thời có deduplication và nhận biết replay mode khi cần.

Đừng dùng Spring **ApplicationEventPublisher** như một event store: API này không cung cấp phát lại lịch sử hoặc durable queue mặc định.

## 12. Phân biệt workflow owner với God Service

Orchestration mang lại quyền điều phối nhưng cũng có chi phí:

**Nên đặt ở orchestrator:**

- Chọn và gọi bước tiếp theo.
- Theo dõi currentStep, status, attempts và deadline.
- Quyết định retry, bù trừ, tạm dừng/manual review.
- Liên kết result event với đúng workflowId/attempt.
- Xác định khi nào workflow thành công hoặc thất bại.

**Không nên nhồi vào orchestrator:**

- Toàn bộ invariant của aggregate.
- Chi tiết SQL, JDBC, connection pooling.
- Logic serialization và giao tiếp broker ở mức thấp.
- Quy tắc tính toán giá, thuế, chiết khấu vốn thuộc domain.
- Hàng chục observer analytics không ảnh hưởng kết quả.

**Nguyên tắc:** orchestrator **chỉ điều phối**, domain services/aggregates giữ nghiệp vụ, infrastructure adapters giữ chi tiết framework. Nếu coordinator quá lớn, chia theo use case hoặc bounded context, không chia tùy tiện thành một chuỗi event không có owner.

## 13. Những trường hợp thực tế

### Checkout có charge và shipment

**Orchestration** thường phù hợp. Các bước phải có kết quả, có rủi ro double-charge, cần compensation và một trạng thái đơn cuối cùng. Observer **OrderFulfilled** có thể cập nhật analytics độc lập sau khi workflow chính hoàn tất.

### Đơn hàng đã confirmed, cần đồng bộ search và analytics

**Event chain/choreography** phù hợp. Các subscriber độc lập; thất bại của search index không làm trạng thái đơn hàng sai. Nếu không được mất dữ liệu cập nhật, hãy publish bằng outbox/queue thay vì chỉ in-memory callback.

### Onboarding cần người duyệt trong 3 ngày

**Durable orchestration** thường hợp hơn event chain đơn giản: cần deadline, trạng thái chờ, quyết định người duyệt, resume sau restart, escalation và audit.

### Notification marketing không critical

Dùng event-driven subscriber hoặc queue. Không cần orchestration cho toàn bộ chiến dịch chỉ để xử lý một notification sau khi một user đăng ký; trừ khi có workflow nhiều bước phụ thuộc kết quả, chính sách retry/opt-out phức tạp hoặc approval.

### Tính cước thuê bao nhiều bước trong một database

Một **application service với transaction local** và domain service calls có thể tốt hơn cả saga lẫn event chain. Không lạm dụng durable engine khi chưa cần.

## 14. Kiểm thử sự khác biệt

### 14.1. Unit test orchestrator

Ở code production nên trừu tượng hóa **Stock**, **Payment** và **Shipping** thành interfaces để đưa fake/spy vào test. Dùng một **List<String>** ghi thứ tự method calls.

Các test quan trọng:

1. **Happy path:** reserve → charge → schedule → completed → notify.
2. **Stock failure:** không gọi payment/shipping, trả lỗi phù hợp.
3. **Payment failure:** release stock đã reserve; không gọi shipping.
4. **Shipping failure:** refund payment rồi release stock; không publish OrderFulfilled.
5. **Compensation failure:** lưu trạng thái chưa bù trừ xong, retry/manual review, không che giấu lỗi gốc.
6. **Duplicate command:** cùng workflowId/idempotencyKey không tạo side effect mới.
7. **Remote timeout:** đánh dấu UNKNOWN, query/reconcile thay vì retry mù.
8. **Observer failure:** bước chính đã hoàn tất không bị đánh dấu cần refund chỉ vì analytics lỗi.
9. **Restart:** resume từ persisted step, không chạy lại các bước thành công.
10. **Cancelled workflow:** xác định giới hạn hủy và nhánh compensation tương ứng.

Demo mục 7 thể hiện happy/failure path in-memory; các case persistence/restart cần integration tests với hạ tầng thật.

### 14.2. Integration test Spring event và transaction

Cần kiểm tra riêng:

- Event observer chỉ được phát sau khi điều kiện nghiệp vụ thành công.
- Listener **@EventListener** đồng bộ gây exception có ảnh hưởng tới publisher như mong đợi theo cấu hình.
- **@TransactionalEventListener(AFTER_COMMIT)** không chạy khi transaction rollback.
- Outbox record và thay đổi business state commit atomic trong cùng database.
- Worker chết sau publish nhưng trước mark-delivered không khiến consumer xử lý side effect trùng.
- Events đến sai thứ tự hoặc quá deadline không làm workflow đi sang trạng thái bất hợp lệ.

Một test chỉ verify **publishEvent(...) đã được gọi** không chứng minh workflow đúng. Phải kiểm tra **business state** và **step outcomes**.

## 15. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng event chain cho mọi bước bắt buộc | Không rõ nơi sở hữu thành công/thất bại | Chọn workflow owner/orchestrator |
| Dùng **@Order** để điều phối business state | Chỉ ưu tiên dispatch, không lưu workflow | State machine + transition guards |
| Tưởng return event đồng nghĩa giao dịch mới | Không tạo atomicity/commit | Xác định transaction boundary riêng |
| Dùng **@Async** để bảo đảm eventual completion | Task memory có thể mất | Durable queue/outbox + retry |
| Retry payment khi timeout với key mới | Nguy cơ double charge | Idempotency key + provider reconciliation |
| Compensation không lưu trạng thái | Crash làm bù trừ dở dang | Durable workflow state và background retry |
| Xem refund như rollback ACID | Lịch sử giao dịch vẫn có charge/refund | Audit cả hai, thiết kế trạng thái rõ |
| Giữ DB transaction qua HTTP call dài | Lock lâu, timeout, deadlock | Local transactions ngắn + orchestration |
| Cho observer không critical vào bước bắt buộc | Analytics lỗi khiến checkout báo lỗi | Đưa observer ra event/queue với error policy |
| Đánh dấu COMPLETED ngay khi gửi command | Chưa chắc participant đã thực hiện | Chờ result event có correlation |
| Không có workflowId, eventId, attemptId | Khó trace và deduplicate | Identity ổn định, metadata rõ |
| Replay event dẫn đến charge lại | Side effect trùng | Tách projection khỏi action, idempotency |
| Orchestrator chứa mọi domain logic | God Service, coupling cao | Domain giữ invariants, coordinator chỉ điều phối |
| Không kiểm thử lỗi và restart | Happy path đánh lừa độ tin cậy | Fault injection, retry/duplicate tests |

## 16. Checklist lựa chọn thiết kế

1. **Bước sau có phụ thuộc bắt buộc vào kết quả bước trước không?** Nếu có, nghiêng orchestration.
2. **Có một status nghiệp vụ cuối cùng cần xác nhận cho API/caller không?** Nếu có, cần workflow owner.
3. **Có remote side effects không thể rollback tự động không?** Nếu có, phải xét compensation.
4. **Có trường hợp kết quả UNKNOWN do timeout không?** Nếu có, cần reconciliation/idempotency.
5. **Process chết giữa các bước có phải tiếp tục được không?** Nếu có, cần durable workflow state.
6. **Event có nhiều observer không critical không?** Nếu có, hãy giữ fan-out tách rời.
7. **Observer lỗi có được phép khiến use case chính báo lỗi không?** Thiết kế error boundary tường minh.
8. **Có replay/redelivery không?** Chặn duplicate side effects.
9. **Quy trình đơn giản chỉ dùng một database transaction không?** Application service thường đủ.
10. **Orchestrator có ôm invariant của domain không?** Đưa quy tắc domain về aggregate/domain service.

**Kết luận:** Chọn **event chain/choreography** cho các phản ứng độc lập, ghép nối lỏng hoặc fan-out sau một sự kiện hợp lệ. Chọn **orchestration** khi quy trình cần **thứ tự bắt buộc, kết quả tổng thể, timeout/retry, bù trừ hoặc trạng thái bền vững để khôi phục**. Hai cách có thể kết hợp: orchestrator quản lý bước chính, còn Spring events hoặc broker events đưa thông báo tới các observer không sở hữu workflow.

### Tài liệu chính thức

- Spring Framework Reference — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
