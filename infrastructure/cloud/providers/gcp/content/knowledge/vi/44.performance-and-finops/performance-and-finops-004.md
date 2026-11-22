# Đánh giá Spot VMs, reservations và cam kết sử dụng

Khi tối ưu chi phí Compute Engine trên Google Cloud, một nhóm có thể thấy cùng một workload nhưng ba lựa chọn tài chính rất khác nhau: chạy VM theo giá on-demand để giữ linh hoạt, dùng **Spot VMs** để giảm đơn giá cho phần công việc có thể gián đoạn, hoặc mua **Committed Use Discounts (CUDs)** cho lượng sử dụng ổn định trong một đến ba năm. Nếu lo ngại không tạo được VM vào giờ cao điểm, nhóm có thể cần **reservations** để giữ sẵn capacity trong một zone.

Các cơ chế này giải quyết những bài toán khác nhau:

- **Spot VM:** dùng năng lực dư với giá thấp, chấp nhận khả năng bị thu hồi bất cứ lúc nào.
- **Reservation:** dành trước năng lực VM cụ thể; thường vẫn phải trả phí tài nguyên đã giữ ngay cả khi chưa dùng.
- **Commitment/CUD:** đổi cam kết tài chính dài hạn lấy đơn giá ưu đãi cho mức sử dụng đủ điều kiện; bản thân CUD không bảo đảm có VM để khởi tạo.

Vì thế, FinOps không nên chọn phương án chỉ theo phần trăm discount. Cần đánh giá workload tolerance, RTO/RPO, lịch tải, nhu cầu capacity, mức sử dụng nền, quyền quản trị và chi phí thực tế qua Cloud Billing.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Spot VMs, on-demand VMs, reservations và CUDs.
- Chọn workload phù hợp với việc bị preempt, checkpoint và retry.
- Thiết kế cách phát hiện preemption, graceful shutdown và khôi phục task.
- Hiểu reservation affinity, tự động tiêu thụ so với specific reservation và phí capacity chưa sử dụng.
- Phân biệt resource-based CUD với compute flexible CUD.
- Hiểu cách kết hợp commitments và reservations mà không nhầm lợi ích capacity với discount.
- Tính mức sử dụng nền, reservation utilization, commitment utilization và savings giả định.
- Đọc thông tin trong Compute Engine, Cloud Billing và Recommender để kiểm chứng phương án.
- Lập kế hoạch kết hợp VM tiêu chuẩn, Spot worker và capacity dự phòng cho một ứng dụng Java.
- Tránh mua commitment hoặc reservation quá mức sau khi rightsizing.

## 1. Ba công cụ, ba mục tiêu khác nhau

| Tiêu chí | On-demand VM | Spot VM | Reservation | Committed Use Discount |
|---|---|---|---|---|
| Mục tiêu | Linh hoạt và cung cấp compute thông thường | Giảm giá cho công việc chấp nhận bị thu hồi | Đảm bảo capacity phù hợp ở zone | Giảm giá cho usage ổn định đủ điều kiện |
| Bị preempt vì Spot capacity? | Không theo cơ chế Spot | Có thể bất kỳ lúc nào | Capacity được dành theo reservation | Không liên quan trực tiếp đến quyền khởi tạo |
| Trả phí khi không dùng? | Thông thường không trả VM compute khi đã stop, nhưng disk/IP còn phí | Không trả giờ compute của VM đã stop; resource liên quan vẫn phí | Có, nếu reserved capacity còn tồn tại và chưa được VM dùng | Có commitment fee/obligation dù sử dụng ít hơn |
| Thời hạn | Theo sử dụng | Không yêu cầu term cố định | Theo vòng đời reservation | 1 hoặc 3 năm |
| Điều kiện | Machine type/quota/availability | Tolerance với preemption và capacity biến động | Match machine/zone/affinity và quota | SKU, location, amount và billing scope đủ điều kiện |
| Bảo đảm capacity? | Không | Không | Có giữ capacity theo cấu hình | Không |
| Phù hợp | Service cần uptime thông thường | Batch, CI workers, fault-tolerant tasks | Capacity cho failover, peak, migration | Baseline chạy ổn định |

Một workload có thể dùng **reservation và CUD cùng lúc** nếu thỏa điều kiện; reservation giữ capacity còn CUD tạo mức giá phù hợp. Ngược lại, Spot VM không tiêu thụ Compute Engine reservations thông thường và **compute flexible CUD không áp dụng cho Spot/preemptible VMs**.

## 2. Bắt đầu từ workload profile, không từ chiết khấu

Trước khi quyết định, hãy phân loại nhu cầu:

| Workload | Load pattern | Chấp nhận interruption | Yêu cầu capacity | Hướng cân nhắc |
|---|---|---|---|---|
| Java checkout API | 24/7, nhạy latency | Rất thấp | Cao | Standard + autoscale, CUD cho baseline |
| Batch tạo báo cáo | Theo lịch, retry được | Cao | Trung bình | Spot với checkpoint |
| CI integration tests | Burst, có thể chạy lại | Trung bình/cao | Trung bình | Spot/MIG hoặc Cloud Build tùy nền tảng |
| Database primary | Liên tục, stateful | Thấp | Cao | Standard + HA, reservation nếu thiếu capacity |
| Analytics worker | Nhiều job độc lập | Cao | Thấp/trung bình | Spot + queue |
| DR standby | Ít traffic nhưng cần capacity khi failover | Không phù hợp cho critical cutover | Cao | Reservation và kế hoạch phục hồi |
| GPU training | Chạy lâu, checkpoint được | Phụ thuộc job | Có thể thiếu GPU theo zone | So sánh Spot và reservation/commitments có hỗ trợ |

