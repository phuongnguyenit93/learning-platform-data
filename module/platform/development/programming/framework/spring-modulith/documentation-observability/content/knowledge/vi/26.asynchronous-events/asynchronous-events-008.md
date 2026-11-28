# Phân biệt event được publish với event được xử lý

## 1. Đặt vấn đề: một dòng log không chứng minh nghiệp vụ đã chạy

Trong chương **Sự kiện bất đồng bộ** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, ta dùng Spring Modulith để quan sát sự tương tác giữa các application module trong ứng dụng Spring Boot. Module graph cho thấy các ranh giới kiến trúc, còn sự kiện, metrics, tracing và context propagation giúp kiểm tra những tương tác đó **khi hệ thống đang vận hành**.

Giả sử module `orders` xác nhận đơn hàng, sau đó phát sự kiện `OrderConfirmed`. Module `notifications` lắng nghe để tạo tác vụ gửi email; module `inventory` lắng nghe để giữ hàng. API trả `200 OK` và log xuất hiện:

~~~text
11:00:00.100 [http-nio-8080-exec-1] INFO Order confirmed: ORD-42
11:00:00.102 [http-nio-8080-exec-1] INFO Published OrderConfirmed: ORD-42
~~~

Ta **chưa thể kết luận** email đã gửi, kho đã giữ hàng, hay thậm chí listener đã được gọi. Với xử lý bất đồng bộ, request có thể kết thúc trong khi listener còn xếp hàng, đang chạy hoặc đã thất bại.

**Nguyên tắc trọng tâm:**

> **Published** nói về hành động phát thông điệp trong ứng dụng; **processed** nói về việc một listener cụ thể đã xử lý thông điệp ấy. Chúng khác thời điểm, khác thành phần chịu trách nhiệm và khác loại bằng chứng kiểm chứng.

Kết thúc bài, bạn có thể:
- Chỉ ra sự khác biệt giữa `publishEvent(...)`, publication được lưu trong registry, listener bắt đầu chạy, listener hoàn tất và kết quả nghiệp vụ thực tế.
- Giải thích vai trò của transaction, `@TransactionalEventListener`, `@Async` và `@ApplicationModuleListener`.
- Dùng Event Publication Registry để xác định sự kiện còn chờ, xử lý lỗi và thử gửi lại; hiểu khác biệt giữa Spring Modulith 1.x và 2.x.
- Phân biệt phép đo `module.events.published` với metric cho xử lý thành công; sử dụng log, Actuator, trace và kiểm thử phù hợp.
- Thiết kế handler có tính idempotent để chịu được trường hợp gọi lại sau lỗi.

## 2. Năm mốc của một event: đừng gộp làm một

Cần đặt tên chính xác cho từng mốc:

| Mốc | Điều đã xảy ra | Điều **chưa thể** suy ra |
| --- | --- | --- |
| **1. Publish được gọi** | Đoạn mã gọi `ApplicationEventPublisher.publishEvent(event)`. | Transaction sẽ commit; có listener quan tâm; xử lý đã thành công. |
| **2. Publication được ghi nhận** | Nếu đã cấu hình Event Publication Registry, hệ thống lưu bản ghi ứng với mỗi transactional listener phù hợp, trong transaction phát sinh sự kiện. | Listener đã bắt đầu hoặc đã hoàn tất. |
| **3. Listener nhận và bắt đầu** | Dispatcher/async executor chuyển event đến một listener; mã xử lý bắt đầu thực thi. | Mã không ném lỗi, transaction của listener commit, hoặc tác dụng bên ngoài đã hoàn tất. |
| **4. Listener hoàn tất** | Listener trả về thành công; registry ghi nhận completion theo cơ chế cấu hình. | Hệ thống bên ngoài chắc chắn đã hoàn tất một công việc vốn có thể tiếp diễn sau lời gọi. |
| **5. Kết quả nghiệp vụ được xác nhận** | Có bằng chứng như bản ghi giữ hàng đã commit, email job đã được chấp nhận hoặc phản hồi xác nhận cuối cùng từ dịch vụ ngoài. | Mọi subscriber khác cũng đã hoàn tất; cùng event chỉ chạy đúng một lần. |

**Chú ý về từ “publish”:** đây là tên thao tác của Spring. Nếu ghi log trước khi transaction commit, log chỉ cho thấy *đã gọi publish*; nó không phải bằng chứng rằng dữ liệu đơn hàng và publication đã commit bền vững. Đặc biệt, một transaction bị rollback vẫn có thể để lại log `publishEvent` trước đó.

