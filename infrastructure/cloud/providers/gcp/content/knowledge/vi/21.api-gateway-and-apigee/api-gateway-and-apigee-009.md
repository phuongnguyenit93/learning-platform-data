# Apigee analytics và quan sát hoạt động API

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Apigee API Analytics**, **API Monitoring**, **Cloud Monitoring**, **Cloud Logging** và **Debug** theo mục đích, độ trễ và phạm vi dữ liệu.
2. Đọc các chỉ số lưu lượng, lỗi, độ trễ và hiệu năng target; sử dụng **metric**, **dimension**, **filter** và **aggregation** mà không suy diễn sai số liệu.
3. Dùng dashboard, **custom report** và **Apigee Metrics API** để điều tra một API proxy; hiểu cơ chế thu thập dữ liệu tùy chỉnh bằng **DataCapture**.
4. Thiết lập các nguyên tắc cảnh báo theo **error rate, latency, traffic và fault source**, liên kết điều tra với ứng dụng Java trên Cloud Run/GKE.
5. Thiết kế xuất dữ liệu sang Cloud Storage/BigQuery, bảo vệ dữ liệu cá nhân và kiểm soát IAM, chi phí, thời gian lưu giữ.
6. Thực hành một quy trình phát hiện–khoanh vùng–khắc phục sự cố API, có bài tập và đáp án.

## 1. Bối cảnh: API chạy được chưa đủ, phải quan sát được

Giả sử hệ thống thương mại điện tử đưa Java **orders-api** trên Cloud Run ra Internet qua một **Apigee API proxy**. Proxy kiểm tra API key/OAuth token, áp **Quota**, **SpikeArrest**, chuyển request tới backend và trả kết quả về client.

Một buổi tối, tỷ lệ HTTP 5xx tăng; đồng thời độ trễ p95 vượt SLO. Nhóm vận hành cần biết:

- API nào, **environment** nào, phiên bản **proxy revision** nào bị ảnh hưởng?
- Lỗi do **policy tại gateway**, kết nối tới **target**, hay lỗi xử lý bên trong Java service?
- Bao nhiêu requests bị ảnh hưởng và xảy ra từ lúc nào?
- Tình trạng có liên quan một developer app/API product, một region hoặc một đợt phát hành không?
- Cần cảnh báo, rollback proxy hay backend, và chứng minh dịch vụ đã phục hồi bằng chỉ số nào?

Trong mô-đun **CLOUD_PROVIDERS_GCP**, Apigee kết nối kiến thức project, IAM/VPC, Cloud Run/GKE/Compute Engine, Cloud SQL, logging và chi phí. Bài này tập trung vào **quan sát vòng đời API** và vận hành, không đi sâu vào cách tạo proxy hoặc bảo mật OAuth từ đầu.

~~~mermaid
flowchart LR
    C["Client / mobile app"] --> G["Apigee API proxy<br/>VerifyAPIKey, Quota, routing"]
    G --> B["Java orders-api<br/>Cloud Run / GKE"]
    B --> DB["Cloud SQL"]
    G --> A["Apigee API Analytics<br/>báo cáo và xu hướng"]
    G --> M["API Monitoring<br/>lỗi / độ trễ gần real-time"]
    G --> L["Access logs / Debug<br/>bằng chứng giao dịch"]
    B --> O["Cloud Logging + Monitoring<br/>backend metrics, traces"]
    A --> R["Operations / product team"]
    M --> R
    L --> R
    O --> R
~~~

**Điểm cốt lõi:** Apigee nhìn được **đường đi qua proxy**, nhưng không tự giải thích đầy đủ JVM heap, truy vấn SQL, hàng đợi Pub/Sub hay độ trễ bên trong Cloud Run/GKE. Muốn chẩn đoán tận gốc cần kết hợp telemetry ở cả **gateway và backend**.

## 2. Năm công cụ quan sát khác nhau

| Công cụ | Câu hỏi trả lời tốt nhất | Dạng dữ liệu | Lưu ý |
|---|---|---|---|
| **Apigee API Analytics** | Lưu lượng, developer/API product, proxy performance biến đổi thế nào theo ngày/tuần? | Metrics tổng hợp, dimensions, dashboards, reports | Có độ trễ xử lý; không phải log từng request |
| **Apigee API Monitoring** | Proxy nào đang phát sinh lỗi, fault code nào tăng, ở region nào? | Gần thời gian thực, Timeline/Investigate/Recent, alert integration | Phù hợp điều tra vận hành; dữ liệu có thể lệch Analytics |
| **Cloud Monitoring** | Khi nào cần cảnh báo/on-call? Có vượt SLO không? | Time series, alerting policies, incident, notification channels | Metrics/nhãn được hỗ trợ theo phiên bản và loại Apigee |
| **Cloud Logging / access logs** | Request lỗi cụ thể xảy ra khi nào, mã trạng thái/fault là gì? | Log events | Cần bật, quản lý quyền, retention, chi phí và lọc PII |
| **Apigee Debug** | Một policy/flow variable đã làm gì trên một request thử nghiệm? | Trace/session cho request được chọn | Chỉ dùng có kiểm soát; không thay thế analytics lịch sử |

**Analytics và API Monitoring không dùng chung một pipeline dữ liệu.** Số liệu có thể khác nhau do tốc độ cập nhật, aggregation, sampling/bucketing, scope và thời gian lưu giữ. Không ép số request từ hai giao diện khớp tuyệt đối trong cùng một phút.

### 2.1. Dữ liệu đến muộn và retention

Theo tài liệu hiện hành, sau request qua proxy, **API Analytics có thể cần đến 10 phút** trước khi số liệu xuất hiện trong dashboards, custom reports hay Metrics API. **API Monitoring** hướng tới tín hiệu gần thời gian thực nhưng không hứa mọi sự kiện đều lập tức nhìn thấy.

**Thời hạn lưu giữ phụ thuộc loại telemetry, gói Apigee và add-on.** Analytics docs nêu khả năng xem dữ liệu đến **14 tháng** với những entitlement hỗ trợ; một số gói/đường quan sát có hạn ngắn hơn. API Monitoring metrics có cửa sổ khác; dữ liệu monitoring logs có query parameters/user agents và được Google quản lý theo chính sách lưu giữ riêng (tài liệu nêu **6 tuần** với loại log này). Khi thiết kế lưu trữ dài hạn, **đối chiếu entitlement/retention thực tế** và lên kế hoạch export.

Trên **Apigee Pay-as-you-go**, tính năng API Analytics/custom reports có thể yêu cầu bật **Apigee API Analytics add-on** cho environment phù hợp và phát sinh phí; gói Subscription có entitlement khác. Không mặc định mọi tổ chức đã có đầy đủ dashboards/exports.

