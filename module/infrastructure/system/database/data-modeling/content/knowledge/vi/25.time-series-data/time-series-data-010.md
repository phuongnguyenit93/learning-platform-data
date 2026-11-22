# Mô hình nhiệt độ thiết bị hoặc chỉ số vận hành theo nhu cầu đọc

## 1. Đặt câu hỏi truy vấn trước khi chọn cấu trúc lưu chuỗi thời gian

Trong module `DATABASE_DATA_MODELING`, người học rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ, ràng buộc và chuẩn hóa đến khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh cách lưu quan hệ, document, đồ thị và phân tích. Với chương **Dữ liệu chuỗi thời gian**, quyết định quan trọng không phải chỉ là “có cột `timestamp`”, mà là **cần đọc gì, trong khoảng nào, ở độ phân giải nào và với mức chính xác nào**.

Giả sử một nhà máy giám sát 20.000 thiết bị. Mỗi thiết bị đo nhiệt độ mỗi 10 giây, một số thiết bị còn gửi độ ẩm, số vòng quay, điện năng tích lũy và trạng thái kết nối. Nhóm vận hành đặt ra những câu hỏi khác nhau:

- “Nhiệt độ **mới nhất** của thiết bị D-100 là bao nhiêu? Giá trị đó có quá cũ không?”
- “Trong **24 giờ qua**, nhiệt độ thiết bị D-100 biến động thế nào để vẽ biểu đồ 5 phút?”
- “Có thiết bị nào **vượt 85 °C** trong 10 phút gần đây không?”
- “Trong tháng trước, **nhiệt độ cao nhất** của từng dây chuyền là bao nhiêu?”
- “Điện năng tiêu thụ theo giờ là bao nhiêu, biết cảm biến gửi **chỉ số đồng hồ tích lũy**?”
- “Khi dữ liệu đến muộn hoặc thiết bị đổi vị trí, báo cáo lịch sử phải được tính lại ra sao?”

Một bảng lưu “giá trị mới nhất” có thể trả lời câu đầu rất nhanh nhưng **không đủ lịch sử** để dựng xu thế. Một bảng thô chứa tất cả phép đo trả lời được lịch sử nhưng không nhất thiết thích hợp để liên tục quét hàng tỷ bản ghi cho dashboard. Một bảng tổng hợp 5 phút giảm chi phí đọc nhưng có thể làm mất đỉnh nhiệt độ ngắn hoặc thứ tự sự kiện.

Mục tiêu là thiết kế **các biểu diễn phù hợp với những đường đọc cụ thể** và biết dữ liệu nào là **nguồn sự thật**.

### Kết quả học tập

Sau bài này, người học có thể:

1. Định nghĩa grain của mẫu đo theo tenant, thiết bị, loại chỉ số và thời điểm; phân biệt mẫu mới với retry hoặc điều chỉnh.
2. Phân biệt metric loại **gauge**, **counter**, **delta** và **state**, tránh tính tổng/trung bình sai.
3. Chọn giữa bảng **wide**, bảng **narrow/long**, document payload và bảng tổng hợp theo workload.
4. Thiết kế truy vấn **latest value**, lịch sử chi tiết, bucket 5 phút, phát hiện ngưỡng và thống kê theo thiết bị/nhóm.
5. Xử lý event time, received time, timezone, gap, dữ liệu trễ, bản ghi trùng, cảm biến lỗi và thay đổi metadata.
6. Xây ràng buộc, partition, chỉ mục và rollup bằng PostgreSQL 16; nêu được giới hạn khi chuyển sang time-series engine hoặc kho phân tích.
7. Kiểm chứng bằng `EXPLAIN`, kiểm thử biên, đối soát số mẫu và chiến lược retention/khôi phục.

## 2. Ma trận mẫu đọc quyết định mô hình vật lý

Trước khi viết DDL, hãy tập hợp **mẫu truy cập**, tần suất và điều kiện lọc:

| Mẫu đọc | Phạm vi | Thời gian/độ phân giải | Cấu trúc thường hữu ích |
|---|---|---|---|
| A. Giá trị mới nhất của một thiết bị | Một `device_id` và `metric_code` | Một điểm mới nhất, đòi kiểm tra độ mới | Index theo device–metric–time; bảng `latest` nếu dashboard truy cập dày đặc |
| B. Đường nhiệt độ của một thiết bị | Một device/metric | 24 giờ, chart 5 phút | Raw readings lọc thời gian hoặc rollup 5 phút |
| C. Tìm điểm vượt ngưỡng | Một nhóm thiết bị/tenant | 10 phút gần nhất, cần giữ đỉnh | Raw hoặc rollup có `MAX` và metadata chất lượng |
| D. Báo cáo dây chuyền theo ngày | Hàng trăm/nghìn device | Một tháng, tổng hợp | Rollup giờ/ngày + lịch sử thiết bị thuộc dây chuyền |
| E. Tổng điện năng | Một hoặc nhiều meter | Hiệu số counter theo giờ, phát hiện reset | Dữ liệu counter có thứ tự; delta/rate đã chuẩn hóa |
| F. Điều tra sự cố | Một device, nhiều metric | Raw quanh một mốc, thứ tự sự kiện chính xác | Raw append/immutable, timestamp, nguồn và provenance |
| G. Quản lý retention | Toàn bộ nhà máy | Xóa raw sau 90 ngày, rollup giữ 2 năm | Partition thời gian, quy trình archive và kiểm thử |

**Không có một index hay một bảng duy nhất tối ưu hoàn hảo A–G.** Thiết kế có thể gồm bảng raw, một bảng trạng thái mới nhất, bảng rollup và dimension thiết bị. Đó không phải nhân bản tùy tiện nếu mỗi biểu diễn có **mục đích, nguồn cập nhật và quy trình đối soát** riêng.

## 3. Phân loại metric: nhiệt độ không giống chỉ số công tơ

Đơn vị, cách đo và toán tử tổng hợp phải gắn với định nghĩa metric, không đoán từ tên cột.

| Loại metric | Ví dụ | Cách đọc/cộng đúng | Sai lầm phổ biến |
|---|---|---|---|
| **Gauge** – giá trị tức thời | Nhiệt độ °C, độ ẩm %, áp suất, CPU usage | Latest, `MIN`, `MAX`, trung bình theo **quy tắc lấy mẫu** | Cộng tất cả nhiệt độ rồi gọi đó là “nhiệt độ của ca” |
| **Cumulative counter** – bộ đếm tích lũy | Tổng kWh, tổng byte mạng, tổng lượt sản xuất | Lấy **chênh lệch hợp lệ giữa hai mốc**, xử lý reset/rollover | `SUM(counter_value)` để tính lượng tiêu thụ |
| **Delta/event count** – lượng phát sinh | Số lỗi trong một khoảng, số sản phẩm vừa hoàn thành | `SUM` qua khoảng không trùng và đúng grain | Cộng một delta nhiều lần do retry hoặc gối cửa sổ |
| **State** – trạng thái | ONLINE/OFFLINE, RUNNING/STOPPED, mã lỗi | As-of state, thời lượng theo từng state, số lần chuyển trạng thái | `AVG(state_code)` rồi diễn giải như một chỉ số vật lý |
| **Distribution/histogram** | Histogram latency, tần suất theo dải | Gộp các bucket tương thích rồi suy percentile | Lấy trung bình p95 của các máy để suy p95 toàn hệ thống |

**Gauge có thể có giá trị âm** (nhiệt độ), nhưng counter tích lũy thường không âm và có thể reset. Kiểm tra miền giá trị phải theo **loại metric cụ thể**. Một constraint chung kiểu `value >= 0` sẽ làm mất số đo nhiệt độ dưới 0 °C.

### Đơn vị và nguồn hiệu chuẩn

Một thiết bị có thể gửi 86 °F, trong khi hệ thống chuẩn hóa thành 30 °C; hoặc gửi giá trị ADC cần phép chuyển đổi từ cấu hình hiệu chuẩn đang có hiệu lực. Phải lưu rõ:

- **Đơn vị canonical** của từng metric, ví dụ `degC`, `percent`, `Wh`, `rpm`.
- **Đơn vị gốc**, giá trị gốc và phiên bản quy tắc chuyển đổi khi cần đối soát.
- **Giới hạn vật lý/nghiệp vụ** và cách đánh dấu số liệu nghi ngờ.
- **Phiên bản hiệu chuẩn** nếu tính lại số đo lịch sử là yêu cầu.

Không trộn °C với °F hoặc Wh với kWh trong cùng một chuỗi rồi vẽ biểu đồ như dữ liệu đồng nhất. Một giá trị đã được đổi đơn vị mà không lưu provenance có thể khó đối soát khi phát hiện sai cấu hình cảm biến.

## 4. Grain và định danh của một mẫu đo

Một lựa chọn cho chuỗi nhiệt độ:

> Một hàng raw biểu diễn **một mẫu đo đã được chuẩn hóa** cho một tenant, một thiết bị, một loại metric tại một thời điểm sự kiện do thiết bị công bố; các lần gửi lại cùng mẫu phải không tạo thêm hàng.

Theo giả định thiết bị tạo **tối đa một phép đo cho mỗi** bộ (`tenant_id`, `device_id`, `metric_code`, `observed_at`), grain có thể dùng khóa duy nhất đó. Đây là **một giả định hợp đồng nguồn**, không phải chân lý của dữ liệu chuỗi thời gian.

### Khi timestamp không đủ để định danh

Có các ngoại lệ:

- Thiết bị gửi **hai mẫu hợp lệ cùng timestamp** vì độ chính xác đồng hồ chỉ tới giây.
- Hai cảm biến bên trong một thiết bị đo cùng metric nhưng ở các vị trí khác nhau.
- Hệ nguồn sửa lại thời gian của cùng một event sau khi đồng bộ.
- Một gói telemetry chứa nhiều metric hoặc nhiều mẫu, và cần truy vết **message ID**.

Khi đó, grain phải thay đổi để có `sensor_id`/`channel_id`, `source_sample_id` hoặc `sequence_number` theo namespace phù hợp. **Không dùng `received_at` làm thành phần unique một cách tùy tiện**, vì cùng event được gửi lại có thể có thời gian nhận khác và bị tính trùng.

| Khóa | Vai trò | Không bảo đảm điều gì? |
|---|---|---|
| (`tenant_id`, `device_id`, `metric_code`, `observed_at`) | Định danh một điểm theo hợp đồng một-mẫu-mỗi-thời-điểm | Không phù hợp nếu nguồn phát nhiều mẫu hợp lệ cùng mốc |
| (`source_system`, `source_message_id`) trong tenant | Idempotency của gói nguồn | Một gói có thể chứa **nhiều** mẫu/metric |
| `source_sample_id` hoặc (`message_id`, `item_index`) | Định danh từng mẫu khi timestamp trùng | Không tự diễn tả ngày/metric hoặc đảm bảo phép đo đúng đơn vị |
| `reading_sk` do kho tự sinh | Định danh vật lý hàng | Không tự phát hiện retry nếu nguồn gửi lại |

Hãy phân biệt **khóa duy nhất của mẫu** với **khóa của gói đến**. Một gói chứa 12 số đo có thể cần một bản ghi ledger cho gói và 12 hàng mẫu; cả hai cấp đều có idempotency riêng.

## 5. Ba trục thời gian cần kiểm soát

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| `observed_at` | **Event time:** lúc cảm biến đo | 08:00:10 UTC |
| `received_at` | **Ingestion time:** lúc máy chủ nhận/lưu | 08:02:30 UTC |
| `processed_at` hoặc `rollup_refreshed_at` | Lúc pipeline kiểm tra/tổng hợp | 08:03:00 UTC |
| `business_date` | Ngày lịch báo cáo của nhà máy/tenant | Ngày theo `Asia/Ho_Chi_Minh` |
| `calibration_valid_from` | Khi cấu hình hiệu chuẩn có hiệu lực | Có thể khác thời điểm được nhập vào hệ thống |

Một số đo lúc 08:00 nhưng nhập lúc 08:02 **thuộc bucket 08:00** nếu biểu đồ được định nghĩa theo event time. Bucket theo `received_at` trả lời câu “dữ liệu đến lúc nào”, phù hợp giám sát pipeline nhưng không đúng để phân tích nhiệt độ thực tế lúc 08:00.

### Đồng hồ thiết bị không đáng tin tuyệt đối

Nếu thiết bị chạy sai đồng hồ và phát timestamp tương lai hơn thời gian máy chủ 30 phút, không nên âm thầm đổi `observed_at := received_at`. Cần đánh dấu `SUSPECT`/quarantine và có cơ chế phát hiện độ lệch:

\[
\mathrm{ingestion\_delay}=received\_at-observed\_at
\]

Độ trễ âm có thể là clock skew, đồng bộ trước thời gian ghi nhận, hoặc lỗi quy đổi timezone. Cần phân biệt trường hợp có thể chấp nhận với trường hợp phải sửa bằng bằng chứng. Nếu sửa timestamp, phải làm rõ **cùng mẫu gốc** được định danh thế nào sau sửa.

### Timezone và DST

`TIMESTAMPTZ` trong PostgreSQL lưu một thời điểm tuyệt đối; cách hiển thị phụ thuộc timezone phiên. Để tính ngày theo nhà máy, chuyển thời điểm sang múi giờ kinh doanh rồi lấy ngày. Ở vùng có DST, **một ngày lịch có thể không dài đúng 24 giờ**. Không dùng cố định `+ interval '24 hours'` để biểu diễn mọi ngày lịch trên toàn thế giới.

## 6. Chọn wide, narrow hay document theo cách đọc

### 6.1. Wide row: nhiều metric trong một hàng

```text
device_snapshot_raw
tenant_id | device_id | observed_at | temperature_c | humidity_pct | rpm
----------+-----------+-------------+---------------+--------------+-----
42        | 100       | 08:00:10    | 31.2          | 60.0         | 1450
42        | 100       | 08:00:20    | 31.4          | NULL         | 1460
```

**Phù hợp khi** những kênh được đo cùng nhịp, cùng thiết bị, thường đọc chung và có tập metric ổn định. Một lần lấy dữ liệu cho bảng dashboard có thể đơn giản và ít row hơn.

**Đánh đổi:** nếu từng metric có cadence riêng, nhiều cột sẽ `NULL`; thêm metric mới thường cần migration; phải giải thích `NULL` nghĩa là không đo, chưa gửi hay cảm biến lỗi. Một hàng có thể bị update nhiều lần khi các kênh đến lệch pha.

### 6.2. Narrow/long row: một metric cho một hàng

```text
sensor_reading
tenant_id | device_id | metric_code | observed_at | metric_value
----------+-----------+-------------+-------------+-------------
42        | 100       | temp_c      | 08:00:10    | 31.2
42        | 100       | humidity    | 08:00:10    | 60.0
42        | 100       | rpm         | 08:00:20    | 1460
```

**Phù hợp khi** thiết bị có tập metric khác nhau, cadence không đồng đều, thường truy vấn một metric theo thời gian, và muốn mở rộng loại metric mà không đổi nhiều cột.

**Đánh đổi:** số hàng và kích thước index tăng; đọc nhiều metric cùng một thời điểm có thể cần pivot/join/aggregation; metric dạng số, trạng thái và histogram không thể ép vào cùng một `NUMERIC` mà không mất semantics. Có thể cần nhiều bảng theo **kiểu dữ liệu hoặc loại metric**.

### 6.3. JSON/document event: một gói nhiều trường

```json
{
  "source_message_id": "gw-42-100-000018",
  "device_code": "D-100",
  "observed_at": "2027-01-15T08:00:10Z",
  "measurements": {
    "temp_c": 31.2,
    "humidity_pct": 60.0,
    "rpm": 1450
  }
}
```

**Phù hợp khi** cần giữ nguyên payload nguồn, schema không ổn định và nhiều chỉ số cùng thuộc một gói giao tiếp. Có thể dùng làm **raw ingestion/staging**, sau đó chuyển sang hàng metric chuẩn để truy vấn và kiểm thử.

**Đánh đổi:** JSON hợp lệ không có nghĩa mỗi metric hợp lệ về loại/đơn vị/miền; khó FK từng metric, khác biệt giữa JSON `null` và thiếu khóa; truy vấn giá trị lồng nhau cần expression/GIN index hoặc ETL. Không tự coi document chứa mảng dữ liệu là schema thời gian chuẩn mà không quy định grain từng phần tử.

### Ma trận chọn nhanh

| Yêu cầu chính | Wide | Narrow | Document/raw |
|---|---|---|---|
| Xem đồng thời 5 metric cố định cùng timestamp | Thuận lợi | Cần pivot hoặc tổng hợp | Đọc payload thuận lợi nếu gói đồng bộ |
| Mỗi thiết bị có tập metric biến động | Nhiều cột sparse | Thuận lợi | Linh hoạt |
| Truy vấn lịch sử một metric theo thiết bị | Được nếu có index thời gian | Rất tự nhiên với khóa device–metric–time | Cần path/index/trích dữ liệu |
| FK/chính sách đơn vị theo metric | Cột có kiểu/ràng buộc riêng | Bảng định nghĩa metric + FK | Validator/pipeline rõ ràng |
| Lưu payload nguyên vẹn để đối soát | Không đủ một mình | Không đủ một mình | Rất phù hợp |
| Tính toán counter, rollup phức tạp | Có thể làm | Dễ chuẩn hóa theo metric type | Thường cần giải nén/parse |

**Lựa chọn thường thực dụng:** raw document ngắn hạn để audit, narrow canonical observations cho phân tích lịch sử, latest-state và rollup để phục vụ đọc nhanh. Không bắt buộc dùng cả bốn lớp nếu hệ thống nhỏ; luôn bắt đầu từ workload và chi phí vận hành.

## 7. Ví dụ PostgreSQL 16: lược đồ raw metric có ràng buộc

Ví dụ sau theo giả định **một mẫu hợp lệ trên mỗi** (`tenant_id`, `device_id`, `metric_code`, `observed_at`). Hệ thống có thể nhập nhiệt độ âm; một số metric loại counter phải xác thực thêm tại pipeline. Mọi mốc thời gian trong partition dùng UTC rõ ràng.

