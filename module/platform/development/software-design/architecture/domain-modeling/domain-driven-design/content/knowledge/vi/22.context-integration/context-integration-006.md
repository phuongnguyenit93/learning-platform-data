# Phân biệt định danh nội bộ với định danh được trao đổi

Trong Domain-Driven Design (DDD), Entity được nhận diện bằng danh tính ổn định trong suốt vòng đời của nó. Tuy nhiên, một hệ thống thường có nhiều Bounded Context, mỗi context có mô hình, ngôn ngữ và quyền sở hữu dữ liệu riêng. Vì vậy, định danh dùng bên trong một context không nhất thiết phải là định danh được công bố cho context khác, API công khai hoặc đối tác.

Nếu dùng một ID cho mọi mục đích mà không xác định rõ ý nghĩa, hệ thống dễ ghép nhầm dữ liệu, phụ thuộc vào cấu trúc lưu trữ nội bộ và khó thay đổi khi tích hợp. Một mã khách hàng trong CRM có thể khác mã khách hàng trong Billing; mã đơn nội bộ có thể khác số đơn hiển thị cho người mua và mã đơn do đối tác vận chuyển cấp.

Bài học này trình bày cách phân biệt định danh nội bộ, định danh nghiệp vụ và định danh trao đổi; cách ánh xạ ID giữa các Bounded Context; cách thiết kế API và Domain Event để tham chiếu đúng thực thể; đồng thời phân biệt Entity ID với event ID, correlation ID và idempotency key. Mục tiêu là giữ quyền sở hữu mô hình ở từng context trong khi vẫn trao đổi được dữ liệu một cách rõ ràng, ổn định và có thể kiểm soát.

## 1. Định danh trong mô hình miền

### 1.1. Entity được nhận diện bằng danh tính

Entity là đối tượng có danh tính riêng và có thể thay đổi trạng thái trong suốt vòng đời. Hai Entity có cùng các thuộc tính không nhất thiết là cùng một Entity.

Ví dụ, hai đơn hàng có cùng khách hàng, sản phẩm và tổng tiền vẫn là hai đơn khác nhau nếu được tạo thành hai giao dịch khác nhau. Order ID giúp hệ thống nhận diện từng đơn hàng xuyên suốt quá trình tạo, xác nhận, giao hàng và hủy.

Định danh của Entity cần có các đặc tính phù hợp với nghiệp vụ:

- Ổn định trong vòng đời Entity.
- Phân biệt được các Entity trong phạm vi quản lý.
- Không phụ thuộc vào những thuộc tính có thể thay đổi như tên hoặc địa chỉ.
- Có thể được dùng để tham chiếu Entity mà không phải truyền toàn bộ dữ liệu của nó.

### 1.2. Định danh luôn có một phạm vi

Một ID chỉ có ý nghĩa khi biết phạm vi mà nó duy nhất.

Ví dụ:

- CustomerId duy nhất trong Customer Context.
- AccountId duy nhất trong Account Context.
- PartnerOrderId duy nhất trong hệ thống của đối tác.
- OrderNumber duy nhất theo quy tắc đánh số đơn của một doanh nghiệp hoặc một kênh bán.

Hai hệ thống có thể cùng tạo ra chuỗi 12345 nhưng chuỗi đó không nhất thiết chỉ cùng một đối tượng. Nếu thiếu thông tin về hệ thống phát hành hoặc phạm vi, việc trao đổi ID có thể dẫn đến liên kết nhầm.

### 1.3. ID không phải là toàn bộ ý nghĩa của Entity

Một ID cho biết đối tượng nào đang được tham chiếu, nhưng không tự mô tả:

- Đối tượng thuộc Bounded Context nào.
- Ai sở hữu dữ liệu.
- Đối tượng đang ở trạng thái nào.
- Bên nhận có quyền đọc hoặc thay đổi nó hay không.
- ID có thể được sử dụng trong những hợp đồng tích hợp nào.

Không nên dùng một ID như bằng chứng xác thực hoặc quyền truy cập. Biết OrderId không có nghĩa người gọi được phép xem đơn hàng. Authorization vẫn cần được kiểm tra riêng.

## 2. Các loại định danh thường gặp

Trong hệ thống DDD, nhiều loại mã có thể cùng xuất hiện trên một Entity. Chúng có mục đích khác nhau và không nên bị đánh đồng.

| Loại định danh | Mục đích | Ví dụ |
|---|---|---|
| Internal ID | Nhận diện Entity trong context sở hữu | SalesOrderId |
| Business ID / Business Number | Mã có ý nghĩa trong quy trình hoặc giao tiếp nghiệp vụ | SO-2026-00125 |
| Public ID | Định danh tài nguyên trong API công khai | ord_8f3a... |
| External ID | Mã do hệ thống hoặc đối tác khác cấp | CarrierShipmentId |
| Event ID | Nhận diện một thông điệp sự kiện cụ thể | EventId |
| Correlation ID | Liên kết nhiều thông điệp trong cùng một quy trình | CorrelationId |
| Idempotency Key | Nhận diện một yêu cầu cần xử lý lặp an toàn | IdempotencyKey |

Một hệ thống có thể dùng cùng một giá trị cho nhiều vai trò nếu có chủ đích, nhưng hợp đồng và vòng đời của các vai trò vẫn khác nhau. Khi thiết kế, hãy đặt tên theo ý nghĩa thay vì dùng một trường chung chung id cho mọi loại mã.

