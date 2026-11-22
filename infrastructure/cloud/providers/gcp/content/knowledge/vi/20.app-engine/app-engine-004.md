# Scaling, instance classes và quản lý lưu lượng

Một API học trực tuyến có thể phục vụ vài yêu cầu mỗi phút vào ban đêm nhưng tăng đột biến khi mở đăng ký khóa học. Nếu cấp quá ít instance, người dùng gặp độ trễ cao hoặc lỗi; nếu luôn giữ nhiều instance, chi phí tăng ngay cả lúc không có traffic. Khi phát hành phiên bản mới, một lỗi khác có thể xuất hiện: ứng dụng đã deploy thành công nhưng toàn bộ người dùng lại bị chuyển tới mã mới trước khi kiểm thử.

**App Engine** là nền tảng chạy ứng dụng được Google Cloud quản lý. Bài này thuộc chương **App Engine** trong module **CLOUD_PROVIDERS_GCP**, nối kiến thức về project, IAM, VPC, dịch vụ điện toán và theo dõi độ tin cậy/chi phí với ba quyết định: **chọn chế độ scaling**, **chọn năng lực mỗi instance** và **phân phối traffic giữa các version**. Nội dung viết cho cả **standard environment** và **flexible environment**, bởi những trường cấu hình của chúng không thể dùng thay thế nhau.

**Mục tiêu học tập:** sau bài này, bạn có thể:

1. Phân biệt App Engine application, service, version và instance.
2. Chọn automatic, basic hoặc manual scaling của Standard; automatic/manual của Flexible.
3. Chọn `instance_class` F/B đúng với loại scaling, hoặc CPU/RAM trong Flexible.
4. Giải thích ảnh hưởng của cold start, concurrency, min/max instances và quota tới SLO/chi phí.
5. Deploy version không chuyển traffic, chia traffic có kiểm soát, xác minh và rollback.
6. Đọc số liệu vận hành, tìm lỗi thường gặp và thực hành trong project thử nghiệm.

## 1. Mô hình App Engine: application → service → version → instance

App Engine tạo **application** trong một Google Cloud project tại một **location** được chọn khi khởi tạo (không thể đổi location của application hiện có theo cách cập nhật thông thường). Một application có thể có nhiều **services** như `default`, `api`, `worker`. Mỗi service có nhiều **versions** của mã/config; mỗi version chạy trên một hoặc nhiều **instances**.

~~~mermaid
flowchart TB
  APP["App Engine application<br/>trong project"] --> API["Service: api"]
  APP --> WORKER["Service: worker"]
  API --> V1["Version v1<br/>traffic 90%"]
  API --> V2["Version v2<br/>traffic 10%"]
  V1 --> I1["Instances v1<br/>autoscaling"]
  V2 --> I2["Instances v2<br/>autoscaling"]
  WORKER --> W["Version hiện tại<br/>scaling riêng"]
~~~

**Scaling cấu hình theo version**, thông qua `app.yaml`; traffic splitting cấu hình ở **service** để phân phối request tới các version của chính service đó. Hai version cùng phục vụ đồng thời có thể cùng tiêu thụ tài nguyên và chi phí.

| Khái niệm | Điều cần nhớ |
| --- | --- |
| **Application** | Một ứng dụng App Engine gắn với project/location; không phải tên một instance. |
| **Service** | Thành phần triển khai độc lập; `default` thường là entrypoint mặc định. |
| **Version** | Bản mã + cấu hình đã deploy, có thể nhận một phần traffic hoặc không có traffic. |
| **Instance** | Đơn vị chạy version, nhận request và tiêu thụ CPU/RAM theo môi trường. |
| **Traffic split** | Phân bổ request **không chỉ định version** giữa các version trong một service. |
| **Version URL** | Truy cập trực tiếp phiên bản cụ thể; **không chịu split** của URL service chung. |

Một version nhận **0% traffic** không đồng nghĩa không ai truy cập được: người có URL version cụ thể vẫn có thể gửi request nếu không có biện pháp bảo vệ. Không dùng traffic split như hàng rào IAM, xác thực hoặc ngăn truy cập môi trường thử nghiệm.

## 2. Chọn Standard hay Flexible trước khi chỉnh scaling

| Tiêu chí | Standard environment | Flexible environment |
| --- | --- | --- |
| Hạ tầng | Runtime sandbox được App Engine quản lý. | Container chạy trên VM Compute Engine do nền tảng quản lý, linh hoạt về runtime/phụ thuộc. |
| Scaling | **Automatic, Basic, Manual**. | **Automatic, Manual**; không có Basic như Standard. |
| Kích thước instance | `instance_class` họ **F** hoặc **B**. | `resources`: `cpu`, `memory_gb`, `disk_size_gb`. |
| Khả năng scale về 0 | **Automatic/Basic** có thể về 0 trong điều kiện phù hợp. | Version hoạt động phải duy trì ít nhất **một instance**; không dùng Flexible để kỳ vọng scale-to-zero như Standard. |
| Chi phí lúc nhàn rỗi | Có thể giảm nhờ dynamic instances; `min_instances` và manual tạo mức nền. | Luôn có phí compute cho các instance nền theo cấu hình. |
| Startup và scale-out | Thường nhanh hơn, nhưng vẫn có loading request/cold start. | Khởi tạo VM/container có thể lâu hơn; cần capacity dự phòng. |
| Khả năng tùy biến | Theo runtime và giới hạn sandbox được hỗ trợ. | Tùy chỉnh OS/runtime và package sâu hơn theo mô hình container. |

**Không chuyển nguyên** `min_instances`, `max_instances` của Standard sang Flexible: Flexible dùng `min_num_instances`, `max_num_instances` và những tham số CPU khác. Chọn môi trường dựa trên runtime và yêu cầu vận hành trước, sau đó tối ưu instance.

## 3. Standard environment: ba chế độ scaling

### 3.1. Automatic scaling — xử lý traffic dao động

Automatic là mặc định trong Standard. App Engine quan sát request rate, latency, CPU hoặc throughput utilization để tăng/giảm số instance. Workload ít yêu cầu có thể về 0, khi nhận yêu cầu mới có thể xuất hiện **cold start/loading request**.

Ví dụ `app.yaml` cho một version API Python Standard:

~~~yaml
runtime: python312
service: api
instance_class: F2
automatic_scaling:
  min_instances: 1
  max_instances: 10
  target_cpu_utilization: 0.65
  max_concurrent_requests: 30
~~~

| Trường | Ý nghĩa | Đánh đổi |
| --- | --- | --- |
| `instance_class: F2` | Năng lực CPU/RAM của một instance. | Lớp lớn hơn có thể phục vụ nhiều tải hơn, giá mỗi giờ cao hơn. |
| `min_instances: 1` | Duy trì mức tối thiểu cho version đang nhận traffic theo điều kiện sản phẩm. | Giảm cold start nhưng phát sinh phí nền; cần hỗ trợ warmup phù hợp. |
| `max_instances: 10` | Giới hạn số instance mà version tự mở rộng tới. | Kiểm soát tài nguyên/chi phí; quá thấp có thể tăng latency/503 khi peak. |
| `target_cpu_utilization: 0.65` | Mục tiêu CPU làm tín hiệu scaling. | Không phải giới hạn CPU cứng hoặc bảo đảm CPU luôn đúng 65%. |
| `max_concurrent_requests: 30` | Số request đồng thời tối đa được lập lịch cho một instance. | Đặt quá cao có thể làm response chậm nếu code không xử lý concurrency hiệu quả. |

**Chú ý thay đổi mặc định:** với project mới tạo **sau tháng 3/2025**, App Engine Standard áp giới hạn mặc định **20 automatic instances** nếu không chỉ định `max_instances`; application cũ có thể có mặc định khác. Vì vậy luôn khai báo giới hạn có chủ đích, đối chiếu quota/phiên bản tài liệu thay vì phụ thuộc mặc định. Với `min_instances`, tài liệu yêu cầu bật **warmup requests** và có xử lý phù hợp để cơ chế hoạt động như kỳ vọng.

### 3.2. Basic scaling — bật khi cần, tắt sau khi nhàn rỗi

Basic tạo instance khi có request và tắt sau `idle_timeout` nếu không còn hoạt động. Phù hợp service dùng không liên tục hoặc có logic khởi tạo cần đặc tính Basic, nhưng khi request tăng đột biến có thể phải chờ instance khởi động.

~~~yaml
runtime: python312
service: report-worker
instance_class: B2
basic_scaling:
  max_instances: 3
  idle_timeout: 10m
~~~

`max_instances` giới hạn số instance hoạt động của version; `idle_timeout` là khoảng thời gian không có request trước khi tắt instance. Đó **không phải** giới hạn thời lượng một request. Basic có hành vi startup/instance addressability khác automatic; chỉ dùng khi ứng dụng thực sự cần.

### 3.3. Manual scaling — số instance cố định

Manual giữ số instance được chỉ định chạy ngay cả lúc không có traffic:

~~~yaml
runtime: python312
service: persistent-worker
instance_class: B2
manual_scaling:
  instances: 2
~~~

Ưu điểm là có sẵn capacity và hỗ trợ một số workflow cần tiến trình kéo dài/địa chỉ instance ổn định. Nhược điểm là trả phí cho instance không dùng và **không tự tăng** khi peak, trừ khi đổi cấu hình và triển khai/vận hành phù hợp.

Nếu một workload thực chất là xử lý hàng đợi theo sự kiện, đừng mặc định dùng manual để giữ một tiến trình polling vô thời hạn. Hãy so sánh Cloud Tasks, Pub/Sub, Cloud Run hoặc giải pháp khác theo yêu cầu, quota và mô hình chi phí.

### 3.4. Bảng so sánh nhanh

| Chế độ Standard | Instance class | Tăng instance theo tải | Về 0 khi nhàn rỗi | Dùng khi |
| --- | --- | --- | --- | --- |
| **Automatic** | F1, F2, F4, F4_1G | Có | Có thể, nếu min/idle và điều kiện cho phép | HTTP API/website có tải biến động. |
| **Basic** | B1, B2, B4, B4_1G, B8 | Có, khi có request và còn dưới max | Có, sau idle timeout | Tải không liên tục, cần một số đặc tính instance backend. |
| **Manual** | B1, B2, B4, B4_1G, B8 | Không tự tăng | Không theo quy tắc nhàn rỗi thông thường | Capacity cố định hoặc workflow cần instance duy trì. |

Các chế độ có **giới hạn request timeout, startup và background processing khác nhau**; ví dụ Standard Automatic có giới hạn request HTTP thường **10 phút**, còn Basic/Manual có thể tới **24 giờ** theo môi trường/tài liệu. Không suy rằng một handler HTTP nên chạy sát giới hạn: tác vụ dài thường nên đưa vào queue/background workflow có trạng thái và retry phù hợp.

## 4. Instance classes và Flexible resources

### 4.1. Chọn class Standard bằng số liệu

Một instance class quyết định mức **CPU tương đối**, giới hạn bộ nhớ và chi phí instance-hour. Các class phổ biến:

| Class | Giới hạn RAM tham khảo | Nhóm scaling |
| --- | ---: | --- |
| F1 | 384 MB | Automatic |
| F2 | 768 MB | Automatic |
| F4 | 1.536 MB | Automatic |
| F4_1G | 3.072 MB | Automatic |
| B1 | 384 MB | Basic, Manual |
| B2 | 768 MB | Basic, Manual |
| B4 | 1.536 MB | Basic, Manual |
| B4_1G | 3.072 MB | Basic, Manual |
| B8 | 3.072 MB | Basic, Manual |

Các chỉ số CPU công bố cho F/B là **mức năng lực tính toán tương đối**, không phải cam kết tần số GHz vật lý cố định. Bộ nhớ giới hạn bao gồm cả ứng dụng và runtime; với Java hoặc thư viện nặng, overhead của runtime có thể đáng kể.

Ví dụ một API xử lý JSON đơn giản chạy ổn trên F1 ở tải nhỏ, nhưng tại peak có thể chạm CPU hoặc bộ nhớ. Nâng lên F2 có thể giảm thời gian xử lý mỗi request; tuy nhiên không tự sửa được truy vấn cơ sở dữ liệu chậm. **Dùng p95/p99 latency, CPU/memory utilization, lỗi OOM và chi phí** để chọn class; không chọn F4_1G chỉ vì “mạnh nhất”.

