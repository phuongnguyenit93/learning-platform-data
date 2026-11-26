# Container resource requests và limits khi triển khai Spring Batch

Khi chạy Spring Batch trên Kubernetes, tăng số luồng hoặc số worker chỉ có ý nghĩa nếu mỗi container được cấp tài nguyên phù hợp và toàn bộ hệ thống còn đủ năng lực xử lý. Cấu hình `resources.requests` và `resources.limits` quyết định Pod có được xếp lịch hay không, khả năng cạnh tranh CPU, mức sử dụng bộ nhớ cho phép và cách ứng dụng phản ứng khi tải tăng. Một Job có thể hoạt động tốt trên máy phát triển nhưng chạy rất chậm, `Pending` hoặc bị `OOMKilled` khi triển khai nếu bỏ qua các giới hạn này.

Bài học thuộc phần **Triển khai** của module **SPRING_BATCH_SCALING_OPERATIONS**, tập trung vào cách lựa chọn, đo lường và vận hành resource requests/limits cho Spring Batch có multi-threaded step, parallel steps, partitioning hoặc worker phân tán. Mục tiêu là tạo cấu hình có cơ sở từ số đo thực tế, duy trì khả năng retry/restart và tránh chuyển nút thắt sang cơ sở dữ liệu hay dịch vụ bên ngoài.

## 1. Phân biệt `requests` và `limits`

Kubernetes cấu hình tài nguyên chủ yếu theo **container** nằm trong Pod:

| Thuộc tính | CPU | Memory |
|---|---|---|
| `requests` | Lượng CPU dùng để xếp lịch Pod; còn ảnh hưởng đến tỷ trọng CPU khi các container cạnh tranh | Lượng bộ nhớ để scheduler kiểm tra khả năng đáp ứng của node |
| `limits` | Mức CPU tối đa container được sử dụng theo cơ chế quota/throttling; chạm ngưỡng thường làm chậm xử lý | Ngưỡng bộ nhớ của container; vượt ngưỡng có thể bị hệ điều hành kết thúc bằng OOM kill |
| Khi dùng ít hơn requests | CPU không bị giữ riêng hoàn toàn cho container; tài nguyên nhàn rỗi có thể được chia sẻ | Không có nghĩa bộ nhớ được cấp phát ngay khi Pod bắt đầu |
| Khi muốn dùng vượt requests | Có thể dùng thêm CPU nếu node còn khả năng và chưa chạm limit | Có thể dùng thêm bộ nhớ nếu chưa chạm limit và node còn bộ nhớ; khi node thiếu bộ nhớ vẫn có nguy cơ eviction |

Các đơn vị thông dụng:

- `cpu: "500m"` nghĩa là **0,5 CPU**; `cpu: "2"` là **2 CPU**, tương ứng với đơn vị CPU Kubernetes quy ước.
- `memory: "1Gi"` là **1.024 MiB**; `2Gi` là **2.048 MiB**. `Gi` dùng lũy thừa 2, còn `G` dùng lũy thừa 10.
- Resource request **không phải** số luồng Java, và CPU limit **không phải** cấu hình số kết nối đến cơ sở dữ liệu.

Ví dụ, container có `requests.cpu: 500m` và `limits.cpu: 2` được scheduler tính khoảng 0,5 CPU khi bố trí lên node; trong thời gian có CPU rảnh, container có thể sử dụng đến mức quota tương ứng 2 CPU. Nếu liên tục cần CPU cao hơn quota, các thread vẫn tồn tại nhưng có thể bị throttling, làm tăng thời gian hoàn thành Job.

Với memory, `requests.memory: 1Gi` và `limits.memory: 2Gi` cho phép mức sử dụng vượt request trong những điều kiện phù hợp, nhưng khi tiến gần hoặc vượt limit, Java có thể bị kết thúc trước khi ghi log lỗi heap một cách đầy đủ. CPU và memory vì vậy cần được đánh giá khác nhau: **CPU thiếu thường gây trễ; memory vượt limit có thể làm mất tiến trình**.

### Scheduler và QoS

Scheduler chủ yếu dựa trên **requests** để xét tài nguyên node. Một Pod có memory request 8Gi có thể bị `Pending` dù ứng dụng thực tế mới cần 2Gi, nếu cluster không có node nào thỏa điều kiện xếp lịch. Ngược lại, request rất thấp giúp Pod dễ được xếp lịch nhưng dễ tạo áp lực bộ nhớ khi nhiều Pod cùng sử dụng gần limit.

