# Biên giới tin cậy giữa event nội bộ và event tích hợp trong Spring Modulith

Một ứng dụng Spring Boot có thể gồm nhiều module nghiệp vụ như `ordering` (đặt hàng), `notification` (thông báo), `shipping` (vận chuyển) và `billing` (hóa đơn). Các module có thể trao đổi với nhau qua Spring application events. Khi cần gửi thông tin cho hãng vận chuyển, hệ thống kế toán hoặc một microservice độc lập, event còn có thể được chuyển thành message gửi qua broker hoặc API tích hợp.

Chính ở thời điểm **thông tin đi từ môi trường do ứng dụng kiểm soát sang một môi trường có quyền kiểm soát, danh tính và chính sách khác**, chúng ta phải nhận diện **biên giới tin cậy** (*trust boundary*). Nếu coi event nội bộ và event gửi ra ngoài có cùng mức tin cậy, hệ thống dễ vô tình tiết lộ dữ liệu, cho phép giả mạo tác nhân, xử lý payload không hợp lệ, áp dụng sai quyền truy cập hoặc thực hiện lại thao tác khi message bị gửi trùng.

Trong chương **Event nội bộ và tích hợp** của module `SPRING_MODULITH_APPLICATION_EVENTS`, bài này giải thích cách thiết kế các biên giới tin cậy khi tổ chức giao tiếp giữa module Spring Modulith bằng application events. Bối cảnh xuyên suốt là giảm phụ thuộc, bảo vệ ranh giới nghiệp vụ, đồng thời bảo đảm việc publish, listener sau commit, event publication registry, retry, kiểm thử và quan sát được triển khai đúng trách nhiệm.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **ranh giới module**, **ranh giới tiến trình** và **biên giới tin cậy**.
- Xác định khi nào event chỉ là Java object trong cùng JVM và khi nào cần một hợp đồng integration message được kiểm soát.
- Lập sơ đồ các bên phát/nhận, dữ liệu đi qua và quyết định bảo mật cần thực hiện tại từng biên giới.
- Thiết kế adapter xuất event với **danh sách trường cho phép**, tránh rò rỉ JPA entity, thông tin cá nhân và dữ liệu nội bộ.
- Giải thích vai trò của xác thực, phân quyền, TLS, định tuyến broker, kiểm tra schema, xác minh tính toàn vẹn và chống replay.
- Phân biệt **độ tin cậy nghiệp vụ** (reliability) với **độ tin cậy về nguồn gốc và quyền xử lý** (security/trust).
- Lập kế hoạch kiểm thử các tình huống giả mạo nguồn gửi, dữ liệu không hợp lệ, message trùng, consumer lỗi và ranh giới transaction.

## 2. Biên giới tin cậy là gì?

**Biên giới tin cậy** là vị trí nơi dữ liệu, lệnh hoặc yêu cầu chuyển từ một miền kiểm soát sang miền khác, khiến giả định về **danh tính, quyền hạn, tính toàn vẹn và cách xử lý dữ liệu** cần được đánh giá lại.

Ví dụ: một event `OrderPlaced` được phát trong Spring ApplicationContext có thể được listener thuộc `analytics` nhận ngay trong cùng JVM. Khi event ấy được ánh xạ thành JSON và gửi sang message broker, payload đã đi qua một biên giới khác: producer, broker, consumer và người quản trị có thể thuộc các tài khoản, tiến trình hoặc tổ chức riêng.

| Ranh giới | Ý nghĩa | Có tự bảo đảm an toàn không? |
| --- | --- | --- |
| **Application module** | Quy định module nào được phụ thuộc API của module nào | Không. Đây chủ yếu là ranh giới kiến trúc và sở hữu nghiệp vụ |
| **Cùng JVM / Spring ApplicationContext** | Các thành phần cùng chạy trong một tiến trình ứng dụng | Không. Cùng tiến trình không tạo vùng cách ly bảo mật giữa các bean |
| **Tiến trình hoặc container khác** | Có địa chỉ mạng, cấu hình runtime và tài khoản riêng | Không mặc nhiên. Cần cấu hình xác thực, kết nối và quyền |
| **Message broker** | Trung gian vận chuyển, có topic/queue, producer và consumer | Phụ thuộc TLS, identity, ACL, lưu trữ, quyền quản trị và cấu hình |
| **Tổ chức/đối tác bên ngoài** | Miền quản trị, chính sách dữ liệu và phiên bản triển khai khác | Phải xác định hợp đồng, quyền được nhận dữ liệu và quy trình xử lý sự cố |

Điểm cốt lõi: **module boundary không đồng nghĩa với security boundary**. `@ApplicationModule(allowedDependencies = ...)` và `ApplicationModules.verify()` có thể ngăn phụ thuộc Java không mong muốn, nhưng không thay thế authorization ở nghiệp vụ hay authentication tại broker/API.

### Phân biệt ba khái niệm “tin cậy”

| Khái niệm | Câu hỏi thực tế |
| --- | --- |
| **Tin cậy nguồn gửi** | Message này do thành phần nào gửi? Thành phần đó có quyền tuyên bố sự kiện này không? |
| **Tin cậy dữ liệu** | Payload có bị sửa đổi, sai schema, chứa giá trị không hợp lệ hoặc vi phạm quyền truy cập dữ liệu không? |
| **Tin cậy giao nhận** | Publication có thể mất, lặp, sai thứ tự hoặc tồn đọng khi có sự cố không? |

Một message có thể đến **đúng broker và đúng topic** nhưng vẫn chứa dữ liệu sai nghiệp vụ. Ngược lại, một event có payload hợp lệ vẫn có thể bị gửi bởi producer không được cấp quyền. Vì vậy, xác thực danh tính, kiểm tra hợp đồng và xử lý reliability là **những kiểm soát bổ sung nhau**.

## 3. Một luồng nghiệp vụ đi qua nhiều biên giới

Giả sử hệ thống bán hàng phát `OrderReadyToShip` sau khi đơn được xác nhận đủ điều kiện giao. Module `notification` cần biết trạng thái này để gửi thông báo nội bộ, còn hãng vận chuyển là một hệ thống riêng cần nhận yêu cầu giao hàng.

~~~mermaid
flowchart LR
    subgraph JVM["Miền ứng dụng Spring Boot / một JVM"]
      ORD["ordering<br/>OrderReadyToShip"]
      EVT["Spring ApplicationEventPublisher"]
      NOTI["notification<br/>Listener nội bộ"]
      ADP["shipping integration<br/>Adapter + mapping"]
      ORD --> EVT
      EVT --> NOTI
      EVT --> ADP
    end
    subgraph PLATFORM["Miền hạ tầng messaging"]
      MQ[("Broker / queue / topic")]
    end
    subgraph PARTNER["Miền đối tác"]
      EXT["Shipping consumer"]
    end
    ADP -->|"Biên giới A: xuất hợp đồng"| MQ
    MQ -->|"Biên giới B: giao cho đối tác"| EXT
