# Sử dụng tài nguyên có thể bị thu hồi cho tải chịu gián đoạn

## 1. Compute giá thấp đi kèm một giả định quan trọng

Các nhà cung cấp cloud thường có loại năng lực tính toán giá thấp hơn, đổi lại họ có quyền **thu hồi (reclaim/preempt)** máy khi cần capacity hoặc theo điều kiện dịch vụ. Các tên thường gặp là **Spot Instances**, **Spot VMs**, **preemptible VMs** hoặc interruptible capacity. Tên gọi, giá, điều kiện thu hồi, thông báo trước và mức hỗ trợ khác nhau theo nhà cung cấp, loại instance, region và thời điểm.

Điều cần thay đổi trong tư duy thiết kế là: **máy có thể biến mất khi workload vẫn đang chạy**. Ứng dụng phải có khả năng chịu gián đoạn, lưu trạng thái cần thiết bên ngoài máy, nhận biết việc thu hồi khi nền tảng cung cấp tín hiệu và đưa công việc chưa hoàn tất trở lại hàng đợi.

Trong module **CLOUD_ARCHITECTURE**, lựa chọn compute phải được đánh giá cùng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Tài nguyên có thể bị thu hồi là một công cụ tối ưu chi phí cho tải phù hợp, không phải cấu hình mặc định cho mọi workload.

Sau bài này, bạn có thể:

- Nhận diện workload phù hợp và không phù hợp với interruptible capacity.
- Thiết kế luồng công việc chịu được việc worker/VM/container bị thu hồi.
- Xử lý interruption notice, graceful shutdown, checkpoint, retry và idempotency.
- Kết hợp capacity có thể bị thu hồi với năng lực on-demand/regular để giữ mức dịch vụ tối thiểu.
- Đa dạng hóa pool, instance type, zone và cách phân phối tác vụ để giảm rủi ro thiếu capacity.
- Đo tổng chi phí thực tế, thời gian hoàn tất và tác động tới SLO trước khi mở rộng sử dụng.

## 2. Tài nguyên có thể bị thu hồi là gì?

Với compute thông thường theo mô hình on-demand hoặc capacity được giữ phù hợp, khách hàng trả tiền để dùng tài nguyên theo điều kiện dịch vụ đã chọn. Với **spot/preemptible capacity**, cloud provider cung cấp năng lực dư thừa hoặc có thể phân bổ lại với mức giá thấp hơn, nhưng có quyền lấy lại khi cần.

Khác biệt thiết kế không chỉ là giá:

| Đặc điểm | Capacity thông thường/on-demand | Capacity có thể bị thu hồi |
|---|---|---|
| Khả năng tiếp tục chạy | Thường ổn định hơn theo cam kết loại dịch vụ đã chọn; vẫn có thể gặp lỗi hạ tầng | Có thêm rủi ro thu hồi chủ động theo điều kiện spot |
| Giá | Thường cao hơn | Thường thấp hơn, có thể biến động tùy mô hình/provider |
| Khả năng có sẵn khi cần tạo mới | Phụ thuộc quota, loại máy, zone và capacity | Có thể không cấp được pool mong muốn tại thời điểm yêu cầu |
| Thông báo thu hồi | Phụ thuộc loại sự cố/dịch vụ | Một số dịch vụ cung cấp interruption notice hoặc metadata; không được giả định mọi trường hợp đều có cảnh báo đủ dài |
| Thích hợp | API cốt lõi, stateful service, thành phần cần capacity ổn định | Batch, worker, render, simulation, CI, xử lý dữ liệu có thể chia nhỏ/chạy lại |
| Thiết kế ứng dụng | Vẫn phải chịu lỗi và triển khai HA | Phải chủ động thiết kế retry, checkpoint, drain và capacity fallback |

**Spot không đồng nghĩa với miễn phí hoặc không đáng tin cậy.** Nó là một phương án mua compute với điều kiện thu hồi khác. Tỷ lệ tiết kiệm, thời gian sống của máy và khả năng cấp mới không thể được coi là hằng số chung cho mọi region hay loại instance.

Một số dịch vụ có thể chấm dứt instance do thu hồi capacity; một số nền tảng có thể cung cấp thời gian cảnh báo trước, một số trường hợp khác có thể kết thúc nhanh hoặc do sự cố không có thông báo. Hãy thiết kế để **không phụ thuộc vào việc luôn nhận được cảnh báo**.

