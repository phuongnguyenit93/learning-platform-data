# Độ trễ, thông lượng, số kết nối và mục tiêu chất lượng dịch vụ

## 1. Vì sao phải đo tải trước khi chọn hoặc thiết kế cơ sở dữ liệu NoSQL?

Một ứng dụng có thể lưu dữ liệu đúng nhưng vẫn không đáp ứng được người dùng. Ví dụ, một dịch vụ thương mại điện tử sử dụng cơ sở dữ liệu document để đọc thông tin sản phẩm. Trong giờ bình thường, trang sản phẩm hiển thị trong 100 ms; đến đợt khuyến mãi, hàng nghìn yêu cầu đến mỗi giây, một số lần tải trang mất 3–5 giây, còn dịch vụ bắt đầu báo lỗi hết kết nối.

Để hiểu và giải quyết tình huống này, cần mô tả **tải dữ liệu** và **chất lượng dịch vụ** bằng những đại lượng đo được:

- **Độ trễ (latency):** mất bao lâu để một thao tác hoàn thành?
- **Thông lượng (throughput):** hệ thống hoàn thành được bao nhiêu thao tác trong một đơn vị thời gian?
- **Số kết nối (connections):** có bao nhiêu kết nối giữa ứng dụng và cơ sở dữ liệu, và chúng được sử dụng ra sao?
- **Mục tiêu chất lượng dịch vụ (SLO):** ở mức tải dự kiến, hệ thống phải đáp ứng nhanh, đúng và sẵn sàng đến mức nào?

Bốn đại lượng liên quan nhưng không thay thế cho nhau. Thêm kết nối không tự động tăng thông lượng; thông lượng cao không bảo đảm độ trễ thấp; độ trễ trung bình thấp không bảo đảm mọi khách hàng có trải nghiệm tốt.

Trong hệ NoSQL phân tán như MongoDB, Cassandra hoặc những hệ key–value phân tán, các yếu tố này còn chịu tác động của **khóa phân vùng, phân phối dữ liệu giữa các nút, cơ chế sao chép, mức nhất quán, kích thước tài liệu và mẫu truy vấn**. Vì vậy, thiết kế dữ liệu và thiết kế hiệu năng phải được xem xét cùng nhau.

## 2. Độ trễ: thời gian hoàn thành một yêu cầu

### 2.1. Xác định rõ đang đo từ đâu đến đâu

Độ trễ của một yêu cầu đọc là thời gian từ điểm bắt đầu được xác định đến khi nhận được kết quả theo tiêu chí hoàn thành đã chọn.

Ví dụ:

```text
Client            API Server               NoSQL Cluster
  | -- HTTP GET --> |                           |
  |                 | -- Query product -------> |
  |                 | <-------- Result -------- |
  | <--- JSON ----- |                           |
  |_________________ thời gian API _____________|
                    |____ thời gian DB ________|
```

Có thể đo ở ít nhất ba phạm vi:

| Phạm vi | Thời điểm bắt đầu và kết thúc | Trả lời câu hỏi |
|---|---|---|
| Độ trễ phía người dùng | Từ khi client gửi yêu cầu đến lúc nhận đủ phản hồi | Người dùng chờ bao lâu? |
| Độ trễ API | Từ khi ứng dụng nhận yêu cầu đến khi hoàn tất phản hồi | Dịch vụ mất bao lâu để xử lý? |
| Độ trễ thao tác NoSQL | Từ khi driver bắt đầu gọi DB đến khi nhận kết quả hoặc xác nhận ghi | Database góp bao nhiêu thời gian? |

Các phép đo trên có thể khác nhau vì thời gian mạng, xác thực, tuần tự hóa JSON, xử lý nghiệp vụ, hàng đợi, retry hoặc nhiều lời gọi DB nối tiếp nhau.

Khi đặt mục tiêu, luôn ghi rõ **đối tượng đo**, **loại thao tác**, **điểm bắt đầu/kết thúc** và **cách xử lý timeout, lỗi, retry**.

### 2.2. Đọc, ghi và truy vấn phức tạp có độ trễ khác nhau

Một thao tác tìm giá trị theo khóa có thể chỉ cần truy cập một phân vùng và trả về một bản ghi nhỏ. Một truy vấn lọc qua nhiều phân vùng, sắp xếp lượng dữ liệu lớn hoặc tổng hợp hàng triệu sự kiện có thể mất lâu hơn nhiều.

Tương tự, hai lời gọi “ghi thành công” có thể mang ý nghĩa khác nhau:

- Hệ thống đã nhận và đưa thao tác vào bộ nhớ.
- Hệ thống đã ghi vào nhật ký bền vững.
- Một số hoặc đa số replica đã xác nhận ghi.
- Một giao dịch gồm nhiều thay đổi đã được xác nhận thành công.

Vì thế, không nên so sánh độ trễ ghi giữa hai database nếu chưa biết **mức xác nhận ghi (write acknowledgment/durability)**. Độ trễ rất thấp đạt được bằng cách bỏ bớt bảo đảm dữ liệu có thể không phù hợp với đơn hàng hoặc giao dịch tài chính.

### 2.3. Trung bình, trung vị và phần trăm vị

Giả sử 100 lần đọc sản phẩm: phần lớn hoàn tất trong vài chục mili giây, nhưng vài lần phải chờ lâu vì mạng, cache miss hoặc máy đang thực hiện compaction.

Các đại lượng thường dùng:

- **Mean (trung bình):** tổng thời gian chia số lần thực hiện; nhạy với giá trị cực lớn.
- **p50 (median):** khoảng 50% các phép đo không vượt quá giá trị này.
- **p95:** khoảng 95% các phép đo không vượt quá giá trị này; nhóm chậm nhất chiếm khoảng 5%.
- **p99:** khoảng 99% các phép đo không vượt quá giá trị này; giúp quan sát “đuôi dài” của phân phối.
- **Max:** phép đo chậm nhất được ghi nhận trong cửa sổ; rất nhạy với số mẫu và lỗi đo.

Ví dụ một báo cáo:

| Chỉ số độ trễ API đọc sản phẩm | Giá trị minh họa |
|---|---:|
| p50 | 24 ms |
| p95 | 95 ms |
| p99 | 280 ms |
| Trung bình | 42 ms |
| Timeout do ứng dụng đặt | 1.000 ms |

