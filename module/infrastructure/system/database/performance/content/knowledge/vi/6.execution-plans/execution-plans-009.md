# Những thông tin kế hoạch không phản ánh đầy đủ: mạng, hàng đợi và xử lý phía ứng dụng

Kế hoạch thực thi cho biết hệ quản trị cơ sở dữ liệu dự định hoặc đã thực hiện các bước nào để lấy và thay đổi dữ liệu: quét bảng, quét chỉ mục, join, sort, aggregate, lọc và ghi. Đây là nguồn thông tin quan trọng khi tối ưu SQL, nhưng nó chỉ mô tả một phần đường đi của yêu cầu. Một kế hoạch có chi phí ước lượng thấp hoặc thời gian thực thi trong DB rất ngắn không bảo đảm người dùng nhận được phản hồi nhanh.

Trong một ứng dụng thực tế, yêu cầu có thể phải chờ trong hàng đợi của máy chủ ứng dụng, chờ lấy kết nối từ pool, đi qua mạng, chờ DB tiếp nhận, thực thi truy vấn, truyền kết quả về, được driver giải mã, ORM chuyển thành đối tượng và cuối cùng được ứng dụng xử lý hoặc hiển thị. Kế hoạch thực thi không thể hiện đầy đủ các bước nằm ngoài phạm vi thực thi của DB. Một số loại chờ bên trong DB cũng cần được xem qua wait events, thống kê phiên hoặc công cụ giám sát riêng, chứ không thể suy ra chỉ từ cây toán tử.

Với phạm vi DATABASE_PERFORMANCE, cần kết hợp kế hoạch thực thi với đo đạc tải, thống kê và cơ chế truy cập dữ liệu. Bài học này tập trung vào ba nhóm thông tin thường bị bỏ sót khi chỉ đọc execution plan: mạng, hàng đợi và xử lý phía ứng dụng. Mục tiêu là xác định thời gian thực sự được tiêu thụ ở đâu, chọn đúng lớp cần điều chỉnh và kiểm chứng toàn bộ yêu cầu sau thay đổi.

## 1. Phạm vi của kế hoạch thực thi

Một execution plan mô tả cách bộ tối ưu truy vấn tổ chức công việc bên trong hệ quản trị. Tùy hệ quản trị và chế độ thu thập, kế hoạch có thể cho biết:

- Các toán tử truy cập dữ liệu như table scan, index scan, index seek hoặc bitmap scan.
- Thứ tự join, kiểu join, sort, aggregate, filter và các toán tử trung gian.
- Số hàng ước lượng và đôi khi số hàng thực tế.
- Chi phí ước lượng, số lần chạy toán tử, bộ nhớ hoặc dữ liệu tạm sử dụng.
- Thời gian thực thi hoặc thời gian của từng toán tử trong chế độ phân tích thực tế, nếu công cụ hỗ trợ.

Những thông tin này giúp trả lời câu hỏi: DB đã chọn cách nào để xử lý câu SQL và công việc bên trong DB có hợp lý hay không?

Kế hoạch thường không mô tả đầy đủ:

- Thời gian request nằm trong hàng đợi của load balancer, web server hoặc worker ứng dụng trước khi gọi DB.
- Thời gian chờ lấy một kết nối khả dụng từ connection pool.
- Độ trễ mạng giữa ứng dụng và DB, số lần round trip, mất gói và truyền lại.
- Thời gian thiết lập TCP/TLS hoặc xác thực kết nối nếu ứng dụng phải tạo kết nối mới.
- Thời gian driver gửi tham số, nhận từng phần kết quả, giải mã kiểu dữ liệu và chuyển dữ liệu sang cấu trúc của ngôn ngữ lập trình.
- Thời gian ORM tạo đối tượng, ánh xạ quan hệ, chạy hook hoặc lazy loading.
- Thời gian serialize thành JSON, gọi dịch vụ khác, áp dụng quy tắc nghiệp vụ, render giao diện hoặc ghi log.
- Thời gian yêu cầu chờ ở hàng đợi nội bộ của DB trước khi được xử lý, nếu kế hoạch không thể hiện riêng phần chờ đó.

Kế hoạch cũng không phải lúc nào cũng cung cấp một con số thời gian có thể so sánh trực tiếp giữa các hệ quản trị. Một số công cụ hiển thị chi phí ước lượng tương đối, không phải mili giây. Một số công cụ đo thời gian thực tế theo toán tử, nhưng cách tính có thể bao gồm hoặc loại trừ các loại chờ khác nhau. Cần đọc tài liệu của hệ quản trị và phân biệt rõ estimated cost, operator time, statement elapsed time và thời gian phía ứng dụng.

