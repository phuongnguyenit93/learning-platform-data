# Tránh payload quá lớn trong Spring Framework Application Events

## 1. Mục tiêu bài học

Một application event tốt thường diễn tả **điều gì vừa xảy ra** bằng một hợp đồng dữ liệu nhỏ, rõ ràng và ổn định, thay vì mang toàn bộ đồ thị đối tượng đang được xử lý. Trong Spring Framework, việc gọi `ApplicationEventPublisher.publishEvent(...)` giúp giảm coupling giữa nơi phát và nơi nhận, nhưng không tự giải quyết vấn đề **kích thước payload, thời gian giữ tham chiếu trong heap, tính nhất quán dữ liệu và chi phí listener**.

Bài này tập trung vào cách **tránh payload quá lớn** khi thiết kế event nội bộ ứng dụng Spring, đồng thời nêu điểm cần thay đổi nếu sự kiện được đưa ra message broker hay hệ thống phân tán.

Sau bài học, bạn có thể:

- Nói chính xác “payload lớn” có nghĩa gì trong **in-process Spring event** và phân biệt với message đã serialize.
- Nhận diện các event ôm nguyên JPA entity graph, danh sách dài, file/`byte[]`, dữ liệu HTTP hoặc object mutable.
- Chọn giữa **ID/reference event**, **minimal immutable snapshot** và **event batch giới hạn kích thước**.
- Biết khi nào listener nên tải dữ liệu theo ID, khi nào cần một snapshot nhỏ để tránh đọc nhầm trạng thái.
- Giải thích ảnh hưởng của đồng bộ, async, queue, transaction và vòng đời dữ liệu lên bộ nhớ và độ đúng.
- Tạo ví dụ Java 17+ có thể chạy bằng Gradle và thực hành cách kiểm tra bằng số liệu thực tế.

**Thông điệp chính:** “Tránh payload lớn” không chỉ là giảm số byte trong một class. Đây là thiết kế **hợp đồng sự kiện**, giới hạn **đồ thị đối tượng có thể được giữ sống**, và xác định **ai chịu trách nhiệm đọc dữ liệu khi listener chạy**.

## 2. Event payload trong Spring Framework thực chất là gì?

Spring Framework cho phép phát một đối tượng bất kỳ:

~~~java
publisher.publishEvent(new OrderPlaced(orderId, "CREATED"));
~~~

Nếu đối tượng không kế thừa `ApplicationEvent`, Spring bọc nó trong `PayloadApplicationEvent<?>` để phân phối đến listener thích hợp. Listener có thể dùng:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Nhận đúng payload đã phát.
}
~~~

Hai đoạn trên là mã minh họa: `publisher`, `OrderPlaced` và bean listener cần tồn tại.

Với multicaster mặc định của Spring, các listener thông thường được gọi **đồng bộ trên thread phát event**. Có thể đổi sang executor để phân phối qua các thread khác. Tuy nhiên, **việc publish nội bộ không mặc nhiên serialize object thành JSON hay sao chép sâu toàn bộ đối tượng**. Nó chuyển sự kiện qua cơ chế listener của Spring trong cùng process.

Điều này dẫn tới hai kết luận quan trọng:

1. Một event chứa tham chiếu đến `OrderEntity` lớn **không tự nhân bản toàn bộ entity graph cho mỗi listener** chỉ vì có nhiều listener. Nhưng event vẫn giữ được tham chiếu tới object graph đó; garbage collector không thể thu hồi những object còn reachable.
2. Nếu một listener, executor queue, buffer, retry structure hoặc lambda đang giữ event, toàn bộ những object còn reachable từ payload **có thể bị giữ sống lâu hơn dự kiến**. Khi mỗi event giữ một đồ thị riêng, việc tồn đọng nhiều event gây áp lực đáng kể lên heap và GC.

Khi dữ liệu được chuyển sang Kafka, RabbitMQ, HTTP, outbox JSON hoặc một hệ thống khác process, payload thường **phải serialize** và chi phí thêm bao gồm số byte truyền, encode/decode, giới hạn message, storage và schema compatibility. Không áp nguyên xi mô hình “chỉ truyền reference trong RAM” cho đường đi liên tiến trình.

## 3. Khi nào payload bị coi là quá lớn?

Không có một ngưỡng byte cố định nào mà mọi hệ thống Spring phải dùng. Đánh giá dựa vào **tính cần thiết, tỷ lệ giữa dữ liệu cần và dữ liệu mang theo, khả năng tồn đọng, độ trễ và điều kiện tải**.

Ví dụ payload có nguy cơ lớn:

- Event chứa cả một `OrderEntity` và các quan hệ JPA như `orderLines`, `customer`, `addresses`, `payments` trong khi listener chỉ cần `orderId`.
- Event mang `List<OrderDetail>` rất dài trong khi listener chỉ cần biết một batch đã hoàn tất.
- Event chứa toàn bộ ảnh, PDF, `byte[]`, Base64 string hoặc tệp upload chỉ để báo “đã tải lên”.
- Event nhét `HttpServletRequest`, HTTP session, security principal, response object, connection, stream, `EntityManager` hoặc những resource có lifecycle phức tạp.
- Event chứa cả object graph mutable có thể bị code phát sửa sau khi `publishEvent`.
- Sự kiện lặp với tần suất cao và mỗi lần kèm nhiều metadata trùng lặp, mặc dù thông tin hữu ích chỉ vài trường.

Cần phân biệt ba loại kích thước:

| Khái niệm | Ý nghĩa | Cách quan sát |
| --- | --- | --- |
| **Shallow size** của instance event | Bộ nhớ riêng của object event và các trường tham chiếu/primitive | Profiler / heap inspection |
| **Retained/reachable graph** | Các object vẫn có thể reachable từ event và những object tham chiếu của nó | Heap dump, profiler; đừng cộng trùng graph dùng chung |
| **Serialized size** | Kích thước sau khi chuyển thành JSON/Avro/Protobuf/... | Đo thực tế sau serialization theo codec thật |

Một `record OrderPlaced(long orderId)` rất nhỏ, nhưng một `record OrderPlaced(OrderEntity order)` có thể giữ tham chiếu đến hàng nghìn object phía sau. Ngược lại, hai event cùng tham chiếu một immutable catalog lớn không có nghĩa heap đã nhân đôi catalog. Vì vậy, đừng cố lấy kích thước bằng `event.toString().length()` hay `Object.toString()`; chúng không đo được bộ nhớ của object graph.

## 4. Nguyên tắc thiết kế: giữ dữ liệu tối thiểu để đáp ứng hợp đồng

Trước khi thêm trường vào event, hỏi:

1. **Listener thật sự cần gì?** Chỉ ID? Trạng thái mới? Thời điểm? Tenant ID? Số version? Một vài giá trị phải giữ bất biến?
2. **Giá trị đó có sẵn/ổn định lúc phát không?** Nếu listener cần trạng thái tại đúng thời điểm xảy ra, phải cân nhắc snapshot.
3. **Listener chạy lúc nào?** Ngay trong thread publisher, bất đồng bộ, sau commit hay sau retry?
4. **Có thể tra cứu theo ID không?** Repository có truy cập được sau commit không? Có thể bị xóa/thay đổi trước lúc listener đọc không?
5. **Payload chứa dữ liệu nhạy cảm không?** Việc giữ/ghi log/serialize có làm tăng phạm vi lộ dữ liệu?
6. **Dữ liệu có giá trị lâu dài không?** Nếu event được lưu ra broker, schema phải ổn định và đủ để tái xử lý.

Mục tiêu không phải “ít trường nhất bằng mọi giá”. Mục tiêu là **ít dữ liệu nhất nhưng vẫn đủ để người nhận xử lý đúng**.

Ví dụ:

~~~java
// Không nên: mọi listener đều nhận cả entity graph.
public record OrderPlacedBad(OrderEntity wholeOrder) {}

// Tối giản khi listener có thể truy vấn lại:
public record OrderPlaced(long orderId) {}

// Snapshot nhỏ khi cần giữ ngữ nghĩa tại thời điểm phát:
public record OrderPlacedSnapshot(
        long orderId,
        String orderStatus,
        java.time.Instant occurredAt,
        long version) {}
~~~

Đây là các định nghĩa minh họa; `OrderEntity` chưa được định nghĩa trong đoạn code này. Không đặt cả ba loại payload vào cùng một event production chỉ vì muốn “phòng khi cần”.

## 5. Chiến lược 1: event chỉ mang ID hoặc khóa tham chiếu

Ví dụ cơ bản:

~~~java
public record InvoiceGenerated(long invoiceId) {}
~~~

Khi nhận event, listener tự lấy những trường cần từ repository:

~~~java
@EventListener
public void onInvoiceGenerated(InvoiceGenerated event) {
    Invoice invoice = invoiceRepository.findById(event.invoiceId())
            .orElseThrow();
    reportService.process(invoice);
}
~~~

Các đoạn này cần `Invoice`, repository, service và bean listener được cấu hình; không phải chương trình độc lập.

### 5.1. Ưu điểm

- Payload nhỏ và ít gắn với cấu trúc entity; đổi thuộc tính nội bộ không buộc sửa mọi event.
- Ít giữ object graph nặng trong bộ nhớ ở thời điểm publish.
- Listener có thể đọc đúng **projection** cần thiết, thay vì làm việc với toàn bộ entity.
- Ít rủi ro vô tình phát tán PII, attachment hoặc lazy-loaded graph sang nơi không phù hợp.
- Nếu sau này chuyển từ event nội bộ sang broker, việc serialize một ID đơn giản và version có thể dễ quản lý hơn.

### 5.2. Đổi lại: tra cứu và tính đúng của dữ liệu

ID-only không miễn phí. Listener phải truy cập repository, nên có thể gặp:

- **N+1 query:** hàng nghìn listener/ID được xử lý riêng làm tăng round-trip.
- **Không thấy dữ liệu chưa commit:** listener chạy ở transaction khác hoặc thread khác trước commit có thể không đọc được bản ghi.
- **Dữ liệu đã bị thay đổi:** listener chạy trễ có thể đọc trạng thái mới, không phải trạng thái ở lúc event xảy ra.
- **Bản ghi đã bị xóa:** ID hợp lệ lúc phát nhưng không còn tồn tại lúc xử lý.
- **Ràng buộc quyền/tenant:** listener cần biết phạm vi hợp lệ để truy vấn, không tự sử dụng security `ThreadLocal` từ request cũ.

Vì thế, chỉ dùng ID khi listener **được phép đọc trạng thái hiện tại** và có cách xử lý not-found/retry/stale data rõ ràng. Nếu việc xử lý phụ thuộc chính xác vào một sự thật quá khứ, cần snapshot nhỏ hoặc event log/outbox đúng nghĩa.

## 6. Chiến lược 2: minimal immutable snapshot

Không phải mọi listener nên truy vấn lại dữ liệu. Một số quyết định phụ thuộc vào **trạng thái tại đúng thời điểm business event**. Ví dụ listener tính hoa hồng trên giá đã chốt; sau đó giá sản phẩm có thể thay đổi.

Khi ấy chỉ mang ID sẽ không đủ. Event nên chứa **những giá trị nghiệp vụ không thể suy luận lại một cách an toàn**:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record PaymentAccepted(
        String paymentId,
        String currency,
        BigDecimal capturedAmount,
        Instant acceptedAt) {}
~~~

Nội dung này vẫn nhỏ, có ngữ nghĩa rõ và không buộc người nhận kéo cả entity `Payment`, lịch sử giao dịch, thông tin thẻ, địa chỉ hóa đơn hay dữ liệu log.

Có thể bổ sung:

- `entityVersion` để phát hiện bản ghi đã thay đổi.
- `occurredAt` để phân biệt thời điểm sự kiện với thời điểm listener chạy.
- `tenantId` nếu dữ liệu đa tenant; coi đây là **đầu vào phân quyền**, không phải bằng chứng quyền truy cập.
- `correlationId`/`traceId` nhỏ, không nhúng toàn bộ request/trace object.

### 6.1. Record chỉ bất biến nông (shallow immutability)

Java record tạo các field cuối cùng, nhưng không tự làm immutable các object nằm bên trong. Ví dụ:

~~~java
public record BatchReady(java.util.List<Long> ids) {
    public BatchReady {
        ids = java.util.List.copyOf(ids);
    }
}
~~~

`List.copyOf(...)` tạo một snapshot không chỉnh sửa được của cấu trúc danh sách, giúp publisher không thể thêm/xóa ID qua list cũ làm thay đổi list trong event. Tuy nhiên, nếu phần tử là mutable object, `List.copyOf` **không deep-copy nội dung từng phần tử**. Với ID kiểu `Long` thì tính ổn định dễ bảo đảm hơn.

Với `byte[]`, cần tự phòng thủ bằng copy nếu thật sự phải chứa dữ liệu nhị phân; nhưng cách tốt hơn thường là **không gửi binary qua event**, mà gửi ID/tên object storage và một ít metadata.

### 6.2. Không ràng buộc event vào entity sống

JPA/Hibernate entity thường có:

- Lazy association và proxy chưa được khởi tạo.
- Persistence context, quan hệ hai chiều và nhiều object liên kết.
- Trạng thái mutable và lifecycle của transaction/session.
- Nguy cơ lỗi khi listener async truy cập lazy field sau khi session đã đóng.

Vì vậy, **không dùng entity graph làm “snapshot miễn phí”**. Một entity chưa được serialize có thể trông nhỏ lúc publish nhưng việc truy cập getter trong listener khiến truy vấn ngoài ý muốn, lỗi lazy initialization hoặc graph phình to. Chuyển sang DTO/record có trường xác định rõ ràng.

## 7. Chiến lược 3: tài nguyên lớn dùng reference, không nhét trực tiếp

Với ảnh, PDF, video, hợp đồng, file import hoặc dữ liệu phân tích lớn, event nên thông báo **vị trí tài nguyên và trạng thái** thay vì mang dữ liệu:

~~~java
public record DocumentUploaded(
        String documentId,
        String storageKey,
        long contentLength,
        String checksum) {}
~~~

Ý nghĩa các trường:

- `documentId` nhận diện tài liệu trong domain.
- `storageKey` định vị object trong hệ thống lưu trữ mà listener có quyền truy cập.
- `contentLength` hỗ trợ kiểm tra giới hạn/quan sát.
- `checksum` hỗ trợ kiểm chứng toàn vẹn khi thực sự cần.

Không đưa **signed URL sống lâu**, secret access key, session token, nội dung file đã Base64 hoặc stream mở vào payload. Với storage private, listener tự tạo URL ngắn hạn hoặc dùng SDK/identity được cấp quyền.

