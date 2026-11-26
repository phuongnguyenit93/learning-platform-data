# Đọc dữ liệu trong nhiều yêu cầu trước khi xác nhận

> **Chương:** Dữ liệu và giao dịch  
> **Module:** SPRING_WEB_FLOW  
> **Mục tiêu:** Thiết kế flow đọc dữ liệu qua nhiều HTTP request trước khi người dùng xác nhận; hiểu dữ liệu nào nên giữ trong flow scope, cách quản lý transaction ngắn, cách phát hiện dữ liệu đã thay đổi, và cách bảo vệ thao tác xác nhận bằng optimistic locking, reservation hold, transaction và idempotency.

## 1. Bài toán: dữ liệu đã đọc có thể thay đổi trước lúc xác nhận

Một người dùng mở flow đặt lịch và chọn khung giờ 10:00. Ứng dụng đọc lịch trống rồi hiển thị trang review. Người dùng kiểm tra email, gọi điện hỏi đồng nghiệp và quay lại sau vài phút mới nhấn **Xác nhận**.

Trong khoảng thời gian đó, một người khác có thể đã đặt cùng khung giờ. Dữ liệu ở trang review lúc này không còn phản ánh trạng thái mới nhất.

~~~text
Request 1: GET /booking
  -> đọc slot 10:00 còn trống
  -> hiển thị chooseSlot

Request 2: POST /booking (next)
  -> đọc giá, chính sách, thông tin khách hàng
  -> hiển thị review

... người dùng suy nghĩ ...

Request 3: POST /booking (confirm)
  -> dữ liệu có thể đã thay đổi
  -> phải xác minh lại trước khi ghi
~~~

Đây là đặc điểm quan trọng của ứng dụng nhiều bước: **một flow execution có thể kéo dài qua nhiều request, nhưng một transaction database không nên kéo dài theo flow execution**.

Người dùng có thể mất vài phút hoặc vài giờ giữa hai lần submit. Không giữ transaction và database lock trong toàn bộ khoảng thời gian đó. Thay vào đó, mỗi request thực hiện một đơn vị đọc/ghi ngắn; khi xác nhận, service kiểm tra lại các điều kiện nghiệp vụ trong transaction mới.

## 2. Hai vòng đời khác nhau: flow execution và database transaction

Spring Web Flow duy trì trạng thái điều hướng của một lần chạy flow qua nhiều request. Transaction quản lý tính nguyên tử của một nhóm thao tác dữ liệu trong database.

| Khái niệm | Vòng đời | Mục đích |
| --- | --- | --- |
| FlowExecution | Qua nhiều HTTP request | Giữ state, event, scope và tiến trình của flow |
| Database transaction | Thường trong một lần gọi service | Đảm bảo nhóm thao tác dữ liệu nhất quán |
| Flow scope | Trong flow execution | Giữ lựa chọn/draft cần dùng ở state sau |
| Persistence context | Thường gắn với transaction/session ORM | Quản lý entity đang được theo dõi |
| Reservation hold | Theo chính sách nghiệp vụ và hạn dùng | Tạm giữ tài nguyên trong lúc người dùng xác nhận |

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant W as Spring Web Flow
    participant S as BookingService
    participant DB as Database
    U->>W: Request 1: chọn khung giờ
    W->>S: loadAvailability()
    S->>DB: SELECT trong transaction ngắn
    DB-->>S: dữ liệu khả dụng
    S-->>W: DTO + version
    W-->>U: Render review
    Note over U,DB: Người dùng suy nghĩ; transaction đọc đã kết thúc
    U->>W: Request 2: confirm
    W->>S: confirm(requestId, slotId, expectedVersion)
    S->>DB: Kiểm tra lại + ghi trong transaction mới
    DB-->>S: commit hoặc conflict
    S-->>W: confirmed hoặc unavailable
    W-->>U: Kết quả
~~~

Flow execution giữ dữ liệu cần cho trải nghiệm người dùng. Database transaction chỉ bao quanh thao tác cần bảo vệ tại thời điểm request đó.

### 2.1. Không mở transaction trong lúc người dùng xem trang

Thiết kế sai:

~~~text
BEGIN TRANSACTION
  đọc danh sách chỗ trống
  render review
  chờ người dùng nhấn confirm trong 5 phút
  ghi booking
COMMIT
~~~

Transaction dài có thể giữ connection, row lock hoặc version snapshot; làm tăng contention, nguy cơ timeout và cạn connection pool. Với flow web nhiều bước, transaction không nên bao phủ thời gian tương tác của con người.

Thiết kế phù hợp:

~~~text
Request A:
  BEGIN
    đọc dữ liệu cần hiển thị
  COMMIT

  người dùng xem trang và suy nghĩ

Request B:
  BEGIN
    đọc lại điều kiện quan trọng
    kiểm tra version/availability
    ghi booking
  COMMIT
~~~

## 3. Dữ liệu nào nên giữ qua các request?

