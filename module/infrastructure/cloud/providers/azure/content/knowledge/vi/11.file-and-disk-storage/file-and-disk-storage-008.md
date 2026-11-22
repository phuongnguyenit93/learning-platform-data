# IOPS, throughput, host cache và disk bursting

> **Chương:** Lưu trữ tệp và đĩa  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **IOPS, throughput, latency, queue depth** và kích thước mỗi thao tác I/O.
2. Tính nhu cầu hiệu năng cho database, log, backup và ETL từ số liệu workload.
3. Nhận diện các giới hạn độc lập của **managed disk**, **Azure VM** và ứng dụng.
4. Chọn loại Azure Managed Disk phù hợp theo dung lượng, hiệu năng cần duy trì và độ trễ.
5. Phân biệt các chế độ **host caching** `None`, `ReadOnly`, `ReadWrite` và các nguy cơ với dữ liệu cần bền vững.
6. Hiểu **credit-based disk bursting** và **on-demand bursting**, điều kiện sử dụng và chi phí.
7. Thu thập chứng cứ bằng Azure CLI, Azure Monitor và công cụ đo I/O trong hệ điều hành để chẩn đoán nghẽn.

## 1. Bối cảnh: cùng dung lượng nhưng đĩa chạy khác nhau

Một công ty dùng Azure VM để chạy ứng dụng xử lý đơn hàng. Trên VM có ba loại dữ liệu:

- **Database**: truy cập ngẫu nhiên các trang dữ liệu nhỏ, yêu cầu hàng nghìn thao tác mỗi giây.
- **Transaction log**: ghi tuần tự, nhạy với độ trễ và tính bền vững của mỗi lần ghi.
- **Backup/batch export**: truyền các khối dữ liệu lớn trong một khoảng thời gian dài.

Nếu chỉ nhìn dung lượng, cả ba có thể dùng đĩa 1 TiB. Tuy nhiên hiệu năng cần thiết hoàn toàn khác nhau: database dễ bị giới hạn bởi **IOPS và latency**, còn backup thường bị giới hạn bởi **throughput**.

Trên Azure, đĩa được gắn vào VM theo mô hình Azure Managed Disks. Tốc độ thực tế phụ thuộc đồng thời vào loại đĩa, cấu hình provisioned performance, giới hạn của VM, cache và cách ứng dụng phát I/O. Có trường hợp đĩa công bố 10.000 IOPS nhưng VM chỉ cho phép ít hơn; có trường hợp benchmark ngắn đạt hiệu năng cao nhờ **bursting**, rồi giảm xuống baseline.

Vì vậy câu hỏi cần đặt ra là: **Ứng dụng cần bao nhiêu IOPS, bao nhiêu MiB/s, trong bao lâu, với latency mục tiêu nào và chạy qua những giới hạn nào?**

## 2. Năm khái niệm nền tảng

### 2.1. IOPS — số thao tác đọc/ghi mỗi giây

**IOPS** (*Input/Output Operations Per Second*) đo số thao tác I/O hoàn tất trong một giây. Ví dụ:

~~~text
Read operations:    3.200/s
Write operations:   1.800/s
Total:              5.000 IOPS
~~~

Đây là con số tổng hợp; phân tích kỹ còn phải xem kích thước I/O, tỷ lệ đọc/ghi và phân bố theo thời gian. Một workload có 5.000 thao tác 4 KiB rất khác với 5.000 thao tác 256 KiB.

### 2.2. Throughput — lượng dữ liệu mỗi giây

**Throughput** biểu thị tốc độ truyền dữ liệu, ví dụ MB/s hoặc MiB/s. Với kích thước I/O trung bình tính bằng KiB:

\[
\text{Throughput (MiB/s)}
\approx
\frac{\text{IOPS}\times\text{I/O size (KiB)}}{1024}
\]

Ví dụ:

| IOPS | Kích thước I/O | Throughput tương ứng |
| ---: | ---: | ---: |
| 2.000 | 8 KiB | 15,625 MiB/s |
| 2.000 | 32 KiB | 62,5 MiB/s |
| 2.000 | 256 KiB | 500 MiB/s |
| 8.000 | 8 KiB | 62,5 MiB/s |

Hai workload cùng 2.000 IOPS nhưng có thể cần băng thông khác nhau **32 lần**.

**Chú ý đơn vị:** 1 MiB = 1.048.576 byte, còn 1 MB = 1.000.000 byte. Các trang giới thiệu SKU và công cụ giám sát có thể dùng cách hiển thị khác nhau; khi tính sizing phải thống nhất đơn vị.

### 2.3. Latency — thời gian hoàn thành I/O

**Latency** là khoảng thời gian từ lúc phát sinh một thao tác đọc/ghi đến khi nhận kết quả, thường đo bằng ms. Với ứng dụng giao dịch, nên quan tâm cả **p95/p99 latency** thay vì chỉ trung bình.

Một hệ thống có thể đạt throughput cao nhưng vẫn khiến người dùng chậm nếu một tỷ lệ nhỏ request có thời gian chờ đột biến.

### 2.4. Queue depth và mức song song

**Queue depth** mô tả số I/O outstanding, đang chờ hoặc đang được xử lý ở một tầng. Một ứng dụng phát các lệnh đọc đồng bộ từng lệnh một có thể không tận dụng hết hiệu năng đĩa, ngay cả khi đĩa còn rất nhiều headroom.

Theo **Little's Law**, với hệ thống ổn định có thể ước lượng:

\[
\text{Outstanding I/O}\approx\text{IOPS}\times\text{Latency (giây)}
\]

Ví dụ, với 4.000 IOPS và latency 5 ms:

~~~text
4.000 × 0,005 = khoảng 20 I/O outstanding
~~~

Đây chỉ là phép ước lượng để hiểu nhu cầu song song. Tăng queue depth quá cao có thể làm latency tăng mà IOPS không tăng thêm khi đã chạm giới hạn.

### 2.5. Kiểu truy cập và kích thước block

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Kích thước I/O | 4 KiB, 8 KiB, 64 KiB, 1 MiB | Quyết định lượng dữ liệu mỗi operation |
| Random/sequential | SQL random page, backup sequential | Ảnh hưởng cache và tối ưu ứng dụng |
| Read/write mix | 90/10, 70/30, 20/80 | Ảnh hưởng đường đọc/ghi và độ trễ |
| Concurrency | 1, 8, 32, 128 I/O đồng thời | Ảnh hưởng khả năng bão hòa tài nguyên |
| Working set | 2 GiB hoặc 2 TiB | Ảnh hưởng hiệu quả cache |
| Peak duration | 60 giây hoặc 4 giờ | Quyết định bursting có thể giúp hay không |

**Không dùng IOPS tối đa của một bài test 4 KiB để dự báo throughput cho tác vụ sao lưu block lớn.**

## 3. Đường I/O qua Azure VM có nhiều tầng giới hạn

