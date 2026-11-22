# Phân chia thành phần theo khả năng mở rộng và chu kỳ thay đổi

Khi thiết kế ứng dụng trên cloud, câu hỏi “nên có bao nhiêu service?” thường được đặt quá sớm. Một câu hỏi hữu ích hơn là: **những phần nào chịu tải khác nhau, thay đổi với nhịp khác nhau và cần được phát triển, triển khai, vận hành độc lập đến mức nào?** Trả lời được câu hỏi này mới có cơ sở chọn mô hình ứng dụng, xác định ranh giới thành phần và bố trí compute, mạng, dữ liệu.

Trong **CLOUD_ARCHITECTURE**, phân chia thành phần là một quyết định kiến trúc liên quan đồng thời đến **khả năng mở rộng, độ tin cậy, bảo mật, chi phí và vận hành**. Không có quy tắc rằng ứng dụng cloud bắt buộc phải là microservices. Một **modular monolith** được tổ chức tốt vẫn có thể đáp ứng yêu cầu của nhiều sản phẩm; các dịch vụ tách riêng đem lại lợi ích khi nhu cầu mở rộng hoặc thay đổi độc lập đủ lớn để bù cho chi phí của một hệ thống phân tán.

Chủ đề này tập trung vào cách xác định **ranh giới chức năng, ranh giới tài nguyên và ranh giới triển khai**, sau đó đánh giá xem chúng nên trùng nhau hay tách nhau trong từng giai đoạn phát triển.

## 1. Ba loại ranh giới cần phân biệt

Một **module** là đơn vị tổ chức mã nguồn và quy tắc phụ thuộc. Một **dịch vụ** là đơn vị cung cấp năng lực thông qua giao diện/contract và có thể có vòng đời chạy riêng. Một **deployment unit** là đơn vị có thể phát hành, mở rộng và rollback như một khối, chẳng hạn một ứng dụng container, function hoặc service.

Ba khái niệm liên quan với nhau nhưng **không bắt buộc trùng nhau**:

| Ranh giới | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Chức năng/nghiệp vụ** | Ai sở hữu quy tắc nghiệp vụ và dữ liệu của phần này? | Đặt chỗ, thanh toán, tìm kiếm |
| **Tài nguyên/khả năng mở rộng** | Phần này cần loại và lượng tài nguyên riêng nào? | Tìm kiếm cần nhiều CPU/RAM; xử lý ảnh cần worker; booking cần database giao dịch |
| **Thay đổi/triển khai** | Phần này phát hành, kiểm thử, rollback và chịu sự cố độc lập đến mức nào? | Luật khuyến mại thay đổi hằng ngày; lõi thanh toán thay đổi thận trọng |

Một service có thể gom nhiều module nếu chúng luôn thay đổi và triển khai cùng nhau. Ngược lại, cùng một năng lực nghiệp vụ có thể có **nhiều deployment unit** cho API, worker nền và tác vụ theo lịch khi đặc tính tải khác nhau. Không nên coi mỗi bảng dữ liệu, mỗi HTTP endpoint hoặc mỗi class là một microservice.

### Minh họa trên một ứng dụng đặt chỗ

~~~mermaid
flowchart LR
    Client["Ứng dụng khách"]
    Client --> Gateway["API / BFF"]
    subgraph Core["Nghiệp vụ giao dịch"]
        Booking["Đặt chỗ"]
        Payment["Thanh toán"]
    end
    subgraph Read["Truy vấn / khám phá"]
        Catalog["Danh mục"]
        Search["Tìm kiếm"]
    end
    subgraph Async["Xử lý nền"]
        Notify["Thông báo"]
        Media["Xử lý ảnh"]
    end
    Gateway --> Booking
    Gateway --> Catalog
    Gateway --> Search
    Booking --> Payment
    Booking --> Notify
    Catalog --> Media
~~~

Sơ đồ mô tả **các năng lực logic**, chưa khẳng định chúng phải chạy thành sáu service. Đầu tiên cần chứng minh tải, chu kỳ thay đổi, tính nhất quán dữ liệu và mục tiêu độ tin cậy của từng năng lực.

## 2. Bắt đầu từ hành trình người dùng và ranh giới nghiệp vụ

Thiết kế bắt đầu bằng việc liệt kê những hành trình cụ thể: tìm chỗ, xem thông tin, giữ chỗ, thanh toán, hủy chỗ, gửi xác nhận, cập nhật hình ảnh. Với mỗi hành trình, xác định quy tắc nghiệp vụ, dữ liệu cần thiết, yêu cầu nhất quán và thành phần có quyền quyết định kết quả.

Ví dụ, hành trình đặt chỗ thường cần **kiểm tra khả dụng và ghi nhận reservation một cách nhất quán**. Nếu chia kiểm tra chỗ trống và ghi đặt chỗ thành hai service độc lập mà không có giao thức chống tranh chấp, có thể phát sinh đặt chỗ trùng. Trong khi đó, email xác nhận không nhất thiết phải nằm trong transaction tạo reservation vì có thể được gửi sau.

### Dùng bounded context để định hình trách nhiệm

Một *bounded context* là phạm vi mà trong đó thuật ngữ, quy tắc và mô hình dữ liệu có nghĩa nhất quán. Ví dụ:

- **Catalog** chịu trách nhiệm mô tả chỗ ở, tiện nghi và hình ảnh đã được công bố.
- **Availability/Booking** chịu trách nhiệm quy tắc giữ chỗ, xung đột lịch và trạng thái reservation.
- **Payment** chịu trách nhiệm lệnh thu/hoàn tiền, trạng thái thanh toán và đối soát.
- **Notification** chịu trách nhiệm mẫu thông báo, kênh gửi, lịch sử gửi và retry.

Một bounded context **có thể là module trong monolith trước khi trở thành service**. Lợi ích của bước này là có ranh giới sở hữu rõ mà chưa phải trả chi phí gọi qua mạng, phân tán dữ liệu và điều phối phát hành.

Khi xem xét một ranh giới, nên hỏi:

1. Có **quy tắc nghiệp vụ độc lập** và người sở hữu rõ ràng không?
2. Có cần **transaction mạnh** với thành phần khác ở phần lớn request không?
3. Có thể mô tả hợp đồng bằng API hoặc event ổn định không?
4. Một thay đổi của phần này có thường xuyên đòi sửa code của phần kia không?
5. Khi thành phần lỗi, có thể giảm cấp hoặc cô lập ảnh hưởng ở phần còn lại không?

