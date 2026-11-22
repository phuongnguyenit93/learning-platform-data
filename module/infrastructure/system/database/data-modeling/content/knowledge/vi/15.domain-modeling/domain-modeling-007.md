# Sự kiện miền để biểu diễn thay đổi có ý nghĩa nghiệp vụ

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **sự kiện miền** (*domain event*) là sự thật nghiệp vụ đã xảy ra, khác với command, trạng thái hiện tại và thao tác CRUD.
- Nhận diện sự kiện đáng mô hình hóa qua ngôn ngữ nghiệp vụ, ranh giới aggregate, bất biến và hậu quả của một thay đổi.
- Thiết kế tên, payload, định danh, thời gian, phiên bản và quan hệ nhân quả của sự kiện đủ rõ để lưu, phát và kiểm chứng.
- Phân biệt **domain event**, **integration event**, **audit log**, **outbox message** và **event sourcing**.
- Đưa thay đổi trạng thái aggregate và sự kiện cần công bố vào cùng một giao dịch khi sử dụng cơ sở dữ liệu quan hệ.
- Xử lý thông điệp lặp, thất lạc phản hồi, không đúng thứ tự và thay đổi schema sự kiện trong hệ thống có nhiều dịch vụ.
- Lựa chọn cấu trúc lưu sự kiện trong dữ liệu quan hệ, document, đồ thị hoặc kho phân tích mà không làm mờ quyền sở hữu nghiệp vụ.

Trong module **DATABASE_DATA_MODELING**, thiết kế dữ liệu không chỉ là chọn thực thể, khóa, quan hệ và chỉ mục; còn phải diễn đạt **điều gì đã thay đổi và vì sao thay đổi đó quan trọng**. Một dòng được cập nhật từ DRAFT sang CONFIRMED là chi tiết lưu trữ. Còn sự kiện **OrderConfirmed** là thông tin nghiệp vụ: một đơn hàng cụ thể đã được xác nhận theo quy tắc của Sales. Sự khác biệt này giúp thiết kế mô hình rõ ý nghĩa, dễ tích hợp và có thể kiểm thử khi yêu cầu tiến hóa.

## 1. Sự kiện miền là điều đã xảy ra

**Domain event** biểu diễn một sự thật đáng quan tâm trong miền, xuất hiện **sau khi** một hành vi nghiệp vụ thành công. Tên sự kiện thường dùng thì quá khứ:

- OrderConfirmed — đơn đã được xác nhận.
- StockReserved — nguồn kho đã giữ một số lượng hàng.
- PaymentAuthorized — hệ thống thanh toán đã chấp nhận ủy quyền.
- SubscriptionCancelled — gói đăng ký đã bị hủy.
- ShipmentDelivered — kiện hàng đã được xác nhận giao.

Một sự kiện thường có danh tính của đối tượng liên quan, thông tin đủ để giải thích thay đổi, thời điểm xảy ra và định danh riêng của **lần sự kiện**. Nó không yêu cầu bên nhận tự ý sửa dữ liệu của aggregate phát sự kiện.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Command** | Ai muốn hệ thống làm gì? | ConfirmOrder(orderId) |
| **Aggregate** | Ai có thẩm quyền kiểm tra và thực hiện? | Order trong Sales |
| **State transition** | Trạng thái đã chuyển thế nào? | DRAFT → CONFIRMED |
| **Domain event** | Sự thật nghiệp vụ nào vừa được tạo? | OrderConfirmed |
| **Integration event** | Sự thật nào cần được công bố theo hợp đồng ngoài ngữ cảnh? | SalesOrderConfirmed v1 |
| **Reaction** | Bên nhận làm gì dựa trên sự thật ấy? | Tạo yêu cầu giữ hàng, cập nhật projection |

Sự kiện không phải lời đề nghị. **ReserveStock** là command yêu cầu Inventory cấp quyền giữ; **StockReserved** là event do Inventory công bố khi việc cấp quyền giữ đã thành công. Không đặt tên một thông điệp yêu cầu là StockReserved rồi coi như kho đã hoàn thành.

## 2. Khi nào nên phát sinh domain event?

Không phải mọi lần UPDATE một cột đều là sự kiện miền có ích. Một ứng viên tốt thường đáp ứng một hoặc nhiều điều kiện:

1. **Có tên trong ngôn ngữ nghiệp vụ:** nhân viên nói "đơn đã xác nhận", "hàng được giữ", "phiếu bị từ chối", thay vì "record được update".
2. **Đánh dấu mốc vòng đời:** sau mốc đó quyền thao tác, nghĩa vụ hoặc trạng thái kinh doanh thay đổi.
3. **Được nhiều hoạt động quan tâm:** thông báo, phân tích, quản lý tồn, kế toán, xử lý hậu mãi.
4. **Cần lưu dấu để giải thích:** vì sao một quyền lợi được cấp, ai duyệt, chính sách nào có hiệu lực.
5. **Có thể định nghĩa điều kiện xảy ra chính xác:** chỉ tạo nếu chuyển trạng thái thành công và các bất biến đã được bảo vệ.

Ví dụ:

