# Đồng nhất lớp Java, bảng lưu trữ và DTO thành một mô hình duy nhất

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận ra **anti-pattern một mô hình cho mọi tầng** khi một class Java đồng thời là đối tượng miền, entity ORM, request/response DTO và payload tích hợp.
- Giải thích vì sao **cùng một đối tượng nghiệp vụ** không có nghĩa các biểu diễn Java, quan hệ lưu trữ và dữ liệu trao đổi có cùng **grain, vòng đời, quyền ghi hoặc hợp đồng tương thích**.
- Phân tích lỗi về **bất biến, mass assignment, rò rỉ dữ liệu, lazy loading, N+1, vòng lặp JSON, transaction, NULL, tiền tệ, thời gian và thay đổi schema**.
- Thiết kế lại trách nhiệm của **aggregate/domain model, persistence model, command/query DTO, integration event và analytical fact** mà không tạo các lớp trung gian vô nghĩa.
- Viết minh họa Java 17, PostgreSQL và mapper tách biệt; giữ định danh, tenant, số tiền và optimistic version đúng cách.
- Xây quy trình chuyển đổi từng bước cho hệ thống đang dùng entity làm API, có bảo đảm backward compatibility và không cần đập bỏ toàn bộ code.
- Đánh giá ngoại lệ: khi một CRUD đơn giản **có thể dùng ít lớp hơn**, và khi bắt buộc tách vì rủi ro hoặc khác biệt ngữ nghĩa.
- Kiểm thử được các ranh giới bằng test nghiệp vụ, API security, hợp đồng, transaction, concurrent update, migration và báo cáo.

Module **DATABASE_DATA_MODELING** rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng: thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục và lược đồ vật lý, đồng thời so sánh cách lưu quan hệ, document, đồ thị và dữ liệu phân tích. Trong chương **Lỗi thường gặp**, bài này tập trung vào một sai lầm có sức lan rộng: **biến một class Java thành cấu trúc chuẩn duy nhất rồi ép database, HTTP và message trao đổi đi theo nó**.

Điều này không đồng nghĩa với lời khuyên "mọi nơi luôn phải có năm lớp giống nhau". Cần tách khi **trách nhiệm và ngữ nghĩa khác nhau**; ngược lại, hệ thống CRUD rất đơn giản có thể giữ một số biểu diễn gần nhau. Vấn đề nằm ở **việc vô tình dùng chung quyền sở hữu, vòng đời và hợp đồng**, chứ không phải tên một annotation hay số lượng class.

## 1. Tình huống: một class Order được dùng cho mọi việc

Giả sử Sales quản lý đơn hàng. Theo yêu cầu nghiệp vụ minh họa:

1. Mỗi Order thuộc đúng một tenant; Order có nhiều OrderLine.
2. Mỗi dòng có SKU, số lượng dương và **đơn giá VND chốt tại lúc đặt**.
3. Order đang DRAFT có thể thêm dòng. Order đã CONFIRMED không được sửa dòng qua lệnh thông thường.
4. Tổng tiền là tổng quantity × unitPriceVnd của tất cả dòng hợp lệ.
5. Client có thể gửi lệnh tạo và xác nhận đơn, nhưng **không tự gán trạng thái, tổng tiền, tenant hay quyền**.
6. API hiển thị đơn cho chủ sở hữu; sự kiện OrderConfirmed cho Inventory/Notification chỉ nên công bố thông tin các consumer cần.

Một cách làm tưởng nhanh:

~~~java
// VÍ DỤ SAI: minh họa anti-pattern, không sao chép vào production.
@Entity
@Table(name = "orders")
public class Order {
    @Id
    public UUID id;

    public UUID tenantId;
    public UUID customerId;
    public String status;
    public long totalVnd;
    public String customerPhone;
    public String internalRiskNote;
    public long version;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    public List<OrderLine> lines;
}

// VÍ DỤ SAI: framework nhận toàn bộ entity từ JSON và trả lại entity.
@PostMapping("/orders")
public Order create(@RequestBody Order incoming) {
    return orderRepository.save(incoming);
}
~~~

Đoạn trên dùng annotation JPA/Spring nhằm thể hiện cấu trúc lỗi, **không phải một ứng dụng đầy đủ có thể chạy ngay**. Những lỗi nổi bật:

- Client có thể thử gửi **status=CONFIRMED**, **totalVnd tùy ý**, **tenantId khác** hoặc **internalRiskNote**; nếu binding và save không chặn, dữ liệu/đặc quyền bị vượt qua. Đây là **mass assignment / over-posting**.
- Không có hành vi confirm() bảo vệ quy tắc đơn rỗng, trạng thái hay giá đã chốt. **Public field** cho phép sửa từ mọi nơi.
- Khi trả entity ra HTTP, **customerPhone** và **internalRiskNote** có thể lọt vào JSON hoặc log nếu không chặn rõ ràng.
- Truy cập **lines** ngoài transaction có thể gặp LazyInitializationException, hoặc sinh **N+1 query** khi hiển thị danh sách nhiều Order.
- Quan hệ hai chiều Order ↔ OrderLine có thể gây **vòng lặp serialization** khi JSON mapper đi qua cả hai phía.
- Đổi tên trường database hoặc refactor quan hệ JPA có nguy cơ thay luôn cấu trúc response, dù người dùng API không hề yêu cầu thay đổi.
- Entity có thể ở trạng thái **detached**, nhưng tầng API vẫn tưởng nó là "đối tượng nghiệp vụ sống" có thể sửa và save.

Trong Spring/JPA, tồn tại nhiều cơ chế để giới hạn field, quyền và serialization; việc dùng annotation đúng có thể giảm một số rủi ro. Nhưng **không có annotation đơn lẻ nào tự giải quyết toàn bộ việc tách ngữ nghĩa và vòng đời**.

## 2. Dấu hiệu nhận diện anti-pattern

| Dấu hiệu trong codebase | Vì sao đáng lo | Câu hỏi cần hỏi |
| --- | --- | --- |
| Controller nhận **@RequestBody OrderEntity** | Mở quyền gán những field persistence không thuộc use case | Client được phép sửa trường nào? |
| Controller trả trực tiếp **List<OrderEntity>** | Response phụ thuộc mapping ORM và graph | Có lộ dữ liệu, N+1, lazy exception không? |
| Domain service chỉ gọi **setStatus("CONFIRMED")** | Bất biến bị thay bằng setter tùy ý | Ai kiểm tra trạng thái trước và dòng hàng? |
| Entity chứa hàng chục field report/read-only | Trộn nhu cầu đọc với quyết định nghiệp vụ | Fact/KPI có cùng grain với aggregate không? |
| Thêm cột SQL là thêm ngay field JSON API | Storage refactor làm biến động contract | Consumer có cần biết field ấy không? |
| Nhận event từ đối tác rồi **save() entity** | Bên ngoài vô tình có quyền ghi mô hình nội bộ | Ai sở hữu trạng thái? |
| Validation bằng **@NotNull** trên entity cho mọi trường | Trộn rule theo use case với constraint tồn tại | CREATE, UPDATE và REST response có cùng điều kiện không? |
| Dùng **id DB tự tăng** cho mọi event/public API | Lẫn surrogate key với business/external ID | ID có ổn định qua chuyển kho/nạp lại không? |
| Lưu **passwordHash/PII** cùng entity trả JSON | Lộ dữ liệu khi mở endpoint hoặc thêm field | Có kiểm soát nội dung công bố theo vai trò không? |
| Vì API cần field mới nên sửa trực tiếp bảng OLTP | Thiết kế storage theo giao diện thay vì bất biến/query | Có thể tạo read projection/DTO riêng không? |

**Không phải cứ thấy @Entity trong domain package là một kết luận sai chắc chắn.** Ở dự án nhỏ có thể tồn tại kiến trúc đơn giản vẫn an toàn. Cần xem **hành vi thực, quyền cập nhật, hợp đồng public, vòng đời và kiểm thử** trước khi quyết định tách.

## 3. Vì sao cùng tên Order nhưng không cùng mô hình?

Phân biệt ít nhất năm vai trò:

| Biểu diễn | Câu hỏi nó trả lời | Grain / vòng đời | Ai có quyền thay đổi? |
| --- | --- | --- | --- |
| **Domain Order** | Khi nào có thể thêm dòng, xác nhận, hủy? | Một Order aggregate, vòng đời nghiệp vụ | Command trên root theo bất biến |
| **Persistence model** | Ghi và đọc bằng bảng/khóa/transaction nào? | Một order_header và nhiều order_line | Repository và migration có kiểm soát |
| **Command DTO** | Caller muốn làm hành vi nào, được nhập field gì? | Một yêu cầu HTTP/API | Caller được xác thực và phân quyền |
| **Response DTO** | Caller được nhìn thấy dữ liệu nào, dạng gì? | Một snapshot phục vụ use case đọc | Producer API quyết định hợp đồng |
| **Integration event** | Sự thật đã commit nào cần thông báo? | Một occurrence có eventId, schemaVersion | Producer có thẩm quyền công bố |
| **Analytical fact** | Một phép đo được đếm/tổng theo grain gì? | Ví dụ một dòng bán đã thanh toán | ETL/BI có quy tắc nguồn/metric |

