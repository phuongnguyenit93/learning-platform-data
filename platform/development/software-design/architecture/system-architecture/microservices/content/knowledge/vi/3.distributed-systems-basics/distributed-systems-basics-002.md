# Lỗi cục bộ và trạng thái thất bại không đồng thời trong Microservices

> Chủ đề: **Software Architecture → System Architecture → Microservices**  
> Nhóm kiến thức: **Nền tảng phân tán**

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích **lỗi cục bộ (local failure)** và **lỗi từng phần (partial failure)** trong hệ thống phân tán, phân biệt lỗi của một instance, một service, một lời gọi và cả quy trình nghiệp vụ.
- Nhận biết vì sao các thành phần **không phát hiện cùng lúc** một sự cố và vì sao một yêu cầu timeout có thể đã được xử lý thành công.
- Diễn giải trạng thái **thành công, thất bại, đang xử lý và chưa xác định kết quả** mà không đánh đồng quan sát của caller với sự thật của provider.
- Thiết kế cách phối hợp trạng thái đơn hàng, tồn kho, thanh toán khi các bước hoàn tất hoặc thất bại ở các thời điểm khác nhau.
- Chọn những biện pháp phù hợp như timeout, retry có kiểm soát, idempotency, transactional outbox, reconciliation, saga và quan sát phân tán.

## 1. Vì sao “một chỗ lỗi” không đồng nghĩa “cả hệ thống lỗi”?

Trong ứng dụng chạy một tiến trình, các lời gọi hàm có xu hướng chia sẻ một vòng đời tiến trình. Với Microservices, mỗi dịch vụ có thể chạy nhiều instance, ở nhiều máy, qua mạng và sử dụng cơ sở dữ liệu hoặc broker riêng. Vì thế một phần có thể hoạt động bình thường trong khi phần khác chậm, mất kết nối hoặc ngừng chạy.

Ví dụ một hệ thống đặt hàng:

~~~text
Khách hàng
    |
    v
[API Gateway] -------> [Order Service] ---------> [Order DB]
                            |
                            +----> [Inventory Service] ---> [Inventory DB]
                            |
                            +----> [Payment Service] -----> [Payment DB]
                                            |
                                            +----> Cổng thanh toán ngoài
~~~

Giả sử Payment Service mất kết nối với cổng thanh toán:

- Order Service và Inventory Service vẫn có thể hoạt động.
- Hệ thống vẫn có thể nhận yêu cầu mới, nhưng chưa chắc hoàn tất thanh toán.
- Một lệnh thanh toán đang chạy có thể đã được cổng thanh toán xử lý trước khi đường kết nối đứt.
- Người dùng có thể nhận timeout mặc dù tiền đã được ghi nhận.
- Tác vụ nền xử lý webhook hoặc đối soát có thể cập nhật trạng thái sau đó.

Đó là đặc trưng của **partial failure**: một tập con thành phần hoặc thao tác bị lỗi trong khi những phần khác tiếp tục chạy. Lỗi có thể nằm ở process, host, kết nối, dependency, tài nguyên, dữ liệu hoặc một nhánh logic.

### 1.1. Những mức độ “lỗi” cần phân biệt

| Mức độ | Ví dụ | Điều có thể kết luận |
| --- | --- | --- |
| **Instance failure** | Một Pod của Order Service crash | Instance ấy không phục vụ được; các replica khác có thể còn hoạt động. |
| **Request failure** | Một request trả 503 hoặc timeout | Request quan sát được là thất bại/chưa hoàn tất; không suy ra toàn bộ service đã chết. |
| **Dependency failure** | Payment không liên lạc được với cổng bên ngoài | Một năng lực phụ thuộc có thể tạm thời không khả dụng. |
| **Service-level outage** | Mọi instance Payment đều không phục vụ được yêu cầu hợp lệ | Năng lực thanh toán đang gián đoạn, dù dịch vụ khác có thể khỏe. |
| **Workflow failure** | Đơn đã được tạo, nhưng giữ hàng bị từ chối | Quy trình đặt hàng chưa đạt mục tiêu; không có nghĩa bước tạo đơn bị rollback tự động. |
| **Data inconsistency** | Order ghi “đã thanh toán”, Payment ghi “chưa thanh toán” | Có bất đồng giữa các bản nhìn/nguồn sự thật; cần xác định nguyên nhân và cơ chế hội tụ. |

Một lỗi của instance có thể được che bởi load balancer. Ngược lại, hàng loạt instance khỏe vẫn có thể trả lỗi nghiệp vụ vì database dùng chung đang quá tải. Không nên suy ra sức khỏe của cả hệ thống chỉ từ một HTTP status hoặc một health check đơn lẻ.

### 1.2. Lỗi cục bộ và lỗi từng phần

**Lỗi cục bộ** là lỗi phát sinh trong phạm vi một thành phần hoặc một thao tác cụ thể: process hết bộ nhớ, transaction bị rollback, thread pool cạn, một request vi phạm ràng buộc dữ liệu. Nó có thể đã được cô lập và xử lý trong thành phần đó.

**Lỗi từng phần** mô tả ảnh hưởng ở cấp hệ thống: một phần hệ thống không thực hiện được trách nhiệm, trong khi phần khác vẫn còn hoạt động. Một lỗi cục bộ có thể gây ra lỗi từng phần, nhưng không phải mọi lỗi cục bộ đều phát triển thành sự cố lớn. Ngược lại, mất mạng giữa hai dịch vụ có thể tạo partial failure dù **cả hai process đều đang chạy**.

Ví dụ:

~~~text
Inventory Service
  - JVM vẫn sống
  - /health trả lời
  - database vẫn truy cập được

Order Service
  - không kết nối tới Inventory trong 3 giây
  - timeout yêu cầu giữ hàng
~~~

Ở thời điểm đó, Order chỉ biết **mình không nhận được câu trả lời đúng hạn**. Order không thể kết luận chắc chắn Inventory chết, không xử lý yêu cầu, hay đã xử lý nhưng phản hồi thất lạc.

## 2. “Trạng thái thất bại không đồng thời” nghĩa là gì?

Trong hệ thống phân tán, các thành phần không chia sẻ một trạng thái thực thi hoặc một đồng hồ toàn cục hoàn hảo. Thông tin đi qua mạng, hàng đợi, callback và cơ sở dữ liệu với độ trễ khác nhau. Do đó **thời điểm sự cố xảy ra, thời điểm phát hiện, thời điểm ghi nhận, và thời điểm người dùng biết đến có thể khác nhau**.

