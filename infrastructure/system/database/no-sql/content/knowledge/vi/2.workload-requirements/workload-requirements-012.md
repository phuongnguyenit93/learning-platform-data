# Lập giả định, rủi ro và câu hỏi cần kiểm chứng bằng thử nghiệm

Khi thiết kế một hệ thống dùng NoSQL, các phát biểu như “dữ liệu rất lớn”, “truy cập chủ yếu là đọc”, “cần độ trễ thấp” hay “cơ sở dữ liệu có thể mở rộng ngang” **chưa đủ để quyết định mô hình dữ liệu, khóa phân vùng, số node, chỉ mục và cách nhất quán**. Những phát biểu đó phải được chuyển thành các **giả định có thể kiểm chứng**, **rủi ro có thể xảy ra** và **câu hỏi thử nghiệm có tiêu chí đạt/trượt**.

Trong chủ đề **Yêu cầu và tải dữ liệu**, mục tiêu của bước này là biến hiểu biết còn thiếu về hệ thống thành một kế hoạch thu thập bằng chứng. Một thiết kế NoSQL chỉ có ý nghĩa khi phù hợp với **truy vấn thực tế, phân bố dữ liệu, lưu lượng, tốc độ tăng trưởng, yêu cầu đúng đắn và điều kiện vận hành**.

> Ví dụ xuyên suốt: một nền tảng bán hàng dự định lưu tài liệu sản phẩm trong cơ sở dữ liệu NoSQL. Ứng dụng đọc chi tiết sản phẩm theo ID, lọc theo danh mục, cập nhật giá và hiển thị dữ liệu cho người mua. Các con số trong bài là **giả định minh họa để thiết kế thử nghiệm**, không phải năng lực hoặc giới hạn mặc định của MongoDB, DynamoDB, Cassandra hay bất kỳ sản phẩm cụ thể nào.

## 1. Phân biệt yêu cầu, sự thật, giả định, giả thuyết và rủi ro

Các khái niệm này có liên hệ nhưng không thay thế được nhau.

| Loại thông tin | Ý nghĩa | Ví dụ trong hệ thống NoSQL |
| --- | --- | --- |
| **Yêu cầu (requirement)** | Điều hệ thống phải đáp ứng, do nghiệp vụ hoặc vận hành đặt ra | 99% yêu cầu xem chi tiết sản phẩm có thời gian phản hồi tối đa 400 ms trong tải đỉnh |
| **Sự thật có bằng chứng (observed fact)** | Dữ liệu đo được, kèm nguồn và khoảng thời gian | Log 14 ngày cho thấy khoảng 72% request là đọc theo ID |
| **Giả định (assumption)** | Điều đang tạm coi là đúng để có thể thiết kế tiếp | Trong 6 tháng tới, cơ cấu read/write không thay đổi đáng kể |
| **Giả thuyết kiểm chứng (testable hypothesis)** | Dự đoán cụ thể, có điều kiện và dấu hiệu bác bỏ | Với 8 triệu tài liệu và 9.000 request/s, cấu hình A giữ p99 dưới 400 ms |
| **Rủi ro (risk)** | Sự kiện/điều kiện có thể làm hỏng mục tiêu nếu xảy ra | Một nhóm khóa “nóng” gây quá tải một partition dù tổng CPU của cụm vẫn thấp |
| **Câu hỏi thử nghiệm** | Điều cần đo hoặc quan sát để ra quyết định | Khi 70% lượt đọc tập trung vào 1% product ID, p99 và tải từng partition thay đổi thế nào? |

Một rủi ro thường bắt nguồn từ **giả định chưa được xác nhận**, nhưng không phải giả định nào cũng nguy hiểm như nhau. Ví dụ, sai ước lượng kích thước tên sản phẩm 10% có thể ít ảnh hưởng; sai giả định về phân bố khóa có thể khiến partition bị nghẽn dù đã tăng gấp đôi số node.

### 1.1. Viết giả định sao cho có thể bác bỏ

Giả định mơ hồ:

> Người dùng hầu hết tìm sản phẩm theo ID; hệ thống chắc chạy nhanh.

Giả định tốt hơn:

> Trong giờ cao điểm, tối thiểu 70% request đọc dữ liệu sản phẩm là truy vấn theo ID; mức truy cập vào 1% khóa phổ biến nhất không vượt 30% tổng lượt đọc. Sẽ đối chiếu bằng log truy vấn của 14 ngày gần nhất và mẫu traffic đại diện cho đợt khuyến mãi.

Câu đầu không chỉ ra cách kiểm tra. Câu sau có **đơn vị, phạm vi, khoảng thời gian, nguồn dữ liệu và điều kiện làm giả định sai**.

Giả thuyết thử nghiệm nên có dạng:

**Trong điều kiện X, dùng phương án Y, hệ thống đạt chỉ số Z theo ngưỡng T; nếu không đạt thì xem lại quyết định D.**

Ví dụ:

> Với 8 triệu sản phẩm, phân bố khóa lệch giống đợt sale, 9.000 request/s trong 10 phút và 10% thao tác ghi, phương án shard theo productId giữ p99 API dưới 400 ms, tỷ lệ lỗi dưới 0,1% và không có partition nào đạt giới hạn tài nguyên kéo dài quá ngưỡng cho phép. Nếu không đạt, cần xem lại phân bố khóa, caching hoặc thiết kế phân vùng trước khi tăng số node.

Không nhất thiết phải định lượng mọi rủi ro bằng một xác suất chính xác. Nếu thiếu dữ liệu lịch sử, ghi rõ **chưa biết** và ưu tiên thử nghiệm theo mức độ hậu quả.

