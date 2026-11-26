# Kiểm soát khóa khi nhiều yêu cầu dùng cùng execution

> **Chương:** Hiệu năng và vận hành  
> **Module:** SPRING_WEB_FLOW  
> **Mục tiêu:** Hiểu vì sao một FlowExecution cần được bảo vệ khi nhiều HTTP request cùng truy cập; nắm vai trò của FlowExecutionLock và repository; xử lý double-click, AJAX, nhiều tab, request lặp và snapshot cũ; phân biệt khóa execution với transaction, khóa database và idempotency; đo lường contention và kiểm thử concurrency.

## 1. Tình huống: hai request cùng tiếp tục một flow

Một người dùng đang ở bước xác nhận lịch hẹn:

~~~text
chooseSlot → contact → review → reserve → completed
~~~

Trình duyệt gửi request tiếp tục flow với cùng execution context. Điều này có thể xảy ra khi:

- Người dùng nhấn nút **Xác nhận** hai lần rất nhanh.
- JavaScript gửi AJAX trong khi form cũng submit.
- Người dùng mở cùng một URL flow ở hai tab.
- Một request bị chậm, người dùng nhấn lại vì nghĩ lần đầu không có tác dụng.
- Proxy/client retry request sau timeout.
- Một thao tác polling hoặc autosave vô tình dùng cùng execution.

Nếu hai thread cùng đọc và thay đổi một FlowExecution mà không có cơ chế đồng bộ, có thể xảy ra:

- Cả hai cùng thấy current state là review.
- Cả hai cùng chạy action reserve.
- Một request chuyển state trong khi request kia vẫn đang đọc dữ liệu cũ.
- Snapshot bị ghi đè hoặc execution được lưu ở trạng thái không nhất quán.
- Action ghi nghiệp vụ được gọi nhiều lần.
- Event đến sai state hoặc request thứ hai dùng dữ liệu đã lỗi thời.

FlowExecution chứa trạng thái có thể thay đổi trong lúc xử lý request. Vì vậy, **việc truy cập đồng thời vào cùng execution phải được kiểm soát**.

## 2. FlowExecution không phải đối tượng dùng chung an toàn cho nhiều thread

Một FlowDefinition thường được dùng chung để tạo nhiều execution. Mỗi FlowExecution là một lần chạy có state, scope và dữ liệu riêng.

~~~text
FlowDefinition: booking
  ├─ Execution A: review
  ├─ Execution B: chooseSlot
  └─ Execution C: contact
~~~

Các execution A, B và C độc lập về mặt vòng đời. Nhưng nếu hai request cùng tiếp tục execution A, chúng có thể cùng tác động đến một state machine và dữ liệu flow.

### 2.1. Hai request khác nhau không nhất thiết là hai execution khác nhau

Ví dụ:

~~~http
POST /booking?execution=e1s4
_eventId=confirm
~~~

~~~http
POST /booking?execution=e1s4
_eventId=confirm
~~~

Hai request có thể được gửi từ hai click hoặc hai tab. Chúng cùng mang execution key minh họa e1s4, vì vậy có thể nhắm tới cùng ngữ cảnh execution/snapshot theo repository.

Ngược lại, hai request tới cùng Flow ID booking nhưng có execution key khác có thể thuộc hai lần chạy khác nhau. Không dùng Flow ID để suy ra chúng cần cùng một khóa.

### 2.2. Phạm vi đồng bộ cần đủ hẹp

Mục tiêu là bảo vệ cùng execution khi cần, trong khi những execution độc lập vẫn có thể chạy song song.

~~~mermaid
flowchart TD
    A["HTTP requests"] --> B{"Execution identity"}
    B -->|"Execution A"| C["Lock A"]
    B -->|"Execution B"| D["Lock B"]
    C --> E["Request A1"]
    C --> F["Request A2 chờ"]
    D --> G["Request B1 chạy song song"]
    E --> H["Lưu execution A"]
    H --> F
    F --> I["Xử lý sau khi lấy được lock"]
~~~

Đây là mô hình khái niệm: các request cùng một execution cần được tuần tự hóa theo cơ chế repository/lock; request của execution khác không nên bị chặn bởi một khóa toàn cục không cần thiết.

## 3. FlowExecutionLock là gì?

Spring Web Flow có abstraction **FlowExecutionLock** để điều phối quyền truy cập đồng thời vào một flow execution. Lock được gắn với việc truy cập execution qua repository; nó giúp tránh nhiều thread cùng thao tác lên trạng thái mutable của cùng execution.

