# Phân vùng quá lớn, phân vùng quá nhỏ và điểm nóng

## 1. Vì sao kích thước và tải phân vùng quyết định chất lượng thiết kế cột rộng?

Trong cơ sở dữ liệu NoSQL **mô hình cột rộng (wide-column)**, cách tổ chức khóa thường quyết định dữ liệu được phân phối, sắp xếp và truy vấn như thế nào. Nếu thiết kế khóa không phù hợp, một cụm có nhiều nút vẫn có thể chậm do một phần dữ liệu quá lớn, quá nhiều phần dữ liệu vụn hoặc một vùng bị truy cập quá mức.

Ba vấn đề cần phân biệt:

- **Phân vùng quá lớn (oversized partition):** một khóa phân vùng gom quá nhiều hàng hoặc dữ liệu; thao tác đọc, ghi, nén/gộp, sao chép và sửa chữa trở nên tốn kém.
- **Phân vùng quá nhỏ (excessively small/tiny partitions):** dữ liệu bị chia thành quá nhiều đơn vị rất nhỏ so với mẫu truy cập; chi phí metadata, định vị và truy vấn qua nhiều phân vùng tăng lên.
- **Điểm nóng (hot partition/hotspot):** một phân vùng, khoảng khóa, replica hoặc nút phải xử lý lượng yêu cầu không cân xứng, kể cả khi dung lượng của nó chưa lớn.

**Kích thước và độ nóng là hai trục độc lập.** Một phân vùng có vài GB nhưng ít ai đọc có thể gây khó khăn khi sửa chữa mà chưa tạo tải tức thời lớn; một phân vùng chỉ vài MB nhưng nhận hàng chục nghìn ghi/giây có thể là điểm nóng nguy hiểm.

Bài học lấy **Apache Cassandra và CQL** làm ví dụ cụ thể cho hệ cột rộng có phân phối theo token của partition key, đồng thời chỉ ra những khác biệt cần lưu ý với các hệ dùng **dải khóa theo thứ tự** như Apache HBase hoặc Google Cloud Bigtable. Các ngưỡng, công cụ và bảo đảm cụ thể phụ thuộc phiên bản, cấu hình và dịch vụ đang sử dụng.

## 2. Nền tảng: partition key khác clustering key

Xét bảng lưu phép đo thiết bị:

~~~sql
CREATE TABLE measurements_by_device (
    device_id text,
    measured_at timestamp,
    measurement_id uuid,
    temperature_c double,
    PRIMARY KEY ((device_id), measured_at, measurement_id)
) WITH CLUSTERING ORDER BY (measured_at DESC, measurement_id DESC);
~~~

Trong mô hình CQL:

- **Partition key:** `device_id`, nằm trong cặp ngoặc `((device_id))`. Các hàng có cùng `device_id` thuộc cùng một **phân vùng logic** của bảng.
- **Clustering columns:** `measured_at` và `measurement_id`. Các hàng cùng partition được sắp xếp theo những cột này theo thứ tự khai báo.
- **Regular column:** `temperature_c`, chứa giá trị phép đo.

Ví dụ dữ liệu:

| device_id | measured_at | measurement_id | temperature_c |
|---|---|---|---:|
| sensor-01 | 2026-11-14T09:00:02Z | id-b | 29,2 |
| sensor-01 | 2026-11-14T09:00:01Z | id-a | 29,1 |
| sensor-02 | 2026-11-14T09:00:01Z | id-c | 30,1 |

Hai hàng của `sensor-01` cùng **một partition** vì có chung partition key; `sensor-02` thuộc partition khác. Clustering columns cho phép định vị và sắp xếp dữ liệu trong phạm vi partition.

~~~text
Bảng measurements_by_device

Partition key = sensor-01
  ├── (09:00:02, id-b) -> 29.2
  ├── (09:00:01, id-a) -> 29.1
  └── ... tiếp tục tăng theo thời gian

Partition key = sensor-02
  └── (09:00:01, id-c) -> 30.1
~~~

Với Cassandra, **token** được tính từ partition key để xác định các replica chịu trách nhiệm lưu dữ liệu theo chiến lược replication; một partition logic có thể tồn tại trên nhiều replica và trải qua nhiều SSTable trên đĩa. Không nên hình dung một partition luôn là một file vật lý duy nhất.

Mấu chốt của bài: **thay đổi clustering key không tự chia một partition thành nhiều partition**. Nếu chỉ dùng `device_id` làm partition key thì hàng triệu mốc thời gian của cùng thiết bị vẫn gom vào một partition logic.

### 2.1. Phân biệt partition với shard, replica và node

| Khái niệm | Chức năng | Cần nhớ |
|---|---|---|
| Partition logic | Tập hàng cùng giá trị partition key | Đơn vị truy vấn/sắp xếp quan trọng trong CQL |
| Token/range | Không gian dùng để định vị dữ liệu lên các nút | Cơ chế cụ thể phụ thuộc DBMS, partitioner và cấu hình |
| Replica | Bản sao của dữ liệu trên các nút theo chính sách replication | Tăng độ bền/sẵn sàng nhưng cũng tạo chi phí ghi và dung lượng |
| Node | Máy/tiến trình lưu trữ và phục vụ nhiều partition | Một node có thể nóng dù không có partition đơn lẻ cực lớn |
| Clustering row | Hàng bên trong một partition | Số hàng và kích thước hàng ảnh hưởng độ lớn partition |

Trên Cassandra, cùng một phân vùng có thể được lưu trên nhiều replica. Không nên tính mỗi replica thành một partition logic mới khi đánh giá số hàng theo partition key.

### 2.2. Các hệ cột rộng không phân phối dữ liệu giống nhau

Ở **Cassandra**, partition key thường được băm thành token và phân phối trên token ring; clustering key có thứ tự trong partition. Do đó một timestamp tăng trong **clustering column** của nhiều partition khác nhau không tự khiến mọi ghi dồn vào một node.

Ở những hệ **sắp đặt row key theo dải từ điển**, như HBase/Bigtable, các khóa liên tiếp có thể rơi vào cùng region/tablet. Nếu row key bắt đầu bằng timestamp hiện tại và các ghi tăng tuần tự, phần dải khóa mới nhất có thể thành hotspot.

Vì vậy, câu “khóa tăng theo thời gian gây nóng” cần hỏi tiếp: **DBMS phân phối theo hash hay theo range, và timestamp nằm ở partition key hay clustering key?**

## 3. Phân vùng quá lớn: dấu hiệu và nguyên nhân

### 3.1. Một khóa gom dữ liệu không có giới hạn

Với bảng `measurements_by_device` ở trên, mọi phép đo của một thiết bị nằm trong partition theo `device_id`. Nếu thiết bị phát liên tục trong nhiều năm, partition sẽ tăng mãi dù số lượng thiết bị trong hệ thống tăng hay giảm.

