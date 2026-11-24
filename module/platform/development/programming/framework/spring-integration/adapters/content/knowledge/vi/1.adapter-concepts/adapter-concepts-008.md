# Tiêu chí chọn adapter cho một integration flow

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Lập yêu cầu đầu vào/đầu ra để chọn **inbound adapter**, **outbound adapter**, **gateway** hoặc endpoint khác trong Spring Integration.
- Đánh giá cơ chế **polling** so với **message-driven**, nhịp dữ liệu, độ trễ, khả năng chịu tải và giới hạn của hệ thống kết nối.
- So sánh những lựa chọn thường gặp với **file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu**.
- Xác định hợp đồng **payload/headers**, cách xác nhận, retry, idempotency, transaction, bảo mật và khả năng vận hành trước khi viết mã.
- Phân tích một số tình huống tích hợp thực tế, chọn MessageChannel phù hợp và phác thảo luồng Java DSL.
- Tránh các quyết định chỉ dựa trên tên công nghệ mà bỏ qua ngữ nghĩa giao nhận và vòng đời kết nối.

## 1. Chọn adapter là chọn hợp đồng giao tiếp

Trong Spring Integration, **channel adapter** nối một hệ thống bên ngoài với luồng message nội bộ. **Inbound channel adapter** đưa dữ liệu từ nguồn ngoài vào MessageChannel; **outbound channel adapter** tiêu thụ message trong channel rồi gửi hoặc ghi dữ liệu ra ngoài. **Gateway** thích hợp khi phải trao đổi **request–reply** để phía gọi nhận một kết quả nghiệp vụ.

Không nên bắt đầu thiết kế bằng câu hỏi “nên dùng Kafka hay JMS?” khi chưa biết dữ liệu cần đi theo hướng nào, ai khởi tạo tương tác, phản hồi cần đến khi nào và các thông điệp có được phép trùng hay mất không. Một sơ đồ integration flow hợp lý phải thể hiện cả **đường dữ liệu** và **hợp đồng hoàn tất** của từng bước.

Ví dụ một hệ thống quản lý đơn hàng có ba nhu cầu:

1. Đối tác thả file CSV lên SFTP mỗi giờ; ứng dụng tự kiểm tra và lấy file. Đây là luồng **inbound dạng polling**.
2. Sau khi lưu đơn hàng, ứng dụng gửi event OrderCreated đến Kafka. Đây là luồng **outbound một chiều**.
3. Trong quá trình đặt hàng trực tuyến, ứng dụng gọi API tính cước và phải lấy số tiền trả về trước khi xác nhận. Đây là luồng **outbound request–reply**, thường dùng gateway.

Cùng một dịch vụ có thể dùng cả ba loại endpoint. Chúng thực hiện **những hợp đồng khác nhau**, không phải ba cách viết tương đương cho cùng một giao tiếp.

~~~mermaid
flowchart TD
    R["Yêu cầu tích hợp"] --> D{"Dữ liệu đi theo hướng nào?"}
    D -->|"Bên ngoài → ứng dụng"| IN{"Bên ngoài cần reply nghiệp vụ?"}
    D -->|"Ứng dụng → bên ngoài"| OUT{"Flow cần reply nghiệp vụ?"}
    IN -->|"Không"| IA["Inbound channel adapter"]
    IN -->|"Có"| IG["Inbound gateway"]
    OUT -->|"Không"| OA["Outbound channel adapter"]
    OUT -->|"Có"| OG["Outbound gateway"]
    IA --> V["Tiếp tục xét giao thức, poller/listener,<br/>payload, bảo đảm giao nhận và vận hành"]
    IG --> V
    OA --> V
    OG --> V
~~~

**Hướng inbound/outbound được tính từ góc nhìn ứng dụng Spring Integration.** Một outbound adapter có thể chờ I/O hoặc nhận xác nhận từ broker, nhưng xác nhận giao thức **không tự biến** thao tác một chiều thành một reply nghiệp vụ trong flow.

## 2. Khung quyết định trước khi chọn endpoint

Có thể dùng mười câu hỏi dưới đây trong buổi thiết kế integration flow:

| Nhóm tiêu chí | Câu hỏi cần chốt | Ảnh hưởng tới lựa chọn |
| --- | --- | --- |
| **Hướng truyền** | Ai khởi tạo: hệ thống ngoài hay ứng dụng? | Inbound hoặc outbound |
| **Mẫu tương tác** | Có phải trả một kết quả để bên gọi tiếp tục không? | Channel adapter hoặc gateway |
| **Cách nhận dữ liệu** | Nguồn phải được hỏi theo lịch hay chủ động phát sự kiện? | Polling adapter, listener/consumer, HTTP endpoint |
| **Độ trễ/SLA** | Dữ liệu có thể trễ vài phút hay cần phản hồi trong giây? | Poll interval, gateway timeout, listener concurrency |
| **Lưu lượng** | Số message/giây, kích thước payload, tải đỉnh và backlog? | Batch, prefetch, capacity, streaming, backpressure |
| **Hợp đồng message** | Payload là File, String, bytes, DTO hay record? Header nào cần giữ? | Converter, transformer, header mapper, serializer |
| **Bảo đảm giao nhận** | Được phép nhận lại, gửi lại, trùng, sai thứ tự hoặc mất không? | ACK/offset, idempotency, transaction, state store |
| **Xử lý lỗi** | Timeout, dữ liệu sai và lỗi đích được xử lý như thế nào? | Error flow, retry/backoff, dead-letter, đối soát |
| **Bảo mật** | Xác thực, phân quyền, mã hóa, dữ liệu nhạy cảm và ranh giới tin cậy? | TLS/SSH, secret management, header allowlist |
| **Vòng đời/quan sát** | Khi nào start/stop? Theo dõi lỗi và tiến độ ở đâu? | SmartLifecycle, scheduler, listener container, metrics |