Trong API Web Flow, abstraction này thuộc package:

~~~java
org.springframework.webflow.execution.repository.FlowExecutionLock
~~~

Các thao tác cốt lõi của lock là:

~~~java
public interface FlowExecutionLock {
    void acquire();
    void release();
}
~~~

Đoạn trên minh họa hợp đồng khái niệm; khi viết code phụ thuộc trực tiếp vào API, hãy đối chiếu đúng chữ ký của phiên bản Spring Web Flow trong dự án.

### 3.1. Lock bảo vệ execution, không bảo vệ mọi dữ liệu của ứng dụng

FlowExecutionLock giúp điều phối truy cập execution. Nó không tự động khóa:

- Một booking được nhiều flow khác nhau cùng sửa.
- Một hàng tồn kho trong database.
- Một bean singleton dùng chung.
- Một file hoặc tài nguyên bên ngoài.
- Một service chạy trên node khác nếu lock chỉ có phạm vi JVM.

Các tài nguyên đó cần cơ chế đồng bộ phù hợp ở tầng sở hữu chúng, thường là transaction, constraint, lock database hoặc distributed coordination.

### 3.2. FlowExecutionRepository có vai trò gì?

FlowExecutionRepository chịu trách nhiệm tìm/lưu/khôi phục execution theo key và snapshot strategy. Cơ chế khóa gắn với repository để kiểm soát truy cập execution trong quá trình tiếp tục.

~~~text
HTTP request + execution key
        |
        v
FlowExecutor
        |
        v
FlowExecutionRepository
        |
        +--> lấy lock phù hợp
        |
        +--> khôi phục execution
        |
        +--> xử lý event/action/transition
        |
        +--> lưu snapshot hoặc cập nhật execution
        |
        +--> nhả lock
~~~

Chi tiết triển khai và thứ tự nội bộ phụ thuộc repository/phiên bản. Điểm cần giữ là execution phải được bảo vệ trong lúc framework thực hiện một thao tác tiếp tục có khả năng đọc/ghi state.

## 4. Vòng đời lock trong một request

Một request tiếp tục flow thường cần một vùng xử lý được đồng bộ:

~~~mermaid
sequenceDiagram
    participant R1 as Request 1
    participant R2 as Request 2
    participant L as Execution Lock
    participant Repo as FlowExecutionRepository
    participant E as FlowExecution
    R1->>L: acquire
    L-->>R1: granted
    R2->>L: acquire cùng execution
    Note over R2,L: Request 2 chờ hoặc xử lý theo chính sách lock
    R1->>Repo: restore/read execution
    Repo->>E: load state
    R1->>E: process event + transition
    R1->>Repo: save updated execution/snapshot
    R1->>L: release
    L-->>R2: granted
    R2->>Repo: tiếp tục theo trạng thái repository hiện tại
    R2->>L: release khi hoàn tất
~~~

Trong mô hình này, request thứ hai không được tự ý sửa execution khi request thứ nhất đang ở trong vùng tới hạn.

### 4.1. Không giữ lock trong thời gian người dùng suy nghĩ

Người dùng có thể mất vài phút để điền form. Flow execution được lưu/tạm dừng giữa các request; execution lock không nên bị giữ trong toàn bộ thời gian người dùng đang đọc trang hoặc suy nghĩ.

Lock chỉ cần được giữ trong giai đoạn server xử lý request có liên quan đến execution. Không tạo một khóa dài hạn từ lúc render view cho đến lần submit tiếp theo.

### 4.2. Lock phải được nhả khi có exception

Nếu tự triển khai một lock wrapper, luôn bảo đảm release trong finally:

~~~java
FlowExecutionLock lock = repository.getLock(executionKey);
lock.acquire();
try {
    processRequest();
} finally {
    lock.release();
}
~~~

Đây là **pseudocode minh họa**, không phải lời khuyên tự gọi repository lock bên ngoài FlowExecutor. Trong ứng dụng bình thường, framework/repository đảm nhiệm việc lấy và nhả lock. Chỉ khi viết custom repository hoặc tích hợp đặc biệt mới cần triển khai contract này.

Nếu lock không được nhả khi exception xảy ra, request sau có thể chờ mãi hoặc bị từ chối vì contention.

### 4.3. Không tự khóa hai lần

