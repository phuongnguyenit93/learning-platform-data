# Thiết kế phép đo có tải tương đương, lặp lại và kiểm soát môi trường

Đánh giá hiệu năng CRaC chỉ có ý nghĩa khi phép đo so sánh hai cách khởi chạy trong điều kiện tương đương. Nếu một lần chạy cold start dùng CPU đang bận, database lạnh và tải lớn, còn lần restore chạy trên node rảnh với cache đã nóng, kết quả không cho biết lợi ích thực sự của checkpoint. Ngược lại, nếu chỉ đo thời gian JVM restore mà bỏ qua image pull, volume mount, reconnect dependency và readiness, kết quả có thể không phản ánh thời gian triển khai mà người vận hành quan tâm.

Một benchmark đáng tin cậy cần xác định rõ câu hỏi cần trả lời, đo riêng từng giai đoạn, dùng cùng workload và offered load, lặp lại nhiều lần, kiểm soát môi trường, ghi nhận mọi sai khác và phân tích độ biến thiên. Với CRaC, nên tách ít nhất ba câu hỏi: restore giúp ứng dụng sẵn sàng nhanh hơn bao nhiêu, request đầu tiên sau restore có nhanh hơn không, và hiệu năng steady-state dưới cùng tải có thay đổi không.

Không có một con số duy nhất đại diện cho “hiệu năng CRaC”. Thời gian tạo checkpoint, thời gian restore, thời gian từ deploy đến readiness, latency của request đầu tiên, throughput, CPU, bộ nhớ và chi phí lưu trữ trả lời những câu hỏi khác nhau. Thiết kế phép đo tốt phải nói rõ mỗi chỉ số bắt đầu/kết thúc ở đâu và điều kiện nào được giữ cố định.

## 1. Xác định câu hỏi và phạm vi phép đo

Trước khi chạy benchmark, hãy viết một giả thuyết có thể kiểm chứng. Ví dụ:

- Restore từ checkpoint giảm thời gian từ lúc container bắt đầu chạy đến khi readiness thành công.
- Warm-up được lưu trong checkpoint làm giảm latency của 100 request đầu tiên.
- Sau khi cả hai cách chạy đạt steady-state, throughput và p95 gần tương đương.
- Restore làm tăng mức sử dụng bộ nhớ ban đầu hoặc thời gian đọc storage.
- Khi scale 20 replica cùng lúc, CRaC giảm thời gian sẵn sàng nhưng tạo burst kết nối database.

Mỗi giả thuyết cần một nhóm chỉ số và một quy trình riêng. Đừng gộp tất cả thành một benchmark duy nhất rồi chọn số thuận lợi nhất.

### Ba nhóm phép đo chính

| Nhóm | Câu hỏi | Điểm đo quan trọng |
|---|---|---|
| Startup/restore | Ứng dụng sẵn sàng phục vụ nhanh đến mức nào? | Process start/restore invocation đến readiness; deploy-to-ready nếu tính cả hạ tầng |
| First-request | Người dùng đầu tiên sau restore có phải trả chi phí khởi tạo không? | Latency request đầu tiên và phân bố latency của N request đầu |
| Steady-state | Khi chạy ổn định dưới tải tương đương, hai cách chạy khác nhau thế nào? | Throughput, p50/p95/p99, error rate, CPU, allocation, GC, memory và dependency load |

Ngoài ba nhóm trên, có thể đo riêng chi phí tạo checkpoint, kích thước artifact, thời gian push/pull, volume mount/copy và chi phí vận hành. Những chỉ số này quan trọng khi tính tổng lợi ích trong pipeline và production.

### Xác định phạm vi đồng hồ

Một con số “startup time” có thể bao gồm hoặc loại trừ nhiều giai đoạn. Nên đặt tên riêng cho từng khoảng:

```text
T_deploy_to_ready
  = scheduling
  + image pull
  + volume attach/mount
  + init container / checkpoint copy
  + process launch hoặc restore
  + reconnect dependency
  + readiness checks

T_process_to_ready
  = process launch / restore invocation
  + runtime và application startup
  + reconnect dependency
  + readiness checks

T_ready_to_first_success
  = thời gian từ readiness đến request đầu tiên thành công
```

Nếu mục tiêu là đánh giá trải nghiệm triển khai, đo `T_deploy_to_ready`. Nếu mục tiêu là so sánh runtime, đo thêm `T_process_to_ready`. Nếu checkpoint được đặt trong image layer còn cold start đã có image cache trên node, hãy ghi rõ image pull có được tính hay không. Không so sánh hai con số có phạm vi khác nhau.

## 2. Thiết lập baseline và các nhóm thử nghiệm

Baseline là cách chạy dùng để đối chiếu. Với ứng dụng CRaC, thường có ít nhất hai nhóm:

- **Cold start:** khởi chạy ứng dụng từ artifact và runtime đã chọn, thực hiện startup bình thường.
- **CRaC restore:** restore từ checkpoint được tạo từ cùng application build và runtime tương thích.

Nếu cần đánh giá lợi ích warm-up, cần ghi rõ checkpoint được tạo sau tập warm-up nào. Một checkpoint chưa warm-up có thể chỉ giúp bỏ qua một phần khởi tạo; checkpoint sau warm-up có thể còn chứa trạng thái JIT/cache nội bộ có thể tái sử dụng.

