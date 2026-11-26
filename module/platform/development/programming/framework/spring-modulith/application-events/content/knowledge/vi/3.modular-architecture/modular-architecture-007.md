# Module sở hữu dữ liệu

## 1. Quyền sở hữu dữ liệu là gì trong modular monolith?

Trong một **modular monolith**, nhiều module nghiệp vụ cùng chạy trong một ứng dụng và thường cùng sử dụng một cơ sở dữ liệu vật lý. Tuy nhiên, việc dùng chung kết nối database **không có nghĩa là mọi module đều có quyền đọc, ghi hoặc tùy ý sửa cấu trúc mọi bảng**. Kiến trúc module hiệu quả đòi hỏi phân định rõ **module nào sở hữu dữ liệu nào**.

**Module sở hữu dữ liệu (data ownership)** nghĩa là một module chịu trách nhiệm về vòng đời, quy tắc nghiệp vụ và tính đúng đắn của một tập thông tin. Với dữ liệu mà nó sở hữu, module quyết định:

- Cấu trúc lưu trữ (entity, bảng, quan hệ, chỉ mục và cách migration).
- Điều kiện để dữ liệu được tạo, sửa, chuyển trạng thái hoặc xóa.
- API nào cho phép module khác yêu cầu thao tác hoặc lấy thông tin.
- Sự kiện nghiệp vụ nào được phát ra khi trạng thái quan trọng thay đổi.
- Cách kiểm thử, quan sát và khôi phục dữ liệu sau khi có lỗi.

Ví dụ trong hệ thống thương mại điện tử:

| Module | Dữ liệu thuộc quyền sở hữu | Quy tắc chính |
| --- | --- | --- |
| `orders` | Đơn hàng, dòng hàng, trạng thái đơn | Khi nào được đặt, xác nhận, hủy đơn |
| `inventory` | Số lượng tồn, các lượt giữ hàng | Không giữ vượt số lượng có thể bán |
| `payments` | Giao dịch, trạng thái thu tiền | Không ghi nhận thu tiền thành công hai lần |
| `loyalty` | Sổ cộng/trừ điểm và số dư điểm | Cộng điểm đúng điều kiện, chống cộng trùng |
| `notifications` | Trạng thái gửi thông báo | Gửi đúng người, ghi nhận và xử lý lỗi gửi |

`orders` có thể biết mã giao dịch hoặc trạng thái thanh toán đã được công bố, nhưng **không sở hữu** bản ghi giao dịch của `payments`. Tương tự, `loyalty` có thể nhận sự kiện đơn đã thanh toán, nhưng không được tự cập nhật bảng đơn hàng để đánh dấu đã trả tiền.

Sau bài này, bạn cần phân biệt được **sở hữu dữ liệu** với **vị trí lưu dữ liệu**, nhận diện phụ thuộc xuyên ranh giới module, thiết kế API và application event cho các nhu cầu tích hợp, đồng thời xác định cách bảo đảm tính nhất quán khi listener xử lý sau commit.

## 2. Sở hữu logic khác với sở hữu database vật lý

Một ứng dụng Spring Modulith có thể dùng **một PostgreSQL instance, một database và thậm chí cùng một schema** trong khi vẫn thực thi quyền sở hữu dữ liệu ở cấp module. Ngược lại, việc đặt mỗi module ở một schema riêng chưa đủ chứng minh có ranh giới tốt nếu code vẫn tùy ý truy cập dữ liệu của nhau.

~~~mermaid
flowchart TB
    subgraph APP["Một Spring Boot application"]
        subgraph ORDER["Module orders"]
            OS["OrderService"] --> OR["OrderRepository"]
        end
        subgraph PAYMENT["Module payments"]
            PS["PaymentService"] --> PR["PaymentRepository"]
        end
        subgraph LOYALTY["Module loyalty"]
            LS["LoyaltyService"] --> LR["RewardRepository"]
        end
    end
    subgraph DB["Một cơ sở dữ liệu vật lý"]
        OT[("orders_*")]
        PT[("payments_*")]
        LT[("loyalty_*")]
    end
    OR --> OT
    PR --> PT
    LR --> LT