~~~mermaid
flowchart TD
    A["Ứng dụng\nSQL, API, ETL"]
    B["Guest OS\nfilesystem, page cache, queue"]
    V["VM size\ncached / uncached limits"]
    H["Azure host cache\nnếu được hỗ trợ"]
    D["Managed disk\nSKU, size, provisioned performance"]
    S["Azure storage platform"]
    A --> B --> V
    V --> H
    H -->|"Cache miss / uncached I/O"| D --> S
    H -.->|"Cache hit hỗ trợ"| A
~~~

Sơ đồ cho thấy các **lớp chức năng**, không diễn tả giao thức vật lý chính xác bên trong Azure.

### 3.1. Giới hạn mỗi managed disk

Mỗi disk có giới hạn IOPS và throughput theo SKU, size hoặc mức provisioned. Ví dụ **hoàn toàn giả định**:

~~~text
Disk data-01:
  Provisioned IOPS:       5.000
  Provisioned throughput: 200 MiB/s
~~~

Hai trần này phải xét **cùng lúc**. Chạm throughput trước thì không đạt được toàn bộ IOPS với block lớn; chạm IOPS trước thì không thể tăng số thao tác bằng cách giảm latency phần mềm đơn thuần.

### 3.2. Giới hạn VM size

VM cũng có giới hạn tổng I/O, đặc biệt **uncached IOPS/throughput** và, với VM hỗ trợ, giới hạn cho đường **cached I/O**.

Giả sử:

~~~text
Disk:              5.000 IOPS, 200 MiB/s
VM uncached limit: 4.000 IOPS, 160 MiB/s
Disk host caching: None
~~~

Trần hiệu năng tổng quát:

~~~text
IOPS       ≤ min(5.000, 4.000) = 4.000
Throughput ≤ min(200, 160)     = 160 MiB/s
~~~

Đó là **trần trên**, không phải mức thực tế được bảo đảm. Ứng dụng có thể thấp hơn do latency, queue depth, lock, CPU hoặc filesystem.

### 3.3. Gắn nhiều data disk có tăng performance không?

Có thể dùng nhiều disk và phân bổ dữ liệu hoặc tạo stripe bằng LVM/Storage Spaces để tận dụng tổng khả năng của chúng. Nhưng:

- Tổng I/O vẫn phải nằm trong giới hạn VM.
- Các disk có thể cạnh tranh cùng đường I/O.
- Stripe làm phức tạp backup, phục hồi và xử lý sự cố.
- VM có giới hạn số data disk/LUN.
- Một số loại disk cho phép tăng IOPS/throughput riêng thay vì tăng số disk hoặc dung lượng.

**Không mặc định hai disk tạo ra gấp đôi IOPS** nếu VM đã bão hòa.

### 3.4. Bốn dạng giới hạn cần phân biệt

1. **Disk-level throttling**: disk đạt provisioned IOPS hoặc throughput.
2. **VM-level throttling**: tổng I/O đạt trần cached/uncached của VM.
3. **Workload-limited**: app có ít I/O outstanding, chờ lock, CPU hoặc dịch vụ khác.
4. **Burst-limited**: disk hết khả năng burst hoặc không đủ điều kiện burst nữa.

Nếu tăng IOPS disk nhưng không thấy cải thiện, hãy kiểm tra trần VM và workload trước khi tăng tiếp.

## 4. Chọn Azure Managed Disk theo nhu cầu

| Loại disk | Workload điển hình | Cấu hình hiệu năng | Host caching | Bursting |
| --- | --- | --- | --- | --- |
| **Standard HDD** | Workload ít I/O, không nhạy latency | Theo tier/size | Tùy VM/cấu hình hỗ trợ | Không lấy bursting làm cơ sở thiết kế |
| **Standard SSD** | Ứng dụng phổ thông cần SSD với chi phí vừa phải | Theo tier/size | Theo cấu hình hỗ trợ | Credit-based ở một số cấu hình đủ điều kiện |
| **Premium SSD (v1)** | Production VM cần IOPS/latency tốt hơn | Gắn với tier/size | Có ở các trường hợp hỗ trợ | Credit-based hoặc on-demand tùy tier và điều kiện |
| **Premium SSD v2** | Cần provision IOPS và throughput độc lập | Điều chỉnh theo giới hạn SKU | **Không hỗ trợ host caching** | Không dùng disk bursting kiểu Premium SSD v1 |
| **Ultra Disk** | Workload đòi hiệu năng rất cao, latency thấp | Provision hiệu năng riêng | **Không hỗ trợ host caching** | Không dùng bursting thông thường |

Đây là so sánh định hướng. Khả năng dùng làm OS/data disk, hỗ trợ VM/region/zone, IOPS/MBps tối đa và mô hình phí có thể thay đổi. Khi chọn cho production, xác minh thông số **đúng SKU, đúng vùng và VM size hiện tại**.

### Vì sao Premium SSD v2 và Ultra Disk có cách sizing khác?

Với Premium SSD (v1), baseline thường gắn với tier/size. Với Premium SSD v2 và Ultra Disk, có thể cấu hình hiệu năng riêng trong phạm vi hỗ trợ. Từ đó:

- Chọn capacity theo dữ liệu cần lưu.
- Chọn provisioned IOPS theo số thao tác cần duy trì.
- Chọn provisioned throughput theo bytes/second cần duy trì.
- Kiểm tra VM có đủ I/O headroom.
- Tính chi phí cấu hình, không dựa vào một đợt burst ngắn để cam kết SLO.

**Dung lượng 1 TiB không đồng nghĩa hiệu năng như nhau ở mọi loại đĩa.**

## 5. Tính nhu cầu hiệu năng cho ứng dụng

### 5.1. OLTP: random I/O nhỏ, nhạy latency

Giả sử database vào giờ cao điểm phát sinh:

~~~text
Read operations/second:  4.500
Write operations/second: 1.500
Average I/O size:        8 KiB
Peak window:             3 giờ
Latency objective:       p99 dưới 10 ms
~~~

Nhu cầu IOPS:

\[
4500+1500=6000\ \text{IOPS}
\]

Nhu cầu throughput:

\[
6000\times8/1024 = 46{,}875\ \text{MiB/s}
\]

Bài toán này nghiêng về **IOPS và latency**; throughput yêu cầu tương đối thấp. Nhưng đỉnh tải kéo dài **3 giờ**, nên không mặc định credit-based bursting có thể giữ tốc độ vượt baseline trong suốt khoảng đó.

### 5.2. Backup: I/O lớn, throughput cao

Giả sử backup đọc tuần tự ở 2.000 IOPS với mỗi thao tác trung bình 256 KiB:

\[
2000\times256/1024=500\ \text{MiB/s}
\]

Tuy chỉ có 2.000 IOPS, công việc này cần tới **500 MiB/s**. Nếu VM uncached throughput chỉ là 160 MiB/s, workload sẽ không đạt yêu cầu 500 MiB/s qua đường đó, bất kể disk IOPS có được nâng thêm.

### 5.3. Phải tính tải chạy đồng thời

| Thời điểm | Workload | Yêu cầu nổi bật |
| --- | --- | --- |
| 09:00–11:00 | Database cao điểm | 6.000 IOPS, p99 thấp |
| 02:00–03:00 | Database thấp điểm + backup | Throughput backup lớn |
| 10:00 có backup đột xuất | Database cao điểm + backup | Trần tổng VM và mức cạnh tranh disk |

