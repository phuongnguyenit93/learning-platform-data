# Nhận diện workload phù hợp với tài nguyên có thể bị thu hồi

Tài nguyên compute có thể bị thu hồi (interruptible compute) thường có giá thấp hơn tài nguyên được bảo đảm khả dụng liên tục, đổi lại nhà cung cấp có thể thu hồi máy hoặc capacity khi cần. Các tên gọi như Spot, Preemptible hay Interruptible là nhãn sản phẩm của từng nền tảng; điều kiện cấp phát, thông báo thu hồi, thời gian chạy và cách tính phí có thể khác nhau. Vì vậy, việc chọn loại máy chỉ dựa trên mức giảm giá là chưa đủ.

Yếu tố quyết định là khả năng của workload khi một instance biến mất bất ngờ. Một tác vụ batch có checkpoint và có thể chạy lại thường phù hợp. Một dịch vụ giữ phiên người dùng trong bộ nhớ, một database primary hoặc một job không thể khôi phục giữa chừng thường cần capacity ổn định hơn. Nhiều hệ thống có thể kết hợp hai loại: giữ một phần capacity nền trên máy thông thường và dùng tài nguyên có thể bị thu hồi để xử lý phần tải linh hoạt.

Bài học này hướng dẫn cách phân loại workload, đánh giá mức chịu gián đoạn, tính hiệu quả kinh tế và thiết kế cơ chế phục hồi trước khi đưa workload lên Spot hoặc Preemptible compute. Sau bài học, bạn có thể:

- Nhận diện workload có thể chạy trên tài nguyên bị thu hồi và workload cần capacity ổn định.
- Đánh giá khả năng retry, checkpoint, khởi động lại và phục hồi trạng thái.
- Phân biệt trạng thái tạm với dữ liệu bền vững, đồng thời bảo vệ tính nhất quán khi instance bị dừng.
- Thiết kế worker, batch, pipeline dữ liệu và job huấn luyện để chịu interruption.
- Ước lượng chi phí thực sau khi tính thời gian chạy lại, checkpoint và công suất dự phòng.
- Kết hợp interruptible với on-demand hoặc capacity được bảo đảm theo mô hình hybrid.
- Kiểm thử kịch bản thu hồi và đặt tiêu chí quyết định cho từng workload.

## 1. Bản chất của interruptible compute

Nhà cung cấp cloud có thể bán một phần capacity chưa được cam kết dài hạn với mức giá thấp hơn. Khi capacity đó cần được phân bổ cho nhu cầu ưu tiên cao hơn hoặc theo chính sách vận hành của nền tảng, instance có thể bị thu hồi. Người dùng không nên giả định instance sẽ tồn tại cho tới khi workload hoàn tất.

Các sản phẩm thường gặp có tên Spot, Preemptible hoặc Interruptible. Chúng có thể khác nhau về:

- Lý do thu hồi và điều kiện capacity bị lấy lại.
- Thời gian thông báo trước khi dừng hoặc terminate.
- Hành vi khi bị thu hồi: shutdown, stop, hibernate hoặc terminate.
- Khả năng giữ lại boot disk và data disk.
- Giới hạn thời gian chạy tối đa, nếu có.
- Cách tính phí phần thời gian đã sử dụng và chi phí lưu trữ còn lại.
- Cơ chế tự động thử cấp phát lại hoặc thay instance.

Không nên coi một thời lượng cảnh báo cụ thể là bảo đảm chung cho mọi cloud. Một số nền tảng gửi tín hiệu trước khi thu hồi, nhưng thời gian có thể ngắn, có thể khác theo loại sự kiện và không phải lúc nào ứng dụng cũng xử lý kịp. Thiết kế đúng phải chịu được trường hợp tiến trình bị dừng đột ngột mà không kịp checkpoint.

### So sánh với capacity thông thường

| Đặc điểm | Capacity được bảo đảm/on-demand | Capacity có thể bị thu hồi |
|---|---|---|
| Mục đích | Duy trì dịch vụ theo nhu cầu đã cấp phát | Tận dụng capacity dư hoặc có điều kiện |
| Giá | Thường cao hơn hoặc theo cam kết riêng | Thường thấp hơn, có thể biến động |
| Khả năng tồn tại | Không bị thu hồi theo cơ chế Spot thông thường, nhưng vẫn có sự cố hạ tầng | Có thể bị thu hồi khi nền tảng cần capacity |
| Phù hợp | Thành phần quan trọng, stateful, latency/SLO nghiêm ngặt | Tác vụ có thể retry, checkpoint hoặc phân tán |
| Vận hành | Cần xử lý lỗi máy như mọi hệ thống phân tán | Cần thêm logic interruption và thay thế capacity |

