# Event payload và module boundary

## 1. Payload của sự kiện liên quan gì đến ranh giới module?

Trong ứng dụng Spring Modulith, **event payload** là dữ liệu mà một module công bố khi có sự kiện nghiệp vụ xảy ra. Chẳng hạn, khi khách hàng gửi đơn hàng, module `checkout` phát `OrderSubmitted`; module `inventory` nhận sự kiện để xử lý phần tồn kho của mình.

**Module boundary** (ranh giới module) quy định những kiểu dữ liệu, dịch vụ và quan hệ phụ thuộc nào được phép đi qua ranh giới đó. Vì module nhận thường cần biết **kiểu Java của event**, cấu trúc payload trở thành một phần của **hợp đồng công khai giữa các module**. Nếu payload chứa entity, repository hoặc kiểu nội bộ của module nguồn, event có thể tạo ra phụ thuộc kiến trúc sai dù hai module không gọi trực tiếp service của nhau.

Ví dụ:

~~~java
// Không nên: OrderEntity là kiểu nội bộ của checkout.
public record OrderSubmitted(OrderEntity order) {}
~~~

Module `inventory` buộc phải hiểu `OrderEntity` để xử lý `OrderSubmitted`. Như vậy một sự kiện tưởng như giúp giảm kết dính lại khiến module nhận phụ thuộc vào mô hình lưu trữ của module phát.

Một hợp đồng gọn hơn:

~~~java
// Nên: chỉ công bố dữ kiện mà module nhận được phép sử dụng.
public record OrderSubmitted(UUID orderId, Instant occurredAt) {}
~~~

Trong một trường hợp khác, nếu `inventory` thật sự cần số lượng và mã hàng để đặt giữ tồn kho, payload có thể gồm các dòng hàng bất biến. Mục tiêu không phải làm event **ít field nhất bằng mọi giá**, mà là làm event **chỉ chứa dữ kiện nghiệp vụ cần thiết, ổn định và hợp lệ để công bố**.

Trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**, chủ đề này phục vụ mục tiêu kiểm chứng kiến trúc bằng `ApplicationModules`, thực hành `@ApplicationModuleTest`, kiểm thử event với transaction/database và thiết lập quality gate CI chống hồi quy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao event payload là một phần của API module.
2. Thiết kế payload bất biến, không rò rỉ entity hay đối tượng triển khai nội bộ.
3. Công bố kiểu event bằng `@NamedInterface` và giới hạn phụ thuộc với `allowedDependencies`.
4. Phân biệt phụ thuộc Java tại thời điểm biên dịch với việc phân phối event lúc chạy.
5. Kiểm thử hợp đồng event, kiểm thử ranh giới bằng `ApplicationModules.verify()` và kiểm thử phát event bằng `@ApplicationModuleTest`.
6. Xem xét tính tương thích, transaction, dữ liệu và trường hợp cần đưa event ra ngoài tiến trình.

## 2. Bốn yếu tố của một hợp đồng sự kiện tốt

