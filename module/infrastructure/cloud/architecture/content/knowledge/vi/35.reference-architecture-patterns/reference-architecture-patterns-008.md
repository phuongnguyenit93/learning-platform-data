# Tác vụ theo lô quy mô lớn và xử lý song song

## 1. Bài toán kiến trúc: hoàn thành một khối lượng lớn trong thời gian hữu hạn

Một hệ thống xử lý theo lô (**batch processing**) nhận một tập công việc hoặc dữ liệu xác định, thực hiện theo đợt và tạo ra kết quả có thể kiểm tra. Ví dụ: kết toán giao dịch cuối ngày, tổng hợp dữ liệu bán hàng, biến đổi dữ liệu cho kho phân tích, dựng hàng nghìn video, tính lại chỉ mục tìm kiếm, mô phỏng khoa học hoặc huấn luyện đặc trưng cho mô hình máy học.

Khi khối lượng dữ liệu tăng từ vài gigabyte lên hàng terabyte, cách chạy một chương trình tuần tự trên một máy có thể không đáp ứng **thời hạn hoàn thành (deadline/SLA)**. Kiến trúc xử lý song song chia khối lượng thành các đơn vị có thể thực hiện đồng thời, phân phối đến nhiều tài nguyên compute, rồi tổng hợp kết quả một cách có kiểm soát.

Trong module **CLOUD_ARCHITECTURE**, chủ đề này là một **mẫu kiến trúc tham chiếu** để đi từ yêu cầu nghiệp vụ đến quyết định **mạng, compute, lưu trữ dữ liệu và triển khai**. Mục tiêu không đơn thuần là chạy nhiều máy: cần cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo các nguyên tắc Well-Architected.

### Batch khác gì streaming và tác vụ nền thông thường?

| Loại xử lý | Cách nhận dữ liệu và thời điểm hoàn thành | Trường hợp phù hợp |
|---|---|---|
| **Batch theo lịch** | Chạy trên một tập dữ liệu đã chốt theo giờ/ngày/tuần; có điểm bắt đầu, kết thúc | Báo cáo cuối ngày, tính hóa đơn hàng tháng |
| **Batch theo yêu cầu** | Kích hoạt khi người dùng hoặc hệ thống gửi một công việc hữu hạn | Xuất dữ liệu, chuyển đổi tập ảnh, dựng video |
| **Micro-batch** | Gom dữ liệu mới thành các đợt nhỏ, chạy lặp lại | Phân tích gần thời gian thực khi chấp nhận độ trễ vài phút |
| **Streaming liên tục** | Xử lý luồng sự kiện không có điểm kết thúc cố định, cập nhật kết quả dần | Phát hiện gian lận, theo dõi sự kiện tức thời |
| **Background job đơn lẻ** | Chạy tác vụ bất đồng bộ; có thể chỉ cần một worker | Gửi email, tạo thumbnail cho một tệp |

Batch không nhất thiết phải “chạy ban đêm”; nó được xác định bởi **ranh giới lô, trạng thái hoàn thành và cách xuất bản kết quả**. Xử lý song song có thể dùng trong batch lẫn streaming. Một batch lớn cũng có thể khởi chạy từ một sự kiện thay vì cron.

## 2. Chuyển yêu cầu nghiệp vụ thành chỉ tiêu thiết kế

Trước khi chọn dịch vụ đám mây, cần ghi rõ các thuộc tính của workload:

| Thuộc tính | Câu hỏi cần trả lời | Ảnh hưởng tới kiến trúc |
|---|---|---|
| **Khối lượng** | Mỗi đợt có bao nhiêu tệp/bản ghi/GB? Mức đỉnh? | Số phân vùng, mức song song, dung lượng tạm |
| **Cửa sổ thời gian** | Phải hoàn thành sau bao lâu? Độ trễ cho phép? | Throughput mục tiêu, quota, autoscaling |
| **Tính độc lập** | Các đơn vị có dùng chung trạng thái hay chờ nhau? | Fan-out/fan-in, DAG, shuffle, đồng bộ |
| **Đặc điểm tài nguyên** | Tốn CPU, GPU, RAM, I/O đĩa hay mạng? | Loại compute và kích cỡ worker |
| **Dữ liệu và tính đúng** | Kết quả phải chính xác tuyệt đối, gần đúng, hay có thể chạy lại? | Khóa phân vùng, deduplication, checkpoint, transaction |
| **Phân loại bảo mật** | Có dữ liệu cá nhân, khóa bí mật, quy định lưu trú? | IAM, mã hóa, mạng riêng, xử lý dữ liệu tạm |
| **SLA phục hồi** | Nếu một worker hỏng, được phép mất bao nhiêu thời gian? | Retry, phục hồi từng phân vùng, dự phòng |
| **Tính kinh tế** | Đợt chạy mỗi ngày/tuần? Dự báo chi phí tối đa? | Compute theo nhu cầu, tắt khi rảnh, tài nguyên có thể gián đoạn |
| **Phụ thuộc** | Đọc từ OLTP, object storage, API hay hệ thống tại chỗ? | Throttling nguồn, kết nối hybrid, vị trí xử lý |

Ví dụ, yêu cầu **“xử lý 900 GB log sau mỗi ngày và có báo cáo trong 90 phút”** phải được chuyển thành mục tiêu tốc độ đọc, biến đổi, ghi và xuất bản. Nếu dữ liệu nằm ở một nguồn chỉ cho đọc 50 MB/s, tăng số worker cũng không giúp vượt nút thắt tại nguồn.

### Ba tiêu chí nghiệm thu cần phân biệt