```sql
CREATE TABLE device (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT GENERATED ALWAYS AS IDENTITY,
    device_code VARCHAR(80) NOT NULL,
    device_name TEXT NOT NULL,
    CONSTRAINT pk_device PRIMARY KEY (tenant_id, device_id),
    CONSTRAINT uq_device_code UNIQUE (tenant_id, device_code),
    CONSTRAINT ck_device_code_nonblank
        CHECK (char_length(btrim(device_code)) > 0)
);

CREATE TABLE metric_definition (
    tenant_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    metric_name TEXT NOT NULL,
    measure_kind VARCHAR(12) NOT NULL,
    canonical_unit VARCHAR(30) NOT NULL,
    expected_period_seconds INTEGER,
    CONSTRAINT pk_metric_definition
        PRIMARY KEY (tenant_id, metric_code),
    CONSTRAINT ck_metric_kind
        CHECK (measure_kind IN ('GAUGE', 'COUNTER', 'DELTA')),
    CONSTRAINT ck_metric_period
        CHECK (expected_period_seconds IS NULL
               OR expected_period_seconds > 0)
);

CREATE TABLE sensor_reading (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    metric_value NUMERIC(20, 6) NOT NULL,
    quality_code VARCHAR(12) NOT NULL DEFAULT 'GOOD',
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    source_system VARCHAR(40) NOT NULL,
    source_message_id VARCHAR(120) NOT NULL,

    CONSTRAINT pk_sensor_reading
        PRIMARY KEY (tenant_id, device_id, metric_code, observed_at),
    CONSTRAINT fk_reading_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT fk_reading_metric
        FOREIGN KEY (tenant_id, metric_code)
        REFERENCES metric_definition (tenant_id, metric_code),
    CONSTRAINT ck_reading_quality
        CHECK (quality_code IN ('GOOD', 'SUSPECT', 'INVALID')),
    -- Miền kỹ thuật minh họa, không phải giới hạn vật lý của mọi metric.
    -- Chặn cả NaN / Infinity trong PostgreSQL qua giới hạn hữu hạn.
    CONSTRAINT ck_reading_finite_bounded
        CHECK (metric_value BETWEEN -1000000000 AND 1000000000)
) PARTITION BY RANGE (observed_at);

CREATE TABLE sensor_reading_2027_01
    PARTITION OF sensor_reading
    FOR VALUES FROM ('2027-01-01 00:00:00+00')
               TO ('2027-02-01 00:00:00+00');

CREATE TABLE sensor_reading_2027_02
    PARTITION OF sensor_reading
    FOR VALUES FROM ('2027-02-01 00:00:00+00')
               TO ('2027-03-01 00:00:00+00');
```

**Giải thích DDL:**

1. `PRIMARY KEY(tenant_id, device_id, metric_code, observed_at)` bảo vệ grain **theo giả định một điểm tại một thời điểm**. Vì PostgreSQL 16 dùng partition theo `observed_at`, khóa duy nhất trên bảng phân vùng phải chứa khóa phân vùng; schema trên đáp ứng quy tắc đó.
2. PK có B-tree trên các cột được liệt kê. Với `tenant_id`, `device_id` và `metric_code` bằng nhau, PostgreSQL có thể scan index **ngược chiều** theo `observed_at` để tìm điểm mới nhất. **Không tạo ngay index DESC trùng toàn bộ tiền tố PK** nếu chưa đo workload.
3. FK tới `device` và `metric_definition` bảo vệ mã thiết bị/metric thuộc tenant đúng. Nhưng FK **không xác nhận** metric gauge/counter được xử lý đúng, đơn vị đã đổi chính xác hoặc thời điểm nguồn đáng tin.
4. `metric_value NUMERIC(20,6)` phù hợp ví dụ số có độ chính xác thập phân cố định, **không phù hợp mọi cảm biến tốc độ cao**. Nếu cần hiệu năng đặc biệt, có thể dùng `DOUBLE PRECISION` nhưng phải kiểm soát NaN/Infinity, sai số và cách tổng hợp. Với counter rất lớn cần kiểu/giới hạn khác.
5. `quality_code` phải được cân nhắc khi tính tổng hợp. Mặc định `GOOD` chỉ thuận tiện cho nguồn đã được xác thực, không nên tự áp GOOD cho mọi payload chưa qua validation.
6. `source_message_id` dùng cho provenance, **không được khai báo UNIQUE** ở đây vì một gói có thể chứa nhiều metric. Nếu cần dedup theo message, thiết kế ledger giao nhận riêng với namespace nguồn.
7. Không có `DEFAULT PARTITION` trong ví dụ. Phép đo ngoài tháng đã tạo sẽ bị từ chối; cần job tạo partition trước và xử lý late arrivals.

### Vì sao không đặt ràng buộc nhiệt độ chung trên mọi hàng?

Giới hạn `temperature_c BETWEEN -50 AND 150` có thể hợp với một cảm biến nhưng vô nghĩa cho metric `rpm` hoặc `energy_total_wh`. Có thể đưa giới hạn vào `metric_definition` và validate qua ingestion/trigger có khóa phù hợp, hoặc tách bảng theo loại metric để dùng `CHECK` riêng. **CHECK một hàng không tự tham chiếu sang bảng định nghĩa metric** để kiểm tra miền nghiệp vụ một cách an toàn.

## 8. Nạp dữ liệu mẫu, chuẩn hóa đơn vị và idempotency

Trên schema thử sạch:

```sql
INSERT INTO device (tenant_id, device_code, device_name)
VALUES (42, 'D-100', 'Cảm biến lò số 1')
RETURNING tenant_id, device_id;

INSERT INTO metric_definition (
    tenant_id, metric_code, metric_name, measure_kind,
    canonical_unit, expected_period_seconds
)
VALUES
    (42, 'temperature_c', 'Nhiệt độ', 'GAUGE', 'degC', 10),
    (42, 'humidity_pct', 'Độ ẩm', 'GAUGE', 'percent', 10),
    (42, 'energy_total_wh', 'Điện năng tích lũy', 'COUNTER', 'Wh', 60);
```

Giả sử ID trả về của thiết bị là `device_id = 1`. Các lệnh bên dưới chỉ chạy sau khi xác minh đúng ID đó:

```sql
INSERT INTO sensor_reading (
    tenant_id, device_id, metric_code, observed_at,
    metric_value, quality_code, source_system, source_message_id
)
VALUES
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:10+00', 31.20, 'GOOD', 'GATEWAY-A', 'msg-1001'),
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:20+00', 31.40, 'GOOD', 'GATEWAY-A', 'msg-1002'),
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:30+00', 85.10, 'GOOD', 'GATEWAY-A', 'msg-1003'),
    (42, 1, 'temperature_c',
     '2027-01-15 08:00:40+00', 31.30, 'GOOD', 'GATEWAY-A', 'msg-1004'),
    (42, 1, 'energy_total_wh',
     '2027-01-15 08:00:10+00', 15000, 'GOOD', 'GATEWAY-A', 'msg-1001'),
    (42, 1, 'energy_total_wh',
     '2027-01-15 08:01:10+00', 15025, 'GOOD', 'GATEWAY-A', 'msg-1005');
```

Hai hàng cùng `source_message_id = 'msg-1001'` hợp lệ vì một gói gửi cả nhiệt độ và công tơ. Giá trị 85,10 °C tồn tại rất ngắn nhưng phải được **giữ trong `MAX`**, không được xóa chỉ vì dashboard vẽ mượt.

### Retry và bản ghi xung đột

Nếu cùng mẫu được gửi lại:

```sql
-- Một retry giữ nguyên grain sẽ va PK và được bỏ qua.
-- Chỉ dùng nếu ingestion đã kiểm tra payload giống hệt hàng hiện có.
INSERT INTO sensor_reading (
    tenant_id, device_id, metric_code, observed_at,
    metric_value, source_system, source_message_id
)
VALUES (
    42, 1, 'temperature_c',
    '2027-01-15 08:00:10+00', 31.20, 'GATEWAY-A', 'msg-1001'
)
ON CONFLICT (tenant_id, device_id, metric_code, observed_at)
DO NOTHING;
```

**Điều kiện quan trọng:** `ON CONFLICT DO NOTHING` cũng bỏ qua trường hợp **cùng khóa mẫu nhưng giá trị bị đổi** từ 31,20 thành 37,20. Không tự coi xung đột là retry hợp lệ. Pipeline phải so dữ liệu với hàng tồn tại, kiểm tra nguồn/revision, rồi phân loại **identical retry**, **correction** hoặc **duplicate bất thường**. Với sửa timestamp hoặc nhiều mẫu cùng thời điểm, cần thiết kế grain/ID nguồn khác trước khi dùng câu lệnh này.

### Bảng ledger cho message

Một phương án cho đường ingestion nhiều metric trong một gói:

```sql
CREATE TABLE ingestion_message_ledger (
    tenant_id BIGINT NOT NULL,
    source_system VARCHAR(40) NOT NULL,
    source_message_id VARCHAR(120) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_ingestion_message_ledger
        PRIMARY KEY (tenant_id, source_system, source_message_id)
);
```

Ledger phải được ghi **cùng transaction** với toàn bộ các mẫu từ một message, hoặc theo một state machine rõ ràng nếu ingestion phân tán. Khi retry, nếu đã có ID đó thì so hash/nội dung và quyết định trả ACK hay chuyển lỗi; **hash bằng nhau không thay thế các biện pháp bảo vệ chống va chạm/nguồn không tin cậy khi yêu cầu kiểm toán cao**. Ledger còn có chi phí lưu trữ và retention riêng; xóa ledger quá sớm có thể làm một message cũ được nạp lại sau khi raw đã purge.

## 9. Truy vấn A: giá trị mới nhất với kiểm tra độ mới

Truy vấn “nhiệt độ hiện tại” thực chất là **giá trị mới nhất đã ghi**, không phải bằng chứng nhiệt độ thật **ngay thời điểm đọc**. Cần trả cả timestamp và trạng thái chất lượng.

```sql
SELECT
    device_id,
    metric_code,
    observed_at,
    metric_value,
    quality_code,
    received_at
FROM sensor_reading
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND observed_at <= '2027-01-15 08:01:00+00'::timestamptz
ORDER BY observed_at DESC
LIMIT 1;
```

Với dữ liệu mẫu, trả 31,30 °C tại 08:00:40 (sau điểm 85,10). Điều kiện thời gian upper bound nhằm tránh lấy dữ liệu **sau thời điểm truy vấn giả định**, đặc biệt khi phân tích lịch sử; một UI thời gian thực nên dùng mốc server hiện tại đã được chuẩn hóa.

