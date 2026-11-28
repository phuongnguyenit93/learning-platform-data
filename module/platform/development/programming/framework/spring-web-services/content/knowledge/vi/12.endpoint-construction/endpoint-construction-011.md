# Ranh giới giao dịch nghiệp vụ và thời điểm tạo phản hồi

Trong **Spring Web Services (Spring-WS)**, endpoint là ranh giới giữa **thông điệp SOAP** và **nghiệp vụ ứng dụng**. Với thao tác có tác dụng phụ như tạo đơn hàng, câu hỏi quan trọng không chỉ là “method trả về đúng JAXB object không?”, mà còn là: **khi nào dữ liệu thực sự được commit, khi nào được phép xác nhận thành công, và điều gì xảy ra nếu client không nhận được phản hồi dù server đã xử lý xong?**

Bài học thuộc chương **Xây dựng endpoint** của module `SPRING_WEB_SERVICES`, dựa trên **contract-first**: XSD/WSDL quy định request/response; JAXB ánh xạ XML; `@Endpoint` điều phối lời gọi; application service quản lý giao dịch; Spring-WS xử lý SOAP Fault, interceptor và transport. XML security, WS-Security, chứng chỉ và kiểm thử tương thích phải gắn vào kiến trúc mà không đánh đồng **giao dịch nghiệp vụ** với **giao thức SOAP**.

**Nguyên tắc cốt lõi:** response chỉ nên biểu đạt kết quả đã đạt đến **mốc cam kết** mà hợp đồng định nghĩa. Một `SubmitOrderResponse` được khởi tạo trong JVM không chứng minh database đã commit; transaction commit thành công cũng không chứng minh client đã nhận được SOAP response.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt transaction DB, use case nghiệp vụ, tạo JAXB response và gửi SOAP response qua mạng.
2. Đặt ranh giới `@Transactional` hợp lý giữa `@Endpoint`, application service và repository.
3. Giải thích vì sao commit của Spring transaction proxy xảy ra **trước khi endpoint nhận kết quả service**, trong kiến trúc trình bày ở đây.
4. Thiết kế ý nghĩa `ACCEPTED`, `PENDING` và `COMPLETED` theo mốc bền vững thực tế.
5. Thiết kế idempotency, khóa duy nhất và transactional outbox để xử lý retry.
6. Phân biệt SOAP Fault từ validation, authorization, rollback với lỗi xảy ra sau commit.
7. Kiểm thử failure window, concurrent retry và tương thích SOAP trên đường truyền.

## 1. Bài toán: client tạo đơn hàng qua SOAP

Hệ thống mua hàng gọi thao tác `SubmitOrder`. Hai bên thống nhất:

- Client gửi `requestId`, `buyerId` và danh sách `item`.
- Server lưu đơn, cấp `orderId` và ghi nhận thời điểm tiếp nhận.
- Sau khi đơn đã được lưu **bền vững**, server trả `status=ACCEPTED`.
- Việc giao hàng/thanh toán là quy trình khác; `ACCEPTED` **không** có nghĩa đã giao hoặc thanh toán xong.
- Nếu client không nhận được response, client có thể retry cùng `requestId` theo quy tắc chống trùng.

Request SOAP 1.1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:SubmitOrderRequest>
      <ord:requestId>REQ-2026-0081</ord:requestId>
      <ord:buyerId>BUYER-15</ord:buyerId>
      <ord:items>
        <ord:item>
          <ord:sku>SKU-01</ord:sku>
          <ord:quantity>2</ord:quantity>
        </ord:item>
      </ord:items>
    </ord:SubmitOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Response thành công với semantics “đã tiếp nhận bền vững”:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:SubmitOrderResponse>
      <ord:requestId>REQ-2026-0081</ord:requestId>
      <ord:orderId>ORD-9021</ord:orderId>
      <ord:status>ACCEPTED</ord:status>
      <ord:acceptedAt>2026-11-27T02:45:00Z</ord:acceptedAt>
    </ord:SubmitOrderResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Ở bài này, `ACCEPTED` nghĩa là bản ghi order và ý định phát sự kiện outbox (nếu có) đã commit trong một DB transaction thành công. Một dịch vụ khác có thể định nghĩa `ACCEPTED` là “đã đưa vào durable queue”; khi đó phải công bố mốc cam kết tương ứng. Không sử dụng cùng một từ nhưng client và server lại hiểu khác nhau.

## 2. Contract-first: XSD không tự định nghĩa transaction

