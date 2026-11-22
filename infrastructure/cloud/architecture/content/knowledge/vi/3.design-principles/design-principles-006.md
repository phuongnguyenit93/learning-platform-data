# Thiết kế theo khả năng phục hồi thay vì giả định hạ tầng luôn hoạt động

Khi triển khai ứng dụng lên cloud, không thể mặc định máy chủ, mạng, ổ đĩa, vùng triển khai hay dịch vụ phụ thuộc sẽ luôn hoạt động. Một instance có thể bị thay thế, request có thể bị timeout, cơ sở dữ liệu có thể quá tải, một availability zone (AZ) có thể mất kết nối và một lần triển khai sai có thể ảnh hưởng tới mọi replica. Kiến trúc đáng tin cậy phải dự kiến những tình huống đó ngay từ lúc xác định yêu cầu nghiệp vụ.

Trong module **CLOUD_ARCHITECTURE**, nguyên lý này nối các quyết định về **mạng, compute, dữ liệu và mô hình triển khai** với khả năng đảm bảo dịch vụ cho người dùng. Mục tiêu không phải xây một hệ thống tuyên bố “không bao giờ lỗi”, mà là **giới hạn phạm vi ảnh hưởng, duy trì luồng quan trọng, bảo vệ dữ liệu và phục hồi trong thời hạn được chấp nhận**. Những quyết định đó cần đánh đổi với chi phí, bảo mật, khả năng mở rộng và vận hành theo tư duy Well-Architected.

## 1. Vì sao phải giả định lỗi sẽ xảy ra?

Một hành trình nghiệp vụ thường đi qua nhiều hệ thống:

~~~mermaid
flowchart LR
    U["Người dùng"] --> EDGE["DNS / CDN / WAF"]
    EDGE --> LB["Load balancer"]
    LB --> APP["Ứng dụng"]
    APP --> DB["Database"]
    APP --> CACHE["Cache"]
    APP --> THIRD["Dịch vụ bên ngoài"]
~~~

Một thành phần hoạt động kém có thể gây ảnh hưởng dây chuyền. Ví dụ, API thanh toán tăng độ trễ làm các thread ứng dụng chờ lâu; connection pool cạn; request tra cứu bình thường bắt đầu timeout dù database vẫn khỏe. Thêm nhiều instance có thể chưa giải quyết được nếu mọi instance cùng phụ thuộc API đó.

Thay vì hỏi “instance này có ổn định không?”, người thiết kế cần hỏi:

1. Khi một instance mất đột ngột giữa request, kết quả giao dịch thế nào?
2. Nếu dependency vẫn sống nhưng phản hồi chậm gấp mười lần, hệ thống có giới hạn thời gian chờ không?
3. Nếu một AZ bị cô lập, công suất và dữ liệu còn lại có đủ phục vụ hành trình cốt lõi không?
4. Khi client timeout nhưng giao dịch có thể đã thành công, làm sao tránh xử lý lặp?
5. Nếu xóa nhầm hoặc sao chép dữ liệu sai, có thể phục hồi từ đâu và mất bao lâu?
6. Ai phát hiện, quyết định failover và kiểm chứng phục hồi?

### Phân biệt reliability, availability và resilience

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Reliability – độ tin cậy** | Hệ thống thực hiện đúng chức năng đã cam kết theo thời gian và điều kiện xác định | Một đặt lịch chỉ được ghi nhận một lần, trạng thái đúng |
| **Availability – tính sẵn sàng** | Tỉ lệ thời gian hoặc request mà dịch vụ dùng được theo một định nghĩa đo | API đặt lịch đáp ứng mục tiêu SLO |
| **Fault tolerance – khả năng chịu lỗi** | Tiếp tục chức năng đã định khi một thành phần hỏng | Mất một instance nhưng load balancer dùng instance còn khỏe |
| **Resilience – khả năng phục hồi** | Hấp thụ, thích ứng và hồi phục sau gián đoạn | Tắt gợi ý cá nhân hóa khi hệ phụ lỗi rồi bật lại |
| **Disaster recovery (DR)** | Khôi phục sau sự cố lớn vượt phạm vi chịu lỗi thông thường | Chuyển sang region dự phòng sau sự cố diện rộng |

**Redundancy (dự phòng) là một công cụ, không phải kết quả cuối cùng.** Hai instance chung một database, cùng cấu hình sai hoặc cùng cạn hạn ngạch có thể đều ngừng phục vụ.

## 2. Xuất phát từ tác động nghiệp vụ và mục tiêu đo được

Không phải mọi chức năng đều cần phục hồi cùng tốc độ. Ứng dụng đặt lịch có thể cần bảo toàn thao tác **đặt lịch và thanh toán** ngay cả khi **gợi ý cá nhân hóa** hoặc **gửi email** gặp lỗi.

