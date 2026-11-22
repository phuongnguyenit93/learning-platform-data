# Lựa chọn Exadata theo yêu cầu hiệu năng và vị trí dữ liệu

## 1. Mục tiêu của quyết định kiến trúc

Trong chương **Exadata và Cloud@Customer** của lộ trình Oracle Cloud Infrastructure (OCI), lựa chọn Exadata cần bắt đầu từ yêu cầu của hệ thống: giao dịch phải nhanh đến mức nào, dữ liệu được phép nằm ở đâu, ứng dụng kết nối từ đâu và ai chịu trách nhiệm vận hành.

Bài học hướng dẫn cách đi từ các yêu cầu đó đến một quyết định có thể kiểm chứng. Phạm vi bao gồm đánh giá workload Oracle Database, vị trí primary và các bản sao, kết nối mạng, khả năng mở rộng, tính sẵn sàng, phân quyền, giám sát và chi phí.

Sau bài học, bạn có thể:

- Phân biệt nhu cầu tăng hiệu năng với nhu cầu thay đổi vị trí triển khai.
- Xác định chỉ số cần đo trước khi chọn cấu hình Exadata.
- So sánh Exadata Database Service trên OCI với Exadata Database Service on Cloud@Customer theo ràng buộc thực tế.
- Thiết kế thử nghiệm để xác nhận độ trễ ứng dụng, công suất và khả năng hoạt động khi thiếu một phần tài nguyên.
- Viết quyết định lựa chọn có giả định, bằng chứng và điều kiện phải xem xét lại.

Nguyên tắc xuyên suốt là **loại phương án không đáp ứng điều kiện bắt buộc trước, rồi mới tối ưu trong các phương án khả thi**. Một cấu hình có throughput cao không thể bù cho việc dữ liệu bị đặt sai phạm vi đã được tổ chức phê duyệt.

## 2. Tách bốn câu hỏi thường bị gộp thành một

### 2.1. Có cần Exadata không?

Exadata tích hợp phần mềm và hạ tầng tối ưu cho Oracle Database. Tuy nhiên, “database đang chậm” chưa phải bằng chứng phải chuyển lên Exadata.

Cần xác định nguyên nhân chính:

- SQL đọc quá nhiều dữ liệu hoặc có execution plan không phù hợp.
- Thiếu CPU, bộ nhớ hoặc năng lực I/O tại tải đỉnh.
- Lock contention, hot block hoặc giao dịch giữ khóa lâu.
- Ứng dụng gọi database quá nhiều lần qua mạng.
- Nhiều workload tranh chấp cùng tài nguyên.
- Hạ tầng hiện tại không còn đáp ứng yêu cầu tăng trưởng và sẵn sàng.

Nếu nguyên nhân là gọi database tuần tự hàng trăm lần cho một request, tăng tốc xử lý trong database chỉ giải quyết một phần. Nếu nguyên nhân là SQL sai logic, phải sửa logic trước khi dùng kết quả đo để sizing.

Đánh giá Exadata nên giữ một đường cơ sở: hệ thống hiện tại sau các tối ưu hợp lý và phương án Oracle Database nhỏ hơn nếu có thể đáp ứng. Với workload vừa phải, ít tăng trưởng và không cần đặc tính của Exadata, phương án khác có thể phù hợp hơn về công suất lẫn vận hành.

### 2.2. Cần mô hình vận hành nào?

Cùng công nghệ Exadata nhưng phạm vi tự quản lý có thể khác nhau. Exadata Database Service là dịch vụ đồng quản lý; không nên diễn giải thành việc Oracle vận hành toàn bộ ứng dụng và dữ liệu thay khách hàng.

Nhóm dự án phải xác định ai quản lý database, cấu hình truy cập, bản vá trong phạm vi khách hàng, lịch backup, kiểm tra recovery và kết nối ứng dụng. Nếu cần mức tự động hóa khác, phải đánh giá riêng dịch vụ tương ứng thay vì suy từ tên phần cứng.

### 2.3. Dữ liệu và ứng dụng sẽ đặt ở đâu?

Database gần người dùng chưa chắc gần ứng dụng. Người dùng có thể ở Việt Nam, nhưng application server lại nằm tại một cloud region khác. Chặng mạng ứng dụng–database thường là thành phần trực tiếp trong thời gian xử lý request.

Cần phân biệt:

- Vị trí người dùng.
- Vị trí application server và connection pool.
- Vị trí primary database.
- Vị trí standby, backup, bản phục hồi thử và dữ liệu phân tích.
- Vị trí hệ thống quản lý khóa, giám sát và nhật ký liên quan.

### 2.4. Chọn cấu hình và quy mô nào?

Chỉ sau khi xác định được mô hình, vị trí và workload mới chọn tài nguyên. Cấu hình phải đáp ứng tải đỉnh, tăng trưởng, công việc nền và các tình huống thiếu tài nguyên đã cam kết.

Không chọn theo dung lượng database đơn thuần. Hai database cùng 10 TB có thể có nhu cầu hoàn toàn khác nhau: một hệ thống thực hiện lookup ngắn, một hệ thống liên tục quét và tổng hợp nhiều TB dữ liệu.

## 3. Phân biệt các phương án triển khai

| Phương án | Nơi đặt hạ tầng | Đặc điểm cần đưa vào đánh giá |
| --- | --- | --- |
| Exadata Database Service on Dedicated Infrastructure trong OCI | Hạ tầng Exadata dành riêng cho khách hàng tại cloud region cung cấp dịch vụ | Kết nối với ứng dụng, khả năng cung cấp tài nguyên, giới hạn dịch vụ và trách nhiệm đồng quản lý |
| Exadata Database Service on Exascale Infrastructure trong OCI | Tài nguyên từ hạ tầng cloud dùng chung theo mô hình dịch vụ | Mức cách ly cần thiết, cách cấp tài nguyên, quy mô khởi đầu và khả năng cung cấp tại region |
| Exadata Database Service on Cloud@Customer | Hạ tầng tại trung tâm dữ liệu khách hàng hoặc địa điểm được chỉ định theo dịch vụ | Điều kiện site, kết nối quản trị OCI, vận hành tại chỗ và các luồng dữ liệu ra ngoài |
| Exadata Database Machine do tổ chức tự triển khai | Địa điểm do tổ chức lựa chọn và chuẩn bị | Mô hình mua sắm, hỗ trợ và trách nhiệm vận hành khác dịch vụ cloud |

