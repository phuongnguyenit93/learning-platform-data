# Lộ trình học module

## Mục tiêu và cách học

**Spring Modulith Application Events** là một phần quan trọng khi thiết kế ứng dụng Spring Boot theo kiểu *modular monolith*: các module triển khai cùng một ứng dụng nhưng tách biệt về trách nhiệm và phụ thuộc mã nguồn. Thay vì để một module gọi trực tiếp nhiều service thuộc module khác, **application event** công bố một sự thật nghiệp vụ để các module quan tâm tự phản ứng.

Lộ trình này dành cho module học **SPRING_MODULITH_APPLICATION_EVENTS**, với mục tiêu tổ chức giao tiếp giữa các module bằng application events, giảm phụ thuộc, bảo vệ ranh giới nghiệp vụ và tiến tới vận hành việc giao sự kiện đáng tin cậy. Nội dung đi từ **publisher, listener, sự kiện và ranh giới module** đến **xử lý sau commit, Event Publication Registry, retry, idempotency, kiểm thử và khả năng quan sát**.

Sau khi hoàn thành, bạn cần tự mình trả lời và chứng minh bằng code được những câu hỏi sau:

1. Vì sao một module nên phát sự kiện nghiệp vụ thay vì gọi trực tiếp mọi module liên quan?
2. Producer có trách nhiệm gì, consumer chịu trách nhiệm gì, và hợp đồng sự kiện được đặt ở đâu để không phá vỡ ranh giới module?
3. Sự khác nhau giữa publish event, xử lý đồng bộ, xử lý sau commit và xử lý bất đồng bộ là gì?
4. Nếu database đã commit nhưng listener thất bại hoặc tiến trình dừng, việc chưa hoàn tất được phát hiện và khôi phục như thế nào?
5. Làm cách nào để xử lý event bị giao lại mà không gửi email hoặc cộng điểm nhiều lần?
6. Cần những test, log, metric và thao tác vận hành nào trước khi có thể tin cậy luồng sự kiện?

**Nguyên tắc học:** mỗi chặng phải tạo một kết quả chạy được và một tình huống lỗi có thể quan sát. Đừng chỉ dừng ở việc nhớ annotation hoặc copy một ví dụ publish/listen hoạt động trong trường hợp thành công.

## 1. Bản đồ toàn bộ lộ trình

Các chặng dưới đây có thứ tự phụ thuộc: hiểu ranh giới trước khi định nghĩa event; hiểu transaction trước khi xử lý độ bền; hiểu lỗi và idempotency trước khi tin vào retry.

| Chặng | Chủ đề chính | Sản phẩm thực hành phải có | Mức độ |
| --- | --- | --- | --- |
| **0** | Nền tảng Spring Boot và modular monolith | Ứng dụng mẫu có các module nghiệp vụ phân biệt được | Cơ bản |
| **1** | Đặt tên event và bảo vệ hợp đồng giữa module | Event bất biến thuộc API công khai của module phát | Cơ bản |
| **2** | Publisher và listener | Một producer phát event, ít nhất hai consumer phản ứng độc lập | Cơ bản |
| **3** | Transaction, after commit, async | Test chứng minh listener chỉ xử lý đúng lúc và hiểu độ trễ | Trung cấp |
| **4** | Event Publication Registry | Lưu dấu publication chưa hoàn tất khi listener thất bại | Trung cấp |
| **5** | Retry, idempotency, xử lý trùng | Thử giao cùng event hai lần mà tác dụng nghiệp vụ vẫn đúng | Trung cấp |
| **6** | Kiểm thử cấu trúc, giao dịch và khôi phục | Bộ test hợp lệ cho publish, rollback, retry và module boundary | Nâng cao |
| **7** | Logging, metrics, tracing và vận hành | Tìm được consumer bị lỗi và publication tồn đọng theo eventId | Nâng cao |
| **8** | Bài thực hành tổng hợp | Luồng nghiệp vụ có event, registry, test và quan sát đầy đủ | Tổng hợp |

Có thể học nhanh các chặng 0–2 để làm quen Spring Modulith, nhưng một luồng sự kiện chỉ đạt mục tiêu **đáng tin cậy** khi kiểm chứng được các chặng 3–7. Từng chặng có **đầu vào**, **nhiệm vụ** và **điều kiện qua chặng** để tránh bỏ qua kiến thức khó nhận ra trong happy path.

~~~mermaid
flowchart TD
    A["0. Hiểu module và ranh giới"] --> B["1. Thiết kế event contract"]
    B --> C["2. Producer & consumer"]
    C --> D["3. Transaction & after commit"]
    D --> E["4. Publication registry"]
    E --> F["5. Retry & idempotency"]
    F --> G["6. Kiểm thử hệ thống"]
    G --> H["7. Quan sát & vận hành"]
    H --> I["8. Capstone hoàn chỉnh"]
