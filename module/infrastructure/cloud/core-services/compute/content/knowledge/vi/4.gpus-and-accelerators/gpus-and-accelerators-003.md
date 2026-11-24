# VRAM, băng thông bộ nhớ và giới hạn kích thước mô hình

## Bối cảnh: GPU có đủ mạnh nhưng vẫn không chạy được mô hình

Khi triển khai mô hình học máy hoặc mô hình ngôn ngữ lớn (LLM), hai thông số của GPU thường quyết định trải nghiệm thực tế là **dung lượng bộ nhớ GPU (VRAM)** và **băng thông bộ nhớ**. Số nhân tính toán, năng lực Tensor Core và thông lượng phép tính rất quan trọng, nhưng chúng không thể bù cho việc mô hình không vừa bộ nhớ hoặc dữ liệu không được chuyển đến bộ xử lý đủ nhanh.

VRAM là nơi GPU lưu các trọng số mô hình, tensor trung gian, dữ liệu đầu vào, bộ đệm và trạng thái phục vụ tính toán. Băng thông bộ nhớ cho biết tốc độ dữ liệu có thể được đọc hoặc ghi giữa GPU và VRAM. Hai GPU cùng có số phép tính lý thuyết tương đương vẫn có thể khác nhau đáng kể nếu một GPU có ít VRAM hơn hoặc băng thông thấp hơn.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, hiểu các giới hạn này giúp chọn GPU và bộ tăng tốc phù hợp, ước lượng kích thước mô hình có thể chạy, quyết định precision hoặc quantization, bố trí nhiều GPU và tối ưu hiệu năng cũng như chi phí trên cloud.

## 1. VRAM là gì và được dùng vào những việc nào?

VRAM (Video Random Access Memory) là bộ nhớ cục bộ có băng thông cao gắn với GPU. Với GPU máy chủ, VRAM thường là bộ nhớ chuyên dụng như GDDR hoặc HBM. GPU dùng vùng nhớ này để giữ dữ liệu cần truy cập nhanh trong quá trình thực thi kernel.

Một workload AI có thể sử dụng VRAM cho nhiều thành phần:

- **Model weights (trọng số):** các tham số đã học của mô hình, thường là phần chiếm nhiều bộ nhớ nhất khi suy luận mô hình lớn.
- **Activations (tensor kích hoạt):** kết quả trung gian của các lớp trong quá trình forward; khi huấn luyện, nhiều activation cần được giữ lại để tính gradient.
- **Gradients (gradient):** đạo hàm dùng để cập nhật trọng số trong quá trình huấn luyện.
- **Optimizer states (trạng thái bộ tối ưu):** ví dụ các moment của Adam, thường chiếm thêm nhiều bộ nhớ cho mỗi tham số.
- **KV cache:** bộ nhớ lưu key và value của các token trước đó để tránh tính lại toàn bộ phần attention trong mỗi bước sinh token của LLM.
- **Input, output và batch:** token, ảnh, embedding, tensor đầu ra và dữ liệu của nhiều mẫu xử lý đồng thời.
- **Workspace và bộ nhớ runtime:** vùng tạm cho kernel, thư viện tăng tốc, CUDA context, graph, allocator và các cấu trúc phục vụ thực thi.

Do đó, không thể lấy dung lượng VRAM bằng đúng kích thước file checkpoint rồi kết luận mô hình chắc chắn chạy được. Checkpoint thường chỉ phản ánh một phần trọng số; lúc nạp và thực thi còn có các khoản bộ nhớ khác.

### 1.1. VRAM khác RAM hệ thống

RAM hệ thống được CPU truy cập trực tiếp; VRAM được GPU truy cập với đường truyền riêng. GPU thường có băng thông VRAM cao hơn đáng kể so với băng thông RAM thông thường, nhưng dung lượng VRAM thường nhỏ hơn tổng RAM của máy chủ.

Khi VRAM không đủ, một số framework hoặc kiến trúc có thể chuyển một phần dữ liệu sang RAM hệ thống, hoặc phân phối dữ liệu sang GPU khác. Các phương án này giúp chạy workload lớn hơn, nhưng thường làm tăng độ trễ và lưu lượng truyền qua PCIe, NVLink hoặc fabric liên kết. Không nên xem RAM hệ thống như phần VRAM có tốc độ tương đương.

