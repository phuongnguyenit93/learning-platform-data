# Chia khoảng thời gian để tổ chức lưu trữ và truy vấn

## 1. Vì sao dữ liệu chuỗi thời gian cần được chia khoảng?

Trong module **DATABASE_DATA_MODELING**, mục tiêu là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng: xác định thực thể, quan hệ, khóa, ràng buộc, chỉ mục và lược đồ vật lý, rồi kiểm chứng rằng mô hình trả lời đúng những câu hỏi quan trọng. Với chương **Dữ liệu chuỗi thời gian**, một quyết định vật lý nổi bật là **chia dữ liệu thành các khoảng thời gian** (*time-based partitioning*).

Xét nền tảng giám sát thiết bị IoT có 100.000 cảm biến. Mỗi thiết bị gửi một bản đo mỗi phút. Hệ thống cần lưu nhiệt độ, độ ẩm, mức pin và trạng thái kết nối; người vận hành thường hỏi:

- Thiết bị 101 có nhiệt độ trung bình trong **15 phút gần nhất** là bao nhiêu?
- Có bao nhiêu lần nhiệt độ vượt ngưỡng trong **tháng 7/2026**?
- Trong ngày 15/07, thiết bị ở một khu vực bị mất dữ liệu bao nhiêu lần?
- Dữ liệu chi tiết nào phải giữ **90 ngày**, dữ liệu tổng hợp theo giờ nào phải giữ **hai năm**?
- Sự kiện đến muộn của tháng trước nên ghi vào đâu?
- Khi kho dữ liệu có hàng tỷ bản đo, làm sao tránh quét cả những năm không liên quan?

Nếu lưu toàn bộ bản đo trong một bảng rất lớn, mỗi truy vấn theo thời gian có nguy cơ phải xử lý quá nhiều dữ liệu, trong khi việc xóa dữ liệu quá hạn và xây lại chỉ mục cũng trở nên tốn kém. **Phân vùng theo thời gian** chia một tập dữ liệu logic thành các phần vật lý dựa trên một cột thời gian, chẳng hạn từng ngày hoặc từng tháng.

Ví dụ:

~~~text
Bảng logic: telemetry_reading

Partition 2026-06: [2026-06-01 00:00 UTC, 2026-07-01 00:00 UTC)
Partition 2026-07: [2026-07-01 00:00 UTC, 2026-08-01 00:00 UTC)
Partition 2026-08: [2026-08-01 00:00 UTC, 2026-09-01 00:00 UTC)
...
~~~

Một truy vấn có điều kiện “từ đầu tháng 7 đến trước tháng 8 theo UTC” có thể chỉ cần xét partition tháng 7 thay vì toàn bộ bảng logic. Khi đến kỳ lưu giữ, hệ thống có thể quản lý/xóa các partition hết hạn theo chính sách được xác định.

**Phân vùng không tự thay đổi ý nghĩa nghiệp vụ của dữ liệu.** Nó chỉ là cách tổ chức lưu trữ. Các vấn đề như điểm thời gian chính xác, sự kiện đến muộn, tính duy nhất, trùng sự kiện, sai múi giờ và công thức tổng hợp vẫn phải được thiết kế riêng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **event time**, **ingestion time**, **valid time**, **processing time** và xác định cột thời gian thích hợp làm khóa phân vùng.
2. Thiết kế các khoảng **[from, to)** không chồng lấn và không bỏ sót biên.
3. Chọn kích thước partition theo khối lượng dữ liệu, mẫu truy vấn và vòng đời lưu trữ.
4. Xây bảng phân vùng RANGE trong PostgreSQL, ghi dữ liệu và kiểm tra vị trí hàng.
5. Viết truy vấn có khả năng **partition pruning**, tránh điều kiện làm khó bộ lập kế hoạch.
6. Phân biệt **phân vùng lưu trữ** với **time bucket tổng hợp**.
7. Xử lý sự kiện đến trễ, backfill, retention, uniqueness, idempotency, chỉ mục và kiểm thử vận hành.

## 2. Trước khi chia khoảng: một hàng đại diện cho điều gì?

Không thể thiết kế partition tốt nếu **grain** và khóa của hàng chưa rõ.

Trong ví dụ cảm biến:

> Một hàng là một bản đo của một đại lượng được một thiết bị gửi và được hệ thống chấp nhận, tại một thời điểm sự kiện xác định.

Một bản đo có thể chứa:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| **tenant_id** | Phạm vi khách hàng/tổ chức | 1 |
| **device_id** | Thiết bị gửi số liệu | 101 |
| **event_id** | Định danh duy nhất do nguồn/ingest cấp trong phạm vi đã định | UUID |
| **event_ts** | Thời điểm sự kiện được đo hoặc xảy ra | 2026-07-15 08:05 UTC |
| **received_at** | Lúc hệ thống tiếp nhận hoặc ghi nhận bản đo | 2026-07-15 08:06 UTC |
| **metric_code** | Loại đại lượng | temperature_c |
| **metric_value** | Giá trị đo | 28.3 |
| **quality_code** | Chất lượng/độ tin cậy | OK |
| **metadata** | Thuộc tính bổ sung được quản trị | Firmware, nguồn truyền |

Nếu một bản tin chứa đồng thời nhiệt độ và độ ẩm, có thể chọn grain **một bản tin thiết bị** với nhiều cột đo hoặc grain **một đại lượng trong bản tin** với metric_code và metric_value. Hai lựa chọn dẫn đến khác biệt về số hàng, khóa và truy vấn.

Ví dụ bản tin thiết bị có hai metric; nếu tách thành hai hàng nhưng dùng cùng event_id, unique key **(event_id)** không đủ để phân biệt chúng. Phải có metric_code hoặc một measurement_id riêng trong khóa. Trong bài này, **event_id** được giả định là **ID của từng bản đo**, không phải ID của gói tin chứa nhiều bản đo.

### 2.1. Thời gian của dữ liệu không có một nghĩa duy nhất

| Trục thời gian | Câu hỏi | Nên hiểu ra sao? |
|---|---|---|
| **event_ts** | Thiết bị đo lúc nào? | Thời gian sự kiện, có thể đến muộn |
| **received_at** | Hệ thống nhận bản đo lúc nào? | Thời gian tiếp nhận |
| **processed_at** | Worker xử lý xong lúc nào? | Thời gian xử lý pipeline |
| **valid_period** | Một trạng thái/quy tắc có hiệu lực trong giai đoạn nào? | Thời gian nghiệp vụ, thường là khoảng |
| **known_period** | Hệ thống đã chấp nhận một thông tin trong giai đoạn nào? | Phục vụ lịch sử hai trục nếu cần |
| **snapshot_at** | Bản chụp đại diện cho điểm cắt nào? | Phụ thuộc định nghĩa nguồn/cutoff |

Ví dụ cảm biến đo lúc **23:55 ngày 30/06**, nhưng do mất mạng đến **00:15 ngày 01/07** mới gửi. Chia theo event_ts sẽ đưa bản đo vào partition tháng 6. Chia theo received_at sẽ đưa nó vào partition tháng 7.

Không có lựa chọn luôn đúng cho mọi hệ thống:

- **Phân vùng theo event time** phù hợp truy vấn “đã xảy ra khi nào?”, cửa sổ dữ liệu lịch sử và các báo cáo theo ngày đo thực tế.
- **Phân vùng theo ingestion time** có thể hữu ích khi khối lượng ghi lớn, nguồn có thời gian không đáng tin, hoặc truy vấn chủ yếu theo thời điểm nhận.
- Hệ thống phải có chiến lược riêng nếu truy vấn thường lọc **cả hai thời gian**, hoặc nếu báo cáo cần biết “hệ thống đã biết gì vào thời điểm K”.

**Nguyên tắc:** chọn khóa phân vùng từ **truy vấn và vòng đời dữ liệu có thẩm quyền**, không chỉ vì cột nào có tên timestamp.

## 3. Khoảng nửa mở [from, to): nền tảng của mọi ranh giới

Với hai biên thời gian A và B, quy ước phổ biến là:

~~~text
[A, B)

t thuộc khoảng khi:
A <= t AND t < B
~~~

Biên trái được bao gồm, biên phải bị loại trừ. Hai khoảng liên tiếp có thể có cùng một mốc kết thúc/bắt đầu mà **không chồng lấn**:

~~~text
Partition tháng 6: [01/06 00:00, 01/07 00:00)
Partition tháng 7: [01/07 00:00, 01/08 00:00)

01/07 00:00 không thuộc tháng 6.
01/07 00:00 thuộc tháng 7.
~~~

Nếu dùng điều kiện **event_ts BETWEEN A AND B**, PostgreSQL diễn giải BETWEEN là **bao gồm cả hai đầu**. Một sự kiện đúng 01/08 00:00 có thể bị đếm ở cả tháng 7 và tháng 8 nếu cả hai báo cáo viết BETWEEN với mốc đầu tháng kế tiếp.

Viết đúng:

~~~sql
WHERE event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
~~~

Không tạo biên kết thúc giả **23:59:59.999** rồi mong phù hợp mọi độ chính xác. Một hệ thống có độ phân giải microsecond có thể có nhiều bản ghi sau mốc đó và trước 00:00.

### 3.1. Biên theo thời điểm tuyệt đối hay theo ngày lịch địa phương?

Tháng 7 theo **UTC** là:

~~~text
[2026-07-01 00:00+00, 2026-08-01 00:00+00)
~~~

Tháng 7 theo **lịch Việt Nam, UTC+07** là:

~~~text
[2026-07-01 00:00+07, 2026-08-01 00:00+07)

Tương đương theo UTC:
[2026-06-30 17:00+00, 2026-07-31 17:00+00)
~~~

Một bản đo lúc **2026-07-01 00:30+07** là **2026-06-30 17:30 UTC**. Nếu partition vật lý chia theo tháng UTC, bản đo này thuộc **partition tháng 6**, dù báo cáo theo tháng lịch Việt Nam tính nó vào tháng 7.

Điều đó **không phải lỗi phân vùng**. Nó cho thấy **ranh giới lưu trữ** và **ranh giới báo cáo theo lịch nghiệp vụ** có thể khác nhau. Một truy vấn báo cáo tháng 7 Việt Nam có thể cần đọc cuối partition tháng 6 và phần lớn partition tháng 7 UTC.

### 3.2. Kiểu thời gian và múi giờ

Với sự kiện là **thời điểm tuyệt đối**, ưu tiên **timestamptz** trong PostgreSQL và biểu diễn múi giờ khi nhập/so sánh. PostgreSQL lưu ngữ nghĩa một thời điểm; cách hiển thị tùy timezone phiên làm việc.

Với ngày nghiệp vụ như “số dư chốt ngày 31/07”, có thể dùng **date** và xác định lịch nghiệp vụ tương ứng. Không suy ngày của giao dịch bằng cách lấy ngày UTC khi doanh nghiệp thực sự dùng lịch địa phương.

Ở khu vực có đổi giờ mùa hè, một ngày địa phương có thể không kéo dài đúng 24 giờ. Khi tính khoảng ngày địa phương, dùng **đầu ngày địa phương của hai ngày liên tiếp** theo timezone được định nghĩa, không luôn cộng 24 giờ vào timestamp.

## 4. Chọn kích thước partition: theo giờ, ngày, tuần hay tháng?

Kích thước partition phải cân bằng khối lượng dữ liệu, số lượng partition, kiểu truy vấn và thao tác vận hành.

| Kỳ partition | Hợp với tình huống | Lợi ích | Rủi ro |
|---|---|---|---|
| **Theo giờ** | Ghi rất lớn, retention theo giờ, dữ liệu nóng ngắn | Phân đoạn nhỏ, drop theo giờ | Số partition/index nhiều, quản trị phức tạp |
| **Theo ngày** | Nhiều sự kiện/ngày, truy vấn thường theo ngày | Retention và backfill ngày thuận tiện | Số bảng con tăng nhanh theo năm |
| **Theo tuần** | Khối lượng vừa, lịch lưu giữ theo tuần | Cân bằng giữa ngày/tháng | Ranh giới tuần cần định nghĩa ISO/lịch nghiệp vụ |
| **Theo tháng** | Lượng dữ liệu vừa phải, lưu nhiều năm, query theo tháng | Ít partition hơn, bảo trì dễ | Partition có thể quá lớn nếu lưu lượng tăng |
| **Theo quý/năm** | Dữ liệu nhỏ hoặc archive lâu dài | Ít metadata | Pruning kém cho truy vấn ngắn, xóa kỳ nhỏ khó |

Không có định luật “1 partition phải bằng đúng N GB”. Hãy chọn dựa trên số hàng/byte thực tế, kích thước index, số partition mở đồng thời, độ dài truy vấn, thời gian vacuum/maintenance, chi phí retention và khả năng hệ quản trị xử lý kế hoạch truy vấn.

### 4.1. Ví dụ ước lượng khối lượng

Giả sử:

~~~text
100.000 thiết bị
1 bản đo/phút/thiết bị
1.440 phút/ngày

=> 144.000.000 bản đo/ngày
=> khoảng 4,32 tỷ bản đo / 30 ngày
~~~

Nếu một bản đo cùng overhead và index tiêu tốn trung bình **200 byte** trong một phép ước lượng sơ bộ, payload+chi phí ước tính đã vào khoảng **28,8 GB/ngày** và **864 GB/30 ngày**. Đây không phải số đo thực tế của PostgreSQL; kích thước cần được đo bằng dữ liệu thật, kiểu cột, compression, WAL, index, replication và chính sách lưu giữ.

Với lưu lượng đó, partition **mỗi tháng** có thể quá lớn cho một số thao tác bảo trì; partition **theo ngày** hoặc phương án chia thêm theo tenant/device có thể hợp lý hơn. Nhưng nếu mỗi partition/ngày vẫn có quá nhiều hàng, partitioning đơn thuần chưa giải quyết hết yêu cầu lưu trữ và tốc độ ghi.

### 4.2. Khi nào không nên chia quá nhỏ?

Nếu có 10.000 partition chứa vài trăm bản ghi mỗi cái, metadata, lập kế hoạch, số index và thao tác quản lý có thể trở thành chi phí đáng kể. Nhiều partition **không tự bảo đảm query nhanh hơn**.

Tăng số lượng partition chỉ nên làm khi có bằng chứng rằng kích thước cũ gây khó khăn cho truy vấn hoặc vòng đời dữ liệu. Với quy mô nhỏ, một bảng có chỉ mục **(tenant_id, device_id, event_ts)** có thể đã đủ tốt.

## 5. Partition pruning là gì?

**Partition pruning** là khả năng bộ lập kế hoạch hoặc bộ thực thi loại bỏ những partition không thể chứa hàng thỏa điều kiện truy vấn.

Giả sử bảng có 36 partition tháng, lưu ba năm dữ liệu. Một truy vấn:

~~~sql
SELECT COUNT(*)
FROM telemetry_reading
WHERE event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00';
~~~

có thể chỉ phải xét partition tháng 7 nếu partition được chia theo **RANGE(event_ts)** với đúng các biên trên.

Truy vấn vẫn phải quét các hàng cần thiết **bên trong** partition tháng 7. Pruning chỉ loại bỏ partition không liên quan; **nó không thay thế chỉ mục trong partition** và cũng không làm GROUP BY tự miễn phí.

### 5.1. Điều kiện nên giữ cột khóa phân vùng ở dạng so sánh trực tiếp

Một câu truy vấn dễ hiểu với partitioning:

~~~sql
WHERE event_ts >= :start_ts
  AND event_ts <  :end_ts
~~~

Phần mềm binding **:start_ts** và **:end_ts** phải truyền tham số có kiểu đúng; ở câu SQL minh họa đây không phải biến PostgreSQL tự tồn tại.

Tránh dùng điều kiện như:

~~~sql
WHERE DATE(event_ts) = DATE '2026-07-15'
~~~

nếu mục tiêu tối ưu là pruning dựa trên RANGE(event_ts). Hàm bọc quanh cột partition có thể khiến việc suy ra partition cần đọc khó hơn hoặc không khả dụng trong một số kế hoạch/phiên bản, ngoài ra **DATE(event_ts)** với timestamptz còn phụ thuộc timezone phiên làm việc.

Nên đổi sang:

~~~sql
WHERE event_ts >= TIMESTAMPTZ '2026-07-15 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-07-16 00:00:00+00'
~~~

Đối với **ngày Việt Nam**, dùng biên **+07** của hai ngày liên tiếp. Không đổi cột sang date rồi áp một mốc UTC ngoài ý nghĩa nghiệp vụ.

