# Phối hợp nhiều mô hình compute trong cùng một hệ thống

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân tích đặc tính workload để chọn máy ảo, container, hàm serverless hoặc dịch vụ compute được quản lý.
- Thiết kế kiến trúc kết hợp nhiều mô hình compute mà vẫn giữ ranh giới trách nhiệm rõ ràng.
- Chọn cách giao tiếp đồng bộ, bất đồng bộ và chia sẻ dữ liệu giữa các thành phần.
- Điều phối luồng công việc, danh tính, mạng, cấu hình và quan sát xuyên suốt nhiều môi trường thực thi.
- Quản lý khả năng phục hồi, mở rộng, bảo mật, chi phí và độ phức tạp vận hành của hệ thống kết hợp.
- Kiểm chứng kiến trúc bằng các kịch bản tải, lỗi thành phần và sự cố phụ thuộc.

## 1. Vì sao một hệ thống cần nhiều mô hình compute?

Một ứng dụng thực tế thường có nhiều loại công việc với yêu cầu khác nhau. API phục vụ người dùng cần độ trễ thấp và số instance sẵn sàng ổn định. Worker xử lý ảnh cần mở rộng theo số tác vụ đang chờ. Một dịch vụ cũ có thể cần hệ điều hành hoặc phần mềm đặc thù. Tác vụ báo cáo chạy vài giờ mỗi đêm lại phù hợp với nền tảng batch. Ép tất cả workload vào một mô hình compute có thể làm tăng chi phí, giảm hiệu năng hoặc khiến vận hành phức tạp.

Phối hợp nhiều mô hình compute nghĩa là phân chia hệ thống thành các thành phần thực thi trên môi trường phù hợp, sau đó kết nối chúng bằng hợp đồng API, sự kiện, hàng đợi, luồng dữ liệu và cơ chế điều phối. Ví dụ:

- API quản lý đơn hàng chạy trong container để có môi trường nhất quán và khả năng mở rộng ngang.
- Một phần mềm lập lịch cũ chạy trên máy ảo vì phụ thuộc hệ điều hành hoặc agent đặc thù.
- Hàm serverless phản ứng khi đơn hàng được xác nhận và phát sự kiện sang các dịch vụ khác.
- Worker container xử lý tác vụ dài hoặc cần thư viện chuyên dụng từ queue.
- Tác vụ tổng hợp dữ liệu chạy theo lịch trên dịch vụ batch được quản lý.
- Cơ sở dữ liệu, cache và message broker dùng dịch vụ managed để giảm công việc vận hành hạ tầng dữ liệu.

Mục tiêu của kiến trúc kết hợp là đặt mỗi workload vào nơi phù hợp, đồng thời giữ trải nghiệm hệ thống nhất quán. Người dùng không cần biết một yêu cầu đi qua bao nhiêu loại compute; họ cần kết quả đúng, an toàn và đúng hạn.

## 2. Các mô hình compute thường phối hợp

| Mô hình | Đặc tính chính | Workload phù hợp | Chi phí và đánh đổi |
|---|---|---|---|
| Máy ảo (VM) | Kiểm soát hệ điều hành, tiến trình, agent và cấu hình máy | Phần mềm cũ, ứng dụng cần quyền hệ thống, dịch vụ có trạng thái hoặc phụ thuộc đặc thù | Cần vá hệ điều hành, quản lý capacity và triển khai |
| Container trên Kubernetes hoặc nền tảng container | Đóng gói ứng dụng, triển khai đồng nhất, điều phối và scale theo Pod/task | API, microservice, worker chạy liên tục, workload cần cấu hình runtime linh hoạt | Cần quản lý cluster hoặc trả chi phí cho nền tảng managed; có overhead điều phối |
| Hàm serverless | Kích hoạt theo request/sự kiện, nền tảng quản lý môi trường thực thi | Webhook, xử lý sự kiện ngắn, glue code, tác vụ có tải gián đoạn | Có giới hạn thời gian, runtime, concurrency; cold start và chi phí theo invocation |
| Container serverless | Chạy container mà không cần tự quản lý node hoặc cluster | API, worker hoặc tác vụ container hóa có tải biến động | Ít quyền kiểm soát hạ tầng; cần hiểu giới hạn nền tảng và mô hình tính phí |
| Dịch vụ batch/compute được quản lý | Lập lịch và cấp tài nguyên cho job hữu hạn | ETL, mô phỏng, xử lý dữ liệu, tác vụ theo lô | Phù hợp job dài nhưng cần quản lý dữ liệu đầu vào, retry và checkpoint |
| Dịch vụ compute chuyên dụng | Tài nguyên GPU, HPC hoặc môi trường tối ưu theo loại tác vụ | Huấn luyện mô hình, mô phỏng khoa học, xử lý song song nặng | Chi phí cao, cần tối ưu thời gian sử dụng và lập lịch tài nguyên |

Không cần biến mọi thành phần thành một dịch vụ độc lập. Mỗi ranh giới mới làm tăng số kết nối, cấu hình, quyền, log, cảnh báo và quy trình phát hành. Chỉ tách workload khi có khác biệt đáng kể về vòng đời, yêu cầu tài nguyên, mức độ tin cậy, khả năng mở rộng hoặc quyền sở hữu.

### 2.1. Chọn mô hình theo đặc tính workload

Đánh giá workload theo các câu hỏi:

- **Thời gian chạy:** request ngắn, worker chạy liên tục hay job kéo dài nhiều giờ?
- **Mẫu tải:** ổn định, theo mùa, burst đột ngột hay theo lịch?
- **Tài nguyên:** CPU, bộ nhớ, I/O, mạng, GPU hoặc truy cập thiết bị đặc thù?
- **Trạng thái:** stateless, cần lưu session, cần volume hay có checkpoint?
- **Khả năng gián đoạn:** có thể retry, chạy lại hoặc chuyển node không?
- **Môi trường:** cần quyền quản trị hệ điều hành, thư viện native hoặc runtime cố định?
- **Độ trễ:** cần phản hồi tức thời hay chấp nhận hàng đợi?
- **Quy mô:** số instance, concurrency, thông lượng và dung lượng dữ liệu?
- **Vận hành:** đội ngũ có khả năng quản lý VM, cluster, function và pipeline hay không?
- **Chi phí:** tính theo thời gian chạy, tài nguyên giữ sẵn, request, dữ liệu truyền và công sức vận hành?

Một workload có thể đổi mô hình theo giai đoạn. Ví dụ, một tác vụ nhập dữ liệu ban đầu chạy trong container worker. Khi khối lượng tăng, nhóm có thể chuyển sang dịch vụ batch để lập lịch, checkpoint và phân bổ tài nguyên hiệu quả hơn. Việc chuyển đổi cần dựa trên số liệu, không chỉ dựa trên xu hướng công nghệ.

## 3. Nguyên tắc thiết kế kiến trúc kết hợp

### 3.1. Chia theo năng lực và vòng đời

Mỗi thành phần nên có một trách nhiệm rõ ràng. API nhận yêu cầu và kiểm tra điều kiện; worker xử lý nghiệp vụ nặng; hàm serverless phản ứng với sự kiện; job batch xử lý tập dữ liệu hữu hạn; VM giữ phần mềm phụ thuộc môi trường đặc thù.

Không nên chia thành phần chỉ vì mỗi mô hình compute có một công nghệ triển khai khác nhau. Một service nhỏ có thể chạy tốt trong cùng một container với thành phần liên quan nếu chúng có cùng vòng đời và yêu cầu scale. Ngược lại, nếu worker cần scale lên hàng trăm instance trong khi API chỉ cần vài replica, tách worker pool giúp mỗi loại workload có chính sách tài nguyên riêng.

### 3.2. Dùng hợp đồng rõ ràng giữa các thành phần

Các thành phần cần giao tiếp qua hợp đồng ổn định:

- API contract cho request/response đồng bộ.
- Event schema cho thông báo sự kiện.
- Message schema cho công việc trong queue.
- Data contract cho bảng, file, object và định dạng dữ liệu.
- Workflow contract cho trạng thái, timeout, retry và kết quả từng bước.

Hợp đồng cần định nghĩa phiên bản, trường bắt buộc, mã lỗi, thời hạn xử lý và quyền truy cập. Tránh để một thành phần phụ thuộc vào cấu trúc nội bộ hoặc filesystem của thành phần khác.

### 3.3. Ưu tiên giao tiếp bất đồng bộ cho công việc dài

Gọi đồng bộ phù hợp khi caller cần kết quả ngay và thời gian phản hồi có giới hạn. Với công việc dài, burst hoặc có thể retry, nên dùng queue hoặc event bus. Caller gửi yêu cầu, nhận jobId, rồi tra cứu trạng thái hoặc nhận sự kiện hoàn tất.

Không giữ một HTTP connection trong nhiều phút chỉ để chờ tác vụ batch nếu có thể tách thành quy trình bất đồng bộ. Cách này giảm phụ thuộc thời gian giữa các mô hình compute và cho phép từng phần scale độc lập.

### 3.4. Tách trạng thái nghiệp vụ khỏi vòng đời compute

Instance VM, Pod, function invocation hoặc batch worker có thể bị thay thế bất cứ lúc nào. Trạng thái nghiệp vụ cần được lưu trong database, object storage, queue hoặc state store bền vững. Không coi filesystem tạm của function hay ổ đĩa ephemeral của container là nơi lưu kết quả duy nhất.

Khi một thành phần khởi động lại ở mô hình compute khác, nó phải có thể tiếp tục từ dữ liệu bền vững và hợp đồng đã định nghĩa.

### 3.5. Tránh phụ thuộc vào chi tiết nhà cung cấp

Dùng adapter hoặc lớp tích hợp khi cần chuyển giữa các dịch vụ tương đương. Tuy nhiên, không nên xây một lớp trừu tượng quá rộng che giấu mọi khác biệt. Queue, stream và event bus có semantics khác nhau; việc ép chúng vào cùng một giao diện đơn giản có thể làm mất các tính năng quan trọng như ordering, visibility timeout hoặc replay.

Trừu tượng hóa những gì thực sự ổn định: định danh, schema, trạng thái nghiệp vụ, retry policy và telemetry. Giữ các cấu hình đặc thù của nền tảng ở adapter hoặc deployment layer.

## 4. Kiến trúc tham khảo: nền tảng thương mại điện tử

Một hệ thống thương mại điện tử có thể phối hợp nhiều mô hình compute như sau:

    Người dùng
       |
       v
    Load balancer / API gateway
       |
       v
    Container service: Order API
       |
       +------> Managed database
       |
       +------> Transactional outbox
                    |
                    v
               Event publisher
                    |
                    v
                Event bus
                 /   |   \
                /    |    \
               v     v     v
          Function  Queue  Function
          payment   image  notification
             |        |        |
             v        v        v
          Payment  Container  Email/SMS
          provider worker    provider
                      |
                      v
                Object storage

    Legacy ERP connector
          (VM)
             |
             +------> ERP database / API

    Nightly reconciliation
          (Managed batch)
             |
             +------> Managed database / Object storage

Trong kiến trúc này:

- Order API chạy trong container, nhận request, xác thực và ghi đơn hàng.
- Database lưu dữ liệu nghiệp vụ.
- Transactional outbox ghi sự kiện cùng transaction với đơn hàng.
- Publisher chuyển outbox record sang event bus.
- Function xử lý bước ngắn như điều phối thanh toán hoặc phát thông báo.
- Queue giữ tác vụ xử lý ảnh; container worker thực hiện công việc nặng và có thể retry.
- VM chạy connector ERP vì cần thư viện hoặc kết nối mạng cũ.
- Job batch đối soát giao dịch vào ban đêm và xuất báo cáo.

Kiến trúc là ví dụ để phân tích, không phải khuôn mẫu bắt buộc. Nếu connector ERP có thể container hóa và không cần đặc quyền hệ điều hành, có thể chuyển sang container. Nếu tác vụ ảnh ngắn và nằm trong giới hạn runtime, function có thể xử lý trực tiếp. Chọn theo yêu cầu thực tế và số liệu.

## 5. Ví dụ luồng nghiệp vụ xuyên nhiều mô hình compute

Giả sử khách hàng đặt hàng và hệ thống cần xác nhận thanh toán, đồng bộ ERP, tạo hóa đơn, xử lý ảnh sản phẩm và gửi thông báo.

1. Client gửi request đến Order API trên container.
2. API xác thực, kiểm tra tồn kho và ghi đơn hàng cùng outbox record trong một transaction.
3. Publisher đọc outbox và phát OrderCreated đến event bus.
4. Function thanh toán nhận sự kiện, gọi payment provider với idempotency key.
5. Khi thanh toán thành công, function phát PaymentCaptured.
6. Event bus định tuyến sự kiện đến function thông báo và queue tạo hóa đơn.
7. Container worker lấy message từ queue, tạo hóa đơn hoặc xử lý tài liệu.
8. Connector ERP trên VM nhận sự kiện đồng bộ, chuyển đổi schema và cập nhật hệ thống cũ.
9. Batch job chạy theo lịch để đối soát các giao dịch, phát hiện sai lệch và tạo báo cáo.
10. Các thành phần cập nhật trạng thái nghiệp vụ để Order API trả kết quả nhất quán cho người dùng.

Mỗi bước có thể thất bại độc lập. Nếu payment provider timeout, function cần retry có giới hạn và idempotency. Nếu ERP ngừng hoạt động, connector có thể giữ công việc trong queue riêng và xử lý sau. Nếu batch job bị dừng, cần checkpoint để tiếp tục. Nếu notification provider lỗi, không được rollback đơn hàng đã thanh toán; chỉ cần retry thông báo hoặc đánh dấu trạng thái cần xử lý.

Điểm quan trọng là xác định rõ trạng thái đơn hàng. Ví dụ, đơn hàng có thể ở trạng thái PAYMENT_PENDING, PAID, ERP_SYNC_PENDING, READY_TO_FULFILL. Không nên đánh dấu toàn bộ đơn hàng hoàn tất chỉ vì một function invocation trả về thành công.

## 6. Kết nối giữa VM, container, serverless và batch

### 6.1. Kết nối đồng bộ qua API

Dùng API khi caller cần kết quả nhanh và hợp đồng phản hồi rõ ràng. Ví dụ container Order API gọi một service trên VM để tra cứu mã khách hàng trong ERP.

Cần cấu hình:

- DNS và endpoint ổn định, không phụ thuộc IP ephemeral.
- TLS và xác thực service-to-service.
- Timeout ngắn phù hợp với SLA của caller.
- Retry chỉ với lỗi tạm thời và thao tác an toàn để retry.
- Circuit breaker hoặc bulkhead để một dịch vụ chậm không chiếm toàn bộ tài nguyên caller.
- Giới hạn connection pool và concurrency để bảo vệ service trên VM.

Không retry vô hạn một request đồng bộ. Nếu service ERP không phản hồi trong timeout, caller nên trả lỗi có kiểm soát hoặc chuyển yêu cầu sang queue để xử lý sau, tùy nghiệp vụ.

### 6.2. Kết nối bất đồng bộ qua queue hoặc event bus

Queue phù hợp với một consumer pool xử lý công việc. Event bus phù hợp khi nhiều consumer cần nhận các sự kiện khác nhau. Một hệ thống có thể dùng cả hai: event bus định tuyến sự kiện đến queue riêng của từng nhóm worker.

Mỗi queue nên có:

- Chủ sở hữu và mục đích rõ ràng.
- Schema và phiên bản message.
- Retention, visibility/lease và giới hạn số lần thử.
- DLQ và quy trình redrive.
- Chính sách ưu tiên, quota và giới hạn backlog.
- Metric tuổi message và tốc độ xử lý.

Tách queue theo loại công việc giúp worker scale riêng. Tránh một queue duy nhất chứa tác vụ ngắn, tác vụ dài và tác vụ khẩn cấp nếu chúng có SLA khác nhau; một công việc nặng có thể làm chậm tất cả message phía sau.

### 6.3. Trao đổi dữ liệu lớn qua object storage

Không truyền file lớn qua API hoặc message broker nếu nền tảng có giới hạn payload hoặc chi phí truyền cao. Thành phần tạo dữ liệu ghi object vào storage, sau đó phát event chứa object key, version, checksum và metadata. Thành phần tiêu thụ đọc object bằng danh tính được cấp quyền.

Cần xác định:

- Ai sở hữu object và ai được phép đọc/xóa?
- Object tồn tại trong bao lâu?
- Có versioning hoặc immutable object không?
- Làm sao xác minh file không bị thay đổi?
- Điều gì xảy ra khi event đến trước khi object có thể đọc?
- Cách xóa dữ liệu theo chính sách retention và yêu cầu nghiệp vụ?

Sự kiện chỉ nên được xác nhận sau khi consumer đã xử lý hoặc lưu trạng thái có thể tiếp tục. Với file lớn, không tải toàn bộ vào bộ nhớ nếu có thể stream theo chunk.

### 6.4. Kết nối mạng riêng và hệ thống cũ

