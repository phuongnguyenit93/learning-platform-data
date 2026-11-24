# Scale-in an toàn và bảo vệ máy đang xử lý tác vụ

Tự động co giãn (autoscaling) giúp nhóm máy tăng hoặc giảm số lượng instance theo nhu cầu. Scale-out thường tạo thêm năng lực phục vụ; scale-in lại loại bỏ năng lực đang tồn tại. Nếu một instance bị dừng trong khi vẫn nhận request, đang chạy job, giữ lease hoặc ghi dữ liệu, thao tác giảm số lượng máy có thể làm mất công việc, tạo xử lý trùng lặp hoặc gây gián đoạn dịch vụ.

**Scale-in an toàn** là quá trình đưa một instance ra khỏi nhóm phục vụ, ngừng giao việc mới, cho phép công việc đang chạy hoàn tất hoặc lưu checkpoint, giải phóng tài nguyên dùng chung, rồi mới dừng máy. Mục tiêu là giảm capacity mà vẫn giữ tính đúng đắn của dữ liệu, tính liên tục của dịch vụ và khả năng phục hồi khi có lỗi.

Bài học này thuộc chương **Nhóm máy và tự động co giãn** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong phạm vi đó, scale-in an toàn giúp nhóm máy tối ưu số instance mà không làm mất request, job hoặc trạng thái quan trọng.

## 1. Scale-in là gì và vì sao cần bảo vệ workload?

### 1.1. Scale-out và scale-in

- **Scale-out:** tăng số instance hoặc replica để xử lý thêm tải.
- **Scale-in:** giảm số instance hoặc replica khi tải giảm hoặc cần loại bỏ capacity dư thừa.
- **Desired capacity:** số instance mà bộ điều khiển autoscaling đang hướng tới.
- **Minimum capacity:** số instance tối thiểu cần duy trì.
- **Maximum capacity:** giới hạn trên của nhóm máy.
- **Scale-in candidate:** instance được chọn để loại khỏi nhóm.
- **Drain:** ngừng giao workload mới cho instance và chờ các hoạt động đang diễn ra kết thúc hoặc chuyển giao.
- **Termination:** dừng instance hoặc container sau khi quá trình drain đạt điều kiện.

Scale-in không đơn giản là tắt máy có CPU thấp nhất. Một máy CPU thấp vẫn có thể đang xử lý một giao dịch quan trọng, giữ kết nối dài, chạy batch job hoặc là thành viên cần thiết để duy trì quorum.

### 1.2. Điều gì có thể xảy ra nếu dừng máy quá sớm?

Một instance bị terminate ngay khi đang hoạt động có thể gây ra:

- Request đang xử lý bị reset hoặc timeout.
- Job đang chạy bị mất tiến độ và phải chạy lại từ đầu.
- Message bị xác nhận đã nhận trước khi kết quả được lưu bền vững.
- Một tác vụ được xử lý đồng thời bởi hai worker.
- Transaction hoặc file đang ghi bị dở dang.
- Kết nối database, cache hoặc hệ thống đối tác bị đóng đột ngột.
- Cluster mất quorum hoặc còn quá ít replica khỏe mạnh.
- Load balancer tiếp tục gửi traffic tới instance sắp dừng.
- Local disk hoặc dữ liệu tạm bị xóa trước khi đồng bộ.

Mức độ ảnh hưởng phụ thuộc workload. Với web server stateless, việc drain kết nối thường đủ để thay máy. Với queue worker, cần quản lý lease, acknowledgement và checkpoint. Với database hoặc hệ thống stateful, cần thêm quy trình replication, failover và bảo vệ quorum.

### 1.3. Các loại workload và chiến lược scale-in

| Loại workload | Rủi ro khi scale-in | Cách bảo vệ thường dùng |
|---|---|---|
| Web/API stateless | Request đang chạy và kết nối dài bị ngắt | Ngừng nhận request mới, deregister khỏi load balancer, chờ request hoàn tất |
| Queue worker | Job đang chạy bị mất hoặc xử lý trùng | Ngừng nhận message mới, hoàn tất/checkpoint job, ack sau khi commit |
| Batch/compute job | Mất tiến độ của job dài | Checkpoint, resume hoặc đợi job hoàn tất |
| Stateful service | Mất dữ liệu, replica hoặc quorum | Replication, leader handoff, failover và kiểm tra quorum |
| Stream processor | Mất offset hoặc xử lý sai thứ tự | Commit offset/checkpoint có kiểm soát, chuyển partition ownership |
| GPU worker | Mất trạng thái model, batch hoặc tác vụ dài | Drain batch, lưu checkpoint, giải phóng accelerator đúng cách |

Một nhóm máy có thể chạy nhiều loại workload. Khi đó cần phân loại instance theo vai trò hoặc cung cấp cơ chế drain riêng cho từng loại tác vụ.

## 2. Vòng đời của một instance khi scale-in

### 2.1. Các trạng thái cần có

Một quy trình an toàn nên phân biệt ít nhất các trạng thái:

1. **In service:** instance đang phục vụ và nhận workload mới.
2. **Scale-in selected:** bộ điều khiển chọn instance để giảm capacity.
3. **Protected/held:** instance được tạm giữ nếu đang có công việc không thể gián đoạn hoặc có điều kiện bảo vệ.
4. **Draining:** instance ngừng nhận workload mới, các hoạt động đang chạy được hoàn tất hoặc chuyển giao.
5. **Quiescent:** không còn request/job cần xử lý; tài nguyên và lease đã được giải phóng.
6. **Terminating:** hệ thống dừng tiến trình và instance.
7. **Terminated:** instance đã rời nhóm và tài nguyên đã được thu hồi.

Không phải nền tảng nào cũng biểu diễn đúng các trạng thái này bằng tên giống nhau. Đây là mô hình logic để thiết kế ứng dụng và automation.

~~~mermaid
stateDiagram-v2
    [*] --> InService
    InService --> Selected: Autoscaler chọn scale-in candidate
    Selected --> Protected: Có tác vụ không thể gián đoạn
    Protected --> InService: Hoàn tất hoặc hết điều kiện bảo vệ
    Selected --> Draining: Cho phép bắt đầu scale-in
    Draining --> Quiescent: Không còn việc đang chạy
    Draining --> InService: Hủy scale-in / rollback
    Quiescent --> Terminating: Dừng tiến trình và giải phóng máy
    Terminating --> Terminated
    Terminated --> [*]
