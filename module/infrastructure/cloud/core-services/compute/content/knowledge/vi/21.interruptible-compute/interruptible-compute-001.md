# Spot, preemptible và interruptible compute hoạt động như thế nào

## Mục tiêu bài học

Spot, preemptible và interruptible compute là các hình thức sử dụng năng lực tính toán dư thừa của nhà cung cấp cloud với mức giá thường thấp hơn máy theo nhu cầu. Đổi lại, nhà cung cấp có thể thu hồi tài nguyên khi cần. Một workload chạy trên loại máy này phải chấp nhận khả năng bị dừng, lưu trạng thái an toàn và tiếp tục công việc trên một instance khác.

Sau bài học này, bạn có thể:

- Giải thích cách hoạt động của capacity có thể bị thu hồi và các tên gọi phổ biến.
- Phân biệt lợi ích chi phí với rủi ro gián đoạn và thiếu capacity.
- Nhận biết nguyên nhân thu hồi, interruption notice và các trạng thái lifecycle.
- Chọn workload phù hợp với Spot hoặc preemptible compute.
- Thiết kế checkpoint, retry, idempotency và graceful shutdown.
- Kết hợp máy có thể thu hồi với máy on-demand để duy trì mức dịch vụ.
- Vận hành Spot fleet, autoscaling group và Kubernetes node pool an toàn.
- Đo chi phí trên mỗi đơn vị công việc đã hoàn tất, thay vì chỉ nhìn giá mỗi giờ.

## 1. Interruptible compute là gì?

Nhà cung cấp cloud có thể có năng lực compute chưa được khách hàng sử dụng hết tại một thời điểm. Họ có thể bán phần capacity dư thừa này với giá ưu đãi. Những máy hoặc tài nguyên này thường được gọi bằng các tên như:

- **Spot instance/Spot VM:** máy ảo sử dụng capacity dư thừa, có giá thay đổi hoặc được định giá theo cơ chế riêng của nhà cung cấp và có thể bị thu hồi.
- **Preemptible VM:** máy ảo có thể bị nhà cung cấp thu hồi trước khi người dùng chủ động dừng; một số sản phẩm preemptible còn có giới hạn thời gian chạy tối đa.
- **Interruptible compute:** tên gọi tổng quát cho tài nguyên compute mà nhà cung cấp hoặc nền tảng điều phối có quyền dừng, thu hồi hoặc thay thế với thời gian báo trước hạn chế.

Tên gọi và điều khoản không hoàn toàn giống nhau giữa các nhà cung cấp. Một số sản phẩm Spot không có thời hạn chạy tối đa cố định nhưng vẫn có thể bị thu hồi bất cứ lúc nào; một số sản phẩm preemptible có giới hạn tuổi thọ riêng. Cần đọc chính sách của đúng dịch vụ, region và loại tài nguyên đang dùng.

Điểm chung là người dùng không có cam kết capacity liên tục giống máy on-demand hoặc capacity reservation. Giá thấp hơn là phần bù cho việc chấp nhận gián đoạn và khả năng không lấy được máy khi cần.

### 1.1. Vì sao nhà cung cấp thu hồi máy?

Các lý do phổ biến gồm:

- Nhà cung cấp cần capacity để đáp ứng nhu cầu ưu tiên cao hơn.
- Host hoặc vùng hạ tầng cần bảo trì hay xử lý lỗi.
- Capacity của một instance family hoặc Availability Zone bị thiếu.
- Giá thị trường hoặc ngưỡng giá do người dùng cấu hình không còn phù hợp với chính sách sản phẩm.
- Dịch vụ áp dụng giới hạn thời gian chạy hoặc điều kiện thu hồi riêng.
- Nhà cung cấp phát hiện một tình trạng hạ tầng cần di chuyển hoặc dừng workload.

Không phải mọi lần thu hồi đều có thể dự đoán. Có dịch vụ gửi interruption notice trước khi dừng máy; có dịch vụ cung cấp tín hiệu lifecycle khác; cũng có tình huống lỗi host khiến máy biến mất mà không có đủ thời gian xử lý. Thiết kế workload phải chịu được cả trường hợp có thông báo lẫn trường hợp mất máy đột ngột.

### 1.2. Mô hình đánh đổi

| Thuộc tính | On-demand/reserved capacity | Spot/preemptible |
|---|---|---|
| Giá compute | Thường cao hơn theo mức giá niêm yết | Thường được chiết khấu |
| Khả năng giữ capacity | Theo cam kết của sản phẩm | Không được bảo đảm liên tục |
| Thời điểm thu hồi | Người dùng hoặc chính sách vận hành | Nhà cung cấp có thể thu hồi |
| Thông báo trước | Không áp dụng cho tình huống thu hồi Spot | Có thể có, thời gian và bảo đảm tùy dịch vụ |
| Phù hợp | Workload cần ổn định, stateful hoặc latency nghiêm ngặt | Workload chịu lỗi, có thể retry/checkpoint |
| Chi phí thực tế | Dễ dự đoán hơn | Phụ thuộc interruption, retry và công việc bị mất |

