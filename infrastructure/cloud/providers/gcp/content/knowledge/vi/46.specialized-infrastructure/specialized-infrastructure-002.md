# Cloud TPU và yêu cầu workload học máy

Trong một hệ thống Google Cloud, Compute Engine có thể chạy API Java, Cloud Storage có thể lưu dữ liệu huấn luyện và GKE có thể điều phối các container. Nhưng khi công việc chính là nhân ma trận lớn, học biểu diễn từ hàng tỷ token hoặc phục vụ mô hình tạo sinh ở lưu lượng cao, CPU thông thường không còn là lựa chọn tối ưu. **Cloud TPU (Tensor Processing Unit)** là bộ tăng tốc chuyên dụng được Google thiết kế cho phép tính tensor và những workload học máy có thể khai thác khả năng song song của phần cứng này.

TPU không phải phương án thay thế trực tiếp cho mọi GPU hoặc CPU. Workload có nhiều nhánh điều kiện, dùng toán tử tùy chỉnh chỉ có trên CUDA, phụ thuộc nhiều vào tiền xử lý trên CPU hoặc yêu cầu số học FP64 có thể không phù hợp. Việc chọn TPU còn phụ thuộc **framework, trình biên dịch XLA, kích thước tensor, bộ nhớ HBM, cấu trúc TPU slice, mạng interconnect, nguồn dữ liệu, quota, giá và khả năng checkpoint**.

Bài học thuộc chương **Hạ tầng chuyên biệt** trong module **CLOUD_PROVIDERS_GCP**. Module đi từ tổ chức project, IAM, VPC tới Compute Engine, GKE, Cloud Run, các dịch vụ lưu trữ và cơ sở dữ liệu; người học thực hành lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Cloud TPU là ví dụ tiêu biểu của việc phải chọn hạ tầng theo **đặc tính workload**, thay vì chọn cấu hình chỉ dựa vào số lượng máy.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của TPU, TensorCore, HBM, XLA, ICI, host VM và TPU slice.
- Phân biệt workload training, fine-tuning, batch inference và online inference.
- Nhận diện đặc điểm workload phù hợp hoặc không phù hợp với TPU.
- So sánh các thế hệ TPU v5e, v5p, Trillium (v6e) và Ironwood (TPU7x) theo nhu cầu.
- Ước lượng nhu cầu bộ nhớ, batch size, sequence length, thông lượng và network/data pipeline.
- Chọn TPU VM trên Compute Engine, TPU trên GKE Standard/Autopilot hoặc nền tảng quản lý phù hợp.
- Hiểu yêu cầu tương thích JAX, PyTorch/XLA, TensorFlow, libtpu và TPU software image.
- Thực hành tạo TPU VM, xác nhận JAX thực sự thấy TPU, chạy phép tính và dọn tài nguyên.
- Hiểu yêu cầu topology và tài nguyên `google.com/tpu` khi chạy workload GKE.
- Lập checklist quota, placement, bảo mật, tính sẵn sàng, monitoring và FinOps.

## 1. Cloud TPU là gì?

Một TPU là bộ tăng tốc được thiết kế để thực hiện những phép tính tensor phổ biến trong deep learning với hiệu quả cao. Các TPU thế hệ mới kết hợp:

- **TensorCore:** phần cứng xử lý phép toán tensor/matrix chuyên dụng.
- **Matrix Multiply Unit (MXU):** mạch tính toán nhân ma trận với tính song song cao.
- **High Bandwidth Memory (HBM):** bộ nhớ băng thông lớn gắn với TPU chip, chứa tham số, activations, optimizer state và dữ liệu trung gian.
- **Inter-Chip Interconnect (ICI):** liên kết tốc độ cao giữa các TPU chip trong một slice để trao đổi tensor và kết quả collective operations.
- **Host VM:** CPU/RAM, hệ điều hành, mạng và tiến trình Python/framework điều khiển TPU.
- **XLA compiler và TPU runtime:** biên dịch, sắp xếp layout, tối ưu graph và thực thi trên TPU.

TPU đặc biệt hữu ích khi chương trình thực hiện nhiều phép nhân ma trận và có thể tạo các khối tính toán lớn, ít đổi shape. Không nên nghĩ TPU chỉ là “CPU có nhiều core”: cách biên dịch, chia dữ liệu và quản lý bộ nhớ khác đáng kể.

### Luồng từ mô hình tới phần cứng

~~~mermaid
flowchart LR
  A[Dữ liệu: Cloud Storage / dataset] --> B[Input pipeline + CPU host]
  B --> C[JAX / PyTorch-XLA / framework tương thích]
  C --> D[XLA compiler + libtpu runtime]
  D --> E[TPU TensorCores + HBM]
  E <--> F[ICI: TPU chips khác trong slice]
  E --> G[Gradient / output / predictions]
  G --> H[Checkpoint / model artifact]
  H --> I[Cloud Storage / artifact registry phù hợp]
~~~

Một hệ thống inference cũng có đầu vào/đầu ra, nhưng thường chú trọng latency và batching hơn là gradients/optimizer. Sơ đồ cho thấy logic xử lý; thực tế phụ thuộc version TPU và framework.

## 2. TPU, CPU và GPU: chọn theo đặc điểm workload

| Tiêu chí | CPU | GPU | TPU |
|---|---|---|---|
| Thế mạnh | Control flow, tiền xử lý, I/O, tác vụ hỗn hợp | Tính toán song song rộng, hệ sinh thái CUDA | Dense tensor/matrix, XLA và nhiều mô hình deep learning |
| Mức linh hoạt | Cao | Cao nếu thư viện/toán tử hỗ trợ | Phụ thuộc graph, compiler và khả năng hỗ trợ operator |
| Tối ưu latency request nhỏ | Thường tốt với logic nhẹ | Có overhead launch/transfer | Cần batching, compile và pipeline phù hợp |
| Huấn luyện lớn | Ít phù hợp cho phần ma trận nặng | Phổ biến | Phù hợp khi mô hình/framework tương thích |
| Operator tùy chỉnh | Viết native code dễ hơn | CUDA/Triton tùy hệ | Không phải mọi CUDA/custom op đều có đường TPU |
| Số học độ chính xác kép | CPU hỗ trợ rộng | Tùy GPU | Không phải lựa chọn chung cho workload FP64 nặng |
| Vận hành | VM/container tiêu chuẩn | Driver, accelerator, distributed runtime | TPU runtime, topology, quota/capacity, XLA |

**Nguyên tắc lựa chọn:** chạy benchmark đại diện trên CPU, GPU và TPU nếu yêu cầu hiệu năng/chi phí quan trọng. Không so sánh chỉ bằng TFLOPS lý thuyết hay giá chip-giờ.

### Những mô hình thường có lợi từ TPU

- Transformer/LLM với phép nhân ma trận lớn.
- Các mô hình hình ảnh, encoder và dense recommendation.
- Huấn luyện quy mô vừa và lớn với JAX hoặc framework được hỗ trợ.
- Fine-tuning có batch và sequence length ổn định.
- Batch inference có đủ lượng dữ liệu để khai thác throughput.
- Online inference khi serving stack, latency budget và batching phù hợp.

