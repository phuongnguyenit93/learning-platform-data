# Phân biệt workload huấn luyện, suy luận và xử lý đồ họa

GPU và các bộ tăng tốc chuyên dụng có thể xử lý nhiều phép tính song song cùng lúc. Chúng thường mang lại lợi ích lớn cho huấn luyện mô hình AI, phục vụ mô hình đã huấn luyện và dựng hình đồ họa. Tuy nhiên, ba nhóm workload này có mục tiêu và kiểu truy cập tài nguyên khác nhau. Một cấu hình GPU phù hợp để huấn luyện mô hình lớn chưa chắc là lựa chọn kinh tế cho suy luận có độ trễ thấp hoặc dựng hình thời gian thực.

Khi thiết kế hạ tầng tính toán đám mây, cần hiểu công việc đang thực hiện, xác định chỉ số thành công, rồi chọn GPU, VRAM, CPU, RAM, lưu trữ và mạng phù hợp. Bài học này tập trung vào cách phân biệt **training**, **inference** và **graphics**, cách chúng sử dụng GPU, cùng quy trình lựa chọn và vận hành cấu hình tăng tốc.

## 1. GPU và bộ tăng tốc xử lý công việc gì?

CPU thường có ít lõi hiệu năng cao, phù hợp với luồng điều khiển, tác vụ tuần tự và nhiều loại công việc hệ thống. GPU có số lượng đơn vị xử lý song song lớn, phù hợp với những phép toán giống nhau được thực hiện trên nhiều phần tử dữ liệu.

Một GPU hiện đại có thể chứa:

- Các đơn vị xử lý số học song song.
- Bộ tăng tốc ma trận hoặc tensor cho phép nhân ma trận và phép toán AI.
- Bộ nhớ riêng trên card, thường gọi là VRAM hoặc device memory.
- Bộ điều khiển bộ nhớ với băng thông cao.
- Cache và bộ nhớ dùng chung trên thiết bị.
- Bộ mã hóa/giải mã video hoặc khối chức năng chuyên dụng tùy dòng GPU.
- Giao tiếp với CPU và các GPU khác qua PCIe hoặc liên kết tốc độ cao riêng.

GPU không tự động làm mọi chương trình nhanh hơn. Chương trình phải có đủ tính song song, dữ liệu cần được đưa tới GPU hiệu quả và phần mềm phải hỗ trợ kiến trúc tăng tốc. Nếu workload dành phần lớn thời gian cho I/O, xử lý tuần tự hoặc chờ dữ liệu từ CPU, GPU có thể ít được sử dụng.

Ngoài GPU, hạ tầng đám mây có thể cung cấp các bộ tăng tốc chuyên dụng khác như TPU hoặc accelerator ASIC. Các thiết bị này thường được tối ưu cho một nhóm phép toán và hệ sinh thái phần mềm cụ thể. Khi lựa chọn, cần xét framework, toán tử được hỗ trợ, khả năng chuyển đổi mô hình và chi phí vận hành.

## 2. Phân biệt training, inference và graphics

Ba nhóm workload có thể cùng chạy trên GPU nhưng mục tiêu khác nhau:

| Tiêu chí | Huấn luyện (training) | Suy luận (inference) | Xử lý đồ họa (graphics) |
|---|---|---|---|
| Mục tiêu | Tìm tham số mô hình bằng cách tối ưu hàm mất mát | Dùng mô hình đã có để tạo dự đoán hoặc nội dung | Tạo, biến đổi hoặc hiển thị hình ảnh và khung hình |
| Đầu vào | Dữ liệu huấn luyện, nhãn hoặc tín hiệu phản hồi | Request, prompt, ảnh, âm thanh hoặc dữ liệu cần dự đoán | Scene, geometry, texture, shader, camera và ánh sáng |
| Công việc chính | Forward pass, tính loss, backward pass, cập nhật trọng số | Forward pass và xử lý request | Rasterization, shading, ray tracing, compositing hoặc encoding |
| Trạng thái mô hình | Trọng số, gradient, optimizer state và activation | Trọng số đã huấn luyện, activation và cache phục vụ request | Asset đồ họa, texture, buffer và trạng thái scene |
| Nhu cầu bộ nhớ | Thường cao do gradient, optimizer và activation | Phụ thuộc kích thước mô hình, batch và concurrency | Phụ thuộc độ phân giải, texture, geometry và số khung hình |
| Kiểu tối ưu | Thông lượng và thời gian hoàn thành quá trình huấn luyện | Độ trễ, thông lượng, concurrency và chi phí mỗi request | Frame time/FPS hoặc thời gian render mỗi cảnh |
| Thời gian chạy | Job dài, có thể nhiều giờ hoặc nhiều ngày | Dịch vụ liên tục hoặc batch theo đợt | Tương tác thời gian thực hoặc job render kéo dài |

Một ứng dụng có thể kết hợp nhiều nhóm. Ví dụ, hệ thống AI tạo ảnh cần huấn luyện mô hình trước, phục vụ suy luận khi người dùng gửi prompt, sau đó dùng pipeline đồ họa hoặc bộ mã hóa để xử lý ảnh đầu ra. Cần đo từng giai đoạn riêng để tránh chọn cấu hình theo một chỉ số tổng hợp gây nhầm lẫn.