**Chú ý về từ “processed”:** luôn xác định **listener nào** và **đến mức thành công nào**. Sự kiện có thể được module `inventory` xử lý thành công, trong khi module `notifications` vẫn lỗi. Vì vậy không nên có một cờ “event đã xử lý” chung cho mọi consumer.

### Sơ đồ thời gian

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders service
    participant TX as DB transaction
    participant R as Event Publication Registry
    participant A as Async executor
    participant L as Notifications listener
    participant N as Notifications DB

    O->>TX: Cập nhật order = CONFIRMED
    O->>O: publishEvent(OrderConfirmed)
    O->>R: Ghi publication cho listener
    Note over TX,R: Cùng transaction gốc nếu cấu hình registry phù hợp
    TX-->>O: COMMIT
    Note over O,L: Publish + commit không có nghĩa đã xử lý
    R-->>A: Sau commit: dispatch event
    A->>L: Gọi @ApplicationModuleListener
    L->>N: Ghi mail job (transaction riêng)
    N-->>L: COMMIT
    L-->>R: Listener hoàn tất
    R->>R: Ghi nhận completion
    Note over R,N: Mail job đã được lưu, chưa đồng nghĩa email đến hộp thư
~~~

Nhánh lỗi cần nhớ:
- Nếu transaction gốc **rollback**, transactional listener mặc định ở pha `AFTER_COMMIT` sẽ không chạy và publication được ghi trong cùng transaction cũng bị rollback.
- Nếu transaction gốc **commit** nhưng listener lỗi, thay đổi đơn hàng đã được giữ lại. Listener thất bại không đảo ngược transaction gốc.
- Nếu process chết **sau commit nhưng trước khi listener chạy**, không có durable publication registry thì event in-memory có nguy cơ mất.
- Nếu process chết **sau khi listener tạo hiệu ứng nhưng trước khi completion được lưu**, lần thử lại có thể tạo hiệu ứng trùng lặp nếu consumer thiếu cơ chế idempotency.

## 3. Không phải mọi Spring event đều tự động chạy bất đồng bộ

Hành vi phụ thuộc vào cách đăng ký listener và cấu hình event multicaster.

| Kiểu listener | Thời điểm / luồng thường gặp | Hệ quả |
| --- | --- | --- |
| `@EventListener` thông thường | Đồng bộ trong luồng publisher với multicaster mặc định. | Listener có thể chạy xong hoặc ném exception trước khi `publishEvent` trả về. Không có mặc định “xếp hàng nền”. |
| `@TransactionalEventListener` (mặc định `AFTER_COMMIT`) | Được kích hoạt khi transaction gốc commit; **không tự bất đồng bộ**. | Không chạy sau rollback; nếu không có transaction đang hoạt động thì mặc định không gọi listener (trừ khi chọn `fallbackExecution`). |
| `@Async` + `@TransactionalEventListener` | Lập lịch xử lý sang executor sau sự kiện commit, khi hỗ trợ `@Async` được bật. | Publisher không chờ listener xử lý xong; cần quản trị executor, lỗi và retry. |
| `@ApplicationModuleListener` | Shortcut của Spring Modulith cho transactional event listener **async** chạy trong transaction mới (`REQUIRES_NEW`). | Phù hợp tích hợp giữa các module nhưng vẫn cần Event Publication Registry nếu muốn theo dõi/khôi phục publication một cách bền vững. |

`@ApplicationModuleListener` tương đương về ý nghĩa với bộ annotation:

~~~java
@Async
@Transactional(propagation = Propagation.REQUIRES_NEW)
@TransactionalEventListener
void on(OrderConfirmed event) {
    // Xử lý độc lập với transaction gốc.
}
~~~

Trong thực tế, dùng annotation tắt `@ApplicationModuleListener` để diễn tả rõ đây là điểm tích hợp giữa các application module.

**Không nhầm hai loại thành công:**

1. `publishEvent(...)` trả về mà không báo lỗi **không** có nghĩa mọi async listener thành công.
2. Listener hoàn tất thành công theo framework **không** có nghĩa một hệ thống bên ngoài (email, Kafka consumer, cổng thanh toán) đã hoàn tất quy trình của nó. Phải định nghĩa riêng tiêu chí thành công và bằng chứng tương ứng.

## 4. Ví dụ Spring Modulith: xác nhận đơn và tạo email job

Bối cảnh có hai application module:

~~~text
com.acme.shop
├── orders
│   ├── OrderService.java
│   └── OrderRepository.java
│   └── api
│       └── OrderConfirmed.java
└── notifications
    ├── OrderNotificationListener.java
    └── MailJobRepository.java
~~~

Event được đặt trong API công khai của module `orders` để module `notifications` có thể phụ thuộc vào kiểu event, trong khi không phải truy cập trực tiếp vào repository hoặc chi tiết nội bộ của `orders`. Module graph giúp tài liệu hóa hướng phụ thuộc này; cấu trúc module **không tự đảm bảo** listener đã xử lý.

### 4.1. Khai báo event và publish trong transaction gốc

~~~java
// com.acme.shop.orders.api.OrderConfirmed
package com.acme.shop.orders.api;

import java.util.UUID;

public record OrderConfirmed(UUID eventId, UUID orderId) {}
~~~

~~~java
// com.acme.shop.orders.OrderService
package com.acme.shop.orders;

import com.acme.shop.orders.api.OrderConfirmed;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();
        orders.save(order);

        // Đây là lời gọi publish trong transaction, chưa phải kết quả xử lý.
        events.publishEvent(new OrderConfirmed(UUID.randomUUID(), orderId));
    }
}
~~~

Giả định `Order`, `OrderRepository` là các thành phần JPA đã có trong ứng dụng. Sự kiện chỉ mang các định danh cần thiết, không giữ entity JPA đang quản lý, connection hoặc đối tượng phụ thuộc vào request scope. Sau khi commit, listener dùng `orderId` để lấy lại dữ liệu cần thiết trong transaction riêng nếu cần.

**Lưu ý:** nếu `confirm(...)` được gọi trực tiếp từ một phương thức khác trong cùng bean mà không đi qua Spring proxy, `@Transactional` có thể không có hiệu lực. Khi đó giả định “publish nằm trong transaction gốc” không còn đúng. Kiểm thử phải chứng minh transaction thực sự hoạt động.

### 4.2. Lắng nghe ở module khác

~~~java
// com.acme.shop.notifications.OrderNotificationListener
package com.acme.shop.notifications;

import com.acme.shop.orders.api.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderNotificationListener {

    private final MailJobRepository jobs;

    public OrderNotificationListener(MailJobRepository jobs) {
        this.jobs = jobs;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        // Phần repository cần UNIQUE(eventId, consumer) để tránh job trùng.
        // Đây là một API nghiệp vụ minh họa do ứng dụng tự triển khai.
        jobs.insertIfAbsent(event.eventId(), "notifications", event.orderId());
    }
}
~~~

`insertIfAbsent(...)` là **phương thức minh họa**, không phải API sẵn có của Spring Data. Hãy hiện thực nó bằng thao tác cơ sở dữ liệu nguyên tử (ví dụ `INSERT ... ON CONFLICT DO NOTHING` trên hệ quản trị hỗ trợ) và ràng buộc unique cho cặp `(eventId, consumer)`. Không chỉ dùng `existsBy...` rồi `save(...)` vì hai lần xử lý song song có thể cùng thấy “chưa tồn tại”.

Nếu `on(...)` trả về thành công, publication tương ứng có thể được đánh dấu hoàn tất. Điều đã được đảm bảo ở ví dụ này là **lệnh tạo mail job chạy thành công trong transaction của listener**. Việc gửi email thật sẽ là bước khác của worker xử lý `MailJob`; cần theo dõi trạng thái riêng như `QUEUED → SENT/FAILED`.

### 4.3. Nền tảng cấu hình tối thiểu

Với Gradle, minh họa các thành phần liên quan (phiên bản được quản lý bằng BOM Spring Modulith tương thích với phiên bản Spring Boot của dự án):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.modulith:spring-modulith-starter-core'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-jdbc'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}
~~~

Lựa chọn `spring-modulith-starter-jdbc` ở đây lưu publication bằng JDBC ngay cả khi mô hình nghiệp vụ dùng JPA. Có thể thay bằng `spring-modulith-starter-jpa` theo yêu cầu triển khai; chỉ chọn storage phù hợp, cấu hình transaction/serializer và chạy migration schema tương ứng. Việc chỉ thêm `spring-modulith-starter-core` **chưa đủ** để có event publication log bền vững.

Cấu hình executor cho các listener async và bảo đảm `@Async` được kích hoạt theo quy ước ứng dụng. Ví dụ khai báo rõ tại application config:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
class AsyncEventConfiguration {
    // Đặt giới hạn pool, queue và chính sách khi quá tải trong triển khai thực tế.
}
~~~

