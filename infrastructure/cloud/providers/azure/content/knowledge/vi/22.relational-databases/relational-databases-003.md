# DTU, vCore, serverless và elastic pool

Một hệ thống bán hàng có cơ sở dữ liệu Azure SQL Database chạy ổn định ban ngày nhưng rất ít truy vấn vào ban đêm. Một công ty SaaS khác quản lý 40 cơ sở dữ liệu riêng cho 40 khách hàng, mỗi khách có thời điểm cao tải khác nhau. Nếu chọn gói tính toán theo cảm tính, doanh nghiệp có thể trả tiền cho tài nguyên nhàn rỗi hoặc gặp độ trễ lớn khi lượng giao dịch tăng.

**Azure SQL Database** cung cấp nhiều cách phân bổ và thanh toán tài nguyên. Bốn thuật ngữ quan trọng là:

- **DTU (Database Transaction Unit):** mô hình tài nguyên gộp CPU, memory và I/O thành các mức hiệu năng.
- **vCore (virtual core):** mô hình biểu diễn tài nguyên bằng số lõi ảo, bộ nhớ, lưu trữ và các lựa chọn phần cứng/dịch vụ được hỗ trợ.
- **Serverless:** một mô hình compute trong vCore, có khả năng tự điều chỉnh compute theo tải và, ở cấu hình hỗ trợ, tự tạm dừng khi không hoạt động.
- **Elastic pool:** nhóm cơ sở dữ liệu độc lập cùng chia sẻ ngân sách tài nguyên tính toán của pool thay vì mỗi database phải được cấp compute riêng.

Điểm dễ nhầm: **DTU và vCore là mô hình mua tài nguyên; serverless là mô hình cấp phát compute; elastic pool là mô hình gom nhiều database để chia sẻ compute**. Chúng không phải bốn database engine khác nhau.

Bài học thuộc chương **Cơ sở dữ liệu quan hệ** của mô-đun **CLOUD_PROVIDERS_AZURE**. Lộ trình khám phá Azure từ subscription, resource group và Microsoft Entra ID đến VNet, tính toán, lưu trữ và dữ liệu; cuối cùng học triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

> **Phạm vi:** Tập trung vào **Azure SQL Database** dạng single database và elastic pool. Không tự áp dụng những lựa chọn DTU, serverless hay elastic pool của bài này cho **Azure SQL Managed Instance**, **SQL Server trên Azure VM** hoặc **Azure Database for PostgreSQL** vì mô hình dịch vụ và giới hạn của chúng khác nhau. SKU, tier, giới hạn và tính sẵn có có thể thay đổi theo region/thời điểm; trước khi mua tài nguyên phải xác nhận cấu hình Azure đang hỗ trợ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt DTU/eDTU, vCore, provisioned compute, serverless và elastic pool.
2. Mô tả mối quan hệ giữa **Basic/Standard/Premium** của DTU và **General Purpose/Business Critical/Hyperscale** của vCore.
3. Giải thích serverless autoscaling, minimum/maximum vCores, auto-pause, auto-resume và tác động tới độ trễ.
4. Lựa chọn single database hoặc elastic pool cho một hay nhiều tenant có chu kỳ tải khác nhau.
5. Đọc và diễn giải CPU, data I/O, log write, workers, sessions, storage và dấu hiệu thiếu tài nguyên.
6. So sánh các phương án theo workload, SLA, bảo mật, tính sẵn sàng, chi phí và vận hành.
7. Biết quy trình thay đổi service objective an toàn, kiểm chứng hiệu năng và chuẩn bị rollback.
8. Sử dụng Azure portal, Azure CLI và T-SQL đọc thông tin trước khi đưa ra quyết định.

## 1. Azure SQL Database là gì?

Azure SQL Database là **cơ sở dữ liệu quan hệ dạng PaaS** tương thích hệ sinh thái SQL Server theo phạm vi tính năng được hỗ trợ. Azure quản lý nhiều nhiệm vụ hạ tầng như phần cứng, hệ điều hành, cơ chế backup nền tảng và khả năng sẵn sàng của dịch vụ. Người sử dụng vẫn chịu trách nhiệm thiết kế schema, truy vấn, bảo mật dữ liệu, kết nối ứng dụng, hiệu năng, phân quyền và quản trị chi phí.

~~~text
Ứng dụng / API / worker
        |
        | TDS/SQL connection được bảo vệ bằng TLS
        v
Azure SQL logical server
        |
        +-- Database: sales-db
        |
        +-- Database: billing-db
        |
        +-- Database: tenant-001
        |
        +-- Database: tenant-002
        |
        +-- Elastic pool (nếu cấu hình):
              tenant-003, tenant-004, ...
~~~

**Logical server** là tài nguyên quản lý endpoint, authentication và một số cấu hình liên quan; nó không đồng nghĩa một VM mà bạn phải gán CPU trực tiếp. Compute và performance của từng database hoặc pool được quản trị theo các lựa chọn dịch vụ tương ứng.

### Câu hỏi đầu tiên khi chọn tài nguyên

- Có **một database lớn** hay **nhiều database riêng**?
- Tải có ổn định cả ngày hay có giai đoạn nhàn rỗi dài?
- Những database có đạt đỉnh **cùng một lúc** hay lệch nhau?
- Tốc độ phản hồi có chấp nhận được thời gian thức dậy khi serverless auto-resume không?
- Giới hạn đáng lo nhất là CPU, I/O, log throughput, bộ nhớ, concurrency hay dung lượng?
- Dữ liệu cần HA, geo-replication, backup/PITR, yêu cầu region và quyền truy cập ở mức nào?

## 2. Tổng quan các lựa chọn

| Mô hình | Đơn vị/tài nguyên chính | Thích hợp với | Đánh đổi |
|---|---|---|---|
| **DTU single database** | Mức DTU kết hợp CPU/memory/I/O | Một database đơn giản, muốn mức tài nguyên gộp dễ chọn | Khó thấy chi tiết riêng CPU/RAM khi so với nhu cầu |
| **vCore provisioned single database** | Số vCores và các thuộc tính tier/hardware | Workload ổn định, cần kiểm soát compute rõ hơn | Compute được cấp phát ngay cả khi tải thấp |
| **vCore serverless single database** | Min/max vCores và compute sử dụng; auto-pause khi được hỗ trợ | Workload biến động, có thời gian nhàn rỗi | Cold start, giới hạn tương thích và bill khi active |
| **DTU elastic pool** | Tổng **eDTUs** của pool và giới hạn từng DB | Nhiều DB nhỏ, tải lệch nhau | Các DB cùng cạnh tranh ngân sách chung |
| **vCore elastic pool** | Tổng vCores/storage theo mô hình pool và giới hạn mỗi DB | SaaS multi-tenant, nhiều DB cùng chia compute | Cần sizing đồng thời, tránh noisy neighbor |

Một cơ sở dữ liệu có thể chuyển giữa các cấu hình được hỗ trợ, nhưng không phải mọi chuyển đổi đều online, tức thời hoặc không có điều kiện. Kiểm tra giới hạn của service tier, thời gian thay đổi và ảnh hưởng tới kết nối trước khi làm trên production.

### Quy tắc phân loại

~~~text
                         Azure SQL Database
                                 |
                    Chọn cách cấp tài nguyên
                      /                    \
                     v                      v
                 DTU model               vCore model
                 /       \                /        \
                v         v              v          v
            Single DB  Elastic pool   Single DB  Elastic pool
                                     /      \
                                    v        v
                               Provisioned  Serverless
                               theo tier   ở cấu hình hỗ trợ
~~~

Sơ đồ mô tả các mô hình phổ biến; **serverless không phải một loại elastic pool có thể chọn mặc định**. Những kết hợp giữa Hyperscale, elastic pools và các compute tier phải được xác nhận bằng ma trận hỗ trợ hiện hành.

## 3. DTU là gì?

**Database Transaction Unit (DTU)** là thước đo hiệu năng gộp dựa trên những đặc tính như:

- Sức xử lý CPU.
- Bộ nhớ.
- Data I/O.
- Log I/O.

Azure cung cấp các service objectives ở những mức DTU khác nhau. Mỗi mức kèm giới hạn về tài nguyên và mức dịch vụ. Bạn chọn một mức thay vì chọn chính xác số vCore và các thành phần phần cứng riêng.

~~~text
Một single database dùng DTU:

      CPU
        \
      Memory ----> Mức DTU/SKU ----> Năng lực database
        /
     Data I/O
        \
       Log I/O
~~~

Ví dụ, **Standard S2** và **Standard S3** là các service objectives theo mô hình DTU (mức tài nguyên khác nhau). Đừng chỉ nhìn tên S2/S3 rồi suy luận quy đổi trực tiếp sang số vCore: chúng là **các gói tài nguyên gộp**.

### Khi nào DTU hữu ích?

- Ứng dụng nhỏ hoặc vừa, không cần chọn riêng compute/hardware.
- Nhóm muốn bắt đầu từ một service objective đơn giản.
- Hệ thống đã dùng DTU ổn định và chưa có lý do kỹ thuật/chi phí rõ ràng để chuyển mô hình.
- Workload phù hợp với gói CPU/memory/I/O được cung cấp.