| Hành trình | Khi phụ thuộc lỗi | Điều bắt buộc bảo toàn |
| --- | --- | --- |
| Xem danh sách lịch trống | Có thể hiển thị cache có đánh dấu độ mới | Không dùng cache cũ làm bằng chứng chắc chắn còn chỗ |
| Tạo đặt lịch | Có thể trả trạng thái chưa xác định và cho tra cứu sau | Không đặt trùng, không mất trạng thái commit |
| Thanh toán | Tạm giữ trạng thái đang xác minh, đối soát khi cần | Không thu tiền hai lần hoặc báo thành công sai |
| Gợi ý cá nhân hóa | Ẩn tính năng hoặc dùng mặc định | Hành trình đặt lịch vẫn hoạt động |
| Gửi email xác nhận | Ghi event để gửi bất đồng bộ | Không làm thất bại một giao dịch đã commit chỉ vì email |

Đội sản phẩm và vận hành cần thỏa thuận:

- **SLI (Service Level Indicator):** đại lượng đo, ví dụ tỉ lệ request đặt lịch hợp lệ có kết quả đúng trong 2 giây.
- **SLO (Service Level Objective):** mục tiêu cho SLI trong cửa sổ, ví dụ 99,9% request hợp lệ trong 30 ngày. Phải định nghĩa request nào được tính, trường hợp lỗi phía người dùng, cửa sổ và điểm đo.
- **SLA (Service Level Agreement):** cam kết dịch vụ có thể kèm điều khoản hợp đồng, không nhất thiết trùng SLO kỹ thuật.
- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để phục hồi dịch vụ sau loại sự cố đã định.
- **RPO (Recovery Point Objective):** khoảng mất dữ liệu theo thời gian tối đa mục tiêu tại điểm phục hồi. RPO 5 phút nghĩa là trong phạm vi sự cố và cơ chế phục hồi đã xác định, tổ chức chấp nhận có thể mất các thay đổi từ tối đa khoảng 5 phút trước thời điểm sự cố.

Nếu SLO **theo thời gian** là 99,9% trong 30 ngày thì ngân sách gián đoạn tương đương:

\[
(1-0{,}999)\times30\times24\times60=43{,}2\text{ phút}.
\]

Nếu SLO được định nghĩa theo **tỉ lệ request tốt**, cần tính error budget bằng số request, không suy trực tiếp ra số phút downtime. Một failover hoàn tất trong 4 phút cũng không tự chứng minh đáp ứng SLO nếu xảy ra quá thường xuyên hoặc nhiều request tiếp tục lỗi sau đó.

**RTO/RPO cần gắn với failure domain.** Restart một instance có thể không làm mất dữ liệu; mất một AZ có thể cần database failover; mất cả region có thể cần khôi phục tại nơi khác, thời gian dài và nguy cơ mất các ghi chưa sao chép. Không nên đưa một cặp RTO/RPO chung chung rồi áp cho mọi sự cố.

## 3. Xác định failure domain và phụ thuộc dùng chung

Failure domain là tập thành phần có thể bị ảnh hưởng cùng lúc bởi một lỗi. Khi thiết kế, cần đánh dấu ranh giới từ process tới region và cả các phụ thuộc logic dùng chung.

| Failure domain | Ví dụ sự cố | Biện pháp phù hợp để đánh giá |
| --- | --- | --- |
| Process/container | Crash, deadlock, out-of-memory | Health check, restart, giới hạn tài nguyên |
| Host/node | Máy chủ hỏng hoặc bị thay thế | Nhiều replica, chống dồn replica trên một node |
| Availability zone | Mất kết nối hoặc lỗi hạ tầng cục bộ | Multi-AZ, load balancing, HA database |
| Region | Sự cố diện rộng hoặc gián đoạn truy cập | DR ở region khác, dữ liệu sao chép, chuyển hướng traffic |
| Dependency | API ngoài, cache, database chậm/quá tải | Timeout, retry có điều kiện, circuit breaker, bulkhead |
| Lỗi logic dùng chung | Release lỗi, secret hết hạn, cấu hình chung sai | Canary, rollback, feature flag, kiểm soát thay đổi |
| Dữ liệu/bảo mật | Xóa nhầm, corruption, mã độc, tài khoản bị chiếm | Backup độc lập, audit, phân quyền, phục hồi theo thời điểm |

**Multi-AZ không đồng nghĩa multi-region, và multi-region không tự phòng chống lỗi dữ liệu logic.** Một bản ghi sai có thể được nhân bản rất nhanh sang mọi vùng. Replica dùng để duy trì dịch vụ và backup dùng để phục hồi về trạng thái hợp lệ có nhiệm vụ khác nhau.

Ngoài những hộp chính trên sơ đồ, cần xem lại các điểm phụ thuộc như DNS, identity provider, kho secrets, CI/CD, hệ thống quản lý khóa, queue, API thanh toán và mạng ra ngoài. Hai cụm compute chạy ở hai AZ vẫn có thể đồng loạt hỏng nếu cùng cấu hình credential sai.

## 4. Triển khai compute và dữ liệu để chịu mất thành phần

Ứng dụng cần **có thể thay thế instance mà không làm mất trạng thái nghiệp vụ**: lưu session quan trọng tại kho được quản lý phù hợp, không tin vào ổ cứng cục bộ của container; triển khai qua cấu hình có thể lặp lại; phân biệt trạng thái *sẵn sàng nhận request* với trạng thái *process đang sống*.