Capacity thông thường vẫn có thể gặp lỗi phần cứng, reboot hoặc sự cố vùng. Interruptible compute bổ sung một nguồn gián đoạn có thể xảy ra theo chính sách cấp phát. Vì vậy, khả năng chịu lỗi vẫn cần thiết ngay cả khi không dùng Spot.

## 2. Tiêu chí nhận diện workload phù hợp

Hãy đánh giá workload theo khả năng phục hồi, không chỉ theo thời lượng chạy hay mức sử dụng CPU.

### Có thể chia nhỏ và chạy lại

Workload phù hợp thường có thể chia thành các đơn vị độc lập:

- Một file, ảnh, video hoặc bản ghi có thể xử lý riêng.
- Một message trong queue có thể được giao lại nếu worker dừng.
- Một shard hoặc partition có thể được xử lý lại mà không làm hỏng kết quả đã hoàn tất.
- Một test suite hoặc build job có thể chạy lại từ đầu.
- Một batch có thể chia thành nhiều task có checkpoint.

Nếu một job kéo dài 10 giờ nhưng chỉ lưu kết quả khi kết thúc, việc bị thu hồi ở giờ thứ 9 có thể làm mất gần toàn bộ công sức. Nếu job được chia thành các task 5 phút hoặc checkpoint định kỳ, lượng công việc phải làm lại giảm đáng kể.

### Có thể retry an toàn

Retry chỉ an toàn khi thực thi lặp lại không tạo tác dụng phụ sai. Ví dụ, xử lý lại một ảnh và ghi kết quả vào cùng object key có thể an toàn nếu thao tác ghi là idempotent. Ngược lại, gửi lại một lệnh trừ tiền hoặc gửi email có thể tạo giao dịch trùng.

Hãy xác định:

- Tác vụ có thể chạy nhiều lần mà kết quả cuối vẫn đúng không?
- Có idempotency key hoặc unique job ID không?
- Có cơ chế deduplication hoặc transactional outbox không?
- Tác vụ có thể dừng giữa một thao tác ghi hay không?
- Có thể phân biệt task hoàn tất với task đang xử lý dở không?

Không nên retry vô hạn. Cần giới hạn số lần, exponential backoff có jitter, dead-letter queue và quy trình xử lý task thất bại vĩnh viễn.

### Có thể checkpoint và khôi phục

Checkpoint lưu trạng thái đủ để tiếp tục công việc sau khi tiến trình khởi động lại. Checkpoint có thể chứa:

- Vị trí đã xử lý trong tập dữ liệu hoặc offset của queue.
- Tham số và trạng thái thuật toán.
- Model weights, optimizer state và số bước huấn luyện.
- Trạng thái pipeline, partition và kết quả trung gian.
- Phiên bản code, dataset, schema và cấu hình cần để tiếp tục.

Checkpoint phải được ghi ra nơi lưu trữ bền vững bên ngoài instance, ví dụ object storage hoặc volume có vòng đời độc lập. Lưu checkpoint trên ổ đĩa tạm của máy bị thu hồi không giúp phục hồi.

### Không phụ thuộc vào một instance duy nhất

Workload càng ít gắn với một máy cụ thể càng dễ dùng interruptible compute. Hãy hỏi:

- Có thể khởi chạy lại ở instance khác không?
- Có thể tái tạo môi trường từ image hoặc container image không?
- Dữ liệu cần thiết có nằm ngoài instance không?
- Có thể phát hiện và thay thế worker bị mất tự động không?
- Có dependency hoặc license bị ràng buộc vào host identity không?

Nếu câu trả lời là không, cần tái cấu trúc hoặc giữ thành phần đó trên capacity ổn định.

## 3. Ma trận phân loại workload

| Workload | Mức phù hợp ban đầu | Điều kiện cần |
|---|---|---|
| Batch xử lý ảnh/video | Cao | Task độc lập, kết quả bền vững, retry idempotent |
| CI build và test | Cao | Source/artifact lưu ngoài máy, job có thể chạy lại |
| Render đồ họa | Cao | Frame hoặc chunk độc lập, checkpoint tiến độ |
| ETL và data processing | Cao đến trung bình | Partition, checkpoint offset, xử lý trùng an toàn |
| Huấn luyện ML phân tán | Trung bình đến cao | Checkpoint model/optimizer, orchestration chịu lỗi, đồng bộ worker |
| Inference batch/offline | Cao | Queue, retry, output idempotent và giới hạn thời hạn |
| API stateless có thể scale ngang | Trung bình | Có capacity ổn định dự phòng, backend health check và thay instance nhanh |
| WebSocket hoặc phiên dài | Thấp đến trung bình | Client reconnect, session externalized và có capacity dự phòng |
| Database primary hoặc message broker quorum | Thấp | Cần ổn định, replication và failover được thiết kế chuyên biệt |
| Hệ thống license khóa theo host | Thấp | Nhà cung cấp license cho phép thay host và khởi chạy lại |
| Tác vụ tương tác có deadline rất ngắn | Thấp | Không thể chịu thời gian cấp phát lại hoặc retry |
| Hệ thống điều khiển stateful duy nhất | Thấp | Cần thiết kế HA/failover riêng trước khi dùng capacity có thể thu hồi |

