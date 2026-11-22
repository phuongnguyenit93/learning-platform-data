# Dự đoán tải đột biến, dữ liệu lệch và nhu cầu mở rộng

Một hệ thống NoSQL có thể chạy rất nhanh khi thử nghiệm với vài nghìn document, nhưng chậm bất thường khi mở bán sản phẩm, nhập dữ liệu hàng loạt, có một khách hàng lớn mới hoặc xuất hiện một bản ghi được truy cập liên tục. Nguyên nhân không nhất thiết là **tổng số bản ghi đã quá lớn**. Điểm nghẽn có thể nằm ở **thời điểm truy cập**, **phân bố khóa dữ liệu**, **kiểu truy vấn**, **khả năng nhận tải của một partition** hoặc **cách ứng dụng xử lý yêu cầu vượt năng lực hiện tại**.

Để dự đoán nhu cầu mở rộng, cần trả lời ba câu hỏi liên kết với nhau:

1. **Tải sẽ biến đổi như thế nào theo thời gian?** Trung bình, đỉnh ngắn, đỉnh kéo dài, tốc độ tăng trưởng và tải nền khác nhau ra sao?
2. **Tải và dữ liệu sẽ tập trung vào đâu?** Một tenant, người dùng, sản phẩm, khóa phân vùng hay khoảng thời gian có thể chiếm phần lớn truy cập không?
3. **Khi vượt năng lực hiện có, hệ thống sẽ làm gì?** Thành phần nào cần mở rộng, công việc nào cần giới hạn hoặc chuyển vào hàng đợi, và mức trễ hay mức mất sẵn sàng nào được chấp nhận?

Trong bài học này, **dữ liệu lệch (data skew)** bao gồm cả phân bố dung lượng không đều và **phân bố truy cập không đều (access skew)**. Ví dụ sử dụng mô hình document và partition/shard phổ biến trong NoSQL. Cơ chế cụ thể khác nhau giữa MongoDB, DynamoDB, Cassandra, Redis và các hệ quản trị khác; không nên áp dụng nguyên xi chính sách partition, transaction, consistency hoặc autoscaling từ một sản phẩm sang sản phẩm khác.

## 1. Vì sao tải trung bình thường đánh lừa người thiết kế?

Giả sử một dịch vụ ghi nhận **8.640.000 yêu cầu API mỗi ngày**.

Tải trung bình theo ngày là:

\[
\frac{8.640.000}{24 \times 60 \times 60} = 100\ \text{request/giây}
\]

Nếu thiết kế chỉ dựa vào 100 request/giây, một giờ cao điểm với hệ số tải gấp 15 lần có thể khiến hệ thống quá tải dù lượng truy cập cả ngày vẫn như dự tính.

Trong cùng một ngày có thể tồn tại nhiều hình dạng tải:

| Hình dạng tải | Ví dụ | Hệ quả thiết kế |
|---|---|---|
| **Ổn định (steady)** | Lưu lượng tương đối đồng đều | Dễ đo và cấp phát tài nguyên |
| **Chu kỳ (periodic)** | Giờ hành chính, cuối tuần, đợt chốt sổ | Có thể dự báo trước hoặc chuẩn bị năng lực theo lịch |
| **Đột biến (burst/spike)** | Flash sale, thông báo push, người dùng cùng đăng nhập | Đỉnh ngắn có thể vượt khả năng nhận yêu cầu tức thời |
| **Tăng dần (ramp)** | Từ 100 lên 1.000 request/giây trong 30 phút | Cho cơ chế mở rộng thời gian phản ứng |
| **Tải kéo dài (sustained)** | Đợt quảng bá kéo dài nhiều giờ | Hàng đợi không thể giải quyết nếu tốc độ đến luôn lớn hơn tốc độ xử lý |
| **Tải nền (background)** | Backfill, đồng bộ, batch, tạo index, backup | Cạnh tranh CPU, I/O, bộ nhớ và băng thông với tải người dùng |
| **Tải lệch (skewed)** | Một tenant hoặc một SKU nhận 40% truy cập | Một vài partition/khóa nóng trong khi tài nguyên khác còn rảnh |

Dự đoán tốt cần nhìn ít nhất **theo ngày, giờ, phút và giây**, tùy thời gian phản ứng mà dịch vụ yêu cầu. Biểu đồ trung bình theo giờ có thể che khuất một đỉnh 5 giây đủ làm cạn connection pool hoặc khiến số yêu cầu chờ tăng nhanh.

### Đỉnh ngắn và đỉnh kéo dài khác nhau

Một đợt **2.000 request/giây trong 10 giây** tạo ra 20.000 yêu cầu. Nếu hệ thống xử lý được 1.000 request/giây, phần vượt tạm thời khoảng 10.000 yêu cầu; có thể cần bộ đệm hoặc từ chối có kiểm soát.

Ngược lại, **2.000 request/giây trong 30 phút** tương ứng 3,6 triệu yêu cầu. Nếu năng lực xử lý chỉ là 1.000 request/giây, số yêu cầu chưa xử lý có thể tiếp tục tăng thêm 1,8 triệu trong thời gian đó. Không thể dựa vào một hàng đợi nhỏ để “chờ qua đỉnh” nếu thiếu năng lực xử lý bền vững và giới hạn chờ hợp lý.

## 2. Đọc đúng các chiều của tải NoSQL

“Có 1.000 request/giây” chưa đủ để ước lượng năng lực database. Một request có thể trúng cache và không truy cập DB; request khác có thể thực hiện nhiều lần đọc, ghi, cập nhật index và truy vấn aggregation.

| Chiều đo | Cần biết điều gì? | Vì sao quan trọng? |
|---|---|---|
| **API RPS/TPS** | Yêu cầu đến mỗi giây, phân theo endpoint | Mô tả áp lực ở tầng ứng dụng |
| **DB operations/s** | Số lần đọc, ghi, update, query mỗi giây | Gần sát tải thật lên storage |
| **Kiểu thao tác** | Point lookup, range scan, aggregate, bulk write, transaction | Chi phí mỗi thao tác rất khác nhau |
| **Kích thước dữ liệu** | Document trung bình, p95/p99, kết quả trả về, index | Ảnh hưởng I/O, băng thông, cache và dung lượng |
| **Phân bố khóa** | Request theo tenant, sản phẩm, partition key | Phát hiện hot key/hot partition |
| **Độ mới yêu cầu** | Có cho phép cache hoặc đọc bản sao trễ không? | Quyết định cách giảm tải đọc |
| **Mục tiêu độ trễ** | p95/p99 và tỉ lệ lỗi của thao tác quan trọng | Định nghĩa “đủ năng lực” từ góc nhìn người dùng |
| **Tốc độ tăng dữ liệu** | Tài liệu/ngày, retention, TTL, cập nhật và xóa | Dự báo lưu trữ, index và vận hành |
| **Tải phụ trợ** | Import, replication, snapshot, restore, index build | Tránh dự báo chỉ dựa vào traffic chính |