### Các mốc thời gian cần phân biệt

| Mốc đo | Phạm vi | Dùng để trả lời |
|---|---|---|
| Request elapsed time | Từ lúc ứng dụng nhận yêu cầu đến khi hoàn tất phản hồi | Người dùng phải chờ bao lâu? |
| Application queue wait | Thời gian request chờ worker hoặc tài nguyên ứng dụng | Ứng dụng có đủ worker để nhận tải? |
| Connection pool wait | Thời gian chờ lấy kết nối DB | Pool có bão hòa hoặc kết nối bị giữ quá lâu? |
| DB client call elapsed | Từ lúc driver bắt đầu gọi DB đến khi hoàn tất thao tác theo định nghĩa driver | Toàn bộ lượt gọi DB mất bao lâu? |
| DB statement execution | Thời gian hệ quản trị xử lý câu lệnh theo số liệu của DB | Bản thân câu SQL mất bao lâu trong DB? |
| Result fetch/transfer | Thời gian nhận hết dữ liệu từ DB và chuyển qua mạng | Kết quả lớn hoặc truyền chậm đến mức nào? |
| Application processing | Giải mã, ánh xạ, tính toán và serialize dữ liệu | Ứng dụng mất bao lâu sau khi nhận kết quả? |

Các mốc này có thể lồng nhau hoặc được công cụ định nghĩa khác nhau. Ví dụ, một API driver có thể tính cả thời gian fetch vào thời gian gọi truy vấn; một công cụ khác ghi riêng thời gian execute và fetch. Trước khi so sánh, hãy xác nhận chính xác điểm bắt đầu và kết thúc của từng phép đo.

## 2. Mạng: độ trễ, thông lượng và số lần round trip

Kết nối ứng dụng với DB thường đi qua loopback, mạng nội bộ, vùng mạng cloud, VPN hoặc nhiều lớp proxy. Độ trễ của đường truyền có thể trở thành phần đáng kể của thời gian phản hồi, nhất là khi ứng dụng thực hiện nhiều lượt gọi tuần tự.

### RTT và chi phí trao đổi tuần tự

RTT (round-trip time) là thời gian một gói tin đi đến đích và phản hồi quay lại. Khi một thao tác cần chờ phản hồi trước khi gửi thao tác tiếp theo, mỗi round trip có thể cộng thêm một phần RTT vào thời gian hoàn tất.

Ví dụ, một endpoint thực hiện 40 truy vấn tuần tự, mỗi truy vấn mất khoảng 3 ms trong DB và đường truyền có RTT 12 ms. Bỏ qua các chi phí khác, phần thời gian tối thiểu có thể đã xấp xỉ:

```text
40 × (12 ms + 3 ms) = 600 ms
```

Trong khi đó, một kế hoạch đơn lẻ chỉ hiển thị 3 ms. Nếu các truy vấn có thể được gộp thành một truy vấn hoặc một batch, số lần trao đổi tuần tự có thể giảm đáng kể. Đây là một nguyên nhân thường gặp của N+1 query trong ORM.

Không nên áp dụng phép nhân này máy móc cho mọi kết nối. Một số giao thức có thể pipeline nhiều lệnh, driver có thể đọc kết quả bất đồng bộ, và thời gian DB có thể chồng lấp với thời gian truyền dữ liệu. Tuy vậy, khi các bước phụ thuộc nhau và phải đợi phản hồi từng lần, RTT là chi phí thực.

### Throughput và kích thước kết quả

Throughput là lượng dữ liệu truyền được trong một đơn vị thời gian. Một truy vấn trả về ít hàng có thể bị giới hạn bởi RTT; một truy vấn trả về hàng trăm nghìn hàng có thể bị giới hạn bởi băng thông, tốc độ đọc socket, giải mã và xử lý ở client.

Để ước lượng sơ bộ, nếu kết quả có kích thước 80 MiB và thông lượng hiệu dụng là 40 MiB/s, riêng thời gian truyền lý tưởng đã vào khoảng 2 giây. Thực tế còn có protocol overhead, TLS, phân mảnh gói, congestion, thời gian fetch, giải mã và tốc độ tiêu thụ của ứng dụng.