Các con số peak của hai tác vụ **không phải lúc nào cũng xảy ra cùng lúc**. Nên đo timeline thực tế để chọn cấu hình và lịch chạy backup phù hợp.

### 5.4. Dự trù headroom

Nếu CPU, VM I/O và disk IOPS luôn sát trần, một thay đổi nhỏ về traffic có thể làm queue depth và latency tăng mạnh. Dự trù headroom theo:

- Độ biến động traffic và mức tăng trưởng dự kiến.
- Thời gian peak, restart, recovery hoặc replay log.
- SLO latency của người dùng.
- Khả năng đổi performance online của đúng loại disk.
- Ngân sách và yêu cầu sẵn sàng.

Không có một con số headroom cố định phù hợp mọi doanh nghiệp; hãy dựa trên telemetry và load test đúng mô hình.

## 6. Host cache: None, ReadOnly và ReadWrite

**Azure host caching** là cơ chế cache ở lớp host của VM dành cho các disk/VM được hỗ trợ. Nó có thể cải thiện hiệu năng với những mẫu I/O phù hợp, nhất là đọc lặp lại. Không phải mọi I/O đều được phục vụ từ cache.

| Chế độ | Ý nghĩa | Khi nào đánh giá |
| --- | --- | --- |
| `None` | Không dùng Azure host caching cho disk | Log giao dịch, workload cần semantics ghi phù hợp, hoặc loại disk không hỗ trợ cache |
| `ReadOnly` | Cho phép cache đọc, không bật write-back caching | Data file đọc nhiều, working set có lặp |
| `ReadWrite` | Cho phép caching đọc và ghi theo cơ chế được hỗ trợ | Một số OS disk và ứng dụng có hướng dẫn hỗ trợ riêng |

### 6.1. Host cache khác bộ đệm của hệ điều hành

Có thể có nhiều lớp cache:

~~~mermaid
flowchart LR
    A["Ứng dụng\nbuffer pool"]
    B["Guest OS\npage cache"]
    C["Azure host cache\nnếu bật"]
    D["Managed disk"]
    A --> B --> C --> D
~~~

Nếu một báo cáo đọc cùng file nhiều lần, các lần sau có thể được phục vụ phần lớn từ application cache, OS page cache hoặc host cache. Khi đó:

- Ứng dụng có thể báo lượng dữ liệu đọc rất cao.
- Số read I/O thực sự xuống managed disk có thể thấp hơn.
- Benchmark “warm cache” có thể nhanh hơn “cold cache”.
- Tỷ lệ cache hit phụ thuộc working set và mẫu truy cập, không chỉ vào chế độ cấu hình.

**Host caching không phải backup hoặc nơi lưu dữ liệu lâu dài của ứng dụng.**

### 6.2. ReadOnly caching

Trong những workload đọc lặp và loại disk có hỗ trợ, `ReadOnly` có thể giảm read I/O xuống storage, giảm latency và tăng tốc độ đọc quan sát ở guest.

Ví dụ database thực hiện nhiều lần truy vấn trên tập dữ liệu tương tự:

1. Các block được truy cập lần đầu.
2. Những lần đọc sau có thể trúng cache ở một lớp thích hợp.
3. Ít read phải đi xuống managed disk hơn.
4. Nếu workload phù hợp, tốc độ đọc của ứng dụng có thể cải thiện.

Giới hạn cần lưu ý:

- Nếu mỗi lần đọc một vùng hoàn toàn mới, cache có thể ít hữu ích.
- ReadOnly không tự làm tăng giới hạn ghi của managed disk.
- Những read được cache có thể chịu **cached I/O limits của VM**.
- Cần đo theo mẫu đọc thật và kiểm tra sự phù hợp của ứng dụng.

### 6.3. ReadWrite caching và tính bền vững

`ReadWrite` không phải nút “tăng tốc miễn phí cho mọi database disk”. Một số ứng dụng yêu cầu chính xác thứ tự ghi, flush hoặc hành vi durable write; chọn sai chế độ có thể ảnh hưởng tính đúng đắn hoặc recovery.

Ví dụ SQL Server trên Azure VM thường được khuyến nghị:

| Vai trò disk | Cache thường được cân nhắc | Lý do |
| --- | --- | --- |
| OS disk | `ReadWrite` theo cấu hình OS disk được hỗ trợ | Đáp ứng hoạt động hệ điều hành |
| SQL data disk | `ReadOnly` khi loại VM/disk phù hợp | Tận dụng đọc lặp lại; phải kiểm tra hướng dẫn SQL |
| SQL transaction log disk | `None` | Đường ghi cần semantics và latency phù hợp |
| Backup/staging | Đo tải thực tế rồi quyết định | Sequential I/O có thể ít lợi ích từ cache |

Đây là **định hướng cho SQL Server**, không áp dụng nguyên xi cho PostgreSQL, Oracle, MySQL hoặc database engine khác. Phải theo hướng dẫn về I/O durability của từng sản phẩm và môi trường.

### 6.4. Những hạn chế host cache phải kiểm tra

- **Premium SSD v2 và Ultra Disk không hỗ trợ host caching.**
- Hỗ trợ của Standard SSD/Premium SSD (v1), OS/data disk và VM size phải được kiểm tra với cấu hình cụ thể.
- Đổi host caching có thể yêu cầu dừng/khởi động VM hoặc ảnh hưởng quá trình I/O.
- Thay cache mode cần có kế hoạch thử, bảo vệ dữ liệu, thời gian bảo trì và rollback phù hợp.
- Cache hit không làm tăng **provisioned disk write IOPS** trong mọi tình huống.

Không thay đổi caching của disk chứa transaction log trên production chỉ vì benchmark `ReadWrite` nhìn cao hơn trong vài giây.

## 7. Disk bursting: vượt baseline trong một khoảng có điều kiện

Workload không phải lúc nào cũng dùng I/O đều đặn:

~~~text
09:00–09:59   500 IOPS
10:00–10:02 3.000 IOPS
10:03–10:59   500 IOPS
~~~

**Disk bursting** là khả năng một số disk Azure được hỗ trợ xử lý I/O cao hơn baseline trong một khoảng và điều kiện nhất định. Nó có thể giúp tối ưu chi phí khi peak ngắn và phần lớn thời gian tải thấp.

### 7.1. Credit-based bursting

Trong cơ chế **credit-based**, khi mức sử dụng thấp hơn baseline, disk có thể tích lũy **burst credits** đến một ngưỡng. Lúc tải tăng vượt baseline, disk tiêu credits; khi credits giảm hoặc hết, khả năng vượt baseline cũng giảm.

~~~mermaid
flowchart LR
    L["Tải dưới baseline\nTích lũy credits"]
    C["Có credits\nđến mức giới hạn"]
    P["Peak vượt baseline\nTiêu credits"]
    E["Credits thấp / hết\nQuay về tốc độ nền"]
    L --> C --> P --> E --> L
~~~

Ví dụ toán học **chỉ để hình dung**, không phải cách Azure tính credits chính thức:

~~~text
Baseline:        500 IOPS
Peak:          3.000 IOPS trong 60 giây
Excess:        2.500 IOPS
Excess work: 150.000 operations vượt baseline
~~~

Cơ chế thực của dịch vụ còn tùy dung lượng credits, disk SKU/tier, giới hạn IOPS và throughput burst, cũng như thời gian đã tích lũy. Không nên dùng 150.000 như giá trị credits của một tier cụ thể.

### 7.2. On-demand bursting

Một số cấu hình **Premium SSD (v1)** đủ điều kiện có mô hình **on-demand bursting**:

- Không phụ thuộc cùng cách tích lũy credits của mô hình credit-based.
- Cho phép vượt baseline theo mức burst hỗ trợ.
- Có thể phải bật cấu hình riêng và **phát sinh phí bổ sung**, tùy điều khoản.
- Vẫn chịu trần của disk và VM; không có khả năng mở rộng vô hạn.

Không mặc định mọi Premium SSD đều được bật on-demand hoặc mọi OS/data disk, region và tier đều hỗ trợ.

### 7.3. Các loại disk và cơ chế bursting

| Loại | Cách nhìn đúng |
| --- | --- |
| Premium SSD (v1) tier nhỏ đủ điều kiện | Có thể có credit-based bursting |
| Premium SSD (v1) tier phù hợp khác | Có thể hỗ trợ on-demand bursting theo điều kiện |
| Standard SSD phù hợp | Có cơ chế credit-based với cấu hình được hỗ trợ |
| Premium SSD v2 | Provision hiệu năng trong giới hạn; không dựa vào disk burst kiểu v1 |
| Ultra Disk | Provision hiệu năng theo nhu cầu được hỗ trợ; không dùng cơ chế burst thông thường |
| Standard HDD | Không coi bursting là cơ chế sizing mặc định |

Thông số cụ thể nên được kiểm tra theo **SKU/size/API/region hiện hành**, không dựa vào một bảng tổng quát từ môi trường khác.

### 7.4. Disk bursting khác VM bursting

**Disk bursting** liên quan managed disk. **VM-level bursting**, nếu một VM size hỗ trợ, là cơ chế khác với điều kiện riêng.

Ngay cả khi disk được phép burst lên mức cao, tổng uncached IOPS/throughput của VM có thể là trần thấp hơn. Ngược lại, VM còn headroom cũng không tự cấp thêm credits cho disk.

### 7.5. Peak ngắn khác tải duy trì

Một benchmark chạy 30 giây có thể trông tuyệt vời khi còn credits. Workload ETL chạy 4 giờ có thể quay về baseline sau một thời gian, làm job kéo dài hơn dự kiến.

Khi quyết định dùng bursting, hãy đo:

1. **Baseline IOPS và throughput** cần duy trì.
2. **Peak duration** và tỷ lệ thời gian peak trong ngày.
3. SKU có cho phép burst không, có credits và giới hạn tối đa nào.
4. VM có đủ cached/uncached headroom không.
5. SLO có chịu được lúc về baseline không.
6. Phí on-demand hoặc chi phí đổi SKU nếu cần.

Không lấy mức burst tối đa làm thông số cam kết cho toàn bộ thời gian chạy hệ thống.

## 8. Phân biệt cache hit, burst và throttling

| Tình huống | Dấu hiệu | Dữ liệu cần đối chiếu |
| --- | --- | --- |
| **Host cache hit cao** | Read trong guest nhanh hơn nhiều so với physical reads xuống disk | Guest/app counters, disk metrics, warm/cold test |
| **Burst credits đang có** | Đầu tải tăng cao, sau đó quay về baseline | Disk SKU/burst behavior, hiệu năng theo thời gian |
| **On-demand bursting** | Tốc độ trên baseline theo cấu hình được bật | Thuộc tính disk, billing, VM limit |
| **Disk throttle** | Disk đạt IOPS hoặc throughput provisioned | Disk-level utilization/latency |
| **VM throttle** | Tổng data disks plateau, disk riêng còn headroom | VM cached/uncached IOPS/bandwidth |
| **Ứng dụng thiếu concurrency** | Disk/VM còn headroom nhưng IOPS thấp | Queue depth, thread, lock, CPU |
| **Memory/page cache** | Đọc lần hai nhanh hơn rất nhiều, ít guest disk I/O | OS/application cache metrics |

**Độ nhanh của cache và độ nhanh do burst là hai hiện tượng khác nhau.** Một phép test có thể chịu ảnh hưởng của cả hai cùng lúc, nên muốn benchmark chính xác phải ghi rõ working set, thời lượng, chế độ caching và trạng thái bursting.


## 9. Kiểm tra cấu hình Azure VM và Managed Disk

Các lệnh trong mục này chỉ **đọc thông tin**. Thay tên resource group, VM và disk bằng tên được phép trong subscription của bạn.

### 9.1. Xác định đúng tenant, subscription và VM size

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Chỉ chọn đúng subscription sau khi đã kiểm tra định danh.
az account set --subscription "<SUBSCRIPTION_ID>"

az vm show \
  --resource-group rg-data-prod \
  --name vm-db-prod \
  --query "{name:name, location:location, size:hardwareProfile.vmSize}" \
  --output json
~~~

VM size quyết định số data disk có thể gắn, hỗ trợ disk type và giới hạn I/O. Cần đối chiếu thông số **cached/uncached IOPS, cached/uncached throughput** của đúng family/size với tài liệu kỹ thuật Azure khi sizing.

### 9.2. Xem OS disk, data disk, LUN và caching

~~~bash
az vm show \
  --resource-group rg-data-prod \
  --name vm-db-prod \
  --query "storageProfile" \
  --output json
~~~

Các trường đáng chú ý:

- `storageProfile.osDisk.caching`.
- `storageProfile.dataDisks[].name`.
- `storageProfile.dataDisks[].lun`.
- `storageProfile.dataDisks[].caching`.
- `storageProfile.dataDisks[].managedDisk.id`.

Ví dụ **minh họa** cho một phần cấu hình:

~~~json
{
  "name": "data-sql-01",
  "lun": 0,
  "caching": "ReadOnly",
  "managedDisk": {
    "id": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-data-prod/providers/Microsoft.Compute/disks/data-sql-01"
  }
}
~~~

Từ đó biết disk LUN 0 được cấu hình `ReadOnly`. Nhưng điều này **không nói lên cache hit rate** hoặc hiệu năng thực tế.

### 9.3. Xem SKU và provisioned performance

~~~bash
az disk show \
  --resource-group rg-data-prod \
  --name data-sql-01 \
  --query "{name:name, sku:sku.name, sizeGiB:diskSizeGb, iops:diskIOPSReadWrite, throughputMBps:diskMBpsReadWrite, burstingEnabled:burstingEnabled, state:diskState}" \
  --output json
~~~

Tùy SKU/API, `diskIOPSReadWrite`, `diskMBpsReadWrite` hoặc `burstingEnabled` có thể là `null` hoặc không áp dụng. Chỉ xem `null` **không đủ** để kết luận khả năng credit-based bursting. Hãy kiểm tra thêm tier, vùng và mô tả hỗ trợ của loại disk tương ứng.

### 9.4. Xem đặc tính VM size theo region