### Những workload có thể không phù hợp

- Pipeline chủ yếu đọc file, xử lý ảnh bằng CPU hoặc gọi API bên ngoài.
- Mô hình quá nhỏ, mỗi request tạo rất ít phép tính.
- Graph thay đổi kích thước liên tục gây nhiều lần compile.
- Operator chỉ có CUDA hoặc extension chưa có kernel TPU tương đương.
- Mô phỏng hoặc bài toán khoa học cần nhiều FP64.
- Tác vụ có nhiều nhánh logic/element-wise operations và rất ít matrix multiplication.
- Workload không chịu được giới hạn topology/quota/zone hoặc thời gian khởi tạo.

Không tự kết luận TPU không thể chạy mọi phép toán có dynamic shape; một số framework có kỹ thuật padding/bucketing hoặc cách tổ chức graph phù hợp. Vấn đề là **chi phí tái biên dịch và hiệu suất thực tế**.

## 3. Các thế hệ TPU cần biết

Google Cloud hỗ trợ các thế hệ TPU theo danh mục và phương thức cấp phát riêng. Các tên thường gặp:

| Thế hệ | Đặc điểm/định hướng | Ví dụ lựa chọn |
|---|---|---|
| TPU v5e | Lựa chọn cân bằng chi phí cho training và inference ở quy mô phù hợp | Fine-tuning, serving, batch workload |
| TPU v5p | Thiết kế cho training quy mô lớn, nhiều chip/slice | Pretraining hoặc job distributed lớn |
| TPU Trillium (v6e) | Thế hệ tối ưu cả training/inference; có nhiều kích cỡ host | Training tiêu chuẩn, fine-tuning, serving |
| TPU7x (Ironwood) | Thế hệ mới tập trung hiệu năng và băng thông cao | Inference/generative AI quy mô lớn, training/fine-tuning phù hợp |
| TPU v4 và cũ hơn | Xuất hiện ở hệ thống legacy hoặc vùng có giới hạn | Duy trì workload khi còn được hỗ trợ |

Các thế hệ khác nhau về TensorCore, HBM, interconnect, precision, topology, phần mềm và tính sẵn sàng theo zone. **Không giả định một checkpoint hoặc Docker image sẽ chạy giống nhau trên mọi thế hệ.**

### Tình trạng framework

JAX và PyTorch/XLA là hai lựa chọn phổ biến cho TPU. TensorFlow có hỗ trợ trên nhiều thế hệ nhưng **theo bảng TPU software versions hiện hành, TensorFlow không hỗ trợ Ironwood (TPU7x)**. Các runtime/plugin như TorchTPU hoặc vLLM có thể có điều kiện hỗ trợ riêng; kiểm tra matrix **framework × TPU version × image/libtpu** trước khi chọn cấu hình.

### Ví dụ machine types

| TPU | Ví dụ TPU-optimized VM | Ý nghĩa |
|---|---|---|
| v5e | `ct5lp-hightpu-1t`, `ct5lp-hightpu-4t` | 1 hoặc 4 chip/VM trong cấu hình hỗ trợ |
| v5p | `ct5p-hightpu-4t` | 4 chip/VM, có thể thành multi-host slice |
| v6e | `ct6e-standard-1t`, `ct6e-standard-4t`, `ct6e-standard-8t` | 1, 4 hoặc 8 chip/VM; kiểm tra topology |
| TPU7x | `tpu7x-standard-4t` | 4 chip/VM; cách quản lý topology khác theo scenario |

Machine type chỉ mô tả host/slice phù hợp, không tự bảo đảm quota/capacity hay việc framework có kernel tối ưu. Trước khi triển khai, xem trang TPU machines/GKE TPU version hiện hành.

## 4. TPU VM, chip, slice và Pod không phải một đơn vị

Đây là nhóm khái niệm dễ gây cấu hình sai:

- **TPU chip:** một thành phần accelerator vật lý có TensorCores và HBM.
- **TPU VM/host:** một hệ điều hành Linux với CPU/RAM và một hoặc nhiều TPU chip gắn vào.
- **TPU slice:** tập chip/host được cấp cho một workload, có topology liên kết cụ thể.
- **TPU Pod:** cụm lớn các chip được kết nối vật lý; một slice là một phần của Pod.
- **Single-host slice:** toàn bộ chip thuộc slice có thể gắn với một VM.
- **Multi-host slice:** nhiều VM cùng tham gia một workload qua mạng/ICI.

Ví dụ trên TPU v6e:

| Machine type | Topology ví dụ | Số chip toàn slice | Số VM | Ghi chú |
|---|---|---:|---:|---|
| `ct6e-standard-1t` | `1x1` | 1 | 1 | Lab và workload nhỏ |
| `ct6e-standard-4t` | `2x2` | 4 | 1 | Single-host |
| `ct6e-standard-8t` | `2x4` | 8 | 1 | Single-host cấu hình 8 chip |
| `ct6e-standard-4t` | `4x4` | 16 | 4 | Multi-host, 4 chip/VM |

Những cấu hình trên minh họa topology được công bố; availability phụ thuộc sản phẩm và zone. Topology như `2x2` là cách sắp xếp **chip**, không phải “2 VM x 2 VM”. Với GKE, container xin chip **trên từng node**, không xin toàn bộ chip của slice vào một pod bất kỳ.

### Tại sao topology ảnh hưởng hiệu năng?

Trong training phân tán, một mô hình có thể được sharding theo data, model và optimizer states. Khi mỗi bước cần all-reduce, all-gather hoặc chuyển activations, tốc độ ICI và cách đặt chip có thể quyết định thông lượng.

Số chip nhiều hơn không đảm bảo training nhanh tỷ lệ thuận; thông tin cần kiểm tra là:

1. Số chip toàn slice và số chip/host.
2. Topology được hỗ trợ cho thế hệ TPU.
3. Sharding strategy của model/framework.
4. Số bytes phải trao đổi giữa chip/host.
5. Hiệu quả của collective operations.
6. Tác động đến memory footprint và batch size.

## 5. XLA, libtpu và sự khác biệt so với chương trình Python thông thường

TPU không thực thi mã Python tự do trên TensorCores. Framework tạo phép toán tensor; **XLA** biên dịch graph thành chương trình tối ưu cho TPU, còn **libtpu** cung cấp runtime/driver.

### JIT compilation

Một bước JAX có thể được trang trí bằng `jax.jit` để XLA biên dịch:

~~~python
import jax
import jax.numpy as jnp

@jax.jit
def matmul_relu(a, b):
    return jnp.maximum(jnp.matmul(a, b), 0)

a = jnp.ones((1024, 1024), dtype=jnp.bfloat16)
b = jnp.ones((1024, 1024), dtype=jnp.bfloat16)

result = matmul_relu(a, b)
result.block_until_ready()  # Đợi phép tính hoàn thành trước khi đo thời gian
print(result.shape)
~~~

Dòng đầu tiên có thể chậm vì phải compile. Các lần gọi sau với hình dạng/dtype tương thích có thể tận dụng executable đã biên dịch. Vì vậy cần tách **compile time** khỏi **steady-state step time** trong benchmark.

