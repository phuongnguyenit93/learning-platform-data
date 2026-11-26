# Event trong cùng module của Spring Modulith

## 1. Event trong cùng module là gì?

**Event trong cùng module** là thông điệp mô tả một việc đã xảy ra trong phạm vi trách nhiệm của **một application module**, được phát để các thành phần khác **cùng module đó** phản ứng. Ví dụ, module `orders` xác nhận đơn hàng rồi thông báo `OrderConfirmed` cho một thành phần cập nhật lịch sử trạng thái hoặc số liệu nội bộ của chính `orders`.

Đặc điểm nổi bật của loại event này:

- **Phạm vi nghiệp vụ:** sự kiện và các listener thuộc cùng một module, chia sẻ hiểu biết về quy tắc module sở hữu.
- **Phạm vi thực thi thông thường:** dùng Spring `ApplicationEventPublisher` và event multicaster trong cùng một `ApplicationContext`, không tự đi qua broker hoặc mạng.
- **Contract:** có thể là chi tiết triển khai **nội bộ**, không bắt buộc phải trở thành API công khai cho module khác.
- **Thời điểm xử lý:** phụ thuộc vào loại listener; có thể đồng bộ ngay khi phát hoặc chờ transaction hoàn tất.
- **Độ tin cậy:** chỉ phát một object không có nghĩa listener đã hoàn tất hoặc event được lưu bền; cần xác định transaction, retry và cơ chế lưu publication theo yêu cầu.

Bài học thuộc chương **Event nội bộ và tích hợp** trong dịch vụ `SPRING_MODULITH_APPLICATION_EVENTS`. Mục tiêu chung là tổ chức giao tiếp bằng application events để giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ, từ publisher, listener đến hậu commit, event publication registry, retry, kiểm thử và quan sát. Trước khi chọn cách trao đổi **giữa các module** hoặc ra hệ thống ngoài, cần hiểu kỹ việc sử dụng event **ngay trong một module**.

### 1.1. Ví dụ ngắn

Giả sử `orders` chịu trách nhiệm:

1. Kiểm tra điều kiện xác nhận đơn hàng.
2. Chuyển trạng thái đơn sang `CONFIRMED`.
3. Ghi lại lịch sử chuyển trạng thái để kiểm toán.
4. Cập nhật read model tóm tắt phục vụ màn hình quản trị đơn.

Hai việc đầu thuộc **luồng quyết định nghiệp vụ cốt lõi**. Hai việc sau có thể được thiết kế theo event trong cùng module **nếu** tính nhất quán của nghiệp vụ cho phép xử lý ở thời điểm lựa chọn.

~~~mermaid
flowchart LR
    API[Order API] --> Service[orders: OrderService]
    Service --> Aggregate[Order aggregate]
    Service --> Publisher[ApplicationEventPublisher]
    Publisher --> Event[OrderConfirmed]
    Event --> Audit[orders: history listener]
    Event --> View[orders: projection listener]
~~~

Tất cả thành phần phía sau `orders:` trong sơ đồ đều có thể sống trong **một application module**. Đường mũi tên event diễn tả **thông báo tới listener**, không ngụ ý message broker hoặc một tiến trình riêng.

## 2. Phân biệt event cùng module, event liên module và integration event

Không phân loại event chỉ bằng tên lớp hoặc việc nó có annotation nào. Câu hỏi quyết định là **ai sở hữu sự thật nghiệp vụ, ai tiêu thụ và thông điệp đi qua ranh giới nào**.

| Tiêu chí | Event trong cùng module | Event giữa các module | Integration event |
| --- | --- | --- | --- |
| Producer và consumer | Thuộc cùng module | Thuộc những application module khác nhau | Consumer ở ngoài ứng dụng/tiến trình nguồn |
| Ví dụ | `orders` phát để `orders.internal.history` xử lý | `orders` phát cho `notifications` nghe | `orders` externalize qua Kafka cho shipping service |
| Phạm vi contract | Có thể hoàn toàn nội bộ | Phải công bố contract hợp lệ cho module khác | Contract bên ngoài, cần schema và version rõ ràng |
| Cơ chế truyền thường dùng | `ApplicationEventPublisher` trong Spring | Cùng publisher, listener trong ứng dụng Spring Modulith | Event externalization, adapter và transport |
| Broker bắt buộc? | Không | Không | Chỉ khi giải pháp tích hợp lựa chọn broker; có thể dùng kênh khác |
| Vấn đề chính | Transaction, thứ tự, lỗi, tránh phức tạp hóa logic | Bảo vệ module boundary và quyền sở hữu | Serialization, versioning, định tuyến, giao lại và vận hành phân tán |

**Cùng đối tượng event có thể có nhiều người nghe ở những phạm vi khác nhau.** Chẳng hạn `OrderConfirmed` ban đầu chỉ được một listener nội bộ dùng; sau này `notifications` muốn nghe nó. Khi ấy cần quyết định **có công bố event contract** hay giữ event nội bộ và phát thêm contract công khai phù hợp.

Spring Modulith không buộc mọi event phải đi qua nhiều module. Trong nhiều trường hợp, Spring Framework events bình thường đã đáp ứng việc phát và nghe **bên trong cùng module**; Spring Modulith giúp kiểm soát cấu trúc module và cung cấp những khả năng bổ sung khi chọn transactional listeners.

## 3. Đầu tiên phải quyết định: dùng event hay gọi method trực tiếp?

Không phải mọi hành vi nội bộ đều nên tách thành event. Event phù hợp khi **một việc đã hoàn thành**, và có những tác vụ khác muốn phản ứng mà người phát không cần phối hợp chi tiết cách xử lý.

### 3.1. Khi nên gọi method trực tiếp

Ưu tiên lời gọi trực tiếp khi:

- Kết quả của bước tiếp theo là **điều kiện bắt buộc** để hoàn thành hành vi hiện tại.
- Cần exception/result rõ ràng để quyết định commit hoặc rollback.
- Thứ tự của các thao tác là một phần quan trọng của quy tắc nghiệp vụ.
- Luồng xử lý ngắn và sự tách biệt bằng event không đem lại lợi ích đáng kể.
- Có thể thể hiện logic trong aggregate hoặc domain service mà không tạo phụ thuộc chéo bất hợp lý.