| Thao tác | Có nên tạo domain event? | Lý do |
| --- | --- | --- |
| Xác nhận đơn từ DRAFT | Có: OrderConfirmed | Mốc cam kết nghiệp vụ, tạo trách nhiệm xử lý |
| Hủy đơn theo chính sách | Có: OrderCancelled | Kích hoạt xử lý bù và thông báo |
| Người dùng mở trang xem đơn | Thường không | Đây là truy vấn, không phải thay đổi trạng thái miền |
| Repository chạy UPDATE version | Không tự động | Version tăng là cơ chế kỹ thuật, không phải sự thật nghiệp vụ độc lập |
| Sửa lỗi dấu cách trong nhãn nội bộ | Tùy miền | Chỉ đáng là event nếu thay đổi có ý nghĩa hoặc yêu cầu audit |
| Lượt giữ chỗ hết hạn | Có thể: ReservationExpired | Cần có một quyết định/transition xác định việc hết hiệu lực |

**Sự kiện miền phải là mô tả chính xác một sự thật.** Nếu chỉ có một bộ đếm thời gian chạy qua hạn nhưng hệ thống chưa hề cập nhật quyền giữ, không được ngầm khẳng định đã giải phóng tài nguyên khi chưa có cơ chế bảo vệ. Có thể tính trạng thái "quá hạn" khi đọc hoặc thực hiện command ExpireReservation nguyên tử rồi phát ReservationExpired.

### Đặt tên gắn với nghiệp vụ, không gắn với SQL

Tránh các tên mơ hồ như EntityUpdated, OrderTableChanged hoặc DataSaved vì chúng không nêu thay đổi nào đáng chú ý. OrderConfirmed có nghĩa rõ hơn OrderStatusChanged: người nghe biết một bước nghiệp vụ đã xảy ra mà không cần suy ra từ cặp giá trị cũ/mới.

Trong một số hệ thống hạ tầng, Change Data Capture (CDC) phát thông điệp cho INSERT/UPDATE/DELETE của bảng. CDC hữu ích để vận chuyển thay đổi dữ liệu, nhưng **thông điệp CDC không tự động là domain event**: một thay đổi nghiệp vụ có thể ghi nhiều hàng, và một UPDATE không nhất thiết tương ứng một sự thật có ý nghĩa với người dùng.

## 3. Aggregate là nơi quyết định một sự kiện có xảy ra

Một aggregate root chịu trách nhiệm bảo vệ các bất biến cục bộ. Ví dụ Order quản lý trạng thái, các dòng hàng và thông tin giá đã chốt; chỉ root mới có quyền quyết định khi nào có thể confirm.

Giả định nghiệp vụ của ví dụ:

- Chỉ Order đang DRAFT mới được xác nhận.
- Order phải có ít nhất một dòng có số lượng hợp lệ.
- Khi chuyển sang CONFIRMED, dòng và đơn giá đã chốt không còn được sửa.
- Một lần xác nhận thành công tạo đúng **một sự thật OrderConfirmed cho lần chuyển đó**.
- Hai request cạnh tranh không được cùng xác nhận dựa trên cùng phiên bản cũ.

Luồng trách nhiệm:

~~~mermaid
flowchart LR
    C["Command: ConfirmOrder"] --> A["Order aggregate root"]
    A -->|"kiểm tra bất biến"| D{Hợp lệ?}
    D -->|"Không"| E["Lỗi miền, không có OrderConfirmed"]
    D -->|"Có"| S["Order chuyển CONFIRMED"]
    S --> V["Ghi nhận domain event OrderConfirmed"]
    V --> P["Repository + transaction"]
    P --> O["Trạng thái + outbox commit cùng nhau"]
    O --> B["Công bố integration event sau commit"]
~~~

Điểm quan trọng: **tạo đối tượng sự kiện trong bộ nhớ không đồng nghĩa sự kiện đã xảy ra bền vững**. Nếu transaction lưu Order thất bại và rollback, không được công bố OrderConfirmed như một sự thật đã commit. Application service/repository phải quyết định ranh giới commit và chỉ kích hoạt các tác động ngoài sau khi dữ liệu đã được ghi thành công.

### Domain event không trao quyền sửa aggregate khác

Sau OrderConfirmed, Inventory có thể nhận một thông điệp và quyết định xử lý yêu cầu giữ hàng. Nó không được sửa trực tiếp những cột trạng thái của Order trong database Sales. Tương tự, Sales không thể kết luận hàng đã giữ chỉ vì nó đã phát OrderConfirmed; cần nhận kết quả do Inventory có thẩm quyền cấp.

Nếu yêu cầu nghiệp vụ là "chỉ được xác nhận Order khi kho đã giữ đủ hàng", hãy thay đổi quy trình: giữ chỗ trước, nhận bằng chứng Reservation, rồi mới confirm; hoặc thêm trạng thái trung gian như AWAITING_STOCK. Không dùng một domain event bất đồng bộ như lời hứa rằng mọi bước tiếp theo đã thành công.

## 4. Thiết kế cấu trúc sự kiện miền