VM trong private subnet có thể kết nối đến ERP qua VPN hoặc private link. Container và function cũng cần đường mạng phù hợp nếu truy cập tài nguyên nội bộ. Không giả định function serverless luôn có quyền truy cập VPC hoặc mạng riêng theo mặc định; cần cấu hình network attachment, route, DNS, security group và quyền phù hợp với nền tảng.

Khi nhiều mô hình compute nằm ở các vùng mạng khác nhau, kiểm tra:

- Định tuyến hai chiều và DNS.
- TLS certificate và trust chain.
- Firewall rule tối thiểu theo source/destination/port.
- NAT, egress và chi phí truyền dữ liệu.
- Băng thông, latency và giới hạn connection.
- Khả năng phục hồi khi VPN hoặc private link mất kết nối.

Nếu một kết nối cũ không thể mở trực tiếp từ cloud, cân nhắc connector chạy gần hệ thống cũ và giao tiếp ra ngoài qua kết nối được kiểm soát.

## 7. Điều phối luồng công việc

Khi nhiều mô hình compute cùng tham gia một quy trình, cần xác định ai chịu trách nhiệm điều phối. Có ba mẫu thường dùng:

| Mẫu | Đặc điểm | Khi phù hợp |
|---|---|---|
| Choreography | Mỗi thành phần phản ứng với event và phát event tiếp theo | Luồng đơn giản, các dịch vụ độc lập |
| Orchestration/workflow | Một workflow quản lý thứ tự, trạng thái, timeout, retry và nhánh | Quy trình nhiều bước, cần theo dõi trạng thái tổng thể |
| Scheduler + queue | Scheduler tạo job hoặc message theo lịch; worker pool xử lý | Batch, tác vụ định kỳ, công việc có thời điểm chạy |

### 7.1. Choreography

Trong choreography, OrderCreated kích hoạt function thanh toán; PaymentCaptured kích hoạt worker hóa đơn và function thông báo; ERP connector lắng nghe sự kiện riêng. Mỗi thành phần biết event cần xử lý và phát event tiếp theo.

Ưu điểm là giảm phụ thuộc trực tiếp giữa các dịch vụ. Nhược điểm là luồng tổng thể khó nhìn khi có nhiều nhánh, retry và điều kiện bù trừ. Cần correlationId, event catalog, dashboard theo workflow và tài liệu hóa các chuyển trạng thái.

### 7.2. Orchestration

Workflow orchestrator lưu trạng thái quy trình và gọi từng bước. Ví dụ:

1. Xác thực đơn hàng.
2. Giữ tồn kho.
3. Gọi thanh toán.
4. Đồng bộ ERP.
5. Phát lệnh giao hàng.
6. Gửi thông báo.

Nếu thanh toán thất bại sau khi giữ tồn kho, workflow có thể gọi bước bù trừ để giải phóng hàng. Nếu ERP tạm ngừng, workflow có thể chờ hoặc đưa bước đồng bộ vào queue, tùy SLA.

Orchestrator không nên chứa toàn bộ logic nghiệp vụ của mọi service. Mỗi bước vẫn thuộc về thành phần chịu trách nhiệm. Workflow quản lý thứ tự và trạng thái; service thực hiện nghiệp vụ và cung cấp kết quả có thể kiểm tra.

### 7.3. Batch orchestration

Batch job cần có lịch, dependency, partition, retry, checkpoint và trạng thái hoàn tất. Scheduler có thể tạo job trên dịch vụ batch hoặc gửi thông điệp đến worker pool. Nếu job chia thành nhiều shard, cần xác định cách phân vùng dữ liệu và tổng hợp kết quả.

Một job chỉ nên được đánh dấu thành công khi tất cả shard bắt buộc đã hoàn tất và kết quả đã được ghi bền vững. Khi một shard lỗi, chỉ chạy lại shard đó nếu dữ liệu và logic hỗ trợ idempotency.

## 8. Quản lý dữ liệu và tính nhất quán

Nhiều mô hình compute thường truy cập cùng dữ liệu. Nếu không định nghĩa quyền sở hữu, các service có thể cùng sửa một bản ghi và tạo race condition.

Nguyên tắc:

- Mỗi miền nghiệp vụ có một nguồn dữ liệu chuẩn (source of truth).
- Các service khác truy cập qua API hoặc event/data contract được kiểm soát.
- Hạn chế nhiều mô hình compute cùng ghi trực tiếp vào một schema nếu không có quy ước transaction và quyền sở hữu.
- Dùng outbox/inbox để phát sự kiện đáng tin cậy cùng thay đổi dữ liệu.
- Dùng idempotency key, unique constraint hoặc conditional write để xử lý trùng.
- Dùng version hoặc sequence number để phát hiện cập nhật cũ.
- Chấp nhận eventual consistency ở nơi nghiệp vụ cho phép và thể hiện trạng thái trung gian cho người dùng.

Ví dụ, Order API sở hữu bảng orders. ERP connector không tự ý cập nhật trực tiếp bảng đó; nó phát ERPOrderSynced hoặc ghi kết quả đồng bộ vào một bounded context riêng. Order service nhận event và cập nhật trạng thái. Cách này tránh hai thành phần cùng sở hữu một bản ghi.

### 8.1. Không chia sẻ filesystem như hợp đồng tích hợp

VM, container và function có thể dùng filesystem với vòng đời khác nhau. Một file trên ổ đĩa local của VM không tự xuất hiện trong container hoặc function. Dùng object storage, file service hoặc volume được quản lý nếu cần chia sẻ dữ liệu. Định nghĩa tên object, version, checksum và retention để các thành phần đọc cùng một dữ liệu.

### 8.2. Tránh dual write

