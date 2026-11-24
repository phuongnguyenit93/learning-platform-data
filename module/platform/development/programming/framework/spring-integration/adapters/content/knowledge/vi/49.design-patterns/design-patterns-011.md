# Anti-corruption layer ở biên hệ thống với Spring Integration Adapters

Khi tích hợp hai hệ thống, điều khó nhất không phải lúc nào cũng là mở kết nối HTTP, tải file qua SFTP hay publish Kafka. Khó khăn thường nằm ở việc **hai bên dùng các khái niệm nghiệp vụ khác nhau**. Một hệ thống đối tác gọi đơn hàng là `booking`, dùng mã trạng thái `S1`/`S2` và tính tiền bằng đơn vị nhỏ nhất; hệ thống nội bộ dùng `Order`, `OrderStatus` và `Money` có đơn vị tiền tệ rõ ràng. Nếu các khái niệm của đối tác đi thẳng vào domain nội bộ, toàn bộ code sẽ dần phụ thuộc vào từ vựng, trạng thái, mã lỗi và thói quen phiên bản của hệ thống bên ngoài.

**Anti-corruption layer (ACL)** là một mẫu thiết kế trong Domain-Driven Design (DDD) nhằm **ngăn mô hình của một bounded context bên ngoài làm biến dạng mô hình của bounded context nội bộ**. ACL tiếp nhận dữ liệu/ý định từ hệ thống ngoài, **diễn giải ý nghĩa**, chuyển đổi thành ngôn ngữ miền nội bộ và dịch kết quả trở lại khi cần. Nó cũng quyết định cách phản ứng trước hợp đồng sai, thiếu định danh, khác biệt về trạng thái, thời gian, tiền tệ, lỗi và các thay đổi phiên bản.

Bài học thuộc chương **Design patterns** của module `SPRING_INTEGRATION_ADAPTERS`. Module hướng tới kết nối các hệ thống ngoài qua **inbound/outbound adapter, gateway, poller và `MessageChannel`**, bao gồm File, SFTP, HTTP, JMS, AMQP, Kafka và database. Trong kiến trúc ấy, Spring Integration cung cấp các **cơ chế vận chuyển/điều phối message**; ACL cung cấp **ranh giới ngữ nghĩa** để việc thay đổi giao thức hay schema đối tác không lan sâu vào domain.

> **Luận điểm trung tâm:** Adapter biết **làm sao** trao đổi dữ liệu với đối tác; ACL biết **dữ liệu đó có nghĩa gì** đối với domain nội bộ và làm sao biểu đạt domain ra ngôn ngữ của đối tác. Có thể triển khai chúng trong cùng một flow, nhưng không nên đánh đồng trách nhiệm.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Anti-corruption layer** theo DDD và vì sao nó hữu ích ở ranh giới tích hợp.
2. Phân biệt **transport adapter**, **gateway**, **DTO mapper**, **translator**, **facade**, **domain service** và **ACL**.
3. Nhận diện sự không tương thích **ngôn ngữ miền, định danh, trạng thái, thời gian, đơn vị, lỗi, bảo mật và version**.
4. Thiết kế ACL **inbound** và **outbound** cho hệ thống có nhiều đối tác và nhiều giao thức.
5. Xây dựng các quy tắc mapping **tường minh, kiểm tra được, không mất dữ liệu âm thầm**.
6. Dùng Spring Integration Java DSL để tổ chức **receive → validate → translate → domain channel** và **domain request → translate → outbound gateway → translate reply**.
7. Chọn phạm vi dùng **canonical internal model** mà không tạo một “mô hình chung toàn công ty” cứng nhắc.
8. Xử lý **contract evolution**, backward compatibility, unknown enum, partner reference mapping và version drift.
9. Kết hợp ACL với **retry, idempotency, error channel, quarantine, audit, tracing, trust boundary và transaction**.
10. Kiểm thử ACL qua unit test, contract test, flow test, transport test và end-to-end test; biết giới hạn bằng chứng của mỗi tầng.

## 2. Vấn đề: khi mô hình bên ngoài tràn vào domain

Giả sử hệ thống của một đối tác giao hàng phát event:

~~~json
{
  "event_key": "evt-4280",
  "booking_ref": "SHIP-2026-000428",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00",
  "client_code": "customer-vn",
  "note": "delivered"
}
~~~

Nội bộ muốn lưu một sự kiện nghiệp vụ có ý nghĩa rõ:

~~~json
{
  "eventId": "evt-4280",
  "shipmentId": "shp-2048",
  "status": "DELIVERED",
  "occurredAt": "2026-11-23T09:00:00Z",
  "tenantId": "VN"
}
~~~

Hai biểu diễn khác nhau **không chỉ về tên trường**:

| Thuộc tính đối tác | Ngữ nghĩa cần xác minh | Biểu diễn nội bộ |
|---|---|---|
| `event_key` | ID event có ổn định khi retry không? Có unique trong phạm vi nào? | `eventId` có scope nguồn/tenant. |
| `booking_ref` | Mã do đối tác cấp, có tái sử dụng không? | `shipmentId` qua bảng tham chiếu đáng tin cậy. |
| `phase = "S2"` | S2 là “delivered”, “out for delivery” hay “accepted”? | Enum `DeliveryStatus.DELIVERED` nếu hợp đồng xác nhận. |
| `event_time` | Thời điểm event hay thời điểm gửi? Có offset hợp lệ không? | `Instant occurredAt`. |
| `client_code` | Giá trị tự khai hay được ràng buộc bởi identity của nguồn? | `tenantId` xác minh theo trusted integration context. |
| `note` | Text mô tả không cấu trúc, có cần lưu/audit? | Bỏ qua hoặc lưu trong metadata được duyệt, không tự coi là trạng thái. |

Nếu code nghiệp vụ viết trực tiếp:

~~~java
if ("S2".equals(partnerEvent.phase())) {
    order.markDelivered();
}
~~~

thì domain đã phải biết mã `S2` của đối tác. Khi đối tác đổi sang `DEL`, mọi chỗ dùng “S2” có thể vỡ. Nguy hiểm hơn: nếu đối tác thay **ý nghĩa** của `S2` nhưng giữ tên, code vẫn chạy và làm sai nghiệp vụ.

**ACL giải quyết bằng cách tập trung diễn giải hợp đồng tại biên**, rồi chỉ đưa vào domain những đối tượng và hành động đã được xác minh theo từ vựng nội bộ.

## 3. Sơ đồ kiến trúc Anti-corruption layer

~~~mermaid
flowchart LR
    subgraph EXTERNAL["Bounded context đối tác"]
        EXT["External API / File / Topic / DB"]
        EDTO["External DTO + partner semantics"]
    end
    subgraph BOUNDARY["Integration boundary"]
        ADAPTER["Spring Integration adapter / gateway"]
        VALID["Transport/contract validation"]
        ACL["Anti-corruption layer<br/>Translate + Interpret + Policy"]
    end
    subgraph DOMAIN["Bounded context nội bộ"]
        CMD["Internal command / event / value objects"]
        SERVICE["Domain service / application service"]
        MODEL["Domain model"]
    end
    EXT --> EDTO --> ADAPTER --> VALID --> ACL --> CMD --> SERVICE --> MODEL
    MODEL -. "Kết quả miền" .-> ACL
    ACL -. "External response" .-> ADAPTER
~~~

**Hai biên khác nhau:**

1. **Biên transport:** byte/record/HTTP request/broker delivery được chuyển thành message có payload và headers.
2. **Biên ngữ nghĩa:** external contract được diễn giải thành domain command/event/value object, có xác minh invariants và mapping rõ ràng.

Không phải lúc nào ACL cũng là **một class riêng**. Nó có thể là một nhóm translator, identifier resolver, semantic validator, exception mapper và application-facing facade được đặt thành module/package rõ ràng, với tests và ownership thống nhất.

## 4. ACL khác những mẫu/thành phần dễ nhầm

| Thành phần/mẫu | Vai trò chính | Có phải ACL? |
|---|---|---|
| **HTTP/SFTP/JMS/AMQP/Kafka adapter** | Kết nối và vận chuyển dữ liệu theo protocol. | **Không tự động**. Có thể chỉ chuyển byte. |
| **Inbound/outbound gateway** | Request–reply và bridge với message flow. | Có thể là một phần đường đi qua ACL. |
| **DTO mapper** | Đổi cấu trúc fields/kiểu dữ liệu. | Là thành phần ACL khi có mục tiêu bảo vệ ngữ nghĩa. |
| **Translator** | Chuyển ngôn ngữ/model giữa hai context. | Thành phần cốt lõi của ACL. |
| **Facade** | Cung cấp API đơn giản cho một subsystem. | Có thể bọc ACL nhưng không thay thế translation. |
| **Adapter pattern (GoF)** | Đổi interface cho tương thích. | Có thể phục vụ ACL; chưa đủ để chặn semantic leakage. |
| **Application service** | Điều phối use case nội bộ. | Tiêu thụ output ACL; không nên biết external status code. |
| **Domain service** | Thực thi quy tắc miền nội bộ. | Không nên phụ thuộc mã đối tác. |
| **Backend-for-Frontend (BFF)** | Tạo API phù hợp từng client/UI. | Có thể dùng translator, mục đích không đồng nhất ACL. |
| **Canonical data model** | Biểu diễn nội bộ dùng chung trong phạm vi chọn. | Hữu ích nhưng không phải ACL nếu thiếu translation/bảo vệ biên. |
| **Schema registry** | Theo dõi schema và compatibility. | Giúp contract governance; không tự hiểu nghiệp vụ. |

Một lớp chỉ đổi `snake_case` sang `camelCase` chưa chắc là ACL đủ giá trị. Ngược lại, nếu nó **tách external meanings, điều chỉnh domain invariants, chặn dữ liệu không diễn giải được và ngăn rò mã đối tác**, lớp đó có vai trò thật sự của ACL dù tên chỉ là `PartnerTranslator`.

## 5. Khi nào nên dùng và khi nào không cần ACL lớn?

**Nên đầu tư ACL rõ ràng khi:**

- Hai bên có **mô hình nghiệp vụ khác nhau**, dù cùng dùng Java/JSON.
- Đối tác thay đổi schema/version theo chu kỳ độc lập.
- Mã trạng thái và lỗi bên ngoài không tương ứng trực tiếp với domain.
- Cần ánh xạ external ID sang internal ID, money/time/unit hoặc tenant.
- Tích hợp nhiều partner cùng một use case, mỗi partner một contract.
- Domain lõi phải bền vững trước việc thay HTTP bằng SFTP/Kafka hay đổi nhà cung cấp.
- Có rủi ro cao từ thông điệp sai, duplicate, stale event hoặc unauthorized data.

**Không nhất thiết tạo một framework ACL lớn khi:** hệ thống nhỏ, hai bên cùng một bounded context thật sự, hợp đồng ổn định và translation cực kỳ đơn giản. Khi ấy một translator nhỏ, có test, đã đủ. Không tạo nhiều abstraction chỉ vì gọi là DDD.

### Dấu hiệu ACL đang bị thiếu

- Service/domain code import package `com.partner.vendor.dto.*`.
- Enum nội bộ chứa `S1`, `S2` chỉ vì một bên ngoài dùng mã đó.
- Mỗi use case tự `if (status.equals("DEL"))` với cách hiểu khác nhau.
- Một external field được suy thành internal ID mà không có mapping policy.
- HTTP error hoặc broker metadata tràn vào logic domain.
- Thay đối tác phải sửa nhiều aggregate thay vì một cụm adapter/translator.

## 6. Nguyên tắc thiết kế ACL

1. **Biên rõ ràng:** code domain không phụ thuộc external DTO, protocol header và exception của vendor.
2. **Ngữ nghĩa trước cú pháp:** hiểu ý nghĩa `S2` trước khi đổi tên thành `DELIVERED`.
3. **Mapping tường minh:** không mặc định unknown enum thành trạng thái hợp lệ.
4. **Không tạo internal ID bằng đoán chuỗi:** dùng reference mapping có thẩm quyền.
5. **Tin cậy có phân lớp:** source authenticity/tenant được xác minh ở biên; payload là dữ liệu chưa tin cậy.
6. **Chuyển đổi thuần túy khi có thể:** translator ít side effect để dễ unit test và replay.
7. **Không trộn transport retries với business mapping:** lỗi transient không được biến thành validation fail.
8. **Quan sát được:** có correlation, contract version, mapping outcome và quarantine reason.
9. **Có chính sách thay đổi version:** mỗi thay đổi vendor không âm thầm đổi behavior domain.
10. **Fail closed cho ambiguity quan trọng:** không tự phát minh trạng thái, đơn vị tiền hay tenant khi chưa xác minh.
11. **Được sở hữu và kiểm thử:** đội tích hợp chịu trách nhiệm contract, domain owner phê duyệt cách diễn giải nghiệp vụ.

## 7. Phân chia lớp trong một ACL thực dụng