Một sự kiện nên **bất biến** và có ngữ nghĩa đủ ổn định để hiểu sau này. Các trường phổ biến:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| eventId | Định danh duy nhất của lần sự kiện | Khác aggregateId, requestId và ID của message broker |
| eventType | Tên của sự thật nghiệp vụ | Ví dụ OrderConfirmed; tránh dùng tên bảng |
| aggregateId | Root nào đã thay đổi | Nên có namespace/tenant khi phạm vi định danh yêu cầu |
| aggregateVersion | Phiên bản của root sau khi áp dụng thay đổi | Hỗ trợ phát hiện thứ tự, nhưng không có nghĩa thứ tự toàn hệ thống |
| occurredAt | Thời điểm sự kiện nghiệp vụ được xác nhận | Thường là UTC; cần chính sách với đồng hồ và thời gian ghi nhận |
| payload | Những dữ kiện mà bên quan tâm cần biết | Ghi ý nghĩa, đơn vị và kiểu dữ liệu rõ ràng |
| schemaVersion | Phiên bản hợp đồng sự kiện khi công bố ra ngoài | Giúp tương thích khi payload tiến hóa |
| correlationId / causationId | Nhóm các bước của cùng một quy trình / sự kiện dẫn đến bước này | Hữu ích cho truy vết, không thay thế eventId |
| producer | Nguồn chịu trách nhiệm phát thông điệp | Quan trọng khi nhiều hệ thống dùng tên sự kiện tương tự |

Không phải domain event nội bộ nào cũng cần toàn bộ các trường trên. Bên trong một bounded context có thể dùng kiểu dữ liệu nhỏ gọn, còn **integration event** phát ra ngoài thường cần envelope đầy đủ, version và quy ước vận hành.

### EventId, aggregateId, requestId khác nhau

Một Order có orderId cố định qua toàn bộ vòng đời. Người dùng có thể gửi một ConfirmOrder với requestId để retry. Khi commit, hệ thống phát một domain event OrderConfirmed với eventId. Broker có thể có thêm messageId do hạ tầng tạo. Bốn định danh có vai trò khác nhau:

~~~text
orderId    = định danh đối tượng nghiệp vụ
requestId  = định danh ý định/lệnh của caller để idempotency
eventId    = định danh một sự thật đã xảy ra
messageId  = định danh gói truyền trên hạ tầng (có thể đổi khi gửi lại)
~~~

Khi cùng requestId được xử lý lại do timeout, không tạo thêm OrderConfirmed nếu command đã thành công. Khi hệ thống gửi lại **cùng sự kiện đã commit**, phải giữ nguyên eventId để bên nhận nhận ra bản sao.

### Chọn payload có mục đích

Với OrderConfirmed, payload có thể chứa orderId, tenantId, tổng tiền, loại tiền, thời điểm xác nhận và phiên bản. Nếu Inventory cần chi tiết SKU/số lượng, cân nhắc một **integration event hoặc command dành riêng cho nhu cầu fulfillment** với hợp đồng rõ ràng. Không tự động đính kèm toàn bộ Customer, phương thức thanh toán, địa chỉ cá nhân và những object nội bộ của Order: payload lớn dễ rò rỉ dữ liệu, khó tiến hóa và làm bên nhận phụ thuộc cấu trúc miền.

Số tiền nên có kiểu số thập phân chính xác hoặc biểu diễn chuỗi decimal với currency. Timestamp phải chỉ rõ múi giờ. Các field tùy chọn, đơn vị đo và ý nghĩa "đã chốt" cần được tài liệu hóa.

## 5. Ví dụ Java 17: Order ghi nhận sự kiện khi confirm

Đoạn mã sau chỉ minh họa miền. Repository và transaction được thiết kế ở phần tiếp theo, không có thao tác gửi thông điệp trong aggregate:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

interface DomainEvent {
    UUID eventId();
    UUID aggregateId();
    long aggregateVersion();
    Instant occurredAt();
}

record OrderConfirmed(
        UUID eventId,
        UUID aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        BigDecimal totalAmount,
        String currency
) implements DomainEvent {
    OrderConfirmed {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(aggregateId);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(totalAmount);
        Objects.requireNonNull(currency);
        if (aggregateVersion <= 0) throw new IllegalArgumentException("version");
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

// Aggregate root; đơn giá và dòng hàng đã được kiểm tra ở thao tác thêm dòng.
final class Order {
    private final UUID id;
    private final String currency;
    private final List<BigDecimal> lineTotals = new ArrayList<>();
    private final List<DomainEvent> pendingEvents = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private long version;

    // Repository phục hồi trạng thái và dữ liệu đã lưu mà không tạo event mới.
    Order(UUID id, String currency, OrderStatus loadedStatus,
          long loadedVersion, List<BigDecimal> persistedLineTotals) {
        this.id = Objects.requireNonNull(id);
        this.currency = Objects.requireNonNull(currency);
        this.status = Objects.requireNonNull(loadedStatus);
        if (loadedVersion < 0) throw new IllegalArgumentException("version");
        this.version = loadedVersion;
        for (BigDecimal amount : Objects.requireNonNull(persistedLineTotals)) {
            if (amount == null || amount.signum() < 0) {
                throw new IllegalArgumentException("Invalid persisted line");
            }
            lineTotals.add(amount);
        }
    }

    void addLineTotal(BigDecimal amount) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order is no longer editable");
        }
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Invalid line total");
        }
        lineTotals.add(amount);
        version++;
    }

    void confirm(UUID eventId, Instant occurredAt) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be confirmed");
        }
        if (lineTotals.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        BigDecimal total = lineTotals.stream()
            .reduce(BigDecimal.ZERO, BigDecimal::add);
        status = OrderStatus.CONFIRMED;
        version++;
        pendingEvents.add(new OrderConfirmed(
            eventId, id, version, occurredAt, total, currency));
    }

    UUID id() { return id; }
    OrderStatus status() { return status; }
    long version() { return version; }
    List<DomainEvent> pendingEvents() {
        return List.copyOf(pendingEvents);
    }
}
~~~