## 2. Thu thập các giả định nền từ yêu cầu và tải dữ liệu

Trước khi thử nghiệm, phải biết mình đang mô phỏng điều gì. Nên lập một **hồ sơ workload** gồm các nhóm sau.

### 2.1. Dung lượng và hình dạng dữ liệu

- **Số thực thể ban đầu:** bao nhiêu sản phẩm, người dùng, đơn hàng, sự kiện?
- **Kích thước bản ghi:** trung bình, p95/p99, kích thước lớn nhất; phân phối trường dài/ngắn, mảng lồng nhau và tệp đính kèm.
- **Độ phân biệt của khóa (cardinality):** bao nhiêu khóa khác nhau, có khóa nào nhận lượng truy cập vượt trội?
- **Quan hệ và truy vấn:** dữ liệu được đọc theo ID, lọc nhiều thuộc tính, duyệt quan hệ, tìm kiếm toàn văn hay tổng hợp?
- **Vòng đời:** bản ghi nào sửa thường xuyên, bản ghi nào bất biến, dữ liệu nào hết hạn và có thể lưu trữ lạnh?
- **Tăng trưởng:** số bản ghi mới/ngày, thay đổi kích thước theo thời gian, chính sách giữ dữ liệu và xóa dữ liệu.

Ví dụ: **8 triệu tài liệu × trung bình 2 KiB ≈ 15,3 GiB dữ liệu thô** (8.000.000 × 2.048 byte). Đây chỉ là phép tính sơ bộ trước khi cộng **index, metadata, replication, log, khoảng trống lưu trữ, compaction và tăng trưởng**. Không được dùng con số dữ liệu thô như dự báo dung lượng đĩa thực tế hay dung lượng RAM cần thiết.

Một tài liệu trung bình 2 KiB cũng không mô tả hết hệ thống nếu có một số tài liệu chứa mảng lịch sử dài hàng MB. Vì thế cần khảo sát cả đuôi phân bố kích thước.

### 2.2. Đường truy cập và phân bố yêu cầu

Đo tổng RPS (requests per second) mới chỉ là bước đầu. Cần biết **mỗi loại yêu cầu làm bao nhiêu thao tác cơ sở dữ liệu**:

| Thao tác tại API | Tỷ trọng giả định ở đỉnh | Với 9.000 request/s | Truy cập dữ liệu cần khảo sát |
| --- | ---: | ---: | --- |
| Xem chi tiết theo ID | 70% | 6.300 request/s | Point read; cache hit/miss; kích thước response |
| Lọc danh mục và thuộc tính | 15% | 1.350 request/s | Index, độ chọn lọc, sắp xếp, phân trang |
| Cập nhật sản phẩm/giá | 10% | 900 request/s | Ghi có điều kiện, tranh chấp cùng bản ghi, replica |
| Tìm kiếm văn bản | 5% | 450 request/s | Search index nếu tách riêng; độ mới sau cập nhật |

Tỷ trọng trên là **cơ cấu API mẫu**, không mặc định rằng mỗi request tương đương một query. Một API có thể gọi nhiều kho, quét nhiều partition, retry hoặc kích hoạt cập nhật dẫn xuất. Số truy vấn phát sinh phải được đo hoặc tính từ truy vết thực tế.

Một số câu hỏi quan trọng:

- **Tải trung bình, p95 và đỉnh tăng gấp mấy lần?** Đỉnh trong 1 phút và đỉnh kéo dài 1 giờ rất khác nhau.
- **Lưu lượng có thiên lệch không?** Có thể 1% sản phẩm nhận 70% lượt xem trong giờ livestream.
- **Độ đồng thời và tốc độ đến:** bao nhiêu request đang chờ, bao nhiêu request mới đến mỗi giây?
- **Tác vụ nền cùng chạy không?** Backfill, export, TTL deletion, CDC, reindex, backup có thể cạnh tranh CPU/I/O với traffic trực tuyến.
- **Retry có làm tăng tải không?** Request lỗi có thể sinh nhiều lượt gọi cơ sở dữ liệu hơn request thành công.
- **Tải đến từ nhiều vùng địa lý không?** Độ trễ mạng và yêu cầu đọc từ vùng nào có thể quyết định đường dữ liệu.

### 2.3. Yêu cầu đúng đắn, độ trễ và phục hồi

Ngoài tốc độ, phải ghi rõ điều gì được phép cũ và điều gì không:

- **Tính nhất quán:** người dùng vừa sửa giá có cần đọc lại thấy ngay không? Giá được chốt khi đặt hàng lấy từ nguồn nào?
- **Giao dịch và ghi đồng thời:** có cần bảo đảm không ghi đè cập nhật, không bán quá tồn kho, không tạo trùng đơn hàng?
- **Độ bền dữ liệu:** một ghi đã được API xác nhận có thể bị mất trong trường hợp lỗi nào theo cấu hình hiện tại?
- **Availability:** khi một node, một vùng hoặc kết nối mạng lỗi, hệ thống chấp nhận tạm dừng ghi, từ chối đọc hay đọc dữ liệu cũ?
- **SLO:** ngưỡng latency p95/p99, throughput duy trì, tỷ lệ lỗi, độ trễ replication/indexing.
- **Phục hồi:** RPO (mức mất dữ liệu cho phép) và RTO (thời gian phục hồi mục tiêu) cần có giá trị cụ thể.

