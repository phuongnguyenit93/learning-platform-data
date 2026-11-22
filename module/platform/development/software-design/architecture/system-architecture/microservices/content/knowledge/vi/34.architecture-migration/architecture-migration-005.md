# Lớp chống xâm nhập để bảo vệ mô hình mới khỏi hệ thống cũ

## 1. Bối cảnh: tích hợp legacy có thể kéo mô hình mới trở lại cách nghĩ cũ

Khi hiện đại hóa một hệ thống lâu năm, nhóm phát triển thường không thể thay thế toàn bộ ứng dụng trong một lần. Các dịch vụ mới phải cùng tồn tại với ERP, billing, CRM, mainframe, database dùng chung, file batch hoặc API cũ. Những hệ thống này có thể sử dụng tên trường, trạng thái, quy tắc nghiệp vụ và giao thức khác nhau.

Ví dụ, hệ thống mới có mô hình đơn hàng:

```text
Order
- orderId
- customerId
- totalAmount
- currency
- status: DRAFT | CONFIRMED | CANCELLED
- lines[]
```

Trong khi hệ thống cũ chỉ cung cấp:

```text
LEGACY_ORD_HDR
- DOC_NO
- CUST_NO
- NET_AMT
- CURR_CD
- DOC_STS: "0", "1", "9"

LEGACY_ORD_DTL
- DOC_NO
- ITEM_NO
- QTY
- UNIT_NET
```

Những mã trạng thái `0`, `1` và `9` có thể mang ý nghĩa lịch sử riêng, và `NET_AMT` có thể chưa bao gồm thuế hoặc phí vận chuyển. Nếu mô hình mới trực tiếp sử dụng những trường, enum và quy tắc của legacy, các khái niệm cũ sẽ lan vào domain mới. Khi đó, nhóm mới khó thay thế hệ thống cũ vì implementation mới đã phụ thuộc sâu vào cách biểu diễn cũ.

**Anti-Corruption Layer (ACL), hay lớp chống xâm nhập**, là một ranh giới tích hợp chuyển đổi mô hình và ngữ nghĩa giữa hệ thống bên ngoài và mô hình nội bộ. ACL bảo vệ domain model mới khỏi bị chi phối bởi API, schema, thuật ngữ, protocol và quy tắc của legacy hoặc một bounded context khác.

ACL không chỉ đổi tên field. Nó cần giữ cho **ý nghĩa nghiệp vụ trong mô hình mới nhất quán**, đồng thời cô lập những khác biệt và giới hạn của hệ thống cũ ở một vị trí có thể kiểm soát, quan sát, kiểm thử và dần thay thế.

### Mục tiêu học tập

Sau bài học, bạn có thể:
1. Giải thích vai trò của ACL trong Domain-Driven Design và chuyển đổi kiến trúc.
2. Phân biệt ACL với adapter kỹ thuật, facade, API gateway, mapper và shared domain model.
3. Xác định những khác biệt về ngôn ngữ, trạng thái, dữ liệu, transaction và lỗi cần được cách ly.
4. Thiết kế mô hình dịch thuật giữa legacy contract và domain model mới.
5. Xử lý đồng bộ, bất đồng bộ, retry, idempotency và consistency qua ranh giới.
6. Tổ chức ACL theo bounded context và quyền sở hữu dữ liệu.
7. Triển khai strangler migration mà không làm legacy semantics lan vào hệ thống mới.
8. Kiểm thử contract, mapping, lỗi và các trường hợp dữ liệu lịch sử.
9. Theo dõi chất lượng tích hợp và lập lộ trình thu hẹp hoặc loại bỏ ACL khi legacy được thay thế.

## 2. Anti-Corruption Layer là gì?

Trong DDD, mỗi bounded context có mô hình, ngôn ngữ và quy tắc có hiệu lực bên trong ranh giới của nó. Hai context có thể cùng dùng từ “Customer” nhưng không có nghĩa chúng mô tả cùng một khái niệm.

Ví dụ:
- CRM xem Customer là hồ sơ quan hệ, marketing preferences và lịch sử tương tác.
- Billing xem Customer là bên chịu trách nhiệm thanh toán, địa chỉ xuất hóa đơn và điều khoản tín dụng.
- Identity xem User là principal có credential, roles và trạng thái xác thực.
- Commerce xem Buyer là người thực hiện giao dịch và nhận trải nghiệm mua hàng.

Nếu hệ thống mới import trực tiếp DTO hoặc entity của CRM, model của CRM có thể trở thành ngôn ngữ mặc định trong Commerce. Một thay đổi CRM có thể buộc Commerce sửa code dù ý nghĩa nghiệp vụ Commerce không thay đổi.

ACL tạo ranh giới:

```text
      Legacy CRM Context
  API / DTO / schema / status codes
                |
                v
       [ ACL / Translator ]
       - protocol adapter
       - validation
       - semantic mapping
       - error translation
       - identity correlation
                |
                v
       New Commerce Context
       Buyer / Purchase / Order
       rules and invariants owned here
```

ACL:
- Đọc contract của hệ thống ngoài.
- Xác thực và chuyển đổi dữ liệu thành ngôn ngữ nội bộ.
- Ánh xạ trạng thái và hành vi theo business meaning.
- Cô lập protocol, lỗi và quirks của legacy.
- Giữ nguyên invariants của domain mới.
- Ngăn kiểu dữ liệu và enum nội bộ của legacy rò rỉ qua public boundary.
- Cung cấp một nơi tập trung để đo, kiểm thử và thay thế integration.

**ACL là một boundary có trách nhiệm ngữ nghĩa**, không phải một thư viện mapping tự động được đặt tên cho đẹp.

## 3. Vì sao legacy có thể “xâm nhập” domain mới?

Có nhiều kiểu xâm nhập.

### 3.1 Xâm nhập ngôn ngữ

Code mới bắt đầu dùng các tên như `DOC_NO`, `CUST_NO`, `FLG_09` hoặc `LEGACY_STATUS_1` trong domain entity. Từ vựng của hệ cũ lan vào business logic mới, khiến mô hình không còn phản ánh ngôn ngữ mà domain team thống nhất.

### 3.2 Xâm nhập cấu trúc dữ liệu

Domain mới dùng trực tiếp:
- Legacy DTO làm parameter cho service.
- Legacy JPA entity trong domain layer.
- Database column type và nullable rules của hệ cũ.
- Enum status có giá trị số hoặc chuỗi lịch sử.
- Một shared model library được nhiều context cùng sửa.

Điều này làm thay đổi schema cũ lan qua nhiều module.

### 3.3 Xâm nhập quy tắc nghiệp vụ

Ví dụ legacy cho phép một đơn hàng chuyển từ `CANCELLED` trở lại `OPEN` vì có quy trình reopen nội bộ. Domain mới không cho phép transition đó sau khi đã hoàn tiền. Nếu logic cũ được copy nguyên trạng, invariants của mô hình mới bị phá vỡ.

### 3.4 Xâm nhập lỗi và giao thức

Legacy trả HTTP 200 với error code trong body, hoặc SOAP fault, file response có header lỗi riêng. Nếu domain service phải biết các quy tắc đó, chi tiết protocol đã thoát khỏi boundary.

### 3.5 Xâm nhập vận hành

Mô hình mới phụ thuộc vào:
- Batch chạy đúng một giờ cố định.
- Legacy chỉ hỗ trợ một request tại một thời điểm.
- Timeout không phân biệt “chưa xử lý” và “đã xử lý nhưng response mất”.
- Một field chỉ được cập nhật qua màn hình cũ.
- Legacy cần session cookie hoặc credential dùng chung.

Những hạn chế này phải được chuyển thành chính sách tích hợp rõ, không rải thành các workaround trong mọi use case.

## 4. Phân biệt ACL với các pattern gần nhau

