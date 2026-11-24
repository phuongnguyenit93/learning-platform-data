# Tính nhất quán, độ trễ và sự cố từng phần khi gọi dịch vụ từ xa

Một ứng dụng Spring Boot ghi đơn hàng vào cơ sở dữ liệu, gửi sự kiện lên hàng đợi và lưu hóa đơn trên object storage. Cả ba dịch vụ managed đều có thể hoạt động bình thường, nhưng hệ thống vẫn phát sinh lỗi: API đã ghi thành công trong khi người dùng nhận timeout; consumer xử lý lại cùng một message; bản sao database chưa thấy cập nhật mới; hoặc một dịch vụ quá chậm làm hết luồng xử lý HTTP.

Đó là bản chất của **hệ thống phân tán**: các thành phần giao tiếp qua mạng, không chia sẻ cùng một thời điểm quan sát, và có thể thất bại độc lập. Trong chương **Nền tảng đám mây**, bài này giúp người học mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION** thực hành tích hợp Spring Boot với storage, messaging, database và secret managed trên **AWS, Azure và Google Cloud** bằng các thư viện Spring Cloud tương ứng; đồng thời biết cấu hình danh tính, quyền, timeout, retry, kiểm thử lỗi và đánh giá khác biệt giữa provider.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt các mức **tính nhất quán** và lựa chọn kỳ vọng phù hợp cho từng luồng đọc/ghi.
- Giải thích độ trễ mạng, độ trễ đuôi (tail latency), thời hạn chờ (deadline), timeout và ảnh hưởng của chuỗi lời gọi đồng bộ.
- Nhận diện **sự cố từng phần**: một thành phần thành công trong khi thành phần khác thất bại hoặc client không biết kết quả.
- Thiết kế retry, exponential backoff, jitter, circuit breaker, bulkhead và giới hạn cạnh tranh có điều kiện.
- Dùng **idempotency key**, transactional outbox/inbox, deduplication và acknowledgement để chống trùng tác vụ nghiệp vụ.
- So sánh hành vi nhất quán và delivery của Amazon S3/SQS/RDS, Azure Blob/Service Bus/SQL và Google Cloud Storage/Pub/Sub/Cloud SQL.
- Xây dựng bài kiểm thử tích hợp có lỗi mạng, phản hồi chậm, duplicate message, read replica lag và việc cấp quyền sai.

## 2. Một request từ xa thực sự trải qua những bước nào?

Gọi REST API, gửi message hay truy vấn cloud database đều không chỉ là gọi một phương thức Java. Ví dụ một request có thể trải qua:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Spring Boot
    participant S as Managed service
    participant R as Data replica
    U->>A: POST /orders
    A->>S: Ghi trạng thái đơn
    S->>S: Commit thành công
    S--xA: Phản hồi bị mất trên mạng
    Note over A: Timeout, chưa biết commit hay chưa
    A-->>U: 504 / lỗi tạm thời
    S-->>R: Sao chép nếu có
    Note over R: Có thể trễ theo mô hình replica
    U->>A: Retry request cùng nghiệp vụ
~~~

Từ góc nhìn của Spring Boot, **timeout chỉ có nghĩa không nhận được kết quả trong hạn chờ**; nó **không chứng minh** dịch vụ đích chưa xử lý request. Nếu retry một thao tác có tác dụng phụ mà không kiểm soát, có thể tạo hai đơn, hai khoản thanh toán hoặc hai thông điệp.

Tương tự, một lần đọc từ replica ngay sau khi ghi vào primary có thể trả về dữ liệu cũ, trong khi lần đọc ở primary đã thấy dữ liệu mới. Đây là vấn đề về **tính nhất quán và nơi đọc**, không nhất thiết là lỗi mất dữ liệu.

## 3. Các loại sự cố từng phần

Sự cố từng phần (*partial failure*) xảy ra khi **một số thành phần hoặc lời gọi thất bại nhưng các phần khác vẫn hoạt động**. Một ứng dụng monolith cũng có thể gặp lỗi, nhưng ranh giới mạng và tài nguyên quản lý độc lập khiến các tình huống sau phổ biến hơn khi sử dụng cloud:

| Tình huống | Điều ứng dụng quan sát | Điều thực tế có thể đã xảy ra |
|---|---|---|
| Không kết nối được | Connection refused, DNS error hoặc timeout | Service down, mạng bị chặn, DNS sai, endpoint sai |
| Kết nối được nhưng đọc phản hồi hết hạn | Read timeout | Server có thể chưa xử lý, đang xử lý hoặc đã commit |
| API A thành công, API B thất bại | Lỗi ở bước thứ hai | Dữ liệu đã ghi tại A; trạng thái tổng thể dở dang |
| Queue đã gửi nhưng publisher không nhận ACK | Timeout/transport error | Message có thể đã được chấp nhận và sẽ được giao |
| Worker xử lý xong nhưng ACK mất | Message xuất hiện lại | Nghiệp vụ đã thực hiện; broker giao lại vì không ghi nhận ACK |
| Primary cập nhật, replica chưa kịp | Đọc thấy giá trị cũ | Sao chép bất đồng bộ còn độ trễ |
| Một AZ/Region suy giảm | Một số request chậm/lỗi | Các zone/region khác vẫn có thể phục vụ |
| IAM/token hết hạn hoặc quyền bị thu hồi | 401/403/PermissionDenied | Network vẫn tốt; request bị chặn bởi xác thực hoặc phân quyền |
| Quota hoặc throttling | 429/ResourceExhausted/Throttling | Dịch vụ đang bảo vệ năng lực xử lý; retry dồn dập làm tình hình xấu đi |

Đừng gom mọi lỗi từ xa thành “dịch vụ không khả dụng”. Cần phân biệt **lỗi tạm thời**, **lỗi cấu hình/quyền**, **lỗi yêu cầu**, **kết quả không xác định** và **lỗi nghiệp vụ vĩnh viễn**.

## 4. Tính nhất quán: nhìn thấy dữ liệu mới đến mức nào?

### 4.1. Không phải mọi hệ thống đều có cùng một mức nhất quán