### 4.2. Flexible: cấp CPU/RAM/disk thay vì F/B class

App Engine Flexible chạy trên VM/container, cấu hình tài nguyên qua `resources` và chỉ hỗ trợ **automatic hoặc manual** scaling.

Ví dụ rút gọn `app.yaml` của ứng dụng Python Flexible:

~~~yaml
runtime: python
env: flex
service: api-flex
resources:
  cpu: 2
  memory_gb: 2.3
  disk_size_gb: 10
automatic_scaling:
  min_num_instances: 1
  max_num_instances: 5
  cool_down_period_sec: 180
  cpu_utilization:
    target_utilization: 0.6
~~~

Đây là **ví dụ cấu hình scaling**, không phải toàn bộ source deployable: Flexible còn cần mã ứng dụng/entrypoint phù hợp với runtime, service, health checks và dependency. Giá trị CPU/RAM/disk phải nằm trong giới hạn được sản phẩm hỗ trợ.

| Khóa Flexible | Ý nghĩa |
| --- | --- |
| `resources.cpu` | Số vCPU yêu cầu cho một instance. |
| `resources.memory_gb` | RAM dùng cho ứng dụng, chưa gồm một phần overhead hệ thống theo tài liệu. |
| `resources.disk_size_gb` | Dung lượng disk instance; không xem như nơi lưu dữ liệu bền vững. |
| `min_num_instances` / `max_num_instances` | Biên số instance khi automatic scaling. |
| `cool_down_period_sec` | Chờ trước khi dùng tín hiệu tải của instance mới để scale. |
| `cpu_utilization.target_utilization` | Mục tiêu CPU autoscaler. |
| `target_concurrent_requests` | Tùy chọn Flexible có trạng thái hỗ trợ riêng; phải xác minh giới hạn và phiên bản trước khi dùng. |

Flexible mặc định automatic scaling và thường giữ **ít nhất một instance hoạt động**, với cấu hình mặc định hiện hành thường có `min_num_instances: 2` nếu không ghi đè. Không áp `min_instances: 0` của Standard vào Flexible. Với manual Flexible:

~~~yaml
runtime: python
env: flex
service: fixed-api
resources:
  cpu: 2
  memory_gb: 2.3
manual_scaling:
  instances: 2
~~~

Mỗi version Flexible đang chạy có thể phát sinh **phí VM**, disk và hạ tầng liên quan ngay cả khi tỷ lệ traffic của version bằng 0. Chi phí/khả năng scaling vì thế cần được xem cùng kế hoạch dừng/xóa version cũ và thời gian giữ rollback.

## 5. Sizing theo tải và kiểm soát cold start

### 5.1. Ước lượng concurrency trước khi chọn max instances

Một phép tính gần đúng theo trạng thái ổn định:

\[
\text{Concurrent requests} \approx \text{RPS}\times\text{Latency trung bình (giây)}
\]

Nếu có 300 requests/giây và mỗi request chiếm trung bình 0,2 giây, mức đồng thời khoảng **60**. Nếu một instance xử lý **15 request đồng thời hiệu quả**, ước lượng tối thiểu là **4 instance** ở trạng thái lý tưởng. Khi tính cho production, cần dự phòng cho peak, phân phối tải không đều, p95/p99, warmup, GC, retry và dependency.

**Đừng dùng `max_concurrent_requests` như hiệu năng đã đo.** Một cấu hình cho phép 30 request đồng thời không có nghĩa ứng dụng xử lý 30 request mà vẫn đạt SLO. Ví dụ service dùng single-threaded blocking code có thể nghẽn dù App Engine còn slot request.

| Quan sát | Có thể do | Hành động |
| --- | --- | --- |
| CPU rất cao, request queue dài | Instance class nhỏ hoặc code tốn CPU | Profile CPU, tối ưu code, thử tăng F class hoặc số instance. |
| CPU thấp, latency vẫn cao | Database, API ngoài, lock, network I/O | Tracing, timeout và connection pool, không tăng CPU mù quáng. |
| Tăng instance rồi database quá tải | Quá nhiều connection hoặc truy vấn đồng thời | Giới hạn pool/RPS, cache, điều chỉnh DB capacity và backpressure. |
| Lâu không có traffic, request đầu chậm | Cold start/loading request | Xem `min_instances`, warmup, giảm khởi tạo nặng. |
| Peak báo hết instance hoặc 503 | Chạm `max_instances`, quota hoặc capacity | Kiểm tra quota, peak profile, RPS và giới hạn chi phí. |
| Flexible scale-up chậm | Khởi động VM/container cần thời gian | Dự phòng min instances, tối ưu container/startup và readiness. |

### 5.2. Warmup requests ở Standard Automatic

App Engine có thể gửi `GET /_ah/warmup` để chuẩn bị instance trước request người dùng. Để bật trong Standard:

~~~yaml
runtime: python312
instance_class: F2
inbound_services:
  - warmup
automatic_scaling:
  min_instances: 1
  max_instances: 8
~~~

Ứng dụng có thể cung cấp handler `/_ah/warmup` thực hiện khởi tạo **ngắn, idempotent, không chứa bí mật trong log**. Warmup là **best effort**: request đầu của một version chưa chạy hoặc tải tăng rất nhanh vẫn có thể là loading request. Vì vậy cần đo cold-start latency thực, không xem bật warmup là cam kết 0 ms.

**Trade-off:** `min_instances > 0` giảm nguy cơ cold start nhưng tăng giờ instance. `min_idle_instances` cũng có thể giữ instance rảnh phục vụ nhanh, song hành vi tính phí và hiệu lực với version nhận traffic cần được xác minh trước khi áp dụng. Warmup có thể tiêu thụ thêm CPU/thời gian nếu handler làm việc nặng.

### 5.3. Ngưỡng autoscaling không phải cơ chế chống tấn công

Giới hạn `max_instances` giúp giới hạn quy mô, nhưng khi bị traffic bất thường, các instance còn lại có thể quá tải. Kết hợp xác thực, Cloud Armor/load balancing phù hợp, rate limit ở gateway/ứng dụng, timeout, quota Cloud Tasks và kiểm soát connection pool. Cũng cần theo dõi chi phí khi phiên bản cũ và mới cùng chạy.