Đây là mô hình rút gọn: danh sách lineTotals chỉ thay cho OrderLine để tập trung vào **phát sinh sự kiện**. Trong ứng dụng thật, OrderLine cần danh tính/số lượng/giá được kiểm tra và repository phải khôi phục chúng đầy đủ. Constructor phục hồi dữ liệu không tăng version hoặc phát event. Version tăng trong bộ nhớ theo mỗi biến đổi; repository phải so sánh với **phiên bản gốc đã nạp** khi ghi và lưu **phiên bản cuối cùng của aggregate**, thay vì dùng phiên bản mới để so sánh trước cập nhật. Nếu một đơn vị công việc gồm nhiều biến đổi, các dòng dữ liệu cùng version cuối phải được ghi nguyên tử.

Khi Order.confirm() thất bại vì trạng thái không hợp lệ hoặc đơn rỗng, không tạo OrderConfirmed. Khi thành công, sự kiện mới nằm trong danh sách **pendingEvents** cho đến khi repository ghi xong. Application service có thể nạp root, gọi command, lưu state + các event phải công bố trong cùng transaction; nếu rollback, bỏ phiên làm việc chưa commit và nạp lại trạng thái nếu retry.

Trong ví dụ, UUID và Instant của event được truyền từ tầng điều phối để có thể kiểm soát tính lặp và kiểm thử. Không nên tự dùng đồng hồ hệ thống ở mọi nơi rồi giả định các bước của một command sẽ có thời điểm nhất quán. Khi nghiệp vụ cần occurredAt lấy từ DB lúc commit hoặc từ nguồn thời gian có thẩm quyền, hãy đưa quy tắc đó vào thiết kế repository.

**Lưu ý:** Không nên coi event vừa tạo như "đã được gửi đi". Root không gọi HTTP, message broker, email hay ghi thẳng database của aggregate khác. Chính transaction và cơ chế phát sau commit xử lý phần đó.

## 6. Domain event, integration event, audit log và event sourcing

Đây là bốn khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Mục đích chính | Ai sở hữu cấu trúc? | Có cần tồn tại lâu dài không? |
| --- | --- | --- | --- |
| **Domain event** | Diễn đạt sự thật vừa xảy ra trong mô hình miền | Bounded context/aggregate phát sinh | Không bắt buộc là nguồn sự thật để khôi phục trạng thái |
| **Integration event** | Thông báo dữ kiện ổn định cho hệ thống/ngữ cảnh khác | Hợp đồng tích hợp của producer | Cần đủ bền để chuyển và retry theo cam kết |
| **Audit log** | Truy vết ai làm gì, khi nào, quyết định nào | Chính sách kiểm toán/tuân thủ | Phụ thuộc retention và yêu cầu truy vết |
| **Event sourcing** | Dùng chuỗi event như nguồn sự thật để dựng lại trạng thái | Mô hình event stream của aggregate | Có: phải lưu và replay được theo thiết kế |

Một OrderConfirmed domain event có thể được ánh xạ thành SalesOrderConfirmedV1 để công bố. Không nhất thiết phơi bày mọi thuộc tính nội bộ của class OrderConfirmed; payload integration thường là một **hợp đồng ổn định** dành cho bên ngoài.

Nếu hệ thống chỉ lưu bảng orders hiện tại cùng một outbox chuyển thông điệp, đó **không phải event sourcing**. Nếu lưu thêm bảng lịch sử trạng thái để audit, cũng chưa đủ để gọi là event sourcing. Event sourcing đòi hỏi các event đã ghi là nguồn dựng lại state, có chính sách phiên bản, replay, tương thích schema và xử lý side effect khi tái dựng.

### Một thay đổi có thể sinh nhiều sự kiện, hoặc không cần công bố

Một command có thể tạo nhiều sự thật nghiệp vụ: InvoiceIssued và PaymentDueScheduled chẳng hạn, nếu đây là hai mốc độc lập được định nghĩa rõ. Ngược lại, một domain event chỉ phục vụ rule nội bộ và không có bên tiêu thụ ngoài thì không nhất thiết chuyển thành integration event.

Không buộc quan hệ "một UPDATE = một event" hoặc "một command = một event" trong mọi trường hợp. Quy tắc quyết định là **ý nghĩa của sự thật đã xảy ra**, không phải số câu SQL.

## 7. Ghi trạng thái và outbox trong cùng transaction PostgreSQL

Một rủi ro phổ biến là:

~~~text
UPDATE orders -> COMMIT thành công
Process crash trước khi publish OrderConfirmed
=> Database có đơn đã xác nhận, hệ thống khác không nhận được sự kiện.
~~~

Đổi thứ tự thành "publish trước, rồi COMMIT" cũng không giải quyết triệt để: có thể công bố OrderConfirmed rồi transaction rollback. **Transactional outbox** giảm khoảng hở này bằng cách lưu **trạng thái aggregate và ý định phát thông điệp** trong cùng transaction cục bộ.

Một lược đồ đơn giản:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    total_amount NUMERIC(19, 2) NOT NULL
        CHECK (total_amount >= 0),
    currency_code CHAR(3) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE sales.outbox_event (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, aggregate_id)
        REFERENCES sales.orders (tenant_id, order_id)
);