## 3. Workload huấn luyện mô hình (training)

### Training thực hiện những bước nào?

Trong huấn luyện học máy, mô hình nhận dữ liệu đầu vào và tạo dự đoán. Hệ thống so sánh dự đoán với nhãn hoặc mục tiêu, tính loss, lan truyền gradient ngược qua mô hình và cập nhật trọng số bằng optimizer.

Một vòng lặp cơ bản gồm:

1. Đọc một batch dữ liệu.
2. Đưa dữ liệu qua mô hình để tính dự đoán (forward pass).
3. Tính loss.
4. Tính gradient (backward pass).
5. Optimizer cập nhật trọng số.
6. Lặp lại qua nhiều batch và epoch cho đến khi đạt tiêu chí dừng.

GPU phù hợp với training vì phép nhân ma trận, convolution và nhiều phép toán tensor có thể chạy song song. Tuy nhiên, training cũng cần CPU để đọc dữ liệu, giải mã, tăng cường dữ liệu, điều phối và chuẩn bị batch.

### Vì sao training thường cần nhiều VRAM?

Bộ nhớ GPU trong training có thể chứa nhiều loại dữ liệu cùng lúc:

- Trọng số của mô hình.
- Gradient tương ứng với trọng số.
- Trạng thái của optimizer, ví dụ moment của Adam.
- Activation trung gian cần giữ để tính backward pass.
- Buffer cho phép toán, workspace của thư viện và dữ liệu đầu vào.
- Bộ nhớ dành cho communication hoặc phân mảnh allocator.

Do đó, kích thước file mô hình không thể dùng trực tiếp làm ước lượng VRAM huấn luyện.

Ví dụ, với mô hình có P tham số, nếu lưu trọng số FP32 thì riêng trọng số cần khoảng 4P byte. Nếu giữ thêm gradient FP32 và hai trạng thái moment FP32 của Adam, phần tham số và optimizer có thể xấp xỉ 16P byte, chưa gồm activation, buffer và dữ liệu. Cách tính thực tế thay đổi theo mixed precision, optimizer, sharding và framework. Đây là phép ước lượng sơ bộ để hiểu vì sao training thường tiêu thụ nhiều VRAM.

### Precision và mixed precision

Training có thể dùng nhiều định dạng số:

- FP32: độ chính xác đơn, thường tốn nhiều bộ nhớ và băng thông hơn.
- FP16: định dạng 16 bit, giảm dung lượng và có thể tăng tốc trên GPU hỗ trợ.
- BF16: định dạng 16 bit có dải số mũ rộng hơn FP16, thường hữu ích trong huấn luyện deep learning.
- FP8 hoặc định dạng thấp hơn: được một số GPU và framework hỗ trợ cho các phép toán nhất định, cần kiểm chứng chất lượng mô hình.

Mixed precision kết hợp nhiều định dạng để tăng tốc và giảm bộ nhớ, đồng thời giữ một số phép tính nhạy với độ chính xác ở định dạng phù hợp. Không nên chuyển precision chỉ để giảm VRAM mà không kiểm tra loss, độ hội tụ và chất lượng mô hình.

### Data parallelism và multi-GPU training

Khi một GPU không đủ bộ nhớ hoặc thời gian huấn luyện quá dài, có thể dùng nhiều GPU:

- Data parallelism: mỗi GPU giữ một bản sao mô hình và xử lý một phần batch. Gradient được đồng bộ giữa các GPU.
- Tensor parallelism: chia phép toán hoặc tensor của mô hình qua nhiều GPU.
- Pipeline parallelism: chia các tầng mô hình thành các stage, mỗi GPU xử lý một phần.
- Sharding: phân chia trọng số, gradient hoặc optimizer state để giảm bộ nhớ cần giữ trên mỗi GPU.

Data parallelism có thể tăng throughput khi batch đủ lớn, nhưng cần trao đổi gradient. Tensor và pipeline parallelism có thể giúp chạy mô hình lớn hơn, nhưng làm tăng yêu cầu giao tiếp và độ phức tạp điều phối.

Khi dùng nhiều GPU trên cùng máy, cần xem xét băng thông giữa GPU, topology PCIe, NVLink hoặc liên kết tương đương. Khi phân tán qua nhiều máy, mạng tốc độ cao và RDMA có thể trở thành yếu tố quyết định. GPU mạnh nhưng kết nối chậm có thể dành nhiều thời gian chờ đồng bộ.

### Đặc điểm hạ tầng phù hợp cho training

Training thường cần:

- GPU có hiệu năng tensor cao và VRAM đủ lớn.
- Nhiều GPU khi mô hình hoặc thời gian huấn luyện yêu cầu.
- Liên kết GPU tốc độ cao cho giao tiếp nội bộ.
- CPU đủ mạnh để nạp và tiền xử lý dữ liệu.
- RAM hệ thống đủ cho cache dataset, worker và buffer.
- Lưu trữ thông lượng cao cho checkpoint và dữ liệu huấn luyện.
- Mạng tốc độ cao nếu dữ liệu hoặc GPU nằm trên nhiều máy.