**Kiểm tra stale:** nếu mốc yêu cầu là 08:01:00 và chính sách metric quy định mẫu mới nhất không được quá 15 giây, giá trị từ 08:00:40 phải được đánh dấu **STALE**. Không tự hiển thị là “nhiệt độ hiện tại 31,30 °C” mà bỏ timestamp.

Ví dụ tính thời gian trễ đối với một mốc truy vấn:

```sql
WITH latest AS (
    SELECT observed_at, metric_value, quality_code
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'temperature_c'
      AND observed_at <= '2027-01-15 08:01:00+00'::timestamptz
    ORDER BY observed_at DESC
    LIMIT 1
)
SELECT
    observed_at,
    metric_value,
    EXTRACT(EPOCH FROM (
        '2027-01-15 08:01:00+00'::timestamptz - observed_at
    )) AS age_seconds,
    CASE
        WHEN quality_code <> 'GOOD' THEN 'NOT_TRUSTED'
        WHEN observed_at <
             '2027-01-15 08:01:00+00'::timestamptz - INTERVAL '15 seconds'
             THEN 'STALE'
        ELSE 'FRESH'
    END AS freshness_state
FROM latest;
```

Nếu không có hàng, kết quả rỗng: đây là trạng thái **NO_DATA**, không phải 0 °C. Nếu cần phân biệt **offline**, **không có metric** và **chưa nhận mẫu**, phải kết hợp trạng thái kết nối hoặc catalog khả năng đo của thiết bị.

## 10. Dashboard nhiều thiết bị: bảng latest-state riêng

Nếu dashboard liên tục lấy điểm mới nhất của hàng chục nghìn cặp device–metric, việc quét/sắp nhiều partition raw mỗi vài giây có thể đắt. Một **bảng trạng thái mới nhất** có thể là read model phù hợp:

```sql
CREATE TABLE device_metric_latest (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    metric_value NUMERIC(20,6) NOT NULL,
    quality_code VARCHAR(12) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT pk_device_metric_latest
        PRIMARY KEY (tenant_id, device_id, metric_code),
    CONSTRAINT fk_latest_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT fk_latest_metric
        FOREIGN KEY (tenant_id, metric_code)
        REFERENCES metric_definition (tenant_id, metric_code)
);

-- Sau khi đã chấp nhận một sample của bảng raw:
INSERT INTO device_metric_latest (
    tenant_id, device_id, metric_code, observed_at,
    metric_value, quality_code, received_at
)
VALUES (
    42, 1, 'temperature_c',
    '2027-01-15 08:00:40+00', 31.30, 'GOOD',
    '2027-01-15 08:00:45+00'
)
ON CONFLICT (tenant_id, device_id, metric_code)
DO UPDATE SET
    observed_at = EXCLUDED.observed_at,
    metric_value = EXCLUDED.metric_value,
    quality_code = EXCLUDED.quality_code,
    received_at = EXCLUDED.received_at
WHERE EXCLUDED.observed_at > device_metric_latest.observed_at;
```

**Quy tắc thời gian:** câu `WHERE EXCLUDED.observed_at > ...` ngăn một mẫu **đến muộn nhưng có event time cũ** ghi đè giá trị mới nhất. Nó không tự giải quyết hai mẫu có cùng timestamp nhưng payload khác: trường hợp đó phải được phân loại là correction/revision và xử lý qua giao thức rõ ràng.

Với kiến trúc ghi nhiều nguồn, cập nhật raw và latest nên có **giao dịch nhất quán**, hoặc cơ chế event/outbox và reconciliation để sửa read model nếu pipeline thất bại sau khi raw đã commit. `device_metric_latest` là **dữ liệu dẫn xuất**, không phải nguồn sự thật mới thay thế raw.

Một câu SQL đọc dashboard:

```sql
SELECT
    d.device_code, l.metric_code,
    l.metric_value, l.observed_at, l.quality_code
FROM device_metric_latest AS l
JOIN device AS d
  ON d.tenant_id = l.tenant_id
 AND d.device_id = l.device_id
WHERE l.tenant_id = 42
  AND l.metric_code = 'temperature_c';
```

Nếu workload chọn tất cả thiết bị **theo một metric** thường xuyên, PK có thứ tự tenant–device–metric có thể không tối ưu. Index phụ `(tenant_id, metric_code, device_id)` là ứng viên cần benchmark, không mặc định tạo cho mọi cột.

## 11. Truy vấn B: lịch sử chi tiết và bucket 5 phút

Biểu đồ 24 giờ thường không cần truyền 8.640 điểm mỗi thiết bị nếu pixel hiển thị chỉ có vài trăm cột. Nhưng phải chọn **phép tổng hợp** phù hợp:

```sql
-- Các phép đo thực của một device/metric trong một khoảng.
SELECT observed_at, metric_value, quality_code
FROM sensor_reading
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
ORDER BY observed_at;
```

Trong PostgreSQL 16, `date_bin` hỗ trợ chia thời gian thành bucket có bước cố định (không phải tháng):

```sql
WITH bucketed AS (
    SELECT
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            '2000-01-01 00:00:00+00'::timestamptz
        ) AS bucket_start,
        metric_value
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'temperature_c'
      AND quality_code = 'GOOD'
      AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
      AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
)
SELECT
    bucket_start,
    COUNT(*) AS sample_count,
    AVG(metric_value) AS sample_mean_c,
    MIN(metric_value) AS min_c,
    MAX(metric_value) AS max_c
FROM bucketed
GROUP BY bucket_start
ORDER BY bucket_start;
```

**Giải thích phép đo:** `AVG` ở đây là **trung bình số mẫu** trong bucket. Nó phù hợp nếu mỗi mẫu được coi có trọng số bằng nhau. Với dữ liệu lấy mẫu không đều (ví dụ 10 mẫu trong 1 phút rồi mất tín hiệu 4 phút), nó **không tự đại diện** nhiệt độ trung bình theo thời gian.

`MIN`/`MAX` giữ lại đỉnh như 85,10 °C trong mẫu, ngay cả khi giá trị trung bình bucket nhìn rất bình thường. Nếu dashboard chỉ hiển thị `AVG`, phải có đường phát hiện vượt ngưỡng độc lập hoặc hiển thị dải `MIN/MAX`.

### Những bucket không có mẫu vẫn phải được thể hiện

`GROUP BY` không tạo hàng cho bucket hoàn toàn trống. Đối với biểu đồ, một khoảng không có dữ liệu nên hiển thị **missing/gap**, không tự vẽ về 0 °C:

```sql
WITH bins AS (
    SELECT generate_series(
        '2027-01-15 08:00:00+00'::timestamptz,
        '2027-01-15 08:55:00+00'::timestamptz,
        INTERVAL '5 minutes'
    ) AS bucket_start
),
aggregated AS (
    SELECT
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            '2000-01-01 00:00:00+00'::timestamptz
        ) AS bucket_start,
        COUNT(*) AS n,
        AVG(metric_value) AS avg_c,
        MAX(metric_value) AS max_c
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'temperature_c'
      AND quality_code = 'GOOD'
      AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
      AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
    GROUP BY 1
)
SELECT
    b.bucket_start,
    COALESCE(a.n, 0) AS sample_count,
    a.avg_c,
    a.max_c
FROM bins AS b
LEFT JOIN aggregated AS a USING (bucket_start)
ORDER BY b.bucket_start;
```

`sample_count = 0` và `avg_c IS NULL` biểu thị bucket **không có mẫu tốt**, không phải nhiệt độ bằng 0. Nếu muốn nội suy hoặc giữ giá trị gần nhất (*last observation carried forward*), phải có **chính sách riêng về độ trễ tối đa**, cách đánh dấu số nội suy và điều kiện không vượt qua đoạn mất kết nối.

## 12. Trung bình theo mẫu khác trung bình theo thời gian

Giả sử một thiết bị ghi:

| Thời điểm | Nhiệt độ |
|---|---:|
| 08:00 | 20 °C |
| 08:01 | 20 °C |
| 08:02 | 20 °C |
| 08:59 | 80 °C |

**Trung bình theo mẫu** là:

\[
\frac{20+20+20+80}{4}=35\,^\circ\mathrm C
\]

Nếu giả định số đo có hiệu lực cho đến khi có số đo mới (*step/hold interpolation*), một trung bình theo thời gian trên 08:00–09:00 có thể khác xa 35 °C vì ba mẫu 20 °C nằm sát nhau, còn khoảng 08:02–08:59 rất dài.

Tuy nhiên, không thể tự kết luận từ bốn mẫu rằng nhiệt độ đã giữ nguyên 20 °C suốt 57 phút. Có thể cảm biến mất tín hiệu và quá trình thực tế thay đổi. Vì vậy mỗi KPI phải có hợp đồng:

- **Sample mean:** mỗi mẫu là một quan sát ngang nhau.
- **Time-weighted mean:** áp một quy tắc diễn giải giữa hai điểm (step-hold, linear interpolation...), giới hạn gap và độ bao phủ (*coverage*).
- **Observed min/max:** cực trị trong những mẫu thực sự có; không khẳng định đã phát hiện mọi cực trị giữa các lần lấy mẫu.
- **Percentile:** định nghĩa percentile theo mẫu hay theo thời lượng, và cách xử lý dữ liệu thiếu/bất thường.

Nếu dùng step-hold, có thể tính:

\[
\overline{T}_{time} =
\frac{\sum_i T_i\Delta t_i}{\sum_i\Delta t_i}
\]

