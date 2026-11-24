# Thiết kế workload suy luận sử dụng bộ tăng tốc

Workload suy luận (inference) nhận dữ liệu đầu vào, đưa dữ liệu qua một mô hình đã được huấn luyện và trả về dự đoán hoặc kết quả. Khi mô hình cần nhiều phép toán ma trận, xử lý tensor hoặc xử lý ảnh/video, CPU có thể không đáp ứng được mục tiêu độ trễ và thông lượng. GPU, NPU hoặc bộ tăng tốc chuyên dụng có thể cải thiện hiệu năng, nhưng chỉ khi mô hình, runtime, dữ liệu và kiến trúc triển khai được tối ưu đồng bộ.

Thiết kế workload inference khác với thiết kế một batch job thuần túy. API tương tác thường có SLO latency theo p95/p99; dịch vụ xử lý nền quan tâm throughput, queue age và thời gian hoàn tất; mô hình sinh nội dung có thể cần theo dõi thời gian đến token đầu tiên và tốc độ sinh token. Một GPU có utilization cao chưa chắc tạo ra trải nghiệm tốt nếu request phải chờ batch quá lâu hoặc VRAM gần cạn.

Bài học này tập trung vào thiết kế hệ thống suy luận sử dụng accelerator trên cloud, từ lựa chọn phần cứng và runtime đến batching, serving, autoscaling, quan sát, bảo mật và tối ưu chi phí. Sau bài học, bạn có thể:

- Phân biệt inference online, streaming và batch inference.
- Chọn CPU, GPU, NPU hoặc accelerator theo mô hình, precision, bộ nhớ và SLO.
- Ước lượng VRAM/RAM và xác định bottleneck compute, memory, network hoặc preprocessing.
- Thiết kế request lifecycle, batching, concurrency và queue phù hợp với latency budget.
- Chọn runtime serving, cách đóng gói model và chiến lược triển khai trên VM hoặc Kubernetes.
- Thiết kế autoscaling dựa trên tải inference và capacity accelerator.
- Đo latency, throughput, accelerator utilization, memory và cost per inference.
- Kiểm thử độ chính xác, độ ổn định, bảo mật dữ liệu và khả năng phục hồi khi accelerator gặp sự cố.

## 1. Inference là gì và khác training như thế nào?

Training cập nhật trọng số mô hình qua nhiều bước tối ưu; inference sử dụng trọng số đã có để tính kết quả cho input mới. Hai giai đoạn có thể dùng cùng loại accelerator nhưng có đặc điểm tài nguyên và mục tiêu khác nhau.

| Đặc điểm | Training | Inference |
|---|---|---|
| Mục tiêu | Tối ưu trọng số qua nhiều bước | Tạo dự đoán từ model đã huấn luyện |
| Bộ nhớ | Model, gradient, optimizer state, activation | Model weights, activation, cache và workspace |
| Tải | Thường chạy dài và có batch lớn | Có thể là request ngắn, liên tục hoặc batch nền |
| SLO | Thời gian hoàn thành training job | Latency, throughput, thời gian phản hồi hoặc deadline |
| Mở rộng | Data/model/pipeline parallelism | Replica, batching, model sharding hoặc nhiều accelerator |
| Vòng đời | Job theo phiên hoặc pipeline | Dịch vụ thường trực, scale theo request hoặc queue |

Inference có nhiều kiểu vận hành:

- **Online inference:** caller gửi request và chờ kết quả trong cùng luồng tương tác.
- **Streaming inference:** kết quả được trả từng phần, ví dụ token hoặc chunk âm thanh.
- **Batch inference:** hệ thống xử lý tập input lớn theo lô, thường ưu tiên throughput và chi phí.
- **Asynchronous inference:** API nhận job, trả job ID; worker xử lý rồi lưu kết quả để caller lấy sau.
- **Edge inference:** model chạy gần thiết bị hoặc nguồn dữ liệu để giảm latency, giảm truyền dữ liệu hoặc hoạt động khi mất kết nối.

Một mô hình có thể được triển khai theo nhiều kiểu. Cần chọn cách serving theo trải nghiệm người dùng, kích thước input, độ dài output, tần suất request và thời hạn xử lý.

## 2. Đặc tả workload trước khi chọn accelerator

Không nên bắt đầu bằng câu hỏi “GPU nào nhanh nhất?”. Hãy mô tả workload và tiêu chí thành công trước:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Model | Kiến trúc, số tham số, framework, input/output shape và phiên bản |
| Input | Kích thước ảnh, chuỗi token, audio duration, tensor dimensions hoặc payload |
| Output | Nhãn, embedding, bounding box, token, score hoặc dữ liệu có cấu trúc |
| Arrival rate | Request trung bình, peak, burst và phân phối theo thời gian |
| Concurrency | Bao nhiêu request đồng thời; request có thời gian xử lý khác nhau không? |
| Latency | p50/p95/p99, time to first token và deadline |
| Throughput | Request/giây, ảnh/giây, token/giây hoặc item/giây |
| Accuracy | Precision, recall, error tolerance hoặc metric chuyên ngành |
| Data | Dữ liệu có nhạy cảm, cần residency hoặc phải xử lý tại edge không? |
| Cost | Ngân sách theo request, token, ảnh hoặc job hoàn tất |

