# Peek-lock, settlement và gia hạn khóa message

Một hệ thống đặt hàng trên Azure thường gửi công việc từ API vào **Azure Service Bus Queue**, rồi các worker xử lý thanh toán, tạo hóa đơn hoặc gửi thông báo. Khi có nhiều worker, hệ thống phải đảm bảo một message không bị hai worker xử lý cùng lúc một cách bình thường. Nhưng nếu worker nhận được message rồi mất kết nối trước khi hoàn tất thì công việc cũng không được biến mất.

**Peek-Lock** trong Azure Service Bus giải quyết phần quan trọng của bài toán: broker giao message cho một consumer và tạm **khóa** nó trong thời gian hữu hạn. Consumer xử lý rồi chủ động thông báo kết quả qua các thao tác **settlement**: **Complete**, **Abandon**, **Dead-letter** hoặc **Defer**. Nếu công việc kéo dài, consumer có thể **gia hạn khóa (renew lock)** trước khi hết hạn.

Tuy nhiên, Peek-Lock **không tạo bảo đảm exactly-once cho nghiệp vụ**. Message có thể được giao lại sau khi khóa hết hạn, network bị lỗi hoặc thao tác settlement thất bại. Một thiết kế đáng tin cậy luôn kết hợp khóa message với **idempotency**, ghi trạng thái bền vững, retry có giới hạn và quan sát vận hành.

Bài học thuộc chương **Hàng đợi và thông điệp** của lộ trình **CLOUD_PROVIDERS_AZURE**: học hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, tính toán, lưu trữ, dữ liệu, triển khai, giám sát, bảo vệ và kiểm soát chi phí một ứng dụng trên Azure.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt ba thao tác **Peek**, **Peek-Lock receive** và **Receive-and-Delete**.
2. Giải thích vòng đời message từ **Active → Locked → Completed/Abandoned/Deferred/Dead-lettered**.
3. Lựa chọn đúng settlement cho thành công, lỗi tạm thời, lỗi dữ liệu vĩnh viễn và công việc cần xử lý sau.
4. Hiểu **LockDuration**, **LockedUntil**, **DeliveryCount**, **MaxDeliveryCount** và **LockToken**.
5. Sử dụng **manual lock renewal** hoặc **AutoLockRenewer** trong Python SDK theo giới hạn phù hợp.
6. Thiết kế consumer chịu được **MessageLockLost**, kết nối gián đoạn, xử lý trùng và lỗi sau khi đã tạo side effect.
7. Phân biệt **message lock** với **session lock** và nhận diện vấn đề prefetch/concurrency.
8. Kiểm tra queue, message counts, RBAC, private networking, metrics và chi phí bằng phương pháp an toàn.

## 1. Vì sao cần khóa message?

Giả sử queue **payment-jobs** có message **PAY-001**, yêu cầu ghi nhận thanh toán. Hai worker A và B đang nhận thông điệp.

Nếu broker xóa message ngay khi chuyển cho A, rồi A chết trước khi lưu giao dịch, công việc có thể bị mất. Nếu broker cho cả A lẫn B cùng xử lý bình thường, hệ thống có nguy cơ ghi thanh toán hai lần.

Peek-Lock đưa ra một thỏa hiệp:

~~~text
Service Bus Queue: payment-jobs
         |
         | receive bằng Peek-Lock
         v
Worker A nhận PAY-001
         |
         +--> Broker tạm khóa PAY-001
         |    Worker B không nhận cùng bản đang khóa theo luồng bình thường
         |
         +--> A xử lý và ghi trạng thái
                 |
                 +-- Thành công --> Complete
                 +-- Lỗi tạm --> Abandon / cho khóa hết hạn
                 +-- Dữ liệu hỏng --> Dead-letter
                 +-- Xử lý sau --> Defer
~~~

Khóa chỉ có **thời hạn**, vì broker không thể chờ mãi một worker đã crash. Nếu A không hoàn tất hoặc gia hạn kịp, broker có thể cho consumer khác nhận lại. Vì vậy ứng dụng không được coi việc đang giữ khóa là bằng chứng vĩnh viễn rằng chỉ mình nó có quyền thực hiện tác động nghiệp vụ.

## 2. Phân biệt Peek, Peek-Lock và Receive-and-Delete

Ba khái niệm có tên gần nhau nhưng ý nghĩa hoàn toàn khác.

| Thao tác/chế độ | Làm gì? | Message có bị khóa? | Rủi ro chính |
|---|---|---|---|
| **Peek** | Duyệt/xem message mà không nhận để xử lý | Không | Không phải cơ chế claim công việc; message vẫn có thể được receiver khác xử lý |
| **Peek-Lock receive** | Nhận message, tạo lock để xử lý trước khi settlement | Có, trong thời gian hữu hạn | Nếu lock mất hoặc settlement thất bại, message có thể được giao lại |
| **Receive-and-Delete** | Broker loại message khỏi queue khi giao theo chế độ này | Không dùng settlement như Peek-Lock | Worker crash sau khi nhận có thể làm mất công việc |

**Peek** thường dùng để kiểm tra hoặc hỗ trợ chẩn đoán, không dùng để xác nhận đã chiếm quyền xử lý. Với **Receive-and-Delete**, tốc độ hoặc độ đơn giản không bù được rủi ro nếu công việc quan trọng.

### Khi nào dùng Receive-and-Delete?

Chỉ cân nhắc với thông tin có thể mất mà không gây vấn đề đáng kể, ví dụ một phần telemetry không thiết yếu đã có cơ chế thu thập khác, và người thiết kế chấp nhận rủi ro mất dữ liệu. Với giao dịch, hóa đơn, công việc batch và cập nhật database, **Peek-Lock thường là lựa chọn phù hợp hơn**.

### Tên gọi dễ gây nhầm

**Peek** không tương đương với **Peek-Lock**. Lệnh peek chỉ nhìn message; việc **lock** phát sinh khi consumer receive trong chế độ **PEEK_LOCK**. Tương tự, **Complete** không phải thao tác xóa tùy ý: nó chỉ hợp lệ cho message mà receiver đang nắm khóa hợp lệ và được thực hiện qua giao thức/SDK phù hợp.

## 3. Vòng đời của một message trong Peek-Lock

~~~text
                  Producer gửi message
                           |
                           v
                         ACTIVE
                           |
                   Receive Peek-Lock
                           |
                           v
                         LOCKED
                     /   /  |  \
                    /   /   |   \
                   v   v    v    v
              COMPLETE ABANDON DEFER DEAD-LETTER
                 |        |     |        |
                 v        v     v        v
             Removed    ACTIVE Deferred  DLQ
                            ^
                            |
                 Lock expired / receive lại
~~~

**Sơ đồ mang tính logic**, không thay thế toàn bộ state machine của broker. Một message còn có thể hết TTL, được tự đưa vào dead-letter queue theo chính sách hoặc bị ảnh hưởng bởi session/transaction.

### Các trạng thái cần hiểu

- **Active:** đủ điều kiện được receiver nhận bình thường.
- **Locked:** đã được receiver nắm giữ trong thời gian nhất định.
- **Completed:** broker chấp nhận settlement thành công và loại message khỏi hàng đợi công việc.
- **Abandoned:** receiver chủ động bỏ khóa; message có thể được giao lại.
- **Deferred:** message được giữ trong queue nhưng **không xuất hiện trong lượt nhận thông thường**, cần lấy lại theo **sequence number**.
- **Dead-lettered:** message chuyển vào **dead-letter subqueue (DLQ)** để xử lý riêng.

