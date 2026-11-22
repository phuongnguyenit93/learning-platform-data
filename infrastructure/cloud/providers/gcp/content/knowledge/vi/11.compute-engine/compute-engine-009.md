# Spot VMs và xử lý gián đoạn workload trên Compute Engine

Một doanh nghiệp thương mại điện tử xử lý ảnh sản phẩm, tạo báo cáo bán hàng và chạy các phép phân tích định kỳ. Những tác vụ này tốn CPU nhưng không phải lúc nào cũng phải hoàn thành ngay. Nhóm hạ tầng muốn giảm chi phí bằng cách dùng **Spot VMs** của Google Compute Engine thay cho VM tiêu chuẩn ở một phần hệ thống. Sau vài giờ vận hành, một VM đang xử lý lô dữ liệu bị thu hồi. Nếu job chỉ lưu kết quả trong bộ nhớ hoặc đĩa tạm, công việc có thể mất và phải bắt đầu lại.

Điểm mấu chốt của Spot VMs là **đổi khả năng bị gián đoạn để lấy mức giá tài nguyên hấp dẫn hơn**, không phải một loại VM luôn rẻ mà có cùng cam kết hoạt động như VM tiêu chuẩn. Muốn sử dụng hiệu quả, ứng dụng cần có khả năng nhận gián đoạn, lưu tiến độ, chạy lại an toàn, tránh xử lý trùng gây hỏng dữ liệu và duy trì đủ năng lực xử lý khi tài nguyên không sẵn có.

Bài học thuộc chương **Compute Engine**, mô-đun **CLOUD_PROVIDERS_GCP**. Nó kết nối cách lựa chọn tài nguyên với tổ chức project, IAM, VPC, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành và vận hành đáng tin cậy trong ngân sách. Trọng tâm là **Spot VM và kiến trúc chịu gián đoạn**, chứ không chỉ cú pháp tạo VM.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt Spot VM, VM tiêu chuẩn và mô hình preemptible VM cũ; biết khi nào nên hoặc không nên chọn Spot.
2. Giải thích sự kiện **preemption**, thông báo tắt máy ngắn và các kiểu termination action `STOP`/`DELETE`.
3. Thiết kế công việc theo hướng **idempotent**, có checkpoint và trạng thái được lưu bền vững bên ngoài VM.
4. Phân tách **hàng đợi công việc**, **worker có thể bị thu hồi** và **nơi lưu kết quả**.
5. Dùng `gcloud` để tạo, quan sát và điều tra Spot VM; hiểu vai trò của Managed Instance Groups (MIG).
6. Xây dựng chiến lược thay thế capacity, giám sát độ trễ hoàn thành và kiểm soát chi phí thực tế.

## 2. Spot VM là gì và khác VM tiêu chuẩn ra sao?

### 2.1. Provisioning model của Compute Engine

Compute Engine hỗ trợ các mô hình cấp phát VM khác nhau. Khi chọn **Spot**, workload chấp nhận rằng Google Cloud có thể **preempt** (thu hồi) VM khi cần tài nguyên, và VM không được bảo đảm tiếp tục chạy trong khoảng thời gian mong muốn.

| Khía cạnh | VM tiêu chuẩn | Spot VM |
| --- | --- | --- |
| Mục tiêu | Workload cần khả năng cấp phát và duy trì theo chính sách dịch vụ thông thường. | Workload chịu được việc VM bị thu hồi hoặc có thể trì hoãn. |
| Mức giá | Theo giá của mô hình cấp phát tiêu chuẩn và các lựa chọn giá phù hợp. | Giá Spot thấp hơn giá tiêu chuẩn tương ứng khi đủ điều kiện, có thể thay đổi theo bảng giá và điều kiện dịch vụ. |
| Gián đoạn do cần thu hồi capacity | Không có cơ chế thu hồi theo chính sách Spot. | Có thể bị thu hồi bất kỳ lúc nào, kể cả ngay sau khi khởi tạo. |
| Sẵn có tại một thời điểm | Vẫn phụ thuộc quota và khả năng cấp phát. | Phụ thuộc nhiều hơn vào capacity Spot tại zone/loại máy; có thể không tạo hoặc khởi động lại được. |
| Khả năng phù hợp | API quan trọng, database chính, dịch vụ khó gián đoạn. | Batch, xử lý dữ liệu chia nhỏ, build/test, worker có thể chạy lại, một phần ML training có checkpoint. |
| Xử lý sự cố | Thiết kế HA/backup vẫn cần thiết. | Phải thiết kế **preemption là tình huống bình thường**, không chỉ là lỗi hiếm gặp. |

Spot VM vẫn là **Compute Engine VM**: có machine type, image, boot disk, network interface, service account, firewall và metrics theo cấu hình. Điểm khác biệt chính nằm ở **chính sách provisioning và khả năng bị thu hồi**. Spot không tự khiến ứng dụng có tính năng retry, HA hoặc checkpoint.

### 2.2. Spot so với preemptible VM cũ

Google Cloud cũng có khái niệm **preemptible VM** từ mô hình trước đó. Cả hai đều có thể bị thu hồi, nhưng **Spot VMs không mang giới hạn thời gian chạy tối đa 24 giờ giống preemptible VM truyền thống**. Điều này không biến Spot thành máy được bảo đảm chạy lâu: một VM có thể chạy nhiều ngày hoặc bị thu hồi rất sớm.

Khi đọc tài liệu hoặc script cũ, không nhầm cờ `--preemptible` với cách chỉ định `--provisioning-model=SPOT`. Khi thiết kế hệ thống mới, chọn mô hình phù hợp với chính sách hiện tại của Google Cloud; đừng dựa vào thời gian VM đã chạy để đoán khi nào sẽ bị preempt.

### 2.3. Những workload phù hợp và không phù hợp

**Ứng viên tốt:**

- Xử lý hàng nghìn ảnh có thể chia thành các nhiệm vụ độc lập.
- Phân tích dữ liệu theo partition, có checkpoint hoặc có thể chạy lại.
- Build và test trong CI với artifact lưu bên ngoài worker.
- Worker nền lấy việc từ Pub/Sub/Cloud Tasks hoặc hàng đợi được quản lý.
- Một số bước xử lý dữ liệu/ML có thể lưu trạng thái và tiếp tục sau gián đoạn.

**Ứng viên cần cân nhắc kỹ hoặc thường không phù hợp:**

- Một VM duy nhất phục vụ API production có yêu cầu sẵn sàng cao.
- Cơ sở dữ liệu ghi chính lưu dữ liệu duy nhất trên ổ cục bộ của Spot VM.
- Công việc tương tác trực tiếp cần độ trễ dự đoán được và không có fallback.
- Job không chia nhỏ được, mất nhiều giờ làm lại mỗi lần bị gián đoạn.
- Hệ thống không có cơ chế chống ghi trùng, phục hồi hoặc theo dõi tiến độ.

Chọn Spot nên dựa trên **khả năng chịu gián đoạn của toàn luồng nghiệp vụ**, không chỉ nhìn vào CPU utilization và mức giảm giá.

## 3. Vòng đời Spot VM và sự kiện preemption