Kế hoạch có thể cho biết số hàng dự kiến hoặc số hàng thực tế được toán tử trả ra, nhưng thường không cho biết chính xác số byte cuối cùng được truyền đến client. Độ rộng hàng, encoding, kiểu dữ liệu, NULL, protocol framing và nén đều ảnh hưởng đến kích thước trên dây.

### Các yếu tố mạng cần đo

| Chỉ số | Ý nghĩa | Khi nào đáng chú ý |
|---|---|---|
| RTT | Độ trễ khứ hồi giữa app và DB | Nhiều lệnh tuần tự hoặc kết nối ở xa |
| Throughput | Lượng dữ liệu truyền mỗi giây | Kết quả truy vấn lớn hoặc batch truyền nhiều dữ liệu |
| Packet loss | Gói tin bị mất | Có thể làm giảm thông lượng và tăng độ trễ |
| TCP retransmission | Gói phải truyền lại | Dấu hiệu đường truyền hoặc thiết bị mạng gặp vấn đề |
| Connection setup time | Thời gian tạo kết nối và xác thực | Ứng dụng tạo kết nối mới quá thường xuyên |
| Socket send/receive queue | Dữ liệu đang chờ gửi hoặc nhận | Một phía tạo hoặc tiêu thụ dữ liệu chậm |
| TLS handshake/CPU | Chi phí thiết lập và mã hóa kết nối | Kết nối ngắn, nhiều lần tạo mới hoặc TLS nặng |

Các chỉ số này cần được lấy ở cả hai đầu hoặc từ nền tảng mạng nếu có thể. Một bộ đếm retransmission tăng ở máy DB không tự chứng minh máy DB là nơi gây mất gói; nguyên nhân có thể nằm ở client, switch, firewall, proxy hoặc đường truyền giữa hai đầu.

### Giảm chi phí mạng

Một số biện pháp thường có ích:

1. Dùng connection pool để tái sử dụng kết nối, tránh tạo TCP/TLS và xác thực cho mỗi truy vấn.
2. Giảm số round trip bằng cách gộp truy vấn, dùng batch hoặc thực hiện phép tính phù hợp ở DB.
3. Chỉ trả về các cột và hàng ứng dụng thật sự cần; tránh lấy toàn bộ bảng rồi lọc ở client.
4. Dùng phân trang hoặc cursor/streaming khi tập kết quả lớn.
5. Đặt ứng dụng gần DB về mặt mạng nếu kiến trúc và yêu cầu sẵn sàng cho phép.
6. Kiểm tra retransmission, packet drops, giới hạn băng thông và thiết lập TLS khi có bằng chứng.

Không nên giảm dữ liệu trả về bằng cách chuyển toàn bộ logic sang DB nếu điều đó khiến truy vấn trở nên khó bảo trì hoặc tạo tải tính toán mới không cần thiết. Hãy chọn nơi xử lý dựa trên chi phí tổng thể và ranh giới nghiệp vụ.

## 3. Hàng đợi: thời gian chờ trước khi truy vấn chạy

Một yêu cầu có thể chờ ở nhiều hàng đợi trước khi execution plan được thực thi. Ví dụ: hàng đợi request của web server, worker pool, connection pool, hàng đợi tiếp nhận kết nối của DB, bộ lập lịch nội bộ, hàng đợi khóa và hàng đợi I/O.

Nếu chỉ nhìn execution plan, ta có thể thấy câu lệnh chạy nhanh sau khi bắt đầu nhưng bỏ qua thời gian nó đã chờ trước đó.

### Các lớp hàng đợi thường gặp

| Hàng đợi | Nơi xuất hiện | Chỉ số nên theo dõi |
|---|---|---|
| Request queue | Load balancer, web server, API gateway | Queue depth, oldest request age, rejected request |
| Worker/thread pool | Runtime ứng dụng | Worker active/idle, task queue, scheduling delay |
| Connection pool | Driver hoặc thư viện truy cập DB | Active/idle connection, pending acquire, acquire wait |
| DB admission/connection | DB hoặc proxy DB | Connection backlog, active sessions, giới hạn phiên |
| Lock/latch wait | Bên trong DB | Blocking session, lock wait duration, deadlock |
| Storage I/O queue | Kernel, thiết bị hoặc dịch vụ lưu trữ | Queue depth, I/O latency, IOPS |
| Socket queue | TCP stack ở hai đầu | Send/receive queue, retransmit, socket buffer pressure |