### 5.2. Truy vấn theo device không có khoảng thời gian

~~~sql
SELECT *
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101;
~~~

Nếu không giới hạn **event_ts**, hệ thống có thể phải xét **mọi partition** vì thiết bị 101 có thể xuất hiện trong mọi kỳ. Chỉ mục device trong từng partition vẫn có thể giúp, nhưng số partition cần thăm có thể nhiều.

Điều này cho thấy điều kiện thời gian cần là **một phần của API tra dữ liệu lịch sử** nếu workload thường chỉ yêu cầu khoảng gần đây.

### 5.3. Kiểm chứng bằng kế hoạch thực thi

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00';
~~~

Xem các node scan, partition được xét, số buffer đọc và thời gian. Trên bảng trống hoặc rất nhỏ, PostgreSQL có thể chọn sequential scan trên partition dù vẫn pruning đúng; đó không tự là lỗi.

Không kết luận hiệu quả chỉ từ một kế hoạch trên vài hàng mẫu. Cần benchmark dữ liệu đủ lớn, tỉ lệ truy vấn theo thiết bị và số partition thực tế.

## 6. Hai quyết định khác nhau: chia lưu trữ và chia nhóm tính toán

**Partition lưu trữ** và **time bucket dùng GROUP BY** hay bị lẫn.

- **Partition storage**: xác định những hàng được cất trong cấu trúc vật lý nào, ví dụ partition tháng 7.
- **Time bucket / tumbling window**: gom các sự kiện thuộc những khoảng như 5 phút, 15 phút hoặc một giờ để tính AVG, SUM, MIN, MAX.
- **Sliding window**: một khoảng phân tích dịch chuyển, ví dụ 15 phút gần nhất cập nhật mỗi phút.
- **Session window**: nhóm hoạt động theo khoảng ngắt không hoạt động.
- **Retention window**: khoảng thời gian dữ liệu được giữ.

Ví dụ dữ liệu tháng 7 nằm trong **một partition tháng**, nhưng truy vấn có thể chia thành **2.976 bucket 15 phút** nếu tháng có 31 ngày (31 × 24 × 4). Ngược lại, một bucket theo giờ ở biên tháng cũng có thể nằm trong phạm vi của một partition tùy quy ước timezone.

~~~text
Partition lưu trữ (tháng):
[---------------------- Tháng 7 ----------------------)

Các bucket báo cáo:
[15m)[15m)[15m)[15m)...[15m)
~~~

**Partitioning không tự tính giá trị AVG theo bucket.** Cần truy vấn tổng hợp, bảng rollup/materialized view hoặc hệ xử lý chuỗi thời gian có chức năng tổng hợp tương ứng.

## 7. Lược đồ PostgreSQL: bảng telemetry phân vùng theo thời điểm sự kiện

PostgreSQL hỗ trợ declarative partitioning với **PARTITION BY RANGE**. Ví dụ sau dùng **event_ts timestamptz** và các partition theo **tháng UTC**.

Giả định:

- Mỗi event_id nhận diện **một bản đo** trong phạm vi nguồn đã định.
- Một tenant có nhiều thiết bị; một thiết bị gửi nhiều metric.
- Dữ liệu chi tiết đo theo **thời điểm thiết bị ghi nhận**, nên chọn event_ts làm khóa partition.
- Mỗi bản đo lưu một giá trị số; thông tin về đơn vị của metric được xác định bằng **metric_code** và metadata/danh mục ngoài ví dụ.
- Các thao tác sửa/đính chính dữ liệu cũ phải đi qua quy trình riêng, không xem dữ liệu đo là luôn chính xác tuyệt đối.

### 7.1. Tạo bảng cha có ràng buộc cơ sở

~~~sql
CREATE TABLE telemetry_reading (
    tenant_id     bigint NOT NULL,
    device_id     bigint NOT NULL,
    event_id      uuid NOT NULL,
    event_ts      timestamptz NOT NULL,
    received_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    metric_code   text NOT NULL CHECK (length(metric_code) > 0),
    metric_value  numeric(18, 4) NOT NULL,
    quality_code  text NOT NULL DEFAULT 'OK',

    CONSTRAINT pk_telemetry_reading
        PRIMARY KEY (event_ts, tenant_id, device_id, event_id)
)
PARTITION BY RANGE (event_ts);
~~~

Đặc điểm:

- **Bảng cha telemetry_reading** là bề mặt logic để INSERT và SELECT.
- **event_ts** chọn partition nhận dữ liệu.
- **PRIMARY KEY** bao gồm **event_ts**, phù hợp giới hạn ràng buộc duy nhất của bảng phân vùng RANGE trong PostgreSQL.
- Khóa trên **không chứng minh event_id duy nhất trên mọi khoảng thời gian**. Cùng event_id với hai event_ts khác nhau vẫn có thể tồn tại; phải thiết kế idempotency nếu đó là điều nghiệp vụ cần.
- Không có **CHECK(received_at >= event_ts)** vì đồng hồ thiết bị có thể nhanh/chậm, dữ liệu có thể đến muộn hoặc bị chỉnh; kiểm tra timestamp bất thường cần được tách thành quy tắc chất lượng dữ liệu thay vì áp một bất biến không chắc đúng.

Một giá trị numeric có thể biểu diễn nhiệt độ âm, vì vậy không nên đặt CHECK(metric_value >= 0) chung cho mọi loại metric. Với độ ẩm phần trăm, mức pin hoặc lượng mưa, mỗi loại có miền giá trị hợp lệ khác nhau; nên kiểm tra theo **metric_code** hoặc dùng lược đồ/validator cụ thể.

### 7.2. Tạo các partition theo tháng UTC

~~~sql
CREATE TABLE telemetry_2026_06
PARTITION OF telemetry_reading
FOR VALUES FROM (TIMESTAMPTZ '2026-06-01 00:00:00+00')
         TO   (TIMESTAMPTZ '2026-07-01 00:00:00+00');

CREATE TABLE telemetry_2026_07
PARTITION OF telemetry_reading
FOR VALUES FROM (TIMESTAMPTZ '2026-07-01 00:00:00+00')
         TO   (TIMESTAMPTZ '2026-08-01 00:00:00+00');

CREATE TABLE telemetry_2026_08
PARTITION OF telemetry_reading
FOR VALUES FROM (TIMESTAMPTZ '2026-08-01 00:00:00+00')
         TO   (TIMESTAMPTZ '2026-09-01 00:00:00+00');
~~~

PostgreSQL kiểm soát các khoảng của partition cùng cha để tránh những vùng ranh giới chồng nhau. Đúng mốc 01/07 00:00 UTC, hàng sẽ vào **telemetry_2026_07**, không vào tháng 6.

Các partition này chỉ bao phủ tháng 6–8/2026. Nếu INSERT dữ liệu tháng 9 khi chưa có partition phù hợp, PostgreSQL sẽ **báo lỗi không tìm được partition**. Ứng dụng phải có lịch tạo partition tương lai hoặc chính sách rõ cho dữ liệu chưa có đích. Không được coi lỗi này là bản đo đã lưu thành công.

Có thể tạo DEFAULT partition làm vùng đệm, nhưng cần kiểm soát nguồn sai thời gian, backfill, việc tách dữ liệu từ DEFAULT sang partition đích, độ lớn vùng đệm và các thao tác có thể tốn khóa/scan. DEFAULT partition không nên trở thành nơi dữ liệu lỗi tồn tại vĩnh viễn mà không bị phát hiện.

### 7.3. Chỉ mục theo mẫu truy vấn thiết bị

~~~sql
CREATE INDEX idx_telemetry_tenant_device_time
ON telemetry_reading (tenant_id, device_id, event_ts DESC);
~~~

Trong PostgreSQL hỗ trợ partitioned index, việc tạo index trên bảng cha tạo chỉ mục tương ứng cho các partition. Nó hướng tới các truy vấn **một tenant/thiết bị trong khoảng thời gian**, hoặc lấy bản đo gần nhất.

Chỉ mục này không thay thế partition pruning. Nếu truy vấn chỉ lọc metric_code mà không có device_id, có thể cần một chỉ mục khác sau khi đo workload; đừng tạo chỉ mục cho mọi tổ hợp cột rồi làm chậm ingest.

