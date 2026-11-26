# Event externalization và hợp đồng message

## 1. Từ application event nội bộ đến message cho hệ thống bên ngoài

Spring Modulith khuyến khích các application module trao đổi qua event để module phát không phải biết mọi module nhận. Ví dụ `orders` phát `OrderPlaced`; module `inventory` nhận qua `@ApplicationModuleListener` để giữ hàng. Nhưng một hệ thống ngoài ứng dụng — chẳng hạn dịch vụ vận chuyển độc lập — không thể đăng ký trực tiếp một Spring application listener trong cùng `ApplicationContext`.

**Event externalization** là cơ chế chọn một số Spring application event và gửi chúng qua hạ tầng messaging như Kafka, AMQP, JMS hoặc Spring Messaging. Nó đóng vai trò **cầu nối giữa sự kiện nội bộ và hệ thống ngoài tiến trình**.

**Hợp đồng message (message contract)** là thỏa thuận có thể kiểm chứng giữa producer và consumer về *message nào sẽ được gửi, định tuyến đến đâu và payload/headers có cấu trúc, ngữ nghĩa ra sao*. Nếu producer đổi field, tên topic, định dạng ngày giờ hoặc key mà consumer không được chuẩn bị, ứng dụng nguồn vẫn có thể chạy bình thường nhưng tích hợp ngoài sẽ bị hỏng.

Ba lớp cần phân biệt:

| Lớp | Phạm vi | Ví dụ |
| --- | --- | --- |
| **Domain/application event** | Giao tiếp trong ứng dụng Spring Modulith. | `OrderPlaced` được phát từ `orders`. |
| **Externalized message** | Dữ liệu, headers, target và key gửi ra broker. | JSON `OrderPlacedMessageV1` đến topic `orders.placed.v1`. |
| **Consumer side effect** | Hệ thống ngoài tiếp nhận và xử lý message. | Dịch vụ shipping lập kế hoạch giao hàng. |

**Gửi được message không đồng nghĩa consumer đã xử lý xong.** Broker có thể xác nhận một lần publish thành công trước khi dịch vụ ngoài đọc, commit offset hoặc cập nhật database của nó.

Bài thuộc chương **Event publication** trong học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Mục tiêu là kiểm chứng ranh giới module bằng `ApplicationModules`, dùng `@ApplicationModuleTest` để kiểm tra event nguồn, rồi mở rộng thành integration/contract tests cho broker, database và quality gate CI.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa publish application event, externalize ra broker và consumer xử lý.
2. Chọn event externalize bằng `@Externalized` hoặc `EventExternalizationConfiguration`.
3. Thiết kế **target**, **routing key**, **headers**, **public payload** và phiên bản schema.
4. Tách hợp đồng message ngoài hệ thống khỏi model JPA và cấu trúc module nội bộ.
5. Dự đoán hành vi commit/rollback, lỗi gửi broker, resubmission và xử lý trùng.
6. Viết unit/contract test cho selection-mapping-routing và integration test với broker thật.
7. Kết hợp kiểm thử ranh giới kiến trúc, publication và hợp đồng message trong CI.

## 2. Luồng externalization trong Spring Modulith

Spring Modulith-native event externalization hoạt động dựa trên **transactional event listener** phối hợp với bộ gửi riêng của từng broker. Theo luồng điển hình:

1. `OrderService` mở transaction, cập nhật dữ liệu rồi gọi `publishEvent(new OrderPlaced(...))`.
2. Hạ tầng xác định event nào phải externalize.
3. Event Publication Registry — nếu đã cấu hình persistence phù hợp — ghi nhận publication đến target externalization trong transaction nghiệp vụ.
4. Khi transaction nguồn **commit**, externalization listener thực hiện thao tác gửi tới broker.
5. Hạ tầng có thể biến đổi payload thành DTO bên ngoài, thêm headers và tính routing target/key.
6. Khi giao tới broker được xác nhận thành công theo cơ chế client, publication có thể được đánh dấu hoàn tất.
7. Consumer bên ngoài nhận message theo giao thức broker và tự quản lý lỗi, retry, idempotency của nó.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as orders.OrderService
    participant DB as Database
    participant App as ApplicationEventPublisher
    participant Ext as Spring Modulith Externalizer
    participant Registry as Event Publication Registry
    participant Broker as Message Broker
    participant Consumer as External Consumer

    Client->>Orders: place(orderId)
    Orders->>DB: Lưu order trong transaction
    Orders->>App: publishEvent(OrderPlaced)
    App->>Registry: Ghi publication cho target externalizer
    Orders->>DB: COMMIT nguồn
    App-->>Ext: Giao sau commit
    Ext->>Ext: Select / map / headers / route
    Ext->>Broker: Publish OrderPlacedMessageV1
    Broker-->>Ext: Xác nhận theo broker client
    Ext-->>Registry: Đánh dấu publication completed
    Broker-->>Consumer: Deliver message
    Consumer->>Consumer: Xử lý và xác nhận riêng
~~~

Sơ đồ trình bày logic, không mô tả chi tiết mọi thread, callback và mức xác nhận của từng broker. Consumer có thể xử lý **sau** thời điểm Registry ghi nhận publication hoàn tất. Spring Modulith không tự đưa transaction database nguồn, broker và database của consumer vào một distributed transaction duy nhất.

### 2.1. Ba bước kỹ thuật của externalization

| Bước | Câu hỏi | Giá trị kiểm thử |
| --- | --- | --- |
| **Selection** | Event này có được externalize không? | `OrderPlaced` được chọn, `InternalPriceRecalculated` không được chọn. |
| **Mapping** | Đối tượng nào được gửi ra ngoài? | `OrderPlaced` được chuyển thành `OrderPlacedMessageV1`, không serialize JPA entity. |
| **Routing** | Message đi tới topic/target nào, key nào? | Topic `orders.placed.v1`, key theo `orderId`. |

Không kiểm thử riêng từng bước dễ dẫn đến lỗi tích hợp: producer có phát event nhưng event bị bỏ qua ở selection; message được gửi nhưng lộ field nội bộ; hoặc payload đúng nhưng topic/key sai.

### 2.2. Điều gì xảy ra khi rollback?

Nếu nguồn gọi `publishEvent` trong transaction rồi transaction **rollback**, một `PublishedEvents` test vẫn có thể quan sát lời gọi phát event. Nhưng transactional externalization listener ở pha `AFTER_COMMIT` **không được kích hoạt**, và bản ghi publication được ghi cùng transaction nguồn cũng rollback.