**Defer không phải dead-letter và cũng không phải hẹn giờ gửi lại tự động.** Nếu ứng dụng không lưu sequence number và không có quy trình đọc deferred messages, công việc có thể nằm đó mà không được consumer bình thường nhìn thấy.

## 4. LockDuration, LockedUntil và LockToken

Khi Service Bus giao message bằng Peek-Lock, nó tạo một khóa có thời hạn. Những thuộc tính quan trọng:

| Khái niệm | Ý nghĩa | Phạm vi |
|---|---|---|
| **LockDuration** | Thời lượng khóa mặc định khi nhận message ở chế độ Peek-Lock | Cấu hình queue/subscription |
| **LockedUntil** | Thời điểm khóa hiện tại hết hạn theo thông tin SDK/broker | Message đã nhận |
| **LockToken** | Mã nhận diện khóa để xác thực thao tác settlement/renewal | Lần giao message có khóa |
| **DeliveryCount** | Số lần message đã trải qua các lần giao lại theo cơ chế broker | Message |
| **MaxDeliveryCount** | Ngưỡng số lần giao trước khi broker tự dead-letter do vượt giới hạn | Cấu hình queue/subscription |

### LockDuration không phải thời gian xử lý vô hạn

Đối với Azure Service Bus, **LockDuration** thường có thể cấu hình từ vài giây đến **tối đa 5 phút** theo giới hạn của entity/API; giá trị mặc định thường là **1 phút**. Cần xác minh giới hạn hiện hành và cấu hình thực tế của queue/subscription trước khi triển khai.

Một job chạy 20 phút **không** được bảo đảm chỉ vì đã đặt LockDuration = 5 phút. Nếu cần xử lý lâu hơn, consumer phải gia hạn khóa đúng cách hoặc thay đổi kiến trúc để hoàn tất sớm và đưa công việc dài sang hệ thống điều phối khác.

### Khóa thuộc lần nhận hiện tại

Nếu worker A đã nhận một message rồi mất khóa, bản nhận đó không còn hợp lệ cho thao tác Complete. Worker B có thể nhận lại cùng message với một khóa mới. **LockToken không nên được lưu như định danh nghiệp vụ** và không thay thế **messageId/jobId** để chống trùng.

### Không dùng thời gian máy làm nguồn chân lý

Thông tin **LockedUntil** giúp biết thời hạn dự kiến, nhưng network latency, clock skew, service state và lệnh settlement mất thời gian. Không chờ đến sát giây cuối mới gia hạn hoặc Complete.

## 5. Settlement: Complete

**Complete** nghĩa là consumer tuyên bố đã xử lý xong message và broker có thể loại nó khỏi luồng công việc. Đây là lựa chọn phổ biến sau khi:

1. Payload được kiểm tra hợp lệ.
2. Kết quả nghiệp vụ được ghi **bền vững** (database, blob, ledger).
3. Các tác động bên ngoài cần thiết đã được xử lý hoặc có cơ chế hoàn tất theo kiến trúc.
4. Consumer vẫn còn khóa hợp lệ.

~~~text
Receive PAY-001
      |
      v
Check jobId trong ledger
      |
      v
Ghi giao dịch idempotent vào DB
      |
      v
Commit DB transaction thành công
      |
      v
Complete message
      |
      v
Broker loại message khỏi queue
~~~

### Vì sao không Complete trước?

Phản ví dụ:

~~~text
Receive -> Complete -> gọi database -> crash
~~~

Nếu message đã bị loại khỏi queue nhưng database chưa ghi xong thì công việc có thể mất. Thứ tự an toàn hơn là **ghi trạng thái/kết quả trước, rồi Complete**.

### Một cửa sổ lỗi không thể tránh bằng Peek-Lock

~~~text
Receive
  |
  v
Ghi DB thành công
  |
  v
Worker crash trước Complete
  |
  v
Message được giao lại
~~~

Ở lần thứ hai, worker phải nhìn thấy **job đã hoàn thành** và chỉ Complete message, **không tạo giao dịch thứ hai**. Đây là lý do **idempotency** bắt buộc dù bạn đã chọn Peek-Lock đúng.

## 6. Settlement: Abandon

**Abandon** chủ động giải phóng lock của message để nó đủ điều kiện được giao lại. Dùng khi consumer không thể hoàn tất trong lần hiện tại nhưng có cơ sở cho rằng lần sau sẽ thành công.

Ví dụ:

- API OCR trả lỗi tạm thời.
- Database đang chuyển đổi và báo lỗi connection.
- Worker thiếu bộ nhớ trong lần xử lý hiện tại nhưng môi trường đang phục hồi.

~~~text
Worker nhận JOB-042
        |
        v
Gọi dịch vụ OCR
        |
        v
OCR trả lỗi 503 tạm thời
        |
        v
Abandon message
        |
        v
Message trở lại trạng thái đủ điều kiện nhận
        |
        v
Worker khác hoặc cùng worker nhận lại
~~~

### Abandon không tự tạo backoff dài

Abandon thường giúp message có thể nhận lại sớm; nếu toàn bộ worker đang gặp cùng lỗi, chúng có thể nhận/abandon liên tục, gây **retry storm**, tăng DeliveryCount và làm message vào DLQ nhanh chóng.

Nếu cần chờ hàng phút hoặc hàng giờ, cân nhắc:

- Exponential backoff trong luồng điều phối có giới hạn.
- Scheduled message hoặc một retry queue chuyên dụng.
- Định tuyến lỗi theo loại và giới hạn concurrency.
- Circuit breaker cho downstream đang hỏng.

Đừng giữ lock rồi ngủ hàng giờ để “retry”: lock phải được gia hạn, tốn tài nguyên worker và có thể vẫn bị mất.

## 7. Settlement: Dead-letter

**Dead-letter** chủ động chuyển message sang **dead-letter subqueue** khi nó không thể được xử lý bằng luồng bình thường, chẳng hạn:

- Payload không đúng schema.
- Thiếu trường bắt buộc, dữ liệu không thể sửa bằng retry.
- Loại công việc đã bị từ chối theo chính sách nghiệp vụ.
- Phát hiện message không còn tương thích với consumer hiện hành.

~~~text
Receive PAY-002
     |
     v
Validate payload
     |
     v
Thiếu orderId bắt buộc
     |
     v
Dead-letter:
  reason = InvalidPayload
  description = Missing orderId
     |
     v
DLQ để điều tra hoặc replay sau khi sửa
~~~

### DLQ không phải thùng rác được xóa tự động

Message trong DLQ cần quy trình:

1. Theo dõi số lượng và tuổi message lỗi.
2. Phân loại nguyên nhân, nhóm theo schema/version/source.
3. Sửa producer hoặc consumer.
4. Quyết định có **replay** hay không.
5. Khi replay, tạo một lần gửi/đường xử lý được kiểm soát với **jobId/idempotency key** giữ nguyên.
6. Ghi lại ai thực hiện và kết quả.

Không tự phát lại hàng nghìn message lỗi dữ liệu chỉ vì service đã hoạt động trở lại; điều đó có thể lặp lỗi và tạo chi phí không cần thiết.

### Reason và description phải an toàn

Ghi lý do ngắn, ổn định và có thể dùng để thống kê, ví dụ **InvalidSchema** hoặc **UnsupportedVersion**. Không đưa password, token, thông tin thẻ hoặc toàn bộ payload nhạy cảm vào dead-letter description.