Nếu hai thành phần luôn phải cập nhật cùng nhau để duy trì một bất biến giao dịch, tách chúng quá sớm dễ tạo ra một **distributed monolith**: nhiều tiến trình nhưng vẫn liên kết chặt về dữ liệu, triển khai và độ tin cậy.

## 3. Phân tích hồ sơ tải để tìm nhu cầu mở rộng độc lập

Khả năng mở rộng là lý do quan trọng để chia deployment unit khi các phần **tiêu thụ tài nguyên khác nhau hoặc chịu đỉnh tải không đồng thời**. Nên lập hồ sơ theo năng lực, không chỉ tính RPS của toàn ứng dụng.

| Năng lực | Loại tải thường gặp | Dạng mở rộng cần cân nhắc | Điểm nghẽn có thể gặp |
| --- | --- | --- | --- |
| Danh mục/trang chi tiết | Nhiều lần đọc, dễ cache, payload thay đổi | CDN/cache, thêm API replica | Egress, cache miss, DB read |
| Tìm kiếm và lọc | Đọc nhiều, truy vấn phức tạp | Scale index/search cluster độc lập | CPU, RAM, index freshness |
| Đặt chỗ | Ghi giao dịch, yêu cầu chống trùng | Scale API có kiểm soát; tối ưu giao dịch | Lock, DB writer, contention |
| Thanh toán | Gọi hệ thống ngoài, thời gian phản hồi biến động | Cô lập pool kết nối và concurrency | Latency, rate limit bên thứ ba |
| Resize ảnh | CPU/I/O nặng, chạy nền, đầu vào dồn cục | Worker autoscale theo backlog | CPU, memory, object storage |
| Email/notification | Tác vụ nền có thể dồn sau chiến dịch | Worker theo queue và quota | Hạn mức provider, retry storm |

Các số liệu quan trọng bao gồm **request/s**, **công việc/s**, **CPU giây/job**, **RAM/job**, **thời gian xử lý**, **độ trễ p95/p99**, **queue depth/lag**, **database QPS/IOPS**, **network egress** và **tốc độ tăng trưởng**. Hai phần có cùng RPS vẫn có nhu cầu compute hoàn toàn khác nhau.

### Ví dụ định lượng: tách worker xử lý ảnh

Giả sử một ứng dụng có tải API ổn định và phát sinh **12.000 ảnh/ngày**. Mỗi ảnh cần trung bình **2 CPU giây** để tạo nhiều kích cỡ; một chiến dịch nhập dữ liệu khiến **6.000 ảnh đến trong 15 phút**. Đây là số minh họa, cần đo CPU, memory và I/O thực tế.

- Tổng nhu cầu xử lý mỗi ngày: \(12.000 \times 2 = 24.000\) CPU giây/ngày, tương đương khoảng **6,67 CPU giờ**.
- Trong đợt 15 phút: \(6.000 \times 2=12.000\) CPU giây.
- Nếu yêu cầu hoàn tất toàn bộ 6.000 ảnh trong 15 phút, lý tưởng cần \(12.000/900 \approx 13,34\) CPU core hoạt động liên tục, **chưa kể overhead và hệ số sử dụng mục tiêu**.
- Nếu một worker chỉ xử lý tuần tự một ảnh và hiệu suất thực đạt 70% so với năng lực CPU lý tưởng, có thể cần khoảng \(\lceil13,34/0,70\rceil=20\) worker một core để đạt thời hạn, nếu storage và queue đáp ứng.

Nếu resize ảnh chạy ngay trong API đặt chỗ, tăng công suất cho ảnh buộc phải scale cả code API và có thể tranh giành CPU với giao dịch quan trọng. Chuyển ảnh sang **queue + nhóm worker có thể scale riêng** thường là cách chia có giá trị ngay cả khi các module nghiệp vụ khác vẫn chạy chung một monolith.

Tuy vậy, tách worker **không tự xóa điểm nghẽn**. Object storage, kết nối mạng, giới hạn đọc/ghi và số lần retry vẫn cần được kiểm tra. Autoscaling theo queue depth phải xét thời gian khởi động worker, độ dài job và backlog có thể chấp nhận.

### Khi nào mở rộng cùng nhau vẫn hợp lý?

Nếu hai module luôn được gọi cùng nhau, dùng tài nguyên tương tự và thường thay đổi trong cùng một release, việc tách tiến trình có thể làm tăng latency và phức tạp mà không tạo thêm năng lực mở rộng hữu ích. Một monolith chạy nhiều replica sau load balancer đã có thể **scale ngang toàn bộ ứng dụng**; vấn đề chỉ xuất hiện rõ khi phần tiêu tốn tài nguyên lớn làm việc scale toàn khối trở nên lãng phí hoặc ảnh hưởng SLO.

## 4. Phân tích chu kỳ thay đổi và nhu cầu phát hành độc lập

**Chu kỳ thay đổi (change cadence)** mô tả tần suất và kiểu thay đổi của một thành phần: thay đổi quy tắc nghiệp vụ, API, dữ liệu, tài nguyên, cấu hình hoặc thuật toán. Hai phần có cùng tải nhưng chu kỳ phát hành khác xa có thể cần ranh giới triển khai khác nhau.

Ví dụ:

| Thành phần | Chu kỳ thay đổi giả định | Tác động nếu luôn phát hành chung |
| --- | --- | --- |
| Gợi ý và ranking tìm kiếm | Thử nghiệm hằng ngày, điều chỉnh thuật toán | Mỗi thử nghiệm kéo theo regression test và rollout của lõi giao dịch |
| Chính sách khuyến mại | Vài lần mỗi tuần | Rủi ro thay đổi mã tính giá ảnh hưởng thanh toán nếu không cô lập |
| Đặt chỗ và kiểm soát trùng lịch | Vài lần mỗi tháng, yêu cầu kiểm thử kỹ | Có thể bị buộc release theo tốc độ tính năng ít quan trọng |
| Tích hợp cổng thanh toán | Thay đổi theo nhà cung cấp và kiểm soát tuân thủ | Việc đổi provider tác động lớn nếu code phân tán khắp ứng dụng |
| Xử lý ảnh | Thay đổi kích thước, định dạng, pipeline | Phải phát hành API giao dịch để thay đổi worker |

Đây chỉ là giả định minh họa, không phải quy luật. Độ quan trọng của một chức năng không tự quyết định tần suất release: hệ thống thanh toán vẫn có thể triển khai thường xuyên nếu kiểm thử, rollback và kiểm soát rủi ro đủ mạnh.