## 3. Workload nào phù hợp?

Điểm quyết định là **chi phí mất tiến trình đang chạy có thể kiểm soát đến đâu**, không chỉ là workload có chạy trên VM hay không.

### 3.1. Workload thường phù hợp

| Workload | Vì sao phù hợp | Điều kiện cần |
|---|---|---|
| Batch xử lý file/ảnh/video | Có thể chia file thành đơn vị nhỏ và chạy lại | Lưu checkpoint/kết quả từng phần ở storage bền vững |
| Render, encode, simulation | Công việc tách thành frame/task độc lập | Task có ID ổn định, output có thể xác minh, retry được |
| Data processing/ETL | Có thể xử lý theo partition hoặc micro-batch | Offset/checkpoint và commit output nhất quán |
| CI build/test | Job thường ngắn, có thể chạy lại khi agent bị thu hồi | Artifact/log lưu ngoài worker; pipeline có retry hợp lý |
| Worker xử lý queue | Message có thể được giao lại nếu worker biến mất | Visibility timeout/lease, ack sau xử lý và idempotency |
| Huấn luyện hoặc tính toán phân tán chịu gián đoạn | Có thể checkpoint model/training state | Phối hợp worker, checkpoint đủ thường xuyên, khôi phục được cụm |
| Dev/test tạm thời | Có thể tạo lại từ IaC và dữ liệu mẫu | Không lưu dữ liệu duy nhất trên VM, không chứa phụ thuộc production |

### 3.2. Workload cần thận trọng hoặc thường không phù hợp

| Workload | Rủi ro | Hướng thiết kế khác |
|---|---|---|
| Database primary hoặc datastore tự quản lý | Thu hồi có thể ảnh hưởng tính sẵn sàng, consistency và recovery | Managed DB/compute ổn định; nếu dùng cho replica hoặc tác vụ phụ thì phải kiểm thử vai trò failover |
| API cốt lõi yêu cầu latency/availability chặt | Nhiều instance cùng pool có thể bị thu hồi hoặc không cấp lại kịp | Giữ capacity nền ổn định, có thể dùng spot cho replica bổ sung nếu đã kiểm soát |
| Stateful service chỉ lưu dữ liệu trên local disk | Mất node có thể mất dữ liệu/chưa ghi | Externalize state; dùng storage bền vững được hỗ trợ |
| Tác vụ dài, không có checkpoint | Mất compute đồng nghĩa làm lại toàn bộ thời gian đã chạy | Chia nhỏ, checkpoint, hoặc dùng capacity ổn định |
| Tác vụ tương tác người dùng đang mở session trên một VM | Thu hồi tạo ngắt phiên, mất trạng thái cục bộ | Session store dùng chung, stateless app và drain |
| Hệ thống điều khiển/điều phối quan trọng | Mất scheduler/leader có thể ảnh hưởng toàn cụm | Tách control plane/leader khỏi spot pool; chỉ worker có thể bị thu hồi |

Không có bảng nào thay thế được thử nghiệm. Một workload dài nhiều giờ vẫn có thể phù hợp nếu checkpoint đáng tin cậy; một worker chỉ chạy vài giây vẫn không phù hợp nếu side effect không idempotent và không thể đối soát.

## 4. Kiến trúc tham chiếu: hàng đợi + worker có thể bị thu hồi

Ví dụ BookingCloud có thêm tác vụ tạo ảnh thumbnail và xuất báo cáo. Khi khách tải ảnh lên, API lưu metadata và file gốc ở object storage, sau đó phát message tạo thumbnail. Worker chạy trên pool spot; kết quả được ghi vào object storage. API và database nghiệp vụ vẫn nằm trên capacity ổn định.

~~~mermaid
flowchart TB
    User["Người dùng"] --> API["Upload/API service<br/>Capacity ổn định"]
    API --> DB[("Metadata DB")]
    API --> OBJ[("Object storage: file gốc")]
    API --> Q["Managed queue"]

    subgraph COMPUTE["Compute worker pool"]
      ON["Worker nền ổn định<br/>On-demand baseline"]
      SP["Worker có thể bị thu hồi<br/>Spot / preemptible"]
    end
    Q --> ON
    Q --> SP
    ON --> OBJ
    SP --> OBJ
    ON --> MET["Logs / metrics / traces"]
    SP --> MET
    MON["Autoscaler / scheduler"] --> ON
    MON --> SP
    SP -.->|"Interruption notice nếu có"| DRAIN["Stop nhận task mới<br/>checkpoint / release lease"]
    DRAIN --> Q