Một con số “trung bình 42 ms” không phản ánh đầy đủ trải nghiệm của nhóm yêu cầu chậm. Nếu API gọi nhiều dịch vụ hoặc nhiều phân vùng cùng lúc, chỉ cần một nhánh chậm cũng có thể kéo dài thời gian phản hồi cuối cùng. Vì vậy, trong hệ phân tán, p95 và p99 thường quan trọng.

**Lưu ý:** p99 = 280 ms không có nghĩa mọi yêu cầu đều dưới 280 ms; khoảng 1% có thể chậm hơn. Việc tính percentile cần đủ số lượng mẫu và phương pháp tổng hợp nhất quán. Không được lấy trung bình các p99 từ nhiều nút để suy ra p99 của toàn hệ thống.

### 2.4. Độ trễ được tạo thành từ nhiều khoản thời gian

Một cách phân rã hữu ích:

```text
Tổng thời gian
  = thời gian xếp hàng
  + thời gian chờ lấy kết nối
  + thời gian mạng
  + thời gian thực thi tại DB
  + thời gian mạng trả về
  + thời gian chuyển đổi dữ liệu/xử lý tại ứng dụng
  + thời gian retry (nếu có)
```

Đây là mô hình khái quát; một số giai đoạn có thể chồng lấp khi thực thi bất đồng bộ. Hãy dùng tracing hoặc các bộ đo tại driver, API và server để biết thời gian thực sự nằm ở đâu.

Ví dụ: độ trễ truy vấn trên database chỉ 8 ms nhưng API có p99 900 ms. Khi đó có thể vấn đề nằm ở hàng đợi kết nối, mạng, thread pool hoặc các bước ngoài database; tăng số shard chưa chắc giúp ích.

## 3. Thông lượng: khối lượng công việc hoàn thành theo thời gian

**Throughput** là số đơn vị công việc được **hoàn thành** mỗi giây hoặc mỗi phút, với đơn vị được định nghĩa rõ.

Các cách đo phổ biến:

| Đơn vị | Ý nghĩa | Thường áp dụng |
|---|---|---|
| Requests per second (RPS) | Yêu cầu API mỗi giây | Cổng API, dịch vụ web |
| Queries/Operations per second (QPS/ops/s) | Truy vấn hoặc thao tác DB mỗi giây | Driver hoặc cụm NoSQL |
| Transactions per second (TPS) | Giao dịch hoàn tất mỗi giây | Nghiệp vụ, giao dịch nhiều bước |
| MB/s hoặc MiB/s | Lưu lượng byte đọc/ghi mỗi giây | Sao chép, nhập dữ liệu, scan |
| Events/s hoặc records/s | Số bản ghi/sự kiện xử lý mỗi giây | Telemetry, stream, ingestion |

**Một RPS không nhất thiết bằng một QPS**. Một yêu cầu API có thể thực hiện 0 truy vấn (cache hit), 1 truy vấn hoặc 5 truy vấn; mỗi truy vấn lại có thể đọc nhiều bản ghi. Không được so sánh hai chỉ số chỉ vì cùng có hậu tố “mỗi giây”.

### 3.1. Thông lượng yêu cầu và thông lượng thành công

Ví dụ trong 10 giây, hệ thống nhận 25.000 yêu cầu nhưng chỉ xử lý thành công 23.000, còn 2.000 bị timeout:

```text
Tốc độ yêu cầu đến      = 25.000 / 10 = 2.500 req/s
Throughput thành công  = 23.000 / 10 = 2.300 req/s
Tỷ lệ thất bại          =  2.000 / 25.000 = 8%
```

Nếu chỉ thông báo “2.500 RPS” sẽ dễ gây hiểu lầm rằng hệ thống đáp ứng được hoàn toàn mức tải đó. Báo cáo hiệu năng cần ghi đồng thời **offered load**, **completed throughput**, **error rate** và **latency**.

### 3.2. Thông lượng tăng không mãi

Khi tăng số client gửi yêu cầu, throughput ban đầu có thể tăng gần tỷ lệ thuận. Đến khi một tài nguyên bị giới hạn, chẳng hạn CPU, I/O, băng thông, một phân vùng nóng hoặc pool kết nối, các thao tác bắt đầu xếp hàng.

```text
Throughput hoàn thành
 ^
 |                      ____________
 |                  ___/
 |              ___/
 |          ___/
 |      ___/
 |  ___/
 +----------------------------------> Tải được gửi vào
                     ^
               gần vùng bão hòa

Độ trễ thường tăng mạnh khi tải tiến gần vùng bão hòa.
```

Đường cong thực tế có thể phức tạp hơn: khi quá tải, throughput đôi khi còn giảm vì retry, timeout, tranh chấp tài nguyên hoặc garbage collection. Năng lực xử lý cần được công bố cùng với độ trễ và tỷ lệ lỗi tại mức tải đó. “DB đạt 20.000 ops/s” không đủ nếu p99 ở mức đó là 10 giây.

### 3.3. Phân biệt đọc và ghi

Cùng 5.000 ops/s nhưng thành phần tải rất khác:

- Hệ A: 95% đọc theo khóa, 5% ghi tài liệu nhỏ.
- Hệ B: 20% đọc, 80% ghi có nhiều chỉ mục.
- Hệ C: 80% đọc nhưng mỗi truy vấn scan nhiều phân vùng.

Kết quả vận hành sẽ khác nhau do chi phí đọc/ghi, cập nhật chỉ mục, compaction, nhân bản và kích thước kết quả. Khi mô tả throughput, hãy ghi **tỷ lệ đọc/ghi, loại truy vấn, kích thước dữ liệu và mức nhất quán**.

## 4. Số kết nối: tài nguyên giao tiếp giữa ứng dụng và database

### 4.1. Kết nối khác với yêu cầu đang chạy

**Connection** thường là một kết nối mạng/phiên giao tiếp do driver duy trì với một nút database hoặc thành phần trung gian. **In-flight operation** là thao tác đã gửi nhưng chưa hoàn thành. **Concurrency** là số thao tác đồng thời đang được xử lý hoặc chờ xử lý theo phạm vi đo.

Ba đại lượng này không giống nhau:

- Một kết nối có thể lần lượt phục vụ nhiều thao tác.
- Tùy giao thức và driver, một kết nối có thể phục vụ một hoặc nhiều thao tác đồng thời (multiplexing).
- Một thao tác đang chờ đến lượt lấy kết nối vẫn góp phần vào thời gian phản hồi, dù chưa được gửi đến database.
- Một ứng dụng có thể mở hàng trăm kết nối nhưng chỉ đang xử lý vài truy vấn.

