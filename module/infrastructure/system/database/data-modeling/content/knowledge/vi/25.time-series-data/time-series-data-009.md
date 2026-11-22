# Số lượng tổ hợp nhãn và rủi ro bùng nổ số chuỗi

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, một mô hình dữ liệu tốt phải chuyển nhu cầu nghiệp vụ thành cấu trúc có ý nghĩa, có thể đo lường và kiểm chứng, từ quan hệ và ràng buộc đến lưu trữ vật lý. Với **dữ liệu chuỗi thời gian** (*time-series data*), ngoài thời điểm và giá trị đo, người thiết kế phải hiểu **các nhãn nhận diện chuỗi** (*labels/tags*). Một lựa chọn nhãn không phù hợp có thể khiến lượng chuỗi tăng nhanh hơn rất nhiều so với số thực thể nghiệp vụ được quan sát.

Sau bài này, bạn có thể:

1. Giải thích **một chuỗi được nhận diện bởi tên metric và toàn bộ bộ nhãn** như thế nào; phân biệt số mẫu với số chuỗi.
2. Tính **giới hạn trên của số tổ hợp nhãn**, hiểu vì sao số tổ hợp thực tế có thể thấp hơn tích lý thuyết.
3. Nhận diện nhãn có **cardinality cao** và **churn cao** như `user_id`, `request_id`, URL thô, pod/job ngắn hạn.
4. Ước lượng tác động đến số mẫu ghi, bộ nhớ, chỉ mục, dung lượng, truy vấn và sự liên tục của chuỗi.
5. Thiết kế bộ nhãn đủ phục vụ truy vấn nhưng không biến mỗi sự kiện thành một chuỗi riêng.
6. Sử dụng SQL để kiểm tra số chuỗi đang hoạt động, số chuỗi theo metric, số giá trị từng nhãn và tốc độ xuất hiện chuỗi.
7. Lập ngân sách cardinality, phép thử instrumentation, cảnh báo và chiến lược giảm rủi ro có kiểm soát.

## 1. Một chuỗi thời gian khác với một bản ghi sự kiện

Giả sử hệ thống đo số yêu cầu HTTP theo dịch vụ. Một metric dạng bộ đếm có thể được biểu diễn như sau:

~~~text
http_requests_total{
    service="checkout",
    environment="prod",
    region="ap-southeast",
    route="/orders/{orderId}",
    status_class="2xx"
}
~~~

Ở cách biểu diễn này, **danh tính của một chuỗi** (*series identity*) được xác định bởi:

\[
\text{Series ID}
=
(\text{metric name},\ \text{label set}).
\]

Một *label set* là tập các cặp `label_name=label_value`. Thứ tự trình bày các cặp không làm chúng trở thành nhãn khác, nhưng **thay đổi một giá trị nhãn** sẽ tạo ra một định danh chuỗi khác. Với ví dụ trên:

~~~text
http_requests_total{service="checkout",route="/orders/{orderId}",status_class="2xx"}
http_requests_total{service="checkout",route="/orders/{orderId}",status_class="5xx"}
~~~

được xem là **hai chuỗi khác nhau** khi các nhãn khác giữ nguyên.

Các mẫu dữ liệu của **cùng một chuỗi** là:

~~~text
series: http_requests_total{service="checkout",region="ap-southeast",...}

2026-11-01T10:00:00Z  1802
2026-11-01T10:00:15Z  1815
2026-11-01T10:00:30Z  1828
~~~

**Thời điểm và giá trị đo không nằm trong định danh chuỗi.** Ba mẫu trên có thể thuộc **một chuỗi**, không phải ba chuỗi. Ngược lại, thay `route` từ đường dẫn chuẩn hóa thành một URL chứa ID riêng của từng yêu cầu có thể khiến hàng nghìn chuỗi khác nhau xuất hiện dù mỗi chuỗi chỉ có một hoặc vài mẫu.

### Phân biệt ba khái niệm

| Khái niệm | Câu hỏi | Đơn vị minh họa |
|---|---|---|
| **Số chuỗi (series cardinality)** | Có bao nhiêu tổ hợp tên metric + nhãn phân biệt? | 7.200 chuỗi |
| **Số mẫu (sample volume)** | Có bao nhiêu điểm dữ liệu được ghi theo thời gian? | 41.472.000 mẫu/ngày |
| **Tốc độ thay chuỗi (series churn)** | Bao nhiêu chuỗi mới xuất hiện, biến mất hoặc thay bộ nhãn qua từng khoảng? | 2.000 chuỗi mới xuất hiện so với giờ trước |

Ba chỉ số có liên quan nhưng **không thay thế nhau**. Hạ tần suất lấy mẫu có thể giảm lượng mẫu mà **không làm giảm số chuỗi đang phải quản lý**.

## 2. Vì sao các nhãn có thể tạo ra bùng nổ tổ hợp?

Một metric được phân biệt theo năm nhãn:

~~~text
service
environment
region
route
status_class
~~~

Giả sử trong phạm vi quan sát:

| Nhãn | Số giá trị phân biệt giả định |
|---|---:|
| `service` | 6 |
| `environment` | 3 |
| `region` | 4 |
| `route` | 20 |
| `status_class` | 5 |

Nếu **mọi cách kết hợp đều có thể xảy ra**, giới hạn trên của số chuỗi cho **một metric** là:

\[
C_{\max}
=
6\times3\times4\times20\times5
=7.200.
\]

Tức là chỉ với năm nhãn nhìn có vẻ nhỏ, hệ thống đã có thể cần quản lý **7.200 chuỗi của riêng metric này**.

Nếu thêm `customer_id` có **1.000 giá trị**, giới hạn trên trở thành:

\[
7.200\times1.000=7.200.000.
\]

Đây là **7,2 triệu tổ hợp tiềm năng**, chưa tính các metric khác.

### Quan trọng: tích các nhãn là giới hạn trên, không mặc nhiên là số chuỗi thật

Trong thực tế:

- Một dịch vụ có thể chỉ chạy ở một vài region.
- Không phải route nào cũng tồn tại trên tất cả service.
- Một số tổ hợp route/status không bao giờ phát sinh.
- `instance_id` thường gắn với một dịch vụ và region cụ thể, không xuất hiện ở mọi tổ hợp.

Do đó:

\[
C_{\text{observed}}\leq\prod_{i=1}^{k}|L_i|
\]

trong đó \(|L_i|\) là số giá trị có thể có của nhãn \(i\) trong **cùng phạm vi** và \(C_{\text{observed}}\) là số **bộ nhãn thực sự xuất hiện** của metric đang xét. Bất đẳng thức áp dụng khi đã thống nhất cách biểu diễn cả **nhãn vắng mặt**, phạm vi và thời điểm quan sát.

Không được báo “có 7,2 triệu chuỗi” chỉ vì phép nhân cho ra số đó. Muốn biết số thực tế, phải **đếm các bộ nhãn phân biệt**, không chỉ đếm giá trị từng cột.

### Những gì khiến tích tăng nhanh

Nếu bộ nhãn ban đầu có \(C\) tổ hợp khả dĩ, thêm một nhãn có \(m\) giá trị **độc lập với các nhãn hiện tại** có thể tăng tới:

