# CQRS và tách mô hình đọc khỏi mô hình ghi

## Mục tiêu học tập

Một hệ thống cloud thường vừa phải xử lý lệnh ghi có nhiều quy tắc nghiệp vụ, vừa phải phục vụ lượng lớn truy vấn có hình dạng dữ liệu rất khác nhau. Màn hình tìm kiếm, danh sách giao dịch, dashboard và báo cáo thường cần join, lọc, sắp xếp hoặc tổng hợp; trong khi luồng ghi phải bảo vệ bất biến, xử lý cạnh tranh và commit dữ liệu đúng.

**CQRS (Command Query Responsibility Segregation)** là nguyên tắc tách trách nhiệm xử lý lệnh làm thay đổi trạng thái khỏi trách nhiệm truy vấn trạng thái. CQRS có thể được áp dụng trong một ứng dụng và cùng một database. Ở mức tách sâu hơn, read model có thể được xây riêng, cập nhật bất đồng bộ và triển khai trên hạ tầng độc lập.

Bài học thuộc chương **Tính nhất quán**, tập trung vào cách phân chia command/query, thiết kế write model/read model, đồng bộ projection, độ trễ nhất quán và chi phí vận hành. Đây là lựa chọn kiến trúc hữu ích trong một số workload, đồng thời bổ sung trạng thái và luồng đồng bộ phải quản lý.

Sau bài học, bạn có thể:

- Phân biệt command với query theo tác động lên trạng thái.
- Nhận diện khi nào mô hình đọc/ghi chung trở thành nút thắt và khi nào CQRS chỉ tạo thêm độ phức tạp.
- Thiết kế write model bảo vệ bất biến nghiệp vụ và read model tối ưu theo nhu cầu truy vấn.
- Chọn cách cập nhật projection bằng transaction, outbox/event, CDC hoặc polling.
- Xử lý eventual consistency, projection lag, duplicate event, ordering, replay và rebuild.
- Thiết kế read-your-writes, version check, polling và trải nghiệm người dùng khi dữ liệu đọc chưa cập nhật.
- Đánh giá database, cache, queue, network, security, observability, TCO và khả năng phục hồi trên cloud.
- Xây dựng kịch bản chất lượng và quyết định áp dụng CQRS theo các nguyên tắc Well-Architected.

## 1. Bài toán: một mô hình dữ liệu phục vụ hai kiểu tải

Giả sử nền tảng đặt phòng quản lý booking, khách hàng, phòng, giá và thanh toán. Một lệnh tạo booking cần:

1. Kiểm tra danh tính và quyền người đặt.
2. Xác minh phòng còn khả dụng trong khoảng thời gian cần đặt.
3. Tính giá theo chính sách tại thời điểm giao dịch.
4. Bảo đảm không có booking xung đột.
5. Ghi booking và trạng thái liên quan một cách nhất quán.
6. Phát sự kiện để gửi thông báo và cập nhật hệ thống phụ trợ.

Đây là luồng **ghi** có bất biến nghiệp vụ. Một sai lệch nhỏ có thể tạo đặt trùng hoặc tính sai tiền.

Màn hình quản trị có thể cần tổng số booking theo ngày, trạng thái và chi nhánh; chi tiết booking cùng thông tin khách, phòng, thanh toán; danh sách booking chờ xác nhận với nhiều bộ lọc; hoặc thống kê doanh thu theo chiến dịch. Đây là luồng **đọc** có hình dạng dữ liệu khác với aggregate dùng để bảo vệ nghiệp vụ ghi.

CQRS đặt câu hỏi: có nên dùng một mô hình cho cả ghi và đọc, hay tổ chức hai mô hình phù hợp với từng mục đích?

~~~mermaid
flowchart LR
    CLIENT["Client / UI"] --> CMD["Command"]
    CMD --> WRITE["Write model"]
    WRITE --> WDB[("Write database")]
    WDB --> EVT["Event / Outbox"]
    EVT --> PROJECT["Projection handler"]
    PROJECT --> RDB[("Read model")]
    CLIENT --> QUERY["Query"]
    QUERY --> READ["Query handler"]
    READ --> RDB
~~~

Sơ đồ trên thể hiện CQRS ở mức tách read/write model và cập nhật projection bất đồng bộ. CQRS không bắt buộc có hai database; cốt lõi là **tách trách nhiệm và mô hình xử lý**, còn ranh giới lưu trữ là quyết định riêng.

## 2. Command và query khác nhau thế nào?

### 2.1. Command: yêu cầu thay đổi trạng thái

Command thể hiện ý định thực hiện hành động nghiệp vụ, ví dụ CreateBooking, ConfirmBooking, CancelBooking, ChangeRoomPrice, CapturePayment hoặc ReserveInventory.

Command handler thường phải kiểm tra:

- Caller có quyền thực hiện hành động không?
- Dữ liệu đầu vào hợp lệ không?
- Aggregate đang ở trạng thái cho phép chuyển tiếp không?
- Bất biến nghiệp vụ còn đúng tại thời điểm commit không?
- Thay đổi có xung đột với command đồng thời không?
- Client retry có tạo tác dụng phụ lặp không?

Command handler điều phối thay đổi trạng thái. Kết quả thường là thành công/thất bại cùng ID, version hoặc trạng thái cần thiết để caller biết điều gì đã được xác nhận.

### 2.2. Query: đọc dữ liệu mà không thay đổi trạng thái nghiệp vụ

Query lấy dữ liệu để hiển thị, phân tích hoặc ra quyết định, ví dụ GetBookingDetails, SearchBookings, GetRevenueByDay hay FindPaymentsPendingReconciliation.

Query nên tránh thay đổi business state. Query có thể ghi telemetry kỹ thuật hoặc tạo cache entry, nhưng không nên âm thầm xác nhận booking hoặc trừ tiền. Query handler tối ưu cho access pattern: projection, join, index, search engine, cache, pagination hoặc aggregate view.

### 2.3. Quy tắc nhận diện