**Không thể kiểm chứng một hệ thống “nhanh và ổn định” nếu chưa biết nhanh đến mức nào, tại tải nào, khi nào được xem là thất bại.**

## 3. Sổ ghi giả định: làm rõ điều đang biết và chưa biết

Nên tạo một **assumption register** gần tài liệu thiết kế. Mỗi dòng ít nhất có: mã, giả định, nguồn, độ tin cậy, hệ quả khi sai, phép thử cần làm, người chịu trách nhiệm và trạng thái.

| Mã | Giả định cần xác nhận | Bằng chứng hiện có | Hệ quả nếu sai | Cách kiểm chứng |
| --- | --- | --- | --- | --- |
| A01 | Ít nhất 70% request là point read | Log của tuần bình thường | Mô hình dữ liệu ưu tiên ID không đủ đáp ứng lọc/tìm kiếm | Phân tích request trace vào ngày thường và ngày sale |
| A02 | 1% khóa phổ biến nhận không quá 30% reads | Chưa có thống kê | Hot partition, p99 tăng đột biến | Đo phân bố ID và chạy workload lệch khóa |
| A03 | Tài liệu trung bình 2 KiB, p99 nhỏ hơn 32 KiB | Mẫu dữ liệu staging | Dự toán storage và network thấp hơn thực tế | Lấy histogram kích thước tài liệu thật |
| A04 | Cache đạt hit ratio ít nhất 85% sau warm-up | Ước lượng | Primary chịu nhiều read hơn dự kiến | Đo hit/miss và thử nghiệm cache lạnh |
| A05 | Trễ đồng bộ search nhỏ hơn 5 giây trong điều kiện bình thường | Chưa đo | Người dùng thấy kết quả tìm kiếm cũ | Đo thời gian từ commit đến khi search thấy tài liệu |
| A06 | Có thể phục hồi tập dữ liệu theo RPO/RTO đã cam kết | Có chính sách backup trên giấy | Mất dữ liệu hoặc downtime vượt mục tiêu | Khôi phục từ backup vào môi trường cô lập, đối chiếu dữ liệu |

**Nguồn** có thể là log thật, mô phỏng, tài liệu sản phẩm, kinh nghiệm vận hành hoặc ý kiến chuyên gia. Mỗi loại có độ tin cậy khác nhau. Kết quả thử trong môi trường nhỏ phải được ghi nhận đúng phạm vi; không suy rộng thành khả năng chịu tải production nếu dữ liệu, topology và mạng khác xa thực tế.

Cần ghi **ngày xác nhận hoặc ngày phải kiểm chứng lại**. Một giả định đúng ở 100.000 khách hàng có thể sai khi sản phẩm đạt 10 triệu khách hàng, thêm địa bàn mới hoặc triển khai chiến dịch flash sale.

## 4. Từ giả định sang bản đồ rủi ro

Rủi ro không chỉ là “NoSQL chậm”. Mỗi rủi ro nên mô tả **nguyên nhân → biểu hiện → tác động → cách phát hiện → cách giảm thiểu**.

| Nhóm rủi ro | Kịch bản cụ thể | Dấu hiệu quan sát | Thử nghiệm/biện pháp |
| --- | --- | --- | --- |
| **Khóa phân vùng nóng** | Nhiều request đến cùng partition hoặc một vài khóa | p99 tăng, throttling, một node/partition nghẽn trong khi các node khác rảnh | Replay skew, đo tải từng partition; xem lại khóa, phân phối hoặc cache |
| **Truy vấn thiếu index** | Query lọc/sắp xếp phải scan nhiều tài liệu | Read amplification, CPU/I/O tăng theo dữ liệu | Kiểm tra query plan, đo latency với dữ liệu đủ lớn; tạo index theo access pattern |
| **Index quá nhiều** | Mỗi lần ghi cập nhật nhiều index phụ | Write latency, storage và chi phí ghi tăng | So sánh write throughput và dung lượng giữa các cấu hình index |
| **Tài liệu phình to** | Mảng lồng nhau tăng không giới hạn | Update tốn I/O, thời gian serialize tăng, chạm giới hạn tài liệu | Sinh dữ liệu với phân phối kích thước thật; tách cấu trúc khi cần |
| **Cache giả định quá lạc quan** | Cache hit thấp hoặc cache mất kết nối | Primary bị read spike, timeout dây chuyền | Tắt cache có kiểm soát, kiểm tra fallback, rate limiting và warm-up |
| **Nhất quán không khớp nghiệp vụ** | Đọc stale khiến giá/đặt chỗ sai | Read-after-write thất bại, xung đột phiên bản | Test cập nhật đồng thời, failover, read consistency thực tế |
| **Replication/CDC chậm** | Consumer không theo kịp ghi hoặc xảy ra lỗi retry | Lag tăng, projection thiếu dữ liệu, queue backlog | Spike/soak test, consumer restart, replay, đối soát nguồn |
| **Bản ghi trùng/thứ tự đảo** | Event gửi lại hoặc đến sai thứ tự | Đếm trùng, projection bị ghi đè bởi phiên bản cũ | Gửi duplicate/out-of-order event; xác minh idempotency |
| **Thay đổi topology** | Rebalance, failover hoặc scale-out khi tải cao | Tail latency tăng, cluster mất headroom | Diễn tập thêm/bớt node và lỗi thành phần |
| **Dung lượng và chi phí tăng** | Replica, index, log, egress và backup vượt ngân sách | Storage/throughput/bill tăng nhanh hơn dữ liệu thô | Dự báo nhiều kịch bản, đo tài nguyên và đơn giá theo tải |
| **Backup không dùng được** | Backup hoàn thành nhưng restore lỗi hoặc mất quá lâu | Không đạt RPO/RTO dù hệ thống có backup | Diễn tập restore, đo thời gian và kiểm tra tính toàn vẹn |