## 8. Ghi dữ liệu và kiểm chứng hàng nằm ở partition nào

Chèn dữ liệu qua bảng cha:

~~~sql
INSERT INTO telemetry_reading (
    tenant_id, device_id, event_id,
    event_ts, metric_code, metric_value
)
VALUES
(
    1, 101, '00000000-0000-4000-8000-000000000001',
    TIMESTAMPTZ '2026-06-30 23:59:00+00',
    'temperature_c', 29.5
),
(
    1, 101, '00000000-0000-4000-8000-000000000002',
    TIMESTAMPTZ '2026-07-01 00:00:00+00',
    'temperature_c', 29.7
),
(
    1, 101, '00000000-0000-4000-8000-000000000003',
    TIMESTAMPTZ '2026-07-01 00:15:00+00',
    'temperature_c', 30.1
),
(
    1, 102, '00000000-0000-4000-8000-000000000004',
    TIMESTAMPTZ '2026-07-15 08:05:00+00',
    'temperature_c', 28.3
),
(
    1, 101, '00000000-0000-4000-8000-000000000005',
    TIMESTAMPTZ '2026-08-01 00:00:00+00',
    'temperature_c', 27.0
),
(
    1, 101, '00000000-0000-4000-8000-000000000006',
    TIMESTAMPTZ '2026-07-01 00:30:00+07',
    'temperature_c', 29.0
);
~~~

Bản cuối diễn đạt giờ địa phương Việt Nam nhưng tương đương **2026-06-30 17:30 UTC**, nên thuộc partition tháng 6 UTC.

Kiểm tra tên partition vật lý bằng **tableoid** trong PostgreSQL:

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    COUNT(*) AS row_count
FROM telemetry_reading
GROUP BY tableoid::regclass
ORDER BY physical_partition;
~~~

Với đúng sáu bản đo ở trên, kết quả kỳ vọng:

| Partition vật lý | Số hàng |
|---|---:|
| telemetry_2026_06 | 2 |
| telemetry_2026_07 | 3 |
| telemetry_2026_08 | 1 |

Một số điều cần nhớ:

- Kết quả dựa trên **UTC của thời điểm tuyệt đối**, không dựa trên chuỗi ngày hiển thị của thiết bị.
- Khi INSERT qua bảng cha, hệ quản trị định tuyến hàng; không cần ứng dụng chọn tên partition bằng chuỗi tự xây.
- Nếu UPDATE làm đổi **event_ts** qua biên partition, database có thể phải chuyển hàng giữa partition. Với dữ liệu đo, nên hạn chế sửa timestamp trừ khi có quy trình correction rõ ràng.
- Bản ghi đo từ tháng cũ **đến muộn** được định tuyến về partition cũ nếu partition đó vẫn tồn tại.

## 9. Viết truy vấn giới hạn thời gian để tận dụng pruning

### 9.1. Bản đo gần nhất của một thiết bị trong tháng 7 UTC

~~~sql
SELECT event_ts, metric_code, metric_value
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101
  AND metric_code = 'temperature_c'
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
ORDER BY event_ts DESC
LIMIT 1;
~~~

Trong dữ liệu mẫu, bản đo nhiệt độ cuối cùng của device 101 trong tháng 7 UTC là **00:15 UTC ngày 01/07**, giá trị **30.1**. Bản **00:30+07** không thuộc tháng 7 UTC; bản **01/08 00:00 UTC** cũng không thuộc vì biên phải bị loại trừ.

### 9.2. Trung bình và số mẫu trong tháng

~~~sql
SELECT
    tenant_id,
    device_id,
    metric_code,
    COUNT(*) AS sample_count,
    AVG(metric_value) AS avg_value,
    MIN(metric_value) AS min_value,
    MAX(metric_value) AS max_value
FROM telemetry_reading
WHERE tenant_id = 1
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
GROUP BY tenant_id, device_id, metric_code
ORDER BY device_id, metric_code;
~~~

**AVG** được tính trên **các bản đo có mặt**. Nếu thiết bị gửi không đều, trung bình các mẫu không nhất thiết bằng trung bình có trọng số theo thời gian. Phải quy định mục tiêu nghiệp vụ: trung bình các lần quan sát, trung bình mỗi phút, hay trung bình liên tục theo thời gian.

### 9.3. Truy vấn tháng 7 theo lịch Việt Nam

~~~sql
SELECT COUNT(*) AS july_vietnam_samples
FROM telemetry_reading
WHERE tenant_id = 1
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
  AND event_ts <  TIMESTAMPTZ '2026-08-01 00:00:00+07';
~~~

Biên UTC tương ứng trải qua **hai partition UTC**: cuối tháng 6 và phần lớn tháng 7. Đây là hệ quả đúng của lịch địa phương; đừng “tối ưu” bằng cách ép truy vấn tháng 7 Việt Nam chỉ đọc partition tháng 7 UTC, vì sẽ bỏ sót dữ liệu trong 7 giờ đầu ngày 01/07 theo giờ Việt Nam.

## 10. Time bucket: nhóm dữ liệu theo 5 phút, 15 phút, giờ hoặc ngày

Phân vùng là cách lưu trữ; báo cáo thường cần **time bucket**.

Trong PostgreSQL 14 trở lên, **date_bin** có thể gom thời điểm theo độ dài cố định như 15 phút. Với nhóm giá trị nhiệt độ của một thiết bị:

~~~sql
SELECT
    date_bin(
        INTERVAL '15 minutes',
        event_ts,
        TIMESTAMPTZ '2026-01-01 00:00:00+00'
    ) AS bucket_start_utc,
    COUNT(*) AS sample_count,
    AVG(metric_value) AS avg_temperature_c
FROM telemetry_reading
WHERE tenant_id = 1
  AND device_id = 101
  AND metric_code = 'temperature_c'
  AND event_ts >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND event_ts <  TIMESTAMPTZ '2026-07-02 00:00:00+00'
GROUP BY bucket_start_utc
ORDER BY bucket_start_utc;
~~~

Dữ liệu mẫu cho device 101:

| Bucket UTC | Giá trị có mặt | AVG |
|---|---|---:|
| [00:00, 00:15) | 29.7 | 29.7 |
| [00:15, 00:30) | 30.1 | 30.1 |

**date_bin** không tự sinh bucket trống. Nếu cần một điểm cho mọi 15 phút để vẽ biểu đồ, có thể tạo **chuỗi mốc thời gian** rồi LEFT JOIN kết quả tổng hợp. Khoảng không có mẫu phải là **NULL/không dữ liệu** nếu chưa có chính sách nội suy hoặc điền 0.

### 10.1. Vì sao không mặc định 0 cho bucket trống?

Với nhiệt độ, không có bản đo không có nghĩa nhiệt độ bằng 0°C. Với tốc độ mạng, “không ghi nhận lưu lượng” khác “đã đo thấy lưu lượng 0”. Một dashboard tự điền 0 có thể tạo cảnh báo giả hoặc làm giảm trung bình sai.

Có thể chọn một trong các chính sách:

- **Null:** chưa có quan sát.
- **Last observation carried forward:** giữ giá trị gần nhất trước bucket, nếu metric cho phép và có giới hạn độ cũ.
- **Interpolation:** nội suy nếu đại lượng, sampling và mô hình có căn cứ.
- **Zero-fill:** chỉ với loại số đo mà thiếu sự kiện thực sự có nghĩa bằng 0 và đã xác minh điều kiện nguồn.

Các cách này tạo **số đo có ngữ nghĩa khác nhau**, phải ghi rõ trong metric definition.

### 10.2. Bucket lịch địa phương khác bucket độ dài cố định

Một **bucket 15 phút** là khoảng độ dài cố định trên trục thời gian tuyệt đối. **Một ngày hoặc một tháng địa phương** là khoảng lịch có ranh giới theo timezone; ở nơi có DST, ngày địa phương có thể dài 23 hoặc 25 giờ.

Không dùng **date_bin(INTERVAL '1 month', ...)** trong PostgreSQL cho tháng lịch; date_bin không hỗ trợ stride chứa tháng hoặc đơn vị lớn hơn tháng. Với nhóm tháng có thể dùng **date_trunc** theo timezone hoặc bảng chiều lịch, nhưng điều kiện WHERE vẫn nên dùng các biên thời gian có thể pruning.

## 11. Chọn chỉ mục trong từng partition