Không lưu session đăng nhập duy nhất trong RAM của một instance: request tiếp theo có thể tới instance hoặc version khác. Sử dụng **shared state** như database/cache phù hợp, thiết kế session/cookie an toàn và migration schema tương thích khi hai version cùng tồn tại.

## 6. Quản lý traffic giữa các version

App Engine cho phép chạy đồng thời các version của **cùng một service**, chuyển toàn bộ traffic hoặc chia traffic theo trọng số. Đó là nền tảng của **canary**, **A/B testing**, **blue-green** và **rollback**; việc deploy thành công chỉ mới tạo version, chưa chứng minh version mới an toàn để phục vụ production.

### 6.1. Deploy và promote là hai thao tác khác nhau

- **Deploy:** tải mã và cấu hình lên App Engine, tạo hoặc cập nhật version.
- **Promote / set traffic:** quyết định những request đến **URL service chung** được điều phối vào version nào.
- **Test trực tiếp:** gọi **version-specific URL** để xác minh version mới trước khi được chia traffic.
- **Rollback:** chuyển traffic trở lại version ổn định, sau đó kiểm tra dữ liệu, logs và nguyên nhân lỗi.

~~~mermaid
flowchart LR
  U["Request tới URL service"] --> ROUTE["App Engine traffic routing"]
  ROUTE -->|"95%"| V1["Version stable-v1"]
  ROUTE -->|"5%"| V2["Version canary-v2"]
  TEST["Kiểm thử trực tiếp<br/>version URL"] -. "Bỏ qua split của service URL" .-> V2
~~~

**Lưu ý bảo mật:** một version ở 0% vẫn có thể truy cập qua version URL. Nếu đó là môi trường xử lý dữ liệu thật, phải áp xác thực/IAM/firewall ứng dụng phù hợp; traffic 0% không phải cơ chế “ẩn” phiên bản.

### 6.2. Ba kiểu chia traffic

| Phương pháp | Cách định tuyến | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **IP** | Hash IP người gửi để gán nhóm vào version. | Phân chia đơn giản theo nguồn IP. | NAT/proxy gom nhiều người về một IP; mobile đổi IP làm trải nghiệm không ổn định. |
| **Cookie** | Sử dụng cookie `GOOGAPPUID` với phân nhóm ổn định theo người dùng. | A/B hoặc canary cần giữ người dùng ở cùng nhóm version tương đối ổn định. | Client phải lưu/trả cookie; cache và việc chuyển tiếp request nội bộ cần chú ý. |
| **Random** | Chọn version theo tỷ lệ cho các request. | Khi phân phối request độc lập và không yêu cầu stickiness. | Cùng một người dùng có thể gặp các version khác nhau liên tiếp. |

Ví dụ khi đặt traffic `stable-v1=0.95` và `canary-v2=0.05`, đây là **mục tiêu định tuyến**, không bảo đảm chính xác 5% người dùng/nghiệp vụ thành công trong một khoảng ngắn. Với IP splitting, proxy có thể làm traffic phân bố lệch lớn; với cookie, một số client di động/backend-to-backend phải chủ động giữ cookie `GOOGAPPUID`.

**Cache:** khi cùng URL có hai version trả nội dung khác nhau, cache/CDN có thể giữ nội dung của một version rồi trả cho người dùng được định tuyến tới version khác. Phải thiết kế cache keys, `Vary` và tài nguyên tĩnh/versioned assets phù hợp; không đặt session data nhạy cảm trong cookie định tuyến.

### 6.3. gcloud: xem version và traffic trước khi đổi

Đây là các lệnh **chỉ đọc** sau khi bạn đã chọn đúng project:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export SERVICE="default"

gcloud config set project "$PROJECT_ID"
gcloud app services list --project="$PROJECT_ID"
gcloud app versions list --service="$SERVICE" --project="$PROJECT_ID"

# Xem cấu hình chia traffic hiện tại và version đang nhận request
gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

Trước thay đổi production, lưu bản chụp tỷ lệ traffic và tên version đang ổn định. Không dựa vào việc tên version chứa chữ `stable` hoặc `canary` để xác định thực tế nó có lỗi hay không.

### 6.4. Canary có kiểm soát bằng `set-traffic`

Giả sử service có hai version đã deploy: `stable-v1` và `canary-v2`. Sau khi chủ hệ thống phê duyệt, có thể chia 95/5 theo cookie:

~~~bash
# THAO TÁC GHI: đổi tỷ lệ traffic thật của service default
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=stable-v1=0.95,canary-v2=0.05 \
  --split-by=cookie

# Đọc lại trạng thái sau thay đổi
gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

Các trọng số cộng thành 1 là cách dễ đọc; CLI hỗ trợ trọng số tương đối nhưng việc chuẩn hóa về 100% giúp review chính xác. Có thể tăng theo từng cột mốc **1% → 5% → 25% → 100%** nếu đạt SLO, và cần giữ khoảng quan sát đủ dài để có lưu lượng đại diện, kể cả peak.

**Điều kiện xuất bản:** version mới phải tương thích schema database, cache, API, background tasks và session với version cũ. Nếu v2 đã chạy migration không tương thích, rollback traffic về v1 có thể **không** khôi phục ứng dụng. Ưu tiên migration **expand → migrate → contract** và tách rollout database khỏi cutover application.

### 6.5. Rollback nhanh về version ổn định

Khi tỷ lệ 5xx/p99 hoặc lỗi nghiệp vụ vượt ngưỡng dừng:

~~~bash
# THAO TÁC GHI: trả 100% traffic về version đã được xác nhận tốt
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=stable-v1=1

gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

Sau rollback, kiểm tra **HTTP error rate, latency, logs và tình trạng database**. Không xóa version mới ngay khi vẫn cần bằng chứng điều tra. Nếu đã cấu hình lưu lượng sticky theo cookie, kiểm tra kết quả định tuyến thực tế sau cutover thay vì chỉ tin CLI trả thành công.

### 6.6. Chuyển 100% traffic: tức thời hay migrate dần?

Khi chuyển từ một version sang version khác, App Engine có cơ chế **traffic migration** để giảm cold-start/latency spike trong những tình huống được hỗ trợ. Lệnh:

~~~bash
# Chỉ dùng sau phê duyệt và kiểm tra hỗ trợ của loại scaling/version
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=canary-v2=1 \
  --migrate
~~~