Mười tiêu chí này cần được phân tích **cùng nhau**. Ví dụ, một nguồn phù hợp với polling về mặt giao thức vẫn có thể không đáp ứng độ trễ tối đa 200 ms. Một broker có thể đáp ứng throughput nhưng không giải quyết việc cần **HTTP response đồng bộ** cho người dùng cuối.

## 3. Tiêu chí 1: hướng dữ liệu và người khởi tạo

Hãy xác định hệ thống **chủ động** bắt đầu mỗi lần trao đổi:

| Tình huống | Hướng của message trong ứng dụng | Endpoint phù hợp |
| --- | --- | --- |
| Ứng dụng quét thư mục nhận file từ đối tác | Ngoài → trong | File inbound adapter |
| Ứng dụng đọc dữ liệu mới qua SFTP | Ngoài → trong | SFTP inbound adapter |
| Broker giao message từ JMS queue cho ứng dụng | Ngoài → trong | JMS inbound adapter |
| Ứng dụng publish event lên Kafka | Trong → ngoài | Kafka outbound adapter |
| Ứng dụng ghi file báo cáo lên máy SFTP | Trong → ngoài | SFTP outbound adapter |
| Ứng dụng gọi REST API tính giá và cần dùng giá trị trả về | Trong → ngoài → trong | HTTP outbound gateway |
| HTTP client gọi ứng dụng và cần response của flow | Ngoài → trong → ngoài | HTTP inbound gateway |

Một hướng khác thường bị bỏ sót: **mã Java gọi vào flow**. Nếu muốn một service Java gọi flow qua interface và nhận kết quả, có thể dùng **@MessagingGateway**. Messaging gateway kết nối giao diện phương thức với messaging flow; nó không nhất thiết đồng nghĩa với việc gửi request ra hệ thống ngoài.

## 4. Tiêu chí 2: one-way hay request–reply

Sự khác biệt không chỉ nằm ở việc có một response kỹ thuật. Phải hỏi: **“Phía gọi có cần dữ liệu nghiệp vụ trả về để hoàn tất quyết định hiện tại không?”**

~~~mermaid
flowchart LR
    subgraph ONE["Một chiều"]
        A1["MessageChannel"] --> A2["Outbound adapter"]
        A2 --> A3["File / Broker / DB"]
    end
    subgraph TWO["Request–reply"]
        G1["Request channel"] --> G2["Outbound gateway"]
        G2 --> G3["API / dịch vụ bên ngoài"]
        G3 -->|"Business response"| G2
        G2 --> G4["Reply channel"]
    end
~~~

**Ví dụ one-way:** phát OrderCreated lên Kafka để các hệ thống khác cập nhật trạng thái khi có điều kiện. Producer có thể nhận acknowledgment ở cấp broker, còn consumer chưa chắc đã xử lý ngay.

**Ví dụ request–reply:** cần biết phí vận chuyển từ API đối tác trước khi xác nhận đơn hàng. Flow cần body của HTTP response; outbound HTTP gateway phù hợp hơn outbound adapter một chiều.

**Ví dụ xử lý kéo dài:** API khởi tạo tác vụ tính toán mất nhiều phút. Việc giữ kết nối gateway đồng bộ trong suốt thời gian này có thể không phù hợp. Có thể thiết kế HTTP 202 Accepted kèm job ID, sau đó query trạng thái hoặc nhận callback/sự kiện hoàn tất. Khi đó phải mô tả rõ hợp đồng trạng thái và correlation ID.

## 5. Tiêu chí 3: nguồn polling hay message-driven

Đây là tiêu chí chủ yếu của **inbound endpoint**, đồng thời liên quan đến consumer lấy message từ một PollableChannel phía outbound.

| Cơ chế | Đặc điểm | Nguồn thường gặp |
| --- | --- | --- |
| **Polling inbound** | Ứng dụng chủ động gọi MessageSource theo lịch | File, SFTP, JDBC query |
| **Message-driven inbound** | Listener/consumer nhận dữ liệu theo cơ chế client/giao thức | JMS, AMQP, Kafka |
| **Request-driven** | Hệ thống ngoài gửi yêu cầu đến endpoint đang lắng nghe | HTTP inbound gateway/adapter |
| **Polling consumer nội bộ** | Endpoint chủ động lấy message từ PollableChannel | QueueChannel → outbound adapter |

Với polling, cần lựa chọn **fixed delay/rate**, **maxMessagesPerPoll**, số lần truy vấn rỗng, timeout và trạng thái đã đọc. Poll quá nhanh tăng tải mạng, CPU hoặc database; poll quá chậm làm tăng latency.