Không có lựa chọn duy nhất đúng cho mọi môi trường. Một batch 15 phút có thể chạy tốt trên Spot; batch cuối kỳ phải xong trước hạn chót rất nghiêm ngặt có thể cần pool standard để bảo đảm tiến độ.

### Phân tích bốn thông số

1. **Interruption tolerance:** job có thể bắt đầu lại mà không gây mất/ghi trùng dữ liệu?
2. **Recovery cost:** tốn bao lâu và bao nhiêu để khôi phục khi VM biến mất?
3. **Capacity sensitivity:** có cần chắc chắn tạo được số VM cụ thể trong một zone?
4. **Demand predictability:** có lượng compute nền ổn định trong suốt 1–3 năm?

Spot chủ yếu tối ưu đơn giá, reservations chủ yếu giảm rủi ro thiếu capacity, CUD tối ưu giá của baseline. Nếu không phân loại trước, tổ chức có thể vừa mua reservation vừa để trống, vừa mua CUD nhưng sau đó di chuyển workload sang dịch vụ không còn đủ điều kiện.

## 3. Spot VMs: tiết kiệm đổi lấy khả năng gián đoạn

Spot VMs là VM dùng **spot provisioning model** trên Compute Engine. Google Cloud có thể lấy lại capacity bằng cách preempt VM; số lượng VM Spot sẵn có thay đổi theo zone, machine family và thời điểm.

Theo tài liệu Compute Engine hiện hành, mức giảm giá Spot có thể **lên tới 91%** với nhiều loại machine/GPU/TPU/Local SSD, nhưng mức cụ thể phụ thuộc SKU và thời điểm. Không dùng con số cao nhất làm mặc định cho business case.

### Đặc tính cần nhớ

- Spot VM có thể bị preempt bất cứ lúc nào, kể cả ngay sau khi bắt đầu job.
- Không có SLA về availability của Spot VM; Spot bị loại khỏi Compute Engine SLA.
- Không có bảo đảm capacity hoặc thời gian chạy tối thiểu/tối đa nếu không cấu hình giới hạn riêng.
- Không thể dựa vào live migration hoặc automatic restart sau sự kiện host như với VM standard.
- Khi preempt, VM được stop hoặc delete theo instance termination action.
- Nếu bị stop, persistent disk vẫn tồn tại và tiếp tục phát sinh storage charges; Local SSD và disk auto-delete cần xem xét riêng.
- Discount của Spot không cộng dồn với compute flexible CUD.

### Workload tốt cho Spot

- Job xử lý chia shard có thể chạy lại.
- Compile/test CI độc lập, không yêu cầu worker cố định.
- Encoding media hoặc data preprocessing theo queue.
- Analytics hoặc simulation có checkpoint.
- Workers phục vụ hàng đợi với idempotent jobs.
- Batch GPU training có checkpoint, nếu loại GPU/machine được hỗ trợ và capacity phù hợp.

### Workload không nên đặt toàn bộ trên Spot

- Database primary không có HA/recovery phù hợp.
- Checkout/payment API với yêu cầu uptime chặt nhưng không có standard capacity dự phòng.
- Transaction đang giữ state chỉ trong RAM.
- Job không có checkpoint, kéo dài hàng giờ và có deadline sát.
- Workload bị ràng buộc license/hardware không phù hợp Spot.
- Single-instance service quan trọng mà preemption gây downtime ngay lập tức.

## 4. Vòng đời preemption: cập nhật cần chú ý

Theo tài liệu Spot VMs, Google Cloud có cơ chế **preemption notice duration** cho Spot:

- **0 giây (mặc định):** không có khoảng delay riêng trước khi hệ thống phát ACPI Soft Off; ứng dụng có thể xử lý preemption trong giai đoạn shutdown.
- **120 giây (nếu được cấu hình):** có khoảng notice riêng trước khi bắt đầu shutdown, giúp workload có thêm thời gian chủ động checkpoint.
- Sau Soft Off, có **shutdown period tối đa khoảng 30 giây theo best effort** trước khi VM bị tắt cưỡng bức.

Không được coi 30 giây hoặc 120 giây là thời gian bảo đảm để ghi toàn bộ dữ liệu. Cần lưu checkpoint định kỳ và thiết kế replay được trước khi tín hiệu preemption xuất hiện.

~~~text
Spot VM RUNNING
       |
       +--> Có thể bị preempt vào bất kỳ lúc nào
                   |
                   v
        Metadata preempted = TRUE
                   |
         [0s hoặc 120s notice]
                   |
                   v
             ACPI Soft Off
                   |
          [Shutdown best effort]
                   |
                   v
        TERMINATED hoặc DELETED
                   |
                   v
       Controller/scheduler retry job
~~~

### Cấu hình termination action

- **STOP:** VM ngừng, có thể được khởi động lại khi capacity có sẵn; disk liên quan có thể tiếp tục tính phí.
- **DELETE:** VM bị xóa; kiểm tra auto-delete của boot/data disks và quản lý checkpoint bên ngoài.

Chọn DELETE nếu worker hoàn toàn disposable và checkpoint đã được lưu bền vững ở nơi khác. Chọn STOP khi cần giữ lại VM metadata/disk nhưng phải tính thêm storage cost và quy trình restart.

## 5. Thiết kế checkpoint, retry và idempotency

Một Java batch worker phù hợp với Spot cần xử lý được:

- Worker chết giữa một shard.
- Một shard được phát lại cho worker khác.
- Kết quả đã ghi một phần trước khi mất VM.
- Event hoặc message được giao lặp lại.
- Worker mới chạy trên máy hoặc zone khác.