Một workflow có thể gồm các bước nối tiếp hoặc chạy bất đồng bộ. Nếu có sự cố, từng bước có thể chuyển trạng thái khác lúc:

~~~text
Thời gian ---------------------------------------------------->

Order:      CREATED ---- PENDING_PAYMENT -------- CONFIRMED
Inventory:  RESERVING --- RESERVED ---------------- RESERVED
Payment:    REQUESTED -- PROCESSING -- SUCCEEDED
Network:    OK ---------- TIMEOUT ----- RECOVERED
Client:     SUBMITTED --- "Không rõ kết quả" --- Thấy xác nhận
~~~

Tại thời điểm timeout, Payment có thể đã thành công nhưng Order chưa nhận được chứng cứ. Kết quả là **trạng thái quan sát ở các bên không nhất quán tức thời**. Sau khi kết nối phục hồi, webhook, event hoặc tác vụ đối soát có thể giúp các thành phần hội tụ về kết quả đúng.

Cần phân biệt ba khái niệm:

1. **Thời điểm thực thi:** thao tác thực sự diễn ra ở nơi sở hữu nó, chẳng hạn Payment ghi nhận một giao dịch.
2. **Thời điểm quan sát:** thành phần khác nhìn thấy kết quả, chẳng hạn Order nhận được PaymentSucceeded.
3. **Thời điểm quyết định nghiệp vụ:** hệ thống đủ chứng cứ để đổi trạng thái đơn, xuất hàng hoặc thông báo kết quả cuối cùng.

Ba thời điểm có thể trùng gần nhau trong trường hợp thuận lợi, nhưng không được giả định luôn trùng nhau.

### 2.1. Không đồng thời không chỉ xảy ra khi dùng message queue

Ngay cả luồng HTTP đồng bộ cũng có thể có trạng thái thất bại lệch nhau:

~~~text
t0  Order gửi POST /payments
t1  Payment nhận yêu cầu, xử lý giao dịch
t2  Payment ghi kết quả SUCCEEDED
t3  Phản hồi từ Payment bị mất trên mạng
t4  Order hết timeout, ghi trạng thái UNKNOWN
t5  Tác vụ đối soát xác minh giao dịch thành công
t6  Order cập nhật PAID
~~~

Ở t4, timeout là **kết quả của việc chờ**, không phải bằng chứng t2 không xảy ra. Nếu Order tự đánh dấu PAYMENT_FAILED và gọi thanh toán lần nữa mà không có idempotency, người dùng có thể bị thanh toán hai lần.

### 2.2. Tại sao các thành phần có góc nhìn khác nhau?

- **Độ trễ mạng:** gói tin đến chậm, đi qua nhiều chặng, hoặc bị mất.
- **Timeout khác nhau:** client hết hạn chờ trước khi server thực sự hoàn tất.
- **Xếp hàng:** event được tạo nhưng còn nằm trong broker hoặc backlog của consumer.
- **Lịch thực thi độc lập:** process được cấp CPU khác thời điểm; một instance đang garbage collection hoặc restart.
- **Cơ chế retry:** cùng một yêu cầu có thể tới nhiều lần tại những thời điểm khác nhau.
- **Bản sao dữ liệu:** cache, read replica hoặc projection có thể chậm hơn nguồn ghi chính.
- **Đồng hồ lệch:** timestamp của các máy không tạo ra thứ tự tuyệt đối đáng tin cậy cho mọi sự kiện.

Vì vậy, **không nên dùng timestamp ở hai máy để tự suy ra chắc chắn thứ tự nhân quả** khi không có quan hệ truyền thông hoặc cơ chế thứ tự phù hợp. Cần dựa vào các dấu vết như request ID, message ID, phiên bản trạng thái, sequence number hoặc quan hệ “sự kiện A dẫn đến B”.

## 3. Mô hình quan sát kết quả: thành công, thất bại và chưa biết

Khi caller gọi một dịch vụ từ xa, hãy phân biệt **sự thật phía provider** với **điều caller quan sát**.

| Caller quan sát | Điều có thể đã xảy ra tại provider | Hành động nên cân nhắc |
| --- | --- | --- |
| Nhận phản hồi thành công hợp lệ | Provider cam kết đã hoàn tất phần việc theo contract | Ghi nhận đúng ngữ nghĩa thành công; không suy diễn thêm các bước ngoài contract. |
| Nhận lỗi nghiệp vụ rõ ràng như “hết tồn” | Provider đã xét điều kiện và từ chối thao tác | Ghi nhận thất bại nghiệp vụ; thường không retry y nguyên nếu dữ liệu chưa đổi. |
| Không kết nối được trước khi gửi request | Có thể request chưa tới provider, nhưng bằng chứng phụ thuộc tầng mạng | Phân loại lỗi; retry nếu hợp đồng cho phép. |
| Timeout sau khi gửi | Provider có thể chưa nhận, đang chạy, đã thành công hoặc đã lỗi | Gắn trạng thái **UNKNOWN/IN_DOUBT**; tra cứu kết quả và retry an toàn nếu được thiết kế. |
| Kết nối đứt khi đang nhận response | Provider có thể đã commit trước khi response mất | Dựa vào operation ID/idempotency key để truy vấn hoặc đối soát. |
| Nhận 5xx | Hệ thống phía provider không phục vụ bình thường; side effect có thể đã xảy ra tùy điểm lỗi và contract | Không tự động coi mọi 5xx là “chưa làm gì”; đánh giá retry semantics. |

Tên trạng thái **UNKNOWN** không có nghĩa provider có trạng thái UNKNOWN trong database. Nó là trạng thái **thiếu thông tin của bên quan sát**. Trong một số miền nghiệp vụ, ta cần lưu nó thành trạng thái kỹ thuật như VERIFYING hoặc PAYMENT_RESULT_PENDING để thúc đẩy đối soát.

### 3.1. Lỗi kỹ thuật khác thất bại nghiệp vụ

- **Lỗi kỹ thuật:** timeout, broker unavailable, connection reset, database failover, process crash. Nó cho biết kênh xử lý có vấn đề.
- **Thất bại nghiệp vụ:** hết hàng, thẻ bị từ chối, hạn mức không đủ, đơn đã hủy. Nó là kết luận theo quy tắc miền nghiệp vụ.
- **Kết quả chưa biết:** không đủ chứng cứ để khẳng định thành công hay thất bại. Đặc biệt phổ biến khi đường phản hồi bị mất.