### Dynamic shapes

Một mô hình liên tục nhận tensor với chiều dài khác nhau có thể kích hoạt recompilation. Các kỹ thuật phổ biến:

- Padding đến một số nhóm chiều dài cố định.
- Bucketing sequence lengths.
- Duy trì batch/shape ổn định trong một phần pipeline.
- Tối ưu sharding/layout và tránh chuyển host–device không cần thiết.
- Benchmark cả chi phí padding lẫn số lần biên dịch.

Đừng cố padding mọi chiều đến kích thước cực lớn: điều này có thể lãng phí HBM và compute. Mục tiêu là **cân bằng ít recompilation với không gian/tính toán bị padding**.

### Precision

Các dtype như `bfloat16` và `float32` thường dùng cho ML trên TPU. Các thế hệ mới có hỗ trợ precision phù hợp cho training/inference, nhưng không được mặc định mọi phép toán ở FP8 hoặc BF16 cho kết quả chất lượng như FP32. Đánh giá convergence, loss scaling, numerical stability và độ chính xác của kết quả.

## 6. Chuyển yêu cầu nghiệp vụ thành đặc tả workload

Một bản yêu cầu hạ tầng ML nên ghi **mục tiêu workload** trước khi nói tới loại TPU.

| Nhóm | Trường cần thu thập | Ví dụ minh họa |
|---|---|---|
| Loại workload | Pretrain, fine-tune, batch inference, online inference | Fine-tuning encoder |
| Framework | JAX, PyTorch/XLA, TensorFlow, serving runtime | JAX |
| Model | Số tham số, kiến trúc, operator, tokenizer | Dense Transformer |
| Data | Kích thước, vị trí, format, tốc độ đọc | 2 TiB parquet/TFRecord |
| Sequence | Input/output length, phân bố length | 512–2.048 tokens |
| Batch | Global batch, per-device batch, gradient accumulation | Cần benchmark |
| Precision | BF16/FP32/mixed precision | BF16 + FP32 accumulators |
| Memory | Weights, activations, gradients, optimizer, KV cache | Chưa đo |
| Throughput | Samples/s, tokens/s hoặc steps/s | Mục tiêu do nhóm ML đặt |
| Latency | p50/p95, TTFT, TPOT nếu serving | Theo SLO |
| Reliability | Checkpoint cadence, RTO, preemption tolerance | Có resume |
| Security | PII, data residency, model access | Confidential dataset |
| Budget | Chi phí/experiment, chip-hours tối đa | Theo quota dự án |

Dữ liệu ví dụ là mô tả cách ghi yêu cầu, không phải kết quả đo thực tế.

### Training và inference khác nhau thế nào?

**Training** có cả forward pass, backward pass và optimizer step; cần HBM cho gradient/optimizer state và có thể có communication lớn giữa chip.

**Fine-tuning** có thể dùng adapter/LoRA để giảm phần tham số cần update nhưng vẫn cần tính attention và lưu activation tùy kỹ thuật.

**Batch inference** tập trung throughput; có thể gom nhiều yêu cầu và xử lý trong thời gian dài.

**Online inference** quan tâm latency p95, time to first token (TTFT), time per output token (TPOT), tokens/s và availability. Batching tăng throughput nhưng có thể tăng thời gian đợi của từng request nếu không được quản lý.

## 7. Ước lượng HBM: không chỉ nhìn kích thước model

Một phép tính thô cho bộ nhớ weights:

~~~text
Weight memory ≈ number_of_parameters × bytes_per_parameter
~~~

Ví dụ **giả định** model dense 7 tỷ tham số lưu BF16:

~~~text
7,000,000,000 × 2 bytes ≈ 14,000,000,000 bytes ≈ 13.0 GiB
~~~

Đây **chỉ là bộ nhớ weights**. Không thể từ đó kết luận model vừa một TPU có HBM 32 GiB với mọi sequence length và concurrency.

### Training cần thêm những gì?

- Gradient tensors.
- Optimizer states, ví dụ Adam có hai moment estimates.
- Activations cho backward pass.
- Temporary buffers, compiled programs, input batch.
- Checkpoint staging.
- Sharding/replication overhead và fragmentation.

### Inference cần thêm những gì?

- Weights.
- KV cache phụ thuộc batch, số layers, context length và concurrent sequences.
- Activation và temporary buffers.
- Runtime memory allocation.
- Potential model sharding và communication buffers.

Một số phương pháp như quantization, recomputation/activation checkpointing hoặc parameter-efficient tuning làm thay đổi nhu cầu HBM và chi phí compute. Chọn cách tối ưu sau khi profiler xác nhận bottleneck, không chỉ dựa vào một bảng tính lý thuyết.

### HBM trên từng chip và sharding

Dung lượng HBM “tổng” của một slice là tổng phần cứng, nhưng **không phải một vùng bộ nhớ dùng chung trong suốt**. Framework cần phân chia tensor qua thiết bị và trả chi phí communication khi ghép kết quả. Nếu một tensor không được sharding hợp lệ hoặc một operation cần materialize toàn bộ tại một chip, vẫn có thể OOM dù tổng HBM slice lớn.

## 8. Tối ưu batch size và hình dạng tensor

Batch size có thể ảnh hưởng đến độ bão hòa MXU và lượng HBM dùng.

- Batch quá nhỏ: TPU có thể thiếu công việc, overhead lớn.
- Batch quá lớn: OOM, convergence thay đổi hoặc tăng latency queue.
- Sequence length quá biến động: compile lại hoặc padding nhiều.
- Layout/sharding không tối ưu: tăng lượng all-gather và collective communication.

Với training phân tán:

~~~text
Global batch size
  = per-device batch size
    × total participating devices
    × gradient accumulation steps
~~~

Đây là công thức minh họa khi các thiết bị xử lý phần dữ liệu không trùng lặp và cấu hình data parallel tương ứng. Khi dùng model/pipeline parallelism, “total devices” không thể tự động dùng toàn bộ TPU chips làm hệ số data parallel; cần tính theo số replica dữ liệu thực tế.

### Benchmark batch

1. Khởi động với batch vừa HBM.
2. Warm up JIT compile.
3. Đo steps/s, samples/s và device utilization.
4. Tăng batch theo mức có kiểm soát.
5. Kiểm tra OOM, numerical quality và convergence.
6. Đo chi phí/chip-hour trên một lượng công việc hoàn thành.
7. Chọn batch đạt mục tiêu hiệu quả **và** chất lượng mô hình.

## 9. Input pipeline: tránh để TPU đợi CPU hoặc lưu trữ

Một TPU có tốc độ tính toán lớn nhưng vẫn có thể rảnh phần lớn thời gian nếu host phải đọc file từ xa, giải mã ảnh hay tokenize quá chậm.

### Các nguồn nghẽn phổ biến