`--migrate` yêu cầu cố gắng chuyển dần, để autoscaler version mới kịp tăng instance; hiệu lực và hạn chế cần đọc theo loại môi trường/version. Không dùng nó như cách ép mọi hình thức traffic split nhiều version đều chuyển dần theo cùng thuật toán. Việc chuyển thẳng 100% tới version chưa có instance có thể tạo **loading-request latency spike**.

## 7. Quy trình phát hành an toàn

| Giai đoạn | Việc làm | Điều kiện chuyển tiếp |
| --- | --- | --- |
| **1. Chuẩn bị** | Kiểm thử mã, schema/data compatibility, chọn instance class/scaling và budget. | Có phiên bản ổn định để quay về. |
| **2. Deploy no-promote** | Tạo version mới nhưng không tự đổi traffic của service chung. | Deploy hoàn tất, version URL kiểm thử được. |
| **3. Smoke test** | Gọi endpoint, auth, DB, Cloud Storage, task queue; kiểm tra log. | Tất cả phép thử thiết yếu đạt. |
| **4. Canary** | Chuyển 1–5% request theo phương pháp split phù hợp. | Có đủ mẫu, p95/p99, error rate và business KPIs bình thường. |
| **5. Mở rộng** | Tăng tỷ lệ có kiểm soát, quan sát peak/cold start/instance count. | SLO, quota, ngân sách và dữ liệu đều đạt. |
| **6. Full rollout** | Chuyển 100%, theo dõi sau phát hành. | Không có lỗi hồi quy, dependency vẫn khỏe. |
| **7. Dọn dẹp** | Đánh giá xóa version/instance không còn dùng sau thời gian rollback. | Không còn route, job, URL và dependency trỏ version cũ. |

**Version được giữ lại không miễn phí mặc định:** manual/Flexible có thể giữ compute dù không còn traffic; Standard Automatic có thể giảm instance khi idle theo điều kiện. Dọn version cũ cần xét thời gian có thể rollback, logs/snapshot và những endpoint gọi thẳng version URL.

## 8. Bài thực hành: hai version Standard và canary 10%

**Mục tiêu:** triển khai hai version của **một service lab riêng**, theo dõi version nào trả request, chuyển tỷ lệ 90/10 rồi quay về 100/0. Lab không đo hiệu năng tối đa; nó kiểm chứng chính xác **deploy, routing và rollback**.

**Điều kiện bắt buộc:** project **đã có App Engine application** và billing phù hợp; account có quyền App Engine deploy, quản lý traffic và xem logs; runtime Python được App Engine Standard hỗ trợ; có `gcloud`, shell và các build services cần thiết. **Không chạy trong project production.** Tạo App Engine application lần đầu có quyết định **location không thể đổi trực tiếp**, nên bài lab **không tự tạo application** hoặc tự chọn region cho người học.

### 8.1. Kiểm tra project và service chưa tồn tại

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export SERVICE="traffic-lab"

gcloud config set project "$PROJECT_ID"
gcloud app describe --project="$PROJECT_ID"
gcloud app services list --project="$PROJECT_ID"
~~~

Nếu service `traffic-lab` **đã tồn tại**, dừng và dùng project lab riêng hoặc tên service khác được phê duyệt. Không ghi đè service của nhóm khác. Khi `gcloud app describe` báo chưa có App Engine application, nhờ người quản trị chọn location theo chính sách trước khi chạy các bước tiếp.

### 8.2. Tạo ứng dụng mẫu ở máy local

Tạo thư mục riêng `traffic-lab/`, với ba file:

**`app.yaml`**

~~~yaml
runtime: python312
service: traffic-lab
entrypoint: gunicorn -b :$PORT main:app
instance_class: F1
automatic_scaling:
  min_instances: 0
  max_instances: 3
  target_cpu_utilization: 0.65
~~~

**`requirements.txt`**

~~~text
Flask>=3,<4
gunicorn>=22,<24
~~~

**`main.py`**

~~~python
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def home():
    return jsonify(
        service=os.environ.get("GAE_SERVICE", "unknown"),
        version=os.environ.get("GAE_VERSION", "local"),
        status="ok",
    )
~~~

Hai version của bài lab dùng **cùng source**, nhưng `GAE_VERSION` trong phản hồi cho biết request thực sự chạy trên version nào. Cấu hình `F1`, `min_instances: 0` và `max_instances: 3` giúp giữ phạm vi compute nhỏ; **không bảo đảm lab miễn phí**, đặc biệt khi build, request và log phát sinh. Với ứng dụng thật, khóa dependency theo phiên bản đã được kiểm thử và cấu hình security/observability phù hợp.

### 8.3. Deploy version đầu và bản canary

Trong thư mục có `app.yaml`:

~~~bash
# Chỉ chạy khi traffic-lab là service mới do bạn sở hữu
# Triển khai version đầu; trong service lab mới có thể cho nhận traffic
gcloud app deploy app.yaml \
  --project="$PROJECT_ID" \
  --version=v1lab \
  --quiet

# Đọc lại: chắc chắn service traffic-lab có v1lab
gcloud app versions list --project="$PROJECT_ID" --service="$SERVICE"

# Bản thứ hai KHÔNG tự chuyển traffic chung sau khi deploy
gcloud app deploy app.yaml \
  --project="$PROJECT_ID" \
  --version=v2lab \
  --no-promote \
  --quiet

gcloud app versions list --project="$PROJECT_ID" --service="$SERVICE"
~~~

Thông thường `v1lab` nhận traffic của service lab mới; `v2lab` đã deploy nhưng chưa được promote. Đọc cột TRAFFIC_ALLOCATED/output thực tế trước khi làm tiếp, bởi cấu hình deploy mặc định có thể chịu tác động bởi chính sách CLI/project. Với một version phục vụ 0%, bạn vẫn có thể kiểm thử qua **version-specific URL** nếu route/authorization cho phép.

**Không cần** thay mã ứng dụng giữa hai lần deploy để minh họa version routing; tuy nhiên trong phát hành thật, v2 phải là artifact mới với revision/test evidence rõ ràng.

### 8.4. Chia 90/10 theo cookie và quan sát

~~~bash
# Thao tác ghi chỉ đối với service riêng do lab tạo
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=v1lab=0.9,v2lab=0.1 \
  --split-by=cookie

gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
~~~

Lấy URL **service** từ Console hoặc mô tả App Engine, rồi gọi bằng client HTTP có giữ cookie:

~~~bash
SERVICE_URL="https://URL_CUA_SERVICE_TRAFFIC_LAB"

# Cookie jar giữ GOOGAPPUID để cùng client có phiên bản tương đối ổn định
curl --silent --show-error \
  --cookie-jar ./lab-cookies.txt \
  --cookie ./lab-cookies.txt \
  "$SERVICE_URL/"

curl --silent --show-error \
  --cookie-jar ./lab-cookies.txt \
  --cookie ./lab-cookies.txt \
  "$SERVICE_URL/"
~~~

Đầu ra JSON có trường `version` là `v1lab` hoặc `v2lab`. Một client có cookie giữ nguyên **không dùng để xác nhận đúng 10% tổng traffic**; bạn cần nhiều client/cookie độc lập và lượng request đủ lớn để ước tính tỷ lệ. Không dùng lệnh tạo traffic tải cao vào project đang chứa dịch vụ khác.

### 8.5. Rollback và dọn tài nguyên lab

~~~bash
# Chuyển tất cả traffic của service lab về v1
gcloud app services set-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --splits=v1lab=1

gcloud app services describe "$SERVICE" --project="$PROJECT_ID"
gcloud app versions list --service="$SERVICE" --project="$PROJECT_ID"

# Chỉ khi xác nhận traffic-lab do chính bài lab tạo và không còn ai dùng
gcloud app services delete "$SERVICE" \
  --project="$PROJECT_ID" \
  --quiet

# Kiểm tra service đã không còn
gcloud app services list --project="$PROJECT_ID"
~~~

Lệnh xóa **service** cũng xóa các version kèm theo. Vì vậy **không** chạy nếu `traffic-lab` có người dùng, worker hoặc cron/task phụ thuộc; chỉ dọn sau khi đã kiểm tra đối tượng do chính bạn tạo. Nếu dùng service `default` cho thử nghiệm khác, không dùng lệnh xóa service lab này để xóa `default`.

Tệp local `lab-cookies.txt` lưu cookie dùng trong lab; dọn theo chính sách môi trường thử nghiệm. App Engine application/project **không** bị xóa; logs, build artifacts, Cloud Storage staging hoặc các tài nguyên liên quan có thể tồn tại sau khi xóa service, cần quản lý riêng theo quyền và chính sách.

## 9. Vận hành: đo hiệu năng, độ tin cậy và chi phí

### 9.1. Dashboard theo service **và version**

Để so sánh canary công bằng, phân tách số liệu theo **service, version, môi trường và khoảng thời gian** thay vì chỉ nhìn tổng request của application:

| Nhóm tín hiệu | Mục tiêu quan sát | Ví dụ khi có vấn đề |
| --- | --- | --- |
| **HTTP latency p50/p95/p99** | Phát hiện request chậm khi cold start hoặc peak. | v2 có p99 cao hơn v1 dù CPU tương tự. |
| **5xx/4xx và tỷ lệ request thành công** | Phân biệt lỗi server với lỗi client; xem lỗi ứng dụng theo version. | 5xx của v2 tăng khi thử 5% traffic. |
| **Instance count, instance hours** | Biết số instance đang chạy và mức tiêu thụ compute. | v1 và v2 cùng có min instances làm phí tăng. |
| **CPU/memory và out-of-memory** | Phát hiện class nhỏ hoặc runtime tạo áp lực tài nguyên. | F1 thường xuyên OOM; chuyển class có thể phù hợp. |
| **Pending/loading latency** | Nhận diện queue và cold start. | Request đầu sau thời gian im lặng rất chậm. |
| **Dependency metrics** | Kết nối Cloud SQL, Datastore/Firestore, VPC/network/API ngoài. | Tăng instance làm vượt connection limit của DB. |
| **Business SLI** | Đơn hàng/đăng ký/đăng nhập có thành công không. | HTTP 200 nhưng nghiệp vụ ghi dữ liệu sai. |
| **Billing/quotas** | Phát hiện tăng instance-hours, request, egress, log và quota. | Canary chiếm ít traffic nhưng giữ nhiều instance nền. |

Sử dụng **Cloud Monitoring**, App Engine Dashboard/Versions, **Cloud Logging** và error reporting phù hợp. Các metric thực tế/phần tên nhãn phụ thuộc runtime và cách xuất metric của ứng dụng; không tự tạo alert dựa trên metric chưa tồn tại.

### 9.2. Tiêu chí dừng canary

Trước khi tăng tỷ lệ, ghi rõ tiêu chí để người trực **có thể quyết định ngay**:

- Error rate v2 không vượt ngưỡng SLO hoặc mức lệch so với v1 trong cùng khung tải.
- p95/p99 không vượt biên đã thống nhất; độ trễ request đầu được theo dõi riêng.
- Không có lỗi database migration, thay đổi API response không tương thích hoặc tăng error budget bất thường.
- `max_instances`, quota, memory và chi phí còn trong phạm vi được duyệt.
- Khi có sự cố, có lệnh và người chịu trách nhiệm rollback, cùng kết quả kiểm thử phiên bản cũ.

**Bẫy thống kê:** 1% traffic trong 5 phút có thể tạo số mẫu quá ít để phát hiện lỗi hiếm. Cần giữ thời lượng quan sát đủ đại diện; việc chọn thời điểm peak/giờ cao điểm là quyết định có cân nhắc rủi ro, không chỉ nhìn tỷ lệ 5xx tức thời.

### 9.3. Ước tính chi phí tổng

Phí App Engine không chỉ phụ thuộc số HTTP request. Một ước lượng cấp kiến trúc:

\[
\text{Tổng chi phí}\approx
\text{instance hours}
+\text{network egress}
+\text{dịch vụ dữ liệu}
+\text{build/log/giám sát}
\]