Không phải mọi dữ liệu đọc ở request đầu đều nên lưu vào flow scope.

| Loại dữ liệu | Cách xử lý phù hợp |
| --- | --- |
| ID của slot, sản phẩm hoặc khách hàng | Có thể giữ trong flow scope; kiểm tra quyền và tồn tại lại khi dùng |
| Lựa chọn người dùng đã nhập | Giữ trong form DTO/draft thuộc flow scope |
| Giá/availability có thể thay đổi | Đọc lại hoặc xác minh version khi xác nhận |
| Entity ORM đang được quản lý | Không giữ kỳ vọng entity vẫn managed qua nhiều request |
| Dữ liệu lớn hoặc nhạy cảm | Tránh lưu nguyên object trong execution snapshot; lưu ID và tải lại khi cần |
| Kết quả đã commit | Lưu ID nghiệp vụ và đọc từ database khi hiển thị |
| Thông tin chỉ phục vụ một lần render | Dùng request/view scope hoặc tính lại |

### 3.1. Giữ ID và dữ liệu nhập, không giữ một entity managed

Flow scope tồn tại lâu hơn một transaction. Entity JPA/Hibernate được tải trong một persistence context có thể trở thành detached sau khi transaction/request kết thúc.

Ví dụ không nên dựa vào:

~~~java
// Không nên coi entity này vẫn managed ở request sau.
flowScope.put("product", managedProductEntity);
~~~

Ở request sau:

- Entity có thể đã detached.
- Quan hệ lazy có thể không tải được khi persistence context đã đóng.
- Dữ liệu entity có thể đã cũ so với database.
- Snapshot serialization có thể gặp vấn đề nếu object graph phức tạp.

Thay vào đó, giữ ID và một DTO nhỏ:

~~~java
public class BookingDraft implements Serializable {
    private String slotId;
    private String customerId;
    private Integer attendeeCount;
    private String requestId;
    private Long expectedSlotVersion;

    // getters/setters
}
~~~

Ở request xác nhận, service tải lại entity bằng ID và kiểm tra trạng thái hiện tại. DTO chỉ chứa dữ liệu cần để mô tả ý định của người dùng.

### 3.2. Không tin dữ liệu từ flow scope như dữ liệu đã được xác thực

Flow scope là nơi giữ dữ liệu trong execution, không phải ranh giới bảo mật hay nguồn dữ liệu chuẩn.

Trước khi dùng ID, giá hoặc số lượng để ghi dữ liệu, service phải:

- Xác minh người dùng hiện tại có quyền thao tác trên tài nguyên.
- Tải dữ liệu authoritative từ database.
- Tính lại giá/tổng tiền từ nguồn tin cậy.
- Kiểm tra trạng thái và điều kiện hiện tại.
- Bỏ qua các giá trị client có thể sửa trái phép.

## 4. Đọc dữ liệu ở từng state

Một flow đặt lịch có thể đọc dữ liệu ở các thời điểm khác nhau:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="loadOptions">

    <action-state id="loadOptions">
        <evaluate expression="bookingAction.loadOptions(flowRequestContext)"/>
        <transition on="success" to="chooseSlot"/>
    </action-state>

    <view-state id="chooseSlot" view="booking/choose-slot">
        <transition on="next" to="loadReview"/>
    </view-state>

    <action-state id="loadReview">
        <evaluate expression="bookingAction.loadReview(flowScope.bookingDraft)"/>
        <transition on="success" to="review"/>
        <transition on="slotUnavailable" to="chooseSlot"/>
    </action-state>

    <view-state id="review" view="booking/review">
        <transition on="confirm" to="confirmBooking"/>
    </view-state>

    <action-state id="confirmBooking">
        <evaluate expression="bookingAction.confirm(flowScope.bookingDraft)"/>
        <transition on="confirmed" to="completed"/>
        <transition on="conflict" to="loadReview"/>
    </action-state>

    <end-state id="completed" view="booking/completed"/>
</flow>
~~~

Đây là flow minh họa. Các bean và view phải được đăng ký trong ứng dụng; tên event và transition phải khớp với kết quả Action.

### 4.1. Đọc danh sách để hiển thị

`loadOptions` có thể truy vấn các slot đang mở và trả về DTO cho view. Transaction đọc kết thúc sau khi service trả kết quả.

### 4.2. Đọc lại trước khi review

Khi người dùng chọn một slot, `loadReview` tải lại chi tiết slot, giá và điều kiện. Nếu slot đã không còn khả dụng, flow quay về bước chọn.

### 4.3. Xác nhận là một thao tác kiểm tra và ghi mới

Không dùng dữ liệu availability từ `loadOptions` làm bằng chứng rằng slot vẫn trống ở request confirm. `confirmBooking` phải gọi service có transaction mới, kiểm tra điều kiện và ghi kết quả nguyên tử.

## 5. Thiết kế service đọc dữ liệu với transaction ngắn

Một service có thể dùng `@Transactional(readOnly = true)` cho truy vấn chỉ đọc:

~~~java
@Service
public class BookingQueryService {

    private final SlotRepository slotRepository;

    public BookingQueryService(SlotRepository slotRepository) {
        this.slotRepository = slotRepository;
    }

    @Transactional(readOnly = true)
    public SlotReviewDto loadReview(String slotId) {
        Slot slot = slotRepository.findById(slotId)
                .orElseThrow(SlotNotFoundException::new);

        return new SlotReviewDto(
                slot.getId(),
                slot.getStartAt(),
                slot.getPrice(),
                slot.getVersion(),
                slot.isAvailable());
    }
}
~~~

`readOnly = true` là metadata/hint cho transaction manager và persistence provider. Nó không thay thế kiểm tra quyền, không đảm bảo mọi database cấm ghi, và không tự tạo snapshot nhất quán xuyên nhiều request.

### 5.1. Dùng DTO/projection để đọc vừa đủ

Không cần tải toàn bộ entity graph nếu trang review chỉ hiển thị giờ, giá và trạng thái:

~~~java
public record SlotReviewDto(
        String slotId,
        Instant startAt,
        BigDecimal price,
        long version,
        boolean available) {
}
~~~

DTO giúp giảm dữ liệu đọc và truyền qua flow, tránh phụ thuộc lazy association sau transaction, tách model giao diện khỏi entity persistence và ghi nhận version để phát hiện thay đổi sau đó.

Nếu dự án dùng Java trước record, có thể tạo class DTO thông thường.

## 6. Xác minh dữ liệu lại khi người dùng xác nhận

Ví dụ trang review hiển thị:

~~~text
Khung giờ: 10:00 - 10:30
Giá: 250.000 VND
Trạng thái: Còn chỗ
~~~

Đây là dữ liệu được đọc tại thời điểm render. Nó có thể thay đổi trước khi người dùng submit.

Service xác nhận phải tự tải lại dữ liệu:

~~~java
@Service
public class BookingCommandService {

    private final SlotRepository slotRepository;
    private final BookingRepository bookingRepository;

    public BookingCommandService(
            SlotRepository slotRepository,
            BookingRepository bookingRepository) {
        this.slotRepository = slotRepository;
        this.bookingRepository = bookingRepository;
    }

    @Transactional
    public BookingConfirmation confirm(
            String slotId,
            String customerId,
            String requestId,
            long expectedVersion) {

        Slot slot = slotRepository.findById(slotId)
                .orElseThrow(SlotNotFoundException::new);

        if (slot.getVersion() != expectedVersion) {
            throw new SlotChangedException();
        }

        if (!slot.isAvailable()) {
            throw new SlotUnavailableException();
        }

        slot.reserve();
        Booking booking = Booking.create(slot, customerId, requestId);
        bookingRepository.save(booking);
        return BookingConfirmation.from(booking);
    }
}
~~~

Ví dụ này minh họa luồng kiểm tra. Trong ứng dụng có concurrency thực, chỉ đọc version rồi kiểm tra trong Java vẫn chưa đủ nếu một transaction khác có thể ghi giữa bước đọc và commit. Cần optimistic locking ở ORM, conditional update hoặc pessimistic lock phù hợp để phép kiểm tra và ghi được bảo vệ.

### 6.1. Tính lại giá ở server

Nếu người dùng gửi giá từ browser hoặc flow scope, service không được tin giá đó khi tạo booking. Hãy tải bảng giá hiện hành từ database hoặc pricing service, tính lại tổng và lưu snapshot giá được áp dụng trong booking.

Nếu giá thay đổi, trả outcome như `priceChanged` để flow hiển thị mức giá mới và yêu cầu người dùng xác nhận lại.

### 6.2. Kiểm tra ownership và quyền

Không chỉ xác minh slot còn trống. Service cần xác minh customer/draft thuộc principal hiện tại. Không cho phép sửa customer ID trong form để đặt lịch thay người dùng khác nếu nghiệp vụ không cho phép.

## 7. Optimistic locking với version

Khi nhiều người đọc cùng một dữ liệu và xác suất xung đột thấp, optimistic locking là lựa chọn phù hợp. Entity có version:

~~~java
@Entity
public class Slot {

    @Id
    private String id;

    private boolean available;

    @Version
    private long version;

    public void reserve() {
        if (!available) {
            throw new SlotUnavailableException();
        }
        available = false;
    }
}
~~~

Khi ORM cập nhật entity, version được dùng để phát hiện một transaction khác đã sửa bản ghi. Nếu có xung đột, persistence provider có thể ném optimistic locking exception khi flush/commit.

### 7.1. Vì sao version phải được kiểm tra ở lúc ghi?

Giả sử hai transaction cùng đọc:

~~~text
Slot 10:00, version = 7, available = true
~~~

Hai người cùng xác nhận:

~~~text
Transaction A: đọc version 7
Transaction B: đọc version 7
Transaction A: reserve và commit version 8
Transaction B: cố cập nhật với version 7
Transaction B: optimistic lock conflict
~~~