| Pattern | Trách nhiệm chính | Quan hệ với ACL |
| --- | --- | --- |
| **Adapter** | Chuyển interface/protocol để hai thành phần tương thích | Có thể là một phần kỹ thuật của ACL |
| **Translator/Mapper** | Chuyển dữ liệu và ý nghĩa giữa hai model | Là thành phần trung tâm của ACL |
| **Facade** | Cung cấp interface đơn giản cho subsystem phức tạp | Có thể đứng trước ACL, nhưng không nhất thiết dịch ngữ nghĩa domain |
| **API Gateway** | Routing, auth, rate limit, edge concerns | Thường ở ranh giới mạng; không thay thế domain translation |
| **DTO mapper** | Copy/chuyển cấu trúc object | Không đủ nếu business semantics khác nhau |
| **Strangler Fig** | Thay thế dần chức năng legacy theo từng phần | ACL thường bảo vệ phần mới trong giai đoạn chuyển đổi |
| **Shared Kernel** | Chia sẻ một phần model/code giữa các contexts theo thỏa thuận chặt | Có mục tiêu khác; không dùng shared model để ép mọi context giống nhau |
| **Open Host Service** | Context cung cấp interface công khai ổn định cho consumer | Có thể là contract ở phía provider, ACL ở phía consumer |

Ví dụ một API Gateway có thể xác thực JWT và route request tới Legacy SOAP Adapter. Nhưng nếu field `CUSTOMER_TYPE=03` cần được diễn giải thành `BusinessBuyer` hoặc `ConsumerBuyer` theo quy tắc Commerce, việc đó thuộc domain translation trong ACL.

Một adapter kỹ thuật chỉ giúp lời gọi thành công; ACL còn bảo đảm **ý nghĩa nhận được đúng với mô hình nội bộ**.

## 5. ACL trong Context Map của DDD

Context Map mô tả quan hệ giữa bounded contexts. Những quan hệ phổ biến có thể gồm:
- Upstream/downstream.
- Customer/Supplier.
- Conformist.
- Anti-Corruption Layer.
- Open Host Service.
- Published Language.
- Shared Kernel.

Khi một context upstream không thể hoặc không nên thay đổi theo nhu cầu downstream, downstream có thể xây ACL.

```text
[Legacy Billing Context]
      |
      | legacy invoice schema / API
      v
[Billing ACL owned by New Finance Context]
      |
      | Invoice, Money, TaxBreakdown
      v
[New Finance Domain]
```

ACL thuộc về **context được bảo vệ** hoặc team sở hữu integration cho context đó, vì team này hiểu mô hình nội bộ cần bảo vệ. Provider legacy vẫn sở hữu contract và dữ liệu của mình.

Nếu ACL đặt trong legacy team và buộc mô hình mới phải dùng DTO của legacy, boundary có thể đảo ngược mục tiêu. Hai bên có thể cùng hợp tác thiết kế contract, nhưng consumer cần kiểm soát cách dịch vào domain của mình.

### Khi nào nên dùng?

ACL đặc biệt hữu ích khi:
- Legacy có ngôn ngữ hoặc data model không phù hợp với domain mới.
- Upstream do vendor/đơn vị khác sở hữu và khó thay đổi.
- Nhiều hệ thống có semantics khác nhau dù dùng cùng tên field.
- Đang chuyển từ monolith sang microservices theo từng capability.
- Một integration có lỗi, protocol hoặc data quality đặc thù.
- Muốn tránh legacy dependency lan qua nhiều bounded contexts.

Không nhất thiết phải tạo ACL lớn cho mọi integration. Nếu hai bên thực sự chia sẻ cùng một ngôn ngữ và contract ổn định, một adapter mỏng có thể đủ. Mức độ ACL nên tương xứng với mức độ khác biệt và rủi ro.

## 6. Bắt đầu bằng việc tìm khác biệt về ngữ nghĩa

Trước khi viết mapper, lập bảng so sánh các khái niệm:

| Khái niệm | Legacy meaning | New domain meaning | Hành động |
| --- | --- | --- | --- |
| Customer | Một account trong CRM | Buyer thực hiện giao dịch | Lookup/correlation, không dùng ID trực tiếp |
| Order status `0` | Có thể là draft hoặc mới nhập | DRAFT | Xác minh theo tài liệu và dữ liệu thực |
| Order status `1` | Có thể là đã ghi nhận, chưa chắc đã thanh toán | CONFIRMED chỉ sau invariant mới | Không map máy móc |
| Net amount | Giá trị trước thuế/phí | Money total theo cấu trúc line/tax/fee | Tính lại hoặc nhận breakdown có nguồn |
| Date | Local date trong timezone văn phòng | Instant hoặc business date theo use case | Xác định timezone/semantics |
| Empty string | Chưa nhập hoặc unknown | Optional value/unknown | Không tự biến thành empty domain value |
| Deleted flag | Soft delete/hidden | Archived/removed theo lifecycle | Xác định hành vi |

Đối với mỗi field, hỏi:
1. Field này biểu diễn fact gì?
2. Ai tạo và ai có quyền thay đổi?
3. Null, empty, zero và missing khác nhau ra sao?
4. Giá trị có đơn vị, currency, timezone hay locale không?
5. Mã trạng thái có nghĩa giống nhau qua thời gian không?
6. Có dữ liệu lịch sử sai format hoặc exception không?
7. Khi không ánh xạ được, cần reject, quarantine hay giữ unknown?
8. Có thể đối chiếu với nguồn khác để xác minh không?

**Tên giống nhau không chứng minh nghĩa giống nhau.** Ngược lại, tên khác nhau cũng có thể biểu diễn cùng một business fact; phải phân tích contract và quy tắc, không chỉ dựa vào code.

## 7. Thiết kế ranh giới lớp tích hợp

Một cấu trúc minh họa:

```text
application/
  usecase/
    ImportLegacyOrder.java

domain/
  model/
    Order.java
    BuyerId.java
    Money.java
    OrderStatus.java
  service/
    OrderImportPolicy.java

integration/
  legacyorder/
    LegacyOrderClient.java
    LegacyOrderResponse.java
    LegacyOrderTranslator.java
    LegacyOrderAcl.java
    LegacyErrorTranslator.java
    LegacyIdentityResolver.java

infrastructure/
  http/
  persistence/
```

Phân vai:
- **LegacyOrderClient:** giao tiếp HTTP/SOAP/file protocol, authentication, timeout và parsing.
- **LegacyOrderResponse:** DTO phản ánh đúng contract bên ngoài, chỉ sống trong integration boundary.
- **LegacyOrderTranslator:** chuyển legacy payload thành command/value objects của domain.
- **LegacyOrderAcl:** orchestration giữa client, translator, identity resolver và domain use case.
- **LegacyErrorTranslator:** chuyển error code/fault thành loại lỗi nội bộ có ý nghĩa.
- **LegacyIdentityResolver:** ánh xạ ID bên ngoài sang identity nội bộ.
- **Domain model:** chỉ chứa khái niệm và invariants của domain mới; không import legacy DTO.

Một cách tổ chức khác có thể dùng package `acl` hoặc `anti_corruption`. Tên thư mục không quan trọng bằng **dependency direction**: domain mới không phụ thuộc trực tiếp vào DTO, client hay persistence model của legacy.

## 8. Dependency direction: mô hình mới không bị buộc theo legacy

Một boundary tốt:

```text
Legacy system
     ^
     | protocol/DTO
     |
Legacy client + DTO
     |
Translator / ACL
     |
New application command
     |
New domain model
```

Trong code, interface mà application cần nên được đặt theo ngôn ngữ của application. Adapter phía ngoài implement interface đó và chuyển đổi contract.

Ví dụ:

```java
public interface LegacyOrderLookup {
    Optional<ExternalOrderSnapshot> findByReference(
        ExternalOrderReference reference
    );
}
```

Tên `ExternalOrderSnapshot` vẫn là một khái niệm integration, không nhất thiết là entity domain. Use case có thể nhận command nội bộ:

```java
public record ImportOrderCommand(
    String sourceReference,
    BuyerId buyerId
) {}
```

Không truyền `LegacyOrderResponse` vào `Order.importFromLegacy(...)` nếu điều đó khiến domain phải biết schema của provider. Thay vào đó, application/ACL chuyển payload thành một command có ý nghĩa.

## 9. Ví dụ mapping trạng thái: không map enum theo vị trí

Giả sử legacy có:

```java
public enum LegacyStatus {
    CODE_0,
    CODE_1,
    CODE_2,
    CODE_9
}
```

Domain mới có:

```java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    FULFILLING,
    COMPLETED,
    CANCELLED,
    PENDING_REVIEW
}
```

Không dùng cách:

```java
OrderStatus status =
    OrderStatus.values()[legacyStatus.ordinal()];
```

Ordinal phụ thuộc thứ tự enum và không diễn tả business meaning. Cũng không map theo phỏng đoán `0 -> DRAFT` nếu tài liệu legacy nói `0` có thể là “chưa được kế toán xác nhận”.

Dùng bảng ánh xạ rõ:

```java
public OrderStatus translateStatus(
    LegacyOrderStatus legacy,
    LegacyOrderFacts facts
) {
    return switch (legacy.code()) {
        case "0" -> {
            if (facts.isSubmitted()) {
                yield OrderStatus.PENDING_REVIEW;
            }
            yield OrderStatus.DRAFT;
        }
        case "1" -> {
            if (facts.isPaymentConfirmed()
                && facts.hasValidLines()) {
                yield OrderStatus.CONFIRMED;
            }
            yield OrderStatus.PENDING_REVIEW;
        }
        case "2" -> OrderStatus.FULFILLING;
        case "9" -> OrderStatus.CANCELLED;
        default -> throw new UnsupportedLegacyStatus(
            legacy.code()
        );
    };
}
```

Đây là pseudocode minh họa; ý nghĩa status và điều kiện phải được xác nhận với domain expert và contract thực. Nếu không đủ dữ liệu để quyết định, **không đoán**. Có thể đưa record vào quarantine/manual review hoặc biểu diễn trạng thái unknown trong integration workflow, tùy hợp đồng.

Domain status mới nên phản ánh **business fact đã được xác minh**, không chỉ mã mà legacy gửi.

## 10. Mapping dữ liệu có đơn vị và quy tắc rõ ràng

### Money và currency

Legacy có thể trả `NET_AMT=125000` và `CURR_CD=VND`. Domain mới nên dùng Money với amount và currency, không lưu số tiền như double.

```java
public record Money(
    BigDecimal amount,
    Currency currency
) {}
```

Cần biết:
- Số tiền là major unit hay minor unit.
- Decimal scale theo currency.
- Rounding mode.
- Giá đã bao gồm thuế chưa.
- Phí vận chuyển/discount đã được tính chưa.
- Có thể là amount âm cho refund/adjustment không.
- Legacy có dùng dấu phẩy/dấu chấm theo locale không.

Không tự nhân/chia 100 chỉ vì field tên `AMT`. Contract có thể trả decimal string hoặc integer minor units.

### Date và time

Phân biệt:
- Instant: một thời điểm tuyệt đối.
- LocalDate: ngày nghiệp vụ không có thời điểm.
- LocalDateTime: ngày giờ địa phương không kèm timezone.
- ZonedDateTime/OffsetDateTime: có quy tắc timezone/offset.
- Business date: ngày kế toán/ngày giao dịch theo lịch riêng.

Một legacy system ghi `2026-11-12 00:30` theo timezone Bangkok/Vietnam có thể bị hiểu sai nếu parse thành UTC. ACL cần biết timezone nguồn, daylight saving nếu liên quan, và cách xử lý giá trị thiếu offset.

### Null, empty và default

Các giá trị:
- Field bị thiếu khỏi payload.
- Field có `null`.
- Chuỗi rỗng.
- Chuỗi chỉ có spaces.
- Số 0.
- Mã `UNKNOWN`.

Có thể biểu diễn những trạng thái khác nhau. ACL không nên chuẩn hóa tất cả thành `null` nếu domain cần phân biệt “chưa biết”, “không áp dụng” và “đã xác nhận không có”.

### Units và quantity

Nếu legacy trả trọng lượng gram còn domain dùng kilogram, cần chuyển đổi có scale/rounding rõ. Với độ dài, thể tích, timezone, locale và tỷ lệ phần trăm, unit phải nằm trong contract hoặc mapping policy; không để magic conversion trong business logic.

## 11. Correlation ID và identity mapping

ID legacy thường không phải ID domain mới:
- Legacy customer number có thể tái sử dụng sau khi account đóng.
- Order reference có thể chỉ unique trong một business unit.
- Một hệ thống có nhiều company codes và sequence reset theo năm.
- ID có leading zeros có thể bị parser biến thành số.
- Một record có thể merge/split trong quá trình chuyển đổi.

Thiết kế identity mapping:
1. Xác định namespace của ID nguồn: system, tenant, company, region.
2. Giữ raw external identifier khi cần audit.
3. Tạo mapping tới internal ID ổn định.
4. Có unique constraint trên khóa external composite nếu business rule cho phép.
5. Xử lý merge, alias và collision có audit.
6. Không coi ID dạng số là quantity; giữ leading zeros nếu có ý nghĩa.
7. Không đưa external ID thành domain primary key chỉ vì thuận tiện migration.

Ví dụ:

```text
External identity:
  sourceSystem = LEGACY_ERP
  companyCode = VN01
  externalCustomerNo = "00008421"

Internal identity:
  buyerId = "buyer_01J..."
```

Mapping nên được lưu bền vững khi cần correlation qua retry, replay và reconciliation. Nếu chỉ dùng cache, DR có thể làm mất mapping và tạo duplicate entity.

## 12. Xử lý legacy error thành domain-level outcome

Một legacy endpoint có thể trả:

```json
{
  "success": false,
  "errorCode": "E-104",
  "message": "Document locked by user"
}
```

Domain/application không nên phải biết `E-104`. ACL chuyển thành loại lỗi có ngữ nghĩa:

| Legacy outcome | Integration interpretation | Domain/application action |
| --- | --- | --- |
| E-104 | Record đang bị lock | Retry sau khi có điều kiện hoặc báo conflict |
| E-210 | Customer code không tồn tại | Reject hoặc yêu cầu identity resolution |
| E-500 | Lỗi hệ thống upstream | Transient/unknown, áp retry budget |
| HTTP timeout | Không biết upstream đã xử lý chưa | Query/reconcile theo operation ID |
| Payload không hợp lệ | Contract/data quality error | Quarantine và alert |

Không map mọi lỗi thành `LegacyIntegrationException` rồi buộc caller phân tích string message. Nên phân loại:
- Validation/business rejection.
- Authentication/authorization failure.
- Not found/identity mismatch.
- Conflict/concurrency.
- Rate limit/quota.
- Transient availability.
- Unknown outcome.
- Contract/schema incompatibility.

Đặc biệt, **timeout không đồng nghĩa command chưa được thực hiện**. Nếu legacy đã ghi dữ liệu nhưng response bị mất, retry không idempotent có thể tạo record trùng. Cần operation ID, query theo reference hoặc reconciliation.

## 13. ACL và anti-corruption cho API đồng bộ

Một luồng synchronous:

```text
New Order Use Case
      |
      v
Legacy Order ACL
      |
      +--> Translate command to legacy request
      |
      +--> Legacy HTTP/SOAP client
      |
      +--> Translate response/error
      |
      v
New domain result
```

Thiết kế:
- Deadline end-to-end rõ ràng.
- Connect/read timeout hữu hạn.
- Retry chỉ cho lỗi được xác định là transient và operation có semantics an toàn.
- Circuit breaker để tránh dồn tải khi legacy suy giảm.
- Bulkhead để legacy chậm không chiếm hết thread/connection pool của service mới.
- Rate limit theo quota upstream.
- Cache chỉ với dữ liệu có freshness policy phù hợp.
- Correlation ID để truy vết.
- Idempotency hoặc read-after-timeout reconciliation cho command.

Không để domain service tự cấu hình một timeout khác nhau cho mỗi lần gọi legacy. Chính sách integration nên được tập trung trong ACL/client và có telemetry.

## 14. ACL và integration bất đồng bộ

Nếu legacy hỗ trợ file batch, polling hoặc message queue, ACL có thể dịch event/record vào command nội bộ:

```text
Legacy batch / CDC / queue
          |
          v
Legacy Ingestion ACL
          |
          +--> Parse + validate
          +--> Translate legacy semantics
          +--> Resolve identity
          +--> Deduplicate/version check
          |
          v
New domain command / inbox
          |
          v
Domain application
```

