# Tỷ lệ đọc/ghi, kích thước bản ghi và phân bố truy cập trong NoSQL

Một hệ quản trị NoSQL thường được chọn để phục vụ khối lượng dữ liệu hoặc lưu lượng lớn, nhưng chỉ biết hệ thống có “một triệu người dùng” hay “một tỷ bản ghi” chưa đủ để chọn cách lưu trữ. Hai ứng dụng có cùng số bản ghi vẫn có thể cần kiến trúc rất khác nhau: một ứng dụng đọc hồ sơ người dùng liên tục và ít cập nhật; ứng dụng khác ghi sự kiện theo thời gian với tốc độ cao; ứng dụng thứ ba có một sản phẩm đang được hàng triệu người xem cùng lúc.

Để mô tả **yêu cầu và tải dữ liệu (workload)**, cần phân tích đồng thời ba khía cạnh:

1. **Tỷ lệ đọc/ghi:** mỗi giây hệ thống thực hiện bao nhiêu yêu cầu đọc, ghi, và mỗi loại thao tác tốn những tài nguyên gì?
2. **Kích thước bản ghi:** mỗi tài liệu, hàng, đối tượng hoặc mục dữ liệu chiếm bao nhiêu byte; kích thước thay đổi như thế nào theo thời gian?
3. **Phân bố truy cập:** những khóa, phân vùng, người dùng hoặc khoảng thời gian nào được truy cập nhiều nhất; mức độ tập trung và đột biến ra sao?

Ba khía cạnh có quan hệ chặt chẽ. Cùng một tỷ lệ 90% đọc có thể vận hành rất nhẹ nếu đa số là truy vấn theo khóa vào bản ghi nhỏ, nhưng trở nên nặng nếu mỗi lần đọc quét hàng nghìn bản ghi. Cùng mức 10.000 thao tác/giây có thể phân tán đều trên nhiều phân vùng hoặc dồn vào một khóa nóng gây nghẽn.

## 1. Xác định đúng đơn vị của workload

Trước khi tính tỷ lệ, cần thống nhất **đang đếm thao tác ở lớp nào**:

| Đơn vị | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Yêu cầu ứng dụng | Một lời gọi HTTP/API hoặc một hành động của người dùng | Có thể phát sinh nhiều thao tác cơ sở dữ liệu |
| Thao tác logic với CSDL | Một lệnh lấy theo khóa, truy vấn, thêm, sửa hoặc xóa | Có thể xử lý nhiều bản ghi và nhiều phân vùng |
| Thao tác vật lý | Đọc trang đĩa, đọc từ cache, ghi WAL/commit log, cập nhật chỉ mục, truyền bản sao | Phụ thuộc engine, cache, index và replication |
| Số byte | Dữ liệu đọc/trả về hoặc được ghi/truyền/lưu | Không thể suy ra chỉ từ số thao tác |

Ví dụ, API “xem trang sản phẩm” có thể đọc thông tin sản phẩm, tồn kho, giá theo khu vực và đánh giá; một yêu cầu HTTP tạo ra bốn hoặc nhiều lượt đọc dữ liệu. Ngược lại, một lệnh ghi theo lô có thể đưa hàng trăm sự kiện vào CSDL. Vì vậy, **RPS của API không mặc nhiên bằng số thao tác/giây của CSDL**.

Một mô tả workload có ích thường ghi:

- **Loại thao tác:** lấy theo khóa (point read), truy vấn theo điều kiện/range, scan, insert, update, delete, batch.
- **Số thao tác/giây:** trung bình, giờ cao điểm và đỉnh ngắn hạn.
- **Phạm vi:** toàn hệ thống và theo collection/table, tenant, khóa phân vùng hoặc vùng địa lý.
- **Kích thước:** byte được gửi, byte bản ghi lưu trữ, byte thực sự được trả về sau projection.
- **Chất lượng dịch vụ:** p50/p95/p99 latency, tỷ lệ lỗi, yêu cầu nhất quán, độ mới của dữ liệu.
- **Thời gian:** ban ngày/ban đêm, ngày thường/chiến dịch, xu hướng tăng trưởng và mùa vụ.

Những con số này cần có **cùng một khoảng thời gian và cùng cách đếm**. Không nên so tỷ lệ đọc của một ngày với lưu lượng ghi của một phút cao điểm.

## 2. Tỷ lệ đọc/ghi (read/write ratio)

### 2.1. Cách tính

Gọi:

- **R**: số thao tác đọc logic trong một giây;
- **W**: số thao tác ghi logic trong một giây, gồm insert, update và delete theo định nghĩa đo lường đã chọn.

