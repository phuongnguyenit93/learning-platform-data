# Khóa chuỗi, thời điểm và các chiều dùng để xác định một phép đo

Một hệ thống thu thập nhiệt độ có thể nhận các bản tin:

~~~text
08:00  Thiết bị D-101, kênh INDOOR, nhiệt độ 25,2 °C
08:00  Thiết bị D-101, kênh OUTDOOR, nhiệt độ 30,1 °C
08:00  Thiết bị D-102, kênh INDOOR, nhiệt độ 24,8 °C
08:01  Thiết bị D-101, kênh INDOOR, nhiệt độ 25,4 °C
~~~

Nếu dùng **thời điểm** làm khóa duy nhất, ba phép đo lúc 08:00 sẽ va chạm. Nếu chỉ dùng **thiết bị + thời điểm**, hai kênh INDOOR và OUTDOOR của D-101 vẫn va chạm. Nếu chỉ dùng **thiết bị + loại chỉ số + thời điểm**, một cảm biến có hai kênh hoặc hai phương pháp xử lý vẫn chưa được phân biệt.

Vấn đề cốt lõi không phải “thêm cột vào khóa chính cho đủ dài”, mà là định nghĩa **một phép đo đại diện cho điều gì**, **những chiều nào làm nó thành một chuỗi riêng** và **thời gian trong bản tin mang ý nghĩa nào**.

Bài này thuộc chương **Dữ liệu chuỗi thời gian** của module **DATABASE_DATA_MODELING**. Mục tiêu là chuyển yêu cầu thu thập dữ liệu thành mô hình định danh, quan hệ, khóa, ràng buộc và chỉ mục có thể kiểm chứng; đồng thời phân biệt cách biểu diễn chuỗi thời gian trong cơ sở dữ liệu quan hệ, document, graph và hệ thống phân tích.

> **Nguyên tắc:** Khóa chuỗi trả lời **“đây là dòng quan sát nào?”**; timestamp trả lời **“phép đo có hiệu lực/xảy ra khi nào?”**; khóa phép đo trả lời **“đây có phải đúng một quan sát riêng biệt trong dòng đó không?”**. Ba khái niệm liên quan nhưng không đồng nghĩa.

## 1. Phân biệt chuỗi thời gian, phép đo và giá trị

Một **chuỗi thời gian (time series)** là tập các quan sát của **cùng một đại lượng có ngữ nghĩa thống nhất**, theo trục thời gian. Mỗi quan sát thường có:

- **Danh tính chuỗi (series identity):** tổ hợp đối tượng, loại chỉ số, kênh, phương pháp hoặc những chiều phân biệt nguồn đo.
- **Thời điểm hoặc khoảng thời gian của phép đo:** lúc ghi nhận hiện tượng, hoặc khoảng mà giá trị đại diện.
- **Giá trị (value):** số đo, trạng thái, bộ giá trị hoặc sự kiện.
- **Metadata chất lượng và xuất xứ:** đơn vị đo, độ tin cậy, nguồn, phiên bản, thời điểm tiếp nhận, lý do hiệu chỉnh.

Một chuỗi nhiệt độ có thể được hình dung:

~~~text
Series S1001:
  tenant = 1
  device = D-101
  metric = air_temperature
  channel = INDOOR
  method = CALIBRATED
  canonical_unit = degC

Observations:
  2026-10-10T08:00:00+07:00  -> 25.2
  2026-10-10T08:01:00+07:00  -> 25.4
  2026-10-10T08:03:00+07:00  -> 25.5
~~~

Cả ba quan sát thuộc **cùng một series**, nhưng là **ba phép đo khác nhau**. Cùng một thiết bị có thể tạo nhiều series; cùng một thời điểm có thể xuất hiện trong nhiều series; cùng một series cũng có thể nhận bản tin lặp hoặc bản sửa.

### 1.1. Mức hạt (grain) của một hàng

Trước khi tạo bảng, viết một câu đầy đủ, ví dụ:

> “Một hàng MeasurementSample là **giá trị nhiệt độ đã chuẩn hóa của đúng một series tại đúng một instant quan sát**, với tối đa một phiên bản hiện hành cho cặp (series, instant).”

Nếu nghiệp vụ cho phép hai mẫu hợp lệ từ cùng một series tại đúng một instant, câu trên **không còn đúng**. Khi đó cần một định danh ổn định khác, chẳng hạn sample_sequence hoặc source_sample_id.

| Câu định nghĩa một hàng | Khóa tự nhiên có thể có | Có thể trùng timestamp? |
| --- | --- | --- |
| Một điểm đọc hiện hành của series tại một instant | (series_id, observed_at) | Không, theo **quy ước grain** này |
| Một sự kiện cảm biến độc lập | (source_system, source_event_id) | Có |
| Một mẫu thứ k do cảm biến phát tại instant t | (series_id, observed_at, sample_seq) | Có, nếu seq phân biệt hợp lệ |
| Một phép tổng hợp 5 phút của series | (series_id, window_start, window_length, aggregation_method, version) | Có giữa các loại/cửa sổ |
| Một phiên bản sửa của cùng điểm đo | (series_id, observed_at, source_revision) | Có, vì đó là **lịch sử phiên bản** |
| Một trạng thái cuối ngày của thiết bị | (device, metric, local_business_date, timezone_rule) | Không theo định nghĩa snapshot |

**Không nên chọn khóa từ dữ liệu mẫu trước khi xác định grain.** Hai giá trị tình cờ không trùng trong tập thử chưa chứng minh chúng sẽ luôn duy nhất.

### 1.2. Bản ghi quan sát khác bản tin truyền tải

Cảm biến có thể gửi lại cùng một sample ba lần do retry. Kho dữ liệu có thể nhận:

~~~text
message 1 -> sample A
message 2 -> sample A   (retry)
message 3 -> sample A   (retry)
~~~

Đây là **ba lần tiếp nhận**, nhưng chỉ **một quan sát nghiệp vụ** nếu ID và payload xác nhận đó là cùng sample. Ngược lại:

~~~text
message 1 -> sample A at 08:00:00.000
message 2 -> sample B at 08:00:00.000
~~~

có thể thực sự là hai quan sát khác nhau nếu thiết bị hỗ trợ nhiều phép đo tại cùng timestamp và có ID mẫu riêng.

Vì vậy cần phân biệt **message ID**, **source event/sample ID**, **series ID** và **observation key**. Không dùng số thứ tự tự tăng khi ingest làm bằng chứng hai bản tin là hai phép đo mới.

## 2. Thiết kế khóa chuỗi (series key)

Khóa chuỗi có thể là một tổ hợp các chiều định danh:

~~~text
series_business_key =
    (tenant_id, device_id, metric_id, channel_code, method_code)
~~~

Trong ví dụ:

- **tenant_id:** phạm vi tổ chức sở hữu thiết bị; device_id có thể chỉ duy nhất trong tenant.
- **device_id:** thiết bị/điểm đo thực sự.
- **metric_id:** đại lượng có ngữ nghĩa và đơn vị chuẩn, ví dụ air_temperature hoặc cumulative_energy.
- **channel_code:** kênh INDOOR, OUTDOOR, PHASE_A, PHASE_B...
- **method_code:** RAW, CALIBRATED hoặc một phương pháp tính có ngữ nghĩa khác nhau.

Hệ thống có thể tạo **series_id** làm khóa thay thế (*surrogate key*) cho tổ hợp trên. Khóa nghiệp vụ phải có **UNIQUE** để hai luồng ghi không tạo hai series_id cho cùng một tổ hợp. Khóa thay thế làm FK và chỉ mục trên bảng mẫu gọn hơn, nhưng không được thay thế quy tắc duy nhất nghiệp vụ.

### 2.1. Chiều nào phải nằm trong khóa chuỗi?

Chỉ đưa một chiều vào series key khi **thay đổi chiều đó tạo một dòng quan sát khác về mặt ngữ nghĩa**.

| Thuộc tính | Thường là chiều định danh chuỗi? | Lý do/ngoại lệ |
| --- | --- | --- |
| Tenant | Có, nếu định danh khác nhau giữa tổ chức | Tránh nối nhầm dữ liệu xuyên tenant |
| Thiết bị hoặc điểm đo | Có | Phân biệt nguồn quan sát |
| Loại metric | Có | Nhiệt độ khác độ ẩm, công suất khác năng lượng |
| Kênh/pha/trục | Có nếu một thiết bị đo nhiều kênh cùng loại | PHASE_A khác PHASE_B |
| Phương pháp RAW/CALIBRATED | Có **nếu hai kết quả cùng tồn tại như hai series** | Nếu chỉ là cách sửa cùng giá trị, nên dùng revision |
| Đơn vị đo | Tùy định nghĩa metric | Nên chuẩn hóa về đơn vị canonical nếu quy đổi được |
| Vị trí hiện tại | Tùy đối tượng được đo | Thiết bị di chuyển không nhất thiết làm đổi identity |
| Firmware version | Thường không | Thường là metadata theo thời gian, trừ khi thay đổi ngữ nghĩa phép đo |
| Chất lượng OK/SUSPECT | Không | Thuộc từng quan sát, không phải một series mới |
| Timestamps ingest | Không | Cùng phép đo đến muộn không được sinh series mới |
| Giá trị đo | Không | Giá trị thay đổi liên tục; đưa vào key sẽ phá ý nghĩa series |
| Request ID/session ID | Thường không | Nhãn có cardinality cực cao, dễ sinh series vô hạn |

Đây không phải danh sách tuyệt đối. Nếu metric “nhiệt độ không khí tại điểm đo cố định” có **điểm đo** là danh tính chính còn sensor vật lý được thay thế theo đợt bảo trì, khóa series có thể dựa trên **measurement_point_id** thay vì device_id. Ngược lại, khi giám sát hành vi của **thiết bị cụ thể**, device_id mới là chiều định danh quan trọng.

### 2.2. Đơn vị và phiên bản ngữ nghĩa

Nhiệt độ **25 °C** và **77 °F** là cùng đại lượng vật lý nhưng khác cách biểu diễn. Nếu đo theo cùng nguồn và instant, không nên tự tạo hai quan sát độc lập rồi cộng/đếm cả hai chỉ vì đơn vị khác nhau.