~~~text
integration/
  partner_acme/
    inbound/
      PartnerEventDto.java
      PartnerInboundFlow.java
      PartnerPayloadValidator.java
    outbound/
      PartnerReserveRequest.java
      PartnerReserveResponse.java
      PartnerOutboundFlow.java
    acl/
      PartnerEventTranslator.java
      PartnerResponseTranslator.java
      PartnerIdentityResolver.java
      PartnerErrorTranslator.java
      PartnerContractVersionPolicy.java
    tests/
      ... (nằm trong src/test/java tương ứng)
domain/
  shipment/
    DeliveryStatus.java
    DeliveryUpdate.java
    ShipmentApplicationService.java
~~~

Đây chỉ là **cách tổ chức minh họa**, không phải cấu trúc bắt buộc của Spring Integration.

| Lớp | Input | Output | Chịu trách nhiệm |
|---|---|---|---|
| **Transport adapter** | HTTP/file/broker/DB | `Message<ExternalPayload>` hoặc bytes | Kết nối, IO, serialization cơ bản, lifecycle. |
| **Contract validator** | External DTO + trusted metadata | Valid external contract hoặc lỗi | Schema, required field, version, size, basic format. |
| **Identifier resolver** | `partnerId + externalRef` | Internal entity ID hoặc unresolved | Reference mapping theo scope. |
| **Semantic translator** | Valid external data + reference | Internal command/event | Enum, unit, time, meaning, trạng thái hợp lệ. |
| **Domain application service** | Internal command | Domain result | Invariants và use-case authorization. |
| **Outbound translator** | Internal request/result | Partner request/response DTO | Biểu diễn theo contract bên ngoài. |
| **Error translator** | Technical/contract/domain outcome | Lỗi/response theo contract | Không lộ exception vendor vào core. |
| **Quarantine/reconciliation** | Event không xử lý được | Evidence + recovery case | Không làm mất bản ghi hoặc báo success giả. |

**Lưu ý:** ACL không nên **định nghĩa lại mọi quy tắc domain**. Nó bảo vệ ranh giới, còn application/domain vẫn phải xác minh invariants. Nếu ACL tự duy trì trạng thái aggregate phức tạp, nó đang trở thành domain thứ hai khó nhất quán.

## 8. Hai chiều translation: inbound và outbound

### 8.1. Inbound

~~~mermaid
flowchart LR
    RAW["External event<br/>PartnerDeliveryEventV1"] --> VALID["Contract validation"]
    VALID --> RESOLVE["Resolve partner reference<br/>+ trusted tenant"]
    RESOLVE --> TRANSLATE["Semantic translation"]
    TRANSLATE --> INTERNAL["DeliveryUpdate<br/>internal model"]
    INTERNAL --> DOM["Domain application service"]
    VALID -. "Reject" .-> QUAR["Quarantine + evidence"]
    RESOLVE -. "Unresolved" .-> QUAR
    TRANSLATE -. "Unknown semantics" .-> QUAR
~~~

Flow inbound có thể **thất bại hợp lệ** khi không biết ánh xạ `phase = "S9"`. Đưa message đó tới quarantine với reason `UNKNOWN_PARTNER_STATUS` thường an toàn hơn việc tự coi `S9` là `DELIVERED` hoặc âm thầm bỏ qua.

### 8.2. Outbound

~~~mermaid
flowchart LR
    CMD["ReserveShipmentCommand<br/>internal"] --> MAP["Outbound translator"]
    MAP --> REQUEST["PartnerReserveRequestV2"]
    REQUEST --> ADAPTER["HTTP/JMS/AMQP outbound gateway"]
    ADAPTER --> RESP["PartnerReserveResponseV2"]
    RESP --> BACK["Inbound response translator"]
    BACK --> RESULT["ReservationResult<br/>internal"]
    ADAPTER -. "Protocol error" .-> ERROR["Technical failure mapping"]
~~~

Outbound translator không chỉ đổi tên trường. Nó có thể **dịch yêu cầu** sang action mà partner hiểu, chọn remote resource identifier, biểu diễn thời gian/đơn vị/kiểu dữ liệu, và dịch reply/errors trở lại **một hợp đồng ổn định đối với application service**.

## 9. Thiết kế model: external DTO không được thành domain entity

Giả sử hệ thống nội bộ cần sự kiện cập nhật tiến trình giao hàng. Dùng Java 17+ records để mô tả ranh giới:

~~~java
package example.partner.external;

// Contract từ một partner cụ thể, không đưa vào domain package.
public record PartnerDeliveryEventV1(
        String eventKey,
        String bookingRef,
        String phase,
        String eventTime,
        String clientCode) {
}
~~~

~~~java
package example.domain.delivery;

import java.time.Instant;

public enum DeliveryStatus {
    IN_TRANSIT, DELIVERED, RETURNED
}

public record DeliveryUpdate(
        String eventId,
        String shipmentId,
        DeliveryStatus status,
        Instant occurredAt,
        String tenantId) {
}
~~~

**Giả định của ví dụ:** external DTO đã được JSON decoder hoặc file parser chuyển thành Java record; wire format thực tế có thể là `snake_case`, trong khi Java dùng camelCase. Field mapping của Jackson/serializer cần được cấu hình tại adapter hoặc DTO (ví dụ `@JsonProperty`), **không suy rằng Jackson tự động đổi mọi tên** khi không cấu hình naming strategy.

### 9.1. Mỗi bên có quyền đổi tên độc lập

Partner đổi `booking_ref` thành `shipment_reference` trong v2: cập nhật partner DTO/translator v2, **không đổi domain `DeliveryUpdate.shipmentId`** nếu ý nghĩa nội bộ vẫn vậy.

Domain đổi cách lưu trạng thái từ enum sang value object có reason: cập nhật interface ACL/domain trong quá trình migration có kiểm soát, không bắt partner phải thay ngay wire contract.

## 10. Mẫu translator: tường minh và dễ kiểm thử

Nên tách những quy tắc **thuần túy** (status/time/required fields) khỏi việc **tra cứu external reference** có I/O. Khi đó unit test mapping nhanh, test resolver có thể kiểm tra idempotency/caching và dữ liệu sai riêng.

### 10.1. Trusted context được xác minh tại biên

~~~java
package example.partner.acl;

public record TrustedPartnerContext(
        String partnerId,
        String tenantId,
        String authenticatedClientCode) {
}
~~~

Đối tượng này chỉ nên được tạo từ **kết quả xác thực, cấu hình connection/source đã duyệt hoặc mapping của inbound adapter**, không từ một header `tenantId` tùy ý do client tự gửi. `tenantId` là **định danh tenant nội bộ**, còn `authenticatedClientCode` là mã client bên partner đã được ràng buộc với kết nối/principal đáng tin. Payload có `clientCode` chỉ là **claimed value** và phải đối chiếu với mã client đã xác minh, không so trực tiếp với tenant nội bộ nếu hai hệ thống dùng mã khác nhau.

### 10.2. Reference resolver có hợp đồng rõ

~~~java
package example.partner.acl;

import java.util.Optional;

public interface ShipmentReferenceResolver {
    Optional<String> findInternalShipmentId(
            String partnerId,
            String tenantId,
            String bookingRef);
}
~~~

Một khóa ánh xạ nên có **partner + tenant + external reference** hoặc phạm vi unique được hợp đồng bảo đảm. Không làm:

~~~java
// SAI nếu không có hợp đồng cho phép quy tắc này:
String internalId = external.bookingRef().replace("SHIP-", "");
~~~

Mã partner có thể tái sử dụng, khác độ dài, khác tenant hoặc thay format. Với dữ liệu nghiệp vụ quan trọng, cần **identity mapping có thẩm quyền**, không phải string manipulation đoán nghĩa.

### 10.3. Translator cụ thể

~~~java
package example.partner.acl;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.Objects;

import example.partner.external.PartnerDeliveryEventV1;
import example.domain.delivery.DeliveryStatus;
import example.domain.delivery.DeliveryUpdate;

public final class PartnerDeliveryTranslator {
    private final ShipmentReferenceResolver references;

    public PartnerDeliveryTranslator(
            ShipmentReferenceResolver references) {
        this.references = Objects.requireNonNull(references);
    }

    public DeliveryUpdate toDomain(
            PartnerDeliveryEventV1 event,
            TrustedPartnerContext trusted) {

        if (event == null || trusted == null) {
            throw new InvalidPartnerContract("Missing event/context");
        }
        requireNonBlank(event.eventKey(), "eventKey");
        requireNonBlank(event.bookingRef(), "bookingRef");
        requireNonBlank(event.phase(), "phase");
        requireNonBlank(event.eventTime(), "eventTime");

        if (!trusted.authenticatedClientCode()
                .equals(event.clientCode())) {
            throw new InvalidPartnerContract("Tenant mismatch");
        }

        String internalId = references.findInternalShipmentId(
                trusted.partnerId(),
                trusted.tenantId(),
                event.bookingRef()
        ).orElseThrow(() ->
                new UnresolvedPartnerReference(event.bookingRef()));

        DeliveryStatus status = switch (event.phase()) {
            case "S1" -> DeliveryStatus.IN_TRANSIT;
            case "S2" -> DeliveryStatus.DELIVERED;
            case "R1" -> DeliveryStatus.RETURNED;
            default -> throw new InvalidPartnerContract(
                    "Unknown partner phase");
        };

        final Instant occurredAt;
        try {
            occurredAt = OffsetDateTime
                    .parse(event.eventTime())
                    .toInstant();
        } catch (DateTimeParseException ex) {
            throw new InvalidPartnerContract(
                    "Invalid event timestamp", ex);
        }

        return new DeliveryUpdate(
                event.eventKey(),
                internalId,
                status,
                occurredAt,
                trusted.tenantId()
        );
    }

    private static void requireNonBlank(
            String value, String name) {
        if (value == null || value.isBlank()) {
            throw new InvalidPartnerContract("Missing " + name);
        }
    }
}
~~~

Hai loại exception minh họa:

~~~java
package example.partner.acl;

public class InvalidPartnerContract extends RuntimeException {
    public InvalidPartnerContract(String message) {
        super(message);
    }
    public InvalidPartnerContract(String message, Throwable cause) {
        super(message, cause);
    }
}

public class UnresolvedPartnerReference extends RuntimeException {
    public UnresolvedPartnerReference(String reference) {
        super("Unresolved external shipment reference: " + reference);
    }
}
~~~

Trong Java thực tế, mỗi `public` top-level class/record/enum nên đặt trong **file riêng theo tên class**. Các code block ở đây được chia theo ý tưởng, không phải một nguồn Java duy nhất để dán tất cả vào một file.

### 10.4. Vì sao không dùng default enum?

~~~java
// SAI: biến mọi giá trị chưa biết thành delivered.
DeliveryStatus status = switch (event.phase()) {
    case "S1" -> DeliveryStatus.IN_TRANSIT;
    default -> DeliveryStatus.DELIVERED;
};
~~~

Nếu partner thêm `S3 = DELIVERY_FAILED`, code sai có thể báo giao hàng đã hoàn thành. Với status có tác động nghiệp vụ, **unknown** nên tạo lỗi contract và được quarantine/điều tra có kiểm soát. Trường hợp business chấp nhận `UNKNOWN` như một trạng thái miền thực sự phải được **đặc tả**, không được dùng như cách che drift của partner.

## 11. Semantic mapping: những bẫy không thấy bằng type checker

| Loại lệch nghĩa | External contract | Internal requirement | Hướng ACL |
|---|---|---|---|
| **Status** | `S2` có nghĩa riêng | `DELIVERED` có invariants | Mapping đã xác nhận version/semantics. |
| **Identifier** | `booking_ref` của partner | `shipmentId` nội bộ | Reference resolver có scope. |
| **Thời gian** | Local time với offset | `Instant` | Parse offset; reject timestamp không rõ zone nếu cần. |
| **Currency** | Minor units (ví dụ cent) | `Money(currency, amount)` | Quy tắc scale/rounding và currency tường minh. |
| **Quantity** | Gram | Kilogram | Dùng đơn vị rõ, xử lý precision. |
| **Null/absent** | Trường vắng có thể nghĩa “unchanged” | Domain update có ý nghĩa khác `null` | Phân biệt missing, null và reset. |
| **Boolean** | `Y/N/U` | true/false/unknown | Không ép unknown thành false. |
| **Error** | `E409_DUP` | `AlreadyExists` hoặc conflict | Error translator gắn context. |
| **Identity** | `clientCode` trong payload | Tenant đã xác thực | Đối chiếu trusted context. |
| **Ordering** | Event đến bất kỳ thứ tự | State machine có thứ tự/version | Version/sequence/stale event policy. |
| **Partial result** | Partner trả `ACCEPTED` | Domain cần `COMPLETED` | Không đổi accepted thành completed. |
| **Precision** | Decimal hoặc số thực | Monetary exactness | `BigDecimal` và rounding policy. |

### 11.1. Ví dụ tiền tệ

Nếu partner trả `total_minor_units: 1099` với `currency: USD`, không được chia 100 bằng `double` rồi đoán mọi currency đều có hai chữ số thập phân. Currency có số chữ số nhỏ nhất khác nhau; conversion phải theo **contract** và monetary library/`BigDecimal` phù hợp. Có thể cần chặn giá trị âm, overflow, precision hoặc currency không hỗ trợ.

### 11.2. Ví dụ thời gian