Kubernetes phân loại QoS cho Pod:

| QoS | Điều kiện tiêu biểu | Ý nghĩa thực tế |
|---|---|---|
| `Guaranteed` | Mọi container khai báo request và limit cho **cả CPU lẫn memory**, với request bằng limit ở từng tài nguyên | Dự trù tài nguyên rõ ràng hơn; thường được ưu tiên bảo vệ hơn trong tình huống node chịu áp lực tài nguyên |
| `Burstable` | Có khai báo request/limit nhưng không thỏa điều kiện Guaranteed | Phù hợp khi tải có đỉnh ngắn và muốn dành khoảng tăng tốc |
| `BestEffort` | Không khai báo CPU/memory request và limit | Dễ bị ảnh hưởng bởi cạnh tranh tài nguyên; ít phù hợp với batch quan trọng |

QoS không thay thế việc quan sát áp lực bộ nhớ, priority, taints/tolerations hoặc chính sách eviction của node. Không nên đặt request bằng limit chỉ để lấy nhãn Guaranteed khi điều đó khiến cluster không thể xếp lịch workload.

## 2. Vì sao scaling Spring Batch dễ chạm giới hạn container?

Một Job Spring Batch không chỉ tiêu thụ CPU của `ItemProcessor`. Tài nguyên còn được sử dụng bởi `ItemReader`, `ItemWriter`, buffer chunk, transaction, kết nối JDBC, thread stack, cache, thư viện native, giao tiếp mạng và garbage collector của JVM.

| Mô hình | Áp lực tài nguyên đáng chú ý | Điều cần kiểm tra trước khi tăng song song |
|---|---|---|
| Single-threaded step | Một luồng xử lý có thể chờ I/O lâu; heap tích lũy theo chunk/batch | CPU thực dùng, thời gian truy vấn và ghi dữ liệu, kích thước chunk |
| Multi-threaded step | Nhiều chunk/transaction đồng thời, thêm thread stack và kết nối DB | Thread safety của reader/writer, kích thước executor, connection pool |
| Parallel steps | Nhiều pipeline cùng lúc, tổng mức dùng bộ nhớ và kết nối tăng | Các step có chạy chồng nhau không, bước nào có peak cao nhất |
| Local partitioning | Nhiều StepExecution trong một JVM/Pod | Tổng số worker chạy đồng thời và trạng thái được chia sẻ |
| Remote partitioning / remote chunking | Nhiều Pod/worker với nhu cầu tài nguyên riêng; manager, broker, DB cũng chịu tải | Tổng requests toàn cụm, tốc độ queue, số kết nối, idempotency, retry/restart |

Ví dụ, nâng executor từ 2 lên 16 thread trong một Pod bị giới hạn 1 CPU có thể khiến 16 chunk cùng cạnh tranh CPU và truy cập database, tăng thời gian GC hoặc độ trễ transaction. Nếu writer bị giới hạn bởi tốc độ database, tăng limit CPU hoặc số Pod cũng không làm throughput tăng tương ứng.

Một cách hiểu hữu ích là phân biệt hai tầng:

1. **Song song trong Pod**: `TaskExecutor`, parallel steps, local partitioning; tất cả phải chia sẻ quota CPU và memory của container.
2. **Song song giữa các Pod**: worker của remote partitioning/chunking; mỗi Pod có requests/limits riêng nhưng cùng chia sẻ DB, broker, storage và giới hạn cluster.

Không tự tăng `spec.parallelism` của Kubernetes Job để nhân bản một Spring Batch Job thông thường. Nếu các Pod cùng khởi chạy một logic Job với cùng tập dữ liệu mà không có giao thức phân chia công việc, chúng có thể chạy trùng hoặc tranh chấp cùng JobInstance. Khi cần phân tán, phải định nghĩa rõ partition, định danh worker, phạm vi dữ liệu và cơ chế restart trước.

## 3. Ví dụ manifest cho một Spring Batch Job

Ví dụ sau dùng một Pod chạy Spring Batch trên Java 17+; các giá trị là **điểm khởi đầu để đo**, không phải mặc định phù hợp cho mọi hệ thống:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: invoice-reconciliation-20261126
  namespace: batch