Giả sử một thiết bị ghi **10 sự kiện mỗi giây**. Trong một ngày:

~~~text
10 sự kiện/giây × 86.400 giây = 864.000 sự kiện/ngày

Giả sử mỗi sự kiện chiếm khoảng 350 byte trước khi
tính hết overhead lưu trữ, chỉ mục và hiệu ứng nén:

864.000 × 350 = 302.400.000 byte
               ≈ 302,4 MB / ngày / thiết bị
~~~

Nếu dùng `device_id` làm partition key mà không chia kỳ, chỉ sau một ngày đã có hàng trăm MB dữ liệu logic cho một thiết bị trong ví dụ này. Sau nhiều tháng, partition có thể rất lớn.

Đây là **phép tính minh họa để thiết kế**, không phải dự báo kích thước trên đĩa. Kích thước thực phụ thuộc serialization, số cột, clustering keys, tombstone, compression, chỉ mục, compaction và phiên bản DBMS.

### 3.2. Phân vùng lớn gây vấn đề ở đâu?

Một partition quá lớn có thể dẫn đến:

1. **Đọc và quét đắt đỏ:** truy vấn không giới hạn, truy vấn theo khoảng rộng hoặc thao tác duyệt nhiều clustering rows có thể phải xử lý lượng dữ liệu lớn.
2. **Độ trễ ở đuôi phân phối tăng:** một số truy vấn chạm partition lớn có thể chậm hơn rõ rệt, làm p95/p99 xấu đi dù tải trung bình vẫn thấp.
3. **Áp lực bộ nhớ và I/O:** nhiều dữ liệu được đọc, xử lý, phân trang hoặc lọc trong một partition.
4. **Chi phí compaction và tombstone:** xóa/TTL và gộp dữ liệu trong các SSTable có thể tăng tải; phân vùng lớn làm một số mẫu đọc trở nên khó kiểm soát.
5. **Streaming, repair và phục hồi khó hơn:** đơn vị dữ liệu lớn và nhiều phiên bản/tombstone có thể khiến thao tác phân phối, đồng bộ và sửa chữa tốn thời gian/tài nguyên.
6. **Tập trung tải ghi:** nếu dữ liệu mới của cùng partition được ghi liên tục với tần suất cao, partition lớn còn có thể là điểm nóng.

Không phải mọi lần đọc một partition lớn đều bắt buộc đọc hết partition. CQL có thể truy vấn giới hạn clustering range. Tuy nhiên, **thiết kế chỉ dựa vào khả năng đọc một dải nhỏ mà bỏ qua kích thước tích lũy cả đời vẫn có rủi ro vận hành**.

### 3.3. Không có một ngưỡng dung lượng tuyệt đối cho mọi hệ

Nhiều hướng dẫn triển khai Cassandra khuyến khích giữ partition ở kích thước có thể quản lý và cảnh báo khi partition phình lớn. Nhưng một con số như “100 MB” chỉ có thể là **mốc tham chiếu hoặc ngưỡng cảnh báo tùy phiên bản/workload**, không phải giới hạn cứng áp dụng cho mọi Cassandra, HBase hay Bigtable.

Nên đặt mục tiêu kích thước dựa trên:

- Bản ghi có độ lớn bao nhiêu và tăng nhanh thế nào.
- Mẫu truy vấn có thường quét một phần hay toàn partition.
- Tải ghi vào từng partition có cao không.
- Khả năng repair/streaming, compaction và thời gian phục hồi được phép.
- Giới hạn được nhà cung cấp/dịch vụ cụ thể công bố.
- Kiểm thử với dữ liệu, số replica và cấu hình gần thực tế.

## 4. Phân vùng quá nhỏ: tại sao “chia nhỏ nhất có thể” không đúng?

Một phản ứng trước partition quá lớn là đưa thêm nhiều trường vào partition key, tới mức **mỗi hàng thành một partition riêng**:

~~~sql
CREATE TABLE measurements_too_fragmented (
    device_id text,
    measured_at timestamp,
    measurement_id uuid,
    temperature_c double,
    PRIMARY KEY ((device_id, measured_at, measurement_id))
);
~~~

Nếu hầu hết tổ hợp đều duy nhất, một ngày của thiết bị có 864.000 sự kiện nghĩa là **864.000 partition logic** chỉ cho thiết bị đó.

### 4.1. Những chi phí thường bị bỏ quên

Với quá nhiều partition nhỏ:

- **Metadata và index:** mỗi partition có chi phí định vị, thông tin chỉ mục/metadata, Bloom filter hoặc cơ chế tương đương tùy engine.
- **Định vị nhiều lần:** để xem lịch sử một thiết bị theo khoảng, ứng dụng có thể phải truy vấn hàng nghìn hoặc hàng triệu partition nếu không có cấu trúc truy cập khác.
- **Fan-out và network round trip:** truy vấn qua nhiều partition có thể tạo nhiều tác vụ nội bộ/điều phối, tăng latency và áp lực coordinator.
- **Chi phí quản trị:** số lượng phân vùng cực lớn có thể ảnh hưởng thống kê, scan, backup, repair, compaction và kế hoạch truy vấn.
- **Thiếu lợi ích của clustering:** những sự kiện cùng thiết bị không còn nằm trong một dải clustering thuận tiện để lấy “100 sự kiện mới nhất”.

Tuy nhiên, **partition nhỏ không phải luôn xấu**. Một bảng tra cứu theo khóa chính mà mỗi khóa chứa một hồ sơ nhỏ, thường chỉ đọc đúng hồ sơ đó, có thể rất phù hợp. Vấn đề xảy ra khi **số partition, mẫu truy vấn và chi phí định vị** không còn khớp với yêu cầu.

### 4.2. Chi phí “nhiều partition nhỏ” và “nhiều hàng nhỏ” khác nhau

Một partition có thể chứa nhiều hàng nhỏ nhưng vẫn cho phép truy vấn theo clustering range; còn một bảng có cùng số hàng nhưng mỗi hàng là partition riêng cần chiến lược truy vấn khác.

Trong thiết kế cột rộng, không nên chỉ đếm **tổng số hàng**. Cần quan sát cả:

- Số partition logic.
- Phân bố số hàng trong một partition.
- Kích thước byte trung bình và lớn nhất mỗi partition.
- Bao nhiêu partition bị truy vấn trong một request.
- Tỷ lệ partition được đọc liên tục và partition hầu như không được truy cập.

Một hệ thống có 100 triệu partition nhỏ có thể hoạt động tốt nếu khối lượng và truy vấn được thiết kế để tra theo khóa riêng. Ngược lại, vài nghìn partition nhưng mỗi request phải quét tất cả cũng có thể không phù hợp.