### 1.2. GB và GiB

Thông số bộ nhớ có thể được ghi theo hệ thập phân hoặc nhị phân:

| Đơn vị | Cách tính | Giá trị gần đúng |
|---|---|---:|
| 1 GB | `10^9` byte | 0,931 GiB |
| 1 GiB | `2^30` byte | 1,074 GB |
| 1 TB/s | `10^12` byte mỗi giây | 0,91 TiB/s |

Nhà sản xuất có thể công bố VRAM theo GB, trong khi công cụ hoặc framework hiển thị GiB. Vì vậy, con số 24 GB trên bảng thông số có thể xuất hiện xấp xỉ 22,4 GiB trong phần mềm. Hệ thống cũng cần dành một phần bộ nhớ cho driver và runtime, nên dung lượng ứng dụng sử dụng được có thể thấp hơn con số danh nghĩa.

## 2. Ước lượng bộ nhớ dành cho trọng số mô hình

Kích thước trọng số phụ thuộc vào số tham số và số bit dùng để lưu mỗi tham số. Nếu mô hình có `P` tham số và mỗi tham số dùng `b` bit, bộ nhớ lý thuyết cho weights là:

\[
M_{weights} = \frac{P \times b}{8}\quad\text{(byte)}
\]

Ví dụ, một mô hình có 7 tỷ tham số (7B) dùng FP16 hoặc BF16, mỗi tham số thường chiếm 2 byte:

\[
7\times10^9 \times 2 = 14\times10^9\text{ byte} \approx 13.04\text{ GiB}
\]

Đây là ước lượng cho trọng số thuần. Một GPU 16 GiB có thể không đủ cho suy luận mô hình này ở batch hoặc context đáng kể, vì còn KV cache, activation, workspace và phần bộ nhớ runtime.

### 2.1. Precision và quantization

Precision mô tả cách biểu diễn số trong tính toán hoặc lưu trữ. Một số định dạng thường gặp:

| Định dạng | Độ rộng thường dùng | Bộ nhớ trọng số lý thuyết trên mỗi tham số | Ghi chú |
|---|---:|---:|---|
| FP32 | 32 bit | 4 byte | Độ chính xác cao, tốn bộ nhớ |
| FP16 | 16 bit | 2 byte | Phổ biến trong suy luận và huấn luyện mixed precision |
| BF16 | 16 bit | 2 byte | Dải số mũ rộng hơn FP16, thường hữu ích khi huấn luyện |
| INT8 | 8 bit | 1 byte | Cần scale/zero point hoặc metadata tùy phương pháp |
| INT4 | 4 bit | 0,5 byte | Giảm mạnh dung lượng, chất lượng phụ thuộc mô hình và phương pháp lượng tử hóa |

**Quantization (lượng tử hóa)** chuyển trọng số hoặc một số phép tính sang định dạng ít bit hơn. Ví dụ, trọng số FP16 của mô hình 7B có dung lượng lý thuyết khoảng 13,04 GiB; nếu lưu trọng số 4 bit, phần payload lý thuyết giảm còn khoảng 3,26 GiB.

Trong triển khai thật, dung lượng không giảm chính xác theo tỷ lệ 4/16 vì có thể có scale, zero point, nhóm lượng tử hóa, tensor chưa lượng tử hóa, padding và cấu trúc runtime. Một số kernel còn giải lượng tử hóa dữ liệu trong lúc tính toán. Vì vậy, hãy xem kích thước checkpoint và đo VRAM sau khi nạp mô hình bằng đúng framework, định dạng và kernel dự kiến dùng.

Quantization giảm bộ nhớ và đôi khi cải thiện tốc độ nhờ giảm lượng dữ liệu phải đọc. Tuy nhiên, chất lượng đầu ra có thể thay đổi; hiệu năng cũng phụ thuộc GPU có hỗ trợ phép toán tương ứng hay không. Định dạng ít bit không tự động nhanh hơn nếu runtime phải chuyển đổi dữ liệu nhiều hoặc kernel chưa được tối ưu.

### 2.2. Ví dụ ước lượng trọng số theo kích thước mô hình

Bảng sau chỉ tính trọng số thuần, chưa gồm bộ nhớ bổ sung:

| Số tham số | FP32 (4 byte) | FP16/BF16 (2 byte) | INT8 (1 byte) | INT4 (0,5 byte) |
|---:|---:|---:|---:|---:|
| 7B | ~26,1 GiB | ~13,0 GiB | ~6,5 GiB | ~3,3 GiB |
| 13B | ~48,4 GiB | ~24,2 GiB | ~12,1 GiB | ~6,1 GiB |
| 34B | ~126,7 GiB | ~63,3 GiB | ~31,7 GiB | ~15,8 GiB |
| 70B | ~260,8 GiB | ~130,4 GiB | ~65,2 GiB | ~32,6 GiB |

Các giá trị dùng đơn vị GiB và giả định mỗi tham số có đúng số byte nêu trong tiêu đề. Với INT4, phép tính 0,5 byte mỗi tham số là mức tối thiểu lý thuyết; checkpoint thực tế có thể lớn hơn.

## 3. Bộ nhớ ngoài weights: activations, KV cache và workspace

### 3.1. Activations và batch size

Activation là tensor trung gian sinh ra khi mô hình xử lý dữ liệu. Kích thước activation phụ thuộc kiến trúc, số lớp, kích thước hidden state, độ dài chuỗi, batch size, precision và cách triển khai kernel.

Batch size càng lớn thì nhiều mẫu được xử lý đồng thời, thường giúp tăng mức sử dụng GPU và chia sẻ chi phí đọc trọng số. Tuy nhiên, activation và các tensor trung gian cũng tăng theo batch size. Nếu batch quá lớn, workload có thể hết VRAM dù weights vẫn vừa bộ nhớ.

Trong huấn luyện, activation thường là một khoản đáng kể vì cần lưu thông tin cho bước backward. Activation checkpointing có thể giảm VRAM bằng cách tính lại một số activation khi cần, đổi lại tăng lượng tính toán. Với suy luận, framework có thể giải phóng nhiều tensor trung gian sau từng bước, nhưng vẫn cần workspace và bộ nhớ cho batch đang chạy.

### 3.2. KV cache trong mô hình sinh token

LLM tự hồi quy sinh từng token. Để không tính lại key và value của toàn bộ token trước đó ở mỗi bước, runtime thường lưu chúng trong KV cache. Cache tăng theo độ dài context, batch hoặc số sequence đang hoạt động, số lớp và số KV head.

Một công thức ước lượng phổ biến cho KV cache là:

\[
M_{KV}=2\times L\times H_{KV}\times D_H\times T\times B\times S
\]

Trong đó:

- `L`: số layer của mô hình.
- `H_KV`: số key/value head trên mỗi layer.
- `D_H`: kích thước mỗi head.
- `T`: số token được giữ trong cache (thường gồm prompt và phần đã sinh).
- `B`: số sequence đang được phục vụ đồng thời, theo cách runtime tổ chức batch.
- `S`: số byte cho mỗi phần tử cache, ví dụ 2 byte với FP16/BF16.
- Hệ số 2 biểu diễn cả key và value.

Ví dụ, mô hình có 32 layer, 8 KV head, head dimension 128, cache FP16, một sequence và 4.096 token:

\[
2\times32\times8\times128\times4096\times1\times2
= 536{,}870{,}912\text{ byte}=512\text{ MiB}
\]

Nếu phục vụ 8 sequence cùng cấu hình, KV cache xấp xỉ 4 GiB. Khi context tăng gấp đôi, phần cache tăng gần gấp đôi nếu các yếu tố khác không đổi. Mô hình dùng Grouped Query Attention (GQA) có số KV head nhỏ hơn số attention head, nhờ đó giảm dung lượng cache so với Multi-Head Attention có cùng hidden size.

Thực tế có thể khác do cache paging, block allocation, sliding-window attention, cache quantization, prefix sharing hoặc cách runtime quản lý sequence. Công thức giúp lập ngân sách ban đầu; số đo từ runtime vẫn là căn cứ cuối cùng.

### 3.3. Workspace, fragmentation và phần dành cho runtime