Ví dụ, muốn xác nhận đơn thì phải kiểm tra trạng thái và điều kiện thanh toán. Đừng biến kiểm tra này thành một listener hậu commit rồi trả lời khách hàng “đã xác nhận” trước khi biết nó có hợp lệ không.

~~~java
@Transactional
public void confirm(UUID orderId) {
    Order order = orders.findById(orderId).orElseThrow();

    order.requireCanConfirm(); // Bất biến bắt buộc.
    order.confirm();           // Quyết định trạng thái.
}
~~~

Trong ví dụ, `OrderRepository`, `Order` và method `requireCanConfirm()` là thành phần giả định của ứng dụng. Logic cốt lõi được gọi tường minh trong cùng transaction để người đọc nhìn thấy điều kiện thành công.

### 3.2. Khi event là lựa chọn tốt

Cân nhắc event nội bộ khi:

- Một mốc nghiệp vụ đã xảy ra có **nhiều phản ứng độc lập**.
- Những tác vụ như ghi lịch sử, projection hoặc quan sát có thể phát triển riêng.
- Publisher không cần biết implementation của từng listener.
- Hệ thống có thể chấp nhận **eventual consistency** cho một số tác vụ hậu quả.
- Cần thêm hoặc bỏ một phản ứng mà không sửa luồng xác nhận nghiệp vụ cốt lõi.

Ví dụ:

~~~text
OrderService.confirm(orderId)
  -> order.requireCanConfirm()
  -> order.confirm()
  -> publish OrderConfirmed
       -> OrderHistoryListener
       -> OrderSummaryProjectionListener
~~~

Nếu ghi lịch sử là **nghĩa vụ bắt buộc phải commit nguyên tử** với việc xác nhận đơn, hãy giữ nó trong cùng transaction bằng thiết kế trực tiếp phù hợp, hoặc dùng một listener đồng bộ/`BEFORE_COMMIT` có kiểm soát và bảo đảm rollback đúng; không mặc nhiên chuyển sang `AFTER_COMMIT` bất đồng bộ.

### 3.3. Bảng quyết định nhanh

| Yêu cầu | Cách triển khai nên cân nhắc | Lý do |
| --- | --- | --- |
| Kiểm tra đơn có hợp lệ trước khi xác nhận | Gọi method trực tiếp | Quy tắc phải quyết định kết quả nghiệp vụ |
| Cập nhật các trường của cùng aggregate | Method của aggregate | Giữ bất biến và state trong một nơi |
| Ghi audit phải nằm trong cùng transaction | Thao tác đồng bộ được bao trong transaction | Tránh thiếu audit khi xác nhận đã thành công |
| Cập nhật read model có thể chậm một chút | Event + listener hậu commit | Có thể tách tác vụ hậu quả |
| Thêm metric về đơn đã xác nhận | Event hoặc instrumentation | Tách quan sát khỏi logic, nhưng tránh đếm sai khi rollback |
| Gửi email cho khách hàng | Event hậu commit, thường ở module thông báo riêng | Hành động ngoài DB không thể rollback cùng đơn |
| Yêu cầu một module khác trả kết quả ngay | API công khai liên module | Event hậu commit không trả kết quả tức thời |

## 4. Đặt event ở đâu trong cấu trúc module?

Trong Spring Modulith, package nghiệp vụ giúp xác định boundary. Nếu event **chỉ sử dụng bên trong `orders`**, không cần vội công bố nó dưới API gốc hoặc khai báo `@NamedInterface`.

Ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
└── orders
    ├── OrderOperations.java                   (API của module nếu cần)
    └── internal
        ├── OrderManagement.java
        ├── OrderRepository.java
        ├── domain
        │   └── Order.java
        ├── events
        │   └── OrderConfirmed.java            (contract nội bộ)
        ├── history
        │   └── OrderHistoryListener.java
        └── projection
            └── OrderSummaryListener.java
~~~

Theo cách tổ chức này:

1. `orders.internal.events.OrderConfirmed` nằm trong vùng nội bộ của module `orders`.
2. Các listener ở `orders.internal.history` và `orders.internal.projection` có thể import sự kiện vì **chúng thuộc cùng module**.
3. Module `notifications` hoặc `reporting` bên ngoài `orders` **không nên import** `orders.internal.events.OrderConfirmed`.
4. Nếu về sau cần công bố sự kiện xuyên module, module `orders` có thể xuất một loại contract trong package gốc hoặc một named interface đã được công bố, đồng thời bảo toàn ý nghĩa nghiệp vụ.

**Lưu ý về Java visibility:** một lớp `public` nằm trong package `internal` vẫn có thể được Java import từ module khác ở thời điểm compile. Kiểm tra boundary của Spring Modulith nhằm phát hiện kiểu phụ thuộc không hợp lệ đó; `public` theo ngôn ngữ Java không đồng nghĩa với API được phép sử dụng xuyên module.

### 4.1. Có nhất thiết tách package `events`?

Không. Với một module nhỏ, đặt một record event trong package của feature liên quan có thể dễ hiểu hơn. Package `events` chỉ hữu ích khi giúp định vị contract rõ ràng; đừng tạo một “event layer” chứa tất cả nghiệp vụ tách rời module sở hữu. Sự kiện nên được đặt gần nơi xác định **sự thật nghiệp vụ** của nó.

## 5. Phát event từ application service

Hạ tầng chuẩn của Spring Framework gồm:

- `ApplicationEventPublisher` để phát event.
- `@EventListener` để xử lý event thông thường.
- `@TransactionalEventListener` để xử lý event theo pha transaction.

Spring Modulith được xây dựng trên hạ tầng này; `@ApplicationModuleListener` là một lựa chọn tiện dụng bổ sung cho listener hậu commit có giao dịch xử lý riêng.

### 5.1. Định nghĩa event bất biến

Một kiểu event đơn giản có thể dùng Java record:

~~~java
package com.example.shop.orders.internal.events;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Trong event này:

- `eventId` phân biệt **một lần phát event**; hữu ích khi listener có retry.
- `orderId` xác định aggregate nguồn.
- `occurredAt` biểu thị thời điểm sự thật nghiệp vụ được ghi nhận.

Chọn đúng các trường cần thiết cho tác vụ nội bộ. `eventId` không bắt buộc với mọi event đơn giản; chỉ nên tạo dữ liệu này khi phục vụ kiểm tra, tương quan, xử lý lặp hoặc những nhu cầu thực tế khác.

### 5.2. Publisher trong transaction nghiệp vụ

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.internal.events.OrderConfirmed;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderManagement {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    OrderManagement(OrderRepository orders,
                    ApplicationEventPublisher publisher,
                    Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findById(orderId).orElseThrow();

        order.requireCanConfirm();
        order.confirm();

        publisher.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, clock.instant()
        ));
    }
}
~~~

Ví dụ giả định có repository, aggregate và bean `Clock` thích hợp. Với JPA, thay đổi trên entity đang được quản lý thường được flush trong quá trình commit; nếu dùng cơ chế lưu trữ khác, cần ghi lưu theo API của repository trước khi kết thúc transaction.

Điểm cần phân biệt: **`publishEvent()` được gọi trong transaction, nhưng listener không nhất thiết xử lý sau commit.** Với `@EventListener` mặc định, listener thường chạy đồng bộ **ngay tại lời gọi này**. Với `@TransactionalEventListener(AFTER_COMMIT)`, Spring đăng ký listener cho thời điểm transaction commit thành công.

### 5.3. Không dùng event để che luồng quyết định

Ví dụ có vấn đề:

~~~java
@Transactional
public void confirm(UUID orderId) {
    publisher.publishEvent(new ConfirmOrderRequested(orderId));
    // Không biết listener đã xác nhận hợp lệ hay chưa.
}
~~~

Nếu việc xác nhận là nghĩa vụ của `orders` và API phải trả kết quả ngay, cách này làm logic bị che sau listener; nếu listener chạy hậu commit hoặc bất đồng bộ thì người gọi có thể nhận phản hồi trước khi quyết định hoàn tất.

Event có tên `ConfirmOrderRequested` còn giống **command** hơn sự kiện đã xảy ra. Không có gì cấm thiết kế command/message trong một quy trình có state machine, nhưng phải đặt đúng ngữ nghĩa và contract kết quả; không nên tự chuyển một phương thức nghiệp vụ đồng bộ sang event chỉ để giảm số dòng mã.

## 6. Ba cơ chế listener và tác động tới transaction

| Annotation | Thời điểm mặc định | Transaction và lỗi | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `@EventListener` | Thực thi khi multicaster dispatch event; mặc định thường đồng bộ | Có thể đang chạy trong transaction nguồn; lỗi có thể truyền về publisher | Tác vụ nội bộ nhanh, cần kết quả trực tiếp hoặc thích hợp với transaction hiện tại |
| `@TransactionalEventListener` | Pha mặc định `AFTER_COMMIT` của transaction liên quan | Nếu không có transaction, mặc định không gọi; hậu commit là sau khi transaction nguồn kết thúc | Tác vụ chỉ nên thực hiện khi dữ liệu nguồn commit |
| `@ApplicationModuleListener` | Meta-annotation của Spring Modulith cho listener bất đồng bộ hậu commit, có transaction riêng | Không nằm trong đường xử lý trực tiếp của request nguồn; phải quản lý lỗi/retry | Tác vụ hậu quả của module, xử lý độc lập với transaction nguồn |

Spring Framework có thể cấu hình event multicaster chạy bất đồng bộ, và `@Async` cũng thay đổi cách listener thực thi. Vì thế bảng mô tả **cấu hình thông thường**; không nên giả định mọi event listener luôn chạy trên cùng thread hoặc luôn theo một thứ tự cố định.

### 6.1. Listener đồng bộ với `@EventListener`

~~~java
package com.example.shop.orders.internal.history;

import com.example.shop.orders.internal.events.OrderConfirmed;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class InTransactionHistoryListener {

    private final OrderHistoryWriter history;

    InTransactionHistoryListener(OrderHistoryWriter history) {
        this.history = history;
    }

    @EventListener
    void on(OrderConfirmed event) {
        history.append(event.orderId(), event.occurredAt());
    }
}
~~~

Ở ví dụ này, `OrderHistoryWriter` là thành phần do module tự định nghĩa. Nếu dùng default multicaster đồng bộ và method phát event đang trong transaction database, lời gọi ghi lịch sử có thể cùng tham gia transaction nguồn. Lỗi runtime không được xử lý ở listener thường **lan trở lại publisher**, và transaction có thể rollback theo quy tắc transaction đã cấu hình.

Điều này có thể **phù hợp** khi lịch sử bắt buộc phải được ghi cùng đơn hàng. Tuy nhiên, nếu ghi lịch sử là điều kiện cốt lõi của nghiệp vụ, method/service trực tiếp thường rõ ràng và dễ kiểm soát thứ tự hơn. Đừng coi `@EventListener` là một cơ chế bảo đảm atomicity độc lập: nó phụ thuộc multicaster, transaction manager và việc listener thực thi đồng bộ.

### 6.2. Listener hậu commit bằng `@TransactionalEventListener`

~~~java
package com.example.shop.orders.internal.projection;

import com.example.shop.orders.internal.events.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderSummaryListener {

    private final OrderSummaryUpdater updater;

    OrderSummaryListener(OrderSummaryUpdater updater) {
        this.updater = updater;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderConfirmed event) {
        updater.updateAfterCommit(event.orderId());
    }
}
~~~

**Điều quan trọng về ghi database sau commit:** callback `AFTER_COMMIT` có thể chạy khi tài nguyên transaction gốc vẫn còn gắn với thread. Nếu listener muốn **ghi dữ liệu mới cần commit chắc chắn**, việc chỉ gọi repository từ callback không tự tạo commit mới. Hãy gọi qua một Spring bean/service dùng `@Transactional(propagation = REQUIRES_NEW)` hoặc dùng cơ chế listener tạo transaction riêng phù hợp.