Không nên dùng một build khác nhau cho hai nhóm. Hãy giữ cùng:

- Application JAR/container image và source commit.
- JDK vendor, version, build, JVM options và GC configuration.
- Cấu hình ứng dụng tĩnh và feature flags.
- Dataset, fixture, request mix và response size.
- Phiên bản database, broker, cache và dịch vụ phụ thuộc.
- CPU/memory limits, thread count, replica count và network path.
- Phiên bản load generator và benchmark script.

Nếu một nhóm bắt buộc dùng cấu hình khác để tạo checkpoint, ghi rõ khác biệt và xem đó là một biến của thí nghiệm. Không âm thầm thay đổi heap, GC, thread pool hoặc pool size giữa hai nhóm.

### Tách hiệu quả checkpoint khỏi chi phí tạo checkpoint

Có hai cách nhìn:

1. **Runtime benefit:** chỉ so sánh thời gian và tài nguyên từ lúc bắt đầu process/restore đến khi sẵn sàng.
2. **Lifecycle cost:** tính cả build, warm-up, checkpoint creation, lưu trữ, phân phối image/volume và restore.

Nếu checkpoint được tái sử dụng cho hàng trăm lần scale-out, chi phí tạo một lần có thể được phân bổ cho nhiều lần restore. Nếu checkpoint phải tạo lại thường xuyên hoặc chứa dữ liệu nhanh lỗi thời, chi phí chuẩn bị có thể đáng kể.

Ví dụ công thức tổng quát:

```text
total_cost_crac(N) =
    checkpoint_build_cost
    + checkpoint_storage_and_distribution_cost
    + N * restore_cost

total_cost_cold(N) =
    N * cold_start_cost
```

Đây là mô hình khái niệm; chi phí thực tế có thể tính bằng thời gian, CPU-seconds, tiền compute/storage/network hoặc kết hợp. Hãy báo cáo cả chi phí một lần và chi phí trên mỗi lần khởi chạy.

## 3. Thiết kế workload giống nhau

Hai nhóm phải nhận cùng một tập request theo cùng phân bố. “Cùng số request” chưa chắc là “cùng tải”: 10.000 request đọc cache có chi phí khác 10.000 request tìm kiếm database hoặc serialize payload lớn.

Hãy định nghĩa workload bằng các thuộc tính:

- Tỷ lệ từng route/use case.
- Payload shape, kích thước request và response.
- Tỷ lệ cache hit/miss.
- Tỷ lệ thành công, lỗi hợp lệ và retry.
- Tenant, user role hoặc feature flag làm thay đổi code path.
- Tần suất gọi dependency và số truy vấn trên mỗi request.
- Thời gian chạy và tốc độ gửi request.
- Concurrency, burst và thời điểm bắt đầu từng scenario.

### Ví dụ request mix

Giả sử dịch vụ xử lý đơn hàng có workload như sau:

| Scenario | Tỷ lệ request | Payload/đường chạy |
|---|---:|---|
| Đọc chi tiết đơn hàng | 40% | Response nhỏ/trung bình, có cache và repository |
| Tìm kiếm đơn hàng | 25% | Filter, sort, phân trang và truy vấn database |
| Xem trạng thái thanh toán | 15% | Gọi service phụ thuộc hoặc cache |
| Cập nhật thông tin giao hàng | 10% | Validation và ghi database trong fixture test |
| Luồng lỗi hợp lệ | 5% | Không tìm thấy, validation error hoặc quyền bị từ chối |
| Payload lớn | 5% | Danh sách nhiều phần tử hoặc response lớn |

Các tỷ lệ chỉ là ví dụ. Hãy lấy phân bố từ access log, trace hoặc mô hình tải đã được xác nhận. Dùng dữ liệu tổng hợp/ẩn danh và fixture có thể reset. Nếu có side effect, chạy trong môi trường cô lập và khôi phục trạng thái giữa các lần thử.

### Giữ nguyên dữ liệu và trạng thái cache

Cache là một biến rất dễ làm benchmark lệch. Nếu CRaC image chứa cache nóng còn cold-start test đọc database lạnh, phép đo có thể phản ánh cache state thay vì lợi ích restore. Điều này có thể là mục tiêu hợp lệ nếu đang đo checkpoint sau warm-up, nhưng phải được ghi rõ.

Nên có các chế độ thử nghiệm riêng:

- **Cache-neutral:** reset/chuẩn hóa cache trước mỗi lần thử để so sánh chi phí runtime.
- **CRaC-warm-cache:** cho phép cache nội bộ được checkpoint giữ lại; cold-start được warm-up theo cùng chính sách trước khi đo steady-state.
- **Production-realistic:** mô phỏng đúng trạng thái cache dự kiến khi scale-out, kể cả distributed cache và database buffer cache.

Không trộn kết quả của các chế độ này trong cùng một bảng mà không phân biệt. Ghi rõ cache nào nằm trong heap, cache nào nằm ngoài tiến trình và cache nào được reset giữa các trial.

## 4. Tải tương đương: offered load, concurrency và burst

Có hai mô hình tạo tải thường dùng:

- **Open-loop:** load generator gửi request theo tốc độ mục tiêu, độc lập với thời gian phản hồi trước đó. Mô hình này phù hợp để đánh giá hệ thống nhận một offered load cố định và phát hiện queueing/overload.
- **Closed-loop:** một số lượng virtual user/client gửi request tiếp theo sau khi request trước hoàn tất. Mô hình này phù hợp để đánh giá concurrency cố định, nhưng tốc độ gửi sẽ giảm khi server chậm.

Không có mô hình nào đúng cho mọi câu hỏi. Nếu muốn so sánh latency ở cùng arrival rate, open-loop thường dễ diễn giải hơn. Nếu muốn so sánh hiệu năng khi có số worker/client cố định, closed-loop có thể phù hợp. Hãy dùng cùng mô hình cho cả cold start và CRaC restore.

### Vì sao chỉ đặt cùng số virtual users có thể sai?

Trong closed-loop test, khi server chậm, client chờ lâu hơn rồi mới gửi request kế tiếp. Hệ thống nhận ít request hơn đúng lúc nó đang chậm. Điều này có thể che giấu latency tail, hiện tượng thường được gọi là *coordinated omission*.

Open-loop với arrival rate được xác định trước giúp nhìn thấy request đến trong lúc server đang bận. Tuy nhiên, load generator phải đủ năng lực và cần giới hạn queue của chính nó; nếu generator không gửi được tốc độ đã định, kết quả không còn là offered load mong muốn.

### Ví dụ với k6 constant arrival rate

Ví dụ sau dùng executor `constant-arrival-rate` để tạo tải open-loop. Cùng một file script và cùng fixture nên được dùng cho cả hai nhóm:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300'],
  },
};

const baseUrl = __ENV.BASE_URL;