Khi đó:

~~~text
Tỷ lệ đọc : ghi = R : W
Tỷ trọng đọc = R / (R + W) × 100%
Tỷ trọng ghi = W / (R + W) × 100%
Tổng thao tác logic mỗi giây = R + W
~~~

Ví dụ, một dịch vụ xử lý 8.000 lượt đọc và 2.000 lượt ghi mỗi giây sẽ có tỷ lệ **4:1**, hay **80% đọc / 20% ghi**. Tuy nhiên, nên ghi cả số tuyệt đối: tỷ lệ 4:1 ở 50 thao tác/giây khác rất xa tỷ lệ 4:1 ở 100.000 thao tác/giây.

Khi W bằng 0, workload chỉ đọc trong khoảng đo; không nên biểu diễn phép chia R/W như một giá trị hữu hạn. Tương tự, workload chỉ ghi cần được mô tả rõ ràng.

### 2.2. Các kiểu workload thường gặp

| Kiểu tải | Đặc điểm | Tác động thiết kế điển hình |
| --- | --- | --- |
| **Read-heavy** | Đọc nhiều hơn ghi, thường gặp ở danh mục sản phẩm, nội dung, hồ sơ công khai | Cần đường đọc ngắn, chỉ mục đúng truy vấn, cache, bản sao phục vụ đọc nếu phù hợp |
| **Write-heavy** | Sự kiện, log, đo lường hoặc thay đổi trạng thái được ghi liên tục | Cần phân bố khóa ghi tốt, đường ghi hiệu quả, ghi theo lô khi phù hợp, chính sách lưu giữ |
| **Mixed** | Đọc và ghi đều quan trọng, ví dụ giỏ hàng, phiên hoạt động, giao dịch nghiệp vụ | Cân bằng chi phí chỉ mục với ghi; xử lý xung đột và yêu cầu nhất quán |
| **Burst/spiky** | Trung bình thấp nhưng lưu lượng tăng đột biến | Cần dự trù đỉnh, điều tiết, hàng đợi, tự mở rộng và tránh khóa nóng |

Tỷ lệ đọc/ghi chỉ là **một chỉ báo**, không phải thước đo chi phí hoàn chỉnh:

- Một **point read** trả về tài liệu 1 KiB thường khác xa truy vấn quét 100.000 tài liệu rồi trả về 10 kết quả.
- Một **insert** có thể khác chi phí với **update** làm thay đổi nhiều chỉ mục hoặc cập nhật điều kiện có tranh chấp.
- Một **delete** có thể chỉ đánh dấu tombstone trước khi dữ liệu thực sự được thu hồi, tùy engine.
- Một lệnh ghi có thể phát sinh ghi commit log, cập nhật index, gửi bản sao và quá trình compact về sau.
- **Cache hit** giúp giảm lần đọc vào CSDL, nhưng cũng làm tỷ lệ quan sát ở tầng API khác tỷ lệ quan sát tại storage engine.

Do đó, cần lập **workload mix theo loại thao tác**, chẳng hạn 60% lấy theo khóa, 15% range query, 5% scan, 15% insert và 5% update, thay vì dừng ở “80% đọc”.

### 2.3. Read amplification và write amplification

**Read amplification** là hiện tượng để đáp ứng một lượng dữ liệu hữu ích, hệ thống phải đọc/xử lý nhiều dữ liệu hơn. Ví dụ, truy vấn chỉ trả về 20 KiB nhưng phải xem xét 20 MiB vì thiếu chỉ mục hoặc dữ liệu nằm rải rác.

**Write amplification** là hiện tượng ghi logic nhỏ có thể dẫn đến nhiều lần ghi vật lý, chẳng hạn do index, WAL, replication, compaction hoặc cơ chế lưu trữ. Cách định nghĩa và cách đo cụ thể khác nhau giữa các hệ quản trị.

Không có một hệ số khuếch đại cố định áp dụng cho mọi NoSQL. Muốn ước lượng tài nguyên phải đo bằng loại truy vấn, cấu hình chỉ mục, chiến lược lưu trữ, mức cache hit và cấu hình bản sao thực tế.

### 2.4. Tỷ lệ đọc/ghi ảnh hưởng đến thiết kế ra sao?

Trong hệ đọc nhiều, có thể tối ưu bằng **truy vấn theo khóa đã biết**, **projection** chỉ lấy trường cần thiết, **cache** các dữ liệu phổ biến, hoặc **denormalization** để giảm số lần truy vấn. Đổi lại, bản sao dữ liệu trong nhiều cấu trúc có thể khiến thao tác ghi phức tạp hơn và phát sinh bài toán đồng bộ.