Với message-driven, cần xem **consumer concurrency**, **prefetch/batch**, **ACK hoặc offset commit**, khả năng redelivery và quá trình rebalance/khôi phục. Kafka consumer có vòng poll nội bộ theo client của nó, nhưng điều đó **không tương đương** với việc bắt buộc cấu hình Spring Integration Poller trên mọi Kafka inbound adapter.

### 5.1. Khi thay nguồn File/SFTP bằng Kafka

Không chỉ đổi một class adapter. File/SFTP thường có câu hỏi “tệp đã ghi xong chưa?” và “tệp nào đã được lấy?”; Kafka có topic/partition, key, offset, consumer group và cơ chế commit. Cần kiểm tra lại:

- **Payload:** File hoặc InputStream chuyển thành bytes, String hay record tùy deserializer.
- **Metadata:** tên file/đường dẫn chuyển thành topic, partition, offset, key.
- **Tiến độ:** bộ lọc file thay bằng offset/ACK và checkpoint theo giao thức.
- **Thứ tự:** có thể dựa vào thứ tự trong một partition theo key, không mặc nhiên toàn bộ topic.
- **Khôi phục:** xác định ranh giới commit với bước ghi nghiệp vụ.

Business handler sau transformer có thể được tái sử dụng nếu thống nhất được một hợp đồng domain ổn định.

## 6. Tiêu chí 4: độ trễ, tải và mô hình MessageChannel

Lựa chọn adapter ảnh hưởng tới cách dữ liệu vào/ra, còn **MessageChannel** ảnh hưởng tới cách dữ liệu được chuyển giữa các endpoint.

| Channel | Ngữ nghĩa chính | Khi cần lưu ý |
| --- | --- | --- |
| **DirectChannel** | Gọi subscriber đồng bộ trên luồng gửi | Handler I/O chậm có thể giữ poller/listener/caller |
| **ExecutorChannel** | Chuyển xử lý cho executor | Cần giới hạn pool, queue, lỗi async và thứ tự |
| **QueueChannel** | Đệm message để polling consumer nhận | Cần capacity, poller và độ bền khi restart |
| **PublishSubscribeChannel** | Phân phát đến nhiều subscriber | Cần xét lỗi hoặc thành công một phần giữa các nhánh |

Ví dụ tải đến **500 message/giây** nhưng downstream chỉ xử lý được **50 message/giây**. Chuyển sang ExecutorChannel có thể giúp producer không chờ ngay từng lần, nhưng backlog tiếp tục tăng khi chênh lệch tồn tại lâu dài. Giải pháp phải gồm **giới hạn nhịp nhận/gửi, capacity, concurrency hợp lý, chính sách quá tải** hoặc mở rộng năng lực downstream.

Đánh giá thêm **kích thước payload**. Nhận 100.000 file nhỏ khác rất nhiều so với nhận 10 file kích thước vài GB. Với file lớn, mô hình dựa trên file path hoặc streaming có thể phù hợp hơn việc nạp toàn bộ payload vào một String/byte array trong bộ nhớ.

**QueueChannel mặc định không phải hàng đợi bền vững trên đĩa.** Nếu message đang chờ bắt buộc không mất khi tiến trình chết, phải có MessageStore bền vững, broker ngoài hoặc mẫu outbox phù hợp. Chọn adapter tốt không tự giải quyết được yêu cầu lưu bền của channel.

## 7. Tiêu chí 5: bảo đảm giao nhận và khả năng xử lý lại

Đây thường là tiêu chí quyết định cho dữ liệu tài chính, đơn hàng hoặc sự kiện quan trọng. Cần thống nhất ý nghĩa của “thành công”:

~~~text
Nguồn đã phát dữ liệu
        ↓
Adapter nhận được
        ↓
MessageChannel chấp nhận
        ↓
Handler xử lý nghiệp vụ
        ↓
Adapter gửi ra ngoài
        ↓
Đích xác nhận theo giao thức
        ↓
Đích hoàn tất nghiệp vụ (nếu có phản hồi/đối soát)
~~~

Các mốc này không nhất thiết cùng nằm trong một transaction. **ACK của JMS/AMQP, commit offset của Kafka, file được chọn bởi poller, HTTP 2xx hay Kafka producer acknowledgment** đều có phạm vi cụ thể. Không nên dùng một tín hiệu trung gian làm bằng chứng toàn bộ nghiệp vụ đã hoàn tất.

| Yêu cầu | Điều cần thiết kế |
| --- | --- |
| Chấp nhận giao lại ít nhất một lần | Handler idempotent, xử lý bản trùng, retry hợp lý |
| Không mất message khi restart | Nguồn có lưu bền, checkpoint/offset/state store hoặc outbox |
| Giữ thứ tự của cùng đơn hàng | Chọn khóa phân vùng/queue/channel và concurrency phù hợp |
| Không tạo hai bản ghi nghiệp vụ | Khóa unique và idempotency key ổn định ở phía xử lý |
| Nhiều đích phải được cập nhật | Trạng thái theo từng đích, outbox, retry/đối soát hoặc compensation |
| Có transaction | Xác định chính xác tài nguyên nào được transaction bao phủ |

