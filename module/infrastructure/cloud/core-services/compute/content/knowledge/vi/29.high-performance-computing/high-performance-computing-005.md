# Shared filesystem, dữ liệu đầu vào và nút thắt I/O của cụm

Trong cụm điện toán hiệu năng cao (HPC), nhiều node tính toán thường cần đọc cùng bộ dữ liệu, ghi kết quả và lưu checkpoint trong khi các job chạy song song. Shared filesystem cung cấp một không gian tệp dùng chung để các node truy cập dữ liệu theo cùng đường dẫn. Cách tổ chức này thuận tiện cho ứng dụng cần ngữ nghĩa tệp POSIX, nhưng cũng tạo ra một tài nguyên dùng chung: nếu quá nhiều node cùng đọc, ghi hoặc tra cứu metadata, lưu trữ và mạng có thể trở thành nút thắt dù CPU vẫn còn nhàn rỗi.

Hiệu năng I/O của cụm phụ thuộc vào nhiều yếu tố cùng lúc: băng thông tổng, IOPS, độ trễ, tốc độ xử lý metadata, kích thước tệp, cách phân bố dữ liệu, số client và kiểu truy cập của ứng dụng. Vì vậy, thiết kế lưu trữ HPC cần bắt đầu từ mẫu truy cập thực tế của workload, sau đó chọn shared filesystem, parallel filesystem, object storage hoặc đĩa cục bộ phù hợp.

Sau bài học, bạn có thể:

- Phân biệt shared filesystem với parallel filesystem và object storage.
- Chọn cách đưa dữ liệu đầu vào đến các node tính toán mà không tạo tải I/O không cần thiết.
- Nhận diện nút thắt về metadata, băng thông, IOPS, độ trễ và mạng.
- Thiết kế vùng scratch, checkpoint và đầu ra cho workload chạy nhiều node.
- Đo và xác minh hiệu năng filesystem trước khi tăng quy mô cụm.

## 1. Shared filesystem trong cụm HPC

Shared filesystem cho phép nhiều node mount cùng một hệ thống tệp và nhìn thấy cùng namespace, thư mục và tệp. Ví dụ, node đăng nhập, node điều phối và các node tính toán có thể cùng truy cập `/shared/project-a`. Người dùng có thể chuẩn bị dữ liệu một lần, gửi job lên scheduler và để các node đọc tệp từ vị trí thống nhất.

Các dịch vụ thường gặp trong cloud gồm:

- **NFS managed file storage:** chẳng hạn Amazon EFS, Google Cloud Filestore hoặc Azure NetApp Files. NFS phù hợp với nhiều workload cần chia sẻ thư mục, home directory, script, thư viện và dữ liệu có mức song song vừa phải. Cần kiểm tra throughput, IOPS, latency, giới hạn client và đặc tính của từng tier.
- **Parallel filesystem:** chẳng hạn Amazon FSx for Lustre hoặc Azure Managed Lustre. Các hệ thống này được thiết kế cho truy cập song song quy mô lớn, thường phân phối dữ liệu qua nhiều thành phần lưu trữ và hỗ trợ các workload đọc/ghi thông lượng cao. Cần cấu hình client, mạng, stripe và dung lượng theo hướng dẫn của dịch vụ.
- **Object storage:** chẳng hạn Amazon S3, Azure Blob Storage hoặc Google Cloud Storage. Object storage có khả năng mở rộng và phù hợp lưu dataset, archive, kết quả dài hạn và kho dữ liệu dùng chung. Nó không mặc nhiên có ngữ nghĩa POSIX như một filesystem được mount; ứng dụng thường truy cập qua API hoặc công cụ đồng bộ/staging.

Shared filesystem và parallel filesystem không hoàn toàn đồng nghĩa. Một hệ thống NFS có thể được nhiều node chia sẻ nhưng thông lượng hoặc metadata service có giới hạn tập trung. Parallel filesystem được thiết kế để phân phối dữ liệu và phục vụ nhiều client đồng thời. Tên sản phẩm không đủ để kết luận hiệu năng; cần xem cấu hình, quota, giới hạn dịch vụ và phép đo trên workload thật.

### Các thành phần của đường I/O

Một thao tác đọc từ node tính toán có thể đi qua các lớp sau:

1. Ứng dụng gọi `open`, `stat`, `read` hoặc `write` trên đường dẫn được mount.
2. Kernel và filesystem client xử lý cache, metadata và yêu cầu I/O.
3. Yêu cầu đi qua mạng cụm đến dịch vụ metadata hoặc máy chủ filesystem.
4. Dịch vụ lưu trữ xác định vị trí dữ liệu, đọc/ghi các khối và trả kết quả.
5. Dữ liệu quay lại client, có thể được cache trong bộ nhớ của node.

Ở filesystem phân tán, metadata và nội dung dữ liệu có thể được phục vụ bởi các thành phần khác nhau. Metadata bao gồm tên tệp, thư mục, quyền, kích thước, timestamp và thông tin phân bố dữ liệu. Một workload tạo hàng triệu tệp nhỏ có thể làm metadata service quá tải dù tổng số byte cần đọc không lớn. Ngược lại, một job đọc tuần tự các tệp lớn có thể chủ yếu bị giới hạn bởi băng thông dữ liệu.

## 2. Chọn filesystem theo mẫu truy cập

Trước khi chọn dịch vụ, hãy mô tả workload theo các câu hỏi:

- Nhiều node đọc cùng một tệp hay mỗi node đọc một shard riêng?
- Tệp chủ yếu lớn và đọc tuần tự, hay rất nhiều tệp nhỏ và thao tác mở/đóng liên tục?
- Các node chỉ đọc hay cùng ghi vào một tệp?
- Có cần khóa tệp, rename nguyên tử, quyền POSIX hoặc thư mục dùng chung không?
- Có bao nhiêu node truy cập đồng thời, và dữ liệu cần đạt tổng throughput bao nhiêu?
- Dữ liệu là input bất biến, scratch tạm thời, checkpoint hay output cần lưu lâu dài?

| Mẫu workload | Hướng lưu trữ thường phù hợp | Điều cần kiểm tra |
|---|---|---|
| Home directory, script, cấu hình và dữ liệu dùng chung dung lượng vừa | NFS managed file storage | Metadata latency, quota, số client, quyền và throughput |
| Nhiều node đọc/ghi các tệp lớn song song | Parallel filesystem | Aggregate bandwidth, stripe layout, client tuning và network throughput |
| Dataset lớn, ít thay đổi, dùng cho nhiều lần chạy | Object storage làm kho chuẩn; stage sang filesystem hoặc local scratch khi chạy | Thời gian tải, chi phí request/egress, tính nhất quán của manifest và phiên bản dữ liệu |
| Tệp tạm, trung gian hoặc scratch riêng từng node | Local NVMe/SSD hoặc instance storage | Dữ liệu có thể mất khi node dừng; phải có bước stage-in/stage-out |
| Checkpoint cần khôi phục sau sự cố | Shared/parallel filesystem hoặc object storage theo thiết kế checkpoint | Tần suất ghi, kích thước checkpoint, tính toàn vẹn và thời gian phục hồi |

Một cụm có thể dùng nhiều tầng lưu trữ cùng lúc: object storage làm kho dữ liệu chuẩn, parallel filesystem làm vùng làm việc tốc độ cao, local NVMe làm scratch gần CPU và shared NFS chứa home directory hoặc file cấu hình. Phân tầng như vậy giúp mỗi loại dữ liệu đi đến nơi phù hợp với thời gian sống và mẫu truy cập của nó.

## 3. Đưa dữ liệu đầu vào đến node tính toán

Đưa input đến cụm là một phần của thiết kế hiệu năng. Nếu mỗi node tự tải lại toàn bộ dataset từ object storage khi job bắt đầu, hàng trăm node có thể đồng loạt tạo request và lưu lượng lớn. Hiện tượng này thường gọi là *thundering herd*. Nó làm tăng thời gian khởi động job, số request, chi phí truyền dữ liệu và tải lên mạng hoặc dịch vụ lưu trữ.

Một quy trình staging có kiểm soát thường gồm:

1. Đặt dataset gốc trong object storage hoặc filesystem dùng chung có quản lý phiên bản.
2. Tạo manifest ghi rõ tên, kích thước, checksum và phiên bản của từng phần dữ liệu.
3. Chia dataset thành shard theo cách phân vùng của thuật toán để mỗi node chỉ tải phần cần dùng.
4. Nếu nhiều node cần cùng dữ liệu, stage một lần vào shared/parallel filesystem hoặc dùng cache có kiểm soát thay vì tải trùng lặp.
5. Với tệp trung gian được đọc nhiều lần trong một node, sao chép sang local SSD/NVMe nếu dung lượng và thời gian tải cho phép.
6. Sau khi job hoàn tất, chuyển kết quả cần giữ lâu dài về vùng lưu trữ bền vững và dọn scratch tạm theo chính sách.