Với job huấn luyện kéo dài, cần có cơ chế checkpoint định kỳ để tiếp tục sau lỗi hoặc gián đoạn. Tần suất checkpoint phải cân bằng giữa thời gian ghi, dung lượng lưu trữ và lượng công việc có thể mất khi job bị dừng.

### Ví dụ vòng lặp training bằng PyTorch

Đoạn mã sau minh họa cấu trúc training đơn giản. Phần khởi tạo model, dataloader và optimizer phụ thuộc bài toán cụ thể.

~~~python
import torch

model.train()

for inputs, targets in train_loader:
    inputs = inputs.to("cuda", non_blocking=True)
    targets = targets.to("cuda", non_blocking=True)

    optimizer.zero_grad(set_to_none=True)

    with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        predictions = model(inputs)
        loss = loss_fn(predictions, targets)

    loss.backward()
    optimizer.step()
~~~

Mixed precision BF16 chỉ nên dùng khi GPU, framework và mô hình hỗ trợ. Một số mô hình hoặc phép toán cần cấu hình precision khác; hãy theo dõi loss và chất lượng trên tập validation.

## 4. Workload suy luận mô hình (inference)

### Inference khác training ở đâu?

Inference sử dụng trọng số đã huấn luyện để xử lý dữ liệu mới. Thông thường, mô hình chạy forward pass và trả kết quả mà không tính backward pass hoặc cập nhật optimizer.

Inference có thể diễn ra theo hai dạng:

- Online inference: nhận request và trả kết quả trong thời gian ngắn, thường chịu yêu cầu độ trễ p95/p99.
- Batch inference: xử lý một tập dữ liệu lớn theo lô, thường ưu tiên thông lượng và chi phí trên mỗi bản ghi.

Một dịch vụ có thể vừa phục vụ request trực tuyến vừa chạy batch. Hai loại tải này nên được lập lịch và giới hạn tài nguyên phù hợp để job batch không làm ảnh hưởng SLO của request trực tuyến.

### VRAM của inference gồm những gì?

Inference thường không cần gradient và optimizer state, nên bộ nhớ có thể thấp hơn training. Tuy nhiên, VRAM vẫn phải chứa:

- Trọng số mô hình.
- Activation và workspace trong quá trình forward.
- Bộ nhớ cache theo request.
- Input/output buffer và dữ liệu trung gian.
- KV cache đối với mô hình sinh tự hồi quy như nhiều mô hình ngôn ngữ lớn.
- Runtime, graph capture hoặc bộ nhớ dự phòng của framework.

Với mô hình ngôn ngữ lớn, KV cache có thể chiếm nhiều VRAM khi số phiên đồng thời và độ dài ngữ cảnh tăng. Một công thức khái quát để ước lượng phần KV cache là:

\[
M_{KV} \approx 2 \times L \times B \times T \times H_{KV} \times D_{head} \times S
\]

Trong đó:

- L: số tầng transformer.
- B: số chuỗi đang hoạt động hoặc batch tương ứng.
- T: số token được giữ trong cache.
- H_KV: số đầu attention dùng cho key/value.
- D_head: chiều rộng mỗi head.
- S: số byte cho mỗi phần tử cache.
- Hệ số 2 biểu diễn cả key và value.

Đây là mô hình ước lượng đơn giản. Cách phân mảnh, tensor parallelism, cache sharing, sliding window, quantization và implementation có thể làm dung lượng thực tế khác đi.

### Tối ưu độ trễ và thông lượng

Inference cần cân bằng nhiều mục tiêu:

- Latency: thời gian từ lúc nhận request đến lúc trả kết quả.
- Throughput: số request, ảnh hoặc token xử lý trong một đơn vị thời gian.
- Concurrency: số request được xử lý đồng thời.
- Cost per request: chi phí để hoàn thành một request hoặc một đơn vị đầu ra.
- Quality: độ chính xác hoặc chất lượng kết quả.

Batching có thể tăng hiệu quả sử dụng GPU vì gom nhiều request vào một lần thực thi. Tuy nhiên, chờ đủ batch có thể làm tăng độ trễ. Với dịch vụ tương tác, cần giới hạn thời gian chờ batch và kích thước batch. Với batch inference ngoại tuyến, có thể ưu tiên batch lớn hơn để tối đa throughput.

Một số kỹ thuật khác:

- Quantization: giảm độ rộng số của trọng số hoặc activation để tiết kiệm VRAM và tăng tốc nếu phần cứng hỗ trợ.
- Model distillation: dùng mô hình nhỏ hơn được huấn luyện để bắt chước mô hình lớn.
- Pruning hoặc kiến trúc hiệu quả: giảm phép tính và dung lượng mô hình.
- KV cache optimization: giảm dung lượng hoặc tăng khả năng tái sử dụng cache.
- Dynamic batching: gom request theo thời gian thực trong giới hạn latency.
- Model parallelism: chia mô hình lớn qua nhiều GPU khi không vừa một thiết bị.