Ví dụ service riêng:

~~~java
@Service
class OrderSummaryUpdater {

    private final OrderSummaryRepository summaries;

    OrderSummaryUpdater(OrderSummaryRepository summaries) {
        this.summaries = summaries;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateAfterCommit(UUID orderId) {
        summaries.rebuildFor(orderId);
    }
}
~~~

Ví dụ trên giả định các import Spring transaction/JPA repository tương ứng. `OrderSummaryListener` gọi một **bean khác** để transaction interceptor được áp dụng; gọi một method `REQUIRES_NEW` trực tiếp bằng `this.method()` trong cùng bean có thể không đi qua Spring proxy.

**Sau commit không đồng nghĩa với bất đồng bộ.** `@TransactionalEventListener` mặc định không tự chuyển công việc sang một executor. Một listener nặng vẫn có thể kéo dài khoảng thời gian request đang kết thúc. Nếu cần tách thời gian phản hồi, xem xét cơ chế async phù hợp, sau đó chịu trách nhiệm quản lý lỗi và tính nhất quán cuối cùng.

### 6.3. `@ApplicationModuleListener` trong cùng một module

Annotation này thường được dùng để giao tiếp **giữa** các module vì làm giảm phụ thuộc thời gian, nhưng không có quy định rằng listener phải nằm trong module khác. Nó cũng có thể phù hợp cho tác vụ hậu commit nội bộ, khi module muốn một transaction xử lý riêng.

~~~java
package com.example.shop.orders.internal.projection;

import com.example.shop.orders.internal.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class AsyncOrderSummaryListener {

    private final OrderSummaryWriter writer;

    AsyncOrderSummaryListener(OrderSummaryWriter writer) {
        this.writer = writer;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        writer.rebuildFor(event.orderId());
    }
}
~~~

Khi dùng annotation này, cần có hạ tầng async/transaction phù hợp phiên bản Spring Boot/Spring Modulith. Listener có thể chạy sau khi request nguồn kết thúc. Nó **không được dùng để bảo đảm bất biến tức thời** mà API nguồn cần xác nhận trước khi trả kết quả.

### 6.4. Các pha transaction khác

`@TransactionalEventListener` hỗ trợ một số pha xử lý:

| Transaction phase | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `BEFORE_COMMIT` | Chạy trước khi commit | Lỗi có thể ảnh hưởng commit; phù hợp các tác vụ có chủ đích phải hoàn tất trước commit |
| `AFTER_COMMIT` | Chạy sau khi commit thành công | Không tự đưa dữ liệu ghi mới vào transaction đã kết thúc |
| `AFTER_ROLLBACK` | Chạy sau khi rollback | Dùng cho cleanup/quan sát thích hợp; không giả định có thể rollback tác vụ ngoài đã thực hiện |
| `AFTER_COMPLETION` | Chạy khi transaction kết thúc bất kể commit hay rollback | Cần biết kết quả nếu logic khác nhau theo outcome |

Nếu không có transaction, transactional listener theo mặc định sẽ **không được kích hoạt** (trừ khi cấu hình `fallbackExecution = true`). Bật fallback khiến listener có thể chạy ngoài ngữ nghĩa hậu commit; cần lựa chọn chủ động khi API có đường gọi không transactional.

## 7. Timeline: cùng một event, ba kết quả khác nhau

Giả sử `orders` phát `OrderConfirmed` trong method `confirm()` có `@Transactional`:

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Service as OrderManagement
    participant TX as Transaction
    participant Sync as @EventListener
    participant After as @TransactionalEventListener
    participant Async as @ApplicationModuleListener

    Client->>Service: confirm(orderId)
    Service->>TX: Begin transaction
    Service->>Service: order.confirm()
    Service->>Service: publishEvent(OrderConfirmed)
    Service->>Sync: Dispatch đồng bộ
    Sync-->>Service: Trả kết quả / exception
    Service->>TX: Commit
    alt Commit thành công
        TX-->>After: Callback AFTER_COMMIT
        TX-->>Async: Giao công việc hậu commit
        Async->>Async: Transaction xử lý riêng
    else Rollback
        Note over After,Async: Không xử lý nhánh hậu commit
    end
    Service-->>Client: Kết quả API theo contract
~~~

Sơ đồ thể hiện ý tưởng, **không khẳng định một thứ tự tuyến tính** giữa tất cả callback, executor và thời điểm response trong mọi cấu hình. Đặc biệt, `@ApplicationModuleListener` có thể thực thi sau hoặc song song khi thread xử lý request nguồn đang hoàn tất.

### 7.1. Nếu listener đồng bộ phát sinh exception

Với multicaster đồng bộ mặc định, exception không được xử lý có thể truyền qua `publishEvent()` đến service. Tùy transaction attributes, transaction có thể rollback.

Ví dụ, nếu `OrderHistoryListener` dùng chung DB transaction và throw `RuntimeException`, khả năng rollback là một phần có thể chủ động sử dụng. Nhưng nếu listener đã gọi hệ thống ngoài, rollback DB **không hoàn tác** email/HTTP request đã gửi.

### 7.2. Nếu listener hậu commit thất bại

Đơn hàng nguồn đã commit; lỗi của listener không tự khôi phục lại trạng thái cũ. Hệ thống cần quyết định:

- Tác vụ có thể bỏ qua và ghi log không?
- Cần retry hoặc resubmit publication không?
- Có cách phát hiện listener xử lý trùng không?
- Module có cần lưu trạng thái projection/lịch sử riêng để kiểm tra tiến độ không?
- Có metric/cảnh báo đủ để biết việc hậu commit đang tồn đọng không?

Không nên trả API “đã cập nhật mọi projection” nếu hợp đồng API chỉ bảo đảm “đơn hàng đã được xác nhận”.

## 8. Spring Data domain events trong aggregate

Trong một số thiết kế Domain-Driven Design, **aggregate** ghi nhận domain events khi trạng thái của nó thay đổi. Spring Data hỗ trợ `@DomainEvents` / `@AfterDomainEventPublication` và lớp tiện ích `AbstractAggregateRoot` để công bố những event đã đăng ký khi gọi một số phương thức repository thích hợp.

### 8.1. Phát event từ application service hay aggregate?

**Application service phát event:** phù hợp khi service xác định transaction/use case và tự tạo payload sau khi aggregate đã hoàn thành quy tắc.

**Aggregate đăng ký domain event:** phù hợp khi mốc phát event gắn chặt với chuyển trạng thái nội bộ, để aggregate tự nêu ra những sự thật nó đã ghi nhận.

Ví dụ minh họa dùng Spring Data:

~~~java
package com.example.shop.orders.internal.domain;

import com.example.shop.orders.internal.events.OrderConfirmed;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.AbstractAggregateRoot;

class Order extends AbstractAggregateRoot<Order> {