~~~mermaid
flowchart TB
    C["Client"] --> LB["Edge / load balancer"]
    subgraph R["Region chính"]
      subgraph A["Availability Zone A"]
        APP1["Ứng dụng A"]
        PRIMARY["DB writer"]
      end
      subgraph B["Availability Zone B"]
        APP2["Ứng dụng B"]
        STANDBY["DB standby"]
      end
      QUEUE["Queue bền vững"]
      WORKER["Worker"]
    end
    LB --> APP1
    LB --> APP2
    APP1 --> PRIMARY
    APP2 --> PRIMARY
    PRIMARY <-->|"Replication / failover"| STANDBY
    APP1 --> QUEUE
    APP2 --> QUEUE
    QUEUE --> WORKER
~~~

Sơ đồ này là **ý tưởng thiết kế**, không phải cam kết sẵn sàng. Cần xác minh failover thực tế, quorum, độ trễ replication, cách ứng dụng phát hiện endpoint writer mới, khả năng tiếp tục hoạt động của queue và đường mạng khi một AZ biến mất.

Những quyết định cần làm rõ:

1. **Phân phối compute:** nhiều instance ở những failure domain khác nhau; load balancer chỉ chuyển traffic tới instance có readiness tốt.
2. **Readiness khác liveness:** readiness thất bại có thể khiến instance tạm ngừng nhận request; liveness thất bại kích hoạt restart. Không nên restart hàng loạt chỉ vì một dependency đang chậm.
3. **Graceful shutdown:** dừng nhận request mới, drain công việc đang xử lý, rồi đóng tài nguyên theo giới hạn thời gian.
4. **State tách khỏi compute:** session, tác vụ nền, idempotency key và dữ liệu nghiệp vụ nằm trong kho có độ bền, backup và khả năng phục hồi phù hợp.
5. **Công suất khi mất một thành phần:** autoscale mất thời gian, vì vậy phải chứng minh năng lực của phần còn lại trước khi năng lực mới được bổ sung.

Ví dụ tải đỉnh **600 RPS**, mỗi instance xử lý bền vững **120 RPS** tại SLO. Nếu chỉ xét thông lượng cần ít nhất \(600/120=5\) instance. Bố trí 3–3 trên hai AZ có 6 instance nhưng khi mất một AZ chỉ còn năng lực **360 RPS**. Nếu yêu cầu giữ đủ 600 RPS khi mất trọn một AZ, mỗi AZ cần **ít nhất 5 instance đã sẵn sàng** theo giả định đơn giản này. Chi phí dự phòng tăng, còn database, mạng và dependency phải được kiểm tra độc lập; các hệ thống có ba AZ có thể có phương án phân bố khác.

## 5. Thiết kế lời gọi có thể chịu timeout, chập chờn và quá tải

Trong hệ thống phân tán, **timeout không có nghĩa thao tác đã thất bại**. Ví dụ client gửi lệnh thanh toán, server đã trừ tiền nhưng response bị mất trên mạng. Nếu client gửi lệnh mới không có cơ chế chống trùng, người dùng có thể bị thu tiền hai lần.

### Timeout và deadline

Mọi kết nối ra ngoài phải có **giới hạn thời gian chờ rõ ràng**. Connect timeout khác với thời gian chờ response, và mỗi request cần tuân thủ deadline tổng. Không hợp lý nếu API cam kết phản hồi trong 2 giây nhưng cho phép dependency chiếm 5 giây rồi thử lại thêm vài lần.

Ví dụ ngân sách xử lý tối đa 2 giây của một API:

| Hoạt động | Ngân sách minh họa |
| --- | ---: |
| Kiểm tra và xác thực request | 200 ms |
| Database | 450 ms |
| Dịch vụ ngoài, bao gồm retry nếu có | 800 ms |
| Serialize, mạng và phần dự phòng | 550 ms |
| **Tổng** | **2.000 ms** |

Ngân sách chỉ là công cụ thiết kế, chưa chứng minh p99 latency đạt SLO; còn thời gian trong queue, phân bố request chậm, contention, garbage collection và giới hạn thực tế của downstream.

Ví dụ Java sử dụng HTTP client có timeout:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;

class PaymentClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(300))
            .build();

    HttpResponse<String> submitPayment(
            URI paymentUri, String jsonBody, UUID operationId
    ) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(paymentUri)
                .timeout(Duration.ofMillis(800))
                .header("Content-Type", "application/json")
                .header("Idempotency-Key", operationId.toString())
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Để có ý nghĩa, **operationId phải được lưu bền vững và sử dụng lại cho cùng giao dịch**, đồng thời dịch vụ thanh toán phải thực sự hỗ trợ idempotency key. Chỉ thêm một header không đủ tạo tính idempotent. Nếu lệnh gửi bị timeout, ứng dụng cần lưu trạng thái chưa xác định, truy vấn hoặc đối soát theo hợp đồng API. Ví dụ Java chỉ minh họa thiết lập timeout; triển khai thật còn phải xử lý mã phản hồi, ngoại lệ, truyền deadline, logging và bảo vệ dữ liệu nhạy cảm.

### Retry có điều kiện và không làm khuếch đại lỗi

Retry có thể khắc phục lỗi thoáng qua, nhưng phải tuân thủ những điều kiện sau:

- Chỉ retry thao tác có thể lặp lại an toàn hoặc có **idempotency** được đảm bảo bởi phía xử lý.
- Giới hạn số lần, dùng **exponential backoff** và **jitter** để tránh nhiều client retry cùng thời điểm.
- Tuân thủ deadline tổng, tín hiệu chờ retry từ downstream (nếu có) và ngưỡng tải của hệ thống.
- Đặt retry tại một tầng có chủ đích. Nếu ba tầng đều tự thử tối đa ba lần, một request ngoài cùng có thể dẫn đến \(3\times3\times3=27\) lần gọi ở tầng sâu nhất theo đường lỗi xấu nhất.
- Quan sát số lần retry, tỉ lệ thành công sau retry và thời gian chờ; một request “thành công” sau nhiều retry vẫn có thể cho thấy dependency không khỏe.

Những mẫu bổ trợ cần biết:

| Mẫu | Khi sử dụng | Giới hạn quan trọng |
| --- | --- | --- |
| **Circuit breaker** | Dependency lỗi/chậm liên tục, cần ngừng gửi request trong thời gian ngắn rồi thử phục hồi | Không thay timeout; cần đo và chọn ngưỡng phù hợp |
| **Bulkhead** | Tách pool kết nối, thread, concurrency giữa các luồng để lỗi không lan rộng | Phân chia sai vẫn có thể bỏ đói luồng quan trọng |
| **Rate limiting** | Giới hạn tốc độ đến/đi để bảo vệ backend | Không giải quyết được mọi cuộc gọi tốn tài nguyên khác nhau |
| **Backpressure** | Cho producer biết consumer đã đến giới hạn xử lý | Phải thiết kế quy tắc chờ, từ chối hoặc lưu đệm |
| **Load shedding** | Từ chối có kiểm soát request ít ưu tiên khi quá tải | Cần phân loại request và trả tín hiệu rõ cho client |
| **Queue** | Tách thời gian xử lý các tác vụ không bắt buộc đồng bộ | Có backlog, duplicate message và nguy cơ cạn dung lượng queue |

Một circuit breaker mở đúng lúc có thể chặn lỗi dây chuyền. Nhưng nếu ứng dụng vẫn giữ hàng nghìn request chờ trong memory, tải có thể tiếp tục tăng. Các giới hạn phải đồng bộ với nhau: timeout, concurrency, queue depth, retry budget và tốc độ downstream.

## 6. Giảm cấp chức năng có chủ đích (graceful degradation)

Resilience không đòi mọi tính năng đều chạy đầy đủ trong mọi hoàn cảnh. Khi một dependency phụ lỗi, hệ thống có thể vẫn giữ hành trình nghiệp vụ cốt lõi:

- Ẩn phần recommendation khi dịch vụ gợi ý không sẵn sàng.
- Hiển thị cache đã ghi rõ thời gian cập nhật cho dữ liệu có thể chấp nhận cũ.
- Đưa email, tạo báo cáo hoặc thu thập analytics sang queue để xử lý sau.
- Hạn chế truy vấn tìm kiếm phức tạp khi database quá tải, đồng thời dành tài nguyên cho giao dịch quan trọng.

**Không phải dữ liệu nào cũng được fallback.** Không dùng lịch trống từ cache cũ để bảo đảm còn chỗ, không báo thanh toán thành công khi chưa có xác nhận và không bỏ qua xác thực/ủy quyền vì hệ thống bảo mật đang lỗi. Với tác vụ nhạy cảm, từ chối có kiểm soát hoặc trả trạng thái “đang xác minh” an toàn hơn.

Mỗi fallback cần định nghĩa: điều kiện kích hoạt, độ cũ dữ liệu tối đa, hành vi người dùng nhìn thấy, chức năng bị hạn chế, cơ chế tắt fallback và tín hiệu chứng minh đã hồi phục. Khi mọi thành phần phục hồi, cần ngăn tình huống toàn bộ traffic cùng quay lại gây quá tải lần nữa.

## 7. Bảo vệ dữ liệu khi hệ thống gặp lỗi

Tăng số instance chỉ bảo vệ phần xử lý. Trong ứng dụng có giao dịch, mục tiêu cốt lõi còn là **không làm mất, nhân đôi hoặc ghi sai trạng thái nghiệp vụ**.

### Idempotency và kết quả không xác định

Idempotency nghĩa là thực hiện cùng một thao tác hợp lệ nhiều lần có **tác dụng nghiệp vụ cuối cùng như một lần**. Ví dụ API tạo đặt lịch có thể nhận một mã yêu cầu do client sinh và lưu cùng kết quả đã xử lý. Khi client retry với cùng mã, server trả lại kết quả tương ứng mà không tạo thêm booking.

Để có hiệu lực thực tế, cần xác định:

1. Phạm vi duy nhất của key, ví dụ theo người dùng và operation; thời hạn lưu key; chính sách nhận lại payload khác nhưng cùng key.
2. Cách đồng bộ key với commit nghiệp vụ để không có race condition giữa hai request đồng thời.
3. Phản hồi cho trạng thái đang xử lý, thành công, thất bại có thể retry hoặc kết quả chưa xác định.
4. Cách đối soát với hệ thống bên ngoài, nhất là khi giao dịch không nằm trọn trong một database.

### Transactional outbox và queue