~~~

Điểm quan trọng:

- API xác nhận file và metadata sau khi có nơi lưu bền vững; không dựa vào ổ đĩa local của worker.
- Queue lưu công việc cần làm; worker chỉ nhận task khi có khả năng xử lý.
- Một phần worker capacity ổn định đảm bảo hệ thống còn tiến triển khi spot pool bị thu hồi hoặc không cấp mới được.
- Spot workers xử lý phần tải có thể phân phối lại; khi bị thu hồi, task phải trở lại hàng đợi hoặc được một worker khác tiếp nhận.
- Object storage và DB là nguồn dữ liệu có thẩm quyền; worker có thể tạo output tạm ở local nhưng phải ghi kết quả cuối theo cơ chế an toàn.

Đây là sơ đồ logic. Với từng provider, cần kiểm tra dịch vụ queue, cơ chế autoscaling, metadata interruption và quyền IAM cụ thể.

## 5. Thiết kế task để có thể chạy lại an toàn

Một worker có thể bị kết thúc ở bất cứ thời điểm nào; ngay cả khi có interruption notice, ứng dụng có thể không kịp hoàn thành mọi thao tác. Vì vậy, mô hình xử lý nên giả định **một task có thể chạy nhiều lần**.

### 5.1. Chia công việc thành đơn vị độc lập

Thay vì giao cho một worker toàn bộ dữ liệu 500 GB trong một task, chia thành partition hoặc object nhỏ:

~~~text
Job: generate-report-2026-11
  Task 0001: read partition 0001 -> write result 0001
  Task 0002: read partition 0002 -> write result 0002
  Task 0003: read partition 0003 -> write result 0003
  ...
  Finalize: verify all partitions -> publish report
~~~

Khi worker xử lý task 0002 bị thu hồi, hệ thống chỉ cần chạy lại partition đó thay vì khởi động toàn bộ job từ đầu.

Mỗi task nên có:

- **Task ID ổn định:** xác định cùng một đơn vị công việc qua các lần retry.
- **Input version/checksum:** biết task đang xử lý đúng phiên bản dữ liệu nào.
- **Lease/visibility timeout:** xác định worker nào tạm chịu trách nhiệm và thời điểm task có thể được giao lại.
- **Checkpoint:** ghi tiến độ đến nơi lưu bền vững theo các mốc có thể khôi phục.
- **Output path xác định:** tránh mỗi lần retry tạo vô hạn kết quả không liên quan.
- **Attempt count/deadline:** giới hạn retry và nhận diện task lỗi lâu dài.

### 5.2. Idempotency và side effect

**Idempotent operation** là thao tác mà thực hiện lặp lại với cùng định danh/đầu vào không làm trạng thái cuối khác đi so với một lần thực hiện hợp lệ. Đây là thuộc tính then chốt khi message/task có thể được giao lại.

Ví dụ, worker tạo thumbnail:

1. Đầu vào gồm `task_id`, `source_object_version` và cấu hình resize.
2. Tạo output tại đường dẫn xác định theo task/version, chẳng hạn `thumbnails/{task_id}/{version}.jpg`.
3. Ghi output tạm rồi publish/rename hoặc cập nhật manifest theo cơ chế storage hỗ trợ; tránh để client nhìn thấy file dở dang.
4. Ghi trạng thái hoàn thành bằng thao tác điều kiện/transaction phù hợp.
5. Nếu retry thấy đúng output đã hoàn tất và checksum hợp lệ, có thể trả thành công mà không nhân đôi side effect.

Với tác vụ thu tiền, gửi email hoặc cập nhật hệ thống bên ngoài, không được chỉ dựa vào “đã nhận ack”. Cần idempotency key được hỗ trợ ở dịch vụ nhận, bảng deduplication, trạng thái workflow hoặc quy trình đối soát. Không phải mọi side effect đều có thể hoàn toàn exactly-once chỉ bằng queue.

### 5.3. Checkpoint ở đâu và bao lâu một lần?

Checkpoint chứa đủ thông tin để tiếp tục hoặc xác minh phần đã hoàn thành: offset, partition, bước workflow, version đầu vào, kết quả trung gian và checksum. Nơi lưu có thể là DB bền vững, object storage hoặc checkpoint service phù hợp.