## 3. Tư duy metric, dimension, filter và time window

Một báo cáo analytics trả lời: **đo cái gì**, **nhóm theo tiêu chí nào**, **lọc dữ liệu nào**, **trong khoảng thời gian nào**?

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| **Metric** | message_count, total_response_time, policy_error | Giá trị định lượng |
| **Aggregation** | sum(message_count), avg(total_response_time) | Cách gộp số liệu |
| **Dimension** | apiproxy, response_status_code, developer_app | Cách chia nhóm |
| **Filter** | apiproxy = orders-v1; response_status_code >= 500 | Thu hẹp tập request |
| **Time range/unit** | 2 giờ gần đây, nhóm mỗi 5 phút | Cửa sổ và độ phân giải |

### 3.1. Các metric thường dùng

| Tên API metric | Phép tổng hợp phổ biến | Dùng để |
|---|---|---|
| **message_count** | sum | Đếm API proxy calls |
| **tps** | Giá trị TPS do hệ thống cung cấp | Giao dịch mỗi giây |
| **is_error** | sum | Lần proxy xử lý thất bại; **không đồng nhất mọi HTTP 4xx** |
| **policy_error** | sum | Lỗi policy **khi làm proxy thất bại** |
| **target_error** | sum | Lỗi từ backend target |
| **total_response_time** | avg/min/max hoặc percentile theo API hỗ trợ | Tổng thời gian proxy nhận request tới lúc gửi response |
| **target_response_time** | avg/min/max hoặc percentile | Thời gian chờ phản hồi của target |
| **request_processing_latency** | avg/min/max | Thời gian Apigee xử lý request trước khi gửi target |
| **response_processing_latency** | avg/min/max | Thời gian Apigee xử lý response trước khi trả client |
| **cache_hit** | sum | Số lần ResponseCache hit, khi cấu hình sử dụng cache |

Tài liệu Apigee chỉ hỗ trợ **một tập hàm aggregation cho mỗi metric**, không thể áp mọi phép toán cho mọi trường. Khi cần p95/p99 hãy dùng **Latency Analysis dashboard** hoặc cú pháp percentile của Metrics API đã được hỗ trợ; **không suy p95 từ avg**.

### 3.2. Dimension quan trọng

| Dimension/API field | Câu hỏi |
|---|---|
| **apiproxy** | Proxy nào chậm/lỗi nhất? |
| **environment** | prod khác test ra sao? |
| **api_product** | API product nào bị ảnh hưởng? |
| **developer_app**, **developer_email** | App/developer nào làm traffic tăng? |
| **response_status_code** | Client nhận 200, 401, 429, 500, 503 với tỷ lệ bao nhiêu? |
| **target_response_code** | Backend trả gì **trước khi** Apigee có thể đổi status? |
| **request_verb** | GET/POST/PUT khác nhau thế nào? |
| **target_url**, **target_host** | Backend/upstream nào tạo lỗi? |
| **ax_execution_fault_policy_name** | Chính sách nào làm flow thất bại? |
| **gateway_flow_id** | Hỗ trợ phân biệt transaction khi đối chiếu dữ liệu |

**Không nhầm response_status_code với target_response_code:** Apigee có thể chặn request ngay tại VerifyAPIKey (chưa gọi target) hoặc dùng RaiseFault/AssignMessage đổi mã status. Khi đó target_response_code có thể không có, hoặc khác status trả khách hàng.

### 3.3. Công thức SLI và những lỗi tính toán

Với SLO giả định **99,9% requests hợp lệ không bị lỗi server**, cần định nghĩa rõ mẫu số và loại lỗi:

\[
\text{Server error rate} = \frac{\text{số request có HTTP 5xx}}{\text{tổng request trong phạm vi đo}} \times 100\%.
\]

\[
\text{Availability SLI} = 1-\frac{\text{số request lỗi thuộc error budget}}{\text{tổng request hợp lệ}}.
\]

Ví dụ **100.000 requests**, trong đó **140 HTTP 5xx**: tỷ lệ 5xx là **0,14%** và availability theo định nghĩa đơn giản là **99,86%**; cao hơn error budget **0,10%**. Đây là số giả định để luyện tính, không phải kết quả đo thật.

**Lưu ý:** 401 do API key không hợp lệ, 429 do Quota/SpikeArrest và 404 do business logic có thể hoặc không được tính vào SLO, tùy **hợp đồng dịch vụ**. Metric **sum(is_error)** không tự tương đương với “tổng số 5xx”. Muốn đếm mã 5xx hãy lọc/group theo **response_status_code** và làm rõ requests do client tạo ra so với backend/proxy failures.

## 4. Phân tích latency để tìm đúng điểm nghẽn

Dashboard **Latency Analysis** hiển thị **median (p50)**, **p95**, **p99** và các loại latency tại proxy/target.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Apigee
    participant T as Target Java API
    C->>P: HTTP request
    Note over P: Request processing latency
    P->>T: Forward request
    Note over P,T: Target response time
    T-->>P: Target response
    Note over P: Response processing latency
    P-->>C: Client response
~~~

| Chỉ số | Bắt đầu/kết thúc | Gợi ý chẩn đoán |
|---|---|---|
| **Total response time** | Apigee nhận request → trả response | SLI nhìn từ gateway, gồm target và overhead |
| **Target response time** | Apigee gửi tới target → nhận phản hồi | Backend Java, SQL, network tới target |
| **Request processing latency** | Nhận request → gửi tới target | Policies, request transformations, auth, quota |
| **Response processing latency** | Nhận phản hồi target → gửi client | Response transformations, policies, serialization/cache |

Với requests thật sự đi đến target, tổng response time thường gồm các phần target + gateway overhead; **không lấy phép cộng trung bình từ những tập request khác nhau để khẳng định nguyên nhân**. Với cache hit, request **không đến target** nên **không có target response time** cho transaction đó.

### Ví dụ đọc p95 và p99

- p50 = **65 ms**, p95 = **350 ms**, p99 = **1.800 ms**.
- Target response time p99 cũng tăng từ **200 ms** lên **1.600 ms**.
- Request/response processing ở Apigee gần như không đổi.

**Giả thuyết hợp lý:** backend hoặc kết nối tới target bị chậm; kiểm tra **Cloud Run/GKE latency, JVM GC, Cloud SQL query time, connection pool**. **Chưa đủ để kết luận** DB gây lỗi nếu thiếu traces/logs.

Ngược lại, nếu target latency ổn định nhưng request processing latency tăng sau khi thêm một policy, điều tra policy/flow tại gateway. Chỉ số p99 nhạy với phần đuôi; **không dùng average để che vấn đề của 1% requests chậm nhất**.

## 5. Sử dụng các dashboard Analytics có sẵn