### Ví dụ: stage shard input vào scratch của từng node

Với job Slurm, một số môi trường cấp thư mục tạm qua biến `SLURM_TMPDIR`. Nếu dataset đã được chia thành shard trước, mỗi task có thể giải nén shard tương ứng lên scratch cục bộ của node, chạy phần tính toán được giao và ghi kết quả vào một thư mục riêng:

```bash
#!/bin/bash
#SBATCH --job-name=matrix-run
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=1

set -euo pipefail

srun bash -c '
  set -euo pipefail
  WORKDIR="${SLURM_TMPDIR:-/tmp}/matrix-${SLURM_JOB_ID}-${SLURM_PROCID}"
  SHARD="/shared/datasets/matrix-case-07/node-${SLURM_PROCID}.tar"
  mkdir -p "$WORKDIR/input" "$WORKDIR/output"
  test -f "$SHARD"
  tar -xf "$SHARD" -C "$WORKDIR/input"

  ./solver --input "$WORKDIR/input" --output "$WORKDIR/output"

  RESULT_DIR="/shared/results/${SLURM_JOB_ID}/rank-${SLURM_PROCID}"
  mkdir -p "$RESULT_DIR"
  cp -a "$WORKDIR/output/." "$RESULT_DIR/"
'
```

Ví dụ giả định mỗi node có một task, `SLURM_PROCID` là chỉ số task duy nhất và các shard tương ứng đã được chuẩn bị trên shared filesystem. `srun` chạy đoạn staging trên từng node nên mỗi task dùng scratch cục bộ của chính node đó; đầu ra cũng được ghi vào thư mục riêng theo rank để tránh ghi đè. Với ứng dụng MPI có nhiều rank trên mỗi node, nên stage một lần cho mỗi node bằng job prolog, bước chuẩn bị dữ liệu hoặc cơ chế node-local staging của scheduler, thay vì giải nén lại cùng shard cho mọi rank. Hãy kiểm tra biến scratch, quyền ghi, dung lượng và cách scheduler phân phối task trong môi trường thực tế.

Nếu dataset gồm hàng triệu tệp nhỏ, đóng gói thành archive hoặc định dạng container dữ liệu có thể giảm số thao tác metadata khi chuyển dữ liệu. Tuy nhiên, đóng gói cũng tiêu tốn CPU và cần thêm không gian tạm; hãy đo tổng thời gian stage, giải nén và đọc dữ liệu để quyết định. Với dữ liệu có thể đọc trực tiếp theo vùng, định dạng phân mảnh như HDF5, NetCDF hoặc Zarr có thể giúp phân phối phần dữ liệu cần thiết, nhưng phải cấu hình chunk/shard phù hợp với mẫu truy cập của ứng dụng.

## 4. Nhận diện các nút thắt I/O

Không phải mọi vấn đề I/O đều là thiếu băng thông. Một job có thể chậm vì nhiều thao tác metadata, nhiều request nhỏ, độ trễ mạng, contention khi nhiều node cùng ghi hoặc cấu hình client không phù hợp.

### Băng thông tổng và băng thông mỗi node

Băng thông tổng là lượng dữ liệu filesystem phục vụ cho toàn cụm trong một giây. Băng thông mỗi node là phần mà một node thực nhận. Nếu filesystem cung cấp 20 GB/s cho cụm 100 node, phép chia đều lý tưởng là 200 MB/s mỗi node; thực tế còn phụ thuộc phân bố dữ liệu, mạng, client và các job khác. Thêm node không bảo đảm tăng tốc tuyến tính nếu filesystem hoặc network đã đạt trần.

### IOPS và kích thước I/O

IOPS là số thao tác đọc/ghi mỗi giây. Với cùng băng thông, nhiều thao tác nhỏ có thể tiêu tốn nhiều IOPS và chi phí giao thức hơn một số thao tác lớn. Ví dụ, đọc 1 triệu tệp 4 KB có thể chậm hơn nhiều so với đọc một tệp 4 GB tuần tự, dù tổng số byte tương đương. Gộp tệp, tăng kích thước buffer hoặc đọc theo block lớn có thể cải thiện hiệu năng nếu ứng dụng cho phép.

