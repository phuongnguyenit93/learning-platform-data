# Thao tác bù, xung đột cập nhật và khóa lạc quan

## 1. Vấn đề: hai request cùng thay đổi một trạng thái

Ứng dụng cloud thường nhận nhiều request đồng thời từ web, mobile, worker và các dịch vụ tích hợp. Hai người có thể sửa cùng một đặt phòng; hai worker có thể xử lý cùng một message; một quy trình thanh toán có thể hoàn tất ở nhà cung cấp nhưng response bị timeout. Nếu hệ thống chỉ đọc dữ liệu, tính toán rồi ghi lại mà không kiểm tra trạng thái đã thay đổi hay chưa, một cập nhật có thể vô tình ghi đè cập nhật khác.

Hai nhóm kỹ thuật thường cần phối hợp:

- **Optimistic concurrency control (kiểm soát đồng thời lạc quan):** cho phép nhiều bên đọc cùng trạng thái, nhưng khi ghi phải xác nhận dữ liệu vẫn ở phiên bản mà thao tác đã đọc. Nếu có thay đổi trước đó, thao tác bị từ chối để caller đọc lại và giải quyết xung đột.
- **Compensation (thao tác bù):** khi một quy trình gồm nhiều bước đã tạo ra một số hiệu ứng nhưng không thể hoàn tất, hệ thống thực hiện hành động nghiệp vụ ngược hoặc điều chỉnh để đưa trạng thái về kết quả chấp nhận được. Đây không phải lúc nào cũng là rollback chính xác như transaction database.

Ví dụ, khách hàng đặt một căn hộ. Booking service giữ chỗ, Payment service yêu cầu thu tiền, rồi hệ thống xác nhận đặt phòng và gửi thông báo. Nếu thanh toán thất bại, hệ thống có thể giải phóng chỗ. Nếu thanh toán thành công nhưng bước xác nhận booking thất bại, có thể cần hoàn tiền hoặc đối soát. Trong khi đó, nếu hai khách cùng đặt một lịch, hệ thống phải ngăn cập nhật ghi đè khiến cả hai cùng tin rằng mình đã có chỗ.

Trong module **CLOUD_ARCHITECTURE**, các quyết định này liên quan trực tiếp đến độ tin cậy, dữ liệu nhất quán, khả năng mở rộng, chi phí và vận hành. Đặc biệt trong kiến trúc phân tán, không thể giả định một transaction ACID bao trùm nhiều database, queue và nhà cung cấp bên ngoài.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích lost update, stale write và các dạng xung đột cập nhật thường gặp.
2. Thiết kế khóa lạc quan bằng version number, timestamp phù hợp hoặc HTTP ETag/If-Match.
3. Xử lý conflict an toàn bằng đọc lại, hợp nhất thay đổi hoặc yêu cầu người dùng quyết định.
4. Phân biệt database rollback, retry và business compensation.
5. Mô hình hóa quy trình nhiều bước bằng Saga, state machine và hành động bù.
6. Thiết kế idempotency, timeout, retry, đối soát và quan sát trạng thái bù.
7. Kiểm thử cạnh tranh cập nhật và các tình huống lỗi từng phần trong kiến trúc cloud.

## 2. Nhận diện xung đột cập nhật

### 2.1. Lost update

Giả sử một reservation có số khách là 2 và hai người dùng cùng mở màn hình ở thời điểm T0:

1. Người A đọc guestCount = 2.
2. Người B cũng đọc guestCount = 2.
3. A sửa thành 3 và ghi vào database.
4. B sửa thành 4 dựa trên bản cũ rồi ghi đè.
5. Kết quả cuối là 4; thay đổi của A đã biến mất mà không ai được thông báo.

~~~mermaid
sequenceDiagram
    participant A as User A
    participant B as User B
    participant DB as Database
    A->>DB: Read guestCount = 2
    B->>DB: Read guestCount = 2
    A->>DB: Write guestCount = 3
    DB-->>A: Success
    B->>DB: Write guestCount = 4 (based on stale value)
    DB-->>B: Success, overwrites A
~~~

Đây là **lost update**: ghi sau ghi đè một thay đổi trước đó vì không có điều kiện kiểm tra phiên bản hoặc cơ chế đồng bộ phù hợp.

### 2.2. Các dạng xung đột khác

| Dạng | Mô tả | Ví dụ |
|---|---|---|
| **Lost update** | Một cập nhật bị ghi đè bởi cập nhật dựa trên dữ liệu cũ | Hai nhân viên sửa cùng địa chỉ khách |
| **Stale write** | Client ghi dựa trên phiên bản đã lỗi thời | App offline gửi lại bản hồ sơ cũ |
| **Write-write conflict** | Nhiều transaction cùng sửa một record hoặc vùng dữ liệu | Hai request cùng đổi trạng thái booking |
| **Check-then-act race** | Kiểm tra điều kiện rồi hành động, nhưng điều kiện thay đổi giữa hai bước | Hai request cùng thấy còn một phòng rồi cùng đặt |
| **Duplicate command** | Một lệnh được xử lý nhiều lần do retry/delivery | Worker nhận lại message thu tiền |
| **Non-repeatable read** | Một transaction đọc cùng dữ liệu hai lần nhưng thấy giá trị khác do transaction khác commit | Màn hình xử lý nghiệp vụ đọc balance trước và sau khi có giao dịch khác |
| **Phantom/read skew** | Một lần đọc tập dữ liệu hoặc nhiều record không còn phản ánh cùng một snapshot | Kiểm tra tổng quota và số booking đang hoạt động trong hai truy vấn khác thời điểm |

