# Lỗi lan truyền và giới hạn phạm vi ảnh hưởng

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Khả năng chịu lỗi (Fault Tolerance)  
> **Trọng tâm:** Hiểu cách một lỗi cục bộ biến thành sự cố dây chuyền, thiết kế ranh giới cô lập và duy trì chức năng quan trọng khi một phần hệ thống gặp vấn đề.

## 1. Vì sao một lỗi nhỏ có thể làm hỏng cả hệ thống?

Trong kiến trúc phân tán, một request thường đi qua nhiều thành phần: API gateway, xác thực, dịch vụ nghiệp vụ, cơ sở dữ liệu, cache, message broker và dịch vụ bên thứ ba. Mỗi thành phần có thể lỗi riêng, nhưng **hậu quả thực tế phụ thuộc vào việc lỗi có vượt qua ranh giới của nó hay không**.

Giả sử trang đặt hàng hiển thị cả danh sách sản phẩm đề xuất. Dịch vụ Recommendations bị chậm. Nếu Checkout phải đợi Recommendations rồi mới tạo đơn, chức năng phụ đã trở thành điểm chặn của chức năng chính. Request bị giữ lâu, thread và connection tích tụ, hàng đợi tăng; cuối cùng Checkout cũng lỗi dù mã xử lý tạo đơn và cơ sở dữ liệu đơn hàng vẫn khỏe.

Hai khái niệm cần phân biệt:

- **Lỗi lan truyền (failure propagation):** trạng thái bất thường ở thành phần A làm thành phần B bị chậm, lỗi, quá tải hoặc tạo thêm lỗi ở nơi khác. Sự lan truyền có thể qua lời gọi trực tiếp, tài nguyên chia sẻ, hàng đợi, các đợt retry hoặc thay đổi cấu hình.
- **Phạm vi ảnh hưởng (blast radius):** tập người dùng, request, tenant, dịch vụ, vùng hạ tầng và chức năng bị tác động bởi một lỗi. Có thể mô tả theo số lượng, tỷ lệ hoặc nhóm đối tượng chịu tác động.

Ví dụ: một instance Recommendations hỏng khiến 1% request đề xuất nhận dữ liệu rỗng thì phạm vi ảnh hưởng nhỏ. Cùng lỗi đó làm nghẽn connection pool dùng chung, khiến mọi giao dịch thanh toán timeout thì phạm vi ảnh hưởng đã vượt xa thành phần hỏng ban đầu.

**Fault tolerance** không có nghĩa mọi request luôn thành công. Mục tiêu hợp lý là giữ lỗi trong ranh giới dự kiến, bảo vệ nghiệp vụ cốt lõi và phục hồi có kiểm soát.

## 2. Mô hình nguyên nhân → cơ chế lan truyền → hậu quả

~~~text
Client
  |
  v
API Gateway
  |
  v
Checkout ────────> Inventory ────────> Inventory DB
  |                     |
  |                     X  DB phản hồi rất chậm
  |                     |
  +──────> Payment      v
  |               Inventory giữ connection, request chờ
  +──────> Recommendations
                        |
            Checkout đợi Inventory / retry
                        |
             Request đang xử lý tăng
                        |
          Thread / connection / queue cạn
                        |
           Checkout lỗi trên diện rộng
~~~

Diễn tiến thường gặp:

1. **Sự kiện khởi đầu:** DB của Inventory bị lock, network bị đứt, pod chết hoặc một downstream trả lời chậm bất thường.
2. **Chờ đợi:** lời gọi đồng bộ không có timeout hợp lý; tài nguyên ở upstream tiếp tục bị chiếm trong lúc chờ.
3. **Khuếch đại:** nhiều caller retry đồng thời; mỗi request của người dùng sinh thêm nhiều request nội bộ.
4. **Cạn kiệt:** thread pool, connection pool, CPU, bộ nhớ, queue hoặc quota bị chiếm hết; request mới cũng chịu ảnh hưởng.
5. **Lan truyền ngang:** phần chức năng không liên quan sử dụng chung tài nguyên hoặc phụ thuộc upstream đã nghẽn.
6. **Phục hồi khó khăn:** khi downstream trở lại, backlog và các đợt retry có thể tiếp tục đè hệ thống; auto-scaling thiếu giới hạn đôi khi tăng áp lực vào dependency chung.

Các bước này không phải lúc nào cũng xuất hiện theo đúng thứ tự. Một lỗi cấu hình chung có thể đánh sập nhiều dịch vụ ngay lập tức; một sự cố mạng ngắn có thể chỉ gây mất vài request nếu cơ chế cô lập hoạt động tốt.