Một request có thể trải qua nhiều hàng đợi nối tiếp. Cần xác định thời gian chờ ở từng tầng thay vì gom tất cả thành “DB chậm”.

### Định luật Little và độ đồng thời

Trong trạng thái ổn định, định luật Little mô tả quan hệ giữa số công việc trung bình trong hệ thống, tốc độ đến và thời gian lưu lại:

```text
L = λ × W
```

Trong đó:

- `L` là số yêu cầu trung bình đang ở trong hệ thống.
- `λ` là tốc độ đến trung bình.
- `W` là thời gian trung bình từ lúc yêu cầu vào đến lúc rời khỏi hệ thống.

Ví dụ, nếu ứng dụng nhận 100 request/giây và mỗi request mất trung bình 0,2 giây, số request đang hoạt động trung bình xấp xỉ 20. Nếu thời gian tăng lên 1 giây trong khi tốc độ đến vẫn là 100 request/giây, số request đang hoạt động có thể tăng lên khoảng 100.

Định luật Little áp dụng cho trung bình trong hệ thống ổn định và cùng một phạm vi đo. Nó không trực tiếp dự báo phân vị p95/p99 hoặc một burst ngắn đang làm backlog tăng. Tuy nhiên, nó giải thích vì sao thời gian phản hồi tăng sẽ làm số request đồng thời tăng nếu tốc độ đến giữ nguyên.

Khi một pool hoặc tài nguyên hoạt động gần giới hạn, hàng đợi có thể tăng rất nhanh. Thêm kết nối DB trong tình huống này có thể làm tăng số phiên tranh CPU, bộ nhớ, khóa và I/O mà không tăng năng lực phục vụ. Cần tìm giới hạn thực tế và dùng admission control/backpressure thay vì chỉ nâng số kết nối.

### Connection pool wait

Connection pool thường giới hạn số kết nối đồng thời để bảo vệ DB và giảm chi phí tạo kết nối. Khi tất cả kết nối đang được mượn, request mới phải chờ.

Các chỉ số cần theo dõi:

- Số kết nối tối đa, active, idle và pending acquire.
- Thời gian chờ lấy kết nối theo p50/p95/p99.
- Thời gian một request giữ kết nối.
- Tỷ lệ timeout khi lấy kết nối.
- Số kết nối bị giữ quá lâu hoặc không được trả về.
- Số truy vấn đang chạy trên mỗi kết nối và số transaction mở.

Pool wait cao có thể xuất hiện dù DB CPU thấp. Nguyên nhân có thể là ứng dụng giữ connection trong khi gọi dịch vụ khác, mở transaction quá sớm, không đóng cursor/result set, pool quá nhỏ hoặc DB đang xử lý các truy vấn dài.

Tăng pool size chỉ nên thực hiện sau khi kiểm tra giới hạn DB và năng lực xử lý. Nếu 30 kết nối đã làm DB bão hòa I/O, tăng lên 100 có thể chỉ tạo thêm hàng đợi và tranh chấp.

## 4. Xử lý phía ứng dụng sau khi DB trả kết quả

Sau khi DB thực hiện truy vấn, ứng dụng vẫn có thể phải làm nhiều việc trước khi hoàn tất request. Kế hoạch thực thi không mô tả đầy đủ các bước này.

### Driver và fetch dữ liệu

Driver có thể nhận kết quả theo từng batch, buffer toàn bộ kết quả hoặc cung cấp cursor/stream. Kích thước fetch ảnh hưởng số round trip, bộ nhớ client và độ trễ đến hàng cuối cùng.

- Fetch size quá nhỏ có thể tạo nhiều lần trao đổi mạng.
- Fetch size quá lớn có thể dùng nhiều RAM, tăng áp lực GC và khiến ứng dụng giữ dữ liệu lâu.
- Buffer toàn bộ kết quả làm tăng thời gian đến khi ứng dụng có thể xử lý từng phần và có thể gây memory pressure.
- Streaming cho phép xử lý từng phần, nhưng cần quản lý vòng đời cursor và connection; cursor mở lâu có thể giữ tài nguyên DB.

Khi đo, hãy tách thời gian execute khỏi thời gian fetch nếu driver hỗ trợ. Với API bất đồng bộ, cần ghi rõ thời gian đến khi lệnh được gửi, thời gian nhận metadata, thời gian nhận hàng đầu tiên và thời gian nhận hàng cuối cùng.

### ORM và ánh xạ đối tượng