\[
C'=C\times m.
\]

Nếu hai nhãn phụ thuộc nhau, mức tăng thực tế có thể thấp hơn. Tuy vậy, rất nhiều nhãn **cardinality trung bình** vẫn có thể tạo ra tổ hợp lớn. Không nên chỉ rà soát những nhãn có hàng triệu giá trị.

## 3. Cardinality cao và churn cao là hai vấn đề khác nhau

### 3.1. Nhãn có cardinality cao

Ví dụ:

~~~text
user_id = U000001 ... U999999
request_id = 8d2f... (mỗi yêu cầu một giá trị)
session_id = 71c9... (mỗi phiên một giá trị)
raw_path = /users/12345/orders/67890
error_message = "failed for item 8934 at ..."
~~~

Các giá trị này có thể rất hữu ích trong **log, trace, dữ liệu sự kiện** nhưng thường không phù hợp làm **nhãn cho metric được lấy mẫu lặp lại**. Nếu mỗi yêu cầu có `request_id` riêng, ta đã biến một metric tổng hợp thành hàng loạt chuỗi gần như chỉ xuất hiện một lần.

### 3.2. Nhãn có churn cao

Không phải nhãn nào có churn cao cũng có số giá trị đồng thời rất lớn. Ví dụ:

~~~text
pod_id = checkout-7bc42      -- tồn tại 15 phút
pod_id = checkout-8d911      -- thay sau deploy
pod_id = checkout-c2a77      -- thay sau scale
~~~

Tại một thời điểm có thể chỉ có 20 pod, nhưng sau nhiều lần deploy và autoscale, hệ thống đã tạo ra **hàng trăm hoặc hàng nghìn bộ nhãn qua thời gian**.

Vì vậy nên theo dõi đồng thời:

- **Active series:** các chuỗi có mẫu gần đây trong một cửa sổ đo đã quy định.
- **Historical distinct series:** tất cả bộ nhãn khác nhau đã gặp trong một khoảng dài hơn.
- **New / disappearing series:** các chuỗi xuất hiện ở cửa sổ này nhưng không ở cửa sổ trước, và ngược lại.
- **Series lifetime:** một chuỗi thường tồn tại bao lâu và có đủ mẫu để tính toán có ý nghĩa không?

Nếu chỉ nhìn **số chuỗi đang hoạt động**, có thể bỏ sót một hệ tạo chuỗi mới liên tục rồi để chúng biến mất. Nếu chỉ nhìn **tổng chuỗi từng xuất hiện**, có thể kết luận quá mức về số chuỗi thực sự cần giữ trong bộ nhớ tại cùng thời điểm.

### 3.3. Nhãn thực thể ngắn hạn đôi khi vẫn cần thiết

`instance`, `pod` hoặc `node` không phải **luôn sai**. Việc quan sát lỗi theo một instance có thể cần thiết cho vận hành. Quyết định nên dựa vào:

- Có thật sự cần truy vấn **từng instance** hay chỉ cần theo service/region?
- Số instance đồng thời và tốc độ thay thế có giới hạn không?
- Có cần cả metric mức dịch vụ và metric mức instance không?
- Mức chi tiết ấy có thể được cung cấp bằng log/trace hoặc một hệ thống khác không?

Mục tiêu là **mức phân giải cần thiết để ra quyết định**, không phải loại bỏ mọi nhãn kỹ thuật.

## 4. Histogram làm số chuỗi tăng thêm như thế nào?

Metric độ trễ HTTP thường cần **phân phối thời gian phản hồi**, không chỉ một trung bình. Với histogram dạng bucket cổ điển, dữ liệu có thể gồm:

~~~text
http_request_duration_seconds_bucket{...,le="0.1"}
http_request_duration_seconds_bucket{...,le="0.3"}
http_request_duration_seconds_bucket{...,le="1.0"}
...
http_request_duration_seconds_bucket{...,le="+Inf"}
http_request_duration_seconds_sum{...}
http_request_duration_seconds_count{...}
~~~

`le` là nhãn giới hạn bucket. **Mỗi giá trị `le` tạo một chuỗi bucket khác nhau** cho cùng tổ hợp nhãn còn lại. Vì thế:

\[
\text{series histogram cổ điển}
\approx
C_{\text{labelset}}\times(B+2),
\]

trong đó \(B\) là **số chuỗi bucket**, bao gồm bucket `+Inf`, còn `+2` đại diện cho `_sum` và `_count`. Đây là phép đếm cho **một histogram cổ điển đầy đủ** với cùng bộ nhãn; cách biểu diễn histogram native hoặc các biến thể metric khác có thể không tuân theo hệ số này.

Nếu ví dụ ở phần trước có **7.200 tổ hợp nhãn** và histogram xuất **10 bucket series, một sum, một count**, số chuỗi có thể lên tới:

\[
7.200\times(10+2)=86.400.
\]

Một nhãn mới có nhiều giá trị không chỉ ảnh hưởng một counter: nó có thể nhân cả **bộ chuỗi histogram** theo từng tổ hợp.

### Có nên bỏ histogram để tiết kiệm số chuỗi?

Không nên kết luận như vậy chỉ từ chi phí. Nếu hệ thống cần kiểm tra SLO độ trễ hoặc phân phối đuôi, histogram có thể rất quan trọng. Cần:

1. Xác định metric nào thật sự cần phân phối độ trễ.
2. Chọn các bucket phục vụ ngưỡng nghiệp vụ/SLO, không tạo dày đặc vô mục đích.
3. Giảm **nhãn không cần thiết** trước khi hy sinh khả năng đo.
4. Xem xét loại histogram và khả năng lưu trữ/truy vấn của công nghệ thực tế.

**Ghi nhớ:** số chuỗi của một metric có thể bị nhân thêm bởi **cấu trúc đo lường** như bucket, chứ không chỉ bởi nhãn ứng dụng.

## 5. Số chuỗi dẫn đến chi phí lưu trữ và vận hành như thế nào?

Hãy quay lại ví dụ 7.200 chuỗi, được lấy mẫu **mỗi 15 giây** trong suốt ngày, giả sử không có mẫu lỗi hoặc bị bỏ qua:

\[
\text{mẫu mỗi chuỗi/ngày}
=\frac{24\times60\times60}{15}
=5.760.
\]

Số mẫu mỗi ngày cho **một metric**:

\[
7.200\times5.760
=41.472.000\text{ mẫu/ngày}.
\]

Nếu là histogram cổ điển có 12 chuỗi trên mỗi bộ nhãn, số mẫu tiềm năng mỗi ngày:

\[
86.400\times5.760
=497.664.000\text{ mẫu/ngày}.
\]

Đây là **ước lượng minh họa ở mức phát mẫu lý tưởng**, không phải đo dung lượng byte của một hệ cụ thể. Thực tế còn phụ thuộc sự hiện diện của series, thời gian hoạt động, scrape thất bại, khả năng nén, cấu trúc chỉ mục và chính sách giữ dữ liệu.

### Những thành phần chịu tác động

