# Đặt id ổn định cho mỗi endpoint @JmsListener

> **Module:** Spring Framework – JMS  
> **Nhóm kiến thức:** `@JmsListener`  
> **Trọng tâm:** Đặt `id` rõ ràng, ổn định và duy nhất cho **listener endpoint trong mỗi Spring application context**, nhằm quản lý lifecycle, kiểm thử và quan sát hệ thống.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `@JmsListener(id = "...")` thực chất đặt **định danh của listener container** do Spring quản lý, không phải tên queue, message ID, JMS client ID hay durable subscription name.
2. Biết vì sao không nên phụ thuộc ID tự sinh nếu ứng dụng cần dùng `JmsListenerEndpointRegistry` để tra cứu hoặc điều khiển đúng endpoint qua nhiều lần deploy.
3. Tạo một quy ước đặt tên ổn định, duy nhất trong phạm vi registry, đủ rõ dịch vụ/nghiệp vụ/vai trò để dùng trong code, log, test và dashboard.
4. Biết kiểm tra danh sách ID bằng `getListenerContainerIds()`, lấy container qua `getListenerContainer(id)` và thực hiện `start()`/`stop()` trong đúng **application instance**.
5. Giải thích tại sao cùng một ID có thể xuất hiện ở **hai replica khác nhau**, nhưng không thể đăng ký trùng hai endpoint trong cùng `JmsListenerEndpointRegistry`.
6. Phân biệt ID endpoint với `destination`, `containerFactory`, bean name, `subscription`, `clientId` và `JMSMessageID`.
7. Xử lý các trường hợp một method có nhiều `@JmsListener`, placeholder cấu hình, đăng ký endpoint bằng code, và thay đổi ID trong khi hệ thống đang vận hành.
8. Viết kiểm thử xác nhận ID đã đăng ký và thiết kế runbook start/stop/diagnostics an toàn, không ngộ nhận `isRunning()` là broker đã giao tiếp khỏe mạnh.

## 1. Một method @JmsListener tạo ra những gì?

Xét một listener đơn giản:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceJobListener {

    @JmsListener(destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        System.out.println("Invoice job: " + invoiceId);
    }
}
```

Về phía Spring:

1. `@EnableJms` (hoặc hạ tầng tương ứng do ứng dụng cấu hình) bật xử lý annotation.
2. `JmsListenerAnnotationBeanPostProcessor` tìm method mang `@JmsListener` trong Spring-managed beans.
3. Spring tạo một **`JmsListenerEndpoint`** mô tả method, destination và các thuộc tính annotation.
4. `JmsListenerContainerFactory` được lựa chọn tạo một **`MessageListenerContainer`** thực hiện việc kết nối, lấy message, chuyển đổi payload và gọi method.
5. `JmsListenerEndpointRegistry` quản lý các listener containers theo **endpoint ID** và lifecycle của chúng.

```text
@Component InvoiceJobListener
         |
         | @JmsListener(...)
         v
JmsListenerAnnotationBeanPostProcessor
         |
         v
JmsListenerEndpoint (id + destination + method + options)
         |
         v
JmsListenerContainerFactory
         |
         v
MessageListenerContainer -----> Queue / Topic trên JMS provider
         |
         +---- JmsListenerEndpointRegistry
                  |
                  +-- id -> container
                  +-- getListenerContainer(id)
                  +-- getListenerContainerIds()
```

**ID trong `@JmsListener` gắn với container do Spring tạo**, không phải primary key của message trên broker. Cùng một destination có thể được phục vụ bởi nhiều listener containers (mỗi container có ID riêng), nhưng chúng tuân theo semantics Queue/Topic, không tự trở thành các nhóm nghiệp vụ độc lập chỉ vì ID khác nhau.

Các listener containers được registry tạo từ annotated endpoints **không phải các Spring bean thông thường để tự `@Autowired` theo tên container**. Hãy dùng registry để quản lý; `@Component` của handler vẫn là bean riêng.

### 1.1. Đặt ID tường minh

```java
@Component
public class InvoiceJobListener {

    @JmsListener(
            id = "billing.invoice.worker.v1",
            destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        // Process invoice.
    }
}
```

Ở đây:

- `billing.invoice.worker.v1` = **ID endpoint trong Spring registry**.
- `billing.invoice.jobs` = **tên destination** do listener container phân giải thành Queue/Topic.
- `consume` = Java handler method.
- `InvoiceJobListener` = Spring bean (theo mặc định có tên suy ra từ class, nhưng không dùng nó như endpoint ID).

**Không có quy tắc JMS bắt buộc đặt ID theo định dạng trên**. Đây là convention ứng dụng. Ý nghĩa của `id` là một **String duy nhất trong registry**, còn tính ổn định qua bản phát hành là trách nhiệm của đội phát triển.

### 1.2. ID được sinh tự động nếu không chỉ rõ

Javadoc `@JmsListener.id()` quy định: nếu không chỉ rõ `id` thì Spring cung cấp một **auto-generated identifier**.

Trong một số phiên bản implementation, ID tự sinh có dạng gần như:

```text
org.springframework.jms.JmsListenerEndpointContainer#0
org.springframework.jms.JmsListenerEndpointContainer#1
...
```

Đó là **chi tiết implementation**, không nên coi là format API bất biến hay ổn định theo thứ tự. Khi thêm listener mới, đổi registration order, thay component scanning, cấu hình hoặc upgrade version, association giữa ID tự sinh và một method có thể thay đổi.

Dùng auto-ID khi không cần tham chiếu endpoint bằng tên cố định. Khi có script vận hành, endpoint health check, điều khiển lifecycle hay test theo ID, nên khai báo `id` rõ ràng.

## 2. “Ổn định” và “duy nhất” là hai yêu cầu khác nhau

Một ID tốt cần cả hai thuộc tính:

**Ổn định theo thời gian:** cùng một logical listener vẫn mang cùng ID khi restart, redeploy, thay tên Java method hoặc thay class/package mà nghiệp vụ không đổi.

**Duy nhất trong phạm vi một registry:** hai endpoints khác nhau trong cùng Spring application context không đăng ký cùng một ID.

Giả sử dịch vụ Billing có hai listener:

```java
@JmsListener(
        id = "billing.invoice.worker.v1",
        destination = "billing.invoice.jobs")
public void processInvoice(String payload) { ... }

@JmsListener(
        id = "billing.reconcile.worker.v1",
        destination = "billing.reconcile.jobs")
