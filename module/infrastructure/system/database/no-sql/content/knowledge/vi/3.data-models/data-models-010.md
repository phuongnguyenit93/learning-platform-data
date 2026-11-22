# Phân biệt cột rộng với lưu trữ cột phục vụ phân tích

Trong NoSQL, **cơ sở dữ liệu cột rộng** (*wide-column store*, đôi khi gọi là *column-family database*) và **lưu trữ theo cột** (*columnar storage*, *column-oriented storage*) dễ bị nhầm vì đều có chữ *column*. Tuy nhiên, hai khái niệm mô tả **hai góc nhìn khác nhau**:

- **Cột rộng** nói chủ yếu về **mô hình dữ liệu và cách truy cập theo khóa**: dữ liệu được tổ chức thành các hàng/phân vùng có nhiều cột, thường gắn với khóa và nhóm cột; phù hợp với truy vấn đã xác định trước, đặc biệt là tìm dữ liệu của một thực thể theo khóa và khoảng thứ tự.
- **Lưu trữ theo cột phục vụ phân tích** nói chủ yếu về **cách tổ chức dữ liệu vật lý để quét nhiều hàng nhưng chỉ cần một số cột**: giá trị của cùng cột được đặt gần nhau trong các khối lưu trữ, tối ưu tổng hợp trên tập dữ liệu lớn.

Đây không phải hai thuật ngữ đồng nghĩa, cũng không phải hai nhóm loại trừ nhau về mặt kỹ thuật. Một sản phẩm có thể kết hợp nhiều ý tưởng về cột, phân vùng, nén và chỉ mục. Điều quan trọng là xác định **khóa truy cập, đơn vị tổ chức dữ liệu và kiểu truy vấn cần tối ưu**.

## 1. Hai câu hỏi xuất phát khác nhau

Giả sử một hệ thống IoT ghi dữ liệu của cảm biến:

| Thiết bị | Thời gian UTC | Khu vực | Nhiệt độ (°C) | Độ ẩm (%) |
| --- | --- | --- | ---: | ---: |
| sensor-17 | 2026-11-14 08:00 | Bắc | 28,5 | 72 |
| sensor-17 | 2026-11-14 08:01 | Bắc | 28,7 | 71 |
| sensor-24 | 2026-11-14 08:00 | Nam | 30,2 | 64 |
| sensor-17 | 2026-11-14 08:02 | Bắc | 28,8 | 70 |
| sensor-24 | 2026-11-14 08:01 | Nam | 30,4 | 63 |

Cùng bảng dữ liệu này có thể phục vụ hai nhu cầu:

**Nhu cầu A — truy cập theo thiết bị:** “Lấy 100 kết quả đo gần nhất của `sensor-17` trong ngày 14/11”. Truy vấn đã biết **thiết bị** và **khoảng thời gian**; chỉ cần một tập nhỏ các bản ghi liên quan. Đây là kiểu truy cập mà thiết kế khóa phân vùng và khóa sắp xếp của một hệ **wide-column** thường hỗ trợ tốt.

**Nhu cầu B — phân tích tổng hợp:** “Tính nhiệt độ trung bình của từng khu vực trong ba tháng, từ hàng trăm triệu kết quả đo”. Truy vấn phải đọc **rất nhiều bản ghi**, nhưng thực tế chỉ cần các cột `region`, `observed_at` và `temperature_c`. Đây là kiểu truy cập mà **columnar storage** được xây dựng để tối ưu.

Nếu chỉ nhìn thấy dữ liệu có năm cột thì chưa biết mô hình nào phù hợp. Cần nhìn **cách truy vấn đọc dữ liệu**, không chỉ hình dạng bảng.

## 2. Wide-column store là gì?

Mô hình **wide-column** phát triển từ cách tổ chức dữ liệu kiểu Bigtable. Thay vì xem bảng là một ma trận chữ nhật mà mọi hàng đều phải có cùng tập giá trị, hệ có thể tổ chức thông tin theo **khóa hàng**, **họ cột** (*column family*) và những cột/ô thuộc từng hàng. Các hàng có thể rất thưa: chỉ lưu những thuộc tính thực sự xuất hiện.