Các vấn đề cần giải quyết:
- File có header/version và encoding nào?
- Một file được phát lại thì nhận diện batch bằng gì?
- Có record lỗi riêng hay cả file thất bại?
- Thứ tự giữa các file/record được bảo đảm thế nào?
- Có watermark hoặc sequence không?
- Duplicate event được nhận diện bằng stable event ID hay composite business key?
- Khi ingestion dừng giữa chừng, checkpoint ở đâu?
- Có thể quarantine record lỗi mà không làm sai ordering nghiệp vụ không?

ACL nên giữ raw payload có kiểm soát khi cần điều tra, nhưng phải áp retention, encryption và data minimization. Không ghi dữ liệu nhạy cảm nguyên bản vào log.

## 15. Giữ mô hình nội bộ sạch: tránh Legacy DTO lan vào domain

Ví dụ không nên:

```java
@Entity
public class Order {
    @Column(name = "DOC_NO")
    private String docNo;

    private String legacyStatusCode;

    public void updateFromLegacy(
        LegacyOrderResponse response
    ) {
        this.legacyStatusCode = response.status();
    }
}
```

Vì domain entity biết trực tiếp schema và protocol cũ. Một ví dụ boundary tốt hơn:

```java
public record LegacyOrderResponse(
    String docNo,
    String custNo,
    String netAmount,
    String currencyCode,
    String documentStatus
) {}

public record ImportOrderCommand(
    OrderId orderId,
    BuyerId buyerId,
    Money total,
    OrderStatus status
) {}
```

Translator chuyển từ `LegacyOrderResponse` sang command/domain input. Domain chỉ biết `OrderId`, `BuyerId`, `Money` và `OrderStatus`.

Nếu mapping cần domain rule, đừng nhét mọi logic vào MapStruct expression hoặc utility tĩnh. Có thể tách:
- Structural mapping: rename/convert đơn vị đơn giản.
- Semantic mapping: cần domain policy và facts.
- Identity resolution: tra cứu mapping bền vững.
- Validation: xác minh contract và invariants.
- Error translation: chuyển lỗi provider thành outcome nội bộ.

**Công cụ mapping không thay thế hiểu biết domain.**

## 16. Java/Spring Boot: một skeleton triển khai

Một ví dụ cấu trúc:

```text
com.example.orders
├── domain
│   ├── model
│   ├── policy
│   └── repository
├── application
│   ├── command
│   ├── port
│   └── usecase
└── integration
    └── legacyerp
        ├── client
        ├── dto
        ├── translator
        ├── acl
        └── error
```

Port phía application:

```java
public interface LegacyOrderPort {
    LegacyOrderSnapshot fetch(
        ExternalOrderReference reference
    );
}
```

DTO phía integration:

```java
public record LegacyOrderDto(
    String docNo,
    String customerNo,
    String amount,
    String currency,
    String statusCode
) {}
```

Translator:

```java
@Component
public class LegacyOrderTranslator {

    public LegacyOrderSnapshot translate(
        LegacyOrderDto source,
        BuyerId buyerId
    ) {
        Money total = parseMoney(
            source.amount(),
            source.currency()
        );

        OrderStatus status = mapStatus(source.statusCode());

        return new LegacyOrderSnapshot(
            new ExternalOrderReference(source.docNo()),
            buyerId,
            total,
            status
        );
    }
}
```

ACL adapter:

```java
@Component
@RequiredArgsConstructor
public class LegacyOrderAcl implements LegacyOrderPort {

    private final LegacyOrderHttpClient client;
    private final LegacyOrderTranslator translator;
    private final LegacyIdentityResolver identityResolver;

    @Override
    public LegacyOrderSnapshot fetch(
        ExternalOrderReference reference
    ) {
        LegacyOrderDto dto = client.fetch(reference.value());

        BuyerId buyerId =
            identityResolver.resolve(dto.customerNo());

        return translator.translate(dto, buyerId);
    }
}
```

Đây là skeleton khái niệm. Cần bổ sung validation, exception mapping, timeout, metrics, trace propagation, authorization, resilience và test. Tùy use case, port có thể trả một domain command/input thay vì `LegacyOrderSnapshot`.

### Quy tắc dependency

- Domain không import Spring HTTP client hoặc legacy DTO.
- Application định nghĩa port theo nhu cầu use case.
- Integration implement port và phụ thuộc vào client/translator.
- DTO không được trả xuyên API public của domain.
- Không chia sẻ legacy DTO library cho nhiều bounded contexts.
- Mapping policy cần test độc lập và có dữ liệu mẫu.

## 17. Xử lý trạng thái không thể ánh xạ

Không phải mọi trạng thái legacy đều có trạng thái tương đương trong domain mới. Có thể legacy có `CLOSED_BY_BATCH`, `REVERSED_PENDING` hoặc mã lịch sử chỉ còn tồn tại trong dữ liệu cũ.

Các lựa chọn:
1. **Map sang trạng thái nội bộ tương ứng** nếu có business meaning rõ.
2. **Map thành trạng thái pending/review** nếu cần thêm bằng chứng trước khi quyết định.
3. **Quarantine record** nếu payload không hợp lệ hoặc không thể bảo đảm invariant.
4. **Reject operation** nếu request mới không được phép theo policy.
5. **Preserve source fact** như metadata integration nếu cần audit, nhưng không cho nó điều khiển domain behavior.
6. **Escalate mapping policy** nếu trạng thái mới xuất hiện thường xuyên.

Không tạo một enum nội bộ gồm mọi mã legacy chỉ để tránh lỗi parse. Điều đó khiến domain mới phụ thuộc vào lịch sử của provider.

Một trạng thái `UNKNOWN` cũng phải có nghĩa và hành vi rõ: nó là unknown source value, unknown outcome, hay chưa phân loại? Không dùng một nhãn chung cho mọi trường hợp.

## 18. Đồng bộ dữ liệu hai chiều và quyền sở hữu

ACL không có nghĩa luôn chỉ một chiều. Trong giai đoạn migration, domain mới có thể gửi lệnh sang legacy hoặc đồng bộ dữ liệu theo cả hai hướng. Nhưng **mỗi business fact cần một owner rõ**.

Ví dụ:
- Legacy ERP vẫn là system of record cho mã kế toán.
- New Commerce sở hữu Buyer experience và Order lifecycle mới.
- ACL gửi lệnh cập nhật trạng thái ERP theo contract.
- ERP trả kết quả, ACL diễn giải thành domain outcome.
- Không cho cả hai hệ cùng sửa một fact mà không có conflict policy.

Trước khi thiết kế bidirectional sync, trả lời:
1. Nguồn nào là authoritative cho từng field/fact?
2. Ai được ghi và trong điều kiện nào?
3. Có version/sequence hoặc optimistic concurrency không?
4. Khi hai bên thay đổi cùng lúc, conflict được giải quyết ra sao?
5. Có tombstone/deletion semantics không?
6. Sync trễ bao lâu thì vi phạm nghiệp vụ?
7. Có reconciliation và audit cho correction không?

**Đồng bộ hai chiều không phải là hai webhook cập nhật lẫn nhau.** Nếu không có ownership và version rules, hệ thống có thể tạo feedback loop hoặc ghi đè dữ liệu mới bằng bản cũ.

## 19. Chống vòng lặp và duplicate trong đồng bộ

Một tình huống:
1. New system gửi `BuyerUpdated` sang legacy.
2. Legacy phát event `CustomerChanged`.
3. ACL nhận event và cập nhật New system.
4. New system lại phát `BuyerUpdated` vì state đã thay đổi.

Nếu không có origin/correlation metadata, vòng lặp có thể tiếp diễn.

Biện pháp:
- Gắn event ID, causation ID, source system và operation ID.
- Phân biệt update do người dùng/domain tạo với update do sync mirror.
- Version hoặc sequence theo record.
- Deduplicate event và command.
- Chỉ phát event domain khi business state thực sự đổi, không phát lại vì mirror update.
- Xác định conflict resolution và ownership cho từng field.
- Có loop detection và alert.

Không bỏ qua event chỉ vì source system là legacy; event đó có thể chứa business fact thực sự mới. Cần phân biệt nguồn phát với nguồn sở hữu fact.

## 20. Idempotency và timeout khi gọi command legacy

Giả sử ACL gửi `CreateInvoice`:
- Legacy đã tạo hóa đơn.
- Response bị timeout.
- ACL retry.
- Legacy tạo hóa đơn thứ hai.

