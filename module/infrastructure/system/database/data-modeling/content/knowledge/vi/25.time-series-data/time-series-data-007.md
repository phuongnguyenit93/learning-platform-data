# Lưu dữ liệu thô, tổng hợp nhiều mức và giảm độ phân giải

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **dữ liệu thô** (*raw measurements/events*), **bảng tổng hợp theo khoảng thời gian** (*time-bucket rollup*) và **dữ liệu đã giảm độ phân giải** (*downsampled series*).
- Xác định **grain**, khóa định danh, mốc thời gian sự kiện, mốc nhận dữ liệu và nguồn chuẩn cho một phép đo trước khi tạo bảng hoặc index.
- Thiết kế chuỗi tổng hợp **raw → 5 phút → 1 giờ → 1 ngày** với công thức hợp nhất đúng, kể cả khi số mẫu không đều.
- Giải thích vì sao **AVG của các AVG**, **SUM của số dư/tồn kho**, **AVG của phần trăm**, **SUM của percentile** hoặc cộng giá trị counter tích lũy có thể sai.
- Xây dựng lược đồ và truy vấn PostgreSQL cho phép đo nhiệt độ, tính rollup có thể chạy lại, đối soát, xử lý dữ liệu đến muộn và bảo vệ ranh giới thời gian.
- Lựa chọn retention, độ phân giải truy vấn, cách biểu diễn khoảng trống và tiêu chí giảm dữ liệu mà vẫn đủ thông tin cho những quyết định nghiệp vụ cần hỗ trợ.
- So sánh cách lưu chuỗi thời gian trong mô hình quan hệ, document, đồ thị và hệ phân tích, cùng các đánh đổi về chi phí đọc/ghi, độ chính xác và tiến hóa lược đồ.

Bài thuộc chương **Dữ liệu chuỗi thời gian** của **DATABASE_DATA_MODELING**. Trong module này, việc chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, khóa, chỉ mục và lược đồ vật lý phải bắt đầu từ câu hỏi: **mỗi điểm dữ liệu có ý nghĩa gì, tại thời điểm nào, và một lần tổng hợp sẽ giữ lại hay làm mất điều gì?**

## 1. Tình huống: một cảm biến ghi nhiều triệu mẫu

Một nhà máy có nhiều cảm biến nhiệt độ gửi dữ liệu về mỗi vài giây. Hệ thống cần:

1. Hiển thị đồ thị **15 phút gần nhất** với độ chi tiết cao để theo dõi biến động.
2. Cho trưởng ca xem **24 giờ gần nhất** theo từng 5 phút.
3. Cho quản lý xem **90 ngày gần nhất** theo từng giờ, cùng mức nhiệt độ thấp nhất và cao nhất.
4. Cho bộ phận vận hành xem xu hướng nhiều năm theo ngày hoặc tuần.
5. Điều tra một sự cố cụ thể bằng **mẫu thô và thời điểm đo ban đầu** nếu dữ liệu còn trong thời hạn lưu.
6. Nhận các mẫu gửi lại do mất mạng, một số mẫu đến muộn hàng phút hoặc hàng giờ.

Một cách làm đơn giản là lưu mọi mẫu thô mãi mãi rồi chạy truy vấn đọc hàng trăm triệu điểm cho mọi biểu đồ. Cách đó có thể không khả thi về tài nguyên. Một cách khác là chỉ lưu **giá trị trung bình theo giờ**; khi đó dung lượng nhỏ nhưng mọi đỉnh nhiệt độ ngắn và thời điểm đo cụ thể đều bị mất.

Thiết kế phù hợp thường gồm **nhiều cấp biểu diễn cùng một dòng dữ liệu**:

~~~text
Thiết bị / nguồn sự kiện
         |
         v
Raw measurement store (grain: một mẫu đo)
         |
         +--------> Tra cứu sự cố gần đây
         |
         v
Rollup 5 phút: count, sum, min, max, ...
         |
         +--------> Biểu đồ theo ca
         |
         v
Rollup 1 giờ: hợp nhất từ 5 phút
         |
         +--------> Dashboard theo ngày / 90 ngày
         |
         v
Rollup 1 ngày: theo ngày nghiệp vụ
         |
         +--------> Xu hướng dài hạn

Mỗi cấp có retention, freshness và cách đối soát riêng.
~~~

**Raw** là nguồn chuẩn cho những giá trị đo đã nhận và được chấp nhận. Bảng 5 phút/giờ/ngày là **dữ liệu dẫn xuất** có thể xây lại khi đủ raw. Nhưng khi raw đã hết thời hạn giữ, không thể mặc định tái tạo được mọi mẫu từ rollup: đó là phần thông tin đã chủ động đánh đổi.

## 2. Tuyên bố grain trước khi chọn khóa và số đo

Với chuỗi thời gian, ba thực thể thường cần phân biệt:

- **Thiết bị/cảm biến**: một nguồn đo có định danh ổn định, loại đại lượng, đơn vị, vị trí hoặc hiệu chuẩn.
- **Mẫu thô**: một lần đo được thiết bị xác định và gửi, có **event time**, ID hoặc sequence để nhận biết gửi trùng.
- **Bucket tổng hợp**: một nhóm mẫu thỏa điều kiện **cảm biến × khoảng thời gian × quy tắc chất lượng**, lưu các trạng thái thống kê để tính kết quả.

Tuyên bố grain ví dụ:

> **raw_temperature:** mỗi hàng là một phép đo nhiệt độ do một sensor phát sinh, nhận diện bởi `(sensor_id, source_sample_id)`; `observed_at` là thời điểm đo.

> **temperature_5m:** mỗi hàng là thống kê các mẫu hợp lệ của **một sensor** có `observed_at` nằm trong **một bucket UTC 5 phút nửa mở**.

> **temperature_hourly:** mỗi hàng là thống kê các mẫu hợp lệ của **một sensor** trong **một giờ UTC nửa mở**, hợp nhất từ các bucket 5 phút đã đầy đủ.

Điều này ngăn bốn nhầm lẫn thường gặp:

1. **Timestamp không nhất thiết là khóa duy nhất.** Thiết bị có thể gửi hai phép đo tại cùng timestamp với ID khác nhau.
2. **Thời điểm nhận khác thời điểm đo.** Không gom dữ liệu muộn theo ngày nó đến server nếu báo cáo hỏi ngày xảy ra sự kiện.
3. **Một bucket không phải một mẫu.** Số đo trung bình là phép dẫn xuất có điều kiện, không thay thế giá trị từng mẫu.
4. **Vắng hàng không chắc bằng số 0.** Có thể không có mẫu, thiết bị ngừng đo, đường truyền bị lỗi hoặc pipeline chưa hoàn thành.

### 2.1. Các khái niệm thời gian cần có trong hợp đồng

| Tên | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **observed_at / event time** | Khi phép đo diễn ra theo nguồn | 08:01:04 |
| **received_at / ingestion time** | Khi hệ thống nhận bản ghi | 08:04:32 |
| **processed_at** | Khi pipeline xử lý hoặc ghi rollup | 08:05:10 |
| **bucket_start** | Cận đầu của khoảng tổng hợp | 08:00:00 |
| **watermark** | Mốc event time được pipeline xem là đủ ổn định theo chính sách đến muộn | 07:55:00, tùy cấu hình |
| **business date** | Ngày trong múi giờ và quy tắc báo cáo nghiệp vụ | Ngày tại một nhà máy |

Nếu đồng hồ thiết bị bị lệch, event time có thể không đáng tin. Cần nguồn đồng hồ, chính sách chấp nhận sai lệch và khả năng đánh dấu mẫu bất thường. **Không sửa hàng loạt event time bằng received_at mà không ghi nhận đây là thay đổi ý nghĩa dữ liệu.**

### 2.2. Metadata cảm biến là dimension, không phải trường phải sao chép vô hạn

Một cảm biến có thể có `sensor_id`, vị trí, loại đo, đơn vị, thời điểm hiệu chuẩn và trạng thái hoạt động. Bảng raw chỉ nên chứa thuộc tính cần để giữ ngữ nghĩa mẫu và phục vụ truy vấn thường xuyên; metadata hiện hành có thể nằm trong **dim_sensor** hoặc một kho quản lý thiết bị.

Nếu cảm biến được chuyển từ khu A sang khu B, báo cáo lịch sử có thể hỏi **vị trí lúc đo** hay **vị trí hiện hành**. Khi cần vị trí lúc đo, phải dùng snapshot/phiên bản có hiệu lực, không tự gắn vị trí hiện tại cho mọi mẫu cũ.

## 3. Raw, rollup và downsampling không đồng nghĩa nhau