**Strong consistency** là cách nói chung rằng một số thao tác đọc phản ánh kết quả của các ghi đã hoàn tất theo cam kết của dịch vụ. Khi nói nghiêm ngặt về đối tượng đơn lẻ, **linearizability** yêu cầu các thao tác có thể được xem như diễn ra tức thời tại một điểm giữa thời gian bắt đầu và kết thúc, đồng thời tôn trọng thứ tự thực tế của thao tác đã hoàn tất.

**Eventual consistency** cho phép các bản sao tạm thời khác nhau và sẽ hội tụ nếu không có cập nhật mới, theo điều kiện hệ thống và cam kết dịch vụ. Nó **không định nghĩa một số giây cố định** mà ứng dụng có thể mặc định. Cần xem SLA, giới hạn và cơ chế quan sát replica lag nếu có.

**Session consistency** và các bảo đảm liên quan như read-your-writes cho phép một phiên hoặc client nhìn thấy các ghi của mình theo điều kiện áp dụng (ví dụ sử dụng session token, đi đúng primary hoặc cung cấp token phiên). **Bounded staleness** giới hạn mức cũ của dữ liệu theo thời gian hoặc số phiên bản khi dịch vụ hỗ trợ. Các bảo đảm về **thứ tự quan sát** và **thứ tự commit transaction** cần được xem riêng.

| Mô hình | Trải nghiệm điển hình | Cần chú ý |
|---|---|---|
| Strong/linearizable cho thao tác được hỗ trợ | Ghi hoàn tất rồi đọc cùng đối tượng thấy kết quả mới theo cam kết | Không tự tạo transaction đa tài nguyên |
| Eventual | Replica hoặc index có thể trả về giá trị cũ sau ghi | Thiết kế chấp nhận stale read hoặc chờ hội tụ |
| Read-your-writes/session | Client trong cùng phiên thấy cập nhật của mình theo điều kiện của dịch vụ | Token phiên, định tuyến đọc và cách tạo client quan trọng |
| Bounded staleness | Đọc có mức trễ được giới hạn theo chế độ của dịch vụ | Đánh đổi latency, availability, throughput và phạm vi triển khai |
| Snapshot/transactional isolation | Nhiều thao tác trong transaction đọc trạng thái nhất quán theo isolation | Phải hiểu isolation level, phạm vi transaction và xử lý conflict |

**Tính nhất quán mạnh của một object** không đồng nghĩa atomic transaction giữa object, database và queue. **Độ bền dữ liệu** (durability), **khả năng sẵn sàng** (availability) và **tính nhất quán khi đọc** là các thuộc tính khác nhau.

### 4.2. Các hiện tượng ứng dụng cần biết

- **Stale read:** vừa cập nhật đơn hàng nhưng trang chi tiết đọc từ replica trả trạng thái cũ.
- **Read skew:** trong một luồng xử lý, các lần đọc từ những thời điểm/replica khác nhau tạo ra tổ hợp trạng thái không từng tồn tại đồng thời.
- **Lost update:** hai request cùng đọc phiên bản cũ rồi ghi đè nhau nếu không có optimistic locking hoặc concurrency control.
- **Out-of-order events:** sự kiện “Đã giao hàng” đến consumer trước sự kiện “Đang vận chuyển”; nếu cập nhật mù, trạng thái có thể quay ngược.
- **Phantom hoặc non-repeatable read:** trong database transaction, tập kết quả hoặc giá trị có thể đổi khi đọc lại tùy isolation level.
- **Duplicate side effect:** cùng lệnh bị thực thi hai lần do retry, dù từng lần đều thành công về mặt kỹ thuật.

Ví dụ dùng optimistic locking cho đơn hàng:

~~~sql
UPDATE orders
SET status = :new_status, version = version + 1
WHERE id = :order_id
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng 0, ứng dụng phải **đọc lại và giải quyết xung đột** hoặc từ chối thay đổi; không tự retry mù với phiên bản cũ. Thao tác này bảo vệ cập nhật trong **một database transaction**, chưa giải quyết việc gửi event ra message broker.

## 5. Khác biệt thực tế giữa dịch vụ AWS, Azure và Google Cloud

Không thể gán nhãn “AWS eventual, Azure strong, GCP strong” cho toàn bộ provider. **Từng loại dịch vụ, loại thao tác, chế độ replica và cấu hình** quyết định bảo đảm.

### 5.1. Object storage

| Nhà cung cấp | Hành vi cần nắm | Điều không được suy luận |
|---|---|---|
| **Amazon S3** | Với S3 general purpose buckets, các thao tác object PUT/GET/LIST và thay đổi metadata/tags liên quan có bảo đảm strong consistency theo tài liệu dịch vụ; các biến thể sản phẩm có đặc tính riêng | Không có transaction atomic cho một nhóm object; cross-region replication có thể bất đồng bộ |
| **Azure Blob Storage** | Primary endpoint cung cấp strong consistency cho thao tác theo cam kết của Blob; ETag/conditional requests hỗ trợ concurrency control | Đọc từ secondary geo-replicated endpoint có thể chậm so với primary; redundancy không ngăn xóa nhầm |
| **Google Cloud Storage** | Object read-after-write, update/delete và object listing có strong consistency theo phạm vi được dịch vụ công bố | Không có distributed SQL transaction trên nhiều object; replication giữa các location có tiến trình riêng |

Ví dụ ứng dụng tải cùng một hóa đơn và thấy dữ liệu cũ có thể đến từ **cache/CDN, client cache, bản sao địa lý, proxy hoặc ứng dụng**, không phải nhất thiết từ consistency model của object storage chính. Cần xác định endpoint thực tế và bộ nhớ đệm.

Object storage cung cấp ETag hoặc generation/version trong nhiều trường hợp. Với thao tác ghi có cạnh tranh, cân nhắc **conditional write**, versioning hoặc kiểm tra generation theo dịch vụ; không chỉ dùng “ghi đè cuối cùng thắng” cho dữ liệu cần tính đúng đắn.

### 5.2. Database và replica

