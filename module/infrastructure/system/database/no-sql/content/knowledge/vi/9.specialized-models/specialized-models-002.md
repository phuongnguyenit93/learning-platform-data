# Cardinality của nhãn, lưu giữ dữ liệu và tổng hợp theo thời gian

Trong một hệ thống giám sát, chỉ một phép đo đơn giản như “CPU đang dùng bao nhiêu phần trăm?” có thể sinh ra hàng chục nghìn chuỗi dữ liệu. CPU được đo theo máy chủ, vùng triển khai, môi trường, lõi xử lý và thời điểm; mỗi tổ hợp thuộc tính lại có lịch sử riêng. Nếu gắn thêm **userId**, **requestId** hoặc địa chỉ URL nguyên bản vào nhãn, số chuỗi có thể tăng rất nhanh và làm hệ thống hết bộ nhớ trước khi dung lượng giá trị đo trên đĩa trở thành vấn đề lớn.

Đó là lý do ba quyết định phải được thiết kế cùng nhau trong các hệ NoSQL chuyên biệt cho dữ liệu theo thời gian:

1. **Cardinality của nhãn:** có bao nhiêu chuỗi thời gian khác nhau và số chuỗi mới phát sinh nhanh đến đâu?
2. **Lưu giữ dữ liệu (retention):** mỗi độ phân giải dữ liệu được giữ trong bao lâu, ở lớp lưu trữ nào, và được xóa bằng cơ chế nào?
3. **Tổng hợp theo thời gian (aggregation, rollup, downsampling):** biến điểm đo chi tiết thành dữ liệu theo phút, giờ, ngày ra sao mà vẫn trả lời đúng câu hỏi nghiệp vụ?

Ba yếu tố gắn chặt với **mô hình truy vấn** và **chi phí hạ tầng**. Giảm thời gian giữ dữ liệu không tự giải quyết cardinality đang hoạt động; gom điểm đo theo giờ không tự giảm số nhãn; và phép lấy trung bình tưởng như vô hại có thể che mất một đợt lỗi kéo dài vài chục giây.

## 1. Ngữ cảnh: mô hình dữ liệu chuỗi thời gian

Một điểm đo thường bao gồm tên phép đo, tập nhãn, timestamp và giá trị:

~~~text
Metric:   http_requests_total
Labels:   service=checkout, env=prod, region=ap-southeast
Time:     2026-11-14T08:00:00Z
Value:    201389
~~~

Ở một số sản phẩm tên gọi có thể khác: **metric name / measurement**, **label / tag / dimension**, **sample / point**, **series**, **field**. Ý tưởng nền tảng là **một chuỗi thời gian (time series)** được định danh bằng **tên phép đo cộng với tổ hợp nhãn**, và chứa các mẫu theo thời gian.

Ví dụ với định dạng trình bày gần Prometheus:

~~~text
http_requests_total{service="checkout",env="prod",region="asia"} 201389
http_requests_total{service="catalog",env="prod",region="asia"} 812004
http_requests_total{service="checkout",env="staging",region="asia"} 1346
~~~

Đây là **ba series**, mặc dù chúng cùng dùng tên **http_requests_total**. Khi giá trị tăng từ 201389 lên 201390 ở thời điểm tiếp theo, đó là **một mẫu mới của series thứ nhất**, không phải series thứ tư.

Một ví dụ dữ liệu đo môi trường:

| Metric | Nhãn | Timestamp | Value |
| --- | --- | --- | ---: |
| temperature_celsius | device=42, room=A | 10:00:00 | 24,3 |
| temperature_celsius | device=42, room=A | 10:00:15 | 24,4 |
| temperature_celsius | device=43, room=A | 10:00:00 | 26,1 |
| temperature_celsius | device=42, room=B | 10:00:00 | 22,0 |

Theo cách định danh series ở trên, bốn hàng có **ba series**. Dữ liệu thiết bị 42, phòng A có hai mẫu. Dữ liệu thiết bị 42, phòng B là một series khác ngay cả khi nghiệp vụ cần xem đó là “cùng thiết bị đã chuyển phòng”.

Các hệ cơ sở dữ liệu chuỗi thời gian như **Prometheus, VictoriaMetrics, InfluxDB, OpenTSDB** hoặc các giải pháp có chỉ mục theo tag đều có cơ chế khác nhau. Ví dụ và ngữ nghĩa cụ thể của một sản phẩm không được mặc định áp dụng nguyên xi cho tất cả. Bài tập trung vào các quyết định kiến trúc chung.

## 2. Cardinality của nhãn là gì?

**Cardinality** của một nhãn là **số giá trị phân biệt** mà nhãn ấy có thể nhận trong phạm vi dữ liệu đang xét.

Ví dụ:

~~~text
env     = {dev, staging, prod}             → cardinality = 3
region  = {asia, eu, us}                  → cardinality = 3
service = {catalog, checkout, payment...} → cardinality = 20
userId  = {1, 2, 3, ..., 10000000}        → cardinality = 10.000.000
~~~

**Series cardinality** là số tổ hợp **tên metric + bộ giá trị nhãn** khác nhau thực sự hiện diện trong dữ liệu. Trong trường hợp mọi tổ hợp đều tồn tại, số series có thể bằng tích cardinality các nhãn:

\[
N_{\text{series,max}} \approx
N_{\text{metric}}\times \prod_{i=1}^{k}|L_i|
\]

Trong đó **|Lᵢ|** là số giá trị của nhãn thứ i. Dấu **xấp xỉ** nhấn mạnh đây là mô hình giới hạn khi mọi tổ hợp đều có thể xuất hiện; cardinality thực tế phụ thuộc những tổ hợp thật sự được ghi và tập nhãn của từng metric.

Ví dụ một metric có:

- 20 service.
- 3 environment.
- 4 region.
- 10 instance trên mỗi nhóm service/environment/region.
- 6 status hoặc nhóm kết quả được ghi thành nhãn.

Nếu tồn tại tất cả tổ hợp thì số series là:

\[
20 \times 3 \times 4 \times 10 \times 6 = 14.400\text{ series.}
\]

Thêm nhãn **customerId** với 100.000 giá trị có thể làm không gian tổ hợp lý thuyết tăng tới **1,44 tỷ series**. Trong thực tế ít khi mọi khách hàng xuất hiện trên mọi instance, nhưng ví dụ cho thấy một nhãn có phạm vi giá trị lớn **có thể** khiến số series tăng theo nhiều bậc độ lớn.

### 2.1. Cardinality của từng nhãn khác cardinality của toàn metric

Hai nhãn đều có 10 giá trị không nhất thiết sinh 100 series. Nếu nhãn **region** chỉ có 10 giá trị và mỗi **datacenter** chỉ thuộc đúng một region, số tổ hợp region–datacenter thực tế có thể chỉ là 10 hoặc 20, không phải 100.

Hãy phân biệt:

| Khái niệm | Cách hiểu | Lý do cần đo |
| --- | --- | --- |
| **Label cardinality** | Số giá trị khác nhau của một nhãn | Phát hiện nhãn mang ID hoặc dữ liệu biến động quá rộng |
| **Series cardinality** | Số tổ hợp metric + nhãn khác nhau | Gắn trực tiếp với chi phí quản lý, index và tra cứu series |
| **Active series** | Số series được xem là hoạt động trong cửa sổ đo theo định nghĩa của engine | Gần với áp lực bộ nhớ của TSDB nhận dữ liệu liên tục |
| **Historical series** | Những series từng tồn tại và còn được lưu trong retention | Ảnh hưởng index, truy vấn lịch sử và dung lượng |
| **Series churn** | Tốc độ series mới xuất hiện và series cũ ngừng gửi mẫu | Dù active series không tăng mãi, churn cao vẫn có chi phí ingest/index |