~~~

## 2. Tình huống xuyên suốt: đơn hàng được thanh toán

Dùng một ứng dụng bán hàng đơn giản để thực hành. Cố gắng giữ nguyên tình huống khi chuyển chặng, vì như vậy bạn có thể quan sát một thay đổi thiết kế ảnh hưởng đến giao dịch, listener và vận hành ra sao.

| Module | Dữ liệu và trách nhiệm module sở hữu | Phản ứng khi đơn đã được thanh toán |
| --- | --- | --- |
| **orders** | Đơn hàng, trạng thái thanh toán được ghi nhận, lịch sử chuyển trạng thái | Phát **OrderPaid** khi một thanh toán hợp lệ làm trạng thái chuyển sang PAID |
| **notifications** | Yêu cầu gửi thông báo, mẫu nội dung và trạng thái gửi | Tạo yêu cầu gửi thông báo xác nhận |
| **loyalty** | Sổ điểm thưởng và quy tắc cộng điểm | Ghi điểm cho giao dịch hợp lệ một lần |
| **reporting** | Dữ liệu tổng hợp phục vụ báo cáo | Cập nhật chỉ số doanh thu theo event |

**Giả định nghiệp vụ:** việc thanh toán đã được một cơ chế đáng tin xác nhận trước khi **orders** ghi nhận PAID; bài thực hành không tự mô phỏng xác thực giao dịch với ngân hàng. Cùng một payment reference không được làm phát sinh nhiều lần chuyển trạng thái PAID.

Trong suốt lộ trình, **OrderPaid** là sự thật đã xảy ra, không phải command yêu cầu **loyalty** cộng điểm hay **notifications** gửi email. Các module nhận có thể hoàn thành muộn hơn giao dịch nguồn, nên không được mặc định rằng điểm thưởng và thông báo đã có ngay khi API đặt hàng trả thành công.

## 3. Chặng 0 — Nền tảng trước khi dùng event

### Kiến thức đầu vào cần tự kiểm tra

Bạn nên hiểu được **Spring Boot**, dependency injection, bean, repository, transaction với **@Transactional**, thao tác database và cơ bản của **JUnit**. Nên biết phân biệt một transaction đã commit với một phương thức Java vừa return. Nếu còn mơ hồ, thực hành một service lưu đơn thành công và một service ném exception khiến transaction rollback trước khi học event.

Đối với Spring Modulith, cần phân biệt:

- **Module ứng dụng** là ranh giới tổ chức mã nguồn/nghiệp vụ bên trong một ứng dụng; nó không nhất thiết là một Maven module, Gradle subproject hay một tiến trình riêng.
- **API công khai của module** chứa những kiểu module khác được phép tham chiếu. Đặt listener ở module nhận và chỉ để listener dùng API đã được công bố của module phát.
- **Internal package** là phần triển khai; module khác không nên import entity/repository/service nội bộ chỉ để tránh định nghĩa contract.
- **Phụ thuộc tĩnh** là việc module nhận import contract; **phụ thuộc lúc chạy** là thời điểm và cách phản ứng được thực thi. Event thay đổi quan hệ này, nhưng không tự loại bỏ mọi phụ thuộc.

Cấu trúc Java minh họa:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderPaid.java
│   ├── OrderPaymentService.java
│   └── internal
│       └── ...
├── notifications
│   └── ...
├── loyalty
│   └── ...
└── reporting
    └── ...
~~~

**Việc cần làm:** tạo một ứng dụng Spring Boot mẫu và tổ chức bốn module theo package. Tự vẽ chiều phụ thuộc hợp lệ; giải thích vì sao **orders** không cần import **loyalty**. Bổ sung kiểm tra cấu trúc Spring Modulith khi đã có đủ phụ thuộc.

**Qua chặng khi:** bạn xác định được module nào **sở hữu sự thật OrderPaid**, module nào chỉ phản ứng, và có thể chỉ ra ví dụ phụ thuộc qua package nội bộ cần loại bỏ.

## 4. Chặng 1 — Thiết kế hợp đồng sự kiện

Một event tốt cần ba yếu tố: **tên diễn đạt đúng mốc nghiệp vụ**, **payload đủ dùng nhưng không kéo theo mô hình nội bộ**, và **khả năng nhận diện một lần xảy ra**.

### Mẫu contract khởi đầu

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        UUID paymentId,
        Instant occurredAt
) {}
~~~