Chỉ một transaction có thể cập nhật theo version cũ. Request còn lại cần xử lý conflict và yêu cầu người dùng chọn lại.

### 7.2. Không giữ entity/version như sự thật duy nhất

Flow scope có thể giữ `expectedVersion` để phát hiện trang review đã cũ. Nhưng việc lưu version trong DTO không tự bảo vệ database. Bảo vệ thực sự phải nằm ở câu lệnh update/flush/commit có điều kiện.

### 7.3. Xử lý conflict thành Event

Action có thể chuyển optimistic locking conflict thành một outcome nghiệp vụ có thể hiển thị:

~~~java
public String confirm(BookingDraft draft) {
    try {
        bookingCommandService.confirm(
                draft.getSlotId(),
                draft.getCustomerId(),
                draft.getRequestId(),
                draft.getExpectedSlotVersion());
        return "confirmed";
    } catch (OptimisticLockingFailureException
             | SlotChangedException ex) {
        return "conflict";
    }
}
~~~

Đây là ví dụ khái niệm. Cần bắt đúng exception thực tế của persistence provider/Spring Data và bảo đảm transaction đã rollback trước khi flow tiếp tục. Nếu transaction đã đánh dấu rollback-only, không tiếp tục dùng cùng transaction để ghi thêm dữ liệu.

Flow có thể:

~~~xml
<action-state id="confirmBooking">
    <evaluate expression="bookingAction.confirm(flowScope.bookingDraft)"/>
    <transition on="confirmed" to="completed"/>
    <transition on="conflict" to="loadReview"/>
</action-state>
~~~

Khi conflict, `loadReview` tải lại giá và availability. View cần giải thích điều gì đã thay đổi và yêu cầu người dùng xác nhận lại nếu cần.

## 8. Pessimistic locking khi cần bảo vệ tài nguyên ngắn hạn

Với tài nguyên khan hiếm hoặc xung đột thường xuyên, có thể dùng pessimistic lock trong transaction xác nhận:

~~~java
public interface SlotRepository extends JpaRepository<Slot, String> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from Slot s where s.id = :id")
    Optional<Slot> findByIdForUpdate(@Param("id") String id);
}
~~~

Service:

~~~java
@Transactional
public BookingConfirmation confirm(String slotId, String requestId) {
    Slot slot = slotRepository.findByIdForUpdate(slotId)
            .orElseThrow(SlotNotFoundException::new);

    if (!slot.isAvailable()) {
        throw new SlotUnavailableException();
    }

    slot.reserve();
    return bookingRepository.save(
            Booking.create(slot, requestId)).toConfirmation();
}
~~~

Pessimistic lock giữ row lock trong transaction hiện tại. Transaction phải ngắn, không chờ người dùng hoặc remote API trong lúc giữ khóa.

### 8.1. Không khóa row khi render review rồi giữ qua request sau

Không mở transaction để lấy `PESSIMISTIC_WRITE`, render view và chờ người dùng nhấn Confirm. Làm vậy sẽ giữ khóa trong thời gian không xác định.

Nếu cần đảm bảo một slot được giữ trong vài phút, hãy dùng reservation hold có trạng thái và thời hạn trong database, không dùng transaction dài.

### 8.2. Chọn optimistic hay pessimistic

| Tiêu chí | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Xung đột | Phát hiện khi ghi | Chặn transaction khác |
| Phù hợp | Đọc nhiều, ghi ít, xung đột thấp | Tài nguyên nóng, cần serialize ngắn |
| Tác động | Có thể rollback và yêu cầu thử lại | Có thể tăng wait/deadlock |
| Thời gian giữ khóa | Không giữ row lock xuyên toàn bộ lần đọc | Giữ trong transaction |
| Yêu cầu | Version hoặc conditional update | Database hỗ trợ locking semantics |

Không có lựa chọn luôn tốt hơn. Đo tỷ lệ conflict, latency và tải database để chọn.

## 9. Reservation hold khi cần giữ tài nguyên trong lúc người dùng xác nhận

Đôi khi nghiệp vụ yêu cầu không chỉ đọc availability mà còn giữ chỗ tạm thời. Ví dụ người dùng cần 5 phút để hoàn tất thanh toán.

~~~text
AVAILABLE
   |
   | create hold
   v
HELD (expiresAt)
   |               \
   | confirm        \ timeout/expire
   v                 v
CONFIRMED          AVAILABLE
~~~

Hold là một bản ghi nghiệp vụ có thời hạn:

~~~java
public class ReservationHold {
    private String holdId;
    private String slotId;
    private String ownerId;
    private Instant expiresAt;
    private HoldStatus status;
}
~~~

Khi người dùng chọn slot:

1. Service tạo hold trong transaction ngắn.
2. Database đánh dấu slot hoặc capacity đã được giữ.
3. Flow scope lưu `holdId`, không giữ row lock.
4. Người dùng xem review và hoàn tất bước tiếp theo.
5. Khi confirm, service kiểm tra hold còn hiệu lực và thuộc owner.
6. Nếu hợp lệ, chuyển hold thành confirmed trong transaction.
7. Nếu hết hạn, trả outcome `holdExpired` để người dùng chọn lại.