| Dịch vụ | Ví dụ về tính nhất quán | Điều cần thiết kế ở Spring Boot |
|---|---|---|
| **Amazon RDS** | Transaction và isolation của database engine trên primary; read replica thường sao chép bất đồng bộ | Read-after-write cần định tuyến tới primary hoặc chấp nhận replica lag |
| **Amazon DynamoDB** | Eventual reads mặc định cho nhiều thao tác; strongly consistent reads có thể chọn với table và local secondary index trong phạm vi được hỗ trợ; GSI và global-table replication có đặc tính riêng | Chọn ConsistentRead ở nơi hỗ trợ; không mặc định GSI/global replica đọc tức thời |
| **Azure SQL Database** | Transaction của SQL engine; geo-secondary/read scale-out có thể có độ trễ đồng bộ tùy chế độ | Hiểu primary/read-only endpoint, isolation và failover |
| **Azure Cosmos DB** | Có các consistency level lựa chọn như Strong, Bounded Staleness, Session, Consistent Prefix, Eventual, kèm các giới hạn cấu hình | Chọn level phù hợp, xử lý session token khi cần read-your-writes |
| **Google Cloud SQL** | Transaction theo engine ở primary; read replicas có thể lag | Không dùng replica cho quyết định cần dữ liệu mới nhất khi chưa xác minh |
| **Cloud Spanner/Firestore** | Có các bảo đảm nhất quán riêng, mạnh ở các loại thao tác được công bố | Đọc theo đúng mode và transaction semantics của sản phẩm |

**Ví dụ:** sau khi thanh toán, API cập nhật bảng đơn hàng trong primary. Trang lịch sử đơn đọc từ read replica có thể vẫn thấy “Chưa thanh toán”. Giải pháp có thể là đọc primary trong một khoảng sau ghi, dùng version để báo trạng thái đang đồng bộ, hoặc áp thiết kế giao diện chấp nhận eventual consistency. Đừng mặc định tăng timeout giải quyết được replica lag.

### 5.3. Messaging và semantics giao nhận

| Dịch vụ | Điều thường phải thiết kế | Chú ý |
|---|---|---|
| **Amazon SQS Standard** | At-least-once delivery; duplicate và thay đổi thứ tự có thể xảy ra | Consumer idempotent, visibility timeout, DLQ |
| **Amazon SQS FIFO** | Thứ tự trong cùng message group, deduplication theo phạm vi/thời hạn dịch vụ | Không suy ra toàn bộ nghiệp vụ exactly-once; retry ngoài cửa sổ dedup vẫn cần xử lý |
| **Azure Service Bus** | Peek-lock/complete-abandon, retry, DLQ, sessions và duplicate detection nếu được cấu hình | Lock có thể hết hạn hoặc ACK thất bại; duplicate detection không thay dedup nghiệp vụ |
| **Google Cloud Pub/Sub** | Thường at-least-once; ordering key và exactly-once delivery là tính năng có điều kiện | Exactly-once delivery không đồng nghĩa side effect trong DB chỉ chạy một lần |

Tên **exactly-once** ở một dịch vụ thường mô tả một **phạm vi hẹp của giao nhận hoặc API**. Không tự mở rộng thành “mọi update DB, gọi HTTP, gửi email và thanh toán diễn ra đúng một lần”. Consumer cần chủ động xử lý trùng lặp, và producer cần xử lý trường hợp publish đã thành công nhưng phản hồi bị mất.

### 5.4. Secret và cấu hình phân tán

Rotation secret có thể tạo khoảng chuyển tiếp: instance A vẫn giữ credential cũ trong cache, instance B đã lấy phiên bản mới, trong khi database chấp nhận một hoặc hai phiên bản tùy quy trình. Thiết kế rotation nên hỗ trợ **thời gian chuyển tiếp được kiểm soát**, làm mới cache, loại bỏ secret cũ và kiểm tra khả năng kết nối. AWS Secrets Manager, Azure Key Vault và Google Cloud Secret Manager cung cấp API/trạng thái phiên bản khác nhau; đừng mặc định đọc secret mỗi request hoặc mặc định giá trị cache luôn tức thời nhất quán.

## 6. Độ trễ: đo tổng hành trình thay vì chỉ thời gian xử lý server

Độ trễ một cloud request có thể gồm DNS, thiết lập kết nối, TLS, mạng giữa hai vị trí, chờ connection pool, hàng đợi server, xử lý nghiệp vụ, ghi bền xuống storage và thời gian trả kết quả.

~~~mermaid
flowchart LR
    A["Spring Boot"] --> P["Pool / DNS / TLS"]
    P --> N["Network"]
    N --> Q["Queueing"]
    Q --> S["Service processing"]
    S --> R["Response"]
    R --> A
~~~

Nhiều SDK giữ kết nối sống để giảm chi phí khởi tạo. Nếu lượng request vượt khả năng connection pool, application có thể chậm **trước cả khi gửi request**. Khi một lời gọi đồng bộ chậm, thread/connection bị giữ lâu, tăng hàng đợi và có thể dẫn tới hiệu ứng lan truyền.

### 6.1. Trung bình không đủ

Nếu phần lớn request nhanh nhưng một tỷ lệ nhỏ rất chậm, **average latency** có thể che giấu trải nghiệm người dùng xấu. Cần quan sát **p50, p95, p99**, timeout rate, error rate và saturation (số request đang chờ, pool usage, CPU, queue depth). Phân tách metric theo service, operation, Region và caller.

**Tail latency** tăng mạnh khi nhiều lời gọi độc lập đều phải thành công trước khi API trả kết quả. Một lần gọi chậm có thể quyết định thời gian toàn bộ request. Chuỗi đồng bộ có thể bị trễ cộng dồn; fan-out song song chịu rủi ro từ lời gọi chậm nhất và tăng tổng tải lên downstream.

### 6.2. Vị trí địa lý và đường mạng

- Nếu Spring Boot chạy tại một Region, còn managed database ở Region khác, mỗi round-trip có thể tăng độ trễ và chi phí truyền dữ liệu.
- Private endpoint/PrivateLink/Private Service Connect thay đổi đường truy cập và khả năng bảo mật mạng, nhưng không tự bảo đảm độ trễ thấp hơn trong mọi cấu hình.
- TLS, proxy, gateway, NAT, DNS, load balancing và quota đều có thể ảnh hưởng thời gian thực.
- Retry xuyên Region hoặc failover sang Region khác có thể thay đổi cả thời gian đáp ứng lẫn hành vi nhất quán.