~~~

Trong sơ đồ, các mũi tên từ repository đến bảng thể hiện **quyền ghi chính**. Database dùng chung đem lại sự thuận tiện về vận hành, migration và transaction cục bộ, nhưng trách nhiệm giữ đúng ranh giới thuộc về mã nguồn, review và các phép kiểm thử cấu trúc.

Có thể áp dụng nhiều mức cô lập:

1. **Cấp mã nguồn:** `orders` chỉ khai báo repository và thực thể cho dữ liệu đơn hàng; các module khác truy cập qua API công khai.
2. **Cấp schema:** dùng schema riêng theo module, ví dụ `orders.*`, `payments.*`. Cách này làm trách nhiệm sở hữu dễ nhìn hơn.
3. **Cấp quyền database:** tùy chính sách và khả năng triển khai, có thể hạn chế quyền truy cập của từng thành phần; trong một ứng dụng sử dụng chung một database user, mức này thường chưa tạo ra rào chắn thực sự giữa các module.

Các cấp này có thể kết hợp, nhưng **không bắt buộc phải tách database** để gọi ứng dụng là modular monolith. Điều quan trọng là module sở hữu kiểm soát các thao tác thay đổi dữ liệu và định nghĩa hợp đồng cho module còn lại.

## 3. Vì sao truy cập trực tiếp vào dữ liệu module khác gây hại?

Giả sử `loyalty` cần cộng điểm khi đơn hàng đã được thanh toán. Một triển khai không phù hợp là tự đọc bảng đơn hàng qua repository của `orders` rồi tự chỉnh sửa trạng thái liên quan:

~~~java
// Minh họa anti-pattern trong module loyalty
@Service
class LoyaltyService {
    private final OrderRepository orders;  // Repository nội bộ của orders
    private final RewardRepository rewards;

    void grantPoints(UUID orderId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();
        if (order.getPaymentState() == PaymentState.PAID) {
            rewards.save(new RewardEntity(orderId, 10));
        }
    }
}
~~~

Đoạn mã tạo ra các vấn đề:

- **Phụ thuộc vào mô hình nội bộ:** đổi tên field, đổi mapping ORM hay chia bảng của `orders` có thể làm `loyalty` hỏng, dù hợp đồng nghiệp vụ không đổi.
- **Lách quy tắc nghiệp vụ:** module khác có thể chỉnh entity/repository mà không đi qua điều kiện kiểm tra trong service sở hữu.
- **Khó xác định trách nhiệm:** khi dữ liệu sai, không rõ module nào là nguồn gây ra thay đổi.
- **Phụ thuộc vào transaction và persistence context:** truy cập lazy property, transaction đang mở hay cách khóa dữ liệu của module khác có thể gây lỗi khó dự đoán.
- **Khó tách module về sau:** một module đã phụ thuộc vào bảng và entity nội bộ của module kia rất khó triển khai hay kiểm thử độc lập.

Truy vấn SQL liên bảng trực tiếp cũng có thể gây ràng buộc tương tự, kể cả khi không import một Java repository nào. Vì vậy, **kiểm thử dependency của Spring Modulith là cần thiết nhưng chưa đủ**: các truy vấn SQL, câu lệnh native, truy cập dùng chung `JdbcTemplate` và công cụ báo cáo cũng cần được xem xét.

Không phải mọi quan hệ khóa ngoại giữa các bảng thuộc nhiều module đều bị cấm trong mọi hệ thống. Tuy nhiên, một khóa ngoại hay cascade xuyên module có thể khiến quá trình thay đổi schema và vòng đời dữ liệu bị ràng buộc chặt. Đó là **quyết định kiến trúc cần chủ động đánh giá**, đặc biệt nếu muốn tăng mức độc lập của các module trong tương lai.