### 9.1. Hold cần được kiểm soát nguyên tử

Không tạo hold bằng cách SELECT số chỗ còn, tăng biến đếm trong Java rồi INSERT mà không có constraint/locking. Hai request đồng thời có thể cùng nhìn thấy một chỗ còn trống. Cần update có điều kiện, unique constraint, row lock hoặc chiến lược atomic phù hợp để tổng số hold/booking không vượt capacity.

### 9.2. Hold cần hết hạn và được dọn dẹp

Một hold có thể bị bỏ dở khi người dùng đóng browser. Hệ thống cần:

- `expiresAt` rõ ràng.
- Kiểm tra hết hạn ngay tại thao tác confirm.
- Job dọn hold hết hạn hoặc logic giải phóng khi truy cập.
- Xử lý trường hợp job chạy trễ.
- Đảm bảo hold hết hạn không còn chiếm capacity theo quy tắc database.

Không chỉ dựa vào scheduler để xác định hold còn hiệu lực. Confirm phải tự kiểm tra thời hạn trong transaction.

### 9.3. Thời hạn hiển thị không thay thế thời hạn ở server

Countdown trên browser chỉ là gợi ý giao diện. Đồng hồ client có thể sai hoặc bị sửa. Server/database mới quyết định hold còn hiệu lực dựa trên thời gian tin cậy.

## 10. Transaction boundary khi đọc nhiều nguồn dữ liệu

Một trang review có thể cần dữ liệu từ nhiều service: slot/availability, giá, thông tin khách hàng, chính sách hủy, thuế/phí. Không phải lúc nào cũng cần một transaction database duy nhất cho mọi nguồn. Cần xác định yêu cầu nhất quán.

### 10.1. Dữ liệu chỉ để hiển thị

Có thể đọc từng nguồn bằng query ngắn và tạo Review DTO. Trang review nên thể hiện thời điểm hoặc phiên bản dữ liệu khi điều đó có ý nghĩa.

### 10.2. Dữ liệu quyết định quyền ghi

Availability, capacity, giá được áp dụng và trạng thái account cần được xác minh lại trong transaction xác nhận hoặc bằng một snapshot/version có hợp đồng rõ.

### 10.3. Dữ liệu đến từ remote service

Không giữ transaction database trong khi gọi remote API lâu. Nếu phải phối hợp nhiều hệ thống, cân nhắc lưu yêu cầu pending rồi xử lý nền, reservation/hold có hạn dùng, saga/workflow nghiệp vụ, outbox/inbox hoặc reconciliation khi timeout khiến kết quả chưa rõ.

Một transaction database cục bộ không thể tự đảm bảo atomicity với một HTTP API bên ngoài.

## 11. Isolation level và ý nghĩa khi đọc qua nhiều request

Isolation level quy định transaction đồng thời nhìn thấy thay đổi của nhau ra sao. Nhưng transaction isolation không kéo dài qua hai HTTP request độc lập.

| Isolation | Khái quát |
| --- | --- |
| READ_UNCOMMITTED | Có thể đọc dữ liệu chưa commit nếu database hỗ trợ |
| READ_COMMITTED | Chỉ đọc dữ liệu đã commit; mỗi query có thể thấy commit mới |
| REPEATABLE_READ | Trong một transaction, lần đọc lặp có thể thấy cùng giá trị theo semantics database |
| SERIALIZABLE | Cung cấp mức cô lập mạnh hơn, có thể tăng contention/retry |

Ngay cả khi request A chạy ở `REPEATABLE_READ`, request B sau vài phút là transaction mới. Nó không tự dùng snapshot của transaction A.

### 11.1. Không dùng isolation level để giữ dữ liệu nhất quán xuyên thời gian người dùng suy nghĩ

Muốn giữ một giá trị đã được chốt, hãy tạo snapshot nghiệp vụ rõ ràng:

- Báo giá có `quoteId`, version và hạn hiệu lực.
- Reservation hold có `holdId` và `expiresAt`.
- Đơn hàng lưu giá/thuế được áp dụng tại thời điểm xác nhận.

Snapshot nghiệp vụ có quy tắc và vòng đời; nó khác với transaction snapshot của database.

### 11.2. Chọn isolation theo invariant

Ví dụ invariant “không được đặt vượt capacity” phải được bảo vệ bằng cơ chế database/transaction phù hợp, không chỉ bằng việc đọc số chỗ còn trống. Có thể dùng conditional update, unique constraint, row lock hoặc serializable transaction tùy mô hình dữ liệu.

## 12. Idempotency khi người dùng xác nhận nhiều lần

Người dùng có thể double-click, refresh sau khi response mất, nhấn Back rồi submit lại, mở hai tab cùng một draft hoặc gửi lại request sau timeout.

