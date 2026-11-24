# Thiết kế stateless để có thể thay thế máy tự động

Trong môi trường cloud, một máy ảo hoặc container có thể bị thay thế khi autoscaling, triển khai phiên bản mới, bảo trì host hoặc phục hồi sau sự cố. Nếu ứng dụng phụ thuộc vào dữ liệu chỉ tồn tại trên máy đó, việc thay thế có thể làm mất phiên người dùng, công việc đang xử lý hoặc cấu hình cần thiết để khởi động. Thiết kế stateless giúp compute instance có thể được tạo mới và loại bỏ tự động mà không làm mất trạng thái nghiệp vụ.

Trong phạm vi CLOUD_CORE_SERVICES_COMPUTE, bài học đặt thiết kế stateless trong bối cảnh các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless. Khi compute được xem là tài nguyên có thể thay thế, hệ thống có thể mở rộng theo tải, triển khai thường xuyên và phục hồi sau lỗi với ít thao tác thủ công hơn. Điều này đòi hỏi trạng thái phải được đặt ở nơi có vòng đời phù hợp, danh tính và cấu hình phải được cấp lại an toàn, còn ứng dụng phải chịu được request, job hoặc kết nối bị gián đoạn.

Sau bài học, bạn có thể:

- Giải thích stateless ở cấp compute và phân biệt với việc ứng dụng hoàn toàn không có trạng thái.
- Xác định dữ liệu nào có thể để tạm trên instance và dữ liệu nào phải nằm ngoài vòng đời máy.
- Thiết kế session, file, job và cấu hình để backend có thể được thay thế.
- Dùng image bất biến, bootstrap tự động, workload identity và service discovery để tạo máy mới.
- Xử lý request retry, message redelivery, graceful shutdown, drain và idempotency.
- Kiểm thử autoscaling, rolling replacement và phục hồi sau khi một instance bị xóa đột ngột.

## 1. Stateless nghĩa là gì?

Một compute instance được thiết kế stateless khi việc thay thế instance không làm mất dữ liệu hoặc trạng thái nghiệp vụ duy nhất cần thiết để hệ thống tiếp tục hoạt động. Instance có thể giữ dữ liệu tạm thời trong RAM hoặc local disk để tăng tốc, nhưng dữ liệu đó có thể được tạo lại hoặc lấy lại từ một nguồn có vòng đời độc lập.

Stateless không có nghĩa ứng dụng không xử lý trạng thái. Một ứng dụng thương mại điện tử vẫn cần biết người dùng đã đăng nhập, giỏ hàng có gì và đơn hàng đang ở bước nào. Điểm khác biệt là trạng thái này không chỉ tồn tại trong bộ nhớ của một VM hoặc container cụ thể.

Ví dụ:

- API nhận request, đọc session từ kho dùng chung, ghi đơn hàng vào database và trả response. VM API có thể bị thay thế mà đơn hàng vẫn tồn tại.
- Worker nhận message từ queue, xử lý giao dịch idempotent và ghi kết quả vào database. Nếu worker bị dừng, message có thể được giao lại cho worker khác.
- Web frontend lấy nội dung từ object storage hoặc CDN thay vì giữ file upload duy nhất trên ổ đĩa local của VM.
- Container được tạo từ image đã version hóa, lấy cấu hình từ hệ thống quản lý cấu hình và secret manager khi khởi động.

### Stateless và stateful

| Tiêu chí | Compute stateless | Compute stateful |
|---|---|---|
| Trạng thái nghiệp vụ | Lưu ở database, object storage, queue hoặc shared store | Có thể nằm trong RAM hoặc disk riêng của instance |
| Thay instance | Có thể tạo máy mới rồi đưa vào phục vụ | Cần chuyển, đồng bộ hoặc phục hồi trạng thái |
| Autoscaling | Dễ thêm/bớt instance nếu dependency đủ năng lực | Cần quản lý membership, replication, shard hoặc quorum |
| Rolling deployment | Có thể thay từng instance theo health và readiness | Cần quy trình chuyển trạng thái và tương thích dữ liệu |
| Failover | Instance khác có thể tiếp tục xử lý | Có thể cần leader election, replication hoặc recovery |
| Rủi ro chính | Shared dependency trở thành điểm quan trọng | Mất dữ liệu cục bộ hoặc trạng thái không nhất quán |

Một hệ thống có thể kết hợp cả hai. Ví dụ API stateless chạy trên nhiều VM, còn database là stateful service có replication và backup. Mục tiêu là chọn đúng nơi lưu trạng thái, không cố biến mọi thành phần thành stateless bằng mọi giá.

## 2. Phân loại trạng thái trước khi thiết kế

Bước đầu tiên là lập danh sách mọi loại dữ liệu mà ứng dụng đọc, tạo hoặc thay đổi. Không phải dữ liệu nào cũng cần cùng một loại lưu trữ.