Đây là phân loại ban đầu. Một workload không phù hợp ở dạng hiện tại có thể trở nên phù hợp sau khi tách state, thêm queue, checkpoint hoặc chuyển dữ liệu sang dịch vụ bền vững.

## 4. Workload thường phù hợp

### Batch processing

Batch job thường xử lý một tập dữ liệu rồi kết thúc, nên dễ chia thành nhiều task độc lập. Ví dụ, hệ thống chuyển mã video chia mỗi video thành các đoạn; hệ thống xử lý ảnh chia theo object; pipeline ETL chia theo partition hoặc ngày dữ liệu.

Kiến trúc tham khảo:

~~~mermaid
flowchart TD
    A["Dataset / object storage"] --> B["Job queue"]
    B --> C["Interruptible worker pool"]
    C --> D["Xử lý task độc lập"]
    D --> E["Ghi output bền vững"]
    E --> F["Đánh dấu task hoàn tất"]
    C -. "worker bị thu hồi" .-> G["Visibility timeout / retry"]
    G --> B
~~~

Queue giữ trạng thái công việc. Worker nhận task, xử lý và chỉ xác nhận hoàn tất sau khi output đã được ghi bền vững. Nếu worker biến mất trước acknowledgement, queue có thể giao lại task sau visibility timeout. Hệ thống cần xử lý khả năng task chạy hai lần.

### CI/CD, build và test

Build, unit test, integration test và một số kiểm thử hiệu năng có thể chạy trên interruptible worker nếu:

- Source code và dependency được lấy lại từ repository hoặc cache dùng chung.
- Build artifact được lưu vào registry hoặc artifact store.
- Log và kết quả test được đẩy ra ngoài worker.
- Job có thể chạy lại từ đầu hoặc tiếp tục từ cache an toàn.
- Pipeline không giữ khóa triển khai hoặc thực hiện thay đổi production không thể lặp.

Không nên để worker Spot vừa build vừa giữ credential triển khai production lâu dài. Dùng danh tính workload ngắn hạn, quyền tối thiểu và tách bước build khỏi bước phát hành có kiểm soát.

### Render, encode và xử lý media

Frame, scene, đoạn video hoặc tác vụ encode có thể chia nhỏ. Lưu manifest ghi rõ task nào đã hoàn tất, output nào đã được xác minh và task nào cần chạy lại. Với render, cần đảm bảo các chunk dùng cùng phiên bản asset, plugin và cấu hình để kết quả ghép lại nhất quán.

### Data engineering và analytics

ETL, map/reduce, truy vấn batch và xử lý log có thể phù hợp nếu partition có thể chạy lại. Hãy lưu checkpoint theo offset hoặc watermark và dùng sink có cơ chế upsert/deduplication. Nếu pipeline có side effect ngoài dữ liệu, cần tách side effect thành bước riêng có idempotency.

## 5. Workload cần thận trọng hoặc tránh

### Database primary và hệ thống lưu trữ stateful

Database primary, metadata store hoặc node giữ trạng thái duy nhất có thể không phù hợp nếu chưa có replication, failover và quy trình phục hồi. Thu hồi instance có thể làm gián đoạn ghi, kéo dài thời gian recovery hoặc làm tăng nguy cơ split-brain nếu fencing không đúng.

Có thể dùng interruptible cho replica đọc, query worker hoặc tác vụ backup phụ trợ nếu hệ thống hỗ trợ và đã kiểm thử. Không đặt database primary, quorum voter quan trọng hoặc storage controller lên Spot chỉ vì chi phí thấp.

### Dịch vụ tương tác có SLO nghiêm ngặt

Một API có thể chạy trên interruptible capacity nếu có đủ capacity ổn định dự phòng và instance bị thu hồi được thay thế nhanh. Tuy nhiên, nếu toàn bộ backend đều là Spot, một đợt thu hồi cùng lúc có thể làm mất năng lực phục vụ. Với API latency thấp, nên giữ baseline trên capacity ổn định và chỉ dùng Spot cho phần burst hoặc workload có thể bị trì hoãn.

### Phiên làm việc dài và trạng thái trong bộ nhớ

Desktop session, WebSocket, game session hoặc tiến trình giữ state trong RAM sẽ bị ảnh hưởng khi máy bị thu hồi. Chỉ nên dùng nếu client có thể reconnect, session state được externalize, tác vụ có checkpoint hoặc người dùng chấp nhận mất phiên.

### Job có deadline cứng và không thể chia nhỏ