Giả sử API tạo đặt lịch và sau đó phát sự kiện gửi email. Nếu database commit xong nhưng ứng dụng crash trước lúc publish, đơn đã tồn tại nhưng thông báo có thể bị mất. Mẫu **transactional outbox** ghi booking và event vào **cùng transaction database**, sau đó một relay đọc outbox để gửi sang queue.

~~~mermaid
sequenceDiagram
    participant Client as Người dùng
    participant API as Booking API
    participant DB as Database
    participant Relay as Outbox relay
    participant Q as Queue
    participant W as Notification worker
    Client->>API: POST booking + idempotency key
    API->>DB: Transaction: booking + outbox event
    DB-->>API: Commit
    API-->>Client: Đã tiếp nhận booking
    Relay->>DB: Đọc outbox chưa gửi
    Relay->>Q: Publish event
    Q-->>W: Deliver (có thể lặp)
    W->>W: Dedupe và thực hiện
~~~

Relay vẫn có thể publish thành công rồi crash trước khi đánh dấu đã gửi. Vì vậy message có thể **được giao lặp**, worker cần idempotent hoặc dedupe phù hợp. Cần theo dõi outbox age, queue lag, retry, dead-letter và công suất xử lý backlog. Không suy rằng có queue đồng nghĩa end-to-end “exactly once”; tính chất của broker có thể không bao trùm tác dụng phụ ở database khác hoặc dịch vụ email.

### Replication và backup phục vụ mục tiêu khác nhau

| Cơ chế | Lợi ích | Giới hạn / đánh đổi |
| --- | --- | --- |
| Sao chép đồng bộ/quorum | Giảm nguy cơ mất một số ghi đã xác nhận trong những kiểu hỏng nhất định | Tăng độ trễ; khi mất quorum có thể không tiếp tục ghi |
| Sao chép bất đồng bộ | Giảm chờ khi ghi và hỗ trợ khoảng cách địa lý lớn hơn | Replica trễ; failover có nguy cơ mất những ghi chưa sao chép |
| Multi-primary / active-active | Có thể phục vụ ghi ở nhiều nơi | Xung đột, ordering, network partition, tính nhất quán phức tạp |
| Backup và point-in-time recovery | Phục hồi trạng thái trước thao tác xóa nhầm hoặc ghi sai | Cần thời gian restore, lưu log và kiểm tra backup |

**RPO bằng 0 là yêu cầu mạnh:** phải chỉ rõ phạm vi sự cố, cơ chế xác nhận commit và giới hạn của sản phẩm dữ liệu. Không suy RPO bằng 0 chỉ vì có replica. Khi failover cần tránh **split-brain** (hai writer cùng nhận ghi) qua leader election, fencing, quorum hoặc cơ chế phù hợp; ứng dụng phải biết reconnect và xử lý các giao dịch đang dở.

Backup nên có lịch và retention rõ, phân quyền phục hồi, mã hóa, kiểm soát truy cập độc lập và khả năng lưu bất biến khi cần. **Replica không thay backup**, vì dữ liệu bị xóa nhầm có thể được đồng bộ sang replica ngay lập tức. Backup chỉ được coi là đáng tin khi restore thành công và dữ liệu sau restore đã được kiểm tra trong thời gian khôi phục mục tiêu.

## 8. Chọn chiến lược disaster recovery theo RTO/RPO

Khi một lỗi vượt qua failure domain được dự phòng, hệ thống cần kế hoạch **khôi phục thảm họa (DR)**. Những cách tiếp cận phổ biến:

| Chiến lược | Hạ tầng tại nơi dự phòng | Đặc điểm phục hồi | Chi phí và rủi ro |
| --- | --- | --- | --- |
| **Backup and restore** | Giữ backup; dựng lại hệ thống khi cần | Phải khôi phục dữ liệu, tài nguyên và xác minh | Chi phí chạy thấp nhưng thường cần RTO dài hơn |
| **Pilot light** | Duy trì thành phần dữ liệu và nền tảng tối thiểu | Khởi động các dịch vụ còn lại rồi chuyển traffic | Chi phí vừa phải, vẫn phụ thuộc thời gian khởi tạo |
| **Warm standby** | Duy trì hệ thống dự phòng quy mô nhỏ | Tăng công suất và chuyển traffic khi cần | Chi phí duy trì cao hơn, phải kiểm thử mở rộng |
| **Active-active** | Nhiều nơi cùng phục vụ traffic | Có thể chuyển traffic nhanh ở kịch bản phù hợp | Phức tạp về routing, xung đột ghi, consistency, chi phí |

Không thể gán một con số RTO/RPO cố định cho từng nhãn; kết quả phụ thuộc lượng dữ liệu, độ trễ replication, công suất còn lại, thời gian chuyển traffic và năng lực đội vận hành. Chuyển DNS **không tức thì** do TTL, cache resolver, các kết nối đang mở và cơ chế của client.

Một runbook DR nên trả lời:

1. **Khi nào kích hoạt:** sự cố nào, SLI nào, ai có thẩm quyền chuyển vùng?
2. **Cô lập nơi cũ:** làm sao ngăn hai database writer cùng tiếp nhận ghi nếu nơi cũ phục hồi một phần?
3. **Chọn điểm khôi phục:** đã đồng bộ đến đâu, những giao dịch nào phải đối soát?
4. **Dựng nơi mới:** mạng, compute, secrets, DNS, database, queue và quota cần sẵn sàng ra sao?
5. **Xác minh luồng chính:** phải thử đăng nhập, đọc và **ghi giao dịch** chứ không chỉ mở trang chủ.
6. **Chuyển lưu lượng và thông báo:** theo dõi lỗi, độ trễ, hiệu năng; có tiêu chí rollback rõ ràng.
7. **Failback:** xử lý những ghi mới ở nơi dự phòng trước khi đưa nơi cũ vào hoạt động trở lại.

**Bảo mật vẫn phải được duy trì trong DR:** quyền truy cập tối thiểu, kiểm soát khóa mã hóa, audit, hạn chế dữ liệu qua khu vực không được phép và bảo vệ backup. Một bản sao dự phòng mở quyền truy cập rộng để “khôi phục nhanh” có thể tạo rủi ro lớn hơn sự cố ban đầu.

## 9. Ví dụ xuyên suốt: nền tảng đặt lịch trên cloud

Giả sử đội phát triển đặt những mục tiêu **minh họa**, cần xác minh với đơn vị nghiệp vụ và load test trước khi cam kết:

| Hành trình / sự cố | Mục tiêu giả định |
| --- | --- |
| API đặt lịch | 99,9% request hợp lệ có kết quả đúng trong ngưỡng latency đã định, đo theo cửa sổ 30 ngày |
| Mất một instance ứng dụng | Dịch vụ còn hoạt động ở instance khác, lỗi ngắn hạn nằm trong error budget |
| Mất một AZ | RTO mục tiêu 5 phút cho hành trình đặt lịch, dữ liệu không mất theo phạm vi cam kết của database |
| Mất region | RTO mục tiêu 60 phút, RPO mục tiêu 5 phút |
| Dịch vụ email ngừng | Booking vẫn commit, sự kiện được lưu để xử lý khi email phục hồi |

Một hướng thiết kế là compute chạy nhiều AZ phía sau load balancer, database hỗ trợ HA/failover, queue bền vững cho tác vụ nền, backup riêng với quy trình restore, và giám sát gắn với hành trình người dùng. Ngoài sơ đồ, cần xác minh route mạng, quota, secret, identity provider và khả năng vận hành khi một phần control plane không truy cập được.

### Kịch bản A: crash instance khi đang xử lý booking

Health check và load balancer nhận biết instance lỗi trong khoảng thời gian đã kiểm chứng. Traffic mới chuyển sang các instance còn lại; scheduler khởi tạo instance thay thế nếu cần. Request đang thực hiện có thể bị mất response. Client gửi lại với **cùng idempotency key** hoặc tra cứu kết quả đã tạo. Hệ thống theo dõi error rate, tail latency và khả năng chịu tải của những instance còn lại.

Nếu session quan trọng chỉ nằm trong RAM của instance vừa hỏng, người dùng có thể bị mất phiên. Nếu backend giữ lock nghiệp vụ ở bộ nhớ cục bộ, hai instance có thể xử lý cùng một booking. Cần thiết kế trạng thái và kiểm soát đồng thời phù hợp; chỉ tăng replica không giải quyết được những vấn đề này.

### Kịch bản B: dịch vụ email ngừng 30 phút

Booking vẫn được ghi và event đi vào outbox/queue. Worker retry có backoff và giới hạn; hàng đợi được quan sát bằng queue depth/lag, dead-letter và tốc độ xử lý. Khi dịch vụ email trở lại, worker tiêu thụ backlog **theo tốc độ được kiểm soát** để không tạo đợt quá tải mới. Consumer cần cơ chế chống gửi trùng hoặc có cách chấp nhận và xử lý duplicate theo hợp đồng nghiệp vụ.

### Kịch bản C: cổng thanh toán timeout

Client nhận trạng thái **“đang xác minh thanh toán”** cùng mã tra cứu. Hệ thống giữ key cho cùng operation, đối soát với cổng thanh toán và xử lý callback/webhook đến muộn hoặc lặp. Chỉ chuyển sang “đã thanh toán” khi có bằng chứng xác thực. Timeout không đủ chứng minh giao dịch đã thất bại, nên việc phát sinh lệnh thanh toán thứ hai với key khác có thể gây thu tiền hai lần.

### Kịch bản D: mất toàn bộ AZ

Ứng dụng ở AZ còn lại phải có năng lực thực; database và queue phải còn đường truy cập; failover writer, DNS/endpoint resolution và connection pool phải phục hồi. Nên đo thời gian **từ lúc hành trình đặt lịch bắt đầu lỗi đến lúc hoạt động bình thường trở lại**, vì database có thể chuyển writer trong một phút nhưng ứng dụng vẫn lỗi nhiều phút nếu giữ kết nối và endpoint cũ.

### Kịch bản E: region chính ngừng hoạt động

Đội vận hành kích hoạt DR, xác minh thời điểm bản sao dữ liệu gần nhất, cô lập writer cũ tránh split-brain, khởi tạo hoặc mở rộng nơi dự phòng và kiểm thử thao tác đọc/ghi. Tiếp theo chuyển traffic và đo **RTO/RPO thực tế** so với mục tiêu 60/5 phút. Nếu không đạt, phải điều chỉnh thiết kế hoặc thỏa thuận nghiệp vụ; không nên báo thành công chỉ vì landing page hiển thị.