### 3.1. Sự khác nhau giữa STOP và DELETE

Spot VM có thể được cấu hình **instance termination action** để xác định điều gì xảy ra khi bị preempt:

| Termination action | Khi xảy ra preemption | Hệ quả cần quan tâm |
| --- | --- | --- |
| **`STOP`** | VM ngừng chạy, thường có trạng thái `TERMINATED`. | Tài nguyên VM và các disk còn tồn tại theo cấu hình; muốn có capacity trở lại phải khởi động/điều phối lại và vẫn có thể gặp thiếu capacity Spot. |
| **`DELETE`** | VM bị xóa sau preemption theo hành vi được hỗ trợ. | VM không còn; boot disk/đĩa có thể bị xóa nếu cấu hình auto-delete. Cần hạ tầng điều phối tạo instance thay thế nếu muốn tiếp tục công việc. |

Chú ý: `TERMINATED` trong Compute Engine có nghĩa **VM đã dừng**, không nhất thiết là bằng chứng đã bị preempt. VM có thể được người vận hành hoặc automation dừng thủ công. Khi điều tra, đối chiếu **sự kiện hệ thống**, cấu hình scheduling, operations và logs có sẵn thay vì suy nguyên nhân từ trạng thái.

Đối với cả hai lựa chọn, **memory, process và kết nối đang mở đều không được bảo đảm giữ lại**. Dữ liệu chưa được flush ra nơi lưu bền vững có thể mất. Ổ đĩa được giữ lại khi STOP không có nghĩa một quy trình đang chạy có thể tiếp tục từ đúng instruction đã dừng.

### 3.2. Những giới hạn scheduling đáng nhớ

Spot VM được cấu hình với provisioning model `SPOT`; các tùy chọn scheduling liên quan cần tương thích. Trong các ví dụ Google Cloud thường dùng:

~~~yaml
scheduling:
  provisioningModel: SPOT
  instanceTerminationAction: STOP
  automaticRestart: false
  onHostMaintenance: TERMINATE
~~~

Đây là **minh họa các thuộc tính** liên quan, không phải file cấu hình để gửi trực tiếp tới API. Spot VM không có cơ chế tự động restart kiểu VM tiêu chuẩn khi bị thu hồi. Có thể cần cơ chế điều phối bên ngoài (MIG, scheduler, job controller hoặc automation) để tạo/khởi chạy worker trở lại.

### 3.3. Thông báo tắt máy trước preemption

Khi preemption diễn ra, Compute Engine có thể gửi tín hiệu tắt máy qua guest OS và cố gắng dành **tối đa khoảng 30 giây** cho hoạt động shutdown theo cơ chế được hỗ trợ. Đây là **nỗ lực tối đa/best effort**, không phải bảo đảm ứng dụng luôn nhận đủ 30 giây hay hoàn thành shutdown script.

~~~mermaid
flowchart TD
    RUN["Spot VM đang xử lý job"] --> EVENT{"Compute Engine preempt VM?"}
    EVENT -- "Chưa" --> RUN
    EVENT -- "Có" --> NOTICE["Thông báo shutdown khi có thể"]
    NOTICE --> SAVE["Worker cố gắng dừng nhận việc, lưu checkpoint"]
    SAVE --> ACTION{"Termination action"}
    ACTION -- "STOP" --> STOP["VM dừng; điều phối capacity trở lại"]
    ACTION -- "DELETE" --> DEL["VM bị xóa; bộ điều phối có thể tạo VM khác"]
    STOP --> RESUME["Worker mới/được khởi động lại nhận việc còn dang dở"]
    DEL --> RESUME
    RESUME --> RUN
~~~

Vì thông báo có thể rất ngắn hoặc không đủ để chạy trọn quy trình, **checkpoint định kỳ trong lúc ứng dụng hoạt động** mới là cơ chế bảo vệ chính. Shutdown hook chỉ nên giúp giảm phần việc phải làm lại.

### 3.4. Lưu trữ nào còn sau gián đoạn?

| Nơi chứa trạng thái | Sau STOP/preemption | Khuyến nghị |
| --- | --- | --- |
| **RAM / process memory** | Mất trạng thái chạy. | Không dùng làm nguồn duy nhất của tiến độ. |
| **Local SSD hoặc vùng dữ liệu tạm** | Dữ liệu có thể mất khi VM bị dừng/preempt theo hành vi của loại lưu trữ. | Chỉ dùng cho cache/scratch; dữ liệu có giá trị phải được lưu nơi bền vững. |
| **Persistent Disk / Hyperdisk phù hợp** | Có thể được giữ khi VM STOP, theo cấu hình disk. | Kiểm tra lifecycle/attachment; không phụ thuộc vào một VM duy nhất cho job cần tái phân phối. |
| **Disk có auto-delete khi VM bị xóa** | Có thể bị xóa cùng instance. | Không lưu kết quả duy nhất trong boot disk tự xóa. |
| **Cloud Storage, database, dịch vụ hàng đợi** | Có vòng đời tách khỏi VM theo cấu hình dịch vụ. | Phù hợp lưu input/output/checkpoint và trạng thái công việc. |

**Không phải cứ dùng Persistent Disk là đủ:** VM có thể bị `DELETE`, disk có thể auto-delete, hoặc worker khác cần đọc dữ liệu qua đường khác. Cần định nghĩa rõ **nơi lưu trạng thái có tính bền vững, quyền truy cập, phiên bản/checkpoint và quy trình phục hồi**.

## 4. Kiến trúc một worker có thể bị thu hồi

### 4.1. Tách ba thành phần

Một mô hình chịu preemption đơn giản:

~~~mermaid
flowchart LR
    P["Ứng dụng tạo job"] --> Q["Pub/Sub / hàng đợi công việc"]
    Q --> W1["Spot VM worker A"]
    Q --> W2["Spot VM worker B"]
    W1 --> D["Cloud Storage / Cloud SQL: checkpoints và kết quả"]
    W2 --> D
    W1 -. "Bị preempt" .-> X["Worker biến mất"]
    Q -. "Job chưa xác nhận xử lý xong" .-> W2
    M["Monitoring / alerting"] -. "Theo dõi backlog và lỗi" .-> Q
    M -.-> W1
    M -.-> W2
~~~

1. **Queue** giữ thông tin về những công việc cần làm, cung cấp cơ chế giao việc và phát lại khi thích hợp.
2. **Spot VM worker** nhận job, tính toán và có thể bị thay thế bất kỳ lúc nào.
3. **Durable store** lưu input, checkpoint và kết quả đã commit; không gắn chặt vào vòng đời của VM.

Đối với công việc quan trọng, cần xác định cách hàng đợi quản lý **acknowledgment, lease/visibility timeout, retry và dead-letter**. Chọn **Pub/Sub** hay **Cloud Tasks** tùy mô hình: Pub/Sub phù hợp sự kiện/phân phối message, Cloud Tasks phù hợp nhiều bài toán điều phối tác vụ HTTP với retry/định nhịp. Một scheduler như **Cloud Batch** cũng có thể giúp vận hành những batch job trên VM; không phải tự viết toàn bộ worker scheduler.

### 4.2. Tách worker khỏi trạng thái