Một request có thể đã commit dù browser không nhận được response. Nếu Action gọi lại service mà không có idempotency, hệ thống có thể tạo booking/order thứ hai.

### 12.1. Tạo request ID cho ý định nghiệp vụ

Khi bắt đầu draft, tạo một request ID ổn định:

~~~java
String requestId = UUID.randomUUID().toString();
draft.setRequestId(requestId);
~~~

Request ID phải gắn với một ý định nghiệp vụ, được giữ qua các request và không được tạo lại mỗi lần nhấn Confirm.

### 12.2. Unique constraint là lớp bảo vệ cuối

Ví dụ schema:

~~~sql
CREATE TABLE booking (
    id            VARCHAR(64) PRIMARY KEY,
    request_id    VARCHAR(64) NOT NULL,
    slot_id       VARCHAR(64) NOT NULL,
    customer_id   VARCHAR(64) NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    CONSTRAINT uq_booking_request UNIQUE (request_id)
);
~~~

Khi hai request cùng insert request ID, database chỉ cho phép một bản ghi. Service bắt duplicate-key theo đúng transaction/provider và đọc lại booking đã tạo để trả cùng kết quả.

### 12.3. Không dùng execution key làm request ID

Flow execution có thể kết thúc hoặc được khởi tạo lại. Request ID nghiệp vụ cần tồn tại qua retry và có thể được tra cứu độc lập với flow. Hai loại key có vòng đời khác nhau.

## 13. Dữ liệu thay đổi và trải nghiệm người dùng

Nếu xác nhận phát hiện dữ liệu đã thay đổi, không nên chỉ trả lỗi kỹ thuật chung chung.

~~~text
Trang review:
  10:00 - 10:30
  250.000 VND

Khi xác nhận:
  slot đã được người khác đặt

Kết quả:
  "Khung giờ này vừa không còn trống.
   Vui lòng chọn một khung giờ khác."
~~~

Các outcome có thể:

| Outcome | Hành vi flow |
| --- | --- |
| confirmed | Đi tới trang hoàn tất |
| slotUnavailable | Quay về chọn slot |
| priceChanged | Tải lại giá và yêu cầu xác nhận lại |
| holdExpired | Giải thích hold hết hạn và chọn lại |
| customerChanged | Làm mới thông tin khách hàng |
| conflict | Tải lại review và cho người dùng quyết định |

### 13.1. Không tự động chấp nhận thay đổi giá

Nếu giá tăng sau khi review, không tự động tạo booking với giá mới mà không thông báo. Hiển thị giá mới và yêu cầu người dùng xác nhận lại theo quy tắc sản phẩm.

### 13.2. Không khôi phục form bằng dữ liệu cũ một cách mù quáng

Khi quay lại review, giữ lựa chọn người dùng còn hợp lệ, nhưng tải lại dữ liệu authoritative. Phân biệt dữ liệu người dùng nhập cần giữ, dữ liệu hệ thống cần làm mới và dữ liệu đã hết hiệu lực cần loại bỏ.

## 14. Action điều phối việc đọc và xác nhận

POJO action có thể gọi query service và command service:

~~~java
public class BookingAction {

    private final BookingQueryService queryService;
    private final BookingCommandService commandService;

    public BookingAction(
            BookingQueryService queryService,
            BookingCommandService commandService) {
        this.queryService = queryService;
        this.commandService = commandService;
    }

    public String loadReview(BookingDraft draft,
                            RequestContext context) {
        SlotReviewDto review = queryService.loadReview(draft.getSlotId());

        context.getFlowScope().put("slotReview", review);
        draft.setExpectedSlotVersion(review.version());
        return review.available() ? "success" : "slotUnavailable";
    }

    public String confirm(BookingDraft draft) {
        try {
            commandService.confirm(
                    draft.getSlotId(),
                    draft.getCustomerId(),
                    draft.getRequestId(),
                    draft.getExpectedSlotVersion());
            return "confirmed";
        } catch (SlotUnavailableException
                 | SlotChangedException ex) {
            return "conflict";
        }
    }
}
~~~

Đây là ví dụ cấu trúc; cần bổ sung kiểm tra principal/ownership và xử lý idempotency ở service. Không coi việc Action nhận BookingDraft từ flow scope là bằng chứng draft hợp lệ.

### 14.1. Action không sở hữu transaction dài

Query service có transaction đọc riêng; command service có transaction ghi riêng. Action chỉ gọi các phương thức này và ánh xạ kết quả thành Event. Tránh đặt transaction trên một phương thức điều phối kéo dài qua nhiều thao tác hoặc cố giữ transaction trong flow execution.

### 14.2. Tránh gọi service từ biểu thức view nhiều lần

Nếu biểu thức EL trong view hoặc on-render gọi query nặng, mỗi lần render/refresh có thể lặp truy vấn. Tập trung đọc ở action phù hợp hoặc dùng cache có invalidation rõ, và đo số query trên mỗi request.

## 15. Kiểm thử dữ liệu qua nhiều request