### Giới hạn của tư duy DTU

Một database có DTU usage cao chưa chắc chỉ bị thiếu CPU. Nguyên nhân có thể là data I/O hoặc log write throughput đang chạm hạn mức. Việc tăng DTU có thể cải thiện nhưng không thay thế việc tối ưu truy vấn, index, batch size và transaction.

**DTU không phải số giao dịch SQL tối đa mỗi giây.** Không có phép đổi đáng tin kiểu “100 DTUs = 100 transactions/second”. Throughput thực tế phụ thuộc schema, locks, kích thước dữ liệu, truy vấn và pattern ghi/đọc.

## 4. Các service tier trong DTU model

| Tier | Đặc điểm khái quát | Ví dụ workload |
|---|---|---|
| **Basic** | Mức tài nguyên nhỏ cho workload đơn giản | Lab, ứng dụng nhỏ và dev/test phù hợp |
| **Standard** | Các mức hiệu năng trung gian | Web app/line-of-business ổn định |
| **Premium** | Mức hiệu năng cao hơn với đặc tính I/O/latency phù hợp | Workload transaction nặng cần hiệu năng cao |

Mỗi tier có giới hạn về size, concurrency, backup retention và tính năng theo SKU. Không kết luận rằng đổi từ Standard sang Premium sẽ luôn khắc phục mọi truy vấn chậm.

### Đọc một metric DTU thế nào?

Giả sử Azure Monitor cho biết database thường xuyên gần 100% mức DTU trong giờ cao điểm. Các bước tiếp theo:

1. Xem **CPU percentage**, **data IO percentage**, **log IO percentage** và những metric liên quan.
2. Xác định request nào gây tải, có blocking hoặc index scan lớn không.
3. Kiểm tra tỉ lệ read/write, số kết nối, workers và sessions.
4. Đo latency trước/sau tối ưu.
5. Nếu vẫn bão hòa theo tải thật, mới cân nhắc tăng mức DTU hoặc chuyển sang vCore.

**Sử dụng cao trong một khoảnh khắc** có thể chỉ là batch bình thường. Điều đáng quan tâm là sử dụng cao kéo dài kèm timeout, throttling hoặc không đáp ứng SLA.

## 5. eDTU là gì?

**Elastic Database Transaction Unit (eDTU)** là đơn vị tài nguyên gộp trong **DTU elastic pool**. Thay vì gán riêng DTU cố định cho từng database, bạn mua ngân sách eDTU chung để nhiều database dùng theo mức tải thực tế.

~~~text
DTU single:
  tenant-A --> S2 database
  tenant-B --> S2 database
  tenant-C --> S2 database

Elastic pool theo DTU:
  tenant-A --\
  tenant-B ---+--> eDTU budget chung
  tenant-C --/
~~~

**Không cộng eDTU của pool với DTU từng database như hai hóa đơn compute độc lập.** Trong pool, các database dùng chung ngân sách pool và chịu các giới hạn được cấu hình theo từng database.

### Tại sao gọi là elastic?

Một tenant có thể đạt đỉnh lúc 9 giờ sáng; tenant khác đạt đỉnh sau giờ làm; tenant thứ ba hầu như không có giao dịch. Pool cho phép khai thác **mức tải không đồng thời**, tránh phải cấp đủ peak compute riêng cho tất cả.

Nếu nhiều tenant cùng đạt đỉnh, pool vẫn bị giới hạn bởi tổng tài nguyên mua. Elastic **không có nghĩa năng lực vô hạn hoặc tự tăng ngân sách pool miễn phí**.

## 6. vCore là gì?

**vCore** là mô hình cấu hình Azure SQL Database theo tài nguyên compute biểu diễn bằng số **virtual cores**, cùng với lựa chọn service tier, hardware, memory profile và storage theo hỗ trợ. Nó giúp người quản trị dễ liên hệ hơn với một workload SQL vốn đã được đo bằng CPU, memory và I/O.

Các lợi ích thường gặp:

- Biết rõ hơn ngân sách compute theo **số vCore**.
- Lựa chọn giữa những **service tiers** có đặc tính hiệu năng/kiến trúc khác nhau.
- Có thể tận dụng **Azure Hybrid Benefit** khi đủ điều kiện và gói hỗ trợ.
- Có các lựa chọn **reserved capacity** hoặc hình thức cam kết chi phí được hỗ trợ, tùy dịch vụ/tier.
- Dễ quy đổi nhu cầu tài nguyên từ quan sát CPU/IO hiện tại hơn so với đơn vị DTU gộp, nhưng vẫn phải benchmark.

### vCore không đồng nghĩa một CPU vật lý riêng

vCore là đơn vị compute của dịch vụ đám mây theo hardware generation/configuration. Một vCore không phải lời hứa có một lõi vật lý chuyên dụng trong mọi SKU.

**Cùng số vCore nhưng khác service tier/hardware có thể cho hiệu năng và chi phí khác.** Bộ nhớ, latency storage, I/O limits và topology của tier ảnh hưởng hiệu năng thực.

## 7. Các service tiers của vCore

Azure SQL Database thường có các tier chính:

| Tier | Kiến trúc/đặc tính ở mức khái quát | Dùng khi |
|---|---|---|
| **General Purpose** | Cân bằng chi phí và hiệu năng, compute và storage theo kiến trúc tier | Ứng dụng nghiệp vụ phổ biến, workload không yêu cầu I/O latency thấp nhất |
| **Business Critical** | Hướng đến I/O latency thấp, tính sẵn sàng/replica và hiệu năng cao theo topology tier | OLTP nặng, workload yêu cầu hiệu năng và SLA chặt |
| **Hyperscale** | Kiến trúc mở rộng dung lượng và compute/storage tách lớp theo thiết kế Hyperscale | Database lớn, tăng trưởng mạnh, workload phù hợp scale/storage đặc thù |

**Hyperscale không chỉ là “Business Critical với nhiều GB hơn”**. Các tier có kiến trúc, HA, backup/restore và giới hạn riêng. Không giả định một tính năng như auto-pause, elastic pool, zone redundancy hoặc replica secondary sẽ giống nhau ở mọi tier.

### Chọn General Purpose hay Business Critical?

Hãy đo **latency và bottleneck**. Nếu database dùng General Purpose có data I/O latency làm chậm giao dịch và tối ưu truy vấn chưa đủ, Business Critical có thể đáng đánh giá. Nếu vấn đề là khóa giao dịch/thiếu index, tăng service tier chưa chắc đem lại lợi ích tương xứng.

### Khi nào cân nhắc Hyperscale?

- Dung lượng database đang tăng vượt khả năng phù hợp của tier hiện tại.
- Restore/scale/read workload cần các đặc tính riêng của Hyperscale.
- Muốn kiến trúc storage và replica có khả năng mở rộng theo thiết kế Hyperscale.

Trước khi chuyển, kiểm tra **hạn chế tính năng, chuyển đổi thuận/ngược, latency, backup retention, billing và khả năng restore** theo cấu hình hiện hành. Không coi việc di chuyển giữa các tier là thao tác có thể đảo ngược tức thì.

## 8. Provisioned compute trong vCore model

**Provisioned compute** là mô hình cấp phát compute theo mức vCore đã chọn. Database có ngân sách CPU/memory theo SKU, kể cả trong các giờ ít hoạt động.

~~~text
Tải ứng dụng trong 24 giờ:

Thấp thấp thấp | CAO CAO | thấp thấp thấp

Provisioned vCore:
Compute đã chọn luôn có mặt theo service objective,
không tự về 0 chỉ vì không có truy vấn.
~~~

Ưu điểm:

1. Tài nguyên được cấp theo mức dự kiến, phù hợp tải liên tục hoặc ổn định.
2. Tránh cơ chế auto-resume do auto-pause của serverless.
3. Dễ dự toán compute theo kích thước cấp phát trong kỳ.
4. Có thể phù hợp với reserved capacity/Azure Hybrid Benefit khi điều kiện cho phép.

Đánh đổi:

- Trả tiền compute cả khi database ít dùng theo mô hình billing tương ứng.
- Muốn đổi số vCore thường phải thay service objective, có thể ảnh hưởng kết nối/latency trong quá trình scale.
- Không có nghĩa ứng dụng sẽ luôn đạt performance tốt nếu query, locking hoặc mạng là nút thắt.

Provisioned thích hợp khi **cần độ trễ ổn định** và database có mức tải nền thường xuyên.

## 9. Serverless trong Azure SQL Database là gì?

**Serverless** là một **compute tier của mô hình vCore** cho **single database ở những service tier/cấu hình được hỗ trợ**. Nó có thể:

- Tự điều chỉnh compute trong khoảng **minimum vCores** và **maximum vCores** dựa trên nhu cầu.
- Tính phí compute theo mức sử dụng, mô hình tính tiền và điều kiện tier.
- Ở cấu hình hỗ trợ, **tự tạm dừng (auto-pause)** sau một khoảng thời gian không hoạt động.
- **Tự tiếp tục chạy (auto-resume)** khi một kết nối/hoạt động phù hợp kích hoạt.