- **Tính đúng (correctness):** không mất/đếm trùng dữ liệu; kết quả khớp quy tắc nghiệp vụ và phiên bản dữ liệu đầu vào.
- **Thời gian hoàn thành (completion time):** tính từ khi dữ liệu **sẵn sàng** đến khi kết quả **đã xuất bản và có thể dùng**, bao gồm chờ hàng đợi, shuffle, retry và kiểm chứng.
- **Khả năng khôi phục:** khi mất worker hoặc gián đoạn cả đợt, có thể chạy lại từ checkpoint/đầu vào ổn định với kết quả tương đương trong giới hạn đã thỏa thuận.

Chỉ đo thời gian xử lý CPU là không đủ để chứng minh SLA của toàn pipeline.

## 3. Mẫu kiến trúc tham chiếu

Một thiết kế phổ biến tách **control plane** (lên lịch, điều phối, quản lý trạng thái) khỏi **data plane** (đọc, xử lý và ghi dữ liệu):

~~~mermaid
flowchart TB
    T["Lịch chạy / sự kiện / API"] --> O["Orchestrator / DAG"]
    O --> M["Tạo manifest đầu vào<br/>run_id, phiên bản dữ liệu, phân vùng"]
    M --> Q["Hàng đợi / bộ lập lịch tác vụ"]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> WN["Worker N"]
    S[("Object storage / data lake<br/>đầu vào bất biến")] --> W1
    S --> W2
    S --> WN
    W1 --> TMP[("Kết quả tạm theo partition")]
    W2 --> TMP
    WN --> TMP
    TMP --> V["Kiểm chứng / reduce / merge"]
    V --> P[("Kết quả chính thức<br/>bảng phân tích / tệp / chỉ mục")]
    O <--> J[("Job state / checkpoint / metadata")]
    W1 -. "metrics / logs" .-> OBS["Quan sát & cảnh báo"]
    W2 -. "metrics / logs" .-> OBS
    WN -. "metrics / logs" .-> OBS
    O -. "events" .-> OBS
    V --> O
~~~

Các khối có vai trò riêng:

1. **Orchestrator** khởi chạy theo lịch/sự kiện, điều phối phụ thuộc, ghi trạng thái và xác định khi nào toàn đợt hoàn tất. Có thể là công cụ workflow, scheduler hoặc dịch vụ điều phối quản lý.
2. **Manifest** “đóng băng” danh sách nguồn và các phân vùng của một lần chạy. Nó chứa **run_id**, phạm vi thời gian, schema/version, vị trí dữ liệu và checksum hoặc thông tin đối soát khi phù hợp.
3. **Queue/scheduler** phân phối task, giới hạn mức chạy đồng thời và hỗ trợ thử lại. Một công cụ xử lý dữ liệu phân tán có thể sở hữu scheduler nội bộ, khi đó không cần hàng đợi rời.
4. **Worker** là VM, container, tác vụ batch quản lý, hàm serverless, process trong engine phân tán hoặc node HPC. Mỗi worker nên xử lý một **đơn vị công việc có định danh**.
5. **Staging** chứa đầu ra chưa công bố, ghi theo phân vùng và lần thử. **Reduce/validation** tổng hợp, kiểm tra đầy đủ rồi mới chuyển trạng thái kết quả thành sẵn sàng.
6. **Metadata store** giữ trạng thái đợt, các lần thử, checkpoint, lineage và phiên bản kết quả; đây là phần cần bảo vệ và sao lưu giống dữ liệu nghiệp vụ.
7. **Observability** theo dõi tiến độ, queue lag, tài nguyên, lỗi, độ lệch phân vùng và chi phí mỗi đợt.

Đây là **mẫu logic**, không quy định phải triển khai bằng đúng bảy sản phẩm. Managed Spark có thể gộp scheduler, worker và shuffle; dịch vụ batch container có thể thay hàng đợi bằng job array; một DAG đơn giản chỉ có hai bước cũng có thể không cần metadata database riêng.

## 4. Chia nhỏ công việc là điều kiện để chạy song song

### 4.1. Tính độc lập và chiến lược phân vùng

Mỗi **partition/shard** nên thỏa các bất biến:

- Phạm vi được định nghĩa rõ: theo ngày, khoảng khóa, hash, tệp hoặc danh sách object.
- Các partition cùng một lần chạy **không chồng lấn** khi mục tiêu là xử lý mỗi đầu vào đúng một lần.
- Hợp các partition bao phủ toàn bộ dữ liệu đã chốt trong manifest.
- Có thể định danh và chạy lại một partition mà không phụ thuộc trạng thái cục bộ của worker vừa hỏng.
- Kích cỡ đủ lớn để công điều phối không lấn át công xử lý, nhưng đủ nhỏ để cân bằng tải.

| Phân vùng theo | Lợi ích | Điểm cần kiểm tra |
|---|---|---|
| **Khoảng thời gian** (ngày/giờ) | Thuận tiện incremental và backfill | Giờ cao điểm làm các partition lệch kích thước |
| **Hash(key)** | Phân phối đều khi khóa đa dạng | Cần giữ số bucket và quy tắc hash ổn định trong một run |
| **Khoảng giá trị** (ID range) | Tối ưu nếu dữ liệu được sắp theo khóa | Key space thưa, hot range và lỗi tại ranh giới |
| **Tệp/object** | Dễ fan-out các tệp độc lập | Tệp quá lớn hoặc hàng triệu tệp nhỏ gây mất cân bằng |
| **Khóa nghiệp vụ** | Giữ toàn bộ bản ghi của cùng entity ở một nơi | “Hot key” tạo worker xử lý rất lâu |

Ví dụ nguồn khoảng 900 GB có thể chia thành vài nghìn phần việc, nhưng **kích cỡ hợp lý phải được benchmark** theo tốc độ đọc, bộ nhớ và độ phức tạp của phép biến đổi. Các giá trị như 128–512 MiB/partition chỉ là **điểm thử ban đầu** thường gặp với phân tích dữ liệu dạng tệp cột, không phải quy định chung cho mọi engine.

### 4.2. Mức song song không vô hạn