Trong hệ ghi nhiều, không nên tạo chỉ mục cho mọi trường vì mỗi lần ghi có thể phải cập nhật thêm các cấu trúc chỉ mục. Cần chọn **partition key** phân tán tải ghi, xem xét batch và buffering, dùng TTL/lưu trữ phân tầng nếu dữ liệu có vòng đời ngắn.

Trong hệ đọc–ghi cùng cao, câu hỏi then chốt thường là: sau khi ghi, lần đọc kế tiếp cần thấy ngay giá trị mới hay có thể chấp nhận độ trễ? **Strong consistency**, **eventual consistency**, điều kiện cập nhật và cơ chế chống ghi đè có thể thay đổi độ trễ, throughput và độ phức tạp. Không nên suy diễn mức nhất quán chỉ từ tỷ lệ đọc/ghi.

## 3. Kích thước bản ghi (record/document size)

### 3.1. Định nghĩa kích thước

Trong NoSQL, “bản ghi” có thể là document JSON/BSON, item key–value, row trong wide-column store, một cạnh/đỉnh đồ thị, v.v. Cần phân biệt:

| Khái niệm | Ví dụ |
| --- | --- |
| **Kích thước dữ liệu logic** | Trường và giá trị mà ứng dụng xem là một bản ghi |
| **Kích thước tuần tự hóa (serialized)** | Byte khi mã hóa thành JSON, BSON, protobuf… bao gồm tên trường và cấu trúc |
| **Kích thước truyền tải** | Byte qua mạng, có thể đã nén hoặc chỉ chứa các trường được yêu cầu |
| **Kích thước lưu trữ vật lý** | Dữ liệu cộng metadata, chỉ mục, phiên bản, log, overhead và ảnh hưởng nén |
| **Dung lượng toàn cụm** | Dữ liệu vật lý cộng bản sao, phân mảnh và khoảng trống vận hành |

Không nên đồng nhất một JSON dài 2 KiB với 2 KiB dung lượng đĩa hoặc 2 KiB cho mỗi lần đọc. Cơ sở dữ liệu có thể dùng kiểu mã hóa khác JSON, nén dữ liệu, và yêu cầu chỉ một phần trường.

Ví dụ một tài liệu sản phẩm:

~~~json
{
  "productId": "P-1042",
  "name": "Bàn phím cơ",
  "price": 1490000,
  "categoryId": "C-18",
  "stock": 24,
  "tags": ["mechanical", "wireless"],
  "updatedAt": "2026-11-14T08:00:00Z"
}
~~~

Nếu mỗi sản phẩm chứa thêm toàn bộ lịch sử thay đổi, danh sách đánh giá và hình ảnh nhúng trực tiếp, kích thước có thể tăng rất nhanh. Một giải pháp là tách **metadata truy cập thường xuyên** khỏi **nội dung lớn hoặc tăng không giới hạn**, sau đó truy xuất phần phụ khi thực sự cần.

### 3.2. Đo phân bố kích thước, không chỉ giá trị trung bình

Kích thước bản ghi trong thực tế thường không đều. Cần xem tối thiểu:

- **p50**: một nửa bản ghi không lớn hơn kích thước này.
- **p95/p99**: phần đuôi chứa các bản ghi lớn, có thể ảnh hưởng băng thông và độ trễ.
- **Max**: bản ghi lớn nhất; hữu ích để xét giới hạn của engine, request hoặc mạng.
- **Phân bố theo loại**: bản ghi sản phẩm, người dùng, đơn hàng và sự kiện không nên gộp vô điều kiện.
- **Tốc độ tăng**: các mảng nhúng như lịch sử truy cập, bình luận hay phần tử giỏ hàng có thể phình ra theo thời gian.

Ví dụ 99% tài liệu chỉ 2 KiB, nhưng 1% tài liệu đạt 500 KiB. Trung bình xấp xỉ **6,98 KiB**, cao hơn ba lần kích thước điển hình 2 KiB. Hệ thống có thể gặp đỉnh băng thông khi những tài liệu lớn được đọc đồng thời, dù độ trễ trung vị vẫn thấp.

### 3.3. Kích thước tác động tới throughput như thế nào?

Ước lượng sơ bộ:

~~~text
Băng thông đọc hữu ích/giây ≈ số đọc/giây × byte trả về trung bình/lần
Băng thông ghi logic/giây ≈ số ghi/giây × byte đầu vào trung bình/lần
Dung lượng dữ liệu mới/ngày ≈ số bản ghi mới/giây × byte/bản ghi × 86.400
Dung lượng giữ lại ≈ dữ liệu phát sinh − dữ liệu bị xóa/hết hạn
~~~

Những phép tính này mô tả **lượng dữ liệu logic**, chưa bao gồm byte đọc thừa, network protocol, index, replication, compaction, backup và compression. Nếu thao tác ghi chủ yếu là **update trên bản ghi có sẵn**, không được lấy toàn bộ số thao tác ghi nhân với kích thước bản ghi rồi coi là dung lượng mới.

Để ước lượng lưu trữ, có thể dùng:

~~~text
Logical storage = số bản ghi còn hiệu lực × kích thước lưu trữ logic trung bình
Replicated data ≈ dữ liệu lưu tại một bản sao × số bản sao
Provisioned storage = replicated data + index + log + overhead + headroom
~~~

Với hệ có mã hóa xóa (erasure coding), tiering hoặc cách tính dung lượng đặc thù, công thức bản sao đơn giản ở trên cần thay bằng mô hình thực tế của hệ đó.

### 3.4. Bản ghi quá lớn gây vấn đề gì?

Một tài liệu lớn có thể làm tăng thời gian đọc/ghi, lượng dữ liệu truyền, bộ nhớ đệm cần dùng và mức tranh chấp khi nhiều tác nhân cùng sửa một đối tượng. Danh sách nhúng tăng mãi có thể chạm giới hạn document/item của sản phẩm cụ thể; giới hạn này khác nhau giữa MongoDB, DynamoDB, Cassandra và các sản phẩm khác, nên phải tra đúng phiên bản/dịch vụ đang dùng.

Mặt khác, chia một đối tượng thành quá nhiều bản ghi nhỏ cũng tạo ra nhiều lần truy cập, nhiều round trip và khó đảm bảo thao tác cập nhật đồng bộ. Quy tắc thực tế là **đóng gói theo mẫu truy cập và vòng đời dữ liệu**: dữ liệu thường được đọc/sửa cùng nhau và có kích thước ổn định có thể nằm chung; phần lớn, ít dùng hoặc phát triển không giới hạn nên được cân nhắc tách riêng.

## 4. Phân bố truy cập (access distribution)

### 4.1. Đọc gì, bằng khóa nào?

Phân bố truy cập trả lời các câu hỏi:

- Truy cập theo **khóa chính**, theo **tenant**, theo khoảng thời gian hay theo điều kiện trên trường không được lập chỉ mục?
- Bao nhiêu phần trăm truy vấn chỉ đọc một bản ghi, một nhóm nhỏ, hoặc quét một vùng lớn?
- Khóa nào nhận nhiều request nhất? Một nhóm nhỏ khóa chiếm bao nhiêu phần trăm lưu lượng?
- Đọc và ghi có cùng phân bố không? Khóa nóng về đọc có đồng thời nóng về ghi không?
- Tải có thay đổi theo giờ, chiến dịch, vùng địa lý hay vòng đời của một đối tượng không?

Với NoSQL phân vùng, **số request toàn cụm chỉ có ý nghĩa khi đi kèm phân bố theo partition key**. Cụm có 20 phân vùng không đồng nghĩa mỗi phân vùng nhận 1/20 lưu lượng.

### 4.2. Các dạng phân bố thường gặp

| Phân bố | Biểu hiện | Rủi ro hoặc hệ quả |
| --- | --- | --- |
| **Gần đồng đều (uniform)** | Các khóa nhận lượng truy cập tương tự | Tương đối dễ cân bằng và dự đoán |
| **Lệch mạnh/Zipf-like** | Một số khóa phổ biến hơn phần lớn khóa còn lại | Hot key, cache hot spot, tài nguyên phân vùng không đều |
| **Theo thời gian** | Dữ liệu mới nhất được truy cập nhiều; dữ liệu cũ giảm dần | Dễ dồn vào “phân vùng hiện tại” nếu key là ngày/giờ |
| **Theo tenant/vùng** | Một khách hàng lớn hoặc một khu vực tạo phần lớn tải | Một partition hoặc tài nguyên chia sẻ bị ảnh hưởng bởi tenant lớn |
| **Theo sự kiện/burst** | Sản phẩm viral, flash sale, batch import, job định kỳ | Đỉnh ngắn hạn cao hơn trung bình rất nhiều |
| **Theo dải khóa (range)** | Đọc liên tiếp một khoảng thời gian, giá trị hoặc vị trí | Cần partition/sort key phục vụ range query; scan sai mô hình có thể rất đắt |