Một object storage reference chỉ giải quyết phần “không giữ binary trong event”; nó còn cần quy tắc:

- Object phải tồn tại và đủ quyền truy cập khi listener xử lý.
- Retention/TTL của object phải dài hơn vòng đời xử lý hợp lệ.
- Listener phải kiểm tra kích thước/loại file, quyền tenant và checksum theo chính sách.
- Tác vụ xóa object phải phối hợp với retry hoặc message chậm.

Khi chuyển event ra broker, payload serialized thường là reference + metadata nhỏ; binary được lấy theo nhu cầu, có giới hạn kích thước và stream an toàn.

## 8. Ví dụ Java 17+ chạy được: phát ID thay vì cả đơn hàng

Ví dụ chạy **Spring Framework thuần**. Repository in-memory được dùng để tập trung vào kích thước hợp đồng event; đây **không phải** ví dụ minh họa transaction thật, JPA hay database. Một listener chỉ nhận `orderId` và `status` rồi truy vấn đúng hai trường dữ liệu nó cần từ repository.

### 8.1. Cấu trúc dự án

~~~text
small-payload-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── PayloadSizeDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'small-payload-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'demo.PayloadSizeDemo'
}
~~~

Spring Framework 6.2.x yêu cầu Java 17 trở lên. Khi chạy trong Spring Boot, nên dùng Boot BOM để quản lý phiên bản framework tương thích.

### 8.2. Toàn bộ mã nguồn