Không tự gọi acquire trong action trong khi FlowExecutor đã lấy lock cho execution, trừ khi API/thiết kế custom lock yêu cầu rõ ràng. Khóa không reentrant có thể khiến cùng thread tự chờ chính nó.

Không gọi release nhiều lần hoặc nhả lock từ thread khác nếu implementation không cho phép.

## 5. Điều gì xảy ra khi double-click?

Giả sử người dùng đang ở state review:

~~~text
review --confirm--> reserve --booked--> completed
~~~

Hai request confirm đến gần như đồng thời:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as FlowExecutor
    participant L as Lock
    participant S as BookingService
    U->>B: Nhấn Confirm hai lần
    B->>F: POST confirm #1
    B->>F: POST confirm #2
    F->>L: Request #1 acquire
    L-->>F: granted
    F->>S: reserveOnce(requestId)
    S-->>F: booked
    F->>L: release
    F->>L: Request #2 acquire
    L-->>F: granted
    Note over F: Request #2 có thể gặp state/snapshot đã đổi
    F->>F: xử lý event theo repository hiện tại
~~~

Lock giúp hai request không cùng sửa execution tại một thời điểm. Nhưng **lock không đồng nghĩa request thứ hai tự động bị loại bỏ**.

Tùy snapshot strategy và repository, request thứ hai có thể:

- Thấy execution đã kết thúc.
- Không còn tìm thấy snapshot/key tương ứng.
- Khôi phục một continuation snapshot cũ.
- Gặp event không hợp lệ ở state hiện tại.
- Được xử lý theo chính sách continuation của ứng dụng.

Không nên dựa vào một kết quả cụ thể nếu chưa xác minh repository/version. Điều cần bảo đảm là service không tạo booking thứ hai khi cùng một ý định nghiệp vụ được gửi lại.

## 6. Khóa execution không thay thế idempotency

Đây là phân biệt quan trọng nhất:

| Cơ chế | Bảo vệ điều gì? | Phạm vi |
| --- | --- | --- |
| FlowExecutionLock | Truy cập đồng thời vào một FlowExecution | Một execution theo repository |
| Database transaction | Tính nguyên tử và nhất quán của thao tác dữ liệu | Các thay đổi trong transaction |
| Database row/unique lock | Cạnh tranh trên dữ liệu được bảo vệ | Bản ghi/constraint/tài nguyên |
| Idempotency key | Một ý định nghiệp vụ không tạo side effect lặp | Thao tác nghiệp vụ qua nhiều request/retry |
| Distributed lock | Đồng bộ tài nguyên dùng chung giữa nhiều process/node | Phạm vi cluster theo implementation |

Ví dụ: request đầu tiên commit booking nhưng response bị mất. Request thứ hai đến sau khi lock đã được nhả. Dù hai request không chạy đồng thời, thao tác đặt lịch vẫn có thể được gọi hai lần nếu service không nhận diện request ID.

### 6.1. Idempotency ở tầng service

Một service có thể nhận request ID ổn định:

~~~java
@Transactional
public ReservationResult reserveOnce(
        String requestId,
        AppointmentDraft draft,
        String principalId) {

    return reservationRepository.findByRequestId(requestId)
            .map(ReservationResult::alreadyCreated)
            .orElseGet(() -> createReservation(requestId, draft, principalId));
}
~~~

Đây là pseudocode. Mẫu đọc rồi ghi không tự chống được hai transaction đồng thời. Cần unique constraint trên request ID hoặc một cơ chế claim/idempotency record nguyên tử. Khi gặp duplicate key, service cần đọc lại kết quả đã tạo và trả cùng reservation.

### 6.2. Execution key không phải idempotency key

Execution key định vị flow execution/snapshot. Idempotency key định danh ý định nghiệp vụ. Một flow mới có execution key khác vẫn có thể tiếp tục cùng một thao tác nghiệp vụ nếu draft/request ID được giữ đúng.

Không dùng execution key làm khóa duy nhất của booking; cũng không dùng booking ID để khôi phục flow execution.

## 7. Snapshot và request cũ

Spring Web Flow có thể quản lý các continuation/snapshot của execution để hỗ trợ quay lại state trước đó theo repository strategy. Vì vậy, hai request có thể mang các key khác nhau nhưng liên quan đến cùng một flow execution, hoặc hai request cùng key có thể cạnh tranh trên một continuation cụ thể.

### 7.1. Phân biệt execution identity và snapshot identity