Một metric có 200.000 series active nhưng ổn định khác một metric có 200.000 series active liên tục **thay toàn bộ nhãn sau mỗi 10 phút**. Trường hợp thứ hai tạo ra nhiều định danh series lịch sử hơn và gây thêm công việc cho head/index, compaction hoặc tái cấu trúc bộ nhớ tùy engine.

### 2.2. Ví dụ nhãn tốt và nhãn nguy hiểm

| Nhãn | Mức cardinality dự kiến | Phù hợp làm nhãn metric? | Ghi chú |
| --- | --- | --- | --- |
| env=prod/staging | Thấp | Thường phù hợp | Dùng để lọc/tổng hợp theo môi trường |
| region=asia/eu/us | Thấp | Thường phù hợp | Nhãn ổn định, hữu ích cho SLO |
| service=checkout/catalog | Thấp hoặc vừa | Thường phù hợp | Phụ thuộc số dịch vụ |
| method=GET/POST/... | Thấp | Thường phù hợp | Nên chuẩn hóa giá trị |
| status_class=2xx/4xx/5xx | Thấp | Thường phù hợp | Có thể dùng mã cụ thể nếu tập giá trị hữu hạn và có nhu cầu |
| route=/orders/{id} | Vừa nếu dùng route template | Thường phù hợp | **Không dùng đường dẫn thật chứa ID** |
| pod/instance_id | Có thể cao và thay đổi thường xuyên | Chỉ dùng khi cần truy vấn ở cấp instance | Theo dõi churn trong môi trường container |
| user_id, session_id | Rất cao | Thường không phù hợp | Ghi vào log/trace hoặc hệ phân tích thích hợp |
| request_id, trace_id | Gần như một giá trị cho mỗi request | Không phù hợp làm nhãn metric tổng quát | Dùng trace/span hoặc exemplar theo khả năng engine |
| raw_url, sql_query | Có thể gần như vô hạn | Không phù hợp | Chuẩn hóa route/query class; tránh đưa dữ liệu nhạy cảm vào nhãn |

**“High cardinality” không phải một ngưỡng số cố định.** Một hệ có 500.000 series ổn định và đủ tài nguyên có thể chạy tốt; một hệ nhỏ hơn nhiều vẫn quá tải nếu churn cao, số lượng index lớn, truy vấn fan-out rộng hoặc hạ tầng hạn chế.

## 3. Vì sao cardinality cao gây tốn kém?

Một mẫu đo có thể chỉ mang một timestamp và một số. Nhưng để lưu và truy vấn được mẫu đó, hệ thống còn phải:

- Nhận diện series bằng tên metric và tập nhãn.
- Duy trì metadata/index giúp tìm các series khớp bộ lọc.
- Quản lý trạng thái series đang ghi ở vùng dữ liệu nóng (*head* hoặc cấu trúc tương đương).
- Mã hóa, nén và ghi các mẫu theo thời gian.
- Phục vụ các phép truy vấn tìm series rồi đọc mẫu.
- Quản lý tuổi thọ của series và dọn dữ liệu lịch sử.

Vì thế có **hai loại tăng trưởng cần đo riêng**:

~~~text
A. Tăng số mẫu:
   100.000 series, lấy mẫu mỗi 15 giây trong 24 giờ
   → 100.000 × 5.760 = 576.000.000 mẫu/ngày

B. Tăng số định danh series:
   Mỗi request mang một requestId mới làm label
   → Có thể tạo gần một series mới cho mỗi request
      dù mỗi series chỉ chứa 1 mẫu
~~~

Ở trường hợp A, chi phí lớn nằm ở lượng mẫu và retention. Ở trường hợp B, index/metadata và vòng đời series có thể trở thành nút nghẽn. Hai trường hợp yêu cầu các biện pháp khác nhau.

### 3.1. Cardinality là chi phí của “chiều dữ liệu”

Giả sử người dùng hỏi:

> Tỷ lệ lỗi HTTP 5xx của dịch vụ checkout trong 5 phút gần nhất ở môi trường production là bao nhiêu?

Các nhãn **service**, **env**, **status_class** có ích vì truy vấn cần nhóm/lọc theo chúng. Trong khi đó, **requestId** không giúp tính tỷ lệ lỗi tổng, nhưng lại chia dữ liệu thành hàng triệu series nhỏ.

Giá trị không có ích cho chiều truy vấn tổng hợp không nên tùy tiện trở thành nhãn. Một nguyên tắc thực dụng là:

**Chỉ đưa một thuộc tính vào nhãn khi có trường hợp truy vấn rõ ràng cần lọc/nhóm theo nó, tập giá trị và tốc độ thay đổi của nó có thể quản lý, và chi phí được chấp nhận.**

Đối với nhu cầu điều tra một request cụ thể, hãy dùng **tracing/log** hoặc một kho sự kiện có chỉ mục thích hợp. Tùy sản phẩm, một **exemplar** có thể liên kết điểm đo với trace cụ thể mà không biến trace ID thành nhãn của mọi series.

### 3.2. Churn: kẻ gây tải ngay cả khi số series hiện tại không lớn

Trong môi trường Kubernetes, nếu gắn **pod UID** hoặc tên pod tạm vào mỗi metric, mỗi lần triển khai có thể tạo hàng nghìn series mới. Series cũ ngừng nhận mẫu nhưng vẫn tồn tại trong retention hoặc trong các cấu trúc cần dọn theo cơ chế engine.

~~~text
Deploy lần 1: pod-a1, pod-b1 → nhiều series
Deploy lần 2: pod-a2, pod-b2 → series khác
Deploy lần 3: pod-a3, pod-b3 → series mới nữa
~~~

Trong kịch bản quan sát ở cấp service, có thể **gộp theo service, route và status** thay vì giữ mọi danh tính pod trong báo cáo dài hạn. Tuy nhiên, giám sát sự cố cấp pod vẫn cần dữ liệu chi tiết trong một khoảng ngắn. Có thể duy trì hai lớp: dữ liệu raw ở độ phân giải cao để điều tra ngắn hạn và dữ liệu tổng hợp theo service cho xu hướng dài hạn.

Không nên giải quyết churn bằng cách xóa hết nhãn instance khi nghiệp vụ còn cần phát hiện một node bất thường; phải cân nhắc khả năng truy vấn cần giữ.

## 4. Thiết kế nhãn trước khi gửi dữ liệu

Việc thu thập một metric nên bắt đầu bằng **đường truy vấn dự kiến**:

~~~text
Câu hỏi: API checkout của production có lỗi tăng không?
Nhóm theo: service, env, route, status_class
Khoảng thời gian: 5 phút, 1 giờ, 30 ngày
Độ phân giải cần: 15 giây ngắn hạn; 5 phút dài hạn
Không cần: request_id, user_id, session_id ở nhãn metric
~~~

Một ví dụ instrumentation không tốt:

~~~text
http_request_duration_seconds{
  service="checkout",
  path="/orders/482719/payment",
  user_id="user-900287",
  trace_id="a93ef..."
} 0.142
~~~

Mỗi order/user/trace mới có thể tạo series mới. Cách tốt hơn cho metric tổng hợp:

~~~text
http_request_duration_seconds{
  service="checkout",
  route="/orders/{orderId}/payment",
  method="POST",
  status_class="2xx"
} 0.142
~~~

Ví dụ trên minh họa cách **giảm tập giá trị của nhãn**. Trong thực tế, metric độ trễ thường dùng histogram hoặc summary chuyên dụng, thay vì một gauge duy nhất chứa độ trễ request gần nhất.

### 4.1. Label không nên thay cho trường dữ liệu giá trị cao

Nếu cần lưu nhiệt độ cho 2 triệu thiết bị:

~~~text
temperature_celsius{device_id="D-001"} 24.3
temperature_celsius{device_id="D-002"} 25.1
...
~~~