| Thành phần | Rủi ro từ nhiều chuỗi | Vì sao cần theo dõi |
|---|---|---|
| **Bộ nhớ / head index** | Nhiều định danh series, metadata và trạng thái ghi | Không chỉ phụ thuộc số mẫu được nén |
| **Ingestion** | Nhiều chuỗi đang nhận mẫu đồng thời | Tăng yêu cầu xử lý, CPU và I/O |
| **Chỉ mục nhãn** | Nhiều bộ nhãn/giá trị mới | Tăng chi phí lập chỉ mục và tra cứu |
| **Lưu trữ dài hạn** | Nhiều mẫu và metadata phải giữ | Tăng dung lượng và chi phí object/block |
| **Truy vấn** | Bộ lọc/aggregation phải xét nhiều series | Tăng CPU, bộ nhớ và thời gian đáp ứng |
| **Compaction / retention** | Nhiều chuỗi ngắn tuổi hoặc nhiều block | Có thể tăng công bảo trì/dọn dẹp |
| **Dashboard và cảnh báo** | Truy vấn và số chuỗi kết quả tăng | Giảm khả năng vận hành, tăng nhiễu cảnh báo |

### Giảm tần suất lấy mẫu giải quyết được gì?

Tăng khoảng lấy mẫu từ **15 giây lên 60 giây** làm số mẫu lý tưởng giảm **4 lần** nếu số chuỗi không đổi. Tuy nhiên số chuỗi với các bộ nhãn đang tồn tại **vẫn có thể giữ nguyên**.

Vì vậy:

~~~text
Tối ưu scrape interval → chủ yếu giảm sample rate.
Tối ưu labelset       → giảm số series và cả metadata/index.
Tối ưu retention      → giới hạn thời gian giữ dữ liệu.
Tối ưu query          → giảm chi phí truy vấn.
~~~

Các biện pháp có thể bổ sung nhau, **không phải thay thế hoàn toàn**.

## 6. Nhãn nào có thể dùng cho metric và nhãn nào nên đưa nơi khác?

Đừng hỏi “nhãn này có bao nhiêu giá trị?” mà chỉ hỏi một lần. Hãy hỏi cả **“người dùng có cần nhóm/lọc metric theo nhãn ấy không, phạm vi giá trị có giới hạn không, và nó có đổi liên tục không?”**

| Dữ liệu | Thường phù hợp làm nhãn metric? | Lý do / lựa chọn |
|---|---|---|
| `service` | Thường có | Nhóm theo dịch vụ, số lượng thường kiểm soát được |
| `environment` | Thường có | Phân biệt prod/staging/dev |
| `region` | Thường có | Phân tích vùng hạ tầng, số giá trị hữu hạn |
| `http_method` | Có điều kiện | `GET`, `POST`... thường ít giá trị |
| `status_class` | Thường có | Nhóm `2xx`, `4xx`, `5xx` giúp quan sát lỗi |
| `status_code` | Có điều kiện | Nhiều hơn class nhưng vẫn tương đối hữu hạn; cân nhắc nhu cầu |
| `route_template` | Có, nếu được kiểm soát | Nên là template ổn định, không phải URL chứa ID |
| `instance`/`pod` | Có điều kiện | Hữu ích để chẩn đoán, nhưng tăng cardinality/churn |
| `tenant_id` | Cần đánh giá riêng | Có thể rất nhiều tenant; phân tích theo tenant có thể cần mô hình khác |
| `customer_id` | Thường không cho metric hạ tầng tổng hợp | Dễ có hàng triệu giá trị, nên dùng dữ liệu sự kiện/BI |
| `user_id` | Thường không | Vừa high-cardinality vừa có thể nhạy cảm |
| `request_id`/`trace_id` | Thường không | Gần như duy nhất cho mỗi yêu cầu, phù hợp log/trace |
| `session_id` | Thường không | Tạo nhiều chuỗi ngắn tuổi |
| `url_path_raw` | Không nếu chứa ID động | Dùng route template |
| `error_message` | Thường không | Chuỗi tự do, dễ sinh vô số giá trị |
| `timestamp` như label | Không | Thời điểm đã là trường của mẫu; đưa vào nhãn tạo series mới |

### URL thô và route template

Không nên phát metric:

~~~text
http_requests_total{path="/users/1001/orders/5001"}
http_requests_total{path="/users/1002/orders/5002"}
http_requests_total{path="/users/1003/orders/5003"}
~~~

Nếu nghiệp vụ cần biết tỷ lệ lỗi **theo loại endpoint**, nhãn thích hợp là:

~~~text
http_requests_total{route="/users/{userId}/orders/{orderId}"}
~~~

Số route template cần được quản lý bởi **router/instrumentation hoặc registry có giới hạn**. Đừng dùng biểu thức thay số bằng `{id}` một cách mù quáng với mọi URL: route có thể chứa slug, tên tài nguyên, mã tùy ý hoặc các biến động ngoài dự kiến.

Một route không được nhận diện nên đi vào nhóm có kiểm soát như `route="unmatched"` khi chính sách yêu cầu, đồng thời ghi URL thô ở **log/trace** nếu được phép. Đừng biến toàn bộ đường dẫn chưa match thành một nhãn mới.

### Giá trị tự do và mã lỗi

`error_message="timeout contacting tenant 983..."` có thể sinh hàng triệu chuỗi. Nếu cần số lỗi theo loại:

~~~text
error_type="dependency_timeout"
error_type="validation_failed"
error_type="internal_failure"
~~~

Danh mục loại lỗi cần hữu hạn, có chủ sở hữu, thay đổi có kiểm soát. Thông điệp chi tiết vẫn được ghi trong log có cơ chế truy vết và retention phù hợp.

## 7. Giữ thông tin chi tiết ở đúng mô hình dữ liệu

Các mục tiêu quan sát khác nhau cần mô hình khác nhau:

| Câu hỏi | Kiểu dữ liệu phù hợp hơn | Vì sao |
|---|---|---|
| Tỷ lệ lỗi theo service, region, route | **Metrics** với nhãn hữu hạn | Tổng hợp và cảnh báo hiệu quả |
| Vì sao request `REQ-123` lỗi? | **Trace / log** có request ID | Truy theo một sự kiện cụ thể |
| Khách hàng nào phát sinh nhiều giao dịch? | **Fact table / event data** theo user/tenant | Cho phép khóa, thời gian, nghiệp vụ và phân tích chi tiết |
| Chi tiết biến động một tài khoản | **Sự kiện giao dịch hoặc audit log** | Không tạo mỗi tài khoản một chuỗi metric không giới hạn |
| Số lượng đơn theo danh mục/ngày | **Data mart** với grain và dimension rõ | Dễ đối soát số đo và lịch sử |
| Tình trạng CPU theo pod đang hoạt động | **Metric có nhãn instance/pod khi cần** | Cần chẩn đoán đối tượng hạ tầng |

Không có nghĩa mọi `tenant_id` hoặc `user_id` đều bị cấm trong **bất kỳ** hệ dữ liệu chuỗi thời gian nào. Một hệ lưu số dư theo tài khoản hoặc cảm biến theo thiết bị có thể **cố ý** có hàng triệu chuỗi vì đó là thực thể đo chính. Khi ấy phải **thiết kế và cấp tài nguyên theo cardinality**, sử dụng phân vùng/sharding và giới hạn rõ ràng, thay vì vô tình đưa cùng loại ID vào bộ nhãn của mọi metric hạ tầng.