Trong Google Cloud console, mở **Apigee → Analytics → API metrics**, rồi chọn environment, thời gian và proxy cần phân tích.

| Dashboard | Dùng khi | Câu hỏi cần trả lời |
|---|---|---|
| **API Proxy Performance** | Traffic/TPS biến đổi | Proxy nào tăng đột ngột, version/revision liên quan? |
| **Error Code Analysis** | 4xx/5xx tăng | Status code và fault nào nổi bật? |
| **Latency Analysis** | SLA/p95 xấu | Proxy hay target chiếm thời gian? |
| **Cache Performance** | Cache hit rate giảm | Có nhiều requests hơn đi tới backend? |
| **Target Performance** | Chậm ở upstream | Target URL/host nào có latency/error lớn? |

### Quy trình điều tra trong 5 bước

1. Chọn **đúng Apigee organization/environment**, múi giờ, cửa sổ thời gian; ghi lại chúng trong incident.
2. Từ API Proxy Performance, tìm **proxy có TPS/error thay đổi**.
3. Qua Error Code Analysis, phân loại **response_status_code** và **target_response_code**; xác định lỗi do gateway hay backend.
4. Qua Latency Analysis và Target Performance, so **p95/p99 của total và target** với baseline.
5. Chuyển sang **API Monitoring → Investigate**, Cloud Logging hoặc backend traces để xác nhận giả thuyết bằng request evidence.

**Không xem dashboard của 5 phút hiện tại là bức tranh đầy đủ**, vì Analytics có thể trễ đến 10 phút. Khi đang ứng cứu, ưu tiên API Monitoring/Cloud Monitoring và logs; dùng Analytics để xác nhận xu hướng sau khi dữ liệu đã ổn định.

## 6. Custom reports: metric × dimension × filter

Khi dashboard chuẩn không trả lời đúng câu hỏi, vào **Apigee → Analytics → Custom reports**. Một report xác định metric, aggregation, dimension, filter và time range; có thể chọn line/column chart.

### 6.1. Bài thực hành A — Lỗi theo proxy và status

**Mục tiêu:** xác định proxy nào có nhiều lỗi trong environment **prod** hôm qua.

Trong giao diện **Custom reports → Create**:

1. Đặt tên **Orders proxy errors – daily**.
2. Chọn metric **Proxy errors (sum)** và **Traffic (sum)** nếu được phép kết hợp trong report.
3. Chọn dimension **API Proxy**; nếu cần thêm, chọn **Response Status Code**.
4. Lọc **API Proxy = orders-v1** hoặc nhóm proxies liên quan, environment **prod**.
5. Chọn cửa sổ **ngày hôm qua (UTC hoặc timezone được UI hiển thị)**, chart type line/column, rồi lưu/chạy.
6. Xem danh sách status và total requests cùng khoảng đo; **không chia error count của một proxy cho total của toàn environment**.

Nếu cần **tỷ lệ 5xx thực sự**, dùng bộ lọc **response_status_code từ 500 đến 599** và tính dựa trên tổng request cùng scope. **Proxy errors** bao gồm một số lỗi không khớp hoàn toàn 5xx, nên phân biệt metric và status.

### 6.2. Real-time report và report job

| Loại | Tác dụng | Giới hạn/lưu ý |
|---|---|---|
| **Real-time custom report** | Xem trong UI, kết quả thường hiển thị sau vài phút | Cửa sổ giao diện tối đa **92 ngày** theo tài liệu |
| **Asynchronous report job** | Tạo job rồi lấy kết quả khi hoàn thành | Có giới hạn **365 ngày** và kết quả tối đa **32 MB** theo tài liệu |
| **Metrics API** | Tích hợp báo cáo vào script/ứng dụng | Cần quyền, range đúng, phân trang/lọc |
| **Export Analytics** | Lưu dữ liệu vào Cloud Storage/BigQuery | Hệ thống riêng, **asynchronous** và phụ thuộc add-on/entitlement |

Không nhầm “real-time custom report” với API Monitoring. Tên **real-time** ở đây nói về cách tạo/trả report đồng bộ, **không có nghĩa dữ liệu Analytics không bị trễ**.

### 6.3. Chống mất thông tin khi nhóm sai

Ví dụ report *average target latency* theo **API Proxy** có thể che việc chỉ **một target host** chậm. Hãy so cùng metric với dimension **target_url** và filter **response_status_code >= 500**. Với TPS tăng đột biến, nhóm thêm **developer_app** để xác định một client có tăng traffic hay tất cả cùng tăng.

**Tránh high cardinality** như request ID, raw URL có user ID hay session token làm dimension. Vừa khó phân tích, vừa tạo rủi ro PII và tăng tải lưu trữ/query.

## 7. DataCapture: thu thập dimension nghiệp vụ tùy chỉnh

Metrics mặc định không nhất thiết có **client tier** (bronze/silver/gold) hoặc mã kênh bán hàng. **DataCapture policy** cho phép lưu một **giá trị chọn lọc** từ proxy flow variables vào Analytics; đó là **Extensible policy**, có thể ảnh hưởng entitlement/cost.

### 7.1. Hai bước bắt buộc

1. Tạo **Data Collector resource** ở cấp Apigee organization với một kiểu dữ liệu và tên bắt đầu bằng **dc_**.
2. Thêm **DataCapture policy** vào một flow của API proxy để gắn collector với một **flow variable** đã được validate/mapped.

Ví dụ: backend/VerifyAPIKey flow thiết lập biến **client.tier.analytics** chỉ nhận một trong **bronze, silver, gold, unknown**. **Không** thu thập raw Authorization header, API key, số thẻ, email hoặc toàn bộ request body để dễ thống kê.

### 7.2. Tạo Data Collector

Giả định **APIGEE_ORG=shop-apigee-dev** là organization có thật và người thao tác có quyền tạo Data Collector. Lệnh dưới chỉ để lab có phép; trên một organization đang dùng chung, việc thêm resource có thể ảnh hưởng analytics schema.

~~~bash
export APIGEE_ORG="shop-apigee-dev"
ACCESS_TOKEN="$(gcloud auth print-access-token)"

curl --fail-with-body -sS \
  -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/datacollectors" \
  -d '{
    "name": "dc_client_tier",
    "description": "Low-cardinality subscription tier",
    "type": "STRING"
  }'
~~~

**Không chạy nếu collector đã tồn tại**; kiểm tra trước bằng UI/API. Tên bắt đầu với **dc_**; không tạo hai collector chỉ khác nhau chữ hoa/thường. Không in biến **ACCESS_TOKEN**, không lưu nó vào source. Dòng `--fail-with-body` cần phiên bản curl tương thích; nếu curl cũ, có thể dùng `-f -sS` và đối chiếu HTTP status.