### 4.1. Ưu tiên theo tác động, độ bất định và thời gian sửa

Trong giai đoạn đầu, không cần gán xác suất giả chính xác cho rủi ro. Có thể dùng một ma trận định tính:

- **Tác động cao:** mất dữ liệu đã xác nhận, sai tồn kho, lộ dữ liệu, không thể phục hồi, không đạt SLO của luồng thanh toán.
- **Bất định cao:** chưa có số đo đáng tin hoặc giả định phụ thuộc vào hành vi người dùng khó dự đoán.
- **Khó đảo ngược:** thay đổi khóa phân vùng, mô hình định danh, hợp đồng nhất quán hoặc migration dữ liệu lớn tốn nhiều thời gian.

Ưu tiên thử nghiệm các rủi ro **vừa tác động cao, vừa thiếu bằng chứng, vừa khó sửa sau khi đi vào production**. Một tối ưu cache có thể để sau nếu vẫn dễ thay đổi; chọn sai partition key có thể kéo theo di trú dữ liệu và downtime.

## 5. Đặt câu hỏi thử nghiệm có thể trả lời bằng số liệu

Câu hỏi tốt có đối tượng, điều kiện, thước đo và phương án hành động.

| Câu hỏi chưa đủ rõ | Câu hỏi có thể thử nghiệm |
| --- | --- |
| NoSQL có nhanh không? | Với 8 triệu bản ghi, 6.300 point reads/s và 900 writes/s, p95/p99 tại API và database là bao nhiêu? |
| Có scale ngang được không? | Khi tăng node từ N lên 2N với cùng phân phối khóa, throughput đạt được và p99 cải thiện bao nhiêu so với chi phí tăng? |
| Sharding có cân bằng không? | Với 70% traffic dồn vào 1% khóa, mức tải partition cao nhất so với trung vị là bao nhiêu? |
| Cache có hiệu quả không? | Với hit ratio lần lượt 0%, 50%, 85%, tải primary, p99 API và tỷ lệ lỗi biến đổi thế nào? |
| Cập nhật có nhất quán không? | Sau ghi thành công, đọc ngay qua replica/search trả dữ liệu mới trong bao lâu; thao tác nào bắt buộc đọc nguồn chính? |
| Có chịu được lỗi không? | Khi mất một node dưới tải đỉnh, hệ thống mất bao lâu để phục vụ lại và có ghi đã xác nhận nào bị mất không? |
| Dữ liệu tăng có ảnh hưởng không? | Khi dữ liệu tăng 10 lần nhưng request/s không đổi, những truy vấn lọc, index và tác vụ bảo trì nào suy giảm? |

Trước khi chạy, cần quyết định **ngưỡng đạt** và **hành động nếu trượt**. Nếu đặt ngưỡng sau khi nhìn kết quả, thử nghiệm dễ biến thành hoạt động xác nhận định kiến.

### 5.1. Mẫu mô tả một thử nghiệm

~~~yaml
experimentId: EXP-HOT-KEY-01
decision: "Khóa phân vùng theo productId có đủ an toàn cho tải sale không?"
assumption: "Một phần nhỏ productId có thể nhận phần lớn lượt đọc"
hypothesis: >
  Với traffic 9.000 API requests/s và 70% lượt đọc dồn vào 1% productId,
  cấu hình được chọn vẫn đạt p99 API <= 400 ms và lỗi < 0.1%.
environment:
  datasetRecords: 8000000
  datasetDistribution: "kích thước, danh mục và độ nóng gần dữ liệu thực"
  topology: "ghi rõ node, loại máy, replica, network và region"
  client: "ghi rõ load generator, pool connection và timeout"
workload:
  pointReadPercent: 70
  filteredReadPercent: 15
  updatePercent: 10
  fullTextSearchPercent: 5
  peakRequestsPerSecond: 9000
  peakDurationMinutes: 10
  keySkew: "70% point reads vào 1% khóa"
measure:
  - "offered RPS và achieved RPS"
  - "p50/p95/p99 end-to-end latency"
  - "error rate và timeout"
  - "throttling, saturation, tải từng node/partition"
  - "CPU, memory, I/O, network và queue depth"
passCriteria:
  p99ApiMillisecondsMax: 400
  errorRatePercentMaxExclusive: 0.1
nextIfFail: "Xem lại phân bố khóa, cache, access pattern và cách phân vùng"
~~~

Đây là **mẫu đặc tả thử nghiệm**, không phải cấu hình chạy trực tiếp cho một công cụ. Cần triển khai tải thực tế tương ứng và định nghĩa rõ phép đo được áp dụng cho **các endpoint nào**, bộ lọc lỗi nào, cách lấy percentile và cửa sổ thời gian. Ngưỡng 400 ms và 0,1% chỉ minh họa một quyết định đã được đặt trước; yêu cầu thực tế phải do hệ thống cụ thể xác định.

## 6. Thiết kế thử nghiệm có khả năng phân biệt nguyên nhân

### 6.1. Tạo dữ liệu giống thực tế, không chỉ đủ số lượng

Một bộ dữ liệu “8 triệu bản ghi giống hệt nhau, khóa ngẫu nhiên đều” rất dễ cho kết quả đẹp nhưng thiếu giá trị nếu production có:

- Danh mục có hàng triệu sản phẩm, danh mục khác chỉ vài chục.
- Giá trị trống, trường hiếm, danh sách thuộc tính dài và tài liệu rất lớn.
- Một số tài khoản/người bán có lưu lượng cao bất thường.
- Dữ liệu mới được đọc thường xuyên hơn dữ liệu cũ.
- Truy vấn nhiều tổ hợp điều kiện, mức chọn lọc và cách phân trang khác nhau.

Nên sinh hoặc ẩn danh mẫu dữ liệu với **histogram kích thước**, **cardinality**, **phân bố khóa**, **tỷ lệ giá trị thiếu**, **độ chọn lọc của filter**, **tương quan giữa các trường** và **tốc độ phát sinh dữ liệu** tương đối gần production. Nếu không có dữ liệu thực, chạy nhiều kịch bản biên và đánh dấu rõ tính giả định của chúng.

### 6.2. Mô hình tải đúng nhịp truy cập

Phân biệt:

- **Offered load:** số request/s mà bộ phát tải cố gửi.
- **Achieved throughput:** số request/s hệ thống thực sự xử lý.
- **Concurrency:** số request đồng thời đang được xử lý/chờ.
- **Latency:** thời gian mỗi yêu cầu phải chờ, gồm hoặc không gồm mạng tùy điểm đo.

Khi tải vượt năng lực, throughput có thể không tăng nữa, queue dài lên và latency tăng. Một bộ phát tải kiểu **closed-loop** chỉ gửi request mới sau khi request trước kết thúc có thể vô tình giảm tốc độ gửi lúc hệ thống chậm; kết quả nhìn “ít request, độ trễ chấp nhận được” không chứng minh hệ thống chịu được lượng yêu cầu bên ngoài. Với mục tiêu đo khả năng xử lý lưu lượng đến, cần cân nhắc mô hình **open-loop**, ghi nhận request bị từ chối hoặc trễ lịch, đồng thời tránh sai lệch đo lường kiểu *coordinated omission*.

Với mỗi request, nên ghi operation type, target key/partition, thời điểm dự kiến và thực tế gửi, kết quả thành công/thất bại, elapsed time và thông tin retry. Ghi cả **thời gian tại client** lẫn số đo phía database để phân biệt nghẽn network, pool kết nối, ứng dụng và kho dữ liệu.

### 6.3. Ma trận kịch bản thử nghiệm

| Kịch bản | Điều thay đổi | Mục tiêu |
| --- | --- | --- |
| **Baseline** | Dữ liệu, index và topology cố định; tải bình thường | Lấy đường cơ sở cho latency, throughput và tiêu thụ tài nguyên |
| **Ramp** | Tăng dần request/s tới khi vi phạm SLO | Tìm điểm bão hòa và mức tải an toàn, thay vì chỉ nhìn throughput cực đại |
| **Spike** | Đột ngột tăng tải theo mô hình flash sale | Kiểm tra queue, connection pool, throttling và phục hồi sau đỉnh |
| **Hot key/partition** | Giữ tổng request/s, tăng độ lệch phân bố khóa | Xem nghẽn cục bộ mà chỉ số trung bình cụm có thể che giấu |
| **Data growth** | Tăng 1×, 3×, 10× số tài liệu | Đo tác động lên index, truy vấn lọc, storage và bảo trì |
| **Index alternatives** | So sánh phương án index đã xác định | Đánh đổi latency đọc, throughput ghi và dung lượng |
| **Cache cold/failure** | Cache lạnh, hit ratio thấp hoặc cache lỗi | Đo sức chịu tải của primary và đường fallback |
| **Soak** | Duy trì tải đại diện trong nhiều giờ | Phát hiện memory leak, compaction, queue tồn đọng và tăng độ trễ theo thời gian |
| **Failure/failover** | Giả lập lỗi thành phần trong môi trường được phép | Kiểm tra error spike, nhất quán, phục hồi và khả năng đạt RTO |
| **Rebuild/restore** | Phục hồi từ backup hoặc dựng lại projection/index | Kiểm chứng quy trình, thời gian và tính toàn vẹn |

Không phải thử nghiệm nào cũng chạy cùng lúc. Để suy ra tác động của một quyết định, cần **giữ các biến khác càng ổn định càng tốt**. Khi có tương tác giữa index, cache và workload, dùng ma trận nhiều tổ hợp có kiểm soát thay vì kết luận từ một lần chạy đơn lẻ.

### 6.4. Chuẩn bị và ghi chép để kết quả tái lập được

Một lần chạy chỉ có giá trị khi người khác biết điều kiện đã dẫn đến kết quả:

1. Ghi phiên bản database, driver, hệ điều hành, loại máy/CPU/RAM/disk, network, cấu hình replica/shard và vị trí các thành phần.
2. Ghi dataset snapshot/seed, kích thước và index, trạng thái cache, thời điểm warm-up, môi trường có traffic khác hay không.
3. Ghi code hoặc commit của load generator, cơ cấu operation, key distribution, timeout, retry, connection pool và số client.
4. Thử vài lần đủ để phát hiện dao động ngẫu nhiên. Không lấy kết quả tốt nhất làm kết luận duy nhất.
5. Đo ở cùng các mốc thời gian và cùng phạm vi; tách thời gian warm-up khỏi cửa sổ được dùng đánh giá SLO.
6. Lưu kết quả raw/histogram, biểu đồ tài nguyên và nhật ký lỗi để phân tích sau này.

Cần kiểm tra **bộ phát tải không tự trở thành nút cổ chai**. Nếu client hết CPU, kết nối mạng bão hòa hoặc giới hạn socket thấp, số đo không phản ánh khả năng của cơ sở dữ liệu.