| Loại trạng thái | Ví dụ | Nơi lưu phù hợp | Có thể mất khi thay máy? |
|---|---|---|---|
| Dữ liệu nghiệp vụ lâu dài | Đơn hàng, thanh toán, hồ sơ | Database hoặc dịch vụ dữ liệu bền vững | Không |
| File người dùng | Ảnh, tài liệu, file export | Object storage hoặc shared file storage | Không |
| Session | Đăng nhập, giỏ hàng, wizard | Shared session store hoặc token được bảo vệ | Không, trong thời hạn phiên |
| Công việc đang chờ | Email, xử lý ảnh, đồng bộ | Durable queue hoặc workflow engine | Không; cần giao lại khi worker mất |
| Cache | Kết quả truy vấn, token metadata có thể làm mới | Cache dùng chung hoặc cache cục bộ | Có thể, nếu tạo lại an toàn |
| Temporary file | File trung gian, scratch data | Ephemeral disk hoặc temporary volume | Có thể |
| Cấu hình | Endpoint, feature flag, tham số runtime | Config service hoặc versioned config artifact | Không phụ thuộc instance |
| Secret | Password DB, API credential, certificate | Secret manager hoặc hệ thống quản lý khóa | Không nhúng duy nhất trong image |
| Trạng thái tiến trình | Thread, biến trong RAM, connection pool | Tái tạo khi process khởi động | Có thể; phải có cơ chế phục hồi |
| Dữ liệu quan sát | Log, metric, trace | Telemetry backend tập trung | Không giữ duy nhất trên máy |

### Câu hỏi kiểm kê

Với từng dữ liệu, hãy trả lời:

1. Đây là dữ liệu nghiệp vụ, cache hay dữ liệu tạm?
2. Nguồn dữ liệu có thẩm quyền (source of truth) nằm ở đâu?
3. Khi instance mất đột ngột, dữ liệu có thể tạo lại không?
4. Nếu không thể tạo lại, RPO và cơ chế backup/replication là gì?
5. Instance khác có thể đọc hoặc tiếp tục xử lý không?
6. Dữ liệu có cần transaction, locking, ordering hoặc consistency đặc biệt không?
7. Ai được phép truy cập và thời gian lưu giữ là bao lâu?

Nếu một file hoặc record quan trọng chỉ có trên local disk của VM, instance đó chưa thể thay thế an toàn.

## 3. Tách compute khỏi dữ liệu bền vững

Compute nên thực hiện xử lý và có thể được thay thế; dữ liệu quan trọng nên nằm ở dịch vụ có vòng đời độc lập với instance.

### Database

Database giữ dữ liệu có cấu trúc và trạng thái giao dịch. Nhiều API instance có thể kết nối cùng database hoặc cụm database theo chính sách truy cập.

Cần thiết kế:

- Database endpoint ổn định qua DNS hoặc managed endpoint.
- Connection pool có giới hạn trên mỗi instance và toàn fleet.
- Transaction và isolation level phù hợp nghiệp vụ.
- Backup, point-in-time recovery và kiểm thử restore.
- Replication/failover cùng mục tiêu RPO/RTO.
- Migration schema tương thích với phiên bản ứng dụng đang chạy đồng thời.

Không nên lưu file database hoặc transaction log duy nhất trên ổ đĩa tạm của VM ứng dụng. Với database tự quản lý, storage, replication và quy trình phục hồi phải được thiết kế như một hệ thống stateful riêng.

### Object storage

Object storage phù hợp với file upload, ảnh, tài liệu, artifact và dữ liệu export. Backend lưu object theo key và metadata trong database thay vì ghi file duy nhất vào filesystem của container.

Ví dụ luồng upload:

1. API xác thực người dùng và kiểm tra quyền.
2. API cấp URL upload tạm thời hoặc nhận file rồi ghi object.
3. Object storage lưu nội dung bền vững.
4. Database lưu object key, owner, checksum và trạng thái xử lý.
5. Worker có thể đọc object từ bất kỳ instance nào.

Nếu object và record database được ghi ở hai hệ thống riêng, cần xử lý trường hợp một thao tác thành công còn thao tác kia thất bại. Có thể dùng trạng thái pending, outbox/event, retry và job đối soát.

### Queue và workflow engine

Queue tách thời điểm gửi công việc khỏi thời điểm worker xử lý. Worker có thể dừng và được thay thế nếu message được giữ bền vững và cơ chế acknowledgement/redelivery được cấu hình đúng.

Cần xác định:

- Visibility timeout hoặc lease của message.
- Retry policy và backoff.
- Dead-letter queue cho message thất bại nhiều lần.
- Idempotency để message giao lại không tạo tác động trùng.
- Ordering và partition key nếu thứ tự là yêu cầu nghiệp vụ.
- Cách lưu checkpoint cho job dài.

### Cache

Cache giúp giảm tải database và latency, nhưng cần xác định dữ liệu nào có thể tái tạo. Cache miss sau khi thay instance có thể làm tăng tải đột ngột lên database. Cần warm-up, TTL, eviction và bảo vệ trước cache stampede khi phù hợp.

Không dùng cache làm source of truth nếu dữ liệu phải tồn tại sau eviction, restart hoặc failover, trừ khi hệ thống cache được thiết kế rõ ràng như kho dữ liệu bền vững theo semantics của dịch vụ.

## 4. Quản lý session mà không phụ thuộc một máy

Một ứng dụng web có thể dùng session trong RAM của backend. Khi load balancer gửi request tiếp theo đến máy khác, backend mới không tìm thấy session. Session affinity có thể giảm triệu chứng nhưng vẫn phụ thuộc máy cũ còn sống.

Các lựa chọn phổ biến:

### Shared session store

Lưu session trong Redis hoặc database có khả năng sẵn sàng phù hợp. Mỗi backend nhận session ID từ cookie, đọc trạng thái từ store và ghi thay đổi trở lại.

Ưu điểm:

- Backend có thể thay thế lẫn nhau.
- Rolling deployment và autoscaling dễ hơn.
- Instance mất không làm mất session nếu shared store còn khả dụng.

