# Phân chia GPU và chia sẻ tài nguyên giữa nhiều workload

GPU có hàng nghìn đơn vị xử lý song song và băng thông bộ nhớ lớn, phù hợp với các tác vụ như huấn luyện mô hình AI, suy luận, xử lý ảnh, mô phỏng và phân tích dữ liệu. Tuy nhiên, một GPU thường có giá trị đầu tư cao và không phải workload nào cũng sử dụng hết năng lực của thiết bị trong mọi thời điểm. Nếu mỗi workload chiếm riêng một GPU, nhiều tài nguyên có thể bị nhàn rỗi. Nếu cho nhiều workload cùng dùng một GPU mà không kiểm soát, chúng có thể tranh chấp compute, bộ nhớ, băng thông và làm giảm tính ổn định.

**Phân chia GPU** và **chia sẻ GPU** là các cách tổ chức việc sử dụng thiết bị giữa nhiều tiến trình, container, máy ảo hoặc người dùng. Có nhiều mức độ khác nhau: cấp toàn bộ GPU cho một workload, chia sẻ theo thời gian, dùng cơ chế đồng thời của runtime, phân vùng phần cứng hoặc ảo hóa GPU. Mỗi cách có mức độ cô lập, hiệu năng, độ phức tạp và chi phí riêng.

Bài học này thuộc chương **GPU và bộ tăng tốc** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong phạm vi đó, biết cách chia sẻ GPU giúp tăng mức sử dụng tài nguyên, phân bổ năng lực phù hợp và kiểm soát chi phí khi nhiều workload cùng cần bộ tăng tốc.

## 1. GPU có những loại tài nguyên nào?

GPU không chỉ có một chỉ số duy nhất là số lượng thiết bị. Một workload có thể bị giới hạn bởi một hoặc nhiều tài nguyên bên trong GPU:

- **Compute units:** các đơn vị xử lý như Streaming Multiprocessors (SM) trên GPU NVIDIA hoặc các cụm tính toán tương đương trên kiến trúc khác. Chúng thực thi các thread hoặc wavefront song song.
- **Bộ nhớ GPU (VRAM):** lưu tensor, dữ liệu đầu vào, trọng số mô hình, activation, buffer và trạng thái của ứng dụng.
- **Băng thông bộ nhớ:** tốc độ trao đổi dữ liệu giữa compute units và VRAM.
- **Cache và bộ nhớ dùng chung:** hỗ trợ tái sử dụng dữ liệu, giảm truy cập VRAM và phối hợp giữa các thread.
- **Copy engines và khả năng truyền dữ liệu:** hỗ trợ sao chép giữa host memory và GPU memory, hoặc giữa các GPU.
- **Liên kết giữa thiết bị:** PCIe, NVLink hoặc công nghệ tương đương, ảnh hưởng đến truyền dữ liệu giữa GPU và CPU hoặc giữa các GPU.
- **Nguồn điện và giới hạn nhiệt:** có thể ảnh hưởng xung nhịp và hiệu năng khi thiết bị chịu tải lâu dài.

Hai workload cùng dùng một GPU có thể tranh chấp ở các tài nguyên khác nhau. Một tác vụ suy luận batch nhỏ có thể sử dụng ít compute nhưng cần bộ nhớ để giữ model. Một tác vụ huấn luyện có thể chiếm nhiều compute, VRAM và băng thông bộ nhớ trong thời gian dài. Chỉ nhìn mức sử dụng GPU tổng thể có thể không đủ để hiểu nguyên nhân chậm.

### 1.1. Compute và VRAM là hai giới hạn khác nhau

Một GPU có thể còn compute capacity nhưng đã gần hết VRAM. Khi đó workload mới không thể cấp phát đủ bộ nhớ, dù biểu đồ utilization chưa đạt 100%. Ngược lại, GPU có thể còn nhiều VRAM nhưng compute units đang bận, khiến workload mới phải chờ hoặc chạy chậm.

Cần phân biệt:

- **GPU utilization:** mức độ bận của một phần hoặc toàn bộ thiết bị trong một khoảng đo; cách định nghĩa phụ thuộc công cụ và nhà cung cấp.
- **Memory utilization:** dung lượng VRAM đang được sử dụng.
- **Memory bandwidth utilization:** mức độ sử dụng băng thông bộ nhớ.
- **SM/compute utilization:** mức độ bận của các đơn vị xử lý.
- **Queueing và latency:** thời gian workload phải chờ tài nguyên trước khi thực thi.

Một hệ thống chia sẻ GPU hiệu quả phải xem xét đồng thời các giới hạn này, cùng yêu cầu latency và mức độ cô lập của ứng dụng.

## 2. Các mô hình cấp phát và chia sẻ GPU

### 2.1. Cấp GPU độc quyền (exclusive allocation)

Trong mô hình này, một workload được cấp toàn bộ một GPU trong thời gian chạy. Hệ thống lập lịch hoặc nền tảng cloud đảm bảo thiết bị đó không được cấp cho workload khác trong cùng phạm vi quản lý.

**Ưu điểm:**

- Dễ dự đoán hiệu năng hơn khi workload kiểm soát toàn bộ thiết bị.
- Tránh tranh chấp compute và VRAM với workload khác trên cùng GPU.
- Phù hợp với tác vụ huấn luyện lớn, workload nhạy latency hoặc ứng dụng cần toàn bộ bộ nhớ thiết bị.
- Dễ phân tích và giới hạn nguyên nhân khi có vấn đề về hiệu năng.

**Hạn chế:**

- GPU có thể nhàn rỗi khi workload không sử dụng liên tục.
- Workload nhỏ có thể không tận dụng hết compute và VRAM.
- Số lượng workload đồng thời bị giới hạn bởi số GPU.
- Chi phí trên mỗi request hoặc job có thể cao nếu thiết bị thường xuyên không được dùng hết.