Hệ wide-column hiện đại có nhiều biến thể. **Apache HBase** gần với mô hình hàng–họ cột–tên cột linh hoạt; **Apache Cassandra** thường được gọi là wide-column nhưng sử dụng mô hình CQL với lược đồ cột được khai báo và trọng tâm thiết kế là **partition key** cùng **clustering columns**. Vì thế, không nên áp dụng nguyên văn mô hình cột động của HBase vào mọi bảng Cassandra.

### 2.1. Hình dung theo hàng và họ cột

Ví dụ theo phong cách HBase, mỗi hàng là một thiết bị, với các nhóm thuộc tính:

```text
Row key: sensor-17
  info:region         -> "Bac"
  info:model          -> "M2"
  latest:temperature  -> 28.8
  latest:humidity     -> 70
  latest:battery      -> 89

Row key: sensor-24
  info:region         -> "Nam"
  latest:temperature  -> 30.4
  latest:humidity     -> 63
  # Không có info:model và latest:battery trong ví dụ này.
```

`info` và `latest` là **họ cột**; `region`, `model`, `temperature` là **tên cột/qualifier** trong ví dụ minh họa. Một ô có thể được nhận diện bằng khóa hàng, họ cột, qualifier và phiên bản thời gian theo cách triển khai HBase. Các giá trị thiếu có thể không cần được lưu thành ô rỗng.

Từ **wide** nhấn mạnh rằng một hàng logic có thể có nhiều cột và cấu trúc thưa, chứ **không có nghĩa toàn bộ cột cùng tên từ hàng triệu thiết bị nhất thiết được ghi nối tiếp vào một vùng đĩa** như định dạng phân tích dạng cột.

### 2.2. Partition key và clustering columns trong Cassandra

Với dữ liệu sự kiện theo thời gian, cách phổ biến là thiết kế một bảng **theo truy vấn dự kiến**. Ví dụ CQL:

```sql
CREATE TABLE measurements_by_device_day (
    device_id text,
    event_day date,
    observed_at timestamp,
    event_id uuid,
    region text,
    temperature_c double,
    humidity_percent double,
    PRIMARY KEY ((device_id, event_day), observed_at, event_id)
) WITH CLUSTERING ORDER BY (observed_at DESC, event_id ASC);
```

Ở đây:

- **`(device_id, event_day)`** là **khóa phân vùng ghép**. Các lần đo của cùng thiết bị trong một ngày được nhóm theo một partition logic.
- **`observed_at`, `event_id`** là **clustering columns**. Chúng xác định thứ tự và giúp phân biệt các sự kiện trong cùng partition; `event_id` tránh trùng khóa khi nhiều lần đo có cùng thời điểm.
- **`region`, `temperature_c`, `humidity_percent`** là các thuộc tính được trả về trong truy vấn; chúng không tự động quyết định partition.

Một truy vấn phù hợp với mô hình khóa:

```sql
SELECT observed_at, temperature_c, humidity_percent
FROM measurements_by_device_day
WHERE device_id = 'sensor-17'
  AND event_day = '2026-11-14'
  AND observed_at >= '2026-11-14T08:00:00Z'
  AND observed_at <  '2026-11-14T09:00:00Z'
LIMIT 100;
```

Điểm quan trọng không nằm ở cú pháp SQL giống nhau, mà ở **đường truy cập**: hệ xác định được partition từ khóa, sau đó đọc một đoạn có thứ tự trong partition đó. Hệ Cassandra sử dụng cấu trúc lưu trữ và chỉ mục nội bộ phù hợp với định tuyến partition và clustering; gọi đây là wide-column **không đồng nghĩa** với việc mỗi trường có một tệp cột giống Parquet.

### 2.3. Tại sao lại chia theo ngày?

Nếu chỉ dùng `device_id` làm partition key, thiết bị hoạt động nhiều năm có thể sinh một partition rất lớn. Thêm `event_day` giúp giới hạn kích thước theo một khoảng thời gian hữu hạn. Đổi lại, truy vấn lịch sử ba ngày cần đọc ba partition; truy vấn toàn năm có thể cần đọc rất nhiều partition.

Thiết kế này thể hiện một nguyên tắc của wide-column: **mô hình dữ liệu chịu ảnh hưởng trực tiếp từ các đường truy vấn chính**. Người thiết kế cân đối kích thước partition, độ phân bố tải, thứ tự dữ liệu và những truy vấn cần thực hiện.