Điểm cần quản lý:

- TTL, eviction và dung lượng.
- Network latency, timeout và connection pool.
- HA, backup hoặc persistence theo yêu cầu.
- Serialization/schema version trong lúc rolling deployment.
- Mã hóa và quyền truy cập session.
- Xử lý store outage mà không tạo retry storm.

### Signed hoặc encrypted client-side token

Một token có chữ ký hoặc mã hóa có thể mang một lượng trạng thái nhỏ. Backend xác minh chữ ký và thời hạn mà không cần truy vấn session store cho mọi request.

Cần lưu ý:

- Chữ ký bảo vệ tính toàn vẹn nhưng không che nội dung; muốn bảo mật nội dung phải dùng mã hóa.
- Token thường khó thu hồi ngay trước khi hết hạn nếu không có deny-list hoặc kiểm tra trạng thái bổ sung.
- Không đưa dữ liệu nhạy cảm hoặc payload lớn vào token.
- Quản lý khóa ký, rotation, audience, issuer và expiry.
- Authorization vẫn phải được kiểm tra ở phía server.

### Không dựa vào sticky session làm nơi lưu trạng thái duy nhất

Sticky session có thể là giải pháp chuyển tiếp cho ứng dụng cũ, nhưng backend vẫn có thể bị restart, scale-in hoặc host failure. Nếu yêu cầu giữ phiên, hãy externalize trạng thái hoặc thiết kế token phù hợp.

## 5. Thiết kế request và job có thể retry an toàn

Trong hệ thống phân tán, client hoặc queue có thể gửi lại một thao tác khi timeout xảy ra. Server có thể đã thực hiện xong nhưng response bị mất; lần retry có thể tạo giao dịch trùng nếu thao tác không idempotent.

**Idempotency** nghĩa là thực hiện cùng một yêu cầu nhiều lần với cùng khóa có hiệu quả nghiệp vụ tương đương thực hiện một lần, trong phạm vi và thời gian được định nghĩa.

### Idempotency key

Ví dụ, client gửi yêu cầu tạo thanh toán với một idempotency key duy nhất. Server lưu key cùng trạng thái và kết quả giao dịch. Nếu request được gửi lại, server trả kết quả đã ghi nhận thay vì tạo khoản thanh toán mới.

Luồng khái niệm:

~~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API instance
    participant DB as Durable database
    C->>A: POST /payments + idempotency key
    A->>DB: Kiểm tra key và tạo operation
    DB-->>A: Kết quả đã commit
    A-->>C: Response
    Note over C,A: Response có thể bị mất trên mạng
    C->>A: Retry cùng idempotency key
    A->>DB: Đọc operation theo key
    DB-->>A: Trả kết quả đã lưu
    A-->>C: Cùng kết quả, không tạo thanh toán mới
~~~~

Cần đặt unique constraint hoặc transaction để hai request đồng thời không cùng tạo operation. Key cần gắn với principal/tenant và loại operation để tránh va chạm hoặc lạm dụng.

### Worker và message redelivery

Worker có thể nhận một message, xử lý rồi bị dừng trước khi acknowledgement. Queue sẽ giao message lại cho worker khác. Vì vậy:

- Ghi nhận message ID hoặc business operation ID đã xử lý.
- Dùng transaction để cập nhật dữ liệu và trạng thái xử lý khi có thể.
- Thiết kế side effect bên ngoài có idempotency key.
- Ack message sau khi kết quả đã được ghi bền vững.
- Giới hạn retry và chuyển message độc vào dead-letter queue.
- Không giả định message chỉ được giao đúng một lần trừ khi hệ thống và semantics cụ thể bảo đảm điều đó.

### Outbox pattern

Khi ứng dụng cần ghi database và phát event, hai thao tác độc lập có thể không cùng thành công. Outbox pattern ghi thay đổi nghiệp vụ và event vào cùng transaction database; một publisher riêng đọc outbox rồi gửi message. Publisher có thể gửi lặp nên consumer vẫn cần idempotent.

## 6. Làm cho instance có thể tạo lại: immutable image và bootstrap

Một instance thay thế cần có thể được tạo từ image và cấu hình đã version hóa, không cần người vận hành đăng nhập để cài từng gói hoặc sửa file thủ công.

### Golden image hoặc container image

Image nên chứa:

- Hệ điều hành hoặc runtime nền đã được vá theo quy trình.
- Dependencies và agent cần thiết.
- Ứng dụng hoặc artifact có version rõ ràng.
- User/group và cấu hình bảo mật mặc định.
- Cơ chế startup, health check và telemetry.

Không bake secret, private key cá nhân hoặc credential dài hạn vào image. Image nên được build trong pipeline, quét lỗ hổng, ký hoặc xác minh nguồn gốc khi nền tảng hỗ trợ, sau đó phát hành bằng immutable version hoặc digest.

### Bootstrap

Khi VM hoặc container được tạo:

1. Nền tảng gán danh tính workload.
2. Bootstrap đọc cấu hình môi trường từ nguồn được phép.
3. Secret được lấy qua identity và secret manager.
4. Ứng dụng khởi động với phiên bản xác định.
5. Agent đăng ký telemetry và health.
6. Instance chỉ nhận traffic sau khi readiness thành công.