Cấp độc quyền không có nghĩa workload tự động có quyền truy cập an toàn hoặc cô lập ở mọi lớp. Cần kết hợp phân quyền thiết bị, container runtime, quyền truy cập host và chính sách bảo mật phù hợp.

### 2.2. Chia sẻ theo thời gian (time-slicing)

**Time-slicing** cho phép nhiều tiến trình hoặc workload dùng chung một GPU bằng cách luân phiên thời gian thực thi. Khi một workload chạy, workload khác có thể phải chờ đến lượt. Driver và GPU scheduler quản lý việc chuyển đổi giữa các công việc theo cơ chế của nền tảng.

Mô hình này hữu ích khi nhiều workload có tải nhỏ, không liên tục hoặc không cần toàn bộ GPU cùng lúc. Ví dụ, nhiều dịch vụ suy luận nội bộ nhận request rải rác trong ngày có thể chia sẻ thiết bị thay vì mỗi dịch vụ giữ một GPU riêng.

~~~mermaid
gantt
    title Minh họa chia sẻ GPU theo lát thời gian
    dateFormat X
    axisFormat %s
    section GPU
    Workload A :a1, 0, 3
    Workload B :b1, 3, 2
    Workload C :c1, 5, 2
    Workload A :a2, 7, 2
    Workload B :b2, 9, 2
~~~

Sơ đồ chỉ minh họa việc luân phiên. Thời lượng lát thời gian, chính sách ưu tiên, mức đồng thời và cách chuyển ngữ cảnh phụ thuộc driver, runtime và nền tảng. Không nên giả định mọi hệ thống đều chia thời gian theo vòng tròn với thời lượng cố định.

**Ưu điểm:**

- Tăng số workload có thể tiếp cận một GPU.
- Cải thiện mức sử dụng khi các workload có thời gian nhàn rỗi.
- Có thể giảm số GPU cần cấp cho các dịch vụ nhỏ.
- Triển khai tương đối đơn giản ở một số nền tảng container.

**Hạn chế:**

- Hiệu năng và latency có thể biến động do tranh chấp.
- Workload nặng có thể làm các workload khác chậm đi.
- Không tự động chia VRAM thành các phần độc lập.
- Không cung cấp mức cô lập lỗi và bảo mật tương đương phân vùng phần cứng.
- Một workload cấp phát quá nhiều bộ nhớ có thể ảnh hưởng đến các workload khác.

Time-slicing thường phù hợp với workload có thể chấp nhận độ trễ biến động và đã được giới hạn tài nguyên ở tầng ứng dụng. Nó không phải lựa chọn mặc định cho workload cần SLA latency nghiêm ngặt hoặc có yêu cầu cách ly mạnh.

### 2.3. Chia sẻ bằng NVIDIA Multi-Process Service (MPS)

**NVIDIA Multi-Process Service (MPS)** là cơ chế cho phép nhiều tiến trình CUDA cùng sử dụng GPU thông qua một dịch vụ điều phối chung. MPS có thể giảm chi phí chuyển đổi giữa các context CUDA và cho phép kernel từ nhiều tiến trình cùng hoạt động trên GPU khi tài nguyên còn khả dụng.

MPS hữu ích khi nhiều tiến trình có kernel nhỏ hoặc không đủ tải để tự lấp đầy GPU. Thay vì mỗi tiến trình giữ một context độc lập gây lãng phí tài nguyên, MPS có thể giúp kết hợp công việc để tăng mức sử dụng.

Các điểm cần hiểu:

- MPS là cơ chế chia sẻ thực thi ở cấp runtime/driver, không phải phân vùng phần cứng.
- Nhiều tiến trình vẫn dùng chung GPU vật lý và các tài nguyên thiết bị.
- Có thể cấu hình giới hạn tỷ lệ hoạt động hoặc mức tài nguyên cho client theo khả năng của phiên bản MPS.
- MPS không tạo ra một vùng VRAM vật lý độc lập cho từng workload.
- MPS không cung cấp mức cách ly lỗi, bảo mật hoặc hiệu năng giống GPU partitioning như MIG.
- Khả năng hỗ trợ, hành vi và giới hạn phụ thuộc GPU, driver, CUDA và cách triển khai.

Ví dụ, ba tiến trình suy luận có batch nhỏ có thể tận dụng MPS để đưa nhiều kernel lên GPU hiệu quả hơn. Tuy nhiên, nếu một tiến trình chiếm phần lớn VRAM hoặc có kernel dài, các tiến trình khác vẫn có thể chịu ảnh hưởng.

MPS cần được thử nghiệm với workload thực tế. Cần theo dõi VRAM, utilization, latency và lỗi client; đồng thời xác minh cách MPS daemon được khởi động, phân quyền và giám sát trong môi trường triển khai.

### 2.4. Phân vùng phần cứng bằng Multi-Instance GPU (MIG)

**Multi-Instance GPU (MIG)** là công nghệ của NVIDIA trên các GPU được hỗ trợ, cho phép chia một GPU vật lý thành nhiều GPU instance. Mỗi instance được cấp một tập tài nguyên phần cứng nhất định, gồm compute và một phần bộ nhớ cùng các thành phần liên quan theo profile được hỗ trợ.

Khác với time-slicing hoặc MPS, MIG tạo các phân vùng phần cứng riêng biệt. Điều này giúp workload có mức hiệu năng và mức cô lập tốt hơn so với chia sẻ mềm trên cùng thiết bị.

~~~mermaid
flowchart TB
    G["Một GPU vật lý hỗ trợ MIG"]
    G --> P1["GPU Instance 1"]
    G --> P2["GPU Instance 2"]
    G --> P3["GPU Instance 3"]
    P1 --> C1["Workload A"]
    P2 --> C2["Workload B"]
    P3 --> C3["Workload C"]