    private UUID id;
    private OrderStatus status;

    void confirm(Instant now) {
        requireCanConfirm();
        status = OrderStatus.CONFIRMED;
        registerEvent(new OrderConfirmed(
            UUID.randomUUID(), id, now
        ));
    }

    private void requireCanConfirm() {
        // Kiểm tra quy tắc nghiệp vụ của đơn hàng.
    }
}
~~~

Application service:

~~~java
@Transactional
public void confirm(UUID orderId) {
    var order = orders.findById(orderId).orElseThrow();
    order.confirm(clock.instant());
    orders.save(order); // Spring Data repository có thể publish domain events.
}
~~~

**Chú ý quan trọng:**

- Đoạn code `Order` là mô hình minh họa và chưa bao gồm đầy đủ mapping JPA, constructor hay trạng thái nghiệp vụ.
- Với `AbstractAggregateRoot`, sự kiện đã đăng ký được công bố qua cơ chế repository của Spring Data khi gọi các phương thức hỗ trợ; chỉ **đổi thuộc tính của entity đang managed** rồi đợi JPA flush có thể không kích hoạt cơ chế publication của repository.
- Việc repository công bố domain event **không mặc nhiên đồng nghĩa event được phát sau commit**. Listener cần chọn pha transaction phù hợp.
- Không đồng thời phát cùng một `OrderConfirmed` ở service và qua `AbstractAggregateRoot` nếu không chủ ý xử lý duplicate.
- Đừng phụ thuộc vào các phương thức delete hàng loạt/`deleteById` để phát domain event nếu aggregate không được nạp và cơ chế repository không thể thu thập event theo đường đó.

### 8.2. Khi nào không cần `@DomainEvents`?

Nếu chỉ có một event phát từ một use case đơn giản, tạo record rồi gọi `publisher.publishEvent(...)` thường rõ ràng và dễ kiểm thử. Thêm cơ chế aggregate event chỉ có ích khi giúp tổ chức domain logic hoặc tránh việc event bị phát sai thời điểm trong nhiều luồng nghiệp vụ khác nhau.

## 9. Thiết kế payload phù hợp khi tất cả vẫn ở cùng module

Event cùng module không cần thiết kế như public integration schema ngay từ đầu. Tuy nhiên, nên sử dụng **payload bất biến, có ý nghĩa** để tránh phụ thuộc vô tình và chuẩn bị cho retry.

### 9.1. Chọn ID, snapshot hay toàn bộ entity?

| Payload | Ưu điểm | Nguy cơ |
| --- | --- | --- |
| `orderId` | Gọn, ổn định, dễ ghi log | Listener có thể phải truy vấn lại dữ liệu sau khi trạng thái đã đổi |
| `orderId + occurredAt + eventId` | Hỗ trợ nhận diện, xử lý lặp và quan sát | Không phải mọi tác vụ cần đủ cả ba trường |
| Snapshot bất biến của thông tin cần thiết | Listener có dữ liệu đúng tại thời điểm phát, giảm truy vấn | Payload lớn hơn, phải kiểm soát ngữ nghĩa và dữ liệu nhạy cảm |
| Tham chiếu đến entity JPA | Viết code ngắn trong cùng transaction | Dễ lộ state mutable, lazy loading và sai nghĩa khi xử lý sau commit |

Với listener hậu commit hoặc bất đồng bộ, **không nên truyền một entity mutable rồi giả định nó vẫn còn được quản lý bởi persistence context**. Dùng định danh hoặc snapshot giá trị bất biến.

Ví dụ nếu lịch sử trạng thái phải ghi giá trị chính xác tại thời điểm chuyển trạng thái:

~~~java
public record OrderStatusChanged(
    UUID orderId,
    String fromStatus,
    String toStatus,
    Instant changedAt
) {}
~~~

Listener không cần truy vấn lại trạng thái cũ sau khi một giao dịch khác đã cập nhật đơn. Tuy nhiên, nếu snapshot chứa dữ liệu cần bảo mật, vẫn phải giới hạn nơi lưu và nơi ghi log, dù event chỉ được xử lý trong cùng tiến trình.

### 9.2. Tên event và mức chi tiết

Tên nên nói lên **sự thật**:

- `OrderConfirmed` mô tả mốc xác nhận.
- `OrderCancelled` mô tả mốc hủy.
- `OrderStatusChanged` mô tả một thay đổi trạng thái tổng quát.

Không nên lạm dụng một loại `GenericEvent(String name, Object payload)` cho mọi nghiệp vụ vì đánh mất contract kiểu tĩnh, khó khám phá dependency và khó kiểm tra dữ liệu bắt buộc. Cũng không cần sinh một event riêng cho từng phép gán field nhỏ nếu không có consumer thực sự.

### 9.3. Sự kiện nội bộ có thể trở thành API công khai sau này

Một thời điểm nào đó, module khác có thể muốn nghe `OrderConfirmed`. Trước khi cho phép import:

1. Kiểm tra ý nghĩa event có thật sự là một sự thật mà các module khác được phép biết.
2. Xác định những field cần thiết và tránh lộ entity/repository nội bộ.
3. Công bố event qua package API của module hoặc `@NamedInterface`.
4. Xác minh dependency giữa module bằng công cụ Spring Modulith.
5. Nếu chuyển ra hệ thống ngoài, bổ sung schema/version/serializer/routing và độ tin cậy phù hợp.

Việc event được phát trong cùng `ApplicationContext` **không tự cấp quyền** cho mọi module khác dùng kiểu event ấy.

## 10. Độ tin cậy khi listener cũng nằm trong cùng module

Nhiều nhóm cho rằng event cùng module chắc chắn đáng tin cậy vì mọi thứ nằm trong một tiến trình. Thực tế, tiến trình có thể dừng **sau khi transaction nguồn commit nhưng trước khi tác vụ hậu commit hoàn tất**; listener có thể gặp exception, còn công việc bên ngoài database không tự rollback.

### 10.1. Event publication registry có cần cho event nội bộ không?

Registry của Spring Modulith theo dõi **publication của transactional event listeners** khi có backend phù hợp. Trọng tâm là sự kiện cần giao cho **listener mục tiêu**; listener có thể ở module khác hoặc thuộc cùng module, tùy mô hình sử dụng.

Khi một listener nội bộ xử lý `OrderConfirmed` thất bại:

~~~text
OrderConfirmed được phát trong transaction
        |
        v
Database đơn hàng commit
        |
        v
Projection listener cần xử lý
        |
        +--> SUCCESS: publication có thể được đánh dấu hoàn tất
        |
        +--> FAILED: publication chưa hoàn tất nếu registry đã cấu hình
                   |
                   v
               recovery/resubmit theo chính sách
~~~

**Registry không tự biến mọi `@EventListener` thành một hàng đợi bền vững.** Khả năng lưu publication áp dụng theo loại listener/transaction và cấu hình persistence. Chỉ dùng `ApplicationEventPublisher` hoặc `@EventListener` không phải lời hứa rằng event có thể được phát lại sau khi process restart.

### 10.2. Một event nhiều listener sẽ có nhiều trạng thái xử lý

Giả sử `OrderConfirmed` có hai listener hậu commit:

| Publication | Kết quả | Hệ quả |
| --- | --- | --- |
| Event E → `OrderHistoryListener` | Thành công | Lịch sử đã ghi |
| Event E → `OrderSummaryListener` | Thất bại | Projection còn chờ cập nhật |

Khi registry đã cấu hình, cần xem xét publication **theo listener**, không gộp thành một cờ cho toàn bộ event. Việc listener A hoàn tất không chứng minh listener B đã xử lý.

### 10.3. Retry có thể làm một tác vụ được thực hiện hai lần

Ví dụ projection listener cập nhật bộ đếm “số đơn đã xác nhận”. Listener cộng `+1` rồi crash trước khi publication được ghi hoàn tất; khi xử lý lại, bộ đếm có thể bị cộng thêm lần nữa.

Hai cách an toàn hơn:

- **Idempotent update:** dựng lại số liệu từ dữ liệu nguồn hoặc dùng thao tác cập nhật bảo đảm không tác động lặp.
- **Deduplication:** ghi khóa `eventId` đã áp dụng với unique constraint, cùng transaction cập nhật projection khi có thể.

Pseudocode:

~~~text
on OrderConfirmed(event):
    begin transaction
        insert processed_event(event.eventId) with unique constraint
        if eventId already existed:
            skip duplicate update
        else:
            update local projection once
    commit
~~~

Việc kiểm tra tồn tại rồi cập nhật trong hai bước không có khóa/transaction có thể gây race khi chạy đồng thời. Với dịch vụ ngoài có tác dụng phụ, chẳng hạn gửi email, cần tính đến idempotency key của nhà cung cấp hoặc phương án đối soát.

### 10.4. Mức bảo đảm nào là đủ?

| Tác vụ nội bộ | Yêu cầu độ tin cậy thường gặp | Lựa chọn minh họa |
| --- | --- | --- |
| Metric chỉ để theo dõi | Có thể chấp nhận mất vài tín hiệu | Instrumentation hoặc listener nhẹ, tránh làm hỏng transaction |
| Audit bắt buộc đồng bộ cùng nghiệp vụ | Không chấp nhận thiếu audit nếu đơn đã commit | Cập nhật audit trong cùng transaction |
| Projection có thể xây lại | Chấp nhận eventual consistency | Listener hậu commit, rebuild và idempotency |
| Tính điểm thưởng có giá trị kinh tế | Không chấp nhận cộng trùng hoặc thất lạc không quan sát được | Publication bền vững, trạng thái xử lý, idempotency và đối soát |

Độ tin cậy là yêu cầu **của tác vụ**, không chỉ phụ thuộc event có ở cùng module hay không.

## 11. Những rủi ro thiết kế khi dùng quá nhiều event nội bộ

### 11.1. Luồng gọi bị ẩn sau nhiều listener

Khi code `confirm()` chỉ có một lời gọi `publishEvent()` nhưng hàng chục listener cùng module chỉnh sửa dữ liệu, người đọc rất khó biết việc xác nhận đơn thật sự thay đổi điều gì. Hãy giữ các **bất biến cốt lõi** trong service/aggregate và chỉ tách tác vụ phản ứng hợp lý.

### 11.2. Vòng lặp event vô tình

~~~text
OrderConfirmed
   -> listener cập nhật Order
   -> phát OrderConfirmed lần nữa
   -> listener lặp lại ...
~~~

Ngăn vòng lặp bằng cách xác định rõ **mốc nghiệp vụ**, phân biệt event mới với cùng sự kiện cũ, có guard kiểm tra state transition và tránh phát lại cùng event mỗi khi chỉ cập nhật projection/audit.

### 11.3. Giả định listener có thứ tự tuyệt đối

Spring có thể hỗ trợ thứ tự listener trong một số kiểu xử lý thông qua `@Order`, nhưng việc phụ thuộc vào thứ tự listener sẽ trở nên mong manh khi thêm `@Async`, listener hậu commit hoặc retry. Nếu bước B bắt buộc xảy ra sau khi bước A thành công để bảo đảm nghiệp vụ, hãy thể hiện **trực tiếp trong orchestrator/workflow** hoặc một state machine với contract rõ.

### 11.4. Phát event khi state chưa thực sự hợp lệ

Nếu code phát `OrderConfirmed` trước khi kiểm tra điều kiện xác nhận, một listener đồng bộ có thể chạy trên dữ liệu chưa hợp lệ. Với listener hậu commit, transaction rollback có thể ngăn xử lý sau commit, nhưng không thể dùng điều đó để thay thế việc xác định đúng **khi nào sự thật nghiệp vụ xảy ra**.

### 11.5. Gửi tác vụ bên ngoài từ listener đồng bộ trước commit

Email hoặc HTTP request không thể rollback cùng database. Nếu phải gửi sau khi đơn đã commit, hãy chọn transactional listener phù hợp và chuẩn bị phương án retry/khôi phục; nếu thông báo là một phần quan trọng của hệ thống, cần theo dõi trạng thái giao và chống duplicate.

### 11.6. Nhầm `@Async` với bảo đảm hậu commit

`@Async` thay đổi thread thực thi; nó **không mặc nhiên đợi transaction nguồn commit** và không truyền transaction context của thread phát event sang worker thread. Nếu một listener cần đọc dữ liệu đã commit, dùng đúng ngữ nghĩa transaction event và thiết lập transaction riêng khi cần.

## 12. Kiểm thử event trong cùng module

Với event nội bộ, nên phân biệt **publisher có phát event**, **listener xử lý đúng**, và **transaction/retry hoạt động đúng**.

### 12.1. Kiểm thử việc phát event

Trong Spring Test, có thể dùng khả năng ghi nhận application events. Ví dụ với Spring Boot test context và Spring Test `@RecordApplicationEvents`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

@SpringBootTest
@RecordApplicationEvents
class OrderEventPublishingTest {