Bootstrap phải có thể chạy lại hoặc phát hiện bước đã hoàn thành. Nếu script chạy hai lần, không được tạo tài khoản trùng, ghi đè dữ liệu quan trọng hoặc thay đổi trạng thái ngoài ý muốn.

### Infrastructure as Code

Dùng IaC để định nghĩa VM template, launch template, container deployment, network, role, storage và autoscaling. Cấu hình được review và version hóa giúp instance thay thế có cùng baseline.

Tránh cấu hình drift do sửa tay trên một máy. Nếu cần sửa khẩn cấp, ghi nhận thay đổi rồi đưa vào source of truth để máy tạo mới cũng nhận cấu hình đúng.

Ví dụ bootstrap dạng khái niệm:

~~~~yaml
compute_template:
  image: orders-api:1.8.4
  instance_profile: orders-api-runtime
  user_data:
    config_source: config/orders/production
    secret_source: secret/orders-api
    startup_command: /opt/orders/bin/start
  health:
    startup_path: /health/startup
    readiness_path: /health/ready
  lifecycle:
    replace_on_image_change: true
~~~~

Đây là YAML minh họa, không phải schema dùng trực tiếp cho một cloud provider cụ thể. Cần ánh xạ sang launch template, instance group, VM scale set hoặc cấu hình orchestrator của nền tảng đang dùng.

## 7. Danh tính và cấu hình phải đi theo workload

Một instance mới có thể có instance ID, IP hoặc hostname khác. Ứng dụng không nên dựa vào danh tính máy cố định để truy cập dịch vụ.

### Workload identity

Dùng instance role, managed identity, service account hoặc workload federation để cấp quyền cho máy mới. Quyền nên được gắn theo vai trò ứng dụng và phạm vi tài nguyên cần thiết.

Ví dụ:

- orders-api chỉ đọc secret kết nối database và ghi event đơn hàng.
- invoice-worker chỉ đọc queue hóa đơn và ghi object vào bucket hóa đơn.
- reporting-job chỉ đọc dữ liệu đã tổng hợp và ghi báo cáo.

Không sao chép access key dài hạn từ máy cũ sang máy mới. Không dùng một role quản trị rộng cho toàn bộ fleet chỉ để bootstrap thuận tiện.

### Configuration

Cấu hình có thể gồm endpoint database, feature flag, log level, region, giới hạn concurrency và tham số runtime. Cần phân biệt:

- Cấu hình theo môi trường: development, staging, production.
- Cấu hình theo workload role: API, worker, scheduler.
- Secret: password, token, private key và credential.
- Runtime dynamic config: thay đổi có thể được tải lại mà không cần rebuild image.

Cấu hình phải có version hoặc audit trail và được kiểm tra trước khi rollout. Secret cần encryption, access control, rotation và log truy cập.

### Service discovery

Instance thay thế có thể có IP mới. Các thành phần khác nên tìm dịch vụ qua DNS, service registry, load balancer hoặc endpoint được quản lý, thay vì hardcode địa chỉ máy.

Đối với outbound allow-list, dùng NAT hoặc egress gateway có địa chỉ ổn định nếu đối tác yêu cầu. Không dựa vào public IP động của từng VM làm danh tính lâu dài.

## 8. Health check, readiness và lifecycle của instance

Một instance mới không nên nhận traffic ngay khi VM ở trạng thái running. Hệ điều hành có thể đã boot nhưng ứng dụng còn đang tải cấu hình, lấy secret, warm cache hoặc kết nối dependency.

### Ba trạng thái cần phân biệt

- **Startup:** ứng dụng đã hoàn thành khởi tạo ban đầu chưa?
- **Readiness:** ứng dụng có thể nhận request mới một cách an toàn không?
- **Liveness:** tiến trình có còn hoạt động và có thể tiếp tục, hay cần restart?

Readiness phải phản ánh khả năng phục vụ của instance. Nếu một dependency tùy chọn bị lỗi, không nhất thiết phải đánh dấu toàn bộ API not-ready; nếu database bắt buộc không truy cập được, có thể cần rút instance khỏi traffic tùy semantics của ứng dụng.

### Vòng đời thay thế

~~~~mermaid
flowchart TD
    A[Tạo instance mới từ image] --> B[Bootstrap config và identity]
    B --> C[Start application]
    C --> D[Startup probe thành công]
    D --> E[Readiness thành công]
    E --> F[Đăng ký vào backend pool]
    F --> G[Phục vụ traffic]
    G --> H[Nhận lệnh drain hoặc terminate]
    H --> I[Đánh dấu not-ready]
    I --> J[Ngừng nhận request mới]
    J --> K[Hoàn tất request/job đang chạy]
    K --> L[Flush và đóng kết nối]
    L --> M[Terminate instance]
~~~~

### Graceful shutdown

Khi nhận tín hiệu dừng:

1. Ngừng nhận request mới hoặc message mới.
2. Đánh dấu not-ready để load balancer/orchestrator rút instance khỏi backend.
3. Chờ connection draining trong giới hạn được cấp.
4. Hoàn tất request đang chạy hoặc hủy theo timeout.
5. Với worker, ngừng nhận message mới và hoàn tất hoặc trả lại lease.
6. Flush dữ liệu cần thiết, đóng connection pool và ghi log cuối.
7. Thoát trước khi grace period hết.

Không thể dựa hoàn toàn vào graceful shutdown vì host có thể mất nguồn đột ngột. Mọi dữ liệu quan trọng phải được ghi bền vững trước khi xác nhận công việc hoàn tất.