### Chỉ báo để nhận ra ranh giới thay đổi

Thu thập **lịch sử thay đổi thực tế** thay vì dựa vào cảm giác:

- **Change coupling:** một thay đổi ở module A thường kéo theo sửa bao nhiêu module khác? Nhiều commit phải đổi A và B đồng thời là tín hiệu ranh giới chưa ổn định.
- **Deployment coupling:** thay đổi A có bắt buộc phát hành B cùng phiên bản không? Có thể rollback A mà không rollback B không?
- **Release frequency:** mỗi tuần/tháng phần này được phát hành bao nhiêu lần, có cần canary, feature flag hoặc phê duyệt riêng không?
- **Change failure rate và MTTR:** phần này thường gây lỗi triển khai ra sao, khôi phục mất bao lâu, blast radius có rộng không?
- **Team ownership:** đội nào chịu trách nhiệm thiết kế, vận hành và SLO? Có phải nhiều đội chờ nhau cho mỗi release không?
- **Schema/contract stability:** giao diện và sự kiện có đủ ổn định để hai phía tiến hóa khác nhịp không?

Nếu gợi ý thay đổi 15 lần/tháng nhưng booking chỉ 2 lần/tháng, việc yêu cầu mỗi thay đổi gợi ý phát hành toàn bộ hệ thống có thể làm tăng công việc kiểm thử và phạm vi ảnh hưởng. Tuy nhiên, **chỉ tách deployment không bảo đảm deploy độc lập**: nếu một đổi tên trường API buộc hai phía nâng cấp đồng thời, các service vẫn gắn chặt về release.

### Độc lập triển khai cần có hợp đồng tương thích

Để hai thành phần thay đổi khác nhịp:

1. Mỗi bên công bố **API contract hoặc event schema** rõ ràng, có kiểm thử hợp đồng (contract testing).
2. Thay đổi tương thích ngược khi có thể; không xóa trường hoặc đổi ý nghĩa của một event khi consumer cũ còn hoạt động.
3. Với thay đổi breaking, áp dụng giai đoạn chuyển tiếp: thêm trường mới, cập nhật consumer, quan sát mức sử dụng, rồi mới bỏ trường cũ.
4. Phát hành bằng canary/rolling deployment, có health check, metric và rollback cho thành phần sở hữu.
5. Tách **feature release** khỏi **code deployment** khi cần bằng feature flag; có thể tắt tính năng mà không rollback mọi thứ.
6. Xác định chính sách cho database migration: release mới và cũ có thể cùng chạy trong thời gian rolling update không?

Ví dụ, thay đổi tên trường **guestCount** sang **numberOfGuests** tại Booking API không nên khiến Catalog và Notification cùng lỗi ngay. Có thể tạm chấp nhận cả hai trường ở request, phát response/event với trường mới trong thời gian chuyển tiếp, cập nhật consumer rồi loại bỏ trường cũ sau khi có bằng chứng không còn sử dụng.

**Tách service mà không có contract versioning, telemetry và rollout độc lập** thường khiến số lượng repository/deployment tăng nhưng tốc độ đổi mới không cải thiện.

## 5. Chọn mức tách phù hợp: module, process, service hay luồng nền?

Các lựa chọn phổ biến nằm trên một phổ:

| Mô hình | Ưu điểm | Giới hạn | Tình huống phù hợp |
| --- | --- | --- | --- |
| **Monolith có tổ chức module** | Gọi trong process nhanh, transaction đơn giản, triển khai và debug dễ | Thường scale/release toàn khối; phụ thuộc có thể tăng nếu thiếu ranh giới | Sản phẩm mới, đội nhỏ, domain còn thay đổi |
| **Monolith + worker/queue tách riêng** | Tách phần CPU/I/O nặng hoặc bất đồng bộ, scale theo loại tải | Cần quản lý queue, retry, trạng thái công việc | Xử lý ảnh, email, đồng bộ, import dữ liệu |
| **Một số dịch vụ tách riêng** | Scale, release và cô lập lỗi của phần chọn lọc | Gọi qua mạng, hợp đồng, dữ liệu và observability phức tạp hơn | Search, recommendation, media có yêu cầu khác rõ ràng |
| **Microservices theo bounded context** | Nhiều đội có thể sở hữu và phát triển dịch vụ độc lập khi ranh giới tốt | Phân tán dữ liệu, chi phí vận hành, phụ thuộc, độ phức tạp DR/QA | Domain lớn, đội có năng lực platform/operations, ranh giới ổn định |

Không có đích đến mặc định là “mọi module phải thành microservice”. Một giải pháp lai có thể hợp lý: **Booking và Payment** là hai module chặt chẽ trong lõi giao dịch ở giai đoạn đầu, **Search** là dịch vụ đọc có index riêng, còn **Media** và **Notification** là worker bất đồng bộ. Sau này có thể tách Payment nếu xuất hiện yêu cầu tuân thủ, đội sở hữu hoặc lịch phát hành riêng đủ rõ.

### Deployment unit và scaling unit

Một deployment unit là thứ phát hành và rollback cùng nhau; một scaling unit là nhóm tài nguyên tăng/giảm công suất cùng nhau. Chúng có thể khác nhau trong thực tế:

- Một ứng dụng monolith có ba module chạy chung process: cả ba thường cùng scale khi thêm replica.
- Một codebase có hai entrypoint, **API** và **worker**: có thể build từ một repository nhưng triển khai và scale bằng hai workload riêng.
- Hai service có thể cùng dùng một cluster Kubernetes nhưng đặt autoscaling, quota, resource requests/limits riêng.
- Một function serverless có thể scale theo request, song vẫn phụ thuộc giới hạn concurrency, cold start và database connection; không phải “mở rộng vô hạn”.
- Một nhóm dịch vụ scale được nhưng database writer chung vẫn giới hạn throughput của toàn bộ hành trình.

Vì vậy cần chỉ rõ **thành phần nào thực sự được scale độc lập**, tín hiệu autoscaling nào sử dụng và dependency nào tiếp tục là nút thắt.

### Không lấy số dòng code làm tiêu chí chính

Một module 5.000 dòng với logic thanh toán phức tạp có thể cần được giữ cùng transaction hơn một module 50.000 dòng xử lý tài liệu độc lập. Tách theo số dòng hoặc tên thư mục mà không nhìn vào giao dịch, tải và chu kỳ đổi có thể tạo nhiều lời gọi mạng nhưng không tăng tự chủ.