| Yếu tố | Câu hỏi thiết kế | Hệ quả nếu bỏ qua |
| --- | --- | --- |
| **Ý nghĩa nghiệp vụ** | Event diễn tả điều gì đã xảy ra? | Dùng tên chung chung hoặc biến event thành lời gọi lệnh trá hình. |
| **Dữ liệu công khai** | Module nhận được phép biết những field nào? | Rò rỉ dữ liệu nhạy cảm hoặc chi tiết triển khai. |
| **Kiểu dữ liệu ổn định** | Field có phụ thuộc entity/proxy/service nội bộ không? | Phụ thuộc sai module, lỗi lazy loading, khó serialize. |
| **Ngữ nghĩa thời gian và phiên bản** | Sự kiện phản ánh thời điểm nào; thay đổi payload ra sao? | Listener hiểu nhầm trạng thái, hỏng consumer khi event thay đổi. |

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(Object)` có thể phát một POJO hoặc record; không bắt buộc kế thừa `ApplicationEvent`. Cơ chế này đưa **đối tượng Java** tới các listener trong cùng application context. Spring Modulith bổ sung mô hình module, kiểm thử, quản lý công bố event và các tiện ích liên quan; **nó không tự bảo đảm rằng mọi đối tượng được phát đều có payload phù hợp ranh giới kiến trúc**.

Một record thuần Java thường thích hợp để mô tả sự kiện:

- Thuộc tính phản ánh một **sự thật đã xảy ra**: `OrderSubmitted`, `PaymentReceived`.
- Field có kiểu rõ ràng: `UUID`, `String`, `int`, `BigDecimal`, `Instant`, hoặc value object thuộc API công khai.
- Không chứa `JpaRepository`, `EntityManager`, `ApplicationContext`, service, entity ORM, session hay proxy framework.
- Danh sách và cấu trúc lồng nhau được sao chép hoặc làm bất biến thực sự; bản thân `record` chỉ bảo đảm tính final của **tham chiếu field**, không tự làm bất biến object mà field trỏ tới.
- Không đưa thông tin cá nhân hoặc bí mật nghiệp vụ vào event nếu consumer không cần chúng.

### Chọn ID, snapshot hay value object?

| Dạng payload | Phù hợp khi | Cần chú ý |
| --- | --- | --- |
| **Chỉ có ID**: `OrderSubmitted(UUID orderId)` | Module nhận cần định danh để liên hệ dữ liệu của chính nó, hoặc có API truy vấn công khai phù hợp. | Không mặc nhiên cho phép module nhận truy cập trực tiếp entity/repository nội bộ của module phát. |
| **Snapshot tối thiểu**: ID, mã hàng, số lượng, thời điểm | Module nhận cần dữ kiện tại đúng lúc sự kiện xảy ra mà không gọi ngược module phát. | Dữ kiện có thể đã cũ so với trạng thái hiện tại; chọn field cẩn thận. |
| **Value object công khai** | Nhiều consumer dùng chung một khái niệm ổn định như `Money`. | Value object cũng phải thuộc một API được công bố; tránh kéo theo một đồ thị kiểu nội bộ. |
| **Entity/aggregate trực tiếp** | Hầu như không phù hợp cho giao tiếp qua module boundary. | Dễ rò rỉ persistence model, trạng thái có thể thay đổi, tăng kết dính và rủi ro serialize. |

Nếu chỉ truyền ID nhưng consumer phải lén truy cập bảng hoặc repository của module khác để lấy dữ liệu, thiết kế vẫn vi phạm boundary ở **đường đọc dữ liệu**. Hãy cân nhắc snapshot nhỏ hoặc API truy vấn công khai và kiểm tra quyền phụ thuộc tương ứng.

## 3. Ví dụ thiết kế API sự kiện giữa checkout và inventory

Giả sử ứng dụng có package gốc `com.example.shop` và hai module `checkout`, `inventory` được Spring Modulith nhận diện theo cấu trúc package mặc định:

~~~text
com.example.shop
├── ShopApplication.java
├── checkout
│   ├── CheckoutService.java
│   ├── events
│   │   ├── OrderSubmitted.java
│   │   └── package-info.java
│   └── internal
│       ├── OrderEntity.java
│       └── OrderRepository.java
└── inventory
    ├── package-info.java
    └── StockReservationListener.java
~~~

Các package con `checkout.internal` và `checkout.events` đều thuộc module `checkout`, nhưng chỉ `checkout.events` được chủ động công bố ra ngoài bằng named interface. Trong cấu hình phát hiện module tùy chỉnh, cần xác nhận ranh giới thực tế từ mô hình `ApplicationModules`.

~~~mermaid
flowchart LR
    subgraph C["Module checkout"]
        CS["CheckoutService"]
        E["events.OrderSubmitted<br/>public contract"]
        I["internal.OrderEntity<br/>internal implementation"]
        CS -->|"publishEvent"| E
        CS --> I
    end
    subgraph V["Module inventory"]
        L["StockReservationListener"]
    end
    E -->|"được phép import và lắng nghe"| L
~~~

Mũi tên từ event công khai đến listener biểu diễn **quan hệ sử dụng kiểu payload**. Hành vi phát nằm trong `checkout`; cơ chế phân phối thực tế do Spring đảm nhiệm. `inventory` không cần import `checkout.internal.OrderEntity`.

### 3.1. Định nghĩa payload bất biến

File `checkout/events/OrderSubmitted.java`:

~~~java
package com.example.shop.checkout.events;

import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public record OrderSubmitted(
        UUID orderId,
        List<Line> lines,
        Instant occurredAt
) {
    public OrderSubmitted {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(occurredAt, "occurredAt");

        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must contain items");
        }
    }

    public record Line(String sku, int quantity) {
        public Line {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }
}
~~~

Vì `Line` là record chỉ chứa `String` và `int`, kết hợp với `List.copyOf(lines)` cho phép tránh việc caller thay đổi danh sách sau khi event được tạo. Nếu phần tử là một object có trạng thái thay đổi, `List.copyOf` **không** tự sao chép sâu các phần tử đó.

Ba field được chọn có lý do:

- `orderId`: giúp consumer nhận diện đơn hàng và chống xử lý trùng nếu có cơ chế lưu dấu.
- `lines`: là snapshot các mã SKU và số lượng mà `inventory` cần cho nhiệm vụ của mình, không chứa entity `OrderLineEntity`.
- `occurredAt`: ghi lại thời điểm sự kiện nghiệp vụ được tạo, không tự nói lên thời điểm consumer đã xử lý.

Nếu hệ thống yêu cầu mã sự kiện độc lập, có thể bổ sung `eventId` được sinh tại nguồn để hỗ trợ idempotency. Không nên ngầm coi `orderId` luôn định danh duy nhất một lần công bố: một đơn hàng có thể phát nhiều event trong vòng đời.

### 3.2. Công bố package event thành named interface

File `checkout/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.checkout.events;
~~~