~~~

Sơ đồ là minh họa khái niệm. Số lượng instance, kích thước profile và cách kết hợp phân vùng phụ thuộc model GPU, thế hệ phần cứng và cấu hình MIG được hỗ trợ. Không phải mọi GPU NVIDIA đều hỗ trợ MIG.

Các profile thường được biểu diễn theo tỷ lệ tài nguyên compute và dung lượng bộ nhớ, ví dụ các tên dạng 1g.5gb hoặc 2g.10gb trên một số dòng GPU. Đây chỉ là ví dụ về cách đặt tên; dung lượng và profile thực tế khác nhau theo model. Cần xem tài liệu chính thức của GPU đang sử dụng trước khi thiết kế phân vùng.

**Ưu điểm:**

- Tách compute và bộ nhớ thành các GPU instance riêng theo profile.
- Cải thiện mức cô lập giữa các workload so với chia sẻ mềm.
- Giúp lập lịch workload nhỏ trên cùng GPU vật lý.
- Hiệu năng của một instance ít bị ảnh hưởng bởi việc workload khác dùng compute trong phân vùng khác hơn so với chia sẻ mềm.
- Có thể tăng khả năng dự đoán hiệu năng và phân bổ tài nguyên.

**Hạn chế:**

- Chỉ hỗ trợ trên một số model GPU và profile cụ thể.
- Các phân vùng có kích thước rời rạc, nên có thể phát sinh tài nguyên dư thừa hoặc khó ghép profile.
- Một số tính năng GPU, chế độ hoạt động hoặc công cụ quản trị có giới hạn khi bật MIG.
- Việc thay đổi cấu hình MIG có thể cần tái cấu hình thiết bị và ảnh hưởng workload đang chạy.
- MIG không thay thế mọi cơ chế dự phòng; GPU vật lý vẫn là một miền lỗi chung.

MIG phù hợp khi cần nhiều workload cùng dùng một GPU nhưng vẫn cần giới hạn tài nguyên phần cứng tương đối rõ ràng, chẳng hạn nhiều dịch vụ suy luận độc lập hoặc nhiều nhóm người dùng có nhu cầu GPU vừa phải.

### 2.5. GPU ảo hóa (vGPU) và chia sẻ giữa máy ảo

Một số nền tảng hỗ trợ **vGPU** hoặc cơ chế GPU virtualization để nhiều máy ảo có thể truy cập cùng GPU vật lý. Hypervisor hoặc lớp quản lý GPU cung cấp thiết bị ảo cho từng VM, áp dụng profile, giới hạn hoặc chính sách chia sẻ theo giải pháp của nhà cung cấp.

Các phương thức phổ biến trong hệ sinh thái ảo hóa gồm:

- **PCI passthrough:** gán trực tiếp toàn bộ thiết bị PCIe cho một VM. Cách này thường cho hiệu năng gần native nhưng GPU đó không được chia sẻ đồng thời cho nhiều VM theo cơ chế thông thường.
- **Mediated device/vGPU:** hypervisor tạo thiết bị GPU ảo cho VM và quản lý việc truy cập phần cứng.
- **SR-IOV hoặc cơ chế tương tự:** thiết bị có thể cung cấp các virtual function riêng nếu phần cứng và nền tảng hỗ trợ. Không phải GPU nào cũng hỗ trợ mô hình này.
- **GPU partitioning:** phân chia thiết bị thành các đơn vị có tài nguyên riêng, tùy công nghệ phần cứng và phần mềm.

vGPU có thể yêu cầu driver đặc biệt, phiên bản hypervisor tương thích và giấy phép thương mại. Trước khi chọn, cần kiểm tra model GPU, profile, hệ điều hành khách, phiên bản driver, số lượng VM, tính năng được cấp phép và giới hạn hiệu năng.

Không nên đồng nhất vGPU với MIG. vGPU là mô hình cung cấp thiết bị GPU ảo cho VM; MIG là công nghệ phân vùng phần cứng trên một số GPU NVIDIA. Một số giải pháp có thể kết hợp hoặc xây dựng dựa trên các cơ chế phần cứng, nhưng cách hỗ trợ cụ thể phụ thuộc sản phẩm.

## 3. So sánh các phương thức chia sẻ

| Phương thức | Cơ chế chính | Cô lập tài nguyên | Trường hợp phù hợp |
|---|---|---|---|
| GPU độc quyền | Một workload giữ toàn bộ GPU | Cao ở cấp cấp phát thiết bị; vẫn cần bảo vệ ở các lớp khác | Huấn luyện lớn, workload nhạy latency, cần toàn bộ VRAM |
| Time-slicing | Luân phiên thời gian thực thi giữa nhiều workload | Thấp; dùng chung VRAM và tài nguyên thiết bị | Tác vụ nhỏ, tải không liên tục, chấp nhận latency biến động |
| NVIDIA MPS | Nhiều tiến trình CUDA phối hợp qua MPS server | Chia sẻ mềm, không phân vùng VRAM vật lý | Nhiều tiến trình CUDA nhỏ, GPU chưa được khai thác hết |
| NVIDIA MIG | Phân vùng GPU thành GPU instance phần cứng | Cao hơn chia sẻ mềm; có phân vùng compute và bộ nhớ theo profile | Suy luận nhiều tenant hoặc workload cần giới hạn tài nguyên rõ |
| vGPU | Hypervisor cung cấp GPU ảo cho VM | Phụ thuộc profile, hypervisor và giải pháp | Hạ tầng VM nhiều người dùng, VDI hoặc workload GPU trong VM |
| PCI passthrough | Gán trực tiếp GPU cho VM | Thiết bị được gán độc quyền cho VM | VM cần hiệu năng gần native và quyền kiểm soát GPU |