Một Order có **ba dòng hàng** không có nghĩa một API response cần ba SQL row riêng; nó có thể trả một JSON chứa lines[]. Ngược lại, một bảng fact tại grain **OrderLine** phải có ba hàng để SUM theo SKU, không thể dùng một row Order aggregate rồi giả định đã có grain theo SKU.

**Không có ánh xạ một-một bắt buộc:**

~~~mermaid
flowchart TB
    REQUEST["ConfirmOrderRequest<br/>lệnh của client"]
    APP["Application service<br/>auth, transaction"]
    DOMAIN["Domain Order<br/>hành vi + bất biến"]
    ROWS[("Storage<br/>order_header + order_line")]
    VIEW["OrderView DTO<br/>field được công bố"]
    OUTBOX[("Outbox event<br/>OrderConfirmedV1")]
    CONSUMER["Inventory / Notification"]
    FACT["FactPaidOrderLine<br/>grain khác"]
    REQUEST --> APP
    APP --> DOMAIN
    DOMAIN <-->|"Repository mapping"| ROWS
    APP --> VIEW
    APP --> OUTBOX
    OUTBOX --> CONSUMER
    ROWS --> FACT
~~~

Mô hình miền và storage thường đi cùng nhau trong **cùng một ứng dụng**, nhưng trao đổi qua boundary nên có hợp đồng độc lập. Đường đọc có thể map từ query SQL sang OrderView mà không phục hồi aggregate nếu không đổi state.

## 4. Bẫy thứ nhất: mất bất biến và quyền quyết định

Xét request giả:

~~~json
{
  "id": "cd6755f2-57cc-48a1-a68a-ef822b629a09",
  "tenantId": "a6389ce1-2bfd-4dbc-9e9c-abdc21ed1509",
  "customerId": "4d9f2611-98c5-4dca-8962-1c45f2b36cb7",
  "status": "CONFIRMED",
  "totalVnd": 100,
  "internalRiskNote": "approved"
}
~~~

Nếu controller deserialize request thẳng thành entity rồi save(), nó có thể vô tình:

- Cho caller **đổi tenantId** nhằm truy cập dữ liệu khác tenant, nếu repository/query không chặn.
- Cho caller **đổi customerId** sau khi Order đã tồn tại.
- Ghi **status=CONFIRMED** mà chưa có OrderLine.
- Ghi tổng tiền **100 VND** không khớp các dòng đã chốt.
- Cho sửa **internalRiskNote** dù field này chỉ dành cho quy trình kiểm soát nội bộ.

Đây là lỗi **quyền truy cập và bất biến**, không giải quyết chỉ bằng việc đổi một trường từ public sang private nếu vẫn có setter và mapper tự động copy toàn bộ.

### Command phải có trường được phép, không phải tất cả cột

Thay vì nhận một OrderEntity, API có thể có:

- **CreateOrderRequest:** product/SKU và quantity mong muốn; không nhận status và total do client tự đặt.
- **AddOrderLineRequest:** SKU/quantity, optional giá tham chiếu nếu nghiệp vụ cho phép; giá chốt lấy từ nguồn có thẩm quyền và kiểm tra trước khi ghi.
- **ConfirmOrderRequest:** idempotencyKey/expectedVersion nếu hợp đồng cần; không nhận totalVnd hoặc trường trạng thái tự do.
- **OrderView:** orderId, status, money breakdown và các dòng được phép hiển thị, theo vai trò.

Ứng dụng xác thực actor và tenant từ **ngữ cảnh bảo mật đáng tin cậy**, không tin mỗi tenantId gửi trong body. Domain kiểm tra quy tắc; storage bảo vệ transaction/concurrent writes. **DTO validation là lớp lọc đầu vào, không thay thế domain rule**.

## 5. Bẫy thứ hai: ORM graph trở thành hợp đồng HTTP

Trong JPA/Hibernate, các quan hệ có thể được nạp **lazy** hoặc **eager** tùy mapping. Nếu JSON serializer được phép đi qua chúng, hình dạng API tùy thuộc trạng thái persistence context:

~~~text
GET /orders?status=CONFIRMED
  -> SELECT orders ...                 (1 query)
  -> serializer đọc order.lines        (có thể N query)
  -> serializer đọc line.product       (có thể thêm query)
  -> line.order trỏ ngược order        (có thể vòng lặp)
~~~

**N+1** là tình huống query ban đầu lấy N Order, sau đó N (hoặc nhiều hơn) query bổ sung để tải quan hệ từng Order. Vấn đề không phải JPA luôn thực hiện N+1, mà là việc **để serializer tự quyết định dữ liệu cần tải** khiến hiệu năng và quyền truy cập khó kiểm soát.

Những cách như @JsonIgnore, @JsonManagedReference/@JsonBackReference hoặc cấu hình Hibernate module có thể giải quyết một biểu hiện cụ thể, nhưng vẫn để **response contract bị buộc vào graph ORM**. Khi thay fetch strategy vì hiệu năng database, API có thể thay dữ liệu mà người tiêu thụ nhìn thấy.

### Thiết kế đường đọc có chủ đích

Một repository có thể cung cấp:

- **loadForCommand(tenantId, orderId):** phục hồi aggregate cùng dòng cần để kiểm tra bất biến.
- **findOrderSummary(tenantId, orderId):** query projection theo các field cần hiển thị.
- **listOrders(tenantId, pageSize, cursor):** trả list summary không kéo toàn bộ lines hoặc thông tin khách hàng.
- **findOrderLines(tenantId, orderId):** phân trang lines theo use case khi cần.

Như vậy, **truy vấn được chọn bởi use case**, không bởi vòng lặp của serializer. Có thể dùng JDBC, JPQL projection, native SQL, Spring Data interface projection hoặc công cụ khác; mục tiêu là rõ **truy vấn, hợp đồng và quyền**.

## 6. Bẫy thứ ba: đổi bảng làm vỡ API, đổi API làm méo bảng

Một thời điểm doanh nghiệp muốn chuyển từ một bảng **order** sang **order_header + order_line**, hoặc thêm bảng lịch sử/partition để tối ưu. Nếu response JSON chỉ là serialization entity, việc tách bảng và thay relation mapping có thể:

1. Đổi field hoặc đường dẫn JSON không chủ ý.
2. Gây lazy exception hoặc N+1 khi tải line.
3. Đưa cột kỹ thuật như row_version, deleted_at ra ngoài.
4. Buộc nhiều client nâng cấp cùng lúc với migration database.
5. Ngăn database team thay cấu trúc nội bộ vì sợ phá API.

Chiều ngược lại cũng nguy hiểm: chỉ vì web cần trường "tên khách hàng", nhóm phát triển thêm customer_name vào order_header và cho mọi command cập nhật nó, dù giá trị có thể được lấy từ một read model và tên khách thay đổi theo quy tắc khác.

**Quy tắc:** schema persistence được quyết định theo **bất biến, transaction, dữ liệu và truy vấn**; DTO được quyết định theo **use case và hợp đồng**. Mỗi thay đổi phải có mapping và compatibility plan, không sao chép field tự động rồi gọi là đồng bộ.

## 7. Những chi tiết giống tên nhưng khác ý nghĩa

Nhiều lỗi của mô hình dùng chung không xuất hiện ngay ở CRUD, mà chỉ lộ khi thay đổi nghiệp vụ, nhiều tenant hoặc hệ thống tích hợp.

| Chi tiết | Trong domain | Trong storage | Trong DTO/event |
| --- | --- | --- | --- |
| **Danh tính** | OrderId ổn định trong một phạm vi | Có thể dùng composite PK/UUID/surrogate key | Public ID và namespace do contract định nghĩa |
| **Tenant** | Ranh giới quyền sở hữu | Có trong khóa, FK, index, Row Level Security nếu áp dụng | Không tự biến field client gửi thành quyền |
| **Version** | Giữ nguyên trạng thái đã thấy để chống ghi cũ | row_version/optimistic locking | ETag/expectedVersion nếu use case cần; event schemaVersion **khác** |
| **Money** | Đơn vị, currency, bất biến và phép tính chính xác | BIGINT đơn vị nhỏ nhất hoặc NUMERIC theo chính sách | Có thể là chuỗi decimal để tránh mất precision trên client |
| **Timestamp** | confirmedAt là sự kiện nghiệp vụ | TIMESTAMPTZ lưu Instant theo chính sách | ISO 8601 có offset, không lấy receivedAt làm occurredAt |
| **NULL** | Có thể là absent/unknown/not applicable | NULL có nghĩa theo constraint | Request missing và JSON null có thể là **hai ý định khác nhau** |
| **Status** | State machine và command hợp lệ | Cột/constraint bảo vệ dữ liệu | Mã trạng thái công khai có version, không là setter |
| **Thông tin nhạy cảm** | Dữ liệu được sở hữu/kiểm soát | Có thể mã hóa, hạn chế truy cập, retention | Chỉ công bố trường đúng quyền/mục đích |