Cần phân biệt **API RPS**, **thao tác DB/giây** và **đơn vị capacity có tính theo kích thước** mà từng dịch vụ quản lý cung cấp. Một thao tác đọc document lớn hoặc đọc với mức nhất quán khác có thể tiêu tốn tài nguyên khác với một point read nhỏ. Không có hệ số quy đổi chung cho mọi NoSQL.

## 3. Một ví dụ tính tải từ yêu cầu nghiệp vụ

Giả sử có dịch vụ đơn hàng với các giả định:

- 8.640.000 API request/ngày, trung bình **100 request/giây**.
- Đỉnh dự kiến bằng **15 lần trung bình**, tức **1.500 request/giây**.
- Trong đỉnh, **80% request là đọc**, **20% là ghi**.
- Trung bình mỗi request đọc tạo **1,4 thao tác đọc DB**; mỗi request ghi tạo **2 thao tác ghi DB**.
- Tạm thời chưa tính cache, retry, batch, transaction và công việc nền.

Ta có:

\[
R_{\text{read}}=1.500 \times 0{,}8 \times 1{,}4
=1.680\ \text{DB read ops/s}
\]

\[
R_{\text{write}}=1.500 \times 0{,}2 \times 2
=600\ \text{DB write ops/s}
\]

Như vậy **1.500 API RPS** có thể tạo ra **2.280 thao tác DB/giây** trong mô hình giả định này. Hai con số không phải cùng đơn vị năng lực: chi phí đọc và ghi, kích thước document, index và mức consistency vẫn phải được xem xét riêng.

Nếu thêm retry, một request lỗi có thể được thực hiện lần nữa. Với các thao tác ghi, retry thiếu **idempotency** có thể gây tạo đơn hoặc thanh toán lặp. Do đó, không nên đơn thuần nhân hệ số retry vào ước lượng tải rồi bỏ qua **tính đúng đắn của nghiệp vụ**.

### Chương trình nhỏ để thay đổi giả định

Ví dụ Python sau tính toán cơ bản; các con số là giả định phục vụ bài học, không phải phép đo của một cụm NoSQL thực tế.

~~~python
requests_per_day = 8_640_000
peak_multiplier = 15

read_fraction = 0.80
db_reads_per_read_request = 1.4
db_writes_per_write_request = 2.0

average_api_rps = requests_per_day / 86_400
peak_api_rps = average_api_rps * peak_multiplier

read_api_rps = peak_api_rps * read_fraction
write_api_rps = peak_api_rps * (1 - read_fraction)

db_read_ops = read_api_rps * db_reads_per_read_request
db_write_ops = write_api_rps * db_writes_per_write_request

print(f"Average API RPS: {average_api_rps:,.0f}")
print(f"Peak API RPS: {peak_api_rps:,.0f}")
print(f"DB read ops/s: {db_read_ops:,.0f}")
print(f"DB write ops/s: {db_write_ops:,.0f}")
~~~

Khi dùng mô hình này cho hệ thống thật, hãy đo số operation thực tế theo endpoint, query shape và kích thước dữ liệu. Tỷ lệ cache hit, read amplification, write amplification và tác vụ nền có thể làm kết quả khác đáng kể.

## 4. Dự đoán tải đột biến từ đâu?

Có hai nhóm tín hiệu: **sự kiện có lịch** và **dấu hiệu quan sát được trong hệ thống**.

### 4.1. Tải theo sự kiện nghiệp vụ

Cần trao đổi với nhóm sản phẩm và vận hành về:

- Thời điểm mở bán, khởi động chiến dịch, phát mã giảm giá hoặc gửi push notification hàng loạt.
- Hạn chót đăng ký, ngày chốt báo cáo, lịch tính cước, đồng bộ theo giờ.
- Sự kiện bên ngoài như livestream, đối tác lớn tích hợp hoặc chương trình tuyển sinh.
- Số tài khoản, cửa hàng hoặc thiết bị dự kiến kích hoạt cùng một lúc.
- Job nội bộ chạy sau triển khai, phục hồi dữ liệu hoặc nhập lần đầu.

Ví dụ, nếu **60.000 thiết bị** được lên lịch gửi heartbeat **trong đúng một phút**, tải do heartbeat gần **1.000 event/giây**, chưa tính retry. Nếu mỗi thiết bị tự gửi đồng loạt tại phút chẵn, tải thực tế có thể tập trung mạnh trong vài giây đầu. Thêm **jitter** cho lịch gửi có thể làm phẳng đỉnh nếu nghiệp vụ chấp nhận được độ phân tán thời gian.

### 4.2. Tải theo lịch sử đo đạc

Từ chuỗi thời gian của request và DB operation, phân tích:

1. Tải trung bình trong các cửa sổ thời gian đủ nhỏ.
2. Đỉnh cực đại trong các cửa sổ 1 giây, 10 giây, 1 phút và 15 phút phù hợp với hệ thống.
3. Tỷ lệ `peak / average` và thời gian duy trì đỉnh.
4. Mức tăng theo tuần/tháng và các ngày có sự kiện.
5. Các mối liên hệ với thao tác nghiệp vụ: mở bán, batch, import, deploy.
6. Độ trễ, lỗi và throttling xuất hiện trước, trong và sau đỉnh.

Dữ liệu lịch sử là nền tảng nhưng **không thể tự dự báo một sự kiện chưa từng xảy ra**. Cần đặt thêm kịch bản dựa trên kế hoạch sản phẩm và giả định tăng trưởng.

### 4.3. Kịch bản thay vì một dự báo duy nhất

| Kịch bản | Giả định mô phỏng | Câu hỏi cần trả lời |
|---|---|---|
| Bình thường | Tải dự kiến với mix đọc/ghi hiện tại | Có đạt SLO và chi phí mục tiêu? |
| Cao điểm đã biết | Giờ cao điểm hoặc sự kiện theo lịch | Năng lực có được chuẩn bị đủ sớm? |
| Burst bất ngờ | Tăng nhanh trong vài giây | Admission control, cache và hàng đợi phản ứng ra sao? |
| Tăng trưởng dài hạn | Khách hàng/dữ liệu tăng qua nhiều tháng | Có cần thêm partition, index, dung lượng hoặc thay mô hình lưu trữ? |
| Tải lệch | Một khóa/tenant chiếm phần lớn request | Có quá tải trên partition riêng lẻ không? |
| Mất một thành phần | Node/availability zone/replica gặp lỗi | Cụm còn lại có đủ năng lực duy trì mục tiêu dịch vụ? |