Một unit test service xác minh transaction logic chưa đủ. Cần kiểm thử toàn bộ khoảng cách giữa request đọc và request ghi.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Đọc slot rồi xác nhận ngay | Booking được tạo khi điều kiện vẫn đúng |
| Đọc slot, người khác đặt trước | Confirm trả conflict, không ghi trùng |
| Giá thay đổi giữa review và confirm | Người dùng thấy giá mới và xác nhận lại |
| Hold hết hạn trước confirm | Confirm từ chối hold cũ |
| Hai request confirm cùng request ID | Chỉ một booking được tạo |
| Hai request confirm khác request ID cùng slot | Capacity không bị vượt |
| Session/flow execution hết hạn | Không làm mất dữ liệu nghiệp vụ đã commit |
| Customer ID bị sửa trong request | Ownership check từ chối |
| Remote service timeout | Trạng thái pending/unknown được đối soát |
| Entity lazy được dùng ở request sau | Không phụ thuộc persistence context cũ |

### 15.1. Integration test hai request

~~~text
start booking flow
request 1: load slots and review

external actor:
  reserve the selected slot and commit

request 2: submit confirm using the old review data

assert:
  no second booking is created
  result is conflict or slotUnavailable
  flow returns to a state that can reload availability
~~~

Test phải sử dụng database transaction độc lập cho external actor; nếu test giữ một transaction cha chưa commit, request flow có thể không nhìn thấy thay đổi theo isolation của test.

### 15.2. Test optimistic locking

1. Hai transaction cùng tải một entity version N.
2. Transaction A cập nhật và commit.
3. Transaction B cập nhật entity cũ.
4. Xác minh B gặp optimistic locking conflict.
5. Xác minh transaction B rollback.
6. Xác minh Action chuyển conflict thành Event phù hợp.

### 15.3. Test reservation hold

- Hold được tạo và gắn owner.
- Hold còn hiệu lực thì confirm thành công.
- Hold hết hạn thì confirm không tạo booking.
- Hai request cùng confirm một hold chỉ tạo một booking.
- Job cleanup không giải phóng hold đã confirmed.

## 16. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Trang review hiển thị availability cũ | Không đọc lại trước confirm | Kiểm tra thời điểm query và version |
| LazyInitializationException | Entity detached sau request | Dùng DTO/ID và tải lại trong service |
| Optimistic lock conflict | Entity đã bị transaction khác sửa | Đọc version, retry/reload có giới hạn |
| Đặt vượt capacity | Chỉ kiểm tra bằng Java trước khi insert | Conditional update/constraint/lock |
| Transaction timeout | Transaction quá dài hoặc lock wait | Đo transaction duration và DB wait |
| Giá bị sửa từ client | Tin giá trong flow/request | Tính lại giá ở server |
| Booking bị tạo trùng | Thiếu idempotency | Request ID + unique constraint |
| Hold vẫn chiếm chỗ sau timeout | Cleanup/expiry không nhất quán | Kiểm tra expiresAt và trạng thái |
| Flow scope quá lớn | Lưu entity graph hoặc dữ liệu không cần | Giữ DTO/ID tối thiểu |
| Request sau không thấy dữ liệu mới | Cách hiểu sai transaction snapshot/cache | Kiểm tra transaction mới, cache và isolation |

### 16.1. Phân biệt dữ liệu cũ và transaction rollback

Một trang review hiển thị giá cũ không có nghĩa transaction xác nhận đã rollback. Có thể trang chỉ đang dùng DTO đã lưu trong flow scope. Tải lại từ service để xác định giá hiện hành.

### 16.2. Không retry mù khi commit chưa rõ

Nếu client timeout sau khi gửi confirm, không biết chắc server đã commit hay chưa. Tra cứu theo request ID trước khi retry. Service idempotent sẽ trả lại kết quả đã có nếu thao tác trước đó thành công.

## 17. Vận hành và quan sát transaction

Theo dõi:

- Thời gian query ở mỗi state.
- Số lần đọc lặp lại cùng dữ liệu.
- Transaction duration của query/command service.
- Tỷ lệ optimistic lock conflict.
- Tỷ lệ slot unavailable tại bước confirm.
- Số hold được tạo, xác nhận và hết hạn.
- Số duplicate request ID.
- Connection pool utilization và database lock wait.
- Tỷ lệ request timeout sau khi command đã được gửi.

### 17.1. Log theo correlation ID

~~~text
flowId=booking
stateId=confirmBooking
requestId=...
slotVersionExpected=7
slotVersionCurrent=8
outcome=conflict
correlationId=...
~~~

Không log thông tin cá nhân, token hoặc toàn bộ flow scope. Request ID nên là mã kỹ thuật không chứa dữ liệu khách hàng.

### 17.2. Cảnh báo conflict tăng cao

Nếu conflict tăng, có thể có nhiều người cùng chọn một tài nguyên nóng, review tồn tại quá lâu trước khi confirm, cache availability quá lâu, action đọc dữ liệu không đúng thời điểm hoặc một tác vụ nền cập nhật cùng entity thường xuyên.