`2026-11-23T09:00:00Z` và `2026-11-23T16:00:00+07:00` biểu diễn cùng một `Instant`. Nếu partner gửi `2026-11-23 16:00:00` **không có zone**, phải có hợp đồng timezone của nguồn; không âm thầm dùng timezone mặc định của JVM vì có thể khác giữa local và CI.

## 12. Chuyển đổi phải tách contract validation và domain invariants

Một sự kiện có thể **đúng schema** nhưng **sai nghiệp vụ**:

~~~json
{
  "event_key": "evt-100",
  "booking_ref": "SHIP-01",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00",
  "client_code": "customer-vn"
}
~~~

Event trên đầy đủ fields; nhưng nếu shipment đã bị hủy hoặc shipment nội bộ không cho chuyển `RETURNED → DELIVERED`, domain cần từ chối transition.

~~~mermaid
flowchart TD
    RAW["Partner payload"] --> SCHEMA{"Schema/contract hợp lệ?"}
    SCHEMA -- "Không" --> REJECT["Invalid contract<br/>quarantine"]
    SCHEMA -- "Có" --> TRANSLATE{"Mapping có nghĩa?"}
    TRANSLATE -- "Không" --> REJECT
    TRANSLATE -- "Có" --> CMD["Internal command"]
    CMD --> DOMAIN{"Domain invariants hợp lệ?"}
    DOMAIN -- "Không" --> BUSINESS["Business rejection<br/>conflict/ignored event"]
    DOMAIN -- "Có" --> APPLY["Apply business transition"]
~~~

**ACL không phải nơi lách qua domain invariants**. Nó diễn giải để domain nhận yêu cầu chuẩn; domain quyết định trạng thái cuối có được phép thay đổi hay không. Hai loại lỗi cần có classification khác nhau trong audit/retry policy.

## 13. Đưa ACL vào Spring Integration Java DSL

Spring Integration cung cấp các bước như `IntegrationFlow.from(...)`, `transform(...)`, `handle(...)`, `filter(...)`, `route(...)` và `channel(...)`. ACL có thể được đặt **giữa decoded inbound payload và application-facing channel**, hoặc **trước outbound gateway và sau phản hồi từ partner**.

### 13.1. Inbound flow: message đã decode → translation → domain channel

~~~java
package example.partner.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

import example.partner.acl.InvalidPartnerContract;
import example.partner.acl.PartnerDeliveryTranslator;
import example.partner.acl.TrustedPartnerContext;
import example.partner.external.PartnerDeliveryEventV1;

@Configuration
@EnableIntegration
public class PartnerIngressConfig {

    // Kênh này chỉ nhận DTO đã decode từ adapter đáng tin cậy.
    @Bean
    DirectChannel decodedPartnerEvents() {
        return new DirectChannel();
    }

    // Ở production, channel dẫn tới application service.
    // Trong flow test có thể dùng QueueChannel để quan sát output.
    @Bean
    QueueChannel internalDeliveryUpdates() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow deliveryIngressFlow(
            DirectChannel decodedPartnerEvents,
            QueueChannel internalDeliveryUpdates,
            PartnerDeliveryTranslator translator) {
        return IntegrationFlow.from(decodedPartnerEvents)
                .handle(PartnerDeliveryEventV1.class,
                        (payload, headers) -> {
                            Object value = headers.get(
                                    "verifiedPartnerContext");

                            if (!(value instanceof TrustedPartnerContext trusted)) {
                                throw new InvalidPartnerContract(
                                        "Missing trusted partner context");
                            }
                            return translator.toDomain(payload, trusted);
                        })
                .channel(internalDeliveryUpdates)
                .get();
    }
}
~~~

**Điều kiện bắt buộc:** header `verifiedPartnerContext` trong ví dụ **không được lấy thẳng từ HTTP request headers hoặc Kafka event headers do client tùy ý ghi**. Adapter/authentication boundary phải kiểm chứng source identity và gắn context này theo một quy ước nội bộ an toàn; nếu input không có context đáng tin, flow từ chối.

Đây là **mẫu minh họa cho Spring Integration Java DSL**, giả định `PartnerDeliveryTranslator` là bean và các DTO/classes ở các phần trước đã khai báo. Phiên bản Spring Integration có thể khác chút về overload typed `handle(...)`. Điều không đổi: **application service chỉ nhìn thấy `DeliveryUpdate`, không thấy `PartnerDeliveryEventV1`**.

### 13.2. Không nối external payload thẳng vào domain

~~~java
// Anti-pattern: domain handler nhận nguyên external DTO.
return IntegrationFlow.from(decodedPartnerEvents)
        .handle(partnerEvent -> domainService.applyPartnerEvent(partnerEvent))
        .get();
~~~

Nếu domain phải nhập package `PartnerDeliveryEventV1` rồi tự hiểu `phase`, lớp bảo vệ đã bị bỏ qua. Khi hệ thống đơn giản, translator và application service có thể được gọi trong cùng handler, nhưng **trách nhiệm chuyển đổi phải vẫn tách biệt và test độc lập**.

### 13.3. Filter hay translator nên xử lý unknown value?

Một filter có thể loại message, nhưng **lọc im lặng** status chưa biết thường là anti-pattern. Nếu partner thêm code mới:

- Contract validator/translator nên báo lỗi có reason và version.
- Error flow quyết định quarantine hay xử lý chờ bổ sung mapping.
- Cần bằng chứng event chưa được áp dụng, không chỉ “không có output”.

Trường hợp cố ý bỏ qua một event (ví dụ notification không liên quan) phải có **rule explicit** và metrics về số event bị bỏ qua.

## 14. ACL outbound và response translation

Giả sử domain muốn “đặt chỗ giao hàng”, còn partner dùng `booking_ref`, `service_code` và trả `state = "A"` hoặc `state = "P"`.

### 14.1. Ba mô hình riêng biệt

~~~java
// Internal command:
public record ReserveShipmentCommand(
        String shipmentId,
        String tenantId,
        String serviceLevel) {
}

// Partner's request DTO:
public record PartnerReserveRequestV2(
        String partnerReference,
        String serviceCode) {
}

// Partner's reply DTO:
public record PartnerReserveResponseV2(
        String partnerBookingId,
        String state) {
}

// Internal result:
public record ShipmentReservationResult(
        String shipmentId,
        String reservationId,
        ReservationOutcome outcome) {
}
~~~

Các records/enums cần nằm trong **package/file riêng** ở source thật. `ReservationOutcome` là enum nội bộ do domain định nghĩa theo hợp đồng, không dùng trực tiếp các mã `A`, `P` của partner.

### 14.2. Outbound translator

~~~java
public final class PartnerReservationTranslator {

    private final PartnerReferenceRepository references;

    public PartnerReservationTranslator(
            PartnerReferenceRepository references) {
        this.references = references;
    }

    public PartnerReserveRequestV2 toPartner(
            ReserveShipmentCommand command) {
        String partnerReference = references
                .toPartnerReference(
                        command.tenantId(), command.shipmentId())
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "No partner shipment mapping"));

        String serviceCode = switch (command.serviceLevel()) {
            case "STANDARD" -> "STD";
            case "EXPRESS" -> "EXP";
            default -> throw new IllegalArgumentException(
                    "Unsupported service level");
        };

        return new PartnerReserveRequestV2(
                partnerReference, serviceCode);
    }

    public ShipmentReservationResult toDomainResult(
            String internalShipmentId,
            PartnerReserveResponseV2 response) {
        ReservationOutcome outcome = switch (response.state()) {
            case "A" -> ReservationOutcome.CONFIRMED;
            case "P" -> ReservationOutcome.PENDING;
            default -> throw new InvalidPartnerContract(
                    "Unknown reservation state");
        };
        return new ShipmentReservationResult(
                internalShipmentId,
                response.partnerBookingId(),
                outcome);
    }
}
~~~

Đoạn trên **minh họa hợp đồng method**; `PartnerReferenceRepository` và `ReservationOutcome` là interface/enum cần định nghĩa trong dự án. Khi reply chỉ có `partnerBookingId`, ACL cần biết **request context hoặc correlation** để liên hệ lại `internalShipmentId`; không suy ra internal ID từ mã phản hồi.

### 14.3. Java DSL ghép HTTP outbound gateway

~~~java
// Mẫu cấu hình minh họa; cần module spring-integration-http
// và import org.springframework.integration.http.dsl.Http,
// org.springframework.http.HttpMethod theo phiên bản dự án.

@Bean
IntegrationFlow reserveWithPartner(
        DirectChannel internalReservations,
        PartnerReservationTranslator translator) {

    return IntegrationFlow.from(internalReservations)
            // Bước này phải duy trì context request để map reply.
            .transform(ReserveShipmentCommand.class,
                    translator::toPartner)
            .handle(Http.outboundGateway(
                        "https://partner.example/v2/reservations")
                    .httpMethod(HttpMethod.POST)
                    .expectedResponseType(PartnerReserveResponseV2.class))
            // Có thể thêm bước map reply với persisted request
            // correlation/context, không tự tạo internal ID từ reply.
            .channel("partnerReservationResponses")
            .get();
}
~~~

**Quan trọng:** cấu hình trên chỉ minh họa outbound translation và lời gọi HTTP; chưa thực hiện bước `toDomainResult` vì việc ghép **original internalShipmentId với reply** cần thiết kế correlation/persistence riêng. Không coi đây là flow hoàn chỉnh cho request/reply production. Ngoài ra `partner.example` chỉ là hostname mẫu; cấu hình thật phải dùng endpoint và secret quản trị qua môi trường an toàn.

### 14.4. Điểm cần test khi có request/reply

1. Internal command được chuyển thành request partner đúng schema/mã dịch vụ.
2. External reference được tra cứu từ store đúng tenant.
3. HTTP method/path/headers và body đúng contract.
4. Response code `A/P` được dịch thành outcome nội bộ rõ nghĩa.
5. Response không chứa đủ correlation bị xử lý theo policy, không đoán ID.
6. Missing reply, timeout, duplicate reply hoặc reply đến trễ không làm lẫn request.
7. Một HTTP 202 hoặc partner `PENDING` không được biến thành internal `CONFIRMED`.
8. Side effect có idempotency/readback nếu retry một operation ghi dữ liệu.

## 15. Một hay nhiều canonical model?

Sự hấp dẫn của một `CanonicalOrderEvent` dùng chung cho mọi partner là giảm số DTO truyền qua hệ thống. Tuy nhiên một **canonical model toàn doanh nghiệp** quá lớn có thể trở thành một bản hợp nhất của mọi trường vendor, tạo ra chính sự ô nhiễm mà ACL muốn ngăn.

### 15.1. Mô hình nội bộ theo bounded context

~~~mermaid
flowchart LR
    A["Partner A contract"] --> ACL_A["ACL A"]
    B["Partner B contract"] --> ACL_B["ACL B"]
    C["Partner C contract"] --> ACL_C["ACL C"]
    ACL_A --> CMD["Delivery bounded context<br/>DeliveryUpdate"]
    ACL_B --> CMD
    ACL_C --> CMD
    CMD --> DOMAIN["Domain logic"]
~~~

**Khuyến nghị:** dùng mô hình nội bộ phù hợp với **bounded context cụ thể**. Nếu nhiều ứng dụng nội bộ độc lập có semantic khác nhau, chúng không bắt buộc dùng một DTO chung chỉ vì tích hợp qua cùng một ESB/integration platform.

### 15.2. Chi phí của canonical model

| Lựa chọn | Ưu điểm | Rủi ro |
|---|---|---|
| Direct partner DTO vào domain | Ít code ban đầu | Vendor leakage, khó đổi đối tác. |
| Một ACL riêng cho mỗi partner | Bảo vệ model, dễ thay vendor | Có chi phí mapping và governance. |
| Một canonical model trong bounded context | Reuse và hợp đồng nội bộ ổn định | Cần owner/versioning, không ôm mọi ngoại lệ partner. |
| Một enterprise-wide canonical schema khổng lồ | Có thể chuẩn hóa ở quy mô tổ chức | Coupling toàn cục, phát triển chậm, khó chứa khác biệt ngữ nghĩa. |
| Tích hợp event-driven với domain events riêng | Loose coupling giữa context | Cần consistency/ordering/versioning rõ. |

Chọn mô hình bằng **ngôn ngữ nghiệp vụ và ownership**, không chỉ vì giống tên field.

## 16. Bảo vệ ranh giới định danh và ownership

Một external ID có thể là:

- ID duy nhất chỉ trong một account của vendor;
- ID tái sử dụng sau một khoảng thời gian;
- số nguyên thay đổi format qua API v2;
- alias cho cùng một object nội bộ;
- định danh của một object khác về nghĩa dù tên tương tự.

### 16.1. Mapping table có scope

~~~sql
CREATE TABLE partner_shipment_reference (
    partner_id       VARCHAR(80) NOT NULL,
    tenant_id        VARCHAR(80) NOT NULL,
    external_ref     VARCHAR(160) NOT NULL,
    internal_id      VARCHAR(120) NOT NULL,
    mapping_version  INTEGER NOT NULL,
    PRIMARY KEY (partner_id, tenant_id, external_ref)
);
~~~