Spot không phải tài nguyên miễn phí hoặc luôn sẵn có. Hãy xem nó như một nguồn capacity có giá thấp hơn nhưng độ sẵn sàng không chắc chắn.

## 2. Spot capacity và capacity pool

Một capacity pool thường được xác định bởi tổ hợp thuộc tính như:

- Region và Availability Zone.
- Instance family, size hoặc loại accelerator.
- Kiến trúc CPU và nền tảng hệ điều hành.
- Tenancy hoặc kiểu triển khai.
- Network, storage và các giới hạn của sản phẩm.
- Những yêu cầu placement hoặc reservation liên quan.

Hai instance cùng số vCPU và RAM nhưng thuộc hai family hoặc zone khác nhau có thể nằm trong hai pool khác nhau. Capacity của một pool có thể cạn trong khi pool khác vẫn còn.

Nếu chỉ yêu cầu một loại instance duy nhất ở một AZ, hệ thống bị phụ thuộc vào một pool hẹp. Khi pool đó thiếu capacity hoặc có interruption rate cao, autoscaler không thể dễ dàng thay thế máy.

### 2.1. Đa dạng hóa capacity

Để tăng cơ hội lấy được capacity, có thể mở rộng danh sách lựa chọn:

- Nhiều instance family có hiệu năng tương đương.
- Một số size phù hợp với cùng workload.
- Nhiều Availability Zone trong cùng region.
- Nhiều pool có kiến trúc CPU hoặc cấu hình phần cứng được ứng dụng hỗ trợ.
- Kết hợp Spot với on-demand capacity.

Không nên đa dạng hóa bằng mọi giá. Ứng dụng phải tương thích với kiến trúc CPU, RAM, GPU, network và storage của các lựa chọn thay thế. Hãy đặt tập instance type dựa trên yêu cầu tài nguyên và benchmark, rồi mở rộng trong nhóm tương đương.

### 2.2. Chiến lược chọn pool

Các chiến lược thường gặp ở dịch vụ Spot fleet gồm:

| Chiến lược | Ý tưởng | Khi cân nhắc |
|---|---|---|
| Lowest price | Ưu tiên pool có giá thấp nhất | Workload rất chịu lỗi, giá là mục tiêu chính và chấp nhận biến động |
| Capacity optimized | Ưu tiên pool có khả năng cấp capacity tốt hơn | Muốn giảm nguy cơ thiếu capacity hoặc interruption |
| Price-capacity optimized | Cân bằng giá và khả năng cấp capacity | Muốn giảm chi phí nhưng vẫn quan tâm tính liên tục |
| Diversified | Phân bổ giữa nhiều pool | Muốn giảm phụ thuộc vào một pool cụ thể |

Tên chiến lược, cách tính và khả năng hỗ trợ tùy nhà cung cấp. Đừng giả định hai cloud có cùng thuật toán chỉ vì tên gọi giống nhau.

Ưu tiên capacity ổn định thường có giá trị hơn việc chọn pool rẻ nhất nếu một lần interruption làm mất nhiều giờ xử lý. Đánh giá bằng chi phí trên mỗi công việc hoàn tất và tỷ lệ thành công, không chỉ bằng giá máy.

## 3. Giá Spot và tổng chi phí thực tế

Giá Spot có thể thay đổi theo pool, thời điểm, region và chính sách dịch vụ. Một số sản phẩm công bố giá hiện tại; một số dùng mức chiết khấu hoặc cơ chế giá riêng. Có thể có tùy chọn ngưỡng giá tối đa, nhưng không phải dịch vụ nào cũng có và cách hoạt động khác nhau.

Đặt ngưỡng giá quá thấp có thể làm instance bị thu hồi hoặc không được cấp. Nếu workload có khả năng checkpoint và tự phục hồi, thường nên ưu tiên chiến lược capacity phù hợp thay vì chỉ cố định một ngưỡng giá rất thấp.

### 3.1. Chi phí mỗi giờ không phải chi phí mỗi kết quả

Giả sử một batch job cần 4 giờ CPU hữu ích. Nếu máy bị thu hồi sau mỗi 90 phút và công việc chưa được checkpoint, phần xử lý trước interruption có thể phải chạy lại. Một mức giá mỗi giờ thấp hơn chưa chắc làm tổng chi phí thấp hơn.

Công thức đánh giá đơn giản:

~~~text
Chi phí trên mỗi đơn vị công việc hoàn tất =
  (compute + storage + network + checkpoint + retry + vận hành)
  / số đơn vị công việc hoàn tất
~~~

Các khoản cần tính:

- Thời gian compute bị mất sau mỗi interruption.
- Chi phí tạo checkpoint, ghi object storage hoặc đồng bộ state.
- Chi phí khởi động lại, tải lại dữ liệu và warmup.
- Chi phí queue, retry, duplicate processing và lưu trữ tạm.
- Chi phí capacity on-demand dự phòng.
- Công sức vận hành và xử lý sự cố.