### Xác định SLO theo loại inference

Với API tương tác, p95/p99 latency thường quan trọng hơn throughput cực đại. Với streaming LLM, cần tách:

- **Time to first token (TTFT):** thời gian từ khi request được nhận đến khi token đầu tiên được gửi.
- **Inter-token latency (ITL):** khoảng thời gian giữa các token tiếp theo.
- **Output token throughput:** tốc độ sinh token.
- **End-to-end latency:** tổng thời gian hoàn tất phản hồi.

Với batch inference, throughput và thời gian hoàn thành toàn bộ dataset có thể quan trọng hơn latency từng item. Với pipeline xử lý ảnh, có thể đặt SLO theo ảnh/giây và tỷ lệ lỗi.

### Latency budget

Thời gian trả kết quả có thể chia thành các thành phần:

\[
T_{total} =
T_{queue} + T_{preprocess} + T_{transfer} +
T_{inference} + T_{postprocess} + T_{network}
\]

Nếu chỉ đo thời gian kernel trên GPU, bạn có thể bỏ sót queueing, tải model, decode ảnh, tokenization, truyền dữ liệu CPU-GPU và serialization. Hãy đo end-to-end cùng thời gian từng phase.

## 3. Chọn CPU, GPU, NPU và accelerator

Accelerator phù hợp khi workload có phép toán song song lớn và runtime hỗ trợ. Không phải mọi mô hình đều cần GPU.

| Loại phần cứng | Điểm mạnh | Workload phù hợp | Điều cần xác minh |
|---|---|---|---|
| CPU | Linh hoạt, xử lý logic và nhánh tốt, dễ triển khai | Model nhỏ, preprocessing, low-QPS, CPU-optimized inference | Vector instruction, core count, memory bandwidth |
| GPU | Song song tensor/ma trận, hệ sinh thái AI rộng | LLM, vision, speech, embedding và batch lớn | VRAM, memory bandwidth, precision, interconnect |
| NPU/AI accelerator | Tối ưu một nhóm operator/precision với hiệu suất năng lượng tốt | Inference được compiler/runtime hỗ trợ | Operator coverage, model conversion, quantization và driver |
| FPGA | Có thể cấu hình pipeline phần cứng cho latency/throughput chuyên biệt | Streaming, signal processing hoặc pipeline ổn định | Toolchain, thời gian phát triển, operator và khả năng vận hành |

### Khi nào CPU là đủ?

CPU có thể là lựa chọn tốt khi model nhỏ, request rate thấp, latency budget rộng hoặc thư viện đã tối ưu vectorization. CPU cũng thường đảm nhiệm tokenization, image decode, request routing, preprocessing và postprocessing ngay cả khi inference chạy trên GPU.

Đừng chuyển toàn bộ pipeline lên GPU nếu phần preprocessing không đủ lớn để bù chi phí transfer và kernel launch. Có thể giữ CPU xử lý decode/validation, sau đó chuyển tensor đã chuẩn hóa sang accelerator.

### Chọn GPU theo workload

Các thông số quan trọng:

- **VRAM capacity:** chứa weights, activation, KV cache, workspace và batch.
- **Memory bandwidth:** ảnh hưởng tốc độ đọc weights, tensor và cache.
- **Compute throughput:** cần xem theo precision thực tế như FP64, FP32, TF32, FP16, BF16 hoặc INT8.
- **Interconnect:** PCIe, NVLink hoặc kết nối tương đương giữa GPU và host/GPU khác.
- **GPU topology:** số GPU trên node, NUMA affinity, PCIe root complex và khả năng peer-to-peer.
- **Software support:** driver, CUDA/HIP/runtime, framework, compiler và serving engine.

Peak FLOPS chỉ là giới hạn lý thuyết. Benchmark với model, sequence length, image size, batch và precision thật mới cho biết throughput có thể đạt.

### NPU và accelerator chuyên dụng

NPU có thể đạt hiệu suất năng lượng tốt khi model được chuyển đổi sang graph/operator mà thiết bị hỗ trợ. Tuy nhiên, một số operator có thể không được hỗ trợ và phải fallback sang CPU, làm tăng latency. Hãy kiểm tra compiler report, operator coverage, quantization constraints và cách runtime xử lý fallback.

## 4. Ước lượng bộ nhớ accelerator

VRAM là giới hạn quan trọng. Model có thể không load được dù GPU compute rất mạnh nếu weights, activation, cache và workspace vượt bộ nhớ khả dụng.

Một mô hình ước lượng:

\[
M_{total} \approx M_{weights} + M_{activations} +
M_{cache} + M_{workspace} + M_{runtime}
\]

Trong đó:

- \(M_{weights}\): bộ nhớ của tham số model.
- \(M_{activations}\): tensor trung gian cho batch và kích thước input.
- \(M_{cache}\): cache phục vụ request, ví dụ KV cache của LLM.
- \(M_{workspace}\): vùng tạm của kernel, attention hoặc thư viện toán.
- \(M_{runtime}\): context, allocator, graph và overhead của serving engine.

### Ước lượng weights