~~~

### 2.2. Trình tự chuẩn

Một trình tự scale-in có kiểm soát thường gồm:

1. Bộ điều khiển xác định cần giảm desired capacity.
2. Chọn instance có thể loại bỏ theo chính sách.
3. Phát tín hiệu drain cho ứng dụng/agent và đánh dấu instance không nhận workload mới.
4. Ứng dụng dừng nhận request/job mới; load balancer hoặc service discovery bắt đầu loại instance khỏi tập đích.
5. Chờ thay đổi định tuyến được truyền tới các thành phần liên quan.
6. Chờ request/job đang chạy hoàn tất, checkpoint hoặc chuyển giao.
7. Commit trạng thái, xác nhận message và giải phóng lease/lock.
8. Đóng kết nối, flush telemetry và giải phóng tài nguyên.
9. Báo hiệu drain hoàn tất để nền tảng tiếp tục terminate.
10. Xác minh instance đã rời nhóm và capacity còn lại vẫn đáp ứng tải.

Thứ tự chính xác giữa deregistration, readiness và tín hiệu shutdown phụ thuộc load balancer, orchestrator và cách ứng dụng nhận traffic. Phải thiết kế để không có khoảng thời gian instance đã ngừng nhận việc nhưng vẫn bị hệ thống định tuyến request mới.

### 2.3. Thời hạn drain

Drain không thể kéo dài vô hạn. Cần đặt:

- **Grace period:** thời gian tối đa dành cho việc shutdown có trật tự.
- **Task deadline:** thời hạn tối đa của một request hoặc job.
- **Termination deadline:** thời điểm nền tảng sẽ buộc dừng instance.
- **Checkpoint interval:** khoảng cách giữa các lần lưu tiến độ.
- **Lease/visibility timeout:** thời gian một worker được giữ quyền xử lý message hoặc tài nguyên.

Nếu công việc dài hơn grace period, ứng dụng cần checkpoint/resume, requeue hoặc chuyển giao. Chờ vô hạn có thể khiến autoscaling không bao giờ giảm được capacity và làm tăng chi phí.

## 3. Xác định instance nào an toàn để loại bỏ

### 3.1. Không chọn chỉ dựa vào CPU

CPU thấp không đồng nghĩa máy rảnh. Một worker có thể đang chờ I/O, giữ transaction, xử lý một job dài hoặc đang giữ lock. Tương tự, CPU cao không có nghĩa máy không thể drain nếu nó đã ngừng nhận việc mới và workload hiện tại sắp hoàn tất.

Ngoài CPU và memory, cần xem:

- Số request đang hoạt động.
- Số job đang chạy và thời gian còn lại ước tính.
- Độ sâu queue và tốc độ message đến.
- Số kết nối đang mở.
- Trạng thái replication, partition hoặc shard.
- Vai trò leader/coordinator.
- Dữ liệu chưa flush hoặc checkpoint.
- Local storage còn dữ liệu cần giữ hay không.
- Trạng thái health và sự cố của instance.

### 3.2. Chính sách chọn scale-in candidate

Một số chính sách thường gặp:

- Loại instance mới nhất hoặc cũ nhất theo mục tiêu triển khai.
- Duy trì cân bằng giữa các zone.
- Ưu tiên instance có capacity dư và ít workload đang chạy.
- Ưu tiên instance đã được đánh dấu drain-ready.
- Giữ lại instance có vai trò đặc biệt hoặc dữ liệu chưa di chuyển.
- Chọn theo chi phí hoặc loại instance khi nhóm dùng nhiều cấu hình.

Chính sách termination mặc định của nhà cung cấp có thể tối ưu cho cân bằng zone hoặc vòng đời instance, nhưng không nhất thiết biết máy nào đang xử lý job dài. Muốn bảo vệ tác vụ, ứng dụng cần xuất trạng thái hoạt động để autoscaler hoặc automation sử dụng.

### 3.3. Tách trạng thái workload khỏi metric hạ tầng

Có thể công bố các metric như:

- active_requests
- active_jobs
- inflight_messages
- oldest_job_age
- drain_ready
- estimated_drain_seconds
- checkpoint_age
- active_leases

Các metric này giúp hệ thống biết instance nào có thể drain. Cần bảo đảm metric có độ trễ chấp nhận được và không biến thành một điểm lỗi duy nhất.

Nếu không thể đưa trạng thái ứng dụng vào quyết định autoscaler, hãy dùng lifecycle hook hoặc cơ chế bảo vệ ở tầng ứng dụng sau khi instance được chọn, rồi mới cho phép termination tiếp tục.

## 4. Drain an toàn cho web server và API

### 4.1. Ngừng nhận request mới

Khi bắt đầu drain:

- Đánh dấu instance không còn readiness hoặc không còn đủ điều kiện nhận traffic.
- Gỡ instance khỏi target group/service discovery.
- Ngừng accept kết nối mới tại listener nếu ứng dụng quản lý trực tiếp.
- Giữ các request đang xử lý cho đến khi hoàn tất hoặc hết deadline.
- Trả response phù hợp nếu client gửi request mới tới instance đang drain.

Readiness và deregistration không phải lúc nào cũng tức thời. Health check, cache, connection reuse và propagation giữa các node có thể tạo độ trễ. Cần đặt một khoảng chờ phù hợp và xác minh load balancer không còn phân phối request mới.

### 4.2. Kết nối keep-alive và kết nối dài

HTTP keep-alive, WebSocket, gRPC streaming hoặc TCP session có thể tồn tại lâu hơn một request thông thường. Nếu đóng listener ngay, kết nối đang mở có thể bị reset.

Ứng dụng cần quy định:

- Không nhận stream mới khi bắt đầu drain.
- Gửi tín hiệu đóng phù hợp nếu giao thức hỗ trợ.
- Cho client thời gian reconnect hoặc chuyển sang endpoint khác.
- Giới hạn thời gian tối đa cho connection drain.
- Xử lý request idempotent và retry an toàn.