| Loại | Một hàng biểu diễn | Còn giữ được gì? | Điều bị mất / rủi ro |
| --- | --- | --- | --- |
| **Raw event/measurement** | Một sự kiện hoặc mẫu đo | Giá trị, thời điểm và ID cụ thể | Tốn dung lượng, index và chi phí truy vấn dài hạn |
| **Rollup 5 phút** | Một sensor × một bucket 5 phút | COUNT/SUM/MIN/MAX và trạng thái khác đã chọn | Không biết chính xác các mẫu nằm tại giây nào nếu không lưu thêm |
| **Rollup 1 giờ** | Một sensor × một giờ | Thống kê có thể hợp nhất từ bucket nhỏ | Mất thứ tự diễn biến trong giờ |
| **Daily rollup** | Một sensor × ngày nghiệp vụ | Xu hướng và thống kê ngày | Không tái tạo được sự cố kéo dài vài giây |
| **Điểm biểu đồ downsampled** | Điểm được chọn/tổng hợp theo phạm vi hiển thị | Đủ chi tiết cho số pixel hoặc mục tiêu đọc | Mất chi tiết, có nguy cơ che đỉnh và biến động |

**Rollup** thường giữ các **trạng thái tính toán** như `sample_count`, `value_sum`, `min`, `max`. **Downsampling** là chủ động biểu diễn dữ liệu ở độ phân giải thấp hơn. Một rollup là một cách hỗ trợ downsampling nhưng không phải cách duy nhất: có thể chọn điểm đại diện, giữ min/max hoặc dùng phương pháp phù hợp hình dạng tín hiệu.

Không nên coi các bảng tổng hợp là “những bản sao raw”. Chúng là **mô hình có grain mới, công thức mới và mất mát thông tin được chủ động chấp nhận**.

## 4. Bucket nửa mở: đặt một mẫu đúng một nơi

Đối với bucket 5 phút tính theo UTC:

~~~text
[08:00:00, 08:05:00)    nhận mẫu 08:00:00 ... 08:04:59.999...
[08:05:00, 08:10:00)    nhận mẫu đúng 08:05:00
[08:10:00, 08:15:00)    nhận mẫu đúng 08:10:00
~~~

Dấu **[)** nghĩa là bao gồm cận đầu và **không bao gồm cận cuối**. Một mẫu ở đúng **08:05:00** chỉ thuộc bucket bắt đầu 08:05, không xuất hiện đồng thời ở hai bucket.

Với bucket độ rộng cố định `w` và gốc thời gian `origin`, có thể hình dung:

$$
b(t) = \mathrm{origin} + \left\lfloor \frac{t-\mathrm{origin}}{w} \right\rfloor w
$$

Công thức mô tả cách xác định `bucket_start` từ timestamp tuyệt đối; trong PostgreSQL có thể dùng `date_bin` với khoảng cố định. Ví dụ:

~~~sql
SELECT date_bin(
    INTERVAL '5 minutes',
    TIMESTAMPTZ '2026-11-22 08:07:23+00',
    TIMESTAMPTZ '1970-01-01 00:00:00+00'
) AS bucket_start;
-- 2026-11-22 08:05:00+00
~~~

**Chú ý:** `date_bin` phù hợp khoảng cố định như phút/giờ; không dùng trực tiếp khoảng chứa tháng vì tháng có độ dài lịch khác nhau. “Một ngày UTC” cũng khác “ngày kinh doanh theo giờ địa phương” ở nơi đổi giờ mùa hè; cần xác định loại bucket trước khi chọn hàm.

### 4.1. UTC và ngày kinh doanh không phải lúc nào cùng ranh giới

Phần lưu raw nên giữ timestamp tuyệt đối rõ nghĩa, thường là `TIMESTAMPTZ` với quy ước thời gian nhất quán. Khi báo cáo theo **ngày địa phương**, ví dụ `Asia/Ho_Chi_Minh`, cần chuyển event time sang giờ địa phương rồi lấy ngày:

~~~sql
SELECT
    (TIMESTAMPTZ '2026-11-22 00:30:00+07'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
    AS business_date;
-- 2026-11-22
~~~

Đối với nhiều khu vực, có thể có ngày dài 23 hoặc 25 giờ do đổi giờ mùa hè. Vì vậy **rollup 1 ngày địa phương không luôn bằng 24 rollup giờ UTC**. Nếu thiết kế hệ thống đa múi giờ, phải chọn đúng các bucket giờ nằm trong khoảng từ **đầu ngày địa phương** tới **đầu ngày địa phương tiếp theo**, sau khi chuyển sang timestamp tuyệt đối.

## 5. Số đo nào có thể tổng hợp qua nhiều cấp?

Một phương pháp đúng phải dựa trên **phép hợp nhất thống kê** chứ không chỉ dựa vào tên hàm SQL.

### 5.1. Trạng thái thống kê có thể hợp nhất

Giả sử bucket A có `count_A, sum_A, min_A, max_A`; bucket B có các trạng thái tương tự. Để gộp hai tập mẫu **không chồng nhau**:

$$
\operatorname{count}_{A\cup B}=\operatorname{count}_A+\operatorname{count}_B
$$

$$
\operatorname{sum}_{A\cup B}=\operatorname{sum}_A+\operatorname{sum}_B
$$

$$
\min_{A\cup B}=\min(\min_A,\min_B),\quad \max_{A\cup B}=\max(\max_A,\max_B)
$$

$$
\operatorname{avg}_{A\cup B}=\frac{\operatorname{sum}_A+\operatorname{sum}_B}{\operatorname{count}_A+\operatorname{count}_B}
$$

Điều kiện quan trọng: các bucket **cùng đơn vị, cùng quy tắc lọc mẫu và không chồng lấn**. `count` là số mẫu hợp lệ, không phải số phút trong bucket.

Có thể lưu thêm các trạng thái cần cho thống kê khác như `sum_of_squares` để hỗ trợ phương sai, hoặc trạng thái thuật toán hợp nhất số học ổn định. Tuy nhiên, phương sai không nên được suy từ cách cộng các **variance** đã tính riêng; khi hợp nhất cần số lượng, trung bình và thông tin biến thiên phù hợp để kiểm soát sai số số học.

### 5.2. Ví dụ: AVG của AVG cho kết quả sai

Một sensor gửi bốn mẫu:

| observed_at (UTC) | Nhiệt độ (°C) | Bucket 5 phút |
| --- | ---: | --- |
| 08:00 | 18 | 08:00 |
| 08:01 | 20 | 08:00 |
| 08:04 | 22 | 08:00 |
| 08:06 | 30 | 08:05 |

Bucket 08:00 có **count = 3, sum = 60, avg = 20°C, min = 18°C, max = 22°C**. Bucket 08:05 có **count = 1, sum = 30, avg = 30°C, min = max = 30°C**.

Nếu lấy trung bình các trung bình bucket:

$$
\frac{20+30}{2}=25\,^\circ\mathrm{C}
$$

Kết quả ấy **không phải trung bình của bốn mẫu**. Kết quả đúng là:

$$
\frac{60+30}{3+1}=22{,}5\,^\circ\mathrm{C}
$$

**Phải giữ ít nhất `sum` và `count`** nếu muốn tổng hợp trung bình chính xác qua nhiều mức. Đối với số đo lưu bằng số thực, còn cần xét sai số tích lũy và chiến lược tính toán phù hợp.

### 5.3. Mẫu không đều: trung bình theo mẫu khác trung bình theo thời gian

Trong ví dụ, sensor có ba mẫu gần nhau và một mẫu cách xa. **22,5°C** là **trung bình số học của bốn mẫu**; nó **không tự đại diện cho nhiệt độ trung bình theo thời gian của cả 10 phút**.

Nếu yêu cầu là “nhiệt độ trung bình trong khoảng thời gian” khi mẫu không đều, phải định nghĩa cách tái dựng tín hiệu giữa các điểm:

- **Giữ giá trị đến mẫu kế tiếp** (*step/last observation carried forward*), có giới hạn khoảng trống hợp lệ.
- **Nội suy tuyến tính** giữa các điểm nếu đại lượng và nghiệp vụ cho phép.
- Dùng số đo đã tích phân theo thời gian do thiết bị cung cấp.
- Đánh dấu khoảng thiếu thay vì đoán giá trị ở thời gian không quan sát được.

Khi đó trung bình theo thời gian có thể được tính bằng **tổng tích phân giá trị × thời lượng / tổng thời lượng hợp lệ**, không bằng `sum(sample_values)/count(samples)`. Cần lưu các trạng thái khác, xử lý ranh giới bucket và chính sách thiếu mẫu. **Không gọi average theo mẫu là time-weighted average nếu chưa thiết kế phép tính trọng số.**

### 5.4. Gauge, counter và event count là ba đại lượng khác

| Loại dữ liệu | Ví dụ | Cách tổng hợp cần xem xét |
| --- | --- | --- |
| **Gauge** | Nhiệt độ, mức nước, CPU usage tức thời | AVG/MIN/MAX theo mẫu; có thể cần time-weighted AVG |
| **Counter tích lũy** | Tổng byte mạng từ lúc máy khởi động, công tơ điện | Tính **delta/rate** giữa các mẫu và xử lý reset/wrap |
| **Event count** | Mỗi đơn thành công là một event | COUNT theo thời gian, chống gửi trùng |
| **Giá trị trạng thái cuối kỳ** | Số dư cuối ngày, tồn kho cuối giờ | Chọn **last valid** với thứ tự rõ; không SUM qua thời gian |
| **Đại lượng dòng trong kỳ** | kWh tiêu thụ trong một khoảng hoặc số tiền capture của event | SUM nếu các khoảng/đơn vị không chồng nhau |

**Không SUM trực tiếp giá trị counter tích lũy.** Nếu bộ đếm đã chạy từ 100 lên 110 rồi reset về 3, việc lấy `MAX - MIN` hay `last - first` trên toàn giờ có thể sai. Cần biết reset, wrap, nhịp lấy mẫu và phân biệt sự kiện reset với dữ liệu lỗi. Nếu không có đủ bằng chứng, đánh dấu chất lượng và tránh công bố rate giả chính xác.

**Không lấy SUM của các trạng thái tồn kho cuối giờ** làm tồn cuối ngày. Trạng thái cuối ngày là một quan sát tại thời điểm kết thúc, còn lượng giao dịch nhập/xuất trong ngày có thể là số đo cộng được.

### 5.5. Percentile và distinct count không thể hợp nhất bằng phép cộng đơn giản

Nếu mỗi bucket 5 phút chỉ lưu **p95**, không thể lấy trung bình các p95 để ra p95 của một giờ. Tương tự, cộng các **COUNT(DISTINCT user_id)** theo phút có thể đếm cùng người nhiều lần trong giờ.

Lựa chọn đúng có thể gồm:

- Tính lại từ **raw** khi còn dữ liệu và khối lượng phù hợp.
- Lưu **trạng thái thống kê hợp nhất được** như histogram có quy tắc rõ hoặc sketch thích hợp (ví dụ cấu trúc ước lượng quantile/distinct), công bố độ sai số và cách merge.
- Chấp nhận chỉ số của từng bucket mà **không** đưa ra p95 của toàn giờ nếu thiếu dữ liệu cần thiết.

Một bảng tổng hợp chỉ lưu `avg`, `p95` và `distinct_count` thường **không đủ để tổng hợp chính xác lên cấp tiếp theo**.

## 6. Lược đồ PostgreSQL: raw là nguồn chuẩn, rollup là dữ liệu dẫn xuất

Ví dụ dùng nhiệt độ tính bằng **°C**, một mẫu có ID do nguồn cấp, timestamp tuyệt đối và giá trị đã xác thực. Đây là schema **minh họa**, chưa bao gồm tất cả trường hiệu chuẩn, chữ ký thiết bị, phân quyền đa tenant hoặc chính sách dữ liệu nhạy cảm.

### 6.1. Bảng sensor và mẫu thô

~~~sql
CREATE TABLE sensors (
    sensor_id TEXT PRIMARY KEY,
    unit_code TEXT NOT NULL CHECK (unit_code = 'C'),
    installed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE raw_temperature (
    raw_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
    source_sample_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    temperature_c NUMERIC(9, 3) NOT NULL,
    quality_status TEXT NOT NULL
        CHECK (quality_status IN ('VALID', 'REJECTED')),
    CONSTRAINT uq_raw_source_sample
        UNIQUE (sensor_id, source_sample_id)
);

CREATE INDEX ix_raw_sensor_observed_at
    ON raw_temperature (sensor_id, observed_at);
~~~

**Khóa và grain:**

- `raw_id` là surrogate key kỹ thuật.
- `UNIQUE(sensor_id, source_sample_id)` bảo vệ grain một mẫu của một sensor; `observed_at` **không** được dùng đơn lẻ làm unique.
- `observed_at` phục vụ bucket theo **event time**; `received_at` giúp đo độ trễ và phát hiện backfill.
- `quality_status` xác định mẫu có đủ điều kiện vào rollup hay không; cả mẫu bị từ chối cũng có thể được giữ ở raw trong phạm vi retention để điều tra.
- Index theo **(sensor_id, observed_at)** phù hợp truy vấn một sensor theo khoảng thời gian; truy vấn toàn bộ sensor theo thời gian có thể cần index hoặc tổ chức vật lý khác.

Nếu nguồn **không cấp ID ổn định cho mẫu**, cần thiết kế định danh dựa trên sequence, khóa tự nhiên hoặc fingerprint có cân nhắc va chạm và gửi trùng. Chỉ chèn `UUID` mới cho mỗi lần server nhận không tự nhận biết một mẫu gửi lại.

**Thiết kế bảng thường cho hàng triệu mẫu/ngày cần xét partition, retention và khả năng nạp.** Ví dụ này cố tình dùng bảng thường để ràng buộc unique đơn giản, tránh ngầm hứa unique toàn cục trên một bảng partitioned có quy tắc khóa khác.

### 6.2. Nạp mẫu an toàn khi thiết bị gửi lại

~~~sql
INSERT INTO raw_temperature (
    sensor_id,
    source_sample_id,
    observed_at,
    temperature_c,
    quality_status
)
VALUES (
    $1, $2, $3::TIMESTAMPTZ, $4::NUMERIC, $5
)
ON CONFLICT (sensor_id, source_sample_id) DO NOTHING;
~~~

`DO NOTHING` **chỉ an toàn khi retry mang cùng nội dung**. Nếu cùng `source_sample_id` nhưng khác `observed_at` hoặc `temperature_c`, đây là **xung đột cần điều tra**, không nên âm thầm bỏ qua như retry bình thường. Một hệ thống thật có thể đọc bản cũ, so fingerprint/payload và lưu sự kiện sửa có dấu vết.

Mô hình **append-only** thường hữu ích để giữ dữ liệu đã nhận và phục vụ truy vết. Nếu nguồn thực sự chỉnh lại một phép đo đã công bố, có thể lưu phiên bản/correction riêng; việc UPDATE trực tiếp raw cần chính sách audit và **vô hiệu hóa rollup bị ảnh hưởng**. “Raw” không có nghĩa không bao giờ có yêu cầu sửa/xóa theo pháp luật hay chính sách lưu trữ.

## 7. Thiết kế rollup 5 phút với trạng thái có thể hợp nhất

~~~sql
CREATE TABLE temperature_5m (
    sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
    bucket_start TIMESTAMPTZ NOT NULL,
    sample_count BIGINT NOT NULL CHECK (sample_count > 0),
    temperature_sum NUMERIC(25, 3) NOT NULL,
    temperature_min NUMERIC(9, 3) NOT NULL,
    temperature_max NUMERIC(9, 3) NOT NULL,
    recalculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sensor_id, bucket_start),
    CHECK (temperature_min <= temperature_max)
);

CREATE TABLE temperature_hourly (
    sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
    bucket_start TIMESTAMPTZ NOT NULL,
    sample_count BIGINT NOT NULL CHECK (sample_count > 0),
    temperature_sum NUMERIC(27, 3) NOT NULL,
    temperature_min NUMERIC(9, 3) NOT NULL,
    temperature_max NUMERIC(9, 3) NOT NULL,
    recalculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sensor_id, bucket_start),
    CHECK (temperature_min <= temperature_max)
);
~~~

Grain của `temperature_5m`: **một hàng/sensor/bucket 5 phút có ít nhất một mẫu hợp lệ**. Nếu không có mẫu hợp lệ, bảng này **không có hàng** cho bucket đó; không tạo hàng với `sample_count = 0` rồi gán `temperature_min = 0` vì 0°C là giá trị nhiệt độ hợp lệ nhưng **không phải bằng chứng đã đo được**.

Để biết một bucket vắng hàng là “thiết bị không có mẫu” hay “pipeline chưa xử lý”, cần thêm metadata **trạng thái hoàn thành kỳ** ở job/checkpoint hoặc một bảng coverage riêng theo thiết kế vận hành. Bảng rollup chứa số liệu **không tự cung cấp độ đầy đủ của pipeline**.

### 7.1. Tính rollup trong một khoảng đã căn biên

Ví dụ cập nhật lại toàn bộ cửa sổ **[08:00, 09:00) UTC**, với `$1` và `$2` là hai timestamp được ứng dụng xác thực **căn biên 5 phút** và `$1 < $2`. Transaction sau xóa các bucket cũ trong khoảng và chèn lại từ raw:

~~~sql
BEGIN;

DELETE FROM temperature_5m
WHERE bucket_start >= $1::TIMESTAMPTZ
  AND bucket_start <  $2::TIMESTAMPTZ;