Oracle mô tả các lựa chọn dịch vụ gồm dedicated, Exascale dùng chung và Cloud@Customer. Các lựa chọn này khác về vị trí và cách cấp hạ tầng; cần xác nhận khả năng cung cấp tại địa điểm dự kiến. [FAQ Exadata Database Service](https://www.oracle.com/engineered-systems/exadata/database-service/faq/).

Bảng không có nghĩa mọi tổ hợp phiên bản, topology và dịch vụ đều tương đương. Cũng không nên dùng từ “Cloud@Customer” để chỉ một Exadata Database Machine tự mua đặt trong phòng máy; đó là các mô hình dịch vụ và trách nhiệm khác nhau.

Ngoài OCI còn có các lựa chọn triển khai Exadata trong một số môi trường cloud khác. Khi ứng dụng nằm ở đó, có thể đưa lựa chọn được hỗ trợ vào danh sách ứng viên; phải đánh giá riêng vị trí thực, tính năng và điều kiện dịch vụ. Bài này tập trung vào quy trình lựa chọn trong bối cảnh OCI và Cloud@Customer.

Các thông số thế hệ phần cứng, đơn vị tính compute, shape, mức cấp phát tối thiểu và giá có thể thay đổi. Hồ sơ quyết định phải ghi đúng dịch vụ, thế hệ, region và thời điểm báo giá; không dùng một bảng cấu hình cũ làm cam kết triển khai.

## 4. Chuyển yêu cầu nghiệp vụ thành hồ sơ workload

### 4.1. Xác định loại công việc và thời điểm xảy ra

Một inventory nên phân tách OLTP, báo cáo, batch, ETL và công việc vận hành.

| Thành phần | Thông tin cần thu thập | Lý do |
| --- | --- | --- |
| Giao dịch trực tuyến | Giao dịch/giây, số request đồng thời, thời gian phản hồi p95/p99, tỷ lệ lỗi | Đánh giá khả năng phục vụ và độ trễ đuôi |
| SQL quan trọng | Tần suất, elapsed time, CPU time, logical/physical reads, plan | Xác định việc gì thực sự tiêu thụ tài nguyên |
| Batch và ETL | Thời gian bắt đầu, cửa sổ hoàn thành, dữ liệu đọc/ghi, mức song song | Phát hiện tải trùng với OLTP |
| Dữ liệu | Dung lượng đã dùng, tăng trưởng, hot working set, LOB và index | Sizing storage, bộ nhớ và cache |
| Redo và commit | Tốc độ sinh redo, tần suất commit, thời gian chờ liên quan | Đánh giá đường ghi và nhu cầu bảo vệ dữ liệu |
| Vận hành | Backup, phục hồi, thu thập thống kê, bảo trì, tạo bản thử | Tránh sizing chỉ cho tải ứng dụng |
| Mạng | RTT, jitter, packet loss, throughput hữu dụng, số lượt trao đổi | Đánh giá vị trí ứng dụng–database |

p95 là ngưỡng mà khoảng 95% quan sát không vượt quá; p99 tương tự cho 99%. Phải nêu loại giao dịch, cửa sổ đo, tải và số mẫu. Một giá trị p95 trộn login, tìm kiếm và xuất báo cáo không cho biết giao dịch nào đang vi phạm mục tiêu.

Số session mở không bằng số session đang cần CPU. Một connection pool có nhiều kết nối chờ công việc không chứng minh database cần thêm compute.

### 4.2. Thu thập đủ chu kỳ kinh doanh

Không sizing chỉ từ trung bình CPU một ngày. Cần bao quát các chu kỳ có ảnh hưởng:

- Giờ cao điểm hằng ngày.
- Chốt sổ, cuối tháng hoặc cuối kỳ.
- Chiến dịch tăng tải và nhập dữ liệu lớn.
- Backup trùng với báo cáo hoặc ETL.
- Giai đoạn sau bảo trì, khi cache chưa ổn định.
- Tình huống thiếu một node hoặc đang bảo trì một phần hạ tầng.

Dùng telemetry hệ điều hành, trace ứng dụng, chỉ số database và công cụ quan sát được cấp quyền. Nếu dùng AWR, ASH, SQL Monitor hoặc công cụ có điều kiện sử dụng riêng, cần xác nhận quyền sử dụng phù hợp với dịch vụ và hợp đồng.

### 4.3. Đặt mục tiêu đo được

Ví dụ yêu cầu giả định:

~~~text
Giao dịch tạo đơn:
- 1.200 giao dịch/giây ở tải mục tiêu.
- p95 không quá 150 ms.
- p99 không quá 400 ms.
- Tỷ lệ lỗi không quá 0,1% trong cửa sổ kiểm thử.
- Đo từ application server qua đúng topology production dự kiến.

Batch cuối ngày:
- Xử lý bộ dữ liệu đại diện trong không quá 45 phút.
- Chạy đồng thời với tải trực tuyến đã thống nhất.
- Tải trực tuyến vẫn đáp ứng các ngưỡng riêng.

Tăng trưởng:
- Dữ liệu tăng 25%/năm trong kịch bản cơ sở.
- Có thêm kịch bản tăng nhanh và quy trình cấp tài nguyên bổ sung.
~~~

Các số trên là dữ liệu thiết kế minh họa, không phải thông số hay SLA của Oracle. Chúng phải do nghiệp vụ và nhóm kỹ thuật xác nhận trước PoC.

## 5. Đánh giá lợi ích hiệu năng theo nút thắt

### 5.1. OLTP cần kiểm tra cả đọc, ghi và tranh chấp

Với OLTP, các phép đo có ích gồm thời gian thực hiện SQL ngắn, độ trễ commit, lookup theo index, số giao dịch đồng thời và độ ổn định khi tải tăng.

Exadata có kiến trúc database server, storage server thông minh và kết nối nội bộ tối ưu cho Oracle Database. Tuy nhiên, lợi ích cụ thể phụ thuộc kiểu truy cập, cache, tài nguyên và thiết kế ứng dụng. [Kiến trúc Exadata](https://www.oracle.com/database/technologies/exadata/architecture/).

Không suy từ độ trễ I/O nội bộ được công bố ra độ trễ request HTTP. Một request còn có thời gian xếp hàng, xử lý Java, nhiều SQL, trao đổi mạng và tích hợp ngoài database.

Những vấn đề như một hàng dữ liệu bị cập nhật tuần tự hoặc giao dịch giữ khóa quá lâu cần được phân tích riêng. Thêm tài nguyên không tự loại bỏ giới hạn do tuần tự hóa.

### 5.2. Phân tích và quét dữ liệu

Smart Scan có thể đẩy một phần xử lý SQL xuống storage server, giảm dữ liệu cần chuyển về database server đối với các thao tác phù hợp. Điều này tạo cơ sở kỹ thuật để thử Exadata cho workload quét và phân tích lớn. [Exadata Smart Scan](https://www.oracle.com/database/technologies/exadata/software/smartscan/).

Không phải mọi câu SQL đều dùng Smart Scan hoặc hưởng lợi như nhau. Trong PoC phải kiểm tra execution plan, dữ liệu thực sự được đọc, mức offload quan sát được và elapsed time tại tải cần phục vụ.

Đừng thiết kế thử nghiệm chỉ bằng một truy vấn quét rất thuận lợi rồi dùng kết quả đó đại diện cho ứng dụng chủ yếu thực hiện lookup ngắn.

### 5.3. Hợp nhất nhiều database

Một mục tiêu khác là đưa nhiều database lên cùng hạ tầng. Lợi ích có thể đến từ sử dụng tài nguyên hiệu quả hơn và chuẩn hóa vận hành, nhưng cần kiểm soát tranh chấp.

Phải lập lịch tải tổng hợp:

~~~text
09:00–11:00: giao dịch trực tuyến tăng cao
10:00–12:00: báo cáo quản trị
22:00–01:00: batch và ETL
23:00–03:00: backup
Ngày cuối tháng: batch kéo dài sang giờ sáng
~~~

Đánh giá resource management và mức cách ly ở các lớp được dịch vụ hỗ trợ. Tách database thành nhiều PDB hoặc VM cluster không làm tổng CPU, bộ nhớ và I/O trở nên vô hạn.

Đơn vị hợp nhất cũng phải xét quyền quản trị, lịch nâng cấp, phạm vi lỗi và yêu cầu vị trí dữ liệu. Hai database có yêu cầu địa điểm khác nhau không nên được gộp chỉ vì tổng dung lượng vừa một hệ thống.

## 6. Vị trí ứng dụng có thể quyết định kết quả hiệu năng

### 6.1. Tính chi phí của các lượt trao đổi tuần tự

Một mô hình đơn giản cho request:

~~~text
Thời gian request xấp xỉ =
    xử lý ứng dụng
  + xử lý trong database
  + tổng thời gian trao đổi qua mạng
  + xếp hàng và các phụ thuộc khác
~~~

Giả sử một request cần 30 lượt trao đổi ứng dụng–database tuần tự. Nếu RTT trong mô hình cố định là 12 ms, riêng phần chờ mạng xấp xỉ:

~~~text
30 × 12 ms = 360 ms
~~~

Nếu đặt ứng dụng gần database và RTT trong cùng mô hình giảm còn 1 ms, phần tương ứng là 30 ms.

Đây là phép tính minh họa cho các lượt trao đổi tuần tự, không phải dự đoán p95 hoặc p99 của một dịch vụ thực. Không cộng các percentile riêng lẻ để suy ra percentile toàn request; phải đo request hoàn chỉnh.

Kết quả cho thấy một hướng suy luận thiết kế: database xử lý SQL nhanh hơn chưa chắc cải thiện đủ trải nghiệm nếu ứng dụng vẫn phải qua đường mạng xa nhiều lần.

### 6.2. Ba cách xử lý cần so sánh

1. Đặt application server gần database tại địa điểm được phép.
2. Giảm số lượt trao đổi bằng batching, điều chỉnh fetch size, gom thao tác hoặc sửa cách truy cập dữ liệu.
3. Giữ ứng dụng tại chỗ và chọn database gần các phụ thuộc khó di chuyển.

Với ứng dụng Java, kiểm tra ORM sinh bao nhiêu SQL cho mỗi request, lỗi N+1, connection pool, kích thước tập kết quả và thời gian giữ kết nối. Chuyển database mà không quan sát lớp này dễ tạo kết luận sai về nền tảng.

Không tăng batch hoặc fetch size một cách máy móc: phải đo bộ nhớ, transaction size, thời gian giữ khóa và lượng dữ liệu ứng dụng thực sự cần.

### 6.3. Đường truyền riêng không làm khoảng cách biến mất

FastConnect có thể là một thành phần của kết nối với OCI, nhưng tên dịch vụ kết nối không bảo đảm mọi yêu cầu độ trễ ứng dụng đều đạt. Độ trễ còn phụ thuộc vị trí, tuyến thực, thiết bị, tải và thiết kế mạng.

Với mỗi ứng viên, đo:

- RTT và độ biến động từ application server thực tế.
- Thông lượng hữu dụng cho tải dữ liệu lớn.
- Hành vi khi một tuyến kết nối bị gián đoạn.
- DNS, routing, firewall và khả năng truy cập endpoint cần thiết.
- Hiệu năng khi backup, replication và ứng dụng cùng sử dụng đường truyền.

Dịch vụ Exadata trong OCI cần thiết kế VCN, client network, backup network và các tuyến tới dịch vụ liên quan theo yêu cầu chính thức. [Thiết lập mạng Exadata Cloud Infrastructure](https://docs.oracle.com/en-us/iaas/exadatacloud/doc/ecs-network-setup.html).

## 7. Xác định vị trí dữ liệu bằng bản đồ các bản sao

### 7.1. Phân biệt các loại yêu cầu

Trong bài này:

- **Vị trí dữ liệu**: dữ liệu hoặc một bản sao nằm ở địa điểm nào.
- **Phạm vi truy cập**: ai, từ đâu và theo cơ chế nào có thể truy cập.
- **Quyền kiểm soát**: tổ chức nào quản lý khóa, quyền, thay đổi và hoạt động vận hành.
- **Khả năng chứng minh**: bằng chứng nào xác nhận các điều trên đang được tuân thủ.

Đây là các chiều đánh giá kiến trúc. Một tên region, mã hóa TDE hoặc địa chỉ trung tâm dữ liệu không tự chứng minh toàn bộ yêu cầu quản trị.

Không tự diễn giải quy định pháp lý thành yêu cầu kỹ thuật. Nhóm phụ trách chính sách cần cung cấp phạm vi đã xác nhận, chẳng hạn: “dữ liệu nghiệp vụ và mọi bản phục hồi phải nằm trong hai địa điểm được duyệt”. Sau đó nhóm kiến trúc chuyển phạm vi đó thành cấu hình và bằng chứng.

### 7.2. Kiểm kê cả dữ liệu ngoài primary

| Loại dữ liệu/bản sao | Câu hỏi phải trả lời |
| --- | --- |
| Primary datafile, redo và dữ liệu tạm | Nằm ở đâu trong hoạt động bình thường? |
| Standby và redo được truyền | Địa điểm DR có thuộc phạm vi được phép không? |
| Backup và bản sao lưu dài hạn | Đích, vùng lưu, thời hạn giữ và bản sao bổ sung là gì? |
| Restore diễn tập và môi trường phát triển | Có dữ liệu thật được phục hồi ra nơi khác không? |
| Export, ETL, báo cáo và cache | Dữ liệu có tiếp tục đi sang nền tảng phân tích hoặc hệ thống tích hợp không? |
| Log, audit, trace và hỗ trợ | Có chứa SQL, bind value, thông tin nhận diện hoặc dữ liệu nghiệp vụ không? |
| Khóa và bí mật truy cập | Nằm ở đâu, ai quản lý và đường khôi phục là gì? |
| Metadata và telemetry dịch vụ | Nội dung nào được gửi tới hệ thống quản trị, theo cấu hình nào? |

Với mỗi luồng, ghi ít nhất: loại dữ liệu, nguồn, đích, mục đích, giao thức, người chịu trách nhiệm và bằng chứng cấu hình.

Không gộp toàn bộ telemetry thành dữ liệu nghiệp vụ, cũng không mặc định telemetry không nhạy cảm. Phải xác định nội dung và cơ chế xử lý cụ thể.

### 7.3. Cloud@Customer cần được đánh giá đúng ranh giới

Ở Cloud@Customer, database VM cluster nằm trên hạ tầng tại trung tâm dữ liệu khách hàng; control plane server kết nối với OCI region cho automation và quản trị. Đây là hai luồng cần phân biệt trong thiết kế. [Mạng Exadata Cloud@Customer](https://docs.oracle.com/en/engineered-systems/exadata-cloud-at-customer/eccid/exacc_network.html).

Đặt primary tại chỗ không tự ngăn backup đi ra cloud. Cloud@Customer có các lựa chọn backup khác nhau; nếu dùng OCI Object Storage phải thiết kế kết nối phù hợp, còn NFS hoặc ZDLRA tại chỗ có yêu cầu khác. [Yêu cầu mạng Cloud@Customer](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-network-requirements.html).

Vì vậy, không mô tả Cloud@Customer mặc định là hệ thống hoàn toàn ngắt kết nối. Cũng không tự kết luận điều gì sẽ tiếp tục hoặc dừng khi mất kết nối OCI; phải xác nhận hành vi của từng chức năng theo tài liệu, cấu hình và thử nghiệm.

Khách hàng cần kiểm soát truy cập mạng, VM và database trong phạm vi trách nhiệm của mình. Các kiểm soát dịch vụ không thay thế quyền người dùng database hoặc phân quyền ứng dụng. [Hướng dẫn bảo mật Cloud@Customer](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-secguide.html).

### 7.4. Sơ đồ cần vẽ trước khi chọn nơi triển khai

~~~mermaid
flowchart TB
    REQ["Yêu cầu nghiệp vụ và phạm vi dữ liệu đã xác nhận"]
    INV["Inventory: dữ liệu, bản sao, ứng dụng, tích hợp"]
    LOC["Các địa điểm ứng viên"]
    GATE{"Đáp ứng điều kiện bắt buộc?"}
    POC["Đo ứng dụng, workload, mạng và khả năng phục hồi"]
    COST["Tính chi phí toàn hệ thống"]
    DEC["Quyết định và điều kiện xem xét lại"]
    REV["Điều chỉnh phương án hoặc yêu cầu"]

    REQ --> INV
    INV --> LOC
    LOC --> GATE
    GATE -->|"Có"| POC
    GATE -->|"Không"| REV
    POC --> COST
    COST --> DEC
    REV --> LOC
~~~

Điều kiện bắt buộc có thể gồm địa điểm, quyền kiểm soát, tương thích phiên bản, khả năng kết nối hoặc thời hạn triển khai. Chỉ các ứng viên vượt qua bước này mới nên được so sánh bằng điểm ưu tiên.

## 8. Sizing theo nhiều chiều tài nguyên

### 8.1. Compute và bộ nhớ phải dựa trên đo đạc

Không sao chép nguyên số core của máy cũ sang báo giá mới rồi xem đó là sizing hoàn chỉnh. Cần xét thế hệ CPU, đơn vị cấp phát của dịch vụ, concurrency, hiệu năng mỗi core và workload đã tối ưu.

Tách các đại lượng:

- Tài nguyên vật lý của hạ tầng.
- Phần tài nguyên cấp cho VM cluster.
- Phần compute được kích hoạt hoặc tính phí theo dịch vụ.
- Tài nguyên có thể sử dụng sau khi một thành phần không còn phục vụ.
- Nhu cầu thật của các database chạy đồng thời.

Tăng compute không có nghĩa mọi tài nguyên liên quan tăng cùng tỷ lệ. Cần kiểm tra cơ chế cấp phát bộ nhớ, storage và khả năng mở rộng của đúng dịch vụ. Oracle mô tả riêng các lựa chọn scaling và cấu hình Exadata Dedicated Infrastructure. [Mô tả dịch vụ Dedicated Infrastructure](https://docs.oracle.com/en-us/iaas/exadatacloud/doc/exa-service-desc.html).

Với bộ nhớ, xem nhu cầu SGA, PGA, hệ điều hành, tác vụ vận hành và mức song song. Working set nóng và bộ nhớ cần cho sort/hash quan trọng hơn việc cố làm toàn bộ database vừa RAM.

### 8.2. Dung lượng phải dùng cùng đơn vị và cùng lớp

Cần phân biệt:

- Raw capacity của thiết bị.
- Usable capacity sau cơ chế bảo vệ và phân bổ của nền tảng.
- Dung lượng đã cấp cho database hoặc vùng lưu.
- Dung lượng thực đã sử dụng.
- Phần dành cho tăng trưởng, hoạt động tạm thời và vận hành.

Không so sánh raw TB của một phương án với usable TB của phương án khác. Cũng không coi dung lượng flash/cache công bố là dung lượng dữ liệu bổ sung có thể sử dụng tùy ý.

Ví dụ sizing giả định, tất cả số dưới đây dùng TB thập phân và đã cùng lớp **usable**:

~~~text
Dữ liệu nghiệp vụ hiện tại:                       12,00 TB
Tăng trưởng 25%/năm trong 3 năm:
    12 × 1,25^3                                  23,44 TB

TEMP dự trù tại thời điểm thiết kế:                3,00 TB
UNDO dự trù:                                      1,00 TB
Vùng recovery cục bộ dự trù:                       6,00 TB
Tổng nhu cầu sử dụng minh họa:                    33,44 TB

Nếu đặt mục tiêu sử dụng tối đa 80%:
    usable capacity cần có ≈ 33,44 / 0,80         41,80 TB
~~~

Đây không phải cấu hình Oracle bán sẵn hay tỷ lệ dự phòng được khuyến nghị cho mọi hệ thống. Khi áp dụng, phải đối chiếu từng thành phần lưu trữ thực tế, các giới hạn nền tảng và nhu cầu dự phòng/rebalance do dịch vụ quy định để tránh tính trùng hoặc bỏ sót.

Standby và backup ngoài hệ thống cần được sizing riêng. Không lấy số 41,80 TB rồi tuyên bố đã bao gồm mọi bản sao.

### 8.3. Sizing khi thiếu một phần tài nguyên

Giả sử PoC đã chuẩn hóa công suất thành một đơn vị CPU hiệu dụng cho cùng workload:

~~~text
Nhu cầu tải đỉnh:                   84 đơn vị
Hai node, mỗi node cung cấp:        64 đơn vị

Bình thường:                       128 đơn vị
Sau khi mất một node:                64 đơn vị
~~~

Cấu hình đủ khi bình thường nhưng không đủ cho tải đỉnh nếu chỉ còn một node.

Nếu mô hình có ba node với cùng công suất, sau khi mất một node còn 128 đơn vị. Để giữ mức sử dụng mục tiêu không quá 70%, ngân sách nhu cầu là 89,6 đơn vị, cao hơn 84 đơn vị trong ví dụ.

Đây là bài toán công suất khái niệm, không phải quy đổi OCPU/ECPU hoặc cam kết shape có thể mua. PoC vẫn phải xác nhận phân bố tải, giới hạn từng node và hành vi ứng dụng; tài nguyên không phải lúc nào cũng phân phối hoàn hảo.

### 8.4. Số core không thay cho throughput lưu trữ

Đối với workload vừa OLTP vừa batch, kiểm tra đồng thời:

- Độ trễ đọc/ghi tại mức tải cần phục vụ.
- IOPS và kích thước I/O.
- Throughput đọc quét, tải nhập dữ liệu và backup.
- Tốc độ sinh redo và năng lực phục vụ replication.
- Độ suy giảm khi có công việc nền hoặc thiếu thành phần.

Một phương án có CPU dư nhưng storage hoặc mạng đã bão hòa vẫn có thể vi phạm p99. Sizing cần chỉ ra tài nguyên nào dự kiến chạm giới hạn trước và hành động mở rộng tương ứng.

## 9. Tính sẵn sàng là điều kiện chọn địa điểm

Không thể hoàn thành quyết định vị trí primary nếu chưa chọn vị trí phục hồi.

Cần trả lời:

- Primary và standby có chung nguồn điện, rack, hạ tầng hoặc đường truyền không?
- Địa điểm DR có được phép giữ cùng loại dữ liệu không?
- Ứng dụng có chuyển sang địa điểm đó được không?
- Năng lực standby có đủ tiếp nhận tải mục tiêu?
- Backup có nằm ngoài miền sự cố cần bảo vệ?
- Nhóm vận hành có truy cập được khóa và công cụ phục hồi khi site chính mất?

RPO là mức mất dữ liệu chấp nhận được; RTO là thời gian khôi phục dịch vụ theo mốc đã thống nhất. Đưa cả hai vào bảng yêu cầu cho từng kịch bản, thay vì ghi chung “cần HA”.

RAC, Data Guard và backup có phạm vi bảo vệ khác nhau. Trong quyết định lựa chọn, điều cần làm là bảo đảm phương án có đủ địa điểm, tài nguyên, mạng và ngân sách cho các cơ chế cần dùng.

Ví dụ: chọn Cloud@Customer tại site A vì yêu cầu primary ở tại chỗ vẫn còn thiếu nếu mục tiêu mất site cần một standby tại site B nhưng B chưa sẵn sàng hoặc không được phép giữ dữ liệu.

Ngược lại, chọn OCI region cho primary chưa tự chứng minh RTO nếu ứng dụng và tuyến kết nối dự phòng vẫn phụ thuộc trung tâm dữ liệu vừa mất.

## 10. Điều kiện triển khai và trách nhiệm vận hành

### 10.1. Với Cloud@Customer

Phải kiểm tra site trước khi chốt lịch:

- Không gian, đường vận chuyển và tải trọng sàn.
- Điện, nguồn dự phòng, tiếp địa và làm mát.
- Cáp, uplink, IP, VLAN, DNS, NTP và tuyến cần thiết.
- Chính sách cho phép kết nối quản trị tới OCI.
- Quy trình tiếp cận thiết bị, bảo trì và phối hợp sự cố.

Các yêu cầu vật lý phụ thuộc cấu hình và thế hệ; cần khảo sát theo tài liệu hiện hành. [Yêu cầu site cho Cloud@Customer](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-site-requirements.html).

Việc chưa có đủ điện hoặc chưa thông được kết nối quản trị là điều kiện chưa đáp ứng, không phải nhược điểm có thể bù bằng điểm benchmark cao.

### 10.2. Với Exadata trong OCI

Phải kiểm tra khả năng cung cấp dịch vụ và tài nguyên tại region, quota/limit, thiết kế VCN/subnet, kết nối ứng dụng, IAM, DNS và đường tới dịch vụ cần thiết.

Không dùng việc tạo thành công một VM nhỏ để kết luận hạ tầng Exadata mong muốn chắc chắn có thể cấp ngay. Cần xác nhận khả năng triển khai thực tế của ứng viên và lịch dự án.

### 10.3. Phân định trách nhiệm

Một ma trận trách nhiệm của dự án nên chỉ rõ:

| Công việc | Câu hỏi cần chốt |
| --- | --- |
| Hạ tầng và bảo trì nền tảng | Oracle làm phần nào, khách hàng cần chuẩn bị hoặc phối hợp phần nào? |
| Database và phần mềm trong phạm vi khách hàng | Ai lập lịch, kiểm tra tương thích và xác nhận sau thay đổi? |
| Mạng | Nhóm nào quản lý VCN, kết nối riêng, firewall tại chỗ và DNS? |
| Backup và recovery | Ai đặt retention, kiểm tra điểm bảo vệ và restore diễn tập? |
| Khóa và quyền | Ai quản lý IAM, quyền database, keystore và audit? |
| Ứng dụng | Ai sửa kết nối, retry, timeout và kiểm tra giao dịch? |
| Giám sát | Ai nhận cảnh báo, xử lý và đo mục tiêu dịch vụ? |

Ma trận là cách tổ chức công việc, không thay cho phạm vi trách nhiệm chính thức của từng dịch vụ.

Automation qua Console/API hoặc công cụ khai báo có thể hỗ trợ chuẩn hóa triển khai. Tuy nhiên, vẫn phải có người sở hữu cấu hình, kiểm tra kết quả và xử lý thay đổi sau migration.

## 11. Lập kế hoạch PoC có tiêu chí đạt từ trước

### 11.1. Chọn dữ liệu và workload đại diện

Một PoC có ích phải phản ánh ứng dụng dự kiến vận hành:

- Dữ liệu đủ lớn để thể hiện hot/cold working set, phân bố và skew.
- SQL, transaction mix và tỷ lệ đọc/ghi giống giai đoạn quan trọng.
- Số client, arrival rate và thời gian chạy đủ để quan sát tải ổn định.
- Cùng topology ứng dụng–database dự kiến.
- Các công việc đồng thời như batch, backup hoặc ETL.
- Cấu hình bảo mật và mạng tương đương mục tiêu.

Nếu dữ liệu thật không được phép đưa vào môi trường PoC, dùng dữ liệu tổng hợp hoặc đã xử lý phù hợp. Phải kiểm tra việc xử lý có làm thay đổi độ phân bố, tỷ lệ nén hoặc hành vi truy vấn đáng kể không.

### 11.2. Cố định điều kiện so sánh

Mỗi lần đo cần lưu:

~~~text
Ứng viên và vị trí:
- Dịch vụ, region/site, thế hệ hạ tầng, cấu hình được cấp.

Database:
- Phiên bản, bản vá, tham số liên quan, schema và statistics.
- Đặc điểm execution plan của các SQL quan trọng.

Ứng dụng:
- Phiên bản, JVM, pool, cấu hình truy cập và điểm đặt client.

Dữ liệu và tải:
- Dung lượng, phân bố, transaction mix, arrival rate, concurrency.
- Thời gian warm-up, thời gian đo và hoạt động nền.

Kết quả:
- Throughput thành công, p50/p95/p99, tỷ lệ lỗi.
- CPU, bộ nhớ, I/O, mạng, redo và các điểm chờ chính.
~~~

Không so kết quả chạy một mình trên ứng viên A với kết quả đang backup trên B rồi quy toàn bộ chênh lệch cho vị trí triển khai. Nếu các điều kiện bắt buộc khác nhau, ghi rõ khác biệt và đo tác động của chúng.

### 11.3. Các pha kiểm thử cần có

| Pha | Mục tiêu | Bằng chứng |
| --- | --- | --- |
| Đường cơ sở | Biết hệ thống hiện tại xử lý thế nào | Kết quả cùng bộ nghiệp vụ và dữ liệu so sánh |
| Tải bình thường | Xác nhận mục tiêu thường ngày | Throughput, percentile, lỗi và tài nguyên |
| Tải đỉnh | Tìm giới hạn khi nhu cầu tăng | Điểm bắt đầu queue, lỗi hoặc vi phạm ngưỡng |
| Tải hỗn hợp | Kiểm tra tranh chấp | OLTP cùng batch/backup theo lịch dự kiến |
| Giảm tài nguyên | Kiểm tra khả năng phục vụ trong phạm vi sự cố đã chọn | Kết quả ứng dụng khi thiếu thành phần |
| Recovery | Xác nhận điểm dữ liệu và thời gian phục hồi | Restore/role transition và giao dịch sau phục hồi |
| Mở rộng | Kiểm tra thao tác và giới hạn scaling | Thời gian thực hiện, tác động và kết quả sau đổi |

Chỉ thực hiện thử lỗi trong phạm vi môi trường thử và kế hoạch đã được tổ chức chấp thuận. Không chạy thử phá hỏng thành phần trên production để bổ sung một bảng điểm.

### 11.4. Đọc kết quả theo điều kiện đạt

Ví dụ hai kết quả giả định cho giao dịch tạo đơn:

| Chỉ số | Mục tiêu | Ứng viên A | Ứng viên B |
| --- | --- | --- | --- |
| Throughput thành công | Ít nhất 1.200 giao dịch/giây | 1.250 | 1.800 |
| p95 | Không quá 150 ms | 130 ms | 190 ms |
| p99 | Không quá 400 ms | 320 ms | 470 ms |
| Tỷ lệ lỗi | Không quá 0,1% | 0,03% | 0,02% |

Nếu cả bốn dòng là điều kiện bắt buộc, B chưa đạt dù throughput cao hơn. Không chọn B chỉ vì “xử lý được nhiều giao dịch hơn”.

Nếu A chỉ đạt trong trạng thái bình thường nhưng không đạt tại tình huống giảm tài nguyên đã cam kết, A cũng chưa đủ bằng chứng. Cần thay cấu hình, giảm tải trong kịch bản đó theo thỏa thuận hoặc xem lại phương án.

### 11.5. Tránh kết luận vượt quá dữ liệu đo

Các sai lệch thường gặp:

- Chạy quá ngắn nên chưa thấy backlog hoặc cạn tài nguyên.
- Chỉ đo trung bình, bỏ qua p99 và lỗi.
- Chạy dữ liệu vừa toàn bộ cache rồi suy ra hiệu năng với dữ liệu lớn hơn nhiều.
- Giảm request khi hệ thống chậm mà không ghi nhận lượng công việc chưa phục vụ.
- Chọn một SQL thuận lợi thay cho transaction mix.
- Chưa kiểm tra ứng dụng ở vị trí thật.
- Không ghi điều kiện patch, plan hoặc resource management.

Kết luận đúng phải giới hạn theo phạm vi đã thử. Một PoC 2 TB không tự chứng minh kết quả cho 40 TB; cần giải thích yếu tố tăng trưởng và có kế hoạch xác nhận bổ sung.

## 12. Tính chi phí của toàn bộ phương án

### 12.1. So sánh cùng phạm vi

Không so tiền compute cloud với riêng giá mua phần cứng tại chỗ. Cần cùng thời hạn, cùng workload và cùng mức bảo vệ.

Một khung tính:

~~~text
Tổng chi phí phương án =
    hạ tầng và compute
  + license/subscription và hỗ trợ liên quan
  + storage cho primary, standby, backup và môi trường thử
  + kết nối và truyền dữ liệu
  + vận hành, giám sát, bảo mật và diễn tập
  + điều kiện site nếu có
  + migration, kiểm chứng và thời gian chạy song song
~~~

Ghi rõ phần nào đã bao gồm trong thuê bao để tránh tính trùng. Với BYOL, xác nhận entitlement có thể dùng cho đúng dịch vụ, số lượng, tính năng, production/standby và các môi trường liên quan theo điều kiện áp dụng.

Chi phí và điều kiện license cần lấy từ báo giá, tài liệu dịch vụ và hợp đồng đang dùng. Không suy ra quyền sử dụng chỉ từ việc tính năng chạy được trong PoC.

### 12.2. Phân biệt chi phí cố định với biến đổi

Trong một phương án dedicated hoặc tại chỗ, giảm compute đang sử dụng không nhất thiết làm giảm toàn bộ chi phí hạ tầng theo cùng tỷ lệ. Với mô hình cấp phát khác, các thành phần tính phí và mức tối thiểu có thể khác.

Hồ sơ nên tách:

- Khoản cam kết hoặc nền tảng cần duy trì.
- Khoản thay đổi theo compute/storage/traffic.
- Chi phí tăng bậc khi vượt năng lực hiện tại.
- Chi phí một lần và chi phí lặp lại.
- Chi phí cho primary và chi phí phục hồi toàn dịch vụ.

Chạy ba kịch bản nhu cầu: thấp, cơ sở và tăng nhanh. Với mỗi kịch bản, ghi thời điểm cần mở rộng và khả năng cung cấp thêm tài nguyên.

### 12.3. Dùng đơn vị chi phí có ý nghĩa

Có thể tính:

~~~text
Chi phí trên 1 triệu giao dịch đạt yêu cầu =
    chi phí trong kỳ
    / số giao dịch thành công đáp ứng mục tiêu trong kỳ
    × 1.000.000
~~~

Không dùng chỉ số này để che việc chưa đạt điều kiện bắt buộc. Một ứng viên rẻ nhưng vi phạm vị trí dữ liệu hoặc p99 vẫn chưa phải phương án khả thi.

Với workload báo cáo, đơn vị có thể là chi phí cho một kỳ batch hoàn tất trong cửa sổ. Chọn đơn vị phù hợp nghiệp vụ và giữ các giả định nhất quán.

## 13. Ma trận lựa chọn và hai ví dụ quyết định

### 13.1. Bước một: điều kiện loại trừ

| Điều kiện bắt buộc | Cách xác nhận | Nếu chưa xác nhận |
| --- | --- | --- |
| Primary và các bản sao ở phạm vi được phép | Bản đồ luồng dữ liệu, cấu hình đích và xác nhận chính sách | Chưa đủ điều kiện chọn |
| Phiên bản, tính năng và tích hợp được hỗ trợ | Tài liệu đúng dịch vụ, inventory và PoC | Phải xử lý khoảng thiếu |
| Độ trễ và công suất đạt mục tiêu | Kết quả PoC tại topology dự kiến | Điều chỉnh hoặc loại |
| Site và kết nối sẵn sàng | Khảo sát, kết quả kiểm tra mạng, kế hoạch triển khai | Chưa cam kết ngày chạy |
| RPO/RTO khả thi | Thiết kế và diễn tập theo phạm vi mục tiêu | Chưa đủ bằng chứng |
| License và khả năng cấp tài nguyên hợp lệ | Xác nhận hợp đồng, entitlement và dịch vụ | Chưa chốt cấu hình/chi phí |

Dùng các trạng thái **Đạt**, **Không đạt**, **Chưa xác nhận**. Không tự chuyển “Chưa xác nhận” thành “Đạt” vì đó là giả định thuận tiện cho tiến độ.

### 13.2. Bước hai: chấm điểm các ứng viên đã qua điều kiện bắt buộc

Ví dụ trọng số và điểm giả định, thang điểm 1–5:

| Tiêu chí ưu tiên | Trọng số | OCI dedicated, ứng dụng chuyển gần database | Cloud@Customer, ứng dụng tại chỗ |
| --- | --- | --- | --- |
| Dư địa hiệu năng và mở rộng | 35% | 4 | 5 |
| Phù hợp kết nối và phụ thuộc | 20% | 4 | 5 |
| Phù hợp năng lực vận hành | 20% | 4 | 3 |
| Chi phí theo kịch bản cơ sở | 15% | 4 | 2 |
| Thời gian triển khai | 10% | 5 | 2 |
| Tổng điểm quy đổi trên 100 | 100% | 82 | 77 |

Cách tính: tổng của `trọng số × điểm / 5`, với trọng số biểu diễn theo thang 100.

Các điểm là đánh giá giả định của một dự án, không phải xếp hạng sản phẩm chung. Với tổ chức đã có site và đội vận hành sẵn, điểm có thể khác hoàn toàn.

Cần thử độ nhạy: nếu trọng số thay đổi hợp lý mà lựa chọn đảo chiều, hãy nêu quyết định đang phụ thuộc mạnh vào ưu tiên nào.

### 13.3. Ví dụ A: dữ liệu phải ở hai trung tâm dữ liệu được duyệt

Giả định tổ chức xác nhận:

- Primary, standby, backup và bản phục hồi có dữ liệu thật chỉ được lưu tại site A hoặc B.
- Ứng dụng có nhiều phụ thuộc nội bộ chưa thể di chuyển.
- Lưu lượng quản trị và hỗ trợ phải được thẩm định riêng.
- Workload đã được chứng minh có nhu cầu đặc tính Exadata.

Hướng đánh giá:

1. Phương án OCI public region không nằm trong danh sách địa điểm được duyệt bị loại tại điều kiện vị trí, dù PoC hiệu năng tốt.
2. Cloud@Customer tại A là ứng viên cần đánh giá tiếp.
3. Thiết kế backup/DR phải nằm trong phạm vi A/B theo yêu cầu, bằng các lựa chọn được dịch vụ hỗ trợ.
4. Kiểm tra site B, đường kết nối, khóa và quy trình phục hồi.
5. Thẩm định các luồng control plane, telemetry, log và hỗ trợ trước khi kết luận toàn phương án phù hợp.

Kết luận hợp lý ở giai đoạn đầu là “Cloud@Customer có cơ sở để tiếp tục PoC và thẩm định”, chưa phải “Cloud@Customer tự động đáp ứng toàn bộ yêu cầu”.

Nếu site không đáp ứng hoặc các luồng bắt buộc chưa được chấp nhận, cần điều chỉnh phương án hoặc làm rõ yêu cầu. Không bỏ qua điều kiện bắt buộc để chốt sản phẩm.

### 13.4. Ví dụ B: dữ liệu được phép vào region phù hợp và ứng dụng có thể chuyển

Giả định:

- Phạm vi dữ liệu cho phép dùng region đã xác nhận.
- Ứng dụng Java có thể triển khai gần database.
- Tải lớn vào giờ cao điểm và có tăng trưởng.
- Tổ chức không muốn chuẩn bị hạ tầng vật lý mới.

Có thể đưa Exadata trên OCI vào PoC cùng thiết kế VCN, IAM, mạng và DR tương ứng. Nếu không có yêu cầu hạ tầng dành riêng, đánh giá cả lựa chọn Exascale được cung cấp; nếu có yêu cầu dành riêng, giữ đúng loại ứng viên đó.

Quyết định dựa trên ứng dụng sau khi chuyển gần database, không dùng RTT từ ứng dụng cũ tại trung tâm dữ liệu để đại diện cho topology mới.

Vẫn phải tính chi phí di chuyển ứng dụng, thay đổi tích hợp, kết nối với hệ thống còn tại chỗ và các bản sao dữ liệu. Việc database được phép lên cloud không bảo đảm toàn bộ kiến trúc hybrid đã tối ưu.

## 14. Kế hoạch migration là một phần của lựa chọn

### 14.1. Kiểm tra tính khả thi của đường chuyển dữ liệu

Cần xác định:

- Phương thức chuyển tương thích với nguồn, đích và yêu cầu downtime.
- Dung lượng thực phải truyền, mức nén có thể dùng và băng thông hữu dụng.
- Tốc độ phát sinh thay đổi trong thời gian chuyển.
- Cách xác nhận dữ liệu, chuyển kết nối và xử lý ứng dụng.
- Thời hạn lưu hệ thống cũ và điều kiện quay lại.

Ví dụ truyền ban đầu 20 TB qua đường có throughput hữu dụng 1 Gbit/s, dùng đơn vị thập phân và bỏ qua mọi overhead khác:

~~~text
Thời gian tối thiểu theo mô hình =
    20 × 10^12 byte × 8 / 10^9 bit/giây
    = 160.000 giây
    ≈ 44,4 giờ
~~~

Đây không phải downtime ước tính và không phải thời gian migration hoàn chỉnh. Còn có chuẩn bị, đọc/ghi, validation, đồng bộ thay đổi và cutover.

Nếu dữ liệu tiếp tục thay đổi, phương án đồng bộ phải đủ năng lực bắt kịp. Một lựa chọn hợp lý về steady-state có thể chưa triển khai kịp nếu đường migration không đáp ứng lịch dự án.

### 14.2. Quay lại sau khi đã ghi dữ liệu mới

Kế hoạch rollback không thể chỉ là đổi connection string về database cũ. Sau cutover, database mới có thể đã nhận giao dịch mà nguồn cũ không có.

Phải định nghĩa:

- Mốc nào còn có thể quay lại mà không đối soát dữ liệu.
- Sau mốc đó, dữ liệu mới được đưa trở lại bằng cách nào.
- Ai quyết định dừng, quay lại hoặc tiếp tục khắc phục.
- Cách xử lý tích hợp đã thực hiện giao dịch bên ngoài.

Tính khả thi của rollback và thời gian chạy song song cần được đưa vào chi phí, lịch và rủi ro lựa chọn.

## 15. Thực hành lập hồ sơ lựa chọn

Thực hành này tạo một quyết định kiến trúc tự chứa cho một workload Oracle Database. Các nội dung dưới đây là mẫu thông tin cần có; không cần tạo thêm file ngoài bài học để hiểu quy trình.

### 15.1. Bộ đầu vào tối thiểu

Thu thập hoặc giả lập có ghi rõ:

1. Ba luồng nghiệp vụ quan trọng và mục tiêu thời gian phản hồi.
2. Tải bình thường, tải đỉnh và lịch batch/backup.
3. Dung lượng, tăng trưởng, hot working set và redo.
4. Vị trí ứng dụng, phụ thuộc và chỉ số mạng.
5. Phạm vi lưu dữ liệu cho primary, standby, backup, thử nghiệm và log.
6. RPO/RTO theo kịch bản và năng lực vận hành.
7. Thời hạn triển khai, khả năng chuẩn bị site và ngân sách cùng phạm vi.

Nếu dùng dữ liệu giả định, phải tách nó khỏi kết quả đo. Không điền một thông số trong brochure vào cột kết quả PoC.

### 15.2. Trình tự thực hiện

- Lập các ứng viên phù hợp với yêu cầu vị trí và mô hình vận hành.
- Kiểm tra điều kiện bắt buộc, ghi rõ phần chưa xác nhận.
- Lập sizing ban đầu cùng giả định và kịch bản tăng trưởng.
- Thiết kế PoC, tiêu chí đạt và phạm vi giảm tài nguyên.
- Tính chi phí cùng thời hạn và mức bảo vệ.
- So sánh, nêu điều kiện lựa chọn và kế hoạch migration.
- Đặt mốc xem xét lại dựa trên dữ liệu quan sát được.

### 15.3. Mẫu quyết định kiến trúc

~~~text
Tên quyết định:
Lựa chọn nền tảng và địa điểm cho database <tên hệ thống>.

Bối cảnh:
Workload, topology ứng dụng và vấn đề cần giải quyết.

Điều kiện bắt buộc:
Vị trí dữ liệu, tương thích, mục tiêu dịch vụ, quyền kiểm soát.

Ứng viên:
Dịch vụ, địa điểm và cấu hình được xem xét.

Bằng chứng:
Kết quả PoC, đo mạng, khảo sát site, xác nhận cấp tài nguyên,
kiểm chứng recovery và báo giá cùng phạm vi.

Lựa chọn:
Phương án được chọn và lý do gắn với bằng chứng.

Đánh đổi:
Chi phí, phụ thuộc, giới hạn mở rộng và trách nhiệm vận hành.

Điều kiện trước triển khai:
Các mục chưa hoàn tất, người chịu trách nhiệm và mốc xử lý.

Migration:
Phương thức, cutover, xác nhận dữ liệu và cách xử lý quay lại.

Xem xét lại khi:
Tải, tăng trưởng, vị trí ứng dụng, chính sách hoặc khả năng
cấp tài nguyên vượt các giả định đã ghi.
~~~

Một hồ sơ tốt phải giúp người đọc phân biệt điều đã biết, điều đã đo và điều còn giả định. Nếu chưa có bằng chứng, giữ trạng thái cần xác nhận thay vì diễn đạt thành bảo đảm của sản phẩm.

## 16. Vận dụng sau khi đã chọn phương án

Lựa chọn không kết thúc ở lúc provision database. Thiết lập dashboard theo đúng các chỉ số dùng trong quyết định: throughput nghiệp vụ, p95/p99, lỗi, CPU, bộ nhớ, I/O, mạng, dung lượng, backup và độ sẵn sàng của nơi phục hồi.

Gắn quyền thay đổi tài nguyên với IAM và quyền database phù hợp; lưu dấu vết thay đổi. Khi dùng automation hoặc hạ tầng khai báo, phải xác định cấu hình nào được quản lý ở đâu để tránh các công cụ ghi đè lẫn nhau.

Đặt cảnh báo trước khi chạm giới hạn đã thử nghiệm. Khi thực tế khác giả định, dùng chính hồ sơ workload để quyết định tối ưu SQL, giảm lượt gọi mạng, bổ sung tài nguyên, tách workload hoặc thay đổi vị trí triển khai.

Lựa chọn Exadata phù hợp là phương án **đáp ứng mục tiêu ứng dụng tại các địa điểm được phép, có đủ năng lực phục hồi và có thể vận hành trong ngân sách đã xác nhận**. Kết luận đó cần đến đo đạc, bản đồ dữ liệu và trách nhiệm cụ thể, thay vì chỉ tên nền tảng hoặc thông số cực đại.