## 3. Lưu trữ theo cột phục vụ phân tích là gì?

**Columnar storage** là cách bố trí dữ liệu sao cho **các giá trị của cùng một cột được lưu gần nhau**, thường theo từng khối hoặc nhóm hàng. Mục tiêu là đọc hiệu quả một số trường trong **rất nhiều bản ghi**, thường gặp ở **OLAP** (*Online Analytical Processing*), kho dữ liệu và hệ phân tích.

Một ví dụ dữ liệu logic gồm ba hàng:

```text
Hàng 1: (sensor-17, Bac, 28.5, 72)
Hàng 2: (sensor-17, Bac, 28.7, 71)
Hàng 3: (sensor-24, Nam, 30.2, 64)
```

Nếu đặt gần nhau theo hàng, có thể hình dung:

```text
Row-oriented layout (minh họa):
[sensor-17 | Bac | 28.5 | 72]
[sensor-17 | Bac | 28.7 | 71]
[sensor-24 | Nam | 30.2 | 64]
```

Nếu đặt theo cột, cách hình dung thay đổi:

```text
Column-oriented layout (minh họa):
device_id     -> [sensor-17, sensor-17, sensor-24]
region        -> [Bac,       Bac,       Nam]
temperature_c -> [28.5,      28.7,      30.2]
humidity      -> [72,        71,        64]
```

Khi cần tính trung bình nhiệt độ, hệ chủ yếu đọc các giá trị của `temperature_c`, cùng những cột cần cho lọc và nhóm; không nhất thiết phải tải nội dung `humidity` hoặc `device_id` nếu truy vấn không sử dụng chúng. Đó là **column pruning** hoặc **projection pushdown**: tránh đọc các cột không cần thiết.

### 3.1. Vì sao đọc theo cột hữu ích cho OLAP?

Giả sử có 100 triệu hàng với 30 trường, nhưng báo cáo chỉ dùng `event_day`, `region`, `temperature_c`. Trong một bố cục thiên về hàng, việc đọc nhiều hàng có thể kéo theo nhiều trường không cần dùng. Trong một bố cục cột, hệ có cơ hội chỉ đọc ba cột liên quan.

Ngoài việc giảm dữ liệu cần đọc, tổ chức theo cột còn hỗ trợ:

| Kỹ thuật | Tại sao có ích |
| --- | --- |
| **Nén theo cột** | Các giá trị cùng kiểu, thường có phân bố và quy luật lặp giống nhau, thuận lợi cho dictionary encoding, run-length encoding, delta encoding và các bộ mã hóa khác. |
| **Đọc và xử lý theo vector/lô** | Hệ có thể áp dụng phép so sánh, tính tổng, trung bình trên một lô giá trị liên tiếp, giảm chi phí xử lý từng hàng riêng lẻ. |
| **Column pruning** | Nếu truy vấn chỉ cần vài cột, bỏ qua nhiều khối cột khác. |
| **Predicate pushdown** | Đưa bộ lọc xuống lớp đọc dữ liệu; kết hợp thống kê min/max hoặc metadata để tránh đọc một số nhóm dữ liệu không phù hợp. |
| **Late materialization** | Chỉ ghép lại các trường thành hàng/đối tượng đầy đủ khi thực sự cần, thay vì tái tạo toàn bộ hàng ngay từ đầu. |

Các tối ưu này tùy hệ lưu trữ và bộ máy truy vấn. Không phải mọi định dạng hoặc database theo cột đều hỗ trợ mọi tính năng như nhau, và không phải truy vấn nào cũng có thể bỏ qua phần lớn dữ liệu.

### 3.2. Parquet tổ chức cột như thế nào?

**Apache Parquet** là một **định dạng tệp lưu trữ theo cột**, không phải bản thân một hệ quản trị cơ sở dữ liệu. Nó được dùng trong data lake và các bộ máy phân tích.

```text
Tệp Parquet
  ├── Row group 1 (một nhóm hàng)
  │    ├── Column chunk: device_id
  │    ├── Column chunk: region
  │    ├── Column chunk: temperature_c
  │    └── Column chunk: humidity_percent
  ├── Row group 2
  │    ├── Column chunk: device_id
  │    ├── Column chunk: region
  │    ├── Column chunk: temperature_c
  │    └── Column chunk: humidity_percent
  └── Metadata: schema, thông tin row group và cột
```