INSERT INTO temperature_5m (
    sensor_id,
    bucket_start,
    sample_count,
    temperature_sum,
    temperature_min,
    temperature_max
)
SELECT
    r.sensor_id,
    date_bin(
        INTERVAL '5 minutes',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS bucket_start,
    COUNT(*)::BIGINT AS sample_count,
    SUM(r.temperature_c) AS temperature_sum,
    MIN(r.temperature_c) AS temperature_min,
    MAX(r.temperature_c) AS temperature_max
FROM raw_temperature AS r
WHERE r.quality_status = 'VALID'
  AND r.observed_at >= $1::TIMESTAMPTZ
  AND r.observed_at <  $2::TIMESTAMPTZ
GROUP BY
    r.sensor_id,
    date_bin(
        INTERVAL '5 minutes',
        r.observed_at,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    );

COMMIT;
~~~

**Vì sao dùng DELETE rồi INSERT thay vì chỉ cộng thêm?**

- Một job bị retry có thể chạy lại cùng khoảng mà **không cộng gấp đôi**.
- Mẫu cũ bị đánh dấu `REJECTED` hoặc nguồn sửa dữ liệu có thể làm số mẫu giảm; tính lại bao phủ cả trường hợp bucket không còn mẫu.
- Nếu dùng `INSERT ... ON CONFLICT DO UPDATE` để thay số liệu, phải xử lý thêm **các bucket trước đây có hàng nhưng nay không còn mẫu**.
- Dùng transaction giúp các thay đổi của lần refresh được commit cùng nhau trong một PostgreSQL; người đọc ở snapshot phù hợp không thấy khoảng trống trung gian do riêng transaction này chưa commit.

**Giới hạn quan trọng:** ví dụ cần **bộ điều phối đảm bảo không có hai job làm mới chồng cửa sổ một cách mất kiểm soát** và phải xét mẫu raw được ghi đồng thời. Transaction trên bảng rollup **không tự đóng băng bảng raw** trong suốt thời gian nạp. Khi đọc raw ở `READ COMMITTED`, câu INSERT thấy một snapshot của raw tại lúc câu lệnh bắt đầu; mẫu commit muộn hơn có thể cần một lần refresh sau. Độ đầy đủ được quyết định bởi watermark/lookback và giao thức job, không chỉ cú pháp SQL.

Nếu các bucket 5 phút được nạp theo từng sensor, có thể giới hạn DELETE/INSERT theo sensor để giảm lock và I/O. Khi khối lượng lớn, cách refresh toàn cửa sổ có thể gây **write amplification** và bloat; cần đo và chuyển sang incremental aggregation có khả năng bù trừ nếu thực sự cần.

### 7.2. Đọc trung bình đúng từ trạng thái rollup

~~~sql
SELECT
    sensor_id,
    bucket_start,
    temperature_min,
    temperature_max,
    temperature_sum / NULLIF(sample_count, 0)
        AS sample_mean_temperature_c,
    sample_count
FROM temperature_5m
WHERE sensor_id = $1
  AND bucket_start >= $2::TIMESTAMPTZ
  AND bucket_start <  $3::TIMESTAMPTZ
ORDER BY bucket_start;
~~~

Tên trường **sample_mean_temperature_c** nhắc rằng đây là trung bình **theo mẫu hợp lệ**, không phải thời gian. Với schema `sample_count > 0`, `NULLIF` là phòng ngừa chung và làm rõ phép chia không được thực hiện khi count bằng 0.

## 8. Tổng hợp nhiều cấp: 5 phút → 1 giờ → 1 ngày

Một giờ có **12 bucket 5 phút theo lịch UTC**, nhưng có thể chỉ có 9 bucket **chứa mẫu hợp lệ**. Việc thiếu ba hàng cần được diễn giải theo chính sách completeness, không tự kết luận nhiệt độ bằng 0 cho 15 phút ấy.

### 8.1. Gộp một giờ từ các trạng thái 5 phút

Giả sử `temperature_5m` đã được làm mới và được xác nhận đủ đến mốc cần thiết. Chạy job giờ trên khoảng **đã căn biên giờ**:

~~~sql
BEGIN;

DELETE FROM temperature_hourly
WHERE bucket_start >= $1::TIMESTAMPTZ
  AND bucket_start <  $2::TIMESTAMPTZ;

INSERT INTO temperature_hourly (
    sensor_id,
    bucket_start,
    sample_count,
    temperature_sum,
    temperature_min,
    temperature_max
)
SELECT
    sensor_id,
    date_bin(
        INTERVAL '1 hour',
        bucket_start,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    ) AS bucket_start,
    SUM(sample_count) AS sample_count,
    SUM(temperature_sum) AS temperature_sum,
    MIN(temperature_min) AS temperature_min,
    MAX(temperature_max) AS temperature_max
FROM temperature_5m
WHERE bucket_start >= $1::TIMESTAMPTZ
  AND bucket_start <  $2::TIMESTAMPTZ
GROUP BY
    sensor_id,
    date_bin(
        INTERVAL '1 hour',
        bucket_start,
        TIMESTAMPTZ '1970-01-01 00:00:00+00'
    );

COMMIT;
~~~

Với các mẫu ví dụ trong phần 5, một giờ có `sum = 90`, `count = 4`, nên `average = 22,5°C`, dù hai bucket 5 phút có trung bình lần lượt 20°C và 30°C.

**Đừng dùng `AVG(temperature_sum / sample_count)`** để tạo trung bình giờ: cách đó cho mỗi bucket cùng trọng số, thay vì mỗi mẫu. Để tạo min/max giờ, dùng **MIN các min** và **MAX các max**.

### 8.2. Tổng hợp ngày: phải chọn loại ngày

Nếu báo cáo yêu cầu **ngày UTC**, có thể dùng khoảng 24 giờ UTC từ mốc 00:00 UTC đến 00:00 ngày tiếp theo, hợp nhất các rollup giờ.

Nếu báo cáo yêu cầu **ngày tại một nhà máy**, hãy tính `business_date` theo timezone của nhà máy và nhóm những bucket hợp lệ thuộc ngày đó. Khi bucket giờ UTC cắt qua ranh giới ngày địa phương không tròn giờ (một số múi giờ lệch 30/45 phút), **không thể gán nguyên bucket giờ đó vào một ngày địa phương mà vẫn đúng tuyệt đối**. Khi ấy cần hạt đủ nhỏ, tính lại ở raw, hoặc chọn ranh giới bucket khớp timezone theo hợp đồng.

Một bảng ngày minh họa có thể có grain **(sensor_id, business_date, timezone_id)** và lưu `count, sum, min, max`, cùng trạng thái completeness. Không đưa `timezone_id` vào khóa một cách trang trí: khi sensor chuyển địa điểm/múi giờ, quy tắc gán ngày phải được xác định theo lịch sử vị trí.

### 8.3. Chuỗi nhiều tầng cần checkpoint và dependency

Nếu job 1 giờ chạy khi job 5 phút chưa áp dụng mẫu đến muộn, bảng 1 giờ vẫn có thể sai dù SQL tổng hợp đúng. Mọi cấp cần có:

- Nguồn dữ liệu và công thức đủ rõ.
- Mốc thời gian **đã hoàn thành** ở cấp thấp hơn.
- Cơ chế đánh dấu bucket bị thay đổi (*dirty bucket*), kéo theo các rollup cấp trên.
- Quy tắc chạy lại và công bố kết quả mới.
- Khả năng đo **độ trễ end-to-end từ raw commit đến API đọc rollup**.

Không chỉ dựa vào thời gian đồng hồ của cron để gọi một bucket “đã hoàn thành”. Nếu sensor gửi dữ liệu muộn, mốc cron không phải bằng chứng đã nhận đủ mẫu.

## 9. Event đến muộn, sai thứ tự và chỉnh sửa lịch sử

Giả sử lúc 08:20 hệ thống nhận một mẫu có `observed_at = 08:02`. Khi ấy:

- Mẫu thuộc **bucket 08:00–08:05**, không thuộc bucket 08:20.
- Nếu `temperature_5m` cho 08:00 đã được tính, bucket đó phải được **refresh/điều chỉnh**.
- Nếu `temperature_hourly` cho 08:00 đã được tính, nó cũng có thể cần refresh.
- Nếu dữ liệu thô của khoảng ấy đã bị xóa, không thể luôn tính lại chính xác từ raw.

### 9.1. Watermark và cửa sổ chấp nhận dữ liệu muộn

Một hợp đồng vận hành có thể quy định:

> Hệ thống chấp nhận dữ liệu đến muộn tối đa **2 giờ** sau event time để cập nhật rollup thông thường; sự kiện muộn hơn đi vào kênh điều tra/backfill có kiểm soát.

**Con số 2 giờ chỉ là ví dụ**, không phải mặc định kỹ thuật. Watermark có thể dựa trên quan sát sự kiện của từng nguồn, thời gian server và allowance đến muộn; phải định nghĩa cách tính và giả định về đồng hồ thiết bị.

Một bucket có thể có các trạng thái:

- **OPEN**: vẫn nhận dữ liệu hợp lệ, hiển thị là chưa hoàn chỉnh.
- **PROVISIONAL**: đã tính nhưng còn trong cửa sổ đến muộn.
- **FINALIZED theo chính sách**: thông thường không còn chỉnh sửa tự động; vẫn có cơ chế correction đặc biệt.

**FINALIZED không phải chứng minh toán học rằng không còn event đến muộn**. Nó chỉ nói một ngưỡng rủi ro và quy trình vận hành đã được chấp nhận. Nếu có correction hồi tố, cần restatement hoặc đánh dấu dữ liệu đã công bố bị thay đổi.

### 9.2. Quy trình dirty bucket

~~~text
Nhận mẫu raw:
  kiểm tra identity + nội dung + quality
  ghi raw thành công
            |
            v
Tìm bucket event-time cấp nhỏ bị ảnh hưởng
  ví dụ: sensor=S1, 5m bucket=08:00
            |
            v
Đánh dấu dirty bucket / enqueue refresh
            |
            v
Refresh 5m từ raw (đủ khoảng)
            |
            v
Đánh dấu + refresh bucket giờ tương ứng
            |
            v
Đánh dấu + refresh ngày nghiệp vụ nếu cần
            |
            v
Đối soát + cập nhật freshness/checkpoint
~~~

Nếu một thay đổi `temperature_c` hoặc `quality_status` làm mẫu được loại khỏi thống kê, delta có thể âm. **Chỉ cộng thêm số liệu từ event mới** sẽ không xử lý đúng trường hợp xóa/chỉnh sửa. Tính lại bucket từ raw dễ đúng hơn trong khoảng nhỏ, còn pipeline incremental cần lưu đủ trạng thái và bút toán bù.

Cần tránh **lost notification**: nếu raw commit thành công nhưng thông báo dirty bucket thất bại, rollup có thể cũ mãi. Có thể ghi outbox/queue intent **trong cùng transaction của nguồn**, dùng CDC, hoặc đối soát các khoảng đã thay đổi; một lời gọi gửi message sau commit mà không retry không bảo đảm hội tụ.

### 9.3. Chạy lại không được đếm trùng

Những lớp idempotency khác nhau:

1. **Raw:** nhận lại cùng `source_sample_id` không chèn thêm hàng.
2. **Job 5 phút:** refresh lại cùng bucket không cộng thêm một lần nữa.
3. **Job giờ/ngày:** chạy lại không nhân số liệu cấp thấp.
4. **Consumer:** nhận lại cùng yêu cầu recompute không tạo nhiều hàng cùng grain.
5. **Correction:** một sự kiện chỉnh sửa có ID/version, không áp dụng hai lần.

Đặt PRIMARY KEY `(sensor_id, bucket_start)` ở rollup bảo vệ định danh hàng, nhưng **không tự bảo đảm phép cộng đúng**. Nếu `ON CONFLICT DO UPDATE SET sum = sum + incoming_sum` được gọi lại sau retry, cùng một bucket có thể bị tăng hai lần; chỉ dùng delta khi có chứng cứ mỗi delta được áp dụng đúng một lần.

## 10. Retention nhiều tầng: quyết định mất thông tin có chủ đích

Dữ liệu thô có giá trị lớn cho điều tra, nhưng giữ mọi mẫu ở độ phân giải gốc nhiều năm có thể đắt. Một chính sách *minh họa*:

| Cấp dữ liệu | Độ phân giải | Thời gian giữ ví dụ | Nhu cầu đọc chính |
| --- | --- | --- | --- |
| Raw | Mỗi mẫu nguồn, có ID và event time | 30 ngày | Điều tra chi tiết, debug, tính lại rollup gần |
| `temperature_5m` | 5 phút | 180 ngày | Theo ca, tuần, tháng gần |
| `temperature_hourly` | 1 giờ | 2 năm | Xu hướng trung hạn, dashboard |
| `temperature_daily` | 1 ngày nghiệp vụ | 5 năm | Xu hướng nhiều năm |

**Các thời hạn là ví dụ, không phải khuyến nghị pháp lý hay cấu hình mặc định.** Phải lấy từ yêu cầu phân tích, điều tra, tuân thủ, quyền riêng tư, khả năng backfill và ngân sách lưu trữ.

### 10.1. Thứ tự an toàn khi xóa raw

Không nên xóa raw chỉ vì đến ngày hết hạn nếu rollup tương ứng chưa được tạo thành công. Một quy trình có thể yêu cầu:

1. Xác minh tất cả bucket trong khoảng cần giữ đều đã được xử lý theo chính sách, kể cả bucket không có mẫu.
2. Kiểm tra checkpoint, failed jobs, dirty bucket và reconciliation.
3. Bảo đảm cấp 5 phút/giờ/ngày phụ thuộc đã hoàn tất trước khi xóa dữ liệu nguồn cần cho chúng.
4. Chốt xử lý mẫu muộn hoặc correction còn tồn đọng.
5. Áp dụng chính sách retention, xóa hoặc lưu trữ lạnh theo quy định; ghi dấu mốc đã purge.
6. Biết rõ những thống kê **không còn khả năng tính lại chính xác** sau khi raw bị xóa.

Sau khi xóa raw, nếu bảng 5 phút chỉ lưu `count,sum,min,max`, vẫn có thể hợp nhất lên giờ/ngày với các metric ấy; **không** thể tái tạo chuỗi mẫu để tính chính xác percentile tùy ý hoặc tìm đỉnh kéo dài 2 giây. Nếu cần, phải lưu thống kê bổ sung, file raw lưu trữ lạnh hoặc thay đổi thời hạn giữ.

### 10.2. Tính toán dung lượng sơ bộ

Giả sử **1.000 sensor**, mỗi sensor gửi **một mẫu/10 giây** liên tục:

$$
1000\times6\times60\times24=8\,640\,000\ \text{mẫu/ngày}
$$

Trong 30 ngày: khoảng **259,2 triệu mẫu raw** trước khi tính dữ liệu nhập thêm, index, metadata, phiên bản hàng, nén hoặc replication.

Rollup 5 phút có tối đa:

$$
1000\times12\times24=288\,000\ \text{bucket/ngày}
$$

Rollup giờ có tối đa **24.000 bucket/ngày**. Các con số giả định mọi sensor có mẫu ở mọi bucket; nếu sensor ngừng gửi thì số hàng thực tế có thể thấp hơn. **Không lấy số byte của một giá trị nhiệt độ nhân số mẫu rồi coi là dung lượng database**: cần tính overhead hàng, khóa, WAL, index, retention và cơ chế sao lưu.

Một bảng rollup lưu mỗi bucket một hàng **không nhất thiết tiết kiệm 30 lần dung lượng vật lý** nếu metadata/index chiếm tỷ lệ lớn ở số hàng nhỏ. Cần benchmark trên cấu hình thật.

### 10.3. Quyền riêng tư và dữ liệu có thời hạn

Dữ liệu chuỗi thời gian không phải lúc nào vô hại. Vị trí thiết bị, lịch hoạt động, hành vi người dùng hoặc thông tin sản xuất có thể là dữ liệu nhạy cảm. Không sao chép mọi tag/source payload vào mọi tầng nếu báo cáo không cần. Lịch xóa/ẩn phải xét **raw, rollup, cache, backup, event log và export** trong phạm vi chính sách áp dụng.

## 11. Giảm độ phân giải cho biểu đồ: chọn điểm hiển thị có ý nghĩa

Một màn hình rộng 1.200 pixel thường không thể biểu diễn rõ **một triệu điểm** trong cùng một đường. Downsampling giúp giảm tải mạng và tránh dựng hình quá nhiều, nhưng thuật toán chọn điểm ảnh hưởng câu chuyện mà người xem nhận được.

### 11.1. Mean-only có thể che cảnh báo

Giả sử một phút có 59 mẫu nhiệt độ **20°C** và một mẫu **80°C**. Trung bình của phút là:

$$
\frac{59\times20+80}{60}=21\,^\circ\mathrm{C}
$$

Nếu dashboard chỉ vẽ **21°C**, người vận hành không thấy đỉnh 80°C có thể quan trọng cho cảnh báo. Vì vậy với dữ liệu cần phát hiện cực trị, có thể trả **average kèm min/max**, hoặc giữ những đỉnh nổi bật và đường biểu diễn band/range.

Tuy nhiên, **min/max không cho biết đỉnh kéo dài bao lâu** hay thứ tự diễn biến. Nếu quyết định an toàn cần “nhiệt độ vượt 70°C liên tục 10 giây”, một bucket chỉ có max=80 không đủ để kết luận điều kiện thời lượng. Cần raw hoặc trạng thái tổng hợp riêng như thời gian vượt ngưỡng được định nghĩa đúng.

### 11.2. Các cách giảm điểm khác nhau

| Cách | Giữ lại | Mất mát/rủi ro | Dùng khi |
| --- | --- | --- | --- |
| **Lấy mẫu mỗi N điểm** | Một số mẫu định kỳ theo vị trí | Có thể bỏ qua spike nằm giữa hai điểm | Tín hiệu có bảo đảm tần số phù hợp, ít cực trị |
| **Mean per bucket** | Xu hướng mức trung bình | Che đỉnh/ngưỡng, sai nếu trung bình của các bucket không trọng số | Phân tích xu hướng, không thay cảnh báo |
| **Min + max + mean** | Xu hướng và biên độ trong bucket | Mất thứ tự/thời lượng spike | Dashboard quan sát biên độ |
| **First + last per bucket** | Điểm đầu và cuối | Có thể bỏ cực trị nội bộ | Dữ liệu cần thể hiện bước thay đổi |
| **Chọn điểm giữ hình dạng** | Một số đỉnh/điểm chuyển hướng | Kết quả tùy thuật toán, không tự bảo toàn thống kê | Render đồ thị nhiều điểm |
| **Histogram/sketch** | Phân bố ước lượng, quantile/distinct có thể hợp nhất | Sai số/giới hạn thuật toán | Phân tích phân bố dài hạn |

**Downsampling hiển thị không nên tự biến thành nguồn chuẩn cho tính toán nghiệp vụ.** Cảnh báo an toàn, billing hoặc điều kiện pháp lý phải dùng dữ liệu và độ chính xác phù hợp, không dựa vào những điểm đã bỏ bớt chỉ để vẽ biểu đồ.

### 11.3. Không tạo đường giả qua khoảng thiếu dữ liệu

Nếu sensor ngừng gửi trong 30 phút, một đồ thị nối thẳng điểm cuối trước khoảng trống với điểm đầu sau khoảng trống có thể khiến người xem tin nhiệt độ tăng đều trong thời gian ấy.

Cần hợp đồng hiển thị:

- Bucket **không có mẫu** là **NULL/gap**, không phải 0.
- Bucket **chưa hoàn thành** có thể được hiển thị khác hoặc ghi chú trạng thái.
- Có thể nội suy/forward fill **chỉ khi nghiệp vụ cho phép**, kèm giới hạn thời gian.
- Với trạng thái cảm biến hoặc sự kiện đếm, cách fill có thể khác với gauge liên tục.

Trong mô hình dữ liệu, `sample_count` là thông tin giúp đánh giá độ bao phủ nhưng **không hoàn toàn chứng minh thiết bị hoạt động liên tục**. Nếu dự kiến sáu mẫu mỗi phút mà chỉ nhận một, average của một mẫu vẫn tính được, nhưng độ tin cậy thấp.

## 12. Chọn cấp dữ liệu cho truy vấn theo phạm vi và độ phân giải

Một API có thể chọn cấp theo khoảng thời gian và giới hạn số điểm hiển thị:

~~~text
GET /sensor/{id}/series?from=...&to=...&targetPoints=1200

Query planner:
  15 phút   -> raw (nếu còn và phù hợp tải)
  24 giờ    -> 5 phút
  90 ngày   -> 1 giờ
  3 năm     -> 1 ngày
~~~

Đây là **quy tắc ví dụ**, không phải mapping bắt buộc. Cần xét thêm **độ phân giải cần để phát hiện spike**, độ tươi của rollup, retention và độ dài bucket. Một truy vấn theo 90 ngày với mục tiêu khoảng 1.200 điểm có thể cần chọn độ phân giải khác tùy giao diện.

### 12.1. Không trộn các khoảng thời gian chồng nhau

Nếu API trả các điểm raw cho **15 phút cuối** và rollup 5 phút cho **24 giờ**, phải chia phạm vi thời gian thành **những khoảng không chồng nhau**. Không cộng rollup đã bao phủ mẫu raw rồi cộng lại raw cùng thời gian.

Ví dụ:

~~~text
[from, cutoff)   -> chỉ lấy rollup 5 phút đã chốt
[cutoff, to)     -> raw mới hơn, được tổng hợp tức thời theo cùng quy tắc
~~~

`cutoff` phải căn đúng biên bucket, và nếu truy vấn cắt ngang bucket đầu/cuối thì cần định nghĩa cách tính **partial bucket**. Một bucket tổng hợp trọn 5 phút có thể chứa các mẫu nằm ngoài phạm vi người dùng hỏi khi `from` không căn biên; không được trả nó như thể đây là thống kê chính xác riêng của đoạn hẹp.

Nếu rollup chưa bắt kịp, API có thể trả dữ liệu cũ kèm watermark hoặc fallback raw trong phạm vi phù hợp. **Đọc từ raw luôn** không phải phương án chữa lag miễn phí khi có hàng triệu request.

### 12.2. Định nghĩa mức độ hoàn chỉnh của kết quả

Một response hữu ích có thể cung cấp:

- `resolution = '5m'`, `timezone = 'UTC'`.
- `from`, `to`, `bucket_start` và ngữ nghĩa bucket nửa mở.
- `sourceWatermark`/mốc rollup đã hoàn thành.
- `isProvisional` khi bucket vẫn trong cửa sổ đến muộn.
- `sampleCount` để đánh giá mật độ mẫu.
- Thống kê `min, max, mean` với đơn vị và cách tính.

Không cần gửi tất cả metadata trong mọi API, nhưng hệ thống phải có khả năng **giải thích độ tươi và ý nghĩa** của từng điểm khi cần đối soát.

## 13. Thiết kế vật lý: partition, index, nén và chi phí cập nhật

Sau khi chốt grain và access pattern mới chọn cách tổ chức vật lý.

### 13.1. Partition theo thời gian

Dữ liệu raw lớn thường được phân vùng theo `observed_at` (ngày/tuần/tháng tùy lưu lượng và khối lượng partition) để:

- Tránh quét dữ liệu ngoài khoảng.
- Làm retention bằng thao tác trên partition phù hợp.
- Giảm chi phí bảo trì một số loại index và thao tác nạp.

Trong PostgreSQL native partitioning, **khóa UNIQUE/PRIMARY KEY của bảng partitioned thường phải bao gồm các cột partition key** theo các quy tắc hỗ trợ của hệ quản trị. Vì thế, không được đổi bảng raw ở phần 6 sang partition theo thời gian rồi mặc định `UNIQUE(sensor_id,source_sample_id)` vẫn bảo vệ toàn cục nếu partition key không nằm trong constraint. Cần thiết kế cơ chế chống trùng tương ứng, ví dụ ID nguồn gắn với ngày, một registry định danh bên ngoài partition, hoặc phương án ingestion idempotent khác đã được kiểm thử.

Chọn partition quá nhỏ tạo nhiều partition/index và chi phí planner; quá lớn làm purge và bảo trì nặng. Số partition phải dựa vào tải, phân bố sensor, retention và cơ chế vận hành.

### 13.2. Chỉ mục phải theo truy vấn

- Truy vấn “sensor S1 trong [t1,t2)” thường hợp `(sensor_id, observed_at)`.
- Truy vấn “tất cả sensor trong một khoảng” có thể cần index chiến lược khác hoặc partition pruning; phụ thuộc selectivity.
- Rollup có PRIMARY KEY `(sensor_id,bucket_start)` để đọc một sensor theo thời gian và ngăn hai hàng cùng grain.
- Bảng lớn theo thời gian có thể dùng index phù hợp tính chất append-only và clustering nếu hệ quản trị hỗ trợ; không tự động tạo nhiều B-tree không dùng.
- Truy vấn theo metadata sensor cần dimension hoặc tổ chức theo tag được kiểm soát; tránh nhân bản vô hạn tag hiếm vào mỗi raw row.

**High cardinality** (quá nhiều ID/tag kết hợp) làm tăng số chuỗi, số nhóm tổng hợp, số hàng và index. Thêm `request_id` hoặc `session_id` duy nhất vào bộ khóa bucket sẽ biến bảng “5 phút × sensor” thành gần như “một hàng × sự kiện”, làm mất lợi ích rollup.

### 13.3. Nén và storage tier không thay thế định nghĩa số đo

Nén có thể giảm byte lưu raw mà **không thay đổi độ phân giải**. Downsampling giảm số điểm và thường **mất thông tin**. Archive sang storage lạnh thay đổi chi phí/độ trễ truy cập chứ không tự làm mất mẫu.

Ba lựa chọn có thể kết hợp:

1. Raw gần đây trên hot storage.
2. Raw cũ hơn nén/lưu trữ lạnh nếu cần phục vụ kiểm toán.
3. Rollup lâu dài trên kho đọc phù hợp.

Đừng gọi “nén” và “giảm độ phân giải” là cùng một việc. Sự khác biệt quyết định khả năng tính lại khi công thức dashboard thay đổi.

## 14. Đối soát từ raw tới từng cấp rollup

Để kiểm tra, cần so **cùng sensor, cùng khoảng thời gian, cùng trạng thái chất lượng và cùng watermark**. Một query đối soát 5 phút trong PostgreSQL:

~~~sql
WITH expected AS (
    SELECT
        sensor_id,
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            TIMESTAMPTZ '1970-01-01 00:00:00+00'
        ) AS bucket_start,
        COUNT(*)::BIGINT AS sample_count,
        SUM(temperature_c) AS temperature_sum,
        MIN(temperature_c) AS temperature_min,
        MAX(temperature_c) AS temperature_max
    FROM raw_temperature
    WHERE quality_status = 'VALID'
      AND observed_at >= $1::TIMESTAMPTZ
      AND observed_at <  $2::TIMESTAMPTZ
    GROUP BY
        sensor_id,
        date_bin(
            INTERVAL '5 minutes',
            observed_at,
            TIMESTAMPTZ '1970-01-01 00:00:00+00'
        )
),
stored AS (
    SELECT *
    FROM temperature_5m
    WHERE bucket_start >= $1::TIMESTAMPTZ
      AND bucket_start <  $2::TIMESTAMPTZ
)
SELECT
    COALESCE(e.sensor_id, s.sensor_id) AS sensor_id,
    COALESCE(e.bucket_start, s.bucket_start) AS bucket_start,
    e.sample_count AS expected_count,
    s.sample_count AS stored_count,
    e.temperature_sum AS expected_sum,
    s.temperature_sum AS stored_sum,
    CASE
        WHEN e.sensor_id IS NULL THEN 'EXTRA_ROLLUP'
        WHEN s.sensor_id IS NULL THEN 'MISSING_ROLLUP'
        WHEN e.sample_count IS DISTINCT FROM s.sample_count
          OR e.temperature_sum IS DISTINCT FROM s.temperature_sum
          OR e.temperature_min IS DISTINCT FROM s.temperature_min
          OR e.temperature_max IS DISTINCT FROM s.temperature_max
            THEN 'VALUE_MISMATCH'
        ELSE 'MATCH'
    END AS sync_status