| Bottleneck | Dấu hiệu | Hướng cải thiện |
|---|---|---|
| Đọc dữ liệu | TPU duty cycle thấp, I/O wait cao | Parallel reads, prefetch, layout dataset |
| Decode/tokenize | CPU host bận nhưng TPU rảnh | Preprocess trước, vectorize hoặc tăng parallelism |
| Nhiều file nhỏ | Request/object metadata quá nhiều | Shard files/record format có chủ đích |
| Chuyển host-device | Transfer chiếm nhiều step time | Batch, pipeline và giữ tensor trên device |
| Dữ liệu khác region | Egress/latency tăng | Đặt dataset và compute gần nhau phù hợp residency |
| Shuffle/sampling | Tắc trước bước training | Prefetch, seed/partition ổn định |
| Checkpoint | Training bị dừng dài trong mỗi save | Async checkpoint và tần suất phù hợp |

Có thể dùng Cloud Storage cho dataset và checkpoint, nhưng cần xem throughput, request costs, location, IAM và pipeline reader. Với data loader, thiết kế nhiều worker phù hợp host CPU và tránh việc tất cả worker đọc một tập file trùng lặp.

### Kịch bản dữ liệu nhiều TB

Nếu dataset ban đầu ở on-premises, hãy chuẩn bị ingestion và integrity check trước khi cấp TPU đắt tiền. Không thuê TPU liên tục chỉ để chờ copy dữ liệu. Kiểm tra bandwidth/latency, checksum và yêu cầu residency. Sắp xếp job để provisioning TPU diễn ra sau khi dữ liệu đã sẵn sàng.

## 10. Huấn luyện phân tán: data, model và pipeline parallelism

Ba kỹ thuật chính:

| Kỹ thuật | Nguyên lý | Rủi ro |
|---|---|---|
| Data parallel | Nhiều replica xử lý các batch khác nhau và tổng hợp gradient | All-reduce, batch scaling, synchronization |
| Model/tensor parallel | Chia tensor hoặc layer giữa thiết bị | All-gather/all-to-all, HBM, topology |
| Pipeline parallel | Chia stages của mô hình qua các thiết bị | Pipeline bubbles, load imbalance |

Các hệ thống thực tế có thể phối hợp nhiều kỹ thuật. TPU slice và ICI giúp giảm communication overhead, nhưng vẫn cần thiết kế sharding phù hợp. Không lấy số chip làm hệ số tăng tốc mà bỏ qua network, optimizer state, pipeline flush và lỗi node.

### Checkpoint và khôi phục

Training nhiều giờ hoặc nhiều ngày cần:

- Checkpoint weights, optimizer state và training step.
- Lưu artifact/checkpoint ở vị trí bền vững ngoài TPU VM.
- Ghi code revision, dependency versions, random seed và config.
- Kiểm tra restore thực tế từ checkpoint.
- Có retry/backoff, xử lý preemption và khởi tạo lại toàn bộ distributed workers.
- Ràng buộc số lượng/retention checkpoint để kiểm soát chi phí.

Nếu chạy Spot, checkpoint cadence phải cân bằng giữa giá lưu trữ/IO và lượng compute có thể mất khi bị thu hồi.

## 11. Chọn nơi chạy: TPU VM, GKE hay nền tảng quản lý?

| Phương án | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|
| TPU VM / Compute Engine | Thử nghiệm, kiểm soát OS/runtime, script huấn luyện trực tiếp | Tự quản lý lifecycle, dependencies, checkpoint, cleanup |
| GKE Standard với TPU slice node pool | Nhiều job container, Kubernetes orchestration, nhóm platform | Chọn machine type/topology, requests/limits, node lifecycle |
| GKE Autopilot với TPU workload | Muốn giảm thao tác quản trị nodes khi cấu hình được hỗ trợ | Cách request TPU khác Standard, yêu cầu version/quota/manifest riêng |
| Vertex AI/managed ML khi hỗ trợ TPU | Muốn tích hợp pipeline/experiment/model lifecycle | Cần kiểm tra loại TPU, region và năng lực hỗ trợ hiện hành |

Không coi **Cloud Run** là nơi tùy ý gắn TPU giống TPU VM; phải đối chiếu accelerator support của dịch vụ chạy ứng dụng. Cloud Run có thể đóng vai trò HTTP API điều phối và gọi inference backend trên TPU.

### Chọn TPU VM cho lab

Một TPU VM đơn lẻ phù hợp để:

- Xác minh framework chạy đúng thiết bị.
- Đo compile/step time.
- Đo HBM trên một node.
- Tạo baseline model nhỏ.
- Gỡ lỗi trước khi mở rộng multi-host.

### Chọn GKE cho sản xuất

GKE phù hợp khi đã có nền tảng container, CI/CD, policy, IAM và observability. Tuy nhiên, TPU slice scheduling có quy tắc **all chips per node** cho pod xin TPU. Node pools đa host và training distributed còn cần đồng bộ số worker/replica, cấu hình networking và group scheduling theo hướng dẫn TPU/GKE.

## 12. Framework và TPU runtime: tránh mismatch

Trước khi chạy workload, kiểm tra ma trận:

~~~text
TPU generation × machine type × TPU software image
× libtpu version × JAX / PyTorch-XLA / TensorFlow
× serving/training framework × model checkpoint format
~~~

### JAX

JAX là lựa chọn phổ biến trên TPU, kết hợp `jax.jit`, `jax.numpy`, `jax.grad`, sharding và PJRT. Trên TPU VM hỗ trợ, tài liệu JAX dùng:

~~~bash
python3 -m pip install "jax[tpu]"
~~~

Đây là cách cài đặt **cho môi trường lab tương thích**. Với production, pin phiên bản JAX/JAXLIB/libtpu trong image được kiểm thử và theo compatibility matrix từng TPU generation.

### PyTorch/XLA

PyTorch có thể chạy trên TPU qua PyTorch/XLA hoặc runtime TPU được hỗ trợ. Không giả định mọi PyTorch model, custom CUDA extension, TorchInductor/Triton kernel hoặc operator đều chuyển sang TPU mà không sửa code. Kiểm tra:

- Phiên bản PyTorch/XLA và libtpu tương ứng.
- Device placement và graph compilation behavior.
- Distributed strategy.
- Unsupported operations và fallback CPU.
- Numerical quality và checkpoint compatibility.

### TensorFlow

TensorFlow có phiên bản runtime TPU theo thế hệ, nhưng khả năng hỗ trợ không đồng nhất. Đặc biệt, **TPU7x (Ironwood) hiện không được TensorFlow hỗ trợ** trong bảng TPU software versions của Google. Với model TensorFlow cũ, có thể phải chọn generation khác hoặc điều chỉnh framework.

### Inference runtime

Đối với LLM serving, Google Cloud đã tài liệu hóa vLLM và SGLang với backend JAX hoặc PyTorch tương ứng, chẳng hạn `vllm-jax`, `vllm-torchtpu`, `sglang-jax` hoặc `sglang-torchtpu`. Hỗ trợ model/quantization/parallelism thay đổi theo release: đọc bảng chính thức thay vì chọn runtime chỉ theo tên.

## 13. Preflight: project, zone, API, IAM, quota và capacity

TPU là tài nguyên chuyên biệt; **có quota không có nghĩa chắc chắn có physical capacity** ở zone cần dùng.

Checklist tối thiểu:

- Chọn project billing và region/zone hỗ trợ machine type.
- Bật API tương ứng với **cách cấp phát** (Compute Engine/GKE hoặc Cloud TPU API).
- Kiểm tra quota đúng TPU family, region/zone và provisioning model.
- Xác nhận stock/capacity thực tế hoặc reservation đã được chấp thuận.
- Kiểm tra service account chạy job có quyền đọc dataset và ghi checkpoint.
- Cấu hình VPC, egress, DNS, firewall, private storage access.
- Chọn OS image hoặc container hỗ trợ TPU generation và libtpu.
- Có budget alert, owner, thời gian dự kiến chạy và cleanup plan.
- Lưu code/data/model artifacts ngoài VM trước khi có nguy cơ bị xóa.

### Hai họ quota cần phân biệt

- **Compute Engine/GKE TPU:** dùng quota Compute Engine API cho accelerator machine/slice theo cách cấp phát tương ứng.
- **Cloud TPU API:** có quota riêng theo TPU version, zone và consumption option.

Không lấy một dòng quota từ Cloud TPU API để kết luận GKE TPU node pool sẽ tạo được. Tài liệu TPU GKE mô tả quota khác với lệnh tạo TPU qua API.

### Ví dụ kiểm tra API cho TPU VM Compute Engine

~~~bash
gcloud config set project PROJECT_ID
gcloud services enable compute.googleapis.com
gcloud compute zones list
~~~

Lệnh trên **không đảm bảo** rằng zone trong danh sách còn TPU capacity. Xem danh mục machine types/availability và quota phù hợp trong Console trước khi provision.

## 14. Thực hành an toàn: tạo TPU v6e VM và chạy JAX

Bài lab chỉ thực hiện trên **project sandbox đã được duyệt chi phí**. TPU có thể đắt tiền ngay cả khi chưa chạy model. Không tự chạy lệnh tạo tài nguyên dưới đây trên production.

### Đầu vào

- Google Cloud CLI đã đăng nhập, có quyền tạo/xóa Compute Engine instance.
- Quota và capacity v6e tại zone lựa chọn.
- Billing, budget alert và owner được xác nhận.
- VPC/service account cho workload có quyền phù hợp.
- Kế hoạch xóa TPU VM ngay sau bài lab.

### Bước 1: Tạo TPU VM

Ví dụ từ tài liệu Compute Engine dùng một VM có 4 chip Trillium:

~~~bash
gcloud compute instances create tpu-lab-v6e \
  --machine-type=ct6e-standard-4t \
  --zone=europe-west4-a \
  --image-project=ubuntu-os-accelerator-images \
  --image-family=ubuntu-accel-2204-amd64-tpu-v5e-v5p-v6e \
  --maintenance-policy=TERMINATE \
  --project=PROJECT_ID
~~~

Chọn `europe-west4-a` chỉ là ví dụ tài liệu; đổi sang zone phù hợp quota, capacity, data residency và giá của tổ chức. Dòng `maintenance-policy=TERMINATE` là yêu cầu vòng đời cho TPU VM ở cấu hình này; hãy chuẩn bị checkpoint để đối phó sự kiện bảo trì.

### Bước 2: Kiểm tra VM và đăng nhập

~~~bash
gcloud compute instances describe tpu-lab-v6e \
  --zone=europe-west4-a \
  --project=PROJECT_ID

gcloud compute ssh tpu-lab-v6e \
  --zone=europe-west4-a \
  --project=PROJECT_ID
~~~

Nếu môi trường dùng IAP hoặc không cấp external IP, cần SSH theo phương thức được tổ chức phê duyệt; không mở port 22 toàn Internet chỉ để thử lab.

### Bước 3: Kiểm tra runtime

Trong TPU VM:

~~~bash
python3 --version
python3 -m pip install "jax[tpu]"
python3 -c 'import jax; print(jax.devices()); assert jax.devices()[0].platform == "tpu"'
~~~

Nếu image đã có các package tương thích, không cần cài lại. Nếu xuất hiện lỗi libtpu/PJRT, dùng version/image theo hướng dẫn framework–TPU generation thay vì cài ngẫu nhiên các wheel.

### Bước 4: Chạy phép nhân ma trận có kiểm soát

Tạo file `tpu_smoke_test.py`:

~~~python
import time
import jax
import jax.numpy as jnp

assert any(d.platform == "tpu" for d in jax.devices()), "No TPU devices detected"

@jax.jit
def step(x, y):
    return jnp.matmul(x, y)

x = jnp.ones((1024, 1024), dtype=jnp.bfloat16)
y = jnp.ones((1024, 1024), dtype=jnp.bfloat16)

start = time.perf_counter()
result = step(x, y)
result.block_until_ready()
first_call = time.perf_counter() - start

start = time.perf_counter()
result = step(x, y)
result.block_until_ready()
steady_call = time.perf_counter() - start

print("Devices:", jax.devices())
print("Result shape:", result.shape)
print("First call seconds:", round(first_call, 4))
print("Warm call seconds:", round(steady_call, 4))
~~~

Chạy:

~~~bash
python3 tpu_smoke_test.py
~~~

Lần đầu có thể bao gồm JIT compilation nên chậm hơn; số liệu đo chỉ là **smoke test**, không dùng để so sánh giá/hiệu năng giữa TPU generation. Cần đo nhiều bước, warmup, shape đại diện, input pipeline và độ ổn định nếu muốn benchmark chính thức.

### Bước 5: Dọn sạch tài nguyên

Thoát khỏi VM, rồi chạy trên máy có Google Cloud CLI:

~~~bash
gcloud compute instances delete tpu-lab-v6e \
  --zone=europe-west4-a \
  --project=PROJECT_ID
~~~

Xác nhận VM đã bị xóa, xem attached disks/IP còn tồn tại và kiểm tra Billing. Nếu có checkpoint/dataset test hoặc các bucket tạm, xóa theo quy trình và retention policy của tổ chức.

## 15. Chạy workload TPU trên GKE Standard

Đối với hệ thống có nhiều job hoặc cần scheduler Kubernetes, TPU được cấp dưới dạng TPU slice node pool với machine type/topology cụ thể.

### Quy tắc resource request

GKE dùng resource `google.com/tpu`. Khi một container xin TPU trên node TPU slice, **giá trị request và limit phải bằng toàn bộ số TPU chips gắn với node đó** theo quy tắc GKE TPU scheduling.

Ví dụ node `ct6e-standard-4t` có 4 chip, nên workload cần:

~~~yaml
resources:
  requests:
    google.com/tpu: 4
  limits:
    google.com/tpu: 4
~~~

Không xin `google.com/tpu: 1` trên node 4-chip với kỳ vọng Kubernetes tự chia node thành bốn pod mỗi pod một chip.

### Ví dụ Pod cho slice một host

Giả sử admin đã provision GKE Standard node pool TPU v6e 4-chip với topology `2x2`:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: jax-tpu-smoke
  labels:
    app: tpu-lab