**Quy tắc thiết kế:** đưa những thao tác cần transaction hoặc đọc/ghi đồng bộ tới nơi gần dữ liệu nhất trong phạm vi dữ liệu được phép; đo từ đúng môi trường chạy trước khi tối ưu.

## 7. Timeout và deadline: không chờ vô hạn

**Timeout** giới hạn thời gian chờ một giai đoạn hoặc một operation. **Deadline** là thời điểm hết hạn cho **toàn bộ yêu cầu nghiệp vụ**. Một request đi qua API Gateway → Spring Boot → database → queue không thể để mỗi bước chờ hết toàn bộ ngân sách thời gian mà vẫn hy vọng trả lời đúng hạn.

Các loại timeout thường gặp:

| Giới hạn | Bảo vệ điều gì? | Khi đặt sai |
|---|---|---|
| Connection/acquire timeout | Chờ lấy connection pool hoặc thiết lập kết nối | Thread bị giữ trong khi pool cạn hoặc mạng không tới đích |
| Connect timeout | Chờ kết nối mạng được thiết lập | Chờ lâu khi đích không nhận kết nối |
| Read/response timeout | Chờ byte phản hồi hoặc kết thúc operation | Không phát hiện server treo hoặc request quá lâu |
| Per-attempt timeout | Giới hạn mỗi lần gọi SDK/API | Một attempt chiếm hết ngân sách; không còn thời gian phục hồi |
| Overall operation deadline | Giới hạn tất cả attempts, backoff và xử lý liên quan | Retry tiếp tục sau khi caller đã bỏ cuộc |
| Message visibility/lock timeout | Khoảng consumer giữ message trước khi redelivery | Message bị giao lại khi xử lý chưa xong; hoặc bị giữ quá lâu khi worker hỏng |

Ví dụ một API có deadline **2 giây** (con số minh họa): cần dự trù thời gian xác thực, truy vấn DB, publish event và trả phản hồi, cộng margin. Nếu bước DB đã chiếm hầu hết thời gian, đừng tiếp tục retry publish nhiều lần trong cùng request. Có thể lưu outbox trong transaction rồi để worker gửi bất đồng bộ.

Timeout hợp lý phải dựa vào **latency measurements**, đặc tính downstream, khả năng retry an toàn và SLO. Đặt timeout quá thấp gây lỗi giả; quá cao gây nghẽn thread/pool. Đảm bảo timeout tổng không vô tình nhỏ hơn thời gian hợp lệ của long polling, streaming hoặc tác vụ batch.

**Hủy request của client không đồng nghĩa rollback ở server.** Đây là điều kiện cốt lõi khi thiết kế retry cho side effects.

## 8. Retry: cần điều kiện, giới hạn và idempotency

### 8.1. Những trường hợp có thể retry

Retry hợp lý với một số lỗi **tạm thời** như mất kết nối ngắn, 429/throttling, 503/service unavailable hoặc lỗi mạng thoáng qua, **nếu operation có thể retry an toàn**. Cần phân biệt:

| Lỗi | Hướng xử lý đề xuất |
|---|---|
| 429 / throttling | Thực hiện backoff, tôn trọng Retry-After nếu có, giảm concurrency |
| 502/503/504 tạm thời | Retry có giới hạn nếu còn deadline và an toàn về side effect |
| Connect timeout trước khi gửi yêu cầu | Thường có thể thử lại nếu cấu hình xác định được không có side effect; SDK xử lý chi tiết |
| Read timeout sau khi request đã gửi | Kết quả **không xác định**; cần idempotency key hoặc kiểm tra trạng thái |
| 400/validation error | Sửa dữ liệu đầu vào; không retry cùng request |
| 401/403 / permission denied | Kiểm tra token, audience, role, IAM/RBAC và network; không retry vô hạn |
| 404 / resource missing | Kiểm tra ID/Region/endpoint; một vài API có propagation delay nhưng phải xác minh cụ thể |
| Concurrency conflict / 409 | Dùng optimistic concurrency, đọc lại và tái tính toán; không lặp mù |

HTTP status chỉ là tín hiệu. Các SDK có phân loại exception và chế độ retry riêng; lỗi 500 có thể đi kèm tác dụng phụ thành công. Với database, cần xem SQLState, loại lỗi transaction và khả năng rollback/commit trước khi lặp lại một command.

### 8.2. Exponential backoff và jitter

Thay vì gọi lại liên tục, tăng khoảng nghỉ theo cấp số nhân rồi thêm **jitter** để nhiều client không đồng thời bắn request vào dịch vụ vừa phục hồi. Mô hình khái niệm:

~~~text
backoff_k = min(maxDelay, baseDelay * 2^k)
sleep_k   = random(0, backoff_k)  # full jitter, minh họa

stop khi:
  - vượt tổng số attempts;
  - hết overall deadline;
  - lỗi không retry được;
  - không thể bảo đảm side effect an toàn.
~~~

Công thức chỉ để giải thích; production cần dùng retry policy của SDK hoặc thư viện ổn định. AWS SDK, các Azure SDK và Google Cloud client libraries có **retry mặc định khác nhau theo API**, có thể xử lý throttling, status code và backoff theo cơ chế riêng. Trước khi thêm Spring Retry/Resilience4j bên ngoài, kiểm tra cấu hình SDK để tránh **retry lồng nhau** (SDK retry nhiều lần rồi service layer retry thêm), gây retry storm.

### 8.3. Idempotency: phép thử an toàn của retry

Một thao tác là **idempotent** nếu thực hiện lặp lại với cùng ý định không làm trạng thái nghiệp vụ tiếp tục thay đổi ngoài tác dụng của lần thực hiện đầu tiên. Ví dụ:

- Đọc object bằng GET thường không tạo side effect nghiệp vụ.
- Ghi trạng thái một đơn sang **PAID** có thể idempotent nếu dùng một event ID và bảo đảm cập nhật một lần.
- **Tạo đơn mới không có idempotency key** thường không idempotent: retry có thể tạo đơn thứ hai.
- Gửi message lại có thể tạo thêm message; chỉ một số tính năng dedup của broker giúp giảm điều này trong phạm vi xác định.
- Upload cùng bytes vào cùng key có thể tạo trạng thái đọc giống nhau, nhưng vẫn tạo **object version mới hoặc phí/side effects** nếu bucket bật versioning; không coi đó là “exactly-once”.