## 9. Autoscaling và thay thế máy tự động

Autoscaling thêm hoặc bớt instance dựa trên metric, lịch hoặc dự báo. Thiết kế stateless giúp mỗi instance mới có thể tham gia fleet mà không cần chuyển trạng thái cục bộ.

### Scale-out

Khi tải tăng:

- Autoscaler tạo instance từ template/image đã kiểm thử.
- Bootstrap cấp identity và cấu hình.
- Startup/readiness kiểm tra ứng dụng.
- Load balancer thêm backend healthy.
- Instance bắt đầu nhận traffic.
- Dashboard theo dõi throughput, latency, errors và saturation.

Cần tính thời gian từ lúc quyết định scale đến khi instance thực sự ready. Nếu khởi động mất vài phút, cần headroom hoặc capacity dự phòng để chịu spike.

### Scale-in

Khi tải giảm:

- Autoscaler chọn instance cần loại.
- Instance được deregister hoặc đánh dấu draining.
- Không nhận request mới.
- Request/job đang chạy được hoàn tất hoặc chuyển tiếp an toàn.
- Local cache và dữ liệu tạm có thể bị bỏ.
- Instance được terminate.

Không chọn instance chỉ dựa trên CPU thấp nếu nó đang giữ kết nối dài hạn hoặc job quan trọng. Cần phối hợp lifecycle hook, drain timeout và cơ chế queue/lease.

### Tránh scale storm

Nếu tất cả instance mới cùng khởi động, chúng có thể đồng loạt tải cache, mở connection database hoặc lấy secret, gây tải đột biến lên dependency. Dùng jitter, giới hạn concurrency bootstrap, connection pool hợp lý và warm-up theo đợt.

## 10. Thiết kế theo VM, container và serverless

| Mô hình | Cách triển khai stateless | Điểm cần chú ý |
|---|---|---|
| VM/instance group | Image bất biến, launch template, external database/object storage, load balancer và autoscaling | Bootstrap, local disk, IP thay đổi, instance lifecycle và capacity |
| Container/orchestrator | Image theo digest, Pod có thể reschedule, persistent data ở service riêng, ConfigMap/Secret hoặc secret manager | Namespace, volume lifecycle, readiness, termination grace period, requests/limits |
| Serverless function | Mỗi invocation có thể chạy trên execution environment mới hoặc được tái sử dụng; trạng thái nghiệp vụ ở database/queue/object storage | Không giả định RAM/local temp tồn tại giữa invocation; xử lý retry, concurrency và timeout |
| Managed application platform | Artifact và cấu hình được khai báo, platform thay instance theo health và policy | Hiểu rõ platform giữ dữ liệu nào, lifecycle hook và giới hạn runtime |

### VM example

Một fleet API chạy trên nhiều VM sau load balancer. Mỗi VM được tạo từ cùng image, nhận role riêng, tải config và secret khi boot, rồi kết nối database managed. File upload nằm ở object storage. Khi VM lỗi, autoscaling group tạo VM mới và load balancer chỉ thêm máy sau khi readiness thành công.

### Container example

Kubernetes Deployment chạy nhiều replica. Pod không giữ dữ liệu nghiệp vụ trên writable layer; session ở shared store, file ở object storage, job ở queue. Pod có readiness probe và termination grace period. Khi node bị drain, Pod được tạo lại ở node khác.

Ví dụ cấu hình minh họa:

~~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: api
          image: registry.example/orders-api:1.8.4
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
~~~~

Đây là ví dụ tối giản. Production còn cần startup/liveness phù hợp, securityContext, secret injection, disruption budget, rollout strategy, service account và observability.

### Serverless example

Function xử lý ảnh nhận event chứa object key, đọc file từ object storage, xử lý rồi ghi kết quả trở lại storage và cập nhật database. Function không lưu kết quả duy nhất trong RAM sau invocation. Nếu nền tảng retry event, idempotency key hoặc trạng thái job giúp tránh xử lý trùng.

## 11. Xử lý dữ liệu tạm và local disk

Stateless không yêu cầu cấm hoàn toàn local disk. Local disk hữu ích cho cache, scratch file, temporary extraction và dữ liệu có thể tái tạo.

Quy tắc lựa chọn:

- Dữ liệu tạm phải có TTL hoặc quy trình dọn.
- File cần chia sẻ giữa instance phải nằm ở object/shared storage.
- Không lưu upload duy nhất, database file hoặc transaction quan trọng trên ephemeral disk.
- Với batch job, checkpoint phải được ghi ra nơi bền vững theo chu kỳ.
- Đặt giới hạn dung lượng và theo dõi disk pressure.
- Khi terminate, không cần sao chép cache nếu có thể warm lại từ source of truth.

Nếu cần persistent volume gắn với một workload stateful, hãy quản lý vòng đời volume độc lập và xác định quy trình detach/attach, fencing và recovery. Đừng giả định persistent volume có thể được mount đồng thời bởi nhiều node nếu storage class không hỗ trợ.

## 12. Đồng bộ và phối hợp giữa nhiều instance

Khi nhiều instance cùng xử lý, các thao tác cần phối hợp không thể dựa vào biến trong RAM của một máy.

### Distributed lock và lease

Có thể dùng distributed lock hoặc lease để chọn một worker thực hiện tác vụ đơn lẻ. Lock cần TTL/lease, cơ chế gia hạn và xử lý client bị treo. Với tài nguyên quan trọng, dùng fencing token hoặc version tăng dần để ngăn một worker cũ tiếp tục ghi sau khi lease hết hạn và worker mới đã tiếp quản.