Ở hệ thống đang vận hành, đặt giới hạn thread/queue, cơ chế từ chối khi quá tải và quy trình dừng ứng dụng có kiểm soát. Nếu background executor tắc nghẽn hoặc bị tắt sớm, không thể suy ra tất cả các publication đều sẽ được xử lý ngay.

## 5. Event Publication Registry làm được gì?

Spring Modulith có **Event Publication Registry** tích hợp cơ chế publish sự kiện của Spring. Với persistence starter và transaction phù hợp, framework tạo **một publication cho mỗi transactional listener được đăng ký** khi event được phát. Các publication này được lưu cùng transaction gốc để có thể xác định listener nào chưa xử lý xong.

Ví dụ `OrderConfirmed(E-77)` được phát với hai listener:

| Consumer | Trạng thái quan sát tại một thời điểm | Ý nghĩa |
| --- | --- | --- |
| `notifications.on(OrderConfirmed)` | `COMPLETED` | Listener notifications đã kết thúc thành công. |
| `inventory.on(OrderConfirmed)` | `FAILED` / incomplete | Listener inventory chưa hoàn tất; cần khôi phục hoặc xử lý lỗi. |

Không nên đếm “một event = một publication” nếu event có nhiều listener. Một event phát ra có thể tạo nhiều bản ghi trong registry.

### 5.1. Lifecycle từ Spring Modulith 2.0

Kể từ **Spring Modulith 2.0**, `EventPublication.Status` cho phép phân biệt các trạng thái chi tiết:

~~~mermaid
flowchart TD
    A[PUBLISHED - đã ghi nhận, chờ xử lý] --> B[PROCESSING - listener đang chạy]
    B -->|thành công| C[COMPLETED]
    B -->|ném exception| D[FAILED]
    D -->|gửi lại| E[RESUBMITTED]
    E --> B
    D -->|chính sách dừng, từ 2.2| F[ABANDONED]
~~~

| Status | Cách hiểu đúng |
| --- | --- |
| `PUBLISHED` | Publication đã lưu và đang chờ/bắt đầu được chuyển đến listener. **Không phải xử lý xong.** |
| `PROCESSING` | Listener đã nhận lượt xử lý; có thể vẫn đang chạy, bị treo hoặc process đã chết. |
| `COMPLETED` | Lần gọi listener thành công; dữ liệu completion được lưu theo chế độ cấu hình. |
| `FAILED` | Listener phát sinh exception hoặc publication được đánh dấu lỗi theo chính sách stale. |
| `RESUBMITTED` | Publication lỗi đã được đưa vào quy trình thử lại, chưa bảo đảm hoàn tất. |
| `ABANDONED` | Từ Modulith **2.2**, publication đã bị từ bỏ theo chính sách sau lỗi; trạng thái này khác với thành công. |

Phiên bản **1.x** chủ yếu dựa vào publication đã/chưa có completion date và các API xử lý incomplete publications. Không áp các enum/status mới vào hệ thống 1.x một cách máy móc. Trước khi viết SQL giám sát hoặc integration với API registry, xác minh đúng major/minor version và schema đang triển khai.

**Quy tắc quan trọng:** nếu listener bắt exception rồi ghi log và trả về bình thường, framework có thể xem listener đã thành công và đánh dấu `COMPLETED`. Khi không thể hoàn tất công việc cần thiết, phải để lỗi đi ra ngoài hoặc dùng cơ chế ghi nhận trạng thái thất bại rõ ràng theo thiết kế của hệ thống.

### 5.2. Khi nào registry bảo vệ được sự kiện?

Trong kịch bản bình thường:

1. Transaction của `orders` cập nhật đơn và ghi publication.
2. Transaction **commit**: cả thay đổi đơn hàng và publication tồn tại.
3. Listener xử lý sau commit và tự thực thi trong transaction khác.
4. Khi listener thành công, registry ghi completion theo cấu hình.

Nếu ứng dụng chết sau bước 2 nhưng trước bước 4, publication còn tồn tại để kiểm tra, khôi phục và thử xử lý lại theo khả năng framework/cấu hình. Registry **không** tự biến mọi listener thành xử lý “exactly once”; cơ chế retry có thể khiến listener chạy nhiều lần.

Nếu không có registry/persistence tương ứng, một async event được dispatch trong bộ nhớ có thể mất khi tiến trình chết. **Có log “Published” không đủ để khẳng định event đã được lưu bền vững.**

### 5.3. Gửi lại và chọn chính sách completion

Một số cấu hình minh họa:

~~~yaml
spring:
  modulith:
    events:
      # Mặc định lưu completion dưới dạng UPDATE.
      completion-mode: update

      # Khôi phục outstanding lúc restart chỉ khi phù hợp topology.
      republish-outstanding-events-on-restart: false
~~~

Ba cách ghi nhận completion thường gặp từ Spring Modulith 1.3:

- `UPDATE` (mặc định): lưu thời điểm hoàn tất trên publication; cần quy trình dọn bản ghi cũ.
- `DELETE`: xóa publication sau khi hoàn tất; không thể dùng registry để truy xuất lịch sử completed tương ứng.
- `ARCHIVE`: di chuyển sang vùng lưu trữ riêng khi hoàn tất, hỗ trợ audit theo cơ chế lưu trữ.

Để chủ động khôi phục, Spring Modulith cung cấp `IncompleteEventPublications`; từ **2.0** có thêm `FailedEventPublications` và `ResubmissionOptions` để lọc/thử lại riêng publication lỗi, giới hạn batch và độ tuổi. Đặc biệt trong triển khai nhiều instance, **không tùy tiện bật** `republish-outstanding-events-on-restart` cho mọi node: node này có thể thử lại trong khi node khác vẫn đang xử lý. Cần phối hợp ownership, chính sách stale, concurrency và idempotency.

Từ 2.0, cấu hình `spring.modulith.events.staleness.*` hỗ trợ đánh dấu những publication mắc kẹt ở `PUBLISHED`, `PROCESSING` hoặc `RESUBMITTED` thành `FAILED` sau ngưỡng tuổi tương ứng. **Mặc định các ngưỡng stale bằng 0**, nên monitor không tự đánh dấu lỗi nếu chưa bật. Đừng lẫn trạng thái `PROCESSING` quá lâu với “đã xử lý thành công”.

## 6. Quan sát: metric publish không phải metric processed

Spring Modulith hỗ trợ quan sát tương tác module bằng Micrometer Observation/Tracing; `spring-modulith-starter-insight` cung cấp tích hợp actuator và observability theo bộ phụ thuộc phù hợp. Đây là khả năng quan sát **runtime** bổ sung cho sơ đồ ranh giới/module graph.

### 6.1. Metric tích hợp sẵn đo điều gì?

Theo tài liệu observability, Spring Modulith tạo các counter:

- `module.events.published`: tổng các event publication được phát trong ứng dụng (có các tag như kiểu event và module).
- `module.events.published.<moduleIdentifier>.<simpleEventTypeName>`: counter riêng theo loại event.

Các counter này trả lời **“Ứng dụng đã phát bao nhiêu event?”**, không trả lời **“Bao nhiêu listener xử lý thành công?”**. Counter publish cũng không tự chứng minh transaction của nghiệp vụ đã commit hay publication có bản ghi bền vững. Một event nhiều consumer càng khiến phép so sánh trực tiếp số published với completed trở nên sai.

Ví dụ:

~~~text
module.events.published{module.event.type="OrderConfirmed"} 100
registry notifications completed = 98
registry inventory completed = 94
registry inventory failed = 3
registry inventory processing/pending = 3
~~~

Đây chỉ là dữ liệu minh họa. Không được kết luận “đã xử lý 98/100 event” cho toàn hệ thống: mỗi consumer có trạng thái riêng, các event có thể đang chạy, đã retry, hoặc bị rollback. Khi dựng dashboard thật, lọc cùng khoảng thời gian, cùng event type/consumer và hiểu rõ retention/mode của registry.

### 6.2. Đo riêng các mốc processed

Để biết kết quả, nên đo ít nhất:

| Chỉ số vận hành | Mục đích | Nguồn gợi ý |
| --- | --- | --- |
| Tổng event phát theo module/loại | Tốc độ xuất hiện sự kiện | `module.events.published` |
| Publication đang chờ/đang chạy/lỗi theo listener | Phát hiện backlog và lỗi | Event Publication Registry, query hoặc API giám sát được kiểm soát |
| Tuổi của publication chưa hoàn tất | Cảnh báo xử lý chậm | Timestamp trong registry và thời gian hiện tại |
| Số lần thử xử lý, số lần thử lại | Phát hiện poison event | Completion attempts / logs và custom metrics |
| Listener xử lý thành công/thất bại | Đo kết quả của consumer | Custom counters/timers trong listener và xử lý lỗi |
| Hiệu ứng nghiệp vụ đã commit/được xác nhận | Đo outcome thực | Bảng MailJob, trạng thái inventory, acknowledgment từ bên ngoài |