Nên ghi rõ giả định và nguồn của mỗi kịch bản: số liệu đo, lịch công bố sản phẩm hay phỏng đoán kỹ thuật. Đừng thể hiện một dự báo tự suy đoán như con số chắc chắn.

## 5. Dữ liệu lệch (data skew) là gì?

Một tập dữ liệu lớn không nhất thiết nguy hiểm bằng một tập dữ liệu phân bố sai so với cách chia tải của hệ thống.

**Storage skew** là khi một số partition giữ nhiều byte hoặc nhiều document hơn hẳn phần còn lại. **Access skew** là khi một số khóa/partition nhận phần lớn truy vấn hoặc cập nhật. Hai loại skew có thể xảy ra độc lập.

Ví dụ:

- 100.000 sản phẩm có kích thước gần bằng nhau, nhưng một sản phẩm đang nổi tiếng nhận 40% lượt xem: **access skew**.
- Một tenant lưu 70% dữ liệu toàn cụm dù số request của tenant đó không cao: **storage skew**.
- Event có khóa phân vùng chỉ là ngày hiện tại: tất cả event của hôm nay có thể dồn vào một vùng khóa: **write skew**.
- Một nhóm người dùng có profile chứa mảng lịch sử kéo dài nhiều năm: **document-size skew**.

### Trường hợp nhiều tenant nhưng một tenant rất lớn

Giả sử dịch vụ nhận 1.500 request/giây và có 100 tenant đang hoạt động. Nếu chia đều, mỗi tenant chỉ có 15 request/giây. Nhưng nếu tenant lớn nhất chiếm **40%**, tenant đó tạo:

\[
1.500 \times 0{,}4 = 600\ \text{request/giây}
\]

99 tenant còn lại cùng chia 900 request/giây. Thống kê “100 tenant, trung bình 15 request/giây/tenant” che khuất một tenant có lượng truy cập gấp **40 lần mức trung bình**.

Đây là lý do capacity tổng của cluster có thể còn dư, nhưng yêu cầu của một tenant vẫn bị throttling hoặc tăng latency.

### Hot key, hot document và hot partition khác nhau thế nào?

- **Hot key:** một khóa logic được truy cập quá thường xuyên.
- **Hot document/item:** một bản ghi cụ thể bị đọc/ghi tập trung.
- **Hot partition/shard:** đơn vị phân bố vật lý nhận quá nhiều công việc hoặc dữ liệu.

Một hot document có thể trở thành nút thắt ở nơi chứa nó. Tuy nhiên, không phải mọi hot key luôn dẫn đến cùng một kiểu hot partition: còn phụ thuộc hệ quản trị, cache, replication, bộ điều phối request và cách ánh xạ khóa. Ngược lại, nhiều khóa khác nhau vẫn có thể cùng dồn vào một partition nóng.

**Không nên chỉ nhìn tổng CPU của cluster.** Mức CPU trung bình 40% hoàn toàn có thể đi kèm một node hoặc partition quá tải.

## 6. Nhận diện dữ liệu lệch bằng phân bố và chỉ số tập trung

Khi phân tích tải, nên xem **phân vị và nhóm đóng góp lớn** thay vì chỉ đếm số khóa.

Một bảng thống kê hữu ích:

| Nhóm | Số request trong 5 phút | Tỷ trọng |
|---|---:|---:|
| Tenant A | 180.000 | 40% |
| Tenant B | 90.000 | 20% |
| Tenant C | 45.000 | 10% |
| Các tenant còn lại | 135.000 | 30% |
| **Tổng** | **450.000** | **100%** |

Lưu lượng trung bình trong 5 phút là `450.000 / 300 = 1.500` request/giây. Nhưng ba tenant đầu đã chiếm **70%**.

Các phép nhìn thường hữu ích gồm:

- **Top-K:** 10 khóa/tenant/query shape nào tốn nhiều tài nguyên nhất?
- **Tỷ trọng top 1/top 10:** bao nhiêu phần trăm tổng read/write thuộc về nhóm nóng?
- **Phân phối p50/p95/p99 theo khóa hoặc partition:** một số partition lệch xa phần lớn còn lại không?
- **Kích thước partition:** document count, bytes và tốc độ tăng trưởng.
- **Khả năng phân biệt key (cardinality):** có đủ nhiều giá trị đang hoạt động để chia tải không?
- **Tốc độ thay đổi điểm nóng:** khóa nóng cố định trong nhiều giờ hay chuyển theo sự kiện?

Chỉ báo nên được gộp theo nhãn có kiểm soát. Gắn trực tiếp mọi `userId` hoặc `productId` làm label trong hệ thống metrics có thể tạo **độ lớn nhãn (metric cardinality)** rất cao và làm tốn tài nguyên giám sát. Với khóa cụ thể, dùng log mẫu, trace, thống kê top-K hoặc công cụ profiling có giới hạn.

## 7. Partition key quyết định khả năng phân tán tải

NoSQL phân tán thường dùng một dạng **partition key/shard key** để quyết định nơi đặt dữ liệu. Lựa chọn này liên hệ trực tiếp với khả năng mở rộng.

Ví dụ bảng sự kiện có các trường:

~~~json
{
  "eventId": "evt-00042",
  "tenantId": "tenant-A",
  "deviceId": "device-51",
  "createdAt": "2026-11-14T07:00:00Z",
  "kind": "heartbeat",
  "payload": { "batteryPercent": 86 }
}
~~~

Các ứng viên khóa có ưu, nhược điểm:

| Khóa phân chia giả định | Điểm thuận lợi | Rủi ro cần xem xét |
|---|---|---|
| `tenantId` | Tập trung dữ liệu mỗi tenant, truy vấn theo tenant thuận tiện | Tenant rất lớn có thể tạo hotspot |
| `deviceId` | Có thể phân bố khi nhiều thiết bị hoạt động | Truy vấn toàn tenant có thể phải đọc nhiều partition; một device quá nóng vẫn lệch |
| `createdAt` đơn thuần | Truy vấn theo thời gian có thể tự nhiên theo thứ tự khóa | Nếu phân vùng theo dải khóa, ghi mới có thể dồn về dải thời gian mới nhất |
| `tenantId + bucket` | Chia một tenant lớn thành nhiều đơn vị | Phải định nghĩa cách chọn bucket, tìm kiếm và tổng hợp kết quả |
| Hash của khóa phù hợp | Phân tán các giá trị khóa khác nhau | **Không** tự chia được nhiều thao tác cùng nhắm vào đúng một khóa |