spec:
  restartPolicy: Never
  nodeSelector:
    cloud.google.com/gke-tpu-accelerator: tpu-v6e-slice
    cloud.google.com/gke-tpu-topology: "2x2"
  containers:
    - name: jax
      # Ví dụ lab; trong production pin image digest.
      image: us-docker.pkg.dev/cloud-tpu-images/jax-ai-image/tpu:latest
      command:
        - /bin/bash
        - -c
        - |
          python3 -c 'import jax; print(jax.devices())'
      resources:
        requests:
          google.com/tpu: 4
        limits:
          google.com/tpu: 4
~~~

Manifest này **không tự tạo node pool**. Nếu chưa có node tương thích, Pod sẽ Pending. Nên dùng image được pin version/digest trong production và kiểm tra GKE version/TPU runtime compatibility.

Các lệnh quan sát trong một cluster lab:

~~~bash
kubectl apply -f jax-tpu-smoke.yaml
kubectl get pods -o wide
kubectl describe pod jax-tpu-smoke
kubectl logs jax-tpu-smoke
kubectl delete pod jax-tpu-smoke
~~~

Ví dụ `kubectl apply` chỉ chạy khi đã có quyền Kubernetes và node pool được chuẩn bị. GKE Standard còn cần quản lý node pool scaling/quota; xóa Pod **không nhất thiết xóa node** hoặc dừng chi phí accelerator.

### Khác biệt multi-host

Với multi-host TPU slice, các worker phải được lập lịch theo topology và tham gia distributed job thống nhất. Tài liệu GKE hướng dẫn Job/JobSet, node pool, placement và networking. Không tạo một Pod đơn lẻ xin toàn bộ chip của nhiều node; mỗi Pod xin chip **trên node của nó**, còn orchestration đảm bảo các thành phần multi-host khởi động và phục hồi phù hợp.

### GKE Autopilot

Autopilot có mô hình request và provisioning khác GKE Standard. Không dùng nguyên các lệnh tạo node pool của Standard. Khi dùng Autopilot, chọn TPU accelerator và workload manifest theo hướng dẫn phiên bản TPU, topology, quota và điều kiện được hỗ trợ. Xác minh hiện trạng trước khi triển khai.

## 16. Online inference trên TPU: throughput và latency

Đối với LLM/chatbot, cần phân biệt hai giai đoạn:

- **Prefill:** xử lý prompt đầu vào, thường tính toán nhiều phép nhân ma trận.
- **Decode:** sinh token tiếp theo từng bước, thường nhạy với memory bandwidth và KV cache.

Các chỉ số cần đo:

| Chỉ số | Ý nghĩa | Vì sao quan trọng |
|---|---|---|
| Time to First Token (TTFT) | Từ request tới token đầu | Trải nghiệm phản hồi ban đầu |
| Time per Output Token (TPOT) | Thời gian mỗi token sinh ra | Độ mượt của streaming |
| Tokens/s/chip | Thông lượng chuẩn hóa | Hiệu quả accelerator |
| p95 end-to-end latency | Độ trễ của toàn request | SLO người dùng |
| Concurrency và queue wait | Số yêu cầu đang chờ/phục vụ | Lập kế hoạch capacity |
| KV-cache utilization | Mức dùng memory cho context | Nguy cơ OOM/giảm concurrency |
| Error/timeout rate | Tỷ lệ request thất bại | Reliability |
| Cost per 1M tokens | Chi phí đơn vị | FinOps |

Các serving stack như vLLM hoặc SGLang có backend phù hợp với JAX/PyTorch trên TPU, nhưng không phải model nào cũng hỗ trợ như nhau. Kiểm tra **model architecture, quantization, TP/DP config, context length và version**.

### Dynamic batching

Batching nhiều request có thể tăng throughput, nhưng một queue quá dài làm TTFT xấu đi. Phải tối ưu theo SLO p95 và cost per token, không chỉ maximum tokens/s trong benchmark tổng hợp.

### Tách API và model server

Một kiến trúc phù hợp:

~~~mermaid
flowchart LR
  C[Client] --> API[API / auth / quota]
  API --> Q[Request queue / router]
  Q --> T[TPU model serving pool]
  T --> R[Streaming response]
  R --> C
  API --> M[Monitoring / tracing / alerts]
  T --> M
  T --> S[Model weights / checkpoint storage]
~~~

API có thể chạy Cloud Run/GKE CPU, trong khi backend model chạy TPU. Cấu hình tối ưu phụ thuộc tốc độ tải weights, concurrency, cold start, model size và yêu cầu phân tách mạng.

## 17. Monitoring và profiling: TPU có đang thực sự làm việc?

Mục tiêu không chỉ là “job chạy không lỗi” mà là biết bottleneck nằm ở compute, memory, host, I/O hay communication.

### Các lớp theo dõi

| Lớp | Tín hiệu cần quan sát |
|---|---|
| TPU device | Accelerator duty cycle, HBM use, memory bandwidth utilization |
| Host VM | CPU, RAM, disk/network I/O, loader queue |
| XLA | Compile time, recompilation, operation profile, collective overhead |
| Training | Steps/s, tokens/s, loss, gradient/optimizer stability |
| Inference | TTFT, TPOT, queue delay, tokens/s, error rate |
| Distributed | Worker failures, collective communication, stragglers |
| Cost | Chip-hours, idle time, checkpoint/storage/egress costs |

Google Cloud có metric như accelerator duty cycle và memory bandwidth utilization cho TPU versions hỗ trợ. Dùng **Cloud Monitoring** và công cụ profiler **XProf** (cho workload XLA-based) để phân tích timeline và operation-level bottlenecks.

### Cách phân loại bottleneck

1. **Duty cycle thấp, host CPU cao:** có thể input-bound; đo decode/tokenization/read throughput.
2. **HBM gần đầy/OOM:** giảm batch/sequence, cải tiến sharding, activation checkpointing.
3. **Compile nhiều:** xem shape variability, static args và caching.
4. **Collective time lớn:** xem topology và partitioning strategy.
5. **Thời gian tải model lớn:** xem storage/size, initialization, prefetch.
6. **Throughput cao nhưng p95 latency xấu:** xem queue wait và batching.
7. **Training loss bất thường:** kiểm tra precision, data distribution, optimizer và numerical stability.

Không nhìn riêng “device utilization cao” để kết luận thành công: một kernel có thể bận nhưng làm việc không cần thiết do padding, dữ liệu lặp hoặc nhiều phép chuyển đổi.

## 18. Bảo mật và quản trị dữ liệu/model

Workload ML thường dùng dataset, model checkpoint và đôi khi có dữ liệu nhạy cảm. Thiết kế bảo mật cần đi trước việc cấp TPU.

### IAM và danh tính

- Dùng service account riêng cho TPU VM hoặc GKE workload.
- Cấp quyền đọc dữ liệu chỉ ở bucket/path cần dùng.
- Cấp quyền ghi checkpoint/artifact theo phạm vi tối thiểu.
- Với GKE, ưu tiên Workload Identity Federation for GKE khi phù hợp.
- Không đặt service account key hoặc token vào image/container.
- Giới hạn quyền tạo/xóa máy TPU và quota adjustment cho nhóm được ủy quyền.

### Network và egress