### 7.1. ID public không đồng nhất khóa chính vật lý

Một bảng có thể dùng BIGINT identity để tăng hiệu quả lưu/truy vấn, trong khi public API dùng UUID/ULID hoặc business ID ổn định. Nếu chuyển dữ liệu sang kho khác, surrogate key có thể thay; consumer không nên bị ràng buộc vào nó. Mỗi ID phải nêu phạm vi duy nhất: toàn hệ thống, trong tenant hay trong source.

### 7.2. Tiền không nên là double tiện tay

100.000 VND ở miền có thể được lưu là **long đơn vị đồng**, còn API dùng chuỗi "100000". Nếu nhiều currency, phải dùng amount+currency và quy tắc scale/làm tròn; SUM hai currency không thể được xem như một số đo duy nhất. Một field double được ORM lưu được không có nghĩa nó phù hợp với kế toán.

### 7.3. Tri-state khi PATCH

Với cập nhật thông tin giao hàng:

~~~json
{}
~~~

có thể nghĩa là **không thay đổi số điện thoại**; còn:

~~~json
{ "phone": null }
~~~

có thể nghĩa là **xóa số điện thoại**, nếu nghiệp vụ cho phép. Trong khi đó:

~~~json
{ "phone": "" }
~~~

có thể là một giá trị không hợp lệ. Nếu bind tất cả vào entity có phone nullable rồi gọi save(), nhiều mapper sẽ làm mất sự phân biệt **không gửi / gửi NULL / gửi rỗng**. Cần command/patch DTO thể hiện tri-state rõ (ví dụ present flag, JsonNullable hoặc JSON Patch theo hợp đồng) và domain policy quyết định thao tác.

### 7.4. Trường lưu cache không phải sự thật tự do

Một cột total_vnd tồn tại vì hiệu năng đọc có thể là **giá trị dẫn xuất**. Nếu domain coi total là biến có setter và client được gán, một transaction có thể tạo total không bằng tổng dòng. Cần quy tắc nguồn, cách tính và đối soát, không chỉ annotation @Column.

## 8. Một mô hình miền Java độc lập, có hành vi

Ví dụ Java 17 sau là **minh họa miền rút gọn**, không phụ thuộc JPA, HTTP hay message broker. Thời điểm và ID được application cấp sau khi xác thực; có kiểm tra tràn số. Nghiệp vụ thật có thể cần giá theo bảng giá/khuyến mại, thuế và nhiều tiền tệ.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

record OrderId(UUID value) {
    OrderId { Objects.requireNonNull(value); }
}

record OrderLine(int lineNo, UUID skuId, int quantity, long unitPriceVnd) {
    OrderLine {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    long amountVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

record OrderConfirmed(UUID eventId, OrderId orderId, long orderVersion,
                      Instant occurredAt, long totalVnd) {
    OrderConfirmed {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(occurredAt);
    }
}

final class SalesOrder {
    private final OrderId id;
    private final UUID customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;
    private long version;

    private SalesOrder(OrderId id, UUID customerId,
                       OrderStatus status, long version) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
        this.status = Objects.requireNonNull(status);
        if (version < 0) throw new IllegalArgumentException("version");
        this.version = version;
    }

    static SalesOrder create(OrderId id, UUID customerId) {
        return new SalesOrder(id, customerId, OrderStatus.DRAFT, 0);
    }

    // Chỉ repository được dùng theo đường phục hồi có kiểm soát.
    static SalesOrder restore(OrderId id, UUID customerId,
                              OrderStatus status, long version,
                              List<OrderLine> storedLines) {
        var order = new SalesOrder(id, customerId, status, version);
        for (var line : List.copyOf(storedLines)) {
            Objects.requireNonNull(line);
            if (order.lines.stream()
                    .anyMatch(x -> x.lineNo() == line.lineNo())) {
                throw new IllegalArgumentException("Duplicate line");
            }
            order.lines.add(line); // phục hồi, không gọi command
        }
        if (status == OrderStatus.CONFIRMED && order.lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid persisted order");
        }
        order.totalVnd(); // phát hiện tràn số trong dữ liệu đã lưu
        return order;
    }

    void addLine(OrderLine line) {
        requireDraft();
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo())) {
            throw new IllegalArgumentException("Duplicate line");
        }
        Math.addExact(totalVnd(), line.amountVnd()); // kiểm tra trước mutate
        lines.add(line);
        version++;
    }

    OrderConfirmed confirm(UUID eventId, Instant when) {
        requireDraft();
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(when);
        if (lines.isEmpty()) {
            throw new IllegalStateException("Empty order");
        }
        long total = totalVnd();
        status = OrderStatus.CONFIRMED;
        version++;
        return new OrderConfirmed(eventId, id, version, when, total);
    }

    long totalVnd() {
        long sum = 0;
        for (var line : lines) {
            sum = Math.addExact(sum, line.amountVnd());
        }
        return sum;
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    OrderId id() { return id; }
    UUID customerId() { return customerId; }
    OrderStatus status() { return status; }
    long version() { return version; }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Not editable");
        }
    }
}
~~~

**Giải thích ranh giới:**

- SalesOrder sở hữu chuyển trạng thái; API không có setter status.
- OrderLine có giá snapshot; đổi giá Catalog hôm sau không tự làm Order cũ đổi tổng.
- totalVnd() tính từ dòng, không dùng giá trị JSON do client cung cấp.
- restore() là đường nạp từ storage, **không tái thực hiện addLine/confirm**, vì làm vậy có thể tăng version và phát sự kiện giả.
- confirm() trả một **domain event trong bộ nhớ**, chưa phải integration event đã được công bố. Nếu transaction lưu thất bại, sự thật chưa commit.
- Ví dụ chưa có tenant trong root vì chỉ minh họa invariants của Order. Application/repository **bắt buộc** gắn tenant lấy từ ngữ cảnh tin cậy trong mọi lệnh lưu và nạp.

Nếu Order có quá nhiều hành vi hoặc transaction dài, cần xem lại aggregate boundary. Không dùng lý do "tách DTO" để vô tình nhúng Inventory và Payment vào cùng SalesOrder.

## 9. Mô hình lưu trữ quan hệ được thiết kế theo grain và transaction

PostgreSQL có thể biểu diễn một Order aggregate bằng nhiều bảng:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    total_vnd BIGINT NOT NULL DEFAULT 0 CHECK (total_vnd >= 0),
    row_version BIGINT NOT NULL DEFAULT 0 CHECK (row_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header(tenant_id, order_id)
);

CREATE INDEX orders_by_customer
    ON sales.order_header (tenant_id, customer_id, created_at DESC);

CREATE TABLE sales.order_outbox (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header(tenant_id, order_id)
);

CREATE INDEX order_outbox_pending
    ON sales.order_outbox (created_at, event_id)
    WHERE published_at IS NULL;
~~~

**Grain** của order_header là một Order theo (tenantId, orderId). Grain của order_line là một dòng OrderLine theo (tenantId, orderId, lineNo). **Một aggregate nhiều hàng** là bình thường; JPA entity hoặc SQL row không định nghĩa một-một aggregate.

### Ràng buộc nào do database bảo vệ?

| Quy tắc | Cơ chế gợi ý | Giới hạn |
| --- | --- | --- |
| Order/line không trùng khóa | PK/UNIQUE | Không xác thực actor được quyền ghi |
| Line phải có Order | FK | Không bảo vệ trạng thái DRAFT/CONFIRMED |
| Quantity > 0, giá không âm | CHECK | Không biết chính sách giá Catalog |
| Chuyển trạng thái từ DRAFT | UPDATE có điều kiện + version | Cần mọi đường ghi tôn trọng giao thức |
| Tổng header bằng tổng dòng | Domain + transaction + đối soát hoặc trigger phù hợp | CHECK thường không kiểm tra tổng của các row con |
| Không tạo hai sự kiện cho một occurrence | Event ID và idempotency key | EventId riêng chưa đủ nếu tạo mới khi retry cùng lệnh |

Một request làm thay đổi OrderLine phải khóa/so sánh **row_version của Order root** để tránh trường hợp confirm dựa trên các dòng cũ, trong khi một worker khác đang sửa dòng. Nếu chỉ version header lúc confirm nhưng mọi script vẫn được sửa order_line độc lập, bất biến tổng/cố định dòng **không được bảo vệ hoàn toàn**.

### Cập nhật trạng thái và outbox nguyên tử

Giả sử repository đọc Order ở row_version=6, domain confirm ra trạng thái version=7:

~~~sql
BEGIN;

UPDATE sales.order_header
SET status = 'CONFIRMED',
    total_vnd = :verified_total_vnd,
    confirmed_at = :confirmed_at,
    row_version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND row_version = :original_version
  AND :new_version > :original_version
RETURNING row_version;

