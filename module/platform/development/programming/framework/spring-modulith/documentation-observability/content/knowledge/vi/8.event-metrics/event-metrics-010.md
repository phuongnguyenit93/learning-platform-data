# Khác biệt metric công bố với metric xử lý event

Trong một ứng dụng **Spring Boot** dùng **Spring Modulith**, việc ghi nhận “đã công bố 100 sự kiện” không đồng nghĩa “đã xử lý thành công 100 sự kiện”. Một sự kiện có thể không có listener, có nhiều listener, được xử lý bất đồng bộ, gặp lỗi rồi retry, hoặc được một listener nhận nhưng công việc bên ngoài vẫn thất bại. Vì thế, cần tách bạch **metric công bố (publication)** và **metric xử lý (processing/consumer)** ngay từ cách đặt câu hỏi đến cách instrument, tính toán và đọc dashboard.

Bài thuộc chương **Event metrics** của mô-đun học **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Trong mục tiêu dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác, bài này tập trung vào **mức độ tin cậy của số đếm event**. Các mảnh ghép liên quan gồm **module graph**, **Actuator**, **Event Publication Registry**, **tracing** và **context propagation** để kiểm chứng điều thực sự xảy ra khi hệ thống vận hành.

> **Phạm vi phiên bản:** Phần lifecycle `PUBLISHED / PROCESSING / COMPLETED / FAILED / RESUBMITTED` áp dụng cho Spring Modulith **từ 2.0**; `ABANDONED` có từ **2.2**. Ví dụ cấu hình giả định dự án dùng Spring Modulith **2.2** cùng phiên bản Spring Boot tương thích và có quản lý phiên bản dependency bằng BOM hoặc dependency management. Với bản cũ hơn, cần đối chiếu đúng tài liệu phiên bản đang dùng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu chính xác Spring Modulith đo gì bằng `module.events.published` và metric theo từng loại event.
2. Phân biệt **một lần phát event**, **một publication dành cho một listener**, **một lần listener chạy**, và **một lần listener hoàn tất thành công**.
3. Giải thích vì sao hai listener nhận cùng một event có thể tạo hai trạng thái xử lý khác nhau dù publication counter chỉ ghi nhận một lần phát.
4. Hiểu trạng thái publication trong **Event Publication Registry** và ảnh hưởng của lỗi, retry, restart, transaction.
5. Thiết kế metric xử lý event bằng Micrometer `Counter` và `Timer` với định nghĩa rõ ràng, không nhầm metric tự tạo với metric có sẵn của Modulith.
6. Đọc các tình huống “publish tăng nhưng xử lý không tăng”, “retry làm attempts tăng”, “số bản ghi completed khác số metric”.
7. Kết hợp counters, publication registry, logs, module entry spans và module graph để chẩn đoán sự cố event-driven.

## 2. Xác định đúng bốn đơn vị đếm

Đây là điểm xuất phát quan trọng nhất:

| Đơn vị | Khi nào tăng/thay đổi? | Nó đại diện cho cái gì? |
| --- | --- | --- |
| **Event published** | Khi ứng dụng công bố một event thông qua cơ chế được instrument | Một lần **công bố** sự kiện |
| **Publication record theo listener** | Khi registry đăng ký event cho một listener đích đủ điều kiện | Một **nghĩa vụ giao event cho một listener** |
| **Listener attempt** | Khi một listener bắt đầu/thực hiện một lần xử lý | Một **lượt thử** xử lý, có thể bao gồm retry |
| **Listener completion** | Khi cơ chế registry nhận diện listener đã hoàn tất thành công | Một publication đã **hoàn tất theo quy ước registry** |

Một event có thể dẫn đến **nhiều publication record** nếu có nhiều listener transactional đủ điều kiện. Một publication record có thể có **nhiều attempt** nếu bị lỗi rồi resubmit. Một attempt có thể thất bại nhưng lần sau thành công; do đó:

~~~text
events_published  ≠  publications_per_listener
publications_per_listener ≠ listener_attempts
listener_attempts ≠ successful_completions
~~~

Dấu `≠` ở đây biểu thị **các loại đại lượng không mặc nhiên tương đương**, chứ không khẳng định trị số của chúng luôn khác nhau.

### 2.1. Ví dụ ngắn: một event, hai listener

Hệ thống bán hàng phát `OrderPlaced` để hai application module xử lý:

- `inventory` nhận event để giữ hàng.
- `notification` nhận event để gửi thông báo.

~~~mermaid
flowchart LR
    O["Orders module<br/>publish OrderPlaced"]
    R["Event Publication Registry<br/>2 listener-target publications"]
    I["Inventory listener"]
    N["Notification listener"]
    M["Publication metric<br/>1 event phát"]
    O -->|"publish 1 event"| M
    O -->|"lưu bản ghi cho từng target<br/>nếu transaction hợp lệ"| R
    R --> I
    R --> N
    I -->|"hoàn tất"| C["COMPLETED"]
    N -->|"lỗi"| F["FAILED"]
    F -->|"resubmit"| N
~~~

Sơ đồ minh họa **một event được công bố một lần** và registry có thể lập **hai nghĩa vụ giao event**. Khi `inventory` thành công và `notification` lỗi, metric phát event không tự biến thành “0 sự kiện thành công” hoặc “1 sự kiện xử lý thất bại”.

Nếu publisher ở trong transaction, việc gọi `publishEvent(...)` có thể xảy ra **trước khi transaction commit**. Đếm publication tại điểm công bố không tự chứng minh transaction cuối cùng commit; việc lưu bản ghi vào registry cũng phụ thuộc transaction và công nghệ lưu trữ được cấu hình.

## 3. Metric công bố event có sẵn của Spring Modulith

Tài liệu **Spring Modulith Production-ready Features** mô tả **hai nhóm metric** được đăng ký cho domain event publication:

| Tên metric Micrometer | Loại | Ý nghĩa |
| --- | --- | --- |
| `module.events.published` | Counter | Tổng hợp các lần **công bố domain event** được nhận diện |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter | Số lần công bố một **loại event cụ thể** gắn với module được nhận diện |

Ví dụ khái niệm: nếu module `orders` công bố `OrderPlaced` ba lần trong một phiên chạy và instrumentation ghi nhận cả ba, counter cho event này tăng thêm ba. Counter **không kiểm tra từng listener đã thành công hay chưa**.

### 3.1. Các tag mặc định

Với metric tổng hợp `module.events.published`, tài liệu liệt kê những khóa **low cardinality**:

| Tag | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `module.event.type` | Loại event được công bố | `OrderPlaced` hoặc tên type được framework ghi nhận |
| `module.identifier` | Định danh kỹ thuật application module | `orders` |
| `module.name` | Tên hiển thị module | `Orders` |

Metric theo từng loại event có những tag module như `module.identifier` và `module.name`. Có thể bổ sung tag cho metric event cụ thể bằng `ModulithEventMetricsCustomizer` nếu cần phân nhóm nghiệp vụ; khi đó phải kiểm soát số lượng giá trị của mỗi tag.

**Không đưa `orderId`, email, UUID của event, user ID, request ID hay dữ liệu người dùng có số lượng giá trị không giới hạn vào metric tag.** Một nhãn giá trị duy nhất trên mỗi event làm tăng mạnh số time series và gây chi phí lưu trữ/thu thập.

### 3.2. Counter trả lời được điều gì?

Với `module.events.published`, bạn có thể hỏi:

- Module `orders` đang công bố những loại event nào?
- Trong 5 phút gần nhất, tốc độ công bố `OrderPlaced` có tăng mạnh không?
- Tỷ lệ công bố các loại event khác nhau thay đổi ra sao sau một phiên bản mới?
- Một nghiệp vụ thử nghiệm có đi qua đường publish event hay không?

Bạn **không** được suy trực tiếp:

- Listener nào đã chạy.
- Listener nào lỗi, thời lượng xử lý bao nhiêu.
- Có bao nhiêu event đang nằm trong backlog.
- Event đã được persist thành công ở mọi nơi.
- Toàn bộ workflow nghiệp vụ đã hoàn thành.

Tài liệu Spring Modulith gọi đó là **metric về event publication**, không phải “event-processing success rate”.

### 3.3. Tên Micrometer và tên xuất sang Prometheus

Tên metric ở Micrometer thường dùng dấu chấm như `module.events.published`. Khi dùng Prometheus, tên có thể được chuẩn hóa thành `module_events_published_total` hoặc dạng tương đương theo naming convention/exporter.

Vì vậy, khi kiểm tra lab:

1. Khám phá tên gốc ở `/actuator/metrics`.
2. Xem các sample thực sự trong `/actuator/prometheus`.
3. Viết PromQL dựa trên **tên thực tế** của hệ thống, tránh giả định chỉ có một cách chuyển đổi tên.
4. Nhớ rằng counter có thể reset khi process restart; dùng `rate(...)` hoặc `increase(...)` phù hợp thay vì coi giá trị raw là tổng số toàn lịch sử.

## 4. Metric xử lý event là gì?

**Metric xử lý** là một nhóm tín hiệu **theo góc nhìn consumer/listener**, thường gồm:

- **Attempts**: số lần một listener được gọi để xử lý event, kể cả retry.
- **Failures**: số lượt xử lý ném lỗi hoặc thất bại theo chính sách đã định nghĩa.
- **Method returns**: số lượt method listener kết thúc bình thường.
- **Duration**: thời gian một lượt listener xử lý (không tự bao gồm thời gian đợi trong queue).
- **Completion**: số publication được xác nhận hoàn tất theo quy ước registry.
- **Lag**: độ trễ từ lúc publish/commit tới lúc listener bắt đầu hoặc hoàn tất, nếu có dữ liệu timestamp và quy ước đo phù hợp.
- **Outstanding/backlog**: các publication chờ xử lý, đang chạy, thất bại hoặc cần resubmit theo phạm vi registry.

**Điểm cần nhớ:** Trong danh mục metric mặc định được Spring Modulith giới thiệu ở mục **Observability Metrics**, hai loại metric **có sẵn** được nêu là counters **publication**. Không nên tự khẳng định Modulith có sẵn tên metric như `module.events.processed`, `module.events.completed` hay `module.events.failed` chỉ vì ứng dụng đã bật observability.

Nếu dự án muốn đếm attempt, outcome hoặc thời gian listener, phải **xác minh instrumentation đã tồn tại** ở dự án hoặc tự xây dựng metric phù hợp (ví dụ qua Micrometer `Counter`, `Timer`, `Observation`). Trạng thái completion thật của transactional event còn được quản lý qua **Event Publication Registry**, là một nguồn dữ liệu khác với Micrometer metric.

### 4.1. So sánh trực tiếp

| Tiêu chí | Metric **công bố** | Metric **xử lý** |
| --- | --- | --- |
| Vị trí quan sát | Publisher / sự kiện được phát ra | Listener, executor, registry hoặc pipeline consumer |
| Câu hỏi | “Đã phát bao nhiêu?” | “Đã thử xử lý bao nhiêu, kết quả gì, mất bao lâu?” |
| Tên mặc định Modulith được tài liệu hóa | `module.events.published` và metric từng event type | Không mặc nhiên có một counter completion chung mang tên cố định |
| Một event có hai listener | Thường đếm **một publication** tại publisher | Có thể có **hai attempts** hoặc hơn, mỗi listener một lượt |
| Retry | Không thể dùng metric công bố để suy số lần retry | Attempts có thể tăng thêm cho mỗi retry |
| Lỗi listener | Publication counter vẫn có thể tăng | Counter outcome/registry thể hiện lỗi tùy instrumentation |
| Thời gian xử lý | Không có trong publication counter | Cần timer/span cho listener |
| Backlog | Không đo trực tiếp | Phải lấy từ registry, queue hoặc cơ chế quản lý trạng thái |