Ví dụ mã minh họa tạo metric **nghiệp vụ** sau khi transaction tạo job đã commit: không chỉ đếm ngay tại lúc bắt đầu handler rồi gọi đó là “success”. Nếu cần độ tin cậy khi cập nhật cả DB và metric, dùng DB làm nguồn sự thật để tính `processed`; metric in-memory phục vụ quan sát gần thời gian thực và có thể lệch khi tiến trình chết.

~~~java
// Minh họa ý tưởng quan sát; cách lấy observation/transaction event
// phụ thuộc cấu hình thực tế của ứng dụng.
@ApplicationModuleListener
void on(OrderConfirmed event) {
    // 1. Ghi job một cách idempotent trong transaction của listener.
    // 2. Nếu lỗi: ném exception để registry ghi nhận chưa hoàn tất.
    // 3. Khi thành công: log sự kiện theo eventId/consumer.
    jobs.insertIfAbsent(event.eventId(), "notifications", event.orderId());
    log.info("event.listener.succeeded type=OrderConfirmed consumer=notifications eventId={}",
        event.eventId());
}
~~~

Log `listener.succeeded` là tín hiệu rất hữu ích để chẩn đoán, nhưng nếu log phát ra **trước commit** và transaction sau đó thất bại thì log cũng chưa phải xác nhận cuối cùng. Quan sát chính xác phải dựa thêm vào registry và dữ liệu nghiệp vụ đã commit.

### 6.3. Tracing và context propagation

Một trace có thể chứa span cho lệnh HTTP xác nhận đơn hàng và span xử lý ở application module khác. Spring Modulith có thông tin như `module.name`, `module.method`, `module.invocation-type` cho các tương tác được instrument. Tuy nhiên:

- Async listener chạy trên thread khác; MDC, security context, baggage và tracing context **không tự bảo đảm** truyền qua mọi loại executor.
- Cần kiểm tra cấu hình Micrometer Context Propagation/TaskDecorator và mức hỗ trợ của Spring Boot/Modulith đang dùng.
- Nếu propagation không hoạt động, listener vẫn có thể xử lý thành công nhưng xuất hiện dưới trace khác hoặc thiếu correlation context.
- Trace được lấy mẫu; **không có span** trong dashboard không đủ để kết luận listener chưa chạy.
- Event identity như `eventId` hoặc `orderId` phù hợp để liên kết log/traces có kiểm soát; tránh dùng ID biến thiên cực lớn làm tag của counter Micrometer.

**Actuator application modules** phản ánh cấu trúc ứng dụng đã phát hiện; nó giúp xác định module và ranh giới phụ thuộc, nhưng **không thay thế** Event Publication Registry hoặc kiểm tra trạng thái nghiệp vụ của từng listener.

## 7. Điều tra một sự cố: API OK nhưng email không đến

Giả sử người dùng xác nhận đơn `ORD-42`. API trả thành công, log `Published OrderConfirmed` tồn tại, nhưng sau 15 phút người dùng chưa thấy email.

Thực hiện điều tra theo bằng chứng, không suy đoán từ một dòng log:

1. **Xác minh transaction gốc:** đơn đã ở trạng thái `CONFIRMED` trong DB chưa? Nếu chưa, kiểm tra rollback, phạm vi `@Transactional` và lỗi transaction.
2. **Xác minh publication:** có publication cho consumer `notifications` không? Nếu không, kiểm tra dependency registry, listener có được Spring đăng ký hay không, annotation phù hợp và điều kiện transaction.
3. **Xem trạng thái listener:** `PUBLISHED`/`PROCESSING`/`FAILED` hay `COMPLETED`? Đối chiếu timestamp, completion attempts và lỗi.
4. **Xem kết quả của listener:** nếu `COMPLETED`, đã có `MailJob` tương ứng trong DB chưa? Nếu không, xem logic bỏ qua, lỗi bị nuốt hoặc đánh dấu hoàn tất quá sớm.
5. **Xem bước gửi email:** nếu `MailJob` đã tồn tại, kiểm tra job worker, xác nhận SMTP/provider, bounce và retry riêng. Đừng quy lỗi cho event publication khi lỗi nằm ở kênh gửi.
6. **Kiểm tra trace và log liên kết:** tìm theo `eventId`, `orderId` và tên consumer; kiểm tra propagation và sampling trước khi kết luận trace thiếu.
7. **Khôi phục có kiểm soát:** với publication lỗi/chưa hoàn tất, dùng cơ chế resubmission phù hợp; trước khi thử lại phải bảo đảm consumer idempotent.

