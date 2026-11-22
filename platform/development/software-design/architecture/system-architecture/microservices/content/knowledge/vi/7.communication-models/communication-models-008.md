# Tránh suy ra rằng mọi tương tác đều cần broker hoặc REST

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Mô hình giao tiếp

## 1. Vấn đề: biến công nghệ giao tiếp thành quy tắc kiến trúc

Khi tìm hiểu microservices, người học thường gặp hai mô hình nổi bật:

- **REST/HTTP:** Service A gọi endpoint của Service B để yêu cầu dữ liệu hoặc thao tác.
- **Message broker:** Service A gửi message lên một hạ tầng trung gian; Service B nhận và xử lý sau.

Đây là hai lựa chọn quan trọng nhưng không đại diện cho mọi nhu cầu giao tiếp. Câu hỏi đúng không phải “nên dùng REST hay Kafka/RabbitMQ cho tất cả tương tác?”, mà là:

> **Tác vụ này cần kết quả gì, vào thời điểm nào, bên nào sở hữu trách nhiệm, mức độ nhất quán và tin cậy cần đến đâu, và có thật sự cần đi qua ranh giới mạng không?**

Một hệ thống có thể đồng thời dùng lời gọi hàm trong cùng module, HTTP/REST cho truy vấn hay lệnh nghiệp vụ, gRPC cho một số kết nối service-to-service, event để phát thông tin trạng thái đã thay đổi, queue cho công việc nền, WebSocket hoặc Server-Sent Events cho cập nhật liên tục, file/object storage cho dữ liệu lớn và batch job cho đồng bộ định kỳ.

Chọn công nghệ trước khi xác định yêu cầu dễ tạo ra hai cực đoan:

1. **REST cho mọi thứ:** mỗi hành vi bị chia thành nhiều HTTP call đồng bộ; luồng nghiệp vụ dài, dễ timeout và phải chờ nhiều service.
2. **Broker cho mọi thứ:** ngay cả câu hỏi cần đáp án tức thời cũng bị biến thành trao đổi message có correlation ID, trạng thái chờ và timeout, làm thiết kế phức tạp mà chưa chắc có lợi.

**Thông điệp chính:** Cơ chế giao tiếp là công cụ để bảo toàn hợp đồng nghiệp vụ, ranh giới sở hữu và yêu cầu vận hành. REST hay broker không phải mục tiêu tự thân.

## 2. Phân tách bốn câu hỏi thường bị trộn lẫn

Để chọn mô hình, trước hết hãy tách riêng những khái niệm sau.

### 2.1. Có cần giao tiếp qua mạng không?

Hai thành phần nằm trong **cùng tiến trình** có thể gọi nhau qua interface hoặc hàm nội bộ. Nếu chúng thuộc cùng một đơn vị triển khai, cùng vòng đời thay đổi và không có nhu cầu tách ở thời điểm hiện tại, thêm HTTP hoặc message broker chỉ để “trông giống microservices” thường tạo độ phức tạp không cần thiết.

Ngược lại, khi hai năng lực thật sự nằm ở các service độc lập, cần hợp đồng qua ranh giới tiến trình. Khi đó mới lựa chọn giao thức và cách trao đổi phù hợp.

### 2.2. Caller có cần kết quả ngay không?

- **Request–response:** caller cần câu trả lời trước khi tiếp tục hành trình hiện tại, ví dụ cần xác nhận một báo giá trước khi người dùng chấp nhận.
- **Fire-and-forget có kiểm soát:** caller chỉ cần ghi nhận yêu cầu để xử lý sau; phải làm rõ khi nào mới coi là đã tiếp nhận an toàn.
- **Asynchronous request–reply:** caller gửi yêu cầu, tiếp tục công việc khác và nhận kết quả sau qua callback, polling hoặc message.
- **Event notification:** một thành phần thông báo sự kiện đã xảy ra; bên phát không ra lệnh cụ thể cho từng consumer phải làm gì.

Đây là **kiểu tương tác**, chưa phải quyết định sử dụng REST hay broker.

### 2.3. Thông tin đang trao đổi là lệnh, truy vấn hay sự kiện?

| Loại | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Query | Yêu cầu thông tin hiện có; về nguyên tắc không tạo tác dụng phụ nghiệp vụ | “Trạng thái đơn hàng hiện là gì?” |
| Command | Yêu cầu một bên thực hiện hành động thuộc trách nhiệm của họ | “Hãy giữ 3 sản phẩm cho đơn X” |
| Event | Thông báo một sự thật đã xảy ra trong domain | “Đơn X đã được xác nhận” |