Cần phân biệt:

- **Số task:** tổng số đơn vị công việc.
- **Concurrency:** số task thực thi tại một thời điểm.
- **Parallelism thực tế:** số core/slot và khả năng xử lý hữu ích đồng thời.

Có 20.000 task không có nghĩa cần 20.000 worker. Ngược lại, chỉ chia dữ liệu thành 10 partition sẽ hạn chế tốc độ dù có 100 worker nhàn rỗi. Orchestrator cần dùng **bounded concurrency** để không vượt quota, nghẽn nguồn dữ liệu hoặc làm quá tải dịch vụ đích.

### 4.3. Các dạng xử lý song song phổ biến

| Mẫu | Cách hoạt động | Ví dụ |
|---|---|---|
| **Embarrassingly parallel** | Mỗi task độc lập, ít hoặc không trao đổi dữ liệu | Chuyển định dạng ảnh, render từng video |
| **Fan-out / fan-in** | Tách hàng loạt task rồi chờ đủ kết quả để tổng hợp | Kiểm tra nhiều tệp, tổng hợp theo ngày |
| **Map / shuffle / reduce** | Map cục bộ → gom dữ liệu theo key → reduce theo key | Đếm sự kiện theo sản phẩm, group-by lớn |
| **DAG nhiều giai đoạn** | Các bước có thứ tự phụ thuộc, có thể chạy song song giữa nhánh | ETL: ingest → clean → join → aggregate |
| **Mô phỏng song song đồng bộ** | Các process trao đổi trạng thái thường xuyên/barrier | HPC, mô phỏng vật lý dùng MPI |

Trong **map/shuffle/reduce**, phép map thường có thể song song dễ dàng; **shuffle** gây I/O đĩa, truyền mạng và cần sắp xếp/phân phối lại dữ liệu. Nếu một key chiếm tỷ lệ lớn, reducer sở hữu key đó sẽ là **straggler** khiến toàn đợt phải chờ.

Các kỹ thuật giảm skew có thể gồm chia lại hot key (salting khi phép tổng hợp cho phép), gom cục bộ trước khi shuffle, broadcast bảng nhỏ khi memory đủ, chọn partition hợp lý hoặc thay thuật toán join. Phải chứng minh tính đúng của reduce sau khi chia hot key.

## 5. DAG và quản lý phụ thuộc giữa các giai đoạn

Khi một tác vụ phụ thuộc đầu ra của tác vụ khác, biểu diễn workflow bằng **directed acyclic graph (DAG)**:

~~~mermaid
flowchart LR
    A["Chốt manifest"] --> B["Đọc log"]
    A --> C["Đọc danh mục sản phẩm"]
    B --> D["Chuẩn hóa / loại lỗi"]
    C --> E["Kiểm tra phiên bản danh mục"]
    D --> F["Join & aggregate"]
    E --> F
    F --> G["Đối soát kết quả"]
    G --> H["Xuất bản phiên bản mới"]
    H --> I["Thông báo hoàn tất"]
~~~

Một DAG tốt phải nói rõ **điều kiện thành công**, **nhánh thất bại**, **timeout** và **khả năng chạy lại** của từng bước. Không nên dùng “task đã gửi lên queue” làm bằng chứng “task hoàn thành”.

### Các lựa chọn điều phối

**Fan-out/fan-in đơn giản:** orchestrator phát danh sách task theo manifest rồi chờ toàn bộ task thành công, xử lý task lỗi theo retry. Phù hợp khi task độc lập và chỉ cần bước tổng hợp cuối.

**Workflow engine với state:** phù hợp khi có nhiều bước, nhánh điều kiện, mốc phê duyệt hoặc nhiều hệ thống cần phối hợp. Orchestrator quản lý tiến độ; dữ liệu lớn vẫn nên nằm ở object storage/data lake, **không đẩy cả tập dữ liệu qua payload workflow**.

**Distributed data engine:** phù hợp cho SQL phân tán, join lớn, shuffle, group-by, checkpoint ở mức xử lý dữ liệu; engine chịu trách nhiệm phân phối task và quản lý dependency nội bộ.

**HPC/job array:** phù hợp tác vụ khoa học hoặc tính toán cần CPU/GPU/đường mạng hiệu năng cao, đôi khi yêu cầu barrier và inter-process communication thường xuyên.

Không phải công việc nào cũng phù hợp với map/reduce. Nếu các task cần truy cập cùng một cấu trúc dữ liệu có thể ghi, việc chạy song song không kiểm soát sẽ dễ gây race condition hoặc lỗi nhất quán.

## 6. Chọn compute và mô hình triển khai

| Tùy chọn compute | Phù hợp | Đánh đổi |
|---|---|---|
| **Serverless functions** | Task ngắn, độc lập, tải biến động mạnh | Giới hạn thời gian, RAM, payload, concurrency; cold start và quota |
| **Managed batch/container jobs** | Chạy theo đợt, mỗi task dài hoặc cần thư viện riêng | Cần đóng gói image, quản lý quota, timeout, dung lượng tạm |
| **Kubernetes Jobs** | Đã có đội ngũ vận hành cluster, cần kiểm soát scheduling và resource | Cần quản lý node pool, quota, image và hoạt động của cluster |
| **Managed distributed processing** | ETL/SQL phân tán, shuffle/group-by/join lớn | Overhead khởi tạo, memory/shuffle tuning, chi phí engine |
| **VM pool hoặc HPC scheduler** | Binary đặc thù, MPI, CPU/GPU chuyên dụng, kiểm soát hệ điều hành | Vận hành scheduler, capacity, image, khôi phục node |
| **Một máy đủ lớn** | Dữ liệu vừa, task không song song tốt, áp lực vận hành thấp | Điểm lỗi đơn, giới hạn mở rộng theo chiều dọc |