    @Autowired OrderManagement management;
    @Autowired ApplicationEvents events;

    @Test
    void publishesOrderConfirmed() {
        UUID id = fixtureConfirmedReadyOrder();

        management.confirm(id);

        assertThat(events.stream(OrderConfirmed.class))
            .anySatisfy(event ->
                assertThat(event.orderId()).isEqualTo(id)
            );
    }

    private UUID fixtureConfirmedReadyOrder() {
        // Test fixture tạo đơn hợp lệ trong DB test.
        throw new UnsupportedOperationException("Implement fixture");
    }
}
~~~

Đây là khung minh họa; cần import `OrderConfirmed`, cấu hình database test, fixture và inject service theo visibility/package của dự án. `@RecordApplicationEvents` là chức năng của Spring Test, còn `@ApplicationModuleTest` là hỗ trợ kiểm thử phạm vi module của Spring Modulith. Không có mục tiêu khẳng định đoạn mã có thể chạy độc lập khi thiếu setup.

### 12.2. Tránh bẫy rollback của test có `@Transactional`

Nếu một test mặc định chạy trong transaction và bị rollback sau khi kết thúc, listener `AFTER_COMMIT` có thể **không được kích hoạt**. Đừng kết luận listener sai chỉ vì test `@Transactional` không quan sát được side effect hậu commit.

Cách kiểm thử phù hợp là đảm bảo transaction nguồn thực sự **commit** trong môi trường test, hoặc kiểm soát việc kết thúc transaction qua công cụ test transaction theo API tương ứng. Sau đó chờ/tìm trạng thái listener (nếu async) bằng điều kiện có timeout thay vì sleep cố định.

### 12.3. Kiểm thử listener độc lập

Đối với `OrderSummaryListener`:

1. Cung cấp một event hợp lệ.
2. Xác nhận projection chỉ cập nhật dữ liệu do module `orders` sở hữu.
3. Cung cấp cùng event hai lần.
4. Xác nhận kết quả không bị nhân đôi nếu listener cam kết idempotency.
5. Kiểm tra event thiếu dữ liệu bắt buộc hoặc aggregate không tồn tại.

Unit test listener chỉ xác minh **logic bên trong listener**; nó không xác minh transaction phase, bean registration hoặc registry hoạt động đúng. Khi cần đảm bảo sau commit/rollback, sử dụng integration test với Spring context và backend thích hợp.

### 12.4. Bảng các tình huống transaction cần có

| Trường hợp | Điều nên kiểm tra |
| --- | --- |
| `confirm()` thành công | Event đúng payload, listener hậu commit xử lý theo thiết kế |
| Quy tắc xác nhận không thỏa mãn | Không phát event biểu thị xác nhận thành công |
| Transaction nguồn rollback | Không kích hoạt tác vụ `AFTER_COMMIT` của đơn chưa commit |
| Synchronous listener throw exception | Xác định ảnh hưởng lên method nguồn/rollback theo cấu hình |
| AFTER_COMMIT listener ghi DB | Transaction ghi mới được commit rõ ràng, không dựa vào transaction nguồn đã hoàn tất |
| Async listener lỗi | Lỗi được log/theo dõi, không bị che mất; chính sách recovery đúng |
| Publication chưa hoàn tất | Có thể quan sát, phát lại hoặc xử lý theo chính sách đã cấu hình |
| Resubmit cùng event | Không nhân đôi projection hoặc tác vụ có tác dụng phụ |

### 12.5. Kiểm tra boundary trong Spring Modulith

Ngay cả với event nội bộ, vẫn nên kiểm tra rằng module khác không bắt đầu tham chiếu những lớp nội bộ của `orders`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesApplicationModuleBoundaries() {
        ApplicationModules
            .of(ShopApplication.class)
            .verify();
    }
}
~~~