Một command có thể đi qua HTTP hoặc queue. Một event có thể đi qua broker, webhook hoặc cơ chế streaming khác. **Không nên đồng nhất “REST là command” và “broker là event”.** Nhiều API REST là query; nhiều queue mang command, không phải event.

### 2.4. Mức độ đồng bộ và mức độ bền vững có phải một?

**Đồng bộ (synchronous)** thường chỉ việc caller chờ kết quả trong cùng luồng xử lý. **Bất đồng bộ (asynchronous)** là caller không cần giữ luồng đó để chờ hoàn tất. Còn **độ bền (durability)** mô tả liệu yêu cầu/message có được lưu để xử lý sau sự cố hay không.

HTTP có thể dùng để gửi yêu cầu tạo job và trả về 202 Accepted cùng job ID, rồi client polling trạng thái: đó là giao diện HTTP với quy trình bất đồng bộ. Ngược lại, một client có thể gửi message qua broker nhưng chờ một reply message trước khi tiếp tục: mô hình request–reply qua broker vẫn tạo phụ thuộc thời gian.

Không được suy ra rằng “có broker = không còn coupling”, “HTTP = luôn đồng bộ”, hay “async = bảo đảm đã xử lý thành công”.

## 3. Bản đồ các lựa chọn giao tiếp

| Cách giao tiếp | Khi thường phù hợp | Điều cần tính đến |
| --- | --- | --- |
| Gọi hàm/interface trong cùng tiến trình | Các module cùng ứng dụng, cùng vòng đời triển khai | Coupling mã nguồn; cần ranh giới module rõ |
| HTTP/REST | Truy vấn tài nguyên, API công khai, thao tác cần kết quả hoặc HTTP ecosystem thuận tiện | Timeout, versioning, retry, authorization, payload |
| HTTP theo tác vụ bất đồng bộ | Gửi job rồi theo dõi trạng thái; không cần giữ request mở | Job ID, persistence, trạng thái và cơ chế polling/callback |
| gRPC | Hợp đồng RPC rõ, hiệu năng và typed interface phù hợp trong nội bộ | Protobuf schema, compatibilities, tooling, quan sát và timeout |
| Message queue / broker | Công việc nền, giảm phụ thuộc thời gian, phân phối tải, xử lý lại | Delivery semantics, retry, duplicate, ordering, dead-letter, vận hành broker |
| Pub/sub event | Một thay đổi domain cần nhiều consumer phản ứng độc lập | Event schema, sở hữu event, eventual consistency, replay |
| Webhook | Thông báo sang hệ thống bên ngoài qua HTTP callback | Xác thực nguồn gửi, idempotency, retry, endpoint có thể offline |
| SSE / WebSocket | Cần đẩy cập nhật đến client theo thời gian gần thực | Kết nối dài, reconnect, auth, fan-out, backpressure |
| Streaming protocol | Dữ liệu liên tục hoặc khối lượng lớn theo luồng | Kiểm soát tốc độ, thứ tự, checkpoint, xử lý trùng |
| Shared file / object storage + tham chiếu | Payload lớn, ảnh, báo cáo, batch import/export | Quyền truy cập, checksum, thời hạn sống, cleanup |
| Batch / scheduled sync | Chấp nhận trễ theo chu kỳ, số lượng lớn | Cửa sổ dữ liệu cũ, đối soát, lịch chạy và khả năng chạy lại |

Bảng này là điểm xuất phát để suy luận, không phải bảng quy định cứng. Một hệ thống có thể kết hợp nhiều lựa chọn cho các luồng khác nhau. Ví dụ cùng một năng lực Payment có HTTP endpoint nhận lệnh thanh toán, event sau khi giao dịch được xác nhận, và batch đối soát cuối ngày.

## 4. REST là một lựa chọn hợp lý khi caller cần câu trả lời

REST đặt trọng tâm vào tài nguyên, trạng thái và ngữ nghĩa HTTP. Các API thường dùng GET để đọc, POST để tạo hoặc thực hiện thao tác, PUT/PATCH để cập nhật, DELETE để xóa, cùng HTTP status code để diễn tả kết quả.