### Phân biệt bốn trạng thái

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| Fault | Điều kiện lỗi tiềm ẩn hoặc sự kiện bất thường | Một node DB mất kết nối |
| Error | Trạng thái bên trong đã sai lệch | Query trả lỗi, pool không lấy được connection |
| Failure | Hành vi quan sát từ bên ngoài không đáp ứng cam kết | API tạo đơn trả 5xx hoặc vượt hạn thời gian |
| Cascading failure | Failure ở một nơi gây thêm failure ở nơi khác | Checkout bị quá tải vì Inventory chậm |

Một timeout hay 5xx có thể là **triệu chứng** ở upstream; không nhất thiết là nguyên nhân gốc tại upstream đó.

## 3. Những con đường lan truyền phổ biến

### 3.1. Chuỗi gọi đồng bộ và fan-out

Mô hình A → B → C phụ thuộc vào độ trễ và khả dụng của các chặng. Trong fan-out A gọi song song B, C, D, tổng thời gian hoàn tất thường bị quyết định bởi nhánh chậm nhất **nếu A đợi tất cả các nhánh**. Fan-out cũng tăng số dependency mà mỗi request phải sử dụng.

Ví dụ lý tưởng với 10 dependency độc lập, mỗi dependency có xác suất đáp ứng thành công 99,9%, và request bắt buộc cả 10 thành công:

~~~text
P(thành công cả chuỗi) = 0,999 ^ 10 ≈ 99,0%
~~~

Đây là phép minh họa theo giả định độc lập; trong hệ thống thực tế, dependency thường có lỗi tương quan do dùng chung vùng mạng, database hoặc cấu hình. Không dùng công thức trên như dự báo SLA khi chưa kiểm tra giả định.

**Câu hỏi thiết kế:** nhánh nào bắt buộc để hoàn thành yêu cầu, nhánh nào có thể trả về sau, dùng cache, hoặc bỏ qua an toàn?

### 3.2. Cạn tài nguyên dùng chung

Một dependency chậm khiến request giữ thread, semaphore, connection hoặc memory lâu hơn. Nếu các chức năng dùng chung một pool, chức năng lỗi có thể lấy hết tài nguyên của chức năng khỏe.

Theo trực giác của Little's Law, tại trạng thái ổn định, lượng công việc đang nằm trong hệ thống xấp xỉ **tốc độ đến × thời gian xử lý**. Ví dụ 300 request/giây và thời gian chờ tăng lên 0,6 giây tương ứng khoảng 180 request đang chờ hoặc xử lý. Nếu còn xếp hàng, retry hoặc fan-out, nhu cầu tài nguyên thực tế có thể cao hơn. Con số này giúp giải thích tại sao tăng latency thường dẫn tới bão hòa trước khi xuất hiện nhiều lỗi trả về.

Các tài nguyên cần nhận diện: worker thread, HTTP connection, DB connection, executor queue, CPU quota, RAM, file descriptor, broker partition, cache hot key và giới hạn API bên thứ ba.

### 3.3. Retry storm và vòng phản hồi dương

Một request có tối đa hai lần retry có thể tạo **ba lần thử** đến downstream. Nếu 300 request/giây đồng thời đụng dependency hỏng, tải thử gọi có thể tiến gần 900 lần/giây khi retry diễn ra nhanh. Nếu gateway, service A và service B đều retry cùng một thao tác, số lần thử có thể nhân lên qua nhiều tầng.

Retry giúp khắc phục lỗi tạm thời khi được giới hạn đúng cách. Retry vô điều kiện trên timeout, 429 hoặc 503 có thể biến quá tải thành quá tải nặng hơn.

Đặc biệt nguy hiểm: client timeout nhưng server đã thực hiện thành công thao tác ghi. Retry thiếu **idempotency key** có thể tạo đơn, trừ tiền hoặc phát sự kiện trùng.

### 3.4. Hàng đợi bất đồng bộ và thông điệp độc

Async messaging tách thời gian sống của caller khỏi consumer nhưng không tự loại bỏ lỗi lan truyền.

- Consumer lỗi liên tục có thể khiến backlog và tuổi của message tăng.
- Một message độc (poison message) bị xử lý lại vô hạn có thể chiếm worker và làm chậm các message khỏe.
- Nhiều consumer cạnh tranh cùng DB có thể đẩy bottleneck sang DB.
- Retry queue không giới hạn có thể trở thành một kho công việc tồn đọng không thể xử lý kịp.

Cần giới hạn lần thử, trì hoãn hợp lý, nơi xử lý message không thành công cuối cùng (dead-letter queue), cơ chế replay có kiểm soát và idempotent consumer.

### 3.5. Hạ tầng, dữ liệu và cấu hình chia sẻ