## 4. Tổ chức ranh giới dữ liệu bằng package Spring Modulith

Spring Modulith thường khám phá application module từ các package trực tiếp dưới package gốc của ứng dụng. Public API của module có thể đặt ở package gốc; các chi tiết implementation nằm trong package nội bộ hoặc package không được xuất ra như API.

~~~text
com.example.shop
├── ShopApplication.java
├── orders/
│   ├── OrderPaid.java                  # Event công khai
│   ├── OrderLookup.java                # API tra cứu công khai
│   ├── OrderSummary.java               # DTO công khai
│   └── internal/
│       ├── OrderEntity.java            # Mô hình persistence riêng
│       ├── OrderRepository.java        # Repository riêng
│       └── OrderService.java           # Thay đổi trạng thái đơn
├── payments/
│   ├── PaymentConfirmed.java           # Event thuộc payments
│   └── internal/
│       ├── PaymentEntity.java
│       └── PaymentRepository.java
└── loyalty/
    └── internal/
        ├── RewardCreditEntity.java     # Dữ liệu điểm thuộc loyalty
        ├── RewardRepository.java
        └── LoyaltyOrderPaidListener.java
~~~

Trong ví dụ này:

- `orders.internal.OrderRepository` không phải API cho các module khác.
- `orders.OrderLookup` và `orders.OrderSummary` cho phép truy vấn thông tin đơn hàng được công bố mà không lộ entity.
- `orders.OrderPaid` là hợp đồng event mà `loyalty` có thể tiêu thụ.
- `loyalty` chỉ ghi các bảng `loyalty` sở hữu, chẳng hạn `reward_credit` và `reward_balance`.

Với API lớn, Spring Modulith hỗ trợ mô tả các *named interface* để công khai một phần package rõ ràng hơn. Dù tổ chức theo cách nào, nguyên tắc vẫn là **module sử dụng chỉ phụ thuộc vào hợp đồng mà module sở hữu chủ động công bố**.

Hãy tránh trả về trực tiếp `OrderEntity` từ public API: đối tượng JPA thường mang theo mapping, trạng thái managed/detached, lazy loading và chi tiết persistence không nên trở thành hợp đồng liên module.

## 5. Hai cách hợp lệ để module khác lấy dữ liệu

Module `loyalty` có thể cần biết giá trị đơn hàng; `reporting` cần thống kê đơn theo ngày. Không có một cơ chế nào phù hợp với mọi trường hợp. Lựa chọn chủ yếu phụ thuộc vào **yêu cầu về thời điểm và tính nhất quán của thông tin**.

### 5.1. Gọi API công khai của module sở hữu khi cần kết quả hiện tại

`orders` có thể cung cấp API chỉ đọc. Hai kiểu `public` sau được đặt trong **hai file Java riêng** cùng package:

~~~java
package com.example.shop.orders;

import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;

public interface OrderLookup {
    Optional<OrderSummary> findSummary(UUID orderId);
}

public record OrderSummary(
        UUID orderId,
        String status,
        BigDecimal totalAmount
) {}
~~~

Implementation trong `orders.internal` sử dụng `OrderRepository` để ánh xạ entity thành DTO. Module khác chỉ phụ thuộc `OrderLookup` và `OrderSummary`.

Lợi thế là bên gọi nhận phản hồi trực tiếp và có thể xử lý lỗi ngay trong request. Đổi lại, bên gọi **phụ thuộc vào sự sẵn sàng và thời gian xử lý API**; gọi lặp lại nhiều lần có thể tăng độ trễ và tạo chỗ thắt hiệu năng. Nếu hành vi thay đổi trạng thái cần đồng bộ, module sở hữu nên cung cấp một API command có kiểm tra điều kiện nghiệp vụ và trả kết quả thích hợp, thay vì cho sửa entity từ bên ngoài.

### 5.2. Nhận event và giữ bản sao đọc cục bộ khi chấp nhận cập nhật trễ