Không phải mọi hệ thống đều cần giải quyết mọi dạng anomaly bằng cùng một cơ chế. Cần xác định **invariant nghiệp vụ** (điều kiện phải luôn đúng), ranh giới transaction và mức consistency được yêu cầu.

## 3. Pessimistic locking và optimistic locking

Hai cách tiếp cận phổ biến để bảo vệ cập nhật đồng thời:

| Tiêu chí | Pessimistic locking | Optimistic concurrency |
|---|---|---|
| Giả định | Xung đột có thể xảy ra đủ thường xuyên để cần khóa trước | Xung đột tương đối hiếm; kiểm tra khi ghi |
| Cách hoạt động | Giữ lock trong thời gian thao tác/transaction | Đọc version, ghi có điều kiện theo version cũ |
| Khi xung đột | Request khác chờ, timeout hoặc bị từ chối do lock | Một request thành công, request dùng version cũ bị conflict |
| Ưu điểm | Có thể đơn giản hóa một số thao tác cần tuần tự hóa | Ít giữ lock dài; phù hợp nhiều lượt đọc, ít xung đột |
| Rủi ro | Deadlock, lock contention, timeout, throughput giảm | Caller phải xử lý conflict và retry/hợp nhất |
| Phù hợp | Critical section ngắn, dữ liệu nóng, invariant cần serialize | API chỉnh sửa hồ sơ, resource có nhiều lượt đọc và xung đột vừa/thấp |

**Khóa lạc quan không có nghĩa là không có kiểm soát đồng thời.** Nó vẫn dùng một thao tác ghi nguyên tử có điều kiện ở database hoặc storage service. Khác biệt nằm ở việc không giữ lock độc quyền trong toàn bộ thời gian client đọc và chỉnh sửa.

Không nên chọn chỉ dựa trên khẩu hiệu “lock-free nhanh hơn”. Với một tài nguyên rất nóng, nhiều client cùng cập nhật liên tục, optimistic retry có thể gây nhiều lần thất bại và tăng tải. Pessimistic locking hoặc thiết kế phân vùng/serialized command có thể phù hợp hơn.

## 4. Khóa lạc quan bằng version number

### 4.1. Nguyên tắc

Mỗi record có một trường version tăng sau mỗi lần cập nhật thành công. Client đọc dữ liệu cùng version; khi ghi, câu lệnh chỉ thành công nếu version hiện tại vẫn bằng version client đã đọc.

Giả sử reservation ban đầu có version = 7:

1. A và B cùng đọc version 7.
2. A ghi thay đổi với điều kiện version = 7; database cập nhật và tăng version lên 8.
3. B ghi với điều kiện version = 7; không có record nào khớp điều kiện.
4. B nhận conflict, đọc lại version 8 và quyết định hợp nhất, thử lại hoặc yêu cầu người dùng xem thay đổi mới.

~~~mermaid
sequenceDiagram
    participant A as User A
    participant B as User B
    participant DB as Database
    A->>DB: Read value, version=7
    B->>DB: Read value, version=7
    A->>DB: UPDATE ... WHERE version=7
    DB-->>A: 1 row updated, version=8
    B->>DB: UPDATE ... WHERE version=7
    DB-->>B: 0 rows updated (conflict)
    B->>DB: Read latest value, version=8
    DB-->>B: Latest state
    B->>B: Merge, retry, or ask user
~~~

### 4.2. Ví dụ SQL

~~~sql
CREATE TABLE reservations (
    reservation_id VARCHAR(40) PRIMARY KEY,
    guest_count INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1
);
~~~

Client đã đọc version 7 và muốn thay guest_count:

~~~sql
UPDATE reservations
SET guest_count = 3,
    version = version + 1
WHERE reservation_id = 'rs-1732'
  AND version = 7;
~~~

Ứng dụng kiểm tra số hàng bị cập nhật:

- **1 row:** cập nhật thành công, version đã tăng.
- **0 row:** có thể record không tồn tại hoặc version đã thay đổi; cần phân biệt bằng quy tắc truy vấn/authorization phù hợp.

Phải thực thi câu lệnh cập nhật trong một thao tác nguyên tử ở database. Mẫu đọc version trước rồi ghi không có điều kiện vẫn bị race. Version cần tăng ở **mọi đường ghi**: API, worker, batch job, admin tool và migration có thay đổi dữ liệu nghiệp vụ. Nếu một luồng bỏ qua version, bảo vệ lost update không còn đáng tin.

### 4.3. Version number khác timestamp

Timestamp có thể dùng làm version token trong một số hệ thống, nhưng cần đánh giá độ chính xác, đồng hồ, hai cập nhật trong cùng độ phân giải, timezone và cách provider tạo giá trị. Một bộ đếm tăng đơn điệu hoặc concurrency token do database cấp thường rõ hơn cho kiểm tra đồng thời.

Không dùng thời gian client gửi lên làm bằng chứng duy nhất về phiên bản mới nhất. Đồng hồ client có thể lệch hoặc request tới server khác nhau về thứ tự.

## 5. Khóa lạc quan ở tầng HTTP: ETag và If-Match