spec:
  backoffLimit: 1
  template:
    metadata:
      labels:
        app: invoice-reconciliation
    spec:
      restartPolicy: Never
      containers:
        - name: batch
          image: registry.example.com/finance/reconciliation:1.4.0
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=60 -XX:+ExitOnOutOfMemoryError"
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
```

Với cấu hình này:

- Kubernetes tính **0,5 CPU và 1Gi memory** vào nhu cầu xếp lịch của container.
- Container có thể dùng đến **2 CPU**, nếu workload có nhu cầu và cluster đáp ứng được; vượt quota sẽ bị throttling.
- Giới hạn memory là **2Gi cho toàn bộ tiến trình trong container**, bao gồm Java heap và phần ngoài heap.
- `-XX:MaxRAMPercentage=60` đặt heap tối đa xấp xỉ 60% memory mà JVM container-aware nhận diện, tức khoảng **1,2Gi** trong tình huống JVM nhận diện giới hạn 2Gi. Phần còn lại vẫn phải đủ cho metaspace, direct buffers, native memory, thread stack và chi phí tiến trình.
- `-XX:+ExitOnOutOfMemoryError` giúp JVM dừng khi phát sinh một số Java `OutOfMemoryError`; nó **không** ngăn được container bị kernel OOM kill khi vượt cgroup memory limit.
- `backoffLimit: 1` giới hạn số lần Kubernetes Job controller thử lại khi Pod thất bại theo chính sách Job. Việc thử lại ở Kubernetes **không bảo đảm** Spring Batch tự resume đúng checkpoint.

Đường dẫn image và namespace trong ví dụ cần được thay bằng giá trị thật. Production thường còn cần Secret, quyền service account, cấu hình logging, network policy và cơ sở dữ liệu chứa `JobRepository`.

**Quan trọng với retry/restart:** `JobRepository` phải tồn tại bền vững bên ngoài Pod nếu cần restart sau khi Pod chết. Writer phải bảo đảm idempotency hoặc cơ chế chống ghi trùng; JobParameters, JobInstance và partition identity cần được điều phối nhất quán. Nếu mỗi lần retry tạo tham số nhận diện Job mới, Spring Batch có thể coi đó là một lần chạy mới thay vì tiếp tục lần chạy bị lỗi.

### Tài nguyên JVM và Spring Batch cần đồng bộ

Không nên đặt `-Xmx` bằng toàn bộ `limits.memory`. Một JVM có heap 2Gi trong container memory 2Gi vẫn có thể vượt limit bởi bộ nhớ ngoài heap. Có thể dùng `-Xmx` cố định hoặc `MaxRAMPercentage` theo điều kiện triển khai, nhưng phải đo peak của **toàn container**; đừng chỉ xem biểu đồ heap.

Nếu dùng multi-threaded step, cần giới hạn executor tương ứng với CPU, memory và kết nối DB. Ví dụ cấu hình bean executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BatchConcurrencyConfig {

    @Bean("batchTaskExecutor")
    public ThreadPoolTaskExecutor batchTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("batch-");
        executor.initialize();
        return executor;
    }
}
```

Bean trên chỉ tạo executor. Step phải được **cấu hình sử dụng executor đó**; việc tạo bean không tự động biến mọi step thành multi-threaded. Đồng thời, reader/writer cần được đánh giá tính thread-safe, transaction boundary phải phù hợp, và pool kết nối của DataSource phải đủ cho số thao tác DB chạy đồng thời nhưng không vượt quá năng lực database.

Trong container bị giới hạn 2 CPU, `maxPoolSize=4` có thể hợp lý nếu nhiều tác vụ chờ I/O, nhưng có thể gây cạnh tranh nếu toàn bộ là CPU-bound. Số 4 phải được xác nhận bằng benchmark và số liệu throttling.

## 4. Cách xác định request và limit từ số đo

Một quy trình thực dụng gồm năm bước.

### Bước 1: Đo baseline với khối lượng dữ liệu đại diện

Chạy Job trong môi trường giống production về cấu hình JVM, phiên bản schema, tốc độ DB/network và loại dữ liệu. Dùng dữ liệu có bản ghi lớn, độ phân bố không đều và truy vấn khó, thay vì chỉ kiểm tra vài trăm bản ghi mẫu.