~~~text
             Tải theo thời gian

vCores
   ^
  4|                  /----\
   |                 /      \
  2|        /-------/        \--
   |       /
0.5|------/
   +---------------------------------> giờ
      Nhàn   Tăng tải     Đạt đỉnh

Serverless: compute có thể tăng/giảm trong min/max đã chọn.
Auto-pause (nếu hỗ trợ) là hành vi riêng khi đủ điều kiện idle.
~~~

**Serverless không có nghĩa không có server và không có chi phí.** Dữ liệu vẫn nằm trên managed storage, có cơ chế backup và vẫn chịu các chi phí storage hoặc dịch vụ liên quan.

### Serverless không phải elastic pool

Serverless **co giãn compute của một database**. Elastic pool **chia sẻ ngân sách compute giữa nhiều database**. Trong bài học, không coi một serverless database như một pool nhiều tenant, và không giả định có thể đặt từng database trong elastic pool thành serverless giống single database.

### Những cấu hình có hỗ trợ serverless

Serverless có trong **General Purpose** và những cấu hình **Hyperscale** được Azure SQL Database hỗ trợ, nhưng **khả năng auto-pause/auto-resume không giống nhau ở mọi tier**. Đặc biệt, không mặc định Hyperscale serverless sẽ tự pause như cấu hình General Purpose serverless. Khi chọn SKU phải kiểm tra support matrix, region, hardware và tính năng đang bật.

## 10. Min vCores, max vCores và autoscaling

Một database serverless có thể được đặt:

~~~text
Min compute: 0,5 vCore (ví dụ, khi SKU hỗ trợ)
Max compute: 4 vCores
Idle window: auto-pause delay theo cấu hình hỗ trợ
~~~

Lúc tải thấp, database có thể sử dụng ít compute hơn mức tối đa; khi CPU/memory demand tăng, compute có thể tăng trong khoảng cho phép. Các giới hạn về I/O/log/worker, latency và memory vẫn tồn tại theo tier/hardware.

### Không cam kết autoscaling tức thời

Khi đột ngột có một trăm truy vấn nặng, compute không nhất thiết tăng lên max vCores trong cùng một mili giây. Thời gian phản ứng, memory pressure, workload mix và giới hạn dịch vụ đều ảnh hưởng kết quả.

### Chọn minimum quá thấp có thể gây vấn đề

- Tải nền có thể thiếu memory hoặc thường xuyên phải tăng compute.
- Các truy vấn đầu burst có thể chậm hơn so với provisioned.
- Những kết nối/nghiệp vụ nhạy latency có thể bị ảnh hưởng.

### Chọn maximum quá thấp cũng nguy hiểm

Nếu nhu cầu CPU liên tục tương đương tám vCores nhưng max chỉ là hai, database vẫn bị giới hạn. Serverless tự động scale **trong phạm vi đã cấu hình**, không tự tăng trần ngoài giới hạn kinh phí.

### Dữ liệu để quyết định

Đo:

- CPU và memory usage theo thời gian.
- Data I/O và log I/O percentages.
- Độ trễ transaction p95/p99.
- Số phiên kết nối, workers, sessions.
- Tần suất peak, độ dài peak và khoảng thời gian idle thực tế.

## 11. Auto-pause và auto-resume

Với **cấu hình serverless hỗ trợ auto-pause**, database có thể được tạm dừng sau khoảng thời gian idle. Khi được kích hoạt, database tự resume để phục vụ kết nối.

~~~text
22:00  Không còn truy vấn ứng dụng
       |
       | Không có hoạt động ngăn việc pause
       v
       Auto-pause delay trôi qua
       |
       v
    Database PAUSED
       |
08:00  Client tạo kết nối
       |
       v
    RESUMING
       |
       v
    ONLINE / kết nối xử lý được
~~~

Các thời điểm chỉ minh họa thứ tự, **không phải cam kết thời gian auto-resume**. Resume có thể tạo độ trễ mà client phải xử lý bằng timeout/retry có kiểm soát.

### Điều kiện để auto-pause hoạt động

Phải kiểm tra:

1. SKU/tier có hỗ trợ auto-pause không.
2. Auto-pause delay đã được cấu hình, không bị vô hiệu hóa.
3. Database không có sessions/hoạt động hoặc tính năng ngăn auto-pause theo quy định.
4. Không có job, monitoring query, health check hay connection pool liên tục đánh thức database.
5. Không bật những tính năng HA/replication hoặc trạng thái dịch vụ không tương thích với auto-pause.

**Đừng cho rằng cứ đặt auto-pause delay là database sẽ chắc chắn pause mỗi đêm.** Một health probe gửi SELECT 1 theo chu kỳ có thể giữ nó hoạt động, tùy cách ứng dụng và điều kiện tạm dừng.

### Cold start ảnh hưởng API thế nào?

Một API có SLA phản hồi 200 ms có thể không phù hợp với database bị pause nếu request đầu tiên phải chờ resume. Trong khi đó, hệ thống báo cáo nội bộ chạy vài lần/ngày có thể chấp nhận thời gian thức dậy.

Client nên có:

- Connection timeout và command timeout phù hợp.
- Retry có backoff/jitter cho các lỗi tạm thời thích hợp.
- Kịch bản người dùng thấy trạng thái “đang khởi động dữ liệu” nếu cần.
- Giới hạn số client cùng retry để tránh retry storm.

**Không retry vô hạn các thao tác ghi không idempotent.** Một timeout có thể xảy ra sau khi server đã ghi giao dịch thành công.

## 12. Chi phí serverless

Trong serverless, chi phí cần nhìn theo **compute sử dụng khi database hoạt động**, cấu hình min/max, memory/CPU billing và **chi phí lưu trữ**. Khi database thật sự auto-paused ở cấu hình hỗ trợ, compute không hoạt động có thể ngừng phát sinh phí compute tương ứng, nhưng storage và các dịch vụ liên quan vẫn tính tiền.

### Mô hình trực giác

~~~text
Tổng chi phí serverless trong kỳ
  ≈ Compute được tính tiền khi active
    + Storage/data size theo tier
    + Backup/retention vượt phần bao gồm nếu có
    + Network/monitoring/những tính năng liên quan
~~~

Đây không phải biểu phí chính thức. Azure SQL có các nguyên tắc billing, minimum compute, memory billing và giới hạn cụ thể tùy SKU. **Không nhân trực tiếp số vCore tối đa với toàn bộ 24 giờ rồi gọi đó là số tiền serverless**, cũng không mặc định 0 vCore-bill trong mọi giờ mà ứng dụng không gửi truy vấn.

### Một ví dụ định tính

| Workload | Serverless có thể tiết kiệm? | Cần kiểm chứng |
|---|---|---|
| Dev/test chỉ chạy giờ hành chính | Có thể, nếu được auto-pause và chấp nhận resume | Health check, connection pool, auto-pause eligibility |
| API công khai nhận request mỗi vài giây cả ngày | Có thể ít lợi thế | Compute bill khi active, latency và peak |
| Báo cáo batch đột biến hai lần/ngày | Có thể phù hợp | Thời gian batch, max compute và cold start |
| Thanh toán đòi phản hồi rất nhanh mọi lúc | Thường cần xem xét provisioned | SLO p99, kết nối và tính sẵn sàng |
| Phân tích dữ liệu liên tục nhiều giờ | Cần benchmark, chưa chắc rẻ | Compute active lâu và giới hạn tier |

Với dữ liệu production, hãy so sánh **chi phí dự kiến hàng tháng** trên Azure Pricing Calculator và quan sát billing thực sau khi thử cấu hình; không chọn serverless chỉ vì tên “serverless”.

## 13. Elastic pool là gì?

**Azure SQL Database elastic pool** là mô hình cho phép nhiều **cơ sở dữ liệu riêng biệt** dùng chung một ngân sách compute của pool. Mỗi database vẫn có schema, quyền, dữ liệu và kết nối độc lập theo thiết kế SQL Database; compute được chia sẻ dựa trên tổng tải và giới hạn pool/per-database.

~~~text
           SaaS ứng dụng multi-tenant
                        |
            +-----------+-----------+
            |           |           |
            v           v           v
         tenant-A     tenant-B     tenant-C
            \           |           /
             \          |          /
              +-------------------+
              | Azure SQL        |
              | Elastic Pool     |
              | Shared resources |
              +-------------------+
~~~

### Vì sao elastic pool phù hợp SaaS?

Một công ty có 50 khách hàng, mỗi người một database. Nếu mua cho mỗi database tài nguyên đủ chịu **peak đồng thời** dù chỉ cao tải vài phút/ngày, tổng compute nhàn rỗi rất lớn. Nếu peaks lệch nhau, pool cho phép chia tài nguyên hiệu quả hơn.

### Lưu ý quan trọng

- Pool có **giới hạn compute tổng**, storage và những quota khác.
- Mỗi database có **minimum/maximum resource settings** theo tier/pool.
- Nhiều database cùng peak có thể làm tài nguyên pool bão hòa.
- Pool không biến nhiều database thành một database chung.
- Pool không tự giải quyết truy vấn chậm hoặc phân vùng tenant kém.
- Điều kiện service tier, số databases, storage và billing phải được kiểm tra theo SKU.