Với WebSocket hoặc stream dài, không thể giả định load balancer sẽ tự di chuyển kết nối đang mở sang instance khác. Client và server cần có giao thức reconnect/resume hoặc chấp nhận kết thúc phiên có thông báo.

### 4.3. Thứ tự readiness và deregistration

Một trình tự có thể dùng là:

1. Ứng dụng chuyển trạng thái nội bộ sang draining.
2. Readiness endpoint trả về trạng thái không sẵn sàng cho request mới.
3. Load balancer ngừng chọn instance sau khi health state được cập nhật.
4. Ứng dụng tiếp tục hoàn tất request đang chạy.
5. Sau khi hết request hoặc đạt deadline, đóng listener và tiến trình.

Một số hệ thống cần deregister target trước rồi mới gửi SIGTERM; hệ thống khác dùng pre-stop hook để điều phối. Quan trọng là phối hợp thời gian health check, deregistration delay, shutdown timeout và grace period.

### 4.4. Ví dụ endpoint readiness và drain

Pseudocode minh họa:

~~~text
state = SERVING

on_start_drain():
    state = DRAINING
    readiness_endpoint = NOT_READY
    stop_accepting_new_requests()

    wait_until(
        active_requests == 0
        OR drain_deadline_reached
    )

    notify_long_lived_clients_to_reconnect()
    close_remaining_connections()
    flush_logs_and_metrics()
    exit_cleanly()
~~~

Đây là mô hình logic, không phải mã chạy trực tiếp. Ứng dụng thực tế phải đồng bộ trạng thái readiness với load balancer/orchestrator và bảo đảm các request bị từ chối trong thời gian drain không bị mất dữ liệu.

## 5. Drain an toàn cho queue worker

### 5.1. Vì sao queue worker cần quy trình riêng?

Worker thường nhận message, xử lý một tác vụ và xác nhận (acknowledge) với queue khi hoàn tất. Nếu instance bị dừng giữa lúc xử lý:

- Message có thể được giao lại sau visibility timeout hoặc lease expiry.
- Job có thể chạy đồng thời ở worker khác nếu lease hết hạn trong khi worker cũ vẫn chạy.
- Nếu ack trước khi kết quả được lưu bền vững, message mất nhưng công việc chưa hoàn tất.
- Nếu không ack và không có checkpoint, job phải chạy lại từ đầu.

Nhiều hệ thống queue cung cấp ngữ nghĩa at-least-once. Điều đó có nghĩa message có thể được giao nhiều lần; ứng dụng cần thiết kế idempotent để xử lý trùng lặp an toàn.

### 5.2. Trình tự shutdown của worker

Khi nhận lệnh drain:

1. Chuyển worker sang trạng thái không nhận job mới.
2. Dừng poll hoặc giảm số lần fetch message mới.
3. Giữ lease/visibility timeout của các job đang chạy nếu cần.
4. Cho các job hoàn tất trong giới hạn thời gian.
5. Lưu kết quả và checkpoint một cách bền vững.
6. Ack message sau khi commit thành công.
7. Với job chưa thể hoàn tất, checkpoint và release/requeue theo giao thức queue.
8. Giải phóng lock, lease và tài nguyên.
9. Báo drain-ready để instance được terminate.

Điểm quan trọng là không ack message chỉ vì worker nhận được tín hiệu shutdown. Ack phải theo sau việc hoàn tất hoặc lưu trạng thái có thể phục hồi.

### 5.3. Visibility timeout và lease

Trong queue dùng visibility timeout, sau khi message được nhận, message tạm thời không hiển thị cho worker khác trong khoảng thời gian cấu hình. Nếu xử lý kéo dài hơn khoảng đó mà không gia hạn, message có thể xuất hiện lại và được worker khác nhận.

Cần:

- Chọn visibility timeout phù hợp với thời gian xử lý dự kiến.
- Gia hạn visibility/lease khi job còn chạy.
- Đặt giới hạn tổng thời gian gia hạn.
- Bảo đảm worker cũ dừng hoặc mất quyền ghi khi lease hết hạn.
- Dùng idempotency key hoặc fencing token cho thao tác có tác động dữ liệu.

Lease biểu diễn quyền sở hữu có thời hạn trong cơ chế phối hợp, nhưng tự nó không dừng tiến trình của worker cũ. Nếu worker cũ tiếp tục chạy sau khi lease hết hạn, hệ thống cần fencing token hoặc kiểm tra ownership ở nơi ghi dữ liệu để ngăn tác động stale.

### 5.4. Checkpoint và requeue

Job dài nên có checkpoint định kỳ. Checkpoint cần lưu đủ trạng thái để worker khác có thể tiếp tục mà không lặp lại tác động đã commit.

Ví dụ job xử lý 1.000 file:

- Lưu danh sách file đã hoàn tất.
- Ghi kết quả mỗi batch vào storage bền vững.
- Lưu cursor hoặc offset tiếp theo.
- Chỉ ack message gốc sau khi tất cả batch hoàn tất và kết quả được commit.
- Nếu drain deadline đến, lưu checkpoint và để message được retry/requeue.

Không lưu checkpoint duy nhất trên local disk của instance sắp bị terminate, trừ khi dữ liệu đó được đồng bộ hoặc volume được giữ lại theo quy trình rõ ràng.

### 5.5. Ví dụ pseudocode worker

~~~text
on_drain_signal():
    accepting_new_jobs = false
    stop_polling_queue()

    for each active_job:
        while job_is_running(active_job):
            renew_visibility_lease(active_job)

            if job_can_finish_before_deadline(active_job):
                continue_processing(active_job)
            else:
                save_checkpoint_to_durable_store(active_job)
                stop_job_safely(active_job)
                release_or_allow_retry(active_job)

        if job_result_is_committed(active_job):
            acknowledge_message(active_job)

    close_queue_client()
    report_drain_complete()
~~~

Trong triển khai thật, cần xử lý race giữa shutdown signal, job completion, lease renewal và ack. Các thao tác lưu kết quả và ack nên có thứ tự rõ ràng, có thể retry và có cơ chế idempotency.

## 6. Tác vụ dài, batch và GPU workload