**Không có một outbound adapter nào tự bảo đảm exactly-once end-to-end** cho mọi sự kết hợp HTTP, SFTP, file, broker và database. Nếu nghiệp vụ yêu cầu không tạo tác động trùng, hãy xử lý tại **khóa nghiệp vụ** (ví dụ partnerId + orderId hoặc eventId), cùng quy trình lưu tiến độ và phục hồi.

### 7.1. “Không rõ đã gửi thành công chưa” là một trạng thái thật

Giả sử outbound HTTP adapter/gateway gửi yêu cầu tạo đơn hàng. Server đã ghi dữ liệu nhưng kết nối mất trước khi trả response. Client thấy timeout. Retry ngay mà không có khóa chống trùng có thể tạo đơn hàng thứ hai.

Với Kafka/JMS/AMQP, việc mất kết nối ở thời điểm sát xác nhận cũng gây bài toán tương tự. Vì vậy phải xác định **trạng thái không rõ kết quả** và **cách đối soát**, thay vì chỉ có hai nhãn success/failure.

## 8. Tiêu chí 6: hợp đồng payload, headers và schema

Một Message trong Spring Integration có **payload** và **headers**. Adapter được chọn phải hỗ trợ kiểu payload hoặc có converter/transformer phù hợp trước và sau nó.

| Nguồn/đích | Payload thường gặp | Metadata cần xem xét |
| --- | --- | --- |
| **File** | File, String, bytes tùy chiều và cấu hình | Tên file, đường dẫn, encoding, trạng thái file |
| **SFTP** | File cục bộ, tệp từ xa, InputStream tùy adapter | Remote path, tên file, session, thời điểm ghi |
| **HTTP** | Body String/bytes/DTO | URL, method, status, Content-Type, correlation |
| **JMS** | TextMessage/BytesMessage sau converter | Message ID, correlation ID, destination, properties |
| **AMQP** | Body bytes/DTO sau converter | Exchange, routing key, delivery tag, content type |
| **Kafka** | Value/record sau deserializer | Topic, partition, offset, key, timestamp |
| **Database/JDBC** | Giá trị hàng, map hoặc đối tượng tùy cấu hình | Cột, khóa, watermark, transaction |

Không nên giả định hai adapter phát ra payload/headers giống nhau chỉ vì chúng cùng xử lý một loại dữ liệu nghiệp vụ. Ví dụ File inbound thường phát **File**, còn một Kafka inbound adapter có thể phát **String JSON** tùy deserializer. Có thể đặt transformer ngay sau biên inbound để chuẩn hóa hai nguồn thành **OrderEvent** trước khi vào business flow.

### 8.1. Header mapper và dữ liệu vượt ranh giới

**replyChannel**, **errorChannel** và các header chứa đối tượng hạ tầng nội bộ không nên được serialize thẳng ra hệ thống ngoài. Header mapper của JMS/AMQP/HTTP/Kafka có phạm vi và quy tắc riêng.

Nên định nghĩa:

- Trường nào là **eventId** và **schemaVersion** ổn định.
- Trường nào phục vụ correlation/tracing và trường nào là khóa idempotency.
- Charset, Content-Type, serializer, schema và phiên bản tương thích.
- Header nào **được phép** chuyển sang bên ngoài; dữ liệu nhạy cảm nào cần loại bỏ.
- Cách xử lý JSON/CSV không hợp lệ, trường bắt buộc bị thiếu hoặc thay đổi schema.

Đối với file CSV, parser cần xử lý dấu phẩy, dấu nháy và xuống dòng đúng chuẩn; việc split chuỗi theo dấu phẩy chỉ phù hợp ví dụ rất đơn giản. Với dữ liệu lớn, phải hạn chế kích thước và xử lý theo stream/batch khi cần.

## 9. Tiêu chí 7: lỗi, timeout và retry

Không nên chọn adapter chỉ vì hoạt động trong tình huống thành công. Các trường hợp cần kiểm tra gồm:

1. **Không kết nối được nguồn/đích:** DNS, mạng, SFTP session hết hạn, broker ngắt, DB pool cạn.
2. **Dữ liệu sai hợp đồng:** JSON/CSV lỗi, payload sai kiểu, header thiếu, serializer không tương thích.
3. **Nguồn/đích quá tải:** queue sâu, rate limit, timeout, số kết nối vượt ngưỡng.
4. **Xử lý nghiệp vụ lỗi:** database constraint, hết tồn kho, duplicate business key.
5. **Kết quả không rõ:** request đã đi nhưng ACK/reply bị mất.

~~~mermaid
flowchart TD
    A["Nhận hoặc gửi message"] --> V{"Lỗi thuộc loại nào?"}
    V -->|"Sai dữ liệu/schema"| BAD["Cách ly message, sửa dữ liệu hoặc hợp đồng"]
    V -->|"Tạm thời: mạng/quá tải"| RET["Retry có giới hạn + backoff"]
    V -->|"Trạng thái đích không rõ"| REC["Đối soát + idempotency"]
    V -->|"Lỗi vĩnh viễn/quyền truy cập"| FIX["Cảnh báo, xử lý cấu hình/quyền"]
    RET --> A
~~~