HTTP cung cấp cơ chế validator để client cập nhật một representation chỉ khi resource vẫn khớp với phiên bản mà client đã đọc.

### 5.1. Đọc resource và nhận ETag

~~~http
GET /v1/reservations/rs-1732
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
ETag: "reservation-v7"
Content-Type: application/json

{
  "id": "rs-1732",
  "guestCount": 2,
  "status": "PENDING"
}
~~~

Client cập nhật với validator:

~~~http
PATCH /v1/reservations/rs-1732
If-Match: "reservation-v7"
Content-Type: application/merge-patch+json

{
  "guestCount": 3
}
~~~

Nếu representation vẫn khớp validator, API thực hiện cập nhật và trả validator mới. Nếu đã thay đổi, server trả **412 Precondition Failed** cho điều kiện If-Match không còn đúng.

### 5.2. Các status code liên quan

| Status | Ý nghĩa thường gặp | Cách client phản ứng |
|---|---|---|
| **200 OK** | Cập nhật thành công và trả representation | Dùng body/ETag mới |
| **204 No Content** | Cập nhật thành công, không có body | Lưu ETag mới nếu có |
| **409 Conflict** | Conflict theo ngữ nghĩa nghiệp vụ hoặc trạng thái hiện tại | Hiển thị/xử lý conflict theo hợp đồng API |
| **412 Precondition Failed** | Điều kiện HTTP như If-Match không thỏa | Đọc lại resource và hợp nhất hoặc yêu cầu người dùng |
| **428 Precondition Required** | Server yêu cầu client gửi precondition theo policy | Đọc lại và gửi If-Match |

Phân biệt 409 với 412 theo hợp đồng. Nếu API dùng If-Match cho concurrency control, 412 thường diễn đạt rõ điều kiện đã không còn đúng. 409 có thể diễn đạt xung đột nghiệp vụ khác, ví dụ không thể hủy booking đã hoàn tất.

### 5.3. ETag không phải lúc nào cũng là database version

ETag là validator cho representation; nó có thể là hash hoặc opaque token. API phải bảo đảm cách tạo và so sánh validator phát hiện được thay đổi liên quan đến representation và thao tác cập nhật. Không tiết lộ thông tin nội bộ nhạy cảm trong ETag.

Với ETag yếu (weak validator) có tiền tố W/, không thể dùng cho phép so khớp mạnh của If-Match. Nếu API cần điều kiện cập nhật chính xác, dùng strong ETag hoặc concurrency token được thiết kế rõ ràng.

## 6. Xử lý conflict: không phải lúc nào cũng retry mù

Khi nhận optimistic conflict, client hoặc service cần biết **thay đổi nào có thể hợp nhất an toàn**.

### 6.1. Các chiến lược

| Chiến lược | Dùng khi | Ví dụ |
|---|---|---|
| **Read–merge–write** | Các thay đổi độc lập và có quy tắc hợp nhất | A đổi số điện thoại, B sửa địa chỉ |
| **Retry sau khi đọc lại** | Thao tác có thể tính lại trên trạng thái mới | Tăng counter có điều kiện |
| **Reject và yêu cầu người dùng** | Thay đổi mang tính lựa chọn, không thể tự hợp nhất | Hai người cùng đặt thời gian khác nhau cho một lịch |
| **Field-level update** | Các field độc lập nhưng cần kiểm soát quyền và invariant | PATCH một thuộc tính thay vì PUT toàn bộ object |
| **Serialize command** | Dữ liệu nóng, yêu cầu thứ tự xử lý | Một queue/partition theo resource ID |
| **Domain-specific merge** | Có quy tắc nghiệp vụ xác định | Cộng số lượng theo delta thay vì ghi absolute value |

### 6.2. Ví dụ hợp nhất

Giả sử A đổi số điện thoại, B đổi địa chỉ. Nếu hai thay đổi không phụ thuộc lẫn nhau và đều hợp lệ theo trạng thái mới nhất, hệ thống có thể lấy bản mới nhất rồi áp lại field của caller. Nhưng nếu cả hai đổi check-in date và điều đó ảnh hưởng availability/pricing, không thể tự chọn một giá trị mà không có quy tắc nghiệp vụ.

Không nên tự động merge mảng, trạng thái thanh toán, quyền truy cập hoặc các field phụ thuộc invariant chỉ vì chúng nằm ở những cột khác nhau.

### 6.3. Retry phải có giới hạn

Một vòng retry hợp lý:

1. Đọc trạng thái và version hiện tại.
2. Tính lại thay đổi từ command gốc trên trạng thái mới.
3. Thử ghi bằng điều kiện version.
4. Nếu vẫn conflict, áp giới hạn số lần/tổng thời gian.
5. Nếu vượt giới hạn, trả conflict có thể hiểu được hoặc chuyển sang xử lý tuần tự.

Retry không giới hạn có thể làm tài nguyên nóng thêm và tăng tải database. Với request từ client, thường nên trả conflict để client tải lại thay vì server tự retry nhiều lần mà người dùng không biết.

## 7. Bảo vệ invariant: check-then-act phải nguyên tử

Một lỗi nghiêm trọng xảy ra khi ứng dụng tách bước kiểm tra và ghi thành hai thao tác không được bảo vệ.

Ví dụ: căn hộ chỉ còn một chỗ trống. Hai request chạy đồng thời:

~~~text
Request A: SELECT available_count -> 1
Request B: SELECT available_count -> 1
Request A: INSERT reservation
Request B: INSERT reservation
~~~