Việc xác minh này nhằm phát hiện vi phạm dependency theo mô hình module. Nó **không chứng minh** một listener đã chạy sau commit, một retry thành công hoặc không có duplicate; những tính chất đó cần kiểm thử hành vi và transaction riêng.

## 13. Bài tập thực hành: tái cấu trúc event trong module orders

**Bối cảnh:** `OrderManagement.confirm()` đang thực hiện bốn việc:

~~~java
@Transactional
public void confirm(UUID orderId) {
    var order = orders.findById(orderId).orElseThrow();
    order.requireCanConfirm();
    order.confirm();
    histories.append(orderId);
    summaries.rebuildFor(orderId);
    auditMetrics.increment();
}
~~~

**Yêu cầu:** làm rõ phần nào cần chạy trong cùng transaction và phần nào có thể phản ứng bằng event nội bộ. Giả sử:

- Lịch sử trạng thái là bằng chứng bắt buộc và phải được commit cùng đơn.
- Projection là dữ liệu dẫn xuất, có thể chậm vài giây và xây lại được.
- Metric chỉ phục vụ quan sát, không được làm lỗi nghiệp vụ.
- Không được để module ngoài `orders` truy cập `OrderRepository`.

### 13.1. Một phương án thiết kế

Giữ việc xác nhận và ghi lịch sử bắt buộc trong transaction; phát `OrderConfirmed` sau khi đã xác lập trạng thái hợp lệ. `OrderSummaryListener` xử lý hậu commit với transaction riêng; metric chỉ ghi nhận kết quả thực sự đã commit, và lỗi metric không được làm mất kết quả nghiệp vụ.