Trong thực tế, mỗi *column chunk* có thể gồm nhiều trang và được nén/mã hóa; metadata hỗ trợ bộ đọc chọn lọc. Parquet **không yêu cầu mọi giá trị của một cột trong toàn bộ kho dữ liệu nằm trong một dải liên tục duy nhất**. Dữ liệu được nhóm theo file, row group và các đơn vị tổ chức nhỏ hơn.

**Apache ORC** cũng là định dạng file theo cột. Các hệ như **ClickHouse** tổ chức dữ liệu bằng các cấu trúc lưu trữ cột phục vụ truy vấn phân tích; **DuckDB** có bộ máy thực thi phân tích theo vector và có thể đọc dữ liệu cột như Parquet. Cần phân biệt **định dạng file** (Parquet/ORC), **bộ máy truy vấn** và **cơ sở dữ liệu**: chúng là các tầng kỹ thuật khác nhau dù cùng có thể tham gia một hệ phân tích.

### 3.3. Ví dụ truy vấn phân tích

Khi tập dữ liệu đã được đưa vào một kho phân tích, truy vấn có thể là:

```sql
SELECT
    region,
    DATE_TRUNC('day', observed_at) AS report_day,
    AVG(temperature_c) AS avg_temperature,
    COUNT(*) AS sample_count
FROM measurements
WHERE observed_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND observed_at <  TIMESTAMP '2026-12-01 00:00:00'
GROUP BY region, DATE_TRUNC('day', observed_at)
ORDER BY report_day, region;
```

Đây là SQL minh họa; cách viết `DATE_TRUNC` và kiểu thời gian phụ thuộc engine. Truy vấn không biết trước `device_id` cụ thể, nên hệ phải xử lý dữ liệu trên nhiều thiết bị. Lợi thế của columnar nằm ở việc chỉ cần các cột thời gian, khu vực và nhiệt độ để lọc, nhóm và tổng hợp, thay vì đọc tất cả thuộc tính của từng sự kiện.

## 4. Đặt hai cách tiếp cận cạnh nhau

| Khía cạnh | Wide-column store | Columnar storage phục vụ phân tích |
| --- | --- | --- |
| **Thuộc lớp khái niệm** | Mô hình dữ liệu và truy cập trong một họ NoSQL | Bố cục lưu trữ/đọc dữ liệu, thường dùng trong OLAP |
| **Câu hỏi cốt lõi** | “Tìm những bản ghi nào theo khóa và thứ tự?” | “Quét những cột nào trên số lượng lớn bản ghi?” |
| **Đơn vị truy cập chủ đạo** | Partition/row theo khóa; phạm vi clustering hoặc qualifier | Khối dữ liệu của từng cột trong file/part/row group |
| **Tổ chức cột** | Cột thuộc một hàng hoặc partition; có thể nằm trong column family | Giá trị cùng cột được gom để đọc và nén theo cột |
| **Truy vấn điển hình** | Lịch sử của một người dùng/thiết bị, tra cứu theo khóa, sự kiện trong một khoảng | `SUM`, `AVG`, `COUNT`, `GROUP BY` trên hàng triệu đến tỷ bản ghi |
| **Kiểu tải thường gặp** | Nhiều ghi/đọc theo khóa với độ trễ được kiểm soát | Quét, lọc, tổng hợp và phân tích lượng dữ liệu lớn |
| **Thiết kế quan trọng** | Partition key, clustering, phân bố tải, kích thước partition | Sắp xếp, phân vùng dữ liệu phân tích, nén, kích thước khối, chỉ mục/thống kê |
| **Chi phí cần xem xét** | Partition nóng, truy vấn thiếu khóa, truy vấn xuyên nhiều partition | Ghi/cập nhật rất nhỏ liên tục, lấy toàn bộ một hàng ở vị trí bất kỳ, quét quá nhiều dữ liệu |
| **Ví dụ** | Apache Cassandra, Apache HBase, Google Bigtable | Parquet, ORC, ClickHouse, kho dữ liệu phân tích dùng tổ chức cột |