Chu kỳ checkpoint là một đánh đổi:

- Checkpoint quá thường xuyên làm tăng I/O, chi phí và thời gian không làm công việc chính.
- Checkpoint quá thưa khiến một lần thu hồi làm mất nhiều công sức đã chạy.
- Checkpoint không nguyên tử với output có thể khiến hệ thống đánh dấu xong nhưng dữ liệu chưa bền vững, hoặc ghi output nhưng trạng thái vẫn pending.

Một ước lượng đơn giản cho khoảng thời gian checkpoint tối ưu thường được biểu diễn bằng các biến: tần suất lỗi/thu hồi, thời gian ghi checkpoint và thời gian công việc có thể bị mất. Không dùng một công thức duy nhất cho mọi workload; hãy đo chi phí checkpoint và thời gian làm lại bằng tải đại diện.

### 5.4. Không giữ state duy nhất trên local disk

Local SSD/ephemeral disk hữu ích cho cache hoặc scratch space, nhưng dữ liệu cần khôi phục phải được đẩy ra storage bền vững. Nếu bắt buộc dùng volume mạng, cần kiểm tra hành vi detach/re-attach, durability, throughput, zone affinity và giới hạn attach khi instance bị thu hồi.

Thiết kế nên có thể tái tạo worker từ image/IaC + cấu hình + dữ liệu bền vững. Không lưu credential dài hạn, private key hay file dữ liệu duy nhất trên local disk của spot VM.

## 6. Xử lý interruption: nhận tín hiệu, drain và trả task

### 6.1. Luồng graceful interruption

Khi nền tảng gửi cảnh báo thu hồi (nếu dịch vụ hỗ trợ), agent trên máy hoặc orchestration layer cần:

1. **Ngừng nhận việc mới:** đánh dấu worker không sẵn sàng trong scheduler/queue consumer.
2. **Dừng nhận message:** không lấy thêm task; task đã nhận phải được hoàn tất hoặc giải phóng lease.
3. **Checkpoint nếu kịp:** chỉ ghi checkpoint đã được xác nhận bền vững; không coi tín hiệu interruption là bảo đảm còn đủ thời gian.
4. **Commit kết quả nguyên tử:** hoàn tất side effect hoặc lưu trạng thái intermediate có thể retry.
5. **Ack hoặc release:** ack chỉ khi task hoàn tất và kết quả bền vững; nếu chưa xong, không ack hoặc release/requeue theo cơ chế dịch vụ.
6. **Đóng tài nguyên:** flush log/metric cần thiết, dọn connection và kết thúc process nhanh chóng.

~~~mermaid
sequenceDiagram
    autonumber
    participant Cloud as Cloud capacity manager
    participant Agent as Worker/agent
    participant Queue as Task queue
    participant Store as Checkpoint/object store
    participant Next as Worker kế tiếp

    Cloud-->>Agent: Interruption notice (nếu có)
    Agent->>Agent: Mark not-ready; stop polling
    Agent->>Agent: Dừng task tại safe point
    opt Có đủ thời gian và checkpoint hợp lệ
        Agent->>Store: Ghi checkpoint/output tạm
        Store-->>Agent: Confirm durable write
    end
    alt Task hoàn tất an toàn
        Agent->>Queue: Ack task
    else Task chưa hoàn tất
        Agent->>Queue: Release lease / không ack
        Queue-->>Next: Redeliver khi lease hết hạn
        Next->>Store: Đọc checkpoint hợp lệ
        Store-->>Next: Resume hoặc chạy lại
    end
    Cloud->>Agent: Reclaim capacity
~~~

Thông báo thu hồi là **cơ hội để dừng có trật tự**, không phải giao kèo rằng ứng dụng luôn được chạy thêm một khoảng thời gian cố định. Hãy đọc đúng tài liệu của loại capacity đang dùng để biết tín hiệu được phát ở đâu, thời điểm và giới hạn nào.

### 6.2. Queue visibility timeout và lease

Nếu worker lấy message từ queue rồi bị thu hồi:

- Khi worker ack sau khi hoàn tất, message được đánh dấu xử lý theo semantics của queue.
- Nếu worker chết trước ack, message có thể xuất hiện lại khi visibility timeout/lease hết hạn.
- Nếu visibility timeout quá ngắn, task dài có thể bị giao đồng thời cho worker khác trong khi worker cũ vẫn chạy.
- Nếu quá dài, một worker đã chết làm task bị trì hoãn lâu trước khi có worker mới xử lý.