Nếu job phải hoàn tất trước một thời điểm và không có khả năng restart đủ nhanh, interruption có thể khiến vi phạm deadline. Cần tính xác suất bị thu hồi, thời gian chạy lại và capacity dự phòng. Có thể chạy phần quan trọng trên máy ổn định và chỉ đưa phần không bắt buộc vào Spot.

## 6. Đánh giá mức chịu gián đoạn

Để quyết định có dùng interruptible hay không, hãy chấm workload theo các câu hỏi sau:

| Tiêu chí | Tốt cho interruptible | Rủi ro cao |
|---|---|---|
| Khả năng chia nhỏ | Task độc lập, kích thước vừa phải | Một tiến trình lớn, không chia được |
| Retry | Idempotent, có deduplication | Retry gây giao dịch trùng hoặc dữ liệu sai |
| Checkpoint | Lưu thường xuyên, khôi phục đã kiểm thử | Không checkpoint hoặc checkpoint quá chậm |
| State | Externalized, có thể tái tạo | Chỉ nằm trong RAM/local disk |
| Deadline | Có thể trì hoãn hoặc chạy lại | Deadline cứng, không có capacity thay thế |
| Startup | Khởi động nhanh, image chuẩn hóa | Warm-up dài, license hoặc dữ liệu khó nạp |
| Dependency | Có capacity và quota dự phòng | Phụ thuộc vào một dịch vụ đã gần bão hòa |
| Quan sát | Có tiến độ, heartbeat và phát hiện worker mất | Không biết task dừng ở đâu |
| Tính nhất quán | Output atomic/versioned | Ghi dở có thể làm hỏng dữ liệu |

Có thể dùng thang điểm nội bộ để sàng lọc, nhưng không nên cộng điểm rồi bỏ qua một điều kiện loại trừ. Ví dụ, workload có điểm cao ở mọi mục nhưng retry có thể trừ tiền hai lần vẫn chưa an toàn.

### Câu hỏi quyết định

1. Nếu instance dừng ngay lúc này, phần công việc mất tối đa là bao nhiêu?
2. Có thể khôi phục từ checkpoint trong bao lâu?
3. Có đủ capacity khác để chạy lại trước deadline không?
4. Task có thể bị giao lại nhiều lần mà vẫn tạo một kết quả đúng không?
5. Nếu nhiều instance bị thu hồi cùng lúc, hệ thống còn phục vụ được không?
6. Dữ liệu và log cần thiết có còn sau khi instance bị xóa không?

## 7. Thiết kế checkpoint và phục hồi

Checkpoint là một phần quan trọng của workload dài. Tần suất checkpoint cần cân bằng giữa chi phí ghi và lượng công việc có thể mất.

### Chọn chu kỳ checkpoint

Giả sử:

- Mỗi lần checkpoint mất thời gian \(C\).
- Thời gian giữa hai checkpoint là \(T\).
- Chi phí khởi động lại và phục hồi là \(R\).
- Tỷ lệ gián đoạn kỳ vọng là \(\lambda\) lần trên một đơn vị thời gian.

Checkpoint quá thường xuyên làm giảm thời gian hữu ích vì phải ghi trạng thái. Checkpoint quá thưa làm tăng lượng công việc phải chạy lại. Có thể bắt đầu bằng mô hình gần đúng để ước lượng khoảng checkpoint, sau đó đo thực tế với kích thước state và tốc độ lưu trữ thật. Với workload không có phân phối interruption ổn định, ưu tiên chọn chu kỳ dựa trên RPO của công việc và kiểm thử các tình huống mất máy.

Không cần checkpoint toàn bộ RAM nếu có thể lưu trạng thái thuật toán nhỏ hơn. Ví dụ, ETL có thể lưu offset đã commit; xử lý file có thể lưu danh sách chunk hoàn tất; training có thể lưu model, optimizer và step number.

### Ghi checkpoint an toàn

Một quy trình phổ biến:

1. Tạo checkpoint mới ở một đường dẫn tạm hoặc object key version mới.
2. Ghi đầy đủ dữ liệu và metadata.
3. Xác minh kích thước, checksum và khả năng đọc.
4. Flush hoặc hoàn tất upload theo bảo đảm của storage.
5. Chỉ sau đó mới cập nhật manifest hoặc con trỏ checkpoint hiện hành.
6. Giữ lại một vài phiên bản trước để phục hồi nếu checkpoint mới bị lỗi.

Không ghi đè checkpoint hợp lệ trước khi checkpoint mới được xác minh. Với object storage, có thể dùng object versioning hoặc key theo phiên bản. Với filesystem, dùng file tạm rồi atomic rename khi semantics của filesystem cho phép.

### Xử lý interruption notice

Nếu nền tảng phát tín hiệu thu hồi, agent hoặc ứng dụng nên:

- Ngừng nhận task mới.
- Đánh dấu worker đang drain để scheduler không giao thêm công việc.
- Lưu checkpoint nếu còn đủ thời gian và checkpoint an toàn.
- Hoàn tất thao tác ghi đang diễn ra hoặc rollback giao dịch chưa commit.
- Đẩy heartbeat và tiến độ cuối cùng ra hệ thống điều phối.
- Thoát gọn trước thời điểm dừng nếu có thể.

Không phụ thuộc hoàn toàn vào notice. Một số trường hợp instance có thể bị dừng mà ứng dụng không kịp xử lý. Supervisor cần phát hiện heartbeat mất, lease hết hạn hoặc worker biến mất để giao lại task.

## 8. Retry, idempotency và queue semantics

Interruptible worker thường cần ít nhất một cơ chế điều phối công việc bền vững. Queue hoặc scheduler nên lưu trạng thái task bên ngoài worker.

### Vòng đời task

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Leased: Worker nhận task
    Leased --> Completed: Output đã commit
    Leased --> Pending: Lease hết hạn / worker mất
    Leased --> RetryWait: Lỗi có thể thử lại
    RetryWait --> Pending: Hết backoff
    RetryWait --> DeadLetter: Vượt giới hạn retry
    Completed --> [*]
    DeadLetter --> [*]
~~~

Worker chỉ nên acknowledge sau khi output được ghi bền vững. Nếu worker bị thu hồi sau khi ghi output nhưng trước khi acknowledge, task có thể chạy lại. Vì vậy, output cần idempotent:

- Dùng task ID ổn định và ghi kết quả theo ID đó.
- Dùng unique constraint hoặc conditional write để tránh tạo bản ghi trùng.
- Dùng trạng thái processing/completed có lease hoặc fencing token.
- Tách side effect không thể lặp khỏi bước tính toán có thể retry.
- Đưa task thất bại nhiều lần vào dead-letter queue để điều tra.

### Lease và fencing

Một worker có thể bị pause hoặc mất kết nối nhưng chưa dừng hoàn toàn. Nếu scheduler giao cùng task cho worker khác, hai worker có thể cùng ghi dữ liệu. Lease giới hạn thời gian worker được quyền xử lý; fencing token hoặc generation number giúp sink từ chối ghi từ worker cũ sau khi quyền đã được cấp cho worker mới.

Không nên chỉ dựa trên heartbeat để bảo đảm độc quyền. Heartbeat có thể trễ do network hoặc máy bị treo. Các thao tác ghi quan trọng cần được bảo vệ bằng transaction, compare-and-swap, version hoặc fencing ở nơi lưu trữ.

## 9. Phân bổ capacity và giảm rủi ro thiếu máy

Spot capacity không phải lúc nào cũng có sẵn ở mọi loại instance, vùng hoặc zone. Một yêu cầu cấp phát có thể thất bại ngay cả khi không có instance nào đang chạy. Workload nên có chiến lược đa dạng hóa:

- Cho phép nhiều instance family hoặc kích thước tương đương nếu ứng dụng hỗ trợ.
- Dùng nhiều availability zone hoặc capacity pool khi dữ liệu và kiến trúc cho phép.
- Đặt giới hạn số instance theo từng loại để tránh tập trung vào một pool khan hiếm.
- Có fallback sang on-demand hoặc capacity ổn định cho phần tải cần hoàn tất.
- Tách task ưu tiên cao khỏi task có thể trì hoãn.

Đa dạng hóa không có nghĩa chọn bất kỳ loại máy nào. Cần kiểm tra kiến trúc CPU, RAM, GPU, network, local storage, instruction set và driver. Với GPU, model và workload phải chạy được trên các accelerator family được chọn; không phải mọi GPU đều tương đương.

### Baseline ổn định và burst interruptible

Một kiến trúc hybrid thường giữ một phần capacity ổn định đủ phục vụ tải tối thiểu, sau đó dùng Spot để bổ sung:

~~~mermaid
flowchart TD
    L["Workload / queue"] --> S["Scheduler"]
    S --> O["Pool capacity ổn định"]
    S --> P["Pool interruptible"]
    O --> R["Xử lý task ưu tiên / baseline"]
    P --> B["Xử lý task có thể retry / batch"]
    R --> D[("Durable output")]
    B --> D
    P -. "Capacity bị thu hồi" .-> Q["Requeue / retry / checkpoint"]
    Q --> L
~~~

Capacity ổn định có thể phục vụ request tương tác, điều phối và task không thể trì hoãn. Interruptible pool xử lý phần việc có thể chia nhỏ hoặc xếp hàng. Nếu Spot capacity biến mất, hàng đợi tăng nhưng dịch vụ chính vẫn duy trì ở mức đã thiết kế.

## 10. Tính hiệu quả kinh tế thực tế

Giá theo giờ thấp hơn không đồng nghĩa tổng chi phí luôn thấp hơn. Hãy tính chi phí trên một đơn vị công việc hoàn thành.