Module `reporting` có thể nghe `OrderPaid` và lưu một bản ghi chỉ phục vụ mục đích báo cáo. `reporting` **sở hữu bảng projection của chính mình**, dù thông tin được dẫn xuất từ event của `orders`.

~~~mermaid
sequenceDiagram
    participant O as orders
    participant D as Database
    participant E as Event bus
    participant R as reporting
    O->>D: Xác nhận trạng thái thanh toán
    O->>E: publish(OrderPaid)
    O->>D: Commit transaction orders
    E-->>R: Giao event sau commit
    R->>D: Ghi order_report_projection
    Note over O,R: Projection có thể cập nhật muộn hơn dữ liệu gốc
~~~

Đây là dạng **event-driven projection**: module nguồn là nơi quyết định sự thật nghiệp vụ; module nhận xây dựng góc nhìn phù hợp với nhu cầu của mình. Phải chấp nhận độ trễ và có cách xử lý sự kiện bị lặp, đến muộn hoặc không đúng thứ tự.

| Nhu cầu | Cách phối hợp thường phù hợp | Lý do |
| --- | --- | --- |
| Kiểm tra điều kiện bắt buộc trước khi xác nhận đơn | Gọi API đồng bộ của module có thẩm quyền | Cần kết quả ngay để quyết định commit hay từ chối |
| Hiển thị thông tin đơn mới nhất trong trang quản trị | API truy vấn của `orders` | Cần nguồn sự thật hiện hành |
| Gửi thông báo sau khi thanh toán | Application event sau commit | Không cần chặn luồng thanh toán vì email |
| Tổng hợp doanh thu theo ngày | Event + projection trong `reporting` | Có thể tối ưu đọc và chấp nhận cập nhật trễ |
| Đồng bộ điểm thưởng | Event + dữ liệu riêng và chống trùng | Module `loyalty` tự quản lý vòng đời điểm |

**Quyền sở hữu bản sao dữ liệu không đồng nghĩa quyền sửa nguồn.** `reporting` có thể cập nhật projection riêng, nhưng không trở thành module sở hữu trạng thái đơn hàng. Khi định nghĩa hợp đồng, cần ghi rõ dữ liệu nào là nguồn chuẩn (*source of truth*), dữ liệu nào là bản sao phục vụ đọc.

## 6. Ví dụ end-to-end: orders phát event, loyalty sở hữu sổ điểm

Giả sử một đơn đã được thanh toán thành công sẽ cộng 10 điểm cho khách hàng. `orders` sở hữu trạng thái đơn hàng; `loyalty` sở hữu sổ ghi điểm. Sau commit thanh toán, `loyalty` có thể nhận event và ghi điểm trong transaction của chính mình.

### 6.1. Định nghĩa event công khai

~~~java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {}
~~~

Event mang **giá trị bất biến** và đủ thông tin để listener xử lý, không chứa `OrderEntity` hay `OrderRepository`. `eventId` giúp theo dõi từng lần phát sự kiện; `orderId` là khóa nghiệp vụ để bảo đảm một đơn chỉ được cộng điểm đúng chính sách. Nếu một đơn có thể thanh toán nhiều lần từng phần, khóa chống trùng và tên sự kiện phải phản ánh đúng mô hình đó, không mặc định `orderId` luôn là duy nhất.

### 6.2. Module sở hữu cập nhật trạng thái rồi publish

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderPaid;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderPaymentService(OrderRepository orders,
                               ApplicationEventPublisher publisher,
                               Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void recordPayment(UUID orderId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();
        if (order.isPaid()) {
            return; // Không phát lại khi ghi nhận trạng thái đã thanh toán
        }
        order.markPaid(); // Chỉ orders được đổi trạng thái của đơn
        publisher.publishEvent(new OrderPaid(
                UUID.randomUUID(), order.getId(),
                order.getCustomerId(), Instant.now(clock)));
    }
}
~~~