Với HTTP POST tạo đơn hoặc gọi payment provider, client gửi **idempotency key** ổn định cho một ý định nghiệp vụ. Phía server lưu key cùng fingerprint của payload và kết quả, từ chối trường hợp cùng key nhưng payload khác, rồi trả kết quả đã lưu cho request retry. Chọn TTL và phạm vi uniqueness theo quy trình nghiệp vụ; key không được chỉ tồn tại trong RAM của một instance.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant D as Transactional database
    C->>A: POST /orders (idempotency-key = K)
    A->>D: Ghi K + đơn + kết quả trong một transaction
    D-->>A: Commit
    A--xC: Phản hồi mất
    C->>A: Retry POST /orders (cùng K)
    A->>D: Kiểm tra K, payload fingerprint
    D-->>A: K đã hoàn tất, kết quả trước đó
    A-->>C: Trả lại kết quả đơn ban đầu
~~~

Phải xử lý **hai request đồng thời có cùng key** bằng unique constraint/transaction/locking phù hợp; kiểu “SELECT xem tồn tại rồi INSERT” mà không có bảo vệ cạnh tranh sẽ bị race condition.

## 9. Circuit breaker, bulkhead và backpressure

Retry không phải giải pháp cho một downstream đang mất khả năng phục vụ. Ba mẫu thiết kế bổ sung:

**Circuit breaker** theo dõi lỗi/chậm và tạm thời chặn các request mới khi đạt ngưỡng; sau khoảng nghỉ, chỉ cho một số request thử kiểm tra khả năng phục hồi. Nó giảm tải nhưng có thể từ chối request hợp lệ khi hệ thống đang hồi phục, vì vậy cần metric và ngưỡng phù hợp.

**Bulkhead** chia giới hạn thread, connection hoặc số request đồng thời theo loại downstream. Khi dịch vụ lưu hóa đơn chậm, nó không được chiếm hết tài nguyên khiến endpoint chỉ đọc trạng thái đơn cũng chết theo.

**Backpressure/rate limiting** giới hạn tốc độ sinh hoặc tiêu thụ công việc để downstream có thể theo kịp. Với messaging, giới hạn concurrency/prefetch, giám sát queue depth/age và retry/DLQ. Với synchronous APIs, có thể trả 429/503 hợp lý thay vì tạo hàng đợi vô hạn.

~~~mermaid
flowchart LR
    API["Spring Boot API"] --> L["Concurrency limit"]
    L --> CB["Circuit breaker"]
    CB --> RT["Retry có deadline + jitter"]
    RT --> S["Managed service"]
    CB -. "Open" .-> F["Fallback / trả lỗi có kiểm soát"]
    S --> M["Metrics: latency, errors, saturation"]
    M -. "Điều chỉnh ngưỡng" .-> L
~~~

Fallback chỉ có ý nghĩa nếu **đúng nghiệp vụ**: hiển thị “đang cập nhật” từ cache có thể chấp nhận cho trang danh sách, nhưng không được tự báo thanh toán thành công khi payment provider không xác nhận.

## 10. Messaging: at-least-once, ACK và trùng lặp

### 10.1. ACK có thể thất bại sau khi xử lý thành công

Một consumer thông thường:

1. Nhận message kèm định danh của delivery.
2. Mở database transaction, áp dụng thay đổi nghiệp vụ và lưu event ID đã xử lý.
3. Commit transaction.
4. ACK/Complete/Delete message sau khi bước 3 thành công.

Nếu worker chết giữa bước 3 và bước 4, broker có thể giao lại message. Khi đó **database phải nhận biết event đã áp dụng** và bỏ qua side effect lặp.

~~~mermaid
sequenceDiagram
    participant Q as Queue / PubSub
    participant W as Spring Boot consumer
    participant DB as Database
    Q->>W: Event E lần 1
    W->>DB: Commit nghiệp vụ + processed(E)
    DB-->>W: OK
    W--xQ: ACK bị mất
    Q->>W: Event E lần 2
    W->>DB: Kiểm tra processed(E)
    DB-->>W: Đã xử lý, không thực thi lại
    W->>Q: ACK thành công
~~~

**Message ID do broker cấp không nhất thiết ổn định giữa những lần publish của cùng sự kiện nghiệp vụ.** Nếu producer retry publish khiến tạo message mới, cần một **eventId do ứng dụng sinh ra** và đặt trong payload/attributes để consumer deduplicate qua cả những lần publish đó.

### 10.2. Khác biệt provider cần nhớ

- **SQS Standard:** at-least-once; message có thể giao lặp và không bảo đảm thứ tự toàn cục. Visibility timeout phải đủ hợp lý với processing, nhưng kể cả vậy vẫn cần idempotency.
- **SQS FIFO:** thứ tự theo message group; deduplication có phạm vi và thời hạn riêng của SQS FIFO. Dùng event ID làm dedup ID có ích, nhưng sau cửa sổ dedup hoặc qua các tác dụng phụ khác vẫn phải chống trùng ở tầng nghiệp vụ.
- **Azure Service Bus:** Peek-Lock có lock duration; xử lý lâu cần renewal theo cơ chế SDK/dịch vụ. Complete bị mất có thể dẫn tới redelivery. Duplicate detection và sessions là tính năng phải cấu hình theo yêu cầu, không thay thế DB dedup.
- **Google Cloud Pub/Sub:** ack deadline có thể được gia hạn bởi client library trong giới hạn hỗ trợ; message chưa ack có thể giao lại. Exactly-once delivery có điều kiện, phạm vi và giới hạn của sản phẩm; hệ thống vẫn phải bảo vệ DB side effects.

DLQ giúp cách ly **poison messages** sau nhiều lần thất bại để điều tra và replay có kiểm soát. Không dùng retry vô hạn cho payload sai schema, dữ liệu thiếu quyền hoặc lỗi nghiệp vụ không thể tự phục hồi. Với event có thứ tự quan trọng, dùng sequence/version và kiểm tra state machine; ordering của broker chưa đảm bảo thứ tự cập nhật ở mọi consumer và hệ thống downstream.