Ở mức khái niệm:

- **Execution identity:** xác định lần chạy flow.
- **Snapshot/continuation identity:** xác định một trạng thái có thể tiếp tục của execution.
- **Current state:** state hiện tại của execution đang được xử lý.

Định dạng key và cách repository quản lý continuation phụ thuộc implementation. Không tự parse chuỗi execution key để suy ra state hoặc thứ tự request.

### 7.2. Back không phải khóa ngược thời gian

Browser Back có thể gửi request dùng continuation snapshot cũ. Repository có thể cho phép tiếp tục snapshot đó hoặc từ chối tùy strategy, nhưng việc quay lại state cũ không tự rollback side effect đã commit.

Ví dụ:

~~~text
Snapshot S1: review
    |
    | confirm
    v
Snapshot S2: completed
~~~

Nếu người dùng mở lại S1, database vẫn có thể chứa booking được tạo ở lần confirm trước. Flow cần đối soát trạng thái nghiệp vụ trước khi cho phép một thao tác ghi mới.

## 8. Khi nào lock contention xảy ra?

Lock contention xuất hiện khi một request muốn truy cập execution đang được request khác giữ lock.

Các nguyên nhân thường gặp:

- Action gọi remote service chậm.
- Query database lâu.
- Code trong transition làm xử lý nặng.
- Một request giữ transaction lâu.
- Client gửi nhiều request song song từ cùng execution.
- Thread bị pause hoặc bị block trong I/O.
- Lock implementation có granularity quá rộng.

### 8.1. Không giữ lock trong công việc không cần thiết

Nếu action thực hiện:

~~~text
acquire execution lock
  -> gọi API bên ngoài mất 30 giây
  -> xử lý JSON lớn
  -> truy vấn nhiều bảng
  -> save execution
release lock
~~~

thì mọi request khác cần cùng execution có thể phải chờ trong thời gian dài.

Hãy:

- Giữ action ngắn.
- Tối ưu truy vấn.
- Đặt timeout cho remote call.
- Không làm tác vụ CPU nặng trong request nếu có thể xử lý nền.
- Tách công việc dài thành trạng thái pending và background job.

### 8.2. Không giữ transaction database qua thời gian người dùng nhập form

Flow execution tồn tại qua nhiều request, nhưng transaction nghiệp vụ nên ngắn và gắn với một thao tác server cụ thể. Không mở transaction khi render form rồi giữ cho đến khi người dùng nhấn Next sau vài phút.

Giữ transaction lâu làm tăng lock contention ở database, giữ connection và có thể gây timeout.

## 9. Thiết kế tác vụ dài bằng trạng thái pending

Nếu thao tác xác nhận cần gọi hệ thống đối tác lâu, không nên giữ request và execution lock trong thời gian không giới hạn.

~~~mermaid
flowchart TD
    A["review"] -->|"confirm"| B["submit action"]
    B --> C["Tạo requestId + ghi trạng thái PENDING"]
    C --> D["Phát job nền"]
    D --> E["pending view-state"]
    E -->|"refresh/check"| F["Tra cứu trạng thái"]
    F -->|"confirmed"| G["completed"]
    F -->|"rejected"| H["review/problem"]
    F -->|"pending"| E
~~~

Request xác nhận chỉ ghi nhận yêu cầu và chuyển flow sang pending. Worker xử lý nền; request sau tra cứu trạng thái. Việc cập nhật database và phát job cần cơ chế nhất quán phù hợp như outbox nếu yêu cầu không được mất sự kiện.

### 9.1. Background worker không tự sửa FlowExecution đang được browser dùng

Worker nền nên cập nhật trạng thái nghiệp vụ trong database. Request tiếp theo của browser đọc kết quả và phát event để flow chuyển state.

Nếu cần resume flow từ hệ thống nền, phải dùng cơ chế resume/notification được thiết kế rõ, có phối hợp lock/repository và xác thực context. Không giữ một tham chiếu FlowExecution mutable trong thread nền rồi sửa trực tiếp.

## 10. Lock trong môi trường nhiều node

Một ứng dụng có thể chạy trên nhiều instance:

~~~text
             Load balancer
              /        \
          Node A      Node B
             \          /
              Shared repository
                    |
                Database
~~~

Nếu lock chỉ tồn tại trong bộ nhớ của Node A, Node B không tự biết Node A đang giữ khóa. Khi hai request cùng execution được route tới hai node, hai local lock riêng có thể cùng cho phép truy cập.