Nếu Payment trả “thẻ bị từ chối” theo contract, Order có thể xử lý PAYMENT_REJECTED. Nếu Order chỉ bị timeout, ghi PAYMENT_REJECTED sẽ là một suy đoán sai. Cách an toàn thường là giữ trạng thái đang xác minh và xác định thời hạn xử lý riêng.

### 3.2. “Không nhận phản hồi” không chứng minh “chưa có side effect”

Hãy xét lệnh thay đổi dữ liệu:

~~~text
Caller                 Provider                  Database
   | POST /reserve         |                          |
   |---------------------->|  BEGIN                   |
   |                       |  UPDATE reservation      |
   |                       |------------------------->|
   |                       |  COMMIT                  |
   |                       |<-------------------------|
   |   X response mất      |                          |
   | ...timeout...         |                          |
~~~

Provider đã commit trong database. Caller không nhìn thấy kết quả. Gửi lại lệnh như một giao dịch mới có thể giữ hàng hai lần nếu provider không có cơ chế nhận diện request lặp.

Điểm cốt lõi: **transport failure** không tương đương **business transaction failure**.

## 4. Một case study: đơn hàng, giữ hàng và thanh toán

Giả sử hệ thống có ba service:

- **Order Service** sở hữu vòng đời đơn.
- **Inventory Service** sở hữu dữ liệu tồn và reservation.
- **Payment Service** sở hữu yêu cầu và kết quả thanh toán.

Một đơn “thành công” cần đạt các điều kiện miền nghiệp vụ do hệ thống định nghĩa, ví dụ giữ hàng thành công và thanh toán thành công. Tuy nhiên, không có transaction ACID chung tự động bao phủ cả ba database.

### 4.1. Luồng không có sự cố

~~~text
Client               Order              Inventory           Payment
  | CreateOrder         |                    |                  |
  |-------------------->|                    |                  |
  |                     | Reserve            |                  |
  |                     |------------------->|                  |
  |                     |<---- RESERVED -----|                  |
  |                     | Charge                                |
  |                     |-------------------------------------->|
  |                     |<---------------- SUCCEEDED -----------|
  |<---- CONFIRMED -----|                    |                  |
~~~

Mỗi service commit dữ liệu thuộc boundary của mình. Sau khi đủ điều kiện, Order Service đổi trạng thái đơn và trả về kết quả phù hợp contract.

### 4.2. Luồng có lỗi ở nhiều thời điểm

| Thời điểm logic | Order | Inventory | Payment | Quan sát từ client |
| --- | --- | --- | --- | --- |
| T0 | Đã lưu đơn PENDING | Chưa nhận lệnh | Chưa nhận lệnh | Đã gửi đơn |
| T1 | Đã gửi Reserve | Đang xử lý | Chưa nhận lệnh | Đang chờ |
| T2 | Biết RESERVED | Reservation đã commit | Chưa nhận lệnh | Đang chờ |
| T3 | Đã gửi Charge | RESERVED | Đã nhận và xử lý thanh toán | Có thể vẫn đang chờ |
| T4 | Timeout khi đợi Payment; ghi VERIFYING | RESERVED | Thực tế SUCCEEDED | UI báo “Đang xác minh” |
| T5 | Chưa nhận event do broker chậm | RESERVED | Đã phát PaymentSucceeded | Có thể xem trạng thái tạm |
| T6 | Nhận event hoặc đối soát kết quả | RESERVED | SUCCEEDED | UI chuyển CONFIRMED |

Tại T4, nếu Order thực hiện hoàn tiền hoặc nhả hàng ngay do nghĩ Payment thất bại, nó có thể tạo một quy trình bù trừ sai thời điểm. Nếu nhận PaymentSucceeded ở T6, Order phải xét lại trạng thái hiện tại và các quy tắc chuyển tiếp.

### 4.3. Tác động của đảo thứ tự và trùng lặp

Giả sử vì retry và độ trễ, Order nhận các event theo thứ tự:

~~~text
T1: PaymentSucceeded(payment-7)
T2: PaymentProcessing(payment-7)     (event cũ đến muộn)
T3: PaymentSucceeded(payment-7)      (event gửi lại)
~~~

Nếu xử lý đơn thuần bằng “event mới đến thì ghi đè status”, Order có thể bị chuyển lùi từ PAID về PROCESSING hoặc phát hành hàng hai lần.

Thiết kế an toàn cần:

- Dùng **paymentId/operationId** để xác định giao dịch đang xét.
- Kiểm tra **transition hợp lệ**: PAID không chuyển ngược về PROCESSING chỉ vì thông điệp đến muộn.
- Nhận diện event trùng bằng **eventId**, phiên bản aggregate hoặc idempotent handler.
- Ghi cập nhật và marker “đã xử lý event” với ranh giới transaction phù hợp khi có thể.
- Nếu event mâu thuẫn, thực hiện **reconciliation** với nguồn sự thật của Payment thay vì đoán theo thứ tự nhận.

Thông điệp đến trễ có thể vẫn là dữ liệu đúng về quá khứ; lỗi xảy ra khi consumer dùng nó để ghi đè trạng thái hiện tại mà thiếu kiểm tra ngữ nghĩa và thứ tự.

## 5. Thiết kế state machine chịu được lỗi từng phần

Một boolean như paymentSuccess=true/false thường không đủ để biểu diễn quá trình có timeout, xử lý chậm và cần xác minh.

Một ví dụ trạng thái đơn:

~~~text
              +----------------+
              |    CREATED     |
              +-------+--------+
                      |
                      v
             +------------------+
             | RESERVING_STOCK  |
             +---+----------+---+
                 |          |
          reserved         rejected
                 |          v
                 v       REJECTED
          +----------------+
          | PAYMENT_PENDING|
          +-------+--------+
                  |
            gửi yêu cầu
                  v
          +----------------+
          | PAYMENT_CHECK  |
          +---+--------+---+
              |        |
       verified paid    verified rejected
              |        |
              v        v
          CONFIRMED   COMPENSATING
                           |
                           v
                        CANCELLED
~~~

Đây là **mô hình minh họa**, không phải danh sách trạng thái bắt buộc cho mọi hệ thống. Tên trạng thái và điều kiện chuyển phải dựa vào yêu cầu nghiệp vụ thật.

### 5.1. Nguyên tắc của state machine