Bảng trên phản ánh các khuynh hướng **thường thấy**, không phải quy tắc tuyệt đối: wide-column có thể tham gia pipeline phân tích và các hệ columnar hiện đại cũng có thể nạp dữ liệu liên tục, hỗ trợ chỉ mục hoặc truy vấn gần thời gian thực. Hiệu năng thực tế phụ thuộc sản phẩm, thiết kế khóa, dữ liệu, phần cứng và cấu hình.

## 5. Sơ đồ: “Rộng theo khóa” khác “dọc theo cột”

Một cách nhìn trực quan là cùng lưu năm sự kiện nhưng với hai mục tiêu khác nhau.

**Mô hình truy cập kiểu wide-column:**

```text
Khóa phân vùng (device_id, event_day)
│
├── (sensor-17, 2026-11-14)
│   ├── 08:02 -> {temp: 28.8, humidity: 70, region: Bac}
│   ├── 08:01 -> {temp: 28.7, humidity: 71, region: Bac}
│   └── 08:00 -> {temp: 28.5, humidity: 72, region: Bac}
│
└── (sensor-24, 2026-11-14)
    ├── 08:01 -> {temp: 30.4, humidity: 63, region: Nam}
    └── 08:00 -> {temp: 30.2, humidity: 64, region: Nam}

Tìm sensor-17 -> xác định partition -> đọc các mốc giờ liên tiếp.
```

**Bố cục đọc kiểu columnar:**

```text
Một row group chứa các sự kiện tương ứng
│
├── device_id     [sensor-17, sensor-17, sensor-24, sensor-17, sensor-24]
├── observed_at   [08:00,     08:01,     08:00,     08:02,     08:01]
├── region        [Bac,       Bac,       Nam,       Bac,       Nam]
├── temperature_c [28.5,      28.7,      30.2,      28.8,      30.4]
└── humidity      [72,        71,        64,        70,        63]

Tính AVG(temp) theo region -> đọc region + temperature_c,
và observed_at nếu có lọc theo thời gian; bỏ qua cột không dùng.
```

Ở ví dụ thứ nhất, dữ liệu được trình bày theo **đường đi từ khóa tới những bản ghi có liên quan**. Ở ví dụ thứ hai, dữ liệu được trình bày theo **cách gom các giá trị của từng thuộc tính để quét và tính toán**. Đây là hai trục tư duy độc lập; ví dụ chỉ là sơ đồ khái niệm, không mô tả nguyên vẹn byte trên đĩa của Cassandra, HBase hay Parquet.

## 6. Tên gọi “column family” gây nhầm như thế nào?

**Column family** xuất hiện trong các hệ kiểu Bigtable/HBase và trong lịch sử thiết kế Cassandra. Nó **không đồng nghĩa** với thuật ngữ **column chunk** trong định dạng file phân tích.

| Tên gọi | Bối cảnh | Ý nghĩa thực dụng |
| --- | --- | --- |
| **Column family** | HBase/Bigtable và một số mô hình wide-column | Nhóm các cột/qualifier liên quan trong mô hình lưu trữ của hệ đó; quy tắc vật lý tùy hệ. |
| **Partition key** | Cassandra, DynamoDB và nhiều hệ phân tán | Khóa hoặc thành phần khóa dùng để quyết định nhóm và vị trí dữ liệu. |
| **Clustering column** | Cassandra và một số hệ tương tự | Trường tham gia tổ chức thứ tự trong partition và khóa chính ghép. |
| **Column chunk** | Parquet | Dữ liệu của một cột trong một row group của file. |
| **Column pruning** | Engine đọc file/database cột | Bỏ đọc các cột không được dùng bởi truy vấn. |
| **Column-store / column database** | Thuật ngữ dễ bị dùng rộng | Phải đọc ngữ cảnh để biết đang nói về wide-column NoSQL hay hệ cột phục vụ OLAP. |

Vì vậy, khi tài liệu nói “database stores data by columns”, nên hỏi tiếp: **cột nào được nhóm với cột nào, theo khóa hàng hay theo một tập nhiều hàng, và cách đó giúp kiểu truy vấn gì?** Câu trả lời này đáng tin hơn việc đoán từ tên sản phẩm hoặc chữ *column*.

## 7. Định hướng thiết kế theo workload

Hai hệ thống có thể lưu cùng một cấu trúc sự kiện, nhưng tối ưu cho hai con đường truy vấn khác nhau.