FROM expected AS e
FULL OUTER JOIN stored AS s
    ON s.sensor_id = e.sensor_id
   AND s.bucket_start = e.bucket_start;
~~~

**Giới hạn phép đối soát:**

- Raw có thể đang nhận mẫu mới; so hai snapshot khác thời điểm có thể tạo chênh lệch tạm thời. Cần **chốt checkpoint hoặc chỉ đối soát bucket đủ cũ** so với watermark.
- Khi raw đã bị purge, không thể so từ raw. Có thể so **hourly với 5m** nếu 5m còn đủ, nhưng không phát hiện được lỗi cùng tồn tại ở hai cấp.
- `COUNT/SUM/MIN/MAX` khớp không chứng minh mọi điểm raw đúng; nhiều sai lệch có thể bù trừ, hoặc chất lượng nguồn đã sai trước khi tổng hợp.
- Với tính toán float, so tuyệt đối số thực có thể không phù hợp; cần ngưỡng sai số có lý do. Ví dụ dùng NUMERIC trong SQL để minh họa.
- Khi xuất hiện mismatch, cần tìm nguyên nhân ở raw, quality, khung thời gian, job, duplicate hoặc correction, rồi **tính lại từ nguồn chuẩn còn sẵn**.

### 14.1. Đối soát nhiều cấp phải xác định các bất biến