Về mặt mô hình, **device_id** có thể là dimension cần thiết để xem lịch sử từng thiết bị. Nhưng trước khi chọn một TSDB dạng metric-label cho toàn bộ dữ liệu, phải tính:

- 2 triệu thiết bị × nhiều loại sensor × nhãn khác sẽ sinh bao nhiêu series?
- Bao nhiêu thiết bị hoạt động đồng thời?
- Có cần tìm một thiết bị cụ thể thường xuyên, hay chỉ tổng hợp theo khu vực?
- Hệ thống có thể phân vùng theo device/time và dùng một **time-series event store** thay vì gắn mọi thiết bị vào label index của một hệ metric theo kiểu Prometheus không?

**Không có quy tắc “deviceId luôn bị cấm”**. Giá trị nhãn có hợp lý hay không phụ thuộc sản phẩm, quy mô, kiểu truy vấn và chi phí hạ tầng. Điều cần tránh là thêm một dimension cardinality cao mà không ước tính được chi phí.

### 4.2. Các kỹ thuật giảm cardinality

| Kỹ thuật | Ví dụ | Đánh đổi |
| --- | --- | --- |
| Chuẩn hóa nhãn | path thực → route template | Mất khả năng truy vấn metric theo từng path cụ thể; bù bằng trace/log |
| Bỏ nhãn không dùng | Không gắn requestId | Giảm cardinality nhưng mất chiều lọc ấy trong metric |
| Giảm độ hạt giá trị | status_code → status_class | Mất chi tiết 404 so với 429 nếu chỉ giữ lớp |
| Giới hạn tập nhãn được phép | Env/service/region từ danh sách đã kiểm soát | Phải xử lý giá trị lạ và cập nhật danh sách |
| Tách raw và aggregate | Giữ instance ngắn hạn, service-level lâu dài | Thêm pipeline, yêu cầu đối soát và đo độ trễ |
| Chặn metric/label tại ingest | Drop metric không dùng hoặc label động | Mất dữ liệu sau điểm lọc; cần biết tác động tới dashboard/alert |
| Lựa chọn hệ lưu trữ khác | Event log cho requestId, TSDB cho metric | Tăng thành phần hệ thống nhưng đúng mô hình truy vấn hơn |

Chỉ đổi tên label **không làm giảm cardinality** nếu giá trị của nhãn vẫn có hàng triệu biến thể. Tương tự, đặt userId dưới tên **tag** thay vì **label** cũng không loại bỏ vấn đề nếu engine lập chỉ mục theo tag.

## 5. Ước lượng lượng mẫu, dung lượng và chi phí

Với **S series active**, lấy mẫu theo chu kỳ **Δ giây**, lượng mẫu một ngày (nếu mọi series đều gửi đều và không mất mẫu) là:

\[
N_{\text{samples/day}}=S \times \frac{86.400}{\Delta}
\]

Ví dụ:

~~~text
S = 100.000 series active
Δ = 15 giây

Số mẫu/series/ngày = 86.400 / 15 = 5.760
Tổng số mẫu/ngày    = 100.000 × 5.760 = 576.000.000
~~~

Nếu giả định **16 byte/mẫu thô** để làm một phép ước lượng minh họa, dữ liệu mẫu có kích thước:

\[
576.000.000 \times 16
= 9.216.000.000\ \text{byte/ngày}
\]

Tức khoảng **9,216 GB theo hệ thập phân**, chưa tính index, metadata, compression, replication, WAL, block overhead và các lớp dữ liệu khác. Nhiều TSDB có cơ chế nén timestamp/giá trị làm số byte/mẫu thực tế khác xa giả định này. **Không dùng 16 byte/mẫu làm định mức cố định cho mọi sản phẩm.**

Với retention 30 ngày và nếu tốc độ luôn như trên, chỉ riêng mẫu thô theo giả định đã là khoảng **276,48 GB**. Đây chưa phải dung lượng đĩa cuối cùng, và cũng **chưa nói gì về chi phí giữ hàng triệu series lịch sử có ít mẫu**.

### 5.1. Đừng nhầm ba nút điều khiển

| Thay đổi | Lượng mẫu mỗi ngày | Số series | Dữ liệu lịch sử giữ lại |
| --- | --- | --- | --- |
| Tăng khoảng lấy mẫu từ 15s lên 60s | Giảm khoảng 4 lần nếu điều kiện khác giữ nguyên | Không nhất thiết giảm | Độ phân giải giảm |
| Bỏ nhãn requestId | Có thể giảm rất mạnh tổng mẫu/metadata nếu mỗi request trước đó tạo series riêng | Giảm rất mạnh | Mất khả năng lọc metric theo requestId |
| Retention từ 90 ngày xuống 30 ngày | Không tự thay đổi ingest hiện tại | Không tự thay đổi active series | Giảm lượng dữ liệu lịch sử được giữ |
| Rollup 1 phút thay dữ liệu 15 giây ở tầng dài hạn | Giảm số điểm của dữ liệu đã rollup | Giữ nguyên nếu vẫn giữ đủ nhãn | Mất chi tiết dưới một phút |
| Rollup bỏ nhãn instance | Có thể giảm | Có thể giảm series đáng kể | Mất khả năng drill down theo instance trong dữ liệu tổng hợp |

**Retention không phải thuốc chữa high-cardinality đang hoạt động.** Nếu metric tạo 500.000 series mới mỗi phút, dù giữ dữ liệu 1 ngày, chi phí tạo/index series vẫn có thể khiến ingest quá tải.

## 6. Lưu giữ dữ liệu: retention là chính sách vòng đời

**Retention policy** quy định dữ liệu được giữ ở độ phân giải và nơi lưu trữ nào, trong bao lâu. Một hệ có thể giữ mẫu đầy đủ 7 ngày để điều tra sự cố, nhưng vẫn cần xu hướng theo giờ trong 1 năm.

Ví dụ:

| Lớp dữ liệu | Độ phân giải | Thời gian giữ minh họa | Câu hỏi hỗ trợ |
| --- | --- | --- | --- |
| **Raw/hot** | 15 giây | 7 ngày | Sự cố vừa xảy ra trong vài phút ở instance nào? |
| **Rollup ngắn** | 1 phút | 30 ngày | Tải và lỗi thay đổi thế nào trong tháng? |
| **Rollup dài** | 1 giờ | 365 ngày | Xu hướng tăng trưởng và tính mùa vụ theo quý/năm? |
| **Archive sự kiện** | Dạng gốc hoặc file partition theo ngày | Theo yêu cầu nghiệp vụ | Điều tra, tái xử lý hoặc phân tích cần sự kiện chi tiết |

Đây là **một chính sách đề xuất**, không phải khả năng tự động sẵn có trong tất cả TSDB. Một số hệ có retention theo bucket/database, một số có quy tắc thời gian riêng, một số cần pipeline hoặc remote storage để tạo và giữ rollup. **Prometheus độc lập**, chẳng hạn, có cơ chế retention cho dữ liệu TSDB của chính nó nhưng **không tự động tạo nhiều lớp downsampling dài hạn theo bảng trên**. Recording rules hoặc hệ lưu trữ truy vấn dài hạn có thể được sử dụng để tạo/giữ chuỗi tổng hợp, theo kiến trúc đã chọn.

### 6.1. TTL/retention không phải xóa vật lý ngay

Nhiều engine xóa theo block, partition hoặc công việc dọn nền. Khi retention tới hạn:

- Dữ liệu có thể **không còn được truy vấn** theo hợp đồng mặc dù file/block chưa được thu hồi ngay.
- Dung lượng có thể chỉ giảm sau compaction hoặc xóa block.
- Backup, snapshot, bản sao và hệ remote-write có thể giữ dữ liệu theo **chính sách riêng**.
- Những ghi đến muộn có timestamp ngoài retention có thể bị từ chối, bỏ qua hoặc có vòng đời đặc biệt tùy engine.