Đây là mã minh họa, giả định repository, entity và `Clock` đã được cấu hình. Trong ứng dụng thực, cần xác thực kết quả thanh toán từ module có thẩm quyền, chống callback thanh toán trùng và bảo đảm chuyển trạng thái hợp lệ. Điều cần tập trung ở đây là `orders` **không gọi `LoyaltyRepository`**, và việc publish nằm trong transaction cập nhật dữ liệu nguồn.

### 6.3. Module nhận tự quyết định cách ghi điểm

~~~java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.OrderPaid;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyOrderPaidListener {
    private final LoyaltyService loyalty;

    LoyaltyOrderPaidListener(LoyaltyService loyalty) {
        this.loyalty = loyalty;
    }

    @ApplicationModuleListener
    public void on(OrderPaid event) {
        loyalty.creditPaidOrder(
                event.orderId(), event.customerId(), 10);
    }
}
~~~

`@ApplicationModuleListener` của Spring Modulith kết hợp listener sau commit, thực thi bất đồng bộ và transaction mới (thông qua `REQUIRES_NEW`). Cần cấu hình hỗ trợ xử lý bất đồng bộ (`@EnableAsync` và executor phù hợp khi ứng dụng chưa có) và các dependency tương ứng. Vì listener chạy sau khi transaction nguồn commit, việc gửi/ghi điểm thất bại **không thể hoàn tác đơn đã được thanh toán**.

Trong `LoyaltyService.creditPaidOrder(...)`, thao tác ghi sổ điểm và tăng số dư phải nằm trong **một transaction** của `loyalty`. Để tránh cộng điểm nhiều lần khi event được giao lại, cần một ràng buộc duy nhất trong database. Ví dụ với PostgreSQL:

~~~sql
CREATE TABLE loyalty.reward_credit (
    id              UUID PRIMARY KEY,
    order_id        UUID NOT NULL UNIQUE,
    customer_id     UUID NOT NULL,
    points          INTEGER NOT NULL CHECK (points > 0),
    created_at      TIMESTAMPTZ NOT NULL
);

-- Chạy trong cùng transaction với bước tăng số dư.
INSERT INTO loyalty.reward_credit
    (id, order_id, customer_id, points, created_at)
VALUES
    (:id, :orderId, :customerId, :points, :now)
ON CONFLICT (order_id) DO NOTHING;
~~~

Chỉ khi câu lệnh `INSERT` thực sự thêm **một bản ghi mới** (affected rows = 1) mới tăng `reward_balance`. Khi affected rows = 0, đơn đã có bản ghi thưởng và không tăng số dư lần nữa. Hai thao tác ghi sổ và cập nhật số dư phải cùng transaction, đồng thời thao tác tăng số dư cần an toàn khi nhiều request cùng cập nhật một khách hàng (ví dụ atomic SQL update hoặc khóa phù hợp).

**Đây là ví dụ minh họa theo PostgreSQL**, không phải SQL di động cho mọi hệ quản trị. Nếu nghiệp vụ cho phép nhiều loại cộng điểm trên cùng đơn, thay khóa duy nhất bằng `(order_id, reward_type)`; nếu mỗi payment có thể tạo phần thưởng khác nhau, chọn khóa tương ứng với quy tắc nghiệp vụ thực tế.

### 6.4. Kết quả đạt được

`orders` có thể triển khai thêm module `loyalty` mà không cần sửa code xác nhận đơn mỗi khi xuất hiện consumer mới. `loyalty` kiểm soát toàn bộ dữ liệu điểm, có thể thay đổi công thức điểm, cấu trúc bảng, cơ chế retry hoặc hệ thống gửi thông báo nội bộ của mình mà không yêu cầu `orders` import các implementation đó.

## 7. Transaction và tính nhất quán khi mỗi module sở hữu dữ liệu

**Ranh giới module không tự động tạo ranh giới transaction vật lý.** Trong modular monolith, một lời gọi trực tiếp có thể thực thi trên cùng database transaction nếu được cấu hình như vậy. Nhưng nếu mục tiêu là để module có thể phát triển độc lập, thiết kế nên làm rõ phần nào cần nhất quán tức thì và phần nào chấp nhận **eventual consistency**.