export default function () {
  const response = http.get(`${baseUrl}/api/orders/benchmark-order-001`);
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
}
```

Các giá trị rate, duration, VU và threshold chỉ là ví dụ. Hãy điều chỉnh theo năng lực hệ thống, bảo đảm `preAllocatedVUs`/`maxVUs` đủ để tạo offered load mà không làm generator thành bottleneck. Nếu có nhiều route, hãy chọn route theo xác suất cố định hoặc dùng dữ liệu scenario có seed để hai nhóm nhận cùng phân bố.

### Kiểm tra load generator

Load generator phải chạy ở máy hoặc node độc lập với server được đo, có đủ CPU/network và không chia sẻ tài nguyên đáng kể với ứng dụng. Theo dõi CPU, network, dropped iterations, VU saturation và queue của generator. Nếu generator bị bão hòa, không được kết luận server đã đạt throughput tối đa.

## 5. Tách startup, request đầu tiên và steady-state

Đây là điểm quan trọng nhất khi đánh giá CRaC. Nếu chỉ đo steady-state sau vài phút, có thể bỏ qua lợi ích lớn nhất của warm-up trong checkpoint. Nếu chỉ đo request đầu tiên, lại không biết hiệu năng sau khi cả hai cách chạy ổn định.

### Experiment A: startup/restore đến readiness

Đo từ mốc bắt đầu được định nghĩa đến khi readiness thành công. Không gửi business traffic trong phép đo này, trừ các health/readiness probe mà hệ thống thực sự dùng.

Ghi nhận riêng:

- Container/Pod scheduling time.
- Image pull time.
- Volume attach/mount hoặc checkpoint copy time.
- JVM launch/restore time.
- CRaC `afterRestore()` callback duration.
- Dependency reconnect duration.
- Thời gian readiness probe chuyển sang ready.

Nếu benchmark chạy trực tiếp trên VM và không có container orchestration, có thể bỏ các giai đoạn không áp dụng nhưng cần giữ định nghĩa giống nhau giữa hai nhóm.

### Experiment B: request đầu tiên sau readiness

Sau khi readiness chuyển true, gửi request đại diện đầu tiên ngay theo một quy tắc cố định. Đo latency từ phía client và server nếu có thể. Tiếp tục đo một chuỗi request đầu tiên, ví dụ 1, 5, 10, 50, 100 request, để xem chi phí cold path giảm dần như thế nào.

Không chạy một đợt warm-up ẩn trước khi đo first-request. Nếu hệ thống cần health check tạo cache hoặc load class, ghi rõ vì nó có thể làm thay đổi kết quả. Health probe nên giống nhau giữa hai nhóm.

### Experiment C: steady-state dưới tải tương đương

Đối với câu hỏi steady-state, cho cả hai nhóm đi qua cùng giai đoạn ổn định trước khi bắt đầu cửa sổ đo. Giai đoạn này cần cùng duration, request mix và offered load. Sau đó đo trong một cửa sổ cố định, ví dụ 5–15 phút tùy workload và độ ổn định.

Lưu ý: warm-up bổ sung cho cold-start trong Experiment C làm giảm khác biệt ban đầu giữa hai nhóm. Điều đó là có chủ đích vì câu hỏi ở đây là hiệu năng ổn định sau khi cả hai đã warm. Không dùng kết quả Experiment C để kết luận về first-request latency.

### Experiment D: burst và scale-out

Nếu production thường tạo nhiều replica cùng lúc, đo kịch bản burst riêng. Khởi động một số replica theo cùng lịch, cùng dependency và cùng offered load. Quan sát image pull/volume read, CPU, connection creation rate, database sessions, consumer rebalance và thời gian tất cả replica đạt readiness.

Không suy rộng kết quả một replica thành kết quả scale-out. CRaC có thể giảm thời gian khởi động mỗi instance nhưng tạo tải đồng thời lên storage hoặc dependency nếu nhiều replica restore cùng lúc.

## 6. Kiểm soát môi trường phần cứng và hệ điều hành

Hiệu năng JVM phụ thuộc mạnh vào môi trường. Hãy giữ cố định hoặc ghi nhận mọi biến có thể ảnh hưởng đến kết quả.

### CPU

- Dùng cùng loại CPU hoặc cùng node pool/instance family.
- Ghi model, architecture, microcode và instruction flags liên quan.
- Giữ cùng CPU quota, cpuset và số core khả dụng.
- Tránh chạy tác vụ nền nặng hoặc benchmark khác trên cùng node.
- Nếu có thể, giữ cùng CPU governor và chính sách frequency scaling.
- Ghi nhận throttling trong cgroup/container.

CPU frequency, thermal throttling và noisy neighbor có thể làm thay đổi latency đáng kể. Một nhóm chạy khi CPU turbo cao còn nhóm khác chạy khi CPU nóng/throttled sẽ tạo kết quả sai lệch.

### Memory và NUMA

- Giữ cùng memory limit/request và heap sizing.
- Ghi RSS, heap used/committed, native memory và page fault.
- Giữ cùng NUMA policy hoặc cùng loại instance nếu NUMA ảnh hưởng.
- Tránh để một nhóm bị memory pressure hoặc swap trong khi nhóm kia không.
- Ghi nhận OOM kill, container eviction và cgroup memory events.

CRaC restore có thể có đặc điểm memory/page fault khác cold start. Không nên chỉ so sánh `-Xmx`; cần xem RSS, native memory và thời gian page-in nếu checkpoint lớn.

### Disk và filesystem

- Dùng cùng loại storage và filesystem khi so sánh.
- Ghi kích thước checkpoint, tốc độ đọc, IOPS và latency.
- Xác định page cache có nóng hay không.
- Nếu checkpoint nằm trong image layer, ghi image đã được pull/cache trước hay tính cả pull.
- Nếu checkpoint nằm trên volume, giữ cùng storage class, mount options và node topology.
- Tránh để một trial chạy trên local SSD còn trial khác đọc từ network filesystem.

### Network

- Dùng cùng network path, MTU, TLS policy và DNS resolver.
- Giữ cùng khoảng cách tới load generator và dependency.
- Ghi latency/loss/retransmission nếu mạng có thể ảnh hưởng.
- Không chạy một nhóm trong cùng node network còn nhóm khác qua cross-zone path.

### Kernel và container runtime

Ghi kernel version, container runtime, cgroup version, CRIU/JDK CRaC build và các giới hạn hệ thống liên quan. Checkpoint/restore có thể phụ thuộc vào các thành phần này. Khi so sánh cold start với CRaC, giữ runtime image và node pool tương thích nhất có thể; nếu CRaC yêu cầu môi trường riêng, ghi rõ đó là điều kiện bắt buộc của phương án.

## 7. Kiểm soát cấu hình JVM và ứng dụng

Giữ cùng JVM options giữa cold-start và checkpoint builder, trừ những khác biệt bắt buộc phải ghi rõ. Những tham số thường cần khóa:

- `-Xms`, `-Xmx` và các giới hạn heap.
- GC algorithm và các GC tuning flags.
- Thread stack size và processor count nhận diện bởi JVM.
- JIT/compiler flags và tiered compilation.
- System properties và timezone.
- Classpath/module path và native library path.
- Logging level và tracing/metrics instrumentation.
- Thread pool, connection pool và queue limits.

Đừng thay đổi `availableProcessors`, pool size hoặc GC chỉ cho một nhóm để làm benchmark trông tốt hơn. Nếu mục tiêu là tối ưu từng phương án với cấu hình tốt nhất, hãy làm một thí nghiệm tuning riêng và báo cáo cả cấu hình đã thay đổi.

### Logging và instrumentation

Logging đồng bộ, tracing chi tiết, profiler và metrics exporter có thể thêm overhead. Hãy giữ cùng mức instrumentation giữa hai nhóm. Nếu cần profiler để chẩn đoán, chạy một lượt riêng và không trộn kết quả profiler với kết quả benchmark chính.

Không tắt logging ở một nhóm nhưng giữ logging ở nhóm kia. Cũng không bật debug logging để tìm lỗi trong trial hiệu năng cuối cùng. Nếu cần ghi log startup, dùng cùng cấu hình và ghi nhận lượng log.

## 8. Kiểm soát trạng thái dependency

Ứng dụng thường phụ thuộc database, cache, broker, DNS, identity provider và HTTP service. Những dependency này có thể biến động trong lúc đo.

Hãy giữ:

- Cùng phiên bản và cấu hình database/broker/cache.
- Cùng dataset, index, schema và transaction isolation.
- Cùng connection pool limits và timeout.
- Cùng network path, TLS và credential policy.
- Cùng trạng thái cache hoặc cùng quy trình reset/warm.
- Cùng mức tải nền và cùng số client khác đang sử dụng dependency.

Nếu một dependency được dùng chung bởi nhiều trial, hãy chạy theo thứ tự có kiểm soát và reset trạng thái cần thiết giữa các trial. Tránh để cold-start trial làm nóng database buffer cache ngay trước CRaC trial mà không ghi nhận điều đó.

### Dependency reconnect sau restore

CRaC có thể yêu cầu đóng connection trước checkpoint và tạo connection mới sau restore. Điều này có thể làm `afterRestore()` và readiness chậm hơn. Hãy đo riêng thời gian reconnect, số connection mới và lỗi retry. Nếu cold start cũng tạo connection mới, hãy dùng cùng điều kiện database và cùng connection pool configuration.

Nếu nhiều replica restore đồng thời, database có thể bị connection storm. Đo riêng một replica và scale-out batch; không dùng kết quả một replica để đại diện cho cluster.

## 9. Kiểm soát page cache và cache state

Page cache của OS, image layer cache, application cache và database cache là các lớp khác nhau. Chúng có thể tạo khác biệt lớn giữa các trial.

Trước mỗi trial, quyết định rõ trạng thái nào cần:

- **Warm filesystem cache:** image/checkpoint đã được đọc trước; phù hợp khi node production thường giữ image trong cache.
- **Cold filesystem cache:** cần đo trường hợp node mới hoặc checkpoint phải đọc từ storage lạnh.
- **Warm application cache:** cache nội bộ đã được nạp qua warm-up và có thể nằm trong checkpoint.
- **Cold application cache:** reset cache để đo startup/first access.
- **Warm dependency cache:** database/cache server đã có dữ liệu thường dùng.

Không nên tùy tiện xóa page cache trên node production hoặc dùng lệnh yêu cầu quyền cao chỉ để tạo một trial cold. Nếu cần đo cold filesystem cache, dùng node/VM test riêng hoặc tạo môi trường cô lập theo chính sách vận hành. Ghi lại phương pháp và trạng thái cache.

Với CRaC, một checkpoint có thể đọc các page từ file-backed mapping hoặc cần page-in từ checkpoint storage tùy cách runtime/OS lưu trạng thái. Hãy đo cả restore duration và page fault/I/O nếu cần hiểu nguyên nhân. Đừng suy luận chỉ từ kích thước checkpoint.

## 10. Lặp lại thử nghiệm và ngẫu nhiên hóa thứ tự

Một lần chạy không đủ để kết luận. Latency có thể thay đổi theo CPU frequency, GC timing, background jobs, network jitter và trạng thái dependency.

Một quy trình thực tế:

1. Chạy pilot để kiểm tra script, xác nhận load generator và đo sơ bộ độ biến thiên.
2. Xác định số trial và cửa sổ đo trước khi thu thập kết quả chính thức.
3. Chạy nhiều trial độc lập cho mỗi nhóm; 5–10 trial có thể dùng để sàng lọc ban đầu, nhưng workload nhiễu hoặc quyết định quan trọng cần nhiều trial hơn.
4. Ngẫu nhiên hóa hoặc luân phiên thứ tự cold/CRaC để tránh một nhóm luôn chạy đầu hoặc cuối khi node nóng lên.
5. Nếu có thể, dùng paired run trên cùng node/host và khoảng thời gian gần nhau.
6. Reset fixture, cache hoặc dependency state theo protocol trước mỗi trial.
7. Lưu raw result và metadata của từng trial.
8. Lặp lại các trial bị lỗi theo chính sách đã định, không xóa outlier chỉ vì kết quả không đẹp.

Ví dụ thứ tự luân phiên:

```text
Block 1: CRaC -> Cold
Block 2: Cold -> CRaC
Block 3: Cold -> CRaC
Block 4: CRaC -> Cold
Block 5: random order
```

Thứ tự phải được chọn trước hoặc random bằng seed được ghi lại. Nếu mỗi trial cần node mới, hãy ghép cặp theo cùng loại node và cùng thời điểm tải hệ thống.

### Tại sao nên paired và randomized?

Paired run giảm ảnh hưởng của khác biệt giữa node hoặc khoảng thời gian. Randomized order giảm bias do môi trường drift theo thời gian. Nếu luôn chạy cold trước rồi CRaC sau, database cache, image cache hoặc CPU temperature có thể làm nhóm thứ hai hưởng lợi.

Không chạy song song cold và CRaC trên cùng node nếu chúng cạnh tranh CPU/memory/disk và làm ảnh hưởng lẫn nhau. Nếu chạy song song trên hai node, cần bảo đảm hai node tương đương và không tranh chấp dependency chung.

## 11. Cỡ mẫu và phân tích thống kê

Số trial cần thiết phụ thuộc độ biến thiên và mức khác biệt mà ta muốn phát hiện. Đừng chọn số lần chạy chỉ vì tiện.

Một cách thực hành:

- Dùng pilot để ước lượng median, variance và độ phân tán giữa các trial.
- Xác định mức cải thiện tối thiểu có ý nghĩa vận hành, ví dụ giảm 10% thời gian ready hoặc 50 ms p95.
- Chọn số trial đủ để khoảng tin cậy của khác biệt hẹp hơn ngưỡng quyết định.
- Nếu kết quả nhiễu, tăng số trial hoặc cải thiện kiểm soát môi trường trước khi kết luận.

### Báo cáo median và khoảng tin cậy

Với startup time, thường nên báo cáo median của các trial cùng min/max hoặc khoảng tin cậy. Với latency request, báo p50/p95/p99 trong từng cửa sổ đo và phân bố giữa các trial. Có thể dùng bootstrap để ước lượng confidence interval cho median hoặc percentile khi phân bố không chuẩn.

Không chỉ lấy trung bình của toàn bộ request rồi bỏ qua sự khác biệt giữa các lần chạy. Nếu một trial có p95 rất cao do dependency bị chậm, cần giữ lại và điều tra theo protocol. Chỉ loại trial khi có tiêu chí loại trừ được định trước, ví dụ load generator chết hoặc node bị OOM, và phải báo số trial đã loại cùng lý do.

### Percentile cần đủ mẫu

p99 từ vài trăm request không ổn định. Muốn ước lượng tail latency, cần đủ số quan sát và báo số lượng request thực tế. Nếu workload ngắn, p99 có thể chỉ phản ánh một vài mẫu. Hãy kéo dài cửa sổ đo hoặc báo rõ percentile không đủ tin cậy.

### Không gộp dữ liệu khác chế độ

Không gộp first-request latency với steady-state latency. Không trộn cache-cold và cache-warm. Không trộn trial chạy trên CPU khác nhau mà không phân tầng. Nếu cần một con số tổng hợp, giải thích cách tính và vẫn cung cấp dữ liệu theo từng nhóm.

## 12. Định nghĩa chỉ số và cách đo

### Startup/restore duration

Đo bằng timestamp từ một controller bên ngoài hoặc process supervisor để không phụ thuộc vào clock nội bộ của ứng dụng. Ghi các mốc:

- `t0`: bắt đầu launch/restore theo định nghĩa.
- `t1`: process được tạo hoặc restore command bắt đầu.
- `t2`: JVM/application callback sau restore bắt đầu.
- `t3`: dependency bắt buộc sẵn sàng.
- `t4`: readiness thành công.

Từ đó có thể tính `t4 - t0`, `t4 - t1`, `t3 - t2` và các giai đoạn khác. Dùng đồng hồ monotonic trong cùng controller để đo duration; nếu dùng timestamp giữa nhiều host, phải cân nhắc clock skew.

### Request latency

Đo từ load generator để phản ánh thời gian người gọi thực sự chờ, bao gồm network round trip. Có thể bổ sung server-side timing để phân biệt queueing/network/application. Dùng cùng client, timeout, TLS, connection reuse và network path cho hai nhóm.

### Throughput và offered load

Ghi cả request rate mà generator dự định gửi và rate server thực sự hoàn thành. Một hệ thống có throughput thấp vì load generator gửi chậm không phải là server bị giới hạn. Báo error rate, dropped iteration và timeout cùng throughput.

### CPU và memory

Thu thập CPU utilization/throttling, RSS, heap used/committed, native memory, GC pause/count, allocation rate, thread count và page faults. Đo ở cùng cửa sổ thời gian và cùng cgroup/container boundary.

### Dependency metrics

Ghi database active/idle sessions, pool acquisition latency, cache hit ratio, broker reconnect, DNS lookup và external API latency. Những chỉ số này giúp xác định khác biệt đến từ ứng dụng hay dependency.

## 13. Không để instrumentation làm thay đổi phép đo

Metrics, tracing, profiler và logging có overhead. Chúng vẫn cần thiết để giải thích kết quả, nhưng phải nhất quán.

Các quy tắc:

- Dùng cùng exporter, sampling rate và log level cho mọi nhóm.
- Đồng bộ scrape interval và metric labels.
- Tránh debug log trong cửa sổ đo chính thức.
- Chạy profiler ở trial riêng nếu profiler gây overhead đáng kể.
- Đo baseline với instrumentation bật đúng cấu hình production.
- Nếu so sánh có và không có instrumentation, xem đó là hai thí nghiệm khác nhau.

Đừng chỉ tắt metrics ở CRaC để giảm overhead nhưng giữ metrics ở cold start. Nếu instrumentation có ảnh hưởng lớn, đo riêng chi phí của nó và báo cáo cấu hình production thực tế.

## 14. Chuẩn hóa quy trình trước mỗi trial

Một runbook giúp mọi lần thử bắt đầu từ trạng thái có thể so sánh. Ví dụ:

```text
Trước trial
  1. Xác nhận node/VM thuộc đúng hardware pool.
  2. Xác nhận image, checkpoint và application digest.
  3. Kiểm tra CPU/memory limits và không có workload nền bất thường.
  4. Reset hoặc chuẩn hóa database/cache/fixture theo protocol.
  5. Xác nhận load generator rảnh và script/version đúng.
  6. Xác nhận network và dependency health.

