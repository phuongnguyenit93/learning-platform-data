# Sự kiện tích hợp trong Spring Modulith

## 1. Sự kiện tích hợp là gì?

**Sự kiện tích hợp (integration event)** là thông điệp mô tả một sự thật nghiệp vụ mà một thành phần công bố để **những hệ thống hoặc tiến trình khác** có thể biết và phản ứng. Ví dụ: sau khi một đơn hàng đã được xác nhận, ứng dụng bán hàng phát sự kiện `orders.confirmed` để hệ thống giao vận tạo yêu cầu giao hàng, hệ thống phân tích cập nhật số liệu hoặc một dịch vụ đối tác đồng bộ đơn.

Trong phạm vi `SPRING_MODULITH_APPLICATION_EVENTS`, trước tiên chúng ta tổ chức giao tiếp giữa **các application module** bằng application events nhằm giảm phụ thuộc trực tiếp, giữ ranh giới nghiệp vụ và hỗ trợ publisher, listener, xử lý sau commit, registry, retry, kiểm thử và quan sát. Khi nhu cầu mở rộng ra **bên ngoài ứng dụng Spring Boot**, một số event được chọn có thể trở thành integration events thông qua cơ chế **event externalization** của Spring Modulith.

Một ví dụ dễ hình dung:

~~~text
Khách hàng xác nhận đơn hàng
  └── module orders ghi nhận OrderConfirmed trong transaction
       ├── notifications listener nội bộ → tạo thông báo trong ứng dụng
       ├── reporting listener nội bộ     → cập nhật projection
       └── event externalization         → Kafka / AMQP / JMS / ...
                                            └── hệ thống giao vận bên ngoài
~~~

Ở đây, **một sự kiện nghiệp vụ có thể dẫn đến nhiều cách tiêu thụ**. Chỉ một số sự kiện cần công bố ra ngoài; không phải mọi domain event đều là integration event.

### 1.1. Sự khác nhau giữa các loại sự kiện

| Khái niệm | Phạm vi và mục đích | Ví dụ |
| --- | --- | --- |
| **Domain event** | Biểu đạt sự thật nghiệp vụ đã xảy ra trong mô hình/domain của module sở hữu | `OrderConfirmed` |
| **Spring application event** | Cơ chế chuyển sự kiện trong một Spring `ApplicationContext` qua `ApplicationEventPublisher` | Publisher phát một đối tượng `OrderConfirmed` |
| **Integration event** | Contract được công bố để tiến trình/hệ thống khác tiêu thụ, cần chú ý schema, version, định danh và độ bền | Message `orders.confirmed.v1` |
| **Command** | Yêu cầu một bên thực hiện hành vi, có thể được chấp nhận hoặc từ chối | `ReserveStock`, `ShipOrder` |
| **Change data capture (CDC) event** | Thể hiện thay đổi ở dữ liệu lưu trữ, thường được đọc từ log thay đổi DB | Thay đổi một dòng trong bảng `orders` |

Một đối tượng Java có thể đồng thời là domain event và payload externalized đơn giản, nhưng **hai loại contract phục vụ hai đối tượng sử dụng khác nhau**: domain event có thể phát triển cùng mô hình nội bộ; integration event phải tính đến người tiêu thụ không thể được nâng cấp đồng thời với hệ thống nguồn.

**Application event không tự động đi qua mạng.** `ApplicationEventPublisher.publishEvent(...)` mặc định phát sự kiện trong ứng dụng đang chạy. Để chuyển event ra Kafka hoặc một broker khác, cần thêm cơ chế externalization, dependency vận chuyển và cấu hình hạ tầng phù hợp.

### 1.2. Event mô tả điều đã xảy ra, không ra lệnh ngầm

So sánh:

- `OrderConfirmed`: “Đơn hàng đã được xác nhận”. Module nhận tự quyết định có cần làm gì.
- `SendOrderConfirmationEmail`: “Hãy gửi email xác nhận đơn”. Đây là một yêu cầu hành động; nếu `orders` chủ động quyết định cách gửi email của `notifications`, ranh giới dễ bị gắn chặt.

Trong một hệ thống dùng kiến trúc command/message rõ ràng, command cũng có chỗ đứng; nhưng cần phân biệt **sự thật đã được xác lập** và **yêu cầu một công việc còn chưa hoàn tất**. Đặt tên hoặc công bố sai ý nghĩa có thể gây lỗi khi consumer hiểu nhầm rằng nghiệp vụ nguồn đã hoàn thành.

## 2. Khi nào cần integration event?

Không phải mọi trao đổi giữa các module đều cần message broker. Hãy bắt đầu từ **ranh giới thực tế của nơi tiêu thụ** và mức nhất quán nghiệp vụ.

| Tình huống | Hướng giao tiếp phù hợp | Lý do |
| --- | --- | --- |
| `notifications` và `orders` thuộc cùng ứng dụng Spring Modulith | Spring application event + listener | Không cần broker để các module cùng tiến trình trao đổi |
| Module khác cần trả kết quả tức thì để transaction được phép commit | API công khai trực tiếp hoặc cơ chế phối hợp tương đương | Quyết định phải có trước khi hoàn tất nghiệp vụ |
| Hệ thống giao vận là ứng dụng độc lập, vận hành và triển khai riêng | Integration event qua broker hoặc kênh tích hợp thích hợp | Bên tiêu thụ không chia sẻ `ApplicationContext` |
| Đối tác cần biết các đơn đã thanh toán thành công | Integration event hoặc webhook có contract ổn định | Cần thông điệp có thể nhận và diễn giải ở bên ngoài |
| Dữ liệu báo cáo nội bộ chấp nhận trễ sau commit | Application event hậu commit | Eventual consistency trong cùng ứng dụng thường đã đủ |
| Trạng thái giao dịch bắt buộc nhất quán ngay trong cùng transaction | Thiết kế transaction/điều phối rõ ràng | Không thể giả định broker bảo đảm commit nguyên tử với mọi hệ thống |