## 10. Quan sát và vận hành cũng là thành phần của resilience

Một hệ thống có replica, autoscale và backup nhưng thiếu tín hiệu cảnh báo, người trực xử lý và runbook vẫn có thể phục hồi rất chậm. Observability cần phản ánh **trải nghiệm của người dùng**, không chỉ trạng thái “xanh” của hạ tầng.

| Tín hiệu | Ví dụ cần đo | Ý nghĩa |
| --- | --- | --- |
| **Traffic** | RPS theo endpoint, AZ, region và hành trình | Có dồn traffic vào phần còn sống? |
| **Errors** | 5xx, timeout, lỗi nghiệp vụ, kết quả chưa xác định | Người dùng bị ảnh hưởng đến đâu? |
| **Latency** | p50, p95, p99; thời gian queue wait | Có suy giảm dần trước khi lỗi hẳn? |
| **Saturation** | CPU/RAM, connection pool, thread pool, IOPS, queue depth | Còn bao nhiêu công suất dự phòng? |
| **Data health** | Replica lag, backup age, outbox lag, restore success | Có nguy cơ mất dữ liệu hoặc event? |
| **Recovery** | Phát hiện lỗi, failover duration, rollback duration | Có đáp ứng RTO đã đặt? |

Cảnh báo nên ưu tiên **tác động người dùng** và **tốc độ tiêu thụ error budget**. CPU 80% tự nó chưa chứng minh một sự cố, trong khi tỉ lệ request đặt lịch lỗi tăng đột biến cần được xử lý ngay cả khi CPU còn thấp. Distributed tracing với correlation ID giúp lần theo request qua API, database, queue và dependency. Log và trace cần tránh ghi token, mật khẩu hay dữ liệu thanh toán nhạy cảm.

Runbook thực tế phải giúp người trực trả lời: xem dashboard nào; khi nào rollback, scale out hoặc chuyển vùng; cách kiểm tra dữ liệu; ai có quyền phê duyệt thay đổi; tiêu chí đóng sự cố là gì. Sau sự cố, một postmortem hướng vào nguyên nhân hệ thống giúp cải tiến quy trình, cảnh báo và thiết kế.

## 11. Thử lỗi có chủ đích để kiểm chứng giả định

Load test trả lời hệ thống có đủ năng lực trong điều kiện bình thường không. **Resilience test** trả lời khi một phần hỏng, chức năng nào còn chạy, mất bao lâu để khôi phục và dữ liệu có còn đúng không.

| Phép thử | Kỳ vọng cần xác định trước | Bằng chứng đo |
| --- | --- | --- |
| Kill một instance ở tải đại diện | Traffic chuyển sang instance còn khỏe | Error rate, tail latency, session loss, thời gian phục hồi |
| Tăng độ trễ một dependency lên vài giây | Timeout và circuit breaker ngăn cạn tài nguyên | Thread/connection usage, retry, rejected requests |
| Ngắt kết nối tới database writer | Failover và reconnect theo thiết kế | Thời gian ghi hoạt động lại, giao dịch chưa xác định |
| Dừng email worker | Booking tiếp tục, backlog tích lũy có kiểm soát | Queue depth, lag, dead-letter, drain time |
| Phát callback thanh toán lặp | Không ghi nhận hoặc thu tiền hai lần | Idempotency, trạng thái giao dịch, audit |
| Restore từ backup | Dữ liệu đúng và có thể sử dụng trong RTO/RPO | Restore duration, điểm phục hồi, kiểm tra tính toàn vẹn |
| Mất một AZ hoặc region trong môi trường cho phép | Các hành trình được cam kết phục hồi đúng hạn | SLI/SLO tại client và RTO/RPO thực đo |

Một quy trình diễn tập hợp lý:

1. **Đặt giả thuyết:** “Mất một instance không làm gián đoạn booking vượt error budget đã định”.
2. **Xác lập trạng thái ổn định:** đo hành trình và tải trước khi thử.
3. **Chọn phạm vi an toàn:** bắt đầu với staging hoặc một phạm vi nhỏ, có điều kiện dừng và kế hoạch rollback.
4. **Tiêm lỗi rõ ràng:** crash process, delay, packet loss, cạn tài nguyên hoặc failover có kiểm soát.
5. **Đo tác động đầu cuối:** từ client đến database và tác vụ nền; kiểm tra cả tính đúng đắn dữ liệu.
6. **Sửa và thử lại:** lưu bằng chứng, cập nhật runbook, cấu hình và năng lực dự phòng.

Thử nghiệm trong staging không tự chứng minh production sẽ giống hệt vì tải, dữ liệu và quota khác nhau. Nếu diễn tập production, cần phạm vi giới hạn, người chịu trách nhiệm và khả năng dừng nhanh. Một bài chaos test “không gây lỗi gì” cũng vô nghĩa nếu thành phần được thử không nằm trên đường nghiệp vụ quan trọng.

## 12. Đánh đổi theo các trụ cột Well-Architected