Với task có thời gian chạy biến thiên, có thể gia hạn visibility/lease theo heartbeat nếu queue hỗ trợ. Heartbeat phải phản ánh worker còn sống và tiến triển; không gia hạn vô hạn cho task bị treo. Worker cần idempotency vì lease không loại bỏ mọi trường hợp giao trùng.

### 6.3. Thời hạn dừng của container/orchestrator

Nếu spot VM là node của Kubernetes hoặc một container orchestrator, cần phân biệt:

- **VM/underlying node interruption:** node có thể biến mất; workload cần được reschedule ở node khác nếu có capacity.
- **Pod eviction/drain:** scheduler/orchestrator có thể cho Pod thời gian graceful termination, gửi tín hiệu dừng và chạy preStop/lifecycle hooks theo cấu hình.
- **Application shutdown:** process phải xử lý SIGTERM hoặc tín hiệu tương ứng, ngừng nhận task và đóng kết nối.

Không giả định thời gian graceful shutdown của Pod luôn dài hơn thời gian còn lại trước khi VM bị thu hồi. Cần dùng interruption handler/daemonset hoặc cơ chế managed của nền tảng (nếu có), rút node khỏi scheduling, drain trong ngân sách thời gian hợp lệ, và vẫn chấp nhận hard termination.

## 7. Đảm bảo capacity khi spot pool không sẵn có

Một lỗi thường gặp là scale toàn bộ hệ thống bằng spot capacity rồi ngạc nhiên khi nhu cầu tăng đúng lúc provider thiếu pool. Tài nguyên giá thấp không nên là **điều kiện duy nhất để hệ thống đạt tiến triển tối thiểu**.

### 7.1. Mô hình baseline + burst

Giữ một lượng capacity ổn định để duy trì mức xử lý tối thiểu, sau đó thêm spot worker khi pool có sẵn:

~~~mermaid
flowchart TB
    Q["Task queue / backlog"]
    AUTO["Scheduler / autoscaler"]
    BASE["Stable baseline<br/>On-demand"]
    SPOT["Elastic workers<br/>Spot capacity"]
    Q --> BASE
    Q --> SPOT
    AUTO --> BASE
    AUTO --> SPOT
    BASE --> DONE["Completed tasks"]
    SPOT --> DONE
    BACK["Spot pool unavailable / reclaimed"] --> AUTO
    AUTO -->|"Chuyển phần cần thiết sang stable capacity<br/>hoặc chấp nhận backlog theo SLO"| BASE
~~~

Nếu backlog tăng trong khi spot capacity biến mất, hệ thống có thể:

- Dùng phần baseline còn headroom.
- Bổ sung on-demand/regular capacity nếu quota và provider còn cấp được.
- Hạn chế nhận tác vụ không cấp bách hoặc điều chỉnh mức concurrency.
- Kéo dài deadline theo thỏa thuận nghiệp vụ đối với batch không khẩn cấp.

Phải xác định **SLO tiến triển tối thiểu**: ví dụ queue backlog không vượt một ngưỡng hoặc batch hoàn tất trước deadline. Nếu không có baseline đủ đáp ứng thì hãy nói rõ SLA của workload bị ảnh hưởng khi spot unavailable.

### 7.2. Đa dạng hóa pool

Chia workload qua nhiều khả năng capacity để giảm phụ thuộc một loại instance hoặc một pool:

- Nhiều instance family/size có khả năng chạy cùng image và ứng dụng.
- Nhiều Availability Zone trong phạm vi độ trễ và dữ liệu cho phép.
- Nhiều pool theo loại CPU/architecture hoặc accelerator khi workload hỗ trợ.
- Nhiều loại node group/launch template hoặc capacity offering, nhưng vẫn dùng cùng chuẩn security và observability.

Việc phân tán phải tương thích với ứng dụng. Chẳng hạn workload phụ thuộc GPU hoặc local NVMe có ít lựa chọn hơn; không thể thêm một pool loại máy không có accelerator rồi tính nó là capacity dự phòng tương đương.

**Capacity-optimized allocation** hoặc chiến lược chọn pool theo availability có thể giảm xác suất chọn nhóm thiếu capacity, tùy provider. Tuy vậy, diversification không loại bỏ rủi ro thu hồi đồng thời khi nhiều pool chịu cùng một áp lực thị trường hoặc lỗi vùng.