| Tình huống | Kết quả khi dùng event sau commit | Cần thiết kế thêm |
| --- | --- | --- |
| Transaction của `orders` rollback | Listener `AFTER_COMMIT` không được gọi | Đảm bảo publish nằm trong transaction nguồn |
| `orders` commit nhưng `loyalty` xử lý chậm | Đơn đã thanh toán; điểm cập nhật muộn | Giao diện/luồng nghiệp vụ chấp nhận trễ, có chỉ báo xử lý nếu cần |
| `loyalty` ném lỗi | Transaction điểm rollback; đơn không rollback | Registry bền vững, cơ chế phát lại, giám sát lỗi |
| Cùng event được gửi hai lần | Listener có thể được gọi hai lần | Unique constraint, idempotency ở module nhận |
| Event đến sai thứ tự | Projection có thể thành trạng thái cũ | Version, sequence hoặc quy tắc bỏ qua event cũ |
| Thay đổi dữ liệu nguồn và event không cùng commit | Có nguy cơ sai lệch hoặc mất thông báo | Publication registry/outbox hoặc cơ chế transaction tương đương |

Với bài toán mà hai module phải đạt một bất biến nghiệp vụ tức thời, hãy cân nhắc **API đồng bộ do module sở hữu cung cấp**, hoặc thiết kế lại quy trình có trạng thái trung gian và xử lý thất bại rõ ràng. Event phù hợp khi bên nhận **phản ứng với sự thật đã xảy ra**, không phải khi module nguồn đang chờ kết quả để xác định sự thật đó có được phép xảy ra hay không.

Đặc biệt, một listener `@EventListener` thông thường có thể chạy **đồng bộ ngay tại `publishEvent(...)`**, trong cùng transaction của publisher; ngoại lệ của listener có thể khiến transaction nguồn rollback. `@TransactionalEventListener` mặc định chạy `AFTER_COMMIT`, nhưng bản thân annotation này **không tự bật async hoặc mở transaction ghi mới**. Hãy chọn annotation theo nhu cầu thực tế thay vì giả định mọi event đều xử lý bất đồng bộ.

## 8. Lưu vết và phục hồi event để bảo vệ dữ liệu module nhận

Tách trách nhiệm bằng event sẽ phát sinh một khoảng thời gian giữa việc **module nguồn commit** và **module nhận xử lý xong**. Nếu JVM dừng hoặc listener lỗi trong khoảng đó, cơ chế chỉ lưu event trong bộ nhớ có thể bỏ sót tác vụ.

**Event Publication Registry** của Spring Modulith giúp lưu bản ghi publication dành cho transactional listener và theo dõi việc xử lý. Với một implementation bền vững phù hợp (như JDBC/JPA được cấu hình với database và transaction tương thích), việc publish event có thể tạo các publication tương ứng listener trong transaction nguồn. Khi listener xử lý thành công, registry ghi nhận hoàn tất; bản ghi chưa hoàn tất có thể được tìm và **gửi lại theo chính sách vận hành/khôi phục** của ứng dụng.

Lưu ý các giới hạn:

- `@ApplicationModuleListener` **không tự động bảo đảm exactly-once**; một listener có thể thực hiện thành công tác động bên ngoài rồi gặp sự cố trước lúc ghi nhận completion.
- Registry cần **implementation lưu trữ thực**; chỉ thêm annotation listener không đồng nghĩa các bản ghi đã được lưu bền.
- Cơ chế resubmit/retry phải được kiểm soát theo phiên bản và cấu hình đang sử dụng; không mặc định mọi lỗi đều được tự động thử lại vô hạn.
- Nếu module nhận thực hiện side effect bên ngoài (email, thanh toán, HTTP API), sử dụng idempotency key ở hệ thống đích nếu có và lưu trạng thái dispatch phù hợp.
- Theo dõi số publication chưa hoàn tất, tuổi của publication, exception, số lần thử lại và thời gian xử lý để phát hiện sai lệch giữa các module.