### 6.1. Xử lý job dài hơn thời gian drain

Nếu một job có thể chạy hàng giờ nhưng autoscaler chỉ dành vài phút cho drain, không thể dựa vào chờ hoàn tất. Có ba chiến lược chính:

- **Checkpoint/resume:** lưu tiến độ định kỳ và tiếp tục trên instance khác.
- **Task boundary:** chia job thành các đơn vị nhỏ, có thể giao lại độc lập.
- **Protected execution:** tạm thời không chọn instance đang chạy job không thể gián đoạn.

Có thể kết hợp cả ba. Ví dụ, job dài được chia thành batch 5 phút, mỗi batch ghi checkpoint; instance chỉ cần hoàn tất batch hiện tại rồi dừng.

### 6.2. GPU và accelerator

GPU workload có thể cần thời gian dài để hoàn thành inference batch, training step hoặc ghi checkpoint model. Trước khi terminate:

- Dừng nhận batch mới.
- Hoàn tất batch đang chạy hoặc lưu trạng thái có thể phục hồi.
- Flush output và checkpoint ra storage bền vững.
- Giải phóng context và tài nguyên accelerator.
- Kiểm tra driver/runtime không còn tiến trình giữ device.
- Cập nhật trạng thái job để scheduler có thể phân công lại.

Nếu framework chỉ lưu checkpoint ở một số ranh giới training step, cần drain tại ranh giới phù hợp. Dừng giữa lúc ghi checkpoint có thể làm hỏng artifact.

### 6.3. Hệ thống stream và partition

Với stream processor, mỗi worker có thể sở hữu một hoặc nhiều partition. Scale-in cần chuyển ownership có kiểm soát:

1. Ngừng nhận partition assignment mới.
2. Hoàn tất record đang xử lý.
3. Commit offset hoặc checkpoint đúng theo semantics của hệ thống.
4. Release partition ownership.
5. Worker khác tiếp nhận partition.
6. Theo dõi lag và duplicate processing.

Commit offset trước khi kết quả xử lý được ghi bền vững có thể làm mất dữ liệu logic. Commit sau khi ghi kết quả có thể tạo duplicate nếu worker crash giữa hai thao tác; vì vậy sink thường cần transaction hoặc idempotency.

## 7. Stateful service và bảo vệ quorum

### 7.1. Không terminate replica tùy tiện

Với database, cache cluster, distributed storage hoặc control plane, mỗi instance có thể giữ dữ liệu hoặc vai trò quan trọng. Scale-in cần kiểm tra:

- Node có phải leader/primary không.
- Số replica khỏe mạnh còn lại.
- Replication lag.
- Quorum và voting membership.
- Shard/partition placement.
- Dữ liệu chưa replicate hoặc chưa flush.
- Khả năng failover và phục hồi sau khi node rời nhóm.

Một cluster có ba voter có thể mất quorum nếu loại bỏ hai node gần nhau hoặc loại bỏ node khi một voter khác đang lỗi. Chỉ số lượng instance còn lại chưa đủ; cần xem thành viên nào thực sự tham gia quorum.

### 7.2. Leader handoff và replica removal

Quy trình scale-in stateful thường cần:

1. Chọn replica có thể loại bỏ theo chính sách dữ liệu.
2. Di chuyển shard hoặc replica nếu cần.
3. Xác minh replication đã bắt kịp.
4. Chuyển leader/primary sang node khác nếu node bị loại đang giữ vai trò đó.
5. Cập nhật membership và quorum theo quy trình sản phẩm.
6. Xác nhận node đã rời cluster an toàn.
7. Sau đó mới terminate compute instance.

Không dùng thao tác terminate VM như cách thay thế cho lệnh remove-node của database hoặc distributed system. Ứng dụng phải được thông báo và hoàn tất quy trình membership trước.

### 7.3. Local ephemeral storage

Nếu workload lưu dữ liệu cần thiết trên local SSD hoặc ephemeral disk, việc terminate có thể xóa dữ liệu. Cần xác định:

- Dữ liệu nào là cache có thể tạo lại.
- Dữ liệu nào là checkpoint hoặc kết quả chưa đồng bộ.
- Volume có tồn tại sau khi instance bị xóa không.
- Có cần detach và gắn lại volume hay không.
- Thứ tự flush, unmount và detach.
- Cách phục hồi nếu instance mất đột ngột.

Thiết kế tốt thường lưu trạng thái quan trọng ở storage bền vững và coi local disk là cache hoặc scratch space có thể tái tạo.

## 8. Lifecycle hook và cơ chế bảo vệ ở nền tảng cloud

### 8.1. Lifecycle hook

Nhiều nền tảng nhóm máy cung cấp lifecycle hook hoặc termination notification. Khi instance được chọn để terminate, nền tảng tạm dừng tiến trình ở một trạng thái chờ để automation hoặc agent thực hiện drain.

Một hook có thể kích hoạt:

- Gửi thông báo tới instance hoặc hệ thống điều phối.
- Đặt trạng thái ứng dụng thành draining.
- Gỡ target khỏi load balancer.
- Chờ job hoàn tất hoặc checkpoint.
- Ghi nhận kết quả và báo tiếp tục termination.

Lifecycle hook có thời hạn và có thể cần heartbeat/extension theo API của nhà cung cấp. Nếu hết thời gian, nền tảng có thể tiếp tục terminate theo cấu hình. Vì vậy, hook cần timeout, retry và fallback rõ ràng.

### 8.2. Instance scale-in protection

Một số dịch vụ autoscaling cho phép đánh dấu instance được bảo vệ khỏi scale-in. Tính năng này hữu ích khi máy đang chạy job không thể gián đoạn hoặc giữ vai trò đặc biệt.

Cần hiểu phạm vi bảo vệ:

- Có thể chỉ ngăn instance bị chọn trong một số hoạt động scale-in do giảm desired capacity.
- Không nhất thiết ngăn health replacement, lỗi hạ tầng, thao tác terminate thủ công hoặc sự kiện ngoài phạm vi tính năng.
- Cần có quy trình gỡ protection sau khi job hoàn tất.
- Nếu bảo vệ quá nhiều instance, nhóm có thể không scale-in được và chi phí tăng.