| Quyết định | Lợi ích phục hồi | Chi phí / giới hạn |
| --- | --- | --- |
| Multi-AZ | Giảm phụ thuộc một failure domain | Tài nguyên dự phòng, lưu lượng liên AZ, độ trễ replication |
| Multi-region | Giảm phụ thuộc một khu vực địa lý | Routing, consistency, tuân thủ lưu trữ, vận hành phức tạp |
| Replication đồng bộ | Giảm nguy cơ mất một số ghi đã commit | Độ trễ ghi tăng, cần quorum để tiếp tục ghi |
| Retry | Hấp thụ một số lỗi thoáng qua | Retry storm, tăng tải và trùng tác dụng phụ |
| Queue | Tách thời điểm xử lý các tác vụ | Backlog, duplicate delivery, thời gian hoàn thành tăng |
| Cache | Giảm tải dependency và latency | Stale data, invalidation, cache stampede |
| Graceful degradation | Giữ hành trình ưu tiên khi phụ thuộc lỗi | Giảm chức năng, phải bảo vệ tính đúng đắn |
| Warm standby | Có thể rút ngắn RTO | Chi phí duy trì liên tục, cần diễn tập failover |
| Backup độc lập | Khôi phục sau xóa nhầm hoặc corruption | Chi phí lưu giữ, restore và kiểm thử định kỳ |

Đánh giá độ tin cậy phải đi kèm **bảo mật**, **hiệu năng**, **chi phí**, **vận hành** và **tính bền vững**. Số replica cao chỉ phù hợp nếu có giá trị nghiệp vụ tương xứng; tuy nhiên giảm dự phòng quá mức cũng có thể gây thiệt hại lớn hơn tiền tiết kiệm. Hãy dùng SLO, RTO/RPO và thử nghiệm để lựa chọn mức phức tạp có thể duy trì được.

### Danh sách câu hỏi khi review thiết kế

- Đã phân biệt hành trình bắt buộc sống sót và chức năng có thể giảm cấp chưa?
- SLO, RTO, RPO có phạm vi, đơn vị, người chịu trách nhiệm và cách đo rõ chưa?
- Khi mất một instance hoặc AZ, công suất thực tế của phần còn lại có đủ không?
- Timeout, retry, circuit breaker và giới hạn concurrency có được cấu hình nhất quán không?
- API ghi có idempotency; các giao dịch với bên ngoài có cơ chế đối soát không?
- Queue, database, cache, DNS, secrets và hệ thống xác thực có được tính trong bản đồ phụ thuộc không?
- Backup có độc lập, mã hóa và đã từng restore thành công đúng thời hạn chưa?
- Có cảnh báo dựa vào trải nghiệm người dùng, runbook, rollback và diễn tập thực tế không?

## 13. Bài tập tự kiểm tra

Một ứng dụng có tải cao điểm **800 RPS**. Kết quả benchmark cho thấy mỗi instance phục vụ bền vững **200 RPS tại SLO yêu cầu**. Ứng dụng chạy trong hai AZ và phải tiếp tục xử lý **800 RPS** khi một AZ mất hoàn toàn. Giả sử database và mạng vẫn đủ năng lực, chưa tính thêm hệ số dự phòng.

**Câu 1:** Cần tối thiểu bao nhiêu instance trong mỗi AZ?

**Lời giải:** Sau khi một AZ hỏng, AZ còn lại cần \(800/200=4\) instance. Vì vậy cần tối thiểu **4 instance đã sẵn sàng ở mỗi AZ, tổng 8**, theo giả định mỗi AZ độc lập về compute. Autoscale bổ sung công suất sau khi sự cố xảy ra chưa đủ để bảo đảm tải tức thời.

**Câu 2:** Nếu database writer chỉ đặt trong một AZ, phương án trên có bảo đảm hành trình đặt lịch không gián đoạn khi mất AZ không?

**Lời giải:** Không. Nếu AZ chứa database bị mất, compute ở AZ kia cũng không thể hoàn tất giao dịch cần dữ liệu. Cần cơ chế database HA/failover, chiến lược đồng bộ và kiểm thử RTO/RPO toàn bộ hành trình.

**Câu 3:** Worker email dừng 20 phút. Có nên rollback đơn đặt lịch vừa commit không?

**Lời giải:** Nếu email không phải điều kiện bắt buộc của giao dịch, có thể commit đơn, lưu sự kiện bền vững qua outbox/queue và gửi sau. Cần theo dõi backlog và tránh gửi trùng khi worker phục hồi.

**Câu 4:** Client gửi thanh toán rồi nhận timeout. Có nên tạo lệnh mới với idempotency key khác không?

**Lời giải:** Không. Lệnh đầu có thể đã thành công. Cần giữ mã giao dịch ban đầu, truy vấn/đối soát theo hợp đồng API và chỉ xác nhận trạng thái khi có bằng chứng đáng tin cậy.

Khi trình bày phương án kiến trúc, hãy luôn chỉ ra **lỗi nào hệ thống chịu được, lỗi nào cần phục hồi, dữ liệu nào phải bảo vệ, phép đo nào chứng minh mục tiêu và chi phí vận hành đi kèm**. Đó là cách chuyển nguyên lý thiết kế theo khả năng phục hồi thành các quyết định có thể kiểm chứng.