ORM có thể chuyển mỗi hàng thành một đối tượng, ánh xạ quan hệ, kiểm tra identity map, thực hiện lazy loading hoặc chạy hook. Với tập kết quả lớn, chi phí cấp phát đối tượng và xử lý quan hệ có thể vượt thời gian DB.

N+1 query là ví dụ điển hình: một truy vấn lấy danh sách cha, sau đó mỗi bản ghi cha kích hoạt một truy vấn con. Execution plan của từng truy vấn có thể rất tốt, nhưng tổng số lần gọi DB và round trip làm request chậm.

Các hướng xử lý gồm:

- Dùng eager loading hoặc join/batch phù hợp để giảm số truy vấn.
- Chỉ ánh xạ các trường cần thiết bằng projection hoặc DTO.
- Tránh tải quan hệ lớn nếu màn hình không dùng.
- Dùng pagination thay vì materialize một tập dữ liệu không giới hạn.
- Kiểm tra log SQL và số lần thực thi trong một request.

Join quá rộng cũng có thể tạo nhiều hàng trùng lặp rồi ORM phải khử trùng hoặc dựng lại đồ thị đối tượng. Do đó, gộp truy vấn cần được đánh giá cùng kích thước kết quả và chi phí ánh xạ.

### Xử lý nghiệp vụ, serialize và render

Ứng dụng có thể thực hiện tính toán, kiểm tra quyền, chuyển đổi tiền tệ, tổng hợp dữ liệu, serialize JSON, nén response hoặc gọi dịch vụ khác. Ở client, dữ liệu có thể tiếp tục được parse, sắp xếp, dựng component và render.

Một số chỉ số nên ghi nhận:

| Giai đoạn | Chỉ số |
|---|---|
| Worker ứng dụng | Queue wait, scheduling delay, worker utilization |
| Driver | Execute time, fetch time, rows fetched, bytes received |
| ORM | Số query, thời gian mapping, số đối tượng tạo ra |
| Runtime | CPU time, allocation rate, GC pause, heap usage |
| Business logic | Thời gian từng bước xử lý, số lần gọi dịch vụ phụ |
| Response | Serialization time, response bytes, compression time |
| Client | Parse time, render time, long tasks và lỗi giao diện |

Nếu API trả dữ liệu nhanh từ DB nhưng response vẫn chậm, hãy kiểm tra lượng dữ liệu, allocation, GC và serialize trước khi thay đổi execution plan.

## 5. Vì sao thời gian DB và thời gian ứng dụng khác nhau?

Giả sử một endpoint có thời gian từ lúc nhận request đến lúc gửi response là 900 ms. Instrumentation cho thấy:

| Thành phần | Thời gian |
|---|---:|
| Chờ worker ứng dụng | 80 ms |
| Chờ connection pool | 250 ms |
| DB xử lý câu lệnh | 20 ms |
| Fetch và truyền kết quả | 180 ms |
| ORM ánh xạ và nghiệp vụ | 220 ms |
| Serialize response | 90 ms |
| Phần khác và sai số đo | 60 ms |
| **Tổng** | **900 ms** |

Trong ví dụ, kế hoạch có thể cho thấy câu SQL chạy trong 20 ms. Tối ưu toán tử từ 20 ms xuống 10 ms chỉ tiết kiệm khoảng 10 ms trên tổng 900 ms. Nếu nguyên nhân chính là pool wait, cần xử lý thời gian giữ connection hoặc concurrency. Nếu nguyên nhân là mapping, cần giảm số đối tượng hoặc lượng dữ liệu.

Các mốc trong bảng là giả định để minh họa cách phân rã. Trong hệ thống thật, các giai đoạn có thể chồng lấp; không phải lúc nào cũng cộng được từng span để bằng chính xác request duration. Cần xác định span cha/con và tránh cộng hai lần thời gian lồng nhau.

## 6. Truy vết xuyên suốt một request

Để biết thời gian nằm ở đâu, cần một trace hoặc bộ log có correlation ID xuyên qua các lớp.

Một trace có thể mô tả:

```text
HTTP request
  ├─ application queue
  ├─ worker execution
  ├─ acquire DB connection
  ├─ DB client call
  │    ├─ send command
  │    ├─ DB statement
  │    └─ fetch result
  ├─ ORM mapping
  ├─ business logic
  ├─ downstream service call
  └─ response serialization
```

Mỗi span nên có thời điểm bắt đầu/kết thúc, trạng thái lỗi và các thuộc tính đủ để phân loại. Có thể dùng OpenTelemetry hoặc hệ thống tracing tương đương. Trace context cần được truyền qua các dịch vụ để các span có thể nối với nhau.