Nếu một thành phần ghi database rồi phát event bằng hai thao tác độc lập, có thể chỉ một thao tác thành công. Dùng transactional outbox khi database hỗ trợ transaction phù hợp. Consumer dùng inbox hoặc idempotency record để xử lý message lặp. Với hệ thống không có transaction chung, thiết kế saga và quy trình đối soát để phát hiện trạng thái lệch.

## 9. Bảo mật xuyên suốt nhiều mô hình compute

Mỗi mô hình compute có cách cấp danh tính khác nhau, nhưng kiến trúc nên dùng nguyên tắc least privilege và danh tính workload riêng.

| Thành phần | Danh tính và quyền cần thiết |
|---|---|
| VM connector | Instance role/service identity chỉ đọc secret, gọi ERP endpoint và ghi queue cần thiết |
| Container service | Service account hoặc workload identity riêng cho database, queue và object storage |
| Serverless function | Execution role chỉ đọc đúng event source, ghi đúng bảng hoặc phát đúng event |
| Batch job | Job identity chỉ đọc input, ghi output và checkpoint |
| CI/CD pipeline | Identity triển khai giới hạn theo môi trường và tài nguyên được phép |

Không chia sẻ một credential quản trị cho mọi mô hình compute. Dùng workload identity hoặc role ngắn hạn nếu nền tảng hỗ trợ. Secret phải được lưu trong secret manager, xoay vòng và không đưa vào image, log hoặc message.

Các kiểm soát khác:

- Mã hóa TLS giữa các thành phần và mã hóa dữ liệu lưu trữ.
- Network segmentation giữa public ingress, application, data và management plane.
- Firewall và security group theo luồng giao tiếp cần thiết.
- Kiểm tra schema và xác thực source của event.
- Audit log cho truy cập dữ liệu và thay đổi quyền.
- Quản lý lỗ hổng OS trên VM, image container, dependency function và runtime batch.
- Phân tách môi trường development, staging và production.
- Hạn chế quyền operator, quyền redrive queue và quyền chạy job thủ công.

Một thành phần được bảo vệ tốt vẫn có thể bị lạm dụng nếu danh tính của thành phần khác có quyền quá rộng. Kiểm tra cả chuỗi quyền từ producer đến consumer và từ CI/CD đến runtime.

## 10. Triển khai và quản lý cấu hình

Nhiều mô hình compute có vòng đời triển khai khác nhau. VM có thể dùng image chuẩn và configuration management; container dùng image registry và rollout; function dùng package hoặc container image; batch job dùng image, template hoặc job definition.

Để quản lý nhất quán:

- Dùng Infrastructure as Code (IaC) cho mạng, identity, queue, event rule, cluster, VM, function và quyền.
- Dùng pipeline riêng hoặc stage riêng cho từng loại artifact nhưng quản lý phiên bản tương thích cùng nhau.
- Đưa cấu hình môi trường vào config store/secret manager, không nhúng vào source code.
- Gắn version, build id và trace metadata vào log.
- Triển khai theo canary, blue/green hoặc rolling update tùy mô hình.
- Có rollback hoặc forward-fix rõ ràng cho schema và event contract.
- Tránh cập nhật thủ công ngoài IaC mà không ghi nhận vào hệ thống quản lý cấu hình.

### 10.1. Thứ tự triển khai phụ thuộc

Một thứ tự triển khai an toàn thường là:

1. Tạo mạng, DNS, identity và secret.
2. Tạo database, queue, event bus, bucket và policy.
3. Triển khai consumer có khả năng đọc cả schema cũ và mới.
4. Triển khai producer phát schema mới nhưng vẫn tương thích.
5. Bật event routing hoặc chuyển traffic từng phần.
6. Theo dõi lỗi, backlog và kết quả nghiệp vụ.
7. Chỉ bỏ schema cũ sau khi không còn producer/consumer sử dụng.

Nếu bật producer mới trước khi consumer sẵn sàng, message có thể bị lỗi hoặc nằm trong DLQ. Nếu xóa queue hoặc schema cũ trước khi consumer đã chuyển đổi, công việc đang chờ có thể không xử lý được.

## 11. Mở rộng và bảo vệ năng lực hệ thống

Mỗi mô hình compute có cách scale riêng:

- VM scale bằng cách tăng kích thước máy hoặc thêm instance qua autoscaling group/VM scale set.
- Container scale bằng replica, HPA hoặc autoscaler của nền tảng.
- Function scale theo invocation và concurrency do nền tảng quản lý.
- Batch scale bằng số job, số shard và tài nguyên cho mỗi job.
- Managed service có quota và giới hạn riêng.

Không nên scale từng thành phần mà không xem xét toàn luồng. Nếu function phát 1.000 request mỗi giây đến database nhưng database chỉ chịu được 200 request mỗi giây, autoscaling của function làm hệ thống kém ổn định hơn.

Cần xác định capacity budget xuyên suốt:

1. Tốc độ sự kiện hoặc request đến.
2. Thông lượng tối đa của từng thành phần.
3. Số connection và request đồng thời đến dependency.
4. Queue depth và tuổi message tối đa.
5. Quota API, database, storage và network.
6. Headroom để chịu lỗi node/zone hoặc một compute pool mất capacity.

Dùng queue để hấp thụ burst, rate limit để giới hạn tốc độ, concurrency cap để bảo vệ dependency và circuit breaker để ngăn gọi liên tục vào dịch vụ đang lỗi. Khi backlog vượt ngưỡng, có thể giảm tốc producer, ưu tiên công việc quan trọng hoặc chuyển một phần workload sang pool khác nếu hợp đồng và dữ liệu cho phép.

### 11.1. Fallback giữa các mô hình compute