### Liên hệ với fact và dimension

Trong data warehouse, một sự kiện:

~~~text
fact_orders(order_id, customer_id, product_id, confirmed_at, amount)
~~~

có thể mang khóa `customer_id` ở grain giao dịch và được phân tích trên hàng triệu khách. Việc đó **không có nghĩa** một metric `http_latency_seconds{customer_id=...}` là lựa chọn phù hợp. Hệ thống phân tích sự kiện và hệ metric vận hành có mục tiêu truy vấn, cách ghi và tối ưu hóa **khác nhau**.

## 8. Thiết kế ngân sách cardinality trước khi triển khai

Một cách tiếp cận thực dụng là xác định **ngân sách chuỗi** cho mỗi nhóm metric và kiểm tra trước khi phát hành.

### Mẫu ngân sách

| Trường | Nội dung cần điền |
|---|---|
| Metric hoặc nhóm metric | `http_requests_total`, histogram latency |
| Mục đích | Tỷ lệ lỗi theo service/route/status |
| Nhãn bắt buộc | `service`, `environment`, `route_template`, `status_class` |
| Nhãn tùy chọn | `region`, `instance` nếu có nhu cầu xác nhận |
| Giới hạn giá trị dự kiến | Số service, route, region, status trong một khoảng |
| Số bộ nhãn thực tế | Distinct label sets trong 15 phút/1 giờ |
| Churn | Bộ nhãn có mặt ở cửa sổ hiện tại nhưng không ở cửa sổ trước |
| Dạng metric | Counter, gauge, histogram cổ điển/native |
| Chi phí dự kiến | Active series, samples/giây, lưu trữ, query |
| Ngưỡng cảnh báo | Theo khả năng hệ và headroom đã được kiểm chứng |
| Người chịu trách nhiệm | Nhóm sở hữu instrumentation/service |
| Biện pháp giảm | Chuẩn hóa route, bỏ nhãn động, hạn chế số bucket... |

Không có một ngưỡng như “mọi metric phải dưới 1.000 chuỗi” phù hợp với mọi hệ. Số cho phép phụ thuộc tổng metric, hạ tầng, tần suất mẫu, retention, kiến trúc và SLO truy vấn.

### Hai phép ước lượng khác nhau

**Trước khi phát hành**, tính tích các nhãn có thể có:

\[
C_{\max}=\prod_i |L_i|.
\]

Đây là phép **stress test thiết kế**; có thể rất cao nếu các nhãn liên quan nhau.

**Sau khi phát hành**, đo trực tiếp:

\[
C_{\text{active}}
=
\left|\{(\text{metric},\text{label set})\text{ có mẫu trong cửa sổ}\}\right|.
\]

Sau đó kiểm tra **tốc độ tạo chuỗi mới**, tốc độ mẫu, thời gian truy vấn và tài nguyên thực. Một cấu hình có 20.000 active series ổn định có thể gây hành vi vận hành khác với cấu hình có 20.000 active series nhưng liên tục thay toàn bộ nhãn mỗi vài phút.

## 9. Mô hình SQL để đo cardinality có thể kiểm chứng

Phần này sử dụng **PostgreSQL làm ví dụ mô hình dữ liệu**, không khẳng định một TSDB chuyên dụng lưu chuỗi vật lý giống hệt như vậy. Mục đích là minh họa cách **định danh series**, đếm bộ nhãn và kiểm tra churn bằng dữ liệu quan hệ.

### 9.1. Danh mục series và bảng mẫu

~~~sql
CREATE TABLE metric_series (
    series_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metric_name TEXT NOT NULL,
    service TEXT NOT NULL,
    environment TEXT NOT NULL,
    region TEXT NOT NULL,
    route_template TEXT NOT NULL,
    status_class TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    UNIQUE (
        metric_name,
        service, environment, region,
        route_template, status_class, instance_id
    )
);

CREATE TABLE metric_samples (
    series_id BIGINT NOT NULL REFERENCES metric_series(series_id),
    sampled_at TIMESTAMPTZ NOT NULL,
    sample_value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (series_id, sampled_at)
);

CREATE INDEX idx_metric_samples_time
    ON metric_samples (sampled_at);
~~~

Trong ví dụ này, **mọi cột nhãn đều NOT NULL** để ràng buộc `UNIQUE` hoạt động nhất quán theo bộ cột. Nếu một metric không dùng `route_template` hoặc `status_class`, pipeline phải biểu diễn **nhãn vắng mặt bằng quy ước tường minh, không va chạm với giá trị thật**. Hệ thực có thể dùng nhãn tùy ý, nullable hoặc cấu trúc khác; đừng coi chuỗi rỗng và nhãn không tồn tại là tương đương nếu engine thực phân biệt chúng.

**Ý nghĩa khóa:**

- `metric_series.series_id`: khóa kỹ thuật cho **một metric + một bộ nhãn**.
- Ràng buộc `UNIQUE` trên các cột nhận diện: ngăn tạo **hai ID series** cho cùng bộ nhãn theo quy tắc chuẩn hóa đầu vào.
- `metric_samples(series_id,sampled_at)`: **một mẫu cho mỗi thời điểm của một series** trong mô hình đơn giản. Một hệ ingest thực tế cần thêm quy tắc khi mẫu cùng timestamp đến trễ, bị gửi lại hoặc có giá trị khác nhau.

`DOUBLE PRECISION` phù hợp minh họa số đo kỹ thuật; **không dùng nó thay `NUMERIC` cho số tiền cần độ chính xác thập phân**. Cần xác định đơn vị đo, kiểu counter/gauge và quy tắc dữ liệu thiếu cho từng metric.

### 9.2. Đếm tổng số series từng được ghi danh

~~~sql
SELECT metric_name, COUNT(*) AS catalog_series
FROM metric_series
GROUP BY metric_name
ORDER BY catalog_series DESC, metric_name;
~~~

Kết quả cho biết **tổng số bộ nhãn trong catalog** theo metric, không phải chắc chắn tất cả đều đang hoạt động. Một catalog không dọn ID cũ có thể tích lũy chuỗi đã chết theo thời gian.

### 9.3. Đếm active series trong một cửa sổ

Giả sử muốn xem những series có **ít nhất một mẫu trong 15 phút**:

~~~sql
WITH active AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 10:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 10:15:00+00'
)
SELECT s.metric_name, COUNT(*) AS active_series
FROM active AS a
JOIN metric_series AS s
  ON s.series_id = a.series_id
GROUP BY s.metric_name
ORDER BY active_series DESC, s.metric_name;
~~~

**Định nghĩa cửa sổ phải rõ.** Một series không gửi mẫu vì scrape bị lỗi có thể bị xem là “không active” trong truy vấn này, dù về mặt cấu hình nó vẫn tồn tại. Active ở đây có nghĩa chính xác là **đã quan sát ít nhất một mẫu trong cửa sổ**.

### 9.4. Đếm số giá trị của từng nhãn