Mỗi kỹ thuật có trade-off về chất lượng, độ trễ, độ phức tạp và khả năng tương thích. Cần benchmark với dữ liệu và phân bố request thực tế.

### Đặc điểm hạ tầng phù hợp cho inference

Inference online thường ưu tiên:

- VRAM đủ chứa mô hình và trạng thái request ở concurrency mục tiêu.
- GPU có hiệu năng tốt cho precision được sử dụng.
- CPU đủ để xử lý networking, tokenization, tiền/hậu xử lý và điều phối.
- Mạng có độ trễ thấp giữa load balancer, ứng dụng và GPU service.
- Autoscaling theo hàng đợi, request rate hoặc mức sử dụng thiết bị.
- Khả năng warm-up và nạp model nhanh khi tạo instance mới.

Inference batch có thể ưu tiên GPU giá phù hợp, throughput cao, khả năng chạy theo lịch và lưu trữ dữ liệu đầu vào/đầu ra hiệu quả.

### Ví dụ cấu trúc inference bằng PyTorch

~~~python
model.eval()

with torch.inference_mode():
    with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        predictions = model(inputs.to("cuda"))
~~~

Inference mode tắt các cơ chế theo dõi gradient không cần thiết. Cần xác nhận dtype được model và GPU hỗ trợ. Với dịch vụ production, còn phải bổ sung batching, giới hạn concurrency, timeout, xử lý lỗi và giám sát.

## 5. Workload xử lý đồ họa (graphics)

### Graphics bao gồm những công việc nào?

Graphics là nhóm workload tạo hoặc biến đổi hình ảnh. Một số dạng phổ biến:

- Real-time rendering: dựng hình theo từng frame để hiển thị tương tác trong game, mô phỏng hoặc ứng dụng 3D.
- Offline rendering: dựng hình chất lượng cao cho phim, hoạt hình, kiến trúc hoặc nội dung quảng cáo; có thể mất nhiều phút hoặc giờ cho một cảnh.
- CAD và visualization: hiển thị mô hình kỹ thuật, dữ liệu khoa học hoặc mô hình 3D phức tạp.
- Video processing: mã hóa, giải mã, chuyển đổi và hậu kỳ video; có thể sử dụng GPU hoặc khối video chuyên dụng.
- Remote graphics: dựng hình trên máy chủ rồi truyền hình ảnh đến thiết bị người dùng.

### GPU thực hiện pipeline đồ họa

Một pipeline đồ họa điển hình có thể gồm:

1. CPU chuẩn bị scene, camera, vật liệu và lệnh vẽ.
2. GPU xử lý vertex và geometry.
3. Rasterizer chuyển hình học thành fragment/pixel.
4. Shader tính màu, ánh sáng, texture và hiệu ứng.
5. Depth test, blending và các bước hậu xử lý.
6. Frame buffer lưu kết quả để hiển thị hoặc mã hóa.

Ray tracing mô phỏng đường đi của tia sáng để tạo phản xạ, khúc xạ và bóng chân thực hơn. Kỹ thuật này có thể dùng các đơn vị tăng tốc chuyên dụng trên GPU hỗ trợ. Chi phí tính toán tăng theo độ phân giải, số tia, số lần phản xạ và chất lượng khử nhiễu.

### Đặc điểm tài nguyên của graphics

Graphics thường cần:

- GPU có năng lực rasterization, shader hoặc ray tracing phù hợp.
- VRAM cho texture, geometry, frame buffer, render target và asset.
- CPU đủ để chuẩn bị scene, mô phỏng, physics và draw call.
- RAM hệ thống cho asset, scene và phần mềm.
- Lưu trữ đủ nhanh để nạp texture, model và video.
- Màn hình, encoder hoặc đường truyền phù hợp nếu dùng remote graphics.

VRAM có thể tăng nhanh theo độ phân giải và số lượng texture. Một cảnh 3D phức tạp có thể hết VRAM dù GPU compute utilization chưa đạt mức tối đa. Khi VRAM thiếu, driver hoặc ứng dụng có thể chuyển dữ liệu qua RAM hệ thống, làm tăng độ trễ và giảm tốc độ khung hình.

### Chỉ số đánh giá graphics

Với real-time graphics:

- FPS (frames per second) cho biết số khung hình mỗi giây.
- Frame time là thời gian tạo một frame; nên xem phân vị và độ ổn định.
- p95/p99 frame time hoặc 1% low giúp phát hiện giật hình.
- VRAM usage, GPU utilization và nhiệt/điện năng nếu có.
- Độ phân giải, chất lượng shader, ray tracing và mức khử răng cưa.

FPS trung bình cao nhưng frame time dao động mạnh vẫn có thể tạo trải nghiệm kém. Độ ổn định của frame time thường quan trọng hơn một con số FPS trung bình duy nhất.