- Đặt accelerator trong VPC/subnet phù hợp và hạn chế inbound.
- Dùng private access/DNS/routing theo phạm vi dịch vụ, không mở SSH toàn Internet.
- Kiểm tra đường kết nối Cloud Storage và artifact registry.
- Áp dụng giới hạn egress khi dữ liệu/model không được phép ra ngoài.
- Theo dõi log truy cập dataset/checkpoint theo chính sách.

### Supply chain

- Pin container digest và Python package versions.
- Kiểm tra model weights từ nguồn đáng tin cậy, license và provenance.
- Quét image, quản lý dependencies và secrets.
- Không tải script/trọng số không kiểm chứng vào VM production có quyền truy cập dữ liệu nhạy cảm.
- Lưu metadata dataset version, code commit, TPU type và framework version để tái tạo kết quả.

### Dữ liệu và retention

- Phân loại PII, quyền truy cập, data residency và encryption.
- Không đưa dữ liệu mẫu chứa thông tin nhạy cảm vào log/profile công khai.
- Lưu checkpoint theo retention và encryption chính sách.
- Xem trace/profile có thể chứa tensor shapes hoặc một số metadata workload cần bảo vệ.

## 19. Chi phí TPU và mô hình cấp phát

Chi phí TPU thay đổi theo **version, location và consumption model**. Các phương án gồm on-demand, Spot, Flex-start và reservations/commitments khi được hỗ trợ.

| Phương án | Phù hợp | Đánh đổi |
|---|---|---|
| On-demand | Lab, thử nghiệm, workload biến động | Không đảm bảo capacity, đơn giá theo thời điểm |
| Spot | Job huấn luyện có checkpoint, chịu preemption | Có thể bị thu hồi, phải resume |
| Flex-start | Job ngắn có thể chờ cấp phát trong giới hạn | Có giới hạn thời lượng/chính sách cấp phát |
| Reservation/commitment | Workload đều, nhu cầu lớn và dự báo được | Cam kết tài chính, capacity management |
| GKE managed scheduling | Đội platform chạy nhiều workload | Vẫn cần tối ưu node utilization và cleanup |