Nếu model có \(P\) tham số và mỗi tham số dùng \(b\) byte:

\[
M_{weights} \approx P \times b
\]

Ví dụ model 7 tỷ tham số dùng weights 16-bit cần khoảng:

\[
7 \times 10^9 \times 2 \approx 14 \text{ GB}
\]

Đây chỉ là dung lượng weights lý thuyết. Model thực tế cần thêm overhead, cache và workspace; cách chia shard cũng có thể làm phát sinh buffer. Không nên chọn GPU có VRAM đúng bằng con số weights.

### KV cache cho mô hình sinh token

LLM autoregressive thường giữ key/value cache để không phải tính lại toàn bộ token trước đó ở mỗi bước decode. Dung lượng cache tăng theo số sequence đồng thời, độ dài context, số layer, số KV head và head dimension.

Một dạng ước lượng gần đúng:

\[
M_{KV} \approx
2 \times L \times B \times S \times H_{KV}
\times D \times bytes
\]

Trong đó \(L\) là số layer, \(B\) là số sequence đang giữ cache, \(S\) là số token được cache, \(H_{KV}\) là số KV head và \(D\) là head dimension. Hệ số 2 đại diện key và value. Cấu trúc GQA/MQA, cache quantization, paging và cách runtime phân bổ có thể làm thay đổi dung lượng thực tế.

Điều này giải thích vì sao tăng concurrency hoặc context length có thể làm VRAM đầy dù model weights không đổi. Khi thiết kế serving, cần benchmark cả số sequence đồng thời và context dài.

## 5. Precision, quantization và chất lượng kết quả

Inference có thể dùng nhiều precision:

- FP32: độ chính xác số học cao hơn nhưng tốn bộ nhớ và compute.
- FP16/BF16: giảm bộ nhớ và tăng throughput trên accelerator phù hợp; cần kiểm tra accuracy.
- INT8/INT4: giảm dung lượng weights và có thể tăng tốc, nhưng chất lượng phụ thuộc model, calibration và kernel.
- Mixed precision: dùng precision khác nhau cho các phần của model để cân bằng accuracy và hiệu năng.

Quantization có thể là post-training quantization hoặc quantization-aware training. Chọn phương pháp theo model, dữ liệu calibration, operator được hỗ trợ và yêu cầu chất lượng.

Trước khi đưa precision mới vào production:

1. Chọn tập validation đại diện và xác định metric chất lượng.
2. Chạy baseline ở precision gốc.
3. Chuyển đổi/quantize model và xác minh operator.
4. So sánh accuracy, recall, BLEU/WER hoặc metric chuyên ngành phù hợp.
5. Benchmark latency, throughput, VRAM và cost.
6. Kiểm tra các trường hợp biên và dữ liệu lệch phân phối.
7. Canary và theo dõi chất lượng sau triển khai.

Không chọn INT4 chỉ vì model vừa VRAM. Nếu chất lượng giảm vượt ngưỡng, cần model nhỏ hơn, sharding, offload hoặc accelerator lớn hơn.

## 6. Kiến trúc serving cho inference

Một hệ thống online inference thường có các lớp:

~~~mermaid
flowchart LR
    C["Client"] --> G["API Gateway / Load Balancer"]
    G --> A["Auth, validation, rate limit"]
    A --> Q["Request queue / admission control"]
    Q --> S["Inference serving"]
    S --> P["Preprocess / tokenizer"]
    P --> X["CPU / GPU / NPU runtime"]
    X --> O["Postprocess"]
    O --> R["Response / stream"]
    S --> M["Metrics, logs, traces"]
~~~

Các thành phần có trách nhiệm riêng:

- Gateway xác thực caller, giới hạn request và kiểm tra payload.
- Admission control quyết định nhận, xếp hàng hoặc từ chối request khi capacity không đủ.
- Serving runtime quản lý model, batch, concurrency và device.
- Pre/postprocessing chuẩn hóa input và chuyển output thành định dạng API.
- Observability ghi latency theo phase, accelerator usage, lỗi và chất lượng.

Với batch inference, có thể bỏ gateway tương tác và dùng object storage, manifest cùng scheduler để nạp dữ liệu theo partition. Với asynchronous inference, API tạo job rồi worker xử lý từ queue.

### Một model hay nhiều model trên một accelerator?

Chạy nhiều model trên cùng GPU có thể tăng utilization nếu từng model có tải thấp, nhưng làm phức tạp việc chia VRAM, scheduling, cache và isolation. Một model lớn có thể bị OOM khi model khác chiếm bộ nhớ hoặc batch tăng đột ngột.

Các chiến lược:

- Một model trên một GPU: đơn giản, dễ dự đoán và cô lập.
- Nhiều replica model trên nhiều GPU: tăng throughput và availability.
- Nhiều model trên cùng GPU: tăng utilization, cần kiểm soát memory và scheduling.
- Model sharding trên nhiều GPU: phục vụ model lớn hơn một GPU.

Chọn theo memory footprint, request pattern, SLO và chi phí vận hành.

## 7. Batching và concurrency

Batching gộp nhiều input thành một lần gọi accelerator để tăng hiệu quả tính toán. Batch lớn thường tăng throughput nhưng cũng có thể tăng latency, VRAM và thời gian chờ request.