-- Nếu trả 0 hàng, ứng dụng phải ROLLBACK và xử lý conflict.
-- verified_total_vnd lấy từ các dòng đã kiểm chứng và bảo vệ
-- bằng cùng giao thức transaction/version, không lấy từ client.

INSERT INTO sales.order_outbox (
    event_id, tenant_id, order_id, aggregate_version,
    event_type, schema_version, occurred_at, payload
) VALUES (
    :event_id, :tenant_id, :order_id, :new_version,
    'sales.order-confirmed', 1, :confirmed_at,
    jsonb_build_object(
        'orderId', :order_id,
        'totalVnd', :verified_total_text,
        'currency', 'VND'
    )
);

COMMIT;
~~~

Đoạn SQL minh họa **lệnh xác nhận với các dòng đã lưu ổn định**; nếu lệnh còn thêm/sửa dòng, repository phải ghi chúng trong chính transaction và giữ đúng version root. Chỉ COMMIT khi UPDATE trả **đúng một hàng** và INSERT outbox thành công. Nếu hai thao tác không cùng commit, có thể phát event OrderConfirmed dù dữ liệu rollback, hoặc dữ liệu confirm nhưng mất ý định publish.

Outbox bảo vệ tính nguyên tử **trong database Sales**, không tự bảo đảm Inventory đã giữ tồn hoặc Payment đã thu tiền. Consumer vẫn cần idempotency vì broker có thể phát lại.

## 10. Persistence row và DTO Java tách khỏi domain

Không bắt buộc một class JPA cho mọi table rồi dùng nó làm DTO. Có thể có các **persistence projections** hoặc record đại diện kết quả nạp SQL:

~~~java
import java.time.Instant;
import java.util.UUID;

record OrderHeaderRow(
    UUID tenantId, UUID orderId, UUID customerId,
    String status, long totalVnd, long rowVersion,
    Instant confirmedAt) {}

record OrderLineRow(
    UUID tenantId, UUID orderId, int lineNo,
    UUID skuId, int quantity, long unitPriceVnd) {}
~~~

Một repository JDBC/JPA có thể map các row đã nạp sang SalesOrder:

~~~java
import java.util.List;

// Mã minh họa phép ánh xạ sau khi repository đã nạp đầy đủ các row.
final class OrderPersistenceMapper {
    static SalesOrder restoreDomain(
            OrderHeaderRow header, List<OrderLineRow> rows) {
        var lines = rows.stream().map(row -> {
            if (!row.tenantId().equals(header.tenantId())
                    || !row.orderId().equals(header.orderId())) {
                throw new IllegalStateException("Cross-order row");
            }
            return new OrderLine(
                row.lineNo(), row.skuId(), row.quantity(),
                row.unitPriceVnd());
        }).toList();

        var domain = SalesOrder.restore(
            new OrderId(header.orderId()), header.customerId(),
            OrderStatus.valueOf(header.status()),
            header.rowVersion(), lines);
        if (domain.totalVnd() != header.totalVnd()) {
            throw new IllegalStateException("Stored total mismatch");
        }
        return domain;
    }
}
~~~

Mapper trên giả định các record persistence và domain đã được định nghĩa cùng module; bản thân một khối mã không phải dự án Java đầy đủ có thể copy rồi build độc lập. Repository còn phải kiểm tra **tenant scope, tính đầy đủ của tập line, trạng thái transaction và thứ tự nạp**. Lỗi **Stored total mismatch** phải được điều tra hoặc sửa theo quy trình dữ liệu, không âm thầm đặt tổng mới rồi tiếp tục một command quan trọng.

### DTO phục vụ mục đích hiển thị

~~~java
import java.util.List;
import java.util.UUID;

record OrderLineView(
    UUID skuId, int quantity, String unitPriceVnd) {}

record OrderView(
    UUID orderId, String status,
    String totalVnd, String currency,
    List<OrderLineView> lines) {
    OrderView { lines = List.copyOf(lines); }
}

final class OrderViewMapper {
    static OrderView fromDomain(SalesOrder order) {
        var views = order.lines().stream()
            .map(line -> new OrderLineView(
                line.skuId(), line.quantity(),
                Long.toString(line.unitPriceVnd())))
            .toList();
        return new OrderView(
            order.id().value(),
            order.status().name(),
            Long.toString(order.totalVnd()),
            "VND",
            views);
    }
}
~~~

Ở đây **row_version, tenant_id, internalRiskNote không bị tự động đưa ra response**. Đây là lựa chọn theo use case chứ không phải mọi API đều phải giấu version. Nếu client cần optimistic update, có thể công bố expectedVersion hoặc ETag **có ngữ nghĩa rõ**; field bị công bố do API contract quyết định chứ không do tình cờ nó nằm trong bảng.

**Chiều mapping có ý nghĩa:**

~~~text
HTTP input DTO
  → validation cú pháp + auth + application command
  → domain behavior
  → repository maps domain thành persistence writes
  → transaction commit
  → response DTO / integration event

Read-only query
  → SQL projection/read model
  → response DTO có quyền và format
~~~

Không cần gọi domain behavior để dựng một báo cáo read-only; cũng không được dùng một read DTO tự do để **ghi ngược** vào aggregate.

## 11. Request/response DTO phải mô tả hành vi, không phải cột

Một API có thể tách các yêu cầu như:

~~~java
import java.util.UUID;

record AddOrderLineRequest(UUID skuId, int quantity) {}

record ConfirmOrderRequest(UUID commandId, long expectedVersion) {}
~~~

**AddOrderLineRequest** không mang unitPriceVnd nếu giá chốt phải được Sales lấy từ bảng giá có thẩm quyền. Nếu use case cho phép khách nhập giá thỏa thuận, request có thể chứa giá đề xuất nhưng **domain/application vẫn cần cơ chế chấp thuận**, không chuyển thẳng thành đơn giá chốt.

**ConfirmOrderRequest** mang expectedVersion để phát hiện request dựa trên dữ liệu cũ, và commandId/idempotencyKey để retry an toàn; **nó không mang status=CONFIRMED**. Endpoint có thể là:

~~~http
POST /v1/orders/6cb1d299-4fd0-4f39-ab95-195db8ffed82/confirm HTTP/1.1
Authorization: Bearer [access-token]
Idempotency-Key: 18f2fe65-b7ee-4d9f-9f9e-65f560125d52
Content-Type: application/json

{
  "expectedVersion": 6
}
~~~

Lớp application thực hiện:

1. Xác thực caller và lấy tenantId/permissions từ context tin cậy.
2. Tra idempotency key theo phạm vi tenant/caller/command; kiểm tra nếu key cũ được dùng với payload khác.
3. Nạp Order theo tenantId, orderId từ repository, bảo vệ trạng thái và version.
4. Gọi **domain confirm()**, không setter status.
5. Lưu state và outbox cùng transaction; kiểm tra số hàng cập nhật.
6. Trả response có trạng thái/tiền đã xác nhận hoặc xử lý conflict, không trả entity JPA.

### Vì sao không dùng một DTO duy nhất cho Create, Update, Read?

| Use case | Field cần có | Field tuyệt đối không được người gọi tự gán |
| --- | --- | --- |
| Tạo đơn | Danh sách SKU và số lượng dự kiến | status, totalVnd, confirmedAt, tenantId |
| Thêm dòng | SKU, quantity, expectedVersion nếu cần | row_version của database dưới dạng tự do, internalRiskNote |
| Xác nhận đơn | OrderId trong URL, command ID/idempotency key | totalVnd, status, paidAt do client tùy ý |
| Xem chi tiết | Các dòng và tổng tiền được phép xem | Các trường nội bộ/PII vượt quyền |
| Xem danh sách | OrderId, status, total và thời gian cơ bản | Không cần tải toàn bộ OrderLine/graph |

Đôi khi nhiều use case có thể dùng chung một **value object/DTO đơn giản** nếu ngữ nghĩa, quyền và định dạng giống nhau. Nhưng **sự trùng field không tự chứng minh chúng là cùng một hợp đồng**. Một CreateRequest với các trường bắt buộc có thể cần validation khác UpdateRequest, nơi một trường không được gửi nghĩa là giữ nguyên.

### Validation nên ở đúng vị trí

- **Transport validation:** JSON có cú pháp đúng, UUID parse được, quantity là số nguyên, field được phép xuất hiện.
- **Authorization:** actor có quyền truy cập đúng Order/tenant không.
- **Domain validation:** đang DRAFT không, dòng hàng hợp lệ, tổng có tràn, transition có hợp lệ không.
- **Persistence protection:** UNIQUE, FK, CHECK, transaction, version condition và quyền DB.
- **Integration contract validation:** schemaVersion, eventId, currency, timestamp và trường bắt buộc có đúng nghĩa.

Mọi lớp có thể lặp một số phép kiểm tra để phòng vệ, nhưng mỗi lớp giữ trách nhiệm riêng; không đẩy tất cả vào annotation trên entity rồi hy vọng mọi đường đi đều dùng nó.

## 12. Integration event không phải JSON của entity lúc save()

Giả sử Sales muốn thông báo Order đã xác nhận:

~~~json
{
  "eventId": "a74acf66-f904-4f90-a82b-1716ad0c7a16",
  "eventType": "sales.order-confirmed",
  "schemaVersion": 1,
  "producer": "sales",
  "tenantId": "8b15ae84-f427-45d4-a949-1a6fcb3f5b17",
  "aggregateId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-22T03:00:00Z",
  "correlationId": "4f77ce91-8352-463d-b4be-29a353a1c029",
  "payload": {
    "orderId": "6cb1d299-4fd0-4f39-ab95-195db8ffed82",
    "totalVnd": "1250000",
    "currency": "VND"
  }
}
~~~

Sự kiện có **envelope và payload dành cho consumer**, không chứa internalRiskNote, row_version vật lý, đối tượng ORM có lazy relation hoặc toàn bộ Customer profile. Đây là một **sự thật đã commit**, khác với ConfirmOrder command vốn có thể bị từ chối.

| Trường / khái niệm | Ý nghĩa | Sai lầm khi dùng chung entity |
| --- | --- | --- |
| eventId | Định danh lần sự thật đã xảy ra | Retry tạo UUID mới và consumer đếm hai lần |
| aggregateId | Order chịu thay đổi | Dùng ID tạm của row/ORM proxy |
| aggregateVersion | Phiên bản trạng thái Order | Nhầm với schemaVersion của JSON |
| schemaVersion | Hợp đồng để consumer parse | Thay field vì refactor DB mà không version |
| occurredAt | Mốc nghiệp vụ từ producer | Lấy receivedAt/publishedAt của broker |
| payload | Dữ kiện tối thiểu đã công bố | Serialize cả quan hệ Customer/Payment/Address |
| tenantId, producer | Namespace và nguồn phát | Cho consumer tin tenantId chưa xác thực là đủ quyền |

**Sự kiện miền khác sự kiện tích hợp:** Domain OrderConfirmed có thể là đối tượng nội bộ, còn integration event được mapper đổi thành contract có version và quyền truy cập. Đổi tên class Java hoặc ORM không bắt buộc tạo breaking change của event nếu ngữ nghĩa ngoài vẫn như cũ.

### Outbox và consumer idempotency

Một relay có thể publish event rồi crash trước khi đánh dấu đã gửi. Khi chạy lại, nó publish **cùng eventId**, không tạo một sự thật nghiệp vụ mới. Consumer nên có dedup/inbox được commit cùng thay đổi state cục bộ:

~~~sql
CREATE SCHEMA IF NOT EXISTS integration;

CREATE TABLE integration.processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer làm trong một transaction: thử INSERT processed_event, nếu đã tồn tại thì không áp dụng tác động cục bộ lần nữa; nếu mới, xử lý và commit rồi ACK. Nếu gửi email/call thanh toán **bên ngoài** transaction, cần idempotency ở đích hoặc một workflow bền vững riêng. Chỉ có bảng processed_event không biến HTTP call ngoài database thành giao dịch ACID.

### Đừng coi mọi thay đổi row là domain event

CDC có thể nhìn thấy UPDATE order_header khi:

- Order thật sự được confirm;
- một cột cache tổng tiền được tính lại;
- một migration backfill dữ liệu cũ;
- một cột audit được sửa;
- retry một thao tác ghi.

Chỉ có ý nghĩa nghiệp vụ/phần tử hợp đồng thích hợp mới quyết định **có sự kiện OrderConfirmed hay không**. Nếu ánh xạ mọi UPDATE của JPA thành event "OrderUpdated" mang toàn bộ entity, consumer vừa không biết nên phản ứng gì vừa có nguy cơ xử lý lặp hoặc dữ liệu nhạy cảm.

## 13. Analytical fact không phải lớp Order đã được copy sang warehouse

Khác biệt grain làm lộ rõ giới hạn của "một mô hình":

| Đối tượng | Grain đúng | Ví dụ đo lường |
| --- | --- | --- |
| Order aggregate | Một Order | Hành vi confirm/cancel và tổng đơn |
| OrderLine storage | Một dòng của Order | SKU, quantity, đơn giá snapshot |
| OrderConfirmed event | Một lần xác nhận hợp lệ | Thời điểm và ID sự kiện |
| FactPaidOrderLine | Một dòng đã đủ điều kiện ghi nhận thanh toán | gross/net/quantity theo ngày và SKU |
| FactPaymentAttempt | Một lần thử thanh toán | Kết quả thử, độ trễ |
| DimProduct SCD2 | Một phiên bản thuộc tính sản phẩm theo hiệu lực | Category/tên sản phẩm tại thời điểm đã chọn |

Một Order có ba dòng tương ứng ba hàng FactPaidOrderLine. Một PaymentAttempt thất bại **không phải** một đơn hàng mới. Một OrderConfirmed cũng **không tự đồng nghĩa** đã thanh toán hoặc có doanh thu kế toán.

Một model fact ví dụ:

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id UUID NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_goods_vnd BIGINT NOT NULL CHECK (gross_goods_vnd >= 0),
    net_paid_goods_vnd BIGINT NOT NULL
        CHECK (net_paid_goods_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (net_paid_goods_vnd <= gross_goods_vnd)
);
~~~

Đây là **schema minh họa cho tình huống một OrderLine được ghi nhận thanh toán đúng một lần**. Nếu có nhiều lần capture một dòng hoặc partial refund, phải chọn grain khác, ví dụ **một capture allocation** hoặc fact điều chỉnh riêng. Không cố nhét nhiều lần thanh toán vào một khóa (Order, lineNo) rồi ghi đè không truy vết.

### JOIN sai làm nhân doanh thu

Giả sử Order O-1 có hai line, tổng 300.000 VND, và Payment có hai attempt (một failed, một captured). Nếu JOIN OrderLine với PaymentAttempt rồi SUM(lineAmount) mà không chọn đúng attempt/grain, kết quả có thể thành 600.000 VND.

Không thể giải quyết bằng cách đổi class OrderEntity thành OrderDTO rồi vẫn JOIN sai. Phải **phát biểu grain, chọn nguồn trạng thái đủ điều kiện và nối dữ liệu ở mức đã tổng hợp chính xác**:

~~~sql
-- Trên fact đã làm sạch: mỗi dòng đã PAID xuất hiện đúng một lần.
SELECT business_date,
       SUM(net_paid_goods_vnd) AS paid_goods_vnd,
       COUNT(DISTINCT order_id) AS paid_orders
FROM mart.fact_paid_order_line
WHERE tenant_id = :tenant_id
  AND business_date >= DATE '2026-11-01'
  AND business_date < DATE '2026-12-01'
GROUP BY business_date
ORDER BY business_date;
~~~

COUNT(*) là số **dòng đã thanh toán**, không phải số Order. COUNT(DISTINCT order_id) theo ngày là số Order có dòng được ghi nhận trong ngày; khi một Order có dòng ở nhiều ngày, phải xem lại định nghĩa KPI và grain. Business date phải được tính theo chính sách múi giờ/cutoff, không mặc định là ngày ETL ingest.

**Một analytical model có thể denormalize vì truy vấn**, nhưng không nên trở thành nguồn ra quyết định cập nhật Order. Data mart có độ trễ, correction và version của pipeline riêng; nó không sở hữu command confirm.

## 14. Trong các cách lưu khác nhau, sai lầm vẫn tồn tại

Anti-pattern một mô hình không chỉ xảy ra khi dùng JPA hoặc SQL:

| Công nghệ | Hình thức "dùng chung" hay gặp | Hậu quả | Hướng thiết kế |
| --- | --- | --- | --- |
| **Quan hệ / JPA** | Entity ánh xạ table được nhận/trả trực tiếp qua REST | Rò field, lazy graph, setter vượt bất biến, migration phá API | Domain/DTO tách quyền, repository và projection |
| **Document database** | Document JSON nội bộ chính là API JSON | Client và writer cũ ghi đè/xóa field mới, thiếu version | Document schema/version, API DTO, conditional update |
| **Graph database** | Node/edge tự sinh thành public response và quyền mutation | Lộ traversal, hiểu nhầm edge là quyền sở hữu | Query/response graph theo use case; domain vẫn có root |
| **Time-series** | Một class SensorReading dùng cả ingest và báo cáo ngày | Không phân biệt raw/event time với bucket aggregate | Raw model, rollup grain, thời gian giữ riêng |
| **Analytical warehouse** | Dùng ORM OrderEntity làm fact | Sai grain, JOIN nhân measure, xóa lịch sử | Fact/dimension có grain/metric, lineage riêng |

### Document cũng có bài toán phiên bản

Document cũ:

~~~json
{
  "orderId": "O-101",
  "schemaVersion": 1,
  "totalVnd": 200000,
  "lines": [
    { "skuId": "P-1", "quantity": 2, "unitPriceVnd": 100000 }
  ]
}
~~~