Bảng trên là định hướng khái quát. Cần đọc tài liệu nhà cung cấp để xác định khả năng hỗ trợ, mức cô lập, giới hạn và yêu cầu license của từng phương thức.

## 4. Chia sẻ GPU trong Kubernetes

### 4.1. Device plugin và extended resource

Kubernetes không mặc định hiểu toàn bộ chi tiết phần cứng GPU. Để cấp GPU cho pod, nhà cung cấp thường triển khai **device plugin**. Plugin phát hiện thiết bị, công bố tài nguyên mở rộng (extended resource) cho kubelet và hỗ trợ cấp thiết bị khi pod được lập lịch.

Với NVIDIA GPU, tài nguyên thường có tên **nvidia.com/gpu**. Một pod có thể yêu cầu một GPU:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-worker
spec:
  restartPolicy: Never
  containers:
    - name: worker
      image: registry.example.com/ml/worker:1.0.0
      resources:
        limits:
          nvidia.com/gpu: 1
~~~

Ví dụ này giả định node đã cài driver phù hợp, NVIDIA Container Toolkit và device plugin đang hoạt động. Kubernetes lập lịch dựa trên số lượng tài nguyên được plugin công bố. Nó không tự chia VRAM hoặc kiểm soát mức sử dụng GPU trong container.

Với tài nguyên mở rộng, thông thường khai báo GPU trong trường **limits**; nếu đồng thời khai báo **requests**, giá trị phải khớp theo quy tắc tài nguyên của Kubernetes. Cần tham khảo phiên bản Kubernetes và device plugin đang triển khai.

### 4.2. Time-slicing với NVIDIA device plugin

NVIDIA Kubernetes device plugin có thể cấu hình time-slicing để công bố nhiều lượt sử dụng logic trên một GPU vật lý. Ví dụ dưới đây minh họa cấu hình cho phép công bố bốn replica logic của một GPU:

~~~yaml
version: v1
sharing:
  timeSlicing:
    renameByDefault: true
    failRequestsGreaterThanOne: true
    resources:
      - name: nvidia.com/gpu
        replicas: 4
~~~

Khi **renameByDefault** được bật, tài nguyên chia sẻ có thể được công bố với tên dạng **nvidia.com/gpu.shared** tùy phiên bản plugin và cấu hình. Pod yêu cầu một đơn vị tài nguyên chia sẻ theo tên được công bố trên node.

Cấu hình trên là ví dụ cho device plugin, không phải Kubernetes Pod manifest. Quản trị viên cần tạo ConfigMap hoặc cấu hình tương ứng, gắn cấu hình cho node/plugin theo tài liệu phiên bản đang dùng, sau đó xác minh tài nguyên thực tế bằng lệnh **kubectl describe node**.

Time-slicing tăng số lượt workload có thể được lập lịch, nhưng không chia VRAM thành các phần độc lập. Nếu bốn pod cùng được cấp một GPU chia sẻ, tổng dung lượng VRAM vẫn là dung lượng vật lý của GPU. Các tiến trình có thể cùng cấp phát bộ nhớ và làm thiết bị hết VRAM.

Đặc biệt, số replica logic không phải số GPU vật lý. Nếu node công bố bốn tài nguyên chia sẻ, scheduler có thể xem đó như bốn đơn vị có thể cấp phát; điều này không có nghĩa thiết bị có bốn lần compute hoặc bộ nhớ.

### 4.3. MIG trong Kubernetes

Khi GPU hỗ trợ MIG, device plugin có thể công bố các GPU instance dưới dạng tài nguyên riêng. Tùy cấu hình, node có thể công bố tài nguyên tổng quát hoặc các profile cụ thể, ví dụ dạng **nvidia.com/mig-1g.5gb**. Tên và profile khả dụng phụ thuộc GPU, driver, MIG strategy và phiên bản plugin.

Một pod yêu cầu profile tương ứng như sau:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: inference-small
spec:
  restartPolicy: Never
  containers:
    - name: inference
      image: registry.example.com/ml/inference:1.0.0
      resources:
        limits:
          nvidia.com/mig-1g.5gb: 1
~~~

Đây là ví dụ minh họa. Trước khi dùng, cần kiểm tra node thực sự công bố đúng tên tài nguyên đó. Nếu profile không tồn tại hoặc node không còn instance phù hợp, pod sẽ ở trạng thái chờ do không đủ tài nguyên.

MIG cần được cấu hình ở cấp GPU/node trước khi workload yêu cầu instance. Việc thay đổi layout MIG có thể làm gián đoạn workload đang sử dụng thiết bị. Nên quản lý cấu hình bằng quy trình hạ tầng có kiểm soát và xác minh lại sau mỗi lần thay đổi.

### 4.4. Lập lịch và phân bổ GPU

Scheduler Kubernetes chủ yếu quyết định pod có thể được đặt trên node nào dựa trên tài nguyên và ràng buộc đã khai báo. Scheduler mặc định không hiểu đầy đủ nhu cầu VRAM, SM, băng thông bộ nhớ hoặc mức độ ưu tiên giữa các tiến trình GPU.

Khi thiết kế cluster, cần xem xét:

- **Node pool:** tách node theo model GPU, dung lượng VRAM, kiến trúc, vùng và mục đích sử dụng.
- **Tài nguyên mở rộng:** khai báo số GPU hoặc GPU instance mà pod cần.
- **Node affinity và taint/toleration:** hướng workload tới đúng nhóm node và tránh sử dụng nhầm thiết bị.
- **MIG profile:** chọn profile đủ VRAM và compute cho từng lớp workload.
- **Priority và quota:** quản lý quyền sử dụng giữa nhóm, namespace hoặc tenant.
- **Topology:** xem xét NUMA, PCIe, NVLink và vị trí GPU khi workload truyền dữ liệu nhiều.
- **Autoscaling:** mở rộng node pool khi có nhu cầu và kiểm tra thời gian cấp GPU, quota cùng capacity thực tế.