## 5. Spring Modulith Event Publication Registry bổ sung điều gì?

**Event Publication Registry** ghi nhận việc event được phát tới các **transactional event listener** mà registry theo dõi. Mặc định các listener có `@TransactionalEventListener` hoặc meta-annotation phù hợp được đưa vào cơ chế này; `@ApplicationModuleListener` là shortcut phổ biến cho listener transactional và bất đồng bộ.

Khi publish, registry có thể tạo **một bản ghi cho từng listener đích** trong transaction nghiệp vụ nguồn. Listener được bao bởi interceptor cập nhật trạng thái khi bắt đầu và hoàn tất. Khi xử lý lỗi, registry lưu thông tin để phục vụ retry/resubmission tùy phiên bản và cấu hình.

Đây là cách theo dõi **đời sống của publication theo listener**, khác với một counter tổng hợp ở phía publisher.

### 5.1. Lifecycle trong Spring Modulith 2.x

Spring Modulith từ 2.0 định nghĩa các trạng thái; 2.2 bổ sung `ABANDONED`:

| Status của `EventPublication` | Ý nghĩa |
| --- | --- |
| `PUBLISHED` | Publication đã được lưu, đang chờ hoặc sắp được xử lý |
| `PROCESSING` | Listener đang thực hiện xử lý publication |
| `COMPLETED` | Listener hoàn tất thành công theo cơ chế completion của registry |
| `FAILED` | Listener ném exception hoặc publication bị đánh dấu thất bại bởi cơ chế phát hiện stale |
| `RESUBMITTED` | Publication lỗi đã được đưa lại vào hàng chờ xử lý |
| `ABANDONED` (2.2+) | Publication bị từ bỏ sau thất bại theo `AbandonPolicy`, không còn được retry theo cơ chế thông thường |

~~~mermaid
stateDiagram-v2
    [*] --> PUBLISHED
    PUBLISHED --> PROCESSING: listener nhận việc
    PROCESSING --> COMPLETED: hoàn tất
    PROCESSING --> FAILED: ném lỗi
    FAILED --> RESUBMITTED: resubmit
    RESUBMITTED --> PROCESSING: thử lại
    FAILED --> ABANDONED: abandon policy (2.2+)
    COMPLETED --> [*]
    ABANDONED --> [*]
~~~

Sơ đồ cho biết **một vòng đời điển hình**; trạng thái stale/crash/recovery có thể tạo thêm các trường hợp khác. Đặc biệt, khi crash xảy ra giữa các lần cập nhật, trạng thái tồn tại trong store có thể khác điều bạn dự đoán từ một log đơn lẻ.

### 5.2. Registry theo dõi số lần xử lý và resubmission

Trong 2.x, mỗi publication còn có thông tin:

- `getCompletionAttempts()`: số lần listener được thử gọi, tăng khi chuyển sang `PROCESSING`; có thể vẫn ghi nhận attempt trong trường hợp process crash.
- `getLastResubmissionDate()`: thời điểm resubmit gần nhất, nếu có.
- Các API như `IncompleteEventPublications` và `FailedEventPublications` để tìm/resubmit các publication theo trạng thái và chính sách.

Những thuộc tính này giúp phân biệt **“một event đã phát một lần”** với **“một listener đã được thử xử lý ba lần”** mà không tự suy từ metric publication.

### 5.3. Vì sao không lấy tổng bản ghi `COMPLETED` làm metric hoàn tất vĩnh viễn?

Registry có **completion mode**:

- `UPDATE`: mặc định ghi completion timestamp và giữ bản ghi, trừ khi bị dọn dẹp sau đó.
- `DELETE`: xóa bản ghi sau khi hoàn tất; API liệt kê publication đã hoàn tất không còn thấy những bản ghi này.
- `ARCHIVE`: chuyển publication hoàn tất sang kho lưu trữ/archived record để vẫn có thể truy vấn theo cơ chế tương ứng.

Vì thế, số bản ghi `COMPLETED` hiện tại là **ảnh chụp trạng thái theo chính sách lưu trữ**, không phải counter tăng mãi. Nếu cần lịch sử tần suất xử lý, hãy có instrumentation/tổng hợp có kiểm soát, hoặc truy vấn kho lịch sử phù hợp với retention.

## 6. Bảng tình huống: một event, hai listener, một retry

Giả sử hệ thống có `inventory` và `notification`, cả hai đều đăng ký transactional listener cho `OrderPlaced`. Publisher gọi `publishEvent(new OrderPlaced(...))` **một lần** trong transaction được commit thành công.

Diễn biến minh họa:

| Mốc | Hành động | Registry cho `inventory` | Registry cho `notification` |
| --- | --- | --- | --- |
| T0 | `orders` công bố `OrderPlaced` | `PUBLISHED` | `PUBLISHED` |
| T1 | Inventory được gọi lần đầu và thành công | `COMPLETED` | `PUBLISHED` |
| T2 | Notification gọi lần đầu và ném lỗi | `COMPLETED` | `FAILED` |
| T3 | Notification được resubmit | `COMPLETED` | `RESUBMITTED` |
| T4 | Notification gọi lần hai, hoàn tất | `COMPLETED` | `COMPLETED` |

Giả sử các **custom processing metrics** được instrument theo từng lượt method listener:

| Đại lượng sau T4 | Giá trị kỳ vọng của ví dụ | Lý do |
| --- | ---: | --- |
| Số lần **publish event gốc** | **1** | Chỉ một lệnh phát `OrderPlaced` của publisher |
| Publication records được tạo cho listener | **2** | Hai listener transactional đủ điều kiện |
| Attempts của `inventory` | **1** | Xử lý thành công ngay lần đầu |
| Attempts của `notification` | **2** | Một lần lỗi, một lần retry thành công |
| Tổng listener attempts | **3** | 1 + 2 |
| Lượt listener method kết thúc bình thường | **2** | Inventory lần đầu; Notification lần retry |
| Lượt listener method ném exception | **1** | Notification lần đầu |
| Publication cuối cùng ở `COMPLETED` | **2** | Hai nghĩa vụ đã hoàn tất, nếu chưa bị dọn/xóa bản ghi |

**Giả định rõ:** Lượt retry ở T3 xử lý lại một **publication đã lưu** mà không tạo thêm một lời gọi `ApplicationEventPublisher.publishEvent(...)` độc lập. Nếu ứng dụng **thật sự publish lại event như event mới**, publication metric có thể tăng thêm. Không suy hành vi của tất cả retry strategies chỉ từ bảng này.

**Hệ quả chính:** Đem số “published = 1” chia cho “successful listener calls = 2” để tính success rate là **sai mẫu số**. Một bên đếm **event gốc**, bên kia đếm **lượt xử lý trên nhiều listener**.

## 7. Ví dụ Java: publisher và hai consumer

Ví dụ sau minh họa application modules theo package `com.example.shop.orders`, `com.example.shop.inventory` và `com.example.shop.notification`. Phần lưu đơn hàng và kết nối email/DB được rút gọn để tập trung vào vị trí đặt instrumentation.

### 7.1. Công bố sự kiện trong module `orders`

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId) {}
~~~

~~~java
// com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void placeOrder(UUID orderId) {
        // Minh họa: lưu đơn hàng trong transaction tại đây.
        events.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

Với Spring Modulith observability được bật, publication của `OrderPlaced` có thể làm tăng `module.events.published`. Lệnh này **chưa nói listener nào đã chạy**, vì `@ApplicationModuleListener` thường được thực hiện bất đồng bộ sau khi transaction nguồn commit.

### 7.2. Consumer `inventory` với custom metrics theo từng attempt

Ví dụ dưới đây cố ý đặt tên metric ứng dụng bắt đầu bằng `shop.` để phân biệt với `module.events.published` **do framework cung cấp**.

~~~java
// com/example/shop/inventory/InventoryListener.java
package com.example.shop.inventory;