Đây là **DDL minh họa**, không phải schema production đầy đủ. Tùy domain còn cần uniqueness constraint, lịch sử mapping, effective dates, audit, soft delete hoặc mapping một-nhiều.

### 16.2. Kiểm tra resolver

- Partner A và B cùng có `booking_ref = 100` nhưng trỏ tới shipment khác nhau.
- Hai tenant có cùng external ID, không được đọc chéo.
- Mã đối tác chưa có mapping → `UNRESOLVED_REFERENCE`, không tạo shipment ngẫu nhiên.
- Mapping thay đổi → lưu version và quyết định event cũ dùng phiên bản nào.
- Cache resolver bị stale sau khi mapping được thu hồi → invalidation hoặc bounded TTL.
- Concurrent updates → tránh hai internal objects nhận cùng reference trái với invariant.

**Lưu ý:** ACL có thể cần gọi application service để giải quyết reference; không tự xây một identity master phân tán nếu nguồn dữ liệu đã có owner.

## 17. ACL với phiên bản hợp đồng và schema evolution

Hệ thống ngoài thường triển khai phiên bản độc lập. Một ACL tốt có khả năng nhận diện **contract version** và ánh xạ nó thành cùng một internal meaning khi phù hợp.

### 17.1. Ví dụ v1 và v2

~~~json
{
  "schemaVersion": 1,
  "booking_ref": "SHIP-2026-000428",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00"
}
~~~

~~~json
{
  "schemaVersion": 2,
  "shipment_reference": "SHIP-2026-000428",
  "delivery_state": "DELIVERED",
  "occurred_at": "2026-11-23T09:00:00Z"
}
~~~

Trong ví dụ, hai event có thể diễn tả cùng **Delivered** nhưng chỉ khi partner xác nhận ngữ nghĩa thực sự như nhau.

### 17.2. Mapping theo version

| Thay đổi | Hành động ACL | Có cần domain đổi? |
|---|---|---|
| `booking_ref` → `shipment_reference` | DTO/parser/mapping v2 | Không, nếu ID vẫn cùng nghĩa. |
| `S2` → `DELIVERED` | Translator v2 | Không, nếu vẫn Delivered. |
| Timestamp thêm offset bắt buộc | Parser contract v2 | Có thể không. |
| Status mới `DELIVERY_FAILED` | Đàm phán domain interpretation | Có thể, nếu domain cần trạng thái mới. |
| Partner đổi ID uniqueness scope | Thay resolver/key strategy | Có thể ảnh hưởng data migration. |
| Thay nghĩa `DELIVERED` thành “đến hub” | Không thể chỉ rename field | Phải xem lại domain mapping/invariants. |

### 17.3. Quy tắc an toàn

1. **Có nguồn version đáng tin:** header, content type, schema registry hoặc field payload được xác minh theo contract.
2. **Có mapping được version hóa:** v1 và v2 không lẫn quy tắc ngầm.
3. **Không tự chấp nhận version mới bằng default permissive.**
4. **Có compatibility tests và fixtures cũ** trước khi deploy translator mới.
5. **Có kế hoạch sunset version** và theo dõi traffic còn ở v1.
6. **Có fallback/quarantine** với dữ liệu không diễn giải được.
7. **Tách schema compatibility khỏi semantic compatibility**: field có thể tương thích kiểu nhưng thay nghĩa.

### 17.4. Lưu bằng chứng version

Khi mapping thất bại, audit nên ghi `partnerId`, contract version, event ID, loại lỗi và hash/tham chiếu payload theo quy định bảo mật; tránh chỉ log “invalid payload” vì không đủ khả năng điều tra contract drift.

## 18. ACL ở biên File và SFTP

File/SFTP thường đưa dữ liệu dạng CSV, XML, JSON hoặc fixed-width, có những vấn đề riêng:

| Ranh giới | Lỗi/rủi ro | Trách nhiệm ACL/adapter |
|---|---|---|
| File readiness | Producer đang ghi dở | Adapter chỉ nhận file đã ready theo quy ước. |
| File encoding | UTF-8/legacy encoding | Parser phát hiện/chuẩn hóa theo contract. |
| CSV schema | Thứ tự cột/định dạng ngày/decimal | Contract validator/translator version tương ứng. |
| Remote path | Path do client cấu thành, traversal | Adapter xác thực đường dẫn trong scope. |
| File identity | Tên file bị tái sử dụng | Event/business ID và metadata bền vững. |
| Record identity | Một file chứa nhiều đơn hàng | ACL map từng row với sourceRef/row number khi cần. |
| Partial errors | 9 rows đúng, 1 row sai | Định nghĩa atomic batch hay partial acceptance. |
| SFTP disconnect | Download một phần | Retry/cleanup theo adapter lifecycle. |
| Quarantine | File không diễn giải được | Lưu có kiểm soát và reason, không im lặng bỏ. |

### 18.1. Một file không nhất thiết là một business transaction

Giả sử file có 10.000 rows, trong đó 100 rows lỗi contract. Cần quyết định:

- **All-or-nothing:** từ chối toàn file, chỉ commit khi tất cả hợp lệ.
- **Partial processing:** cho 9.900 rows, quarantine 100 rows, báo cáo đối soát.
- **Staged import:** parse và validate toàn bộ trước, rồi apply theo transaction/batch.

ACL có thể tạo **row-level canonical commands** và validation report; quyết định atomicity/business settlement thuộc use case và storage/transaction design. Test phải chứng minh không “đọc được file” = “tất cả rows đã thành công”.

### 18.2. Mapping lỗi có vị trí xác định

Một record lỗi nên ghi tham chiếu `fileId`, `rowNumber`, `contractVersion`, `reasonCode` và thông tin tối thiểu có quyền truy cập. Không ghi private keys, credential SFTP hoặc dữ liệu cá nhân toàn phần trong log chỉ để debug.

## 19. ACL ở biên HTTP inbound và outbound

### 19.1. HTTP inbound gateway

HTTP gateway có thể ánh xạ request JSON thành `Message<ExternalDto>`; ACL sau đó:

1. Xác minh schema/version/content type.
2. Nhận trusted principal/tenant từ security layer đã xác thực.
3. Đối chiếu claimed tenant trong payload nếu contract yêu cầu.
4. Ánh xạ external command thành internal command.
5. Nhận application result và dịch sang response DTO/status code của external API.

**Không đưa trực tiếp DTO public API vào aggregate** chỉ vì controller/HTTP gateway tiện làm như vậy.

### 19.2. HTTP outbound gateway

Outbound ACL dịch internal request sang request đối tác và dịch HTTP response về **outcome có nghĩa đối với domain**.

| HTTP response | Ý nghĩa transport | Điều ACL cần xác định |
|---|---|---|
| 200 | HTTP request thành công | Response body có hợp đồng nghiệp vụ nào? |
| 201 | Tạo resource HTTP | Resource ID và trạng thái có đủ dùng không? |
| 202 | Đã chấp nhận yêu cầu | Chưa tự đồng nghĩa business completed. |
| 400 | Request sai theo API | Schema/validation/quarantine hay bug translator? |
| 401/403 | Authentication/authorization failure | Không retry vô ích bằng cùng credential. |
| 404 | Không tìm thấy | Permanent hay eventual consistency tùy contract. |
| 409 | Conflict | Already processed, duplicate hoặc conflict thực sự? |
| 429 | Rate limit | Retry/backoff theo hợp đồng, không tạo storm. |
| 500/503 | Server failure | Retry bounded, idempotency/readback cho writes. |
| Timeout sau POST | Không biết server đã làm gì | Unknown outcome và reconciliation. |

ACL/error translator không được biến mọi HTTP 2xx thành **domain success** nếu body mang status `REJECTED` hoặc `PENDING`.

### 19.3. Header từ client là dữ liệu chưa tin cậy

Không nên tin `X-Tenant-Id` hoặc `X-Role` từ request mà không có authentication/authorization boundary. Nếu hệ thống dùng API gateway đáng tin, cần có quy ước *strip and re-inject* metadata bảo mật hoặc xác minh chữ ký/mTLS theo thiết kế; tránh giả mạo header qua proxy.

## 20. ACL ở biên JMS, AMQP và Kafka

### 20.1. Dù đều là message, semantics khác nhau

| Khía cạnh | JMS | AMQP | Kafka |
|---|---|---|---|
| Định tuyến | Destination, message selector/provider | Exchange, routing key, binding/queue | Topic, partition, key |
| Delivery state | Session/transaction/ack | ACK/NACK/requeue/confirm | Offset/consumer group/commit |
| Ordering | Theo destination/provider/consumer setup | Theo queue và concurrency | Trong partition, không toàn topic |
| Retry | Container redelivery/advice | Requeue/delayed retry/DLX | Consumer retry/DLT/reprocess |
| Hợp đồng payload | JMS body/properties | AMQP body/properties/headers | Record key/value/headers |

ACL nên tập trung vào **payload meaning, business ID, domain event, error classification**, còn adapter/container chịu trách nhiệm protocol ACK/offset và connection lifecycle.

### 20.2. External event đến từ Kafka

~~~mermaid
flowchart LR
    TOPIC["Partner Kafka topic<br/>ExternalEventV2"] --> CONSUMER["Kafka inbound adapter"]
    CONSUMER --> DECODER["Deserialize + schema check"]
    DECODER --> ACL["ACL: resolve ref,<br/>map meaning/status"]
    ACL --> EV["Internal DeliveryUpdate"]
    EV --> APP["Application service"]
    ACL --> ERROR["Contract error quarantine"]
    APP --> OUT["Side effect + idempotency"]
~~~

Nếu Kafka consumer đã commit offset sau khi ACL chuyển event vào một kênh nội bộ **chưa có durability**, hệ thống có thể mất event khi app crash. Điều này là **transaction/delivery design**, không phải tự được đảm bảo bởi việc có ACL. Test cần xác định **khi nào source được ACK/commit so với lúc xử lý hoặc durable recovery**.

### 20.3. Mã sự kiện và key

External Kafka key có thể được dùng để phân partition, nhưng không mặc định là internal entity ID. ACL có thể cần `partnerId + tenantId + eventId` để dedupe và `externalRef → internalId` để cập nhật aggregate. Cách chọn key ảnh hưởng ordering; đổi key có thể làm sự kiện cùng shipment rơi sang partition khác.

### 20.4. Chuyển lỗi contract ra DLT

Unknown status hoặc invalid schema thường là **non-transient**; retry handler lặp vô ích. Hệ thống có thể đưa vào DLT/quarantine với reason code và có quy trình redrive sau khi cập nhật translator. Nhưng **publish DLT thành công phải được xác nhận**, không chỉ gọi mock publisher rồi ACK source ngay nếu hợp đồng yêu cầu không mất message.

## 21. ACL ở biên JDBC/database

Không nên để schema của hệ thống đối tác **định hình schema domain nội bộ**. Một JDBC inbound adapter có thể đọc legacy table:

~~~sql
SELECT ext_event_key, ext_order_ref, state_code, event_epoch_ms
FROM legacy_shipments
WHERE processed_flag = 0;
~~~

ACL:

- map `ext_order_ref` qua reference resolver;
- dịch `state_code` theo contract/version;
- chuẩn hóa `event_epoch_ms` thành `Instant` với đơn vị millisecond rõ ràng;
- tạo `DeliveryUpdate` hoặc domain command;
- không chuyển `processed_flag` thành một thuộc tính domain chỉ vì source có cột đó.

### 21.1. Polling, transaction và consistency

| Tình huống | Rủi ro | Test nên có |
|---|---|---|
| Row được đọc hai lần | Duplicate side effect | Business idempotency. |
| Row mark processed trước domain commit | Mất event khi app crash | Transaction/checkpoint phù hợp. |
| Hai poller cùng query | Claim trùng | Row lock/lease/atomic update. |
| Mapping missing reference | Event chưa thể diễn giải | Quarantine/retry bằng policy có owner. |
| Contract schema đổi cột | Mapping sai âm thầm | Contract/DB integration test. |
| Timestamp unit đổi | Sai thời gian hàng nghìn lần | Test epoch seconds vs milliseconds. |
| Source database unavailable | I/O transient | Retry/backoff ở adapter, không biến thành domain validation. |

**Tách failure class:** SQL connection timeout là lỗi hệ thống, trong khi `state_code = "??"` là lỗi ngữ nghĩa. Nếu cả hai đều bị bắt chung thành `InvalidPartnerContract`, retry và vận hành sẽ xử lý sai.

## 22. Chính sách lỗi: contract, reference, domain và transport

Một hệ thống có ACL tốt phân loại lỗi để quyết định **retry, reject, quarantine, reconcile hay propagate**.