Không thể suy ra một khóa “tốt nhất” chỉ từ bảng này. Cần xem **query access pattern**, cơ chế partition cụ thể của database, giới hạn per-partition, kích thước dữ liệu và yêu cầu truy vấn.

### Hash không chữa được một khóa nóng duy nhất

Giả sử mọi request đều cập nhật document:

~~~json
{ "_id": "stock:SKU-42", "available": 1250 }
~~~

Băm `"stock:SKU-42"` luôn cho cùng giá trị băm. Phân phối tốt giữa **nhiều khóa khác nhau** không làm một khóa duy nhất trở thành nhiều khóa. Nếu 500 request/giây cùng cập nhật document đó, nút thắt có thể nằm ở chính quá trình cập nhật một bản ghi.

Với MongoDB, ví dụ cập nhật số lượng tồn kho có điều kiện:

~~~javascript
db.stock.updateOne(
  { _id: "stock:SKU-42", available: { $gte: 1 } },
  { $inc: { available: -1 } }
);
~~~

Thao tác này kiểm tra điều kiện và cập nhật nguyên tử đối với **một document**. Nó tránh một kiểu race condition khi trừ tồn kho, nhưng không tự giải quyết khả năng chịu tải của document nóng, xử lý một request đã được thực hiện nhưng client timeout, hoặc tính nhất quán của nhiều document liên quan. Các vấn đề này cần chiến lược riêng, chẳng hạn idempotency và transaction phù hợp với hệ quản trị.

### Khi nào cân nhắc phân bucket?

Một bộ đếm lượt xem có thể được phân thành nhiều bucket, ví dụ `views:SKU-42:0` tới `views:SKU-42:15`. Các lần tăng được phân bổ giữa bucket; phép đọc cộng lại để nhận tổng.

Đánh đổi:

- Việc tăng thường phân tán hơn nếu các bucket được chọn và đặt phù hợp.
- Việc đọc tổng tốn thêm thao tác hoặc cần giá trị tổng hợp đã tính sẵn.
- Tăng số bucket ảnh hưởng chi phí lưu trữ, index và vận hành.
- Dữ liệu vừa ghi có thể chưa xuất hiện ngay trong bản tổng hợp nếu xử lý bất đồng bộ.

Điều này thường phù hợp với **counter hoặc analytics có quy tắc trễ được chấp nhận**. Với tồn kho, số dư hoặc trạng thái phải đảm bảo bất biến mạnh, không thể chia tùy ý mà không thiết kế lại cơ chế đặt chỗ và đối soát.

## 8. Đọc nhiều và ghi nhiều cần cách xử lý khác nhau

Một hệ thống “nóng” có thể nóng ở hai phía.

### Tải đọc lớn

Ví dụ một bài viết trở nên phổ biến và được xem 10.000 lần trong một phút. Nếu dữ liệu ít thay đổi và ứng dụng chấp nhận độ trễ cập nhật, cache có thể giảm đáng kể tải đọc đến NoSQL.

Các kỹ thuật:

- **Cache theo khóa** với TTL phù hợp, tránh mỗi lượt xem đều truy vấn document.
- **CDN hoặc edge caching** cho nội dung công khai có thể cache.
- **Precompute/materialized view** cho báo cáo hoặc nội dung tổng hợp tốn nhiều phép đọc.
- **Request coalescing/single-flight** để nhiều request đồng thời cho cùng một khóa chỉ kích hoạt một lần tải nguồn.
- **Jitter cho TTL** nhằm giảm nhiều cache entry hết hạn cùng thời điểm.

Nhưng cache tạo thêm câu hỏi: dữ liệu được phép cũ bao lâu, cập nhật cache thế nào, invalidation ra sao, và điều gì xảy ra nếu cache hỏng hoặc bị xóa sạch?

**Cache stampede** xuất hiện khi hàng nghìn request cùng thấy cache miss và đồng loạt truy vấn DB. Do đó, tỷ lệ cache hit cao trong điều kiện bình thường không bảo đảm an toàn khi có cold start hoặc hết hạn hàng loạt.

### Tải ghi lớn

Ghi thường kéo theo nhiều chi phí hơn một lệnh chèn dữ liệu:

- Ghi dữ liệu chính, ghi index và log/journal theo cơ chế của DB.
- Phân phối dữ liệu sang replica hoặc vùng khác, tùy cấu hình.
- Kiểm tra điều kiện cập nhật, xung đột ghi và transaction.
- Đồng bộ sự kiện, change stream, materialized view hoặc hệ thống tìm kiếm.

Với event, telemetry hoặc dữ liệu ghi hàng loạt, các lựa chọn có thể gồm **batch write**, tách luồng ghi thành các phân vùng thích hợp, hàng đợi có giới hạn, chính sách retention/TTL và xử lý bất đồng bộ nếu nghiệp vụ cho phép.

Với cập nhật cùng một item mang ý nghĩa nghiệp vụ mạnh, cần xem xét **điều phối theo khóa**, **optimistic concurrency**, **conditional write** hoặc **transaction**, thay vì tăng số luồng ghi vô hạn.

## 9. Dự báo dung lượng lưu trữ và tốc độ tăng trưởng

Tăng trưởng không chỉ là request/giây. Một cụm vẫn phục vụ truy vấn nhanh nhưng có thể bị thiếu dung lượng hoặc tăng thời gian backup/restore khi dữ liệu tích lũy.

Giả sử ứng dụng lưu **500.000 document mới mỗi ngày**, kích thước trung bình **2 KiB/document** và giữ dữ liệu 30 ngày.

Ước lượng phần dữ liệu thô:

\[
500.000 \times 2\ \text{KiB/ngày}
\approx 0{,}95\ \text{GiB/ngày}
\]

\[
0{,}95 \times 30 \approx 28{,}6\ \text{GiB}
\]

Nếu giữ **3 bản sao vật lý** trong một mô hình replication giả định, dung lượng thô cộng gộp có thể gần **85,8 GiB** trước khi xét index, metadata, log, phân bổ trống, nén, backup và các yếu tố của database cụ thể.

Các yếu tố phải đo riêng:

| Yếu tố | Tác động |
|---|---|
| **Index** | Tăng dung lượng và chi phí ghi, đôi khi rất đáng kể |
| **Replication** | Cần thêm tài nguyên lưu trữ và băng thông, tùy cấu hình |
| **Compression** | Có thể giảm số byte lưu thực tế, phụ thuộc nội dung dữ liệu |
| **Update và xóa** | Có thể tạo chi phí log, compaction hoặc phân mảnh trước khi dung lượng được thu hồi |
| **TTL/retention** | Giới hạn dữ liệu giữ lâu dài nhưng việc xóa cũng tiêu thụ tài nguyên |
| **Backup/snapshot** | Cần xét thời gian, vùng chứa, chi phí và khả năng khôi phục |
| **Bản ghi bất thường** | Một số document rất lớn có thể làm lệch trung bình và tăng tải bộ nhớ/network |