## 6. Quyền sở hữu dữ liệu quyết định mức độc lập thực tế

Một lỗi thường gặp khi chuyển từ monolith sang nhiều service là **chia code nhưng vẫn cho các service sửa trực tiếp cùng một database schema**. Khi đó một migration của service A có thể phá service B; cả hai khó triển khai độc lập, tranh chấp connection pool, lock và thông lượng writer.

Trong thiết kế chia theo nghiệp vụ, mỗi thành phần có quyền **sở hữu logic đọc/ghi và bất biến dữ liệu** của mình. “Database per service” là một hướng đạt quyền sở hữu đó, **không nhất thiết bắt buộc một database server vật lý cho mỗi service**. Có thể bắt đầu từ schema riêng, quyền truy cập riêng, API sở hữu dữ liệu và quy tắc không ghi chéo, sau đó tách hạ tầng dữ liệu khi thật sự cần cách ly tải hoặc lifecycle.

### Khi nào cần giữ transaction cùng một ranh giới?

Đặt chỗ là ví dụ:

1. Một suất chỉ được đặt bởi một giao dịch hợp lệ tại một thời điểm.
2. Thao tác kiểm tra và giữ chỗ phải phòng race condition.
3. Trạng thái reservation phải nhất quán với bất biến “không bán trùng”.

Nếu kiểm tra lịch trống qua service A rồi ghi reservation qua service B mà không có concurrency control, hai request có thể cùng thấy chỗ trống và cùng đặt. Một thiết kế có thể để **Booking sở hữu transaction/constraint** ngăn trùng và phát sự kiện sau commit. Catalog/Search có thể nhận một projection trạng thái để phục vụ truy vấn, nhưng projection **không phải nguồn xác nhận cuối cùng cho thao tác ghi**.

### Sự kiện và eventual consistency

Khi tách các thành phần có vòng đời khác nhau, đôi khi chấp nhận độ trễ đồng bộ:

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Booking as Booking
    participant DB as Booking database
    participant Outbox as Event publisher
    participant Queue as Event broker
    participant Search as Search indexer
    Client->>Booking: Tạo đặt chỗ (idempotency key)
    Booking->>DB: Commit reservation + outbox
    DB-->>Booking: Thành công
    Booking-->>Client: Xác nhận đặt chỗ
    Outbox->>Queue: ReservationCreated
    Queue-->>Search: Sự kiện (có thể lặp / đến trễ)
    Search->>Search: Cập nhật read model
~~~

Với thiết kế này, Booking quyết định tính đúng đắn của giao dịch, còn Search nhận dữ liệu để tối ưu đọc và có thể hiển thị chậm hơn vài giây. Cần nêu rõ **mức trễ cho phép**, bảo vệ consumer trước sự kiện lặp, sai thứ tự, thiếu dữ liệu và xây dựng cơ chế replay/reconcile. Sơ đồ minh họa luồng logic; outbox publisher cần cơ chế lấy dữ liệu đã commit đáng tin cậy.

Không phải tất cả nghiệp vụ đều chấp nhận eventual consistency: một số ràng buộc tài chính hoặc tồn kho cần được bảo vệ ở nơi sở hữu dữ liệu, có thể bằng transaction, constraint, khóa hoặc giao thức thích hợp.

### Migration dữ liệu an toàn khi hai phiên bản cùng tồn tại

Một schema migration nên áp dụng mẫu **expand → migrate → contract**:

1. **Expand:** thêm cấu trúc mới tương thích ngược, không xóa ngay cấu trúc cũ.
2. **Migrate:** triển khai ứng dụng hỗ trợ cả cũ/mới, backfill dữ liệu theo lô, đo lỗi và độ trễ, cập nhật các consumer.
3. **Contract:** chỉ bỏ cột, event hoặc đường API cũ khi xác minh không còn producer/consumer sử dụng.

Trong giai đoạn hai phiên bản cùng chạy, cần hiểu đường ghi nào là nguồn sự thật để tránh “dual write” thiếu transaction làm dữ liệu lệch. Tách service chưa hoàn tất nếu schema migration vẫn yêu cầu dừng đồng thời toàn hệ thống.

## 7. Giao tiếp giữa các thành phần: nhanh, chắc chắn và ít phụ thuộc

Việc chuyển một lời gọi hàm nội bộ thành lời gọi qua mạng thay đổi cách hệ thống thất bại. Lời gọi từ Booking sang Payment có thể gặp timeout, mất kết nối hoặc nhận kết quả mơ hồ; lời gọi hàm cùng process thông thường không gặp các lỗi mạng đó. Vì vậy **ranh giới dịch vụ cũng là ranh giới xử lý lỗi**.

### Đồng bộ và bất đồng bộ

| Phương thức | Phù hợp khi | Đổi lại |
| --- | --- | --- |
| Gọi trong process | Cần dữ liệu ngay, transaction và lifecycle giống nhau | Cùng deployment/scaling unit; khó cô lập lỗi trong cùng process |
| HTTP/gRPC đồng bộ | Client cần phản hồi trực tiếp; hợp đồng request/response rõ | Network latency, timeout, retry, fan-out, dependency chặn đường chính |
| Event qua message broker | Phát thông tin đã xảy ra cho nhiều consumer có thể xử lý sau | Eventual consistency, xử lý lặp, thứ tự, versioning |
| Command qua queue | Tác vụ nền cần xử lý có giới hạn và theo dõi | Backlog, trạng thái bất đồng bộ, dead-letter và giám sát |
| Batch/file transfer | Tích hợp dung lượng lớn, không cần thời gian thực | Độ trễ, đối soát và kiểm soát lần chạy |

Không nhất thiết phải dùng event cho mọi trao đổi. Gọi trực tiếp vẫn hợp lý khi cần trả lời ngay và hệ thống phụ thuộc có SLO phù hợp. Tuy nhiên, một chuỗi **Gateway → Service A → Service B → Service C → Service D** làm độ trễ và rủi ro lỗi của hành trình phụ thuộc nhiều thành phần. Nên giảm các lời gọi trên đường nóng (*critical path*) và tránh fan-out không cần thiết.

### Tính sẵn sàng của chuỗi phụ thuộc

Giả sử ba dependency bắt buộc, độc lập về xác suất lỗi, có availability lần lượt là 99,9%, 99,9% và 99,5%. Nếu mọi request phải được cả ba đáp ứng thì:

\[
A_{\text{chuỗi}}\approx0{,}999\times0{,}999\times0{,}995
\approx99{,}30\%.
\]

Đây chỉ là phép minh họa **khi các sự cố độc lập và các dependency đều bắt buộc**, không phải công thức tổng quát cho hệ thống thực: cache, retry, fallback, redundancy và lỗi tương quan làm kết quả khác đi. Nhưng nó cho thấy vì sao tách service không đồng nghĩa tăng availability.

### Cách bảo vệ ranh giới dịch vụ

- **Timeout/deadline** cho từng lời gọi và ngân sách tổng của hành trình.
- **Retry có giới hạn, backoff, jitter**, chỉ với thao tác an toàn hoặc có idempotency.
- **Circuit breaker và bulkhead** để lỗi ở một dependency không tiêu hết tài nguyên ứng dụng.
- **Queue, backpressure và rate limiting** cho tác vụ nền hoặc luồng không thể xử lý nhanh hơn nguồn gửi.
- **Observability theo trace ID** qua các lời gọi và event; ghi nhận request lỗi, queue lag, thời gian xử lý, version của producer/consumer.
- **Giao ước thứ tự và trùng lặp:** không giả định message chỉ tới một lần; thiết kế consumer idempotent, khóa thứ tự theo thực thể nếu nghiệp vụ yêu cầu.

Với workflow trải qua nhiều hệ thống dữ liệu, có thể dùng **saga** (các bước giao dịch cục bộ và hành động bù) nếu business cho phép. Hành động bù không phải transaction rollback tuyệt đối; ví dụ “hoàn tiền” có thể mất thời gian, có phí và có trạng thái trung gian. Các bất biến nghiệp vụ cần được chỉ rõ trước khi chia giao dịch ra nhiều service.

## 8. Mở rộng riêng từng thành phần: từ số đo đến cơ chế triển khai

Nói “service này scale độc lập” chỉ có ý nghĩa khi biết **đo gì, tăng gì và giới hạn ở đâu**.

Với nhóm request có chi phí CPU tương đối ổn định, có thể ước lượng sơ bộ:

\[
\text{CPU core cần thiết}\approx
\frac{\text{RPS}\times\text{CPU giây/request}}
{\text{mức sử dụng CPU mục tiêu}}.
\]

Ví dụ một endpoint tìm kiếm nhận **150 RPS**, mỗi request dùng trung bình **0,03 CPU giây** theo profiling và mục tiêu chạy CPU trung bình dưới **60%**. Nhu cầu ước tính là \(150\times0{,}03/0{,}6=7{,}5\) core CPU hiệu dụng, trước khi cộng overhead, headroom cho đỉnh, replica chịu lỗi và ràng buộc bộ nhớ. Nếu search có query p99 nặng hoặc index lớn, chỉ dùng CPU trung bình sẽ không đủ để sizing.

Với tác vụ queue, cần đo **arrival rate**, **service rate** và **backlog**:

\[
\text{Backlog tăng mỗi giây}\approx
\max(0,\lambda_{\text{đến}}-\mu_{\text{xử lý}}).
\]

Nếu queue nhận **100 job/s** nhưng worker chỉ hoàn thành **80 job/s**, backlog tăng khoảng **20 job/s**, tức **1.200 job/phút**. Scale worker phải xét cả thời gian khởi động, quota downstream và thời gian drain backlog sau đỉnh. Đặt số replica theo CPU có thể chưa phản ánh chính xác backlog hoặc latency của job; một số workload cần autoscale theo **queue depth, queue age hoặc concurrency**.

Từng loại công việc có thể chọn mô hình triển khai phù hợp:

| Loại thành phần | Cách triển khai có thể phù hợp | Điểm phải thử nghiệm |
| --- | --- | --- |
| API stateless với tải tương đối liên tục | Container service, VM auto scaling hoặc nền tảng ứng dụng được quản lý | Load balancer, readiness, phiên, CPU/RAM, scale-out |
| Search với index riêng | Dịch vụ search được quản lý hoặc cluster riêng | Index size, freshness, query p99, replica, failover |
| Xử lý ảnh theo sự kiện | Queue + worker container/serverless | Cold start, memory, thời gian xử lý, duplicate, concurrency quota |
| Batch lớn theo lịch | Job/batch scheduler | Cửa sổ hoàn tất, checkpoint, retry, chi phí thời gian chạy |
| Giao dịch cần database nhất quán | API stateless + data layer được thiết kế riêng | Lock, transaction contention, writer QPS, failover, RPO/RTO |

**Serverless, container và VM đều có thể đáp ứng một phần bài toán.** Lựa chọn dựa trên độ dài job, cold start, tài nguyên, lưu lượng, quota, mô hình tính tiền và năng lực vận hành. Không nên chọn “microservice + serverless” chỉ vì chức năng nhỏ: một function gọi database với concurrency không giới hạn vẫn có thể làm cạn connection pool.

### Scaling độc lập vẫn có ràng buộc chung

Một service được tăng từ 4 lên 40 replica chỉ hữu ích nếu **database connection pool, writer, cache, broker và API ngoài** có khả năng chịu tải tăng theo. Phải đo công suất end-to-end và thiết lập giới hạn theo nguồn lực hiếm nhất. Nếu mỗi instance mở 30 kết nối DB, 40 instance có thể tạo tới **1.200 kết nối**, vượt giới hạn một database nhỏ. Connection pooling, backpressure và giới hạn concurrency là một phần của thiết kế scale.

## 9. Đánh đổi độ tin cậy, bảo mật, chi phí và vận hành

Phân chia thành phần tốt giúp giảm *blast radius* nhưng cũng tạo thêm đường lỗi: mạng, contract, xác thực giữa service, DNS, message broker, data replication và pipeline triển khai. Cần so sánh lợi ích với chi phí thực.

| Góc nhìn Well-Architected | Khi tách hợp lý có thể tốt hơn | Khi tách quá mức có thể tệ hơn |
| --- | --- | --- |
| **Reliability** | Cô lập tài nguyên; giảm ảnh hưởng của xử lý ảnh/search tới booking | Nhiều dependency bắt buộc, timeout dây chuyền, event bị lặp/trễ |
| **Performance efficiency** | Chọn CPU/RAM/runtime, autoscale theo workload | Overhead mạng, serialization, fan-out, cache miss giữa service |
| **Security** | Phân quyền riêng, cô lập dữ liệu và vùng xử lý nhạy cảm | Thêm identity, secret, token và bề mặt tấn công giữa service |
| **Cost optimization** | Không cần scale cả ứng dụng vì một workload; có thể dùng tài nguyên chuyên biệt | Nhiều replica tối thiểu, load balancer, egress, log/trace, môi trường |
| **Operational excellence** | Deploy/rollback độc lập, ownership rõ, lỗi có phạm vi nhỏ | Tăng pipeline, release coordination, tracing, on-call và runbook |
| **Sustainability** | Tài nguyên đặt đúng nơi cần, worker theo tải | Tài nguyên dự phòng nhàn rỗi ở quá nhiều service |