Đối với workload cần nhiều GPU cùng lúc, cần xác định yêu cầu về số GPU, topology và giao tiếp liên GPU. Cấp đủ số lượng thiết bị nhưng đặt chúng trên các node hoặc topology không phù hợp có thể làm giảm mạnh hiệu năng huấn luyện phân tán.

## 5. Bảo vệ bộ nhớ và mức độ cô lập

### 5.1. VRAM không tự động được chia theo phần trăm

Một nhầm lẫn thường gặp là cho rằng nếu chia GPU thành bốn lượt time-slicing thì mỗi workload tự động được giới hạn 25% VRAM. Đây không phải hành vi mặc định. Time-slicing chỉ tăng số lượt sử dụng logic mà scheduler hoặc device plugin công bố; các tiến trình vẫn chia sẻ bộ nhớ GPU vật lý.

Tương tự, MPS cho phép phối hợp nhiều tiến trình CUDA nhưng không biến VRAM thành các phân vùng phần cứng riêng. Một tiến trình có thể cấp phát nhiều bộ nhớ hơn dự kiến và gây lỗi cho tiến trình khác.

MIG có thể cung cấp phân vùng bộ nhớ theo profile trên GPU được hỗ trợ. Đây là lựa chọn phù hợp hơn khi cần giới hạn VRAM và compute theo phần cứng, nhưng vẫn phải kiểm tra các giới hạn thực tế của từng profile.

### 5.2. Cô lập hiệu năng và cô lập lỗi

Có ít nhất ba khía cạnh cô lập cần xem xét:

1. **Cô lập tài nguyên:** giới hạn compute, bộ nhớ hoặc băng thông mà workload có thể sử dụng.
2. **Cô lập hiệu năng:** workload khác khó làm thay đổi latency hoặc throughput của workload đang chạy.
3. **Cô lập lỗi và bảo mật:** lỗi tiến trình hoặc thao tác không an toàn khó ảnh hưởng đến workload khác.

GPU độc quyền thường dễ dự đoán hơn ở cấp thiết bị. MIG tăng mức cô lập nhờ phân vùng phần cứng. Time-slicing và MPS là chia sẻ mềm, nên mức cô lập thấp hơn và cần kiểm soát chặt ở tầng ứng dụng, hệ điều hành và nền tảng.

Dù dùng MIG, GPU vật lý, node, driver và hệ thống điện vẫn là các điểm có thể lỗi chung. Không nên coi phân vùng GPU là cơ chế dự phòng phần cứng.

### 5.3. Cô lập tenant và bảo mật

Khi nhiều nhóm hoặc khách hàng cùng sử dụng GPU, cần xác định ranh giới tin cậy:

- Chỉ cấp quyền truy cập thiết bị cho container hoặc VM được phép.
- Không mount socket quản trị hoặc quyền đặc biệt của host vào workload không đáng tin cậy.
- Quản lý driver và runtime GPU theo phiên bản được hỗ trợ.
- Giới hạn quyền truy cập dữ liệu, model, checkpoint và secret.
- Tách namespace, service account, network policy và quota theo tenant.
- Kiểm tra khả năng xóa hoặc làm sạch dữ liệu nhạy cảm khi tái sử dụng thiết bị.
- Dùng cơ chế phân vùng và ảo hóa đã được nhà cung cấp xác nhận cho môi trường nhiều tenant.

Không nên đưa workload không tin cậy vào cùng một GPU dùng chung mềm chỉ dựa trên giả định rằng container đã tạo ra ranh giới bảo mật đầy đủ. Container chia sẻ kernel host và driver GPU; cần đánh giá threat model của toàn nền tảng.

## 6. Chọn mô hình theo loại workload

### 6.1. Huấn luyện mô hình lớn

Training có thể cần gần như toàn bộ compute, VRAM và băng thông của GPU. Một số workload còn cần nhiều GPU và liên kết tốc độ cao. GPU độc quyền thường là lựa chọn dễ dự đoán hiệu năng nhất.

Nếu mô hình có thể chia thành các job nhỏ, dùng batch hoặc checkpoint, có thể cân nhắc lập lịch chia sẻ theo thời gian cho các job ít quan trọng. Tuy nhiên, cần đo thời gian chờ, tổng thời gian hoàn thành và tác động của tranh chấp.

### 6.2. Suy luận mô hình

Inference có nhiều dạng:

- **Online inference:** request đến liên tục và thường có yêu cầu latency.
- **Batch inference:** xử lý theo lô, có thể chấp nhận thời gian chờ dài hơn.
- **Embedding hoặc reranking:** workload có thể nhỏ nhưng chạy với tần suất cao.
- **Model serving nhiều phiên bản:** nhiều model nhỏ cần giữ trong VRAM.

MIG có thể phù hợp để cấp profile riêng cho nhiều dịch vụ inference cần mức cô lập tương đối. MPS hoặc time-slicing có thể phù hợp với nhiều tiến trình nhỏ, nếu latency và mức tranh chấp nằm trong ngưỡng. Với online inference nhạy latency, nên benchmark theo p95/p99 khi nhiều tenant cùng chạy.

### 6.3. Xử lý ảnh, video và mô phỏng

Các tác vụ xử lý ảnh hoặc video có thể có tải theo đợt, phù hợp với chia sẻ nếu pipeline hỗ trợ hàng đợi và retry. Mô phỏng khoa học hoặc xử lý dữ liệu có thể sử dụng nhiều VRAM và băng thông bộ nhớ; cần benchmark để xác định chia sẻ mềm có làm kéo dài thời gian chạy hay không.