Do đó, phải kiểm tra **giới hạn timestamp được chấp nhận, thời điểm dữ liệu ngừng hiển thị, thời điểm thu hồi dung lượng và chính sách backup**. Không nên dùng retention đơn thuần để chứng minh rằng dữ liệu cá nhân đã bị xóa khỏi mọi bản sao.

### 6.2. Những quyết định cần có trước khi đặt retention

1. **Nhu cầu nghiệp vụ:** dashboard cần nhìn bao xa, độ phân giải tối thiểu là gì?
2. **Nhu cầu điều tra:** khi xảy ra lỗi, người vận hành cần xem từng instance/từng giây trong bao lâu?
3. **Nhu cầu tuân thủ:** có ràng buộc giữ/xóa dữ liệu, quyền truy cập hoặc phân loại dữ liệu không?
4. **Đến muộn và sửa dữ liệu:** các mẫu gửi trễ có được chấp nhận? Nếu rollup đã tính xong thì có được tính lại?
5. **Khả năng dựng lại:** dữ liệu raw có được lưu ở nơi khác để tái xử lý sau khi hết retention ở TSDB?
6. **Chi phí:** lưu bao nhiêu byte trên một lớp, bao nhiêu replica, bao nhiêu dữ liệu được đọc khi truy vấn?

Một chính sách “giữ 30 ngày” chưa đủ: cần nói rõ **giữ gì** (raw, rollup, index, event gốc), **ở đâu**, và **khi hết hạn thì ứng dụng nhìn thấy gì**.

## 7. Downsampling và rollup là gì?

**Downsampling** biến một chuỗi điểm đo dày thành tập điểm thưa hơn. **Rollup** thường là việc tính các thống kê theo các khoảng thời gian (*time buckets*), ví dụ mỗi 1 phút hoặc mỗi 1 giờ.

Giả sử nhiệt độ có mẫu mỗi 15 giây:

~~~text
10:00:00 → 23,8°C
10:00:15 → 24,0°C
10:00:30 → 24,1°C
10:00:45 → 24,9°C
~~~

Một rollup cho phút 10:00 có thể lưu:

~~~json
{
  "bucketStart": "2026-11-14T10:00:00Z",
  "count": 4,
  "sum": 96.8,
  "avg": 24.2,
  "min": 23.8,
  "max": 24.9
}
~~~

Nếu chỉ lưu **avg=24,2**, ta mất thông tin về điểm cao nhất 24,9 và số lượng mẫu. Lưu thêm **min, max, sum, count** có thể tăng dung lượng so với một average duy nhất nhưng cho phép trả lời nhiều câu hỏi hơn và tính lại trung bình của nhiều bucket chính xác hơn.

### 7.1. Công thức trung bình đúng khi gộp nhiều bucket

Giả sử bucket A có trung bình 10 từ 2 mẫu, bucket B có trung bình 40 từ 8 mẫu.

**Trung bình của hai trung bình**:

\[
\frac{10+40}{2}=25
\]

Nhưng **trung bình thực của 10 mẫu**:

\[
\frac{10\times2+40\times8}{2+8}=34
\]

Vì thế, để rollup từ phút lên giờ, nên giữ **sum và count** (hoặc thống kê đủ để tính lại), rồi dùng:

\[
\operatorname{avg}_{combined}=
\frac{\sum_i sum_i}{\sum_i count_i}
\]

Không tính trung bình đơn giản của các average nếu số mẫu mỗi bucket khác nhau.

### 7.2. Sample-weighted khác time-weighted

Với sensor có tần suất gửi không đều, trung bình theo mẫu có thể bị lệch so với trung bình theo thời gian.

Ví dụ:

~~~text
10:00 → nhiệt độ 20°C, giữ gần 50 phút
10:50 → nhiệt độ 40°C, gửi 10 mẫu liên tiếp
~~~

Trung bình đơn giản theo 11 mẫu gần 38°C, dù nhiệt độ 20°C kéo dài phần lớn thời gian. Muốn biểu diễn **nhiệt độ trung bình trong một giờ**, có thể cần cách tính **time-weighted average**, tích phân/trọng số theo thời gian quan sát và quy tắc xử lý khoảng thiếu dữ liệu.

Việc chọn mean theo mẫu hay theo thời gian phải xuất phát từ **nghĩa của phép đo**. Không phải một engine downsampling bất kỳ sẽ tự suy ra định nghĩa nghiệp vụ đúng.

### 7.3. Gộp theo thời gian có thể che spike

Ví dụ 1 phút gồm 59 giây latency 20 ms và 1 giây latency 5.000 ms. Nếu tính trung bình theo giây, average của phút là khoảng:

\[
\frac{59\times20 + 1\times5.000}{60}
\approx 103\ \text{ms}
\]

Một đợt trễ 5 giây đã bị “làm mượt” thành 103 ms. Nếu mục tiêu là phát hiện lỗi đột biến, nên lưu hoặc truy vấn **max, phân phối độ trễ, histogram hoặc p99 được tính từ dữ liệu phù hợp**. Nếu không, rollup có thể khiến dashboard lịch sử trông ổn trong khi người dùng từng gặp sự cố lớn.

## 8. Phép tổng hợp phải phù hợp loại metric

Không có một phép **AVG theo giờ** phù hợp cho mọi dữ liệu. Trước tiên phải biết kiểu metric và cách giải thích mẫu.

| Loại dữ liệu | Ví dụ | Tổng hợp thường hữu ích | Sai lầm phổ biến |
| --- | --- | --- | --- |
| **Gauge** | CPU usage, nhiệt độ, độ dài queue | min/max/avg, sum/count, last; time-weighted khi cần | Cộng tất cả nhiệt độ để hiểu “tổng nhiệt độ” |
| **Counter tích lũy** | Tổng request, tổng lỗi, bytes đã gửi | delta/rate/increase trên khoảng thời gian, xử lý reset | Lấy AVG của giá trị counter tuyệt đối để đo request/s |
| **Histogram cổ điển** | Số request trong các bucket latency | Cộng count của từng bucket phù hợp rồi tính quantile/rate | Lấy trung bình các p95 của từng instance |
| **Tỷ lệ** | Error rate, success ratio | Gộp **tử số/mẫu số** trước khi chia | Trung bình đơn giản tỷ lệ các nhóm có kích thước khác nhau |
| **Event occurrence** | Một giao dịch/thiết bị bật báo động | Count theo cửa sổ, distinct count nếu có định nghĩa | Đếm nhiều lần sự kiện trùng hoặc coi event mất là 0 |
| **Giá trị cuối** | Trạng thái hiện tại, tồn kho | Last có ngữ nghĩa thời điểm và độ mới | Sum/avg các trạng thái rời rạc |
| **Percentile tính trước** | p95 latency theo phút | Cần phân phối/histogram/sketch thích hợp để gộp | Trung bình p95 các phút thành p95 toàn giờ |

### 8.1. Counter và xử lý reset

Một counter tích lũy có thể tăng:

~~~text
10:00:00 → 100 requests
10:01:00 → 190 requests
10:02:00 →   5 requests  (tiến trình restart, counter reset)
10:03:00 →  25 requests
~~~

Phép lấy số cuối trừ số đầu cho ra **25 − 100 = −75**, rõ ràng không phải lượng request đã xử lý. Cần dùng hàm **rate/increase có nhận biết counter reset** theo khả năng của TSDB, đồng thời hiểu rằng khi reset xảy ra giữa hai lần lấy mẫu, số request chính xác phát sinh ngay trước reset có thể không quan sát được từ mẫu lưu.

Ví dụ PromQL:

~~~promql
sum by (service) (
  rate(http_requests_total{env="prod"}[5m])
)
~~~