Trong trial
  1. Ghi t0 và các mốc startup/restore.
  2. Đợi readiness theo cùng điều kiện.
  3. Đo first request nếu đây là experiment B.
  4. Chạy cùng warm-up/load phase nếu đây là experiment C.
  5. Thu metrics trong cửa sổ cố định.
  6. Ghi error, dropped iterations và environmental event.

Sau trial
  1. Lưu raw output và metadata.
  2. Dọn fixture hoặc reset dependency.
  3. Kiểm tra node không bị throttling/OOM bất thường.
  4. Đánh dấu trial hợp lệ hoặc loại theo rule đã định trước.
```

Nếu cần chạy nhiều trial liên tục trên cùng host, hãy có khoảng nghỉ hoặc điều kiện ổn định nhiệt/CPU. Không dùng thời gian nghỉ tùy ý khác nhau giữa hai nhóm.

## 15. Manifest benchmark để tái lập kết quả

Lưu cấu hình benchmark cùng kết quả. Manifest giúp người khác chạy lại và biết vì sao hai lần đo khác nhau.

Ví dụ YAML:

```yaml
benchmark:
  name: orders-crac-comparison
  version: 3
  runId: run-2026-11-13-001
  experiment: steady-state
  randomSeed: 74129

application:
  buildId: orders-2.1.0-build1842
  artifactDigest: sha256:REPLACE_WITH_REAL_DIGEST
  checkpointId: orders-2.1.0-crac-1842
  jdkBuild: crac-jdk-build-pinned
  jvmOptionsProfile: production-g1-2g