## 11. Distributed transaction: vì sao không thể chỉ dùng @Transactional?

Annotation **@Transactional** của Spring thường bao quanh một **transaction manager** (ví dụ một database). Nó không tự tạo transaction nguyên tử trải dài từ PostgreSQL sang SQS, Azure Service Bus, Pub/Sub, S3 hay HTTP API. Ví dụ:

~~~text
BEGIN DATABASE TRANSACTION
  UPDATE orders SET status = 'CONFIRMED'
COMMIT

PUBLISH OrderConfirmed TO QUEUE
~~~

Nếu commit thành công nhưng publish thất bại, database có đơn confirmed nhưng thiếu event. Đảo thứ tự publish trước commit thì event có thể được xử lý dù transaction DB sau đó rollback. **Không có thứ tự hai lời gọi đơn giản nào giải quyết nguyên tử cả hai hệ thống.**

### 11.1. Transactional outbox

**Transactional outbox** ghi cùng lúc trạng thái nghiệp vụ và một hàng outbox **trong cùng database transaction**. Worker riêng lấy các hàng chưa gửi, publish lên broker, rồi đánh dấu đã gửi:

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Một database transaction"]
    TX --> ORD["Update orders"]
    TX --> OUT["Insert outbox_event"]
    OUT --> PUB["Outbox publisher"]
    PUB --> MQ["SQS / Service Bus / PubSub"]
    MQ --> CON["Idempotent consumer"]
    PUB -. "ACK publish mất: retry" .-> OUT
~~~

Khi publish thành công mà cập nhật outbox status thất bại, publisher có thể gửi lại. Vì thế outbox cải thiện **khả năng giao event đáng tin cậy**, nhưng **không loại bỏ duplicate**. Consumer cần **inbox/dedup** hoặc thiết kế operation idempotent. Outbox worker cần locking/claim để nhiều instance không xử lý cùng row quá nhiều, có retry/backoff và cơ chế theo dõi stuck records.

### 11.2. Saga/compensation

Với quy trình gồm nhiều dịch vụ độc lập (đặt hàng, giữ kho, thanh toán, vận chuyển), có thể dùng **Saga**: mỗi bước là transaction cục bộ, khi bước sau thất bại thì thực hiện bước bù (*compensation*) theo quy tắc nghiệp vụ. Compensation không nhất thiết là hoàn tác vật lý hoàn hảo; ví dụ trả lại hàng tồn và hoàn tiền là các nghiệp vụ mới có trạng thái, có thể cũng thất bại và cần retry/audit.

Saga cần trạng thái rõ ràng, idempotency cho cả thao tác chính lẫn bù, xử lý event out of order và timeout chờ đối tác. Không tự thay thế bằng distributed lock hoặc tin rằng mọi API đều hỗ trợ XA/2PC.

## 12. Ví dụ Spring Boot: consumer idempotent bằng database

Giả sử ứng dụng nhận sự kiện **OrderStatusChanged** qua SQS, Service Bus hoặc Pub/Sub. Mỗi event chứa **eventId** duy nhất do producer sinh, orderId và status. Ý tưởng là lưu khóa event đã xử lý cùng với thay đổi trạng thái **trong cùng một transaction**.

Ví dụ DDL **PostgreSQL**:

~~~sql
CREATE TABLE processed_message (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Service Spring Boot (Java 17+, dùng Spring JDBC và transaction manager cho cùng datasource):

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderStatusChanged(
        String eventId, long orderId, String newStatus) {}

@Service
public class OrderEventHandler {
    private final JdbcTemplate jdbc;

    public OrderEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void handle(OrderStatusChanged event) {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }

        int newlyRecorded = jdbc.update(
                "INSERT INTO processed_message (consumer_name, event_id) " +
                "VALUES (?, ?) ON CONFLICT DO NOTHING",
                "order-status-consumer",
                event.eventId());

        if (newlyRecorded == 0) {
            return; // Event đã được commit trước đó.
        }

        int updated = jdbc.update(
                "UPDATE orders SET status = ? WHERE id = ?",
                event.newStatus(), event.orderId());
        if (updated != 1) {
            // Exception làm transaction rollback cả bản ghi dedup.
            throw new IllegalStateException("Order not found");
        }
    }
}
~~~

Điểm cần hiểu:

- Đoạn ví dụ minh họa **PostgreSQL** vì dùng **ON CONFLICT DO NOTHING**; thay cú pháp thích hợp nếu dùng SQL Server, MySQL hoặc engine khác.
- **Unique key** ngăn hai consumer song song cùng áp dụng một event ID. Cả cập nhật orders và insert dedup phải nằm trong **cùng transaction/datasource**.
- Listener/adapter của broker chỉ **ACK sau khi phương thức xử lý và database commit thành công**. Cách cấu hình ACK khác nhau tùy phiên bản Spring Cloud AWS, Spring Cloud Azure, Spring Cloud GCP và client library.
- Không bắt exception rồi trả về thành công khi DB rollback, vì broker có thể ACK nhầm và mất tác vụ.
- Logic trên chống **trùng cùng eventId**, chưa chống **event đến sai thứ tự**. Nếu status có thứ tự/version, thêm kiểm tra sequence hoặc state transition hợp lệ; nếu order thiếu vĩnh viễn, cần chính sách xử lý poison message thay vì retry vô hạn.
- Không ghi payload nhạy cảm vào bảng dedup chỉ để phát hiện trùng; có thể lưu fingerprint phù hợp và retention theo yêu cầu.

Thực tế các hệ thống còn cần transaction timeout, kiểm soát thời gian lock, chiến lược dọn bảng processed_message và bảo vệ trước cùng eventId bị dùng với payload khác.

### 12.1. Vì sao lock của broker không thay được database dedup?

Visibility timeout (SQS), Peek-Lock (Service Bus) và ack deadline (Pub/Sub) là cơ chế quản lý **lần giao message**, không phải khóa transaction của database nghiệp vụ. Một consumer có thể commit xong rồi chết trước ACK; message được phát lại và một consumer khác nhận tiếp. Do đó, thiết kế phải chịu được ít nhất trường hợp **xử lý lặp sau commit**.

## 13. Thiết kế cấu hình thời gian chờ và retry trong Spring