### 10.1. In-memory lock không tự trở thành distributed lock

Một `synchronized` block hoặc ReentrantLock trong JVM chỉ điều phối thread trong process đó. Nó không khóa thread ở node khác.

Với deployment nhiều node, cần bảo đảm repository và lock coordination có phạm vi phù hợp với cách execution được lưu/khôi phục. Tùy kiến trúc, có thể cần:

- Repository hỗ trợ lưu execution dùng chung.
- Cơ chế lock phân tán/cluster-aware.
- Khóa hoặc optimistic concurrency ở tầng storage.
- Session affinity kết hợp repository và bảo vệ nhất quán phù hợp.

**Sticky session một mình không phải bảo đảm correctness.** Request retry, failover, deploy hoặc route thay đổi vẫn có thể đưa cùng execution đến node khác.

### 10.2. Kiểm tra semantics của repository

Khi chọn repository, hãy xác minh:

1. Execution được lưu ở đâu: memory, HTTP session, database hay store khác?
2. Execution key có dùng chung được giữa node không?
3. Lock được chia sẻ trong phạm vi nào?
4. Khi node chết trong lúc giữ lock, lock có được giải phóng/lease hết hạn không?
5. Snapshot có versioning/expiration như thế nào?
6. Concurrent update được xử lý bằng lock, version check hay cơ chế khác?
7. Có thể quan sát lock timeout và repository failure không?

Không giả định một repository lưu execution phân tán cũng tự cung cấp distributed lock nếu tài liệu implementation không xác nhận.

## 11. Lock granularity và ảnh hưởng hiệu năng

Khóa quá rộng làm giảm throughput; khóa quá hẹp có thể không bảo vệ đủ trạng thái.

| Granularity | Hành vi | Rủi ro |
| --- | --- | --- |
| Toàn ứng dụng | Mọi execution phải chờ cùng lock | Throughput thấp, một request chậm ảnh hưởng toàn hệ thống |
| Theo flow ID | Các user cùng flow bị chặn lẫn nhau | Không cần thiết nếu execution độc lập |
| Theo execution | Chỉ request cùng execution cạnh tranh | Thường là phạm vi hợp lý cho state mutable |
| Theo snapshot | Có thể cho phép một số continuation khác nhau | Cần hiểu rõ semantics và side effect |
| Theo tài nguyên nghiệp vụ | Bảo vệ booking/inventory cụ thể | Cần ở service/database, độc lập flow lock |

FlowExecutionLock thường hướng tới bảo vệ execution. Những lock nghiệp vụ phải được thiết kế ở service/repository dữ liệu.

### 11.1. Tránh một global synchronized cho mọi request

Ví dụ không phù hợp:

~~~java
public synchronized Event handle(RequestContext context) {
    return bookingService.reserve(context);
}
~~~

Phương thức synchronized trên singleton bean có thể serialize mọi request đi qua bean đó, kể cả những execution độc lập. Nó làm giảm khả năng xử lý song song và không bảo vệ dữ liệu trên node khác.

Đừng thêm synchronized như một cách thay thế FlowExecutionLock hoặc transaction. Nếu bean giữ state mutable dùng chung, hãy thiết kế lại phạm vi state và concurrency của bean.

## 12. Deadlock và thứ tự lấy khóa

Một request có thể nắm execution lock rồi gọi service lấy database row lock. Một luồng khác có thể nắm database lock rồi gọi ngược vào cùng flow execution. Nếu thứ tự khóa không thống nhất, có nguy cơ deadlock.

~~~mermaid
flowchart TD
    A["Thread 1"] --> B["Giữ execution lock"]
    B --> C["Chờ database lock"]
    D["Thread 2"] --> E["Giữ database lock"]
    E --> F["Chờ execution lock"]
    C -.-> G["Deadlock cycle"]
    F -.-> G
~~~

Đây là tình huống minh họa về thứ tự khóa giữa hai tầng. Tránh:

- Gọi ngược vào flow từ callback trong khi transaction/DB lock đang giữ.
- Giữ database transaction mở trong lúc chờ remote service.
- Lấy các lock theo thứ tự khác nhau giữa các code path.
- Dùng synchronized ở service rồi gọi lại flow executor.

### 12.1. Quy tắc giảm deadlock