~~~sql
WITH active AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 10:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 10:15:00+00'
)
SELECT
    s.metric_name,
    COUNT(DISTINCT s.service) AS services,
    COUNT(DISTINCT s.environment) AS environments,
    COUNT(DISTINCT s.region) AS regions,
    COUNT(DISTINCT s.route_template) AS routes,
    COUNT(DISTINCT s.status_class) AS status_classes,
    COUNT(DISTINCT s.instance_id) AS instances,
    COUNT(*) AS observed_labelsets
FROM active AS a
JOIN metric_series AS s
  ON s.series_id = a.series_id
GROUP BY s.metric_name
ORDER BY observed_labelsets DESC;
~~~

`observed_labelsets` là **số bộ nhãn đã quan sát**, còn các cột `services`, `routes`... là **số giá trị phân biệt của từng chiều**. Không nhân chúng rồi trình bày sản phẩm như số observed thực tế; các nhãn có thể tương quan.

### 9.5. Đo churn giữa hai cửa sổ liên tiếp

~~~sql
WITH previous_window AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 09:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 10:00:00+00'
),
current_window AS (
    SELECT DISTINCT series_id
    FROM metric_samples
    WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 10:00:00+00'
      AND sampled_at <  TIMESTAMPTZ '2026-11-01 11:00:00+00'
),
appeared_vs_previous AS (
    SELECT series_id FROM current_window
    EXCEPT
    SELECT series_id FROM previous_window
)
SELECT s.metric_name, COUNT(*) AS appeared_vs_previous_hour
FROM appeared_vs_previous AS a
JOIN metric_series AS s
  ON s.series_id = a.series_id
GROUP BY s.metric_name
ORDER BY appeared_vs_previous_hour DESC;
~~~

Kết quả là **series có mẫu trong giờ hiện tại nhưng không có mẫu trong giờ liền trước**. Một series từng tồn tại trước đó rồi hoạt động lại vẫn có thể xuất hiện trong kết quả. Vì vậy gọi chỉ số này là **“xuất hiện so với cửa sổ trước”**, **không** khẳng định mọi dòng đều là series lần đầu được tạo trong lịch sử.

Muốn đo *first-ever new series*, cần biết thời điểm xuất hiện đầu tiên hoặc có log tạo series đáng tin cậy. Churn còn có chiều ngược là **series biến mất so với cửa sổ trước**; có thể đổi thứ tự hai vế của phép `EXCEPT` để đo.

### 9.6. Đo số mẫu theo giờ

~~~sql
SELECT
    DATE_TRUNC('hour', sampled_at) AS hour_utc_or_session_zone,
    COUNT(*) AS ingested_samples
FROM metric_samples
WHERE sampled_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND sampled_at <  TIMESTAMPTZ '2026-11-02 00:00:00+00'
GROUP BY DATE_TRUNC('hour', sampled_at)
ORDER BY hour_utc_or_session_zone;
~~~

Trong PostgreSQL, cách `DATE_TRUNC` hiển thị mốc `TIMESTAMPTZ` có thể chịu ảnh hưởng **múi giờ phiên**. Khi đối chiếu giữa hệ, phải chuẩn hóa timezone và mốc giờ. Số mẫu theo giờ bổ sung thông tin cho active series nhưng không thay thế phép đếm distinct labelset.

### 9.7. SQL là công cụ kiểm tra, không phải kiến trúc TSDB bắt buộc

Mô hình hai bảng trên cho thấy:

- Nhãn phải có **định danh ổn định, chuẩn hóa**, tránh tạo series mới chỉ vì cách ghi chữ hoa/chữ thường hoặc ký tự trong nhãn khác nhau.
- Một `series_id` có thể có nhiều mẫu theo thời gian; **khóa series và khóa mẫu khác nhau**.
- **Catalog cardinality**, **active cardinality**, **sample volume** và **churn** cần được đo riêng.

TSDB chuyên dụng có thể dùng chỉ mục đảo, segment/block, nén hoặc biểu diễn nhãn linh hoạt khác; lựa chọn vật lý phải dựa trên workload và công nghệ cụ thể.

## 10. Biện pháp giảm số chuỗi theo thứ tự ưu tiên

### 10.1. Sửa từ nơi phát metric

Đây thường là nơi hiệu quả nhất:

- Thay URL thô bằng `route_template` do router chuẩn hóa.
- Thay `error_message` tự do bằng `error_type` hữu hạn, có quy trình duyệt giá trị mới.
- Không đưa `request_id`, `trace_id`, `session_id`, `user_id` tùy ý vào mọi metric.
- Chỉ thêm `tenant_id` khi có lý do đo theo tenant và đã tính được ngân sách.
- Hạn chế tạo tên metric động như `orders_for_user_123_total`. Đưa những phân loại hữu hạn vào nhãn hoặc dùng hệ sự kiện nếu thực thể quá nhiều.
- Bảo đảm cùng tên route, môi trường, region có **quy tắc chuẩn hóa nhất quán** giữa các phiên bản deploy.

Nếu giảm từ nguồn, hệ thu thập không phải nhận và quản lý các chuỗi thừa ngay từ đầu.

### 10.2. Kiểm soát ở tầng thu thập và lưu trữ

Tùy công nghệ, có thể:

- Bỏ nhãn không cần thiết **trước khi ghi** vào kho metric.
- Từ chối hoặc gắn cờ metric/labelset vượt ngân sách đã phê duyệt.
- Áp dụng limit theo metric, service hoặc tenant và phát cảnh báo về dữ liệu bị từ chối.
- Tách một số metric mức instance rất chi tiết vào tầng lưu trữ có retention ngắn, còn metric tổng hợp ở tầng khác.
- Giảm retention của dữ liệu chi tiết khi phù hợp nhu cầu tra cứu và nghĩa vụ lưu giữ.

**Cảnh báo:** bỏ nhãn có thể làm **hai chuỗi khác nhau có cùng bộ nhãn còn lại**. Với counter/gauge/histogram, không thể cứ bỏ nhãn rồi ghép các mẫu trùng thời điểm một cách tùy tiện: phải xác định **quy tắc tổng hợp đúng cho loại metric**, hoặc cấu hình cách xử lý xung đột phù hợp. Việc mất nhãn `instance` cũng có thể làm giảm khả năng chẩn đoán.

### 10.3. Tổng hợp trước khi lưu

Nếu chỉ cần tỷ lệ lỗi theo service và route, có thể cân nhắc một luồng metric **đã tổng hợp theo service/route/status** thay vì giữ mọi nhãn giao dịch ở kho dài hạn.

Nhưng:

- Với counter, phải xử lý **reset** của từng chuỗi nguồn theo đúng ngữ nghĩa trước khi tổng hợp tốc độ.
- Với histogram, phải gộp các bucket/phân phối theo cách công nghệ hỗ trợ, không lấy trung bình đơn giản các percentile.
- Với gauge, phép cộng/mean/max chỉ đúng khi có ý nghĩa nghiệp vụ.
- Khi bỏ nhãn instance, không còn khả năng truy vấn metric chi tiết của từng instance từ dữ liệu tổng hợp đã lưu.