Cần một operation identity ổn định:
```text
operationId = invoice-create:order-42:v1
sourceReference = order-42
requestHash = stable hash of canonical command
```

Nếu provider hỗ trợ idempotency key, dùng đúng semantics và thời hạn của họ. Nếu không:
- Tìm theo business reference trước khi retry.
- Duy trì integration journal bền vững.
- Phân biệt known failure và unknown outcome.
- Đối soát sau timeout.
- Đưa trường hợp không thể xác minh vào manual review.
- Không sinh ID mới mỗi lần retry.

Integration journal có thể lưu:
- operation ID.
- request identity/hash.
- upstream reference.
- state: CREATED/SENT/ACKNOWLEDGED/UNKNOWN/RECONCILED.
- attempt count và timestamps.
- correlation/trace IDs.
- response summary đã lọc dữ liệu nhạy cảm.

Không dùng journal thay business ledger. Nó là bằng chứng điều phối tích hợp, cần retention và access policy riêng.

## 21. ACL và transactional outbox/inbox

Nếu domain mới commit database rồi cần gửi command/event sang legacy, không nên dual-write tùy tiện:

```text
New Domain DB transaction
  ├─ update Order state
  └─ write Outbox command
          |
          v
     ACL Relay
          |
          v
     Legacy system
          |
          v
     Response / callback
          |
          v
     ACL translator + Inbox
          |
          v
     New Domain application
```

Outbox bảo đảm business update và ý định gửi command/event nằm trong cùng transaction nội bộ. Relay có thể gửi trùng, nên ACL cần stable operation ID và legacy/provider phải có cách deduplicate hoặc query kết quả.

Inbox giúp ghi nhận event đã nhận và business state trong transaction nội bộ. Nhưng nó không tạo atomic transaction với legacy. Nếu legacy đã thực hiện lệnh mà callback bị mất, vẫn cần reconciliation.

## 22. Lỗi, retry, timeout và circuit breaker ở ACL

ACL là một boundary phù hợp để đặt chính sách resilience vì nó hiểu provider-specific behavior.

| Tình huống | Hành vi nên cân nhắc |
| --- | --- |
| Validation reject từ legacy | Không retry; chuyển thành business outcome |
| 401/403 | Kiểm tra credential/authorization; alert, không retry liên tục |
| 404 | Phân biệt resource không tồn tại và route sai |
| 409/lock conflict | Retry có điều kiện hoặc trả conflict |
| 429 | Tôn trọng quota/Retry-After và rate limit |
| 5xx transient | Retry bounded với exponential backoff/jitter nếu operation an toàn |
| Timeout trước khi gửi | Có thể retry theo client/network evidence |
| Timeout sau khi gửi | Unknown outcome; query/reconcile trước retry |
| Schema mismatch | Quarantine/alert, không retry vô hạn |
| Circuit open | Fail fast hoặc đưa command vào durable queue nếu hợp đồng cho phép |

Không cấu hình retry ở cả Gateway, ACL, HTTP client và legacy SDK mà không có tổng retry budget. Nếu mỗi lớp tự retry ba lần, một operation có thể tạo nhiều lần gọi upstream ngoài dự kiến.

### Timeout theo deadline

```text
User request deadline: 2 seconds
  ├─ auth: 100 ms
  ├─ ACL call: 1,200 ms
  ├─ local work: 300 ms
  └─ response/overhead reserve: 400 ms
```

Các con số minh họa. Deadline phải được truyền xuyên các tầng và phần còn lại được dùng để quyết định có tiếp tục gọi dependency hay không. Không đặt timeout lớn hơn deadline caller rồi giữ thread vô ích.

## 23. Data quality và quarantine

Legacy data có thể chứa:
- Customer ID không còn mapping.
- Currency code không hỗ trợ.
- Date sai format.
- Quantity âm ngoài business rule.
- Duplicate business reference.
- Status không nhận diện.
- Field bị truncate do schema cũ.
- Record thiếu dữ liệu do migration lịch sử.
- Character encoding không đúng.

ACL nên phân loại:
- **Syntactic invalidity:** payload không parse được.
- **Contract invalidity:** thiếu field bắt buộc hoặc sai schema version.
- **Semantic invalidity:** giá trị parse được nhưng vi phạm ý nghĩa/business rule.
- **Reference mismatch:** không resolve được identity/relationship.
- **Temporal inconsistency:** version hoặc timestamp không hợp lệ.
- **Unknown value:** schema hợp lệ nhưng code/status mới chưa biết.

Quarantine:
- Lưu reference và raw payload tối thiểu cần thiết, được bảo vệ.
- Ghi error class, mapping version và correlation ID.
- Có owner và deadline xử lý.
- Cho phép sửa mapping rồi replay có kiểm soát.
- Không tự động bỏ record hoặc biến thành default.
- Có metric theo loại lỗi và tuổi record.

Nếu dữ liệu nhạy cảm, raw payload cần encryption, retention và quyền truy cập tối thiểu. Không đẩy toàn bộ request body vào log để tiện debug.

## 24. Bảo mật ở boundary tích hợp

ACL thường giao tiếp với hệ thống ngoài trust boundary:
- Xác thực service-to-service và credential riêng.
- Least privilege cho operation cần dùng.
- TLS và xác minh certificate.
- Quản lý secret rotation.
- Audience/scope và tenant context rõ.
- Validate input để tránh injection/unsafe deserialization.
- Không tin identity hoặc role chỉ vì legacy gửi field trong payload.
- Không ghi PII/secret vào logs/traces.
- Kiểm soát egress và endpoint allowlist khi policy yêu cầu.
- Audit hành động thay đổi dữ liệu và admin operations.

ACL không nên tự nâng quyền của user. Ví dụ một request từ Buyer A không được dùng shared ERP credential để đọc dữ liệu Buyer B chỉ vì adapter có quyền kỹ thuật rộng. Cần truyền context và thực thi authorization ở đúng resource owner.

### Trust boundary và data minimization

```text
Untrusted legacy response
          |
          v
Parse + schema validation
          |
          v
Authorization / tenant mapping
          |
          v
Semantic translation
          |
          v
Minimal domain command
          |
          v
New domain
```

Một payload hợp lệ về schema vẫn có thể chứa dữ liệu thuộc tenant khác hoặc một trạng thái không được phép. Validation và authorization là hai bước khác nhau.

## 25. Versioning contract và thay đổi legacy

Legacy thường khó thay đổi, nhưng contract vẫn có thể thay do:
- Vendor upgrade.
- Thêm field hoặc enum.
- Đổi encoding/date format.
- SOAP WSDL thay đổi.
- File batch thay header.
- API chuyển từ v1 sang v2.
- Thay cách diễn giải status sau migration nội bộ.

ACL nên:
1. Gắn contract version hoặc detect format rõ.
2. Lưu test fixtures đại diện cho version đang hỗ trợ.
3. Có compatibility policy và deprecation window.
4. Phát hiện unknown fields/enum theo policy.
5. Không âm thầm coi giá trị mới là default.
6. Version mapping rules nếu semantic thay đổi.
7. Có replay/backfill khi mapping policy cần sửa dữ liệu dẫn xuất.
8. Thử old/new payload trong staging trước cutover.

Nếu một status legacy đổi ý nghĩa theo ngày hiệu lực, cần version hoặc context metadata để biết record thuộc semantics nào. Mapping một code duy nhất theo logic hiện tại có thể diễn giải sai lịch sử.

## 26. ACL trong Strangler Fig migration

Strangler Fig thay thế dần chức năng của hệ thống cũ bằng các phần mới, trong khi traffic được định tuyến theo capability hoặc use case.

```text
                Client
                  |
                  v
             Routing layer
               /      \
              /        \
       New service    Legacy app
            |              |
            |              |
         New DB       Legacy DB/API
            |
            v
      New domain model

Legacy integration ACL
      bridges only
      where needed
```

Lộ trình:
1. Chọn capability có ranh giới và owner rõ.
2. Xác định dữ liệu/behavior nào còn do legacy sở hữu.
3. Tạo ACL để mô hình mới không phụ thuộc trực tiếp legacy contract.
4. Route một phần read/write traffic sang new service theo policy.
5. Đối soát kết quả giữa old/new trong giai đoạn shadow/canary.
6. Chuyển ownership của business facts và write path có kiểm soát.
7. Ngừng consumer/endpoint cũ khi không còn traffic.
8. Gỡ ACL khi dependency thực sự biến mất, hoặc giữ một adapter cần thiết cho provider còn lại.