Document mới có trường discountPerUnitVnd và totalVnd đã giảm. Nếu old writer đọc rồi **replace cả document** bằng một POJO không có field mới, nó có thể xóa discount mà không cảnh báo. Mô hình document cần reader có version, mapper hiểu dữ liệu cũ, optimistic version/conditional update và quy tắc cấm writer cũ sửa đối tượng dùng schema mới.

### Graph cũng không có quyền xuyên context

Node Customer → Order → Product dùng để truy vấn quan hệ nhiều bước, nhưng không chứng minh Customer có quyền sửa tất cả Order và Product qua cạnh. Nếu đem nguyên node graph làm DTO để client PATCH quan hệ, có thể biến một tính năng tìm kiếm thành quyền cập nhật rộng hơn ý định nghiệp vụ.

**Rút ra:** lựa chọn relational/document/graph/analytics thay đổi cách lưu và truy vấn, **không xóa trách nhiệm phân biệt mô hình miền, vật lý và trao đổi**.

## 15. Khi nào không cần tách mọi lớp?

Một hệ thống CRUD nhỏ có thể không cần nhiều mapper và model. Tách lớp là **công cụ quản lý ranh giới**, không phải KPI số lượng file.

Ví dụ một công cụ quản trị nội bộ duy nhất lưu danh mục **mã đơn vị đo** gồm code, name và active:

- Người dùng đều có cùng quyền, không có thông tin nhạy cảm.
- Không có bất biến phức tạp ngoài code duy nhất và tên không rỗng.
- Không có consumer công khai phụ thuộc lâu dài vào định dạng API.
- Không có các đường ghi độc lập hoặc workflow nhiều trạng thái.
- Ứng dụng và database được deploy cùng vòng đời, dữ liệu ít và migration đơn giản.

Trong trường hợp này, một data record hoặc projection có cấu trúc gần giống table và DTO có thể đủ. Nhưng vẫn cần xác thực quyền, SQL parameterization, constraint, concurrency phù hợp và không tự mở tất cả cột hệ thống cho người dùng.

### Ma trận quyết định mức độ tách

| Câu hỏi | Nếu "có" | Hướng hành động |
| --- | --- | --- |
| API/event được nhiều consumer độc lập dùng? | Contract thay chậm hơn schema nội bộ | Tách exchange DTO và version/compatibility |
| Có PII/secret hoặc quyền field khác nhau? | Entity không an toàn để serialize | Dùng DTO allowlist theo vai trò |
| Có trạng thái và bất biến chuyển đổi? | Setter có thể bypass rule | Dùng domain behavior và command |
| Một aggregate trải nhiều bảng/document? | Không 1:1 với persistence model | Repository mapping rõ |
| Có đọc và ghi khác workload? | Eager graph làm chậm list, write model nặng | Read projection riêng |
| Có tích hợp nhiều bounded context? | Một từ có thể khác nghĩa | ACL, command/event contract riêng |
| Có analytical fact/dimension? | Grain khác và dữ liệu lịch sử riêng | Semantic model không là ORM entity |
| Old/new binaries chạy song song khi deploy? | Field mới có thể bị writer cũ xóa/ghi sai | Có schema version, compatibility tests |
| Chỉ là CRUD nội bộ nhỏ và ổn định? | Lớp bổ sung có thể không đem lợi ích | Giữ đơn giản, nhưng bảo vệ quyền/constraint |

**Tách vì một ranh giới thật, không tách vì tên pattern.** Một hệ thống có 15 class đều là bản sao field của Order mà tất cả tự map lẫn nhau vẫn có thể rối hơn một mô hình đơn giản. Hãy ghi **lý do thay đổi, quyền sở hữu và quy tắc ánh xạ**; đó là giá trị của việc tách.

### Các kỹ thuật bổ trợ, không thay thế thiết kế

- **MapStruct hoặc mapper tự viết:** giảm code chuyển đổi lặp, nhưng mapping tự động cùng tên có thể không phát hiện field đổi nghĩa.
- **Bean Validation:** hữu ích để kiểm tra định dạng và constraint theo nhóm, nhưng không bảo vệ mọi business transition.
- **Jackson annotations:** có thể chặn một số field và vòng lặp; không biến persistence entity thành hợp đồng public ổn định.
- **JPA @Version:** hỗ trợ optimistic locking của ORM, nhưng mọi đường ghi (native SQL/batch) phải được kiểm soát theo cùng chính sách.
- **CQRS/read projections:** hữu ích khi read và write khác workload; không nhất thiết phải có hai database hoặc event sourcing.
- **Anti-corruption layer:** chuyển ý nghĩa từ đối tác; không đơn thuần đổi snake_case sang camelCase.

## 16. Chuyển đổi hệ thống legacy từng bước, không "đập bỏ và viết lại"

Khi code cũ đã dùng OrderEntity làm input/output, thay mọi API và class trong một PR lớn có thể gây downtime hoặc phá client. Một lộ trình hợp lý:

### Bước 1 — Lập bản đồ các đường sử dụng entity

Tìm **các luồng** chứ không chỉ tên class:

- Endpoint nào nhận, trả hoặc ghi OrderEntity?
- Scheduler, admin tool, batch job nào gọi save()/merge()?
- Serializer nào dùng lazy association hoặc tự mở field?
- Consumer nào parse JSON từ entity; có client mobile phiên bản cũ không?
- Có script SQL trực tiếp sửa status/total/OrderLine không?
- Report nào SELECT trực tiếp bảng OLTP hoặc dùng row để tính số liệu?

**Đầu ra:** ma trận caller → use case → quyền → model hiện tại → rủi ro → owner. Không cần sao chép mọi file vào bài tài liệu; cần biết phạm vi tác động để tránh bỏ sót old writer.

### Bước 2 — Cố định hợp đồng hiện tại bằng test

Trước khi sửa endpoint, ghi nhận contract mà client **thực sự phụ thuộc**:

~~~text
GET /v1/orders/{id}
  response fields đang được consumer dùng
  format id/status/amount/time và null handling
  lỗi 403/404/409 theo phạm vi quyền

POST /v1/orders
  những field được phép nhập
  behavior khi caller gửi field cấm
  retry/idempotency hiện tại
~~~

Nếu API trước đây lỡ công bố field nhạy cảm, **không coi việc tiếp tục phơi bày nó là nghĩa vụ tương thích**; cần khắc phục an toàn, đánh giá tác động và thông báo consumer thích hợp. Nhưng với field hợp lệ, thêm DTO mới nên giữ contract v1 trong giai đoạn chuyển tiếp.

### Bước 3 — Tách response DTO trước, giữ schema hiện tại

Tạo OrderViewMapper hoặc SQL projection có quyền truy cập rõ. Đổi controller **chỉ trả DTO**, tránh serializer đi sâu vào entity. Kiểm tra client contract, SQL query count, pagination và PII.

Ưu điểm: thường **không cần đổi database** để đạt lợi ích lớn về bảo mật và khả năng tiến hóa. Việc này có thể làm trước khi tách domain aggregate phức tạp.

### Bước 4 — Tách command DTO và giới hạn đầu vào

Đưa CreateOrderRequest, AddLineRequest, ConfirmOrderRequest vào application boundary. Từ đó xử lý:

- allowlist trường đầu vào theo use case;
- tenant/actor lấy từ security context;
- idempotency/expectedVersion;
- không tự map status và total từ request sang row;
- kiểm tra state transition bằng domain behavior.

**Đừng dùng reflection copy tất cả field từ request sang entity**: nó chỉ thay hình thức anti-pattern. Mapper ghi có chủ đích sẽ rõ hơn và dễ review.

### Bước 5 — Phục hồi domain và quản lý transaction

Có thể giữ các bảng cũ trong khi repository mới ánh xạ sang SalesOrder. Domain xác thực bất biến; repository áp originalVersion/row lock và ghi atomically. Các đường ghi còn lại phải được nâng cấp hoặc bị chặn để không bypass rule.

Nếu tổng tiền cũ từng được lưu sai hoặc có trạng thái lạ, **không âm thầm sửa khi load**. Đưa dữ liệu lỗi vào chương trình reconciliation/migration có audit, tách việc sửa dữ liệu khỏi lệnh confirm của khách.

### Bước 6 — Tách event integration và read/analytics model

Chỉ phát integration event **sau commit** bằng outbox hoặc cơ chế bền vững tương đương; có schemaVersion, quyền consumer và idempotency. Bổ sung fact/dimension riêng theo grain nếu có báo cáo phân tích; tránh tính gross/paid trực tiếp từ những UPDATE ORM.

### Bước 7 — Migration vật lý theo expand–migrate–switch–contract

Khi cần đổi bảng thực:

1. **Expand:** thêm cột/bảng ở dạng old/new writer có thể cùng tồn tại.
2. **Migrate/backfill:** chuyển dữ liệu theo quy tắc có căn cứ; giữ unknown nếu thiếu lịch sử.
3. **Switch:** nâng reader/writer và consumer, đối soát dữ liệu, bật tính năng mới sau khi old writer nguy hiểm đã rời đi.
4. **Contract:** xóa field/bảng cũ chỉ khi không còn dependency và có kế hoạch khôi phục.