### Quy trình xử lý mẫu

~~~text
Pub/Sub/Cloud Tasks/Batch queue
             |
             v
    Claim work item + deadline
             |
             v
      Process chunk N
             |
             v
   Write durable checkpoint
             |
             v
   Commit result idempotently
             |
             v
   Ack / mark work completed
~~~

Các điểm quan trọng:

1. Không ack message trước khi kết quả nghiệp vụ được lưu bền.
2. Có khóa idempotency hoặc unique constraint để tránh tạo dữ liệu trùng.
3. Chia job lớn thành chunk đủ nhỏ để replay không tốn quá nhiều.
4. Đặt retry có giới hạn và dead-letter policy cho lỗi không phục hồi.
5. Dùng Cloud Storage, database hoặc storage có độ bền phù hợp cho checkpoint.
6. Ghi metric thời gian lãng phí do preemption, số lần retry và backlog.

### Ví dụ Java graceful shutdown

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class SpotWorker {
    private static final AtomicBoolean stopping = new AtomicBoolean(false);

    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            stopping.set(true);
            // Đánh dấu dừng nhận task mới; flush checkpoint theo budget.
        }));

        while (!stopping.get()) {
            // Nhận một chunk, xử lý idempotently và lưu checkpoint bền.
            // Thực tế cần cancellation, deadline và health metrics.
        }
    }
}
~~~

Shutdown hook chỉ là cơ chế hỗ trợ, không thay thế checkpoint định kỳ. Nếu process bị kill, mất network hoặc host bị thu hồi bất ngờ, hook có thể không hoàn thành. Kiểm tra hệ thống bằng cách giả lập stop/delete trong môi trường thử nghiệm.

## 6. Tạo Spot VM minh họa

Lệnh sau tạo một Spot worker, cần được review bởi nhóm hạ tầng trước khi chạy vì có thể phát sinh phí và thay đổi project.

~~~bash
gcloud compute instances create spot-worker-01 \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=e2-standard-4 \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --image-family=debian-13 \
  --image-project=debian-cloud
~~~

Khi cần notice kéo dài, xác minh machine type/zone hỗ trợ rồi cấu hình preemption notice duration theo gcloud version và tài liệu hiện hành. Đừng viết code phụ thuộc tuyệt đối vào việc notice luôn có đủ 120 giây.

Kiểm tra trạng thái:

~~~bash
gcloud compute instances describe spot-worker-01 \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,status,scheduling,disks,labels)"
~~~

Gắn labels owner/environment/cost-center và cấu hình IAM tối thiểu. Không cấp quyền Owner cho Spot worker chỉ vì VM sẽ bị xóa sau job.

### Spot với Managed Instance Groups

MIG giúp duy trì số lượng VM mong muốn và tạo lại instance khi bị preempt. Nhưng MIG không thể tạo Spot VM nếu zone hết Spot capacity. Có thể cần multi-zone strategy, autoscaling, standard fallback pool hoặc hàng đợi cho phép job trì hoãn.

### GKE Spot node pools

Trên GKE, Spot capacity có thể dùng cho các Pods chấp nhận eviction. Cần node affinity/taints/tolerations theo cấu hình node pool, Pod disruption handling và sự phân biệt workloads critical vs optional.

Không chạy toàn bộ control plane dependencies hoặc mọi replica của dịch vụ cần uptime cao trên Spot nodes. Dùng PodDisruptionBudget, topology spread và standard node pool cho phần lõi; PDB không ngăn được mọi trường hợp preemption.

## 7. Đánh giá Spot bằng tổng chi phí hoàn thành công việc

Đơn giá thấp chưa chắc chi phí trên mỗi job thấp. Cần tính:

~~~text
Cost per completed job
  = compute charges
  + retry/reprocessing compute
  + checkpoint storage/network
  + scheduler/queue overhead
  + expected business impact của deadline misses
~~~

Ví dụ giả định, không đại diện cho giá GCP:

| Thuộc tính | VM standard | Spot worker |
|---|---:|---:|
| Đơn giá giả định | 1,00 USD/giờ | 0,30 USD/giờ |
| Thời gian compute cần cho một job | 10 giờ | 10 giờ |
| Thời gian bị lặp do preemption | 0 giờ | 3 giờ |
| Compute cost | 10,00 USD | 3,90 USD |
| Checkpoint/storage overhead | 0,10 USD | 0,80 USD |
| Tổng chi phí minh họa | 10,10 USD | 4,70 USD |

Spot trong ví dụ vẫn rẻ hơn, nhưng không có nghĩa job sẽ xong đúng hạn. Nếu bỏ lỡ SLA gây thiệt hại lớn, workload có thể cần fallback trên standard VMs.

### Theo dõi Spot metrics

- Job completion rate và completion deadline.
- Preemption count/rate theo machine type/zone.
- Spot capacity allocation failures.
- Retry và reprocessing hours.
- Average checkpoint age.
- Queue backlog và age of oldest task.
- Cost per successful job.
- Tỷ lệ fallback sang standard VMs.
- RTO/RPO của workload khi bị preempt.

Không dùng duy nhất tỷ lệ preemption lịch sử để bảo đảm capacity tương lai. Tình trạng Spot thay đổi theo thời điểm.

## 8. Reservations: giữ sẵn năng lực Compute Engine

**Reservation** là việc dành trước capacity phù hợp với cấu hình VM tại một zone. Khi tạo reservation và hệ thống xác nhận có capacity, tài nguyên được giữ cho các instance phù hợp đến khi reservation bị xóa hoặc hết vòng đời theo cấu hình.