**CPU-bound:** Ưu tiên hiệu năng core, bộ nhớ phù hợp, giảm contention. **Memory-bound:** Kiểm tra peak memory mỗi task, kích cỡ join/hash table và cơ chế spill ra đĩa. **I/O-bound:** Theo dõi đọc/ghi và số kết nối; thêm core chưa chắc tăng throughput. **GPU-bound:** Đánh giá batch size, bộ nhớ GPU, thời gian cấp phát accelerator và truyền dữ liệu CPU↔GPU.

Khi dùng compute co giãn, phải đặt **max concurrency** dựa trên cả ngân sách, quota và sức chịu tải của hệ thống nguồn/đích. Worker ngắn hạn cần được khởi tạo từ image/version cố định, có health check, thời hạn xử lý, chính sách retry và dọn tài nguyên sau khi kết thúc.

### Hướng dẫn chọn nhanh

Nếu nhiệm vụ là **xử lý độc lập hàng triệu ảnh**: ưu tiên job array hoặc worker container điều khiển qua queue. Nếu là **join và group-by trên dữ liệu terabyte**: xem xét engine phân tán có shuffle. Nếu là **chạy mô phỏng cần giao tiếp mật độ cao giữa các node**: xem xét HPC với network latency/throughput phù hợp. Nếu xử lý rất nhỏ, đều đặn và ít phụ thuộc: một scheduled job có thể đủ, không cần dựng cluster phức tạp.

## 7. Sizing theo SLA và xác định nút thắt

Thời gian hoàn thành phụ thuộc vào **đường đi chậm nhất**: đọc dữ liệu, giải mã, biến đổi, shuffle, ghi, kiểm chứng và xuất bản.

Với lô **900 GB (hệ thập phân)** cần xử lý trong **90 phút**, tốc độ dữ liệu tối thiểu trên toàn pipeline, nếu chỉ tính một lượt dữ liệu, là:

\[
\text{Throughput tối thiểu}=\frac{900\,000\text{ MB}}{90\times60\text{ s}}\approx166{,}7\text{ MB/s}.
\]

Giả sử đo thực tế một worker xử lý được **20 MB/s** với cùng loại dữ liệu và phép biến đổi. Số worker tối thiểu theo phép chia đơn giản là:

\[
N_{\min}=\left\lceil\frac{166{,}7}{20}\right\rceil=9.
\]

Nếu chỉ tính **70% hiệu quả có thể khai thác** để dự phòng thời gian khởi tạo, task lệch tải và retry, ước tính ban đầu thành:

\[
N_{\text{dự kiến}}=\left\lceil\frac{166{,}7}{20\times0{,}7}\right\rceil=12.
\]

**12 worker chỉ là kết quả sizing sơ bộ**, không bảo đảm đạt SLA. Cần đo cả băng thông object storage, throughput database, tốc độ ghi và thời gian của các bước tuần tự. Nếu đọc nguồn chỉ đạt 100 MB/s, pipeline khó đạt 166,7 MB/s dù tăng worker. Cũng cần dự trù tài nguyên cho backfill và cạnh tranh với các batch khác.

### Luật Amdahl và hiệu suất mở rộng

Không phải toàn bộ công việc đều song song được. Nếu tỷ phần thời gian tuần tự là **f**, dùng **P** worker, tốc độ tăng lý tưởng bị giới hạn:

\[
S(P)=\frac{1}{f+(1-f)/P}.
\]

Ví dụ **10% công việc tuần tự** và **20 worker** thì mức tăng lý tưởng chỉ khoảng **6,9 lần**; tăng gấp đôi worker chưa chắc giảm tương ứng thời gian hoàn thành. Ngoài phần tuần tự, truyền mạng, shuffle, contention và điều phối còn làm kết quả thực tế thấp hơn.

### Tối ưu hóa trước khi mở rộng bừa bãi

1. **Đẩy filter/projection về gần nguồn:** chỉ đọc cột, khoảng thời gian hoặc bản ghi cần dùng.
2. **Giảm đọc lại:** tận dụng dữ liệu dạng cột, nén phù hợp, cache có giới hạn; tránh mỗi task quét toàn bộ dữ liệu.
3. **Giảm shuffle:** pre-aggregate cục bộ, chọn partition key, tối ưu join.
4. **Chống tệp quá nhỏ:** gộp tệp ở kích thước phù hợp; hạn chế overhead metadata và request.
5. **Giới hạn đồng thời theo downstream:** database, API và message broker đều có quota/connection cap.
6. **Đo straggler:** xem thời gian từng partition thay vì chỉ nhìn thời gian trung bình.

Tốc độ tăng theo số worker thường chỉ tốt đến khi chạm một trong các giới hạn về dữ liệu, tài nguyên hoặc tính tuần tự.

## 8. Tính đúng dữ liệu khi chạy đồng thời

### 8.1. Đầu vào bất biến và danh tính lần chạy

Một lần chạy nên có **run_id**, **input snapshot/manifest**, **schema version** và **mốc cắt dữ liệu** rõ ràng. Nếu danh sách tệp thay đổi trong lúc xử lý, hai task có thể nhìn thấy hai phiên bản đầu vào khác nhau.

Với dữ liệu đang phát sinh liên tục, xác định ranh giới bằng partition thời gian, snapshot hoặc offset/phiên bản nguồn. Dữ liệu đến muộn được xử lý theo chính sách backfill/correction cụ thể, không âm thầm trộn vào lô đã phát hành.

### 8.2. Retry, at-least-once và idempotency

Trong hệ thống phân tán, worker có thể hoàn thành phép ghi nhưng bị mất kết nối trước khi xác nhận; scheduler có thể chạy lại. Vì vậy, nhiều queue/workflow có **ngữ nghĩa at-least-once**, dẫn tới khả năng task được thực thi nhiều lần.

Một task **idempotent** cho cùng đầu vào và cùng định danh phải tạo ra cùng hiệu ứng cuối, kể cả khi retry. Một chiến lược thường dùng:

- Sinh **task_id** từ **run_id + partition_id + phiên bản thuật toán**.
- Ghi kết quả vào staging với định danh partition và attempt rõ ràng, tránh hai attempt ghi đè không kiểm soát.
- Xác nhận hoàn tất bằng một bản ghi trạng thái có **điều kiện/transaction** để chỉ chấp nhận một kết quả hợp lệ.
- Bước publish chỉ tham chiếu các partition đã được xác nhận và đối soát đầy đủ.
- Nếu có side effect bên ngoài (ví dụ thanh toán, email, ghi sang API), dùng **idempotency key** ở hệ thống đích hoặc cơ chế giao dịch/đối soát phù hợp.

Không nên khẳng định “exactly once” chỉ vì queue có đánh dấu đã nhận tin. **Exactly-once effect** cần được chứng minh trên toàn đường đi, bao gồm đọc, ghi, commit, retry và side effect, trong phạm vi cơ chế cụ thể.

### 8.3. Ghi staging rồi xuất bản có kiểm soát

Sơ đồ trạng thái có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> PLANNED
    PLANNED --> RUNNING
    RUNNING --> VALIDATING: các task hoàn tất
    RUNNING --> RETRYING: lỗi có thể thử lại
    RETRYING --> RUNNING
    RUNNING --> FAILED: vượt giới hạn lỗi
    VALIDATING --> PUBLISHED: kiểm tra đạt, commit thành công
    VALIDATING --> FAILED: thiếu partition hoặc đối soát sai
    PUBLISHED --> [*]
    FAILED --> [*]
~~~

Giả mã điều phối dưới đây minh họa **quy tắc**, không phải API của nhà cung cấp cụ thể:

~~~text
manifest = freeze_input(run_id, input_version, partition_plan)

for partition in manifest.partitions:
    enqueue(task_id=(run_id, partition.id), max_attempts=3)

worker(task):
    input = read_only_partition(manifest, task.partition_id)
    output = deterministic_transform(input)
    location = write_unique_staging(run_id, task.partition_id, attempt_id, output)
    checksum = validate_local_output(location)
    commit_partition_once(run_id, task.partition_id, location, checksum)

coordinator(run_id):
    wait_until_all_partitions_committed_or_job_failed()
    check_coverage_counts_checksums_and_business_invariants()
    publish_new_version_atomically_if_supported()
    mark_run_published_only_after_commit_confirmation()
~~~

Từ “atomically” ở đây đòi hỏi **cơ chế commit thực sự hỗ trợ**: transaction của database/table format, compare-and-swap cho con trỏ phiên bản, hoặc một cách publication nhất quán tương đương. Không được giả định thao tác ghi/rename nhiều object trong object storage là một transaction. Nếu đích không hỗ trợ đổi phiên bản nguyên tử, thiết kế cách người đọc chỉ truy cập phiên bản đã có **completion marker** và bảo đảm marker không được tạo sớm.

### 8.4. Checkpoint, retry và xử lý lỗi không thể tự phục hồi

| Loại lỗi | Ví dụ | Phản ứng phù hợp |
|---|---|---|
| **Tạm thời** | Timeout mạng, worker bị thu hồi, throttle | Retry có giới hạn, exponential backoff + jitter |
| **Lỗi dữ liệu cục bộ** | Dòng sai schema, object hỏng | Quarantine/quy trình data quality; tránh retry vô hạn |
| **Lỗi logic toàn cục** | Code lỗi ở mọi partition | Fail-fast, dừng phát task, sửa code rồi chạy lại có phiên bản |
| **Thiếu tài nguyên** | OOM, hết disk tạm, quota thấp | Tuning partition/concurrency, chọn memory, spill hoặc xin quota |
| **Kết quả thiếu nhất quán** | Tổng tiền không khớp, mất partition | Không publish, điều tra và chạy lại phần lỗi |

**Checkpoint** nên đủ nhỏ để hạn chế làm lại nhưng không quá thường xuyên gây I/O tốn kém. Với task dài nhiều giờ, lưu mốc đã xử lý an toàn; với task vài giây, retry toàn task thường đơn giản hơn.

## 9. Thiết kế dữ liệu, mạng và bảo mật

### Tổ chức lưu trữ dữ liệu

Một pipeline dữ liệu quy mô lớn thường tách **raw/bronze** (dữ liệu nguồn), **validated/clean** (chuẩn hóa và kiểm tra), **curated/serving** (sẵn sàng cho người dùng). Tên tầng là quy ước, điều quan trọng là biết nguồn gốc và phiên bản của mỗi kết quả.

Với dữ liệu phân tích dạng bảng, định dạng cột và partition pruning có thể giảm I/O. Với tệp multimedia hay mô phỏng, nên chọn cách chia task theo đơn vị độc lập thay vì ép vào mô hình bảng. Dữ liệu trung gian lớn có thể cần local scratch/ephemeral disk hoặc shuffle service; phải dự đoán **kích cỡ lớn nhất** khi spill.

Nếu nguồn là **OLTP**, tránh cho hàng trăm worker quét trực tiếp vào database production: cân nhắc snapshot, read replica, xuất dữ liệu sang object storage hoặc pipeline CDC, và giới hạn tốc độ lấy dữ liệu. Đánh giá tải lên storage và lag/khả năng nhất quán của replica.

### Mạng và vị trí đặt tài nguyên

- Đặt compute gần nguồn/đích dữ liệu theo region/vùng và yêu cầu residency; đo chi phí truyền dữ liệu **liên vùng, liên zone, qua Internet hoặc qua mạng hybrid**.
- Dùng subnet/private endpoint hoặc kết nối riêng khi phù hợp; hạn chế public inbound cho worker.
- Xác định băng thông tổng, số kết nối đồng thời, throughput NAT/proxy, DNS, timeout và quota API.
- Không dựa vào IP worker cố định nếu compute scale-out/scale-in; dùng service identity hoặc cơ chế kết nối đã được thiết kế.
- Kiểm tra đường đọc, đường ghi và đường điều khiển/metadata; một chiều thông có thể không đảm bảo toàn DAG chạy được.