1. **Phân biệt trạng thái trung gian và trạng thái cuối.** PAYMENT_CHECK có thể diễn ra nhiều phút; CONFIRMED hoặc CANCELLED thường mang ý nghĩa kết luận ở mức đơn hàng.
2. **Mỗi chuyển tiếp có điều kiện.** Ví dụ chỉ được CONFIRMED khi có bằng chứng payment hợp lệ và reservation còn hiệu lực.
3. **Không tin tuyệt đối vào thứ tự message đến.** Dựa vào định danh và phiên bản trạng thái; xử lý event cũ theo quy tắc rõ ràng.
4. **Đảm bảo xử lý lặp an toàn.** Một sự kiện thành công được gửi lại không được tạo thêm lần giao hàng hoặc ghi tiền lần thứ hai.
5. **Mọi trạng thái tạm cần lối thoát.** Có job giám sát, deadline, cảnh báo và quy trình xác minh thay vì treo vô thời hạn.
6. **Quyết định được ghi bền vững.** Chỉ giữ trạng thái trong RAM của một instance khiến mất tiến độ khi Pod bị restart.

Một ví dụ quy tắc chuyển tiếp:

| Trạng thái hiện tại | Tín hiệu | Chuyển tiếp | Ghi chú |
| --- | --- | --- | --- |
| PAYMENT_PENDING | PaymentRequested đã lưu | PAYMENT_CHECK | Không coi request gửi đi là đã thanh toán. |
| PAYMENT_CHECK | PaymentSucceeded hợp lệ | CONFIRMED | Kiểm tra paymentId, amount, orderId và trạng thái giữ hàng. |
| PAYMENT_CHECK | PaymentRejected có xác nhận | COMPENSATING | Bắt đầu nhả reservation nếu đã giữ hàng. |
| PAYMENT_CHECK | HTTP timeout | PAYMENT_CHECK | Tiếp tục xác minh; chưa tự kết luận thất bại. |
| CONFIRMED | PaymentSucceeded lặp | CONFIRMED | Bỏ qua tác dụng phụ lặp; vẫn có thể ghi metric. |
| CONFIRMED | PaymentProcessing đến muộn | CONFIRMED | Không cho chuyển trạng thái lùi. |
| COMPENSATING | ReleaseStockSucceeded | CANCELLED | Chỉ hoàn tất sau khi đã đạt điều kiện bù trừ cần thiết. |

Nếu một luồng nghiệp vụ có thể thay đổi sau khi “final”, hãy mô tả **chuyển tiếp mới** như REFUND_PENDING/REFUNDED, thay vì ngầm sửa ý nghĩa CONFIRMED.

### 5.2. Local transaction có giới hạn ở đâu?

~~~text
Order DB transaction:
  - lưu Order = PAYMENT_CHECK
  - lưu OutboxEvent = PaymentRequested
  - COMMIT

Payment DB transaction (độc lập):
  - lưu PaymentAttempt = SUCCEEDED
  - COMMIT
~~~

Transaction đầu chỉ bảo đảm tính nguyên tử giữa những thay đổi thuộc Order DB. Nó **không tự động** commit hay rollback Payment DB. Khi bước sau lỗi, Order cần quy trình xử lý tiếp tục hoặc bù trừ theo hợp đồng nghiệp vụ.

## 6. Timeout, retry và idempotency: ba cơ chế không thể tách rời

### 6.1. Timeout là giới hạn chờ, không phải bằng chứng thất bại

Caller cần timeout để không treo mãi. Nhưng timeout chỉ giới hạn **thời gian caller sẵn sàng chờ**. Nó không bảo đảm server đã dừng xử lý.

Nên xem xét:

- **Connection timeout:** giới hạn thiết lập kết nối.
- **Request/read timeout:** giới hạn đợi kết quả của một lời gọi.
- **Overall deadline:** giới hạn thời gian toàn bộ thao tác/request đi qua nhiều service.
- **Business deadline:** hạn nghiệp vụ, chẳng hạn giữ hàng tối đa một khoảng thời gian nhất định.

Nếu API Gateway chờ 2 giây, Order chờ Inventory 3 giây, Inventory chờ database 5 giây thì các thời hạn mâu thuẫn có thể gây xử lý vô ích sau khi client đã bỏ cuộc. Cần phân phối deadline giữa các chặng và hỗ trợ hủy khi thích hợp, nhưng việc gửi tín hiệu cancel **không bảo đảm side effect đã được rollback**.

### 6.2. Retry có điều kiện

Retry hợp lý với một số lỗi tạm thời, nhưng retry có thể tăng tải đúng lúc hệ thống đang quá tải. Mỗi tầng đều retry sẽ nhân số lần gọi:

~~~text
Gateway retry 3 lần
   x Order retry 3 lần
      x Payment retry 3 lần
          = tối đa 27 attempt cho một thao tác logic
~~~

Đây là ví dụ minh họa hiện tượng **retry amplification**, chưa tính các thử lại do client/broker.

Nguyên tắc:

- Chỉ retry khi **contract nói rõ điều kiện an toàn** và lỗi có khả năng tạm thời.
- Dùng **bounded retries**, exponential backoff và jitter; tôn trọng deadline và Retry-After nếu có.
- Tránh nhiều tầng tự retry cùng một thao tác mà không có ngân sách chung.
- Không retry vô hạn một lỗi nghiệp vụ chắc chắn, chẳng hạn số lượng đặt lớn hơn tồn khả dụng.
- Với thao tác tạo side effect, cần **idempotency** hoặc một bước query/reconciliation trước khi phát thêm attempt.
- Theo dõi số attempt, độ trễ và tác động đến downstream.

### 6.3. Idempotency là gì?

Một thao tác **idempotent** là khi thực hiện lại cùng một yêu cầu logic không tạo thêm thay đổi nghiệp vụ ngoài hiệu ứng đã được chấp nhận ở lần đầu. Điều này khác với việc mọi response bytes đều phải giống nhau trong mọi thời điểm, mặc dù nhiều API chọn trả lại kết quả đã lưu để consumer dễ dùng.

Ví dụ:

~~~http
POST /v1/payments
Idempotency-Key: order-1001-payment-v1
Content-Type: application/json

{
  "orderId": "order-1001",
  "amount": 340000,
  "currency": "VND"
}
~~~

Nếu request timeout, client gọi lại với **cùng khóa cho cùng thao tác logic**. Payment Service có thể trả trạng thái hoặc kết quả của payment attempt cũ thay vì tạo giao dịch mới.

Nhưng chỉ gắn header chưa đủ. Provider cần thiết kế:

- Phạm vi khóa: theo tenant, customer, order hoặc operation type.
- Kiểm tra payload: cùng khóa nhưng dữ liệu khác phải bị xử lý theo contract đã công bố.
- Lưu bền vững trạng thái attempt và kết quả/operation ID phù hợp.
- Xử lý request trùng **đồng thời**, ví dụ bằng unique constraint và transaction/cơ chế khóa phù hợp.
- TTL của khóa và chính sách sau khi hết hạn; caller không được giả định khóa tồn tại mãi.
- Phân biệt response của thao tác đã chạy xong và thao tác còn IN_PROGRESS.

**Idempotency ở API nội bộ không tự động bảo vệ side effect ở hệ thống ngoài.** Payment Service cũng cần dùng định danh/khóa idempotency do cổng thanh toán hỗ trợ hoặc quy trình đối soát tương ứng.

### 6.4. At-most-once, at-least-once và xử lý thực tế

| Mô hình giao nhận/xử lý | Khả năng | Đánh đổi |
| --- | --- | --- |
| **At-most-once** | Không chủ động phát lại sau khi giao một lần | Có thể mất tác vụ/thông điệp khi lỗi. |
| **At-least-once** | Gửi lại để tăng khả năng xử lý | Có thể giao hoặc xử lý trùng. |
| **Exactly-once** | Một số nền tảng bảo đảm trong phạm vi định nghĩa rất cụ thể | Không được suy ra mọi side effect xuyên service, DB và API ngoài đều xảy ra đúng một lần. |

Với at-least-once delivery, consumer phải chịu được message trùng. Một thao tác tài chính cần **idempotent business effect**, không chỉ “đã ack một message”.

## 7. Ngăn mất thông điệp ở ranh giới lưu dữ liệu

Một lỗi khó phát hiện là **dual write**: service vừa ghi database vừa gửi message, nhưng hai việc không nằm trong cùng một transaction nguyên tử.

~~~text
Bước 1: Order DB commit trạng thái PAYMENT_CHECK
Bước 2: Process crash trước khi publish PaymentRequested
=> Trạng thái đã đổi, nhưng Payment không nhận lệnh
~~~

Nếu đổi thứ tự publish trước khi commit, lại có thể xảy ra event gửi thành công nhưng dữ liệu Order bị rollback. Hai thứ tự đơn giản đều để lại cửa sổ lỗi.

### 7.1. Transactional outbox

Một phương án phổ biến:

1. Trong **cùng transaction Order DB**, lưu trạng thái nghiệp vụ và một bản ghi outbox.
2. Một publisher riêng đọc outbox rồi gửi event/message tới broker.
3. Chỉ sau khi có xác nhận phù hợp, publisher đánh dấu đã gửi; nếu crash, có thể phát lại.
4. Consumer dùng idempotent handler hoặc inbox/deduplication để chịu được duplicate.

~~~text
Order Service
  BEGIN DB TRANSACTION
     UPDATE orders SET status = PAYMENT_CHECK ...
     INSERT INTO outbox(event_id, type, payload, status) ...
  COMMIT

Outbox Publisher ----> Message Broker ----> Payment Consumer
       retry                                   deduplicate
~~~

Outbox giúp giảm nguy cơ **DB đã commit nhưng event biến mất vĩnh viễn do process crash**. Nó **không đồng nghĩa message được giao đúng một lần**: publisher có thể gửi thành công rồi crash trước khi đánh dấu gửi; vì vậy consumer vẫn cần xử lý lặp.

Nếu Payment nhận một message nhưng crash sau khi xử lý side effect và trước khi ack, broker có thể giao lại. Cần phối hợp message ID, business operation ID, transaction record và trạng thái đã xử lý để không lặp tác động.

### 7.2. Inbox/deduplication và thứ tự message

Consumer có thể lưu eventId đã xử lý trong cùng transaction với cập nhật dữ liệu cục bộ. Khi gặp bản sao, nó nhận diện và bỏ qua side effect. Tuy nhiên, một event ID mới đại diện cho cùng thao tác nghiệp vụ cũng có thể gây lặp; do đó dedupe ở message và **idempotency theo business key** là hai tầng khác nhau.

Nếu thứ tự là bắt buộc, có thể dùng:

- Sequence/version theo từng orderId, không phụ thuộc đồng hồ máy.
- Partition key theo aggregate để hỗ trợ thứ tự trong phạm vi broker quy định.
- Optimistic concurrency trên bản ghi domain.
- Bộ đệm hoặc quy trình truy vấn lại trạng thái khi phát hiện thiếu version.

Không giả định có thứ tự toàn cục giữa mọi partition, mọi service và mọi transport.

## 8. Saga và bù trừ khi thất bại ở thời điểm khác nhau

Một giao dịch liên dịch vụ thường được diễn đạt thành **chuỗi transaction cục bộ**. Saga điều phối các bước và những hành động khôi phục khi một bước không đạt yêu cầu.

Ví dụ:

~~~text
1. Order tạo đơn PENDING
2. Inventory giữ hàng
3. Payment thu tiền
4. Order xác nhận đơn

Nếu 3 thất bại đã được xác minh:
    -> Yêu cầu Inventory nhả hàng
    -> Cập nhật trạng thái đơn theo kết quả bù trừ
~~~

Hai cách phổ biến:

- **Choreography:** các service phản ứng với sự kiện của nhau theo quy tắc đã định; giảm một điểm điều phối trung tâm nhưng luồng tổng thể có thể khó theo dõi.
- **Orchestration:** một thành phần điều phối/tiến trình nghiệp vụ quyết định bước tiếp theo và trạng thái của saga; thường dễ quan sát luồng tổng thể hơn, nhưng chính nó cần lưu tiến độ và phục hồi khi lỗi.

Không có phương án tự động tốt nhất cho mọi hệ thống. Điều quan trọng là **bước nào thuộc quyền quyết định của service nào, bước nào có thể bù trừ, và lúc nào được phép tuyên bố kết thúc**.

### 8.1. Compensation không phải rollback vật lý

Một thao tác bù trừ là **nghiệp vụ mới** làm giảm hoặc đảo ngược tác động của bước trước. Nó có thể thất bại và có thể không khôi phục thế giới chính xác như chưa từng xảy ra thao tác.

Ví dụ:

- Đã giữ hàng → nhả reservation có thể là compensation tương đối đơn giản.
- Đã thanh toán → hoàn tiền là giao dịch riêng, có độ trễ, phí, bước kiểm soát và trạng thái REFUND_PENDING.
- Đã gửi email → không thể “thu hồi” email chỉ bằng rollback database.
- Đã giao hàng → cần quy trình hoàn trả, không thể xóa dấu vết giao hàng.

