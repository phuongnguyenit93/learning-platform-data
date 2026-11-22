# Kiểm thử timeout, retry, thông điệp trùng và sai thứ tự

Trong hệ thống microservices, một request có thể đi qua nhiều dịch vụ, mạng, hàng đợi và cơ sở dữ liệu. Những thành phần đó không cùng có một đồng hồ, không luôn trả lời đúng hạn và không cung cấp một cam kết thứ tự duy nhất cho mọi sự kiện. Một lời gọi có thể **timeout dù phía nhận đã hoàn tất**; retry có thể tạo hai lệnh giống nhau; một message có thể được phát lại sau khi xử lý thành công; sự kiện phiên bản mới có thể đến trước phiên bản cũ.

Vì thế, kiểm thử luồng thành công một lần chưa đủ. Bài này xây dựng **chiến lược kiểm thử có thể tái lập** cho bốn tình huống liên quan chặt chẽ: timeout, retry, thông điệp trùng và thông điệp sai thứ tự. Trọng tâm là chứng minh *tính đúng đắn của nghiệp vụ* khi có lỗi, không chỉ kiểm tra HTTP status hoặc số lần gọi hàm.

Các ví dụ dùng hệ thống Order, Payment và Inventory của kiến trúc microservices. Mã Java và SQL được nêu như ví dụ học tập, cần điều chỉnh theo transaction boundary, broker, SDK và hợp đồng thực tế của dự án.

## 1. Kết quả học tập

Sau bài học, người học có thể:

- Mô tả vì sao timeout không chứng minh một thao tác đã thất bại ở phía server và vì sao retry cần cơ chế idempotency.
- Thiết kế test cho connect timeout, response timeout, deadline tổng, retry có giới hạn, backoff và trường hợp retry không an toàn.
- Chủ động tạo duplicate delivery, replay sau crash, message đến trễ và message đảo thứ tự.
- Xác định business invariant: không charge hai lần, không trừ kho hai lần, không ghi lùi trạng thái và không mất sự kiện phải xử lý.
- Phân biệt kiểm thử ở unit, integration, contract, consumer, end-to-end và fault injection.
- Dùng fake clock, fake transport, proxy, broker thử nghiệm và cơ sở dữ liệu thật trong phạm vi phù hợp để có test ổn định.
- Đặt tiêu chí pass/fail dựa trên trạng thái dữ liệu, dấu vết side effect và thời gian phục hồi.

## 2. Mô hình lỗi: điều gì thực sự xảy ra?

Hãy xét lời gọi từ Order Service đến Payment Service:

~~~text
Order Service           Network            Payment Service
     |                      |                      |
     |---- charge(order) -->|--------------------->|
     |                      |                tạo charge
     |                      |<---- response ------|
     |<--- response --------|                      |
     |                      |                      |
~~~

Trong một lần chạy bình thường, Order nhận kết quả và lưu trạng thái đơn. Nhưng mạng có thể làm mất **request**, mất **response** hoặc làm response chậm hơn deadline của người gọi. Ba kịch bản tạo hậu quả khác nhau:

| Hiện tượng | Điều người gọi biết | Điều có thể xảy ra ở phía nhận |
|---|---|---|
| Không kết nối được trước khi gửi | Chưa nhận response; có thể biết kết nối thất bại | Thao tác thường chưa được gửi, nhưng cần hiểu chính xác tầng transport |
| Request đã gửi, caller timeout | Không biết kết quả cuối | Có thể chưa nhận, đang xử lý hoặc đã commit |
| Server trả 5xx | Nhận response lỗi | Có thể rollback, nhưng cũng có thể side effect đã xảy ra trước khi lỗi trả về |
| Response thành công bị mất | Caller thấy timeout | Server đã hoàn tất, nếu retry có thể thực thi lại |
| Consumer commit DB rồi crash trước khi ACK message | Broker thấy message chưa ACK | Business DB đã cập nhật, message sẽ có thể được phát lại |
| Hai message cùng aggregate đến ngược thứ tự | Consumer vẫn nhận đủ hai message | Nếu áp dụng mù, state cuối có thể bị ghi lùi |

Đây là nền tảng của các bài test: **quan sát của caller không luôn đồng nhất với trạng thái ở callee**. Đặc biệt, “timeout” mô tả việc *ngừng chờ*, không mặc nhiên có nghĩa “server hủy giao dịch”.

### Fault, failure, outcome và recovery

- **Fault:** điều kiện được tạo ra, ví dụ độ trễ mạng 2 giây, HTTP 503, mất ACK hoặc cố tình gửi lại một message.
- **Failure:** yêu cầu không đáp ứng hợp đồng, ví dụ trả kết quả quá deadline hoặc phát sinh charge trùng.
- **Outcome:** trạng thái thực tế sau xử lý, có thể thành công, thất bại hoặc chưa biết đối với caller.
- **Recovery:** hệ thống kết thúc trạng thái chưa biết bằng retry an toàn, tra cứu kết quả, reconciliation hoặc replay mà vẫn giữ bất biến nghiệp vụ.

Test cần đo outcome từ nguồn đáng tin: DB, fake provider lưu lệnh, trạng thái aggregate, event store, consumer offset hoặc audit; chỉ dựa vào response từ caller có thể bỏ qua tác động thực tế.

## 3. Dựng ví dụ nghiệp vụ và bất biến cần bảo vệ

Giả sử một đơn hàng đi qua các bước:

~~~text
POST /orders
    |
    v
Order Service -- reserve --> Inventory Service
    |
    v
OrderCreated event
    |
    v
Payment Service -- charge --> Payment Provider
    |
    v
PaymentCompleted / PaymentFailed event
    |
    v
Order Projection cập nhật trạng thái
~~~

Một order có `orderId`, một lệnh charge có `paymentAttemptId`, mỗi event có `eventId`, `aggregateId` và `aggregateVersion`. Các ID này phục vụ những mục đích khác nhau:

| ID | Mục đích |
|---|---|
| orderId | Nhận diện entity nghiệp vụ |
| idempotencyKey hoặc paymentAttemptId | Nhận diện cùng một thao tác qua những lần retry |
| eventId | Nhận diện cùng một event bị deliver nhiều lần |
| aggregateVersion / sequence | Xác định thứ tự cập nhật theo một aggregate |
| traceId / correlationId | Truy vết kỹ thuật; không nên mặc định dùng làm khóa idempotency |

**Business invariants** là các điều kiện phải đúng trong mọi lịch thực thi được kiểm thử:

1. Một payment attempt chỉ tạo tối đa một charge thực ở provider.
2. Một event `InventoryReserved` bị phát lại không trừ kho lần thứ hai.
3. Trạng thái Order không bị quay về trạng thái cũ bởi một event đến trễ.
4. Message đã ACK chỉ khi trạng thái yêu cầu đã được lưu bền vững theo hợp đồng xử lý.
5. Retry không vượt giới hạn về số lần thử, tổng deadline và lưu lượng bổ sung.
6. Event gap không bị lặng lẽ đánh dấu “đã xử lý” nếu logic yêu cầu đủ các phiên bản liên tiếp.
7. Event không hợp lệ không được coi là thành công chỉ vì handler không ném exception.

Test tốt biến từng invariant thành assertion đọc được từ trạng thái hệ thống. Ví dụ: `count(charges where paymentAttemptId = X) == 1` có ý nghĩa hơn `HTTP 200` vì endpoint có thể trả kết quả thành công dù đã charge hai lần.

## 4. Kiểm thử timeout: cần mô phỏng nhiều điểm lỗi

Timeout tồn tại tại nhiều tầng:

- **Connection timeout:** chưa thiết lập được kết nối đến địa chỉ đích trong thời hạn cho phép.
- **Read/response timeout:** kết nối đã có, request có thể đã gửi nhưng chậm nhận dữ liệu phản hồi.
- **Request deadline:** tổng thời gian ngân sách cho cả nghiệp vụ, bao gồm queue, retry và mọi downstream call.
- **Timeout từ broker/worker:** hết thời hạn lease, visibility timeout hoặc thời gian ACK; message có thể được giao lại.
- **Timeout nghiệp vụ:** đơn chờ thanh toán quá lâu, reservation hết hạn, saga cần bù trừ.

Không nên gộp tất cả vào một trường hợp “server sleep lâu rồi kiểm tra exception”. Các loại timeout có hệ quả khác nhau về side effect và recovery.

### 4.1. Ngân sách thời gian cho nhiều hop

Giả sử API Gateway cho phép tối đa 2.000 ms để trả phản hồi. Order phải gọi Inventory và Payment; không thể đặt 2.000 ms cho **mỗi** downstream rồi kỳ vọng toàn bộ request dưới 2.000 ms.

~~~text
Deadline tổng: 2.000 ms
|-- Xác thực / xác minh:   150 ms
|-- Reserve Inventory:    550 ms
|-- Charge Payment:       800 ms
|-- Lưu trạng thái:       250 ms
|-- Dự phòng:             250 ms
                         ------
                         2.000 ms
~~~

Các con số chỉ minh họa cách lập ngân sách, không phải cấu hình bắt buộc. Với gọi song song, cần xét critical path thay vì chỉ cộng cơ học; với gọi tuần tự, tổng thời gian phải tính cả thời gian chờ backoff.

**Test:** đưa Inventory vào tình trạng phản hồi sau 1.200 ms. Xác nhận Order không tiếp tục gọi Payment sau khi deadline đã hết; kết nối và tài nguyên được giải phóng; client nhận lỗi/trạng thái rõ ràng trong thời gian cho phép. Nếu phía Inventory vẫn xử lý sau khi caller ngừng chờ, dữ liệu phải còn nhất quán.

### 4.2. Các test case timeout cụ thể

| ID | Tình huống được tiêm | Assertion cần có |
|---|---|---|
| T01 | Không kết nối được Inventory | Có timeout/fail fast theo chính sách; không kẹt thread vô hạn |
| T02 | Inventory nhận request nhưng trì hoãn response | Deadline tổng được giữ; caller không tự coi thao tác chắc chắn thất bại |
| T03 | Inventory commit reservation rồi response bị bỏ | Retry/tra cứu không reserve hai lần |
| T04 | Payment response về ngay sau deadline | Không tạo charge thứ hai khi xử lý kết quả muộn và retry |
| T05 | Nhiều request đồng thời timeout | Pool, queue và connection không tăng vô hạn; request khác còn phục vụ |
| T06 | Chậm ở hop đầu, deadline còn ít ở hop sau | Truyền deadline còn lại hoặc từ chối bắt đầu bước không thể hoàn thành |
| T07 | Worker ACK timeout sau khi DB commit | Redelivery không ghi thay đổi hai lần |
| T08 | Hủy request tại caller | Cancellation được truyền khi có hỗ trợ; không giả định hủy được side effect đã commit |

Quan sát độ trễ bằng thời gian đơn điệu (monotonic clock) cho đo duration; không dùng thời gian đồng hồ hệ thống dễ bị chỉnh để tính thời lượng. Trong unit test, ưu tiên fake clock hoặc scheduler ảo. Trong integration test, có thể dùng server/proxy thử nghiệm để chặn/trì hoãn response.

### 4.3. Phân biệt timeout với “unknown outcome”

Một ca quan trọng trong kiểm thử thanh toán:

~~~text
T0  Order gửi charge(paymentAttemptId=P-42)
T1  Provider nhận lệnh
T2  Provider ghi charge thành công
T3  Response bị cắt
T4  Order timeout
T5  Order thử lại cùng paymentAttemptId=P-42
T6  Provider trả kết quả của P-42, không tạo charge mới
~~~

Nếu provider không hỗ trợ idempotency theo key, Order phải có cơ chế tra cứu/hòa giải trạng thái và quy trình xử lý kết quả chưa biết. Chỉ cài retry theo mã timeout mà không bảo vệ side effect là một lỗi thiết kế.

## 5. Kiểm thử retry: đúng đối tượng, đúng số lần, đúng thời hạn

Retry có thể giúp vượt qua lỗi tạm thời, nhưng cũng có thể khuếch đại sự cố. Test phải xét đồng thời **khi nào retry**, **bao nhiêu lần**, **khoảng cách giữa các lần**, **khi nào dừng** và **tác động nghiệp vụ**.

### 5.1. Phân loại lỗi

| Phản hồi/lỗi | Hành vi retry điển hình | Lý do |
|---|---|---|
| Mất kết nối hoặc timeout trước khi biết outcome | Retry có điều kiện; bắt buộc bảo vệ thao tác có side effect | Outcome có thể chưa biết |
| HTTP 503, 502 hoặc 504 từ dependency | Có thể retry có giới hạn/backoff nếu endpoint cho phép | Thường là lỗi tạm thời, nhưng không đảm bảo thao tác chưa commit |
| HTTP 429 | Tôn trọng tín hiệu rate limit/Retry-After nếu có; áp dụng deadline | Tiếp tục gọi ngay làm tăng tắc nghẽn |
| HTTP 400 do payload sai | Không retry cùng payload | Không tự sửa lỗi validation |
| HTTP 401/403 do quyền | Thường không retry tự động; cần sửa danh tính/quyền | Có thể là lỗi cấu hình không tạm thời |
| Conflict có ngữ nghĩa nghiệp vụ | Cần quyết định theo API contract | Có thể cần đọc lại version/state thay vì thử mù |
| Message xử lý lỗi tạm thời | Retry/backoff rồi DLQ hoặc parking theo chính sách | Tránh vòng lặp vô hạn |
| Message bị lỗi dữ liệu không thể sửa | DLQ/quarantine và báo lỗi | Retry cùng payload không giúp khắc phục |