### Metadata và thư mục lớn

Các thao tác `stat`, `open`, `close`, `mkdir`, `rename` và liệt kê thư mục đều tạo tải metadata. Một job khởi chạy hàng nghìn process, mỗi process quét cùng thư mục có hàng triệu tệp, có thể làm metadata service nghẽn trước khi truyền dữ liệu bắt đầu. Phân chia thư mục, tạo manifest, giảm số lần quét, cache metadata hợp lý và tránh mở cùng một tập tệp từ mọi rank có thể giảm tải.

### Độ trễ, contention và ghi đồng thời

Các ứng dụng nhạy với độ trễ có thể bị ảnh hưởng ngay cả khi throughput tổng còn dư. Nhiều node ghi vào cùng một tệp có thể cần khóa hoặc đồng bộ, gây contention và làm giảm khả năng song song. Khi có thể, mỗi rank hoặc node nên ghi ra tệp riêng, sau đó hợp nhất bằng một bước cuối. Nếu bắt buộc ghi chung, dùng định dạng và thư viện hỗ trợ parallel I/O như MPI-IO hoặc HDF5 parallel, đồng thời xác minh filesystem hỗ trợ đúng chế độ truy cập.

### Network và vị trí dữ liệu

Filesystem từ xa phụ thuộc băng thông và độ trễ mạng giữa node với storage. Traffic I/O có thể cạnh tranh với MPI communication nếu dùng chung hạ tầng mạng. Kiểm tra loại instance, network bandwidth, placement, đường đi qua subnet và giới hạn phía dịch vụ. Nếu dữ liệu được đọc lặp lại, cache gần compute hoặc local scratch có thể giảm lưu lượng từ shared storage.

## 5. Tổ chức dữ liệu cho đọc, ghi và checkpoint

### Input chủ yếu đọc

Dataset đầu vào thường bất biến trong suốt một lần chạy. Có thể chuẩn bị dữ liệu một lần, xác minh checksum rồi mount read-only hoặc stage vào cache. Phân vùng dữ liệu sao cho mỗi node đọc phần riêng giúp giảm truy cập trùng lặp. Nếu tất cả node cần cùng một tệp lớn, parallel filesystem hoặc cơ chế cache phân tán có thể phù hợp hơn việc mỗi node tải một bản riêng.

### Output và tệp tạm

Không nên để mọi process ghi vào cùng một log hoặc tệp CSV. Mỗi rank có thể ghi tệp riêng theo rank hoặc shard; sau job, một bước tổng hợp sắp xếp và hợp nhất kết quả. Đặt output tạm trên scratch để tránh làm chậm filesystem dùng chung cho các job khác, sau đó chỉ chuyển dữ liệu cần lưu về storage bền vững.

### Checkpoint

Checkpoint lưu trạng thái tính toán để job có thể tiếp tục sau thời gian chờ, lỗi node hoặc giới hạn thời gian chạy. Nếu checkpoint quá thường xuyên, việc ghi dữ liệu có thể chiếm phần lớn thời gian tính toán. Nếu checkpoint quá thưa, sự cố có thể làm mất nhiều giờ xử lý. Hãy chọn chu kỳ dựa trên thời gian tạo checkpoint, xác suất gián đoạn, thời gian tính toán và RPO mong muốn.

Với checkpoint lớn, có thể ghi song song ra nhiều tệp hoặc dùng thư viện checkpoint hỗ trợ MPI. Tránh để mọi rank đồng loạt ghi một tệp chung theo cách tuần tự. Cần ghi metadata cho checkpoint, xác minh kích thước/checksum và chỉ đánh dấu checkpoint hoàn tất sau khi mọi phần đã được ghi bền vững. Dọn checkpoint cũ theo chính sách giữ phiên bản, nhưng luôn giữ đủ điểm khôi phục đã cam kết.

## 6. Ví dụ lựa chọn dịch vụ lưu trữ cloud