### Bảo mật theo quyền tối thiểu

Mỗi worker chỉ cần quyền **đọc partition đầu vào, ghi staging được giao và gửi trạng thái**, không nhất thiết có quyền xóa hoặc xuất bản dữ liệu chính thức. Coordinator hoặc publisher dùng một vai trò riêng có quyền commit. Không đặt secret trong image, file cấu hình công khai hoặc nhật ký.

Dữ liệu nhạy cảm cần mã hóa khi truyền và lưu, quản lý khóa, giới hạn truy cập, chính sách retention và xóa dữ liệu tạm. Log/trace không nên ghi payload PII nguyên bản. Đối với job chạy theo nhiều tenant, cần cách ly bằng IAM, namespace, tài nguyên và giới hạn quota phù hợp. Supply chain của container/image cần được kiểm soát tương ứng mức độ rủi ro.

## 10. Triển khai, quan sát và vận hành

### Gói triển khai có thể tái lập

Mỗi run nên ghi **image digest/code version, cấu hình, schema version, input version, partition plan**. Nhờ vậy khi cần tính lại hoặc điều tra lỗi, có thể biết chính xác phiên bản nào đã tạo ra kết quả.

Pipeline CI/CD nên kiểm tra tương thích cấu hình và schema, sau đó chạy thử bằng dữ liệu mẫu đại diện. Tránh cập nhật image đang xử lý làm hai worker trong một run dùng hai phiên bản logic khác nhau. Với thay đổi lớn, tạo run/version mới và so sánh kết quả trước khi thay bản chính.

### Chỉ số cần có trên dashboard

| Nhóm | Chỉ số/quan sát | Ý nghĩa |
|---|---|---|
| **Tiến độ** | Job duration, số task xong/còn lại, ETA có độ tin cậy | Có nguy cơ trễ deadline không? |
| **Điều phối** | Queue depth, queue wait time, retry count, task timeout | Scheduler/worker có đủ năng lực? |
| **Hiệu năng** | MB/s đọc/ghi, CPU, RAM, spill disk, network, shuffle size | Tài nguyên nào là bottleneck? |
| **Phân phối tải** | Median/p95/p99 task duration, partition size, straggler count | Có skew hoặc phân vùng quá lớn? |
| **Chất lượng dữ liệu** | Số dòng nhận/xuất, duplicate, invalid row, checksum, late data | Có được phép publish? |
| **Độ tin cậy** | Tỷ lệ job thành công, số lần checkpoint/restore, thời gian phục hồi | SLO có đạt không? |
| **Chi phí** | Chi phí/run, vCPU-hour, GB processed, storage tạm, egress | Có tăng chi phí bất thường không? |

Thiết lập **run_id** và **task_id** nhất quán trong log/metric/trace để truy vết từ dashboard tới task cụ thể. Khi một worker lỗi, người vận hành phải tìm được input partition, log, attempt, code version và output staging của lần thử đó.

Cảnh báo nên dựa trên tác động: job trễ hạn, nhiều partition liên tục lỗi, kết quả sai đối soát, hoặc chi phí tăng mạnh. Chỉ cảnh báo CPU cao sẽ tạo nhiễu vì batch thường chủ đích dùng gần hết CPU trong thời gian ngắn.

### Quản lý vận hành lặp lại

- **Backfill:** cho phép chạy lại một khoảng dữ liệu quá khứ với run_id riêng; không trộn staging vào kết quả production trước khi kiểm chứng.
- **Schema evolution:** kiểm soát thêm/đổi kiểu/xóa cột, quy tắc null/default và tính tương thích với consumer.
- **Data retention:** có TTL để dọn staging, log và checkpoint sau thời gian cần cho khôi phục, điều tra và tuân thủ.
- **Graceful termination:** khi scale-in/thu hồi node, task có thể checkpoint và giải phóng lease; task chưa commit sẽ được thử lại.
- **Runbook:** ai trực, chỉ số go/no-go, cách tạm dừng queue, khôi phục dữ liệu, chạy lại một partition, phát hành lại kết quả.

## 11. Đánh đổi theo Well-Architected

| Trụ cột | Lựa chọn giúp cải thiện | Đánh đổi hoặc rủi ro cần đánh giá |
|---|---|---|
| **Operational Excellence** | DAG, image/version cố định, IaC, runbook, alert | Tăng công thiết lập ban đầu, phải duy trì workflow/metadata |
| **Security** | IAM theo task, private networking, encryption, audit | Kiểm soát chi tiết có thể làm tăng độ phức tạp vận hành |
| **Reliability** | Retry từng partition, checkpoint, multi-zone khi phù hợp | Thêm chi phí lưu trữ checkpoint, replication và thời gian xác minh |
| **Performance Efficiency** | Partition đúng, autoscaling, pre-aggregate, data locality | Tăng worker vượt ngưỡng có thể tăng shuffle/contension |
| **Cost Optimization** | Compute theo lượt chạy, quota, right-sizing, spot khi an toàn | Capacity giá thấp có thể bị thu hồi, làm tăng retry và trễ SLA |
| **Sustainability** | Tắt tài nguyên khi rảnh, tăng hiệu suất xử lý/GB | Cần đo tác động thực tế; cấu hình tối ưu giá chưa chắc tối ưu tài nguyên |

Một số xung đột điển hình:

1. **Nhiều worker hơn** có thể giảm thời gian hoàn thành nhưng tăng tổng chi phí nếu shuffle/overhead cao.
2. **Spot/preemptible** tiết kiệm chi phí nhưng phù hợp hơn với task retry được và có checkpoint; phần điều phối và bước commit có thể cần tài nguyên ổn định.
3. **Ghi mọi kết quả trung gian** giúp debug và phục hồi từng bước nhưng tăng storage, retention và bề mặt dữ liệu nhạy cảm.
4. **Đặt dữ liệu nhiều region** tăng khả năng dự phòng cho một số nhu cầu, nhưng có thể gây phí truyền, phức tạp nhất quán và vi phạm residency nếu không kiểm soát.
5. **Micro-batch thường xuyên** giảm độ trễ đầu ra nhưng tăng số lượt khởi tạo, metadata, tệp nhỏ và chi phí orchestration.

Điểm quyết định là **SLO nghiệp vụ, giới hạn bảo mật và TCO**, không phải khả năng scale tối đa trên sơ đồ.

## 12. Tình huống thực tế: xử lý log bán lẻ 900 GB mỗi đêm

### 12.1. Bối cảnh giả định

Một sàn thương mại điện tử nhận khoảng **900 GB log truy cập và sự kiện xem sản phẩm mỗi ngày** dưới dạng object trong cùng region. Bộ phận kinh doanh cần báo cáo lượt xem, tỷ lệ chuyển đổi và sản phẩm phổ biến **trong 90 phút sau khi chốt dữ liệu**. Dữ liệu có thể đến muộn, một số sự kiện bị gửi lặp, và bảng danh mục sản phẩm có phiên bản theo ngày.

Các con số dưới đây là **giả định phục vụ học kiến trúc**, không phải thông số của dịch vụ cloud cụ thể. Mục tiêu thiết kế:

- **Correctness:** mỗi sự kiện chỉ đóng góp một lần theo khóa **event_id** trong tập đầu vào đã chốt; nhận biết dữ liệu đến muộn để backfill.
- **Performance:** 95% các đợt chạy hoàn thành trong 90 phút, bao gồm kiểm chứng và publish (một ví dụ SLO cần người dùng nghiệp vụ phê duyệt).
- **Reliability:** hỏng một worker không bắt toàn bộ pipeline chạy lại; không xuất bản bộ số liệu thiếu partition.
- **Security:** trường nhận dạng người dùng được giảm thiểu/ẩn danh theo chính sách; worker không truy cập trực tiếp database giao dịch.
- **Cost:** compute được tắt sau mỗi đợt; có ngân sách/run và cảnh báo chi phí bất thường.

### 12.2. Đề xuất kiến trúc

1. **Chốt input:** một job tạo manifest của các object thuộc ngày D và schema version; xác định cutoff và chính sách dữ liệu đến muộn.
2. **Fan-out chuẩn hóa:** mỗi task đọc một nhóm object/partition, kiểm tra schema, chuẩn hóa timestamp, giữ trường cần thiết và lưu dữ liệu tạm.
3. **Deduplicate:** phân phối theo event_id hoặc dùng phương pháp tương đương bảo đảm các bản ghi cùng event_id được so sánh đúng; quy tắc chọn bản ghi hợp lệ phải xác định (ví dụ bản ghi có version cao nhất).
4. **Join danh mục:** sử dụng ảnh chụp danh mục phiên bản ngày D, chọn broadcast join nếu bảng đủ nhỏ và đo memory; nếu không, join phân tán.
5. **Aggregate:** tính nhóm theo ngày và product_id, áp dụng pre-aggregation nếu phép tổng hợp cho phép. Với tỷ lệ chuyển đổi, lưu **tử số và mẫu số** trước khi tính tỷ lệ để tránh “trung bình của các tỷ lệ” sai.
6. **Validate:** kiểm tra partition đầy đủ, số dòng vào/ra theo quy tắc lọc, tổng event hợp lệ, tính duy nhất event_id, kiểm tra giá trị bất thường và so sánh với khoảng lịch sử.
7. **Publish:** ghi phiên bản kết quả mới, đổi con trỏ/commit bằng cơ chế nhất quán được nền tảng hỗ trợ; chỉ thông báo dashboard sau commit.
8. **Backfill và dọn dẹp:** sự kiện đến muộn được đưa vào run correction/backfill có kiểm soát; staging cũ xóa sau retention.

~~~mermaid
flowchart TB
    RAW[("Raw objects ngày D")] --> MAN["Manifest + cutoff"]
    DIM[("Danh mục phiên bản D")] --> JOIN["Join theo product_id"]
    MAN --> N["Đọc / normalize / validate"]
    N --> DUP["Deduplicate theo event_id"]
    DUP --> JOIN
    JOIN --> AGG["Aggregate theo product_id / ngày"]
    AGG --> QA["Đối soát và kiểm tra chất lượng"]
    QA -- "Pass" --> PUB[("Publish bảng báo cáo phiên bản mới")]
    QA -- "Fail" --> ERR["Chặn publish + cảnh báo"]
    PUB --> BI["Dashboard / API"]
~~~

### 12.3. Dự toán công suất

Theo mục 7, thông lượng lý thuyết cần đạt là **166,7 MB/s**, ước tính **12 worker** nếu benchmark **20 MB/s/worker** và chỉ dự kiến tận dụng **70% hiệu quả**. Tuy nhiên, các bước **shuffle, join, validation và publish** tiêu thụ thêm thời gian, vì vậy kết quả sizing phải được đánh giá với pipeline thật và tải đỉnh; có thể cần tài nguyên dự phòng hoặc tối ưu thuật toán.

Giả sử sau benchmark nhóm quyết định dùng **14 worker**, mỗi worker có đơn giá hiệu dụng **0,25 đơn vị tiền/giờ** và chạy **1,5 giờ**. Khi ấy **chi phí compute giả định** là:

\[
14\times1{,}5\times0{,}25 = 5{,}25
\]