Nếu không có database constraint, transaction isolation hoặc cơ chế atomic update phù hợp, cả hai có thể thành công.

Một lựa chọn là cập nhật có điều kiện:

~~~sql
UPDATE inventory
SET available_count = available_count - 1,
    version = version + 1
WHERE property_id = 'home-25'
  AND available_count > 0
  AND version = 12;
~~~

Ứng dụng chỉ coi đã giữ được chỗ khi một hàng được cập nhật. Nếu không, đọc lại trạng thái và xử lý theo nghiệp vụ. Tùy bài toán, cần unique/exclusion constraint cho khoảng thời gian không được trùng, transaction phù hợp hoặc một mô hình reservation/hold riêng.

**Optimistic version không tự bảo đảm mọi invariant phức tạp.** Nếu invariant trải qua nhiều record hoặc nhiều bảng, chỉ version của một row có thể không đủ. Cần đặt ranh giới transaction và constraint tại đúng nơi có thẩm quyền quyết định.

## 8. Transaction, rollback và compensation khác nhau thế nào?

Ba khái niệm thường bị đánh đồng:

- **Rollback database transaction:** hủy các thay đổi chưa commit trong một transaction ACID trên phạm vi mà database kiểm soát.
- **Retry:** thử thực hiện lại một thao tác sau lỗi được xem là tạm thời hoặc sau khi đọc trạng thái mới.
- **Compensation:** tạo một thao tác nghiệp vụ mới để bù hiệu ứng đã commit ở một bước trước trong quy trình phân tán.

Ví dụ, DB đã commit trạng thái booking, payment provider đã thu tiền, và email đã được gửi. Không tồn tại một nút rollback duy nhất có thể quay ngược tất cả ba hệ thống một cách nguyên tử. Hệ thống cần **compensating actions**: hủy/điều chỉnh booking, hoàn tiền qua provider và có thể gửi thông báo cập nhật.

| Khía cạnh | Rollback transaction | Compensation |
|---|---|---|
| Phạm vi | Một transaction do transaction manager/database kiểm soát | Nhiều thao tác/dịch vụ đã hoàn tất ở các thời điểm khác nhau |
| Tính nguyên tử | Các thay đổi chưa commit được rollback theo semantics DB | Không nguyên tử xuyên mọi hệ thống |
| Thời điểm | Trước hoặc khi commit thất bại | Sau khi một hoặc nhiều bước đã tạo hiệu ứng |
| Kết quả | Trạng thái như trước transaction | Trạng thái nghiệp vụ mới nhằm bù/điều chỉnh hiệu ứng cũ |
| Khả năng thất bại | Transaction rollback có cơ chế DB cụ thể | Compensation cũng có thể fail, retry, cần đối soát hoặc can thiệp người |
| Ví dụ | Update booking và outbox cùng transaction bị lỗi | Đã charge nhưng booking không thể xác nhận, cần refund |

**Compensation không xóa lịch sử.** Hoàn tiền không làm cho khoản thu chưa từng xảy ra; nó tạo một giao dịch mới tham chiếu tới giao dịch trước. Giữ lịch sử là cần thiết cho audit, đối soát và tranh chấp.

## 9. Saga: điều phối các bước và hành động bù

Saga là một mô hình quản lý quy trình phân tán gồm nhiều local transaction. Mỗi bước commit trong một service/database riêng; nếu quy trình không thể tiếp tục, các bước bù được thực hiện theo quy tắc đã thiết kế.

### 9.1. Ví dụ đặt phòng và thanh toán

~~~mermaid
flowchart TD
    Start["Create reservation"] --> Hold["T1: Hold inventory"]
    Hold --> Charge["T2: Request payment"]
    Charge --> Paid{"Payment result"}
    Paid -->|Success| Confirm["T3: Confirm booking"]
    Confirm --> Notify["Publish confirmation"]
    Notify --> Done["Completed"]
    Paid -->|Declined| Release["C2: Release hold"]
    Release --> Fail["Booking failed"]
    Confirm -->|Permanent failure| Refund["C3: Refund payment"]
    Refund --> Release2["C2: Release hold"]
    Release2 --> Compensated["Compensated / reconcile"]
~~~

Trong ví dụ:

- **T1** giữ chỗ với expiry/lease để tránh giữ tài nguyên vô hạn.
- **T2** yêu cầu thanh toán bằng idempotency key.
- **T3** xác nhận booking sau khi kết quả thanh toán được xác thực.
- **C2** giải phóng chỗ đang giữ.
- **C3** yêu cầu hoàn tiền nếu đã thu tiền nhưng booking không thể xác nhận.

Saga phải xử lý cả trường hợp payment timeout nhưng nhà cung cấp đã thu tiền. Không được suy luận timeout đồng nghĩa payment thất bại; cần truy vấn theo idempotency/reference hoặc reconciliation trước khi gửi charge mới.

### 9.2. Orchestration và choreography

| Cách điều phối | Cách hoạt động | Ưu điểm | Đánh đổi |
|---|---|---|---|
| **Orchestration** | Một workflow/state machine quyết định bước tiếp theo, retry và compensation | Thấy trạng thái tổng thể, luồng xử lý rõ | Workflow engine và state machine là thành phần quan trọng cần vận hành |
| **Choreography** | Service phản ứng với event của service khác | Ít điều phối trung tâm, các service tự chủ hơn | Khó nhìn toàn bộ quy trình, dễ tạo vòng event và khó quản lý thứ tự |