Hai microservice tách code nhưng dùng chung một database cluster, schema, connection pool, cache cluster, secret, control plane hoặc network egress vẫn nằm chung một failure domain ở cấp đó.

Ví dụ một job báo cáo chạy query nặng trên DB giao dịch có thể khiến dịch vụ đặt hàng chậm. Một cấu hình retry sai được triển khai đồng loạt có thể gây lỗi đồng thời trên nhiều vùng. Tách service chỉ là một ranh giới logic; **cô lập thật phải xét cả tài nguyên vận hành**.

## 4. Định nghĩa phạm vi ảnh hưởng và failure domain

**Failure domain** là nhóm thành phần có khả năng cùng bị ảnh hưởng bởi một loại sự cố. Các ranh giới thường xét gồm:

| Cấp ranh giới | Ví dụ sự cố | Cách giới hạn tác động |
|---|---|---|
| Request | Một request có input lỗi hoặc timeout | Deadline, validation, cancellation |
| Thread/pool | Worker gọi API chậm chiếm hết pool | Bulkhead, bounded queue, concurrency limit |
| Instance/pod | Process crash hoặc memory leak | Replica, health check, pod resource limit |
| Service | Release lỗi toàn bộ instance | Canary, rollback, tách đường triển khai |
| Tenant/khách hàng | Một tenant phát sinh tải bất thường | Quota và phân vùng tài nguyên theo tenant |
| Database/shard | Query lock hoặc hot partition | Shard, read replica phù hợp, workload isolation |
| Zone | Mất một availability zone | Phân tán replica, điều hướng traffic theo zone |
| Region | Mất vùng hoặc dependency vùng | Multi-region khi RTO/RPO và chi phí yêu cầu |
| Chức năng nghiệp vụ | Recommendations hỏng | Degrade tính năng phụ, giữ Checkout hoạt động |

Không có một cách chia tuyệt đối đúng. Ví dụ cô lập theo tenant giúp giữ sự cố của tenant A không lấn sang tenant B, nhưng có thể tăng chi phí pool hoặc giảm hiệu suất sử dụng tài nguyên khi tải mất cân bằng.

### Đo blast radius cụ thể

Phạm vi ảnh hưởng nên được diễn tả bằng đại lượng có thể quan sát:

- **Theo request:** tỷ lệ request thất bại hoặc vượt deadline trong từng endpoint.
- **Theo người dùng/tenant:** số lượng và tỷ lệ user hay tenant chịu tác động.
- **Theo chức năng:** những nghiệp vụ bị mất hoàn toàn so với những tiện ích chỉ bị suy giảm.
- **Theo không gian:** số instance, shard, zone, region bị ảnh hưởng.
- **Theo thời gian:** thời gian phát hiện, thời gian cô lập và thời gian trở lại mức dịch vụ bình thường.

Ví dụ một lỗi Recommendations khiến 15% request nhận danh sách đề xuất rỗng, nhưng 0% request tạo đơn bị ảnh hưởng, là một kết quả cô lập chức năng có thể chấp nhận tùy yêu cầu sản phẩm. Ngược lại, cùng sự cố gây 20% timeout ở API thanh toán là dấu hiệu phạm vi ảnh hưởng đã vượt ranh giới dự định.

## 5. Lớp phòng vệ tại từng lời gọi

Không có một cơ chế đơn lẻ ngăn được mọi dạng cascading failure. Thực tế dùng nhiều lớp có mục tiêu rõ ràng.

### 5.1. Deadline và timeout budget

**Deadline** là thời điểm cuối cùng một thao tác còn có ý nghĩa. **Timeout** giới hạn thời gian đợi ở một bước. Nếu API cam kết đáp ứng trong 900 ms, các dịch vụ downstream không thể mỗi nơi tự đặt timeout 2 giây.

Ví dụ ngân sách minh họa cho đường tạo đơn tuần tự:

| Công đoạn | Ngân sách tối đa |
|---|---:|
| Xác thực | 100 ms |
| Kiểm tra tồn kho | 200 ms |
| Thanh toán | 250 ms |
| Ghi đơn / hoàn tất | 200 ms |
| Dự phòng mạng, queue, biến động | 150 ms |
| **Tổng** | **900 ms** |

Đây là ngân sách thiết kế, không phải số đo production. Với các nhánh gọi song song, tính theo critical path; không máy móc cộng toàn bộ thời gian của các nhánh. Truyền **remaining deadline** hoặc thời gian còn lại qua mỗi hop; downstream không nên bắt đầu thao tác chắc chắn vượt deadline còn lại.

Cần phân biệt timeout kết nối, timeout đọc/phản hồi, timeout toàn request và giới hạn thời gian lấy connection từ pool. Đặt timeout ở một lớp nhưng để lớp khác chờ vô hạn vẫn có thể làm cạn tài nguyên. Hủy request ở caller không đảm bảo công việc ở server dừng ngay: phải xét hỗ trợ cancellation của thư viện và downstream.