Vì vậy, phải kiểm tra **không có message được gửi do transaction bị rollback**, thay vì khẳng định lệnh `publishEvent` chưa từng chạy. Các side effect do `@EventListener` thông thường thực hiện đồng bộ trước commit không mặc nhiên được rollback cùng database.

## 3. Hạ tầng broker được Spring Modulith hỗ trợ

Spring Modulith có các integration module riêng:

| Hạ tầng | Artifact | Đặc điểm định tuyến |
| --- | --- | --- |
| **Apache Kafka** | `spring-modulith-events-kafka` | Logical target trở thành topic; routing key được sử dụng như message key. |
| **AMQP** | `spring-modulith-events-amqp` | Logical routing key được dùng làm AMQP routing key; cần thư viện/config broker phù hợp, ví dụ Spring Rabbit. |
| **JMS** | `spring-modulith-events-jms` | Dùng Spring JMS; không hỗ trợ routing key theo cách của Kafka/AMQP. |
| **Spring Messaging** | `spring-modulith-events-messaging` | Target là tên bean `MessageChannel`; thông tin routing được chuyển tiếp qua header `springModulith_routingTarget`. |

Các adapter đều liên quan đến **selection**, **payload** và **routing**, nhưng không có nghĩa cùng một tên target/key sẽ mang ý nghĩa hạ tầng giống hệt nhau. Broker có thể yêu cầu topic/exchange/queue, serializer, ACL, xác nhận gửi và topology riêng.

Ví dụ dependency Gradle cho Kafka, với ứng dụng đã có Spring Boot và cơ chế quản lý phiên bản dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-events-kafka'
    implementation 'org.springframework.modulith:spring-modulith-starter-jdbc'
    implementation 'org.springframework.kafka:spring-kafka'

    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
~~~

**Vai trò các dependency khác nhau:** `spring-modulith-events-kafka` cung cấp externalization adapter; `spring-modulith-starter-jdbc` là ví dụ về persistence cho Event Publication Registry. Ứng dụng còn cần JDBC driver/datasource, transaction manager, schema publication, cấu hình Kafka producer và serializers. Dự án có thể sử dụng JPA/MongoDB hoặc loại registry persistence khác; không nhất thiết phải dùng JDBC trong mọi ứng dụng.

Ví dụ cấu hình broker — **giá trị minh họa**, không phải endpoint production:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=org.springframework.kafka.support.serializer.JsonSerializer
~~~

Config serializer phải tương thích với **payload sau bước mapping**, không chỉ với domain event ban đầu. Về vận hành, topic và quyền producer/consumer cần được provision qua quy trình hạ tầng; không giả định mọi broker đều tự tạo topic.

## 4. Hợp đồng message: không sao chép tùy tiện model nội bộ

Một Spring application event là đối tượng Java do ứng dụng sở hữu. Nếu serialize nguyên object đó ra ngoài, thay đổi tên package, kiểu trường hoặc logic nội bộ có thể vô tình trở thành breaking change đối với consumer.

Đề xuất thiết kế **contract riêng**:

| Thành phần hợp đồng | Ví dụ | Lý do cần ổn định |
| --- | --- | --- |
| **Event name** | `orders.placed` | Ý nghĩa nghiệp vụ thống nhất. |
| **Schema version** | `1` | Consumer biết cách diễn giải payload. |
| **Event ID** | UUID | Chống xử lý trùng khi broker/registry retry. |
| **Aggregate ID** | `orderId` | Liên hệ với đối tượng nghiệp vụ; có thể làm Kafka key. |
| **Occurred at** | ISO-8601 UTC | Thời điểm nghiệp vụ, không nhầm với thời điểm gửi/nhận. |
| **Payload** | `total`, `currency` | Dữ liệu consumer thật sự cần. |
| **Routing** | `orders.placed.v1` | Tên topic/target được quản trị. |
| **Headers** | `eventType`, `schemaVersion`, `eventId` | Phục vụ quan sát/định tuyến theo broker hỗ trợ. |

### 4.1. Ví dụ hợp đồng JSON

~~~json
{
  "schemaVersion": 1,
  "eventId": "0f8b419b-8d34-4d96-8f05-536ae96559f1",
  "orderId": "96b97f50-2ad5-4a42-9f11-fc4c174f71d5",
  "occurredAt": "2026-11-26T01:30:00Z",
  "total": 129900.00,
  "currency": "VND"
}
~~~

JSON trên chỉ minh họa, không phải bản ghi hệ thống thật. Một hợp đồng tốt cần quy định rõ thêm:

- `total` dùng **decimal** hay đơn vị tiền nhỏ nhất (integer), quy tắc rounding và precision.
- `currency` theo mã nào và có phân biệt chữ hoa/chữ thường không.
- `occurredAt` có luôn UTC không, độ chính xác đến mili/vi giây thế nào.
- Field nào **bắt buộc**, field nào tùy chọn, có chấp nhận `null` hay không.
- Consumer xử lý field không biết hoặc message có version cao hơn ra sao.
- Có thông tin nhạy cảm nào không được đưa vào message/log/headers.

Ví dụ, đổi `total` từ `129900.00` thành chuỗi `"129900 VND"` sẽ phá vỡ consumer đọc số, ngay cả khi bên producer Java vẫn biên dịch.

### 4.2. Một message không phải bản sao toàn bộ aggregate

Không gửi `OrderEntity` kèm quan hệ JPA, Hibernate lazy proxy, thông tin thanh toán nhạy cảm hoặc toàn bộ profile khách hàng chỉ vì những dữ liệu ấy có sẵn. Hợp đồng nên:

1. Chứa dữ liệu vừa đủ cho consumer thực hiện công việc đã cam kết.
2. Có danh tính event/aggregate ổn định.
3. Không yêu cầu consumer hiểu class nội bộ hoặc tên package triển khai.
4. Có cách mở rộng schema với chiến lược backward/forward compatibility.
5. Được lưu và kiểm tra qua các phiên bản triển khai.

Nếu consumer cần bổ sung dữ liệu ngoài contract, cân nhắc mở rộng có version hoặc thiết kế query API riêng; không mở thẳng database của module nguồn để “tiện”.

## 5. Ví dụ cấu trúc module: orders phát, outbound externalize

Giả sử `ShopApplication` nằm ở `com.example.shop`. Dưới cách phát hiện module theo package con trực tiếp:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── internal
│   │   ├── OrderEntity.java
│   │   └── OrderRepository.java
│   └── events
│       ├── OrderPlaced.java
│       └── package-info.java
└── outbound
    ├── OrderExternalizationConfiguration.java
    ├── package-info.java
    └── contract
        └── OrderPlacedMessageV1.java