### Trường hợp A: ứng dụng xem lịch sử một thiết bị

API:

```http
GET /devices/sensor-17/measurements?day=2026-11-14&limit=100
```

Một bảng wide-column theo khóa `(device_id, event_day)` và sắp xếp theo `observed_at` có thể cung cấp đường đọc trực tiếp đến nhóm sự kiện phù hợp. Với cách này, nên xác định:

1. Mỗi thiết bị tạo bao nhiêu bản ghi trong một ngày và partition lớn đến mức nào?
2. Thiết bị nào tạo tải đột biến hoặc có thể gây **hot partition**?
3. Người dùng có thường xem nhiều ngày, hay chỉ một khoảng gần đây?
4. Có truy vấn nào không có `device_id` hoặc `event_day` không? Nếu có, cần một mô hình đọc khác hay một pipeline phân tích?

Nếu ứng dụng thường cần “100 bản ghi cuối cùng” thì tổ chức theo thiết bị và thời gian là điểm khởi đầu hợp lý. Tuy nhiên, chỉ tạo thêm một chỉ mục cho `region` không mặc nhiên làm truy vấn phân tích toàn hệ thống nhanh như một kho columnar.

### Trường hợp B: nhóm phân tích xem xu hướng khu vực

Báo cáo:

```text
Trong 90 ngày qua:
  - Nhiệt độ trung bình theo vùng, theo giờ
  - Số lượng sự kiện theo từng ngày
  - Top 10% thiết bị có nhiệt độ cao nhất
```

Đây là các truy vấn **quét nhiều thiết bị**, **lọc tập lớn** và **tổng hợp nhiều bản ghi**. Định dạng lưu trữ cột giúp đọc chọn lọc các trường và tính toán theo lô. Thiết kế cần cân nhắc kích thước file/part, chiến lược phân vùng thời gian, sắp xếp dữ liệu, metadata lọc, nén và chi phí nhập dữ liệu.

**Phân vùng trong OLAP cũng không đồng nghĩa với partition key của wide-column.** Ví dụ, một bảng Parquet có thể được chia các thư mục `year=2026/month=11/`, giúp bộ máy bỏ qua những khoảng thời gian không cần đọc. Còn partition key `(device_id, event_day)` của Cassandra phục vụ định tuyến tới các partition logic của hệ. Cùng từ *partition*, nhưng cấp độ và cách sử dụng khác nhau.

### Trường hợp C: vừa phục vụ API vừa cần dashboard

Không nhất thiết ép một cấu trúc lưu trữ xử lý cả hai công việc. Một kiến trúc có thể là:

```text
Thiết bị / ứng dụng
       |
       v
Luồng sự kiện / API ghi
       |
       +------------------------------+
       |                              |
       v                              v
Wide-column database             Pipeline ETL/stream
(đọc theo khóa thiết bị)               |
       |                              v
       v                       Parquet/ORC hoặc
API xem lịch sử                 kho phân tích columnar
                                      |
                                      v
                                Dashboard / OLAP
```

Trong thực tế, pipeline có thể lấy dữ liệu từ nguồn ghi, từ log thay đổi hoặc từ luồng sự kiện; sơ đồ chỉ minh họa một cấu hình khả dĩ. Khi sử dụng hai kho dữ liệu, cần xử lý **độ trễ đồng bộ**, **ghi lặp**, **sự kiện đến muộn**, **thay đổi schema** và **quy tắc cập nhật/xóa** để dashboard có số liệu đáng tin cậy.

Kiến trúc một hoặc hai hệ phụ thuộc yêu cầu nghiệp vụ và chi phí vận hành. Điểm cần giữ là **chọn đường truy cập cho từng công việc**, không bắt buộc chọn công nghệ chỉ vì nhãn NoSQL hoặc SQL.

## 8. Các hiểu lầm thường gặp

### “Wide-column là columnar, nên quét báo cáo phải nhanh”

Không thể suy ra như vậy. Hệ wide-column được định hướng bởi mô hình khóa và phân vùng. Một báo cáo theo `region` chạy trên mọi thiết bị có thể phải đọc nhiều partition nếu không được hỗ trợ bởi một cấu trúc hay pipeline riêng. Hệ columnar chuyên phân tích có lợi thế vì bố trí những thuộc tính dùng trong báo cáo theo cột.