Với offline rendering, nên đo thời gian render mỗi frame hoặc mỗi cảnh, chất lượng đầu ra và chi phí trên mỗi frame. GPU có throughput cao có thể phù hợp hơn GPU tối ưu độ trễ thấp.

### Đồ họa và AI có thể dùng cùng GPU nhưng khác ưu tiên

Một GPU hỗ trợ tensor core có thể vừa chạy AI vừa xử lý đồ họa, nhưng không phải mọi ứng dụng đồ họa đều tận dụng các đơn vị tensor. Game thời gian thực có thể phụ thuộc mạnh vào shader, rasterization, ray tracing và VRAM. Huấn luyện AI phụ thuộc vào phép toán tensor, bộ nhớ và giao tiếp GPU.

Nếu cùng một GPU được chia sẻ giữa inference và rendering, cần kiểm tra mức độ cạnh tranh tài nguyên, khả năng cô lập và ảnh hưởng đến latency hoặc frame time. Với workload tương tác có SLO chặt, dùng GPU chuyên dụng hoặc phân vùng thiết bị được hỗ trợ có thể giúp kết quả ổn định hơn.

## 6. So sánh cách chọn GPU cho từng workload

| Thành phần | Training | Inference | Graphics |
|---|---|---|---|
| Năng lực GPU | Tensor/compute throughput cao | Hiệu năng theo precision và batch | Rasterization, shader, ray tracing hoặc video engine |
| VRAM | Trọng số, gradient, optimizer, activation | Trọng số, activation, KV cache, workspace | Texture, geometry, frame buffer, render target |
| Băng thông bộ nhớ GPU | Quan trọng với mô hình và batch lớn | Quan trọng khi nạp trọng số, xử lý tensor và KV cache | Quan trọng với texture và buffer lớn |
| Kết nối GPU | Rất quan trọng khi multi-GPU | Cần thiết nếu mô hình được chia qua nhiều GPU | Quan trọng khi nhiều GPU render hoặc truyền asset |
| CPU và RAM host | Data loader, augmentation, checkpoint | Tokenization, networking, batching, preprocessing | Scene setup, physics, asset loading, draw calls |
| Mạng | Đồng bộ gradient và đọc dataset phân tán | Request/response và phân phối model | Remote desktop, asset và stream hình ảnh |
| Chỉ số chính | Step time, samples/tokens per second, convergence | p50/p95/p99 latency, throughput, cost/request | FPS, frame time, render time/frame |
| Kiểu triển khai | Job dài, cluster multi-GPU | Service liên tục hoặc batch | Workstation ảo, render farm hoặc ứng dụng tương tác |

### Chọn GPU theo thứ tự

1. Xác định workload và framework.
2. Tính dung lượng VRAM cần thiết ở đỉnh tải.
3. Xác định precision và loại phép toán được sử dụng.
4. Đánh giá hiệu năng đơn GPU trước khi thêm GPU.
5. Nếu cần multi-GPU, kiểm tra topology và interconnect.
6. Kiểm tra CPU, RAM, lưu trữ và mạng để tránh nghẽn dữ liệu.
7. Xác minh driver, runtime, quota và khả năng cung cấp GPU ở vùng cần dùng.
8. Benchmark bằng workload đại diện và tính chi phí trên đơn vị công việc.

Không nên chọn chỉ theo tên GPU hoặc số lượng GPU. Hai thiết bị có cùng dung lượng VRAM vẫn có thể khác đáng kể về băng thông bộ nhớ, tensor throughput, ray tracing, encoder và interconnect.

## 7. Ví dụ lựa chọn hạ tầng cho ba tình huống

### Tình huống A: huấn luyện mô hình phân loại ảnh

Một nhóm cần huấn luyện mô hình phân loại ảnh trên tập dữ liệu lớn. Job chạy nhiều giờ và có thể chia batch qua nhiều GPU.

Nhóm cần kiểm tra:

- Kích thước mô hình và VRAM cần cho trọng số, gradient, optimizer state và activation.
- Khả năng dùng mixed precision mà không giảm chất lượng quá mức.
- CPU và RAM cho giải mã ảnh, augmentation và data loader.
- Throughput của lưu trữ chứa dataset.
- Tốc độ checkpoint và khả năng khôi phục job.
- Interconnect nếu dùng nhiều GPU.

Nếu GPU utilization thấp nhưng CPU hoặc data loader thường xuyên bận, cần tối ưu pipeline dữ liệu trước khi tăng số GPU. Nếu GPU hết VRAM, có thể giảm batch, dùng gradient accumulation, activation checkpointing hoặc phân tán mô hình; cần đo tác động đến thời gian huấn luyện.

### Tình huống B: phục vụ mô hình ngôn ngữ cho API

Một dịch vụ nhận prompt và sinh văn bản cho người dùng. Nhóm phải đáp ứng giới hạn độ trễ, đồng thời xử lý nhiều request.

Nhóm cần ước lượng:

- Dung lượng trọng số theo precision triển khai.
- VRAM cho KV cache theo số phiên và độ dài context.
- Workspace và activation khi batch thay đổi.
- Throughput token đầu vào và đầu ra.
- Thời gian nạp model và warm-up.
- Độ trễ p95/p99 ở concurrency cao điểm.
- Chi phí trên mỗi nghìn token hoặc mỗi request.