~~~

Các biên giới ở ví dụ gồm:

1. **Trong ứng dụng:** `ordering` công bố event cho `notification` và adapter. Đây là ranh giới sở hữu module và API, trong cùng môi trường Spring.
2. **Từ ứng dụng tới broker:** Java object được chọn lọc, chuyển thành hợp đồng truyền tải và gửi bằng identity của producer.
3. **Từ broker tới consumer của đối tác:** message được cấp quyền đọc, xác thực nguồn theo mô hình tích hợp và kiểm tra lại dữ liệu trước khi thay đổi trạng thái.

Trong từng biên giới, cần đặt câu hỏi: *Ai có thể gửi? Ai được phép nhận? Dữ liệu nào được công bố? Ai được quyền thực hiện hành động khi nhận? Nếu message bị sửa, lặp hoặc chậm thì sao?*

## 4. Event nội bộ có mức tin cậy thế nào?

Spring application event thông thường là **Java object** được publish bằng `ApplicationEventPublisher`. Consumer trong cùng ứng dụng có thể lắng nghe bằng `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener` theo cách triển khai và cấu hình phù hợp.

~~~java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.UUID;

public record OrderReadyToShip(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

~~~java
// Ví dụ trong module ordering.
events.publishEvent(
        new OrderReadyToShip(
                UUID.randomUUID(),
                orderId,
                clock.instant()
        )
);
~~~

Không yêu cầu `OrderReadyToShip` kế thừa `ApplicationEvent`. Event này có thể đi hoàn toàn qua Spring event infrastructure trong cùng JVM, không cần Kafka, RabbitMQ hay JSON.

### Vì sao không nên coi “nội bộ” là “đã an toàn”?

- **Đầu vào nghiệp vụ có thể đến từ bên ngoài.** Nếu HTTP request chứa `orderId`, `customerId` hoặc trạng thái do khách hàng tự khai, service phải kiểm tra quyền và điều kiện nghiệp vụ trước khi phát event.
- **Mã chạy trong cùng JVM có đặc quyền lớn.** Application module là đơn vị tổ chức và ràng buộc phụ thuộc, không phải sandbox an toàn cách ly một thư viện độc hại hay bean bị xâm nhập.
- **Payload nội bộ vẫn cần hợp đồng rõ.** Event mang JPA entity hoặc đối tượng có thể bị thay đổi khiến consumer đọc dữ liệu không nhất quán hoặc làm lộ thuộc tính không cần thiết.
- **Listener có thể gây side effect nghiêm trọng.** Một listener sai có thể gửi dữ liệu cho nhầm người, cập nhật trạng thái sai hoặc gọi một dịch vụ bên ngoài dù event xuất phát từ nội bộ.

**Quy tắc:** kiểm tra quyền tại **điểm ra quyết định nghiệp vụ**, trước khi ghi trạng thái và publish sự kiện. Event không phải cách bỏ qua bước phân quyền; người phát phải bảo đảm một sự thật có quyền và có ý nghĩa thực sự đã xảy ra.

## 5. Bảo vệ ranh giới module trước khi ra ngoài

Spring Modulith giúp đưa phụ thuộc về hợp đồng công khai. Với cách phát hiện module mặc định, package gốc `ordering` là API được công bố; package con chỉ thành API khi được khai báo hợp lệ, ví dụ:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Consumer `notification` có thể giới hạn phụ thuộc:

~~~java
// com/example/shop/notification/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.notification;
~~~

Như vậy, listener có thể dùng `ordering.events.OrderReadyToShip` mà không cần import `ordering.internal.OrderRepository`. Một test kiến trúc có thể xác minh ranh giới này:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void verifiesModules() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra trên đánh giá cấu trúc và phụ thuộc module, **không kiểm tra danh tính producer trên broker** và không chứng minh consumer ngoài hệ thống có quyền truy cập payload. Phân quyền ở nghiệp vụ và xác thực ở các biên giới tích hợp là trách nhiệm khác.

## 6. Nguy cơ khi dùng nguyên event nội bộ làm message tích hợp

Giả sử một entity đơn hàng có dữ liệu sau:

~~~java
// Ví dụ kiểu lưu trữ nội bộ, không phải hợp đồng tích hợp.
class OrderEntity {
    UUID id;
    UUID customerId;
    String customerEmail;
    String shippingAddress;
    String internalFraudScore;
    String staffNote;
}
~~~

Nếu đưa trực tiếp entity này vào event rồi serialize toàn bộ object sang JSON, đối tác có thể nhận cả email, ghi chú nhân viên, điểm rủi ro hoặc quan hệ JPA ngoài mục đích giao hàng. Hệ quả không chỉ là rò rỉ dữ liệu: consumer còn phụ thuộc vào persistence model của ứng dụng, và thay đổi entity có thể làm vỡ schema truyền tải.

### Hợp đồng nội bộ và hợp đồng tích hợp nên có trách nhiệm riêng

| Khía cạnh | Internal event | Integration event |
| --- | --- | --- |
| Đối tượng chính | Các application module trong cùng ứng dụng | Consumer ở tiến trình hoặc tổ chức khác |
| Biểu diễn | Thường là Java record/object | JSON, Avro, Protobuf hoặc định dạng thống nhất qua hệ thống truyền tải |
| Khả năng đổi schema | Thường nâng cấp cùng bản build | Có thể cần hỗ trợ đồng thời nhiều phiên bản consumer |
| Dữ liệu | Dữ liệu vừa đủ cho nghiệp vụ trong ứng dụng | Chỉ các trường cần thiết và được phép vượt biên giới |
| Danh tính bên nhận | Listener Java theo cấu hình Spring | Identity mạng/broker, ACL, quyền tiêu thụ |
| Kiểm soát bắt buộc | Module API, quyền nghiệp vụ, transaction | Thêm authn/authz, TLS, schema, dữ liệu nhạy cảm, replay, rate limit |

Một sự thật nghiệp vụ có thể được mô tả bằng cả hai hợp đồng, nhưng **không nhất thiết dùng chung class và serializer**. Adapter là nơi chủ động ánh xạ giữa hai bên.

## 7. Lập danh sách dữ liệu được phép vượt biên giới

**Data minimization** nghĩa là chỉ đưa dữ liệu cần thiết cho mục đích đã định qua biên giới. Không nên mặc định “có dữ liệu trong event nội bộ” đồng nghĩa “mọi consumer ngoài đều được nhận”.

Ví dụ với đối tác vận chuyển:

| Trường | Internal event | Gửi cho đối tác? | Lý do |
| --- | --- | --- | --- |
| `eventId` | Có | Có | Hỗ trợ truy vết và idempotency |
| `orderId` nội bộ | Có | Cân nhắc | Có thể lộ cấu trúc hệ thống; ưu tiên mã tham chiếu bên ngoài |
| `externalShipmentRef` | Từ adapter | Có | Mã định danh nghiệp vụ hợp lệ cho đối tác |
| `occurredAt` | Có | Có nếu cần | Hỗ trợ quy tắc thời gian và kiểm tra độ trễ |
| `customerEmail` | Có thể có ở module khác | Không mặc định | Chỉ gửi khi thật sự cần, có cơ sở và quyền xử lý |
| `shippingAddress` | Lưu trong nghiệp vụ | Chỉ qua kênh được kiểm soát nếu cần | Thông tin cá nhân; hạn chế phân phối rộng qua topic |
| `internalFraudScore` | Chỉ nội bộ | Không | Không thuộc mục đích giao hàng |
| `staffNote` | Chỉ nội bộ | Không | Có nguy cơ chứa thông tin nhạy cảm và không liên quan |

Nếu đối tác cần địa chỉ giao hàng, có thể cung cấp bằng **API có xác thực và phân quyền riêng** sử dụng mã tham chiếu, hoặc đưa một tập trường được phép vào message trên kênh đã phân quyền chặt. Lựa chọn phụ thuộc mục đích, thời gian lưu trữ và chính sách dữ liệu của hệ thống.

Đặc biệt với hệ thống nhiều tenant, **tenant ID trong message không tự chứng minh quyền truy cập**. Consumer phải đối chiếu identity đã xác thực, quyền trên tài nguyên và mối quan hệ tenant trước khi hiển thị hoặc thay đổi dữ liệu. Không được tin một tenant ID chỉ vì nó có trong JSON.

## 8. Adapter: nơi chuyển đổi hợp đồng và thực hiện kiểm soát

Một kiến trúc có thể bố trí adapter xuất event trong module tích hợp riêng. Module `ordering` vẫn phát event nội bộ; adapter chịu trách nhiệm chọn lọc thông tin, ánh xạ sang hợp đồng ngoài và gọi thành phần gửi message.

~~~text
ordering.internal
    -> publish OrderReadyToShip (internal event)
    -> shippingintegration.internal.ShippingEventBridge
    -> map sang ShipmentRequestedV1 (hợp đồng ngoài)
    -> ShippingMessageSender
    -> broker/queue/topic của đối tác
~~~

### 8.1. Định nghĩa hợp đồng tích hợp riêng

~~~java
package com.example.shop.shippingintegration.contract;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record ShipmentRequestedV1(
        UUID eventId,
        String eventType,
        int schemaVersion,
        String shipmentReference,
        Instant occurredAt
) {
    public ShipmentRequestedV1 {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(eventType, "eventType");
        Objects.requireNonNull(shipmentReference, "shipmentReference");
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (schemaVersion != 1
                || !"shipment.requested".equals(eventType)
                || shipmentReference.isBlank()) {
            throw new IllegalArgumentException("Invalid integration contract");
        }
    }
}
~~~

`ShipmentRequestedV1` là **hợp đồng minh họa do ứng dụng thiết kế**, không phải định dạng mặc định Spring Modulith tự tạo. `shipmentReference` là mã tham chiếu dành cho đối tác, tách biệt với ID database nội bộ. Không đưa trực tiếp địa chỉ, email hoặc ghi chú vào contract khi đối tác chưa có quyền và nhu cầu sử dụng những dữ liệu đó.

### 8.2. Ánh xạ từ internal event sang contract ngoài

~~~java
package com.example.shop.shippingintegration.internal;

import com.example.shop.ordering.events.OrderReadyToShip;
import com.example.shop.shippingintegration.contract.ShipmentRequestedV1;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingEventBridge {

    private final ShipmentReferenceService references;
    private final ShippingMessageSender sender;

    ShippingEventBridge(
            ShipmentReferenceService references,
            ShippingMessageSender sender
    ) {
        this.references = references;
        this.sender = sender;
    }

    @ApplicationModuleListener
    void on(OrderReadyToShip event) {
        String externalRef =
                references.requireAuthorizedReference(event.orderId());

        ShipmentRequestedV1 message = new ShipmentRequestedV1(
                event.eventId(),
                "shipment.requested",
                1,
                externalRef,
                event.occurredAt()
        );

        sender.send(message);
    }
}
~~~

`ShipmentReferenceService` và `ShippingMessageSender` là **abstraction ví dụ phải được ứng dụng triển khai**. `requireAuthorizedReference(...)` cần dùng API hợp lệ, xác minh trạng thái được phép gửi đi và ánh xạ mã tham chiếu cho đúng đối tác; tên method không tự mang đến cơ chế bảo mật. `sender.send(...)` chịu trách nhiệm truyền message trên kết nối được cấu hình an toàn và báo lỗi đúng cách.

`@ApplicationModuleListener` cung cấp mô hình xử lý sau commit, bất đồng bộ và transaction riêng theo cơ chế/cấu hình Spring Modulith tương ứng. **Tách listener sau commit không đồng nghĩa việc gửi message và ghi nhận đã gửi là một thao tác nguyên tử**; cần xem xét failure window, registry và cơ chế retry riêng.

### 8.3. Payload truyền đi sẽ trông như thế nào?

~~~json
{
  "eventId": "e45a822e-57a1-4cf5-8d4b-879dafb01c51",
  "eventType": "shipment.requested",
  "schemaVersion": 1,
  "shipmentReference": "SHP-8A13F2",
  "occurredAt": "2026-11-25T08:15:00Z"
}
~~~

Đây là **JSON ví dụ do adapter serialize**. Trên thực tế có thể cần thêm key phân vùng, identity/issuer, correlation ID và metadata vận chuyển. Những trường đó phải được định nghĩa rõ ý nghĩa; **không coi header tự khai trong payload là bằng chứng xác thực**.

## 9. Xác thực và phân quyền ở biên giới broker

Khi message rời JVM, hạ tầng tích hợp phải xác định được **ai được gửi, ai được đọc và ai được quản trị**. Các kiểm soát điển hình:

| Kiểm soát | Mục đích | Sai lầm thường gặp |
| --- | --- | --- |
| **TLS cho đường truyền** | Bảo vệ kết nối khỏi nghe lén và sửa đổi trên đường truyền, theo cấu hình xác thực endpoint | Dùng kết nối không mã hóa hoặc bỏ xác minh chứng chỉ |
| **Xác thực producer/consumer** | Nhận diện ứng dụng kết nối bằng cơ chế broker hỗ trợ như SASL, mTLS, OAuth | Dùng chung một tài khoản cho mọi dịch vụ |
| **ACL theo topic/queue** | Chỉ cho phép producer gửi và consumer đọc đúng tài nguyên | Cấp quyền wildcard cho toàn bộ broker |
| **Tách identity môi trường** | Ngăn dev/staging/production hoặc các đối tác dùng nhầm quyền | Dùng chung credential và namespace giữa môi trường |
| **Quản lý secrets** | Bảo vệ và luân chuyển khóa/chứng chỉ/token | Đưa credential vào code hoặc log |
| **Kiểm soát dữ liệu lưu trong broker** | Giới hạn người có thể truy cập bản lưu, backup và DLQ | Chỉ bảo vệ kết nối mà bỏ qua dữ liệu lưu trữ |
| **Audit thay đổi quyền** | Phát hiện quyền gửi/đọc bị mở rộng ngoài dự kiến | Không theo dõi cấp quyền và thao tác của tài khoản đặc quyền |

Các công nghệ có cách cấu hình khác nhau: Kafka, RabbitMQ hoặc một dịch vụ cloud queue không sử dụng cùng một cơ chế ACL và xác thực. Tên công nghệ không thay thế việc **chứng minh cấu hình quyền thực tế**.

### Xác thực broker chưa chắc là xác thực end-to-end

Broker có thể xác thực producer tại thời điểm nhận message, nhưng consumer đôi khi chỉ thấy **topic và payload**, không có chứng cứ mật mã end-to-end cho từng thông điệp. Nếu mô hình đe dọa bao gồm broker trung gian không đáng tin cậy, nhiều producer dùng chung topic hoặc yêu cầu chứng minh nguồn gửi cho đối tác, có thể cần **chữ ký thông điệp/MAC và quy tắc xác minh có quản lý khóa**, ngoài TLS.

Không nên tùy tiện coi một header `producerName = "ordering"` là chứng cứ danh tính. Giá trị do sender tự khai có thể bị giả mạo nếu không được ràng buộc với credential hoặc cơ chế xác minh thực tế.

## 10. Consumer ngoài phải kiểm tra lại dữ liệu nhận vào

Khi message đi vào một ứng dụng khác, consumer phải coi payload là **dữ liệu từ một nguồn bên ngoài tiến trình**, dù producer dự kiến là hệ thống nội bộ của công ty.

Các bước xử lý nên có thứ tự:

1. **Xác minh kênh và danh tính:** kết nối/message đến qua nguồn đã được xác thực và được phép publish loại sự kiện này.
2. **Giải mã có giới hạn:** giới hạn kích thước message, độ sâu cấu trúc và tài nguyên parser để tránh payload gây cạn kiệt tài nguyên.
3. **Kiểm tra schema/version:** event type và version được hỗ trợ, các trường bắt buộc đúng kiểu và cấu trúc.
4. **Kiểm tra ngữ nghĩa:** dữ liệu tham chiếu tồn tại, có quan hệ tenant/đối tác hợp lệ, trạng thái chuyển đổi được phép.
5. **Kiểm tra trùng và thứ tự:** áp dụng khóa idempotency, phiên bản aggregate hoặc thứ tự theo nghiệp vụ khi cần.
6. **Thực hiện side effect có transaction phù hợp:** chỉ đánh dấu hoàn tất sau khi nghiệp vụ xử lý thành công theo quy tắc vận hành.

Ví dụ hợp đồng nhận callback từ hãng vận chuyển:

~~~java
package com.example.shop.shippingintegration.contract;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record ShipmentAcceptedV1(
        UUID eventId,
        String shipmentReference,
        Instant acceptedAt
) {
    public ShipmentAcceptedV1 {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(shipmentReference);
        Objects.requireNonNull(acceptedAt);

        if (shipmentReference.isBlank()) {
            throw new IllegalArgumentException("Missing shipment reference");
        }
    }
}
~~~

Record constructor giúp bảo vệ một phần bất biến của dữ liệu, **không xác thực được ai đã gửi**. Đặc biệt, không xử lý trực tiếp `shipmentReference` như “quyền được sửa trạng thái”:

~~~java
// Pseudocode cho consumer biên giới, không phải API sẵn có của Spring Modulith.
void handle(AuthenticatedPartner identity, ShipmentAcceptedV1 message) {
    authorization.requireCanUpdateShipment(
            identity,
            message.shipmentReference()
    );
    deduplication.processOnce(
            identity.partnerId(),
            message.eventId(),
            () -> shipments.accept(
                    message.shipmentReference(),
                    message.acceptedAt()
            )
    );
}
~~~

`AuthenticatedPartner` phải xuất phát từ **cơ chế xác thực đáng tin cậy** của kết nối hoặc thông điệp, không dựng bằng một trường `partnerId` chưa được xác minh trong payload. Các interface trong pseudocode là trách nhiệm ứng dụng, cần triển khai cùng transaction và ràng buộc dữ liệu thích hợp.

## 11. Tính toàn vẹn, chống giả mạo và chống replay

Một message có cấu trúc JSON hợp lệ vẫn có thể nguy hiểm nếu người không có quyền có thể tạo nó, sửa giá trị hoặc gửi lại nhiều lần.

### 11.1. Nguồn gửi được xác thực

- Chỉ cấp quyền publish loại event cho **service identity** thực sự sở hữu sự kiện.
- Ghi lại identity producer đã được xác thực ở hạ tầng, không dựa vào `source` tự khai.
- Với giao tiếp xuyên tổ chức có yêu cầu cao, cân nhắc chữ ký/MAC trên dạng message chuẩn hóa và chính sách luân chuyển khóa.
- Tách quyền đọc, ghi và quản trị; không cấp quyền tiêu thụ dữ liệu khách hàng cho consumer không có nhu cầu.

### 11.2. Chống phát lại và xử lý trùng

Ví dụ một message `ShipmentAcceptedV1(eventId=E-5)` bị gửi lại:

~~~text
Message E-5 -> consumer -> cập nhật trạng thái thành ACCEPTED
Message E-5 -> consumer -> phát hiện đã xử lý -> không cập nhật lần nữa
~~~

Consumer có thể dùng khóa `(authenticatedProducer, eventId)` hoặc `(consumerName, eventId)` theo cách định danh nguồn của hệ thống. Kết hợp **unique constraint và transaction cập nhật nghiệp vụ** giúp hai consumer worker cạnh tranh không đồng thời áp dụng cùng event.

Nếu một hành động được phép xảy ra nhiều lần ở các mốc khác nhau (ví dụ một shipment có nhiều cập nhật trạng thái hợp lệ), chỉ dedupe bằng `shipmentReference` sẽ sai: phải phân biệt **ID sự kiện**, **định danh đối tượng** và **phiên bản/trạng thái**.

### 11.3. Chống replay không chỉ là “đã xử lý chưa?”

Với message chứa hành động nhạy cảm, có thể cần kiểm tra **thời hạn chấp nhận, thời gian sự kiện, nonce hoặc version nghiệp vụ** cùng identity đã xác thực. Tuy nhiên:

- Timestamp đơn thuần không chứng minh message hợp lệ; đồng hồ các hệ thống có thể lệch.
- Event cũ có thể cần được xử lý lại hợp pháp để khôi phục sau sự cố; chính sách chống replay không được vô tình chặn mọi retry hợp lệ.
- Deduplication cần có chính sách lưu giữ đủ dài cho khoảng thời gian hệ thống có thể phát lại event.

Quy tắc cần dựa trên loại sự kiện: một callback “thực hiện thanh toán” đòi hỏi cơ chế chặt hơn một event “đã thay đổi trạng thái” phục vụ báo cáo.

## 12. Độ tin cậy giao nhận khác với độ tin cậy nguồn dữ liệu

Spring Modulith có thể sử dụng **Event Publication Registry** để theo dõi việc publication đã được xử lý hay còn dang dở khi các dependency và storage thích hợp được cấu hình. Điều này phục vụ **reliability**, giúp phát hiện tình huống listener thất bại và hỗ trợ chiến lược xử lý lại.

Tuy nhiên, các vấn đề dưới đây khác nhau:

| Vấn đề | Kiểm soát chủ yếu |
| --- | --- |
| Listener không xử lý vì ứng dụng dừng | Lưu publication/khôi phục, retry theo chính sách |
| Producer không có quyền gửi vào topic | Identity producer + ACL broker |
| Payload chứa dữ liệu khách hàng không được chia sẻ | Adapter lọc trường + phân quyền dữ liệu |
| Message bị sửa hoặc giả mạo | Kênh tin cậy, xác thực, kiểm tra integrity/chữ ký nếu cần |
| Retry khiến gửi hai yêu cầu giao hàng | Idempotency ở adapter, broker/consumer và API đối tác |
| Consumer xử lý event sai trạng thái nghiệp vụ | Validation, authorization và state machine |
| Message lỗi định dạng liên tục bị retry | Phân loại lỗi, DLQ/quarantine, cảnh báo và quy trình xử lý |

`@Async` hoặc xử lý sau commit **không phải biên giới bảo mật** và cũng không tự bảo đảm message đã được lưu bền. Retry không tự giải quyết thông tin sai hoặc nguồn gửi chưa được xác thực; thậm chí có thể khuếch đại tác động của message độc hại nếu không giới hạn.

### 12.1. Cửa sổ lỗi sau commit

Xét trình tự:

~~~mermaid
sequenceDiagram
    participant O as ordering
    participant DB as Local database
    participant B as Shipping adapter
    participant MQ as Broker
    O->>DB: Ghi đơn hàng
    O->>O: Publish OrderReadyToShip
    O->>DB: Commit transaction
    DB-->>B: Listener AFTER_COMMIT
    B->>MQ: Gửi ShipmentRequestedV1
    MQ-->>B: Xác nhận nhận
    Note over B,MQ: Crash có thể xảy ra trước khi ghi completion
~~~

Nếu broker đã nhận message nhưng adapter chưa kịp ghi publication hoàn tất, lần retry tiếp theo có thể gửi lại message. Nếu adapter không bao giờ gửi được, có thể cần cơ chế khôi phục publication. **Một transaction database local không tự động bao trùm commit của broker**.

Khi có yêu cầu tính bền vững cao, cần cân nhắc Event Publication Registry theo cấu hình phù hợp, transactional outbox hoặc cơ chế chuyên biệt cho broker, đồng thời thiết kế consumer idempotent. Không nên tuyên bố exactly-once chỉ vì có registry hoặc sau commit.

### 12.2. Phân loại retry theo nguyên nhân

| Nhóm lỗi | Ví dụ | Phương án thường phù hợp |
| --- | --- | --- |
| **Tạm thời** | Broker timeout, đối tác quá tải | Retry giới hạn, exponential backoff, jitter |
| **Hợp đồng không tương thích** | `schemaVersion = 99` không được hỗ trợ | Không retry vô hạn; đưa vào quarantine/DLQ để điều tra |
| **Không được cấp quyền** | Producer sai ACL, consumer thiếu quyền tài nguyên | Từ chối, ghi audit; sửa cấu hình/quyền sau xác minh |
| **Sai nghiệp vụ** | Chuyển trạng thái từ DELIVERED về CREATED | Từ chối hoặc xử lý theo state machine, không áp dụng bừa |
| **Message trùng** | `eventId` đã hoàn tất | Bỏ qua an toàn và xác nhận theo chính sách |

DLQ không phải nơi chứa dữ liệu miễn kiểm soát: cần giới hạn quyền đọc, chính sách lưu giữ, mã hóa và quy trình xem xét thủ công vì message lỗi có thể vẫn chứa dữ liệu nhạy cảm.

## 13. Biên giới tin cậy và dữ liệu nhạy cảm

Việc đưa event qua broker thường làm tăng **số bản sao dữ liệu**: log producer, bộ nhớ broker, bản lưu topic, DLQ, log consumer, trace và hệ thống giám sát. Mỗi bản sao là một vị trí phải xem xét quyền truy cập và thời gian lưu giữ.

### Hướng thiết kế thực tế

1. **Cho phép theo trường:** adapter tạo contract ngoài từ danh sách trường đã được duyệt, thay vì serialize object nội bộ rồi cố gắng xóa trường.
2. **Tách dữ liệu định danh khỏi dữ liệu nghiệp vụ:** dùng mã tham chiếu cho đối tác nếu đủ, và cung cấp dữ liệu chi tiết qua API được bảo vệ khi thật sự cần.
3. **Không đưa secret vào event:** password, API key, access token và private key không thuộc event payload. Nếu cần token cho một workflow, phải đánh giá riêng việc cấp phát, thời hạn, audience và bảo vệ nó.
4. **Giới hạn log:** log ID an toàn, event type, mã lỗi và trạng thái xử lý; tránh log raw payload chứa thông tin cá nhân.
5. **Bảo vệ bản lưu:** ACL, encryption at rest khi phù hợp, retention và quyền backup/DLQ phải nhất quán với phân loại dữ liệu.
6. **Quy trình xóa/thu hồi:** đối tác và hạ tầng có thể giữ message lâu hơn ứng dụng; yêu cầu về retention và xóa dữ liệu cần được tính từ lúc thiết kế.

### Dữ liệu nhiều tenant

Nếu cùng một topic chứa message của nhiều tenant, một consumer được cấp quyền đọc topic có thể **nhìn thấy dữ liệu của mọi tenant trên topic đó**, trừ khi có cơ chế cô lập bổ sung. Kiểm tra `tenantId` ở code là cần thiết nhưng không thể bù lại một thiết kế quyền đọc rộng trong môi trường có yêu cầu tách biệt cao.

Các lựa chọn có thể gồm topic/queue riêng theo trust domain, ACL chi tiết, mã hóa payload theo người nhận hoặc thay đổi cách phân phối dữ liệu. Cần quyết định dựa trên số lượng tenant, chi phí vận hành và yêu cầu cô lập thực tế.

## 14. Biên giới tích hợp đi vào hệ thống

Không chỉ sự kiện **đi ra** cần bảo vệ. Khi hệ thống nhận event từ đơn vị vận chuyển, ngân hàng hoặc ứng dụng bên ngoài, đó là luồng **đi vào** từ một trust domain khác.

Một adapter nhận message nên đi theo các bước:

~~~mermaid
flowchart TD
    A["Nhận message ngoài"] --> B["Xác thực nguồn / kênh"]
    B --> C{"Có quyền gửi loại event?"}
    C -->|Không| X["Từ chối + audit"]
    C -->|Có| D["Parse có giới hạn + validate schema"]
    D --> E{"Payload hợp lệ?"}
    E -->|Không| Q["Quarantine / DLQ có kiểm soát"]
    E -->|Có| F["Kiểm tra tenant, tài nguyên, trạng thái"]
    F --> G{"Được phép chuyển trạng thái?"}
    G -->|Không| X
    G -->|Có| H["Dedupe và thực hiện nghiệp vụ"]
    H --> I["Ghi kết quả / xác nhận xử lý"]
~~~

Đặc biệt, **việc message đến đúng topic không đồng nghĩa consumer được phép ghi trực tiếp vào database của module nghiệp vụ**. Adapter nên chuyển dữ liệu đã kiểm tra thành lời gọi API/command hợp lệ của module sở hữu nghiệp vụ; module đích tiếp tục áp dụng invariant và authorization cần thiết.

Nếu nghiệp vụ nội bộ sau đó cần phát event như `ShipmentAccepted`, module sở hữu trạng thái nên publish sau khi xác nhận chuyển đổi hợp lệ. Không để callback ngoài tự giả mạo domain event đã được xác nhận.

## 15. Event contract và khả năng tương thích khi vượt biên giới

Event nội bộ thường được xây dựng và triển khai cùng phiên bản ứng dụng. Integration message có thể được consumer cũ đọc trong lúc producer đã nâng cấp.

| Thay đổi | Trong một bản build Spring Modulith | Qua broker/đối tác độc lập |
| --- | --- | --- |
| Thêm trường mới | Có thể cần cập nhật constructor và các caller | Cần quy tắc optional/default và khả năng đọc của consumer cũ |
| Đổi tên trường | Có thể gây lỗi compile | Có thể làm consumer cũ không parse được |
| Đổi ngữ nghĩa nhưng giữ kiểu | Có thể qua compile mà sai logic | Đặc biệt nguy hiểm vì lỗi âm thầm ở nhiều hệ thống |
| Đổi tên event/topic | Cập nhật listener nội bộ | Cần migration, routing và thời gian hỗ trợ song song |
| Đổi serializer | Trong JVM có thể không ảnh hưởng event | Có thể phá vỡ toàn bộ consumer tích hợp |

Với integration events, nên định nghĩa **event type**, **schema version**, tập trường và các quy tắc tương thích. Có thể dùng schema registry hoặc hợp đồng dữ liệu tùy công nghệ, cùng các bài consumer contract test.

### Cảnh báo về dữ liệu mặc định

Không tự mặc định giá trị nhạy cảm hoặc mang ý nghĩa nghiệp vụ nghiêm trọng. Ví dụ, thiếu `customerConsent` không được tự coi là `true`; thiếu tenant ID không được mặc định một tenant chung. Với phiên bản cũ thiếu trường, consumer cần chính sách từ chối, fallback được nghiệp vụ chấp thuận hoặc chuyển đổi schema rõ ràng.

## 16. Ma trận đe dọa và kiểm soát

| Tình huống | Hệ quả | Kiểm soát quan trọng |
| --- | --- | --- |
| Service không liên quan publish `ShipmentAccepted` giả | Giao hàng bị đổi trạng thái không hợp lệ | Producer identity, ACL, authorization và kiểm tra state machine |
| Adapter serialize nguyên `OrderEntity` | Lộ email, địa chỉ, ghi chú | DTO ngoài với allowlist; kiểm thử không rò rỉ trường |
| Message bị sửa trên đường truyền | Consumer hành động theo dữ liệu giả | TLS có xác thực, integrity; chữ ký/MAC khi yêu cầu end-to-end |
| Header tự khai `tenantId` sai | Rò rỉ hoặc sửa dữ liệu tenant khác | Ràng buộc tenant với danh tính đã xác thực và quyền tài nguyên |
| Event được gửi lại sau crash | Tạo hai shipment/ghi nhận hai lần | Stable event ID, idempotency, unique constraint |
| Message malformed hoặc oversized | Lỗi parser, cạn kiệt tài nguyên | Kích thước tối đa, validation schema, quarantine |
| Retry liên tục message không thể xử lý | Backlog và làm nghẽn hệ thống | Phân loại lỗi, backoff, DLQ, cảnh báo |
| Consumer cũ đọc message schema mới | Mất dữ liệu hoặc hiểu sai | Versioning, compatibility tests, triển khai chuyển tiếp |
| Log raw payload ở production | Rò rỉ dữ liệu qua log/trace | Redaction, giới hạn trường và retention |
| Broker/topic có quyền đọc quá rộng | Dữ liệu ngoài phạm vi bị sao chép | Least privilege, cô lập trust domain, kiểm tra ACL |

Ma trận này giúp thiết kế dựa trên **mối đe dọa cụ thể**, tránh giả định dùng một công nghệ sẽ tự giải quyết mọi vấn đề. Chẳng hạn TLS bảo vệ đường truyền nhưng không thay thế kiểm tra nghiệp vụ; registry giúp recovery nhưng không xác minh nguồn message.

## 17. Kiểm thử biên giới tin cậy

Nên chia bộ kiểm thử theo nơi đặt kiểm soát và loại bằng chứng cần thu thập.

### 17.1. Test kiến trúc trong Spring Modulith

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này xác minh quan hệ phụ thuộc tĩnh, ví dụ `shippingintegration` không import class trong `ordering.internal` khi API đó chưa được công bố. Nó **không** xác minh TLS, broker ACL hay payload được mã hóa.

### 17.2. Test mapping của adapter

Với `OrderReadyToShip` đầu vào, cần kiểm tra:

- `ShipmentRequestedV1` có đúng event ID, schema version và mã tham chiếu đối tác.
- Contract ngoài **không có** `customerEmail`, `internalFraudScore` và `staffNote`.
- Mapper từ chối đơn hàng không đủ điều kiện gửi hoặc mã tham chiếu không hợp lệ.
- Một event được xử lý lại vẫn dùng cùng event ID; mã tham chiếu không đổi theo từng lần thử nếu nghiệp vụ yêu cầu.

Ví dụ assertion bằng Jackson cho một thông điệp đã serialize:

~~~java
// Minh họa assertion; "json" đến từ serializer tích hợp trong test.
JsonNode payload = objectMapper.readTree(json);

assertThat(payload.path("schemaVersion").asInt()).isEqualTo(1);
assertThat(payload.path("eventType").asText())
        .isEqualTo("shipment.requested");
assertThat(payload.has("customerEmail")).isFalse();
assertThat(payload.has("internalFraudScore")).isFalse();
assertThat(payload.has("staffNote")).isFalse();
~~~

Test này chỉ kiểm tra các trường được nêu. Trong dự án thật cần kết hợp schema test và danh sách trường cho phép, tránh một field nhạy cảm mới bị đưa vào payload mà test cũ không nhận biết.

### 17.3. Test bảo mật tại broker/API

Các kịch bản có giá trị:

1. Credential của service **không được cấp quyền** không thể publish vào topic vận chuyển.
2. Consumer không được phép không thể đọc topic hoặc gọi API chi tiết đơn hàng.
3. Chứng chỉ/credential không hợp lệ bị từ chối; kết nối phải dùng cấu hình TLS mong muốn.
4. Message sai schema hoặc mang giá trị không hợp lệ bị từ chối, không tạo side effect.
5. Đối tác A không thể dùng tham chiếu của đối tác B để thay đổi shipment.
6. Message cũ, message trùng và message sai thứ tự được xử lý theo chính sách đã công bố.
7. DLQ và dashboard không cho tài khoản không liên quan đọc dữ liệu nhạy cảm.

### 17.4. Test giao nhận tin cậy

Giả lập producer commit đơn hàng nhưng adapter thất bại khi gửi broker; cần chứng minh publication được phát hiện và xử lý lại theo cơ chế đã cấu hình. Giả lập broker đã nhận nhưng adapter bị crash trước khi ghi completion; consumer phải tránh tạo shipment trùng.

Với listener `AFTER_COMMIT`, kiểm tra cả trường hợp transaction nguồn rollback: event chưa có hiệu lực nghiệp vụ thì **không được xuất ra đối tác**. Một test tự gắn `@Transactional` rồi rollback ở cuối có thể không kích hoạt listener sau commit; khi cần test commit thực, phải chủ động thiết lập transaction boundary và cơ chế chờ async.

## 18. Quan sát, audit và xử lý sự cố theo biên giới

Một event đi qua ba hệ thống có thể thành công ở publisher nhưng thất bại tại broker hoặc consumer. Mỗi bước cần ghi nhận đủ dữ liệu để xác định **đã qua biên giới nào**, **do identity nào thực hiện** và **đang thất bại ở đâu**.

| Vị trí | Thông tin quan sát hữu ích |
| --- | --- |
| Publisher | Event ID, loại sự kiện, aggregate ID, thời điểm nghiệp vụ, kết quả transaction |
| Adapter | Phiên bản contract ngoài, event ID, route/target, kết quả mapping, thời gian thử |
| Broker | Identity producer/consumer, topic/queue, lỗi authn/authz, độ trễ, retry, DLQ |
| External consumer | Event ID, nguồn đã xác thực, trạng thái validation, idempotency, kết quả nghiệp vụ |
| Registry/recovery | Publication đang chờ, đã hoàn tất, thất bại, số lần thử và thời gian tồn đọng |

Một số chỉ số gợi ý: tỷ lệ message bị từ chối do xác thực, số payload sai schema, số message bị dedupe, số publication chưa hoàn tất, thời gian từ commit tới khi partner xác nhận và số sự kiện nằm trong DLQ.

Tránh biến observability thành một kênh rò rỉ dữ liệu. Không log raw credential, chữ ký bí mật, địa chỉ đầy đủ hoặc payload không được làm sạch. Log correlation ID giúp liên kết sự cố; nó **không phải bằng chứng danh tính**.

### Khi xảy ra sự cố

Nếu phát hiện message không hợp lệ hoặc bị giả mạo:

1. Xác định identity và kênh thực sự đã gửi message từ log hạ tầng đáng tin cậy.
2. Cô lập credential hoặc route có vấn đề theo quy trình vận hành.
3. Xác định event nào đã được consumer áp dụng, event nào đang chờ hoặc ở DLQ.
4. Chỉ phát lại message đã được xác minh hợp lệ; bảo vệ thao tác replay bằng quyền và audit.
5. Khôi phục trạng thái nghiệp vụ qua quy trình được định nghĩa, không trực tiếp sửa dữ liệu từ một payload chưa được tin cậy.

## 19. Bài thực hành: đánh dấu và kiểm soát ba biên giới tin cậy

**Bối cảnh:** Ứng dụng có `ordering`, `notification`, `shippingintegration`. Module `ordering` phát `OrderReadyToShip` khi đơn đủ điều kiện. Adapter chuyển thông tin tới broker để đối tác vận chuyển nhận và trả về `ShipmentAcceptedV1`.

### Phần A — Vẽ sơ đồ và xác định giả định

Vẽ ba miền: JVM nội bộ, messaging platform và hệ thống đối tác. Ghi rõ ai sở hữu mỗi thành phần; identity nào publish/consume; dữ liệu nào đi qua biên giới; tổ chức nào quản lý credential và retention.

Đặt câu hỏi: liệu `@NamedInterface("events")` đã đủ bảo vệ topic broker hay chưa? Giải thích vì sao kiểm tra ranh giới kiến trúc và xác thực broker là hai trách nhiệm khác nhau.

### Phần B — Thiết kế hai contract

1. Viết `OrderReadyToShip(UUID eventId, UUID orderId, Instant occurredAt)` ở API sự kiện của `ordering`.
2. Viết `ShipmentRequestedV1` có event ID, schema version, event type, mã shipment reference và thời gian.
3. Thiết kế adapter chuyển đổi từ event nội bộ sang contract ngoài; không truy cập repository nội bộ của `ordering` từ module khác.
4. Liệt kê những trường của `OrderEntity` **không được gửi** và lý do.
5. Nếu đối tác cần địa chỉ, mô tả một API lấy dữ liệu có xác thực, phân quyền theo shipment reference và chính sách lưu giữ.

### Phần C — Tạo tình huống tấn công và lỗi

1. Dùng credential không có quyền để gửi vào topic vận chuyển; kỳ vọng broker từ chối.
2. Thay `shipmentReference` bằng tham chiếu của một đối tác khác; consumer phải từ chối khi không có quyền.
3. Gửi message có `schemaVersion = 99` hoặc thiếu event ID; consumer phải xử lý như lỗi hợp đồng.
4. Gửi lại message hợp lệ cùng event ID hai lần; chỉ một thay đổi nghiệp vụ được áp dụng.
5. Giả lập broker timeout sau commit và adapter retry; kiểm tra trạng thái publication và idempotency.
6. Kiểm tra log/DLQ không chứa trường nhạy cảm ngoài chính sách đã chấp thuận.

### Phần D — Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Module không phụ thuộc implementation của nhau | `ApplicationModules.verify()` PASS |
| Dữ liệu xuất được lọc theo hợp đồng | Schema/mapping test PASS, không lộ trường nhạy cảm |
| Producer/consumer có quyền phù hợp | Negative authn/authz test PASS |
| Payload từ ngoài được xác minh | Sai schema/tenant/trạng thái bị từ chối |
| Giao nhận phục hồi được khi lỗi tạm thời | Publication/retry có trạng thái và kết quả quan sát được |
| Xử lý trùng an toàn | Test cùng event ID không tạo side effect thứ hai |
| Có thể điều tra mà không lộ dữ liệu | Audit/log theo định danh an toàn; kiểm soát retention/DLQ |

## 20. Những hiểu nhầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Hai module cùng JVM là hai miền bảo mật tách biệt.” | Module boundary chủ yếu là quy tắc kiến trúc; cùng JVM không tạo sandbox giữa các module |
| “Đã có `allowedDependencies` thì không cần authorization.” | Quy định import không xác minh quyền người dùng hoặc quyền producer/consumer |
| “Event nội bộ an toàn nên cứ serialize nguyên object gửi broker.” | Dữ liệu phải được phân loại, lọc và ánh xạ thành hợp đồng phù hợp với người nhận |
| “Có TLS thì mọi message đều đáng tin.” | TLS bảo vệ kết nối; schema, quyền nghiệp vụ và idempotency vẫn cần được kiểm tra |
| “Header `source` chứng minh ai gửi event.” | Header tự khai chỉ là dữ liệu; phải gắn với cơ chế xác thực thực tế |
| “Event Publication Registry tự chống giả mạo.” | Registry phục vụ theo dõi publication/reliability; không thay authn/authz |
| “`@Async` khiến event được giao bền vững.” | Async không mặc nhiên lưu bền hoặc retry sau crash |
| “Consumer nhận message rồi có quyền sửa mọi shipment.” | Phải xác thực nguồn, phân quyền theo tài nguyên và kiểm tra trạng thái hợp lệ |
| “Một lần xử lý thành công nghĩa là sẽ không bao giờ nhận lại.” | Retry và failure window có thể tạo message trùng; consumer cần idempotency |
| “DLQ chỉ chứa dữ liệu lỗi nên không cần bảo vệ.” | DLQ vẫn có thể chứa dữ liệu nhạy cảm và payload độc hại |

## 21. Tự kiểm tra kiến thức

**Câu 1. Vì sao ranh giới module Spring Modulith không tương đương biên giới tin cậy?**

Vì module boundary kiểm soát quan hệ phụ thuộc và quyền truy cập API ở mức kiến trúc; nó không cung cấp cách ly bảo mật trong cùng JVM, không xác thực người gửi qua mạng và không thay thế authorization tại nghiệp vụ.

**Câu 2. `ApplicationEventPublisher.publishEvent(...)` có tự gửi message ra Kafka/RabbitMQ không?**

Không. Spring application event có thể được truyền hoàn toàn nội bộ trong ApplicationContext. Muốn gửi ra ngoài cần cơ chế externalization hoặc adapter/producer riêng cùng cấu hình transport phù hợp.

**Câu 3. Tại sao không gửi nguyên JPA entity sang đối tác?**

Vì entity chứa chi tiết persistence và có thể chứa dữ liệu không được phép chia sẻ, khiến contract ngoài phụ thuộc quá chặt vào nội bộ. Nên tạo DTO tích hợp với tập trường được cho phép rõ ràng.

**Câu 4. Có thể tin `tenantId` và `producerName` trong payload để cho phép cập nhật dữ liệu không?**

Không. Những trường này có thể do sender tự khai. Cần danh tính đã xác thực và kiểm tra quyền trên tenant/tài nguyên trước khi thực hiện thay đổi.

**Câu 5. Vì sao listener sau commit cùng registry vẫn có thể dẫn tới gửi message trùng?**

Vì có thể xảy ra lỗi sau khi broker đã nhận message nhưng trước khi producer/registry ghi nhận hoàn tất. Khi khôi phục, message có thể được phát lại, nên cần idempotency và chính sách retry.

**Câu 6. Một message sai schema có nên được retry vô hạn không?**

Không. Đây thường là lỗi không khắc phục được bằng retry tức thì. Nên phân loại, chuyển tới quarantine/DLQ có kiểm soát và xử lý theo quy trình.

## 22. Tổng kết

**Biên giới tin cậy là nơi những giả định về danh tính, quyền hạn và dữ liệu phải được xác minh lại.** Trong Spring Modulith, event nội bộ giúp giảm phụ thuộc giữa application modules qua hợp đồng Java được công bố, nhưng module boundary không tự tạo biên giới bảo mật. Khi sự kiện được externalize qua broker hoặc nhận từ đối tác, phải bổ sung hợp đồng tích hợp, phân loại và giới hạn dữ liệu, xác thực/ủy quyền, bảo vệ đường truyền, validation, kiểm soát replay và audit.

Một thiết kế đáng tin cậy kết hợp đúng **ngữ nghĩa sự kiện**, **ranh giới transaction sau commit**, **Event Publication Registry và cơ chế khôi phục khi cần**, **idempotency ở consumer**, cùng **kiểm thử và quan sát theo từng biên giới**. Những kiểm soát này giúp hệ thống tiếp tục mở rộng giao tiếp bằng application events mà vẫn bảo vệ ranh giới nghiệp vụ và dữ liệu khi thông tin rời khỏi miền kiểm soát ban đầu.