public void reconcile(String payload) { ... }
```

Cả hai dùng convention `<service>.<domain>.<role>.<contractVersion>`, nhưng đây chỉ là **gợi ý đặt tên**, không phải cú pháp Spring áp đặt.

Tại sao version có thể hữu ích? Nếu phiên bản mới thực sự tạo ra **một logical endpoint riêng** có contract khác (ví dụ chạy song song trong migration), `.v2` giúp tránh va chạm. Nếu chỉ refactor class name hoặc thay log, **không cần đổi endpoint ID**.

### 2.1. Quy ước khuyến nghị

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| Service/owner | Biết đội/hệ thống chịu trách nhiệm | `billing` |
| Domain/feature | Biết nghiệp vụ | `invoice` |
| Role | Phân biệt worker, audit, notification… | `worker` |
| Contract version (nếu cần) | Nhiều endpoint khác contract cùng tồn tại | `v1` |
| Toàn bộ ID | Đọc được, deterministic, ít đổi | `billing.invoice.worker.v1` |

**Không** dùng UUID sinh lúc startup làm endpoint ID nếu mục tiêu là tra cứu ổn định.

```java
// ANTI-PATTERN về chiến lược: đừng dùng runtime-generated ID
// cho một endpoint mà dashboard/script phải tra cứu cố định.
String ephemeral = java.util.UUID.randomUUID().toString();
```

Đoạn trên chỉ minh họa việc UUID thay đổi qua lần chạy; không phải cách đặt annotation value, vì giá trị annotation Java phải là compile-time constant (trừ khi dùng cơ chế placeholder/SpEL do Spring hỗ trợ).

### 2.2. ID có cần khác nhau giữa các replica?

**Không bắt buộc** nếu hai replica là hai **application contexts tách biệt** và cùng triển khai một logical endpoint. Ví dụ:

```text
Pod A / Spring Context A              Pod B / Spring Context B
  Registry A                            Registry B
  id = billing.invoice.worker.v1        id = billing.invoice.worker.v1
      |                                      |
      v                                      v
  container A                            container B
      |                                      |
      +-------- Queue billing.invoice.jobs --+
                 competing consumers
```

Mỗi registry có namespace ID của riêng nó. Hai containers trên hai replica có thể cùng ID vì chúng không được đăng ký chung vào **một** registry. Trên Queue, chúng cạnh tranh nhận message theo broker; ID giống nhau không làm Queue tự nhân bản message.

**Nhưng trong telemetry tập trung**, tag `endpointId` một mình không đủ để nhận diện một container runtime duy nhất. Hãy kết hợp thêm `service`, `environment` và `instance/pod` trong dữ liệu quan sát. Không vì muốn tag duy nhất toàn cụm mà nhét pod UUID vào `@JmsListener.id` nếu ứng dụng cần quản lý bằng logical ID ổn định.

### 2.3. ID trùng trong cùng registry bị từ chối

`JmsListenerEndpointRegistry` kiểm tra ID khi đăng ký listener container. Hai endpoint cùng ID trong **một registry** là lỗi cấu hình, không phải “Spring tự gộp listeners”.

```java
// MINH HỌA SAI: hai endpoint trong cùng application context.
@JmsListener(id = "billing.worker.v1",
             destination = "billing.invoice.jobs")
public void invoice(String value) { /* ... */ }

@JmsListener(id = "billing.worker.v1",
             destination = "billing.reconcile.jobs")
public void reconcile(String value) { /* ... */ }
```

Khi Spring đăng ký endpoint thứ hai, registry có thể ném `IllegalStateException` với thông điệp kiểu `Another endpoint is already registered with id 'billing.worker.v1'`. Đây là lỗi cần sửa ở configuration/code, **không phải lỗi broker chưa tạo queue**.

Lưu ý: lỗi này không có nghĩa mỗi application replica phải tự sinh ID khác. Ranh giới kiểm tra uniqueness là **instance registry đang chứa các endpoint**.

## 3. Đừng nhầm endpoint id với những loại ID khác

Có nhiều chữ “id” trong JMS/Spring. Chúng giải quyết những bài toán khác nhau.

| Định danh | Nằm ở đâu? | Phạm vi/ý nghĩa | Ví dụ |
| --- | --- | --- | --- |
| `@JmsListener(id=...)` | Spring annotation/registry | Tên của endpoint container **trong Spring registry** | `billing.invoice.worker.v1` |
| `destination` | Spring annotation/JMS provider | Tên Queue hoặc Topic để nhận message | `billing.invoice.jobs` |
| `containerFactory` | Spring annotation | Tên Spring bean của factory tạo container | `invoiceListenerFactory` |
| `@Component("...")` | Spring BeanFactory | Bean name của object handler | `invoiceJobListener` |
| `subscription` | `@JmsListener` / JMS Topic | Tên subscription khi cấu hình durable/shared | `billing-audit-v1` |
| JMS `clientId` | JMS Connection/Container | Định danh client connection cho một số subscription use cases; có quy tắc uniqueness riêng | `billing-audit-client` |
| `JMSMessageID` | Header của **mỗi message** | ID do provider gán khi gửi, khác mỗi message | `ID:...` (provider-specific) |
| `JMSCorrelationID` | Message header | Ghép request/reply theo hợp đồng ứng dụng | `req-42` |
| `businessId` | Body/property ứng dụng | Định danh nghiệp vụ và idempotency | `invoice-42` |

**Không bao giờ suy ra**:

- `@JmsListener(id="x")` đặt JMS `Connection.setClientID("x")`.
- `@JmsListener(id="x")` tạo durable subscription tên `x`.
- `@JmsListener(id="x")` khiến broker tạo queue tên `x`.
- `@JmsListener(id="x")` buộc các message nhận có `JMSMessageID="x"`.
- `@Component("x")` tự dùng `x` làm endpoint id.

Mỗi trường có API và lifecycle riêng. Một service có thể cần **cả endpoint ID cố định lẫn subscription name cố định**, nhưng đặt một cái không thay cho cái kia.

### 3.1. Ví dụ Queue: ID endpoint không phải JMS group ID

JMS có header/property chuẩn `JMSXGroupID` để nhóm các message liên quan khi provider hỗ trợ message grouping. Endpoint ID **không phải** `JMSXGroupID` và không ra lệnh broker gán một partition vào một endpoint cụ thể.

Nếu yêu cầu xử lý tuần tự theo invoiceId, cần thiết kế message grouping/ordering và concurrency theo provider, không chỉ đặt listener id theo invoiceId.

### 3.2. Ví dụ Topic durable: ba ID tách biệt

```java
@JmsListener(
        id = "billing.audit.topic.consumer.v1",
        destination = "billing.events",
        subscription = "billing-audit-v1",
        containerFactory = "billingDurableTopicFactory")