với `Δt` chỉ được tính cho **các khoảng có độ bao phủ được chấp nhận**. Khoảng giữa hai mẫu vượt ngưỡng gap có thể bị bỏ khỏi mẫu số hoặc được báo riêng, không âm thầm giả vờ được đo đầy đủ.

**Không tính trung bình của các trung bình bucket** khi số mẫu mỗi bucket khác nhau. Nếu tổng hợp từ rollup, dùng `SUM(sample_sum)/SUM(sample_count)` cho trung bình theo mẫu. Với trung bình theo thời gian, cần lưu **weighted_sum và covered_duration** theo quy tắc xác định, không thể khôi phục từ sample mean và sample count nếu thông tin khoảng thời gian đã mất.

## 13. Counter tích lũy: đọc chênh lệch, phát hiện reset và gap

Metric `energy_total_wh` trong ví dụ là **công tơ tích lũy**. Nếu giá trị ở 08:00 là 15.000 Wh và 08:01 là 15.025 Wh, lượng tiêu thụ hợp lệ giữa hai mốc là **25 Wh**, không phải 30.025 Wh.

Mô hình truy vấn:

```sql
WITH ordered AS (
    SELECT
        observed_at,
        metric_value AS current_counter,
        LAG(observed_at) OVER (ORDER BY observed_at) AS previous_at,
        LAG(metric_value) OVER (ORDER BY observed_at) AS previous_counter
    FROM sensor_reading
    WHERE tenant_id = 42
      AND device_id = 1
      AND metric_code = 'energy_total_wh'
      AND quality_code = 'GOOD'
      AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
      AND observed_at <  '2027-01-15 09:00:00+00'::timestamptz
)
SELECT
    observed_at,
    previous_at,
    previous_counter,
    current_counter,
    CASE
        WHEN previous_counter IS NULL THEN NULL
        WHEN observed_at - previous_at > INTERVAL '10 minutes' THEN NULL
        WHEN current_counter >= previous_counter
             THEN current_counter - previous_counter
        ELSE NULL
    END AS delta_wh
FROM ordered
ORDER BY observed_at;
```

Giá trị đầu tiên không có mẫu trước trong dải lọc nên có `delta_wh = NULL`. Nếu cần tính tiêu thụ **đúng tại ranh giới đầu giờ**, phải tra **mẫu hợp lệ ngay trước đầu giờ** làm baseline, không chỉ lọc các mẫu bên trong giờ rồi lấy `LAG`. Nếu không có mẫu baseline đủ mới, kết quả phải đánh dấu thiếu độ bao phủ.

Nếu counter giảm từ 15.025 xuống 2:

- Có thể đã **reset** do reboot.
- Có thể **rollover** vì hết dải số của thiết bị.
- Có thể thiết bị bị thay hoặc đồng hồ gửi dữ liệu lỗi/out-of-order.

Không dùng `GREATEST(current - previous, 0)` rồi coi phần âm là “không tiêu thụ”, vì nó có thể che reset hoặc lượng tiêu thụ thật trong đoạn đó. Cần định nghĩa chính sách counter reset, giới hạn tối đa, chu kỳ thiết bị và trạng thái chất lượng; một số hệ có thể suy delta sau reset nếu biết **chính xác** ngữ nghĩa bộ đếm, còn hệ khác phải đánh dấu đoạn không xác định.

**Rate** được tính từ `delta / duration` với đơn vị rõ ràng. Ví dụ Wh/s khác W theo định nghĩa vật lý nhưng có thể quy đổi đúng; không lấy `counter_value / observed_at` hoặc `AVG(counter_value)` để biểu diễn công suất.

## 14. Trạng thái và sự kiện vận hành cần mô hình khác gauge

Trạng thái `RUNNING`/`STOPPED` không có ý nghĩa khi tính `AVG(1,2,3)` trừ khi doanh nghiệp chủ đích định nghĩa một mã số tương ứng, và ngay cả khi đó giá trị trung bình mã vẫn không tự là phần trăm uptime.

Hai lựa chọn:

1. **State events:** một hàng mỗi lần chuyển trạng thái, có `effective_at`, state mới, lý do và ID sự kiện; để tính thời lượng cần ghép thời điểm chuyển tiếp và giới hạn khoảng báo cáo.
2. **State samples:** chuỗi mẫu trạng thái tại nhịp cố định; uptime ratio theo số mẫu chỉ là xấp xỉ khi mất mẫu hoặc nhịp thay đổi.

Ví dụ DDL event-oriented:

```sql
CREATE TABLE device_state_event (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    source_event_id VARCHAR(120) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    state_code VARCHAR(20) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT pk_state_event
        PRIMARY KEY (tenant_id, device_id, source_event_id),
    CONSTRAINT fk_state_event_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT ck_device_state
        CHECK (state_code IN ('RUNNING', 'STOPPED', 'OFFLINE'))
);
```

`source_event_id` là khóa của sự kiện chuyển trạng thái; nếu hệ nguồn không cung cấp ID bền vững, phải giải quyết grain trước khi dùng DDL. Một sự kiện có `effective_at` cũ nhưng được nhập muộn có thể thay đổi kết quả tính uptime lịch sử; muốn giữ báo cáo đã chốt phải có version hoặc correction policy.

## 15. Chất lượng dữ liệu: missing, suspect, invalid và ngưỡng cảnh báo

Một phép đo thiếu không đồng nghĩa giá trị 0. Một mẫu vượt ngưỡng không nhất thiết là lỗi, đặc biệt trong giám sát sự cố.

| Tình trạng | Ví dụ | Cách lưu/đọc |
|---|---|---|
| **GOOD** | 32,1 °C đã qua kiểm tra nguồn | Dùng cho biểu đồ/aggregate theo hợp đồng |
| **SUSPECT** | 250 °C vượt miền vật lý dự kiến nhưng chưa có xác nhận | Lưu để điều tra, loại khỏi KPI mặc định hoặc hiện riêng |
| **INVALID** | Payload `"temperature": "unknown"`, lỗi checksum | Quarantine raw payload; không đưa vào bảng numeric như số 0 |
| **MISSING** | Không có mẫu từ 08:01 đến 08:07 | Biểu diễn **bằng sự vắng mặt** hoặc dữ liệu coverage/gap, không tạo hàng 0 °C |
| **LATE** | Đo lúc 08:00, nhận lúc 08:09 | Giữ event time, theo dõi ingestion delay |
| **CORRECTED** | Gửi bản hiệu chỉnh sau calibration | Cần ID/revision và chính sách giữ bản gốc/tái dựng |

Không tự đặt `CHECK(temp_c < 85)` nếu mục tiêu là **phát hiện quá nhiệt**. Constraint như vậy sẽ từ chối chính mẫu 85,10 °C mà hệ thống cần giữ để cảnh báo. **Giới hạn hợp lệ vật lý** khác **ngưỡng cảnh báo vận hành**; hai loại phải được mô hình riêng.

### Phát hiện vượt ngưỡng không được dựa chỉ trên trung bình

```sql
SELECT
    device_id,
    MAX(metric_value) AS max_temp_c,
    COUNT(*) AS high_samples
FROM sensor_reading
WHERE tenant_id = 42
  AND metric_code = 'temperature_c'
  AND quality_code = 'GOOD'
  AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND observed_at <  '2027-01-15 08:10:00+00'::timestamptz
  AND metric_value > 85
GROUP BY device_id;
```

Với dữ liệu mẫu, thiết bị 1 xuất hiện với đỉnh 85,10 °C. Nhưng một **mẫu đơn** vượt ngưỡng khác yêu cầu “nhiệt độ liên tục vượt 85 °C ít nhất 2 phút”: điều kiện liên tục cần độ phủ, thời gian và cách diễn giải giữa mẫu, không thể suy bằng một `MAX` duy nhất.

**Cảnh báo thời gian thực** còn phải xét độ trễ nhận dữ liệu, sự kiện đến muộn, tính lặp khi retry và chính sách thu hồi/cập nhật cảnh báo. Một câu SQL tính max trên raw không tự là hệ thống cảnh báo đáng tin.

## 16. Partition thời gian, B-tree và BRIN: tối ưu theo điều kiện đọc

### 16.1. Partition pruning theo event time

Với bảng `sensor_reading` phân vùng theo `observed_at`, truy vấn có điều kiện:

```sql
WHERE observed_at >= '2027-01-15 00:00:00+00'::timestamptz
  AND observed_at <  '2027-01-16 00:00:00+00'::timestamptz
```

có thể chỉ xét partition tháng 01. Nhưng truy vấn chỉ có `device_id = 1` mà **không có thời gian** có thể phải thăm nhiều partition, dù mỗi partition đều có index. Vì thế bảng `device_metric_latest` là ứng viên tốt cho truy vấn mới nhất lặp liên tục.

### 16.2. Lựa chọn thứ tự B-tree

PK hiện tại có index theo:

```text
(tenant_id, device_id, metric_code, observed_at)
```

Nó phù hợp với “một thiết bị, một metric, một khoảng thời gian” và hỗ trợ quét ngược cho latest trong phạm vi tenant/device/metric. Nhưng mẫu “cùng một metric ở tất cả thiết bị trong 10 phút” có thể cần index khác:

```sql
-- Ứng viên CHỈ TẠO nếu query nhiều thiết bị theo một metric đủ quan trọng.
CREATE INDEX idx_reading_tenant_metric_time_device
    ON sensor_reading (tenant_id, metric_code, observed_at DESC, device_id);
```

