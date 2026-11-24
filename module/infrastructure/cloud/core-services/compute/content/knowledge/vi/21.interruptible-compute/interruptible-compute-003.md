# Xử lý tín hiệu gián đoạn và thời gian dừng có giới hạn

Compute có thể bị thu hồi khi nhà cung cấp cần lấy lại năng lực, khi nhóm vận hành scale-in, khi một node được bảo trì hoặc khi orchestrator thay thế workload. Với Spot/preemptible VM và một số loại compute có thể gián đoạn, ứng dụng đôi khi nhận được thông báo trước khi tài nguyên bị dừng. Khoảng thời gian này thường ngắn và phụ thuộc nhà cung cấp, loại tài nguyên cùng nguyên nhân thu hồi.

Ứng dụng cần biến thông báo đó thành một quy trình có deadline: ngừng nhận công việc mới, bảo toàn tiến độ quan trọng, hoàn tất những thao tác có thể kết thúc an toàn, giải phóng lease hoặc lock và thoát trước khi nền tảng kết thúc instance. Nếu không có đủ thời gian, workload phải dừng ở một ranh giới nhất quán để instance khác có thể tiếp tục.

Bài học thuộc module **CLOUD_CORE_SERVICES_COMPUTE**, chương **Compute có thể bị thu hồi**. Nội dung tập trung vào cách nhận và xử lý tín hiệu gián đoạn, quản lý thời gian dừng có giới hạn, phối hợp với queue/orchestrator/OS, bảo toàn dữ liệu và kiểm thử tình huống thu hồi.

## 1. Vì sao cần xử lý interruption notice?

Với compute có thể bị thu hồi, việc instance tồn tại đến hết một phiên làm việc không được bảo đảm. Nhà cung cấp có thể cần thu hồi tài nguyên để đáp ứng nhu cầu khác hoặc thực hiện hoạt động hạ tầng. Một workload chạy trên máy đó có thể bị dừng trong khi đang xử lý request, message hoặc batch job.

Nếu ứng dụng không chuẩn bị:

- Job đang chạy có thể mất toàn bộ tiến độ.
- Message đã nhận nhưng chưa hoàn tất có thể bị kẹt hoặc bị xử lý lặp.
- Transaction có thể ở trạng thái chưa rõ kết quả đối với client.
- Buffer chưa flush có thể làm mất dữ liệu.
- Instance mới có thể khởi động nhưng không biết công việc cũ đã hoàn thành đến đâu.
- Shutdown kéo dài có thể vượt deadline và bị kết thúc cưỡng bức.

Interruption notice cho ứng dụng cơ hội bảo toàn tiến độ. Tuy nhiên, notice không phải cam kết rằng ứng dụng luôn có đủ thời gian hoặc luôn nhận được sự kiện. Thiết kế phải tận dụng notice khi có nhưng vẫn phục hồi được sau khi mất máy đột ngột.

### 1.1. Các nguồn gián đoạn thường gặp

| Nguồn | Ví dụ | Đặc điểm |
|---|---|---|
| Capacity reclaim | Spot/preemptible VM bị thu hồi | Có thể có notice trước, nhưng thời gian và cách gửi khác nhau |
| Scale-in | Autoscaling giảm số instance | Có thể có lifecycle hook hoặc thời gian drain |
| Rolling update | Orchestrator thay thế instance/Pod | Thường có quy trình termination và grace period |
| Scheduled maintenance | Host hoặc nền tảng cần bảo trì | Có thể có lịch/sự kiện, tùy dịch vụ |
| Operator action | Người vận hành dừng hoặc xóa máy | Có thể chủ động phối hợp nhưng vẫn cần deadline |
| Host failure | Máy vật lý hoặc tiến trình lỗi đột ngột | Có thể không có notice hữu ích |

Không nên coi mọi trường hợp dừng là Spot eviction. Mỗi nguồn có thể có mức độ báo trước, độ tin cậy và cơ chế xác nhận khác nhau.

### 1.2. Notice, signal và termination

Ba sự kiện cần phân biệt:

- **Interruption notice:** thông báo từ cloud/provider rằng tài nguyên có thể sắp bị thu hồi hoặc thay đổi trạng thái.
- **Shutdown signal:** tín hiệu gửi tới tiến trình hoặc service, chẳng hạn SIGTERM trên Linux hoặc service stop control trên Windows.
- **Forced termination:** nền tảng kết thúc tiến trình/VM khi deadline hết hoặc khi xảy ra lỗi đột ngột.

Notice thường là cơ hội để bắt đầu chuẩn bị sớm. Signal yêu cầu tiến trình chuyển sang quy trình dừng. Forced termination có thể không cho ứng dụng cơ hội cleanup.

## 2. Tìm hiểu đường đi của tín hiệu

Một tín hiệu gián đoạn có thể được phát hiện ở nhiều lớp:

1. Cloud provider tạo event hoặc interruption notice.
2. Agent, metadata endpoint, event bus hoặc API của provider chuyển thông tin tới workload/control plane.
3. Thành phần quản lý workload yêu cầu instance ngừng nhận công việc mới.
4. Orchestrator hoặc OS gửi tín hiệu dừng tới tiến trình.
5. Ứng dụng chạy quy trình shutdown có deadline.
6. Nền tảng kết thúc instance khi ứng dụng đã thoát hoặc khi thời gian cho phép hết.

~~~mermaid
sequenceDiagram
    participant C as Cloud Provider
    participant E as Event / Metadata / Agent
    participant O as Orchestrator / Lifecycle Manager
    participant A as Application
    participant Q as Queue / Load Balancer
    participant D as Durable Storage
    C->>E: Interruption notice
    E->>O: Resource sắp bị thu hồi + deadline
    O->>A: ShutdownRequested
    A->>A: Chuyển sang quiescing
    A->>Q: Ngừng nhận request / message mới
    Q-->>A: Drain hoặc trả lease theo giao thức
    A->>D: Lưu checkpoint / commit kết quả
    D-->>A: Xác nhận ghi bền vững
    A->>A: Đóng kết nối và thoát
    A-->>O: Shutdown complete
    O-->>C: Instance sẵn sàng dừng