Thông thường nên:

1. Xác định **canonical_unit** gắn với metric, chẳng hạn degC.
2. Chuyển đổi tại ingestion/semantic layer, ghi nhận **source_unit** nếu cần truy vết.
3. Bảo đảm chuyển đổi đúng công thức và độ chính xác.
4. Nếu một metric đổi **định nghĩa** (chẳng hạn nhiệt độ tức thời thành trung bình 5 phút), dùng **metric version/method/aggregation khác**, không âm thầm tái sử dụng series như thể các giá trị tương đương.

Với chỉ số tài chính, đơn vị tiền tệ **VND và USD** không tương đương khi chưa quy đổi theo tỷ giá và thời điểm thích hợp; currency có thể là thành phần metric semantic key hoặc dimension phải được dùng khi nhóm dữ liệu.

### 2.3. Có nên thêm mọi nhãn vào series key?

Không. Một nhãn chứa user_id, request_id hoặc trace_id thay đổi theo mỗi thông điệp có thể tạo số series gần bằng số sự kiện. Điều này gây **cardinality explosion**: rất nhiều series có ít điểm đo, tiêu tốn bộ nhớ metadata, index, số file/partition và chi phí truy vấn.

Hãy tách:

- **Series dimensions:** thuộc tính ổn định đủ để phân biệt các dòng đo cần theo dõi.
- **Observation attributes:** chất lượng, source_event_id, độ lệch đồng hồ, nhãn thao tác, payload chi tiết.
- **Contextual/time-varying dimensions:** vị trí thiết bị, nhóm vận hành, firmware theo khoảng hiệu lực.
- **Measure values:** nhiệt độ, lưu lượng, số điện, trạng thái đo.

Nếu một trường chỉ dùng để lọc một số lần kiểm tra nhưng có hàng triệu giá trị khác nhau, không nhất thiết phải biến nó thành tag định danh chuỗi. Có thể giữ ở bản ghi sự kiện hoặc bảng liên hệ riêng.

## 3. Khóa của phép đo: series + thời điểm có đủ không?

Trong một mô hình sampling thông thường:

~~~text
PRIMARY KEY (series_id, observed_at)
~~~

là hợp lý **nếu và chỉ nếu** nghiệp vụ xác nhận:

> Với cùng series, một instant chỉ có tối đa một mẫu được xem là hợp lệ tại trạng thái hiện hành.

Điều này không đồng nghĩa mọi thiết bị chỉ gửi một bản tin tại mỗi giây. Một timestamp có thể có độ chính xác đến microsecond, hoặc nhiều bản tin thuộc **cùng một mẫu** được gửi lại. Cần biết **độ chính xác và cách gán timestamp** của nguồn.

### 3.1. Những trường hợp khóa hai cột thất bại

1. **Đo nhiều lần trong một millisecond:** nguồn chỉ lưu timestamp đến millisecond, khiến các mẫu thật trùng instant sau khi làm tròn.
2. **Lấy mẫu nhiều kênh:** channel_code chưa nằm trong series key nên hai phép đo khác loại bị ép chung.
3. **Hai nguồn đồng thời đo cùng mục tiêu:** source_id hoặc measurement_method có thể làm xuất hiện hai series khác nhau.
4. **Cảm biến gửi bản sửa:** một mẫu có nhiều version; cần bảng lịch sử riêng nếu không muốn ghi đè.
5. **Một phép đo trải dài khoảng thời gian:** khóa thực sự phải bao gồm interval hoặc định nghĩa window.
6. **Cùng timestamp nhưng nhiều event:** một chuỗi sự kiện hoạt động không nhất thiết có tính duy nhất theo thời điểm.

### 3.2. Khi nhiều phép đo cùng instant là hợp lệ

Nếu nguồn cung cấp **sample_seq ổn định** cho từng series/instant, grain có thể là:

~~~text
(series_id, observed_at, sample_seq)
~~~

Nếu nguồn cung cấp **source_sample_id** toàn cục hoặc theo tenant/source, có thể dùng:

~~~text
(source_system, source_sample_id)
~~~

làm khóa nghiệp vụ quan sát, còn (series_id, observed_at) là cặp để lọc/thứ tự.

**Không tự sinh sample_seq dựa trên thứ tự thông điệp đến** nếu muốn nhận diện retry, vì cùng mẫu có thể đến ở vị trí khác trong hàng đợi. Chọn một ID ổn định từ nguồn hoặc quy tắc suy diễn được xác minh.

### 3.3. Dùng surrogate key ở bảng mẫu có giải quyết trùng không?

Một **sample_id BIGINT IDENTITY** chỉ giúp hàng có khóa kỹ thuật riêng. Nó **không ngăn** hai hàng chứa cùng sự kiện nghiệp vụ. Vẫn cần UNIQUE theo grain, hoặc bảng sự kiện có định danh nguồn và cơ chế dedup.

Ví dụ, nếu yêu cầu là một mẫu/series/instant, thêm sample_id nhưng bỏ UNIQUE(series_id, observed_at) là làm yếu bất biến. Nếu yêu cầu cho nhiều mẫu cùng instant, đặt UNIQUE(series_id, observed_at) là **quá chặt**.

## 4. Trục thời gian: một bản ghi có thể có nhiều timestamp

Một phép đo có thể mang các mốc thời gian khác nhau:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **observed_at / event_time** | Instant hiện tượng được quan sát | 08:00 tại cảm biến |
| **device_recorded_at** | Timestamp thô do thiết bị đóng dấu | Có thể lệch do clock drift |
| **received_at / ingested_at** | Lúc hệ thống nhận và chấp nhận bản tin | 08:05 do mạng chậm |
| **processed_at** | Lúc pipeline chuẩn hóa/đánh giá chất lượng | 08:06 |
| **valid_from / valid_to** | Khoảng phiên bản/thuộc tính có hiệu lực | Vị trí thiết bị từ 01/10 đến 20/10 |
| **bucket_start_at / bucket_end_at** | Khoảng đại diện cho phép tổng hợp | Trung bình từ 08:00 đến trước 08:05 |

**Observed_at không nhất thiết bằng received_at.** Dữ liệu có thể đến trễ, bị gửi lặp hoặc được nhập lại. Khi báo cáo “nhiệt độ theo giờ xảy ra”, phải nhóm theo observed_at; khi phân tích “độ trễ pipeline”, phải so received_at và observed_at.

### 4.1. Instant so với thời gian địa phương

Một instant như:

~~~text
2026-10-10T08:00:00+07:00
~~~

chỉ cùng thời điểm với:

~~~text
2026-10-10T01:00:00Z
~~~

Trong PostgreSQL, **TIMESTAMPTZ** biểu diễn một instant có thể so sánh, sắp xếp và tính khoảng cách giữa các múi giờ. Nó **không giữ nguyên nhãn timezone gốc** như “Asia/Ho_Chi_Minh” hoặc offset ban đầu để tái hiện chính xác cách người gửi viết timestamp.

Nếu cần biết timezone nghiệp vụ gốc, lưu riêng **timezone_name** dưới dạng tên vùng IANA, hoặc lấy theo lịch sử vị trí thiết bị. Không gán một giá trị TIMESTAMP WITHOUT TIME ZONE là “UTC” bằng thói quen mà không có quy ước được kiểm soát.

### 4.2. Giờ mùa hè (DST), thời gian không tồn tại và thời gian lặp

Ở một số vùng có chuyển giờ mùa hè, một giờ địa phương có thể **không tồn tại** vào ngày nhảy giờ hoặc **xuất hiện hai lần** vào ngày lùi giờ. Vì thế:

~~~text
device_local_time = 01:30
~~~

**không luôn đủ xác định một instant** nếu thiếu timezone và offset/qui tắc xử lý lúc chuyển giờ.

Với hệ thống theo ngày giờ địa phương, cần xác định vùng timezone và cách xử lý timestamp mơ hồ. Nếu chỉ lưu giờ địa phương không offset, không nên suy ra observed_at chính xác cho mọi tình huống.

Ngày nghiệp vụ cũng có thể dài **23, 24 hoặc 25 giờ** tùy múi giờ và ngày. Nếu nhóm dữ liệu theo ngày địa phương, không mặc định mọi ngày đều có đúng 86.400 giây.

### 4.3. Độ phân giải timestamp không phải tần suất lấy mẫu

Hai khái niệm khác nhau:

- **Timestamp precision/resolution:** nguồn phân biệt mili giây, micro giây hay nano giây.
- **Sampling interval/cadence:** thiết bị dự kiến đo mỗi giây, mỗi phút hay bất thường.

Một cảm biến lấy mẫu 100 lần/giây nhưng chỉ gửi thời gian đến giây sẽ sinh nhiều điểm cùng timestamp nếu không có sample_seq. Một thiết bị đo mỗi phút nhưng dùng timestamp microsecond vẫn có thể gặp **jitter** (08:00:00.032, 08:01:00.041).

PostgreSQL TIMESTAMPTZ thường có độ chính xác đến **micro giây**. Nếu thiết bị thực sự cần phân biệt timestamp nano giây, cần thiết kế bổ sung chẳng hạn **epoch_ns dạng BIGINT**, nguồn/chuỗi và thứ tự mẫu, đồng thời kiểm soát phạm vi giá trị và công cụ đọc/ghi; không âm thầm làm tròn rồi chèn đè dữ liệu khác.

### 4.4. Clock drift và chỉnh đồng hồ

Một cảm biến có thể chạy nhanh/chậm vài giây; khi đồng bộ NTP, timestamp nguồn có thể “nhảy lùi”. Nếu chỉ dựa vào thời gian ghi bởi thiết bị để chống trùng, các mẫu thật có thể đè nhau.

Cần phân biệt:

- **raw_device_time:** timestamp gốc để audit.
- **corrected_observed_at:** instant đã hiệu chỉnh theo chính sách được ghi nhận.
- **clock_quality/offset_estimate:** mức tin cậy của phép hiệu chỉnh.
- **source_sample_id/sequence:** nhận diện mẫu độc lập với đồng hồ.