### 7.3. Đừng tự động scale vào cuộc đua giá

Không chọn pool chỉ vì giá spot hiện tại thấp nhất. Cần cân bằng:

- Xác suất pool có capacity trong thời điểm cần.
- Tỷ lệ interruption và ảnh hưởng tới tiến độ task.
- Hiệu năng/giá trên mỗi đơn vị công việc hoàn thành.
- Chi phí làm lại, checkpoint, retry và điều phối.
- Chi phí on-demand fallback và headroom cần giữ.

Giá rẻ theo giờ không nhất thiết có **chi phí trên một kết quả thành công** thấp. Một pool bị thu hồi liên tục làm task chạy lại nhiều lần có thể đắt hơn pool có giá cao hơn nhưng hoàn tất ổn định.

## 8. Autoscaling và quản lý hàng đợi

### 8.1. Scale theo nhu cầu thực

Với worker bất đồng bộ, CPU không phải lúc nào cũng là metric phù hợp nhất. Có thể scale dựa trên:

- Số message đang chờ (backlog).
- Tuổi của message lâu nhất (age of oldest message).
- Tốc độ message đến và tốc độ xử lý.
- Số task đang in-flight và thời gian xử lý trung bình.
- Mục tiêu thời gian hoàn tất batch/deadline.
- Capacity thực sự sẵn có trong mỗi pool.

Một quy tắc gần đúng:

`Số worker cần ≈ backlog / (throughput mục tiêu mỗi worker × thời gian cho phép để xử lý backlog)`

Đây chỉ là ước lượng khởi đầu; cần tính thêm task có độ dài khác nhau, overhead startup, concurrency limit, retry và quota. Scale dựa trên một snapshot backlog mà bỏ qua tốc độ tạo message có thể khiến hệ thống scale thiếu hoặc quá mức.

### 8.2. Tách logic retry khỏi autoscaling

Nếu task lỗi do dữ liệu độc hại hoặc bug, scale thêm worker chỉ làm tăng số lần lỗi. Cần phân loại:

| Loại lỗi | Phản ứng |
|---|---|
| Worker bị thu hồi | Cho task có thể retry trở lại queue/lease, tiếp tục từ checkpoint |
| Lỗi hạ tầng tạm thời | Retry có backoff, jitter và giới hạn |
| Dependency throttling | Giảm concurrency, áp dụng backpressure, retry theo chỉ dẫn dịch vụ |
| Input không hợp lệ / lỗi deterministic | Chuyển DLQ hoặc trạng thái failed để xử lý, không retry vô hạn |
| Task chạy quá lâu | Kiểm tra heartbeat/lease, giới hạn runtime, checkpoint hoặc chia nhỏ |
| Pool không có capacity | Dùng fallback, giữ backlog trong giới hạn SLO, phát cảnh báo |

DLQ cần có owner, retention, dashboard và quy trình replay sau khi khắc phục nguyên nhân. Không replay hàng loạt message gây hiệu ứng lặp tới hệ thống bên ngoài.

## 9. Bảo mật khi dùng compute có thể bị thu hồi

Việc máy biến mất không làm giảm nghĩa vụ bảo vệ dữ liệu. Worker có thể đang xử lý file khách hàng, token, dữ liệu phân tích hoặc secret.

### 9.1. Identity và quyền tối thiểu

- Mỗi worker/service role chỉ có quyền đọc object đầu vào, ghi output/checkpoint, nhận message hoặc publish trạng thái trong phạm vi cần thiết.
- Dùng workload identity/role ngắn hạn theo nền tảng khi có thể; tránh nhúng access key cố định vào image, user data hoặc script.
- Tách quyền của scheduler, node bootstrap, worker và người vận hành.
- Ghi audit các hành động nhạy cảm và giới hạn quyền replay DLQ.

### 9.2. Dữ liệu và disk

- Mã hóa dữ liệu trên đường truyền tới queue, object storage, database và dependency.
- Chọn mã hóa at-rest và quản lý key phù hợp; kiểm tra quyền worker truy cập key.
- Không để dữ liệu nhạy cảm duy nhất trên ephemeral disk.
- Khi kết thúc bình thường, xóa dữ liệu tạm theo chính sách; không coi thao tác xóa local là biện pháp duy nhất vì disk có thể mất đột ngột.
- Bảo vệ checkpoint/output chống sửa giả hoặc trộn dữ liệu giữa task/tenant; dùng path/key có namespace và kiểm tra quyền.