~~~

**Module `orders` là nguồn phát.** Module `outbound` sở hữu chính sách chuyển domain event thành public message contract. `orders` không cần import Kafka template, Rabbit template hay DTO được công khai ra bên ngoài. Spring Modulith externalization adapter thực hiện phần giao tiếp broker.

### 5.1. Event nội bộ được công bố qua named interface

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import org.springframework.modulith.events.Externalized;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Externalized("orders.placed.v1")
public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        BigDecimal total,
        String currency
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(total);
        Objects.requireNonNull(currency);
    }
}
~~~

`@Externalized` là cách **opt-in** chọn loại event để gửi ra broker. Giá trị `orders.placed.v1` ở đây chỉ định **logical target** (ví dụ tên Kafka topic), không thay thế event name hoặc version field trong payload.

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Named interface cho phép module `outbound` phụ thuộc vào public event API của `orders`. `@Externalized` lựa chọn externalization, còn `@NamedInterface` quản lý **module boundary** — hai annotation giải quyết hai vấn đề khác nhau.

### 5.2. Source service lưu dữ liệu và publish trong transaction

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void place(UUID orderId, BigDecimal total, String currency) {
        orders.save(new OrderEntity(orderId, total, currency));
        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, Instant.now(), total, currency));
    }
}
~~~

`OrderEntity`/`OrderRepository` là thành phần JPA nội bộ được lược bỏ định nghĩa để tập trung vào externalization. Ứng dụng cần validation, unique constraint, quản lý trạng thái và idempotency của use case theo yêu cầu nghiệp vụ.

Event được **phát trong transaction** nhưng adapter externalization dựa trên transactional listener sẽ gửi sau commit. Nếu transaction bị rollback, không được tạo message ngoài chỉ dựa vào event này.

### 5.3. Public DTO thuộc integration contract

File `outbound/contract/OrderPlacedMessageV1.java`:

~~~java
package com.example.shop.outbound.contract;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPlacedMessageV1(
        int schemaVersion,
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        BigDecimal total,
        String currency
) {}
~~~

`OrderPlacedMessageV1` là payload dự kiến đưa lên broker; nó **không phải JPA entity** và không chứa phương thức phụ thuộc vào service/repository. Chọn `V1` trong tên Java có thể giúp quản lý code, nhưng **hợp đồng trên dây** là tên event/topic, trường `schemaVersion` và schema serializer thực sự — không phải tên class Java trong producer.