đơn vị tiền cho một đợt. Đây **không phải TCO**: còn phải tính orchestration, lưu trữ/raw/staging, request, shuffle/network, logging, phí truyền liên vùng, retry và chi phí đội ngũ vận hành. Tổng chi phí còn phụ thuộc vào việc 14 worker có thực sự đạt được deadline hay không.

### 12.4. Thử nghiệm trước production

| Kịch bản | Cách thử | Điều kiện nghiệm thu |
|---|---|---|
| Khối lượng đỉnh | Replay tập dữ liệu đại diện 900 GB và skew thực tế | Job đạt SLO end-to-end với mức tài nguyên dự kiến |
| Worker bị thu hồi | Hủy một worker khi đang xử lý partition | Chỉ retry phần chưa commit, không mất/đếm trùng |
| Task xác nhận thất bại | Giả lập ghi staging xong nhưng mất ACK | Retry không làm duplicate result |
| Tệp sai schema | Chèn dữ liệu hỏng vào một partition | Quarantine hoặc fail theo chính sách, không publish âm thầm |
| Hot key | Tạo product_id có nhiều sự kiện bất thường | Đo skew; xử lý mà vẫn giữ đúng tổng số |
| Thiếu phân vùng | Cố tình không hoàn thành một task | Coordinator chặn publish, gửi cảnh báo |
| Dữ liệu đến muộn | Phát sinh sự kiện ngày D sau cutoff | Áp dụng correction/backfill đúng phiên bản |
| Chi phí vượt dự kiến | Tăng retry hoặc chạy backfill đồng thời | Quota/budget/alert có hiệu lực, không gây quá tải nguồn |

Chỉ được ghi “đạt SLA” sau khi kết quả đo thực tế đạt mục tiêu, bao gồm cả failover/retry. Các con số 12 hoặc 14 worker không thay được benchmark.

## 13. Bài tập thực hành thiết kế

Một công ty có ba loại workload:

**A.** Mỗi tối chuyển đổi 50.000 tệp PDF độc lập sang ảnh; mỗi tệp mất 5–40 giây và có thể thử lại. **B.** Tổng hợp 2 TB dữ liệu bán hàng với phép join lớn giữa bảng giao dịch và danh mục; kết quả cần trước 7 giờ sáng. **C.** Chạy mô phỏng khoa học trên 64 process phải trao đổi thông tin sau mỗi bước tính toán.

Hãy trả lời:

1. Chọn mô hình compute ưu tiên cho **A, B, C**: serverless, batch containers, distributed data engine, VM/HPC hoặc phương án khác. Nêu lý do từ **tính phụ thuộc, tài nguyên và thời hạn**.
2. Thiết kế **manifest, partition key và idempotency key** cho A hoặc B. Phải chỉ ra cách phát hiện partition thiếu và chống duplicate do retry.
3. Phác họa DAG gồm **ít nhất bốn giai đoạn** cho B; ghi điều kiện nghiệm thu trước publish.
4. Nếu B bị chậm dù số worker tăng, cần kiểm tra những metric nào để tìm bottleneck?
5. Đưa ra một phương án **cost optimization** có thể làm tăng rủi ro trễ SLA, và cách giảm rủi ro đó.

**Gợi ý đối chiếu:**

- **A:** phù hợp fan-out/fan-in bằng batch container hoặc serverless nếu thời hạn chạy, kích cỡ tệp và giới hạn dịch vụ cho phép; mỗi input file có task_id cố định và output versioned.
- **B:** thường cần distributed data engine cho join/shuffle; kiểm tra skew, kích thước dimension, memory, spill, I/O, queue wait và quota. Có thể gộp/tiền tổng hợp một số trường trước khi shuffle.
- **C:** thiên về HPC/VM có kết nối mạng phù hợp cho process trao đổi thường xuyên; chia các process thành task độc lập theo queue có thể không đáp ứng barrier/latency.
- Tài nguyên spot/preemptible có thể giảm chi phí của A/B nếu xử lý **idempotent, checkpoint được** và có đủ quỹ thời gian dự phòng; không nên đưa cả phần publish quan trọng lên tài nguyên dễ bị thu hồi mà thiếu cơ chế dự phòng.

## 14. Danh sách kiểm tra khi duyệt kiến trúc batch song song

- [ ] Có chỉ tiêu **khối lượng, SLA completion, độ chính xác, phục hồi, ngân sách** và owner rõ ràng.
- [ ] Đầu vào được **chốt phiên bản** và phân vùng bảo đảm đầy đủ, không chồng lấn.
- [ ] Đã lựa chọn hình thức parallelism tương ứng với tính độc lập, nhu cầu shuffle và trao đổi dữ liệu.
- [ ] Compute được sizing bằng **benchmark end-to-end**; giới hạn concurrency và quota có cơ sở.
- [ ] Retry có giới hạn; task có idempotency; checkpoint được kiểm chứng khi phù hợp.
- [ ] Staging và publish được tách rõ; kết quả chỉ hiển thị sau đối soát và commit hợp lệ.
- [ ] Data layout, network, IAM, encryption, secret và data retention đã được thiết kế.
- [ ] Log/metric/trace liên kết được theo run_id và task_id; có cảnh báo trễ hạn, lỗi đối soát và chi phí.
- [ ] Đã diễn tập worker failure, duplicate, skew, thiếu partition và backfill.
- [ ] Tài nguyên ngừng khi không có việc; TCO đã tính storage, network, retries và vận hành.

**Nguyên tắc cốt lõi:** Batch quy mô lớn không phải “chia càng nhiều worker càng tốt”. Thiết kế tốt bắt đầu từ **đầu vào ổn định, ranh giới công việc đúng, tốc độ đo được và cơ chế xuất bản kết quả an toàn**; sau đó mới lựa chọn hạ tầng cloud đáp ứng mục tiêu nghiệp vụ và các đánh đổi Well-Architected.