XSD mẫu `orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="RequestIdType">
    <xs:restriction base="xs:string">
      <xs:minLength value="8"/>
      <xs:maxLength value="64"/>
      <xs:pattern value="[A-Za-z0-9._-]+"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="QuantityType">
    <xs:restriction base="xs:positiveInteger">
      <xs:maxInclusive value="999"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="OrderItemType">
    <xs:sequence>
      <xs:element name="sku" type="xs:string"/>
      <xs:element name="quantity" type="ord:QuantityType"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="ItemsType">
    <xs:sequence>
      <xs:element name="item" type="ord:OrderItemType"
                  minOccurs="1" maxOccurs="100"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="SubmitOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="ord:RequestIdType"/>
        <xs:element name="buyerId" type="xs:string"/>
        <xs:element name="items" type="ord:ItemsType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="SubmitOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="ord:RequestIdType"/>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="status" type="xs:string"/>
        <xs:element name="acceptedAt" type="xs:dateTime"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

WSDL document/literal có thể công bố operation `SubmitOrder` dựa trên hai global elements `SubmitOrderRequest` và `SubmitOrderResponse`. Với `DefaultWsdl11Definition`, tên kết thúc bằng `Request`/`Response` là quy ước nhận diện; với WSDL tĩnh, `wsdl:part/@element` phải trỏ đến QName đúng.

**XSD quy định hình dạng XML, không quy định lúc nào DB commit.** Chẳng hạn:

- `xs:dateTime` cho biết định dạng thời gian, không chứng minh đó là timestamp vật lý lúc commit. Trong ví dụ `acceptedAt` được xác định trong transaction và lưu bền vững khi commit.
- `requestId` có đúng pattern không đồng nghĩa request đã được chống trùng; idempotency cần DB constraint và xử lý concurrency.
- `buyerId` do client khai báo không phải bằng chứng đã được xác thực danh tính.
- `status=ACCEPTED` là **ngữ nghĩa nghiệp vụ** được mô tả ngoài schema; nên dùng enum và mô tả trạng thái rõ trong hợp đồng thực tế.

| Quyết định hợp đồng | Ví dụ | Nơi bảo đảm |
| --- | --- | --- |
| Thành công nghĩa là gì? | Order + outbox record đã commit | Transactional application service |
| Khi nào trả `ACCEPTED`? | Sau khi transactional service trả thành công | Endpoint + response mapper |
| Client retry bằng gì? | Cùng `requestId` | Idempotency policy |
| Phạm vi khóa chống trùng? | Buyer đã xác thực + requestId | DB unique constraint và business logic |
| Event downstream được gửi khi nào? | Sau commit qua outbox publisher | Background process |
| Lỗi trước commit có gì? | SOAP Fault theo loại lỗi | Exception resolver |
| Lỗi sau commit? | DB không tự rollback, client retry/query | Recovery contract |

## 3. Bốn ranh giới thường bị nhầm lẫn

| Ranh giới | Bắt đầu/kết thúc | Bảo đảm điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- | --- |
| **SOAP message** | Client gửi Envelope, server tạo Envelope phản hồi | Cấu trúc protocol, payload | Database đã commit |
| **Application use case** | Xử lý `SubmitOrder` | Quy tắc nghiệp vụ và phối hợp thành phần | Client nhận được HTTP response |
| **Database transaction** | `begin/commit/rollback` trên tài nguyên tham gia | Atomicity và durability theo DB | Hệ thống khác xử lý hoặc response đã gửi thành công |
| **Network delivery** | Gửi bytes, nhận bytes, client parse response | Nếu nhận trọn vẹn, client biết một kết quả | Server biết chắc mọi hành động của client sau khi nhận |

Một JDBC/JPA transaction **không tự bao trùm** HTTP SOAP transport hoặc hệ thống của đối tác. DB commit không chờ client xác nhận ở tầng nghiệp vụ; nếu mạng đứt sau commit, không có thao tác “rollback HTTP” làm DB quay về.

### 3.1. Mốc thời gian khi thành công

~~~mermaid
sequenceDiagram
    autonumber
    participant C as SOAP client
    participant D as MessageDispatcher
    participant E as @Endpoint
    participant S as @Transactional service proxy
    participant DB as Database
    participant O as Outbox publisher

    C->>D: SubmitOrderRequest
    D->>D: Parse, route, validate, security
    D->>E: JAXB request
    E->>E: XML DTO → application command
    E->>S: submit(command)
    S->>DB: BEGIN, INSERT order + outbox
    DB-->>S: Operations finished
    S->>DB: COMMIT
    DB-->>S: Commit OK
    S-->>E: SubmissionReceipt
    E->>E: Receipt → JAXB response
    E-->>D: SubmitOrderResponse
    D-->>C: HTTP SOAP response
    O->>DB: Poll outbox after commit
    O->>O: Publish independently
~~~

Trong mô hình **Spring declarative transactions qua proxy**, một transaction mới được bắt đầu khi gọi service qua proxy; commit xảy ra lúc phương thức transactional hoàn thành bình thường **trước khi proxy trả quyền điều khiển cho endpoint**. Vì vậy endpoint chỉ tạo `SubmitOrderResponse` **sau** `useCase.submit(command)` sẽ không tạo success response nếu việc commit giao dịch đó ném exception.

Điều kiện: các ghi chính đều tham gia transaction ấy, không có công việc bất đồng bộ chưa hoàn tất mà contract lại tuyên bố đã hoàn tất. Nếu service chỉ gửi một event không bền vững rồi return, `ACCEPTED` mang ý nghĩa khác.

## 4. Đặt `@Transactional` ở đâu?

### 4.1. Application service làm transaction boundary

~~~text
SOAP/XML → MessageDispatcher → @Endpoint
                                │
                        JAXB DTO → Command
                                │
                                ▼
                       SubmitOrderUseCase
                         @Transactional
                       ┌────────────────────┐
                       │ Business invariants│
                       │ Save order         │
                       │ Save idempotency   │
                       │ Save outbox        │
                       │ COMMIT / ROLLBACK  │
                       └────────────────────┘
                                │
                                ▼
                       Receipt → JAXB response
                                │
                                ▼
                         SOAP XML / HTTP
~~~

Lý do:

1. Transaction bắt đầu **sau bước parse/route và các kiểm tra cần có**, không giữ connection DB trong lúc nhận SOAP request qua mạng.
2. Transaction bao trùm một **use case có nghĩa**: lưu order và outbox cùng thành công hoặc cùng rollback.
3. Business service có thể được gọi từ SOAP, batch job hoặc message consumer mà không phụ thuộc transport.
4. Endpoint tách mapping XML khỏi persistence, giúp dễ test và versioning.
5. SOAP serialization và network response nằm **ngoài** transaction database, tránh giữ lock quá lâu.

### 4.2. Vì sao không vội gắn `@Transactional` lên `@Endpoint`?

Một số dự án có thể làm được điều đó, nhưng thường không tối ưu vì endpoint sẽ có động cơ giữ transaction quanh XML mapping, dễ nhồi business logic vào SOAP handler và gây hiểu lầm rằng transaction kéo dài đến lúc client nhận response.

Annotation `@Transactional` chỉ có hiệu lực khi lời gọi đúng cơ chế AOP/transaction interceptor, không phải nhờ `@Endpoint`. Với Spring proxy, cần có Spring bean, method và đường gọi phù hợp. Nếu thực sự đặt transaction ở endpoint, hãy kiểm thử mốc commit/rollback và cách tương tác với endpoint adapter.

### 4.3. Không giữ transaction trong lúc chờ mạng

Tránh transaction DB kéo dài khi gọi SOAP/HTTP service khác, gửi email, chờ payment, chờ broker ACK không tham gia DB transaction, serialize XML lớn hoặc stream response chậm. Transaction dài tăng lock contention, deadlock và tiêu thụ tài nguyên.

Một DB transaction không tự biến remote SOAP call thành một bước atomic. Hãy cân nhắc transactional outbox hoặc một workflow/saga có trạng thái bền vững.

## 5. Ví dụ triển khai: mapper, application service, endpoint

Giả sử XJC sinh `SubmitOrderRequest`/`SubmitOrderResponse` từ các global elements với anonymous complex types, có getters/setters phù hợp. Nếu XSD/binding sinh `JAXBElement` thay vì object root trực tiếp, điều chỉnh theo `ObjectFactory` đã sinh.

### 5.1. Application model không phụ thuộc SOAP

~~~java
public record SubmitOrderLine(String sku, int quantity) {}

public record SubmitOrderCommand(
        String requestId,
        String buyerId,
        List<SubmitOrderLine> lines) {
    public SubmitOrderCommand {
        lines = List.copyOf(lines);
    }
}

public record SubmissionReceipt(
        String requestId,
        String orderId,
        Instant acceptedAt) {}
~~~

Đây là những khai báo khái niệm: trong Java, hãy đặt mỗi public top-level record vào tệp phù hợp và import `java.util.List` / `java.time.Instant`. Trong ứng dụng thật, `buyerId` phải được đối chiếu với principal đã xác thực; hoặc lấy buyer identity từ security context đáng tin.

### 5.2. Mapper giữa JAXB và ứng dụng

~~~java
@Component
public class SubmitOrderSoapMapper {

    public SubmitOrderCommand toCommand(SubmitOrderRequest request) {
        List<SubmitOrderLine> lines =
            request.getItems().getItem().stream()
                .map(item -> new SubmitOrderLine(
                    item.getSku(),
                    item.getQuantity().intValueExact()))
                .toList();

        return new SubmitOrderCommand(
            request.getRequestId(),
            request.getBuyerId(),
            lines);
    }

    public SubmitOrderResponse toResponse(SubmissionReceipt receipt) {
        SubmitOrderResponse response = new SubmitOrderResponse();
        response.setRequestId(receipt.requestId());
        response.setOrderId(receipt.orderId());
        response.setStatus("ACCEPTED");
        response.setAcceptedAt(toXmlUtcDateTime(receipt.acceptedAt()));
        return response;
    }

    // Helper toXmlUtcDateTime(Instant) chuyển sang
    // XMLGregorianCalendar UTC, phù hợp xs:dateTime.
}
~~~

Code minh họa cần imports và helper tương ứng. `xs:positiveInteger` thường được JAXB sinh thành `BigInteger`, do đó `intValueExact()` tránh làm mất dữ liệu khi chuyển sang int. XSD validation 1..999 vẫn phải chạy; không mặc định một getter JAXB luôn trả non-null khi ai đó gọi method trực tiếp trong test.

### 5.3. Application service sở hữu transaction

~~~java
@Service
public class SubmitOrderUseCase {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final Clock clock;

    public SubmitOrderUseCase(
            OrderRepository orders,
            OutboxRepository outbox,
            Clock clock) {
        this.orders = orders;
        this.outbox = outbox;
        this.clock = clock;
    }

    @Transactional
    public SubmissionReceipt submit(SubmitOrderCommand command) {
        // Xác minh quyền và quy tắc nghiệp vụ.
        // Idempotency phải xử lý atomic với unique constraint;
        // khung này giả định request đã được phân loại là mới.
        Instant acceptedAt = clock.instant();
        OrderEntity order = OrderEntity.acceptedFrom(
            command, acceptedAt);

        orders.save(order);
        outbox.save(OutboxEvent.orderAccepted(order));

        return new SubmissionReceipt(
            command.requestId(),
            order.getId(),
            acceptedAt);
    }
}
~~~

`OrderRepository`, `OutboxRepository`, `OrderEntity` và `OutboxEvent` là các abstraction phải được ứng dụng hiện thực; đoạn trên **không phải chương trình độc lập chạy ngay**. Giả định hai repository dùng **cùng database và transaction manager**. Nếu chúng ghi hai database khác nhau, `@Transactional` đơn lẻ không làm hai nguồn dữ liệu trở nên atomic.

Ví dụ còn giả định `order.getId()` đã sẵn sàng khi tạo receipt, chẳng hạn vì ID do ứng dụng cấp hoặc ID từ database đã được lấy qua cơ chế persist/flush thích hợp. Nếu ID chỉ được tạo ở một bước muộn hơn, phải điều chỉnh cách cấp/lấy ID trước khi tạo receipt. **Flush không đồng nghĩa commit**: commit vẫn là ranh giới xác nhận thành công cho giao dịch này.

`acceptedAt` được lấy **trước commit** và lưu cùng transaction; nó là mốc nghiệp vụ ghi nhận, **không phải timestamp commit vật lý**. Nếu cần timestamp commit chính xác, contract và cách tạo timestamp ở DB phải được thiết kế riêng.

### 5.4. Endpoint gọi service, rồi mới dựng response

~~~java
@Endpoint
public class SubmitOrderEndpoint {

    private static final String NS = "urn:example:orders:v1";

    private final SubmitOrderUseCase useCase;
    private final SubmitOrderSoapMapper mapper;

    public SubmitOrderEndpoint(
            SubmitOrderUseCase useCase,
            SubmitOrderSoapMapper mapper) {
        this.useCase = useCase;
        this.mapper = mapper;
    }

    @PayloadRoot(namespace = NS, localPart = "SubmitOrderRequest")
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {

        SubmitOrderCommand command = mapper.toCommand(request);

        // Proxy transaction commit trước khi trả kết quả cho caller.
        SubmissionReceipt receipt = useCase.submit(command);

        // Không thêm DB writes ở đây.
        return mapper.toResponse(receipt);
    }
}
~~~

Trình tự thông thường:

1. Spring-WS định tuyến theo payload QName `{urn:example:orders:v1}SubmitOrderRequest`.
2. JAXB/argument resolver đọc XML thành request object.
3. Mapper tạo application command.
4. Service proxy mở transaction, ghi dữ liệu và commit.
5. Chỉ khi proxy trả kết quả thành công, endpoint nhận `SubmissionReceipt`.
6. Mapper tạo `SubmitOrderResponse`; Spring-WS marshal, đóng SOAP Envelope và gửi HTTP response.

Nếu commit thất bại và exception nổi lên, `mapper.toResponse(...)` không chạy trong luồng thành công. Nhưng lỗi serialization hoặc network **vẫn có thể xảy ra sau khi DB đã commit**.

### 5.5. Không trả JPA entity trực tiếp

~~~java
// Anti-pattern: không trả persistence entity làm SOAP contract.
@ResponsePayload
public OrderEntity submit(@RequestPayload SubmitOrderRequest request) {
    return repository.save(...);
}
~~~

Entity dễ chứa field nội bộ, quan hệ lazy, dữ liệu nhạy cảm hoặc cấu trúc không khớp XSD. Serialization có thể chạy khi persistence context đã đóng. Dùng immutable receipt/application result rồi chuyển sang JAXB response ổn định.

## 6. Khi nào commit, khi nào rollback?

### 6.1. Spring `@Transactional` qua proxy

Trong mô hình phổ biến:

- Method Spring-managed `public` được gọi **qua proxy** có thể được transaction interceptor bao bọc.
- Propagation mặc định `REQUIRED`: tham gia transaction đang có hoặc mở transaction mới nếu chưa có.
- Khi method chạy thành công, interceptor commit **transaction mà nó sở hữu** trước khi trả về caller.
- Mặc định Spring đánh dấu rollback với `RuntimeException` / `Error`; checked exception cần xem policy hoặc cấu hình `rollbackFor` nếu muốn rollback.
- Method body đã `return` nhưng phần interceptor vẫn có thể **flush/commit và ném exception** trước khi endpoint nhận được giá trị.

**Điều kiện quan trọng:** nếu bên ngoài đã có transaction và service chỉ tham gia nó, commit thật có thể xảy ra ở phạm vi ngoài service. Kiến trúc bài này yêu cầu **endpoint không mở transaction ngoài** và service sở hữu transaction cho command; không được khái quát “mọi lời gọi @Transactional đều commit trước khi trở về” cho bất kỳ propagation nào.

### 6.2. Các bẫy transaction

| Tình huống | Hệ quả có thể xảy ra | Phòng tránh |
| --- | --- | --- |
| `new SubmitOrderUseCase(...)` thủ công | Không gọi qua Spring proxy | Inject Spring bean |
| Tự gọi method `@Transactional` trong cùng bean | Self-invocation có thể bypass proxy | Tách bean hoặc dùng `TransactionTemplate` |
| Catch và nuốt exception trong service | Proxy thấy return bình thường, có thể commit | Xử lý có chủ đích/đánh dấu rollback |
| Ném checked exception | Có thể không rollback theo mặc định | `rollbackFor` phù hợp |
| `REQUIRES_NEW` cho ghi độc lập | Inner transaction có thể commit dù outer rollback | Chỉ dùng nếu thật sự muốn semantics đó |
| Chạy tác vụ async trong transaction | Transaction context không tự sang thread khác | Outbox/durable workflow |
| Ghi vào hai DB khác nhau | Local transaction không atomic xuyên DB | Kiến trúc phân tán thích hợp |
| DB phát hiện lỗi lúc commit | Lỗi nổi lên sau khi method body đã return | Tạo success response sau proxy returns |
| Serialize response lỗi sau commit | DB đã thay đổi, client có thể không biết | Idempotency và recovery |

`@Transactional(readOnly = true)` hữu ích ở một số query service nhưng thường là hint/optimization; nó **không phải authorization** và không phải bảo đảm tuyệt đối không thể ghi.

### 6.3. Sơ đồ các điểm lỗi

~~~mermaid
flowchart TD
    A["SOAP request đã parse/route"] --> B["Endpoint tạo command"]
    B --> C["Service BEGIN transaction"]
    C --> D{"Lỗi trước commit?"}
    D -- "Có" --> E["Rollback; fault theo policy"]
    D -- "Không" --> F["Ghi order + outbox"]
    F --> G{"COMMIT thành công?"}
    G -- "Không" --> H["Không trả success receipt bình thường"]
    G -- "Có" --> I["Endpoint nhận SubmissionReceipt"]
    I --> J["Tạo JAXB / SOAP response"]
    J --> K{"Client nhận response?"}
    K -- "Có" --> L["Client biết kết quả"]
    K -- "Không" --> M["DB đã commit, kết quả chưa rõ với client"]
    M --> N["Retry an toàn / Query status"]
~~~

## 7. Bốn thời điểm “tạo phản hồi” khác nhau

1. **Tạo dữ liệu kết quả**: service tạo `SubmissionReceipt` bên trong transaction.
2. **Commit DB**: các ghi trở nên bền vững theo bảo đảm của database.
3. **Tạo JAXB/XML response**: endpoint mapper và adapter chuyển receipt thành SOAP payload.
4. **Client nhận và xử lý**: transport/client đọc toàn bộ response, unmarshalling thành công.

`SubmissionReceipt` có thể được tạo **trước commit**; nhưng nhờ transaction proxy, endpoint chỉ nhận receipt **sau khi commit thành công** (theo cấu hình đã nêu). JAXB response thường được dựng ở bước tiếp theo. Không gọi “đã trả response” khi mới khởi tạo object Java trong method.

### 7.1. Crash sau commit nhưng trước response

~~~text
T0  SOAP request đến server
T1  DB transaction BEGIN
T2  INSERT order, INSERT outbox
T3  COMMIT OK              ← dữ liệu bền vững
T4  Process crash          ← client chưa nhận response
T5  Client timeout
T6  Client retry cùng requestId
~~~

Nếu không chống trùng, server có thể tạo **hai đơn**. Với idempotency được thiết kế đúng, retry sẽ đọc cùng kết quả đã lưu, trả **cùng orderId** và timestamp receipt theo giao ước.

### 7.2. Mapper/HTTP lỗi sau commit

Nếu `mapper.toResponse(receipt)` tạo `xs:dateTime` không hợp lệ, hoặc HTTP connection đứt:

- DB có thể đã commit.
- Server **không thể tự rollback transaction đã hoàn tất**.
- Nếu response chưa bị ghi, hạ tầng có thể tạo fault; nếu đã gửi một phần, có thể không thể gửi một SOAP Fault hoàn chỉnh.
- Client có thể chỉ thấy timeout, lỗi transport hoặc XML thiếu.

Đừng thực hiện thao tác xóa order ngay chỉ để “bù” lỗi marshal: side effect downstream có thể đã chạy. Hãy xây recovery qua requestId, idempotency và trạng thái.

## 8. Idempotency: retry không tạo thêm tác dụng phụ

`requestId` là định danh cho **một ý định nghiệp vụ**, không chỉ correlation ID để log.

### 8.1. Hợp đồng retry

| Tình huống | Hành vi đề xuất |
| --- | --- |
| RequestId mới, nội dung hợp lệ | Tạo order mới, lưu receipt |
| Cùng buyer tin cậy + requestId, cùng nội dung | Trả receipt ban đầu, không tạo order/outbox mới |
| Cùng khóa nhưng payload nghiệp vụ khác | SOAP Fault `REQUEST_ID_CONFLICT` |
| Hai request đồng thời cùng khóa | Chỉ một hiệu ứng tạo order được commit |
| Client dùng requestId khác | Theo hợp đồng có thể là ý định mới |
| Key hết thời hạn lưu | Hành vi phải được quy định rõ: từ chối, tra cứu hoặc chính sách tái sử dụng |

Nếu `buyerId` do client gửi tùy ý, không được dùng nó để vượt qua authorization. Khóa nên nằm trong phạm vi **principal/buyer đã xác thực**.

### 8.2. Kiểm tra trước khi insert chưa đủ

~~~java
// Race condition: cả hai transaction cùng thấy "chưa có".
if (repository.findByBuyerIdAndRequestId(buyerId, requestId).isEmpty()) {
    repository.save(newOrder);
}
~~~

Hai transaction đồng thời có thể cùng vượt qua kiểm tra. Cần **unique constraint/index** trong DB, ví dụ `UNIQUE(buyer_id, request_id)`, cùng một chiến lược xử lý xung đột.

Thuật toán mang tính thiết kế:

~~~text
1. Xác định buyer đã xác thực và canonical business fingerprint.
2. Thử ghi idempotency record với khóa duy nhất trong transaction.
3. Cùng transaction: ghi order, receipt, outbox rồi commit.
4. Nếu bị unique conflict từ concurrent request:
   - kết thúc/rollback transaction thất bại;
   - đọc receipt đã commit bằng transaction/read context mới;
   - cùng fingerprint -> trả receipt cũ;
   - fingerprint khác -> Fault REQUEST_ID_CONFLICT.
5. Khi transaction đối thủ chưa hiển thị, xử lý trạng thái đang
   xử lý/retry có giới hạn theo policy.
~~~

**Không** bắt unique constraint exception rồi tiếp tục đọc/commit trong một transaction JPA đã bị đánh dấu rollback-only. Đường xử lý xung đột cần transaction boundary riêng.

### 8.3. Fingerprint phản ánh ý định, không so byte SOAP

XML có thể đổi prefix, whitespace hoặc Header mà giữ nguyên dữ liệu nghiệp vụ. So sánh byte-for-byte SOAP Envelope dễ coi một retry hợp lệ là request khác.

Fingerprint nên được định nghĩa từ các trường **mang ý nghĩa tạo đơn**, ví dụ buyer đã xác thực, danh sách `(sku, quantity)` và lựa chọn nghiệp vụ liên quan. Quy tắc thứ tự, normalizing, hashing và version cần nhất quán. **Business fingerprint không phải XML Signature canonicalization**.

### 8.4. Receipt ban đầu khác trạng thái đơn hiện tại

Một retry `SubmitOrder` sau một giờ vẫn có thể trả `ACCEPTED` và `acceptedAt` ban đầu, trong khi `GetOrderStatus` trả `SHIPPED`. Đó không phải mâu thuẫn: một thao tác hỏi **kết quả tiếp nhận ban đầu**, thao tác kia hỏi **trạng thái hiện tại**. Hợp đồng phải mô tả rõ điều này.


## 9. Transactional outbox và giới hạn giao dịch DB

Giả sử sau khi tiếp nhận đơn phải thông báo cho hệ thống kho qua SOAP hoặc broker. Cách làm rủi ro:

~~~java
@Transactional
public SubmissionReceipt submit(SubmitOrderCommand command) {
    OrderEntity order = repository.save(...);
    warehouseSoapClient.notifyOrder(order); // Remote call
    return receiptOf(order);
}
~~~

Có ít nhất bốn vấn đề:

1. Partner có thể xử lý thông báo rồi **response thất lạc**: local server không biết cần retry hay không.
2. Partner thành công nhưng database local **rollback**: hai hệ thống không nhất quán.
3. Database commit nhưng notification thất bại: hệ thống thiếu dấu vết bền vững để phát lại.
4. Chờ remote SOAP call giữ transaction/lock lâu hơn cần thiết.

### 9.1. Mẫu transactional outbox

Trong **cùng một transaction DB** với order:

~~~sql
BEGIN;
INSERT INTO orders (...);
INSERT INTO idempotency_receipts (...);
INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, status
) VALUES (..., 'ORDER_ACCEPTED', ..., 'NEW');
COMMIT;
~~~

Đây là **pseudocode SQL** để minh họa các bản ghi phải cùng commit; placeholder `...` cần được thay bằng schema/table thực tế. Publisher độc lập sẽ đọc các outbox events đã commit và gửi đến hệ thống ngoài:

~~~text
Outbox event NEW
    → publisher lấy bản ghi
    → gửi tới broker/partner
    → ghi nhận kết quả gửi
    → retry có giới hạn/backoff nếu lỗi
    → alert/dead-letter theo quy trình nếu không thể xử lý
~~~

Outbox giúp không đánh mất **ý định phát sự kiện** đã commit với order, trong phạm vi một database giao dịch. Nhưng publisher có thể gửi **trùng** sau crash, vì vậy consumer/partner cũng phải idempotent theo `eventId` hoặc business key. Outbox không tự bảo đảm “exactly-once end-to-end”.

### 9.2. `AFTER_COMMIT` chưa đủ thay thế outbox

Spring có `@TransactionalEventListener(phase = AFTER_COMMIT)` để xử lý listener sau commit. Với việc cập nhật cache hoặc notification best-effort, cách này có thể phù hợp.

Tuy nhiên, nếu process crash **sau commit và trước callback**, ý định gửi chỉ nằm trong memory có thể bị mất. Nếu hợp đồng yêu cầu eventual delivery bền vững qua restart, cần lưu công việc vào DB/outbox/queue durable trước khi trả receipt thành công.

### 9.3. Mốc cam kết giữa nhiều hệ thống

| Thiết kế | Mốc có thể xác nhận | Điều chưa được bảo đảm |
| --- | --- | --- |
| Order commit trong một DB | Order đã lưu | Kho biết đơn |
| Order + outbox commit cùng DB | Order và ý định phát sự kiện đã lưu | Event đã được nhận ngoài DB |
| Broker ACK theo cơ chế broker | Broker đã nhận theo cam kết broker | Consumer đã áp dụng nghiệp vụ |
| Consumer lưu kết quả thành công | Bước downstream đó đã hoàn tất | Những bước downstream khác |
| Workflow toàn bộ hoàn tất | Có thể báo trạng thái cuối | Client đã nhận response trạng thái cuối |

Nếu cần một giao dịch nghiệp vụ kéo dài qua thanh toán, kho và vận chuyển, nên xây workflow/saga và trạng thái bền vững. **Không** giữ transaction DB mở chờ mọi bước remote trả lời.

## 10. Đồng bộ, bất đồng bộ và ý nghĩa response status

**SOAP request-response** nói về trao đổi thông điệp, không đồng nghĩa toàn bộ nghiệp vụ phải hoàn tất đồng bộ.

### 10.1. Đồng bộ cho bước tiếp nhận

~~~text
SOAP SubmitOrder
  → validate/authenticate/authorize
  → transaction: lưu order + outbox
  → commit
  → SOAP response ACCEPTED + orderId
~~~

Hợp đồng có thể hứa rằng order tồn tại để truy vấn ngay (tùy consistency của kiến trúc đọc), nhưng không hứa kho đã giao hàng. Nếu commit thất bại, **không trả `ACCEPTED`** như một response thành công thông thường.

### 10.2. Bất đồng bộ có trạng thái bền vững

~~~text
SOAP SubmitOrder
  → transaction: lưu order/job PENDING_REVIEW
  → commit
  → response PENDING_REVIEW + trackingId
  → worker xử lý sau
  → trạng thái APPROVED / REJECTED / COMPLETED
~~~

Ở đây `PENDING_REVIEW` chỉ có nghĩa job đã được tiếp nhận **bền vững**, không phải đã phê duyệt. Contract cần công bố operation truy vấn như `GetOrderStatus` hoặc callback/notification nếu dùng.

Đừng trả `COMPLETED` ngay sau khi chỉ đẩy task vào `@Async` trên memory, vì crash có thể làm mất task. Một status phải gắn với điều kiện bền vững mà hệ thống có thể chứng minh.

### 10.3. Một timeout có ý nghĩa gì?

~~~text
Client thấy timeout / connection reset
               ≠
Server chắc chắn chưa nhận request
               ≠
Transaction chắc chắn rollback
~~~

Đối với client, kết quả là **chưa biết**. Hành động đúng là retry an toàn cùng requestId, hoặc query trạng thái theo contract; không tự sinh requestId mới cho mỗi lần timeout.

## 11. SOAP Fault phải phản ánh lỗi mà không nói sai trạng thái DB

### 11.1. Phân loại lỗi theo thời điểm

| Tình huống | DB transaction trong kiến trúc mẫu | Cách xử lý |
| --- | --- | --- |
| XML không hợp XSD | Use case chưa được gọi | SOAP Fault lỗi request |
| WS-Security/timestamp/chữ ký thất bại | Không cho chạy nghiệp vụ | Security fault/từ chối theo policy |
| Buyer không có quyền | Không tạo order mới | Authorization fault có kiểm soát |
| Rule nghiệp vụ không thỏa | Rollback/không ghi mới | Business fault theo contract |
| RequestId xung đột với payload khác | Không tạo order thứ hai | Fault `REQUEST_ID_CONFLICT` |
| Database báo lỗi trước hoặc tại commit | Không có success receipt; cần làm rõ kết quả nếu lỗi mất kết nối xảy ra sát commit | Fault hoặc transport failure |
| Response mapper lỗi **sau commit** | Order vẫn tồn tại | Fault hoặc connection failure, retry/query |
| Mạng đứt sau commit | Order vẫn tồn tại | Client retry/query |
| Outbox publisher lỗi sau commit | Order/outbox vẫn tồn tại | Publisher retry, không rollback order |
| Downstream từ chối đơn về sau | Order vẫn đã được tiếp nhận trước đó | Cập nhật trạng thái nghiệp vụ, không viết lại receipt lịch sử |

SOAP 1.1 dùng các faultcode như `Client` và `Server`; SOAP 1.2 dùng `Sender`/`Receiver` và cấu trúc Fault khác. Spring-WS có `EndpointExceptionResolver` để ánh xạ exception, nhưng **không tự bảo đảm** mọi exception Java trở thành fault detail mà đối tác mong muốn.

### 11.2. Fault có mã máy đọc được

Ví dụ SOAP 1.1 Fault khi cùng `requestId` nhưng dữ liệu khác:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soapenv:Client</faultcode>
      <faultstring>Conflicting requestId</faultstring>
      <detail>
        <ord:OrderFault xmlns:ord="urn:example:orders:v1">
          <ord:code>REQUEST_ID_CONFLICT</ord:code>
          <ord:requestId>REQ-2026-0081</ord:requestId>
        </ord:OrderFault>
      </detail>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>
~~~

`OrderFault` **chưa nằm trong XSD ví dụ mục 2**. Khi dùng thực tế, phải định nghĩa schema fault detail, WSDL fault nếu cần và exception resolver tạo đúng nội dung. Client nên dựa trên stable fault code để quyết định có retry hay không, không so khớp `faultstring` mang tính diễn giải.

### 11.3. Lỗi ngay lúc commit có thể mơ hồ

Nếu DB xác nhận rollback, không trả success receipt. Tuy nhiên, trường hợp driver mất kết nối đúng lúc gửi lệnh commit có thể khiến phía ứng dụng **không biết chắc** DB đã commit hay chưa (phụ thuộc DB/driver và sự cố). Vì vậy không được hứa “mọi commit exception đều chắc chắn không có order”.

Với trường hợp không rõ, dùng idempotency key để tra cứu kết quả durable sau khi kết nối phục hồi; nếu chưa có, retry đúng chính sách. Đây cũng là lý do fault/network recovery phải được thiết kế **ngay trong hợp đồng**.

### 11.4. Không phải cứ HTTP lỗi là transaction rollback

HTTP 200 thường đi với SOAP success, HTTP 500 thường đi với SOAP 1.1 Fault, nhưng proxy, SOAP version và lỗi transport có thể làm hành vi khác. Client cần phân biệt:

- **SOAP response thành công** chứa receipt.
- **SOAP Fault** có fault code/detail.
- **HTTP/network failure** không có SOAP response đáng tin cậy.

Chỉ nhìn HTTP status không đủ kết luận DB đã commit hay chưa.

## 12. Validation, bảo mật và lúc bắt đầu transaction

Một đường đi điển hình:

~~~text
TLS/mTLS, gateway/filter
       ↓
SOAP parsing với XML parser an toàn
       ↓
Endpoint mapping
       ↓
WS-Security + schema validation interceptors (theo cấu hình)
       ↓
Endpoint mapper, authorization context
       ↓
@Transactional application service
       ↓
SOAP response / fault
~~~

| Lớp | Trách nhiệm | Không được suy diễn |
| --- | --- | --- |
| TLS/mTLS | Kênh mã hóa, kiểm tra chain/hostname/client cert theo chính sách | Không tự chứng minh payload SOAP hợp XSD |
| WS-Security/WSS4J (ví dụ `Wss4jSecurityInterceptor`) | Signature, timestamp, token, encryption theo policy | Không thay DB transaction |
| XML parser an toàn | Chống XXE/external entity, giới hạn size/depth/time | Không tự kiểm quyền buyer |
| `PayloadValidatingInterceptor` | Kiểm QName, kiểu, thứ tự, cardinality theo XSD | Không kiểm tồn kho/quyền |
| Application authorization | Principal đáng tin được phép tạo đơn? | Không tin `buyerId` client khai báo tùy ý |
| DB transaction | Atomicity các ghi trên tài nguyên cùng tx | Không xác nhận client đã nhận response |

**Lưu ý:** `EndpointInterceptor` thường được gắn với invocation chain **sau khi tìm được endpoint**. Không thể khẳng định interceptor này bảo vệ toàn bộ HTTP path kể cả request không map được; gateway, servlet filter và transport vẫn cần chính sách riêng.

### 12.1. Phải xử lý đúng phần tử đã được ký

Với XML Signature, phải bảo đảm node được xác minh chữ ký **chính là node** được JAXB/endpoint dùng. Không tự chọn `//*[local-name()='SubmitOrderRequest']` mà bỏ qua namespace/security context; hệ thống dễ rơi vào lỗi XML signature wrapping.