### 5.2. Bulkhead: chia khoang tài nguyên

Tên gọi mượn từ vách ngăn tàu: một khoang bị ngập không kéo chìm toàn bộ tàu.

Hai dạng quen thuộc:

- **Semaphore bulkhead:** giới hạn số lời gọi đồng thời đến một dependency; vượt ngưỡng thì từ chối sớm hoặc dùng fallback.
- **Thread-pool bulkhead:** mỗi nhóm công việc có executor và queue giới hạn riêng, giảm nguy cơ công việc chậm chiếm hết worker của công việc khác.

Ví dụ tách nhóm quan trọng Checkout/Payment khỏi Recommendations. Nếu Recommendations đạt 32 lời gọi đồng thời, request mới nhận danh sách trống hoặc đáp án cache; không được chiếm slot dành cho thanh toán. Giới hạn phải được tính theo **sức chứa thực tế của dependency**, số replica caller và headroom, vì 32 slot trên mỗi pod nhân với 20 pod có thể thành 640 lời gọi đồng thời.

Bulkhead đặt sai có thể chỉ chuyển bottleneck đến DB chung. Phải xác định tài nguyên nào thực sự được cô lập.

### 5.3. Circuit breaker: ngắt gọi dependency đang lỗi

Circuit breaker thường có ba trạng thái:

1. **Closed:** cho gọi bình thường và ghi nhận kết quả.
2. **Open:** khi vượt ngưỡng lỗi/slow-call đã cấu hình, từ chối nhanh lời gọi mới trong một khoảng nghỉ.
3. **Half-open:** cho một số request thử để xác định downstream đã phục hồi chưa, rồi đóng lại hoặc mở tiếp.

Circuit breaker giảm thời gian chờ vô ích, nhưng không thay thế timeout hoặc concurrency limit. Nếu chỉ dựa vào phần trăm lỗi mà lưu lượng quá thấp, tín hiệu có thể nhiễu; nếu chỉ dựa vào HTTP 5xx mà bỏ qua slow call, breaker có thể mở quá muộn. Thiết lập cửa sổ quan sát, số mẫu tối thiểu và thời gian mở theo đặc tính dịch vụ.

Circuit breaker xử lý tín hiệu lỗi, còn **bulkhead bảo vệ tài nguyên**. Hai cơ chế bổ trợ nhau.

### 5.4. Retry có giới hạn, exponential backoff và jitter

Chỉ retry khi lỗi **có khả năng phục hồi nhanh** và thao tác được phép thực hiện lại. Giới hạn số lần thử, tổng thời gian, số request retry đồng thời và ngân sách retry toàn hệ thống.

Ví dụ chuỗi trì hoãn cơ bản 100 ms → 200 ms → 400 ms có thể thêm **jitter**, tức độ ngẫu nhiên, để các caller không cùng thức dậy tại một thời điểm. Retry phải dừng khi hết deadline. Với 429 và Retry-After, tôn trọng chỉ dẫn thích hợp của downstream trong phạm vi deadline.

Đặt retry ở một tầng được chủ động chọn, tránh mỗi service đều tự retry nhiều lần. Với giao dịch có side effect, dùng idempotency key hoặc cơ chế deduplication và xác định rõ kết quả chưa biết khi timeout.

### 5.5. Load shedding, rate limit và backpressure

- **Rate limiting:** đặt giới hạn tốc độ request theo client, tenant, endpoint hoặc dependency; phản hồi phù hợp như 429 khi quá giới hạn chính sách.
- **Concurrency limiting:** giới hạn số request đang được xử lý hoặc đang chờ dependency; thường phản ánh áp lực thực tốt hơn chỉ giới hạn request/giây.
- **Load shedding:** bỏ/từ chối nhanh request ít ưu tiên khi hệ thống gần bão hòa, giữ năng lực cho nghiệp vụ quan trọng.
- **Backpressure:** điều chỉnh tốc độ producer theo năng lực consumer; trong luồng async dùng bounded queue, credit hoặc cơ chế pause; tránh buffer không giới hạn.

Từ chối có chủ đích đôi khi tốt hơn để mọi request xếp hàng rồi cùng timeout. Cần định nghĩa thứ tự ưu tiên nghiệp vụ và phản hồi rõ ràng cho client.

### 5.6. Fallback và graceful degradation

Fallback phù hợp khi dữ liệu dự phòng **không làm sai nghiệp vụ**:

- Recommendations lỗi → trả danh sách rỗng hoặc cache hợp lệ.
- Avatar service lỗi → hiển thị biểu tượng mặc định.
- Search suggestion lỗi → bỏ gợi ý, giữ chức năng tìm kiếm cơ bản.

Không được che giấu lỗi nghiệp vụ quan trọng:

- Payment không xác nhận → **không tự coi đã thu tiền**.
- Inventory không kiểm tra được → không tự khẳng định còn hàng nếu hợp đồng yêu cầu giữ hàng chắc chắn.
- Quyền truy cập chưa xác thực → không cho phép mặc định chỉ để giữ tỷ lệ thành công.

Fallback cần có giới hạn độ cũ của dữ liệu, cảnh báo khi đang được kích hoạt và metric riêng, nếu không hệ thống có thể “xanh” về HTTP 200 nhưng đang phục vụ kết quả suy giảm kéo dài.

## 6. Cô lập từ kiến trúc, không chỉ trong thư viện

### 6.1. Tách phụ thuộc bắt buộc và phụ thuộc tùy chọn

Phân loại từng dependency thành:

- **Critical:** kết quả không thể thiếu để đảm bảo tính đúng đắn, bảo mật hoặc toàn vẹn giao dịch.
- **Optional:** thiếu kết quả vẫn có thể trả lời đúng hợp đồng ở chế độ giảm chức năng.
- **Deferred:** công việc có thể chạy sau khi trả lời bằng event/job với khả năng retry, theo dõi và bù trừ phù hợp.

Mục tiêu là loại bỏ lời gọi đồng bộ không cần thiết khỏi đường nóng của một request. Ví dụ gửi email xác nhận không cần chặn phản hồi “đã tạo đơn”, miễn có outbox/event đáng tin cậy để không làm mất thông báo khi tiến trình gặp lỗi.

### 6.2. Cô lập workload và tenant

Một số cách triển khai:

- Pool/queue riêng cho API thời gian thực và batch job.
- Quota, concurrency limit, rate limit theo tenant hoặc tier.
- Tách read replica cho báo cáo nếu tính nhất quán cho phép; không dùng query báo cáo nặng trên primary giao dịch.
- Shard hoặc phân vùng theo tenant để giới hạn hot partition; đánh giá nguy cơ hot shard mới hình thành.
- Resource request/limit, priority và autoscaling policy theo loại workload.
- **Cell-based architecture:** chia tập người dùng/tenant thành các cell vận hành tương đối độc lập, mỗi cell có phiên bản service và tài nguyên thiết yếu riêng trong phạm vi cần thiết; một cell lỗi chỉ ảnh hưởng tập được phân vào cell đó.

Càng cô lập mạnh, vận hành càng tốn kém: nhân đôi hạ tầng, mất hiệu quả pooling, tăng phức tạp định tuyến và failover. Thiết kế ranh giới theo SLO và rủi ro, không phải cứ tách nhiều là tốt.

### 6.3. Cô lập thay đổi và triển khai

Một release lỗi có thể tạo blast radius lớn hơn cả lỗi runtime. Dùng canary, rollout theo cohort/zone, feature flag có khả năng tắt nhanh và rollback có thử nghiệm. Đừng cập nhật đồng thời toàn bộ instance/region khi cần giữ đường quay về phiên bản ổn định.

Failover cũng có thể gây lan truyền: dồn 100% traffic từ vùng hỏng sang vùng còn lại khi vùng đích chỉ đủ chịu tải bình thường sẽ tạo sự cố thứ hai. Phải đo headroom và xác định chính sách điều tiết tải khi chuyển vùng.

### 6.4. Cô lập dữ liệu và giao dịch

Microservices có schema hoặc database riêng giúp giảm một số dạng coupled failure, nhưng còn phụ thuộc vào cluster, hạ tầng và luồng sự kiện chung. Tránh giao dịch đồng bộ dài qua nhiều service khi có thể dùng state machine, outbox và saga cho quy trình phù hợp.

Saga không bảo đảm rollback tự động như một transaction DB đơn. Mỗi bước cần định nghĩa side effect, thao tác bù trừ, idempotency, trạng thái trung gian và khả năng người vận hành xử lý tình huống chưa xác định kết quả. Cô lập lỗi phải đi kèm **tính đúng đắn dữ liệu**, không chỉ khả dụng.

## 7. Ví dụ thiết kế: giữ Checkout hoạt động khi Recommendations lỗi

### Trước khi cô lập

~~~text
Checkout request
  ├─ Auth (bắt buộc)
  ├─ Inventory (bắt buộc)
  ├─ Payment (bắt buộc)
  └─ Recommendations (phụ)
          |
          └─ Timeout 3 s, retry 3 lần
                 |
                 └─ Giữ worker, gây queue và timeout toàn request
~~~