Không nên đưa mọi request qua ACL nếu capability đã được chuyển hoàn toàn và không còn legacy dependency. ACL là công cụ cô lập giai đoạn tích hợp, không phải một tầng bắt buộc vĩnh viễn.

## 27. Read path và write path có thể cần chiến lược khác nhau

### Read path

Có thể:
- Query legacy API.
- Đồng bộ định kỳ thành projection mới.
- Consume CDC/events.
- Dùng cache có freshness contract.
- Backfill historical records.

Cần xác định độ mới, ownership, conflict và behavior khi source unavailable.

### Write path

Rủi ro cao hơn vì có side effect:
- Legacy có phải source of truth không?
- Write có thể được gửi lại an toàn không?
- Có dual-write không?
- Có transaction/compensation?
- Khi timeout unknown, query trạng thái thế nào?
- Ai phát event sau commit?
- Có thể rollback code mà không rollback business operation không?

Một số hệ thống chọn **strangler read first**, sau đó cutover write sau khi projection và mapping được xác minh. Nhưng không phải quy tắc phổ quát; business criticality và khả năng đồng bộ có thể đòi chiến lược khác.

Không dùng read replica/projection cũ làm cơ sở cho write quyết định nếu freshness chưa đáp ứng invariant.

## 28. Shadow traffic và dual-run

Trước khi chuyển traffic, có thể gửi một bản sao request read-only tới hệ mới hoặc so sánh kết quả của hai hệ:

```text
Real request
    |
    v
Legacy response -----------------> User (current path)
    |
    +---- shadow copy ------------> New ACL/domain
                                      |
                                      v
                                 Compare outputs
                                      |
                                      v
                                Metrics/report
```

Lưu ý:
- Shadow request không được tạo side effect thật.
- Redact/minimize sensitive data.
- Giới hạn tỷ lệ traffic và tải lên legacy/new.
- So sánh theo semantic equivalence, không so raw JSON.
- Ghi version và mapping rule.
- Phân loại khác biệt hợp lệ và lỗi thực sự.
- Không để kết quả shadow tự ghi vào canonical database.

Dual-run cho write phức tạp hơn nhiều. Nếu cả hai hệ đều thực hiện thanh toán, xuất hàng hoặc phát hóa đơn, có thể gây duplicate side effect. Chỉ chạy song song với sandbox, simulation hoặc cơ chế fencing/dedup có chứng minh.

## 29. Cutover dữ liệu: snapshot, change stream và reconciliation

Một quy trình migration có thể gồm:
1. Snapshot legacy data tại watermark/sequence xác định.
2. Import và map vào model mới.
3. Consume changes sau watermark.
4. Đối soát count, relationships và business invariants.
5. Shadow reads và so semantic output.
6. Tạm kiểm soát writes trong cutover window nếu cần.
7. Chuyển ownership/routing.
8. Monitor mismatch và rollback gate.
9. Giữ legacy read-only theo thời hạn retention.
10. Decommission khi đủ bằng chứng.

```text
Legacy snapshot at W
       |
       v
ACL import + translation
       |
       v
New domain/projection
       |
       +<--- changes after W (CDC/events)
       |
       v
Reconcile + parity checks
       |
       v
Controlled cutover
```

Nếu không có sequence/CDC đáng tin cậy, timestamp đơn giản có thể tạo gap hoặc duplicate. Cần dùng watermark phù hợp với nguồn, stable keys và reconciliation window.

## 30. ACL và eventual consistency

Nếu ACL đọc dữ liệu từ legacy rồi cập nhật projection mới bất đồng bộ:
- Người dùng có thể thấy dữ liệu stale.
- Một update cũ có thể đến sau update mới.
- Retry có thể phát duplicate.
- Một bản import full snapshot có thể ghi đè delta mới hơn.
- Consumer lag có thể tăng khi legacy gửi burst.

Cơ chế:
- Version/sequence per entity.
- Monotonic update: chỉ áp version mới hơn theo contract.
- Stable event/record ID.
- Idempotent upsert.
- Checkpoint bền vững.
- Bounded retry và DLQ/quarantine.
- Reconciliation định kỳ.
- Freshness SLI và trạng thái “data syncing” nếu cần.

Không dùng `updated_at` làm version nếu timestamp không đủ độ tin cậy hoặc nhiều writer có thể tạo cùng giá trị. Có thể cần sequence, rowversion, ETag hoặc change token từ provider.

## 31. Tổ chức ACL theo ownership và trách nhiệm

ACL nên có owner giống service/integration quan trọng:
- Team sở hữu new bounded context chịu trách nhiệm mapping semantics vào domain.
- Team/platform integration sở hữu client libraries, credential, connectivity hoặc broker infrastructure theo phân quyền.
- Legacy owner chịu trách nhiệm contract và availability phía họ.
- Domain experts xác nhận business mapping.
- Security kiểm tra trust boundary và data handling.
- Operations theo dõi SLO, retry, lag và quarantine.

Một ACL quan trọng cần:
- Contract owner.
- Business mapping owner.
- On-call/escalation.
- Dashboard và runbook.
- Schema/fixture version.
- Dependency inventory.
- Decommission criteria.

Nếu ACL là thư viện dùng chung cho nhiều context, cẩn thận không đưa domain model của một context vào shared library. Thường nên chia sẻ protocol/client utility ở tầng kỹ thuật, còn semantic translation nằm tại từng consumer boundary.

## 32. Observability: đo cả lỗi kỹ thuật và lỗi dịch thuật

Một ACL có thể HTTP 200 nhưng map sai giá trị. Vì vậy cần nhiều nhóm metric:

| Metric | Mục đích |
| --- | --- |
| `acl_requests_total` theo operation/outcome | Traffic và kết quả tích hợp |
| `acl_latency_seconds` p50/p95/p99 | Latency upstream và tổng ACL |
| `acl_translation_failures_total` | Không ánh xạ được schema/semantic |
| `acl_unknown_enum_total` | Giá trị trạng thái mới/chưa hỗ trợ |
| `acl_identity_resolution_failures_total` | Không resolve được ID |
| `acl_upstream_timeout_total` | Timeout, gồm unknown outcome |
| `acl_retry_attempts_total` | Retry amplification |
| `acl_circuit_state` | Trạng thái breaker |
| `acl_quarantine_records` / oldest age | Dữ liệu cần điều tra |
| `acl_sync_lag_seconds` | Freshness khi sync bất đồng bộ |
| `acl_reconciliation_mismatch_total` | Sai lệch giữa nguồn và model mới |
| `acl_contract_version` | Biết version payload/provider |
| `acl_deprecated_path_usage` | Theo dõi việc loại bỏ legacy route |

Không đưa raw customer/order ID vào labels vì cardinality và privacy. Dùng trace/log có quyền truy cập phù hợp, correlation ID và sampling policy.

### Trace xuyên boundary

```text
New API request
  -> use case
  -> ACL
  -> legacy HTTP call
  -> translator
  -> domain command
  -> DB transaction
```

Trace nên thể hiện:
- Provider/system name và operation.
- Contract version/mapping version.
- Latency, retry count và outcome class.
- Correlation/causation ID.
- Error category, không chứa secret/raw PII.
- Domain operation ID đã được bảo vệ.

Nếu legacy không hỗ trợ trace context, ACL có thể ghi external request ID và correlation mapping để nối log hai phía.

## 33. Kiểm thử ACL: contract, mapping và hành vi lỗi

### 33.1 Mapping unit tests

Test:
- Mỗi legacy status được hỗ trợ.
- Unknown status.
- Null/empty/missing field.
- Money scale/currency.
- Timezone và date boundary.
- Leading zeros/ID collision.
- Duplicate lines và ordering.
- Legacy data lịch sử bất thường.
- Semantic rules phụ thuộc nhiều field.

### 33.2 Contract tests

- DTO parsing theo provider version.
- SOAP WSDL/schema hoặc JSON schema.
- Field thêm/bỏ/đổi type.
- Error response và HTTP status.
- Encoding và date formats.
- Backward compatibility với fixture cũ.
- Consumer expectations và provider behavior.