Nếu trọng số vừa một GPU nhưng KV cache làm VRAM đầy khi tăng concurrency, có thể cần GPU nhiều VRAM hơn, tối ưu cache, giảm context, quantization hoặc chia model. Chỉ tăng batch mà không theo dõi latency có thể làm dịch vụ phản hồi chậm hơn.

### Tình huống C: dựng hình 3D cho ứng dụng tương tác

Một nhóm cung cấp môi trường làm việc 3D từ xa. Người dùng tương tác với scene phức tạp ở độ phân giải cao.

Nhóm cần kiểm tra:

- VRAM cho texture, geometry và render target.
- Hiệu năng shader/rasterization hoặc ray tracing.
- Frame time ở cảnh phức tạp, không chỉ FPS trung bình.
- CPU cho scene update và draw call.
- Độ trễ mạng và chất lượng truyền hình ảnh.
- Encoder video nếu stream frame đến người dùng.
- Khả năng cô lập phiên khi nhiều người dùng chung hạ tầng.

GPU compute mạnh không tự động bảo đảm frame time tốt. Cần thử scene thật, độ phân giải thật và đường truyền thực tế.

## 8. Phần mềm và môi trường triển khai GPU

GPU cần một chuỗi phần mềm tương thích. Các thành phần thường gồm:

- Driver thiết bị.
- Runtime và thư viện tính toán như CUDA hoặc ROCm tùy phần cứng.
- Framework như PyTorch, TensorFlow hoặc framework chuyên dụng.
- Thư viện giao tiếp multi-GPU như NCCL hoặc thành phần tương đương.
- Runtime suy luận và tối ưu model như TensorRT, ONNX Runtime hoặc engine phục vụ mô hình.
- Công cụ đồ họa như DirectX, Vulkan, OpenGL hoặc engine dựng hình.
- Container image có phiên bản driver/runtime/framework tương thích.

Không phải mọi phiên bản framework đều hỗ trợ mọi kiến trúc GPU. Trước khi triển khai, kiểm tra ma trận tương thích và thử chạy một workload nhỏ trên đúng image production.

### GPU trong máy ảo

Với VM gắn GPU, cần kiểm tra loại GPU, số thiết bị, VRAM, chế độ passthrough hoặc virtual GPU, driver guest, quota và vùng triển khai. Một số nhà cung cấp yêu cầu chọn đúng loại VM hoặc image đã cấu hình driver.

### GPU trong Kubernetes

Trong Kubernetes, GPU thường được đưa vào node thông qua device plugin hoặc cơ chế tương đương. Pod khai báo tài nguyên GPU cần thiết; scheduler đặt pod lên node có thiết bị phù hợp.

Cần lưu ý:

- Node pool GPU có thể tách riêng theo loại thiết bị.
- GPU thường được cấp như tài nguyên mở rộng và có cách khai báo riêng.
- Một số nền tảng hỗ trợ MIG hoặc cơ chế phân vùng GPU; mức hỗ trợ tùy thiết bị và phiên bản.
- Chia sẻ GPU theo time-slicing hoặc vGPU có thể tăng mật độ, nhưng hiệu năng và cô lập thay đổi theo cơ chế.
- Autoscaler phải hiểu quota, thời gian cấp node và giới hạn vùng.

Không nên giả định một pod yêu cầu một GPU sẽ luôn được đặt trên GPU có VRAM hoặc kiến trúc phù hợp. Cần dùng node label, taint/toleration và cấu hình tài nguyên đúng với môi trường.

### Bảo vệ dữ liệu và môi trường tăng tốc

Dữ liệu huấn luyện, prompt, model và asset đồ họa có thể chứa thông tin nhạy cảm hoặc tài sản sở hữu trí tuệ. Hãy dùng quyền truy cập tối thiểu cho dataset và model registry, mã hóa dữ liệu lưu trữ/truyền tải, giới hạn quyền truy cập node GPU và kiểm tra nguồn gốc container image. Khi dùng thiết bị chia sẻ, cần hiểu cơ chế cô lập của nền tảng và tránh lưu dữ liệu nhạy cảm trong vùng bộ nhớ hoặc ổ đĩa tạm ngoài chính sách cho phép.

## 9. Đo lường và giám sát

### Chỉ số dùng chung

- GPU utilization và mức sử dụng từng thiết bị.
- VRAM đã dùng, còn trống và mức tăng theo thời gian.
- GPU memory bandwidth nếu công cụ cung cấp.
- Nhiệt độ, công suất và trạng thái throttling nếu được phép quan sát.
- CPU utilization, RAM host và thời gian chờ I/O.
- PCIe hoặc interconnect utilization nếu có.
- Thông lượng lưu trữ và mạng.

GPU utilization cao không nhất thiết đồng nghĩa hệ thống hiệu quả. Một workload có thể dùng GPU liên tục nhưng tạo ra ít kết quả hữu ích do batch nhỏ, đồng bộ nhiều hoặc dữ liệu đầu vào chậm. Hãy đo cả kết quả công việc.