1. Xác định thứ tự lock thống nhất giữa execution, application và database.
2. Giữ transaction ngắn.
3. Không thực hiện network I/O lâu khi đang giữ DB lock.
4. Không gọi lại flow executor từ bên trong critical section nếu không cần.
5. Có timeout và logging cho lock/database wait.
6. Khi gặp deadlock, retry transaction có giới hạn nếu thao tác idempotent.

Database có thể tự phát hiện deadlock và rollback một transaction. Điều đó không có nghĩa FlowExecutionLock tự khôi phục trạng thái nghiệp vụ; action cần xử lý lỗi và service phải bảo đảm retry an toàn.

## 13. Lock timeout và phản hồi khi contention cao

Nếu nhiều request cùng một execution, request chờ lock có thể tăng latency. Nếu lock có timeout, request có thể không lấy được lock trong thời gian cho phép.

Không nên:

- Hiển thị stack trace cho người dùng.
- Tự động tạo execution mới cho cùng thao tác.
- Retry vô hạn ngay lập tức.
- Bỏ qua lock và sửa execution trực tiếp.

Nên:

- Ghi nhận contention/wait duration.
- Trả phản hồi retryable phù hợp với web integration.
- Dùng backoff có jitter cho client nếu retry được phép.
- Bảo đảm retry giữ nguyên idempotency key.
- Giới hạn số lần retry.
- Kiểm tra request đầu tiên đã hoàn tất nghiệp vụ chưa trước khi cho gửi lại.

### 13.1. Không nhầm lock timeout với kết quả nghiệp vụ

Lock timeout nói rằng request không lấy được quyền truy cập execution trong thời gian quy định. Nó không nói rằng booking đã hết chỗ, thanh toán thất bại hay người dùng thiếu quyền.

Giữ các loại lỗi riêng:

- Execution lock contention/timeout.
- Repository unavailable.
- Domain rejection.
- Database transaction timeout.
- Remote service timeout.

Mỗi loại có cách retry và phản hồi khác nhau.

## 14. Quy tắc khi triển khai custom repository hoặc custom lock

Phần lớn ứng dụng nên dùng repository/lock implementation được Web Flow hỗ trợ. Nếu có yêu cầu custom, cần thực hiện đúng contract.

Một custom lock phải cân nhắc:

- Hai request cùng execution nhận cùng một cơ chế phối hợp.
- Các execution độc lập không vô tình dùng chung lock.
- acquire có semantics rõ khi contention.
- release luôn được gọi sau khi xử lý.
- Exception không để lock bị kẹt vĩnh viễn.
- Có xử lý thread interruption/timeout nếu API hỗ trợ.
- Nhiều node dùng cơ chế coordination chung nếu repository shared.
- Không dùng object lock chỉ được tạo mới cho mỗi request, vì hai request sẽ không chia sẻ cùng monitor.

### 14.1. Anti-pattern: tạo lock mới trong mỗi lần gọi

~~~java
public void handle(String executionId) {
    Object lock = new Object();
    synchronized (lock) {
        process(executionId);
    }
}
~~~

Mỗi request tạo một object khác nhau, nên hai thread không đồng bộ với nhau. Đây chỉ là khóa cục bộ vô nghĩa đối với request khác.

### 14.2. Anti-pattern: map lock không dọn dẹp

Một ConcurrentHashMap<ExecutionId, Lock> tự quản lý có thể tăng mãi nếu không có chiến lược lifecycle/cleanup. Việc xóa lock khi vẫn có thread đang chờ cũng có thể tạo hai lock khác nhau cho cùng execution.

Không tự xây lock registry nếu repository framework đã cung cấp cơ chế. Nếu buộc phải làm, cần thiết kế atomic lifecycle, reference counting/lease và test cạnh tranh kỹ lưỡng.

## 15. Observability: đo contention và tác động

Chỉ nhìn số request/giây chưa đủ để biết execution lock có gây nghẽn không. Theo dõi các tín hiệu:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Lock wait duration | Thời gian chờ lấy lock |
| Lock hold duration | Thời gian giữ lock |
| Lock acquisition timeout count | Số lần không lấy được lock |
| Concurrent request count per execution | Số request đồng thời nhắm cùng execution |
| Flow request latency | Latency tổng của request Web Flow |
| Repository read/write latency | Thời gian restore/save snapshot |
| Action duration | Thời gian xử lý action trong critical section |
| Duplicate business request count | Số lần idempotency key được dùng lại |

### 15.1. Log theo execution nhưng tránh lộ key