Partition pruning giúp bỏ qua các partition không liên quan. **Chỉ mục** giúp tìm nhanh hàng trong những partition vẫn phải đọc.

| Mẫu truy vấn | Chiến lược thường cân nhắc |
|---|---|
| Một tenant + device trong khoảng thời gian | B-tree (tenant_id, device_id, event_ts) |
| Thiết bị và metric theo khoảng thời gian | B-tree (tenant_id, device_id, metric_code, event_ts) |
| Quét toàn tháng để tổng hợp mọi thiết bị | Partition scan/parallel scan tùy khối lượng |
| Khoảng thời gian lớn, dữ liệu vật lý tương quan với event_ts | BRIN(event_ts) có thể tiết kiệm |
| Tra event_id để chống duplicate | Cấu trúc dedup/registry khác nếu cần global uniqueness |
| Phân tích theo vùng/loại thiết bị | Dimension mapping và tổng hợp phù hợp, không chỉ index telemetry |

Ví dụ chỉ mục BRIN tùy workload:

~~~sql
CREATE INDEX idx_telemetry_event_ts_brin
ON telemetry_reading USING brin (event_ts);
~~~

BRIN thường nhỏ và hữu ích khi các giá trị thời gian **tương quan với thứ tự vật lý** của hàng. Nếu ingest có nhiều bản đo đến muộn được chèn rải rác hoặc dữ liệu được tái tổ chức, hiệu quả có thể giảm. Không khẳng định BRIN luôn tốt hơn B-tree.

Tạo đồng thời B-tree và BRIN chỉ khi truy vấn thực tế cần cả hai; mỗi chỉ mục đều làm tăng chi phí INSERT, WAL và lưu trữ. Dùng EXPLAIN, thống kê và phép đo khối lượng ghi để quyết định.

### 11.1. Sắp xếp cột trong chỉ mục phải theo workload

B-tree **(tenant_id, device_id, event_ts DESC)** có ích cho truy vấn giới hạn tenant/device rồi lấy điểm mới nhất. Nếu truy vấn phần lớn lọc **metric_code** nhưng không lọc device_id, thứ tự đó có thể không tối ưu.

Không thêm mọi biến thể chỉ mục có thể nghĩ ra. Nên ưu tiên các mẫu truy vấn có tần suất cao và ảnh hưởng lớn tới độ trễ, sau đó đo chi phí tổng.

## 12. Uniqueness, idempotency và giới hạn khóa toàn cục

**Dữ liệu chuỗi thời gian thường có sự kiện gửi lại.** Gateway có thể timeout sau khi database commit, rồi gửi lại cùng bản đo. Nếu không có idempotency, một bản đo có thể xuất hiện hai lần, làm COUNT, SUM hoặc AVG sai.

Ví dụ khóa trên bảng partitioned:

~~~sql
PRIMARY KEY (event_ts, tenant_id, device_id, event_id)
~~~

cho phép database ngăn hai hàng có **cùng bốn giá trị**, nhưng **không ngăn cùng event_id được ghi với event_ts khác**.

Trong PostgreSQL, ràng buộc UNIQUE/PRIMARY KEY trên bảng partitioned cần bao gồm các cột khóa phân vùng để hệ quản trị có thể bảo đảm uniqueness thông qua các partition. Do đó một **UNIQUE(event_id)** toàn cục trên bảng RANGE(event_ts) không thể được thay thế bằng một chỉ mục UNIQUE riêng trên từng partition mà vẫn giữ cùng ngữ nghĩa.

### 12.1. Nếu cần chống trùng event_id bất kể event_ts

Có thể chọn một bảng registry không phân vùng theo thời gian, với khóa nghiệp vụ duy nhất:

~~~sql
CREATE TABLE ingest_event_registry (
    tenant_id      bigint NOT NULL,
    source_system  text NOT NULL,
    event_id       uuid NOT NULL,
    first_event_ts timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, source_system, event_id)
);
~~~

Một giao thức ghi:

1. Bắt đầu transaction.
2. Chèn khóa idempotency vào registry. Nếu trùng, kiểm tra bản ghi đã được xử lý và trả trạng thái phù hợp, **không chèn thêm telemetry**.
3. Chèn bản đo vào bảng telemetry_reading.
4. Commit **cùng transaction** nếu hai bảng thuộc cùng database.
5. Retry phải nhận diện cùng event_id, nguồn và tenant; nếu payload khác nhưng ID trùng, đó là **xung đột** cần điều tra, không mặc định ghi đè.

Nếu dùng **INSERT ... ON CONFLICT DO NOTHING** cho registry, ứng dụng phải kiểm tra có thật sự chèn một hàng mới hay không, thay vì tiếp tục chèn telemetry ngay cả khi registry đã tồn tại.

Registry thêm chi phí ghi và giữ khóa toàn cục. Nếu chỉ bảo đảm idempotency trong một cửa sổ retry, có thể dùng chiến lược retention riêng, nhưng khi xóa registry phải chấp nhận/giải quyết nguy cơ nhận lại event cũ. Không chọn TTL cho registry mà quên thời gian nguồn có thể gửi lại.

### 12.2. Event timestamp không phải khóa danh tính đáng tin

Hai cảm biến có thể gửi hai phép đo ở cùng một microsecond. Một thiết bị có thể phát lại một bản đo nhưng thay timestamp do đồng hồ được sửa. Vì vậy **(device_id, event_ts)** chỉ là khóa duy nhất nếu giao thức nguồn **thật sự bảo đảm** tối đa một bản đo tại mỗi thời điểm đó cho đúng loại metric.

Đối với chuỗi có nhiều metric, event_id hoặc sequence nguồn còn giúp phân biệt bản đo độc lập với timestamp.

## 13. Sự kiện đến muộn và dữ liệu có thời gian không đúng

Một bản đo có **event_ts** tháng 6 nhưng **received_at** tháng 7 là tình huống bình thường nếu thiết bị bị mất mạng. Với phân vùng theo event_ts:

- Nếu partition tháng 6 còn tồn tại và cho phép ghi, bản đo được chèn vào đó.
- Nếu partition tháng 6 đã bị xóa theo retention, INSERT có thể thất bại vì không có partition.
- Nếu event_ts nằm ngoài phạm vi hợp lệ (thiết bị gửi năm 1970 hoặc năm 2099), không được âm thầm tạo partition ngẫu nhiên và coi dữ liệu đúng.

### 13.1. Chính sách late-arrival rõ ràng

| Tình huống | Cách xử lý có thể chọn | Điều cần công bố |
|---|---|---|
| Chậm 5 phút | Nhập vào partition hiện có | Độ trễ theo received_at |
| Chậm 2 ngày | Nhập partition ngày/tháng cũ | Rollup/aggregate bị ảnh hưởng |
| Chậm 2 tháng, raw đã archive | Khôi phục/backfill có kiểm soát hoặc đưa vùng chờ | Khoảng phục hồi và chi phí |
| Timestamp tương lai quá xa | Quarantine, cảnh báo clock skew | Ngưỡng clock sai chấp nhận |
| Timestamp trước thời kỳ dữ liệu được phép | Từ chối hoặc lưu ngoại lệ | Không làm hỏng retention |
| Cùng event_id nhưng timestamp khác | Xung đột/dedup theo nguồn | Không tự tạo hai bản đo |

**Watermark** có thể đại diện cho một thời điểm mà pipeline dự kiến dữ liệu trước đó đã đủ đầy theo SLA. Nhưng watermark là một **cam kết về độ trễ và xử lý**, không phải bằng chứng logic rằng không bao giờ có sự kiện cũ hơn tới nữa. Cần chính sách xử lý ngoại lệ sau watermark.

### 13.2. Backfill và tính đúng của aggregate

Nếu một bản đo nhiệt độ tháng 6 đến vào tháng 7, raw partition tháng 6 có thể được bổ sung, nhưng bảng tổng hợp tháng 6 đã xây trước đó có thể **không còn chính xác**.

Các lựa chọn:

- Đánh dấu bucket bị ảnh hưởng và **tính lại** từ raw.
- Áp dụng điều chỉnh incremental nếu công thức có thể cập nhật an toàn.
- Giữ phiên bản rollup, ngày tính lại và nguồn.
- Đóng kỳ sau mốc SLA, rồi xử lý ngoại lệ bằng bản điều chỉnh được công bố.