Phân bố thường thay đổi theo thời gian. Một khóa “lạnh” hôm nay có thể thành khóa nóng khi có khuyến mãi. Vì vậy, khảo sát dữ liệu lịch sử cần đi kèm kịch bản sự kiện bất thường.

### 4.3. Nhận biết hot key và hot partition

**Hot key** là khóa nhận lượng truy cập lớn bất thường. **Hot partition** là phân vùng vật lý hoặc logic phải gánh tải cao hơn khả năng xử lý; nhiều khóa không quá nóng vẫn có thể cùng rơi vào một phân vùng nóng.

Ví dụ:

~~~text
10.000 lượt đọc/giây trên toàn cụm
├── 1 sản phẩm đang nổi: 4.000 lượt đọc/giây
└── Các sản phẩm khác: 6.000 lượt đọc/giây
~~~

Dù dùng hàm băm để chia khóa đều, **tất cả lượt đọc của cùng một khóa** có thể vẫn tập trung tại một vị trí dữ liệu chính, trừ khi hệ thống có bản sao, cache hoặc kỹ thuật phân phối đọc phù hợp. Tăng số phân vùng đơn thuần không nhất thiết giải quyết hot key.

Một số hướng xử lý:

- **Đọc nóng:** cache gần ứng dụng/CDN nếu đúng loại dữ liệu; dùng replica phục vụ đọc nếu hỗ trợ và độ trễ nhất quán cho phép; tránh gọi lại dữ liệu không đổi ở mọi request.
- **Ghi nóng:** phân tán các bản ghi độc lập bằng khóa có độ đa dạng cao; cân nhắc sharded counter, bucket theo thời gian hoặc theo shard khi bài toán cho phép, đồng thời có cách tổng hợp đúng.
- **Tenant lớn:** quan sát theo tenant, cân nhắc giới hạn tài nguyên, cách ly hoặc phân vùng theo chiến lược phù hợp thay vì để một tenant chiếm toàn bộ.
- **Query theo range:** chọn key và index để dữ liệu cần đọc được truy cập hiệu quả; tránh tăng shard ngẫu nhiên rồi buộc mọi truy vấn range phải fan-out toàn cụm.

Không nên thêm phần ngẫu nhiên vào partition key một cách mù quáng: việc phân tán ghi có thể khiến các thao tác đọc, sắp xếp hoặc transaction phải tìm trên nhiều shard.

### 4.4. Những chỉ số mô tả độ lệch

Ngoài throughput trung bình, nên đo:

| Chỉ số | Câu hỏi trả lời |
| --- | --- |
| **Top-1/Top-10/Top-1% keys** | Một số ít khóa chiếm bao nhiêu % số request? |
| **Throughput lớn nhất trên mỗi partition** | Phân vùng căng nhất có quá tải dù cả cụm còn dư tài nguyên không? |
| **p95/p99 của ops/key hoặc ops/partition** | Đuôi tải phân bố lệch tới đâu? |
| **Cache hit ratio theo key/nhóm key** | Cache có thực sự hấp thụ tải đọc nóng không? |
| **Độ trễ và throttling theo partition/tenant** | Vấn đề chỉ xảy ra với nhóm khóa nào? |
| **Tính thời vụ và hệ số peak/average** | Giờ cao điểm lớn hơn bình quân bao nhiêu lần? |

Ví dụ: một ngày có 100 triệu lượt đọc, trong đó 70% tập trung vào 1% khóa, thì giả định “chia đều 100 triệu lượt đọc trên toàn bộ khóa” sẽ đánh giá thấp khả năng phát sinh điểm nóng.

## 5. Kết hợp ba khía cạnh để chọn thiết kế dữ liệu

Một quyết định thiết kế tốt phải xuất phát từ **thao tác nào diễn ra thường xuyên nhất, dữ liệu nào được mang theo mỗi thao tác, và thao tác ấy tập trung ở đâu**.