**Retry** là thử lại; **idempotency** là làm cho bản gửi/nhận lại không tạo tác động nghiệp vụ trùng. Không thể thay thế idempotency chỉ bằng cách tăng số lần retry hoặc giảm timeout.

Với **DirectChannel**, exception downstream có thể truyền ngược trên cùng chuỗi gọi. Với **ExecutorChannel/QueueChannel**, lỗi có thể phát sinh sau khi producer đã được trả về, nên cần đường xử lý **ErrorMessage/errorChannel**, listener error handler, advice hoặc callback phù hợp. Cơ chế lỗi phải được kiểm chứng theo endpoint cụ thể.

## 10. Tiêu chí 8: bảo mật, môi trường và vòng đời kết nối

Mỗi giao thức có yêu cầu vận hành khác nhau:

| Giao thức | Tài nguyên và bảo mật cần xét |
| --- | --- |
| File | Quyền thư mục, đường dẫn an toàn, tên file, hạn mức dung lượng |
| SFTP | SSH host key verification, key/credential, session pooling, timeout/reconnect |
| HTTP | TLS, auth token, timeout, proxy, rate limit, hợp đồng mã phản hồi |
| JMS/AMQP | Broker credentials, TLS, connection factory, listener container, topology |
| Kafka | Bootstrap brokers, TLS/SASL, ACL, consumer group, serializer |
| Database | JDBC URL, pool, tài khoản giới hạn quyền, transaction isolation |

Trong ứng dụng Spring Integration, nhiều endpoint triển khai **Lifecycle/SmartLifecycle** để start/stop. Inbound polling adapter cần scheduler; JMS/AMQP/Kafka inbound thường phụ thuộc listener container hoặc consumer; outbound endpoint phụ thuộc connection/session/client. **isRunning() == true** không chứng minh máy chủ ngoài đang khả dụng hoặc mọi message đã xử lý thành công.

Khi khởi động hệ thống có nhiều bước, thường nên **chuẩn bị downstream trước khi bật inbound**; khi dừng, **ngừng nguồn nhận thêm trước khi dừng phần xử lý**. Hãy xem xét thứ tự phase, active tasks, backlog, reply đang chờ và tài nguyên chia sẻ. **stop() không mặc nhiên đợi tất cả message hoàn tất** hoặc khôi phục tiến độ sau crash.

## 11. Ma trận lựa chọn theo hệ thống

Bảng sau là điểm khởi đầu để **thu hẹp lựa chọn**, không phải bảng xếp hạng công nghệ:

| Công nghệ | Bài toán phù hợp | Cơ chế inbound phổ biến | Điểm cần kiểm tra trước khi chọn |
| --- | --- | --- | --- |
| **File cục bộ** | Import/export batch, trao đổi đơn giản | Polling directory | File ghi xong chưa, quyền truy cập, naming, restart |
| **SFTP** | Trao đổi file giữa tổ chức qua mạng | Polling/đồng bộ file | SSH, session, remote directory, atomic publish |
| **HTTP** | API trực tuyến, request–reply hoặc gửi webhook | Request-driven | SLA, status/body, auth, timeout, idempotency |
| **JMS** | Tích hợp queue/topic trong hệ sinh thái JMS | Message-driven listener | Destination, transaction/ACK, redelivery, converter |
| **AMQP** | Queue, routing theo exchange/binding | Message-driven listener | Exchange/routing key, prefetch, ACK/NACK, DLQ |
| **Kafka** | Event stream, lưu và đọc lại log theo partition | Consumer/listener | Topic/key/partition, offset, group, retention, ordering |
| **JDBC/database** | Đồng bộ trạng thái từ bảng hoặc ghi dữ liệu | Polling query hoặc outbound update | Watermark, transaction, khóa duy nhất, tải truy vấn |

Không nên suy ra “Kafka luôn tốt hơn JMS” hay “SFTP luôn chậm hơn HTTP”. Khả năng đáp ứng phụ thuộc workload, cách triển khai, yêu cầu hợp đồng, hạ tầng đang có và năng lực vận hành của đội ngũ.

### 11.1. Phân biệt queue và event log

JMS/AMQP thường được sử dụng để truyền công việc qua queue với cơ chế acknowledgment/redelivery phù hợp. Kafka thường được dùng khi có luồng sự kiện lưu theo topic/partition, cần nhiều consumer group hoặc khả năng đọc lại dữ liệu theo retention. Tuy vậy, mỗi nền tảng đều có nhiều mode cấu hình; hãy so sánh bằng **yêu cầu giao nhận thực tế** thay vì nhãn “message queue” hoặc “stream”.

### 11.2. Khi nào database polling là phương án hợp lý?

Nếu hệ thống nguồn chỉ cho phép đọc bảng, JDBC polling có thể là lựa chọn thực dụng. Cần truy vấn theo **watermark/khóa tăng dần hoặc trạng thái xử lý**, có index và giới hạn batch phù hợp; nếu watermark cập nhật sai thời điểm, một số bản ghi có thể bị bỏ sót hoặc đọc lặp.

Nếu hệ thống nghiệp vụ có quyền thay đổi schema/ứng dụng nguồn và cần phát sự kiện tin cậy sau khi commit dữ liệu, **outbox** là một mẫu cần xem xét. Nó giải quyết phần phối hợp lưu trạng thái và phát event tốt hơn việc đoán thay đổi chỉ bằng mốc thời gian.