Thu thập tối thiểu:

- Throughput: số item hoặc chunk hoàn thành mỗi giây; thời lượng toàn Job và từng step; độ trễ đọc, xử lý, ghi.
- CPU: mức CPU thực sử dụng, tỷ lệ thời gian bị throttling, trạng thái node.
- Memory: memory working set của container, Java heap dùng sau GC, peak heap, GC pause, direct/native memory nếu có.
- I/O: độ trễ truy vấn, pool kết nối DB đang dùng/chờ, độ trễ broker hoặc API, disk/network throughput.
- Độ tin cậy: số lần retry/skip, transaction rollback, tốc độ hồi phục sau restart và tính đúng của kết quả.

Đo cả peak khi chạy đồng thời và lúc chuyển giai đoạn xử lý. Giá trị trung bình của một Job nhiều giờ có thể che mất đỉnh memory lúc writer gom dữ liệu hoặc nhiều partition hoàn thành cùng lúc.

### Bước 2: Ước tính requests

CPU request được chọn từ lượng CPU thường cần để đạt tốc độ yêu cầu trong điều kiện cạnh tranh hợp lý; memory request cần phản ánh bộ nhớ thực sự cần trong phần lớn thời gian chạy để Pod có cơ hội được xếp lịch lên node phù hợp.

Ví dụ quan sát một worker có CPU thường 0,4–0,7 CPU và memory working set khoảng 0,8–1,1Gi. Có thể thử request CPU 500m, memory 1Gi, sau đó kiểm tra sức tải và mức ổn định thực tế. Nếu peak thường xuyên vượt xa request, cần xem lại request hoặc số Pod vì cluster có thể bị overcommit và chịu áp lực tài nguyên.

### Bước 3: Xác định limits từ peak và yêu cầu ổn định

Với memory, cần dành dư địa cho heap, native memory, thread stack, buffer và biến động của dữ liệu. Limit chỉ nhỉnh hơn peak đã đo có thể không đủ khi input tăng hoặc GC hành xử khác; phải kiểm thử bằng dữ liệu xấu nhất hợp lý.

Với CPU, đặt limit thấp dễ tạo throttling cho các giai đoạn đòi CPU đột biến, ngay cả khi CPU trung bình có vẻ thấp. Một số workload batch phù hợp với **CPU request rõ ràng và CPU limit thoáng hơn**, hoặc không đặt CPU limit nếu chính sách cluster cho phép và có giám sát đầy đủ. Việc bỏ CPU limit không xóa bỏ cạnh tranh CPU giữa Pod trên cùng node.

### Bước 4: Tính tổng nhu cầu của nhiều Pod

Với `N` Pod worker giống nhau, chỉ xét container worker:

```text
CPU requested toàn nhóm    = N × requests.cpu mỗi worker
Memory requested toàn nhóm = N × requests.memory mỗi worker
CPU limit danh nghĩa       = N × limits.cpu mỗi worker
Memory limit danh nghĩa    = N × limits.memory mỗi worker
```

Nếu chạy 8 worker với request `500m / 1Gi` và limit `2 CPU / 2Gi`, scheduler cần bố trí tổng cộng **4 CPU request và 8Gi memory request** (chưa tính manager, sidecar và các Pod khác). Tổng giới hạn danh nghĩa là **16 CPU và 16Gi memory**, nhưng những con số limit **không phải phần tài nguyên cluster đã dành sẵn**. Tất cả worker có thể cùng chạm đỉnh và cạnh tranh tài nguyên node.

Với Pod có nhiều container, cần cộng nhu cầu của các container và xét thêm cách Kubernetes hạch toán init container, Pod overhead, quota namespace và tài nguyên node có thể cấp phát (allocatable). Đừng so sánh yêu cầu workload trực tiếp với tổng CPU/RAM vật lý của node mà bỏ qua phần hệ thống sử dụng.

### Bước 5: Kiểm thử trước khi tăng quy mô

Thử tăng worker theo các mức, chẳng hạn 1 → 2 → 4 → 8, đồng thời giữ cố định loại dữ liệu, database và yêu cầu đầu ra. Ghi lại throughput tổng, CPU/memory theo Pod, tỷ lệ throttling, thời gian chờ DB và tỷ lệ lỗi. Nếu thêm Pod không còn cải thiện thời gian hoàn thành, xác định nút thắt mới trước khi tiếp tục tăng tài nguyên.