Vì thế khi Payment timeout và outcome chưa biết, **không nên vội refund**. Trước hết cần định danh và xác minh giao dịch nào thực sự thành công.

### 8.2. Chống trạng thái treo

Một saga cần được thiết kế để không mắc kẹt mãi trong PAYMENT_CHECK hoặc COMPENSATING:

- Lưu trạng thái, attempt count, operation ID, deadline và bước tiếp theo.
- Có worker quét các quy trình quá hạn và kiểm tra nguồn sự thật.
- Retry bước còn dang dở theo chính sách, không lặp nghiệp vụ bừa bãi.
- Đưa trường hợp mâu thuẫn hoặc không thể tự giải quyết vào **manual review** có dữ liệu truy vết.
- Định nghĩa khi nào có thể chuyển về trạng thái cuối và cách người dùng được thông báo.

Lưu ý: **deadline kỹ thuật** không đương nhiên là hạn kết thúc nghiệp vụ. Hết thời gian chờ phản hồi của API không có nghĩa được phép hủy một giao dịch thanh toán đã commit.

## 9. Cách cô lập lỗi và tránh lan truyền

Tình trạng một dependency chậm dễ làm service phía trước hết thread, connection pool hoặc hàng đợi. Khi nhiều request cùng mắc kẹt, một lỗi cục bộ có thể lan rộng thành outage.

Các cơ chế thường được cân nhắc:

| Biện pháp | Mục đích | Rủi ro nếu dùng sai |
| --- | --- | --- |
| **Timeout/deadline** | Giới hạn thời gian chiếm tài nguyên của caller | Quá ngắn tạo false timeout và nhiều kết quả UNKNOWN. |
| **Retry với backoff/jitter** | Phục hồi lỗi thoáng qua | Khuếch đại tải và tác dụng phụ nếu thiếu idempotency. |
| **Circuit breaker** | Tạm ngưng gọi dependency có tỉ lệ lỗi cao | Có thể chặn cả request đã hồi phục nếu cấu hình chưa phù hợp. |
| **Bulkhead** | Tách pool/tài nguyên để một nhánh chậm không kéo sập mọi nhánh | Cần phân bổ tài nguyên theo ưu tiên thực tế. |
| **Rate limit/backpressure** | Giới hạn tốc độ nhận so với năng lực xử lý | Nếu không có chính sách phản hồi/hàng đợi, khách hàng chỉ thấy lỗi khó hiểu. |
| **Load balancing/health check** | Né instance lỗi, sử dụng replica khỏe | Health check đơn giản không phát hiện mọi lỗi nghiệp vụ hay dependency. |
| **Graceful degradation** | Giữ các chức năng an toàn còn khả dụng | Không được giả vờ “đã thanh toán/đã đặt hàng” khi chưa có xác nhận. |
| **Reconciliation** | Đối chiếu và sửa sai khác trạng thái | Phải biết nguồn sự thật và định danh nghiệp vụ đáng tin. |

Các biện pháp trên có mục tiêu khác nhau. Circuit breaker bảo vệ tài nguyên caller; nó **không chứng minh** bên kia không xử lý request trước đó. Reconciliation xác minh sự thật sau lỗi; nó **không thay thế** idempotency khi phát lại.

### 9.1. Khi nào nên degrade?

Một trang sản phẩm có thể tạm không hiển thị phần gợi ý mua kèm nếu Recommendation Service lỗi. Ngược lại, không nên cho phép “đặt hàng thành công” bằng cách bỏ qua kiểm tra tồn hoặc xác nhận thanh toán khi đó là bất biến nghiệp vụ của hệ thống.

Chiến lược degrade phải được quyết định bởi **mức chấp nhận của nghiệp vụ**, không chỉ do HTTP client có thể catch exception.

## 10. Contract API và trải nghiệm người dùng trong trạng thái chưa chắc chắn

Một API tốt cần diễn đạt rõ **đã nhận yêu cầu**, **đã hoàn thành** và **chưa xác định kết quả**.

Ví dụ API tạo yêu cầu thanh toán bất đồng bộ:

~~~http
POST /v1/payments
Idempotency-Key: order-1001-payment-v1
Content-Type: application/json

{
  "orderId": "order-1001",
  "amount": 340000,
  "currency": "VND"
}
~~~

Nếu provider đã chấp nhận tác vụ và xử lý sau, một contract có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/payment-operations/payop-77
Content-Type: application/json

{
  "operationId": "payop-77",
  "status": "PROCESSING"
}
~~~

Một endpoint truy vấn tiến độ:

~~~http
GET /v1/payment-operations/payop-77

HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "payop-77",
  "status": "SUCCEEDED",
  "paymentId": "pay-9001"
}
~~~

Đây là **contract minh họa**, không phải chuẩn bắt buộc cho mọi dịch vụ. 202 xác nhận request được chấp nhận xử lý, **chưa bảo đảm kết quả cuối**. API vẫn cần chỉ rõ định dạng lỗi, bảo mật, tần suất polling, thời hạn giữ trạng thái và ý nghĩa các giá trị status.

Từ góc nhìn sản phẩm:

- Khi chưa biết kết quả, hiển thị **“Đang xác minh kết quả”** thay vì kết luận “Thất bại” hoặc “Đã thanh toán”.
- Cung cấp mã giao dịch/đơn hàng để người dùng truy vấn lại mà không tạo giao dịch mới.
- Nếu nút “Thử lại” được cung cấp, hệ thống phải dùng cùng định danh thao tác hoặc quy trình kiểm tra bảo đảm an toàn.
- Thông báo trạng thái cuối sau khi có chứng cứ từ nguồn sở hữu.
- Với giao dịch quan trọng, để lại lịch sử trạng thái và hỗ trợ đối soát khi cần.

Thiết kế contract nên nêu rõ sự khác biệt giữa **business status** và **HTTP/transport status**. Một HTTP 200 cho GET /operations chỉ nói truy vấn status thành công; bên trong payload, operation có thể FAILED.

## 11. Quan sát và điều tra lỗi lệch thời điểm

Vì các bên nhìn thấy sự cố khác lúc nhau, một dòng log “timeout” tại Order không đủ để kết luận nguyên nhân gốc.

### 11.1. Những định danh nên đi xuyên suốt

- **Trace ID:** nối các span của một request hoặc luồng phân tán khi hệ thống tracing hỗ trợ.
- **Correlation ID:** liên kết những thao tác của cùng quy trình nghiệp vụ, kể cả qua message bất đồng bộ.
- **Order ID, paymentId, reservationId:** định danh đối tượng và thao tác trong miền nghiệp vụ.
- **Request ID, idempotency key, eventId:** phân biệt attempt, một thao tác logic và từng message.
- **Service, instance, version:** chỉ rõ nơi xử lý và phiên bản đang chạy.