public void onEvent(String payload) { /* ... */ }
```

Đây là method minh họa nằm trong Spring-managed component có Topic factory được cấu hình durable đúng. `id` dùng cho registry; `subscription` dùng cho durable JMS subscription. `clientId` có thể phải được cấu hình qua `ConnectionFactory`/listener factory tùy shared/unshared semantics và version provider.

Đổi **endpoint ID** để chỉnh công cụ vận hành thường không tự xóa broker subscription. Đổi **subscription name/client identity** có thể tạo subscription khác và tác động nghiêm trọng đến backlog. Vì vậy cần quản trị hai loại tên độc lập.

Với nhiều replica, **không đặt cùng unshared durable JMS clientId** cho các connections đang hoạt động rồi cho rằng endpoint ID giống nhau sẽ giúp chia tải. Hãy xác định dùng shared durable subscription hay thiết kế identity riêng đúng hợp đồng JMS/provider.

## 4. Ví dụ cấu hình Spring JMS đầy đủ với ID ổn định

Ví dụ dưới dùng **Spring Framework 6.x hoặc 7.x, Java 17+, Jakarta Messaging**. Cần dependency `spring-jms`, provider JMS, broker và `ConnectionFactory` thực tế. Các file được trình bày như **các class trong cùng một Spring project**; chúng không thể chạy bằng `javac` chỉ có JDK.

Giả định broker có hai Queue:

- `billing.invoice.jobs`: xử lý tạo hóa đơn.
- `billing.reconcile.jobs`: đối soát.

### 4.1. Khai báo listener container factory

**File `BillingJmsConfig.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class BillingJmsConfig {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);       // Queue.
        factory.setSessionTransacted(true);    // Local JMS transaction.
        factory.setConcurrency("1-3");
        return factory;
    }
}
```

- `@EnableJms` bật annotation-driven JMS endpoints.
- Bean factory mặc định tên `jmsListenerContainerFactory` được Spring tìm khi annotation không chỉ định factory riêng.
- `setSessionTransacted(true)` là lựa chọn cho listener cần redelivery khi xử lý lỗi; không phải điều kiện để đặt ID.
- `concurrency="1-3"` có thể tạo nhiều consumer sessions cho một endpoint, **không có nghĩa tạo ba endpoint IDs**.
- Config broker, authentication, resource provisioning và connection recovery do project/provider quản lý. Queue có thể cần được tạo sẵn.

### 4.2. Hai handler có ID khác nhau

**File `InvoiceJobListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceJobListener {

    @JmsListener(
            id = "billing.invoice.worker.v1",
            destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        System.out.println("Invoice: " + invoiceId);
    }
}
```

**File `ReconciliationListener.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationListener {

    @JmsListener(
            id = "billing.reconcile.worker.v1",
            destination = "billing.reconcile.jobs")
    public void consume(String batchId) {
        System.out.println("Reconcile: " + batchId);
    }
}
```

Hai endpoint này có ID ổn định bất kể tên class Java có đổi (nếu vẫn giữ annotation ID). Cùng một bean có thể có nhiều listener methods, miễn mỗi endpoint có ID riêng.

Nếu gửi một `TextMessage` chứa `INV-42` tới `billing.invoice.jobs`, listener thứ nhất **có thể** in `Invoice: INV-42` nếu broker hoạt động, queue hợp lệ và message được consumer xử lý. Không cung cấp stdout cố định cho integration snippet vì timing, concurrency, redelivery, number of replicas và trạng thái broker là runtime-dependent.

### 4.3. Không đặt id thành tên queue một cách mù quáng

Không có gì cấm đặt:

```java
@JmsListener(
        id = "billing.invoice.jobs",
        destination = "billing.invoice.jobs")
```

Nhưng đây **không phải quy tắc nên áp dụng chung**. Khi có **hai endpoint khác nhau cùng nghe một destination** (ví dụ selector khác nhau hoặc listener method khác), ID trùng queue name sẽ gây xung đột registry. Chọn ID theo **logical consumer role** thay vì chỉ chép nguyên destination.

## 5. Tìm container bằng id: JmsListenerEndpointRegistry

Spring cung cấp:

```text
org.springframework.jms.config.JmsListenerEndpointRegistry
```

Hai method quan trọng:

```java
Set<String> getListenerContainerIds();