### Minh họa đánh đổi chi phí

Giả sử một monolith gồm ba thành phần và phải giữ **6 instance** để chịu tải. Tách một phần thành service độc lập có thể giúp monolith chỉ cần 4 instance và service mới 2 instance, chưa chắc giảm chi phí ngay vì tổng công suất vẫn là 6, lại thêm load balancer, logging và giao tiếp. Lợi ích chỉ xuất hiện rõ nếu service mới **tăng/giảm công suất theo nhịp riêng**, cho phép dùng loại máy phù hợp hoặc giảm tài nguyên của phần còn lại.

Ngoài tiền compute, cần tính **truyền dữ liệu giữa AZ/region, database riêng, broker, observability, deployment pipeline, thời gian hỗ trợ sự cố và công sức vận hành**. Không so sánh kiến trúc bằng số container đang chạy tại một thời điểm.

### Cô lập bảo mật theo ranh giới nghiệp vụ

Ranh giới service cho phép cấp quyền hẹp: Media worker chỉ cần đọc object đầu vào và ghi object kết quả; Notification chỉ đọc thông tin thông báo đã tối thiểu hóa; Payment bảo vệ dữ liệu thanh toán theo chính sách phù hợp. Nhưng việc chia service tạo thêm giao tiếp cần **xác thực service-to-service, ủy quyền, mã hóa khi truyền, quản lý secret và audit**. Đừng nhân bản dữ liệu cá nhân sang mọi service chỉ để mỗi service có database riêng. Nếu có yêu cầu cư trú dữ liệu hoặc xóa dữ liệu, cần xác định rõ bản sao, event và thời hạn retention trên toàn hệ thống.

## 10. Quy trình quyết định có nên tách một thành phần

Một thành phần là ứng viên tách tốt khi có **năng lực nghiệp vụ được sở hữu rõ**, nhu cầu **scale khác biệt** hoặc **phát hành độc lập**, và có thể đặt **hợp đồng giao tiếp đủ ổn định**. Ngược lại, thành phần thường xuyên đổi cùng phần lõi, chia sẻ transaction liên tục và thiếu người vận hành sẽ khó nhận được lợi ích từ việc tách.

Có thể dùng ma trận đánh giá định tính:

| Tiêu chí | Dấu hiệu ủng hộ tách | Dấu hiệu nên giữ cùng deployment |
| --- | --- | --- |
| **Tải và tài nguyên** | Đỉnh khác giờ, CPU/RAM/IO chuyên biệt, scale riêng tiết kiệm rõ | Tải và tài nguyên tương tự, scale toàn khối đáp ứng SLO |
| **Chu kỳ thay đổi** | Release thường xuyên khác nhịp, rollback riêng có giá trị | Luôn chỉnh sửa và release cùng nhau |
| **Ranh giới nghiệp vụ** | Quy tắc và quyền sở hữu riêng, contract rõ | Bất biến nghiệp vụ và transaction chặt |
| **Dữ liệu** | Có nguồn dữ liệu sở hữu rõ, có thể sử dụng API/event | Cần join/ghi chéo xuyên ranh giới trên đường nóng |
| **Độ tin cậy** | Có thể cô lập sự cố hoặc giảm cấp độc lập | Tạo thêm dependency đồng bộ bắt buộc, nguy cơ gián đoạn tăng |
| **Bảo mật và tuân thủ** | Cần phân quyền, dữ liệu, network zone hoặc kiểm soát riêng | Thêm quá nhiều đường truyền dữ liệu nhạy cảm |
| **Đội ngũ và vận hành** | Có người sở hữu SLO, pipeline, giám sát và hỗ trợ sự cố | Thiếu năng lực vận hành hoặc không có team chịu trách nhiệm |
| **Chi phí tổng** | Tiết kiệm compute hoặc giảm thiệt hại sự cố đo được | Infrastructure, tracing, deployment và support tăng hơn lợi ích |

Không cần quy đổi ma trận này thành một “điểm chuẩn” tùy ý. Hãy ghi **bằng chứng, mức tin cậy, lựa chọn hiện tại và điều kiện xem xét lại**. Ví dụ:

> **Quyết định:** Tách worker xử lý ảnh khỏi API trong quý hiện tại vì CPU ảnh chiếm 65% ở giờ import, ảnh có deadline hoàn tất 5 phút và không cần transaction đồng bộ với booking. **Giữ Booking trong modular monolith** vì 90% thay đổi của Availability và Reservation cùng sửa một bất biến dữ liệu. **Xem xét tách Search** khi p95 tìm kiếm, ngân sách compute hoặc tốc độ phát hành vượt ngưỡng đã thống nhất.

Một quyết định có thể kiểm chứng nên đi kèm chỉ số thành công: latency, error rate, throughput, cost/workload, tốc độ deploy và số sự cố tác động chéo giữa các năng lực.

## 11. Lộ trình tách dần ứng dụng đang hoạt động

Khi xuất phát từ một monolith, nên ưu tiên **tạo ranh giới trong code và đo tác động trước khi chuyển giao tiếp qua mạng**. Một lộ trình thực dụng:

### Bước 1 — Quan sát các đường đi chính

Gắn tracing và metric cho hành trình tìm kiếm, booking, thanh toán, xử lý ảnh. Đo CPU/memory theo tác vụ, RPS, số query, thời gian trong transaction, phụ thuộc đồng bộ, tần suất thay đổi code và lỗi theo release. Có baseline trước khi sửa để biết việc tách có mang lại lợi ích không.

### Bước 2 — Tạo module và quyền sở hữu rõ trong ứng dụng hiện tại

Nhóm code theo năng lực, quy định entrypoint/contract giữa module, hạn chế truy cập trực tiếp bảng thuộc module khác và có kiểm thử cho bất biến nghiệp vụ. Có thể bắt đầu bằng namespace/package, interface, cơ chế dependency injection và các module build tách được. Ranh giới này giúp phát hiện coupling trước khi trả giá cho hệ thống phân tán.