DB transaction có thể hoàn toàn atomic nhưng vẫn commit dữ liệu sai nếu input bị giả mạo. Transaction và security là **hai trục bảo đảm độc lập**.

### 12.2. Business invariant cần được giữ trong transaction

Một rule như “tồn kho đủ để nhận đơn” có thể kiểm tra sớm để fail-fast. Nhưng nếu tồn kho thay đổi đồng thời, kiểm tra sớm **không đủ**. Khi commit, bất biến phải được bảo vệ bằng constraint, locking/version, atomic update hoặc cơ chế nhất quán phù hợp.

Đừng kiểm tồn kho trước khi mở transaction, rồi cho rằng kết quả đó vẫn chính xác sau khi các request khác đã cập nhật DB.

## 13. Ranh giới transaction theo loại use case

### 13.1. Query chỉ đọc

~~~java
@Service
public class GetOrderUseCase {

    private final OrderRepository repository;

    @Transactional(readOnly = true)
    public OrderView getById(String id) {
        OrderEntity entity = repository.requireById(id);
        return new OrderView(entity.getId(), entity.getState());
    }
}
~~~

Ví dụ này chuyển entity thành DTO **trước khi transaction kết thúc**, tránh endpoint truy cập lazy entity ngoài persistence context. `readOnly=true` là hint/optimization, không phải rào cản ghi tuyệt đối hoặc authorization.