### 2.1. Internal ID

Internal ID được tạo và quản lý trong Bounded Context sở hữu Entity. Nó có thể là UUID, số tăng tự động hoặc một kiểu ID chuyên biệt khác.

Ví dụ:

~~~java
public record SalesOrderId(UUID value) {
    public SalesOrderId {
        Objects.requireNonNull(value);
    }

    public static SalesOrderId generate() {
        return new SalesOrderId(UUID.randomUUID());
    }
}
~~~

Internal ID có thể là khóa chính của database, nhưng hai khái niệm không bắt buộc phải giống nhau. Một hệ thống có thể dùng sequence nội bộ trong database và dùng một ID khác làm định danh của mô hình miền.

Không cần thay đổi ID chỉ vì nó là số tăng tự động. Cần đánh giá xem việc công bố ID đó có làm lộ thông tin không mong muốn, tạo phụ thuộc vào cấu trúc lưu trữ hoặc gây khó khăn cho hợp đồng tích hợp hay không.

### 2.2. Business ID hoặc Business Number

Business ID là mã được con người hoặc quy trình nghiệp vụ sử dụng. Ví dụ số đơn SO-2026-00125, mã hợp đồng hoặc mã hồ sơ.

Business ID có thể có định dạng dễ đọc và quy tắc đánh số riêng. Nó thường hữu ích trên hóa đơn, màn hình hỗ trợ khách hàng hoặc chứng từ.

Tuy nhiên, Business ID không tự động là khóa chính tốt. Một số mã có thể được cấp lại, thay đổi theo năm, có phạm vi duy nhất theo chi nhánh hoặc chứa thông tin có thể được điều chỉnh.

Nếu business number là một phần của ngôn ngữ nghiệp vụ, hãy mô hình hóa nó thành Value Object và xác định rõ phạm vi duy nhất.

~~~java
public record OrderNumber(String value) {
    public OrderNumber {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Order number is required"
            );
        }
    }
}
~~~

### 2.3. Public ID

Public ID được công bố qua API hoặc giao diện bên ngoài. Nó có thể trùng Internal ID nếu doanh nghiệp chấp nhận điều đó và hợp đồng được quản lý rõ.

Một Public ID riêng có thể giúp hệ thống:

- Không phụ thuộc trực tiếp vào kiểu khóa database.
- Giữ URL ổn định khi thay đổi persistence.
- Tránh để lộ sequence có thể suy đoán số lượng bản ghi.
- Phân biệt tài nguyên công khai với khóa nội bộ.
- Có không gian định danh phù hợp cho nhiều loại tài nguyên.

Public ID không thay thế kiểm tra quyền truy cập. Một chuỗi khó đoán chỉ giảm khả năng dò mã, không phải cơ chế authorization.

### 2.4. External ID

External ID được cấp bởi một hệ thống khác. Ví dụ, hệ thống vận chuyển cấp ShipmentId, cổng thanh toán cấp PaymentReference, hoặc nền tảng bán hàng cấp mã đơn của họ.

External ID chỉ duy nhất trong phạm vi do hệ thống phát hành quy định. Vì vậy, một External ID thường cần đi kèm tên hệ thống nguồn, tenant, đối tác hoặc loại tài nguyên.

Ví dụ:

~~~java
public record ExternalOrderReference(
    String sourceSystem,
    String value
) {
    public ExternalOrderReference {
        if (sourceSystem == null || sourceSystem.isBlank()) {
            throw new IllegalArgumentException(
                "Source system is required"
            );
        }

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "External order reference is required"
            );
        }
    }
}
~~~

Không nên chỉ lưu externalId = 123 nếu có thể nhận cùng chuỗi 123 từ nhiều đối tác. Phạm vi định danh phải là một phần của khóa ánh xạ.

## 3. Vì sao không nên mặc định chia sẻ Internal ID giữa các Bounded Context?

### 3.1. Mỗi Bounded Context sở hữu một mô hình riêng

DDD xem Bounded Context là ranh giới trong đó một mô hình và ngôn ngữ có ý nghĩa nhất quán. Cùng một khái niệm trong hai context có thể có cấu trúc và vòng đời khác nhau.

Ví dụ:

- Sales Context quản lý đơn hàng thương mại và khách mua.
- Fulfillment Context quản lý công việc lấy hàng, đóng gói và giao hàng.
- Billing Context quản lý hóa đơn, khoản phải thu và chứng từ.

Sales có thể có SalesOrderId. Fulfillment có thể có FulfillmentOrderId. Billing có thể có InvoiceId. Một đơn hàng thương mại có thể tạo ra nhiều công việc fulfillment và nhiều hóa đơn hoặc chứng từ liên quan.

Nếu ép tất cả context dùng chung một lớp Order và một ID nội bộ, các mô hình dễ phụ thuộc vào cách tổ chức dữ liệu của nhau. Một thay đổi trong Sales có thể buộc Fulfillment và Billing thay đổi dù ngữ nghĩa nghiệp vụ của chúng không đổi.

### 3.2. Cùng một thực thể nghiệp vụ có thể có nhiều cách biểu diễn

Một đơn hàng trong Sales có thể được xem là:

- Đơn hàng đã được khách xác nhận.
- Một yêu cầu cần giữ hàng trong Fulfillment.
- Cơ sở phát hành hóa đơn trong Billing.

Các context có thể tham chiếu cùng giao dịch gốc, nhưng không nhất thiết phải dùng cùng Entity hoặc cùng khóa nội bộ. Bên nhận có thể lưu ID do bên gửi cấp như một External Reference và tạo ID riêng cho Aggregate của mình.

### 3.3. Chia sẻ ID vẫn có thể đúng nếu là quyết định kiến trúc có chủ đích

Không có quy tắc tuyệt đối rằng mọi Bounded Context phải có ID khác nhau. Một tổ chức có thể có Party Context hoặc Identity Context sở hữu một định danh toàn doanh nghiệp. Các context khác có thể dùng định danh đó khi chúng thực sự tham chiếu cùng một khái niệm đã được thống nhất.

Điều cần tránh là vô tình chia sẻ khóa database hoặc dùng chung ID chỉ vì thuận tiện. Nếu ID là một phần hợp đồng liên context, cần xác định:

- Context nào phát hành và sở hữu ID.
- ID có ổn định qua thay đổi hệ thống không.
- Những context nào được phép tham chiếu.
- Quy tắc khi dữ liệu được hợp nhất, tách hoặc xóa.
- Ai chịu trách nhiệm duy trì tính duy nhất và ánh xạ.

## 4. Ví dụ: Sales và Fulfillment dùng định danh riêng

Giả sử khách đặt một đơn trong Sales Context. Khi đơn được xác nhận, Sales phát sự kiện SalesOrderConfirmed. Fulfillment nhận sự kiện và tạo công việc xử lý giao hàng.

Hai context có mô hình riêng:

~~~text
Sales Context
    SalesOrder
        SalesOrderId
        OrderNumber
        CustomerId
        Lines
        Status

             |
             | SalesOrderConfirmed
             v

Fulfillment Context
    FulfillmentOrder
        FulfillmentOrderId
        SourceSalesOrderId
        PickingTasks
        DeliveryStatus
~~~

Sales sở hữu SalesOrderId. Fulfillment sở hữu FulfillmentOrderId. Fulfillment lưu SourceSalesOrderId để biết công việc của nó phát sinh từ đơn nào.

Nếu một đơn Sales tạo hai shipment hoặc nhiều fulfillment order theo kho, không thể giả định một SalesOrderId tương ứng đúng một FulfillmentOrderId. Quan hệ một-nhiều phải được phản ánh trong mô hình tích hợp.

### 4.1. Các kiểu ID riêng biệt trong Java

~~~java
public record SalesOrderId(UUID value) {
    public SalesOrderId {
        Objects.requireNonNull(value);
    }
}

public record FulfillmentOrderId(UUID value) {
    public FulfillmentOrderId {
        Objects.requireNonNull(value);
    }
}
~~~

Dù cả hai dùng UUID, kiểu wrapper giúp compiler và người đọc phân biệt rõ ý nghĩa. Tránh truyền nhầm FulfillmentOrderId vào phương thức yêu cầu SalesOrderId.

### 4.2. Event mang định danh của context phát hành

~~~java
public record SalesOrderConfirmed(
    UUID eventId,
    SalesOrderId salesOrderId,
    OrderNumber orderNumber,
    Instant occurredAt,
    int schemaVersion
) {
}
~~~

Event mô tả sự việc đã xảy ra trong Sales Context. salesOrderId là ID của đơn hàng do Sales sở hữu. Event không cần mang toàn bộ Entity SalesOrder hoặc chia sẻ lớp domain của Sales cho Fulfillment.

Các trường được chọn phải đủ cho hợp đồng của consumer. Nếu Fulfillment cần dữ liệu dòng hàng, có thể công bố snapshot cần thiết hoặc yêu cầu một API phù hợp; không nên buộc consumer truy cập trực tiếp database của Sales.

### 4.3. Fulfillment tạo ID nội bộ riêng

~~~java
public final class FulfillmentOrder {

    private final FulfillmentOrderId id;
    private final SalesOrderId sourceSalesOrderId;

    public FulfillmentOrder(
        FulfillmentOrderId id,
        SalesOrderId sourceSalesOrderId
    ) {
        this.id = Objects.requireNonNull(id);
        this.sourceSalesOrderId =
            Objects.requireNonNull(sourceSalesOrderId);
    }

    public FulfillmentOrderId id() {
        return id;
    }

    public SalesOrderId sourceSalesOrderId() {
        return sourceSalesOrderId;
    }
}
~~~

Trong Fulfillment, sourceSalesOrderId là một tham chiếu đến nguồn phát sinh. Nó không biến SalesOrder thành một phần của Fulfillment Aggregate.

## 5. Bảng ánh xạ External ID sang Internal ID

### 5.1. Khi nào cần bảng ánh xạ?

Bảng ánh xạ hữu ích khi context nhận ID từ hệ thống khác và cần liên kết nó với Entity nội bộ.

Ví dụ:

| Source system | External order ID | Internal fulfillment ID |
|---|---|---|
| SALES | SO-1001 | FUL-9001 |
| SALES | SO-1002 | FUL-9002 |
| PARTNER-A | A-7788 | FUL-9003 |