Một bảng ví dụ giúp diễn giải:

| Event / consumer | Registry | MailJob | Kết luận hợp lý |
| --- | --- | --- | --- |
| E1 / notifications | `PUBLISHED` | Không có | Chưa chứng minh đã gọi listener; kiểm tra executor/dispatch. |
| E2 / notifications | `FAILED` | Không có | Listener đã lỗi hoặc bị stale; tìm nguyên nhân và khôi phục. |
| E3 / notifications | `COMPLETED` | Có, `QUEUED` | Listener thành công; bước gửi email chưa hoàn tất. |
| E4 / inventory | `COMPLETED` | Không áp dụng | Chỉ inventory thành công; không suy ra notifications thành công. |
| E5 / notifications | Không thấy publication | Không có | Có thể rollback, thiếu registry, listener không đủ điều kiện, hoặc completion mode `DELETE` sau thành công. Cần đối chiếu thêm. |

## 8. Khả năng xử lý trùng lặp và nhất quán

Event handling thường được thiết kế để chịu retry. Một consumer có thể tạo hiệu ứng nhưng process chết trước khi framework lưu trạng thái completion. Khi khôi phục, cùng event được gọi lại.

**Ví dụ lỗi:** listener gửi ngay email trực tiếp qua SMTP, SMTP đã nhận thành công, rồi JVM crash trước completion. Lần chạy lại có thể gửi email lần thứ hai. Registry không thể tự biết trạng thái cuối của SMTP nếu hệ thống ngoài không cung cấp giao thức xác nhận/idempotency phù hợp.

Biện pháp:
- Mỗi event có `eventId` bền vững, tái sử dụng **cùng ID** khi xử lý lại publication cũ; không tạo ID mới trong listener.
- Ghi kết quả tiêu thụ vào bảng với unique key như `(consumer, eventId)` trong cùng transaction với thao tác nội bộ cần bảo vệ.
- Với hiệu ứng ngoài DB, dùng cơ chế idempotency key do downstream hỗ trợ hoặc transactional outbox/job để quản lý việc gửi riêng và ghi nhận trạng thái.
- Phân biệt retry tạm thời (network timeout) với lỗi vĩnh viễn (dữ liệu không hợp lệ); giới hạn số lần thử, dùng backoff và cách xử lý poison event.
- Không giả định thứ tự xử lý bằng thứ tự phát event: nhiều listener và async executor có thể thực thi song song, retry có thể phá thứ tự.
- Với hệ thống nhiều node, phối hợp khôi phục outstanding publications để tránh các node cùng xử lý trùng hoặc giành quyền không phù hợp.

**Đích thiết kế thực tế** là xử lý ít nhất một lần (at-least-once trong các điều kiện được hỗ trợ bởi persistence/retry) **kết hợp idempotency ở consumer**, thay vì khẳng định mọi effect chỉ xảy ra đúng một lần chỉ nhờ annotation.

## 9. Kiểm thử hai mốc publish và process riêng biệt

Đừng viết một bài test kiểu “gọi confirm rồi thấy event” và cho rằng toàn bộ pipeline đã được kiểm chứng. Chia kiểm thử theo điều muốn chứng minh.

### 9.1. Chứng minh event đã được publish

Spring Modulith cung cấp `@ApplicationModuleTest` và `PublishedEvents`/`AssertablePublishedEvents` để kiểm tra sự kiện đã được phát trong phạm vi test.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.acme.shop.orders.api.OrderConfirmed;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrdersEventTest {

    @Autowired OrderService orders;

    @Test
    void publishesOrderConfirmed(PublishedEvents events) {
        // orderId cần trỏ tới order hợp lệ trong fixture test.
        orders.confirm(orderId);

        assertThat(events.ofType(OrderConfirmed.class)
            .matching(OrderConfirmed::orderId, orderId))
            .hasSize(1);
    }
}
~~~

Đoạn trên minh họa API test; `orderId`, entity và fixture phải được tạo trong project thực tế. **Ý nghĩa của assertion chỉ là event đã được publish trong bài test.** Nó không khẳng định listener đã chạy, transaction đã commit hay hiệu ứng đã xuất hiện.

### 9.2. Chứng minh listener đã xử lý thành công