Framework có thể cấp phát vùng nhớ tạm cho cuBLAS, cuDNN, attention kernel, graph capture và các phép toán khác. Một số allocator giữ lại vùng VRAM đã cấp phát để tái sử dụng, khiến số liệu “reserved” cao hơn số tensor đang dùng. Vì vậy, cần phân biệt bộ nhớ đang được tensor sử dụng với bộ nhớ framework đã giữ từ GPU.

Nếu tổng dung lượng lý thuyết vừa sát dung lượng VRAM danh nghĩa, một allocation nhỏ hoặc workspace lớn hơn dự kiến cũng có thể gây lỗi out-of-memory. Nên dành headroom cho runtime, biến động batch, context và quá trình nạp mô hình.

## 4. Băng thông bộ nhớ GPU là gì?

Băng thông bộ nhớ (memory bandwidth) là lượng dữ liệu có thể truyền giữa GPU và VRAM trong một đơn vị thời gian, thường được công bố bằng GB/s hoặc TB/s. Băng thông phụ thuộc loại bộ nhớ, tốc độ truyền, độ rộng bus và thiết kế bộ điều khiển bộ nhớ.

Một công thức khái quát cho băng thông đỉnh:

\[
Bandwidth = \frac{Transfer\ rate\times Bus\ width}{8}
\]

Khi tốc độ truyền được tính theo bit mỗi giây và bus width tính bằng bit, cần chia cho 8 để đổi sang byte mỗi giây. Thông số nhà sản xuất công bố thường là băng thông lý thuyết tối đa. Ứng dụng thực tế thường đạt thấp hơn do mẫu truy cập, kernel, mức đồng thời, cache, overhead và giới hạn của workload.

VRAM capacity và bandwidth giải quyết hai vấn đề khác nhau:

- **Capacity:** có đủ chỗ để giữ weights, KV cache và tensor cần thiết không?
- **Bandwidth:** GPU có đọc/ghi dữ liệu đó đủ nhanh để duy trì tốc độ tính toán không?

GPU có VRAM lớn nhưng bandwidth thấp có thể chạy được mô hình nhưng sinh token chậm. GPU có bandwidth rất cao nhưng VRAM quá nhỏ có thể không nạp nổi mô hình hoặc context cần thiết.

## 5. Vì sao bandwidth ảnh hưởng đến tốc độ suy luận?

### 5.1. Memory-bound và compute-bound

Một workload được gọi là **memory-bound** khi tốc độ chủ yếu bị giới hạn bởi việc chuyển dữ liệu từ bộ nhớ; được gọi là **compute-bound** khi tốc độ chủ yếu bị giới hạn bởi năng lực thực hiện phép toán.

Trong suy luận LLM, hai giai đoạn thường có đặc điểm khác nhau:

- **Prefill:** mô hình xử lý prompt đầu vào. Có thể xử lý nhiều token cùng lúc, tận dụng song song tốt hơn và thường có xu hướng compute-bound ở một số cấu hình.
- **Decode:** mô hình sinh từng token tiếp theo. Với batch nhỏ, mỗi bước thường phải truy cập phần lớn trọng số để tính token mới, nên có thể bị giới hạn bởi bandwidth bộ nhớ.

Đây là xu hướng, không phải quy luật tuyệt đối. Batch size, kích thước mô hình, context, kernel attention, quantization và phần cứng có thể làm thay đổi nút thắt.

### 5.2. Arithmetic intensity và mô hình Roofline

Arithmetic intensity là số phép toán thực hiện trên mỗi byte dữ liệu được chuyển từ bộ nhớ. Workload có arithmetic intensity thấp dễ bị giới hạn bởi bandwidth; workload có intensity cao có thể tận dụng năng lực tính toán cao hơn.

Mô hình Roofline biểu diễn giới hạn hiệu năng gần đúng:

\[
Performance\leq\min(Peak\ FLOPS,\ Bandwidth\times Arithmetic\ Intensity)
\]

Nếu bandwidth nhân với arithmetic intensity nhỏ hơn peak FLOPS, tăng số phép tính lý thuyết của GPU có thể không cải thiện nhiều tốc độ. Khi đó, cải thiện truy cập bộ nhớ, batching hoặc giảm lượng dữ liệu phải đọc có thể hữu ích hơn.

### 5.3. Ước lượng giới hạn tốc độ decode