## 14. Elastic pool: mô hình tài nguyên chia sẻ

Giả sử một pool vCore có ngân sách tính toán được cấu hình là **8 vCores** và chứa ba database:

~~~text
Pool capacity: 8 vCores (minh họa)

09:00:
  tenant-A dùng nhiều CPU
  tenant-B ít hoạt động
  tenant-C ít hoạt động
  -> pool có thể phục vụ peak A tốt

13:00:
  tenant-A dùng nhiều CPU
  tenant-B cũng peak
  tenant-C cũng peak
  -> tổng nhu cầu có thể vượt 8 vCores
~~~

Đây là ví dụ về ngân sách tổng, **không phải phép cộng đơn giản để dự đoán scheduler thực tế**. Pool còn có giới hạn I/O/log/memory, các giới hạn mỗi DB và cơ chế tài nguyên theo service tier.

### Giới hạn per-database

Nếu một tenant có thể chiếm gần hết pool, các tenant khác dễ bị ảnh hưởng. Cần kiểm soát **minimum và maximum resource per database**, phù hợp service objective của pool:

- **Minimum** đặt mức tài nguyên tối thiểu theo cấu hình được hỗ trợ.
- **Maximum** giới hạn lượng compute một database có thể tiêu thụ.
- Tổng các cam kết tối thiểu và mức công suất pool phải thỏa những ràng buộc cấu hình.

Đừng giả định “max mỗi DB = 8, pool 8” có nghĩa cả 20 DB đồng thời được dùng 8 vCores; mỗi DB chỉ có **trần tiềm năng**, không phải compute riêng được cấp đủ mọi lúc.

### Noisy neighbor

Một database có truy vấn quét bảng lớn có thể tiêu thụ CPU, I/O hoặc log throughput, làm tenant khác chậm theo cơ chế chia sẻ. Cần theo dõi cả:

1. **Pool resource utilization**.
2. **Per-database utilization**.
3. **Query/resource waits**.
4. **Business SLO** của từng tenant.

Nếu một tenant thường xuyên nặng, cân nhắc chuyển database đó sang single database hoặc một pool riêng có giới hạn phù hợp.

## 15. Khi nào elastic pool hiệu quả về chi phí?

Giả sử có 30 databases:

- Phần lớn có traffic rất thấp.
- Một số tăng tải ngắn vào giờ mở cửa.
- Các peak ít khi trùng nhau.
- Mỗi database phải tách dữ liệu và quyền theo khách hàng.

Pool có thể giảm compute nhàn rỗi vì không cần mua trần riêng cho mọi database.

Ngược lại, nếu **tất cả tenant đồng thời cao tải** vào 10:00–12:00 mỗi ngày, tổng compute cần thiết vẫn lớn. Một pool quá nhỏ sẽ chậm và retry nhiều, còn pool quá lớn gây chi phí nhàn rỗi.

### Cách so sánh

~~~text
Chi phí phương án A:
  Tổng compute/storage của N single databases

Chi phí phương án B:
  Compute/storage và những khoản phụ của elastic pool

Đánh giá thêm:
  p95/p99 latency
  Peak concurrency
  Data I/O và log I/O
  Query completion rate
  Thời gian quản trị và rủi ro noisy neighbor
~~~

Không chỉ cộng bảng giá list price; khi có reserved capacity, license benefit hoặc các mức storage/backup khác nhau, kết quả kinh tế thay đổi.

## 16. DTU elastic pool và vCore elastic pool

| Tiêu chí | DTU elastic pool | vCore elastic pool |
|---|---|---|
| Đơn vị compute | **eDTU** | **vCores** |
| Cách nhìn tài nguyên | Gói tổng hợp CPU/memory/I/O | vCore, hardware/tier và resource limits |
| Giới hạn mỗi DB | Theo cấu hình eDTU min/max | Theo cấu hình compute/resource của pool |
| Các tier | Các pool tiers của mô hình DTU theo khả năng | Tier vCore được hỗ trợ như General Purpose, Business Critical và lựa chọn khác theo thời điểm |
| Cost optimization | Chia eDTUs giữa các DB | Chia vCores và chọn tier/hardware/benefits phù hợp |
| Dùng khi | Tổ chức đã vận hành DTU hoặc muốn mức gộp | Cần kiểm soát compute minh bạch hơn |

**eDTU không thể đổi trực tiếp thành vCore bằng một tỉ lệ cố định áp cho mọi query**. Quy đổi cần đo workload thật và dùng guidance/tool estimation của Azure phù hợp, rồi test.

### Pool khác serverless ở mô hình billing

Elastic pool thường mua **ngân sách compute của pool**, trong khi serverless co giãn compute của single database và có thể auto-pause theo điều kiện. Một pool có 20 database cùng idle không mặc định auto-pause và ngừng tính phí giống serverless single database.

### Vấn đề storage

Phải xem cả giới hạn **max data size từng DB**, giới hạn **storage tổng của pool** và chi phí storage theo tier. Một pool có CPU đủ nhưng chứa vài database tăng dung lượng nhanh vẫn có thể gặp ngưỡng storage.

## 17. Chọn single database hay pool?

| Câu hỏi | Nghiêng về single database | Nghiêng về elastic pool |
|---|---|---|
| Có bao nhiêu database? | Một/vài DB riêng có tải đáng kể | Nhiều DB nhỏ và tương tự |
| Tải có ổn định không? | Tải riêng ổn định/dễ dự báo | Tải từng DB biến động và lệch nhau |
| Cần cách ly hiệu năng mạnh? | Có | Cần đánh giá noisy-neighbor và per-DB max |
| Có sự khác biệt lớn giữa các tenant? | Tenant lớn nên tách riêng | Tenant nhỏ khá đồng nhất dễ gom |
| Có yêu cầu auto-pause? | Serverless single DB có thể phù hợp | Pool không tự thay thế auto-pause |
| Chi phí compute nhàn rỗi? | Có thể cao nếu mỗi DB provisioned | Có thể tiết kiệm nếu mức sử dụng tổng thấp |
| Quản trị tenant lifecycle? | Không nhất thiết phức tạp | Cần theo dõi pool membership, per-DB limits |

### Một chiến lược hỗn hợp

SaaS production thường không cần chọn **tất cả** database vào một pool:

- Khách hàng nhỏ: chung một elastic pool.
- Khách hàng trung bình: nhóm theo workload hoặc SLO vào nhiều pool.
- Khách hàng lớn/đòi performance riêng: single database vCore provisioned.
- Dev/test hoặc công việc ngắt quãng: serverless single database nếu điều kiện phù hợp.

Mỗi tenant vẫn cần bảo mật dữ liệu và quyền riêng, bất kể compute được chia sẻ thế nào.

## 18. DTU và vCore: không có hệ số đổi cố định

Nhiều người hỏi: “100 DTU tương đương bao nhiêu vCore?” Câu trả lời đáng tin phải dựa trên **đặc tính workload**.

Ví dụ:

~~~text
Database X (DTU)
  CPU percent: 90%
  Data IO percent: 20%
  Log IO percent: 15%

Database Y (DTU)
  CPU percent: 25%
  Data IO percent: 95%
  Log IO percent: 85%

Hai DB có thể cùng mức DTU gần 100%,
nhưng X nghiêng về CPU và Y nghiêng về I/O.
~~~

Nếu chỉ dùng một phép đổi DTU→vCore mà không xem I/O limits, database Y có thể vẫn bị bóp nghẽn sau migration dù số vCore nhìn có vẻ đủ.

### Quy trình đánh giá migration

1. Thu thập **ít nhất một chu kỳ tải đại diện**, bao gồm giờ peak, batch, cuối tuần/cuối tháng khi cần.
2. Lưu metrics CPU, data I/O, log I/O, workers, sessions, latency.
3. Tìm query nặng, wait types, missing/unused indexes, transaction dài và blocking.
4. Xác định SLA/RPO/RTO và những tính năng phải giữ.
5. Chọn vCore SKU/tier/hardware ứng viên theo Azure guidance.
6. Thử tải ở môi trường gần production hoặc canary hợp lý.
7. So sánh hiệu năng và chi phí; chuẩn bị quay lại service objective phù hợp nếu cần.

**Không chuyển tier chỉ để sửa một truy vấn không có index** mà chưa phân tích tuning.

## 19. Đọc workload bằng các chỉ số nào?