Không có bảng nào thay thế được hợp đồng của API. Ví dụ, một upstream trả 500 sau khi đã commit payment vẫn tạo kết quả chưa biết, nên retry chỉ an toàn khi có cùng idempotency key.

### 5.2. Backoff và jitter

Giả sử chính sách tối đa 3 lần thử **tổng cộng** (lần đầu + 2 retry), dùng exponential backoff và jitter:

~~~text
Attempt 1: gọi ngay
Nếu lỗi tạm thời:
    đợi ngẫu nhiên trong khoảng 0..100 ms
Attempt 2:
    nếu còn ngân sách deadline, gọi tiếp
    nếu lỗi tạm thời:
        đợi ngẫu nhiên trong khoảng 0..200 ms
Attempt 3:
    nếu còn ngân sách deadline, gọi lần cuối
Hết attempts hoặc deadline: dừng và trả kết quả lỗi/chưa xác định
~~~

Jitter giảm khả năng hàng nghìn client cùng retry vào đúng một thời điểm. Tổng số lần thử cần **có giới hạn**; số lần retry = số attempts - 1. Đặt tên cấu hình rõ ràng để tránh off-by-one.

Kiểm thử với fake scheduler nên xác nhận số lần thử, khoảng đợi nằm trong khoảng cho phép, việc không thử khi deadline không đủ, và không tạo quá nhiều yêu cầu đồng thời. Không nên test chính xác một số mili giây ngẫu nhiên; có thể inject nguồn random cố định và kiểm tra khoảng hợp lệ.

### 5.3. Retry amplification

Nếu Order nhận 100 request/giây, mỗi request gọi Inventory một lần, tải cơ sở là 100 downstream calls/giây. Nếu mọi request được phép thử tối đa 3 lần và luôn lỗi, hệ thống có thể tạo tới khoảng 300 lần gọi/giây ở trạng thái ổn định, chưa kể queue và các tầng trung gian cũng retry.

Nếu Gateway, Order và Inventory client **đều retry**, số lần gọi xấu nhất có thể nhân nhau. Do đó cần test retry **trên toàn đường request**, không chỉ ở một thư viện client.

Test áp dụng tải và lỗi tạm thời để quan sát:

- Số attempts trên một request và trên toàn hệ thống.
- Tỷ lệ request thành công sau retry.
- p95/p99 latency khi retry.
- Số kết nối/chờ trong pool và queue length.
- Retry budget, circuit breaker, bulkhead và rate limit có làm việc đúng không.
- Dependency phục hồi rồi thì retries có ngừng dồn tải bất thường không.

### 5.4. Test retry bằng double có kịch bản

Một cách nhanh là dùng scripted fake: lần gọi đầu trả lỗi tạm thời, lần hai thành công, lần ba không được gọi. Một fake khác trả lỗi mãi để test giới hạn. Một fake giả lập “server đã commit nhưng response mất” để xác nhận idempotency.

~~~java
// Pseudocode: fake client cho test, không phải adapter production.
final class ScriptedGateway {
    int calls = 0;

    Receipt charge(String idempotencyKey) {
        calls++;
        if (calls == 1) {
            throw new TemporaryNetworkException();
        }
        return Receipt.success("charge-42");
    }
}

// Assertion mong muốn với maxAttempts=3:
// receipt thành công; calls == 2;
// cùng một idempotencyKey qua mọi attempt;
// không vượt deadline tổng.
~~~

Một test chỉ có `calls == 2` chưa đủ khi side effect quan trọng: còn phải xem provider simulator có tạo đúng một charge và ứng dụng có cập nhật state nhất quán hay không.

## 6. Thông điệp trùng: “at least once” thực sự có nghĩa gì?

Trong nhiều hệ thống message broker, cấu hình phân phối **at least once** cho phép một message được gửi lại nếu consumer chưa xác nhận hoàn tất. Ngay cả khi producer gửi đúng một lần, consumer vẫn có thể nhận nhiều lần.

Ví dụ:

~~~text
Broker                   Consumer                 Database
   |-- Event E1 ----------->|
   |                        |-- UPDATE state ----->|
   |                        |<-- COMMIT ------------|
   |                        X  crash trước ACK
   |
   |-- Event E1 ----------->|  consumer khác nhận lại
   |                        |-- UPDATE lần nữa? --->|
~~~

Nếu UPDATE là “trừ 1 đơn vị tồn kho” không có bảo vệ, tồn kho bị trừ hai lần. Nếu UPDATE là “set trạng thái bằng cùng một giá trị” có thể có vẻ an toàn nhưng vẫn có thể lặp side effect khác như gửi email, phát lệnh thanh toán hoặc phát sự kiện mới.

**At least once không phải exactly once.** Một số broker hỗ trợ exactly-once trong một phạm vi nhất định, chẳng hạn transaction của log và offset, nhưng không tự động bảo đảm đúng một tác động đối với database hoặc hệ thống thanh toán bên ngoài. Kiểm thử phải đặt ranh giới của cam kết một cách rõ ràng.

### 6.1. Idempotency ở ba lớp

1. **Producer/API command:** cùng business command hoặc idempotency key không sinh nhiều tác động.
2. **Consumer:** cùng eventId gửi lại không làm thay đổi business state lần nữa.
3. **External side effect:** cùng thanh toán/gửi yêu cầu sang provider được nhận diện bằng khóa nghiệp vụ ổn định hoặc được hòa giải khi outcome không rõ.

Không nên đồng nhất **eventId** với **business operation ID**. Nếu retry của producer tạo ra hai event khác ID nhưng cùng nội dung “charge order X”, dedup theo eventId không ngăn hai charge. Cần invariant theo khóa nghiệp vụ.

### 6.2. Inbox / processed-event trong cùng transaction

Một thiết kế thường dùng là bảng theo dõi event đã xử lý:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(200) NOT NULL,
    processed_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Luồng xử lý mong muốn:

~~~text
BEGIN TRANSACTION
  Thử INSERT (consumerName, eventId) vào processed_message
  Nếu đã tồn tại:
      không áp dụng business update lần nữa
      COMMIT và ACK như một duplicate hợp lệ
  Nếu mới:
      kiểm tra dữ liệu, version và trạng thái nghiệp vụ
      cập nhật business DB
      ghi outbox event nếu cần phát sự kiện tiếp
      COMMIT
ACK sau khi transaction commit thành công
~~~

Ý tưởng là **dedup record, business update và outbox phải cùng transaction database** nếu chúng thuộc cùng ranh giới nhất quán. Nếu ghi “đã xử lý” trước rồi business update thất bại, replay có thể bị bỏ qua và mất nghiệp vụ. Nếu business update commit trước rồi ghi dedup thất bại, replay có thể làm trùng side effect.

Ví dụ lệnh kiểu PostgreSQL:

~~~sql
BEGIN;

-- Chỉ một worker giành quyền xử lý event trong một transaction.
INSERT INTO processed_message (consumer_name, event_id)
VALUES ('order-projection', 'evt-001')
ON CONFLICT DO NOTHING;

-- Kiểm tra số dòng vừa insert bằng API database.
-- Nếu là 0: message đã xử lý; không chạy business update.
-- Nếu là 1: kiểm tra state/version rồi cập nhật projection,
-- và ghi transactional outbox khi cần.

COMMIT;

-- ACK broker chỉ sau khi COMMIT thành công.
~~~

Đây là phác thảo transactional workflow; code thật phải xử lý rollback, lỗi SQL và transaction isolation. Một record “processed” nên tương ứng với business effect đã commit, không chỉ “handler vừa được gọi”.

### 6.3. Những tình huống duplicate cần kiểm thử

| ID | Kịch bản | Kỳ vọng |
|---|---|---|
| D01 | Cùng eventId gửi liên tiếp hai lần | Business update xảy ra đúng một lần |
| D02 | Cùng eventId gửi song song ở hai consumer instance | Unique constraint/transaction chặn cập nhật trùng |
| D03 | Consumer crash trước database commit | Message phát lại và xử lý thành công |
| D04 | Consumer commit DB, crash trước ACK | Message phát lại nhưng không tạo side effect lần nữa |
| D05 | Producer resend cùng lệnh với cùng business key, eventId khác | Business invariant vẫn ngăn thao tác trùng |
| D06 | Redelivery sau khi consumer rebalance/restart | Không mất event, không nhân đôi side effect |
| D07 | Event hợp lệ nhưng external provider timeout sau khi đã xử lý | Dùng cùng idempotency key hoặc reconciliation |
| D08 | EventId rỗng hoặc bị tái sử dụng sai | Chặn input không hợp lệ, không gây silent corruption |

Phải kiểm tra cả bảng lưu business, bảng dedup, outbox, kết quả provider fake và trạng thái broker/ACK. Kiểm tra chỉ một bảng có thể bỏ sót side effect ngoài transaction.

## 7. Sai thứ tự: cần xác định “thứ tự nào?”

Distributed systems không mặc nhiên có thứ tự tổng thể cho mọi sự kiện. Cần định nghĩa thứ tự mà nghiệp vụ thật sự đòi hỏi, thường là **theo một aggregate**, ví dụ Order-123.

Giả sử Order Projection cần xử lý:

~~~text
E1: OrderCreated         order=O-123, version=1
E2: PaymentAuthorized    order=O-123, version=2
E3: OrderCompleted       order=O-123, version=3
~~~

Thứ tự đúng: E1 → E2 → E3. Nhưng vì các producer, retry topic hoặc consumer concurrency, hệ thống có thể quan sát E3 → E1 → E2. Nếu handler đơn giản đặt status từ mỗi event, kết quả có thể sai hoặc bị ghi lùi.

Trong Kafka, message cùng partition được lưu theo thứ tự của partition đó. Tuy nhiên không có thứ tự tổng thể giữa các partition, và việc chuyển sang retry topic, nhiều consumer xử lý song song hoặc nguồn event khác nhau vẫn có thể làm ứng dụng thấy thứ tự không như kỳ vọng. Đặt partition key theo aggregate giúp giữ thứ tự trong một luồng được cấu hình đúng, nhưng không thay thế kiểm tra version tại consumer.

### 7.1. Chọn chiến lược xử lý

| Chiến lược | Phù hợp khi | Rủi ro cần kiểm thử |
|---|---|---|
| Partition/queue theo aggregateId | Muốn các event cùng entity đi trên một luồng có thứ tự | Repartition, concurrency, retry topic, producer ordering |
| Version tăng đơn điệu + kiểm tra version | Projection cần áp dụng chính xác thứ tự thay đổi | Gap, event thiếu, replay, optimistic lock |
| Giữ event đến sớm trong buffer | Có thể chờ phiên bản còn thiếu trong giới hạn | Buffer vô hạn, memory leak, gap không bao giờ lấp |
| Bỏ stale event | Event phiên bản thấp đã được supersede và logic cho phép | Bỏ nhầm side effect bắt buộc |
| Rebuild projection từ event log | Có nguồn event bền vững và deterministic reducer | Thời gian rebuild, schema migration, snapshot cũ |
| Thiết kế phép cập nhật giao hoán | Phép toán độc lập thứ tự, phù hợp với dữ liệu | Không phải nghiệp vụ nào cũng giao hoán/đơn điệu |

**Không áp dụng “bỏ qua event cũ” cho mọi loại message.** Ví dụ `PaymentAuthorized` và `RefundIssued` là các sự kiện nghiệp vụ khác nhau. Nếu mỗi sự kiện có side effect cần thực hiện, việc bỏ qua theo timestamp hoặc tên trạng thái có thể làm mất bước hoàn tiền. Cần mô hình state machine, version hoặc ledger phù hợp.

### 7.2. Gap detection

Nếu projection đang ở version 3 và nhận version 5:

- Không được coi version 5 là version 4 rồi cập nhật state nếu hợp đồng đòi đủ mọi transition.
- Có thể lưu/park version 5, chờ version 4 trong giới hạn cho phép.
- Nếu gap kéo dài, có thể tái đọc event log, yêu cầu replay, resync snapshot hoặc chuyển sang hàng đợi cần can thiệp.
- Chỉ đánh dấu version 5 đã áp dụng khi điều kiện nghiệp vụ thực sự thỏa mãn.

Nếu nhận event version 2 khi projection đã ở version 5, đó có thể là stale/replay; cách xử lý phải nhất quán với hợp đồng consumer. EventId đã xử lý nên được nhận diện là duplicate; event chưa xử lý nhưng version cũ có thể cần điều tra hoặc được bỏ qua một cách có chủ đích nếu business logic cho phép.