Fallback cần được thiết kế trước. Ví dụ, nếu serverless function không thể xử lý file lớn trong giới hạn runtime, nó có thể ghi job vào queue để container worker xử lý. Nếu Spot container node thiếu capacity, worker có thể chờ hoặc chuyển sang On-Demand theo chính sách. Nếu ERP connector trên VM ngừng hoạt động, queue giữ các message cho đến khi connector phục hồi.

Không tự động chạy cùng một tác vụ đồng thời trên hai mô hình compute nếu chưa có idempotency và khóa phân phối. Fallback có thể tạo xử lý trùng, tranh chấp tài nguyên hoặc thứ tự kết quả không xác định. Cần định nghĩa điều kiện kích hoạt, thời gian chờ, nơi lưu trạng thái và cách quay lại đường xử lý bình thường.

## 12. Độ tin cậy và phục hồi sự cố

Trong hệ thống kết hợp, lỗi có thể xảy ra ở bất kỳ lớp nào: VM, node, function, broker, network, database hoặc nhà cung cấp bên ngoài. Thiết kế cần giả định mỗi thành phần có thể tạm thời không sẵn sàng.

Các nguyên tắc:

- **Timeout:** đặt timeout rõ ràng cho mọi lời gọi đồng bộ.
- **Retry:** chỉ retry lỗi có thể phục hồi; dùng backoff và jitter.
- **Idempotency:** đảm bảo xử lý lại không tạo tác dụng phụ trùng.
- **DLQ:** cô lập message lỗi kéo dài để không chặn queue chính.
- **Circuit breaker:** ngừng gọi dependency khi lỗi vượt ngưỡng.
- **Bulkhead:** giới hạn tài nguyên cho từng loại workload để lỗi không lan toàn hệ thống.
- **Health/readiness:** chỉ nhận traffic khi thành phần thực sự sẵn sàng.
- **Checkpoint:** lưu tiến độ cho batch hoặc job dài.
- **Graceful shutdown:** ngừng nhận việc mới và hoàn tất hoặc nhả công việc đang xử lý.
- **Multi-zone/region:** phân tán thành phần theo yêu cầu phục hồi và chi phí.

### 12.1. Sự cố một mô hình compute

| Sự cố | Hành vi cần có |
|---|---|
| VM connector mất kết nối | Queue giữ message; connector được khởi động lại hoặc chuyển sang instance dự phòng |
| Container Pod bị eviction | Deployment tạo Pod mới; message chưa ack được giao lại; state lấy từ kho bền vững |
| Function timeout | Nguồn áp dụng retry hoặc DLQ; idempotency ngăn tác dụng phụ lặp |
| Batch worker bị dừng | Job tiếp tục từ checkpoint hoặc chạy lại shard an toàn |
| Event bus chậm | Theo dõi tuổi sự kiện, retry publish và tránh producer ghi nhận thành công sai |
| Database quá tải | Giới hạn concurrency, giảm tốc consumer và bảo vệ bằng connection pool |
| Private link/VPN mất | Request timeout có giới hạn; queue giữ công việc; cảnh báo kết nối và phục hồi route |

### 12.2. Ranh giới lỗi và mức độ suy giảm

Không phải mọi sự cố đều cần làm toàn bộ hệ thống dừng. Nếu dịch vụ gửi email lỗi, đơn hàng vẫn có thể được ghi nhận và thông báo gửi lại sau. Nếu hệ thống đối soát ban đêm chậm, API bán hàng có thể tiếp tục hoạt động. Nếu payment provider không khả dụng, hệ thống không được đánh dấu đơn hàng là đã thanh toán.

Xác định rõ chức năng cốt lõi, chức năng có thể trì hoãn và chức năng có thể suy giảm. Trạng thái nghiệp vụ phải thể hiện điều đó, ví dụ NOTIFICATION_PENDING hoặc ERP_SYNC_PENDING, để người dùng và vận hành biết công việc còn tồn đọng.

## 13. Quan sát và truy vết xuyên mô hình

Mỗi môi trường compute có log và metric riêng. Nếu không có định danh chung, việc truy tìm một request qua API container, function, queue, VM connector và batch job sẽ khó khăn.

Nên truyền các trường:

- correlationId hoặc traceId cho toàn bộ luồng nghiệp vụ.
- eventId/messageId cho từng sự kiện hoặc message.
- jobId cho công việc dài.
- tenantId nếu hệ thống đa tenant và chính sách cho phép.
- serviceName, runtime, version và environment.
- attempt/retryCount để biết một message đã được thử bao nhiêu lần.

Theo dõi các nhóm chỉ số:

| Nhóm | Metric |
|---|---|
| API/container | Request rate, p95/p99 latency, error rate, replica, CPU/memory |
| VM | CPU/memory/disk, process health, patch state, network connection |
| Function | Invocation, duration, cold start, timeout, throttle, concurrency |
| Queue/event bus | Depth, oldest age, publish/consume rate, retry, DLQ |
| Batch | Job duration, shard completion, checkpoint age, retry và failure |
| Data/dependency | Database latency, connection, storage throughput, API 429/5xx |
| Business | Thời gian từ yêu cầu đến hoàn tất, số đơn ở trạng thái chờ, tỷ lệ hoàn tất |
| Cost | Cost per request/job, compute hours, data transfer, storage và idle capacity |

Dùng distributed tracing xuyên qua HTTP và message khi nền tảng hỗ trợ. Khi chuyển qua queue, đưa trace context vào message header hoặc envelope. Với batch job chạy nhiều giờ, ghi checkpoint và trace/span theo từng shard hoặc giai đoạn thay vì giữ một span khổng lồ.

Cảnh báo theo SLO và backlog, không chỉ theo CPU. Một function có CPU thấp nhưng queue age tăng vẫn có thể vi phạm SLA do dependency chậm. Một VM có CPU cao trong vài phút có thể bình thường nếu công việc batch đang chạy đúng kế hoạch.