### 6.4. Môi trường phát triển và thử nghiệm

Notebook, môi trường thử nghiệm và job phát triển thường có tải không liên tục. Chia sẻ GPU giúp nhiều người dùng tiếp cận thiết bị với chi phí thấp hơn. Tuy nhiên, cần quota, giới hạn thời gian chạy, giới hạn bộ nhớ ở tầng ứng dụng và cơ chế dọn dẹp tài nguyên sau khi người dùng kết thúc phiên.

Không nên để một notebook quên tắt kernel chiếm GPU trong thời gian dài. Nền tảng cần theo dõi idle session, timeout, quota và quyền ưu tiên để tài nguyên quay lại pool dùng chung.

## 7. Ước lượng và phân bổ tài nguyên GPU

### 7.1. Đo nhu cầu trước khi chọn profile

Với từng workload, thu thập:

- VRAM tối thiểu và mức đỉnh.
- Mức sử dụng compute và thời gian kernel.
- Băng thông bộ nhớ.
- Kích thước batch và số request đồng thời.
- Latency mục tiêu và throughput cần đạt.
- Thời gian chạy, chu kỳ tải và mức ưu tiên.
- Dung lượng model, activation, cache và buffer.
- Số GPU và yêu cầu giao tiếp liên GPU.

Đối với inference, batch size và số request đồng thời có thể làm VRAM tăng nhanh. Với training, optimizer state, gradient, activation và checkpoint có thể chiếm nhiều bộ nhớ hơn trọng số model. Không nên chọn GPU chỉ dựa vào kích thước file model.

### 7.2. Dự phòng và giới hạn

Khi cấp profile MIG hoặc lập quota chia sẻ, cần chừa khoảng an toàn cho peak memory và biến động tải. Nếu workload thường dùng 4 GB nhưng đôi khi tăng lên 7 GB, profile có 5 GB sẽ không phù hợp chỉ vì mức trung bình thấp.

Với time-slicing, cần đặt giới hạn số workload cùng GPU và kiểm soát mức sử dụng trong ứng dụng. Với MPS, có thể cân nhắc cấu hình tỷ lệ hoạt động cho client nếu nền tảng hỗ trợ, nhưng phải nhớ rằng tỷ lệ hoạt động không tương đương giới hạn VRAM.

Với MIG, chọn profile dựa trên cả compute và bộ nhớ. Một profile có đủ VRAM nhưng quá ít compute có thể không đạt throughput. Ngược lại, profile có compute phù hợp nhưng thiếu VRAM có thể không tải được model hoặc batch.

### 7.3. Tránh phân mảnh tài nguyên

MIG dùng các profile rời rạc. Một GPU có thể còn tổng dung lượng tài nguyên nhưng không có tổ hợp instance phù hợp với yêu cầu mới. Ví dụ, các phân vùng nhỏ đã được cấp hết khiến workload cần profile lớn không thể chạy, dù một số tài nguyên còn dư ở các phần không ghép được theo cấu hình.

Đây là **phân mảnh tài nguyên**. Cần quan sát nhu cầu theo profile, tỷ lệ sử dụng và thời gian chờ. Có thể giải quyết bằng cách chuẩn hóa một số profile, gom nhóm workload tương đồng, lên lịch lại khi ít tải hoặc dành một số GPU cho workload lớn.

## 8. Giám sát và xử lý sự cố

### 8.1. Chỉ số cần theo dõi

| Nhóm chỉ số | Ví dụ | Ý nghĩa |
|---|---|---|
| Compute | GPU utilization, SM activity, kernel duration | Xác định GPU có đang bận hay không |
| Memory | VRAM used/free, allocation failure | Phát hiện thiếu bộ nhớ hoặc cấp phát tăng bất thường |
| Memory bandwidth | Throughput đọc/ghi bộ nhớ | Phát hiện nghẽn truyền dữ liệu nội bộ |
| Latency | Queue wait, inference latency p50/p95/p99 | Đo ảnh hưởng của tranh chấp tới người dùng |
| Throughput | Request/s, samples/s, jobs/hour | Đo năng lực xử lý thực tế |
| Reliability | GPU reset, Xid/error, pod restart | Phát hiện lỗi thiết bị hoặc driver |
| Scheduling | Pending pods, allocation failure, profile usage | Phát hiện thiếu tài nguyên hoặc phân mảnh |
| Cost | Chi phí GPU theo request/job/model | Đánh giá hiệu quả sử dụng tài nguyên |

Có thể dùng công cụ theo nhà cung cấp như NVIDIA System Management Interface (nvidia-smi), NVIDIA Data Center GPU Manager (DCGM), exporter cho Prometheus hoặc dashboard của nền tảng cloud. Với GPU không thuộc NVIDIA, dùng công cụ giám sát tương ứng của nhà sản xuất.

### 8.2. Chẩn đoán tình huống thường gặp

**GPU utilization thấp nhưng workload chậm:** có thể CPU preprocessing, I/O, network, batch nhỏ hoặc đồng bộ dữ liệu đang là nút thắt. Không nên vội tăng GPU.

**VRAM đầy dù compute thấp:** model hoặc cache đang giữ bộ nhớ; có thể batch, số tiến trình hoặc bản sao model quá lớn. Kiểm tra allocation và memory leak.

**Nhiều workload chậm cùng lúc:** có thể tranh chấp GPU, băng thông, copy engine hoặc CPU host. Tách chỉ số theo workload và thử nghiệm giảm số tenant đồng thời.

**Pod không được lập lịch:** kiểm tra tài nguyên GPU node công bố, profile MIG, quota namespace, node selector, taint và tên extended resource.