## 5. Bài toán sizing cụ thể

Giả sử một hệ thống cần đối soát **12 triệu bản ghi trong 90 phút**. Benchmark một worker với cấu hình trong manifest cho thấy tốc độ ổn định **450 item/giây** trên dữ liệu đại diện; memory peak vẫn thấp hơn 2Gi và DB chưa quá tải.

Thông lượng trung bình tối thiểu theo mục tiêu:

```text
12.000.000 / (90 × 60) ≈ 2.222 item/giây
```

Nếu khả năng mở rộng gần tuyến tính, 5 worker cho khoảng 2.250 item/giây, gần sát yêu cầu và rất ít dư địa cho lỗi, skew hoặc thời gian khởi động. Có thể **thử nghiệm** 6 worker:

```text
Thông lượng lý thuyết: 6 × 450 = 2.700 item/giây
Thời gian lý thuyết: 12.000.000 / 2.700 ≈ 74 phút
CPU requests:          6 × 500m = 3 CPU
Memory requests:       6 × 1Gi  = 6Gi
CPU limits danh nghĩa: 6 × 2    = 12 CPU
Memory limits:         6 × 2Gi  = 12Gi
```

Đây là **ước lượng**, không phải cam kết SLA. Nếu 6 worker tạo ra quá nhiều kết nối DB, lock contention, hàng đợi broker hoặc tranh chấp I/O, throughput thực tế có thể thấp hơn đáng kể. Cần đo trong điều kiện tải đồng thời, kiểm tra phân phối partition và thêm headroom cho node, manager, monitoring và hệ thống lưu trữ.

Đặc biệt, nếu Spring Batch đang xử lý theo partition, mỗi worker phải nhận phạm vi dữ liệu riêng và có khả năng chạy lại an toàn. Tăng số Pod mà phân chia dữ liệu không đúng có thể tạo throughput giả vì đếm trùng bản ghi.

## 6. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng điều chỉnh |
|---|---|---|
| Pod `Pending`, không bắt đầu Job | Requests quá cao so với allocatable của node; ResourceQuota, LimitRange, node selector, affinity hoặc taints | Xem sự kiện Pod, quota, khả năng node; giảm requests khi số đo cho phép hoặc bổ sung capacity |
| Job chậm, CPU cao, không OOM | CPU-bound, CPU throttling do limit thấp, số thread quá nhiều hoặc GC tốn CPU | Đo throttling và CPU usage; điều chỉnh CPU limit/request, pool, chunk hoặc thuật toán |
| `OOMKilled`, exit code thường là 137 | Toàn bộ bộ nhớ container vượt cgroup limit; heap hoặc native memory/buffer tăng | Đo memory peak, giảm chunk/buffer/concurrency, điều chỉnh heap và memory limit |
| Pod bị `Evicted` | Node chịu pressure tài nguyên; Pod có thể dùng memory vượt request hoặc gây áp lực ephemeral storage | Kiểm tra lý do eviction, request thực tế, node capacity và phần dữ liệu tạm |
| CPU còn rảnh nhưng tốc độ không tăng | Chờ database, network, broker, lock hoặc pool connection | Đo thời gian chờ I/O, độ trễ truy vấn, quota downstream trước khi tăng Pod |
| Job bị chạy lại hoặc ghi trùng sau Pod failure | Thiết kế JobParameters/JobRepository hoặc writer chưa restart-safe | Dùng metadata bền vững, partition identity ổn định và idempotent write |
| Nhiều worker cùng OOM vào cuối step | Chunk/buffer hoặc kết quả trung gian tăng cùng thời điểm | Kiểm tra peak memory theo thời điểm; giảm in-flight item hoặc tách giai đoạn |

**Cần phân biệt lỗi Java heap và lỗi giới hạn container.** Java `OutOfMemoryError: Java heap space` là một dạng thiếu bộ nhớ trong JVM; `OOMKilled` trong trạng thái container cho thấy kernel đã kết thúc tiến trình vì vượt ràng buộc bộ nhớ, thường không có cơ hội cleanup. Exit code 137 chỉ cho biết tiến trình bị SIGKILL; kết hợp với `reason: OOMKilled` và events mới đủ cơ sở chẩn đoán OOM.