## 7. Đo đúng thứ quyết định thành công

### 7.1. Không dùng latency trung bình thay cho p99

Giả sử 99 request hoàn thành trong 20 ms và 1 request mất 2.000 ms. Trung bình chỉ khoảng 39,8 ms, nhưng một nhóm người dùng vẫn chịu chờ rất lâu. Vì vậy:

- **p50** cho biết trải nghiệm trung vị.
- **p95/p99** phản ánh phần đuôi chậm, quan trọng khi nhiều dịch vụ gọi liên tiếp.
- **Max** hữu ích để điều tra nhưng rất nhạy với số mẫu và yếu tố bất thường.
- **Error/timeout rate** phải được báo cùng latency; nếu loại bỏ mọi request timeout khỏi percentile, kết quả có thể trở nên lạc quan giả tạo.

Với hệ thống phân tán, p99 của toàn API không nhất thiết bằng p99 của một query. API còn có mạng, xử lý ứng dụng, cache, nhiều lần gọi dữ liệu và queue.

### 7.2. Bộ số đo tối thiểu

| Lớp | Nên quan sát | Dùng để trả lời |
| --- | --- | --- |
| Client/API | Offered/achieved RPS, concurrency, latency histogram, 4xx/5xx, timeout, retry | Người dùng có nhận được kết quả đúng hạn không? |
| Database | Read/write throughput, query latency, scanned/returned count, slow queries, index usage | Tải nào làm query hoặc ghi suy giảm? |
| Partition/node | CPU, RAM, disk IOPS/latency, network, queue, throttling, phân bố key | Có nghẽn cục bộ hoặc lệch tải không? |
| Replication/stream | Replication lag, CDC/consumer lag, backlog, replay failures | Bản sao và dữ liệu dẫn xuất có theo kịp không? |
| Cache | Hit/miss, evictions, memory, response latency, fallback rate | Cache có thực sự giảm tải primary không? |
| Dung lượng/chi phí | Data + index + replica + log, lượng ghi, request cost, backup/egress | Thiết kế có khả thi khi dữ liệu và traffic tăng? |
| Đúng đắn | Lost update, duplicate, stale read, invariant violations, đối soát bản ghi | Hệ thống nhanh nhưng có trả kết quả sai không? |

Thường cần vẽ số đo theo **cùng trục thời gian**: tại giây p99 tăng, partition nào đạt ngưỡng I/O, queue có dài lên và cache hit có giảm không? Tương quan thời gian giúp tìm nguyên nhân, nhưng vẫn phải có thử nghiệm cô lập để xác nhận quan hệ nhân quả.

### 7.3. Công suất an toàn khác công suất tối đa

Nếu hệ thống có thể đạt 12.000 request/s trong một phút trước khi lỗi tăng mạnh, điều đó **không có nghĩa** nên đặt tải production ở 12.000 request/s. Phải để dư địa cho:

- Đỉnh vượt dự báo, retry storm và rebalancing.
- Mất một node/replica, thay đổi leader hoặc tác vụ sửa chữa.
- Tăng trưởng dữ liệu, chiến dịch mới, backup và compaction.

**Headroom** là khoảng năng lực dự phòng giữa tải vận hành và điểm bắt đầu vi phạm SLO. Đặt headroom theo nhu cầu phục hồi và biến động thực tế; không có tỷ lệ cố định phù hợp cho mọi hệ thống NoSQL.

## 8. Kiểm chứng các giả định về tính đúng đắn và sự cố

Đánh giá NoSQL chỉ bằng throughput có thể bỏ qua lỗi nghiêm trọng nhất: **đã trả thành công nhưng trạng thái nghiệp vụ sai**.

### 8.1. Thử nghiệm ghi đồng thời

Tình huống: hai nhân viên cùng sửa giá của một sản phẩm từ phiên bản 7.

~~~text
T0: Giá = 1.490.000, version = 7
T1: Client A đọc version 7
T2: Client B đọc version 7
T3: Client A ghi giá 1.390.000 với điều kiện version = 7 → thành công
T4: Client B ghi giá 1.590.000 với điều kiện version = 7 → phải bị từ chối hoặc xử lý xung đột
~~~

Thử nghiệm phải chứng minh **hành vi thật của driver, câu lệnh ghi, cấu hình consistency/transaction và logic API**; không chỉ giả định rằng sản phẩm database hỗ trợ một tính năng nào đó nên ứng dụng tự động dùng đúng.

Các câu hỏi tương tự gồm:

- Hai request cùng giữ một đơn vị tồn kho có thể đều trả thành công không?
- Một thao tác retry có tạo hai đơn hàng không?
- Khi kết nối đứt sau khi database đã commit nhưng trước khi client nhận phản hồi, ứng dụng có thể gửi lại an toàn không?
- Đọc trên replica ngay sau ghi có đáp ứng yêu cầu read-your-writes không?
- Sau failover, có ghi đã được xác nhận nào không còn xuất hiện? Điều này có đúng với mức bền vững được cấu hình không?

### 8.2. Thử nghiệm bản sao và nguồn dữ liệu dẫn xuất

Nếu có cache, search index hoặc read model, cần phân biệt:

**Ghi tại nguồn chính thành công** ≠ **mọi bản sao đã cập nhật**.

Một phép thử độ mới có thể ghi bản ghi kèm phiên bản và timestamp, rồi đo thời điểm cùng phiên bản xuất hiện tại từng đường đọc. Ghi latency phân phối theo p50/p95/p99 và trường hợp mất sự kiện, thay vì chỉ ghi “eventual consistency hoạt động”.