### “Columnar chỉ dành cho SQL, wide-column chỉ dành cho NoSQL”

Đây là hai trục phân loại khác nhau. SQL là ngôn ngữ truy vấn; NoSQL là một nhóm mô hình/công nghệ dữ liệu. Cassandra dùng CQL có cú pháp giống SQL nhưng không có cùng ngữ nghĩa truy vấn tùy ý như cơ sở dữ liệu quan hệ. Ngược lại, ClickHouse có giao diện truy vấn SQL và sử dụng lưu trữ cột. Parquet là file format và có thể được đọc bằng nhiều ngôn ngữ hoặc công cụ khác nhau.

### “Dữ liệu hình bảng thì lưu theo cột là đủ”

Hình dạng hàng–cột chỉ mô tả dữ liệu logic. Một bảng có thể được lưu theo hàng, theo cột, theo khóa–giá trị hoặc bằng nhiều cấu trúc nội bộ. Cách tổ chức phải được xét cùng các câu hỏi: **đọc một hàng hay nhiều hàng**, **cần bao nhiêu cột**, **tần suất cập nhật**, **cách lọc** và **mức độ phân tán**.

### “Số cột càng nhiều thì wide-column càng phù hợp”

Số lượng cột tự nó không quyết định mô hình tốt. Một bảng phân tích có hàng trăm cột thưa vẫn có thể được xử lý hiệu quả trong một hệ columnar nếu truy vấn chỉ lấy một số trường. Một cơ sở dữ liệu wide-column có thể thích hợp cả khi mỗi sự kiện chỉ có vài trường, miễn cách truy vấn theo partition/clustering phù hợp.

### “Lưu trữ theo cột không thể ghi liên tục hoặc tra cứu từng bản ghi”

Các hệ columnar hiện đại có thể hỗ trợ nhập dữ liệu liên tục, lập chỉ mục và truy vấn chọn lọc, nhưng chi phí thường phụ thuộc cách gom batch, hợp nhất part, sắp xếp và bảo trì dữ liệu. Không nên biến xu hướng tối ưu OLAP thành một giới hạn tuyệt đối. Cần đo hiệu năng với workload cụ thể.

### “Phân mảnh, replication và columnar là một cơ chế”

**Sharding/partitioning** phân phối các phần dữ liệu, **replication** lưu các bản sao để tăng độ sẵn sàng và **columnar storage** quyết định cách dữ liệu được bố trí theo cột. Một hệ phân tán có thể áp dụng cả ba cùng lúc, nhưng chúng giải quyết những vấn đề khác nhau.

## 9. Chọn giải pháp bằng các câu hỏi thực tế

Thay vì hỏi “dữ liệu có bao nhiêu cột?”, hãy lần lượt xác định:

| Câu hỏi | Nếu câu trả lời thường là… | Hướng nên xem xét |
| --- | --- | --- |
| Truy vấn có biết **khóa thực thể** trước không? | Có, phần lớn truy vấn bắt đầu từ user/device/account cụ thể | Thiết kế wide-column theo khóa/phân vùng có thể phù hợp |
| Cần đọc bao nhiêu bản ghi cho một truy vấn? | Ít bản ghi trong một partition hoặc một phạm vi nhỏ | Ưu tiên đường đọc theo khóa và thứ tự |
| Cần bao nhiêu trường trên tổng số trường? | Chỉ vài trường, nhưng quét hàng triệu hàng | Columnar có lợi thế đọc chọn lọc theo cột |
| Có thường `GROUP BY`, `SUM`, `AVG`, thống kê nhiều chiều không? | Có, trên phạm vi rất lớn | Engine OLAP và tổ chức cột là ứng viên tự nhiên |
| Có phải cập nhật/xóa từng thực thể liên tục? | Có, với yêu cầu độ trễ thấp | Kiểm tra khả năng ghi/cập nhật và đọc theo khóa của hệ được chọn |
| Có nguy cơ tập trung dữ liệu ở một khóa? | Một số thiết bị/người dùng cực lớn | Thiết kế lại partition hoặc bucket, bất kể sản phẩm |
| Có cần cả API và dashboard? | Có, đường đọc rất khác nhau | Đánh giá hai mô hình phục vụ hoặc một engine hỗ trợ cả hai, cùng chi phí đồng bộ |