### Static batching

Static batching chờ đủ số request hoặc tạo batch có kích thước cố định. Phù hợp với batch inference offline hoặc workload có input size ổn định. Nếu batch không đủ đầy, accelerator có thể nhàn rỗi; nếu chờ quá lâu, latency tăng.

### Dynamic batching

Dynamic batching gom request đến trong một khoảng thời gian ngắn hoặc đến khi đạt batch size tối đa. Cần đặt:

- Max batch size.
- Max queue delay.
- Timeout khi batch chưa đầy.
- Giới hạn concurrency và bộ nhớ.
- Chính sách ưu tiên hoặc tách queue theo model/SLO.

Ví dụ API vision có thể chờ tối đa vài mili giây để gom nhiều ảnh, nhưng không nên kéo dài queue delay vượt latency budget.

### Continuous batching cho LLM

LLM serving có thể dùng continuous/in-flight batching: sequence mới được thêm vào batch khi sequence khác hoàn tất hoặc giải phóng slot. Cách này cải thiện utilization khi prompt và output có độ dài khác nhau. Cần theo dõi KV cache, số sequence đang chạy, prefill/decode throughput và ITL.

### Concurrency không phải lúc nào càng cao càng tốt

Nếu concurrency tăng quá mức, queueing delay và memory pressure tăng; GPU có thể OOM hoặc p99 latency xấu đi. Cần benchmark ma trận batch size × concurrency × input length, sau đó chọn điểm vận hành nằm trong SLO và giữ headroom.

## 8. Chọn inference runtime và model server

Runtime quyết định cách model được load, tối ưu graph, quản lý batch, cấp phát memory và gọi accelerator.

| Runtime / serving engine | Trường hợp thường dùng | Điểm cần đánh giá |
|---|---|---|
| ONNX Runtime | Model xuất ONNX, cần nhiều execution provider | Operator support, graph optimization, provider fallback |
| NVIDIA TensorRT | NVIDIA GPU, tối ưu engine cho model/shape cụ thể | Build engine, precision, profile shape và compatibility |
| NVIDIA Triton Inference Server | Phục vụ nhiều model/backend, dynamic batching và model repository | Model lifecycle, metrics, concurrency và GPU sharing |
| vLLM | LLM serving với continuous batching và KV cache management | Model support, parallelism, memory và token metrics |
| Hugging Face TGI | Serving một số mô hình sinh văn bản | Model compatibility, batching, quantization và deployment |
| OpenVINO | Tối ưu inference trên phần cứng Intel được hỗ trợ | Operator coverage, precision và device plugin |

Không có runtime tốt nhất cho mọi model. Hãy chọn theo framework gốc, accelerator, operator coverage, yêu cầu streaming/batching, khả năng quan sát và quy trình cập nhật model.

### Model repository và versioning

Quản lý model như một artifact có phiên bản:

- Model ID và version.
- Digest/checksum.
- Framework và runtime version.
- Precision/quantization.
- Input/output schema.
- Dataset hoặc source lineage theo chính sách.
- Benchmark và validation result.

Không cập nhật model weights trong thư mục đang được serving mà không có versioning và rollout an toàn. Có thể triển khai model version mới song song, chạy shadow/canary, sau đó chuyển traffic theo tỷ lệ.

## 9. Phân bổ model trên nhiều GPU

Khi model không vừa một GPU hoặc cần throughput cao, có thể dùng nhiều GPU.

### Data parallel / replica parallel

Mỗi GPU giữ một bản model và xử lý request khác nhau. Cách này thường dễ mở rộng inference stateless vì request có thể phân phối qua load balancer. Cần cân bằng số request, độ dài input/output và memory usage giữa replica.

### Tensor parallelism

Chia các phép toán tensor của một layer qua nhiều GPU. Phù hợp khi model lớn hoặc muốn tăng tốc một request, nhưng cần giao tiếp giữa GPU thường xuyên. Interconnect giữa GPU có ảnh hưởng lớn.

### Pipeline parallelism

Chia các layer thành các stage trên nhiều GPU. Có thể xử lý nhiều microbatch để tăng utilization, nhưng pipeline bubble và communication có thể làm tăng latency.

### Model placement và topology

Đối với multi-GPU:

- Kiểm tra GPU-to-GPU bandwidth và topology.
- Giữ các GPU của cùng một model gần nhau khi nền tảng hỗ trợ.
- Xác minh PCIe/NVLink hoặc interconnect tương đương.
- Kiểm tra CPU/NUMA affinity và đường truyền host-to-device.
- Tránh đặt shard trên các node khác nhau nếu model parallelism cần giao tiếp chặt mà network không đáp ứng.

Model replica thường phù hợp để tăng tổng throughput; model parallelism phù hợp khi model không vừa một accelerator hoặc một request cần nhiều GPU. Hai chiến lược có thể kết hợp.

## 10. Triển khai inference trên Kubernetes

Kubernetes có thể lập lịch Pod yêu cầu accelerator thông qua device plugin hoặc cơ chế tài nguyên mở rộng do vendor cung cấp. Tên resource và label phụ thuộc phần cứng/runtime; ví dụ NVIDIA thường quảng bá GPU bằng resource nvidia.com/gpu.