~~~

Sơ đồ là luồng logic tổng quát. Trên một nền tảng cụ thể, provider có thể gửi notice trực tiếp qua metadata hoặc event service; orchestrator có thể gửi SIGTERM; một số dịch vụ không cho phép workload xác nhận hoàn tất interruption. Hãy triển khai theo cơ chế được tài liệu chính thức của nền tảng hỗ trợ.

### 2.1. Các kênh nhận thông báo

Tùy môi trường, ứng dụng hoặc agent có thể nhận thông tin qua:

- Instance metadata hoặc endpoint sự kiện của VM.
- Cloud event service hoặc event bus.
- Notification queue/topic.
- API lifecycle của autoscaling service.
- Kubernetes node/pod event và termination lifecycle.
- SIGTERM/SIGINT hoặc Windows Service Control.
- Agent quản trị của nhà cung cấp.

Không nên giả định rằng tất cả cloud đều dùng cùng một metadata URL, cùng định dạng event hoặc cùng thời gian báo trước. Đặt phần tích hợp provider vào một adapter riêng để phần xử lý nghiệp vụ không phụ thuộc API cụ thể.

### 2.2. Polling và event-driven

**Polling** là cách workload hoặc agent kiểm tra định kỳ xem có notice mới không. Ưu điểm là dễ triển khai khi provider chỉ cung cấp endpoint truy vấn; nhược điểm là có độ trễ phát hiện và có thể tạo request liên tục.

**Event-driven** nhận thông báo khi provider phát sự kiện. Cách này giảm polling và có thể phát hiện sớm hơn, nhưng cần xử lý event trùng, event đến trễ, mất kết nối tới event bus và thứ tự sự kiện không bảo đảm.

Có thể kết hợp cả hai: nhận event làm tín hiệu chính, polling làm cơ chế đối soát hoặc dự phòng nếu kiến trúc provider hỗ trợ.

## 3. Chuẩn hóa tín hiệu thành một hợp đồng nội bộ

Ứng dụng không nên rải logic riêng cho từng loại interruption trong mọi module. Hãy chuẩn hóa các nguồn thành một sự kiện nội bộ, ví dụ:

~~~json
{
  "type": "ShutdownRequested",
  "resource_id": "worker-instance-42",
  "reason": "capacity-reclaim",
  "source": "cloud-event",
  "event_id": "evt-7f21",
  "observed_at": "2026-11-22T10:15:00Z",
  "deadline_at": "2026-11-22T10:16:30Z"
}
~~~

Các trường có ý nghĩa:

| Trường | Mục đích |
|---|---|
| type | Loại sự kiện chuẩn hóa |
| resource_id | Instance, VM, task hoặc Pod bị ảnh hưởng |
| reason | Spot reclaim, scale-in, maintenance, deployment hoặc operator |
| source | Metadata, event bus, signal, orchestrator hoặc admin |
| event_id | Nhận diện sự kiện để chống xử lý trùng |
| observed_at | Thời điểm ứng dụng nhận biết sự kiện |
| deadline_at | Thời điểm muộn nhất cần hoàn tất theo thông tin nguồn |

Đây là schema minh họa; không phải payload chuẩn của một cloud provider. Adapter phải chuyển payload thực tế sang schema nội bộ và giữ lại mã sự kiện/metadata cần cho audit.

### 3.1. Deadline phải có nguồn và độ tin cậy

Nếu provider cung cấp deadline tuyệt đối, hãy lưu nó cùng nguồn phát và thời điểm nhận. Nếu chỉ có khoảng thời gian còn lại, chuyển thành deadline dựa trên đồng hồ monotonic của tiến trình để tránh sai lệch do đồng hồ hệ thống bị chỉnh.

Không nên tự tạo một deadline dài hơn thời gian provider cấp. Nếu không biết deadline, ứng dụng nên dùng một shutdown budget bảo thủ theo chính sách của workload và chuẩn bị dừng ngay.

### 3.2. Xử lý event trùng và event đến trễ

Một event có thể được gửi nhiều lần do retry của event bus hoặc do polling và event-driven cùng phát hiện. Handler phải idempotent:

- Cùng event_id chỉ kích hoạt một lần chuyển trạng thái.
- Sự kiện đến sau khi đã bắt đầu shutdown không khởi động quy trình lần nữa.
- Deadline mới ngắn hơn phải được ưu tiên.
- Event cũ không được kéo dài deadline đã có.
- Ghi nhận nguồn và thời điểm để điều tra.

Nếu nhiều tín hiệu khác nhau cùng yêu cầu dừng, hãy lấy deadline nghiêm ngặt nhất còn hiệu lực.

## 4. Quản lý shutdown deadline

Thời gian báo trước có thể ngắn. Ứng dụng cần lập ngân sách thay vì chờ job hoàn tất vô hạn.

Gọi:

- T_d: thời điểm deadline phải thoát.
- T_n: thời gian ngừng nhận công việc mới và drain.
- T_j: thời gian hoàn tất job đang chạy nếu có thể.
- T_p: thời gian checkpoint hoặc commit dữ liệu.
- T_c: thời gian đóng connection và tài nguyên.
- T_s: safety margin dành cho độ trễ, scheduling và sai số.

Điều kiện ngân sách:

~~~text
T_n + T_j + T_p + T_c + T_s <= T_remaining
~~~

Trong đó T_remaining là thời gian từ lúc nhận notice tới deadline. Safety margin không nên bị dùng hết cho công việc nghiệp vụ; nó dành cho những bước cuối có thể mất thời gian không dự đoán được.

### 4.1. Ưu tiên theo thời gian còn lại

Khi nhận notice, hãy tính thời gian còn lại:

~~~text
T_remaining = T_d - T_now
~~~

Sau đó chọn hành động:

| Thời gian còn lại | Hành động ưu tiên |
|---|---|
| Còn nhiều thời gian so với một job | Ngừng nhận job mới, hoàn tất job hiện tại và commit |
| Chỉ đủ cho checkpoint | Dừng job tại ranh giới an toàn, lưu tiến độ rồi release lease |
| Gần safety margin | Ngừng mọi công việc mới, ghi checkpoint tối thiểu hoặc trạng thái phục hồi |
| Đã quá deadline | Không bắt đầu cleanup dài; ưu tiên tính nhất quán và để cơ chế phục hồi tiếp quản |

Các ngưỡng phải được đo từ workload thực tế. Không dùng một số giây cố định cho mọi ứng dụng hoặc mọi provider.

### 4.2. Dành safety margin

Một số bước shutdown có thời gian biến động: ghi object storage, flush log, đóng TLS connection, cập nhật queue visibility hoặc deregister load balancer. Nếu ứng dụng đợi đến giây cuối mới thực hiện, chỉ một lần network timeout cũng có thể khiến tiến trình vượt deadline.

Hãy đặt deadline nội bộ sớm hơn deadline nền tảng:

~~~text
application_deadline = provider_deadline - safety_margin
~~~

Ứng dụng phải hoàn tất trước application_deadline. Safety margin cần dựa trên percentile cao của thời gian cleanup và điều kiện mạng thực tế, không chọn theo giá trị trung bình.

### 4.3. Dùng đồng hồ monotonic cho timeout

Deadline tuyệt đối từ event có thể dùng UTC để lưu và audit. Tuy nhiên, bộ đếm timeout trong tiến trình nên dựa trên monotonic clock để việc chỉnh giờ hệ thống không làm thời gian còn lại tăng hoặc giảm bất ngờ.

Nếu host clock có thể lệch, cần tính sai số và giảm safety margin phù hợp. Không được kéo dài deadline chỉ vì đồng hồ của instance khác với clock của control plane.

## 5. State machine cho quy trình gián đoạn

Một state machine giúp tránh xử lý shutdown theo nhiều nhánh không nhất quán.

~~~mermaid
stateDiagram-v2
    [*] --> Running
    Running --> NoticeReceived: Interruption notice
    NoticeReceived --> Quiescing: Chặn công việc mới
    Quiescing --> Checkpointing: Có công việc đang chạy
    Quiescing --> Finalizing: Không còn công việc
    Checkpointing --> Draining: Checkpoint/commit xong
    Checkpointing --> Finalizing: Hết ngân sách
    Draining --> Finalizing: Lease đã release hoặc job đã ack
    Finalizing --> Exited: Đóng tài nguyên
    Running --> ForcedExit: Mất máy / kill đột ngột
    NoticeReceived --> ForcedExit: Deadline hết
    ForcedExit --> [*]
    Exited --> [*]
~~~

Các trạng thái:

- **Running:** nhận và xử lý công việc bình thường.
- **NoticeReceived:** đã ghi nhận tín hiệu và deadline.
- **Quiescing:** ngừng nhận request, message hoặc job mới.
- **Checkpointing:** lưu tiến độ của công việc đang chạy.
- **Draining:** hoàn tất, acknowledge hoặc release công việc theo giao thức.
- **Finalizing:** flush dữ liệu, đóng connection và dừng agent phụ thuộc.
- **Exited:** tiến trình đã thoát sạch.
- **ForcedExit:** tiến trình không có cơ hội hoàn tất; phục hồi dựa vào durable state.

Mọi chuyển trạng thái phải idempotent. Nhiều thread có thể cùng phát hiện signal hoặc nhận event; chỉ một luồng điều phối nên sở hữu state transition.

## 6. Dừng nhận công việc mới ngay khi có notice

Sau khi nhận notice, bước đầu tiên thường là ngừng nhận thêm công việc. Nếu tiếp tục nhận job trong lúc đang checkpoint, ứng dụng có thể không bao giờ kết thúc.

Tùy workload:

- API: đánh readiness false, deregister khỏi load balancer hoặc ngừng accept connection mới.
- Queue worker: dừng polling/receive message mới.
- Batch: không lấy partition hoặc chunk mới.
- Streaming consumer: dừng fetch record mới và xác định offset có thể commit an toàn.
- Scheduler: không phân công job mới cho instance sắp bị thu hồi.
- GPU worker: không nhận batch mới; lưu trạng thái model hoặc optimizer nếu job cần resume.

### 6.1. Drain request đang chạy

Với API, tiếp tục xử lý request đã nhận trong ngân sách còn lại. Nếu request không thể hoàn tất:

- Trả lỗi retryable nếu giao thức và client hỗ trợ.
- Bảo đảm thao tác có idempotency key.
- Không báo thành công trước khi kết quả đã commit.
- Đóng kết nối theo giao thức nếu buộc phải dừng.

Đối với HTTP/2, WebSocket hoặc streaming response, cần có cách báo đóng hoặc reconnect phù hợp. Không nên giữ connection mở vô hạn khi deadline đã gần.

### 6.2. Queue worker và lease

Với queue, message đã nhận thường có visibility timeout hoặc lease. Khi shutdown:

1. Dừng receive/poll.
2. Tiếp tục job hiện tại nếu đủ thời gian.
3. Lưu kết quả bền vững trước khi acknowledge.
4. Nếu chưa thể hoàn tất, lưu checkpoint và release/để lease hết hạn theo semantics của queue.
5. Đóng consumer sau khi công việc đã ở trạng thái có thể phục hồi.

Không acknowledge message chỉ để làm queue trống trước khi instance bị thu hồi. Nếu kết quả chưa được ghi an toàn, thao tác đó có thể làm mất công việc.

### 6.3. Tránh giữ lease quá hạn