Không tắt optimistic locking để giảm số lỗi hiển thị. Xác định nguyên nhân cạnh tranh và cải thiện trải nghiệm chọn lại/hold.

## 18. Bài thực hành: xác nhận một slot sau nhiều request

Xây dựng flow:

~~~text
loadOptions → chooseSlot → loadReview → review → confirmBooking
                                             |             |
                                             |             +→ confirmed → completed
                                             |             +→ conflict → loadReview
                                             |
                                             +→ back → chooseSlot
~~~

**Yêu cầu:**

1. Tạo BookingDraft chỉ giữ ID, lựa chọn người dùng, request ID và expected version.
2. Tạo query service dùng transaction đọc ngắn và trả SlotReviewDto.
3. Tạo command service dùng transaction ghi riêng.
4. Dùng @Version hoặc conditional update để bảo vệ slot.
5. Xử lý conflict thành Event conflict.
6. Khi conflict, tải lại review và hiển thị thay đổi cho người dùng.
7. Không giữ JPA entity managed trong flow scope qua các request.
8. Tạo request ID ổn định và unique constraint chống booking trùng.
9. Nếu nghiệp vụ cần giữ chỗ, tạo ReservationHold có expiresAt.
10. Kiểm thử một actor khác đặt slot giữa hai request.
11. Kiểm thử hai request confirm đồng thời.
12. Kiểm thử timeout sau commit bằng cách tra cứu request ID.
13. Đo transaction duration, query count và conflict rate.

**Bảng kết quả:**

| Hạng mục | Kết quả mong đợi |
| --- | --- |
| Dữ liệu trong flow scope | DTO/ID tối thiểu |
| Transaction đọc | Ngắn, kết thúc trước khi render/chờ người dùng |
| Transaction xác nhận | Kiểm tra và ghi trong cùng ranh giới bảo vệ |
| Dữ liệu thay đổi | Conflict/priceChanged/slotUnavailable rõ ràng |
| Optimistic locking | Phát hiện cập nhật cạnh tranh |
| Idempotency | Một request ID chỉ tạo một booking |
| Reservation hold | Có owner, expiresAt và cleanup |
| Retry sau timeout | Tra cứu kết quả trước, không ghi trùng |

**Tiêu chí đạt:** dữ liệu được đọc lại ở thời điểm cần thiết; transaction không kéo dài qua thời gian người dùng suy nghĩ; tài nguyên không bị đặt vượt capacity; dữ liệu flow không chứa entity managed cũ; người dùng nhận được thông báo rõ khi điều kiện thay đổi.

## 19. Tổng kết và câu hỏi tự kiểm tra

Một flow nhiều bước có thể đọc dữ liệu trong request đầu, giữ lựa chọn trong flow scope và xác nhận trong request sau. Vì thời gian giữa hai request không bị giới hạn, dữ liệu đọc trước có thể đã cũ. Hãy giữ DTO/ID nhỏ trong flow scope, tải lại dữ liệu authoritative ở service và kiểm tra quyền, availability, giá và version tại thời điểm xác nhận.

Mỗi request nên có transaction ngắn. Dùng optimistic locking hoặc conditional update để phát hiện xung đột; dùng pessimistic lock trong transaction ngắn khi cần; dùng reservation hold có hạn dùng nếu nghiệp vụ thực sự cần giữ tài nguyên trong lúc người dùng suy nghĩ. Idempotency và unique constraint bảo vệ thao tác ghi khi request bị gửi lại. Transaction isolation không giữ snapshot xuyên nhiều HTTP request, và entity ORM không nên được coi là managed qua các request.

**Câu hỏi tự kiểm tra:**

1. Vì sao không nên giữ một database transaction trong toàn bộ flow execution?
2. Flow scope và persistence context có vòng đời khác nhau như thế nào?
3. Vì sao nên giữ ID/DTO thay vì entity ORM trong flow scope?
4. Dữ liệu nào cần được đọc lại khi người dùng nhấn Confirm?
5. @Transactional(readOnly = true) có bảo đảm dữ liệu không thay đổi giữa các request không?
6. Optimistic locking phát hiện xung đột bằng cách nào?
7. Vì sao kiểm tra version trong Java mà không có cơ chế bảo vệ lúc ghi vẫn có race condition?
8. Khi nào nên dùng pessimistic lock?
9. Reservation hold khác việc giữ transaction/row lock trong lúc người dùng suy nghĩ ra sao?
10. Vì sao transaction isolation không tạo snapshot chung cho hai request cách nhau vài phút?
11. Idempotency key khác execution key ở điểm nào?
12. Cần kiểm thử những tình huống nào để chứng minh confirm không dùng dữ liệu cũ và không tạo booking trùng?

## Tài liệu tham khảo

- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Web Flow 2.5.x Reference Guide](https://docs.spring.io/spring-webflow/docs/2.5.x/reference/html/)