Hãy giữ event trong package API công khai của module **orders**; nếu đặt trong một package khác, phải công bố package đó qua cơ chế phù hợp của Spring Modulith. **Record** phù hợp với payload nhỏ, bất biến theo các field. Đừng đưa **Order** entity JPA, **EntityManager**, Spring service hoặc đối tượng có trạng thái sống vào event.

| Câu hỏi thiết kế | Quyết định ở bài thực hành |
| --- | --- |
| **Điều gì đã xảy ra?** | Một thanh toán hợp lệ đã khiến đơn được ghi nhận PAID |
| **Khi nào sinh event?** | Khi chuyển trạng thái nghiệp vụ được chấp nhận, bên trong transaction nguồn |
| **Một đơn có thể có nhiều event?** | Có thể có các event khác nhau như OrderCreated, OrderPaid, OrderRefunded; không dùng orderId thay cho eventId |
| **Vì sao cần eventId?** | Consumer theo dõi và từ chối xử lý trùng cùng một lần xảy ra |
| **Vì sao cần paymentId?** | Producer nhận ra thanh toán đã xử lý; consumer có thể dựa vào identity nghiệp vụ |
| **Dữ liệu nhạy cảm đặt ở đâu?** | Chỉ cung cấp field cần thiết; không đưa chi tiết phương thức thanh toán hay thông tin bí mật vào payload |

**Việc cần làm:** viết contract và một đoạn mô tả rõ ý nghĩa của từng field. Cho một bạn học đóng vai consumer và thử triển khai listener chỉ dựa vào contract; nếu họ buộc phải import entity nội bộ thì bạn cần xem lại payload hoặc API.

**Qua chặng khi:** bạn giải thích được khác biệt giữa **event** (sự thật đã xảy ra) và **command** (yêu cầu một bên làm việc), đồng thời chỉ ra được hệ quả khi đổi ý nghĩa của **OrderPaid** mà không cập nhật consumer.

## 5. Chặng 2 — Publish và subscribe trong cùng ứng dụng

Mục tiêu đầu tiên là làm cho một producer công bố sự kiện và nhiều consumer nhận độc lập. API cốt lõi là **ApplicationEventPublisher** của Spring.

### Producer mẫu

~~~java
package com.example.shop.orders;

import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderPaymentService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    OrderPaymentService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirmVerifiedPayment(UUID orderId, UUID paymentId) {
        Order order = orders.findById(orderId).orElseThrow();

        // Domain method minh họa: chỉ true khi có lần chuyển trạng thái mới.
        if (!order.markPaidIfNew(paymentId)) {
            return;
        }

        publisher.publishEvent(new OrderPaid(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                paymentId,
                clock.instant()
        ));
    }
}
~~~

**Order**, **OrderRepository** và **markPaidIfNew** là thành phần miền mà bạn tự hiện thực; đoạn mã giả định repository dùng JPA entity được quản lý trong transaction. Trong ứng dụng thực, thao tác nhận callback thanh toán cần xác thực và chống gửi lặp độc lập với việc consumer chống lặp event.

### Consumer mẫu

~~~java
package com.example.shop.loyalty;

import com.example.shop.orders.OrderPaid;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyOnOrderPaid {

    @EventListener
    void on(OrderPaid event) {
        // Bước đầu: chỉ log eventId và paymentId để thấy event được phân phối.
        System.out.println("Order paid: " + event.eventId());
    }
}
~~~

Trước tiên hãy chạy một consumer **loyalty** và một consumer **notifications**, cùng dùng **@EventListener** để thấy tính chất một event có nhiều bên nhận. **@EventListener** mặc định thực thi đồng bộ trong luồng publish, nếu không có cấu hình bất đồng bộ riêng; listener có thể chạy trước khi transaction nguồn commit. Vì vậy giai đoạn này chỉ nên log và xác nhận phân phối, **chưa thực hiện side effect không thể hoàn tác như gửi email thật**.

**Việc cần làm:** chạy một yêu cầu thanh toán hợp lệ, ghi lại eventId ở producer và cả hai consumer; thêm consumer **reporting** mà không chỉnh business logic của **orders**.

**Qua chặng khi:** bạn có thể mô tả luồng **publisher → multicaster → listener**, đồng thời chứng minh **orders** không import những consumer cụ thể.

## 6. Chặng 3 — Giao dịch, after commit và bất đồng bộ

Đây là mốc quan trọng nhất để tránh một lỗi phổ biến: **event được phát không có nghĩa transaction đã commit**. Khi producer gọi **publishEvent** trong transaction, **@EventListener** đồng bộ có thể chạy trước commit và exception của nó có thể ảnh hưởng transaction nguồn.