## 8. Settlement: Defer

**Defer** phù hợp khi message hợp lệ nhưng consumer muốn xử lý sau theo một trình tự ứng dụng riêng, ví dụ:

- Công việc B phải đợi công việc A hoàn thành.
- Một tài liệu cần được phê duyệt trước khi xử lý.
- Một thành phần đang đợi dữ liệu phụ trợ mà ứng dụng có cơ chế theo dõi.

Khi defer, message không xuất hiện trong các lần receive bình thường. Ứng dụng phải giữ **sequence number** của message để có thể nhận lại bằng API **receive deferred messages**.

~~~text
Receive JOB-B (sequence number 12345)
        |
        v
Dependency JOB-A chưa hoàn tất
        |
        v
Ghi ledger:
  JOB-B -> DEFERRED, sequenceNumber=12345
        |
        v
Defer message
        |
        v
JOB-A hoàn tất
        |
        v
Receive deferred message bằng sequence number
        |
        v
Xử lý JOB-B -> Complete
~~~

### Defer khác Scheduled Message

| Tình huống | Phương án thích hợp |
|---|---|
| Message đã nhận nhưng cần để lại vì phụ thuộc nghiệp vụ | Defer + lưu sequence number + quy trình đánh thức |
| Muốn gửi một message mới có hiệu lực vào thời gian tương lai | Schedule message theo khả năng Service Bus |
| Message lỗi vĩnh viễn | Dead-letter |
| Message lỗi tạm, muốn thử lại sớm | Abandon hoặc chiến lược retry có kiểm soát |

**Không dùng Defer nếu ứng dụng không có nơi lưu sequence number và cơ chế đánh thức.** Lưu số này trong database bền vững hoặc hệ thống điều phối phù hợp, không chỉ trong RAM của worker.

## 9. Bảng chọn settlement theo tình huống

| Trạng thái xử lý | Settlement gợi ý | Lưu ý |
|---|---|---|
| Ghi dữ liệu và trạng thái thành công | **Complete** | Chỉ Complete sau khi side effect bền vững |
| Job đã SUCCEEDED ở lần trước, message bị giao lại | **Complete** | Không chạy tác động nghiệp vụ lần hai |
| SQL/API báo lỗi 503, cần retry | **Abandon** hoặc retry có backoff | Không retry nóng vô hạn |
| JSON hỏng/thiếu trường bắt buộc | **Dead-letter** | Reason rõ, không lộ dữ liệu |
| Đợi bước phụ thuộc, có ledger điều phối | **Defer** | Phải lưu sequence number |
| Khóa đã hết hạn | Không còn settlement hợp lệ cho lần nhận cũ | Chờ/nhận lại đúng cách, kiểm tra idempotency |
| Worker dừng khi đang xử lý | Finish/Complete nếu còn thời gian và lock, hoặc cho retry an toàn | Hỗ trợ graceful shutdown |

Các lựa chọn trong bảng là hướng thiết kế; yêu cầu luật nghiệp vụ, session, TTL và cơ chế transaction có thể làm thay đổi hướng triển khai.

## 10. DeliveryCount và MaxDeliveryCount

Service Bus dùng **DeliveryCount** để hỗ trợ nhận diện message đã được xử lý lại nhiều lần; entity có cấu hình **MaxDeliveryCount**. Giá trị mặc định thường là **10** đối với queue/subscription, cần xem thực tế.

Khi consumer liên tục Abandon hoặc khóa hết hạn và message được giao lại, delivery count có thể tăng. Khi vượt ngưỡng delivery tối đa theo quy tắc broker, Service Bus có thể **tự dead-letter** message với lý do liên quan tới số lần giao.

~~~text
PAY-003:
  lần xử lý thứ 1: worker A crash
  lần xử lý thứ 2: worker B Abandon
  lần xử lý thứ 3: worker C lỗi
  ...
  vượt MaxDeliveryCount
       |
       v
  Broker chuyển vào DLQ
~~~

### Vì sao không tăng MaxDeliveryCount lên thật lớn?

Nếu payload có lỗi vĩnh viễn, thêm 1.000 lần thử chỉ:

- Tạo thêm lượt xử lý và chi phí.
- Làm nhiễu log/cảnh báo.
- Gây mất thời gian trên message không thể thành công.
- Tăng áp lực lên downstream.

Chọn MaxDeliveryCount theo loại công việc, khả năng phục hồi và SLA. Phân loại **transient** với **permanent** trước khi quyết định retry.

### Đừng coi DeliveryCount là ID của một lần nghiệp vụ

DeliveryCount giúp vận hành, nhưng không thay cho **messageId** hay **jobId**. Một producer có thể gửi message mới mang cùng lệnh nghiệp vụ; một message cũng có thể được redeliver. Thiết kế chống trùng dựa trên định danh nghiệp vụ có quy tắc rõ ràng.

## 11. Khi nào phải gia hạn khóa?

Giả sử queue cấu hình LockDuration = 60 giây, trong khi công việc OCR có thể kéo dài 3 phút. Nếu consumer không gia hạn:

~~~text
00:00  Worker A nhận JOB-100, lock đến 01:00
00:10  A bắt đầu OCR
01:00  Lock hết hạn
01:05  Worker B có thể nhận lại JOB-100
02:50  A hoàn tất OCR và thử Complete
02:50  Complete có thể lỗi MessageLockLost
~~~

Trong lúc ấy, B có thể đang xử lý cùng công việc. Bài toán cần giải quyết ở **hai tầng**:

1. **Giữ khóa đủ lâu khi công việc đang chạy hợp lệ**, qua renewal.
2. **Chống tác động trùng khi khóa vẫn mất**, qua idempotency/lease nghiệp vụ.

Renewal giảm nguy cơ duplicate do hết hạn trong điều kiện bình thường, nhưng **không biến Peek-Lock thành transaction bao trùm tất cả hệ thống**.

### Hai cách renew

- **Manual renewal:** consumer gọi SDK để xin thời hạn khóa mới cho message.
- **Automatic renewal:** SDK tạo cơ chế gia hạn định kỳ trong khoảng thời gian tối đa do ứng dụng cấu hình.

Thời hạn renewal có giới hạn; ứng dụng cần lựa chọn mức hợp lý theo thời gian xử lý, thời gian xử lý tối đa cho phép và ngân sách.

## 12. Manual lock renewal

Trong Azure Service Bus Python SDK, receiver có thao tác tương ứng **renew_message_lock(message)** dành cho message đang có khóa hợp lệ.

Pseudocode:

~~~text
message = receive_peek_lock()
deadline = now + processing_timeout

while not job_finished and now < deadline:
    process_small_step()

    if nearing_message_lock_expiration:
        receiver.renew_message_lock(message)

if job_finished_and_result_durable:
    receiver.complete_message(message)
else:
    handle_retry_or_failure()
~~~

Các lưu ý:

- Renew phải xảy ra **trước** khi lock hết hạn.
- Nếu lock đã mất, không có thao tác renew nào “cứu” lại bản nhận cũ.
- Network lỗi, service maintenance hoặc consumer process bị dừng có thể khiến renewal thất bại.
- Lock renewal không gia hạn TTL dữ liệu hay đảm bảo xử lý thành công.
- Không dùng vòng lặp renew vô hạn nếu nghiệp vụ cần timeout.

### Tách thời gian xử lý khỏi thời gian giữ khóa