Reservation hữu ích khi:

- Dự kiến tăng số VM lớn tại thời điểm cutover.
- Cần capacity dự phòng để failover.
- Có workload GPU hoặc machine type khó cấp phát ở giờ cao điểm.
- Chuẩn bị migration wave cần triển khai một số VM đúng zone.
- Cần chuẩn bị capacity cho chiến dịch có lịch cụ thể.

Reservation **không tự cung cấp giá thấp hơn**. Google Cloud tính phí tài nguyên đã reserve theo cơ chế giá tương ứng, kể cả khi chưa có VM tiêu thụ reservation. Các CUD/discount hợp lệ có thể áp dụng theo quy định.

### Reservation không phải backup hoặc HA

Reservation bảo đảm khả năng tạo VM theo cấu hình đã đặt, không tự:

- Chạy ứng dụng thay bạn.
- Sao chép dữ liệu.
- Chuyển traffic khi instance lỗi.
- Bảo đảm mọi dependency ngoài VM có capacity.
- Chữa rủi ro cùng-zone; một reservation trong zone không phải DR multi-zone.

Kế hoạch DR cần còn database replication, storage, networking, secrets, IAM, DNS và diễn tập.

## 9. Các loại reservation và consumption

Một reservation có thể:

- **Single-project:** capacity được dành trong phạm vi project.
- **Shared reservation:** cho phép các project được chọn dùng capacity theo chính sách chia sẻ.
- **Automatically consumed:** VM phù hợp có thể sử dụng capacity tự động theo reservation affinity và quy tắc consumption.
- **Specifically targeted:** chỉ VM cấu hình target reservation đó mới dùng capacity.

### Reservation affinity

Reservation affinity xác định VM:

- Có thể tiêu thụ reservation phù hợp bất kỳ.
- Chỉ được dùng một reservation cụ thể.
- Không được dùng reservation.

Nếu machine type, CPU platform, GPU/Local SSD hoặc thuộc tính khác không khớp, VM có thể không tiêu thụ capacity đã giữ. Tương tự, reservation đã full hoặc quota không đủ có thể khiến VM không khởi tạo được.

**Spot VMs không tiêu thụ Compute Engine reservations**, kể cả khi có machine type trùng khớp. Đây là ranh giới quan trọng khi phối hợp workload.

### Ví dụ tạo single-project reservation

Lệnh sau **phát sinh chi phí capacity kể cả khi chưa có VM chạy**, chỉ được thực hiện theo approval và budgeting:

~~~bash
gcloud compute reservations create batch-capacity \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=n2-standard-4 \
  --vm-count=5
~~~

Kiểm tra capacity:

~~~bash
gcloud compute reservations list \
  --project=PROJECT_ID \
  --format="table(name,zone,specificReservation.count,specificReservation.inUseCount)"
~~~

Field hiển thị phụ thuộc API/CLI version; nếu projection không xuất hiện, dùng --format=yaml để xem cấu trúc response.

~~~bash
gcloud compute reservations describe batch-capacity \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format=yaml
~~~

Theo dõi số VM thực sự tiêu thụ, số còn rỗi và thời gian tồn tại. Nếu reservation dùng cho migration hoặc peak ngắn hạn, lập ngày review/delete từ trước.

## 10. Chi phí reservation chưa sử dụng

Giả sử một reservation giữ chỗ cho 10 VM giống nhau ở zone A, nhưng chỉ có 6 VM đang chạy và tiêu thụ đúng reservation.

~~~text
Reserved capacity:      10 VM
Consumed:                6 VM
Unconsumed:              4 VM
Reservation utilization: 60%
~~~

Google Cloud tính phí năng lực đã reserve trong khoảng reservation tồn tại. Vì thế 4 VM-slot rỗi vẫn là chi phí cơ hội/chi phí đã giữ. Một VM đang tiêu thụ reservation **không bị tính hai lần compute cho cùng reserved resources**.

### Các câu hỏi cần kiểm tra

- Reservation tồn tại để bảo đảm capacity cho thời điểm nào?
- Bao nhiêu VM đang thực sự tiêu thụ?
- Các VM có machine type/affinity phù hợp?
- Có project nào vô tình dùng shared reservation?
- Phí unused capacity có nằm trong ngân sách?
- Khi nào cần resize/delete reservation?
- Có attachment vào commitment làm giới hạn việc sửa/xóa reservation?

Một reservation quá lớn có thể làm hóa đơn tăng dù không có VM production mới. Phân biệt **capacity assurance** với **cost saving** trong báo cáo FinOps.

## 11. Committed Use Discounts là gì?

**Committed Use Discounts (CUDs)** là lợi ích giảm giá đổi lấy cam kết sử dụng tài nguyên hoặc cam kết mức chi tiêu tối thiểu trong kỳ hạn **1 hoặc 3 năm**.

Cam kết phù hợp với workload đã có baseline ổn định. Nếu sử dụng thấp hơn mức cam kết, nghĩa vụ tài chính không tự biến mất. Nếu sử dụng vượt, phần vượt có thể được tính theo giá/discount khác tùy SKU và chính sách billing.

Hai loại chính thường gặp:

| Loại CUD | Đơn vị cam kết | Khi phù hợp |
|---|---|---|
| Resource-based CUD | Lượng vCPU, memory hoặc resource đủ điều kiện theo quy định | Baseline Compute Engine ổn định theo region/machine family |
| Compute flexible CUD | Mức chi tiêu hourly tối thiểu cho SKU đủ điều kiện | Workload có thể thay đổi máy/dịch vụ nhưng vẫn có eligible spend ổn định |