### 13.2. Command all-or-nothing

~~~text
BEGIN
  Validate transactional business invariants
  Insert order and lines
  Save idempotency receipt
  Insert outbox events
COMMIT
~~~

Một local transaction bảo đảm atomicity cho các ghi **tham gia cùng transactional database và transaction manager**. Nếu một bước thất bại, việc rollback phải loại bỏ toàn bộ thay đổi thuộc transaction đó.

### 13.3. Command phối hợp hệ thống ngoài

Đối với thanh toán, kho hoặc hệ thống SOAP bên ngoài:

- Không coi remote HTTP/SOAP call là phần của local DB transaction.
- Tách trạng thái “order đã nhận” và “đã thanh toán/giao kho”.
- Dùng business key idempotent ở các bước có thể retry.
- Thiết kế workflow/saga, compensation hoặc outbox thích hợp; không hứa rollback xuyên hệ thống chỉ bằng `@Transactional`.

### 13.4. Partial acceptance khác all-or-nothing

| Chính sách | Cách thiết kế đúng |
| --- | --- |
| **All-or-nothing** | Một item lỗi thì không commit đơn; SOAP Fault hoặc lỗi nghiệp vụ theo hợp đồng |
| **Partial acceptance** | Schema response phải biểu diễn kết quả từng item, rule commit rõ ràng; không âm thầm chuyển semantics |
| **Async batch** | Lưu durable job rồi trả trackingId và trạng thái tiếp nhận; kết quả item được cập nhật sau |