Một công việc có thể cần 20 phút do chờ OCR. Nếu worker phải giữ message lock và giữ một replica chạy suốt thời gian đó, ứng dụng tăng chi phí và tạo rủi ro renewal bị gián đoạn.

Với workflow rất dài, cân nhắc **Durable Functions, Container Apps Jobs, Saga, scheduler hoặc state machine**: consumer nhận message, tạo một job bền vững, Complete thông điệp **chỉ sau khi job được ghi chắc chắn**, rồi hệ thống khác theo dõi và thực hiện công việc dài. Thiết kế này phải có cơ chế điều phối kết quả riêng; không đơn giản Complete trước khi ghi bất cứ trạng thái nào.

## 13. AutoLockRenewer trong Python SDK

Python SDK của Azure Service Bus cung cấp **AutoLockRenewer** để tự gia hạn message lock trong một khoảng tối đa. Đây là công cụ hữu ích khi thời gian xử lý thay đổi nhưng thường không quá dài.

Ví dụ ý tưởng:

~~~python
from azure.servicebus import AutoLockRenewer

renewer = AutoLockRenewer(max_lock_renewal_duration=300)

try:
    # receiver đã nhận message trong chế độ PEEK_LOCK.
    renewer.register(
        receiver,
        message,
        max_lock_renewal_duration=300
    )

    process_message(message)
    # Complete sau khi mọi side effect cần thiết đã bền vững.
    receiver.complete_message(message)
finally:
    renewer.close()
~~~

**Đoạn trên minh họa logic, không chạy riêng lẻ** vì receiver/message/process_message cần được khởi tạo. Các giá trị **300 giây** là thời gian gia hạn tối đa ứng dụng yêu cầu, không phải LockDuration của queue và không bảo đảm lock sẽ giữ suốt 300 giây trong mọi điều kiện.

### Những giới hạn của tự gia hạn

1. Renewal chỉ hoạt động khi tiến trình và cơ chế SDK còn hoạt động, có mạng và còn quyền.
2. SDK có thể gặp lỗi gia hạn dù công việc vẫn đang chạy.
3. Đến giới hạn max lock renewal duration, khóa có thể hết hạn nếu công việc chưa xong.
4. Một message đã mất khóa không thể được Complete bằng lock cũ.
5. Trong workload CPU-bound, cần kiểm tra việc xử lý có làm nghẽn thread/event loop thực hiện renewal không.
6. Không nên đăng ký hàng nghìn message khóa cùng lúc nếu tài nguyên SDK/worker không đáp ứng.

Theo dõi **thời gian xử lý p95/p99** để lựa chọn giới hạn renewal, không chỉ dựa vào trung bình.

## 14. Ví dụ Python: nhận và settlement bằng Peek-Lock

Đây là ví dụ thực hành với **azure-servicebus** và **azure-identity**. Worker kết nối tới queue đã tồn tại, nhận message theo Peek-Lock, kiểm tra payload JSON, mô phỏng tác vụ ngắn và Complete. Message sai schema được Dead-letter; lỗi xử lý tạm thời được Abandon nếu còn khóa.

### Điều kiện trước khi chạy

- Một Azure Service Bus namespace và queue được tạo trong môi trường lab.
- Người chạy có quyền **Azure Service Bus Data Receiver** tại phạm vi phù hợp.
- Dùng Microsoft Entra ID/managed identity hoặc thông tin developer được cấp quyền, không nhúng connection string vào code.
- Kết nối TLS và DNS/network tới namespace phải hoạt động.
- Queue không chứa giao dịch production: chương trình **thực sự nhận và settlement** message.
- Python runtime cùng packages:

~~~bash
python -m pip install azure-servicebus azure-identity
~~~

Khai báo biến môi trường ví dụ:

~~~bash
export SERVICEBUS_FQDN="sb-demo.servicebus.windows.net"
export SERVICEBUS_QUEUE="invoice-jobs"
~~~

Trên Azure, **DefaultAzureCredential** có thể sử dụng managed identity; local có thể sử dụng danh tính developer nếu được cấu hình. Cần xác minh tenant, subscription, quyền và môi trường thực tế trước khi chạy.

### Worker mẫu

~~~python
import json
import logging
import os
import time

from azure.identity import DefaultAzureCredential
from azure.servicebus import (
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusReceiveMode,
)
from azure.servicebus.exceptions import MessageLockLostError


FQDN = os.environ["SERVICEBUS_FQDN"]
QUEUE = os.environ["SERVICEBUS_QUEUE"]