Một mô hình đơn giản:

**Chi phí hiệu dụng = chi phí compute + lưu trữ checkpoint + truyền dữ liệu + điều phối + công việc chạy lại**

**Chi phí trên một tác vụ thành công = tổng chi phí hiệu dụng / số tác vụ hoàn tất hợp lệ**

Các yếu tố cần tính:

- Mức giá interruptible thực tế trong từng vùng và thời điểm.
- Thời gian instance chạy hữu ích trước khi bị thu hồi.
- Tỷ lệ task phải chạy lại và thời gian bị mất.
- Chi phí tạo checkpoint, đọc checkpoint và lưu trữ.
- Chi phí truyền dữ liệu khi task được chuyển sang instance khác.
- Thời gian khởi động, tải image, model hoặc dataset.
- Chi phí capacity dự phòng ổn định.
- Chi phí vận hành và độ phức tạp tăng thêm.

### Ví dụ tính đơn giản

Giả sử một batch cần 100 giờ compute hữu ích. On-demand có giá 1 đơn vị/giờ. Interruptible có giá 0,4 đơn vị/giờ. Nếu do interruption, tổng giờ compute phải chạy là 125 giờ và chi phí checkpoint/storage/transfer là 5 đơn vị:

| Phương án | Compute cost | Chi phí phụ | Tổng |
|---|---:|---:|---:|
| On-demand | 100 × 1 = 100 | 0 | 100 |
| Interruptible | 125 × 0,4 = 50 | 5 | 55 |

Trong ví dụ này, interruptible vẫn tiết kiệm. Nhưng nếu thời gian chạy lại tăng lên 230 giờ và chi phí phụ là 10, tổng sẽ là 102 đơn vị, cao hơn on-demand. Các con số chỉ minh họa; cần lấy giá, lịch sử interruption và thời gian xử lý thực tế của môi trường mục tiêu.

### Không tối ưu chỉ theo phần trăm giảm giá

Hãy theo dõi:

- Cost per successful job.
- Tỷ lệ task bị retry hoặc dead-letter.
- Tỷ lệ thời gian compute hữu ích trên tổng thời gian instance.
- Thời gian từ lúc interruption tới khi task được tiếp tục.
- Chi phí lưu checkpoint và dữ liệu trung gian.
- Mức độ đáp ứng deadline và SLO.

Nếu tiết kiệm compute nhưng thường xuyên trễ deadline, lựa chọn đó có thể không phù hợp với sản phẩm.

## 11. Chọn kích thước task và thời lượng chạy

Task quá dài làm tăng lượng công việc có thể mất khi bị thu hồi. Task quá ngắn làm tăng overhead điều phối, startup và ghi metadata.

Hãy cân bằng:

- Thời lượng task so với khả năng bị interruption.
- Thời gian khởi động worker và tải dữ liệu.
- Chi phí checkpoint và tần suất commit.
- Kích thước output và thời gian upload.
- Khả năng chia task và phân phối đều.
- Deadline và tốc độ xử lý backlog.

Ví dụ, một pipeline chuyển mã có thể chia video thành chunk 2–5 phút thay vì một job 2 giờ, nếu codec và quy trình ghép cho phép. Một job huấn luyện không nhất thiết checkpoint mỗi batch; có thể lưu theo số step hoặc khoảng thời gian đã đo để cân bằng chi phí.

Không có một thời lượng task tối ưu chung. Hãy chạy thử với vài kích thước task và so sánh throughput thành công, thời gian khôi phục và chi phí trên đơn vị công việc.

## 12. Bảo mật và quản lý dữ liệu

Instance có thể bị thu hồi, thay thế hoặc khởi chạy ở capacity pool khác. Vì vậy, không nên lưu bí mật hoặc dữ liệu quan trọng chỉ trên máy:

- Lấy credential ngắn hạn từ workload identity hoặc secret manager.
- Không nhúng private key, token dài hạn hoặc mật khẩu vào image.
- Dùng quyền tối thiểu cho bucket, queue, database và registry.
- Mã hóa dữ liệu truyền và lưu trữ theo chính sách.
- Giới hạn metadata service và bảo vệ instance identity.
- Xóa dữ liệu tạm hoặc cache nhạy cảm khi instance kết thúc.
- Ghi log và audit event ra hệ thống bên ngoài instance.

Với dữ liệu nhạy cảm, kiểm tra vị trí lưu trữ, vùng xử lý, quyền truy cập và quy định lưu giữ. Tài nguyên rẻ hơn không làm giảm trách nhiệm bảo vệ dữ liệu.

## 13. Các mẫu kiến trúc tham khảo

### Worker stateless với queue