Các ID có thể liên quan nhưng không hoàn toàn thay thế nhau. Một orderId có thể có nhiều payment attempt khác nhau; dùng orderId làm khóa duy nhất cho mọi thanh toán có thể chặn nhầm lần thanh toán hợp lệ sau khi người dùng đổi phương thức.

### 11.2. Metrics cần theo dõi

| Nhóm tín hiệu | Ví dụ câu hỏi |
| --- | --- |
| **Availability** | Bao nhiêu request hợp lệ hoàn tất theo contract? |
| **Latency** | P95/P99 thời gian xử lý và thời gian chờ dependency? |
| **Error by type** | Có bao nhiêu 4xx nghiệp vụ, 5xx hạ tầng, timeout và UNKNOWN? |
| **Retry pressure** | Mỗi thao tác logic tạo bao nhiêu attempt? Bao nhiêu trùng lặp? |
| **Queue health** | Backlog, consumer lag, dead-letter và tuổi message lâu nhất? |
| **Workflow health** | Bao nhiêu đơn kẹt PAYMENT_CHECK quá deadline nghiệp vụ? |
| **Reconciliation** | Bao nhiêu bản ghi bất nhất được phát hiện/giải quyết? |
| **Resource** | Thread/connection pool, CPU, memory, DB locks, saturation? |

Chú ý tránh **cardinality quá cao** khi gắn từng orderId/paymentId làm label metrics. Những ID chi tiết thường phù hợp hơn trong log hoặc trace, còn metric nên có nhãn ổn định.

### 11.3. Quy trình điều tra một lỗi timeout

1. Từ request của người dùng, lấy correlation ID/orderId và mốc thời gian theo nguồn có độ tin cậy.
2. Tìm span/lời gọi từ Order sang Payment: đã gửi request nào, tới endpoint/instance nào, timeout ở chặng nào?
3. Tra bản ghi Payment bằng operationId/idempotency key để biết side effect thực tế.
4. Kiểm tra outbox, broker, consumer lag và các message bị retry/dead-letter.
5. So sánh trạng thái bền vững của Order, Inventory, Payment; tách **dữ liệu nguồn** với cache/projection có thể chậm.
6. Dựa vào state machine và quy tắc nghiệp vụ để tiếp tục, bù trừ hoặc chuyển manual review.
7. Ghi nhận nguyên nhân kỹ thuật, thời gian bất nhất, tác động người dùng và cách ngăn tái diễn.

Không dùng log tại một instance làm bằng chứng phủ định rằng các instance khác hoặc hệ thống ngoài chưa xử lý thao tác.

## 12. Kiểm thử tình huống lỗi thay vì chỉ kiểm thử đường thành công

Một bài test happy path “Order → Inventory → Payment → CONFIRMED” chưa phản ánh hành vi khi các bước thất bại khác thời điểm. Những kịch bản đáng kiểm chứng:

| Tình huống | Kỳ vọng thiết kế |
| --- | --- |
| Inventory từ chối giữ hàng có lý do nghiệp vụ | Order chuyển đúng trạng thái từ chối, không tiếp tục thanh toán không hợp lệ. |
| Payment commit thành công nhưng response mất | Order vào trạng thái xác minh, tra cứu và cuối cùng ghi nhận thành công; không thanh toán trùng. |
| Order crash sau khi commit DB trước khi gửi message | Outbox còn bản ghi và publisher gửi được sau khi hồi phục. |
| Publisher gửi event thành công rồi crash trước khi ack/đánh dấu | Event có thể gửi lại; consumer xử lý lặp an toàn. |
| PaymentSucceeded đến hai lần | Không phát sinh shipment hoặc side effect lần hai. |
| PaymentProcessing đến sau PaymentSucceeded | Trạng thái không bị chuyển lùi. |
| Consumer tạm ngưng, broker tồn backlog | Workflow hiển thị trạng thái trung gian hợp lệ; tiếp tục khi consumer hồi phục. |
| Hết deadline nhưng kết quả payment chưa xác minh | Không tự gán rejected; chuyển nhánh tra cứu/cảnh báo theo policy. |
| Compensation nhả hàng lỗi tạm thời | Saga lưu tiến độ, retry có giới hạn hoặc chuyển xử lý vận hành. |
| Ứng dụng chạy nhiều instance và một instance bị kill | Yêu cầu mới được chuyển tới instance khỏe, tiến trình nghiệp vụ đã lưu vẫn tiếp tục được. |

Có thể mô phỏng bằng fault injection có kiểm soát, test double trả timeout sau commit, ngắt broker, delay message, tắt consumer hoặc thực hiện rolling restart trong môi trường thử nghiệm. Các kịch bản cần kiểm tra **dữ liệu cuối, số side effect và hành vi khi lặp**, không chỉ HTTP status.

### 12.1. Một kịch bản cần đặc biệt chú ý: timeout sau commit

~~~text
Given:
  Payment chưa có bản ghi cho operation X.
  Order gửi Charge(X) với idempotency key K.

When:
  Payment xử lý thành công và commit.
  Phản hồi đầu tiên bị mất.
  Order timeout và phát lại Charge(X) với K.

Then:
  Chỉ có một business payment được tạo cho X.
  Lời gọi lặp trả hoặc dẫn về cùng kết quả/operation theo contract.
  Order cuối cùng nhận được trạng thái thanh toán chính xác.
~~~

Đây là test có giá trị vì nó phân biệt **“retry hoạt động”** với **“retry không tạo tác dụng phụ nguy hiểm”**.

## 13. Những hiểu nhầm thường gặp

**“Timeout nghĩa là server không chạy thao tác.”**  
Không đúng. Request có thể chưa đến, đang chạy hoặc đã commit; timeout chỉ phản ánh caller không có phản hồi đúng hạn.

**“Một service lỗi sẽ làm cả Microservices architecture lỗi.”**  
Không luôn đúng. Lỗi từng phần cho phép phần còn lại tiếp tục, nếu thiết kế ranh giới, tài nguyên và fallback phù hợp. Nhưng dependency quan trọng vẫn có thể làm suy giảm chức năng cốt lõi.

**“Các service phải cùng lúc chuyển sang FAILED.”**  
Không. Chúng không chia sẻ đồng hồ, transaction và trạng thái tức thời. Mỗi service có thể ghi nhận kết quả ở thời điểm khác nhau; quy trình cần phương án hội tụ.