def parse_job(message):
    # Mẫu này yêu cầu sender dùng message body kiểu JSON bytes (DATA).
    raw = b"".join(message.body)
    data = json.loads(raw.decode("utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Message body must be a JSON object")
    if not isinstance(data.get("jobId"), str) or not data["jobId"]:
        raise ValueError("Missing jobId")
    return data


def do_short_demo_work(job):
    # Chỉ mô phỏng tính toán; không tạo side effect thật.
    # Production phải ghi output và idempotent job ledger bền vững.
    logging.info("Processing jobId=%s", job["jobId"])
    time.sleep(2)


def main():
    credential = DefaultAzureCredential()
    renewer = AutoLockRenewer(max_lock_renewal_duration=300)

    try:
        with ServiceBusClient(
            fully_qualified_namespace=FQDN,
            credential=credential,
        ) as client:
            with client.get_queue_receiver(
                queue_name=QUEUE,
                receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                prefetch_count=0,
                max_wait_time=5,
            ) as receiver:
                # Lab: lấy tối đa một message trong một lần chạy.
                messages = receiver.receive_messages(
                    max_message_count=1,
                    max_wait_time=5,
                )

                for message in messages:
                    try:
                        renewer.register(
                            receiver,
                            message,
                            max_lock_renewal_duration=300,
                        )

                        try:
                            job = parse_job(message)
                        except (ValueError, UnicodeDecodeError,
                                json.JSONDecodeError) as invalid:
                            receiver.dead_letter_message(
                                message,
                                reason="InvalidPayload",
                                error_description="Missing or invalid JSON job",
                            )
                            logging.warning(
                                "Dead-lettered invalid message: %s",
                                type(invalid).__name__,
                            )
                            continue

                        do_short_demo_work(job)
                        receiver.complete_message(message)
                        logging.info("Completed jobId=%s", job["jobId"])

                    except MessageLockLostError:
                        # Lock cũ không còn hợp lệ: không cố Complete lần nữa.
                        logging.exception("Message lock was lost")

                    except Exception:
                        logging.exception("Unexpected worker error")
                        try:
                            receiver.abandon_message(message)
                        except Exception:
                            # Có thể lock đã mất; broker sẽ xử lý redelivery.
                            logging.exception(
                                "Unable to abandon the received message"
                            )
    finally:
        renewer.close()
        credential.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
~~~

**Giới hạn của ví dụ:**

- Đây là **consumer lab**, không phải giải pháp production; nó nhận nhiều nhất một message và cố tình xử lý ngắn.
- Không có database/ledger idempotency thật, retry scheduler, circuit breaker hay structured telemetry đầy đủ.
- Payload giả định **DATA message body** chứa JSON UTF-8; một số message body type khác cần decoder khác.
- Không gửi message mẫu hoặc tự tạo queue; người học phải dùng queue thử nghiệm đã được cấp quyền.
- Nhánh lỗi chung chỉ cố Abandon khi còn lock; nếu quyền/connection đã hỏng, thao tác đó cũng có thể thất bại.
- Cấu hình AutoLockRenewer để minh họa dù tác vụ chỉ mất khoảng 2 giây. Với tác vụ ngắn hơn LockDuration ổn định, tự gia hạn có thể không cần thiết.
- Khi gặp MessageLockLost sau khi nghiệp vụ thực sự đã thành công, lần nhận sau vẫn phải dùng ledger để tránh tác động trùng.

## 15. Mẫu production: ledger idempotent và Complete an toàn

Một consumer nghiêm túc cần **idempotency key** gắn với nghiệp vụ, không chỉ lock token. Ví dụ:

~~~text
MessageId = producer-assigned identifier
JobId = ORD-00421
Ledger key = namespace + business operation + JobId
~~~

Ledger có thể được lưu trong Azure SQL, Cosmos DB, PostgreSQL hoặc một storage hỗ trợ **unique key/conditional write**. Pseudocode:

~~~text
receive message Peek-Lock
validate and normalize JobId

atomically insert JobId as PROCESSING with lease/owner
    if already SUCCEEDED:
        Complete current delivery
        stop
    if another worker owns active processing lease:
        defer or retry safely based on policy
        stop

try:
    perform business operation with idempotent side effects
    durably record SUCCEEDED + result reference
    Complete current message while lock remains valid
except permanent invalid input:
    record rejected status
    Dead-letter message if lock valid
except transient error:
    record failed attempt
    Abandon or schedule controlled retry if lock valid
except lock lost:
    do not settle stale delivery
    preserve ledger for safe redelivery/reconciliation
~~~

### Vì sao “check rồi insert” chưa đủ?

Hai worker có thể cùng đọc ledger và đều thấy JobId chưa tồn tại. Nếu sau đó cả hai tạo side effect, hệ thống vẫn trùng. Phải dùng **unique constraint, transaction, compare-and-swap hoặc atomic claim**.

### Lease nghiệp vụ khác Message Lock

Message lock bảo vệ quyền settlement ở Service Bus. **Business lease/ledger** bảo vệ tính đúng đắn khi thao tác trải dài sang database, Blob Storage hoặc API khác. Hai cơ chế có thể hết hạn ở thời điểm khác nhau; hãy thiết kế job claim timeout và recovery riêng.

### Khi có side effect ngoài hệ thống

Nếu worker gửi email hoặc yêu cầu thanh toán tới đối tác, Complete/DB transaction không thể tự rollback email đã gửi. Cần dùng **idempotency key với API đối tác**, outbox pattern, trạng thái gửi bền vững và reconciliation.

## 16. MessageLockLost và các lỗi thường gặp

**MessageLockLost** (hoặc một lỗi Service Bus tương ứng) cho biết thao tác đang yêu cầu sử dụng khóa không còn hợp lệ. Nguyên nhân có thể là:

- Worker xử lý quá lâu so với LockDuration.
- Gia hạn khóa không xảy ra kịp thời hoặc bị lỗi.
- Network/interruption khiến phiên nhận không tiếp tục hoạt động như kỳ vọng.
- Hạ tầng/dịch vụ làm mất khóa trong một số trường hợp, kể cả khi thời hạn dự kiến chưa kết thúc.
- Tác vụ settlement được gửi từ một đối tượng receiver/lock đã lỗi hoặc cũ.

### Không bao giờ coi việc gọi Complete thất bại là nghiệp vụ chưa chạy

Ví dụ:

~~~text
10:00:00 Receive PAY-120
10:00:15 Ghi giao dịch DB thành công
10:01:05 Attempt Complete -> MessageLockLost

Kết luận đúng:
  - Giao dịch DB có thể đã tồn tại.
  - Message có thể được giao lại.
  - Consumer mới phải kiểm tra JobId và Complete an toàn.

Kết luận SAI:
  - Complete thất bại nên chắc chắn DB chưa ghi.
~~~

### Nên làm gì khi mất khóa?

1. Không cố Complete/Abandon bằng lock token đã hết hiệu lực.
2. Ghi log an toàn: messageId, jobId, deliveryCount, thời gian xử lý, loại lỗi.
3. Để broker điều phối lại message, không tự tạo một bản sao vô điều kiện.
4. Khi nhận lại, thực hiện quy trình idempotency.
5. Điều chỉnh LockDuration, renewal, concurrency và thiết kế tác vụ nếu lỗi lặp lại.

## 17. Prefetch có thể làm lock hết hạn trước khi xử lý

**Prefetch** cho phép client tải trước nhiều message để giảm lượt network. Nó có thể tăng throughput khi xử lý nhanh, nhưng có rủi ro với Peek-Lock: **message đã được prefetched có thể bắt đầu chịu thời hạn khóa trong khi vẫn đang nằm trong bộ nhớ client**, trước khi ứng dụng thực sự bắt đầu xử lý.

Ví dụ:

~~~text
LockDuration = 60 giây
Prefetch = 100 messages
Một worker xử lý tuần tự: 5 giây/message

Message thứ 20 chờ trong buffer khoảng 95 giây.
Đến lúc xử lý, lock của nó có thể đã hết hạn.
~~~

### Hướng điều chỉnh

- Với tác vụ lâu: **prefetch_count=0** hoặc giá trị rất nhỏ.
- Với tác vụ nhanh: tăng prefetch sau khi đo throughput và lock-loss rate.
- Không nhận nhiều message hơn số có thể xử lý trong giới hạn lock/renewal.
- Đo **thời gian chờ trong buffer**, không chỉ thời gian xử lý khi đã bắt đầu.
- Dùng concurrent consumers nếu workload thích hợp, nhưng tránh vượt khả năng database/API.

**Gia hạn tự động không biến prefetch vô hạn thành an toàn.** Đăng ký renew cho tất cả message đang buffered có thể làm tăng tải và không giải quyết nút thắt xử lý tuần tự.

## 18. Concurrency và lock ownership

Nếu queue có 500 message và 20 workers, Service Bus phân phối các message đủ điều kiện đến các receiver theo cơ chế của broker. Mỗi worker có thể có nhiều message đang nhận tùy SDK/config.

~~~text
Queue: 500 active messages
        |
        +--> Worker A: message 1, 2, 3 ...
        +--> Worker B: message 4, 5, 6 ...
        +--> Worker C: message 7, 8, 9 ...
        ...
~~~

Khi concurrency tăng:

- Throughput có thể cải thiện.
- Khả năng lock timeout tăng nếu xử lý nhiều hơn năng lực thực.
- Database connection pool hoặc API rate limit dễ bị quá tải.
- Việc retry một message có thể trùng với tác động của delivery trước.

Một rule tốt là **concurrency ≤ năng lực xử lý bền vững**, và tổng thời gian từ nhận đến settlement phải phù hợp với LockDuration/renewal budget.

### Session-enabled queue: trường hợp đặc biệt

Nếu queue/subscription có **sessions**, consumer có thể nhận theo **SessionId**. Cơ chế **session lock** khác message lock thông thường:

- Receiver chiếm một session để xử lý nhóm message theo phiên.
- Thứ tự trong cùng session có thể được ứng dụng điều phối theo khả năng Service Bus.
- Có API **renew session lock** và cơ chế tự gia hạn session theo SDK.
- Session lock hết hạn có thể làm receiver mất quyền xử lý session đó.

Không dùng **renew_message_lock** như lựa chọn mặc định cho mọi message trong session receiver; hãy xem đúng SDK/session API. Session hữu ích khi cần nhóm công việc theo customer/order, nhưng vẫn phải xử lý idempotency, lock loss và workflow side effects.

## 19. Bài toán giao dịch và tính đúng đắn giữa hệ thống

Service Bus có khả năng transaction cho **một số thao tác messaging được hỗ trợ**, nhưng một giao dịch Azure SQL hoặc PostgreSQL không mặc định nằm chung một atomic transaction với Complete của Service Bus.

Tình huống:

~~~text
Receive message
  |
  v
Commit DB transaction
  |
  v
Complete Service Bus message
~~~

Nếu tiến trình crash giữa hai bước, broker vẫn có thể giao lại dù DB đã commit. Thiết kế theo **at-least-once delivery + idempotent processing** thường thực tế hơn là giả định “một message bằng một giao dịch” trên mọi hệ thống.

### Transactional Outbox

Với ứng dụng vừa cập nhật DB vừa cần phát message mới, **outbox pattern** có thể:

1. Ghi dữ liệu nghiệp vụ và bản ghi outbox trong **cùng transaction DB**.
2. Một publisher độc lập đọc outbox để gửi Service Bus.
3. Đánh dấu outbox đã gửi theo cơ chế idempotent.
4. Receiver phía sau chống duplicate dựa trên định danh nghiệp vụ.

Outbox không làm network và broker không bao giờ lỗi; nó tạo đường phục hồi khi DB commit nhưng gửi message chưa thành công.

## 20. Gia hạn khóa và thiết kế tác vụ dài

So sánh ba phương án:

| Phương án | Khi phù hợp | Rủi ro/giới hạn |
|---|---|---|
| Xử lý trong một lần lock | Công việc ngắn, thời gian ổn định | Lỗi nếu vượt LockDuration |
| Auto-renew trong giới hạn | Công việc dài vừa phải, worker còn hoạt động | Có thể mất lock; CPU/thread/network và giới hạn renewal |
| Tách sang durable job | Tác vụ hàng chục phút/giờ hoặc chờ người dùng | Cần ledger, workflow, timeout và cơ chế hoàn tất riêng |

Một ví dụ thiết kế công việc xuất báo cáo:

~~~text
Service Bus message: GenerateMonthlyReport
        |
        v
Consumer tạo job record (idempotent)
        |
        v
Complete message sau khi job đã được tạo bền vững
        |
        v
Job runner xử lý báo cáo nhiều phút
        |
        +-- Status = RUNNING
        +-- Status = SUCCEEDED / FAILED
        |
        v
Gửi thông báo kết quả theo workflow riêng
~~~

Ở mô hình này, thông điệp đầu vào có nghĩa là **“đã tiếp nhận yêu cầu xử lý”** chứ không phải “đã tạo báo cáo xong”. Phải làm rõ hợp đồng nghiệp vụ và API trạng thái job để không tạo hiểu lầm khi Complete sớm.

## 21. Cấu hình Queue và các ngưỡng vận hành

Các thuộc tính liên quan có thể được quản lý tại **queue/subscription**:

| Cấu hình | Tác động |
|---|---|
| **LockDuration** | Thời hạn khóa cho lượt receive Peek-Lock |
| **MaxDeliveryCount** | Khi vượt ngưỡng, broker có thể tự dead-letter |
| **DefaultMessageTimeToLive** | TTL mặc định của message nếu không đặt riêng |
| **DeadLetteringOnMessageExpiration** | Hành vi chuyển message hết TTL vào DLQ nếu cấu hình |
| **RequiresSession** | Entity bắt buộc message/receiver dùng session phù hợp |
| **DuplicateDetection** | Có thể hạn chế nhận lại message gửi có cùng MessageId trong cửa sổ hỗ trợ |

### Duplicate detection không thay thế idempotency

**Duplicate detection** ở broker có thể giúp lọc một số lần gửi trùng theo **MessageId** trong khoảng thời gian được cấu hình. Nhưng nó không đảm bảo handler không chạy hai lần khi **cùng một message được redeliver sau lock loss**. Nó cũng không bảo vệ mọi tác động ngoài broker.

### TTL không bằng LockDuration

- **LockDuration:** quyền tạm thời của consumer đối với message đã nhận.
- **TTL:** thời gian tồn tại hợp lệ của message theo cấu hình.
- **MaxDeliveryCount:** giới hạn số lần giao lại thất bại.

Chúng là các trục riêng, không được cộng hoặc dùng thay nhau.

## 22. Kiểm tra read-only bằng Azure CLI

Các lệnh sau **chỉ đọc cấu hình**; tên tài nguyên giả định:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az servicebus namespace show \
  --resource-group "rg-messaging-lab" \
  --name "sb-orders-lab" \
  --query "{name:name,location:location,sku:sku.name}" \
  --output json
~~~

Xem queue và thông số khóa:

~~~bash
az servicebus queue show \
  --resource-group "rg-messaging-lab" \
  --namespace-name "sb-orders-lab" \
  --name "payment-jobs" \
  --query "{name:name,lockDuration:lockDuration,maxDeliveryCount:maxDeliveryCount,requiresSession:requiresSession,deadLetterOnExpiry:deadLetteringOnMessageExpiration}" \
  --output json
~~~

Đọc toàn bộ cấu hình nếu cần so sánh:

~~~bash
az servicebus queue show \
  --resource-group "rg-messaging-lab" \
  --namespace-name "sb-orders-lab" \
  --name "payment-jobs" \
  --output json
~~~

Một số trường về runtime count có thể xuất hiện tùy phiên bản API/CLI. Đối chiếu với Azure portal/metrics để xem **Active**, **Dead-lettered**, **Scheduled**, **Transfer** hoặc những nhóm count liên quan nếu được hỗ trợ. Đừng suy luận chính xác tình trạng worker từ một snapshot số lượng message.

### Không dùng CLI thay đổi queue để “test lock”

Việc thay **LockDuration**, **MaxDeliveryCount**, xóa queue hoặc drain DLQ có thể tác động ngay tới consumer production. Phần thực hành nên dùng **queue lab** riêng. Nếu sửa cấu hình trên sản xuất, phải có phê duyệt, change window, điều kiện rollback và đo tác động.

## 23. Microsoft Entra ID, RBAC và private networking

### Danh tính worker

Ưu tiên **managed identity** của Azure Functions, Container Apps, VM hoặc AKS Workload Identity để dùng SDK Service Bus khi môi trường hỗ trợ.

| Thành phần | Quyền nên đánh giá |
|---|---|
| Producer | **Azure Service Bus Data Sender** ở phạm vi thích hợp |
| Consumer | **Azure Service Bus Data Receiver** ở queue/subscription cần xử lý |
| Operator | Quyền xem cấu hình/metrics/log và quyền replay được phân tách |
| Admin queue | Quyền quản lý entity theo RBAC hẹp, không cấp cho mọi worker |

Không dùng **Owner toàn subscription** chỉ để đọc message. Shared Access Signature/connection string có thể được dùng ở môi trường tương thích, nhưng phải hạn chế quyền, lưu trong Key Vault/secret store, rotate định kỳ và không nhúng vào image/repository.

### Phân biệt quyền và đường mạng

Worker có Azure RBAC đúng vẫn có thể không kết nối được Service Bus nếu:

- Namespace đã giới hạn public network access.
- Private Endpoint/DNS/route không phù hợp.
- Firewall/NSG/UDR chặn đường egress.
- Proxy/TLS hoặc cấu hình AMQP/WebSocket không phù hợp.

Ngược lại, network thông suốt vẫn có thể trả lỗi xác thực hoặc 403 vì identity không đủ quyền.

**Peek-Lock không thay thế xác thực.** Lock giới hạn việc nhiều consumer nắm một message ở broker, không ngăn người quản trị có quyền cao xem dữ liệu nhạy cảm hoặc thay đổi cấu hình.

## 24. Giám sát lock, settlement và backlog

Một hệ thống đáng tin cậy phải quan sát được từ lúc message được gửi tới khi hoàn tất:

| Chỉ số/telemetry | Ý nghĩa |
|---|---|
| **Active messages** | Backlog đủ điều kiện nhận |
| **Dead-letter message count** | Message lỗi cần điều tra |
| **Scheduled/deferred counts hoặc inventory** | Công việc đang chờ xử lý theo cơ chế riêng |
| **DeliveryCount** | Dấu hiệu retry/giao lại |
| **MessageLockLost count** | Khóa bị mất khi xử lý hoặc settlement |
| **Complete/Abandon/Dead-letter outcomes** | Phân loại kết quả consumer |
| **Processing time p50/p95/p99** | Chọn LockDuration/renewal budget và concurrency |
| **Lock renewal errors** | Phát hiện network/SDK/tác vụ xử lý vượt thời hạn |
| **Oldest message age** | Công việc chờ lâu nhất so với SLA |
| **DLQ reason distribution** | Phân biệt lỗi producer, schema và downstream |
| **Worker CPU/RAM/concurrency** | Phát hiện nghẽn tài nguyên |
| **Cost per successful job** | Đánh giá hiệu quả toàn pipeline |

Không phải tất cả trường ở bảng là **Azure Monitor metric tích hợp**. MessageLockLost, settlement outcomes, p95, jobId và DLQ reason thường cần **telemetry ứng dụng** hoặc truy vấn bổ sung. Azure Monitor và metrics của Service Bus cung cấp một phần thông tin broker.

### Mẫu log không lộ dữ liệu

~~~json
{
  "jobId": "PAY-001",
  "messageId": "msg-001",
  "deliveryCount": 3,
  "settlement": "COMPLETE",
  "processingDurationMs": 1820,
  "lockRenewalCount": 0,
  "result": "SUCCEEDED"
}
~~~

Không log connection string, token, toàn bộ payload cá nhân, số thẻ, khóa mã hóa hay dữ liệu thanh toán nhạy cảm.

### Những cảnh báo hữu ích

- Số message **dead-lettered** tăng trong thời gian ngắn.
- **MessageLockLost** tăng sau khi thay đổi prefetch/concurrency.
- Queue backlog hoặc tuổi message vượt SLA.
- Nhiều Abandon liên tiếp với cùng một loại lỗi.
- Worker sống nhưng không Complete message nào.
- Renewal thất bại hoặc processing p99 vượt giới hạn thời gian giữ khóa.
- Chi phí broker/compute tăng vì retry storm.

## 25. Xử lý lỗi theo nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Complete báo MessageLockLost | Lock hết hạn, renew lỗi hoặc kết nối/receiver bị gián đoạn | So sánh processing time, LockedUntil, network và renewal logs |
| Message giao lại dù DB đã ghi | Worker crash hoặc settlement không thành công | Kiểm tra ledger và xử lý idempotent |
| Nhiều message vào DLQ vì MaxDeliveryCount | Retry nóng, lỗi backend kéo dài hoặc payload không hợp lệ | Phân loại lỗi, backoff, MaxDeliveryCount và DLQ reason |
| Message không còn xuất hiện khi receive bình thường | Có thể đã Defer, DLQ, Complete hoặc hết điều kiện nhận | Kiểm tra trạng thái queue và sequence number/inventory |
| Consumer ReceiveAndDelete làm mất công việc | Message bị loại khi giao trước khi worker commit | Chuyển sang Peek-Lock và thêm durable processing |
| Tăng prefetch rồi nhiều lock lost | Message chờ lâu trong client buffer | Giảm prefetch, đo thời gian đợi và concurrency |
| Auto-renew vẫn để mất lock | Vượt renewal budget, network/CPU/SDK lỗi | Theo dõi renewal failures, giới hạn thời gian, tái cấu trúc job |
| Hệ thống xử lý trùng thanh toán | Thiếu idempotency hoặc API bên ngoài không hỗ trợ idempotency key | Dùng ledger unique key và đối chiếu side effect |
| Worker không nhận được message | RBAC, queue/session mode, DNS hoặc Private Endpoint sai | Kiểm tra identity, session requirement và broker metrics |
| Settlement lỗi sau khi VM/Container restart | Receiver cũ bị đóng, khóa không còn hợp lệ | Đảm bảo graceful shutdown và an toàn khi redelivery |
| Queue active bằng 0 nhưng còn việc | Deferred, locked/in-flight, scheduled hoặc DLQ | Kiểm tra các loại trạng thái và job ledger |
| API chậm làm queue tăng | Không đủ concurrency hoặc downstream throttling | Đo throughput, p95, 429/503, giới hạn retry và scale |

### Quy trình chẩn đoán sáu bước

1. **Broker:** xác nhận queue/subscription, LockDuration, MaxDeliveryCount, active/DLQ counts.
2. **Consumer mode:** Peek-Lock hay ReceiveAndDelete? Có sessions và prefetch không?
3. **Timing:** thời gian xử lý, LockedUntil và renewal budget có đủ không?
4. **Settlement:** worker đã gọi Complete/Abandon/Defer/Dead-letter chưa, có lỗi SDK không?
5. **Side effect:** database/API bên ngoài đã ghi chưa, ledger cho biết gì?
6. **Hạ tầng:** identity, network, DNS, worker restart, quota và downstream throttling?

Không chỉnh tăng LockDuration ngay khi thấy MessageLockLost mà chưa đo processing time; một lỗi worker crash hoặc mạng vẫn có thể xảy ra dù lock dài hơn.

## 26. Tối ưu hiệu năng và chi phí

Peek-Lock có chi phí thao tác messaging và chi phí worker liên quan. Một hệ thống retry quá nhiều hoặc auto-renew khóa vô hạn có thể làm tăng chi phí mà không cải thiện SLA.

### Những biến cần cân đối

- **LockDuration:** đủ cho tác vụ ngắn phổ biến, không thay cơ chế workflow dài.
- **Prefetch:** tăng throughput nhưng dễ hết hạn trước khi xử lý nếu quá lớn.
- **Concurrency:** tăng số tác vụ song song nhưng có thể làm downstream quá tải.
- **MaxDeliveryCount:** đủ retry lỗi tạm thời, tránh vòng lặp cho dữ liệu lỗi.
- **Retry backoff:** hạn chế retry storm và các lần gọi API vô ích.
- **TTL:** phù hợp giá trị nghiệp vụ của công việc.
- **Auto-renew budget:** phù hợp p99 và timeout ứng dụng.
- **DLQ monitoring:** tránh tồn đọng dữ liệu lỗi không được xử lý.

### Ví dụ sizing đơn giản

Giả sử:

~~~text
Backlog = 600 messages
Một worker xử lý = 5 messages/phút
SLA cần hoàn tất trong = 30 phút

Năng lực cần = 600 / 30 = 20 messages/phút
Worker tối thiểu lý thuyết = ceil(20 / 5) = 4
~~~

Đây chưa tính cold start, retry, message phức tạp, lock renewal và rate limit database. Nếu mỗi worker có thể xử lý một message trong 12 giây nhưng nguồn dữ liệu chỉ cho 10 giao dịch/phút, tăng worker từ 4 lên 20 có thể gây thêm lỗi 429/503.

Service Bus có giá theo tier, operations và các điều kiện dịch vụ hiện hành; Azure Functions/Container Apps/VM cũng có phí compute. Ngoài ra còn log, networking/Private Endpoint và các dịch vụ dữ liệu phụ thuộc. Dùng Azure Cost Management và giá theo region/tier thay vì chèn một mức phí cố định.

## 27. Bài tập tình huống: xử lý thanh toán chống trùng

Một công ty thương mại điện tử gửi message vào Service Bus Queue **payment-jobs**. Mỗi message chứa:

~~~json
{
  "jobId": "PAY-2026-00042",
  "orderId": "ORD-2026-00123",
  "amount": 250000,
  "currency": "VND"
}
~~~

Yêu cầu:

- Hệ thống có 5 worker chạy trên Azure Container Apps.
- LockDuration = 60 giây.
- Thời gian xử lý thông thường 10 giây nhưng API thanh toán đôi lúc kéo dài 2 phút.
- Một số message thiếu **orderId**.
- API đối tác có thể nhận yêu cầu thành công nhưng trả response timeout.
- Không được tạo giao dịch thanh toán hai lần.
- Queue cần giám sát SLA 5 phút từ lúc enqueue đến khi xử lý.

### Nhiệm vụ

1. Giải thích vì sao chọn Peek-Lock thay vì ReceiveAndDelete.
2. Thiết kế bước validate payload trước khi gọi API.
3. Chọn Complete/Abandon/Defer/Dead-letter cho bốn trạng thái nghiệp vụ.
4. Xác định cách gia hạn khóa khi API mất khoảng 2 phút.
5. Giải thích vì sao AutoLockRenewer không thay thế idempotency key.
6. Thiết kế ledger theo jobId và unique constraint.
7. Xử lý tình huống API đã thanh toán nhưng response timeout.
8. Nêu vì sao prefetch=100 ở mỗi worker có thể nguy hiểm.
9. Thiết kế MaxDeliveryCount, retry backoff và cách xử lý DLQ.
10. Mô tả log và cảnh báo khi MessageLockLost tăng.
11. Nêu cách dùng managed identity/RBAC và Private Endpoint.
12. Đề xuất bài kiểm thử cố ý cho worker crash trước Complete.

### Gợi ý lời giải

Chọn Peek-Lock và dùng **jobId** làm idempotency key. Trước khi gọi API thanh toán, kiểm tra database xem job đã thành công chưa; thực hiện claim bằng thao tác atomic. Nếu API hỗ trợ idempotency key, gửi cùng jobId cho mọi lần retry. Sau khi có xác nhận bền vững hoặc đối chiếu trạng thái đối tác, ghi SUCCEEDED và Complete message.

Khi API timeout nhưng không biết giao dịch đã thành công, **không lập tức gửi một yêu cầu thanh toán mới với định danh khác**. Cần truy vấn/đối chiếu trạng thái phía đối tác bằng idempotency key hoặc quy trình reconciliation.

Nếu payload thiếu orderId, Dead-letter với reason rõ. Nếu lỗi 503 tạm thời, Abandon hoặc retry có backoff; nếu tác vụ dài hơn lock, dùng auto/manual renewal trong giới hạn và vẫn xử lý được lock loss. Prefetch phải phù hợp thời gian xử lý thực và concurrency.

## 28. Checklist production

| Nhóm | Bằng chứng cần xác minh |
|---|---|
| Receive mode | Đang dùng PEEK_LOCK cho nghiệp vụ quan trọng |
| Entity config | LockDuration, MaxDeliveryCount, TTL và sessions phù hợp |
| Settlement | Complete sau durable commit, lỗi được phân loại đúng |
| Defer | Có lưu sequence number và cách lấy lại |
| Dead-letter | Có DLQ alert, reason an toàn và runbook replay |
| Renewal | Thời lượng/giới hạn phù hợp p99, có theo dõi failure |
| Idempotency | JobId, unique key/atomic claim và side effects an toàn |
| Prefetch | Không quá số message có thể xử lý trước lock timeout |
| Concurrency | Không vượt năng lực DB/API phụ thuộc |
| Shutdown | Worker xử lý SIGTERM/restart và redelivery đúng |
| Identity | Managed identity và Azure Service Bus Data Receiver đúng scope |
| Network | DNS, firewall/private endpoint và đường AMQP/TLS đúng |
| Observability | MessageLockLost, DeliveryCount, settlements, DLQ và SLA |
| Cost | Có budget broker, compute, log, retries và DLQ |
| Resilience | Đã thử crash, timeout, duplicate, lock expiry và replay |

## 29. Câu hỏi tự kiểm tra

1. Điểm khác biệt giữa Peek và Peek-Lock receive là gì?
2. Vì sao ReceiveAndDelete có thể làm mất công việc khi worker crash?
3. Khi nhận message bằng Peek-Lock, consumer có quyền xử lý độc quyền vĩnh viễn không?
4. Điều gì xảy ra khi một message bị khóa nhưng worker không Complete kịp?
5. Complete nên được gọi trước hay sau khi kết quả nghiệp vụ ghi bền vững?
6. Vì sao database commit thành công nhưng Complete thất bại vẫn có thể tạo duplicate?
7. Abandon có tự thực hiện exponential backoff hay không?
8. Khi nào nên Dead-letter ngay thay vì retry?
9. Defer khác Dead-letter và Scheduled Message như thế nào?
10. Nếu Defer message rồi không lưu sequence number, có rủi ro gì?
11. LockDuration, TTL và MaxDeliveryCount khác nhau ra sao?
12. Vì sao không dùng LockToken làm idempotency key?
13. AutoLockRenewer làm gì và không bảo đảm điều gì?
14. Khi MessageLockLost xảy ra, có nên Complete tiếp bằng message cũ không?
15. Vì sao prefetch quá lớn có thể dẫn tới lock expiry trước khi xử lý?
16. Session lock khác message lock ở đâu?
17. Duplicate detection của broker có thay thế ledger idempotent không?
18. Tại sao Azure Service Bus transaction không tự gộp cả giao dịch DB?
19. Những thông số nào cần đo trước khi tăng concurrency hoặc MaxDeliveryCount?
20. Khi queue ActiveMessageCount bằng 0, có chắc tất cả job đã hoàn thành không?
21. Lỗi 403 và timeout tới Service Bus có thể bắt nguồn từ những tầng nào?
22. Nêu ba phép thử bắt buộc trước khi đưa một consumer thanh toán vào production.

## Tài liệu tham khảo

- Microsoft Learn — *Message transfers, locks, and settlement*: https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement
- Microsoft Learn — *Service Bus dead-letter queues*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues
- Microsoft Learn — *Message deferral*: https://learn.microsoft.com/azure/service-bus-messaging/message-deferral
- Microsoft Learn — *Service Bus messaging overview*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview
- Microsoft Learn — *Message sessions*: https://learn.microsoft.com/azure/service-bus-messaging/message-sessions
- Microsoft Learn — *Duplicate detection*: https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection
- Microsoft Learn — *Service Bus transactions*: https://learn.microsoft.com/azure/service-bus-messaging/service-bus-transactions
- Microsoft Learn — *Authenticate with Microsoft Entra ID*: https://learn.microsoft.com/azure/service-bus-messaging/authenticate-application
- Microsoft Learn — *Azure Service Bus Python SDK*: https://learn.microsoft.com/python/api/overview/azure/servicebus-readme