| Metric/chỉ số | Nó cho biết gì? | Nếu cao, điều tra gì? |
|---|---|---|
| **DTU percentage** | Mức sử dụng so với ngân sách DTU | CPU/data I/O/log I/O nguồn gây giới hạn |
| **CPU percentage** | Mức CPU so với giới hạn | Query CPU, plans, concurrency, missing indexes |
| **Data IO percentage** | Áp lực đọc/ghi dữ liệu so với limit | Table scans, index design, read pattern |
| **Log IO percentage** | Áp lực ghi transaction log | Batch writes, transaction pattern, log bottleneck |
| **Memory usage** | Áp lực bộ nhớ theo giới hạn/metric được hỗ trợ | Sort/hash, plan cache, workload memory |
| **Workers percentage** | Khả năng xử lý yêu cầu đồng thời | Excess concurrency, long-running queries |
| **Sessions percentage** | Kết nối/sessions gần ngưỡng | Connection pooling/leaks, retry storm |
| **Storage used / max size** | Nguy cơ gần hết dung lượng | Growth, retention, indexing/archival |
| **Deadlocks / blocking / waits** | Vấn đề tranh chấp | Isolation, lock duration, indexing, transaction |
| **Query duration p95/p99** | Kết quả khách hàng nhìn thấy | Query Store, execution plans, backend/network |

**Một metric cao không tự là nguyên nhân gốc.** Chẳng hạn CPU cao do liên tục retry một truy vấn bị deadlock; chỉ tăng compute chưa sửa được deadlock.

### Cần tách ba cấp quan sát

1. **Database:** database đang chạm resource limits nào?
2. **Pool:** tổng vCore/eDTU, workers/IO và những database cùng peak?
3. **Application:** request rate, latency, timeout, connection pool, 429/5xx và business SLO?

Nếu chỉ xem tổng pool, có thể bỏ qua một tenant đã chạm per-database max dù pool vẫn còn phần compute chưa dùng.

## 20. T-SQL: kiểm tra resource usage từ database

Các lệnh bên dưới **chỉ đọc** và cần quyền thích hợp. Chạy trên **Azure SQL Database** cần đo, bằng kết nối được cấp quyền, không dùng trên dữ liệu production nếu chưa cân nhắc chính sách giám sát và log.

### Thống kê resource gần đây

~~~sql
SELECT TOP (100)
    end_time,
    avg_cpu_percent,
    avg_data_io_percent,
    avg_log_write_percent,
    avg_memory_usage_percent
FROM sys.dm_db_resource_stats
ORDER BY end_time DESC;
~~~

**sys.dm_db_resource_stats** cung cấp thông tin theo mẫu thời gian cho database hiện tại; khoảng thời gian lưu thống kê và các trường sẵn có phụ thuộc Azure SQL Database. Muốn xem xu hướng nhiều ngày/tuần, sử dụng Azure Monitor, Query Store hoặc kho telemetry với retention phù hợp.

### Kiểm tra mức tài nguyên và cấu hình hiện hành

~~~sql
SELECT
    name,
    state_desc,
    compatibility_level
FROM sys.databases
ORDER BY name;
~~~

Truy vấn này **không** đủ để kết luận số DTU/vCore hay thông số serverless. Cần kết hợp **Azure resource properties**/service objective và metrics.

### Kiểm tra các truy vấn có chi phí cao

**Query Store** của Azure SQL Database (khi được bật và cấu hình) cho phép phân tích lịch sử thực thi và regression. Với workload chậm, hãy xem Query Store ở Azure portal/SSMS/Azure Data Studio hoặc truy vấn DMV/Query Store phù hợp.

Không tự tạo index hàng loạt dựa trên một snapshot missing index suggestions. Index mới có thể làm tăng storage và chi phí ghi.

## 21. Đo peak, median và chu kỳ tải

Một giờ sử dụng 90% CPU không đại diện cho cả tháng. Khi chọn serverless hay pool, cần đo tải ở nhiều độ phân giải:

~~~text
Theo phút:
  phát hiện burst và timeout

Theo giờ:
  thấy thời điểm hệ thống đạt đỉnh trong ngày

Theo ngày/tuần:
  thấy chu kỳ nghiệp vụ

Theo tháng/quý:
  thấy batch cuối kỳ, chiến dịch, sự kiện lớn
~~~

### Bảng baseline mẫu

| Chỉ số | Ban ngày | Ban đêm | Peak cuối tháng |
|---|---:|---:|---:|
| CPU tương đối | 35% | 2% | 85% |
| Data I/O tương đối | 20% | 1% | 70% |
| Log I/O tương đối | 25% | 1% | 90% |
| Request/s | 80 | 0–2 | 500 |
| Latency p95 | 70 ms | 50 ms | 900 ms |

**Số liệu là ví dụ giả định để học cách phân tích**, không phải benchmark chính thức hay dự báo của một SKU Azure nào.

Từ bảng này:

- Serverless có thể đáng thử nếu database thực sự **idle đủ dài** để giảm compute và không có điều kiện ngăn pause.
- Provisioned đáng thử nếu latency p95 phải ổn định trong mọi thời điểm.
- Nếu 30 tenant có peak lệch nhau, elastic pool có thể có lợi; nếu tất cả peak cuối tháng cùng lúc, cần tăng tổng pool hoặc tách nhóm.

## 22. Các mô hình tính tiền cần phân biệt

| Phương án | Compute được nhìn theo | Storage | Lưu ý |
|---|---|---|---|
| DTU single | Service objective/DTUs đã chọn | Theo giới hạn/biểu phí của tier | Gói tài nguyên gộp |
| vCore provisioned single | VCore đã cấp phát theo SKU/tier | Theo đặc tính/biểu phí vCore tier | Có thể xem reserved capacity/benefits nếu hỗ trợ |
| vCore serverless single | Compute sử dụng và các mức tối thiểu theo billing model | Vẫn có phí storage/backup liên quan | Auto-pause nếu được hỗ trợ và thật sự xảy ra |
| DTU pool | eDTU pool | Theo pool và data sizes | Cần tính toàn bộ databases trong pool |
| vCore pool | vCore pool | Theo cấu hình pool/data size | Không nhân full peak mỗi DB khi peaks lệch |

### Không nhầm giá compute và storage

VCore provisioned thường cho phép nhìn compute và storage rõ hơn, nhưng mức giá vẫn phụ thuộc **region, tier, hardware, redundancy, backup retention và chương trình ưu đãi**. DTU có cấu trúc giá/giới hạn riêng. Một model so sánh tài chính nên thể hiện:

~~~text
TCO hàng tháng xấp xỉ:
  Database compute
  + Data storage
  + Backup/PITR/LTR chi phí phụ nếu có
  + Networking/Private Endpoint và dịch vụ liên quan
  + Monitoring/Log Analytics
  + Chi phí vận hành và migration
~~~

Không tự điền một đơn giá USD cố định vào giáo trình vì bảng giá có thể thay đổi. Sử dụng Azure Pricing Calculator và Azure Cost Management theo region/offer đang dùng.

## 23. Azure Hybrid Benefit và reserved capacity

Một lý do một tổ chức chọn vCore provisioned là khả năng tối ưu hóa license và chi phí theo chương trình Azure phù hợp.

### Azure Hybrid Benefit

Đối với khách hàng có **SQL Server licenses đủ điều kiện**, Azure Hybrid Benefit có thể giúp giảm phần chi phí license trong những SKU/dịch vụ được hỗ trợ. Điều kiện phụ thuộc loại license, Software Assurance/subscription và các quy tắc của Microsoft.

Không tự áp dụng benefit chỉ vì doanh nghiệp “có mua SQL Server trước đây”; cần kiểm tra **điều kiện pháp lý/license compliance và SKU hỗ trợ** với nhóm phụ trách.

### Reserved capacity

Các hình thức đặt trước capacity được hỗ trợ có thể hữu ích cho workload chạy ổn định dài hạn. Nhưng nếu database thường idle và tự pause, cam kết cố định có thể không phải lựa chọn kinh tế nhất.

### Đánh giá tổng thể

So sánh:

- Giá pay-as-you-go.
- Giá sau license benefit nếu hợp lệ.
- Giá theo reserved capacity nếu đáp ứng điều kiện.
- Khả năng phải thay đổi workload/tier trong kỳ.
- Rủi ro cam kết quá lớn so với nhu cầu.

Không sử dụng một mức giảm giá giả định làm cơ sở duy nhất cho quyết định architecture.

## 24. Serverless và connection pooling

Một vấn đề thực tế của serverless là **database không pause** vì ứng dụng liên tục tạo kết nối hoặc chạy health checks.

~~~text
Application pool
    |
    +--> connection 1 vẫn hoạt động
    +--> connection 2 vẫn hoạt động
    +--> health check SELECT 1 định kỳ
    |
    v
Azure SQL serverless database
    |
    +--> Có thể không đạt điều kiện idle để auto-pause
~~~

### Cần xem xét

1. Mức idle thật sự của database, không chỉ request HTTP.
2. Connection pool ở App Service, Functions, AKS hoặc VM.
3. Background jobs, maintenance, scheduled queries và monitoring.
4. Các tính năng database có thể ngăn pause.
5. Cơ chế retry/backoff khi resume.

Không “tắt hết health checks” bừa bãi chỉ để tiết kiệm compute. Health checks còn có ý nghĩa vận hành; cần thiết kế phương pháp phù hợp giữa SLO và điều kiện auto-pause.

### Pooling và timeouts của client

Nếu có 100 application instances cùng resume một database, request đầu có thể đồng thời timeout/retry, tạo áp lực mới. Cần:

- Max pool size và retry có giới hạn.
- Backoff/jitter.
- Idempotency cho các thao tác ghi.
- Theo dõi connection failures và thời gian mở kết nối.
- Cân nhắc provisioned nếu workload có yêu cầu phục vụ liên tục.

## 25. Serverless và các tính năng có điều kiện

Một số chức năng và cấu hình có thể ảnh hưởng việc chọn serverless hoặc auto-pause:

- Active geo-replication/failover groups theo ma trận hỗ trợ.
- Long-term retention, data sync hoặc những tính năng quản trị liên quan theo cấu hình.
- Private endpoint/firewall và các đường kết nối/monitoring; **không phải mọi tính năng mạng đều ngăn auto-pause**, nhưng phải xác minh.
- Hyperscale serverless với hành vi auto-pause riêng.
- HA/zone redundancy hoặc backup restore options tùy service tier.
- Các hoạt động nền cần thiết làm database không được coi là idle.

**Không kết luận mọi tính năng liệt kê đều luôn bị cấm trên serverless.** Đây là checklist tương thích; phải đối chiếu tài liệu tính năng, SKU và tình trạng database trước khi chuyển.

## 26. Elastic pool và vấn đề SaaS multi-tenant

Với mô hình **database-per-tenant**, pool giảm chi phí compute nhưng ứng dụng vẫn phải quản lý:

1. **Tenant routing:** kết nối đúng database theo tenant đã xác thực.
2. **Schema migration:** áp migration cho nhiều database có giám sát.
3. **Backup/recovery:** một database cần phục hồi độc lập không làm hỏng tenant khác.
4. **Per-tenant SLO:** đo latency và lượng sử dụng của từng tenant.
5. **Noisy neighbor:** cô lập hoặc chuyển tenant lớn khi cần.
6. **Security:** SQL users/Entra ID, firewall, private endpoint và secret rotation.
7. **Lifecycle:** tạo, nâng cấp, chuyển pool hoặc xóa database theo workflow có phê duyệt.

~~~text
Authenticated API request
        |
        v
Tenant registry / authorization
        |
        v
Database mapping
        |
        +--> Tenant A -> Pool 1, database A
        +--> Tenant B -> Pool 1, database B
        +--> Tenant C -> Pool 2, database C
        +--> Tenant D -> Single database (dedicated)
~~~

**Elastic pool không bảo đảm phân quyền giữa tenant**. Database riêng giúp xây dựng ranh giới dữ liệu, nhưng API phải xác thực tenant và không cho phép user tự chọn một database khác qua header/query chưa được kiểm tra.

## 27. Bảo mật và mạng cho cả bốn mô hình

Dù database dùng DTU, vCore, serverless hay pool, các nguyên tắc bảo mật vẫn tương tự:

### Danh tính và quyền

- Ưu tiên **Microsoft Entra authentication** hoặc managed identity ở những ứng dụng/dịch vụ hỗ trợ.
- Cấp quyền database tối thiểu theo vai trò.
- Tránh dùng SQL admin cho mọi kết nối ứng dụng.
- Không nhúng password/connection string vào source code, image hoặc tài liệu.
- Sử dụng Key Vault/secret management và quy trình rotate.

### Kết nối mạng

- Cấu hình firewall, private endpoint và private DNS khi yêu cầu.
- Kiểm tra đường kết nối từ App Service, AKS, Functions/VM tới SQL endpoint.
- Dùng TLS và cấu hình client driver phù hợp.
- Không mở public network access trên toàn Internet chỉ để sửa lỗi kết nối.
- Đối chiếu NSG/UDR/Azure Firewall và chính sách egress trong VNet.

### Kiểm soát dữ liệu

- Backup/PITR và retention theo yêu cầu.
- Mã hóa at rest/in transit theo khả năng dịch vụ và chính sách.
- Auditing và log truy vấn phù hợp, tránh lộ PII/secrets.
- Data masking/row-level security khi cần nhưng không thay thế authorization ở ứng dụng.

**Chọn elastic pool không thay đổi trách nhiệm bảo mật dữ liệu giữa các tenants.**

## 28. Availability, backup và DR

Khi chọn service tier và compute model, phải đánh giá:

- SLA và tính sẵn sàng của SKU hiện hành.
- Redundancy/failover khi hạ tầng có sự cố.
- Zone redundancy và multi-region DR nếu dịch vụ/tier cho phép.
- Automated backups, PITR và long-term retention theo cấu hình hỗ trợ.
- Restore time và backup storage/geo-restore limitations.
- Ảnh hưởng khi database scale/chuyển tier hoặc tự resume.

### Không nhầm auto-pause với failover

**Auto-pause** của serverless là việc tạm dừng compute khi idle, phục vụ tiết kiệm tài nguyên trong cấu hình cho phép. **Failover/HA** là phản ứng khi xảy ra lỗi hạ tầng. Hai hiện tượng có thể đều làm kết nối bị gián đoạn tạm thời nhưng nguyên nhân và yêu cầu xử lý khác nhau.

### Không nhầm elastic pool với replication

Nhiều database trong một elastic pool vẫn sử dụng một ngân sách compute chung. Điều đó **không tạo bản sao dữ liệu ở region khác** và không tự bảo đảm DR. Backup/replication phải được thiết kế theo từng database và tier.

### Thử khôi phục có kiểm chứng

Một backup báo thành công chưa đủ chứng minh đáp ứng RPO/RTO. Cần restore drill tại môi trường cô lập, kiểm tra schema, record counts, transaction integrity và thời gian end-to-end, rồi mới khẳng định chiến lược dữ liệu đủ an toàn.

## 29. Azure portal: quy trình đánh giá lựa chọn

Các bước sau hướng đến **quan sát và lập kế hoạch**. Khi thực sự thay cấu hình database có thể phát sinh phí hoặc ảnh hưởng kết nối; phải được phê duyệt và chạy trên tài nguyên lab trước.

### Bước 1: xác định database

1. Chọn subscription và resource group đúng.
2. Mở tài nguyên **SQL databases** và chọn database cần đánh giá.
3. Xem logical server, region, trạng thái, service tier và compute model.
4. Kiểm tra database thuộc elastic pool hay single database.
5. Xác định owner, ứng dụng dùng database và SLA.

### Bước 2: xem Compute + storage

Trong phần cấu hình compute/storage theo giao diện hiện hành:

- Nếu dùng DTU: xem tier và service objective.
- Nếu dùng vCore: xem tier, hardware và số vCore.
- Nếu dùng serverless: xem min/max compute và auto-pause khi hỗ trợ.
- Nếu dùng elastic pool: xem ngân sách pool, storage và per-DB limits.

### Bước 3: mở Metrics và Query Performance

Lấy biểu đồ đủ thời gian phản ánh peak:

- CPU, data I/O, log I/O, DTU usage nếu dùng DTU.
- Storage, workers/sessions và connection failures.
- Query Store/tuning findings và app p95 latency.
- Với pool: cùng lúc xem tổng pool và từng database.

### Bước 4: mô phỏng phương án

So sánh:

1. Single DTU hiện tại.
2. Single vCore provisioned.
3. Single serverless nếu tương thích và idle rõ ràng.
4. Elastic pool cho nhóm databases có peak lệch nhau.

Đo hiệu năng trước/sau trên môi trường kiểm thử, không thay production chỉ vì calculator có số tiền thấp hơn.

## 30. Azure CLI: kiểm tra cấu hình read-only

Các lệnh bên dưới chỉ **đọc tài nguyên Azure**, không tạo, scale hoặc xóa database. Điền thông tin của subscription và môi trường được cấp quyền.

### Xác định subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az account show \
  --query "{subscription:id,name:name,tenantId:tenantId}" \
  --output json
~~~

### Xem logical server

~~~bash
az sql server show \
  --resource-group "rg-sql-lab" \
  --name "sql-demo-server" \
  --query "{name:name,location:location,version:version}" \
  --output json
~~~

### Xem single database

~~~bash
az sql db show \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --name "orders-db" \
  --query "{name:name,status:status,sku:sku,computeModel:computeModel,minCapacity:minCapacity,autoPauseDelay:autoPauseDelay,elasticPoolName:elasticPoolName,maxSizeBytes:maxSizeBytes}" \
  --output json
~~~

Một trường có thể null/vắng tùy compute model và Azure API. Ví dụ, autoPauseDelay không có ý nghĩa như nhau với mọi DTU/vCore SKU. Xem full JSON khi cần xác nhận cấu trúc thực, không tự sửa cấu hình để “làm hiện ra” một field.

### Liệt kê databases

~~~bash
az sql db list \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --query "[].{name:name,sku:sku,status:status,elasticPoolName:elasticPoolName}" \
  --output table
~~~

### Xem elastic pools

~~~bash
az sql elastic-pool list \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --output json

az sql elastic-pool show \
  --resource-group "rg-sql-lab" \
  --server "sql-demo-server" \
  --name "tenant-pool" \
  --output json
~~~

Đối chiếu SKU, capacity, perDatabaseSettings và storage limits trong kết quả thực tế. **Chỉ đọc cấu hình không chứng minh pool đủ năng lực**; cần Azure Monitor và latency theo tenant.