Không có nhãn công nghệ nào thay thế được **truy vấn thực tế và phép đo trên dữ liệu đại diện**. Hãy tính cả độ trễ yêu cầu, thông lượng ghi, lưu lượng quét, chi phí lưu trữ, cập nhật, bảo trì và tính nhất quán dữ liệu.

## 10. Bài tập tự kiểm tra

**Bài 1.** Hệ thống có 50 triệu lượt thanh toán, mỗi lượt có 25 thuộc tính. Một báo cáo tính tổng `amount` theo `payment_method` trong một quý. Báo cáo chỉ dùng ba trường: thời gian, phương thức và số tiền. Nên liên hệ kiểu lưu trữ nào trước?

**Gợi ý đáp án:** Columnar storage/OLAP, vì truy vấn đọc rất nhiều hàng nhưng chỉ dùng một số cột để lọc và tổng hợp. Partitioning theo quý/tháng, metadata và chỉ mục phù hợp có thể giúp giảm phạm vi đọc.

**Bài 2.** API cần trả về 50 giao dịch mới nhất của `account-123` mỗi lần người dùng mở màn hình. Thiết kế `partition key = account_id`, `clustering key = transaction_time` có giải quyết đúng nhu cầu không?

**Gợi ý đáp án:** Đây là một mô hình truy cập phù hợp cho wide-column. Tuy nhiên vẫn cần cân nhắc khóa phụ chống trùng thời gian, kích thước partition, số giao dịch của tài khoản và thời gian lưu. Một tài khoản phát sinh lượng giao dịch cực lớn có thể cần bucket thời gian.

**Bài 3.** Một bảng Cassandra có các cột `region`, `amount`, `created_at` và hơn 100 triệu row. Có thể khẳng định hệ chỉ đọc cột `amount` khi chạy thống kê doanh thu toàn quốc như với Parquet không?

**Gợi ý đáp án:** Không. Tên cột và hình dạng bảng không chứng minh bố cục vật lý hay đường thực thi truy vấn. Cần xét khóa phân vùng, khả năng truy vấn, sơ đồ dữ liệu và engine xử lý. Với thống kê toàn cục, thường phải thiết kế thêm bảng phục vụ truy vấn hoặc pipeline phân tích.

**Bài 4.** Một file Parquet có hai row group, mỗi nhóm lưu các column chunk riêng. Có phải mọi giá trị `region` của toàn file nằm liên tục trong đúng một đoạn duy nhất?

**Gợi ý đáp án:** Không. Parquet tổ chức theo row group, mỗi row group có column chunk của từng cột. Giá trị cùng cột được nhóm **trong mỗi đơn vị lưu trữ phù hợp**, không nhất thiết trải dài liên tục trên toàn bộ file hoặc toàn bộ data lake.

**Bài 5.** Một nhóm nói: “Vì hệ có replication factor = 3 nên ba truy vấn `AVG` chạy đồng thời sẽ nhanh gấp ba”. Lập luận thiếu gì?

**Gợi ý đáp án:** Replication factor nói về bản sao, không bảo đảm khả năng song song hóa truy vấn hay tăng thông lượng tuyến tính. Phải xét bộ máy truy vấn, vị trí dữ liệu, điều phối, tài nguyên và cách phân chia công việc. Replication và columnar giải quyết những bài toán khác nhau.

## 11. Ghi nhớ theo đường đi của truy vấn

Hãy tưởng tượng **wide-column** như một thư viện được bố trí để bạn biết ngay **ngăn của một thiết bị/khách hàng**, rồi đọc những sự kiện liên tiếp trong ngăn đó. Còn **columnar storage** giống một hệ thống gom **cùng loại thông tin** của rất nhiều bản ghi thành các phần dễ quét và tính toán, để thống kê trên toàn bộ thư viện mà không cần xem mọi chi tiết của từng bản ghi.

Khi gặp từ *column* trong tài liệu hệ cơ sở dữ liệu, hãy xác định rõ câu hỏi đang được trả lời: **tổ chức dữ liệu theo khóa để tìm một nhóm bản ghi**, hay **tổ chức giá trị theo cột để phân tích một tập bản ghi lớn**. Sự phân biệt này giúp lựa chọn mô hình NoSQL, thiết kế truy vấn và kiến trúc phân tích đúng mục đích.