- Queue giữ task bền vững.
- Worker có thể bị dừng và khởi động lại ở máy khác.
- Output được ghi theo task ID và chỉ acknowledge sau khi commit.
- Lease hết hạn sẽ cho phép giao lại task.
- Dead-letter queue giữ task lỗi cần can thiệp.

Đây thường là mẫu dễ bắt đầu nhất với interruptible compute.

### Batch có checkpoint

- Scheduler chia batch thành partition.
- Mỗi partition ghi checkpoint và output riêng.
- Worker bị thu hồi chỉ làm chạy lại partition chưa hoàn tất.
- Bộ tổng hợp xác minh tất cả partition trước khi công bố kết quả.

### Distributed training

- Một nhóm capacity ổn định có thể giữ vai trò điều phối hoặc parameter service nếu kiến trúc cần.
- Worker interruptible tham gia tính toán theo cơ chế chịu lỗi.
- Training checkpoint gồm model, optimizer, scheduler, random state và step.
- Khi worker mất, orchestration tái lập worker hoặc khôi phục từ checkpoint gần nhất.
- Với synchronous training, một worker mất có thể làm cả nhóm chờ; cần đánh giá elastic training, worker replacement và checkpoint cadence.

Không phải mọi framework distributed training đều hỗ trợ thay worker đang chạy. Hãy kiểm tra semantics của framework và thử interruption thực tế trước khi chuyển workload.

### Hybrid API và batch

- API phục vụ tương tác trên capacity ổn định.
- Request nặng được đưa vào queue.
- Interruptible worker xử lý tác vụ nền có thể retry.
- Kết quả được lưu bền vững và API trả trạng thái tiến độ.

Cách tách này giúp người dùng không phụ thuộc vào việc một Spot instance còn tồn tại trong suốt request dài.

## 14. Kiểm thử interruption trước khi đưa vào production

Không nên đợi nhà cung cấp thu hồi máy thật mới biết ứng dụng có phục hồi được hay không. Hãy chủ động mô phỏng:

1. Dừng worker giữa lúc xử lý task.
2. Dừng worker sau khi ghi output nhưng trước acknowledgement.
3. Dừng worker trong lúc đang ghi checkpoint.
4. Mất kết nối mạng tới queue hoặc object storage.
5. Làm chậm checkpoint hoặc khiến checkpoint thất bại.
6. Thu hồi nhiều worker cùng lúc.
7. Thử cấp phát lại nhưng pool Spot không còn capacity.
8. Chuyển task sang loại instance khác.
9. Khởi chạy lại từ checkpoint cũ và xác minh kết quả.

Tiêu chí đạt:

- Không mất task đã được xác nhận.
- Task có thể chạy lại mà không tạo output hoặc side effect trùng.
- Checkpoint hỏng không ghi đè checkpoint tốt trước đó.
- Hệ thống phát hiện worker mất trong thời gian chấp nhận được.
- Queue không tăng vô hạn và có backpressure.
- Workload hoàn tất trong deadline hoặc có cơ chế fallback.
- Chi phí thực tế vẫn đạt mục tiêu sau khi tính retry và phục hồi.

## 15. Quy trình lựa chọn workload

~~~mermaid
flowchart TD
    A["Xác định workload và SLO"] --> B{"Có thể chia nhỏ hoặc retry?"}
    B -- "Không" --> C{"Có thể externalize state và thêm checkpoint?"}
    C -- "Không" --> D["Dùng capacity ổn định"]
    C -- "Có" --> E["Thiết kế phục hồi và kiểm thử"]
    B -- "Có" --> E
    E --> F{"Retry có idempotent và dữ liệu bền vững?"}
    F -- "Không" --> G["Bổ sung deduplication / transaction / checkpoint"]
    G --> H["Thử interruption và phục hồi"]
    F -- "Có" --> H
    H --> I{"Đạt SLO, deadline và chi phí?"}
    I -- "Không" --> D
    I -- "Có" --> J["Chạy canary interruptible"]
    J --> K["Mở rộng dần và theo dõi"]
~~~

Một quy trình thực tế:

1. Mô tả tác vụ, deadline, SLO và dữ liệu cần giữ.
2. Phân loại state, dependency và khả năng chia nhỏ.
3. Thiết kế queue, retry, checkpoint hoặc cơ chế resume.
4. Chọn loại instance và pool đa dạng tương thích.
5. Tính chi phí hiệu dụng và capacity dự phòng.
6. Mô phỏng interruption trong staging.
7. Chạy canary trên một phần workload.
8. Theo dõi tỷ lệ interruption, retry, thời gian phục hồi và cost per successful job.
9. Chỉ tăng tỷ lệ interruptible khi tiêu chí ổn định được đáp ứng.

## 16. Những sai lầm thường gặp