| Tình huống | Rủi ro chi phí |
| --- | --- |
| Giữ `min_instances` cao cả ngày | Tính giờ instance nền ngay lúc rất ít người dùng. |
| Standard chọn F4/F4_1G không dựa tải | Mức tính phí instance-hour cao hơn F1. |
| Flexible giữ nhiều version manual | Có compute nền riêng cho mỗi version. |
| Max instances quá cao dưới tải lỗi hoặc bị abuse | Tăng mạnh instance-hours, database connections và chi phí liên quan. |
| Max instances quá thấp | Tắc nghẽn và lỗi khi peak, mất doanh thu/dịch vụ. |
| Canary kéo dài nhưng không dọn v1/v2 | Tài nguyên, request trực tiếp qua version URL và chi phí phát sinh khó theo dõi. |

Đối với Standard, F/B instance class được quy đổi sang **frontend/backend instance-hour** theo đơn vị tính giá của sản phẩm. Flexible có cấu trúc giá khác dựa trên tài nguyên VM; cần xem giá hiện hành theo region, quota/free tier và dịch vụ phụ. **Cloud Billing budget alert không phải hard spending cap.**

## 10. Xử lý sự cố phổ biến

| Triệu chứng | Nguyên nhân cần kiểm tra | Bước đầu an toàn |
| --- | --- | --- |
| Deploy thành công nhưng người dùng vẫn thấy code cũ | Version mới dùng `--no-promote` hoặc split còn 100% v1 | `gcloud app versions list`, `gcloud app services describe`. |
| Canary “5%” nhưng nhận rất nhiều request | Split theo IP, nhiều traffic từ chung proxy/NAT | Chuyển phương pháp phù hợp sau review; đo distribution theo nhiều client. |
| Cùng user gặp hai UI khác nhau | Random/IP split, IP đổi hoặc client không giữ `GOOGAPPUID` | Dùng cookie split nếu cần sticky và kiểm tra cookie forwarding. |
| Bật traffic v2 làm request đầu chậm | Không có warm instance, khởi tạo phụ thuộc nặng | Kiểm tra cold start, warmup, `min_instances`, migrate gradual. |
| Version phục vụ traffic nhưng instance không tăng | Chạm `max_instances`/quota, CPU signal, pending queue hoặc dependency | Xem metrics per version, quota, class và saturation. |
| Flexible không scale về 0 | Đây là đặc tính môi trường Flexible | Dự toán instance nền, dùng Standard/Cloud Run nếu yêu cầu scale-to-zero phù hợp. |
| `app.yaml` báo class không hợp lệ | Dùng F class với Basic/Manual hoặc B class với Automatic | Đối chiếu bảng class và scaling type Standard. |
| Flexible `min_instances` không hoạt động | Dùng nhầm khóa Standard thay cho `min_num_instances` | Đọc đúng tài liệu Flexible `app.yaml`. |
| Autoscaling tăng làm lỗi DB | Quá nhiều kết nối/transaction đồng thời | Kiểm tra connection pool, quota/DB capacity, backpressure. |
| Rollback traffic nhưng lỗi vẫn tiếp tục | Migration dữ liệu không tương thích, cache, background job hoặc version URL | Đối chiếu schema, jobs, session/caches và route; kích hoạt runbook dữ liệu. |
| Xóa version cũ gây lỗi một số request | Có client/cron/task đang dùng version-specific URL | Rà soát reference và logs trước khi xóa. |
| Hóa đơn vẫn tăng sau khi traffic về 0 | Manual/Flexible instances, version/instance nền, dịch vụ dữ liệu còn dùng | Xem Versions, Instance Hours, Compute/Network/Billing per service. |

### 10.1. Runbook 503 khi tăng traffic

1. **Xác định service/version đang nhận traffic** và thời điểm bắt đầu 503.
2. So sánh **RPS, CPU, instance count, pending latency và max instances** của từng version.
3. Kiểm tra application logs: exception, OOM, database timeout, lỗi config/secret.
4. Xem các dependency và connection pool — tăng instance có thể làm DB quá tải.
5. Nếu lỗi tập trung ở canary, **giảm tỷ lệ hoặc rollback** qua `set-traffic` sau xác nhận owner.
6. Xác minh request mới về version ổn định và error rate phục hồi; ghi incident cùng thay đổi traffic.
7. Khắc phục nguyên nhân rồi mới thử canary lại; không liên tục tăng `max_instances` như cách giải quyết mọi lỗi.

Nếu traffic đã được chuyển về v1 mà 503 vẫn cao, cần kiểm tra liệu **v1 còn có đủ instance/capacity** hoặc đang phụ thuộc cơ sở dữ liệu bị ảnh hưởng bởi v2. Có thể cần traffic migration thay vì cutover đột ngột, nhưng quyết định phải dựa trên số liệu và giới hạn sản phẩm.

## 11. Bài tập tình huống

### Tình huống A — API có tải biến động

API phục vụ trang bài học có trung bình 40 RPS và peak **360 RPS**. Thời gian xử lý trung bình ở peak là **150 ms**. Benchmark trong môi trường giống production cho thấy một instance F2 giữ SLO với khoảng **12 request đồng thời thực tế**; khi quá ngưỡng, latency p99 tăng mạnh.

**Yêu cầu:** ước lượng số instance tối thiểu theo concurrency, chỉ ra vì sao cần thêm headroom, đề xuất Automatic hay Manual, và nêu metric phải đo.

**Hướng giải:**

\[
360 \times 0{,}15 = 54\text{ request đồng thời}
\]

Trong điều kiện lý tưởng, `ceil(54/12) = 5` instance. Đây chỉ là **cận ước lượng**, không phải giá trị `max_instances` cuối: p99, peak burst, thời gian startup, CPU, dependency và quota có thể đòi thêm capacity. Với traffic dao động, **Standard Automatic** có thể phù hợp, với min/max, class và concurrency được thử bằng load test; giám sát p99, RPS, số instance, 503, DB connection và chi phí.

### Tình huống B — Worker chạy ít lần mỗi ngày

Service tạo báo cáo chỉ nhận yêu cầu vài lần/ngày, mỗi request có thể mất 30–60 giây. Đội dự định dùng Standard Manual B8 với hai instance suốt 24 giờ.

**Yêu cầu:** so với Basic B2, Automatic F2 và một luồng tác vụ qua Cloud Tasks. Xác định điều kiện để chọn mỗi giải pháp.