| Workload | Đọc/ghi | Kích thước bản ghi | Phân bố | Hướng cân nhắc |
| --- | --- | --- | --- | --- |
| Danh mục sản phẩm | Đọc áp đảo | Metadata nhỏ; mô tả và media có thể lớn | Một số sản phẩm rất nóng | Tối ưu get-by-id, chỉ lấy trường cần thiết, cache dữ liệu phổ biến, tách media lớn |
| Dữ liệu telemetry | Ghi áp đảo | Sự kiện nhỏ, số lượng lớn | Tập trung theo thiết bị/thời gian, có burst | Khóa ghi có độ phân tán, ingest theo lô, TTL và query theo khoảng thời gian |
| Giỏ hàng | Cả đọc và cập nhật | Nhỏ đến trung bình, có thể tăng | Nóng theo user đang hoạt động | Thiết kế theo user/cart, cập nhật có điều kiện, kiểm soát kích thước và xung đột |
| Lịch sử đơn hàng | Đọc theo user và thời gian, ghi khi phát sinh | Có nhiều dòng hàng | Lệch theo tenant/user, query theo thời gian | Key hỗ trợ mẫu đọc, pagination, phân biệt đơn hàng với sự kiện trạng thái |
| Bảng xếp hạng realtime | Đọc và cập nhật rất cao | Bản ghi nhỏ | Một số thứ hạng/đối tượng cực nóng | Cấu trúc truy vấn phù hợp, cân nhắc precompute, cache và cập nhật tăng dần |

Ví dụ, **nhúng toàn bộ đánh giá vào tài liệu sản phẩm** có thể giảm số lượt đọc để hiển thị trang chi tiết, nhưng cũng khiến tài liệu tăng kích thước và bị cập nhật liên tục. Nếu đánh giá nhiều và trang sản phẩm được xem thường xuyên, mô hình lưu sản phẩm riêng với đánh giá riêng, kèm truy vấn phân trang hoặc số liệu tổng hợp, thường dễ kiểm soát tải hơn.

Ngược lại, tách mọi trường sản phẩm thành một bảng riêng có thể tạo ra nhiều round trip không cần thiết. Câu hỏi phải là “API chủ đạo cần trả về những dữ liệu gì trong một lần?” và “phần nào thay đổi độc lập?”.

## 6. Ví dụ tính workload và dung lượng

Giả sử một dịch vụ danh mục có số liệu ở giờ bình thường:

| Thông số | Giá trị giả định |
| --- | ---: |
| Point read và query | 4.800 thao tác/giây |
| Insert, update, delete | 1.200 thao tác/giây |
| Kích thước dữ liệu trả về trung bình mỗi lần đọc | 2 KiB |
| Dữ liệu logic đầu vào trung bình mỗi lần ghi | 1 KiB |
| Tỷ lệ ghi thực sự tạo bản ghi mới | 25% lượt ghi |
| Kích thước một bản ghi mới trung bình | 1 KiB |
| Đỉnh tải ngắn hạn | Gấp 3 lần mức bình thường |
| Chính sách giữ dữ liệu mới | 30 ngày |
| Hệ số bản sao minh họa | 3 bản sao dữ liệu |

**Bước 1 — Phân loại tải.**

~~~text
R : W = 4.800 : 1.200 = 4 : 1
Tỷ trọng đọc = 4.800 / 6.000 = 80%
Tỷ trọng ghi = 1.200 / 6.000 = 20%
Đỉnh tổng thao tác = 6.000 × 3 = 18.000 thao tác/giây
~~~

**Bước 2 — Tính dữ liệu hữu ích truyền mỗi giây.**

~~~text
Dữ liệu đọc trả về = 4.800 × 2 KiB = 9.600 KiB/s ≈ 9,38 MiB/s
Dữ liệu đầu vào ghi = 1.200 × 1 KiB = 1.200 KiB/s ≈ 1,17 MiB/s
~~~

Đây là byte dữ liệu ứng dụng. Khi đo mạng giữa app, database và replica, thực tế phải tính thêm protocol, index/cache behavior, các lần thử lại và replication. Peak có thể làm các con số trên tăng, nhưng không nhất thiết mọi loại thao tác đều tăng cùng hệ số.

**Bước 3 — Ước lượng dữ liệu mới nếu mức tải giả định duy trì liên tục.**

~~~text
Insert mới mỗi giây = 1.200 × 25% = 300 bản ghi/s
Dữ liệu mới mỗi ngày = 300 × 1 KiB × 86.400
                       = 25.920.000 KiB ≈ 24,72 GiB
Dữ liệu mới trong 30 ngày ≈ 741,6 GiB ≈ 0,724 TiB
3 bản sao dữ liệu này ≈ 2,17 TiB
~~~

Giả định ở đây là 75% lượt ghi còn lại chỉ sửa/xóa dữ liệu sẵn có, mỗi bản ghi insert có kích thước trung bình 1 KiB và dữ liệu được giữ trọn 30 ngày. Dung lượng phục vụ thật còn cần tính dữ liệu ban đầu, chỉ mục, overhead, snapshot/backup, retention, compression, biến động kích thước và headroom. Nếu lưu lượng chỉ xuất hiện vài giờ mỗi ngày thì không thể nhân thẳng tốc độ giờ cao điểm với 86.400 giây.