Khi tính nhu cầu mở rộng, đừng chỉ so kích thước dữ liệu thô với dung lượng đĩa. Cần tính **working set**: dữ liệu và index được truy cập thường xuyên có phù hợp với bộ nhớ/cache không, và khi working set vượt cache thì lượng I/O thay đổi thế nào.

## 10. Ước lượng năng lực xử lý và độ trễ

Một hệ thống “đủ capacity” không chỉ trả lời được số lượng request; nó phải đáp ứng mục tiêu trễ và độ tin cậy.

Ví dụ yêu cầu dịch vụ:

- p95 của API đọc nhỏ hơn 200 ms.
- p99 của thao tác ghi nhỏ hơn 500 ms.
- Tỷ lệ lỗi dưới ngưỡng được thống nhất trong cửa sổ đo.
- Không mất event đã xác nhận thành công.
- Khi quá tải, phản hồi rõ ràng thay vì khiến request treo vô hạn.

Các con số ở đây **chỉ minh họa cách viết SLO**; mục tiêu cụ thể phải xuất phát từ nghiệp vụ và kết quả đo.

### Quan hệ giữa lưu lượng, thời gian và số tác vụ đang xử lý

Định luật Little cho hệ thống ổn định ở trạng thái phù hợp:

\[
L = \lambda \times W
\]

Trong đó:

- `L` là số tác vụ trung bình trong hệ thống.
- `\lambda` là tốc độ hoàn thành/đến trung bình trong trạng thái ổn định.
- `W` là thời gian trung bình một tác vụ ở trong hệ thống.

Với 1.500 request/giây và thời gian xử lý trung bình 80 ms:

\[
L = 1.500 \times 0{,}08 = 120
\]

Tức khoảng **120 request đang xử lý trung bình**, nếu giả định ổn định thỏa điều kiện của công thức. Đây không phải số connection cần cấp cố định và cũng không phải p99. Thời gian chờ hàng đợi, nhiều round-trip đến DB, pool connection và độ trễ đuôi có thể làm số request đồng thời tăng mạnh.

Khi tốc độ yêu cầu đến vượt tốc độ xử lý bền vững, hàng đợi tăng theo thời gian. Lúc đó dùng một giá trị latency trung bình quá khứ để dự báo theo công thức ổn định sẽ không phản ánh đúng tình trạng đang tích lũy backlog.

## 11. Hàng đợi giúp hấp thụ burst đến mức nào?

Hàng đợi là một **công cụ tách thời điểm nhận việc và xử lý việc**, không tạo thêm throughput cho database.

Giả sử:

- Producer đưa vào **800 event/giây**.
- Consumer cùng DB xử lý an toàn **500 event/giây**.
- Đỉnh kéo dài **60 giây**.

Số event tồn đọng tăng xấp xỉ:

\[
(800 - 500) \times 60 = 18.000\ \text{event}
\]

Sau đỉnh, nếu tốc độ đến giảm còn **300 event/giây**, trong khi consumer vẫn xử lý 500 event/giây, tốc độ dọn tồn đọng còn 200 event/giây. Sẽ cần khoảng:

\[
18.000 / 200 = 90\ \text{giây}
\]

để xử lý hết backlog **trong mô hình đơn giản**, chưa tính retry, message lỗi và độ trễ khác.

Bởi vậy cần thiết kế:

- **Giới hạn độ dài hàng đợi, tuổi event và thời gian xử lý cuối cùng**.
- **Backpressure** khi producer đến nhanh hơn năng lực chấp nhận.
- **Retry có giới hạn, exponential backoff và jitter**.
- **Idempotency** cho consumer có thể nhận event lặp.
- **Dead-letter queue hoặc vùng cách ly** cho message lỗi không thể xử lý sau chính sách retry.
- **Chính sách ưu tiên** để công việc quan trọng không bị chặn bởi batch ít quan trọng.

Không nên chuyển một thao tác cần phản hồi thành công tức thời sang hàng đợi mà vẫn trả lời như thể dữ liệu đã được xử lý xong. Cần phân biệt rõ trạng thái **accepted** và **completed** trong API và trải nghiệm người dùng.

## 12. Mở rộng hệ thống: thêm tài nguyên ở đâu?

Trong NoSQL phân tán, có nhiều hướng mở rộng khác nhau, mỗi hướng giải quyết một loại nút thắt.

| Cách mở rộng | Có thể giúp khi | Không tự giải quyết |
|---|---|---|
| **Vertical scaling** (CPU/RAM/I/O lớn hơn) | Node thiếu năng lực tính toán, bộ nhớ hoặc I/O | Giới hạn phần mềm và hotspot logic vẫn còn |
| **Horizontal scaling** (nhiều node/partition) | Dữ liệu, khóa và công việc phân tán tốt | Một khóa nóng, truy vấn kém hoặc thao tác ghi tuần tự trên cùng document |
| **Read replicas / cache** | Tải đọc đủ điều kiện phân tán hoặc cache | Tải ghi trên điểm ghi chính; ràng buộc nhất quán chặt |
| **Shard/partition redesign** | Skew đến từ phân bố khóa không phù hợp | Business invariant cần cập nhật nguyên tử một tài nguyên logic |
| **Tối ưu query và index** | Mỗi request tốn quá nhiều I/O/CPU | Lưu lượng tăng vô hạn hoặc khối lượng thao tác nghiệp vụ vốn cần thiết |
| **Batch và xử lý bất đồng bộ** | Công việc cho phép trì hoãn, gộp hoặc sắp lịch | Năng lực xử lý bền vững thấp hơn tải đến kéo dài |
| **Giới hạn tải/prioritization** | Cần bảo vệ dịch vụ khỏi quá tải | Không tạo thêm năng lực, phải chấp nhận chậm/từ chối một phần công việc |

**Replication không đồng nghĩa write sharding.** Replica có thể tăng khả năng sẵn sàng và phục vụ một số loại đọc tùy consistency, nhưng ghi thường vẫn phải đi qua cơ chế phối hợp nhất định; thêm replica thậm chí có thể tăng chi phí đồng bộ.