| Lỗi | Nguồn | Ví dụ | Xử lý đề xuất |
|---|---|---|---|
| **TransportTransient** | Adapter/network | HTTP 503, SFTP mất kết nối | Retry bounded/backoff, quan sát outage. |
| **SerializationFailure** | Decoder/schema | JSON sai cấu trúc | Reject/quarantine, không retry y nguyên. |
| **UnsupportedContractVersion** | ACL contract | Nhận v5 khi chỉ hỗ trợ v1-v2 | Quarantine và báo drift. |
| **UnknownExternalStatus** | Semantic mapping | `phase = "S9"` | Quarantine, owner xác nhận nghĩa. |
| **UnresolvedExternalReference** | Resolver | `booking_ref` chưa map | Chờ reconciliation hoặc reject theo hợp đồng. |
| **TenantMismatch** | Trust boundary | Payload claims tenant khác | Reject/security incident; không tự sửa tenant. |
| **DomainConflict** | Application/domain | Event stale hoặc transition cấm | Ghi nhận business conflict, không map thành 503. |
| **UnknownOutcome** | Outbound/network | POST timeout sau khi gửi | Readback/idempotency trước retry. |
| **RecoveryFailure** | DLQ/quarantine publisher | Không lưu được bản lỗi | Escalate/propagate, không giả vờ handled. |

### 22.1. Error code nội bộ có ý nghĩa nghiệp vụ

~~~json
{
  "errorId": "err-789",
  "category": "CONTRACT",
  "code": "UNKNOWN_EXTERNAL_STATUS",
  "partnerId": "partner-a",
  "contractVersion": 2,
  "eventId": "evt-4280",
  "retryable": false,
  "state": "QUARANTINED"
}
~~~

Schema trên là **mẫu nội bộ**, không phải payload tự động của Spring Integration. Không expose toàn bộ internal `partnerId`/exception/stack trace cho client public nếu chính sách bảo mật không cho phép.

### 22.2. Khi nào trả reply cho external gateway?

Với **request/reply gateway**, phải xác định:

- Trả 4xx cho lỗi contract/tenant validation.
- Trả 409 cho domain conflict nếu public contract quy định.
- Trả 5xx/503 cho transient internal failure khi phù hợp.
- Trả 202 hoặc tracking ID khi xử lý bất đồng bộ, không gọi là completed.
- Trường hợp unknown outcome có status/correlation để truy vấn lại.

Một `ErrorMessageSendingRecoverer` gửi lỗi vào channel một chiều **chưa tạo reply HTTP/JMS gateway**. Nếu caller cần response, error flow phải map thành response tương ứng, nếu không có thể gây timeout giả.

## 23. Retry, idempotency và ACL: ba trách nhiệm khác nhau

**ACL** diễn giải external message. **Retry** quyết định thử lại một thao tác. **Idempotency** bảo vệ side effect khi cùng operation được xử lý nhiều lần.

~~~mermaid
flowchart TD
    E["External event (eventId=E-1)"] --> A["ACL translation"]
    A --> ID["Identity/correlation + dedupe"]
    ID --> OP["Domain operation"]
    OP --> SIDE["Database/HTTP/Kafka side effect"]
    SIDE --> ACK{"Đã xác nhận?"}
    ACK -- "Chưa / timeout" --> VERIFY["Readback / retry policy"]
    VERIFY --> ID
    ACK -- "Rồi" --> DONE["Verified outcome"]
~~~

### 23.1. Một event có thể bị giao lại nhiều lần

Nếu JMS/AMQP/Kafka/File/SFTP source giao lại cùng logical event, Spring message ID được sinh lại hoặc broker delivery metadata khác, nhưng **eventId nghiệp vụ** phải ổn định theo hợp đồng nếu dùng để dedupe.

### 23.2. Không retry một external DTO bằng cách map ra internal command mới mỗi lần mà bỏ qua trạng thái

Kịch bản:

~~~text
E-1: external status S2 = delivered
ACL dịch E-1 → DeliveryUpdate(eventId=E-1, status=DELIVERED)
Domain commit update thành công
ACK broker bị mất
Broker redeliver E-1
ACL dịch lại cùng command
Domain dedupe theo business key/eventId, không tạo tác dụng trùng
~~~

Test cần xác nhận cả **delivery count** và **business side-effect count**, không chỉ số lần mapper chạy. ACL không nhất thiết giữ bảng dedupe; đó thường là trách nhiệm application/storage, nhưng **ACL phải giữ identity đúng và không làm mất idempotency key**.

### 23.3. Đánh đổi khi partner thiếu event ID

Không tùy tiện hash toàn payload rồi coi đó là event ID nếu partner có thể phát hai event hợp lệ có payload giống nhau. Cần thương lượng contract, chọn composite key có nghĩa hoặc cơ chế inbox/reconciliation có owner. Mọi heuristic phải có test collision/false duplicate và giới hạn rõ.

## 24. Trust boundary và bảo mật thông điệp

ACL là lớp bảo vệ **ngữ nghĩa**, nhưng không thay thế authentication/authorization/TLS/secret management.

| Điểm kiểm tra | Mục đích | Test |
|---|---|---|
| HTTP mTLS/OAuth/API key | Xác minh caller/client | Không cho request chưa xác thực vào trusted channel. |
| SFTP host key/auth | Bảo đảm server/partner đúng | Reject host key bất ngờ. |
| Kafka/JMS/AMQP ACL/topic permission | Chỉ nguồn được quyền publish/consume | Không nhận message từ namespace sai. |
| Trusted source identity | Gắn `partnerId` và `tenantId` đúng | Không lấy principal từ payload giả mạo. |
| Schema/size limits | Bảo vệ decoder/resource | Chặn payload quá lớn, dữ liệu nguy hiểm. |
| Path/URI validation | Tránh path traversal/SSRF | Không xây request tới host/path tùy ý từ input. |
| Deserialization allowlist | Giảm rủi ro object deserialization | Chỉ nhận type/schema đã duyệt. |
| Data classification | Quy định lưu/quarantine/log PII | Không lộ sensitive data. |
| Rate limiting | Tránh data flood/retry storm | Có giới hạn nguồn và cảnh báo. |
| Audit/correlation | Truy vết sự kiện | Có event ID, tenant đã xác minh và mapping outcome. |

### 24.1. Không giữ nguyên headers không tin cậy

Một message external có thể chứa `replyChannel`, `errorChannel` hoặc tên header trông giống nội bộ. Inbound transport adapter **không được cho phép client tự điều khiển channel nội bộ bằng header tùy ý**. Ở biên, chỉ nhận allowlist metadata được ánh xạ và khởi tạo lại trusted context. Điều này đặc biệt quan trọng khi các handler downstream dùng routing dựa trên headers.

### 24.2. Không trả raw exception của domain ra external API

Error translator nên quyết định public error code/status; không expose stack trace, connection strings, SQL query, token, private key hoặc thông tin tài nguyên tenant khác.

## 25. Quản lý correlation, audit và observability

Khi một event đi qua nhiều adapter, cần giữ **identity xuyên các dạng message**:

~~~text
Partner event_key
    → ACL eventId
    → Internal operationId / shipmentId
    → HTTP Idempotency-Key
    → Kafka result-eventId
    → Audit / evidence reference
~~~

### 25.1. Mẫu audit

~~~json
{
  "traceId": "trace-2048",
  "partnerId": "partner-a",
  "tenantId": "VN",
  "externalEventId": "evt-4280",
  "externalReference": "SHIP-2026-000428",
  "internalShipmentId": "shp-2048",
  "contractVersion": 1,
  "translatorVersion": "delivery-acl-v4",
  "mappingOutcome": "TRANSLATED",
  "processingOutcome": "APPLIED",
  "targetEvidenceId": "domain-event-9901"
}
~~~

Chỉ lưu trường `externalReference`/`internalShipmentId` khi dữ liệu không thuộc phạm vi nhạy cảm hoặc đã được bảo vệ phù hợp; có thể dùng masked/hash/reference. Log sự kiện thất bại nên đủ thông tin **reason và version**, không cần dump toàn bộ raw payload.

### 25.2. Metrics đáng theo dõi

| Metric | Giúp phát hiện | Cẩn trọng |
|---|---|---|
| **ACL translation success rate** | Contract drift, mapping lỗi | Phải phân nhóm theo version/partner. |
| **Unknown enum count** | Partner thêm trạng thái | Không gộp vào “generic parsing error”. |
| **Unresolved reference backlog** | Reference mapping chưa có | Theo dõi tuổi và owner, không chỉ số lần lỗi. |
| **Tenant mismatch count** | Security/trust boundary lỗi | Có cảnh báo với quyền phù hợp. |
| **Quarantine count/oldest age** | Event chưa xử lý | Không chỉ tính tỷ lệ thành công của event được chọn lọc. |
| **Translator latency P95/P99** | Resolver/transformer chậm | Tách I/O resolver khỏi mapping CPU. |
| **Contract version distribution** | Adoption và sunset plan | Không dùng event ID làm metric label. |
| **Duplicate logical event rate** | Retry/redelivery | Phân biệt attempt vật lý và business operation. |
| **Business confirmation lag** | Kết quả cuối đến chậm | Không đồng nhất với adapter send ACK. |

### 25.3. Chọn metric labels

Label nên dùng `partner`, `version`, `result`, `errorCategory`, `adapterType` và `flowId` với cardinality được quản lý. Không đưa `eventId`, `traceId` hay user ID làm label metric theo từng request. Correlation cụ thể thuộc **trace/log/evidence store** có phân quyền.

## 26. Kiểm thử translator bằng JUnit: semantic mapping mới là mục tiêu

Unit test của ACL không nên phụ thuộc SFTP server, Kafka broker hay HTTP endpoint. Mục tiêu là **cùng external contract + trusted context + reference mapping thì ra internal meaning xác định**, và mọi input không thể diễn giải bị từ chối có lý do.

### 26.1. Happy path

~~~java
package example.partner.acl;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.Test;

import example.partner.external.PartnerDeliveryEventV1;
import example.domain.delivery.DeliveryStatus;
import example.domain.delivery.DeliveryUpdate;

class PartnerDeliveryTranslatorTest {

    private final ShipmentReferenceResolver references =
            (partnerId, tenantId, bookingRef) -> {
                if ("partner-a".equals(partnerId)
                        && "VN".equals(tenantId)
                        && "SHIP-2026-000428".equals(bookingRef)) {
                    return Optional.of("shp-2048");
                }
                return Optional.empty();
            };

    private final PartnerDeliveryTranslator translator =
            new PartnerDeliveryTranslator(references);

    private final TrustedPartnerContext verified =
            new TrustedPartnerContext(
                    "partner-a", "VN", "customer-vn");

    @Test
    void translatesPartnerDeliveryIntoInternalEvent() {
        PartnerDeliveryEventV1 external =
                new PartnerDeliveryEventV1(
                        "evt-4280",
                        "SHIP-2026-000428",
                        "S2",
                        "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        DeliveryUpdate result =
                translator.toDomain(external, verified);

        assertEquals("evt-4280", result.eventId());
        assertEquals("shp-2048", result.shipmentId());
        assertEquals(DeliveryStatus.DELIVERED, result.status());
        assertEquals(
                Instant.parse("2026-11-23T09:00:00Z"),
                result.occurredAt());
        assertEquals("VN", result.tenantId());
    }

    @Test
    void rejectsUnknownStatusInsteadOfGuessing() {
        PartnerDeliveryEventV1 unknown =
                new PartnerDeliveryEventV1(
                        "evt-4281", "SHIP-2026-000428",
                        "S9", "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        assertThrows(InvalidPartnerContract.class,
                () -> translator.toDomain(unknown, verified));
    }

    @Test
    void rejectsClientCodeThatDoesNotMatchTrustedSource() {
        PartnerDeliveryEventV1 forged =
                new PartnerDeliveryEventV1(
                        "evt-4282", "SHIP-2026-000428",
                        "S2", "2026-11-23T16:00:00+07:00",
                        "other-customer");

        assertThrows(InvalidPartnerContract.class,
                () -> translator.toDomain(forged, verified));
    }

    @Test
    void doesNotInventInternalIdForUnknownPartnerReference() {
        PartnerDeliveryEventV1 missing =
                new PartnerDeliveryEventV1(
                        "evt-4283", "SHIP-UNKNOWN",
                        "S2", "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        assertThrows(UnresolvedPartnerReference.class,
                () -> translator.toDomain(missing, verified));
    }
}
~~~

Trong ví dụ này, `ShipmentReferenceResolver` là functional interface (một abstract method), nên có thể dùng lambda. Test đã kiểm tra **mã partner, tenant, external ID, status, time zone và invalid input**; vẫn chưa chứng minh adapter nhận JSON/file hay source đã được xác thực thật.

### 26.2. Không chỉ test một enum value

Hãy test đủ bảng `phase`:

| Partner code | Internal status | Điều kiện |
|---|---|---|
| `S1` | `IN_TRANSIT` | Contract v1 xác nhận. |
| `S2` | `DELIVERED` | Contract v1 xác nhận. |
| `R1` | `RETURNED` | Contract v1 xác nhận. |
| `S9` | Lỗi `UNKNOWN_EXTERNAL_STATUS` | Không suy đoán. |
| `null`/empty | Lỗi `INVALID_CONTRACT` | Không pass-through. |
| `s2` | Theo policy case-sensitive | Không tự uppercase nếu chưa có hợp đồng. |

Nếu version v2 dùng text thay code, viết **test fixture riêng theo version**; không thêm một `default` rộng rồi hy vọng mọi code tương thích.

## 27. Contract test, snapshot/golden fixtures và version drift

**Unit test translator** khẳng định logic chuyển đổi. **Contract test** xác minh external payload thực tế và serializer/parser hiểu đúng wire contract: tên trường, kiểu số, encoding, timestamp, required/optional, enum và version.

### 27.1. Dùng bộ mẫu do partner công bố

~~~text
src/test/resources/contracts/partner-a/
  delivery-v1-success.json
  delivery-v1-missing-ref.json
  delivery-v1-unknown-phase.json
  delivery-v2-success.json
  delivery-v2-new-status.json
~~~

Danh sách chỉ là **cấu trúc mẫu**, không yêu cầu tạo các file đó trong bước biên soạn bài học. Trong dự án thật, các fixture phải được đối chiếu với **partner contract được quản lý** và có version/nguồn xác thực.

### 27.2. Đừng cho parser che lỗi hợp đồng

Ví dụ JSON partner v1 dùng `event_key`:

~~~json
{
  "event_key": "evt-4280",
  "booking_ref": "SHIP-2026-000428",
  "phase": "S2",
  "event_time": "2026-11-23T16:00:00+07:00",
  "client_code": "customer-vn"
}
~~~

Nếu Java DTO là `eventKey` nhưng Jackson chưa có `@JsonProperty("event_key")` hoặc naming strategy, deserialize có thể cho `eventKey = null`. Một translator unit test dựng DTO bằng constructor **không phát hiện lỗi serialization này**.

Test contract nên giải mã **raw JSON fixture** rồi assert fields trước khi gọi translator; đối với outbound, serialize external request và assert **wire names** chứ không chỉ record getters.

### 27.3. Nguồn version và drift detection

| Tình huống | Test nên có |
|---|---|
| Partner v1 vẫn phát sinh | Fixture v1 vẫn decode/map được theo policy. |
| Partner thêm field tùy chọn | Tương thích hoặc reject theo chính sách đã duyệt. |
| Partner bỏ field bắt buộc | Không biến thiếu field thành default nguy hiểm. |
| Partner đổi integer sang string | Parser/translator không âm thầm ép sai. |
| Partner đổi nghĩa enum cũ | Semantic contract review và regression test. |
| Partner gửi unknown version | Quarantine/unsupported version, có telemetry. |
| Partner đổi cách biểu diễn timestamp | Test zone/offset/precision. |
| Partner đổi source identifier scope | Test resolver và migration mapping. |

**Schema compatibility không đồng nghĩa semantic compatibility.** Một JSON vẫn hợp lệ về kiểu nhưng `S2` đã đổi nghĩa là một breaking change về domain.

## 28. Flow test Spring Integration: giữ logic ACL thật, mock transport

Một flow test hữu ích nên chạy:

~~~text
Message<PartnerDeliveryEventV1>
    → Contract validation
    → Reference resolver (fake store)
    → PartnerDeliveryTranslator thật
    → Message<DeliveryUpdate>
    → QueueChannel quan sát
~~~

### 28.1. Mẫu kiểm thử channel

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig({
        PartnerIngressConfig.class,
        PartnerIngressTestBeans.class
})
class PartnerAclIntegrationFlowTest {