@Nullable
MessageListenerContainer getListenerContainer(String id);
```

`getListenerContainerIds()` trả tập ID của các listener containers mà registry quản lý. `getListenerContainer(id)` trả container tương ứng hoặc **`null`** khi không tìm thấy.

Container có các lifecycle method:

```java
boolean isRunning();
void start();
void stop();
```

Đừng gọi `registry.getListenerContainer(id).stop()` khi chưa kiểm tra null; nếu key sai, bạn sẽ gặp `NullPointerException` và chưa có container nào được dừng.

### 5.1. Service tra cứu an toàn

**File `BillingListenerControl.java`:**

```java
import java.util.Set;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public final class BillingListenerControl {

    public static final String INVOICE_ID =
            "billing.invoice.worker.v1";
    public static final String RECONCILE_ID =
            "billing.reconcile.worker.v1";

    private final JmsListenerEndpointRegistry registry;

    public BillingListenerControl(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public Set<String> registeredIds() {
        return Set.copyOf(registry.getListenerContainerIds());
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer container =
                registry.getListenerContainer(id);

        if (container == null) {
            throw new IllegalArgumentException(
                    "Unknown JMS endpoint id: " + id);
        }
        return container;
    }

    public boolean invoiceContainerRunning() {
        return requireContainer(INVOICE_ID).isRunning();
    }

    public void stopInvoiceListenerLocally() {
        requireContainer(INVOICE_ID).stop();
    }

    public void startInvoiceListenerLocally() {
        requireContainer(INVOICE_ID).start();
    }
}
```

Đây là class hoàn chỉnh để dùng trong Spring project đã bật `@EnableJms`; không phải chương trình chạy bằng JDK thuần. Các lifecycle calls phải được bảo vệ bởi **authorization/quy trình vận hành**. Không nên đưa thẳng `stop()`/`start()` thành HTTP endpoint không có authentication, role checks, audit và safety controls.

**Một câu cực quan trọng:** Dừng container trên **một application instance** không có nghĩa đã dừng mọi replica trong cluster. Registry nằm trong một context/JVM, không phải broker-wide registry.

### 5.2. So sánh getListenerContainers với autowire bean

Spring reference/Javadoc ghi rõ: listener containers do endpoint registry tạo **không nhất thiết là bean riêng trong `ApplicationContext`**. Vì vậy:

```java
// Không phụ thuộc @Qualifier("billing.invoice.worker.v1")
// để tự động inject MessageListenerContainer giống một @Bean thường.
```

Thay vào đó:

```java
MessageListenerContainer container =
        registry.getListenerContainer("billing.invoice.worker.v1");
```

Nếu ứng dụng có container do chính bạn tạo `@Bean` thủ công, nó thuộc cơ chế khác và có thể không nằm trong registry của annotated endpoints. Đừng suy ra `getListenerContainerIds()` liệt kê mọi `MessageListenerContainer` có thể tồn tại trong toàn ApplicationContext.

### 5.3. Danh sách ID là một tập, không phải danh sách thứ tự

`getListenerContainerIds()` trả `Set<String>`. Không phụ thuộc iteration order hoặc thứ tự khởi tạo để quyết định endpoint nào là “số 0” hay “số 1”. Nếu cần hiển thị cố định:

```java
var sorted = registry.getListenerContainerIds()
        .stream().sorted().toList();
System.out.println(sorted);
```

Dòng in chỉ minh họa sort; danh sách thực tế còn tùy cấu hình listener trong application context. Có thể dùng ID ổn định trong test hoặc hệ thống metrics mà không phải phụ thuộc thứ tự trả về.

### 5.4. isRunning không phải toàn bộ health check

`container.isRunning() == true` cho thấy lifecycle container **đang ở trạng thái running theo Spring**. Nó không chứng minh:

- Broker hiện kết nối ổn định và mọi consumer đã subscribe thành công.
- Destination tồn tại/đúng type và principal có quyền nhận.
- Message đang được deliver và handler đã commit nghiệp vụ.
- Không có retry/recovery loop, connection chập chờn hoặc poison messages.
- Queue backlog và oldest message age nằm trong SLA.

Một listener container có cơ chế recovery khi broker tạm down có thể còn ở trạng thái started trong khi delivery chưa hiệu quả. Health/observability phải gồm **broker connectivity, consumer counts, queue/topic subscription backlog, processing latency, error logs và business results**, không chỉ `isRunning`.

## 6. Start/stop theo id: công dụng và giới hạn

ID ổn định giúp bộ phận vận hành có thể:

- Dừng tạm việc consume của **một logical listener** trên một instance khi cần bảo trì.
- Khởi động lại đúng listener thay vì dừng toàn bộ JMS subsystem.
- Kiểm tra sự tồn tại của endpoint sau rollout/refactor.
- Gắn tên endpoint nhất quán vào diagnostics và log.
- Viết automation an toàn với một **allowlist** các endpoint được phép điều khiển.

### 6.1. Start/stop thay đổi gì?

```text
Spring Context A
  Registry A
    billing.invoice.worker.v1
         |
         +-- stop() --> local listener container ngừng tiêu thụ
         |
         +-- start() -> local listener container bắt đầu lại

JMS Broker
  Queue billing.invoice.jobs
    vẫn tồn tại, chịu chính sách persistence/TTL/retention
```

Gọi `stop()` trên container **không xóa Queue** và không đồng nghĩa purge messages. Message pending có thể tiếp tục tồn trong broker theo cấu hình. Message đang in-flight, session transaction và thời điểm stop hoàn tất cần được hiểu theo implementation/container/provider; đừng khẳng định mọi `stop()` lập tức hủy/rollback toàn bộ handler đang chạy.

`start()` kích hoạt lại lifecycle container nhưng không bảo đảm broker hiện khỏe hay message mới ngay lập tức được xử lý. Cần quan sát logs/metrics.

### 6.2. Nhiều replica phải điều khiển từng instance

Nếu hai replicas có cùng ID `billing.invoice.worker.v1`, bạn gọi `stop()` trong **Replica A**:

- A ngừng nhận (theo lifecycle container local).
- B **vẫn có thể tiếp tục nhận** từ cùng queue.
- Nếu mục tiêu là global maintenance, phải có workflow tác động trên toàn fleet, hoặc chặn producer/consumer bằng cơ chế deployment/broker phù hợp.
- Lệnh vận hành nên ghi cả `logical endpoint ID` và `instance identity` để tránh diễn giải sai phạm vi.

**Đặt ID giống nhau trên hai replica không biến `JmsListenerEndpointRegistry` thành distributed registry.**

### 6.3. Chú ý khi listener tiêu thụ Topic

Trên Topic non-durable, stop có thể làm subscription/consumer không còn active, tùy lifecycle container; message publish trong lúc subscriber không tồn tại **có thể không được giữ**. Với durable subscription, retention phụ thuộc cấu hình durable identity, delivery mode, expiration và broker policy. Đừng nói “stop luôn an toàn cho mọi message” chỉ vì endpoint ID ổn định.

Nếu muốn bảo trì không mất topic events, phải thiết kế durable/shared subscription phù hợp **trước khi** dùng stop/start.

## 7. Đặt ID bằng property placeholder

Một vài hệ thống muốn dùng config centralize:

```java
@Component
public class InvoiceJobListener {

    @JmsListener(
            id = "${app.jms.invoice.endpoint-id:billing.invoice.worker.v1}",
            destination = "billing.invoice.jobs")
    public void consume(String invoiceId) {
        // ...
    }
}
```

`id` annotation khai báo một String có **Spring property placeholder**, không phải Java runtime expression thông thường. `JmsListenerAnnotationBeanPostProcessor` giải quyết giá trị bằng embedded value resolver trước khi đăng ký endpoint. Nếu property không được cấp, phần sau dấu hai chấm là default `billing.invoice.worker.v1`.

**Điều kiện cần:** giá trị cuối cùng sau resolve phải là **nonblank và duy nhất trong registry**. Nếu configuration mỗi lần deploy đổi giá trị, ID không còn ổn định như mong muốn.

### 7.1. Khi nào nên dùng placeholder?

Phù hợp khi:

- Cùng codebase triển khai những logical listener roles khác nhau ở các profile, nhưng **mỗi role có ID cố định** được kiểm soát.
- Một tổ chức có convention ID trong config cần được validate khi startup.
- Cần migrations có kế hoạch từ ID cũ sang ID mới mà có thể kiểm soát qua environment config.

Không phù hợp khi:

- Mỗi pod dùng một random UUID làm `endpoint-id`.
- ID tự sinh từ timestamp hoặc build number nên đổi mỗi deployment.
- ID chứa thông tin bí mật, customer PII hoặc token.
- ID do một external user tùy ý nhập và có thể đè ID endpoint khác.

**Nhắc lại:** cùng logical listener chạy ở nhiều replicas có thể dùng cùng endpoint ID vì mỗi replica có registry riêng. Không dùng placeholder để chế ra giá trị pod-specific chỉ vì sợ “trùng ID toàn cluster”.

### 7.2. Nếu đổi namespace config

Từ:

```text
billing.invoice.worker.v1
```

sang:

```text
billing.invoice.consumer
```

nên coi đó là thay đổi **địa chỉ quản trị Spring**, không tự động là migration broker resource. Cập nhật mọi code `registry.getListenerContainer(...)`, dashboards, runbooks, startup assertions, alert labels và các automation. Đừng đổi nếu chỉ refactor method mà không có lý do vận hành.

## 8. Một method được gắn nhiều @JmsListener: mỗi endpoint một ID

`@JmsListener` là **repeatable annotation** trong Spring. Một method có thể lắng nghe hai destination:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class SharedInvoiceHandler {

    @JmsListener(
            id = "billing.invoice.primary.v1",
            destination = "billing.invoice.primary")
    @JmsListener(
            id = "billing.invoice.retry.v1",
            destination = "billing.invoice.retry")
    public void handle(String invoiceId) {
        // Một Java method, hai listener endpoints độc lập.
    }
}
```

Hai annotation tạo **hai endpoints**, do đó cần **hai ID duy nhất**. Cùng Java method không có nghĩa chỉ tạo một container.

Tuy hai endpoints gọi chung handler, chúng có thể có:

- Destination và selector khác.
- Factory/concurrency khác.
- Lịch sử retry, DLQ và backlog khác ở broker.
- Các lifecycle trạng thái riêng khi lấy từ registry.

Việc một method xử lý được hai luồng **không tự bảo đảm** Java method hoặc shared dependencies thread-safe. Khi có concurrency, cần kiểm soát mutable state, idempotency và transaction.

### 8.1. Tránh ID biến thành tên method

Nếu đặt ID theo `com.example.billing.InvoiceHandler.processInvoice`, việc đổi tên package/class/method sẽ làm ID đổi dù logical endpoint không đổi. Nếu mục tiêu là ổn định qua refactor, nên dùng **business-facing ID** độc lập với cấu trúc Java.

Điều tương tự áp dụng cho default durable subscription name (Spring có thể tạo từ class/method nếu không chỉ rõ). Nhưng **subscription name** lại là broker-side identity; cần quản trị nó riêng, không suy ra explicit endpoint ID sẽ thay default subscription name.

## 9. Đăng ký listener endpoint bằng code

Khi endpoints không viết bằng annotation, Spring còn hỗ trợ `JmsListenerConfigurer` và `JmsListenerEndpointRegistrar`.

**File `DynamicBillingListenerConfig.java`:**

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;
import org.springframework.jms.config.SimpleJmsListenerEndpoint;

@Configuration
@EnableJms
public class DynamicBillingListenerConfig
        implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        SimpleJmsListenerEndpoint endpoint =
                new SimpleJmsListenerEndpoint();

        endpoint.setId("billing.manual.worker.v1");
        endpoint.setDestination("billing.manual.jobs");
        endpoint.setMessageListener(message -> {
            // Xử lý raw jakarta.jms.Message.
        });

        registrar.registerEndpoint(endpoint);
    }
}
```

Đây là **class cấu hình Spring JMS**, không chạy độc lập bằng JDK. Nó giả định ứng dụng đã có **default listener container factory** hoặc registrar đã được cấu hình factory phù hợp, cùng một broker/provider/destination. `SimpleJmsListenerEndpoint` thực hiện mô tả endpoint, không tự bảo đảm tạo Queue vật lý.

Điểm cần nhớ:

- `endpoint.setId(...)` giữ **cùng hợp đồng ID** như `@JmsListener(id=...)`.
- Registry dùng ID đó để quản lý lifecycle và tra cứu.
- Nếu code đăng ký hai endpoints cùng ID trong một registry, có thể bị từ chối.
- Với dynamic endpoints runtime do cấu hình tạo ra, cần chiến lược deterministic và allowlist để không biến ID thành tổ hợp ngẫu nhiên vô hạn.

### 9.1. Factory explicit khi đăng ký bằng code

Nếu ứng dụng có nhiều factories:

```java
// Trong configureJmsListeners(...) với factory đã được inject:
registrar.registerEndpoint(endpoint, specificJmsListenerContainerFactory);
```

Đây là một đoạn minh họa hợp đồng; `specificJmsListenerContainerFactory` phải là bean `JmsListenerContainerFactory<?>` hợp lệ trong scope, không có sẵn ngẫu nhiên. Tên factory/bean không phải ID endpoint; chúng có thể được chia sẻ cho nhiều endpoints.

### 9.2. Nếu cần tạo hàng trăm endpoint theo tenant

Hãy cân nhắc:

- Có thật cần **một JMS listener container và ID riêng cho từng tenant** hay nên dùng queue/selector/routing khác?
- Max connections/sessions/consumers của broker là bao nhiêu?
- Có giới hạn số endpoint và cleanup khi tenant bị xóa?
- ID được cấp phát lại theo một mapping ổn định, không phụ thuộc thứ tự lấy danh sách từ database?
- Nếu tenant name chứa ký tự không phù hợp cho metric/log hoặc thông tin nhạy cảm, đã chuẩn hóa/ẩn danh chưa?
- Việc restart có tạo ra **cùng tập logical IDs** không?
- Nếu topic durable theo tenant, subscription identity và retention được quản trị riêng chưa?

ID stable **giải quyết khả năng quản trị**, không giải quyết resource explosion, data isolation hay JMS ordering.

## 10. Kiểm thử hợp đồng ID khi application startup

Không cần đợi message thực được xử lý mới biết Spring có đăng ký ID đúng hay không.

### 10.1. Assertions cơ bản

Trong **integration test có Spring ApplicationContext** và JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jms.config.JmsListenerEndpointRegistry;

class BillingListenerIdsTest {

    @Autowired
    JmsListenerEndpointRegistry registry;

    @Test
    void expectedEndpointsAreRegistered() {
        assertTrue(registry.getListenerContainerIds()
                .contains("billing.invoice.worker.v1"));

        assertTrue(registry.getListenerContainerIds()
                .contains("billing.reconcile.worker.v1"));

        assertNotNull(registry.getListenerContainer(
                "billing.invoice.worker.v1"));
    }
}
```