### 7.3. Không dùng thời gian nhận làm thứ tự nghiệp vụ

**receivedAt** chỉ cho biết consumer thấy event lúc nào; nó không bảo đảm thứ tự tạo hoặc commit của nghiệp vụ. **eventCreatedAt** có thể bị ảnh hưởng bởi đồng hồ lệch, queue, retry và nhiều producer. Nếu cần thứ tự chính xác của một aggregate, ưu tiên sequence/version được phát hành tại nguồn có thẩm quyền, hoặc thứ tự log được định nghĩa trong cùng transaction boundary.

## 8. Ví dụ Java: kiểm thử duplicate và out-of-order có thể tái lập

Ví dụ dưới đây minh họa reducer in-memory để làm rõ hành vi; production cần transaction, unique constraint, durable inbox và cơ chế chịu concurrent consumers.

~~~java
import java.util.HashSet;
import java.util.Set;

record OrderEvent(String eventId, String orderId, long version, String status) {}

enum ApplyResult {
    APPLIED, DUPLICATE, STALE, GAP
}

final class OrderProjection {
    private final Set<String> processedEvents = new HashSet<>();
    private long currentVersion = 0;
    private String status = "NONE";

    ApplyResult apply(OrderEvent event) {
        if (processedEvents.contains(event.eventId())) {
            return ApplyResult.DUPLICATE;
        }
        if (event.version() <= currentVersion) {
            return ApplyResult.STALE;
        }
        if (event.version() != currentVersion + 1) {
            return ApplyResult.GAP;
        }

        // Ví dụ đơn giản cho đúng một order, không dùng làm store production.
        status = event.status();
        currentVersion = event.version();
        processedEvents.add(event.eventId());
        return ApplyResult.APPLIED;
    }

    long version() {
        return currentVersion;
    }

    String status() {
        return status;
    }
}
~~~

Test với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class OrderProjectionTest {
    @Test
    void holdsFutureEventAndIgnoresDuplicateWithoutRegressing() {
        var projection = new OrderProjection();

        var created = new OrderEvent("evt-1", "order-42", 1, "CREATED");
        var paid = new OrderEvent("evt-2", "order-42", 2, "PAID");

        assertEquals(ApplyResult.GAP, projection.apply(paid));
        assertEquals(0, projection.version());

        assertEquals(ApplyResult.APPLIED, projection.apply(created));
        assertEquals(ApplyResult.DUPLICATE, projection.apply(created));

        assertEquals(ApplyResult.APPLIED, projection.apply(paid));
        assertEquals(ApplyResult.STALE, projection.apply(
            new OrderEvent("evt-old", "order-42", 1, "CREATED")
        ));

        assertEquals(2, projection.version());
        assertEquals("PAID", projection.status());
    }
}
~~~

Test cố tình gọi version 2 **trước** version 1; nếu code cứ ghi status mới nhất theo thời gian nhận, assertion sẽ phát hiện sai. Nó cũng chứng minh rằng event gây GAP không bị ghi vào `processedEvents`, nên có thể xử lý sau khi event còn thiếu xuất hiện.

**Giới hạn mô hình:** code chỉ chứa một projection cho một order, không có lock hay DB; Set trong memory biến mất khi restart. Trong production, dùng `orderId` để định tuyến đúng aggregate, state có persistence, transactional write và ràng buộc version/uniqueness. Đừng dùng đoạn demo để khẳng định chịu được xử lý song song hoặc crash.

## 9. Ví dụ kiểm thử xử lý DB và ACK sau khi crash

Một consumer production thường đi qua các mốc:

~~~text
A. Broker deliver event E1
B. Consumer bắt đầu DB transaction
C. Ghi dedup record
D. Cập nhật business state và outbox
E. Commit DB transaction
F. ACK broker
~~~

Đặt fault tại từng điểm tạo ra các test có giá trị:

| Điểm crash | Trạng thái DB | Broker có thể làm gì? | Assertion |
|---|---|---|---|
| Trước B | Chưa thay đổi | Redeliver E1 | E1 được xử lý về sau |
| Giữa C và D nhưng chưa commit | Transaction rollback | Redeliver E1 | Không bị đánh dấu đã xử lý vĩnh viễn |
| Sau D nhưng trước E | Transaction rollback nếu cùng DB transaction | Redeliver E1 | Không có partial commit |
| Sau E, trước F | Business effect đã commit | Redeliver E1 | Không nhân đôi effect |
| Sau F | DB đã commit | Không cần redeliver thông thường | State bền vững đúng |

Nếu dùng provider ngoài như cổng thanh toán, external effect không nằm trong cùng transaction với database. Lúc đó cần outbound idempotency key, transactional outbox để ghi intent và một worker giao tiếp provider, hoặc reconciliation. Một database transaction riêng không thể tự làm cho hai hệ thống độc lập trở thành một atomic transaction.

### 9.1. Kiểm thử đồng thời

Hai consumer có thể nhận cùng message do rebalance, retry hoặc cơ chế điều phối sai. Test đơn luồng với Set in-memory không chứng minh an toàn đồng thời.

Thử nghiệm nên chạy hai worker với cùng `eventId`, dùng barrier để hai worker cùng tới bước insert dedup, rồi thả đồng thời. Kết quả cần có:

- Unique constraint chỉ cho một transaction giành quyền xử lý.
- Worker còn lại không chạy business effect lần hai.
- Không tồn tại trạng thái dedup đã commit nhưng business effect chưa commit.
- Khi một worker rollback, worker còn lại hoặc redelivery vẫn có đường xử lý thành công.

Không nên dùng `Thread.sleep(100)` để “hy vọng” hai worker đụng nhau. Barrier/latch làm điều kiện giao nhau rõ ràng và tái lập được.

## 10. Lập chiến lược test theo lớp

Không phải kịch bản nào cũng cần môi trường microservices đầy đủ. Chọn lớp kiểm thử theo bằng chứng cần thu được:

| Lớp test | Công cụ/kỹ thuật phù hợp | Điều xác minh |
|---|---|---|
| Unit | Fake clock, scripted fake, in-memory reducer | Quyết định retry, deadline, phân loại lỗi, state transition |
| Component | Embedded/fake server, test application context | HTTP client, exception mapping, retry interceptor, cancellation |
| Integration | Database thật hoặc test container, broker thử nghiệm | Transaction, unique constraint, redelivery, ACK, version, serialization |
| Contract | API/message schema, mã lỗi, idempotency contract | Hai phía hiểu cùng một ngữ nghĩa timeout/retry/event |
| End-to-end | Nhiều service trong staging và test provider | Business invariant xuyên service |
| Fault injection | Proxy/chaos job có giới hạn, network delay/drop/reset | Cơ chế thực tế khi latency, mất response hoặc restart |