~~~bash
# Lệnh đọc thông tin SKU VM tại một vùng ví dụ.
az vm list-sizes \
  --location southeastasia \
  --output table
~~~

Lệnh có thể trả về danh sách dài. Để xem chính xác trần cached/uncached IOPS và throughput, cần đối chiếu bảng khả năng I/O của VM family/size tương ứng, bởi kết quả `list-sizes` không nhất thiết hiển thị đủ mọi giới hạn hiệu năng.

### 9.5. Những lệnh không nên chạy khi đang chẩn đoán đọc-only

Những thao tác như thay cache mode, resize VM, nâng disk tier hoặc bật on-demand bursting có thể tác động thời gian hoạt động và chi phí. Đừng chạy `az vm update` hoặc `az disk update` trước khi có bằng chứng về bottleneck, đánh giá compatibility, backup và kế hoạch rollback.

## 10. Thu thập metric hiệu năng đúng lớp

### 10.1. Azure Monitor: xem cả VM và disk

Mở Azure Monitor → Metrics cho **VM** và **Managed Disk** liên quan. Các nhóm metric hữu ích:

| Nhóm | Cần biết |
| --- | --- |
| Read/write operations per second | Số IOPS đọc và ghi |
| Read/write bytes per second | Throughput từng chiều |
| Read/write latency | Có đợt chậm I/O trùng với app latency không? |
| Disk IOPS/bandwidth consumed percentage | Có dấu hiệu sát trần provisioned không? |
| VM cached/uncached performance | Có đang chạm giới hạn I/O ở VM không? |
| VM CPU/memory | Có bottleneck ngoài disk không? |
| OS disk và từng data disk | Disk nào tạo ra tải? |

**Tên metric và dimension thực tế phụ thuộc resource type/SKU.** Không mặc định mọi disk đều phát hành cùng bộ chỉ số. Hãy xem metric definitions của tài nguyên trước khi sao chép tên từ ví dụ khác.

### 10.2. Kiểm tra metric definitions bằng CLI

~~~bash
DISK_ID=$(az disk show \
  --resource-group rg-data-prod \
  --name data-sql-01 \
  --query id \
  --output tsv)

az monitor metrics list-definitions \
  --resource "$DISK_ID" \
  --output table
~~~

Sau đó chọn metric thực sự có trong danh sách, ví dụ nhóm read/write operations hoặc bytes per second. Với metric hiển thị theo tài nguyên VM, hãy lấy resource ID của VM rồi xem definitions ở scope đó.

Khi đánh giá, nhớ rằng metric Azure Monitor có **chu kỳ tổng hợp**. Biểu đồ trung bình một phút có thể làm mờ burst vài giây. Cần chọn aggregation và time granularity phù hợp.

### 10.3. Trên Linux: iostat và lsblk

Nếu guest đã có gói `sysstat`:

~~~bash
# Lấy 5 mẫu liên tiếp, mỗi mẫu cách nhau 1 giây.
iostat -dx 1 5

# Xác định disk, size và mountpoint đang đo.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
~~~

Trong `iostat -x`, tên cột có thể khác theo phiên bản:

| Cột | Ý nghĩa |
| --- | --- |
| `r/s`, `w/s` | Read/write operations mỗi giây |
| `rkB/s`, `wkB/s` | Tốc độ đọc/ghi theo đơn vị công cụ |
| `r_await`, `w_await`, `await` | Thời gian chờ/xử lý I/O trung bình |
| `aqu-sz` | Số I/O outstanding/hàng đợi trung bình |
| `%util` | Mức bận theo cách đo của guest OS |

**Không kết luận disk bão hòa chỉ vì `%util=100`** trên thiết bị ảo có nhiều queue. Phải xem IOPS, throughput, latency, queue và giới hạn Azure.

### 10.4. Trên Windows: Performance Monitor

Trên Windows VM, dùng PerfMon hoặc hệ thống telemetry có sẵn với các counter như:

- `PhysicalDisk\Disk Reads/sec`, `Disk Writes/sec`.
- `PhysicalDisk\Disk Read Bytes/sec`, `Disk Write Bytes/sec`.
- `PhysicalDisk\Avg. Disk sec/Read`, `Avg. Disk sec/Write`.
- `PhysicalDisk\Current Disk Queue Length`.

Cần đối chiếu disk/LUN trong OS với managed disk tương ứng. Tên ổ như `C:` hoặc `D:` không thay cho việc xác minh Resource ID của Azure disk.

### 10.5. Đừng nhầm các lớp metric

Giả sử dashboard của ứng dụng cho thấy 12.000 read IOPS, nhưng metric trên managed disk cho thấy 3.000 read IOPS. Đây chưa chắc là lỗi đo:

- Một phần read có thể được đáp ứng từ application cache.
- Một phần được phục vụ từ guest OS page cache.
- Một phần có thể trúng Azure host cache khi được hỗ trợ.
- Metric đo ở guest, VM và managed disk không nhất thiết phản ánh cùng số operation.

Khi cần xác minh, đo **cold read** và **warm read**, ghi working set, cache mode, disk metrics và số operation do ứng dụng phát ra.

### 10.6. Quan sát đủ lâu

Đối với workload có backup 90 phút, checkpoint hoặc burst credits, một ảnh chụp 10 giây thường không đủ. Nên thu số liệu xuyên suốt:

1. Trước peak để làm baseline.
2. Bắt đầu peak.
3. Giữa và cuối thời gian peak.
4. Sau khi tải giảm.
5. Giai đoạn phục hồi khi vừa restart hoặc vừa đổi cache mode.

Mục tiêu là **sustained performance và application SLO**, không chỉ một giá trị IOPS cao nhất.

## 11. Benchmark có kiểm soát

### 11.1. Ba câu hỏi benchmark khác nhau

- **IOPS test:** random I/O nhỏ có thể đạt bao nhiêu operation/s khi đủ concurrency?
- **Throughput test:** sequential I/O lớn có thể đạt bao nhiêu MiB/s?
- **Application benchmark:** truy vấn/API thật đáp ứng latency và throughput nghiệp vụ như thế nào?

Kết quả `fio` hoặc DiskSpd không tự thay thế benchmark SQL, ETL hoặc API. Hai bài test có block size/queue depth khác nhau có thể cho kết quả chênh lệch lớn.

### 11.2. Kiểm soát các điều kiện so sánh

Trước khi chạy benchmark, ghi:

| Tham số | Cần cố định hoặc lưu lại |
| --- | --- |
| VM size | Family, size, region/zone |
| Disk | SKU, size, provisioned IOPS và MBps |
| Cache | None/ReadOnly/ReadWrite |
| Workload | Block size, random/sequential, read/write ratio |
| Concurrency | Threads/jobs và queue depth |
| Dataset | Kích thước file, warm/cold cache |
| Duration | Thời gian warm-up, thời gian test, peak length |
| Bursting | Disk có credit/on-demand và khả năng đã sử dụng |
| Environment | Filesystem, OS, driver, quá trình nền |

Nếu đổi đồng thời VM size, disk tier và queue depth thì không thể biết thay đổi nào tạo ra hiệu quả.