**Bước 4 — Kiểm tra điểm nóng.** Giả sử một sản phẩm nhận riêng 1.500 lượt đọc/giây. Dù cả cụm xử lý trung bình 6.000 thao tác/giây, shard chứa sản phẩm ấy vẫn có thể là nút thắt. Khi đó cần xem khả năng phục vụ khóa nóng, cache hit, độ trễ riêng của shard và phương án đọc phân tán; không thể kết luận hệ thống đủ sức chỉ vì tổng throughput còn thấp hơn capacity toàn cụm.

**Bước 5 — Chuyển phép tính thành yêu cầu kỹ thuật.** Hệ thống cần phục vụ hỗn hợp 80/20 ở mức bình thường, đạt đỉnh khoảng 18.000 thao tác/giây trong kịch bản đã nêu, chịu được khóa sản phẩm nóng và giữ dữ liệu theo chính sách 30 ngày. Các mốc độ trễ p95/p99, giới hạn lỗi, nhất quán và ngân sách phải do yêu cầu nghiệp vụ cung cấp trước khi kết luận một thiết kế hay sản phẩm CSDL đáp ứng được.

## 7. Thu thập dữ liệu workload trong thực tế

### 7.1. Bắt đầu từ hành động nghiệp vụ

Liệt kê những đường đi chính trong ứng dụng: xem chi tiết, tìm kiếm, thêm giỏ hàng, đặt đơn, ghi sự kiện, cập nhật trạng thái. Với mỗi đường đi, xác định số thao tác CSDL phát sinh, kích thước đầu vào/đầu ra, kiểu truy vấn và khóa được dùng.

Ví dụ một bảng đo:

| Hành động | Operation | Tần suất | Bản ghi liên quan | Khóa truy cập |
| --- | --- | ---: | --- | --- |
| Xem sản phẩm | Get by ID | 3.000/s | Metadata ~2 KiB | productId |
| Xem tồn kho | Get by ID | 2.000/s | State ~0,5 KiB | productId + warehouseId |
| Tìm sản phẩm | Query theo category | 800/s | Trang 20 kết quả | categoryId + sort |
| Cập nhật tồn kho | Conditional update | 400/s | State ~0,5 KiB | productId + warehouseId |
| Thu thập sự kiện | Batch insert | 100 batch/s | 100 event/batch | deviceId/timeBucket |

Ở dòng cuối, **100 batch/giây tương ứng 10.000 event/giây**, nhưng số request tới database và cách engine tính operation phụ thuộc API ghi theo lô. Do đó phải giữ cả số batch lẫn số phần tử/batch khi ước lượng.

### 7.2. Quan sát nhiều lớp

Các nguồn dữ liệu thường hữu ích:

- **Application tracing và log:** tên operation, collection, key đã ẩn danh/hash, số byte, latency, retry, cache hit.
- **Database metrics:** read/write throughput, scan efficiency, dung lượng, index size, IOPS, CPU, memory, replication lag, throttle, phân vùng nóng.
- **Query profiler hoặc slow query log:** truy vấn lọc/sắp xếp tốn kém, lượng dữ liệu quét, kế hoạch truy vấn, kết quả trả về.
- **Product analytics:** giờ cao điểm, chiến dịch, tenant lớn, hành vi làm bùng nổ tải.

Tránh ghi lộ nội dung nhạy cảm khi thu thập workload: thông thường chỉ cần tên trường, kích thước, loại thao tác và định danh khóa được băm/ẩn danh để thống kê phân bố.

Đọc dữ liệu theo **cửa sổ thời gian** (ví dụ phút, giờ, ngày), rồi phân nhóm theo loại truy vấn, partition key và tenant. Cần lưu cả trung bình và đỉnh vì workload có thể rất khác giữa thời điểm bình thường và flash sale.

### 7.3. Mẫu đặc tả workload để bàn giao thiết kế

Một bản mô tả ngắn có thể ghi dưới dạng YAML:

~~~yaml
workload:
  period: "peak-hour"
  operations_per_second:
    point_read: 4800
    range_read: 900
    insert: 300
    update: 800
    delete: 100
  payload:
    read_response_bytes:
      p50: 1024
      p95: 8192
      p99: 65536
    record_bytes:
      p50: 2048
      p95: 12288
      p99: 131072
  access:
    partition_key: "tenantId#entityId"
    top_1_percent_keys_read_share: 0.65
    largest_tenant_traffic_share: 0.20
    burst_multiplier: 3
  data_lifecycle:
    retention_days: 30
    expected_new_records_per_second: 300
  service_targets:
    read_p95_ms: 30
    write_p95_ms: 50
    consistency: "theo yêu cầu từng operation"
~~~

Các giá trị trên chỉ là **dữ liệu giả định để minh họa cấu trúc**; không phải ngưỡng khuyến nghị chung cho NoSQL. Trong dự án thật, cần ghi rõ phương pháp đo, nguồn số liệu và môi trường thu thập. Chú ý các loại read có thể có kích thước và latency khác nhau, nên đặc tả chi tiết hơn theo từng operation khi thiết kế.

## 8. Từ workload đến thử tải và lựa chọn công nghệ

Các giả thuyết về thiết kế cần được kiểm chứng bằng workload sát thực tế. Chạy cùng số lượng thao tác nhưng cấp khóa ngẫu nhiên đều, kích thước cố định 1 KiB và không có truy vấn range có thể cho kết quả đẹp mà không phản ánh ứng dụng đang có hot key, tài liệu lớn và những lần quét dữ liệu.

Một bộ thử tải có ý nghĩa gồm các tình huống độc lập:

1. **Bình thường:** phát sinh đúng tỷ lệ đọc/ghi, kích thước và truy vấn phổ biến.
2. **Đỉnh lưu lượng:** tăng tốc độ trong khoảng thời gian ngắn, quan sát latency p95/p99, lỗi, queue và throttling.
3. **Khóa nóng:** giữ nguyên tổng thông lượng nhưng dồn một phần request vào vài key/partition.
4. **Đuôi kích thước:** dùng cả bản ghi p95/p99, không chỉ bản ghi trung bình.
5. **Tăng trưởng:** thử ở mức dung lượng, số tenant, số index và retention gần trạng thái dự kiến.
6. **Đọc ngay sau ghi:** xác nhận kết quả có phù hợp yêu cầu nhất quán của nghiệp vụ.

Khi so sánh các hướng lưu trữ NoSQL (key–value, document, wide-column, search-oriented…), cần đối chiếu **mẫu truy cập chủ đạo và giới hạn đo được** với khả năng của từng sản phẩm. Không có kết luận rằng “đọc nhiều thì nhất định dùng document database” hoặc “ghi nhiều thì nhất định dùng wide-column”: khả năng thực tế còn phụ thuộc partitioning, indexing, replication, cách truy vấn, cấu hình và tài nguyên.

## 9. Những ngộ nhận cần tránh

| Nhận định dễ gây sai | Cách hiểu đúng |
| --- | --- |
| “80% đọc nên ghi không đáng quan tâm.” | 20% của throughput rất lớn vẫn có thể là tải ghi nặng; update và index có chi phí riêng. |
| “Bản ghi trung bình 2 KiB nên mọi lần đọc tốn 2 KiB.” | Query có thể lấy nhiều bản ghi, chỉ một phần trường hoặc phải đọc/quét thêm dữ liệu. |
| “Hash partition key là mọi partition đều cân bằng.” | Một khóa cực nóng hoặc tenant lớn vẫn có thể tạo điểm nghẽn. |
| “Cụm đạt 50.000 ops/s nghĩa là mọi workload 50.000 ops/s đều chạy được.” | Kích thước, mẫu query, phân bố khóa, consistency và burst quyết định throughput khả dụng. |
| “Ghi 1.000 bản ghi/s nghĩa là dung lượng luôn tăng 1.000 bản ghi/s.” | Update/delete không đồng nghĩa insert; TTL, retention và compression làm thay đổi dung lượng giữ lại. |
| “Thêm index luôn làm đọc nhanh hơn mà không ảnh hưởng gì.” | Index có chi phí lưu trữ, duy trì khi ghi và đôi khi không giúp truy vấn sai mẫu. |

Khi thiết kế NoSQL, **tỷ lệ đọc/ghi cho biết hệ thống phải làm công việc gì; kích thước bản ghi cho biết mỗi công việc mang theo bao nhiêu dữ liệu; phân bố truy cập cho biết công việc ấy dồn vào đâu và khi nào**. Chỉ khi kết hợp cả ba với độ trễ, nhất quán, vòng đời dữ liệu và mức tải đỉnh, ta mới có cơ sở chọn mô hình dữ liệu, partition key, chỉ mục, cache và phương án mở rộng phù hợp.