## 14. Quản lý chi phí tổng thể

So sánh chi phí theo toàn hệ thống thay vì giá của từng compute riêng lẻ.

| Mô hình | Thành phần chi phí cần tính |
|---|---|
| VM | Instance hours, disk, license, snapshot, network egress và idle capacity |
| Container | CPU/memory requests, node hours, control plane, storage, load balancer và logging |
| Serverless | Invocation, duration, memory, provisioned capacity, event routing và retry |
| Batch | Thời gian job, tài nguyên peak, storage trung gian, checkpoint và thời gian chờ |
| Tích hợp | Queue operations, data transfer, NAT, private link, log, trace và monitoring |

Một thành phần serverless có thể có giá mỗi lần gọi thấp nhưng tạo hàng triệu invocation do fan-out hoặc retry. Một cluster container có thể tốn chi phí node nhàn rỗi nếu không scale down. VM có thể rẻ cho tải ổn định nhưng tốn công vá và quản lý. Batch có thể tiết kiệm nếu chạy đúng cửa sổ và tắt tài nguyên sau khi hoàn tất.

Các biện pháp tối ưu:

- Đo chi phí trên mỗi request hoặc nghiệp vụ hoàn tất.
- Tắt hoặc scale down tài nguyên không dùng khi an toàn.
- Chọn Spot cho batch/worker chịu gián đoạn và giữ capacity ổn định cho thành phần quan trọng.
- Tối ưu kích thước container/function theo profile thực tế.
- Giảm truyền dữ liệu giữa region và giữa các dịch vụ.
- Dùng retention hợp lý cho queue, log, object và checkpoint.
- Phát hiện retry loop và event fan-out ngoài dự kiến.
- Phân bổ chi phí theo service, team, environment và tenant.

Không tối ưu riêng từng thành phần nếu điều đó làm tăng chi phí ở nơi khác. Ví dụ, chuyển xử lý sang function có thể giảm node hours nhưng tăng số lần đọc database và phí event routing. Đánh giá cả đường đi của dữ liệu.

## 15. Quy trình thiết kế một hệ thống kết hợp

Có thể áp dụng các bước sau:

1. **Liệt kê workload:** ghi rõ chức năng, chủ sở hữu, thời gian chạy, tải, tài nguyên và trạng thái.
2. **Phân loại yêu cầu:** xác định latency, throughput, SLA, khả năng gián đoạn, bảo mật và vùng dữ liệu.
3. **Chọn compute:** ghép từng workload với VM, container, function, batch hoặc managed service.
4. **Xác định ranh giới:** quyết định thành phần nào là service, worker, function, connector hoặc job.
5. **Thiết kế hợp đồng:** API, event schema, message, data contract, version và mã lỗi.
6. **Thiết kế luồng dữ liệu:** xác định nguồn dữ liệu chuẩn, nơi lưu file, quyền truy cập và retention.
7. **Chọn cơ chế điều phối:** choreography, workflow orchestrator hoặc scheduler/queue.
8. **Thiết kế độ tin cậy:** timeout, retry, idempotency, DLQ, checkpoint, fallback và graceful shutdown.
9. **Thiết kế mạng và danh tính:** DNS, TLS, private connectivity, workload identity và least privilege.
10. **Đặt capacity và giới hạn:** concurrency, quota, connection pool, queue depth và headroom.
11. **Thiết lập quan sát:** correlation, trace, metric, log và cảnh báo xuyên mô hình.
12. **Tính chi phí:** compute, network, storage, license, managed services và công sức vận hành.
13. **Kiểm thử lỗi:** mô phỏng mất VM, Pod eviction, function timeout, backlog và dependency outage.
14. **Triển khai từng phần:** canary, rollout và rollback theo từng thành phần, theo dõi SLO trước khi mở rộng.

## 16. Ví dụ lựa chọn mô hình theo workload

Một doanh nghiệp có năm workload:

| Workload | Đặc tính | Mô hình đề xuất | Lý do |
|---|---|---|---|
| Order API | Request ngắn, tải biến động, cần rollout liên tục | Container service | Scale ngang, môi trường nhất quán và kiểm soát runtime |
| ERP connector | Phần mềm cũ, cần thư viện native và kết nối mạng riêng | VM | Duy trì môi trường tương thích trong khi xây kế hoạch hiện đại hóa |
| Image thumbnail | Tác vụ ngắn, phát sinh theo upload | Serverless function | Kích hoạt theo sự kiện, tự mở rộng theo nhu cầu |
| Video transcoding | Tác vụ dài, CPU/GPU cao, có checkpoint | Container worker hoặc batch compute | Kiểm soát tài nguyên, xử lý job dài và retry theo shard |
| Nightly reconciliation | Chạy theo lịch, đọc nhiều dữ liệu và kết thúc sau khi hoàn thành | Managed batch | Lập lịch, phân bổ capacity và quản lý job hữu hạn |

Các lựa chọn có thể thay đổi theo tải và giới hạn nền tảng. Nếu thumbnail cần thư viện native lớn hoặc xử lý vượt timeout, chuyển sang container worker. Nếu ERP connector đã được container hóa và không cần quyền OS, có thể đưa vào nền tảng container. Nếu transcoding có workload ổn định, cân nhắc pool compute chuyên dụng thay vì cấp phát động mỗi job.

## 17. Kịch bản kiểm chứng trước production

Thử nghiệm trong staging hoặc môi trường tương đương:

1. **Kiểm tra đường đi bình thường:** gửi một yêu cầu và truy vết qua API, event bus, function, worker/VM connector và kho dữ liệu.
2. **Kiểm tra hợp đồng:** phát event schema mới và xác nhận consumer cũ xử lý tương thích; kiểm tra version không hỗ trợ.
3. **Kiểm tra duplicate:** phát lại message và event; xác nhận idempotency ngăn tác dụng phụ trùng.
4. **Kiểm tra timeout:** làm một dependency chậm hơn timeout; xác nhận retry có giới hạn và circuit breaker hoạt động.
5. **Kiểm tra mất VM:** dừng connector thử nghiệm; xác nhận queue giữ công việc và connector phục hồi có thể tiếp tục.
6. **Kiểm tra Pod eviction:** xóa Pod worker trong staging; xác nhận message chưa ack được giao lại và state không mất.
7. **Kiểm tra function throttle:** giới hạn concurrency hoặc tạo burst; xác nhận queue hấp thụ tải và downstream không bị quá tải.
8. **Kiểm tra batch checkpoint:** dừng một shard giữa chừng; xác nhận job tiếp tục từ checkpoint hoặc chạy lại an toàn.
9. **Kiểm tra mạng:** ngắt private link/VPN thử nghiệm; xác nhận timeout, cảnh báo và backlog được quản lý.
10. **Kiểm tra fallback:** làm một compute pool không khả dụng; xác nhận workload được chờ, chuyển pool hoặc suy giảm đúng chính sách.
11. **Kiểm tra quan sát:** tìm correlationId và eventId trên dashboard/log/trace của tất cả thành phần.
12. **Kiểm tra chi phí:** so sánh cost per request/job với mục tiêu và xác nhận không có tài nguyên giữ lại ngoài dự kiến.

Ghi lại thời gian phục hồi, số message retry, thời gian backlog được xóa và ảnh hưởng đến SLO. Không thử sự cố gây gián đoạn trên production nếu chưa có kế hoạch kiểm soát và quy trình khôi phục.

## 18. Sự cố thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| API thành công nhưng tác vụ nền không chạy | Outbox publisher lỗi, rule event sai hoặc queue không nhận message | Kiểm tra outbox age, publish result, event rule và queue metrics |
| Function tăng tải làm database lỗi | Concurrency không giới hạn hoặc connection pool quá lớn | Giới hạn concurrency, dùng proxy/pool và đo database connections |
| Worker container không truy cập ERP trên VM | DNS, route, firewall, TLS hoặc private link sai | Kiểm tra đường mạng hai chiều, security group và certificate |
| Batch job chạy lại từ đầu sau lỗi | Không có checkpoint hoặc checkpoint không bền vững | Kiểm tra vị trí checkpoint, shard id và idempotency |
| Sự kiện được xử lý hai lần ở hai mô hình compute | Fallback đồng thời hoặc at-least-once delivery | Dùng idempotency key chung và cơ chế claim công việc có lease |
| Dữ liệu giữa service không nhất quán | Nhiều thành phần cùng ghi một nguồn dữ liệu hoặc dual write | Xác định source of truth, outbox/inbox và quyền ghi |
| Chi phí tăng sau khi tách service | Fan-out, network egress, logging hoặc idle capacity tăng | Phân tích cost theo luồng nghiệp vụ và từng thành phần |
| Khó truy vết request xuyên hệ thống | Thiếu correlationId hoặc trace context qua queue | Chuẩn hóa metadata và truyền trace header/message attribute |
| Rollout gây lỗi schema | Producer mới phát event mà consumer cũ không hiểu | Dùng backward-compatible schema và triển khai consumer trước |
| Fallback không hoạt động khi pool mất | Chưa cấu hình policy, quyền hoặc capacity dự phòng | Thử failover, kiểm tra quota, identity và điều kiện kích hoạt |

## 19. Checklist thiết kế và vận hành

- [ ] Phân loại workload theo thời gian chạy, tải, tài nguyên, trạng thái và khả năng gián đoạn.
- [ ] Chọn VM, container, serverless, batch hoặc managed service theo đặc tính thực tế.
- [ ] Mỗi thành phần có trách nhiệm, chủ sở hữu và ranh giới dữ liệu rõ ràng.
- [ ] Định nghĩa API, event, message và data contract có version.
- [ ] Chọn đồng bộ hoặc bất đồng bộ theo SLA và thời gian xử lý.
- [ ] Lưu trạng thái nghiệp vụ trong kho bền vững.
- [ ] Dùng outbox/inbox, idempotency và checkpoint ở nơi cần thiết.
- [ ] Đặt timeout, retry, DLQ, circuit breaker và graceful shutdown.
- [ ] Quản lý DNS, TLS, network segmentation và private connectivity.
- [ ] Cấp workload identity riêng với quyền tối thiểu.
- [ ] Quản lý hạ tầng và cấu hình bằng IaC, pipeline có version và rollback.
- [ ] Giới hạn concurrency, connection, quota và queue backlog.
- [ ] Theo dõi correlationId, trace, metric, log và SLO xuyên mô hình.
- [ ] Kiểm thử mất VM, Pod eviction, function timeout, batch failure và dependency outage.
- [ ] Đo chi phí trên mỗi nghiệp vụ hoàn tất, bao gồm network và vận hành.
- [ ] Có runbook cho fallback, replay, DLQ và phục hồi dữ liệu.

## Kết luận

Phối hợp nhiều mô hình compute cho phép mỗi workload dùng môi trường phù hợp với vòng đời, tài nguyên và SLA của nó. Kiến trúc chỉ hoạt động ổn định khi các thành phần có hợp đồng rõ ràng, trạng thái được lưu bền vững, giao tiếp được điều phối bằng API, queue, event hoặc workflow, và danh tính cùng quan sát được quản lý xuyên suốt. Hãy kiểm chứng cả đường đi bình thường lẫn tình huống một compute pool hoặc dependency mất khả năng phục vụ, sau đó đánh giá chi phí trên toàn bộ luồng nghiệp vụ trước khi đưa hệ thống vào production.