Không thể suy ra “500 kết nối = 500 truy vấn/s” hoặc “500 kết nối = 500 truy vấn đồng thời” nếu chưa biết cách driver và giao thức sử dụng kết nối.

### 4.2. Connection pool

Phần lớn ứng dụng dùng **connection pool**: nhóm kết nối được mở sẵn hoặc mở dần, tái sử dụng cho nhiều yêu cầu để tránh chi phí thiết lập kết nối mới liên tục.

```text
                  API instance A
         +----------------------------+
Request ->|    Connection pool       |
Request ->|   [C1] [C2] [C3] ...      |----> NoSQL nodes
Request ->|  wait queue (nếu bận)    |
         +----------------------------+
```

Các tham số thường cần biết, tên thực tế thay đổi theo driver:

| Tham số | Tác động |
|---|---|
| Minimum pool size | Có thể duy trì sẵn một số kết nối |
| Maximum pool size | Giới hạn số kết nối cho mỗi pool |
| Connection acquisition timeout | Yêu cầu được chờ lấy kết nối trong bao lâu |
| Connection idle timeout/lifetime | Khi nào kết nối rảnh hoặc quá cũ được đóng |
| Server selection/discovery timeout | Chờ driver tìm nút phù hợp để thao tác |
| Max in-flight requests | Giới hạn yêu cầu đang chạy, có thể tách biệt giới hạn connection |

Khi một instance có pool tối đa 20 kết nối, nhưng hệ thống tự động tăng từ 5 lên 30 instance, tổng mức tối đa về mặt cấu hình có thể từ 100 lên **600 kết nối**. Con số thực tế còn tùy số nút, số pool riêng biệt, topology, việc driver mở kết nối theo nút và lưu lượng sử dụng.

Do đó, cần quy hoạch kết nối ở **quy mô toàn bộ ứng dụng và toàn cụm**, không chỉ mỗi tiến trình.

### 4.3. Quá ít hoặc quá nhiều kết nối đều có vấn đề

**Quá ít kết nối:** yêu cầu chờ trong hàng đợi của driver; DB có thể chưa bận nhưng API vẫn chậm. Đây là lúc cần xem thời gian chờ lấy kết nối, active/idle connections, pending requests và độ dài hàng đợi.

**Quá nhiều kết nối:** tốn bộ nhớ, file descriptor, chi phí TLS, theo dõi trạng thái, CPU do tranh chấp; dễ làm database hoặc proxy quá tải. Tăng pool khi nút DB đã bão hòa có thể làm thời gian chờ và số lỗi tăng thêm.

**Kết nối mới mở liên tục:** tạo/đóng kết nối cho mỗi yêu cầu gây tốn handshake và tăng độ trễ; thường nên tái sử dụng client/driver theo vòng đời ứng dụng.

**Bão hòa một nút cụ thể:** tổng số connection toàn cụm có thể bình thường nhưng một nút giữ nhiều request vì phân vùng nóng hoặc cơ chế định tuyến.

### 4.4. Đặc điểm kết nối của hệ NoSQL phân tán

Không nên dùng một công thức pool size cho mọi sản phẩm:

- Driver MongoDB có thể quản lý pool theo server đã biết trong topology; số socket thực tế chịu ảnh hưởng của pool, monitoring và số server.
- Driver Cassandra thường là hệ thống nhận biết topology và gửi yêu cầu đến các nút phù hợp với khóa phân vùng và mức nhất quán; mô hình đồng thời của driver có thể khác driver database quan hệ.
- Các dịch vụ key–value như Redis thường sử dụng ít kết nối được tái sử dụng và có thể pipeline hoặc multiplex theo thư viện client.

Điểm chung là phải quan sát **kết nối thực tế, số thao tác đồng thời, hàng đợi và giới hạn từng nút**, rồi đọc tài liệu cấu hình của sản phẩm/driver đang sử dụng.

## 5. Mối liên hệ giữa độ trễ, thông lượng và số thao tác đồng thời