**Container báo exec hoặc driver error:** kiểm tra phiên bản driver, CUDA runtime, container toolkit, image architecture và khả năng tương thích giữa các thành phần.

**GPU bị reset hoặc mất thiết bị:** kiểm tra log kernel, driver, lỗi phần cứng, nguồn điện và nhiệt độ. Cô lập node nếu có dấu hiệu lỗi thiết bị ảnh hưởng nhiều workload; khôi phục theo runbook của nền tảng.

### 8.3. Kiểm thử tranh chấp có kiểm soát

Trước khi đưa nhiều tenant vào cùng GPU, chạy thử các tổ hợp tải:

1. Một workload chạy riêng để lấy baseline.
2. Hai workload cùng loại chạy đồng thời.
3. Hai workload khác loại, ví dụ inference và batch processing.
4. Tải đỉnh với VRAM gần ngưỡng.
5. Một workload kết thúc bất thường hoặc bị kill.
6. Thay đổi số lượng workload đồng thời và đo latency, throughput.

So sánh kết quả với SLO. Nếu một tenant có thể làm tenant khác vượt ngưỡng latency hoặc gây OOM, cần giảm mức chia sẻ, chuyển sang MIG hoặc cấp GPU độc quyền.

## 9. Tối ưu chi phí và hiệu quả sử dụng

Chi phí GPU thường lớn hơn nhiều loại tài nguyên compute khác. Tối ưu không chỉ là tăng utilization; cần giảm chi phí trên mỗi đơn vị công việc mà vẫn đáp ứng yêu cầu chất lượng.

Một số biện pháp:

- **Gom workload nhỏ:** đặt các workload tương thích vào cùng GPU bằng time-slicing hoặc MPS khi có thể chấp nhận tranh chấp.
- **Dùng MIG cho nhiều tenant:** cấp profile phù hợp thay vì để từng workload giữ toàn bộ GPU.
- **Tách lớp workload:** workload latency-sensitive dùng GPU riêng hoặc MIG; batch có thể dùng phần tài nguyên còn lại theo chính sách.
- **Batching:** gộp request để tăng hiệu quả compute, đồng thời kiểm soát latency và VRAM.
- **Autoscaling:** tăng/giảm số GPU hoặc node theo hàng đợi, throughput và độ trễ.
- **Scale-to-zero hoặc tắt node nhàn rỗi:** phù hợp với môi trường phát triển và batch nếu thời gian khởi động chấp nhận được.
- **Giới hạn thời gian và quota:** dừng workload không hoạt động, notebook bỏ quên hoặc job vượt thời hạn.
- **Theo dõi chi phí theo tenant:** phân bổ chi phí theo request, model, nhóm hoặc dự án.

Không nên đặt mục tiêu utilization 100% cho mọi thời điểm. Khi GPU luôn ở sát ngưỡng, workload mới không có headroom, latency dễ tăng và hệ thống khó chịu được đột biến. Nên duy trì mức dự phòng phù hợp với đặc tính tải và SLO.

## 10. Ví dụ thiết kế

### Ví dụ A: Nhiều dịch vụ suy luận nhỏ trên một GPU

Một nhóm có bốn model nhỏ, mỗi model nhận request không liên tục. Mỗi model không cần toàn bộ compute của GPU, nhưng vẫn cần giữ trọng số trong VRAM.

Nhóm đo VRAM đỉnh, latency và mức compute. Nếu GPU có hỗ trợ MIG và mỗi model vừa với profile riêng, có thể cấp các GPU instance để tách tài nguyên. Nếu model có thể chia sẻ mềm và latency ít nhạy, nhóm có thể thử MPS hoặc time-slicing.

Sau thử nghiệm, nhóm chọn phương thức dựa trên p95/p99 latency, tỷ lệ lỗi cấp phát bộ nhớ, throughput và chi phí. Cần giữ một phương án quay lại GPU độc quyền nếu mức tranh chấp làm SLO không đạt.

### Ví dụ B: Cluster Kubernetes có GPU MIG

Một cluster có node GPU hỗ trợ MIG. Quản trị viên cấu hình profile theo nhu cầu: một số instance nhỏ cho inference, một số profile lớn hơn cho tác vụ xử lý nặng. Device plugin công bố tài nguyên theo profile. Deployment yêu cầu đúng extended resource và được lập lịch lên node có tài nguyên tương ứng.

Hệ thống monitoring theo dõi số instance khả dụng, VRAM, utilization, pending pod và latency. Khi profile nhỏ bị sử dụng hết, autoscaler có thể bổ sung node hoặc đội vận hành điều chỉnh phân bổ theo kế hoạch. Cần có runbook cho việc thay đổi MIG layout vì thao tác này có thể ảnh hưởng workload đang chạy.

### Ví dụ C: Nền tảng notebook dùng chung

Một nền tảng phát triển cấp GPU cho nhiều người dùng. Người dùng có thể mở notebook trong thời gian ngắn và thường để thiết bị nhàn rỗi giữa các lần chạy cell.

Nền tảng áp dụng quota theo nhóm, timeout cho session không hoạt động, giới hạn thời gian chạy và cơ chế chia sẻ GPU. Workload production có yêu cầu latency nghiêm ngặt được tách khỏi pool notebook. Dashboard hiển thị mức sử dụng, số session, thời gian chờ và chi phí theo nhóm để nhóm vận hành cân đối capacity.

## 11. Những sai lầm thường gặp

**Cho rằng time-slicing chia VRAM thành các phần riêng.** Time-slicing chia sẻ thời gian thực thi; bộ nhớ GPU vẫn là tài nguyên dùng chung và có thể bị một workload chiếm nhiều.

**Coi MPS là phân vùng phần cứng.** MPS giúp nhiều tiến trình CUDA phối hợp thực thi, nhưng không cung cấp vùng VRAM và mức cô lập phần cứng như MIG.