Ở đây tính rate **theo từng series trước**, sau đó mới sum theo service. Cách này cho phép cơ chế phát hiện reset áp dụng cho mỗi counter gốc. Gộp các giá trị counter thô của nhiều instance trước rồi mới tính rate có thể làm reset của một instance bị che hoặc diễn giải sai.

Khi muốn lưu rollup dài hạn, có thể lưu số lượng request tăng thêm trên mỗi bucket và thông tin thời lượng hợp lệ, hoặc lưu rate với các trọng số cần thiết. Không nên cộng các giá trị counter tích lũy cuối phút rồi gọi kết quả là “tổng request trong giờ”.

### 8.2. Error rate phải gộp tử số và mẫu số

Giả sử:

~~~text
Service A: 1 lỗi / 10 request    → error rate 10%
Service B: 10 lỗi / 1.000 request → error rate 1%
~~~

Trung bình đơn giản hai tỷ lệ là **5,5%**. Tỷ lệ lỗi thực của toàn hệ là:

\[
\frac{1+10}{10+1000}=\frac{11}{1010}\approx 1,09\%
\]

Nếu muốn rollup và gộp theo vùng/dịch vụ, phải giữ được **error_count** và **request_count** hoặc một thống kê tương đương. Chỉ lưu **error_rate_percent** riêng lẻ khiến việc gộp đúng trở nên khó hoặc không thể.

### 8.3. Không thể gộp p95 bằng trung bình p95

Hai instance có p95 lần lượt 100 ms và 300 ms. P95 toàn hệ **không phải** 200 ms, cũng không nhất thiết bằng trung bình có trọng số của hai giá trị đó. Percentile phụ thuộc **phân phối toàn bộ mẫu**.

Nếu cần p95 trên nhiều instance hoặc khoảng thời gian, phải giữ một dạng phân phối có thể hợp nhất thích hợp như **histogram buckets** hoặc cấu trúc sketch được engine hỗ trợ và hiểu sai số. Với **Prometheus classic histogram**, mỗi **le** (*less than or equal*) là một nhãn bucket; cần bảo toàn cùng hệ ranh giới bucket và tính toán từ các count phù hợp.

Ví dụ minh họa PromQL:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_request_duration_seconds_bucket{env="prod"}[5m])
  )
)
~~~

Đây là ví dụ cho **classic histogram**. Histogram kiểu khác, sketch hoặc summary có quy tắc tổng hợp riêng; không nên áp dụng cùng công thức máy móc.

## 9. Tổ chức rollup nhiều tầng

Một kiến trúc có thể đi theo luồng:

~~~mermaid
flowchart TD
    A["Nguồn metric / sensor"] --> I["Ingest: parse, chuẩn hóa nhãn, kiểm tra timestamp"]
    I --> R[("Raw series, 15 giây\nRetention 7 ngày")]
    I --> P["Pipeline tổng hợp theo cửa sổ"]
    P --> M[("Rollup 1 phút\nRetention 30 ngày")]
    M --> H["Rollup tiếp, giữ sum/count/min/max"]
    H --> Y[("Rollup 1 giờ\nRetention 365 ngày")]
    Q["API / Dashboard"] --> R
    Q --> M
    Q --> Y
~~~

Sơ đồ cho thấy **một lựa chọn thiết kế**, không phải hệ thống nào cũng có sẵn ba tầng dữ liệu. Có thể dùng pipeline stream, batch, recording rules hoặc tính năng continuous aggregate của sản phẩm phù hợp.

Một bảng rollup tối giản:

~~~text
Key:
  metric_name
  label_set_or_selected_dimensions
  bucket_start
  resolution

Values:
  sum
  count
  min
  max
  last
  quality_flags
~~~

Đối với counter hoặc histogram, cấu trúc cần khác: lưu delta/bucket counts hoặc thành phần có thể hợp nhất. Không ép mọi loại metric vào cùng định dạng sum/count/min/max nếu ngữ nghĩa không phù hợp.

### 9.1. Truy vấn nên chọn lớp theo thời gian và độ phân giải

Một dashboard:

- Xem **2 giờ gần nhất**: có thể đọc raw 15 giây để điều tra spike.
- Xem **14 ngày**: có thể đọc rollup 1 phút để giảm số điểm và chi phí.
- Xem **1 năm**: có thể đọc rollup 1 giờ để hiển thị xu hướng.

Độ phân giải còn phải phù hợp với **số pixel và mục đích phân tích**. Một đồ thị rộng 1.000 pixel cho một năm không thể hiện có ý nghĩa mọi mẫu 15 giây; nhưng một phép điều tra lỗi 20 giây cũng không thể dựa duy nhất vào dữ liệu theo giờ.

Ứng dụng nên ghi rõ lớp nào đang được hiển thị, độ phân giải là bao nhiêu, dữ liệu đã giảm nhãn nào và có mất chi tiết gì. Tránh làm người xem tưởng một điểm tổng hợp là giá trị đo tại đúng timestamp đại diện.

### 9.2. Phép gộp nhiều tầng cần tính kết hợp

Nếu rollup 15 giây → 1 phút → 1 giờ:

- **sum:** cộng các sum cùng nghĩa.
- **count:** cộng số mẫu hoặc sự kiện hợp lệ.
- **min/max:** lấy min của min hoặc max của max.
- **average:** tính **sum toàn bộ / count toàn bộ**, không average của average.
- **ratio:** gộp hai thành phần tử số/mẫu số rồi tính lại.
- **histogram:** gộp count theo bucket tương thích rồi tính quantile.
- **last:** chọn bản có timestamp hợp lệ mới nhất, không chọn theo thứ tự đến ngẫu nhiên.

Nếu một tầng không giữ những thành phần đủ để tổng hợp đúng, lớp trên **không thể khôi phục chúng từ một giá trị average/p95 đơn lẻ**. Quyết định cần những phép query nào trước khi bỏ dữ liệu raw.

## 10. Chọn nhãn cho rollup cũng là quyết định cardinality

Giả sử raw metric có:

~~~text
cpu_usage{service="checkout", env="prod", region="asia", instance="pod-1"}
cpu_usage{service="checkout", env="prod", region="asia", instance="pod-2"}
...
~~~

Nếu rollup 1 giờ vẫn giữ nguyên **instance**, số series tổng hợp có thể gần bằng số series raw; chỉ số mẫu giảm. Nếu các báo cáo dài hạn chỉ cần **service + env + region**, ta có thể gộp qua instance để giảm cả **số series** và **số mẫu**:

~~~text
Raw:
  (service, env, region, instance) × 15 giây

Rollup:
  (service, env, region) × 1 giờ
~~~

Nhưng phép gộp phải giữ nghĩa của metric:

- **Tổng request/s** từ nhiều instance có thể cộng rate.
- **CPU phần trăm trung bình** giữa instance có thể cần trọng số theo CPU capacity; không mặc định sum các phần trăm rồi xem là tỷ lệ toàn cụm.
- **Latency p95** phải tính từ phân phối gộp, không average p95 instance.
- **Độ trễ của một pod cụ thể** sẽ không còn truy vấn được sau khi bỏ instance khỏi rollup.

Điều này cho thấy **drop label là thay đổi hợp đồng truy vấn** chứ không chỉ là tối ưu bộ nhớ.

## 11. Cửa sổ thời gian và sự kiện đến muộn

Một rollup thường gom dữ liệu theo những cửa sổ như:

~~~text
[10:00:00, 10:01:00)
[10:01:00, 10:02:00)
[10:02:00, 10:03:00)
~~~

Khoảng **[start, end)** bao gồm start và không bao gồm end để một mẫu tại đúng 10:01:00 không rơi vào hai cửa sổ kề nhau.

Các khái niệm thời gian cần tách biệt:

| Mốc | Ý nghĩa |
| --- | --- |
| **Event time** | Lúc sự kiện được đo/phát sinh theo nguồn |
| **Ingestion time** | Lúc hệ lưu trữ nhận và xử lý mẫu |
| **Processing time** | Lúc pipeline tổng hợp chạy |
| **Bucket start/end** | Mốc logic dùng để đặt mẫu vào cửa sổ |
| **Watermark/allowed lateness** | Chính sách hệ stream ước lượng mức tiến của event time và chấp nhận dữ liệu trễ |

Ví dụ sensor đo lúc **10:00:50** nhưng mạng nghẽn nên tới kho lúc **10:03:20**. Nếu rollup 10:00 đã chốt lúc 10:01, điều gì xảy ra?

Có một số chính sách:

1. **Chấp nhận và cập nhật lại bucket cũ:** dữ liệu tổng hợp có thể thay đổi sau khi dashboard từng hiển thị.
2. **Giữ cửa sổ mở thêm một khoảng trễ:** tăng độ chính xác nhưng tăng độ trễ công bố kết quả.
3. **Bỏ dữ liệu đến quá muộn:** đơn giản hơn nhưng báo cáo phải chấp nhận thiếu dữ liệu.
4. **Backfill định kỳ:** đọc lại raw từ nguồn bền vững và tính lại những bucket cần chỉnh.

Mỗi chính sách có hệ quả với báo cáo theo thời gian, checkpoint và truy vấn. **Không thể mặc định mọi TSDB cho phép ghi đè dữ liệu lịch sử tùy ý hoặc tự recompute tất cả rollup đã có**.

### 11.1. Sự kiện trùng có thể làm sai tổng hợp

Nếu nguồn gửi lại cùng event ba lần, một pipeline **count** ngây thơ có thể tăng ba. Muốn đếm sự kiện duy nhất, phải có **event ID ổn định** và cơ chế idempotency/dedup thích hợp.

Trong metric hệ thống theo chu kỳ scrape, cùng một timestamp và tập label có thể có hợp đồng ghi đè/trùng khác với event stream. Phải hiểu nguyên tắc dedup của sản phẩm và pipeline; không lấy tính năng tự xử lý duplicate ở một engine làm bảo đảm chung cho mọi hệ NoSQL.

## 12. Khoảng trống mẫu không phải giá trị bằng 0

Một sai lầm rất phổ biến khi tổng hợp là coi **không có mẫu** giống **mẫu giá trị 0**.

~~~text
10:00 → cpu_usage = 40%
10:01 → không có mẫu (agent mất kết nối)
10:02 → cpu_usage = 45%
~~~

Nếu điền 0 vào 10:01, trung bình ba phút là (40 + 0 + 45)/3 ≈ **28,3%**, trong khi trung bình trên hai mẫu quan sát được là **42,5%**. Hai số trả lời **hai câu hỏi khác nhau**.

Cần quy định:

- Missing có nghĩa nguồn lỗi, mạng lỗi, hay thiết bị tắt?
- Có được nội suy tuyến tính hoặc carry-forward giá trị trước không?
- Được carry-forward tối đa bao lâu để tránh “máy đã mất” mà dashboard vẫn báo CPU bình thường?
- Alert “không còn dữ liệu” có phải alert riêng, thay vì được diễn giải như tải bằng 0?
- Khi tính sum/count/average, mẫu thiếu có làm tăng count không?

Đối với counter, tính rate cần đủ mẫu và xử lý reset; một khoảng dài không có điểm đo không nên mặc nhiên được coi là mức hoạt động 0. Với SLO hoặc báo cáo tài chính, cần ghi riêng **mức độ bao phủ dữ liệu (coverage/completeness)**.

## 13. Nhãn thay đổi theo thời gian: tính đúng đắn khi rollup

Giả sử thiết bị D-42 được gắn nhãn **region=asia** vào tuần trước, nhưng hôm nay được chuyển sang **region=eu**. Nếu metric được ghi với region trong label, TSDB có thể thấy:

~~~text
temperature{device="D-42",region="asia"} ...
temperature{device="D-42",region="eu"} ...
~~~

Đó là **hai series**. Một báo cáo “nhiệt độ trung bình theo vùng trong 12 tháng” phải định nghĩa:

- Tính theo **vùng tại thời điểm đo** hay vùng hiện tại của thiết bị?
- Các thay đổi metadata trong quá khứ có phải cập nhật lại dữ liệu/rollup cũ?
- Có cho phép một thiết bị đóng góp vào hai region ở những khoảng thời gian khác nhau không?

Series cardinality tăng do label thay đổi là một phần tự nhiên của **churn**. Nhưng nếu nghiệp vụ muốn truy vấn lịch sử theo một thực thể ổn định và thuộc tính của nó biến động, có thể lưu **device_id + timestamp** trong kho event, rồi tham chiếu bảng lịch sử thuộc tính theo khoảng thời gian hiệu lực (*slowly changing dimension* hoặc cơ chế tương đương). Không phải mọi thuộc tính thay đổi đều nên được ghi cứng vào label của mọi metric.

## 14. Chính sách nhãn và retention liên quan đến quyền riêng tư

Giá trị nhãn thường xuất hiện ở:

- Index và metadata của TSDB.
- Dashboard và query kết quả.
- URL tham số truy vấn, log truy vấn, alert message và bản sao lưu.
- Hệ thống remote-write hoặc kho metrics thứ cấp.

Nếu gắn **email**, **token**, **sessionId** hoặc thông tin người dùng vào nhãn, vấn đề không chỉ là cardinality; còn có nguy cơ lộ dữ liệu và khó thực thi chính sách xóa dữ liệu ở mọi hệ. Cần thiết kế nhãn theo **nhu cầu quan sát và phạm vi dữ liệu được phép**, dùng phân quyền và redaction phù hợp.

Retention của một TSDB không tự xóa bản sao trong log, trace, dashboard snapshot hay hệ remote storage. Nếu yêu cầu xóa có hạn định, phải liệt kê đường dữ liệu và hợp đồng lưu giữ của từng bản sao, rồi kiểm chứng thực tế.

## 15. Quan sát chính hệ thống lưu dữ liệu theo thời gian

Để quản lý cardinality và retention, cần giám sát hệ thống observability/TSDB chứ không chỉ giám sát ứng dụng.

| Chỉ số | Câu hỏi cần trả lời | Hành động khi bất thường |
| --- | --- | --- |
| **Active series** | Số series đang hoạt động tăng nhanh không? | Tìm metric/label mới gây tăng |
| **Series created/removed rate** | Churn có tăng sau deploy không? | Kiểm tra pod UID, URL, tenant/user label |
| **Distinct label values** | Nhãn nào có tập giá trị lớn nhất? | Xem lại hợp đồng instrumentation |
| **Samples ingested/s** | Lượng mẫu đến tăng do nhiều series hay sampling nhanh hơn? | Đối chiếu scrape interval, nguồn mới |
| **Rejected samples** | Dữ liệu bị từ chối do hạn timestamp, lỗi nhãn hay quota? | Xem cấu hình và nguồn tạo mẫu |
| **Index/head memory** | Áp lực bộ nhớ đến từ series metadata? | Giảm cardinality/churn hoặc mở rộng đúng nút nghẽn |
| **Storage growth** | Retention và compression có giữ được ngân sách? | Tính lại cấp lưu trữ, mẫu/series và bản sao |
| **Compaction/retention lag** | Dữ liệu đã hết hạn có được dọn kịp? | Điều tra công việc nền và sức chứa |
| **Query fan-out/scanned series** | Dashboard có phải đọc quá nhiều series? | Giảm chiều truy vấn, recording rules, rollup |
| **Rollup freshness/completeness** | Tổng hợp có theo kịp nguồn và đủ mẫu? | Xem backlog, late data, retry/backfill |
| **Query p95/p99, lỗi** | Người dùng có truy vấn dashboard đúng hạn? | Tối ưu index, phạm vi thời gian, phân giải hoặc capacity |