### Metric riêng theo workload

| Workload | Metric nên theo dõi | Câu hỏi vận hành |
|---|---|---|
| Training | Step time, samples/sec hoặc tokens/sec, loss, GPU utilization, VRAM, checkpoint duration | Job có tiến triển và hội tụ đúng dự kiến không? |
| Inference | Request/sec, tokens/sec, time to first token, inter-token latency, p95/p99, queue depth, VRAM/KV cache | Dịch vụ có đáp ứng SLO khi tăng concurrency không? |
| Real-time graphics | FPS, frame time, 1% low, VRAM, dropped frame, encode latency | Người dùng có trải nghiệm mượt và ổn định không? |
| Offline rendering | Render time/frame, số frame/giờ, VRAM peak, lỗi render | Chi phí cho mỗi frame và thời gian hoàn thành có đạt mục tiêu không? |

Với NVIDIA GPU, công cụ như nvidia-smi có thể giúp xem thiết bị và mức sử dụng. Với AMD GPU, công cụ tương ứng có thể là rocm-smi hoặc công cụ do nền tảng cung cấp. Tên và metric khả dụng tùy driver, thiết bị và môi trường ảo hóa.

Ví dụ lệnh kiểm tra trên hệ thống NVIDIA:

~~~sh
nvidia-smi
nvidia-smi dmon
~~~

Các lệnh này chỉ áp dụng khi driver NVIDIA và tiện ích tương ứng được cài đặt. Trong môi trường cloud, cần kết hợp metric trong máy với metric cấp nền tảng và metric của ứng dụng.

## 10. Tối ưu chi phí và khả năng mở rộng

### Chi phí không chỉ là giá GPU mỗi giờ

Tổng chi phí có thể gồm:

- GPU hoặc accelerator và VM đi kèm.
- CPU, RAM, ổ đĩa và snapshot.
- Lưu trữ dataset, model, checkpoint và asset.
- Lưu lượng mạng giữa các node hoặc ra Internet.
- License phần mềm và dịch vụ quản lý.
- Thời gian GPU nhàn rỗi khi chờ dữ liệu hoặc chờ request.
- Chi phí dự phòng để duy trì tính sẵn sàng.

Đo chi phí theo kết quả hữu ích:

- Training: chi phí cho một lần huấn luyện hoàn thành hoặc một đơn vị chất lượng mô hình.
- Inference: chi phí trên mỗi request, nghìn token hoặc bản ghi dự đoán.
- Graphics: chi phí trên mỗi frame, cảnh render hoặc phiên người dùng.

Một GPU đắt hơn có thể rẻ hơn trên mỗi đơn vị công việc nếu hoàn thành nhanh hơn. Ngược lại, GPU mạnh nhưng chỉ sử dụng một phần nhỏ thời gian có thể làm chi phí tăng.

### Scale up và scale out

Scale up là chuyển sang GPU có năng lực hoặc VRAM lớn hơn. Cách này phù hợp khi mô hình hoặc scene không vừa thiết bị hiện tại, hoặc workload cần một GPU mạnh hơn.

Scale out là tăng số GPU hoặc số node. Cách này phù hợp khi công việc có thể chia nhỏ, request độc lập hoặc batch có thể phân phối. Hiệu quả scale out phụ thuộc khả năng song song và chi phí giao tiếp. Thêm GPU không bảo đảm throughput tăng tuyến tính.

### Chọn mô hình cấp phát phù hợp

- On-demand: linh hoạt cho workload không ổn định hoặc thử nghiệm.
- Capacity reservation hoặc cam kết sử dụng: có thể phù hợp với workload chạy đều và cần chắc chắn về dung lượng.
- Spot/preemptible: phù hợp với job có thể checkpoint và tiếp tục khi bị thu hồi; cần đánh giá rủi ro gián đoạn.
- Autoscaling: phù hợp với inference hoặc job queue có tải thay đổi, nhưng phải tính thời gian cấp GPU và warm-up model.

Training kéo dài cần checkpoint và xử lý retry. Inference cần scale theo request, queue và latency. Graphics tương tác cần duy trì phiên và frame time, nên autoscaling phải tính thời gian khởi tạo session và nạp scene.

## 11. Quy trình quyết định loại GPU và cấu hình

~~~mermaid
flowchart TD
    A["Xác định mục tiêu workload"] --> B{"Công việc chính là gì?"}
    B -- "Training" --> C["Ước lượng VRAM cho weights, gradients, optimizer, activations"]
    B -- "Inference" --> D["Ước lượng VRAM cho weights, KV cache, concurrency"]
    B -- "Graphics" --> E["Ước lượng VRAM cho scene, texture, frame buffer"]
    C --> F["Chọn GPU, precision và số thiết bị"]
    D --> F
    E --> F
    F --> G["Kiểm tra CPU, RAM, storage, interconnect và network"]
    G --> H["Kiểm tra driver, runtime, framework và quota"]
    H --> I["Benchmark trên workload đại diện"]
    I --> J{"Đạt chất lượng, SLO và cost target?"}
    J -- "Chưa" --> K["Điều chỉnh model, batch, scene hoặc cấu hình"]
    K --> I
    J -- "Đạt" --> L["Triển khai, giám sát và tối ưu định kỳ"]