Integration event giúp **giảm phụ thuộc theo thời gian**: producer không cần đợi consumer hoàn thành xử lý để kết thúc nghiệp vụ nguồn. Tuy nhiên, nó làm xuất hiện những yêu cầu mới như lưu bền thông điệp, hợp đồng tương thích, xử lý lặp, thông điệp đến trễ và quan sát đa hệ thống.

~~~mermaid
flowchart LR
    UI[API / UI] --> Orders[orders module]
    Orders --> DB[(DB nghiệp vụ)]
    Orders --> Publisher[ApplicationEventPublisher]
    Publisher --> Local[Internal listeners]
    Publisher --> Ext[Event externalization]
    Ext --> Broker[(Message broker)]
    Broker --> Shipping[Shipping service]
    Broker --> Analytics[Analytics service]
~~~

Sơ đồ cho thấy **ranh giới triển khai**: module `orders`, listener nội bộ và externalizer cùng thuộc modular monolith; `Shipping service` và `Analytics service` là consumer ngoài tiến trình.

## 3. Ai sở hữu sự kiện và dữ liệu?

Một integration event có giá trị khi quyền phát sự kiện được gắn với **module thực sự sở hữu sự thật nghiệp vụ**.

Giả sử:

- `orders` sở hữu đơn hàng và trạng thái xác nhận.
- `payments` sở hữu giao dịch thanh toán.
- `inventory` sở hữu tồn kho và reservation.
- `shipping` nằm ở hệ thống bên ngoài và sở hữu vòng đời vận chuyển.

Chỉ `orders` được quyết định khi nào phát `OrderConfirmed`. Module `payments` có thể phát `PaymentCaptured`; việc nhận `PaymentCaptured` **không tự động có nghĩa** đơn hàng đã được xác nhận nếu `orders` còn các điều kiện khác. Hệ thống giao vận không nên dựa vào việc tự kiểm tra một bảng nội bộ của `orders` để đoán trạng thái.

### 3.1. Ranh giới sở hữu phải được thể hiện trong contract

| Thành phần | Sở hữu và hành vi | Dữ liệu công bố cho ngoài ứng dụng |
| --- | --- | --- |
| `orders` | Xác nhận/hủy đơn, áp dụng quy tắc đơn hàng | `orderId`, `occurredAt`, trạng thái hoặc dữ liệu đã được chọn |
| `payments` | Ghi nhận thanh toán thành công, thất bại hoặc hoàn tiền | `paymentId`, `orderId`, loại kết quả |
| `shipping` | Quy trình đóng gói, giao hàng và tracking | Phát event riêng khi trạng thái giao vận thay đổi |
| `analytics` | Đọc event để tạo projection | Không được tự sửa dữ liệu nguồn của `orders` |

Nếu consumer cần biết thêm thông tin, producer cần chọn giữa hai cách: bổ sung **snapshot tối thiểu** vào payload hoặc công bố một **API truy vấn ổn định**. Không nên chuyển trực tiếp entity JPA, repository hoặc đối tượng chứa quan hệ lazy qua broker.

### 3.2. Domain event và integration DTO: dùng chung hay tách riêng?

Hai chiến lược phổ biến:

1. **Dùng cùng một event:** đơn giản khi payload domain đã là dữ liệu bất biến, ổn định, không chứa chi tiết nội bộ và consumer ngoài ứng dụng chấp nhận schema đó.
2. **Tách integration DTO khỏi domain event:** hữu ích khi schema bên ngoài cần version, tên trường ổn định, giới hạn dữ liệu hoặc hỗ trợ nhiều consumer phát triển độc lập.

Ví dụ kiểu domain event nội bộ:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Ví dụ DTO ở lớp tích hợp (mang tính minh họa, không khẳng định framework tự tạo ra nó):

~~~java
package com.example.shop.orders.integration;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmedV1(
    UUID eventId,
    String eventType,
    int schemaVersion,
    UUID orderId,
    Instant occurredAt
) {
    public static OrderConfirmedV1 from(OrderConfirmed source) {
        return new OrderConfirmedV1(
            source.eventId(),
            "orders.confirmed",
            1,
            source.orderId(),
            source.occurredAt()
        );
    }
}
~~~

Đoạn `from(...)` giả định `OrderConfirmed` đã được import và một adapter trong module `orders` được phép sử dụng cả hai kiểu. DTO thứ hai không nên khiến consumer phải biết cách ánh xạ entity hoặc phụ thuộc vào package nội bộ. Spring Modulith hỗ trợ **mapping** trước bước chuyển ra broker; có thể dùng khả năng đó để tách biểu diễn thông điệp khỏi đối tượng event ban đầu khi cần.

## 4. Thiết kế integration event contract

Khi một event rời khỏi tiến trình, contract của nó trở thành ranh giới giao tiếp giữa các hệ thống có thể triển khai độc lập. Cần xác định ít nhất **ý nghĩa, schema, version, định danh, thời điểm, routing và chính sách dữ liệu**.

### 4.1. Một payload minh họa

~~~json
{
  "eventId": "9258cc53-c7c0-4d16-9632-4b090fae69f2",
  "eventType": "orders.confirmed",
  "schemaVersion": 1,
  "aggregateId": "e7a86f12-b8f0-4394-a74c-b99b421830ee",
  "occurredAt": "2026-11-25T08:00:00Z",
  "data": {
    "orderId": "e7a86f12-b8f0-4394-a74c-b99b421830ee",
    "currency": "VND",
    "amountMinor": 420000
  }
}
~~~

Đây là **schema do đội phát triển tự thiết kế**, không phải biểu diễn JSON mặc định bắt buộc của Spring Modulith. Nếu chọn externalize trực tiếp một `record`, payload mặc định phụ thuộc cấu hình serializer của transport. Khi tạo envelope như ví dụ, cần viết bước mapping/serialization tương ứng.