Các lệnh thường dùng (thay namespace và tên Job/Pod thực tế):

```bash
kubectl get jobs -n batch
kubectl get pods -n batch -l app=invoice-reconciliation
kubectl describe pod -n batch <pod-name>
kubectl top pod -n batch --containers
kubectl get resourcequota -n batch
kubectl get limitrange -n batch
kubectl logs -n batch <pod-name> -c batch
kubectl logs -n batch <pod-name> -c batch --previous
```

Lệnh `kubectl top` cần Metrics Server hoặc nguồn metrics tương thích; nó cung cấp ảnh chụp mức dùng gần hiện tại, **không thay thế việc thu thập peak và lịch sử dài hạn**. `kubectl logs --previous` chỉ hữu ích khi có phiên bản container trước đó trong Pod và log còn được giữ. Với Pod bị xóa và thay bằng Pod mới, phải tra log tập trung hoặc sự kiện phù hợp.

Nếu dùng Prometheus/cAdvisor hoặc hệ thống quan sát tương tự, nên theo dõi CPU usage, mức throttled CPU theo thời gian, container memory working set/peak, số lần restart/OOM, thời lượng Job, chunk latency, throughput, heap/GC, Hikari pool và trạng thái broker. Tên metrics cụ thể phụ thuộc runtime và cấu hình export của cluster.

## 7. Điều chỉnh phối hợp với thread pool, chunk size và hệ thống bên ngoài

Một thay đổi về tài nguyên container có thể đòi hỏi thay đổi cách xử lý dữ liệu:

- **CPU-bound processor:** ưu tiên benchmark giới hạn CPU phù hợp và số worker/threads vừa phải; nếu throttling nhiều, so sánh tác động của tăng CPU quota với giảm concurrency.
- **I/O-bound reader/writer:** một số thread bổ sung có thể tăng throughput, nhưng connection pool và giới hạn DB/API phải được tính đồng thời. Nếu DB chỉ cho phép thêm 20 kết nối, nhiều Pod × nhiều thread không thể mặc định được sử dụng ồ ạt.
- **Chunk lớn:** giảm số transaction nhưng có thể giữ nhiều item trong memory, kéo dài thời gian rollback và tăng peak heap. Chọn chunk size từ kết quả đo, đặc biệt khi bản ghi có kích thước không đều.
- **Remote workers:** áp cùng phương pháp sizing cho từng loại manager/worker; manager có thể ít CPU nhưng cần kết nối broker và độ ổn định cao, còn worker tiêu thụ CPU/heap theo partition.
- **Ephemeral storage:** Job tạo file tạm, sort spill hoặc staging cần xem thêm `ephemeral-storage` request/limit, `emptyDir` và tài nguyên disk node; CPU/memory không phản ánh đầy đủ loại tải này.

Ví dụ về giới hạn downstream: có 6 worker, mỗi worker có tối đa 4 thao tác JDBC đồng thời thì tổng số thao tác có thể đến **24** trước khi cộng kết nối của manager và dịch vụ khác. Nếu database chỉ chịu thêm 12 truy vấn đồng thời với độ trễ chấp nhận được, tăng CPU limit của worker không giải quyết được tình trạng chờ DB. Cần giảm concurrency hoặc phân phối lại công việc.

## 8. Vận hành trong cluster và lựa chọn chính sách phù hợp

Khi triển khai nhiều Job cùng thời gian, cần kiểm tra cả giới hạn ở cấp namespace:

- **`ResourceQuota`** có thể giới hạn tổng requests/limits hoặc số Pod/Job trong namespace. Pod hoặc Job mới có thể bị chặn dù vài node còn CPU.
- **`LimitRange`** có thể đặt min/max/default cho request và limit. Giá trị được admission áp dụng có thể khác nội dung manifest nếu người viết bỏ sót trường.
- **Cluster autoscaler** có thể thêm node khi tồn tại Pod không thể xếp lịch vì thiếu capacity, nếu cluster được cấu hình cho phép; việc scale phụ thuộc node pool, quota và thời gian khởi động.
- **Horizontal Pod Autoscaler (HPA)** thường nhắm các workload như Deployment; không coi nó là bộ điều khiển tự động của một Kubernetes Job hữu hạn. Muốn điều chỉnh số worker batch cần thiết kế rõ controller/queue/partition và quy tắc hoàn thành công việc.
- **CPU-based autoscaling** tính utilization tương đối với CPU requests trong các cấu hình HPA dùng resource metric; request không hợp lý có thể làm tín hiệu autoscale sai lệch.