~~~

Trình tự áp dụng:

1. Mô tả mục tiêu và kiểu tải: training, inference, real-time graphics hay offline rendering.
2. Xác định chỉ số thành công: thời gian huấn luyện, latency, throughput, FPS hoặc render time.
3. Ước lượng VRAM ở mức đỉnh, gồm dữ liệu trung gian và concurrency.
4. Chọn kiến trúc GPU và precision tương thích với phần mềm.
5. Kiểm tra CPU, RAM host, lưu trữ, mạng và interconnect.
6. Xác minh quota, vùng, dung lượng cung cấp và giấy phép.
7. Benchmark bằng dữ liệu, model hoặc scene đại diện.
8. Tính chi phí trên đơn vị công việc và kiểm tra kịch bản lỗi.
9. Triển khai có giám sát, checkpoint hoặc autoscaling phù hợp.
10. Rightsize sau khi có dữ liệu vận hành.

## 12. Những sai lầm thường gặp

1. **Dùng cùng một tiêu chí cho cả ba workload.** Training tối ưu thời gian hoàn thành, inference tối ưu latency/throughput, graphics tối ưu frame time hoặc render time.
2. **Chọn GPU chỉ theo số lượng thiết bị.** VRAM, tensor throughput, memory bandwidth và interconnect mới quyết định nhiều giới hạn thực tế.
3. **Ước lượng VRAM training bằng kích thước file model.** Gradient, optimizer state và activation có thể chiếm phần lớn bộ nhớ.
4. **Bỏ qua KV cache trong inference.** Concurrency và context dài có thể làm VRAM tăng nhanh.
5. **Chỉ xem FPS trung bình.** Frame time dao động và 1% low có thể cho thấy trải nghiệm giật hình.
6. **Dùng mixed precision hoặc quantization mà không kiểm tra chất lượng.** Giảm độ chính xác có thể ảnh hưởng loss, độ hội tụ hoặc đầu ra.
7. **Thêm GPU nhưng không kiểm tra interconnect.** Giao tiếp chậm có thể làm mất lợi ích song song.
8. **Để CPU hoặc storage không theo kịp GPU.** GPU sẽ nhàn rỗi khi thiếu dữ liệu hoặc checkpoint chậm.
9. **Không kiểm tra tương thích driver và framework.** Thiết bị có thể không được nhận diện hoặc một số toán tử không chạy.
10. **Chia sẻ GPU mà không đo mức cạnh tranh.** Một workload có thể làm latency hoặc frame time của workload khác tăng.
11. **Bỏ qua thời gian warm-up.** Inference hoặc graphics có thể mất nhiều thời gian nạp model, shader và asset.
12. **Không tính chi phí dữ liệu và mạng.** Training phân tán và render farm có thể phát sinh lưu lượng lớn.

## 13. Checklist trước khi triển khai

- [ ] Đã phân loại rõ workload là training, inference, real-time graphics hay offline rendering.
- [ ] Đã xác định chỉ số thành công và SLO.
- [ ] Đã ước lượng VRAM peak, gồm trạng thái trung gian và concurrency.
- [ ] Đã chọn precision và framework tương thích.
- [ ] Đã kiểm tra GPU memory bandwidth và hiệu năng phép toán cần dùng.
- [ ] Đã đánh giá interconnect khi dùng nhiều GPU hoặc nhiều node.
- [ ] Đã kiểm tra CPU, RAM host, lưu trữ và mạng.
- [ ] Đã xác minh driver, runtime, thư viện và container image.
- [ ] Đã kiểm tra quota, vùng triển khai và khả năng cấp GPU.
- [ ] Đã benchmark trên model, dữ liệu hoặc scene đại diện.
- [ ] Đã đo throughput, latency hoặc frame time phù hợp workload.
- [ ] Đã có checkpoint, retry, warm-up hoặc autoscaling phù hợp.
- [ ] Đã tính chi phí trên đơn vị công việc hữu ích.
- [ ] Đã thiết lập giám sát GPU, VRAM và metric ứng dụng.

## Kết luận

Training cần tài nguyên để tính gradient, giữ optimizer state và activation; inference cần VRAM cho trọng số, trạng thái request và cache trong khi cân bằng latency với throughput; graphics cần năng lực dựng hình và VRAM cho scene, texture, buffer cùng yêu cầu frame time ổn định. Hãy phân loại workload trước, xác định chỉ số thành công, ước lượng tài nguyên ở mức đỉnh và benchmark trên môi trường đại diện. Việc chọn GPU đúng kiến trúc, kết hợp CPU, RAM, lưu trữ, mạng và phần mềm tương thích giúp hệ thống đạt mục tiêu hiệu năng với chi phí có thể kiểm soát.