Ví dụ:

    Client
      |
      | GET /products/123
      v
    Catalog
      |
      | 200 OK + product representation
      v
    Client

Khi client đang hiển thị trang và cần thông tin sản phẩm ngay, request–response là tự nhiên. Không nhất thiết đặt một message broker ở giữa rồi xây request-reply chỉ để trả cùng dữ liệu.

REST/HTTP có lợi vì hệ sinh thái rộng, proxy, gateway, cache, observability, authentication và công cụ kiểm thử thuận tiện. Nhưng REST không tự giải quyết các bài toán về data ownership, độ tin cậy hoặc transaction.

### 4.1. Những câu hỏi phải đặt khi dùng REST

- Caller có cần kết quả trước khi phản hồi người dùng không?
- Có timeout và deadline tổng cho hành trình chưa?
- Request có tác dụng phụ không? Nếu retry sau timeout có nguy cơ thực thi lặp không?
- Lỗi service đích có bắt buộc làm toàn bộ thao tác thất bại không?
- Contract có thể phát triển tương thích khi hai service chạy phiên bản khác nhau không?
- Request này có tạo N+1 calls hoặc vòng phụ thuộc A→B→A không?

**Ví dụ cần đặc biệt cẩn thận:** Ordering gửi POST tạo thanh toán. Payment xử lý thành công nhưng phản hồi bị mất; Ordering timeout. Việc gọi lại mà không có idempotency key hoặc truy vấn trạng thái có thể tạo giao dịch trùng. Chọn REST hay broker không thay thế thiết kế idempotency và đối soát.

### 4.2. HTTP vẫn có thể bắt đầu tác vụ nền

Giả sử client yêu cầu xuất báo cáo mất vài phút:

    POST /reports/exports
    → 202 Accepted
    → { "jobId": "job-42", "statusUrl": "/reports/exports/job-42" }

Client tiếp tục công việc và đọc trạng thái theo job ID hoặc nhận thông báo hoàn tất sau đó. Job có thể được đẩy vào worker queue ở bên trong service, nhưng **API phía client vẫn là HTTP**. Không nên giữ kết nối HTTP suốt thời gian xử lý nếu nghiệp vụ không cần.

## 5. Broker phù hợp khi cần tách thời điểm xử lý hoặc phân phối thông điệp

Message broker là hệ thống trung gian nhận, lưu/định tuyến và chuyển message theo cơ chế cụ thể. Tùy công nghệ, broker có thể hỗ trợ queue, pub/sub, retention, consumer group, acknowledgement, replay hoặc các đặc tính khác.

Một ví dụ: sau khi Ordering xác nhận đơn, các năng lực Notification, Analytics và Loyalty có thể phản ứng ở nhịp riêng.

    Ordering
       |
       | OrderConfirmed event
       v
    Event broker
       |------> Notification consumer
       |------> Analytics consumer
       '------> Loyalty consumer

Lúc này Ordering chỉ phát biểu “đơn đã được xác nhận” sau khi trạng thái nghiệp vụ tương ứng được ghi nhận. Nó không cần chờ mỗi consumer hoàn thành email, cập nhật thống kê hoặc tích điểm trước khi phản hồi bước đặt hàng, **nếu quy tắc nghiệp vụ cho phép**.

### 5.1. Broker không tự bảo đảm nghiệp vụ chính xác

Các câu hỏi bắt buộc gồm:

- **Delivery guarantee:** broker và ứng dụng cam kết mức nào, ví dụ at-most-once hoặc at-least-once, trong những điều kiện nào?
- **Duplicate:** consumer có thể nhận lại message do retry, rebalance hoặc lỗi sau khi xử lý nhưng trước khi ack không?
- **Ordering:** thứ tự được giữ theo key/partition/queue nào; có cần thứ tự toàn cục không?
- **Failure:** message lỗi được retry ra sao, có dead-letter queue và quy trình xử lý sự cố không?
- **Schema evolution:** consumer cũ đọc được event mới không?
- **Retention/replay:** message tồn tại bao lâu; khi phát lại có gây side effect trùng không?
- **Observability:** có theo dõi backlog, lag, retry, poison message và thời điểm nghiệp vụ hội tụ không?