### 7.3. DataCapture policy XML

Trong bundle API proxy, tạo policy XML **DC-ClientTier.xml** và gắn vào **đúng flow step**, sau khi biến đã được gán:

~~~xml
<DataCapture name="DC-ClientTier" continueOnError="true" enabled="true">
  <Capture>
    <DataCollector>dc_client_tier</DataCollector>
    <Collect ref="client.tier.analytics" />
  </Capture>
</DataCapture>
~~~

**Quan trọng:**

- Biến **client.tier.analytics** **không tự tồn tại**: tạo bằng ExtractVariables/AssignMessage/JavaScript policy được kiểm soát trước step DataCapture.
- `continueOnError="true"` là lựa chọn minh họa để lỗi quan sát không làm request nghiệp vụ thất bại; với nghiệp vụ cần thu thập bắt buộc, chọn policy và error handling khác theo thiết kế.
- Một policy có thể có nhiều **Capture** nhưng mỗi **DataCollector** trong cùng policy phải khác nhau.
- Không thu thập dữ liệu nhạy cảm/high cardinality; tuân thủ privacy, retention, data residency và phân quyền.
- Sau deploy một proxy revision mới, **đợi dữ liệu Analytics đến** rồi kiểm tra custom report theo `dc_client_tier`. Tên hiển thị trong UI/API có thể phụ thuộc resource/data collector configuration.

**Bẫy:** DataCapture không thay thế transaction logs hoặc distributed tracing. Nó thu thập **trường được chọn** để tổng hợp, không nên dùng để lưu nguyên payload của mọi request.

## 8. API Monitoring: phát hiện và khoanh vùng sự cố

Trong Apigee console, đi tới **Proxy Development → API monitoring**. Ba góc nhìn hữu ích:

| View | Khi sử dụng | Cách đọc |
|---|---|---|
| **Timeline** | Sự cố bắt đầu khi nào? | So thời gian tăng lỗi/latency với deploy hoặc traffic spike |
| **Investigate** | Proxy, fault code, region, status nào bị ảnh hưởng? | Drill down theo dimension và fault source |
| **Recent** | API nào nổi bật gần đây? | Treemap biểu diễn khối lượng traffic và mức độ bất thường |

### 8.1. Phân biệt nơi phát sinh lỗi

| Dấu hiệu | Giả thuyết đầu tiên | Kiểm chứng tiếp |
|---|---|---|
| `VerifyAPIKey` / `InvalidApiKey`, 401/403 | Client gửi key thiếu/sai/hết quyền | API product, developer app, VerifyAPIKey policy logs |
| `SpikeArrest` hoặc `QuotaViolation`, thường 429 | Traffic vượt giới hạn policy | Client identity, policy thresholds, spike baseline |
| Fault `TargetEndpoint` timeout / 503 | Kết nối/backend/network có vấn đề | Target host, Cloud Run/GKE readiness, VPC, upstream errors |
| **target_error** tăng, target response_code 500/503 | Java backend trả lỗi | Java logs, dependency traces, Cloud SQL |
| **policy_error** tăng sau deploy proxy revision | Một policy mới hoặc cấu hình sai | Diff proxy revision, Debug trong môi trường an toàn |

Mã lỗi/fault code cụ thể phụ thuộc policy và flow thực tế, không phải mọi 429 đều do SpikeArrest. Ví dụ có thể bị **backend rate limiter** trả 429 hoặc Apigee Quota policy tạo 429. Cần nhìn **fault source và target_response_code**, không suy từ status đơn lẻ.

### 8.2. Cảnh báo qua Cloud Monitoring

**API Monitoring tích hợp với Cloud Monitoring alerting**, trong đó có:

- **Metric-based alerts:** request/response counts, HTTP 500/503, latency percentile hoặc fault count vượt ngưỡng trong cửa sổ đo.
- **Log-based alerts:** khi một sự kiện/fault pattern cụ thể xuất hiện trong Cloud Logging.

Tạo qua **Monitoring → Alerting → Policies → Create policy**, không phải nút riêng trong API Monitoring Timeline. Người tạo cần quyền như **roles/monitoring.alertPolicyEditor**; quản lý notification channel cần **roles/monitoring.notificationChannelEditor**. Người chỉ xem API Monitoring thường cần **roles/apigee.readOnlyAdmin** và **roles/monitoring.viewer**.

Với Apigee và Apigee hybrid **v1.12+**, tài liệu khuyến nghị dùng bộ metrics mới như:

~~~text
apigee.googleapis.com/proxy/request_count
apigee.googleapis.com/proxy/response_count
apigee.googleapis.com/proxyv2/latencies_percentile
~~~

Những metrics và labels được phép lọc phụ thuộc phiên bản/môi trường. Có thể phân nhóm theo **env, location, proxy_name, method, response_code, fault_code, fault_source** hoặc percentile khi metric hỗ trợ; xem **Metrics Explorer** trước khi tạo policy.

### 8.3. Ví dụ thiết kế alert — không phải ngưỡng mặc định của Google

| SLI | Điều kiện minh họa | Hành động |
|---|---|---|
| **5xx rate** | Trên **2%** trong **5 phút**, đồng thời tối thiểu 100 requests | Page on-call, xem Error Code Analysis và target health |
| **Latency p95** | Trên **800 ms** liên tiếp **10 phút** | So target vs proxy latency, DB latency |
| **429 rate** | Tăng gấp **3 lần baseline**, loại bỏ nhóm load test | Xem SpikeArrest/Quota và traffic nguồn |
| **Throughput drop** | Giảm **70%** so cùng giờ điển hình | Kiểm tra network, client errors, DNS, rollout |

Đây là **số giả định cho bài học**, không phải SLO phù hợp mọi API. Với 10 requests/5 phút, 2% rất nhiễu; phải đặt điều kiện **minimum traffic** hoặc multi-window burn-rate. Cần **notification channels đã kiểm thử**, owner/on-call rotation, severity và runbook links; tránh alert fatigue.

**Cảnh báo không tự sửa sự cố:** một incident đưa team đến API Monitoring, sau đó xác nhận bằng logs/target telemetry rồi rollback hoặc fix nếu được phép.

## 9. Bài thực hành B — Gọi Apigee Metrics API

**Mục tiêu:** lấy **request count**, **proxy failures** và **target latency** theo API proxy mà không cần tạo dashboard mới. Đây là API quản lý **Apigee**, không phải URL client gọi business API.

### 9.1. Chuẩn bị

Bạn cần organization Apigee hoạt động, environment **test** có traffic, quyền đọc Analytics phù hợp và một tài khoản gcloud đã đăng nhập. Tên dưới đây chỉ minh họa; thay bằng giá trị thật:

~~~bash
export APIGEE_ORG="shop-apigee-dev"
export APIGEE_ENV="test"
ACCESS_TOKEN="$(gcloud auth print-access-token)"
~~~

**Không commit hoặc in access token**; tài khoản cần quyền tương ứng với Apigee analytics. Nếu dữ liệu rỗng, kiểm tra environment, thời gian UTC, entitlement/add-on và delay 10 phút trước khi kết luận API hỏng.

### 9.2. Lấy số request theo proxy trong hai ngày

~~~bash
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/apiproxy?select=sum(message_count)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&timeUnit=day"
~~~

**Cú pháp:**

- **/stats/apiproxy** nhóm theo dimension **apiproxy**. Bỏ **/apiproxy** để xem thống kê environment-level.
- **select=sum(message_count)** lấy số lượng proxy calls.
- **timeRange** theo dạng **MM/DD/YYYY HH:MM~MM/DD/YYYY HH:MM** với khoảng trắng URL-encoded thành **%20**; đây chỉ là cửa sổ ví dụ.
- **timeUnit=day** nhóm theo ngày; cần cân nhắc time zone của biểu đồ và phạm vi thời gian.

Đầu ra là JSON có **environments**, **dimensions** và **metrics**; số có thể nằm trong chuỗi số thực. Không cộng hai tổng của hai dimensions không tương thích hoặc lấy trung bình của các giá trị trung bình khi không có trọng số.

### 9.3. Lấy proxy errors và target latency

~~~bash
# Proxy failures (không đồng nghĩa mọi response code 5xx)
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/apiproxy?select=sum(is_error)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&timeUnit=day"

# Average target response time tính theo target URL
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/target_url?select=avg(target_response_time)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&timeUnit=day"
~~~

**Đọc kết quả đúng:** nếu request bị Apigee chặn trước khi đến target, **target_response_time** có thể không được ghi. Không lấy tổng toàn bộ requests chia cho số target calls của một nhóm sai.

### 9.4. Phân tích mã 5xx theo proxy

~~~bash
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/apiproxy?select=sum(message_count)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&filter=(response_status_code%20ge%20500%20and%20response_status_code%20le%20599)"
~~~

Khi filter bằng **response_status_code**, đây là số proxy calls có mã status trong khoảng 500–599 trả về client, khác với **sum(is_error)**. Nếu cần **5xx ratio**, gọi thêm request **không có filter** cùng environment/timeRange/dimension rồi chia theo từng proxy.

### 9.5. Metrics API không thay thế incident metrics

Metrics API có giới hạn **timeRange tối đa khoảng 6 tháng mỗi truy vấn** theo tài liệu; nếu cần lịch sử lâu hơn hãy dùng export hoặc chia truy vấn. Hỗ trợ **sortby, topk, limit, offset**, nhưng cần sắp xếp ổn định khi phân trang. Nếu tổ chức Pay-as-you-go chưa bật **API Analytics add-on**, truy vấn có thể bị từ chối dù proxy vẫn xử lý requests.

Đối với cảnh báo sản xuất theo phút, nên dùng **Cloud Monitoring metrics** thay vì gọi Analytics API mỗi vài giây — vì ingestion delay, quota và mô hình dữ liệu khác nhau.

## 10. Đối chiếu Apigee với backend Java, Cloud Logging và Debug

### 10.1. Correlation ID xuyên qua nhiều hệ thống

Một HTTP request có thể đi qua **load balancer → Apigee → Cloud Run/GKE → Cloud SQL**. Nên có **correlation ID** an toàn được chuyển cùng request và trả trong telemetry.

~~~text
Client sends request
  ↓
Apigee: request_id = 5b0f... (generated or validated)
  ↓ header: X-Request-ID
Java orders-api: logs request_id + duration + operation
  ↓
Cloud Logging: filter request_id and service
  ↓
Trace backend/SQL to isolate high latency
~~~

Nếu client tự gửi **X-Request-ID**, proxy/backend phải **validate** định dạng và length, không tin tuyệt đối. Tránh đưa API key, email, token, số đơn hàng thật vào ID dùng trong logs. Với distributed tracing chuẩn, ưu tiên **W3C traceparent** theo cơ chế tracing đã cấu hình.

### 10.2. Java/Spring Boot: structured log an toàn

Ví dụ interceptor đơn giản chỉ minh họa cách đọc/gắn ID — **không phải mã tracing hoàn chỉnh**:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public final class CorrelationInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(HttpServletRequest req,
                             HttpServletResponse res,
                             Object handler) {
        String id = req.getHeader("X-Request-ID");
        if (id == null || !id.matches("[A-Za-z0-9_-]{8,64}")) {
            id = UUID.randomUUID().toString();
        }
        req.setAttribute("correlationId", id);
        res.setHeader("X-Request-ID", id);
        return true;
    }
}
~~~

**Lưu ý:** cần **đăng ký interceptor** trong Spring MVC để nó thực sự chạy, ví dụ qua **WebMvcConfigurer.addInterceptors**. Tracing/correlation phải được kiểm thử trên request path thực. Không log raw Authorization/Cookie headers hoặc full payload; chỉ log **method, route template, status, duration, proxy/backend release version, safe correlation ID**.

### 10.3. Debug và access logs

**Apigee Debug** phù hợp khi đã cô lập lỗi ở một proxy policy: chọn đúng environment/proxy, tạo session có thời hạn và gửi **request thử nghiệm không chứa PII** để xem flow variables, policy execution, target call.

**Apigee access logs** ghi thông tin transaction tại ingress và giúp điều tra các tình huống đặc biệt mà metrics tổng hợp không giải thích được, như response code **0** ở ingress. Kiểm tra Logging/IAM/retention trước khi trích xuất logs ra hệ thống ngoài.

Không bật cơ chế ghi toàn payload cho mọi request production chỉ vì gặp một lỗi hiếm: tốn chi phí, tăng độ trễ/volume và có thể vi phạm quy tắc bảo mật thông tin.

### 10.4. Cách dùng đúng các nguồn

| Nếu thấy | Điều tra tiếp ở đâu? |
|---|---|
| **Policy error** tăng sau một proxy revision | Diff policy, Apigee Debug và proxy deployment history |
| **Target error** tăng với target response_code=503 | Cloud Run/GKE service logs, readiness, resource quotas |
| **Target latency** tăng, proxy overhead không tăng | Backend traces, JVM GC, Cloud SQL query statistics |
| **No target response code**, 401/429 ở proxy | VerifyAPIKey/OAuth, Quota/SpikeArrest, API product/app |
| **HTTP 200 từ proxy** nhưng UI báo sai dữ liệu | Business logs/traces, validation, response transformations |

**Không giả định Cloud Trace tạo end-to-end trace tự động** chỉ vì bật Apigee Analytics. Phải cấu hình truyền trace context/SDK/telemetry đúng trong proxy và backend theo kiến trúc.