Khi đã phát sinh dữ liệu theo mô hình mới, rollback một binary cũ không hiểu trường mới có thể **xóa mất thông tin**. Phương án an toàn đôi khi là roll-forward/hotfix hoặc tạm chặn write, không đơn giản đổi image triển khai.

### Ma trận chuyển tiếp

| Giai đoạn | Entity JPA cũ | DTO riêng | Domain riêng | DB mới |
| --- | --- | --- | --- | --- |
| Hiện trạng | Cả read/write/API | Chưa | Chưa | Chưa |
| Tách response | Vẫn dùng trong repository | **Read DTO có contract** | Chưa bắt buộc | Chưa |
| Tách command | Chỉ tầng storage | Read + command DTO | Bắt đầu hành vi | Chưa |
| Bảo vệ miền | Persistence riêng | Tất cả API qua DTO | **Aggregate bảo vệ rule** | Có thể chưa |
| Expand schema | Persistence có mapper mới | Không phải đổi contract | Giữ nghĩa | Cột/bảng tương thích |
| Switch/contract | Không còn lộ ra ngoài | Contract có version | Đường ghi có chủ | Schema mới đã đối soát |

Mỗi giai đoạn cần **test regression** và tiêu chí triển khai. Không tuyên bố thành công vì package đã có tên **domain**, trong khi controller vẫn nhận entity và SQL admin vẫn ghi vượt bất biến.

## 17. Bộ kiểm thử phát hiện lỗi trước khi production

| Lớp kiểm thử | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| **API security** | Client gửi tenantId của người khác, internalRiskNote hoặc status | Không được gán trái quyền; không lộ dữ liệu |
| **API contract** | GET OrderView, POST ConfirmOrder v1 | Field/format/error ổn định theo hợp đồng |
| **Serialization** | Entity có quan hệ hai chiều và lazy association | Controller dùng DTO, không vòng lặp và không N+1 ngoài dự tính |
| **Domain unit** | Confirm Order rỗng hoặc CANCELLED | Bị từ chối, state không đổi |
| **Domain unit** | Quantity âm, giá âm, tổng long overflow | Lỗi rõ trước khi ghi |
| **Repository mapping** | Nạp Order có nhiều dòng | Đúng ID, tenant, số dòng, total, version |
| **Data corruption** | DB có total khác SUM(line) | Báo mismatch, không âm thầm hợp thức hóa |
| **Concurrency** | Hai confirm cùng originalVersion | Tối đa một commit |
| **Transactional outbox** | INSERT outbox thất bại sau UPDATE Order | Rollback cả Order |
| **Consumer** | Broker redeliver cùng eventId | Không nhân đôi tác động |
| **HTTP PATCH** | Missing phone vs phone=null vs phone="" | Theo ba ý định được định nghĩa |
| **Read performance** | List 100 Order, mỗi Order có nhiều line | Số query/latency được đo, không bất ngờ tải graph |
| **Schema evolution** | Old/new app cùng đọc cột mới | Không mất dữ liệu/đổi ngữ nghĩa |
| **Analytics grain** | Order có hai line, hai payment attempts | Không nhân tổng sau JOIN |
| **Cross-tenant** | Cùng UUID giả định ở hai tenant | Không ghép/đọc nhầm |

### Ví dụ Java unit test cho domain

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class SalesOrderTest {
    @Test
    void cannotConfirmEmptyOrder() {
        var order = SalesOrder.create(new OrderId(UUID.randomUUID()),
                                      UUID.randomUUID());
        assertThrows(IllegalStateException.class, () ->
            order.confirm(UUID.randomUUID(), Instant.now()));
        assertEquals(OrderStatus.DRAFT, order.status());
    }

    @Test
    void confirmsAmountFromLinesNotRequestBody() {
        var order = SalesOrder.create(new OrderId(UUID.randomUUID()),
                                      UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 2, 100_000));
        order.addLine(new OrderLine(2, UUID.randomUUID(), 1, 50_000));
        var event = order.confirm(UUID.randomUUID(),
            Instant.parse("2026-11-22T03:00:00Z"));
        assertEquals(250_000L, event.totalVnd());
        assertEquals(OrderStatus.CONFIRMED, order.status());
    }

    @Test
    void rejectsLineMutationAfterConfirm() {
        var order = SalesOrder.create(new OrderId(UUID.randomUUID()),
                                      UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 1, 10_000));
        order.confirm(UUID.randomUUID(), Instant.now());
        assertThrows(IllegalStateException.class, () ->
            order.addLine(new OrderLine(2, UUID.randomUUID(), 1, 10_000)));
    }
}
~~~

Các test trên giả định JUnit Jupiter có trong project, **chỉ minh họa kiểm thử miền**. Chúng không chứng minh DB ngăn ghi đồng thời, REST không lộ PII hoặc message không bị phát trùng; phải bổ sung integration/contract tests trong môi trường tương ứng.

### Test chống race cần engine thật

Với Order version=6 và status DRAFT:

~~~text
T1 nạp Order version=6; T2 nạp Order version=6
T1 confirm, UPDATE WHERE version=6 → 1 row
T1 INSERT outbox, COMMIT
T2 confirm, UPDATE WHERE version=6 → 0 row
T2 ROLLBACK, trả conflict hoặc kết quả idempotent thích hợp
Kết luận: chỉ một transition commit và một business event tương ứng
~~~

Nếu cả T1 và T2 dùng **cùng idempotency key**, application cần đối chiếu cùng request và trả lại kết quả đã xử lý theo hợp đồng. Nếu là hai command khác nhau, xung đột version là hợp lệ. Mock repository trả về cùng entity trong bộ nhớ **không phản ánh khóa/isolation thực tế**, nên không đủ kiểm chứng tranh chấp.

### Quan sát sau khi triển khai

Cần đo thêm các tín hiệu:

- Số request mang field lạ hoặc bị chặn vì mass assignment.
- Tỷ lệ 403/409 theo endpoint, tenant và phiên bản client.
- Query count, p95 latency, lazy loading exception khi trả danh sách.
- Data mismatch giữa header total và dòng, orphan line, duplicate ID.
- Optimistic locking conflict và tỷ lệ retry thành công.
- Outbox lag, consumer dead-letter, event duplicate/gap.
- Chênh lệch dashboard với nguồn theo cùng tenant/cutoff/metric version.

Một hệ thống đã tách DTO nhưng vẫn có các lỗi trên cần được điều tra tiếp; **tên kiến trúc không bảo đảm kết quả**.

## 18. Bài tập thực hành: hệ thống đặt vé sự kiện

### Bối cảnh

Một ứng dụng bán vé hội thảo đang dùng **TicketBookingEntity** vừa là JPA entity vừa làm request/response và message JSON:

~~~java
// CODE CŨ CÓ VẤN ĐỀ: chỉ minh họa, không dùng trong production.
@Entity
class TicketBookingEntity {
    @Id
    public UUID bookingId;
    public UUID tenantId;
    public UUID customerId;
    public String customerEmail;
    public String status;            // DRAFT/HELD/PAID/CANCELLED
    public long totalPriceVnd;
    public String internalFraudFlag;
    @OneToMany(mappedBy = "booking")
    public List<TicketLineEntity> ticketLines;
}
~~~

Controller hiện tại:

~~~java
// CODE CŨ CÓ VẤN ĐỀ:
@PutMapping("/bookings/{bookingId}")
TicketBookingEntity save(@RequestBody TicketBookingEntity body) {
    return repository.save(body);
}
~~~

Yêu cầu mới:

- Khách được chọn loại vé và số lượng; giá được chốt từ chính sách giá đã được xác minh.
- Năng lực chỗ ngồi theo hạng vé do **TicketInventory** quản lý. **Booking** không được tự tăng giảm tổng sức chứa.
- Khi Payment xác nhận đã thu đúng số tiền, Booking có thể chuyển sang PAID theo trạng thái cho phép; không tin trường status do browser gửi.
- Người dùng chỉ được xem booking của họ; nhân viên chống gian lận xem internalFraudFlag qua use case/role riêng.
- Một Booking có nhiều TicketLine; một Booking đã thanh toán không được tự ý đổi giá dòng.
- Notification cần sự kiện BookingPaid; Analytics cần số vé đã thanh toán theo loại vé và số Booking duy nhất theo ngày.
- Ứng dụng mobile cũ chưa nâng cấp ngay; cần thay đổi dần mà không làm lộ field mới.

### Câu hỏi