Không giữ lock lâu hơn cần thiết. Nếu tác vụ có thể chia nhỏ và idempotent, queue/partition thường đơn giản hơn một global lock.

### Leader election

Một số tác vụ như scheduler hoặc controller cần một leader tại một thời điểm. Leader election phải dùng cơ chế phối hợp có consistency phù hợp, lease timeout và fencing. Không dùng biến static trong process hoặc file local làm cơ chế leader duy nhất khi có nhiều instance.

### Cache invalidation

Cache cục bộ có thể khác nhau giữa instance. Nếu dữ liệu thay đổi cần phản ánh nhanh, dùng TTL phù hợp, event invalidation hoặc shared cache. Không giả định cache của mọi máy luôn đồng nhất.

### Giới hạn connection

Nếu có 20 instance, mỗi instance mở tối đa 50 connection database, tổng số connection tiềm năng là 1.000. Database phải đủ capacity hoặc pool cần được giới hạn theo toàn fleet. Scale compute có thể làm quá tải dependency dù từng instance vẫn khỏe.

## 13. Triển khai phiên bản mới và thay thế dần

Immutable deployment giúp tạo instance mới với image mới rồi thay instance cũ theo chiến lược có kiểm soát.

### Rolling replacement

Thay từng nhóm instance:

1. Tạo instance mới.
2. Đợi startup và readiness.
3. Đưa instance mới vào backend pool.
4. Drain instance cũ.
5. Chờ request/job kết thúc.
6. Terminate instance cũ.
7. Tiếp tục nhóm tiếp theo.

Cần bảo đảm capacity còn đủ trong lúc cả phiên bản cũ và mới cùng chạy.

### Blue/green

Dựng fleet xanh với phiên bản mới, kiểm tra và chuyển traffic từ fleet xanh dương sang fleet xanh. Rollback bằng cách chuyển traffic về fleet cũ nếu vẫn còn tương thích.

### Schema migration tương thích

Trong thời gian rolling deploy, phiên bản cũ và mới có thể cùng truy cập database. Dùng chiến lược expand-and-contract:

1. Thêm schema/field mới theo cách phiên bản cũ vẫn hoạt động.
2. Deploy ứng dụng mới có thể đọc/ghi cấu trúc mới.
3. Chuyển dữ liệu hoặc backfill.
4. Xác minh mọi instance đã dùng cấu trúc mới.
5. Sau một giai đoạn an toàn, loại bỏ field hoặc cấu trúc cũ.

Không triển khai migration phá hủy trước khi mọi instance cũ đã ngừng dùng schema đó.

## 14. Bảo mật trong mô hình stateless

Instance thay thế cần nhận đúng quyền và secret mà không mang theo credential cũ.

- Dùng workload identity hoặc instance role thay vì key dài hạn trong image.
- Giới hạn IAM theo action và resource; không cấp quyền quản trị toàn account.
- Lấy secret lúc runtime qua secret manager và truyền qua kênh bảo mật.
- Không ghi secret vào log, user data công khai, image layer hoặc metadata không được bảo vệ.
- Xoay vòng credential và hỗ trợ phiên bản secret trong giai đoạn rollout.
- Dùng TLS cho kết nối đến database, cache, queue và object storage khi dịch vụ hỗ trợ.
- Tách identity theo vai trò API, worker, migration job và scheduler.
- Khi instance bị nghi xâm nhập, thu hồi identity/session và thay máy từ image tin cậy.
- Xác minh log/audit được gửi ra ngoài instance để không mất khi máy bị xóa.

Stateless giúp thay máy dễ hơn, nhưng không tự động làm hệ thống an toàn. Nếu mọi instance mới đều nhận một role quá rộng hoặc image chứa secret, việc tự động thay máy chỉ tái tạo cùng một rủi ro.

## 15. Kiến trúc ví dụ: API và worker có thể thay thế

Một dịch vụ xử lý đơn hàng có API, worker, database, queue, session store và object storage.

~~~~mermaid
flowchart TD
    U[Client] --> LB[Load balancer]
    LB --> A1[API instance A]
    LB --> A2[API instance B]
    A1 --> DB[(Orders database)]
    A2 --> DB
    A1 --> SS[(Shared session store)]
    A2 --> SS
    A1 --> Q[(Durable queue)]
    A2 --> Q
    Q --> W1[Worker instance 1]
    Q --> W2[Worker instance 2]
    W1 --> DB
    W2 --> DB
    W1 --> OS[(Object storage)]
    W2 --> OS
    A1 -. workload identity .-> SM[Secret manager]
    A2 -. workload identity .-> SM
    W1 -. workload identity .-> SM
    W2 -. workload identity .-> SM
~~~~

Cách hoạt động:

- Load balancer phân phối request đến API instance healthy.
- Session nằm ở shared store; API A hoặc B đều có thể xử lý cùng người dùng.
- Đơn hàng được ghi vào database và event được phát qua outbox/queue.
- Worker nhận message, xử lý idempotent và lưu file kết quả vào object storage.
- Mỗi instance có identity riêng theo vai trò.
- Log, metric và trace được gửi đến backend tập trung.
- Autoscaler có thể thêm hoặc loại API/worker mà không chuyển dữ liệu nghiệp vụ từ máy cũ.

### Điều gì xảy ra khi một máy bị xóa?