## 11. Xuất Analytics sang Cloud Storage hoặc BigQuery

**Export** thích hợp khi cần lưu lịch sử dài hạn, kết hợp API usage với chi phí/doanh thu hoặc phân tích theo SQL. Nó **không phải** realtime streaming logs. Theo tài liệu, export hỗ trợ **CSV** và **newline-delimited JSON** tới **Cloud Storage** hoặc **BigQuery** thông qua một export job **asynchronous**.

### 11.1. Quy trình tổng quát

1. Chọn dataset/bucket đích và **data location** phù hợp với Analytics region và quy định residency.
2. Bật APIs cần thiết, cấp quyền cho **Apigee service agent** ghi vào đích; phân quyền theo tài nguyên cụ thể.
3. Tạo **analytics datastore** trong organization Apigee.
4. Gửi **export request** cho một environment và một ngày dữ liệu.
5. Theo dõi **state** đến khi completed; kiểm tra số records, schema, mã hóa, retention.
6. Kết hợp với dữ liệu khác trong BigQuery sau khi xóa/ẩn PII.

Với một số trường hợp Analytics ở US/EU, export BigQuery yêu cầu **dataset cùng multi-region US/EU**; muốn dataset region cụ thể, có thể cần export qua Cloud Storage rồi nạp vào BigQuery. **Không tự tạo dataset bất kỳ region** và mong export thành công.

### 11.2. Ví dụ API export — cần datastore đã cấu hình

Đây là ví dụ curl cho organization và environment đã có datastore **Analytics-BQ-Dev**:

~~~bash
ACCESS_TOKEN="$(gcloud auth print-access-token)"
curl -f -sS -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/analytics/exports" \
  -d '{
    "name": "Daily API analytics export for lab",
    "description": "Export one UTC day of data",
    "dateRange": {
      "start": "2026-11-17",
      "end": "2026-11-18"
    },
    "outputFormat": "json",
    "datastoreName": "Analytics-BQ-Dev"
  }'
~~~

**Chú ý:**

- **dateRange chỉ được trải một ngày** theo API export và sử dụng mốc UTC. `end` là mốc bắt đầu ngày kế tiếp.
- Phản hồi ban đầu có thể có **state=enqueued**; **không** phải đã xuất xong. Dùng **self** URL để lấy trạng thái hoặc list exports.
- Export API có quota, tài liệu nêu **500 calls/ngày/organization**; lỗi quota có thể trả **429**.
- Free/trial không hỗ trợ export; Pay-as-you-go cần add-on đủ điều kiện; IAM để tạo datastore/export khác quyền chỉ xem dashboard.
- JSON xuất ra chứa metrics/dimensions tùy config, **không tự động là bảng request-level access logs**.

### 11.3. Kiểm tra chất lượng sau export

| Kiểm tra | Tại sao quan trọng? |
|---|---|
| Đúng environment/time window | Tránh trộn test và production |
| Job completed, object/table tồn tại | enqueued chưa nghĩa là dữ liệu đã ghi |
| Schema, record count và metric totals | Phát hiện missing/duplicate hoặc dữ liệu đến trễ |
| Partition/retention/permissions | Không giữ PII vô hạn, không mở bucket/dataset công khai |
| Encryption và location | Tuân thủ security/data residency |
| BigQuery query costs | Tránh full-scan lịch sử dài trên bảng lớn |

Không xuất request headers, cookies hoặc full payload nếu không có mục đích hợp pháp và quy trình bảo mật; **DataCapture** và access logs có thể làm tăng nhạy cảm của dữ liệu được lưu.

## 12. Bảo mật, IAM, độ tin cậy và chi phí quan sát

### 12.1. Phân quyền theo nhiệm vụ

| Nhóm | Nhu cầu | Quyền và giới hạn cần xem |
|---|---|---|
| **API product analyst** | Xem lưu lượng, custom reports | Apigee Analytics Viewer/role đọc theo entitlement; không cấp quyền sửa proxy |
| **SRE/on-call** | Xem API Monitoring, Cloud Monitoring, logs | **roles/apigee.readOnlyAdmin**, **roles/monitoring.viewer**, Logging Viewer theo dữ liệu |
| **Alert operator** | Tạo/sửa alert, notification channels | **roles/monitoring.alertPolicyEditor**, **roles/monitoring.notificationChannelEditor** |
| **Proxy developer** | Sửa flow, DataCapture, deploy revision | Role Apigee developer/deployer phù hợp environment |
| **Data platform** | Export và quản lý BigQuery/GCS datastore | Apigee Analytics Editor/Org Admin khi bắt buộc, quyền data destination của service agent |
| **Security/auditor** | Điều tra thay đổi quyền và data access | Role audit/viewer có phạm vi, không cần thấy raw secret/payload |

Vai trò thực tế có thể khác theo Apigee organization/gói; **xem permissions chính thức** trước khi cấp. Không cấp **Apigee Organization Admin** cho mọi người chỉ vì họ cần xem dashboard. Apigee service agent khi export cần đúng quyền lên data destination; không nhầm nó với runtime service account của Java backend.

### 12.2. Nguy cơ dữ liệu cá nhân

- **Authorization**, **Cookie**, **Set-Cookie**, API keys, OAuth tokens và password: **không capture** vào custom dimensions/logs.
- **User-Agent, query string, client IP, developer email** có thể là dữ liệu cá nhân; áp dụng privacy review và retention phù hợp.
- Không dùng **raw customer ID** làm dimension tùy chỉnh có hàng triệu giá trị. Chỉ thu thập **nhóm định danh ít giá trị** như tier, API product hoặc channel được kiểm soát.
- Bật DataCapture trên proxy production sau khi review **sensitivity, masking, schema/cardinality, cost và access permissions**.
- Khi chia sẻ báo cáo ra ngoài đội vận hành, ưu tiên dữ liệu tổng hợp, ẩn danh; không gửi link truy cập raw logs qua kênh không được phê duyệt.

### 12.3. Chi phí và giới hạn

Theo mô hình thương mại, Apigee có thể tính phí theo **API calls**, môi trường, chính sách mở rộng, Analytics add-on, các tính năng nâng cao hoặc capacity. Bên cạnh đó:

| Thành phần | Rủi ro |
|---|---|
| **Analytics add-on / reports** | Không có entitlement thì bị giới hạn; report jobs có quota |
| **DataCapture** | Extensible policy có thể có chi phí/capacity riêng |
| **Cloud Monitoring alerting** | Từ **1/5/2026** Google bắt đầu tính phí alerting theo bảng giá hiện hành |
| **Cloud Logging** | Log volume, retention, queries/exports và truy cập dữ liệu |
| **Cloud Storage/BigQuery export** | Object storage, ingestion, BigQuery queries, transfer/egress |
| **Java backend** | Cloud Run/GKE, Cloud SQL, network khi request tăng |