Nếu sửa observed_at, danh tính khóa theo (series_id, observed_at) cũng thay đổi. Phải có quy trình di trú/phiên bản hóa để tránh làm mất liên kết tới dữ liệu đã công bố.

## 5. Phép đo tại một instant khác phép đo trong một khoảng

Một mẫu nhiệt độ tức thời và **nhiệt độ trung bình 5 phút** không có cùng grain.

### 5.1. Phép đo tức thời

~~~text
(series_id, observed_at) -> temperature_value
~~~

Ví dụ nhiệt độ 25,2 °C tại 08:00:00. Giá trị diễn đạt **tại instant đó** theo định nghĩa cảm biến/thuật toán.

### 5.2. Phép đo theo cửa sổ

~~~text
(series_id, window_start_at, window_end_at, aggregation_method)
    -> aggregate_value
~~~

Ví dụ giá trị **AVG** của nhiệt độ trong cửa sổ:

~~~text
[08:00, 08:05)
~~~

được định nghĩa bằng khoảng **nửa mở [start, end)**: bao gồm mốc bắt đầu, không bao gồm mốc kết thúc. Mẫu đúng 08:05 thuộc cửa sổ sau, không đồng thời thuộc hai cửa sổ liền kề.

Phải xác định:

- Khoảng là 5 phút cố định hay một ngày địa phương?
- Giá trị AVG là **trung bình các mẫu** hay **trung bình trọng số theo thời gian**?
- Xử lý khoảng trống và mẫu kém chất lượng thế nào?
- Phép tổng hợp có dùng dữ liệu đã hiệu chỉnh đến cutoff nào?
- Có cần lưu **sample_count, coverage, calculation_version, watermark** không?

Cùng một series và window_start có thể có cả **MIN, MAX, AVG** và những độ dài cửa sổ khác nhau. Vì vậy **(series_id, window_start)** không luôn là khóa đủ cho bảng aggregate.

### 5.3. Không được đánh đồng timestamp cửa sổ với thời điểm quan sát

Một hệ thống có thể gắn nhãn dữ liệu aggregate bằng **window_end_at** thay vì **window_start_at**. Cả hai cách đều có thể dùng nếu thống nhất, nhưng phải lưu mô tả rõ.

Nếu một bản tin:

~~~json
{"timestamp":"2026-10-10T08:05:00+07:00","value":25.3}
~~~

là **AVG của [08:00,08:05)**, không thể tự hiểu đó là nhiệt độ tức thời tại 08:05. Thiếu loại phép đo và độ dài cửa sổ sẽ dẫn đến JOIN/so sánh sai.

## 6. Đại lượng đo quyết định phép tính

Cùng một timestamp và series key vẫn chưa đủ để biết **SUM, AVG, MAX hay hiệu số** có ý nghĩa hay không.

| Loại metric | Ví dụ | Ý nghĩa của value | Phép tính thường cần |
| --- | --- | --- | --- |
| **Gauge** | Nhiệt độ, mực nước, số kết nối hiện tại | Trạng thái ở instant | LAST, MIN, MAX, AVG theo định nghĩa |
| **Cumulative counter** | Tổng kWh đồng hồ, tổng byte mạng | Tổng tích lũy đến thời điểm | DELTA giữa mẫu, RATE theo thời gian |
| **Delta/event count** | Số yêu cầu trong một phút | Phát sinh trong khoảng | SUM các khoảng không trùng |
| **State** | RUNNING, STOPPED, ERROR | Trạng thái theo thời gian | Thời lượng trạng thái, số lần chuyển |
| **Histogram/distribution** | Phân bố latency trong một khoảng | Nhiều bucket/tóm tắt | Gộp histogram đúng cấu trúc; không AVG p95 |
| **Transaction event** | Một lần mua/hoàn | Một sự kiện có định danh riêng | COUNT/DISTINCT/SUM theo grain |

### 6.1. Gauge không phải đại lượng cộng theo thời gian

Nhiệt độ 25 °C lúc 08:00 và 26 °C lúc 08:01 **không** có nghĩa “51 °C của hai phút”. Nếu cần trung bình, dùng AVG theo định nghĩa; với lấy mẫu **không đều**, AVG không trọng số có thể khác trung bình thời gian thực.

Ví dụ: 25 °C kéo dài 9 phút, 35 °C chỉ kéo dài 1 phút. Trung bình hai mẫu là 30 °C, nhưng trung bình có trọng số theo thời lượng là 26 °C, nếu giả định giá trị giữ nguyên giữa hai mốc. Phải nêu giả định nội suy/step-function.

### 6.2. Counter không được SUM các snapshot tích lũy

Đồng hồ điện ghi:

~~~text
08:00 -> 450.0 kWh (tổng tích lũy)
08:01 -> 450.2 kWh
~~~

Mức tiêu thụ trong khoảng là **0,2 kWh**, không phải 900,2 kWh. Nếu counter reset hoặc bị wrap-around, hiệu số có thể âm hoặc nhảy lớn; cần chính sách nhận diện reset/thiết bị thay đồng hồ.

### 6.3. Đơn vị và độ chính xác số

- Dùng kiểu NUMERIC khi cần tính toán thập phân xác định theo miền, ví dụ số tiền; có chi phí lưu và tính toán cao hơn.
- Dùng DOUBLE PRECISION khi dữ liệu đo vật lý phù hợp số chấm động và chấp nhận sai số gần đúng; thiết kế phép so sánh và aggregate tương ứng.
- Không trộn Celsius và Fahrenheit, kW và kWh, bytes và bits, VND và USD trong cùng phép SUM chỉ vì cùng kiểu dữ liệu số.
- Nếu đơn vị có thể đổi, lưu **đơn vị chuẩn/phiên bản metric** và provenance khi chuyển đổi.

Một metric “power_kw” (công suất tức thời) và “energy_kwh” (năng lượng tích lũy) là hai **đại lượng khác nhau**, không phải chỉ hai nhãn của cùng một series.

## 7. Lược đồ quan hệ PostgreSQL: metadata series và bảng quan sát

Để giữ định danh nghiệp vụ rõ ràng mà không lặp lại nhiều khóa trên hàng triệu mẫu, ta tách:

1. **Tenant:** phạm vi tổ chức.
2. **Device:** thiết bị/đối tượng đo trong tenant.
3. **MetricDefinition:** đại lượng và đơn vị chuẩn.
4. **MeasurementSeries:** định danh một dòng đo ổn định.
5. **MeasurementSamples:** giá trị theo timestamp của từng series.

### 7.1. Các bảng định danh và ràng buộc

~~~sql
-- PostgreSQL: chạy các ví dụ trong database thử nghiệm.
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

CREATE TABLE devices (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    device_id BIGINT NOT NULL,
    device_code TEXT NOT NULL,
    device_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, device_id),
    UNIQUE (tenant_id, device_code)
);

CREATE TABLE metric_definitions (
    metric_id BIGINT PRIMARY KEY,
    metric_code TEXT NOT NULL UNIQUE,
    canonical_unit TEXT NOT NULL,
    metric_kind TEXT NOT NULL
        CHECK (metric_kind IN ('GAUGE', 'COUNTER', 'DELTA'))
);

CREATE TABLE measurement_series (
    series_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    metric_id BIGINT NOT NULL REFERENCES metric_definitions(metric_id),
    channel_code TEXT NOT NULL,
    method_code TEXT NOT NULL,

    CONSTRAINT fk_series_device
        FOREIGN KEY (tenant_id, device_id)
        REFERENCES devices(tenant_id, device_id),

    CONSTRAINT uq_series_business_key
        UNIQUE (
            tenant_id, device_id, metric_id,
            channel_code, method_code
        )
);
~~~

Các điểm cần chú ý:

- FK ghép **(tenant_id, device_id)** ngăn dùng device_id của tenant khác. Nếu chỉ tạo FK(device_id) trong một hệ mà device_id không duy nhất toàn cục, dữ liệu có thể không hợp lệ hoặc cấu trúc FK không tạo được.
- **UNIQUE** trên tổ hợp định danh business key bảo vệ không tạo hai series cho cùng dòng đo.
- **series_id** là surrogate key thuận tiện để lưu ở bảng mẫu. Nó không thay đổi ý nghĩa của tổ hợp định danh.
- MetricDefinition giữ **metric_kind** và **canonical_unit**, giúp người dùng không cộng nhầm gauge với counter. Nếu định nghĩa metric thay đổi căn bản, cần metric ID/version mới.
- Channel/method được **NOT NULL**; nếu sử dụng NULL trong tổ hợp UNIQUE, phải xét quy tắc NULL của DBMS và liệu có thể sinh các bản ghi tưởng như trùng nhau.

### 7.2. Bảng mẫu một giá trị hiện hành trên series và instant

~~~sql
CREATE TABLE measurement_samples (
    series_id BIGINT NOT NULL
        REFERENCES measurement_series(series_id),
    observed_at TIMESTAMPTZ NOT NULL,
    measurement_value NUMERIC(16, 5) NOT NULL,
    quality_code TEXT NOT NULL DEFAULT 'OK'
        CHECK (quality_code IN ('OK', 'SUSPECT', 'INVALID')),
    source_revision BIGINT NOT NULL DEFAULT 1
        CHECK (source_revision > 0),
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    PRIMARY KEY (series_id, observed_at)
);
~~~

Khóa chính bảo đảm **tối đa một hàng hiện hành cho một series tại một instant**. Nó **không** chứng minh thời gian nguồn là chính xác, chuỗi không có khoảng trống, metric có đúng đơn vị, hoặc quality_code = OK.

Chọn không thêm CHECK(measurement_value >= 0), vì **nhiệt độ Celsius có thể âm**. Nếu một metric cụ thể không được âm (ví dụ đếm sự kiện), phải xác nhận quy tắc theo metric và triển khai ở nơi có đủ ngữ cảnh; một CHECK chỉ nhìn hàng sample không biết metric_kind của bảng cha.

**received_at** được hệ thống ghi khi chấp nhận hàng và có thể khác observed_at. Việc sử dụng NOW/CURRENT_TIMESTAMP hay clock_timestamp liên quan thời điểm bắt đầu transaction so với thời điểm thực; ở ví dụ chọn clock_timestamp để minh họa timestamp thực lúc câu lệnh chạy.