CREATE INDEX outbox_unpublished
    ON sales.outbox_event (created_at, event_id)
    WHERE published_at IS NULL;

CREATE INDEX outbox_aggregate_sequence
    ON sales.outbox_event (tenant_id, aggregate_id, aggregate_version);
~~~

Lược đồ này giả định Outbox chỉ lưu event của Order. Nếu một outbox dùng chung cho nhiều loại aggregate, FK tới một bảng orders sẽ không còn phù hợp; thay bằng hợp đồng định danh producer + aggregateType và quy tắc toàn vẹn riêng. Chỉ mục outbox_unpublished hỗ trợ lấy bản ghi chờ phát, không tự bảo đảm thứ tự toàn hệ thống.

### Giao dịch xác nhận Order

Giả sử application service đã nạp Order DRAFT version 4 với các dòng hàng hợp lệ, gọi confirm() và nhận version mới là 5. Trong repository, cần lưu trạng thái mới và event đã dựng cùng nhau:

~~~sql
BEGIN;

UPDATE sales.orders
SET status = 'CONFIRMED',
    total_amount = :verified_total_amount,
    version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
  AND :new_version > :expected_version
RETURNING version;

-- Chỉ tiếp tục nếu UPDATE trả đúng 1 hàng.
-- Nếu bằng 0: ROLLBACK, không insert outbox.
-- :new_version là version thực tế trả về.

INSERT INTO sales.outbox_event
    (event_id, tenant_id, aggregate_id, aggregate_version,
     event_type, schema_version, occurred_at, payload)
VALUES
    (:event_id, :tenant_id, :order_id, :new_version,
     'SalesOrderConfirmed', 1, :occurred_at,
     jsonb_build_object(
         'orderId', :order_id,
         'tenantId', :tenant_id,
         'totalAmount', :total_amount_text,
         'currency', :currency_code
     ));

COMMIT;
~~~

Trong ví dụ, :expected_version là phiên bản khi repository nạp Order; :new_version là phiên bản cuối do aggregate tạo, phải khớp phiên bản trên event. Giá trị :verified_total_amount và :total_amount_text được tạo từ **cùng kết quả đã tính và kiểm tra trong miền**, không lấy trực tiếp từ client. Nếu command thay đổi dòng hàng cùng lúc với confirm, các thay đổi đó phải được lưu trong cùng transaction. Ở ví dụ xác nhận đơn đã có dòng từ trước, version tăng đúng một lần (4 → 5). Khi nhiều hành vi trong một đơn vị công việc cùng tăng version, SQL vẫn ghi phiên bản cuối; các sự kiện công bố có thể mang những phiên bản khác nhau, và không phải mọi version nhất thiết có một integration event.

**Bảo đảm ở mức database:** hoặc cả Order và outbox record được commit, hoặc cả hai rollback. Điều này **không tự bảo đảm** broker đã nhận hay consumer đã xử lý event. Một tiến trình chuyển tiếp (outbox relay) còn phải đọc outbox và publish với retry.

### Vì sao "exactly once" dễ bị hiểu sai?

Relay có thể publish thành công rồi crash trước khi đánh dấu published_at. Khi khởi động lại, nó gửi lại **cùng eventId**; broker hoặc consumer có thể thấy hai bản sao. Outbox giải quyết vấn đề mất ý định phát do hai transaction rời rạc, nhưng thông thường cung cấp mô hình **ít nhất một lần** (*at-least-once*) khi phát, không phải tác động nghiệp vụ đúng một lần trên mọi hệ thống.

Consumer phải làm các tác động của mình **idempotent**, hoặc dùng giao dịch cục bộ kết hợp với bảng ghi nhận event đã xử lý.

## 8. Consumer: idempotency, thứ tự và quyền sở hữu

Giả sử SalesOrderConfirmed khiến Inventory bắt đầu xử lý giữ hàng. Inventory có quyền quyết định có giữ được hàng hay không, dựa trên số lượng tồn và chính sách riêng.

~~~mermaid
sequenceDiagram
    participant O as Sales / Order
    participant DB as Sales DB + Outbox
    participant B as Broker
    participant I as Inventory
    O->>DB: COMMIT Order CONFIRMED + event
    DB-->>O: Commit OK
    DB->>B: Publish SalesOrderConfirmed
    B->>I: Deliver eventId = E42
    I->>I: Dedup + đặt giữ trong transaction
    I-->>B: Ack sau commit
    B->>I: Redelivery eventId = E42
    I->>I: Đã xử lý E42, không giữ lại
~~~

Một bảng dedup cục bộ tại Inventory:

~~~sql
CREATE SCHEMA IF NOT EXISTS inventory;

CREATE TABLE inventory.processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Mô thức tiêu thụ trong **một transaction của Inventory**:

~~~text
BEGIN
  INSERT inventory.processed_event(consumer_name, event_id)
    ON CONFLICT DO NOTHING RETURNING event_id

  Nếu 0 hàng:
    COMMIT; ACK; kết thúc (đây là bản sao đã xử lý)

  Nếu 1 hàng:
    Đọc payload; kiểm chứng phiên bản/tenant/dữ liệu cần thiết
    Thực thi command Inventory phù hợp, bảo vệ tồn kho bằng transaction
    Ghi reservation hoặc kết quả từ chối và outbox Inventory
    COMMIT; ACK