### 9.3. Supply chain và bootstrap

Worker thường được tạo tự động từ image. Image cần nguồn tin cậy, vá lỗi, quét lỗ hổng, ký/verify artifact nếu quy trình hỗ trợ, và không chứa secret. IaC/launch template phải được review như code; spot capacity không phải lý do để bỏ qua kiểm soát production.

## 10. Hiệu quả chi phí: tính theo công việc hoàn thành

Để so sánh capacity ổn định và spot, hãy dùng **cost per successful work unit**, thay vì chỉ xem giá mỗi giờ.

Một công thức phân tích:

~~~text
Tổng chi phí workload
  = compute cost
  + storage/checkpoint cost
  + network/egress cost
  + queue/observability cost
  + chi phí làm lại do interruption
  + chi phí on-demand fallback

Chi phí trên một task thành công
  = tổng chi phí workload / số task hoàn tất hợp lệ
~~~

Ví dụ giả định cho một batch 10.000 task:

| Khoản | Phương án capacity ổn định | Phương án spot-first |
|---|---:|---:|
| Compute chính | 100 đơn vị chi phí | 55 |
| Retry/checkpoint/storage | 3 | 9 |
| Capacity fallback | 0 | 12 |
| Quan sát/điều phối tăng thêm | 2 | 5 |
| **Tổng** | **105** | **81** |
| Task thành công | 10.000 | 10.000 |
| **Chi phí/task thành công** | **0,0105** | **0,0081** |

Các con số chỉ minh họa phương pháp tính. Trong thực tế, phải đo cùng loại công việc, cùng mức độ hoàn tất, cùng yêu cầu deadline và tính cả công sức vận hành. Nếu spot-first chỉ hoàn tất 8.000 task trong thời hạn, không thể coi nó rẻ hơn mà bỏ qua 2.000 task trễ.

Các metric cần thu:

- Spot interruption rate, số lần reclaim và nguyên nhân nếu provider cung cấp.
- Thời gian từ notice đến khi node dừng, tỷ lệ drain/checkpoint thành công.
- Số task retry, duplicate, thất bại, thời gian làm lại.
- Backlog/age, thời gian hoàn tất p50/p95/p99 và tỷ lệ đạt deadline.
- Tỷ lệ spot/on-demand, thời gian fallback, quota/capacity error.
- Chi phí compute, storage, data transfer, logging và chi phí trên mỗi task thành công.

## 11. Đánh giá bằng tư duy Well-Architected

| Góc nhìn | Câu hỏi khi đưa spot vào kiến trúc | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Khi worker bị thu hồi, alert đi đâu, task được trả lại thế nào, ai xử lý DLQ? | Runbook, interruption handler, dashboard, thử nghiệm chaos |
| **Security** | Worker có secret/data gì, quyền tới đâu, image được quản lý ra sao? | IAM least privilege, image scanning, audit, encryption và kiểm thử quyền |
| **Reliability** | Pool hết capacity hoặc bị thu hồi đồng loạt thì workload có tiếp tục không? | Baseline capacity, fallback, retry/checkpoint test, deadline/SLO |
| **Performance Efficiency** | Throughput/task latency có đạt khi pool đổi loại máy hoặc scale không? | Load test theo instance mix, backlog, p95 processing time, saturation |
| **Cost Optimization** | Cost per completed task có giảm sau khi tính interruption và fallback không? | Billing + work-unit metrics, retry cost, egress, storage |
| **Sustainability** | Có giảm thời gian compute nhàn rỗi và tránh chạy lại không cần thiết? | Utilization, checkpoint overhead, duplicate work, resource lifecycle |

Không đánh dấu một workload là “phù hợp spot” chỉ vì chi phí compute theo giờ thấp hơn. Phải chứng minh hệ thống chịu được **sự gián đoạn của chính compute pool** mà vẫn đạt yêu cầu nghiệp vụ.

## 12. Bài thực hành: thiết kế pool worker chịu interruption

Một nhóm dữ liệu cần xử lý 50.000 file ảnh mỗi đêm. Mỗi file mất trung bình 90 giây để resize và trích xuất metadata. Kết quả phải sẵn sàng trước 06:00. File gốc nằm trong object storage; metadata được ghi vào DB. Tải không tương tác trực tiếp với người dùng.