Ví dụ: nếu listener đã gửi email nhưng transaction order rollback, khách nhận email cho một trạng thái chưa tồn tại. Để các phản ứng độc lập chờ dữ liệu nguồn được lưu thành công, hãy học transactional listener.

| Cơ chế | Khi nào phản ứng? | Điểm cần hiểu |
| --- | --- | --- |
| **@EventListener** | Mặc định ngay khi publish | Đồng bộ, có thể trong transaction producer; lỗi có thể truyền về publisher |
| **@TransactionalEventListener(phase = AFTER_COMMIT)** | Khi transaction phát event commit thành công | Bản thân annotation không mặc định bất đồng bộ hoặc tạo transaction mới |
| **@ApplicationModuleListener** | Annotation tiện ích của Spring Modulith: hậu commit, bất đồng bộ, transaction mới | Phù hợp cho consumer thuộc module khác; kết quả có thể xuất hiện sau response API |

Chuyển **loyalty** sang mô hình phù hợp với Spring Modulith:

~~~java
package com.example.shop.loyalty;

import com.example.shop.orders.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyOnOrderPaid {

    private final LoyaltyLedger ledger;

    LoyaltyOnOrderPaid(LoyaltyLedger ledger) {
        this.ledger = ledger;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        ledger.awardOnce(event.eventId(), event.customerId());
    }
}
~~~

**LoyaltyLedger.awardOnce** là phương thức minh họa do bạn tự xây dựng. **@ApplicationModuleListener** kết hợp ý nghĩa của transactional event listener, **@Async** và transaction mới (**REQUIRES_NEW**). Cần cấu hình môi trường bất đồng bộ và transaction đúng theo ứng dụng/phiên bản đang sử dụng.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders
    participant DB as Database
    participant Loyalty as loyalty listener
    Client->>Orders: confirmVerifiedPayment(...)
    Orders->>DB: Cập nhật PAID trong T1
    Orders->>Orders: publishEvent(OrderPaid)
    Orders->>DB: Commit T1
    DB-->>Loyalty: Kích hoạt phản ứng sau commit
    Loyalty->>DB: Ghi điểm trong T2
    Loyalty-->>Loyalty: Hoàn tất
~~~

Đây là **sơ đồ logic**, không cam kết response HTTP trả trước khi listener được lên lịch. Consumer làm việc trong transaction riêng; thất bại của consumer sau commit không thể rollback transaction nguồn đã commit.

**Bài thực hành bắt buộc:**

1. Cho transaction producer rollback có chủ đích sau khi publish và kiểm tra listener hậu commit **không tạo điểm thưởng**.
2. Cho producer commit và consumer chạy thành công; ghi rõ lúc nào từng transaction hoàn tất.
3. Cho consumer ném exception và quan sát dữ liệu nguồn **vẫn PAID**.
4. Thử publish ngoài transaction; giải thích vì sao **@TransactionalEventListener** mặc định có thể không chạy nếu không bật **fallbackExecution**.
5. Tạo một consumer chậm và kiểm tra trạng thái eventual consistency; không kết luận rằng kết quả điểm thưởng phải có ngay trong HTTP response.

**Qua chặng khi:** bạn phân biệt được bốn thời điểm **phát event**, **commit nguồn**, **bắt đầu listener** và **hoàn thành hiệu ứng consumer**; giải thích đúng các trường hợp rollback.

## 7. Chặng 4 — Event Publication Registry: lưu dấu công việc chưa hoàn tất

Hậu commit giúp tránh phản ứng cho giao dịch rollback, nhưng tạo ra câu hỏi khó: **source đã commit, JVM dừng trước khi consumer kịp chạy hoặc đánh dấu hoàn tất thì sao?**

Để xử lý khoảng trống này, Spring Modulith có **Event Publication Registry** theo dõi việc phát và hoàn thành event cho các transactional listener được hỗ trợ. Khi cấu hình publication repository bền vững và hạ tầng phù hợp, mỗi listener được quan tâm có thể có bản ghi publication cần hoàn thành. Listener thành công làm publication tương ứng được hoàn tất; publication chưa hoàn tất cần chính sách khôi phục/resubmit.

~~~mermaid
flowchart TD
    A["orders thay đổi trạng thái trong T1"] --> B["Publish OrderPaid"]
    B --> C["Registry ghi publication theo listener trong T1"]
    C --> D{"T1 commit?"}
    D -->|Không| E["Rollback dữ liệu và publication"]
    D -->|Có| F["Consumer nhận sau commit"]
    F --> G{"Consumer xử lý thành công?"}
    G -->|Có| H["Đánh dấu publication hoàn tất"]
    G -->|Không / tiến trình dừng| I["Publication chưa hoàn tất"]
    I --> J["Kiểm tra, sửa lỗi và resubmit theo chính sách"]
    J --> F