Đặt **billing budgets** và review sử dụng theo environment/product. **Budget alert không tự dừng** proxy hoặc ngắt tài nguyên. Không đặt số giá cố định trong bài vì bảng giá, quotas và entitlements thay đổi.

### 12.4. Phạm vi sản phẩm: Apigee ≠ API Gateway

**Google Cloud API Gateway** và **Apigee** là hai sản phẩm quản lý API khác nhau. API Gateway phù hợp nhiều bài toán gateway đơn giản theo API config/OpenAPI, còn Apigee tập trung vào **API lifecycle, products/developers, policies, analytics và vận hành chuyên sâu**. Những dashboards, DataCapture và Metrics API ở bài này là **tính năng Apigee**; không sao chép đường dẫn, IAM roles hoặc API tương ứng sang API Gateway rồi giả định giống nhau.

## 13. Runbook sự cố: từ cảnh báo đến xác nhận phục hồi

Giả sử lúc **10:15 UTC**, alert báo **orders-v1 HTTP 5xx > 2% trong 5 phút**.

### Bước 1 — Xác minh scope

Xác định **Apigee org, environment, proxy, time window UTC, region và lượng traffic**. Tránh báo động vì environment **test** hoặc một đợt synthetic load không thuộc production.

### Bước 2 — Xác định gateway hay target

Trong **API Monitoring → Timeline/Investigate**, lọc proxy orders-v1, status 5xx và fault source:

- **Policy errors/flow fault** tăng: xem policy revision, VerifyAPIKey/Quota/JavaScript execution.
- **Target errors/target 503** tăng: kiểm tra Cloud Run/GKE backend.
- Không có target_response_code: có thể request bị chặn sớm, trả từ cache hoặc chưa đến target.

### Bước 3 — So độ trễ

Trong **Latency Analysis** so **total**, **target**, **request/response processing** theo baseline trước sự cố. Nếu target tăng mạnh nhưng proxy overhead gần như ổn, điều tra Java/database. Nếu gateway overhead tăng sau deploy policy, kiểm tra proxy revision.

### Bước 4 — Liên hệ release và log

Đối chiếu các mốc:

~~~text
10:08  Cloud Run revision orders-00042 được promote
10:11  Java logs: connection timeout bắt đầu tăng
10:15  Apigee target_error + HTTP 503 tăng
10:17  Cloud SQL connections chạm ngưỡng
~~~

Đây là **dòng thời gian giả định** để thực hành. Không coi quan hệ gần nhau về thời gian là bằng chứng nhân quả duy nhất; cần kiểm chứng với logs/traces/metrics cùng correlation ID.

### Bước 5 — Khắc phục có kiểm soát

Nếu sự cố do backend revision mới, **rollback traffic Cloud Run** sau khi kiểm tra schema/data compatibility. Nếu do proxy revision, rollback **proxy deployment** qua pipeline được duyệt. Nếu do Quota/SpikeArrest, không tăng rate limit tùy tiện khi chưa phân biệt legitimate traffic với abuse.

### Bước 6 — Xác nhận phục hồi

Theo dõi liên tục ít nhất một cửa sổ alert:

- 5xx và target errors về baseline.
- p95/p99 latency về trong SLO.
- Request volume bình thường; không phải lỗi giảm chỉ vì traffic sụt về 0.
- Java logs, Cloud SQL và gateway metrics đồng nhất về xu hướng.
- Không còn alert mới; cập nhật ticket, owner và root cause.

**Analytics dashboard có thể đến sau**; dùng nó để tổng hợp tác động khi dữ liệu đã hội tụ, thay vì trì hoãn xử lý production.

## 14. Tình huống tổng hợp: API thương mại điện tử trên GCP

Hệ thống **Hải Đăng** dùng:

- Apigee **orders-v1** và **payments-v1** trong environment **prod**.
- Backend **orders-api Java** trên Cloud Run, kết nối Cloud SQL PostgreSQL.
- **Cloud Logging + Monitoring** cho backend; **Apigee API Analytics + API Monitoring** cho đường API.
- API product dành cho **mobile-partners** và **merchant-portal** với auth/quota khác nhau.

### 14.1. Thiết kế dashboard vận hành

| Dashboard/report | Metrics | Dimensions/filter | Hành động khi bất thường |
|---|---|---|---|
| **API health** | message_count, 5xx status counts, p95 total latency | proxy, environment | Trigger SRE triage |
| **Target health** | target_error, target response time | target_url/target_host | Xem Cloud Run, Cloud SQL |
| **Policy health** | policy_error | proxy, fault policy | Review API key/OAuth/quota config |
| **Client usage** | TPS, request counts | developer_app, API product | Capacity planning, abuse detection |
| **Business segment** | Orders API calls | dc_client_tier (3–4 values) | So sánh mức sử dụng theo gói |

### 14.2. Thử nghiệm canary Java

Sau khi backend chuyển 10% traffic sang revision mới:

1. Quan sát **Apigee error/latency** theo proxy, xác nhận cả backend cũ và mới nếu có telemetry revision.
2. Ghi correlation ID để đối chiếu **Cloud Run logs** với các request lỗi qua gateway.
3. Nếu latency target tăng mà không có policy deploy, ưu tiên điều tra backend, SQL connection pool.
4. Khi rollback backend, xác nhận **SLO và traffic volume** phục hồi; không chỉ nhìn HTTP 200 từ một URL /health.

### 14.3. Ví dụ số liệu giả định

Trong 10 phút:

| Proxy | Requests | HTTP 5xx | 5xx rate | p95 total |
|---|---:|---:|---:|---:|
| orders-v1 | 80.000 | 1.600 | **2,0%** | 980 ms |
| payments-v1 | 20.000 | 20 | **0,1%** | 240 ms |

Kết luận có cơ sở: lỗi tập trung ở **orders-v1**, không phải toàn bộ Apigee organization. Giả thuyết tiếp: target orders-api/Cloud SQL hoặc policy chỉ gắn với orders-v1. **Không vội thay global Apigee configuration** khi payments-v1 vẫn đạt SLO.

Nếu error budget orders-v1 là **0,1%**, trong 80.000 requests ngân sách đơn giản là **80 lỗi**. Có **1.600** HTTP 5xx nghĩa là đã dùng **20 lần ngân sách lỗi** cho cửa sổ này, nhưng phải đảm bảo chính xác SLO định nghĩa 5xx và time window.

## 15. Bài tập và đáp án gợi ý

### Bài tập A — Chọn đúng công cụ