## 12. Tình huống A: nhập đơn hàng theo lô từ SFTP

**Yêu cầu giả định:** Đối tác đặt file CSV lên SFTP theo giờ; mỗi file chứa nhiều đơn hàng. Cho phép nhận trễ vài phút. Đơn hàng không được tạo hai lần khi gửi lại file hoặc restart ứng dụng.

**Lựa chọn:** SFTP inbound adapter theo lịch, sau đó MessageChannel, transformer parse CSV, service activator kiểm tra và lưu đơn hàng. Nếu cần xuất biên nhận, dùng outbound adapter file/SFTP riêng.

~~~mermaid
flowchart LR
    S["SFTP server"] --> IA["SFTP inbound adapter<br/>poller"]
    IA --> CH["rawFiles"]
    CH --> T["CSV parser + validation"]
    T --> O["OrderService<br/>idempotency + transaction"]
    O --> OUT["Receipt message"]
    OUT --> OA["SFTP outbound adapter"]
    OA --> D["SFTP receipts"]
~~~

**Các quyết định bắt buộc:**

- Đồng bộ file từ xa về local hay xử lý stream, tùy kích thước và cách triển khai.
- Quy tắc đối tác công bố **file hoàn tất**; tránh đọc file đang upload.
- Bộ lọc/metadata store để giảm nhận lại sau restart.
- Chống trùng theo **partnerId + orderId**, không chỉ dựa vào tên file.
- Phân biệt lỗi CSV (thường cần cách ly) với lỗi mạng SFTP (có thể retry).
- Chính sách ghi receipt, đặt tên file, tránh overwrite và xử lý khi chỉ một phần đơn hàng thành công.

SFTP phù hợp với hợp đồng trao đổi file đã được đối tác thống nhất. Không cần chọn Kafka chỉ vì ứng dụng nội bộ sử dụng messaging: việc chuyển giao thức phải được hai bên hỗ trợ và giải quyết một yêu cầu có thật.

## 13. Tình huống B: đặt hàng trực tuyến qua HTTP

**Yêu cầu giả định:** Client gửi POST /orders và cần mã đơn hàng hoặc thông báo từ chối trong cùng request. Luồng kiểm tra tồn kho, tính giá từ một API ngoài rồi tạo đơn.

**Lựa chọn:** HTTP **inbound gateway** để nhận request và trả response; HTTP **outbound gateway** nếu flow cần response body từ dịch vụ tính giá. Các bước business dùng transformer/service activator và channel phù hợp với SLA.

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant I as Inbound HTTP gateway
    participant F as IntegrationFlow
    participant O as Outbound HTTP gateway
    participant P as API tính giá
    C->>I: POST /orders
    I->>F: Message<OrderRequest>
    F->>O: PriceRequest
    O->>P: HTTP request
    P-->>O: PriceResponse
    O-->>F: Message<PriceResponse>
    F-->>I: OrderResult
    I-->>C: HTTP response
~~~

**Các quyết định bắt buộc:**

- Request/response schema, Content-Type, HTTP status và mã lỗi nghiệp vụ.
- Timeout của client, gateway, HTTP client đến API ngoài và chính sách retry.
- Idempotency key nếu client có thể gửi lại POST sau timeout.
- Cách trả kết quả khi xử lý chậm: response đồng bộ hoặc 202 Accepted với job ID.
- Xác thực, authorization, rate limit, không lộ dữ liệu nhạy cảm trong headers/log.

Một inbound HTTP adapter một chiều không tự cung cấp hợp đồng trả kết quả nghiệp vụ như inbound gateway. Nếu không cần reply trong cùng request, có thể thiết kế cơ chế tiếp nhận bất đồng bộ với response theo trạng thái riêng.

## 14. Tình huống C: phát sự kiện đơn hàng đến nhiều hệ thống

**Yêu cầu giả định:** Sau khi transaction tạo đơn hàng thành công, các hệ thống phân tích, chăm sóc khách hàng và kho cần biết event OrderCreated. Đích có thể không hoạt động trong một khoảng thời gian; cần xử lý lại an toàn.

**Lựa chọn khả thi:** Lưu event vào **transactional outbox** cùng transaction nghiệp vụ, worker phát qua **Kafka outbound adapter** nếu hệ sinh thái yêu cầu event stream, retention, nhiều consumer group. Nếu hạ tầng hiện tại dựa trên JMS/AMQP và bài toán chủ yếu là phân phối công việc theo queue, adapter tương ứng cũng có thể phù hợp.

~~~text
OrderService
  -> Database transaction: Order + OutboxEvent
  -> Outbox polling/worker
  -> MessageChannel<OrderCreated>
  -> Kafka/JMS/AMQP outbound adapter
  -> Broker
  -> Consumer theo hệ thống đích
~~~

**Các quyết định bắt buộc:**

- Event ID và schemaVersion ổn định; chính sách tương thích dữ liệu.
- Topic/key/partition đối với Kafka hoặc destination/routing đối với JMS/AMQP.
- Điểm ghi nhận outbox đã gửi và xử lý trạng thái chưa rõ ACK.
- Idempotent consumer vì event có thể được giao lại.
- Retention, dead-letter/retry và quy trình đối soát khi consumer chậm.