Giá niêm yết thường biểu diễn **theo chip-hour**, nhưng hóa đơn có thể gồm thành phần khác như compute resources, storage, networking, reservations hoặc dịch vụ orchestration. Tra [Cloud TPU Pricing](https://cloud.google.com/tpu/pricing) theo đúng cấu hình trước khi lập ngân sách.

### Công thức ước tính

~~~text
Accelerator cost (ước lượng)
  ≈ number_of_chips × billable_hours × applicable_price_per_chip_hour

Total experiment cost
  ≈ accelerator cost
    + persistent storage / checkpoint storage
    + data transfers and operations
    + supported host / orchestration charges
    + profiling / logging / monitoring charges where applicable
~~~

Đây là khung dự toán, không thay thế SKU/pricing thật và không nên cộng hai lần khoản đã bao gồm trong SKU.

### Tối ưu giá trị công việc

Tính các chỉ số như:

- **Cost per completed training run** (gồm cả retry và thời gian compile).
- **Cost per million training tokens**.
- **Cost per million generated tokens**.
- **Cost per evaluated model**.
- **Useful accelerator duty cycle**.
- **Checkpoint recovery loss** tính theo compute time có thể mất.

Một TPU thế hệ mới có giá chip-hour cao hơn nhưng hoàn thành workload nhanh hơn vẫn có thể rẻ hơn trên **đơn vị kết quả**. Cần benchmark cùng dataset, model quality, precision và mục tiêu latency trước khi kết luận.

### Tránh chi phí rỗi

- Không cấp TPU từ đầu khi dataset chưa sẵn sàng.
- Dùng checkpoint để chia job và hỗ trợ Spot khi phù hợp.
- Xóa/stop tài nguyên theo cơ chế hỗ trợ, xác nhận billing state.
- Với GKE, kiểm tra node pools/TPU slices sau khi xóa Pod/Job.
- Xem idle capacity trong reservations và chính sách re-use.
- Cài budget alert và owner cho resource.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tạo TPU VM thất bại | Quota thiếu, zone không hỗ trợ hoặc capacity không có | Kiểm tra version, zone, API, quota và reservation |
| GKE Pod Pending | Chưa có node pool, topology/selector không khớp | Kiểm tra node labels, topology và cluster version |
| GKE xin 1 TPU trên node 4-chip | GKE không chia nhỏ TPU resource theo cách đó | Request/limit toàn bộ số chip trên node |
| JAX chỉ thấy CPU | Image/libtpu mismatch hoặc accelerator chưa sẵn sàng | Kiểm tra `jax.devices()`, runtime, image |
| PyTorch model có unsupported op | CUDA/custom kernel không có TPU path | Kiểm tra PyTorch/XLA compatibility và sửa operator |
| TensorFlow trên TPU7x không hoạt động | Generation không hỗ trợ TensorFlow | Chọn supported generation hoặc framework khác |
| First step rất chậm | XLA JIT compile hoặc input pipeline setup | Tách compile time với steady-state time |
| Chạy lâu nhưng throughput thấp | CPU input-bound, shape/padding hoặc communication | Profile XProf, data loader, sharding |
| TPU OOM | Weights + activations + KV cache vượt HBM | Giảm batch/seq, sharding, quantization phù hợp |
| Training mất tiến độ sau Spot | Không có checkpoint bền vững | Lưu/kiểm tra restore checkpoint, retry |
| Inference TTFT xấu | Queue/batching/cold loading | Đo queue wait, warmup và concurrency |
| Multi-host job treo | Một worker không khởi động hoặc collective mismatch | Kiểm tra group scheduling và logs từng host |
| Chi phí vượt budget | TPU idle/oversized, job retry liên tục | Đo chip-hours, unit cost và cleanup |
| Kết quả training khác biệt | Precision, seed, runtime hoặc data không đồng nhất | Pin environment, kiểm tra convergence |
| Dataset đọc chậm | Storage location, file layout hoặc host I/O | Parallel reads, prefetch, shard dữ liệu |

## 21. Bài tập tình huống: chọn TPU cho ba workload

### Workload A: fine-tune mô hình ngôn ngữ nội bộ

Đặc điểm: model Transformer, sequence length 2.048, batch có thể điều chỉnh, cần chạy vài giờ mỗi lần và chấp nhận resume sau preemption.

Đề xuất đánh giá:

1. Xác nhận JAX/PyTorch-XLA và model operators được hỗ trợ.
2. Ước tính weights, activation và optimizer/HBM.
3. Thử slice v6e hoặc phiên bản khác có quota/capacity.
4. Pin runtime, checkpoint vào Cloud Storage.
5. Benchmark steady-state tokens/s và cost per completed run.
6. Cân nhắc Spot/Flex-start nếu phù hợp khả năng preemption.

### Workload B: API realtime gợi ý sản phẩm

Đặc điểm: request nhỏ, SLA p95 thấp, embeddings lớn, traffic thay đổi theo thời điểm.

Đề xuất đánh giá:

1. Thử CPU/GPU/TPU baseline; không mặc định TPU hiệu quả hơn.
2. Kiểm tra model có SparseCore/embedding support phù hợp hay không.
3. Ước lượng HBM, concurrency và batching.
4. Thiết kế autoscaling/capacity, tránh cold load quá lâu.
5. Đo p95 end-to-end latency, cost per 1.000 requests.
6. Giữ API auth/quota trên lớp serving thích hợp và cách ly model backend.

### Workload C: batch ETL chuyển đổi CSV

Đặc điểm: parse CSV, làm sạch chuỗi, đọc/ghi nhiều file và vài phép cộng đơn giản.

Đề xuất: trước tiên dùng CPU/batch processing phù hợp. Nếu phần lớn thời gian là parsing/I/O chứ không phải tensor compute, TPU sẽ dễ bị idle và gây lãng phí. Chỉ cân nhắc TPU khi có phần ML tensor lớn tách riêng và benchmark chứng minh lợi ích.

### Câu hỏi phân tích

- Workload nào cần checkpoint thường xuyên nhất?
- Tại sao Workload B phải ưu tiên p95 hơn peak throughput?
- Khi nào nên dùng nhiều TPU chips trên một host thay vì nhiều hosts?
- Điều gì khiến v6e với giá thấp hơn một thế hệ khác vẫn có thể đắt hơn trên mỗi training run?
- Ranh giới dữ liệu và IAM thay đổi thế nào khi dùng model nội bộ nhạy cảm?

## 22. Checklist trước khi triển khai production

- [ ] Loại workload và SLO (steps/s hoặc TTFT/TPOT) được định nghĩa.
- [ ] Framework và TPU generation có compatibility matrix được xác nhận.
- [ ] Model operators/precision/quantization đã được thử nghiệm.
- [ ] HBM estimate gồm weights, activations/gradients hoặc KV cache.
- [ ] Batch/sequence lengths và sharding strategy đã được đánh giá.
- [ ] Topology và số chips/host/chips/slice được xác nhận.
- [ ] Zone/quota/capacity hoặc reservation đã được chuẩn bị.
- [ ] TPU software image và libtpu/JAX/PyTorch được pin version.
- [ ] Dataset pipeline có throughput đủ để không làm TPU idle.
- [ ] Checkpoint/resume được thử, nhất là khi dùng Spot.
- [ ] Service accounts, bucket access, networking và secrets tuân thủ chính sách.
- [ ] Benchmark đo steady-state, compile overhead, cost per useful unit.
- [ ] Có monitoring TPU duty cycle, HBM, CPU/I/O, inference/training KPIs.
- [ ] Có cảnh báo lỗi worker, OOM, queue, job retries và chi phí.
- [ ] Có cơ chế cleanup cho TPU VM và GKE node pool.
- [ ] Có kế hoạch rollback và khả năng phục hồi khi mất host/slice.
- [ ] Dataset/model version, seed, code revision và image digest được lưu.
- [ ] Chi phí vùng, đời TPU và mô hình cấp phát được xác minh trước khi phê duyệt.

## Câu hỏi ôn tập

1. TPU khác CPU/GPU về loại tính toán và compiler như thế nào?
2. Vì sao một model 7 tỷ tham số BF16 không thể kết luận sẽ vừa HBM chỉ bằng phép tính weights?
3. TPU slice khác TPU VM và TPU Pod ở điểm nào?
4. Vì sao JIT compile và dynamic shapes ảnh hưởng đến benchmark TPU?
5. Khi nào một workload I/O-bound không nên chạy TPU?
6. GKE xin `google.com/tpu: 1` trên node có 4 chip có hợp lệ theo quy tắc TPU scheduling không?
7. Phân biệt quota khi tạo Compute Engine/GKE TPU và Cloud TPU API.
8. Vì sao có quota nhưng vẫn không tạo được TPU ở zone cụ thể?
9. Spot TPU phù hợp với workload nào, và checkpoint có vai trò gì?
10. Những metric nào cần đo để tối ưu LLM online serving trên TPU?
11. Vì sao TensorFlow không phải lựa chọn mặc định cho TPU7x?
12. Chi phí per chip-hour và cost per completed training run có thể dẫn tới quyết định khác nhau như thế nào?

## Kết luận

Cloud TPU là hạ tầng tăng tốc chuyên biệt cho các phép toán tensor trong học máy. Lựa chọn thành công không chỉ phụ thuộc vào thế hệ TPU có TFLOPS cao hay HBM lớn mà còn phụ thuộc vào **mức phù hợp của model, framework/XLA, hình dạng tensor, topology, sharding, data pipeline, quota, capacity và yêu cầu phục hồi**.

Với bài toán training, hãy đo bước huấn luyện ổn định, tốc độ tokens/s, chất lượng mô hình và khả năng resume. Với inference, hãy đo TTFT, TPOT, p95 latency, concurrency, KV cache và chi phí trên mỗi token. TPU VM thích hợp để thử nghiệm có kiểm soát; GKE phù hợp với điều phối container ở quy mô lớn khi đã đáp ứng nguyên tắc node pool, topology và `google.com/tpu`.

Khi lựa chọn dựa trên benchmark và SLO, bảo vệ dataset/model bằng IAM, đặt checkpoint bên ngoài VM và theo dõi unit economics, Cloud TPU có thể mang lại hiệu quả đáng kể cho workload học máy phù hợp mà không gây lãng phí hạ tầng chuyên biệt.

## Tài liệu tham khảo

- [Understand Tensor Processing Units](https://cloud.google.com/docs/compute-area/tpus)
- [Cloud TPU overview](https://cloud.google.com/tpu/docs/intro-to-tpu)
- [Cloud TPU versions and machine types](https://cloud.google.com/compute/docs/tpus/tpu-machines)
- [Plan your Cloud TPU resources](https://cloud.google.com/tpu/docs/plan-tpus)
- [Create a TPU VM instance](https://cloud.google.com/compute/docs/tpus/create-tpu-vm-instance)
- [Quickstart: Create a TPU instance](https://cloud.google.com/compute/docs/tpus/quickstart-create-tpu-instance)
- [TPU software versions and framework support](https://cloud.google.com/tpu/docs/runtimes)
- [Cloud TPU quotas](https://cloud.google.com/tpu/docs/quota)
- [About TPUs in GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/tpus)
- [Plan TPUs in GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/plan-tpus)
- [Deploy TPU workloads in GKE Standard](https://cloud.google.com/kubernetes-engine/docs/how-to/tpus)
- [Deploy TPU workloads on GKE Autopilot](https://cloud.google.com/kubernetes-engine/docs/how-to/tpus-autopilot)
- [Cloud TPU performance guide](https://cloud.google.com/tpu/docs/performance-guide)
- [Profile your model on Cloud TPU](https://cloud.google.com/tpu/docs/profile-tpu-vm)
- [Monitor Cloud TPU VMs](https://cloud.google.com/tpu/docs/troubleshooting/tpu-vm-monitoring)
- [Run inference on Cloud TPU](https://cloud.google.com/tpu/docs/tpu-inference)
- [Cloud TPU pricing](https://cloud.google.com/tpu/pricing)
- [JAX installation on Cloud TPU](https://docs.jax.dev/en/latest/installation.html)