Nếu API A bị terminate đột ngột:

- Load balancer phát hiện health check thất bại và ngừng gửi request mới.
- Request đang mở có thể lỗi; client retry với timeout và idempotency key.
- API B tiếp tục phục vụ và đọc session từ shared store.
- Autoscaler tạo API instance C từ image và config đã version hóa.
- C lấy identity, secret, đăng ký telemetry và chỉ nhận traffic khi ready.

Nếu worker 1 bị terminate sau khi xử lý nhưng trước khi acknowledgement:

- Queue có thể giao lại message.
- Worker 2 hoặc worker mới xử lý lại.
- Idempotency record ngăn side effect trùng.
- Message chỉ được xác nhận sau khi kết quả bền vững.

## 16. Quy trình chuyển ứng dụng stateful sang stateless

Không nhất thiết phải viết lại toàn bộ ứng dụng trong một lần. Có thể chuyển từng loại trạng thái theo thứ tự rủi ro.

1. **Kiểm kê state:** tìm session, file, cache, local database, job và cấu hình trên từng máy.
2. **Phân loại:** đánh dấu source of truth, dữ liệu có thể tái tạo và dữ liệu cần RPO.
3. **Externalize file:** chuyển upload và artifact sang object/shared storage; lưu reference trong database.
4. **Externalize session:** dùng shared store hoặc token phù hợp; đồng bộ TTL và schema.
5. **Tách job:** đưa công việc dài vào durable queue và làm worker idempotent.
6. **Chuẩn hóa config/secret:** lấy từ config service và secret manager theo workload identity.
7. **Đóng gói image:** build image bất biến, version hóa và triển khai bằng IaC.
8. **Thêm lifecycle:** startup/readiness, graceful shutdown, drain và timeout.
9. **Kiểm thử thay máy:** terminate một instance có kiểm soát trong staging và quan sát phục hồi.
10. **Mở rộng dần:** canary, rolling replacement và scale test; theo dõi SLO, dữ liệu và chi phí.
11. **Loại bỏ state cục bộ cũ:** chỉ sau khi xác minh không còn consumer phụ thuộc.

### Tiêu chí hoàn tất

- Có thể tạo instance mới từ image và config mà không thao tác thủ công.
- Instance mới không cần IP hoặc hostname cố định.
- Session và dữ liệu nghiệp vụ không mất khi thay một instance.
- Request/job retry không tạo giao dịch trùng.
- Instance chỉ nhận traffic sau khi readiness thành công.
- Scale-in có drain và không bỏ dở công việc ngoài chính sách.
- Secret và quyền được cấp động theo identity.
- Có metric/log/trace tập trung và runbook phục hồi.

## 17. Kiểm thử khả năng thay thế tự động

Một thiết kế chỉ được xem là stateless khi đã thử thay máy trong điều kiện đại diện.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Terminate một API instance | Xóa một instance trong staging khi có traffic | Load balancer loại máy lỗi; backend khác tiếp tục phục vụ |
| Scale-out | Tăng tải để tạo instance mới | Máy mới bootstrap, ready và nhận traffic không cần thao tác tay |
| Scale-in | Giảm desired capacity | Instance drain, hoàn tất request và terminate đúng hạn |
| Reboot host/VM | Reboot có kiểm soát | Service tự khởi động, lấy config/secret và đạt readiness |
| Mất local disk | Thay instance hoặc làm mới ephemeral storage | Dữ liệu nghiệp vụ không mất; cache được tạo lại |
| Shared store chậm | Tạo latency/failure trong môi trường thử | Timeout và fallback được kiểm soát; không gây retry storm |
| Queue redelivery | Dừng worker trước acknowledgement | Message được giao lại; kết quả nghiệp vụ không bị nhân đôi |
| Database failover | Chuyển primary trong môi trường thử | Client reconnect, retry an toàn và dữ liệu đáp ứng RPO |
| Secret rotation | Thay phiên bản secret | Instance mới lấy secret mới; phiên bản cũ được thu hồi theo kế hoạch |
| Rolling schema change | Chạy phiên bản cũ và mới cùng lúc | Cả hai tương thích trong giai đoạn chuyển đổi |

Có thể dùng fault injection hoặc game day để thử mất một instance, node hoặc dependency. Chỉ thực hiện trên môi trường và phạm vi được phép; đặt giới hạn tác động, người giám sát và điều kiện dừng.

### Metric cần theo dõi

- Thời gian từ tạo instance đến readiness.
- Tỷ lệ bootstrap thành công và lỗi lấy secret/config.
- Số backend healthy, request rate và latency trong quá trình thay máy.
- Session miss, request retry và idempotency conflict.
- Queue depth, oldest message age, redelivery và dead-letter count.
- Database connection count, pool wait, failover time và replication lag.
- Error rate, p95/p99 latency và SLO/error budget.
- Tỷ lệ instance bị thay lặp lại, crash loop hoặc không đạt readiness.

## 18. Những sai lầm thường gặp

**Chỉ chuyển session ra ngoài nhưng vẫn lưu file upload trên máy.** Người dùng có thể giữ đăng nhập nhưng file biến mất khi backend bị thay. Kiểm kê cả filesystem và dữ liệu tạm.

**Dùng sticky session thay cho shared state.** Affinity chỉ định tuyến request; nó không bảo vệ session khi instance restart hoặc failover.