Đây là **mảnh test class**, yêu cầu test runner tạo Spring context và dependency injection (ví dụ cấu hình Spring Test/Boot test). Chỉ viết `@Autowired` trong class JUnit thuần không được Spring quản lý thì field có thể null. Với môi trường test không có broker, có thể cấu hình listener factory **`setAutoStartup(false)`** để kiểm tra registry mà không khởi động consumption, rồi chạy integration tests riêng với provider thật.

Không assert số lượng ID chính xác nếu project còn nhiều endpoints hợp lệ khác, trừ khi test giới hạn một context tối giản. Hãy kiểm tra contract ID được mong đợi.

### 10.2. Test negative: duplicate IDs

Trong một application context test riêng, cố đăng ký hai endpoints cùng ID (qua annotations hoặc programmatic). Test cần xác minh **startup/registration fails** chứ không tự sửa trùng thành một tên tạm.

Đây là configuration error, nên fail-fast là hành vi tốt. Đừng nuốt `IllegalStateException` rồi tiếp tục chạy một listener thiếu kiểm soát.

### 10.3. Test về tính ổn định qua refactor

Trước khi rename handler class/method, lưu contract danh sách IDs mong muốn. Sau refactor:

1. Boot context test và lấy `getListenerContainerIds()`.
2. So sánh các **ID business-critical** với bộ kỳ vọng.
3. Kiểm tra destination/selector/factory đúng; chỉ check ID chưa đủ.
4. Đảm bảo operational scripts vẫn dùng keys cũ.
5. Với durable topic, kiểm tra thêm **subscription name/client ID** không bị thay vô ý.

Nếu annotation đã chỉ rõ `id`, refactor Java code thường không cần làm ID đổi. Đó là lợi ích chính của explicit stable IDs.

### 10.4. Kiểm tra absence rõ ràng

`registry.getListenerContainer("billing.invoice.worker.v1") == null` có thể do:

- Chưa bật `@EnableJms`/annotation post-processing.
- Handler chưa là Spring-managed bean hoặc nằm ngoài component scan.
- Annotation nằm ở lớp/method không được Spring phát hiện theo cấu trúc hiện tại.
- Endpoint id đã đổi do config placeholder/profile.
- Container/endpoint đăng ký qua **registry khác** với bean bạn đang inject.
- App context test không include configuration chứa listener.