### Bước 3 — Tách workload có độ phụ thuộc thấp

Ưu tiên tác vụ nền, như ảnh và email: ghi sự kiện/job bền vững, worker riêng, idempotency, retry và dead-letter. Điều chỉnh công suất worker độc lập. Không chuyển toàn bộ dữ liệu và chức năng sang service mới cùng một lần.

### Bước 4 — Tách dữ liệu và hợp đồng của ứng viên tiếp theo

Ví dụ Search có thể lấy dữ liệu qua event/CDC hoặc pipeline đồng bộ được kiểm soát để xây index riêng. Định nghĩa dữ liệu nguồn thuộc Catalog/Booking, độ trễ đồng bộ cho phép, cơ chế backfill và đối soát. Không cho Search tự cập nhật trực tiếp reservation để sửa chỗ trống.

### Bước 5 — Chuyển dần traffic theo strangler pattern

Đặt một lớp định tuyến ổn định, chuyển một số endpoint/nhóm request tới service mới; dùng canary, feature flag hoặc routing có khả năng rollback. So sánh kết quả, latency, error rate, số lần gọi giữa thành phần và tổng chi phí. Nếu chuyển toàn bộ traffic trước khi test sự cố/rollback, rủi ro có thể lớn hơn lợi ích.

~~~mermaid
flowchart TB
    Client["Client"] --> Route["API gateway / routing"]
    Route -->|Luồng còn lại| Mono["Modular monolith: Booking + Catalog"]
    Route -->|Canary tìm kiếm| Search["Search service"]
    Mono -->|Sự kiện đã commit| Broker["Message broker"]
    Broker --> Media["Media workers"]
    Broker --> Notification["Notification workers"]
    Broker --> Indexer["Search indexer"]
    Indexer --> Search
~~~

Đây là cấu trúc tham khảo, không bắt buộc phải dùng API gateway cho mọi ứng dụng. Điều quan trọng là **có đường chuyển tiếp và rollback**, hợp đồng dữ liệu và cơ chế vận hành đủ tin cậy.

### Bước 6 — Dọn đường cũ và kiểm chứng tính độc lập

Sau khi chuyển traffic, bỏ code/đường ghi cũ theo kế hoạch, kiểm soát việc trùng nguồn dữ liệu, dọn flag và schema đã hết sử dụng. Kiểm tra service mới có thể deploy và rollback riêng, chịu tải riêng, xử lý lỗi dependency và có dashboard/on-call phù hợp. Nếu lần deploy nào cũng phải đồng bộ nhiều service, ranh giới vẫn cần cải thiện.

**Tiêu chí dừng tách** nên rõ: nếu lợi ích về SLO, chi phí, tốc độ thay đổi hoặc cô lập sự cố chưa đủ, tiếp tục duy trì module trong monolith có thể là lựa chọn hợp lý.

## 12. Case study: chọn ranh giới cho nền tảng đặt chỗ

Giả sử một nền tảng có các đặc tính **minh họa** sau:

| Thành phần | Yêu cầu và tín hiệu | Hướng thiết kế ban đầu |
| --- | --- | --- |
| **Catalog** | Nội dung đọc nhiều, cập nhật vài lần/ngày | Module sở hữu dữ liệu gốc, cache/CDN cho nội dung công khai |
| **Search** | Query CPU/RAM cao; ranking thay đổi thường xuyên; cần index riêng | Service độc lập nếu baseline đo cho thấy scale và release riêng có giá trị |
| **Booking/Availability** | Transaction chống trùng; thay đổi quy tắc cùng nhau; độ trễ thấp | Giữ ranh giới giao dịch chung trong modular monolith hoặc service Booking thống nhất |
| **Payment integration** | Cần idempotency, đối soát, quota provider | Adapter/module có hợp đồng rõ; tách nếu có nhu cầu bảo mật, vận hành hoặc thay đổi độc lập |
| **Media** | Đỉnh upload ảnh theo chiến dịch; resize tốn CPU | Queue + worker có autoscale riêng, object storage |
| **Notification** | Gửi theo sự kiện, chấp nhận trễ vài phút | Outbox/event + worker, retry và theo dõi backlog |

### Nếu bắt đầu bằng một monolith chưa chia module

Một đợt import 10.000 ảnh có thể làm CPU tăng mạnh, dẫn đến p99 của API đặt chỗ xấu đi. Đồng thời, thay đổi ranking tìm kiếm yêu cầu rollout toàn ứng dụng và regression test booking. Đây là hai tín hiệu khác nhau: **tải cần tách** và **chu kỳ release cần tách**.

### Một phương án tiến hóa có cơ sở

Giai đoạn đầu, tổ chức lại module theo Catalog, Search, Booking, Payment. Chuyển Media và Notification ra worker bất đồng bộ vì dễ xác định công việc, failure domain và cơ chế retry. Đo lại latency, error rate, CPU, backlog và chi phí; khi Search có đủ chứng cứ về tải và chu kỳ phát hành riêng, tách index và API Search.

Booking và Availability tiếp tục cùng ranh giới ghi giao dịch để bảo vệ bất biến không đặt trùng. Payment giữ một adapter có idempotency và trạng thái đối soát rõ, có thể tách deployment sau khi giao diện và dữ liệu đủ ổn định. Dữ liệu Search có thể trễ, còn kết luận “đặt chỗ thành công” luôn dựa trên Booking.

### Hai tiêu chí chấp nhận sau khi tách

**Hiệu năng:** Khi tải import ảnh tăng gấp nhiều lần, p95/p99 và tỉ lệ lỗi Booking vẫn nằm trong SLO; backlog Media được xử lý trong khoảng chấp nhận mà không scale quá mức API. Đo ở mức workload và hành trình, không chỉ nhìn số replica.

**Chu kỳ thay đổi:** Đội Search có thể phát hành ranking mới, canary và rollback mà không bắt buộc phát hành Booking. Contract/schema phải duy trì tương thích và số thay đổi đồng thời ở nhiều service giảm. Nếu p99 cải thiện nhưng mỗi release vẫn cần phối hợp ba đội, mục tiêu độc lập thay đổi chưa đạt.

### Điều gì xảy ra nếu thiết kế sai ranh giới?