### 3.2. Ví dụ so sánh

Một nhóm batch worker xử lý 10.000 tác vụ. Có hai phương án:

| Chỉ số | Fleet on-demand | Fleet Spot kết hợp on-demand |
|---|---:|---:|
| Giá compute trung bình giả định | Cao hơn | Thấp hơn |
| Tác vụ bị retry | Thấp | Có thể cao hơn |
| Capacity nền | Ổn định | On-demand giữ phần nền |
| Capacity burst | On-demand | Spot bổ sung |
| Yêu cầu checkpoint | Có thể đơn giản hơn | Cần thiết kế rõ |
| Rủi ro thiếu capacity | Thấp hơn nếu đã bảo đảm | Cao hơn ở pool Spot |
| Chi phí mỗi tác vụ thành công | Baseline | Phải đo sau retry và interruption |

Không thể kết luận phương án Spot rẻ hơn chỉ từ mức discount. Hãy chạy thử ở quy mô nhỏ, ghi nhận interruption, thời gian xử lý lại và chi phí tổng trước khi chuyển workload lớn.

## 4. Interruption notice và vòng đời thu hồi

Một số dịch vụ cung cấp tín hiệu trước khi thu hồi instance. Tín hiệu có thể đến qua metadata endpoint, event service, notification, API hoặc trạng thái lifecycle. Cách nhận tín hiệu và thời gian báo trước tùy nền tảng.

Khi nhận notice, ứng dụng cần chuyển sang chế độ shutdown có kiểm soát:

1. Ghi nhận interruption event và thời điểm cần hoàn tất.
2. Ngừng nhận công việc mới.
3. Gỡ instance khỏi load balancer hoặc ngừng polling queue.
4. Hoàn tất request/job đang chạy nếu còn đủ thời gian.
5. Ghi checkpoint hoặc lưu kết quả trung gian.
6. Flush log và metric quan trọng.
7. Đóng connection, giải phóng lock/lease và kết thúc process.
8. Để instance bị thu hồi hoặc terminate theo lifecycle của provider.

Không được giả định notice luôn đến hoặc luôn có đủ thời gian để hoàn tất toàn bộ công việc. Thời gian báo trước có thể ngắn, có thể khác theo sản phẩm và có thể không xuất hiện khi host gặp lỗi đột ngột.

### 4.1. Thiết kế hai đường xử lý

Một hệ thống vững chắc cần có cả hai đường:

- **Graceful interruption:** nhận notice, dừng nhận việc mới, checkpoint và thoát.
- **Unexpected loss:** instance biến mất mà không kịp chạy shutdown handler; workload được phát hiện mất heartbeat/lease và job được giao lại.

Đường thứ hai là bắt buộc. Nếu tính đúng đắn của dữ liệu phụ thuộc vào việc shutdown hook chắc chắn chạy, hệ thống chưa chịu được interruption.

~~~mermaid
flowchart TD
    A["Spot instance đang chạy"] --> B{"Có interruption notice?"}
    B -->|Có| C["Stop nhận việc mới"]
    C --> D["Drain và checkpoint"]
    D --> E["Flush và kết thúc"]
    B -->|Không, máy mất đột ngột| F["Heartbeat hoặc lease hết hạn"]
    F --> G["Scheduler phát hiện worker mất"]
    E --> H["Job được xác nhận hoàn tất hoặc giao lại"]
    G --> H
    H --> I["Worker khác tiếp tục"]
~~~

## 5. Thiết kế checkpoint

Checkpoint là bản lưu trạng thái đủ để tiếp tục công việc từ một điểm gần nhất sau khi instance bị dừng.

Một checkpoint tốt nên có:

- Job ID hoặc partition ID.
- Phiên bản schema và phiên bản ứng dụng.
- Offset, cursor hoặc vị trí xử lý.
- State cần thiết để khôi phục.
- Timestamp và generation/version.
- Checksum hoặc cách xác minh tính toàn vẹn.
- Trạng thái hoàn tất và metadata tương thích.

Checkpoint phải được ghi vào nơi tồn tại độc lập với instance có thể bị thu hồi, ví dụ object storage, database hoặc dịch vụ lưu trữ bền vững. Dữ liệu chỉ nằm trên local ephemeral disk có thể mất cùng máy.

### 5.1. Ghi checkpoint an toàn

Một quy trình ghi checkpoint có thể gồm:

1. Tạo snapshot nhất quán của trạng thái tại một ranh giới công việc.
2. Ghi vào object/key tạm với generation mới.
3. Đọc lại metadata hoặc kiểm tra checksum.
4. Ghi manifest xác nhận checkpoint hoàn chỉnh.
5. Chỉ sau đó cập nhật con trỏ checkpoint mới nhất.
6. Giữ lại checkpoint trước đó cho tới khi checkpoint mới được xác nhận.

Cách ghi này tránh trường hợp process bị dừng giữa lúc ghi và để lại một file dở dang được hiểu nhầm là checkpoint hợp lệ.