## 5. Điểm nóng: tải tập trung dù phân vùng chưa lớn

**Hot partition** là phân vùng chịu lượng truy vấn hoặc ghi cao bất thường so với phần còn lại. **Hot node** là nút đang nhận tải vượt khả năng phục vụ; nguyên nhân có thể là một hoặc nhiều partition nóng, phân bố token không đều, thiếu tài nguyên, compaction hoặc traffic ứng dụng lệch.

Ví dụ một hệ có một triệu khách hàng nhưng gần như tất cả lượt truy cập đều nhằm vào `tenantId = "super-tenant"`. Nếu partition key chỉ là `tenantId`, phần lớn ghi của tenant này tập trung vào một partition logic và các replica của nó, cho dù cụm có rất nhiều nút.

### 5.1. Độ nóng phụ thuộc tốc độ, không chỉ dung lượng

Có thể có bốn trường hợp:

| Kích thước | Lưu lượng | Tình huống | Vấn đề chính |
|---|---|---|---|
| Nhỏ | Thấp | Cấu hình người dùng ít truy cập | Thường bình thường |
| Lớn | Thấp | Nhật ký lịch sử của một thiết bị hiếm khi được đọc | Khó xử lý kích thước, scan, repair hoặc lưu giữ |
| Nhỏ | Cao | Bộ đếm của một chiến dịch rất nổi tiếng | Tranh chấp/throughput tại khóa nóng |
| Lớn | Cao | Dòng sự kiện liên tục của một tenant rất lớn | Kết hợp vấn đề dung lượng và tải |

Một partition nhỏ có thể bị nóng ngay trong vài giây nếu hàng trăm nghìn client cùng cập nhật một bộ đếm. Ngược lại, một partition nhiều GB chưa chắc đang nóng theo số request/giây.

### 5.2. Những nguyên nhân phổ biến

- **Khóa phân vùng ít giá trị:** `status = "ACTIVE"`, `country = "VN"` hoặc `type = "CLICK"` thường có cardinality quá thấp khi dùng một mình.
- **Một tenant hoặc thiết bị nổi trội:** số lượt ghi/đọc của một khóa lớn hơn hàng nghìn lần khóa khác.
- **Tất cả ghi đổ vào bucket hiện tại:** partition theo `tenantId#day` bị quá tải trong ngày có sự kiện lớn.
- **Range sharding với khóa tăng:** trong HBase/Bigtable, row key bắt đầu bằng timestamp có thể làm vùng khóa mới nhất chịu hầu hết ghi.
- **Thao tác ghi tập trung vào một row/counter:** dù dữ liệu không lớn, cùng một khóa thường xuyên bị cập nhật.
- **Query thiếu giới hạn:** một màn hình liên tục lấy nhiều hàng từ cùng một partition.
- **Phân bố/hạ tầng không đều:** các replica, ổ đĩa hoặc mạng của vài node đã quá tải, khiến vùng dữ liệu đặt ở đó bị chậm.

### 5.3. Tại sao thêm nút chưa chắc giải quyết?

Nếu một partition chỉ được phục vụ bởi một tập replica nhất định, thêm node vào cluster không nhất thiết làm lưu lượng trên partition đó được chia đều ra tất cả node mới. Hệ có thể cân bằng token/range, nhưng **một khóa quá nóng vẫn chỉ có phạm vi phân phối hạn chế** theo mô hình dữ liệu và consistency.

Giải pháp thường phải điều chỉnh **partition key, bucketing, đường truy vấn hoặc kiến trúc ghi**, không chỉ tăng số máy.

## 6. Ba bài toán có thể nhìn bằng sơ đồ

~~~mermaid
flowchart TD
  A["Thiết kế partition key"] --> B{"Dữ liệu và tải phân bố thế nào?"}
  B --> C["Một khóa gom quá nhiều hàng"]
  B --> D["Mỗi hàng thành một partition"]
  B --> E["Một khóa nhận phần lớn request"]
  C --> C1["Oversized partition: kích thước lớn"]
  D --> D1["Tiny partitions: số partition quá lớn, truy vấn fan-out"]
  E --> E1["Hot partition: tập trung lưu lượng"]
  C1 --> F["Thiết kế bucket/retention theo thời gian"]
  D1 --> G["Nhóm theo truy vấn và clustering key"]
  E1 --> H["Chia tải bằng khóa đủ đa dạng, hash bucket hoặc đường ghi khác"]
~~~

Sơ đồ mô tả các hướng xử lý thường gặp. Một lựa chọn như time bucket có thể giảm kích thước partition, nhưng nếu tất cả lưu lượng vẫn đổ vào **bucket hiện tại**, điểm nóng chưa được giải quyết. Hash bucket có thể giảm nóng nhưng buộc truy vấn đọc nhiều bucket rồi ghép.

## 7. Chọn partition key từ mẫu truy cập

Trước khi tạo bảng, cần xác định:

1. **Truy vấn chính là gì?** Lấy sự kiện của một thiết bị trong ngày, lịch sử một khách hàng hay toàn bộ sự kiện của một tenant?
2. **Partition key có đủ giá trị phân biệt?** Các giá trị có phân bố tương đối đều hay một vài khóa chiếm gần hết lưu lượng?
3. **Có thể giới hạn tốc độ tăng mỗi partition?** Tốc độ ghi trung bình và cao điểm nhân với thời gian lưu giữ cho ra khối lượng bao nhiêu?
4. **Clustering key hỗ trợ lọc/sắp xếp nào?** Có cần mới nhất trước, khoảng thời gian hay thứ tự ổn định khi timestamp trùng?
5. **Một request sẽ chạm bao nhiêu partition?** Có thể truy vấn trong một partition hay phải fan-out?
6. **Dữ liệu có thời điểm hết hạn nào?** Retention, TTL và dữ liệu đến trễ ảnh hưởng cách tạo bucket ra sao?
7. **Mức consistency và replication nào được dùng?** Chi phí đọc/ghi tại replica phụ thuộc yêu cầu xác nhận và cấu hình cụ thể.

Không nên chọn partition key bằng cách lấy ngẫu nhiên một cột có tên “ID”. Một khóa có cardinality cao nhưng không phù hợp truy vấn có thể tạo rất nhiều partition nhỏ và buộc ứng dụng quét nhiều nơi.

## 8. Time bucketing: giới hạn dung lượng theo kỳ

Với luồng dữ liệu theo thời gian, một cách thiết kế thường gặp là thêm **time bucket** vào partition key.

Thay vì:

~~~text
Partition key = deviceId
Clustering    = measuredAt, measurementId
~~~

Có thể dùng:

~~~text
Partition key = (deviceId, eventDay)
Clustering    = measuredAt, measurementId
~~~