1. **Coi Spot như máy rẻ hơn nhưng giống on-demand:** bỏ qua khả năng bị thu hồi.
2. **Không lưu trạng thái bên ngoài instance:** mất dữ liệu hoặc tiến độ khi máy bị terminate.
3. **Chỉ xử lý interruption notice:** ứng dụng vẫn thất bại nếu máy bị dừng đột ngột.
4. **Retry không idempotent:** tạo bản ghi, giao dịch hoặc side effect trùng.
5. **Checkpoint không nguyên tử:** checkpoint mới bị ghi dở làm hỏng khả năng resume.
6. **Dùng một capacity pool duy nhất:** không thể cấp phát lại khi pool đó thiếu máy.
7. **Đặt toàn bộ hệ thống quan trọng trên Spot:** một đợt thu hồi có thể làm mất dịch vụ.
8. **Bỏ qua downstream:** thêm worker làm database hoặc storage quá tải.
9. **Chỉ so sánh giá theo giờ:** không tính compute chạy lại, checkpoint, startup và vận hành.
10. **Không kiểm thử nhiều instance bị thu hồi cùng lúc:** đánh giá thấp ảnh hưởng tương quan.
11. **Dùng license hoặc host identity không tương thích:** máy thay thế không thể khởi chạy workload.
12. **Không có fallback:** backlog tăng nhưng không có capacity ổn định để xử lý deadline quan trọng.

## 17. Checklist đánh giá trước khi dùng interruptible compute

- [ ] Workload có thể chia nhỏ, retry hoặc checkpoint.
- [ ] Dữ liệu bền vững được lưu ngoài instance.
- [ ] Task có ID ổn định và cơ chế chống xử lý trùng.
- [ ] Output chỉ được công bố sau khi ghi hoàn tất và xác minh.
- [ ] Worker mất được phát hiện qua lease/heartbeat/timeout.
- [ ] Có xử lý interruption notice nhưng không phụ thuộc vào notice.
- [ ] Có retry limit, backoff, jitter và dead-letter queue.
- [ ] Có capacity pool hoặc loại instance thay thế.
- [ ] Dependency và downstream chịu được số worker thay đổi.
- [ ] Có baseline capacity ổn định nếu workload yêu cầu SLO liên tục.
- [ ] Đã tính cost per successful job, bao gồm retry và checkpoint.
- [ ] Đã kiểm thử interruption đơn lẻ và đồng thời.
- [ ] Có log, metrics, cảnh báo và runbook phục hồi.
- [ ] Credential, secret và dữ liệu nhạy cảm không phụ thuộc vòng đời instance.
- [ ] Có tiêu chí canary, mở rộng và quay lại capacity ổn định.

## 18. Bài tập vận dụng

Một nhóm xử lý 500.000 ảnh mỗi đêm. Mỗi ảnh mất trung bình 8 giây để resize và nén. Nhóm đang chạy trên 20 VM on-demand. Có thể dùng Spot với giá giả định bằng 35% giá on-demand, nhưng worker có thể bị thu hồi trong lúc xử lý. Output được ghi vào object storage và kết quả task được lưu trong database.

1. Vì sao workload này có tiềm năng phù hợp với interruptible compute?
2. Hãy đề xuất cách chia task, lưu tiến độ và xác nhận hoàn tất.
3. Nếu worker bị thu hồi sau khi upload output nhưng trước khi cập nhật trạng thái task, làm thế nào tránh tạo kết quả trùng?
4. Nhóm nên theo dõi những chỉ số nào ngoài giá compute theo giờ?
5. Thành phần nào nên tiếp tục chạy trên capacity ổn định?
6. Cần thử nghiệm interruption nào trước khi chuyển phần lớn workload sang Spot?

Gợi ý: dùng một task ID ổn định cho mỗi ảnh, ghi output theo object key xác định và dùng conditional update/unique constraint để trạng thái hoàn tất chỉ được commit một lần. Worker chỉ acknowledge sau khi xác minh output. Theo dõi cost per successful image, retry rate, interruption rate, queue age, thời gian hoàn tất batch và chi phí lưu trữ. Queue, database điều phối và phần dịch vụ có deadline nghiêm ngặt nên có capacity ổn định; worker resize có thể dùng Spot sau khi kiểm thử retry và deduplication.

## Kết luận

Interruptible compute phù hợp nhất với workload có thể chia nhỏ, chạy lại hoặc khôi phục từ checkpoint, có dữ liệu bền vững bên ngoài instance và xử lý retry an toàn. Batch, CI, render, ETL và nhiều tác vụ offline thường là ứng viên tốt. Database primary, stateful service đơn lẻ và tác vụ tương tác có deadline nghiêm ngặt cần capacity ổn định hoặc kiến trúc HA chuyên biệt. Quyết định cuối cùng phải dựa trên SLO, khả năng phục hồi, nguồn cung capacity và chi phí trên một đơn vị công việc hoàn thành, sau khi đã kiểm thử interruption trong điều kiện gần thực tế.