Về chính sách, `Guaranteed` hữu ích khi cần dự trù chặt và capacity đủ lớn; `Burstable` thường linh hoạt cho batch có đỉnh theo giai đoạn. Nếu đặt CPU limit, cần đo tác động của throttling lên thời gian hoàn thành; nếu không đặt CPU limit, vẫn phải theo dõi tình trạng CPU contention và tôn trọng chính sách tài nguyên của cluster. Memory limit nên có cơ sở từ phép đo và vùng dự phòng, vì sai số ở đây có thể khiến Job bị kill.

Không dùng retry vô hạn để che lỗi thiếu tài nguyên. Khi Pod liên tục `OOMKilled`, Kubernetes tạo thêm attempt chỉ tái diễn cùng lỗi và có thể làm tăng số lần truy cập dữ liệu ngoài. Khôi phục Job phải đi kèm **kiểm soát số lần thử**, khả năng resume theo `ExecutionContext`/`JobRepository` và kiểm tra tác động của những commit đã thành công.

## 9. Checklist trước khi đưa vào production

1. Đã đo throughput, CPU, container memory peak, heap/GC, DB/broker latency trên tập dữ liệu đại diện và tại mức concurrency dự kiến.
2. Đã khai báo tường minh CPU/memory requests và memory limit cho từng container; đã đánh giá CPU limit theo dấu hiệu throttling.
3. Đã tính tổng requests của manager, worker, sidecar và các Pod chạy đồng thời; kiểm tra node allocatable, namespace quota và headroom.
4. Đã gắn số luồng, chunk size, connection pool và số partition với tài nguyên thực tế; reader/writer chịu được concurrency.
5. Đã chạy thử các tình huống Pod bị kill, Job retry, dữ liệu skew và worker thất bại giữa transaction; kết quả sau restart không trùng hoặc thiếu dữ liệu.
6. Đã có dashboard/alert cho `Pending`, `OOMKilled`, `Evicted`, throttling kéo dài, Job duration vượt SLA và mức sử dụng DB/queue.
7. Đã kiểm chứng cách JobParameters, JobRepository và work partition được duy trì qua mỗi lần Kubernetes tạo Pod mới.

## 10. Bài tập vận dụng

**Tình huống A:** Một Pod chạy multi-threaded step với 12 thread, `requests.cpu=500m`, `limits.cpu=1`. CPU usage gần 1 CPU, throttling tăng và thời gian Job xấu đi khi tăng từ 6 lên 12 thread. Hãy so sánh hai phép thử: giữ 6 thread với CPU limit hiện tại, và dùng 12 thread với CPU limit cao hơn (khi node đủ năng lực). Đo throughput, CPU throttling, GC và DB latency; chỉ chấp nhận cấu hình mới nếu cải thiện được thời gian hoàn thành mà không tạo nút thắt khác.

**Tình huống B:** Tám worker remote partitioning cùng chạy, mỗi worker request 1Gi và limit 2Gi memory. Trong giờ cao điểm, nhiều worker lên đến 1,9Gi và node xảy ra memory pressure. Hãy tính tổng request (**8Gi**) và tổng limit (**16Gi**) của các worker; kiểm tra mức dùng thực, headroom node, giới hạn manager/sidecar, dữ liệu skew và chunk size. Đề xuất phương án điều chỉnh request, hạn chế worker đồng thời hoặc bổ sung node; sau đó thử restart một partition đang chạy để xác nhận không mất hoặc ghi trùng dữ liệu.

Các giá trị requests/limits tốt là kết quả của **đo tải → xác định nút thắt → đặt ngân sách tài nguyên → kiểm thử lại**. Với Spring Batch, cấu hình container chỉ hoàn chỉnh khi tốc độ xử lý, độ ổn định JVM, sức chịu tải downstream và khả năng restart đều được chứng minh bằng số liệu.