Nếu yêu cầu partial success, phải thay đổi cả **hợp đồng XML**, **giao dịch** và **kiểm thử**, không chỉ catch exception trong loop.

## 14. Kiểm thử transaction và thời điểm gửi response

### 14.1. Ma trận fault injection

| Kịch bản | Dữ liệu order/outbox | Kết quả client có thể thấy | Mục tiêu |
| --- | --- | --- | --- |
| XML sai QName/XSD | Không có ghi mới | Fault/lỗi request | Validation trước business |
| Caller không có quyền | Không có ghi mới | Từ chối | Authorization |
| Rule nghiệp vụ sai | Không có ghi mới | Business fault | Rollback |
| Order insert xong, outbox insert lỗi cùng tx | Cả hai rollback | Không có success receipt | Atomicity |
| Unique constraint lỗi ở commit | Không tạo success response bình thường | Fault/transport, cần xác minh kết quả | Commit boundary |
| Request hợp lệ, DB commit | Có order và outbox | `ACCEPTED` | Commit-before-response |
| Client disconnect sau commit | Có order/outbox | Timeout | Recovery |
| Retry cùng requestId và nội dung | Không tạo order thứ hai | Receipt cũ | Idempotency |
| Retry cùng key, payload khác | Không sửa order đầu | Fault `REQUEST_ID_CONFLICT` | Fingerprint |
| Hai request cùng key đồng thời | Chỉ một order commit | Kết quả theo retry policy | Unique index |
| Response mapper lỗi sau commit | Order vẫn tồn tại | Fault/connection failure | Hậu commit |
| Publisher outbox lỗi | Order/outbox vẫn còn | Receipt gốc không đảo ngược | Retry publisher |
| Crash server sau commit | Order/outbox còn sau restart | Client có thể timeout | Durability |
| Consumer nhận event lặp | Không tạo side effect trùng ở consumer | Không đổi receipt gốc | Downstream idempotency |