~~~

Registry **không tự biến application event thành message broker qua nhiều process**, cũng không có nghĩa chỉ cần thêm một annotation là mặc định có lưu trữ bền và tự retry mãi mãi. Bạn phải tìm và cấu hình integration lưu publication phù hợp với Spring Modulith và cách lưu trữ đang dùng (ví dụ JDBC hoặc JPA), xác minh transaction boundaries, đồng thời xác định cơ chế resubmit cho publication chưa hoàn tất. Những API và tùy chọn resubmission có thể thay đổi theo phiên bản, nên bài thực hành phải bám đúng dependency và tài liệu của phiên bản đã chọn.

**Việc cần làm:**

- Cấu hình storage bền vững cho publication trong ứng dụng mẫu.
- Phát event trong transaction rồi xác minh publication được lưu hoặc rollback tương ứng với transaction nguồn.
- Cố ý cho **loyalty** lỗi sau commit; xác minh tồn tại publication chưa hoàn tất và **orders** vẫn PAID.
- Khắc phục lỗi, kích hoạt khả năng khôi phục theo cấu hình đang dùng và đọc lại trạng thái hoàn tất.
- Thử restart giữa lúc cần xử lý để chứng minh registry tồn tại sau vòng đời JVM.

**Qua chặng khi:** có bằng chứng từ database/log cho cả ba trường hợp **rollback**, **listener hoàn thành**, **listener thất bại còn publication chưa hoàn tất** và bạn giải thích được cách khôi phục. Chỉ test rằng một log xuất hiện chưa đủ chứng minh độ bền của event.

## 8. Chặng 5 — Retry và idempotency: thiết kế cho sự kiện bị giao lại

Ngay cả khi consumer đã hoàn thành side effect, tiến trình có thể dừng **trước khi registry đánh dấu hoàn tất**. Khi resubmit, cùng event có thể được giao lại. Thiết kế nên hướng tới xử lý **at-least-once** có thể lặp, không giả định mỗi listener chạy đúng một lần.

### Tách hai lớp chống xử lý trùng

- **Ở producer:** webhook/callback thanh toán lặp với cùng **paymentId** phải không tạo một lần chuyển trạng thái nghiệp vụ mới. Khóa duy nhất hoặc logic transaction theo payment reference có thể bảo vệ điểm này.
- **Ở consumer:** cùng **eventId** được giao lại không được ghi nhiều lần một hiệu ứng, chẳng hạn cộng điểm hoặc tạo yêu cầu gửi email.

Một schema minh họa cho **loyalty**:

~~~sql
CREATE TABLE loyalty_award (
    award_id       BIGINT PRIMARY KEY,
    event_id       VARCHAR(36) NOT NULL,
    customer_id    VARCHAR(36) NOT NULL,
    points         INTEGER NOT NULL,
    CONSTRAINT uq_loyalty_award_event UNIQUE (event_id)
);
~~~

Khi viết **awardOnce**, hãy ghi dấu việc xử lý và cập nhật ledger/điểm trong **cùng transaction**. **Unique constraint** quan trọng vì hai lần xử lý song song có thể cùng thấy chưa tồn tại nếu chỉ kiểm tra bằng truy vấn **SELECT** trước đó.

| Lỗi giả lập | Consumer nên hành động gì? |
| --- | --- |
| DB tạm hết kết nối | Ném lỗi phù hợp để publication không bị đánh dấu hoàn tất và xử lý lại sau |
| Event trùng với cùng eventId | Bỏ qua hiệu ứng đã có, báo xử lý thành công có kiểm soát |
| Payload vi phạm bất biến nghiệp vụ | Ghi lỗi có thể chẩn đoán; không retry vô hạn với dữ liệu không thể sửa bằng chờ |
| External API timeout sau khi đã thực hiện | Có nguy cơ side effect lặp; dùng idempotency key hoặc xác nhận trạng thái bên ngoài nếu có |
| Consumer bị hỏng lâu ngày | Cảnh báo publication tồn đọng; vận hành sửa lỗi và resubmit có giới hạn |

**Retry phải có giới hạn và chiến lược.** Hãy định nghĩa số lần thử, khoảng chờ/backoff khi phù hợp, cách cảnh báo, cách sửa lỗi và quy trình vận hành sau khi quá ngưỡng. Một event bị kẹt phải nhìn thấy được trong hệ thống, không bị “nuốt” exception rồi đánh dấu hoàn thành giả.