Bảng này giúp Fulfillment tìm Aggregate của mình khi nhận thông điệp hoặc callback từ nguồn bên ngoài.

### 5.2. Phạm vi duy nhất của External ID

Một schema đơn giản có thể là:

~~~sql
CREATE TABLE external_order_mapping (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system VARCHAR(80) NOT NULL,
    external_order_id VARCHAR(160) NOT NULL,
    fulfillment_order_id UUID NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_external_order_source
        UNIQUE (
            source_system,
            external_order_id,
            fulfillment_order_id
        ),
    CONSTRAINT uq_fulfillment_order
        UNIQUE (fulfillment_order_id)
);
~~~

Unique constraint trên bộ ba source_system, external_order_id và fulfillment_order_id ngăn một liên kết bị ghi trùng. Schema này cho phép một external order tạo nhiều Fulfillment Order, đồng thời unique constraint trên fulfillment_order_id thể hiện giả định mỗi Fulfillment Order chỉ có một nguồn đơn trong ví dụ này.

Nếu nghiệp vụ yêu cầu quan hệ một-một, có thể bổ sung unique constraint trên (source_system, external_order_id). Nếu một Fulfillment Order được tạo từ nhiều nguồn, cần bỏ hoặc thay đổi unique constraint trên fulfillment_order_id. Schema phải phản ánh cardinality thực tế.

### 5.3. Không ghép ID bằng chuỗi tùy tiện

Tránh cách tạo khóa như:

~~~java
String key = sourceSystem + "-" + externalId;
~~~

Nếu thành phần có dấu phân cách hoặc quy tắc escape khác nhau, khóa ghép có thể mơ hồ. Dùng composite key có hai field rõ ràng hoặc một Value Object chuyên biệt.

~~~java
public record ExternalOrderKey(
    SourceSystem sourceSystem,
    String externalOrderId
) {
    public ExternalOrderKey {
        Objects.requireNonNull(sourceSystem);

        if (externalOrderId == null
            || externalOrderId.isBlank()) {
            throw new IllegalArgumentException(
                "External order id is required"
            );
        }
    }
}
~~~

### 5.4. Ánh xạ cần có vòng đời và chính sách

Không nên xóa mapping ngay khi một Aggregate hoàn tất nếu callback, đối soát hoặc yêu cầu hỗ trợ vẫn có thể tham chiếu ID cũ.

Cần quyết định:

- Mapping được giữ bao lâu?
- Có được thay đổi đích ánh xạ không?
- Nếu đối tác đổi mã thì lưu alias hay tạo mapping mới?
- Nếu hai bản ghi bị hợp nhất, lịch sử mapping được giữ thế nào?
- Khi nguồn gửi một ID đã từng dùng nhưng nội dung khác, hệ thống xử lý ra sao?

Định danh tích hợp là dữ liệu vận hành quan trọng, không chỉ là một cột phụ để join.

## 6. Anti-Corruption Layer chuyển đổi định danh và mô hình

### 6.1. Vai trò của Anti-Corruption Layer

Anti-Corruption Layer (ACL) bảo vệ mô hình của Bounded Context khỏi ngôn ngữ và cấu trúc của hệ thống bên ngoài. ACL nhận thông điệp, xác thực cấu trúc, chuyển đổi dữ liệu và định danh sang mô hình nội bộ.

Ví dụ đối tác vận chuyển gửi:

~~~json
{
  "partnerCode": "CARRIER-A",
  "shipmentRef": "SHIP-77881",
  "merchantOrderRef": "SO-1001",
  "status": "DELIVERED"
}
~~~

Fulfillment không nên đưa trực tiếp các chuỗi này vào mọi Entity miền. Adapter có thể chuyển thành các kiểu rõ nghĩa:

~~~java
public record CarrierShipmentId(String value) {
    public CarrierShipmentId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Carrier shipment id is required"
            );
        }
    }
}

public record CarrierOrderReference(
    String carrierCode,
    String value
) {
}
~~~

ACL tra cứu mapping từ merchantOrderRef và carrierCode, sau đó gọi hành vi trên Aggregate nội bộ phù hợp.

### 6.2. Chuyển đổi ở ranh giới, không rải khắp Domain Model

Nếu mọi Entity đều biết định dạng ID của đối tác, thay đổi API đối tác có thể lan khắp mô hình miền. Hãy tập trung parsing, validation và translation tại integration adapter hoặc ACL.

Domain Model nên nhận FulfillmentOrderId, CarrierShipmentId hoặc một kiểu miền đã được xác thực, thay vì tự xử lý JSON và chuỗi không rõ nguồn.

### 6.3. Không dùng ACL để che giấu dữ liệu mơ hồ

Nếu một external ID khớp nhiều bản ghi, ACL không nên tùy tiện chọn bản ghi đầu tiên. Nó cần từ chối hoặc đưa thông điệp vào luồng xử lý lỗi để con người hoặc quy trình đối soát giải quyết.

Nếu mapping chưa tồn tại, cần xác định có thể tạo mới hay phải chờ một sự kiện khác. Không suy ra Internal ID bằng cách chuyển kiểu hoặc tự ghép chuỗi.

## 7. Định danh trong API công khai

### 7.1. API nên công bố định danh có hợp đồng rõ ràng

Một API có thể trả về:

~~~json
{
  "id": "ord_01J8Y2WQ4K8...",
  "orderNumber": "SO-2026-00125",
  "status": "CONFIRMED"
}
~~~

Trong đó:

- id là Public ID để gọi lại tài nguyên.
- orderNumber là mã đơn dễ đọc cho người dùng.
- status là trạng thái được API công bố.

Hai trường có thể khác nhau và phục vụ hai mục đích khác nhau. API cần tài liệu hóa phạm vi duy nhất, tính ổn định và quy tắc sử dụng của từng trường.

### 7.2. Đừng dùng dữ liệu thay đổi làm resource ID

Tên khách, email, số điện thoại hoặc địa chỉ có thể thay đổi. Dùng chúng làm ID thường dẫn đến URL không ổn định, xử lý đổi dữ liệu phức tạp và nguy cơ lộ thông tin cá nhân.

Nếu nghiệp vụ có một mã tự nhiên bất biến, duy nhất và được quản lý tốt, nó có thể là business identifier phù hợp. Nhưng phải xác nhận các thuộc tính đó thay vì giả định.

### 7.3. Public ID không phải bí mật

ID khó đoán không thay thế authorization. API vẫn phải kiểm tra người dùng có quyền truy cập đúng tài nguyên theo tenant, chủ sở hữu và chính sách phân quyền.

Cũng không nên trả Internal ID chỉ vì nghĩ rằng UUID không thể bị đoán. Quyết định công bố ID cần dựa trên hợp đồng và ranh giới sở hữu, không dựa trên việc ID có khó đoán hay không.

### 7.4. Giữ API contract độc lập với khóa database

Nếu API trả trực tiếp khóa sequence, việc chuyển database hoặc thay đổi chiến lược khóa có thể ảnh hưởng client. Public ID ổn định giúp tách hợp đồng API khỏi chi tiết persistence.

Nếu đã công bố một ID, cần quản lý việc thay đổi định dạng, alias và khả năng tra cứu ngược trong thời gian tương thích. Không tái sử dụng ID cũ cho một tài nguyên mới.

## 8. Định danh trong Domain Event và Message

### 8.1. Phân biệt Entity ID với Event ID

Một Entity có thể phát nhiều sự kiện trong vòng đời:

- SalesOrderCreated.
- SalesOrderConfirmed.
- SalesOrderCancelled.
- SalesOrderShipped.

Tất cả sự kiện có thể mang cùng SalesOrderId, nhưng mỗi sự kiện cần EventId riêng để nhận diện một lần phát hành cụ thể.

~~~java
public record EventEnvelope<T>(
    UUID eventId,
    String eventType,
    int schemaVersion,
    Instant occurredAt,
    String sourceContext,
    String correlationId,
    String causationId,
    T payload
) {
}
~~~

eventId nhận diện thông điệp; payload.salesOrderId nhận diện Entity mà sự kiện nói đến. Không dùng hai giá trị thay thế nhau.

### 8.2. Correlation ID và Causation ID

Correlation ID liên kết nhiều thông điệp thuộc cùng một quy trình. Ví dụ một đơn hàng phát sinh yêu cầu giữ hàng, thanh toán, giao hàng và các phản hồi tương ứng. Các thông điệp có thể cùng mang một Correlation ID.

Causation ID chỉ ra thông điệp hoặc hành động trực tiếp dẫn đến sự kiện hiện tại. Nó hữu ích khi truy vết chuỗi nguyên nhân.

Cả hai không phải Entity ID. Một correlation có thể bao gồm nhiều Entity và nhiều Event.

### 8.3. Ví dụ event envelope

~~~json
{
  "eventId": "evt-91a2",
  "eventType": "SalesOrderConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T03:00:00Z",
  "sourceContext": "sales",
  "correlationId": "corr-7c11",
  "causationId": "cmd-5521",
  "payload": {
    "salesOrderId": "sales-order-1001",
    "orderNumber": "SO-2026-00125"
  }
}
~~~

Consumer cần biết ID nào là của nguồn phát hành, ID nào là của message và ID nào dùng để truy vết. Đừng đặt tất cả vào trường id chung chung.

### 8.4. Event nên mang định danh ổn định của nguồn

Khi consumer nhận event, salesOrderId vẫn là định danh do Sales phát hành. Consumer có thể:

- Lưu nó làm source reference.
- Tạo mapping với ID nội bộ.
- Dùng nó làm khóa tra cứu theo nguồn.
- Chuyển đổi qua ACL trước khi gọi domain behavior.

Consumer không nên giả định chuỗi đó là khóa chính của database mình.

## 9. Idempotency Key không phải Entity ID hay Event ID

### 9.1. Vì sao cần Idempotency Key?

Client có thể gửi lại cùng một yêu cầu vì timeout, mất kết nối hoặc không nhận được phản hồi. Nếu mỗi lần gửi lại đều tạo một đơn mới, hệ thống có thể phát sinh giao dịch trùng.

Idempotency Key giúp hệ thống nhận diện các lần gửi lại của cùng một ý định yêu cầu trong phạm vi được quy định.

Ví dụ request:

~~~http
POST /orders
Idempotency-Key: checkout-req-7f91
Content-Type: application/json
~~~

Client gửi lại cùng key trong thời gian hợp lệ, server có thể trả lại kết quả đã lưu thay vì tạo một Order khác.