### 14.2. Unit test endpoint orchestration

~~~java
@Test
void createsSoapResponseAfterUseCaseReturns() {
    SubmitOrderRequest request = fixtureValidRequest();
    SubmissionReceipt receipt = new SubmissionReceipt(
        "REQ-2026-0081", "ORD-9021",
        Instant.parse("2026-11-27T02:45:00Z"));

    when(useCase.submit(any())).thenReturn(receipt);

    SubmitOrderResponse response = endpoint.submit(request);

    assertEquals("ORD-9021", response.getOrderId());
    assertEquals("ACCEPTED", response.getStatus());
    verify(useCase).submit(any());
}
~~~

Đây là khung JUnit/Mockito cần fixture, imports và dependency thích hợp. Vì `useCase` bị mock, test **không** kiểm chứng commit thật, transaction proxy, SOAP dispatcher hay đường truyền.

### 14.3. Integration test phải nhìn thấy commit thật

Một bài kiểm thử transaction cần:

1. Gọi **Spring service proxy thật** và database/transaction manager tương đương production.
2. Không bọc lời gọi trong outer transaction của test nếu cần kiểm tra commit **ngay khi service trả về**.
3. Truy vấn order/outbox từ transaction hoặc connection mới sau lời gọi.
4. Tiêm lỗi insert outbox để xác minh order rollback.
5. Gửi hai request đồng thời và kiểm tra unique key chỉ có một tác dụng phụ.
6. Test retry sau restart/crash hoặc network failure ở nơi có thể kiểm soát.
7. Kiểm tra exception lúc commit và sự khác biệt với lỗi sau commit.