Ở mô hình này, latency của Recommendations có thể quyết định latency của Checkout dù dữ liệu đề xuất không liên quan đến việc ghi đơn.

### Sau khi cô lập

~~~text
Checkout request
  ├─ Auth, Inventory, Payment: deadline và chính sách lỗi riêng
  └─ Recommendations: giới hạn 250 ms
          |
          ├─ semaphore tối đa 32 call/instance
          ├─ circuit breaker + metric riêng
          ├─ không retry đồng bộ vô hạn
          └─ quá hạn / vượt limit / breaker open → []
                        |
                 Checkout vẫn hoàn tất nghiệp vụ chính
~~~

**Điều kiện đúng:** trả danh sách đề xuất rỗng là một hành vi được hợp đồng API và sản phẩm chấp nhận. Nếu response tạo đơn có trường Recommendations tùy chọn, nên thể hiện rõ trường đó có thể trống, thay vì giả vờ dữ liệu luôn đầy đủ.

### Ví dụ Java: giới hạn cạnh tranh và thời gian gọi dịch vụ phụ

Đoạn mã minh họa ý tưởng, sử dụng Java HttpClient và Semaphore của JDK. Nó tập trung vào ranh giới của một dependency tùy chọn; trong hệ thống thực tế còn cần logging, metrics, bảo mật endpoint, xử lý response schema và chính sách circuit breaker.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.Semaphore;

public final class RecommendationGateway {
    private final Semaphore slots = new Semaphore(32);
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(100))
            .build();

    public String getOptionalRecommendations(URI endpoint) {
        if (!slots.tryAcquire()) {
            return "[]"; // Không chiếm thêm tài nguyên khi quá tải
        }

        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofMillis(250))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            return response.statusCode() == 200
                    ? response.body()
                    : "[]";
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return "[]";
        } catch (IOException ex) {
            return "[]";
        } finally {
            slots.release();
        }
    }
}
~~~

Những giới hạn cần hiểu khi áp dụng ví dụ:

- **32 slot là trên một instance**, không phải giới hạn toàn cụm; nhân với số instance để xét tải tối đa có thể đổ về Recommendations.
- **250 ms** là timeout cho HTTP request này; chỉ nên cấu hình sau khi xác định deadline tổng, p95/p99 latency, giới hạn backend và độ nhạy với tail latency.
- Trả **[]** chỉ hợp lệ cho nhánh thực sự tùy chọn. Không dùng kiểu catch-and-default này cho thanh toán, phân quyền hoặc thao tác ghi quan trọng.
- Mã ví dụ chưa có circuit breaker, retry budget, metric, điều khiển tải toàn cluster hay kiểm soát kiểu dữ liệu; mỗi thành phần đó cần thiết kế và tích hợp riêng khi hệ thống yêu cầu.
- Cần ghi nhận số lần vượt slot, timeout, HTTP error và fallback để hệ thống vẫn thấy rõ Recommendations đang suy giảm.

### Về thứ tự thiết kế

Bắt đầu từ **hợp đồng nghiệp vụ**: khi dependency lỗi thì hành vi nào vẫn đúng? Sau đó mới chọn timeout, số slot, circuit breaker và giới hạn tải. Nếu bắt đầu từ thư viện mà không biết điều gì được phép degrade, cơ chế fault tolerance có thể che khuất lỗi dữ liệu nghiêm trọng.

## 8. Quan sát lỗi lan truyền bằng metric và tracing

Không thể kiểm soát blast radius nếu chỉ xem CPU trung bình và tỷ lệ 5xx toàn hệ thống. Cần phân tách theo endpoint, dependency, tenant, vùng, instance và mức độ ưu tiên.

| Tín hiệu | Giúp trả lời |
|---|---|
| Latency p50/p95/p99 theo hop | Nơi nào bắt đầu chậm, tail latency tăng ra sao? |
| In-flight requests và queue depth/age | Có đang tích tụ công việc chờ? |
| Thread, connection, semaphore utilization | Pool nào sắp cạn? |
| Retry attempts / original requests | Tải có đang bị khuếch đại? |
| Circuit breaker state, reject count | Lớp bảo vệ có kích hoạt đúng? |
| HTTP 429/503, timeout, cancellation | Từ chối sớm hay đang chờ đến khi quá hạn? |
| Fallback count và chất lượng output | Hệ thống có đang suy giảm âm thầm? |
| Message lag, DLQ, retry queue | Consumer có bắt kịp producer? |
| Error rate theo tenant/cell/zone | Lỗi có còn nằm trong phạm vi dự kiến? |
| Độ dài giai đoạn phục hồi | Backlog có tiếp tục gây quá tải sau khi dependency hồi phục? |