Nếu bất kỳ thao tác nghiệp vụ nào lỗi:
  ROLLBACK cả dedup mark và thay đổi Inventory
  Retry hoặc đưa vào luồng xử lý lỗi theo chính sách
~~~

Chỉ đánh dấu processed_event **trong cùng transaction với tác động cục bộ**. Nếu đánh dấu trước rồi tác động sau ở giao dịch khác, crash sẽ khiến sự kiện bị coi đã xử lý nhưng Inventory chưa thay đổi. Tương tự, chỉ ACK broker sau khi kết quả cục bộ bền vững.

Một command Inventory thất bại vì **không đủ hàng** là kết quả nghiệp vụ, không nhất thiết là lỗi hệ thống cần retry vô hạn. Inventory có thể ghi kết quả StockReservationRejected và công bố sự kiện của chính mình; Sales quyết định tiếp theo có hủy/giữ chờ Order theo chính sách.

### Thứ tự xử lý

OrderConfirmed có thể được phát trước OrderCancelled, nhưng hai message đến consumer theo thứ tự ngược vì retry, nhiều partition hoặc nhiều relay. Nếu trạng thái của bên nhận phụ thuộc thứ tự, dùng aggregateVersion/sequence để phát hiện sự kiện cũ, lỗ hổng hoặc bản sao và xử lý theo hợp đồng.

- **eventId** phát hiện trùng một lần xảy ra.
- **aggregateVersion** biểu diễn thứ tự thay đổi **của một aggregate** khi được gán nhất quán.
- **correlationId** nối các bước của một workflow, không phải số thứ tự.
- Không suy ra thứ tự tuyệt đối của tất cả các aggregate từ timestamp hoặc thứ tự bản ghi trên broker.

Nếu relay xử lý song song các hàng outbox, index theo created_at không thể một mình bảo đảm OrderConfirmed luôn được phát trước OrderCancelled. Có thể partition message theo aggregateId và giữ thứ tự, hoặc để consumer quản lý version và tạm chờ sự kiện còn thiếu.

## 9. Phiên bản hợp đồng và tiến hóa schema sự kiện

Khi sự kiện ra khỏi một bounded context, nó trở thành hợp đồng được nhiều consumer sử dụng. Thay đổi tùy tiện field có thể làm hệ thống bên ngoài ngừng xử lý.

Một integration event minh họa:

~~~json
{
  "eventId": "e3563fa7-3ab1-4e08-88a1-3f3a884b47aa",
  "eventType": "SalesOrderConfirmed",
  "schemaVersion": 1,
  "producer": "sales",
  "tenantId": "fe8175f8-cc11-4fbe-8536-100f4b613c04",
  "aggregateId": "b188c0f3-83de-49be-8f84-fcdbbfbdc168",
  "aggregateVersion": 5,
  "occurredAt": "2026-11-22T02:00:00Z",
  "correlationId": "f1d3a6a1-9644-4c64-a86c-ae2a4d13b6a3",
  "payload": {
    "orderId": "b188c0f3-83de-49be-8f84-fcdbbfbdc168",
    "totalAmount": "23000000.00",
    "currency": "VND"
  }
}
~~~

Các câu hỏi cần thống nhất:

1. **Tên và ý nghĩa event có ổn định không?** SalesOrderConfirmed không nên lúc đầu nghĩa là khách đã xác nhận, về sau âm thầm đổi thành Payment đã thu tiền.
2. **Field mới có tùy chọn không?** Thêm một trường optional với mặc định có thể tương thích hơn việc đổi tên/xóa trường bắt buộc.
3. **Có đổi đơn vị hoặc cách làm tròn không?** totalAmount là decimal và currency được chỉ rõ; không chuyển từ đơn vị đồng sang đơn vị nghìn đồng mà giữ nguyên tên field.
4. **Consumer có bỏ qua field chưa biết không?** Hợp đồng cần quy tắc rõ; không giả định mọi thư viện serializer đều xử lý như nhau.
5. **Có cần event type/version mới không?** Một thay đổi ngữ nghĩa không tương thích thường cần hợp đồng mới hoặc giai đoạn chuyển đổi.

Với sự kiện đã lưu lâu, cần có chiến lược schema registry, upcaster/adapter hoặc hỗ trợ nhiều version nếu có nhu cầu replay. Tránh để các consumer phụ thuộc trực tiếp vào class/entity nội bộ của producer, vì một refactor bảng không nên là thay đổi API công khai.

### Anti-corruption layer tại ranh giới

Một sự kiện CustomerRegistered trong Customer Management không nhất thiết có cùng nghĩa với BuyerActivated trong Sales. Bên nhận có thể dùng lớp chuyển đổi ngữ nghĩa để tạo mô hình phù hợp với mình thay vì copy nguyên object của bên phát. Các trường ID, trạng thái, thời gian hiệu lực và namespace cần được diễn giải theo hợp đồng, không chỉ theo tên giống nhau.

## 10. Dữ liệu sự kiện, lịch sử và quyền riêng tư

Khi chọn payload và thời gian lưu:

- Chỉ gửi dữ liệu cần thiết theo hợp đồng; có thể gửi ID hoặc tham chiếu tới dữ liệu theo quyền truy cập thay vì nhúng toàn bộ thông tin cá nhân.
- Đặt quyền đọc topic/queue và chính sách bảo vệ dữ liệu tương xứng với mức nhạy cảm của payload.
- Phân biệt **occurredAt** (thời điểm sự thật nghiệp vụ) với **recordedAt/created_at** (lúc hệ thống lưu) và **publishedAt** (lúc broker nhận); chúng có thể khác nhau.
- Tính đến xóa/ẩn danh theo quy định và nhu cầu kiểm toán. Event đã phân tán và tồn tại trong nhiều bản sao/backup có thể rất khó sửa sau này; giảm dữ liệu nhạy cảm ngay từ đầu là lựa chọn thiết kế tốt hơn.
- Không coi outbox là kho audit vĩnh viễn. Outbox thường là hàng đợi bền vững có chính sách dọn dẹp sau khi đã phát thành công và hết thời gian cần retry/đối soát.

**Nhất quán dữ liệu và đầy đủ lịch sử là hai yêu cầu khác nhau.** Outbox có thể bảo đảm ý định phát một sự kiện được ghi cùng giao dịch, nhưng không tự cho phép tái dựng tất cả trạng thái đã qua, cũng không thay thế audit về actor, lý do và nguồn quyết định.

Nếu cần lịch sử pháp lý, thiết kế audit trail với chủ thể, thời gian, yêu cầu thay đổi, mức bất biến/tamper evidence và thời hạn lưu phù hợp; không chỉ lưu một chuỗi JSON tùy ý rồi tuyên bố có kiểm toán.

## 11. Cùng một sự kiện, nhiều kiểu lưu trữ

Mô hình sự kiện miền không phụ thuộc một công nghệ cụ thể. Cần phân biệt **nguồn ghi có thẩm quyền** với **mô hình đọc/quan sát**.

| Lựa chọn | Cách biểu diễn | Điều cần kiểm chứng |
| --- | --- | --- |
| **Quan hệ** | Root state ở bảng giao dịch, outbox/đôi khi event log ở bảng riêng | ACID commit, khóa/phiên bản, chỉ mục unpublished, retention |
| **Document** | Document chứa root và pending message/outbox theo cơ chế database, hoặc event collection | Phạm vi thao tác nguyên tử, giới hạn document, chính sách tránh nhúng lịch sử vô hạn |
| **Đồ thị** | Sự kiện/quan hệ kết nối đối tượng khi cần truy vấn nguyên nhân và chuỗi ảnh hưởng | Edge không tự chứng minh thứ tự, thẩm quyền hoặc transaction của nghiệp vụ |
| **Phân tích/cột** | FactBusinessEvent với eventType, thời điểm, aggregateId, dimension | Thích hợp thống kê chuyển đổi/thời gian; thường là bản sao có độ trễ |

Ví dụ: SalesOrderConfirmed được tiêu thụ để xây bảng phân tích số đơn xác nhận theo ngày. Kho phân tích có thể dùng cột event_id để loại bản sao và date dimension để tổng hợp, nhưng **không dùng số liệu phân tích trễ làm nguồn quyết định một Order hiện có được confirm lần nữa hay không**.

Trên database quan hệ, bảng outbox phục vụ **vận chuyển**; bảng audit phục vụ **truy vết**; bảng order là **trạng thái hiện tại**. Nếu chọn event sourcing, stream sự kiện là nguồn dựng trạng thái và cần mô hình version/replay riêng. Các mục đích khác nhau không nên bị ép dùng chung một bảng chỉ vì đều có chữ "event".

## 12. Kiểm thử sự kiện theo kết quả nghiệp vụ và lỗi hệ thống

Một bộ kiểm thử có giá trị cần bao phủ cả **lúc không được phát sự kiện** và **lúc thông điệp bị gửi lại**:

| Tình huống | Kỳ vọng |
| --- | --- |
| ConfirmOrder trên DRAFT có dòng hợp lệ | Order thành CONFIRMED; lưu OrderConfirmed cùng transaction |
| ConfirmOrder trên DRAFT rỗng | Bị từ chối; không có OrderConfirmed đã commit |
| ConfirmOrder lần nữa trên CONFIRMED | Không tạo sự kiện mới; trả kết quả theo chính sách idempotency |
| Hai request confirm cùng version | Tối đa một transition commit; request còn lại nhận xung đột/kết quả đã xử lý |
| Lưu Order thành công nhưng INSERT outbox thất bại | Rollback cả thay đổi Order |
| Commit xong, relay crash trước publish | Outbox vẫn còn để retry |
| Publish xong, relay crash trước đánh dấu đã gửi | Có thể gửi lại cùng eventId; consumer không áp dụng hai lần |
| Consumer nhận event version 7 rồi version 6 | Không ghi đè trạng thái mới bằng dữ liệu cũ; xử lý theo sequence policy |
| Event thiếu trường bắt buộc | Phản hồi lỗi hợp đồng, cô lập hoặc đưa vào luồng xử lý không hợp lệ |
| Inventory không đủ hàng | Ghi kết quả từ chối có thẩm quyền; không tự coi OrderConfirmed là StockReserved |

Khi chạy test đồng thời, không chỉ kiểm tra HTTP status. Hãy kiểm tra **trạng thái cuối của database**, số lần tác động nghiệp vụ và số outbox/eventId thực sự được commit.

## 13. Bài tập: giao hàng và thông báo khách