| Câu hỏi | Command | Query |
| --- | --- | --- |
| Có chủ đích thay đổi business state? | Có | Không |
| Có thực thi invariant nghiệp vụ ghi? | Có | Không |
| Có thể trả về dữ liệu? | Có, thường là ID/version/result | Có, là dữ liệu được yêu cầu |
| Retry có thể tạo side effect? | Có, cần idempotency/concurrency control | Thường không, nhưng vẫn có chi phí tải |
| Có thể tối ưu dữ liệu riêng? | Write model | Read model |
| Ví dụ | Hủy booking | Xem booking đã hủy chưa |

HTTP method không thay thế việc hiểu hành vi thực tế. GET không nên gửi thanh toán hoặc sửa trạng thái chỉ vì thuận tiện. Command thường dùng POST/PUT/PATCH/DELETE theo semantics API, query thường dùng GET.

## 3. CQRS là gì và không phải là gì?

### 3.1. CQRS chỉ tách trách nhiệm, không nhất thiết tách hạ tầng

Ở mức đơn giản, ứng dụng giữ cùng một database nhưng tổ chức command handler và query handler độc lập:

~~~mermaid
flowchart TB
    API["API layer"] --> C["Command handler"]
    API --> Q["Query handler"]
    C --> W[("Shared database")]
    Q --> R["Read queries"]
    R --> W
~~~

Cùng một database có thể phục vụ cả ghi và đọc, nhưng code path, validation và query model được tách. Cách này giảm coupling trong mã nguồn mà chưa cần distributed synchronization.

### 3.2. CQRS với read model riêng

Ở mức tách sâu hơn, command thay đổi write database; sự kiện hoặc CDC cập nhật read database:

~~~mermaid
flowchart TB
    CMD["Command API"] --> CH["Command handler"]
    CH --> WDB[("Write DB")]
    WDB --> OUTBOX["Outbox / CDC"]
    OUTBOX --> BROKER[("Event stream / broker")]
    BROKER --> P1["Projection: booking list"]
    BROKER --> P2["Projection: dashboard"]
    P1 --> RDB1[("Read store A")]
    P2 --> RDB2[("Analytics store")]
    Q1["Query API"] --> RDB1
    Q2["Dashboard API"] --> RDB2
~~~

Read model có thể nằm trong relational database, search engine, cache, document store, key-value store hoặc warehouse tùy nhu cầu. Read store riêng cho phép tối ưu khả năng đọc mà không làm thay đổi write model, nhưng kéo theo eventual consistency và vận hành đồng bộ.

### 3.3. CQRS không đồng nghĩa microservices hoặc event sourcing

| Khái niệm | Câu hỏi mà nó trả lời |
| --- | --- |
| CQRS | Tách trách nhiệm xử lý command và query như thế nào? |
| Microservices | Năng lực nghiệp vụ được chia thành dịch vụ triển khai độc lập nào? |
| Event-driven architecture | Các thành phần phản ứng và giao tiếp qua event ra sao? |
| Event sourcing | Trạng thái hiện tại được biểu diễn bằng chuỗi event nào? |
| Read replica | Làm sao nhân bản dữ liệu để mở rộng tải đọc? |
| Materialized view | Làm sao lưu trước kết quả truy vấn để đọc nhanh? |

Có thể dùng CQRS mà không dùng event sourcing. Write model vẫn lưu trạng thái trong bảng quan hệ và phát event qua outbox. Có thể dùng microservices mà không dùng CQRS. Có thể tạo read replica nhưng vẫn dùng cùng mô hình query. Các kỹ thuật có thể phối hợp, nhưng không thay thế định nghĩa của nhau.

## 4. Write model: bảo vệ quy tắc và bất biến nghiệp vụ

Write model được thiết kế quanh các thay đổi trạng thái hợp lệ. Với booking, aggregate có thể chứa trạng thái đặt chỗ, thời gian, khách hàng, phòng, giá đã chốt và version.

Ví dụ các bất biến:

- Booking chỉ được xác nhận khi đang Pending.
- Booking không được chuyển sang Confirmed sau khi đã Cancelled.
- Không có hai booking Confirmed xung đột cùng phòng/thời gian.
- Tổng tiền tại thời điểm xác nhận phải theo chính sách giá hợp lệ.
- Một payment capture có business key duy nhất cho lần thanh toán tương ứng.

Write model có thể dùng domain object, service, transaction và constraint ở database. Không nên dựa hoàn toàn vào UI hoặc query kiểm tra trước đó vì trạng thái có thể đổi giữa lúc đọc và lúc ghi.

### 4.1. Command handler minh họa bằng Java

~~~java
public record ConfirmBookingCommand(
    UUID bookingId,
    UUID callerId,
    String idempotencyKey
) {}

public record CommandResult(
    UUID aggregateId,
    long version,
    String status
) {}

public final class ConfirmBookingHandler {
    private final BookingRepository bookings;
    private final AuthorizationService authorization;

    public ConfirmBookingHandler(
        BookingRepository bookings,
        AuthorizationService authorization
    ) {
        this.bookings = bookings;
        this.authorization = authorization;
    }

    public CommandResult handle(ConfirmBookingCommand command) {
        authorization.requireCanConfirm(
            command.callerId(), command.bookingId()
        );

        Booking booking = bookings.findForUpdate(command.bookingId())
            .orElseThrow(BookingNotFoundException::new);

        booking.confirm();
        bookings.save(booking);

        return new CommandResult(
            booking.id(), booking.version(), booking.status().name()
        );
    }
}
~~~

Đây là ví dụ khái niệm. Ứng dụng thực tế cần đặt transaction boundary, xử lý idempotency key, optimistic/pessimistic concurrency và quyền từ danh tính đã xác thực. Không tin callerId do client tùy ý gửi; phải lấy từ security context của server.

### 4.2. Concurrency và invariant ở write side

Hai request đồng thời có thể cùng đọc “còn phòng” trước khi một request commit. Các biện pháp có thể cần phối hợp:

- Unique/exclusion constraint hoặc cơ chế bảo vệ overlap ở database.
- Optimistic locking với version.
- Pessimistic lock cho aggregate hoặc tài nguyên tranh chấp.
- Conditional update theo điều kiện còn khả dụng.
- Transaction isolation phù hợp và retry conflict.
- Idempotency key để chống lặp cùng command từ client.

CQRS không tự giải quyết race condition. Write model phải bảo vệ invariant tại điểm commit; read model có thể chậm nhưng không được dùng thay cho kiểm tra ghi có tính quyết định.