Một broker đã nhận message không đồng nghĩa hệ thống kho hoặc CRM đã cập nhật thành công. Nếu cần kết quả từ một đích để tiếp tục xử lý yêu cầu đang chạy, phải thiết kế reply/correlation hoặc một workflow bất đồng bộ có trạng thái.

## 15. Ví dụ Java DSL: lựa chọn file inbound polling cho batch

Yêu cầu giả định: đối tác cung cấp file CSV ở **thư mục cục bộ** (mô phỏng nguồn file, có thể mở rộng thành SFTP). Độ trễ vài giây chấp nhận được, nên dùng file inbound polling adapter. Flow tạo **Message<File>** rồi chuyển thành String UTF-8 và xử lý đơn giản. Mục đích là cho thấy các tiêu chí lựa chọn trở thành cấu hình endpoint như thế nào.

Với Spring Boot, sử dụng starter Spring Integration và module **spring-integration-file** tương thích với BOM của Spring Boot.

~~~java
import java.io.File;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class BatchFileFlowConfiguration {

    @Bean
    public MessageChannel rawFiles() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow fileIngressFlow() {
        return IntegrationFlow
            .from(
                Files.inboundAdapter(new File("./data/inbox"))
                    .autoCreateDirectory(true)
                    .patternFilter("*.csv"),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofSeconds(5))
                        .maxMessagesPerPoll(10)))
            .channel("rawFiles")
            .get();
    }

    @Bean
    public IntegrationFlow inspectCsvFlow() {
        return IntegrationFlow.from("rawFiles")
            .transform(File.class, source -> {
                try {
                    return java.nio.file.Files.readString(
                        source.toPath(), StandardCharsets.UTF_8);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            })
            .handle(String.class, (content, headers) -> {
                System.out.println(
                    "Nhan CSV, so ky tu: " + content.length());
                return null; // Flow minh hoa ket thuc tai day.
            })
            .get();
    }
}
~~~

### 15.1. Quyết định nào được mã hóa trong ví dụ?

| Tiêu chí | Cấu hình hoặc hành vi |
| --- | --- |
| Hướng inbound | Files.inboundAdapter tạo message từ file bên ngoài |
| Polling | Pollers.fixedDelay đặt chu kỳ 5 giây |
| Batch | maxMessagesPerPoll(10) giới hạn số message mỗi lượt |
| Bộ lọc nguồn | patternFilter("*.csv") chỉ chọn tên tệp phù hợp |
| Channel | rawFiles là DirectChannel, consumer xử lý đồng bộ |
| Hợp đồng payload | Message<File> → transformer đọc String UTF-8 |
| Xử lý cuối | Handler minh họa chỉ ghi log; chưa ghi database |

### 15.2. Cách thử

1. Khởi động ứng dụng có cấu hình trên.
2. Đặt một file **orders-001.csv** có vài dòng vào **./data/inbox**.
3. Quan sát handler in số ký tự sau lượt poll.
4. Đặt file **readme.txt**: nó không được chọn bởi patternFilter.
5. Thử file CSV có nội dung sai hoặc tệp lớn để nhận thấy ví dụ chưa có parser/streaming, rồi xác định bước mở rộng theo yêu cầu thực tế.

**Giới hạn chủ đích:** Ví dụ chưa parse CSV, chưa có database transaction, chưa bảo đảm file đã được ghi hoàn tất, chưa có durable filter và idempotency qua restart. Trước khi dùng production, cần bổ sung kiểm tra file sẵn sàng, nguồn file bền vững, cơ chế chống trùng nghiệp vụ, phân luồng lỗi và quan sát. Đây chính là những tiêu chí thiết kế khiến một bản demo không tự trở thành một giải pháp tích hợp hoàn chỉnh.

## 16. Từ bản thiết kế tới tiêu chí nghiệm thu

Chọn được adapter chưa đủ; nên mô tả kết quả có thể kiểm chứng trước khi triển khai:

| Yêu cầu | Cách kiểm chứng |
| --- | --- |
| Đúng hướng và giao thức | Inbound nhận được dữ liệu; outbound ghi/gửi đúng đích |
| Đúng hợp đồng | Payload/headers/schema/encoding phù hợp với consumer |
| Độ trễ đáp ứng | Đo thời gian nhận, xử lý và phản hồi trên tải thực tế |
| Không bỏ sót sau restart | Dừng đột ngột, khởi động lại, kiểm tra checkpoint/backlog |
| Không tạo tác động nghiệp vụ trùng | Phát lại cùng eventId/orderId và kiểm tra trạng thái đích |
| Lỗi có thể phục hồi | Mô phỏng timeout, lỗi broker, thiếu quyền, quá tải và quan sát retry |
| Lỗi dữ liệu được cách ly | Đưa payload sai schema và kiểm tra error flow |
| Dừng/bật an toàn | Stop inbound, chờ xử lý, resume, kiểm tra message đang chạy |
| Dữ liệu không rò rỉ | Kiểm tra log, headers chuyển ra ngoài, secret/credential |
| Đủ tín hiệu vận hành | Metrics nhận/gửi, backlog, lỗi, retry, ACK, latency và business outcome |