**Thêm shard cũng không tự chữa truy vấn kém.** Một truy vấn quét rộng có thể biến thành nhiều truy vấn trên nhiều shard, làm tăng fan-out và chi phí tổng hợp. Nên đánh giá cả p95/p99, fan-out query, số document scanned/returned và tải trên từng node.

### Autoscaling có độ trễ và giới hạn

Cơ chế autoscaling có thể cần thời gian để đo tín hiệu, cấp node, làm ấm cache, di chuyển partition hoặc chuyển traffic. Vì vậy, một đỉnh tăng từ 100 lên 5.000 request/giây trong hai giây không chắc được cứu kịp bằng autoscaling phản ứng.

Một kế hoạch thường kết hợp:

- **Năng lực dự phòng** cho những dao động tức thời được dự kiến.
- **Pre-scaling** trước sự kiện có lịch nếu nền tảng hỗ trợ.
- **Autoscaling** để đáp ứng xu hướng tăng và đỉnh kéo dài.
- **Rate limiting/backpressure** để bảo vệ phần chưa thể mở rộng.
- **Kiểm soát điểm nóng** vì tổng capacity không mô tả được mọi phân vùng.

Khi có giới hạn capacity của nhà cung cấp, hãy xác định **giới hạn theo account, table/collection, node, partition và thao tác**; tên và con số giới hạn khác nhau theo dịch vụ, cấu hình và thời điểm.

## 13. Giữ tính đúng đắn khi hệ thống quá tải

Một chiến lược giảm tải có thể đạt throughput tốt nhưng gây lỗi dữ liệu nếu áp dụng không đúng nghiệp vụ.

### Đặt hàng và tồn kho

Với một SKU được mua liên tục, không thể chỉ cache số lượng tồn và trừ tồn độc lập trong mỗi instance ứng dụng. Các instance có thể cùng tin rằng còn hàng và tạo quá số đơn.

Các lựa chọn tùy DB và yêu cầu:

- **Conditional atomic update** trên một document cho thao tác đáp ứng đủ điều kiện.
- **Optimistic concurrency** với số phiên bản và retry có giới hạn.
- **Reservation/hold** có thời hạn và trạng thái rõ ràng.
- **Transaction** khi bất biến trải rộng nhiều document và DB hỗ trợ theo yêu cầu.
- **Hàng đợi/điều phối theo khóa** nếu cần tuần tự hóa thao tác trên một thực thể logic.

Cách nào cũng có đánh đổi giữa throughput, độ trễ, chi phí vận hành và mô hình nhất quán. Không nên đổi sự chính xác của tồn kho để lấy thêm throughput mà không có yêu cầu nghiệp vụ chấp thuận.

### Ghi event và telemetry

Với telemetry có thể nhận bất đồng bộ, có thể phản hồi `202 Accepted` sau khi tiếp nhận bền vững vào hàng đợi nếu hợp đồng API quy định đúng ý nghĩa đó. Việc xử lý cuối cùng diễn ra sau. Nếu cần đảm bảo không mất event đã nhận, phải xác định thời điểm **đã ghi bền vững**, retry và chính sách khôi phục.

### Rate limit công bằng theo tenant

Khi một tenant chiếm phần lớn tải, giới hạn toàn hệ thống có thể khiến nhiều tenant nhỏ bị ảnh hưởng. **Rate limit theo tenant** hoặc hạn ngạch có trọng số giúp phân chia nguồn lực công bằng hơn. Tuy vậy, chính sách phải cân nhắc gói dịch vụ, ưu tiên nghiệp vụ, burst allowance và các tác vụ không thể trì hoãn.

HTTP có thể phản hồi `429 Too Many Requests` hoặc `503 Service Unavailable` tùy ngữ nghĩa tình huống; client cần chính sách retry có backoff/jitter và không retry vô hạn. Với request ghi, idempotency key hoặc cơ chế tương đương giúp giảm rủi ro thực hiện lặp.

## 14. Kiểm thử tải phải tái tạo cả skew và burst

Một bài load test với 1.000 request/giây, khóa được chọn đều ngẫu nhiên, có thể báo “PASS”. Nhưng sản phẩm thật có thể có 60% request truy cập cùng một tenant, một khoảng thời gian ghi dồn vào shard cuối, hoặc cache bị xóa sau deploy.

Để kiểm thử phản ánh nhu cầu mở rộng, nên có **ma trận kịch bản**:

| Kịch bản | Mẫu lưu lượng | Điểm quan sát |
|---|---|---|
| Baseline | Tốc độ ổn định, mix đọc/ghi như thực tế | Latency, error, resource, cost |
| Ramp | Tăng từng bước và giữ đủ lâu | Thời điểm bắt đầu vi phạm SLO |
| Spike | Tăng đột ngột rồi hạ xuống | Throttling, queue, recovery |
| Soak | Tải cao nhiều giờ | Memory leak, compaction, tăng độ trễ |
| Skew | 40–70% request dồn vào nhóm nhỏ key | Hottest partition, xung đột, retry |
| Cold cache | Cache miss hàng loạt | Tải đổ về database, thời gian hồi phục |
| Background overlap | Vừa có batch/backup/index job, vừa có traffic | Tranh chấp I/O và CPU |
| Failure under load | Mất node/replica hoặc network suy giảm có kiểm soát | Khả năng duy trì phục vụ và độ trễ failover |

Tỷ lệ 40–70% trong hàng skew là **giả định thử thách**; tình huống thật nên dựa vào phân bố quan sát được hoặc rủi ro dự kiến. Các bài kiểm thử gây tải lớn cần chạy ở môi trường và thời điểm được phép, với dữ liệu giả hoặc đã được quản lý phù hợp.

### Cần mô phỏng những gì?

- Kích thước document thực tế, có cả các giá trị lớn hiếm gặp.
- Tỷ lệ đọc/ghi và dạng query chính, kể cả fan-out và aggregation.
- Số lượng key đang hoạt động; phân bố đều, tập trung và theo thời gian.
- Thời gian nghĩ của client, concurrency, deadline và retry.
- Cache warm/cold, eviction và mất cache.
- Index, replica, cấu hình consistency, retention và batch nền tương tự môi trường mục tiêu.

**Không dùng duy nhất số request thành công làm kết luận.** Cần nhìn p95/p99, tỉ lệ timeout, độ dài hàng đợi, tuổi message, mức throttling theo partition và khả năng phục hồi sau đỉnh.

## 15. Dashboard và cảnh báo để biết khi nào phải mở rộng

Một dashboard tốt không chỉ có “CPU” và “disk”. Cần kết hợp tín hiệu trải nghiệm người dùng, tải thực tế và phân phối nội bộ.