### 9.2. Phạm vi của Idempotency Key

Một key nên được định nghĩa trong phạm vi rõ ràng, chẳng hạn:

- Client hoặc API credential.
- Tenant.
- Operation hoặc endpoint.
- Khoảng thời gian lưu giữ.

Cùng một key được dùng cho hai khách hàng khác nhau không nên vô tình trùng một bản ghi idempotency nếu phạm vi không cho phép.

### 9.3. Lưu key cùng dấu vân tay request

Một cách triển khai thường gặp:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id VARCHAR(80) NOT NULL,
    operation VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    response_status INTEGER,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_idempotency_scope
        UNIQUE (
            tenant_id,
            operation,
            idempotency_key
        )
);
~~~

Request hash giúp phát hiện trường hợp client vô tình dùng lại cùng key cho nội dung khác. Nếu key đã tồn tại nhưng request hash khác, server cần trả lỗi theo hợp đồng thay vì dùng kết quả cũ cho một yêu cầu khác.

### 9.4. Event deduplication có phạm vi khác

Consumer thường lưu EventId đã xử lý để tránh xử lý lại cùng message khi broker giao ít nhất một lần. Đó là deduplication của message.

Idempotency Key của command nhận diện ý định từ client. Entity ID nhận diện đối tượng. Event ID nhận diện một sự kiện. Ba loại này có thể liên quan nhưng không thể thay thế nhau.

## 10. Thiết kế kiểu định danh mạnh trong Java

### 10.1. Dùng wrapper type để tránh nhầm ID

Nếu mọi ID đều là String hoặc UUID, compiler không thể phát hiện truyền nhầm:

~~~java
void shipOrder(UUID orderId, UUID shipmentId) {
    // ...
}
~~~

Người gọi có thể vô tình đảo hai tham số. Wrapper type làm rõ ý nghĩa:

~~~java
public record SalesOrderId(UUID value) {
    public SalesOrderId {
        Objects.requireNonNull(value);
    }
}

public record ShipmentId(UUID value) {
    public ShipmentId {
        Objects.requireNonNull(value);
    }
}

void shipOrder(
    SalesOrderId orderId,
    ShipmentId shipmentId
) {
    // ...
}
~~~

Compiler sẽ từ chối truyền ShipmentId vào vị trí SalesOrderId.

### 10.2. Không ép mọi ID thành cùng một interface nếu mất ý nghĩa

Có thể tạo interface chung cho các ID nếu nó giúp một framework hoặc thư viện hoạt động. Tuy nhiên, đừng làm mọi ID trở thành một kiểu không phân biệt trong các API miền.

Tên kiểu nên thể hiện context và khái niệm sở hữu. CustomerId trong CRM và BillingCustomerId có thể khác nhau dù đều chứa UUID.

### 10.3. Kiểm tra null và định dạng tại ranh giới

Khi nhận ID từ HTTP hoặc message, adapter cần parse và xác thực định dạng trước khi tạo kiểu miền. Nếu định danh không hợp lệ, trả lỗi giao thức hoặc validation rõ ràng.

Không nên để chuỗi bất kỳ đi sâu vào Domain Model rồi mới gây lỗi ở một truy vấn database khó hiểu.

## 11. Xử lý thay đổi, hợp nhất và vòng đời định danh

### 11.1. Không tái sử dụng ID

Sau khi một Entity bị xóa hoặc ngừng hoạt động, ID cũ không nên được tái sử dụng cho Entity khác. Event, log, chứng từ và hệ thống tích hợp có thể vẫn tham chiếu ID cũ.

Nếu có yêu cầu xóa dữ liệu, cần phân biệt việc xóa thông tin cá nhân với việc tái sử dụng định danh. Có thể cần tombstone, alias hoặc bản ghi tham chiếu tối thiểu theo chính sách lưu trữ.

### 11.2. Khi hai Entity được hợp nhất

Ví dụ hai hồ sơ khách hàng được xác định là cùng một người và cần hợp nhất. Không nên tùy tiện đổi mọi ID đã công bố.

Một quy trình có thể chọn một Entity làm bản ghi còn hiệu lực, lưu alias từ ID cũ sang ID chuẩn và phát sự kiện CustomerMerged. Các context tiêu thụ sự kiện cập nhật mapping hoặc quan hệ theo chính sách.

Nếu context không cần đồng bộ ngay, cần xác định thời gian và cách xử lý tham chiếu cũ.

### 11.3. Khi nguồn bên ngoài đổi ID

Nếu đối tác cấp mã mới cho cùng một tài nguyên, cần biết mã mới là alias của tài nguyên cũ hay đại diện cho tài nguyên khác.

Có thể lưu nhiều External Reference cho cùng một Internal ID nếu hợp đồng cho phép. Cần có trạng thái hiệu lực, thời điểm bắt đầu/kết thúc hoặc nguồn xác nhận khi cần đối soát.

### 11.4. Không dùng tên hoặc email làm khóa liên context mặc định

Tên, email, số điện thoại và địa chỉ có thể thay đổi, có thể trùng hoặc có quy tắc chuẩn hóa phức tạp. Chúng phù hợp làm thuộc tính tìm kiếm hoặc đối chiếu, nhưng không nên mặc định là khóa liên kết lâu dài.