Scale-in protection là cơ chế hỗ trợ; ứng dụng vẫn phải có checkpoint, retry và xử lý khi instance bị mất đột ngột.

### 8.3. Termination policy

Termination policy quyết định instance nào được chọn khi nhóm cần giảm capacity. Có thể dựa trên tuổi instance, cân bằng zone, loại instance hoặc tiêu chí riêng do nền tảng hỗ trợ.

Nếu workload có thời gian xử lý khác nhau, nên kết hợp policy với trạng thái drain-ready. Không nên giả định termination policy mặc định biết số job đang chạy hoặc độ quan trọng của dữ liệu trên máy.

### 8.4. Thông báo terminate có thời hạn

Một số môi trường cung cấp thông báo trước khi instance bị thu hồi, ví dụ khi dùng capacity có thể bị thu hồi hoặc preemptible/spot. Thời gian cảnh báo có thể ngắn và phụ thuộc nhà cung cấp, loại sự kiện và region.

Ứng dụng cần xử lý thông báo theo hướng best-effort:

- Ngừng nhận việc mới ngay.
- Lưu checkpoint nhanh.
- Commit các kết quả đã hoàn tất.
- Để job chưa hoàn tất có thể được retry.
- Không phụ thuộc vào việc luôn nhận được thông báo trước khi máy mất.

Thông báo trước không phải bảo đảm máy luôn có đủ thời gian để hoàn tất mọi công việc.

## 9. Kubernetes và quá trình pod termination

### 9.1. Trình tự kết thúc pod

Khi pod bị xóa, Kubernetes bắt đầu quy trình termination và áp dụng thời gian grace. Lifecycle hook preStop, nếu có, chạy trong khoảng grace period; sau đó container nhận tín hiệu TERM. Khi hết grace period, tiến trình còn chạy có thể bị KILL.

Đồng thời, pod được đánh dấu terminating và các thành phần điều phối endpoint cập nhật trạng thái phục vụ. Propagation qua kube-proxy, dataplane, ingress hoặc load balancer có thể mất thời gian. Ứng dụng không nên giả định mọi nơi đã ngừng gửi traffic ngay khi nhận tín hiệu.

### 9.2. Các trường cấu hình liên quan

Một Pod spec có thể dùng:

~~~yaml
spec:
  terminationGracePeriodSeconds: 90
  containers:
    - name: api
      image: example/api:1.2.3
      lifecycle:
        preStop:
          exec:
            command: ["/app/bin/drain", "--timeout=60s"]
~~~

Ví dụ chỉ minh họa cấu trúc. Image phải thực sự có lệnh drain; thời gian hook và thời gian shutdown phải nằm trong grace period tổng. Grace period bắt đầu khi quá trình termination khởi động, nên preStop tiêu thụ một phần thời gian này.

Ứng dụng vẫn cần xử lý SIGTERM. preStop không thay thế logic graceful shutdown và không bảo đảm request đang chạy sẽ hoàn tất nếu tiến trình không quản lý chúng.

### 9.3. Readiness, preStop và SIGTERM

Một cách phối hợp phổ biến:

1. Khi bắt đầu termination, preStop gọi endpoint hoặc lệnh chuyển ứng dụng sang draining.
2. Readiness probe trả về không sẵn sàng để giảm traffic mới.
3. Ứng dụng chờ propagation và hoàn tất request đang hoạt động.
4. Container nhận SIGTERM.
5. Ứng dụng đóng listener, flush và thoát trước khi hết grace period.

Có thể thiết kế SIGTERM là điểm bắt đầu drain và preStop chỉ chờ một khoảng ngắn, nhưng cần tránh hai nơi cùng thực hiện logic không idempotent. Hành vi cụ thể phải được kiểm thử với runtime, probe và ingress thực tế.

### 9.4. PodDisruptionBudget (PDB)

PodDisruptionBudget giới hạn mức gián đoạn tự nguyện đối với một nhóm pod khi thao tác đi qua Eviction API, ví dụ trong nhiều quy trình drain node. PDB giúp bảo vệ số pod sẵn sàng tối thiểu trong một số loại disruption.

PDB không thay thế graceful shutdown và không phải lá chắn cho mọi cách xóa pod. Các thao tác delete trực tiếp, force delete hoặc một số đường scale/rollout có thể không chịu cùng cơ chế eviction. Cần hiểu controller và thao tác đang sử dụng.

### 9.5. Deployment, StatefulSet và worker

- **Deployment:** phù hợp workload stateless; cần readiness, rolling update và shutdown logic.
- **StatefulSet:** cung cấp identity và thứ tự ổn định hơn; việc scale down vẫn cần xử lý dữ liệu, membership và storage.
- **Job/CronJob:** cần đảm bảo job có thể retry hoặc checkpoint; không giả định pod luôn chạy đến hết.
- **Queue worker:** cần dừng poll, hoàn tất/checkpoint job và ack đúng thứ tự.
- **DaemonSet:** thường gắn với node lifecycle; cần kế hoạch drain node và agent cleanup.

Kubernetes controller có hành vi khác nhau. Không nên dùng một cấu hình termination chung cho mọi loại workload.

## 10. Autoscaling policy để giảm rủi ro scale-in

### 10.1. Scale-in stabilization

Metric tải có thể giảm nhanh trong thời gian ngắn rồi tăng lại. Nếu scale-in phản ứng ngay, nhóm máy có thể dao động liên tục (flapping), tạo nhiều lần drain và cold start.

Có thể dùng:

- Scale-in stabilization window.
- Cooldown hoặc thời gian chờ sau scale-out.
- Ngưỡng scale-in thấp hơn ngưỡng scale-out (hysteresis).
- Minimum capacity để giữ buffer.
- Giới hạn số instance giảm trong mỗi chu kỳ.
- Lịch scale theo giờ cho workload có mẫu tải rõ ràng.

Cần phân biệt stabilization của autoscaler với drain timeout. Stabilization quyết định khi nào bắt đầu giảm capacity; drain timeout quyết định một instance được phép mất bao lâu để kết thúc công việc.

### 10.2. Scale-in theo metric workload

CPU hoặc network utilization chỉ phản ánh một phần tình trạng. Với queue worker, các metric phù hợp hơn có thể là:

- Queue depth trên mỗi worker.
- Số job đang chạy.
- Tuổi của message cũ nhất.
- Tốc độ message đến và hoàn tất.
- Thời gian xử lý trung vị và percentile cao.
- Số worker đang drain.
- Số instance thực sự có thể loại bỏ.

Không scale-in nếu tải còn backlog lớn dù CPU đang thấp do worker bị chờ I/O hoặc dependency. Ngược lại, khi queue rỗng và không có job đang chạy, có thể giảm nhanh hơn trong giới hạn minimum capacity.

### 10.3. Giới hạn tốc độ scale-in

Giảm một phần capacity mỗi chu kỳ giúp:

- Duy trì đủ replica trong khi node drain.
- Hạn chế số job phải checkpoint cùng lúc.
- Tránh dồn tải lên các worker còn lại.
- Giảm rủi ro mất quorum hoặc cạn capacity.
- Có thời gian quan sát lỗi sau từng batch.

Với workload stateful, giới hạn scale-in nên dựa trên replication, quorum và tốc độ di chuyển dữ liệu chứ không chỉ phần trăm instance.

### 10.4. Tính capacity sau khi drain

Giả sử nhóm có 10 worker, mỗi worker xử lý an toàn 20 job đồng thời. Nếu scale-in 4 worker trong khi 120 job vẫn đang chạy, 6 worker còn lại có thể không đủ capacity nếu tất cả job được chuyển tiếp hoặc retry cùng lúc.

Cần tính:

- Năng lực xử lý của instance còn lại.
- Tải đang chạy và backlog.
- Thời gian drain.
- Burst traffic trong thời gian thay máy.
- Tỷ lệ lỗi hoặc retry có thể phát sinh.
- Headroom cần duy trì cho sự cố một zone hoặc một node.

Không nên đặt desired capacity thấp hơn mức cần thiết chỉ vì metric hiện tại đang thấp trong một khoảng thời gian ngắn.

## 11. Xử lý lỗi và race condition trong scale-in

### 11.1. Instance bị terminate trước khi drain xong

Có thể xảy ra khi lifecycle hook hết hạn, host crash, autoscaler force terminate hoặc cloud infrastructure gặp sự cố. Ứng dụng cần giả định graceful shutdown có thể không xảy ra.

Biện pháp:

- Job phải có thể retry hoặc resume.
- Kết quả cần được ghi bền vững trước ack.
- Dùng idempotency key cho side effect.
- Lease phải hết hạn để worker khác nhận lại job.
- Checkpoint phải lưu ngoài instance.
- Có reconciliation để tìm job ở trạng thái không rõ.

### 11.2. Worker cũ và worker mới cùng xử lý

Nếu lease hết hạn nhưng worker cũ vẫn chạy, worker mới có thể nhận cùng job. Cần:

- Gia hạn lease khi worker còn sở hữu job.
- Dùng fencing token hoặc version tăng dần.
- Kiểm tra token ở nơi ghi dữ liệu.
- Dùng idempotent write hoặc transaction.
- Không cho worker stale tiếp tục commit chỉ vì tiến trình vẫn sống.

### 11.3. Shutdown lặp lại hoặc tín hiệu đến nhiều lần

Automation có thể gửi drain signal nhiều lần, hoặc ứng dụng nhận cả preStop và SIGTERM. Handler shutdown cần idempotent:

- Chuyển trạng thái sang draining một lần.
- Không nhận thêm việc sau lần chuyển trạng thái đầu.
- Không ack/release cùng một message nhiều lần ngoài semantics cho phép.
- Không đóng client trước khi job đang dùng nó kết thúc.
- Có timeout và đường thoát rõ ràng.

### 11.4. Drain không bao giờ hoàn tất

Nguyên nhân có thể là request treo, job không có deadline, connection không đóng, lease renewal bị lỗi hoặc metric active-work không giảm.

Cần đặt deadline, ghi log tác vụ còn lại, checkpoint/requeue nếu có thể và quyết định rõ khi nào cho phép force terminate. Một instance bị treo drain không nên giữ capacity vô thời hạn mà không có cảnh báo và owner.

### 11.5. Không có tín hiệu shutdown

Nếu host bị crash hoặc bị thu hồi đột ngột, không có cơ hội drain. Vì vậy, mọi workload quan trọng phải được thiết kế để chịu được mất instance bất ngờ; graceful shutdown chỉ giảm xác suất mất tiến độ chứ không thay thế fault tolerance.

## 12. Ví dụ thiết kế: nhóm queue worker

Một nhóm worker xử lý message từ queue. Mỗi job có thời gian xử lý từ vài giây đến vài phút; kết quả được ghi vào database và object storage.

Thiết kế:

1. Autoscaler dựa trên queue depth và tuổi message để tăng/giảm worker.
2. Worker có concurrency giới hạn và connection pool tới database.
3. Khi được chọn scale-in, instance nhận lifecycle event.
4. Agent chuyển worker sang draining và dừng poll message mới.
5. Job đang chạy tiếp tục gia hạn visibility lease.
6. Job gần hoàn tất được phép kết thúc trong drain deadline.
7. Job dài hơn deadline ghi checkpoint vào object storage và được phép retry.
8. Worker commit kết quả trước, ack message sau.
9. Worker release lease, đóng database/queue client và báo drain-ready.
10. Lifecycle hook hoàn tất, autoscaling group terminate instance.
11. Metric queue depth, oldest message age, active jobs và failed jobs được theo dõi sau scale-in.

~~~mermaid
flowchart TD
    A["Nhận scale-in event"] --> B["Đánh dấu worker draining"]
    B --> C["Dừng poll / nhận job mới"]
    C --> D{"Còn job đang chạy?"}
    D -->|Không| H["Đóng client, giải phóng lease"]
    D -->|Có| E{"Job hoàn tất trước deadline?"}
    E -->|Có| F["Commit kết quả rồi ACK"]
    F --> D
    E -->|Không| G["Lưu checkpoint và cho phép retry"]
    G --> H
    H --> I["Báo drain-ready"]
    I --> J["Terminate instance"]
~~~