import com.example.shop.orders.OrderPlaced;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryListener {

    private final MeterRegistry meters;
    private final StockReservation stock;

    InventoryListener(MeterRegistry meters, StockReservation stock) {
        this.meters = meters;
        this.stock = stock;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        long started = System.nanoTime();
        String outcome = "returned";

        try {
            stock.reserve(event.orderId());
        } catch (RuntimeException exception) {
            outcome = "threw";
            throw exception; // Để registry thấy lỗi và áp dụng chính sách retry.
        } finally {
            // Đếm MỖI lượt gọi method, kể cả lượt retry.
            Counter.builder("shop.event.listener.attempts")
                    .description("Listener invocation attempts")
                    .tag("listener", "inventory.order-placed")
                    .tag("outcome", outcome)
                    .register(meters)
                    .increment();

            // Đo thời gian xử lý MỖI lượt gọi method, không gồm thời gian chờ.
            Timer.builder("shop.event.listener.duration")
                    .description("Elapsed time inside the listener method")
                    .tag("listener", "inventory.order-placed")
                    .tag("outcome", outcome)
                    .register(meters)
                    .record(System.nanoTime() - started, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

`StockReservation` là một nghiệp vụ/service trong module inventory với method `reserve(UUID orderId)`; ứng dụng thật cần cung cấp implementation của nó. Bài tập code này minh họa **vị trí đo** chứ không phải một mẫu xử lý tồn kho hoàn chỉnh.

### 7.3. Định nghĩa chính xác outcome trong ví dụ

Hai nhãn `outcome=returned` và `outcome=threw` được chọn có chủ đích:

- **`returned`**: method `on(...)` kết thúc bình thường ở phần code được instrument.
- **`threw`**: method `on(...)` ném `RuntimeException` ra ngoài.

**`returned` không được mặc định đổi tên thành `COMPLETED` của Event Publication Registry.** Method có thể trả về trước khi interceptor/transaction completion được ghi nhận; cũng có thể còn công việc bất đồng bộ bên ngoài không được chờ. Nếu muốn metric biểu thị **registry completion thành công**, phải instrument tại đúng chỗ cập nhật trạng thái hoặc đo từ nguồn dữ liệu trạng thái được lưu, có xử lý giao dịch và retry chính xác.

Tương tự, nếu nghiệp vụ bên trong **catch rồi nuốt exception**, instrumentation trên sẽ gắn `returned`, dù có thể có thất bại nghiệp vụ cần được đo riêng. Hãy định nghĩa outcome theo nhu cầu sản phẩm, không chỉ dựa vào exception nếu trạng thái domain có nhiều kết quả khác nhau.

### 7.4. Vì sao không chỉ dùng một metric counter?

`Timer` của Micrometer có `count` và `totalTime`, nên bản thân timer đã có số lần được ghi nhận. Counter `shop.event.listener.attempts` trong ví dụ là **một lựa chọn để minh họa rõ attempts và outcome**; trên production, có thể bỏ counter trùng nghĩa và dùng `Timer.count` nếu cách xuất dữ liệu đã đáp ứng nhu cầu.

Cả counter và timer đều là metric **được ứng dụng định nghĩa**, không phải metric event-processing tự động của Spring Modulith.

## 8. Bật metrics và đọc dữ liệu trong Actuator

Ví dụ cho ứng dụng Spring Boot có quản lý phiên bản tương thích với Modulith:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Modulith actuator + observability, bao gồm publication metrics.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Micrometer registry nếu muốn Prometheus scrape.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Triển khai registry bền vững khi dùng transactional event publication
    // bằng JDBC; cần datasource và DB được cấu hình cho dự án.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-jdbc'
}
~~~

**Phân biệt dependency:** `spring-modulith-starter-insight` hỗ trợ module Actuator/observability; `spring-modulith-starter-jdbc` thiết lập implementation persistence cho **Event Publication Registry** dùng JDBC, ngoài ra cần data source/transaction manager và cấu hình DB phù hợp. **Metrics không thay thế event registry, và event registry không tự là Prometheus registry.**

Ví dụ `application.yml` cho lab có Actuator và Prometheus:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,modulith
~~~

Sau khi khởi động và thực sự gọi nghiệp vụ publish event:

~~~bash
# Danh sách tên metric đang có trong Micrometer.
curl -fsS http://localhost:8080/actuator/metrics

# Counter gốc do Spring Modulith công bố.
curl -fsS http://localhost:8080/actuator/metrics/module.events.published

# Custom listener attempts, chỉ có sau khi listener đã được gọi.
curl -fsS http://localhost:8080/actuator/metrics/shop.event.listener.attempts

# Timer do ứng dụng tự instrument cho listener.
curl -fsS http://localhost:8080/actuator/metrics/shop.event.listener.duration

# Kiểm tra tên được xuất sang Prometheus thực tế.
curl -fsS http://localhost:8080/actuator/prometheus | grep 'module_events_published'
curl -fsS http://localhost:8080/actuator/prometheus | grep 'shop_event_listener'
~~~

Lưu ý:

1. Nếu metric chưa được đăng ký vì chưa có event/attempt, tên đó có thể chưa hiện trong `/actuator/metrics`.
2. `/actuator/prometheus` cần registry Prometheus và web exposure phù hợp; `/actuator/metrics` có thể vẫn hoạt động khi không cài Prometheus.
3. Tên đã được chuẩn hóa của Prometheus, các suffix như `_total` và `_seconds_count` phụ thuộc convention/exporter; hãy quan sát thực tế trước khi viết truy vấn.
4. Một lần gọi không đồng nghĩa counter đã persist lâu dài: counter thường sống trong process; Prometheus scrape theo chu kỳ và cần lưu trữ ngoài để xem lịch sử.
5. Với listener bất đồng bộ, phép đo custom có thể xuất hiện **sau** publication metric một khoảng thời gian.

### 8.1. Ví dụ PromQL cho tốc độ publish và processing

Tên dưới đây là **minh họa cho cách đặt tên sau khi đã xác minh endpoint Prometheus**:

~~~promql
# Số publication trong cửa sổ 5 phút theo module/event type.
sum by (module_identifier, module_event_type) (
  increase(module_events_published_total[5m])
)
~~~

~~~promql
# Tốc độ attempt listener theo outcome trong 5 phút.
sum by (listener, outcome) (
  rate(shop_event_listener_attempts_total[5m])
)
~~~

~~~promql
# Thời gian xử lý trung bình trên các attempt được timer ghi nhận.
sum(rate(shop_event_listener_duration_seconds_sum[5m]))
/
sum(rate(shop_event_listener_duration_seconds_count[5m]))
~~~

**Phép chia cuối** chỉ có ý nghĩa khi mẫu đo đủ và mẫu số khác 0, và phải lọc cùng nhóm listener/outcome nếu muốn một phân tích riêng. Đây là **thời gian bên trong method listener**, không phải độ trễ từ publish đến complete. Nếu muốn p95, cần cấu hình histogram/SLO buckets tương ứng; không thể tự lấy percentile từ trung bình.

### 8.2. Các dashboard nên tách riêng

Một dashboard sự kiện hữu ích nên phân biệt:

| Panel | Nguồn | Đơn vị và cách đọc |
| --- | --- | --- |
| Event publications/min | `module.events.published` | Event được phát theo khoảng thời gian |
| Listener attempts/min | `shop.event.listener.attempts` (custom) | Lượt gọi listener, gồm retry |
| Listener throw rate | Custom metric `outcome=threw` | Lượt method ném lỗi, không nhất thiết là lỗi cuối cùng của publication |
| Listener latency p95 | Timer/histogram custom | Độ trễ method listener; không gồm queue lag nếu không instrument |
| Outstanding publications | Event Publication Registry / truy vấn trạng thái | Snapshot backlog theo trạng thái, không phải Counter |
| End-to-end publish→complete lag | Đo riêng bằng timestamp publication/completion | Thời gian từ mốc publication đã định nghĩa đến hoàn tất |
| Module interaction trace | Micrometer Tracing / module entry spans | Một giao dịch cụ thể đi qua các module nào |

## 9. Phân biệt metric xử lý với trạng thái registry

Một metric đã ghi `outcome=returned` thường tăng **ngay sau khi method hoàn tất**. Nhưng registry cập nhật publication status theo lifecycle và chiến lược transaction; vì vậy cần tách hai định nghĩa:

- **Method-level metrics:** “Một lần listener chạy xong phần thân method và trả bình thường/ném exception”.
- **Registry-level completion:** “Một publication dành cho listener đã hoàn tất theo quy tắc commit/completion của registry”.

Khi tính các chỉ số như **completion rate**, mẫu số và cửa sổ thời gian phải được chọn rõ ràng. Không thể lấy:

~~~text
completed_records_now / all_published_events_since_start
~~~

rồi gọi đó là “tỷ lệ thành công” nếu có nhiều listener mỗi event, retry, xóa publication theo `DELETE`, purge lịch sử hoặc event mới đang chờ xử lý.

### 9.1. Một tỷ lệ đúng cần gắn với đơn vị

Ví dụ bài toán: “Trong một cohort gồm 500 **publication-target** được tạo ở ngày D, bao nhiêu publication-target cuối cùng hoàn tất trong 1 giờ?”

Ta có thể định nghĩa:

\[
\text{completion rate}_{1h}
=
\frac{\text{số publication-target của cohort D đạt COMPLETED trong 1h}}
{\text{số publication-target hợp lệ của cohort D}}
\]

Đây là **tỷ lệ theo cohort và từng listener-target**, khác với tỷ lệ `returned` trên mọi attempt trong 1 giờ. Cần dữ liệu lịch sử đủ để biết cohort, completion timestamp và trạng thái cuối cùng; tùy `completion-mode` mà registry hiện tại có hoặc không giữ lại thông tin.

Nếu bài toán chỉ là “Phần trăm lượt method listener **không ném exception** trong 5 phút”, định nghĩa từ custom metrics lại khác:

\[
\text{method return ratio}
=
\frac{\text{attempts gắn outcome=returned}}
{\text{tất cả attempts được đo}}
\]

Cả hai tỷ lệ đều có ích, nhưng chúng đo **hai tầng khác nhau** và không nên mang cùng tên “event success rate”.

### 9.2. Backlog là đại lượng tại một thời điểm

Một snapshot có thể đếm số publication đang ở `PUBLISHED`, `PROCESSING`, `FAILED`, `RESUBMITTED` hoặc `ABANDONED` theo yêu cầu vận hành. Đây là **gauge/state count** phù hợp hơn counter, vì số lượng tồn đọng có thể tăng hoặc giảm.

Registry có cơ chế staleness monitor để chuyển các publication ở trạng thái tồn đọng quá lâu sang `FAILED` theo cấu hình. Điều đó **không nhất thiết tạo ra một lượt listener attempt thất bại mới**. Nếu lấy số lượng `FAILED` làm “số lần exception”, bạn sẽ đếm sai nguyên nhân lỗi.

## 10. Tracing và context propagation bổ sung điều gì?

Metric trả lời các câu hỏi **bao nhiêu lần** và **tốc độ ra sao**. **Module entry spans** giúp xác định **một lần listener cụ thể đã chạy qua đâu và mất bao lâu** nếu tracing được bật.

Spring Modulith module entry spans có các thuộc tính như:

| Attribute | Tác dụng khi đọc listener |
| --- | --- |
| `module.identifier` | Listener thuộc application module nào, ví dụ `inventory` |
| `module.name` | Tên module |
| `module.invocation-type` | Phân biệt `event listener` với `bean` |
| `module.method` | Entry method của module được gọi |

Ví dụ một workflow:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orders
    participant R as Publication Registry
    participant I as Inventory
    C->>O: placeOrder()
    O->>R: publish OrderPlaced / lưu target publication
    O-->>C: HTTP response
    R-->>I: dispatch listener (async)
    Note over I: module entry span<br/>invocation-type=event listener
    I-->>R: complete hoặc fail
~~~

Không mặc định span của listener thuộc cùng trace với HTTP request: `@ApplicationModuleListener` chạy bất đồng bộ, context có thể không được truyền hoặc được khôi phục sau commit. Spring Boot/Micrometer cần **context propagation** qua executor/transport phù hợp nếu muốn nối ngữ cảnh.

**Phân biệt ba điều:**

- Publication metric tăng: event **được phát** ở phía publisher.
- Listener span xuất hiện: một lượt thực thi **được instrument và lấy mẫu**.
- Registry publication đạt `COMPLETED`: listener-target **đã được đánh dấu hoàn tất**.

Ba điều này cung cấp những bằng chứng khác nhau, không điều nào tự thay thế hoàn toàn hai điều còn lại. Sampling có thể làm một listener span không xuất hiện dù listener đã chạy; metrics method và trạng thái registry vẫn có thể cung cấp thông tin độc lập.

## 11. Liên hệ module graph và Actuator

**Module graph** của Spring Modulith mô tả phụ thuộc giữa các application module. Một listener ở `inventory` nhận `OrderPlaced` từ `orders` có thể tạo quan hệ dependency kiểu `EVENT_LISTENER` **inventory → orders**, vì `inventory` tham chiếu event type do `orders` công khai.

Ngược lại, **hướng sự kiện khi chạy** là `orders phát → inventory nhận`.

`GET /actuator/modulith` có thể cho biết module names, base packages và các outgoing dependencies, nhưng không trả số lượt publish/attempt/completion hay trạng thái lịch sử của publication.

Bởi vậy, khi cần xác minh “module inventory có đăng ký quan hệ event với orders hay không”, dùng module graph/Actuator và code. Khi cần biết “listener đã xử lý event của order này chưa”, dùng registry/logs/traces; không kết luận từ cạnh `EVENT_LISTENER` đơn thuần.

## 12. Những tình huống chẩn đoán thường gặp

| Hiện tượng | Diễn giải có thể có | Bước kiểm tra kế tiếp |
| --- | --- | --- |
| `module.events.published` tăng, listener attempts không tăng | Event chưa đến listener; chưa đủ điều kiện trigger; transaction chưa commit; listener async chưa chạy; custom instrumentation thiếu | Kiểm tra transactional listener, registry status, log, executor, thời gian chờ |
| Published = 1, attempts = 2 | Có thể một event có 2 listener hoặc một listener retry 2 lần | Tách theo nhãn listener và kiểm tra publication-target/attempt count |
| Published tăng, `FAILED` trong registry tăng | Có listener ném exception hoặc stale publication bị đánh dấu lỗi | Đọc exception logs và nguyên nhân `FAILED`; đừng quy mọi FAILED cho exception mới |
| Attempts `threw` tăng, sau đó `returned` cũng tăng | Listener có thể đã retry và hồi phục | Đối chiếu cùng publication ID và trạng thái cuối cùng |
| `COMPLETED` records giảm dù listener vẫn thành công | Registry dùng `DELETE`, archive hoặc dọn dữ liệu | Kiểm tra completion mode, retention và kho lưu trữ |
| Published tăng nhưng Prometheus không có metric | Chưa có exporter/registry, endpoint chưa expose, naming khác, scrape bị gián đoạn | Xem `/actuator/metrics` và `/actuator/prometheus` trước, rồi target scrape |
| Listener method `returned` nhưng business state sai | Lỗi bị catch, side effect bên ngoài thất bại, transaction hoặc outbox chưa hoàn tất | Kiểm tra business invariant, DB commit, downstream acknowledgement |
| Event được publish trước crash, không thấy listener | Transaction rollback hoặc publication persistence/recovery chưa được cấu hình đúng | Kiểm tra transaction outcome, registry store và cơ chế resubmission |
| Metric đúng nhưng trace listener không có | Trace chưa bật/sampling bỏ/thiếu context propagation | Kiểm tra tracer/exporter/sampling và async executor |
| Số events và records khác nhau | Nhiều target listeners hoặc chỉ một tập listener được registry theo dõi | Kiểm tra listener registration và `registry-trigger-annotation` |

### 12.1. Phân biệt lỗi application với lỗi quan sát

Khi một metric không xuất hiện, có hai nhóm nguyên nhân rất khác nhau:

1. **Nghiệp vụ không tạo ra hành động cần đo**: không publish, listener không chạy, transaction rollback, hoặc chưa có retry.
2. **Hành động xảy ra nhưng dữ liệu quan sát không đi tới dashboard**: meter chưa được đăng ký, thiếu Micrometer registry, exporter lỗi, Prometheus chưa scrape hoặc tag/tên metric khác dự kiến.

Đừng sửa nghiệp vụ chỉ vì một truy vấn dashboard không có kết quả. Kiểm tra từ nguồn dữ liệu gần ứng dụng nhất rồi mới sang exporter/backend.

### 12.2. Nên cảnh báo điều gì?

Một số điều kiện cảnh báo hữu ích:

- **Publication rate giảm bất thường** khi lưu lượng nghiệp vụ vẫn bình thường.
- **Attempt failure rate** của một listener tăng so với ngưỡng ổn định của nó.
- **Processing duration p95** tăng kéo dài.
- **Outstanding/FAILED/stale publications** tăng hoặc không giảm theo chu kỳ.
- **Oldest outstanding age** vượt ngưỡng vận hành.
- **Retry attempts** của một publication tăng vượt ngưỡng cho phép.

Không nên chỉ cảnh báo “published > processed trong đúng một phút” mà không tính đến số listeners, độ trễ async, retry và cửa sổ thống kê.

## 13. Thiết kế metric theo nguyên tắc rõ ràng

### 13.1. Chọn đơn vị và tên ngay từ đầu

Thay vì đặt chung chung `events_processed`, nên xác định:

| Metric đề xuất (do ứng dụng tự định nghĩa) | Đơn vị | Ngữ nghĩa |
| --- | --- | --- |
| `shop.event.listener.attempts` | Counter | Một lượt method listener được gọi và kết thúc khối được instrument |
| `shop.event.listener.duration` | Timer | Elapsed time của mỗi lượt method listener |
| `shop.event.listener.pending` | Gauge nếu có nguồn trạng thái hợp lệ | Số publication-target chưa hoàn tất ở thời điểm quan sát |
| `shop.event.listener.oldest.pending.age` | Gauge/derived metric | Độ tuổi của publication chưa hoàn tất lâu nhất |
| `shop.event.listener.completed` | Counter tự tạo nếu có hook tin cậy | Số lần registry xác nhận completion trong thời gian đo |

**Không thể dùng `Timer` trong method để tự khẳng định tính chính xác của `shop.event.listener.completed`.** Khi yêu cầu mức chính xác là “registry đã xác nhận completed”, thiết kế phải đo theo trạng thái registry hoặc một transactionally consistent event/hook tương ứng.

### 13.2. Nhãn (tags) nên có cardinality thấp

Nhãn được khuyến nghị: `event_type` (tập loại event hữu hạn), `listener` (tên cố định), `module` (module ID), `outcome` (enum nhỏ), `attempt_kind` (original/retry nếu có cơ sở xác định).

Tránh: `order_id`, `event_id`, `publication_id`, `user_id`, email, URL có token hoặc thông tin khách hàng. Những định danh này có thể đi vào **structured logs** với quy định bảo mật và quyền truy cập phù hợp; không biến chúng thành time-series labels.

### 13.3. Định nghĩa rõ khi ghi metric

Với mục tiêu “đếm mỗi lần bắt đầu xử lý” thì meter nên increment ngay **đầu** listener; với mục tiêu “đếm mỗi lần kết thúc lượt xử lý” thì increment trong `finally` như ví dụ. Hai cách khác nhau khi process crash. Nếu muốn đếm chính xác các attempts vẫn dang dở sau crash, cần **registry completion attempts** hoặc một nguồn state durable; một in-memory counter trong JVM không giải quyết được.

Tương tự, timer đặt bên trong listener method không bao gồm **queue wait time** từ publish đến listener bắt đầu. Muốn đo processing lag end-to-end cần mốc thời gian publication đáng tin cậy và thời điểm hoàn tất cuối cùng, kèm quy tắc xử lý retry.

## 14. Bài thực hành

### Bài 1 — Nhận diện đại lượng

Xét ba câu:

1. “Trong 5 phút gần nhất, `orders` công bố bao nhiêu `OrderPlaced`?”
2. “`inventory` đã thử xử lý `OrderPlaced` bao nhiêu lượt, gồm cả retry?”
3. “Bao nhiêu publication-target của `notification` đã đạt `COMPLETED`?”

Hãy chọn nguồn phù hợp cho từng câu và giải thích vì sao không lấy cùng một counter trả lời cả ba.

**Gợi ý:** (1) built-in publication counter; (2) custom attempt metric hoặc registry attempt history; (3) registry/completion instrumentation theo listener target.

### Bài 2 — Tính số đếm khi có fan-out và retry

Một event `OrderPlaced` được publish một lần và có ba listener `inventory`, `notification`, `billing`. `inventory` thành công lần 1, `notification` thành công lần 2, `billing` lỗi cả 3 lần rồi bị `ABANDONED`. Hãy tính:

- Số original event published.
- Số target publications được tạo, giả định cả ba được registry theo dõi.
- Tổng attempts.
- Số lượt thành công và thất bại ở **method-level**.
- Số publication-target hoàn tất và bị abandon ở **registry-level**.

**Đáp án định hướng:** 1 publication gốc; 3 target publications; attempts = `1+2+3=6`; method-level thành công 2, thất bại 4; registry-level `COMPLETED=2`, `ABANDONED=1` theo giả định phiên bản 2.2 và chính sách abandon áp dụng.

### Bài 3 — Instrument listener

Tạo một listener `@ApplicationModuleListener` nhận `OrderPlaced`. Dùng Micrometer `Counter` và `Timer` đặt tại vị trí method như mục 7. Chạy ba lượt: thành công, ném lỗi và retry thành công. Đọc `/actuator/metrics`; trình bày sự khác biệt giữa `returned`/`threw` và `COMPLETED`/`FAILED` của registry.

### Bài 4 — Tách queue lag khỏi processing duration

Giả sử:

~~~text
Event được lưu:          10:00:00.000
Listener bắt đầu:        10:00:03.000
Listener kết thúc:       10:00:03.200
Publication completed:  10:00:03.250
~~~

Tính:

1. Thời gian chờ trước khi listener bắt đầu.
2. Thời gian chạy method listener.
3. Thời gian từ lưu publication đến registry completion.

**Đáp án:** chờ 3.000 ms; method duration 200 ms; end-to-end 3.250 ms. Đây là **ba phép đo khác nhau**, cần chọn đúng mốc để phù hợp mục tiêu phân tích.

### Bài 5 — Chẩn đoán registry và metric khác nhau

Ứng dụng dùng `spring.modulith.events.completion-mode=DELETE`. Counter custom `shop.event.listener.attempts{outcome="returned"}` tăng đều, nhưng `CompletedEventPublications` không trả bản ghi. Hãy giải thích vì sao có thể là hành vi đúng, và đề xuất nguồn dữ liệu phù hợp nếu tổ chức cần báo cáo completion theo ngày.

### Bài 6 — Đối chiếu module graph, metrics và tracing

Kiểm tra một luồng `orders → OrderPlaced → inventory`:

1. Dùng `/actuator/modulith` xác định dependency listener ở mức module.
2. Dùng `module.events.published` kiểm tra có publication được ghi nhận.
3. Dùng custom metrics hoặc registry kiểm tra listener attempts và final status.
4. Nếu có tracing, tìm module entry span `inventory` và đọc `module.invocation-type=event listener`.
5. Giải thích trường hợp trace bị sampling bỏ nhưng metrics/registry vẫn có dữ liệu.

## 15. Câu hỏi ôn tập

1. `module.events.published` đo publication hay completion của listener?
2. Một event có ba listener thì publisher counter có bắt buộc tăng ba không?
3. Publication record của registry được tạo theo event gốc hay theo từng listener target?
4. Vì sao retry có thể làm listener attempts tăng nhưng original publication count không tăng?
5. `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED` và `RESUBMITTED` có ý nghĩa gì?
6. `ABANDONED` áp dụng từ phiên bản nào và khác `COMPLETED` ra sao?
7. `getCompletionAttempts()` giúp trả lời câu hỏi gì?
8. Vì sao `DELETE` completion mode khiến số bản ghi completed hiện tại không đại diện lịch sử success?
9. Một method listener trả bình thường có luôn bảo đảm registry đã chuyển `COMPLETED` không?
10. Làm thế nào đo queue lag khác với method execution duration?
11. Khi Prometheus không có metric, cần kiểm tra những lớp nào trước khi kết luận event không được phát?
12. Vì sao nên sử dụng low-cardinality tags trên metrics?
13. Khi nào dùng module entry spans thay vì event publication counter?
14. Vì sao `EVENT_LISTENER` trên module graph không chứng minh listener đã xử lý thành công?

## 16. Ghi nhớ

**Metric công bố đếm lần event được phát; metric xử lý đếm công việc của listener theo định nghĩa đã thiết kế.** Trong Spring Modulith, `module.events.published` và metric theo từng event type là các **publication counters có sẵn**; chúng không phải bộ đếm listener success/failure.

Muốn biết xử lý đến đâu, hãy phân biệt **mỗi original event**, **mỗi publication-target** và **mỗi listener attempt**; dùng **Event Publication Registry** để theo dõi lifecycle, attempts, completion, failed/resubmitted/abandoned theo phiên bản, và dùng **Micrometer custom metrics** cho throughput/latency/outcome của listener khi cần. **Tracing** cho biết một lần xử lý cụ thể đã đi qua module nào; **Actuator/module graph** mô tả ranh giới và dependency; **context propagation** giúp nối các span khi xử lý bất đồng bộ.

### Tài liệu tham khảo chính thức

- [Spring Modulith — Production-ready Features: Observability Metrics, `module.events.published`](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith — Working with Application Events: `@ApplicationModuleListener` và Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Modulith — EventPublicationRegistry JavaDoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html).
- [Spring Boot — Metrics, Actuator và Micrometer registries](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Boot — Observability và context propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Micrometer — Concepts: Counters, Timers và Dimensional Metrics](https://docs.micrometer.io/micrometer/reference/concepts/index.html).