Ví dụ Deployment yêu cầu một GPU:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vision-inference
spec:
  replicas: 2
  selector:
    matchLabels:
      app: vision-inference
  template:
    metadata:
      labels:
        app: vision-inference
    spec:
      nodeSelector:
        accelerator: nvidia-gpu
      containers:
        - name: server
          image: registry.example.com/vision-inference:1.2.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "4"
              memory: "16Gi"
              nvidia.com/gpu: "1"
            limits:
              cpu: "8"
              memory: "24Gi"
              nvidia.com/gpu: "1"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 6
~~~

Ví dụ giả định node được gắn label accelerator=nvidia-gpu và device plugin đã hoạt động. Trong môi trường thực tế, cần cấu hình đúng node label, driver, container toolkit, device plugin, runtime class nếu cần và tài nguyên extended resource của vendor.

### Các điểm cần kiểm tra

- Node có accelerator đúng model, VRAM và driver version.
- Device plugin quảng bá tài nguyên và node allocatable đúng.
- Pod request GPU phù hợp với loại accelerator.
- Model image, weights và runtime tương thích driver.
- Readiness chỉ thành công sau khi model load và warm-up hoàn tất.
- Liveness không restart liên tục khi model đang khởi tạo lâu.
- Pod có memory/CPU đủ cho preprocessing và serving.
- Node pool có quota và autoscaling phù hợp.
- Pod disruption và rolling update không làm mất toàn bộ capacity.

### GPU sharing

Một số nền tảng hỗ trợ chia GPU bằng MIG, time-slicing hoặc cơ chế vendor. Các phương thức có semantics khác nhau:

- MIG phân chia GPU thành các instance phần cứng có tài nguyên được cô lập theo profile được hỗ trợ.
- Time-slicing chia thời gian thực thi, có thể tăng utilization nhưng không tương đương VRAM riêng cho mỗi workload.
- Một số giải pháp vGPU hoặc scheduler chuyên dụng cung cấp lớp chia sẻ khác.

Không giả định GPU request bằng 1 luôn tương ứng với một GPU vật lý riêng nếu cluster có cơ chế sharing. Cần hiểu isolation, VRAM limit, performance interference và quota thực tế.

## 11. Autoscaling cho inference workload

HPA theo CPU không phải lúc nào phản ánh đúng tải GPU. Một server có CPU thấp nhưng GPU đầy; ngược lại, GPU utilization có thể thấp vì request đang chờ tokenization hoặc data transfer.

Metric có thể dùng:

| Workload | Metric hữu ích |
|---|---|
| Vision API | Requests per replica, queue delay, images/sec, GPU utilization và VRAM |
| Embedding service | Tokens/sec hoặc items/sec, batch queue, GPU memory |
| LLM serving | Active sequences, pending requests, TTFT, ITL, tokens/sec, KV cache usage |
| Batch inference | Queue depth, oldest job age, completion rate và estimated time to drain |
| Audio/video | Streams per replica, real-time factor, frames/sec và accelerator utilization |

### Scale-up và scale-down

Scale-up cần tính thời gian:

1. HPA/custom metrics nhận biết tải tăng.
2. Controller tạo Pod.
3. Node autoscaler cấp node GPU nếu thiếu capacity.
4. Node cài/khởi tạo driver và device plugin.
5. Pod tải model weights và khởi tạo runtime.
6. Warm-up hoàn tất, readiness thành công.
7. Load balancer mới gửi traffic.

Thời gian cấp node GPU và tải model có thể dài. Với API có latency nghiêm ngặt, cần giữ baseline replica hoặc dùng capacity pre-warmed. Scale-to-zero có thể tiết kiệm chi phí nhưng gây cold start và không phù hợp nếu yêu cầu phản hồi tức thì.

Scale-down cần drain request, stream hoặc batch đang chạy. Với LLM streaming, cần xử lý client disconnect và không cắt request đang sinh nếu không có cơ chế resume. Với batch, có thể ngừng nhận job mới và hoàn tất batch hiện tại trước khi terminate.

### Admission control và backpressure

Khi không còn capacity, hệ thống cần quyết định:

- Queue request trong giới hạn latency budget.
- Trả 429/503 hoặc thông báo retry-after.
- Chuyển sang model nhỏ hơn hoặc CPU fallback nếu chất lượng/SLO cho phép.
- Giảm max output tokens hoặc input size.
- Ưu tiên request quan trọng.
- Từ chối sớm request vượt quota.

Queue không giới hạn có thể biến quá tải accelerator thành latency tăng vô hạn. Luôn đặt queue capacity, timeout và chính sách shedding.

## 12. Tối ưu inference latency và throughput

Tối ưu theo phase giúp tránh nâng cấp GPU khi bottleneck nằm ở nơi khác.

### Preprocessing

- Decode ảnh/audio/video hiệu quả.
- Resize/normalize bằng thư viện vectorized hoặc accelerator nếu phù hợp.
- Tokenize song song và cache kết quả khi an toàn.
- Giảm copy dữ liệu giữa process và host memory.
- Dùng pinned memory hoặc asynchronous transfer khi runtime hỗ trợ và benchmark chứng minh có lợi.