Distributed tracing giúp nối request từ caller đến dependency và chỉ ra đoạn chờ dài. Tuy nhiên, trace bị sampling hoặc thiếu span không đủ để chứng minh hệ thống không lỗi; cần kết hợp metric, log và dữ liệu nghiệp vụ.

Khi điều tra incident, dựng một dòng thời gian: **dependency nào đổi trạng thái trước, metric nào bắt đầu tăng, ranh giới nào bị vượt, cơ chế nào kích hoạt và vì sao chức năng khác bị ảnh hưởng**. Tỷ lệ 5xx ở Checkout có thể bắt đầu sau lỗi Inventory; nhầm symptom thành root cause có thể khiến sửa sai chỗ.

## 9. Kiểm chứng khả năng giới hạn phạm vi ảnh hưởng

Kiểm chứng là một phần của thiết kế độ tin cậy, cần thực hiện trong môi trường và phạm vi đã được kiểm soát.

### Trường hợp thử nghiệm gợi ý

| Tình huống cố ý tạo ra | Hành vi mong đợi |
|---|---|
| Recommendations timeout hoặc 503 | Checkout trả lời trong deadline, trường phụ fallback, metric ghi nhận |
| Inventory chậm hơn ngân sách | Checkout dừng chờ có giới hạn và báo trạng thái không thể xác nhận tồn kho; không tạo đơn sai |
| 30–50% request bị lỗi tạm thời | Retry không nhân tải quá ngân sách, có backoff và jitter |
| Tenant A tăng tải đột biến | Tenant B giữ SLO trong giới hạn thiết kế nhờ quota/partition |
| Một consumer gặp poison message | Message lỗi được cách ly/DLQ, các message hợp lệ vẫn xử lý |
| Một zone mất kết nối | Replica còn lại đủ headroom hoặc hệ thống shed tải có kiểm soát |
| Dependency hồi phục sau outage | Backlog được giải phóng có nhịp, không tạo đợt quá tải thứ hai |

Nên bắt đầu từ thử nghiệm trên một cell hoặc nhóm traffic nhỏ với giới hạn rõ ràng, chuẩn bị cách dừng và quan sát ảnh hưởng. “Tiêm lỗi thành công” không có nghĩa hệ thống hoạt động hoàn hảo; kết quả quan trọng là **nghiệp vụ nào suy giảm, trong bao lâu, và có vượt ranh giới dự kiến không**.

### Phân biệt tiêu chí kỹ thuật và tiêu chí nghiệp vụ

- **Kỹ thuật:** timeout có giới hạn, queue không tăng vô hạn, breaker mở đúng, không vượt giới hạn tài nguyên.
- **Nghiệp vụ:** thanh toán không bị nhân đôi, đơn hàng không ghi sai, tỷ lệ tạo đơn và thời gian đáp ứng của tenant khác nằm trong mức cho phép.

Một hệ thống có thể giảm 5xx bằng cách trả 200 với dữ liệu mặc định không hợp lệ. Vì vậy kiểm chứng phải bao gồm **độ đúng của kết quả**, không chỉ HTTP status.

## 10. Các lỗi thiết kế thường gặp

**“Thêm retry là sẽ chịu lỗi tốt hơn.”** Retry quá nhiều tầng, không có jitter hoặc idempotency, thường làm tăng tải vào dependency đang suy yếu. Chỉ retry lỗi phù hợp trong deadline và retry budget.

**“Có circuit breaker thì không cần timeout.”** Khi breaker đóng, caller vẫn có thể chờ vô hạn nếu timeout thiếu. Breaker cũng không giới hạn số connection đang dùng; cần bulkhead và bounded queue.

**“Tách microservice là đã cách ly.”** Shared DB, shared executor, cùng một cache hot key hoặc một rollout đồng loạt vẫn có thể là điểm lỗi chung.

**“Tăng số replica sẽ giải quyết mọi quá tải.”** Replica có thể tăng số connection và query đến DB đang nghẽn, khiến sự cố lan rộng. Xem bottleneck thật trước khi scale.

**“Fallback cứ trả 200 là tốt.”** Dữ liệu mặc định sai với thanh toán, tồn kho, xác thực hoặc quyền truy cập là lỗi nghiêm trọng hơn việc từ chối request.

**“Queue async bảo đảm không có cascading failure.”** Queue không giới hạn chỉ đổi sự cố timeout thành sự cố backlog, lag, memory hoặc replay storm.

**“Chỉ nhìn tỷ lệ lỗi tổng thể.”** Một tenant quan trọng bị lỗi 100% có thể bị che trong tỷ lệ lỗi chung rất thấp. Đo theo failure domain và chức năng.