**“HTTP 200 là nghiệp vụ đã hoàn thành toàn bộ.”**  
Chỉ đúng nếu contract quy định như vậy. Trả 200 cho endpoint truy vấn có thể đi kèm payload status=PROCESSING; 202 thường biểu diễn chấp nhận tác vụ chưa hoàn tất.

**“Retry nhiều lần sẽ làm hệ thống tin cậy hơn.”**  
Retry thiếu giới hạn có thể khuếch đại tải và lặp side effect. Phải gắn với điều kiện lỗi, deadline và idempotency.

**“Có Kafka/broker là exactly-once end-to-end.”**  
Không thể suy ra điều đó. Cần xét phạm vi bảo đảm của broker, transaction của database, consumer và các side effect bên ngoài.

**“Saga rollback tất cả như một transaction database.”**  
Không đúng. Compensation là thao tác nghiệp vụ mới, đôi khi bất khả thi hoặc không đảo ngược hoàn toàn hiệu ứng đã xảy ra.

**“Event đến sau là trạng thái mới nhất.”**  
Không. Thứ tự nhận có thể khác thứ tự nghiệp vụ. Consumer cần xác thực nguồn, version, transition và quan hệ nhân quả.

**“Instance vẫn healthy thì mọi request của service khỏe.”**  
Không. Readiness/liveness chỉ quan sát một phần. DB, pool, downstream hoặc lỗi logic có thể khiến request thất bại dù process còn sống.

## 14. Bài tập ứng dụng

### Bài 1: Phân loại kết quả

Order gửi Charge, Payment đã commit SUCCEEDED, nhưng response bị mất; Order ghi timeout.

**Câu hỏi:** Đây là payment thất bại hay chỉ là kết quả chưa xác định ở Order? Có nên gửi một Charge mới với transaction ID khác?

**Gợi ý trả lời:** Payment thực tế đã thành công; Order chỉ thiếu thông tin ở thời điểm timeout. Cần truy vấn trạng thái theo operation ID/idempotency key hoặc đối soát, tránh tạo Charge mới độc lập. Có thể retry cùng thao tác logic nếu contract bảo đảm an toàn.

### Bài 2: Hai message trái thứ tự

Order nhận PaymentSucceeded ở thời điểm A, sau đó nhận PaymentPending ở thời điểm B.

**Câu hỏi:** Có nên chuyển PAID về PENDING vì B đến sau?

**Gợi ý trả lời:** Không tự động. Cần kiểm tra version/sequence, paymentId và state transition. Message cũ đến muộn không đủ cơ sở để ghi đè trạng thái đã xác nhận; nếu có bằng chứng mâu thuẫn, đối soát nguồn Payment.

### Bài 3: Đã giữ hàng, chưa xác minh thanh toán

Inventory RESERVED cho order-81. Payment timeout. Một job chạy sau 30 giây muốn giải phóng hàng ngay.

**Câu hỏi:** Job cần biết những gì?

**Gợi ý trả lời:** Cần chính sách hạn reservation, kết quả thực của payment, trạng thái saga hiện tại, mối liên hệ payment attempt–order, các cam kết với người dùng và cách xử lý nếu thanh toán thành công đến muộn. Hết timeout kỹ thuật không đủ kết luận thanh toán thất bại.

### Bài 4: Sự cố sau transaction

Order commit dữ liệu và định gửi PaymentRequested qua broker; process crash giữa hai thao tác.

**Câu hỏi:** Làm sao tránh đơn chờ thanh toán mãi vì message bị mất?

**Gợi ý trả lời:** Dùng transactional outbox để lưu state và sự kiện trong một transaction cục bộ; publisher gửi lại khi hồi phục. Consumer vẫn phải xử lý trùng an toàn vì outbox không bảo đảm exactly-once xuyên mọi thành phần.

### Bài 5: Vẽ timeline

Hãy tự vẽ ít nhất bốn dòng thời gian: **Client, Order, Payment, Broker**, đánh dấu lúc request đến, commit, timeout, event được publish và event được consume. Ghi trạng thái từng bên tại mỗi thời điểm; xác định khi nào kết quả chỉ “chưa biết” và khi nào có đủ bằng chứng kết luận.

**Tiêu chí tự kiểm:** Không dùng cùng một thời điểm cho mọi thành phần theo mặc định; không suy ra transaction của dịch vụ này tự rollback transaction của dịch vụ khác.

## 15. Tổng kết và từ vựng trọng tâm

| Thuật ngữ | Ý nghĩa ngắn gọn |
| --- | --- |
| **Local failure** | Một thành phần hoặc thao tác gặp lỗi trong phạm vi của nó. |
| **Partial failure** | Chỉ một phần hệ thống lỗi; các phần khác có thể vẫn hoạt động. |
| **Delayed detection** | Thành phần quan sát phát hiện lỗi sau khi lỗi xảy ra. |
| **Ambiguous outcome / in-doubt** | Caller chưa đủ thông tin xác định thao tác từ xa thành công hay thất bại. |
| **Timeout** | Hết thời hạn chờ phản hồi, không phải chứng nhận side effect chưa xảy ra. |
| **Retry** | Thử lại thao tác khi có cơ sở an toàn; cần giới hạn và kiểm soát tải. |
| **Idempotency** | Lặp cùng thao tác logic mà không tạo side effect nghiệp vụ mới ngoài ý định. |
| **Eventual consistency** | Các bản nhìn có thể lệch tạm thời và hội tụ theo cơ chế hệ thống thiết kế, dưới các giả định phù hợp. |
| **Outbox / Inbox** | Kỹ thuật gắn thay đổi DB với ý định phát message và/hoặc nhận diện message đã xử lý. |
| **Saga / compensation** | Điều phối các transaction cục bộ và thao tác khắc phục khi workflow không đạt mục tiêu. |
| **Reconciliation** | Đối chiếu các trạng thái với nguồn sự thật để kết luận và sửa sai khác. |

**Nguyên tắc thực hành:** Trong Microservices, hãy luôn đặt ba câu hỏi trước khi xử lý một “lỗi”: **(1) Thành phần nào thực sự thất bại? (2) Bên nào chỉ chưa nhận được kết quả? (3) Bằng chứng nào cho phép đưa ra quyết định nghiệp vụ cuối cùng?** Nếu chưa trả lời được câu (3), hãy giữ trạng thái có thể xác minh, bảo vệ side effect bằng idempotency và thiết kế đường phục hồi rõ ràng.