Các tên property của Spring Cloud AWS, Spring Cloud Azure và Spring Cloud GCP **khác nhau theo phiên bản**, và nhiều thao tác sử dụng chính retry policy của AWS SDK, Azure SDK hoặc Google Cloud client. Thay vì cho rằng một tên property dùng được cho tất cả, hãy xác định lớp đang thực sự quản lý timeout:

1. **HTTP/Web client:** connect timeout, response timeout, max connections, pool acquisition, TLS.
2. **Managed service SDK:** per-attempt timeout, overall timeout, retry conditions, backoff/jitter, API deadlines.
3. **Message listener:** concurrency, prefetch, visibility/lock/ack deadline, xử lý exception và DLQ.
4. **Business flow:** end-to-end deadline, idempotency, circuit breaker, bulkhead, fallback.

Một tập giá trị dưới đây chỉ là **mẫu cấu hình do ứng dụng tự định nghĩa**, không phải property auto-configure của Spring Cloud:

~~~yaml
integration:
  orders:
    overall-deadline: 2s
    max-attempts: 3
    backoff-base: 100ms
    backoff-cap: 1s
    max-concurrent-requests: 40
  consumer:
    max-concurrency: 8
    dead-letter-after-failures: 5
~~~

Các số trên là **giá trị minh họa**, không phải khuyến nghị áp dụng nguyên xi. Mỗi ứng dụng phải bind và thực thi bằng code hoặc thư viện phù hợp; property không tự có tác dụng. Dựa vào SLO, kích thước message, latency thực, throughput, mức quota và giới hạn của dịch vụ để hiệu chỉnh.

Nếu sử dụng **Resilience4j/Spring Retry**, đặt retry ở **một hoặc một số lớp được kiểm soát**, nhận biết SDK đã retry nội bộ hay chưa. Không để API retry 3 lần, service layer 3 lần và SDK 3 lần một cách vô ý, vì số request downstream có thể nhân lên. Khi cùng một overall deadline được truyền qua tầng call, mọi attempt phải dừng nếu không còn ngân sách.

Với thao tác có **side effect**, phải có idempotency hoặc business reconciliation trước khi cho phép retry. Với các lời gọi đọc idempotent, vẫn cần backoff và giới hạn, tránh làm quá tải downstream.

## 14. Kiểm thử tích hợp: chủ động gây lỗi trong môi trường cô lập

Một bài kiểm thử “ghi và đọc thành công” là cần nhưng chưa đủ. Nên kiểm tra **đúng hành vi khi thất bại** bằng test environment tách khỏi production:

| Kịch bản | Cách tạo tình huống | Kết quả mong muốn |
|---|---|---|
| Response bị trễ | Test proxy/fault injection tăng latency | Timeout đúng ngân sách, không giữ thread vô hạn |
| Server commit, ACK/response bị mất | Test adapter giả lập kết quả không xác định sau commit | Retry bằng cùng idempotency key; chỉ một side effect nghiệp vụ |
| Hai request cùng idempotency key | Gửi đồng thời trên môi trường test | Unique constraint/locking chỉ cho một thực thi |
| Message redelivery | Không ACK lần đầu hoặc cho lock hết hạn trong test | Consumer nhận lại nhưng không áp dụng DB hai lần |
| Publisher thất bại sau DB commit | Ngắt publish trong outbox worker test | Outbox còn record; retry publish rồi consumer dedup |
| Read replica lag | Đọc qua replica test sau ghi primary | UI/API chấp nhận stale read hoặc chuyển đọc primary khi cần |
| API throttling 429 | Mock/trigger quota test có kiểm soát | Backoff, jitter, không retry storm, đo được metric |
| IAM 403 / sai endpoint | Dùng test identity thiếu quyền hoặc endpoint test sai | Dừng đúng lớp, báo lỗi nguyên nhân, không tăng quyền tự động |
| Một downstream chậm kéo dài | Giới hạn throughput và làm chậm dịch vụ test | Circuit breaker/bulkhead bảo vệ endpoint khác |
| Event out of order | Publish sequence đảo thứ tự trong test | Version/state machine ngăn lùi trạng thái |
| Poison message | Payload sai schema hoặc vi phạm invariant | Đi DLQ/quarantine theo chính sách, có cảnh báo |
| Recovery/DR | Diễn tập mất node/zone hoặc service failover phù hợp | Luồng phục hồi đúng RTO/RPO đã thiết kế |

**Mock** có thể kiểm tra code retry và idempotency logic, nhưng không thay thế test trên cloud cho IAM, quota, network, tính nhất quán replica, dead-letter behavior hoặc chi phí. Khi test với dịch vụ thật, cần resource riêng, giới hạn chi phí và cơ chế cleanup.

### 14.1. Các metric cần thu thập

- **Request:** p50/p95/p99 latency, attempt count, timeout count, status/exception theo operation, in-flight request, pool saturation.
- **SDK/retry:** số lần retry, backoff, throttling, tổng thời gian operation, tỉ lệ circuit breaker open.
- **Messaging:** message age, backlog, delivery count, lock/visibility expiry, DLQ depth, duplicate suppressed, consumer lag.
- **Database:** pool usage, lock wait, transaction duration, commit failures, read replica lag, conflict rate.
- **Nghiệp vụ:** số đơn phát sinh thực, số payment attempts, event/outbox pending, số lần reconciliation, mức mất dữ liệu và thời gian phục hồi.

Log nên có trace ID, request ID, event ID, idempotency key dạng đã xử lý phù hợp, resource ID, Region và attempt number; **không log token, password, raw secret, payment data hay payload nhạy cảm**. Tracing giúp biết client gọi tới đâu, nhưng khi phản hồi bị mất nó **không tự chứng minh server chưa commit**.

## 15. Tình huống áp dụng theo cloud provider

### 15.1. AWS: S3 + SQS + RDS

Spring Boot tạo đơn trong RDS và lưu outbox trong cùng transaction. Outbox worker gửi event qua SQS. Nếu send timeout, worker có thể gửi lại; consumer dùng event ID để dedup. Khi đọc object trên S3, hiểu rằng object operations có consistency guarantees riêng; nếu đọc từ CDN, cache hoặc hệ thống sao chép liên Region, cần xét thêm cơ chế đồng bộ đó. Với RDS read replica, yêu cầu read-your-writes của luồng xác nhận đơn nên đọc primary hoặc kiểm soát replica lag.