**“Failover luôn tăng khả dụng.”** Chuyển tải sang vùng không đủ sức chứa sẽ tạo lỗi dây chuyền. Failover cần kiểm chứng capacity và điều kiện kích hoạt.

## 11. Một quy trình ra quyết định thiết kế

Khi thêm dependency mới vào request path, có thể trả lời tuần tự:

1. **Xác định nghiệp vụ:** kết quả của dependency là bắt buộc, tùy chọn hay có thể xử lý sau? Nếu nó lỗi, response nào là đúng?
2. **Vẽ dependency graph:** dịch vụ nào gọi ai, đồng bộ hay async, fan-out ở đâu, có tài nguyên chung nào?
3. **Đặt deadline đầu cuối:** phân bổ ngân sách cho các bước, xác định cơ chế truyền deadline và cancellation.
4. **Xác định failure domain:** request, tenant, pool, service, shard, zone hay region nào có thể cùng hỏng?
5. **Chặn lan truyền:** chọn bulkhead, concurrency limit, bounded queue, rate limit, backpressure, circuit breaker và retry budget đúng chỗ.
6. **Bảo vệ dữ liệu:** kiểm tra idempotency, deduplication, transactional outbox hoặc compensation khi có side effect.
7. **Thiết kế chế độ suy giảm:** chỉ dùng fallback đúng với hợp đồng; giám sát chất lượng kết quả.
8. **Quan sát và thử lỗi:** đặt metric theo ranh giới, diễn tập dependency chậm, quá tải và phục hồi; điều chỉnh ngưỡng từ số đo thực.

Không cần triển khai mọi cơ chế trong mọi dự án. Ví dụ dịch vụ đơn giản ít phụ thuộc có thể bắt đầu với timeout hợp lý, queue giới hạn và giới hạn concurrent call. Kiến trúc nhiều tenant với SLO nghiêm ngặt có thể cần cell isolation, quota phân lớp và cơ chế failover có kiểm soát.

## 12. Bài tập tình huống

**Bối cảnh:** hệ thống gồm Gateway → Order → Payment và Order → Notification. Notification gửi email qua bên thứ ba. Nhà cung cấp email bắt đầu trả lời sau 10 giây. Order có 100 worker và nhận 200 request/giây. Order hiện chờ Notification xong mới trả kết quả tạo đơn; timeout Notification là 15 giây.

**Câu hỏi tự suy luận:**

1. Lỗi bắt đầu từ đâu và theo con đường nào nó có thể làm Order cạn worker?
2. Vì sao thêm ba lần retry tức thì ở Order có thể làm tình hình nặng hơn?
3. Có thể thay đổi hợp đồng xử lý như thế nào để việc gửi email không quyết định khả năng tạo đơn?
4. Nếu đưa email vào queue, cần thiết kế thêm những gì để tránh message trùng, backlog vô hạn và poison message?
5. Sẽ dùng metric nào để chứng minh Payment và tạo đơn vẫn bình thường trong khi email suy giảm?

**Gợi ý lời giải:** nếu email chỉ là thông báo sau giao dịch, có thể ghi đơn và một outbox event trong cùng ranh giới transaction phù hợp; worker async gửi email với concurrency giới hạn, retry có backoff, idempotency/deduplication, DLQ và quan sát message age. API tạo đơn trả kết quả dựa trên trạng thái lưu đơn, không chờ dịch vụ email. Nếu email là điều kiện pháp lý bắt buộc trước khi hoàn tất một loại giao dịch cụ thể, phải điều chỉnh state machine và hợp đồng theo đúng yêu cầu đó, không áp dụng fallback mù.

## 13. Ghi nhớ cốt lõi

- **Lỗi cục bộ trở thành sự cố hệ thống khi nó chiếm tài nguyên hoặc phá vỡ phụ thuộc vượt khỏi ranh giới ban đầu.**
- **Blast radius** cần được xác định bằng người dùng, tenant, request, chức năng, vùng hạ tầng và thời gian bị ảnh hưởng.
- **Timeout/deadline** giới hạn thời gian chờ; **bulkhead/concurrency limit** giới hạn lượng tài nguyên; **circuit breaker** ngắt các lời gọi đang có nguy cơ lỗi; **rate limit/backpressure** điều tiết tải; **retry có ngân sách** chỉ hỗ trợ lỗi tạm thời phù hợp.
- **Graceful degradation** phải giữ tính đúng đắn nghiệp vụ. Chức năng phụ có thể tắt; dữ liệu thanh toán, quyền truy cập và toàn vẹn giao dịch không được bịa kết quả.
- **Thiết kế ranh giới, quan sát theo failure domain và kiểm chứng bằng sự cố có kiểm soát** mới cho biết kiến trúc đã thật sự hạn chế lỗi lan truyền hay chưa.