Các mức discount khác nhau theo SKU, machine family, term và Cloud Billing model; không dùng một tỷ lệ chung cho mọi resource.

### Resource-based commitments

Đặc điểm:

- Cam kết một lượng tài nguyên Compute Engine nhất định với kỳ hạn 1 hoặc 3 năm.
- Có liên hệ tới project và region mua cam kết; phạm vi chia sẻ sang project khác phụ thuộc cấu hình CUD sharing.
- Dùng cho resource đủ điều kiện như vCPU, memory, GPU, Local SSD, sole-tenant hoặc một số license theo loại commitment.
- Region và loại tài nguyên có thể giới hạn nơi usage được coverage.
- Có thể kết hợp với reservation, nhưng bản thân commitment không giữ capacity.

Với Cloud Billing account tạo sau một số mốc cấu hình mới, quy tắc chia sẻ CUD mặc định có thể khác account cũ. Kiểm tra Billing settings và tài liệu hiện hành thay vì giả định mọi project tự chia sẻ discount.

### Compute flexible CUDs

Đặc điểm:

- Mua tại Cloud Billing account.
- Cam kết mức spend tối thiểu theo giờ trong 1 hoặc 3 năm.
- Có thể áp dụng cho tập hợp Compute Engine/GKE/Cloud Run SKUs đủ điều kiện theo tài liệu.
- Thanh toán commitment fee trong kỳ dù eligible usage thấp hơn mức mua.
- **Không áp dụng cho Spot/preemptible VMs**.
- Những machine families và resource khác nhau có mức giảm giá và điều kiện term khác nhau.

Một số tài khoản có thể ở mô hình billing CUD khác nhau trong quá trình chuyển đổi sang cơ chế tiêu thụ/discount mới. Khi lập phương án, dùng giá và mô hình thực tế trên Cloud Billing account đó.

## 12. CUD không thay thế reservation

Hai lựa chọn thường bị hiểu nhầm:

**Mua CUD mà không tạo reservation:** có ưu đãi giá cho eligible usage, nhưng không giữ sẵn số VM cụ thể trong zone. Nếu thiếu capacity, việc đã cam kết chi trả không bảo đảm VM sẽ được khởi tạo đúng thời điểm.

**Tạo reservation nhưng không có CUD:** giữ sẵn capacity, song vẫn bị tính phí tương ứng trong thời gian tồn tại; không tự nhận thêm discount chỉ vì đã reserve.

**Kết hợp CUD và reservation:** khi phù hợp, capacity được giữ và usage/reserved resources có thể nhận CUD theo điều kiện. Một số resource-based commitments cho phép gắn reservation; các resource đặc thù có thể yêu cầu attached reservation.

### Ví dụ phối hợp

Một ứng dụng có 8 VM nền chạy 24/7, đã quan sát nhiều tháng và yêu cầu failover capacity trong zone. Nhóm có thể:

1. Rightsize baseline còn 8 VM theo tải và SLO.
2. Cân nhắc resource-based CUD cho một phần usage ổn định, không mua sát 100% peak.
3. Tạo reservation giữ đúng capacity cần bảo đảm.
4. Cấu hình VM/MIG tiêu thụ reservation phù hợp.
5. Theo dõi CUD coverage/utilization và reservation consumption riêng biệt.

Không mua commitment mới dựa trên cấu hình VM chưa được rightsizing. Nếu giảm usage sau khi mua, khoản cam kết có thể không được khai thác hết.

## 13. Công thức đánh giá commitment utilization

Các nhóm nên theo dõi:

~~~text
Commitment utilization
  = eligible usage được coverage
    / mức cam kết đã mua

Reservation utilization
  = số capacity units đang tiêu thụ
    / tổng capacity units đã reserve
~~~

Hai tỷ lệ đo vấn đề khác nhau. Commitment utilization thấp nghĩa là đã trả phí nhưng chưa tận dụng hết cam kết. Reservation utilization thấp nghĩa là đã giữ nhiều capacity hơn nhu cầu thực tế.

### Ví dụ giả định

Giả sử eligible usage ổn định ở mức 100 đơn vị chi phí on-demand mỗi giờ, với các dao động theo ngày.

- Mua flexible commitment tương đương 60 đơn vị/giờ có thể giúp tận dụng baseline.
- Mua tương đương 120 đơn vị/giờ có nguy cơ còn phần unused trong các giờ bình thường.
- Chỉ mua commitment sau khi đã tính growth, planned decommissioning, rightsizing và chuyển dịch workload.

Ví dụ chỉ nhằm minh họa, không phải hướng dẫn quy đổi tiền commitment fee sang lượng eligible usage trên Billing account cụ thể. Cần dùng Cloud Billing reports và pricing/commitment calculator để tính chính xác.

### Khi nào tránh commitment dài hạn?

- Sắp thay đổi machine family hoặc kiến trúc lớn.
- Có kế hoạch di chuyển phần lớn workload sang dịch vụ/SKU không đủ điều kiện.
- Baseline chưa ổn định hoặc project sẽ đóng.
- Khó dự báo region, amount hay thời gian sử dụng.
- Tài chính chưa phê duyệt nghĩa vụ cam kết kéo dài 1–3 năm.

Không cố mua CUD chỉ vì phần trăm discount lớn. Lợi ích chỉ có ý nghĩa khi phần usage đủ điều kiện và thực sự tồn tại trong kỳ.

## 14. Đọc thông tin hiện có trước khi mua

### Xem reservations