Với suy luận LLM batch nhỏ, một ước lượng rất thô là mỗi token mới cần đọc phần lớn trọng số một lần. Khi đó, giới hạn trên do bandwidth có thể hình dung bằng:

\[
Tokens/s\approx\frac{Effective\ memory\ bandwidth}{Bytes\ read\ per\ token}
\]

Ví dụ, nếu mô hình có khoảng 14 GB trọng số và GPU đạt 1 TB/s băng thông hiệu dụng, phép chia đơn giản cho kết quả khoảng 71 token/s. Đây chỉ là trần lý tưởng hóa để hiểu tác động của bandwidth; hệ thống thực tế còn đọc KV cache, thực hiện phép toán, đồng bộ, xử lý sampling và chịu overhead runtime. Mức bandwidth hiệu dụng cũng có thể thấp hơn thông số đỉnh.

Batching có thể cải thiện hiệu quả đọc weights: một lần đọc trọng số phục vụ nhiều sequence trong cùng batch, nên lượng byte weights trên mỗi token đầu ra có thể giảm. Đổi lại, batch lớn hơn tiêu thụ thêm KV cache và activation, làm tăng độ trễ chờ batch hoặc áp lực VRAM.

## 6. Kích thước mô hình bị giới hạn bởi điều gì?

Không có một con số tham số duy nhất quyết định mô hình có chạy được hay không. Giới hạn phụ thuộc cách sử dụng và cấu hình triển khai.

### 6.1. Suy luận và huấn luyện có ngân sách bộ nhớ khác nhau

| Thành phần | Suy luận | Huấn luyện đầy đủ |
|---|---|---|
| Weights | Có | Có |
| Activations | Có, thường giải phóng sớm hơn | Có, cần giữ hoặc tính lại cho backward |
| KV cache | Thường có với LLM tự hồi quy | Không phải khoản cache decode thông thường; có thể có cấu trúc khác tùy bài toán |
| Gradients | Không | Có |
| Optimizer states | Không | Có, ví dụ moment của Adam |
| Bộ nhớ tạm/runtime | Có | Có, thường lớn hơn do forward/backward và optimizer |

Vì huấn luyện cần gradients, optimizer states và activations, nó thường đòi hỏi VRAM lớn hơn đáng kể so với suy luận cùng mô hình. Một ước lượng thô cho full fine-tuning với Adam có thể lên khoảng 12–20 byte hoặc hơn trên mỗi tham số, tùy precision, master weights, optimizer, sharding và implementation; chưa tính activation và workspace. Không nên dùng con số này thay cho phép đo trên framework thực tế.

### 6.2. Context length và concurrency

Với LLM, tăng context length làm KV cache tăng. Tăng số người dùng hoặc sequence đồng thời cũng làm cache tổng tăng. Vì vậy, GPU có thể nạp được weights nhưng chỉ phục vụ được ít request đồng thời, hoặc chỉ hỗ trợ context ngắn hơn mong muốn.

Ví dụ, một máy chủ suy luận chạy được một sequence 8K token chưa chắc có thể chạy 16 sequence 8K token cùng lúc. Cần tính KV cache theo batch/concurrency, đồng thời tính workspace và bộ nhớ dự phòng.

### 6.3. Kích thước mô hình và cách chia mô hình

Nếu weights và phần bộ nhớ phụ trợ không vừa một GPU, có thể cân nhắc:

- **Quantization:** giảm số bit lưu weights hoặc cache, cân bằng với chất lượng đầu ra và hỗ trợ kernel.
- **Tensor parallelism:** chia tensor hoặc phép tính của một lớp qua nhiều GPU, thường cần liên lạc giữa GPU.
- **Pipeline parallelism:** chia các lớp thành những stage đặt trên các GPU khác nhau.
- **CPU offload:** giữ một phần weights hoặc trạng thái trong RAM hệ thống và chuyển khi cần; tiết kiệm VRAM nhưng có thể chậm do truyền qua PCIe hoặc liên kết khác.
- **Context/batch nhỏ hơn:** giảm KV cache và activation, đổi lại giới hạn độ dài đầu vào hoặc thông lượng.
- **Mô hình nhỏ hơn hoặc kiến trúc hiệu quả hơn:** chọn số tham số, số KV head hoặc cấu hình phù hợp với ngân sách triển khai.