Nguyên tắc thực dụng: lỗi thuần logic nên test ở lớp thấp để có phản hồi nhanh; lỗi phụ thuộc transaction/ACK cần kiểm chứng với tài nguyên thật; lỗi mạng/cụm chỉ có thể kết luận ở lớp môi trường tương ứng.

Test với mock `paymentClient.charge()` trả success hai lần không thể chứng minh provider thực sự deduplicate key. Cần contract/integration với fake provider lưu lịch sử charge, hoặc sandbox của nhà cung cấp nếu được hỗ trợ.

## 11. Thiết kế thí nghiệm có thể tái lập

### 11.1. Kiểm soát đầu vào

Ghi rõ:

- Identity của request, order và event: `orderId`, `eventId`, `idempotencyKey`.
- Phiên bản aggregate, thứ tự message đã gửi và thứ tự deliver dự kiến.
- Lịch trả lời của fake/proxy: thành công, 503, latency, drop response.
- Tải và concurrency: một request, nhiều request, hai worker cùng xử lý.
- Chính sách retry: max attempts, backoff, jitter, deadline.
- Trạng thái ban đầu: DB, inbox/outbox, offset, provider side-effect ledger.
- Trạng thái cuối và side effect count mong đợi.

### 11.2. Dùng fake clock và scheduler có điều khiển

Với backoff, clock thật và `Thread.sleep` tạo test chậm hoặc không ổn định. Fake clock cho phép dịch thời gian chủ động để kiểm tra:

~~~text
deadline = 1.000 ms
attempt 1 bắt đầu t=0, kết thúc lỗi t=100
backoff = 200 ms -> attempt 2 bắt đầu t=300
attempt 2 timeout tại t=800
backoff kế tiếp = 400 ms
t=1.200 > deadline -> KHÔNG chạy attempt 3
~~~

Chú ý: nếu scheduler và HTTP client dùng đồng hồ khác nhau, fake clock một phía chưa đủ để kiểm chứng deadline thật. Trong unit test có thể mô phỏng thuần logic; integration test dùng timeout thực tế với biên an toàn phù hợp.

### 11.3. Kiểm soát thứ tự deliver

Với event E1, E2, E3, thay vì chờ broker tình cờ đảo thứ tự, xây fake delivery cho các lịch:

~~~text
[E1, E2, E3]          -- bình thường
[E1, E1, E2, E3]      -- duplicate
[E2, E1, E3]          -- đảo thứ tự
[E1, E3, E2]          -- gap rồi recovery
[E3, E2, E1]          -- đảo toàn bộ
[E1, E2, crash, E2, E3] -- redelivery sau crash
~~~

Với `n` event nhỏ, có thể chạy mọi hoán vị hữu hạn hoặc property-based testing. Điều quan trọng là định nghĩa kết quả cho từng lịch, thay vì giả định tất cả cách sắp xếp phải trả “success ngay”.

### 11.4. Test theo seed

Nếu kiểm thử có random latency/jitter, đặt seed và ghi lại seed khi test thất bại. Với lỗi khó tái lập, lưu chuỗi fault đã chọn và lịch event thực tế. Mục tiêu là có thể dựng lại lịch gây lỗi một cách quyết định.

## 12. Test matrix tổng hợp timeout, retry, trùng và sai thứ tự

Bốn hiện tượng thường phối hợp với nhau. Ma trận dưới đây là bộ kịch bản khởi đầu, có thể điều chỉnh theo hợp đồng:

| Case | Fault / lịch thực thi | Điều cần khẳng định |
|---|---|---|
| M01 | Inventory trả 503 một lần rồi thành công | Retry hợp lệ, không quá giới hạn, không nhân đôi reservation |
| M02 | Inventory chậm hơn timeout nhưng chưa commit | Caller dừng đúng deadline; không leak connection |
| M03 | Inventory commit rồi mất response | Retry cùng key hoặc reconciliation, chỉ reserve một lần |
| M04 | Payment charge thành công rồi Order timeout | Không có charge thứ hai, trạng thái có thể xác minh |
| M05 | HTTP 400 liên tục | Không retry vô ích |
| M06 | HTTP 429 với Retry-After vượt deadline | Dừng khi hết budget, không gọi muộn |
| M07 | Hai consumer xử lý E1 song song | Exactly one business effect nhờ transaction/unique key |
| M08 | DB commit rồi consumer crash trước ACK | Replay được nhận diện, state không thay đổi lần hai |
| M09 | E2 đến trước E1 | Không áp dụng sai state; sau E1 có thể xử lý lại E2 |
| M10 | E3 đến trước E1 và E2 | Gap được giữ/quản lý; không mất event |
| M11 | E1 bị lặp sau khi đã xử lý E3 | Không ghi lùi trạng thái |
| M12 | Retry topic đưa message cũ quay lại | Consumer xử lý stale/duplicate theo policy |
| M13 | Hai event có cùng business key nhưng eventId khác nhau | Không phát sinh side effect nghiệp vụ trùng |
| M14 | Một service retry trong khi upstream gateway cũng retry | Tổng số attempts vẫn nằm trong giới hạn hệ thống |
| M15 | Secret/dependency tạm thời unavailable trong retry window | Retry chỉ cho lỗi được phép, không tăng quyền hay bypass validation |
| M16 | Sau khi hết lỗi mạng, queue còn tồn | Backlog giảm; không mất event, không phát lại side effect |

Mỗi case cần viết rõ **setup → fault → action → observed outcome → assertion**. Không nên đánh dấu đạt chỉ vì test kết thúc mà không ném exception.

## 13. Cách viết assertion cho dữ liệu và side effect

Các assertion khác nhau trả lời những câu hỏi khác nhau:

**Đúng số lần tạo tác động:** fake provider có `chargeCountByKey("pay-42") == 1`; DB có một reservation hợp lệ cho order.

**Đúng số lần gọi downstream:** `attemptCount <= maxAttempts`. Có thể có nhiều lời gọi cho cùng key, miễn provider effect chỉ xảy ra một lần và chính sách cho phép.

**Đúng trạng thái cuối:** Order không bị chuyển từ `PAID` về `PENDING` bởi event cũ; projection version không giảm.

**Đúng xử lý gap:** event version 3 không được coi đã commit khi version 2 chưa đến, nếu contract yêu cầu tuần tự.