Không ghi đè checkpoint tốt gần nhất bằng một bản chưa hoàn chỉnh. Nếu dùng database, cần transaction hoặc cơ chế versioning phù hợp. Nếu dùng object storage, thiết kế key và manifest sao cho thao tác publish checkpoint có thể được xác minh.

### 5.2. Chọn chu kỳ checkpoint

Checkpoint quá thường xuyên làm tăng I/O, network và chi phí. Checkpoint quá thưa làm tăng lượng công việc phải chạy lại.

Nếu công việc bị gián đoạn ngẫu nhiên và thời điểm interruption không phụ thuộc vào tiến trình, khoảng mất công việc kỳ vọng có thể xấp xỉ một nửa chu kỳ checkpoint. Đây chỉ là mô hình ước lượng đơn giản; workload, phân phối interruption và thời gian ghi checkpoint có thể làm kết quả khác đi.

Cân nhắc:

- Thời gian và chi phí tạo một checkpoint.
- Tốc độ xử lý và chi phí chạy lại.
- Tần suất interruption quan sát được.
- Kích thước state và thời gian khôi phục.
- SLO hoàn tất job và mức độ mất dữ liệu cho phép.

Có thể checkpoint theo thời gian, số record, số batch, số bước mô hình hoặc ranh giới transaction. Với pipeline dữ liệu, offset của message/partition thường là điểm khôi phục tự nhiên.

## 6. Retry và idempotency

Khi một worker bị thu hồi, scheduler có thể giao lại cùng công việc cho worker khác. Worker cũ có thể đã ghi kết quả nhưng chưa kịp xác nhận hoàn tất. Nếu worker mới chạy lại, kết quả có thể bị nhân đôi.

**Idempotency** nghĩa là thực hiện lại cùng một thao tác với cùng khóa nghiệp vụ không làm thay đổi kết quả cuối ngoài ý muốn.

Các kỹ thuật phổ biến:

- Gán idempotency key ổn định cho mỗi job hoặc operation.
- Dùng unique constraint hoặc upsert có điều kiện trong database.
- Chỉ commit offset/ack message sau khi kết quả bền vững.
- Dùng transaction hoặc outbox pattern cho thao tác ghi và phát event.
- Thiết kế retry có exponential backoff và jitter.
- Giới hạn số lần retry và đưa job lỗi kéo dài vào dead-letter queue.
- Lưu trạng thái job với lease hoặc fencing token để worker cũ không thể ghi đè worker mới.

### 6.1. Lease và fencing token

Một worker có thể giữ lease trong một khoảng thời gian. Nếu worker mất heartbeat, scheduler cho phép worker khác tiếp quản. Tuy nhiên, worker cũ có thể vẫn còn chạy trong một khoảng ngắn do network partition.

Fencing token là số phiên tăng dần hoặc token phiên làm việc. Hệ thống lưu trữ chỉ chấp nhận thao tác từ token mới nhất. Điều này ngăn worker cũ ghi kết quả sau khi quyền sở hữu job đã được chuyển sang worker mới.

Lease giúp phát hiện worker mất; fencing token bảo vệ dữ liệu khi có hai worker cùng nghĩ mình sở hữu công việc.

## 7. Workload phù hợp với Spot/preemptible

Spot phù hợp nhất với workload có thể phân mảnh, retry hoặc khôi phục từ checkpoint.

| Workload | Mức phù hợp | Điều kiện |
|---|---|---|
| Batch processing | Cao | Chia job thành task nhỏ, lưu kết quả bền vững |
| CI build/test | Cao | Build có thể chạy lại, cache lưu ngoài instance |
| Rendering/transcoding | Cao | Chia frame/chunk và ghi output theo phần |
| Data processing | Cao | Checkpoint offset, partition và đảm bảo xử lý lặp an toàn |
| ML training | Có điều kiện | Framework hỗ trợ checkpoint model/optimizer và resume |
| Stateless web/API | Có điều kiện | Có capacity thay thế, load balancer và không lưu state cục bộ |
| Kubernetes worker node | Có điều kiện | Pod có thể reschedule, PDB và termination handling được thiết kế đúng |
| Database replica/read worker | Có điều kiện | Có replication và quy trình thay thế replica |
| Database primary | Thấp | Chỉ cân nhắc với kiến trúc có failover đã kiểm thử và storage bền vững |
| Stateful singleton | Thấp | Có thể mất state hoặc ngừng dịch vụ nếu không có bản thay thế |
| Latency-critical service | Thấp đến trung bình | Chỉ dùng cho phần capacity có thể thay thế mà không phá SLO |

Không nên đặt toàn bộ capacity của một dịch vụ quan trọng lên Spot nếu dịch vụ không có phương án dự phòng. Một ứng dụng stateless vẫn có thể bị gián đoạn nếu toàn bộ instance cùng nằm trong một pool bị thu hồi.

### 7.1. Chia workload thành phần có thể thu hồi

Một kiến trúc thường dùng:

- Control plane và scheduler chạy trên capacity ổn định.
- Queue lưu công việc chưa xử lý.
- Worker Spot xử lý task có thể retry.
- Kết quả và checkpoint ghi vào storage bền vững.
- Một nhóm worker on-demand nhỏ làm capacity dự phòng hoặc xử lý tác vụ cần hoàn tất nhanh.
- Autoscaler bổ sung worker theo backlog và thay thế worker bị mất.

Cách tách này giới hạn tác động của interruption vào phần worker, đồng thời giữ trạng thái và điều phối ở lớp ổn định.

~~~mermaid
flowchart LR
    U["Producer / API"] --> Q["Durable queue"]
    Q --> S["Scheduler"]
    S --> O["On-demand workers"]
    S --> P["Spot workers"]
    O --> R["Checkpoint / result store"]
    P --> R
    R --> D["Result consumer"]
    P -. "Interruption / retry" .-> S
~~~

## 8. Xây dựng fleet kết hợp On-demand và Spot

Một fleet hỗn hợp thường dùng capacity ổn định làm nền, sau đó bổ sung Spot để xử lý tải biến động.

Ví dụ một dịch vụ cần tối thiểu 6 worker để đáp ứng tải nền và có thể tăng tới 30 worker vào giờ cao điểm:

- Duy trì 6 worker on-demand hoặc capacity đã được bảo đảm.
- Bổ sung Spot khi queue backlog tăng.
- Nếu Spot không lấy được capacity, cho phép on-demand mở rộng tới mức giới hạn đã định.
- Khi tải giảm, loại bỏ worker Spot trước theo policy.
- Giữ đủ headroom để xử lý interruption và thời gian khởi động worker thay thế.

Tỷ lệ Spot không nên được chọn chỉ dựa trên mức discount. Nó phụ thuộc interruption rate, khả năng thay thế, SLO và mức capacity on-demand có thể chịu chi phí.

### 8.1. Chính sách phân bổ

Có thể dùng các nguyên tắc:

- Giữ phần capacity quan trọng nhất trên on-demand hoặc reserved capacity.
- Dùng Spot cho phần tải có thể giảm hoặc chạy lại.
- Đa dạng hóa instance family và AZ trong nhóm tương đương.
- Duy trì minimum on-demand capacity để không phụ thuộc hoàn toàn vào Spot.
- Bật fallback sang on-demand khi thiếu Spot nếu SLO yêu cầu.
- Đặt maximum capacity và budget guardrail để tránh chi phí tăng ngoài dự kiến.
- Tránh scale tất cả worker vào cùng một pool hoặc cùng một AZ.

Fallback sang on-demand giúp tăng độ sẵn sàng nhưng có thể làm chi phí tăng nhanh trong một đợt thiếu Spot. Cần đặt giới hạn, cảnh báo và quy tắc ưu tiên công việc.

### 8.2. Không tạo thundering herd khi bị thu hồi

Nếu nhiều instance cùng bị thu hồi, tất cả worker có thể retry hoặc tạo instance thay thế cùng lúc. Điều này gây tải đột biến lên API cloud, registry, database, queue và dependency.

Giảm rủi ro bằng cách:

- Dùng backoff có jitter cho retry.
- Giới hạn tốc độ tạo instance và số job đồng thời.
- Phân phối worker qua nhiều pool/AZ.
- Đặt concurrency limit theo dependency.
- Tách job ưu tiên cao và thấp.
- Không để mọi worker tải cùng một artifact lớn cùng thời điểm.
- Theo dõi backlog và khả năng xử lý thay thế.

## 9. Spot trong autoscaling group

Một nhóm máy có thể kết hợp nhiều loại instance và nhiều nguồn capacity. Cấu hình điển hình gồm:

- Danh sách instance type được phép.
- Tỷ lệ hoặc số lượng on-demand.
- Chiến lược lựa chọn Spot pool.
- Danh sách AZ.
- Desired/minimum/maximum capacity.
- Health check và replacement policy.
- Instance warmup.
- Lifecycle hook hoặc interruption handler.
- Capacity rebalance nếu dịch vụ hỗ trợ.

Capacity rebalance là cơ chế ở một số nền tảng nhằm chủ động thay thế instance được đánh giá có nguy cơ bị thu hồi trước khi nhận interruption notice cuối cùng. Cơ chế này có thể yêu cầu tạo máy mới trước, sau đó drain và loại máy cũ. Không phải lúc nào cũng có đủ capacity thay thế, vì vậy vẫn cần xử lý mất máy đột ngột.

### 9.1. Cách vận hành nhóm máy

1. Scaling policy phát hiện thiếu capacity.
2. Fleet manager chọn pool phù hợp từ danh sách được phép.
3. Instance được khởi chạy và đăng ký monitoring.
4. Health check xác nhận ứng dụng sẵn sàng.
5. Load balancer hoặc scheduler phân phối công việc.
6. Interruption handler nhận notice nếu có.
7. Worker ngừng nhận việc và checkpoint.
8. Fleet manager thay thế instance nếu còn capacity.
9. Scheduler giao lại task chưa hoàn tất.