Nhiều GPU không tự động tạo thành một vùng VRAM thống nhất có thể sử dụng như một GPU đơn. Framework phải hỗ trợ chia mô hình, runtime phải quản lý shard và dữ liệu phải đi qua kết nối GPU phù hợp. Khi các GPU trao đổi nhiều, băng thông và độ trễ liên kết như NVLink hoặc PCIe có thể trở thành nút thắt mới.

## 7. Ví dụ lập ngân sách VRAM cho một dịch vụ LLM

Giả sử cần phục vụ một mô hình 7B với trọng số FP16. Ta có thể lập ngân sách sơ bộ như sau:

| Khoản mục | Ước lượng |
|---|---:|
| Weights FP16 | ~13,0 GiB |
| KV cache cho 1 sequence, 4K token theo ví dụ 32 layer/8 KV head | ~0,5 GiB |
| Activation, workspace, runtime và buffer | Phụ thuộc framework/kernel; cần đo |
| Headroom vận hành | Dành thêm cho biến động batch, context và allocation |

Nếu GPU có 16 GiB VRAM, riêng weights và KV cache đã chiếm khoảng 13,5 GiB, chưa tính các khoản còn lại. Cấu hình này có thể quá sát giới hạn. GPU 24 GiB tạo thêm dư địa cho runtime và concurrency, nhưng mức phục vụ thực tế vẫn phải được benchmark.

Nếu chuyển weights sang INT4, payload trọng số lý thuyết giảm xuống khoảng 3,3 GiB. Phần VRAM tiết kiệm có thể dùng cho KV cache lớn hơn, batch lớn hơn hoặc context dài hơn. Tuy nhiên, cần xác minh định dạng lượng tử hóa, chất lượng đầu ra và tốc độ kernel trên GPU được chọn.

Một quy trình sizing có thể thực hiện như sau:

1. Xác định số tham số, kiến trúc, số layer, số KV head, head dimension và precision/quantization.
2. Ước lượng weights bằng số tham số nhân số byte mỗi tham số.
3. Ước lượng KV cache theo context length và concurrency mục tiêu.
4. Ước lượng activation và workspace bằng benchmark trên framework/runtime dự kiến.
5. Cộng thêm phần bộ nhớ runtime và headroom; không lập kế hoạch ở mức vừa khít dung lượng danh nghĩa.
6. Thử tải với context và concurrency gần điều kiện production, quan sát VRAM peak và tốc độ token.
7. Điều chỉnh GPU, quantization, batch, context hoặc cách phân phối mô hình theo kết quả đo.

## 8. Đo VRAM và hiệu năng trong thực tế

### 8.1. Công cụ quan sát

Trên GPU NVIDIA, `nvidia-smi` cung cấp thông tin về bộ nhớ, mức sử dụng GPU, tiến trình và một số chỉ số thiết bị. Với PyTorch, có thể xem thông tin bộ nhớ bằng các API sau:

```python
import torch

if torch.cuda.is_available():
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    allocated_bytes = torch.cuda.memory_allocated()
    reserved_bytes = torch.cuda.memory_reserved()
    peak_bytes = torch.cuda.max_memory_allocated()

    print(f"Free: {free_bytes / 2**30:.2f} GiB")
    print(f"Total: {total_bytes / 2**30:.2f} GiB")
    print(f"Allocated: {allocated_bytes / 2**30:.2f} GiB")
    print(f"Reserved: {reserved_bytes / 2**30:.2f} GiB")
    print(f"Peak allocated: {peak_bytes / 2**30:.2f} GiB")
```

`memory_allocated` phản ánh bộ nhớ tensor đang được PyTorch cấp phát; `memory_reserved` phản ánh vùng allocator đã giữ từ CUDA. `mem_get_info` trả về thông tin bộ nhớ thiết bị tại thời điểm gọi. Cần đo peak sau khi chạy đúng workload, vì đọc ngay sau khi nạp mô hình có thể bỏ sót đỉnh bộ nhớ trong prefill hoặc batch lớn.

### 8.2. Chỉ số nên benchmark