### Nguyên tắc instrument

1. Đo thời gian request ở biên ứng dụng, dùng monotonic clock cho khoảng thời gian trong cùng tiến trình.
2. Đo riêng queue wait và worker processing.
3. Đo thời gian acquire connection, thời gian giữ connection và transaction duration.
4. Đo execute và fetch theo cách driver hỗ trợ.
5. Gắn query fingerprint hoặc tên thao tác nghiệp vụ thay vì lưu toàn bộ SQL có dữ liệu nhạy cảm.
6. Ghi rows fetched và bytes received khi có thể.
7. Đo ORM mapping, business logic, downstream call và serialization.
8. Dùng trace sampling hợp lý để không tạo thêm tải quá lớn.
9. Đồng bộ đồng hồ giữa các máy khi cần đối chiếu log phân tán; ưu tiên span duration do từng tiến trình đo bằng monotonic clock.

Không đưa mật khẩu, token, thông tin cá nhân hoặc giá trị tham số nhạy cảm vào trace. Nếu cần nhận diện truy vấn, hãy chuẩn hóa câu lệnh và ẩn literal/parameter theo chính sách bảo mật của hệ thống.

## 7. Phân biệt các kiểu chờ trong DB với chờ bên ngoài DB

Kế hoạch thực thi có thể không thể hiện rõ mọi thời gian chờ. Cần kết hợp các công cụ của DB:

- Session/activity view cho biết phiên đang chạy, đang idle hoặc chờ.
- Wait events hoặc wait statistics cho biết loại tài nguyên mà phiên đang chờ, tùy hệ quản trị.
- Blocking session và lock graph giúp nhận diện giao dịch chặn.
- Query statistics cho biết số lần chạy, tổng thời gian, thời gian trung bình và số hàng.
- Connection/admission metrics cho biết giới hạn phiên hoặc hàng đợi tiếp nhận.

Phân biệt ba nhóm:

1. **DB execution work:** CPU, I/O, join, sort, aggregate và thao tác truy cập dữ liệu.
2. **DB internal wait:** lock, latch, buffer, log flush, worker hoặc tài nguyên nội bộ.
3. **External wait:** pool ứng dụng, mạng, hàng đợi worker, driver fetch, ORM và xử lý response.

Một phiên DB ở trạng thái chờ lock vẫn là thời gian trong DB, nhưng nó không phải chi phí của toán tử scan hay join. Một request đang chờ connection pool thậm chí chưa có session DB tương ứng. Cần tránh gán mọi khoảng thời gian trước hoặc trong DB call cho execution plan.

## 8. Quy trình chẩn đoán khi kế hoạch có vẻ tốt nhưng request vẫn chậm

Hãy đi theo đường đi của request, từ ngoài vào trong:

1. **Xác nhận triệu chứng.** Ghi endpoint, loại request, p50/p95/p99, timeout và thời điểm xuất hiện.
2. **Kiểm tra request queue.** Xem request có phải chờ worker hoặc thread pool trước khi bắt đầu xử lý không.
3. **Kiểm tra connection pool.** Đo pending acquire, acquire latency, active/idle connection và thời gian giữ kết nối.
4. **Đo DB call.** Phân biệt thời gian gửi lệnh, statement execution và fetch result nếu driver cho phép.
5. **Đối chiếu DB.** Xem execution plan, query statistics, rows actual/estimated, wait events, lock wait và I/O.
6. **Kiểm tra mạng.** Đo RTT, retransmission, packet loss, throughput, kết nối mới và kích thước kết quả.
7. **Đo xử lý phía ứng dụng.** Xem ORM mapping, số query, CPU, allocation, GC, business logic và serialize.
8. **So sánh request nhanh và chậm.** Dùng trace cùng endpoint, tham số đã được làm mờ và cùng loại workload để tìm giai đoạn khác biệt.
9. **Đưa ra giả thuyết có thể kiểm chứng.** Ví dụ: pool wait tăng do transaction giữ connection trong lúc gọi dịch vụ ngoài.
10. **Thay đổi một yếu tố và đo lại.** Giữ điều kiện tải, dữ liệu và cache tương đương; đo cả DB và request end-to-end.