Với test tích hợp đầy đủ, cần:
- Chạy ứng dụng với transaction manager, persistence starter, DB test tương đương môi trường thật và executor async.
- Kích hoạt `orders.confirm(...)` từ một transaction có thể commit thật. Tránh cấu hình test rollback toàn bộ transaction ngoài cùng làm `AFTER_COMMIT` không chạy.
- Đợi bằng điều kiện có giới hạn thời gian (ví dụ Spring Modulith `Scenario` API hoặc Awaitility), không `Thread.sleep(...)` cố định.
- Kiểm tra DB có đúng **một** `MailJob` với `eventId` và `consumer` đã nhận.
- Kiểm tra completion của publication theo đúng completion mode, không suy ra failed chỉ vì bảng không có record khi dùng `DELETE`.
- Mô phỏng listener lỗi: nghiệp vụ gốc vẫn commit, listener để lại publication lỗi/chưa hoàn tất; khôi phục sau khi sửa lỗi.
- Mô phỏng gọi lại cùng event: không tạo `MailJob` trùng.
- Mô phỏng rollback ở publisher: listener `AFTER_COMMIT` không tạo `MailJob`.

| Test | Bằng chứng bắt buộc |
| --- | --- |
| Publisher phát sự kiện | `PublishedEvents` có `OrderConfirmed` đúng `orderId`. |
| Publisher rollback | Dữ liệu đơn không commit, listener không tạo effect. |
| Listener xử lý thành công | Job/hiệu ứng đã commit và publication được hoàn tất theo cấu hình. |
| Listener ném exception | Không có effect thành công giả; publication có thể phục hồi. |
| Listener bị chạy lại | Ràng buộc idempotency ngăn bản ghi/hiệu ứng trùng. |
| Hai listener cùng nhận event | Trạng thái từng publication độc lập. |
| Process chết/khởi động lại | Publication tồn tại bền vững và khôi phục theo chính sách. |

### 9.3. Một bài thực hành tự đối chiếu

1. Thêm log vào `OrderService.confirm` tại lúc `publishEvent(...)` và vào đầu/cuối `OrderNotificationListener.on`.
2. Cho listener chậm vài giây; quan sát HTTP request kết thúc và thứ tự log.
3. Cho listener ném exception có chủ đích, xem trạng thái publication; xác nhận order vẫn `CONFIRMED`.
4. Bỏ lỗi, resubmit publication bằng API/cấu hình tương thích với version dự án.
5. Gửi lại cùng `eventId` và chứng minh ràng buộc unique ngăn tạo job trùng.
6. Xem `module.events.published` và so với tình trạng registry; giải thích vì sao hai số đo không thể dùng thay thế nhau.
7. Dùng module graph và Actuator để xác nhận module `notifications` phụ thuộc vào API event của `orders`, rồi dùng trace/log để quan sát lúc listener thực sự chạy.

## 10. Câu hỏi tự đánh giá

1. `publishEvent(...)` trả về mà không ném lỗi cho phép kết luận được những điều gì và không cho phép kết luận điều gì?
2. `@TransactionalEventListener` mặc định có tự động chạy sang thread khác không? Vai trò của `@Async` là gì?
3. Vì sao cùng một `OrderConfirmed` có thể có một publication hoàn tất và một publication thất bại?
4. Nếu transaction gốc bị rollback, listener ở `AFTER_COMMIT` có chạy không? Log publish trước rollback có còn giá trị gì?
5. Trong Spring Modulith 2.x, `PUBLISHED`, `PROCESSING`, `COMPLETED` và `FAILED` khác nhau thế nào?
6. Khi completion mode là `DELETE`, một truy vấn “không thấy bản ghi” có chứng minh listener chưa xử lý không?
7. Vì sao đếm `module.events.published` không cho biết số email đã gửi?
8. Khi process chết sau khi gửi email nhưng trước khi ghi completion, xử lý lại có thể gây ra lỗi gì? Thiết kế ngăn lỗi đó ra sao?
9. Vì sao trace thiếu span xử lý async chưa đủ để kết luận event chưa chạy?
10. Một test chỉ dùng `PublishedEvents` và một test dùng `Scenario`/điều kiện kết quả nghiệp vụ chứng minh những điều khác nhau nào?

## Tài liệu tham khảo

- [Spring Modulith Reference — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listener, publication registry, lifecycle, recovery và test published events.
- [Spring Modulith Reference — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Actuator, module observability, traces và `module.events.published`.
- [Spring Modulith Reference — Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html): completion mode, restart republication và staleness.
- [Spring Modulith API — `@ApplicationModuleListener`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html): async transactional event listener với transaction riêng.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): cách hoạt động của `@TransactionalEventListener` và các transaction phase.
- [Spring Framework Reference — Annotation Support for Async](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executor và bất đồng bộ.