AVG không chỉ cần một giá trị trung bình đã lưu; nếu cập nhật incremental, thường cần **SUM và COUNT** của các bản đo hợp lệ. Khi bản đo cũ được sửa/xóa, lại cần biết đóng góp trước đó để rút khỏi tổng.

## 14. Retention, lifecycle và xóa partition

Dữ liệu chuỗi thời gian thường có **vòng đời theo tuổi dữ liệu**:

~~~text
Raw hot (0–7 ngày):
  truy vấn thường xuyên, ghi nhiều

Raw warm (8–90 ngày):
  lưu chi tiết, truy vấn ít hơn

Rollup hourly (0–2 năm):
  giữ tổng hợp theo giờ

Archive cold (sau 90 ngày nếu chính sách cho phép):
  đối soát/khôi phục có chi phí cao hơn
~~~

Đây chỉ là ví dụ. Thời gian giữ thực tế phải dựa trên yêu cầu nghiệp vụ, hợp đồng, quy định, ngân sách và loại dữ liệu.

### 14.1. Xóa một partition thay vì DELETE từng hàng

Khi toàn bộ partition tháng 6 đã quá hạn, có thể cân nhắc:

~~~sql
-- Minh họa thao tác có tính phá hủy dữ liệu.
-- Chỉ thực hiện khi đã hoàn tất quy trình retention,
-- xác minh kỳ, quyền, backup/archive và phụ thuộc.

ALTER TABLE telemetry_reading
DETACH PARTITION telemetry_2026_06;

-- DROP TABLE telemetry_2026_06; -- Chỉ sau khi được phê duyệt xóa.
~~~

**DETACH** tách bảng con khỏi bảng cha, không tự xóa dữ liệu của bảng vừa tách. **DROP TABLE** mới xóa dữ liệu vật lý của bảng đó. Các thao tác này cần kiểm tra quyền, khóa và ảnh hưởng tới query đang chạy; cú pháp/chế độ hỗ trợ concurrent detach phụ thuộc phiên bản và bối cảnh PostgreSQL.

Nếu dữ liệu đã nằm ở archive sau DETACH, phải ghi lại vị trí archive và phạm vi truy vấn được bảo đảm. Nếu vẫn có late-arriving events thuộc kỳ đó, chúng cần được điều hướng sang quy trình xử lý dữ liệu cũ; không tự nhận dữ liệu đã được lưu thành công vào partition đã detach.

### 14.2. Partition boundary phải khớp chính sách giữ dữ liệu

Nếu quy định chỉ giữ raw **90 ngày tính theo ngày thực**, nhưng partition theo **tháng**, không thể drop một phần tháng mà vẫn chỉ dùng thao tác drop partition tháng. Có thể:

- Chọn partition theo ngày để áp retention chính xác hơn.
- Chấp nhận giữ dư tới hết partition, nếu chính sách cho phép.
- Kết hợp xóa hàng trong kỳ biên với drop partition nguyên kỳ cũ, nhưng có chi phí DELETE/vacuum.

Retention không nên dựa vào tên partition do ai đó đặt thủ công; cần kiểm chứng **bounds thực tế**, kỳ dữ liệu đã hết hạn và những yêu cầu hold/kiểm toán trước khi xóa.

### 14.3. Raw và rollup có retention độc lập

Giữ hourly average hai năm không có nghĩa có thể phục hồi **từng bản đo** sau khi raw bị xóa. Nếu nghiệp vụ yêu cầu kiểm tra sự kiện cụ thể tại một phút trong năm ngoái, aggregate theo giờ không thay thế raw.

Vì vậy API nên ghi rõ cửa sổ:

- Chi tiết đến mức bản đo: 90 ngày.
- Thống kê theo giờ: hai năm.
- Thống kê theo ngày: có thể dài hơn theo hợp đồng.

Đừng quảng cáo truy vấn lịch sử chi tiết trong thời gian mà dữ liệu gốc đã hết retention.

## 15. Tổng hợp trước, phân vùng sau, hay cả hai?

Ở quy mô lớn, thường cần nhiều tầng:

~~~mermaid
flowchart TD
    A["Thiết bị / nguồn sự kiện"] --> B["Ingest + kiểm tra thời gian / event_id"]
    B --> C["Raw telemetry partition theo event_ts"]
    C --> D["Rollup 15 phút"]
    D --> E["Rollup theo giờ / ngày"]
    E --> F["Dashboard và báo cáo lịch sử"]
    C --> G["Tra cứu sự kiện chi tiết"]
    C --> H["Archive / retention"]
~~~

Các tầng phục vụ những câu hỏi khác nhau:

- **Raw**: phục hồi bản đo cụ thể, phân tích anomaly ở độ phân giải gốc.
- **Rollup 15 phút**: dashboard gần thời gian thực, ít hàng hơn.
- **Rollup giờ/ngày**: phân tích xu hướng dài hạn.
- **Archive**: giữ chứng cứ hoặc phục hồi khi cần, với SLA truy vấn khác.

Partitioning của raw và rollup có thể có **kỳ khác nhau**. Ví dụ raw theo ngày, rollup theo tháng; không có lý do buộc các bảng dùng cùng độ hạt partition.

### 15.1. Bảng rollup có grain riêng

Ví dụ grain **một tenant–device–metric–bucket 15 phút**:

~~~sql
CREATE TABLE telemetry_15m_rollup (
    tenant_id     bigint NOT NULL,
    device_id     bigint NOT NULL,
    metric_code   text NOT NULL,
    bucket_start  timestamptz NOT NULL,
    sample_count  bigint NOT NULL CHECK (sample_count >= 0),
    sample_sum    numeric(24, 4) NOT NULL,
    min_value     numeric(18, 4),
    max_value     numeric(18, 4),

    PRIMARY KEY (
        bucket_start, tenant_id, device_id, metric_code
    )
)
PARTITION BY RANGE (bucket_start);
~~~

Bảng trên cần **partition con** trước khi INSERT; đây là lược đồ minh họa grain chứ chưa phải một hệ thống rollup hoàn chỉnh. Việc tạo bảng cha riêng cho rollup cho phép có vòng đời/index khác raw.

AVG có thể được tính:

~~~sql
SELECT
    tenant_id,
    device_id,
    metric_code,
    SUM(sample_sum) /
        NULLIF(SUM(sample_count), 0) AS avg_from_rollup
FROM telemetry_15m_rollup
WHERE bucket_start >= TIMESTAMPTZ '2026-07-01 00:00:00+00'
  AND bucket_start <  TIMESTAMPTZ '2026-08-01 00:00:00+00'
GROUP BY tenant_id, device_id, metric_code;
~~~

Tính **trung bình của các trung bình bucket** bằng AVG(sample_avg) thường sai khi bucket có số mẫu khác nhau. Cần **SUM(sample_sum)/SUM(sample_count)**.

Nếu metric là nhiệt độ bình quân theo **thời lượng** chứ không theo số mẫu, cần trọng số thời gian phù hợp thay vì sample_count. Với percentile, median hoặc distinct count, SUM/COUNT đơn giản không đủ; phải thiết kế aggregate state hoặc dùng raw để tính lại.

### 15.2. Một rollup có thể không phản ánh dữ liệu mới nhất

Nếu worker tổng hợp chạy mỗi giờ, dữ liệu raw mới đã có nhưng rollup giờ cuối chưa hoàn tất. API cần nêu **watermark/last_refreshed_at** và chính sách kết hợp dữ liệu raw của kỳ chưa đóng, tránh vừa tính rollup đã chốt vừa cộng thêm raw cùng kỳ gây double count.

## 16. Partitioning theo thời gian và thêm một chiều không gian khác

Nếu một partition ngày chứa quá nhiều bản ghi của hàng nghìn tenant, có thể cần chia thêm theo **tenant, device hoặc hash**. Đây là phân vùng hai cấp hoặc sharding, không phải một phép tối ưu miễn phí.

Ví dụ ý tưởng:

~~~text
RANGE(event_ts theo ngày)
    -> HASH(tenant_id) hoặc HASH(device_id)
~~~

Lợi ích có thể là giảm kích thước mỗi shard và phân tán tải ghi. Nhưng đánh đổi gồm:

- Nhiều đối tượng vật lý hơn, thêm index và metadata.
- Query toàn bộ tenant/thiết bị có thể phải truy cập nhiều shard.
- Cross-shard aggregation và giao dịch phức tạp hơn.
- Unique key phải phù hợp cấu trúc phân vùng.
- Hotspot vẫn tồn tại nếu một tenant/thiết bị tạo phần lớn lưu lượng.
- Retention và archive cần xử lý toàn bộ shard của một kỳ.

Không chọn số hash bucket chỉ dựa trên số thiết bị. Phải đo skew, khối lượng ghi, số partition vật lý, truy vấn có lọc tenant/device hay không và giới hạn engine.

### 16.1. Time partition khác sharding toàn hệ thống

**Partitioning** thường là phân chia dữ liệu dưới một bảng logic của cùng một hệ quản trị. **Sharding** có thể phân tán dữ liệu qua nhiều node/database độc lập, kéo theo chuyện routing, transaction và truy vấn cross-shard.

Trong hệ thống time-series chuyên dụng, khái niệm **chunk/hypertable** có thể tự động hóa việc chia thời gian và các chiều khác. Dù công cụ nào, vẫn phải định nghĩa event time, retention, data contract, khóa danh tính và tính đúng của aggregate.

## 17. Mô hình quan hệ, document, graph và kho phân tích

Tư duy **chọn khoảng thời gian theo truy vấn và vòng đời** vẫn hữu ích khi thay đổi loại lưu trữ.

| Mô hình | Cách tổ chức thường gặp | Điều cần cẩn trọng |
|---|---|---|
| **Relational/PostgreSQL** | RANGE partition theo timestamp, index trong partition | Unique key toàn cục, pruning, DDL/bảo trì |
| **Time-series database** | Chunks/hypertables, time buckets, compression, retention policy | Ngữ nghĩa event/ingest time, late data, aggregate refresh |
| **Document** | Collection theo tháng hoặc partition key có thành phần thời gian | Cross-collection query, TTL, index, trùng event |
| **Graph** | Cạnh/node có thời gian hiệu lực hoặc event time | Truy vấn đường đi theo thời gian, nhất quán giữa các cạnh |
| **Kho phân tích/lakehouse** | Partition theo ngày nạp/ngày nghiệp vụ, clustering, file pruning | File nhỏ, dữ liệu đến muộn, rewrite partition, metadata |
| **Event stream/log** | Topic-partition/segment theo offset hoặc thứ tự sự kiện | Offset không nhất thiết là ngày sự kiện; event time có thể đến muộn |

### 17.1. Document: chia collection theo tháng có thể gây nợ kỹ thuật

Một cách đơn giản là tạo **readings_2026_06**, **readings_2026_07**. Nhưng nếu application phải tự ghép tên collection cho từng query, cần xử lý:

- Query qua nhiều kỳ.
- Schema/index đồng nhất giữa các collection.
- Nạp sự kiện cũ khi collection đã archive.
- Thống nhất timezone.
- Retention và quyền truy cập.
- Số lượng collection tăng theo thời gian.

Nếu database document có partitioning hoặc TTL tích hợp, có thể tốt hơn việc tự tạo collection theo tên tháng. Dù vậy, TTL không thay thế yêu cầu kiểm toán và xử lý dữ liệu đến muộn.

### 17.2. Graph: thời gian có thể nằm trên quan hệ

Một đồ thị thiết bị có các quan hệ **DEVICE_LOCATED_IN_SITE** thay đổi theo thời gian. Muốn báo nhiệt độ theo khu vực ngày 15/07, phải xác định thiết bị thuộc site nào **vào ngày 15/07**, không chỉ site hiện tại.

Ngay cả khi bản đo đã được partition theo event_ts, JOIN tới một quan hệ vị trí không có lịch sử vẫn có thể làm báo cáo quá khứ sai.

### 17.3. Lakehouse: date partition và vấn đề file nhỏ

Trong hệ thống cột/file, có thể ghi dữ liệu theo **event_date** hoặc **ingestion_date** và dùng metadata file để bỏ qua tệp không liên quan. Nếu mỗi microbatch sinh nhiều file rất nhỏ, chi phí metadata/file open có thể cao. Cần compaction, clustering và lịch rewrite phù hợp.

Partition theo event_date giúp query lịch sự kiện; partition theo ingestion_date giúp theo dõi lô nhận. Đặc biệt với late data, chọn cái nào cần ưu tiên phải xuất phát từ mẫu truy vấn chứ không sao chép cấu hình sẵn.

## 18. Vận hành partition: tạo trước, quan sát, đối soát và phục hồi

Partitioning là một **quy trình vận hành liên tục**, không chỉ một lần CREATE TABLE.

### 18.1. Tạo trước partition tương lai

Nên có job tạo partition **trước** khoảng dữ liệu tiếp theo với thời gian dự phòng cho clock skew và kế hoạch ingest. Nếu tháng 8 sắp bắt đầu, partition tháng 8 cần tồn tại trước khi nhận event_ts thuộc tháng ấy.

Job nên có tính **idempotent**: chạy lại không tạo trùng hoặc làm thay đổi biên của partition đã đúng. Khi thất bại, cần cảnh báo trước khi việc ghi bị gián đoạn.

Việc dùng script tự tạo tên partition từ mốc giờ phải tôn trọng timezone và trường hợp năm nhuận, tháng 28/29/30/31 ngày. Không giả định mọi tháng có 30 ngày.

### 18.2. Các chỉ số giám sát

| Metric vận hành | Ý nghĩa |
|---|---|
| Partition tương lai đã sẵn sàng | Không mất ghi ở biên kỳ |
| Số partition và kích thước mỗi partition | Theo dõi tăng trưởng/skew |
| Số bản đo bị từ chối do thiếu partition | Phát hiện lỗi kế hoạch |
| Độ trễ received_at − event_ts | Phân bố late arrivals, clock skew |
| Số event bị deduplicate | Theo dõi retry |
| Khoảng raw còn được truy vấn | Bảo đảm retention |
| Watermark/last rollup refresh | Độ mới của dashboard |
| Rows/bytes theo tenant/device | Phát hiện hot tenant |
| Thời gian query và buffer đọc | Kiểm chứng pruning/index |
| Backfill/rebuild đang chạy | Tránh công bố dữ liệu chưa đầy đủ |

**received_at − event_ts** có thể âm nếu đồng hồ thiết bị chạy nhanh; đây là tín hiệu dữ liệu cần điều tra, không nhất thiết là một số cần CHECK cứng trong bảng thô.

### 18.3. Các yêu cầu khôi phục

Khi partition bị tạo thiếu hoặc lưu nhầm dữ liệu do timezone, quy trình cần biết:

1. Dữ liệu gốc có còn trong log/broker/object storage không?
2. Có idempotency key để import lại mà không tạo duplicate không?
3. Bản ghi nào bị đưa sang partition sai, bản nào chưa bao giờ được ghi?
4. Các rollup nào bị ảnh hưởng và có thể tính lại từ raw không?
5. Dashboard/report đã xuất bản có cần revision không?
6. Có thể dừng ghi vào kỳ bị tác động trong khi sửa để tránh race không?

Không chỉ “đổi tên partition” để sửa lỗi biên thời gian: tên bảng không quyết định điều kiện RANGE thực tế, và dữ liệu có thể cần được chuyển theo timestamp.

## 19. Ma trận kiểm thử bắt buộc

### 19.1. Biên thời gian

| Sự kiện | Partition UTC kỳ vọng |
|---|---|
| 2026-06-30 23:59:59+00 | Tháng 6 |
| 2026-07-01 00:00:00+00 | Tháng 7 |
| 2026-07-31 23:59:59+00 | Tháng 7 |
| 2026-08-01 00:00:00+00 | Tháng 8 |
| 2026-07-01 00:30:00+07 | Tháng 6 |
| 2026-09-01 00:00:00+00 | Lỗi nếu chưa có partition tháng 9 hoặc DEFAULT |
| Event tháng 6 đến trong tháng 7 | Tháng 6 nếu event_ts dùng làm partition key |

### 19.2. Truy vấn