Trong thiết kế này, ACK luôn theo sau commit kết quả. Nếu commit thành công nhưng ACK thất bại, message có thể được giao lại; thao tác xử lý phải idempotent để không tạo side effect trùng.

## 13. Kiểm thử quy trình scale-in

### 13.1. Kiểm thử chức năng

Trong staging, tạo các tình huống:

- Instance không có request/job đang chạy.
- Instance đang xử lý request ngắn.
- Instance đang giữ WebSocket hoặc gRPC stream.
- Worker đang chạy job ngắn và job dài.
- Visibility lease sắp hết hạn.
- Job đang checkpoint.
- Instance đang giữ vai trò leader hoặc replica.
- Lifecycle hook timeout.
- Instance bị kill trước khi drain hoàn tất.

Xác minh kết quả dữ liệu, số lần xử lý, trạng thái queue, request error và thời gian drain.

### 13.2. Kiểm thử tải và scale-in đồng thời

Tạo tải tăng giảm theo chu kỳ, sau đó quan sát:

- Desired capacity và actual capacity.
- Số instance đang drain.
- Active requests/jobs trên từng instance.
- Queue depth và oldest message age.
- Request error rate và latency.
- Thời gian từ scale-in event đến termination.
- Job retry, duplicate và failure.
- Capacity còn lại sau mỗi batch.

Kiểm tra cả lúc traffic tăng trở lại trong khi một số instance đang drain. Autoscaler cần có khả năng scale-out lại mà không bị trạng thái drain cũ làm chậm hoặc làm mất capacity cần thiết.

### 13.3. Kiểm thử fault injection

Có thể chủ động mô phỏng:

- Kill process ngay sau khi nhận message.
- Ngắt mạng khi đang ghi kết quả.
- Làm queue visibility timeout hết hạn.
- Cho database chậm hoặc từ chối connection.
- Làm lifecycle callback không phản hồi.
- Gửi SIGTERM hai lần.
- Kéo dài job vượt quá grace period.

Mục tiêu là chứng minh hệ thống phục hồi đúng: không mất job đã được xác nhận, không ghi side effect trùng ngoài kiểm soát và có thể tiếp tục sau khi instance biến mất.

### 13.4. Tiêu chí hoàn tất

Một đợt scale-in chỉ được xem là thành công khi:

- Instance đã ngừng nhận workload mới.
- Request/job đang chạy đã hoàn tất hoặc được lưu trạng thái có thể phục hồi.
- Message chỉ được ACK sau commit phù hợp.
- Lease/lock và partition ownership được giải phóng đúng cách.
- Không vi phạm quorum hoặc replica minimum.
- Instance rời load balancer/service discovery.
- Capacity còn lại đáp ứng tải và SLO.
- Không có job thất lạc hoặc lỗi tăng bất thường sau scale-in.

## 14. Metric và cảnh báo cần theo dõi

| Metric | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| Active requests | Request đang xử lý trên instance | Không giảm trong thời gian drain |
| In-flight jobs | Job đã nhận nhưng chưa hoàn tất | Còn job khi gần hết grace period |
| Drain duration | Thời gian từ drain start tới drain-ready | Vượt percentile hoặc deadline |
| Drain timeout count | Số lần drain hết thời gian | Tăng đột biến |
| Requeued/retried jobs | Job được giao lại | Tăng bất thường sau scale-in |
| Duplicate processing | Job có dấu hiệu xử lý trùng | Có side effect trùng |
| Queue oldest age | Tuổi message lâu nhất | Tăng sau khi giảm worker |
| Lease expiry | Số lease hết hạn khi job còn chạy | Tăng hoặc có worker stale |
| Target deregistration time | Thời gian gỡ instance khỏi load balancer | Vượt thời gian dự kiến |
| Remaining capacity | Capacity sau khi scale-in | Thấp hơn headroom yêu cầu |
| Scale-in protection count | Số instance đang được bảo vệ | Quá cao hoặc không giảm |
| Quorum/replica health | Trạng thái cluster stateful | Replica dưới ngưỡng hoặc quorum suy giảm |

Metric nên phân biệt theo nhóm workload, zone và phiên bản ứng dụng. Tránh chỉ xem tổng số job của toàn fleet vì một instance có thể còn job dài trong khi tổng số job đã thấp.

## 15. Những sai lầm thường gặp

**Terminate ngay khi desired capacity giảm.** Desired capacity là mục tiêu của nhóm, không chứng minh instance đã sẵn sàng dừng. Cần drain và xác minh.

**Chỉ dùng CPU để chọn instance.** CPU thấp không có nghĩa không có tác vụ quan trọng. Cần xem active work, lease và trạng thái ứng dụng.

**Gỡ instance khỏi load balancer nhưng không dừng queue polling.** Worker vẫn có thể nhận job mới từ queue dù không còn nhận traffic HTTP. Mỗi nguồn workload cần cơ chế drain riêng.

**ACK message trước khi lưu kết quả.** Nếu máy bị dừng sau ACK, message không được giao lại nhưng kết quả có thể chưa tồn tại. Commit trước, ACK sau.

**Chờ mọi job hoàn tất vô thời hạn.** Một job treo có thể ngăn scale-in mãi mãi. Cần deadline, checkpoint, requeue và cảnh báo.

**Chỉ tăng termination grace period.** Thời gian dài hơn không sửa được job không thể phục hồi hoặc lease sai. Phải thiết kế checkpoint và retry.

**Coi scale-in protection là bảo đảm tuyệt đối.** Tính năng bảo vệ có phạm vi giới hạn; host vẫn có thể mất do lỗi hoặc thao tác ngoài cơ chế đó.

**Dùng PDB như cơ chế duy nhất bảo vệ pod.** PDB chỉ điều phối một số voluntary eviction; không thay thế ứng dụng graceful shutdown hoặc bảo vệ trước mọi cách xóa pod.

**Không tính đến kết nối dài.** WebSocket, gRPC stream và TCP session cần thông báo đóng, reconnect hoặc resume.

**Không kiểm thử trường hợp mất máy đột ngột.** Graceful shutdown có thể không được gọi. Workload phải chịu được crash và retry.

**Scale-in quá nhiều instance cùng lúc.** Điều này có thể làm cạn capacity còn lại, tạo retry storm hoặc làm cluster mất quorum. Giới hạn batch và theo dõi headroom.