    @Autowired
    @Qualifier("decodedPartnerEvents")
    DirectChannel input;

    @Autowired
    @Qualifier("internalDeliveryUpdates")
    QueueChannel output;

    @Test
    void translatesAtTheBoundaryAndPreservesTrustedContext() {
        TrustedPartnerContext trusted =
                new TrustedPartnerContext(
                        "partner-a", "VN", "customer-vn");

        PartnerDeliveryEventV1 external =
                new PartnerDeliveryEventV1(
                        "evt-4280", "SHIP-2026-000428",
                        "S2", "2026-11-23T16:00:00+07:00",
                        "customer-vn");

        boolean accepted = input.send(
                MessageBuilder.withPayload(external)
                        .setHeader("verifiedPartnerContext", trusted)
                        .setHeader("traceId", "test-trace-2048")
                        .build());

        assertTrue(accepted);
        Message<?> observed = output.receive(1_000);
        assertNotNull(observed);
        assertInstanceOf(DeliveryUpdate.class,
                observed.getPayload());

        DeliveryUpdate result =
                (DeliveryUpdate) observed.getPayload();
        assertEquals("shp-2048", result.shipmentId());
        assertEquals(DeliveryStatus.DELIVERED, result.status());
        assertEquals("VN", result.tenantId());
    }
}
~~~

`PartnerIngressTestBeans` là cấu hình test cần **cung cấp `PartnerDeliveryTranslator` và fake `ShipmentReferenceResolver`** tương ứng; ví dụ có tính minh họa, không phải test có thể biên dịch độc lập khi thiếu các lớp/bean đã định nghĩa ở trên.

**Quan trọng về bảo mật:** test gắn `verifiedPartnerContext` bằng code kiểm thử được tin cậy để xác minh flow logic. Nó **không chứng minh** bất kỳ HTTP caller nào cũng bị chặn nếu cố gửi header cùng tên. Muốn xác nhận trust boundary, phải có test inbound adapter/auth layer thực, trong đó các untrusted headers bị strip và context chỉ được tạo sau xác thực.

### 28.2. Vì sao nên có ít nhất hai flow tests?

- **Happy path:** correct payload → correct `DeliveryUpdate`.
- **Negative path:** wrong tenant/unknown external state → **không có domain side effect**, có error/rejection theo thiết kế.

Nếu flow dùng `DirectChannel`, exception có thể truyền về caller. Nếu có `ExecutorChannel`/poller, error path có thể bất đồng bộ; test phải quan sát đúng `ErrorMessage`/recovery channel. Đừng chỉ khẳng định `send()` không throw là thành công.

## 29. Adapter integration tests: kiểm tra giao thức mà flow test chưa thể chứng minh

| Adapter | Fixture phù hợp | Bằng chứng pass |
|---|---|---|
| **File** | `@TempDir`, ready files, parser thực | File đúng được phát, file partial bị loại. |
| **SFTP** | SFTP server thử nghiệm, host key/credentials test | Remote file được tải/gửi đúng, reconnect theo policy. |
| **HTTP inbound** | HTTP client/test server hoặc MockMvc khi phù hợp | Status/body/headers, auth, input mapping. |
| **HTTP outbound** | HTTP stub/test server | Method, path, body, reply status, TLS/timeout khi cần. |
| **JMS** | Broker thử nghiệm | Destination, JMS properties, transaction, ack/redelivery. |
| **AMQP** | RabbitMQ broker thử nghiệm | Exchange/routing, ack/nack, confirm, DLX. |
| **Kafka** | Kafka broker thử nghiệm | Topic/key/partition/schema, offset/commit, DLT. |
| **JDBC** | Database test cùng engine production khi cần | Query, mapping, transaction, locking, claim/restart. |

**Flow test thành công không chứng minh transport integration thành công.** Ví dụ mock outbound handler nhận `PartnerReserveRequestV2` không đủ chứng minh HTTP serializer gửi đúng `snake_case` hoặc Kafka key được gắn đúng partition.

### 29.1. Fault injection không làm mất trạng thái

Các test transport nên có:

1. Source unavailable, adapter retry/backoff giới hạn.
2. Decoder/schema error được đưa tới error path có ý nghĩa.
3. ACL unknown status được quarantine, không “fixed” bằng retry transport vô hạn.
4. Side effect đã thành công nhưng response/ACK bị mất → idempotency và readback.
5. Restart trước/sau checkpoint → không bỏ sót hoặc tạo side effect trùng ngoài chính sách.
6. Recovery path tự thất bại → không coi source message handled nếu chưa bảo đảm durability.

## 30. Ma trận kiểm thử ACL tổng thể

| # | Tình huống | Tầng | Điều cần xác minh |
|---:|---|---|---|
| 1 | Partner status `S1` | Unit | Map thành `IN_TRANSIT` đúng. |
| 2 | Partner status `S2` | Unit | Map thành `DELIVERED` đúng. |
| 3 | Unknown status `S9` | Unit | Reject; không default sai. |
| 4 | Missing external event key | Unit | Invalid contract. |
| 5 | Empty external reference | Unit | Invalid contract. |
| 6 | Wrong client code | Unit/security | Tenant mismatch, không tạo command. |
| 7 | Unresolved reference | Unit/integration | Không tạo internal ID bằng heuristic. |
| 8 | Partner A/B dùng trùng external ref | Resolver test | Mapping cách ly theo partner. |
| 9 | Tenant A/B dùng trùng external ref | Resolver test | Mapping cách ly theo tenant. |
| 10 | Reference changed after cache | Resolver integration | Cache invalidation/TTL theo contract. |
| 11 | Timestamp với +07:00 | Unit | Đúng `Instant` UTC. |
| 12 | Timestamp không có offset | Unit | Reject hoặc dùng zone theo contract rõ. |
| 13 | Timestamp invalid | Unit | Error có reason, không dùng default now. |
| 14 | Decimal currency precision | Unit | Không mất đơn vị/precision. |
| 15 | Missing vs null field | Contract | Đúng semantics update/clear. |
| 16 | V1 JSON snake_case | Contract | Deserialize đúng Java DTO. |
| 17 | V2 schema | Contract | Decode và translate version phù hợp. |
| 18 | Unknown contract version | Contract | Quarantine/unsupported. |
| 19 | Same field type, changed meaning | Semantic regression | Không coi schema pass là domain pass. |
| 20 | Inbound flow valid message | Spring flow | Domain payload/header đúng. |
| 21 | Inbound flow invalid message | Spring flow | Không có domain side effect. |
| 22 | Header giả mạo trusted context từ HTTP | HTTP security | Bị strip/reject, không cấp tenant sai. |
| 23 | Outbound command valid | Unit/flow | Partner DTO đúng status/service code. |
| 24 | Outbound unsupported service code | Unit | Reject trước remote call. |
| 25 | HTTP reply `PENDING` | Contract | Không map thành completed. |
| 26 | HTTP 202 | HTTP integration | Pending/accepted semantics đúng. |
| 27 | HTTP 400 invalid request | HTTP integration | Error classification, không retry mù. |
| 28 | HTTP 503 transient | HTTP integration | Retry bounded/backoff. |
| 29 | HTTP timeout sau POST | E2E | Readback/idempotency, không duplicate. |
| 30 | File chưa ready | File integration | Không đọc file partial. |
| 31 | File có row sai | File integration | Atomic/partial error policy rõ. |
| 32 | SFTP mất kết nối | SFTP integration | Reconnect/partial transfer đúng. |
| 33 | JMS redelivery | JMS integration | No duplicate side effect. |
| 34 | AMQP DLQ | AMQP integration | Bản lỗi thật có trong queue. |
| 35 | Kafka schema drift | Kafka integration | Reject/quarantine đúng; offset policy. |
| 36 | Kafka message đến sai thứ tự | Domain integration | Stale event được xử lý theo policy. |
| 37 | JDBC hai poller cùng source | DB integration | Claim/transaction đúng. |
| 38 | Domain state transition không hợp lệ | Domain test | Domain reject, ACL không bypass. |
| 39 | Same event ID redelivery | Domain/inbox | Idempotency. |
| 40 | Quarantine publisher failure | Recovery integration | Không false ACK. |
| 41 | Contract v1/v2 chạy song song | Migration test | Mỗi version đúng mapping. |
| 42 | Shadow comparison mapping v1/v2 | Migration | Không sinh side effect trong shadow. |
| 43 | Rollback ACL version | Migration | Event đang chờ xử lý không bị mất. |
| 44 | Secret trong error payload | Security | Redact và hạn chế quyền đọc. |
| 45 | Cross-tenant ID lookup | Security | Không lộ dữ liệu tenant khác. |
| 46 | Parallel flow test | Isolation | Không dùng chung mutable state. |
| 47 | Restart với persistent metadata | Recovery | Checkpoint và dedupe bền. |
| 48 | Fallback schema không được phép | Contract | Không tự đoán/trả success. |
| 49 | Latency của resolver tăng | Performance | Có SLO và degradation policy. |
| 50 | Target đã hoàn thành nhưng upstream ACK mất | E2E | Reconciliation đúng kết quả cuối. |

Không cần chạy cùng một danh sách ở mọi transport. Mỗi mục phải gắn **đúng component đang được kiểm tra**, dữ liệu test, expected outcome, timeout, cleanup và evidence. Một assertion “không thấy exception” không chứng minh ACL đã map đúng, càng không chứng minh hệ thống đích đã nhận và lưu dữ liệu.

## 31. Case study: đối tác giao hàng đa giao thức

### 31.1. Bối cảnh

Một nền tảng nội bộ quản lý shipment. **Đối tác A** gửi CSV qua SFTP mỗi 15 phút, dùng `booking_ref`/`S1`/`S2`. **Đối tác B** gửi Kafka event JSON, dùng `shipment_reference` và `DELIVERY_COMPLETED`. Nội bộ chỉ muốn hiểu một sự kiện `DeliveryUpdate` với `shipmentId`, `status`, `occurredAt` và `tenantId`.

~~~mermaid
flowchart LR
    A["Partner A<br/>SFTP CSV"] --> S["SFTP/File adapters"]
    B["Partner B<br/>Kafka JSON"] --> K["Kafka inbound adapter"]
    S --> PA["ACL A<br/>CSV/phase/reference"]
    K --> PB["ACL B<br/>JSON/status/reference"]
    PA --> INTERNAL["Internal DeliveryUpdate"]
    PB --> INTERNAL
    INTERNAL --> VALID["Domain invariant + inbox dedupe"]
    VALID --> STORE["Shipment aggregate / persistence"]
    STORE --> EVENTS["Internal domain event"]
~~~

Mỗi ACL có **ngôn ngữ riêng của partner**; cả hai phát ra **một model đúng theo ngữ nghĩa nội bộ**, không ép partner B phải dùng mã `S2` của partner A.

### 31.2. Partner A: SFTP

Quy trình:

1. Poll SFTP sau khi file được đánh dấu ready.
2. Tải file về local folder/stream theo cấu hình, không tin filename đơn lẻ là business ID.
3. Parse/validate từng CSV row, phiên bản contract và content encoding.
4. Đối chiếu source connection với trusted partner/tenant.
5. Resolve `booking_ref`, dịch `S2` thành `DELIVERED`.
6. Đưa `DeliveryUpdate` vào application service, chống trùng theo event ID.
7. Đối soát rows thành công/lỗi theo atomicity policy; lưu quarantine có reason.

### 31.3. Partner B: Kafka

Quy trình:

1. Consumer nhận record đúng topic/partition/tenant.
2. Decoder/registry kiểm tra schema v2 và enum values.
3. Tạo trusted source context dựa trên broker identity/connection configuration đã duyệt.
4. ACL B dịch `DELIVERY_COMPLETED` thành `DELIVERED`, resolve internal shipment ID.
5. Domain xử lý stale event và dedupe.
6. Commit offset hoặc durable recovery theo policy, không ACK khi lỗi chưa được xử lý nếu contract yêu cầu.

### 31.4. Điều không được xảy ra

- Domain if/else đọc thẳng `S2` hoặc `DELIVERY_COMPLETED`.
- Hai external IDs trùng giữa partner bị coi là cùng shipment.
- CSV timestamp local tự dùng timezone máy chạy.
- Unknown status mặc định `DELIVERED`.
- Một lỗi Kafka schema bị retry xử lý mãi mà không quarantine.
- Một business event hoàn tất được áp dụng hai lần do source redeliver.

### 31.5. Bằng chứng nghiệm thu

| Bằng chứng | Nguồn |
|---|---|
| File Kafka record/source đã nhận | Adapter transport evidence. |
| External contract version đúng | Decoder/contract validator. |
| Partner reference đã resolve | Reference store/tracing. |
| Canonical internal event đúng | ACL unit/flow test. |
| Domain transition hợp lệ | Domain tests/DB state. |
| Không side effect trùng | Inbox/idempotency store và readback. |
| Event lỗi được bảo toàn | Quarantine/DLT persisted record. |
| Restart không mất backlog | Recovery/transport test. |

## 32. Case study: thay nhà cung cấp HTTP mà không đổi domain

### 32.1. Trạng thái hiện tại

Domain yêu cầu `ReserveShipmentCommand` nhưng đang dùng partner A:

~~~text
ReserveShipmentCommand
   → ACL Partner A
   → HTTP API A POST /v1/bookings
   → Partner A reply
   → ShipmentReservationResult
~~~

Đội muốn chuyển sang partner B, nơi endpoint là `/v2/reservations`, dùng `priority = HIGH/NORMAL` thay cho `service_code` và phản hồi `status = QUEUED/ACTIVE`.

### 32.2. Chiến lược thay dần

~~~mermaid
flowchart TD
    CMD["Internal ReserveShipmentCommand"] --> ROUTE{"Partner routing policy"}
    ROUTE -- "Cohort A" --> A["ACL A + HTTP Gateway A"]
    ROUTE -- "Cohort B" --> B["ACL B + HTTP Gateway B"]
    A --> MAPA["A reply translator"]
    B --> MAPB["B reply translator"]
    MAPA --> RES["ShipmentReservationResult"]
    MAPB --> RES
~~~

Phần còn lại của domain không nên có code:

~~~java
if (partner.equals("B")) {
    // Domain hiểu QUEUED/ACTIVE của một vendor mới.
}
~~~

Thay vào đó, routing ở **application/integration policy**, còn translator B chịu trách nhiệm ánh xạ status và error riêng; domain chỉ biết `PENDING`, `CONFIRMED` hoặc kết quả nội bộ đã được thiết kế.

### 32.3. Shadow mode không được tạo side effect trùng

Nếu chạy A và B đồng thời để so sánh mapping, tránh **gửi cả hai yêu cầu tạo booking thật** vì sẽ gây hai shipment. Có thể:

- Chạy translation B ở chế độ **dry-run** trên bản request đã được redaction; không gọi API tạo.
- So sánh các trường được kỳ vọng tương đương về ngữ nghĩa.
- Thử B trên sandbox/tenant test riêng với IDs riêng.
- Chỉ khi contract và side effect được chứng minh, chuyển cohort theo feature flag.

**Không gọi shadow traffic là an toàn chỉ vì request có header `X-Shadow: true`** nếu partner không cam kết sẽ không tạo side effect.

## 33. Di trú sang ACL từ kiến trúc chưa có biên rõ ràng

Một hệ thống lâu năm có thể đã phân tán mapping vendor trong service, repository và message listener. Không cần big-bang rewrite.

### 33.1. Các bước di trú có kiểm soát

1. **Inventory:** xác định external types, status codes, SQL tables, protocol headers đang rò vào domain.
2. **Thiết lập vocabulary nội bộ:** thống nhất command/result/event và invariants với domain owner.
3. **Khoanh vùng một use case:** chọn một flow có tác động cao và contract đủ hiểu.
4. **Thêm translator tại biên:** giữ domain public interface ổn định, đưa vendor conversion ra ngoài.
5. **Characterization tests:** khóa hành vi hiện tại tốt và các lỗi đã biết.
6. **Contract tests:** dùng fixtures partner thật/sandbox, bao gồm v1/v2 và lỗi.
7. **Dual-run không side effect hoặc shadow validation:** so sánh mapping trước/sau trong phạm vi an toàn.
8. **Feature flag/canary:** chuyển dần một cohort có rollback plan.
9. **Quan sát unknown/compat drift:** theo dõi quarantine, mismatches và target outcome.
10. **Gỡ coupling cũ:** xóa import DTO/vendor enums khỏi domain sau khi mọi flow đã chuyển và test pass.

### 33.2. Tiêu chí rollback

- Tăng `UNKNOWN_EXTERNAL_STATUS` hoặc unresolved reference bất thường.
- Domain transitions sai lệch so với baseline được duyệt.
- Tăng duplicate/unknown outcome hoặc lỗi cross-tenant.
- Partner v1/v2 mapping không còn tương thích.
- Side effect ở đích không khớp khi reconciliation.

Rollback không chỉ là chuyển cờ: cần biết **message đang chờ ở channel/broker**, version của serialized payload và idempotency state. Nếu version cũ không đọc được event do version mới phát ra, rollback có thể tạo thêm lỗi; test phải bao phủ khả năng tương thích đó.

## 34. Anti-pattern thường gặp khi thiết kế ACL

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Domain import external DTO | Vendor đổi schema làm vỡ core. | Chỉ đưa internal command/event qua biên. |
| DTO field rename được gọi là ACL đầy đủ | Không giải quyết semantic mismatch. | Tách state/ID/time/unit/error translation. |
| Dùng external enum trong domain | S2/S9 xuất hiện khắp business code. | Domain enum/value object riêng. |
| Default unknown status thành success | Áp dụng sai trạng thái nghiệp vụ. | Reject/quarantine unknown semantics. |
| Đoán internal ID từ string prefix | Collision, cross-tenant và mapping sai. | Reference resolver có scope/owner. |
| Tin tenant ID tự khai trong payload | Rò dữ liệu và xử lý chéo tenant. | Trusted context + đối chiếu claims. |
| Bỏ qua timezone khi parse thời gian | Event áp dụng sớm/muộn. | Offset/zone theo contract, dùng Instant. |
| Dùng double cho tiền | Precision/rounding lỗi. | Money/value object + BigDecimal policy. |
| Canonical enterprise schema quá lớn | Coupling và field vendor tràn vào “chuẩn”. | Canonical theo bounded context, ACL theo partner. |
| ACL chứa toàn bộ business logic | Hai nguồn chân lý nghiệp vụ. | Domain giữ invariants, ACL giữ translation. |
| Converter ẩn transaction/network | Unit test khó; retry boundary mơ hồ. | Tách pure translation với resolver/service I/O. |
| Bắt mọi exception thành invalid contract | Retry transport sai. | Classify transport, contract, domain, unknown outcome. |
| Retry POST timeout mù quáng | Side effect trùng. | Idempotency/readback và reconcile. |
| Quarantine chỉ log rồi bỏ message | Mất dữ liệu khi restart. | Durable recovery và redrive. |
| Thay ACL nhưng không test parser | JSON snake_case mất fields. | Raw payload contract tests. |
| Chỉ test happy path | Unknown code/duplicate/version drift lọt. | Negative tests, concurrency/recovery. |
| Response 202 bị map completed | Sai trạng thái workflow. | Pending/accepted domain outcome riêng. |
| Shadow gọi API ghi dữ liệu thật | Tạo hai đối tượng/side effects. | Dry-run mapping hoặc sandbox cô lập. |
| Không có owner cho contract mapping | Không ai xác nhận nghĩa code mới. | RACI/domain review/version governance. |
| Log raw payload và token | Lộ dữ liệu nhạy cảm. | Redaction, data minimization, access control. |

## 35. Quyết định kiến trúc: chọn đúng trách nhiệm và ownership

Một ACL tốt không chỉ có code mapper; nó cần **quy tắc ra quyết định và người chịu trách nhiệm** để không biến thành một đống if/else không ai dám thay.

| Quyết định | Chủ thể nên tham gia | Bằng chứng cần có |
|---|---|---|
| Ý nghĩa external status | Partner contract owner + domain owner | Mapping matrix/version được xác nhận. |
| Internal domain vocabulary | Domain owner | Model/invariants và use-case tests. |
| Identifier uniqueness/scope | Domain/data owner + integration team | Reference schema/constraints và migration plan. |
| Trusted partner/tenant mapping | Security/identity + integration team | Auth/source identity và authorization tests. |
| Lỗi được retry | Operations/integration + domain owner | Retry/error policy và idempotency analysis. |
| Quarantine và redrive | Operations/data governance | Durability, owner, retention, access control. |
| Contract version sunset | Partner owner + product/domain | Usage metrics, compatibility tests, cutoff dates. |
| Backward compatible rollout | Platform/integration + partner owner | Canary/rollback/evidence. |
| Business reconciliation | Domain owner + operations | Target readback và exception workflow. |

### 35.1. Mẫu decision record ngắn

~~~yaml
# Quyết định minh họa; không phải cấu hình Spring Integration.
decision:
  id: ACL-DELIVERY-004
  title: Translate partner phase S2 to internal DELIVERED
  scope:
    partner: partner-a
    contractVersion: 1
    internalBoundedContext: shipment
  interpretation:
    externalValue: S2
    internalValue: DELIVERED
    confirmedBy: partner-contract-owner
  prerequisites:
    - verified-source-tenant
    - resolved-internal-shipment-id
    - valid-event-timestamp
  unsupportedValuePolicy: QUARANTINE
  evidence:
    - contract-fixture-v1
    - semantic-regression-test
    - partner-acceptance-record
  supersedes: null
~~~

Đây là **mẫu decision record**. Giá trị `confirmedBy` phải được điền bằng owner/bằng chứng thật trong dự án, không dùng một giá trị mẫu làm căn cứ triển khai production.

### 35.2. Khi nào ACL nên nói “không biết”?

ACL không nên đoán khi:

- Partner gửi trạng thái mới chưa được định nghĩa.
- External ID chưa thể xác định entity nội bộ.
- Unit/currency/time zone thiếu hoặc mâu thuẫn.
- Tenant trong payload khác với kết nối đã xác thực.
- Reply có trạng thái `ACCEPTED` nhưng domain cần `COMPLETED`.
- Contract version chưa hỗ trợ.

Không biết là một **trạng thái kỹ thuật/ngữ nghĩa hợp lệ cần được xử lý**, không phải lý do để tạo dữ liệu mặc định. Tùy rủi ro, message có thể được quarantine, chờ mapping, báo lỗi cho caller hoặc gửi workflow reconciliation.

## 36. Quy trình xử lý một sự cố contract drift

Giả sử đối tác bắt đầu gửi `phase = "S9"` nhưng ACL chỉ hỗ trợ `S1`, `S2` và `R1`.

### 36.1. Phát hiện và bảo toàn

1. Schema decoder nhận được message hợp lệ về cấu trúc.
2. ACL gặp unknown phase và tạo lỗi `UNKNOWN_EXTERNAL_STATUS`.
3. Error flow **không** chuyển message thành `DELIVERED` và không âm thầm drop.
4. Lưu quarantine/failed reference có quyền truy cập, phiên bản contract và correlation.
5. Retry classifier nhận biết lỗi **không thể được sửa bằng cách lặp lại cùng payload ngay lập tức**.
6. Vận hành nhận cảnh báo theo ngưỡng; source ACK/offset theo **durable recovery policy** đã thiết kế.

### 36.2. Xác minh ngữ nghĩa

Đội tích hợp hỏi contract owner: `S9` có nghĩa gì, có liên quan tới status nội bộ nào? Domain owner quyết định:

- Map `S9` vào một trạng thái hiện có nếu thực sự cùng nghĩa.
- Bổ sung một trạng thái/domain event mới nếu sự kiện thể hiện một khái niệm mới quan trọng.
- Chỉ lưu làm metadata/audit không thay đổi aggregate nếu domain không cần áp dụng.
- Từ chối nếu partner đang vi phạm hợp đồng và yêu cầu sửa upstream.

### 36.3. Triển khai và redrive

1. Tạo fixture `S9` và negative/positive unit tests.
2. Chạy contract tests raw payload và mapping.
3. Cập nhật translator theo version, không đổi mapping `S2` cũ.
4. Deploy qua canary hoặc rollout có kiểm soát.
5. Redrive message từ quarantine với `eventId` gốc, kiểm tra stale version và idempotency.
6. Xác nhận trạng thái nội bộ và outcome cuối, rồi mới resolve quarantine record.

### 36.4. Không tạo retry storm

Nếu hàng nghìn message `S9` đến trong vài phút, việc retry tức thì làm tăng tải và giữ queue. Dùng quarantine có owner, alert gộp và redrive sau khi mapping được sửa. Đây là một ví dụ cho thấy **ACL, retry, error handling và operations là các phần bổ sung nhau**, không thay thế nhau.

## 37. Mẫu đặc tả biên tích hợp dùng lại

~~~yaml
# Mẫu học tập: không phải application.yml của Spring Integration.
aclBoundary:
  id: partner-a-delivery-v1
  ownerTeam: integration-platform
  language: vi