Với consumer, cố tình gửi event trùng, sai thứ tự, ngắt kết nối và khởi động lại để kiểm tra **idempotency, checkpoint, replay và đối soát**. Những cơ chế này phải có hành vi phù hợp kiểu sự kiện: với event cộng/trừ dạng delta, không thể chỉ dùng “version lớn hơn thì nhận” nếu các phiên bản trung gian đã bị mất.

### 8.3. Thử nghiệm phục hồi

Giả định “backup mỗi đêm nên an toàn” không chứng minh RPO/RTO. Hãy thực hiện diễn tập có giới hạn:

1. Xác định thời điểm backup gần nhất và trạng thái ghi tiếp theo.
2. Khôi phục trong môi trường cô lập và đo từ lúc bắt đầu tới lúc có thể phục vụ kiểm tra dữ liệu.
3. Đối chiếu số lượng, checksum hoặc bất biến nghiệp vụ trên mẫu/toàn bộ dữ liệu phù hợp.
4. Ghi rõ phần dữ liệu có thể mất và thời gian thực tế để có hệ thống sử dụng được.
5. Thử quy trình khôi phục tiếp tục luồng ghi/sự kiện khi cần, không chỉ xác nhận file backup tồn tại.

Với hệ thống phân tán, fault injection nên được tiến hành trong môi trường thử nghiệm được phép, có phạm vi và khả năng dừng thử nghiệm rõ ràng. Không cần phá môi trường production chỉ để chứng minh một giả thuyết thiết kế.

## 9. Ví dụ hoàn chỉnh: chọn khóa truy cập cho kho sản phẩm

Nhóm phát triển cân nhắc lưu sản phẩm theo **productId** và dùng index cho **categoryId + trạng thái + giá**. Yêu cầu thử nghiệm được giả định:

- Dữ liệu: 8 triệu sản phẩm, kích thước trung bình 2 KiB, phân bố kích thước lệch.
- Tải đỉnh: 9.000 request/s trong 10 phút, cơ cấu như bảng ở mục 2.
- Trạng thái dữ liệu: nhiều sản phẩm vừa sửa giá trong đợt sale; 1% ID phổ biến nhất có thể nhận 70% point reads.
- SLO mẫu: p99 API dưới 400 ms, lỗi dưới 0,1% tại tải đỉnh; điều kiện ghi đồng thời phải đúng.

### 9.1. Các giả thuyết cần kiểm

| ID | Giả thuyết | Cách thử | Quyết định phụ thuộc |
| --- | --- | --- | --- |
| H01 | Point read theo ID đáp ứng SLO ở tải bình thường và tải sale | Ramp + hot-key workload trên dữ liệu 8 triệu bản ghi | Có cần cache/đổi cách phân vùng? |
| H02 | Index lọc danh mục phù hợp khi category lớn và truy vấn có sắp xếp | Query plan + dữ liệu có phân bố category lệch | Cấu trúc index và phân trang nào được chọn? |
| H03 | Cấu hình ghi có điều kiện tránh lost update dưới cạnh tranh cao | Nhiều writer cùng version, kiểm tra kết quả cuối | Logic cập nhật có đạt bất biến nghiệp vụ? |
| H04 | Khi cache mất, fallback không làm sập primary | Chạy cache-cold/circuit-breaker ở tải có kiểm soát | Mức rate limit và chiến lược giảm tải là gì? |
| H05 | Khi mất một node, hệ thống vẫn giữ mục tiêu hồi phục và không vi phạm hợp đồng ghi | Fault injection và đối soát ghi/đọc | Topology, replica, timeout và retry có đủ không? |
| H06 | Khi dữ liệu tăng 3 lần, chi phí và index vẫn trong phạm vi chấp nhận | Sinh dữ liệu tăng trưởng và chạy workload đồng nhất | Cần thay đổi index, tier storage hay dự toán? |

### 9.2. Cách đọc một kết quả giả định

Giả sử nhóm chạy thử và thu được kết quả **minh họa**:

| Kịch bản | Achieved throughput | p99 API | Tỷ lệ lỗi | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| Bình thường, phân bố ID gần đều | 9.000 request/s | 190 ms | 0,02% | Đạt các ngưỡng mẫu |
| Tải như trên, khóa nóng | 8.400 request/s | 870 ms | 1,8% | Trượt SLO; điểm nghẽn có thể cục bộ |
| Khóa nóng, cache được làm ấm | 9.000 request/s | 300 ms | 0,04% | Cải thiện luồng đọc; vẫn cần kiểm tra cache miss và ghi |
| Khóa nóng, cache không sẵn sàng | 7.600 request/s | 1.200 ms | 3,1% | Cần cơ chế giảm tải/fallback và capacity headroom |

Không thể kết luận “chỉ cần bật cache là xong”. Kết quả gợi ý **phân bố khóa** là rủi ro đáng tập trung. Nhóm cần đối chiếu metric từng partition, xem cách truy vấn được route, kiểm tra retry, đo cache miss và chạy lại trên các điều kiện tương đương trước khi chốt thiết kế. Nếu thao tác ghi cũng bị nghẽn cùng một khóa, cache đọc không giải quyết ràng buộc ghi đó.

Một quyết định có thể là: giữ point read theo ID, thêm cache cho sản phẩm “nóng”, quy định fallback/rate limit, kiểm tra lại partition strategy đối với pattern ghi và đặt ngưỡng cảnh báo cho hot partition. Quyết định phải được gắn với **bằng chứng và phạm vi đo**, tránh biến một thử nghiệm thành lời bảo đảm chung cho mọi tải trong tương lai.