## 31. T-SQL: quan sát chậm và tranh chấp tài nguyên

Một database có p95 latency cao có thể do:

- Query scan nhiều dữ liệu.
- Index không phù hợp.
- Blocking/deadlocks.
- Transaction kéo dài.
- CPU throttling.
- Log write throttling.
- Connection/session exhaustion.

Một hướng chẩn đoán:

~~~text
Client p95 latency tăng
         |
         v
Database CPU/IO/log có đạt giới hạn?
      /          \
     Có          Không
     |             |
     v             v
Xem resource     Xem blocking, waits,
limitations      network, query plans,
và query nặng    app connection pool
     |
     v
Thử tuning / sizing trong lab
~~~

### Đừng dùng DMV như bằng chứng duy nhất

DMVs có thời hạn giữ dữ liệu và thông tin theo sampling. Với workload nhiều ngày, sử dụng **Azure Monitor**/Query Store và logs có retention. Nếu workload có spikes ngắn, đồ thị trung bình theo giờ có thể che khuất vấn đề.

### Đánh giá query tuning trước upscale

Ví dụ một truy vấn lọc theo customerId nhưng bảng không có index phù hợp có thể quét hàng triệu rows. Thay đổi index đúng làm giảm data I/O và CPU đáng kể, có thể rẻ hơn việc tăng nhiều vCore. Nhưng index mới cũng tăng chi phí ghi và dung lượng; phải đo trước/sau trên dữ liệu gần thực tế.

## 32. Migration: đổi DTU sang vCore

**Thay service objective** có thể là hoạt động được Azure SQL Database hỗ trợ, nhưng phải tính tới giới hạn, thời gian scale, ảnh hưởng kết nối và khả năng đổi lại.

### Trước khi đổi

1. Chụp lại current SKU/service objective, max size và features.
2. Lưu biểu đồ metrics trong một chu kỳ đại diện.
3. Đánh giá phần mềm client/drivers, connection retry và transaction semantics.
4. Đối chiếu unsupported/incompatible features ở tier đích.
5. Tính storage/backup/replication/quota và giá theo region.
6. Phân công người phê duyệt, lịch thay đổi, phương án rollback.

### Trong khi đổi

1. Thực hiện trên lab hoặc môi trường staging trước.
2. Theo dõi operation status/provisioning.
3. Kiểm tra kết nối có thể gián đoạn và client retry phù hợp.
4. Không chạy benchmark đầy tải đồng thời với hoạt động thay đổi lớn nếu không có kế hoạch.

### Sau khi đổi

1. Xác nhận service objective mới được áp dụng.
2. Kiểm tra chức năng login, read/write và các transaction nghiệp vụ.
3. So sánh CPU/IO/log/waits và latency p95/p99 ở cùng loại tải.
4. Kiểm tra backup/PITR/DR, alerts và logs.
5. Đo billing/cost trong thời gian đủ dài.

**Rollback không phải lúc nào chỉ là chọn lại gói cũ.** Một số chuyển đổi tier/hardware/dung lượng có ràng buộc, thời gian hoặc giới hạn quay lại. Cần nắm điều kiện trước khi change.

## 33. Migration: đưa database vào hoặc ra elastic pool

### Những điểm cần cân nhắc

- Pool và database phải thỏa điều kiện region/logical server/tier và các ràng buộc của dịch vụ.
- Dữ liệu không tự biến mất khi database chuyển pool, nhưng performance/cost và service objective có thể thay đổi.
- Database lớn có thể chiếm tài nguyên quá nhiều, ảnh hưởng pool.
- Một pool ở ngưỡng storage hoặc compute có thể không nhận thêm database.
- Các tính năng riêng của single database/elastic pool cần được xác minh tương thích.

### Quy trình

1. Lập danh sách databases và peak đồng thời.
2. Xác định pool SKU, total compute và per-DB min/max.
3. Kiểm tra storage và những database lớn bất thường.
4. Di chuyển **một nhóm nhỏ** vào pool lab/canary.
5. Theo dõi pool metrics, latency theo DB và connection failures.
6. Tăng dần số DB nếu có dư địa thực.
7. Cài cảnh báo cho noisy-neighbor và capacity.
8. Có quy trình tách tenant nặng sang single database hoặc pool khác.

Không gom 100 tenants vào một pool chỉ vì trung bình mỗi DB nhàn rỗi; phải đo **cùng thời điểm** và khả năng gặp sự kiện peak toàn bộ tenant.

## 34. Dùng serverless cho môi trường phát triển và kiểm thử

Một ví dụ hợp lý là môi trường dev/test chỉ được dùng trong giờ làm việc:

~~~text
Developer chạy test: 09:00–18:00
Ban đêm: rất ít hoạt động
Database: serverless single DB, cấu hình auto-pause nếu hỗ trợ
~~~

Ưu điểm:

- Có cơ hội giảm compute bill ở thời gian không sử dụng.
- Không phải duy trì mức vCore provisioned lớn 24/7 cho một DB test.

Những điều phải kiểm tra:

- CI pipeline chạy test lúc nửa đêm có làm database resume không?
- Tools/health checks có giữ connection liên tục không?
- Integration tests có timeout do resume không?
- Database có backup/retention và dữ liệu kiểm thử cần giữ không?
- Tính năng cần dùng có tương thích serverless và auto-pause không?

Không bật serverless cho production chỉ vì thành công trên môi trường dev/test; traffic, yêu cầu latency và tính năng khác nhau.

## 35. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| DTU gần 100% và API chậm | CPU/data I/O/log I/O đạt giới hạn | Đo ba nhóm metrics và query plans |
| Tăng DTU nhưng không nhanh hơn | Blocking, deadlocks, network hoặc query không tối ưu | Query Store, waits, application traces |
| Chuyển sang vCore cùng “con số” nhưng chậm | Không có tỉ lệ DTU→vCore 1:1, hardware/I/O khác | So sánh resource limits và benchmark |
| Serverless không auto-pause | Tính năng chưa hỗ trợ, có session/hoạt động nền hoặc cấu hình delay | Kiểm tra SKU, autoPauseDelay, connections và hoạt động |
| Request đầu sau idle chậm | Cold start/auto-resume | Xem database state và thời gian kết nối, điều chỉnh SLO |
| Serverless bill cao dù ít giao dịch | Database không pause hoặc compute active/worker nền | Xem usage hours, metrics, config và billing |
| Serverless chạm max vCores | Nhu cầu vượt trần hoặc query nặng | Đo CPU/waits, tối ưu và cân nhắc tăng max |
| Pool đủ vCore nhưng một DB chậm | Per-DB max/IO giới hạn, query lock hoặc memory | Xem per-database metrics và pool settings |
| Nhiều tenant chậm cùng giờ | Noisy neighbor hoặc peak đồng thời vượt pool | Theo dõi tổng pool và từng database |
| Pool tăng storage bất thường | Một vài tenant tăng dữ liệu/index | Xem max size/used storage và retention |
| Connection timeout sau đổi tier | Scale/reconfiguration, network hoặc client retry kém | Correlate time, Azure Activity Log, client driver |
| Azure SQL trả lỗi 401/18456 | Authentication/RBAC/SQL login | Xác định Entra ID, SQL permissions, token |
| App không kết nối Private Endpoint | DNS/NSG/UDR/firewall, không phải DTU/vCore | Kiểm tra DNS và đường TCP/TLS |
| Giá ước tính thấp nhưng bill cao | Storage/backup/network/monitoring hoặc billing compute khác giả định | Cost Analysis theo resource/SKU/tier |
| Pool membership hiển thị sai | Đang xem logical server/resource group khác hoặc thay đổi đang chạy | Azure resource ID, subscription và CLI show |

### Quy trình chẩn đoán sáu bước

1. **Scope:** đúng subscription, logical server, database và pool?
2. **Model:** DTU/vCore, provisioned/serverless, tier và SKU nào?
3. **Resources:** CPU/data I/O/log I/O, memory, workers, storage có chạm trần?
4. **Query/application:** Query Store, waits, blocking và connection pool có vấn đề?
5. **Infrastructure:** auth, DNS, firewall/private endpoint và scale/reconfiguration?
6. **Costs/SLO:** giải pháp đang trả bao nhiêu, latency/throughput có đáp ứng?

Không tự xóa database/recreate pool khi xuất hiện timeout. Trước tiên phân loại lỗi và bảo vệ dữ liệu/khả năng khôi phục.

## 36. Case study: 24 database SaaS và tải không đều

Một nhà cung cấp SaaS quản lý 24 khách hàng, mỗi khách có một Azure SQL Database. Thông tin quan sát:

- **18 tenant nhỏ:** trung bình dùng tương đương 0,2 vCore mỗi tenant, peak tối đa 1 vCore, thường vào các giờ khác nhau.
- **4 tenant trung bình:** trung bình khoảng 0,7 vCore, peak 2 vCores.
- **2 tenant lớn:** dùng thường xuyên 2–4 vCores, có peak cao trong thời gian dài.
- Có một DB quản trị nội bộ chỉ chạy báo cáo vào cuối ngày.
- API production cần p95 query latency dưới 150 ms ở tải thường.
- Dữ liệu tài chính yêu cầu backup/PITR và khả năng phục hồi được kiểm thử.