Ví dụ một job:

~~~json
{
  "job_id": "image-batch-2026-001",
  "object_uri": "gs://retail-inputs/images/item-8842.jpg",
  "output_uri": "gs://retail-results/images/item-8842.webp",
  "attempt": 1
}
~~~

Worker nhận metadata rồi đọc file nguồn từ Cloud Storage. Nếu VM bị thu hồi, hàng đợi hoặc scheduler có thể cho một worker khác xử lý lại cùng `job_id`. Thông tin đầu vào đủ để tái dựng công việc, không phụ thuộc vào đường dẫn tạm trên VM cũ.

Trường `attempt` trong JSON chỉ là ví dụ nghiệp vụ, **không phải một trường chuẩn bắt buộc của Pub/Sub**. Nếu cần đếm số lần thực thi, ứng dụng/scheduler phải có cơ chế quản lý phù hợp.

### 4.3. Idempotency là điều kiện sống còn

Một job được gọi là **idempotent** khi thực thi lại không tạo tác động sai so với việc thực hiện một lần theo ngữ nghĩa nghiệp vụ. Với Spot, job có thể được chạy hai lần nếu:

- Worker cũ ghi kết quả thành công nhưng bị preempt trước khi gửi ack.
- Worker xử lý chậm hơn thời hạn lease, khiến scheduler giao lại công việc.
- Người vận hành chủ động retry sau lỗi mạng mà không biết bước commit đã thành công chưa.

**Mẫu không an toàn:**

~~~text
Nhận message → trừ tiền khách hàng → ghi ảnh → ack

Nếu bị preempt sau "trừ tiền" nhưng trước ack:
  message bị phát lại → khách hàng có thể bị trừ tiền lần hai.
~~~

**Mẫu tốt hơn:**

~~~text
Nhận message(job_id cố định)
  → kiểm tra job_id đã commit chưa
  → xử lý input
  → lưu kết quả theo khóa ổn định, sử dụng điều kiện ghi/transaction khi cần
  → đánh dấu job_id COMPLETED trong durable store
  → ack message

Nếu nhận lại cùng job_id:
  → phát hiện đã COMPLETED
  → không lặp side effect
  → ack an toàn
~~~

Khi có **nhiều hệ thống đích** (ví dụ vừa ghi Cloud SQL, vừa gọi API thanh toán), chỉ kiểm tra `COMPLETED` trước khi xử lý vẫn có thể gặp race condition. Cần thiết kế **unique constraint, transaction, idempotency key** hoặc outbox/saga theo đặc tính nghiệp vụ. Đừng coi việc dùng Pub/Sub là bảo đảm toàn bộ hệ thống “exactly once”.

## 5. Checkpoint và phục hồi tiến độ

### 5.1. Checkpoint là gì?

**Checkpoint** là trạng thái đủ để tiếp tục công việc từ một mốc nhất quán, thay vì chạy lại từ đầu. Với xử lý file lớn, checkpoint có thể lưu danh sách partition đã hoàn thành. Với huấn luyện mô hình, checkpoint có thể chứa trọng số model, optimizer state và thông tin tiến độ phù hợp. Với ETL, checkpoint có thể là offset, watermark hoặc khóa bản ghi cuối đã commit.

~~~text
Input 100 partitions

0 ───── 20 ───── 40 ───── 60 ───── 80 ───── 100
                ^
           checkpoint đã commit: 40

VM bị preempt khi đang xử lý partition 47:
  worker khác bắt đầu từ checkpoint 40,
  kiểm tra kết quả đã commit trước khi xử lý lại.
~~~

Mất nhiều nhất một phần nhỏ công việc kể từ checkpoint giúp giảm chi phí thực thi lại, nhưng checkpoint quá thường xuyên cũng tốn I/O và thời gian.

### 5.2. Chọn chu kỳ checkpoint

Một bài toán đánh đổi:

| Checkpoint quá thưa | Checkpoint quá dày |
| --- | --- |
| Ít overhead lưu trạng thái. | Thời gian ghi/checkpoint nhiều hơn. |
| Khi bị preempt có thể mất nhiều công việc. | Giảm lượng công việc phải làm lại. |
| Recovery chậm nếu job dài. | Dễ tăng chi phí lưu trữ, API calls hoặc database writes. |

Ví dụ job thường chạy 60 phút nhưng việc checkpoint chỉ mất 2 giây: có thể bắt đầu thử nghiệm lưu tiến độ mỗi 2–5 phút rồi đo overhead và lượng công việc bị làm lại. Những số này **chỉ minh họa chiến lược thử nghiệm**, không phải tần suất tối ưu cho mọi workload.

Điều quan trọng hơn con số là checkpoint phải **nhất quán**. Nếu ghi “partition 40 đã xong” trước khi dữ liệu partition 40 thực sự được lưu đầy đủ, worker sau có thể bỏ sót kết quả.

### 5.3. Lưu checkpoint an toàn

Cách tổ chức khuyến nghị:

1. Ghi kết quả trung gian đến một vị trí/phiên bản riêng, chẳng hạn object tạm hoặc record transaction.
2. Chỉ sau khi kết quả được lưu thành công mới **commit checkpoint** sang trạng thái “đã hoàn thành”.
3. Dùng object generation preconditions, unique key hoặc transaction khi có nhiều worker cạnh tranh.
4. Xác minh checkpoint có schema/version phù hợp với phiên bản code đang chạy.
5. Giữ thông tin input, code version, output checksum và thời điểm để có thể audit.

Ví dụ cấu trúc metadata:

~~~json
{
  "job_id": "daily-sales-2026-11-19",
  "checkpoint_version": 3,
  "completed_partitions": ["p00", "p01", "p02"],
  "input_manifest_uri": "gs://retail-inputs/manifests/2026-11-19.json",
  "output_prefix": "gs://retail-results/daily/2026-11-19/",
  "worker_release": "sales-etl-1.8.0",
  "state": "RUNNING"
}
~~~

Đây là **schema tự thiết kế**, không phải API response của Google Cloud. Khi có nhiều worker, một bản JSON trong Cloud Storage chỉ đủ an toàn nếu cơ chế cập nhật đồng thời được thiết kế; nếu không, hai worker có thể ghi đè checkpoint của nhau.

### 5.4. Ví dụ bảo vệ commit bằng Cloud SQL

Giả sử mỗi job có một kết quả cuối cùng lưu trong PostgreSQL trên Cloud SQL:

~~~sql
CREATE TABLE batch_results (
    job_id TEXT PRIMARY KEY,
    output_uri TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ví dụ idempotent commit: không tạo thêm bản ghi nếu job_id đã tồn tại.
INSERT INTO batch_results (job_id, output_uri)
VALUES ('image-batch-2026-001', 'gs://retail-results/images/item-8842.webp')
ON CONFLICT (job_id) DO NOTHING;
~~~

Primary key tránh ghi hai bản ghi cho cùng một job, nhưng **không tự xác nhận nội dung object đầu ra đúng**. Nếu cùng job_id bị chạy với hai thuật toán/đầu vào khác nhau, cần quy định cách kiểm tra manifest, checksum và xử lý xung đột. Nếu ghi object trước rồi commit SQL, vẫn phải xử lý tình huống SQL transaction thất bại và object tạm tồn tại; nên có chiến lược cleanup/garbage collection.

## 6. Shutdown scripts: hữu ích nhưng không đủ

### 6.1. Mục tiêu thực tế

Khi được báo sắp tắt, worker nên ưu tiên:

1. Ngừng **nhận job mới**.
2. Đánh dấu trạng thái đang dừng nếu kịp và cơ chế coordinator hỗ trợ.
3. Flush checkpoint đã gần hoàn thành hoặc trạng thái nhỏ cần thiết.
4. Đóng kết nối/ghi log mức vừa đủ, không khởi động tác vụ dài.

Không nên chờ một công đoạn upload nhiều gigabyte đến khi VM bắt đầu shutdown. Shutdown có thể xảy ra mà không có đủ thời gian, và script có thể bị kết thúc trước khi hoàn thành.

### 6.2. Ví dụ shutdown script minh họa

Đây là một đoạn Bash có thể dùng làm **nội dung metadata shutdown-script**, nhưng cần tùy biến đường dẫn, service và phương án lưu trạng thái thực tế:

~~~bash
#!/usr/bin/env bash
set -u

# Chỉ minh họa: ứng dụng phải được thiết kế tự checkpoint từ trước.
logger -t spot-worker "Shutdown requested: stop taking new jobs"

# Nếu worker có signal handler, yêu cầu service dừng nhận công việc.
# Không giả định systemctl hoặc service này có sẵn trên mọi image.
systemctl stop retail-batch-worker.service || true

logger -t spot-worker "Shutdown hook finished (best effort)"
~~~

Với Linux VM có guest environment phù hợp, Compute Engine hỗ trợ startup/shutdown scripts qua metadata. **Script trên không đảm bảo save checkpoint**; nó chỉ minh họa việc yêu cầu worker dừng theo trình tự. Cần timeout chặt cho shutdown hook, và worker phải tự lưu tiến độ định kỳ hoặc xử lý tín hiệu dừng theo cách có thể kiểm thử.

### 6.3. Tại sao không dùng shutdown hook làm nguồn sự thật?

Những tình huống có thể xảy ra:

- Worker đang bận CPU hoặc network, không kịp phản hồi.
- VM bị lỗi hoặc bị thu hồi quá nhanh để hook thực thi đầy đủ.
- Kết nối tới Cloud Storage/Cloud SQL gặp sự cố đúng lúc cần flush.
- Script viết được trạng thái “đã hoàn thành” nhưng dữ liệu output chưa commit.

Nguồn sự thật phải là **durable checkpoint và kết quả giao dịch nhất quán**, không phải “shutdown script đã chạy” hay một dòng log cuối cùng của VM.

## 7. Tạo và quan sát Spot VM bằng gcloud

Các lệnh dưới đây dùng những giá trị minh họa. **Lệnh có `create`, `start`, `stop`, `delete` làm thay đổi tài nguyên thật và có thể phát sinh chi phí**; chỉ chạy trong project/zone được phép. Mẫu sử dụng Bash, còn trên PowerShell cần thay cách khai báo biến và dấu nối dòng.

### 7.1. Kiểm tra context trước khi tạo

~~~bash
# READ-ONLY: kiểm tra project/tài khoản.
gcloud config get-value project
gcloud auth list

# READ-ONLY: xem các instance hiện có.
gcloud compute instances list \
  --project=retail-lab
~~~

Nếu đã có VPC riêng, chỉ định network/subnet và service account theo thiết kế. Tránh dựa vào default VPC hoặc default Compute Engine service account khi workload cần quyền truy cập dữ liệu production.

### 7.2. Tạo Spot VM đơn lẻ

~~~bash
# WRITE: tạo VM để thử nghiệm, thông số minh họa.
gcloud compute instances create spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-2 \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB
~~~

Cú pháp có thể thay đổi theo phiên bản CLI, machine type và khả năng hỗ trợ tại zone. Nếu dự án có chính sách không cấp public IP, hãy thêm cấu hình network thích hợp và kiểm tra **Private Google Access**, Cloud NAT hoặc đường egress cần thiết cho package updates và Google APIs. Đừng cấp external IP rộng chỉ để thuận tiện chạy thử.

Các cờ quan trọng:

| Cờ | Ý nghĩa |
| --- | --- |
| `--provisioning-model=SPOT` | Yêu cầu cấp phát VM theo mô hình Spot. |
| `--instance-termination-action=STOP` | Giữ VM ở trạng thái dừng khi preemption theo chính sách hỗ trợ. |
| `--maintenance-policy=TERMINATE` | Chọn hành vi guest khi có sự kiện bảo trì host tương ứng; phù hợp yêu cầu Spot. |
| `--no-restart-on-failure` | Không bật automatic restart theo mô hình VM tiêu chuẩn. |
| `--machine-type` và `--zone` | Quyết định tài nguyên và vị trí cấp phát; ảnh hưởng giá và capacity. |

Lệnh tạo thành công không phải bảo đảm Spot VM sẽ tiếp tục chạy đủ thời gian để hoàn thành job.

### 7.3. Kiểm tra VM sau khi tạo

~~~bash
# READ-ONLY: xem trạng thái và thông số scheduling.
gcloud compute instances describe spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,zone,machineType,scheduling,disks)"

# READ-ONLY: liệt kê các VM có provisioning model Spot.
gcloud compute instances list \
  --project=retail-lab \
  --filter="scheduling.provisioningModel=SPOT" \
  --format="table(name,zone.basename(),status,scheduling.provisioningModel)"
~~~

Những câu lệnh chỉ đọc trạng thái hiện tại. Để biết một instance bị preempt vào lúc nào, xem thêm **Cloud Logging system event/audit logs** và operations tương ứng nếu được ghi/giữ lại. Một VM `TERMINATED` không cho biết chắc đã do preemption, stop thủ công hay nguyên nhân khác.

### 7.4. Cấu hình DELETE khi điều phối chủ động

Với một worker thuần tính toán, output đã lưu bên ngoài VM, mô hình **`DELETE`** có thể phù hợp hơn `STOP`:

~~~bash
# WRITE: một Spot VM mới có thể bị xóa khi preempt.
gcloud compute instances create spot-worker-ephemeral \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-2 \
  --provisioning-model=SPOT \
  --instance-termination-action=DELETE \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --image-family=debian-12 \
  --image-project=debian-cloud
~~~

**Hãy đặc biệt kiểm tra auto-delete của boot disk/attached disks**. Dữ liệu quan trọng không được phụ thuộc vào việc VM hoặc disk sẽ còn sau preemption. Nếu cần VM mới tự xuất hiện sau khi instance bị xóa, phải có **scheduler/MIG/automation** phù hợp; riêng lựa chọn `DELETE` không tự tạo replacement.

## 8. Managed Instance Groups với Spot workers

### 8.1. Vì sao MIG hữu ích?

**Managed Instance Group (MIG)** quản lý một tập VM theo **instance template**. Nhóm có thể sử dụng cơ chế tái tạo instance/duy trì số lượng mục tiêu, autoscaling và các tính năng phù hợp với loại MIG. Khi dùng Spot VMs:

- VM có thể bị preempt và không còn phục vụ.
- MIG có thể cố gắng **tạo lại/duy trì số lượng VM** theo cấu hình.
- Việc tạo lại **không chắc thành công ngay**, vì capacity Spot ở zone hoặc machine type có thể không đủ.
- Một worker mới phải lấy lại công việc từ hàng đợi/checkpoint; không giả định MIG phục hồi tiến trình cũ.

**MIG bảo vệ capacity ở mức cố gắng điều phối, không biến Spot thành tài nguyên có cam kết sẵn có như VM tiêu chuẩn.**

### 8.2. Tạo instance template cho Spot

Ví dụ dưới đây minh họa cấu hình Spot worker với termination action `DELETE` để nhóm có thể thay thế VM khi cần. Các lệnh tạo tài nguyên thật:

~~~bash
# WRITE: template dùng cho Spot workers.
gcloud compute instance-templates create retail-spot-worker-template \
  --project=retail-lab \
  --machine-type=e2-standard-2 \
  --provisioning-model=SPOT \
  --instance-termination-action=DELETE \
  --maintenance-policy=TERMINATE \
  --no-restart-on-failure \
  --image-family=debian-12 \
  --image-project=debian-cloud

# WRITE: zonal MIG có mục tiêu hai worker.
gcloud compute instance-groups managed create retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --template=retail-spot-worker-template \
  --size=2
~~~

Một thiết kế production cần bổ sung **startup process, service account quyền tối thiểu, networking, health policy, logs/metrics và phương án xử lý job an toàn**. Nếu worker sử dụng `systemd`, startup script hoặc container image, đảm bảo phiên bản khởi tạo nhất quán và không lưu credential trong instance template.

### 8.3. Quan sát MIG

~~~bash
# READ-ONLY: trạng thái và cấu hình MIG.
gcloud compute instance-groups managed describe retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a

# READ-ONLY: danh sách instances do nhóm quản lý.
gcloud compute instance-groups managed list-instances retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

Nếu MIG báo số lượng hiện hữu nhỏ hơn mục tiêu, cần xem operations/errors, quota và năng lực cấp phát. **Không giả định tăng target size từ 2 lên 10 sẽ có ngay 10 VM Spot**.

### 8.4. Zonal hay regional MIG?

| Lựa chọn | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| **Zonal MIG** | Cấu hình đơn giản, phù hợp workload thử nghiệm hoặc job có khả năng chạy lại. | Phụ thuộc capacity của một zone; gián đoạn có thể ảnh hưởng phần lớn worker. |
| **Regional MIG** | Có thể phân bổ VM giữa nhiều zone theo chiến lược nhóm. | Cấu hình/capacity phức tạp hơn; không bảo đảm Spot luôn đủ ở mọi zone. |
| **Nhóm Spot + nhóm on-demand** | Giữ một phần năng lực xử lý ổn định, dùng Spot cho phần tăng thêm. | Cần điều phối load, quota và mục tiêu chi phí/SLO rõ ràng. |

Chọn chiến lược phân phối VM của regional MIG theo những tính năng được hỗ trợ tại thời điểm triển khai. Với hệ thống có deadline, **capacity nền bằng VM tiêu chuẩn** hoặc một cơ chế xử lý fallback thường đáng tin cậy hơn việc phụ thuộc 100% vào Spot.

## 9. Spot VM trong GKE và lựa chọn thay thế

### 9.1. GKE Spot node pools

GKE có thể sử dụng **Spot VMs làm worker nodes** theo cấu hình node pool phù hợp. Kubernetes workload chạy trên những node này vẫn có thể bị gián đoạn khi node bị preempt. Vì vậy cần:

1. Chỉ đưa những Pod chịu gián đoạn vào Spot nodes.
2. Dùng **node labels, taints/tolerations, affinity** hoặc các cơ chế scheduling hỗ trợ để đặt đúng workload.
3. Chia job thành những đơn vị có thể chạy lại; dùng **Kubernetes Jobs** hoặc queue worker phù hợp.
4. Đảm bảo ứng dụng xử lý `SIGTERM`, termination grace và lưu checkpoint ngoài Pod/node.
5. Theo dõi số nodes/pods khả dụng, Pending Pods và khả năng cấp phát lại.

Một Pod có **PersistentVolume** không tự bảo đảm an toàn nếu dữ liệu cuối cùng được ghi vào `emptyDir`, filesystem container hoặc memory. Cũng cần xem StorageClass, quyền truy cập và khả năng volume được tái gắn theo kiến trúc.

### 9.2. Không nhầm Spot VM với Cloud Run

Cloud Run là mô hình serverless mà người dùng **không chọn Spot provisioning model cho VM underlying** theo cách tạo Compute Engine Spot VM. Nếu workload là một HTTP API cần scale theo requests, Cloud Run có thể là lựa chọn tốt hơn về vận hành; nhưng không thể coi nó chỉ đơn giản là “Spot VM không phải quản lý”.

Với batch job, có thể xem xét **Cloud Batch**, **GKE Jobs**, Compute Engine MIG hoặc kiến trúc worker dùng Pub/Sub. Quyết định phụ thuộc vào mức độ chịu gián đoạn, cách đóng gói công việc, thời gian chạy, hỗ trợ GPU, tính di động và khả năng quản trị.

### 9.3. Bảng chọn công cụ

| Nhu cầu | Phương án nên khảo sát | Điều cần kiểm chứng |
| --- | --- | --- |
| Chạy một script thử nghiệm có thể làm lại. | Một Compute Engine Spot VM. | Trạng thái output và cách khởi chạy lại. |
| Hàng nghìn job độc lập, có checkpoint. | Cloud Batch hoặc queue + Spot worker/MIG. | Retry, concurrency, quota, capacity và checkpoint. |
| Job đã đóng gói thành container trong cụm Kubernetes. | GKE Job trên Spot node pool khi thích hợp. | Placement, Pod lifecycle, volume và tái lập lịch. |
| Dịch vụ HTTP stateless với yêu cầu vận hành đơn giản. | Cloud Run hoặc VM tiêu chuẩn/MIG theo SLO. | Không giả định Cloud Run dùng Spot theo ý người tạo. |
| Database giao dịch chính. | Dịch vụ database được quản lý như Cloud SQL hoặc kiến trúc HA phù hợp. | RPO/RTO, durability, backup, restore và SLO. |

## 10. Tính kinh tế: giá rẻ chưa chắc tổng chi phí thấp

### 10.1. Công thức suy nghĩ đơn giản

Giả sử một job cần 100 đơn vị công việc tính toán nếu không bị gián đoạn:

~~~text
Tổng chi phí thực tế
  ≈ Chi phí thời gian Spot VM chạy
   + Chi phí chạy lại phần việc bị mất
   + Chi phí checkpoint / durable storage / queue
   + Chi phí mạng, logs và điều phối
   + Chi phí capacity tiêu chuẩn dự phòng (nếu có)
~~~