### Model execution

- Chọn precision phù hợp.
- Fuse operator và tối ưu graph.
- Dùng kernel/library phù hợp accelerator.
- Tối ưu batch size và sequence length.
- Tránh CPU fallback ngoài dự kiến.
- Profile kernel và memory access.

### Postprocessing

- Giảm serialization không cần thiết.
- Tránh copy tensor lớn về CPU nếu chỉ cần một số kết quả.
- Tách bước ghi kết quả dài sang async worker nếu phù hợp.

### Cache

Cache có thể dùng cho embedding, kết quả inference lặp lại hoặc model artifact. Cache key phải bao gồm model version, preprocessing version và các tham số ảnh hưởng kết quả. Không cache output theo input không đáng tin cậy nếu có nguy cơ rò rỉ dữ liệu giữa tenant.

## 13. Độ chính xác, kiểm thử và rollout model

Tối ưu hiệu năng không được làm mất kiểm soát chất lượng. Mỗi model version cần bộ validation đại diện.

### Kiểm thử trước phát hành

- Unit test cho preprocessing/postprocessing.
- Golden dataset để so sánh kết quả với baseline.
- Accuracy/precision/recall hoặc metric chuyên ngành.
- Test input rỗng, quá lớn, malformed và dữ liệu ngoài phân phối.
- Load test với concurrency và payload đại diện.
- Stress test VRAM, batch tối đa và context dài.
- Test timeout, client disconnect và accelerator reset.
- Test model reload, rollback và node replacement.

### Canary và shadow traffic

Canary chuyển một tỷ lệ nhỏ traffic sang model/runtime mới và theo dõi latency, error, resource và quality. Shadow traffic chạy bản mới song song nhưng không trả kết quả mới cho người dùng; cần kiểm soát chi phí và dữ liệu nhạy cảm. Khi metric đạt ngưỡng, tăng dần traffic.

Model rollback nên trỏ về artifact digest đã xác minh. Không chỉ rollback container image mà quên rollback weights, tokenizer, config hoặc preprocessing pipeline.

## 14. Quan sát inference và tìm bottleneck

Một dashboard hữu ích nên kết hợp chỉ số ứng dụng và accelerator:

| Nhóm | Metric |
|---|---|
| Request | Request rate, success/error, timeout, queue depth |
| Latency | p50/p95/p99, queue wait, preprocessing, inference, postprocessing |
| Model | Model load time, version, batch size, input/output size |
| GPU | Utilization, VRAM used/free, memory bandwidth, temperature/power nếu được phép |
| Runtime | Kernel time, host-device transfer, CPU fallback, allocator fragmentation |
| LLM | TTFT, ITL, input/output tokens/sec, active sequences, KV cache |
| Capacity | Replica, pending Pod, node count, GPU allocatable và quota |
| Cost | GPU-hours, cost per request/image/token/job thành công |
| Quality | Accuracy proxy, drift, validation score, fallback rate |

### Diễn giải tín hiệu

- GPU utilization thấp và queue cao: có thể bottleneck ở CPU preprocessing, lock, data transfer hoặc scheduling.
- GPU utilization cao nhưng throughput thấp: kiểm tra kernel, memory bandwidth, batch shape và precision.
- VRAM gần đầy và OOM: giảm concurrency/context/batch, quantize hoặc chọn accelerator có VRAM lớn hơn.
- p99 cao nhưng p50 tốt: kiểm tra queueing, request dài, batch delay và contention.
- CPU cao, GPU thấp: kiểm tra tokenizer, decode, serialization, data loader và CPU fallback.
- GPU cao, latency tăng theo concurrency: giảm admission hoặc điều chỉnh batch/sequence scheduling.

Không dùng một metric duy nhất để tự động scale. Nên kết hợp tải, queueing, latency và memory headroom để tránh scale-out liên tục khi bottleneck nằm ở dependency khác.

## 15. Bảo mật và quản trị dữ liệu inference

Inference có thể xử lý dữ liệu cá nhân, hình ảnh, giọng nói, tài liệu hoặc nội dung nội bộ. Cần bảo vệ cả input, output, model và accelerator host.

- Xác thực caller và phân quyền theo tenant.
- Mã hóa dữ liệu truyền và lưu trữ.
- Giới hạn log input/output; redact dữ liệu nhạy cảm.
- Dùng workload identity và quyền tối thiểu cho model server.
- Chỉ tải model từ registry/artifact store được phê duyệt.
- Xác minh checksum, signature và provenance của model artifact.
- Quét image/runtime và quản lý driver/host patching.
- Cô lập workload khi chia sẻ GPU; kiểm tra cơ chế memory isolation.
- Xóa cache hoặc dữ liệu tạm theo chính sách tenant.
- Kiểm soát outbound network và secret truy cập model repository.

Model artifact cũng là một phần của chuỗi cung ứng. Một file weights bị thay thế có thể làm thay đổi hành vi mô hình hoặc chứa nội dung độc hại trong định dạng có thể thực thi khi load. Chỉ tải artifact từ nguồn tin cậy, xác minh digest và dùng định dạng an toàn theo framework.

## 16. Ví dụ thiết kế: API phân loại ảnh dùng GPU