- VRAM peak và phần VRAM còn trống khi tải tối đa.
- Thời gian nạp model và thời gian khởi động.
- Time to first token (TTFT), tốc độ decode token/giây và độ trễ p50/p95/p99.
- Thông lượng tổng theo request hoặc token/giây.
- Batch size, context length và số sequence đồng thời đạt được.
- GPU utilization, memory bandwidth hoặc memory controller utilization nếu công cụ hỗ trợ.
- Tỷ lệ out-of-memory, throttling và lỗi khi tăng tải.

Benchmark cần dùng prompt, output length, batch và concurrency đại diện cho ứng dụng. Một phép thử ngắn với batch 1 không đủ để dự đoán hiệu năng của dịch vụ nhiều người dùng.

## 9. Chọn GPU theo VRAM và bandwidth

Khi chọn GPU cho cloud workload, nên đánh giá đồng thời các yếu tố:

| Tiêu chí | Câu hỏi cần trả lời | Tác động |
|---|---|---|
| VRAM capacity | Weights, KV cache, activation và workspace có vừa không? | Xác định mô hình, context và concurrency tối đa |
| Memory bandwidth | GPU có cấp dữ liệu đủ nhanh cho workload không? | Ảnh hưởng rõ đến workload memory-bound và decode |
| Compute throughput | Có đủ năng lực FP16/BF16/FP8/INT8 hoặc phép toán cần dùng không? | Ảnh hưởng prefill, training và các kernel compute-bound |
| Interconnect | Nhiều GPU trao đổi dữ liệu qua PCIe hay NVLink? | Ảnh hưởng tensor/pipeline parallelism |
| Reliability and availability | Có thể cấp đủ GPU cùng loại trong vùng cần triển khai không? | Ảnh hưởng khả năng mở rộng và tính sẵn sàng |
| Cost | Giá theo giờ và hiệu năng trên mỗi đơn vị công việc là bao nhiêu? | Ảnh hưởng tổng chi phí phục vụ |

Một GPU VRAM lớn phù hợp với mô hình cần giữ nhiều weights hoặc KV cache. Một GPU có bandwidth cao phù hợp hơn khi tốc độ truyền dữ liệu là nút thắt. Với huấn luyện, năng lực tính toán, interconnect và khả năng mở rộng cụm cũng rất quan trọng. Không nên chọn chỉ dựa trên một con số TFLOPS hoặc dung lượng VRAM.

## 10. Những nhầm lẫn thường gặp

**Kích thước checkpoint bằng VRAM cần thiết.** Checkpoint thường chủ yếu chứa weights; runtime còn cần KV cache, activation, workspace và buffer.

**GPU có nhiều TFLOPS hơn luôn suy luận nhanh hơn.** Nếu workload memory-bound, bandwidth và cách truy cập bộ nhớ có thể quyết định tốc độ nhiều hơn peak FLOPS.

**Quantization 4 bit luôn dùng đúng một phần tư VRAM của FP16.** Payload lý thuyết có tỷ lệ đó, nhưng metadata, tensor chưa lượng tử hóa và runtime làm dung lượng thực tế lớn hơn.

**VRAM đầy có nghĩa mô hình quá lớn.** Batch, context, KV cache, workspace hoặc allocator cũng có thể là nguyên nhân. Cần đo peak và phân tích từng khoản.

**Nhiều GPU tự động gộp VRAM thành một bộ nhớ duy nhất.** Cần framework hỗ trợ model parallelism; liên lạc giữa GPU có chi phí và có thể giới hạn hiệu năng.

**Một lần benchmark là đủ.** Hiệu năng thay đổi theo prompt length, output length, batch, concurrency, precision và runtime. Cần thử nhiều điều kiện gần tải thật.

## Kết luận

VRAM quyết định lượng weights và trạng thái tính toán có thể giữ gần GPU; băng thông bộ nhớ quyết định tốc độ trao đổi dữ liệu giữa GPU và VRAM. Kích thước mô hình có thể ước lượng ban đầu từ số tham số và precision, nhưng sizing thực tế phải tính thêm activation, KV cache, workspace, runtime, context length và concurrency. Khi chọn GPU, hãy ghép ngân sách bộ nhớ với đặc điểm memory-bound/compute-bound, khả năng liên kết nhiều GPU và kết quả benchmark trên workload đại diện để đạt cân bằng giữa hiệu năng, khả năng phục vụ và chi phí.