**Một phép `sum by (...)` trong dashboard chỉ làm ít chuỗi hơn ở kết quả truy vấn; nó không tự làm ít chuỗi hơn đã được ingest/lưu ở nguồn.**

### 10.4. Những cách “giảm cardinality” dễ gây hiểu nhầm

| Cách làm | Vì sao chưa giải quyết vấn đề gốc |
|---|---|
| Hash `user_id` thành chuỗi băm | Số giá trị phân biệt gần như giữ nguyên; có thể còn rủi ro liên kết cá nhân |
| Cắt ngắn ID tùy tiện | Có nguy cơ va chạm, gộp nhầm dữ liệu; không có quy tắc nghiệp vụ |
| Giảm số dòng hiển thị trên dashboard | Chỉ giảm kết quả hiển thị, không giảm lượng chuỗi đã lưu |
| Chỉ tăng scrape interval | Giảm số mẫu, thường không giảm cardinality |
| Chỉ giảm retention | Giảm thời gian giữ mẫu cũ, nhưng không xóa nguyên nhân tạo nhiều active series |
| Chỉ dùng `topk` khi truy vấn | Có thể vẫn phải quét nhiều series để tính top k |
| Chuyển `request_id` từ nhãn này sang tên metric | Vẫn tạo vô số định danh metric khác nhau |
| Dùng `status="other"` cho mọi lỗi | Giảm chuỗi nhưng có thể mất tín hiệu lỗi quan trọng; phải giữ nhóm hữu ích |

Mục tiêu không phải chỉ đạt một số đếm thấp, mà là **giữ đúng tín hiệu cần quan sát với chi phí kiểm soát được**.

## 11. Kiểm chứng cardinality trước và sau khi triển khai

### Bước 1 — Xác nhận câu hỏi cần metric trả lời

Ví dụ: “Theo service/route, tỷ lệ lỗi 5xx trong 5 phút có vượt ngưỡng không?”. Nếu không có ai cần tỷ lệ theo `user_id` tại hệ metric, nhãn đó rất khó biện minh.

### Bước 2 — Lập danh sách metric và bộ nhãn

Đừng lấy union của tất cả nhãn rồi nhân cho mọi metric. Mỗi **metric family** có bộ nhãn, độ phân giải và số mẫu khác nhau. Một histogram có `le`, `_sum`, `_count` cũng khác counter chỉ có một chuỗi trên mỗi bộ nhãn.

### Bước 3 — Ước lượng tích trên các giá trị có thể có

Tính \(C_{\max}\), đánh dấu nhãn **độc lập** hoặc **phụ thuộc nhau**, chỉ ra mức tăng khi thêm nhãn mới và giả định về churn.

### Bước 4 — Kiểm thử với tải đại diện

Theo dõi **active series**, **mẫu/giây**, **series xuất hiện so với cửa sổ trước**, memory, indexing, độ trễ truy vấn và tỷ lệ scrape lỗi. Thử các kịch bản deployment, scale, tenant mới, route mới và traffic đột biến.

### Bước 5 — Đặt giới hạn và người chịu trách nhiệm

Phân metric theo nhóm chủ sở hữu. Với mỗi nhóm cần ngân sách, cảnh báo và quy trình rà soát khi thêm label. Một label mới nên được xem như **thay đổi schema**, không phải chỉ là một dòng code vô hại.

### Bước 6 — Kiểm tra chất lượng sau khi tối ưu

So metric trước/sau thay đổi ở cùng phạm vi:

- Tổng yêu cầu và tổng lỗi có còn khớp nguồn phù hợp không?
- Có nhầm nhóm route/status hoặc mất nhãn phục vụ SLO không?
- Có series trùng sau khi bỏ nhãn không?
- Dashboard/cảnh báo có đổi ngữ nghĩa hoặc mất thông tin không?
- Dữ liệu truy vết request chi tiết còn nằm ở log/trace theo quyền và retention cần thiết không?

Không công bố tối ưu thành công chỉ vì số series giảm mà quên xác minh **độ đúng của chỉ số**.

## 12. Ví dụ truy vấn và cảnh báo trong hệ metric

Với hệ hỗ trợ cú pháp **PromQL** tương tự Prometheus, một truy vấn tỷ lệ yêu cầu theo service và route có thể viết:

~~~promql
sum by (service, route) (
  rate(http_requests_total[5m])
)
~~~

Nếu muốn tỷ lệ lỗi 5xx so với mọi yêu cầu theo service, cần tách tử số/mẫu số với cùng phạm vi:

~~~promql
sum by (service) (
  rate(http_requests_total{status_class="5xx"}[5m])
)
/
sum by (service) (
  rate(http_requests_total[5m])
)
~~~

**Điều kiện:** `http_requests_total` là counter đúng ngữ nghĩa, `status_class` được ghi nhất quán, các series được chọn không nhân cùng một yêu cầu và thời gian quan sát phù hợp. Khi mẫu số bằng 0, kết quả cần được xử lý theo chính sách dashboard/cảnh báo. Đối với counter có reset, phép tính tốc độ nên áp dụng ở **từng chuỗi trước khi cộng**.

### Histogram cổ điển

Ví dụ ước tính phân vị 95% độ trễ theo service khi có bucket cổ điển:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

Phép này phụ thuộc chất lượng cấu hình bucket, số mẫu và bộ nhãn metric. Không được thay bằng **trung bình các p95 của từng instance**. Với histogram native hay engine khác, cú pháp và mô hình tính có thể khác.

### Truy vấn tổng hợp không xóa chi phí của nhãn nguồn

Giả sử `http_requests_total` có thêm `request_id`. Dù truy vấn `sum by(service)` trả một số nhỏ chuỗi, hệ thống **vẫn có thể đã nhận hàng triệu chuỗi theo request_id**. Giải pháp cần nằm ở instrumentation hoặc pipeline lưu trữ, không phải chỉ ở phần GROUP BY của dashboard.

## 13. Các cảnh báo vận hành nên theo dõi

Một bộ giám sát tốt không chỉ cảnh báo khi ổ đĩa gần đầy. Có thể quan sát:

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Active series theo metric/service | Số chuỗi có mẫu trong một cửa sổ | Tăng đột ngột sau deploy |
| Historical distinct labelsets | Tổng bộ nhãn từng thấy trong kỳ | Liên tục tăng dù số đối tượng hoạt động ổn định |
| New-vs-previous series | Bộ nhãn xuất hiện trong cửa sổ hiện tại nhưng không ở cửa sổ trước | Pod churn hoặc nhãn động không kiểm soát |
| Ingested samples/s | Khối lượng mẫu vào hệ | Vượt công suất / tăng chi phí |
| Label value count | Số giá trị route/tenant/instance... | Xuất hiện route thô hoặc error message mới |
| Index/head memory | Tài nguyên quản lý series và nhãn | Tăng nhanh hơn sample rate |
| Query duration / scanned series | Chi phí truy vấn dashboard | Fanout do thêm nhãn, selector quá rộng |
| Scrape failures / dropped series | Dữ liệu bị thiếu hoặc bị từ chối | Budget limiter gây mất tín hiệu |
| Series lifetime distribution | Độ bền một chuỗi | Nhiều chuỗi sống rất ngắn |