Nếu thiếu instrumentation, hãy bổ sung phép đo nhỏ nhất có thể để phân biệt các giai đoạn. Không nên thay chỉ mục, tăng pool và đổi fetch size cùng lúc, vì khi kết quả thay đổi sẽ khó xác định yếu tố nào tạo ra khác biệt.

## 9. Ba tình huống thực tế

### Tình huống A: Kế hoạch nhanh nhưng API chậm do N+1

Một màn hình lấy 100 đơn hàng. Truy vấn chính mất 5 ms; mỗi đơn hàng tiếp tục tải thông tin khách hàng bằng một truy vấn 2 ms. Kế hoạch của từng truy vấn đều có index seek và số hàng nhỏ.

Tuy nhiên, ứng dụng thực hiện 101 lần gọi DB. Nếu các lần gọi diễn ra tuần tự và RTT là 8 ms, chi phí round trip có thể lớn hơn nhiều chi phí toán tử. Trace cho thấy số DB call cao và tổng thời gian fetch lớn.

Có thể dùng join, eager loading hoặc batch fetch để giảm số lần gọi. Sau thay đổi, kiểm tra số hàng trả về, kích thước kết quả và thời gian ORM mapping; một join quá rộng có thể thay N+1 bằng một tập kết quả phình to.

### Tình huống B: DB statement nhanh nhưng request chờ pool

Trong giờ cao điểm, DB ghi nhận statement median 12 ms và CPU còn dư. API p95 lại tăng lên 700 ms. Metric pool cho thấy tất cả kết nối đều active, pending acquire tăng và p95 acquire wait đạt 400 ms.

Trace chỉ ra một số luồng giữ connection trong transaction rồi gọi dịch vụ thanh toán bên ngoài. Thời gian gọi mạng đó không cần thiết phải nằm trong transaction DB, nhưng connection vẫn bị giữ.

Có thể rút ngắn transaction, lấy dữ liệu cần thiết rồi đóng transaction trước khi gọi dịch vụ ngoài, hoặc điều chỉnh concurrency sau khi xác nhận năng lực DB. Phải giữ đúng quy tắc nghiệp vụ và xử lý lỗi giữa các bước; không được tách transaction tùy tiện nếu cần tính nguyên tử.

### Tình huống C: DB trả kết quả lớn, ứng dụng xử lý chậm

Một truy vấn báo cáo dùng index scan và aggregate hợp lý, nhưng trả về 250.000 hàng. DB statement hoàn tất trong 300 ms, trong khi fetch kéo dài 1,8 giây, ORM mapping thêm 900 ms và serialize JSON thêm 600 ms.

Kế hoạch không cho thấy đầy đủ kích thước byte truyền, số lần fetch, tốc độ parse và chi phí tạo đối tượng. Có thể cần phân trang, lọc cột, tổng hợp ở DB, xuất file theo luồng hoặc chuyển báo cáo sang tác vụ nền.

Khi thay đổi, đo thời gian đến hàng đầu tiên, thời gian đến hàng cuối, peak memory, GC pause, bytes transmitted và thời gian serialize. Nếu nghiệp vụ cần toàn bộ dữ liệu, streaming có thể giảm bộ nhớ đỉnh nhưng phải quản lý cursor và connection cẩn thận.

## 10. Thiết kế phép đo và so sánh trước/sau

Một phép đo tốt cần trả lời cùng lúc hai câu hỏi: DB có làm ít công việc hơn không, và người dùng có nhận phản hồi nhanh hơn không?

| Nhóm | Chỉ số trước/sau |
|---|---|
| Request | p50, p95, p99, throughput, error/timeout rate |
| Hàng đợi ứng dụng | Queue depth, queue wait, worker utilization |
| Connection pool | Active/idle, pending acquire, acquire latency, connection hold time |
| DB | Statement elapsed, query count, rows, CPU, I/O, wait events, lock wait |
| Mạng | RTT, bytes, throughput, retransmits, packet drops |
| Driver/fetch | Execute time, fetch time, fetch count, rows/bytes received |
| Ứng dụng | ORM mapping, business processing, CPU, allocation, GC, serialization |
| Tính đúng đắn | Kết quả dữ liệu, thứ tự, phân trang, transaction semantics và lỗi |

Giữ cùng một workload hoặc một mẫu đại diện có thể lặp lại. Nếu số người dùng, dữ liệu, cache hoặc độ trễ mạng thay đổi giữa hai lần đo, kết quả có thể không phản ánh tác động của thay đổi SQL.