Một mối quan hệ hữu ích trong hệ thống ổn định là **định luật Little (Little's Law)**:

```text
L = λ × W

L : số công việc trung bình đang ở trong hệ thống
λ : tốc độ hoàn thành trung bình (đơn vị công việc/giây)
W : thời gian trung bình một công việc ở trong hệ thống (giây)
```

Ví dụ, dịch vụ hoàn thành đều đặn 2.000 thao tác DB/giây, mỗi thao tác mất trung bình 40 ms tính từ lúc vào phạm vi đo đến lúc ra:

```text
λ = 2.000 thao tác/giây
W = 40 ms = 0,04 giây
L = 2.000 × 0,04 = 80 thao tác đồng thời trung bình
```

Điều đó cho thấy trong phạm vi đo tương ứng, trung bình có khoảng 80 thao tác đang được xử lý hoặc chờ. **80 không phải số kết nối cần cấu hình** vì một connection có thể xử lý nhiều thao tác, một yêu cầu có thể giữ kết nối khác nhau theo từng giai đoạn, và driver có thể có hàng đợi riêng.

Định luật Little dùng **giá trị trung bình trong trạng thái ổn định**, không dùng p95 hay p99 thay cho `W`. Khi backlog tăng không ngừng, số thao tác đang chờ không còn ổn định; không nên dùng công thức để khẳng định hệ thống có đủ công suất.

### 5.1. Ví dụ khi tăng tải

Giả sử cùng một API đọc theo khóa:

| Tải gửi vào | Thông lượng thành công | Độ trễ trung bình | p99 | Ý nghĩa |
|---|---:|---:|---:|---|
| 500 req/s | 500 req/s | 15 ms | 45 ms | Còn dư năng lực |
| 1.500 req/s | 1.500 req/s | 25 ms | 100 ms | Tải tăng nhưng vẫn đáp ứng |
| 2.200 req/s | 2.180 req/s | 90 ms | 800 ms | Bắt đầu bão hòa |
| 3.000 req/s | 2.100 req/s | 450 ms | 2.500 ms | Quá tải, timeout/retry có thể xuất hiện |

Các số liệu chỉ minh họa một kịch bản. Điểm đáng chú ý là mức 3.000 req/s **không** có nghĩa hệ xử lý được 3.000 req/s. Thông lượng hoàn thành giảm và p99 tăng cho thấy cần giới hạn tải, tối ưu truy vấn hoặc bổ sung tài nguyên ở nút thắt thực tế.

### 5.2. Vì sao p99 tăng sớm hơn cảm nhận từ trung bình?

Khi một số request bị cache miss, chờ kết nối hoặc đọc phân vùng nóng, chúng tạo thành phần đuôi dài. Nếu API phải gọi nhiều service hoặc fan-out đến nhiều shard, một nhánh chậm có thể kéo dài yêu cầu tổng thể. Tối ưu p99 đòi hỏi tìm những nguyên nhân gián đoạn, không chỉ tăng tốc câu truy vấn “thường gặp”.

## 6. Các yếu tố của NoSQL ảnh hưởng đến ba chỉ số vận hành

### 6.1. Khóa phân vùng và dữ liệu nóng

Hệ NoSQL phân tán thường quyết định nơi lưu/truy xuất dữ liệu dựa trên **partition key/shard key**. Nếu mọi sự kiện đều mang cùng một khóa `tenant_id = 'hot-tenant'` và dồn đến một phân vùng, một nút có thể quá tải dù CPU trung bình toàn cụm còn thấp.

Ví dụ thiết kế khóa cho nhật ký:

| Thiết kế | Rủi ro/điểm mạnh |
|---|---|
| Chỉ `tenant_id` | Tenant lớn có thể làm nóng một phân vùng |
| `(tenant_id, day)` | Phân tán theo ngày, nhưng một tenant rất lớn trong cùng ngày vẫn có thể nóng |
| `(tenant_id, day, bucket)` | Có thể chia tải cho nhiều bucket; đọc phải truy vấn và tổng hợp nhiều bucket |

Chọn key cần biết mẫu truy vấn và mức phân bổ tải. Tạo thêm bucket giúp chia tải ghi nhưng có thể làm truy vấn đọc phức tạp và phát sinh fan-out. Không có một partition key đúng cho mọi workload.

### 6.2. Kích thước tài liệu/bản ghi

Trả về toàn bộ tài liệu 2 MB cho một trang chỉ cần tên và giá sản phẩm sẽ tiêu tốn mạng, CPU và bộ nhớ. Projection/chỉ chọn trường cần thiết giúp giảm dữ liệu truyền; phân trang giúp tránh phản hồi quá lớn. Tuy nhiên, việc đọc dữ liệu trên đĩa và lợi ích của projection còn phụ thuộc storage engine và chỉ mục.

Với tài liệu thường xuyên cập nhật một phần nhỏ, cấu trúc lồng nhau quá lớn có thể tăng chi phí ghi, tăng tranh chấp hoặc chịu giới hạn kích thước tài liệu tùy sản phẩm.

### 6.3. Chỉ mục và loại truy vấn

Truy vấn theo khóa được lập chỉ mục khác với quét toàn bộ collection. Các truy vấn lọc, sắp xếp, tổng hợp và tìm kiếm cần chỉ mục phù hợp; chỉ mục dư thừa lại làm tăng chi phí ghi và dung lượng lưu.

Đừng tối ưu “5.000 QPS” bằng một phép thử đọc theo khóa khi tải thật gồm cả aggregation, sort, query không dùng index và nhiều mức selectivity.

### 6.4. Sao chép và nhất quán

Replication giúp tăng khả năng chịu lỗi và, trong một số cấu hình, phân phối tải đọc. Nhưng các thao tác chờ nhiều bản sao xác nhận có thể tăng độ trễ ghi hoặc giảm tốc độ hoàn thành khi một replica chậm.

Ví dụ, đọc với yêu cầu nhất quán mạnh hơn có thể phải trao đổi thêm với các nút hoặc chờ nút phù hợp; đọc từ replica gần người dùng có thể nhanh hơn nhưng mức mới của dữ liệu phụ thuộc cơ chế nhất quán.

Mỗi phép đo phải kèm theo **read/write concern, consistency level, vùng địa lý và topology** để có ý nghĩa.

### 6.5. Bộ nhớ đệm và trạng thái hệ thống

Khi dữ liệu còn trong bộ nhớ, truy vấn thường nhanh hơn đọc từ bộ nhớ thứ cấp. Sau khi khởi động, thay đổi tập truy cập hoặc làm mới cache, p95/p99 có thể khác đáng kể.

Một số hệ dùng cấu trúc lưu trữ cần compaction, có thể tạo tải I/O nền. TTL, tombstone, garbage collection, snapshot, backup và quá trình đồng bộ replica cũng ảnh hưởng độ trễ. Bài kiểm tra cần đủ dài để quan sát tình trạng ổn định và những hoạt động nền quan trọng.

### 6.6. Vị trí địa lý và mạng

Ứng dụng đặt ở một vùng địa lý nhưng DB ở vùng khác phải trả chi phí đường truyền cho mỗi lượt trao đổi. Nếu một yêu cầu thực hiện nhiều lần đọc nối tiếp, độ trễ đường truyền có thể cộng dồn. Phân phối dữ liệu đa vùng cần cân bằng độ trễ, chi phí nhân bản, khả năng chịu lỗi và tính nhất quán.

## 7. Mục tiêu chất lượng dịch vụ: SLI, SLO và SLA

### 7.1. Ba khái niệm khác nhau

- **SLI (Service Level Indicator):** chỉ số đo chất lượng dịch vụ thực tế, chẳng hạn tỷ lệ yêu cầu thành công hoặc tỷ lệ phản hồi dưới ngưỡng thời gian.
- **SLO (Service Level Objective):** mục tiêu cụ thể đặt ra cho SLI trong một cửa sổ thời gian nhất định.
- **SLA (Service Level Agreement):** thỏa thuận cam kết chất lượng với khách hàng, thường có điều khoản trách nhiệm, bồi hoàn hoặc biện pháp xử lý khi không đạt.

SLO là công cụ kỹ thuật để vận hành, thường được đặt chặt chẽ và đo thường xuyên. SLA có thể sử dụng một số chỉ tiêu tương tự nhưng là khái niệm về cam kết giữa các bên. Không phải mọi SLO đều trở thành SLA.

### 7.2. Định nghĩa SLI sao cho đo được

Ví dụ cho API đọc sản phẩm:

> Trong cửa sổ 30 ngày, ít nhất **99,9%** yêu cầu `GET /products/{id}` hợp lệ phải trả về trạng thái đúng và toàn bộ nội dung phản hồi trong **200 ms** hoặc nhanh hơn, đo tại API gateway.

Ở đây:

- **Đối tượng:** API GET sản phẩm.
- **Mẫu số:** số yêu cầu hợp lệ, theo quy định đo của dịch vụ.
- **Yêu cầu tốt:** kết quả đúng *và* trả về trong 200 ms.
- **Ngưỡng:** 99,9% yêu cầu tốt.
- **Cửa sổ:** 30 ngày.
- **Điểm đo:** API gateway.

Ta có thể định nghĩa:

```text
SLI yêu cầu tốt (%) =
    100 × (số yêu cầu hợp lệ, trả kết quả đúng trong ≤ 200 ms)
          / (tổng số yêu cầu hợp lệ)
```

Yêu cầu timeout và lỗi server làm giảm tỷ lệ yêu cầu tốt. Cần quy định rõ cách xử lý yêu cầu bị client hủy, lỗi 4xx do tham số không hợp lệ, request thử nghiệm, retry và lỗi từ tầng gateway. Tránh loại trừ tùy tiện những trường hợp chậm hoặc lỗi chỉ để báo cáo đẹp.

**Một SLO gộp độ trễ và lỗi** như trên trả lời trực tiếp việc người dùng có nhận được phản hồi dùng được kịp thời hay không. Dịch vụ vẫn nên theo dõi riêng p50/p95/p99, error rate và availability để chẩn đoán nguyên nhân.

### 7.3. Error budget

Nếu mục tiêu là 99,9% yêu cầu tốt, tỷ lệ ngân sách cho yêu cầu “không tốt” là:

```text
Error budget = 100% - 99,9% = 0,1%
```

Trong một cửa sổ có 20.000.000 yêu cầu thuộc phạm vi đo:

```text
Ngân sách yêu cầu không tốt
    = 20.000.000 × 0,001
    = 20.000 yêu cầu
```

Tất cả lỗi, timeout và phản hồi vượt 200 ms được định nghĩa là không tốt đều tiêu thụ ngân sách đó. Đây là cách theo dõi khả năng chịu đựng chất lượng kém theo tiêu chí đã chọn, không phải quyền cố tình gây lỗi.

Với SLO về **thời gian sẵn sàng** 99,9% trong một cửa sổ cố định 30 ngày, khoảng thời gian không sẵn sàng theo ngưỡng là:

```text
30 ngày × 24 giờ × 60 phút × (1 - 0,999)
= 43,2 phút
```

Ngân sách theo thời gian khác với ngân sách theo số yêu cầu; đừng trộn hai cách tính. Nếu lưu lượng giờ cao điểm lớn hơn bình thường, một phút lỗi có thể làm hỏng rất nhiều yêu cầu dù thời gian mất dịch vụ không dài.

### 7.4. SLO cho những thao tác khác nhau

| Workload | Ví dụ chỉ tiêu kỹ thuật | Điều phải làm rõ |
|---|---|---|
| Đọc dữ liệu sản phẩm | p95 API ≤ 120 ms ở tải dự kiến; tỷ lệ thành công ≥ 99,9% | Mức cache hit, kích thước tài liệu |
| Đặt hàng | Tỷ lệ giao dịch xử lý đúng ≥ 99,95% và độ trễ trong ngưỡng riêng | Tính nguyên tử, chống đặt trùng, xác nhận bền vững |
| Ingest telemetry | Duy trì ≥ 50.000 sự kiện/s, lỗi ≤ 0,1% | Kích thước event, policy retry, lag cuối nguồn |
| Truy vấn phân tích | p95 ≤ 5 s với loại truy vấn được định nghĩa | Khối lượng quét, số người chạy đồng thời |
| Đồng bộ tìm kiếm | 99% thay đổi xuất hiện trong index trong ≤ 10 s | Độ trễ lan truyền và lỗi đồng bộ |

Các con số trên chỉ là **ví dụ thiết kế SLO**, không phải chuẩn áp dụng sẵn cho mọi dự án. Mỗi SLO cần được thống nhất với người dùng sản phẩm và kiểm chứng bằng phép đo thật.

### 7.5. SLO gắn với trải nghiệm và tính đúng đắn

Không nên chỉ đặt “DB p99 < 50 ms” nếu API vẫn trả chậm hoặc trả sai. Mục tiêu cuối cùng cần phản ánh trải nghiệm và tính chính xác của chức năng. Các metric DB là chỉ số hỗ trợ phân tích và cảnh báo.

Ví dụ trong hệ thanh toán, dữ liệu được ghi “rất nhanh” nhưng thiếu bảo đảm ghi bền hoặc xử lý trùng lặp vẫn là không đạt chất lượng. Tốc độ chỉ có ý nghĩa khi đi cùng cam kết đúng dữ liệu.

## 8. Lập hồ sơ tải và năng lực hệ thống

Trước khi cấu hình cơ sở dữ liệu, nên lập **workload profile** theo từng nhóm thao tác.

Một hồ sơ tối thiểu có thể gồm:

| Thuộc tính | Ví dụ |
|---|---|
| Loại yêu cầu | Đọc sản phẩm theo ID, cập nhật giỏ, ghi sự kiện |
| Tỷ lệ đọc/ghi | 75% đọc, 25% ghi |
| Tải trung bình/giờ cao điểm | 1.000 / 4.000 API req/s |
| Độ lệch tải | 20% khóa nhận 80% lượt truy cập, nếu quan sát thực tế đúng như vậy |
| Kích thước dữ liệu | 2 KB mỗi tài liệu trung bình; p99 100 KB |
| Số bản ghi | 50 triệu tài liệu; tăng 2 triệu/tháng |
| Độ trễ mục tiêu | p95 đọc ≤ 100 ms; p99 đọc ≤ 300 ms |
| Mức nhất quán | Theo yêu cầu nghiệp vụ của từng loại đọc/ghi |
| Tần suất đột biến | Khuyến mãi, đợt ghi telemetry đồng loạt |
| Topology | Số node, shard, replica, vùng địa lý |

Thông số đầu vào cần lấy từ sản phẩm thật, log truy cập và dữ liệu quan sát được. Nếu chưa có dữ liệu, ghi rõ giả định để thay thế sau khi triển khai thử.

### 8.1. Ví dụ tính đồng thời ban đầu

Một API dự kiến chạy ở mức **2.000 req/s**, trong đó 70% đọc với thời gian trung bình 35 ms, 30% ghi với thời gian trung bình 70 ms. Giả sử mỗi API request tương ứng đúng một thao tác DB và các giá trị đều đo trong cùng phạm vi:

```text
W trung bình = 0,70 × 35 ms + 0,30 × 70 ms
             = 45,5 ms = 0,0455 s

L = 2.000 × 0,0455 = 91 thao tác trung bình
```

Con số 91 giúp hình dung số thao tác đồng thời theo Little's Law. Nó **không chỉ ra tự động** nên đặt pool là 91 hoặc cần 91 connection. Cần kiểm tra cách driver xử lý nhiều request trên mỗi connection, số instance, số server, queue, tải đỉnh và mức dư địa khi lỗi.

Nếu lưu lượng đột ngột tăng gấp ba nhưng cụm chỉ xử lý bền vững được 2.500 req/s, hệ thống sẽ phải xếp hàng, từ chối sớm hoặc giảm tải; mở thêm kết nối không tạo thêm công suất CPU/đĩa.

## 9. Kiểm thử tải để tìm ngưỡng vận hành an toàn

### 9.1. Các dạng kiểm thử

| Loại kiểm thử | Cách thực hiện | Mục đích |
|---|---|---|
| Baseline | Tải thấp, ổn định | Có mốc latency/throughput ban đầu |
| Load test | Chạy mức tải dự kiến theo giờ bình thường và cao điểm | Kiểm tra SLO ở tải mục tiêu |
| Stress test | Tăng tải vượt năng lực dự kiến | Tìm điểm bão hòa và cách hệ phản ứng |
| Spike test | Tăng đột ngột trong thời gian ngắn | Kiểm tra queue, autoscaling và backpressure |
| Soak/endurance | Duy trì tải nhiều giờ | Phát hiện memory leak, compaction, cache, ổ đĩa |
| Failure test | Gián đoạn một node/replica hoặc kết nối mạng trong môi trường thử | Quan sát failover, retry và độ trễ khi sự cố |

Đối với bài toán NoSQL, dữ liệu thử phải có đủ **số bản ghi, kích thước, phân phối khóa, chỉ mục, tỷ lệ đọc/ghi và mức nhất quán** tương đương môi trường thật. Hệ có 1.000 tài liệu mẫu khó đại diện cho hệ có hàng trăm triệu tài liệu và nhiều partition nóng.

### 9.2. Cách phát sinh tải cũng ảnh hưởng kết quả

Một bộ phát sinh tải **closed-loop** thường chờ phản hồi của yêu cầu trước rồi mới gửi tiếp. Khi hệ thống chậm, nó tự gửi ít yêu cầu hơn; tải đo được có thể giảm đúng lúc ta muốn thấy hệ thống quá tải.

Một bộ phát sinh tải **open-loop** cố gắng phát yêu cầu theo tốc độ đã định dù phản hồi chậm; thường hữu ích để đo khả năng đáp ứng khi nhu cầu thật vẫn tiếp tục đến. Tuy nhiên, cần đủ tài nguyên tại máy tạo tải và cơ chế ghi nhận chính xác yêu cầu bị trễ hoặc không gửi được.

**Coordinated omission** là hiện tượng phép đo bỏ qua thời gian mà lẽ ra các yêu cầu phải đến nhưng bộ phát tải bị trì hoãn vì đang chờ. Nó có thể khiến p99 báo cáo đẹp hơn thực tế. Chọn công cụ đo và thiết kế lịch gửi phải phù hợp mục tiêu kiểm thử; đo cả thời gian chờ và yêu cầu bị từ chối.

### 9.3. Một quy trình thực hành

1. Xác định API/query, tải mục tiêu, tiêu chí đúng, mức nhất quán, thời gian chạy và SLO.
2. Chuẩn bị tập dữ liệu đại diện, bao gồm khóa phổ biến và khóa ít truy cập.
3. Xác nhận bộ tạo tải có đủ CPU, mạng và số client để không trở thành nút thắt.
4. Khởi động ở tải thấp, cho hệ thống ổn định và ghi metric nền.
5. Tăng tải theo các bậc, ghi throughput thành công, lỗi, p50/p95/p99, số kết nối và thời gian chờ queue.
6. Theo dõi từng node DB: CPU, memory, I/O, network, phân vùng nóng, replica lag, compaction, GC và mức dùng pool.
7. Chạy đủ lâu để thấy hoạt động nền; kiểm tra phản ứng khi lỗi xảy ra và sau khi hồi phục.
8. Xác định mức tải lớn nhất mà **toàn bộ tiêu chí SLO vẫn đạt**, kèm dư địa cho đột biến hoặc sự cố.

Khi thay đổi thiết kế dữ liệu hay hạ tầng, dùng lại cùng bộ điều kiện thử để so sánh có ý nghĩa.

### 9.4. Các chỉ số cần quan sát cùng nhau

```text
Ứng dụng / API
  - Tốc độ yêu cầu đến, throughput thành công
  - Response time p50/p95/p99
  - Tỷ lệ 4xx/5xx/timeout, retry
  - Số request in-flight, độ dài hàng đợi

Driver / kết nối
  - Connection active/idle/opening
  - Pool wait time, acquisition timeout
  - Request in-flight, retry và server selection

NoSQL cluster
  - CPU, RAM, disk IOPS/latency, network
  - Read/write ops, query latency
  - Hot partitions, scatter-gather, scan
  - Cache hit rate, compaction/GC, replica lag
```

Bảng điều khiển nên cho phép xem theo **thời gian, endpoint, loại truy vấn, node và shard/partition**. Trung bình toàn cụm có thể che giấu một node đã quá tải.

## 10. Nên xử lý thế nào khi hệ thống chậm hoặc quá tải?

Đi từ triệu chứng đo được đến nguyên nhân; tránh coi một tham số như “số connection” là giải pháp cho mọi vấn đề.

| Triệu chứng | Khả năng thường gặp | Hướng kiểm tra/xử lý |
|---|---|---|
| API p99 cao, DB query nhanh | Chờ pool, xử lý ở ứng dụng, mạng, retry | Tracing từng giai đoạn, đo pool wait và queue |
| Pool đầy nhưng CPU DB còn thấp | Pool quá nhỏ, connection leak, xử lý đồng thời bị giới hạn | Kiểm tra cách giữ/release connection; điều chỉnh theo driver |
| Tăng connection rồi p99 còn tệ hơn | DB đã bão hòa, tranh chấp I/O hoặc CPU | Giới hạn concurrency, tối ưu query, mở rộng đúng điểm nghẽn |
| CPU toàn cụm thấp nhưng một node quá tải | Hot partition hoặc mất cân bằng phân phối | Đo tải theo shard/key, xem lại phân vùng |
| Đọc chậm khi cache miss | Phải truy cập ổ đĩa, index chưa phù hợp | Xem execution plan, index, tỷ lệ cache hit |
| Ghi chậm theo đợt | Compaction, replication, index write amplification | Theo dõi I/O nền, cấu hình/chia tải, thiết kế ghi |
| Lỗi tăng vọt khi traffic spike | Queue không giới hạn, retry storm, timeouts dài | Backpressure, timeout, retry có giới hạn và jitter |
| p50 tốt nhưng p99 rất cao | Truy vấn hiếm, fan-out, node chậm, GC | Phân tích trace theo nhóm chậm, kiểm tra từng node |
| Hiệu năng giảm sau mở rộng node | Rebalancing, đồng bộ replica, network, routing | Đo giai đoạn chuyển dữ liệu, kiểm tra topology |

### 10.1. Tối ưu truy vấn và mô hình dữ liệu

Bắt đầu bằng câu hỏi: thao tác chậm nhất đọc/ghi những gì? Có lọc đúng theo partition key không? Có index phù hợp không? Có trả nhiều trường hơn cần thiết không? Có dùng pagination giới hạn kích thước trang không?

Trong NoSQL, thay đổi **cách nhóm bản ghi, thiết kế khóa phân vùng hoặc bổ sung read model theo câu truy vấn** đôi khi quan trọng hơn nâng cấp cấu hình. Nhưng phi chuẩn hóa để tăng tốc đọc phải đi cùng chiến lược cập nhật và kiểm soát tính nhất quán của dữ liệu sao chép.

### 10.2. Caching

Cache có thể giảm số lần đọc DB nếu nhiều yêu cầu lặp lại cùng dữ liệu. Cần quyết định:

- Dữ liệu nào được cache và với khóa nào?
- TTL là bao lâu, khi nào xóa hoặc làm mới?
- Khi dữ liệu thay đổi, có cho phép cache trả kết quả cũ trong khoảng thời gian ngắn không?
- Khi cache đồng loạt hết hạn, có cách hạn chế đám đông request dồn đến DB không?

Không dùng cache để che giấu vấn đề tính đúng đắn hoặc tính nhất quán của nghiệp vụ quan trọng. Một số dữ liệu như số dư hoặc ghế còn trống cần thiết kế cẩn thận hơn dữ liệu danh mục.

### 10.3. Backpressure, timeout và retry

Khi yêu cầu đến nhanh hơn khả năng phục vụ, hệ thống cần cơ chế điều tiết:

- **Giới hạn concurrency** hoặc queue tại ứng dụng để tránh dồn tải vô hạn.
- **Timeout** theo tổng ngân sách thời gian của request; timeout ở driver nên phù hợp với timeout bên ngoài.
- **Từ chối sớm** hoặc trả trạng thái quá tải có kiểm soát khi không còn khả năng xử lý.
- **Retry có giới hạn, có backoff và jitter** cho lỗi tạm thời; không retry vô điều kiện thao tác không idempotent.
- **Idempotency key** hoặc cơ chế chống thực hiện trùng với yêu cầu ghi có thể bị gửi lại.

Ví dụ, nếu tất cả client đều retry ngay ba lần khi một nút chậm, số yêu cầu dồn vào nút đó có thể tăng mạnh và làm sự cố kéo dài. Retry phải có ngân sách và quan sát được như một thành phần của tải.

### 10.4. Mở rộng đúng nút thắt

Nếu đĩa của một node đã tối đa IOPS, tăng số kết nối không làm đĩa nhanh hơn. Nếu mọi request đến cùng một khóa nóng, thêm node cũng chưa chắc chia được tải. Nếu dữ liệu chậm do mạng xuyên vùng, thêm CPU DB có thể không cải thiện.

Việc mở rộng có thể gồm thêm tài nguyên cho node, phân mảnh lại dữ liệu, bổ sung replica cho tải đọc, tối ưu chỉ mục hoặc tách workload phân tích khỏi đường giao dịch. Mỗi giải pháp phải gắn với metric cho thấy giới hạn nằm ở đâu.

## 11. Một ví dụ thiết kế SLO và khả năng chịu tải

Giả sử một dịch vụ API sử dụng NoSQL document database để hiển thị danh mục sản phẩm.

**Bối cảnh:**

- Giờ bình thường: 600 req/s; giờ cao điểm dự kiến: 2.000 req/s.
- Phần lớn yêu cầu đọc theo `product_id`, một số đọc danh sách sản phẩm có filter.
- Kích thước kết quả danh mục khoảng vài KB, nhưng một số sản phẩm có metadata lớn.
- API cần phản hồi chính xác; dữ liệu mô tả sản phẩm có thể cho phép cache trong giới hạn đã thỏa thuận.

**Đề xuất mục tiêu đo lường (minh họa):**

| Chỉ tiêu | Cách đặt |
|---|---|
| Good-request SLO | ≥ 99,9% yêu cầu GET hợp lệ có kết quả đúng trong ≤ 200 ms trên cửa sổ 30 ngày |
| Ngưỡng kiểm thử tải | Tại 2.000 req/s, p95 ≤ 120 ms và p99 ≤ 300 ms; tỷ lệ lỗi ≤ 0,1% |
| Phạm vi phép đo | Tại API gateway, theo từng endpoint; DB driver metrics để chẩn đoán |
| Kiểm tra kết nối | Không có pool-wait kéo dài hay acquisition-timeout ở mức tải cam kết |
| Kiểm tra cụm | Không có node/partition bão hòa kéo dài; còn dư địa khi một node gặp lỗi theo yêu cầu hệ thống |

Bảng kiểm thử có p99 ≤ 300 ms không tự động chứng minh SLO “99,9% trong ≤ 200 ms”; cần đo riêng tỷ lệ yêu cầu đạt ngưỡng 200 ms. SLO dài hạn cũng không được chứng minh chỉ bằng một lần benchmark ngắn.

**Các bước đưa vào thiết kế:**

1. Lấy mẫu truy vấn thật và xem câu nào đọc theo khóa, câu nào lọc nhiều điều kiện.
2. Đảm bảo các truy vấn phổ biến có chỉ mục và không trả dữ liệu thừa.
3. Xem phân phối khóa truy cập để nhận diện sản phẩm cực kỳ phổ biến hoặc tập dữ liệu quá lớn.
4. Dùng pool được quản lý qua vòng đời ứng dụng; tính tổng connection khi autoscaling.
5. Theo dõi API latency, driver pool wait, query latency, lỗi và metric từng node.
6. Kiểm thử 600, 2.000 và trên 2.000 req/s, cùng trường hợp traffic spike và lỗi node.
7. Nếu lỗi SLO, tìm tầng gây chậm trước khi quyết định tăng pool, tăng node hay đổi mô hình dữ liệu.

Ở giai đoạn đầu, dịch vụ có thể chỉ cần một DB và một cache. Việc thêm công nghệ mới hoặc thay toàn bộ mô hình lưu trữ cần dựa trên dữ liệu đo được và chi phí vận hành thực tế.

## 12. Các sai lầm cần tránh

**“Thêm connection thì chắc chắn tăng QPS.”** Connection chỉ là một tài nguyên. Nếu điểm nghẽn nằm ở CPU, I/O, hotspot hoặc replica, thêm connection có thể làm hệ chậm hơn.

**“p99 thấp hơn 100 ms nghĩa là mọi yêu cầu dưới 100 ms.”** Sai. Khoảng 1% mẫu có thể vượt ngưỡng đó; vẫn cần xem timeout, lỗi và quy mô mẫu.

**“DB đạt 10.000 ops/s nên API chịu được 10.000 req/s.”** Sai. Một API request có thể tạo nhiều DB operations, tốn thêm xử lý, truy vấn nhiều bản ghi hoặc gọi dịch vụ khác.

**“Latency trung bình là đủ để đặt SLO.”** Sai. Trung bình che giấu các request chậm; một SLO tốt nên được xác định theo trải nghiệm mong muốn, ví dụ tỷ lệ yêu cầu tốt trong ngưỡng thời gian.

**“Dữ liệu càng nhiều thì throughput chắc chắn giảm theo cùng một tỷ lệ.”** Không thể kết luận chỉ từ dung lượng. Hiệu năng còn phụ thuộc mẫu truy cập, index, cache, kích thước bản ghi, phân phối khóa và cấu hình tài nguyên.

**“Benchmark với 1.000 bản ghi chứng minh hệ chạy tốt với 100 triệu bản ghi.”** Sai. Kích thước dữ liệu, chỉ mục, bộ nhớ đệm và quá trình phân vùng ảnh hưởng lớn đến kết quả.

**“SLO là một con số p95 không có thời hạn.”** Chưa đủ. SLO cần đơn vị đo, điểm đo, phạm vi request và cửa sổ đánh giá, cùng quy tắc xử lý lỗi hoặc ngoại lệ.

**“Tăng retry sẽ giúp hệ ổn định khi quá tải.”** Retry thiếu giới hạn thường làm tải thêm nặng. Cần timeout, giới hạn concurrency, backoff và kiểm soát idempotency.

## 13. Bài tập tự vận dụng

### Bài tập 1: lượng thao tác đồng thời

Một dịch vụ đọc từ database đạt 1.200 ops/s ở trạng thái ổn định, thời gian từ lúc gửi đến lúc hoàn thành thao tác trung bình là 50 ms.

1. Theo Little's Law, trung bình có bao nhiêu thao tác trong phạm vi đo?
2. Có thể kết luận pool cần đúng số kết nối như kết quả vừa tính không? Vì sao?

**Gợi ý:** `L = 1.200 × 0,05 = 60` thao tác. Số connection cần phụ thuộc driver, khả năng multiplex, số instance, cách phân phối truy vấn và giới hạn tài nguyên. Không thể suy trực tiếp từ `L`.

### Bài tập 2: throughput và tỷ lệ lỗi

Trong 60 giây, một benchmark gửi 150.000 yêu cầu; 141.000 thành công, 9.000 timeout.

1. Offered load trung bình là bao nhiêu request/s?
2. Throughput thành công là bao nhiêu request/s?
3. Tỷ lệ lỗi là bao nhiêu? Có nên tuyên bố hệ “chịu được 2.500 RPS” không?

**Gợi ý:** tải đến 2.500 req/s, throughput thành công 2.350 req/s, timeout 6%. Mức tải đó không đạt yêu cầu nếu SLO lỗi nhỏ hơn 6%.

### Bài tập 3: tìm nút thắt

Một API có p99 1.200 ms, nhưng truy vấn DB p99 chỉ 30 ms. Driver báo 400 ms chờ connection pool ở một số request, CPU DB khoảng 40%.

**Câu hỏi:** Nên ưu tiên điều tra thành phần nào?

**Gợi ý:** Hãy kiểm tra pool wait, cách tái sử dụng client, connection leak, số request in-flight và giới hạn pool so với số instance. Chưa có bằng chứng rằng việc tăng số node DB hoặc đổi schema sẽ xử lý được 400 ms chờ pool.

### Bài tập 4: định nghĩa SLO

Nhóm phát triển viết: “API phải nhanh, sẵn sàng 99,9%”. Hãy viết lại thành chỉ tiêu kiểm chứng được.

**Một cách diễn đạt:** “Trong 30 ngày, ít nhất 99,9% yêu cầu GET hợp lệ được nhận tại API gateway trả về kết quả đúng trong không quá 250 ms; timeout và lỗi server được tính là yêu cầu không tốt”. Sau đó định nghĩa rõ trường hợp client hủy, lỗi nhập liệu, thời điểm bắt đầu/kết thúc và cách tổng hợp metric.

## 14. Kết luận

Khi thiết kế hệ thống sử dụng NoSQL, cần nhìn đồng thời vào **độ trễ, thông lượng, số thao tác đồng thời, giới hạn kết nối và SLO**. Độ trễ phản ánh thời gian chờ; thông lượng phản ánh lượng công việc hoàn tất; connection pool giới hạn một phần cách ứng dụng tương tác với DB; SLO chuyển yêu cầu trải nghiệm thành tiêu chí kiểm chứng được.

Một hệ thống đáng tin cậy không chỉ đạt thông lượng cao trong một benchmark đọc theo khóa. Nó phải giữ được độ trễ và tính đúng đắn theo SLO tại tải thực tế, kể cả khi có phân vùng nóng, bộ nhớ đệm chưa sẵn sàng, đột biến truy cập hoặc lỗi nút. Lập hồ sơ tải, đo bằng nhiều tầng metric, thử nghiệm với dữ liệu đại diện và tối ưu đúng điểm nghẽn là nền tảng cho quyết định vận hành NoSQL hiệu quả.