~~~mermaid
flowchart TD
    Start[confirm order] --> Check[Kiểm tra quy tắc]
    Check --> Tx[Đổi trạng thái + ghi lịch sử trong transaction]
    Tx --> Publish[Phát OrderConfirmed]
    Publish --> Commit{Commit thành công?}
    Commit -->|Không| Rollback[Rollback; không có tác vụ hậu commit]
    Commit -->|Có| Projection[Projection listener có transaction riêng]
    Commit -->|Có| Metric[Metrics listener / instrumentation]
    Projection --> Result[Projection cuối cùng nhất quán]
~~~

Phương án này có thể thay đổi nếu lịch sử được lưu theo event sourcing hoặc nếu metric là telemetry không cần đồng bộ theo transaction. Điều quan trọng là **nêu rõ mức bảo đảm của từng tác vụ**.

### 13.2. Các bước thực hành

1. Xác định lớp và package mà `OrderConfirmed` sẽ nằm trong module `orders`.
2. Viết record event bất biến có `orderId`, `occurredAt` và định danh sự kiện nếu cần.
3. Cập nhật `OrderManagement.confirm()` để phát event sau khi aggregate đã xác nhận hợp lệ.
4. Chọn công việc giữ trong transaction và công việc chuyển sang `@TransactionalEventListener` hoặc `@ApplicationModuleListener`.
5. Nếu listener hậu commit ghi database, thiết kế transaction mới có commit rõ ràng.
6. Viết test cho trường hợp xác nhận thành công và rollback.
7. Khi có registry, tạo tình huống projection lỗi rồi kiểm tra trạng thái publication và cơ chế phục hồi.
8. Thử xử lý cùng event hai lần và kiểm chứng projection không bị nhân đôi.
9. Chạy kiểm tra boundary của Spring Modulith để bảo đảm không có module khác tham chiếu `orders.internal`.

### 13.3. Câu hỏi tự đánh giá

1. Vì sao `@EventListener` đồng bộ có thể chạy trước khi dữ liệu nguồn được commit?
2. Nếu một listener cùng module chỉ ghi dữ liệu sau commit, vì sao cần transaction mới cho thao tác ghi đó?
3. Khi nào `ApplicationEventPublisher` giúp cấu trúc nội bộ rõ hơn lời gọi method trực tiếp?
4. Vì sao event nội bộ không bắt buộc phải được công bố thành `@NamedInterface`?
5. Nếu listener hậu commit thất bại sau khi trạng thái đơn đã commit, nguồn có tự rollback không?
6. `@Async` có mặc định đảm bảo listener chỉ chạy sau commit không?
7. Khi chuyển từ service-published event sang `AbstractAggregateRoot`, có rủi ro phát event trùng ở đâu?
8. Tại sao một listener nhận event hai lần có thể làm bộ đếm sai, dù event chỉ đi trong cùng tiến trình?
9. Khi module khác muốn nghe event nội bộ, cần đánh giá những quyết định nào về contract và boundary?
10. Một test có `@Transactional` và rollback tự động có thể gây hiểu nhầm gì khi kiểm thử `AFTER_COMMIT`?

## 14. Checklist thiết kế event trong cùng module

- [ ] Event diễn đạt sự thật nghiệp vụ đã xảy ra, do đúng module sở hữu.
- [ ] Quy tắc cốt lõi cần kết quả ngay vẫn nằm trong luồng đồng bộ/transaction thích hợp.
- [ ] Sử dụng event khi có lợi ích thật về tách phản ứng, tránh biến mọi method thành event.
- [ ] Contract nội bộ nằm trong package thuộc module; module khác không import lớp nội bộ trái ranh giới.
- [ ] Payload đủ rõ ràng và bất biến, không phụ thuộc entity JPA mutable ngoài transaction.
- [ ] Đã chọn đúng giữa `@EventListener`, `@TransactionalEventListener` và `@ApplicationModuleListener`.
- [ ] Hiểu rõ listener nào chạy trước commit, hậu commit, đồng bộ hoặc bất đồng bộ.
- [ ] Listener hậu commit ghi database có transaction riêng phù hợp.
- [ ] Các tác vụ quan trọng có chính sách xử lý lỗi, retry và idempotency.
- [ ] Nếu dùng registry, đã cấu hình backend và kiểm tra publication chưa hoàn tất.
- [ ] Đã có test cho event phát ra, commit, rollback, duplicate và recovery khi cần.
- [ ] Quan sát được lỗi listener mà không làm lộ dữ liệu nhạy cảm.

**Nguyên tắc chính:** event trong cùng module là công cụ diễn đạt **hậu quả của một sự thật nghiệp vụ** và tách các phản ứng thích hợp ngay trong module đó. Hãy dùng nó khi giúp code rõ hơn, đồng thời giữ bất biến quan trọng trong ranh giới transaction đúng, xác định rõ thời điểm listener chạy và xây dựng khả năng khôi phục tương xứng với trách nhiệm của từng tác vụ.