| Nhóm tín hiệu | Chỉ số nên quan sát | Diễn giải |
|---|---|---|
| Trải nghiệm | p50/p95/p99 latency, timeout, lỗi theo endpoint | Người dùng có đang bị ảnh hưởng? |
| Lưu lượng | API RPS, DB reads/writes, kích thước payload, tốc độ tăng | Áp lực tăng theo chiều nào? |
| Năng lực | CPU, memory, disk IOPS, network, connection pool | Tài nguyên nào gần giới hạn? |
| Partition | Throughput theo partition, hottest key, throttled requests, bytes/partition | Có skew mà trung bình che giấu không? |
| Truy vấn | Query latency, scanned/returned, index hit, slow query | Có truy vấn đắt hoặc index không phù hợp? |
| Cache | Hit/miss, eviction, load vào source, stampede | Cache có giảm tải thật không? |
| Async | Queue depth, age of oldest message, consumer lag, retry, DLQ | Backlog tăng hay đang phục hồi? |
| Replication | Replication lag, trạng thái node, failover | Tính sẵn sàng và độ mới của đọc có bị ảnh hưởng? |
| Chi phí | Chi phí storage, capacity, network, backup và index | Mở rộng có bền vững về chi phí? |

Ví dụ một cảnh báo theo hướng SLO:

> Trong 5 phút, p99 của API ghi tăng vượt mục tiêu **đồng thời** tỷ lệ throttle tại DB tăng; kiểm tra ngay phân bố ghi theo partition và mức backlog.

Các ngưỡng, khoảng đo và mức độ khẩn cấp phải được hiệu chỉnh bằng lịch sử đo và SLO; số liệu đơn lẻ như CPU 70% không tự chứng minh hệ thống đang quá tải. Tương tự, thời điểm latency p99 tăng có thể do GC, network hoặc service phụ trợ thay vì storage.

Một dashboard có cả **thời điểm** và **khóa nóng** giúp trả lời câu hỏi quan trọng: “Giờ hệ thống chậm vì tổng tải tăng, vì một tenant quá nóng, hay vì một query đắt bất thường?”

## 16. Quy trình lập kế hoạch capacity theo tình huống

Giả sử nhóm sản phẩm thông báo sẽ mở một đợt bán hàng vào thứ Sáu. Có thể triển khai tư duy theo chuỗi quyết định sau.

~~~mermaid
flowchart TD
    A["Sự kiện, tăng trưởng và SLO"] --> B["Ước lượng peak RPS, đọc/ghi, kích thước"]
    B --> C["Phân bố khóa, tenant, partition, giờ cao điểm"]
    C --> D["Tái hiện bằng load test burst + skew"]
    D --> E{"Nút thắt quan sát được?"}
    E -->|"Query / index"| F["Tối ưu truy vấn và dữ liệu"]
    E -->|"Hot key / partition"| G["Thiết kế lại phân phối hoặc điều phối theo khóa"]
    E -->|"Tổng capacity"| H["Scale node/partition, chuẩn bị năng lực"]
    E -->|"Tải đến nhanh"| I["Cache, queue có giới hạn, admission control"]
    F --> J["Đo lại SLO, rủi ro, chi phí"]
    G --> J
    H --> J
    I --> J
~~~

### Bước 1 — Ghi profile nhu cầu, không chỉ peak RPS

Ví dụ hồ sơ dự kiến:

~~~yaml
scenario: friday-promotion
traffic:
  apiAverageRps: 100
  apiPeakRps: 1500
  peakDurationMinutes: 20
  readFraction: 0.80
  writeFraction: 0.20
skew:
  topTenantShare: 0.40
  hottestSkuShareOfWrites: 0.30
data:
  averageDocumentKiB: 2
  newDocumentsPerDay: 500000
  retentionDays: 30
serviceObjectives:
  readP95Milliseconds: 200
  writeP99Milliseconds: 500
assumptions:
  - "Đây là dữ liệu giả định để lập kế hoạch"
  - "Cần đo lại operation cost, cache hit và giới hạn theo partition"
~~~

Ở đây `hottestSkuShareOfWrites: 0.30` nghĩa là **30% request ghi nhắm đến một SKU**, không phải 30% tổng mọi request. Với 1.500 API RPS và 20% request là ghi, số yêu cầu ghi là 300/giây; khoảng **90 request ghi/giây** có thể dồn vào SKU đó nếu tỷ lệ áp dụng đúng tại API. Đó là chỉ báo phải kiểm tra điểm nghẽn theo khóa, không phải kết luận chắc chắn một partition sẽ chịu chính xác 90 thao tác DB/giây.

### Bước 2 — Đo đường đi thực của request

Xác định endpoint nào truy cập collection nào, bao nhiêu operation, index nào được dùng và mỗi operation mất bao lâu. Đừng quên luồng cập nhật giỏ hàng, áp mã giảm giá, trừ tồn, tạo đơn, phát event và các tác vụ hậu xử lý.

### Bước 3 — Kiểm tra phân bố thực tế

Đo request theo SKU/tenant/query shape, số key hoạt động và tải từng partition. Cần biết có phải **một item** được cập nhật liên tục, hay là **nhiều item** cùng nằm trong một partition.

### Bước 4 — Chọn biện pháp theo nút thắt

Nếu đọc sản phẩm quá nhiều, xem xét cache và cơ chế tránh cache stampede. Nếu thao tác trừ tồn trên một SKU quá tập trung, đánh giá giới hạn của atomic update và thiết kế reservation/idempotency. Nếu tổng storage hoặc số partition hiện tại thiếu, lập kế hoạch mở rộng vật lý. Nếu import nền tranh chấp tài nguyên, phân lịch hoặc giới hạn tốc độ job.

### Bước 5 — Quy định hành vi khi vượt dự báo

Ngay cả sau mở rộng vẫn cần xác định:

- Có thể giảm hoặc từ chối yêu cầu nào?
- Client có được retry không và trong bao lâu?
- Yêu cầu nào được xác nhận là đã hoàn thành, yêu cầu nào mới được tiếp nhận?
- Khi DB chậm, hệ thống có dừng nhập thêm việc vào queue vô hạn không?
- Có cơ chế ưu tiên hoạt động cốt lõi trước báo cáo hoặc analytics không?

### Bước 6 — Diễn tập và theo dõi hậu sự kiện

Chạy kịch bản spike và skew trong môi trường kiểm thử phù hợp, quan sát khả năng hồi phục. Khi chạy thực tế, theo dõi metric và có phương án điều chỉnh capacity, giới hạn batch, tắt tính năng phụ hoặc giảm tốc producer tùy mục tiêu dịch vụ.

## 17. Những ngộ nhận thường gây thiết kế sai