Cụm từ “exactly once” của một số công nghệ thường có **phạm vi bảo đảm cụ thể**, chẳng hạn trong một pipeline xử lý hoặc ghi vào hệ thống nhất định. Không được tự suy ra “mỗi email, lần thu tiền hoặc tác động ở hệ thống ngoài được thực hiện đúng một lần” chỉ nhờ cấu hình broker. Consumer vẫn cần thiết kế idempotency và hợp đồng nghiệp vụ tương ứng.

### 5.2. Event khác command gửi qua queue

**Event:** `OrderConfirmed` là sự thật đã xảy ra; bên phát không cần biết toàn bộ người nhận. Nó hữu ích cho mở rộng phản ứng mà ít ràng buộc trực tiếp.

**Command qua queue:** `GenerateInvoiceForOrder` yêu cầu một năng lực cụ thể tạo hóa đơn; cần làm rõ chủ sở hữu xử lý, phản hồi/trạng thái, retry và điều kiện hoàn tất.

Cùng dùng broker nhưng mục đích khác nhau. Đặt tên tất cả message bằng hậu tố “Event” không khiến chúng trở thành domain event.

## 6. Không phải mọi nội dung đều cần HTTP hay broker

### 6.1. Gọi nội bộ khi trách nhiệm vẫn nằm cùng tiến trình

Một modular monolith có thể dùng interface để các module giao tiếp:

    CheckoutApplicationService
       |
       | PricingPort.quote(cart)
       v
    PricingModule

Nếu hai module cùng tiến trình, việc biến `quote` thành HTTP call sang localhost hoặc qua broker chỉ vì định hướng “sau này sẽ tách” có thể tạo overhead, retry và mô hình lỗi phân tán từ quá sớm.

Có thể giữ ranh giới module rõ, bảo vệ dữ liệu và thiết kế interface ổn định. Khi xuất hiện lý do triển khai độc lập có thật, chuyển ranh giới kỹ thuật ra mạng với kế hoạch tương thích.

### 6.2. Query trực tiếp ở nơi dữ liệu được sở hữu

Trong một service, các lớp nghiệp vụ có thể truy cập repository của chính service đó mà không phải gọi REST nội bộ. Nếu một màn hình cần dữ liệu của service khác, trước tiên xác định liệu cần query qua API, một read projection được đồng bộ hoặc snapshot tại thời điểm giao dịch.

**Không nên mở quyền ghi chéo cơ sở dữ liệu của các service** để tránh API một cách tùy tiện: giải pháp này thường làm mất quyền sở hữu dữ liệu và tạo coupling schema. Shared database có thể hợp lý trong một ứng dụng/module có chung ownership, nhưng khác hẳn với việc nhiều microservices cùng tự do cập nhật bảng của nhau.

### 6.3. File hoặc object storage cho payload lớn

Xuất file PDF dài, dữ liệu phân tích lớn hoặc media không nhất thiết nên nhét hoàn toàn vào một message của broker. Một mô hình có thể là:

    Report service tạo file
      → lưu vào object storage
      → phát ReportReady(reportId, objectKey, checksum)
      → người nhận tải file có phân quyền

Message chỉ chứa metadata và tham chiếu, còn dữ liệu lớn được truyền bằng kênh phù hợp. Cần xử lý quyền đọc, vòng đời file, checksum và tránh để đường dẫn công khai lộ dữ liệu nhạy cảm.

### 6.4. Polling hoặc push đến trình duyệt

Nếu giao diện cần biết tiến độ job mỗi vài giây, polling API trạng thái có thể đủ đơn giản và tin cậy. Nếu cần nhiều cập nhật liên tục từ server đến client, SSE có thể phù hợp khi chủ yếu là một chiều; WebSocket có thể phù hợp khi hai chiều liên tục.

Không nên đưa broker trực tiếp ra trình duyệt như giải pháp mặc định. Backend vẫn chịu trách nhiệm authorization, kiểm soát tải và bảo vệ dữ liệu người dùng.

### 6.5. Batch integration

Hệ thống kế toán cần dữ liệu đối soát cuối ngày có thể dùng batch export/import với kiểm tra toàn vẹn và đối soát. Nếu không có nhu cầu thời gian thực, việc vận hành event stream toàn thời gian có thể không đem lại lợi ích tương xứng.

## 7. Cách chọn cơ chế từ yêu cầu nghiệp vụ

Một chuỗi câu hỏi quyết định hữu ích:

1. **Hai thành phần có thật sự nằm ở hai đơn vị triển khai độc lập không?** Nếu không, xem xét interface hoặc module call trước.
2. **Có cần kết quả ngay để hoàn thành thao tác hiện tại không?** Nếu có, request–response qua HTTP/gRPC hoặc cơ chế tương đương thường dễ biểu đạt.
3. **Nếu service đích chậm hoặc ngừng hoạt động, thao tác hiện tại có bắt buộc chờ không?** Nếu không, cân nhắc job/queue/event có lưu trạng thái bền vững.
4. **Đang yêu cầu hành động hay thông báo một sự thật?** Command cần người chịu trách nhiệm xử lý; event giúp các bên khác phản ứng với điều đã xảy ra.
5. **Có bao nhiêu người nhận và họ có cần độc lập tiến độ xử lý?** Nhiều consumer độc lập có thể phù hợp với pub/sub; một worker xử lý công việc có thể dùng queue đơn giản.
6. **Độ mới dữ liệu và nhất quán cần đến đâu?** Nếu phải quyết định ngay trên trạng thái cập nhật, chỉ dùng event/cached projection có thể chưa đủ.
7. **Khi lỗi hoặc mất kết nối, hệ thống sẽ làm gì?** Chọn cơ chế phù hợp với retry, idempotency, timeout, trạng thái chưa rõ và khả năng đối soát.
8. **Đội ngũ có vận hành và giám sát được cơ chế này không?** Broker, schema registry, streaming platform hay hệ thống callback đều tạo chi phí vận hành thực.

### Ma trận quyết định nhanh

| Nhu cầu | Lựa chọn khởi đầu đáng xem xét | Điều kiện cần xác minh |
| --- | --- | --- |
| Đọc chi tiết một tài nguyên từ service khác, cần ngay | HTTP/REST hoặc gRPC | Timeout, cache, quyền truy cập |
| Yêu cầu nghiệp vụ cần phản hồi ngay | Request–response | Idempotency, trạng thái khi timeout, hợp đồng |
| Gửi email sau khi hoàn tất đơn | Event/queue hoặc job nền | Email có bắt buộc trước khi xác nhận đơn không? |
| Tạo báo cáo tốn vài phút | HTTP 202 + job status; worker queue khi cần | Trạng thái job, hủy, retry, lưu kết quả |
| Nhiều hệ thống cần biết một thay đổi đã xảy ra | Domain event qua pub/sub phù hợp | Delivery, consumer độc lập, schema evolution |
| Đồng bộ dữ liệu định kỳ, chấp nhận trễ | Batch/file integration | Chu kỳ, reconciliation, lỗi dữ liệu |
| Cập nhật dashboard đang mở | Polling, SSE hoặc WebSocket | Tần suất, chiều giao tiếp, số kết nối |
| Trao đổi nhiều lần trong cùng ứng dụng | Interface/internal call | Ranh giới module và dependency direction |
| Truyền file lớn | HTTP streaming hoặc object storage + reference | Authentication, checksum, lifetime |

Đây là **lựa chọn ban đầu**, không phải kết luận bắt buộc. Chẳng hạn một command có thể vào queue khi cần lưu bền và chấp nhận xử lý sau; một read query có thể sử dụng projection của event stream. Điều quyết định là contract nghiệp vụ.

## 8. Case study: quy trình đặt hàng có nhiều kiểu tương tác

Xét quy trình của một cửa hàng trực tuyến:

- Khách xem giá và tồn kho.
- Khách đặt hàng và chọn phương thức thanh toán.
- Hệ thống ghi nhận đơn.
- Khách nhận thông báo.
- Bộ phận phân tích ghi nhận doanh thu.
- Vận hành tạo báo cáo đối soát định kỳ.

Không có lý do ép tất cả bước đi qua cùng một công nghệ.

### 8.1. Đọc thông tin để hiển thị

    Browser ── HTTP GET ──> Catalog

Một query cần trả ngay để hiển thị có thể dùng HTTP; nếu dữ liệu công khai ít thay đổi, có thể có HTTP cache/CDN. Nếu có số lượng lớn item, thiết kế bulk API hoặc read model để tránh N+1. Broker không phải yêu cầu bắt buộc.

### 8.2. Xác nhận đặt hàng và thanh toán

    Browser ── POST /orders ──> Ordering
                                  |
                                  | command: authorize payment
                                  v
                                Payment