~~~bash
gcloud compute reservations list \
  --project=PROJECT_ID \
  --format=yaml
~~~

Với reservation cụ thể:

~~~bash
gcloud compute reservations describe RESERVATION_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format=yaml
~~~

Xem capacity reserved, consumption, sharing/affinity và các thuộc tính đã giữ.

### Xem resource-based commitments

~~~bash
gcloud compute commitments list \
  --project=PROJECT_ID \
  --regions=REGION
~~~

Kiểm tra term, trạng thái activation, region, resource type, amount và reservations được attach nếu có. Spend-based flexible CUD có thể được quản lý tại Cloud Billing account và có cách xem khác; không chỉ nhìn danh sách regional Compute Engine commitments để kết luận toàn bộ CUD của tổ chức.

### Xem Spot VM configuration

~~~bash
gcloud compute instances describe VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,status,machineType,scheduling,labels)"
~~~

Xác minh provisioning model, termination action và các setting liên quan.

### Đối chiếu Billing

Cloud Billing reports và billing export sang BigQuery giúp kiểm tra:

- Eligible spend theo SKU, machine family và project.
- Số giờ usage thực tế và mức ổn định.
- CUD fee/discount/credits theo mô hình billing.
- Reservation unused capacity charges.
- Chi phí Spot, standard fallback và storage.
- Savings cuối cùng sau rightsizing và migration.

Mọi quyết định mua cam kết cần có phương án tài chính được phê duyệt; không dùng lệnh create/purchase trong bước chỉ phân tích.

## 15. Matrix chọn chiến lược

| Nhu cầu | Spot VM | Reservation | CUD |
|---|---|---|---|
| Batch 2 giờ, chạy lại được | Rất phù hợp | Thường không cần | Không cần nếu usage không ổn định |
| Service production 24/7 | Chỉ một phần phụ trợ | Có thể cần nếu capacity quan trọng | Hợp lý cho baseline đủ điều kiện |
| Launch cần thêm 100 VM một ngày | Spot nếu chấp nhận thiếu | Có thể cân nhắc reservation thời hạn ngắn | Không nhất thiết mua 1–3 năm |
| DR cần 20 VM khởi động ngay | Không phù hợp critical recovery | Hữu ích nếu phải bảo đảm capacity | Chỉ giảm giá nếu usage/conditions phù hợp |
| CI workers theo pull requests | Phù hợp với retry | Không nhất thiết | Chỉ cho phần baseline ổn định |
| GPU train có checkpoint | Phù hợp nếu Spot capacity | Cân nhắc khi cần chắc chắn GPU | Cân nhắc với usage GPU dự báo và SKU đủ điều kiện |
| Workload sắp rời Compute Engine | Có thể cho batch tạm | Chỉ khi có kế hoạch migration cụ thể | Tránh cam kết dài hạn quá mức |
| Load tăng đột biến không đoán trước | Có thể tăng phần opportunistic | Reservation nếu cần assurance | Chỉ baseline, phần burst giữ linh hoạt |

Không nhầm "phù hợp" với bảo đảm. Spot availability và reservation capacity có thể phụ thuộc machine type, zone và thời điểm; một số loại reservation có giới hạn trên GPU, machine series hoặc dịch vụ tích hợp.

## 16. Ví dụ kiến trúc kết hợp cho Java workload

Một hệ thống thương mại điện tử gồm:

- Checkout API Java/Spring trên GKE/Compute Engine.
- Order database trong dịch vụ managed database.
- Worker xử lý analytics và báo cáo theo Pub/Sub.
- CI runners chạy integration tests.
- Nhóm VM standby phục vụ recovery.

### Phân tầng capacity

~~~text
                     HTTP users
                         |
                         v
            Production Java API baseline
            Standard VM / GKE standard nodes
            CUD cho eligible stable usage
                         |
             +-----------+-----------+
             |                       |
             v                       v
      Database service         Pub/Sub queue
      HA + backups                  |
                                  v
                           Spot workers
                           Checkpoint + retry
                                  |
                             fallback pool
                           Standard/on-demand

 DR failover capacity: reservations nếu cần giữ chỗ
~~~

### Quyết định cho từng thành phần

| Thành phần | Hướng quyết định | Điều kiện |
|---|---|---|
| Checkout API | Standard capacity + CUD baseline | Có đủ telemetry/SLO và usage ổn định |
| Analytics worker | Spot + idempotent queue | Có checkpoint và retry |
| Integration test workers | Spot hoặc ephemeral runners | Test có thể restart không làm hỏng dữ liệu |
| Failover VMs | Reservation nếu capacity availability critical | Có DR drill, không chỉ giữ chỗ trên giấy |
| Peak traffic bổ sung | On-demand autoscaling | Không mua commitment cho peak hiếm |

### Ví dụ cost review

Trước khi mua bất kỳ commitment nào:

1. Chạy rightsizing cho baseline 90 ngày hoặc chu kỳ phù hợp.
2. Xem mức usage thấp nhất có thể dự báo trong năm tới.
3. Trừ resource sắp decommission, workload chuyển sang managed service và phần có thể đưa lên Spot.
4. Ước tính phần còn lại đủ điều kiện cho từng loại CUD.
5. So sánh 1 năm, 3 năm và on-demand trong nhiều growth scenarios.
6. Với reservation, tính riêng chi phí capacity chưa được dùng trong giai đoạn dự kiến.
7. Kiểm tra compliance/DR và khả năng duy trì capacity trong zone.
8. Lấy phê duyệt từ FinOps, application owner và đội vận hành.

## 17. Reservation sử dụng thấp: nguyên nhân và điều tra