## 16. Checklist triển khai scale-in an toàn

### Thiết kế workload

- [ ] Phân loại workload stateless, queue, batch, stream hay stateful.
- [ ] Xác định dữ liệu nào phải lưu bền vững trước khi dừng.
- [ ] Thiết kế job có thể retry, resume hoặc checkpoint.
- [ ] Dùng idempotency key/fencing token khi có side effect hoặc lease.
- [ ] Xác định deadline và thời gian xử lý tối đa.

### Drain và shutdown

- [ ] Có trạng thái serving/draining rõ ràng.
- [ ] Dừng nhận request/job mới khi bắt đầu drain.
- [ ] Gỡ khỏi load balancer/service discovery đúng trình tự.
- [ ] Chờ request đang chạy hoặc thông báo client reconnect.
- [ ] Gia hạn lease/visibility timeout khi job còn chạy.
- [ ] Commit kết quả trước khi ACK message.
- [ ] Checkpoint/requeue job không thể hoàn tất trong deadline.
- [ ] Đóng kết nối và giải phóng lock/lease.
- [ ] Có timeout và fallback khi drain không hoàn tất.

### Autoscaling và nền tảng

- [ ] Chọn scale-in candidate dựa trên trạng thái workload.
- [ ] Cấu hình lifecycle hook/termination notification nếu nền tảng hỗ trợ.
- [ ] Hiểu giới hạn của instance scale-in protection.
- [ ] Đặt scale-in stabilization và giới hạn số máy mỗi batch.
- [ ] Giữ minimum capacity và headroom phù hợp.
- [ ] Bảo vệ quorum, replica và partition ownership.
- [ ] Với Kubernetes, cấu hình readiness, SIGTERM, preStop và grace period.
- [ ] Hiểu PDB áp dụng cho loại thao tác eviction nào.

### Kiểm thử và vận hành

- [ ] Test request ngắn, request dài và kết nối streaming.
- [ ] Test job ngắn, job dài, lease expiry và checkpoint.
- [ ] Test lifecycle hook timeout và mất instance đột ngột.
- [ ] Theo dõi drain duration, active jobs, retries và duplicate processing.
- [ ] Xác minh capacity sau scale-in đáp ứng SLO.
- [ ] Có cảnh báo khi instance bị bảo vệ quá lâu hoặc drain timeout tăng.
- [ ] Ghi nhận kết quả và cập nhật runbook sau mỗi sự cố.

## 17. Ghi nhớ

- Scale-in phải loại bỏ capacity sau khi workload đã ngừng nhận việc mới và xử lý an toàn công việc đang chạy.
- CPU thấp không chứng minh instance rảnh; cần theo dõi request, job, lease, checkpoint và vai trò cluster.
- Web/API cần readiness, deregistration, connection draining và xử lý kết nối dài.
- Queue worker cần dừng poll, giữ lease hợp lý, commit kết quả rồi mới ACK.
- Job dài cần checkpoint/resume, chia nhỏ hoặc được bảo vệ tạm thời khỏi scale-in.
- Stateful service cần replication, leader handoff và xác minh quorum trước khi loại node.
- Lifecycle hook và scale-in protection hỗ trợ điều phối nhưng không thay thế fault tolerance.
- Kubernetes cần phối hợp readiness, preStop, SIGTERM, termination grace period và PDB theo đúng phạm vi.
- Autoscaler nên dùng stabilization, giới hạn batch và headroom để tránh scale-in quá nhanh.
- Luôn kiểm thử cả graceful shutdown lẫn tình huống instance mất đột ngột.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Scale-in | Giảm số instance hoặc replica trong nhóm compute. |
| Scale-out | Tăng số instance hoặc replica để đáp ứng tải. |
| Desired capacity | Số lượng instance mà bộ điều khiển autoscaling hướng tới. |
| Drain | Ngừng giao workload mới và hoàn tất hoặc chuyển giao công việc đang chạy. |
| Graceful shutdown | Dừng tiến trình theo trình tự để đóng kết nối và lưu trạng thái an toàn. |
| Lifecycle hook | Cơ chế tạm dừng một giai đoạn vòng đời instance để automation thực hiện hành động. |
| Scale-in protection | Cơ chế bảo vệ instance khỏi một số hoạt động scale-in tự động. |
| Termination policy | Quy tắc chọn instance sẽ bị loại khỏi nhóm. |
| Connection draining | Ngừng gửi kết nối mới tới target và chờ kết nối hiện tại kết thúc. |
| In-flight request/job | Request hoặc job đã bắt đầu nhưng chưa hoàn tất. |
| Checkpoint | Trạng thái tiến độ được lưu để tiếp tục công việc sau khi worker thay đổi. |
| Idempotency | Tính chất thực hiện lặp lại một thao tác mà không tạo thêm tác động ngoài dự kiến. |
| Acknowledgement (ACK) | Xác nhận message đã được xử lý theo semantics của hệ thống queue. |
| Visibility timeout | Khoảng thời gian message đã nhận tạm thời không hiển thị cho worker khác. |
| Lease | Quyền sở hữu tài nguyên hoặc công việc có thời hạn. |
| Fencing token | Token có thứ tự/version dùng để ngăn chủ sở hữu cũ ghi dữ liệu sau khi lease đã chuyển. |
| Quorum | Số thành viên cần thiết để cluster đạt đồng thuận hoặc duy trì hoạt động theo giao thức. |
| PodDisruptionBudget | Chính sách Kubernetes giới hạn một số voluntary disruption đối với nhóm pod. |
| terminationGracePeriodSeconds | Thời gian Kubernetes dành cho quá trình kết thúc pod trước khi buộc dừng container. |
| preStop | Lifecycle hook của container được thực hiện trước khi gửi tín hiệu dừng. |
| SIGTERM | Tín hiệu yêu cầu tiến trình kết thúc có trật tự. |
| Retry storm | Hiện tượng nhiều client đồng loạt retry làm tăng tải khi dependency đang lỗi. |
| Scale-in stabilization | Khoảng thời gian làm dịu trước khi autoscaler thực hiện giảm capacity. |