Nếu worker không thể hoàn tất trước deadline, đừng tiếp tục gia hạn lease khi nó không còn đủ thời gian chạy. Worker khác cần có cơ hội nhận lại job. Việc release lease phải phối hợp với checkpoint để job không bắt đầu lại từ đầu nếu có thể tiếp tục.

## 7. Checkpoint theo deadline

Checkpoint lưu tiến độ để workload có thể tiếp tục trên một instance khác. Với compute bị thu hồi, checkpoint nên được thiết kế từ đầu thay vì chỉ bổ sung khi sự cố xảy ra.

Checkpoint có thể chứa:

- Job ID và phiên bản thuật toán.
- Input reference và checksum.
- Partition, offset hoặc vị trí xử lý.
- Trạng thái trung gian cần thiết.
- Output đã commit và output còn dang dở.
- Thời điểm checkpoint và sequence/version.
- Thông tin xác định instance/worker tạo checkpoint.

### 7.1. Chọn checkpoint granularity

Nếu checkpoint quá thưa, mất máy sẽ làm chạy lại nhiều công việc. Nếu checkpoint quá thường xuyên, workload tốn I/O và thời gian ghi. Hãy chọn granularity theo:

- Thời gian xử lý một chunk.
- Kích thước checkpoint.
- Chi phí ghi bền vững.
- RPO của tiến độ.
- Xác suất interruption và deadline thường gặp.

Với job dài, chia công việc thành chunk độc lập thường dễ phục hồi hơn một thao tác đơn khổng lồ.

### 7.2. Ghi checkpoint nhất quán

Checkpoint phải khớp với output đã lưu. Nếu checkpoint ghi trước output, lần chạy sau có thể bỏ qua kết quả chưa tồn tại. Nếu output ghi trước checkpoint, job có thể chạy lại phần đó.

Các cách thường dùng:

- Transaction bao gồm output và progress marker khi cùng database.
- Idempotent output với key duy nhất theo job/chunk.
- Write output vào object tạm, xác minh xong rồi ghi commit marker.
- Versioned checkpoint với sequence tăng đơn điệu.
- Manifest chỉ tham chiếu các chunk đã hoàn tất và bền vững.

Không ghi đè checkpoint tốt bằng một checkpoint cũ đến trễ. Dùng version hoặc compare-and-swap để chỉ chấp nhận tiến độ mới hơn.

### 7.3. Checkpoint phải ở storage bền vững

RAM, local ephemeral disk hoặc volume chỉ gắn với instance sắp bị thu hồi không phải nơi duy nhất lưu checkpoint. Hãy dùng database, object storage hoặc durable volume có khả năng tồn tại qua vòng đời instance.

Nếu checkpoint service không truy cập được, ứng dụng cần hành vi dự phòng: hoàn tất phần nhỏ có thể commit, release job để retry từ checkpoint trước hoặc ghi trạng thái phục hồi tối thiểu vào một nơi bền vững khác. Không giả vờ checkpoint đã thành công khi storage chưa xác nhận.

## 8. Job dài và công việc không thể dừng giữa chừng

Một số tác vụ không thể pause ở bất kỳ dòng lệnh nào. Ví dụ:

- Ghi một file archive lớn.
- Xử lý một transaction nghiệp vụ.
- Training một epoch hoặc cập nhật model.
- Build artifact cần output hoàn chỉnh.
- Chạy migration có thay đổi schema.

Hãy xác định safe point trước khi triển khai:

- Ranh giới giữa các chunk hoặc partition.
- Ranh giới transaction.
- Điểm commit output.
- Thời điểm có thể serialize trạng thái.
- Bước nào phải chạy lại nếu interruption xảy ra.

Nếu không có safe point, hãy thiết kế một wrapper hoặc protocol để thao tác trở nên atomic/idempotent, hoặc chọn loại compute ít có khả năng bị thu hồi hơn.

### 8.1. Không thể hoàn tất trước deadline

Nếu job còn 20 phút nhưng chỉ còn 30 giây trước interruption, ứng dụng không nên chờ job hoàn tất. Hãy:

1. Ngừng cấp job mới.
2. Yêu cầu job dừng ở safe point gần nhất.
3. Lưu checkpoint hoặc tiến độ đã commit.
4. Ghi trạng thái cần resume.
5. Release lease hoặc cho phép job được giao lại.
6. Thoát trước safety deadline.

### 8.2. Job không hỗ trợ checkpoint

Nếu không thể checkpoint, có thể dùng chiến lược:

- Chia nhỏ job ở scheduler.
- Lưu output theo chunk idempotent.
- Chạy lại toàn bộ chunk chưa commit.
- Giữ job trong queue cho worker khác.
- Dùng checkpoint ở tầng dữ liệu đầu vào/đầu ra thay vì serialize toàn bộ memory.

Không phải mọi ứng dụng đều phù hợp với Spot/preemptible compute. Workload yêu cầu xử lý liên tục không thể gián đoạn và không có cơ chế phục hồi có thể cần compute ổn định hơn.

## 9. Phối hợp với Linux, systemd và container runtime

Trên Linux, SIGTERM thường là yêu cầu kết thúc mềm. Ứng dụng nên bắt tín hiệu và chuyển sang cùng state machine đã định nghĩa. SIGKILL không thể bị bắt; khi bị gửi, tiến trình không thể chạy cleanup.

### 9.1. Xử lý SIGTERM

Handler của signal nên làm việc tối thiểu: đánh dấu shutdown requested hoặc đánh thức event loop. Không thực hiện network I/O, ghi file phức tạp hay chờ lock dài ngay bên trong signal handler.

Ví dụ Python:

~~~python
import asyncio
import signal

shutdown_requested = asyncio.Event()

def on_shutdown_signal():
    shutdown_requested.set()