**Đúng phục hồi:** khi dependency hoạt động trở lại, retry/backoff và queue xử lý tiếp trong khoảng thời gian thiết kế.

**Đúng khi từ chối:** payload lỗi hoặc command không hợp lệ phải bị từ chối, có thể đưa DLQ/quarantine tùy chính sách, không tự xem là thành công.

Có thể hình dung bộ assertion ở cuối một integration test:

~~~text
assert order.status == "PAID"
assert order.version == 3
assert paymentProvider.countCharges(paymentAttemptId) == 1
assert inventory.reservationsFor(orderId) == 1
assert processedMessage.count(consumer, eventId) == 1
assert outbox.countBusinessEvent(orderId, "PAYMENT_COMPLETED") == 1
assert retryAttempts <= configuredMaxAttempts
assert noUnboundedPendingTasks
~~~

Các assertion là pseudocode biểu thị hợp đồng; không phải API của một framework cụ thể.

## 14. Transactional outbox và inbox liên quan thế nào?

Khi một service vừa cập nhật database vừa phát event, có lỗ hổng nếu làm hai thao tác không có ràng buộc:

~~~text
Update DB thành công
    |
Process crash
    |
Publish event chưa xảy ra  -> service khác không biết thay đổi
~~~

**Transactional outbox** ghi business state và record event cần phát trong cùng DB transaction. Một publisher riêng đọc outbox rồi gửi event. Publisher có thể gửi trùng nếu crash sau publish nhưng trước khi đánh dấu đã gửi, nên consumer vẫn cần idempotency.

**Inbox/processed message** giúp consumer không áp dụng lại cùng event sau redelivery. Hai mẫu phối hợp:

~~~text
Producer Transaction:
    business update + outbox event -> COMMIT

Outbox Publisher:
    publish to broker -> có thể publish lặp

Consumer Transaction:
    inbox/dedup + business update + next outbox -> COMMIT
    ACK broker sau COMMIT
~~~

Test cần đặt crash tại các ranh giới COMMIT/PUBLISH/ACK để xác minh không mất sự kiện và không nhân đôi tác động. Nếu external effect không nằm trong DB transaction, dùng stable idempotency key hoặc reconciliation tại điểm tích hợp đó.

Không nên kết luận “exactly once toàn hệ thống” từ việc bật một option của broker. Phải định nghĩa exactly once của **đối tượng gì**: event trong log, bản ghi DB, hay side effect ở nhà cung cấp ngoài.

## 15. Kiểm thử consumer với rebalancing, retry queue và dead-letter queue

### Rebalancing

Khi một consumer trong group dừng, partition có thể được chuyển cho worker khác. Nếu offset/ACK chưa phản ánh transaction đã commit, message có thể được giao lại. Test nên stop worker tại điểm sau DB commit nhưng trước ACK và xác minh worker kế tiếp deduplicate an toàn.

### Retry queue/topic

Một message lỗi có thể được đưa sang retry topic, còn những message mới hơn tiếp tục được xử lý trong luồng chính. Khi message cũ trở lại, thứ tự theo aggregate có thể bị thay đổi. Test cần kiểm tra policy: giữ thứ tự bằng cách park aggregate, chấp nhận event độc lập thứ tự, hoặc xử lý gap/stale có kiểm soát.

### Dead-letter queue

DLQ không phải “thùng rác” cho mọi lỗi. Cần biết message vì sao bị đưa vào DLQ, ai xử lý và cách replay tránh side effect trùng. Test một message lỗi dữ liệu để chắc chắn không retry vô hạn, ghi đủ context an toàn và có đường xử lý/khôi phục.

### Poison message

Một message luôn lỗi có thể chặn cả partition nếu ứng dụng nhất quyết xử lý tuần tự. Cần giới hạn retry, cảnh báo và cơ chế quarantine phù hợp với yêu cầu thứ tự. Test cả việc không làm mất message và không khiến mọi aggregate không liên quan bị nghẽn.

## 16. Quan sát hệ thống để hiểu test thất bại

Khi test chạy trên nhiều service, chỉ stack trace của một tiến trình không đủ. Kết hợp metric, trace và log có correlation:

| Tín hiệu | Ví dụ cần thu thập | Ý nghĩa |
|---|---|---|
| Request latency | p95/p99 của Order API | Độ trễ có bị retry làm tăng quá budget không? |
| Dependency attempts | `payment_client_attempts_total` theo outcome | Mỗi logical request tạo bao nhiêu downstream calls? |
| Timeout count | Client timeout, server timeout, broker lease expiry | Timeout xảy ra tại tầng nào? |
| Duplicate detection | Inbox conflict, idempotency hit | Có replay và dedup đúng không? |
| Ordering gap | Event version ahead of expected | Có message bị đảo thứ tự/chưa đến không? |
| Stale event | Version cũ đến sau | Có nguy cơ ghi lùi không? |
| DLQ backlog | Số message chờ xử lý | Có event bị tắc dài hạn không? |
| Business ledger | Số charge, reservation, refund | Side effect cuối có chính xác không? |

Trace nên có `correlationId`, tên operation và mã lỗi; log không nên chứa payload nhạy cảm, token hoặc thông tin thanh toán. Trong metric, không gắn mọi `orderId`/`eventId` làm label vì cardinality sẽ tăng mạnh; các ID chi tiết phù hợp với trace/log có kiểm soát hơn.

Thời điểm fault được bật/tắt cũng cần ghi nhận để liên hệ biểu đồ với tác nhân. Các test case khó tái lập nên lưu seed, lịch message và phiên bản phần mềm cùng tài nguyên kiểm thử.

## 17. Các lỗi thường gặp khi viết test

**Chỉ kiểm tra HTTP status.** Order API có thể trả 500 sau khi Payment đã charge thành công. Phải kiểm tra ledger side effect.

**Coi timeout là rollback.** Cắt response không đảm bảo dừng được server. Kiểm thử outcome sau timeout, xử lý unknown result.

**Retry mù trên thao tác không idempotent.** Có thể tạo đơn, charge hoặc email trùng. Chọn idempotency key ổn định, giới hạn retry và kiểm tra contract.

**Nhầm số attempts với số retries.** Cấu hình `maxAttempts=3` thường bao gồm lần thử đầu; cần chỉ rõ semantic trong test.

**Dựa vào sleep để tạo race.** Test khó tái lập, dễ pass giả. Dùng latch/barrier hoặc điều khiển scheduler.

**Giả lập duplicate bằng cách gọi một handler tuần tự rồi kết luận an toàn đồng thời.** Unique constraint và transaction cần integration test với worker song song.