1. Chỉ ra **ít nhất sáu lỗi** hoặc nguy cơ từ code cũ, phân nhóm theo quyền, bất biến, hiệu năng, tương thích và dữ liệu.
2. Đề xuất **TicketBooking aggregate**, TicketLine value object và bất biến cho các trạng thái DRAFT/HELD/PAID/CANCELLED. Quy tắc **không cấp vượt sức chứa** thuộc bounded context nào?
3. Đề xuất **schema quan hệ** gồm booking_header, booking_line, khóa ghép tenant, FK, CHECK và version. Mô tả thao tác ghi nào cần transaction, thao tác nào cần giao thức liên context.
4. Thiết kế **CreateBookingRequest**, **PayBooking command** và **BookingView**: trường nào có thể nhập, trường nào chỉ đọc và trường nào không công bố?
5. Thiết kế integration event **BookingPaidV1** gồm eventId, bookingId, occurredAt, currency, paidTotalVnd và schemaVersion. Vì sao không gửi nguyên TicketBookingEntity?
6. Một Payment callback bị gửi hai lần; làm sao tránh BookingPaid bị ghi hai lần và tránh gửi hai email? Phân biệt transaction cục bộ và tác động ngoài.
7. Một Booking có hai dòng: 2 vé STANDARD giá 500.000 VND/vé và 1 vé VIP giá 1.000.000 VND. Tổng bằng bao nhiêu? Analytics có thể lấy COUNT(*) từ fact theo dòng vé để đếm **Booking** không?
8. Hãy đưa ra kế hoạch **tách DTO trước, domain và repository sau, cuối cùng đổi schema** cùng ít nhất bốn kiểm thử bắt buộc.
9. Người dùng gửi PATCH có trường **customerEmail=null** và một request không có trường customerEmail. Hai thao tác có luôn đồng nghĩa không? Thiết kế hợp đồng để phân biệt.
10. Nếu kho phân tích chỉ lưu một hàng/Booking nhưng muốn doanh số theo ticketType, điều gì đang sai về grain và cần sửa thế nào?

### Hướng giải tham khảo

**1. Nhận diện lỗi.** Browser có thể thử sửa status, total, tenantId, customerId và internalFraudFlag; response trả dữ liệu chống gian lận và email quá rộng; quan hệ ticketLines có thể lazy/N+1/vòng lặp; entity bị thay cấu trúc khi migration; PUT với entity dễ overwrite trường mới bằng NULL; không có state machine hoặc điều kiện version.

**2. Domain.** TicketBooking root có các command addTicket, requestHold, recordCapturedPayment, cancel theo quy tắc. TicketLine có ticketType, quantity>0, unitPriceVnd≥0, giá chốt và lineNo/lineId duy nhất. PAID không được đổi dòng qua command thường. TicketInventory mới sở hữu bất biến không giữ vượt capacity; Booking chỉ nhận một **reservation token/confirmation** hợp lệ theo contract. Payment sở hữu captured amount, không phải callback không xác thực từ client.

**3. Storage.** booking_header có PK(tenantId, bookingId), trạng thái, totalVnd, rowVersion, thời điểm phù hợp; booking_line có PK(tenantId, bookingId, lineNo), FK vào header và CHECK quantity/price. Nếu chốt giá/tổng, ghi các dòng/header trong một transaction và bảo vệ version. Cấp chỗ ở TicketInventory và thu tiền ở Payment là **các transaction riêng**, cần command idempotent, trạng thái trung gian và workflow bù/đối soát.

**4. DTO.** CreateBookingRequest nhận ticketType và quantity; server kiểm tra giá và quyền. PayBooking không có setter status=PAID và có idempotency/expectedVersion phù hợp. BookingView chỉ trả bookingId, ticket lines, số tiền, trạng thái và thời điểm người dùng được xem. Không trả internalFraudFlag; email chỉ trả khi use case/quyền phù hợp và theo nguyên tắc tối thiểu.

**5. Event.** BookingPaidV1 công bố sự thật đã commit với eventId ổn định, bookingId, tenantId/producer scope, occurredAt, schemaVersion, amount và currency; không phơi bày cờ chống gian lận hoặc graph ORM. Event không có nghĩa TicketInventory đã cấp chỗ nếu đó là một quy trình riêng chưa hoàn tất.

**6. Retry.** Payment callback phải được xác thực và đối chiếu theo captureId/bookingId/tenantId/amount; lưu trạng thái PAID cùng outbox trong transaction. Retry cùng captureId không tạo thêm lần thanh toán. Consumer Notification dedup eventId; nếu gửi email bên ngoài transaction, cần idempotency key/trạng thái gửi để hạn chế lặp theo chính sách được công bố.

**7. Tính tiền.** Tổng là \(2\times500.000 + 1\times1.000.000 = 2.000.000\) VND. Fact theo **dòng vé** có hai hàng nhưng chỉ **một Booking**; COUNT(*) không phải số Booking. Muốn số Booking dùng COUNT(DISTINCT bookingId) theo cùng tenant và kỳ (với định nghĩa ngày phù hợp); muốn số vé dùng SUM(quantity).

**8. Refactor.** Tách response DTO để chặn field nhạy cảm và lazy graph; tách request/command DTO để ngăn over-posting; bổ sung domain behavior và repository/transaction; sau đó mở rộng schema/migrate/đối soát/switch/contract. Kiểm thử mass assignment và cross-tenant, confirm/pay sai trạng thái, hai callback trùng, optimistic locking tranh chấp, SQL transaction rollback khi outbox lỗi, event contract, dashboard đúng grain.

**9. PATCH.** Field không được gửi có thể nghĩa là giữ nguyên; JSON null có thể nghĩa là yêu cầu xóa, nếu nghiệp vụ cho phép. Hợp đồng phải diễn đạt tri-state, không tin nullable field trong entity là đủ.

**10. Grain.** Một hàng/Booking chứa tổng tiền không thể tự phân bổ doanh số theo nhiều ticketType nếu chỉ có một trường ticketType. Cần **fact theo TicketLine hoặc một allocation fact** và snapshot giá/tổng phù hợp. Nếu JOIN fact booking một hàng với nhiều dòng ticket mà SUM(totalBooking) trực tiếp, doanh số sẽ bị nhân.

## 19. Checklist phòng tránh và kết luận

Trước khi dùng một Java class ở nhiều ranh giới, hãy tự hỏi:

- **Mục đích:** class này là aggregate có hành vi, persistence row, command DTO, response DTO hay event?
- **Grain:** một object/bảng/JSON có cùng **đơn vị dữ liệu** với nơi được tái sử dụng không?
- **Quyền sở hữu:** ai được thay status, giá, tenant, email hoặc internal flag? Caller có thể ghi field cấm không?
- **Bất biến:** command có đi qua root/state machine và transaction, hay chỉ save() một object do client gửi?
- **Cập nhật đồng thời:** mọi writer cùng tôn trọng optimistic version/lock của aggregate không?
- **Tiền và thời gian:** amount có currency/đơn vị chính xác; timestamp có nguồn/cutoff rõ ràng không?
- **NULL và PATCH:** absent, null và giá trị cụ thể có được phân biệt theo ý định không?
- **Bảo mật:** có trường PII/secret/internal nào vô tình được serializer đưa ra response/log/event không?
- **ORM graph:** controller có gây lazy exception, N+1, circular reference hoặc tải dữ liệu quá mức không?
- **Storage:** PK/FK/CHECK/index/partition dựa trên bất biến và truy vấn, không sao chép mù quáng class?
- **Mapping:** conversion có được kiểm chứng cho ID/tenant/status/version/money và không tự bỏ qua dữ liệu sai không?
- **Hợp đồng:** REST và event có schema/version, backward compatibility và semantic owner rõ ràng không?
- **Outbox:** sự thật đã commit trước khi phát event; consumer dedup và xử lý retry an toàn không?
- **Analytics:** fact có grain/measure/timestamp đúng; JOIN không nhân số liệu; không dùng trạng thái đọc trễ để quyết định OLTP?
- **Tiến hóa:** đổi bảng có thể giữ API ổn định; đổi API có thể không phá migration; old writer có đọc/ghi được dữ liệu mới không?
- **Mức độ tách:** tạo lớp riêng vì khác nghĩa/quyền/vòng đời, hay chỉ vì muốn thêm boilerplate?
- **Kiểm thử:** đã có unit, DB concurrency, API security, contract, consumer idempotency và data reconciliation cho các rủi ro thực tế chưa?

**Kết luận:** **Một đối tượng nghiệp vụ có thể được biểu diễn nhiều cách**, và việc ép Java class, bảng lưu trữ, DTO HTTP, event và dữ kiện phân tích thành một mô hình duy nhất thường đánh đồng **quyền thay đổi, ngữ nghĩa, grain và vòng đời**. Hậu quả không chỉ là code khó bảo trì; đó còn là bất biến bị bỏ qua, lộ dữ liệu, đọc chậm, thay schema phá API, event trùng và báo cáo sai. Cách khắc phục là **xác định ranh giới trước**, đặt hành vi đúng nơi sở hữu, dùng constraint/transaction cho storage, DTO/contract được thiết kế theo mục đích và mapper có kiểm chứng. Đồng thời giữ đủ thực dụng: với CRUD nội bộ rất đơn giản, không cần nhân bản class vô ích. Mục tiêu cuối cùng của **DATABASE_DATA_MODELING** là mô hình dữ liệu **rõ ý nghĩa, an toàn, kiểm chứng được và có thể tiến hóa**, chứ không phải nhiều hay ít file Java.