**Bối cảnh:** Một hệ thống vận chuyển quản lý Shipment với vòng đời CREATED → PACKED → DISPATCHED → DELIVERED; có thể chuyển sang FAILED_DELIVERY và RETRYING theo quy tắc. Mỗi Shipment có shipmentId và orderId tham chiếu đến Order thuộc Sales. Một khách có thể nhận nhiều thông báo khi một thông điệp được broker phát lại, vì vậy cần thiết kế idempotency.

### Yêu cầu

1. Xác định các domain event đáng phát sinh, phân biệt với command. Đặt tên theo sự thật nghiệp vụ.
2. Chọn root có quyền quyết định Shipment đã giao thành công; Order có được sửa trực tiếp trạng thái Shipment không?
3. Đề xuất payload tối thiểu cho ShipmentDelivered, gồm định danh, thời gian, phiên bản và dữ liệu cần cho người tiêu thụ. Có nên nhúng địa chỉ nhận đầy đủ vào thông điệp không?
4. Mô tả cách commit trạng thái DELIVERED và ý định gửi thông báo trong cùng transaction.
5. Nếu một ShipmentDelivered được gửi hai lần, một lần đến trễ sau ShipmentDeliveryCorrected, Notification và Analytics phải xử lý thế nào?
6. Nếu một lệnh MarkDelivered thất bại vì Shipment chưa DISPATCHED, có phát ShipmentDelivered không? Giải thích.

### Hướng giải tham khảo

- Command gồm PackShipment, DispatchShipment, MarkDelivered, ReportDeliveryFailure; các sự kiện tương ứng khi thành công có thể là ShipmentPacked, ShipmentDispatched, ShipmentDelivered, ShipmentDeliveryFailed. Không dùng DispatchShipment làm tên của một sự kiện đã xảy ra.
- Shipment là aggregate root trong Logistics; orderId chỉ là tham chiếu sang Sales. Logistics kiểm tra trạng thái và bằng chứng giao hàng. Sales có thể nhận event để cập nhật read model hoặc điều phối nghiệp vụ sau giao, nhưng không tự sửa bảng Shipment.
- Payload có eventId, aggregateId = shipmentId, orderId, tenantId khi cần, aggregateVersion, occurredAt, deliveryResultCode, schemaVersion và correlationId. Hạn chế dữ liệu cá nhân; Notification có thể tra địa chỉ liên hệ qua nguồn có thẩm quyền hoặc nhận token/ID theo hợp đồng.
- Transaction cập nhật Shipment sang DELIVERED kèm phiên bản và insert outbox; relay gửi sau commit, consumer dedup theo eventId. Nếu cùng command được retry thì không phát thêm sự kiện mới cho một chuyển trạng thái đã hoàn tất.
- Khi ShipmentDeliveryCorrected đến sau hoặc trước ShipmentDelivered, consumer phải dùng version/chuỗi sự kiện và chính sách sửa sai. Không mặc định "gửi lại event cũ" là một lần giao hàng mới; Analytics loại bản sao dựa eventId và có mô hình tính lại số liệu khi cần correction.
- Nếu trạng thái trước không phù hợp, command thất bại và không có ShipmentDelivered đã commit. Một event giả sẽ đánh lừa Notification, báo cáo và quy trình hậu mãi.

### Mở rộng

Hãy giải thích vì sao một bảng audit gồm actor, fromStatus, toStatus có thể cần tồn tại ngay cả khi hệ thống đã có outbox ShipmentDelivered. Hai bảng có thể liên quan nhưng **mục tiêu, quyền truy cập và thời hạn lưu khác nhau**.

## 14. Checklist rà soát thiết kế domain event

- Tên event có diễn đạt một **sự thật đã xảy ra** bằng ngôn ngữ nghiệp vụ không?
- Aggregate nào có thẩm quyền tạo event và bất biến nào được bảo vệ trước khi tạo?
- Khi transaction rollback, có chắc không có integration event giả được công bố không?
- eventId, aggregateId, requestId, messageId, version và correlationId có vai trò/phạm vi riêng được định nghĩa không?
- Payload có loại tiền, đơn vị, timestamp, phiên bản schema và dữ liệu tối thiểu cần thiết không?
- Đã phân biệt domain event nội bộ với hợp đồng integration và với audit/event sourcing chưa?
- Publisher có retry an toàn và consumer có dedup/idempotency trong cùng transaction với tác động cục bộ không?
- Nếu sự kiện đến trễ hoặc không theo thứ tự, hệ thống có cách xác định trạng thái hợp lệ không?
- Đường ghi và quyền sở hữu của aggregate khác có được tôn trọng khi xử lý event không?
- Mô hình quan hệ/document/đồ thị/phân tích có đáp ứng truy vấn, retention, bảo mật và khả năng tiến hóa không?

**Kết luận:** Sự kiện miền giúp mô hình ghi lại **ý nghĩa của thay đổi**, không chỉ việc một cột đã được cập nhật. Aggregate quyết định sự thật nào có thể xảy ra; transaction biến thay đổi thành kết quả bền vững; integration event truyền sự thật qua ranh giới; consumer tự bảo vệ tính nhất quán và idempotency của mình. Thiết kế theo cách đó giúp cơ sở dữ liệu, ứng dụng và hệ thống tích hợp diễn đạt cùng một nghiệp vụ rõ ràng, có thể kiểm chứng và thay đổi có kiểm soát.