Một dịch vụ nhận ảnh sản phẩm, trả về nhãn và confidence score. Tải trung bình 40 request/giây, peak 120 request/giây. SLO p95 dưới 250 ms. Benchmark trên một GPU cho thấy model xử lý 80 ảnh/giây với batch 8, nhưng p95 tăng khi queue delay vượt 10 ms.

### Kiến trúc

~~~mermaid
flowchart TD
    C["Client"] --> G["API Gateway"]
    G --> A["Auth + payload validation"]
    A --> L["Load balancer"]
    L --> S1["GPU inference replica 1"]
    L --> S2["GPU inference replica 2"]
    S1 --> M["Model registry / versioned weights"]
    S2 --> M
    S1 --> O["Response + metrics"]
    S2 --> O
~~~

Thiết kế ban đầu có hai replica để giữ headroom và phục vụ khi một replica gặp sự cố. Dynamic batching có max batch 8 và queue delay tối đa 10 ms theo kết quả benchmark. Mỗi replica có giới hạn concurrency và readiness chỉ đạt sau khi model load/warm-up xong.

### Capacity sơ bộ

Nếu mỗi GPU replica xử lý ổn định 80 ảnh/giây trong SLO, hai replica có năng lực lý thuyết khoảng 160 ảnh/giây khi tải phân phối đều. Đây không phải cam kết capacity production: cần trừ headroom, kiểm tra peak request shape, ảnh lớn, preprocessing, lỗi replica và dependency.

Autoscaling có thể dựa trên request per replica, queue delay và GPU utilization. Khi peak kéo dài, tăng replica; khi tải giảm ổn định, giảm replica sau khi drain request. Nếu node GPU cần nhiều phút để cấp phát, giữ baseline hoặc pre-warm node để tránh vi phạm SLO.

### Kiểm thử

1. Tải ảnh có kích thước và định dạng khác nhau.
2. Chạy concurrency tăng dần từ tải nền đến peak và vượt peak.
3. Đo p50/p95/p99, queue delay và inference time riêng.
4. Kiểm tra VRAM ở batch tối đa.
5. Mô phỏng một replica mất và xác minh replica còn lại chịu tải.
6. Kiểm tra scale-up node/Pod và thời gian model ready.
7. So sánh accuracy với baseline khi thay precision hoặc runtime.

## 17. Ví dụ thiết kế: LLM inference streaming

Một endpoint chat nhận prompt, tạo phản hồi theo token và stream tới client. Đặc điểm cần quan tâm:

- Prompt length và output token limit.
- TTFT và inter-token latency.
- Số sequence đồng thời và KV cache.
- Prefill throughput so với decode throughput.
- Continuous batching và scheduling fairness.
- Model weights, quantization và tensor parallelism.
- Client disconnect, timeout và cancellation.

Với LLM, request dài có thể chiếm KV cache lâu hơn request ngắn. Nếu chỉ cân bằng theo số request, replica có thể mất cân bằng đáng kể. Có thể dùng active sequences, token budget, KV cache occupancy hoặc estimated remaining work để điều phối.

Nếu model không vừa VRAM một GPU, dùng model sharding hoặc quantization đã kiểm thử. Nếu cần throughput lớn, tăng replica và phân phối request; nếu một request cần nhiều GPU, phải kiểm tra interconnect và latency giao tiếp giữa shard.

## 18. Tối ưu chi phí inference

Chi phí nên được đo theo kết quả hợp lệ:

\[
CostPerInference =
\frac{GPUCost + CPUCost + StorageCost + NetworkCost + ServingOverhead}
{SuccessfulInferences}
\]

Với LLM có thể tính cost per 1,000 input/output tokens; với vision có thể tính cost per 1,000 images; với batch có thể tính cost per completed job.

Các cách tối ưu:

- Chọn accelerator theo benchmark thay vì peak spec.
- Tăng batch vừa đủ để cải thiện throughput mà không phá latency.
- Dùng quantization nếu accuracy vẫn đạt ngưỡng.
- Dùng model nhỏ hơn hoặc cascade model cho request đơn giản.
- Scale theo queue và tải thực tế; giảm capacity khi idle.
- Dùng asynchronous/batch inference cho tác vụ không cần phản hồi tức thì.
- Cache kết quả có thể tái sử dụng và không gây rò rỉ dữ liệu.
- Tối ưu preprocessing để GPU không chờ CPU.
- Tránh giữ GPU provisioned vượt nhu cầu nếu có thể dùng pool linh hoạt.
- Tính cả thời gian model load, warm-up và idle khi scale.

GPU đắt hơn theo giờ vẫn có thể rẻ hơn trên mỗi inference nếu hoàn tất nhiều request hơn hoặc giảm thời gian giữ capacity. Cần đo cost per successful inference cùng SLO và quality.