| Trường | Ý nghĩa và lưu ý |
| --- | --- |
| `eventId` | Định danh duy nhất cho sự kiện; hỗ trợ phát hiện xử lý trùng |
| `eventType` | Loại sự thật nghiệp vụ; nên đặt tên độc lập với Java class |
| `schemaVersion` | Phiên bản contract phục vụ kiểm soát tương thích |
| `aggregateId` | Định danh thực thể/aggregate nguồn để dùng cho routing hoặc ordering |
| `occurredAt` | Thời điểm sự thật nghiệp vụ xảy ra, thường thống nhất UTC |
| `data` | Dữ liệu thật sự cần cho consumer theo contract đã thỏa thuận |

Không nhất thiết dùng đủ tất cả trường; lựa chọn phụ thuộc yêu cầu. Ví dụ `amountMinor` biểu thị số tiền ở đơn vị nhỏ nhất đã quy ước, tránh nhập nhằng số thực và đơn vị tiền tệ. Nếu dùng nhiều loại tiền, schema cần nói rõ đơn vị và cách làm tròn.

### 4.2. Sự kiện phải là sự thật đã xác lập

Nếu `orders` phát `OrderConfirmed` trong một transaction nhưng transaction đó rollback, không nên để hệ thống giao vận nhận được thông điệp nói rằng đơn đã được xác nhận. Vì vậy, khi phát các sự kiện quan trọng, cần dùng **transactional event handling** và cơ chế lưu publication/dispatch thích hợp để kết nối trạng thái nghiệp vụ với việc công bố.

Trong Spring Modulith, externalization gốc dựa trên listener theo transaction, phối hợp với event publication registry. Việc phát từ một service có `@Transactional` tạo nền tảng để publication được ghi cùng transaction nghiệp vụ khi đã cấu hình registry bền vững. Các thành phần cụ thể và mức bảo đảm phụ thuộc version, backend và transport.

### 4.3. Tương thích khi nâng phiên bản

Với event được tiêu thụ bởi hệ thống ngoài, **không thể luôn yêu cầu tất cả consumer cập nhật cùng thời điểm**. Khi thay đổi schema:

- Thêm trường mới dạng tùy chọn và có giá trị mặc định rõ ràng thường dễ tương thích hơn xóa/đổi tên trường cũ.
- Đổi ý nghĩa của `OrderConfirmed` thành “đã nhận thanh toán nhưng còn chờ giữ hàng” là thay đổi **ngữ nghĩa** và có thể buộc tạo loại event mới.
- Cẩn trọng khi đổi kiểu dữ liệu, định dạng ngày, đơn vị tiền, tên enum hoặc cấu trúc JSON lồng nhau.
- Với thay đổi không tương thích, dùng schema version hoặc event type mới và kế hoạch chuyển tiếp.
- Nếu có publication chưa xử lý hoặc thông điệp tồn đọng trên broker, consumer mới vẫn có thể gặp schema cũ.

Ví dụ, `orders.confirmed.v1` và `orders.confirmed.v2` có thể được chạy song song trong giai đoạn chuyển đổi khi có kế hoạch tương thích rõ ràng. Việc gắn số phiên bản vào tên topic hay vào payload là lựa chọn kiến trúc; cần thống nhất cách quản lý với consumer.

### 4.4. Bảo vệ dữ liệu và giới hạn phạm vi công bố

Integration event có thể được sao chép, lưu trữ lâu và chuyển cho nhiều consumer. Không nên mặc định đưa email, địa chỉ, số điện thoại, token, dữ liệu thanh toán nhạy cảm hoặc toàn bộ đơn hàng ra broker. Chỉ công bố trường thực sự cần; cân nhắc phân quyền đọc topic, mã hóa đường truyền, chính sách lưu trữ và xóa dữ liệu.

Trường `eventId` và `traceId` có thể phục vụ quan sát mà không cần ghi thông tin cá nhân vào log.

## 5. Event externalization trong Spring Modulith

Spring Modulith cung cấp khả năng **chọn application events để externalize** sang các transport được hỗ trợ. Cách dùng gốc gồm ba bước:

1. Thêm dependency Spring Modulith tương ứng với broker.
2. Chọn loại event được công bố ra ngoài, thường bằng `@Externalized`.
3. Xác định địa chỉ đích/routing và bảo đảm cấu hình transport cùng registry phù hợp.

### 5.1. Sự khác nhau giữa publisher nội bộ và externalizer

Producer nghiệp vụ có thể tiếp tục sử dụng `ApplicationEventPublisher`. Externalizer là thành phần riêng quan sát những event được chọn và gửi chúng ra hạ tầng ngoài, nên producer không phải gọi trực tiếp `KafkaTemplate` hay `RabbitTemplate` cho mỗi consumer.

~~~mermaid
sequenceDiagram
    participant API as Client API
    participant Orders as orders service
    participant DB as Business DB
    participant Events as Spring event publisher
    participant Registry as Publication registry
    participant Externalizer as Event externalizer
    participant Broker as Kafka / AMQP
    participant Consumer as External consumer

    API->>Orders: confirm(orderId)
    Orders->>DB: Cập nhật đơn (transaction)
    Orders->>Events: publishEvent(OrderConfirmed)
    Events->>Registry: Ghi publication (khi cấu hình)
    Orders->>DB: Commit
    DB-->>Orders: Commit thành công
    Events-->>Externalizer: Xử lý event sau commit
    Externalizer->>Broker: Gửi integration message
    Broker-->>Externalizer: Kết quả gửi theo transport
    Externalizer->>Registry: Đánh dấu hoàn tất khi thành công
    Broker-->>Consumer: Giao message
    Consumer->>Consumer: Kiểm tra duplicate và xử lý
~~~

Sơ đồ chỉ ra đường đi **logic** của cơ chế externalization dựa trên listener và registry. Chi tiết xác nhận từ broker, thứ tự callback, cách resubmit và thời điểm lưu transaction phụ thuộc cấu hình thực tế. **Publication hoàn tất ở phía producer không chứng minh consumer đã xử lý thành công.**

### 5.2. Ví dụ với Kafka

Giả sử dự án sử dụng phiên bản Spring Modulith hỗ trợ annotation-based externalization. Trong Gradle, cấu hình các dependency minh họa sau, để BOM/Dependency Management tương thích với Spring Boot quyết định phiên bản:

~~~kotlin
dependencies {
    implementation("org.springframework.modulith:spring-modulith-events-kafka")
    implementation("org.springframework.modulith:spring-modulith-starter-jdbc")
}
~~~

- `spring-modulith-events-kafka` cung cấp tích hợp externalization với Kafka; ứng dụng phải có cấu hình Kafka hợp lệ.
- `spring-modulith-starter-jdbc` là một lựa chọn registry dùng JDBC và serialization thích hợp; tùy dự án cũng có thể chọn JPA, MongoDB hoặc backend khác được hỗ trợ.
- Cần quản lý BOM/version tương thích, datasource, transaction manager và schema migration. Đoạn cấu hình không bao gồm toàn bộ hạ tầng broker/DB hoặc production settings.

Event contract được chọn để externalize:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;
import org.springframework.modulith.events.Externalized;

@Externalized("orders.confirmed.v1::#{#this.orderId()}")
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Với Kafka, trong định dạng `target::key`, `orders.confirmed.v1` là đích logic thường được dùng làm **topic** và expression `#{#this.orderId()}` tính **message key** từ event. Việc chọn key theo `orderId` hỗ trợ phân vùng các event cùng đơn vào cùng một Kafka partition khi producer dùng partitioner nhất quán; **nó không tự bảo đảm mọi hệ thống tiêu thụ theo thứ tự toàn cục**.

Đoạn Java ứng dụng phát sự kiện:

~~~java
package com.example.shop.orders.internal;

import com.example.shop.orders.events.OrderConfirmed;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderManagement {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderManagement(OrderRepository orders,
                    ApplicationEventPublisher events,
                    Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findById(orderId).orElseThrow();
        order.confirm();
        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(), orderId, clock.instant()
        ));
    }
}
~~~

`OrderRepository`, aggregate `Order` và cấu hình `Clock` là các thành phần giả định của dự án ví dụ. Với Spring Data/JPA, việc lưu aggregate do cách quản lý persistence context quyết định; mục đích của đoạn mã là trình bày **điểm phát event trong luồng transaction**, không xây dựng một ứng dụng hoàn chỉnh có thể chạy riêng.

Phần đáng chú ý: service này chỉ biết `ApplicationEventPublisher` và contract nghiệp vụ, **không biết hostname Kafka, topic consumer hay địa chỉ dịch vụ giao vận**. Dependency và annotation của externalization được đưa vào phần cấu hình/contract phù hợp.

### 5.3. Ba bước mà externalizer thực hiện

| Bước | Câu hỏi | Cơ chế thường dùng |
| --- | --- | --- |
| **Selection** | Event nào được phép đi ra ngoài? | `@Externalized` hoặc cấu hình lựa chọn theo loại |
| **Mapping** | Gửi chính đối tượng event hay DTO ngoài ứng dụng? | Mapping để tạo payload, header và schema thích hợp |
| **Routing** | Gửi tới đâu và sử dụng key nào? | Routing target và routing key, phụ thuộc broker |

Mặc định, những loại event có annotation phù hợp trong vùng package được cấu hình mới là ứng viên externalization. Có thể tùy biến selection, mapping và routing bằng API cấu hình theo phiên bản đang dùng. Khi mapping thành DTO bên ngoài, **routing mặc định vẫn có thể dựa trên event gốc**; nếu muốn routing dựa trên payload sau mapping, phải cấu hình tương ứng theo API phiên bản đó.

### 5.4. Broker và adapter không đồng nhất

| Hạ tầng | Artifact Spring Modulith | Cách định tuyến cần chú ý |
| --- | --- | --- |
| **Kafka** | `spring-modulith-events-kafka` | Target là topic, key có thể là Kafka message key |
| **AMQP/RabbitMQ** | `spring-modulith-events-amqp` | Routing key kết hợp với exchange/binding cấu hình |
| **JMS** | `spring-modulith-events-jms` | Target theo destination, không hỗ trợ routing key theo kiểu Kafka |
| **Spring Messaging** | `spring-modulith-events-messaging` | Target liên hệ với `MessageChannel`, routing được chuyển theo metadata phù hợp |

Những adapter khả dụng có thể thay đổi theo phiên bản Spring Modulith. Không nên suy diễn `target` là cùng một loại địa chỉ ở mọi broker. Ví dụ: Kafka topic khác RabbitMQ exchange/routing key; việc topic/queue có được tạo tự động hay không là trách nhiệm cấu hình broker tương ứng.

## 6. Cơ sở dữ liệu, transaction và event publication registry

### 6.1. Bài toán dual write

Giả sử nghiệp vụ phải vừa ghi đơn hàng vào database vừa gửi Kafka message:

~~~text
BEGIN TRANSACTION
UPDATE orders SET status = 'CONFIRMED'
COMMIT
send Kafka "orders.confirmed"
~~~

Nếu ứng dụng chết **sau khi database commit nhưng trước khi gửi Kafka**, đơn hàng đã xác nhận mà hệ thống giao vận không nhận sự kiện. Nếu đảo ngược thứ tự, broker có thể nhận event nhưng transaction database sau đó rollback.

Đây là bài toán **dual write** giữa hai hệ thống có transaction độc lập. Chỉ đặt `@Transactional` quanh method gọi database và broker **không tự tạo atomic transaction chung**. Cần lựa chọn cơ chế quản lý publication phù hợp.

### 6.2. Registry trong Spring Modulith xử lý được phần nào?

Event Publication Registry của Spring Modulith hỗ trợ ghi **publication dành cho transactional event listeners** cùng transaction nghiệp vụ khi backend phù hợp được cấu hình. Mỗi listener/đích publication có trạng thái xử lý; khi listener thực hiện thành công, registry có thể ghi nhận hoàn tất. Khi thất bại, publication chưa hoàn tất có thể được kiểm tra và resubmit theo cơ chế hiện hành.

Đối với externalization gốc dựa trên listener, việc gửi ra broker được Spring Modulith tổ chức như một transactional listener; registry giúp theo dõi và phục hồi những lần gửi thất bại.