Nếu có reservation giữ 20 VM nhưng chỉ 5 VM sử dụng, có thể do:

- Kế hoạch migration/cutover bị hoãn.
- VM không match machine type, min CPU platform, GPU/Local SSD.
- Reservation affinity cấu hình sai.
- VM chạy ở zone khác.
- Shared reservation không cho consumer project phù hợp.
- Quota hoặc reservation bị degraded.
- Owner đã chuyển tải sang vùng hoặc kiến trúc khác.

Các bước:

1. Xem reservation assuredCount, count và inUseCount.
2. Kiểm tra consumer instance properties và affinity.
3. Xác minh topology và desired capacity.
4. Đối chiếu kế hoạch migration/campaign.
5. Nếu không còn cần capacity, xem khả năng resize/delete theo loại reservation.
6. Nếu attached vào commitment, kiểm tra restriction trước khi thay đổi.

Không xóa reservation được attach vào một commitment đặc thù mà không xác minh policy. Một số attached reservations bị giới hạn thay đổi trong toàn bộ kỳ commitment.

## 18. Spot capacity biến động: thiết kế fallback

Một service có pool Spot 10 workers có thể tạm thời chỉ khởi tạo được 4 workers. Nếu queue tăng, cần lựa chọn:

- Chấp nhận xử lý chậm hơn trong giới hạn SLA.
- Mở thêm Spot capacity ở zone/machine family khác nếu được hỗ trợ.
- Chuyển một phần queue sang standard pool.
- Hoãn tác vụ ít quan trọng.
- Tăng mức checkpoint để giảm waste khi preemption cao.

### Phân tách priority

| Loại công việc | Ưu tiên | Capacity |
|---|---|---|
| Confirm order / payment | Critical | Standard capacity |
| Generate invoice | High | Standard hoặc hybrid theo deadline |
| Send routine notifications | Medium | Queue + Spot/fallback |
| Build recommendation dataset | Low | Spot |
| Nightly integration tests | Low/Medium | Spot và retry |

Controller phải đo queue age và deadline; không chỉ tăng instance count mù quáng. Nếu dùng Standard fallback, đặt budget guardrail và alert khi chi phí vượt dự kiến.

## 19. Governance và IAM

Việc mua commitment hoặc tạo reservation có thể tạo nghĩa vụ chi phí lớn. Phân biệt rõ các vai trò:

- **FinOps analyst:** đọc billing, usage, recommendations.
- **Platform engineer:** đánh giá machine types, reservation consumption, workload topology.
- **App owner:** xác nhận SLO, deadline, khả năng preemption.
- **Security:** kiểm tra service account, network, data protection.
- **Financial approver:** chấp nhận term/commitment fee và reservation charges.
- **Operations:** thực thi change và rollback.

Không cấp quyền tạo commitment cho mọi developer. Sử dụng IAM least privilege, review/audit trail và change request có định danh.

### Nhãn và metadata

Nên gắn labels hoặc tags:

- owner, application, environment.
- cost-center và business-unit.
- lifecycle/retention.
- capacity-purpose: baseline, spot, DR, migration.
- commitment-owner hoặc reservation-review-date nếu phù hợp quy ước.

Tránh đặt dữ liệu nhạy cảm hoặc thông tin cá nhân vào label values. Không dùng label làm nguồn sự thật duy nhất về nghĩa vụ tài chính; cần gắn với billing contract và resource inventory.

## 20. Quy trình phê duyệt trước khi mua

Một proposal cần có:

1. Workload inventory và owner.
2. Baseline 30/60/90 ngày hoặc chu kỳ dài hơn tùy workload.
3. Dự báo tăng trưởng, giảm tải và planned migrations.
4. Region/machine series/SKU/usage eligibility.
5. Discount/fee/term theo Cloud Billing account hiện hành.
6. Reservation scope, VM count, utilization target và end date.
7. Bản so sánh spot, on-demand, CUD, reservation + CUD.
8. Kịch bản xấu: preemption nhiều, demand giảm, zone unavailable.
9. Các chi phí phát sinh: storage, egress, retry, operations, DR.
10. Owner, financial approver, change window và audit.

### Không bỏ qua break-even

Ví dụ một commitment rẻ hơn on-demand khi dùng đủ mức nhưng phí cam kết vẫn phải trả trong thời gian workload đã dừng. Hãy tính đường hòa vốn theo utilization và loại hợp đồng cụ thể, kể cả các tình huống usage bị chuyển sang SKU không đủ điều kiện.

Đừng so sánh mỗi "discount rate" của Spot với CUD. Spot có rủi ro preemption; CUD tạo nghĩa vụ dài hạn; reservation có phí capacity chưa dùng. Bài toán thực tế là tổng chi phí hoàn thành mục tiêu vận hành với mức rủi ro chấp nhận được.