### 11.3. Ví dụ fio trên filesystem lab riêng

Các lệnh sau **có ghi dữ liệu thử**. Chỉ chạy trên **đĩa lab riêng** sau khi xác minh đúng mount point, đủ dung lượng và không có dữ liệu cần giữ. Không chạy `fio` vào raw device chứa dữ liệu thật hoặc production volume.

~~~bash
# Thao tác ghi file 2 GiB, CHỈ dùng trên đĩa chuyên để thử.
fio \
  --name=sequential-write-lab \
  --filename=/mnt/bench-volume/fio-test.bin \
  --size=2G \
  --rw=write \
  --bs=256k \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

Sau khi file thử được tạo hợp lệ, có thể đo random read:

~~~bash
fio \
  --name=random-read-lab \
  --filename=/mnt/bench-volume/fio-test.bin \
  --size=2G \
  --rw=randread \
  --bs=8k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

Cách đọc:

- `IOPS` và `BW`: tốc độ thao tác và tốc độ dữ liệu.
- `latency` cùng percentile: mức chờ I/O.
- Tải CPU và các tác vụ khác.
- Biểu đồ Azure Monitor ở cùng thời gian.

**Giới hạn:** `--direct=1` chủ yếu bỏ qua **guest OS page cache** trên hệ thống hỗ trợ; **không nhất thiết bỏ qua Azure host cache**. File 2 GiB cũng có thể quá nhỏ so với working set thật. Benchmark 60 giây dễ phản ánh **burst** thay vì mức duy trì trong nhiều giờ.

### 11.4. Đo tải dài thay vì chỉ peak ngắn

Nếu ứng dụng chạy 2–4 giờ liên tục, benchmark hiệu năng **sustained** phải có thời lượng và kích thước dữ liệu đủ phù hợp, trên một môi trường lab được phép. Theo dõi sự thay đổi tốc độ theo thời gian; nếu ban đầu rất nhanh rồi giảm, xét burst credits, cache và VM throttling.

Không tự tăng cường độ thử trên production khi chưa có phương án bảo vệ ứng dụng và giới hạn tác động.

## 12. Quy trình điều tra khi disk hoặc database chậm

Giả sử sau khi tăng traffic, API latency tăng và database báo nhiều lần chờ disk.

### Bước 1 — Xác định điểm đau của người dùng

Ghi tên VM/disk, workload, thời gian, p95/p99 application latency, read/write mix và những thay đổi gần đây (deploy, backup, disk resize, VM resize, snapshot hoặc đổi cache).

### Bước 2 — Đọc cấu hình thật

Dùng Azure CLI ở mục 9 để xác nhận:

- SKU và provisioned IOPS/throughput của từng disk.
- VM size và uncached/cached limits.
- Caching của OS/data disks.
- Burst mode có hỗ trợ hoặc đã bật hay không.
- Tổng data disks và workload dùng chung VM.

### Bước 3 — Tính IOPS và throughput

Từ metric đo được, tính kích thước I/O trung bình:

\[
\text{I/O size (KiB)}
\approx
\frac{\text{Throughput (MiB/s)}\times1024}{\text{IOPS}}
\]

Nếu đạt 80 MiB/s với 5.120 IOPS, kích thước I/O bình quân khoảng **16 KiB**.

### Bước 4 — So sánh disk cap, VM cap và workload

| Hiện tượng | Khả năng mạnh hơn | Việc cần xem |
| --- | --- | --- |
| Disk sát IOPS cap, VM còn headroom | Disk IOPS-bound | Nâng provisioned IOPS/SKU, phân tải |
| Disk sát throughput cap, IOPS chưa cao | Disk throughput-bound | Throughput cap, block size, kiểu I/O |
| Nhiều disk plateau khi VM sát uncached cap | VM-level throttle | Chọn VM size có I/O headroom |
| Disk/VM còn headroom, queue thấp | App thiếu concurrency | Thread, DB wait, lock, queue depth |
| Queue cao, latency tăng, IOPS không tăng | Có thể đã bão hòa | Trần disk/VM, CPU/memory |
| Đầu benchmark nhanh, sau vài phút chậm | Burst hết hoặc workload thay đổi | SKU, credit/burst behavior, timeline |
| Read lặp lại nhanh, cold read chậm | Cache ảnh hưởng | Working set, host/OS/app cache |
| Ghi transaction log chậm | Write latency/durability | Cache log disk, DB log waits, flush |

### Bước 5 — Loại trừ yếu tố khác

Disk không phải thủ phạm duy nhất. Xem thêm:

- SQL locks hoặc query plan không tối ưu.
- CPU bão hòa, thiếu RAM, paging/swap.
- Database connection pool, thread pool.
- Backup/antivirus/agent nền cạnh tranh I/O.
- Filesystem gần đầy, cấu hình readahead hay I/O scheduler.
- Ứng dụng tạo quá nhiều I/O nhỏ hoặc ghi đồng bộ không cần thiết.
- Network/service phụ thuộc và độ trễ ở tầng khác.

### Bước 6 — Chỉ thay một yếu tố được kiểm soát

Phương án có thể gồm: tăng IOPS/throughput provisioned, đổi disk tier, chọn VM size phù hợp, phân tách data/log, điều chỉnh cache theo khuyến nghị database, tối ưu query/batching, hoặc thay lịch backup.

Trước bất kỳ thay đổi nào, xác định có downtime không, khả năng hoàn tác, backup và ảnh hưởng chi phí.

### Bước 7 — Đo kết quả thực

Sau thay đổi, kiểm tra:

1. p95/p99 application latency có giảm không?
2. IOPS/throughput có đạt mục tiêu trong **toàn bộ peak** không?
3. Có hiện tượng disk/VM throttling, queue tăng hoặc burst cạn không?
4. Có thay đổi về tính bền vững, lỗi ghi hay khả năng recovery không?
5. Chi phí tăng có đáng giá so với SLO đạt được không?

**Tối ưu đúng là tối ưu hành vi người dùng và khả năng vận hành, không chỉ nâng một con số IOPS trên bảng thông số.**


## 13. Hai tình huống triển khai thực tế

### 13.1. SQL Server OLTP và transaction log

**Bối cảnh:** SQL Server chạy trên Azure VM, lưu data files và transaction log trên các managed disk riêng. Trong giờ cao điểm có nhiều random read/write nhỏ, đêm có backup.

Phân tích ban đầu:

| Thành phần | Workload | Mục tiêu chính |
| --- | --- | --- |
| Data disk | Random I/O 8 KiB, đọc nhiều | IOPS, read latency |
| Transaction log disk | Sequential write, cần durability | Write latency, tính đúng đắn |
| Backup disk hoặc đích backup | I/O tuần tự lớn | Throughput và thời gian hoàn thành |
| VM | Tổng I/O của mọi disk | Cached/uncached limits và headroom |

Ví dụ số học:

~~~text
Data I/O: 5.500 IOPS × 8 KiB
  → khoảng 42,97 MiB/s

Transaction log I/O: 1.000 IOPS × 32 KiB
  → khoảng 31,25 MiB/s
~~~

Hướng lựa chọn:

1. Đo baseline và p95/p99 latency từng đường I/O.
2. Chọn SKU/IOPS/throughput cho peak duy trì, có headroom.
3. Cân nhắc `ReadOnly` host caching cho SQL data disk trên cấu hình hỗ trợ và theo hướng dẫn của SQL Server.
4. Ưu tiên `None` cho transaction log disk khi đó là hướng dẫn phù hợp với workload/disk.
5. Kiểm tra VM-level I/O limits; tránh cấu hình disk cao hơn nhiều mà VM không sử dụng được.
6. Không dựa vào burst credits để đảm bảo một phiên giao dịch cao điểm kéo dài hàng giờ.
7. Theo dõi SQL wait stats, log write latency, CPU/memory, disk/VM metrics và app SLO.

**Bài học:** hai disk có cùng capacity không nhất thiết nên dùng cùng cache mode hoặc SKU vì yêu cầu đọc/ghi và durability khác nhau.

### 13.2. Batch analytics đọc dữ liệu lớn

**Bối cảnh:** pipeline đọc file lớn để tạo báo cáo, chạy khoảng hai giờ mỗi đêm. Nhu cầu ước lượng:

~~~text
Sequential read operations: 1.500 IOPS
Average size:               512 KiB
Required throughput:        750 MiB/s
Window:                     2 giờ
~~~

Phân tích:

- 1.500 IOPS không phải yêu cầu cao đối với mọi disk, nhưng **750 MiB/s** là mức throughput đáng kể.
- Chọn disk chỉ vì IOPS tối đa có thể không đủ throughput.
- Đường uncached của VM phải đáp ứng được mức bytes/s tương ứng.
- ReadOnly cache có thể ít tác dụng nếu mỗi dữ liệu chỉ được đọc một lần và working set rất lớn.
- Tải kéo dài hai giờ khiến việc chỉ dựa vào credit-based burst trở nên rủi ro.
- Có thể cân nhắc disk cho phép provision throughput riêng nếu cấu hình VM/region hỗ trợ.

Để tối ưu, ngoài đĩa còn cần xem batch size, độ song song I/O, phân vùng dữ liệu, CPU nén/giải nén và độ trễ dịch vụ đích.

### 13.3. Bảng quyết định ban đầu

| Workload | Chỉ tiêu ưu tiên | Host cache nên xem xét | Đánh giá bursting |
| --- | --- | --- | --- |
| OLTP random read | IOPS, p99 latency | ReadOnly data disk trên cấu hình được hỗ trợ | Chỉ phù hợp peak ngắn với đủ headroom |
| Transaction log | Latency ghi, durability | None theo hướng dẫn sản phẩm | Không làm nền tảng để bảo đảm ghi liên tục |
| Backup/restore | Throughput tuần tự | Đo theo workload thật | Xem thời lượng job |
| ETL/batch | MiB/s, thời gian hoàn thành | Không mặc định có lợi | Xem độ dài peak và chi phí |
| VM nghiệp vụ phổ thông | Giá, latency, IOPS, throughput | Theo OS/data và SKU | Có thể hữu ích với spike ngắn |
| Database hiệu năng cao | Provisioned IOPS/throughput, latency | v2/Ultra không hỗ trợ cache | Chọn baseline phù hợp thay vì phụ thuộc credits |

## 14. Bài thực hành tính toán và xác định bottleneck

### 14.1. Bộ dữ liệu giả lập

Một VM có một data disk và các giới hạn **hoàn toàn giả định**:

| Thông số | Giá trị |
| --- | ---: |
| Disk baseline IOPS | 5.000 |
| Disk baseline throughput | 180 MiB/s |
| VM uncached IOPS | 4.000 |
| VM uncached throughput | 150 MiB/s |
| Host cache | None |
| Kích thước I/O trung bình | 64 KiB |
| Thời gian peak | 3 giờ |

#### Bài A — 4.000 IOPS cần bao nhiêu throughput?

\[
4000\times64/1024=250\ \text{MiB/s}
\]

**Đáp án:** cần 250 MiB/s, lớn hơn cả disk baseline throughput 180 MiB/s và VM uncached throughput 150 MiB/s. Tăng disk IOPS riêng lẻ không giải quyết được giới hạn throughput.

#### Bài B — Nếu VM giới hạn 150 MiB/s, có thể đạt nhiều nhất bao nhiêu IOPS ở 64 KiB?

\[
\text{IOPS}\leq\frac{150\times1024}{64}=2400
\]

**Đáp án:** trần lý thuyết khoảng **2.400 IOPS** theo throughput, trước khi xét latency và phần mềm. Dù VM công bố uncached IOPS 4.000, block size này làm throughput cap xuất hiện trước.

#### Bài C — Có nên chọn bursting để đáp ứng peak ba giờ?

**Đáp án:** không mặc định. Cần xác minh SKU, loại burst, giới hạn credits/on-demand, trần VM và chi phí. Nếu mục tiêu là hiệu năng ổn định liên tục ba giờ, nên sizing mức provisioned/baseline có thể duy trì hoặc thay đổi kiến trúc.

#### Bài D — Thay disk thành SKU hỗ trợ 400 MiB/s nhưng giữ VM thì sao?

**Đáp án:** trần VM uncached throughput vẫn 150 MiB/s. Phải xác minh VM size có thể nâng cấp hoặc thay đổi đường I/O nếu mục tiêu thật sự cao hơn.

### 14.2. Bài tập phân loại IOPS-bound và throughput-bound

| Workload | IOPS | I/O size | Throughput tương ứng |
| --- | ---: | ---: | ---: |
| A | 10.000 | 8 KiB | 78,125 MiB/s |
| B | 800 | 512 KiB | 400 MiB/s |
| C | 1.000 | 16 KiB | 15,625 MiB/s |

**Câu hỏi:** workload nào có khả năng chịu áp lực IOPS cao nhất? Workload nào cần băng thông lớn nhất? Có thể kết luận latency của chúng chỉ từ bảng này không?

**Gợi ý:**

- A có nhu cầu số thao tác lớn nhất.
- B có nhu cầu thông lượng lớn nhất.
- C nhỏ hơn về cả IOPS và throughput, nhưng vẫn có thể chậm nếu backend có độ trễ cao.
- Không đủ dữ liệu xác định latency; phải có concurrency, queue, khả năng disk/VM và workload thực.

### 14.3. Bài tập phân biệt host cache và disk burst

Kết quả một phép đo giả định:

~~~text
Host cache: ReadOnly
Guest application:     12.000 read IOPS
Managed disk metric:    3.000 read IOPS
Lần đọc thứ hai:        nhanh hơn rõ rệt
~~~

**Câu hỏi:** có chắc metric Azure sai không?

**Đáp án:** không. Nhiều read có thể được phục vụ từ application/OS/host cache. Cần so sánh cold/warm cache, working set, guest counters và metric ở storage. Một số metric đo ở các lớp khác nhau nên không có nghĩa chúng phải bằng nhau.

### 14.4. Bài tập thiết kế phương án cải thiện

Một VM đang có 4 data disks. Tổng workload 6.000 uncached IOPS, VM limit là 5.000 uncached IOPS, mỗi disk đều còn headroom.