Với quy trình nhiều nhánh, thời gian dài, có human approval hoặc cần audit, orchestration thường dễ diễn giải hơn. Với chuỗi event đơn giản và ít bước, choreography có thể đủ. Không cần Saga chỉ vì có hai service giao tiếp; hãy dùng transaction cục bộ nếu invariant có thể được bảo vệ trong một ranh giới.

### 9.3. State machine và trạng thái trung gian

Một quy trình dài nên có trạng thái tường minh, ví dụ:

~~~text
REQUESTED
  -> INVENTORY_HELD
  -> PAYMENT_PENDING
  -> PAYMENT_CONFIRMED
  -> BOOKING_CONFIRMED

Các nhánh:
PAYMENT_DECLINED -> COMPENSATING -> FAILED
PAYMENT_UNKNOWN  -> RECONCILING
CONFIRM_FAILED   -> REFUND_PENDING -> COMPENSATING
COMPENSATION_FAILED -> MANUAL_REVIEW
~~~

Không gộp mọi lỗi thành FAILED. Trạng thái **PAYMENT_UNKNOWN** cần giữ riêng vì phía provider có thể đã hoàn tất nhưng hệ thống chưa nhận được kết quả. Quy trình reconciliation sẽ xác minh trạng thái trước khi quyết định bước tiếp.

## 10. Thiết kế compensation đúng nghĩa nghiệp vụ

Compensation không nhất thiết là thực hiện chính xác thao tác ngược trên dữ liệu. Nó cần phản ánh những gì hệ thống và người dùng đã trải qua.

| Thao tác đã hoàn tất | Hành động bù có thể có | Điều cần kiểm tra |
|---|---|---|
| Giữ chỗ | Giải phóng hold | Hold còn thuộc Saga hiện tại không? Đã hết hạn hay được quy trình khác tiếp quản? |
| Thu tiền | Refund hoặc void/authorize reversal tùy trạng thái giao dịch | Provider đã capture hay chỉ authorize? Refund có thể một phần không? |
| Cấp voucher | Thu hồi voucher hoặc phát bút toán điều chỉnh | Voucher đã được dùng chưa? Có vi phạm cam kết đã hiển thị? |
| Gửi email | Gửi email đính chính hoặc thông báo hủy | Không thể thu hồi email đã gửi; cần xử lý minh bạch |
| Cập nhật search index | Phát event sửa/xóa index | Index có eventual consistency và replay không? |
| Tạo hóa đơn | Phát hành credit note/điều chỉnh theo quy định nghiệp vụ | Không xóa lịch sử hóa đơn đã phát hành |

Một số hành động không thể hoàn tác hoàn toàn. Gửi email, gửi SMS hoặc thông báo cho đối tác không thể biến mất chỉ bằng cách cập nhật database. Compensation có thể là **hành động điều chỉnh mới**, không phải xóa dấu vết.

### 10.1. Compensation cũng phải idempotent

Nếu Saga retry bước refund, có nguy cơ refund hai lần. Dùng compensation ID hoặc idempotency key ổn định theo Saga step:

~~~text
Saga ID: saga-rs-1732
Step: refund-payment
Compensation key: saga-rs-1732:refund:v1
~~~

Service nhận cùng key phải trả lại kết quả đã xử lý hoặc tiếp tục trạng thái operation hiện có, không tạo thêm hoàn tiền. Cần lưu response/reference của provider để đối soát.

### 10.2. Thứ tự bù

Compensation thường được thiết kế theo thứ tự ngược với các bước đã hoàn tất, nhưng không phải quy tắc tuyệt đối. Phụ thuộc nghiệp vụ, có bước cần làm trước để ngăn tác động tiếp tục xảy ra:

- Dừng nhận thêm command hoặc chuyển workflow sang trạng thái canceling.
- Chặn xác nhận/tiêu thụ tài nguyên mới.
- Hoàn tiền hoặc giải phóng hold theo yêu cầu và dependency.
- Cập nhật read model, gửi thông báo và lưu audit.

Điều quan trọng là xác định **precondition, owner, retry, timeout và hậu quả nếu bù thất bại** cho từng hành động.

## 11. Timeout và kết quả không xác định

Một timeout không nói cho caller biết thao tác phía server đã thành công hay chưa. Đặc biệt khi gọi payment, inventory hoặc dịch vụ bên thứ ba:

1. Caller gửi request.
2. Provider xử lý và commit giao dịch.
3. Response bị mất trên đường mạng.
4. Caller timeout và không biết kết quả.

Nếu caller gửi request mới với idempotency key khác, có thể thu tiền hai lần. Nếu caller đánh dấu thất bại ngay, trạng thái hệ thống sẽ không phản ánh provider.

### Cách xử lý

- Tạo operation ID/idempotency key trước khi gọi provider và lưu trạng thái.
- Khi timeout, đặt trạng thái **UNKNOWN/PENDING_RECONCILIATION**, không đánh dấu chắc chắn thất bại.
- Truy vấn provider theo reference/idempotency key hoặc chờ webhook có chữ ký.
- Xác minh webhook, chống replay và bảo vệ endpoint nhận callback.
- Chỉ thực hiện compensation hoặc retry command sau khi đã biết kết quả hoặc theo chính sách xử lý unknown đã định.
- Chạy reconciliation định kỳ cho những operation ở trạng thái trung gian quá lâu.