~~~mermaid
flowchart TD
    A[Transaction nghiệp vụ bắt đầu] --> B[Thay đổi dữ liệu]
    B --> C[Phát application event]
    C --> D[Registry lưu publication]
    D --> E{Transaction commit?}
    E -->|Không| F[Rollback: không công bố kết quả nghiệp vụ]
    E -->|Có| G[Externalizer gửi broker]
    G --> H{Gửi thành công?}
    H -->|Có| I[Đánh dấu publication hoàn tất]
    H -->|Lỗi| J[Giữ trạng thái cần xử lý lại]
    J --> K[Recovery / retry phù hợp]
    K --> G
~~~

Sơ đồ thể hiện nguyên tắc. Việc lưu registry được đưa vào transaction nguồn **chỉ khi đã cấu hình hạ tầng transaction và persistence phù hợp**. Trạng thái chi tiết có thể khác giữa các phiên bản (ví dụ Spring Modulith 2.x cung cấp lifecycle publication tường minh hơn).

### 6.3. Registry không đồng nghĩa với một outbox engine hoàn chỉnh

Một **transactional outbox** đúng nghĩa lưu ý định gửi thông điệp trong cùng transaction database, rồi có một bộ xử lý riêng đọc outbox và chuyển đến broker với cơ chế claim, retry và kiểm soát đồng thời. Event publication registry giải quyết việc theo dõi/khôi phục publication cho các listener, nhưng không mặc nhiên cung cấp tất cả khả năng điều phối và thứ tự của một outbox processor chuyên dụng.

Spring Modulith **2.1** bổ sung lựa chọn externalization qua các giải pháp outbox như Namastack Outbox hoặc JobRunr, bên cạnh cơ chế externalization bằng listener. Khi dự án yêu cầu nhiều replica, kiểm soát thứ tự, retry tự động và dispatch ổn định, cần đánh giá phiên bản, adapter và chế độ externalization thực tế trước khi chọn kiến trúc.

| Tiêu chí | Externalization dựa trên listener + registry | Outbox chuyên dụng |
| --- | --- | --- |
| Ghi nhận publication liên quan transaction nguồn | Có, khi registry được cấu hình đúng | Có, theo thiết kế transactional outbox |
| Phục hồi publication thất bại | Có API/cơ chế resubmit theo cấu hình | Thường có dispatcher và retry policy riêng |
| Điều phối nhiều instance | Phải đánh giá và thiết kế thêm nếu cần | Thường là trọng tâm của outbox engine |
| Ordering giữa nhiều event | Không mặc định được bảo đảm toàn cục | Có thể được kiểm soát theo khóa/stream nếu engine hỗ trợ |
| Ghi nhận consumer bên ngoài đã xử lý | Không | Không; consumer vẫn cần ACK/offset và idempotency riêng |

Không nên ghi `spring.modulith.events.externalization.mode: outbox` khi chưa có dependency outbox và phiên bản tương thích; cấu hình chỉ có ý nghĩa khi dự án đã cung cấp implementation tương ứng.

### 6.4. Khi nào một publication được xem là hoàn tất?

Với externalizer, “đã gửi” thường chỉ tương ứng với việc **transport/adapter hoàn thành theo semantics mà nó cung cấp**, ví dụ broker phản hồi kết quả publish. Điều đó **không có nghĩa** consumer đã xử lý và commit dữ liệu của họ.

Ta cần phân biệt ba thời điểm:

1. **Business committed:** trạng thái nghiệp vụ nguồn đã được database xác nhận.
2. **Broker accepted:** transport công bố message thành công theo bảo đảm cấu hình.
3. **Consumer processed:** bên nhận xử lý và ghi nhận tiến độ riêng.

Mỗi thời điểm có thể thất bại độc lập. Sử dụng trace/event ID xuyên hệ thống giúp quan sát được luồng, nhưng không biến ba transaction thành một transaction chung.

## 7. Độ tin cậy: retry, duplicate, ordering và idempotency

### 7.1. Cùng một event có thể được chuyển nhiều lần

Giả sử externalizer gửi message tới broker thành công rồi ứng dụng crash trước khi registry ghi hoàn tất. Khi publication được phát lại, broker có thể nhận **hai bản sao** của cùng một integration event. Điều đó có thể xảy ra dù producer đã áp dụng retry hợp lý.

Consumer không được giả định `exactly-once` end-to-end chỉ vì broker có cơ chế transaction hoặc deduplication. Bảo đảm thực tế còn phụ thuộc producer, broker, consumer, database đích và tác dụng phụ ra hệ thống ngoài.

### 7.2. Thiết kế idempotency theo eventId

Một consumer có thể lưu `processed_event_id` với unique constraint trong database mà nó sở hữu. Khi nhận lại cùng `eventId`, consumer nhận biết event đã được áp dụng.