**Câu hỏi:** nếu tăng IOPS provisioned của cả bốn disk, liệu ứng dụng có tăng lên 6.000 IOPS không?

**Đáp án:** không thể vượt trần VM 5.000 uncached IOPS bằng cách chỉ thay đổi disk. Cần đánh giá VM size khác hoặc bố trí workload sang nhiều VM/đường I/O phù hợp, đồng thời xác minh throughput và application concurrency.

### 14.5. Bài tập lập kế hoạch quan sát

Điền bằng chứng thực tế cho hệ thống của bạn:

| Câu hỏi | Cần xác minh |
| --- | --- |
| Ứng dụng chậm vào lúc nào? | Timeline peak, latency p95/p99 |
| Nghẽn IOPS hay throughput? | Ops/s, bytes/s, I/O size |
| Disk đã sát giới hạn chưa? | SKU, provisioned values, metrics |
| VM có chạm trần I/O? | Cached/uncached limits và counters |
| Cache đang ảnh hưởng kết quả? | Caching mode, warm/cold, guest/disk metrics |
| Burst được hỗ trợ và đủ lâu? | SKU, mode, thời lượng peak, credits/on-demand |
| Có yếu tố không phải disk? | CPU/RAM/lock/query/dependency |
| Thay đổi nào an toàn và hiệu quả? | Tác động, downtime, rollback, chi phí, SLO |

## 15. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Dung lượng disk lớn thì ứng dụng chắc chắn nhanh.” | SKU, provisioned IOPS/throughput, VM và workload đều quan trọng. |
| “10.000 IOPS đồng nghĩa 10.000 MB/s.” | Cần biết kích thước I/O và đơn vị dữ liệu. |
| “Disk đạt IOPS yêu cầu là đủ.” | Còn throughput, latency và giới hạn VM. |
| “Gắn thêm hai disk sẽ tăng gấp đôi IOPS.” | VM aggregate limit và concurrency có thể cản trở. |
| “ReadWrite cache luôn nhanh hơn và an toàn cho database.” | Phải tuân thủ semantics ghi/durability và hướng dẫn workload. |
| “ReadOnly cache làm nhanh mọi đọc/ghi.” | Chủ yếu giúp đọc lặp với cache hit phù hợp; không tăng tốc ghi mặc định. |
| “Premium SSD v2 và Ultra Disk có host caching như Premium SSD v1.” | Hai loại này không hỗ trợ host caching. |
| “Burst IOPS là hiệu năng duy trì cả ngày.” | Có điều kiện, giới hạn và có thể hết credits. |
| “Bật disk bursting thì VM tự tăng I/O limit.” | Disk và VM có các trần độc lập. |
| “Benchmark 30 giây đủ chứng minh production sẽ đạt SLO.” | Phải đo sustained performance, latency và workload thật. |
| “I/O chậm chắc chắn do disk.” | Có thể do CPU, memory, lock, database hoặc ứng dụng. |
| “Đổi cache mode là thay đổi không gián đoạn.” | Có thể cần bảo trì/restart, cần kiểm tra và chuẩn bị rollback. |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Workload 3.000 IOPS, trung bình 16 KiB/I/O. Throughput xấp xỉ bao nhiêu?

**Đáp án:** `3000 × 16 / 1024 = 46,875 MiB/s`.

**Câu 2.** Disk được provision 10.000 IOPS, nhưng VM có uncached limit 6.000 IOPS và cache None. Có thể đạt 10.000 uncached IOPS ổn định không?

**Đáp án:** Không. VM limit 6.000 là giới hạn trước khi xét throughput và khả năng ứng dụng.

**Câu 3.** Vì sao backup có thể chậm dù IOPS không cao?

**Đáp án:** Backup có block size lớn, nên đòi hỏi nhiều MiB/s. Throughput cap ở disk hoặc VM có thể là bottleneck chính.

**Câu 4.** ReadOnly host caching giúp gì, có làm tăng hiệu năng ghi không?

**Đáp án:** Có thể tăng hiệu năng đọc khi cache hit; không nên suy rằng nó làm tăng trực tiếp khả năng ghi của managed disk.

**Câu 5.** Vì sao transaction log thường tránh Write caching tùy tiện?

**Đáp án:** Log yêu cầu semantics ghi bền vững và recovery; phải theo hướng dẫn của database engine và Azure VM/disk liên quan.

**Câu 6.** Disk nhanh hai phút đầu rồi giảm về baseline. Nêu ba nguyên nhân cần kiểm tra.

**Đáp án:** Burst credits cạn, VM/disk bandwidth cap hoặc sự thay đổi trong tải/caching. Dùng cấu hình và metrics để xác minh.

**Câu 7.** Premium SSD v2 cần tăng IOPS mà không tăng dung lượng: nên đánh giá gì?

**Đáp án:** Khả năng provision IOPS/throughput riêng trong giới hạn SKU/VM/region và chi phí tương ứng; không áp dụng mô hình burst/host cache của Premium SSD v1.

**Câu 8.** Vì sao `fio --direct=1` không bảo đảm loại bỏ tất cả cache?

**Đáp án:** Tham số này chủ yếu bypass guest OS page cache trong hệ điều hành hỗ trợ; host cache và những lớp khác vẫn có thể ảnh hưởng.

**Câu 9.** Bạn nâng disk từ 200 MiB/s lên 500 MiB/s nhưng VM limit là 160 MiB/s. Kết quả nào nên kỳ vọng với I/O uncached?

**Đáp án:** Không thể vượt trần uncached throughput 160 MiB/s của VM chỉ bằng tăng disk. Cần xem đổi VM/kiến trúc sau khi xác nhận bottleneck.

**Câu 10.** Nếu IOPS đạt mục tiêu nhưng p99 latency vẫn cao, hệ thống đã đạt SLO chưa?

**Đáp án:** Chưa chắc. SLO của ứng dụng có thể phụ thuộc latency đuôi, contention và thời gian hoàn thành request; phải đối chiếu metric nghiệp vụ.

## Ghi nhớ

- **IOPS** đo thao tác mỗi giây; **throughput** đo dữ liệu mỗi giây; **latency** là thời gian một thao tác; **queue depth** thể hiện số thao tác đang chờ/xử lý.
- **Throughput ≈ IOPS × kích thước I/O** sau khi thống nhất đơn vị. Chọn disk theo cả IOPS, MiB/s và latency.
- Hiệu năng thực tế chịu giới hạn đồng thời của **disk, VM, cached/uncached path và workload**.
- **Host caching** có ba chế độ `None`, `ReadOnly`, `ReadWrite`; chỉ dùng khi loại disk hỗ trợ và semantics đọc/ghi phù hợp.
- **Disk bursting** có thể giúp với peak ngắn, nhưng không thay thế baseline được provision cho tải duy trì nhiều giờ.
- Phân biệt **credit-based burst, on-demand burst** và khả năng điều chỉnh provisioned IOPS/throughput của từng SKU.
- Luôn đo **Azure Monitor + guest metrics + application SLO**, đánh giá chi phí và rollback trước khi nâng disk/VM hoặc thay chế độ cache.