Đối với **notifications**, một email được nhà cung cấp nhận rồi nhưng consumer crash có thể gây gửi lại. Transaction nội bộ không thể rollback email đã gửi; nếu provider không hỗ trợ idempotency, cần nêu rõ giới hạn, tổ chức bảng yêu cầu gửi và quy trình xác minh.

**Qua chặng khi:** bạn gửi cùng eventId hai lần, kể cả đồng thời, và chứng minh database chỉ ghi một tác dụng hợp lệ. Tiếp theo, giải thích được vì sao **eventId khác nhau nhưng cùng paymentId** vẫn có thể là lỗi ở producer.

## 9. Chặng 6 — Kiểm thử theo ba tầng

Đối với hệ thống event-driven, **test happy path không đủ**. Nên chia kiểm thử thành ba nhóm để xác định lỗi đang nằm ở contract, nghiệp vụ consumer hay cơ chế giao nhận.

### Tầng A: kiểm tra cấu trúc và contract

Dùng Spring Modulith để kiểm tra module boundary, bảo đảm **loyalty** và **notifications** chỉ tham chiếu API công khai của **orders**.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTests {

    @Test
    void modulesRespectBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ShopApplication** là lớp khởi động ứng dụng minh họa; package, classpath và dependency Spring Modulith phải được cấu hình phù hợp.

### Tầng B: kiểm thử producer và consumer

Spring Modulith cung cấp các hỗ trợ như **@ApplicationModuleTest**, **PublishedEvents** và **Scenario** (tùy tập phụ thuộc test được cài đặt). Hãy kiểm tra:

- Producer chỉ phát **OrderPaid** khi trạng thái thật sự chuyển sang PAID.
- Payload chứa các ID và thời điểm đúng quy tắc.
- Consumer ghi một bản ghi ledger khi nhận event hợp lệ.
- Consumer không nhân đôi hiệu ứng khi nhận lại event.
- Module nhận không phụ thuộc package nội bộ của module phát.

### Tầng C: kiểm thử transaction, registry và restart

| Kịch bản | Dấu hiệu PASS |
| --- | --- |
| Producer rollback sau publish | Không có phản ứng hậu commit; publication theo transaction không được commit |
| Producer commit | Listener hậu commit thực thi và tạo hiệu ứng |
| Consumer lỗi sau commit | Nghiệp vụ producer vẫn được commit; publication chưa hoàn tất còn có thể xác định |
| Resubmit cùng event | Tác dụng nghiệp vụ không nhân đôi |
| Restart sau commit và trước khi listener hoàn tất | Publication chưa hoàn tất được phát hiện và có thể xử lý lại |
| Hai consumer, một consumer lỗi | Có thể biết listener nào đã hoàn thành và listener nào cần khôi phục |

**Bẫy khi kiểm thử:** test được bọc transaction rồi tự rollback ở cuối thường không kích hoạt listener **AFTER_COMMIT**. Muốn kiểm chứng sau commit, phải để transaction thực sự commit trong kịch bản test. Với listener bất đồng bộ, dùng cách chờ theo điều kiện có timeout (chẳng hạn hỗ trợ của **Scenario**) thay vì đợi một số mili giây cố định.

**Qua chặng khi:** một test integration có thể tái hiện lỗi consumer và chứng minh đường khôi phục, không chỉ xác nhận **ApplicationEventPublisher.publishEvent** đã được gọi.

## 10. Chặng 7 — Quan sát, cảnh báo và vận hành

Một event-driven module khó vận hành nếu chỉ biết request của producer đã thành công. Cần trả lời được **event nào**, **consumer nào**, **trạng thái publication nào** và **tác động nghiệp vụ thực tế nào**.

| Nhóm tín hiệu | Nội dung nên theo dõi | Câu hỏi vận hành |
| --- | --- | --- |
| **Log có cấu trúc** | eventId, eventType, orderId/paymentId, consumer, trạng thái, lỗi | “Đơn này đã đến listener nào?” |
| **Metric** | Số publication chưa hoàn tất, số lỗi, retry, độ trễ | “Có tồn đọng đang tăng lên không?” |
| **Độ tuổi publication** | Khoảng thời gian từ publish đến lúc hoàn tất hoặc đang mở | “Sự kiện nào mắc lâu nhất?” |
| **Idempotency** | Số duplicate được phát hiện và chặn | “Retry có tạo ra lượng trùng bất thường?” |
| **Tracing/correlation** | ID liên kết request, producer và consumer | “Đường đi của một sự kiện xuyên qua các module ra sao?” |

Không log payload chứa dữ liệu thanh toán hoặc thông tin cá nhân nhạy cảm. Nếu ghi **paymentId** hay **orderId** để truy vết, hãy áp dụng quyền truy cập log và quy định bảo mật dữ liệu phù hợp.

**Bài diễn tập vận hành:**

1. Cho consumer **notifications** ném lỗi trong một số lần nhận.
2. Phát một sự kiện hợp lệ; đọc dữ liệu publication để xác định listener chưa hoàn tất.
3. Quan sát metric số publication còn mở và thời gian tồn đọng tăng lên.
4. Sửa nguyên nhân; resubmit theo quy trình của bản ứng dụng đang triển khai.
5. Xác nhận trạng thái publication hoàn tất, tác dụng nghiệp vụ xảy ra đúng một lần và số tồn đọng giảm.
6. Ghi một runbook ngắn hướng dẫn nhận biết và xử lý lỗi tương tự.

**Qua chặng khi:** một người khác chỉ có **eventId** và công cụ quan sát vẫn có thể xác định nguyên nhân vì sao consumer không hoàn tất, cách khôi phục và điều kiện dừng retry.

## 11. Chặng 8 — Capstone: hoàn thiện một luồng OrderPaid

Hãy kết hợp những gì đã học thành một sản phẩm nhỏ có thể trình diễn trước người review.

~~~mermaid
flowchart LR
    A["Đầu vào thanh toán đã xác thực"] --> B["orders ghi PAID trong T1"]
    B --> C["Publish OrderPaid"]
    C --> D["Registry: publication theo consumer"]
    D --> E["notifications: tạo yêu cầu gửi"]
    D --> F["loyalty: awardOnce"]
    D --> G["reporting: cập nhật dữ liệu"]
    E --> H["Hoàn tất hoặc chờ retry"]
    F --> H
    G --> H
    H --> I["Metrics, logs, resubmit"]
~~~

**Tính năng tối thiểu:**

1. **Producer trong orders**: nhận một giao dịch thanh toán đã được xác thực, kiểm tra chuyển trạng thái, phát **OrderPaid** có eventId.
2. **Ba consumer độc lập**: notifications tạo yêu cầu gửi, loyalty ghi ledger điểm thưởng, reporting cập nhật số liệu của mình.
3. **After commit**: các consumer không làm side effect nếu transaction nguồn rollback.
4. **Registry bền vững**: một consumer lỗi để lại publication chưa hoàn tất và có cách khôi phục.
5. **Idempotency**: cùng event được giao lại không tạo hiệu ứng trùng.
6. **Kiểm thử**: module boundary, publisher, rollback, listener lỗi, retry/resubmit, cạnh tranh nhận trùng và restart.
7. **Quan sát**: hiển thị được lỗi, publication tồn đọng và độ trễ theo eventId.

**Kịch bản demo nên có hai phần.** Phần thành công cho thấy producer commit, ba consumer tự xử lý và tất cả publication được hoàn tất. Phần lỗi cố ý làm **loyalty** thất bại sau commit: đơn vẫn PAID, notifications có thể hoàn tất, còn publication của loyalty được phát hiện để xử lý lại. Khi phục hồi, ledger chỉ tăng điểm đúng một lần.

Đây là bằng chứng kiến trúc rõ ràng hơn rất nhiều so với một demo chỉ in dòng “Event received” ra console.

## 12. Lịch thực hành gợi ý

Thời gian phụ thuộc nền tảng Java/Spring Boot hiện có; bảng sau là **gợi ý tổ chức phiên học**, không phải ước lượng bắt buộc.

| Phiên | Trọng tâm | Kết quả trước khi kết thúc |
| --- | --- | --- |
| **Phiên 1** | Chặng 0–2: ranh giới, contract, publisher, hai consumer | Luồng phát và nhận OrderPaid chạy được |
| **Phiên 2** | Chặng 3: transaction, after commit, async | Test chứng minh rollback và hậu commit |
| **Phiên 3** | Chặng 4–5: registry, lỗi, retry, idempotency | Lỗi consumer còn dấu vết và giao lại không nhân đôi hiệu ứng |
| **Phiên 4** | Chặng 6–7: test và observability | Bộ test nghiệp vụ/giao nhận và runbook vận hành |
| **Phiên 5** | Chặng 8: capstone và review | Demo thành công, thất bại, khôi phục; tài liệu kiến trúc hoàn chỉnh |

Nếu có ít thời gian, hãy giữ **một bài thực hành xuyên suốt**, không đổi sang ví dụ khác ở mỗi phiên. Nếu đã quen Spring Boot và transaction, có thể rút gọn chặng 0 nhưng không bỏ việc kiểm tra module boundary.

### Ma trận tự đánh giá trước khi kết thúc

| Mức | Dấu hiệu người học đã đạt |
| --- | --- |
| **Cơ bản** | Giải thích producer/consumer, tạo event đúng nghĩa, publish và nhận qua listener |
| **Trung cấp** | Phân biệt sync/async/after commit, xử lý rollback, hiểu eventual consistency |
| **Khá** | Cấu hình registry bền vững, kiểm chứng publication chưa hoàn tất và cơ chế khôi phục |
| **Nâng cao** | Xử lý event lặp bằng idempotency trong transaction; có test lỗi/restart và quan sát vận hành |
| **Sẵn sàng áp dụng** | Giải thích được mọi trạng thái lỗi trong capstone, biết khi nào **không nên** dùng event và review được module boundary |

## 13. Những ngộ nhận cần loại bỏ trên đường học

| Ngộ nhận | Điều cần nhớ |
| --- | --- |
| “Gọi publishEvent xong là tất cả consumer đã xử lý.” | Publish chỉ phát event vào cơ chế phân phối; listener có thể chạy sau commit và bất đồng bộ. |
| “@EventListener luôn chạy sau commit.” | Theo mặc định nó có thể chạy ngay trong transaction đang mở; cần transactional listener để kiểm soát thời điểm. |
| “@TransactionalEventListener tự tạo transaction mới.” | Không. Việc chạy sau commit và việc mở transaction mới là hai quyết định khác nhau. |
| “@ApplicationModuleListener làm mất mọi rủi ro sự kiện.” | Nó giúp bố trí transaction và async; độ bền phụ thuộc registry/storage/recovery được cấu hình. |
| “Có registry rồi thì consumer không bao giờ nhận trùng.” | Retry có thể giao lại một event; idempotency vẫn bắt buộc với side effect cần đúng một lần. |
| “Event nội bộ đồng nghĩa message broker liên tiến trình.” | Application event của Spring chủ yếu hoạt động trong tiến trình ứng dụng; tích hợp ngoài cần thiết kế bổ sung. |
| “Tách module qua event nghĩa là dữ liệu cuối cùng phải đồng nhất ngay.” | Sau commit, các consumer có thể cập nhật muộn hơn; cần quy định rõ trạng thái eventual consistency. |
| “Test publisher được gọi là đã test xong.” | Cần test transaction, listener, lỗi, registry, nhận trùng và recovery. |
| “Event sourcing chính là Spring application events.” | Event sourcing dùng event như nguồn dữ liệu để tái dựng trạng thái; event giao tiếp module không mặc nhiên là event sourcing. |

## 14. Checklist hoàn thành lộ trình

Chỉ đánh dấu hoàn tất khi có code hoặc kết quả kiểm thử chứng minh được điều tương ứng.

- [ ] Giải thích trách nhiệm producer, consumer và module boundary.
- [ ] Tạo contract **OrderPaid** công khai, bất biến và có ngữ nghĩa rõ ràng.
- [ ] Một producer phát event, nhiều consumer đăng ký nhận độc lập.
- [ ] Chứng minh sự khác nhau giữa **@EventListener**, **@TransactionalEventListener** và **@ApplicationModuleListener**.
- [ ] Viết test rollback để chứng minh side effect hậu commit không chạy.
- [ ] Cấu hình publication repository bền vững và tìm được publication chưa hoàn tất.
- [ ] Thử lỗi sau commit, resubmit và restart để kiểm chứng đường khôi phục.
- [ ] Thiết kế khóa idempotency ở producer và consumer; kiểm tra xử lý lặp và song song.
- [ ] Chạy kiểm tra ranh giới module bằng Spring Modulith.
- [ ] Có test tích hợp cho luồng lỗi và quan sát eventId, consumer, retry, độ trễ.
- [ ] Trình diễn capstone với đường thành công, đường lỗi và xử lý lại.

### Kết luận định hướng

Thứ tự học hiệu quả cho **SPRING_MODULITH_APPLICATION_EVENTS** là **hiểu module → thiết kế sự thật nghiệp vụ → publish/subscribe → hiểu transaction → lưu dấu publication → retry và chống trùng → kiểm thử → quan sát vận hành**. Giá trị cốt lõi của Spring Modulith application events nằm ở khả năng để các module hợp tác thông qua một hợp đồng sự kiện rõ ràng, trong khi mỗi module vẫn sở hữu nghiệp vụ và dữ liệu của mình.

Đích cuối của lộ trình không chỉ là “phát được event”, mà là **chứng minh được điều gì xảy ra khi commit, rollback, consumer thất bại, sự kiện bị giao lại hoặc tiến trình khởi động lại**. Khi trả lời được những tình huống đó bằng code, test và dữ liệu quan sát, bạn đã có nền tảng để thiết kế giao tiếp module đáng tin cậy trong Spring Modulith.