**Để worker đánh dấu message hoàn tất trước khi ghi kết quả bền vững.** Nếu worker chết sau acknowledgement, công việc có thể mất. Xác định thứ tự commit/ack và dùng idempotency.

**Retry mọi lỗi vô hạn.** Retry storm có thể làm dependency quá tải hơn. Dùng timeout, backoff, jitter, giới hạn lần thử và circuit breaker.

**Dùng một shared store nhưng không thiết kế HA.** Session store hoặc cache có thể trở thành điểm lỗi chung. Đặt mục tiêu availability, capacity, backup và recovery cho chính store.

**Nhúng secret trong image hoặc user data.** Image và metadata có thể được sao chép hoặc đọc bởi nhiều hệ thống. Lấy secret runtime theo identity.

**Tạo máy mới nhưng vẫn cần cấu hình thủ công.** Điều này làm thay thế tự động không đáng tin cậy. Version hóa image/config và kiểm thử bootstrap có thể lặp lại.

**Scale-in không drain.** Request, WebSocket hoặc job đang chạy có thể bị cắt. Phối hợp readiness, deregistration delay, termination grace period và queue lease.

**Không tính tải phát sinh lên dependency.** Thêm API instance có thể mở thêm hàng trăm database connection hoặc tạo cache stampede. Giới hạn pool và scale theo capacity end-to-end.

**Cho rằng stateless đồng nghĩa không cần backup.** Database, object storage, queue và session store vẫn giữ trạng thái quan trọng. Cần backup, replication và restore test theo RPO/RTO.

## 19. Checklist thiết kế stateless

### Trạng thái và dữ liệu

- [ ] Đã kiểm kê session, file, cache, job, config, secret và dữ liệu nghiệp vụ.
- [ ] Source of truth nằm ngoài vòng đời compute instance.
- [ ] File cần chia sẻ được lưu trong object/shared storage.
- [ ] Session có shared store hoặc token được bảo vệ và có vòng đời rõ.
- [ ] Cache có thể tái tạo và có TTL/eviction phù hợp.
- [ ] Queue/job có retry, acknowledgement, idempotency và dead-letter policy.
- [ ] Backup, replication, RPO/RTO và restore test được xác định.

### Compute và bootstrap

- [ ] Image được version hóa, quét và phát hành bất biến.
- [ ] Instance mới bootstrap tự động từ IaC/template.
- [ ] Cấu hình được version hóa và tách theo môi trường.
- [ ] Secret lấy runtime qua workload identity.
- [ ] Instance không phụ thuộc IP/hostname cố định.
- [ ] Service discovery hoặc load balancer cung cấp endpoint ổn định.
- [ ] Không cần thao tác tay để cài đặt hoặc sửa cấu hình sau khi tạo máy.

### Vòng đời và độ sẵn sàng

- [ ] Startup, readiness và liveness có semantics rõ.
- [ ] Chỉ backend ready mới nhận traffic.
- [ ] Scale-in có drain và graceful shutdown.
- [ ] Request/job có timeout, retry và idempotency.
- [ ] Shared dependency có capacity, HA và monitoring.
- [ ] Có headroom để chờ instance mới khởi động.

### Kiểm thử và vận hành

- [ ] Đã terminate instance trong staging khi đang có traffic.
- [ ] Đã kiểm thử scale-out, scale-in, reboot và dependency failure.
- [ ] Đã kiểm thử queue redelivery và side effect trùng.
- [ ] Đã kiểm thử secret rotation và rolling schema migration.
- [ ] Metric/log/trace tập trung, không mất khi instance bị xóa.
- [ ] Có runbook, owner, điều kiện dừng và quy trình rollback.

## 20. Tự kiểm tra

1. Stateless ở cấp compute có nghĩa là gì? Vì sao một ứng dụng stateless vẫn có thể dùng database và session?
2. Dữ liệu nào nên đặt ở database, object storage, queue, cache và local ephemeral disk?
3. Vì sao session affinity không đủ để bảo đảm trạng thái khi instance bị terminate?
4. Một worker bị dừng sau khi ghi dữ liệu nhưng trước khi acknowledgement. Cần thiết kế thế nào để message redelivery không tạo giao dịch trùng?
5. Vì sao idempotency key cần được lưu bền vững và có unique constraint?
6. Những thành phần nào cần có trong image và bootstrap để tạo instance mới tự động?
7. Workload identity giúp instance mới nhận quyền như thế nào mà không cần copy access key?
8. Phân biệt startup, readiness và liveness trong quá trình thay máy.
9. Khi scale-in, cần phối hợp load balancer drain, application shutdown và queue lease ra sao?
10. Vì sao autoscaling compute có thể làm database hoặc session store quá tải?
11. Hãy mô tả quy trình kiểm thử terminate một API instance và xác minh dịch vụ vẫn đáp ứng SLO.
12. Stateless có loại bỏ nhu cầu backup và disaster recovery không? Giải thích.

Thiết kế stateless giúp compute instance trở thành tài nguyên có thể tạo mới, thay thế hoặc mở rộng theo nhu cầu. Để đạt được điều đó, trạng thái nghiệp vụ phải nằm ở dịch vụ có vòng đời phù hợp; image, cấu hình và identity phải tái tạo được; request và job phải chịu được retry; còn lifecycle phải có readiness, drain và graceful shutdown. Khi những điều kiện này được kiểm chứng bằng thử nghiệm thay máy thực tế, VM, container và serverless có thể phục hồi linh hoạt hơn mà không phụ thuộc vào một instance cụ thể.