Spring Modulith mặc định xem các kiểu công khai trong **base package của module** là API của module; kiểu trong package con thường là chi tiết triển khai, trừ khi được công bố theo cơ chế như `@NamedInterface`. Không được đồng nhất từ khóa Java `public` với “được phép truy cập xuyên module”: class có thể `public` ở mức Java nhưng nằm ngoài API mà Spring Modulith chấp nhận.

Khai báo named interface giúp module `inventory` sử dụng `OrderSubmitted` như hợp đồng có tên `checkout :: events`, thay vì mở rộng quyền truy cập ra toàn bộ `checkout`.

### 3.3. Phát event từ nghiệp vụ của module nguồn

File `checkout/CheckoutService.java` (ví dụ tối giản):

~~~java
package com.example.shop.checkout;

import com.example.shop.checkout.events.OrderSubmitted;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
public class CheckoutService {

    private final ApplicationEventPublisher events;

    public CheckoutService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public void submit(UUID orderId, List<OrderSubmitted.Line> lines) {
        // Ứng dụng thực: xác nhận và lưu đơn hàng trong transaction.
        var payload = new OrderSubmitted(orderId, lines, Instant.now());
        events.publishEvent(payload);
    }
}
~~~

Đây là ví dụ minh họa cách xây dựng và phát payload; phần lưu đơn hàng đã được lược bỏ. Trong dự án thực cần repository, quy tắc nghiệp vụ, transaction manager và cách xử lý lỗi đúng với môi trường chạy. Không nên cho code bên ngoài module `checkout` tự tạo `OrderSubmitted` để giả vờ đơn hàng đã được gửi: module sở hữu nghiệp vụ cần quyết định **khi nào sự thật đó được công bố**.

### 3.4. Module nhận chỉ phụ thuộc vào event API

File `inventory/StockReservationListener.java`:

~~~java
package com.example.shop.inventory;

import com.example.shop.checkout.events.OrderSubmitted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class StockReservationListener {

    @ApplicationModuleListener
    void reserve(OrderSubmitted event) {
        for (OrderSubmitted.Line line : event.lines()) {
            // Ứng dụng thực: gọi logic/repository nội bộ của inventory.
            System.out.printf("Reserve %s x %d%n",
                    line.sku(), line.quantity());
        }
    }
}
~~~

`@ApplicationModuleListener` trong Spring Modulith cung cấp semantics của transactional event listener với xử lý bất đồng bộ. Listener này nên cập nhật dữ liệu do `inventory` quản lý, không mượn repository của `checkout`. Lúc này module `inventory` có **phụ thuộc kiểu Java có chủ đích** đến API sự kiện của `checkout`, nhưng không phụ thuộc vào chi tiết persistence hay service nội bộ.