## 19. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Model không load được | VRAM thiếu, weights sai precision hoặc runtime không hỗ trợ operator | Đo memory footprint, kiểm tra model/runtime và quantization |
| GPU utilization thấp | CPU preprocessing, data transfer hoặc queue scheduling là bottleneck | Profile từng phase, giảm copy và tối ưu data loader |
| GPU OOM khi tăng concurrency | Activation/KV cache/batch vượt VRAM | Giới hạn concurrency, batch/context; quantize hoặc tăng VRAM |
| p99 latency tăng mạnh | Queueing, batch delay hoặc request dài | Giới hạn queue, admission control, tách workload theo SLO |
| Throughput không tăng khi thêm GPU | Communication, model shard hoặc load imbalance | Profile interconnect, topology và parallel strategy |
| Pod không nhận GPU | Device plugin, node label, driver hoặc resource request sai | Kiểm tra node allocatable, plugin và Pod events |
| Pod Ready nhưng request lỗi | Model load chưa hoàn tất hoặc health check quá nông | Readiness gắn với model availability và warm-up |
| CPU cao, GPU nhàn rỗi | Tokenization/decode hoặc CPU fallback | Kiểm tra operator coverage và preprocessing |
| Model mới giảm accuracy | Precision/quantization hoặc preprocessing thay đổi | Chạy validation và rollback artifact |
| Scale-up quá chậm | Node provisioning, image/model download và warm-up | Giữ baseline, cache artifact hoặc pre-warm capacity |
| Chi phí cao khi traffic thấp | GPU luôn provisioned hoặc batch/concurrency kém | Scale-down an toàn, async batch và rightsizing |

## 20. Checklist triển khai workload inference dùng accelerator

- [ ] Đã xác định online, streaming, asynchronous hay batch inference.
- [ ] Đã mô tả model, input/output shape, arrival rate và concurrency.
- [ ] Đã đặt SLO latency/throughput và accuracy threshold.
- [ ] Đã benchmark CPU, GPU hoặc NPU trên workload đại diện.
- [ ] VRAM/RAM đã tính weights, activation, cache, workspace và runtime overhead.
- [ ] Precision/quantization đã được validation về chất lượng.
- [ ] Runtime và driver tương thích với accelerator.
- [ ] Preprocessing, transfer, inference và postprocessing được đo riêng.
- [ ] Batch size, queue delay và concurrency nằm trong giới hạn SLO/memory.
- [ ] Model version, digest và preprocessing version được quản lý.
- [ ] Kubernetes device plugin, node pool và resource request đã được xác minh.
- [ ] Readiness chỉ đạt sau khi model load và warm-up hoàn tất.
- [ ] Autoscaling dùng metric phù hợp với workload accelerator.
- [ ] Có admission control, backpressure và queue limit.
- [ ] Scale-in drain request/stream/job trước khi terminate.
- [ ] Đã kiểm thử lỗi GPU, OOM, node replacement và model rollback.
- [ ] Input/output, model artifact, secret và log được bảo vệ.
- [ ] Dashboard có latency, throughput, VRAM, utilization, quality và cost.
- [ ] Đã tính cost per successful inference và kiểm tra SLO trong peak.

## 21. Bài tập vận dụng

Một nhóm triển khai mô hình phân loại ảnh trên Kubernetes. Model có 5 tỷ tham số, weights được lưu ở precision 16-bit. Mỗi GPU có 24 GB VRAM. Khi chạy một replica, model load thành công nhưng chỉ còn ít VRAM trống; tăng batch từ 4 lên 16 làm throughput tăng nhưng một số request p99 vượt SLO và thỉnh thoảng container OOM. CPU utilization của node chỉ khoảng 35%, còn GPU utilization thường trên 90%.

1. Ước lượng dung lượng weights lý thuyết của model.
2. Vì sao model load thành công không có nghĩa có thể tăng batch tùy ý?
3. Những thành phần VRAM nào ngoài weights cần được tính?
4. Hãy đề xuất cách benchmark batch size và concurrency để tìm điểm cân bằng.
5. Có nên tăng CPU node trước không? Cần thu thập dữ liệu gì để quyết định?
6. Đề xuất hai hướng giảm cost per inference mà vẫn giữ accuracy và p99 SLO.

Gợi ý: 5 tỷ tham số ở 2 byte/tham số cần khoảng 10 GB cho weights, nhưng runtime, activation, workspace và cache cần thêm bộ nhớ. Batch lớn làm tăng activation và có thể tăng queueing delay; OOM có thể xảy ra trước khi GPU compute đạt giới hạn. Hãy đo VRAM theo batch/concurrency, p95/p99, queue delay, throughput và accuracy. CPU chỉ nên tăng nếu profiling cho thấy preprocessing/tokenization hoặc host-side pipeline là bottleneck. Có thể thử quantization đã validation, dynamic batching có giới hạn, model nhỏ hơn hoặc tối ưu preprocessing.

## Kết luận

Thiết kế workload inference sử dụng bộ tăng tốc bắt đầu từ model, input pattern, SLO và bottleneck thực tế. GPU/NPU có thể tăng throughput nhưng cần đủ VRAM, runtime tương thích, dữ liệu được cấp phát hiệu quả và kiến trúc serving phù hợp. Batching, concurrency, model parallelism và autoscaling phải được hiệu chỉnh đồng thời với latency, quality và memory headroom. Đo end-to-end, kiểm thử trên tải đại diện, quản lý model artifact an toàn và tối ưu cost per successful inference giúp hệ thống đạt hiệu năng ổn định khi đưa vào production.