### 33.3 Integration tests

- Authentication/authorization.
- Timeout, 429, 5xx và circuit breaker.
- Connection reset sau khi command có thể đã xử lý.
- Duplicate response/callback.
- Retry và idempotency.
- Checkpoint restart/replay.
- Rate limiting và payload size.

### 33.4 Domain invariants

Sau translation, xác nhận:
- Money/currency hợp lệ.
- Buyer identity có quyền/đúng tenant.
- Order transition được phép.
- Quantity và totals cân bằng.
- Không duplicate aggregate/operation.
- Không chuyển trạng thái terminal trái quy tắc.
- Không biến unknown thành confirmed.

Không chỉ kiểm tra mapper trả đúng object. Cần kiểm tra **domain từ chối hoặc xử lý an toàn dữ liệu đã được dịch**.

## 34. Golden fixtures và mapping version

Giữ bộ payload mẫu đại diện cho legacy:
- Happy path.
- Từng status code.
- Null/optional fields.
- Version cũ và mới.
- Encoding edge cases.
- Error payload.
- Data có dấu hiệu corruption.
- Tenant/company variations.

Mỗi fixture nên có:
- Source contract version.
- Thời điểm hoặc giai đoạn semantics.
- Kỳ vọng mapping.
- Provenance/approval từ domain owner.
- Dữ liệu đã synthetic/redacted, không dùng PII production nguyên bản.

Nếu mapping rule thay đổi, cần biết record lịch sử có được remap lại không. Với projection, có thể rebuild theo mapping version mới. Với business state đã commit hoặc side effect đã thực hiện, không tự động chạy mapping mới để viết lại quá khứ nếu không có migration/reconciliation plan.

## 35. ACL và anti-corruption không phải nơi giấu mọi vấn đề

Một ACL quá lớn có thể trở thành monolith tích hợp:
- Chứa logic của nhiều bounded contexts.
- Mapping mọi hệ thống vào một canonical model chung quá rộng.
- Có hàng trăm conditional theo provider.
- Nắm quyền đọc/ghi mọi database.
- Không có owner rõ.
- Không có SLO hoặc test độc lập.
- Trở thành dependency trung tâm cho mọi service.

Giải pháp:
- Chia ACL theo consumer bounded context hoặc integration responsibility.
- Giữ domain rules ở domain owner.
- Chỉ chia sẻ transport/client primitives khi thật sự chung.
- Tách workload và failure domain khi integration có tải/criticality khác.
- Đặt contract rõ, versioning và ownership.
- Theo dõi mapping complexity, change frequency và deprecation progress.

**ACL cô lập coupling; nó không làm coupling biến mất.** Nếu một service mới phụ thuộc đồng bộ vào legacy cho mọi thao tác, availability và latency của legacy vẫn ảnh hưởng hành trình mới. Cần xem xét cache/projection, async workflow hoặc chuyển ownership khi phù hợp.

## 36. Khi nào nên loại bỏ ACL?

ACL có thể giảm hoặc được gỡ khi:
- Legacy capability đã bị decommission.
- Data ownership chuyển sang domain mới.
- Không còn consumer sử dụng contract cũ.
- Mọi historical records cần thiết đã được migrate/reconcile.
- Không còn batch, scheduled jobs hoặc manual processes phụ thuộc.
- Monitoring cho thấy legacy path usage bằng 0 trong cửa sổ đủ dài.
- Contract, credentials, network route và service catalog được dọn.
- Runbook và DR plan đã chuyển sang nguồn mới.

Không xóa ACL chỉ vì traffic giảm trong một tuần. Có thể còn job hàng tháng, audit queries hoặc fallback hiếm. Cần inventory toàn bộ consumer và usage telemetry.

Một decommission plan:
1. Mark legacy integration deprecated.
2. Chặn tạo consumer mới.
3. Xác định tất cả clients, jobs, reports và data exports.
4. Chuyển consumer còn lại.
5. Theo dõi usage tới qua ít nhất các chu kỳ nghiệp vụ cần thiết.
6. Disable credentials/route theo change window.
7. Lưu dữ liệu và audit theo retention.
8. Xóa code/ACL sau khi không còn dependency.
9. Đóng ADR/exception liên quan với evidence.

## 37. Case study: chuyển Order Management khỏi ERP cũ

### Hiện trạng

ERP cũ sở hữu order headers, line items, status codes và invoice references. New Commerce cần triển khai độc lập cho web/mobile, nhưng ERP vẫn xử lý kế toán và kho hàng.

Các vấn đề:
- ERP trả status dạng code.
- Customer identity dùng company-scoped number.
- Giá tiền là net amount, thuế nằm ở bảng khác.
- Update command có thể timeout sau khi ERP đã commit.
- Batch export chạy mỗi 15 phút.
- Không có idempotency key chính thức.

### Thiết kế ACL

New Order context sở hữu:
- New Order ID và lifecycle.
- Buyer identity nội bộ.
- Money/tax breakdown theo contract mới.
- Domain invariants và API public.

ERP ACL chịu trách nhiệm:
- Gọi ERP API/batch.
- Translate legacy DTO và status.
- Resolve customer/order references.
- Lưu operation journal cho command.
- Quản lý retry, unknown outcome và reconciliation.
- Đưa lỗi mapping vào quarantine.
- Publish domain integration events theo outbox/inbox phù hợp.

### Lộ trình

1. Tạo read adapter và mapping fixtures.
2. Import dữ liệu lịch sử thành projection, chưa đổi write ownership.
3. So sánh semantic output giữa ERP và new model.
4. Chuyển read path theo cohort/traffic.
5. Định nghĩa command contract và operation identity.
6. Chạy sandbox/controlled write integration.
7. Chuyển ownership của order creation theo capability.
8. Giữ ERP adapter cho accounting fields còn thuộc ERP.
9. Gỡ các endpoint cũ khi consumers được chuyển.

### Kết quả cần đo

- Tỷ lệ record không map được.
- Tỷ lệ unknown command outcomes.
- Order state mismatch.
- Import lag và batch completion age.
- Duplicate operation attempts.
- Số user journeys còn phụ thuộc trực tiếp legacy.
- Số integration-specific branches trong domain code.
- Thời gian đưa thay đổi mới ra production.

Không tuyên bố thành công chỉ vì new API đã nhận traffic. Cần xác minh data correctness, business ownership và đường phục hồi khi ERP unavailable.

## 38. Quyết định kiến trúc cho ACL

Một ADR về ACL có thể ghi:
- Bounded context nào được bảo vệ.
- Legacy systems/contracts trong scope.
- Business facts nào do ai sở hữu.
- Mapping principles và unknown-value policy.
- Sync/async boundary và consistency target.
- Idempotency/retry/reconciliation model.
- Security/trust boundary.
- Observability và SLO.
- Migration stages và decommission triggers.
- Consequences, operational costs và risks.

Một exception có thể cần nếu:
- Tạm truy cập shared database trong migration.
- Legacy chưa hỗ trợ chuẩn auth mới.
- Dữ liệu phải giữ format cũ trong một khoảng thời gian.
- Một consumer chưa thể hỗ trợ schema version mới.

ADR chọn **cách thiết kế boundary**; exception ghi **phần lệch chuẩn có giới hạn**. Không dùng một ADR để hợp thức hóa vi phạm policy bắt buộc.

## 39. Anti-patterns thường gặp

**“ACL chỉ là MapStruct mapper.”** Structural mapping không đủ xử lý semantic mismatch, unknown outcomes và business invariants.

**“Dùng DTO legacy làm domain entity cho nhanh.”** Coupling schema và enum cũ lan khắp model mới.

**“Tạo canonical model chung cho tất cả hệ thống.”** Một mô hình tổng quát quá rộng thường xóa khác biệt có ý nghĩa giữa bounded contexts.

**“Map mọi status không biết sang UNKNOWN rồi tiếp tục.”** Có thể làm mất thông tin quan trọng và khiến nghiệp vụ sai; cần quarantine/review theo policy.

**“HTTP 200 nghĩa là command thành công.”** Legacy có thể trả business error trong body hoặc trạng thái chưa hoàn tất.

**“Timeout thì retry ngay.”** Có thể nhân side effect nếu upstream đã commit.

**“Mỗi service tự gọi ERP theo cách riêng.”** Mapping, credentials và error handling phân tán, khó audit và thay thế.