**Hướng giải:** Basic có thể giảm chi phí nhờ dừng instance khi idle nhưng có cold start; Manual duy trì sẵn capacity và có chi phí nền; Automatic phù hợp nếu mã/request đáp ứng giới hạn và tính chất runtime. Với xử lý lâu, nên đánh giá queue, retry/idempotency và giới hạn thời lượng request thay vì chọn B8 chỉ vì request dài. Quyết định phụ thuộc độ trễ chấp nhận được, độ dài công việc, bộ nhớ và môi trường.

### Tình huống C — Canary sai cách gây lệch trải nghiệm

Đội muốn phát hành UI mới cho 10% học viên. Họ dùng `--split-by=ip`, nhưng phần lớn request đi qua reverse proxy công ty và học viên dùng mạng di động. Trong log, v2 có lúc nhận 35% traffic, cùng một học viên đổi UI giữa các phiên.

**Yêu cầu:** chọn phương pháp split khác và giải thích điều gì vẫn phải kiểm soát.

**Hướng giải:** dùng **cookie splitting** và bảo đảm client giữ `GOOGAPPUID`. Đánh giá các request đi qua proxy, các call nội bộ và cache/Vary; đồng thời kiểm tra API/schema/database tương thích giữa v1/v2. Cookie giúp sticky tương đối, không phải hệ thống identity hoặc session security.

### Tình huống D — 5xx tăng sau canary

App Engine Standard `api` đang chia v1 95%, v2 5%. Sau 15 phút, error rate v2 tăng, database connections đạt giới hạn. V2 mở connection pool 30 per instance và `max_instances: 20`.

**Yêu cầu:** nêu cách xử lý cấp tốc và giải pháp dài hạn.

**Hướng giải:** giảm tỷ lệ hoặc rollback v2 theo runbook, xác minh v1 và DB phục hồi. Sau đó kiểm tra số instance × pool connections, định tuyến, retry storm và transaction latency. Khắc phục pool/concurrency/backpressure và test tải trước lần phát hành sau; không tăng `max_instances` hoặc DB role đặc quyền theo cảm tính.

## 12. Câu hỏi tự kiểm tra

1. **Scaling cấu hình theo service hay version?** — Trong `app.yaml` theo **version**; service có thể có nhiều version với scaling riêng.
2. **Standard Automatic dùng instance class B2 được không?** — Không; Automatic dùng họ **F**, Basic/Manual dùng họ **B**.
3. **Flexible có `basic_scaling` hoặc `min_instances: 0` như Standard không?** — Không; Flexible dùng automatic/manual và các trường `min_num_instances`/`max_num_instances`.
4. **Đặt `max_concurrent_requests: 50` có bảo đảm instance xử lý 50 request đúng SLO không?** — Không; đó là mức scheduling, phải benchmark ứng dụng.
5. **Deploy `--no-promote` có làm service URL chuyển sang bản mới không?** — Không; version có thể được triển khai mà không thay tỷ lệ traffic.
6. **Version 0% traffic có chắc không truy cập được không?** — Không; version-specific URL có thể vẫn truy cập được nếu không có kiểm soát riêng.
7. **Lý do IP split có thể lệch 10%?** — NAT/proxy gom request, IP thay đổi và mẫu nhỏ.
8. **Cookie split có thể dùng làm xác thực người dùng không?** — Không; `GOOGAPPUID` là cơ chế phân nhóm traffic, không xác định quyền nghiệp vụ.
9. **Warmup có loại bỏ mọi cold start không?** — Không, warmup là best effort.
10. **Rollback traffic có tự rollback database schema không?** — Không; phải thiết kế schema compatibility và runbook dữ liệu.
11. **Vì sao canary nhỏ vẫn có phí đáng kể?** — v1/v2 cùng chạy và có thể có min/manual/Flexible instances độc lập.
12. **Chọn max instances chỉ theo số tiền mong muốn có đủ không?** — Không; giới hạn quá thấp có thể làm rớt request, cần đối chiếu peak/SLO và các lớp giảm tải.

## 13. Tài liệu Google Cloud tham khảo

- [App Engine Standard — How instances are managed](https://cloud.google.com/appengine/docs/standard/how-instances-are-managed): ba chế độ scaling, startup, request timeout và cold start.
- [App Engine Standard — Overview và instance classes](https://cloud.google.com/appengine/docs/standard/overview): F/B class, RAM/CPU tương đối và môi trường Standard.
- [App Engine Standard — app.yaml reference](https://cloud.google.com/appengine/docs/standard/reference/app-yaml): `automatic_scaling`, `basic_scaling`, `manual_scaling`, `instance_class`.
- [App Engine Flexible — app.yaml reference](https://cloud.google.com/appengine/docs/flexible/reference/app-yaml): `resources`, `min_num_instances`, `max_num_instances` và manual scaling.
- [App Engine Standard — Configuring warmup requests](https://cloud.google.com/appengine/docs/standard/configuring-warmup-requests): best effort warmup và khởi tạo instance.
- [App Engine Standard — Splitting traffic](https://cloud.google.com/appengine/docs/standard/splitting-traffic): IP/cookie routing, version URLs và A/B testing.
- [App Engine Standard — Migrating traffic](https://cloud.google.com/appengine/docs/standard/migrating-traffic): chuyển toàn bộ traffic và giảm loading latency.
- [gcloud app deploy](https://cloud.google.com/sdk/gcloud/reference/app/deploy): `--version`, `--no-promote` và các tùy chọn deploy.
- [gcloud app services set-traffic](https://cloud.google.com/sdk/gcloud/reference/app/services/set-traffic): `--splits`, `--split-by`, `--migrate`.
- [gcloud app services delete](https://cloud.google.com/sdk/gcloud/reference/app/services/delete): xóa service/version trong project.
- [App Engine pricing](https://cloud.google.com/appengine/pricing): phí Standard, Flexible, instance-hours và thành phần liên quan.
- [App Engine monitoring](https://cloud.google.com/appengine/docs/standard/monitoring): quan sát service, version và ứng dụng.

**Kết luận:** quản lý App Engine hiệu quả là cân bằng **capacity của từng instance**, **cách App Engine mở rộng số instance** và **đường đưa request tới version**. Dùng dữ liệu tải thực để chọn class/min/max, deploy version mới không tự promote, tăng traffic có kiểm soát và giữ khả năng rollback. Một cấu hình chỉ đáng tin khi thỏa **SLO, tính đúng đắn của dữ liệu, quyền truy cập và ngân sách** trong phép đo thực tế.