**Tình huống:** (1) tìm xu hướng request của API product trong 30 ngày, (2) biết lỗi 503 mới tăng 2 phút, (3) xem biến flow của VerifyAPIKey trên một request thử nghiệm, (4) đối chiếu lỗi với SQL trace.

**Đáp án:** (1) **API Analytics/custom report**, (2) **API Monitoring/Cloud Monitoring**, (3) **Apigee Debug**, (4) **Cloud Logging/Tracing backend**. Không chọn một công cụ duy nhất cho bốn mục đích.

### Bài tập B — Tính error rate

Proxy nhận **50.000 requests**, có **250 HTTP 5xx**, **1.000 HTTP 401** và **500 HTTP 429**.

**Hỏi:** HTTP 5xx rate bao nhiêu? Có nên cộng mọi 401/429 vào số lỗi SLO?

**Đáp án:** **0,5%**. 401/429 có thể là kết quả chính sách đúng thiết kế; cần hợp đồng SLO quyết định tính hay loại, không cộng máy móc.

### Bài tập C — Phân biệt lỗi proxy/target

Metrics cho orders-v1: **sum(policy_error)=600**, **sum(target_error)=0**, đa số client nhận HTTP 401; target_response_code rỗng.

**Đáp án định hướng:** nhiều requests có thể bị chặn trước target bởi VerifyAPIKey/OAuth. Kiểm tra **ax_execution_fault_policy_name**, developer app/key và proxy revision; không vội rollback Cloud SQL.

### Bài tập D — Đọc latency

Trước deploy: p95 total **250 ms**, p95 target **200 ms**. Sau deploy: p95 total **900 ms**, p95 target **220 ms**, request-processing p95 tăng mạnh.

**Đáp án:** nghi bottleneck ở **Apigee request processing/policy**, không phải target Java theo số liệu đầu tiên. Kiểm tra proxy revision và Debug; percentile từ các nhóm riêng không được cộng như một đẳng thức chính xác.

### Bài tập E — Thiết kế custom report

Bạn cần tìm **top 5 client apps có nhiều HTTP 429 nhất** trong prod hôm qua.

**Đáp án:** metric **sum(message_count)**, dimension **developer_app**, filter **response_status_code = 429**, time range và environment **prod**; sắp xếp giảm dần/topk=5. So với **total requests của từng app** trước khi đánh giá ai vi phạm cao nhất theo tỷ lệ.

### Bài tập F — Bảo vệ DataCapture

Đội growth muốn ghi **Authorization header** và **customer email** thành dimensions cho mọi request.

**Đáp án:** từ chối thiết kế này vì rò rỉ credentials/PII và cardinality. Chọn các giá trị ít nhạy cảm, ít cardinality như **client tier** đã validate; review DataCapture policy, retention và access rights.

### Bài tập G — Gọi Metrics API

**Yêu cầu:** viết request lấy tổng request theo proxy trong environment **test** cho một ngày UTC, rồi đối chiếu một dashboard. Xác định vì sao response có thể rỗng.

**Đáp án định hướng:** dùng **/organizations/ORG/environments/test/stats/apiproxy?select=sum(message_count)&timeRange=...&timeUnit=day** kèm Bearer token có quyền. Kiểm tra đúng organization/environment/time window, analytics add-on, traffic thực, IAM và **data delay đến khoảng 10 phút**.

### Bài tập H — Alert và điều tra

Proxy orders-v1 tăng 503 nhưng không có tăng policy_error; target_error và target_response_time đều tăng.

**Đáp án:** ưu tiên target backend, Cloud Run/GKE readiness, Cloud SQL connections, network; kiểm tra Apigee fault source và logs. Cấu hình alert 5xx và latency kèm minimum traffic, không spam theo từng request lỗi.

### Bài tập I — Export và chi phí

Tổ chức cần giữ analytics **24 tháng** để phân tích năm, nhưng entitlement UI chỉ cho thời hạn ngắn hơn.

**Đáp án:** thiết kế export có kiểm soát sang **Cloud Storage/BigQuery**, phân vùng/lifecycle/IAM, privacy review, đối chiếu analytics location và data accuracy. Theo dõi trạng thái export **enqueued → completed**, quota, storage/query costs; không nhầm export với request logs chi tiết.

## 16. Tổng kết và tài liệu tham khảo

**Sáu điểm cần nhớ:**

1. **API Analytics** giúp hiểu xu hướng và hiệu năng API; **API Monitoring** ưu tiên phát hiện/điều tra sự cố gần thời gian thực. Hai pipeline có độ trễ và số liệu không nhất thiết bằng nhau.
2. Chọn đúng **metric, dimension, filter, time window**; **proxy errors, policy errors, target errors, HTTP 5xx** không đồng nghĩa.
3. Độ trễ phải tách **total, target, request/response processing** và đọc p95/p99, không chỉ average.
4. **Custom reports, Metrics API, DataCapture** mở rộng phân tích; DataCapture chỉ thu thập **dữ liệu đã kiểm soát**, không lưu secrets hoặc PII theo mặc định.
5. **Cloud Monitoring alerts + access logs + backend telemetry** tạo chuỗi điều tra từ cảnh báo đến root cause và xác nhận phục hồi.
6. **IAM least privilege, entitlements/add-on, retention, region, logging/export cost** phải được đánh giá trước khi bật ở production.

**Nguồn chính thức để đối chiếu thêm:**

1. [Apigee API Analytics overview](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/analytics-services-overview) — cấu trúc Analytics, dashboards, data delay/retention.
2. [Analytics metrics, dimensions and filters](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/analytics-reference) — tên API metrics và dimensions chính xác.
3. [Latency Analysis dashboard](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/latency-analysis-dashboard) — target/request/response latency và p95/p99.
4. [Create and manage custom reports](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/create-custom-reports) — reports, report jobs và filters.
5. [Using the Metrics API](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/use-analytics-api-measure-api-program-performance) — REST queries, select, timeRange, topk.
6. [DataCapture policy](https://docs.cloud.google.com/apigee/docs/api-platform/reference/policies/data-capture-policy) — XML, DataCollector và Extensible policy.
7. [Collect custom analytics data](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/using-data-capture) — tạo collector và custom dimensions.
8. [API Monitoring overview](https://docs.cloud.google.com/apigee/docs/api-monitoring) — Timeline, Investigate, Recent, fault isolation.
9. [Set up alerts and notifications](https://docs.cloud.google.com/apigee/docs/api-monitoring/alerts-notifications) — metrics/labels, thresholds, Cloud Monitoring IAM.
10. [Understand Apigee observability](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/understand-apigee-observability) — Analytics/Monitoring/access logs khác nhau.
11. [Export Analytics data](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/export-data) — Cloud Storage/BigQuery, datastore và export jobs.