Một hợp đồng có thể đặt bất biến:

- Tổng `sample_count` của các bucket 5 phút trong một giờ bằng `sample_count` rollup giờ **nếu** tất cả bucket cần thiết đã được xử lý và không chồng lấn.
- Tổng `temperature_sum` tương ứng khớp; min/max được hợp nhất đúng.
- `bucket_start` căn đúng biên của resolution.
- Mỗi khóa grain xuất hiện tối đa một hàng.
- Không có bucket bị đánh dấu finalized nhưng còn dirty chưa xử lý.
- Cấp thấp và cấp cao có checkpoint đủ để chứng minh chúng cùng nguồn dữ liệu tại mốc đã công bố.

Nếu giám sát chỉ có “job chạy thành công” mà không kiểm tra invariant và freshness, rollup vẫn có thể sai kéo dài.

## 15. Ra quyết định bằng workload, độ chính xác và chi phí

Giả sử dashboard hiển thị 90 ngày cho một sensor, yêu cầu:

- p95 API không quá **300 ms**.
- Hiển thị khoảng **1.000–2.000 điểm** với **min/max** để không che cực trị.
- Chỉ số giờ được phép chậm tối đa **10 phút** sau khi dữ liệu được nhận đủ theo chính sách.
- Điều tra mẫu thô trong **30 ngày**.
- Tổng hợp lại được khi event đến muộn trong cửa sổ đã công bố.