## 12. Idempotency trong cập nhật và compensation

Optimistic concurrency bảo vệ xung đột version; idempotency bảo vệ việc lặp cùng một ý định. Hai cơ chế giải quyết vấn đề khác nhau và thường cần dùng cùng nhau.

| Vấn đề | Cơ chế chính |
|---|---|
| Hai caller đọc cùng version rồi ghi | Optimistic concurrency / conditional update |
| Một client retry cùng yêu cầu tạo booking | Idempotency key ở API command |
| Queue giao message nhiều lần | Idempotent consumer/deduplication |
| Saga thực hiện refund lại do timeout | Compensation idempotency key |
| Webhook provider gửi lại | Lưu event ID/provider transaction ID đã xử lý |
| Một operation đã xử lý nhưng response mất | Tra cứu operation cũ và trả kết quả đã có |

Một API ghi nên ràng buộc idempotency key với caller/tenant, loại operation và hash của request phù hợp. Nếu cùng key nhưng payload khác, trả conflict theo hợp đồng thay vì trả nhầm kết quả cũ.

Ví dụ bảng lưu trạng thái:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(80) NOT NULL,
    operation_key VARCHAR(120) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    operation_id VARCHAR(80) NOT NULL,
    status VARCHAR(30) NOT NULL,
    response_reference VARCHAR(200),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

Bảng cần unique constraint cho phạm vi key; retention phải đủ lâu so với cửa sổ retry/đối soát. Không lưu thông tin payment nhạy cảm nếu chỉ cần provider reference.

## 13. Chọn consistency boundary và mô hình dữ liệu

Xung đột thường khó giải quyết hơn khi invariant bị chia qua nhiều owner. Trước khi tách service/database, xác định:

- Record hoặc aggregate nào là nguồn sự thật cho invariant?
- Ai có quyền ghi và có thể serialize command ở đâu?
- Những dữ liệu nào cần transaction nguyên tử?
- Những dữ liệu nào có thể cập nhật sau qua event?
- Consumer chấp nhận độ trễ và khả năng đọc stale tới đâu?
- Có thể tái tạo read model từ event/source of truth không?

Ví dụ, quyết định “còn chỗ để xác nhận hay không” nên nằm trong một boundary có khả năng thực thi atomic constraint/conditional update. Search index có thể là read model eventual consistent; không dùng search result cũ làm bằng chứng cuối cùng rằng chỗ vẫn còn.

Một cách thiết kế hữu ích là **write model** sở hữu quy tắc và dữ liệu chính; **read model** được cập nhật từ event để phục vụ truy vấn. Khi read model chậm, API có thể hiển thị trạng thái đang đồng bộ hoặc đọc authoritative store cho hành động quan trọng.

## 14. Kiểm thử xung đột và Saga

Test thông thường theo thứ tự tuần tự không phát hiện đầy đủ lost update hoặc race condition. Cần test có đồng thời và lỗi tiêm vào từng ranh giới.

### 14.1. Test optimistic concurrency

Kịch bản:

1. Tạo resource version 1.
2. Hai client cùng đọc version 1.
3. Client A ghi thành công với version 1.
4. Client B ghi với version 1 và phải nhận conflict.
5. Xác nhận dữ liệu cuối phản ánh thay đổi A, version chỉ tăng đúng theo số update thành công.
6. Thử B đọc lại và merge/retry theo policy.

~~~text
Given reservation version = 1
When client A and B read version = 1
And A updates with expected version = 1
Then A succeeds and version becomes 2
When B updates with expected version = 1
Then B receives conflict
And no stale value overwrites A
~~~

### 14.2. Test các bất thường Saga

| Fault injection | Kết quả mong muốn |
|---|---|
| Inventory hold thành công, payment decline | Release hold một lần về mặt nghiệp vụ |
| Payment provider capture xong nhưng response timeout | Chuyển UNKNOWN và reconcile, không charge mù lần nữa |
| Booking confirmation lỗi sau khi payment capture | Refund/compensation theo policy và audit |
| Refund timeout sau khi provider thực hiện | Tra cứu cùng idempotency key trước khi retry |
| Consumer nhận event hai lần | Side effect không lặp ngoài ý muốn |
| Compensation service ngừng hoạt động | Saga giữ trạng thái COMPENSATING, retry và alert |
| Workflow engine restart | Khôi phục state, không chạy lại step tạo hiệu ứng trùng |
| Hold hết hạn trong khi payment pending | Xử lý race giữa expiry, payment callback và confirm |

### 14.3. Đo lường

- Tỷ lệ optimistic conflict theo resource/endpoint.
- Số lần retry trung bình và p95 retry count.
- Tỷ lệ Saga thành công, thất bại và đang bù.
- Tuổi của operation ở trạng thái pending/unknown/compensating.
- Tỷ lệ compensation thành công, thất bại và cần manual review.
- Số operation cần reconciliation và thời gian xử lý.
- Tỷ lệ duplicate/idempotency hit và side effect bị ngăn.

Conflict rate tăng có thể báo hiệu tài nguyên quá nóng, UI giữ dữ liệu quá lâu hoặc endpoint thay quá nhiều field một lần. Không nên xem mọi conflict là lỗi; cần theo dõi mức conflict người dùng có thể chấp nhận và tác động lên latency.