Khi một deploy khiến bộ nhớ TSDB tăng đột biến, nên so sánh:

1. Metric nào có series mới nhiều nhất?
2. Nhãn nào xuất hiện giá trị phân biệt nhiều nhất?
3. Có label nào vô tình chứa URL/path hoặc ID request không?
4. Tốc độ **series creation** có tăng, trong khi samples/s không tăng tương ứng?
5. Có thay đổi scrape target, số instance, retention hoặc remote-write không?

Không nên chữa vấn đề bằng cách **tăng RAM liên tục** khi nguyên nhân là một nhãn phát sinh gần như vô hạn giá trị.

## 16. Thiết kế thử nghiệm trước khi triển khai

Một thử nghiệm có giá trị phải tái hiện **cả cardinality, sampling rate, churn và kiểu truy vấn**. Một benchmark chỉ ghi một metric với một bộ nhãn sẽ không bộc lộ chi phí index của môi trường thật.

### 16.1. Đặc tả workload mẫu

~~~yaml
scenario: metrics-retention-rollup
series:
  active: 100000
  churnNewPerHour: 20000
scrape:
  intervalSeconds: 15
labels:
  serviceValues: 20
  envValues: 3
  regionValues: 4
  instanceValues: variable
retention:
  rawDays: 7
  rollup1mDays: 30
  rollup1hDays: 365
queries:
  - "error rate by service for last 5 minutes"
  - "p95 latency by route for last 24 hours"
  - "request volume by region for last 30 days"
  - "CPU min/max of an instance for last 2 hours"
measure:
  - "ingested samples per second"
  - "active and historical series"
  - "series creation/churn rate"
  - "index/head memory"
  - "storage growth, compaction lag"
  - "query p95/p99 and scan volume"
  - "rollup freshness and accuracy"
~~~

Đây là **mẫu kịch bản**, không phải cấu hình chạy trực tiếp cho một TSDB. Cần thay bằng dữ liệu và SLO của hệ thống. Nếu dùng Prometheus cho ví dụ, cần phân biệt cấu hình local retention với quy trình tạo/giữ rollup ở hệ khác.

### 16.2. Ma trận kiểm chứng

| Kịch bản | Biến thay đổi | Cần tìm hiểu |
| --- | --- | --- |
| Baseline | Số series và sampling ổn định | Sức chứa/độ trễ tại tải dự kiến |
| Tăng label cardinality | Thêm giá trị service/tenant/user giả lập | Ảnh hưởng tới head/index và query |
| Churn cao | Thay nhãn instance thường xuyên | Chi phí tạo/hủy series |
| Interval ngắn | 15s → 5s | Số mẫu, CPU ingest, storage và hiệu quả truy vấn |
| Retention dài | 7 ngày → 30 ngày raw | Dung lượng và chi phí truy vấn lịch sử |
| Rollup nhiều mức | Raw so với 1m/1h | Tiết kiệm lưu trữ và mức mất chi tiết |
| Burst và spike | Tải tăng đột biến ngắn | Alert/dashboards có bỏ sót đỉnh không? |
| Counter reset | Restart một số instance | Rate/increase có còn đúng không? |
| Mẫu thiếu | Mất kết nối một phần nguồn | Tổng hợp có đánh dấu thiếu dữ liệu? |
| Late arrival | Sự kiện tới trễ sau khi bucket đóng | Rollup có cập nhật, bỏ mẫu hay backfill? |
| Failover/recovery | Lỗi node/compaction kéo dài ở môi trường thử | Tính đúng, backlog và thời gian hồi phục |

Đặc biệt, cần chạy cùng một workload qua **ít nhất hai thiết kế nhãn** (raw URL vs normalized route, hoặc instance-level vs service-level) và qua các mức độ phân giải khác nhau. Theo dõi **chi phí trả cho một truy vấn có ý nghĩa** thay vì chỉ so dung lượng lưu.

### 16.3. Kiểm chứng tính đúng của rollup

Tạo một bộ dữ liệu nhỏ có kết quả biết trước:

~~~text
Metric gauge:   10, 20, 40, 50
Metric counter: 100, 120, 5(reset), 15
Missing:        bỏ mẫu ở một khoảng
Late sample:    gửi lại một mẫu thuộc bucket đã đóng
Duplicate:      gửi một event hai lần cùng eventId
~~~

Sau đó đối chiếu:

- Sum, count, min, max, average được tính đúng.
- Counter reset không tạo rate âm giả.
- Missing không tự thành số 0 nếu hợp đồng không yêu cầu.
- Duplicate không làm tăng count sai nếu nghiệp vụ yêu cầu đếm duy nhất.
- Late sample được xử lý theo chính sách đã chọn và có dấu hiệu dữ liệu được sửa lại.
- Rollup 1 giờ từ 60 bucket 1 phút tương đương kết quả tính từ dữ liệu raw đối với những phép tổng hợp **có tính kết hợp và thống kê đủ**.

Đây là kiểm chứng **ngữ nghĩa dữ liệu**, ngoài bài test throughput và latency.

## 17. Ví dụ tích hợp: giám sát API thương mại điện tử

Hệ thống có 25 dịch vụ, 3 môi trường, 4 region, hàng trăm instance thay đổi trong ngày. Mỗi dịch vụ xuất các metric:

~~~text
http_requests_total
http_request_duration_seconds_bucket
http_request_duration_seconds_sum
http_request_duration_seconds_count
process_cpu_seconds_total
queue_depth
~~~

### 17.1. Bước 1: quy định nhãn

Nhãn được duyệt:

~~~text
env, service, region, route, method, status_class
~~~

Một số metric cấp instance có thể thêm **instance**. Không đưa **userId, orderId, requestId, traceId** vào tập label của metric tổng quát. Với classic histogram, nhãn **le** làm tăng số series theo số bucket, nên phải tính rõ số bucket khi dự báo cardinality.

Ví dụ nếu một metric histogram cổ điển có 10 bucket hữu hạn cộng bucket +Inf, mỗi tổ hợp service/env/region/route/method/status có thể tạo **11 series bucket**, cùng với các series sum và count của histogram. Bố cục cụ thể phụ thuộc instrumentation và cấu hình bucket.

### 17.2. Bước 2: xác định truy vấn cần giữ

**Phát hiện lỗi tăng trong 5 phút**:

~~~promql
sum by (service) (
  rate(http_requests_total{env="prod",status_class="5xx"}[5m])
)
/
sum by (service) (
  rate(http_requests_total{env="prod"}[5m])
)
~~~

Biểu thức là ví dụ dùng PromQL; khi mẫu số bằng 0 hoặc không có dữ liệu, dashboard/alert phải định nghĩa cách hiển thị, không mặc định mọi trường hợp là lỗi bằng 0%.

**Độ trễ p95 từ classic histogram**:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_request_duration_seconds_bucket{env="prod"}[5m])
  )
)
~~~

Đối với xu hướng 365 ngày, cần giữ các thành phần tổng hợp có thể tái sử dụng hoặc histogram phù hợp để tính lại phân vị, thay vì chỉ giữ một giá trị p95 của mỗi giờ rồi cộng/trung bình.

### 17.3. Bước 3: retention theo mục đích

Một thiết kế đề xuất:

- **Raw 15 giây trong 7 ngày** để điều tra lỗi cấp instance.
- **Rollup 1 phút trong 30 ngày** giữ tổng request/error và histogram bucket theo service/route.
- **Rollup 1 giờ trong 365 ngày** giữ request/error count, các thành phần cho tính tỷ lệ và thống kê latency phù hợp; bỏ nhãn instance nếu báo cáo dài hạn không cần nó.