**Bẫy:** test Spring có `@Transactional` trên test method thường rollback khi test kết thúc. Service `REQUIRED` lúc đó tham gia outer transaction và không commit ngay khi method service trả về. Dùng test không có outer transaction hoặc `TestTransaction`/`TransactionTemplate` đúng mục tiêu để kiểm tra boundary.

### 14.4. Kiểm thử Spring-WS

`MockWebServiceClient` giúp đưa XML payload qua hạ tầng Spring-WS test:

~~~java
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

client.sendRequest(
        withPayload(new StringSource(submitOrderRequestXml)))
      .andExpect(
        payload(new StringSource(expectedAcceptedResponseXml)));
~~~

Ví dụ cần Spring-WS Test, imports và fixtures. Payload fixture là phần tử root `SubmitOrderRequest`, không phải cả SOAP Envelope nếu dùng `withPayload(...)`. Dùng clock cố định hoặc assertion XML/XPath hợp lý cho `acceptedAt`; không so prefix XML bằng chuỗi cứng.

Ở phía client, `MockWebServiceServer` kiểm tra `WebServiceTemplate` gửi đúng QName, SOAPAction theo WSDL nếu dùng, và xử lý SOAP Fault/timeout. Kiểm thử client Java và .NET sinh từ WSDL công bố xác minh **tương thích XML trên mạng**, không chỉ object Java.