**Mark event processed trước khi ghi business state.** Crash giữa hai bước làm message bị bỏ qua vĩnh viễn. Ghi cùng transaction nếu thuộc một DB.

**Dùng timestamp nhận để xử lý ordering.** Đồng hồ và network không cung cấp thứ tự nghiệp vụ đáng tin. Dùng sequence/version hoặc chiến lược aggregate thích hợp.

**Bỏ event đến trễ vô điều kiện.** Với event có side effect độc lập, bỏ qua có thể mất việc cần thực hiện. Hãy định nghĩa contract xử lý stale/gap.

**Cho rằng broker có exactly-once thì external provider chắc chắn exactly-once.** Phạm vi transaction của broker không bao phủ mọi hệ thống ngoài.

**Không thử trường hợp sau khi khắc phục lỗi.** Dừng network fault rồi phải quan sát queue recovery, cache, pool và dữ liệu có trở lại ổn định hay không.

**Test chạy với cùng dữ liệu thật.** Side effect như payment hoặc email nên dùng sandbox/fake provider và dữ liệu thử nghiệm cô lập.

## 18. Quy trình thực hành từ một giả thuyết cụ thể

Giả thuyết: *Khi Payment đã ghi nhận charge nhưng response bị mất, Order Service retry cùng một idempotency key, không tạo charge thứ hai; sau đó PaymentCompleted event bị phát hai lần và đến trước một event cũ, Order vẫn giữ trạng thái đúng.*

### Bước 1 — Chuẩn bị hệ thống thử nghiệm

Tạo `orderId=O-42`, `paymentAttemptId=P-42`. Dùng provider simulator lưu mọi request và mọi charge; dùng broker thử nghiệm hoặc harness có thể kiểm soát lịch deliver; dùng database staging/test với dữ liệu riêng.

### Bước 2 — Đặt baseline và điều kiện pass

Một charge duy nhất, một order cuối cùng ở `PAID`, không mất event, deadline và retry nằm trong chính sách. Phân biệt `attemptCount` (có thể lớn hơn một) với `chargeCount` (phải đúng một).

### Bước 3 — Tiêm lost response

Provider nhận charge thành công rồi cố tình không trả response đầu tiên. Xác nhận Order nhìn thấy timeout và retry giữ nguyên `paymentAttemptId`.

### Bước 4 — Tiêm redelivery

Cho consumer xử lý `PaymentCompleted(eventId=E-2)`, commit projection rồi giả lập mất ACK để broker phát lại E-2. Xác nhận inbox nhận diện duplicate và chỉ một business effect.

### Bước 5 — Tiêm out-of-order

Cho event version 3 đến trước version 2 trên một đường test kiểm soát. Kiểm tra projection không áp dụng sai hoặc ghi lùi; sau khi đủ event, state hội tụ về kết quả được hợp đồng xác định.

### Bước 6 — Quan sát sau khi bỏ fault

Khôi phục đường mạng và consumer. Theo dõi queue backlog, retry count, charge ledger, inbox/outbox và trạng thái Order. Nếu hệ thống chỉ hồi phục HTTP nhưng ledger sai, thí nghiệm thất bại.

### Bước 7 — Lưu bằng chứng

Ghi lịch fault, mã case, phiên bản ứng dụng, seed nếu có random, metric, trace, trạng thái database và kết quả provider simulator. Khi phát hiện lỗi, sửa đúng ranh giới rồi chạy lại cùng kịch bản.

## 19. Bài tập tự luyện

### Bài A — Deadline và retry budget

API Gateway có deadline 1.500 ms. Order gọi Inventory có timeout từng attempt là 900 ms; backoff 200 ms. Hãy xác định điều gì xảy ra khi attempt đầu dùng hết 900 ms, và đề xuất chính sách không gọi attempt mới nếu không còn thời gian hữu ích. Viết test với fake clock chứng minh số attempts và thời gian dừng phù hợp.

### Bài B — Duplicate giữa hai consumer

Hai worker cùng đọc event “ReserveStock” cho `orderId=O-17`, `eventId=E-17`. Hãy thiết kế schema unique key, transaction và concurrency test để chứng minh chỉ một reservation được tạo dù hai worker cùng tới điểm ghi gần như đồng thời. Thử thêm trường hợp worker thắng race rollback.

### Bài C — Message sai thứ tự

Một Order có các version 1, 2, 3 và nhận lịch `[3, 1, 2, 2, 3]`. Viết reducer/harness có version check và duplicate detection. Xác định lúc nào event 3 bị giữ do gap, lúc nào có thể xử lý lại, và vì sao version cuối không được giảm.

### Bài D — Lost response của thanh toán

Payment Provider đã tạo charge và mất response trước khi Order nhận được. Viết kịch bản kiểm thử cho hai trường hợp: provider hỗ trợ idempotency key; provider không hỗ trợ nhưng có API tra cứu. Mô tả dữ liệu tối thiểu cần lưu để không tự tạo charge mới với key khác khi kết quả chưa biết.

### Bài E — Retry topic gây đảo thứ tự

Message E1 lỗi tạm thời và được đưa sang retry topic; E2 của cùng aggregate đi tiếp trên topic chính. Thiết kế chiến lược đảm bảo consumer không áp dụng E2 sai. So sánh cách park aggregate, version gap detection và event handler có tính giao hoán.

Mỗi bài cần nêu **bất biến nghiệp vụ, fault được tiêm, cách đo kết quả và hành vi khôi phục**. Một test có thể đạt về latency nhưng vẫn không đạt về đúng đắn dữ liệu.

## 20. Tóm lược tư duy kiểm thử

Timeout nói rằng người gọi ngừng chờ; nó **không chứng minh** bên nhận chưa thực hiện thao tác. Retry giúp vượt lỗi tạm thời nhưng có thể khuếch đại tải và gây side effect trùng. At-least-once delivery cho phép replay, nên consumer cần idempotency và ranh giới transaction đúng. Sai thứ tự yêu cầu định nghĩa phiên bản, state transition và cách quản lý gap thay vì ghi đè bằng event đến cuối.

Một chiến lược kiểm thử đáng tin cậy dựng được các lịch lỗi chủ động, giữ chúng có thể tái lập và kiểm tra đồng thời **thời gian**, **số lần thử**, **bản ghi bền vững**, **side effect ngoài hệ thống** và **trạng thái phục hồi**. Chỉ khi các bất biến còn đúng qua timeout, retry, duplicate và out-of-order, hệ thống mới có bằng chứng thực tế về khả năng xử lý sự cố phân tán.