| Nhu cầu | Ví dụ dịch vụ | Cách sử dụng và lưu ý |
|---|---|---|
| Chia sẻ thư mục POSIX cho nhiều VM | Amazon EFS, Google Cloud Filestore, Azure NetApp Files | Mount vào node; theo dõi throughput, IOPS, metadata latency và số client |
| I/O song song thông lượng cao cho HPC | Amazon FSx for Lustre, Azure Managed Lustre | Dùng làm scratch hoặc filesystem làm việc; thiết kế stripe, client và network theo workload |
| Dataset chuẩn và archive dung lượng lớn | Amazon S3, Azure Blob Storage, Google Cloud Storage | Quản lý phiên bản/manifest; stage phần cần thiết vào filesystem hoặc local scratch khi chạy |
| Dữ liệu trung gian tốc độ cao, vòng đời ngắn | Local NVMe/SSD của node | Tận dụng độ trễ thấp; dữ liệu có thể mất khi node bị thu hồi hoặc dừng |

Ví dụ, một cụm GPU chạy mô phỏng có thể lưu dataset chuẩn trong object storage, liên kết hoặc stage dữ liệu sang FSx for Lustre, rồi để các node tính toán đọc song song. Các tệp tạm và shard trung gian được đặt trên local NVMe. Checkpoint quan trọng được ghi về filesystem dùng chung hoặc object storage sau khi hoàn tất. Thiết kế này giảm việc mọi GPU node truy cập object storage trực tiếp cho từng thao tác nhỏ.

Với NFS managed file storage, hãy xác nhận số lượng client, throughput mode, hiệu năng theo kích thước workload và hành vi khi nhiều node quét thư mục cùng lúc. Với parallel filesystem, hãy xem hướng dẫn về stripe count/size, dung lượng metadata, cách mount client và liên kết object storage. Không thay đổi stripe hoặc mount option trên cụm production khi chưa thử nghiệm với nhà cung cấp và workload đại diện.

## 7. Đo hiệu năng và xác minh trên cụm

Đo theo từng lớp để tìm đúng điểm nghẽn. Bắt đầu bằng phép đo baseline trên một node, sau đó tăng số node theo các mức cố định. So sánh throughput tổng và throughput mỗi node; nếu tổng throughput không tăng khi số node tăng, filesystem, network hoặc metadata có thể đã đạt giới hạn.

Một số lệnh kiểm tra trên Linux:

```bash
# Xem filesystem và kiểu mount
df -hT /shared
findmnt /shared

# Theo dõi thiết bị block cục bộ
iostat -xz 1

# Với mount NFS, nếu công cụ có sẵn
nfsiostat 1

# Với client Lustre, xem dung lượng và stripe layout
lfs df -h /shared
lfs getstripe /shared/dataset.bin
```

Các lệnh Lustre chỉ dùng được trên client Lustre và tùy phiên bản/cấu hình. `iostat` phản ánh thiết bị block cục bộ, không mô tả đầy đủ hiệu năng của một filesystem mạng; cần kết hợp metric client, network và dịch vụ lưu trữ. `nfsiostat` cung cấp số liệu NFS nếu gói công cụ phù hợp đã được cài đặt.

Để đo throughput, IOPS và latency có kiểm soát, có thể dùng `fio` trên một thư mục benchmark riêng, không dùng dữ liệu production:

```bash
mkdir -p /shared/benchmark/$USER

# Tạo trước tệp thử nghiệm trong thư mục benchmark riêng.
fio --name=prepare \
  --directory=/shared/benchmark/$USER \
  --filename=fio-test-file \
  --size=4G \
  --rw=write \
  --bs=1M \
  --numjobs=1 \
  --group_reporting

# Đo đọc tuần tự trên tệp vừa tạo.
fio --name=seq-read \
  --directory=/shared/benchmark/$USER \
  --filename=fio-test-file \
  --size=4G \
  --rw=read \
  --bs=1M \
  --numjobs=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

Ví dụ này đo baseline tuần tự bằng một job. Khi kiểm tra I/O song song, tăng số job hoặc chạy nhiều client với tệp riêng; nếu dùng `iodepth`, chọn `ioengine` hỗ trợ bất đồng bộ và xác minh filesystem hỗ trợ chế độ I/O đã chọn. Chọn `--size` và thời gian đủ nhỏ để phép đo không làm ảnh hưởng người dùng khác. Lệnh chuẩn bị ghi đè tệp `fio-test-file`, vì vậy chỉ dùng tên tệp mới trong thư mục benchmark được cấp riêng; không chạy ghi ngẫu nhiên trên mount chứa dữ liệu thật. Ghi nhận cả throughput, IOPS, latency trung bình và percentile cao, không chỉ một con số MB/s.

Khi đo nhiều node, dùng cùng kích thước dữ liệu và cùng thời gian chạy, tăng dần số client, đồng thời theo dõi metric từ phía storage. Tránh cho mọi node ghi cùng một filename. Mỗi node hoặc job cần file riêng để không tạo xung đột và để phép đo phản ánh đúng mức song song dự kiến.

### Cách đọc kết quả

- Throughput tăng gần tuyến tính theo số node: filesystem còn khả năng mở rộng ở dải tải đã thử.
- Throughput tổng đứng yên nhưng CPU node còn thấp: kiểm tra giới hạn storage, network hoặc quota.
- IOPS cao, throughput thấp và latency tăng: workload có thể gồm nhiều I/O nhỏ hoặc truy cập ngẫu nhiên.
- Thời gian `open`/`stat` cao, nhưng đọc tuần tự nhanh: điều tra metadata, số lượng tệp và cấu trúc thư mục.
- Một node chậm hơn nhiều node khác: kiểm tra network path, placement, mount, CPU steal và vị trí shard.
- Job chạy nhanh lúc đầu rồi chậm: kiểm tra burst credit/quota nếu dịch vụ có áp dụng, cache, contention và tải từ job khác.

## 8. Các lỗi thiết kế thường gặp

- **Mọi node cùng tải toàn bộ dataset:** tạo burst lên object storage và kéo dài thời gian khởi động. Dùng manifest, shard, cache hoặc staging một lần.
- **Đặt hàng triệu tệp nhỏ trong một thư mục:** làm metadata và thao tác liệt kê chậm. Chia thư mục theo shard hoặc đóng gói dữ liệu.
- **Mọi rank ghi vào một tệp chung:** gây khóa, đồng bộ và contention. Dùng tệp theo rank/shard hoặc parallel I/O đúng chuẩn.
- **Dùng shared filesystem làm scratch cho mọi thứ:** tệp tạm và log gây cạnh tranh với input/output quan trọng. Chuyển dữ liệu trung gian sang local scratch khi phù hợp.
- **Không tính dung lượng checkpoint:** job có thể hết dung lượng hoặc làm filesystem đầy đúng lúc cần phục hồi. Ước tính dung lượng, chu kỳ và chính sách retention.
- **Đo một node rồi suy ra hiệu năng toàn cụm:** bỏ qua contention, network và metadata khi tăng số client. Thử tải theo quy mô tăng dần.
- **Chỉ nhìn CPU utilization:** CPU thấp có thể là dấu hiệu process đang chờ I/O. Theo dõi thời gian chờ, throughput, latency và hàng đợi I/O.

## Checklist thiết kế I/O cho cụm

- [ ] Đã phân loại dữ liệu thành input, scratch, checkpoint, output và archive.
- [ ] Đã xác định mẫu truy cập: tuần tự/ngẫu nhiên, tệp lớn/nhỏ, đọc/ghi và số node đồng thời.
- [ ] Đã chọn shared filesystem, parallel filesystem, object storage hoặc local NVMe theo từng loại dữ liệu.
- [ ] Đã có manifest, phiên bản và checksum cho dataset đầu vào.
- [ ] Đã tránh tải trùng dữ liệu và có kế hoạch staging/sharding rõ ràng.
- [ ] Đã tách dữ liệu tạm khỏi dữ liệu cần lưu lâu dài.
- [ ] Đã thiết kế output và checkpoint để giảm ghi đồng thời vào một tệp.
- [ ] Đã kiểm tra dung lượng, quota, metadata, băng thông, IOPS và network.
- [ ] Đã benchmark từ một node đến quy mô nhiều node bằng dữ liệu đại diện.
- [ ] Đã có cảnh báo cho filesystem gần đầy, latency tăng, throughput giảm và backlog I/O.
- [ ] Đã xác minh quy trình stage-out, checksum, khôi phục checkpoint và dọn scratch.

Thiết kế I/O tốt giúp các node dành phần lớn thời gian cho tính toán thay vì chờ dữ liệu. Hãy chọn tầng lưu trữ theo mẫu truy cập, phân phối input có chủ đích, tách scratch khỏi dữ liệu bền vững và benchmark ở quy mô cụm thực tế trước khi đưa workload lớn vào vận hành.