  externalContext:
    partnerId: partner-a
    protocol: SFTP
    schemaVersion: 1
    sourceIdentity: authenticated-sftp-account
    payloadType: PartnerDeliveryEventV1
    readinessRule: ready-marker

  trust:
    verifiedContext:
      - partnerId
      - tenantId
      - authenticatedClientCode
    claimedFields:
      - clientCode
    mismatchPolicy: REJECT

  translation:
    input: PartnerDeliveryEventV1
    output: DeliveryUpdate
    identityResolver: ShipmentReferenceResolver
    status:
      S1: IN_TRANSIT
      S2: DELIVERED
      R1: RETURNED
    unknownStatus: QUARANTINE
    timestampRule: REQUIRE_OFFSET
    preserve:
      - eventId
      - traceId
      - contractVersion

  errors:
    invalidContract: QUARANTINE
    unresolvedReference: RECONCILE
    domainConflict: DOMAIN_REJECTION
    transientTransport: BOUNDED_RETRY
    unknownOutboundOutcome: READBACK_BEFORE_RETRY

  delivery:
    businessIdempotencyKey:
      - tenantId
      - partnerId
      - eventId
    durableRecoveryRequired: true
    replayRequiresAuthorization: true

  verification:
    - translator-unit-tests
    - raw-contract-fixtures
    - spring-integration-flow-tests
    - sftp-adapter-integration-tests
    - restart-and-redrive-tests
    - security-boundary-tests