### Nhiệm vụ

1. Giải thích vì sao mô hình “mỗi tenant một provisioned database bằng peak” dễ lãng phí.
2. Chọn nhóm tenant nào có thể vào elastic pool, nhóm nào nên single database.
3. Giải thích tại sao trung bình 18 x 0,2 vCore **không đủ** để quyết định pool capacity.
4. Đề xuất một cách đo concurrency/peak của các tenant.
5. Thiết kế per-DB maximum phù hợp để hạn chế noisy neighbor.
6. Đánh giá DB báo cáo cuối ngày có phù hợp serverless không.
7. So sánh DTU pool với vCore pool theo metrics và chi phí.
8. Nêu các điều kiện khác nhau giữa General Purpose, Business Critical và Hyperscale.
9. Đề xuất kế hoạch migration canary, rollback và quan sát.
10. Xác định metrics cần cảnh báo tại pool và database.
11. Nêu chiến lược quyền truy cập tenant, private networking và backup.
12. Tạo bảng dự toán TCO với compute, storage, backup, monitoring và công vận hành.

### Gợi ý lời giải

- **18 tenant nhỏ:** có thể thử một hoặc vài elastic pools vì peak lệch nhau.
- **4 tenant trung bình:** đánh giá pool riêng hoặc cùng nhóm nhỏ khi số liệu đồng thời cho phép.
- **2 tenant lớn:** có thể đặt single provisioned để có ngân sách compute riêng và SLO rõ ràng.
- **DB báo cáo nội bộ:** thử serverless single DB nếu giai đoạn idle dài, tính năng tương thích và chấp nhận thời gian resume.

Lưu ý các số **0,2/0,7 vCore** trong tình huống là giá trị đo/mô hình giả định, không phải cách Azure báo một vCore fractional cho mọi SKU. Quyết định cuối phải dựa trên **capacity/sku thực tế**, metrics và load test.

## 37. Bài tập tính capacity pool sơ bộ

Giả sử có 12 database:

~~~text
Mỗi DB:
  peak demand dự kiến = 2 vCore

Nhưng peak đồng thời:
  thông thường 2 DB cùng peak
  thỉnh thoảng 4 DB cùng peak

Nhu cầu compute peak khái niệm:
  2 x 2 = 4 vCores (thông thường)
  4 x 2 = 8 vCores (sự kiện hiếm)
~~~

Một pool 8 vCores **có thể là ứng viên thử nghiệm** nhưng chưa đủ bằng chứng cho production, vì:

- CPU không phải tài nguyên duy nhất.
- I/O và log throughput có thể bão hòa trước.
- Những database khác vẫn tiêu thụ tải nền.
- Per-DB max và tier limits có thể tác động.
- Peaks có thể đồng thời hơn dự kiến khi có chiến dịch hoặc batch.
- Cần dự phòng headroom cho spike và sự cố.

Chỉ dùng phép cộng này để chọn **danh sách cấu hình cần benchmark**, không coi đó là bảo đảm SLO hoặc mức giá chuẩn.

## 38. Checklist chọn mô hình trước production

| Nhóm | Câu hỏi nghiệm thu |
|---|---|
| Loại dịch vụ | Đúng Azure SQL Database hay là Managed Instance/VM/PostgreSQL? |
| Workload | Có baseline nhiều ngày, peak đồng thời và business SLO? |
| DTU | Đã xem CPU/data I/O/log I/O chứ không chỉ DTU percentage? |
| vCore | Tier, hardware, vCores, resource limits và storage phù hợp? |
| Provisioned | Tải nền đủ để duy trì compute cố định? |
| Serverless | SKU tương thích, min/max hợp lý, auto-pause thực sự có thể xảy ra? |
| Resume | Client retry/backoff, timeout và SLO có chấp nhận cold start? |
| Elastic pool | Nhiều database có tải lệch nhau, có số liệu đồng thời? |
| Per-DB limits | Không có tenant chiếm quá nhiều compute/IO pool? |
| Storage | Max size mỗi DB/pool, data growth và backup retention phù hợp? |
| Query tuning | Đã dùng Query Store/waits/index analysis trước scale? |
| HA/DR | Backup/PITR, zone/geo redundancy và restore drill phù hợp? |
| Security | Entra ID/managed identity, RBAC, TLS, private endpoint khi cần? |
| Cost | Compute + storage + backups + monitor + network được dự toán? |
| Migration | Có canary, change window, rollback và validation? |
| Observability | Alert CPU/IO/log/workers/connections/storage và p95 latency? |
| Documentation | Database owner, service objective và lý do chọn đã được ghi lại? |

## 39. Câu hỏi tự kiểm tra

1. DTU được dùng để biểu diễn những loại tài nguyên nào?
2. Vì sao 100 DTU không tương đương 100 transaction/second?
3. eDTU khác DTU single database ra sao?
4. vCore model giúp nhìn tài nguyên theo cách nào?
5. Một vCore có luôn là một CPU vật lý riêng biệt không?
6. Basic/Standard/Premium thuộc mô hình nào?
7. General Purpose, Business Critical và Hyperscale khác nhau về định hướng gì?
8. Provisioned compute có tự về 0 khi database idle không?
9. Serverless có nghĩa là không có storage cost không?
10. Serverless có tự mở rộng vượt max vCores đã cấu hình không?
11. Auto-pause có luôn sẵn cho mọi Hyperscale serverless database không?
12. Vì sao health check hoặc connection pool có thể ngăn auto-pause?
13. Độ trễ auto-resume ảnh hưởng API như thế nào?
14. Vì sao phải thiết kế retry idempotent sau timeout?
15. Elastic pool đem lại lợi ích lớn khi các DB có peak đồng thời hay lệch nhau?
16. Vì sao pool có thể gặp noisy-neighbor?
17. Per-database maximum trong pool giải quyết vấn đề gì?
18. Vì sao không nhân số vCore tối đa của từng DB rồi khẳng định pool luôn có tổng compute đó?
19. Có thể đổi eDTU sang vCore theo một tỉ lệ cố định không?
20. Khi DTU đạt 100%, những metrics nào cần xem trước?
21. Một database bị log I/O throttling có tự cải thiện nếu chỉ thêm CPU không?
22. Vì sao Query Store quan trọng khi chọn size?
23. Serverless single DB và elastic pool khác nhau ở mô hình co giãn nào?
24. Reserved capacity và Azure Hybrid Benefit có những điều kiện gì cần kiểm tra?
25. Vì sao elastic pool không tự tạo geo-replication cho dữ liệu?
26. Nếu chuyển DB giữa các tier, những bước nghiệm thu nào bắt buộc?
27. Tại sao một canary nhỏ hữu ích khi gom database vào pool?
28. Làm thế nào xác định serverless rẻ hơn provisioned cho một workload cụ thể?
29. Những loại chi phí nào dễ bị bỏ sót khi nhìn giá compute?
30. Với 20 tenant và tải không đều, bạn sẽ phân nhóm database ra sao?

## Tài liệu tham khảo

- Microsoft Learn — *Azure SQL Database overview*: https://learn.microsoft.com/azure/azure-sql/database/sql-database-paas-overview
- Microsoft Learn — *DTU-based purchasing model*: https://learn.microsoft.com/azure/azure-sql/database/service-tiers-dtu
- Microsoft Learn — *vCore-based purchasing model*: https://learn.microsoft.com/azure/azure-sql/database/service-tiers-sql-database-vcore
- Microsoft Learn — *General Purpose service tier*: https://learn.microsoft.com/azure/azure-sql/database/service-tier-general-purpose
- Microsoft Learn — *Business Critical service tier*: https://learn.microsoft.com/azure/azure-sql/database/service-tier-business-critical
- Microsoft Learn — *Hyperscale service tier*: https://learn.microsoft.com/azure/azure-sql/database/service-tier-hyperscale
- Microsoft Learn — *Serverless compute tier for Azure SQL Database*: https://learn.microsoft.com/azure/azure-sql/database/serverless-tier-overview
- Microsoft Learn — *Elastic pools in Azure SQL Database*: https://learn.microsoft.com/azure/azure-sql/database/elastic-pool-overview
- Microsoft Learn — *Resource limits for single databases*: https://learn.microsoft.com/azure/azure-sql/database/resource-limits-vcore-single-databases
- Microsoft Learn — *Resource limits for elastic pools*: https://learn.microsoft.com/azure/azure-sql/database/resource-limits-vcore-elastic-pools
- Microsoft Learn — *Monitoring and performance tuning in Azure SQL Database*: https://learn.microsoft.com/azure/azure-sql/database/monitor-tune-overview
- Microsoft Learn — *sys.dm_db_resource_stats*: https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-db-resource-stats-azure-sql-database
- Microsoft Learn — *Azure SQL Database pricing*: https://azure.microsoft.com/pricing/details/azure-sql-database/
- Microsoft Learn — *Azure Hybrid Benefit for Azure SQL*: https://learn.microsoft.com/azure/azure-sql/azure-hybrid-benefit