Log có thể ghi:

~~~text
flowId=booking
stateId=reserve
lockResult=acquired
lockWaitMs=18
lockHoldMs=74
correlationId=...
requestOutcome=booked
~~~

Đây là định dạng minh họa. Tránh ghi raw execution key hoặc dữ liệu cá nhân vào metrics labels. Có thể dùng hash/ID quan sát được đã được kiểm soát nếu cần nối log.

### 15.2. Đo p95/p99

Lock contention thường xuất hiện ở tail latency trước khi ảnh hưởng rõ đến latency trung bình. Theo dõi p95/p99 của:

- Lock wait.
- Lock hold.
- Flow request.
- Action/service.
- Repository snapshot.

Nếu lock wait tăng cùng lúc action duration tăng, cần tìm action đang giữ execution lock quá lâu. Nếu lock wait cao nhưng action ngắn, có thể client đang gửi request trùng hoặc lock granularity quá rộng.

## 16. Kiểm thử concurrency

Một test concurrency nên xác minh cả tính nhất quán của execution và tính duy nhất của nghiệp vụ.

### 16.1. Kiểm thử hai request cùng execution

Pseudocode:

~~~text
execution = startFlow("booking")
execution = moveTo(execution, "review")
key = currentExecutionKey(execution)

barrier = new CyclicBarrier(2)

thread1:
    barrier.await()
    submit(key, event="confirm")

thread2:
    barrier.await()
    submit(key, event="confirm")

await both requests

assert execution is consistent
assert no unhandled concurrent mutation
assert reservation count for requestId == 1
~~~

Đây là pseudocode, không phải test Java chạy nguyên văn. Test thực tế cần dùng servlet/Web Flow integration và repository thật hoặc implementation test tương ứng.

### 16.2. Kiểm thử execution độc lập

Khởi tạo hai execution A và B:

~~~text
request A1 -> execution A
request B1 -> execution B
~~~

Xác minh request B không phải chờ một global lock do request A giữ, trừ khi kiến trúc có tài nguyên dùng chung cần serialize riêng.

### 16.3. Kiểm thử exception trong vùng lock

Cho action ném exception trong khi request đang xử lý:

- Request kết thúc theo exception policy.
- Lock được release.
- Request kế tiếp có thể tiếp tục/nhận lỗi theo repository policy.
- Execution không bị giữ khóa vô hạn.
- Cause chain vẫn được ghi nhận.

### 16.4. Kiểm thử nhiều node

Trong deployment nhiều instance:

1. Route request đầu tiên của execution tới Node A.
2. Gửi request đồng thời/tiếp theo tới Node B.
3. Xác minh repository và lock coordination không cho hai node sửa execution trái phép.
4. Mô phỏng Node A restart trong khi request đang xử lý.
5. Xác minh lock lease/recovery và kết quả nghiệp vụ.

Test này cần môi trường tương tự production; test đơn JVM không chứng minh distributed locking.

## 17. Chẩn đoán lỗi khi nhiều request dùng cùng execution

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Request thứ hai chờ lâu | Request đầu giữ lock lâu | Đo lock wait/hold, action duration |
| Event không hợp lệ sau double-click | Request đầu đã chuyển state | Kiểm tra snapshot/current state và event |
| Booking bị tạo hai lần | Service thiếu idempotency | Kiểm tra request ID, unique constraint |
| State/snapshot không nhất quán | Custom repository/lock sai | Kiểm tra lock identity và save semantics |
| Chỉ lỗi khi chạy nhiều node | Lock chỉ có phạm vi JVM | Kiểm tra repository và distributed coordination |
| Lock không được nhả sau exception | Custom code thiếu finally/cleanup | Kiểm tra lifecycle và exception path |
| Mọi flow đều chậm khi một action chậm | Global lock hoặc singleton synchronized | Kiểm tra granularity |
| Database deadlock | Thứ tự lấy lock/transaction không nhất quán | Đọc DB deadlock graph và transaction trace |
| Retry tạo side effect mới | Execution lock bị nhầm với idempotency | Bảo vệ service theo business request ID |

### 17.1. Trình tự điều tra

1. Xác định flow ID và execution identity từ log an toàn.
2. Xác định repository implementation và snapshot strategy.
3. Xem hai request có cùng execution hay chỉ cùng Flow ID.
4. Đo thời gian lock wait/hold và thời gian action.
5. Xem event và state trước/sau từng request.
6. Kiểm tra transaction, request ID và side effect.
7. Nếu nhiều node, xác minh lock có được chia sẻ giữa node.
8. Kiểm tra exception path có release lock.
9. Viết test tái hiện bằng hai request đồng thời.