**“Tải trung bình 100 RPS thì cấp 200 RPS là dư.”** Dự báo phải xem cả đỉnh ngắn, đỉnh kéo dài, thay đổi traffic mix và các sự kiện có lịch. Hệ số dự phòng cần dựa trên dữ liệu và thời gian phản ứng của hệ thống.

**“Cluster còn 50% CPU nên không thể quá tải.”** Một partition, node, lock logic, connection pool hoặc thao tác hot document có thể chạm giới hạn trước tổng CPU.

**“Băm shard key là hết lệch.”** Hash giúp phân phối **các giá trị khác nhau**; không tách một khóa logic được cập nhật liên tục nếu dữ liệu vẫn gắn với một khóa ấy.

**“Cứ thêm replica là ghi nhanh hơn.”** Replication phục vụ mục tiêu sẵn sàng và một số kiểu phân tán đọc; throughput ghi phụ thuộc kiến trúc ghi/consensus của database.

**“Hàng đợi hấp thụ được mọi lưu lượng.”** Hàng đợi chỉ trì hoãn công việc. Nếu tải đến cao hơn khả năng xử lý trong thời gian dài, backlog và thời gian chờ tăng không giới hạn nếu thiếu biện pháp khác.

**“Có autoscaling nên không cần dự trữ capacity.”** Autoscaling có thể cần thời gian, bị giới hạn quota hoặc không chữa được hot key. Burst tức thời cần chính sách nhận tải, cache và hạn mức.

**“Cache càng lâu càng tốt.”** Cache giúp giảm đọc nhưng có thể làm người dùng thấy dữ liệu cũ. Tính đúng đắn của tồn kho, hạn mức và trạng thái giao dịch cần được xét riêng.

**“Load test đều key là giống production.”** Traffic thật thường có phân bố đuôi dài, top tenant lớn, đối tượng nổi tiếng và đỉnh thời gian. Test thiếu skew có thể đánh giá sai khả năng mở rộng.

**“Mở rộng là thay một con số cấu hình.”** Thêm node nhưng giữ truy vấn full scan, khóa phân vùng kém hoặc hoạt động batch không giới hạn có thể chỉ làm chi phí tăng.

## 18. Bài tập tư duy và cách suy luận

### Tình huống A — Sự kiện tăng đột biến nhưng queue dồn lại

Một luồng event nhận 1.200 message/giây trong 3 phút. Consumer xử lý bền vững 900 message/giây. Sau 3 phút, luồng đến giảm còn 600 message/giây, consumer vẫn xử lý 900 message/giây.

**Hỏi:** backlog tăng bao nhiêu trong đỉnh và cần bao lâu để tiêu hết backlog sau khi tải giảm, nếu không tính message lỗi hay retry?

**Gợi ý suy luận:**

\[
(1.200-900)\times(3\times60)=54.000\ \text{message}
\]

Sau đỉnh, tốc độ giảm backlog là `900-600 = 300` message/giây, nên thời gian lý tưởng để xóa tồn đọng là:

\[
54.000 / 300 = 180\ \text{giây}
\]

Tức thêm **3 phút**. Trong thực tế phải chừa biên độ cho retry, giới hạn DB, message lớn và biến động tốc độ xử lý.

### Tình huống B — Tổng throughput đủ nhưng một SKU vẫn chậm

Một cluster được đo có thể xử lý nhiều nghìn lần cập nhật lên **những khóa độc lập** mỗi giây. Trong flash sale, 60% thao tác trừ tồn lại nhắm đúng một SKU và độ trễ tăng mạnh.

**Hỏi:** nên thêm node hay xem xét cách biểu diễn tồn kho trước?

**Gợi ý suy luận:** trước hết đo thao tác trên item/partition nóng, cạnh tranh cập nhật và xử lý retry. Nếu phần lớn công việc cùng tranh một trạng thái có bất biến mạnh, thêm node không tự phân chia được item đó. Phải lựa chọn cơ chế ghi theo SKU, đặt chỗ hoặc giới hạn tốc độ hợp lý trước khi kết luận cần thay đổi topology.

### Tình huống C — Dữ liệu tăng đều nhưng latency chỉ tăng cuối tháng

Số document tăng 2% mỗi tuần, còn p99 truy vấn báo cáo tăng mạnh vào ngày cuối tháng.

**Hỏi:** đây chắc chắn là thiếu shard?

**Gợi ý suy luận:** chưa đủ dữ kiện. Có thể query báo cáo quét phạm vi lớn, job tính cước tranh I/O, một số tenant có dữ liệu lớn hoặc working set vượt cache. Đo query shape, index, scanned/returned, partition skew và tải background trong đúng cửa sổ xảy ra sự cố trước khi quyết định mở rộng.

## 19. Khung quyết định có thể áp dụng cho hệ thống NoSQL thực tế

Khi nhận yêu cầu “phải chịu gấp 10 lần tải”, hãy chuyển yêu cầu đó thành một hợp đồng đo được:

1. **Gấp 10 lần cái gì?** API request, DB operation, số key đồng thời hay lượng dữ liệu?
2. **Tăng trong bao lâu?** Vài giây, 15 phút, một ngày hay dài hạn?
3. **Tải nằm ở đâu?** Phân bố đều, top tenant, top SKU, hot document hay range thời gian mới nhất?
4. **Điều kiện đọc/ghi là gì?** Có được cache, chờ hàng đợi hoặc chấp nhận dữ liệu trễ không?
5. **Mục tiêu chất lượng nào phải giữ?** p95/p99, tỉ lệ lỗi, tính nhất quán, mất mát dữ liệu, thời gian phục hồi?
6. **Điểm nghẽn thực tế là gì?** Query, index, partition, capacity, connection, network, background load hay khóa nghiệp vụ?
7. **Biện pháp nào giải đúng nguyên nhân?** Tối ưu truy vấn, sửa partition key, giới hạn tải, chia công việc, cache, pre-scale hay tăng node?
8. **Chứng minh bằng gì?** Kịch bản kiểm thử tái hiện được burst, skew, cold cache và hành vi khi vượt ngưỡng.

Điểm quan trọng nhất của bài học là **dự báo NoSQL phải xem cả khối lượng và phân bố công việc**. Dữ liệu trải đều cùng 1.500 request/giây là một bài toán khác hoàn toàn với 1.500 request/giây dồn vào một tenant hoặc một document. Dự đoán tải đột biến cho biết *khi nào và bao nhiêu*, phân tích dữ liệu lệch cho biết *ở đâu*, còn thiết kế mở rộng chỉ có ý nghĩa khi xác định được *nút thắt nào cần được thay đổi và bất biến nào phải được giữ nguyên*.