Các số liệu sau **hoàn toàn giả định để học cách đánh giá**, không phải benchmark thực:

| Cách đọc 90 ngày | Điểm trả cho 1 sensor | p95 minh họa | Đánh đổi |
| --- | ---: | ---: | --- |
| Raw trực tiếp, mẫu/10 giây | Khoảng 777.600 | 2.200 ms | Giữ mọi điểm trong kỳ nhưng quá tải và vượt retention raw |
| Rollup 5 phút | 25.920 | 540 ms | Có min/max, nhiều điểm hơn UI cần |
| Rollup 1 giờ | 2.160 | 170 ms | Đạt API SLO, vẫn thấy cực trị trong từng giờ |
| Rollup 1 ngày | 90 | 95 ms | Quá thô cho phân tích biến động trong ngày |

**Quyết định có điều kiện:** rollup giờ có thể phù hợp cho biểu đồ 90 ngày nếu yêu cầu xem biến động từng giờ và min/max theo giờ. Nhưng cần kiểm tra **freshness**, sự kiện muộn, độ phủ sensor và tính đúng của thống kê. Nếu nghiệp vụ cần phát hiện spike 5 giây, riêng rollup giờ không thể trả lời đầy đủ; phải có đường raw/cảnh báo riêng.

Không nên chọn chỉ dựa trên p95: bảng giờ có thể giảm chi phí đọc nhưng tăng chi phí ghi, index, queue, lưu trữ, reprocessing và vận hành. Một hệ thống cần đo:

| Chiều đo | Ví dụ |
| --- | --- |
| **Ghi raw** | Mẫu/giây, ghi trùng, lỗi validation, p95/p99 ingest |
| **Rollup** | Số bucket/s, thời gian job, CPU/I/O, write amplification |
| **Độ tươi** | Source commit → 5m → hourly → API, oldest dirty bucket |
| **Dữ liệu đến muộn** | Tỷ lệ, phân phối thời gian trễ, số bucket restatement |
| **Tính đúng** | Missing/extra/mismatch rollup, sample_count và coverage |
| **Lưu trữ** | Raw/5m/hourly/daily, index, backup, nén, retention |
| **Truy vấn** | p95/p99 theo khoảng 15 phút, 24 giờ, 90 ngày, 3 năm |
| **Phục hồi** | Thời gian rebuild một ngày/tuần, khả năng backfill sau purge |

## 16. Chọn mô hình dữ liệu theo loại truy cập

### 16.1. Quan hệ và time-series extension

Một PostgreSQL có thể lưu raw, rollup và dimension sensor trong các bảng với khóa, chỉ mục và giao dịch rõ. Ưu điểm là dễ diễn đạt ràng buộc và đối soát SQL, kết hợp metadata với dữ liệu sự kiện.

Ở tải lớn, hệ time-series chuyên biệt hoặc extension có thể cung cấp quản lý partition/chunk, nén, retention và continuous aggregates. Nhưng **khả năng cụ thể phụ thuộc sản phẩm và phiên bản**; cần xác minh cách xử lý late data, refresh, unique key và timezone thay vì giả định mọi engine giống nhau.

### 16.2. Document

Mô hình document có thể phù hợp khi mỗi mẫu là một event document hoặc khi lưu một **khối mẫu giới hạn theo sensor × khoảng thời gian**. Một document chứa mảng không giới hạn có thể tăng quá lớn và gây tranh chấp; không nên nhúng toàn bộ lịch sử nhiều năm vào một document sensor.

Trong document store, nếu đã gom nhiều mẫu vào một document, vẫn phải xác định **grain logic của từng mẫu**, khóa chống trùng và cách cập nhật đúng bucket khi có event đến muộn. Nhúng không thay thế các quy tắc thống kê.

### 16.3. Graph

Graph hữu ích cho **quan hệ giữa sensor, thiết bị, vị trí, nhà máy, dây chuyền** hoặc phân tích phụ thuộc lỗi. Nhưng lưu hàng tỷ mẫu như các cạnh đơn lẻ không mặc nhiên phù hợp hơn kho chuỗi thời gian.

Một kiến trúc có thể giữ mẫu ở time-series store và giữ đồ thị quan hệ thiết bị ở graph; truy vấn dùng sensor_id để liên kết. Nếu vị trí/sở hữu thiết bị thay đổi, chiều thời gian của quan hệ cũng phải rõ khi phân tích dữ liệu lịch sử.

### 16.4. Hệ phân tích/columnar

Kho phân tích có thể dùng một fact ở grain **một mẫu** hoặc một fact ở grain **sensor × bucket**, kết hợp dimension sensor và dimension thời gian. Từ fact chi tiết có thể tạo rollup phục vụ dashboard và báo cáo dài hạn.

Cần phân biệt **số đo trạng thái** (gauge/số dư) với **dòng sự kiện cộng được**. Một bảng fact theo giờ có `count,sum,min,max` dùng để rollup tiếp, còn một bảng chỉ có `avg` có thể không đủ. Hình thức lưu cột hay file Parquet không tự sửa phép hợp nhất sai.