**“ACL xử lý luôn business policy mới.”** Boundary tích hợp không nên trở thành nơi chứa toàn bộ domain logic; policy thuộc domain owner.

**“Hai chiều sync là cập nhật qua lại.”** Không có field ownership, sequence và loop detection sẽ tạo feedback loop và overwrite.

**“Shadow traffic có thể gọi write thật.”** Có thể tạo hóa đơn/thanh toán/đơn hàng trùng.

**“Đã chuyển 90% traffic thì xóa legacy.”** 10% còn lại có thể là batch, reconciliation hoặc khách hàng quan trọng; cần inventory và decommission gate.

**“ACL là tầng tạm nên không cần vận hành tốt.”** Có thể tồn tại nhiều năm và trở thành critical integration; cần SLO, owner, runbook và security.

**“ACL giải quyết mọi dependency.”** Nó cô lập ngữ nghĩa nhưng không xóa network, availability, quota hoặc data dependency của legacy.

## 40. Checklist thiết kế và vận hành ACL

### Domain boundary
- [ ] New domain model không import legacy DTO/entity.
- [ ] Thuật ngữ và business invariants được domain owner xác nhận.
- [ ] Field/status mapping dựa trên semantics, không dựa vào tên hoặc ordinal.
- [ ] Unknown values có policy rõ: reject, pending, quarantine hoặc review.
- [ ] ID, money, date, timezone và units được chuyển đổi rõ.
- [ ] Data ownership và source of truth theo từng fact.

### Integration behavior
- [ ] Client/protocol được cô lập trong integration layer.
- [ ] Timeout/deadline và retry budget rõ.
- [ ] Unknown outcome có idempotency/reconciliation path.
- [ ] Rate limit, breaker và bulkhead phù hợp upstream.
- [ ] Batch/checkpoint/replay có thể phục hồi.
- [ ] Duplicate, out-of-order và loop detection được xử lý.
- [ ] Sync/async consistency và freshness target được công bố.

### Security and operations
- [ ] Credential/workload identity riêng và least privilege.
- [ ] TLS, tenant mapping và authorization đúng trust boundary.
- [ ] Logs/traces không lộ PII/secrets.
- [ ] Owner, dashboard, SLO và runbook rõ.
- [ ] Quarantine có retention, access và remediation owner.
- [ ] Provider/version changes được theo dõi.

### Migration and lifecycle
- [ ] Có contract fixtures và mapping tests.
- [ ] Shadow/dry-run không tạo side effects.
- [ ] Cutover có parity/reconciliation và rollback criteria.
- [ ] Legacy consumers/jobs đã được inventory.
- [ ] Decommission có usage evidence và retention plan.
- [ ] ADR/exception/service catalog được cập nhật.

## 41. Bài tập thực hành

### Bài 1 — Mapping status

Legacy ERP trả status `0`, `1`, `2` và `9`. Domain mới có DRAFT, CONFIRMED, FULFILLING, COMPLETED, CANCELLED. Thiết kế bảng mapping, xác định facts bổ sung cần thiết và cách xử lý mã không biết.

### Bài 2 — Tìm xâm nhập model

Một class domain `Order` có field `legacyDocNo`, `erpStatusCode` và method `updateFromSapDto`. Hãy chỉ ra dependency violation và thiết kế lại interface/translator.

### Bài 3 — Money và timezone

Legacy trả amount dạng string `"1.250,50"` và timestamp `2026-11-12 00:30`. Xác định locale, currency, timezone và rounding assumptions cần làm rõ trước khi map.

### Bài 4 — Timeout không rõ kết quả

ACL gửi CreateInvoice, nhận timeout nhưng ERP đã tạo invoice. Thiết kế operation journal, stable idempotency key, query/reconciliation và state machine không tạo invoice thứ hai.

### Bài 5 — Hai chiều đồng bộ

New Customer service và legacy CRM cùng có thể sửa địa chỉ. Xác định field owner, version, conflict policy, origin metadata và cách tránh update loop.

### Bài 6 — Shadow migration

Hãy thiết kế shadow read từ legacy sang new model cho 5% traffic. Xác định semantic comparison, privacy controls, load budget và điều kiện chuyển read path.

### Bài 7 — Quarantine

Một file batch 10.000 record có 30 record không resolve được customer ID. Đề xuất cách lưu evidence, xử lý record lỗi, checkpoint, ordering và replay mà không bỏ mất 9.970 record hợp lệ.

### Bài 8 — Security boundary

ACL dùng ERP shared credential có quyền đọc tất cả công ty. Một request của tenant A yêu cầu customer B. Xác định trust issue và cách kiểm soát tenant authorization ở cả new domain và integration.

### Bài 9 — Decommission

Legacy API usage giảm về 0 trong 20 ngày nhưng có một job reconciliation chạy theo tháng. Lập decommission checklist và lý do không thể kết luận đã bỏ dependency chỉ từ traffic API.

### Bài 10 — Architecture decision

So sánh ACL riêng theo từng bounded context với một integration service dùng chung toàn doanh nghiệp. Chọn phương án theo domain semantics, ownership, operational complexity và khả năng thay legacy.

## 42. Ghi nhớ

- **ACL bảo vệ ngôn ngữ, mô hình và invariants của bounded context mới** trước contract và semantics của hệ thống ngoài.
- **ACL không chỉ đổi tên field**; nó xử lý trạng thái, identity, money, thời gian, lỗi, protocol và quy tắc nghiệp vụ.
- **Domain mới không nên phụ thuộc trực tiếp vào legacy DTO/entity**; dependency direction nên đi qua port, adapter và translator.
- **Không map status theo ordinal hoặc phỏng đoán**; unknown values cần policy rõ, có thể quarantine hoặc manual review.
- **Mỗi business fact cần source of truth/owner rõ**, nhất là khi đồng bộ hai chiều.
- **Timeout có thể là unknown outcome**, nên retry command phải dựa vào idempotency và reconciliation.
- **Outbox/inbox hỗ trợ durability và dedup trong transaction nội bộ**, nhưng không tạo global transaction với legacy.
- **Shadow traffic và dual-run phải tránh side effects trùng**; so sánh theo semantics, không chỉ raw payload.
- **ACL cần SLO, metrics, owner, runbook và security controls** nếu nó nằm trên critical path.
- **Strangler migration dùng ACL để chuyển từng capability**, rồi gỡ hoặc thu hẹp adapter khi dependency thực sự biến mất.
- **ADR ghi quyết định boundary và mapping; exception quản lý lệch chuẩn; contract tests bảo vệ khả năng tương thích.**

Một lớp chống xâm nhập tốt giúp hệ thống mới giữ được ngôn ngữ và quy tắc riêng, trong khi vẫn khai thác được dữ liệu và khả năng của legacy trong giai đoạn chuyển đổi. Nó tạo ra một ranh giới có thể kiểm chứng và thay thế, để **chi phí của quá khứ không lan thành cấu trúc bắt buộc của tương lai**.

### Tài liệu tham khảo

- Eric Evans — *Domain-Driven Design: Tackling Complexity in the Heart of Software*, phần Context Map và Anti-Corruption Layer.
- Vaughn Vernon — *Implementing Domain-Driven Design*, phần Context Mapping.
- Martin Fowler — Anti-Corruption Layer: https://martinfowler.com/bliki/AntiCorruptionLayer.html
- Martin Fowler — Strangler Fig Application: https://martinfowler.com/bliki/StranglerFigApplication.html
- Microsoft Azure Architecture Center — Anti-Corruption Layer pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer
- Microsoft Azure Architecture Center — Strangler Fig pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig
- Martin Fowler — Bounded Context: https://martinfowler.com/bliki/BoundedContext.html
- Chris Richardson — Microservices Patterns: https://microservices.io/patterns/refactoring/anti-corruption-layer.html
- OpenTelemetry — Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/
- OWASP — API Security Top 10: https://owasp.org/www-project-api-security/

Các tên hệ thống, mã trạng thái, API, class Java, con số và quy trình trong bài là ví dụ minh họa. Khi áp dụng cần xác nhận semantics với domain owner và contract owner, kiểm tra data classification, quyền truy cập, yêu cầu compliance và hành vi thực tế của hệ thống legacy.