async def run():
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, on_shutdown_signal)
    loop.add_signal_handler(signal.SIGINT, on_shutdown_signal)

    await worker.start()
    await shutdown_requested.wait()

    # Các bước dưới đây phải dùng deadline do interruption manager cấp.
    await worker.stop_accepting_new_jobs()
    await worker.checkpoint_or_finish_current_job()
    await worker.release_unfinished_lease()
    await worker.close()

asyncio.run(run())
~~~

Đây là ví dụ minh họa. Các hàm worker là adapter của ứng dụng; trong production cần bao từng bước bằng timeout dựa trên shutdown budget, xử lý cancellation và bảo đảm lỗi ở một bước không bỏ qua bước đóng tài nguyên thiết yếu. add_signal_handler phù hợp với event loop trên Unix; Windows cần cơ chế service control tương ứng.

### 9.2. systemd

systemd có thể gửi SIGTERM rồi chờ theo TimeoutStopSec trước khi kết thúc tiến trình theo chính sách của service. Thời gian này phải ngắn hơn deadline của nền tảng bên ngoài và đủ cho ứng dụng hoàn tất cleanup.

~~~ini
[Unit]
Description=Interruptible batch worker
After=network-online.target

[Service]
Type=simple
User=batch
ExecStart=/opt/batch/bin/worker
KillSignal=SIGTERM
TimeoutStopSec=40s
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

Giá trị 40 giây chỉ là ví dụ cho cấu hình service, không phải thời gian báo trước chung của cloud. Nếu provider chỉ còn 30 giây, systemd timeout 40 giây không bảo vệ được tiến trình. Deadline ngoài cùng luôn có ưu tiên.

### 9.3. Container runtime

Khi container dừng, runtime thường gửi signal tới tiến trình chính (PID 1), chờ grace period rồi kết thúc cưỡng bức nếu tiến trình chưa thoát. Hãy bảo đảm:

- Ứng dụng là PID 1 hoặc signal được init/wrapper chuyển tiếp đúng.
- Signal handler khởi động shutdown state machine.
- Grace period của container không dài hơn deadline instance/node.
- Không dựa vào shell wrapper bỏ qua signal.
- Health/readiness được cập nhật để ngừng nhận traffic.

## 10. Kubernetes termination lifecycle

Khi Pod bị xóa hoặc thay thế, Kubernetes chuyển Pod sang terminating, cập nhật endpoint để ngừng đưa Pod vào các endpoint sẵn sàng mới, chạy preStop hook nếu có, gửi tín hiệu kết thúc tới container và chờ terminationGracePeriodSeconds. Khi hết grace period, runtime có thể kết thúc container cưỡng bức.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
spec:
  replicas: 4
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: worker
          image: registry.example/batch-worker:v4
          lifecycle:
            preStop:
              exec:
                command: ["/app/bin/drain", "--deadline-seconds=35"]
~~~

Đây là cấu hình minh họa. Lệnh drain phải là công cụ có thật trong image và phải dừng nhận job, checkpoint hoặc release lease theo giao thức. preStop tiêu thụ thời gian trong termination grace period; không cộng thời gian hook bên ngoài ngân sách 45 giây. Ứng dụng vẫn cần xử lý SIGTERM và tự theo dõi deadline.

Với node bị thu hồi, cần phân biệt thời gian báo trước của cloud provider với thời gian termination grace period của Pod. Node có thể không còn đủ thời gian để áp dụng toàn bộ grace period cho mọi Pod. Không nên giả định mỗi Pod đều được cấp trọn vẹn thời gian đã cấu hình khi node bị mất đột ngột.

### 10.1. Pod eviction và node interruption

Pod eviction có thể do drain node, resource pressure hoặc quy trình quản trị. Node interruption có thể do cloud reclaim hoặc host failure. Các event khác nhau có thể đi qua đường xử lý khác nhau.

Nếu dùng node termination handler hoặc agent tương đương, cần kiểm tra:

- Agent nhận notice từ đúng provider.
- Agent có quyền cần thiết và được triển khai trên mọi node phù hợp.
- Thứ tự cordon, drain và terminate đúng với nền tảng.
- PodDisruptionBudget có ảnh hưởng đến voluntary drain không.
- Workload stateful có volume/replication phù hợp không.
- Hệ thống xử lý trường hợp agent hoặc event bus không hoạt động.

## 11. Windows Service và ứng dụng chạy trên Windows

Windows Service nhận yêu cầu dừng qua Service Control Manager (SCM), thường là SERVICE_CONTROL_STOP. Service nên chuyển sang trạng thái stop pending, ngừng nhận công việc mới, hoàn tất hoặc checkpoint job và báo stopped khi đã cleanup.

Các điểm cần triển khai:

- Handler stop chỉ phát tín hiệu cho worker/event loop.
- Dừng nhận request hoặc message mới.
- Dùng cancellation token hoặc cơ chế tương đương truyền deadline xuống các tác vụ.
- Đặt timeout cho network, storage và database operation.
- Flush dữ liệu và log cần thiết.
- Đóng connection, thread, timer và handle.
- Ghi nhận trạng thái nếu buộc phải dừng trước khi job hoàn tất.

Windows có cơ chế preshutdown cho service được cấu hình hỗ trợ, nhưng thời gian và hành vi phụ thuộc SCM cùng chính sách hệ thống. Không coi preshutdown là bảo đảm rằng ứng dụng có thời gian vô hạn. Deadline của cloud hoặc hypervisor vẫn là giới hạn ngoài cùng.

## 12. Phân biệt graceful stop, pause và hibernate

Các nền tảng có thể cung cấp nhiều hành động khi tài nguyên bị thu hồi:

- **Stop:** dừng VM hoặc tiến trình; bộ nhớ đang chạy không nhất thiết được bảo toàn.
- **Terminate:** xóa instance/tài nguyên theo semantics của dịch vụ.
- **Hibernate:** lưu trạng thái bộ nhớ vào storage theo khả năng dịch vụ rồi dừng VM; không phải mọi instance/workload đều hỗ trợ.
- **Pause/suspend:** tạm ngừng thực thi nếu nền tảng có hỗ trợ, nhưng không nên mặc định có thể tiếp tục đúng trạng thái.
- **Checkpoint:** ứng dụng tự lưu trạng thái nghiệp vụ để chạy lại trên compute khác.