Nếu nghiệp vụ thực sự dùng một mã tự nhiên như mã số thuế hoặc mã đăng ký, cần xác nhận tính duy nhất, phạm vi, quyền sở hữu và quy tắc thay đổi trước khi dùng làm business identifier.

## 12. Bảo mật và quyền riêng tư của định danh

### 12.1. ID có thể tiết lộ thông tin

Một ID dạng sequence có thể làm lộ tương đối số lượng bản ghi hoặc tốc độ tăng trưởng. Một ID chứa mã khách, khu vực hoặc thời gian có thể tiết lộ dữ liệu nội bộ.

Định danh công khai nên tránh nhúng thông tin nhạy cảm nếu không có lý do nghiệp vụ rõ ràng.

### 12.2. ID khó đoán không phải cơ chế bảo vệ

UUID hoặc chuỗi ngẫu nhiên làm khó việc đoán tài nguyên nhưng không thay thế:

- Authentication.
- Authorization.
- Kiểm tra tenant.
- Kiểm tra quyền sở hữu.
- Audit log.

API phải kiểm tra quyền truy cập trên từng tài nguyên. Không được cho rằng người gọi biết ID thì đương nhiên có quyền sử dụng nó.

### 12.3. Tránh đưa dữ liệu cá nhân vào ID

Không mã hóa email, số điện thoại, tên hoặc ngày sinh vào một ID công khai. Hash dữ liệu cá nhân cũng không tự động làm dữ liệu vô danh; nếu không gian giá trị nhỏ, có thể dò ngược bằng cách thử các đầu vào phổ biến.

Dùng ID ngẫu nhiên hoặc ID không mang ý nghĩa cá nhân và giữ dữ liệu nhận dạng ở các trường được bảo vệ phù hợp.

### 12.4. Giới hạn dữ liệu trong log và event

Log và event có thể được lưu lâu hoặc sao chép qua nhiều hệ thống. Chỉ đưa định danh và thuộc tính cần thiết cho mục đích xử lý. Không thêm dữ liệu cá nhân chỉ để thuận tiện debug.

## 13. Kiểm thử hợp đồng định danh và mapping

### 13.1. Unit test cho kiểu ID

Kiểm tra:

- ID bắt buộc không null.
- Giá trị rỗng bị từ chối nếu chính sách yêu cầu.
- Hai kiểu ID khác nhau không thể bị truyền nhầm.
- Equality của wrapper dựa trên giá trị đúng như mong đợi.

### 13.2. Integration test cho mapping

Với bảng external mapping, kiểm tra:

- Cùng source và external ID tra ra đúng Internal ID.
- Cùng external ID từ hai source khác nhau được phân biệt.
- Cùng source và external ID không thể ánh xạ đến hai bản ghi nếu hợp đồng yêu cầu duy nhất.
- Mapping không tồn tại trả kết quả not found rõ ràng.
- Callback đến trước sự kiện tạo mapping được xử lý theo chính sách.
- Mapping được giữ sau khi Aggregate hoàn tất nếu còn cần đối soát.

### 13.3. Test consumer với event được giao lặp

Consumer nên nhận cùng Event ID hai lần và chỉ áp dụng tác động nghiệp vụ một lần. Việc lưu dấu đã xử lý cần có cơ chế nguyên tử phù hợp với cập nhật Aggregate để tránh đánh dấu event thành công nhưng thay đổi nghiệp vụ chưa commit.

### 13.4. Test thay đổi schema và nguồn phát hành

Nếu một đối tác thay đổi định dạng ID hoặc version event, contract test và adapter test cần xác nhận việc parse và mapping vẫn đúng. Không để thay đổi tên field hoặc kiểu dữ liệu lan vào Domain Model của consumer.

## 14. Những sai lầm thường gặp

### Dùng một trường id cho mọi loại mã

Điều này làm mờ nguồn phát hành và ý nghĩa. Hãy dùng tên rõ ràng như salesOrderId, externalOrderId, eventId và idempotencyKey.

### Dùng khóa database làm hợp đồng liên context

Consumer trở nên phụ thuộc vào cách lưu trữ của producer. Hãy công bố một định danh ổn định theo hợp đồng, hoặc để consumer ánh xạ ID nguồn sang ID nội bộ.

### Cho rằng ID giống nhau nghĩa là cùng một Entity

Hai context có thể có cùng chuỗi ID nhưng quản lý những khái niệm khác nhau. Luôn xác định source context và phạm vi duy nhất.

### Dùng email hoặc tên làm khóa

Các thuộc tính này có thể thay đổi hoặc trùng. Dùng định danh ổn định và giữ email/tên như thuộc tính nghiệp vụ.

### Để External ID đi sâu vào mọi lớp miền

Điều này gắn mô hình nội bộ với định dạng đối tác. Hãy chuyển đổi ở ACL hoặc adapter.

### Không đặt unique constraint cho mapping

Kiểm tra trùng trong code không đủ khi hai message đến đồng thời. Database cần bảo vệ uniqueness ở phạm vi đã định nghĩa.

### Nhầm Event ID với Aggregate ID

Một Aggregate phát nhiều event. Nếu dùng Aggregate ID làm khóa deduplication, consumer có thể bỏ qua các event hợp lệ tiếp theo của cùng Aggregate.

### Nhầm Idempotency Key với Event ID