Đây là **mô hình phân tích**, không phải công thức Billing chính thức. Khi so sánh Spot với VM tiêu chuẩn, dùng số liệu:

- Đơn giá theo machine type, zone, cấu hình disk và thời điểm hiện hành.
- Tỷ lệ job hoàn thành, tỷ lệ bị thu hồi, thời gian làm lại và checkpoint overhead.
- Chi phí Cloud Storage/Cloud SQL/Pub/Sub, logs, data transfer và orchestration.
- Số worker trung bình, mức dư capacity, lịch chạy và deadline nghiệp vụ.

Một công việc tiêu tốn 30 phút tính toán nhưng liên tục bị preempt ở phút thứ 29 và phải làm lại từ đầu có thể có **chi phí trên mỗi kết quả hoàn thành** cao, bất kể giá mỗi giờ Spot thấp.

### 10.2. Ví dụ so sánh có điều kiện

Giả sử:

| Thông số | Phương án A: không checkpoint | Phương án B: checkpoint định kỳ |
| --- | --- | --- |
| Thời gian xử lý lý tưởng | 60 phút | 60 phút |
| Khi bị thu hồi ở phút 45 | Phải chạy lại từ đầu. | Có thể tiếp tục từ checkpoint phút 40. |
| Phần việc mất | Khoảng 45 phút. | Khoảng 5 phút, chưa tính overhead. |
| Chi phí lưu trạng thái | Thấp hơn. | Có thêm I/O và lưu trữ. |
| Độ tin cậy hoàn thành | Phụ thuộc một khoảng chạy dài liên tục. | Tốt hơn khi worker thay thế được cấp lại. |

Số liệu chỉ minh họa một tình huống, không phải thống kê preemption trên Google Cloud. Phần việc tiết kiệm được phải được so với chi phí checkpoint thực đo.

### 10.3. Deadline và tỷ lệ Spot/on-demand

Một kiến trúc thực tế có thể chia queue:

~~~text
Job có deadline sát / nhiệm vụ cần capacity ổn định
    → worker tiêu chuẩn hoặc dịch vụ được quản lý phù hợp

Job linh hoạt, có thể chia nhỏ, đủ checkpoint
    → Spot workers

Queue tồn đọng hoặc thiếu Spot capacity quá lâu
    → trigger fallback có kiểm soát theo ngân sách/SLO
~~~

Đây là nguyên tắc quản trị **thời gian hoàn thành**. Tăng Spot lên 100% chỉ để tối thiểu giá một đơn vị CPU có thể làm tăng chi phí kinh doanh nếu các job quan trọng không kịp hạn.

## 11. Giám sát preemption và chất lượng xử lý

### 11.1. Hai nhóm chỉ số phải theo dõi

**Sức khỏe tài nguyên:**

- Số Spot VM đang chạy, bị dừng, bị xóa hoặc chưa cấp phát thành công.
- Các sự kiện preemption/system events có sẵn trong Cloud Logging.
- Các lần MIG tạo lại VM không thành công, cảnh báo quota hoặc thiếu capacity.
- CPU/memory/disk/network metrics theo công cụ giám sát được cấu hình.

**Sức khỏe nghiệp vụ:**

- Queue backlog và thời gian chờ của job lâu nhất.
- Tỷ lệ job hoàn thành trong deadline.
- Số lần thử trung bình, tỷ lệ retry và phần việc bị mất do preemption.
- Tuổi checkpoint gần nhất, thời gian phục hồi và số job cần can thiệp.
- Tỷ lệ output trùng, lỗi ghi commit, lỗi không idempotent hoặc sai kết quả.

Một MIG có hai VM Spot đang chạy nhưng queue tồn đọng hàng giờ **không đủ để kết luận hệ thống khỏe**. Ưu tiên SLI phản ánh kết quả thật, chẳng hạn “95% ảnh sản phẩm được xử lý trong 10 phút sau khi tải lên”.

### 11.2. Phân biệt lỗi capacity với lỗi ứng dụng

| Hiện tượng | Giả thuyết ban đầu | Hướng điều tra |
| --- | --- | --- |
| VM bị `TERMINATED` bất ngờ. | Preemption, stop thủ công hoặc lỗi khác. | Xem system event, operations, scheduling và audit logs. |
| MIG không đạt target size. | Thiếu Spot capacity, quota, policy hoặc template lỗi. | Xem MIG errors/operations, machine type, zone và quota. |
| Worker chạy nhưng job được xử lý lặp. | Ack muộn, lease hết hạn, worker chết sau commit. | Kiểm tra idempotency key, transaction/commit và retry logic. |
| Checkpoint có nhưng job không tiếp tục. | Schema thay đổi, checksum sai, checkpoint chưa commit an toàn. | Kiểm tra version, input manifest, dữ liệu và logs. |
| Job bị mắc kẹt mãi sau preemption. | Không có cơ chế giao lại việc, ack quá sớm hoặc lease không hết. | Kiểm tra queue, scheduler và trạng thái công việc bền vững. |
| Chi phí tăng dù dùng Spot. | Rework lớn, overprovision, logging/network/PD hoặc fallback không kiểm soát. | Xem Billing, completion cost và tài nguyên tồn tại sau STOP. |

### 11.3. Quan sát bằng gcloud

~~~bash
# READ-ONLY: trạng thái Spot VMs hiện có.
gcloud compute instances list \
  --project=retail-lab \
  --filter="scheduling.provisioningModel=SPOT" \
  --format="table(name,zone.basename(),status)"

# READ-ONLY: xem thông tin scheduling/termination action một VM.
gcloud compute instances describe spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(status,scheduling)"

# READ-ONLY: xem trạng thái quản lý của MIG.
gcloud compute instance-groups managed list-instances retail-spot-workers \
  --project=retail-lab \
  --zone=asia-southeast1-a
~~~

Với lịch sử preemption, xem **Cloud Logging System Event logs** theo tên project, instance ID, thời gian và cấu hình log; ví dụ sự kiện liên quan tới preemption được Google Cloud ghi nhận khi hỗ trợ. Các quy tắc retention, quyền đọc logs và schema có thể khác theo loại sự kiện, nên không tự suy rằng không thấy log đồng nghĩa VM chưa từng bị preempt.

### 11.4. Cảnh báo tốt hơn cảnh báo từng VM đơn lẻ

Một Spot VM bị thu hồi là sự kiện **dự kiến**. Không nhất thiết tạo cảnh báo khẩn mỗi lần có preemption. Những cảnh báo có ích hơn là:

- Queue backlog vượt ngưỡng theo SLO.
- Không đủ worker trong một khoảng thời gian ảnh hưởng deadline.
- Tỷ lệ job thất bại liên tiếp hoặc retry vượt giới hạn.
- Checkpoint không cập nhật trong khoảng thời gian dài.
- Dự trù chi phí hoặc fallback đạt ngưỡng ngân sách.

Tách cảnh báo **kỹ thuật** (VM thiếu capacity) và **nghiệp vụ** (job quá hạn) giúp đội vận hành tập trung vào tác động thật, tránh cảnh báo nhiễu.

## 12. Tình huống triển khai: xử lý ảnh sản phẩm

### 12.1. Yêu cầu