Không kết luận “queue đã mất” chỉ từ giá trị null. Null ở đây nói rằng **registry hiện tại không có ID tương ứng**, chưa phải trạng thái broker.

## 11. Java 17 chạy độc lập: mô phỏng registry ổn định và phạm vi instance

Để ghi nhớ uniqueness và phạm vi registry mà không phải bật broker, ví dụ sau chạy **chỉ với JDK 17**. Nó mô phỏng một mapping `endpoint ID -> running state`, không implement Spring JMS, không gửi/nhận message và không thay thế kiểm thử trên provider.

Tạo file **`EndpointIdScopeDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public final class EndpointIdScopeDemo {

    static final class Registry {
        private final Map<String, Boolean> states = new LinkedHashMap<>();

        void register(String endpointId) {
            if (states.putIfAbsent(endpointId, true) != null) {
                throw new IllegalStateException(
                        "Duplicate endpoint: " + endpointId);
            }
        }

        void stop(String endpointId) {
            if (!states.containsKey(endpointId)) {
                throw new IllegalArgumentException(
                        "Unknown endpoint: " + endpointId);
            }
            states.put(endpointId, false);
        }

        boolean running(String endpointId) {
            return Boolean.TRUE.equals(states.get(endpointId));
        }

        Set<String> ids() {
            return states.keySet();
        }
    }

    public static void main(String[] args) {
        String invoice = "billing.invoice.worker.v1";

        Registry podA = new Registry();
        podA.register(invoice);
        podA.register("billing.reconcile.worker.v1");

        Registry podB = new Registry();
        podB.register(invoice); // Trùng A được vì registry khác.

        podA.stop(invoice);      // Chỉ thay đổi state ở pod A.

        boolean duplicateRejected = false;
        try {
            podA.register(invoice);
        } catch (IllegalStateException ex) {
            duplicateRejected = true;
        }

        System.out.println("A ids: " + podA.ids());
        System.out.println("A invoice running: " + podA.running(invoice));
        System.out.println("B invoice running: " + podB.running(invoice));
        System.out.println("Duplicate in A rejected: " + duplicateRejected);
    }
}
```

Biên dịch và chạy:

```bash
javac EndpointIdScopeDemo.java
java EndpointIdScopeDemo
```

**Stdout chính xác:**

```text
A ids: [billing.invoice.worker.v1, billing.reconcile.worker.v1]
A invoice running: false
B invoice running: true
Duplicate in A rejected: true
```

Giải thích:

- `LinkedHashMap` giữ thứ tự thêm để đầu ra `ids()` ổn định trong chương trình demo.
- Hai Registry objects có thể chứa **cùng ID** mà không xung đột, tương tự hai Spring contexts tách biệt.
- Trong cùng một Registry, đăng ký ID lần hai bị từ chối.
- Dừng A không làm B ngừng.
- Demo không mô phỏng JMS `@JmsListener`, Spring lifecycle, broker queue, transaction, connection recovery hoặc delivery semantics. Vì vậy không lấy stdout làm cam kết về timing hoặc trạng thái broker trong ứng dụng thật.

## 12. Quan sát và logging: dùng ID ổn định thế nào?

Một endpoint ID ổn định rất hữu ích như **logical label** trong metrics/tracing/logging, nhưng Spring không bảo đảm mọi telemetry system tự tạo tag theo ID nếu bạn chưa instrument nó.

### 12.1. Một bản ghi chẩn đoán nên phân biệt hai chiều

Ví dụ cấu trúc log:

```text
service=billing
environment=prod
instance=pod-a
endpointId=billing.invoice.worker.v1
destination=billing.invoice.jobs
state=RUNNING
pendingMessages=...
lastProcessedBusinessId=...
```

Các trường `pendingMessages` và trạng thái thực tế phải được lấy từ **broker/application metrics**, không phải suy ra từ endpoint registry. Gắn `endpointId` ổn định giúp dashboard truy vết đúng logical listener qua nhiều deploy; `instance` giúp phân biệt replicas.

### 12.2. Tránh label cardinality không kiểm soát

Không dùng:

```text
endpointId=billing.invoice.worker.<random-uuid>
endpointId=billing.invoice.worker.<timestamp>
endpointId=billing.invoice.worker.<every-request-id>
```

Đó là chuỗi minh họa, **không phải syntax annotation**. Random/time/request-specific IDs làm dashboards đầy labels mới, không thể so sánh xu hướng qua lần chạy và tạo chi phí metric cao.

Endpoint ID nên là **tập hữu hạn được quản trị** (một ID trên một logical consumer role), còn `requestId`/`JMSMessageID` thuộc trường trace/event tương ứng.

### 12.3. Lifecycle metric chưa đủ

Một dashboard chất lượng nên kết hợp:

- Registry ID count và presence: listener có được đăng ký không?
- Container lifecycle: có running không?
- Broker consumer count/connection status: container có thật sự nhận được quyền consume không?
- Queue depth hoặc durable subscription backlog: message có đang tồn không?
- Oldest message age: có vượt SLA không?
- Processed rate, failure/retry/DLQ counts: business handler có hoạt động hiệu quả không?
- Application instance: replica nào đang thiếu/bị stop?
- Business IDs/idempotency: xử lý không tạo effect trùng khi rollback.

**ID là khóa quan sát; nó không tự tạo health guarantee.**

## 13. Triển khai nhiều môi trường và tránh xung đột tên

### 13.1. Dev/staging/prod

Bạn có thể giữ cùng logical endpoint ID `billing.invoice.worker.v1` ở cả dev/staging/prod vì chúng là các Spring contexts khác nhau. Trong logging/metrics tập trung phải có `environment` label tách dữ liệu.

Không tự đổi ID theo environment nếu script chung kỳ vọng logical name ổn định và đã có label environment. Nếu tổ chức bắt buộc namespace ID theo environment, hãy nhất quán và kiểm thử resolver/registry của môi trường đó; hiểu rằng đó là quyết định quản trị riêng, không phải đòi hỏi Spring.

### 13.2. Two services sharing broker destination

Service Billing và service Audit có thể cùng nghe một queue, nhưng vẫn cần endpoint IDs diễn đạt vai trò khác nhau, ví dụ `billing.invoice.worker.v1` và `audit.invoice.worker.v1`. **Tuy nhiên**, trên queue, hai service sẽ cạnh tranh nhận message — không phải mỗi service nhận một bản. Nếu Audit cần mọi event, phải thiết kế Topic/subscriptions hoặc routing fan-out riêng.

ID ổn định không thay đổi semantics phân phối của queue/topic.

### 13.3. Blue/green hoặc canary deployment

Hai bản ứng dụng cùng chạy:

- Mỗi bản có registry riêng nên có thể có cùng logical endpoint ID.
- Nếu cả hai nghe một queue, chúng **cùng tham gia competing consumers**, trừ khi có selectors/routing cách ly.
- Nếu mục tiêu canary 5% lưu lượng, endpoint ID không tự làm traffic split; phải dùng cơ chế routing/deployment/broker phù hợp.
- Với durable Topic, việc có cùng `clientId`/subscription trong hai bản có thể vi phạm unshared subscription identity; cần plan shared durable hay riêng subscriptions.