Không đặt một ngưỡng duy nhất cho tất cả service. Đo **baseline trước deploy**, headroom của hạ tầng, nhu cầu cảnh báo và các chu kỳ hoạt động. Cảnh báo phải có **người sở hữu và thao tác xử lý**: tìm nhãn mới, rollback instrumentation, sửa route hoặc điều chỉnh cấu hình có kiểm soát.

## 14. Liên hệ với các mô hình dữ liệu khác

| Mô hình | Cách biểu diễn thời gian và định danh | Điểm cần tránh |
|---|---|---|
| **TSDB có nhãn** | Tên metric + bộ nhãn nhận diện chuỗi, mỗi chuỗi nhiều mẫu | Nhãn chứa ID động dẫn tới hàng loạt series |
| **Quan hệ** | `metric_series` chứa định danh bộ nhãn; `metric_samples` chứa thời điểm/giá trị | Trộn khóa series với khóa mẫu, chỉ mục lớn khi tổ hợp nhãn tăng |
| **Document / event log** | Một document/event cho một request với metadata chi tiết | Không ép mọi thuộc tính sự kiện thành nhãn của metric tổng hợp |
| **Đồ thị** | Node/edge cho thực thể và quan hệ; thời gian có thể là thuộc tính sự kiện | Mỗi đường đi không nhất thiết là một chuỗi đo; cần định nghĩa đối tượng truy vấn |
| **Kho phân tích dạng cột** | Fact sự kiện chứa ID, ngày, dimension, measure | Không nhân bản measure khi JOIN; dùng group cardinality đúng grain |

Với một hệ thống có **hàng triệu thiết bị cảm biến**, `device_id` có thể chính là định danh chủ chốt của một time series. Đây là trường hợp **cardinality lớn được thiết kế chủ đích**. Cần mô hình công suất, phân vùng theo thiết bị/thời gian, retention, downsampling khi phù hợp và truy vấn định danh cụ thể.

Ngược lại, với metric `service_http_latency`, `user_id` thường không phải dimension cần thiết cho SLO dịch vụ. Chính **mục đích nghiệp vụ** quyết định nên đặt ID ở nhãn metric hay ở dữ liệu sự kiện.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách sửa |
|---|---|---|
| “Mỗi mẫu đo là một chuỗi” | Một chuỗi có nhiều mẫu theo thời gian | Phân biệt series identity với timestamp/value |
| “Chỉ cần một nhãn cardinality cao mới nguy hiểm” | Tích nhiều nhãn vừa phải cũng có thể rất lớn | Ước lượng tổ hợp, đo distinct labelsets |
| “Tích các số giá trị nhãn là số series hiện có” | Không phải mọi tổ hợp đều xuất hiện | Đo active/observed; xem tích là giới hạn trên |
| “Ít active series thì không có churn” | Nhãn có thể thay liên tục | Đo new/disappearing series và lifetime |
| “Đổi ID thành hash là giảm cardinality” | Mỗi ID thường vẫn có giá trị hash khác nhau | Chuyển ID chi tiết sang log/trace/event store |
| “`path` luôn hữu hạn” | URL chứa ID có thể gần như vô hạn | Dùng route template ổn định |
| “`sum by(service)` giảm chi phí ingest” | Kết quả truy vấn ít nhưng nguồn vẫn lưu các series chi tiết | Giảm nhãn trước khi lưu hoặc tổng hợp đúng |
| “Giảm scrape interval giải quyết bùng nổ nhãn” | Chủ yếu giảm số mẫu | Giảm labelset và churn riêng |
| “Có histogram 10 bucket nghĩa là 10 chuỗi tổng cộng” | Mỗi bộ nhãn có nhiều bucket, sum/count | Nhân số series theo cấu trúc histogram |
| “Cứ bỏ nhãn instance là an toàn” | Mất phân giải; có thể tạo xung đột bộ nhãn | Xác định phép tổng hợp và nhu cầu chẩn đoán |
| “Mọi tenant_id đều không nên là nhãn” | Có hệ buộc phải đo theo tenant | Dự báo và cấp tài nguyên chủ đích |
| “Dùng top-k là đã giảm số series được lưu” | Top-k thường chỉ giới hạn kết quả | Chặn phát/ingest hoặc chuyển tầng theo thiết kế |
| “Nhãn không có rủi ro bảo mật” | Có thể lộ ID khách/user, URL có tham số | Thiết kế phân quyền, phân loại dữ liệu và retention |
| “Giảm series là đủ, không cần kiểm tra chất lượng KPI” | Có thể bỏ nhãn làm gộp nhầm lỗi/route | Đối soát sau thay đổi |

## 16. Bài luyện tập có lời giải

### Bài 1 — Tính tổ hợp nhãn tối đa

Một metric có 4 `service`, 3 `environment`, 2 `region`, 10 `route`, 5 `status_class`. Nếu mọi tổ hợp đều có thể xuất hiện, số chuỗi tối đa của metric là bao nhiêu?

**Lời giải:**

\[
4\times3\times2\times10\times5=1.200.
\]

Đây là **giới hạn trên** theo giả định kết hợp tự do, không tự động là số active series.

### Bài 2 — Thêm nhãn ID động

Với metric ở bài 1, thêm `user_id` có 1.000 giá trị. Giới hạn trên mới là bao nhiêu? Có thể kết luận hệ thống chắc chắn có chừng ấy chuỗi?

**Lời giải:** \(1.200\times1.000=1.200.000\) chuỗi tiềm năng. **Không** thể khẳng định có đúng 1,2 triệu chuỗi: nhiều tổ hợp có thể không xảy ra. Tuy nhiên nhãn `user_id` tạo rủi ro lớn và cần được chứng minh là thiết yếu nếu dùng trong metric.

### Bài 3 — Ước lượng số mẫu

Có 1.200 chuỗi liên tục hoạt động, lấy mẫu mỗi 15 giây. Trong một ngày có bao nhiêu mẫu nếu mọi lần lấy mẫu thành công?

**Lời giải:** Mỗi chuỗi có \(86.400/15=5.760\) mẫu/ngày. Tổng:

\[
1.200\times5.760=6.912.000\text{ mẫu/ngày}.
\]

Số mẫu không phải số chuỗi. Nếu lấy mỗi 60 giây, số mẫu lý tưởng giảm bốn lần, còn số series không tự thay đổi.

### Bài 4 — Histogram có nhiều chuỗi hơn counter

Một histogram cổ điển dùng cùng 1.200 bộ nhãn, có 8 bucket series (đã tính `+Inf`), một `_sum` và một `_count`. Có bao nhiêu series?

**Lời giải:** \(1.200\times(8+2)=12.000\) series cho histogram minh họa. Nếu công nghệ dùng biểu diễn histogram khác, phải tính theo cấu trúc thực tế.

### Bài 5 — Đếm giá trị nhãn không bằng đếm bộ nhãn

Một metric chỉ có hai nhãn `service` và `region`. Có hai service `A,B`, hai region `R1,R2`, nhưng A chỉ chạy ở R1 và B chỉ chạy ở R2. Số series thực tế tối thiểu và tích tối đa là gì, giả sử mỗi cặp hoạt động có một chuỗi?