File `outbound/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.outbound;
~~~

## 6. Selection, mapping, headers và routing bằng Java configuration

Spring Modulith cung cấp `EventExternalizationConfiguration` để lựa chọn event và tùy chỉnh thông điệp. Ví dụ dưới đây dùng đồng thời:

- `@Externalized` để đánh dấu event.
- `mapping(...)` để tạo DTO `OrderPlacedMessageV1`.
- `headers(...)` để thêm thông tin định danh/phiên bản.
- `routeKey(...)` để dùng `orderId` làm Kafka key.

File `outbound/OrderExternalizationConfiguration.java`:

~~~java
package com.example.shop.outbound;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.outbound.contract.OrderPlacedMessageV1;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.events.EventExternalizationConfiguration;

import java.util.Map;

@Configuration(proxyBeanMethods = false)
class OrderExternalizationConfiguration {

    @Bean
    EventExternalizationConfiguration eventExternalizationConfiguration() {
        return EventExternalizationConfiguration.externalizing()
                .select(EventExternalizationConfiguration
                        .annotatedAsExternalized())
                .mapping(OrderPlaced.class, event ->
                        new OrderPlacedMessageV1(
                                1,
                                event.eventId(),
                                event.orderId(),
                                event.occurredAt(),
                                event.total(),
                                event.currency()))
                .headers(OrderPlaced.class, event -> Map.of(
                        "eventType", "orders.placed",
                        "schemaVersion", "1",
                        "eventId", event.eventId().toString()))
                .routeKey(OrderPlaced.class,
                        event -> event.orderId().toString())
                .build();
    }
}
~~~

Trong ví dụ, `@Externalized("orders.placed.v1")` cung cấp target, còn `routeKey` tính key từ event. Với Kafka, target được dùng như **topic**, còn key giúp định tuyến các record cùng order tới partition theo cấu hình producer/broker.

**Lưu ý quan trọng về API:** bước `select(annotatedAsExternalized())` là selection programmatic. Theo tài liệu Spring Modulith, khi tùy chỉnh selection theo cách này, cần hiểu nó thay thế bộ lọc mặc định dựa trên base package; mọi event được annotate tương ứng và có mặt trong classpath có thể được xem xét. Nếu cần giới hạn theo module/package, hãy dùng selector phù hợp và kiểm thử cả sự kiện **không được phép externalize**.

### 6.1. Routing mặc định hay tùy chỉnh?

Nếu chỉ dùng:

~~~java
@Externalized("orders.placed.v1")
public record OrderPlaced(/* ... */) {}
~~~

thì logical target đã được khai báo trực tiếp. Nếu bỏ value, Spring Modulith có thể chọn tên type tương đối với application base package làm target; ví dụ `orders.events.OrderPlaced`. Đây có thể không phải tên topic ổn định cho consumer ngoài, vì đổi package/refactor Java có nguy cơ đổi topic. Nên dùng **target tường minh** khi broker topic là một hợp đồng dài hạn.

Với annotation, có thể khai báo cả key:

~~~java
@Externalized("orders.placed.v1::#{#this.orderId()}")
public record OrderPlaced(/* ... */) {}
~~~

Mẫu `target::key` cho phép phần key là SpEL expression lấy từ event, nhưng cần kiểm tra SpEL accessor/record method thực tế. Đây là **phương án thay thế** cho cách `routeKey(...)` ở trên; không cần cấu hình trùng hai lần nếu một cách đã giải quyết đủ.

### 6.2. Mapping khác routing

Mặc định routing được quyết định dựa trên **event gốc**, không dựa trên DTO sau mapping. Vì vậy:

~~~text
OrderPlaced (event gốc)
  |-- selection: @Externalized
  |-- mapping  : OrderPlacedMessageV1
  |-- routing  : orders.placed.v1 + key(orderId từ event gốc)
  +-- headers  : eventType/schemaVersion/eventId
~~~

Không giả định vì payload chuyển thành `OrderPlacedMessageV1` mà target tự đổi thành `OrderPlacedMessageV1`. Spring Modulith có API `routeMapped()` khi muốn router tính theo payload **đã mapping**, nhưng đó là lựa chọn chủ động và cần test riêng để tránh silent routing change.

### 6.3. Chọn event bằng predicate thay vì annotation

Một ứng dụng muốn giữ domain event hoàn toàn độc lập với annotation externalization có thể lựa chọn bằng code:

~~~java
@Bean
EventExternalizationConfiguration externalization() {
    return EventExternalizationConfiguration.externalizing()
            .select(event -> event instanceof OrderPlaced)
            .route(OrderPlaced.class, event ->
                    RoutingTarget.forTarget("orders.placed.v1")
                            .andKey(event.orderId().toString()))
            .build();
}
~~~

Đây là **một cấu hình thay thế**, không nên đồng thời đăng ký thêm bean `EventExternalizationConfiguration` khác cạnh tranh với cấu hình ở mục trước. Cần import `RoutingTarget` và `OrderPlaced`. Khi dùng selector programmatic, hãy có test âm tính để chứng minh event nội bộ khác không bị externalize vô tình.

## 7. Hợp đồng tương thích: thay đổi thế nào mà không phá consumer?

Hợp đồng message tồn tại độc lập với tốc độ deploy của producer. Một module có thể được refactor hàng tuần, nhưng consumer ngoài có thể chỉ nâng cấp mỗi quý.

### 7.1. Tương thích schema không tự đến từ Java compilation

| Thay đổi | Thường an toàn? | Điều kiện |
| --- | --- | --- |
| Thêm field optional `promotionCode` | Có thể | Consumer bỏ qua unknown field và field mới có default/nullable rõ ràng. |
| Thêm field required không có default | Nguy hiểm | Consumer cũ/new cần chiến lược tương thích. |
| Đổi `orderId` từ UUID string thành integer | Breaking change | Cần version schema hoặc giai đoạn chuyển đổi. |
| Đổi `total` từ decimal sang string | Breaking change | Consumer parse sai kiểu. |
| Đổi timestamp từ UTC sang timezone local tùy server | Nguy hiểm | Ngữ nghĩa thời gian bị thay đổi. |
| Đổi Kafka key từ `orderId` sang `eventId` | Có thể breaking ở hành vi | Partition/order theo aggregate có thể thay đổi. |
| Đổi topic `orders.placed.v1` thành `orders.placed` | Breaking về routing | Consumer phải đổi subscription/ACL. |
| Đổi tên class nội bộ nhưng giữ public DTO/serializer/topic | Có thể an toàn | Không dựa vào Java type header hoặc package-name contract. |

Tính tương thích phụ thuộc format (JSON, Avro, Protobuf…), serializer và chính sách của consumer. “Thêm field là luôn an toàn” không đúng khi consumer cấu hình strict deserialization hoặc validate schema cứng.

### 7.2. Version payload và topic

Có hai lựa chọn phổ biến:

- **Một topic, nhiều version**: event giữ logical target ổn định, mỗi message mang `schemaVersion`; consumer hiểu nhiều phiên bản hoặc dùng schema registry phù hợp.
- **Topic theo major version**: ví dụ `orders.placed.v1`, `orders.placed.v2`; producer có thể dual-publish trong giai đoạn chuyển đổi có quản lý.

Không có một cách phù hợp cho mọi hệ thống. Với schema thay đổi không tương thích, nên có **lộ trình migration**: tài liệu hợp đồng, release note, consumer test, shadow/dual-read hoặc dual-publish khi cần, thời hạn ngừng hỗ trợ version cũ.

**Cảnh báo:** dual-publish có thể khiến hệ thống ngoài xử lý cùng nghiệp vụ hai lần nếu nó subscribe cả hai topic/version. Cần định danh event và chính sách deduplication rõ ràng.

### 7.3. Semantics trước syntax

Ngay cả khi JSON hợp lệ và schema không đổi, việc thay đổi **ý nghĩa** event cũng có thể breaking:

- Trước đây `OrderPlaced` nghĩa là đơn hàng đã được **commit**, sau đó đổi thành “request nhận được nhưng chưa lưu”.
- `total` trước đây đã gồm thuế, sau đó đổi thành chưa gồm thuế.
- `occurredAt` từ thời điểm đặt hàng đổi thành thời điểm message được gửi lên Kafka.

Các thay đổi này có thể không làm consumer deserialize lỗi nhưng gây sai nghiệp vụ. Message contract phải mô tả **điều kiện phát, ý nghĩa field và bảo đảm giao hàng**, không chỉ liệt kê tên trường.

## 8. Testing selection, mapping và routing mà chưa cần Kafka

Với ví dụ configuration ở mục 6, có thể unit test `EventExternalizationConfiguration` ngay trong package `com.example.shop.outbound`. Cách này nhanh, ổn định và bắt lỗi cấu hình trước khi chạy integration test broker.

~~~java
package com.example.shop.outbound;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.outbound.contract.OrderPlacedMessageV1;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.events.EventExternalizationConfiguration;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class OrderExternalizationConfigurationTests {

    private final EventExternalizationConfiguration config =
            new OrderExternalizationConfiguration()
                    .eventExternalizationConfiguration();

    @Test
    void selectsMapsAndRoutesOrderPlaced() {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        Instant occurredAt = Instant.parse("2026-11-26T01:30:00Z");
        var amount = new BigDecimal("129900.00");

        var event = new OrderPlaced(
                eventId, orderId, occurredAt, amount, "VND");

        assertThat(config.supports(event)).isTrue();
        assertThat(config.supports(new Object())).isFalse();

        assertThat(config.map(event)).isEqualTo(
                new OrderPlacedMessageV1(
                        1, eventId, orderId, occurredAt, amount, "VND"));

        var route = config.determineTarget(event);
        assertThat(route.getTarget()).isEqualTo("orders.placed.v1");
        assertThat(route.getKey()).isEqualTo(orderId.toString());

        assertThat(config.getHeadersFor(event))
                .containsEntry("eventType", "orders.placed")
                .containsEntry("schemaVersion", "1")
                .containsEntry("eventId", eventId.toString());
    }
}
~~~

Test này khẳng định **config-level contract**: event được chọn, payload mapping đúng, target/key và headers đúng. Nó **chưa chứng minh** Spring Kafka serializer có gửi ra một message thật, broker đã xác nhận hay consumer đọc được.

### 8.1. Kiểm tra JSON serialized đúng cấu trúc

Nếu ứng dụng chọn JSON với Jackson, hãy test DTO bằng **cùng ObjectMapper/serializer configuration** mà producer dùng:

~~~java
@Test
void serializesExternalPayloadWithStableShape() throws Exception {
    var event = new OrderPlaced(
            UUID.fromString("0f8b419b-8d34-4d96-8f05-536ae96559f1"),
            UUID.fromString("96b97f50-2ad5-4a42-9f11-fc4c174f71d5"),
            Instant.parse("2026-11-26T01:30:00Z"),
            new BigDecimal("129900.00"),
            "VND");

    var dto = config.map(event);
    String json = objectMapper.writeValueAsString(dto);
    var tree = objectMapper.readTree(json);

    assertThat(tree.path("schemaVersion").asInt()).isEqualTo(1);
    assertThat(tree.path("eventId").asText())
            .isEqualTo(event.eventId().toString());
    assertThat(tree.path("orderId").asText())
            .isEqualTo(event.orderId().toString());
    assertThat(tree.path("currency").asText()).isEqualTo("VND");
    assertThat(tree.has("customerPassword")).isFalse();
}
~~~

Đây là **đoạn test bổ sung**, cần đặt trong lớp test đã có `config`, `objectMapper` và import cần thiết. Để dùng `Instant`, ObjectMapper phải có cấu hình ngày giờ thích hợp (ví dụ Java Time module). Hãy lưu một số **golden JSON fixtures** hoặc schema do team quản lý để CI phát hiện các thay đổi không tương thích theo thời gian; không chỉ so DTO với chính code mapping vừa sửa.

### 8.2. Vì sao phải có test âm tính?

Nếu vô tình cấu hình selector “externalize mọi event”, có thể gửi cả `InternalPriceRecalculated`, `PasswordResetRequested` hoặc sự kiện chứa dữ liệu nhạy cảm ra broker. Một test:

~~~java
assertThat(config.supports(new InternalPriceRecalculated(...)))
        .isFalse();
~~~

sẽ phát hiện sai phạm **event selection**. `InternalPriceRecalculated` là kiểu minh họa; dự án phải thay bằng một event nội bộ thực có dữ liệu fixture phù hợp.

## 9. @ApplicationModuleTest kiểm chứng việc phát event nguồn

Đặt test trong package `com.example.shop.orders`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderPublicationTests {

    @Autowired OrderService orders;

    @Test
    void publishesPublicOrderPlacedEvent(PublishedEvents events) {
        UUID orderId = UUID.randomUUID();
        orders.place(orderId, new BigDecimal("129900.00"), "VND");

        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.eventId()).isNotNull();
                    assertThat(event.total())
                            .isEqualByComparingTo("129900.00");
                    assertThat(event.currency()).isEqualTo("VND");
                });
    }
}
~~~

`PublishedEvents` quan sát application events của test; đây là **producer module test**, không phải test gửi broker. Module test `STANDALONE` có thể không bootstrap outbound/broker integration ở module khác. Nếu test này pass nhưng Kafka topic sai hoặc mapper làm rơi trường `eventId`, consumer ngoài vẫn có thể thất bại.

**Phân chia trách nhiệm kiểm thử:**

- `orders` test: event nào được phát và payload domain nào đúng.
- `outbound` test: event nào được chọn, mapping/route/headers/schema ra sao.
- Broker integration test: message thực sự được gửi sau commit và đọc được với serializer phù hợp.
- Consumer contract test: consumer thực sự hiểu message và xử lý lặp/field version.

## 10. Integration test với broker thật

Sau unit contract tests, cần một bài kiểm thử tích hợp Kafka/AMQP/JMS tùy hạ tầng đang dùng. Có thể dùng Testcontainers hoặc embedded broker phù hợp bản dependency. Mục tiêu **không chỉ test method `KafkaTemplate.send(...)` được gọi**, mà còn quan sát message trên broker.

### 10.1. Kịch bản Kafka end-to-end tối thiểu

1. Khởi động test application với `spring-modulith-events-kafka`, Registry persistence, datasource và Kafka broker dành cho test.
2. Provision topic `orders.placed.v1`; cấu hình producer serializer tương ứng DTO.
3. Tạo order trong transaction và để `OrderService.place(...)` **commit thật**.
4. Consumer test đăng ký vào `orders.placed.v1`, đọc record theo timeout.
5. Assert topic, key, headers, payload JSON, `eventId`, `orderId`, `schemaVersion` và giá trị tiền.
6. Kiểm tra chỉ sự kiện được chọn mới ra broker; event không chọn không làm xuất hiện message ngoài dự kiến.
7. Trong test riêng, gây rollback sau `publishEvent` rồi kiểm tra không có externalized message tương ứng.

Ví dụ **phần assertion** khi test harness đã nhận được `ConsumerRecord<String, String> record` và có `ObjectMapper`:

~~~java
assertThat(record.topic()).isEqualTo("orders.placed.v1");
assertThat(record.key()).isEqualTo(orderId.toString());

var body = objectMapper.readTree(record.value());
assertThat(body.path("schemaVersion").asInt()).isEqualTo(1);
assertThat(body.path("orderId").asText())
        .isEqualTo(orderId.toString());
assertThat(body.path("eventId").asText()).isNotBlank();
assertThat(body.path("currency").asText()).isEqualTo("VND");
~~~

Đây không phải test class tự chạy: việc tạo consumer, bootstrap broker, cấu hình serializer, chờ record và dọn offsets cần triển khai với bộ công cụ test tương ứng. Nếu producer dùng `JsonSerializer`, giá trị Kafka có thể được deserialize thành object hoặc byte array tùy cấu hình consumer; hãy **đối chiếu on-wire bytes thực** trước khi chọn kiểu `ConsumerRecord`.

### 10.2. Test rollback không externalize

Trong một `@SpringBootTest` **không** có `@Transactional` bao ngoài:

~~~java
var tx = new TransactionTemplate(transactionManager);
UUID orderId = UUID.randomUUID();

tx.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderPlaced(
            UUID.randomUUID(),
            orderId,
            Instant.now(),
            new BigDecimal("129900.00"),
            "VND"));
    status.setRollbackOnly();
});
~~~

Tại đây `publishEvent` **đã được gọi**; test `PublishedEvents` có thể vẫn thấy event. Nhưng externalization theo `AFTER_COMMIT` không được kích hoạt. Bài kiểm thử nên có **nhánh commit đối chứng** để chứng minh adapter đang hoạt động, đồng thời kiểm tra Registry không để lại publication bền vững của event bị rollback.

**Một lưu ý về negative assertion async:** “không thấy record trong 100 ms” chưa chứng minh tuyệt đối không bao giờ có record. Thiết kế test dùng ID riêng, consumer offset được cô lập, deadline đủ hợp lý, kiểm tra cấu hình transaction/registry và đối chứng commit thay vì chỉ dựa vào `Thread.sleep`.

### 10.3. Khi broker không sẵn sàng

Test tích hợp lỗi broker cần kiểm tra:

- Transaction nguồn có commit và dữ liệu nghiệp vụ còn tồn không?
- Publication externalization có được lưu để phục hồi không?
- Adapter có báo lỗi hoặc publication còn incomplete theo cấu hình không?
- Khi broker phục hồi, resubmission có gửi được message **đúng topic/key/payload** không?
- Nếu broker đã nhận message nhưng producer không nhận được ack, retry có thể tạo message lặp không?

Đây là phép kiểm tra về **tính bền vững và retry**, khác test JSON contract đơn thuần. Với nhiều listener nội bộ và externalizer, cần quan sát đúng publication **theo target**, không đếm mọi bản ghi Registry rồi coi là số lần gửi broker.

## 11. Registry, ack và giới hạn bảo đảm giao hàng

Spring Modulith-native externalization dựa trên transactional listener. Khi kết hợp Event Publication Registry persistence, lỗi trong **tương tác gửi tới broker** có thể để lại publication chưa hoàn tất để xử lý lại.

Tuy nhiên cần tách các mốc:

| Mốc | Có thể khẳng định | Không thể khẳng định |
| --- | --- | --- |
| `PublishedEvents` thấy event | Producer application event đã được phát. | Database đã commit; broker đã nhận. |
| Registry lưu publication sau commit | Có bản ghi giao event tới externalizer target. | Broker đã nhận message. |
| Externalizer hoàn tất publication | Thao tác gửi qua broker adapter được xem là thành công theo cơ chế ack/config. | Consumer đã đọc và commit side effect. |
| Consumer đọc được record | Message đã tới consumer. | Consumer đã cập nhật database thành công hoặc không bị đọc lại. |
| Consumer ghi transaction xử lý + marker idempotency | Side effect DB đã được xác nhận trong phạm vi transaction đó. | Mọi hệ thống ngoài khác đều đạt exactly once. |

### 11.1. Trường hợp gửi thành công nhưng Registry chưa kịp hoàn tất

1. Producer gọi broker và broker nhận được message.
2. Connection lỗi hoặc tiến trình dừng trước khi Registry đánh dấu publication completed.
3. Recovery resubmit publication còn incomplete.
4. Broker có thể nhận **message thứ hai** của cùng `eventId`.

Vì vậy **externalization không mặc nhiên mang bảo đảm exactly-once delivery hoặc exactly-once business effect**. Consumer cần nhận diện trùng bằng `eventId`/khóa nghiệp vụ và xử lý theo transaction/unique constraint phù hợp. Nếu dịch vụ ngoài gửi email hoặc gọi API thanh toán, dùng idempotency key ở nơi thực hiện side effect nếu được hỗ trợ.

### 11.2. Native externalization và transactional outbox chuyên dụng

Spring Modulith-native externalization dựa trên listener bất đồng bộ là cách tích hợp gọn, nhưng không thay thế mọi khả năng của một outbox triển khai đầy đủ. **Từ Spring Modulith 2.1**, tài liệu chính thức mô tả khả năng ủy quyền externalization qua các tích hợp như Namastack Outbox và JobRunr cho những yêu cầu outbox nâng cao.

Ví dụ ở phiên bản hỗ trợ, khi đã thêm starter tích hợp thích hợp:

~~~properties
spring.modulith.events.externalization.mode=outbox
~~~

Đây là **chọn chế độ khi đã cấu hình đúng implementation**, không phải property khiến bất kỳ project nào tự có outbox hoàn chỉnh. Khi chọn kiến trúc, phải đánh giá transactional coupling, ordering, retry scheduling, failure recovery, backpressure, consumer idempotency và cách vận hành của implementation cụ thể.

### 11.3. Ordering của message

Kafka key `orderId` có ích cho phân vùng các sự kiện cùng order; tuy nhiên ordering còn phụ thuộc partition, cấu hình producer, số instance và cơ chế retry. Khi nhiều thread externalize đồng thời, sự kiện mới có thể được gửi **trước** sự kiện cũ.

Spring Modulith có tùy chọn tuần tự hóa tương tác broker:

~~~properties
spring.modulith.events.externalization.serialize-externalization=true
~~~

Tùy chọn này giúp tuần tự hóa hoạt động externalization trong phạm vi cơ chế được cung cấp, nhưng **không phải cam kết thứ tự toàn cục xuyên mọi instance và consumer**. Nếu consumer cần xử lý `OrderPlaced` trước `OrderShipped`, message nên có aggregate version/sequence và chính sách xử lý out-of-order.

## 12. Consumer contract, idempotency và schema migration

Consumer ngoài không nên coi `eventId` chỉ là metadata trang trí:

~~~java
@Transactional
public void on(OrderPlacedMessageV1 message) {
    if (processedEventRepository.existsById(message.eventId())) {
        return;
    }

    shipmentRepository.createFromOrder(
            message.orderId(), message.total(), message.currency());
    processedEventRepository.save(
            new ProcessedEvent(message.eventId()));
}
~~~

Đoạn này là minh họa: cần triển khai repositories, validation và khóa duy nhất theo `eventId`. Chỉ gọi `existsById` không giải quyết race hoàn toàn: hai consumer đồng thời có thể đều thấy chưa xử lý. Cần unique constraint, transaction đúng và cách xử lý xung đột khi commit.

### 12.1. Consumer có thể nhận version mới

Một chiến lược rõ ràng:

~~~java
switch (message.schemaVersion()) {
    case 1 -> handleV1(message);
    default -> throw new UnsupportedMessageVersionException(
            message.schemaVersion());
}
~~~

Đây là đoạn mô tả chính sách, không phải code chạy độc lập: `handleV1` và exception cần triển khai. Nếu consumer chưa hỗ trợ version mới, phải quyết định **từ chối + dead-letter/retry có kiểm soát**, hay giữ backward-compatible reader. Không retry vô hạn một schema vĩnh viễn không hỗ trợ.

### 12.2. Contract tests nên đi theo cả hai phía

Một hợp đồng có thể được kiểm tra bằng:

- **Producer contract test:** payload JSON, headers, target, key và ngữ nghĩa publish được giữ ổn định.
- **Consumer contract test:** consumer deserialize được các fixture hỗ trợ và hiểu đúng giá trị field.
- **Compatibility test:** schema mới có phá vỡ consumer version cũ không, hoặc consumer mới còn đọc message tồn đọng cũ không.
- **Broker integration test:** actual headers/type/serialization và topic/key từ adapter có đúng contract không.

Nếu hai team triển khai độc lập, có thể dùng schema registry, consumer-driven contract testing hoặc fixture dùng chung tùy công nghệ; nhưng **không để consumer buộc phụ thuộc trực tiếp vào JPA entity** của producer.

## 13. Quan sát và bảo mật externalization

### 13.1. Những chỉ số cần theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| Số publication externalizer chưa hoàn tất theo target | Backlog gửi broker. |
| Tuổi publication externalizer cũ nhất | Khả năng event bị kẹt vượt SLA. |
| Số lần resubmit và tỷ lệ hoàn tất | Khả năng phục hồi khi broker có lỗi. |
| Producer send error/timeout rate | Độ ổn định kết nối và cấu hình broker. |
| Message serialization failure | Schema/serializer không tương thích. |
| Consumer lag và dead-letter count | Tình trạng xử lý sau khi message đã tới broker. |
| Duplicate detected theo event ID | Hiệu quả idempotency và mức retry thực tế. |
| Out-of-order detected theo aggregate ID | Nhu cầu version/sequence trong contract. |

Backlog trong Registry và consumer lag là **hai loại tồn đọng khác nhau**: cái trước biểu thị công việc gửi broker chưa hoàn tất, cái sau biểu thị message đã tồn tại trên broker nhưng consumer chưa xử lý hết.

### 13.2. Log/tracing có đủ để điều tra?

Một record log theo chuẩn ứng dụng nên có: `eventId`, `orderId` khi được phép, `eventType`, `schemaVersion`, `target`, `routingKey`, `publicationId` (nếu có), `attempt`, `correlationId`, `result` và `errorCategory`.

Không log toàn bộ payload chứa PII hoặc thông tin thanh toán. Không đặt `eventId`/`orderId` làm label metric cardinality cao; dùng trong log/trace có thời gian lưu giữ và quyền truy cập phù hợp.

Đối với listener async hoặc resubmit sau restart, MDC/thread-local tracing context không mặc nhiên được kế thừa. Nên đưa correlation ID không nhạy cảm vào contract/headers và mở span xử lý riêng phía consumer.

### 13.3. Bảo vệ hợp đồng message

- Chỉ xuất những field đã được kiểm tra theo phân loại dữ liệu.
- Mã hóa đường truyền và cấu hình ACL cho topic/queue.
- Không dùng broker message như nơi chứa access token, mật khẩu hoặc toàn bộ entity khách hàng.
- Định nghĩa retention, quyền đọc, dead-letter policy và quy trình xóa dữ liệu theo yêu cầu tổ chức.
- Nếu message có giá trị tiền, ID thanh toán hoặc quyết định nghiệp vụ quan trọng, cần validation và audit phù hợp.
- Nếu có nhiều tenant, ranh giới tenant/authorization phải được thực thi tại producer, broker và consumer; routing key không tự là cơ chế phân quyền.

## 14. Quality gate CI: kiểm chứng cả module boundary lẫn message contract

### 14.1. Test kiến trúc

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện phụ thuộc vòng, truy cập API không công khai hoặc vi phạm `allowedDependencies`. Trong ví dụ, `outbound` được phép dùng `orders.events.OrderPlaced`, nhưng không được import repository nội bộ của module `orders`.

**Giới hạn:** `ApplicationModules.verify()` không khởi động Kafka, không kiểm tra JSON và không biết consumer ngoài có đọc được `OrderPlacedMessageV1` không. Do đó phải kết hợp với test hợp đồng và tích hợp.

### 14.2. Ma trận quality gate

| Gate | Phát hiện hồi quy nào? | Kiểm tra |
| --- | --- | --- |
| **Architecture** | Outbound phụ thuộc code nội bộ của orders hoặc tạo vòng phụ thuộc. | `ApplicationModules.of(...).verify()`. |
| **Source publication** | Use case quên phát hoặc payload `OrderPlaced` sai. | `@ApplicationModuleTest` + `PublishedEvents`. |
| **Selection** | Event cần externalize bị bỏ qua, event bí mật vô tình bị xuất. | `config.supports(...)` dương tính và âm tính. |
| **Mapping/schema** | Field rơi, sai kiểu, sai đơn vị, lộ dữ liệu nhạy cảm. | Mapping unit test + JSON fixture/schema compatibility. |
| **Routing** | Topic/key/headers thay đổi ngoài hợp đồng. | `determineTarget`, `getHeadersFor`, broker record assertions. |
| **Commit/rollback** | Gửi message cho transaction nguồn rollback. | Integration test với transaction manager và broker/Registry. |
| **Broker integration** | Adapter, serializer hoặc ACL/broker config sai. | Testcontainers/embedded broker và consumer test. |
| **Failure recovery** | Gửi broker lỗi làm mất publication hoặc retry sai. | Fault injection + Registry incomplete/resubmit. |
| **Consumer idempotency** | Duplicate do retry tạo hai side effect. | DB unique marker, replay cùng event ID. |
| **Compatibility** | Schema thay đổi phá consumer cũ. | Golden fixtures/schema registry/consumer contract test. |
| **Observability** | Không phân biệt backlog gửi broker và consumer lag. | Metric/log contract và kiểm tra cảnh báo. |

Các gate chạy trong pipeline CI với thứ tự phù hợp chi phí: test kiến trúc và mapping nhanh trước, broker/database integration ở job riêng nhưng là điều kiện bắt buộc cho thay đổi externalization.

**Không đánh đồng “test `PublishedEvents` pass” với “message đã xuất đúng broker”.** Test publication ở nguồn là cần thiết nhưng không đủ để bảo vệ hợp đồng ngoài hệ thống.

## 15. Những lỗi thiết kế thường gặp

1. **Externalize mọi event nội bộ.** Có thể làm lộ payload nhạy cảm và tạo coupling không cần thiết.
2. **Serialize JPA entity ra Kafka.** Kéo theo lazy proxy, liên kết database, field nội bộ và sự phụ thuộc vào tên class Java.
3. **Không version schema.** Consumer khó phân biệt thay đổi tương thích hay breaking.
4. **Để tên topic phụ thuộc tên package.** Refactor code gây breaking change về routing.
5. **Giả định Kafka key không quan trọng.** Consumer dùng thứ tự theo aggregate có thể phụ thuộc key/partition.
6. **Nhầm registry completed với consumer completed.** Registry theo dõi thao tác gửi từ application, không kiểm soát end-to-end tất cả consumer.
7. **Không xử lý duplicate.** Broker ack có thể mất và publication được resubmit.
8. **Tự gọi lại use case để retry externalization.** Có thể sinh event nghiệp vụ mới; phải xử lý lại publication thích hợp.
9. **Dùng `Thread.sleep` cố định trong test async.** Dễ flaky, khó bảo vệ CI.
10. **Bỏ qua rollback test.** Có thể vô tình gửi message cho dữ liệu nguồn chưa commit.
11. **Không có consumer contract test.** Producer tự test serializer chưa chứng minh consumer cũ vẫn đọc được.
12. **Bật outbox mode mà không cấu hình implementation.** Property không thay thế persistence, job scheduling, migration và vận hành.

## 16. Bài tập tình huống

Một hệ thống bán hàng cần gửi `OrderPaid` từ module `payments` đến dịch vụ `shipping` qua Kafka. Payload hiện tại là:

~~~json
{
  "schemaVersion": 1,
  "eventId": "4d6d6867-691d-4936-b9c8-4051f9246ec3",
  "orderId": "b860be3d-838b-4e62-bc74-173109662692",
  "paidAt": "2026-11-26T03:00:00Z",
  "amount": 150000,
  "currency": "VND"
}
~~~

Topic: `payments.order-paid.v1`; key: `orderId`. Producer phát event trong transaction và dùng Spring Modulith Kafka externalization cùng Registry persistence.

**Câu hỏi:**

1. Vì sao module `payments` không nên gửi thẳng `PaymentEntity` ra Kafka?
2. Test `PublishedEvents` ở `payments` có chứng minh Kafka nhận được message không?
3. Nếu transaction thanh toán rollback sau `publishEvent`, message có nên xuất hiện trên topic không?
4. Nếu broker nhận message nhưng Registry không ghi completed trước khi ứng dụng crash, điều gì có thể xảy ra sau resubmit?
5. Việc đổi key sang `eventId` có thể ảnh hưởng gì tới consumer?
6. Nếu thêm field bắt buộc `taxAmount` mà consumer v1 không biết, phải đánh giá điều gì?
7. Vì sao Registry backlog và Kafka consumer lag là hai metric khác nhau?
8. Bộ test tối thiểu nào cần đi qua CI trước khi phát hành thay đổi này?

**Đáp án tham khảo:**

1. Vì entity thuộc mô hình nội bộ, có thể chứa proxy, field nhạy cảm và phụ thuộc database không ổn định; dùng message DTO có hợp đồng rõ ràng.
2. Không. `PublishedEvents` chứng minh event nội bộ được phát; cần test adapter, serializer và broker thực tế.
3. Không; externalization sau commit phải bỏ qua transaction nguồn rollback.
4. Message cùng `eventId` có thể được gửi lại; consumer cần idempotency.
5. Kafka key ảnh hưởng partitioning và khả năng bảo toàn thứ tự theo đơn hàng; thay đổi có thể phá giả định consumer.
6. Đánh giá backward/forward compatibility, default và chiến lược version/migration, không chỉ sửa record Java.
7. Registry backlog là công việc producer gửi chưa hoàn tất; consumer lag là record broker chưa được nhóm consumer xử lý hết.
8. Có `ApplicationModules.verify()`, `PublishedEvents`, selection/mapping/routing contract tests, test broker commit/rollback, consumer compatibility và idempotency/recovery.

## 17. Checklist thiết kế và kiểm chứng

- [ ] Có định nghĩa rõ business event nào là **nội bộ**, event nào được **externalize**.
- [ ] Hợp đồng ngoài gồm event name, schemaVersion, eventId, aggregateId, timestamp, payload semantics, target/key/headers.
- [ ] Chỉ đưa dữ liệu cần thiết ra broker; không serialize nguyên JPA entity hoặc đưa PII không cần thiết.
- [ ] Có target/topic tường minh, không phụ thuộc tên package có thể refactor.
- [ ] Producer dùng serializer có cấu hình tương thích với public DTO, không dựa vào mặc định chưa kiểm chứng.
- [ ] Routing key phục vụ đúng nhu cầu partition/order; có test khóa đúng theo aggregate.
- [ ] Selection có test âm tính với event không được phép gửi ra ngoài.
- [ ] Mapping và contract JSON/schema có golden fixtures hoặc consumer contract tests.
- [ ] Externalization listener chỉ gửi sau commit; có test rollback đối chứng commit.
- [ ] Có Registry persistence và cơ chế phục hồi phù hợp nếu yêu cầu delivery bền vững.
- [ ] Biết rõ Registry completed không có nghĩa consumer đã xử lý.
- [ ] Consumer idempotent và có chiến lược xử lý message lặp, out-of-order, version không hỗ trợ.
- [ ] Nếu cần outbox nâng cao, đã đánh giá mode/implementation tương thích phiên bản.
- [ ] Có metric/log/trace cho publication backlog, broker send error và consumer lag.
- [ ] Module phát không phụ thuộc trực tiếp vào implementation Kafka/Rabbit hoặc module ngoài.
- [ ] `ApplicationModules.verify()`, `@ApplicationModuleTest`, mapping/contract tests và integration tests chạy trong CI.

**Kết luận:** Event externalization đưa một phần application events từ Spring Modulith ra hạ tầng messaging, còn **message contract** quyết định producer và consumer có hiểu nhau qua nhiều phiên bản hay không. Hãy kiểm thử riêng selection, mapping, routing, schema, transaction commit/rollback, gửi broker, recovery và idempotency. Khi kết hợp các kiểm chứng đó với `ApplicationModules.verify()` và `@ApplicationModuleTest`, hệ thống giữ được ranh giới module rõ ràng mà vẫn tích hợp đáng tin cậy với dịch vụ ngoài.

### Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): externalization, broker adapters, annotation, programmatic config, registry và outbox.
- [EventExternalizationConfiguration API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventExternalizationConfiguration.html): `supports`, `map`, `determineTarget` và `getHeadersFor`.
- [RoutingTarget API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/RoutingTarget.html): target, key và builder.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): listener sau commit.

> Lưu ý tương thích: hành vi native externalization, API cấu hình và các outbox integration có thể khác nhau giữa các phiên bản. Các ví dụ ở bài cần được điều chỉnh theo dependency/serializer/transaction manager cụ thể của dự án; bài mới hoàn thành bước biên soạn, chưa thay thế vòng Content QA hoặc chạy integration test thực.