SQS Standard consumer phải chịu được duplicate. Nếu dùng FIFO để duy trì thứ tự theo order ID/message group, vẫn cần kiểm tra event sequence và bảo vệ side effect ở DB.

### 15.2. Azure: Blob + Service Bus + Azure SQL

Ứng dụng ghi hóa đơn vào Blob Storage và phát sự kiện qua Service Bus. Khi consumer đã ghi vào Azure SQL nhưng thao tác Complete message lỗi do mất mạng/lock hết hạn, message có thể trở lại; bảng processed_message giúp bỏ qua side effect lặp. Nếu đọc dữ liệu từ bản sao geo-secondary của storage hoặc SQL, độ mới có thể khác primary. Cần chọn retry/lock renewal theo giới hạn SDK và service.

Azure Managed Identity giúp tránh lưu credential dài hạn, nhưng thiếu RBAC data role hoặc private endpoint DNS sai vẫn làm lời gọi fail. Không xử lý mọi 403 bằng retry; kiểm tra principal, scope role và network.

### 15.3. Google Cloud: Cloud Storage + Pub/Sub + Cloud SQL

Ứng dụng lưu object trong Cloud Storage, publish event lên Pub/Sub và cập nhật Cloud SQL. Các guarantee mạnh của Cloud Storage cho object operations không tạo transaction nguyên tử giữa object và DB. Nếu producer publish được nhưng mất response, duplicate event có thể xuất hiện; consumer cần event ID từ nghiệp vụ.

Pub/Sub ordering key hoặc exactly-once delivery nếu bật đúng điều kiện không loại bỏ yêu cầu idempotency tại Cloud SQL. Read replica Cloud SQL vẫn có thể có replica lag. Service account cần permission đúng trên bucket/topic/secret; 403 không đồng nghĩa lỗi nhất quán.

## 16. Những ngộ nhận dễ gây lỗi production

| Ngộ nhận | Thực tế |
|---|---|
| “Timeout nghĩa là server không xử lý” | Server có thể đã commit; client chỉ không biết kết quả |
| “Retry mọi exception là tốt” | Retry có thể nhân side effect, làm quá tải dịch vụ và vượt deadline |
| “SDK đã retry nên không cần idempotency” | Retry policy không tự xử lý tính đúng đắn nghiệp vụ |
| “Object storage strong consistency nghĩa là nhiều object có transaction” | Bảo đảm thường theo operation/object; không tự có transaction đa hệ thống |
| “Một project/Region thì mọi replica đều mới như nhau” | Location và kiểu replica mới quyết định độ trễ đồng bộ |
| “Hàng đợi FIFO bảo đảm mọi consumer exactly once” | Ordering/dedup có phạm vi; commit DB và ACK vẫn có thể tách rời |
| “@Transactional bao cả gửi SQS/PubSub/Service Bus” | Transaction manager của DB không tự atomic với các dịch vụ đó |
| “Nâng visibility timeout sẽ ngăn duplicate vĩnh viễn” | Crash/ACK loss vẫn gây giao lại; xử lý cần idempotent |
| “Đọc từ cache/replica luôn phù hợp cho mọi màn hình” | Quyết định nghiệp vụ có thể yêu cầu đọc mới nhất từ primary |
| “Circuit breaker giải quyết nguyên nhân lỗi” | Nó giới hạn ảnh hưởng; vẫn phải sửa và theo dõi downstream |
| “Secret manager đã quản lý rotation nên app tự đổi ngay” | Credential caching, connection pool và quy trình chuyển phiên bản cần thiết kế |

## 17. Checklist trước khi đưa tích hợp cloud lên production

- **Consistency contract:** ghi rõ service nào, operation nào bảo đảm dữ liệu mới tới đâu; xác định đường đọc primary, replica, cache, index.
- **Latency budget:** đặt deadline tổng và timeout từng tầng dựa trên p95/p99 cùng SLO; giám sát pool saturation.
- **Retry:** có tiêu chí lỗi retry được, backoff/jitter, giới hạn attempts; kiểm tra retry mặc định của SDK để tránh lồng nhau.
- **Idempotency:** mỗi nghiệp vụ có event/request ID ổn định, unique constraint, xử lý payload trùng key và xung đột đồng thời.
- **Messaging:** ACK sau commit, xử lý redelivery/duplicate/out-of-order, DLQ và quy trình replay an toàn.
- **Transactions:** dùng outbox/inbox hoặc Saga cho side effects xuyên hệ thống; không dựa vào @Transactional để atomic với broker.
- **Bảo mật:** role/managed identity/service account chỉ có quyền cần, endpoint/Region đúng, secret không bị ghi log.
- **Reliability controls:** circuit breaker, bulkhead, concurrency limit và fallback đúng nghiệp vụ.
- **Testing:** test mất response sau commit, timeout, retry storm, replica lag, duplicate, 403/429 và khôi phục trên staging.
- **Observability:** có metrics latency, retries, duplicates, DLQ, replica lag, backlog, reconciliation và trace gắn với event ID.

## 18. Tổng kết

Khi Spring Boot gọi dịch vụ managed từ xa, **tính nhất quán** quyết định dữ liệu nào có thể được nhìn thấy, **độ trễ** quyết định khi nào ứng dụng còn đủ thời gian hoàn thành yêu cầu, và **sự cố từng phần** tạo ra tình huống một bước thành công trong khi bước tiếp theo thất bại hoặc kết quả bị mất trên đường truyền. Không có một cấu hình timeout/retry duy nhất giải quyết được cả ba vấn đề.

Ứng dụng tích hợp AWS, Azure và Google Cloud an toàn cần thiết kế rõ **consistency contract → deadline → retry có giới hạn → idempotency → transaction/outbox → ACK → quan sát và phục hồi**. Khi hiểu từng lớp và kiểm thử các tình huống kết quả không xác định, nhóm phát triển có thể khai thác Spring Cloud và các dịch vụ managed mà vẫn giữ được tính đúng đắn của dữ liệu, hành vi có thể dự đoán và khả năng vận hành khi một thành phần cloud gặp sự cố.