## 10. Ghi nhận kết luận và rủi ro còn lại

Kết thúc một đợt kiểm chứng, tạo một **decision record** ngắn gọn nhưng đủ truy vết:

~~~text
Quyết định: Dùng productId làm khóa truy cập chính cho Product Store
Ngày kiểm chứng: YYYY-MM-DD
Phiên bản hệ thống: <database/driver/topology/config/commit>
Giả định đã xác nhận: A01, A03
Giả định bị bác bỏ: A02 (độ lệch khóa cao hơn dự kiến)
Kết quả: EXP-BASE-01, EXP-HOT-KEY-01, EXP-FAILOVER-01
Phạm vi đạt: <dataset, workload, SLO và giới hạn được đo>
Rủi ro còn lại: Tải sale vượt 9.000 request/s, cache đồng loạt mất hiệu lực
Biện pháp: Cảnh báo hot partition, rate limit, fallback, tiếp tục thử nghiệm
Chủ sở hữu: <nhóm/người chịu trách nhiệm>
Thời điểm kiểm chứng lại: <khi traffic tăng X% hoặc sau thay đổi dữ liệu lớn>
~~~

Nếu chưa có bằng chứng, viết rõ **UNKNOWN**. Nếu một giả định bị bác bỏ, cập nhật thiết kế, mô hình dữ liệu hoặc yêu cầu; đừng âm thầm sửa ngưỡng để bài test trông thành công. Nếu có quyết định tạm thời do hạn chế thời gian, ghi rõ **điều kiện chấp nhận rủi ro và dấu hiệu phải xem xét lại**.

### Những lỗi tư duy thường gặp

1. **Chọn công nghệ rồi mới tìm workload để chứng minh công nghệ đó phù hợp.** Hãy bắt đầu từ đường đọc/ghi và bất biến, sau đó mới chọn mô hình dữ liệu.
2. **Chỉ thử dữ liệu ít, phân bố đều và tải ổn định.** Kết quả không đại diện cho hot key, tăng trưởng, burst và truy vấn đuôi dài.
3. **Báo một con số throughput cực đại.** Cần kèm latency phân vị, lỗi, offered load và điều kiện thử.
4. **Đo trung bình toàn cluster.** Một partition nóng vẫn có thể timeout dù CPU trung bình thấp.
5. **Tin vào cam kết nhất quán chung chung.** Phải kiểm tra đúng thao tác, consistency level, driver, replica và luồng cập nhật ứng dụng.
6. **Xem failover là thành công khi dịch vụ lại trả HTTP 200.** Còn phải kiểm chứng dữ liệu đã commit, thời gian gián đoạn, lỗi và việc xử lý request trùng.
7. **Không ghi giả định và bằng chứng.** Khi sản phẩm thay đổi, nhóm không biết quyết định kiến trúc nào cần thử lại.

## 11. Bài tập thực hành

Giả sử một ứng dụng đặt chỗ có 2 triệu phòng, mỗi ngày phát sinh 100.000 giao dịch đặt phòng. Các yêu cầu mới:

- Người dùng tìm phòng theo thành phố, ngày, giá và tiện nghi.
- Một số thành phố có nhu cầu cao gấp hàng chục lần phần còn lại.
- Hai người không được cùng giữ thành công một phòng cho một khoảng thời gian trùng nhau.
- Danh sách tìm kiếm có thể trễ cập nhật vài giây, nhưng quyết định giữ phòng phải đúng ngay lúc xác nhận.
- Hệ thống dự kiến chạy chiến dịch giảm giá tạo lưu lượng gấp 5 lần ngày thường.

Hãy tự lập **ba giả định**, **ba rủi ro có tác động lớn** và **ba câu hỏi thử nghiệm**. Với mỗi câu hỏi, chỉ rõ dữ liệu cần sinh, mẫu traffic, phép đo, ngưỡng đạt và hành động nếu trượt. Một hướng trả lời:

| Giả định | Rủi ro | Thử nghiệm cần đặt ra |
| --- | --- | --- |
| Phân bố nhu cầu giữa các thành phố tương đối ổn định | Một số partition địa lý bị nóng khi sale | Ở tải đỉnh ×5 và traffic dồn vào top thành phố, p99 và tải từng partition có đáp ứng SLO không? |
| Phép giữ phòng có bảo vệ tranh chấp cùng khoảng thời gian | Double booking khi có request đồng thời | Với N request cùng tranh một phòng/khung giờ, có nhiều hơn một lệnh giữ phòng thành công không? |
| Search index cập nhật đủ nhanh cho trải nghiệm tìm kiếm | Người dùng thấy phòng đã hết hoặc giá cũ | Thời gian từ commit đến khi search phản ánh phiên bản mới là bao nhiêu; có recheck availability khi xác nhận không? |

Điểm mấu chốt của tư duy yêu cầu và tải dữ liệu trong NoSQL là **mỗi quyết định quan trọng đều có một giả định đằng sau**. Hãy viết giả định ấy ra, nêu rõ hậu quả nếu nó sai, và thiết kế phép thử đủ thực tế để **bác bỏ hoặc củng cố quyết định bằng bằng chứng**. Kết quả mong đợi không phải “hệ thống chạy được”, mà là biết **hệ thống đáp ứng yêu cầu nào, trong giới hạn nào, còn rủi ro nào và khi nào phải kiểm chứng lại**.