  observability:
    metrics:
      - translation_result
      - unknown_status
      - unresolved_reference
      - quarantine_oldest_age
      - confirmed_processing_latency
    redactRawPayload: true
~~~

### 37.1. Cách sử dụng mẫu

Mỗi mục phải có **contract owner và evidence**. Ví dụ `RECONCILE` cần giải thích ai đối soát, ở đâu lưu pending record và SLA xử lý; `QUARANTINE` cần giải thích durability, retention và quyền redrive; `REQUIRE_OFFSET` phải được kiểm tra với cả timestamp hợp lệ và invalid.

Không đặt toàn bộ YAML trên vào ứng dụng rồi kỳ vọng Spring tự tạo các endpoint. Đây là **mẫu mô tả kiến trúc và kiểm thử**, cần được triển khai thành configuration, translators, repositories, flows và runbooks riêng.

## 38. Bài tập thực hành

### Bài tập 1 — Phân biệt adapter và ACL

Với luồng `SFTP CSV → Spring Integration → Order Service`, hãy vẽ hai biên:

1. **Transport:** SFTP session, remote directory, file readiness, parser.
2. **Semantic:** status, ID, unit/time, tenant, business command.

Chỉ rõ lớp nào được phép import external DTO; lớp domain có được biết `phase = "S2"` không? Giải thích hậu quả nếu hai lớp trộn vào nhau.

### Bài tập 2 — Thiết kế translator an toàn

Tạo `PartnerDeliveryEventV1` và `DeliveryUpdate` như ví dụ, bổ sung trạng thái `DELIVERY_FAILED` của partner v2.

Yêu cầu:

1. Định nghĩa v2 DTO và mapping rule có owner.
2. Viết tests cho v1/v2, unknown status, timestamp thiếu offset.
3. Không mặc định mã unknown thành trạng thái thành công.
4. Dùng resolver cho external reference.
5. Kiểm tra tenant claims theo trusted context.

### Bài tập 3 — Unit và flow tests

Xây dựng Spring Integration `IntegrationFlow` gồm input channel, translator và output channel.

Yêu cầu:

1. Unit test translator không cần Spring context.
2. Flow test với `DirectChannel` và `QueueChannel`.
3. Gửi message với trusted context được tạo bởi fixture.
4. Assert output là internal command/event, không phải external DTO.
5. Gửi unknown status, xác minh error path và không có domain side effect.
6. Giải thích vì sao bài test chưa chứng minh SFTP/Kafka thật.

### Bài tập 4 — Contract versioning

Partner đổi v1 (`booking_ref`, `S2`) sang v2 (`shipment_reference`, `DELIVERED`).

Yêu cầu:

1. Tạo hai raw JSON fixtures.
2. Decode bằng serializer/parser thật được cấu hình.
3. Map cả hai về cùng nội bộ `DeliveryUpdate` khi semantics tương đương.
4. Tạo một change có cùng kiểu dữ liệu nhưng đổi meaning; kiểm tra hệ thống phát hiện.
5. Đề xuất cách sunset v1 và rollback v2 không làm mất event pending.

### Bài tập 5 — Reference resolver đa tenant

Tạo bảng `partner_shipment_reference` và hai tenants A/B, hai partners P/Q.

Yêu cầu:

1. Cùng external reference xuất hiện ở nhiều scope.
2. Test kết quả resolve đúng từng scope.
3. Test mapping missing, mapping bị thu hồi và cache stale.
4. Thiết kế uniqueness constraint và audit change.
5. Không đưa logic đoán ID bằng prefix vào domain.

### Bài tập 6 — HTTP outbound request/reply

Tạo `ReserveShipmentCommand` và hai DTO theo partner.

Yêu cầu:

1. Outbound translator dịch service-level sang partner code.
2. HTTP test server ghi nhận method/URI/body/headers.
3. Partner trả `PENDING`; domain result **không** được coi completed.
4. Tạo HTTP 503, 429, 400, read timeout sau POST.
5. Thiết kế idempotency/readback và test side effect chỉ xảy ra một lần logic.
6. Liên kết original internal shipment ID với reply qua correlation được kiểm soát.

### Bài tập 7 — File/SFTP/Kafka đa đối tác

Partner A gửi file CSV qua SFTP; partner B gửi JSON qua Kafka. Cả hai cập nhật trạng thái shipment.

Yêu cầu:

1. Thiết kế hai adapters/ACL độc lập.
2. Cả hai xuất `DeliveryUpdate` có nghĩa thống nhất.
3. Test file readiness, Kafka schema/topic/offset và error/recovery.
4. Test duplicate event ID và trạng thái đến ngược thứ tự.
5. Test tenant isolation và unknown status ở mỗi partner.
6. Chỉ rõ phần nào phải dùng server/broker thật.

### Bài tập 8 — Migration từ legacy integration

Hệ thống đang dùng `if ("S2".equals(event.phase()))` trong ba application services.

Yêu cầu:

1. Tìm những điểm leaky abstraction trong thiết kế.
2. Tạo translator và domain model phù hợp.
3. Viết characterization tests trước khi refactor.
4. Thiết kế canary, shadow validation không tạo side effect và rollback.
5. Ghi RACI cho partner contract/domain mapping.
6. Đề xuất metric phát hiện semantic drift.

### Bài tập 9 — Sự cố contract drift thực tế

Partner thêm mã `S9` mà không thông báo trước. Hãy xây dựng:

- Detection tại contract/semantic layer.
- Durable quarantine và error code.
- Retry classifier không lặp vô ích.
- Quy trình xác minh meaning với partner/domain owner.
- Cập nhật translator version và test regression.
- Redrive có authorization/audit/idempotency.
- Điều kiện đóng incident sau khi readback target.

### Bài tập 10 — Đánh giá kiến trúc

Thiết kế một **Architecture Decision Record (ADR)** lựa chọn giữa:

- Dùng trực tiếp external DTO trong domain.
- Một ACL riêng cho từng partner.
- Một enterprise canonical model cho tất cả hệ thống.

Nêu bối cảnh, lựa chọn, tiêu chí đánh giá, chi phí mapping, ownership, versioning, vận hành, testing và trường hợp khiến quyết định cần được xem lại.

## 39. Checklist nghiệm thu ACL tại biên hệ thống

- [ ] **Đã xác định external và internal bounded contexts**, không trộn từ vựng giữa hai bên.
- [ ] **Domain không import external DTO/exception/protocol headers** không cần thiết.
- [ ] **Transport adapter và semantic translator có trách nhiệm phân biệt**.
- [ ] **Có internal command/event/result rõ nghĩa**, được domain owner xác nhận.
- [ ] **External ID được resolve theo partner/tenant scope**, không đoán từ chuỗi.
- [ ] **Trusted context được tạo sau authentication/source verification**, không tin client header.
- [ ] **Status/enum mapping explicit**, unknown không mặc định success.
- [ ] **Time/unit/currency conversion được đặc tả**, không dùng default timezone/precision tùy tiện.
- [ ] **Contract validation khác domain invariant validation**, có error category riêng.
- [ ] **Có inbound và outbound translation** ở những hướng có kết nối.
- [ ] **Reply correlation đúng**, accepted/pending không bị nâng thành completed.
- [ ] **Schema và semantics có version management**, test v1/v2 cùng tồn tại khi cần.
- [ ] **Có contract tests trên raw payload**, không chỉ unit test DTO dựng tay.
- [ ] **Có Spring Integration flow tests** cho channel wiring và negative path.
- [ ] **Có adapter integration tests theo transport thực tế**: File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC.
- [ ] **Có idempotency/duplicate/stale-event policy**, đặc biệt khi redelivery/restart.
- [ ] **Có retry/error/quarantine/reconciliation rõ**, không xử lý unknown như lỗi transient.
- [ ] **Quarantine và DLT có durability/retention/access control** theo nhu cầu.
- [ ] **Không báo success khi mới gửi message**, có readback/evidence ở đích khi cần.
- [ ] **Có tracing/correlation và metrics**, kiểm soát cardinality và PII/secret.
- [ ] **Có owner quyết định semantic mapping**, không tự suy từ tên field.
- [ ] **Migration/canary/rollback được kiểm tra**, không tạo side effect khi shadow.
- [ ] **Test fixtures độc lập, có cleanup và timeout hữu hạn**, không dùng tài nguyên production.
- [ ] **Có checklist/risk review** khi contract partner thêm field, status, version hoặc đổi meaning.

## 40. Tổng kết

**Anti-corruption layer (ACL)** giúp bounded context nội bộ phát triển bằng **ngôn ngữ miền của chính nó** dù phải tích hợp với những hệ thống ngoài có trạng thái, định danh, đơn vị, phiên bản và giao thức khác nhau. ACL không đơn giản là đổi tên trường; nó phải **diễn giải ngữ nghĩa, xác minh trust context, resolve references, phân loại lỗi và không cho external assumptions rò vào domain**. Đồng thời, ACL không thay thế domain invariants, transport security, transaction, idempotency hoặc durable recovery.

Trong Spring Integration, ACL có thể được đặt giữa **inbound adapter/gateway và application-facing `MessageChannel`**, cũng như giữa **internal command và outbound adapter/gateway**. File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC có cách nhận/gửi và semantics ACK/offset/transaction khác nhau; translation bảo vệ miền nhưng **chỉ adapter/transport integration tests mới chứng minh được I/O thật**, còn **end-to-end tests** xác nhận business side effect cuối.

Một ACL có chất lượng phải trả lời được: **dữ liệu từ partner nào, phiên bản hợp đồng nào, nhận dạng nguồn/tenant đã được xác thực ra sao, external ID map tới object nội bộ nào, giá trị bên ngoài mang nghĩa gì, lỗi nào phải cách ly, event có thể bị giao lại không, và bằng chứng nào xác nhận domain đã xử lý đúng**. Khi những câu hỏi này có câu trả lời rõ ràng, hệ thống có thể thêm đối tác mới, thay nhà cung cấp hoặc nâng cấp giao thức mà không làm ô nhiễm mô hình nghiệp vụ cốt lõi.