Nhóm đề xuất:

> “Chạy toàn bộ worker bằng spot VM để tiết kiệm tiền. Mỗi VM lấy file từ queue, xử lý rồi ghi vào DB. Nếu VM bị thu hồi, hệ thống tạo VM khác và người dùng không nhận ra.”

Hãy thiết kế lại bằng cách trả lời:

**Bài 1 — Phân loại workload.** Vì sao tải này có vẻ phù hợp với spot? Những điều kiện nào có thể khiến nó không còn phù hợp (deadline quá chặt, side effect không idempotent, data local)?

**Bài 2 — Xác định đơn vị task.** Mỗi file hay một batch file là đơn vị công việc? Đặt task ID, input version, output path và trạng thái hoàn thành như thế nào để retry không tạo kết quả sai?

**Bài 3 — Xử lý interruption.** Vẽ sequence từ nhận message đến xử lý, checkpoint, ghi output, ack. Thêm nhánh VM chết trước notice, sau checkpoint, và sau ghi output nhưng trước ack.

**Bài 4 — Capacity fallback.** Chọn baseline on-demand tối thiểu, số pool/zone/instance family và cách scale theo backlog/oldest-message-age. Khi spot không cấp được capacity, hệ thống làm gì để bảo vệ deadline?

**Bài 5 — Bảo mật.** Xác định role của worker, quyền object storage/DB/queue, secret, disk và log. Có cần đưa email hoặc dữ liệu cá nhân vào queue payload không?

**Bài 6 — Đo chi phí.** So sánh spot-first với capacity ổn định bằng cost per successfully processed file, có tính retry, checkpoint, fallback và số file trễ deadline.

### Khung câu trả lời mẫu

| Thành phần | Quyết định minh họa | Bằng chứng |
|---|---|---|
| Task | Một file + object version + processing config | Retry không tạo output trùng hoặc sai version |
| State | Queue + DB task status + checkpoint ở storage bền vững | Có thể khôi phục sau kill worker |
| Worker | Spot cho phần lớn throughput, baseline ổn định cho tiến triển tối thiểu | Queue age và deadline đạt khi spot mất |
| Shutdown | Stop polling, safe checkpoint, release/expire lease, không ack task dở | Thử interruption ở nhiều thời điểm |
| Security | Workload identity và quyền tối thiểu | Test deny ngoài phạm vi |
| Cost | Tính tổng chi phí / số file hoàn tất hợp lệ | Billing đối chiếu work-unit metrics |

## 13. Checklist trước khi chạy workload trên spot/preemptible capacity

- [ ] Đơn vị công việc nhỏ, có ID ổn định và có thể chạy lại.
- [ ] Trạng thái cần giữ được lưu ngoài VM/container có thể bị thu hồi.
- [ ] Output ghi theo cách an toàn, tránh dữ liệu dở dang bị coi là hoàn tất.
- [ ] Task có idempotency/deduplication và xử lý side effect lặp.
- [ ] Queue lease/visibility timeout, heartbeat, retry/backoff, DLQ và replay được thiết kế.
- [ ] Worker nhận interruption notice nếu có, ngừng polling và graceful shutdown trong giới hạn thực tế.
- [ ] Hệ thống vẫn hoạt động đúng khi VM chết **không có notice**.
- [ ] Có baseline capacity hoặc chính sách chấp nhận backlog/deadline rõ ràng khi spot unavailable.
- [ ] Pool được đa dạng hóa theo lựa chọn máy/zone mà workload thực sự hỗ trợ.
- [ ] Autoscaler dùng backlog/age/throughput và không khuếch đại lỗi deterministic.
- [ ] Quyền IAM, secrets, image, network, disk và log tuân thủ chính sách bảo mật.
- [ ] Đo interruption rate, retry, checkpoint overhead, work completion, SLO và cost per successful task.
- [ ] Có runbook, owner, quota/capacity fallback và bài diễn tập trước production.

Tài nguyên có thể bị thu hồi phát huy hiệu quả khi **công việc chịu được việc dừng giữa chừng** và hệ thống có thể tiếp tục từ trạng thái bền vững. Kết quả thiết kế tốt không phải là chạy được worker trên spot một lần, mà là vẫn hoàn thành đúng công việc, đúng quyền và trong giới hạn thời gian/chi phí khi compute bị thu hồi nhiều lần.