### 7.3. Dữ liệu mẫu

~~~sql
INSERT INTO tenants (tenant_id, tenant_name)
VALUES (1, 'Nhà máy A');

INSERT INTO devices
    (tenant_id, device_id, device_code, device_name)
VALUES
    (1, 101, 'D-101', 'Cảm biến khu A'),
    (1, 102, 'D-102', 'Cảm biến khu B');

INSERT INTO metric_definitions
    (metric_id, metric_code, canonical_unit, metric_kind)
VALUES
    (10, 'air_temperature', 'degC', 'GAUGE'),
    (20, 'energy_total', 'kWh', 'COUNTER');

INSERT INTO measurement_series
    (series_id, tenant_id, device_id, metric_id,
     channel_code, method_code)
VALUES
    (1001, 1, 101, 10, 'INDOOR', 'CALIBRATED'),
    (1002, 1, 101, 10, 'OUTDOOR', 'CALIBRATED'),
    (1003, 1, 102, 10, 'INDOOR', 'CALIBRATED'),
    (1004, 1, 101, 20, 'TOTAL', 'RAW');

INSERT INTO measurement_samples
    (series_id, observed_at, measurement_value)
VALUES
    (1001, TIMESTAMPTZ '2026-10-10 08:00:00+07', 25.2),
    (1001, TIMESTAMPTZ '2026-10-10 08:01:00+07', 25.4),
    (1001, TIMESTAMPTZ '2026-10-10 08:03:00+07', 25.5),

    (1002, TIMESTAMPTZ '2026-10-10 08:00:00+07', 30.1),
    (1003, TIMESTAMPTZ '2026-10-10 08:00:00+07', 24.8),

    (1004, TIMESTAMPTZ '2026-10-10 08:00:00+07', 450.0),
    (1004, TIMESTAMPTZ '2026-10-10 08:01:00+07', 450.2);
~~~

Hai mẫu của các series khác nhau có **cùng observed_at**, điều hoàn toàn hợp lệ. Với series 1001, không có mẫu ở **08:02**, nên đây là một **gap trong kỳ vọng lấy mẫu mỗi phút** — nếu lịch lấy mẫu thực sự quy định như vậy.

**Không có hàng** ở 08:02 không đồng nghĩa giá trị là 0, cũng chưa chắc cảm biến hỏng; có thể bị mất mạng, giảm tần suất, thiếu quyền truy cập hoặc chưa nhận dữ kiện.

### 7.4. Thử tính duy nhất

Nếu chạy:

~~~sql
INSERT INTO measurement_samples
    (series_id, observed_at, measurement_value)
VALUES
    (1001, TIMESTAMPTZ '2026-10-10 08:00:00+07', 99.9);
~~~

PostgreSQL từ chối vì đã có PK **(1001, 08:00)**. Điều này là đúng **theo grain của bảng measurement_samples**. Nhưng nếu bản tin mới là một hiệu chỉnh hợp lệ, không nên đơn giản “bỏ vì trùng” hoặc “đè vì đến sau”. Cần cơ chế phiên bản/nguồn ở phần tiếp theo.

## 8. Truy vấn theo khóa chuỗi, thứ tự thời gian và chiều

### 8.1. Lấy các mẫu của một series trong khoảng nửa mở

~~~sql
SELECT observed_at, measurement_value, quality_code
FROM measurement_samples
WHERE series_id = 1001
  AND observed_at >= TIMESTAMPTZ '2026-10-10 08:00:00+07'
  AND observed_at <  TIMESTAMPTZ '2026-10-10 08:05:00+07'
ORDER BY observed_at;
~~~

Dùng điều kiện **>= start và < end** giúp hai khoảng liền nhau không cùng giữ một mẫu ở ranh giới, đồng thời không phải tính timestamp “cuối ngày 23:59:59.999999”.

### 8.2. Lấy mẫu gần nhất của từng series

~~~sql
SELECT DISTINCT ON (series_id)
       series_id, observed_at, measurement_value
FROM measurement_samples
WHERE quality_code = 'OK'
ORDER BY series_id, observed_at DESC;
~~~

Với dữ liệu ví dụ, truy vấn trả tối đa một mẫu OK mới nhất **trong mỗi series**. Nếu truy vấn không có điều kiện giới hạn tenant, cần kiểm soát phạm vi thông qua MeasurementSeries và quyền truy cập để tránh đọc dữ liệu tổ chức khác.

**Giá trị mới nhất** chưa chắc là **giá trị hiện tại** về mặt vận hành: cảm biến có thể ngừng gửi nhiều ngày. Dashboard còn phải so observed_at với ngưỡng freshness do nghiệp vụ quy định.

### 8.3. Tìm số đo nhiệt độ INDOOR của thiết bị D-101

~~~sql
SELECT s.series_id,
       m.observed_at,
       m.measurement_value,
       md.canonical_unit
FROM measurement_samples AS m
JOIN measurement_series AS s ON s.series_id = m.series_id
JOIN devices AS d
  ON d.tenant_id = s.tenant_id
 AND d.device_id = s.device_id
JOIN metric_definitions AS md ON md.metric_id = s.metric_id
WHERE s.tenant_id = 1
  AND d.device_code = 'D-101'
  AND md.metric_code = 'air_temperature'
  AND s.channel_code = 'INDOOR'
  AND s.method_code = 'CALIBRATED'
ORDER BY m.observed_at;
~~~

Điều kiện chọn **thiết bị + metric + channel + method** xác định đúng series. Nếu chỉ lọc D-101, câu SQL có thể trộn series nhiệt độ trong nhà, ngoài trời và counter năng lượng.

### 8.4. Trung bình các mẫu trong cửa sổ cố định 5 phút

PostgreSQL hỗ trợ hàm **date_bin** ở các phiên bản phù hợp, cho phép chia thời gian thành các bucket có chiều dài cố định:

~~~sql
SELECT date_bin(
           INTERVAL '5 minutes',
           observed_at,
           TIMESTAMPTZ '1970-01-01 00:00:00+00'
       ) AS bucket_start,
       COUNT(*) AS sample_count,
       AVG(measurement_value) AS sample_average_deg_c
FROM measurement_samples
WHERE series_id = 1001
  AND quality_code = 'OK'
  AND observed_at >= TIMESTAMPTZ '2026-10-10 08:00:00+07'
  AND observed_at <  TIMESTAMPTZ '2026-10-10 08:05:00+07'
GROUP BY bucket_start
ORDER BY bucket_start;
~~~

Ba mẫu 25,2; 25,4; 25,5 cho **sample_average = 25,3666... °C**. Đó là trung bình **theo số mẫu**, không chắc là trung bình **theo thời lượng** vì vắng mẫu 08:02 và khoảng giữa 08:01–08:03 dài hơn.

**date_bin** làm việc với khoảng thời gian cố định có nguồn gốc xác định; không dùng một bucket cố định 24 giờ để thay cho mọi **ngày địa phương** ở vùng có DST. Nếu dùng tháng/quý, hãy dùng quy tắc lịch và công cụ hỗ trợ calendar buckets tương ứng.

### 8.5. Ngày theo timezone nghiệp vụ

Để lấy ngày địa phương của một observed_at khi quy tắc báo cáo là giờ Việt Nam:

~~~sql
SELECT (observed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
           AS vietnam_business_date,
       COUNT(*) AS sample_count
FROM measurement_samples
WHERE series_id = 1001
GROUP BY vietnam_business_date
ORDER BY vietnam_business_date;
~~~

Điều này cho thấy một cách gán ngày trong truy vấn. Khi lọc dữ liệu lớn, nên chuyển ranh giới ngày địa phương thành **hai instant TIMESTAMPTZ** rồi dùng điều kiện range trên observed_at để có cơ hội dùng index/partition pruning. Không dùng timezone server mặc định thay cho timezone nghiệp vụ.

## 9. Khoảng trống, nhịp lấy mẫu và độ bao phủ dữ liệu

Một hệ thống có nhịp đo mỗi phút có thể kỳ vọng:

~~~text
08:00  -> có
08:01  -> có
08:02  -> thiếu
08:03  -> có
~~~

Nhưng kiểm tra gap chỉ đúng nếu biết:

- Series đó **dự kiến hoạt động** trong khoảng ấy không?
- Nhịp lấy mẫu có cố định hay thay đổi theo chế độ vận hành?
- Timestamps có bám chính xác ranh giới phút hay có jitter?
- Có cho gửi bù sau vài phút, vài giờ hoặc vài ngày?
- Quality_code INVALID có được coi là “đã có mẫu” hay “thiếu mẫu hợp lệ”?

### 9.1. Tạo lịch kỳ vọng bằng generate_series

Ví dụ này **giả định timestamps bám đúng ranh giới phút**:

~~~sql
WITH expected AS (
    SELECT step_at AS expected_at
    FROM generate_series(
        TIMESTAMPTZ '2026-10-10 08:00:00+07',
        TIMESTAMPTZ '2026-10-10 08:03:00+07',
        INTERVAL '1 minute'
    ) AS g(step_at)
)
SELECT e.expected_at,
       m.measurement_value,
       CASE WHEN m.observed_at IS NULL THEN 'MISSING'
            ELSE m.quality_code END AS sample_state
FROM expected AS e
LEFT JOIN measurement_samples AS m
  ON m.series_id = 1001
 AND m.observed_at = e.expected_at
ORDER BY e.expected_at;
~~~

Kết quả sẽ đánh dấu **08:02 là MISSING** theo dữ liệu mẫu. Không nên dùng COALESCE(measurement_value, 0) chỉ để bảng hiển thị đẹp hơn; **không có mẫu** khác với **mẫu có giá trị 0**.

Nếu sensor ghi nhận 08:01:00.041, phép JOIN bằng chính xác 08:01:00 không khớp. Cần định nghĩa **quy tắc tolerance/rounding/nearest sample** và xử lý nhiều mẫu có thể rơi vào cùng một bucket. Làm tròn về phút trước khi quyết định grain có thể làm mất dữ liệu nếu không có chính sách tổng hợp hoặc định danh phụ.

### 9.2. Completeness và freshness là hai chỉ tiêu khác nhau

- **Completeness:** trong một khoảng đã đủ thời gian chờ dữ kiện muộn, tỷ lệ slot dự kiến có mẫu hợp lệ là bao nhiêu?
- **Freshness:** đã bao lâu từ lần quan sát hợp lệ mới nhất?
- **Latency:** chênh lệch từ observed_at đến received_at hoặc processed_at là bao nhiêu?
- **Quality:** tỷ lệ mẫu OK, SUSPECT, INVALID theo nguồn/loại lỗi.

Một series có thể **fresh** (vừa gửi một mẫu) nhưng vẫn **thiếu nhiều slot** ở quá khứ; hoặc completeness cao trong một ngày trước nhưng hiện đã ngừng gửi.

### 9.3. Nội suy và điền giá trị thiếu không tạo ra quan sát thật

Các kỹ thuật có thể gồm:

- **Forward fill:** dùng giá trị gần nhất trước đó trong một giới hạn.
- **Linear interpolation:** nội suy giữa hai điểm lân cận.
- **Zero fill:** chỉ khi “thiếu nghĩa là 0” là quy tắc nghiệp vụ thật.
- **Leave missing:** giữ NULL/gap và đưa ra tỷ lệ coverage.

Bản ghi suy diễn phải được **đánh dấu nguồn/phương pháp**; không nên ghi đè các mẫu cảm biến gốc. Với metric rủi ro cao (y tế, an toàn thiết bị, tài chính), không tự áp nội suy để che mất dữ liệu.

## 10. Counter, delta và rate từ chuỗi thời gian

Counter tích lũy cần so các mẫu liên tiếp theo **cùng series**.

~~~sql
WITH counters AS (
    SELECT series_id, observed_at, measurement_value,
           LAG(measurement_value) OVER (
               PARTITION BY series_id
               ORDER BY observed_at
           ) AS previous_value,
           LAG(observed_at) OVER (
               PARTITION BY series_id
               ORDER BY observed_at
           ) AS previous_at
    FROM measurement_samples
    WHERE series_id = 1004
      AND quality_code = 'OK'
)
SELECT observed_at,
       measurement_value,
       previous_value,
       CASE
           WHEN previous_value IS NULL THEN NULL
           WHEN measurement_value >= previous_value
                THEN measurement_value - previous_value
           ELSE NULL
       END AS nonnegative_delta_kwh,
       EXTRACT(EPOCH FROM observed_at - previous_at)
           AS seconds_between_samples
FROM counters
ORDER BY observed_at;
~~~

Từ 450,0 đến 450,2 kWh, delta là **0,2 kWh**. Giá trị counter giảm không nên tự hiểu là “tiêu thụ âm”: có thể do reset, đổi thiết bị, đảo chiều theo định nghĩa metric hoặc bản tin đến sai thứ tự. Ví dụ gán NULL để **đánh dấu cần xử lý theo chính sách**, không tự áp logic sửa counter.

Nếu muốn rate kWh/giờ:

~~~text
rate_kwh_per_hour = delta_kwh / elapsed_seconds * 3600
~~~

Cần kiểm tra elapsed_seconds > 0, chất lượng cả hai điểm, reset và thời điểm quan sát thực. Không chia cho “60 giây mặc định” nếu thực tế hai mẫu cách nhau 59,3 hoặc 120 giây.

Với event count đã được định nghĩa là số phát sinh trong từng cửa sổ không chồng lấp, SUM theo các khoảng hợp lệ có thể phù hợp hơn trừ hai counter; nhưng phải phân biệt cách dữ liệu nguồn được ghi.

## 11. Dữ liệu đến trễ, lặp, hiệu chỉnh và phiên bản phép đo

Một cùng series + observed_at có thể xuất hiện nhiều lần ở đường ingestion vì:

1. **Retry:** cùng quan sát, cùng nội dung.
2. **Correction:** cùng quan sát, giá trị mới/quality mới được nguồn xác nhận.
3. **Out-of-order:** revision mới đến trước revision cũ.
4. **Clock correction:** nguồn sửa timestamp thực của mẫu.
5. **Hai sample độc lập:** grain ban đầu có thể đã định nghĩa sai.

Không thể xử lý cả năm bằng một câu **ON CONFLICT DO UPDATE vô điều kiện**.

### 11.1. Current-state table và update có điều kiện theo source_revision

Nếu nguồn đảm bảo revision_no **tăng đơn điệu theo (series_id, observed_at)**, có thể chỉ cập nhật khi revision mới hơn:

~~~sql
INSERT INTO measurement_samples
    (series_id, observed_at, measurement_value,
     quality_code, source_revision, received_at)
VALUES
    (1001,
     TIMESTAMPTZ '2026-10-10 08:00:00+07',
     25.3, 'OK', 2, clock_timestamp())
ON CONFLICT (series_id, observed_at)
DO UPDATE SET
    measurement_value = EXCLUDED.measurement_value,
    quality_code      = EXCLUDED.quality_code,
    source_revision   = EXCLUDED.source_revision,
    received_at       = EXCLUDED.received_at
WHERE EXCLUDED.source_revision > measurement_samples.source_revision
RETURNING series_id, observed_at, measurement_value, source_revision;
~~~

Bản revision 2 sửa giá trị từ **25,2 thành 25,3**. Nếu revision 1 bị gửi lại sau đó, điều kiện WHERE không cho ghi đè revision 2.

Nhưng lưu ý:

- **Source revision phải ổn định và đáng tin**; không dùng thứ tự đến làm revision.
- Bản tin **cùng revision nhưng payload khác** là xung đột cần quarantine/kiểm tra, không chỉ âm thầm bỏ.
- UPDATE làm mất giá trị hiện hành cũ nếu không có bảng audit/history.
- Khi source sửa **observed_at**, đó là thay đổi thành phần khóa; cần một **source_sample_id** ổn định để biết phải chuyển bản ghi nào.
- Một giá trị mới không nhất thiết là “mẫu mới” để tăng COUNT quan sát; nó có thể là phiên bản của mẫu cũ.

### 11.2. Bảng revision append-only khi cần as-known-at

Nếu phải tái hiện “lúc 09:00 hệ thống từng biết giá trị nào”, có thể giữ các phiên bản:

~~~sql
CREATE TABLE measurement_sample_revisions (
    series_id BIGINT NOT NULL
        REFERENCES measurement_series(series_id),
    observed_at TIMESTAMPTZ NOT NULL,
    source_revision BIGINT NOT NULL CHECK (source_revision > 0),
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    measurement_value NUMERIC(16,5) NOT NULL,
    quality_code TEXT NOT NULL
        CHECK (quality_code IN ('OK', 'SUSPECT', 'INVALID')),
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    PRIMARY KEY (series_id, observed_at, source_revision),
    UNIQUE (source_system, source_event_id)
);
~~~

Trong ví dụ này, bảng revision là **lịch sử nguồn**; bảng measurement_samples ở phần 7 có thể được xem là **projection trạng thái hiện hành**. Không cộng cả hai bảng như hai nguồn sự thật độc lập.

Giả sử mỗi nguồn đảm bảo cùng source_event_id là một bản tin bất biến và source_revision là số phiên bản tăng, truy vấn phiên bản mới nhất **đã biết trước cutoff**:

~~~sql
SELECT DISTINCT ON (series_id, observed_at)
       series_id, observed_at,
       source_revision, measurement_value, quality_code
FROM measurement_sample_revisions
WHERE received_at < TIMESTAMPTZ '2026-10-11 09:00:00+07'
ORDER BY series_id, observed_at, source_revision DESC;
~~~

Nếu các revision đến **khác thứ tự**, truy vấn chọn số revision cao nhất trong tập đã nhận trước cutoff, không đơn thuần chọn bản tin đến cuối. Điều này đúng **theo quy ước revision tăng của nguồn**; nếu nguồn dùng kiểu phiên bản khác, phải điều chỉnh.

Không đặt ra chính sách “mọi bản tin có loaded_at lớn hơn là sự thật mới nhất” khi bản tin cũ có thể đến muộn. Để tái hiện lịch sử đầy đủ còn cần bảo vệ bảng revision khỏi UPDATE/DELETE tùy tiện và quản lý lịch sử dimension.

### 11.3. Không để dedup biến thành che giấu sai dữ liệu

Một khóa UNIQUE có thể chặn INSERT lặp, nhưng không tự phân biệt:

- Retry cùng ID và cùng payload: chấp nhận bỏ qua.
- Cùng ID nhưng payload khác: **xung đột**.
- Hai ID khác cho cùng phép đo do nguồn phát lỗi: cần business dedup.
- Hai ID khác, cùng instant nhưng là hai phép đo thật: **không được tự xóa bớt**.

Chính sách dedup nên lưu **source_system, source_event_id, source_sample_id, source_revision** cùng kết quả kiểm tra payload khi nguồn có dữ liệu đó; phạm vi tenant phải phù hợp.

## 12. Chiều thay đổi theo thời gian: vị trí, chủ sở hữu và phiên bản thiết bị

Vị trí hiện tại của thiết bị không nhất thiết là nơi một mẫu lịch sử đã được đo. Ví dụ thiết bị D-101 chuyển từ khu A sang khu B ngày 20/10:

~~~text
D-101 ở Site A trong [01/10,20/10)
D-101 ở Site B từ 20/10 trở đi
~~~

Một mẫu xảy ra ngày 10/10 phải thuộc Site A theo **as-of observed_at**; không thể JOIN mọi mẫu lịch sử với bảng Devices có site_id hiện hành và tự động gán về Site B.

### 12.1. Mô hình lịch sử vị trí

~~~sql
CREATE TABLE sites (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    site_id BIGINT NOT NULL,
    site_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, site_id)
);