## 21. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chạy DB primary trên một Spot VM | Mất availability khi preempt | Standard/HA, backup và recovery |
| Tin rằng Spot có thể giữ capacity | Instance có thể không tạo được | Fallback hoặc reservation cho standard |
| Chỉ lưu trạng thái batch trong RAM | Mất tiến độ khi VM dừng | Checkpoint bền vững |
| Tin rằng shutdown luôn có đủ 30/120 giây | Job mất dữ liệu/không flush | Periodic checkpoint và idempotency |
| Mua CUD và nghĩ capacity đã được reserve | Vẫn có thể thiếu VM lúc peak | Reservation nếu cần assurance |
| Tạo reservation và nghĩ đã được discount | Trả phí unused reserved resources | Tính utilization và cân nhắc CUD |
| Chạy Spot rồi áp thêm flexible CUD | Tính sai mức tiết kiệm | Loại Spot khỏi eligible flexible usage |
| Mua commitment trước khi rightsizing | Baseline giảm dẫn đến underutilization | Rightsize trước, commitment sau |
| Dùng mức discount cao nhất làm giá mặc định | Forecast quá lạc quan | Pricing theo SKU/region/term thực |
| Không kiểm tra reservation affinity | VM không tiêu thụ chỗ đã giữ | Verify VM/reservation matching |
| Quên shared reservation billing | Project cost allocation sai | Review owner/consumer project và CUD sharing |
| Đếm reservation và VM thành hai phí compute độc lập | Cost double counting | Đối chiếu billing model và credits |
| Không lập ngày review reservation | Giữ capacity không dùng kéo dài | Có owner, review và delete policy |
| Không kiểm thử Spot preemption | Retry/rollback chưa hoạt động | Chaos/pilot test ở staging |
| Không tách standard và Spot SLO | Đánh giá độ tin cậy sai | SLO theo user journey và worker queue |

## 22. Checklist triển khai trên GCP

### Spot VMs

- [ ] Workload chịu được VM preempt bất kỳ lúc nào.
- [ ] Có idempotency, retry và checkpoint bền vững.
- [ ] Có giới hạn deadline và chính sách standard fallback.
- [ ] Đã cấu hình STOP/DELETE và hiểu ảnh hưởng lên disk.
- [ ] Đã xét notice 0s/120s cùng shutdown best effort.
- [ ] Đã benchmark interruption rate/cost per completed job.
- [ ] Không dựa vào Spot cho service có SLA critical mà thiếu fallback.
- [ ] Đã kiểm tra machine series, GPU và zone được hỗ trợ.
- [ ] Có metrics preemption, backlog, retries, cost và errors.

### Reservations

- [ ] Có yêu cầu capacity rõ ràng và owner.
- [ ] Có zone, machine type, GPU/Local SSD và quota hợp lệ.
- [ ] Biết reservation tự động hay specifically targeted.
- [ ] VM được cấu hình affinity phù hợp.
- [ ] Có tiêu chí reservation utilization và end/review date.
- [ ] Đã tính phí reserved capacity chưa được tiêu thụ.
- [ ] Đã xác minh shared reservation billing nếu có.
- [ ] Đã kiểm tra attached commitment restrictions trước khi sửa/xóa.
- [ ] Không kỳ vọng Spot VMs tiêu thụ reservation.

### CUD và FinOps

- [ ] Đã rightsizing trước khi mua commitment.
- [ ] Có usage baseline và growth/migration forecast.
- [ ] Đã phân biệt resource-based với flexible CUD.
- [ ] Đã xem region, account, project sharing và SKU eligibility.
- [ ] Đã đối chiếu term 1 năm/3 năm và phí cam kết.
- [ ] Không coi commitment là bảo đảm capacity.
- [ ] Không áp flexible CUD cho Spot workload.
- [ ] Có cost scenarios, break-even và sensitivity analysis.
- [ ] Có financial approval, audit và monitoring coverage/utilization.
- [ ] Đo realized savings qua Cloud Billing sau triển khai.

## Kết luận

Spot VMs, Compute Engine reservations và Committed Use Discounts phục vụ ba bài toán tách biệt: **chi phí cho workload chấp nhận gián đoạn**, **độ chắc chắn có capacity**, và **giá ưu đãi cho baseline ổn định**. Spot phù hợp với batch, CI và workers có checkpoint; reservation hữu ích cho migration, capacity planning và DR nhưng tốn phí ngay cả khi chưa sử dụng; CUD có thể giảm giá đáng kể nhưng tạo nghĩa vụ 1–3 năm và không tự giữ chỗ. Một chiến lược FinOps tốt bắt đầu từ dữ liệu utilization và SLO, thực hiện rightsizing, sau đó chọn công cụ phù hợp cho từng tầng workload. Cần đo cả **reliability lẫn chi phí thực tế** để tránh tiết kiệm trên bảng giá nhưng tăng rủi ro vận hành.

## Tài liệu tham khảo

- [Compute Engine: Spot VMs overview](https://docs.cloud.google.com/compute/docs/instances/spot)
- [Compute Engine: Create and use Spot VMs](https://docs.cloud.google.com/compute/docs/instances/create-use-spot)
- [Compute Engine: Spot VM best practices](https://docs.cloud.google.com/compute/docs/instances/spot-best-practices)
- [Compute Engine: Reservations overview](https://docs.cloud.google.com/compute/docs/instances/reservations-overview)
- [Compute Engine: Create single-project reservation](https://docs.cloud.google.com/compute/docs/instances/reservations-single-project)
- [Compute Engine: Consume reservations](https://docs.cloud.google.com/compute/docs/instances/reservations-consume)
- [Compute Engine: View reservations](https://docs.cloud.google.com/compute/docs/instances/reservations-view)
- [Compute Engine: Monitor reservation consumption](https://docs.cloud.google.com/compute/docs/instances/reservations-monitor)
- [Compute Engine: Committed use discounts](https://docs.cloud.google.com/compute/docs/instances/committed-use-discounts-overview)
- [Compute Engine: Combine reservations and commitments](https://docs.cloud.google.com/compute/docs/instances/reservations-with-commitments)
- [Compute Engine: View resource-based commitments](https://docs.cloud.google.com/compute/docs/committed-use-discounts/view-resource-based-commitments)
- [Cloud Billing: Cost optimization](https://docs.cloud.google.com/billing/docs/how-to/cost-management)
- [Cloud Billing: Export data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)