### 16.1. Một bản ghi quyết định ngắn

Trước khi triển khai, có thể ghi rõ những điều sau trong tài liệu thiết kế:

~~~text
Luồng: PartnerOrderImport
Nguồn/đích: SFTP partner -> OrderService -> database
Hướng: inbound polling
Endpoint: SFTP inbound adapter + poller
Đầu vào: CSV UTF-8, schema v1, file hoàn tất qua rename
Thông lượng: batch theo giờ; độ trễ chấp nhận < 5 phút
Channel: DirectChannel ở bước parse/validate; giới hạn tải theo năng lực DB
Tiến độ: metadata store bền vững + khóa partnerId/orderId
Thành công: transaction nghiệp vụ commit; receipt xử lý riêng
Lỗi: sai CSV -> cách ly; lỗi mạng -> retry/backoff; DB lỗi -> phục hồi
Vận hành: quản lý secret SFTP, endpoint lifecycle, metric backlog/error
~~~

Thông số trong ví dụ là **giả định thiết kế**, cần thay bằng yêu cầu và phép đo của hệ thống thực tế.

## 17. Sai lầm thường gặp khi chọn adapter

**Chọn theo tên công nghệ trước khi xác định kiểu giao tiếp.** Một HTTP flow cần phản hồi không thể được đánh giá giống luồng publish Kafka một chiều.

**Nhầm acknowledgment với kết quả nghiệp vụ.** JMS/AMQP ACK, Kafka producer acknowledgment hoặc HTTP 202 có phạm vi riêng; phải xác định mốc hoàn tất mà nghiệp vụ cần.

**Cho rằng polling là lựa chọn kém trong mọi trường hợp.** Polling có thể hợp lý khi nguồn chỉ có API đọc theo lịch hoặc bên đối tác bàn giao batch. Cần đánh giá SLA và tải thay vì mặc định thay bằng event-driven.

**Dùng QueueChannel và tin rằng tự động chống mất message.** Queue mặc định trong bộ nhớ không bảo đảm khôi phục khi crash.

**Bỏ qua kiểu payload khi thay adapter.** File có thể phát File, Kafka phát String/record; transformer và header mapping phải được kiểm tra lại.

**Tăng concurrency trước khi đo downstream.** Nhiều worker có thể chỉ đẩy nhanh việc tích lũy backlog hoặc gây quá tải cho hệ thống đích.

**Retry vô hạn cho dữ liệu sai.** Parser lỗi do schema sẽ không tự hồi phục nhờ retry; phải phân loại lỗi tạm thời và lỗi cần sửa dữ liệu.

**Dùng correlation ID làm khóa chống trùng duy nhất.** Correlation phục vụ truy vết/request–reply; idempotency cần khóa nghiệp vụ ổn định và cơ chế kiểm tra tại nơi sinh side effect.

**Chỉ đo isRunning của endpoint.** Endpoint có thể chạy nhưng không kết nối được, poll lỗi liên tục hoặc backlog tăng. Cần quan sát toàn tuyến.

## 18. Câu hỏi tự kiểm tra

1. Một đối tác gửi file CSV mỗi đêm và chấp nhận độ trễ vài phút. Bạn sẽ chọn hướng/cơ chế inbound nào? Những điều kiện nào phải kiểm tra trước khi đưa vào production?
2. Nếu một API cần trả về phí giao hàng để flow tính tổng tiền, tại sao outbound gateway phù hợp hơn outbound adapter?
3. Kafka consumer có vòng poll nội bộ. Điều này có nghĩa mọi Kafka inbound adapter phải dùng Spring Integration poller không?
4. Vì sao tăng maxMessagesPerPoll khi downstream đã quá tải có thể làm tình hình xấu hơn?
5. Khi đổi từ file sang Kafka, những khía cạnh của payload, metadata, ACK/offset và thứ tự cần đánh giá lại?
6. Một POST tạo đơn hàng bị timeout, nhưng phía đích có thể đã ghi thành công. Cần cơ chế gì trước khi retry?
7. Khi nào QueueChannel cần lưu trữ bền vững hoặc thay bằng broker/outbox?
8. Tại sao chọn JDBC polling chỉ dựa trên thời gian cập nhật cuối có thể gây bỏ sót hoặc trùng dữ liệu?
9. Nếu phát một event sang hai hệ thống và chỉ một đích thành công, cần ghi trạng thái như thế nào để phục hồi?
10. Ngoài isRunning, những chỉ số nào cho biết một adapter và cả integration flow đang vận hành khỏe?

## Tổng kết

**Chọn adapter cho integration flow** là quyết định về **hợp đồng giao tiếp, ngữ nghĩa giao nhận và vận hành**. Hãy bắt đầu từ **hướng dữ liệu**, **one-way hay request–reply**, **polling hay listener**, sau đó kiểm tra tải, MessageChannel, payload/headers, ACK/offset, retry, idempotency, giao dịch, bảo mật và lifecycle. File, SFTP, HTTP, JMS, AMQP, Kafka và database đều có vị trí khi giải quyết đúng nhu cầu. Một lựa chọn tốt phải được thể hiện bằng cấu hình có thể kiểm chứng và kịch bản phục hồi sau lỗi, thay vì chỉ bằng tên adapter được sử dụng.