environment:
  architecture: amd64
  nodePool: benchmark-cpu-pool
  cpuLimit: "4"
  memoryLimit: 8Gi
  kernel: recorded-kernel-version
  storageClass: local-nvme
  imagePullPolicy: IfNotPresent

workload:
  script: k6-orders-v3.js
  model: open-loop
  arrivalRatePerSecond: 200
  duration: 5m
  requestMix: orders-mix-v5
  datasetRevision: fixture-2026-11-10
  cachePolicy: warm-application-cache

measurement:
  startupTrials: 10
  steadyStateTrials: 10
  warmupDuration: 2m
  measurementDuration: 5m
  readinessDefinition: readiness-probe-success
```

Các giá trị trong manifest chỉ minh họa. Digest, kernel, CPU, storage class và cấu hình thật phải được lấy từ môi trường thử nghiệm. Không đưa token, password, private key hoặc dữ liệu người dùng vào manifest.

## 16. Ví dụ thiết kế một chiến dịch so sánh cold start và CRaC

Giả sử mục tiêu là đánh giá dịch vụ REST trên cùng một node pool. Có thể thiết kế bốn experiment:

| Experiment | Cold start | CRaC restore | Chỉ số chính |
|---|---|---|---|
| Startup | Start từ cùng JAR/runtime | Restore từ checkpoint của cùng build | Process-to-ready và deploy-to-ready |
| First request | Gửi request ngay sau ready | Gửi request ngay sau ready | Latency request 1, 5, 10, 50, 100 |
| Steady-state | Cùng warm-up phase rồi tải cố định | Cùng warm-up phase rồi tải cố định | Throughput, p95/p99, CPU, memory, GC |
| Scale-out | Khởi động 10 replica theo batch | Restore 10 replica theo batch | Time-to-ready của batch, connection burst, storage/network load |

Mỗi experiment chạy nhiều trial, thứ tự cold/CRaC được ngẫu nhiên hóa hoặc ghép cặp. Dùng cùng dataset, request mix, load generator và dependency state. Ghi lại nếu image pull hoặc checkpoint copy được tính vào deploy-to-ready.

### Ví dụ bảng kết quả

Các con số sau chỉ minh họa cách trình bày, không phải kết quả thực tế:

| Chỉ số | Cold start | CRaC restore | Thay đổi |
|---|---:|---:|---:|
| Process-to-ready median | 8.2 s | 2.1 s | -74.4% |
| First request p95 | 420 ms | 95 ms | -77.4% |
| Steady-state throughput | 1,950 req/s | 1,940 req/s | -0.5% |
| Steady-state p95 | 82 ms | 83 ms | +1.2% |
| RSS sau ready | 620 MiB | 710 MiB | +14.5% |
| Restore-to-ready p95 | — | 2.8 s | — |

Diễn giải phải dựa trên nhiều trial và khoảng tin cậy. Nếu steady-state throughput gần như nhau nhưng RSS tăng, CRaC có thể giúp startup/first request nhưng tăng memory footprint. Nếu deploy-to-ready không cải thiện vì image pull/checkpoint copy chiếm phần lớn thời gian, cần tối ưu phân phối artifact hoặc cache node.

## 17. Phân tích kết quả và trình bày kết luận

Một báo cáo benchmark nên có:

1. Câu hỏi và giả thuyết.
2. Mô tả cold-start và CRaC configuration.
3. Hardware/runtime/environment manifest.
4. Workload model, request mix, offered load và dataset.
5. Định nghĩa từng timestamp/metric.
6. Số trial, thứ tự chạy, seed và quy tắc loại trial.
7. Kết quả từng trial và thống kê tổng hợp.
8. Khoảng tin cậy/độ biến thiên và các environmental events.
9. Giới hạn của phép đo và phạm vi có thể suy rộng.

Tránh kết luận “CRaC nhanh hơn X%” nếu chỉ đo một route, một node hoặc một trial. Nên viết rõ: “Trong workload X, trên node pool Y, với JDK build Z và cache policy W, median process-to-ready giảm ... qua N trial; steady-state p95 ...”. Cách diễn đạt này cho biết kết quả áp dụng trong điều kiện nào.

### Báo cáo cả độ biến thiên

Ví dụ bảng cho từng trial:

| Trial | Cold start ready | CRaC ready | Ghi chú |
|---:|---:|---:|---|
| 1 | 8.0 s | 2.0 s | Hợp lệ |
| 2 | 8.4 s | 2.2 s | Hợp lệ |
| 3 | 8.1 s | 2.1 s | Hợp lệ |
| 4 | 10.7 s | 2.3 s | Cold bị CPU throttling; xử lý theo rule đã định |
| 5 | 8.3 s | 2.0 s | Hợp lệ |

Nếu trial 4 bị loại, báo rõ lý do và kết quả có/không có trial đó nếu nó ảnh hưởng kết luận. Không xóa một trial chỉ vì nó làm giảm mức cải thiện quan sát được.

## 18. Các sai lầm thường gặp

### So sánh hai build khác nhau

Một nhóm có thể chứa code/dependency mới hơn, làm kết quả không còn cô lập được tác động của CRaC. Dùng cùng artifact digest và runtime hoặc ghi nhận thay đổi như một biến riêng.

### Đo một lần rồi kết luận

Một lần chạy có thể bị ảnh hưởng bởi CPU frequency, GC hoặc dependency jitter. Lặp lại và báo cáo phân bố giữa các trial.

### Chỉ dùng cùng số request

Request mix hoặc payload khác nhau làm workload khác nhau. Khóa route distribution, data shape, cache policy và offered load.

### Chỉ dùng fixed VUs rồi kết luận latency tail

Closed-loop có thể giảm offered load khi server chậm và che giấu queueing. Dùng open-loop khi cần arrival rate cố định và theo dõi dropped iterations.

### Để load generator chạy trên cùng máy

Generator cạnh tranh CPU/network với server và làm kết quả không ổn định. Tách generator và theo dõi năng lực của nó.

### Đo startup nhưng bỏ image pull hoặc volume mount

Kết quả process-to-ready có thể tốt nhưng deploy-to-ready vẫn chậm. Báo riêng các giai đoạn và phạm vi đồng hồ.

### Đo steady-state để kết luận về request đầu tiên

Warm-up phase làm mất khác biệt khởi đầu. Đo first-request thành experiment riêng.

### Không chuẩn hóa cache và dependency

Database buffer cache, page cache hoặc external cache có thể làm một nhóm hưởng lợi. Định nghĩa cache policy và reset/prime theo protocol.

### Chỉ báo cáo average latency

Average có thể che giấu tail latency và outlier. Báo p50/p95/p99, số mẫu, error rate và throughput.

### Loại outlier không có quy tắc

Việc loại trial sau khi xem kết quả tạo bias. Định nghĩa điều kiện loại trước và lưu raw data.

### Thay đổi nhiều biến cùng lúc

Đổi GC, heap, pool size và node type cùng lúc khiến không biết yếu tố nào tạo khác biệt. Mỗi experiment chỉ thay biến đã xác định.

## 19. Checklist trước khi công bố kết quả

- [ ] Câu hỏi benchmark và giả thuyết được xác định rõ.
- [ ] Cold-start và CRaC dùng cùng application build/digest.
- [ ] JDK, JVM options, container limits và dependency version được khóa.
- [ ] Workload có cùng request mix, payload, dataset và cache policy.
- [ ] Offered load hoặc concurrency model giống nhau.
- [ ] Load generator chạy độc lập và không bị bão hòa.
- [ ] Startup, first-request và steady-state được đo riêng.
- [ ] Image pull, volume mount/copy và dependency reconnect được báo riêng hoặc tính nhất quán.
- [ ] CPU, memory, disk, network, kernel và storage được kiểm soát/ghi nhận.
- [ ] Logging, metrics, tracing và profiling giống nhau giữa các nhóm.
- [ ] Có nhiều trial và thứ tự được randomize/paired.
- [ ] Cỡ mẫu đủ cho percentile và mức khác biệt cần phát hiện.
- [ ] Raw data, manifest, seed và script version được lưu.
- [ ] Outlier được xử lý theo rule định trước và có ghi chú.
- [ ] Kết luận nêu rõ điều kiện, giới hạn và độ biến thiên.

## 20. Kết luận

Phép đo CRaC đáng tin cậy phải so sánh cold start và restore dưới cùng workload, offered load, runtime, tài nguyên và trạng thái dependency. Hãy đo riêng thời gian từ process/deploy đến readiness, latency của request đầu tiên và hiệu năng steady-state. Dùng cùng request mix, payload, dataset, cache policy và load generator; chọn open-loop hoặc closed-loop theo câu hỏi cần trả lời.

Lặp lại nhiều trial, randomize thứ tự, ghép cặp khi có thể và báo cáo median, percentile, độ biến thiên cùng khoảng tin cậy. Kiểm soát CPU, memory, disk, page cache, network, kernel, JDK, container limits và instrumentation. Lưu manifest cùng raw result để người khác có thể tái lập. Khi trình bày kết quả, nói rõ điều kiện benchmark và phạm vi áp dụng thay vì rút ra một tỷ lệ cải thiện chung từ một lần chạy. Nhờ vậy, quyết định sử dụng CRaC dựa trên hiệu quả có thể quan sát và lặp lại trong điều kiện gần production.