Mỗi thiết bị có partition mới theo ngày. Khi dữ liệu lưu 90 ngày, có thể ước tính số partition và kích thước từng ngày để chọn thời hạn phù hợp.

### 8.1. Ví dụ bảng CQL theo ngày

~~~sql
CREATE TABLE measurements_by_device_day (
    device_id text,
    event_day date,
    measured_at timestamp,
    measurement_id uuid,
    temperature_c double,
    PRIMARY KEY ((device_id, event_day), measured_at, measurement_id)
) WITH CLUSTERING ORDER BY (measured_at DESC, measurement_id DESC);
~~~

Trong thiết kế này:

- `(device_id, event_day)` là **composite partition key**.
- Một partition chứa các phép đo của **một thiết bị trong một ngày**.
- `measured_at` và `measurement_id` là clustering columns.
- `measurement_id` là một thành phần phân biệt các hàng có thời gian đo trùng, cần ổn định qua retry nếu muốn ghi lại cùng khóa.

Ví dụ truy vấn một ngày:

~~~sql
SELECT measured_at, measurement_id, temperature_c
FROM measurements_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-14'
ORDER BY measured_at DESC
LIMIT 100;
~~~

Đây là truy vấn phục vụ **một partition**; nếu phải lấy dữ liệu kéo dài 7 ngày, ứng dụng cần đọc những ngày liên quan rồi ghép kết quả, hoặc dùng một mô hình truy vấn khác được thiết kế rõ.

### 8.2. Chọn bucket theo giờ, ngày hay tháng

Một cách ước lượng sơ bộ:

~~~text
rowsPerBucket = avgRowsPerSecond × secondsPerBucket

estimatedBytesPerBucket =
    rowsPerBucket × avgSerializedRowBytes + estimatedOverhead
~~~

Với 10 sự kiện/giây, 350 byte/sự kiện:

| Bucket | Số sự kiện minh họa | Dữ liệu tính từ 350 byte/hàng, chưa tính overhead |
|---|---:|---:|
| 1 phút | 600 | 0,21 MB |
| 1 giờ | 36.000 | 12,6 MB |
| 1 ngày | 864.000 | 302,4 MB |
| 30 ngày | 25.920.000 | 9.072 MB |

Khi chọn bucket, phải dùng **tải đỉnh và phân bố thiết bị thực tế**, không chỉ trung bình. Thiết bị bình thường ghi một lần/phút nhưng một thiết bị đặc biệt ghi 1.000 lần/giây có thể tạo partition cực lớn ngay cả với bucket theo giờ.

Không nên suy ra bucket 1 giờ là lựa chọn mặc định cho mọi hệ. Bucket quá ngắn lại làm tăng số partition và chi phí truy vấn xuyên kỳ.

### 8.3. Time bucket giảm kích thước nhưng chưa chắc giảm nóng

Giả sử một cảm biến ghi 50.000 sự kiện mỗi giây:

~~~text
(sensor-99, 2026-11-14T09) -> mọi ghi từ 09:00 đến 09:59
~~~

Partition theo giờ có thể chỉ tồn tại trong một giờ, nhưng **mọi yêu cầu ghi cùng giờ vẫn vào một partition logic**. Nó vẫn có thể là hot partition.

Khi gặp trường hợp đó, cần xét thêm hash bucketing hoặc chia nguồn ghi thành nhiều phạm vi độc lập.

## 9. Hash bucketing/salting: chia tải cho khóa nóng

**Hash bucketing** thêm một thành phần phân vùng dựa trên giá trị băm ổn định. Ví dụ:

~~~text
Partition key = (deviceId, eventDay, bucket)
bucket       = stableHash(measurementId) mod 16
Clustering   = measuredAt, measurementId
~~~

Các phép đo của cùng thiết bị và ngày được trải ra **16 partition logic**. Nếu ID có phân bố phù hợp, lưu lượng ghi có thể chia đều hơn.

### 9.1. CQL cho mô hình kết hợp ngày và bucket