Tùy domain, Ordering có thể cần kết quả đồng bộ để phản hồi thành công/thất bại, hoặc trả về trạng thái PENDING khi đối tác thanh toán cần xử lý lâu. Hợp đồng phải nêu rõ:

- Ai sở hữu trạng thái đơn và trạng thái thanh toán?
- Idempotency key nào ngăn tạo giao dịch trùng?
- Khi Payment xử lý xong nhưng phản hồi bị mất, xác định kết quả ra sao?
- Nếu giữ tồn kho trước khi thanh toán, tình huống thất bại được bù trừ thế nào?

Đổi REST sang broker không xóa các câu hỏi này. Nếu quy trình kéo dài, có thể dùng saga/orchestration và trạng thái trung gian thay cho giữ một request đồng bộ rất lâu.

### 8.3. Thông báo sau khi đơn được xác nhận

    Ordering: OrderConfirmed
        |
        v
    Event publication
        |
        +----> Notification
        +----> Analytics
        '----> Loyalty

Vì việc gửi email hoặc cập nhật thống kê thường có thể diễn ra sau xác nhận đơn, event giúp các consumer xử lý độc lập và không giữ bước checkout chờ họ. Tuy nhiên cần xác định chính xác **khi nào** `OrderConfirmed` có hiệu lực; chỉ phát event sau khi thay đổi trạng thái được ghi nhận bền vững.

Nếu dùng cơ sở dữ liệu giao dịch và broker riêng, có nguy cơ commit DB thành công nhưng phát event thất bại. **Transactional outbox** là một cách giải quyết: ghi trạng thái nghiệp vụ và bản ghi sự kiện vào cùng giao dịch DB, rồi một publisher chuyển outbox sang broker; consumer phải chịu được event lặp.

### 8.4. Đối soát và báo cáo

Đối soát với đối tác thanh toán có thể nhận file cuối ngày hoặc truy vấn API theo lô. Nếu đối tác không hỗ trợ streaming event, không có lý do xây cầu nối broker phức tạp chỉ để phục vụ một batch có lịch rõ.

**Kết quả:** cùng một hành trình có thể dùng HTTP để nhận lệnh, thao tác nội bộ cho logic cùng tiến trình, event cho hậu xử lý, queue cho job có retry, và batch cho đối soát. Đây là quyết định theo trách nhiệm và thời điểm cần kết quả.

## 9. Sai lầm phổ biến khi chọn REST hoặc broker

### “Microservices nghĩa là mọi service phải có REST API”

Không đúng. Microservice là một ranh giới nghiệp vụ và vận hành, không được xác định bởi việc sử dụng một giao thức duy nhất. Có service chủ yếu xử lý message, có service phục vụ API, có worker chỉ chạy tác vụ nền.

### “Dùng broker sẽ luôn nhanh hơn REST”

Không đúng. Gửi message qua broker có thể có lưu bền, định tuyến, serialization, queueing và xử lý trễ. Với query rất nhỏ cần đáp án ngay, request–response trực tiếp có thể đơn giản và phù hợp hơn. Broker hữu ích chủ yếu nhờ thay đổi **kiểu phụ thuộc thời gian và cách phân phối công việc**, chứ không phải cam kết latency thấp tuyệt đối.

### “Cứ bất đồng bộ là loại bỏ coupling”

Không đúng. Event schema, ý nghĩa trạng thái, khóa định danh, thứ tự và điều kiện xử lý vẫn tạo hợp đồng giữa producer với consumer. Một consumer phụ thuộc vào trường nội bộ chưa ổn định có thể gây coupling mạnh dù không có HTTP call.

### “REST thì không thể xử lý bất đồng bộ”

Không đúng. HTTP 202 Accepted, job resource và polling/callback là mô hình xử lý bất đồng bộ hợp lệ; backend có thể có queue hoặc worker mà client không cần biết chi tiết.

### “Có broker thì message sẽ xử lý đúng một lần”

Không đúng nếu hiểu ở mức tác dụng phụ nghiệp vụ. Từng hệ thống có delivery semantics và điều kiện bảo đảm cụ thể. Tác vụ như thu tiền, tạo phiếu hoặc gửi thông báo vẫn cần định danh, idempotency, ack và xử lý lại an toàn.

### “Dữ liệu cần lúc nào cũng phải gọi service chủ”