**Dùng MIG mà không kiểm tra profile.** Profile có kích thước rời rạc và phụ thuộc model GPU. Một profile phù hợp trên dòng GPU này có thể không tồn tại trên dòng khác.

**Chỉ nhìn GPU utilization trung bình.** Utilization trung bình không cho biết latency p99, peak VRAM, thời gian chờ hoặc phân mảnh tài nguyên. Cần đo theo workload.

**Đưa workload không tin cậy vào cùng GPU chia sẻ mềm.** Container không tự tạo ranh giới bảo mật đầy đủ cho GPU, driver và kernel. Cần đánh giá threat model và mức cô lập.

**Cấp quá nhiều lượt chia sẻ.** Tăng số replica logic có thể làm nhiều pod được lập lịch nhưng không tăng năng lực vật lý. Kết quả có thể là latency tăng và OOM.

**Không dành capacity dự phòng.** Khi GPU luôn được lấp đầy, hệ thống khó hấp thụ tải đột biến hoặc phục hồi workload sau lỗi node.

**Thay đổi MIG layout khi workload đang chạy.** Thay đổi phân vùng có thể yêu cầu dừng hoặc tái cấu hình thiết bị. Cần có kế hoạch bảo trì và di chuyển workload.

**Không đo chi phí trên đơn vị công việc.** Utilization cao chưa chắc có nghĩa kinh tế tốt nếu latency, lỗi hoặc thời gian hoàn thành tăng mạnh.

## 12. Checklist trước khi triển khai

- [ ] Xác định model GPU, VRAM, compute capability và tính năng chia sẻ được hỗ trợ.
- [ ] Đo peak VRAM, compute, bandwidth, latency và throughput của từng workload.
- [ ] Xác định yêu cầu cô lập hiệu năng, lỗi và bảo mật giữa tenant.
- [ ] Chọn GPU độc quyền, time-slicing, MPS, MIG hoặc vGPU theo yêu cầu.
- [ ] Kiểm tra driver, CUDA, runtime, hypervisor và device plugin tương thích.
- [ ] Xác minh profile MIG hoặc tên extended resource thực tế trên node.
- [ ] Thiết lập quota, giới hạn số workload và chính sách ưu tiên.
- [ ] Cấu hình scheduling, node affinity, taint/toleration và topology phù hợp.
- [ ] Theo dõi VRAM, compute, bandwidth, latency, lỗi và thời gian chờ.
- [ ] Kiểm thử tranh chấp, OOM, restart và tình huống một workload lỗi.
- [ ] Duy trì headroom và phương án dự phòng khi GPU hoặc node gặp sự cố.
- [ ] Tính chi phí theo request, job hoặc tenant và điều chỉnh mức chia sẻ.

## 13. Ghi nhớ

- **GPU có nhiều loại tài nguyên:** compute, VRAM, băng thông bộ nhớ, copy engine và liên kết giữa thiết bị.
- **GPU độc quyền** dễ dự đoán hiệu năng nhưng có thể để lại tài nguyên nhàn rỗi.
- **Time-slicing** luân phiên thời gian thực thi; không tự chia VRAM thành các vùng độc lập.
- **MPS** giúp nhiều tiến trình CUDA phối hợp sử dụng GPU; đây là chia sẻ mềm, không phải phân vùng phần cứng.
- **MIG** chia một số GPU NVIDIA được hỗ trợ thành các GPU instance có tài nguyên phần cứng theo profile.
- **vGPU** cung cấp thiết bị GPU ảo cho VM; khả năng và mức cô lập phụ thuộc giải pháp ảo hóa.
- **Kubernetes device plugin** công bố GPU hoặc GPU instance để scheduler cấp cho pod; scheduler không tự hiểu mọi giới hạn VRAM và compute.
- Lựa chọn mô hình phải dựa trên peak VRAM, latency, throughput, mức cô lập, khả năng hỗ trợ và chi phí.
- Giám sát theo workload và kiểm thử tranh chấp là điều kiện cần để chia sẻ GPU an toàn.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| GPU | Graphics Processing Unit, bộ xử lý song song cho đồ họa và tính toán tăng tốc. |
| VRAM | Bộ nhớ chuyên dụng trên GPU, lưu dữ liệu và trạng thái của workload. |
| SM | Streaming Multiprocessor, cụm đơn vị xử lý trên một số kiến trúc GPU NVIDIA. |
| Time-slicing | Chia thời gian sử dụng GPU giữa nhiều workload. |
| MPS | NVIDIA Multi-Process Service, cơ chế phối hợp nhiều tiến trình CUDA dùng chung GPU. |
| MIG | NVIDIA Multi-Instance GPU, công nghệ phân vùng phần cứng trên các GPU được hỗ trợ. |
| vGPU | GPU ảo được cung cấp cho máy ảo qua lớp ảo hóa. |
| PCI passthrough | Gán trực tiếp thiết bị PCIe vật lý cho máy ảo. |
| Device plugin | Thành phần Kubernetes phát hiện và công bố tài nguyên thiết bị cho kubelet. |
| Extended resource | Tài nguyên mở rộng mà Kubernetes có thể lập lịch và cấp cho pod. |
| GPU instance | Một phân vùng GPU được tạo theo profile phần cứng, ví dụ trong MIG. |
| VRAM fragmentation | Tình trạng bộ nhớ hoặc phân vùng còn dư nhưng không đáp ứng được yêu cầu cấp phát tiếp theo. |
| Headroom | Phần năng lực dự phòng để hấp thụ tải tăng hoặc biến động. |
| Throughput | Số lượng request, mẫu dữ liệu hoặc công việc xử lý được trong một đơn vị thời gian. |
| Latency | Thời gian từ khi gửi yêu cầu đến khi nhận được kết quả. |