Một nền tảng bán lẻ cần xử lý khoảng hàng trăm nghìn ảnh mỗi ngày:

- Ảnh nguồn lưu trong một **Cloud Storage bucket**.
- Một dịch vụ **Cloud Run** nhận yêu cầu tạo job và ghi metadata vào hàng đợi.
- **Compute Engine Spot VMs** chạy chương trình chuyển định dạng ảnh.
- **Cloud SQL** lưu trạng thái nghiệp vụ và đường dẫn ảnh đầu ra.
- Một số dịch vụ liên quan dùng **GKE** cho pipeline phân tích.
- Mục tiêu: phần lớn ảnh xử lý kịp hạn, có thể chịu worker bị thu hồi mà không làm mất ảnh hoặc tạo bản ghi trùng.

Spot VMs cần chỉ đọc ảnh nguồn, ghi output/checkpoint theo prefix đã cấp và cập nhật job status theo quyền IAM tối thiểu. Không cấp role project Editor chỉ để worker có thể truy cập Cloud Storage.

### 12.2. Thiết kế đề xuất

~~~mermaid
flowchart TD
    CLIENT["Người quản lý sản phẩm upload ảnh"] --> GCSIN["Cloud Storage: input"]
    CLIENT --> API["Cloud Run: tạo job_id"]
    API --> Q["Queue: job metadata"]
    API --> SQL["Cloud SQL: job state"]
    Q --> MIG["MIG / scheduler quản lý Spot workers"]
    MIG --> W["Worker VM: process one image"]
    W --> GCSIN
    W --> TMP["Cloud Storage: staged output"]
    TMP --> OUT["Cloud Storage: published output"]
    W --> SQL
    W -. "Preemption" .-> REDO["Queue redelivery / retry"]
    REDO --> MIG
    MON["Cloud Monitoring"] -. "Queue lag, retries, SLA nội bộ" .-> Q
    MON -.-> SQL
~~~

Luồng dữ liệu phải có quy tắc commit rõ ràng. Một phương án:

1. Cloud Run tạo `job_id` ổn định và ghi row `PENDING` trong Cloud SQL.
2. Metadata job được gửi vào queue; worker bất kỳ có thể nhận.
3. Worker tính kết quả và upload vào **staging object** có tên gắn với job/attempt.
4. Worker kiểm tra checksum và commit trạng thái `COMPLETED` qua transaction/idempotency key.
5. Đối tượng hoàn thành được công bố theo quy tắc versioning/atomic write; job được ack khi durable state hợp lệ.
6. Nếu bị preempt ở bất kỳ bước nào, một worker khác kiểm tra trạng thái và tiếp tục hoặc làm lại phần chưa commit.
7. Cleanup job định kỳ xử lý staging objects không còn tham chiếu và những job vượt giới hạn retry.

**Quan trọng:** nếu publish object và commit Cloud SQL là hai thao tác độc lập, không có transaction phân tán mặc định giữa chúng. Thiết kế phải xử lý crash ở khoảng giữa hai bước bằng trạng thái trung gian, reconciliation hoặc quy tắc commit nhất quán. Không tuyên bố toàn luồng là exactly-once chỉ vì có primary key trong SQL.

### 12.3. IAM, mạng và dữ liệu

| Thành phần | Quyền/cấu hình cần cân nhắc | Lý do |
| --- | --- | --- |
| Spot worker service account | Chỉ các quyền đọc input và ghi output/checkpoint cần thiết. | Giảm phạm vi truy cập dữ liệu khi VM bị xâm nhập. |
| Cloud SQL | Kết nối có xác thực và database privileges phù hợp. | VM có đường mạng không tự được quyền cập nhật bản ghi. |
| VPC | VM không cần external IP nếu đường đến Google APIs/DB được thiết kế đúng. | Giảm bề mặt truy cập; xem Private Google Access/Cloud NAT/PSC theo nhu cầu. |
| Queue identity | Chỉ được nhận và ack job thuộc workload tương ứng. | Tách quyền enqueue và quyền xử lý. |
| CI/CD deployer | Quyền cập nhật template/MIG theo phạm vi được giao. | Không trao quyền hạ tầng cho runtime worker. |
| Logging | Log đủ để truy vết `job_id`, attempt, checkpoint và lỗi. | Điều tra khi preemption và retry. |

Không lưu bí mật dịch vụ hoặc Cloud SQL password trong image công khai hay startup-script gắn trên metadata không được bảo vệ. Ưu tiên cơ chế danh tính được quản lý, Secret Manager và quyền đọc tối thiểu theo kiến trúc.

### 12.4. Kịch bản lỗi cần kiểm thử

| Thời điểm VM bị preempt | Kết quả mong muốn |
| --- | --- |
| Trước khi lấy job. | Không mất việc; job vẫn trong queue. |
| Sau khi nhận job nhưng trước khi tạo output. | Job có thể được giao lại sau lease/ack deadline. |
| Sau khi upload staged object nhưng trước khi commit. | Worker mới phát hiện output tạm và hoàn thành/retry có kiểm soát. |
| Sau commit SQL nhưng trước ack. | Redelivery phát hiện `COMPLETED`, không tạo bản ghi hoặc side effect trùng. |
| Trong lúc checkpoint. | Checkpoint cuối cùng đã commit vẫn đọc được; bản ghi dở không được coi là hợp lệ. |
| Khi cả zone thiếu Spot capacity. | Queue giữ việc; nếu vượt deadline, kích hoạt phương án fallback được phê duyệt. |

Đây mới là bộ kiểm thử quyết định **ứng dụng chịu được gián đoạn**, không phải chỉ kiểm tra lệnh `gcloud compute instances create` chạy thành công.

## 13. Những sai lầm thường gặp

### 13.1. “Spot VM rẻ nên phù hợp mọi production”

Không đúng. Mức giảm giá không bảo đảm capacity hay khả năng phục vụ. Production có thể dùng Spot **cho một lớp công việc linh hoạt**, nhưng chức năng quan trọng thường cần nền capacity ổn định hoặc fallback.

### 13.2. “VM chạy được 20 giờ rồi, chắc sắp bị thu hồi”

Không có quy tắc dự báo đơn giản như vậy cho Spot. Khả năng preemption phụ thuộc nhu cầu tài nguyên và điều kiện dịch vụ, không phải bộ đếm thời gian có thể xác định trước. Không áp lịch restart chỉ dựa vào suy đoán tuổi VM.

### 13.3. “Bật shutdown script thì không bao giờ mất dữ liệu”

Sai. Thời gian thông báo là best effort và có thể không đủ. Checkpoint định kỳ và durable commit mới là lớp bảo vệ chính.

### 13.4. “MIG luôn thay thế Spot VM ngay lập tức”

Sai. MIG có thể cố gắng duy trì target capacity, nhưng nếu zone thiếu Spot capacity thì instance thay thế có thể chưa được tạo. Cần phân tán zone, fallback và giám sát backlog theo yêu cầu.

### 13.5. “Persistent Disk làm mọi job có thể resume”

Không hẳn. Disk có thể còn sau STOP nhưng process memory mất; nếu VM bị DELETE và disk auto-delete, dữ liệu cũng có thể mất. Worker khác cần biết cách tìm và đọc trạng thái an toàn.