Không log toàn bộ execution object hoặc flowScope để điều tra; dữ liệu có thể chứa thông tin cá nhân và token.

## 18. Bài thực hành: hai tab cùng xác nhận một booking

Một flow đặt lịch có state:

~~~text
chooseSlot → contact → review → reserve → completed
~~~

Người dùng mở review ở hai tab. Hai tab cùng gửi event confirm gần như đồng thời. Ứng dụng đôi khi tạo hai booking.

**Yêu cầu:**

1. Vẽ luồng hai request cùng tiếp tục một execution.
2. Giải thích vai trò của FlowExecutionLock và repository trong việc bảo vệ state mutable.
3. Xác định phạm vi lock: execution, snapshot hay phạm vi khác theo repository thực tế.
4. Phân tích điều gì xảy ra khi request thứ hai được xử lý sau request thứ nhất.
5. Thiết kế request ID/idempotency key ổn định cho một ý định booking.
6. Thêm unique constraint hoặc idempotency record để chống ghi trùng.
7. Kiểm thử hai request đồng thời bằng barrier/latch.
8. Kiểm thử exception trong lúc giữ lock và xác minh lock được nhả.
9. Đo lock wait, hold duration và action duration.
10. Nếu chạy nhiều node, mô tả repository/lock coordination cần thiết.
11. Kiểm tra browser Back dùng snapshot cũ không làm booking bị tạo lại.
12. Viết phản hồi phù hợp khi lock contention hoặc kết quả ghi chưa xác định.

**Bảng kết quả mong đợi:**

| Kịch bản | Kết quả |
| --- | --- |
| Hai request cùng execution đến đồng thời | State được bảo vệ khỏi cập nhật đồng thời |
| Hai request cùng request ID nghiệp vụ | Chỉ một booking được tạo |
| Hai execution độc lập | Có thể xử lý song song |
| Action ném exception | Lock được giải phóng theo contract |
| Request đến node khác | Repository/lock phối hợp đúng trong cluster |
| Timeout sau commit | Đối soát và trả booking đã tạo |

**Tiêu chí đạt:** execution không bị hai thread sửa cùng lúc; các execution độc lập không bị serialize không cần thiết; booking không trùng; lock được release cả khi exception; deployment nhiều node có cơ chế phối hợp thực sự.

## 19. Tổng kết và câu hỏi tự kiểm tra

Spring Web Flow cần kiểm soát truy cập đồng thời vào cùng FlowExecution vì execution chứa state và scope có thể thay đổi. **FlowExecutionLock** và repository phối hợp để bảo vệ quá trình tiếp tục execution. Lock chỉ giải quyết đồng bộ truy cập execution trong phạm vi implementation; nó không thay thế transaction, database constraint, idempotency hoặc distributed lock cho tài nguyên dùng chung.

Khi double-click, AJAX hoặc nhiều tab gửi request cùng execution, framework cần tuần tự hóa thao tác trên execution. Request thứ hai vẫn có thể được xử lý sau đó theo repository/snapshot strategy; vì vậy service phải chống side effect lặp bằng request ID/idempotency. Giữ critical section ngắn, tránh gọi tác vụ chậm, bảo đảm release khi exception, và kiểm tra coordination trong môi trường nhiều node.

**Câu hỏi tự kiểm tra:**

1. Vì sao hai request cùng Flow ID chưa chắc cùng FlowExecution?
2. FlowExecutionLock bảo vệ đối tượng/trạng thái nào?
3. Vì sao lock phải được lấy trong lúc xử lý request nhưng không giữ suốt thời gian người dùng nhập form?
4. Vì sao double-click vẫn có thể tạo side effect lặp dù execution lock đã tuần tự hóa request?
5. Execution key khác idempotency key ở điểm nào?
6. Vì sao synchronized trên singleton service có thể làm nghẽn các execution độc lập?
7. In-memory lock có bảo vệ execution khi request đi tới hai node khác nhau không?
8. Cần làm gì để tránh lock bị giữ sau exception?
9. Lock contention khác database deadlock và domain rejection như thế nào?
10. Những test nào chứng minh execution lock, idempotency và distributed coordination hoạt động đúng?