- Search cần truy vấn đồng bộ Booking cho **từng kết quả** trong trang danh sách: fan-out làm latency và tải DB tăng mạnh; nên xem cách đồng bộ projection và xác minh cuối ở luồng đặt chỗ.
- Notification gọi lại nhiều service trong lúc gửi để lấy đầy đủ dữ liệu khách hàng: rủi ro lỗi dây chuyền và quyền truy cập dữ liệu rộng; nên cân nhắc payload tối thiểu hoặc API query phù hợp.
- Booking và Availability tách database nhưng vẫn có yêu cầu cập nhật đồng bộ cho mọi thao tác: có thể phát sinh race condition và khó chứng minh tính nhất quán.
- Media không có giới hạn concurrency và retry: tách worker nhưng vẫn có thể làm object storage hoặc API phụ thuộc quá tải.

Những lỗi này nhắc rằng **ranh giới tốt làm giảm coupling và cô lập tài nguyên**, chứ không chỉ đổi tên package thành service.

## 13. Những sai lầm thường gặp

1. **Một table = một service:** ranh giới dữ liệu kỹ thuật không nhất thiết tương ứng một năng lực nghiệp vụ; dễ sinh join và transaction phân tán.
2. **Tách vì số dòng code:** kích thước codebase không thể hiện nhu cầu scale và độ độc lập release.
3. **Gọi microservice nhưng dùng chung schema và ghi chéo:** tăng số deployment mà vẫn bắt buộc nâng cấp đồng thời.
4. **Giao tiếp đồng bộ cho mọi thứ:** chuỗi fan-out làm tăng latency và số điểm lỗi bắt buộc.
5. **Tách transaction mạnh mà chưa có cơ chế nhất quán:** có nguy cơ đặt chỗ trùng, trạng thái thanh toán lệch hoặc ghi mất sự kiện.
6. **Scale API nhưng bỏ qua downstream:** database writer, pool kết nối, rate limit provider hoặc broker vẫn có thể là nút thắt.
7. **Không tính chi phí tối thiểu của service:** replica dự phòng, load balancer, network, observability và thời gian trực vận hành làm tổng chi phí tăng.
8. **Phát hành độc lập trên danh nghĩa:** schema và API breaking buộc mọi service cùng deploy; thiếu contract test và quy trình deprecation.
9. **Không có ownership/SLO riêng:** mỗi sự cố mất thời gian tìm đội chịu trách nhiệm, dù đã tách service.
10. **Tách hàng loạt trong một lần:** thay đổi đồng thời cả ranh giới code, dữ liệu và routing khiến rollback và xác định nguyên nhân khó hơn.

## 14. Bài tập thực hành và đáp án định hướng

Một nền tảng đào tạo có các chức năng: đăng nhập, xem khóa học, tìm kiếm khóa học, mua khóa học, phát video và xuất chứng chỉ PDF. Hiện toàn bộ chạy chung một ứng dụng container; có các quan sát sau:

- Search chiếm 55% CPU lúc học viên làm bài tìm tài liệu, nhưng chỉ 10% tổng request.
- Xuất chứng chỉ PDF chạy 2 phút mỗi job; một đợt thi có thể tạo 3.000 job trong 10 phút.
- Quy tắc mua khóa học và thanh toán thường thay đổi trong cùng pull request vì ràng buộc đối soát.
- Đội nội dung muốn điều chỉnh xếp hạng tìm kiếm mỗi ngày; đội giao dịch release theo kế hoạch cẩn trọng hơn.
- API mua khóa học phải hoàn tất đúng một lần và giữ được trạng thái ngay cả khi dịch vụ email lỗi.

**Câu 1 — Chọn thành phần tách trước:** Có nên biến cả sáu chức năng thành sáu service ngay không?

**Gợi ý trả lời:** Chưa có cơ sở. Nên lập ranh giới module và đo baseline; **PDF export** là ứng viên worker/queue riêng vì có job dài, tải theo đợt và có thể xử lý bất đồng bộ. **Search** cũng là ứng viên tách tốt nhờ CPU và release cadence riêng, nhưng cần đo index, latency, hợp đồng dữ liệu và chi phí trước khi quyết định. Đăng nhập/mua khóa học không tự động cần service riêng.

**Câu 2 — Chọn tín hiệu scale cho PDF worker:** Vì sao chỉ scale theo RPS của API không đủ?

**Gợi ý trả lời:** API có thể nhận 3.000 request tạo job rất nhanh rồi kết thúc, trong khi mỗi job PDF kéo dài 2 phút. Tín hiệu nên gồm **queue depth/age, job duration, concurrency, CPU/RAM**, deadline hoàn tất và quota storage. Cần thiết kế retry và idempotency để tránh xuất hoặc gửi chứng chỉ trùng.

**Câu 3 — Có nên tách mua khóa học và thanh toán không?**

**Gợi ý trả lời:** Cần phân biệt *ranh giới trách nhiệm* với *deployment*. Trước tiên tạo adapter/contract thanh toán và cơ chế idempotency/đối soát. Nếu phần mua và thanh toán cần một bất biến chặt, chưa có hợp đồng ổn định và luôn release cùng nhau, giữ trong cùng deployment có thể giảm rủi ro. Tách sau khi có dữ liệu chứng minh lợi ích độc lập và thiết kế xử lý trạng thái phân tán.

**Câu 4 — Cách chứng minh Search thực sự deploy độc lập?**

**Gợi ý trả lời:** Định nghĩa API/event schema tương thích, contract test, canary và rollback riêng; Search có index được cập nhật mà không truy cập ghi trực tiếp vào bảng mua khóa học. Theo dõi số lần thay đổi đồng thời ở Search và phần lõi, p99 latency, lỗi sau deploy và chi phí của từng workload.

**Câu 5 — Các mục tiêu Well-Architected cần review là gì?**

**Gợi ý trả lời:** Độ tin cậy của giao dịch mua khóa học, giới hạn sự cố do PDF/Search gây ra; quyền truy cập dữ liệu của worker; khả năng scale theo loại tải; observability, runbook và ownership; chi phí compute/queue/storage/egress; khả năng quay lại trạng thái ổn định sau rollout lỗi.

Khi đánh giá một phương án phân chia thành phần, hãy trình bày **ranh giới nghiệp vụ, biểu đồ tải, lịch sử thay đổi, phụ thuộc dữ liệu, hợp đồng giao tiếp, chiến lược deploy/rollback và cách đo hiệu quả**. Đây là những bằng chứng giúp quyết định khi nào nên giữ modular monolith, khi nào tách worker và khi nào một dịch vụ độc lập thực sự cần thiết.