## 15. Case study: hai người cùng chỉnh reservation và lỗi thanh toán

**Bối cảnh:** một nền tảng đặt chỗ cho phép khách thay đổi số khách và ngày lưu trú. Hệ thống gồm Reservation API, Inventory service, Payment provider và Notification worker.

### 15.1. Xung đột cập nhật ngày lưu trú

A và B cùng đọc reservation version 10. A đổi ngày trả phòng; B đổi số khách. Nếu API dùng PUT toàn bộ document, B có thể ghi lại ngày cũ và xóa thay đổi của A. Có hai lựa chọn:

- Dùng PATCH chỉ cho field mà caller được phép thay đổi, kèm If-Match version 10. Sau khi A thành công lên version 11, B bị 412.
- Service đọc lại version 11 và hợp nhất số khách nếu rule availability/pricing vẫn cho phép; nếu thay đổi ngày ảnh hưởng giá và chỗ trống, yêu cầu người dùng xem lại dữ liệu mới.

Không tự merge mọi field. Thay đổi số khách có thể ảnh hưởng sức chứa, giá và điều kiện booking; cần chạy lại validation nghiệp vụ trên trạng thái mới.

### 15.2. Lỗi khi thanh toán

1. Reservation service tạo operation và giữ inventory với expiry.
2. Payment service gọi provider bằng idempotency key gắn với operation.
3. Provider thu tiền nhưng response timeout.
4. Operation chuyển PAYMENT_UNKNOWN; worker reconciliation truy vấn provider.
5. Nếu đã capture, workflow tiếp tục xác nhận booking.
6. Nếu provider xác nhận chưa thu tiền và retry window còn hợp lệ, workflow có thể thử lại cùng key theo hợp đồng provider.
7. Nếu không thể xác nhận booking sau khi đã thu tiền, workflow yêu cầu refund và giải phóng hold theo policy.
8. Nếu refund chưa rõ kết quả, giữ REFUND_PENDING/RECONCILING và alert; không giả định đã hoàn tiền.

### 15.3. Trạng thái và quyền sở hữu

| Thành phần | Trạng thái sở hữu | Trách nhiệm |
|---|---|---|
| Reservation service | REQUESTED, CONFIRMED, CANCELLED, COMPENSATING | Quyết định trạng thái booking và phát hành operation |
| Inventory service | HELD, COMMITTED, RELEASED, EXPIRED | Bảo vệ không đặt trùng và vòng đời hold |
| Payment service/provider | PENDING, CAPTURED, DECLINED, REFUND_PENDING, REFUNDED, UNKNOWN | Theo dõi giao dịch và đối soát |
| Notification worker | QUEUED, SENT, FAILED | Gửi thông báo sau trạng thái nghiệp vụ phù hợp |

Mỗi service sở hữu trạng thái của nó; workflow tổng hợp tiến trình nhưng không giả định có thể ghi trực tiếp vào database của service khác.

## 16. Đánh đổi theo tư duy Well-Architected

| Góc nhìn | Quyết định | Lợi ích và đánh đổi |
|---|---|---|
| **Reliability** | Version check, idempotency, Saga và reconciliation | Ngăn ghi đè/lặp hiệu ứng và xử lý lỗi từng phần; tăng số trạng thái cần quản lý |
| **Security** | Authorization trước update/compensation, bảo vệ webhook và secret | Ngăn thao tác trái phép; cần audit và rotation |
| **Performance efficiency** | Optimistic locking cho xung đột thấp, serialize các tài nguyên nóng | Tránh lock dài; conflict/retry có thể tăng tải khi contention cao |
| **Cost optimization** | Chọn consistency boundary và retry có giới hạn | Giảm lock wait/transaction dài; thêm workflow, event và đối soát có chi phí |
| **Operational excellence** | State machine, dashboards, runbook và operation history | Dễ giải thích sự cố; cần owner cho trạng thái pending/manual review |
| **Sustainability** | Tránh retry storm và tác vụ lặp không cần thiết | Giảm compute/data transfer và lãng phí do xử lý trùng |

Khóa lạc quan giảm thời gian giữ lock nhưng không miễn phí: conflict nhiều sẽ tốn lượt đọc/ghi và làm người dùng phải thử lại. Saga tăng khả năng xử lý lỗi từng phần nhưng yêu cầu thiết kế compensation, idempotency, timeout và reconciliation. Lựa chọn phải dựa trên invariant, mức xung đột, SLO và năng lực vận hành.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Đọc rồi ghi mà không có version/constraint | Lost update | Conditional write hoặc transaction phù hợp |
| Chỉ kiểm tra version ở API, không ở database | Race vẫn xảy ra giữa check và update | Đưa điều kiện version vào cùng atomic write |
| Dùng timestamp client làm version | Đồng hồ lệch hoặc hai update trùng độ phân giải | Dùng version/concurrency token đáng tin |
| Retry conflict vô hạn | Tăng tải và starvation | Giới hạn retry, merge hoặc chuyển xử lý tuần tự |
| Tự merge mọi field | Vi phạm invariant và rule nghiệp vụ | Chỉ merge field có quy tắc an toàn |
| Coi compensation là rollback | Lịch sử và side effect ngoài hệ thống không biến mất | Tạo business action bù có audit |
| Timeout bị coi là thất bại chắc chắn | Thu tiền/đặt chỗ lặp | Trạng thái UNKNOWN và reconciliation |
| Compensation không idempotent | Hoàn tiền hoặc giải phóng tài nguyên nhiều lần | Compensation key và operation state |
| Không theo dõi Saga đang bù | Quy trình treo mà không ai biết | Alert theo age/status và manual review |
| Chia invariant qua nhiều DB quá sớm | Saga phức tạp chỉ để làm một thao tác lẽ ra atomic | Xem lại consistency boundary và domain ownership |
| Read model stale được dùng làm quyết định ghi | Chấp nhận giao dịch sai | Kiểm tra source of truth ở critical command |