CREATE TABLE device_site_history (
    tenant_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    site_id BIGINT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,

    PRIMARY KEY (tenant_id, device_id, valid_from),
    FOREIGN KEY (tenant_id, device_id)
        REFERENCES devices(tenant_id, device_id),
    FOREIGN KEY (tenant_id, site_id)
        REFERENCES sites(tenant_id, site_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

Điều kiện CHECK ngăn khoảng ngược, nhưng **không cấm** hai hàng site-history của cùng thiết bị có thời gian chồng lấp. Nếu quy định “một thiết bị ở tối đa một site tại mỗi instant”, cần exclusion constraint hoặc cơ chế giao dịch kiểm tra không chồng lấp.

### 12.2. Truy vấn site đúng tại thời điểm phép đo

~~~sql
SELECT m.series_id,
       m.observed_at,
       m.measurement_value,
       h.site_id
FROM measurement_samples AS m
JOIN measurement_series AS s ON s.series_id = m.series_id
JOIN device_site_history AS h
  ON h.tenant_id = s.tenant_id
 AND h.device_id = s.device_id
 AND m.observed_at >= h.valid_from
 AND (h.valid_to IS NULL OR m.observed_at < h.valid_to)
WHERE s.tenant_id = 1;
~~~

Nếu lịch sử có **khoảng trống**, INNER JOIN sẽ làm **rơi mẫu** khỏi báo cáo. Nếu lịch sử **chồng lấp**, JOIN sẽ **nhân bản mẫu**. Cần kiểm tra chất lượng chiều theo thời gian, và có thể dùng LEFT JOIN để đối soát các mẫu chưa tìm được site thay vì âm thầm bỏ qua.

**Cần xác nhận quy tắc danh tính:** nếu một “series” được định nghĩa là phép đo **tại Site A** chứ không phải **từ thiết bị D-101**, khi thiết bị di chuyển có thể phải mở series mới; không chỉ bổ sung lịch sử site.

## 13. Thiết kế chuỗi đa chiều và những trường hợp dễ sai

### 13.1. Một máy có nhiều cảm biến cùng đại lượng

Nếu D-101 có hai đầu dò nhiệt độ đều gọi là INDOOR, tổ hợp tenant/device/metric/channel chưa đủ. Có thể cần:

~~~text
probe_id hoặc sensor_port
~~~

là thành phần định danh. Nếu thay đầu dò cũ bằng đầu dò mới nhưng muốn theo dõi cùng **điểm đo logic**, lựa chọn key phụ thuộc mục tiêu báo cáo: theo thiết bị vật lý hay theo điểm đo ổn định.

### 13.2. Vùng không gian hoặc tọa độ

Một phép đo thời tiết ở lưới tọa độ có thể định danh theo **cell_id + metric + altitude/level** thay vì device_id. Đừng nhét latitude/longitude chấm động vào khóa chính mà chưa quyết định hệ tọa độ, độ chính xác làm tròn, ô lưới và cách xử lý điểm di chuyển.

### 13.3. Kích thước thống kê là một chiều của series

Cùng một cảm biến có thể xuất:

- Nhiệt độ tức thời (RAW).
- Nhiệt độ trung bình 1 phút (AVG_1M).
- Giá trị lớn nhất 1 phút (MAX_1M).

Ba dòng này khác **phương pháp và grain**. Có thể tách raw và aggregates thành các bảng khác nhau, hoặc đưa statistic/window vào khóa aggregate. Không nên lưu chúng cùng series mà không có trường phân biệt vì một số timestamp có thể trùng.

### 13.4. Nhãn nhiều giá trị và phân cấp

Một máy có thể thuộc nhiều nhóm bảo trì. Nếu JOIN mẫu với **tất cả nhóm** rồi SUM đại lượng đo, một sample có thể bị nhân số dòng. Với phép phân nhóm có thể chồng lấp, cần định nghĩa **mỗi mẫu tính một lần cho mỗi nhóm** hay **phân bổ trọng số** khi tổng các nhóm phải cộng lại bằng tổng toàn bộ.

Đặc biệt, không SUM các gauge như nhiệt độ chỉ vì có nhiều mẫu; lựa chọn phép tính phải đi cùng ý nghĩa metric.

### 13.5. Một phép đo nhiều giá trị (vector/histogram)

Một bản tin có thể chứa ba trục gia tốc x, y, z hoặc histogram latency. Có hai lựa chọn:

- Giữ một **quan sát vector** với các thành phần có cấu trúc, nếu mọi trục luôn được đo cùng một lần và thường xử lý cùng nhau.
- Tách thành ba series metric/channel x, y, z, nếu cần truy vấn, gán chất lượng hoặc cập nhật từng trục độc lập.

Không tự coi vector là ba sự kiện độc lập khi chúng chia sẻ **source_sample_id** và một lần hiệu chuẩn. Bảng cấu trúc và khóa phải phản ánh ý nghĩa của cả bộ giá trị.

## 14. Mô hình vật lý: chỉ mục, partition và độ lớn dữ liệu

Một series có thể phát 60 mẫu/phút, tức **86.400 mẫu/ngày**. Nếu hệ thống có 10.000 series hoạt động cùng nhịp, lượng dữ liệu lý thuyết là **864 triệu mẫu/ngày** trước khi xét mất mẫu, nén và metadata. Đây là phép tính quy mô để thiết kế, **không phải benchmark đã chạy**.

Với lượng dữ liệu lớn, quyết định khóa vật lý ảnh hưởng trực tiếp đến ghi, đọc và retention.

### 14.1. Chỉ mục cho một series theo khoảng thời gian

Khóa chính:

~~~sql
PRIMARY KEY (series_id, observed_at)
~~~

trên measurement_samples đã tạo B-tree theo tổ hợp đó. Nó phù hợp các truy vấn:

~~~text
WHERE series_id = ?
  AND observed_at >= ?
  AND observed_at < ?
~~~

và có thể quét theo thứ tự timestamp tăng hoặc giảm trong phạm vi một series. Không nhất thiết phải tạo thêm index **(series_id, observed_at DESC)** chỉ để lấy 10 mẫu mới nhất nếu index hiện có có thể quét ngược hiệu quả.

### 14.2. Truy vấn theo thời gian trên nhiều series

Khi dashboard lấy **mọi series trong một khoảng ngắn**, index bắt đầu bằng series_id có thể không hỗ trợ tốt phép lọc chỉ theo observed_at. Tùy tải, cân nhắc:

~~~sql
CREATE INDEX idx_measurement_samples_time
ON measurement_samples (observed_at);
~~~

hoặc một **BRIN(observed_at)** trên bảng append-only rất lớn nếu các hàng được ghi có **tương quan vật lý** với thời gian quan sát:

~~~sql
CREATE INDEX idx_measurement_samples_time_brin
ON measurement_samples USING brin (observed_at);
~~~

**Không tạo cả hai chỉ mục theo thói quen.** B-tree thường chọn lọc chính xác hơn nhưng lớn/chi phí ghi cao hơn; BRIN gọn khi dữ liệu gần thứ tự thời gian vật lý nhưng có thể phải recheck nhiều trang. Late-arriving samples làm observed_at đi lùi so với thứ tự chèn, giảm tương quan và có thể làm BRIN kém hiệu quả.

Đánh giá bằng **EXPLAIN (ANALYZE, BUFFERS)**, số dòng, số page, độ trễ và chi phí nạp trên dữ liệu đại diện.

### 14.3. Partition theo thời gian

Một bảng sample rất lớn có thể phân vùng theo tháng/ngày trên observed_at để:

- Giới hạn scan nhờ partition pruning khi truy vấn lọc observed_at.
- Quản lý retention hoặc archive từng khoảng.
- Điều phối thao tác bảo trì theo phạm vi dữ liệu.

Nhưng việc partition có chi phí: nhiều index, catalog, kế hoạch, số partition, dữ liệu muộn phải chèn vào partition cũ. Nó không tự giúp truy vấn chỉ lọc **series_id** nhưng không có thời gian.

**Lưu ý PostgreSQL:** Unique/Primary Key trên bảng partitioned phải bao gồm các cột partition key tương ứng theo quy tắc hiện hành. PK(series_id, observed_at) phù hợp với partition theo observed_at, nhưng nếu thiết kế PK khác hoặc partition theo một trường khác thì cần xem xét lại khả năng cưỡng chế uniqueness toàn bảng.

Với các event_id cần UNIQUE toàn cục xuyên partition theo thời gian, không nên giả định một unique index **chỉ trên event_id** có thể cưỡng chế trực tiếp toàn bộ partition PostgreSQL khi partition key không nằm trong ràng buộc. Có thể dùng **bảng dedup/ingestion ledger không partition theo thời gian** hoặc cơ chế định danh/phân vùng khác.

### 14.4. Retention và downsampling

Nếu raw samples chỉ được giữ 90 ngày nhưng aggregates 5 phút được giữ 3 năm:

- Phải xác định các phép tính aggregate, window, đơn vị và chất lượng.
- Cần xử lý late arrivals và correction trong cả raw lẫn aggregate.
- Phải biết **cửa sổ nào đã hoàn chỉnh/finalized** và khi nào cho restatement.
- Không cho phép hai độ phân giải cùng xuất hiện dưới **một series key không phân biệt** rồi bị SUM/AVG lại.
- Khi xóa raw, phải ghi nhận giới hạn khả năng tái tính toán chi tiết.

Nếu một chỉ tiêu aggregate được tính từ 20 mẫu nhưng chỉ còn 15 mẫu hợp lệ sau hiệu chỉnh, phải quyết định tính lại, giữ phiên bản cũ hay phát hành correction. Không coi aggregate là sự thật bất biến chỉ vì raw đã hết hạn.

## 15. So sánh quan hệ, document, time-series DB, graph và kho phân tích

Cùng một yêu cầu “một phép đo có định danh chuỗi và instant” có thể biểu diễn bằng nhiều công nghệ, nhưng quy tắc grain và tính đúng không đổi.

| Kiến trúc | Cách tổ chức thường gặp | Điểm cần kiểm chứng |
| --- | --- | --- |
| **RDBMS/PostgreSQL** | Metadata series + bảng samples có PK/FK và timestamp | Định danh, tính duy nhất, partition/index, late corrections |
| **Time-series DB** | Metric name + tags/labels tạo series; timestamp + value | Cardinality, độ phân giải, duplicate timestamp, retention/downsampling |
| **Document** | Document chứa series và mảng điểm, hoặc một document/mẫu | Cập nhật mảng lớn, index theo thời gian, dedup và lịch sử |
| **Graph** | Node Device/Metric/Site và các cạnh quan hệ theo thời gian | Định danh, as-of relationships, traversal không nhân mẫu |
| **Warehouse/OLAP** | Fact measurements + conformed dimensions/DimTime | Grain, SCD2, measure semantics, rollup và coverage |

### 15.1. Document

Ví dụ một document metadata series:

~~~json
{
  "seriesId": 1001,
  "tenantId": 1,
  "deviceCode": "D-101",
  "metricCode": "air_temperature",
  "channel": "INDOOR",
  "method": "CALIBRATED",
  "canonicalUnit": "degC"
}
~~~

và một document điểm đo:

~~~json
{
  "seriesId": 1001,
  "observedAt": "2026-10-10T08:00:00+07:00",
  "value": 25.2,
  "quality": "OK",
  "sourceRevision": 1
}
~~~

Giữ một document **trên mỗi quan sát** có thể giúp index theo series/time, nhưng cần xác nhận uniqueness và cách update. Nhúng **vô hạn** điểm vào một document series có thể làm document quá lớn và tạo điểm nóng ghi. Một số document DB có cơ chế bucketing; cần so sánh chính xác theo sản phẩm sử dụng.

### 15.2. Time-series database và labels

Một số TSDB coi **tên metric + tập labels/tags** là định danh series. Ví dụ:

~~~text
air_temperature{tenant="1",device="D-101",
                channel="INDOOR",method="CALIBRATED"}
~~~

Đây là cách biểu diễn cùng ý nghĩa với series business key trong bảng quan hệ. Nhưng cách xử lý **hai sample cùng timestamp**, backfill, chất lượng, nhãn thay đổi và retention **phụ thuộc sản phẩm/phiên bản**. Không tự giả định mọi TSDB dùng cùng chính sách duplicate hoặc tự đảm bảo exactly-once.

Đưa request_id hay user_id rất động vào labels có thể khiến cardinality tăng theo số request, thay vì theo số thiết bị × metric × channel. Trước khi thêm label, cần ước lượng **số series đang hoạt động**, vòng đời và số chiều tổ hợp.

### 15.3. Graph và context thay đổi theo thời gian

Graph hữu ích khi một thiết bị qua nhiều vị trí, có quan hệ phụ thuộc nhiều cấp hoặc cần truy vết mạng cảm biến. Nhưng việc dùng graph không tự giải quyết storage của hàng tỷ sample hay phép trung bình theo thời gian.

Thường có thể kết hợp:

~~~text
Graph: Device --LOCATED_AT(valid_from,valid_to)--> Site
TSDB/Fact: (series_id, observed_at) -> value
~~~

Khi JOIN/traversal graph để gán site cho sample, phải lấy **quan hệ có hiệu lực tại observed_at**, không lấy mọi đường liên quan tới Device. Một Device có nhiều đường trong graph có thể làm cùng một sample bị đếm nhiều lần.

### 15.4. Warehouse và grain đo lường

Trong kho phân tích, một fact có thể có khóa:

~~~text
FactMeasurement(
  series_key,
  observed_time_key,
  device_version_key,
  location_version_key,
  value,
  quality_code
)
~~~

Nhưng không nên mặc định cả **series_key** lẫn tất cả dimension version đều độc lập; nếu thay đổi thuộc tính dimension làm phát sinh nhiều hàng khi JOIN, KPI có thể bị nhân. Cần định nghĩa conformed dimensions, SCD2 theo thời điểm sự kiện và grain đúng.

Một fact **temperature gauge** không thể SUM qua ngày chỉ vì nó là cột số. Một fact **energy delta** có thể cộng qua thời gian nếu các khoảng không chồng, đúng unit và không có sự kiện trùng.

## 16. Bộ kiểm thử ràng buộc và chất lượng dữ liệu

Một mô hình series nên có kiểm thử cố định trước và sau khi nạp, đặc biệt khi thay đổi cấu trúc hoặc thêm loại metric.

### 16.1. Kiểm tra các bất biến dữ liệu

| Bất biến | Cách kiểm chứng |
| --- | --- |
| Series business key duy nhất | UNIQUE trên đúng tổ hợp tenant/device/metric/channel/method |
| Sample current-state không trùng | PK(series_id, observed_at) nếu grain một mẫu/instant |
| Mọi sample thuộc series tồn tại | FK tới measurement_series |
| Mọi series trỏ tới device cùng tenant | FK ghép (tenant_id,device_id) |
| Metric có đơn vị và loại rõ | MetricDefinition + ràng buộc miền |
| Timestamp có instant đúng | TIMESTAMPTZ, timezone/offset nguồn, kiểm tra clock |
| Mẫu cùng revision không mâu thuẫn | Unique revision/source ID + kiểm tra payload |
| Revision cũ không đè revision mới | Upsert có điều kiện hoặc projection từ event history |
| Site theo thời điểm không chồng lấp | Effective-dated dimension + kiểm tra khoảng |
| Snapshot không bị cộng theo thời gian | Quy tắc semantic layer và test KPI |
| Missing khác zero | Test gap/coverage và quality |
| Rollup không lẫn raw | Grain/metric/window/method phân biệt |
| Truy vấn không vượt tenant | Query predicate, quyền DB/RLS nếu áp dụng |
| Event đến muộn không bị bỏ sót | Watermark, retry/backfill, đối soát nguồn–đích |

### 16.2. Truy vấn kiểm kê số sample theo series

~~~sql
SELECT series_id,
       COUNT(*) AS sample_count,
       MIN(observed_at) AS first_observed_at,
       MAX(observed_at) AS last_observed_at,
       COUNT(*) FILTER (WHERE quality_code <> 'OK')
           AS non_ok_samples
FROM measurement_samples
GROUP BY series_id
ORDER BY series_id;
~~~

Điều này giúp xem độ phủ và chất lượng ở mức tổng quát, nhưng **COUNT(*) không thay cho expected slots**. Một series lấy mẫu 1 lần/ngày không thể bị coi là thiếu dữ liệu chỉ vì có ít hàng hơn series lấy mẫu mỗi giây.

### 16.3. Tìm các vị trí có nhiều revision

~~~sql
SELECT series_id, observed_at,
       COUNT(*) AS revision_count,
       MIN(source_revision) AS first_revision,
       MAX(source_revision) AS last_revision
FROM measurement_sample_revisions
GROUP BY series_id, observed_at
HAVING COUNT(*) > 1
ORDER BY series_id, observed_at;
~~~

Nhiều revision không tự là lỗi: có thể phản ánh việc nguồn đã sửa phép đo hợp lệ. Nhưng cần biết version cao nhất đã được áp vào current-state, có bản tin xung đột hoặc thời điểm đã công bố hay không.

### 16.4. Phát hiện series có độ trễ lớn

~~~sql
SELECT series_id,
       COUNT(*) AS count_samples,
       AVG(EXTRACT(EPOCH FROM received_at - observed_at))
           AS avg_lag_seconds,
       MAX(EXTRACT(EPOCH FROM received_at - observed_at))
           AS max_lag_seconds
FROM measurement_samples
GROUP BY series_id;
~~~

Đây là minh họa trên bảng current-state. Nếu received_at bị UPDATE khi nhận correction, nó phản ánh **lần cập nhật gần nhất** chứ không còn là **thời điểm nhận lần đầu**. Muốn đo lateness của nguồn ban đầu, cần lịch sử ingestion riêng.

Không coi mọi lag âm là “nhiệt độ tương lai”: có thể đồng hồ nguồn bị lệch hoặc hệ thống gửi thời điểm dự báo. Phải phân loại metric và quy tắc timestamp.

## 17. Quy trình chuyển yêu cầu thành thiết kế

Để mô hình một nguồn time-series mới, áp dụng tuần tự:

1. **Định nghĩa thực thể được đo.** Theo dõi device vật lý, điểm đo logic, site cố định, người dùng, giao dịch hay ô lưới không gian?
2. **Định nghĩa metric.** Tên, đơn vị chuẩn, gauge/counter/delta/state, miền giá trị và phiên bản phương pháp.
3. **Định nghĩa series business key.** Những chiều nào khi khác nhau thì bắt buộc trở thành series khác? Những chiều nào chỉ là metadata?
4. **Viết grain observation.** Một series/instant có tối đa một mẫu hay nhiều mẫu hợp lệ? Nguồn có sample ID ổn định không?
5. **Định nghĩa thời gian.** observed, recorded, received, effective, window start/end, timezone, độ phân giải và đồng hồ nguồn.
6. **Định nghĩa dữ liệu thiếu và chất lượng.** Chưa đo, mất kết nối, INVALID, SUSPECT, zero thực và nội suy có phải khác trạng thái không?
7. **Chọn mô hình vật lý.** Bảng metadata + sample, event append-only, revision table, document, TSDB hoặc mô hình kết hợp.
8. **Thiết kế khóa/ràng buộc.** PK, UNIQUE, FK theo tenant, dimension versions và quy tắc chống trùng.
9. **Thiết kế cập nhật.** Retry, out-of-order, sửa timestamp/giá trị, source version và yêu cầu as-known-at.
10. **Thiết kế truy vấn.** Theo series, theo mọi series trong khoảng, last-known, bucket, counter delta, gap và site as-of.
11. **Thiết kế dữ liệu lớn.** Chỉ mục, partition, compression, retention, downsampling và backfill.
12. **Tạo dữ liệu thử biên.** Hai kênh cùng instant, cùng sample retry ba lần, hai bản sửa, DST, clock drift, mất một slot.
13. **Đo và đối soát.** EXPLAIN, dữ liệu đại diện, throughput, số active series, độ trễ ingest, coverage và số xung đột.
14. **Ghi hợp đồng dữ liệu.** Đơn vị, version, key, grain, timezone, chất lượng, quyền truy cập và chính sách lịch sử.

### 17.1. Mẫu hợp đồng định danh một phép đo

~~~text
Business entity:
  Điểm đo nhiệt độ indoor của D-101, tenant 1.

Metric:
  air_temperature; canonical_unit=degC; kind=GAUGE.

Series business key:
  (tenant_id, device_id, metric_id, channel_code, method_code)
  = (1, 101, 10, INDOOR, CALIBRATED).

Observation grain:
  Một giá trị hiện hành tại mỗi observed_at cho một series.

Observation key:
  (series_id, observed_at)

Source identity:
  source_system + source_sample_id, nếu nguồn hỗ trợ.

Time semantics:
  observed_at = instant đã chuẩn hóa;
  received_at = timestamp nhận tại pipeline;
  business timezone = theo site có hiệu lực tại observed_at.

Duplicates:
  Cùng source ID/payload = retry;
  cùng source ID nhưng payload khác = lỗi/phiên bản có kiểm soát.

Corrections:
  Ưu tiên source_revision cao hơn;
  lưu revision log nếu phải truy vết.

Missing/quality:
  NULL/gap khác zero; INVALID không tính vào AVG hợp lệ.

Retention:
  Raw 90 ngày (chỉ nếu chính sách chấp thuận);
  rollup 5 phút có method và calculation_version.

Queries:
  Series timeline, latest OK, gap, hourly AVG, site as-of.
~~~

Hợp đồng này cần được cập nhật khi thiết bị, metric, phương pháp hay yêu cầu nghiệp vụ thay đổi. Không chỉ viết “timestamp + value” rồi hy vọng tất cả hệ thống dùng cùng cách hiểu.

## 18. Bài tập có hướng dẫn giải

### Bài 1. Timestamp có đủ làm khóa?

**Đề bài:** Hai cảm biến khác nhau cùng đo lúc 08:00:00. Có thể dùng observed_at làm PRIMARY KEY chung cho bảng Measurement không?

**Gợi ý giải:** Không. Hai quan sát ở **hai series khác nhau** có thể cùng timestamp. Cần thêm series identity hoặc định danh mẫu từ nguồn, theo grain đã định nghĩa.

### Bài 2. Thêm channel vào khóa chuỗi

**Đề bài:** Thiết bị D-101 đo nhiệt độ INDOOR và OUTDOOR tại 08:00. Khóa (device_id, metric_id, observed_at) có đủ không?

**Gợi ý giải:** Không, vì hai kênh vẫn trùng. Nếu channel tạo hai dòng quan sát khác nhau, nó phải nằm trong **series business key**, hoặc là thành phần của khóa observation nếu không dùng series_id.

### Bài 3. Sample cùng timestamp nhưng khác ID

**Đề bài:** Cảm biến tốc độ cao gửi hai sample thực khác nhau cùng timestamp đến millisecond, mỗi mẫu có source_sample_id ổn định. Có nên UPDATE mẫu thứ hai lên mẫu thứ nhất không?

**Gợi ý giải:** Không. Đây có thể là **hai quan sát hợp lệ**. Sửa grain, ví dụ dùng source_sample_id hoặc sample_seq ổn định; không bỏ bớt chỉ vì timestamp giống nhau.

### Bài 4. Gauge và counter

**Đề bài:** Nhiệt độ 25 rồi 26 °C, counter điện 450,0 rồi 450,2 kWh. Phép tính nào phù hợp?

**Gợi ý giải:** Nhiệt độ là gauge: AVG/MIN/MAX tùy câu hỏi, không SUM thành 51 °C. Counter năng lượng có delta 0,2 kWh nếu không reset; không SUM thành 900,2 kWh.

### Bài 5. Đến trễ nhưng cùng thời điểm quan sát

**Đề bài:** Mẫu đo 08:00 đến pipeline lúc 08:10. Dashboard theo ngày đo nên gán 08:00 hay 08:10?

**Gợi ý giải:** Gán theo **observed_at 08:00**. **received_at 08:10** dùng để đo latency hoặc as-known-at. Không biến dữ liệu muộn thành mẫu mới lúc nhận.

### Bài 6. Sửa mẫu cũ

**Đề bài:** Series 1001 lúc 08:00 có revision 1 giá trị 25,2, sau đó revision 2 giá trị 25,3. Nếu báo cáo hỏi “giá trị mới nhất đã xác nhận”, nên lấy gì?

**Gợi ý giải:** Lấy **revision 2 = 25,3** theo quy tắc revision tăng của nguồn. Nếu cần tái hiện báo cáo cũ, giữ revision log/received_at; không chỉ overwrite mà không có lịch sử.

### Bài 7. Firmware version có phải tag định danh?

**Đề bài:** D-101 thay firmware mỗi tháng nhưng loại phép đo không đổi. Có nên tự tạo series mới mỗi lần firmware thay đổi?

**Gợi ý giải:** Không mặc định. Firmware có thể là **thuộc tính theo thời gian** của device. Chỉ tạo series mới nếu nó làm thay đổi **ngữ nghĩa/method** của phép đo hoặc yêu cầu phân tích quy định phải tách.

### Bài 8. Thiết bị di chuyển

**Đề bài:** D-101 ở Site A đến 20/10, sau đó ở Site B. Báo cáo nhiệt độ Site A ngày 10/10 phải JOIN site nào?

**Gợi ý giải:** Site A, theo khoảng hiệu lực chứa **observed_at** của mẫu. JOIN với site hiện hành làm sai lịch sử; nếu có nhiều khoảng khớp phải xử lý dữ liệu chồng lấp.

### Bài 9. Gap là zero?

**Đề bài:** Series có giá trị 25,2 lúc 08:00 và 25,4 lúc 08:01, không có hàng 08:02. Có được điền 0 vào báo cáo tự động không?

**Gợi ý giải:** Không, trừ khi chính sách nghiệp vụ nói **thiếu nghĩa là zero**. Đây là một gap. Có thể để NULL, cảnh báo thiếu hoặc sử dụng phương pháp nội suy được ghi nhãn.

### Bài 10. Kích thước cửa sổ có thuộc khóa?

**Đề bài:** Một series có AVG_1M và AVG_5M đều gắn timestamp 08:05. Khóa (series_id, timestamp) có đủ cho bảng aggregates không?

**Gợi ý giải:** Không. Cần phân biệt **window length, aggregation method** và có thể calculation_version, hoặc lưu các aggregate ở những series/bảng tách biệt có grain rõ.

### Bài 11. Địa phương và DST

**Đề bài:** Hai bản tin có local time 01:30 trong ngày đổi giờ lùi ở một vùng có DST. Nếu chỉ lưu local time không offset/timezone, có thể phân biệt hai instant không?

**Gợi ý giải:** Không chắc. Cần offset hoặc thông tin timezone và quy tắc giải mơ hồ, sau đó chuẩn hóa về instant để lưu/so sánh.

### Bài 12. Index nào cho lịch sử một series?

**Đề bài:** Truy vấn luôn lọc series_id, khoảng observed_at và ORDER BY observed_at DESC. Đã có PK(series_id, observed_at). Có cần chắc chắn tạo thêm index DESC không?

**Gợi ý giải:** Không. B-tree nhiều trường hiện có có thể quét ngược trong phạm vi series. Hãy đọc **EXPLAIN (ANALYZE, BUFFERS)** trước khi thêm index trùng công dụng.

### Bài 13. Nhiều tenant

**Đề bài:** Tenant 1 và 2 đều có device_id=101. Một bảng Series chỉ FK(device_id) tới Device có đảm bảo cùng tenant không?

**Gợi ý giải:** Không. Cần khóa ghép **(tenant_id, device_id)** và FK ghép tương ứng, hoặc thiết kế định danh Device duy nhất toàn hệ thống có ràng buộc tenant rõ.

### Bài 14. Nạp lại cùng source_event_id

**Đề bài:** Một sample được phát lại ba lần. Nếu mỗi lần tạo một sample_id auto-increment mới, hệ quả gì?

**Gợi ý giải:** Có thể thành ba phép đo giả và làm lệch COUNT/AVG. Cần nhận diện **cùng sự kiện nguồn** bằng khóa ổn định, dedup có kiểm tra payload và xử lý sửa phiên bản riêng.

### Bài 15. Thay timestamp vì chỉnh đồng hồ

**Đề bài:** Nguồn sửa observed_at của mẫu từ 08:00:00 sang 07:59:59.950 do phát hiện clock drift. Vì sao UPDATE mỗi cột timestamp có thể cần kiểm tra thêm?

**Gợi ý giải:** observed_at là thành phần **khóa observation** trong mô hình hiện tại. Việc đổi có thể va chạm khóa khác, thay bucket báo cáo, làm sai tham chiếu hoặc lịch sử. Cần source_sample_id ổn định và quy trình correction/restatement có kiểm chứng.

## 19. Ghi nhớ

- **Khóa chuỗi** được tạo từ những chiều làm hai dòng đo khác nhau về ngữ nghĩa: chủ thể, metric, kênh, phương pháp và phạm vi tenant khi cần.
- **Khóa phép đo** thường là **series + instant**, nhưng chỉ đúng khi có tối đa một quan sát hợp lệ tại một instant của series. Nếu có nhiều mẫu thật, cần source_sample_id/sequence hoặc grain khác.
- **Timestamp không phải toàn bộ danh tính.** Phân biệt observed_at, received_at, event/valid time, timestamp của cửa sổ và timezone.
- **Metric kind quyết định phép tính:** gauge, counter, delta, state và aggregate không thể tùy ý SUM/AVG như nhau.
- **Dimension có hiệu lực theo thời gian** phải được JOIN theo observed_at, không nhất thiết theo thuộc tính hiện hành của thiết bị.
- **Late arrivals, retry và revisions** cần định danh nguồn ổn định, quy tắc upsert/dedup, phiên bản và đối soát.
- **Series cardinality và dữ liệu vật lý** tác động đến khả năng mở rộng: tránh labels thay đổi quá nhanh, đo index/partition/retention dựa trên tải đại diện.
- **Missing khác zero, sample khác interval aggregate, observed time khác ingestion time.** Nếu mất các phân biệt này, một lược đồ có thể hợp lệ về cú pháp nhưng sai kết quả phân tích.

Một mô hình chuỗi thời gian đáng tin không chỉ lưu **timestamp + value**. Nó cho phép trả lời chính xác: **đây là phép đo của đối tượng nào, đại lượng và phương pháp nào, tại instant hoặc khoảng nào, có phải bản mới hay bản sửa, và có được tổng hợp với những phép đo khác hay không?**