Đừng đánh đồng desired capacity với healthy capacity. Một instance đang provisioning, boot hoặc warmup chưa chắc đóng góp năng lực xử lý thực tế.

## 10. Spot trong Kubernetes

Kubernetes có thể chạy node pool Spot cho workload chịu lỗi. Node Spot có thể bị nhà cung cấp thu hồi; Pod cần được thiết kế để reschedule và khôi phục.

Các thành phần cần phối hợp:

- Node pool hoặc node group được đánh dấu Spot.
- Taint/label để chỉ workload phù hợp được schedule lên node này.
- Toleration và node affinity ở Pod.
- Node termination handler hoặc cơ chế nhận interruption event.
- Drain node trước khi terminate khi có thời gian.
- PodDisruptionBudget (PDB) cho các eviction có thể kiểm soát.
- Replica trên nhiều node/AZ.
- Persistent state ở storage bền vững và cơ chế detach/reattach phù hợp.

### 10.1. Ví dụ tách workload Spot

Ví dụ node Spot được gắn label và taint riêng. Pod batch worker chấp nhận schedule lên nhóm node đó:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
spec:
  replicas: 8
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      nodeSelector:
        capacity-type: spot
      tolerations:
        - key: "capacity-type"
          operator: "Equal"
          value: "spot"
          effect: "NoSchedule"
      terminationGracePeriodSeconds: 90
      containers:
        - name: worker
          image: registry.example.com/batch-worker:3.0.0
          lifecycle:
            preStop:
              exec:
                command: ["/app/bin/stop-accepting-work"]
~~~

Đây là ví dụ minh họa; label, taint và cách nhận diện Spot phụ thuộc node provider/controller. Lệnh preStop phải tồn tại trong image và phải dừng nhận việc theo cách ứng dụng hỗ trợ. Kubernetes có thể gửi SIGTERM sau khi chạy hook; ứng dụng cần graceful shutdown và hoàn tất trong termination grace period.

### 10.2. Vai trò và giới hạn của PDB

PodDisruptionBudget giới hạn số Pod có thể bị gián đoạn bởi các eviction được Kubernetes kiểm soát. PDB giúp bảo vệ availability khi drain node có kế hoạch, nhưng không ngăn nhà cung cấp tắt máy đột ngột và không bảo đảm Pod luôn sống khi node bị mất.

Vì vậy:

- Duy trì đủ replica trên các node/AZ độc lập.
- Đặt PDB phù hợp với số replica và mức availability cần thiết.
- Cấu hình node termination handler để drain khi nhận notice.
- Kiểm thử tình huống node mất mà không có thời gian drain.
- Đảm bảo workload có retry, checkpoint hoặc state externalized.

Không dùng PDB như một bảo đảm chống Spot interruption.

## 11. Xử lý interruption trong ứng dụng

Ứng dụng cần biết cách ngừng nhận việc và hoàn tất công việc đang chạy.

Một worker xử lý queue có thể dùng quy trình:

1. Nhận interruption signal.
2. Chuyển trạng thái worker thành draining.
3. Dừng poll hoặc nhận message mới.
4. Hoàn thành batch hiện tại nếu còn đủ thời gian.
5. Commit kết quả bền vững.
6. Ack message hoặc cập nhật checkpoint sau commit.
7. Nếu không kịp, không ack để queue giao lại sau visibility timeout/lease.
8. Đóng consumer và thoát.

Không ack message trước khi kết quả được commit. Nếu worker bị thu hồi sau khi ack nhưng trước khi ghi kết quả, công việc có thể bị mất.

### 11.1. Ví dụ Java graceful shutdown

Đoạn mã minh họa một worker có thể dừng nhận task mới, chờ task hiện tại và lưu checkpoint:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WorkerLifecycle {
    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final ExecutorService executor;
    private final CheckpointStore checkpointStore;

    public WorkerLifecycle(
            ExecutorService executor,
            CheckpointStore checkpointStore) {
        this.executor = executor;
        this.checkpointStore = checkpointStore;
    }

    public boolean canAcceptWork() {
        return !draining.get();
    }

    public void onInterruption() {
        if (!draining.compareAndSet(false, true)) {
            return;
        }

        stopPollingForNewTasks();

        executor.shutdown();
        try {
            if (!executor.awaitTermination(45, TimeUnit.SECONDS)) {
                requestCooperativeStopAtSafeBoundary();
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    return; // Dùng checkpoint định kỳ khi task không thể dừng an toàn.
                }
            }
            checkpointStore.saveConsistentCheckpoint();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
        }
    }

    private void requestCooperativeStopAtSafeBoundary() {
        // Yêu cầu task dừng ở ranh giới an toàn theo giao thức của ứng dụng.
    }

    private void stopPollingForNewTasks() {
        // Dừng consumer hoặc scheduler theo API của ứng dụng.
    }

    interface CheckpointStore {
        void saveConsistentCheckpoint();
    }
}
~~~