Không hẳn. Dữ liệu dùng để quyết định nghiệp vụ có thể cần kiểm tra với chủ sở hữu tại thời điểm thao tác; dữ liệu chỉ dùng để hiển thị có thể lấy từ cache, snapshot hoặc projection có độ mới được công bố. Cần cân bằng nhất quán với độ trễ và độ sẵn sàng.

### “Thấy nhiều HTTP calls thì chuyển hết sang event”

Có thể chỉ chuyển từ khó khăn về latency sang khó khăn về nhất quán và quan sát. Hãy kiểm tra N+1, batch, API theo business operation hoặc điều chỉnh ranh giới trước khi biến thao tác cần đáp án ngay thành event-driven process.

## 10. Đánh đổi vận hành khi thêm một cơ chế giao tiếp

Mỗi kiểu truyền thông tạo ra một hợp đồng vận hành khác nhau.

| Vấn đề | Request–response trực tiếp | Broker/queue/event |
| --- | --- | --- |
| Khi receiver tạm thời unavailable | Caller nhận lỗi/timeout; có thể fallback | Message có thể chờ nếu đã được nhận bền vững; backlog tăng |
| Hành vi retry | Caller hoặc hạ tầng cần điều khiển | Consumer/broker thường hỗ trợ retry nhưng vẫn phải thiết kế |
| Kết quả chưa chắc chắn | Timeout có thể mơ hồ | Ack và tác dụng phụ cũng có thể mơ hồ |
| Phát triển hợp đồng | API/version compatibility | Message schema/consumer compatibility |
| Quan sát | Tracing theo request khá trực quan | Cần correlation ID, lag, backlog, tracing qua async boundary |
| Xử lý trùng | Cần idempotency khi request có side effect | Consumer cần idempotency do redelivery |
| Thứ tự | Có thể rõ trong một lời gọi, không bảo đảm thứ tự giữa nhiều request | Tùy partition/key/queue và retry; không mặc nhiên có thứ tự toàn cục |
| Khả năng kiểm soát tải | Rate limit, connection/concurrency limit | Queue depth, consumer lag, backpressure và số worker |
| Độ phức tạp hạ tầng | HTTP gateway, discovery, TLS, client policy | Broker, cluster, retention, schema, DLQ, monitoring, vận hành |

Một broker giúp tách producer khỏi **thời điểm consumer chạy**, nhưng không tự giúp toàn hệ thống luôn sẵn sàng. Nếu consumer ngừng hoạt động quá lâu, backlog và chi phí lưu trữ tăng; nếu yêu cầu nghiệp vụ cần kết quả ngay, người dùng vẫn phải chờ hoặc nhận trạng thái đang xử lý.

## 11. Những bất biến cần giữ dù chọn công nghệ nào

Các quyết định giao tiếp phải bảo vệ các đặc tính nghiệp vụ chung:

**Tính đúng đắn:** Không thu tiền hai lần, không giữ tồn kho quá số lượng cho phép, không xác nhận một đơn khi điều kiện chưa thỏa.

**Quyền sở hữu dữ liệu:** Một năng lực có trách nhiệm rõ về thay đổi trạng thái và invariant; service khác không được tự ý sửa dữ liệu nội bộ của nó.

**Khả năng tương thích:** Producer và consumer, client và server có thể được nâng cấp không đồng thời trong phạm vi contract đã cam kết.

**Trạng thái lỗi có nghĩa:** Hết deadline hoặc mất kết nối không biến thành một kết luận chắc chắn rằng thao tác chưa chạy. Cần trạng thái PENDING/UNKNOWN/FAILED/COMPLETED nếu nghiệp vụ yêu cầu, cùng cơ chế truy vấn hoặc đối soát.

**Bảo mật:** Authentication, authorization, mã hóa đường truyền, kiểm tra schema/input và quyền truy cập dữ liệu phải phù hợp với đường giao tiếp. Broker không miễn trừ kiểm soát quyền của publisher/consumer.

**Khả năng quan sát:** Có correlation/trace ID xuyên request và event, thời gian xử lý, lỗi, retry, backlog và khả năng truy ngược một kết quả nghiệp vụ tới các bước liên quan.

**Khả năng phục hồi:** Timeouts, retry hữu hạn, backoff với jitter, idempotency, circuit breaker hoặc bulkhead nơi phù hợp; với async thì có DLQ, replay/repair và khả năng điều tra message lỗi.

Những nguyên tắc này độc lập với tên sản phẩm và thường quan trọng hơn tranh luận REST hay broker.