Index này còn có thể hỗ trợ điều kiện theo time và lọc trên `metric_code`. Tuy nhiên, thêm một B-tree trên hàng tỷ mẫu là chi phí lớn: mỗi insert phải duy trì thêm index ở partition đích; disk/cache/WAL và thời gian xây index đều tăng. Không tạo nó chỉ vì “có người hỏi nhiệt độ của cả nhà máy” một lần mỗi quý.

### 16.3. BRIN theo thời gian

Nếu raw data phần lớn append theo thứ tự event time, PostgreSQL có thể hưởng lợi từ **BRIN**:

```sql
-- Ứng viên nhỏ gọn cho scan theo khoảng thời gian rộng.
CREATE INDEX idx_reading_observed_brin
    ON sensor_reading USING BRIN (observed_at);
```

BRIN tóm tắt phạm vi trang; phù hợp dữ liệu tương quan với thứ tự vật lý và truy vấn quét khoảng thời gian, thường nhỏ hơn B-tree đầy đủ. Nhưng BRIN **không tự thay B-tree** cho truy vấn latest một thiết bị hoặc `ORDER BY ... LIMIT`; hàng được đọc từ các trang ứng viên vẫn có thể cần recheck.

**Late arrivals** làm thứ tự ghi vật lý không hoàn toàn trùng với `observed_at`, giảm độ chọn lọc BRIN nếu dữ liệu nhiều tháng cũ được nhập xen vào partition. Cần đo tương quan, số trang phải đọc và thực tế truy vấn.

### 16.4. Độ hạt partition

Retention 90 ngày raw có thể gợi ý partition theo ngày hoặc tháng, nhưng quyết định phụ thuộc dung lượng mỗi partition, giờ tạo/xóa, số đối tượng, index, backup và truy vấn. Nếu ghi nhiều triệu mẫu mỗi ngày, partition tháng có thể rất lớn; nếu lượng ghi nhỏ, partition ngày tạo quá nhiều đối tượng. Không có ngưỡng hàng bắt buộc cho mọi DBMS.

Trong PostgreSQL 16, `PRIMARY KEY`/`UNIQUE` trên bảng partitioned phải bao gồm khóa partition theo giới hạn hệ thống. Nếu muốn unique theo `source_message_id` **trên toàn bộ thời gian**, một unique index chỉ trên partition không đủ; cần ledger riêng như mục 8 hoặc cơ chế khác. Không thêm timestamp vào unique message ID chỉ để DDL hợp lệ, vì message trùng được nhận ở thời gian khác có thể lọt.

## 17. Rollup theo 5 phút: cấu trúc phục vụ đọc lịch sử dài

Khi màn hình tháng chỉ cần điểm 5 phút hoặc theo giờ, có thể dùng bảng dẫn xuất:

```sql
CREATE TABLE metric_5m_rollup (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_code VARCHAR(80) NOT NULL,
    bucket_start TIMESTAMPTZ NOT NULL,
    sample_count BIGINT NOT NULL,
    sample_sum NUMERIC(30,6) NOT NULL,
    sample_min NUMERIC(20,6) NOT NULL,
    sample_max NUMERIC(20,6) NOT NULL,
    first_sample_at TIMESTAMPTZ NOT NULL,
    last_sample_at TIMESTAMPTZ NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    rollup_revision BIGINT NOT NULL DEFAULT 1,
    CONSTRAINT pk_metric_5m_rollup
        PRIMARY KEY (tenant_id, device_id, metric_code, bucket_start),
    CONSTRAINT ck_rollup_sample_count CHECK (sample_count > 0),
    CONSTRAINT ck_rollup_min_max CHECK (sample_min <= sample_max),
    CONSTRAINT ck_rollup_sample_order
        CHECK (
            first_sample_at <= last_sample_at
            AND first_sample_at >= bucket_start
            AND last_sample_at < bucket_start + INTERVAL '5 minutes'
        ),
    CONSTRAINT ck_rollup_revision CHECK (rollup_revision > 0)
);
```

Với gauge, `sample_sum`, `sample_count`, `sample_min` và `sample_max` đủ cho **sample mean**, min/max và việc gộp nhiều bucket không chồng nhau. **Không đủ** để khôi phục percentile chính xác, đường đi từng mẫu hoặc time-weighted mean nếu không có thêm thông tin.

### 17.1. Tính lại một bucket từ raw

```sql
-- Ghi lại trạng thái bucket 08:00-08:05 từ raw còn lưu.
INSERT INTO metric_5m_rollup (
    tenant_id, device_id, metric_code, bucket_start,
    sample_count, sample_sum, sample_min, sample_max,
    first_sample_at, last_sample_at
)
SELECT
    tenant_id, device_id, metric_code,
    date_bin(
        INTERVAL '5 minutes',
        observed_at,
        '2000-01-01 00:00:00+00'::timestamptz
    ) AS bucket_start,
    COUNT(*) AS sample_count,
    SUM(metric_value) AS sample_sum,
    MIN(metric_value) AS sample_min,
    MAX(metric_value) AS sample_max,
    MIN(observed_at) AS first_sample_at,
    MAX(observed_at) AS last_sample_at
FROM sensor_reading
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND quality_code = 'GOOD'
  AND observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND observed_at <  '2027-01-15 08:05:00+00'::timestamptz
GROUP BY tenant_id, device_id, metric_code, bucket_start
ON CONFLICT (tenant_id, device_id, metric_code, bucket_start)
DO UPDATE SET
    sample_count = EXCLUDED.sample_count,
    sample_sum = EXCLUDED.sample_sum,
    sample_min = EXCLUDED.sample_min,
    sample_max = EXCLUDED.sample_max,
    first_sample_at = EXCLUDED.first_sample_at,
    last_sample_at = EXCLUDED.last_sample_at,
    rollup_revision = metric_5m_rollup.rollup_revision + 1,
    refreshed_at = clock_timestamp();
```

**Lý do tính lại thay vì cộng dồn vô điều kiện:** nếu một raw sample được gửi lại hoặc bị hiệu chỉnh, chỉ tăng `sample_count += 1` và `sample_sum += value` sẽ đếm trùng hoặc để lại giá trị cũ. Tính lại từ nguồn sự thật cho một bucket có thể **idempotent về nội dung**, miễn raw đã được dedup và tập mẫu đọc nhất quán.

Phép `UPSERT` trên là một ví dụ cơ chế, **chưa có orchestration cho production**. Nếu hai worker đồng thời tính rollup từ hai snapshot dữ liệu khác nhau, bản cập nhật cũ hơn vẫn có thể ghi đè trạng thái mới hơn. Cần khóa/điều phối theo bucket, watermark, batch/version hoặc cách cập nhật bảo đảm tính đơn điệu, rồi đối soát.

### 17.2. Đọc rollup đúng khi gộp một giờ hoặc một ngày

```sql
SELECT
    device_id,
    metric_code,
    SUM(sample_sum) / NULLIF(SUM(sample_count), 0) AS sample_mean,
    MIN(sample_min) AS observed_min,
    MAX(sample_max) AS observed_max,
    SUM(sample_count) AS total_samples
FROM metric_5m_rollup
WHERE tenant_id = 42
  AND device_id = 1
  AND metric_code = 'temperature_c'
  AND bucket_start >= '2027-01-15 08:00:00+00'::timestamptz
  AND bucket_start <  '2027-01-15 09:00:00+00'::timestamptz
GROUP BY device_id, metric_code;
```

Không dùng `AVG(sample_sum / sample_count)` nếu các bucket có số mẫu khác nhau. Cũng không dùng rollup nhiệt độ này cho `energy_total_wh` rồi tính điện năng bằng `SUM(sample_sum)`: counter phải có phép tính delta, reset và gap riêng **trước khi tổng hợp**.

**Bucket rỗng** không có hàng trong bảng rollup này vì `sample_count > 0`. Với biểu đồ, dùng lịch bucket/generate_series để thể hiện khoảng thiếu thay vì lấp bằng 0.

## 18. Khi dữ liệu đến muộn: cửa sổ đóng và watermark

Giả sử pipeline đã tạo rollup 08:00–08:05 lúc 08:06. Đến 08:08, gateway mới gửi mẫu đo lúc 08:03. Dòng raw thuộc bucket **08:00**, không phải 08:05–08:10. Nếu rollup không được tính lại, chart và `MAX` sẽ sai.

Một chính sách có thể gồm:

- **Allowed lateness:** chấp nhận số đo đến trễ tối đa 2 giờ mà vẫn tự động cập nhật raw/rollup.
- **Watermark:** mốc nghiệp vụ mà pipeline tạm coi các khoảng trước đó đã đủ dữ liệu để công bố, có thể dựa trên observed time, độ trễ và trạng thái nguồn.
- **Revision:** bucket được tính lại có phiên bản/`refreshed_at`, downstream có thể cập nhật hoặc giải thích số liệu thay đổi.
- **Very late data:** sự kiện ngoài cửa sổ được chuyển xử lý ngoại lệ, không âm thầm vứt hoặc lén thay số liệu đã chốt.

**Watermark không phải chứng nhận rằng tuyệt đối không còn dữ liệu đến muộn**. Nó là một chính sách về độ hoàn chỉnh và độ trễ chấp nhận. Nếu SLA yêu cầu kết quả bất biến sau khi chốt, dữ liệu đến sau phải thành correction có phiên bản thay vì sửa lặng số đã công bố.

### Idempotency ở cả ba lớp

| Lớp | Bất biến | Cách kiểm chứng |
|---|---|---|
| Message/ingestion | Một message nguồn không được xử lý thành hai bộ mẫu | Ledger theo namespace, đối chiếu payload và transaction |
| Raw reading | Một mẫu theo grain không thành hai hàng | Unique key/PK; xử lý revision khác identical retry |
| Rollup | Một bucket không được cộng cùng raw sample hai lần | Tính lại hoặc cập nhật delta có ledger, test replay và late data |