**Lời giải:** Hai chuỗi quan sát: `(A,R1)`, `(B,R2)`. Tích giới hạn trên \(2\times2=4\). Không được báo có 4 series vì `(A,R2)` và `(B,R1)` không tồn tại.

### Bài 6 — Chọn route template

Metric phát `path="/orders/12345"`, `path="/orders/12346"`, ... cho mỗi yêu cầu. Nhóm SRE chỉ cần tỷ lệ lỗi theo loại endpoint. Bạn thay đổi mô hình thế nào?

**Lời giải:** Ghi nhãn `route="/orders/{orderId}"` được chuẩn hóa bằng router hoặc registry, và `status_class` hữu hạn. Chuyển đường dẫn thô/request ID vào log hoặc trace theo quyền và retention nếu cần đối soát. Đừng dùng regex cắt URL không kiểm soát.

### Bài 7 — Churn sau mỗi lần deploy

Một service luôn có 20 pod hoạt động. Cứ 15 phút toàn bộ pod ID được thay bằng giá trị mới. Active series có thể ổn định nhưng vấn đề nào vẫn xảy ra?

**Lời giải:** **Churn cao**: xuất hiện nhiều series với pod ID mới rồi các series cũ biến mất. Bộ nhớ/chỉ mục, metadata và lưu trữ lịch sử có thể chịu tải dù số pod đồng thời vẫn là 20. Cần đo series xuất hiện/biến mất theo cửa sổ, không chỉ active series.

### Bài 8 — Hash có giảm cardinality?

Hệ thống thay `user_id="U123"` bằng `user_hash="e3ab..."` trong nhãn metric và giữ một hash khác nhau cho mỗi user. Số chuỗi có giảm đáng kể không?

**Lời giải:** Thường **không**: gần như mỗi user vẫn là một giá trị phân biệt. Hash cũng không mặc nhiên làm dữ liệu an toàn trước liên kết hoặc tái định danh. Cần bỏ nhãn ID khỏi metric tổng hợp và chuyển yêu cầu tra cứu chi tiết sang mô hình phù hợp.

### Bài 9 — Tối ưu scrape interval

Hệ thống có 50.000 active series ở chu kỳ 10 giây. Đổi thành 30 giây thì số mẫu lý tưởng giảm bao nhiêu lần? Có chắc active series giảm ba lần?

**Lời giải:** Số mẫu lý tưởng giảm **3 lần** nếu các series và điều kiện thu thập giữ nguyên. Active series **không chắc** giảm: mỗi bộ nhãn có thể vẫn còn tồn tại. Cần kiểm soát cardinality riêng.

### Bài 10 — Tổng hợp counter có reset

Một nhóm muốn tạo metric tổng số request theo service từ các counter ở mức instance. Có nên cộng các giá trị counter thô của các instance trước rồi mới lấy tốc độ, bất chấp instance reset không?

**Lời giải:** Không nên mặc nhiên. Reset của từng counter có thể làm tổng thô đổi đột ngột và gây cách diễn giải sai. Với hệ như Prometheus, thường tính **`rate` của từng counter trước rồi `sum` theo service**. Cần kiểm thử khi instance xuất hiện, biến mất và reset.

### Bài 11 — Đếm chuỗi theo thời gian

Giờ 09 có các series `S1,S2,S3`. Giờ 10 có `S2,S3,S4`. Số active ở mỗi giờ, số xuất hiện so với giờ trước và số biến mất là bao nhiêu?

**Lời giải:** Mỗi giờ có **3 active series**. `S4` xuất hiện so với giờ trước (**1**); `S1` biến mất (**1**). Số active không đổi nhưng tập bộ nhãn đã thay. Chỉ số này không chứng minh `S4` chưa từng tồn tại trước giờ 09.

### Bài 12 — Nhãn tenant có nên cấm hoàn toàn?

Một nền tảng có 300 tenant, cần SLO riêng theo tenant. Nhóm định thêm `tenant_id` vào metric latency cho mọi endpoint/status/pod mà chưa dự báo số chuỗi. Quyết định đúng là gì?

**Lời giải:** Không kết luận “cấm mọi tenant label” hay “thêm ngay”. Phải xác nhận nhu cầu SLO từng tenant, số tenant hiện tại và dự báo tăng, bộ nhãn hiện có, số bucket histogram, churn, khả năng hạ tầng và chính sách phân quyền. Có thể cần một metric mức tenant được tổng hợp, một hệ phân tích chuyên dụng hoặc phân tầng retention; lựa chọn dựa trên ngân sách và kiểm chứng.

## 17. Checklist trước khi thêm nhãn vào metric

- [ ] Đã xác định **câu hỏi vận hành/nghiệp vụ** thực sự cần nhãn này.
- [ ] Đã phân biệt **metric series**, **sample** và **sự kiện cá biệt**.
- [ ] Đã định nghĩa **metric name + labelset** là nhận diện chuỗi.
- [ ] Đã thống kê số giá trị dự kiến của từng nhãn, bao gồm sự tăng trưởng theo thời gian.
- [ ] Đã tính **giới hạn trên tổ hợp** và không nhầm nó với số thực tế.
- [ ] Đã đo **distinct labelsets** theo metric và active window thay vì chỉ nhân các `COUNT(DISTINCT)` riêng lẻ.
- [ ] Đã xem xét **churn** của pod, instance, session hoặc nhãn ngắn tuổi.
- [ ] Không đưa request ID, trace ID, user ID, URL thô hoặc timestamp vào nhãn tổng hợp vô hạn.
- [ ] Route, status, error type có **danh mục/chuẩn hóa hữu hạn**, có chính sách giá trị lạ.
- [ ] Đã tính số chuỗi phụ do histogram bucket, sum/count và các metric family liên quan.
- [ ] Đã dự báo tác động đến **active series, sample rate, RAM, index, disk, query latency**.
- [ ] Đã ghi ngân sách và người sở hữu metric, có kiểm tra khi bổ sung label hoặc deploy mới.
- [ ] Nếu bỏ nhãn/tổng hợp, đã định nghĩa **cách xử lý counter reset, gauge, histogram** và xung đột bộ nhãn.
- [ ] Không dùng hash, `topk` hoặc thay đổi scrape interval như giải pháp thay thế cho thiết kế nhãn.
- [ ] Đã giữ đường truy vết chi tiết qua log, trace hoặc fact/event data với phân quyền và retention phù hợp.
- [ ] Đã kiểm thử trước/sau trên số liệu thật, cảnh báo và các KPI/SLO cần bảo toàn.

**Ghi nhớ:** **Một nhãn mới có thể nhân số chuỗi theo số giá trị của nó; nhiều nhãn hữu hạn khi kết hợp vẫn có thể bùng nổ cardinality**. Tích các số giá trị là giới hạn trên để dự báo, còn số chuỗi thực tế phải được đo qua **bộ nhãn phân biệt, active window và churn**. Giữ các nhãn cần thiết để quan sát, chuyển ID sự kiện chi tiết sang nơi phù hợp và kiểm tra chi phí lẫn ý nghĩa số liệu trước khi triển khai.