File `inventory/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "checkout :: events"
)
package com.example.shop.inventory;
~~~

Ràng buộc trên cho phép `inventory` phụ thuộc vào named interface `events` của `checkout`. Nếu `inventory` import `checkout.internal.OrderRepository`, bước kiểm chứng kiến trúc phải phát hiện vi phạm. Khi dự án khai báo tên module tùy biến, cần dùng tên module thực tế trong `allowedDependencies`.

## 4. Phân biệt boundary được kiểm tra tĩnh và hợp đồng runtime

**Boundary tĩnh** kiểm tra module nào import module nào và kiểu được import có thuộc API công khai không. **Hành vi runtime** kiểm tra lời gọi nghiệp vụ có phát đúng payload hay không và consumer có xử lý đúng hay không. Cả hai đều cần được kiểm thử.

| Câu hỏi | Cơ chế phù hợp | Điều cơ chế đó chưa chứng minh |
| --- | --- | --- |
| `inventory` có dùng lớp nội bộ `checkout` không? | `ApplicationModules.of(...).verify()` | Event có được phát trong một use case cụ thể không. |
| `checkout.submit(...)` có phát đúng `OrderSubmitted` không? | `@ApplicationModuleTest` và `PublishedEvents` | Listener `inventory` xử lý và commit thành công không. |
| Payload có bất biến và hợp lệ không? | Unit test trực tiếp record/validation | Dependency graph của toàn ứng dụng hợp lệ không. |
| Listener có cập nhật tồn kho sau commit không? | Integration test với transaction/database; có thể dùng `Scenario` | Hợp đồng sẽ tương thích với consumer ngoài JVM sau khi đổi phiên bản không. |
| Payload có serialize/deserialize được không? | Test serializer cùng cấu hình thực tế | Giao sự kiện được bảo đảm chính xác một lần không. |

Ngay cả khi không có một lời gọi service trực tiếp, `inventory` vẫn phụ thuộc vào class `OrderSubmitted` khi nó khai báo tham số listener. Đó là **phụ thuộc tại thời điểm biên dịch**. Mục đích không phải xóa bỏ mọi phụ thuộc, mà là **giới hạn chúng vào hợp đồng công khai đã được kiểm chứng**.

### 4.1. Kiểm chứng kiến trúc với ApplicationModules

Ví dụ test đặt ở package `com.example.shop`:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTests {

    @Test
    void respectsPublishedEventApi() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đây là một quality gate quan trọng cho học phần `SPRING_MODULITH_VERIFICATION_TESTING`: nếu lập trình viên đổi listener thành phụ thuộc vào `checkout.internal.OrderEntity`, test kiến trúc cần thất bại theo quy tắc API module. Tuy nhiên, `verify()` **không đánh giá trực tiếp tính tối thiểu, bảo mật hoặc ý nghĩa nghiệp vụ của mọi field payload**; các tiêu chí này phải được xem xét bằng thiết kế và test chuyên biệt.

### 4.2. Kiểm thử event được công bố bằng @ApplicationModuleTest

Đặt test trong package `com.example.shop.checkout` để Spring Modulith xác định module mục tiêu theo vị trí test:

~~~java
package com.example.shop.checkout;

import com.example.shop.checkout.events.OrderSubmitted;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class CheckoutEventTests {

    @Autowired
    CheckoutService checkout;

    @Test
    void publishesPublicPayload(PublishedEvents events) {
        UUID id = UUID.randomUUID();
        var lines = List.of(new OrderSubmitted.Line("SKU-42", 2));

        checkout.submit(id, lines);

        assertThat(events.ofType(OrderSubmitted.class)
                .matching(OrderSubmitted::orderId, id))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.lines()).containsExactlyElementsOf(lines);
                    assertThat(event.occurredAt()).isNotNull();
                });
    }
}
~~~

Test minh họa kiểm tra **loại event** và **dữ liệu trong payload**, thay vì chỉ kiểm tra rằng phương thức `submit` không ném exception. Để chạy trong dự án thật, cần chuẩn bị cấu hình Spring Boot/Modulith, transaction manager và fixture dữ liệu phù hợp với triển khai của use case.

Các test liên quan đến mutation cũng hữu ích:

~~~java
@Test
void eventCopiesLineList() {
    var original = new java.util.ArrayList<>(
            java.util.List.of(new OrderSubmitted.Line("SKU-42", 2)));
    var event = new OrderSubmitted(
            java.util.UUID.randomUUID(), original, java.time.Instant.now());

    original.clear();

    assertThat(event.lines()).hasSize(1);
    assertThatThrownBy(() -> event.lines().clear())
            .isInstanceOf(UnsupportedOperationException.class);
}
~~~

Đây là một **đoạn test độc lập**: đặt trong test class có các import JUnit/AssertJ thích hợp (gồm `assertThatThrownBy`). Nó kiểm tra việc snapshot danh sách không bị tác động sau khi tạo event; không thay thế test tích hợp.

### 4.3. Kiểm thử listener và database

Giả sử `submit` lưu thay đổi đơn hàng rồi phát event trong transaction:

1. Test module nguồn xác nhận `OrderSubmitted` được công bố với `orderId` và `lines` đúng.
2. Integration test kiểm tra transaction **commit thật**; nếu transaction bị rollback, listener `AFTER_COMMIT` mặc định không chạy.
3. Test module nhận/integration xác nhận dữ liệu tồn kho thay đổi đúng theo payload, với thời gian chờ phù hợp nếu xử lý bất đồng bộ.
4. Test tình huống event có thể được xử lý lại để bảo đảm cập nhật tồn kho **idempotent** khi hệ thống có cơ chế retry hoặc phát trùng.

Phân biệt `@EventListener` mặc định xử lý đồng bộ theo luồng phát với `@TransactionalEventListener` mặc định chờ `AFTER_COMMIT`; `@ApplicationModuleListener` của Spring Modulith cũng có hành vi xử lý theo transaction và bất đồng bộ. Nếu test tự mở transaction nhưng luôn rollback ở cuối, việc kỳ vọng listener sau commit cập nhật database là không phù hợp. Có thể dùng hỗ trợ kiểm thử `Scenario` của Spring Modulith hoặc chờ theo điều kiện nghiệp vụ; tránh `Thread.sleep` cố định.

Khi dùng **Event Publication Registry**, có thể bổ sung test về bản ghi công bố và trạng thái hoàn tất đối với listener có hỗ trợ. Cơ chế registry giúp theo dõi và hỗ trợ xử lý lại event tùy cấu hình lưu trữ; **không tự biến toàn bộ luồng thành xử lý đúng một lần (exactly once)**. Consumer vẫn cần xử lý idempotency theo yêu cầu nghiệp vụ.

## 5. Một số vi phạm boundary điển hình

### 5.1. Đưa entity JPA vào payload

~~~java
// Sai: event khiến module nhận biết implementation của checkout.
public record OrderSubmitted(OrderEntity entity) {}
~~~

Hệ quả: phụ thuộc vào persistence model; có thể lộ quan hệ JPA chưa load, lazy proxy hoặc trạng thái entity đã thay đổi. Nếu cần các dòng hàng, hãy chuyển chúng thành `OrderSubmitted.Line` trước khi phát.

### 5.2. Dùng collection mutable

~~~java
// Rủi ro: List có thể bị sửa ở nơi khác sau khi công bố.
public record OrderSubmitted(List<Line> lines) {}
~~~

Record chỉ cố định tham chiếu `lines`, không làm danh sách bất biến. Sao chép có kiểm soát bằng `List.copyOf`; nếu các phần tử mutable, cần chuyển chúng thành value object bất biến.

### 5.3. Event chứa quá nhiều dữ liệu

~~~java
// Không nên công bố những dữ liệu inventory không cần:
public record OrderSubmitted(
        UUID orderId,
        String customerPasswordHash,
        String internalFraudScore,
        List<OrderEntity> entities
) {}
~~~

Payload càng rộng thì diện lộ dữ liệu và chi phí thay đổi hợp đồng càng lớn. Dữ liệu nhạy cảm, nội bộ hoặc có vòng đời riêng nên được loại khỏi event nếu không thiết yếu cho consumer.

### 5.4. Truyền ID rồi truy cập repository nội bộ

~~~java
// Sai ý tưởng: listener thuộc inventory phụ thuộc kho dữ liệu riêng của checkout.
class StockReservationListener {
    // CheckoutOrderRepository là kiểu nội bộ của module checkout.
    CheckoutOrderRepository repository;
}
~~~

Đưa ID vào payload không tự bảo đảm boundary đúng. Consumer cần dữ kiện ổn định ngay tại thời điểm phát thì nên cân nhắc snapshot; nếu phải truy vấn trạng thái mới nhất, hãy sử dụng API truy vấn được công bố và xem xét ảnh hưởng tới coupling.

### 5.5. Hiểu nhầm event với command

`OrderSubmitted` mô tả một sự thật. `ReserveStockNow` thường là yêu cầu thực hiện thao tác. Một event nghiệp vụ nên độc lập với chuyện có bao nhiêu consumer và chúng sẽ làm gì. Nếu cần một lệnh có phản hồi tức thời hoặc bảo đảm tính nhất quán chặt, cần đánh giá liệu một lời gọi API nghiệp vụ có phù hợp hơn event bất đồng bộ hay không.

## 6. Hợp đồng payload theo thời gian: phiên bản và tính tương thích

Payload là API, nên việc sửa nó có thể ảnh hưởng tất cả module đang compile hoặc đang đọc sự kiện được lưu lại. Ví dụ đổi:

~~~java
public record OrderSubmitted(UUID orderId, Instant occurredAt) {}
~~~

thành:

~~~java
public record OrderSubmitted(
        UUID orderId,
        Instant occurredAt,
        String salesChannel
) {}
~~~

Việc thêm field vào Java record sẽ thay đổi canonical constructor; các caller dùng `new OrderSubmitted(id, at)` có thể không còn compile nếu không được cung cấp constructor tương thích. Với event đã được persist hoặc chuyển ra message broker, thay đổi còn có thể tác động đến serialization/deserialization và schema của consumer ở phiên bản khác.

Để quản lý thay đổi hợp đồng:

1. Xác định các consumer và field chúng thật sự đọc trước khi sửa event type.
2. Xem xét constructor tương thích khi chỉ thay đổi API Java và việc đó hợp lệ với nghiệp vụ.
3. Với thay đổi ngữ nghĩa lớn, cân nhắc một event mới như `OrderSubmittedV2` và kế hoạch chuyển đổi consumer.
4. Khi lưu hoặc gửi event ngoài tiến trình, kiểm thử round-trip với đúng serializer, cấu hình type mapping và phiên bản schema thực tế.
5. Bổ sung trường `eventId` hoặc `schemaVersion` **khi có nhu cầu rõ ràng**, thay vì coi Spring Modulith mặc định sinh và quản lý các field đó cho mọi POJO event.

### Event nội bộ và integration event khác nhau thế nào?

Một `ApplicationEvent` trong Spring context có thể chuyển đối tượng Java tới listener cùng JVM mà không cần định dạng JSON. Khi đưa payload vào registry, broker, file lưu hoặc API bên ngoài, ràng buộc serialization, versioning và khả năng đọc lại event trở nên quan trọng hơn.

Boundary kiến trúc giữa module và ranh giới tiến trình là hai vấn đề khác nhau:

| Cấp độ | Điều cần kiểm tra |
| --- | --- |
| **Giữa các module trong một ứng dụng** | Event type được công bố đúng named interface; module nhận không import implementation nội bộ. |
| **Qua transaction/database** | Thời điểm commit, khả năng rollback, snapshot dữ liệu, retry và idempotency. |
| **Ra broker/hệ thống ngoài** | Định dạng tuần tự hóa, schema tương thích, định danh sự kiện, chính sách bảo mật và consumer độc lập phiên bản. |

Đừng giả định rằng vì Spring phân phối POJO nội bộ thành công thì payload tự động thích hợp để gửi qua Kafka, RabbitMQ hoặc để lưu lâu dài. Việc externalize event là một quyết định và cấu hình riêng.

## 7. Đưa kiểm chứng payload và boundary vào CI

Một quality gate phù hợp cho học phần verification/testing nên chạy ít nhất những nhóm kiểm tra sau:

| Nhóm test | Khi nào thất bại? | Giá trị bảo vệ |
| --- | --- | --- |
| **Architecture test**: `ApplicationModules.verify()` | Module nhận import kiểu `internal`, tạo phụ thuộc vòng hoặc vi phạm `allowedDependencies`. | Ngăn xói mòn ranh giới module. |
| **Event publication test**: `@ApplicationModuleTest` + `PublishedEvents` | Use case không phát sự kiện, phát sai loại hoặc payload sai. | Giữ ổn định hợp đồng nghiệp vụ tại nguồn. |
| **Payload unit test** | Collection bị sửa ngoài ý muốn, dữ liệu không hợp lệ lọt vào event. | Giữ bất biến và tính hợp lệ cơ bản. |
| **Transaction/database integration test** | Listener không chạy sau commit, dữ liệu được cập nhật sai hoặc thiếu idempotency. | Phát hiện lỗi phối hợp giữa module và cơ sở dữ liệu. |
| **Serialization/compatibility test** (nếu có) | Event lưu/gửi không đọc được bởi phiên bản serializer/consumer dự kiến. | Giảm hồi quy khi nâng cấp hợp đồng. |

Tích hợp các test vào tác vụ kiểm thử chuẩn trên CI và cấu hình job thất bại khi test thất bại. Ví dụ, dự án dùng Gradle thường chạy `./gradlew test`, còn dự án Maven có thể chạy `./mvnw test` nếu dùng Maven Wrapper. Đây là gợi ý quality gate, không giả định dự án nào cũng có cùng công cụ hoặc cùng cách cấu hình.

Lưu ý: **Không có một lời gọi `verify()` nào đủ để đánh giá cả tính đúng đắn nghiệp vụ, bảo mật payload, transaction và tính tương thích phiên bản**. Cần kết hợp phân tích ranh giới tĩnh với test hành vi và integration test đúng bối cảnh.

## 8. Bài tập tình huống

Ứng dụng có ba module: `sales`, `shipment` và `analytics`. Một lập trình viên tạo event:

~~~java
// com.example.shop.sales.events.OrderPaid
public record OrderPaid(
        SalesOrderEntity order,
        List<PaymentEntity> payments
) {}
~~~

`shipment` chỉ cần `orderId` và địa chỉ vận chuyển đã xác nhận; `analytics` chỉ cần giá trị đơn hàng, đơn vị tiền tệ và thời điểm thanh toán.

**Câu hỏi:**

1. Vì sao payload trên là lựa chọn không tốt cho boundary?
2. Nên công bố những trường nào?
3. Chỉ dùng `ApplicationModules.verify()` đã đủ xác nhận `shipment` xử lý đúng chưa?
4. Nếu consumer chạy sau commit và có retry, cần thêm yêu cầu nào?

**Gợi ý đáp án:**

1. `SalesOrderEntity` và `PaymentEntity` là kiểu persistence nội bộ; consumer bị buộc hiểu mô hình lưu trữ và có nguy cơ đọc trạng thái mutable/lazy.
2. Có thể dùng event bất biến chứa `orderId`, snapshot địa chỉ cần thiết, `totalAmount`, `currency`, `paidAt`. Xem xét mức độ nhạy cảm của địa chỉ; nếu hai consumer có yêu cầu truy cập rất khác nhau, cân nhắc phân tách hợp đồng hoặc chỉ công bố thông tin mỗi consumer thực sự cần.
3. Không. `verify()` kiểm tra quan hệ phụ thuộc; cần test phát event và integration test quan sát kết quả ở `shipment`.
4. Nên có cơ chế nhận diện sự kiện và xử lý lặp an toàn (idempotency), test sau commit, đồng thời kiểm chứng dữ liệu không bị cập nhật nhiều lần bởi cùng một sự kiện.

## 9. Checklist thiết kế và kiểm thử

- [ ] Event mô tả một sự thật nghiệp vụ đã xảy ra, tên và thời điểm có nghĩa rõ ràng.
- [ ] Payload chỉ chứa các field cần công bố; loại bỏ entity, repository, service và dữ liệu nhạy cảm không cần thiết.
- [ ] Nested type thuộc API công khai; các collection được sao chép, phần tử có thiết kế bất biến.
- [ ] Package của event được công bố qua base package API hoặc `@NamedInterface` khi cần.
- [ ] Module nhận chỉ phụ thuộc vào API được phép và `allowedDependencies` được khai báo đúng.
- [ ] `ApplicationModules.verify()` chạy trong test/CI để phát hiện phụ thuộc sai.
- [ ] `@ApplicationModuleTest` hoặc test phù hợp xác nhận loại event, payload và ngữ cảnh phát.
- [ ] Nếu event có liên quan transaction, database, registry hoặc async listener, đã kiểm thử commit và idempotency.
- [ ] Nếu event cần lưu hay gửi ra ngoài tiến trình, đã kiểm tra serialization và tương thích phiên bản.

**Kết luận:** Một event giúp các module phối hợp lành mạnh khi payload đại diện cho **hợp đồng nghiệp vụ được công bố có chủ đích**. Thiết kế record/value object phù hợp, giới hạn phụ thuộc bằng named interface và quy tắc module, rồi kết hợp test kiến trúc với test hành vi để boundary được bảo vệ qua mỗi lần thay đổi code.