Nếu dữ liệu đã được purge khỏi raw nhưng một sự kiện rất trễ xuất hiện, **không thể đơn giản tính lại đúng bucket từ raw**. Cần chính sách lưu nguồn/archived data đủ lâu, correction hoặc loại khỏi báo cáo với dấu vết giải thích. Retention là một phần của tính đúng, không chỉ là tối ưu dung lượng.

## 19. Thay đổi thiết bị, vị trí và hiệu chuẩn theo thời gian

Một thiết bị có thể được chuyển từ dây chuyền A sang B ngày 01/07. Nếu muốn báo cáo “nhiệt độ trung bình theo dây chuyền tại thời điểm đo”, không join raw vào `device.current_line` rồi gán mọi mẫu tháng 03 vào B.

Một bảng lịch sử quan hệ có thể dùng:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE device_assignment_period (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    valid_during TSTZRANGE NOT NULL,
    production_line_code VARCHAR(60) NOT NULL,
    CONSTRAINT fk_assignment_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES device (tenant_id, device_id),
    CONSTRAINT ck_assignment_window
        CHECK (
            NOT isempty(valid_during)
            AND NOT lower_inf(valid_during)
        ),
    CONSTRAINT ex_device_one_line_at_time
        EXCLUDE USING GIST (
            tenant_id WITH =,
            device_id WITH =,
            valid_during WITH &&
        )
);
```

Quy tắc ví dụ là một thiết bị thuộc **tối đa một dây chuyền** ở một thời điểm. Nếu nghiệp vụ cho phép nhiều dây chuyền cùng lúc, thiết kế khác và có thể cần bridge theo thời gian. `EXCLUDE` ngăn overlap nhưng không tự ngăn **gap**.

Để tra đúng dây chuyền tại thời điểm đo:

```sql
SELECT
    a.production_line_code,
    r.device_id,
    r.observed_at,
    r.metric_value
FROM sensor_reading AS r
JOIN device_assignment_period AS a
  ON a.tenant_id = r.tenant_id
 AND a.device_id = r.device_id
 AND a.valid_during @> r.observed_at
WHERE r.tenant_id = 42
  AND r.metric_code = 'temperature_c'
  AND r.quality_code = 'GOOD'
  AND r.observed_at >= '2027-01-15 08:00:00+00'::timestamptz
  AND r.observed_at <  '2027-01-15 09:00:00+00'::timestamptz;
```

Nếu có **0 assignment**, inner join sẽ làm mất mẫu; nếu có **2 assignment** vì dữ liệu legacy không sạch, join nhân đôi mẫu. Phải đối soát số mẫu trước và sau join, chặn hoặc báo rõ những mẫu không ánh xạ được.

### Calibration và phép đo đã chuẩn hóa

Nếu hệ thống cập nhật hệ số hiệu chuẩn sau khi dữ liệu được nạp, cần quyết định:

- **As measured/as processed:** giữ giá trị canonical đã công bố lúc nhập, lưu `calibration_version_id`, công thức/nguồn.
- **Restated:** tính lại lịch sử theo bản hiệu chuẩn hồi tố và xuất kết quả có phiên bản, không ghi đè im lặng nếu báo cáo trước phải tái lập.
- **Raw sensor value:** giữ đủ dữ liệu gốc và đơn vị để kiểm chứng phép biến đổi khi có tranh chấp.

Một FK tới `calibration_version_id` chỉ xác nhận version tồn tại, không tự chứng minh version đó có hiệu lực tại `observed_at`. Đây là bài toán temporal mapping tương tự device assignment.

## 20. Retention, downsampling và chi phí lưu trữ

Giả định 20.000 thiết bị, mỗi thiết bị đo **một metric** mỗi 10 giây:

\[
20\,000\times 6\ \mathrm{mẫu/phút}
\times 60\times24
=172\,800\,000\ \mathrm{mẫu/ngày}
\]

Nếu mỗi thiết bị đo ba metric với cùng nhịp, số hàng narrow có thể tăng xấp xỉ ba lần, **nếu** mọi metric đều được gửi đầy đủ. Đây là bài tính dung lượng ở mức số hàng, không phải ước lượng byte chính xác: kích thước index, heap, TOAST, metadata, WAL, replication và nén phụ thuộc DBMS.

Một chính sách retention minh họa:

| Tầng | Độ phân giải | Thời gian giữ | Mục tiêu đọc |
|---|---|---|---|
| Raw chuẩn hóa | Từng mẫu 10 giây | 90 ngày | Điều tra sự cố, phân tích đỉnh/gap và tính lại rollup |
| Rollup 5 phút | Count/sum/min/max | 2 năm | Chart ngày–tháng, theo dõi nhiệt độ lịch sử |
| Rollup ngày | KPI có ngữ nghĩa rõ | 5 năm nếu hợp đồng cho phép | Báo cáo xu hướng nhiều năm |
| Ingestion ledger/payload gốc | Theo quy định nguồn và kiểm toán | Phụ thuộc yêu cầu dedup/đối soát | Truy vết và replay |

**Không có thời hạn mặc định hợp lệ cho mọi hệ thống.** Nếu phải phát hiện đỉnh 2 giây, giữ duy nhất rollup 5 phút có `MAX` chỉ cho biết **có một đỉnh trong bucket**, không tái dựng được chính xác dạng sóng hoặc thời điểm phát sinh nếu không lưu thêm `argmax_at`/raw.

Nếu cần tính percentile p99 trên cả năm, không thể suy chính xác chỉ từ sum/count/min/max; phải lưu raw lâu hơn, cấu trúc histogram/sketch có sai số được kiểm soát, hoặc percentile rollup đủ thông tin theo công nghệ phù hợp. Gộp p95 của từng giờ bằng `AVG` là sai về mặt thống kê.

### Retention là thao tác nghiệp vụ

Trong PostgreSQL, có thể dùng `DETACH PARTITION`/`DROP` sau khi đã archive, kiểm tra phụ thuộc và phê duyệt. Nhưng thao tác tách/xóa partition có thể ảnh hưởng FK, CDC, báo cáo cũ và khả năng replay. Không gọi việc xóa raw là “an toàn” khi rollup vẫn còn thiếu late data hoặc chưa qua đối soát.

Nếu rollup được làm lại từ raw, phải tính **ngày cuối cùng được phép sửa** theo cả retention và allowed lateness; đừng purge raw ngay sau khi rollup tạm có dữ liệu.

## 21. Đo hiệu năng theo đường đọc thay vì theo số index

Trước khi chọn cấu trúc chính thức, thử nhiều kịch bản:

```sql
-- A: latest một device/metric.
EXPLAIN (ANALYZE, BUFFERS)
SELECT observed_at, metric_value
FROM sensor_reading
WHERE tenant_id = 42 AND device_id = 1
  AND metric_code = 'temperature_c'
ORDER BY observed_at DESC
LIMIT 1;

-- B: lịch sử trong khoảng thời gian.
EXPLAIN (ANALYZE, BUFFERS)
SELECT observed_at, metric_value
FROM sensor_reading
WHERE tenant_id = 42 AND device_id = 1
  AND metric_code = 'temperature_c'
  AND observed_at >= '2027-01-15 00:00:00+00'::timestamptz
  AND observed_at <  '2027-01-16 00:00:00+00'::timestamptz
ORDER BY observed_at;

-- C: xem các partition đang tồn tại.
SELECT
    relid::regclass AS relation_name,
    parentrelid::regclass AS parent_name,
    isleaf,
    level