Trong ứng dụng kết nối với dịch vụ ở JVM khác, application event nội bộ không phải message broker liên tiến trình. Khi cần truyền sự kiện ra Kafka/RabbitMQ hoặc dịch vụ ngoài, dùng cơ chế externalization hay messaging thích hợp và thiết kế riêng việc giao nhận bền vững.

## 9. Kiểm thử quyền sở hữu dữ liệu và hợp đồng liên module

Một bộ kiểm thử hợp lý xác nhận **cả cấu trúc phụ thuộc** lẫn **hành vi dữ liệu**:

### 9.1. Kiểm tra cấu trúc với Spring Modulith

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTest {

    @Test
    void modulesHaveValidDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` kiểm tra các quy tắc kiến trúc module mà Spring Modulith nhận diện, gồm các phụ thuộc không hợp lệ và vòng phụ thuộc. Ví dụ `loyalty.internal` import `orders.internal.OrderRepository` thường bị phát hiện là truy cập implementation không công khai. Tuy nhiên, kiểm tra này **không thể khẳng định mọi truy vấn native SQL đều đúng quyền sở hữu**.

### 9.2. Kiểm thử chức năng và transaction

Tạo các test tình huống:

1. Gọi `OrderPaymentService.recordPayment` cho một đơn hợp lệ, kiểm tra trạng thái nguồn chuyển thành `PAID` và event có `orderId` chính xác.
2. Cho transaction nguồn rollback, xác minh không có bản ghi cộng điểm sau commit.
3. Cho listener chạy thành công, xác minh sổ `reward_credit` và số dư điểm cùng cập nhật.
4. Giao cùng event hai lần hoặc chạy hai listener đồng thời, xác minh unique constraint bảo vệ **chỉ một lần cộng điểm**.
5. Cố tình làm listener lỗi giữa quá trình xử lý, xác minh transaction của `loyalty` rollback đầy đủ và publication còn có khả năng được phục hồi.
6. Truy vấn từ module khác qua `OrderLookup`, bảo đảm caller không phải phụ thuộc `OrderEntity`.

Với listener sau commit, test phải **thực sự commit transaction nguồn** trước khi chờ kết quả; test được bao bởi transaction tự rollback có thể không kích hoạt listener `AFTER_COMMIT`. Với listener async, dùng cơ chế chờ có timeout có giới hạn thay vì giả định xử lý xong ngay sau lời gọi publish.

### 9.3. Kiểm tra quy tắc ở mức code và database

Ngoài `verify()`, có thể tổ chức code review hoặc static checks để phát hiện:

- Một module import repository/entity trong package nội bộ của module khác.
- SQL hay JPQL từ module này đọc/ghi trực tiếp bảng của module khác.
- Mapper, DTO công khai mang theo entity persistence hoặc đối tượng mutable nội bộ.
- Migration làm thay đổi bảng thuộc module khác mà không có hợp đồng hoặc phối hợp rõ ràng.

## 10. Cải tiến hệ thống đang dùng bảng chung

Khi tiếp nhận monolith cũ, dữ liệu có thể đang được nhiều service truy cập tùy tiện. Không nhất thiết phải tách database hoặc sửa toàn bộ code trong một lần. Có thể tiến hành theo thứ tự:

1. **Lập bản đồ dữ liệu:** xác định module nghiệp vụ, bảng, thực thể, người ghi, người đọc và các transaction liên quan.
2. **Chọn một owner cho từng dữ liệu nguồn:** ví dụ chỉ `orders` được thay đổi `order_status`; ghi rõ các trạng thái nghiệp vụ thuộc quyền ai.
3. **Cố định các hành vi ghi:** đưa quy tắc chỉnh sửa về service của owner; module khác gọi API công khai thay cho việc truy cập repository trực tiếp.
4. **Tách nhu cầu đọc:** truy vấn cần chính xác hiện thời dùng API; bảng báo cáo hoặc read model có thể chuyển dần sang projection nhận event.
5. **Bổ sung event và độ tin cậy:** phát sự kiện sau thay đổi trạng thái, cấu hình registry bền vững khi cần, chống xử lý trùng và bổ sung giám sát.
6. **Khóa ranh giới bằng kiểm thử:** dùng `ApplicationModules.verify()` cùng các kiểm tra repository/query và tình huống rollback, retry.
7. **Tùy nhu cầu, tách schema hoặc quyền database:** thực hiện sau khi đã có ranh giới hợp đồng rõ ràng, giảm nguy cơ migration phá vỡ những truy cập chéo còn sót.

Chú ý **thay đổi quyền sở hữu dữ liệu là thay đổi hành vi và hợp đồng**, không chỉ là đổi package. Một module từng cập nhật trực tiếp bảng khác có thể đang dựa vào tính nguyên tử của cùng transaction; khi chuyển sang event sau commit, cần đánh giá lại quy tắc nhất quán và cách phục hồi khi listener thất bại.

## 11. Thực hành: phân định dữ liệu orders, payments, notifications

Thiết kế ba module theo yêu cầu:

- `orders` sở hữu `orders` và `order_items`; giữ trạng thái xử lý đơn.
- `payments` sở hữu `payment_transactions` và idempotency của xác nhận từ cổng thanh toán.
- `notifications` sở hữu `notification_deliveries` và trạng thái gửi email.

Yêu cầu thực hiện:

1. Vẽ sơ đồ package sao cho không module nào import repository hoặc entity nội bộ của module khác.
2. Xác định **ai là owner** của trạng thái thanh toán; tách rõ trạng thái giao dịch trong `payments` và trạng thái hiển thị liên quan trong `orders` nếu chúng tồn tại đồng thời.
3. Tạo event `PaymentConfirmed` trong API của `payments` với ID giao dịch, ID đơn và thời điểm xảy ra.
4. Giải thích `orders` nên phản ứng bằng event hay cần một API đồng bộ trong trường hợp nghiệp vụ có điều kiện giao hàng đặc biệt.
5. Thiết kế listener của `notifications` và bảng delivery có unique key để không gửi lại một thông báo chỉ vì event được retry.
6. Viết ít nhất ba test: transaction thanh toán rollback, listener lỗi và nhận lại cùng event hai lần.

**Câu hỏi tự kiểm tra:** Nếu `notifications` truy cập trực tiếp bảng `orders` để đọc email người mua, ranh giới nào đang bị vượt qua? Nếu báo cáo chấp nhận cập nhật chậm 5 giây, nên gọi API `orders` theo từng dòng hay tạo projection riêng? Nếu gửi email thành công nhưng ghi completion thất bại, module nhận cần điều kiện nào để tránh gửi trùng?

## 12. Những nguyên tắc cần giữ khi thiết kế

Một module **sở hữu dữ liệu** khi nó kiểm soát ý nghĩa, điều kiện thay đổi và hợp đồng truy cập dữ liệu đó; không phải chỉ vì các bảng được đặt chung thư mục hay cùng tên schema. Với Spring Modulith, có thể dùng public API/module interface cho truy vấn hoặc command đồng bộ, và **application events** cho phản ứng sau khi một sự kiện nghiệp vụ đã xảy ra. Module nhận có thể sở hữu bản sao dữ liệu đọc riêng, song phải phân biệt rõ với nguồn sự thật.

Khi dùng event sau commit, cần thiết kế trước cho **eventual consistency, xử lý trùng, lỗi bất đồng bộ và phục hồi publication**. Sự kết hợp giữa ranh giới package, repository nội bộ, Event Publication Registry và kiểm thử giao dịch mới giúp các module giữ được mức độc lập thực tế khi phát triển cùng một ứng dụng Spring Boot.

**Tài liệu tham khảo chính thức:**

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