### 14.5. Thử crash window có chủ đích

Trong môi trường tích hợp có kiểm soát:

- Làm mất network response sau khi DB commit.
- Restart server; gửi lại cùng requestId; xác minh không tạo đơn mới.
- Tạm dừng outbox publisher; bảo đảm event vẫn tồn tại, sau đó giao lại khi publisher phục hồi.
- Kiểm tra consumer nhận lặp nhưng chỉ áp dụng nghiệp vụ một lần.

Unit test với repository mock **không đủ** chứng minh durability. Những bảo đảm đó cần DB, broker và failure injection thực tế.

## 15. Những lỗi thiết kế cần tránh

| Anti-pattern | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| Endpoint chứa SQL/transaction/remote SOAP | Transaction dài, tầng trách nhiệm lẫn nhau | Use case transactional riêng |
| Trả `ACCEPTED` khi chưa commit | Client tin đã lưu dù có thể rollback | Map response sau khi commit hoàn tất |
| Dựa vào HTTP status để kết luận DB rollback | Timeout có thể xảy ra sau commit | Idempotency/query |
| Retry bằng requestId mới | Có thể tạo nhiều đơn | Giữ cùng requestId cho một ý định |
| Chỉ query rồi insert, không unique constraint | Race condition | DB uniqueness + conflict recovery |
| Đọc tiếp trong JPA transaction đã rollback-only | Recovery không tin cậy | Context/transaction mới |
| Gọi đối tác trong DB transaction | Không atomic qua mạng, lock lâu | Outbox/saga |
| Callback in-memory `AFTER_COMMIT` được coi là durable | Process crash có thể mất event | Outbox nếu cần delivery bền vững |
| Mapper ghi DB sau khi service commit | Side effect ngoài boundary | Mapper thuần |
| Trả JPA entity qua JAXB | Lộ field, lazy loading, coupling | DTO/receipt riêng |
| Catch mọi lỗi rồi trả `success=false` | Mất SOAP Fault semantics | Resolver + stable fault detail |
| `@Transactional` với self-invocation | Proxy có thể bị bypass | Separate bean/TransactionTemplate |
| `readOnly=true` được dùng như authorization | Không phải cơ chế bảo mật | Principal + policy |
| “XML hợp XSD” bị coi là “chữ ký hợp lệ” | Bỏ qua WS-Security | Interceptor xác thực đúng node |
| Test có outer transaction mà tưởng service đã commit | Kết luận sai | Test đúng transaction boundary |

## 16. Quy trình thiết kế và checklist hoàn thiện

~~~mermaid
flowchart TD
    A["Xác định intent và tác dụng phụ"] --> B["Chọn mốc durable cho response status"]
    B --> C["Thiết kế XSD/WSDL, requestId, fault, retry"]
    C --> D["DB transaction, unique index, receipt"]
    D --> E{"Có side effect ngoài DB?"}
    E -- "Có" --> F["Outbox / durable workflow / saga"]
    E -- "Không" --> G["Xây service @Transactional"]
    F --> G
    G --> H["Endpoint map XML ↔ command/receipt"]
    H --> I["Validation, WS-Security, authorization"]
    I --> J["Test rollback, commit, timeout, concurrency"]
    J --> K["Interoperability SOAP clients"]
~~~

Trước khi công bố một endpoint có tác dụng phụ, hãy thống nhất các quyết định:

1. `status` trong response nghĩa chính xác điều gì? Mốc commit nào phải hoàn thành?
2. `requestId` duy nhất theo phạm vi nào và tồn tại trong bao lâu?
3. Retry cùng khóa nhưng dữ liệu khác trả lỗi gì?
4. Client có operation nào để query trạng thái sau timeout?
5. Những lỗi nào chắc chắn chưa tạo order, những lỗi nào có kết quả chưa xác định?
6. Event downstream có thể giao trùng không và consumer xử lý thế nào?
7. Buyer/principal được xác thực, phân quyền và kiểm chữ ký ra sao?
8. Các version XSD/WSDL/JAXB/SOAP client nào cần tương thích?

### Câu hỏi tự kiểm tra

1. Vì sao tạo `SubmissionReceipt` bên trong service chưa chứng minh transaction đã commit?
2. Khi service transactional dùng `REQUIRED` và **không có outer transaction**, commit diễn ra trước hay sau lúc endpoint nhận result?
3. Vì sao client timeout sau khi gọi `SubmitOrder` không chứng minh đơn chưa được tạo?
4. Unique constraint giúp gì khi hai request cùng `requestId` tới đồng thời?
5. Nếu JAXB marshal lỗi sau khi order đã commit, có thể rollback transaction cũ không? Recovery nên làm gì?
6. Vì sao `@Transactional` không tạo atomicity xuyên HTTP SOAP call tới đối tác?
7. `@TransactionalEventListener(AFTER_COMMIT)` khác outbox ở bảo đảm durability nào?
8. `PENDING_REVIEW` và `COMPLETED` khác gì khi worker xử lý bất đồng bộ?
9. Tại sao SOAP Fault business, XSD validation fault và network timeout cần retry policy khác nhau?
10. Vì sao test service với outer `@Transactional` dễ đưa ra kết luận sai về mốc commit?
11. Khi SOAP Body được ký số, điều gì bảo đảm endpoint dùng đúng node đã được xác minh?
12. Nếu nghiệp vụ cho partial acceptance, những gì phải thay đổi trong response XSD, transaction và test?

**Ghi nhớ:** `@Endpoint` nên là ranh giới chuyển đổi SOAP ↔ use case, còn **application service `@Transactional` sở hữu ranh giới commit**. Với command có tác dụng phụ, response thành công chỉ được tạo sau khi mốc cam kết định nghĩa trong hợp đồng đã hoàn tất. Dù DB commit, SOAP response vẫn có thể thất lạc; **idempotency, unique constraint, outbox và kiểm thử timeout/crash** mới giúp tích hợp doanh nghiệp tin cậy.