Đừng cố giải bài toán canary bằng việc đổi ID ngẫu nhiên.

## 14. Quy trình đổi ID đã dùng trong production

Đổi một ID giống như đổi **API nội bộ cho vận hành**.

### Trước khi đổi

1. Tìm những nơi gọi `getListenerContainer("old-id")`, automation start/stop, test assertions, health checks, dashboard filters và log correlation.
2. Xác định endpoint logic có thực sự đổi contract hay chỉ là refactor.
3. Xác nhận không nhầm với việc đổi `subscription`, `destination` hoặc `clientId`.
4. Xem có nhiều application contexts/profiles cùng triển khai endpoint không.
5. Chọn ID mới theo convention và kiểm tra uniqueness với các endpoint còn lại.

### Khi triển khai

1. Đưa thay đổi code/config và các bên tiêu thụ ID vào cùng kế hoạch release.
2. Kiểm thử startup registry chứa ID mới, không trùng ID.
3. Cập nhật script quản trị để tra đúng ID trước khi gọi lifecycle operation.
4. Nếu rolling deployment, biết một thời gian cả bản cũ và mới chạy, dashboard cần theo dõi cả hai logical IDs.
5. Không xóa queue/durable subscription chỉ vì endpoint Spring đổi ID.

### Sau khi triển khai

1. Kiểm tra `getListenerContainerIds()` trên từng instance.
2. Kiểm tra broker consumer count và processing rate.
3. Xem error/retry/backlog/DLQ không tăng bất thường.
4. Xác nhận tất cả automation cũ đã ngừng dùng key đã đổi.
5. Ghi rõ lý do đổi trong runbook để tránh lần refactor sau lại thay ID không chủ ý.

### Khi **không nên** đổi

Nếu chỉ đổi class từ `InvoiceJobListener` thành `InvoiceProcessor` hoặc đổi method từ `consume` thành `process`, nhưng logical consumer vẫn là worker xử lý invoice jobs, **giữ nguyên** `billing.invoice.worker.v1`. Đó chính là mục đích của stable endpoint ID.

## 15. Các lỗi phổ biến và cách sửa

**Lỗi 1 — “Bỏ trống id, Spring vẫn có ID, nên nó luôn cố định.”**

Sai. Có ID tự sinh nhưng không có hợp đồng ổn định qua refactor/registration order. Với nhu cầu vận hành, khai báo `id` rõ.

**Lỗi 2 — “id chính là queue name.”**

Sai. `id` là key Spring registry; `destination` quyết định Queue/Topic. Có thể trùng chuỗi nhưng chúng là hai khái niệm.

**Lỗi 3 — “Hai methods cùng id thì Spring sẽ chia tải trên cùng container.”**

Sai. Registry từ chối ID trùng trong cùng context. Muốn concurrency, cấu hình container `concurrency`; muốn nhiều endpoint, dùng nhiều IDs.

**Lỗi 4 — “Mỗi Kubernetes pod phải có một id khác để broker không từ chối.”**

Sai về `@JmsListener.id`. Registry nằm local mỗi pod; cùng logical ID là hợp lý. Broker-side `clientId`/durable subscription identity có quy tắc khác.

**Lỗi 5 — “@Component bean name được tự dùng làm id.”**

Không nên giả định. Bean handler và listener container là hai đối tượng/namespace khác nhau.

**Lỗi 6 — “Đổi id giúp xoá backlog queue.”**

Sai. Backlog là state broker/destination. Đổi id Spring không purge, redrive hay reset Queue.

**Lỗi 7 — “Đổi id bằng đổi durable subscription name là cùng một thao tác.”**

Sai. `subscription` và `clientId` là broker-facing; đổi sai có thể làm subscription mới không đọc pending cũ.

**Lỗi 8 — “getListenerContainer(id) luôn trả container.”**

Sai. Nó có thể trả `null` nếu ID không tồn tại trong registry hiện tại; phải kiểm tra.

**Lỗi 9 — “stop(id) dừng toàn hệ thống.”**

Sai. `stop()` trên local container chỉ ảnh hưởng instance đang thao tác; các replicas khác vẫn có thể consume.

**Lỗi 10 — “isRunning=true là broker đang healthy.”**

Không đủ. Cần metrics về connectivity, backlog, actual deliveries, failures và recovery.

**Lỗi 11 — “ID phải chứa hash của build để biết đang chạy version nào.”**

Không phù hợp với stable ID. Build version nên là metadata/deployment label riêng; endpoint ID đại diện logical role lâu dài.

**Lỗi 12 — “Hai @JmsListener trên cùng một method chỉ cần một id.”**

Sai. Mỗi annotation đăng ký endpoint riêng, cần ID riêng.

**Lỗi 13 — “Đặt id trùng với tên factory thì Spring lấy factory đó.”**

Sai. `containerFactory` là bean name để chọn factory, không liên quan `id`.

**Lỗi 14 — “Đổi method/class name không ảnh hưởng gì khi thiếu explicit id.”**

Không chắc. Auto-ID có thể phụ thuộc thứ tự đăng ký; default subscription name còn có thể dựa trên fully qualified class/method. Đặt rõ endpoint ID và subscription identity khi có yêu cầu ổn định.

**Lỗi 15 — “Có ID ổn định tức xử lý message exactly once.”**

Sai. Delivery, ack/transaction, idempotency, retry và business correctness là mối quan tâm khác.

**Lỗi 16 — “Có thể cho bất kỳ HTTP client nào truyền id để stop listener.”**

Nguy hiểm. Các thao tác start/stop là quyền vận hành; phải giới hạn danh sách endpoints, xác thực/ủy quyền, audit và có cách rollback.

## 16. Checklist code review và vận hành

Trước khi merge thêm một `@JmsListener`:

- [ ] Endpoint có `id` explicit, dễ hiểu và **ổn định** qua deploy?
- [ ] ID có duy nhất với tất cả annotated/programmatic endpoints trong registry đó?
- [ ] ID đại diện logical listener role, không phụ thuộc thứ tự đăng ký, UUID hoặc timestamp?
- [ ] Nếu có nhiều replicas, đã phân biệt logical ID với instance identity trong monitoring?
- [ ] Đã tách `id` khỏi `destination`, `containerFactory`, `subscription`, JMS `clientId`?
- [ ] Listener có đúng Queue/Topic semantics và broker resource?
- [ ] Nhiều listeners cùng một Queue có phải intended competing consumers không?
- [ ] Nếu nhiều annotations trên một method, mỗi annotation có ID riêng?
- [ ] Nếu ID lấy từ placeholder, giá trị cuối của mọi profile có nonblank và không trùng?
- [ ] Startup integration test xác nhận registry chứa các IDs quan trọng?
- [ ] Có unit/integration test negative cho duplicate id và missing id lookup?
- [ ] Có điểm tra cứu registry rõ ràng để quản lý lifecycle thay vì inject container như bean thường?
- [ ] API quản trị start/stop (nếu có) được bảo vệ và audit?
- [ ] Trước khi stop Topic, có xem non-durable/durable subscription và retention behavior?
- [ ] Health check có dựa trên broker/app metrics, không chỉ `isRunning`?
- [ ] Mỗi lần đổi ID có migration plan cho scripts, alerts, dashboards và runbooks?
- [ ] Đổi ID không vô tình đổi durable subscription name/clientId?
- [ ] Không trộn lẫn endpoint ID với JMSMessageID/JMSCorrelationID/idempotency key?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `@JmsListener(id="billing.worker", destination="billing.jobs")`: hai String mô tả cái gì?