~~~sql
CREATE TABLE processed_integration_events (
    event_id VARCHAR(36) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Pseudocode minh họa:

~~~text
consume(message):
    validate schema / event type / version
    begin transaction
      insert processed_event_id (unique)
      nếu ID đã tồn tại:
          bỏ qua cập nhật nghiệp vụ trùng
      nếu là ID mới:
          áp dụng thay đổi local theo contract
    commit
    xác nhận message/offset theo cơ chế consumer
~~~

Phần kiểm tra ID và thay đổi dữ liệu phải được phối hợp **atomic trong transaction của consumer** khi có thể. Nếu consumer gọi một API ngoài rồi mới đánh dấu đã xử lý, lần retry vẫn có thể gọi lại; khi đó cần idempotency key ở provider hoặc một workflow bù trừ/đối soát.

### 7.3. Ordering theo aggregate

Ví dụ với một đơn hàng, có thể phát `OrderConfirmed` rồi `OrderCancelled`. Khi producer có nhiều instance, retry hoặc nhiều partition, bên nhận có thể thấy thứ tự khác dự kiến nếu không có chiến lược phù hợp.

- Với Kafka, chọn key thống nhất theo `orderId` giúp nhóm message cùng đơn vào một partition trong điều kiện producer/partitioner nhất quán.
- Việc giữ thứ tự **trong một partition** không tương đương bảo đảm thứ tự giữa các topic, partition hoặc lần khôi phục bất thường.
- Bổ sung `aggregateVersion` hoặc sequence nếu consumer phải phát hiện event cũ/đến muộn.
- Thiết kế state machine ở consumer để từ chối chuyển trạng thái không hợp lệ thay vì áp dụng mù quáng theo thứ tự nhận.
- Nếu ordering có yêu cầu pháp lý/nghiệp vụ chặt, đánh giá phương án outbox và dispatch theo khóa phù hợp.

Ví dụ schema có thể bổ sung:

~~~json
{
  "eventId": "ccb7cb1d-78f4-4660-bb1e-a58d82080677",
  "eventType": "orders.cancelled",
  "aggregateId": "e7a86f12-b8f0-4394-a74c-b99b421830ee",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-25T08:35:00Z"
}
~~~

`aggregateVersion` cần được tạo từ mô hình nghiệp vụ có định nghĩa thứ tự đáng tin cậy; không tự suy ra từ timestamp khi nhiều tác vụ có thể xảy ra đồng thời.

### 7.4. Phân loại lỗi và chính sách xử lý

| Tình huống | Hành vi đề xuất |
| --- | --- |
| Broker tạm thời không sẵn sàng | Giữ publication/outbox chưa hoàn tất; retry có backoff và giới hạn |
| Producer restart sau commit | Khôi phục publication hợp lệ theo cơ chế registry/outbox đã chọn |
| Message trùng đến consumer | Deduplicate theo ID và áp dụng nghiệp vụ idempotent |
| Consumer nhận schema không tương thích | Tách hàng lỗi/DLQ hoặc lưu để điều tra; tránh retry vô hạn |
| Event đến muộn hoặc ngoài thứ tự | Dùng version/state machine và chính sách xử lý event cũ |
| Dịch vụ ngoài xử lý thành công nhưng xác nhận bị mất | Thiết kế idempotency key/đối soát, không tự tin coi request là chưa xảy ra |
| Một consumer lỗi còn consumer khác thành công | Mỗi bên theo dõi trạng thái và recovery độc lập |

**Retry nên có giới hạn, backoff và quan sát**, vì lặp liên tục một sự kiện sai schema hoặc dữ liệu không hợp lệ có thể gây nghẽn hệ thống. Dead-letter queue là công cụ hữu ích ở tầng broker/consumer khi có chính sách vận hành rõ, không phải tính năng tự động mặc định của `ApplicationEventPublisher`.

## 8. Ví dụ: hành trình sự kiện xác nhận đơn hàng

### 8.1. Thiết kế luồng hoàn chỉnh

Giả sử một ứng dụng Spring Modulith có `orders`, `notifications` và `reporting`; hệ thống vận chuyển `shipping-service` chạy độc lập.

**Bước 1 — Xác định sự thật nghiệp vụ.** `orders` chỉ phát `OrderConfirmed` sau khi các điều kiện xác nhận đơn đã hợp lệ.

**Bước 2 — Thiết kế event nội bộ.** `OrderConfirmed(eventId, orderId, occurredAt)` bất biến, nằm trong API/named interface phù hợp của module `orders`.

**Bước 3 — Chọn consumer nội bộ.** `notifications` xử lý email bằng listener hậu commit; `reporting` cập nhật projection của chính module.

**Bước 4 — Chọn integration event.** `shipping-service` cần được báo khi đơn đã sẵn sàng để lập yêu cầu giao. Đánh giá liệu event `OrderConfirmed` có đủ chính xác về ngữ nghĩa; nếu việc vận chuyển chỉ bắt đầu sau khi đóng gói, nên định nghĩa một sự kiện khác như `OrderReadyForShipment`.

**Bước 5 — Cấu hình externalization.** Chọn event có ý nghĩa, đặt topic/target, routing key và serializer; dùng registry bền vững hoặc outbox phù hợp yêu cầu.

**Bước 6 — Triển khai consumer.** Consumer chỉ tin vào contract công khai, kiểm tra version và duplicate, áp dụng state machine riêng, xác nhận tiến độ khi đã commit thay đổi cần thiết.

**Bước 7 — Kiểm thử lỗi.** Cho broker tạm dừng, restart producer, gửi lại event cũ và gây lỗi ở consumer để kiểm chứng khả năng phục hồi.

~~~mermaid
flowchart TB
    subgraph App[Spring Modulith - shop application]
      Orders[orders] --> Pub[ApplicationEventPublisher]
      Pub --> Notify[notifications listener]
      Pub --> Report[reporting listener]
      Pub --> Ext[Externalization adapter]
      Ext -. publication .-> Reg[(Registry / outbox)]
    end
    Ext --> Broker[(orders.confirmed.v1 topic)]
    Broker --> Ship[shipping-service]
    Ship --> ShipDB[(Shipping DB)]
~~~

### 8.2. Không đánh đồng các kết quả

Sau khi API xác nhận đơn trả HTTP `200` hoặc `202` theo contract riêng, ta chỉ có thể kết luận những điều **API đã hứa bảo đảm**. Nếu nó cam kết transaction xác nhận đã commit, không thể suy từ đó rằng email đã gửi thành công, broker đã nhận message hay hệ thống giao vận đã tạo shipment.

Một dashboard có thể hiển thị những trạng thái khác nhau:

| Hệ thống | Câu hỏi cần trả lời | Nguồn dữ liệu |
| --- | --- | --- |
| `orders` | Đơn đã xác nhận chưa? | Database nghiệp vụ của `orders` |
| Externalizer | Event đã gửi đến broker thành công chưa? | Registry/outbox và telemetry transport |
| Broker | Message đang tồn đọng bao nhiêu? | Metadata topic/queue và metric broker |
| `shipping-service` | Yêu cầu giao hàng đã tạo chưa? | Database và consumer progress của shipping |
| `notifications` | Email đã gửi chưa, có cần retry không? | Dữ liệu và trạng thái xử lý của notifications |

Tách các trạng thái theo quyền sở hữu giúp hỗ trợ vận hành và phân tích sự cố khi một phần hệ thống chậm hoặc lỗi.

## 9. Kiểm thử integration events đúng mức

### 9.1. Kiểm thử publisher nghiệp vụ

Khi gọi `OrderManagement.confirm(orderId)` với dữ liệu hợp lệ, cần xác minh:

- Đơn chuyển trạng thái hợp lệ.
- `OrderConfirmed` được phát đúng thời điểm trong luồng xử lý.
- `eventId` khác rỗng, `orderId` và `occurredAt` đúng contract.
- Khi xác nhận thất bại hoặc transaction rollback, không tạo hiệu ứng externalization hậu commit của một kết quả không tồn tại.

Spring Modulith có `@ApplicationModuleTest` và `PublishedEvents` để kiểm tra việc phát event trong phạm vi module. Công cụ đó giúp xác nhận **publisher có phát event**, nhưng chưa thay thế kiểm thử thực tế với broker và registry.

### 9.2. Kiểm thử externalization

Với integration test dùng Kafka/RabbitMQ thực hoặc môi trường test tương đương, kiểm tra:

1. Event đủ điều kiện được chọn để externalize.
2. Event không được chọn **không bị công bố ra ngoài**.
3. Topic/target và key được tính đúng cho từng aggregate.
4. Payload có schema và version như contract tiêu thụ kỳ vọng.
5. Khi source transaction rollback, không có message hợp lệ được gửi.
6. Khi broker tạm ngừng, publication được ghi nhận/khôi phục đúng theo cấu hình.
7. Sau khi chuyển lại thành công, publication không bị đánh dấu lỗi dai dẳng.

Đối với `@Externalized`, một unit test trên Java annotation chỉ kiểm tra sự hiện diện annotation; **integration test với cấu hình thật** mới chứng minh wiring, transaction, serialization và transport phù hợp.

### 9.3. Kiểm thử consumer

Tối thiểu nên có các ca:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Nhận event hợp lệ lần đầu | Tạo hoặc cập nhật dữ liệu local chính xác |
| Nhận lại cùng `eventId` | Không nhân đôi tác dụng phụ |
| Nhận event có `schemaVersion` không hỗ trợ | Theo chính sách phân loại lỗi, không xử lý sai dữ liệu |
| Nhận `OrderCancelled` trước `OrderConfirmed` | Không chuyển trạng thái sai, xử lý theo state machine |
| DB consumer commit lỗi | Broker/consumer có cơ chế nhận lại thay vì đánh dấu xử lý hoàn tất sai |
| Gửi API ngoài thành công nhưng mất response | Không nhân đôi hành động nếu bên ngoài hỗ trợ idempotency |

Đối với hệ thống có yêu cầu ordering hoặc throughput lớn, nên kiểm thử nhiều partition, nhiều consumer instance và tốc độ resubmit trong thời điểm hệ thống khôi phục.

### 9.4. Kiểm tra kiến trúc module

Các module nội bộ vẫn cần tuân thủ ranh giới Spring Modulith, ngay cả khi có event externalization:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {
    @Test
    void verifiesBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này phát hiện phụ thuộc mã nguồn sai theo mô hình module, **không bảo đảm** việc giao message hoặc xử lý idempotency của consumer ngoài tiến trình.

## 10. Quan sát và vận hành luồng integration event

Đường đi của integration event thường trải qua nhiều ranh giới mạng và database, vì vậy cần quan sát riêng từng chặng. Nên thiết kế trước các câu hỏi vận hành:

- Một event được phát từ nghiệp vụ lúc nào, đã commit chưa?
- Publication nào chưa hoàn tất, có bao nhiêu lần retry?
- Lần cuối externalizer gặp lỗi gì và với target nào?
- Broker đang có backlog bao nhiêu; có producer timeout hoặc publish failure không?
- Consumer xử lý event trong bao lâu, backlog/lag tăng vì lý do gì?
- Event nào bị bỏ qua vì duplicate hoặc schema không tương thích?

### 10.1. Gợi ý trường log/trace

~~~json
{
  "eventId": "9258cc53-c7c0-4d16-9632-4b090fae69f2",
  "eventType": "orders.confirmed",
  "aggregateId": "e7a86f12-b8f0-4394-a74c-b99b421830ee",
  "module": "orders",
  "externalTarget": "orders.confirmed.v1",
  "publicationStatus": "pending",
  "attempt": 2
}
~~~

Các tên trường/log trên là đề xuất quan sát, **không phải schema bắt buộc hay tên trạng thái cố định** của Spring Modulith. Không log toàn bộ payload nếu có thông tin cá nhân hoặc dữ liệu bí mật. Có thể bổ sung correlation ID hoặc distributed trace ID để nối request nguồn với event và consumer.

### 10.2. Một số metric hữu ích

| Metric | Diễn giải |
| --- | --- |
| `event_publications_pending` | Số publication còn chờ xử lý |
| `event_publication_failures_total` | Số lần externalize thất bại |
| `event_externalization_latency` | Thời gian từ commit tới broker chấp nhận, khi có đo lường |
| `consumer_lag` | Độ trễ consumer theo semantics broker |
| `consumer_duplicate_total` | Số message trùng được consumer phát hiện |
| `consumer_processing_latency` | Thời gian xử lý một message ở consumer |

Đây là **tên metric gợi ý** để xây dashboard, không khẳng định Spring Modulith tự phát hành các tên đó. Với registry hoàn tất lưu lịch sử lâu dài, cần cân nhắc lưu trữ/archiving và dọn dữ liệu phù hợp, tránh bảng publication tăng không giới hạn.

## 11. Những nhầm lẫn thường gặp

### “Dùng `ApplicationEventPublisher` là tự động gửi event ra Kafka”

Sai. Publisher của Spring hoạt động bên trong ứng dụng. Cần dependency externalization, lựa chọn event, broker adapter, cấu hình connection và cơ chế quản lý publication nếu muốn gửi ra ngoài.

### “Mọi domain event đều nên thành integration event”

Sai. Nhiều domain event chỉ phục vụ xử lý nội bộ. Công bố tràn lan khiến bên ngoài phụ thuộc vào chi tiết mô hình nguồn, tăng nguy cơ lộ dữ liệu và làm phức tạp versioning. Chọn event dựa trên nhu cầu của consumer và quyền sở hữu nghiệp vụ.

### “Lưu publication là đã bảo đảm consumer xử lý chính xác một lần”

Sai. Registry theo dõi công việc phát/giao sự kiện ở phía ứng dụng nguồn; consumer phải có trạng thái, offset/ACK và idempotency riêng. Duplicate có thể phát sinh khi retry hoặc khi xác nhận bị mất.

### “`@Transactional` tự làm cho database và Kafka commit nguyên tử”

Sai. Transaction thông thường bảo vệ resource của transaction manager được cấu hình. Việc phối hợp database và broker cần kiến trúc publication phù hợp; không nên giả định hai resource độc lập có commit nguyên tử.

### “Message đến Kafka theo thứ tự là consumer mọi nơi sẽ nhận theo thứ tự”

Sai. Thứ tự cần được phát biểu theo topic/partition/key, concurrency, retry và state machine của consumer. Không thể suy ra ordering toàn cục từ việc dùng Kafka key.

### “Spring Modulith Registry là một outbox engine đáp ứng mọi yêu cầu production”

Không nên mặc định. Registry theo dõi publication và hỗ trợ recovery; các yêu cầu như điều phối đa instance, ordering, claim và dispatch chính sách phức tạp cần được đánh giá riêng. Spring Modulith 2.1 có lựa chọn tích hợp outbox, nhưng phụ thuộc backend và cấu hình phù hợp.

### “Integration event chỉ là đổi tên DTO và gửi JSON”

Sai. Một integration event bao gồm **ngữ nghĩa nghiệp vụ**, quyền sở hữu, contract tương thích, transaction, routing và chính sách xử lý lỗi. Payload đúng cú pháp JSON chưa đủ để hệ thống nhận diễn giải đúng thông điệp.

## 12. Bài tập thực hành và tiêu chí hoàn thành

**Bài toán:** Ứng dụng Spring Modulith có các module `orders`, `billing` và `notifications`. Khi `orders` xác nhận đơn, hệ thống logistics chạy độc lập cần tạo shipment. Một số sự kiện bị mất khi Kafka tạm ngừng; một số shipment được tạo hai lần sau retry.

### 12.1. Yêu cầu triển khai

1. Xác định module nào được quyền phát sự kiện xác nhận đơn và điều kiện nghiệp vụ để sự kiện hợp lệ.
2. Thiết kế contract integration event `orders.confirmed.v1` với `eventId`, `orderId`, `occurredAt` và các trường cần thiết khác.
3. Cấu hình Spring Modulith để externalize đúng event, với Kafka topic và key theo `orderId`.
4. Cấu hình registry bền vững hoặc outbox phù hợp để quản lý sự kiện chưa gửi thành công.
5. Tạo consumer logistics lưu dấu `eventId` và tránh tạo nhiều shipment với cùng một đơn khi message được giao lại.
6. Viết các ca test: transaction rollback, broker lỗi, replay event, duplicate event, consumer restart.
7. Quan sát publication chưa hoàn tất và consumer lag bằng log/metric phù hợp.

### 12.2. Checklist nghiệm thu

- [ ] Sự kiện chỉ được phát khi nghiệp vụ nguồn thực sự đủ điều kiện.
- [ ] Event được externalize có ý nghĩa và schema ổn định với consumer bên ngoài.
- [ ] Producer không phụ thuộc trực tiếp vào implementation hoặc endpoint riêng của consumer.
- [ ] Có cơ chế bảo vệ publication khi source transaction commit nhưng broker tạm ngừng.
- [ ] Consumer xử lý lặp an toàn, có chính sách cho event lỗi và schema không tương thích.
- [ ] Routing/key/order được mô tả phù hợp với mức bảo đảm của transport.
- [ ] Các ca commit, rollback, gửi lỗi, replay và duplicate có kết quả kiểm chứng.
- [ ] Theo dõi được event còn dang dở mà không cần kiểm tra thủ công từng bảng dữ liệu.

### 12.3. Câu hỏi tự kiểm tra

1. Sự khác biệt lớn nhất giữa một domain event nội bộ và integration event là gì?
2. Tại sao không nên tự động externalize mọi application event của một Spring Modulith?
3. `@Externalized("orders.confirmed.v1::#{#this.orderId()}")` thể hiện target và routing key ra sao khi dùng Kafka?
4. Vì sao publication registry không chứng minh được consumer bên ngoài đã xử lý xong?
5. Trường hợp broker nhận message nhưng producer crash trước khi ghi dấu hoàn tất có thể dẫn tới điều gì?
6. Vì sao event ID cần đi cùng unique constraint hoặc chiến lược idempotency có bảo vệ cạnh tranh?
7. Khi nào nên dùng integration DTO khác với domain event?
8. Thay đổi ý nghĩa của event dù schema giữ nguyên có thể gây hậu quả gì?
9. Điểm khác nhau giữa externalization dựa trên listener và một outbox engine chuyên dụng là gì?
10. Những thông số nào cho thấy producer đã hoạt động bình thường nhưng consumer vẫn đang tụt lại?

## 13. Tài liệu đối chiếu

- [Spring Modulith Reference — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event listeners, publication registry, event externalization, các backend/adapter và lưu ý vận hành.
- [Spring Modulith API — `@Externalized`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/Externalized.html): annotation công bố event ra hạ tầng bên ngoài.
- [Spring Modulith Reference — Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html): cấu hình event registry/externalization của phiên bản tài liệu hiện hành.

Từ góc nhìn kiến trúc, **sự kiện tích hợp là một contract vượt ranh giới triển khai**. Spring Modulith giúp chọn và externalize application events, nhưng chất lượng của luồng vẫn phụ thuộc vào việc xác định đúng sự thật nghiệp vụ, ghi publication phù hợp với transaction, thiết kế versioning, xử lý trùng, khôi phục khi lỗi và theo dõi cả producer lẫn consumer.