Mã chỉ minh họa cấu trúc. Trong triển khai thật, cần xử lý lỗi checkpoint, trạng thái transaction, timeout còn lại và việc task bị interrupt. Không gọi checkpoint đồng thời với task đang ghi cùng state nếu chưa có cơ chế snapshot nhất quán.

Shutdown hook của JVM có thể giúp xử lý SIGTERM hoặc tín hiệu kết thúc có kiểm soát. Tuy nhiên, nó không bảo đảm chạy khi host mất điện, kernel panic hoặc provider thu hồi mà không có thông báo. Checkpoint định kỳ vẫn cần thiết.

### 11.2. Ngân sách thời gian shutdown

Thời gian shutdown phải ngắn hơn thời gian báo trước thực tế và thời gian termination grace được cấp. Dành ngân sách riêng cho:

- Dừng nhận việc mới.
- Hoàn tất request/task đang chạy.
- Ghi checkpoint.
- Flush log/metric.
- Đóng kết nối và thoát.

Nếu notice quá ngắn để hoàn tất job, bỏ dở có kiểm soát và giao lại task thường an toàn hơn cố gắng hoàn thành rồi ghi dữ liệu dở dang.

## 12. Lưu trữ và bảo vệ dữ liệu

Spot instance thường được xem là compute tạm thời. Thiết kế dữ liệu cần giả định local ephemeral storage có thể biến mất.

Nguyên tắc:

- Lưu dữ liệu bền vững trên database, object storage hoặc volume có lifecycle độc lập.
- Không lưu kết quả duy nhất trên root disk của Spot VM.
- Mã hóa volume, checkpoint và dữ liệu tạm.
- Dùng workload identity hoặc credential ngắn hạn.
- Không đóng gói secret vào image hoặc snapshot.
- Xóa hoặc thu hồi credential khi instance bị hủy.
- Đặt TTL cho file tạm và checkpoint cũ.
- Kiểm soát quyền truy cập checkpoint theo job/tenant.
- Ghi nhận version để tránh khôi phục state bằng binary không tương thích.

Nếu dùng persistent volume, xác minh semantics attach/detach, zone affinity và thời gian gắn volume vào máy thay thế. Volume không tự động di chuyển qua AZ trong mọi dịch vụ. Với dữ liệu stateful, cần thiết kế replication hoặc storage độc lập phù hợp.

## 13. Theo dõi và đo hiệu quả Spot

Đừng chỉ theo dõi số lượng instance đang chạy. Cần quan sát cả khả năng cấp capacity, interruption và công việc bị ảnh hưởng.

| Chỉ số | Ý nghĩa |
|---|---|
| Spot capacity requested/fulfilled | Capacity Spot yêu cầu và cấp được |
| Spot share | Tỷ lệ capacity đang chạy bằng Spot |
| Interruption count/rate | Số lần hoặc tỷ lệ instance bị thu hồi |
| Interruption reason | Nguyên nhân hoặc loại event nếu provider cung cấp |
| Notice-to-drain duration | Thời gian từ notice đến khi worker ngừng nhận việc |
| Checkpoint success rate | Tỷ lệ checkpoint hoàn tất thành công |
| Checkpoint age | Tuổi của checkpoint gần nhất |
| Work lost/retried | Khối lượng phải xử lý lại |
| Job completion rate | Tỷ lệ job hoàn tất |
| Queue backlog/age | Độ dài queue và tuổi của công việc chờ |
| Replacement time | Thời gian để có worker thay thế sẵn sàng |
| On-demand fallback share | Tỷ lệ capacity phải chuyển sang on-demand |
| Cost per completed unit | Chi phí trên mỗi job/record/frame hoàn tất |

Gắn interruption event với instance pool, instance type, AZ, image version và workload. Tránh dùng instance ID làm label cho mọi metric dài hạn nếu số instance rất lớn; có thể lưu ID trong event/log để điều tra chi tiết.

### 13.1. Cảnh báo cần có

- Interruption rate tăng đột biến trong một pool.
- Spot capacity không được cấp trong thời gian dài.
- On-demand fallback tăng vượt ngân sách.
- Checkpoint thất bại hoặc checkpoint quá cũ.
- Queue backlog tăng dù autoscaler đã scale-out.
- Replacement time vượt SLO.
- Job retry hoặc duplicate result tăng.
- Một AZ hoặc instance family trở thành điểm tập trung capacity.

Khi có interruption, phân biệt provider event với lỗi ứng dụng. Một instance bị thu hồi là hành vi có thể dự kiến của sản phẩm; checkpoint thất bại hoặc dữ liệu bị nhân đôi là lỗi thiết kế cần xử lý.

## 14. Kiểm thử khả năng chịu interruption

Không chờ lần Spot eviction đầu tiên trong production mới kiểm tra hệ thống. Có thể chủ động dừng worker hoặc node trong môi trường thử nghiệm để mô phỏng các điểm lỗi.

Kịch bản kiểm thử:

1. Dừng worker khi không có task đang chạy.
2. Dừng worker giữa một task nhưng sau checkpoint.
3. Dừng worker trong lúc ghi checkpoint.
4. Dừng worker sau khi commit kết quả nhưng trước khi ack message.
5. Mất node đột ngột không có notice.
6. Thu hồi nhiều worker cùng lúc.
7. Không cấp được Spot capacity thay thế.
8. Fallback sang on-demand trong giới hạn ngân sách.
9. Kiểm tra job không bị mất và kết quả không bị nhân đôi.
10. Đo thời gian phục hồi và chi phí xử lý lại.

Sau mỗi bài test, đối chiếu queue, checkpoint, database và output. Một test chỉ chứng minh Pod hoặc VM được tạo lại chưa đủ; cần chứng minh công việc nghiệp vụ được tiếp tục đúng.

## 15. Những lỗi thường gặp

**Dùng Spot cho workload không thể gián đoạn:** một singleton hoặc primary không có failover có thể làm cả dịch vụ ngừng hoạt động. Chỉ đưa phần capacity có thể thay thế lên Spot.

**Chỉ dựa vào interruption notice:** host có thể lỗi hoặc biến mất trước khi handler chạy. Dùng checkpoint định kỳ và lease/heartbeat.

**Lưu state duy nhất trên local disk:** dữ liệu mất khi instance bị thu hồi. Ghi state vào storage bền vững.

**Ack message trước khi commit:** interruption có thể làm mất công việc. Commit kết quả rồi mới ack.

**Retry không có idempotency:** worker mới có thể tạo kết quả trùng. Dùng idempotency key, transaction hoặc fencing token.

**Chỉ chọn pool rẻ nhất:** pool rẻ có thể thiếu capacity hoặc interruption nhiều. Đo chi phí mỗi kết quả hoàn tất và cân nhắc capacity-optimized.

**Chỉ dùng một instance type/AZ:** làm fleet phụ thuộc vào pool hẹp. Đa dạng hóa trong nhóm phần cứng tương thích.

**Toàn bộ fleet dùng Spot:** một đợt thu hồi có thể làm mất capacity cùng lúc. Duy trì on-demand baseline hoặc fallback phù hợp.

**Đặt PDB rồi cho rằng node không thể bị thu hồi:** PDB không chặn việc provider tắt máy đột ngột. Dùng replica, drain handler và recovery.

**Shutdown hook làm checkpoint quá lâu:** thời gian còn lại có thể hết trước khi lưu xong. Checkpoint định kỳ và giới hạn thời gian shutdown.

**Không kiểm thử thiếu capacity:** autoscaler có thể không tìm được Spot pool. Có fallback, queue buffering và giới hạn backlog.

**Chỉ so sánh giá mỗi giờ:** bỏ qua retry, checkpoint và công việc bị mất. Đo chi phí trên mỗi đơn vị công việc thành công.

## 16. Checklist triển khai Spot/preemptible

- [ ] Đã đọc chính sách interruption, notice, runtime limit và billing của đúng dịch vụ.
- [ ] Workload có thể retry, checkpoint hoặc được thay thế an toàn.
- [ ] State và kết quả được lưu ngoài instance có thể thu hồi.
- [ ] Job/message có idempotency key hoặc cơ chế chống xử lý trùng.
- [ ] Worker có heartbeat/lease và scheduler phát hiện mất máy.
- [ ] Có handler dừng nhận việc mới khi nhận interruption notice.
- [ ] Hệ thống vẫn đúng khi mất máy đột ngột không có notice.
- [ ] Checkpoint được ghi nguyên tử, xác minh và có version.
- [ ] Fleet đa dạng instance type và AZ trong phạm vi tương thích.
- [ ] Có on-demand baseline hoặc fallback theo SLO và ngân sách.
- [ ] Autoscaler phân biệt capacity yêu cầu, capacity đang khởi động và capacity healthy.
- [ ] Kubernetes node Spot có taint/label, termination handler và drain policy phù hợp.
- [ ] PDB được dùng đúng phạm vi và không bị coi là bảo đảm chống eviction cưỡng bức.
- [ ] Có metric interruption, checkpoint, retry, backlog và cost per completed unit.
- [ ] Đã thử interruption giữa task, lúc ghi checkpoint và mất máy đột ngột.
- [ ] Credential, volume, snapshot và dữ liệu tạm được bảo vệ khi instance bị hủy.
- [ ] Có giới hạn chi phí và cảnh báo khi fallback on-demand tăng cao.

Spot, preemptible và interruptible compute cho phép tận dụng capacity dư thừa với chi phí thấp hơn, nhưng đổi lại workload phải chấp nhận việc máy có thể bị thu hồi. Hãy dùng chúng cho công việc có thể chia nhỏ, retry hoặc khôi phục từ checkpoint; lưu state ở hệ thống bền vững và bảo đảm thao tác idempotent. Kết hợp Spot với capacity on-demand, đa dạng hóa pool và đo chi phí trên mỗi kết quả hoàn tất sẽ giúp giảm chi phí mà vẫn giữ khả năng phục hồi khi capacity bị gián đoạn.