Khi một request gặp lỗi, log/trace có thể chứa **requestId** để tra cứu. Dashboard metric giữ nhãn có cardinality kiểm soát, nhưng có liên kết tới hệ điều tra chi tiết. Đây là phân chia công việc theo truy vấn: metrics trả lời “hệ thống đang có xu hướng gì?”, trace/log trả lời “yêu cầu cụ thể nào đã xảy ra điều gì?”.

### 17.4. Bước 4: theo dõi hiệu quả và rủi ro

- Có metric nào tạo hàng trăm nghìn series mới sau deploy?
- Số instance tạo churn có nằm trong năng lực hệ thống?
- 1 phút hay 1 giờ có làm mất spike quan trọng đối với SLO?
- Bộ lưu trữ dài hạn có cần giữ route detail, hay chỉ service/region?
- Khi mất mẫu và counter reset, báo cáo error rate có xử lý đúng?
- Khi remote-write hoặc pipeline rollup trễ, dashboard có hiển thị tuổi dữ liệu?

Từ đó điều chỉnh nhãn, khoảng lấy mẫu, độ phân giải và thời gian giữ trên cơ sở **câu hỏi cần trả lời và bằng chứng đo được**, thay vì chọn TTL mặc định cho mọi metric.

## 18. Những nhầm lẫn thường gặp

1. **“Metric chỉ có một số nên rất nhẹ.”** Chi phí series metadata, index, nhãn và churn có thể lớn hơn dự kiến.
2. **“Giảm retention từ 90 ngày xuống 7 ngày sẽ hết lỗi cardinality.”** Không nhất thiết; active series và churn ở hiện tại vẫn có thể quá tải.
3. **“Có 10 giá trị mỗi nhãn thì luôn là 100 series cho hai nhãn.”** Không đúng nếu chỉ một phần tổ hợp xuất hiện, hoặc các nhãn thuộc những metric khác nhau.
4. **“Lấy mẫu mỗi phút thay vì 15 giây sẽ giảm số nhãn.”** Không: việc này chủ yếu giảm số mẫu, không tự làm giảm tập series.
5. **“Lưu trung bình theo giờ là đủ cho mọi truy vấn.”** Không: spike, min/max, phần trăm lỗi, histogram và counter cần các thống kê phù hợp.
6. **“Trung bình p95 của hai region là p95 toàn hệ thống.”** Sai: percentile không gộp bằng average.
7. **“Counter là số tích lũy nên cứ lấy cuối trừ đầu.”** Có thể sai khi counter reset hoặc thiếu mẫu.
8. **“Thiếu mẫu nghĩa là giá trị 0.”** Không có bằng chứng; có thể chỉ là agent hoặc mạng bị lỗi.
9. **“Downsampling luôn làm giảm cardinality.”** Không nếu rollup vẫn giữ mọi nhãn; nó có thể chỉ giảm số mẫu.
10. **“Retention xóa dữ liệu ngay ở tất cả bản sao.”** Không: còn block, snapshot, backup, remote store và quy trình dọn riêng.
11. **“Gắn userId vào label giúp điều tra request.”** Nó có thể làm cardinality rất lớn; log/trace thường phù hợp hơn.
12. **“Một rollup đã chốt không thể thay đổi.”** Tùy chính sách late arrival và khả năng recompute; cần nêu rõ hợp đồng.

## 19. Bài tập thực hành

Một nền tảng theo dõi thiết bị IoT có:

- 200.000 thiết bị, mỗi thiết bị gửi ba metric **temperature**, **humidity** và **battery_level**.
- Chu kỳ đo 30 giây, nhưng 5% thiết bị có thể gửi dữ liệu muộn tới 10 phút.
- Nhãn hiện tại: **deviceId, siteId, region, firmwareVersion, userId**.
- Đội vận hành cần xem dữ liệu **từng thiết bị trong 48 giờ**, xu hướng **theo site trong 90 ngày**, báo cáo **theo region trong 2 năm**.
- Một số thiết bị có dữ liệu mất khi mất kết nối; firmware có thể thay đổi giữa các lần cập nhật.

### Phần A — Ước lượng cardinality và số mẫu

Hãy tính số series lý thuyết khi chỉ xét **ba metric × 200.000 thiết bị** và mỗi thiết bị có một tổ hợp nhãn tại một thời điểm. Nếu có 600.000 series active và chu kỳ 30 giây, số mẫu/ngày dự kiến là:

\[
600.000\times\frac{86.400}{30}
=1.728.000.000\text{ mẫu/ngày.}
\]

Sau đó giải thích vì sao **userId** và **firmwareVersion** có thể làm số series lịch sử vượt mức 600.000, dù cùng một thiết bị không gửi đồng thời hai giá trị nhiệt độ. Phân biệt việc thay nhãn theo thời gian với việc tạo nhiều series cùng lúc.

### Phần B — Thiết kế nhãn

Chọn nhãn nào cần để truy vấn từng thiết bị, theo site và theo region. Nhãn nào có thể chuyển sang metadata của thiết bị thay vì gắn vào mọi metric? Nếu firmwareVersion cần phục vụ chẩn đoán, có nên giữ nó ở raw 48 giờ và bỏ khỏi rollup 90 ngày không?

### Phần C — Retention và rollup

Đề xuất:

- Độ phân giải/raw retention cho điều tra một thiết bị.
- Dữ liệu theo site trong 90 ngày cần giữ **sum, count, min, max** hoặc thống kê gì?
- Dữ liệu theo region trong 2 năm nên gộp qua những nhãn nào?
- Khi site có số thiết bị thay đổi, tính **nhiệt độ trung bình toàn site** từ những bucket như thế nào để không mắc lỗi trung bình của trung bình?

### Phần D — Dữ liệu thiếu và đến muộn

Một sensor đo nhiệt độ lúc 10:00:30 nhưng gửi tới lúc 10:08. Quy trình rollup đã chốt phút 10:00 lúc 10:02. Hãy chọn chính sách cập nhật lại bucket, chờ thêm, bỏ mẫu hoặc backfill. Nêu độ trễ dữ liệu hiển thị mà nhóm vận hành chấp nhận.

Một thiết bị không gửi dữ liệu trong 20 phút phải được biểu diễn là **missing/offline** hay **temperature = 0°C**? Điều gì xảy ra với thống kê trung bình nếu điền 0?

### Phần E — Chạy thử và ra quyết định

Thiết kế kịch bản so sánh:

| Phương án | Nhãn raw | Rollup 90 ngày | Rollup 2 năm | Cần đánh giá |
| --- | --- | --- | --- | --- |
| A | device, site, region, firmware, user | Giữ mọi nhãn | Giữ mọi nhãn | Khả năng bùng nổ series và churn |
| B | device, site, region | Gộp theo site | Gộp theo region | Tiết kiệm tài nguyên và độ chính xác |
| C | device và metadata tham chiếu | Gộp theo site có hiệu lực tại event time | Gộp theo region | Chi phí join/biến đổi và xử lý metadata lịch sử |

Với từng phương án, đo active series, tốc độ tạo series, samples/s, index/head memory, dung lượng dự báo, p99 truy vấn 48 giờ/90 ngày/2 năm, độ mới rollup, khả năng xử lý dữ liệu trễ và sai số thống kê. Chỉ chọn sau khi đã nêu **đường truy vấn, yêu cầu giữ lịch sử và giới hạn chấp nhận được**.

**Ý chính:** Ở các hệ NoSQL theo thời gian, **cardinality quyết định số chuỗi cần quản lý**, **sampling interval quyết định số mẫu phát sinh**, **retention quyết định dữ liệu lịch sử được giữ**, còn **rollup quyết định thông tin nào còn lại khi giảm độ phân giải**. Bốn quyết định liên hệ chặt chẽ nhưng không thay thế nhau. Thiết kế tốt giữ được những chiều dữ liệu cần truy vấn, những thống kê đủ để tính toán đúng, và độ chi tiết phù hợp với cả điều tra ngắn hạn lẫn phân tích dài hạn.