### 13.6. “Queue phát lại message thì chắc chắn không mất hoặc trùng”

Queue có retry hỗ trợ xử lý lỗi, nhưng **ack trước khi commit** có thể làm mất công việc, còn **commit trước ack** có thể gây chạy lại. Idempotency và transaction/reconciliation vẫn bắt buộc.

### 13.7. “Cloud Run được triển khai trên Spot VM thì sẽ rẻ hơn”

Người dùng Cloud Run không tùy chọn Spot provisioning model của Compute Engine để đặt cho Cloud Run service như một VM. Nếu muốn tự quản lý Spot, cần chọn phương án Compute Engine/GKE/Batch phù hợp và chấp nhận thêm chi phí vận hành.

## 14. Bài tập tự kiểm tra

### Bài 1 — Chọn workload

Phân loại ba hệ thống: (a) máy chạy database chính, (b) worker resize ảnh trong queue, (c) HTTP API thanh toán yêu cầu sẵn sàng cao. Trường hợp nào phù hợp thử Spot trước và vì sao?

**Gợi ý:** (b) thường phù hợp nếu mỗi ảnh có thể xử lý lại, đầu vào/kết quả bền vững và có phương án xử lý deadline; (a), (c) cần mô hình sẵn sàng/độ bền khác.

### Bài 2 — Phân biệt STOP và DELETE

Một Spot VM có `--instance-termination-action=STOP`. Sau preemption, cần kiểm tra những gì trước khi kết luận có thể khởi động lại và tiếp tục job? Nếu chuyển sang `DELETE`, điều gì xảy ra với boot disk có auto-delete?

**Gợi ý:** trạng thái VM, capacity Spot, dữ liệu đã checkpoint, queue, boot disk/attached disks và nguồn khởi chạy worker; với DELETE phải xét vòng đời disk cùng instance.

### Bài 3 — Chọn chu kỳ checkpoint

Một job chạy 90 phút, mất 4 giây để lưu checkpoint. Hãy thử so sánh checkpoint mỗi 2, 5 và 15 phút. Phân tích phần việc mất tối đa khi preempt và overhead của checkpoint, sau đó đề xuất ngưỡng ban đầu để benchmark.

**Gợi ý:** checkpoint thường hơn giúp giảm công việc phải làm lại nhưng tăng số lần ghi. Không chỉ lấy overhead, cần tính tính nhất quán và khả năng phục hồi.

### Bài 4 — Xử lý double processing

Worker A đã commit output vào Cloud SQL, sau đó bị preempt trước khi ack message. Worker B nhận lại cùng `job_id`. Hãy thiết kế cách worker B kiểm tra trạng thái và tránh ghi trùng; giải thích vai trò của unique key/transaction.

### Bài 5 — Điều tra một VM dừng

~~~bash
gcloud compute instances describe spot-worker-01 \
  --project=retail-lab \
  --zone=asia-southeast1-a \
  --format="yaml(status,scheduling)"
~~~

Nếu `status: TERMINATED`, có đủ chứng cứ để nói đã xảy ra preemption không? Hãy nêu thêm những nguồn thông tin cần xem và cách kiểm tra job có được giao lại hay không.

### Bài 6 — Kiến trúc deadline

Job cần hoàn thành trước 06:00 hằng ngày nhưng Spot capacity không đủ từ 04:00 đến 05:30. Hãy đề xuất cách theo dõi queue lag, lúc kích hoạt worker tiêu chuẩn và kiểm soát trần chi phí fallback. Vì sao chỉ tăng số Spot instances mong muốn trong MIG chưa chắc giải quyết được?

## 15. Checklist trước khi triển khai thực tế

| Hạng mục | Điều cần xác minh |
| --- | --- |
| **Workload suitability** | Có thể gián đoạn, retry và hoàn thành lại theo SLO. |
| **Provisioning model** | Dùng `SPOT`, chọn machine type/zone được hỗ trợ và kiểm tra quota. |
| **Termination action** | Chọn `STOP` hoặc `DELETE` theo vòng đời worker và disk. |
| **Shutdown handling** | Có hook/tín hiệu khi phù hợp, nhưng không phụ thuộc hoàn toàn vào thời gian thông báo. |
| **Durable state** | Input, checkpoint, output và idempotency keys nằm ngoài VM hoặc được bảo vệ theo thiết kế. |
| **Retry** | Có ack/lease, giới hạn retry và dead-letter hoặc xử lý lỗi cuối. |
| **Concurrency** | Có bảo vệ race condition và ghi trùng giữa nhiều worker. |
| **Orchestration** | Có MIG/Batch/GKE hoặc bộ điều phối tương ứng, theo dõi thiếu Spot capacity. |
| **Fallback** | Có phương án dùng capacity tiêu chuẩn hoặc giảm tải khi deadline bị đe dọa. |
| **IAM và network** | Service account quyền tối thiểu; VPC egress/Google APIs/DB được cấu hình đúng. |
| **Observability** | Theo dõi preemption, backlog, checkpoint age, retry và tỷ lệ hoàn thành job. |
| **Cost control** | So sánh chi phí mỗi job hoàn thành, không chỉ chi phí mỗi giờ VM. |
| **Recovery test** | Đã thử mất VM ở nhiều điểm trong luồng và kiểm tra không mất/ghi trùng dữ liệu. |

## 16. Nguồn tra cứu và ghi nhớ

Tính năng, mức giá, machine type/zone hỗ trợ và chính sách thu hồi có thể thay đổi. Khi triển khai, đối chiếu tài liệu Google Cloud hiện hành:

- [Spot VMs overview — Compute Engine](https://cloud.google.com/compute/docs/instances/spot)
- [Create and use Spot VMs](https://cloud.google.com/compute/docs/instances/create-use-spot)
- [Preemptible VM instances](https://cloud.google.com/compute/docs/instances/preemptible)
- [Instance scheduling options](https://cloud.google.com/compute/docs/instances/instance-scheduling-options)
- [Managed Instance Groups overview](https://cloud.google.com/compute/docs/instance-groups)
- [Cloud Batch documentation](https://cloud.google.com/batch/docs)
- [GKE Spot VMs](https://cloud.google.com/kubernetes-engine/docs/concepts/spot-vms)
- [Cloud Storage consistency](https://cloud.google.com/storage/docs/consistency)
- [Cloud Pub/Sub subscriber overview](https://cloud.google.com/pubsub/docs/subscriber)
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)

**Spot VM phù hợp khi workload được thiết kế để sống sót sau gián đoạn.** VM có thể bị thu hồi bất kỳ lúc nào; cơ chế bảo vệ thực sự nằm ở việc chia nhỏ công việc, lưu checkpoint có tính nhất quán, commit idempotent, giao lại job khi cần và duy trì capacity thay thế theo deadline. Khi kết hợp những nguyên tắc đó với Compute Engine, IAM, VPC, dịch vụ dữ liệu và giám sát, nhóm có thể tận dụng lợi thế chi phí Spot mà vẫn quản lý rủi ro mất dữ liệu và chất lượng dịch vụ.