Một command có thể tạo ra nhiều event; một event có thể được giao nhiều lần. Hai loại key phục vụ hai ranh giới khác nhau.

### Cho rằng Public ID là bí mật

ID không thay thế authorization. Luôn kiểm tra quyền trên tài nguyên và tenant.

### Chia sẻ ID toàn cục mà không có chủ sở hữu

Một ID toàn cục cần có context phát hành, quy tắc duy nhất và vòng đời được quản lý. Nếu không, nó dễ trở thành một coupling ẩn giữa các context.

## 15. Bài tập thực hành: tích hợp đơn hàng với đối tác vận chuyển

Một nền tảng thương mại điện tử tích hợp với hai đối tác vận chuyển. Sales phát hành SalesOrderId và OrderNumber. Fulfillment tạo FulfillmentOrderId. Mỗi đối tác cấp CarrierShipmentId riêng và gửi callback cập nhật trạng thái giao hàng.

Hãy thực hiện:

1. Xác định các loại ID trong Sales, Fulfillment và hệ thống đối tác.
2. Chọn ID nào được công bố trong API của nền tảng.
3. Thiết kế event SalesOrderConfirmed có định danh nguồn và metadata cần thiết.
4. Thiết kế bảng mapping cho SalesOrderId và CarrierShipmentId.
5. Xác định phạm vi unique của external ID theo từng đối tác.
6. Thiết kế ACL chuyển callback của đối tác thành lệnh miền trong Fulfillment.
7. Phân biệt Event ID, Correlation ID và Idempotency Key.
8. Viết test cho callback trùng, external ID không tồn tại và cùng mã từ hai đối tác.
9. Xác định cách xử lý khi đối tác đổi mã shipment hoặc gửi callback đến muộn.

### 15.1. Gợi ý mô hình mapping

~~~java
public record CarrierShipmentReference(
    String carrierCode,
    String externalShipmentId
) {
    public CarrierShipmentReference {
        if (carrierCode == null || carrierCode.isBlank()) {
            throw new IllegalArgumentException(
                "Carrier code is required"
            );
        }

        if (externalShipmentId == null
            || externalShipmentId.isBlank()) {
            throw new IllegalArgumentException(
                "External shipment id is required"
            );
        }
    }
}
~~~

Một mapping có thể lưu:

| Trường | Ý nghĩa |
|---|---|
| carrier_code | Nguồn phát hành ID |
| external_shipment_id | Mã shipment do đối tác cấp |
| fulfillment_order_id | Aggregate nội bộ cần tìm |
| created_at | Thời điểm tạo mapping |
| status | Trạng thái hiệu lực nếu cần quản lý alias |

Nếu một Fulfillment Order có nhiều shipment, mapping phải phản ánh quan hệ một-nhiều. Nếu một external shipment có thể được liên kết lại sau đối soát, cần quy tắc cập nhật và audit rõ ràng.

## 16. Checklist thiết kế định danh giữa các context

Trước khi công bố hoặc nhận một ID, hãy kiểm tra:

- Đã xác định Entity hoặc tài nguyên mà ID nhận diện.
- Đã biết context phát hành và sở hữu ID.
- Phạm vi duy nhất được định nghĩa rõ.
- Internal ID được phân biệt với business number và external ID.
- Public ID có hợp đồng ổn định và không phụ thuộc vô tình vào khóa database.
- Consumer không giả định external ID là khóa nội bộ của mình.
- Mapping có source/tenant scope và unique constraint phù hợp.
- ACL chuyển đổi định dạng và ngôn ngữ ở ranh giới tích hợp.
- Event ID, Aggregate ID, Correlation ID và Idempotency Key có mục đích riêng.
- Callback hoặc message giao lặp được xử lý idempotent.
- Quy tắc hợp nhất, alias, đổi mã và lưu giữ mapping đã rõ.
- ID không chứa dữ liệu cá nhân không cần thiết.
- Authorization được kiểm tra riêng, không dựa vào việc biết ID.
- Có unit test và integration test cho parsing, mapping, uniqueness và deduplication.

## Kết luận

Định danh nội bộ giúp một Bounded Context quản lý Entity theo mô hình và vòng đời của chính nó. Định danh được trao đổi là một phần của hợp đồng tích hợp và cần có nguồn phát hành, phạm vi duy nhất, ý nghĩa và chính sách vòng đời rõ ràng. Hai loại định danh có thể trùng giá trị nếu được thiết kế có chủ đích, nhưng không nên mặc định chúng là một.

Khi các context có mô hình riêng, hãy để context sở hữu phát hành Internal ID và để consumer lưu External Reference hoặc ánh xạ sang ID nội bộ của mình. ACL chịu trách nhiệm chuyển đổi dữ liệu và định danh ở ranh giới. Event ID, Correlation ID và Idempotency Key cần được phân biệt với Entity ID để xử lý message, truy vết và yêu cầu gửi lặp đúng cách.

Thiết kế định danh tốt giúp các Bounded Context trao đổi được với nhau mà không phải chia sẻ khóa lưu trữ hoặc phụ thuộc vào cấu trúc nội bộ của nhau. Điều quan trọng là luôn trả lời rõ: ai phát hành ID, nó duy nhất ở đâu, ai sở hữu nó và bên nhận phải dùng nó như thế nào.