1. Truy vấn tháng 7 UTC chỉ chọn bản đo thuộc **[01/07 00:00 UTC, 01/08 00:00 UTC)**.
2. Truy vấn ngày 01/07 Việt Nam bao gồm khoảng **[30/06 17:00 UTC, 01/07 17:00 UTC)**, dù dữ liệu nằm trên hai partition UTC.
3. COUNT theo thiết bị không nhân đôi sự kiện khi nguồn gửi lại cùng event_id.
4. Bucket 15 phút tại 00:15 thuộc bucket bắt đầu **00:15**, không thuộc bucket kết thúc 00:15.
5. Bucket không có mẫu được xử lý theo quy tắc NULL/zero/interpolation đã định.
6. AVG nhiều bucket được tính bằng tổng sum / tổng count, không trung bình đều các AVG khi số mẫu khác nhau.
7. Query thiếu điều kiện thời gian được đo để thấy chi phí đọc nhiều partition.
8. Kiểm tra EXPLAIN và buffers trên dữ liệu đủ lớn, không coi số hàng ít là benchmark.

### 19.3. Vận hành và integrity

1. Thiếu partition mới làm INSERT thất bại rõ, không tạo thành công giả.
2. Hai worker tạo cùng partition không phá vỡ schema; job có idempotency.
3. Late event vào partition cũ có chính sách rõ nếu partition đang archive hoặc đã drop.
4. Event_id trùng với timestamp khác bị xử lý theo idempotency cấp nghiệp vụ, không ỷ lại vào composite PK.
5. Ghi registry và telemetry trong cùng transaction hoặc cơ chế nhất quán được kiểm chứng.
6. Backfill thay đổi dữ liệu kỳ cũ làm rollup được tính lại/đánh dấu stale.
7. Retention không xóa partition trước khi hết kỳ dữ liệu được phép và hết các legal hold cần áp dụng.
8. Migrate từ bảng không phân vùng không làm mất hàng ở mốc chính xác đầu tháng.
9. Khi chuyển thời gian thiết bị từ local sang UTC, không thay đổi ngữ nghĩa sự kiện.
10. Tất cả tenant và nguồn giữ nguyên ranh giới phân quyền/identity trong dữ liệu phân vùng.

## 20. Bài thực hành: thiết kế hệ thống 2 tỷ bản đo mỗi tháng

Một doanh nghiệp vận hành thiết bị giám sát kho lạnh. Hệ thống thu khoảng **2 tỷ bản đo mỗi tháng** từ nhiều tenant; 70% truy vấn xem **24 giờ gần nhất** của một thiết bị, 25% truy vấn xem **báo cáo tháng** theo khu vực và 5% dùng cho điều tra sự cố trong **90 ngày gần nhất**.

Yêu cầu:

- Bản đo chi tiết giữ **90 ngày**, số liệu theo giờ giữ **hai năm**.
- Thiết bị đôi lúc mất mạng và gửi dữ liệu chậm **đến 48 giờ**.
- Một thiết bị có thể gửi lại event_id cũ khi retry.
- Dashboard cần 15 phút/lần cập nhật, đồng thời nhận diện khoảng không có số liệu.
- Khu vực của thiết bị có thể thay đổi, nên báo cáo lịch sử phải dùng **khu vực có hiệu lực tại ngày đo**.
- Một số timestamp thiết bị bị lệch nhiều ngày cần cách ly để xác minh.

Hãy đưa ra thiết kế:

1. **Chọn grain của raw:** một bản đo cho một metric của thiết bị. Nêu bộ khóa (tenant, device, event_id hoặc version nguồn) và miền giá trị.
2. **Phân biệt thời gian:** event_ts, received_at, processed_at, source clock. Giải thích vì sao event_ts hoặc received_at phù hợp với các mẫu query đã nêu.
3. **Chọn kỳ partition:** theo ngày hay tháng? Ước tính trung bình bản đo/ngày và đánh đổi số partition/kích thước. Không chỉ trả lời theo cảm tính.
4. **Đặt biên UTC:** xây khoảng ngày/tháng nửa mở; viết một truy vấn ngày Việt Nam và chỉ ra partition UTC có thể phải đọc.
5. **Tạo PostgreSQL DDL:** bảng cha PARTITION BY RANGE(event_ts), PK phù hợp hạn chế unique, partition con và chỉ mục theo tenant–device–time.
6. **Chống duplicate:** nêu cơ chế registry hoặc sequence nguồn; xử lý retry khi event_id trùng nhưng payload khác.
7. **Late events 48 giờ:** partition cũ có sẵn, xử lý watermark và rollup 15 phút thế nào?
8. **Aggregate:** định nghĩa grain rollup 15 phút, lưu sample_sum/sample_count, tính AVG từ tổng; xử lý bucket trống bằng NULL hay quy tắc cụ thể.
9. **Retention:** làm sao bảo đảm raw 90 ngày, hourly rollup hai năm và không mất dữ liệu do drop partition sớm?
10. **Khu vực lịch sử:** thiết kế quan hệ thiết bị–khu vực có valid_period, temporal join theo event_ts hoặc business date đúng yêu cầu.
11. **Truy vấn:** lấy 24 giờ gần nhất của device, COUNT sự kiện trong tháng, MAX nhiệt độ theo ngày, và báo cáo theo khu vực có hiệu lực.
12. **Chất lượng:** thử biên 00:00, clock skew, duplicate, thiếu partition, late event và thay đổi dimension khu vực.
13. **Đối soát:** so số đo thô với rollup sau một lần backfill; chỉ công bố báo cáo khi phiên bản dữ liệu được xác minh.
14. **Giới hạn:** giải thích vì sao một aggregate hourly không đủ để tìm chính xác bản đo đã vượt ngưỡng ở giây 12:30:15 sau khi raw bị xóa.

**Tiêu chí đạt:** chọn partition từ query/retention, không mất dữ liệu ở biên; uniqueness được định nghĩa theo nguồn; late events và rollup nhất quán; biết giới hạn của downsampling; truy vấn không đánh đồng storage interval với time bucket hay thời gian hệ thống ghi nhận.

## 21. Checklist thiết kế và kết luận

Trước khi triển khai phân vùng chuỗi thời gian, hãy xác nhận:

- **Grain:** mỗi hàng là một bản đo, một sự kiện, một trạng thái hay một snapshot?
- **Mốc thời gian:** event time, ingestion time, valid time và ngày nghiệp vụ đã có định nghĩa tách biệt chưa?
- **Khoảng:** các partition có dùng [from, to), không overlap và không bỏ sót các biên kỳ chưa?
- **Timezone:** ranh giới vật lý là UTC hay lịch địa phương? Các báo cáo theo timezone khác có được tính đúng không?
- **Kích thước:** giờ/ngày/tháng được chọn dựa trên dữ liệu, truy vấn và maintenance chứ không chỉ sở thích?
- **Pruning:** API có điều kiện event_ts trực tiếp, đủ khả năng bỏ partition không liên quan không?
- **Index:** các chỉ mục trong partition phục vụ truy vấn thực tế và không làm ingest quá chậm chứ?
- **Unique:** PK/UNIQUE có bao gồm khóa phân vùng khi engine yêu cầu; event_id có cần dedup toàn cục không?
- **Late arrivals:** backfill và event quá cũ có quy trình xử lý, không âm thầm bỏ mất không?
- **Rollup:** bucket, cửa sổ, sum/count, missing data, cách tính lại và watermark rõ ràng chưa?
- **Retention:** drop/detach/archival được xác nhận, raw và aggregate có thời hạn giữ riêng không?
- **Vận hành:** tạo partition trước kỳ, theo dõi thiếu partition, kiểm tra EXPLAIN, phát hiện skew và retry chưa?
- **Mô hình khác:** nếu dùng document, graph, time-series DB hay lakehouse, các bất biến thời gian và dữ liệu còn được duy trì không?
- **Kiểm chứng:** có ca thử ở đúng đầu/cuối tháng, múi giờ địa phương, timestamp đến muộn, dữ liệu trùng và thiếu bucket không?

**Nguyên tắc cốt lõi:** chia khoảng thời gian là một **quyết định tổ chức dữ liệu**, không phải một phép biến đổi làm thay đổi sự thật nghiệp vụ. Hãy chọn **đúng trục thời gian**, dùng **biên nửa mở**, xác định **mức chia từ truy vấn và vòng đời lưu trữ**, rồi kết hợp pruning, chỉ mục, retention và rollup có ngữ nghĩa rõ ràng. Một mô hình chuỗi thời gian đáng tin phải vừa đọc hiệu quả, vừa giữ đúng dữ liệu ở các mốc ranh giới và có thể giải thích điều gì xảy ra khi bản đo đến muộn hoặc bị điều chỉnh.