FROM pg_partition_tree('public.sensor_reading'::regclass)
ORDER BY level, relid;
```

`EXPLAIN (ANALYZE, BUFFERS)` thực thi câu SELECT, có thể tiêu thụ nhiều tài nguyên trên bảng lớn; hãy đo trong môi trường/khung giờ kiểm soát. Quan sát:

- **Partition pruning:** query ngày 15/01 có thực sự tránh partition tháng khác không?
- **Index scan so với seq scan:** điều kiện lọc device/metric/time có chọn được đường truy cập rẻ hơn không?
- **Số hàng ước lượng/thực tế**, số trang `shared hit/read` và thời gian p95/p99 khi nhiều thiết bị đọc đồng thời.
- **Fanout do join metadata:** số mẫu có bị nhân hoặc mất khi tra lịch sử dây chuyền?
- **Tốc độ ghi:** samples/s, latency insert, WAL/redo, page/cache pressure, index size, vacuum/compaction và chi phí tạo partition.
- **Rollup freshness:** độ trễ từ event/ingestion đến chart, số bucket bị reprocess và các lỗi chưa đối soát.

Một query chạy nhanh với hai partition rỗng không chứng minh hệ thống vẫn đáp ứng khi mỗi partition có hàng tỷ mẫu. Dữ liệu kiểm thử phải có phân bố tenant/thiết bị nóng, late arrivals, missing gaps, reset counter và nhiều loại metric.

## 22. So sánh PostgreSQL, TSDB, document, graph và kho phân tích

| Cách lưu | Điểm mạnh | Cần kiểm chứng |
|---|---|---|
| **PostgreSQL quan hệ + partition** | FK/constraint rõ, SQL đa dạng, raw/rollup do ứng dụng kiểm soát | Partition/index/retention và chi phí ghi lớn; không tự có mọi tính năng time-series chuyên dụng |
| **Time-series database hoặc extension** | Có thể hỗ trợ chunk, nén, retention, continuous aggregate/downsampling và time-series functions | Chính sách license/extension, late data, index, uniqueness và thời điểm làm mới theo đúng phiên bản |
| **Document/event store** | Lưu payload linh hoạt, thuận lợi audit message nguồn | Trích mẫu, idempotency từng phần tử, index thời gian/metric và validation |
| **Columnar warehouse** | Quét lịch sử lớn, nhóm nhiều thiết bị, lưu nén theo cột | Độ trễ ingest, chi phí refresh, ràng buộc PK/FK có thể không được enforce |
| **Graph** | Duyệt mối liên hệ thiết bị–dây chuyền–phụ tùng–sự cố | Không tự thay thế phép lưu/rollup của hàng tỷ mẫu; traversal theo metadata cần thời gian hiệu lực |

Một TSDB có hàm `time_bucket`, nén và continuous aggregate có thể thuận tiện hơn PostgreSQL core khi tải cực lớn. **Không giả định những hàm đó có sẵn trong PostgreSQL 16 thuần**: ví dụ bài dùng `date_bin` là chức năng của PostgreSQL 16, còn hệ extension/sản phẩm khác có API, giới hạn và cách refresh riêng.

Nếu nhu cầu chủ yếu là **truy vấn trạng thái mới nhất**, một read model latest-state có thể giảm độ trễ hơn việc chuyển toàn bộ hệ thống sang một DBMS khác. Nếu nhu cầu là **quét tỷ mẫu trong nhiều năm**, kiến trúc lưu trữ phân tích/columnar có thể hợp lý hơn chỉ thêm B-tree. Quyết định dựa trên workload và mục tiêu nhất quán, không dựa vào tên gọi công nghệ.

## 23. Các sai lầm thường gặp

| Nhận định sai | Vì sao sai | Hướng xử lý |
|---|---|---|
| “Chuỗi thời gian chỉ cần timestamp và value.” | Thiếu tenant, device, metric, đơn vị, quality, nguồn và grain | Định nghĩa hợp đồng đo, khóa và provenance |
| “Lần nhận cuối là giá trị mới nhất.” | Mẫu đến muộn có received_at mới nhưng observed_at cũ | Phân biệt latest by event time và latest ingested |
| “Một timestamp luôn là một sample duy nhất.” | Nguồn có nhiều channel/sequence tại cùng giây | Thiết kế sample ID/độ phân giải đúng |
| “Mẫu thiếu có giá trị 0.” | Số 0 là phép đo có nghĩa, không phải missing | Giữ `NULL`/gap, hiển thị coverage |
| “Lấy `AVG` 5 phút là nhiệt độ trung bình theo thời gian.” | Sampling không đều, gap làm sai trọng số | Định nghĩa sample mean hoặc time-weighted mean |
| “Chỉ lưu trung bình là đủ để phát hiện quá nhiệt.” | Đỉnh ngắn bị làm mượt | Giữ raw hoặc `MAX` cùng thời điểm/quality |
| “`SUM(counter_value)` là điện năng tiêu thụ.” | Counter là tổng tích lũy | Dùng delta có phát hiện reset/rollover/gap |
| “Mẫu trên 85 °C phải bị `CHECK` từ chối.” | Mất chính bằng chứng quá nhiệt | Tách physical validity khỏi alert threshold |
| “`ON CONFLICT DO NOTHING` luôn là idempotent đúng.” | Che conflict cùng ID nhưng payload khác | So sánh payload, version và xử lý correction |
| “Một B-tree mới giải quyết dashboard 20.000 thiết bị.” | Latest nhiều series có thể phải quét nhiều partition | Đo index và cân nhắc latest-state table |
| “Rollup chỉ cần cộng dồn mỗi khi nhận message.” | Retry/late correction nhân số mẫu | Recompute từ raw hoặc dùng ledger delta |
| “SCD2/thiết bị đổi dây chuyền không ảnh hưởng fact đo.” | Join metadata hiện tại có thể gán sai lịch sử | As-of join, xác minh không gap/overlap |
| “Phân vùng tháng tự xuất hiện khi sang tháng mới.” | Ghi bị từ chối nếu thiếu partition | Tạo trước và giám sát ranh giới |
| “Raw đã xóa vẫn luôn có thể tính lại rollup chính xác.” | Mất dữ liệu gốc, percentile/gap/revision | Retention kết hợp late policy và archive |
| “Một histogram p95 có thể gộp bằng AVG(p95).” | Percentile không có tính cộng như sum | Lưu histogram/sketch hoặc raw theo nhu cầu |

## 24. Bài luyện tập: thiết kế giám sát nhiệt độ và điện năng cho nhà máy

**Bối cảnh:** ba nhà máy, 12.000 thiết bị; một nửa gửi nhiệt độ mỗi 5 giây, phần còn lại mỗi 30 giây. 2.000 thiết bị gửi thêm bộ đếm năng lượng Wh mỗi phút. Gateway có thể offline 30 phút rồi gửi bù; 0,5% mẫu có timestamp tương lai do lỗi đồng hồ; 2% mẫu nhiệt độ thiếu khi mất mạng. Thiết bị có thể được chuyển dây chuyền và được hiệu chuẩn lại mỗi quý.

Yêu cầu đọc:

- **R1:** trạng thái nhiệt độ mới nhất của mọi thiết bị trong một nhà máy, refresh 3 giây, cảnh báo khi dữ liệu quá cũ 30 giây.
- **R2:** chart nhiệt độ thiết bị theo 5 phút trong 30 ngày, phải thấy bucket thiếu và đỉnh quá nhiệt.
- **R3:** tổng điện năng tiêu thụ Wh theo ca 8 giờ, không đếm sai khi counter reset.
- **R4:** nhiệt độ cao nhất theo dây chuyền tại **thời điểm đo**, báo cáo mỗi ngày.
- **R5:** điều tra sự cố với toàn bộ raw mẫu trong 60 ngày.
- **R6:** raw giữ 90 ngày; rollup 5 phút giữ 2 năm; chỉ số tổng hợp tháng giữ 5 năm.

### Nhiệm vụ

1. **Viết grain:** định nghĩa khóa duy nhất của raw nhiệt độ và counter, giải quyết mẫu trùng timestamp và message chứa nhiều metric. Phân biệt event ID với source message ID.
2. **Chọn schema:** so wide row, narrow row và raw JSON; đề xuất một thiết kế chính thức có lược đồ, FK theo tenant, metadata metric, quality flags và unit.
3. **Tối ưu R1:** trình bày truy vấn latest từ raw và thiết kế bảng latest-state; chỉ ra vì sao late arrival không được ghi đè điểm mới hơn.
4. **Tối ưu R2:** tạo bucket 5 phút theo event time, giữ `COUNT`, `SUM`, `MIN`, `MAX`, hiển thị gap và định nghĩa sample mean khác time-weighted mean.
5. **Tối ưu R3:** xây tính `delta_wh` theo counter, lấy baseline trước ranh giới ca, xử lý reset/rollover và đoạn mất mẫu.
6. **Tối ưu R4:** thiết kế lịch sử thiết bị → dây chuyền với khoảng hiệu lực, as-of join và ca kiểm thử chống nhân/mất số đo.
7. **Chất lượng dữ liệu:** xử lý timestamp tương lai, nhiệt độ vượt ngưỡng, JSON null, giá trị thiếu, đơn vị °F/°C và hiệu chuẩn sửa hồi tố.
8. **Late data:** định nghĩa watermark và allowed lateness; lập thuật toán refresh bucket 5 phút có tính idempotent và xác định sau khi khóa sổ.
9. **Retention:** chọn độ hạt partition ngày/tháng, lịch tạo trước, thứ tự archive/rollup/đối soát/drop và phương án replay sau khi raw đã purge.
10. **Benchmark:** mô phỏng dữ liệu lệch giữa các thiết bị, đo p95 của R1/R2/R4, throughput ingest, số partition scan, dung lượng index/WAL và độ trễ rollup.

### Checklist bàn giao

- [ ] Mẫu đọc, khoảng thời gian, độ phân giải, SLA và chính sách độ mới đã được ghi rõ.
- [ ] Grain raw xác định đúng thiết bị, metric, thời điểm và khóa nguồn; retry không tạo mẫu mới.
- [ ] Gauge, counter, delta và state không bị dùng chung phép tổng hợp sai nghĩa.
- [ ] Đơn vị, khoảng hợp lệ, quality, event time, received time và timezone đã được chuẩn hóa.
- [ ] Có đường đọc latest nhanh mà late arrival không ghi đè trạng thái mới hơn.
- [ ] Bucket thiếu, độ bao phủ, min/max và dữ liệu đến muộn được thể hiện minh bạch.
- [ ] Trọng số lấy mẫu, tính delta, reset và nội suy có hợp đồng nghiệp vụ rõ ràng.
- [ ] Device metadata/hiệu chuẩn có phiên bản hiệu lực; báo cáo lịch sử dùng as-of join khi cần.
- [ ] Partition/index/rollup/retention được chọn theo workload và kiểm thử trên dữ liệu đại diện.
- [ ] Các bước nhập lại, replay, correction, watermark, đối soát và rollback đã được thiết kế.

**Mô hình chuỗi thời gian đúng không chỉ giữ từng số đo mà còn giữ được cách diễn giải số đo theo thời điểm và nhu cầu đọc.** Nhiệt độ cần đọc latest, đỉnh và độ phủ; bộ đếm cần delta và xử lý reset; trạng thái cần thời lượng; còn bảng raw, latest và rollup phải có nguồn sự thật, grain và chính sách đồng bộ rõ ràng. Khi những lựa chọn này được kiểm chứng bằng truy vấn thực tế, hệ thống vừa đáp ứng dashboard nhanh vừa không làm sai lịch sử vận hành.