## 18. Checklist review thiết kế

### Xung đột cập nhật và optimistic concurrency

- [ ] Invariant nghiệp vụ và dữ liệu sở hữu đã được xác định.
- [ ] Mọi đường ghi đều dùng version/concurrency token hoặc cơ chế atomic tương đương.
- [ ] Conditional update được thực thi trong database/storage operation nguyên tử.
- [ ] API có semantics rõ cho 409, 412 hoặc 428 theo loại conflict.
- [ ] Client đọc lại, merge hoặc yêu cầu người dùng; không retry mù.
- [ ] Version tăng ở API, worker, batch và các công cụ ghi khác.
- [ ] Có concurrency test và metric conflict/retry.

### Compensation và Saga

- [ ] Các local transaction và thứ tự workflow được mô tả.
- [ ] Mỗi bước có timeout, retry policy và trạng thái rõ.
- [ ] Mỗi hành động có thể bù đã xác định compensation, precondition và owner.
- [ ] Compensation có idempotency key và lưu provider/reference.
- [ ] Timeout/unknown outcome có reconciliation trước khi lặp side effect.
- [ ] Có trạng thái COMPENSATING, UNKNOWN và MANUAL_REVIEW khi cần.
- [ ] DLQ/failed workflow có alert, runbook và người chịu trách nhiệm.
- [ ] Audit giữ lịch sử giao dịch gốc và giao dịch bù.

### Vận hành

- [ ] Có dashboard theo conflict, retry, Saga age, compensation success và pending operation.
- [ ] SLO phản ánh kết quả nghiệp vụ đầu cuối.
- [ ] Có fault-injection test cho từng cửa sổ lỗi quan trọng.
- [ ] Có hướng dẫn xử lý thủ công và đối soát khi provider không trả kết quả rõ.
- [ ] Chi phí retry, event, workflow và vận hành được tính vào cost per business operation.

## 19. Bài tập thực hành

**Bối cảnh:** hệ thống đặt xe cho thuê có một xe còn trống trong khoảng thời gian T. Hai khách đồng thời gửi yêu cầu đặt xe. Một request giữ xe thành công và bắt đầu thanh toán; provider thu tiền nhưng response bị timeout. Trong lúc đó, nhân viên hỗ trợ cập nhật reservation và email xác nhận có thể đã gửi.

Hãy thiết kế cách bảo vệ nhất quán:

1. Xác định invariant cần bảo vệ để không có hai reservation được xác nhận cho cùng xe và cùng khoảng thời gian.
2. Chọn cách bảo vệ: transaction/constraint, conditional update, optimistic version hoặc serialize command. Giải thích ranh giới dữ liệu.
3. Định nghĩa API read/update với version hoặc ETag/If-Match và hành vi khi nhận 412.
4. Nêu cách xử lý khi thay đổi của nhân viên và khách hàng xung đột; field nào có thể merge, field nào phải yêu cầu xem lại?
5. Mô hình hóa Saga đặt xe–thanh toán–xác nhận, gồm trạng thái UNKNOWN, compensation và manual review.
6. Thiết kế idempotency cho client retry, payment request, webhook, release hold và refund.
7. Xác định cách đối soát trường hợp provider đã thu tiền nhưng response mất.
8. Nêu hành vi nếu email đã gửi trước khi booking bị hủy hoặc bù trừ.
9. Xây dựng concurrency tests và fault-injection scenarios.
10. Đặt dashboard/SLO cho conflict rate, pending age, refund completion và tỷ lệ đặt xe thành công.

**Gợi ý tự kiểm tra:** Không dùng kết quả search/read availability làm bằng chứng cuối cùng khi ghi booking; thao tác giữ chỗ cần có tính nguyên tử hoặc được serialize. Không coi payment timeout là payment decline. Không thể thu hồi email đã gửi bằng rollback database. Mỗi bước bù phải là một thao tác nghiệp vụ có owner, idempotency và audit.

## 20. Ghi nhớ

**Optimistic concurrency** bảo vệ cập nhật dựa trên phiên bản mới nhất bằng conditional write; khi phát hiện conflict, caller cần đọc lại, hợp nhất theo rule hoặc yêu cầu quyết định mới. Cơ chế này phù hợp khi xung đột đủ thấp và không cần giữ lock trong thời gian người dùng chỉnh sửa.

**Compensation** xử lý hiệu ứng đã commit trong một quy trình phân tán mà không có transaction toàn cục. Nó tạo hành động nghiệp vụ mới, có thể thất bại hoặc cần đối soát, nên cần state machine/Saga, idempotency, timeout, retry có giới hạn và manual recovery. Thiết kế tốt bắt đầu từ invariant và consistency boundary, rồi kiểm chứng các race condition và lỗi từng phần bằng test cùng số liệu vận hành.