Hibernate không thay thế checkpoint nghiệp vụ. Một image memory có thể phụ thuộc phần cứng, kernel, network session hoặc trạng thái bên ngoài; khi resume, ứng dụng vẫn cần kiểm tra kết nối và tính nhất quán. Checkpoint ở cấp ứng dụng thường dễ di chuyển giữa các instance hơn.

## 13. Deadline-aware worker: ví dụ triển khai

Worker cần một interruption manager sở hữu deadline và chuyển trạng thái. Các job nên có giới hạn thời gian, checkpoint tại safe point và chỉ acknowledge sau khi kết quả bền vững.

Ví dụ Python ở mức khung:

~~~python
import asyncio
import time

SAFETY_MARGIN_SECONDS = 5
shutdown_requested = asyncio.Event()
deadline_monotonic = None

def request_shutdown(deadline_seconds_from_now):
    global deadline_monotonic
    candidate = time.monotonic() + deadline_seconds_from_now

    # Nếu nhận nhiều notice, giữ deadline sớm nhất.
    if deadline_monotonic is None:
        deadline_monotonic = candidate
    else:
        deadline_monotonic = min(deadline_monotonic, candidate)

    shutdown_requested.set()

def remaining_budget():
    if deadline_monotonic is None:
        return None  # Chưa có interruption: chưa áp deadline dừng.
    return max(
        0,
        deadline_monotonic - time.monotonic() - SAFETY_MARGIN_SECONDS,
    )

async def run_worker(queue):
    while not shutdown_requested.is_set():
        job = await queue.receive(timeout=1)
        if job is None:
            continue

        if shutdown_requested.is_set():
            await queue.release(job)
            break

        # Hàm xử lý kiểm tra stop_event tại các safe point.
        outcome = await process_until_safe_point(
            job,
            stop_event=shutdown_requested,
            remaining_budget=remaining_budget,
        )

        if outcome.completed:
            await persist_result(job.id, outcome.result)
            await queue.ack(job)
            continue

        # Job chưa hoàn tất: checkpoint rồi release trong phần budget còn lại.
        budget = remaining_budget()
        if budget > 0:
            try:
                await asyncio.wait_for(
                    save_checkpoint(job, outcome.checkpoint_state),
                    timeout=budget,
                )
            except asyncio.TimeoutError:
                pass  # Giữ checkpoint bền vững gần nhất đã commit.

        budget = remaining_budget()
        if budget > 0:
            try:
                await asyncio.wait_for(queue.release(job), timeout=budget)
            except asyncio.TimeoutError:
                pass  # Lease sẽ hết hạn theo semantics của queue.
        break

    # Đóng consumer nếu còn thời gian; nếu không, để lease/connection timeout
    # và cơ chế phục hồi của queue tiếp quản.
    budget = remaining_budget()
    if budget > 0:
        await asyncio.wait_for(queue.close(), timeout=budget)
~~~

Đây là khung minh họa, không phải thư viện queue hoàn chỉnh. Hàm process_until_safe_point phải tiếp tục bình thường khi chưa có notice và chỉ trả về kết quả chưa hoàn tất khi stop_event được đặt hoặc budget sắp hết. Trong production, các bước persist, ack, checkpoint, release và close cần có timeout riêng, trạng thái job có version và thao tác idempotent. Nếu không còn đủ thời gian hoặc storage không truy cập được, hãy dựa vào checkpoint bền vững gần nhất và để lease hết hạn theo semantics của queue. Không acknowledge khi chưa commit kết quả.

## 14. Xử lý khi notice đến quá muộn hoặc không đến

Notice có thể đến trễ do event delivery, agent lỗi, network partition hoặc host failure. Ứng dụng phải có cơ chế phục hồi độc lập với notice.

### 14.1. Thiết kế cho mất máy đột ngột

- Lưu trạng thái quan trọng ở storage bền vững.
- Checkpoint định kỳ thay vì chỉ checkpoint khi nhận notice.
- Dùng lease có thời hạn để worker khác tiếp nhận job bị bỏ lại.
- Dùng idempotency key để xử lý lại an toàn.
- Đặt transaction boundary rõ ràng.
- Có watchdog phát hiện worker mất heartbeat.
- Không phụ thuộc cleanup để dữ liệu trở nên nhất quán.

### 14.2. Checkpoint định kỳ và checkpoint khẩn cấp

Checkpoint định kỳ giảm lượng tiến độ phải làm lại nếu không có notice. Khi notice đến, checkpoint khẩn cấp lưu phần tiến độ mới kể từ checkpoint gần nhất.

Tần suất định kỳ có thể chọn theo chi phí checkpoint và mức mất tiến độ chấp nhận được. Không đợi tới interruption mới ghi toàn bộ trạng thái nếu việc đó có thể vượt deadline.

### 14.3. Reconciliation sau khi instance mất

Scheduler hoặc controller cần phát hiện job có lease hết hạn, instance không heartbeat hoặc trạng thái execution chưa kết thúc. Nó có thể:

1. Đánh dấu execution cũ là interrupted/unknown.
2. Kiểm tra checkpoint và output đã commit.
3. Tạo execution mới hoặc giao lại job.
4. Dùng idempotency để tránh ghi trùng.
5. Ghi lại attempt count và nguyên nhân interruption.

Không được coi việc instance biến mất là bằng chứng job thất bại hoàn toàn; có thể output đã commit trước khi acknowledgement bị mất. Cần reconciliation với durable state.

## 15. Các lưu ý theo nhà cung cấp

Mỗi cloud provider có cơ chế và thời gian thông báo riêng. Một số ví dụ thường gặp:

| Nền tảng | Cơ chế có thể gặp | Lưu ý thiết kế |
|---|---|---|
| AWS EC2 Spot | Interruption notice qua instance metadata và event service; có thể có rebalance recommendation | Xử lý notice và rebalance event; kiểm tra hành động stop/hibernate/terminate được cấu hình |
| Azure Spot VM | Scheduled Events/eviction notice tùy loại VM và cấu hình | Theo dõi event qua cơ chế Scheduled Events và chuẩn bị dừng nhanh |
| Google Cloud Spot/Preemptible | Preemption notice qua metadata/service event theo loại VM | Có thể chỉ có khoảng báo trước ngắn; thiết kế checkpoint thường xuyên |
| Kubernetes trên cloud | Node event, termination handler và Pod termination lifecycle | Kết hợp notice của node với drain và grace period của Pod |

Thời gian báo trước, trường payload, event delivery và hành động sau notice có thể thay đổi theo loại compute, region và chính sách dịch vụ. Hãy xác minh tài liệu hiện hành cho đúng loại instance và cấu hình. Không dùng một con số cố định cho mọi provider hoặc giả định notice luôn được gửi.

### 15.1. Adapter theo provider

Nên tách tích hợp:

- AwsInterruptionAdapter
- AzureScheduledEventAdapter
- GcpPreemptionAdapter
- KubernetesTerminationAdapter
- OsSignalAdapter

Mỗi adapter chuyển event riêng thành ShutdownRequested nội bộ. Phần worker, checkpoint và shutdown manager dùng chung một giao thức. Cách này giảm phụ thuộc provider và giúp kiểm thử state machine bằng event giả lập.

## 16. Quan sát quá trình interruption

Ứng dụng cần ghi nhận cả thời gian và kết quả của từng giai đoạn:

- Số notice theo reason và source.
- Thời gian từ notice tới lúc bắt đầu quiescing.
- Thời gian ngừng nhận job mới.
- Số job đang chạy khi nhận notice.
- Số job hoàn tất, checkpoint, release hoặc retry.
- Thời gian checkpoint và tỷ lệ checkpoint thất bại.
- Deadline còn lại khi bắt đầu finalization.
- Số lần vượt deadline hoặc bị forced termination.
- Số job được giao lại sau interruption.
- Số lần xử lý trùng và kết quả idempotency.

Metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| interruption_notice_total | Số interruption notice đã nhận |
| interruption_notice_late_total | Số notice đến khi ngân sách còn lại quá thấp |
| shutdown_remaining_seconds | Thời gian còn lại khi bắt đầu từng giai đoạn |
| shutdown_duration_seconds | Tổng thời gian từ notice tới exit |
| checkpoint_duration_seconds | Thời gian lưu checkpoint |
| checkpoint_failure_total | Số lần checkpoint thất bại |
| jobs_released_on_interrupt_total | Số job được release |
| jobs_retried_after_interrupt_total | Số job được giao lại |
| forced_termination_total | Số lần tiến trình không thoát kịp |

Log cần có event ID, resource ID, reason, deadline, state transition và correlation/job ID. Không ghi token, secret hoặc payload nhạy cảm vào log.

## 17. Kiểm thử interruption handling

Kiểm thử cần chứng minh ứng dụng phản ứng đúng khi có nhiều mức thời gian và lỗi phụ thuộc.

Các kịch bản:

1. Nhận notice khi không có job đang chạy.
2. Nhận notice ngay sau khi lấy message nhưng trước khi bắt đầu xử lý.
3. Nhận notice khi job còn đủ thời gian hoàn tất.
4. Nhận notice khi job không thể hoàn tất trước deadline.
5. Nhận hai notice trùng event ID.
6. Nhận notice thứ hai có deadline sớm hơn.
7. Nhận event đến trễ hoặc deadline đã qua.
8. Checkpoint storage timeout hoặc không truy cập được.
9. Worker bị kill giữa lúc ghi output và checkpoint.
10. Worker commit xong nhưng chưa acknowledge queue.
11. Mất event agent nhưng OS vẫn gửi SIGTERM.
12. Không nhận notice và instance bị mất đột ngột.
13. Kubernetes Pod bị terminating khi node cũng đang bị thu hồi.
14. Service Windows nhận stop trong lúc xử lý job.

### 17.1. Tiêu chí đạt

- Không nhận công việc mới sau khi chuyển sang quiescing.
- Deadline không bị kéo dài khi có event trùng hoặc đến trễ.
- Checkpoint phản ánh đúng output đã commit.
- Message chỉ được acknowledge sau khi kết quả bền vững.
- Job chưa hoàn tất có thể retry hoặc resume.
- Cleanup kết thúc trước application deadline trong kịch bản được hỗ trợ.
- Khi mất notice hoặc bị kill đột ngột, durable state vẫn cho phép phục hồi.
- Không tạo side effect trùng ngoài kiểm soát.

### 17.2. Diễn tập trong môi trường an toàn

Có thể tạo một interruption simulator gửi event với deadline ngắn để kiểm tra state machine. Bắt đầu với một worker canary, giới hạn số job và dùng dữ liệu thử nghiệm. Ghi lại thời gian từng giai đoạn, sau đó tăng dần độ phức tạp.

Không thử nghiệm thu hồi một fleet production lớn nếu chưa có giới hạn blast radius, capacity dự phòng và điều kiện dừng rõ ràng.

## 18. Ví dụ thực tế: batch xử lý ảnh trên Spot VM

Một hệ thống xử lý ảnh dùng Spot VM để giảm chi phí. Mỗi job đọc một nhóm ảnh từ object storage, tạo thumbnail và ghi kết quả. Job có thể kéo dài vài phút, trong khi notice thu hồi có thể chỉ cho một khoảng thời gian ngắn.

Thiết kế:

1. Scheduler gửi job ID và danh sách object vào durable queue.
2. Worker lấy job bằng lease có thời hạn.
3. Mỗi ảnh được xử lý thành một chunk độc lập.
4. Thumbnail được ghi bằng key idempotent theo job ID và object ID.
5. Sau mỗi chunk, worker ghi checkpoint gồm danh sách object đã hoàn tất.
6. Khi nhận interruption notice, worker dừng polling queue.
7. Worker hoàn tất chunk hiện tại nếu còn đủ budget; nếu không, hủy ở safe point.
8. Worker ghi checkpoint mới, release lease và đóng client.
9. Instance khác nhận job, đọc checkpoint và tiếp tục phần chưa hoàn tất.

Nếu worker bị mất trước khi ghi checkpoint, chunk gần nhất có thể được chạy lại. Vì output dùng key idempotent, chạy lại không tạo thumbnail trùng. Queue và durable state cho phép hệ thống tiếp tục mà không cần instance cũ.

## 19. Chọn workload phù hợp với interruptible compute

Workload phù hợp thường có một hoặc nhiều đặc điểm:

- Có thể chia thành chunk hoặc partition.
- Có thể checkpoint hoặc chạy lại với chi phí chấp nhận được.
- Không cần giữ kết nối dài hạn tới một client.
- Có thể dùng queue hoặc scheduler để phân phối lại.
- Có output idempotent hoặc transaction rõ ràng.
- Có thể chấp nhận thời gian hoàn thành biến động.

Ví dụ:

- Batch rendering, transcoding hoặc xử lý ảnh.
- CI build và test có thể chạy lại.
- Distributed data processing.
- Simulation hoặc workload nghiên cứu có checkpoint.
- Worker xử lý queue.
- Stateless service có capacity dự phòng và khả năng thay instance.

Workload ít phù hợp:

- Database primary tự quản lý không có replication/failover phù hợp.
- Tác vụ ghi dữ liệu duy nhất nhưng không có transaction/checkpoint.
- Session hoặc state quan trọng chỉ nằm trong RAM.
- Job dài không thể dừng hoặc chạy lại.
- Hệ thống yêu cầu latency rất ổn định và không có capacity thay thế.

Không phải workload không phù hợp thì tuyệt đối không thể chạy trên Spot/preemptible. Có thể tách phần có thể gián đoạn sang compute giá thấp và giữ phần stateful/critical trên compute ổn định.

## 20. Những sai lầm thường gặp

- **Coi notice là bảo đảm:** event có thể đến trễ, bị mất hoặc không được hỗ trợ trong một số failure mode.
- **Dùng một timeout cho mọi provider:** mỗi loại compute có deadline và semantics khác nhau.
- **Chỉ bắt SIGTERM:** bỏ lỡ interruption notice đến sớm hơn từ cloud control plane.
- **Chỉ nghe event bus:** không xử lý trường hợp event agent hoặc network bị lỗi.
- **Tiếp tục nhận job mới sau notice:** làm tăng công việc cần dừng và dễ vượt deadline.
- **Chờ job dài hoàn tất bằng mọi giá:** không dành thời gian cho checkpoint và cleanup.
- **Checkpoint chỉ trong RAM/local disk:** mất cùng instance khi bị thu hồi.
- **Ack trước khi commit:** có thể mất message và kết quả.
- **Release lease nhưng không checkpoint:** worker khác phải chạy lại toàn bộ job.
- **Không xử lý event trùng:** shutdown handler chạy nhiều lần và gây race condition.
- **Cho event mới kéo dài deadline:** có thể vượt thời gian provider cho phép.
- **Không dành safety margin:** network hoặc storage chậm khiến shutdown bị kill.
- **Dùng preStop thay cho logic ứng dụng:** hook không tự bảo đảm dữ liệu và lease được xử lý đúng.
- **Chỉ kiểm thử graceful notice:** không kiểm tra mất host hoặc forced termination.

## 21. Checklist triển khai

Trước khi dùng interruptible compute, hãy xác nhận:

- [ ] Workload có thể chia nhỏ, checkpoint hoặc retry an toàn.
- [ ] Đã xác định nguồn interruption notice của provider.
- [ ] Có adapter chuyển notice và OS signal về cùng một shutdown event.
- [ ] Event có reason, resource ID, event ID và deadline.
- [ ] Handler xử lý event trùng và event đến trễ một cách idempotent.
- [ ] Deadline nội bộ ngắn hơn deadline nền tảng và có safety margin.
- [ ] Ứng dụng ngừng nhận job mới ngay khi quiescing.
- [ ] Queue lease, acknowledgement và retry được phối hợp đúng.
- [ ] Checkpoint được ghi vào storage bền vững và có version.
- [ ] Output và checkpoint nhất quán, có idempotency.
- [ ] Container/systemd/Windows Service timeout nằm trong ngân sách ngoài cùng.
- [ ] Có cơ chế phục hồi khi notice không đến hoặc checkpoint thất bại.
- [ ] Metric và log ghi lại thời gian từng giai đoạn.
- [ ] Đã kiểm thử deadline ngắn, event trùng, mất notice và forced termination.

## 22. Ghi nhớ

Interruption notice là cơ hội để workload chuẩn bị trước khi compute bị thu hồi. Ứng dụng cần nhận biết nguồn tín hiệu, chuẩn hóa event, đặt deadline và safety margin, ngừng nhận công việc mới, checkpoint hoặc hoàn tất công việc có thể, release lease, đóng tài nguyên và thoát đúng hạn.

Thiết kế nên dùng một state machine idempotent và deadline-aware để phối hợp cloud event, orchestrator và OS signal. Queue, checkpoint, transaction, lease và idempotency phải được thiết kế cùng nhau để instance mới có thể tiếp tục. Vì notice không phải lúc nào cũng đến, checkpoint định kỳ và durable state vẫn là lớp bảo vệ thiết yếu khi máy mất đột ngột. Hãy đo thời gian shutdown và diễn tập interruption thường xuyên để chứng minh workload có thể phục hồi an toàn trong giới hạn thời gian thực tế.