Nên xem phân vị thay vì chỉ trung bình. Một connection pool có thể có thời gian chờ trung bình thấp nhưng một nhóm request phải chờ rất lâu. Một truy vấn có thời gian DB trung bình tốt nhưng một số tham số chọn tập dữ liệu lớn hơn nhiều. Phân tích theo query fingerprint và loại request giúp tránh che khuất các trường hợp này.

## 11. Cách chọn nơi tối ưu

| Bằng chứng | Lớp nên điều tra trước | Hướng xử lý có thể thử |
|---|---|---|
| DB statement chậm, actual rows lớn hoặc plan không hợp lý | SQL, thống kê và DB | Sửa SQL, cập nhật thống kê, chỉ mục phù hợp |
| DB statement nhanh nhưng pool acquire chậm | Ứng dụng và pool | Rút ngắn thời gian giữ connection, kiểm tra transaction, điều tiết concurrency |
| Nhiều query nhỏ và RTT cao | Giao tiếp app-DB | Batch, join, eager loading, giảm round trip |
| Fetch time cao, rows/bytes lớn | Kết quả và mạng | Lọc cột/hàng, phân trang, cursor hoặc streaming |
| DB xong nhanh nhưng ORM mapping chậm | Tầng ứng dụng | Projection/DTO, giảm object graph, tránh lazy loading |
| Serialize hoặc render chậm | API/client | Giảm payload, phân trang, nén phù hợp, xử lý bất đồng bộ |
| Wait event/lock wait cao | Cơ chế giao dịch DB | Rút ngắn transaction, giảm tranh chấp, điều chỉnh thứ tự khóa |
| Request queue cao nhưng DB còn rảnh | Worker/app admission | Điều chỉnh worker, queue và giới hạn nhận tải |

Không nên tối ưu tầng đang có metric dễ nhìn nhất. Hãy ưu tiên thành phần chiếm phần lớn thời gian hoặc tạo ra đuôi độ trễ, đồng thời đánh giá tác động đến các tầng còn lại.

## 12. Checklist khi execution plan không giải thích được độ trễ

- [ ] Thời gian đo ở ứng dụng và DB đã được định nghĩa rõ điểm bắt đầu/kết thúc chưa?
- [ ] Request có phải chờ worker hoặc hàng đợi ứng dụng không?
- [ ] Connection pool có pending acquire hoặc thời gian chờ cao không?
- [ ] Một request thực hiện bao nhiêu DB call và có mẫu N+1 không?
- [ ] RTT, retransmission, packet loss và kết nối mới có thay đổi không?
- [ ] Kết quả có quá nhiều hàng hoặc byte không?
- [ ] Driver có tốn thời gian fetch, decode hoặc chuyển kiểu dữ liệu không?
- [ ] ORM có tạo quá nhiều đối tượng hoặc lazy-load quan hệ không?
- [ ] CPU, allocation, GC và serialization ở ứng dụng có tăng không?
- [ ] DB có wait event, lock wait hoặc queue nội bộ mà plan không thể hiện rõ không?
- [ ] Các span có cùng correlation ID và timestamp đáng tin cậy không?
- [ ] Đã đo lại request end-to-end sau khi tối ưu và kiểm tra tính đúng đắn chưa?

## 13. Nguyên tắc ra quyết định

Execution plan giúp hiểu công việc bên trong DB, nhưng hiệu năng người dùng cảm nhận là kết quả của toàn bộ đường đi từ lúc nhận request đến lúc trả response. Mạng có thể làm tăng chi phí round trip và truyền dữ liệu; hàng đợi có thể khiến yêu cầu chờ trước khi DB bắt đầu; driver, ORM và ứng dụng có thể tiêu tốn thêm thời gian sau khi DB hoàn tất.

Khi kế hoạch có vẻ tốt mà request vẫn chậm, hãy phân rã thời gian theo từng giai đoạn và nối các phép đo bằng trace hoặc correlation ID. Đối chiếu số liệu ứng dụng, connection pool, DB, mạng và hệ điều hành trong cùng khoảng thời gian. Chỉ khi xác định được phần chi phí chiếm ưu thế, nhóm phát triển mới chọn được thay đổi phù hợp.

Sau điều chỉnh, xác minh cả thời gian phản hồi, thông lượng, hàng đợi, số DB call, kích thước kết quả và tài nguyên tiêu thụ. Một tối ưu có ý nghĩa khi cải thiện trải nghiệm end-to-end, duy trì tính đúng đắn dữ liệu và không đẩy nút thắt sang một lớp khác.