~~~sql
CREATE TABLE measurements_by_device_day_bucket (
    device_id text,
    event_day date,
    bucket tinyint,
    measured_at timestamp,
    measurement_id uuid,
    temperature_c double,
    PRIMARY KEY (
        (device_id, event_day, bucket),
        measured_at,
        measurement_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    measurement_id DESC
);
~~~

Với `bucket` có giá trị từ 0 đến 15, một truy vấn đọc một bucket:

~~~sql
SELECT measured_at, measurement_id, temperature_c
FROM measurements_by_device_day_bucket
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-14'
  AND bucket = 3
  AND measured_at >= '2026-11-14T08:00:00Z'
  AND measured_at <  '2026-11-14T09:00:00Z'
LIMIT 100;
~~~

Truy vấn này có đủ các thành phần partition key và giới hạn clustering range. Để lấy **100 phép đo mới nhất trên toàn bộ 16 bucket**, ứng dụng không thể xem kết quả từ bucket 3 là đầy đủ. Nó phải đọc các bucket liên quan rồi **merge theo cặp khóa (measured_at, measurement_id)**, có cursor hoặc cách phân trang nhất quán giữa các bucket.

### 9.2. Tính bucket phải ổn định qua retry

Ví dụ Java về mặt ý tưởng:

~~~java
int bucketCount = 16;
int bucket = Math.floorMod(measurementId.hashCode(), bucketCount);
~~~

Nếu `measurementId` là định danh ổn định của phép đo, cùng phép đo được gửi lại sẽ cho cùng bucket. Nếu mỗi lần retry sinh ID ngẫu nhiên mới, phép đo có thể đi vào bucket khác và bị ghi trùng.

Trong hệ nhiều ngôn ngữ lập trình hoặc cần ổn định sau thay đổi phiên bản, phải **chỉ định thuật toán băm và encoding thống nhất**. Không thể mặc định mọi ngôn ngữ tạo cùng hash code cho một UUID hoặc chuỗi.

Một lựa chọn khác là lưu `bucket` như thuộc tính đã được xác định khi nhận sự kiện lần đầu và truyền ổn định trong mọi thao tác tiếp theo.

### 9.3. Cái giá phải trả khi chia hash bucket

- Mỗi ngày của một thiết bị có nhiều partition hơn, làm tăng số partition toàn hệ.
- Truy vấn “mới nhất” phải fan-out đến nhiều bucket và ghép thứ tự.
- Dữ liệu cũ có thể dùng số bucket khác dữ liệu mới nếu chiến lược thay đổi; ứng dụng phải biết phiên bản quy tắc.
- Khi một bucket mất cân bằng do hàm băm hoặc dữ liệu, điểm nóng vẫn có thể xảy ra.
- Dùng bucket theo số ngẫu nhiên mới cho mỗi lần ghi sẽ phá tính xác định của truy vấn và làm idempotency khó hơn.

**Hash bucket là công cụ đánh đổi giữa phân tán ghi và chi phí đọc**. Hãy thêm khi đo được tải tập trung thực sự hoặc khi dự báo dung lượng yêu cầu, không thêm số bucket lớn một cách mặc định.

## 10. So sánh ba thiết kế khóa cho cùng bài toán

Giả sử truy vấn chính là “lấy 100 phép đo mới nhất của một thiết bị”.

| Thiết kế | Partition key | Ưu điểm | Vấn đề tiềm ẩn |
|---|---|---|---|
| A: không chia kỳ | `deviceId` | Một partition để lấy lịch sử thiết bị | Partition tăng không giới hạn; thiết bị nóng gây quá tải |
| B: theo ngày | `(deviceId, eventDay)` | Giới hạn kích thước theo kỳ, dễ truy vấn trong ngày | Ngày hiện tại vẫn nóng; truy vấn nhiều ngày cần ghép |
| C: theo ngày + bucket | `(deviceId, eventDay, bucket)` | Chia thêm lưu lượng của thiết bị nóng | Fan-out khi đọc; thêm chi phí metadata và hợp nhất kết quả |

Ví dụ minh họa phân bố:

~~~text
A. Không bucket:
sensor-01
  └── [rất nhiều sự kiện qua nhiều năm]

B. Time bucket:
sensor-01#2026-11-13
sensor-01#2026-11-14
sensor-01#2026-11-15

C. Time + hash bucket:
sensor-01#2026-11-14#00
sensor-01#2026-11-14#01
...
sensor-01#2026-11-14#15
~~~

Càng phân mảnh nhiều, tải ghi có thể phân bố tốt hơn nhưng việc đọc một danh sách có thứ tự trên toàn bộ các phần trở nên phức tạp hơn. Vì thế phải thiết kế **cả hai đường đọc và ghi** trước khi chọn khóa.

## 11. Khi nào số bucket là quá nhiều hoặc quá ít?

Một hệ thống với 100.000 thiết bị, mỗi thiết bị một partition/ngày, có thể tạo khoảng 100.000 partition mới mỗi ngày nếu tất cả đều hoạt động. Nếu thêm 16 bucket **cho mọi thiết bị**, số partition có dữ liệu sẽ tùy theo phân bố sự kiện; với thiết bị đủ dữ liệu để chạm mọi bucket, có thể tăng lên 1,6 triệu partition/ngày.

Trong khi đó, đa số thiết bị có thể chỉ ghi vài chục phép đo một ngày. Với những thiết bị này, 16 bucket không giúp đáng kể nhưng làm truy vấn phức tạp hơn.

Có thể cân nhắc:

- Chỉ dùng **time bucket** cho nhóm thiết bị tải thấp và trung bình.
- Thiết kế **mẫu riêng cho thiết bị siêu nóng** nếu sản phẩm và ứng dụng chấp nhận nhiều đường ghi/đọc.
- Chọn **số bucket theo lưu lượng cực đại** và mức fan-out có thể chấp nhận, không chỉ theo khả năng đánh số bucket.
- Giới hạn số partition phải đọc trên một request; có thể dùng mô hình truy vấn phụ nếu cần nhiều hướng truy cập.
- Xác định **chính sách chuyển đổi số bucket**: thay đổi từ 4 sang 16 không tự làm dữ liệu cũ di chuyển sang khóa mới.

Không nên tính số partition chỉ từ số tổ hợp lý thuyết nếu nhiều tổ hợp rỗng. Thay vào đó, cần ước lượng số partition **có dữ liệu** theo phân bố traffic.

## 12. Hotspot trên hệ theo dải khóa: sự khác biệt quan trọng

Trong Cassandra, partition key thường được hash trước khi xác định vị trí token; một khóa timestamp tăng không nhất thiết làm mọi partition chạy vào “node cuối”.

Trong HBase/Bigtable, row key được sắp theo thứ tự từ điển và các vùng dải khóa có thể được phân cho region/tablet. Ví dụ row key:

~~~text
20261114T090000000Z#sensor-01
20261114T090000001Z#sensor-34
20261114T090000002Z#sensor-12
...
~~~

Các khóa mới có tiền tố timestamp gần nhau liên tục đi vào phần cuối của không gian khóa; một vùng mới nhất có thể nhận phần lớn lưu lượng ghi.

Một số chiến lược trong hệ range-partitioned:

- Đưa **mã thiết bị/tenant** hoặc thành phần phân tán có ý nghĩa lên trước timestamp.
- Dùng **hash prefix/salt** trước timestamp để chia dữ liệu thành nhiều dải.
- Dùng **reverse timestamp** khi cần quét mới nhất trước, nhưng vẫn phải xét độ nóng của dải khóa.
- Thiết kế row key theo **truy vấn chủ đạo**, không chỉ theo mong muốn ghi tuần tự.
- Kiểm tra giới hạn của chính dịch vụ: số region/tablet, splitting, hotspot và quy tắc phân bố của phiên bản hiện hành.

Ví dụ row key có hash prefix:

~~~text
03#sensor-01#20261114T090000000Z
11#sensor-34#20261114T090000001Z
07#sensor-12#20261114T090000002Z
~~~

Hash prefix có thể chia tải, nhưng một truy vấn theo thời gian toàn cụm phải đọc nhiều dải và ghép dữ liệu. Số lượng prefix và quy tắc tính cần ổn định, đồng thời phải tương thích cách tạo region/tablet của DBMS.

Không nên áp dụng máy móc “salting row key” của Bigtable cho mọi bảng Cassandra: kỹ thuật cụ thể và cơ chế phân phối có thể khác nhau.

## 13. TTL, tombstone và kích thước phân vùng

Với dữ liệu sự kiện, thường cần giới hạn thời gian lưu trữ bằng TTL. Ví dụ ghi một phép đo trong Cassandra:

~~~sql
INSERT INTO measurements_by_device_day (
    device_id,
    event_day,
    measured_at,
    measurement_id,
    temperature_c
) VALUES (
    'sensor-01',
    '2026-11-14',
    '2026-11-14T09:00:02Z',
    11111111-1111-4111-8111-111111111111,
    29.2
) USING TTL 2592000;
~~~

`2592000` giây tương đương **30 ngày**. Trong Cassandra, dữ liệu hết hạn không nhất thiết bị loại khỏi mọi SSTable ngay tại giây hết hạn. Xóa và TTL tạo ra cơ chế đánh dấu hết hạn/tombstone mà hệ phải xử lý an toàn trong quá trình compaction và repair.

### 13.1. TTL không biến một partition vô hạn thành thiết kế tốt

Một partition gồm nhiều năm dữ liệu có thể vẫn có chi phí tombstone và truy vấn khó đoán trước khi các bản ghi cũ được xử lý. Việc giữ hàng mới trong cùng partition, ghi/xóa liên tục và các bản cập nhật đến muộn có thể ảnh hưởng hiệu quả compaction.

Bucket theo thời gian giúp đặt ranh giới kích thước và vòng đời rõ hơn, nhưng TTL vẫn cần được cấu hình và quan sát đúng.

### 13.2. Tombstone ảnh hưởng đường đọc

Khi một query phải quét nhiều dữ liệu đã bị xóa/hết hạn để tìm những hàng còn sống, độ trễ có thể tăng và DBMS có thể phát cảnh báo tombstone theo cấu hình.

Các thao tác cần xem xét:

- Mẫu xóa hoặc TTL có tạo quá nhiều tombstone tại vùng clustering được quét không?
- Khoảng dữ liệu truy vấn có đi qua phần lịch sử đã hết hạn không?
- Chiến lược compaction có phù hợp với workload thời gian, TTL và dữ liệu đến trễ không?
- Repair và thời gian lưu tombstone được vận hành ra sao để tránh phục hồi dữ liệu đã xóa không đúng mong muốn?

Trong Cassandra có các chiến lược compaction khác nhau, trong đó **TimeWindowCompactionStrategy (TWCS)** thường được cân nhắc cho dữ liệu thời gian có TTL và mô hình ghi phù hợp. Tuy nhiên, TWCS có các giả định/vấn đề riêng về cập nhật, timestamp và dữ liệu đến muộn; không nên đổi chiến lược chỉ vì bảng có cột thời gian.

### 13.3. Dữ liệu đến trễ và kỳ phân vùng

Một thiết bị offline gửi bù sự kiện đo từ tuần trước. Nếu `event_day` trong khóa lấy từ `measured_at`, sự kiện sẽ được ghi vào **partition của tuần trước**, không phải partition ngày nhận.

Điều này có thể phù hợp để truy vấn theo thời gian đo, nhưng ảnh hưởng:

- Dữ liệu cũ được ghi bổ sung sau khi partition tưởng đã ít thay đổi.
- TTL tính từ **thời điểm ghi** nếu áp dụng TTL lúc ghi, nên retention theo “30 ngày từ thời gian đo” cần được xử lý riêng.
- Compaction theo cửa sổ thời gian có thể chịu ảnh hưởng bởi dữ liệu đến muộn và timestamp ghi.
- Nếu client báo giờ sai, sự kiện có thể rơi vào bucket tương lai/quá khứ không mong muốn.

Cần quyết định phân vùng theo **event time** hay **ingestion time** dựa trên truy vấn, độ tin cậy đồng hồ và retention. Có thể cần giữ cả hai thời gian trong dữ liệu.

## 14. Quan sát đúng các dấu hiệu trước khi sửa thiết kế

Chỉ nhìn CPU trung bình của cluster là chưa đủ. Một vài partition nóng có thể làm một số request rất chậm trong khi tài nguyên tổng thể chưa bị sử dụng hết.

### 14.1. Các chỉ số cần quan sát

| Nhóm | Cần tìm gì? | Ý nghĩa |
|---|---|---|
| Partition size | Kích thước trung bình, lớn nhất, phân vị cao, tốc độ tăng | Phát hiện partition vô hạn hoặc ngoại lệ |
| Rows per partition | Số hàng trung bình, lớn nhất, phân bố theo tenant/device | Giải thích kích thước và cardinality |
| Read/write latency | p50, p95, p99 theo bảng, endpoint và nhóm khóa | Nhận diện tác động người dùng |
| Throughput | Request/giây theo partition key, tenant hoặc node | Phát hiện skew và hot key |
| Resource | CPU, disk I/O, network, heap, cache, compaction backlog | Xác định nút thắt tài nguyên |
| Tombstone | Cảnh báo/lượt quét tombstone và truy vấn liên quan | Phát hiện chi phí đọc dữ liệu hết hạn/xóa |
| SSTable/read path | SSTable touched/read, cache hit và đường truy vấn | Nhận diện read amplification |
| Coordinator/fan-out | Số partition chạm trên một request, timeout, paging | Phát hiện mô hình tiny partitions gây quét nhiều nơi |
| Replica/repair | Độ trễ đồng bộ, lỗi repair, streaming và dung lượng | Đánh giá tính bền vững khi mở rộng hoặc phục hồi |

Tên metric và cách thu thập tùy DBMS. Ở Cassandra có thể dùng metric của node, tracing, công cụ thống kê SSTable/partition và các cơ chế xác định truy vấn/partition nóng tùy phiên bản hoặc nền tảng giám sát. Không nên dựa vào một lệnh cụ thể như một API ổn định cho mọi bản phát hành.

### 14.2. Đọc distribution thay vì chỉ average

Giả sử 99% partition có 3 MB, 1% partition có 800 MB. Trung bình có thể trông chấp nhận được nhưng nhóm 1% dễ gây sự cố.

Tương tự, tổng throughput 100.000 ops/giây có thể phân bố đều hoặc tập trung 80.000 ops vào một tenant. Hai hệ có cùng tổng throughput nhưng khác hẳn nguy cơ nóng.

Nên xem **top partition theo kích thước**, **top key theo tốc độ truy cập** và **p99 latency gắn với các key/tenant lớn**.

### 14.3. Đo cả đọc và ghi

Một thiết kế hash bucket có thể giảm p99 ghi nhưng tăng p99 đọc do phải fan-out và merge kết quả từ nhiều bucket. Cần đo **cả đường đọc, ghi, xóa, backup/repair và migration**, không chỉ một chỉ số được cải thiện.

## 15. Quy trình xử lý partition quá lớn

Giả sử hệ đang dùng `PRIMARY KEY ((device_id), measured_at, measurement_id)`, và một số thiết bị có partition nhiều GB.

Hướng xử lý theo thứ tự:

1. **Đo kích thước và tăng trưởng:** những thiết bị nào tạo dữ liệu nhiều, tốc độ ghi và retention hiện tại ra sao.
2. **Xem mẫu truy vấn:** lấy mới nhất, quét ngày, truy vấn theo sự kiện hay phân tích lịch sử nhiều năm?
3. **Chọn time bucket:** ngày hoặc giờ dựa trên kích thước dự kiến của thiết bị lớn nhất và số partition cần đọc.
4. **Xem khả năng nóng của bucket hiện tại:** nếu tải ghi vẫn tập trung, cân nhắc thêm hash bucket.
5. **Thiết kế bảng truy vấn mới:** Cassandra thường thích mô hình bảng theo access pattern; tránh kỳ vọng truy vấn tùy ý xuyên partition rẻ.
6. **Xây kế hoạch di chuyển dữ liệu:** backfill dữ liệu lịch sử, duy trì ghi/đọc chuyển tiếp theo cơ chế có thể kiểm soát, so sánh độ đầy đủ rồi chuyển traffic.
7. **Theo dõi sau chuyển đổi:** p95/p99, kích thước partition mới, số partition trong một request, độ trễ repair và tombstone.

Không thể đổi **partition key của dữ liệu hiện hữu** bằng cách sửa tên một cột rồi kỳ vọng hệ thống tự phân phối lại theo thiết kế mới. Thường cần tạo bảng/mô hình mới và di chuyển dữ liệu có kiểm soát.

## 16. Quy trình xử lý quá nhiều partition nhỏ

Giả sử mỗi sự kiện là một partition và màn hình “lịch sử 24 giờ của sensor-01” phải lấy rất nhiều khóa.

Hướng khắc phục:

1. Xác định truy vấn nào đang fan-out đến nhiều partition và số partition trung bình/cao điểm mỗi request.
2. Xác định **đơn vị nhóm tự nhiên**: một thiết bị trong một giờ/ngày, một tenant trong kỳ hoặc một nhóm sự kiện có giới hạn.
3. Đặt các hàng liên quan cùng **composite partition key**; dùng clustering columns để hỗ trợ khoảng thời gian và thứ tự.
4. Giữ giới hạn kích thước bằng time bucket hoặc bounded group, tránh chuyển từ quá nhỏ sang quá lớn.
5. Chuyển dữ liệu sang bảng mới và điều chỉnh API phân trang, cursor và các truy vấn liên quan.
6. Đo số partition/request, số hàng/partition, dung lượng và độ trễ trước/sau.

Một bảng lookup riêng theo `measurement_id` vẫn có thể tồn tại để phục vụ yêu cầu “lấy đúng một phép đo bằng ID”. Trong hệ cột rộng, **nhiều bảng được thiết kế theo các truy vấn khác nhau** có thể là lựa chọn hợp lý, dù tạo chi phí đồng bộ giữa các bảng.

## 17. Quy trình xử lý hot partition

Nếu một tenant ghi quá nhiều dữ liệu vào bucket trong ngày:

1. **Tìm điểm nóng thực sự:** partition key cụ thể, node/replica, loại thao tác và thời điểm tải cao.
2. **Phân biệt nóng vì kích thước hay vì traffic:** xem bytes/partition và ops/s theo partition.
3. **Kiểm tra thao tác ghi chung một row/counter:** nếu vậy, chia partition theo ngày có thể không đủ; cần phân phối cập nhật theo nhiều khóa có thể tổng hợp.
4. **Cân nhắc hash buckets theo ID ổn định:** tăng số partition nhận ghi trong cùng kỳ.
5. **Tính chi phí đọc lại:** mỗi truy vấn cần đọc bao nhiêu bucket, merge như thế nào, có cần bảng đọc phụ?
6. **Đánh giá consistency và retry:** dữ liệu ghi hai lần vào hai bucket do bucket không ổn định có thể khiến mất tính đúng đắn.
7. **Thử trên dữ liệu skew gần thực tế:** đo p99, compaction, tải replica và số request song song khi fan-out.

Nếu một tài liệu/bộ đếm liên tục được cập nhật bởi nhiều nguồn, giải pháp có thể là **sharded counter** hoặc phân phối bộ đếm rồi tổng hợp, với đánh đổi về độ trễ và nhất quán kết quả. Không nên tự tạo nhiều bản sao một giá trị duy nhất rồi cộng lại nếu nghiệp vụ cần một ràng buộc giao dịch chặt như tồn kho không được âm.

## 18. Migration: thay đổi partition key cần đi đôi với định danh ổn định

Ví dụ từ bảng cũ:

~~~text
old: partition = deviceId
     clustering = measuredAt, measurementId
~~~

Sang bảng mới:

~~~text
new: partition = (deviceId, eventDay, bucket)
     clustering = measuredAt, measurementId
~~~

Phải xác định rõ:

- `eventDay` được tính từ `measuredAt` theo UTC hay từ `ingestedAt`?
- `bucket` được tính từ thuộc tính ổn định nào, và bao nhiêu bucket?
- Sự kiện gửi lại sẽ vào **đúng một partition và một primary key** như lần trước chứ?
- Truy vấn cũ lấy lịch sử nhiều năm sẽ đổi như thế nào?
- Khi backfill và traffic mới cùng chạy, đâu là nguồn dữ liệu đáng tin cho mỗi giai đoạn?

Một kế hoạch chuyển đổi có thể gồm:

~~~mermaid
flowchart LR
  A["Thiết kế khóa mới và truy vấn"] --> B["Tạo bảng mới"]
  B --> C["Backfill dữ liệu lịch sử"]
  C --> D["Đồng bộ các ghi phát sinh trong lúc chuyển"]
  D --> E["Đối chiếu dữ liệu và đo tải"]
  E --> F["Chuyển đường đọc"]
  F --> G["Ngừng đường ghi cũ khi an toàn"]
~~~

Sơ đồ chỉ mô tả ý tưởng. Thứ tự triển khai backfill/dual-write/change capture tùy hệ. Với dữ liệu có yêu cầu mạnh về nhất quán, cần thiết kế cụ thể trạng thái chuyển tiếp, xử lý lỗi, retry và tiêu chí đối chiếu; không mặc định dual-write đơn giản đảm bảo nguyên tử giữa hai bảng.

### 18.1. Idempotency khi ghi lại

Nếu `measurementId` được tạo ổn định một lần ở nguồn và cả `eventDay` lẫn `bucket` được tính nhất quán, retry có thể truy cập cùng primary key trong bảng CQL. Nếu mỗi retry sinh `measurementId` mới hoặc chọn bucket ngẫu nhiên, một phép đo có thể trở thành nhiều hàng.

Đồng thời, **khóa ổn định chỉ giúp nhận diện một bản ghi**. Nó không tự giải quyết mọi xung đột về payload, timestamp ghi, TTL hoặc cập nhật đồng thời; cần quy định hành vi ghi đè, version và consistency phù hợp.

## 19. Bài tập: thiết kế bảng sự kiện đa tenant

Một nền tảng có 10.000 tenant:

- 9.900 tenant nhỏ, mỗi tenant có trung bình 20 sự kiện/phút.
- 99 tenant trung bình, mỗi tenant có 1.000 sự kiện/giây vào cao điểm.
- 1 tenant lớn, cao điểm có thể tạo 50.000 sự kiện/giây.
- Dữ liệu phải giữ 90 ngày.
- API thường lấy 100 sự kiện mới nhất của **một tenant**.
- Một số truy vấn cần lấy sự kiện trong 24 giờ gần nhất.
- Có sự kiện gửi lại sau lỗi mạng; ID nghiệp vụ phải ổn định.

### 19.1. Các phương án thử chọn

**Phương án A**

~~~sql
PRIMARY KEY ((tenant_id), event_time, event_id)
~~~

**Phương án B**

~~~sql
PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
~~~

**Phương án C**

~~~sql
PRIMARY KEY ((tenant_id, event_day, bucket), event_time, event_id)
~~~

**Câu hỏi:**

1. Phương án nào dễ tạo partition lớn theo thời gian?
2. Phương án B có đủ cho tenant 50.000 sự kiện/giây không?
3. Với phương án C, nếu dùng 32 bucket, một API lấy 100 sự kiện mới nhất phải làm gì?
4. Có nên dùng cùng số bucket cho tenant nhỏ và tenant lớn?
5. TTL 90 ngày có thay thế việc chọn kích thước bucket không?
6. Những metric nào giúp kiểm tra phương án được chọn?

### 19.2. Hướng phân tích

- A gom toàn bộ lịch sử theo tenant: có nguy cơ kích thước không giới hạn và một tenant lớn tạo hot partition.
- B cắt theo ngày, giúp chặn tăng trưởng theo lịch sử nhưng **ngày hiện tại của tenant lớn vẫn có thể rất nóng**.
- C chia tải theo bucket ổn định, nhưng với 32 bucket phải đọc những bucket liên quan rồi **hợp nhất có thứ tự** để biết 100 sự kiện mới nhất. Mỗi bucket cũng phải có pagination/cursor nếu muốn đọc liên tục.
- Dùng 32 bucket cho tất cả tenant có thể khiến 9.900 tenant nhỏ bị chia quá vụn so với nhu cầu. Có thể cần profile tải hoặc chính sách số bucket theo nhóm tenant, song phải thiết kế định tuyến và thay đổi cấu hình an toàn.
- TTL là chính sách xóa/hết hạn; không tự đảm bảo partition hiện tại nhỏ hoặc không nóng.
- Cần đo độ lớn partition, số partition/request, p95/p99 đọc/ghi, tỷ lệ skew, CPU/I/O từng replica, compaction, tombstone, lỗi và chi phí fan-out.

**Ước tính nhanh cho tenant rất lớn:** 50.000 sự kiện/giây × 86.400 giây = 4,32 tỷ sự kiện/ngày. Với 300 byte/sự kiện, riêng dữ liệu logic trước overhead khoảng **1.296 GB/ngày**. Chỉ bucket theo ngày rõ ràng chưa hợp lý cho mức tải minh họa này; ngay cả 32 bucket cũng còn khoảng 40,5 GB dữ liệu logic/bucket/ngày nếu phân bố đều. Phải tính thêm chính sách lưu trữ, dung lượng node, throughput, cách chia phạm vi và cả khả năng tách luồng ingestion trước khi quyết định.

Những con số trên là **bài tính giả định** nhằm cho thấy vì sao việc chọn bucket phải xuất phát từ công suất và kích thước thật, không phải lời khuyên về một ngưỡng chuẩn cho Cassandra.

## 20. Những ngộ nhận dễ gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Một bảng wide-column có thể chứa vô hạn hàng trong một partition mà không có đánh đổi.” | Khả năng lưu trữ không thay thế giới hạn vận hành của scan, compaction, repair, tombstone và hot key. |
| “Thêm clustering column là tự chia nhỏ partition.” | Clustering chỉ tổ chức hàng **trong** partition; partition key mới quyết định nhóm dữ liệu. |
| “Partition nhỏ luôn tốt.” | Quá nhiều partition cực nhỏ có thể tăng metadata và chi phí truy vấn fan-out. |
| “Partition lớn luôn là điểm nóng.” | Kích thước và tải truy cập là hai trục khác nhau; partition nhỏ cũng có thể rất nóng. |
| “Chỉ cần thêm node sẽ xử lý mọi hot partition.” | Một khóa nóng vẫn có phạm vi replica/phân phối hạn chế; có thể cần thay mô hình key hoặc đường ghi. |
| “Time bucket luôn giải quyết hotspot.” | Mọi ghi trong bucket hiện tại vẫn có thể đổ vào cùng partition. |
| “Hash bucket càng nhiều càng tốt.” | Bucket nhiều làm tăng số partition và chi phí đọc/merge; cần cân bằng. |
| “Mọi NoSQL wide-column đều hotspot khi khóa bắt đầu bằng timestamp.” | Hash partitioning và range partitioning có đặc điểm nóng khác nhau. |
| “TTL tự xóa vật lý ngay lúc hết hạn và ngăn partition lớn.” | TTL có thể tạo tombstone, dữ liệu được xử lý qua compaction và vẫn cần thiết kế partition đúng. |
| “Có index là truy vấn xuyên mọi partition luôn rẻ.” | Chi phí phụ thuộc chỉ mục, cơ chế định tuyến, fan-out, kích thước kết quả và consistency. |
| “Bucket random trên mỗi lần retry giúp phân phối đều hơn mà không ảnh hưởng gì.” | Random không ổn định có thể tạo bản ghi trùng và khó truy vấn đúng partition. |
| “Một threshold dung lượng áp dụng cho mọi cluster.” | Ngưỡng cần dựa vào sản phẩm, bản phát hành, cấu hình, workload và SLO thực tế. |

## 21. Kết luận

Trong mô hình cột rộng, partition key quyết định ranh giới dữ liệu; clustering key hỗ trợ sắp xếp và truy vấn **bên trong** ranh giới đó. Vì thế, cùng một tập dữ liệu có thể gặp ba thất bại khác nhau:

1. **Partition quá lớn:** một khóa tích lũy quá nhiều hàng, làm tăng chi phí đọc, compaction, tombstone, repair và phục hồi. Time bucket và retention có thể giới hạn tốc độ tăng theo kỳ.
2. **Partition quá nhỏ:** chia dữ liệu quá vụn, tạo nhiều metadata và khiến một request phải đọc nhiều partition. Cần gom dữ liệu theo mẫu truy cập và dùng clustering key cho những hàng liên quan.
3. **Hot partition:** một khóa hoặc dải khóa nhận lưu lượng không cân xứng, kể cả khi dữ liệu còn nhỏ. Cần xử lý phân bố khóa, hash bucket, thay đường ghi hoặc điều chỉnh mô hình truy cập.

**Time bucketing giới hạn kích thước; hash bucketing chia tải; clustering key phục vụ thứ tự; không kỹ thuật nào thay thế hoàn toàn kỹ thuật khác.** Cách kết hợp phù hợp phải được quyết định từ truy vấn thực, tốc độ tăng dữ liệu, độ lệch giữa các tenant, mô hình phân phối của DBMS và mục tiêu p95/p99. Khi đổi khóa, cần chuẩn bị cả kế hoạch di chuyển dữ liệu, bảo đảm ID ổn định qua retry và cách đọc qua nhiều partition.