Lưu thành `src/main/java/demo/PayloadSizeDemo.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class PayloadSizeDemo {

    // DTO nội bộ mô phỏng bản ghi lưu ở repository.
    public record OrderDetails(
            long id,
            String customerName,
            List<String> itemCodes) {

        public OrderDetails {
            itemCodes = List.copyOf(itemCodes);
        }
    }

    // Event không giữ OrderDetails, chỉ giữ thông tin thực sự cần.
    public record OrderPlaced(
            long orderId,
            String status,
            Instant occurredAt) {}

    public static class OrderRepository {
        private final Map<Long, OrderDetails> orders =
                new ConcurrentHashMap<>();

        public void save(OrderDetails order) {
            orders.put(order.id(), order);
        }

        public Optional<OrderDetails> findById(long id) {
            return Optional.ofNullable(orders.get(id));
        }
    }

    public static class NotificationListener {
        private final OrderRepository repository;

        public NotificationListener(OrderRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            OrderDetails order = repository.findById(event.orderId())
                    .orElseThrow(() ->
                            new IllegalStateException(
                                    "Missing order " + event.orderId()));

            System.out.println(
                    "listener: order=" + order.id()
                    + ", status=" + event.status()
                    + ", items=" + order.itemCodes().size());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public OrderRepository orderRepository() {
            return new OrderRepository();
        }

        @Bean
        public NotificationListener notificationListener(
                OrderRepository repository) {
            return new NotificationListener(repository);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderRepository repository =
                    context.getBean(OrderRepository.class);

            repository.save(new OrderDetails(
                    101L, "Mai", List.of("SKU-A", "SKU-B")));

            System.out.println("publisher: saved order 101");

            context.publishEvent(
                    new OrderPlaced(
                            101L,
                            "CREATED",
                            Instant.parse("2026-11-11T03:00:00Z")));

            System.out.println("publisher: publishEvent returned");
        }
    }
}
~~~

### 8.3. Chạy và stdout kỳ vọng

Từ thư mục `small-payload-demo`, cài JDK 17+ và Gradle rồi chạy:

~~~bash
gradle -q run
~~~

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

Các dòng **do ứng dụng tự in ra** sẽ theo thứ tự:

~~~text
publisher: saved order 101
listener: order=101, status=CREATED, items=2
publisher: publishEvent returned
~~~

Gradle và logging có thể ghi thêm dòng khác tùy môi trường.

**Giải thích:**

1. Repository lưu `OrderDetails` chứa dữ liệu chi tiết. Trong ứng dụng thật đây có thể là database; ở ví dụ dùng `ConcurrentHashMap`.
2. `OrderPlaced` chỉ có `orderId`, `status` và `occurredAt`, không giữ tham chiếu đến `OrderDetails` hay `List<String>`.
3. Spring dùng `ApplicationEventPublisher.publishEvent(Object)` để phát POJO record và `@EventListener` tự nhận đúng kiểu.
4. Multicaster mặc định gọi listener đồng bộ, nên dòng `listener: ...` xuất hiện **trước** dòng `publisher: publishEvent returned`.
5. Listener lấy dữ liệu theo ID và in số lượng item. Mọi dữ liệu chi tiết nằm ở repository, không phải event payload.

**Giới hạn của demo:** `OrderRepository` là in-memory, không có network, transaction hoặc concurrent update trong lúc chạy; do đó ví dụ chỉ minh họa **hợp đồng nhỏ và luồng xử lý đồng bộ**. Không được suy ra pattern ID-only sẽ an toàn trong mọi tình huống async/transaction mà không thiết kế ranh giới đọc dữ liệu.

## 9. Đổi từ payload lớn sang payload nhỏ: ví dụ trước–sau

Giả sử một service đang phát:

~~~java
// Minh họa thiết kế cần xem lại:
publisher.publishEvent(new OrderChanged(
        orderEntity,
        customerEntity,
        orderEntity.getLines(),
        invoicePdfBytes));
~~~

Bốn đối tượng này có thể giữ lại một graph rất lớn; một số còn là mutable JPA entity hoặc `byte[]`. Chỉ vì listener muốn gửi thông báo “đơn hàng thay đổi” không có nghĩa nó cần nhận đầy đủ dữ liệu.

Thiết kế thay thế:

~~~java
publisher.publishEvent(new OrderStatusChanged(
        orderId,
        previousStatus,
        currentStatus,
        Instant.now(),
        entityVersion));
~~~

Trong thực tế, cả `OrderChanged` và `OrderStatusChanged` cần được định nghĩa; đây là đoạn **minh họa**, không phải mã độc lập. Một record nhỏ như `OrderStatusChanged` giúp người nhận biết sự thật nghiệp vụ đã xảy ra mà không cần xem cấu trúc entity. Nếu muốn hiển thị danh sách sản phẩm, listener có thể truy vấn projection cụ thể từ repository; nếu cần chính xác “danh sách tại lúc xảy ra”, cân nhắc snapshot nhỏ tương ứng.

### 9.1. Không đẩy chi phí sang listener một cách mù quáng

Tránh payload lớn nhưng tạo 1.000 query trùng lặp cũng không tốt. Có thể:

- Dùng projection query chỉ lấy các trường cần, không load cả graph.
- Gộp truy vấn theo ID nếu một listener xử lý nhiều event cùng loại.
- Cache có giới hạn khi dữ liệu phù hợp, nhưng phải xác định quy tắc invalidation.
- Tách notification ít quan trọng ra worker không chặn request.
- Giới hạn batch, queue, số worker và tốc độ publish thay vì chỉ đổi field của event.

Thiết kế tốt tối ưu **end-to-end cost**: heap, CPU, database, transaction và latency.

## 10. Ảnh hưởng của synchronous vs asynchronous event processing

### 10.1. Đồng bộ mặc định

Với `SimpleApplicationEventMulticaster` mặc định, listener chạy trên thread của publisher. Khi đó, một event lớn làm tăng áp lực bộ nhớ nhưng thường chỉ được giữ trong khoảng thời gian xử lý listener, trừ khi code khác lưu tham chiếu. Chi phí lớn khác là listener quét graph hoặc truy cập lazy association gây truy vấn database không dự kiến.

~~~text
publisher -> publishEvent(large event)
          -> listener A xử lý ngay
          -> listener B xử lý ngay
          -> publishEvent trả về
~~~

### 10.2. Khi bật task executor

Nếu cấu hình multicaster dùng `ThreadPoolTaskExecutor` hoặc đặt `@Async` trên listener thích hợp, các công việc có thể được **xếp vào queue** và chạy sau. Lúc này event/payload có thể còn được worker task giữ tham chiếu trong lúc chờ.

~~~text
publisher -> submit event A ---\
publisher -> submit event B ----> executor queue -> worker xử lý
publisher -> submit event C ---/
~~~

Ở đường đi này, một số rủi ro tăng rõ:

- **Retained heap** tăng theo số event đang chờ và graph của từng event.
- Queue dài làm listener xử lý dữ liệu muộn; ID có thể stale và bản ghi có thể thay đổi.
- Listener không nhất thiết hoàn thành theo thứ tự publish, ngay cả khi có `@Order`.
- ThreadLocal, security context, MDC và imperative transaction **không tự động** theo worker thread.
- Exception trong worker có thể không truyền về publisher.
- Executor quá tải có thể từ chối task hoặc áp dụng chính sách riêng; không suy luận `publishEvent` luôn đồng nghĩa xử lý thành công.

Đặt executor trên multicaster cũng **không đồng nghĩa mọi listener được chạy async**: từ Spring 6.1, những `ApplicationListener` không hỗ trợ async ở cấp multicaster, bao gồm một số transaction-synchronized listeners, cần chạy trong thread publisher ở phần đăng ký cần thiết.

### 10.3. Một phép ước lượng năng lực queue

Với mỗi event giữ một mảng byte riêng cỡ 200 KiB, **10.000 task bị tồn đọng** có thể giữ xấp xỉ **1,95 GiB dữ liệu mảng** (chưa tính overhead), dù logic listener chỉ cần một ID. Đây chỉ là phép nhân minh họa giả định **mỗi event có dữ liệu riêng**, không phải đo đạc heap thật.

Trong thực tế, retained size phụ thuộc reference sharing, object layout, queue và collector; phải kiểm chứng bằng profiler/JFR/heap dump và số liệu queue thật. Đừng chỉ đo shallow size của record rồi kết luận an toàn.

## 11. Transaction và thời điểm đọc dữ liệu theo ID

Một vấn đề quan trọng: với ID-only event, **listener đọc dữ liệu vào thời điểm nào?**

### 11.1. Event đồng bộ trong transaction hiện tại

Nếu service publish sau khi lưu entity nhưng **trước commit**, listener đồng bộ chạy trong transaction hiện tại có thể nhìn thấy thay đổi chưa commit. Tuy vậy, việc listener xử lý xong không có nghĩa transaction đã commit; commit cuối cùng còn có thể rollback.

Nếu listener gửi email ở thời điểm này, database có thể rollback trong khi email đã gửi. Đó là lỗi thiết kế **về thời điểm**, không phải lỗi do payload nhỏ.

### 11.2. Event sau commit

Với thao tác chỉ nên xảy ra sau khi transaction thành công, một lựa chọn là:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    // Xử lý phản ứng sau commit, đọc dữ liệu trong scope phù hợp.
}
~~~

Đây là **phương thức minh họa** cần một bean Spring, transaction manager và class `OrderPlaced` được định nghĩa. Mặc định của `@TransactionalEventListener` cũng là `AFTER_COMMIT`; khai báo tường minh giúp người đọc dễ hiểu.

Những điều cần ghi nhớ:

- Với cấu hình mặc định, nếu event được phát **ngoài transaction**, listener transaction không chạy, trừ khi đặt `fallbackExecution = true`.
- Nếu listener đọc trạng thái **mới nhất** sau commit, record có thể đã được cập nhật lần nữa; nếu không được phép, event cần version/snapshot hoặc điều kiện kiểm tra version.
- Nếu listener ghi dữ liệu mới sau commit, không mặc nhiên giả định đang có transaction mới. Hãy mở transaction riêng phù hợp khi cần commit thêm dữ liệu.
- Nếu event cần được xử lý sau restart, **Spring in-process event không phải hàng đợi bền vững**; cân nhắc transactional outbox, broker và idempotent consumer.

### 11.3. Không dùng ID-only khi yêu cầu snapshot tuyệt đối

Ví dụ: giá tại thời điểm thanh toán đã được khách chấp thuận là một dữ kiện nghiệp vụ cần giữ. Listener truy vấn giá hiện tại một phút sau có thể cho ra kết quả khác. Lúc đó, event có thể cần:

~~~java
public record PaymentCaptured(
        String paymentId,
        java.math.BigDecimal amount,
        String currency,
        long agreementVersion) {}
~~~

Cách này vẫn tránh graph khổng lồ, đồng thời giữ đúng nội dung tối thiểu phải bất biến. Với dữ liệu đặc biệt nhạy cảm, cân nhắc token/reference bảo vệ thay vì đưa giá trị trực tiếp vào event nếu không cần.

## 12. Batch event và giới hạn cardinality

Một event mang danh sách ID có thể hợp lý khi một thao tác nghiệp vụ tạo nhiều đối tượng, nhưng danh sách tăng không giới hạn sẽ trở thành payload lớn theo cách khác:

~~~java
// Không nên khi ids có thể gồm hàng trăm nghìn mục:
public record BatchImported(java.util.List<Long> ids) {}

// Chỉ mang thông tin batch:
public record BatchImportCompleted(
        String batchId,
        long importedCount) {}
~~~

Trong cách thứ hai, listener truy vấn các dòng có `batchId`, phân trang theo kích thước giới hạn. Nếu cần xử lý độc lập từng item, một cơ chế queue/batch worker có kiểm soát thường phù hợp hơn việc phát một event giữ mọi entity.

Khi thực sự gửi danh sách ID:

- Đặt giới hạn phần tử tối đa dựa trên benchmark.
- Copy list ngay lúc tạo event để tránh producer sửa sau khi publish.
- Cân nhắc batch/window có thứ tự, retry và deduplication.
- Dùng pagination/keyset để listener không nạp cả batch trở lại memory một lần.
- Tránh bùng nổ số query: batch fetch thay vì từng ID nếu hợp đồng cho phép.

Một batch reference như `batchId` cũng phải có chính sách lưu trữ đủ lâu; nếu dữ liệu batch bị xóa trước khi listener xử lý, giảm kích thước payload bằng reference có thể tạo lỗi khó sửa.

## 13. Quy tắc giới hạn và bảo vệ dữ liệu

### 13.1. Chỉ giữ dữ liệu được phép chia sẻ

Giảm payload thường giúp giảm bề mặt rò rỉ dữ liệu, nhưng chỉ ID cũng không tự an toàn. Một ID, tenant ID hay customer ID vẫn có thể nhạy cảm. Với event:

- Không cho password, access token, JWT, secret, cookie hoặc thông tin thẻ vào payload.
- Không đưa cả `SecurityContext` hoặc `HttpServletRequest` vào event; truyền dữ kiện cần thiết và xác thực quyền ở listener.
- Không log toàn bộ payload mặc định nếu event có PII.
- Xác định ranh giới tenant khi listener truy vấn theo ID; ID lấy từ event không là sự bảo đảm quyền truy cập.
- Nếu event chuyển ra ngoài process, định nghĩa schema, phân loại dữ liệu và quyền truy cập độc lập.

### 13.2. Giới hạn theo hành vi, không có “ngưỡng thần kỳ”

Tùy hệ thống, có thể đặt policy:

- Không nhét file binary hoặc entity graph vào event.
- Một event chỉ mang các primitive, ID, enum, timestamp và DTO nhỏ cần thiết.
- Không dùng danh sách không giới hạn; yêu cầu batch ID + pagination khi vượt ngưỡng dựa trên đo đạc.
- Mỗi event hợp đồng rõ ràng giữa producer và consumer.
- Không tham chiếu object mutable có lifecycle request/transaction.
- Nếu có outbox/broker: giới hạn **serialized bytes** dựa trên giới hạn thật của hạ tầng, thay vì chỉ nhìn số field.

Trong code review, một câu hỏi hữu ích là: **“Nếu 10.000 event loại này đang chờ xử lý thì những object nào sẽ còn reachable?”**

## 14. Đo đạc và kiểm thử để quyết định payload có quá lớn không

Nên đo trong môi trường gần workload thực tế, không dựa vào một test chỉ in `Runtime.getRuntime().freeMemory()` trước/sau một event đơn lẻ. GC, class loading, cache và JIT làm số liệu đó nhiễu.

Các chỉ số hữu ích:

| Chỉ số | Lý do |
| --- | --- |
| Kích thước payload sau serialize (nếu có broker) | Chi phí network/storage và giới hạn message thật |
| Heap usage, allocation rate, retained objects | Đánh giá áp lực RAM và giữ tham chiếu |
| GC pause/CPU | Phát hiện allocation churn hoặc heap pressure |
| Executor active threads và queue depth | Phát hiện backlog giữ nhiều event |
| Publisher latency p95/p99 | Xem listener đồng bộ có làm chậm request không |
| Listener processing latency và lỗi/retry | Xem việc chuyển gánh nặng sang repository có tăng thời gian không |
| Số query / row fetch / N+1 | Đánh giá cái giá của ID-only event |
| DB transaction timeout/lock time | Phát hiện listener làm transaction quá lâu |

Dụng cụ có thể dùng: Java Flight Recorder (JFR), heap dump/heap histogram, Micrometer/Actuator khi có, metrics của `ThreadPoolTaskExecutor`, database slow query log, integration test tải và JMH cho microbenchmark đã cô lập. Nếu có consumer hàng đợi, đo cả message lag, retry và DLQ.

### 14.1. Các test cần viết

1. **Schema test:** event chỉ có những trường được chấp nhận, không chứa entity/`byte[]` hoặc resource không được phép.
2. **Immutability test:** nếu event chứa list, sửa list ban đầu sau khi tạo event không làm thay đổi danh sách trong event.
3. **Synchronous test:** default listener được gọi theo đường đi mong đợi, dữ liệu projection có đủ.
4. **Async/backlog test:** giới hạn queue, quan sát heap/latency khi listener chậm và nhiều event được publish.
5. **Transaction test:** listener chỉ chạy sau commit nếu yêu cầu; không gửi side effect khi rollback.
6. **Stale/not-found test:** listener phản ứng đúng nếu entity bị xóa hoặc version thay đổi trước khi xử lý.
7. **Batch/load test:** với hàng nghìn ID, xác minh không có `N+1` gây quá tải và không tạo list khổng lồ.
8. **Security test:** ID không vượt tenant boundary, payload không chứa secret hay PII dư thừa.

Không cần ép mọi thứ vào một unit test. Kiểm thử hợp đồng event bằng unit test, còn transaction/async/DB cần integration test có cấu hình thực.

## 15. Các lỗi phổ biến và cách sửa

| Lỗi / ngộ nhận | Vấn đề | Cách sửa |
| --- | --- | --- |
| “Spring event tự serialize nên class lớn chỉ ảnh hưởng JSON” | Event in-process thường truyền object/reference, ảnh hưởng retained heap | Đo object graph và vòng đời reference |
| “Có nhiều listener nên Spring luôn copy sâu entity graph” | Không có bảo đảm copy sâu mặc định | Tránh payload nặng vì retention/mutable state, không suy luận nhân bản vô điều kiện |
| Publish cả JPA entity vì “listener có thể cần” | Coupling vào ORM/lazy loading, giữ graph lớn | Dùng ID hoặc projection/snapshot nhỏ |
| Publish cả `MultipartFile`/`InputStream` | Resource có lifecycle, có thể bị đóng hoặc giữ dữ liệu lớn | Lưu bền vững trước, chỉ gửi storage reference |
| ID-only nhưng listener đọc trong thread khác trước commit | Không nhìn thấy dữ liệu hoặc transaction context | Phát/đăng ký ở phase phù hợp, sau commit nếu cần |
| ID-only khi listener cần giá gốc | Dữ liệu hiện tại đã thay đổi | Dùng small immutable snapshot với amount/version |
| Mutable list trong record | Record chỉ immutable nông | Dùng `List.copyOf` cho danh sách ID; thiết kế immutable phần tử |
| Queue unbounded với event lớn | Backlog giữ heap, GC pressure, OOM | Giới hạn queue, backpressure, pool, payload size |
| Một event chứa hàng trăm nghìn item | Payload/buffer tăng vô hạn | Batch ID và pagination/chunk |
| Giảm payload nhưng N+1 repository fetch | Chuyển chi phí từ RAM sang DB | Projection, batch query, cache khi phù hợp |
| “publishEvent xong là listener async xử lý thành công” | Chỉ bàn giao cho cơ chế phân phối; task có thể chưa chạy | Theo dõi completion/error, retry, observability |
| Chỉ dùng `Thread.sleep` để test async | Test flake, không đo đúng lifecycle | Latch/future với timeout và trạng thái dữ liệu |
| Đưa dữ liệu nhạy cảm vào event/log | Tăng bề mặt lộ dữ liệu | Least-privilege payload, không log secret |
| Đưa event nội bộ sang broker mà giữ nguyên object graph | Serialized bytes và schema khác với in-memory reference | Thiết kế DTO/contract và đo size thật |

## 16. Checklist thiết kế trước khi merge

- [ ] Event tên theo một sự thật nghiệp vụ cụ thể, payload diễn tả **đúng thông tin cần thiết**.
- [ ] Không đưa nguyên JPA entity graph, request/session, stream, connection hoặc file binary vào event.
- [ ] Nếu chỉ truyền ID, listener chấp nhận đọc **trạng thái hiện tại**; nếu không, dùng snapshot nhỏ/version.
- [ ] Trường danh sách có giới hạn và được snapshot defensively nếu mutable.
- [ ] Event không chứa secret/PII dư thừa và listener kiểm tra tenant/access context phù hợp.
- [ ] Đã phân tích sync/async, queue retention, rollback và thời điểm DB commit.
- [ ] Biết hành vi khi record không tồn tại, version lệch, task retry hoặc event bị xử lý lại.
- [ ] Không nhầm độ lớn in-memory object graph với serialized size của message.
- [ ] Có chỉ số heap/queue/latency/query để đánh giá hiệu năng dưới tải thật.
- [ ] Không sử dụng Spring in-process events thay cho outbox/broker nếu hệ thống cần giao nhận bền vững.

## 17. Câu hỏi tự kiểm tra

**1.** Vì sao `record Event(OrderEntity order)` có thể gây áp lực bộ nhớ dù `record` chỉ chứa một trường?

**Đáp án:** Trường đó là reference; event có thể giữ cả object graph còn reachable từ entity, đặc biệt khi task bị tồn đọng trong queue. Record không tự biến cả graph thành dữ liệu nhỏ.

**2.** Nếu listener chỉ cần biết ID để truy vấn trạng thái hiện tại, nên chọn payload nào?

**Đáp án:** Một event nhỏ chứa ID và metadata thực sự cần. Không cần mang cả entity graph hoặc attachment.

**3.** Nếu listener phải dùng số tiền tại thời điểm thanh toán, ID-only có đủ không?

**Đáp án:** Không phải lúc nào cũng đủ. Có thể dùng immutable snapshot nhỏ như `paymentId`, `amount`, `currency` và `agreementVersion`; nếu đọc lại thì phải bảo đảm dữ liệu đúng thời điểm.

**4.** Có thể phát event chứa PDF `byte[]` lớn vì “Spring không serialize” không?

**Đáp án:** Không nên. Việc không serialize mặc định không loại bỏ chi phí lưu mảng trong heap và giữ tham chiếu; giải pháp thường là storage reference.

**5.** `@TransactionalEventListener(AFTER_COMMIT)` có chắc luôn chạy không?

**Đáp án:** Không. Nếu không có transaction và `fallbackExecution` mặc định false, listener không chạy. Nếu commit thất bại/rollback, callback AFTER_COMMIT không được phát như một commit thành công.

**6.** Chuyển sang ID-only có phải luôn nhanh hơn không?

**Đáp án:** Không. Nếu mỗi listener tạo quá nhiều query, tổng chi phí có thể tệ hơn; cần projection, batch fetch và đo thực tế.

**7.** Tại sao `List.copyOf(ids)` có ích với event batch?

**Đáp án:** Nó giữ cấu trúc list trong event không bị producer thêm/bớt sau khi tạo và chặn sửa list qua event. Nó không deep-copy các phần tử mutable.

## 18. Tài liệu tham khảo

- Spring Framework `ApplicationEventPublisher` — event publication và payload object: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework `PayloadApplicationEvent`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Spring Framework `SimpleApplicationEventMulticaster` — đồng bộ mặc định, executor và error handling: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Reference — Observability Support và context propagation: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Java Flight Recorder / JDK Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/