## 17. Checklist trước khi triển khai

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Một mẫu raw chính xác là gì? | `sensor_id + source_sample_id`, thời điểm và đơn vị |
| Khi thiết bị gửi trùng thì sao? | Khóa idempotency và quy tắc payload xung đột |
| Số đo thuộc loại nào? | Gauge, cumulative counter, event count, trạng thái cuối kỳ |
| Bucket có ranh giới gì? | [start,end), origin, timezone, fixed hay calendar |
| Mẫu hợp lệ nghĩa là gì? | Quy tắc quality và khả năng sửa/đối soát |
| Có thể hợp nhất metric nào? | Count/sum/min/max, state đặc thù, không lấy AVG của AVG |
| Khi không có mẫu thì sao? | Missing/gap, không tự đổi thành 0 |
| Độ trễ nào được chấp nhận? | Watermark, late event window, provisional/finalized |
| Job tính lại như thế nào? | Chống trùng, dirty bucket, dependency nhiều tầng |
| Retention dựa trên điều gì? | Điều tra, báo cáo, luật/chính sách, khả năng backfill |
| Khi raw đã purge có mất gì? | Percentile chính xác, mẫu riêng lẻ, tín hiệu ngắn |
| API chọn resolution thế nào? | Khoảng truy vấn, pixel, min/max, partial bucket |
| Đối soát được không? | Cùng mốc dữ liệu, count/sum/min/max và coverage |
| Chi phí vật lý? | Partition/index/nén, cardinality, query và write SLO |
| Ai sở hữu nguồn và rollup? | Trách nhiệm sửa raw, pipeline, dashboard và cảnh báo |

## 18. Bài tập vận dụng

### Bài 1 — Trung bình của hai bucket

Bucket A có **3 mẫu** nhiệt độ 18, 20, 22°C. Bucket B có **1 mẫu** 30°C.

**Câu hỏi:** Giá trị `avg` toàn khoảng là bao nhiêu? Tại sao `AVG(avg_A,avg_B)` sai?

### Bài 2 — Mẫu ở ranh giới bucket

Hệ thống dùng bucket 5 phút UTC, một mẫu có `observed_at = 08:05:00`.

**Câu hỏi:** Mẫu thuộc bucket bắt đầu 08:00 hay 08:05? Nếu dùng `BETWEEN 08:00 AND 08:05` rồi `BETWEEN 08:05 AND 08:10`, có vấn đề gì?

### Bài 3 — Counter mạng bị reset

Một bộ đếm số byte đã truyền tăng dần rồi bị reset khi thiết bị khởi động lại. Nhóm dùng `SUM(counter_value)` theo giờ để báo tổng byte truyền.

**Câu hỏi:** Vì sao sai? Cần thông tin và công thức gì?

### Bài 4 — Cảnh báo bị mất khi chỉ giữ trung bình

Một sensor có 59 mẫu 20°C và một mẫu 80°C trong một phút. Dashboard lưu duy nhất `avg` phút.

**Câu hỏi:** Người dùng thấy gì? Làm sao giữ khả năng nhìn spike? Có thể suy được spike kéo dài bao lâu từ min/max không?

### Bài 5 — Event đến muộn sau khi tính cả ba cấp

Job đã tính 5 phút, giờ và ngày cho một sensor. Sau đó có một mẫu hợp lệ với event time thuộc bucket 5 phút của hôm trước.

**Câu hỏi:** Phải xử lý những bảng và checkpoint nào? Nếu raw hôm trước đã bị xóa thì có thể làm gì và không thể khôi phục được điều gì?

### Bài 6 — Một bucket không có hàng

Bảng `temperature_5m` không có hàng sensor S1 lúc 09:10. Frontend hiển thị 0°C, trong khi dữ liệu đo quanh đó đều khoảng 25°C.

**Câu hỏi:** Hiển thị 0°C có hợp lý không? Phân biệt những nguyên nhân nào có thể gây thiếu hàng?

### Bài 7 — Chọn cấp dữ liệu theo mục tiêu

Dashboard muốn xem nhiệt độ 90 ngày với khoảng 1.500–2.500 điểm, đã có rollup 5 phút, giờ và ngày. Cần giữ cực trị nhưng không cần từng mẫu trong toàn kỳ.

**Câu hỏi:** Cấp nào là ứng viên? Cần lưu/trả những số đo nào và phải kiểm tra gì trước khi dùng?

### Bài 8 — Trung bình theo mẫu và theo thời gian

Một sensor đo nhiều lần liên tiếp trong 5 giây, sau đó im lặng 20 phút rồi gửi một mẫu khác. Nhóm dùng `SUM(value)/COUNT(*)` và gọi đó là nhiệt độ trung bình theo thời gian.

**Câu hỏi:** Sai ở ý nghĩa nào? Phải bổ sung hợp đồng và dữ liệu gì nếu thật sự cần trung bình theo thời gian?

### Bài 9 — Retention và tính lại percentile

Raw giữ 30 ngày, rollup 5 phút chỉ lưu `count,sum,min,max` và giữ 1 năm. Sau 6 tháng nhóm muốn p99 chính xác của từng giờ từ các mẫu gốc.

**Câu hỏi:** Có thể suy p99 chính xác từ các trường rollup ấy không? Những lựa chọn nào giúp hỗ trợ yêu cầu mới?

### Gợi ý lời giải

1. Bucket A có `sum=60,count=3`; bucket B có `sum=30,count=1`. Trung bình theo **bốn mẫu** là **(60+30)/(3+1)=22,5°C**. Trung bình hai AVG cho **25°C** vì mỗi bucket được trọng số như nhau dù số mẫu khác nhau.
2. Thuộc bucket **[08:05,08:10)**. Hai khoảng dùng `BETWEEN` có cận đóng sẽ cùng tính mẫu 08:05, gây đếm trùng. Dùng **[start,end)**.
3. Counter tích lũy không phải số byte riêng của từng mẫu. Cần **delta giữa các mẫu theo đúng thứ tự**, metadata hoặc quy tắc phát hiện **reset/wrap** và xử lý khoảng thiếu; không SUM giá trị tuyệt đối.
4. Average là **21°C**, che đỉnh 80°C. Lưu **min/max** hoặc giữ điểm cực trị và dữ liệu cảnh báo riêng. Từ min/max **không suy được thời lượng spike**; cần raw hoặc state thời gian vượt ngưỡng.
5. Refresh bucket **5 phút**, sau đó **giờ**, **ngày**, cập nhật dirty flags/checkpoint/freshness và đối soát. Nếu raw đã purge, có thể xử lý **delta có chứng cứ** nếu hợp đồng và trạng thái đủ; không thể tự tái lập mọi mẫu gốc/percentile chính xác từ count/sum/min/max.
6. Không: **vắng mẫu ≠ 0°C**. Cần thể hiện gap/NULL và kiểm tra sensor ngừng gửi, mẫu REJECTED, truyền chậm, job chưa xử lý, partition/retention hoặc lỗi ingest.
7. **Rollup giờ** cho khoảng 90 ngày thường có khoảng **2.160 điểm**, hợp mục tiêu. Trả `mean` tính từ sum/count, **min/max**, count và metadata độ tươi. Kiểm tra late events, độ phủ, SLO API và mức mất chi tiết có chấp nhận không.
8. **SUM/COUNT** là trung bình **theo số mẫu**, ưu tiên bất hợp lý đoạn lấy mẫu dày. Cần định nghĩa phép nội suy/giữ giá trị giữa mẫu, **giới hạn gap**, tích phân giá trị theo thời lượng và cách xử lý ranh giới khoảng.
9. **Không**, p99 không thể khôi phục chính xác từ count/sum/min/max. Cần còn raw/archive, lưu **phân bố đủ thông tin** hoặc sketch/histogram hợp nhất được với sai số được chấp nhận, hoặc thay đổi retention/định nghĩa báo cáo.

## 19. Ghi nhớ

**Dữ liệu thô giữ từng quan sát; rollup giữ trạng thái thống kê theo bucket; downsampling giảm độ phân giải để phục vụ truy vấn và biểu đồ.** Ba cách lưu này có **grain, thời gian, mức đầy đủ và rủi ro mất thông tin khác nhau**.

Muốn tổng hợp nhiều cấp đúng, hãy giữ các thành phần **có thể hợp nhất** như `count,sum,min,max` cho những đại lượng phù hợp, không lấy trung bình các trung bình một cách máy móc. Counter, số dư, percentile, distinct count và trung bình theo thời gian cần công thức hoặc trạng thái khác.

**Giảm độ phân giải là một quyết định nghiệp vụ có thể mất thông tin**, không đơn thuần là nén file. Trước khi purge raw, phải biết người dùng cần điều tra điều gì, có thể tính lại những chỉ số nào, sự kiện đến muộn được xử lý ra sao và khi dữ liệu thiếu phải hiển thị thế nào. Chỉ khi cả **độ đúng, độ tươi, khả năng phục hồi và chi phí** đều rõ ràng, mô hình chuỗi thời gian mới dễ bảo trì và tiến hóa an toàn.