## 5. Read model: tối ưu theo nhu cầu truy vấn

Read model là cấu trúc dữ liệu được chuẩn bị để trả lời một hoặc nhiều query hiệu quả. Nó có thể tổng hợp hoặc phi chuẩn hóa dữ liệu từ nhiều nguồn.

Màn hình booking list có thể cần Booking ID, trạng thái, ngày nhận/trả, tên khách, phòng, chi nhánh, tổng tiền và trạng thái thanh toán. Trong write model, các dữ liệu có thể nằm trong nhiều aggregate/bảng. Read model có thể lưu thành một document hoặc bảng projection để giảm join và tăng tốc tìm kiếm.

### 5.1. Projection minh họa

~~~sql
CREATE TABLE booking_read_model (
    booking_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    customer_name VARCHAR(200),
    room_name VARCHAR(200),
    branch_id UUID,
    booking_status VARCHAR(30) NOT NULL,
    payment_status VARCHAR(30),
    check_in DATE,
    check_out DATE,
    total_amount DECIMAL(18,2),
    source_version BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Bảng này là ví dụ, không phải schema bắt buộc. Read model chỉ nên lưu trường cần cho query, tuân thủ quyền và phân loại dữ liệu. Không sao chép PII hoặc dữ liệu thanh toán nhạy cảm nếu màn hình không cần.

### 5.2. Nhiều read model cho nhiều access pattern

| Read model | Query tối ưu | Lưu trữ có thể cân nhắc |
| --- | --- | --- |
| Booking detail | Một booking theo ID, nhiều trường liên quan | Document/relational projection |
| Booking search | Filter, sort, full-text, phân trang | Search index |
| Dashboard theo ngày | Group, aggregate, trend | OLAP/warehouse/materialized aggregate |
| Available room lookup | Tra cứu nhanh theo ngày/địa điểm | Key-value/cache hoặc projection |
| Customer history | Danh sách giao dịch của một khách | Partitioned relational/document view |

Không nhất thiết tạo database mới cho mỗi query. Read model có thể là một schema hoặc materialized view trong cùng database, tùy quy mô và yêu cầu độc lập.

### 5.3. Phi chuẩn hóa có chủ đích

Read model thường lưu dữ liệu đã join hoặc aggregate sẵn. Điều này giúp query đơn giản và nhanh hơn nhưng dữ liệu có thể bị lặp. Khi tên khách thay đổi, tất cả projection chứa tên khách có thể cần cập nhật; nếu bất đồng bộ, một thời gian có thể có dữ liệu cũ.

Cần quyết định trường nào là snapshot tại thời điểm giao dịch (ví dụ tên trên hóa đơn), trường nào luôn hiển thị giá trị mới nhất, projection nào được phép eventual consistency, và thay đổi nguồn dữ liệu sẽ phát event nào để cập nhật các view.

## 6. CQRS và consistency: read model thường cập nhật bất đồng bộ

Nếu write database và read database là hai kho độc lập, transaction ghi không thể mặc nhiên commit cả hai cùng lúc. Quy trình thường là:

1. Command cập nhật write database.
2. Cùng transaction tạo outbox event.
3. Relay/event connector phát event.
4. Projection handler tiêu thụ event.
5. Read model được cập nhật.
6. Query tiếp theo đọc trạng thái mới.

Trong khoảng giữa bước 1 và bước 5, người dùng có thể đọc dữ liệu cũ. Đây là **eventual consistency**: nếu không có cập nhật mới và hệ thống tiếp tục xử lý bình thường, read model sẽ tiến tới phản ánh trạng thái nguồn.

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Command API
    participant W as Write DB
    participant O as Outbox / Broker
    participant P as Projection worker
    participant R as Read DB
    participant Q as Query API
    U->>C: Confirm booking
    C->>W: Commit booking + outbox
    W-->>C: Commit success, version 12
    C-->>U: Confirmed, version 12
    U->>Q: Refresh booking list
    Q->>R: Read projection
    R-->>Q: Có thể vẫn là version 11
    O->>P: Deliver event version 12
    P->>R: Apply projection
    Q->>R: Read again
    R-->>Q: Version 12
~~~

Cần định nghĩa trải nghiệm người dùng khi query trả version cũ. Có thể hiển thị “đang cập nhật”; với thao tác cần quyết định chính xác, query phải kiểm tra write model hoặc dùng read-your-writes token.

## 7. Những chiến lược đồng bộ read model

### 7.1. Cập nhật đồng bộ cùng database

Nếu write và read model ở cùng relational database, command handler có thể cập nhật cả hai trong cùng transaction hoặc dùng trigger/materialized view tùy thiết kế.

**Ưu điểm:** consistency mạnh trong transaction boundary, đơn giản hóa read-after-write.

**Giới hạn:** hai model vẫn chia sẻ CPU, I/O, lock và connection; projection nặng có thể kéo dài transaction và làm chậm write. Cách này hữu ích để bắt đầu CQRS ở mức code separation.

### 7.2. Transactional outbox

Write transaction ghi cả business state và event vào outbox. Relay đọc và publish event; projection consumer cập nhật read store. Outbox tránh khoảng hở giữa commit business data và ý định phát event.

Nếu relay publish thành công nhưng chết trước khi đánh dấu event đã gửi, event có thể được gửi lại. Projection consumer phải idempotent theo eventId/version hoặc upsert an toàn.

### 7.3. Change Data Capture (CDC)

CDC đọc transaction log hoặc change stream của write database để tạo sự kiện thay đổi. Cần hiểu:

- Thay đổi nào là business event, thay đổi nào chỉ là kỹ thuật?
- Có đủ thông tin để tạo projection hay phải lookup thêm?
- Schema migration ảnh hưởng connector thế nào?
- Lag, offset, retention và recovery được quản lý ra sao?
- Delete được biểu diễn bằng tombstone hay event riêng?
- Có thể replay từ điểm nào và dữ liệu nguồn còn đủ không?

CDC capture row changes; nó không tự biến mọi row change thành domain event tốt. Cần thiết kế contract cho consumer.

### 7.4. Polling hoặc scheduled refresh

Job định kỳ truy vấn thay đổi kể từ watermark trước đó và cập nhật read model. Cách này phù hợp workload không đòi cập nhật gần thời gian thực.

Rủi ro gồm polling lag, bỏ sót bản ghi đến muộn, watermark sai, query làm tăng tải write database và chạy trùng. Nên có timestamp/sequence ổn định, checkpoint bền vững, overlap window và idempotent upsert.

### 7.5. So sánh các phương án

| Phương án | Độ trễ cập nhật | Độ phức tạp | Phù hợp khi |
| --- | --- | --- | --- |
| Cùng transaction DB | Gần như ngay khi commit | Thấp đến trung bình | Cùng DB, read model không quá nặng |
| Outbox + broker | Gần thời gian thực nhưng có lag | Trung bình đến cao | Cần tách store và phát event tin cậy |
| CDC | Thường gần thời gian thực | Cao, cần connector/ops | Nhiều bảng/nguồn thay đổi, cần capture log |
| Polling/batch refresh | Theo chu kỳ | Có thể thấp lúc đầu | Dữ liệu báo cáo chấp nhận trễ |
| Rebuild toàn bộ | Phụ thuộc thời gian rebuild | Tốn tài nguyên | Tái tạo projection, migration hoặc khôi phục |

Không chọn phương án chỉ theo độ trễ danh nghĩa. Cần kiểm thử throughput, duplicate, ordering, recovery, schema evolution và chi phí vận hành.

## 8. Projection handler: idempotency, ordering và version

Projection handler chuyển event thành trạng thái read model. Nó phải chịu được event giao lặp, đến muộn, sai thứ tự và được replay.

### 8.1. Idempotent projection

Một cách đơn giản là lưu source version cùng aggregate. Chỉ áp dụng update nếu version mới hơn version đã lưu.

~~~sql
INSERT INTO booking_read_model (
    booking_id, booking_status, source_version, updated_at
)
VALUES (
    :booking_id, :status, :version, CURRENT_TIMESTAMP
)
ON CONFLICT (booking_id)
DO UPDATE SET
    booking_status = EXCLUDED.booking_status,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE booking_read_model.source_version < EXCLUDED.source_version;
~~~

Cú pháp gần PostgreSQL. Trong hệ thống thật, cần xử lý cùng version nhưng payload khác, validate event và cập nhật đủ trường projection theo contract.

Nếu projection là phép cộng như tăng tổng số booking, upsert theo version của một aggregate đơn lẻ có thể chưa đủ. Cần lưu event ID đã áp dụng, dùng transaction, hoặc xây projection có thể tính lại từ nguồn dữ liệu.

### 8.2. Ordering và version gap

Giả sử projection hiện có booking version 8 nhưng nhận event version 7. Có thể bỏ qua vì dữ liệu cũ. Nếu hiện có version 6 nhưng nhận event version 8, event version 7 bị thiếu. Tùy nghiệp vụ, có thể chờ event còn thiếu trong thời gian giới hạn, reload aggregate state từ nguồn chuẩn, rebuild projection cho aggregate hoặc đưa event vào quarantine và cảnh báo.

Không áp dụng version 8 tùy tiện nếu việc bỏ qua version 7 làm mất một chuyển đổi trạng thái quan trọng.

### 8.3. Event schema evolution

Projection consumer có thể chạy lâu hơn phiên bản producer hoặc được deploy độc lập. Nên có schema version và quy tắc tương thích:

- Thêm field optional có default phù hợp.
- Không đổi nghĩa field hiện hữu mà không version hóa.
- Không xóa field khi consumer cũ vẫn cần.
- Có contract test producer/consumer.
- Có kế hoạch replay event cũ khi nâng projection.
- Khi cần đổi read model, chạy projection phiên bản mới song song rồi chuyển query traffic sau khi kiểm chứng.

## 9. Read-your-writes và trải nghiệm người dùng

Một hệ thống eventual consistency có thể khiến người dùng vừa xác nhận booking nhưng danh sách vẫn hiển thị Pending. Đây không nhất thiết là lỗi dữ liệu nguồn, nhưng nếu UX không rõ, người dùng có thể bấm xác nhận lần nữa hoặc gọi hỗ trợ.

Các chiến lược:

**Trả trạng thái command rõ ràng:** response trả bookingId, version và trạng thái đã commit. UI có thể hiển thị kết quả command trực tiếp thay vì đợi read projection.

**Read-your-writes routing:** sau command, query có thể đọc write database hoặc endpoint trạng thái chuẩn trong một khoảng thời gian ngắn.

**Version token:** client gửi minimumVersion trong query; read service đợi projection đạt version đó trong thời hạn ngắn hoặc trả trạng thái chưa sẵn sàng.

**Polling:** client polling trạng thái projection với backoff và giới hạn; không polling liên tục gây tải.

**Push update:** server gửi event qua WebSocket/SSE khi projection cập nhật, nếu trải nghiệm đòi hỏi.

**Optimistic UI:** UI hiển thị trạng thái dự kiến sau command nhưng đánh dấu pending cho đến khi được xác nhận.

### 9.1. Không biến query thành nguồn quyết định ghi

Read model có thể trễ. Nếu client thấy phòng còn trống trong projection rồi gửi command giữ phòng, write handler vẫn phải kiểm tra write model và invariant. “Query vừa trả còn chỗ” không phải quyền giữ chỗ.

### 9.2. Mức nhất quán theo use case

| Use case | Consistency mong muốn | Chiến lược có thể dùng |
| --- | --- | --- |
| Booking confirmation | Chỉ trả confirmed sau write commit | Write model là nguồn chuẩn |
| Booking list sau xác nhận | Có thể trễ ngắn nếu UX thể hiện | Read-your-writes/version token |
| Báo cáo doanh thu | Chấp nhận trễ theo kỳ | Batch projection, watermark |
| Số phòng khả dụng | Không bán vượt tồn | Kiểm tra và reserve ở write side |
| Chi tiết thanh toán | Có thể cần gần mới nhất | Query nguồn chuẩn hoặc projection có version |
| Dashboard điều hành | Có thể chấp nhận vài phút | Aggregate/read store riêng |

Không áp dụng cùng một consistency policy cho mọi query. Hãy gắn yêu cầu với hậu quả nếu dữ liệu đọc cũ.

## 10. Rebuild, backfill và migration read model

Read model là dữ liệu dẫn xuất; cần có khả năng tạo lại hoặc sửa khi logic projection thay đổi.

### 10.1. Rebuild từ event log

Nếu event được lưu đủ lâu và có schema/contract ổn định, có thể tạo projection mới bằng cách replay event từ đầu hoặc một checkpoint. Cần xem event retention, thời gian rebuild, ảnh hưởng production, phân biệt live traffic với replay, tránh external side effect, kiểm tra projection mới và khả năng rollback.

### 10.2. Backfill từ write database

Nếu event history không đủ, có thể đọc snapshot hiện tại từ write database để dựng projection. Cần snapshot hoặc watermark để thay đổi phát sinh trong lúc backfill không bị mất.

Quy trình tham khảo:

1. Chụp mốc dữ liệu hoặc snapshot consistent.
2. Backfill theo key range/partition.
3. Đồng thời lưu các thay đổi phát sinh sau watermark.
4. Áp dụng phần thay đổi còn lại theo thứ tự phù hợp.
5. So sánh record count, aggregate totals và sample records.
6. Chạy shadow query để so kết quả.
7. Chuyển traffic sang read model mới.
8. Giữ rollback cho đến khi xác nhận ổn định.

### 10.3. Blue/green projection

Có thể tạo booking_read_v2 song song booking_read_v1. Projection worker ghi vào v2; khi v2 đạt lag thấp và kiểm tra dữ liệu đạt, query service chuyển dần traffic. Giữ v1 trong khoảng thời gian rollback.

Không xóa projection cũ ngay sau chuyển đổi. Cần kiểm tra index, storage, quota và retention; trong thời gian dual-build, database và worker có thể chịu tải cao hơn.

## 11. CQRS có cần event sourcing không?

**Không.** CQRS chỉ yêu cầu tách trách nhiệm command và query. Write model có thể dùng CRUD/relational state thông thường và transactional outbox.

Event sourcing lưu các event bất biến làm nguồn sự thật để tái dựng trạng thái aggregate. Cách này có lợi khi cần audit lịch sử trạng thái và replay domain event, nhưng đòi hỏi event evolution, snapshot, projection, ordering và vận hành event store.

| Đặc điểm | CQRS với state-based write model | CQRS kết hợp event sourcing |
| --- | --- | --- |
| Nguồn chuẩn | Trạng thái hiện tại trong DB | Chuỗi event bất biến |
| Ghi | Update/insert/delete transaction | Append event hợp lệ |
| Rebuild read model | Từ snapshot/CDC/outbox hoặc dữ liệu hiện tại | Có thể replay event history |
| Audit | Cần lưu lịch sử riêng nếu cần | Event history tự nhiên hơn |
| Độ phức tạp | Thấp hơn trong nhiều ứng dụng CRUD | Cao hơn: versioning, snapshot, projection |
| Truy vấn trạng thái | Read từ write model hoặc projection | Fold event hoặc projection |
| Khi phù hợp | Hệ thống cần separation vừa phải | Nghiệp vụ event-centric, audit/replay là yêu cầu lớn |

Không chọn event sourcing chỉ vì đã chọn CQRS. Hãy xác định lợi ích về lịch sử, audit và replay có đủ bù chi phí và learning curve hay không.

## 12. Database và hạ tầng cloud cho CQRS

### 12.1. Cùng database, schema riêng

Ứng dụng có thể dùng một relational database, command handler cập nhật bảng nghiệp vụ và query handler đọc view/materialized view hoặc bảng projection riêng.

Ưu điểm: transaction và consistency đơn giản; dễ bắt đầu; ít thành phần vận hành.

Giới hạn: read/write vẫn tranh chấp CPU, I/O, lock và connection; read workload nặng có thể ảnh hưởng transaction. Cần index, workload isolation, query budget và pool riêng.

### 12.2. Write primary và read replica

Một primary chịu ghi, replica phục vụ query. Đây là read scaling, không hoàn toàn là CQRS. Replica thường cập nhật bất đồng bộ nên query có thể đọc dữ liệu cũ.

Cần đo replication lag, kiểm soát read-after-write, failover và khả năng replica chịu truy vấn. Nếu query shape khác biệt đáng kể, read projection chuyên biệt có thể phù hợp hơn replica thuần túy.

### 12.3. Write store và read store riêng

Có thể dùng relational database cho transaction, search engine cho tìm kiếm, warehouse cho analytics hoặc cache/document database cho view chi tiết. Cần quản lý:

- Network hop và egress/cross-zone cost.
- Dữ liệu lặp và chính sách xóa.
- Encryption, IAM và tenant isolation trên từng store.
- Backup/restore và rebuild.
- Credential, connection pool và quota.
- Data residency, retention và audit.

Read store riêng giúp mở rộng độc lập nhưng tăng số dependency và failure mode. Nếu read projection lỗi, command ghi có tiếp tục được không? Điều đó phụ thuộc event durability, backlog capacity và yêu cầu nghiệp vụ.

### 12.4. Degraded mode

Nếu read store down nhưng write database còn hoạt động, command có thể vẫn ghi và outbox tiếp tục tích lũy event; query có thể trả lỗi hoặc fallback tới nguồn chuẩn với giới hạn tải. Nếu broker down, outbox giữ event để relay sau; cần giám sát backlog và capacity.

Không cho phép backlog vô hạn. Cần retention, storage capacity, throttling và cảnh báo trước khi outbox làm đầy write database.

## 13. Security và quyền truy cập trong hai mô hình

Tách read/write không được tạo đường vòng bảo mật.

- Command handler xác thực caller và authorization cho từng hành động.
- Query handler kiểm tra quyền xem từng đối tượng và tenant scope; read model không phải dữ liệu công khai.
- Projection chỉ đưa các trường cần thiết vào read store.
- Event/outbox có thể chứa PII hoặc payment metadata; mã hóa, retention và quyền truy cập phù hợp.
- Service identity của projection worker chỉ được đọc topic/schema và ghi đúng read store.
- Tenant ID phải được lấy/kiểm tra từ nguồn tin cậy, không tin giá trị do client truyền.
- Audit ghi command quan trọng, thay đổi quyền, replay và rebuild có tác động dữ liệu.
- Nếu xóa dữ liệu cá nhân, cần propagate deletion tới read model, cache, search index, warehouse và archive theo chính sách.

Một lỗi phổ biến là command side kiểm tra quyền đầy đủ nhưng query side trả projection theo ID, khiến người dùng truy cập dữ liệu tenant khác. Phân quyền phải được thực thi ở mỗi query boundary.

## 14. Hiệu năng, cache và chi phí consistency

### 14.1. Tách read/write có thể giảm tranh chấp

Khi dashboard đọc liên tục, read database hoặc warehouse riêng có thể giảm áp lực trên write primary. Nhưng projection lag, event backlog, storage và network làm chi phí tăng.

CQRS cũng có thể tạo nhiều query service/handler; nếu read model không đúng access pattern, hệ thống thêm tầng mà vẫn phải join hoặc gọi nhiều dịch vụ.

### 14.2. Cache có vai trò gì?

Cache là kỹ thuật tối ưu read path, không đồng nghĩa read model. Có thể cache query result hoặc projection, nhưng phải thiết kế invalidation và TTL. Nếu cache cập nhật chậm hơn read store, consistency lag có thêm một tầng.

Cache-aside, write-through và event invalidation có trade-off riêng. Với dữ liệu quyền hoặc thanh toán quan trọng, TTL dài có thể gây hiển thị sai. Query dùng cache không được trở thành nguồn quyết định cho command quan trọng.

### 14.3. Ước lượng lag và backlog

Giả sử hệ thống phát trung bình 500 event/giây, projection worker xử lý 650 event/giây khi hoạt động bình thường. Khi worker dừng 2 phút:

~~~text
Backlog tạo ra = 500 event/s × 120 s
               = 60.000 events
~~~

Khi worker chạy lại, năng lực dư so với event mới là:

~~~text
650 - 500 = 150 events/s
~~~

Thời gian giảm hết backlog, giả định arrival rate và processing rate ổn định:

~~~text
60.000 / 150 = 400 giây ≈ 6 phút 40 giây
~~~

Ví dụ bỏ qua burst, retry, thời gian xử lý không đều và giới hạn read store. Nếu worker chỉ xử lý bằng tốc độ event đến, backlog không giảm. Cần headroom đủ lớn và kiểm thử recovery time, không chỉ throughput bình thường.

### 14.4. Cost per query và business operation

~~~text
Cost per successful command
  = (Write compute + write DB + event/outbox + network + operations)
    / Number of successful commands

Cost per query
  = (Read compute + read store + cache + network + observability)
    / Number of successful queries
~~~

Với CQRS tách store, chi phí có thể gồm duplicate storage, broker, projection compute, log/tracing và backup bổ sung. Cần so với chi phí hiện tại của read query trên primary, bao gồm tác động đến hiệu năng write và scale primary.

## 15. Quan sát và vận hành CQRS

Không nên chỉ giám sát API command và query riêng lẻ. Cần thấy toàn bộ chuỗi từ write commit tới read projection.

| Nhóm | Metric | Câu hỏi |
| --- | --- | --- |
| Command | Success/failure, conflict, validation error, latency p95/p99 | Ghi có đúng và kịp thời không? |
| Write store | Transaction duration, lock wait, connection, replication | Nguồn chuẩn có bị quá tải không? |
| Event/outbox | Pending count, oldest unpublished age, publish failure | Thay đổi đã được phát chưa? |
| Broker | Throughput, lag, redelivery, DLQ, partition skew | Event đang chờ hay lỗi ở đâu? |
| Projection | Processing duration, failure, version gap, duplicate ignored | Read model có theo kịp nguồn không? |
| Read store | Query latency, index/cache hit, storage, throttle | Query có đáp ứng SLO không? |
| Consistency | Projection lag, source version vs read version | Dữ liệu đọc cũ bao lâu? |
| Business | Command completion, query correctness, reconciliation mismatch | Người dùng có nhận kết quả đúng không? |
| Cost | Cost per command/query, storage, broker, egress | Tách model có đáng chi phí không? |

### 15.1. Trace và correlation

Gắn commandId, aggregateId, eventId, correlationId và sourceVersion ở các ranh giới. Trace có thể nối command API, write DB, outbox relay, broker, projection worker và read store. Không nhúng dữ liệu cá nhân vào span attributes.

Correlation ID giúp tìm hành trình; sourceVersion cho biết projection đã bắt kịp mức thay đổi nào.

### 15.2. Cảnh báo theo tác động

- Outbox event cũ nhất chưa publish vượt ngưỡng.
- Projection lag vượt SLO.
- Read model version gap kéo dài.
- DLQ tăng bất thường.
- Read store throttling hoặc query p99 vượt mục tiêu.
- Command conflict tăng do concurrency.
- Không có projection update trong khi write event vẫn tăng.
- Reconciliation giữa write và read model sai lệch.
- Dung lượng outbox/broker sắp đầy.

Mỗi alert cần owner, dashboard và runbook. Không cảnh báo chỉ vì một event duplicate nếu consumer deduplicate an toàn; nhưng duplicate tăng bất thường có thể báo hiệu ACK/visibility hoặc producer retry đang sai cấu hình.

## 16. SLO và kịch bản chất lượng minh họa

Các ngưỡng chỉ là ví dụ học tập, không phải chuẩn chung. Cần chốt điểm đo, cửa sổ, workload và hậu quả nghiệp vụ.

| Mã | Tình huống | Phản hồi mong đợi | Thước đo minh họa |
| --- | --- | --- | --- |
| QA-CQRS-01 | Người dùng xác nhận booking | Write model commit invariant; response trả version đã ghi | 99,9% command hợp lệ được xác nhận trong p95 500 ms |
| QA-CQRS-02 | Projection worker hoạt động bình thường | Read model tiến tới version nguồn | 99% event được áp dụng trong 10 giây |
| QA-CQRS-03 | Worker dừng 2 phút rồi phục hồi | Backlog được xử lý mà không mất hoặc áp dụng sai event | Lag dưới 10 giây trong 8 phút; không sai lệch business key |
| QA-CQRS-04 | Client đọc ngay sau command | Hỗ trợ read-your-writes hoặc thể hiện trạng thái pending | Read trả version tối thiểu hoặc báo projection chưa cập nhật |
| QA-CQRS-05 | Consumer nhận event trùng/sai thứ tự | Deduplicate/version check bảo vệ projection | Không có trạng thái regression; event gap được phát hiện |
| QA-CQRS-06 | Read store bị lỗi | Command vẫn hoạt động nếu durability/backlog đủ; query degraded có kiểm soát | Command SLO giữ trong cửa sổ thử; backlog không vượt capacity |
| QA-CQRS-07 | Tenant A truy vấn dữ liệu tenant B | Từ chối và audit | 100% ca trái phép trong bộ test bị chặn |
| QA-CQRS-08 | Rebuild projection phiên bản mới | Projection mới khớp nguồn trước khi chuyển traffic | Count, totals và sample records đạt đối soát |

SLO projection lag khác SLO API command. Command có thể hoàn tất nhanh nhưng projection trễ nhiều phút. Nếu nghiệp vụ cần cập nhật gần thời gian thực, phải đo và đặt mục tiêu riêng.

## 17. Case study: nền tảng đặt chỗ CQRS

### 17.1. Bối cảnh

Nền tảng đặt chỗ có lưu lượng đọc tìm kiếm và booking list lớn hơn nhiều so với ghi. Khi khuyến mãi, dashboard nội bộ chạy nhiều truy vấn aggregate làm write database tăng CPU và lock contention.

Yêu cầu giả định:

- Command xác nhận booking phải bảo đảm không trùng phòng.
- Booking list chấp nhận trễ ngắn nếu có chỉ báo cập nhật.
- Dashboard doanh thu chấp nhận trễ tối đa vài phút.
- Query search cần filter/sort linh hoạt.
- Dữ liệu tenant phải cách ly.
- Có khả năng rebuild read models sau khi đổi schema.

### 17.2. Thiết kế

**Write side:** Spring Boot command API và relational primary. Booking aggregate, constraint và transaction bảo vệ invariant. Outbox row được ghi cùng transaction.

**Event transport:** Relay phát event booking, payment và cancellation. Broker giữ event theo durability policy; consumer xử lý at-least-once.

**Read side:**
- Booking detail/list projection trong read relational store.
- Search projection trong search engine.
- Revenue aggregate trong analytical store.
- Query handler kiểm tra tenant scope, phân trang và version/lag.

~~~mermaid
flowchart TB
    U["Web / Admin"] --> CMD["Command API"]
    CMD --> W["Write model"]
    W --> WDB[("Relational primary")]
    WDB --> O[("Outbox")]
    O --> B[("Event broker")]
    B --> P1["Booking projection"]
    B --> P2["Search projection"]
    B --> P3["Revenue projection"]
    P1 --> R1[("Read relational store")]
    P2 --> R2[("Search store")]
    P3 --> R3[("Analytics store")]
    U --> Q1["Booking query API"]
    U --> Q2["Search query API"]
    U --> Q3["Dashboard query API"]
    Q1 --> R1
    Q2 --> R2
    Q3 --> R3
~~~

### 17.3. Hành vi khi booking vừa xác nhận

Command API commit booking và outbox; trả bookingId, Confirmed và version 12. UI hiển thị confirmation từ kết quả command. Booking list có thể vẫn ở version 11, nên query API nhận minimumVersion 12 hoặc UI đánh dấu trạng thái cập nhật. Khi projection đạt version 12, dữ liệu hiển thị bình thường.

Dashboard doanh thu có thể cập nhật trong vài phút; màn hình thanh toán chi tiết quan trọng hơn có thể đọc từ nguồn consistency mạnh hoặc hiển thị trạng thái đang đối soát.

### 17.4. Sự cố và phục hồi

Giả sử search projection worker dừng trong 4 phút. Write command vẫn tiếp tục nếu outbox/broker có dung lượng và durability phù hợp. Search data cũ hơn; UI có thể hiển thị thời điểm cập nhật hoặc giảm chức năng. Khi worker hoạt động lại, backlog được xử lý, version check ngăn event cũ ghi lùi dữ liệu.

Nếu read store lỗi kéo dài, không cho phép backlog vô hạn làm đầy nguồn ghi. Cần giới hạn retention, cảnh báo, pause workload không quan trọng hoặc tăng capacity có kiểm soát. Rebuild search index được tiến hành riêng, đối soát rồi mới chuyển traffic.

### 17.5. Lợi ích và chi phí

Lợi ích: query search/dashboard scale độc lập, write model tập trung bảo vệ invariant, mỗi read model tối ưu theo access pattern.

Chi phí: event transport, projection worker, nhiều kho dữ liệu, schema versioning, eventual consistency, reconciliation, backup và trực vận hành. Nếu workload nhỏ, chi phí này có thể vượt lợi ích; cần thử tối ưu query/index/read replica trước khi tách sâu.

## 18. Khi nào nên và không nên dùng CQRS?

| Dấu hiệu | Quyết định nên xem xét |
| --- | --- |
| Read và write có access pattern khác biệt rõ | Tách query handler/model có thể hữu ích |
| Dashboard/analytics gây tải lên write primary | Read projection hoặc analytical store riêng |
| Read query cần nhiều join/aggregate/search phức tạp | Materialized read model/search projection |
| Cần scale read và write độc lập | CQRS với read store riêng nếu TCO phù hợp |
| Nhiều projection phục vụ nhiều consumer | Event-driven projection có thể phù hợp |
| CRUD đơn giản, read/write tương đương | Một model có thể đơn giản hơn |
| Team chưa có năng lực vận hành broker/CDC | Bắt đầu bằng CQRS trong một DB hoặc chưa tách |
| Dữ liệu cần nhất quán tức thời ở mọi query | Read store bất đồng bộ có thể không phù hợp |
| Chưa định nghĩa nguồn chuẩn và ownership | Chưa nên tách thành nhiều store |
| Nhiều hệ thống cùng ghi trực tiếp một dữ liệu | Làm rõ ownership trước khi tạo projection |

CQRS không phải mặc định cho mọi CRUD application. Áp dụng vì một vấn đề cụ thể có thể đo, không phải vì kiến trúc có vẻ hiện đại.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Nghĩ CQRS bắt buộc hai database | Tăng hạ tầng không cần thiết | Tách command/query trong code trước |
| Dùng read model để quyết định invariant ghi | Dữ liệu trễ gây ghi sai hoặc overbooking | Write side kiểm tra và commit invariant |
| Coi query và command chỉ khác HTTP method | Logic nghiệp vụ vẫn trộn lẫn | Phân loại theo tác động lên trạng thái |
| Không đo projection lag | Người dùng thấy dữ liệu cũ nhưng không biết nguyên nhân | SLI lag, version và dashboard |
| Projection không idempotent | Event duplicate làm tăng số liệu | Inbox, business key, version và upsert |
| Không xử lý event sai thứ tự | Projection bị regression | Aggregate version và gap handling |
| Outbox không có cleanup | Bảng tăng vô hạn, query chậm | Retention/archive có audit |
| Rebuild projection không giới hạn | Quá tải DB/broker/read store | Throttle, snapshot, shadow build |
| Sao chép toàn bộ PII sang read stores | Tăng rủi ro dữ liệu và chi phí xóa | Data minimization và deletion propagation |
| Không đối soát source/read model | Sai lệch kéo dài khó phát hiện | Count, total, version và reconciliation |
| Chọn event sourcing chỉ vì CQRS | Độ phức tạp cao hơn lợi ích | Đánh giá riêng nhu cầu event history |
| Tách quá sớm | Nhiều dịch vụ, queue và runbook | Bắt đầu theo bottleneck và SLO thực |

## 20. Bài tập thực hành

Một nền tảng bán vé có 50.000 truy vấn tìm kiếm mỗi phút trong giờ mở bán và 500 lệnh đặt vé mỗi phút. Mỗi vé chỉ được bán một lần; dashboard doanh thu có thể trễ tối đa 2 phút; danh sách vé của người dùng cần phản ánh đơn vừa đặt trong vòng 5 giây. Hệ thống hiện dùng một relational database.

Hãy thực hiện:

1. Xác định command và query trong luồng tìm kiếm, giữ vé, xác nhận thanh toán, hủy vé và xem lịch sử.
2. Vẽ write model bảo vệ invariant “một vé chỉ có một chủ sở hữu hiệu lực”.
3. Thiết kế ít nhất hai read model cho tìm kiếm và dashboard; nêu vì sao hình dạng dữ liệu khác nhau.
4. Chọn cách phát event từ write model và giải thích outbox/CDC phù hợp thế nào.
5. Thiết kế projection handler có idempotency, version check và xử lý event đến sai thứ tự.
6. Đề xuất read-your-writes để danh sách vé cập nhật trong 5 giây.
7. Xác định degraded mode khi read database hoặc broker down.
8. Đề xuất metric cho command latency, query latency, projection lag, outbox age, duplicate rate và reconciliation.
9. Tính backlog và thời gian phục hồi nếu 20.000 event tích lũy, worker xử lý 300 event/giây trong khi 200 event/giây mới tiếp tục đến.
10. Lập TCO và so với phương án tối ưu query/index/read replica trên một database.
11. Viết ADR nêu tiêu chí áp dụng CQRS, rủi ro còn lại và điều kiện xem xét lại.

**Gợi ý tự đánh giá:** Bài làm đạt khi nêu được nguồn dữ liệu chuẩn, bất biến ở write side, mô hình đọc, cơ chế cập nhật, độ trễ cho phép, cách phục hồi và bằng chứng đo được. Vẽ hai database mà không giải thích đồng bộ chưa phải thiết kế CQRS hoàn chỉnh.

## 21. Checklist trước khi đưa CQRS vào production

- [ ] Đã xác định command và query theo tác động lên trạng thái.
- [ ] Write model có nguồn chuẩn và bảo vệ invariant trong transaction.
- [ ] Query handler có access pattern, schema và index rõ.
- [ ] Read model chỉ lưu dữ liệu cần thiết và có tenant authorization.
- [ ] Có cơ chế phát thay đổi đáng tin cậy: transaction cùng DB, outbox, CDC hoặc polling có checkpoint.
- [ ] Projection idempotent, có version/order policy và xử lý gap.
- [ ] Đã xác định consistency expectation cho từng query.
- [ ] Có read-your-writes hoặc UI trạng thái pending khi phù hợp.
- [ ] Có rebuild/backfill, shadow validation và rollback projection.
- [ ] Có deletion propagation cho cache, search, warehouse và archive.
- [ ] Có metrics projection lag, outbox age, DLQ, version gap và reconciliation.
- [ ] Có capacity/retention cho backlog khi consumer hoặc read store lỗi.
- [ ] TCO gồm broker, compute, read stores, network, backup, observability và vận hành.
- [ ] Đã thử duplicate, out-of-order, crash, lag, failover và rebuild.
- [ ] ADR nêu rõ lợi ích, giới hạn và điều kiện bỏ/tái đánh giá CQRS.

## 22. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi thiết kế CQRS |
| --- | --- |
| **Operational Excellence** | Có thể vận hành projection, rebuild, replay, schema migration và đối soát bằng runbook rõ ràng không? |
| **Security** | Command/query authorization, tenant isolation, event protection và deletion propagation có đầy đủ không? |
| **Reliability** | Write state và event có được ghi đáng tin cậy; projection có chịu duplicate, lag và phục hồi không? |
| **Performance Efficiency** | Read/write có scale độc lập đúng bottleneck; lag, p95/p99 và connection có đạt SLO không? |
| **Cost Optimization** | Lợi ích giảm tải primary có bù read store, broker, worker, storage và công sức vận hành không? |
| **Sustainability** | Có tránh sao chép dữ liệu không cần thiết, rebuild lặp và tài nguyên read store nhàn rỗi không? |

**Kết luận:** CQRS tách trách nhiệm thay đổi trạng thái khỏi trách nhiệm truy vấn, cho phép write model bảo vệ bất biến và read model tối ưu theo từng access pattern. Khi hai mô hình nằm ở các store riêng và cập nhật qua event, hệ thống phải quản lý projection lag, duplicate, ordering, replay và đối soát. Hãy áp dụng CQRS khi có khác biệt đọc/ghi đủ rõ để bù chi phí đồng bộ và vận hành; bắt đầu từ ranh giới logic, xác định nguồn chuẩn và đo chất lượng end-to-end theo tinh thần Well-Architected.