**Đáp án:** `id` là tên endpoint container trong Spring registry; `destination` là địa chỉ JMS Queue/Topic mà listener nhận.

**Câu 2.** Tại sao không nên viết script `getListenerContainer("org.springframework.jms.JmsListenerEndpointContainer#0")`?

**Đáp án:** ID này có thể là implementation-generated và thứ tự registration có thể thay đổi qua code/deploy; không có hợp đồng ổn định cho logical method.

**Câu 3.** Hai listener methods cùng ID trong một ApplicationContext có hợp lệ không?

**Đáp án:** Không. Registry từ chối duplicate ID vì mỗi ID phải chỉ tới đúng một container trong registry đó.

**Câu 4.** Hai replicas Spring khác nhau cùng khai báo `id="billing.invoice.worker.v1"` có xung đột registry không?

**Đáp án:** Không, nếu là hai registries độc lập. Nhưng JMS clientId/durable identity có quy tắc riêng.

**Câu 5.** ID endpoint có cần trùng với `@Component` bean name không?

**Đáp án:** Không. Bean handler và container endpoint có namespace/trách nhiệm khác nhau.

**Câu 6.** Muốn dừng listener có ID biết trước, API nào phù hợp?

**Đáp án:** `JmsListenerEndpointRegistry.getListenerContainer(id)` rồi kiểm tra null và gọi `stop()` trên container local.

**Câu 7.** Dừng listener A có dừng listener trên pod B không?

**Đáp án:** Không. Registry chỉ biết container trong ApplicationContext của mình.

**Câu 8.** `getListenerContainer(id)` trả null có chứng minh broker queue không tồn tại không?

**Đáp án:** Không. Nó chỉ nói registry không có endpoint với ID đó.

**Câu 9.** `isRunning() == true` có chứng minh service đã xử lý message không?

**Đáp án:** Không. Cần broker connectivity, consumer metrics, error logs và business completion.

**Câu 10.** Một method gắn hai `@JmsListener` tới hai destinations; cần mấy ID?

**Đáp án:** Hai endpoint IDs riêng nếu muốn quản trị rõ và tránh trùng.

**Câu 11.** Thay ID từ `invoice.worker.v1` sang `invoice.worker.v2` có tự di chuyển pending queue messages không?

**Đáp án:** Không. Đó là thay đổi key quản trị trong Spring; queue state trên broker là chuyện khác.

**Câu 12.** Một durable topic consumer có `id="audit.v1"` nhưng chưa cấu hình subscription identity đúng. ID đó có tự biến nó thành durable subscriber không?

**Đáp án:** Không. Cần factory settings, subscription name và JMS connection identity phù hợp, riêng với endpoint ID.

**Câu 13.** Vì sao không nên thêm build number vào `id`?

**Đáp án:** Nó làm key đổi mỗi deploy, phá scripts/dashboards/test đã dựa vào logical ID ổn định. Build number nên là label metadata riêng.

**Câu 14.** Khi một endpoint đã đổi class/method Java nhưng giữ contract, nên xử lý ID thế nào?

**Đáp án:** Giữ nguyên ID explicit để tránh thay key của các công cụ vận hành.

**Câu 15.** Nếu muốn xem tất cả IDs của annotated containers trong registry, dùng API nào?

**Đáp án:** `registry.getListenerContainerIds()`; Set không bảo đảm thứ tự, sort nếu cần hiển thị.

**Câu 16.** Tại sao ID ổn định chưa đủ để quản lý nhiều replicas an toàn?

**Đáp án:** ID là local registry key; phải ghi rõ target instance và bảo đảm quyền quản trị/điều phối fleet.

**Câu 17.** `JMSMessageID` có dùng để lookup listener container không?

**Đáp án:** Không. Nó định danh message do JMS provider gửi, không định danh listener.

**Câu 18.** Khi thêm listener vào code, bạn cần kiểm tra gì trước khi quyết định ID?

**Đáp án:** Logical role, uniqueness trong registry, destination semantics, compatibility với runbooks/scripts, và nguy cơ đổi subscription identity nếu là Topic durable.

## Kết luận

**`@JmsListener(id = "...")` định danh một Spring JMS listener endpoint/container**, dùng làm key trong `JmsListenerEndpointRegistry`. Nếu ứng dụng cần vận hành, giám sát hoặc kiểm thử theo tên endpoint, hãy **đặt ID tường minh, ổn định theo logical role và duy nhất trong mỗi registry** thay vì dựa vào auto-generated ID.

Giữ rõ ba ranh giới:

1. **Spring endpoint identity:** `id` → tra cứu container, lifecycle, code/tests/observability.
2. **JMS transport identity:** `destination`, `subscription`, JMS `clientId` → địa chỉ và quyền nhận message trên broker.
3. **Message/business identity:** `JMSMessageID`, `JMSCorrelationID`, business request ID → trace, request/reply và idempotency.

Một stable endpoint ID hỗ trợ **khả năng quản trị tốt hơn**, nhưng không thay thế thiết kế queue/topic, durable subscriptions, transaction, broker monitoring hay bảo mật các thao tác quản trị.

### Tài liệu tham khảo chính thức

1. [Spring Framework – @JmsListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListener.html) — `id()` là unique container identifier, auto-generated ID nếu bỏ trống; `destination`/`subscription`/`containerFactory` là các thuộc tính khác.
2. [Spring Framework – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — `@EnableJms`, annotated listener infrastructure, repeatable `@JmsListener` và programmatic endpoint registration.
3. [Spring Framework – JmsListenerEndpointRegistry API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html) — `getListenerContainer(id)`, `getListenerContainerIds()`, registration/lifecycle và container management.
4. [Spring Framework – MessageListenerContainer API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/MessageListenerContainer.html) — lifecycle `start()`/`stop()`/`isRunning()` và JMS container abstraction.
5. [Spring Framework – JmsListenerAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListenerAnnotationBeanPostProcessor.html) — annotation discovery, endpoint registration và embedded value resolution.
6. [Spring Framework – DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html) — connection factory, concurrency, transactions và container creation.
7. [Spring Framework – JmsListenerConfigurer API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/annotation/JmsListenerConfigurer.html) — configuration hook để đăng ký endpoints bằng code.
8. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — JMS client identifiers, queue/topic semantics, durable/shared subscriptions, message headers; những định danh này **khác** endpoint ID của Spring.