## 12. Checklist lựa chọn có thể dùng trong thiết kế

Trước khi tạo một kết nối giữa hai thành phần, ghi lại ngắn gọn:

1. **Business operation:** người dùng hoặc hệ thống muốn đạt kết quả cụ thể gì?
2. **Owner:** ai chịu trách nhiệm đưa ra quyết định và lưu trạng thái?
3. **Interaction type:** query, command hay event?
4. **Time constraint:** phải phản hồi ngay, hay có thể chờ bao lâu?
5. **Consistency:** dữ liệu cũ chấp nhận được đến mức nào?
6. **Failure behavior:** khi đích timeout, retry/truy vấn đối soát ra sao?
7. **Multiplicity:** một nhận, nhiều nhận; push hay pull; thường xuyên hay batch?
8. **Volume:** throughput, payload, độ trễ p95/p99, peak traffic?
9. **Evolution:** service có thể deploy khác phiên bản mà vẫn tương thích không?
10. **Operations:** có sẵn năng lực chạy, giám sát, bảo mật và sửa lỗi đường truyền đó không?

Sau đó thử viết một câu quyết định:

> “Với tác vụ [X], bên gọi cần [kết quả/trạng thái] trong [thời gian]; dữ liệu do [Y] sở hữu; vì [yêu cầu nhất quán và xử lý lỗi], dùng [cơ chế] kèm [contract/timeout/idempotency/quan sát].”

Nếu không thể điền các phần trên, việc chọn REST, broker hay gRPC vẫn thiếu căn cứ.

## 13. Bài tập thực hành

Một nền tảng bán hàng có các năng lực **Catalog, Ordering, Payment, Notification, Search, Analytics**. Nhóm phát triển đề xuất: “Cho tất cả service giao tiếp bằng Kafka để có kiến trúc event-driven”, trong khi nhóm khác đề xuất: “Tất cả qua REST để dễ debug”.

Hãy chọn cơ chế ban đầu và giải thích cho từng tương tác:

1. Trang chi tiết sản phẩm cần tên, ảnh và giá mới nhất theo chính sách hiển thị.
2. Ordering cần yêu cầu Payment cho một giao dịch mà người dùng đang chờ.
3. Sau khi đơn được xác nhận, cần gửi email và cập nhật thống kê.
4. Search cần cập nhật chỉ mục sau khi mô tả sản phẩm thay đổi; cho phép độ trễ ngắn.
5. Người dùng yêu cầu xuất báo cáo doanh thu khối lượng lớn.
6. Hai module nhỏ của cùng một ứng dụng cần dùng chung logic tính phí đã đóng gói bằng interface.
7. Bảng theo dõi đơn hàng cần tự động cập nhật tiến độ vận chuyển trên trình duyệt.

Với mỗi trường hợp, hãy chỉ rõ: **query/command/event**, **cần kết quả ngay hay không**, **chủ sở hữu trạng thái**, **cách xử lý timeout/trùng**, **dữ liệu có cần nhất quán tức thời không**.

**Gợi ý định hướng:** Trang sản phẩm có thể dùng HTTP hoặc projection/cache phù hợp; yêu cầu thanh toán cần hợp đồng lệnh chặt và idempotency; email/analytics có thể phản ứng với event; Search có thể cập nhật từ event; báo cáo có thể dùng job và object storage; module nội bộ dùng interface; trình duyệt có thể dùng polling/SSE/WebSocket tùy nhu cầu. Đây là các lựa chọn để thảo luận, không phải đáp án duy nhất.

## 14. Kết luận

**Đừng suy ra rằng mọi tương tác trong microservices phải đi qua REST hoặc broker.** Mỗi công nghệ giải quyết một phần khác nhau của bài toán: request–response giúp lấy kết quả trực tiếp; message queue và event hỗ trợ xử lý độc lập theo thời gian; giao tiếp nội bộ tránh overhead khi chưa có ranh giới mạng; streaming, polling, file và batch giải quyết những nhu cầu riêng.

Kiến trúc tốt bắt đầu từ **ranh giới nghiệp vụ, nhu cầu thời gian, tính nhất quán, quyền sở hữu dữ liệu và hành vi khi lỗi**. Chọn cơ chế đơn giản nhất đáp ứng những yêu cầu đó, đo lại tác động thực tế và kết hợp các mô hình khi thật sự cần.
